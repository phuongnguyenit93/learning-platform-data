# Kiểm thử nhiều người nhận và recipient bị lỗi

Gửi một email cho nhiều người nhận là trường hợp rất phổ biến trong ứng dụng Spring Framework Mail: thư có nhiều địa chỉ `To`, `Cc`, `Bcc`, hoặc một batch gồm nhiều `MimeMessage` khác nhau. Điểm khó nằm ở chỗ **một địa chỉ có thể được SMTP server chấp nhận trong khi địa chỉ khác bị từ chối**. Nếu test chỉ kiểm tra method `JavaMailSender.send(...)` có ném exception hay không, chúng ta không biết server đã nhận recipient nào, có nhận dữ liệu thư hay chưa, và việc gửi lại có gây trùng hay không.

**Kiểm thử tích hợp nhiều người nhận và recipient bị lỗi** phải quan sát cả **SMTP envelope và phản hồi tại lệnh `RCPT TO`**, không chỉ đọc header `To` của `MimeMessage`. Một SMTP test server có thể được lập trình trả `250` cho địa chỉ hợp lệ, `450` cho lỗi tạm thời và `550` cho địa chỉ bị từ chối. Bằng cách đó, test tái hiện được hành vi thực sự của Jakarta Mail transport và các exception được Spring Mail bọc lại.

Bài học trình bày quy trình test từ đơn giản đến chuyên sâu: tạo MIME message cho `To/Cc/Bcc`, phân biệt header và envelope, kiểm tra policy `mail.smtp.sendpartial`, đọc `MailSendException` và `SendFailedException`, xây SMTP server thử nghiệm có thể từ chối recipient theo kịch bản, và thiết kế retry không gửi trùng. Toàn bộ ví dụ dùng email thử và SMTP trên loopback, không gửi thư thật cho khách hàng.

## 1. Mục tiêu của bài kiểm thử tích hợp

Sau bài học, một bộ test tốt cần chứng minh được:

1. Ứng dụng thêm đúng các địa chỉ `To`, `Cc` và `Bcc` vào message.
2. SMTP transport cố gửi tới đúng tập recipient mong đợi qua các lệnh `RCPT TO`.
3. Server test có thể chấp nhận hoặc từ chối từng recipient bằng mã phản hồi được kiểm soát.
4. Khi có một recipient bị từ chối, ứng dụng thể hiện đúng hành vi theo `mail.smtp.sendpartial`.
5. Lỗi từ Jakarta Mail được quan sát và liên kết với `MailSendException`/`SendFailedException` khi phù hợp.
6. Ứng dụng không nhầm **một message thất bại** với **tất cả recipient đều thất bại**.
7. Tác vụ không tự động retry tới những người nhận có thể đã được server chấp nhận.
8. Không gọi trạng thái `DELIVERED` chỉ vì server SMTP test trả `250` sau `DATA`.

### Điều gì nằm ngoài phạm vi của test?

SMTP test server chỉ chứng minh ứng dụng tương tác với **server thử nghiệm** đúng kịch bản. Nó không bảo đảm Gmail, Microsoft 365 hoặc một provider production khác sẽ có cùng chính sách, cũng không chứng minh thư sẽ đến Inbox, không bị spam filter hay không bị bounce sau vài giờ.

## 2. Cần phân biệt message, recipient và SMTP envelope

Ba cấp độ thường bị trộn lẫn:

| Cấp độ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Notification** | `notificationId=N-100` | Một yêu cầu gửi do ứng dụng quản lý |
| **Message** | Một `MimeMessage` có `To: a, b` | Nội dung và header của một email |
| **SMTP recipient** | Hai lệnh `RCPT TO` cho `a` và `b` | Địa chỉ nhận theo SMTP envelope |

Một notification có thể sinh ra một message, nhưng một message vẫn có thể có nhiều người nhận. Một batch có thể chứa nhiều message, mỗi message lại có nhiều recipient. Vì thế, có ít nhất ba con số khác nhau:

- Số notification.
- Số `MimeMessage` được thử gửi.
- Số địa chỉ SMTP recipient được chấp nhận/từ chối.

Đừng dùng một counter `failedMessages.size()` để kết luận có bao nhiêu email address bị từ chối.

## 3. To, Cc, Bcc và địa chỉ nhận trên SMTP

Với Spring Mail:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo(new String[] {
        "primary-a@example.net",
        "primary-b@example.net"
});
helper.setCc("manager@example.net");
helper.setBcc("audit@example.net");
```

Ứng dụng xây thông tin người nhận trong `MimeMessage`. Khi transport gửi, Jakarta Mail dùng các địa chỉ tương ứng để tạo SMTP envelope `RCPT TO`.

Một phiên SMTP minh họa:

```text
S: 220 localhost ESMTP test server
C: EHLO application.test
S: 250-localhost
S: 250 SIZE 10000000
C: MAIL FROM:<notice@example.org>
S: 250 2.1.0 Sender OK
C: RCPT TO:<primary-a@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<primary-b@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<manager@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: [MIME message bytes]
C: .
S: 250 2.0.0 Message accepted for relay
```

Đây là phiên SMTP **giả lập**. Dòng `250 2.0.0` sau `DATA` chỉ có nghĩa server đó chấp nhận message để xử lý tiếp, không phải chứng nhận người nhận đã đọc thư.

### Tại sao cần test Bcc riêng?

`Bcc` là recipient của envelope nhưng không được phép hiển thị công khai như danh sách `To/Cc` trong bản thư người nhận nhìn thấy. Bài test nên tách:

- **Envelope test:** địa chỉ Bcc có được đưa vào `RCPT TO` hay không.
- **Recipient-visible header test:** dữ liệu mà mail client người nhận thấy có để lộ Bcc hay không.

Không suy ra hành vi SMTP chỉ từ `message.getRecipients(...)`, và không lấy `message.writeTo(...)` trước khi gửi làm bằng chứng cuối cùng rằng Bcc đã được loại khỏi dữ liệu nhận. Cần kiểm tra message mà SMTP test server nhận và/hoặc bước transport tương ứng.

## 4. Một recipient sai khác với một địa chỉ sai cú pháp

Có hai loại “recipient không hợp lệ”:

| Loại | Ví dụ | Thời điểm phát hiện |
| --- | --- | --- |
| Sai cú pháp | `not-an-email` hoặc địa chỉ không hợp lệ theo parser/validation | Có thể bị chặn khi dựng message |
| Đúng cú pháp nhưng server từ chối | `blocked@example.net` | Thường tại lệnh SMTP `RCPT TO` |

Để kiểm thử **recipient bị SMTP từ chối**, cần dùng địa chỉ **đúng cú pháp** nhưng được server test cấu hình trả mã lỗi. Nếu đưa địa chỉ sai cú pháp vào `MimeMessageHelper` và nó ném `AddressException` trước khi kết nối, bài test không kiểm tra hành vi từ chối của SMTP.

`InternetAddress.validate()` chỉ kiểm tra mức cú pháp; nó không thể xác nhận mailbox tồn tại hay provider sẽ nhận thư. Cũng không nên gửi tới một địa chỉ thật chỉ để xem nó bị bounce.

## 5. SMTP trả lời theo từng recipient như thế nào?

Các mã phản hồi thường gặp ở `RCPT TO`:

| Reply | Diễn giải khái quát | Chính sách test gợi ý |
| --- | --- | --- |
| `250 2.1.5` | Recipient được chấp nhận tại bước RCPT | Cho phép tiếp tục |
| `450 4.2.0` | Từ chối tạm thời | Ghi nhận lỗi có thể retry |
| `451 4.3.0` | Lỗi tạm thời của server | Kiểm tra backoff |
| `550 5.1.1` | Recipient bị từ chối rõ | Không retry mù cùng địa chỉ |
| `553` | Lỗi địa chỉ theo chính sách server | Kiểm tra nguyên nhân và dữ liệu |

Mã SMTP phụ thuộc server, lệnh và enhanced status code. Không biến bảng ví dụ thành quy tắc tuyệt đối cho mọi provider. Một số server trả `550` do chính sách relay, một số lại từ chối địa chỉ chỉ sau khi đã nhận message.

### Phân biệt RCPT TO với DATA

```text
MAIL FROM -> server biết sender
RCPT TO   -> server nhận hoặc từ chối mỗi recipient
DATA      -> client gửi MIME bytes nếu transport tiếp tục
250 DATA  -> server chấp nhận message ở phiên giao dịch ấy
```

Server trả `250` cho một `RCPT TO` chưa có nghĩa đã nhận nội dung. Nếu client không gửi `DATA`, recipient đó chưa được submit message thành công trong giao dịch này.

## 6. Hành vi mặc định khi có recipient bị từ chối

Jakarta Mail SMTP transport có thuộc tính `mail.smtp.sendpartial`. Khi nó là `false` (mặc định trong cấu hình phổ biến), nếu phát hiện một hoặc nhiều recipient không được chấp nhận, transport thường **không gửi phần DATA cho toàn message**; nó báo lỗi thay vì tiếp tục chỉ với tập recipient được chấp nhận.

Ví dụ:

```text
RCPT TO:<a@example.net>       -> 250
RCPT TO:<blocked@example.net> -> 550
RCPT TO:<c@example.net>       -> 250
                                      |
                                      v
                       sendpartial=false
                       Không gửi DATA cho message
                       Ném SendFailedException
```

Điều cần kiểm tra trong integration test là **server có nhận DATA hay không**, chứ không chỉ thấy lệnh `RCPT TO` nào được chấp nhận. Một recipient nhận `250` ở bước RCPT nhưng không có DATA vẫn chưa nhận nội dung message trong giao dịch đó.

### Test nào phù hợp?

Cho một message có:

- `accepted-a@example.net`: server trả `250`.
- `blocked@example.net`: server trả `550`.
- `accepted-c@example.net`: server trả `250`.

Với `sendpartial=false`, test kỳ vọng:

1. Server nhìn thấy lệnh RCPT cho các recipient theo transport behavior.
2. Có phản hồi từ chối `blocked@example.net`.
3. Server **không chấp nhận DATA** cho message đó.
4. JavaMailSender báo lỗi gửi.
5. Ứng dụng giữ được correlation để xử lý từng trường hợp.

Không khẳng định đã gửi thành công cho `accepted-a` chỉ vì nó có reply `250` ở bước RCPT.

## 7. Hành vi khi bật mail.smtp.sendpartial

Khi `mail.smtp.sendpartial=true`, Jakarta Mail SMTP transport có thể tiếp tục gửi message tới những recipient được server chấp nhận dù những địa chỉ khác bị từ chối. Sau đó, transport **vẫn có thể ném `SendFailedException`** để báo kết quả một phần.

```text
RCPT TO:<accepted-a@example.net> -> 250
RCPT TO:<blocked@example.net>    -> 550
RCPT TO:<accepted-c@example.net> -> 250
                                         |
                                         v
                            sendpartial=true
                            DATA -> 250 accepted
                            Ghi nhận partial failure
```

Điều này tạo khác biệt lớn trong retry:

- `accepted-a` và `accepted-c` đã được transport báo gửi thành công đến SMTP server trong giao dịch thử nghiệm.
- `blocked` bị từ chối ở RCPT.
- Gửi lại nguyên message tới cả ba có thể tạo bản sao cho các recipient đã được chấp nhận.

**Không suy diễn rằng sendpartial=true làm `send(...)` trả về thành công hoàn toàn.** Client vẫn cần quan sát exception và phân nhóm recipient.

## 8. Cấu hình JavaMailSenderImpl cho integration test

Ta có thể tạo sender trỏ về một SMTP server cục bộ tại port mà test cấp phát:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;

static JavaMailSenderImpl testSender(
        int smtpPort,
        boolean allowPartial
) {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(smtpPort);
    sender.setProtocol("smtp");
    sender.setDefaultEncoding("UTF-8");

    var properties = sender.getJavaMailProperties();
    properties.setProperty("mail.smtp.auth", "false");
    properties.setProperty(
            "mail.smtp.connectiontimeout", "3000");
    properties.setProperty("mail.smtp.timeout", "3000");
    properties.setProperty("mail.smtp.writetimeout", "3000");
    properties.setProperty(
            "mail.smtp.sendpartial",
            Boolean.toString(allowPartial));

    return sender;
}
```

Trong bài test này:

- Host `127.0.0.1` bảo đảm không gọi một SMTP production bất ngờ.
- Port được test server cấp phát động để giảm xung đột giữa các bài test.
- Không bật AUTH/TLS vì server thử nghiệm tối giản chưa hỗ trợ.
- Timeout hữu hạn giúp tránh test treo mãi khi protocol handler gặp sự cố.
- `sendpartial` được thiết lập tường minh trong từng scenario.

Test TLS, credential và SMTP AUTH cần một SMTP test server có hỗ trợ các tính năng đó; không được dùng fake server plaintext để kết luận bảo mật production đã đúng.

## 9. Tạo một message có nhiều To/Cc/Bcc

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

static MimeMessage buildMultiRecipientMessage(
        JavaMailSenderImpl sender
) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("notice@example.org");
    helper.setTo(new String[] {
            "accepted-a@example.net",
            "blocked@example.net"
    });
    helper.setCc("accepted-c@example.net");
    helper.setBcc("private-copy@example.net");
    helper.setSubject("Thông báo kiểm thử recipient");
    helper.setText(
            "Đây là thư kiểm thử nội bộ, không gửi ra Internet.",
            false
    );

    return message;
}
```

Với thông báo không có attachment, `multipart=false` vẫn đủ cho test recipient. Việc kiểm tra envelope `RCPT TO` không phụ thuộc email là text đơn hay `multipart/alternative`. Nên bắt đầu bằng text đơn để cô lập vấn đề recipient; sau đó mới thêm multipart nếu nghiệp vụ yêu cầu.

### setTo khác addTo

`helper.setTo(...)` đặt lại tập người nhận To, còn `helper.addTo(...)` thêm địa chỉ. Nếu application build danh sách qua nhiều bước, hãy kiểm tra tập cuối cùng không thiếu hoặc lặp. Không giả định repeated `setTo` tự cộng dồn recipient.

## 10. Kiểm tra các recipient trong message trước khi gửi

Đọc thông tin trong message giúp xác minh composer trước khi transport chạy:

```java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;

static List<String> addresses(
        MimeMessage message,
        Message.RecipientType type
) throws MessagingException {
    Address[] result = message.getRecipients(type);
    if (result == null) {
        return List.of();
    }
    List<String> emails = new ArrayList<>();
    for (Address address : result) {
        emails.add(((InternetAddress) address)
                .getAddress()
                .toLowerCase(Locale.ROOT));
    }
    return emails;
}
```

Ví dụ assertion:

```java
assertEquals(
        Set.of("accepted-a@example.net", "blocked@example.net"),
        Set.copyOf(addresses(message, Message.RecipientType.TO))
);
assertEquals(
        List.of("accepted-c@example.net"),
        addresses(message, Message.RecipientType.CC)
);
assertEquals(
        List.of("private-copy@example.net"),
        addresses(message, Message.RecipientType.BCC)
);
```

Những assertion này kiểm tra việc **dựng MIME recipient fields**, không chứng minh server đã nhận các địa chỉ đó. Tiếp theo cần kiểm tra SMTP conversation bằng một server cục bộ.

## 11. Chọn SMTP test server cho từng mục đích

Không phải SMTP test server nào cũng dễ cấu hình để **từ chối một recipient cụ thể**:

| Công cụ/hướng tiếp cận | Điểm mạnh | Giới hạn cần biết |
| --- | --- | --- |
| **GreenMail** | SMTP test server trong JVM, lưu message đã nhận, hỗ trợ test gửi/nhận | Khả năng tạo reply `RCPT TO` tùy kịch bản/API; cần cấu hình phù hợp |
| **Mailpit / MailHog** | Bắt và xem email test rất tiện | Không mặc định là bộ mô phỏng mọi mã lỗi recipient |
| **Custom scripted SMTP server** | Quy định chính xác reply của từng lệnh `RCPT TO` | Chỉ là SMTP subset, không thay thế production provider |
| **Provider sandbox** | Gần với quy tắc của chính provider | Có thể không trả các tình huống chính xác/deterministic |
| **Mockito mock JavaMailSender** | Kiểm tra nhánh application exception nhanh | Không kiểm tra giao thức thực trên socket |

Để test nội dung email nhận được, GreenMail/Mailpit thường rất phù hợp. Để test **lỗi từng recipient và `sendpartial`**, một SMTP test server có thể chủ động trả `250`, `450`, `550` tại `RCPT TO` cho kết quả rõ và lặp lại được.

Trong các ví dụ tiếp theo, ta dùng một server Java tối giản trên `127.0.0.1`, được khởi tạo riêng cho từng test. Nó không xác thực, không TLS và không chuyển tiếp thư ra Internet.

## 12. Xây scripted SMTP server đơn giản cho integration test

Server sau triển khai phần giao thức tối thiểu cần cho test: banner, EHLO/HELO, MAIL FROM, RCPT TO, DATA, RSET và QUIT. Mỗi recipient có thể được gán mã phản hồi theo một `Map`; những recipient không có cấu hình riêng được chấp nhận.

### 12.1. Lớp server test

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class ScriptedSmtpServer implements AutoCloseable {

    private final ServerSocket listener;
    private final ExecutorService executor;
    private final Map<String, Integer> replies;
    private final List<String> observedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> acceptedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> rejectedRecipients =
            new CopyOnWriteArrayList<>();
    private final List<String> receivedMime =
            new CopyOnWriteArrayList<>();
    private final AtomicInteger dataAccepted = new AtomicInteger();
    private volatile IOException serverFailure;

    public ScriptedSmtpServer(Map<String, Integer> replies)
            throws IOException {

        this.replies = replies;
        this.listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress());

        this.executor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "test-smtp");
            t.setDaemon(true);
            return t;
        });
        executor.submit(this::serveOneConnection);
    }

    public int port() {
        return listener.getLocalPort();
    }

    public List<String> observedRecipients() {
        return List.copyOf(observedRecipients);
    }

    public List<String> acceptedRecipients() {
        return List.copyOf(acceptedRecipients);
    }

    public List<String> rejectedRecipients() {
        return List.copyOf(rejectedRecipients);
    }

    public int acceptedDataCount() {
        return dataAccepted.get();
    }

    public List<String> capturedMime() {
        return List.copyOf(receivedMime);
    }

    public IOException serverFailure() {
        return serverFailure;
    }

    private void serveOneConnection() {
        try (Socket client = listener.accept()) {
            client.setSoTimeout(5000);

            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            PrintWriter output = new PrintWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII),
                    true);

            output.print("220 localhost ESMTP test server\r\n");
            output.flush();

            String line;
            boolean readingData = false;
            int currentAccepted = 0;
            StringBuilder mime = new StringBuilder();

            while ((line = input.readLine()) != null) {
                if (readingData) {
                    if (".".equals(line)) {
                        receivedMime.add(mime.toString());
                        dataAccepted.incrementAndGet();
                        mime.setLength(0);
                        readingData = false;
                        currentAccepted = 0;
                        reply(output, "250 2.0.0 Message queued");
                    } else {
                        // Chỉ lưu fixture test; không dùng server này
                        // để nhận email thật có PII.
                        mime.append(line).append("\r\n");
                    }
                    continue;
                }

                String upper = line.toUpperCase(Locale.ROOT);

                if (upper.startsWith("EHLO ")) {
                    output.print("250-localhost\r\n");
                    output.print("250 SIZE 10000000\r\n");
                    output.flush();
                } else if (upper.startsWith("HELO ")) {
                    reply(output, "250 localhost");
                } else if (upper.startsWith("MAIL FROM:")) {
                    currentAccepted = 0;
                    reply(output, "250 2.1.0 Sender OK");
                } else if (upper.startsWith("RCPT TO:")) {
                    int start = line.indexOf('<');
                    int end = line.indexOf('>', start + 1);

                    String address = (start >= 0 && end > start)
                            ? line.substring(start + 1, end)
                            : line.substring(8).trim();

                    address = address.toLowerCase(Locale.ROOT);
                    observedRecipients.add(address);

                    int code = replies.getOrDefault(address, 250);
                    if (code == 250) {
                        acceptedRecipients.add(address);
                        currentAccepted++;
                        reply(output, "250 2.1.5 Recipient OK");
                    } else {
                        rejectedRecipients.add(address);
                        if (code >= 400 && code < 500) {
                            reply(output,
                                    code + " 4.2.0 Temporary rejection");
                        } else {
                            reply(output,
                                    code + " 5.1.1 Recipient rejected");
                        }
                    }
                } else if (upper.equals("DATA")) {
                    if (currentAccepted == 0) {
                        reply(output,
                                "554 5.5.1 No accepted recipient");
                    } else {
                        reply(output, "354 End data with <CRLF>.<CRLF>");
                        readingData = true;
                    }
                } else if (upper.equals("RSET")) {
                    currentAccepted = 0;
                    reply(output, "250 2.0.0 Reset");
                } else if (upper.equals("NOOP")) {
                    reply(output, "250 2.0.0 OK");
                } else if (upper.equals("QUIT")) {
                    reply(output, "221 2.0.0 Bye");
                    break;
                } else {
                    reply(output, "502 5.5.2 Command not supported");
                }
            }
        } catch (IOException ex) {
            // Nếu test đóng listener trong lúc chờ accept,
            // sự cố shutdown có thể là bình thường.
            if (!listener.isClosed()) {
                serverFailure = ex;
            }
        }
    }

    private static void reply(PrintWriter out, String response) {
        out.print(response);
        out.print("\r\n");
        out.flush();
    }

    @Override
    public void close() throws IOException {
        listener.close();
        executor.shutdownNow();
    }
}
```

### Server thử nghiệm trên làm được gì?

- Port ngẫu nhiên do OS cấp, giúp các test không phải dùng chung port cố định.
- Lắng nghe **một** SMTP connection; mỗi test khởi tạo một server riêng.
- Chấp nhận và từ chối recipient bằng mã reply cụ thể.
- Ghi các recipient transport đã thử ở `RCPT TO`.
- Phân biệt recipient được `250` ở RCPT với **DATA thực sự được chấp nhận**.
- Giữ bản MIME **chỉ của fixture giả** để test header nếu cần.
- Dùng timeout và tự đóng socket trong `try-with-resources`.

### Server này không làm được gì?

Nó không triển khai đầy đủ RFC SMTP, STARTTLS, AUTH, ESMTP extension, message size limit, queue thật, delivery hay bounce. Đặc biệt, `receivedMime` được dựng từ các dòng đọc qua charset ASCII nên **không phải byte-level capture chuẩn cho mọi thông điệp 8-bit**. Với test này ta chỉ dùng nội dung và địa chỉ giả; để kiểm tra binary fidelity/MIME encoding, dùng GreenMail hoặc SMTP capture server chuẩn.

Vì server chỉ nhận một connection và một transaction test đơn giản, đừng dùng nó trong production hoặc bài test đa phiên phức tạp. Có thể mở rộng thành server nhiều connection nếu cần kiểm tra connection pooling và concurrency, nhưng đó là một chủ đề khác.

## 13. Test 1: tất cả recipient được chấp nhận

Test tích hợp đầu tiên xác nhận `JavaMailSenderImpl` nói chuyện được với server trên socket và gửi DATA khi mọi recipient được `250`:

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

@Test
void submitsMessageWhenAllRecipientsAccepted() throws Exception {
    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(Map.of())) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        // Trong test này server mặc định trả 250 cho mọi RCPT.
        assertDoesNotThrow(() -> sender.send(message));

        assertEquals(1, smtp.acceptedDataCount());
        assertEquals(
                Set.of(
                        "accepted-a@example.net",
                        "blocked@example.net",
                        "accepted-c@example.net",
                        "private-copy@example.net"
                ),
                Set.copyOf(smtp.observedRecipients())
        );
        assertTrue(smtp.rejectedRecipients().isEmpty());
    }
}
```

Những điều test này chứng minh:

1. Spring Mail tạo được SMTP session tới server cục bộ.
2. Transport gửi đúng tập `RCPT TO` dự kiến.
3. Server nhận một lượt DATA và trả kết quả accepted.

Nó **không** chứng minh các email đã tới Inbox; server giả lập chỉ ghi nhận DATA vào bộ nhớ.

### Kiểm tra Bcc

Ở test này, `private-copy@example.net` xuất hiện trong `observedRecipients()`, chứng minh Bcc đã đi qua SMTP envelope. Nếu muốn xác nhận transport không đưa header Bcc vào message mà server nhận, hãy inspect `smtp.capturedMime()` trong môi trường test:

```java
String captured = smtp.capturedMime().get(0);

String headerBlock = captured.split("\\r?\\n\\r?\\n", 2)[0];

assertTrue(headerBlock.lines()
        .noneMatch(line ->
                line.regionMatches(true, 0, "Bcc:", 0, 4)));
```

 Test tách **phần header trước dòng trống** rồi kiểm tra không có dòng bắt đầu bằng `Bcc:` bất kể hoa/thường. Không tìm `"bcc:"` trên toàn body, vì body có thể tình cờ chứa văn bản ấy. Với message thật, không được log raw DATA chỉ để kiểm tra Bcc.

## 14. Test 2: một recipient bị 550, sendpartial=false

Giả sử `blocked@example.net` bị server trả `550` trong khi ba địa chỉ còn lại được `250`.

```java
import org.springframework.mail.MailSendException;

@Test
void rejectsWholeMessageWhenOneRecipientInvalidAndPartialOff()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 550))) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        MailSendException exception = assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(
                smtp.rejectedRecipients()
                        .contains("blocked@example.net")
        );

        assertEquals(
                0,
                smtp.acceptedDataCount(),
                "No DATA should be accepted with sendpartial=false"
        );

        assertFalse(
                exception.getFailedMessages().isEmpty(),
                "Spring should report the failed MimeMessage"
        );
    }
}
```

Đây là scenario trọng tâm: những recipient được `250` ở RCPT **không đồng nghĩa** message đã được gửi cho họ. Vì `sendpartial=false`, transport có thể từ chối gửi DATA cho toàn message sau khi phát hiện một recipient lỗi.

Điều kiện test được định nghĩa chặt: một connection, một message, server chủ động trả `550` ở RCPT, và Jakarta Mail SMTP transport đang dùng cấu hình mặc định không gửi một phần. Với behavior khác do phiên bản thư viện, test cần xem transcript và lý do trước khi điều chỉnh expectation.

### Đừng assert số accepted recipient bằng số message đã gửi

`smtp.acceptedRecipients().size()` đếm địa chỉ đã nhận `250` tại RCPT. `smtp.acceptedDataCount()` đếm lần server test nhận xong DATA. Đây là hai metric **khác đơn vị** và không được dùng thay cho nhau.

## 15. Test 3: một recipient bị 550, sendpartial=true

Khi cho phép partial send, message có thể được submit tới những recipient được chấp nhận, dù transport vẫn báo một hoặc nhiều địa chỉ lỗi.

```java
@Test
void submitsToAcceptedRecipientsWhenPartialEnabled()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 550))) {

        var sender = testSender(smtp.port(), true);
        var message = buildMultiRecipientMessage(sender);

        MailSendException failure = assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(smtp.rejectedRecipients()
                .contains("blocked@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("accepted-a@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("accepted-c@example.net"));
        assertTrue(smtp.acceptedRecipients()
                .contains("private-copy@example.net"));

        assertEquals(
                1,
                smtp.acceptedDataCount(),
                "Valid recipients should receive DATA submission"
        );

        assertFalse(failure.getFailedMessages().isEmpty());
    }
}
```

Đây là tình huống dễ tạo duplicate nhất. Caller thấy `MailSendException` nhưng SMTP test server đã trả `250` sau DATA. Nếu ứng dụng retry **nguyên message với toàn bộ recipient**, những người đã được chấp nhận có thể nhận thêm một bản sao.

Không dùng `sendpartial=true` như một cách “bỏ qua lỗi recipient”; đó là **lựa chọn chính sách gửi một phần** và làm phát sinh trách nhiệm theo dõi kết quả riêng cho mỗi recipient.

## 16. Test 4: recipient bị 450 (lỗi tạm thời)

Để phân biệt lỗi tạm thời với lỗi vĩnh viễn, scripted server có thể trả `450`:

```java
@Test
void recordsTemporaryRecipientRejection()
        throws Exception {

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(
                         Map.of("blocked@example.net", 450))) {

        var sender = testSender(smtp.port(), false);
        var message = buildMultiRecipientMessage(sender);

        assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertTrue(smtp.rejectedRecipients()
                .contains("blocked@example.net"));
        assertEquals(0, smtp.acceptedDataCount());
    }
}
```

Với `sendpartial=false`, test transport vẫn có thể không gửi DATA cho toàn message. Sự khác nhau giữa `450` và `550` nằm ở **nguyên nhân và chính sách xử lý sau lỗi**:

- `450` thông thường là ứng viên retry có giới hạn/backoff.
- `550` thường đòi hỏi sửa recipient, policy hoặc danh sách gửi.

Đừng test “450 tự retry” chỉ từ `JavaMailSenderImpl.send(...)` vì JavaMailSender không tự cung cấp toàn bộ workflow retry cho từng recipient. Retry logic phải thuộc application service, worker hoặc notification state machine và được test riêng.

## 17. Đọc MailSendException và lỗi recipient của Jakarta Mail

Khi `JavaMailSenderImpl` thực hiện SMTP transport, Spring Mail thường chuyển các lỗi liên quan gửi thành `MailSendException`. Với một `MimeMessage` có nhiều recipient, cần phân biệt:

- `MailSendException.getFailedMessages()`: map **message object -> exception**.
- `MailSendException.getMessageExceptions()`: các exception ở mức message.
- `jakarta.mail.SendFailedException`: có thể cung cấp thông tin recipient hợp lệ/không hợp lệ theo báo cáo transport.
- Exception SMTP cụ thể do implementation cung cấp: có thể mang reply code, lệnh SMTP hoặc địa chỉ lỗi.

**Một entry trong failed-message map không đại diện cho một recipient.** Một `MimeMessage` có bốn người nhận và một người bị từ chối vẫn có thể tạo **một** entry failed message.

### Ví dụ lấy map

```java
try {
    sender.send(message);
} catch (MailSendException ex) {
    Map<Object, Exception> failures =
            ex.getFailedMessages();

    for (Map.Entry<Object, Exception> failure :
            failures.entrySet()) {
        Object messageObject = failure.getKey();
        Exception cause = failure.getValue();

        // Tương quan messageObject với notificationId
        // rồi phân tích cause theo tầng Jakarta Mail.
    }

    if (failures.isEmpty()) {
        // Map rỗng KHÔNG chứng minh send thành công.
        // Có thể là lỗi transport chung hoặc không có
        // thông tin lỗi cho từng message.
    }
}
```

Nếu code chỉ viết `catch (MailSendException)` mà bỏ qua `MailAuthenticationException`, nó có thể không xử lý được lỗi xác thực. Ngoài ra, lỗi dựng MIME có thể phát sinh trước `send` dưới dạng `MessagingException` hoặc `MailPreparationException` tùy đường gọi.

## 18. SendFailedException và ba nhóm địa chỉ

`jakarta.mail.SendFailedException` có các API:

```java
Address[] invalid = error.getInvalidAddresses();
Address[] validSent = error.getValidSentAddresses();
Address[] validUnsent = error.getValidUnsentAddresses();
```

Diễn giải:

| Nhóm | Ý nghĩa tổng quát theo báo cáo transport |
| --- | --- |
| `invalidAddresses` | Những địa chỉ bị coi là không hợp lệ hoặc bị từ chối |
| `validSentAddresses` | Những địa chỉ mà transport báo đã gửi tới ở giai đoạn của lỗi |
| `validUnsentAddresses` | Những địa chỉ hợp lệ nhưng chưa được gửi |

**Cảnh báo:** mảng có thể `null` hoặc rỗng tùy lỗi/implementation; không mặc định mọi `SendFailedException` đều điền đầy đủ ba nhóm. `validSent` không chứng minh email đã tới Inbox, và `validUnsent` không đồng nghĩa địa chỉ sai cú pháp.

### Vì sao các nhóm thay đổi theo sendpartial?

Với `sendpartial=false`, một recipient bị từ chối có thể khiến transport không gửi DATA cho bất cứ ai. Những recipient được `250` tại RCPT có thể ở nhóm **validUnsent** do message chưa được submit.

Với `sendpartial=true`, transport có thể submit DATA cho nhóm được chấp nhận và báo những địa chỉ đó là **validSent**, trong khi địa chỉ bị từ chối nằm trong nhóm **invalid**. Hãy xác minh thông tin này qua server test và exception, thay vì hard-code giả định cho mọi provider.

## 19. Duyệt cause chain và MessagingException.nextException

Jakarta Mail có thể nối các lỗi qua:

- `Throwable.getCause()`.
- `MessagingException.getNextException()`.

Vì vậy, chỉ gọi `ex.getCause()` một lần có thể bỏ sót `SendFailedException` nằm sâu hơn.

Một utility dành cho test:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Queue;
import java.util.Set;

static List<Throwable> causesIncludingNext(Throwable root) {
    Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
    Queue<Throwable> pending = new ArrayDeque<>();
    List<Throwable> result = new ArrayList<>();
    pending.add(root);

    while (!pending.isEmpty()) {
        Throwable current = pending.remove();
        if (!seen.add(current)) {
            continue;
        }

        result.add(current);

        if (current.getCause() != null) {
            pending.add(current.getCause());
        }

        if (current instanceof MessagingException messaging) {
            Exception next = messaging.getNextException();
            if (next != null) {
                pending.add(next);
            }
        }
    }

    return result;
}

static List<SendFailedException> findRecipientFailures(
        Throwable root
) {
    List<SendFailedException> result = new ArrayList<>();
    for (Throwable error : causesIncludingNext(root)) {
        if (error instanceof SendFailedException sendFailure) {
            result.add(sendFailure);
        }
    }
    return result;
}
```

Utility sử dụng identity set để không đi vòng vô hạn khi cause/next exception liên kết phức tạp. Nó giúp tìm những lỗi có thông tin địa chỉ mà không phụ thuộc package exception riêng của một implementation.

Trong ứng dụng production, đừng log toàn bộ message và exception text chưa sanitize: nhiều lỗi SMTP mang recipient, host hoặc dữ liệu có thể nhạy cảm.

## 20. Assertion cho các nhóm recipient

Ví dụ chuyển `Address[]` sang tập địa chỉ, xử lý `null`:

```java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;

static Set<String> toAddressSet(Address[] addresses) {
    if (addresses == null) {
        return Set.of();
    }
    Set<String> result = new HashSet<>();
    for (Address address : addresses) {
        result.add(((InternetAddress) address)
                .getAddress()
                .toLowerCase(Locale.ROOT));
    }
    return result;
}
```

Kết hợp với test partial:

```java
MailSendException exception = assertThrows(
        MailSendException.class,
        () -> sender.send(message)
);

List<SendFailedException> reports =
        findRecipientFailures(exception);

assertFalse(reports.isEmpty());

Set<String> invalid = new HashSet<>();
Set<String> validSent = new HashSet<>();
Set<String> validUnsent = new HashSet<>();

for (SendFailedException report : reports) {
    invalid.addAll(
            toAddressSet(report.getInvalidAddresses()));
    validSent.addAll(
            toAddressSet(report.getValidSentAddresses()));
    validUnsent.addAll(
            toAddressSet(report.getValidUnsentAddresses()));
}

assertTrue(invalid.contains("blocked@example.net"));
```

Những assertion sâu hơn như `validSent` bằng đúng ba địa chỉ cần dựa vào kết quả đã kiểm chứng của Jakarta Mail implementation và kịch bản SMTP đang dùng. Nếu kết quả là một exception khác hoặc các mảng rỗng do transport không cung cấp đủ thông tin, test không nên đoán trạng thái recipient chỉ để cho pass.

### Test thêm tình huống không có recipient info

Không phải mọi `MailSendException` đều chứa `SendFailedException`, ví dụ lỗi kết nối trước SMTP handshake. Ứng dụng phải có nhánh xử lý khi `findRecipientFailures(ex)` trả danh sách rỗng. Không thay thế thông tin còn thiếu bằng “tất cả recipient đều đã gửi” hoặc “tất cả đều chắc chắn chưa gửi” nếu không có bằng chứng.

## 21. Test 5: tất cả recipient đều bị từ chối

Một kịch bản quan trọng là không recipient nào được `250`:

```java
@Test
void doesNotSendDataWhenEveryRecipientRejected()
        throws Exception {

    Map<String, Integer> replies = Map.of(
            "accepted-a@example.net", 550,
            "blocked@example.net", 550,
            "accepted-c@example.net", 550,
            "private-copy@example.net", 550
    );

    try (ScriptedSmtpServer smtp =
                 new ScriptedSmtpServer(replies)) {

        var sender = testSender(smtp.port(), true);
        var message = buildMultiRecipientMessage(sender);

        assertThrows(
                MailSendException.class,
                () -> sender.send(message)
        );

        assertEquals(0, smtp.acceptedRecipients().size());
        assertEquals(0, smtp.acceptedDataCount());
    }
}
```

Ngay cả khi `sendpartial=true`, không có recipient được chấp nhận thì không có nhóm hợp lệ để gửi DATA. Server test có thể giúp chứng minh transport không gửi nội dung khi tất cả RCPT bị từ chối.

## 22. Test 6: sender có nhiều MimeMessage khác nhau

Đừng nhầm **một message có nhiều recipient** với **một batch có nhiều message**:

```java
MimeMessage messageA = buildMessage(
        "a@example.net", "A");
MimeMessage messageB = buildMessage(
        "b@example.net", "B");
MimeMessage messageC = buildMessage(
        "c@example.net", "C");

mailSender.send(messageA, messageB, messageC);
```

Với một batch, `MailSendException.getFailedMessages()` có thể chứa các entry cho những **message object** bị lỗi. Một message thành công không nhất thiết có entry.

### Tương quan message với notification ID

```java
Map<Object, UUID> notificationIds =
        new IdentityHashMap<>();

notificationIds.put(messageA, notificationA.id());
notificationIds.put(messageB, notificationB.id());
notificationIds.put(messageC, notificationC.id());

try {
    mailSender.send(messageA, messageB, messageC);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        UUID id = notificationIds.get(entry.getKey());
        Exception cause = entry.getValue();

        recordFailure(id, cause.getClass().getSimpleName());
    }
}
```

`IdentityHashMap` chỉ phục vụ việc tương quan cùng object instance trong một lần gửi. Khi retry sau restart, định danh bền vững phải là `notificationId` được lưu trong database, không phải identity của một Java object.

### Tại sao cần SMTP test server nhiều transaction?

Một phiên `JavaMailSenderImpl.send(messageA, messageB, messageC)` có thể thực hiện nhiều lượt `MAIL FROM/RCPT TO/DATA` trên transport. Scripted server tối giản ở trên hỗ trợ nhiều transaction trong **một connection**, nhưng nếu implementation reconnect khi lỗi hoặc đóng connection giữa chừng thì server một connection là không đủ. Để test batch và recovery ở mức transport đa phiên, hãy dùng GreenMail hoặc mở rộng test harness hỗ trợ nhiều connection.

Không viết test batch chỉ assert số phần tử `getFailedMessages()` rồi cho rằng đã kiểm chứng được nội dung từng email. Cần quan sát số DATA, RCPT replies và notification outcomes.

## 23. Gửi một message cho từng recipient: ưu và nhược

Một cách tránh trạng thái partial phức tạp là mỗi notification chỉ chứa một recipient SMTP:

```text
Notification N1 -> MimeMessage -> recipient A
Notification N2 -> MimeMessage -> recipient B
Notification N3 -> MimeMessage -> recipient C
```

Ưu điểm:

- Dễ gắn trạng thái SMTP vào notification/recipient.
- Dễ retry riêng một địa chỉ.
- Ít nguy cơ vô tình gửi lại tới địa chỉ đã thành công.
- Giúp tránh lộ danh sách `To/Cc` của những người nhận không nên thấy nhau.

Nhược điểm:

- Nhiều message hơn, có thể tốn thêm chi phí hoặc tài nguyên provider.
- Nếu nội dung thực sự dành cho một nhóm người nhận chung, gửi riêng có thể làm thay đổi semantics `Reply All`.
- Cần quyết định cách lưu một event nghiệp vụ liên quan tới nhiều notification.

**Không có quy tắc bắt buộc mọi email phải gửi riêng.** Nhưng với thông báo cá nhân hóa hoặc cần retry chính xác từng recipient, mô hình một recipient/notification thường dễ vận hành hơn.

## 24. Kiểm thử Bcc và không làm lộ recipient

Khi gửi nhiều người nhận, quyền riêng tư là một yêu cầu nghiệp vụ quan trọng:

- `To`: người nhận chính có thể nhìn thấy.
- `Cc`: người nhận sao chép thường được hiển thị.
- `Bcc`: người nhận ẩn, không nên xuất hiện trong header hiển thị của bản gửi cho người khác.

Một integration test nên kiểm tra **cả hai mặt**:

```text
Bcc recipient có trong SMTP RCPT TO?
             |
             +-- Có: transport nhận đúng người nhận ẩn

Raw message nhận tại SMTP test server
             |
             +-- Không có Bcc: header trong dữ liệu được gửi
```

Test Bcc phải sử dụng fixture giả và server cục bộ, vì raw MIME có thể chứa dữ liệu riêng tư. Không log toàn bộ message production vào CI.

### Khi resend chỉ cho recipient lỗi

Nếu một message có `To: a, b` và `b` thất bại, gửi lại **cùng object message** mà không thay danh sách recipient có thể khiến `a` nhận trùng.

Với retry theo recipient, hãy tạo **message mới** từ dữ liệu notification, chọn lại envelope recipient và cân nhắc semantics của header:

- Không giữ To/Cc/Bcc của người không cần nhận trong lần retry nếu điều đó gây gửi trùng hoặc tiết lộ danh sách.
- Nếu cần giữ lịch sử nhóm người nhận, tách metadata nghiệp vụ khỏi header phát hành.
- Với thư cá nhân hóa, dùng một recipient duy nhất trong message là lựa chọn đơn giản.

Không “sửa nhanh” bằng cách thay `Bcc` thành `To` mà không đánh giá chính sách riêng tư.

## 25. Kiểm thử địa chỉ trùng và danh sách rỗng

Ngoài lỗi SMTP, ứng dụng nên test validation của danh sách người nhận:

| Trường hợp | Kỳ vọng tùy policy ứng dụng |
| --- | --- |
| Cùng địa chỉ xuất hiện hai lần trong To | Deduplicate hoặc báo validation error |
| Cùng địa chỉ có trong To và Cc | Quyết định cấp ưu tiên hiển thị |
| Cùng địa chỉ trong To và Bcc | Tránh vừa công khai vừa ẩn một người nhận |
| Danh sách recipient rỗng | Từ chối tạo notification/send |
| Chỉ có Bcc | Chấp nhận hay từ chối theo policy; kiểm tra transport |
| Chuỗi rỗng/null trong danh sách | Chuẩn hóa/validation có giải thích |
| Địa chỉ có display name Unicode | Parse/encode đúng và SMTP envelope chính xác |
| Một địa chỉ có chữ hoa/thường khác nhau | Không deduplicate bừa nếu policy không chắc |

### Tách business validation khỏi SMTP behavior

Đối với danh sách người nhận trùng, `MimeMessageHelper` không phải cơ chế tự động bảo đảm các yêu cầu nghiệp vụ của bạn. Có thể cần normalize/deduplicate trước khi tạo `MimeMessage`.

Địa chỉ email có nhiều quy tắc về phần local-part và domain. Không áp dụng quy tắc chuyển toàn bộ local-part sang lowercase như một chân lý mọi provider. Trong môi trường test với các địa chỉ giả cố định, có thể dùng lowercase để so sánh tập; trong production, normalization/deduplication phải dựa trên chính sách định nghĩa rõ.

## 26. Kịch bản quan trọng: DATA bị từ chối sau khi các RCPT được chấp nhận

Không phải mọi lỗi người nhận xảy ra ngay tại `RCPT TO`. Server có thể nhận tất cả recipient ở `RCPT TO` nhưng trả lỗi ở lệnh `DATA` hoặc phản hồi cuối sau nội dung:

```text
RCPT TO:<a@example.net> -> 250
RCPT TO:<b@example.net> -> 250
DATA                    -> 354
[MIME bytes + terminator]
                         <- 554 5.7.1 Message rejected
```

Ở đây:

- `RCPT TO` đã được chấp nhận ở giai đoạn trước.
- **Message submission cuối bị từ chối** tại DATA.
- Không thể đánh dấu hai recipient là `SUBMITTED` chỉ dựa trên các reply `250` ở RCPT.

Muốn test, mở rộng scripted SMTP server để cấu hình phản hồi cuối DATA. Trong nhánh nhận dấu `"."`, thay `250` cuối bằng `554` khi kịch bản yêu cầu. Assert:

1. Client đã gửi DATA.
2. Server trả `554` cuối.
3. Spring Mail báo lỗi.
4. Ứng dụng không ghi `SUBMITTED` cho message theo lần thử đó.
5. Chính sách retry căn cứ reply code và nguyên nhân, không dựa trên số RCPT được `250`.

Điều này khác với kịch bản `sendpartial=false`, nơi transport có thể **không bắt đầu DATA** khi một recipient bị từ chối.

## 27. Kịch bản timeout sau DATA: kết quả có thể không xác định

Một trường hợp khó hơn:

```text
Client                                  SMTP server
  |                                         |
  |-------- RCPT TO ----------------------->|
  |<------- 250 ----------------------------|
  |-------- DATA + MIME + "." ------------>|
  |                                         | xử lý message
  X  không nhận được phản hồi cuối           |
  |                                         |
  | MailSendException / timeout            |
```

Nếu server đã nhận message nhưng phản hồi `250` bị mất, client có thể coi gửi thất bại. Nếu gửi lại ngay cho các recipient đó, người nhận có thể thấy email trùng.

**MIME message có thể hoàn toàn hợp lệ; lỗi này thuộc kết quả SMTP transport.** Một integration test muốn mô phỏng phải làm cho test server chủ động ngắt kết nối hoặc không trả reply **sau khi đã đọc dấu kết thúc DATA**, rồi xác nhận application ghi trạng thái chưa xác định.

Không viết assertion “timeout nghĩa là chắc chắn server chưa nhận”. Với lỗi ở giai đoạn khác như không mở được TCP connection, mức độ chắc chắn có thể khác; cần phân loại theo giai đoạn giao thức.

### Trạng thái UNKNOWN

Ứng dụng có thể dùng:

- `PENDING`: notification chờ xử lý.
- `PROCESSING`: worker đang thử gửi.
- `SUBMITTED`: SMTP/provider đã chấp nhận theo bằng chứng ứng dụng nhận.
- `RETRY_WAIT`: lỗi phù hợp chính sách retry.
- `FAILED`: không gửi tiếp theo policy.
- `UNKNOWN`: không xác định được SMTP đã chấp nhận hay chưa.

Khi `UNKNOWN`, test phải xác nhận **không có retry mù**. Có thể reconcile thông qua provider event, log theo message/notification ID hoặc quy trình vận hành. SMTP thuần không cung cấp idempotency key chung cho mọi relay; header `Message-ID` không tự bảo đảm deduplicate.

## 28. Kiểm thử bounce sau khi SMTP chấp nhận

Một SMTP relay có thể trả `250` cho `RCPT TO` và `DATA` rồi sau đó mới phát hiện mailbox không tồn tại. Khi đó có thể phát sinh **bounce bất đồng bộ**.

```text
Application
     |
     +-- SMTP 250 after DATA --> SUBMITTED
     |
     v
Provider tries downstream delivery
     |
     +-- mailbox rejected --> BOUNCED event
```

Một bài test chỉ dùng scripted SMTP server ở lớp transport **không thể chứng minh** downstream bounce. Nếu ứng dụng nhận webhook hoặc DSN:

1. Test ứng dụng ghi `SUBMITTED` sau khi SMTP chấp nhận.
2. Mô phỏng provider callback/bounce cho recipient B.
3. Xác minh status của recipient B chuyển sang `BOUNCED`.
4. Xác minh không tự đặt recipient A thành `BOUNCED`.
5. Kiểm tra webhook authorization, deduplication và thứ tự event.

Không xóa hoặc đánh dấu sai recipient chỉ vì một email nhóm có người nhận downstream bounce. Với thông báo cá nhân hóa, lưu trạng thái per-recipient sẽ giúp việc này đơn giản hơn.

## 29. Test SMTP accepted không phải test delivered

Các khái niệm:

| Mốc | Bằng chứng có thể có | Tên trạng thái phù hợp |
| --- | --- | --- |
| Tạo notification | Database đã commit | `PENDING` |
| Worker lấy notification | Claim/lease | `PROCESSING` |
| Server trả `250` ở `RCPT TO` | Recipient được chấp nhận tại bước RCPT | Chưa được gọi là `SUBMITTED` |
| Server trả `250` cuối `DATA` | SMTP nhận message để xử lý tiếp | `SUBMITTED` |
| Provider phát event delivery | Provider báo giao tới server đích | `DELIVERED` nếu có semantics ấy |
| Provider phát bounce | Nỗ lực giao không thành công | `BOUNCED` |
| Mất reply cuối sau DATA | Không biết đã nhận message chưa | `UNKNOWN` |

Đặc biệt, `JavaMailSender.send(...)` trả về `void`. Method không ném exception không đồng nghĩa “người dùng đã đọc email”. Test nên dùng từ `submitted` thay vì `delivered` khi chỉ quan sát SMTP.

## 30. Một luồng quản lý kết quả theo recipient

Khi ứng dụng cho phép gửi một phần, một bảng tracking có thể gồm:

```text
notification_id
recipient_id
recipient_role       TO / CC / BCC
smtp_attempt
smtp_status          PENDING / PROCESSING / SUBMITTED /
                     RETRY_WAIT / FAILED / UNKNOWN
smtp_reply_code
last_attempt_at
next_attempt_at
```

Không nhất thiết lưu địa chỉ email thô trong mọi bảng/log; có thể tham chiếu recipient ID theo chính sách dữ liệu. Cần xác định rõ semantics của một message chung với nhiều recipient: `DATA` được gửi một lần tới tập recipient SMTP đã chấp nhận, nhưng trạng thái retry có thể khác nhau theo từng recipient.

### Ví dụ sau partial send

Giả sử một message có ba recipient và `sendpartial=true`:

| Recipient | RCPT | DATA | Trạng thái sau lần thử |
| --- | --- | --- | --- |
| A | `250` | `250` chung | `SUBMITTED` |
| B | `550` | Không nằm trong tập được nhận | `FAILED` theo policy |
| C | `250` | `250` chung | `SUBMITTED` |

Không được retry A và C chỉ vì Spring ném một `MailSendException` cho message có B bị từ chối. Nếu B được sửa địa chỉ hoặc yêu cầu gửi lại, tạo một **lần thử có tập recipient riêng**.

### Tránh hiểu nhầm một status cho toàn message

Một cột `message.status=FAILED` có thể làm mất thông tin rằng A và C đã được SMTP chấp nhận. Nếu hệ thống cần xử lý chính xác, hãy lưu kết quả theo recipient hoặc sử dụng một notification/recipient ngay từ đầu.

## 31. Retry 4xx cần backoff, không cần vòng lặp nóng

Ví dụ policy:

```text
Attempt 1: gửi lần đầu
Attempt 2: sau 30 giây
Attempt 3: sau 2 phút
Attempt 4: sau 10 phút
Attempt 5: sau 30 phút
```

Đây chỉ là lịch minh họa. Thực tế cần:

- Backoff theo loại lỗi.
- Jitter để tránh các worker retry cùng thời điểm.
- Giới hạn attempt và thời gian tối đa.
- Tôn trọng rate limit/quota/provider policy.
- Không retry `550` không thể khắc phục bằng chờ đợi.
- Không tự động retry khi outcome `UNKNOWN` nếu không đánh giá nguy cơ duplicate.

### Test retry scheduler

Không cần `Thread.sleep(...)` hàng phút trong test. Có thể đưa `Clock` hoặc một abstraction thời gian vào service rồi kiểm tra:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T08:00:00Z"),
        ZoneOffset.UTC
);

RetryDecision decision = retryPolicy.classify(
        SmtpFailure.temporary(450),
        2,
        fixedClock.instant()
);

assertEquals(RetryDecision.Kind.RETRY_WAIT,
        decision.kind());
assertTrue(decision.nextAttemptAt()
        .isAfter(fixedClock.instant()));
```

`RetryDecision`, `RetryPolicy` và `SmtpFailure` là **abstraction do ứng dụng tự xây**. Integration test của SMTP transport cung cấp bằng chứng về mã lỗi; unit test của retry policy xác minh trạng thái và thời điểm thử lại.

## 32. Không bật mail.smtp.reportsuccess tùy tiện

Jakarta Mail SMTP còn có một số thuộc tính có thể làm thay đổi thông tin exception. Một ví dụ là `mail.smtp.reportsuccess`, dùng để báo chi tiết recipient đã được chấp nhận và có thể dẫn tới các exception thành phần mang thông tin success, tùy implementation.

Nếu bật thuộc tính này trong test mà production không bật, kết quả exception và callback có thể khác. Nên:

1. Đặt tường minh các property SMTP quan trọng trong test.
2. Ghi nhận phiên bản Jakarta Mail/Angus Mail mà Spring Boot đang quản lý.
3. Kiểm tra các nhóm `SendFailedException` theo đúng cấu hình chạy thực.
4. Không xem sự có mặt của một exception class cụ thể là bảo đảm delivery.

Các class SMTP chuyên biệt có thể mang tên/package khác nhau giữa implementation. Chỉ phụ thuộc vào interface/exception Jakarta Mail chung khi phần mềm không cần kiểm tra chi tiết provider-specific; nếu cần reply code chính xác, hãy xác định library thực tế.

## 33. Tích hợp với Spring Boot và cấu hình test

Trong ứng dụng Spring Boot, cấu hình thực tế thường đến từ:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
```

**Đừng để integration test dùng nhầm các biến production.** Với test localhost, cấu hình cần override host/port và tắt AUTH/STARTTLS khi scripted server không hỗ trợ.

Một test `@SpringBootTest` có thể dùng `@DynamicPropertySource` để đưa port động vào Spring context:

```java
@DynamicPropertySource
static void mailProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.mail.host", () -> "127.0.0.1");
    registry.add("spring.mail.port", () -> smtp.port());
    registry.add("spring.mail.properties.mail.smtp.auth",
            () -> "false");
    registry.add("spring.mail.properties.mail.smtp.starttls.enable",
            () -> "false");
    registry.add("spring.mail.properties.mail.smtp.sendpartial",
            () -> "true");
}
```

Đây là đoạn minh họa phần property binding; `smtp` phải được khởi tạo **trước khi Spring context đọc property**, ví dụ qua lifecycle test extension hoặc static fixture được kiểm soát, và đóng sau test. Không đặt `@BeforeAll` quá muộn nếu context đã khởi tạo và truy cập `smtp.port()`.

Khi một class test thay `sendpartial` giữa các test, phải tránh tái sử dụng context/sender với cấu hình cũ một cách vô ý. Dùng test instance/config riêng hoặc tạo `JavaMailSenderImpl` cho từng scenario.

## 34. GreenMail cho trường hợp mọi recipient được chấp nhận

Với bài kiểm thử cần đọc chính MIME đã nhận, GreenMail là lựa chọn thuận tiện hơn một SMTP server tự viết. Một ví dụ khung:

```java
GreenMail greenMail = new GreenMail(
        new ServerSetup(0, "127.0.0.1", "smtp")
);

greenMail.start();
try {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(greenMail.getSmtp().getPort());

    MimeMessage mail = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mail, true, "UTF-8");
    helper.setFrom("test-sender@example.org");
    helper.setTo(new String[] {
            "first@example.net", "second@example.net"
    });
    helper.setText("Plain text", "<p>HTML test</p>");

    sender.send(mail);

    assertTrue(greenMail.waitForIncomingEmail(5000, 1));
    MimeMessage[] received = greenMail.getReceivedMessages();
    assertTrue(received.length >= 1);

    // Kiểm tra nội dung/recipient của message được nhận
    // theo API và semantics của GreenMail version đang dùng.
} finally {
    greenMail.stop();
}
```

Đây là ví dụ sử dụng API GreenMail phổ biến; cần thêm dependency test, import và điều chỉnh theo phiên bản thư viện thực tế. Với nhiều recipient, cách GreenMail lưu message theo mailbox và cách API `getReceivedMessages()` tổng hợp kết quả cần được xác nhận theo phiên bản đang dùng. Để assert chính xác từng mailbox, hãy dùng API lấy message của từng user nếu phù hợp; không đồng nhất số mailbox với số SMTP DATA transaction.

**Để kiểm tra từ chối từng RCPT**, dùng scripted SMTP server hoặc công cụ có khả năng cấu hình reply từ chối tương ứng. Đừng giả định một SMTP capture server luôn cho phép cấu hình `550` cho một địa chỉ cụ thể.

## 35. Viết assertion có ý nghĩa theo SMTP stage

Khi muốn xác minh kết quả integration test, nên biểu diễn rõ **loại sự kiện**:

| Dữ liệu quan sát được | Câu hỏi trả lời được |
| --- | --- |
| `observedRecipients()` | Transport đã gửi `RCPT TO` cho những địa chỉ nào? |
| `acceptedRecipients()` | Test server đã trả `250` cho những RCPT nào? |
| `rejectedRecipients()` | Test server đã trả `4xx/5xx` cho những RCPT nào? |
| `acceptedDataCount()` | Có bao nhiêu lần server test nhận DATA và trả accepted? |
| `MailSendException` | Spring sender có ghi nhận lỗi gửi? |
| `SendFailedException` address groups | Transport phân nhóm địa chỉ ra sao? |
| `capturedMime()` | Server test đã nhìn thấy MIME bytes/dòng gì trong DATA? |

**Một số assertion mẫu:**

```java
assertEquals(
        Set.of("accepted-a@example.net", "blocked@example.net"),
        Set.copyOf(addresses(
                message, Message.RecipientType.TO))
);

assertTrue(smtp.observedRecipients()
        .contains("blocked@example.net"));

assertTrue(smtp.rejectedRecipients()
        .contains("blocked@example.net"));

assertEquals(0, smtp.acceptedDataCount());
```

Đoạn này kiểm tra các lớp khác nhau: composer chứa đúng To, SMTP có cố thử recipient bị chặn, server đã từ chối, và **không có DATA được chấp nhận**. Đừng biến một assertion “có RCPT 250” thành “email delivered”.

## 36. Kiểm thử application xử lý một phần thành công

Ở tầng nghiệp vụ, một service có thể nhận kết quả transport rồi cập nhật notification/recipient state. Hãy test logic này với **trạng thái thực tế SMTP test tạo ra**, nhưng không tự đoán một mail send exception luôn có dữ liệu per-recipient đầy đủ.

Một policy minh họa:

```text
SMTP attempt
    |
    v
Lấy kết quả theo message + recipient khi có bằng chứng
    |
    +-- RCPT 550 chắc chắn -> FAILED / INVALID_RECIPIENT
    |
    +-- RCPT 450 chắc chắn -> RETRY_WAIT
    |
    +-- DATA 250 và recipient được nhận -> SUBMITTED
    |
    +-- Mất phản hồi cuối DATA -> UNKNOWN
    |
    +-- Không đủ thông tin -> REVIEW / UNKNOWN
```

Một bài test đầy đủ nên assert hai khía cạnh:

1. **Transport behavior:** SMTP test server đã nhận những lệnh và trả những mã nào.
2. **Application policy:** database/repository được cập nhật trạng thái nào, có lịch retry hay không và có loại khỏi lần thử tiếp theo những recipient đã submit.

Trong test theo tầng, có thể kiểm thử bước phân loại bằng đơn vị `RecipientSendOutcome` được tạo từ một adapter transport, sau đó integration test xác nhận adapter diễn giải đúng `SendFailedException`. Không cần gộp tất cả logic vào một method `catch` khổng lồ.

## 37. Ví dụ anti-pattern: retry nguyên message khi có một recipient lỗi

```java
try {
    sender.send(message);
} catch (MailSendException ex) {
    // Sai với sendpartial=true: những recipient hợp lệ
    // có thể đã được SMTP chấp nhận.
    sender.send(message);
}
```

Nếu lần đầu A và C đã được `250` sau DATA, lần thứ hai có thể gửi thêm bản sao tới A/C. Cách an toàn hơn:

1. Phân tích lỗi theo recipient khi có bằng chứng.
2. Ghi các recipient đã `SUBMITTED`.
3. Chỉ lên lịch retry cho recipient phù hợp.
4. Khi retry, tạo message/notification mới hoặc bản gửi có tập recipient chính xác.
5. Không retry tự động với kết quả `UNKNOWN` nếu không có policy kiểm soát duplicate.

### Không dùng Message-ID như khóa chống trùng

Giữ một header `Message-ID` ổn định có thể hữu ích cho correlation, nhưng SMTP không có yêu cầu chung phải deduplicate theo header này. Do đó, một message gửi hai lần với cùng `Message-ID` **vẫn có thể được nhận hai lần**.

Nếu provider có API idempotency key chính thức, sử dụng theo tài liệu và phạm vi của provider. SMTP thuần thường cần idempotency ở tầng nghiệp vụ kết hợp chính sách phục hồi.

## 38. Một message có nhiều recipient và một batch nhiều message: test riêng

Ví dụ hai luồng:

```text
Luồng A
-------
send(MimeMessage X)
  To: A, B
  Cc: C
  Bcc: D
  --> một SMTP message, nhiều RCPT

Luồng B
-------
send(MimeMessage X, MimeMessage Y, MimeMessage Z)
  X --> RCPT A
  Y --> RCPT B
  Z --> RCPT C
  --> nhiều SMTP message, mỗi cái có RCPT riêng
```

Khi ứng dụng gặp `MailSendException`:

- Luồng A cần biết kết quả theo recipient trong **một message**.
- Luồng B cần biết kết quả theo **message** và có thể tiếp tục xuống recipient.

Không dùng cùng một expectation cho cả hai loại batch. Ví dụ `getFailedMessages().size()==1` trong luồng A không có nghĩa chỉ một địa chỉ lỗi; nó chỉ có thể là một message object được báo lỗi.

## 39. Test lặp recipient qua To/Cc/Bcc

Một application gửi email cho nhiều người nên xác định chính sách trùng:

```text
To:  alice@example.net
Cc:  alice@example.net
Bcc: alice@example.net
```

Những câu hỏi cần trả lời:

1. Composer có cho phép cùng địa chỉ ở nhiều role không?
2. Nếu có, recipient có bị gửi nhiều lần hay transport tự xử lý trùng?
3. Role nào được hiển thị trong header khi địa chỉ xuất hiện ở To và Bcc?
4. Ứng dụng có cần dedup trước khi gọi helper không?

Không giao việc quyết định business policy cho SMTP provider. Viết test validation/composer xác nhận danh sách đã chuẩn hóa, rồi test transport với danh sách đó.

**Thận trọng về so sánh địa chỉ:** domain là case-insensitive theo DNS, nhưng local-part có ngữ nghĩa phức tạp tùy provider. Không áp dụng heuristic như xóa dấu chấm, bỏ `+tag` hoặc lowercase local-part cho mọi domain nếu chưa có chính sách.

## 40. Kiểm thử lỗi trước khi kết nối SMTP

Nếu ứng dụng truyền:

```text
recipient = "invalid address"
```

vào một API yêu cầu `InternetAddress` hợp lệ, lỗi cú pháp có thể xuất hiện trước khi mở SMTP connection. Đây là test **validation/message preparation**, không phải test `RCPT TO` bị từ chối.

Một suite nên có hai test khác nhau:

- **Invalid input:** bảo đảm địa chỉ không hợp lệ bị loại sớm, không phát sinh notification/send.
- **SMTP recipient rejection:** dùng `blocked@example.net` đúng cú pháp, server test trả `550`.

Nếu test không phân biệt, một lần fail tại `AddressException` có thể bị hiểu nhầm là sender đã xử lý đúng phản hồi server.

## 41. Test lỗi xác thực khác lỗi recipient

`MailAuthenticationException` thường là lỗi SMTP AUTH, ảnh hưởng việc đăng nhập trước khi gửi message. Nó không phải báo cáo per-recipient rejection.

Một bài kiểm thử nên phân loại:

| Lỗi | Giai đoạn | Chính sách |
| --- | --- | --- |
| Invalid address syntax | Build/validation | Sửa input, không gửi |
| Authentication failed | AUTH | Sửa credential/provider policy |
| Recipient 450 | RCPT TO | Retry có backoff |
| Recipient 550 | RCPT TO | Thường lỗi recipient/policy |
| Message 554 | DATA | Xem policy/nội dung |
| Timeout sau DATA | DATA outcome | `UNKNOWN`/reconciliation |

Không dùng một `catch (MailSendException)` để xử lý tất cả loại lỗi mail rồi retry mọi thứ theo cùng một cách. `MailPreparationException`, `MailAuthenticationException` và `MailSendException` có ý nghĩa khác nhau.

## 42. CI và tính xác định của test

Để một integration test SMTP chạy ổn định trên CI:

- Chỉ bind server vào `127.0.0.1` hoặc loopback.
- Dùng port ngẫu nhiên thay vì port cố định dễ trùng.
- Không đọc SMTP credential từ môi trường production.
- Đặt connect/read/write timeout hữu hạn.
- Đóng server và socket sau mỗi test.
- Không chia sẻ một `JavaMailSenderImpl` mutable giữa các scenario có `sendpartial` khác nhau.
- Đừng dựa vào thứ tự test hoặc `Thread.sleep` dài.
- Nếu chạy song song, mỗi test cần server/port và fixture riêng.
- Không log full MIME có địa chỉ hay token thật.
- Ghi rõ phiên bản Spring Mail/Jakarta Mail khi test kiểm tra exception-specific behavior.

### Tránh test phụ thuộc Internet

Không kiểm tra recipient lỗi bằng cách gửi mail đến địa chỉ không tồn tại trên Internet. Provider có thể chấp nhận ở RCPT rồi bounce sau, áp dụng rate limit hoặc đưa tài khoản test vào danh sách cảnh báo. Một SMTP server cục bộ có phản hồi xác định giúp test nhanh và không ảnh hưởng bên ngoài.

### Tránh chờ vô hạn

Server test nên có socket timeout. Nếu cần chờ sự kiện bất đồng bộ, dùng latch/future với timeout hữu hạn hoặc API wait của SMTP test framework. Không thêm `Thread.sleep(5000)` tùy ý rồi kỳ vọng server chắc chắn đã nhận.

## 43. Bảng test matrix đề xuất

| Mã | RCPT A | RCPT B | Partial | DATA | Kết quả cần quan sát |
| --- | --- | --- | --- | --- | --- |
| T01 | 250 | 250 | false | 250 | Không lỗi, DATA accepted |
| T02 | 250 | 550 | false | Không gửi | Message thất bại, không có DATA |
| T03 | 250 | 550 | true | 250 | Partial submit, có lỗi recipient |
| T04 | 250 | 450 | false | Không gửi | Lỗi recipient tạm thời, retry policy |
| T05 | 550 | 550 | true | Không gửi | Không recipient nào được chấp nhận |
| T06 | 250 | 250 | false | 554 | DATA bị server từ chối |
| T07 | 250 | 250 | true | Mất final reply | UNKNOWN, không retry mù |
| T08 | To/Cc/Bcc 250 | — | false | 250 | Đủ RCPT, Bcc không lộ trong header nhận |
| T09 | Một message | Một message lỗi khác | — | Theo message | Failed-message correlation trong batch |
| T10 | 250 rồi downstream bounce | — | false | 250 | SUBMITTED rồi BOUNCED qua event |

Đây là bảng kế hoạch kiểm thử, không phải tuyên bố mọi SMTP implementation có cùng outcome trong mọi tình huống. Từng test phải có server script, property transport và assertions tương ứng. Với lỗi final DATA không rõ, không áp đặt trạng thái “chắc chắn fail” khi không có reply.

## 44. Logging và bảo vệ dữ liệu trong test

Ngay cả với test, hãy dùng địa chỉ giả:

```text
accepted-a@example.net
blocked@example.net
private-copy@example.net
notice@example.org
```

Không lấy địa chỉ người dùng thật từ database production đưa vào test fixture hoặc console. Trong ứng dụng thật, log thường chỉ cần:

```text
notificationId=N-341-01
recipientId=R-02
recipientRole=BCC
smtpStage=RCPT_TO
smtpReplyCode=550
failureClass=SendFailedException
classification=PERMANENT_REJECTION
attempt=1
```

Tránh:

- Log nguyên `MimeMessage`, To/Cc/Bcc hoặc header tùy chỉnh.
- Đưa raw exception message từ SMTP vào metric label.
- Đưa subject/body hay attachment vào CI report.
- Lưu raw Bcc hoặc token trong screenshot test.

Một `MailSendException` có thể chứa thông tin địa chỉ trong nested exception; nếu phải lưu stack trace, áp dụng policy riêng cho dữ liệu diagnostic nhạy cảm.

## 45. Những lỗi thường gặp khi viết integration test

| Sai lầm | Tại sao sai? | Cách đúng |
| --- | --- | --- |
| Mock `JavaMailSender.send` rồi gọi là integration test | Không có SMTP giao thức | Dùng test server thật trên socket |
| Test sai cú pháp nhưng gọi là RCPT rejection | Lỗi xảy ra trước SMTP | Dùng địa chỉ đúng cú pháp, server trả 550 |
| Assert có `250` RCPT là đã gửi mail | Chưa có DATA | Kiểm tra final DATA reply |
| Cho rằng `sendpartial=true` không ném lỗi | Partial failure vẫn có thể ném exception | Kiểm tra cả exception và DATA |
| Cho rằng `sendpartial=false` gửi cho những RCPT đã nhận 250 | Transport có thể hủy toàn message | Xem DATA count |
| Dùng `failedMessages.size()` đếm recipient lỗi | Map theo message object | Dùng SendFailedException groups/SMTP evidence |
| Retry nguyên message sau partial | Gây duplicate cho recipient đã thành công | Retry riêng recipient phù hợp |
| Test gửi đến SMTP public | Thiếu kiểm soát, có side effect thật | Local scripted SMTP |
| Hard-code port 2525 cho mọi test | Dễ xung đột khi chạy song song | Ephemeral port |
| Dùng `Thread.sleep` để đợi server | Flaky do scheduling | Event/latch/timeouts |
| Coi 250 DATA là delivered | SMTP acceptance khác mailbox delivery | SUBMITTED; provider event riêng |
| Không test Bcc | Có thể lộ danh sách người nhận ẩn | Kiểm tra RCPT + header của test capture |
| Không test 4xx | Không phân biệt transient/permanent | Script 450 và 550 riêng |
| Bỏ qua outcome sau DATA timeout | Có thể gửi trùng | UNKNOWN/reconciliation |
| Bật `reportsuccess` mà không kiểm tra | Exception behavior thay đổi | Cấu hình test tường minh |

## 46. Checklist triển khai test nhiều recipient

### Chuẩn bị

- [ ] Test dùng SMTP localhost và địa chỉ giả.
- [ ] Có dữ liệu To, Cc, Bcc đại diện đủ các role.
- [ ] Có server script trả 250, 450 và 550 theo recipient.
- [ ] `mail.smtp.sendpartial` được chỉ định tường minh.
- [ ] Có timeout và cơ chế cleanup server.

### Kiểm tra transport

- [ ] Assert tập recipient quan sát ở `RCPT TO`.
- [ ] Assert recipient được server chấp nhận/từ chối.
- [ ] Assert có hay không có DATA, tùy scenario.
- [ ] Assert exception đúng mức message/transport.
- [ ] Không nhầm `RCPT 250` với `DATA 250`.

### Kiểm tra application

- [ ] Có correlation message/recipient/notification ID.
- [ ] Không retry nguyên batch nếu một phần đã thành công.
- [ ] Phân biệt 4xx, 5xx và outcome mơ hồ.
- [ ] Bcc không lộ trong message hiển thị.
- [ ] Có trạng thái `SUBMITTED`, `RETRY_WAIT`, `FAILED`, `UNKNOWN` phù hợp.
- [ ] Có kiểm thử bounce/delivery event riêng nếu ứng dụng hỗ trợ.

### Vận hành

- [ ] Test không gửi tới SMTP production.
- [ ] Không lưu dữ liệu người dùng thật trong CI.
- [ ] Không chờ vô hạn hoặc phụ thuộc thứ tự test.
- [ ] Không hard-code boundary, Message-ID hoặc giả định về provider không được test.
- [ ] Lỗi được báo bằng notification ID và stage rõ ràng.

## 47. Tình huống tự luyện

### Tình huống A — Một người nhận bị 550

Một message gửi cho A, B, C. A và C được `250`, B bị `550`. `sendpartial=false`.

**Câu hỏi:** A và C đã được submit chưa?

**Gợi ý:** chưa thể kết luận từ RCPT. Với behavior thông thường của transport khi partial off, không có DATA được gửi. Test phải assert final DATA count và exception.

### Tình huống B — Bật partial

Cùng danh sách trên nhưng `sendpartial=true`. Server trả `250` sau DATA; Spring ném `MailSendException`.

**Câu hỏi:** có thể gọi `sender.send(message)` lần nữa ngay không?

**Gợi ý:** không nên. A/C có thể nhận trùng. Cần correlation theo recipient, ghi trạng thái submitted, và chỉ xử lý B theo policy phù hợp.

### Tình huống C — Recipient sai cú pháp

Test truyền `"not-an-email"` vào `setTo` và nhận exception trước khi SMTP server thấy lệnh `RCPT TO`.

**Câu hỏi:** test này đã kiểm tra recipient rejection chưa?

**Gợi ý:** chưa. Đây là validation/parse test. Với SMTP rejection, dùng địa chỉ hợp cú pháp và script reply `550`.

### Tình huống D — Bcc đã xuất hiện ở RCPT

Server log có `RCPT TO:<audit@example.net>`, nhưng người nhận chính phàn nàn rằng danh sách Bcc bị lộ.

**Câu hỏi:** cần kiểm tra thêm gì?

**Gợi ý:** inspect headers của message test mà server nhận, không chỉ recipient envelope. Tránh dùng raw production mail để điều tra.

### Tình huống E — Server trả DATA 554

Mọi `RCPT TO` đều trả `250`, sau đó server từ chối message bằng `554` cuối DATA.

**Câu hỏi:** có được đánh dấu các recipient là submitted không?

**Gợi ý:** không. Phải phân loại lỗi ở DATA; RCPT acceptance chưa phải message submission.

### Tình huống F — Timeout sau DATA

Worker đã truyền toàn bộ MIME bytes nhưng không nhận phản hồi cuối.

**Câu hỏi:** nên dùng trạng thái nào?

**Gợi ý:** `UNKNOWN` nếu không có bằng chứng xác định; tránh retry mù và tìm provider event khi có.

### Tình huống G — Batch ba MimeMessage

Một exception chứa một failed-message entry cho message thứ hai.

**Câu hỏi:** đó có phải là một recipient lỗi không?

**Gợi ý:** không nhất thiết. Map theo message object; message đó có thể có nhiều recipient. Cần đọc nguyên nhân và correlation.

### Tình huống H — Recipient bị bounce sau nhiều giờ

SMTP test chứng minh message đã `SUBMITTED`. Provider phát bounce cho một recipient sau đó.

**Câu hỏi:** integration test cần làm gì?

**Gợi ý:** test webhook/event processing riêng để chuyển trạng thái recipient phù hợp; không thay đổi trạng thái các recipient khác nếu không có bằng chứng.

## 48. Kết luận

Kiểm thử nhiều người nhận và recipient bị lỗi trong Spring Framework Mail cần quan sát **giao thức SMTP**, chứ không chỉ kiểm tra các header `To/Cc/Bcc` hoặc nhìn vào một `MailSendException`. Khi một người nhận bị từ chối, `mail.smtp.sendpartial=false` thường khiến cả message không được gửi DATA; `sendpartial=true` có thể submit tới những recipient được chấp nhận nhưng vẫn báo lỗi một phần. Hai trường hợp này dẫn đến **chính sách retry hoàn toàn khác nhau**.

Một bộ integration test đáng tin cậy nên dùng SMTP test server cục bộ có reply `250/450/550` được lập trình theo recipient, kiểm tra tập `RCPT TO`, số lần nhận DATA, phân tích `SendFailedException` và ánh xạ message/recipient vào notification ID bền vững. Ngoài ra cần test Bcc, message batch, lỗi cuối DATA và tình huống timeout không rõ kết quả. Khi có partial success, **không retry nguyên message hoặc toàn batch một cách mù quáng**.

Cuối cùng, hãy giữ ranh giới giữa `RCPT TO` được chấp nhận, SMTP `DATA` được chấp nhận và thư thực sự được giao tới mailbox. Test SMTP cung cấp bằng chứng về **submission tại server thử nghiệm**; delivery, bounce và client rendering cần lớp kiểm thử khác. Cách tiếp cận này giúp ứng dụng gửi đúng người nhận, xử lý lỗi theo từng địa chỉ và giảm đáng kể nguy cơ gửi trùng hoặc báo sai kết quả gửi email.
