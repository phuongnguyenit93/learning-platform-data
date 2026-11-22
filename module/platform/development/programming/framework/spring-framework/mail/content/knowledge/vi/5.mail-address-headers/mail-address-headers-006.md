# Message-ID và định danh message

Khi ứng dụng **Spring Framework Mail** gửi email, người phát triển thường cần trả lời các câu hỏi: “Thông điệp này có định danh nào?”, “Log gửi ở ứng dụng tương ứng với thư nào trong hệ thống email?”, “Làm sao cho người nhận trả lời đúng luồng hội thoại?”, “Vì sao SMTP báo thành công nhưng tôi không tìm thấy thư?”, hoặc “Gửi lại với cùng Message-ID có tránh được email trùng không?”.

Trung tâm của những câu hỏi đó là header **`Message-ID`**. Đây là định danh ở cấp *thông điệp email* theo chuẩn định dạng thư, nhưng trong hệ thống thực tế còn tồn tại **ID sự kiện nghiệp vụ**, **ID giao dịch SMTP**, **ID hàng đợi của máy chủ** và **ID do nhà cung cấp email trả về**. Mỗi ID giải quyết một việc khác nhau; trộn lẫn chúng dễ dẫn đến sai lệch trạng thái gửi thư, lỗi đối soát và luồng email bị phân tán.

Bài học này đi từ cú pháp `Message-ID`, cách Spring/Jakarta Mail sinh và sử dụng nó, đến thiết kế truy vết, threading, retry và xử lý các trường hợp cần định danh message trên nhiều hệ thống.

## 1. Message-ID là gì?

**`Message-ID`** là một trường header của email, được mô tả trong chuẩn định dạng thông điệp Internet (RFC 5322). Nó nhận diện **một phiên bản thông điệp cụ thể** do hệ thống tạo thư phát hành. Giá trị thường có dạng:

```text
Message-ID: <b164ef38-96d3-4fc5-a05a-8bbdc4ce8411@mailer.example.com>
```

Quan sát giá trị này:

- `Message-ID` là **tên trường header**.
- Phần `<...>` là giá trị `msg-id` được chuẩn hóa, thường bao gồm một phần định danh bên trái, dấu `@` và phần miền định danh ở bên phải.
- `mailer.example.com` là một miền định danh do bên tạo thư kiểm soát trong ví dụ.
- Chuỗi bên trái cần đủ khả năng phân biệt giữa các thông điệp được phát hành; UUID là một lựa chọn dễ áp dụng.

Với dạng thường dùng, ta có thể biểu diễn:

```text
Message-ID: <unique-id@domain>
             |         |
             |         +-- namespace / domain định danh
             +------------ phần phân biệt thông điệp
```

Một `Message-ID` nên **duy nhất trên phạm vi toàn cầu** đối với từng thông điệp được tạo. Tính duy nhất chủ yếu là trách nhiệm của bên sinh ID, không phải điều mà máy chủ SMTP tự chứng minh. Không nên dùng một ID cố định cho tất cả email của ứng dụng.

### 1.1. Message-ID nằm trong header, không phải lệnh SMTP

Trước khi truyền nội dung thư, SMTP dùng các lệnh như `MAIL FROM` và `RCPT TO` để khai báo phong bì gửi. Khi bước `DATA` bắt đầu, client gửi **headers và body**, trong đó có thể có `Message-ID`:

```text
C: MAIL FROM:<no-reply@example.com>
S: 250 2.1.0 OK
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: Example Shop <no-reply@example.com>
C: To: alice@example.net
C: Subject: Xac nhan don hang
C: Message-ID: <order-evt-93a0@mailer.example.com>
C: Date: Thu, 12 Nov 2026 08:00:00 +0000
C:
C: Don hang cua ban da duoc ghi nhan.
C: .
S: 250 2.0.0 Queued as Q7F28A
```

Các tiền tố `C:` và `S:` chỉ là ký hiệu minh họa client/server, không được gửi trên đường truyền. Sau khi SMTP server trả `250` cho `DATA`, ta chỉ biết server ở chặng đó đã **chấp nhận trách nhiệm xử lý thông điệp**. Không thể suy ra thư đã được giao đến Inbox hoặc đã được người nhận đọc.

Trong ví dụ trên:

- `<order-evt-93a0@mailer.example.com>` là **Message-ID của nội dung thư**.
- `Q7F28A` là **queue ID** do SMTP server minh họa cấp khi tiếp nhận.
- Hai giá trị độc lập; không có quy tắc rằng Message-ID phải chứa queue ID hoặc ngược lại.

### 1.2. Message-ID khác các địa chỉ và header thường gặp

| Trường | Dùng để làm gì? | Có phải Message-ID không? |
|---|---|---|
| `From:` | Địa chỉ người gửi hiển thị trong thư. | Không. |
| `To:` / `Cc:` | Địa chỉ người nhận hiển thị trong nội dung thư. | Không. |
| `MAIL FROM` / `RCPT TO` | Địa chỉ trong phong bì giao dịch SMTP. | Không; đây là lệnh SMTP, không phải header. |
| `Date:` | Thời điểm gửi theo thông điệp. | Không; thời điểm không đủ định danh duy nhất. |
| `Subject:` | Tiêu đề thông điệp. | Không; nhiều thư có thể trùng tiêu đề. |
| `Message-ID:` | Định danh của thông điệp theo định dạng email Internet. | Có. |
| `In-Reply-To:` | Tham chiếu Message-ID của thông điệp mà thư đang trả lời. | Không; đây là quan hệ giữa các thư. |
| `References:` | Danh sách các Message-ID được tham chiếu trong một chuỗi hội thoại. | Không; đây là metadata tạo luồng. |
| `Content-ID:` | Định danh **một MIME part**, thường dùng với ảnh inline và `cid:`. | Không; nó định danh một phần của thư. |
| `Received:` | Thông tin một số chặng máy chủ chuyển thư thêm vào. | Không; đây là dấu vết đường đi. |

Một email có thể mang nhiều loại ID vì chúng mô tả **những thực thể khác nhau**.

## 2. Cú pháp, tính duy nhất và nơi sinh Message-ID

Theo RFC 5322, giá trị `msg-id` có hình thức bao quát gồm dấu ngoặc nhọn góc và hai thành phần trái/phải được phân tách bởi `@`. Cú pháp chuẩn chi tiết hơn việc tự nối hai chuỗi bất kỳ; cách đơn giản để triển khai là dùng ID chỉ gồm ký tự an toàn và một domain định danh hợp lệ.

Ví dụ dễ đọc:

```text
Message-ID: <abc123@example.com>
Message-ID: <20261112.080000.845d28fd@mailer.example.com>
Message-ID: <6d34cc43-7dd0-47dd-9408-411ee17cc1fa@notifications.example.com>
```

Các ví dụ trên mang tính minh họa; không dùng lại nguyên giá trị trong hệ thống sản xuất.

### 2.1. Ai chịu trách nhiệm sinh?

Thông thường, **hệ thống tạo email** sinh hoặc nhờ thư viện sinh `Message-ID`. Nó có thể là:

1. Ứng dụng tự gắn header trước khi chuyển thư;
2. Jakarta Mail sinh khi chuẩn bị thông điệp để gửi;
3. Một mail service hoặc provider sinh/thay thế `Message-ID` nếu thông điệp tới họ thiếu hoặc họ áp dụng chính sách riêng.

RFC khuyến nghị mỗi thông điệp nên có Message-ID. Trên thực tế, email nhận được vẫn có thể **thiếu header**, có header sai định dạng hoặc có giá trị trùng. Hệ thống tiêu thụ email cần dự phòng các trường hợp đó.

### 2.2. Cần sinh ID như thế nào?

Một chính sách đơn giản là sử dụng **UUID ngẫu nhiên kết hợp miền do ứng dụng kiểm soát**:

```java
import java.util.UUID;

String messageId =
    "<" + UUID.randomUUID() + "@mailer.example.com>";
```

Đây là minh họa cách tạo **chuỗi Message-ID**, chưa tự gắn nó vào bất kỳ email nào. Phần domain bên phải giúp tạo namespace định danh có ý nghĩa và phần UUID giúp giảm xác suất trùng.

Cần tránh:

- Dùng số thứ tự như `<1@localhost>` cho mọi lần chạy, vì dễ trùng giữa các máy.
- Dùng duy nhất timestamp tính bằng giây, vì nhiều thư có thể được phát hành trong cùng một giây.
- Đưa email người nhận, số điện thoại, access token hoặc bí mật vào `Message-ID`.
- Chứa các ký tự không hợp lệ trong phần định danh khi tự nối chuỗi.
- Cho rằng Message-ID do client gửi lên hoặc nhận từ người ngoài là một định danh đã được xác thực.

**`Message-ID` không phải token bảo mật.** Nó có thể được người nhận, máy chủ trung gian và hệ thống xử lý mail quan sát, trích xuất hoặc sao chép. Không nên dùng nó làm khóa cho hành động nhạy cảm như xác thực tài khoản hay truy cập tài nguyên riêng.

### 2.3. Message-ID có tồn tại trước khi gửi không?

Không nên mặc định rằng một đối tượng `MimeMessage` mới tạo đã có Message-ID. Với Jakarta Mail, giá trị này thường được tạo khi thông điệp được chuẩn bị hoặc lưu thay đổi bằng `saveChanges()`, và thư viện gửi có thể gọi bước đó giúp ứng dụng.

Ví dụ ở mức API:

```java
MimeMessage message = mailSender.createMimeMessage();

// Lúc mới tạo, message.getMessageID() có thể trả về null.
message.saveChanges();

// Sau khi saveChanges(), implementation thường đã sinh Message-ID.
String generatedMessageId = message.getMessageID();
```

**Lưu ý:** `saveChanges()` không gửi thư qua mạng. Nó hoàn thiện trạng thái và một số header của đối tượng MIME. Việc gọi `saveChanges()` thêm lần nữa trong quy trình gửi có thể tác động đến Message-ID tùy thư viện/implementation. Vì vậy giá trị đọc trước khi gửi không nhất thiết là định danh cuối cùng thực sự xuất hiện ở thư đã nhận.

Nếu cần một ID **ổn định trước cả bước gửi**, nên có một **ID nghiệp vụ riêng** cho yêu cầu gửi email, độc lập với Message-ID mà tầng email quyết định.

## 3. Phân biệt tất cả các loại message ID trong một hệ thống gửi mail

Đây là phần quan trọng nhất khi thiết kế hệ thống: có thể xuất hiện nhiều chuỗi mang tên “message ID” ở các tầng khác nhau.

| Định danh | Ai cấp? | Phạm vi | Công dụng điển hình |
|---|---|---|---|
| **Application message ID / event ID** | Ứng dụng | Nghiệp vụ, cơ sở dữ liệu, queue | Truy vết sự kiện “cần gửi thư”, ngăn tạo job trùng, tìm log và liên hệ với đơn hàng. |
| **RFC Message-ID / Internet Message-ID** | Bên tạo thư hoặc mail implementation/provider | Thông điệp email | Nhận diện thư trong header, tạo luồng hội thoại, đối chiếu một số hệ thống mail. |
| **SMTP queue ID** | Máy chủ SMTP tiếp nhận ở một chặng | Hàng đợi của máy chủ đó | Tra cứu log của SMTP relay, ví dụ mã sau `250 Queued as ...`. |
| **Provider message ID** | Dịch vụ email/API | Trong phạm vi nhà cung cấp | Truy vấn trạng thái gửi, đối chiếu event, webhook, dashboard của provider. |
| **Mailbox UID / ID nội bộ** | Máy chủ hoặc ứng dụng lưu hộp thư | Một hộp thư hoặc kho lưu trữ | Xác định bản ghi email đã lưu; có thể khác nhau giữa các hộp thư dù cùng một thông điệp. |
| **Content-ID** | Bên xây MIME | Một MIME part | Liên kết ảnh inline/tài nguyên với HTML thông qua `cid:...`. |

Ví dụ luồng định danh trong một hệ thống thương mại điện tử:

```text
Đơn hàng ORD-1028
    |
    v
Sự kiện email EVT-f9b6              <-- application_event_id
    |
    v
Outbox -> Worker -> MimeMessage
                       |
                       +-- Message-ID:
                       |   <5bd29a@mailer.example.com>
                       |
                       +-- X-Correlation-ID: EVT-f9b6
    |
    v
SMTP relay tiếp nhận thư              <-- smtp_queue_id = Q7F28A
    |
    v
Dịch vụ email / event callback        <-- provider_message_id = provider-8391
    |
    v
Delivery / Bounce / Complaint
```

Không phải tất cả môi trường đều có đầy đủ các ID trên. Ví dụ, khi chỉ dùng SMTP relay đơn giản, ứng dụng có thể không nhận được provider message ID hoặc event delivery.

### 3.1. Vì sao không dùng Message-ID thay khóa chính của database?

Lý do gồm:

- Message-ID có thể được sinh muộn, sau khi ứng dụng tạo yêu cầu gửi.
- Một số dịch vụ thay đổi hoặc chuẩn hóa header.
- Một yêu cầu nghiệp vụ có thể tạo nhiều email khác nhau, ví dụ mỗi người nhận một thông điệp.
- Một thông điệp có thể được gửi nhiều lần do retry, trong khi hoạt động gửi và kết quả giao hàng cần theo dõi riêng.
- Email đầu vào có thể thiếu hoặc trùng Message-ID; không nên đặt niềm tin tuyệt đối vào header đến từ nguồn bên ngoài.

Vì vậy, **application ID** nên là khóa truy vết chủ đạo trong hệ thống nội bộ. Message-ID và provider ID là các giá trị quan sát bổ sung để đối soát.

## 4. JavaMailSender xử lý Message-ID như thế nào?

Trong Spring Framework Mail, `JavaMailSender` là interface gửi email. `JavaMailSenderImpl` thường sử dụng Jakarta Mail và SMTP transport. Với `SimpleMailMessage`, Spring có thể chuyển nội dung sang MIME ở tầng thực hiện; với `MimeMessage`, ứng dụng được phép thao tác trực tiếp trên header.

Quy trình khái quát:

```text
mailSender.createMimeMessage()
         |
         v
MimeMessageHelper đặt From / To / Subject / Text
         |
         v
Thêm header nghiệp vụ nếu cần
         |
         v
Chuẩn bị MIME (Date, Message-ID, MIME boundaries...)
         |
         v
mailSender.send(message)
         |
         v
SMTP DATA chứa các header thực tế
         |
         v
SMTP server tiếp nhận hoặc báo lỗi
```

Thư viện email có thể **tự sinh Message-ID** khi gửi. Hành vi bảo toàn một Message-ID do người dùng đặt có thể phụ thuộc phiên bản Spring/Jakarta Mail, implementation và nhà cung cấp phía sau; khi ID phải giữ nguyên, cần kiểm tra chính sách của transport và đối chiếu với thông điệp thực tế.

### 4.1. Ví dụ gửi email và đọc Message-ID

Ví dụ với Spring Boot 3.x / Spring Framework 6.x, Java 17+, Jakarta Mail:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

`application.yml` với SMTP hỗ trợ STARTTLS:

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

Hai biến `SMTP_USERNAME` và `SMTP_PASSWORD` nên được lấy từ môi trường hoặc secret store. Ví dụ sau dùng một **application ID** riêng, được sinh trước bước gửi:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.UUID;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public SentMailInfo sendOrderConfirmation(
            String recipient, String orderCode) throws MessagingException {

        String applicationId = UUID.randomUUID().toString();

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText(
            "Đơn hàng " + orderCode + " đã được ghi nhận."
        );

        // ID để liên hệ log SMTP với nghiệp vụ của ứng dụng.
        message.setHeader("X-Correlation-ID", applicationId);

        // Thư viện hoàn thiện MIME và gửi qua SMTP.
        mailSender.send(message);

        // Header có thể được tạo trong quá trình gửi.
        String rfcMessageId = message.getMessageID();
        return new SentMailInfo(applicationId, rfcMessageId);
    }

    public record SentMailInfo(
        String applicationId,
        String rfcMessageId
    ) {}
}
```

Điểm cần phân tích:

1. `UUID.randomUUID()` tạo **ID của ứng dụng** trước khi gửi. Nếu giao dịch nghiệp vụ có sẵn ID hoặc outbox row ID, nên sử dụng ID ổn định đó thay vì sinh ID mới mỗi lần retry.
2. `message.setHeader("X-Correlation-ID", applicationId)` gắn metadata truy vết vào thông điệp. Header tùy biến có thể được một số hệ thống giữ lại, biến đổi hoặc loại bỏ; không được coi nó là cơ chế xác thực.
3. `mailSender.send(message)` là thao tác gửi, có thể ném `MailException` nếu thất bại ở tầng Spring Mail.
4. `message.getMessageID()` đọc Message-ID của `MimeMessage` sau lần gửi thành công tại tầng API. Kết quả có thể là `null` trong các trường hợp implementation khác biệt; cần xử lý như metadata có thể thiếu.
5. Hai trường `applicationId` và `rfcMessageId` không nhất thiết giống nhau, và việc gọi gửi trả về bình thường **không chứng minh email đã đến Inbox**.

Nếu `send(...)` ném lỗi, phương thức trên không trả `SentMailInfo`. Trong hệ thống có outbox, **lưu application ID và yêu cầu gửi trước**, sau đó ghi trạng thái lần thử, lỗi và các ID quan sát được khi có kết quả; không để mất khả năng truy vết chỉ vì kết nối SMTP gián đoạn.

### 4.2. Có nên tự gắn header Message-ID?

Có trường hợp ứng dụng cần chủ động đặt một giá trị `Message-ID` hợp lệ. Về mặt cú pháp, có thể gắn header:

```java
String customMessageId =
    "<" + UUID.randomUUID() + "@mailer.example.com>";

MimeMessage message = mailSender.createMimeMessage();
message.setHeader("Message-ID", customMessageId);
```

Tuy nhiên, đoạn này **chỉ thể hiện cách đặt header**, không cam kết giá trị sẽ được giữ nguyên tới hộp thư nhận. Jakarta Mail có cơ chế cập nhật một số header khi `saveChanges()` chạy; một số phiên bản/implementation của Spring Mail có xử lý bảo toàn Message-ID do ứng dụng đặt, nhưng cách xử lý còn tùy môi trường và lớp dịch vụ gửi tiếp theo.

Khi cần một Message-ID do ứng dụng kiểm soát:

- Dùng cú pháp hợp lệ và chiến lược sinh ID đủ duy nhất.
- Hiểu thứ tự tạo MIME, `saveChanges()` và `send(...)` của implementation đang dùng.
- Ghi nhận giá trị thực tế sau gửi và đối chiếu header ở thông điệp đã đến hệ thống nhận.
- Kiểm tra nhà cung cấp email có chính sách ghi đè hoặc chuyển đổi Message-ID hay không.

Đối với phần lớn ứng dụng giao dịch, **để Jakarta Mail sinh Message-ID và dùng một application ID riêng để truy vết** sẽ đơn giản hơn.

### 4.3. Vì sao SimpleMailMessage không đủ khi cần thao tác header?

`SimpleMailMessage` thích hợp gửi text thuần, cung cấp các trường phổ biến như `from`, `to`, `subject`, `text`. Nó không phải API tổng quát để sửa mọi MIME header. Khi cần đọc hoặc đặt `Message-ID`, `In-Reply-To`, `References` hay header tùy biến, nên tạo **`MimeMessage`** qua `JavaMailSender.createMimeMessage()`.

Điều đó **không đồng nghĩa** thư text thuần gửi bằng `SimpleMailMessage` sẽ thiếu Message-ID; transport có thể tự tạo nó trong quá trình gửi. Khác biệt ở đây là khả năng **điều khiển và quan sát header** từ mã ứng dụng.

## 5. Message-ID và luồng hội thoại: In-Reply-To, References

Một mục đích quan trọng của `Message-ID` là giúp mail client **nhóm thư trả lời thành một cuộc hội thoại**.

Giả sử email gốc:

```text
From: support@example.com
To: alice@example.net
Subject: Ticket #123
Message-ID: <ticket123-initial@support.example.com>
```

Alice trả lời:

```text
From: alice@example.net
To: support@example.com
Subject: Re: Ticket #123
Message-ID: <alice-reply-01@client.example.net>
In-Reply-To: <ticket123-initial@support.example.com>
References: <ticket123-initial@support.example.com>
```

Support trả lời tiếp:

```text
From: support@example.com
To: alice@example.net
Subject: Re: Ticket #123
Message-ID: <ticket123-reply-02@support.example.com>
In-Reply-To: <alice-reply-01@client.example.net>
References: <ticket123-initial@support.example.com> <alice-reply-01@client.example.net>
```

Ở đây:

- **`Message-ID`** của mỗi thư là một định danh **mới**.
- **`In-Reply-To`** chỉ đến thông điệp mà thư mới đang trả lời.
- **`References`** lưu chuỗi Message-ID có liên quan để hỗ trợ dựng cây hội thoại.

Thứ tự và nội dung của `References` nên được tạo từ metadata của email gốc và quy tắc threading phù hợp. Ứng dụng email có thể còn xem xét subject hoặc các heuristics khác khi nhóm thư; không nên mặc định `In-Reply-To`/`References` sẽ bảo đảm mọi client tạo ra đúng một conversation.

### 5.1. Tạo email trả lời trong Spring

Ví dụ, ứng dụng đã xử lý một email đầu vào đáng tin cậy và có `Message-ID` của nó:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class ReplyMailService {
    private final JavaMailSender mailSender;

    public ReplyMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReply(
            String recipient,
            String originalMessageId,
            String existingReferences) throws MessagingException {

        MimeMessage reply = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(reply, "UTF-8");

        helper.setFrom("support@example.com");
        helper.setTo(recipient);
        helper.setSubject("Re: Yêu cầu hỗ trợ");
        helper.setText("Chúng tôi đã tiếp nhận phản hồi của bạn.");

        // Các giá trị phải đến từ header đã parse/kiểm tra hợp lệ.
        reply.setHeader("In-Reply-To", originalMessageId);

        String references = (existingReferences == null
                || existingReferences.isBlank())
            ? originalMessageId
            : existingReferences.trim() + " " + originalMessageId;
        reply.setHeader("References", references);

        // Message-ID của thư trả lời thường do thư viện tự sinh.
        mailSender.send(reply);
    }
}
```

**Điều kiện của ví dụ:** `originalMessageId` và `existingReferences` đã được lấy từ một thông điệp đã parse, kiểm tra cú pháp/độ dài và xử lý tránh chèn header không hợp lệ. Không đưa trực tiếp chuỗi tùy ý do người dùng nhập vào `setHeader(...)`. Hệ thống thực tế cần chuẩn hóa danh sách References để tránh trùng lặp hoặc phát triển vô hạn trong những cuộc hội thoại dài.

**Không sao chép `Message-ID` của thư gốc sang Message-ID của thư trả lời.** Thư trả lời là một thông điệp mới, nên có ID mới; liên kết với thư cũ qua `In-Reply-To` và `References`.

### 5.2. Có phải cùng Subject thì cùng một thread?

Không. Nhiều email có thể có cùng subject “Thông báo đơn hàng” mà thuộc những người nhận và sự kiện khác nhau. Subject không phải định danh duy nhất. Ngược lại, các mail client cũng có thể đưa ra quyết định gom nhóm khác nhau ngay cả khi header tham chiếu hợp lệ. Khi hệ thống support cần một luồng nghiệp vụ ổn định, nên duy trì **ticket ID riêng** trong database thay vì phụ thuộc hoàn toàn vào cách client email nhóm thư.

## 6. Message-ID khi gửi nhiều người nhận, gửi lại và retry

### 6.1. Một thông điệp gửi nhiều người nhận

Trong một giao dịch SMTP, client có thể khai báo nhiều `RCPT TO` cho cùng nội dung thư. Vì đó vẫn là **một thông điệp**, các người nhận có thể thấy cùng `Message-ID`:

```text
MAIL FROM:<noreply@example.com>
RCPT TO:<alice@example.net>
RCPT TO:<bob@example.net>
DATA
Message-ID: <notice-001@mailer.example.com>
...
```

Nếu hệ thống lại tạo **mỗi người nhận một email cá nhân hóa** với nội dung, thời điểm gửi hoặc header khác nhau, nên coi đó là các thông điệp riêng và cấp Message-ID phù hợp cho từng thông điệp.

Số lượng người nhận, số giao dịch SMTP và số Message-ID vì vậy **không luôn bằng nhau**.

### 6.2. Retry có phải giữ nguyên Message-ID?

Không có quy tắc rằng chỉ cần giữ nguyên Message-ID thì mail server sẽ tự loại bỏ thư trùng. Một SMTP relay hoặc inbox hoàn toàn có thể chấp nhận **hai bản giao hàng mang cùng Message-ID**. Ngược lại, một số hệ thống có logic dedup riêng, nhưng không nên phụ thuộc vào hành vi không được bảo đảm đó.

Giả sử:

1. Worker gửi đủ dữ liệu thư đến SMTP server.
2. Server đã tiếp nhận nhưng phản hồi `250` thất lạc do mạng.
3. Worker thấy timeout, đánh dấu lỗi và gửi lại.
4. Người nhận có thể nhận **hai email**, kể cả khi Message-ID của hai lần gửi giống nhau.

Sơ đồ:

```text
Outbox job EVT-202
       |
       +-- attempt 1 --> SMTP chấp nhận thư
       |                  nhưng client không nhận được 250
       |
       +-- attempt 2 --> SMTP chấp nhận thư lần nữa
                          |
                          v
                    Có thể giao trùng
```

Chiến lược nên dùng:

- Gắn **application message ID** hoặc outbox ID ổn định với một yêu cầu nghiệp vụ.
- Ghi nhận từng **send attempt** và trạng thái của nó riêng biệt.
- Dùng retry có backoff, giới hạn số lần và xử lý trường hợp kết quả **không xác định**.
- Với email liên quan thanh toán, xác minh hoặc nghiệp vụ nhạy cảm, thiết kế idempotency ở nguồn tạo yêu cầu và cân nhắc đối soát provider event.
- Không coi việc dùng lại một `Message-ID` là cơ chế đảm bảo “exactly once”.

### 6.3. Tại sao nên tách app ID khỏi Message-ID khi retry?

Giả sử ứng dụng dùng outbox:

| Trường | Giá trị ví dụ | Mục đích |
|---|---|---|
| `outbox_id` | `EVT-202` | Yêu cầu nghiệp vụ duy nhất. |
| `attempt_no` | `1`, `2` | Lần thử gửi. |
| `internet_message_id` | `<e9cd@mailer.example.com>` | Message-ID quan sát được ở tầng email. |
| `smtp_queue_id` | `Q71F` | Mã hàng đợi do SMTP relay trả về, nếu có. |
| `provider_message_id` | `P-0092` | Mã riêng của provider, nếu có. |
| `status` | `PENDING`, `SENT_TO_PROVIDER`, `UNKNOWN`, `FAILED` | Trạng thái nội bộ theo bằng chứng đã có. |

Một outbox event có thể có nhiều send attempts. Mỗi attempt có thể thu được hoặc không thu được ID của tầng SMTP/provider. Thiết kế này dễ mở rộng hơn việc gộp mọi thứ thành một cột `messageId` không rõ nguồn.

## 7. Đối soát Message-ID với log SMTP và provider

Ví dụ đường đi:

```text
App log:       correlation_id=EVT-202
Message MIME:  Message-ID=<e9cd@mailer.example.com>
SMTP response: 250 2.0.0 queued as Q71F
Provider API:  provider_message_id=P-0092
Webhook:       event=delivered, provider_message_id=P-0092
```

Những giá trị này có thể liên kết bằng bảng đối chiếu nếu hệ thống cấp chúng và giữ lại thông tin cần thiết. **Không nên giả định SMTP queue ID được nhà cung cấp API trả về giống Message-ID trong header.**

### 7.1. Khi gửi bằng SMTP

SMTP response đôi khi chứa queue ID, nhưng không phải lúc nào cũng có. `JavaMailSender.send(...)` thông thường là API cấp cao, không nhất thiết cung cấp trực tiếp queue ID của server cho mã nghiệp vụ. Nếu cần đối soát, có thể phải dựa vào log của relay, header/metadata do ứng dụng gắn và chức năng sự kiện riêng của nhà cung cấp.

### 7.2. Khi gửi bằng API/SDK

Một provider có thể trả về một ID riêng ngay sau HTTP request thành công. ID đó hữu ích để truy vấn delivery event, bounce hoặc complaint. Nhưng HTTP request thành công cũng thường chỉ là **provider đã tiếp nhận yêu cầu**, chưa phải người nhận đã nhận thư.

Nếu webhook chứa Message-ID, cần xác nhận tài liệu provider: một số dịch vụ đặt tên trường “message_id” cho **ID nội bộ**, số khác cho RFC Message-ID, số khác chứa cả hai. Hãy phân biệt chúng bằng tên trường rõ ràng trong database.

### 7.3. Message-ID không tự chứng minh tính xác thực

Một email giả mạo có thể chứa `Message-ID` nhìn hoàn toàn hợp lệ. Header này không thay thế xác thực nguồn gửi (SPF, DKIM, DMARC), xác thực người dùng hoặc chữ ký ứng dụng. Người nhận có thể chèn một ID trùng với ID đã có.

Nếu hệ thống xử lý **email đầu vào**, hãy xem Message-ID như metadata không đáng tin cậy cho đến khi được kiểm tra và đặt trong ngữ cảnh hộp thư/nguồn nhận. Không nên dùng riêng Message-ID để quyết định cấp quyền, thanh toán hoặc kích hoạt thao tác nhạy cảm.

## 8. Thiết kế lưu trữ định danh trong hệ thống Spring

Một mô hình dữ liệu minh họa:

```text
email_outbox
  id                   UUID / String  (PK)
  business_event_type  String
  business_event_id    String
  recipient            String
  template_code        String
  status               Enum
  created_at           Timestamp

email_send_attempt
  id                   UUID / String  (PK)
  outbox_id            FK -> email_outbox.id
  attempt_number       Integer
  started_at           Timestamp
  finished_at          Timestamp?
  internet_message_id  String?
  smtp_queue_id        String?
  provider_message_id  String?
  smtp_response_code   String?
  error_category       String?
  status               Enum
```

`?` biểu thị một trường có thể vắng mặt, không phải cú pháp SQL. Đây là mô hình khái niệm để nhận diện các lớp định danh, không phải schema bắt buộc cho mọi ứng dụng.

Luồng xử lý có thể đi như sau:

1. Giao dịch nghiệp vụ tạo yêu cầu gửi và lưu `email_outbox.id` ổn định; với transactional outbox, thao tác này được ghi cùng transaction của sự kiện nghiệp vụ.
2. Worker lấy job, tạo attempt mới và ghi thời gian bắt đầu.
3. Worker soạn MIME, đặt header correlation nếu phù hợp, rồi gọi `JavaMailSender.send(...)` hoặc provider API.
4. Ghi lại kết quả API và ID quan sát được, phân biệt “SMTP/provider tiếp nhận” với “đã giao”.
5. Nếu có webhook giao hàng hoặc bounce, đối chiếu theo provider ID/correlation ID được công bố và cập nhật trạng thái.
6. Với lỗi timeout không rõ kết quả, xử lý trạng thái `UNKNOWN` và chính sách retry/đối soát thay vì kết luận chắc chắn đã thất bại.

Với ứng dụng chỉ gửi một vài email thông báo và không cần quan sát từng lần thử, schema trên có thể quá phức tạp. Khi đó vẫn nên biết rõ **ID nào thuộc nghiệp vụ** và **ID nào là header email**, để không lẫn lộn khi debug.

## 9. Những lỗi và ngộ nhận thường gặp

### 9.1. “Mỗi email chắc chắn phải có Message-ID”

Phần lớn email chuẩn sẽ có `Message-ID`, nhưng hệ thống nhận mail vẫn có thể gặp thư thiếu header, header sai định dạng hoặc trùng ID. Không được giả định dữ liệu đầu vào luôn hoàn hảo.

### 9.2. “SMTP trả 250 nghĩa là Message-ID đã được giao đến Inbox”

Sai. Phản hồi 250 sau `DATA` chỉ nói SMTP server **đã tiếp nhận thông điệp ở chặng đó**. Việc giao cuối, bounce và hiển thị trong Inbox còn phụ thuộc xử lý tiếp theo.

### 9.3. “Message-ID có thể dùng thay cho request ID và queue ID”

Sai về phạm vi. Message-ID là metadata của thông điệp; request ID, queue ID, provider ID có vòng đời và nguồn cấp khác. Chỉ khi có mapping rõ ràng mới có thể truy vết qua các tầng.

### 9.4. “Mỗi lần gọi send luôn tạo Message-ID mới”

Không nên khẳng định như vậy. Kết quả còn tùy đối tượng MIME có được dùng lại, có header được đặt sẵn, bước `saveChanges()` và cách implementation xử lý. Về mặt thiết kế ứng dụng, một thông điệp mới nên có Message-ID riêng; nếu muốn gửi nhiều nội dung khác nhau, hãy tạo những `MimeMessage` độc lập.

### 9.5. “Cùng Message-ID thì sẽ không bao giờ nhận thư trùng”

Sai. Message-ID không phải khóa idempotency có hiệu lực chung cho SMTP. Hạ tầng nhận có thể xử lý hai thông điệp giống hoặc khác nhau mang cùng Message-ID theo cách riêng.

### 9.6. “Message-ID chính là Content-ID của logo inline”

Sai. `Message-ID` nhận diện toàn bộ email, còn `Content-ID` nhận diện một part như hình ảnh. HTML `<img src="cid:logo">` tham chiếu `Content-ID: <logo>` chứ không phải Message-ID của toàn thư.

### 9.7. “Muốn reply cùng thread thì đặt lại Message-ID của thư cũ”

Sai. Thư trả lời có **Message-ID mới** và liên kết đến thư trước bằng `In-Reply-To` / `References`. Dùng lại Message-ID của thư gốc làm mất ý nghĩa định danh từng thông điệp.

## 10. Quan sát Message-ID trong email đã gửi

Khi cần chẩn đoán, hãy xem **nguồn gốc thông điệp (raw email / show original)** trong ứng dụng đọc thư nếu ứng dụng đó có hỗ trợ. Các trường hữu ích:

```text
Message-ID: <e9cd@mailer.example.com>
Date: Thu, 12 Nov 2026 08:00:00 +0000
From: Example Shop <no-reply@example.com>
To: alice@example.net
Subject: Xac nhan don hang
In-Reply-To: <older@support.example.com>
References: <initial@support.example.com> <older@support.example.com>
```

Lưu ý ở bản raw:

- Header field name thường không phân biệt chữ hoa/chữ thường, nhưng nên dùng cách viết chuẩn `Message-ID` để dễ đọc.
- Những header có thể được xuống dòng (folding) khi dài; khi parse cần dùng thư viện hiểu định dạng MIME/RFC thay vì tách chuỗi thủ công theo xuống dòng.
- Không nên suy diễn rằng mọi hệ thống sẽ giữ nguyên toàn bộ header tùy biến.
- Một bản sao thư lưu trong mailbox có thể mang thêm header của hệ thống nhận; Message-ID là một trong các metadata cần đọc, không phải bản ghi đầy đủ về hành trình thư.

Với Jakarta Mail, có thể đọc:

```java
String messageId = mimeMessage.getMessageID();
String[] replies = mimeMessage.getHeader("In-Reply-To");
String[] references = mimeMessage.getHeader("References");
```

Hãy xử lý trường hợp `null` hoặc header nhiều giá trị; không ép buộc chuỗi nào cũng có mặt. Đối với email nhận từ bên ngoài, chuẩn hóa và kiểm tra giá trị trước khi lưu hoặc sử dụng cho tính năng reply.

## 11. Bài tập thực hành

### Bài 1 — Phân biệt các định danh trong log

Cho log:

```text
OUTBOX: id=EVT-502
MIME: Message-ID=<ab54@mailer.example.com>
SMTP: 250 2.0.0 queued as Q7F28A
WEBHOOK: message_ref=P-884, status=delivered
```

Hãy xác định ID nghiệp vụ, RFC Message-ID, SMTP queue ID và provider ID.

**Đáp án:** `EVT-502` là application/outbox ID, `<ab54@mailer.example.com>` là RFC Message-ID, `Q7F28A` là SMTP queue ID, còn `P-884` là ID của provider trong ví dụ. Cần mapping rõ ràng giữa chúng.

### Bài 2 — Tạo định danh cho email mới

Viết code Java tạo một UUID và kết hợp domain `mailer.example.com` thành chuỗi Message-ID dạng `<uuid@mailer.example.com>`. Giải thích tại sao không nên dùng một biến đếm tăng từ 1 trên mỗi lần khởi động ứng dụng.

**Gợi ý:** UUID giảm nguy cơ trùng giữa nhiều máy/tiến trình; biến đếm cục bộ dễ lặp lại khi restart hoặc scale ngang.

### Bài 3 — Tạo thư trả lời

Email gốc:

```text
Message-ID: <initial-001@support.example.com>
```

Email trả lời cần một `Message-ID` mới, `In-Reply-To: <initial-001@support.example.com>` và `References: <initial-001@support.example.com>`. Nếu lại có thư tiếp theo, danh sách References mở rộng theo các message cha của cuộc hội thoại.

### Bài 4 — Phân tích timeout sau DATA

Worker đã gửi thư nhưng mất kết nối trước phản hồi `250`. Có nên ghi “gửi thất bại chắc chắn” và thử ngay với cùng Message-ID không?

**Gợi ý:** Không thể chắc chắn server đã tiếp nhận hay chưa. Lưu trạng thái không xác định, dùng application ID/outbox để quản lý lần thử, cân nhắc đối soát và retry có giới hạn; cùng Message-ID không đảm bảo loại bỏ thư trùng.

### Bài 5 — Content-ID có thay được Message-ID không?

Email HTML có:

```html
<img src="cid:brand-logo" alt="Logo">
```

Part ảnh có `Content-ID: <brand-logo>`. Có thể dùng `brand-logo` làm Message-ID cho tất cả email của hệ thống không?

**Đáp án:** Không. CID chỉ định danh một MIME part để HTML tham chiếu. Message-ID phải định danh thông điệp mới và tránh trùng giữa các email được phát hành.

## 12. Tổng kết

**`Message-ID` là định danh của thông điệp email trong header theo chuẩn Internet**. Nó giúp nhận diện thư và kết nối luồng trả lời qua `In-Reply-To` / `References`. Trong ứng dụng Spring Framework Mail, Jakarta Mail thường sinh hoặc hoàn thiện header này trong quá trình chuẩn bị/gửi `MimeMessage`; ứng dụng có thể đọc bằng `getMessageID()` và thao tác header trực tiếp với `MimeMessage` khi cần.

Khi xây dựng hệ thống gửi email đáng tin cậy, hãy phân biệt rõ **application/outbox ID**, **RFC Message-ID**, **SMTP queue ID** và **provider message ID**. Dùng application ID ổn định để điều phối nghiệp vụ, lưu Message-ID như metadata của thư, liên kết các ID nếu có bằng chứng, và không dùng Message-ID làm cam kết giao hàng hay cơ chế chống gửi trùng.
