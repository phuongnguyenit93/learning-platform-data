# MailSendException và các failed message

Trong ứng dụng Spring Framework Mail, một lời gọi `JavaMailSender.send(...)` có thể ném `MailSendException` khi quá trình gửi email qua mail transport gặp lỗi. Lỗi này đặc biệt đáng chú ý khi ứng dụng gửi **nhiều message trong một lần gọi**: một số message có thể đã được SMTP server chấp nhận trong khi message khác thất bại. Vì thế, chỉ nhìn thấy exception rồi kết luận “toàn bộ email chưa gửi” có thể dẫn tới việc gửi trùng.

Spring cung cấp `MailSendException.getFailedMessages()` để truy xuất những message được ghi nhận là gặp lỗi cùng exception tương ứng. Tuy nhiên, danh sách này cần được diễn giải theo **giai đoạn gửi, loại lỗi và thông tin trả về từ SMTP**; nó không phải danh sách các email chắc chắn chưa đến người nhận, cũng không phải bằng chứng rằng các message còn lại đã được giao tới Inbox.

Bài học tập trung vào cách đọc `MailSendException`, phân tích failed messages trong batch, truy tìm nguyên nhân gốc từ Jakarta Mail, phân biệt lỗi theo message và theo recipient, xây dựng log chẩn đoán an toàn và quyết định retry có kiểm soát.

## 1. MailSendException nằm ở đâu trong Spring Mail?

Spring Mail có một số nhóm exception thường gặp:

| Exception | Tình huống điển hình | Hướng điều tra |
| --- | --- | --- |
| `MailException` | Lớp cha của các exception Spring Mail | Xác định subtype cụ thể |
| `MailAuthenticationException` | SMTP authentication không thành công | Credential, chính sách SMTP AUTH, cơ chế xác thực |
| `MailParseException` | Dữ liệu mail không parse/chuyển đổi hợp lệ theo luồng sử dụng | Địa chỉ, định dạng dữ liệu |
| `MailPreparationException` | Lỗi khi chuẩn bị MIME message, ví dụ trong `MimeMessagePreparator` | Template, attachment resource, Jakarta Mail |
| `MailSendException` | Transport không gửi được hoặc có một hay nhiều message thất bại | Connection, SMTP response, failed messages |

Các exception Spring Mail thường là unchecked. Vì vậy, code gọi `send(...)` không cần khai báo `throws MailSendException`. Điều đó không có nghĩa là có thể bỏ qua lỗi.

### MailSendException khác MessagingException

`MailSendException` thuộc Spring Mail. `jakarta.mail.MessagingException` thuộc Jakarta Mail và thường xuất hiện khi thao tác trên MIME message hoặc trong tầng transport.

Ví dụ:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.MimeMessageHelper;

// Khi dựng MIME:
helper.setTo(recipient);      // Có thể ném MessagingException.
helper.setSubject(subject);   // Có thể ném MessagingException.

// Khi giao cho sender:
mailSender.send(message);     // Có thể ném MailException,
                              // trong đó có MailSendException.
```

Nếu `MimeMessageHelper` không xây dựng được MIME message, lỗi có thể phát sinh **trước** khi gửi SMTP. Nếu thông qua `MimeMessagePreparator`, Spring có thể bọc một số lỗi chuẩn bị vào `MailPreparationException`. Không nên gom mọi lỗi MIME và SMTP vào cùng loại “đường truyền chập chờn”.

## 2. Khi nào MailSendException thường xuất hiện?

Một số tình huống:

1. Không kết nối được tới SMTP host hoặc port.
2. Mail server đóng kết nối hoặc xảy ra lỗi giao tiếp.
3. SMTP server từ chối sender, recipient hoặc nội dung message.
4. Một message trong batch bị transport báo lỗi, trong khi các message khác có thể đã được xử lý.
5. Thao tác kết thúc/đóng transport lỗi sau một chuỗi gửi.
6. Kết nối bị ngắt tại thời điểm kết quả của việc gửi chưa rõ.

Ví dụ một batch:

```text
JavaMailSender.send(M1, M2, M3, M4)
                 |
                 v
             SMTP transport
                 |
                 +-- M1: server chấp nhận
                 +-- M2: bị từ chối
                 +-- M3: server chấp nhận
                 +-- M4: lỗi I/O
                 |
                 v
       MailSendException
       failedMessages: M2 -> cause2
                       M4 -> cause4
```

Sơ đồ này minh họa khả năng một batch có kết quả không đồng nhất. Thực tế còn phụ thuộc lỗi xảy ra tại **bước kết nối chung** hay tại **từng message**, và ứng dụng có đủ thông tin xác nhận SMTP đã chấp nhận message hay không.

## 3. Các thành phần quan trọng của MailSendException

Hai API cần biết:

```java
Map<Object, Exception> failures = exception.getFailedMessages();
Exception[] causes = exception.getMessageExceptions();
```

Ngoài ra, exception có thông tin chung:

```java
String message = exception.getMessage();
Throwable cause = exception.getCause();
```

### getFailedMessages()

`getFailedMessages()` trả về `Map<Object, Exception>`. Mỗi entry liên kết một đối tượng message với lỗi mà Spring ghi nhận khi cố gửi nó:

- **Key:** message tương ứng, thường là `MimeMessage` hoặc `SimpleMailMessage` tùy overload và cách gọi.
- **Value:** exception liên quan đến việc gửi message đó.

Đây là dữ liệu có giá trị nhất khi cần phân tích **batch có nhiều message**.

### getMessageExceptions()

`getMessageExceptions()` trả về mảng các exception gắn với message failures. Nó thuận tiện khi chỉ muốn duyệt các nguyên nhân, nhưng không giữ thông tin tương ứng với message một cách rõ ràng như map.

Trong xử lý batch, ưu tiên `getFailedMessages()` để biết **message nào** đi với **cause nào**. Dùng `getMessageExceptions()` khi cần điều tra hoặc thống kê nguyên nhân nhưng không có thông tin message đầy đủ.

### getCause() và getMessage()

`getCause()` có thể thể hiện lỗi mức transport hoặc lỗi bao ngoài, chẳng hạn lỗi kết nối. `getMessage()` cung cấp mô tả tổng quát, nhưng không đủ để phân biệt:

- Lỗi trước khi gửi dữ liệu hay sau khi SMTP có thể đã nhận dữ liệu.
- Một hay nhiều message thất bại.
- Có recipient nào được server chấp nhận hay không.

Không chỉ xử lý bằng `exception.getMessage().contains("timeout")` rồi tự động retry tất cả.

## 4. Đọc failed messages đúng cách

Ví dụ cơ bản:

```java
import org.springframework.mail.MailSendException;

import java.util.Map;

try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    Map<Object, Exception> failedMessages =
            ex.getFailedMessages();

    for (Map.Entry<Object, Exception> entry :
            failedMessages.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception failure = entry.getValue();

        // Xác định message qua correlation mapping của ứng dụng.
        // Phân loại failure trước khi quyết định retry.
    }

    if (failedMessages.isEmpty()) {
        // Có lỗi send/transport nhưng không có map chi tiết.
        // Không diễn giải map rỗng là toàn bộ message đã gửi thành công.
    }
}
```

Điểm quan trọng là **map có thể rỗng** trong một số trường hợp exception được tạo mà không có thông tin thất bại theo từng message. Do đó:

- `failedMessages.isEmpty() == true` **không** chứng minh batch thành công.
- `failedMessages.containsKey(message) == true` chỉ cho biết Spring ghi nhận lỗi ở message đó.
- Một message không nằm trong map không đồng nghĩa đã được giao đến Inbox.
- Với lỗi network xảy ra tại thời điểm mơ hồ, message nằm trong map cũng không luôn có nghĩa chắc chắn chưa được SMTP server chấp nhận.

## 5. Key trong failedMessages là đối tượng message, không phải email address

Giả sử ứng dụng:

```java
MimeMessage first = mailSender.createMimeMessage();
MimeMessage second = mailSender.createMimeMessage();

// Thiết lập người nhận, subject, body cho từng message.
mailSender.send(first, second);
```

Khi gặp `MailSendException`, key trong `getFailedMessages()` là đối tượng message gắn với thao tác gửi, chứ **không mặc định là chuỗi recipient**.

Không giả định:

```java
// Sai cách hiểu: key không phải String email address.
Exception cause = ex.getFailedMessages()
        .get("customer@example.net");
```

Thay vào đó, ứng dụng cần tự lưu một ánh xạ từ message object sang notification ID hoặc mã nghiệp vụ trước khi gọi sender:

```java
Map<Object, String> notificationIds = new IdentityHashMap<>();

MimeMessage first = buildMessage(firstNotification);
MimeMessage second = buildMessage(secondNotification);

notificationIds.put(first, firstNotification.id());
notificationIds.put(second, secondNotification.id());

try {
    mailSender.send(first, second);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        String notificationId =
                notificationIds.get(entry.getKey());
        Exception cause = entry.getValue();

        // correlation bằng notificationId
        // thay vì ghi toàn bộ MimeMessage vào log.
    }
}
```

Trong ví dụ, `IdentityHashMap` thể hiện rõ việc ánh xạ dựa trên **cùng object instance** đã đưa vào batch. Đây là kỹ thuật chỉ nên dùng trong một luồng xử lý đang chạy; không nên lưu key object vào database hoặc coi object identity là định danh bền vững.

Nếu hệ thống dùng `SimpleMailMessage`, cách tiếp cận tương tự có thể thực hiện với các object gốc. Nhưng khi cần retry sau restart hoặc nhiều worker, hãy lưu **notification ID** trong database và xây lại message từ dữ liệu đó.

## 6. SimpleMailMessage và MimeMessage có thể cùng xuất hiện

Spring Mail có hai hướng gửi quen thuộc:

### Gửi text đơn giản

```java
SimpleMailMessage simple = new SimpleMailMessage();
simple.setFrom("no-reply@example.org");
simple.setTo("person@example.net");
simple.setSubject("Thông báo");
simple.setText("Nội dung text.");

mailSender.send(simple);
```

### Gửi MIME/HTML

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, "UTF-8");

helper.setFrom("no-reply@example.org");
helper.setTo("person@example.net");
helper.setSubject("Thông báo HTML");
helper.setText("<p>Nội dung <strong>HTML</strong>.</p>", true);

mailSender.send(mime);
```

Trong `JavaMailSenderImpl`, nội dung `SimpleMailMessage` được chuyển sang MIME để gửi qua transport, nhưng thông tin failed message có thể tham chiếu đến object đơn giản ban đầu. Vì vậy, code xử lý không nên ép mọi key thành `MimeMessage`:

```java
Object key = entry.getKey();

if (key instanceof MimeMessage mime) {
    // MIME message bị ghi nhận lỗi.
} else if (key instanceof SimpleMailMessage simple) {
    // Simple mail message bị ghi nhận lỗi.
} else {
    // Không biết chính xác loại key:
    // chỉ dùng correlation metadata đã lưu bên ngoài.
}
```

Không dựa vào `key.toString()` để ghi log. Đối tượng message có thể mang địa chỉ người nhận, nội dung hoặc header nhạy cảm.

## 7. Phân biệt một message và nhiều recipient

Một `MimeMessage` có thể gửi cho **nhiều người nhận**:

```java
helper.setTo(new String[] {
        "a@example.net",
        "b@example.net",
        "c@example.net"
});
```

Khi message này gặp lỗi:

- `getFailedMessages()` nói về **message object** gặp lỗi.
- Nó không nhất thiết nói chính xác **recipient nào** bị từ chối.
- Một số recipient có thể được server chấp nhận trong khi recipient khác bị từ chối, tùy lệnh SMTP, chính sách transport và cấu hình gửi từng phần.

Để tìm tình trạng từng địa chỉ, cần xem nguyên nhân Jakarta Mail, đặc biệt `jakarta.mail.SendFailedException` và các exception chuyên biệt của SMTP provider.

Đừng lấy số entry của `failedMessages` làm số địa chỉ người nhận thất bại. Một entry có thể liên quan đến message có hàng chục recipient.

## 8. Hiểu SendFailedException của Jakarta Mail

`SendFailedException` có thể mang những nhóm địa chỉ:

```java
import jakarta.mail.SendFailedException;
import jakarta.mail.Address;

void inspect(SendFailedException ex) {
    Address[] invalid = ex.getInvalidAddresses();
    Address[] validSent = ex.getValidSentAddresses();
    Address[] validUnsent = ex.getValidUnsentAddresses();
}
```

Ý nghĩa khái quát:

| API | Ý nghĩa của transport khi báo lỗi | Điều không được tự suy diễn |
| --- | --- | --- |
| `getInvalidAddresses()` | Các địa chỉ không hợp lệ/không được chấp nhận theo báo cáo transport | Không phải toàn bộ recipient của message |
| `getValidSentAddresses()` | Những địa chỉ mà transport báo đã được gửi tới/chấp nhận ở giai đoạn liên quan | Không chứng minh giao tới Inbox |
| `getValidUnsentAddresses()` | Địa chỉ hợp lệ nhưng chưa được gửi theo báo cáo transport | Không phải lỗi cú pháp email |

Các mảng có thể `null` hoặc rỗng tùy lỗi và implementation. Đừng mặc định mọi exception đều chứa danh sách đầy đủ.

### Một ví dụ phân tích

Giả sử message có ba recipient:

```text
To: a@example.net, b@example.net, c@example.net
```

Transport báo:

```text
invalidAddresses:     b@example.net
validSentAddresses:   a@example.net
validUnsentAddresses: c@example.net
```

Khi đó không nên gửi lại nguyên message tới cả ba recipient một cách mù quáng: `a@example.net` có thể nhận bản sao. Cần đọc chính sách partial send và xem transport thực sự đã thực hiện những gì.

**Lưu ý:** báo cáo các nhóm recipient phản ánh hành vi và bằng chứng của transport tại thời điểm exception, không phải sự kiện delivery cuối cùng.

## 9. Chuỗi nguyên nhân MessagingException

Một exception Jakarta Mail có thể chứa:

- Cause thông thường (`Throwable.getCause()`).
- “Next exception” theo cơ chế liên kết của `MessagingException.getNextException()`.
- Một `SendFailedException` hoặc exception SMTP cụ thể ở sâu trong chuỗi.

Vì vậy, chỉ dùng `getCause()` một lần có thể bỏ sót dữ liệu chẩn đoán.

Ví dụ đi qua cause chain:

```java
static void traceCauses(
        Throwable failure,
        Consumer<Throwable> consumer
) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = failure;
    while (current != null && visited.add(current)) {
        consumer.accept(current);
        current = current.getCause();
    }
}
```

Hàm trên chỉ duyệt cause chain thông thường. Với `MessagingException`, cần xem thêm `getNextException()`; next exception có thể khác với cause chain. Một utility đầy đủ cần tránh lặp vòng và không log raw exception messages khi chưa được kiểm soát dữ liệu nhạy cảm.

### Đọc next exception cẩn thận

```java
if (failure instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();
    if (next != null) {
        // Phân tích next theo kiểu exception thực tế.
    }
}
```

Với SMTP provider, có thể có exception chuyên biệt chứa SMTP reply code, địa chỉ và command. Tên package của exception cụ thể phụ thuộc mail implementation/version đang dùng (ví dụ thư viện Angus hoặc các implementation cũ), nên không hard-code package class khi chưa xác định dependency của dự án.

## 10. SMTP reply code là dữ liệu chẩn đoán, không phải toàn bộ kết luận

SMTP có các nhóm phản hồi:

| Nhóm | Ý nghĩa tổng quát | Hướng xử lý sơ bộ |
| --- | --- | --- |
| 2xx | Server chấp nhận bước giao thức tương ứng | Xem bước nào được chấp nhận |
| 4xx | Lỗi tạm thời theo giao thức | Có thể retry theo policy |
| 5xx | Lỗi vĩnh viễn theo giao thức | Thường cần sửa cấu hình, địa chỉ hoặc dữ liệu |

Ví dụ:

- `421`: server không sẵn sàng/đóng kết nối.
- `450` hoặc `451`: vấn đề tạm thời liên quan mailbox/server.
- `550`: nhiều hệ thống dùng khi mailbox/recipient bị từ chối.
- `552`: vượt giới hạn lưu trữ hoặc kích thước theo ngữ cảnh server.
- `554`: message bị từ chối theo chính sách hoặc lỗi giao dịch.

Đây là các ví dụ phổ biến, không phải quy tắc tuyệt đối cho mọi provider. **Reply code cần gắn với lệnh SMTP cụ thể** và thông báo server cung cấp. Cùng mã `550` có thể xuất hiện vì nhiều lý do khác nhau.

### Reply của RCPT TO khác reply cuối DATA

```text
Client                              SMTP server
  | ---- MAIL FROM ---------------> |
  | <--- 250 ---------------------- |
  | ---- RCPT TO -----------------> |
  | <--- 250 / 4xx / 5xx ---------- |
  | ---- DATA --------------------> |
  | <--- 354 ---------------------- |
  | ---- MIME bytes + "." --------> |
  | <--- 250 / 4xx / 5xx ---------- |
```

Nếu recipient bị từ chối ở bước `RCPT TO`, transport có thể biết rõ địa chỉ nào bị từ chối. Nếu kết nối mất **sau khi gửi xong DATA nhưng trước khi nhận phản hồi cuối**, ứng dụng có thể không biết server đã chấp nhận message hay chưa.

Không phân loại lỗi chỉ dựa vào cụm từ trong exception mà bỏ qua thời điểm lỗi xảy ra.

## 11. Connection failure khác per-message failure

Khi gửi một batch, lỗi có thể ở hai tầng:

### Lỗi kết nối chung

```text
connect SMTP
     |
     X connection failed
     |
     +-- M1 chưa có cơ hội gửi
     +-- M2 chưa có cơ hội gửi
     +-- M3 chưa có cơ hội gửi
```

Nếu kết nối chưa hình thành, nhiều message có thể cùng được gắn với một root cause. Trong `JavaMailSenderImpl`, lỗi thiết lập kết nối có thể khiến toàn bộ danh sách đầu vào được báo failed.

### Lỗi từng message

```text
connect SMTP: success
   |
   +-- send M1 -> accepted
   +-- send M2 -> error
   +-- send M3 -> accepted
   |
   +-- close connection
```

Trong tình huống này, failed map hữu ích để phân biệt message bị lỗi và message không được ghi nhận lỗi trong vòng lặp. Nhưng kết quả thực tế còn phụ thuộc response SMTP và trạng thái đóng transport.

**Không retry toàn bộ batch chỉ vì có một `MailSendException`.** Trước hết phải phân tích failed messages và trạng thái đã ghi nhận cho từng notification.

## 12. Ví dụ đầy đủ: gửi batch và tương quan notification ID

Giả sử ứng dụng có ba notification cần gửi. Mỗi notification có ID bền vững.

```java
record MailRequest(
        UUID notificationId,
        String recipient,
        String subject,
        String body
) {}
```

Tạo MIME message bằng helper:

```java
private MimeMessage createMail(MailRequest request)
        throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("notification@example.org");
    helper.setTo(request.recipient());
    helper.setSubject(request.subject());
    helper.setText(request.body(), false);

    return message;
}
```

Tương quan object với notification:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;

import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public void submitBatch(List<MailRequest> requests)
        throws MessagingException {

    List<MimeMessage> messages = new ArrayList<>();
    Map<Object, UUID> correlation = new IdentityHashMap<>();

    for (MailRequest request : requests) {
        MimeMessage mime = createMail(request);
        messages.add(mime);
        correlation.put(mime, request.notificationId());
    }

    try {
        mailSender.send(messages.toArray(MimeMessage[]::new));
        for (MailRequest request : requests) {
            // Record SMTP submission result using a short DB transaction.
            markSubmitted(request.notificationId());
        }
    } catch (MailSendException ex) {
        for (Map.Entry<Object, Exception> entry :
                ex.getFailedMessages().entrySet()) {

            UUID notificationId =
                    correlation.get(entry.getKey());
            Exception sendFailure = entry.getValue();

            if (notificationId != null) {
                recordFailureForReview(
                        notificationId,
                        sendFailure
                );
            }
        }

        // Khi batch ném exception, phần không có trong failed map
        // và phần map thiếu thông tin cần được xác minh riêng.
        recordBatchExceptionForReconciliation(ex);
    }
}
```

Các method `markSubmitted`, `recordFailureForReview` và `recordBatchExceptionForReconciliation` là điểm mở rộng do ứng dụng triển khai. Ví dụ mô tả **cách lấy correlation**, chưa phải chính sách retry/commit đầy đủ; production phải lưu trạng thái một cách nguyên tử, xử lý map rỗng và phân loại từng failure.

### Vì sao không tự đánh dấu mọi message không có trong failed map là DELIVERED?

Vì:

1. “Không có lỗi được ghi nhận theo message” không đồng nghĩa delivery.
2. Lỗi transport/close có thể xuất hiện sau một số lần gửi.
3. SMTP acceptance khác delivery tới mailbox.
4. Nếu không có bằng chứng đủ mạnh cho từng message, cần trạng thái chưa xác định hoặc cơ chế reconciliation.

Nếu không cần tối ưu số round-trip, gửi từng notification riêng biệt thường giúp correlation và trạng thái đơn giản hơn:

```java
for (MailRequest request : requests) {
    try {
        mailSender.send(createMail(request));
        markSubmitted(request.notificationId());
    } catch (MailSendException ex) {
        recordFailureForReview(request.notificationId(), ex);
    }
}
```

Nhưng cách gửi riêng không loại bỏ kết quả SMTP mơ hồ, không tự bảo đảm exactly-once, và phải có chính sách lỗi khi chuẩn bị message trước `send`.

## 13. Cách đọc getMessageExceptions()

Ví dụ:

```java
catch (MailSendException ex) {
    Exception[] messageErrors = ex.getMessageExceptions();

    for (Exception error : messageErrors) {
        // Phân loại loại lỗi hoặc tạo chẩn đoán tổng hợp.
    }
}
```

`getMessageExceptions()` phù hợp để nhìn danh sách nguyên nhân, nhưng có hai hạn chế khi xử lý nghiệp vụ:

- Không có khóa message trong phần tử mảng.
- Dễ đếm một lỗi chung lặp ở nhiều message như nhiều sự cố độc lập.

Ví dụ lỗi kết nối trước khi gửi có thể ảnh hưởng mười message. Nếu map chứa mười entry cùng một exception gốc, đếm “mười lỗi SMTP khác nhau” có thể sai.

Thường nên thống kê riêng:

- Số notification bị ảnh hưởng.
- Số exception theo lớp hoặc root cause.
- Số batch bị lỗi.
- Số nguyên nhân network/auth/recipient/content.

Không dùng `getMessageExceptions().length` làm số message chắc chắn chưa giao tới người nhận.

## 14. Phân loại nguyên nhân: network, authentication, recipient, content

| Nhóm lỗi | Dấu hiệu thường gặp | Retry? | Điều cần xem |
| --- | --- | --- | --- |
| DNS/connection | Không resolve host, connect refused, network unavailable | Thường retry được nếu thất bại chắc chắn trước gửi | Host, port, firewall, DNS, timeout |
| TLS/STARTTLS | Handshake/certificate/protocol lỗi | Thường cần sửa cấu hình; không retry nóng | TLS mode, trust, chứng chỉ, server |
| Authentication | Credential bị từ chối, SMTP AUTH disabled | Không retry vô hạn | Username, auth mechanism, provider policy |
| Recipient | Server từ chối một số RCPT TO | Tùy mã và recipient group | Địa chỉ cụ thể, 4xx/5xx, partial send |
| Sender/domain policy | Sender không được phép, relay denied | Thường cần sửa cấu hình/chính sách | From, envelope sender, authentication |
| Message content/size | Kích thước quá lớn, nội dung bị chặn | Thường cần sửa nội dung | MIME size, attachment, provider limit |
| Rate limiting | Server throttling, phản hồi tạm thời | Retry có backoff | Quota, throughput, Retry-After nếu API có |
| Timeout sau DATA | Không thấy phản hồi cuối | **Kết quả mơ hồ** | Log transport, provider event, SMTP stage |
| Lỗi đóng transport | Exception khi đóng connection | Không đủ để khẳng định các message chưa gửi | Kết quả trước khi close, provider logs |

Không dùng công thức “mọi `MailSendException` đều retry”. Cùng lớp exception có thể bao nhiều nguyên nhân rất khác nhau.

## 15. MailAuthenticationException không nên bị nhầm thành failed message

Ví dụ cấu hình SMTP sai credential:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

Nếu xác thực thất bại, Spring có thể ném `MailAuthenticationException`. Đây là loại lỗi riêng; code chỉ `catch (MailSendException)` có thể không xử lý nó.

Nên dùng các nhánh rõ ràng:

```java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Điều tra credential/provider policy; không retry ồ ạt.
} catch (MailSendException ex) {
    // Đọc failed messages và phân loại transport outcome.
} catch (MailException ex) {
    // Lỗi Spring Mail khác, ghi nhận theo notification.
}
```

Không log password, token SMTP hoặc toàn bộ cấu hình chứa secret. Với lỗi xác thực, cần kiểm tra tài khoản, quyền SMTP AUTH và cấu hình TLS.

## 16. MailPreparationException xảy ra trước hoặc khi chuẩn bị gửi

Email phức tạp có thể được tạo bằng `MimeMessagePreparator`:

```java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");
    helper.setFrom("no-reply@example.org");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(plainText, htmlText);
    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );
};

mailSender.send(preparator);
```

Nếu preparator lỗi vì template, địa chỉ, resource hoặc tạo MIME, Spring có thể ném `MailPreparationException` chứ không nhất thiết `MailSendException`.

Vì vậy:

- Xử lý lỗi **render/compose** tách với lỗi SMTP.
- Không retry kết nối mạng khi lỗi thực tế là file attachment không đọc được.
- Không coi message đã bắt đầu gửi nếu preparator chưa tạo MIME thành công.

Lỗi chuẩn bị message thường cần sửa dữ liệu/template/resource. Một số lỗi nguồn tài nguyên tạm thời có thể retry, nhưng phải phân loại theo nguyên nhân thực tế.

## 17. Cấu hình SMTP timeout để chẩn đoán

Các property timeout giúp tránh thread bị treo quá lâu:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Các giá trị tính bằng millisecond trong cấu hình Jakarta Mail SMTP. Đây là giá trị minh họa, cần điều chỉnh theo mạng, provider và kích thước message.

| Property | Phạm vi |
| --- | --- |
| `mail.smtp.connectiontimeout` | Timeout khi thiết lập kết nối |
| `mail.smtp.timeout` | Timeout đọc phản hồi từ socket |
| `mail.smtp.writetimeout` | Timeout khi ghi dữ liệu ra socket |

Các timeout có ý nghĩa khác nhau khi quyết định retry:

- **Không kết nối được:** thường có bằng chứng message chưa được gửi qua kết nối đó.
- **Timeout đọc phản hồi sau DATA:** server có thể đã nhận message; không được suy ra chưa gửi.
- **Timeout ghi dữ liệu:** cần xem giai đoạn và lượng dữ liệu đã được truyền; kết quả có thể chưa chắc chắn.

Timeout giúp hệ thống không treo vô hạn, nhưng không tự cung cấp bảo đảm exactly-once.

## 18. Bật mail debug một cách an toàn

Jakarta Mail có các tùy chọn debug giao thức để giúp tìm lệnh SMTP và phản hồi server. Trong môi trường kiểm soát, có thể bật theo cấu hình tương ứng:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
```

**Không bật debug SMTP vô thời hạn trong production.** Log giao thức có thể chứa địa chỉ gửi/nhận, metadata, nội dung nhạy cảm và tùy trường hợp thông tin xác thực. Cần:

- Chỉ bật trong khoảng điều tra ngắn.
- Kiểm soát nơi log được ghi và ai được truy cập.
- Loại bỏ/redact địa chỉ, token, header nhạy cảm và nội dung thư.
- Không đưa debug log thô vào ticket công khai.
- Tắt lại khi xong và tuân thủ chính sách retention.

Trong nhiều tình huống, chỉ cần SMTP reply code, stage, exception class, notification ID và provider message ID để chẩn đoán mà không cần lưu body.

## 19. Log thế nào để tìm failed message nhưng không lộ PII?

Một log có cấu trúc:

```text
event=mail_submission_failure
notificationId=N-2026-091
attempt=2
transport=smtp
smtpStage=RCPT_TO
smtpReplyCode=550
exceptionClass=SendFailedException
classification=PERMANENT_RECIPIENT_REJECTION
status=FAILED
```

Không nên:

```java
logger.error(
        "Failed mail: " + failedMessage +
        ", cause=" + exception,
        exception
);
```

Vì `failedMessage` và exception message có thể mang raw email addresses, server detail, đường dẫn nội bộ hoặc nội dung message.

Hãy log các trường đã chuẩn hóa. Nếu cần truy dấu người nhận, lưu `recipientId` nội bộ hoặc hash có kiểm soát thay vì địa chỉ đầy đủ.

### Correlation ID nên tồn tại trước send

Một notification ID nên được cấp khi ứng dụng ghi nhận yêu cầu gửi, ví dụ:

```text
orderEventId=order-123-confirmed
notificationId=N-2026-091
messageType=ORDER_CONFIRMATION
templateVersion=v5
attempt=2
```

Khi `MailSendException` xảy ra, hệ thống có thể liên kết exception với notification mà không cần tìm trong subject/body. Điều này đặc biệt quan trọng khi cùng nội dung được gửi cho nhiều người.

## 20. Khi gửi batch: đừng tự retry lại cả danh sách

Ví dụ anti-pattern:

```java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    mailSender.send(messages); // Nguy cơ gửi trùng toàn batch.
}
```

Vì một số message có thể đã được SMTP server chấp nhận trong lần đầu, gửi lại tất cả có thể tạo duplicate.

Một luồng phù hợp hơn:

```text
Batch send throws MailSendException
            |
            v
Đọc failedMessages + root causes
            |
            v
Tương quan message với notification ID
            |
            v
Phân loại theo từng notification
            |
            +-- definite temporary rejection -> RETRY_WAIT
            +-- definite permanent rejection -> FAILED
            +-- ambiguous acceptance --------> UNKNOWN
            +-- confirmed submission --------> SUBMITTED
            |
            v
Retry riêng những notification phù hợp policy
```

**Quan trọng:** map chỉ là một phần bằng chứng. Không cố suy đoán `SUBMITTED` cho mọi message không nằm trong map nếu batch có lỗi đóng transport hoặc kết quả chưa đủ rõ.

### Vì sao gửi từng notification có thể dễ vận hành hơn?

Gửi một message mỗi lần:

- Dễ gắn lỗi vào notification ID.
- Dễ lưu attempt count và trạng thái.
- Dễ phân loại retry riêng.
- Ít khả năng nhầm message này với message khác.

Nhược điểm có thể là overhead kết nối/transport và throughput. Nếu batching thật sự cần thiết, cần xây cơ chế correlation và trạng thái đủ chi tiết, thay vì chỉ bắt một exception chung.

## 21. Retry phải dựa trên bằng chứng, không chỉ loại exception

Một chính sách tối giản:

| Tình huống | Trạng thái gợi ý | Hành động |
| --- | --- | --- |
| Lỗi DNS/connect trước gửi | `RETRY_WAIT` | Retry có backoff |
| SMTP trả lời rõ ràng 4xx và chưa chấp nhận message | `RETRY_WAIT` | Retry theo giới hạn |
| SMTP trả lời rõ ràng 5xx recipient/sender bị từ chối | `FAILED` hoặc chờ sửa dữ liệu | Không retry liên tục |
| SMTP AUTH lỗi | `FAILED`/configuration incident | Sửa cấu hình trước khi retry |
| Template/MIME lỗi trước send | `FAILED`/quarantine | Sửa dữ liệu/template |
| Mất phản hồi cuối sau DATA | `UNKNOWN` | Provider reconciliation hoặc policy có rủi ro |
| SMTP đã chấp nhận rõ ràng | `SUBMITTED` | Theo dõi delivery riêng |

Đây là khung chính sách; phải xét đặc điểm SMTP provider, business criticality, recipient count và yêu cầu tránh gửi trùng của ứng dụng.

### Backoff và jitter

Với lỗi tạm thời:

```text
Attempt 1: gửi lần đầu
Attempt 2: sau 30 giây
Attempt 3: sau 2 phút
Attempt 4: sau 10 phút
Attempt 5: sau 30 phút
```

Giới hạn số lần retry và thêm jitter để tránh nhiều worker cùng retry một lúc. Nếu provider trả hướng dẫn giới hạn tốc độ hoặc thời gian chờ, ưu tiên áp dụng theo chính sách provider.

Với lỗi thường trực hoặc dữ liệu sai, retry lặp lại không giúp ích mà có thể gây khóa tài khoản hoặc vượt quota.

## 22. Trạng thái UNKNOWN và kết quả SMTP mơ hồ

Một cửa sổ lỗi điển hình:

```text
Worker                            SMTP server
  |                                    |
  |--------- DATA + MIME ------------->|
  |                                    | đã nhận message
  |<-------- 250 accepted -------------|  (phản hồi bị mất)
  X timeout                           |
  |                                    |
  | MailSendException                  |
  |                                    |
  | Không biết chắc server đã nhận hay chưa
```

Nếu tự động gửi lại, server có thể nhận message thứ hai. Nếu không gửi lại, trong trường hợp server chưa nhận, email có thể bị mất.

Hãy tách:

- **Lỗi chắc chắn trước acceptance:** có thể retry theo policy.
- **Lỗi chắc chắn bị server từ chối:** xử lý theo mã và nguyên nhân.
- **Lỗi không có bằng chứng đủ về acceptance:** ghi `UNKNOWN`, tra cứu provider nếu có, áp dụng chính sách reconcile.

### Cách reconcile

- Truy vấn provider API/event log theo correlation hoặc provider message ID khi có.
- Nhận delivery/accepted/bounce webhook nếu provider hỗ trợ.
- Giữ attempt metadata đủ để điều tra mà không lưu secret.
- Quy định thời gian chờ và thẩm quyền cho resend thủ công.
- Nếu bắt buộc tự retry, công khai rủi ro có thể có duplicate trong thiết kế và giám sát.

Không dùng `Message-ID` của MIME như một “khóa chống trùng SMTP” mặc định. SMTP thuần không có cam kết deduplicate toàn cục chỉ nhờ header này.

## 23. JavaMailSender trả về void: cần lưu trạng thái ở ứng dụng

API gửi thường không trả về đối tượng receipt per recipient:

```java
mailSender.send(mimeMessage); // void
```

Nếu không ném exception, ứng dụng biết quá trình gọi sender đã hoàn thành theo kết quả transport quan sát được; **không có nghĩa email đã được giao tới Inbox**.

Để theo dõi lifecycle, ứng dụng có thể lưu:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã ghi nhận yêu cầu gửi |
| `PROCESSING` | Worker đang xử lý |
| `SUBMITTED` | SMTP/provider chấp nhận request gửi theo kết quả quan sát được |
| `RETRY_WAIT` | Chờ retry lỗi có thể phục hồi |
| `FAILED` | Thất bại cuối theo policy |
| `UNKNOWN` | Chưa rõ server có nhận message hay chưa |
| `DELIVERED` | Có bằng chứng giao từ provider/event nếu hệ thống hỗ trợ |
| `BOUNCED` | Provider báo bounce sau submission |

Không dùng một cờ `sent=true/false` duy nhất nếu cần phân biệt lỗi gửi, lỗi giao thư và kết quả mơ hồ.

## 24. Gửi async: exception có thể xuất hiện ở worker, không ở caller

Ví dụ:

```java
@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendAsync(MimeMessage message) {
        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

Lỗi `MailSendException` xảy ra trong worker và được biểu diễn bằng future exceptional khi Spring quản lý method async đúng cách. Caller không thể chỉ dùng:

```java
try {
    asyncMailService.sendAsync(message);
} catch (MailSendException ex) {
    // Không phải cách bắt lỗi worker đã chạy bất đồng bộ.
}
```

Thay vào đó:

```java
asyncMailService.sendAsync(message)
        .whenComplete((unused, failure) -> {
            if (failure != null) {
                // Correlate theo notification ID và ghi nhận lỗi.
            }
        });
```

Nếu task cần phục hồi sau restart, future vẫn chưa đủ. Cần lưu notification/outbox và status bền vững để worker retry theo policy.

### @Async không tự chuyển MailSendException thành retry

Chỉ thêm `@Async` không làm lỗi biến mất và không tự phân loại nguyên nhân. `@Retryable` cũng cần thận trọng: retry nguyên method gửi có thể gửi trùng khi lần trước SMTP đã chấp nhận nhưng phản hồi bị mất.

## 25. Transactional outbox và MailSendException

Với email nghiệp vụ, một mô hình vận hành ổn định là:

```text
HTTP/business transaction
    |
    +-- UPDATE order
    +-- INSERT mail_notification(PENDING)
    |
    v
COMMIT
    |
    v
Worker claim notification
    |
    v
Compose MIME message
    |
    v
JavaMailSender.send(...)
    |
    +-- success ----------> SUBMITTED
    |
    +-- MailSendException -> classify failed message/cause
                                |
                                +-- RETRY_WAIT
                                +-- FAILED
                                +-- UNKNOWN
```

Lợi ích:

- Yêu cầu gửi tồn tại sau commit và sau restart.
- Mỗi notification có định danh riêng.
- Worker có thể ghi attempt và kết quả.
- Có thể điều tra failed message theo notification ID.
- Không cần giữ database transaction mở khi SMTP hoạt động.

### Outbox không tự loại bỏ mọi duplicate

Nếu worker gửi xong rồi crash trước khi ghi `SUBMITTED`, notification có thể được đọc lại. Vì thế:

- Dùng atomic claim và lease để hạn chế hai worker cùng gửi.
- Ghi correlation và trạng thái.
- Phân loại `UNKNOWN` khi kết quả chưa rõ.
- Dùng provider-level idempotency nếu provider API hỗ trợ.
- Không khẳng định exactly-once delivery chỉ nhờ outbox.

## 26. Không nhầm failed message với retry candidate

Một message xuất hiện trong `getFailedMessages()` là **message mà sender ghi nhận lỗi**. Nó chưa hẳn là một message **an toàn để gửi lại ngay**.

Ví dụ ba trường hợp:

**Trường hợp A — Connection refused trước khi SMTP session bắt đầu.** Message chưa được truyền qua kết nối thất bại. Đây thường là ứng viên retry sau khi chờ/backoff.

**Trường hợp B — Recipient bị từ chối rõ ràng bằng 550.** Gửi lại cùng địa chỉ ngay có thể thất bại tiếp; cần sửa recipient hoặc giải quyết chính sách của provider.

**Trường hợp C — Connection mất sau DATA.** Có thể message đã được chấp nhận. Retry ngay có nguy cơ duplicate; cần `UNKNOWN` hoặc provider reconciliation.

Do đó, workflow không nên là:

```text
failedMessages => retry tất cả
```

mà là:

```text
failedMessages
  -> match notification
  -> inspect root cause / SMTP stage
  -> classify outcome
  -> choose policy
  -> update durable state
```

## 27. Đọc dữ liệu recipient từ failed message: lưu ý bảo mật

Khi key là `MimeMessage`, bạn có thể lấy recipient:

```java
if (message instanceof MimeMessage mime) {
    Address[] recipients = mime.getAllRecipients();
    // Chỉ xử lý nội bộ; không log thô nếu chứa dữ liệu cá nhân.
}
```

Nhưng lấy recipient từ object lỗi có một số giới hạn:

- `getAllRecipients()` có thể phát sinh `MessagingException`.
- Recipient có thể bao gồm To, Cc và Bcc.
- Không phải recipient nào cũng thất bại nếu một message có nhiều người nhận.
- Log recipient có thể làm lộ địa chỉ email và Bcc.

Thay vì dựa vào raw message để tìm notification, lưu correlation từ trước. Nếu cần báo cáo recipient-level, phân loại thông tin từ `SendFailedException` và lưu kết quả với quyền truy cập phù hợp.

## 28. Kiểm thử MailSendException bằng SMTP test server

Không nên thử lỗi transport bằng cách gửi email thật cho người dùng.

Một số công cụ hữu ích:

- **GreenMail:** SMTP server dùng trong integration test để xác nhận message và mô phỏng tình huống gửi.
- **Mailpit/MailHog:** bắt email ở local/staging, xem nội dung và raw MIME.
- **Mock JavaMailSender:** tạo lỗi có chủ đích khi unit test nhánh xử lý exception.
- **SMTP test server có rule từ chối:** kiểm tra response code và trường hợp một recipient/message bị từ chối.

### Test 1 — Một message gửi thành công

Thiết lập SMTP test server chấp nhận message. Kiểm tra:

- `send(...)` không ném `MailSendException`.
- Message xuất hiện tại server test.
- Notification được ghi `SUBMITTED`, không phải `DELIVERED`.

### Test 2 — Không kết nối được

Cho sender trỏ tới một SMTP endpoint không sẵn sàng trong môi trường test. Kiểm tra:

- Lỗi được phân loại connection/transport phù hợp.
- Notification không bị xóa.
- Retry policy có backoff.
- Log không chứa credential.

### Test 3 — Recipient không hợp lệ

SMTP test server từ chối một recipient. Kiểm tra:

- `MailSendException` hoặc exception phù hợp được ghi nhận.
- Có thể truy cập `SendFailedException` khi implementation cung cấp.
- Danh sách invalid/valid sent/valid unsent không bị hiểu sai.
- Không gửi lại toàn message tới các recipient đã được chấp nhận.

### Test 4 — Batch chỉ một message bị từ chối

Gửi một batch hai hoặc ba message, cấu hình server từ chối một message cụ thể.

Kỳ vọng:

- Tương quan được failed entry với notification ID.
- Không mặc định đánh dấu toàn batch là thất bại.
- Không tự retry toàn batch.
- Trạng thái từng notification phản ánh bằng chứng thực tế.

### Test 5 — Exception không có failed-message map

Giả lập `MailSendException` không kèm map chi tiết. Kiểm tra:

- Code không ném `NullPointerException` khi duyệt.
- Không hiểu map rỗng là success.
- Toàn operation được chuyển sang điều tra/reconciliation phù hợp.

### Test 6 — Kết quả mơ hồ sau DATA

SMTP test harness chủ động ngắt kết nối ở ranh giới sau khi nhận DATA nhưng trước khi trả phản hồi cuối.

Kỳ vọng:

- Ứng dụng không retry tự động ngay với giả định chưa gửi.
- Trạng thái có thể chuyển `UNKNOWN`.
- Có đường đối chiếu hoặc chính sách vận hành rõ ràng.

## 29. Ví dụ utility tóm tắt lỗi theo kiểu an toàn

Thay vì log toàn bộ message, utility có thể xuất thống kê kiểu lỗi:

```java
public record SendFailureSummary(
        int failedMessageCount,
        List<String> exceptionTypes,
        boolean hasPerMessageDetails
) {}

public SendFailureSummary summarize(MailSendException ex) {
    Map<Object, Exception> failed = ex.getFailedMessages();

    List<String> types = failed.values().stream()
            .map(value -> value.getClass().getSimpleName())
            .distinct()
            .sorted()
            .toList();

    return new SendFailureSummary(
            failed.size(),
            types,
            !failed.isEmpty()
    );
}
```

Đây là summary **kỹ thuật**, không phải verdict “bao nhiêu email đã không tới Inbox”. Nó giúp log và dashboard có số lượng message gặp lỗi mà không cần chứa recipient/body.

Nếu map rỗng mà exception vẫn có cause, có thể ghi `exceptionType` và một `diagnosticCode` riêng; không cần lưu nguyên exception message chưa được sanitize.

## 30. Metrics và observability cho failed messages

| Metric | Ý nghĩa |
| --- | --- |
| `mail_submission_attempt_total` | Số lần cố gửi |
| `mail_submission_success_total` | Số lần sender quan sát được thành công |
| `mail_send_exception_total` | Số exception dạng MailSendException |
| `mail_failed_message_total` | Số entry failed message được ghi nhận |
| `mail_authentication_error_total` | Số lỗi xác thực |
| `mail_retry_scheduled_total` | Số notification được đưa vào retry |
| `mail_unknown_outcome_total` | Số notification có kết quả chưa rõ |
| `mail_permanent_failure_total` | Số notification thất bại cuối |
| `mail_outbox_lag_seconds` | Độ trễ từ lúc ghi notification đến xử lý |

Khi thiết kế metric, cần tránh cardinality cao. Không đặt email address, notification ID, subject hoặc exception message làm label của time-series metric. Những thông tin này nên nằm trong log/tracing có kiểm soát, không phải metric label.

### Phân biệt ba chỉ số

- **Exception count:** một lần gọi `send(...)` có thể ném một exception.
- **Failed-message count:** một exception có thể chứa nhiều failed-message entries.
- **Recipient failure count:** một message có thể có nhiều recipient và kết quả per-recipient khác nhau.

Ba số này không nên được cộng hoặc so sánh như thể cùng đơn vị.

## 31. Quy trình chẩn đoán thực tế

Khi hệ thống báo `MailSendException`, có thể thực hiện theo trình tự:

1. **Xác định notification/batch:** lấy notification ID, attempt, thời điểm và SMTP host alias.
2. **Xem loại exception:** MailSendException, MailAuthenticationException hay MailPreparationException.
3. **Đọc failed messages:** số entry, mapping về notification ID; xử lý riêng nếu map rỗng.
4. **Truy nguyên cause:** exception class, cause chain, `MessagingException.getNextException()` và SMTP reply code nếu có.
5. **Định vị giai đoạn SMTP:** connect, AUTH, MAIL FROM, RCPT TO, DATA hay close.
6. **Đánh giá partial outcome:** một message hay nhiều message; một recipient hay nhiều recipient.
7. **Phân loại:** retryable known failure, permanent failure, ambiguous outcome, observed submission.
8. **Ghi trạng thái bền vững:** `RETRY_WAIT`, `FAILED`, `UNKNOWN` hoặc `SUBMITTED` theo bằng chứng.
9. **Đối chiếu provider:** nếu outcome mơ hồ, tra event/log hoặc yêu cầu vận hành kiểm tra.
10. **Rà soát ảnh hưởng:** tránh gửi lại các notification đã được chấp nhận.

Quy trình này nên được tự động hóa ở phần có thể xác định chắc chắn và để đường xử lý riêng cho những tình huống SMTP không cung cấp đủ bằng chứng.

## 32. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ log `ex.getMessage()` | Không biết message nào lỗi | Đọc `getFailedMessages()` và correlation |
| Coi map rỗng là thành công | Bỏ sót lỗi transport/close | Phân tích exception chung và trạng thái operation |
| Coi mọi key là `MimeMessage` | ClassCastException khi gửi simple mail | Kiểm tra kiểu key, dùng correlation ID |
| Dùng recipient string làm map key | Không tìm được lỗi của message | Key là message object, không mặc định recipient |
| Log toàn bộ failed message | Lộ To/Cc/Bcc, body và header | Log notification ID và metadata đã sanitize |
| Dùng số failed entry làm số recipient lỗi | Thống kê sai | Phân biệt message-level và recipient-level |
| Retry toàn bộ batch | Gửi trùng message đã được chấp nhận | Retry theo notification và bằng chứng |
| Retry mọi MailSendException | Gửi trùng hoặc retry lỗi vĩnh viễn | Phân loại root cause, SMTP stage, UNKNOWN |
| Coi `send(...)` thành công là delivered | Báo sai trạng thái giao thư | Dùng SUBMITTED, theo dõi delivery riêng |
| Bỏ qua `MailAuthenticationException` | Lỗi xác thực không được xử lý | Catch MailException taxonomy đầy đủ |
| Không giới hạn SMTP timeout | Worker bị giữ lâu, queue tăng | Cấu hình connect/read/write timeout |
| Dùng Message-ID để chống trùng | Vẫn có thể nhận hai email | Dùng idempotency ở application/provider |
| Không lưu notification state | Không retry/reconcile sau restart | Outbox và trạng thái bền vững |
| Chỉ dựa vào exception text | Phân loại mong manh theo thông điệp provider | Ưu tiên type, stage và reply code |
| Không xử lý nhiều recipient | Có thể gửi lại tới người đã nhận | Phân tích SendFailedException/partial send |

## 33. Tình huống thực hành

### Tình huống A: Ba message, một message bị lỗi

Ứng dụng gọi `mailSender.send(m1, m2, m3)`. Exception chứa `failedMessages` với key `m2`.

**Cách xử lý:** tương quan `m2` với notification ID; đọc cause của `m2` và phân loại. Không tự động retry cả `m1` và `m3`. Với các message còn lại, dựa trên bằng chứng gửi và trạng thái mà hệ thống đã ghi để xác định submitted/unknown.

### Tình huống B: failedMessages rỗng

`MailSendException` xảy ra nhưng map không có entry.

**Cách xử lý:** không tuyên bố mọi message đều thành công. Kiểm tra `getCause()`, thông điệp tổng quát, giai đoạn xảy ra lỗi và provider log. Có thể cần reconciliation cho toàn operation.

### Tình huống C: SMTP từ chối một recipient trong message nhiều người nhận

Một `MimeMessage` có ba recipient; `SendFailedException` báo một địa chỉ invalid và hai địa chỉ khác thuộc nhóm valid.

**Cách xử lý:** đọc các nhóm địa chỉ và chính sách partial send. Không đánh đồng một failed message với ba recipient failed; không gửi lại tới tất cả nếu có người đã được server chấp nhận.

### Tình huống D: SMTP connection timeout trước connect

Ứng dụng chưa hình thành kết nối SMTP.

**Cách xử lý:** kiểm tra DNS, host, port, firewall, TLS mode và timeout. Nếu chắc chắn message chưa được gửi qua kết nối này, đưa notification vào retry với backoff.

### Tình huống E: Server đã nhận DATA nhưng phản hồi bị mất

Worker nhận exception do timeout sau khi truyền message.

**Cách xử lý:** ghi `UNKNOWN`, kiểm tra provider logs/event và tránh retry tự động khi chưa đánh giá nguy cơ duplicate.

### Tình huống F: Gửi bất đồng bộ rồi process restart

Worker bắt `MailSendException` nhưng chỉ log, không lưu trạng thái. Sau restart không còn biết notification nào lỗi.

**Cách xử lý:** dùng outbox/notification table, attempt count, claim, outcome và retry policy bền vững.

### Tình huống G: Credential SMTP bị thu hồi

Ứng dụng liên tục retry gửi mail nhưng toàn bộ lần thử đều thất bại vì xác thực.

**Cách xử lý:** phân loại `MailAuthenticationException`, tạm ngừng retry và sửa credential/phân quyền theo chính sách provider. Không tăng concurrency để “thử cho nhanh”.

### Tình huống H: Dashboard báo 100 failed messages

Một lỗi kết nối chung xảy ra với batch 100 message; map có 100 entry cùng nguyên nhân.

**Cách xử lý:** phân biệt 100 notification bị ảnh hưởng với một incident kết nối. Đếm exception classes/root causes riêng để tránh hiểu lầm đã xảy ra 100 lỗi độc lập.

## 34. Quy tắc cần ghi nhớ

1. **`MailSendException` là lỗi gửi/transport của Spring Mail, không đồng nghĩa mọi message chưa được nhận.**
2. **`getFailedMessages()` trả về `Map<Object, Exception>` theo message object**, không phải recipient hoặc notification ID.
3. **`getMessageExceptions()` cung cấp các cause theo message**, nhưng map tốt hơn khi cần correlation.
4. **Failed message khác failed recipient.** Với nhiều recipient, phải xem `SendFailedException` và thông tin SMTP.
5. **Map rỗng không đồng nghĩa batch thành công.**
6. **Một batch có thể có kết quả từng message khác nhau.** Không retry cả batch chỉ vì một exception.
7. **SMTP acceptance không phải delivery.** Sender thành công chỉ cho biết kết quả transport quan sát được.
8. **Timeout sau DATA có thể là kết quả mơ hồ.** Dùng `UNKNOWN` và reconciliation khi cần.
9. **Phân loại theo exception type, SMTP stage và reply code**, không dựa vào một chuỗi thông báo duy nhất.
10. **Lưu notification ID và trạng thái bền vững**, dùng retry/backoff và outbox cho email nghiệp vụ.
11. **Bảo vệ dữ liệu trong log.** Không in toàn bộ MimeMessage, Bcc, token hoặc SMTP credential.
12. **Dùng SMTP test server và fault injection** để kiểm tra nhánh lỗi, kể cả map rỗng và batch một phần.

## 35. Kết luận

`MailSendException` là tín hiệu quan trọng khi Spring Framework Mail không thể hoàn tất thao tác gửi theo kết quả transport. Đối với batch, `getFailedMessages()` giúp xác định các **message object được báo lỗi** và nguyên nhân tương ứng; `getMessageExceptions()` hỗ trợ khảo sát các lỗi thành phần. Tuy nhiên, chỉ riêng một exception không thể nói thay toàn bộ lịch sử SMTP, tình trạng từng recipient hoặc kết quả giao thư cuối cùng.

Cách xử lý an toàn là **tương quan từng message với notification ID trước khi gửi**, đọc exception theo tầng Spring/Jakarta Mail/SMTP, xác định giai đoạn xảy ra lỗi, phân biệt lỗi chắc chắn với kết quả mơ hồ, rồi ghi trạng thái `SUBMITTED`, `RETRY_WAIT`, `FAILED` hoặc `UNKNOWN` theo bằng chứng. Với ứng dụng bất đồng bộ hoặc nhiều worker, kết hợp transactional outbox, atomic claim và retry có giới hạn để công việc không mất qua restart mà không vô tình gửi lại cả batch. Nhờ đó, hệ thống vừa chẩn đoán `MailSendException` chính xác hơn vừa giảm nguy cơ gửi trùng và báo sai trạng thái email.
