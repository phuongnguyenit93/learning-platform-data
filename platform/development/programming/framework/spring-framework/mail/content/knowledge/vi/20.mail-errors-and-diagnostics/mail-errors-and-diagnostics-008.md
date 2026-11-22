# Lỗi recipient bị từ chối từng phần

Khi một ứng dụng **Spring Framework Mail** gửi email cho nhiều người nhận, không phải mọi địa chỉ đều được SMTP server chấp nhận như nhau. Có thể xảy ra trường hợp trong cùng một lần gửi:

- `alice@example.net` được server chấp nhận;
- `bob@example.net` bị từ chối vì địa chỉ không tồn tại;
- `carol@example.net` tạm thời bị từ chối do mailbox đầy hoặc chính sách giới hạn;
- kết quả gửi cho toàn bộ nhóm phụ thuộc vào cách mail provider xử lý **partial recipient failure**.

Đây là tình huống **recipient bị từ chối từng phần**: một số địa chỉ có thể hợp lệ và được chấp nhận ở một giai đoạn SMTP, trong khi các địa chỉ khác không được chấp nhận. Lỗi này khác với việc SMTP server từ chối hoàn toàn kết nối, sai mật khẩu hoặc từ chối toàn bộ nội dung email.

Điểm quan trọng là **không được tự động gửi lại toàn bộ danh sách người nhận khi chỉ một vài recipient thất bại**. Nếu một số địa chỉ đã được chấp nhận và nội dung email đã được gửi cho họ, retry toàn bộ có thể tạo email trùng.

Bài học tập trung vào luồng SMTP, khác biệt giữa cấu hình gửi toàn bộ và gửi một phần, cách đọc exception từ Jakarta Mail/Spring Mail, cách phân loại recipient cần retry và thiết kế trạng thái gửi an toàn.

## 1. Recipient bị từ chối từng phần là gì?

Một message có thể có nhiều địa chỉ trong các nhóm:

~~~text
To:  alice@example.net, bob@example.net
Cc:  carol@example.net
Bcc: audit@example.net
~~~

SMTP server không quyết định có nhận thư hay không chỉ bằng cách đọc header `To`, `Cc` hoặc `Bcc`. Khi gửi, SMTP client xây dựng **envelope recipients** và lần lượt gửi lệnh `RCPT TO` cho mỗi địa chỉ.

Một SMTP session minh họa:

~~~text
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250 SIZE 25000000

C: MAIL FROM:<notifications@example.com>
S: 250 2.1.0 Sender OK

C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<bob@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<carol@example.net>
S: 450 4.2.2 Mailbox temporarily unavailable

C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK
~~~

Ở giai đoạn `RCPT TO`:

- Alice và địa chỉ audit đã được chấp nhận làm recipient cho giao dịch SMTP hiện tại.
- Bob bị từ chối với phản hồi dạng 5xx.
- Carol bị từ chối tạm thời với phản hồi dạng 4xx.

**Chấp nhận `RCPT TO` chưa đồng nghĩa email đã được nộp thành công.** SMTP client còn phải chuyển nội dung bằng `DATA` (hoặc cơ chế tương đương nếu provider hỗ trợ) và nhận phản hồi hoàn tất. Nếu không có bước nộp nội dung thành công, những recipient từng được chấp nhận ở `RCPT TO` vẫn có thể **chưa được gửi**.

### 1.1. Ba câu hỏi phải tách biệt

Khi chẩn đoán, cần trả lời riêng:

1. **Địa chỉ nào được chấp nhận ở `RCPT TO`?**
2. **Nội dung thư có được SMTP server chấp nhận sau `DATA` hay không?**
3. **Email đã được giao tới mailbox cuối cùng hay chưa?**

Ba câu hỏi không tương đương. Thông thường Spring Mail/Jakarta Mail trực tiếp báo kết quả **SMTP submission**; việc delivery/bounce xảy ra về sau có thể cần provider event, DSN hoặc webhook riêng.

### 1.2. Partial rejection không chỉ là “email sai cú pháp”

Một địa chỉ có thể có cú pháp đúng như `alice@example.net` nhưng SMTP vẫn từ chối do:

- mailbox không tồn tại;
- domain hoặc relay policy không cho phép;
- quota/mailbox tạm thời đầy;
- recipient bị chặn theo danh sách chính sách;
- server yêu cầu xác thực hoặc không cho phép relay;
- tần suất gửi hoặc reputation bị giới hạn;
- server từ chối vì lý do tạm thời mà không tiết lộ chi tiết.

Ngược lại, địa chỉ không hợp lệ về cú pháp có thể bị phát hiện ngay trong Java trước khi ứng dụng đi tới lệnh SMTP.

## 2. Diễn biến SMTP khi có recipient bị từ chối

Để hiểu xử lý lỗi, cần nhìn theo thứ tự của SMTP:

~~~mermaid
sequenceDiagram
    participant A as Spring Mail
    participant S as SMTP server
    A->>S: MAIL FROM
    S-->>A: 250 Sender accepted
    A->>S: RCPT TO Alice
    S-->>A: 250 Accepted
    A->>S: RCPT TO Bob
    S-->>A: 550 Rejected
    A->>S: RCPT TO Carol
    S-->>A: 450 Temporary rejection
    Note over A,S: Tiếp tục hay dừng phụ thuộc cấu hình sendpartial/provider
    alt Partial delivery enabled
        A->>S: DATA cho recipient đã chấp nhận
        S-->>A: 250 Message queued
        Note over A: Báo lỗi/partial result cho recipient bị từ chối
    else Partial delivery disabled
        A->>S: RSET hoặc kết thúc giao dịch
        Note over A: Không nộp DATA theo đường gửi partial mặc định
    end
~~~

Hành vi chính xác của transport còn phụ thuộc Jakarta Mail SMTP provider và cấu hình. Quy tắc quan trọng:

- Lệnh `RCPT TO` cho mỗi địa chỉ có thể có phản hồi độc lập.
- Gửi phần còn lại hay dừng cả message là quyết định của SMTP client/provider.
- Với chế độ không cho phép partial send, một recipient thất bại có thể làm cả message bị hủy trước khi nộp `DATA`.
- Với partial send, provider có thể nộp nội dung cho nhóm đã được chấp nhận và đồng thời báo lỗi cho nhóm bị từ chối.

### 2.1. Mã phản hồi 2xx, 4xx và 5xx

| Phản hồi | Ý nghĩa tổng quát | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| `250` | Recipient được chấp nhận trong giao dịch SMTP hiện tại | `250 2.1.5 Recipient OK` | Tiếp tục xử lý message, chưa kết luận delivery |
| `251` | Server chấp nhận và có cơ chế forward | `251 User not local; will forward` | Xem như acceptance theo phản hồi server |
| `450` | Từ chối tạm thời | Mailbox unavailable | Có thể retry theo chính sách |
| `451` | Lỗi xử lý tạm thời | Local error | Có thể retry với backoff |
| `452` | Thiếu tài nguyên tạm thời | Insufficient storage | Có thể retry với giới hạn |
| `550` | Từ chối thường được coi là vĩnh viễn | User unknown/policy | Kiểm tra nguyên nhân, không retry mù |
| `551` | User không local; có gợi ý forward | User not local | Tuân thủ chính sách địa chỉ, không tự chuyển tiếp tùy tiện |
| `553` | Mailbox name không được chấp nhận | Invalid mailbox name | Sửa/kiểm tra địa chỉ |
| `554` | Transaction hoặc policy bị từ chối | Transaction failed | Phân tích phản hồi theo giai đoạn |

Theo mô hình SMTP:

- **4xx** là transient negative completion: vấn đề có thể tạm thời.
- **5xx** là permanent negative completion: cùng một yêu cầu không nên retry nguyên trạng vô hạn.

Tuy nhiên, mã được trả về trong **ngữ cảnh lệnh cụ thể** mới quyết định ý nghĩa. Ví dụ `550` ở `RCPT TO` khác `550` hoặc `554` ở giai đoạn nộp message. Phần mô tả text của server cũng không phải một API được chuẩn hóa hoàn toàn.

### 2.2. Enhanced status codes

Server có thể trả mã chi tiết:

~~~text
550 5.1.1 Recipient address rejected: User unknown
450 4.2.2 Mailbox full
550 5.7.1 Relay access denied
451 4.7.1 Temporary rate limit
~~~

Ví dụ:

- `5.1.1` thường liên quan địa chỉ nhận không tồn tại.
- `4.2.2` thường liên quan quota/mailbox full theo hướng tạm thời.
- `5.7.1` có thể là policy, authentication hoặc relay restriction.
- `4.7.1` có thể là chính sách hạn chế tạm thời.

**Không suy ra toàn bộ nguyên nhân chỉ từ chuỗi mô tả.** Cần xem lệnh SMTP, mã 3 chữ số, enhanced status và chính sách provider.

## 3. Hai chế độ xử lý: all-or-nothing và partial send

Với SMTP transport thường dùng trong Jakarta Mail, thuộc tính `mail.smtp.sendpartial` ảnh hưởng cách xử lý khi một số recipient bị từ chối.

### 3.1. Mặc định thường là sendpartial=false

Ví dụ:

~~~properties
mail.smtp.sendpartial=false
~~~

Trong chế độ này, khi provider phát hiện recipient không được chấp nhận, nó thường **không nộp nội dung message cho nhóm còn lại** và báo lỗi gửi. Những địa chỉ từng nhận phản hồi `250` ở `RCPT TO` có thể vẫn thuộc nhóm **valid but unsent**: địa chỉ hợp lệ ở bước RCPT, nhưng chưa có message được gửi theo đường đi này.

Ví dụ:

~~~text
To: Alice, Bob, Carol
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250

sendpartial=false
-> SMTP transport không gửi DATA cho message này
-> Lần gửi này thất bại cho toàn bộ message
~~~

Kết luận thận trọng: nếu nguyên nhân đúng là từ chối một recipient tại giai đoạn RCPT trong provider có hành vi trên, không nên gắn nhãn “Alice đã nhận email” chỉ vì `RCPT TO` được chấp nhận. Phải kiểm tra dữ liệu exception và hành vi transport thực tế.

### 3.2. Bật sendpartial=true

Ví dụ:

~~~properties
mail.smtp.sendpartial=true
~~~

Trong chế độ này, SMTP transport hỗ trợ có thể gửi message cho **những recipient được chấp nhận**, ngay cả khi các recipient khác bị từ chối.

~~~text
To: Alice, Bob, Carol
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250

sendpartial=true
-> DATA được gửi cho nhóm được chấp nhận
-> Transport báo partial failure
-> Alice/Carol: reported valid-sent nếu DATA đã được chấp nhận
-> Bob: không được gửi qua lần submission này
~~~

Điều dễ gây nhầm: **partial send có thể vừa thành công cho một nhóm, vừa ném exception cho cả lời gọi gửi**. Không được suy luận “method ném exception ⇒ không ai được gửi”.

### 3.3. Bảng so sánh

| Khía cạnh | `sendpartial=false` | `sendpartial=true` |
| --- | --- | --- |
| Một recipient bị từ chối ở RCPT | Thường dừng việc nộp nội dung cho cả message | Có thể gửi cho các recipient còn được chấp nhận |
| Recipient từng `250` ở RCPT | Có thể hợp lệ nhưng chưa gửi | Có thể nằm trong nhóm được nộp message |
| Lời gọi Java | Báo lỗi | Vẫn có thể báo lỗi dù một phần đã gửi |
| Nguy cơ khi retry cả danh sách | Có thể gửi lại sau khi sửa đối tượng nhận, nhưng phải xác định kết quả cũ | **Rất cao** nếu đã có nhóm thành công |
| Trạng thái vận hành | Message-level failure thường rõ hơn | Cần recipient-level outcome |
| Use case phù hợp | Muốn tránh gửi nếu danh sách có lỗi trước DATA | Muốn gửi tối đa cho nhóm hợp lệ và theo dõi từng địa chỉ |

Không nên bật `sendpartial=true` như một “cách sửa lỗi”. Đây là **quyết định về semantics của ứng dụng**: một thông điệp có được phép chỉ đến một phần danh sách hay không.

## 4. Cấu hình Spring Boot cho partial send

Khi dùng Spring Boot và Jakarta Mail SMTP provider hỗ trợ thuộc tính, có thể cấu hình qua `spring.mail.properties`:

~~~yaml
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
      "[mail.smtp.sendpartial]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

`mail.smtp.sendpartial` là thuộc tính của SMTP provider; không phải phương thức của `MimeMessageHelper`. Default và chi tiết thực thi có thể tùy thư viện Jakarta Mail/provider, vì vậy cần kiểm tra đúng implementation và version đang triển khai.

Nếu không muốn xử lý giao một phần, giữ chế độ mặc định hoặc cấu hình rõ:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.sendpartial]": false
~~~

### 4.1. Không nhầm sendpartial với reportsuccess

Một số SMTP provider có thuộc tính `mail.smtp.reportsuccess` để báo chi tiết cả các địa chỉ được chấp nhận. Khi bật, thư viện có thể tạo các exception kiểu báo thành công cho từng địa chỉ và làm lời gọi ném `SendFailedException` ngay cả khi mọi recipient được nộp thành công theo cơ chế của provider.

Vì vậy:

- Không bật `mail.smtp.reportsuccess` chỉ để “ghi log cho nhiều hơn” nếu chưa thiết kế xử lý exception tương ứng.
- Không coi mọi exception trong chuỗi nguyên nhân đều là recipient thất bại.
- Phân biệt provider-specific success report với `SMTPAddressFailedException`.
- Ghi rõ cấu hình thực tế khi chẩn đoán một kết quả gửi có vẻ mâu thuẫn.

### 4.2. Chỉ tác động tới SMTP transaction đang gửi

Thuộc tính `sendpartial` không:

- tự kiểm tra mailbox có tồn tại trước khi gửi;
- tự tạo retry job;
- tự xóa recipient lỗi khỏi database;
- tự bảo đảm delivery tới inbox;
- tự làm cho message idempotent;
- tự lưu trạng thái từng recipient cho lần thử kế tiếp.

Ứng dụng vẫn cần logic phân loại và lưu kết quả ở tầng nghiệp vụ.

## 5. Các exception liên quan trong Spring Mail và Jakarta Mail

Khi gọi:

~~~java
mailSender.send(mimeMessage);
~~~

Spring có thể ném `MailException` (một runtime exception). Trường hợp lỗi gửi có thể xuất hiện dưới dạng `MailSendException`. Exception tầng dưới từ Jakarta Mail/provider có thể chứa dữ liệu chi tiết về những địa chỉ được gửi hoặc bị từ chối.

Các kiểu quan trọng:

| API / exception | Vai trò |
| --- | --- |
| `org.springframework.mail.MailException` | Base exception ở Spring Mail |
| `org.springframework.mail.MailSendException` | Lỗi gửi, có thể chứa lỗi theo từng message |
| `MailSendException.getFailedMessages()` | Map từ message gửi lỗi sang exception tương ứng |
| `jakarta.mail.SendFailedException` | Lỗi gửi có thể cung cấp tập địa chỉ valid-sent, valid-unsent và invalid |
| `jakarta.mail.MessagingException` | Base exception Jakarta Mail, hỗ trợ chuỗi `getNextException()` |
| `SMTPAddressFailedException` của SMTP provider | Có thể chứa recipient, lệnh và mã SMTP bị từ chối |
| `SMTPSendFailedException` của SMTP provider | Có thể chứa lỗi giao dịch gửi tại cấp SMTP |

Tên package của lớp SMTP provider-specific có thể khác giữa thế hệ JavaMail và Jakarta Mail/Angus Mail. Ví dụ có các lớp dưới package kiểu `com.sun.mail.smtp` hoặc `org.eclipse.angus.mail.smtp`, tùy version. Vì vậy, ưu tiên xử lý ở tầng API chuẩn `SendFailedException` rồi chỉ dùng lớp provider-specific khi cần mã SMTP chi tiết.

### 5.1. MailSendException có thể bọc nhiều lỗi

`JavaMailSender` có overload gửi nhiều message:

~~~java
mailSender.send(message1, message2, message3);
~~~

Nếu một số message lỗi, `MailSendException.getFailedMessages()` chứa lỗi theo **message object**. Đây là tầng khác với nhiều **recipient** bên trong một message.

Hai loại “partial”:

1. **Một batch nhiều message:** message A gửi được nhưng message B lỗi.
2. **Một message nhiều recipient:** trong message B, Alice được chấp nhận nhưng Bob bị từ chối.

Không được đồng nhất hai lớp kết quả. Đầu tiên chọn đúng message trong `getFailedMessages()`, sau đó phân tích recipient trong exception của message ấy.

### 5.2. Ba tập địa chỉ từ SendFailedException

`jakarta.mail.SendFailedException` cung cấp:

~~~java
Address[] getValidSentAddresses();
Address[] getValidUnsentAddresses();
Address[] getInvalidAddresses();
~~~

Ý nghĩa khái quát:

| Tập địa chỉ | Cách hiểu thận trọng |
| --- | --- |
| `validSentAddresses` | Provider báo địa chỉ hợp lệ và đã được gửi trong lần submission |
| `validUnsentAddresses` | Provider báo địa chỉ hợp lệ nhưng **không được gửi** trong lần này |
| `invalidAddresses` | Provider báo địa chỉ không được chấp nhận/không hợp lệ trong ngữ cảnh gửi |

Cần lưu ý:

- Một mảng có thể là `null`, không đồng nghĩa “đã gửi”.
- Provider/version/loại lỗi có thể chỉ trả một phần thông tin.
- `invalidAddresses` không tự chứng minh lỗi là **vĩnh viễn**; để quyết định retry cần mã SMTP và loại lỗi.
- `validSentAddresses` nói về kết quả submission được báo, **không phải Inbox delivery**.
- Các tập có thể cần được đối chiếu với danh sách recipient ban đầu; không đoán trạng thái cho địa chỉ không được báo cáo.

### 5.3. Exception chain có nhiều tầng

Spring exception có thể bọc Jakarta Mail exception qua `getCause()`; ngoài ra `MessagingException` còn có `getNextException()`. Đôi khi thông tin địa chỉ nằm ở exception bên trong chứ không phải exception ngoài cùng.

Một cây ví dụ:

~~~text
MailSendException
  |
  +-- failedMessages[MimeMessage]
        |
        +-- SendFailedException
              |
              +-- SMTPAddressFailedException (Bob, 550, RCPT TO)
              +-- SMTPAddressFailedException (Carol, 450, RCPT TO)
~~~

Không giả định toàn bộ exception chain luôn có hình dạng này. Dữ liệu thực tế phụ thuộc provider, loại lỗi và thời điểm sự cố.

## 6. Ví dụ gửi một email tới nhiều recipient

Để minh họa, dùng `MimeMessageHelper`:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendAnnouncement(JavaMailSender sender)
        throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            false,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("notifications@example.com");
    helper.setTo(new String[] {
            "alice@example.net",
            "bob@example.net"
    });
    helper.setCc("carol@example.net");
    helper.setSubject("Thông báo bảo trì hệ thống");
    helper.setText(
            "Hệ thống sẽ bảo trì theo lịch đã công bố."
    );

    sender.send(message);
}
~~~

`setTo` và `setCc` tạo recipient metadata trong message. Khi gửi, transport quyết định envelope recipient list phù hợp. Nếu Bob bị từ chối ở `RCPT TO` nhưng Alice và Carol được chấp nhận, kết quả thực tế phụ thuộc `mail.smtp.sendpartial` và phản hồi tiếp theo của server.

**Không tự sửa danh sách nhận ngay khi bắt một exception tổng quát.** Hãy đọc dữ liệu recipient từ nguyên nhân SMTP và lưu trạng thái theo đúng đơn vị gửi mà ứng dụng đã định nghĩa.

### 6.1. To/Cc/Bcc không phải ba giao dịch SMTP độc lập

Trong một `MimeMessage`, các địa chỉ To/Cc/Bcc thường cùng tham gia một SMTP submission với những lệnh `RCPT TO` tương ứng. Một lỗi ở Bcc cũng có thể ảnh hưởng kết quả gửi cho To nếu transport đang ở chế độ all-or-nothing.

Ngược lại, bật partial send không tự biến việc gửi cho mỗi To/Cc/Bcc thành một job độc lập có retry riêng. Để có trạng thái và chính sách khác nhau theo recipient, ứng dụng cần tự quản lý danh sách recipient ở tầng job.

## 7. Đọc lỗi recipient một cách có cấu trúc

Một cách chẩn đoán trong Java là:

1. Bắt `MailSendException` khi lời gọi gửi lỗi.
2. Lấy lỗi của đúng `MimeMessage` từ `getFailedMessages()`.
3. Duyệt `cause` và `MessagingException.getNextException()`.
4. Tìm `SendFailedException` để lấy các tập địa chỉ.
5. Nếu provider hỗ trợ, tìm exception chứa mã SMTP cụ thể.
6. Ghi lại recipient-level outcome; các recipient không xác định phải được đánh dấu **UNKNOWN**, không tự coi là đã gửi hoặc chưa gửi.

### 7.1. Hàm duyệt chuỗi exception

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;

public final class MailExceptionInspector {
    private MailExceptionInspector() {
    }

    public static List<SendFailedException> findRecipientReports(
            Throwable error) {
        if (error == null) {
            return List.of();
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        List<SendFailedException> reports = new ArrayList<>();
        queue.add(error);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!visited.add(current)) {
                continue;
            }
            if (current instanceof SendFailedException report) {
                reports.add(report);
            }

            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }

            if (current instanceof MessagingException messaging) {
                Exception next = messaging.getNextException();
                if (next != null) {
                    queue.addLast(next);
                }
            }
        }
        return List.copyOf(reports);
    }
}
~~~

Hàm này chỉ **trích xuất báo cáo**, chưa tự diễn giải và gửi lại. Nó duyệt cả cause chain lẫn Jakarta Mail next-exception chain, dùng tập `visited` theo identity để tránh lặp hoặc vòng tham chiếu.

### 7.2. Trích xuất danh sách địa chỉ

~~~java
import java.util.Arrays;
import java.util.List;
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

static List<String> addresses(Address[] values) {
    if (values == null) {
        return List.of();
    }
    return Arrays.stream(values)
            .map(Address::toString)
            .toList();
}

static void inspectReport(SendFailedException report) {
    List<String> sent = addresses(
            report.getValidSentAddresses());
    List<String> unsent = addresses(
            report.getValidUnsentAddresses());
    List<String> invalid = addresses(
            report.getInvalidAddresses());

    // Chỉ minh họa dữ liệu chẩn đoán.
    // Production nên log ID/đếm thay vì địa chỉ cá nhân thô.
    System.out.println("valid-sent count: " + sent.size());
    System.out.println("valid-unsent count: " + unsent.size());
    System.out.println("invalid count: " + invalid.size());
}
~~~

Nếu có nhiều báo cáo nested, không nên cộng số lượng một cách máy móc vì cùng địa chỉ có thể được báo ở các tầng exception khác nhau. Phải hợp nhất theo recipient identity và hiểu semantics của provider. Khi các báo cáo có vẻ mâu thuẫn hoặc thiếu địa chỉ, đánh dấu cần điều tra thay vì ra quyết định gửi lại tự động.

### 7.3. Lấy nguyên nhân từ MailSendException

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;

try {
    sender.send(message);
} catch (MailSendException ex) {
    Exception messageFailure =
            ex.getFailedMessages().get(message);

    if (messageFailure != null) {
        var reports = MailExceptionInspector
                .findRecipientReports(messageFailure);

        for (var report : reports) {
            inspectReport(report);
        }
    } else {
        // Không có báo cáo recipient-level đáng tin cậy
        // cho message này: ghi UNKNOWN và điều tra.
    }

    throw ex; // Không biến một lỗi partial thành kết quả thành công giả.
}
~~~

Ví dụ giả định `message` là đúng object `MimeMessage` được truyền cho sender. Với batch nhiều message, duyệt từng entry trong `getFailedMessages()` và liên kết với job/recipient tương ứng.

### 7.4. Vì sao không chỉ bắt MessagingException?

`JavaMailSender.send(...)` khai báo lỗi ở tầng Spring bằng `MailException`; không giống lời gọi trực tiếp Jakarta Mail API thường dùng `MessagingException`.

Không nên viết:

~~~java
try {
    sender.send(message);
} catch (MessagingException ex) { // Không phải lỗi chính của JavaMailSender.send
    // ...
}
~~~

Khối bắt này có thể không phù hợp chữ ký method/cách exception được Spring chuyển đổi. Trong code gọi `MimeMessageHelper`, `MessagingException` có thể xuất hiện ở giai đoạn **chuẩn bị MIME**; trong code gọi `JavaMailSender.send`, xử lý `MailException`/`MailSendException` ở tầng Spring.

## 8. Đọc mã SMTP ở mức provider-specific

`SendFailedException` chuẩn cho biết các nhóm địa chỉ nhưng không cung cấp đầy đủ thông tin về mọi phản hồi `RCPT TO`. Provider SMTP có thể cung cấp class riêng, ví dụ `SMTPAddressFailedException`, với những method kiểu:

~~~java
getAddress();      // Địa chỉ liên quan.
getCommand();      // Lệnh SMTP, thường là RCPT TO.
getReturnCode();   // Mã 3 chữ số, ví dụ 450 hoặc 550.
~~~

Tên package phụ thuộc provider. Khi dùng Angus Mail trong một phiên bản phù hợp, có thể có:

~~~java
import org.eclipse.angus.mail.smtp.SMTPAddressFailedException;

void inspectProviderError(Throwable cause) {
    if (cause instanceof SMTPAddressFailedException smtpError) {
        int code = smtpError.getReturnCode();
        String command = smtpError.getCommand();
        String address = smtpError.getAddress().toString();

        // Chuyển code + command thành chẩn đoán,
        // không log trực tiếp address trong production.
    }
}
~~~

Đây là **minh họa phụ thuộc Angus Mail**: chỉ dùng import này nếu dependency thực tế có class đó. Với thế hệ JavaMail khác, package có thể khác. Không đặt dependency vào provider-specific API chỉ để xử lý những lỗi mà `SendFailedException` chuẩn đã biểu diễn đủ.

### 8.1. Cần biết phản hồi ở giai đoạn nào

Ví dụ:

~~~text
RCPT TO Bob -> 550 5.1.1 User unknown
~~~

đây là lỗi theo recipient.

Nhưng:

~~~text
DATA -> 552 5.3.4 Message size exceeds fixed maximum message size
~~~

có thể là lỗi toàn message sau khi các lệnh `RCPT TO` trước đó đã được chấp nhận. Không nên lấy `552` ở giai đoạn DATA rồi kết luận một người nhận cụ thể bị từ chối vì mailbox full.

Tương tự, lỗi `MAIL FROM`, xác thực hoặc TLS thường ảnh hưởng toàn bộ submission, không chỉ một recipient.

## 9. Thiết kế trạng thái theo recipient

Nếu sản phẩm cho phép gửi một phần, cần lưu trạng thái **từng recipient**, không chỉ một boolean `emailSent` cho cả danh sách.

Ví dụ:

~~~text
Mail job: job-752
Message key: maintenance-2026-11-12:group-7

Recipient                 Status
------------------------------------------------
alice@example.net         SUBMITTED
bob@example.net           REJECTED_PERMANENT
carol@example.net         RETRY_WAIT
audit@example.net         SUBMITTED
~~~

Để vận hành, trạng thái có thể có:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PENDING` | Chưa thử gửi |
| `PROCESSING` | Worker đang thực hiện attempt |
| `SUBMITTED` | Provider/transport báo nộp message thành công cho recipient |
| `RETRY_WAIT` | Chưa gửi, có lỗi tạm thời và chờ retry |
| `REJECTED_PERMANENT` | Từ chối dứt khoát theo kết quả đáng tin cậy |
| `INVALID_INPUT` | Địa chỉ sai/không hợp lệ ở tầng ứng dụng |
| `UNKNOWN` | Không xác định chắc đã được chấp nhận hay chưa |
| `FAILED_FINAL` | Kết thúc attempts theo chính sách |
| `BOUNCED` | Provider báo delivery thất bại sau submission |

`BOUNCED` là sự kiện có thể xuất hiện **sau** `SUBMITTED`, không nhất thiết là kết quả ngay tại `send(...)`.

### 9.1. Một schema tham khảo

~~~sql
CREATE TABLE mail_delivery_job (
    id              VARCHAR(64) PRIMARY KEY,
    message_key     VARCHAR(160) NOT NULL UNIQUE,
    subject_key     VARCHAR(120) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

CREATE TABLE mail_recipient_delivery (
    id                  VARCHAR(64) PRIMARY KEY,
    mail_job_id         VARCHAR(64) NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    recipient_role      VARCHAR(10) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    last_smtp_code      INTEGER,
    last_enhanced_code  VARCHAR(20),
    next_attempt_at     TIMESTAMP,
    submitted_at        TIMESTAMP,
    last_error_at       TIMESTAMP,
    FOREIGN KEY (mail_job_id) REFERENCES mail_delivery_job(id),
    UNIQUE (mail_job_id, recipient_address, recipient_role)
);
~~~

Đây là schema minh họa. Nếu sản phẩm cho phép một địa chỉ xuất hiện ở nhiều vai trò To/Cc/Bcc trong cùng job, phải có quy tắc xử lý trùng địa chỉ và scope uniqueness phù hợp. Cột `recipient_address` là dữ liệu cá nhân; cần kiểm soát truy cập, mã hóa/retention theo chính sách.

### 9.2. Tách logical request khỏi attempt

Một message key thường nhận diện một yêu cầu gửi. Nhưng mỗi lần retry có thể chứa **tập recipient khác nhau**. Không nên dùng attempt ID làm message key.

~~~text
Logical mail job:
  messageKey = announcement:group-7:version-1

Attempt 1 recipients:
  Alice, Bob, Carol

Attempt 2 recipients:
  Carol

Attempt 3 recipients:
  Carol (nếu attempt 2 vẫn chưa rõ kết quả)
~~~

Trong mô hình này, recipient-level status và attempt history là dữ liệu cần thiết để quyết định nhóm nào được gửi lại.

## 10. Retry chính xác phần chưa gửi

Giả sử provider báo:

~~~text
Alice: valid-sent
Bob:   invalid (550 5.1.1)
Carol: invalid/unsent (450 4.2.2)
~~~

Nếu partial send đã nộp email cho Alice, việc gọi lại:

~~~java
helper.setTo(new String[] {
        "alice@example.net",
        "bob@example.net",
        "carol@example.net"
});
sender.send(message);
~~~

có thể khiến Alice nhận email lần thứ hai. Đó là cách retry **không an toàn**.

Thay vào đó, chính sách lý tưởng:

1. Ghi Alice = `SUBMITTED` theo kết quả được báo đáng tin cậy.
2. Ghi Bob = `REJECTED_PERMANENT` nếu mã SMTP thực sự cho thấy lỗi vĩnh viễn của recipient.
3. Ghi Carol = `RETRY_WAIT` nếu mã cho thấy lỗi tạm thời và provider xác nhận chưa gửi.
4. Tạo attempt mới chỉ cho Carol.
5. Không tự retry những địa chỉ có trạng thái `UNKNOWN` mà chưa xác định được chính sách rủi ro gửi trùng.

### 10.1. Mã 4xx không phải luôn retry ngay

Một phản hồi tạm thời có thể là:

~~~text
450 4.2.2 Mailbox full
451 4.7.1 Temporarily deferred
~~~

Nên dùng backoff và giới hạn số lần thử:

~~~text
Attempt 1: ngay lúc tạo job
Attempt 2: sau một khoảng chờ
Attempt 3: khoảng chờ dài hơn
Attempt 4: retry cuối hoặc chuyển FAILED_FINAL
~~~

Có thể dùng exponential backoff với jitter, giới hạn tổng số attempts và thời gian sống của thông báo. Với email chứa mã OTP hoặc link hết hạn, không retry sau khi nội dung mất giá trị nghiệp vụ.

### 10.2. Mã 5xx cần kiểm tra nguyên nhân

Nếu server trả:

~~~text
550 5.1.1 User unknown
~~~

thường không nên retry địa chỉ đó vô hạn với cùng nội dung. Nhưng một mã 5xx khác, như `5.7.1`, có thể liên quan domain policy, permission hoặc relay configuration chứ không phải người dùng nhập sai email.

Do đó:

- Không tự động xóa tài khoản khách hàng chỉ vì một RCPT TO bị từ chối.
- Không tự thay đổi địa chỉ người nhận từ text phản hồi server.
- Cần phân loại lý do trước khi đánh dấu permanent failure.
- Nếu lỗi liên quan cấu hình sender/provider, xử lý ở tầng vận hành.

### 10.3. Trạng thái UNKNOWN là một kết quả hợp lệ

Nếu kết nối bị cắt sau khi nội dung đã được truyền nhưng trước khi ứng dụng nhận phản hồi xác nhận, có thể không biết SMTP server đã nhận message hay chưa.

~~~text
Client sends DATA bytes
SMTP server may accept
Network connection lost
JavaMailSender throws exception
~~~

Trong tình huống này, retry có thể tạo duplicate. Không được tự suy ra `NOT_SENT` chỉ vì có exception. Đối với email quan trọng, có thể cần tra cứu provider event hoặc chính sách retry chấp nhận khả năng gửi trùng.

## 11. Cách tốt nhất khi cần kiểm soát riêng từng recipient

Nếu mỗi recipient cần nhận nội dung cá nhân hóa hoặc cần retry độc lập, cân nhắc **mỗi recipient là một message/job riêng** thay vì gửi một MIME message cho danh sách lớn.

### 11.1. Một email cho nhiều recipient

Ưu điểm:

- ít SMTP submissions hơn;
- đơn giản khi gửi cùng một nội dung cho nhóm nhỏ;
- phù hợp với thư trao đổi có nhiều To/Cc.

Nhược điểm:

- một lỗi recipient có thể tác động các recipient khác;
- partial outcome phức tạp;
- khó retry theo người nhận;
- các địa chỉ To/Cc có thể hiển thị cho nhau;
- khó cá nhân hóa nội dung và tracking.

### 11.2. Một email cho một recipient

Ưu điểm:

- kết quả thường dễ phân loại theo từng job;
- retry không cần dựng lại danh sách người nhận;
- tránh vô tình tiết lộ danh sách người nhận;
- dễ cá nhân hóa ngôn ngữ, tên, token và template.

Nhược điểm:

- số lần gửi và chi phí vận hành có thể tăng;
- cần queue, rate limit và chính sách provider phù hợp;
- không phù hợp nếu mục đích là một cuộc trao đổi chung mà mọi người phải thấy cùng một To/Cc.

### 11.3. Bảng quyết định

| Nhu cầu | Hướng thiết kế thường phù hợp |
| --- | --- |
| Email giao dịch cho từng khách hàng | Một job/message cho từng recipient |
| Email OTP hoặc reset password | Một message cho một recipient |
| Thông báo cá nhân hóa hàng loạt | Fan-out thành các job độc lập |
| Email trao đổi nội bộ có nhiều To/Cc | Có thể dùng một message nhiều recipient |
| Cần biết chính xác recipient nào retry | Job/recipient state chi tiết hoặc một message/recipient |
| Không muốn một recipient lỗi làm chặn tất cả | Cân nhắc partial send hoặc tách message |
| Provider có HTTP API per-recipient status | Có thể tích hợp API riêng theo contract provider |

Không có phương án luôn đúng. Cấu trúc nhận phải khớp với semantics của sản phẩm và chính sách riêng tư.

## 12. Header recipient và SMTP envelope không hoàn toàn giống nhau

Khi tạo:

~~~text
To: alice@example.net, bob@example.net
Cc: carol@example.net
~~~

đây là header giúp email client hiển thị người nhận. SMTP envelope quyết định địa chỉ được router chuyển tới.

Nếu `sendpartial=true` và Bob bị từ chối, email gửi cho Alice vẫn có thể giữ header:

~~~text
To: alice@example.net, bob@example.net
~~~

Mặc dù Bob **không** nhận message ở lần gửi đó. Thư viện không nhất thiết xóa địa chỉ bị từ chối khỏi header của phần nội dung đã gửi.

Hệ quả:

- Người nhận có thể nhìn thấy tên/địa chỉ của recipient không được gửi.
- Một hệ thống downstream không nên suy ra từ header rằng mọi người đã nhận mail.
- Nếu retry chỉ cho Bob, phải quyết định header hiển thị của message retry theo chính sách nghiệp vụ.

### 12.1. Bcc cần được bảo vệ

`Bcc` thường không được đưa vào header hiển thị của bản message gửi đến người nhận, nhưng vẫn tham gia envelope delivery. Khi tự dựng MIME hoặc thao tác retry, không được vô tình đưa danh sách Bcc vào To/Cc hoặc vào log công khai.

Khi gửi email hàng loạt cho khách hàng không có quan hệ với nhau, **một message/recipient** thường dễ bảo vệ riêng tư hơn cố gắng gom mọi người vào To/Cc.

## 13. Thiết kế cơ chế idempotency cho retry partial

Một recipient bị lỗi có thể được retry nhiều lần do queue redelivery hoặc worker crash. Cần phân biệt:

- **Message key:** định danh yêu cầu gửi logic.
- **Recipient key:** định danh một người nhận trong yêu cầu.
- **Attempt ID:** định danh một lần thử SMTP.

Ví dụ:

~~~text
messageKey = maintenance-2026-11-12:group-7

recipientKey[alice] = <messageKey>:user-101
recipientKey[bob]   = <messageKey>:user-102
recipientKey[carol] = <messageKey>:user-103

attempt 1: Alice/Bob/Carol
attempt 2: Carol
~~~

Giữ cùng message key và recipient key trong mọi attempt. Database unique constraint trên `(message_key, recipient_key)` giúp không tạo nhiều recipient job logic từ việc event được phát lại.

### 13.1. Outbox và trạng thái bền vững

Đối với email quan trọng:

1. Ghi một outbox job và các recipient trong cùng transaction nghiệp vụ.
2. Worker claim job hoặc subset recipient đủ điều kiện.
3. Gửi SMTP bên ngoài database transaction giữ lock.
4. Phân tích partial result theo các recipient trong attempt.
5. Cập nhật trạng thái cho từng recipient trong transaction riêng.
6. Retry những recipient đủ điều kiện, giữ nguyên identity.

Ghi trạng thái recipient nên dùng transaction để tránh mất/ghi đè kết quả giữa worker khác nhau. Nếu có nhiều worker, cần lease/locking/version để ngăn xử lý song song cùng recipient.

### 13.2. Vẫn có cửa sổ gửi trùng

Kịch bản:

~~~text
T1 Worker gửi cho Alice
T2 SMTP chấp nhận
T3 Worker crash trước khi DB cập nhật Alice = SUBMITTED
T4 Job được nhận lại sau lease timeout
T5 Alice có thể bị gửi lần nữa
~~~

Unique key không thể làm SMTP và database thành một transaction nguyên tử. Để giảm duplicate:

- dùng API provider có idempotency key nếu được hỗ trợ;
- ghi provider message ID khi có;
- quản lý lease và kết quả UNKNOWN;
- chọn chính sách retry theo rủi ro nghiệp vụ;
- thiết kế nội dung có thể chịu duplicate nếu không thể tránh hoàn toàn.

## 14. Phân biệt synchronous rejection và bounce sau gửi

Một recipient có thể được SMTP server chấp nhận ở giai đoạn submission nhưng thư vẫn bị trả lại sau đó.

~~~text
Ứng dụng -> SMTP relay: 250 Message accepted
SMTP relay -> Server đích: Mailbox not found
SMTP relay -> Return-path: Delivery failure / bounce
~~~

Khi này:

- `JavaMailSender.send(...)` ban đầu có thể trả về bình thường.
- Không có `SendFailedException` ngay tại lần gửi.
- Delivery failure xuất hiện qua bounce, DSN, provider API hoặc webhook sau đó.

Đây **không** phải cùng hiện tượng với server từ chối `RCPT TO` đồng bộ.

| Loại thất bại | Thời điểm biết | Nguồn dữ liệu | Trạng thái |
| --- | --- | --- | --- |
| `RCPT TO` bị từ chối | Trong SMTP submission | SMTP exception / response | Rejected/Retry wait |
| `DATA` bị từ chối | Trong SMTP submission | Transport exception | Message-level failed/unknown |
| Bounce sau acceptance | Sau khi transport đã nộp | DSN/provider event | Bounced |
| Người dùng không mở thư | Không phải lỗi SMTP | Engagement event nếu có | Không suy luận từ send |

Không tự đổi `SUBMITTED` thành `DELIVERED` chỉ vì `send(...)` không ném lỗi.

## 15. Quy trình chẩn đoán khi production báo partial recipient rejection

Khi gặp báo cáo “gửi cho ba người, chỉ một người nhận được”, nên làm theo một quy trình có hệ thống.

### Bước 1 — Xác định đúng logical job và attempt

Ghi nhận:

~~~text
mailJobId
messageKey
attemptId
provider
smtpHost
configurationProfile
timestamp
~~~

Không bắt đầu bằng việc gửi lại ngay. Cần tránh gửi trùng cho recipient đã được chấp nhận.

### Bước 2 — Xem danh sách recipients dự kiến

Lấy danh sách địa chỉ **từ dữ liệu job đã chụp**, không chỉ dựa vào header To:

~~~text
To: Alice, Bob
Cc: Carol
Bcc: Audit
~~~

Kiểm tra có recipient trùng, địa chỉ sai cú pháp hoặc thay đổi danh sách giữa các attempts không.

### Bước 3 — Kiểm tra cấu hình transport

Xác định:

~~~text
mail.smtp.sendpartial
mail.smtp.reportsuccess
SMTP host/port
TLS/authentication
Provider implementation/version
~~~

Chỉ một thay đổi `sendpartial` cũng có thể làm cách Spring Mail báo kết quả khác đáng kể.

### Bước 4 — Xem exception chain

Đọc:

- Spring exception loại gì?
- `MailSendException.getFailedMessages()` chứa message nào?
- Có `SendFailedException` không?
- Các mảng `validSent`, `validUnsent`, `invalid` báo gì?
- Có `SMTPAddressFailedException` kèm address/code/command không?
- Lỗi xảy ra ở `RCPT TO` hay `DATA`?

Không dựa riêng vào message text như “Send failed”, vì thông tin đó không thể hiện đầy đủ partial outcome.

### Bước 5 — Đối chiếu với provider log

Nếu có SMTP relay/provider logs, tìm bằng thời gian, message/job ID hoặc provider ID tương ứng. Chú ý:

- provider có thể log recipient rejection riêng;
- log không nhất thiết có đầy đủ Bcc hoặc nội dung;
- không nên chia sẻ nguyên văn log chứa địa chỉ cá nhân, token hoặc thông tin xác thực.

Nếu không tìm được bằng chứng cho một recipient, giữ `UNKNOWN` thay vì tự gắn `NOT_SENT`.

### Bước 6 — Quyết định retry

| Kết quả đã xác minh | Hành động |
| --- | --- |
| Đã submitted | Không retry chỉ vì một recipient khác lỗi |
| Bị từ chối tạm thời, chắc chắn chưa gửi | Retry recipient đó với backoff |
| Bị từ chối vĩnh viễn | Báo lỗi/sửa dữ liệu hoặc policy |
| Chưa gửi vì all-or-nothing | Sau khi khắc phục nguyên nhân, có thể thử lại toàn message |
| Không xác định đã gửi chưa | Áp dụng chính sách xử lý UNKNOWN, cân nhắc duplicate risk |

### Bước 7 — Ghi nhận kết quả

Lưu recipient-level status, SMTP code, attempt ID và thời điểm. Không chỉ đánh dấu một cờ `sent = true/false` cho toàn job nhiều recipient.

## 16. Bảo mật và quyền riêng tư khi xử lý lỗi recipient

Exception của SMTP provider có thể chứa địa chỉ người nhận và phản hồi server. Log toàn bộ exception có thể làm lộ thông tin cá nhân.

Các nguyên tắc:

- Không log SMTP username/password, token hoặc raw authentication command.
- Không log toàn bộ email body/attachment để chẩn đoán recipient.
- Chỉ log recipient ID nội bộ hoặc địa chỉ được che/ẩn khi có thể.
- Giới hạn quyền truy cập logs và dữ liệu recipient status.
- Không đưa email address vào metric label có cardinality lớn.
- Không tự phân loại “người dùng không tồn tại” rồi hiển thị thông tin nhạy cảm cho caller chưa được xác thực.
- Nếu dùng `mail.debug` hoặc SMTP protocol trace trong môi trường test, bảo vệ logs và tắt khi không cần.

Ví dụ log vận hành:

~~~text
event=mail_partial_failure
mailJobId=job-752
attemptId=try-3
validSentCount=2
validUnsentCount=0
rejectedCount=2
temporaryRejectCount=1
permanentRejectCount=1
result=PARTIAL_SUBMISSION
~~~

Khi cần tra cứu một recipient cụ thể, dùng `recipientId` nội bộ thay vì email thô trong dashboard công khai.

## 17. Kiểm thử partial recipient failure

Khi xây module gửi mail, cần kiểm thử riêng ở cấp transport và cấp business retry policy.

### 17.1. Test một recipient bị từ chối với sendpartial=false

Giả lập SMTP server:

~~~text
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250
~~~

Kiểm tra:

- adapter báo lỗi đúng loại;
- message không bị ghi nhận là `SUBMITTED` cho mọi recipient;
- recipient từng `250` nhưng chưa nộp `DATA` được nhận diện là chưa gửi;
- retry policy không đánh dấu Alice thành delivered.

### 17.2. Test sendpartial=true

Với cùng kết quả `RCPT TO`:

- kiểm tra provider gửi `DATA` cho recipient được phép;
- lời gọi có thể ném exception chứa partial result;
- recipient valid-sent được ghi trạng thái submitted;
- recipient bị từ chối được ghi trạng thái phù hợp;
- lần retry sau không bao gồm nhóm valid-sent.

### 17.3. Test nhiều loại response

| Case | Mô phỏng | Kỳ vọng |
| --- | --- | --- |
| 1 | Tất cả `250`, DATA `250` | Submission không có lỗi đồng bộ |
| 2 | Một `550 5.1.1` | Chẩn đoán recipient permanent reject |
| 3 | Một `450 4.2.2` | Có thể retry recipient bị từ chối |
| 4 | Tất cả RCPT `250`, DATA `554` | Lỗi ở cấp message, không quy hết cho một recipient |
| 5 | Kết nối ngắt sau DATA | Kết quả unknown, không suy luận chắc chưa gửi |
| 6 | `reportsuccess=true` | Parser phân biệt success report và failure |
| 7 | Bcc bị từ chối | Không lộ địa chỉ Bcc trong To/Cc hoặc public logs |
| 8 | Batch nhiều MimeMessage | Không nhầm failed message với failed recipient |
| 9 | Worker retry sau partial | Giữ trạng thái và không gửi lại valid-sent |
| 10 | Provider bounce sau submit | Trạng thái được cập nhật bằng event riêng |

### 17.4. Mock JavaMailSender chưa đủ cho SMTP reply

Unit test có thể mock `JavaMailSender` để kiểm tra policy chuyển exception thành trạng thái. Nhưng một mock không tự kiểm tra cơ chế `RCPT TO`, `DATA` hoặc `mail.smtp.sendpartial` của provider.

Để kiểm tra behavior SMTP thực tế, dùng integration SMTP test server có khả năng cấu hình phản hồi khác nhau theo recipient hoặc một server test viết riêng. Một số mail catcher chỉ nhận mọi recipient nên không thích hợp để mô phỏng từng loại `RCPT TO` rejection nếu không có cơ chế tùy chỉnh.

Không dùng SMTP production để thử tạo lỗi bằng địa chỉ khách hàng thật.

### 17.5. Test race và crash window

Với job/recipient state bền vững, kiểm tra thêm:

- hai worker cùng claim một recipient;
- lease hết hạn khi worker vẫn đang gửi;
- SMTP accepted nhưng worker crash trước DB update;
- retry nhận lại same key, same recipient;
- provider từ chối một recipient sau khi job đã xử lý một phần;
- dữ liệu recipient status không bị lost update khi nhiều worker cập nhật.

Những test này nhằm kiểm tra logic idempotency và retry, không chỉ kỹ thuật gửi MIME.

## 18. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Catch `MailException` rồi xem tất cả recipient thất bại | Có thể retry cả nhóm đã gửi | Đọc partial report và lưu trạng thái từng recipient |
| Xem `250 RCPT TO` là đã delivered | Báo cáo sai và mất khả năng retry | Phân biệt RCPT, DATA và delivery |
| Bật `sendpartial=true` mà vẫn lưu một boolean `sent` | Không biểu diễn được thành công một phần | Recipient-level outcome |
| Mặc định `sendpartial=false` nhưng đánh dấu recipient `250` là đã gửi | Không gửi lại được phần đáng lẽ chưa gửi | Đọc `validUnsent` và kết quả DATA |
| Xem mọi địa chỉ `invalid` là vĩnh viễn | Bỏ qua lỗi tạm thời 4xx | Kết hợp SMTP code/command |
| Retry toàn danh sách sau partial send | Recipient đã gửi nhận mail trùng | Chỉ retry phần chưa gửi có đủ bằng chứng |
| Chỉ dựa vào `getCause()` | Bỏ qua `MessagingException.getNextException()` | Duyệt cả hai chuỗi |
| Nhầm `MailSendException.getFailedMessages()` với recipient list | Phân loại sai cấp message và recipient | Phân tách hai tầng kết quả |
| Luôn xem exception là chưa gửi ai | Không đúng khi partial enabled hoặc kết quả uncertain | Có trạng thái `UNKNOWN` |
| Dựa vào `To` header để xác định ai đã nhận | Header không phản ánh envelope/acceptance | Lưu recipients và transport outcome |
| Đưa Bcc vào retry To/Cc | Lộ danh sách recipient bí mật | Bảo toàn role, dùng message riêng khi cần |
| Bật `reportsuccess` mà parser coi mọi exception là lỗi | Báo sai submission | Phân biệt success report của provider |
| Xóa recipient bị từ chối khỏi tài khoản khách hàng | Có thể xóa do policy/reputation tạm thời | Phân loại và thực hiện quy trình vận hành |
| Đánh dấu `DELIVERED` ngay sau `send` | Không phản ánh bounce về sau | Dùng `SUBMITTED` và delivery event riêng |

## 19. Tình huống tổng hợp: gửi thông báo cho ba người

Một ứng dụng gửi thông báo bảo trì cho Alice, Bob và Carol. Cấu hình:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.sendpartial]": true
~~~

Kết quả SMTP:

~~~text
RCPT Alice -> 250 Accepted
RCPT Bob   -> 550 5.1.1 User unknown
RCPT Carol -> 450 4.2.2 Temporarily unavailable
DATA       -> 250 Message accepted for Alice
~~~

Theo báo cáo được xác minh từ provider:

~~~text
Alice = SUBMITTED
Bob   = REJECTED_PERMANENT
Carol = RETRY_WAIT
~~~

Ứng dụng ghi:

~~~text
mailJobId = job-752
messageKey = maintenance:2026-11-12:group-7
attemptCount = 1
status = PARTIAL_SUBMISSION
~~~

Sau khoảng backoff, worker tạo attempt thứ hai:

~~~text
Recipient list: Carol
Message key: vẫn là maintenance:2026-11-12:group-7
Attempt ID: mới
~~~

Alice không có trong lần gửi thứ hai, vì đã được báo submitted. Bob không được retry tự động vì có mã permanent reject. Carol là địa chỉ duy nhất đủ điều kiện retry. Nếu lần gửi thứ hai thành công, job có thể kết thúc với trạng thái tổng hợp như “2/3 submitted, 1/3 permanent reject”.

Nếu SMTP server phản hồi không rõ Alice đã nhận DATA chưa, ứng dụng **không thể kết luận chắc Alice đã được gửi**. Khi đó trạng thái phải phản ánh sự không chắc chắn, thay vì dùng cùng logic đơn giản của ví dụ trên.

### 19.1. So sánh khi sendpartial=false

Vẫn với cùng các mã `RCPT TO` nhưng `sendpartial=false`:

~~~text
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 450
Transport không nộp DATA cho message theo cấu hình all-or-nothing
~~~

Các recipient từng `250` không nên được ghi là delivered/submitted trong lần gửi này. Sau khi sửa danh sách hoặc áp dụng chính sách mới, ứng dụng có thể tạo attempt phù hợp. Sự khác biệt quan trọng là **kết quả được xác nhận ở giai đoạn DATA** và cách transport báo cáo valid-sent/valid-unsent, không phải chỉ số mã `250` trong các lệnh `RCPT TO`.

## 20. Checklist xử lý partial recipient rejection

Khi thiết kế hoặc điều tra:

1. **Xác định kiểu gửi:** một message nhiều recipient hay nhiều message độc lập?
2. **Xác định configuration:** `sendpartial` và `reportsuccess` hiện dùng là gì?
3. **Tách giai đoạn SMTP:** rejection ở `RCPT TO`, `DATA` hay bounce sau submission?
4. **Đọc exception đúng tầng:** Spring `MailSendException`, Jakarta `SendFailedException` và SMTP provider-specific exception.
5. **Đối chiếu ba tập địa chỉ:** valid-sent, valid-unsent, invalid, cùng danh sách recipient gốc.
6. **Không đánh đồng invalid với permanent:** cần mã SMTP 4xx/5xx và ngữ cảnh.
7. **Lưu trạng thái từng recipient:** submitted, retry wait, permanent reject hoặc unknown.
8. **Retry có chọn lọc:** không gửi lại recipient đã submitted theo bằng chứng đáng tin.
9. **Bảo vệ Bcc và dữ liệu cá nhân:** không vô tình lộ danh sách nhận trong header hoặc log.
10. **Phối hợp idempotency:** giữ message key và recipient identity ổn định qua retry.
11. **Không tuyên bố exactly-once:** crash window giữa SMTP và cập nhật database vẫn tồn tại.
12. **Kiểm thử với SMTP server mô phỏng rejection:** mock sender đơn thuần không đủ để kiểm tra hành vi giao thức.

## 21. Những điều cần nhớ

- SMTP phản hồi riêng cho từng `RCPT TO`, nên một message có thể gặp **recipient rejection từng phần**.
- `250` tại `RCPT TO` chỉ là chấp nhận recipient ở bước đó; submission còn phụ thuộc `DATA`.
- Với `mail.smtp.sendpartial=false`, provider thường dừng gửi nội dung nếu có recipient bị từ chối.
- Với `mail.smtp.sendpartial=true`, provider có thể gửi cho nhóm hợp lệ và **vẫn ném exception** để báo nhóm thất bại.
- `SendFailedException` có ba tập thông tin quan trọng: valid-sent, valid-unsent, invalid.
- `MailSendException.getFailedMessages()` là lỗi **theo message**, không trực tiếp là danh sách recipient thất bại.
- Để có mã lỗi cụ thể, có thể cần xem `SMTPAddressFailedException` và lệnh SMTP theo provider.
- **Không retry toàn bộ nhóm** nếu một phần đã được nộp thành công.
- Kết quả không xác định phải được ghi nhận là `UNKNOWN` khi chưa có bằng chứng rõ.
- Email đã `SUBMITTED` vẫn có thể bounce về sau; delivery là trạng thái khác.

Xử lý lỗi recipient bị từ chối từng phần không chỉ là bắt exception và gọi `send(...)` thêm lần nữa. Một hệ thống Spring Mail đáng tin cậy phải hiểu **recipient nào được nộp, recipient nào chưa gửi, recipient nào bị từ chối và kết quả nào vẫn chưa chắc chắn**. Khi tách đúng những trạng thái này, ứng dụng mới có thể retry an toàn, giảm email trùng và báo cáo trung thực kết quả gửi cho từng người nhận.

### Tài liệu tham khảo

- **RFC 5321 — Simple Mail Transfer Protocol:** `MAIL FROM`, `RCPT TO`, `DATA` và SMTP reply codes.
- **RFC 3463 — Enhanced Mail System Status Codes:** mã chi tiết cho địa chỉ, mailbox và policy.
- **Spring Framework Reference — Email:** `JavaMailSender` và `MimeMessageHelper`.
- **Spring Framework API — `MailSendException`:** xử lý lỗi gửi và `getFailedMessages()`.
- **Jakarta Mail API — `SendFailedException` / `MessagingException`:** valid-sent, valid-unsent, invalid addresses và next-exception chain.
- **Jakarta Mail/Angus Mail SMTP provider documentation:** `mail.smtp.sendpartial`, `mail.smtp.reportsuccess` và các lớp SMTP failure cụ thể.
