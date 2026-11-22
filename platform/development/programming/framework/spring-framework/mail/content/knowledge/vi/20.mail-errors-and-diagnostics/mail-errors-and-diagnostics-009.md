# Xác định message đã được gửi đến server hay chưa trong Spring Framework Mail

Khi ứng dụng Spring gọi `JavaMailSender.send(...)`, một lỗi timeout hoặc exception có thể khiến người phát triển đặt câu hỏi: **SMTP server đã nhận email chưa, hay email chưa hề rời ứng dụng?** Đây không chỉ là vấn đề log. Nếu retry trong khi server đã nhận message, người dùng có thể nhận thư trùng; nếu đánh dấu thành công khi server chưa nhận, hệ thống có thể làm mất thông báo.

Để chẩn đoán đúng, phải phân biệt **đã tạo message trong ứng dụng**, **đã gửi dữ liệu qua kết nối SMTP**, **SMTP relay đã chấp nhận trách nhiệm xử lý message**, và **người nhận cuối đã nhận thư**. Bốn trạng thái này không tương đương. Trong Spring Framework Mail, `JavaMailSender` giúp gửi email nhưng không tự cung cấp bằng chứng rằng mọi người nhận đã thấy email trong Inbox.

Bài học tập trung vào bằng chứng tại các bước SMTP, ý nghĩa của mã phản hồi, các khoảng không chắc chắn khi kết nối bị đứt, cách đọc lỗi JavaMail/Spring Mail, chiến lược correlation với provider, retry an toàn và quy trình chẩn đoán vận hành.

## 1. “Đã gửi” có nhiều nghĩa khác nhau

Trong hệ thống email, cùng một từ “sent” đôi khi được dùng cho các mốc rất khác nhau:

| Trạng thái | Điều đã thực sự xảy ra | Có chứng minh SMTP relay đã nhận message? |
| --- | --- | --- |
| CREATED | Đã tạo `SimpleMailMessage` hoặc `MimeMessage` | Không |
| ENQUEUED | Job gửi mail đã nằm trong executor/queue/outbox | Không |
| CONNECTED | Client mở kết nối TCP đến SMTP server | Không |
| AUTHENTICATED | Server chấp nhận xác thực SMTP | Không |
| ENVELOPE_ACCEPTED | Server đã chấp nhận MAIL FROM/RCPT TO | Chưa |
| DATA_STARTED | Server trả `354` và cho phép truyền nội dung | Chưa |
| DATA_SENT | Client truyền xong message và dấu kết thúc DATA | Chưa đủ nếu không có phản hồi cuối |
| SUBMITTED/ACCEPTED | Server trả phản hồi thành công cho **kết thúc DATA** | Có, đối với SMTP hop đó |
| DELIVERED | Có tín hiệu giao thư từ hệ thống nhận/provider | Không suy ra chỉ từ submission |
| OPENED | Có tín hiệu mở thư, nếu tính năng tracking được bật và có hiệu lực | Không phải bằng chứng chắc chắn người thật đã đọc |

Một lời gọi `@Async` đã được executor nhận chỉ cho biết task đã vào hàng đợi trong process. Một row `PENDING` trong transactional outbox chỉ cho biết ý định gửi đã được lưu. Không được gắn nhãn các trạng thái này là `SENT`.

Ngay cả `SUBMITTED` cũng chỉ nên hiểu là **SMTP server/relay mà ứng dụng kết nối đã chấp nhận message**, chứ không phải message chắc chắn đã vào Inbox.

## 2. SMTP session diễn ra như thế nào?

Giả sử Spring Mail kết nối tới một relay SMTP bằng STARTTLS, xác thực và gửi một message cho một recipient. Một phiên giao tiếp rút gọn có thể trông như sau:

~~~text
Client                                   SMTP server
  |                                            |
  |-------- TCP connection ------------------>|
  |<------- 220 Service ready ----------------|
  |-------- EHLO app.example.com ------------>|
  |<------- 250 capabilities -----------------|
  |-------- STARTTLS ------------------------>|
  |<------- 220 Ready for TLS ----------------|
  |====== TLS handshake =====================|
  |-------- EHLO app.example.com ------------>|
  |<------- 250 capabilities -----------------|
  |-------- AUTH ... ------------------------>|
  |<------- 235 Authentication successful ---|
  |-------- MAIL FROM:<bounce@example.com> -->|
  |<------- 250 Sender OK -------------------|
  |-------- RCPT TO:<user@example.net> ------>|
  |<------- 250 Recipient OK ----------------|
  |-------- DATA ---------------------------->|
  |<------- 354 Start mail input ------------|
  |-------- MIME headers and body ---------->|
  |-------- <CRLF>.<CRLF> -------------------->|
  |<------- 250 2.0.0 Queued as A1B2C3 -----|
  |-------- QUIT ---------------------------->|
  |<------- 221 Closing connection ----------|
~~~

Đây là một ví dụ minh họa, không phải bản ghi thực của bất kỳ provider nào. Một số hệ thống dùng implicit TLS hoặc không yêu cầu AUTH; không phải mọi server đều trả cùng câu chữ hay queue ID.

**Mốc quan trọng nhất đối với SMTP submission là phản hồi thành công sau dấu kết thúc DATA**. SMTP client truyền nội dung và kết thúc bằng dòng chứa duy nhất dấu chấm theo framing SMTP. Sau đó server trả kết quả tiếp nhận message.

### Vì sao `250` chưa chắc là “đã gửi”?

Mã `250` có thể xuất hiện ở nhiều bước:

- Sau `EHLO`: server trả capability.
- Sau `MAIL FROM`: địa chỉ envelope sender được chấp nhận.
- Sau `RCPT TO`: recipient được chấp nhận cho transaction hiện tại.
- Sau dấu kết thúc `DATA`: server thông báo đã chấp nhận toàn bộ message.

Chỉ nhìn log có dòng `250 OK` mà không biết nó gắn với lệnh nào là chưa đủ để kết luận message đã được chấp nhận.

### Vì sao `354` cũng chưa phải thành công?

Phản hồi `354 Start mail input` là lời mời client bắt đầu truyền nội dung DATA. Nếu client bị lỗi khi đang truyền nội dung hoặc server không trả kết quả cuối, trạng thái message chưa được xác nhận. Không đánh dấu SUBMITTED khi mới nhìn thấy `354`.

## 3. Bằng chứng mạnh nhất: kết quả cuối của DATA

Khi server trả mã thành công cuối cùng sau toàn bộ message DATA, theo ngữ nghĩa SMTP thông thường, server đã chấp nhận trách nhiệm xử lý message cho các envelope recipient tương ứng.

Ví dụ:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.com
C: To: user@example.net
C: Subject: Confirmed
C:
C: Your order is confirmed.
C: .
S: 250 2.0.0 Ok: queued as A1B2C3
~~~

Dòng `250 2.0.0 Ok: queued as A1B2C3` xuất hiện **sau DATA terminator** là bằng chứng SMTP server đã nhận submission. Nếu provider có queue ID `A1B2C3`, lưu ID đó để đối chiếu với mail log, dashboard hoặc support của provider.

Cần phân biệt ba kết luận:

1. **Server đầu tiên đã nhận submission**: có thể chứng minh bằng final success reply sau DATA.
2. **Message được chuyển tới hệ thống nhận tiếp theo**: có thể cần log/trace của relay.
3. **Message được giao tới mailbox người nhận**: cần tín hiệu delivery/bounce hoặc dữ liệu đáng tin cậy từ provider.

Không thể suy ra (2) hoặc (3) chỉ từ kết luận (1).

### Không phải mọi SMTP client API đều trả queue ID

`JavaMailSender.send(...)` không có một trường kết quả chuẩn mang `queueId` của SMTP server. Nếu muốn lưu queue ID từ response DATA, cần khả năng quan sát transport thực tế, log SMTP relay, API của provider hoặc một cơ chế instrumentation có hỗ trợ cụ thể. Không giả định rằng có thể lấy queue ID trực tiếp từ `MimeMessage.getMessageID()`: hai định danh này khác nhau.

## 4. Phân loại các mốc để xác định mức độ chắc chắn

Có thể sử dụng bảng suy luận sau trong chẩn đoán:

| Dấu hiệu quan sát được | Kết luận có thể đưa ra | Mức độ chắc chắn |
| --- | --- | --- |
| Không kết nối được TCP tới SMTP | Relay đó chưa thể nhận submission qua lần thử này | Cao, nếu không có đường gửi song song |
| TLS handshake thất bại trước MAIL FROM | Không hoàn tất SMTP submission ở connection này | Cao |
| SMTP AUTH bị từ chối trước DATA | Chưa submit message ở connection này | Cao |
| RCPT TO bị từ chối trước DATA | Recipient bị từ chối cho transaction đang xét | Cao đối với recipient ấy |
| Server trả `354` | Server cho phép client truyền DATA | Chưa chứng minh accepted |
| Client đã gọi writeTo/đã truyền bytes | Dữ liệu đã được ghi về phía socket/client | Không đủ để chứng minh server xử lý |
| Server trả `4xx/5xx` sau DATA | Server báo không chấp nhận submission đó | Cao theo phản hồi hiện có |
| Server trả `2xx` sau DATA | SMTP hop đã chấp nhận message | Cao |
| Client timeout khi chờ final reply sau DATA | Server có thể đã nhận hoặc chưa | **Không xác định** |
| `JavaMailSender.send` trả về không exception | Thư viện coi thao tác gửi thành công theo hợp đồng và chế độ recipient | Bằng chứng ứng dụng, cần xem partial-send |
| Email xuất hiện trong Inbox | Mailbox đã nhận một bản email | Cao cho email đó, nhưng chưa chắc khớp job nếu thiếu correlation |
| Không thấy email trong Inbox | Không biết đã được relay nhận chưa | Không thể kết luận |

Bất cứ khi nào không có trace SMTP và server-side logs, phải chấp nhận rằng một số tình huống không thể xác định tuyệt đối bằng thông tin phía client.

## 5. Hiểu kết quả trả về của JavaMailSender

Trong Spring Framework Mail, API thường dùng:

~~~java
MimeMessage message = mailSender.createMimeMessage();

// Dùng MimeMessageHelper để thiết lập From/To/Subject/Text.
mailSender.send(message);
~~~

`JavaMailSender.send(...)` là một lời gọi đồng bộ đối với thao tác submission ở tầng JavaMail. Nếu method kết thúc bình thường, ứng dụng thường có thể ghi nhận `SUBMITTED` theo hợp đồng của thư viện: transport đã hoàn tất thao tác gửi cho recipient tương ứng với cấu hình. Tuy nhiên, nó không trả một delivery receipt chứng minh message đã đến mailbox cuối.

Nếu method ném exception, phải đọc **loại exception và nguyên nhân** trước khi kết luận rằng không có recipient nào được server chấp nhận.

### Không nên dùng boolean sent đơn giản

Ví dụ đơn giản này dễ đánh đồng quá nhiều trạng thái:

~~~java
try {
    mailSender.send(message);
    notification.setSent(true);
} catch (Exception exception) {
    notification.setSent(false);
}
~~~

Trong hệ thống có retry hoặc nhiều recipient, flag `sent` không đủ mô tả sự cố. Có thể dùng những trạng thái rõ hơn:

~~~java
public enum MailSubmissionStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    REJECTED,
    AMBIGUOUS,
    FAILED
}
~~~

Delivery status `DELIVERED` và `BOUNCED` nên được theo dõi riêng nếu provider có sự kiện giao thư. Không đặt `DELIVERED` ngay sau khi gọi `send(...)` thành công.

## 6. Đọc exception của Spring Mail

Một số loại exception thường gặp gồm:

| Exception | Ý nghĩa tổng quát | Điều cần kiểm tra |
| --- | --- | --- |
| `MailAuthenticationException` | Xác thực mail server thất bại | Credential, auth mechanism, TLS, account policy |
| `MailPreparationException` | Chuẩn bị nội dung/email có lỗi | Địa chỉ, encoding, MIME resource, attachment |
| `MailSendException` | Quá trình gửi gặp lỗi | Failed messages, nested causes, SMTP phase |
| `MailParseException` | Lỗi parsing địa chỉ hoặc dữ liệu mail | Dữ liệu đầu vào, format |
| `MailException` | Base runtime exception của Spring Mail | Không đủ để tự phân loại transient/permanent |

Lỗi cụ thể phụ thuộc JavaMail provider, giai đoạn transport và cách Spring wrap các `MessagingException` của Jakarta Mail. Một exception `MailSendException` không có nghĩa chắc chắn mọi message trong batch đều thất bại.

### Ví dụ xử lý MailSendException

~~~java
import java.util.Map;
import org.springframework.mail.MailSendException;

try {
    mailSender.send(messages);
} catch (MailSendException exception) {

    Map<Object, Exception> failed =
        exception.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        // Ghi log an toàn ID ứng dụng và loại lỗi,
        // tránh in raw MIME/recipient lên log.
        log.warn("Mail submission failed: type={}",
            cause.getClass().getSimpleName());
    }

    throw exception;
}
~~~

Khi gọi send nhiều message trong một batch, `getFailedMessages()` có thể cung cấp mapping những message không gửi được với exception tương ứng. Phải đối chiếu với ID thông báo của ứng dụng. Đừng lấy một exception tổng quát rồi đánh dấu cả batch là chưa gửi; một số message khác có thể đã được submit.

Ở mức từng message, vẫn có thể có tình huống lỗi sau khi một số recipient được chấp nhận hoặc kết quả không rõ. Vì vậy, cần xem nested exception và transport semantics.

## 7. Jakarta Mail SendFailedException và recipient-level state

Jakarta Mail có `SendFailedException`, có thể cung cấp các nhóm địa chỉ:

- `getValidSentAddresses()`: các địa chỉ được transport ghi nhận đã gửi thành công theo hành vi gửi hiện tại.
- `getValidUnsentAddresses()`: địa chỉ hợp lệ nhưng chưa được gửi thành công.
- `getInvalidAddresses()`: các địa chỉ bị xem là không hợp lệ.

Một số SMTP implementation có các exception cụ thể hơn cho địa chỉ hoặc lệnh SMTP. Tên package có thể khác nhau theo dòng thư viện: môi trường cũ dùng JavaMail, môi trường mới dùng Jakarta Mail/Angus Mail. Đừng hard-code cách xử lý chỉ dựa vào một implementation class nếu ứng dụng hỗ trợ nhiều transport.

Các tập địa chỉ ở trên là thông tin tại tầng submission, **không phải bằng chứng mailbox đã nhận được mail**.

### Partial success với nhiều recipients

Giả sử message có To/Cc/Bcc tổng cộng ba envelope recipients:

~~~text
MAIL FROM:<no-reply@example.com>       -> 250
RCPT TO:<alice@example.net>            -> 250
RCPT TO:<bob@example.org>              -> 550
RCPT TO:<carol@example.edu>            -> 250
~~~

Hành vi tiếp theo phụ thuộc cấu hình SMTP transport. Một số chế độ từ chối gửi toàn bộ message nếu một recipient không hợp lệ; chế độ cho phép partial send có thể tiếp tục gửi DATA cho những recipient được chấp nhận.

Với JavaMail SMTP provider, thuộc tính như `mail.smtp.sendpartial` có thể ảnh hưởng hành vi này. Không bật partial send chỉ để “giảm lỗi” mà chưa xem yêu cầu nghiệp vụ, vì khi đó kết quả gửi của từng recipient cần được ghi nhận riêng.

Nếu một message có nhiều recipient, câu hỏi “đã gửi chưa?” có thể có câu trả lời **khác nhau theo recipient**. Khi hệ thống yêu cầu đối soát chi tiết, nên lưu per-recipient status hoặc gửi các message độc lập để giảm độ phức tạp.

### Không nhầm header To/Cc/Bcc với SMTP envelope

Trong email có hai lớp thông tin:

- **Header** `To`, `Cc`, `From`: nội dung MIME mà người nhận thấy.
- **SMTP envelope** `MAIL FROM` và `RCPT TO`: địa chỉ dùng cho việc vận chuyển.

`Bcc` thường không xuất hiện trong header được phân phối, nhưng recipient Bcc vẫn được cung cấp qua SMTP envelope. Khi chẩn đoán, kiểm tra envelope recipient đã được chấp nhận thay vì chỉ xem header `To`.

## 8. Timeout ở giai đoạn nào thì kết quả không rõ?

Timeout có thể xảy ra ở nhiều điểm. Mức độ chắc chắn thay đổi theo thời điểm.

### Connection timeout

Ứng dụng không thiết lập được kết nối tới server. Nếu không có retry/failover khác đã chạy, **lần thử này chưa gửi dữ liệu tới SMTP server**.

~~~text
Client ----- connect ----X---- SMTP server
           timeout
~~~

Lúc này thường có thể retry nếu nguyên nhân có vẻ tạm thời, vẫn nằm trong quota/deadline.

### Timeout trong TLS hoặc AUTH

Nếu TLS handshake hoặc xác thực thất bại trước khi gửi envelope/DATA, kết nối đó chưa hoàn tất submission. Nhưng lỗi cấu hình không nên được retry dày đặc. Cần sửa credential, certificate, STARTTLS mode hoặc policy provider.

### Timeout trong MAIL FROM hoặc RCPT TO

Chưa tới bước hoàn tất DATA nên chưa có bằng chứng server đã chấp nhận toàn bộ message qua connection đó. Nếu có server response từ chối recipient, cần ghi nhận rõ. Đừng suy ra success từ việc có `250` ở MAIL FROM.

### Timeout khi đang truyền DATA

Có thể server chưa nhận đủ nội dung; cũng có thể thư viện đã truyền gần hoặc toàn bộ nội dung nhưng client không biết server đã xử lý đến đâu. Tùy điểm lỗi, kết luận có thể không chắc chắn.

### Timeout sau khi gửi dấu kết thúc DATA

Đây là khoảng không chắc chắn quan trọng nhất:

~~~text
Client                              Server
  |                                    |
  |--- MIME bytes and DATA end ------->|
  |                                    | accepted & queued?
  |<--------- response lost --------- X|
  |
  +--> timeout / socket error
~~~

Nếu server đã ghi message vào queue rồi phản hồi bị mất, phía client có thể báo lỗi dù message thực tế đã được tiếp nhận. Retry tự động có thể gửi bản thứ hai.

**Không có cách suy luận đáng tin cậy từ một timeout thuần túy rằng message chắc chắn chưa tới server.** Muốn xác định rõ hơn cần SMTP relay logs, provider query hoặc correlation ID.

## 9. SMTP debug log có thể cung cấp bằng chứng gì?

Jakarta Mail có chế độ debug ghi lại diễn tiến phiên SMTP. Trong Spring Boot, có thể bật property JavaMail tương ứng tại môi trường debug:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${MAIL_USERNAME}
    password: ${MAIL_PASSWORD}
    properties:
      mail:
        debug: true
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Đây là ví dụ phục vụ chẩn đoán có kiểm soát. Cách ghi log thực tế phụ thuộc version Jakarta Mail/Angus Mail, Session debug output và cấu hình logging. Cần kiểm tra đầu ra trong môi trường an toàn trước khi dùng.

### Cẩn thận với dữ liệu nhạy cảm

**Không bật SMTP protocol debug thường trực trên production nếu chưa kiểm soát rủi ro.** Transcript có thể chứa:

- Email người nhận và envelope sender.
- Hostname/domain.
- Nội dung/metadata MIME.
- Thông tin AUTH hoặc dữ liệu nhạy cảm tùy phiên bản/cấu hình.
- Message ID, queue ID hoặc nội dung phục vụ đối chiếu.

Chỉ bật trong thời gian ngắn, trên một luồng gửi kiểm thử hoặc một tài khoản test, hạn chế người xem log và có quy trình tắt/retention. Không log password/token và không copy raw transcript có PII vào ticket công khai.

### Cách đọc một SMTP transcript

Thay vì tìm mọi dòng `250`, hãy xác định lần lượt:

1. Có kết nối tới đúng host/port không?
2. Có STARTTLS/auth thành công không?
3. Server trả gì cho `MAIL FROM`?
4. Server trả gì cho từng `RCPT TO`?
5. Có lệnh `DATA` và phản hồi `354` không?
6. Client có gửi kết thúc DATA không?
7. Server có phản hồi `2xx` **sau** kết thúc DATA không?
8. Có queue ID hoặc transaction ID của provider không?
9. Có lỗi connection/timeout sau bước nào?
10. Gửi có nhiều recipient, partial send hoặc nhiều message trong batch không?

Nếu không thấy phản hồi cuối DATA vì log bị cắt hoặc connection mất, không đủ căn cứ để đánh dấu `NOT_SENT` tuyệt đối.

## 10. Đặt timeout để tránh treo vô thời hạn

SMTP có thể chờ kết nối, đọc phản hồi và ghi dữ liệu. Trong JavaMail SMTP provider, các property thường gặp:

~~~properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
~~~

Các giá trị thường tính bằng mili giây:

| Property | Điều khiển |
| --- | --- |
| `mail.smtp.connectiontimeout` | Thời gian chờ thiết lập kết nối |
| `mail.smtp.timeout` | Thời gian chờ đọc dữ liệu/phản hồi từ server |
| `mail.smtp.writetimeout` | Thời gian chờ ghi ra socket |

Nếu dùng protocol `smtps`, prefix tương ứng có thể là `mail.smtps.*` theo provider. Không nhầm timeout network với “thời gian server chắc chắn chưa nhận mail”.

Một read timeout khi chờ final DATA reply có thể tạo trạng thái AMBIGUOUS. Rút timeout quá ngắn có thể tăng tỷ lệ lỗi và gửi trùng khi retry. Đặt timeout phải dựa trên thời gian SMTP thực tế, kích thước message và SLA.

## 11. Correlation ID: liên kết từ ứng dụng đến SMTP

Nếu không có ID ổn định, việc đối chiếu một lỗi JavaMail với log của relay rất khó, đặc biệt khi nhiều message có cùng subject và recipient.

Nên có ít nhất:

- **Notification ID**: ID nội bộ của yêu cầu gửi.
- **Attempt ID**: ID riêng cho mỗi lần thử.
- **Message-ID header**: ID của message theo RFC, hữu ích để correlation.
- **Provider queue/message ID**: ID do SMTP relay/ESP trả về nếu có.
- **Recipient/envelope metadata**: chỉ ghi ở mức được phép theo chính sách bảo mật.
- **Timestamp UTC**: mốc gửi, nhận phản hồi và cập nhật trạng thái.

Các ID này có mục đích khác nhau và không nên coi chúng là một.

### Ví dụ ghi header correlation tùy chỉnh

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendNotification(
        String notificationId,
        String recipient,
        String text) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Xác nhận thông báo");
    helper.setText(text, false);

    message.setHeader(
        "X-App-Notification-ID",
        notificationId
    );

    mailSender.send(message);
}
~~~

Header tùy chỉnh giúp đối chiếu raw MIME khi hệ thống nhận giữ lại header. Provider có thể chỉnh sửa hoặc loại bỏ header, nên không xem đó là bằng chứng duy nhất.

### Message-ID không phải queue ID

Header `Message-ID` là một định danh của email trong nội dung RFC 5322. Provider queue ID là định danh nội bộ tại một SMTP hop hoặc ESP. Chúng có thể khác nhau hoàn toàn.

`MimeMessage.getMessageID()` đọc Message-ID header mà message đang mang. Khi gọi `saveChanges()` hoặc `JavaMailSender.send(...)`, thư viện có thể tạo/cập nhật các header quản lý, bao gồm Message-ID tùy implementation. Nếu cần ghi nhận giá trị thực tế, hãy quan sát message đã được chuẩn bị/gửi theo implementation và đối chiếu trên relay. Không tự giả định Message-ID tạo trước lời gọi send sẽ luôn giữ nguyên.

Message-ID **không phải một idempotency key được SMTP bảo đảm**. Hai message gửi lại với cùng Message-ID vẫn có thể được giao hai lần.

## 12. Ghi trạng thái có ý nghĩa trong ứng dụng

Đừng chỉ có `sent = true/false`. Một mô hình rõ ràng hơn:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--- send() returns normally ---> SUBMITTED
   |
   +--- definitive rejection ------> REJECTED / FAILED
   |
   +--- uncertain result ----------> AMBIGUOUS
   |
   +--- transient before DATA -----> RETRY_WAIT
   |
   +--- permanent preparation -----> FAILED

SUBMITTED
   |
   +--- provider event -----------> DELIVERED / BOUNCED / DEFERRED
~~~

Nên tách **submission state** khỏi **delivery state** nếu ứng dụng có nhu cầu theo dõi cả hai. Một record có thể SUBMITTED và sau đó BOUNCED; điều này không mâu thuẫn.

Ví dụ model:

~~~java
public record MailSubmissionRecord(
    String notificationId,
    String attemptId,
    SubmissionStatus status,
    Instant attemptedAt,
    Instant acceptedAt,
    String providerMessageId,
    String failureCode
) {}

public enum SubmissionStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    REJECTED,
    AMBIGUOUS,
    RETRY_WAIT,
    FAILED
}
~~~

Không nhất thiết phải lưu mọi thông tin cho email best-effort, nhưng với transactional mail, những trạng thái này giúp operator biết thực sự còn cần retry hay đã phải đối soát.

## 13. Minh họa logging quanh JavaMailSender

Một adapter có thể ghi nhận mốc bắt đầu, kết thúc và exception. Ví dụ:

~~~java
@Service
public class MailSubmissionService {

    private final JavaMailSender mailSender;
    private final MailAttemptRecorder recorder;

    public MailSubmissionService(
            JavaMailSender mailSender,
            MailAttemptRecorder recorder) {
        this.mailSender = mailSender;
        this.recorder = recorder;
    }

    public void submit(
            String notificationId,
            MimeMessage message) {

        String attemptId = UUID.randomUUID().toString();
        Instant startedAt = Instant.now();

        recorder.markStarted(
            notificationId, attemptId, startedAt);

        try {
            mailSender.send(message);

            recorder.markSubmitted(
                notificationId, attemptId, Instant.now());

        } catch (MailException exception) {
            recorder.recordFailure(
                notificationId,
                attemptId,
                exception.getClass().getSimpleName(),
                Instant.now()
            );

            throw exception;
        }
    }
}
~~~

`MailAttemptRecorder` là interface do ứng dụng tự định nghĩa, không phải API của Spring Mail. Ví dụ dùng exception class để ghi mốc kỹ thuật; production cần thêm classifier để phân biệt definite rejection với ambiguous outcome.

**Quan trọng:** log từ wrapper chỉ nói rằng `send(...)` đã trả thành công hay exception. Nó không tự chứng minh SMTP DATA final reply nếu cần phân tích lỗi có độ chính xác cao. Khi cần, kết hợp log ứng dụng với transcript SMTP và provider-side trace.

Không ghi full `MimeMessage`, email body, secret hay attachment vào log chỉ để chẩn đoán.

## 14. Khi @Async trả về, email đã đến server chưa?

Không nhất thiết. Ví dụ:

~~~java
@Async("mailTaskExecutor")
public void sendAsync(OutgoingMail mail) {
    mailDelivery.send(mail);
}
~~~

Khi caller invoke `sendAsync`, task có thể mới được đưa vào executor. Lời gọi từ caller kết thúc không có nghĩa `mailDelivery.send(...)` đã thực thi hoặc SMTP đã nhận message.

~~~text
HTTP request
    |
    +--> submit async task
    |
    +--> HTTP response 202 Accepted
                 |
                 v
            Thread pool queue
                 |
                 v
            Worker thread
                 |
                 v
            JavaMailSender.send
                 |
                 v
            SMTP DATA response
~~~

Nếu trả HTTP `202 Accepted`, phải hiểu đó là application đã nhận yêu cầu xử lý, không phải SMTP accepted. Nếu task chỉ nằm trong in-memory queue, process crash có thể làm mất job.

Với email quan trọng, hãy lưu yêu cầu gửi trong outbox/broker bền vững rồi sử dụng worker để thực thi. Như vậy trạng thái `PENDING` có thể được khôi phục sau restart.

## 15. Khi nào retry là an toàn?

Trước retry, xác định có bằng chứng message đã được SMTP hop chấp nhận chưa.

| Tình huống | Retry tự động? | Lý do |
| --- | --- | --- |
| Không kết nối được, chưa giao tiếp SMTP | Có thể, nếu lỗi tạm thời | Chưa có submission qua lần thử này |
| Xác thực thất bại do credential sai | Không, cần sửa cấu hình | Retry lặp nguyên lỗi |
| Server trả 4xx trước DATA | Có thể theo policy | Chưa có accepted message qua transaction này |
| Server trả 4xx sau DATA | Có thể theo chính sách/provider | Server báo không nhận lần submit đó |
| Server trả 5xx sau DATA | Thường không, trừ khi sửa nội dung/policy | Rejection vĩnh viễn hoặc theo policy |
| Có final 250 sau DATA | Không retry cùng submission | Server đã nhận |
| Không nhận được final DATA response | Không thể khẳng định an toàn | Có nguy cơ message đã được nhận |
| `send` thành công nhưng sau đó có bounce | Không retry mù | Delivery failure cần xử lý riêng |

Một ứng dụng có thể quyết định retry cả kết quả AMBIGUOUS nếu thông báo ít nhạy cảm và chấp nhận được duplicate. Nhưng đó phải là chính sách nghiệp vụ có chủ đích, không phải kết luận kỹ thuật rằng message chưa được gửi.

### Vì sao cần outbox?

Outbox lưu yêu cầu gửi cùng transaction nghiệp vụ, giúp không mất job. Worker ghi attempt/status và retry lỗi tạm thời theo delay. Tuy nhiên, outbox không tạo exactly-once SMTP delivery:

~~~text
Worker gửi thành công
         |
         v
Server trả 250
         |
         v
Worker bị kill trước khi ghi SUBMITTED
         |
         v
Outbox vẫn PROCESSING
         |
         v
Lease hết hạn và worker retry
         |
         v
Có thể gửi trùng
~~~

Nếu provider API hỗ trợ idempotency key, dùng cùng key cho các lần thử. SMTP truyền thống không cung cấp idempotency guarantee chung; Message-ID tự nó không ngăn duplicate.

## 16. Đối chiếu với SMTP server hoặc provider

Khi bằng chứng phía client không đủ, cần chuyển sang nguồn dữ liệu phía server.

### SMTP relay do đội vận hành quản lý

Tìm mail log/queue bằng:

- Thời điểm gửi gần đúng, đồng bộ timezone/UTC.
- Envelope sender.
- Envelope recipient.
- Message-ID header nếu relay có log.
- Queue ID nếu có.
- Hostname ứng dụng hoặc authenticated sender.
- Notification ID/header tùy chỉnh nếu relay lưu lại.

Cần xác định **sự kiện acceptance** tại hop đầu, không chỉ nhìn một dòng kết nối thành công. Sau đó theo dõi queue ID trong log relay để biết message được chuyển tiếp, deferred hay bounced.

### Email Service Provider

Nếu dùng ESP có dashboard, event API hoặc webhook, đối chiếu:

- Provider message ID.
- Event type: accepted/processed, delivered, deferred, bounced, dropped, complained.
- Timestamp và recipient.
- API/SMTP submission request tương ứng.
- Suppression list, quota và policy rejection.

Các tên event khác nhau theo provider. Không đồng nhất một event `processed` hoặc `accepted` với `delivered` nếu tài liệu provider không nói như vậy.

### Mailbox của người nhận

Nếu người dùng báo không thấy thư, cần kiểm tra thêm spam/junk, quarantine, rule, forwarding và mailbox policy. Việc người dùng không tìm thấy email không chứng minh server gửi ban đầu chưa nhận submission.

## 17. DSN, bounce và delivery event

SMTP có các cơ chế liên quan đến Delivery Status Notification (DSN), còn ESP thường cung cấp webhook sự kiện. Chúng giúp biết điều gì xảy ra **sau khi message được chấp nhận**.

Ví dụ:

~~~text
Application
    |
    v
SMTP relay ---- 250 accepted ----> Application: SUBMITTED
    |
    +--> Delivery success event ---> DELIVERED
    |
    +--> Temporary downstream error -> DEFERRED
    |
    +--> Permanent downstream error -> BOUNCED
~~~

Một bounce có thể đến vài phút hoặc vài giờ sau. Trạng thái SUBMITTED vẫn đúng tại thời điểm đầu; delivery state chuyển sang BOUNCED khi có bằng chứng mới.

DSN không có mặt trên mọi luồng mail và không bảo đảm mọi downstream provider gửi thông tin đầy đủ. Email client mở thư hoặc download tracking pixel cũng không phải bằng chứng chắc chắn người thật đã đọc, do proxy, cache, chặn ảnh và các tính năng bảo vệ quyền riêng tư.

## 18. Nhiều SMTP hop làm chẩn đoán phức tạp hơn

Email thường không đi thẳng từ ứng dụng tới Inbox:

~~~text
Spring application
       |
       v
SMTP submission relay
       |
       v
Outbound filtering / policy
       |
       v
Destination MX
       |
       v
Mailbox storage
       |
       v
Recipient client
~~~

Final `250` sau DATA chỉ xác nhận hop mà client đang kết nối. Relay có thể chấp nhận rồi đưa message vào queue để kiểm tra thêm. Sau đó message có thể:

- Được chuyển tiếp thành công.
- Bị giữ để quét/quarantine.
- Bị deferred và thử lại ở downstream.
- Bounce vì hộp thư không tồn tại/quota.
- Bị policy/suppression của provider chặn.

Không được lấy response đầu tiên làm bằng chứng hoàn tất mọi hop. Nếu cần SLA giao thư, nên theo dõi provider delivery events và phân loại trạng thái downstream.

## 19. Ví dụ sơ đồ ra quyết định khi gặp lỗi gửi mail

~~~text
JavaMailSender.send(...) gọi xong?
                |
         +------+------+
         |             |
       Thành công      Exception/timeout
         |             |
         v             v
   Mark SUBMITTED    Đọc nested cause,
   (theo API)        SMTP phase, logs
         |             |
         |       +-----+----------------------+
         |       |            |               |
         |    Trước DATA  Server báo lỗi   Sau DATA nhưng
         |       |        final rõ ràng    mất response
         |       |            |               |
         |       v            v               v
         |   Chưa submit   4xx/5xx classify  AMBIGUOUS
         |       |            |               |
         |       v            v               v
         |  Retry/sửa lỗi  Retry hoặc dừng  Provider trace/
         |                                     reconciliation
         |
         v
  Theo dõi delivery riêng
         |
       +---+
       |   |
    Delivered  Bounced/Deferred
~~~

Điểm đặc biệt: **nếu thiếu final response, kết luận đúng có thể là “không biết”, không phải “chưa gửi”**. Chấp nhận trạng thái AMBIGUOUS giúp hệ thống không vô tình nói quá mức bằng chứng.

## 20. Ví dụ chẩn đoán các tình huống cụ thể

### Tình huống 1: Connection refused

Log ghi `Connection refused` khi mở socket tới SMTP host:port. Không có phiên SMTP cho lần thử này. Nếu không có failover hoặc retry song song, message chưa được submit qua connection đó.

Hướng xử lý: xác minh DNS, port, firewall, network, SMTP availability và cấu hình TLS. Nếu lỗi tạm thời, retry có backoff; nếu cấu hình sai, sửa trước khi retry.

### Tình huống 2: Authentication failed

Server trả lỗi AUTH. Không có bằng chứng đã tới MAIL FROM/RCPT/DATA trong phiên đó. Đây thường là lỗi credential/policy, không phù hợp retry liên tục.

Hướng xử lý: kiểm tra credential, application password/OAuth nếu provider yêu cầu, STARTTLS và account permissions. Không log credential.

### Tình huống 3: Server chấp nhận recipient nhưng DATA bị từ chối

~~~text
S: 250 Recipient OK
C: DATA
S: 354 Continue
C: ...message...
C: .
S: 552 Message size exceeds policy
~~~

Server đã chấp nhận recipient nhưng **không chấp nhận toàn bộ message**. Cần giảm kích thước MIME, thay attachment bằng link hoặc điều chỉnh policy hợp lệ. Retry lại cùng message thường không giúp.

### Tình huống 4: Final DATA reply bị mất

~~~text
C: DATA
S: 354 Continue
C: ...message...
C: .
[read timeout, không có final reply]
~~~

Không thể khẳng định message chưa được nhận. Dùng queue/provider logs với correlation ID để đối chiếu. Nếu không thể đối chiếu, áp dụng policy về duplicate và đánh dấu AMBIGUOUS.

### Tình huống 5: Server trả final 250 nhưng người dùng không thấy email

Submission thành công tại relay đầu. Cần kiểm tra downstream provider events, spam/quarantine, mailbox rule, bounce hoặc defer. Không retry nguyên message chỉ vì người dùng chưa thấy email sau một vài giây.

### Tình huống 6: Batch có một message lỗi

`JavaMailSender.send(message1, message2, message3)` có thể báo lỗi liên quan một số message trong batch. Không đánh dấu toàn bộ ba message là NOT_SENT nếu không có bằng chứng; dùng `MailSendException.getFailedMessages()` và trạng thái từng notification để đối chiếu.

### Tình huống 7: Một recipient bị từ chối, những recipient khác hợp lệ

Cần kiểm tra `mail.smtp.sendpartial`, `SendFailedException` và SMTP transcript. Một số recipient có thể đã nhận submission theo transport, số khác không. Không lưu một flag chung cho cả nhóm nếu hệ thống cần đối soát chính xác.

### Tình huống 8: @Async caller báo thành công

Method gọi `@Async` return bình thường có thể chỉ báo task được nhận bởi executor. Phải theo dõi kết quả worker, không suy ra SMTP accepted từ HTTP response. Nếu hệ thống cần độ tin cậy, dùng outbox thay cho queue thuần trong bộ nhớ.

## 21. Kiểm thử kết quả submission bằng SMTP test server

Để hiểu cách ứng dụng phản ứng, nên dùng SMTP test server như GreenMail hoặc MailHog/Mailpit trong môi trường test. Với test thành công, kiểm tra server đã nhận raw message có đúng Message-ID/header, recipient và nội dung.

Các tình huống nên mô phỏng:

1. TCP connection failure trước SMTP handshake.
2. AUTH failure.
3. Recipient rejection tại RCPT TO.
4. DATA rejection sau khi truyền nội dung.
5. Final `250` sau DATA.
6. Disconnect/timeout trước và sau DATA terminator.
7. Gửi nhiều recipient với partial-send policy.
8. Batch send có success và failure trộn lẫn.
9. Worker crash sau khi relay accepted nhưng trước khi database đánh dấu SUBMITTED.
10. Provider event bounce đến sau submission.

Không phải test server nào cũng hỗ trợ tiêm lỗi ở mọi SMTP phase. Với tình huống mất response cuối DATA, có thể cần một SMTP stub/proxy chuyên dụng có khả năng chủ động đóng connection ở đúng thời điểm.

### Test đơn giản với fake mail sender

Unit test có thể xác nhận logic ứng dụng khi `send` trả bình thường hoặc ném exception:

~~~java
@Test
void normalReturnMarksSubmissionAsSubmitted() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MailAttemptRecorder recorder = mock(MailAttemptRecorder.class);

    // Stub createMimeMessage hoặc dùng sender thật với test Session.
    // Gọi service submit với một MimeMessage hợp lệ.
    // Assert recorder.markSubmitted(...) được gọi.

    // Đây là unit test application semantics,
    // không chứng minh SMTP server thực sự nhận message.
}
~~~

Mock test chỉ xác nhận cách code xử lý kết quả từ abstraction. Muốn biết SMTP conversation, cần integration test qua server/proxy thật hoặc công cụ giả lập có khả năng kiểm soát giao thức.

## 22. Sổ tay chẩn đoán tại production

Khi có ticket “không nhận được email”, có thể theo trình tự:

1. **Xác định notification ID** và thời điểm gửi dự kiến.
2. **Kiểm tra job/outbox**: PENDING, PROCESSING, RETRY_WAIT, SUBMITTED, AMBIGUOUS hay FAILED?
3. **Tìm attempt log** theo attempt ID, host/provider, timestamp; xác nhận worker đã chạy.
4. **Nếu có exception**, phân loại network, TLS/auth, recipient, DATA, timeout và nested causes.
5. **Kiểm tra bằng chứng server acceptance**: final `2xx` sau DATA, queue ID hoặc log provider.
6. **Nếu kết quả không rõ**, không tự kết luận NOT_SENT; đánh dấu AMBIGUOUS và đối soát.
7. **Nếu SUBMITTED**, tra provider delivery/bounce/defer/suppression event.
8. **Nếu provider báo DELIVERED**, kiểm tra mailbox, spam, quarantine và forwarding cùng phía người nhận.
9. **Quyết định retry** dựa trên loại lỗi, deadline và duplicate risk.
10. **Cập nhật trạng thái và ghi nhận kết quả điều tra** bằng ID, không lưu nội dung nhạy cảm không cần thiết.

Có thể dùng mẫu record:

~~~json
{
  "notificationId": "mail-2026-00031",
  "attemptId": "attempt-4",
  "status": "AMBIGUOUS",
  "smtpPhase": "AFTER_DATA",
  "provider": "primary-relay",
  "startedAt": "2026-11-12T10:00:00Z",
  "lastObservedReply": "354",
  "finalDataReplyObserved": false,
  "providerQueueId": null,
  "reason": "socket read timeout after DATA"
}
~~~

Các trường ở đây là **schema minh họa**. `JavaMailSender` không tự điền `smtpPhase` hay `providerQueueId`; cần nguồn dữ liệu transport/provider phù hợp. Không tạo giá trị giả để lấp những trường không có bằng chứng.

## 23. Quan sát hệ thống để tránh mất dấu

Một hệ thống mail nên phân biệt metrics theo tầng:

| Metric | Điều quan sát |
| --- | --- |
| Requests accepted | Application nhận yêu cầu gửi |
| Jobs queued | Công việc được lưu/đưa vào queue |
| Submission attempts | Số lần thực sự gọi sender |
| Submission success | Transport báo thành công |
| Submission rejected | Transport/server báo lỗi xác định |
| Submission ambiguous | Kết quả không rõ |
| Provider delivered | Sự kiện delivery có bằng chứng |
| Provider bounced | Sự kiện bounce |
| Queue oldest age | Độ trễ của thông báo chưa submit |
| Retry exhausted | Job hết policy thử lại |

Nên có alert cho SMTP authentication failures, timeout sau DATA, provider throttling, nhiều record AMBIGUOUS hoặc PENDING quá lâu. Một tỷ lệ `send` success cao không bảo đảm delivery rate cao; hai chuỗi metrics cần được theo dõi riêng.

Tránh gắn recipient address hoặc notification ID làm metric label có cardinality cao. Log có thể chứa internal ID để đối chiếu, nhưng metric labels nên dùng category, provider và failure class có số lượng giá trị hữu hạn.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Có dòng 250 nghĩa là đã gửi” | Có thể là 250 của EHLO/MAIL FROM/RCPT | Xác định final 2xx sau DATA |
| “354 nghĩa là server nhận message” | 354 chỉ cho phép bắt đầu DATA | Chờ kết quả sau dấu kết thúc DATA |
| “Client đã write bytes nên server đã nhận” | Socket write không phải server acceptance | Cần final reply hoặc server log |
| “send() ném exception nên chắc chắn chưa gửi” | Có thể partial/ambiguous | Đọc cause và SMTP phase |
| “send() thành công nên đã tới Inbox” | Chỉ xác nhận submission | Theo dõi delivery events |
| “Không thấy email nghĩa là SMTP chưa nhận” | Có thể bị spam, defer, bounce | Điều tra downstream |
| “Message-ID là queue ID” | Hai định danh phục vụ mục đích khác nhau | Lưu riêng các ID |
| “Message-ID tự chống gửi trùng” | SMTP không bảo đảm dedup | Provider idempotency nếu hỗ trợ |
| “HTTP 202 nghĩa là email đã gửi” | Có thể chỉ nhận job async | Theo dõi worker/submission state |
| “Retry mọi timeout đều an toàn” | Timeout sau DATA có thể đã được nhận | Trạng thái AMBIGUOUS/reconciliation |
| “Một recipient sai thì mọi recipient chưa gửi” | Partial send có thể đã xảy ra | Xem recipient-level diagnostics |
| “Mail debug luôn vô hại” | Có thể lộ credential/PII/MIME | Debug giới hạn, sanitize và tắt |
| “Gửi thành công rồi xóa outbox ngay” | Mất khả năng đối soát/reconciliation | Retention có kiểm soát |

## 25. Ghi nhớ

Để xác định message đã được gửi đến server hay chưa, cần dựa vào **bằng chứng ở đúng bước SMTP**:

- `EHLO`, `AUTH`, `MAIL FROM` và `RCPT TO` thành công chưa chứng minh toàn bộ message được server chấp nhận.
- `354` cho phép truyền DATA nhưng không phải kết quả submission.
- **Final 2xx sau dấu kết thúc DATA** là bằng chứng rõ nhất rằng SMTP hop hiện tại đã chấp nhận message.
- Nếu client timeout trước khi thấy final DATA reply, kết quả có thể **không xác định**.
- `JavaMailSender.send(...)` kết thúc bình thường thường tương ứng submission thành công theo thư viện, nhưng không chứng minh delivered.
- Khi có `MailSendException`, cần xem failed messages, nested cause, SMTP phase và recipient-level outcome.
- Với nhiều recipient hoặc partial send, một message có thể có kết quả khác nhau giữa các recipient.
- SMTP envelope và MIME headers là hai lớp khác nhau; Bcc cũng là recipient trên envelope.
- Message-ID, notification ID, attempt ID và provider queue ID nên được lưu riêng để correlation.
- Debug log hữu ích khi tra SMTP phase nhưng phải bảo vệ credential, PII và nội dung thư.
- Sau submission, delivery/bounce/defer là vấn đề downstream và cần theo dõi qua provider events.
- Async queue hoặc outbox PENDING không có nghĩa message đã tới SMTP server.
- Với timeout AMBIGUOUS, retry cần cân nhắc duplicate, provider reconciliation và idempotency.
- Không log “not sent” nếu bằng chứng duy nhất là một socket read timeout sau DATA.

**Quy tắc quan trọng nhất:** Nếu có final success reply của SMTP sau DATA, có cơ sở kết luận server đó đã nhận submission. Nếu kết nối mất trước phản hồi cuối, kết luận chính xác có thể chỉ là “chưa biết”. Thiết kế ứng dụng có trạng thái AMBIGUOUS, correlation ID và quy trình đối soát sẽ giúp tránh vừa mất email vừa gửi trùng khi gặp sự cố mạng.
