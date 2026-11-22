# MessagingException và nguyên nhân từ Jakarta Mail

Khi gửi email bằng Spring Framework Mail, một lỗi xuất hiện ở **MimeMessageHelper**, **Jakarta Mail**, transport SMTP hoặc kết nối mạng có thể được biểu diễn dưới nhiều lớp exception. Nếu chỉ nhìn vào thông báo ngoài cùng, người phát triển rất dễ kết luận sai: thấy **MailSendException** thì nghĩ “SMTP đã từ chối”, thấy **MessagingException** thì nghĩ “địa chỉ sai”, hoặc cứ có timeout là gửi lại ngay.

Thực tế, **jakarta.mail.MessagingException** là loại exception nền tảng của Jakarta Mail dành cho nhiều sự cố liên quan hệ thống mail. Nó không phải tên của một nguyên nhân duy nhất. Để chẩn đoán đúng, cần xem **exception subtype**, **chuỗi nguyên nhân**, **exception liên kết của Jakarta Mail**, **giai đoạn gửi** và, nếu có, **mã phản hồi SMTP**.

Ví dụ, cùng một thao tác gửi có thể thất bại vì:

- Không tạo được MIME part do tên attachment hoặc dữ liệu không phù hợp.
- Không kết nối được SMTP server.
- STARTTLS hoặc TLS handshake lỗi.
- Đăng nhập SMTP thất bại.
- Một hay nhiều địa chỉ người nhận bị từ chối.
- Message bị server từ chối ở giai đoạn DATA.
- Kết nối mất sau khi server có thể đã chấp nhận email.

Các tình huống đó không thể dùng chung một chính sách retry. Mục tiêu của bài học là hiểu **MessagingException và cách tìm nguyên nhân thực sự từ Jakarta Mail**, sau đó chuyển kết quả thành thông tin chẩn đoán và hành động phù hợp trong ứng dụng Spring.

## 1. Spring Mail và Jakarta Mail nằm ở đâu trong luồng gửi?

Một ứng dụng Spring thường làm việc với **JavaMailSender**, **MimeMessage** và **MimeMessageHelper**. Bên dưới, Spring sử dụng Jakarta Mail để dựng message và thực hiện transport.

~~~text
Application service
       |
       v
JavaMailSender / MimeMessageHelper
       |
       +-- Tạo MIME headers, body, attachment, inline resources
       |
       v
Jakarta Mail
       |
       +-- Session
       +-- Message / MimeMessage
       +-- Transport
       |
       v
SMTP provider / server
       |
       v
Remote mail infrastructure
~~~

Các lỗi có thể xuất hiện tại hai điểm lớn:

1. **Chuẩn bị message:** Jakarta Mail API được gọi để thiết lập header, body, multipart hoặc attachment. Một số phương thức khai báo **throws MessagingException**.
2. **Thực hiện gửi:** Spring JavaMailSender gọi transport. Các lỗi được Spring chuyển thành **MailException** hoặc subtype runtime thích hợp để ứng dụng xử lý.

Điểm quan trọng: **MessagingException không đồng nghĩa với MailException**. Chúng thuộc hai hệ phân cấp exception khác nhau.

### 1.1. Ví dụ phần chuẩn bị có checked exception

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("user@example.net");
helper.setSubject("Thông báo");
helper.setText("Xin chào!", false);
~~~

Các thao tác của MimeMessageHelper có thể khai báo **MessagingException**. Vì vậy, đoạn code nằm trong method phải bắt exception hoặc khai báo throws theo Java.

### 1.2. Ví dụ phần gửi có Spring runtime exception

~~~java
mailSender.send(message);
~~~

**JavaMailSender.send(...)** được khai báo theo API Spring Mail, thường phát sinh **MailException** hoặc subtype của nó nếu gửi thất bại. Các exception gốc từ Jakarta Mail có thể được giữ trong cause hoặc cấu trúc chi tiết đi kèm.

Do đó, cần phân biệt **lỗi dựng MIME** và **lỗi gửi mail** trước khi phân loại.

## 2. MessagingException là gì?

**jakarta.mail.MessagingException** là checked exception của Jakarta Mail, đại diện cho sự cố ở API gửi/nhận email, MIME hoặc transport. Nó kế thừa từ **Exception**, nên một method khai báo throws MessagingException phải được xử lý theo quy tắc checked exception của Java.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;

public MimeMessage createMessage(
        JavaMailSender sender,
        String recipient
) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setTo(recipient);
    helper.setSubject("Xác nhận");
    helper.setText("Nội dung thư", false);

    return message;
}
~~~

Method này cho phép caller biết việc chuẩn bị MimeMessage có thể thất bại.

### 2.1. Không phải mọi MessagingException đều có cùng ý nghĩa

Một số subtype quan trọng:

| Kiểu exception | Ngữ cảnh thường gặp | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| **MessagingException** | Lỗi mail tổng quát | Lỗi xảy ra ở bước nào? Có nested exception không? |
| **AuthenticationFailedException** | Xác thực mail server | Credentials, token, AUTH mechanism hay policy? |
| **SendFailedException** | Gửi thất bại, có thể liên quan địa chỉ | Recipient nào hợp lệ, không hợp lệ hoặc chưa gửi? |
| **AddressException** | Cú pháp địa chỉ email | Input địa chỉ có hợp lệ không? |
| **ParseException** | Phân tích nội dung hoặc cú pháp mail | Header/địa chỉ/nội dung có được tạo đúng không? |

**AddressException** thuộc package **jakarta.mail.internet**, là một subtype cụ thể liên quan cú pháp địa chỉ. Tên class không đồng nghĩa rằng SMTP đã xác nhận mailbox không tồn tại: kiểm tra cú pháp và kiểm tra mailbox thực tế là hai việc khác nhau.

### 2.2. Chuyển đổi namespace theo phiên bản

Trong các ứng dụng Spring Framework 6 và Spring Boot 3 trở lên, Jakarta Mail dùng namespace **jakarta.mail**.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
~~~

Nhiều tài liệu hoặc mã nguồn cũ của Spring 5/JavaMail dùng:

~~~java
import javax.mail.MessagingException;
import javax.mail.internet.MimeMessage;
~~~

**javax.mail** và **jakarta.mail** là hai namespace API khác nhau. Không trộn chúng trong cùng một đoạn code Spring Mail hiện đại nếu dependency đang dùng Jakarta. Khi nâng cấp, cần kiểm tra đồng bộ dependency, import và các provider triển khai Jakarta Mail.

## 3. Khác biệt giữa MessagingException và MailException

Spring đặt một lớp trừu tượng lên API JavaMailSender để người dùng ứng dụng xử lý lỗi gửi thư qua exception runtime thuộc Spring.

~~~text
Spring Mail
  MailException
      |
      +-- MailAuthenticationException
      +-- MailSendException
      +-- MailParseException
      +-- MailPreparationException
      |
      +-- Các subtype khác

Jakarta Mail
  MessagingException
      |
      +-- AuthenticationFailedException
      +-- SendFailedException
      +-- ParseException
            |
            +-- AddressException
~~~

Sơ đồ chỉ hiển thị những kiểu thường gặp và quan hệ chính, không phải toàn bộ class hierarchy của mọi phiên bản thư viện.

| Khía cạnh | Jakarta MessagingException | Spring MailException |
| --- | --- | --- |
| Package | **jakarta.mail** | **org.springframework.mail** |
| Loại exception | Checked | Runtime |
| Thường bắt gặp | API MIME, Jakarta Mail transport | API JavaMailSender và abstraction Spring |
| Thông tin nguyên nhân | Subtype, getNextException, cause | Subtype Spring, cause, failed messages tùy class |
| Dùng để xử lý | Biết chi tiết lỗi từ Jakarta Mail | Quyết định xử lý lỗi ở tầng ứng dụng Spring |

### 3.1. Vì sao Spring wrap exception?

Ứng dụng thường không muốn tất cả service gửi thư đều phải khai báo checked exception của transport. JavaMailSender cho phép Spring chuyển lỗi provider thành subtype của MailException.

Ví dụ một lỗi AUTH từ Jakarta Mail có thể được nhìn thấy ở Spring như **MailAuthenticationException**, trong khi **AuthenticationFailedException** còn nằm trong cause.

Tuy nhiên, không có bảo đảm rằng mọi lỗi SMTP sẽ được map chính xác thành một subtype Spring duy nhất. Cần đọc lớp bọc và các nguyên nhân lồng bên dưới.

### 3.2. Cách bắt lỗi tổng quát

~~~java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Xác thực là nhóm lỗi cần xem xét riêng.
} catch (MailSendException ex) {
    // Kiểm tra các message thất bại và nguyên nhân gốc.
} catch (MailException ex) {
    // Lỗi khác ở tầng Spring Mail.
}
~~~

Thứ tự bắt đặt subtype trước superclass. Không nên bắt **Exception** rồi tự động retry mọi lỗi, vì lỗi chuẩn bị nội dung, cú pháp và cấu hình không nhất thiết có thể phục hồi bằng retry.

## 4. Cơ chế exception liên kết đặc biệt của Jakarta Mail

Một điểm rất quan trọng là **MessagingException có cơ chế liên kết exception qua getNextException()**. Đây là lý do một chẩn đoán chỉ duyệt Java **Throwable.getCause()** có thể bỏ lỡ thông tin.

Ví dụ khái niệm:

~~~text
MessagingException
    |
    +-- getCause() --> nguyên nhân được Java expose
    |
    +-- getNextException() --> Exception liên kết của Jakarta Mail
                                 |
                                 +-- Có thể là MessagingException khác
                                 +-- Có thể là SocketException
                                 +-- Có thể là SSLException
                                 +-- Có thể là exception provider
~~~

Tùy phiên bản và cách exception được tạo, **getCause() có thể trỏ vào nested exception**, nhưng không nên giả định cause chain luôn phản ánh đầy đủ mọi mắt xích Jakarta Mail.

### 4.1. getNextException()

API:

~~~java
Exception next = messagingException.getNextException();
~~~

Nó trả về exception tiếp theo trong chuỗi liên kết nếu có, hoặc null.

Ví dụ khi chẩn đoán:

~~~java
if (error instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();

    if (next != null) {
        log.warn(
                "Jakarta Mail nested exception type: {}",
                next.getClass().getName()
        );
    }
}
~~~

Đây là ví dụ chỉ đọc loại exception. Nếu cần đọc thêm các mắt xích, phải duyệt chúng có giới hạn và tránh vòng lặp.

### 4.2. setNextException()

Jakarta Mail cũng có API:

~~~java
boolean added = messagingException.setNextException(otherException);
~~~

API này cho phép bổ sung một exception vào chuỗi liên kết trong những trường hợp phù hợp. Thông thường **mã ứng dụng không cần tự chỉnh sửa chuỗi exception**. Việc tự thêm lỗi vào chuỗi có thể làm chẩn đoán khó hơn nếu không có quy ước rõ ràng.

Trong luồng ứng dụng thông thường, hãy **quan sát getNextException()**, không tự thêm các exception không liên quan chỉ để ghi log.

### 4.3. getCause() vẫn quan trọng

Một Spring MailException có thể wrap Jakarta MessagingException qua Java cause. Từ MessagingException, ta lại cần xem getNextException.

~~~text
MailSendException (Spring)
       |
       +-- getCause()
              |
              v
         MessagingException (Jakarta)
              |
              +-- getNextException()
                     |
                     v
                SocketTimeoutException
~~~

Nếu chỉ log class ngoài cùng, bạn mất thông tin về timeout. Nếu chỉ đọc getCause từ MessagingException, có thể bỏ qua exception được nối bằng API riêng của Jakarta Mail trong một số trường hợp.

### 4.4. Không nhầm thông điệp exception với nguyên nhân

Một chuỗi như **Could not send message** chỉ cho biết thao tác ở mức cao thất bại. Nó không đủ để phân biệt:

- Sai tài khoản.
- Server từ chối RCPT TO.
- File attachment không đọc được.
- TLS handshake thất bại.
- Timeout kết nối.
- Server đã nhận DATA nhưng response bị mất.

Thông điệp con có thể cung cấp ngữ cảnh, nhưng cần xem class, mã SMTP và phase thực tế.

## 5. Hàm duyệt cause và Jakarta next exception

Một utility nhỏ có thể thu thập **loại exception** theo cả hai nhánh **getCause()** và **getNextException()**. Đoạn code dưới đây được thiết kế để tránh vòng lặp và không log secrets.

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class MailExceptionInspector {

    private MailExceptionInspector() {
    }

    public static List<String> collectExceptionTypes(
            Throwable root
    ) {
        if (root == null) {
            return List.of();
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        List<String> result = new ArrayList<>();

        pending.addLast(root);

        while (!pending.isEmpty() && result.size() < 32) {
            Throwable current = pending.removeFirst();

            if (!visited.add(current)) {
                continue;
            }

            result.add(current.getClass().getName());

            Throwable cause = current.getCause();
            if (cause != null && cause != current) {
                pending.addLast(cause);
            }

            if (current instanceof MessagingException mailError) {
                Exception next = mailError.getNextException();

                if (next != null && next != current) {
                    pending.addLast(next);
                }
            }
        }

        return result;
    }
}
~~~

Ví dụ sử dụng:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    List<String> types =
            MailExceptionInspector.collectExceptionTypes(ex);

    log.error(
            "Mail operation failed. Exception types: {}",
            types
    );

    throw ex;
}
~~~

### 5.1. Vì sao dùng IdentityHashMap?

Vì các exception có thể liên kết qua nhiều đường (cause và next), cần bảo đảm không duyệt lặp một object. **IdentityHashMap** dùng định danh object thay vì equals để theo dõi chính xác những exception đã gặp.

### 5.2. Vì sao giới hạn 32 nodes?

Một chuỗi exception bị lỗi hoặc bất thường không nên khiến logger chạy vô hạn. Giới hạn số node giúp chẩn đoán có chi phí dự đoán được.

Con số 32 chỉ là ví dụ. Có thể điều chỉnh, đồng thời cần giới hạn chiều dài thông điệp và dung lượng dữ liệu log.

### 5.3. Utility này chưa bao gồm mọi cấu trúc lỗi Spring

Ví dụ, **MailSendException** có thể giữ các exception chi tiết của nhiều message trong cấu trúc riêng. Hàm chỉ duyệt cause và Jakarta next sẽ **không tự động** xem mọi entry đó.

Vì thế, để chẩn đoán lỗi gửi batch, cần đọc thêm các accessor như **getMessageExceptions()** hoặc **getFailedMessages()** khi chúng có sẵn.

## 6. SendFailedException và địa chỉ đã được xử lý khác nhau

**jakarta.mail.SendFailedException** là subtype quan trọng khi lời gọi gửi không hoàn tất như mong muốn. Nó có thể cung cấp ba nhóm địa chỉ:

- **getInvalidAddresses()**: các địa chỉ được xác định là không hợp lệ theo kết quả transport.
- **getValidSentAddresses()**: các địa chỉ hợp lệ được transport đánh dấu đã gửi.
- **getValidUnsentAddresses()**: các địa chỉ hợp lệ nhưng chưa gửi.

Ví dụ:

~~~java
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

public void inspectRecipients(SendFailedException failure) {
    Address[] invalid = failure.getInvalidAddresses();
    Address[] validSent = failure.getValidSentAddresses();
    Address[] validUnsent = failure.getValidUnsentAddresses();

    int invalidCount = invalid == null ? 0 : invalid.length;
    int sentCount = validSent == null ? 0 : validSent.length;
    int unsentCount = validUnsent == null ? 0 : validUnsent.length;

    log.warn(
            "SMTP recipient result: invalid={}, validSent={}, validUnsent={}",
            invalidCount,
            sentCount,
            unsentCount
    );
}
~~~

### 6.1. Đừng retry toàn bộ batch theo phản xạ

Giả sử một message có ba người nhận:

~~~text
alice@example.net   -> accepted and sent
bob@example.net     -> invalid
carol@example.net   -> valid but unsent
~~~

Nếu retry nguyên message tới cả ba người:

- Alice có thể nhận bản sao.
- Bob tiếp tục bị từ chối.
- Carol có thể cần retry nhưng phải theo kết quả cụ thể.

Cần đối chiếu các nhóm địa chỉ với cách provider xử lý **partial send**. Không suy diễn số người nhận thực tế chỉ từ một boolean success/failure của toàn message.

### 6.2. accepted không đồng nghĩa delivered

Ngay cả khi transport đánh dấu một địa chỉ đã được gửi, điều đó thường chỉ phản ánh bước SMTP/provider. Server có thể chấp nhận message nhưng sau đó gửi bounce.

Hãy dùng tên trạng thái chính xác như **ACCEPTED_BY_RELAY** hoặc **SMTP_SENT**, không tự hiểu là người nhận đã mở email.

### 6.3. Một recipient có thể bị từ chối do policy

Một địa chỉ ở nhóm invalid hoặc một phản hồi SMTP 550 không nhất thiết chứng minh mailbox không tồn tại. Lỗi có thể liên quan sender, policy hoặc quota.

Để quyết định suppression, cần xem thêm enhanced status code và tín hiệu đáng tin cậy từ provider.

## 7. AddressException: sai cú pháp không phải mailbox không tồn tại

**jakarta.mail.internet.AddressException** thường xuất hiện khi parse hoặc xác minh cú pháp địa chỉ. Nó khác với trường hợp SMTP server trả **550 5.1.1 User unknown** cho một địa chỉ có cú pháp hợp lệ.

Ví dụ kiểm tra cú pháp:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public void validateAddress(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "Email address must not be blank"
        );
    }

    try {
        InternetAddress address = new InternetAddress(value, true);
        address.validate();
    } catch (AddressException ex) {
        throw new IllegalArgumentException(
                "Invalid email address syntax",
                ex
        );
    }
}
~~~

Cần nhớ:

- Validation cú pháp không đảm bảo mailbox có thật.
- Một domain có thể chưa nhận thư hoặc có chính sách đặc biệt.
- Địa chỉ quốc tế hóa có những yêu cầu SMTPUTF8 riêng.
- Việc parse chuỗi không xác minh người nhận sở hữu mailbox.

Một lỗi AddressException trong giai đoạn chuẩn bị message thường cần **sửa dữ liệu đầu vào**, không retry SMTP.

## 8. AuthenticationFailedException và lỗi đăng nhập SMTP

**jakarta.mail.AuthenticationFailedException** mô tả xác thực không thành công ở tầng Jakarta Mail. Trong Spring, nó có thể được wrap thành **MailAuthenticationException**.

Một số nguyên nhân:

- Username hoặc password sai.
- App password bị thu hồi.
- SMTP AUTH bị vô hiệu hóa.
- OAuth token hết hạn, sai scope hoặc bị thu hồi.
- Cơ chế AUTH không được hỗ trợ.
- Tài khoản bị khóa.
- Provider tạm thời không cung cấp dịch vụ xác thực.

### 8.1. Không retry mù lỗi AUTH

Nếu cấu hình sai, việc thử lại cùng credentials sau vài giây thường không giúp ích và có thể kích hoạt cơ chế bảo vệ account.

Hướng xử lý:

1. Xác định account gửi bị ảnh hưởng.
2. Tạm dừng những tác vụ dùng account có cấu hình lỗi.
3. Cảnh báo cho bộ phận vận hành.
4. Sửa credential, quyền hoặc cơ chế xác thực.
5. Kiểm tra có kiểm soát rồi mới khôi phục queue.

Nếu provider trả lỗi tạm thời ở AUTH, chẳng hạn 454 4.7.0, có thể dùng retry với backoff và giới hạn, không kết luận mọi AuthenticationFailedException đều vĩnh viễn.

### 8.2. Ví dụ bắt lỗi Spring ở ranh giới service

~~~java
public void deliver(MimeMessage message) {
    try {
        mailSender.send(message);
    } catch (MailAuthenticationException ex) {
        log.error(
                "SMTP authentication failed for sender account {}",
                senderAccountId
        );

        throw ex;
    }
}
~~~

Đừng log password, OAuth token, raw AUTH payload hoặc thông tin bí mật. **senderAccountId** là định danh nội bộ không nhạy cảm trong ví dụ.

### 8.3. Lỗi AUTH khác lỗi MAIL FROM

Một account có thể đăng nhập thành công nhưng không được phép gửi bằng địa chỉ envelope sender cụ thể. Lỗi đó có thể xảy ra ở MAIL FROM, không phải AUTH.

Không tự thay đổi password khi server thực sự từ chối quyền gửi thay mặt một domain hoặc địa chỉ From.

## 9. Lỗi mạng và TLS trong chuỗi nguyên nhân

Lỗi gửi mail cũng có thể bắt nguồn từ exception của Java networking hoặc TLS, xuất hiện dưới MessagingException:

| Loại lỗi | Ví dụ nguyên nhân | Hướng điều tra |
| --- | --- | --- |
| **UnknownHostException** | Host SMTP không phân giải được | Kiểm tra hostname, DNS, cấu hình |
| **ConnectException** | Kết nối bị từ chối | Kiểm tra host, port, firewall, service |
| **SocketTimeoutException** | Connect/read timeout | Kiểm tra mạng, timeout, giai đoạn gửi |
| **SocketException** | Connection reset/broken pipe | Kiểm tra kết nối, proxy, provider |
| **SSLHandshakeException** | TLS handshake lỗi | Kiểm tra certificate, trust, protocol, SNI |
| **CertificateException** | Certificate/trust không hợp lệ | Kiểm tra certificate chain và truststore |

Ví dụ chuỗi lỗi:

~~~text
MailSendException
    |
    v
MessagingException: Could not connect to SMTP host
    |
    v
ConnectException: Connection refused
~~~

Khi đó, đổi recipient không giải quyết được vấn đề.

### 9.1. Phân biệt lỗi cấu hình và lỗi tạm thời

- Host sai hoặc port sai là lỗi cấu hình cần sửa.
- Firewall chặn lâu dài cần thay đổi chính sách hoặc route.
- Một timeout ngắn có thể retry có giới hạn.
- Certificate expired hoặc truststore thiếu CA thường cần sửa cấu hình/TLS.
- Không tắt certificate validation chỉ để làm email gửi được.

### 9.2. Giai đoạn timeout quyết định nguy cơ gửi trùng

Nếu timeout ở CONNECT, SMTP server chưa có cơ hội nhận message của phiên đó.

Nếu timeout sau khi ứng dụng gửi toàn bộ DATA nhưng chưa nhận response cuối cùng, server **có thể đã chấp nhận message**. Retry khi ấy có nguy cơ gửi trùng.

Một exception SocketTimeoutException đơn thuần không luôn cung cấp đủ thông tin về giai đoạn. Nếu phase không rõ, nên ghi trạng thái **UNKNOWN_OUTCOME** thay vì mặc định “chưa gửi”.

## 10. SMTP reply code và enhanced status code

Lỗi SMTP thường mang mã phản hồi ba chữ số:

| Nhóm | Ý nghĩa khái quát |
| --- | --- |
| **2xx** | Lệnh được chấp nhận |
| **3xx** | Chờ thêm thông tin từ client |
| **4xx** | Negative completion tạm thời |
| **5xx** | Negative completion trong điều kiện hiện tại |

Ngoài ra, một số server cung cấp enhanced status code như **5.1.1**, **4.7.0** hoặc **5.7.8**.

Ví dụ:

~~~text
550 5.1.1 User unknown
~~~

~~~text
535 5.7.8 Authentication credentials invalid
~~~

~~~text
421 4.7.0 Temporarily rate limited
~~~

Những tín hiệu này hữu ích hơn một thông điệp Spring Mail chung. Tuy nhiên, code và diagnostic text cụ thể phụ thuộc provider.

### 10.1. Một mã 550 không đủ để kết luận recipient sai

Ví dụ:

~~~text
550 5.1.1 User unknown
~~~

có thể nói về mailbox không tồn tại.

Nhưng:

~~~text
550 5.7.1 Message rejected by policy
~~~

có thể nói về quyền gửi, policy hoặc danh tiếng sender.

Nếu thấy 550 rồi tự đưa recipient vào danh sách invalid, bạn có thể suppression nhầm những địa chỉ hợp lệ.

### 10.2. 4xx không đồng nghĩa retry ngay

Phản hồi 4xx thường mang nghĩa tạm thời, nhưng cần dùng backoff và giới hạn. Nếu provider rate-limit, retry ngay có thể làm tình hình xấu hơn.

### 10.3. 5xx không đồng nghĩa sửa recipient

5xx có thể liên quan AUTH, MAIL FROM, RCPT TO hoặc DATA. Phải xác định phase và enhanced status code.

## 11. SMTP provider exception: một lớp chẩn đoán chuyên biệt

Ngoài các class chung của Jakarta Mail, SMTP provider thường có exception mang mã phản hồi hoặc địa chỉ liên quan. Ví dụ, một số provider dùng các tên kiểu như:

- **SMTPAddressFailedException**
- **SMTPAddressSucceededException**
- **SMTPSendFailedException**

Các class này có thể nằm trong package phụ thuộc implementation, chẳng hạn các package của Angus Mail hoặc các provider kế thừa JavaMail. **Không mặc định một package provider cụ thể luôn có mặt ở mọi ứng dụng.**

### 11.1. Vì sao provider exception có ích?

Khi exception cung cấp SMTP reply code, command hoặc recipient, ứng dụng có thể phân biệt:

~~~text
SMTP command = RCPT TO
Reply code   = 550
Enhanced     = 5.1.1
Recipient    = recipient-ref-42
~~~

với:

~~~text
SMTP command = DATA
Reply code   = 554
Enhanced     = 5.7.1
Recipient    = not necessarily one mailbox
~~~

Trường hợp đầu có thể liên quan mailbox cụ thể; trường hợp sau có thể là policy của toàn message.

### 11.2. Không phân loại theo message text một cách mong manh

Code như:

~~~java
if (exception.getMessage().contains("User unknown")) {
    // Treat recipient as permanently invalid
}
~~~

rất dễ sai khi provider đổi ngôn ngữ, format hoặc nội dung diagnostic. Ưu tiên thông tin cấu trúc từ provider, enhanced status code và stage. Nếu chỉ có text, phân loại bảo thủ và giữ trạng thái cần điều tra.

### 11.3. Tạo adapter độc lập provider

Một mô hình chẩn đoán chung:

~~~java
public enum SmtpPhase {
    CONNECT,
    TLS,
    AUTH,
    MAIL_FROM,
    RCPT_TO,
    DATA,
    AFTER_DATA,
    UNKNOWN
}

public record SmtpFailureSignals(
        SmtpPhase phase,
        Integer replyCode,
        String enhancedStatus,
        String recipientReference,
        boolean responseMayHaveBeenLostAfterData
) {}
~~~

Tầng infrastructure lấy dữ liệu từ provider exception, còn tầng nghiệp vụ chỉ dùng SmtpFailureSignals. Khi đổi Jakarta Mail implementation hoặc SMTP provider, phần policy không phải phụ thuộc trực tiếp vào package provider cũ.

## 12. MailSendException có thể chứa lỗi của nhiều message

Spring **MailSendException** có thể dùng khi gửi một hoặc nhiều MimeMessage không thành công. Nó cung cấp thêm thông tin ngoài cause thông thường, ví dụ các method:

~~~java
ex.getMessageExceptions();
ex.getFailedMessages();
~~~

### 12.1. getMessageExceptions()

~~~java
catch (MailSendException ex) {
    Exception[] failures = ex.getMessageExceptions();

    for (Exception failure : failures) {
        log.warn(
                "Failed mail message exception type: {}",
                failure.getClass().getName()
        );
    }
}
~~~

Mỗi exception có thể chứa Jakarta next exception hoặc cause riêng. Không chỉ đọc lỗi đầu tiên rồi áp dụng kết luận đó cho cả batch.

### 12.2. getFailedMessages()

~~~java
catch (MailSendException ex) {
    Map<Object, Exception> failures = ex.getFailedMessages();

    log.warn(
            "Failed mail messages: {}",
            failures.size()
    );
}
~~~

Mapping giúp liên kết message bị lỗi với exception tương ứng. Kiểu map key cụ thể có thể liên quan MimeMessage hoặc object được gửi qua API. Hãy đọc contract của phiên bản Spring đang dùng khi xây dựng adapter chi tiết.

**Không log toàn bộ key hoặc gọi toString trên message nếu có nguy cơ lộ nội dung email.** Chỉ chuyển key về correlation ID nội bộ hoặc số lượng phù hợp.

### 12.3. Phân biệt prepare error với send error

Một lỗi khi render template hoặc addAttachment không có cùng semantics với lỗi sau DATA. Một lỗi được ném trước khi gọi send thường không có nguy cơ server đã chấp nhận message của lần gửi đó.

Tuy vậy, nếu một batch đã gửi vài message trước khi lỗi xảy ra ở message tiếp theo, vẫn cần theo dõi từng message thay vì coi cả batch là “chưa gửi”.

## 13. Ví dụ Spring service tách lỗi chuẩn bị và lỗi gửi

Một service có thể tách hai giai đoạn để ghi nhận nguyên nhân rõ ràng:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceDeliveryService {

    private final JavaMailSender mailSender;

    public InvoiceDeliveryService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdf
    ) {
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException(
                    "Invoice PDF must not be empty"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED,
                    "UTF-8"
            );

            helper.setFrom("billing@example.org");
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn " + invoiceNumber);
            helper.setText("Vui lòng xem hóa đơn đính kèm.", false);

            helper.addAttachment(
                    "invoice.pdf",
                    new ByteArrayResource(pdf),
                    "application/pdf"
            );
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare invoice email",
                    ex
            );
        }

        try {
            mailSender.send(message);
        } catch (MailException ex) {
            // Chuyển lỗi sang tầng delivery/outbox để phân loại.
            throw ex;
        }
    }
}
~~~

Đoạn code minh họa hai vùng trách nhiệm:

- **Prepare:** tạo phần MIME, header, body và attachment.
- **Send:** giao message cho Jakarta Mail transport qua JavaMailSender.

Trong ứng dụng thật, recipient và invoiceNumber cần được xác thực/chuẩn hóa theo nghiệp vụ. Không đưa dữ liệu người dùng chưa kiểm soát vào header hoặc filename.

### 13.1. Tại sao không retry lỗi chuẩn bị?

Nếu recipient sai cú pháp hoặc PDF rỗng, gửi lại ngay với cùng dữ liệu vẫn thất bại. Nên sửa dữ liệu nguồn trước khi tạo một lượt gửi mới.

### 13.2. Tại sao lỗi gửi cần chẩn đoán sâu?

Nếu send ném MailSendException, nguyên nhân có thể là kết nối, xác thực, RCPT TO, DATA hoặc kết quả không xác định. Tên exception không đủ để chọn hành động.

## 14. Ví dụ sử dụng MimeMessagePreparator

Spring hỗ trợ tạo message qua **MimeMessagePreparator**:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(mimeMessage, true, "UTF-8");

    helper.setFrom("support@example.org");
    helper.setTo("user@example.net");
    helper.setSubject("Thông báo");
    helper.setText("Nội dung email", false);
});
~~~

Cách này gói chuẩn bị và gửi trong một API gọi. Nếu việc chuẩn bị message thất bại, Spring có thể bọc lỗi thành một MailException thích hợp cho bước chuẩn bị/parsing, tùy loại lỗi và cách adapter xử lý.

Ưu điểm: ngắn gọn, dễ dùng khi chỉ cần dựng một message. Hạn chế chẩn đoán: caller có thể thấy Spring exception ngoài cùng thay vì MessagingException trực tiếp, nên vẫn cần đọc cause.

### 14.1. So sánh hai phong cách

| Phong cách | Ưu điểm | Lưu ý |
| --- | --- | --- |
| Tự tạo MimeMessage rồi gửi | Dễ chia ranh giới prepare và send trong code | Cần bắt MessagingException ở bước chuẩn bị |
| Dùng MimeMessagePreparator | Cú pháp gọn, tập trung dựng MIME | Spring có thể wrap lỗi chuẩn bị, cần quan sát cause |

Cả hai cách đều dùng Jakarta Mail dưới tầng Spring và đều có thể phát sinh lỗi cần chẩn đoán.

## 15. Không dùng một catch-all để retry

Mẫu cần tránh:

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    retryLater(message);
}
~~~

Nó trộn:

- Input/header sai.
- Template không đọc được.
- AUTH bị từ chối vĩnh viễn.
- Mailbox không tồn tại.
- SMTP tạm thời quá tải.
- Timeout sau DATA có thể đã gửi thành công.

Một chính sách phù hợp nên xem nguyên nhân và mức độ chắc chắn về kết quả.

### 15.1. Mô hình kết quả phân loại

~~~java
public enum DeliveryFailureCategory {
    INVALID_INPUT,
    AUTH_CONFIGURATION,
    RECIPIENT_REJECTED,
    POLICY_REJECTED,
    TEMPORARY_SERVER_FAILURE,
    NETWORK_FAILURE,
    MESSAGE_PREPARATION,
    UNKNOWN_OUTCOME
}

public enum DeliveryAction {
    STOP_AND_FIX_DATA,
    PAUSE_SENDER_CONFIG,
    RETRY_WITH_BACKOFF,
    REVIEW_BEFORE_RETRY
}
~~~

Đây là enum nghiệp vụ do ứng dụng tự thiết kế, không phải enum có sẵn của Spring hay Jakarta Mail.

### 15.2. Ma trận chẩn đoán

| Tín hiệu | Nhóm lỗi khả dĩ | Hành động khuyến nghị |
| --- | --- | --- |
| AddressException khi chuẩn bị | Input/cú pháp địa chỉ | Sửa địa chỉ, không retry nguyên trạng |
| MailAuthenticationException + AUTH 535 | Credentials/quyền gửi | Tạm dừng sender, kiểm tra cấu hình |
| AUTH 454 4.7.x | Xác thực tạm thời không khả dụng | Retry có backoff, giới hạn |
| RCPT TO 550 5.1.1 đáng tin | Recipient không tồn tại | Xác minh/suppression theo chính sách |
| RCPT TO 450 4.2.x | Recipient tạm thời không khả dụng | Retry có giới hạn |
| MAIL FROM/DATA 550 5.7.1 | Policy hoặc quyền gửi | Điều tra; không gắn nhãn user unknown |
| Connection refused | Host/port/firewall/provider | Kiểm tra cấu hình và tình trạng service |
| SSLHandshakeException | TLS/certificate | Kiểm tra trust/cert/protocol |
| Timeout trước DATA, có phase rõ | Lỗi mạng tạm thời | Retry có backoff |
| Mất phản hồi sau DATA | Kết quả chưa xác định | Đối soát, xem nguy cơ gửi trùng |
| Attachment không đọc được | Resource/file | Sửa file hoặc nguồn dữ liệu |

Không dùng bảng này như một bộ phân loại tuyệt đối. Trong thực tế có thể thiếu phase, enhanced status hoặc lỗi gốc, nên cần trạng thái UNKNOWN/REVIEW thay vì tự đưa ra quyết định chắc chắn.

## 16. Ghi trạng thái lỗi vào outbox

Với email quan trọng, sử dụng outbox giúp tách việc commit dữ liệu nghiệp vụ khỏi SMTP. Worker gửi email, chẩn đoán lỗi và cập nhật kết quả riêng.

Mô hình trạng thái minh họa:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted ------> ACCEPTED_BY_RELAY
   |
   +-- 4xx temporary ------> RETRY_WAIT
   |
   +-- AUTH configuration -> PAUSED_CONFIG
   |
   +-- Invalid recipient -> INVALID_RECIPIENT
   |
   +-- Policy rejection --> NEEDS_REVIEW
   |
   +-- Unknown after DATA > UNKNOWN_OUTCOME
   |
   +-- Retry exhausted ---> FAILED
~~~

Trong bản ghi có thể lưu:

~~~text
eventId
attemptCount
smtpAccountReference
recipientReference
errorCategory
smtpReplyCode
enhancedStatusCode
smtpPhase
outcomeKnown
nextAttemptAt
lastAttemptAt
~~~

Không cần ghi raw MIME body, attachment hoặc password để chẩn đoán retry.

### 16.1. Lỗi tài khoản và lỗi recipient có phạm vi khác nhau

Nếu một SMTP account sai mật khẩu, toàn bộ job dùng account đó có thể thất bại. Nên tạm dừng account thay vì cho từng job retry liên tục.

Nếu chỉ một recipient sai cú pháp hoặc không tồn tại, hãy giữ các job khác tiếp tục hoạt động.

### 16.2. Retry không nên chạy lại nghiệp vụ

Nếu email xác nhận hóa đơn gửi thất bại, worker chỉ nên retry **tác vụ gửi**. Không chạy lại nghiệp vụ lập hóa đơn, tạo đơn hàng hoặc thu tiền chỉ vì SMTP lỗi.

## 17. Kết quả không xác định và nguy cơ gửi trùng

Một failure window quan trọng:

~~~text
1. Worker gửi SMTP DATA.
2. Server nhận đủ nội dung.
3. Server chấp nhận message.
4. Kết nối đứt trước khi response tới worker.
5. JavaMailSender báo lỗi/timeout.
6. Worker không biết message đã được chấp nhận hay chưa.
~~~

Nếu retry, message có thể được gửi thêm một lần.

### 17.1. MailSendException không chứng minh chưa gửi

Ngay cả khi JavaMailSender ném MailSendException, ứng dụng không nên tự suy ra mọi recipient chưa nhận message. Cần xem partial-send result và thời điểm lỗi.

### 17.2. Message-ID không phải exactly-once guarantee

Header Message-ID giúp nhận diện và đối soát mail, nhưng SMTP server/client không bắt buộc tự loại bỏ message trùng theo cùng Message-ID.

Nếu provider có idempotency key qua API riêng, dùng theo contract của provider. SMTP thuần không có một cơ chế exactly-once gửi email tổng quát.

### 17.3. Thiết kế nội dung chịu được retry

Một event nghiệp vụ nên có ID ổn định. Retry không nên tạo thêm đơn hàng, thay đổi trạng thái hay phát hành mã xác thực khác nếu đang xử lý cùng một ý định gửi.

Ví dụ:

~~~text
Mail event:
  eventId = ORDER_CONFIRMED:1001:version-3
  recipientRef = customer-42
  template = order-confirmation-v2
~~~

Đây là metadata nghiệp vụ minh họa, không phải format bắt buộc của Jakarta Mail.

## 18. Bật debug Jakarta Mail có kiểm soát

Khi cần chẩn đoán kết nối, xác thực hoặc phản hồi SMTP trong môi trường phát triển, có thể bật debug của Jakarta Mail bằng property tương ứng.

Ví dụ Spring Boot YAML:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      "[mail.debug]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Đây là ví dụ cấu hình; các giá trị timeout tính bằng mili giây và cần điều chỉnh theo provider, tải hệ thống, SLA.

### 18.1. Debug có thể tiết lộ dữ liệu nhạy cảm

Log protocol có thể chứa server, sender, recipient, command, response hoặc metadata. Tùy cách cấu hình và provider, thông tin xác thực và dữ liệu message cũng có nguy cơ bị ghi nhận.

Chỉ bật debug trong môi trường có kiểm soát, giới hạn thời gian, bảo vệ quyền truy cập log và redaction dữ liệu. Không bật protocol logging chi tiết mặc định ở production.

### 18.2. Timeout không giải quyết nguyên nhân gốc

Đặt timeout hữu hạn giúp worker không treo mãi. Nhưng nếu DNS sai, credential bị từ chối hoặc certificate không hợp lệ, chỉ tăng timeout không khắc phục được lỗi.

### 18.3. Phải phân biệt ba timeout

- **connectiontimeout:** thời gian chờ tạo kết nối.
- **timeout:** thời gian chờ đọc phản hồi.
- **writetimeout:** thời gian chờ ghi dữ liệu ra socket.

Timeout ở bước ghi hoặc đọc sau DATA có thể tạo kết quả chưa xác định. Vì vậy, timeout setting là một phần của độ tin cậy, không chỉ là một công cụ để “tránh lỗi”.

## 19. Logging an toàn khi xử lý MessagingException

Một log có ích thường chứa **ngữ cảnh tác vụ** và **loại nguyên nhân**, không phải toàn bộ email.

Ví dụ:

~~~text
eventId=mail-event-123
accountRef=smtp-account-01
recipientRef=customer-42
phase=RCPT_TO
smtpReply=550
enhancedStatus=5.1.1
category=RECIPIENT_REJECTED
attempt=1
decision=STOP_AND_FIX_DATA
~~~

Thông tin cần tránh ghi trực tiếp:

- Password SMTP và OAuth token.
- MIME body chứa dữ liệu cá nhân.
- Attachment hoặc file PDF.
- Raw AUTH command.
- Toàn bộ exception message không được kiểm duyệt.
- Recipient đầy đủ trong hệ thống log rộng quyền khi không cần.

### 19.1. Log root cause nhưng không làm mất ngữ cảnh

Chỉ ghi:

~~~text
SocketTimeoutException
~~~

có thể không đủ, vì không biết timeout trước hay sau DATA và thuộc tác vụ nào.

Ngược lại, chỉ ghi:

~~~text
MailSendException: Mail server connection failed
~~~

cũng không đủ.

Một log tốt chứa event ID, phase khi biết, exception class, SMTP code, policy decision và attempt count.

### 19.2. Không log cùng lỗi ở mọi tầng

Nếu tầng infrastructure đã log đầy đủ một lỗi và worker cũng log lại cùng stack trace, log có thể bị trùng rất nhiều. Có thể để tầng dưới trả lỗi có cấu trúc, còn tầng điều phối log một bản ghi quyết định kèm correlation ID.

## 20. Cách điều tra một MessagingException theo từng bước

Khi có sự cố thật:

1. **Xác định thao tác:** lỗi ở bước chuẩn bị MIME hay ở send?
2. **Xem exception ngoài cùng:** MailException subtype hay MessagingException trực tiếp?
3. **Đọc cause chain:** loại exception gốc là gì?
4. **Đọc getNextException:** có exception provider hoặc mạng liên kết không?
5. **Kiểm tra MailSendException details:** message nào và recipient nào bị ảnh hưởng?
6. **Xác định SMTP phase:** CONNECT, TLS, AUTH, MAIL FROM, RCPT TO hay DATA?
7. **Đọc reply và enhanced status:** có mã cấu trúc từ provider không?
8. **Xác định kết quả:** đã được server accept, chưa accept hay UNKNOWN?
9. **Phân loại lỗi:** cấu hình, dữ liệu, policy, tạm thời hoặc chưa rõ?
10. **Chọn hành động:** sửa cấu hình, sửa địa chỉ, retry có giới hạn, đối soát hoặc dừng.
11. **Ghi trạng thái:** cập nhật outbox/job và giám sát.
12. **Kiểm chứng cách phục hồi:** sau khi sửa lỗi, thử có kiểm soát rồi tiếp tục queue.

### 20.1. Minh họa: sai mật khẩu SMTP

~~~text
MailAuthenticationException
    |
    v
AuthenticationFailedException
    |
    v
SMTP AUTH rejected
~~~

Kết luận: vấn đề xác thực. Không chuyển recipient thành invalid. Tạm dừng sender account và kiểm tra thông tin xác thực hoặc policy.

### 20.2. Minh họa: mailbox không tồn tại

~~~text
MailSendException
    |
    v
SendFailedException
    |
    v
Provider recipient failure
    |
    v
RCPT TO -> 550 5.1.1
~~~

Kết luận: với phản hồi đáng tin, recipient không tồn tại. Xử lý địa chỉ theo chính sách, không retry mù cùng dữ liệu.

### 20.3. Minh họa: lỗi TLS

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SSLHandshakeException
~~~

Kết luận: kiểm tra certificate, truststore, TLS protocol và host. Không tắt xác thực TLS để tránh lỗi.

### 20.4. Minh họa: timeout sau DATA

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SocketTimeoutException
    |
    v
Phase: AFTER_DATA, result unknown
~~~

Kết luận: không khẳng định email chưa gửi. Ghi UNKNOWN_OUTCOME và đối soát nếu có tín hiệu từ provider; retry phải tính tới nguy cơ gửi trùng.

## 21. Kiểm thử chẩn đoán exception

Có thể kiểm tra logic chẩn đoán riêng, không cần gửi mail ra Internet.

### 21.1. Test utility getNextException

Ví dụ:

~~~java
@Test
void inspectorSeesJakartaNestedException() {
    MessagingException outer =
            new MessagingException("Sending failed");

    outer.setNextException(
            new java.net.SocketTimeoutException("Read timed out")
    );

    List<String> types =
            MailExceptionInspector.collectExceptionTypes(outer);

    assertTrue(types.contains(
            "java.net.SocketTimeoutException"
    ));
}
~~~

Test này xác minh utility nhận diện next exception. Nó không cần SMTP server thật.

### 21.2. Test lỗi tạo MIME

Các trường hợp có thể kiểm tra:

- Địa chỉ người nhận sai cú pháp.
- Tham số attachment không hợp lệ.
- Resource không đọc được.
- Nội dung hoặc header không phù hợp.
- Template renderer phát sinh lỗi.

Mục tiêu là tách lỗi chuẩn bị khỏi lỗi gửi transport.

### 21.3. Test lỗi AUTH, RCPT TO và DATA

Một SMTP test server hoặc fake transport có thể tạo phản hồi xác định:

| Tình huống | Policy mong đợi |
| --- | --- |
| AUTH 535 5.7.8 | Tạm dừng sender config |
| AUTH 454 4.7.0 | Retry có backoff và giới hạn |
| RCPT TO 550 5.1.1 | Không retry cùng địa chỉ |
| RCPT TO 450 4.2.x | Retry theo lịch |
| DATA 554 5.7.x | Điều tra policy/content |
| Timeout trước DATA | Retry có điều kiện |
| Mất phản hồi sau DATA | UNKNOWN_OUTCOME |
| Partial recipients | Không gửi lại mù toàn danh sách |

Không dùng tài khoản production để cố ý thử nhiều lần mật khẩu sai nhằm tạo test case.

### 21.4. Test batch failure

Nếu JavaMailSender nhận nhiều MimeMessage, có thể giả lập một message lỗi và một message thành công để kiểm tra việc mapping failed messages và xử lý retry riêng.

Điều quan trọng là không đánh dấu toàn batch đã gửi hoặc chưa gửi chỉ vì API ném một exception tổng quát.

## 22. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Chỉ log MessagingException.getMessage() | Không thấy nested cause/provider error | Duyệt cause và getNextException |
| Chỉ duyệt Java getCause() | Có thể bỏ sót linked exception Jakarta Mail | Kiểm tra getNextException |
| Coi mọi MessagingException là lỗi SMTP | Exception có thể phát sinh khi dựng MIME | Tách prepare và send |
| Retry mọi MailException | Lỗi input/AUTH/policy thường cần sửa | Dùng classifier và trạng thái |
| Đánh đồng 550 với user unknown | 550 còn có thể là policy | Xem enhanced code và phase |
| Đánh đồng SMTP accept với delivered | Có thể bounce sau khi server chấp nhận | Ghi trạng thái chính xác |
| Retry toàn bộ batch có partial send | Có thể gửi trùng cho recipient đã accept | Theo dõi per-message/per-recipient |
| Xem timeout là chắc chắn chưa gửi | Có thể xảy ra sau DATA | Ghi UNKNOWN_OUTCOME |
| Log raw MIME và AUTH payload | Lộ dữ liệu cá nhân/secrets | Redaction và log có cấu trúc |
| Tắt TLS certificate validation để tránh lỗi | Mất bảo vệ kết nối | Sửa trust/certificate/config |
| Dùng regex message text làm classifier duy nhất | Diagnostic khác giữa provider | Ưu tiên code/phase/type cấu trúc |
| Trộn javax.mail với jakarta.mail | Không tương thích namespace/dependency | Đồng bộ API theo Spring phiên bản đang dùng |

## 23. Câu hỏi thường gặp

**1. MessagingException có phải lỗi gửi SMTP không?**

Không nhất thiết. Nó là checked exception tổng quát của Jakarta Mail, có thể xuất hiện ở giai đoạn chuẩn bị MIME hoặc transport.

**2. Vì sao JavaMailSender.send() ném MailSendException thay vì MessagingException?**

Spring dùng abstraction MailException dạng runtime. Lỗi gốc Jakarta Mail có thể được giữ trong cause hoặc cấu trúc message failures để chẩn đoán.

**3. getNextException() khác getCause() thế nào?**

getNextException() là API liên kết exception của Jakarta MessagingException. getCause() là API chuẩn Java Throwable. Để chẩn đoán đầy đủ, nên xem cả hai với cơ chế chống duyệt lặp.

**4. Có nên tự gọi setNextException() không?**

Thông thường không cần. Nó là API của Jakarta Mail để nối exception. Ứng dụng chủ yếu nên đọc chuỗi nguyên nhân do thư viện cung cấp.

**5. AuthenticationFailedException có nghĩa mật khẩu chắc chắn sai?**

Không. Có thể do token, AUTH mechanism, account policy hoặc lỗi tạm thời. Cần xem phản hồi và cấu hình provider.

**6. AddressException chứng minh mailbox không tồn tại?**

Không. Nó thường liên quan parse/cú pháp địa chỉ. Mailbox tồn tại hay không là thông tin khác, thường do hệ thống nhận hoặc quá trình bounce cung cấp.

**7. SendFailedException có thể chứa nhiều nhóm recipient?**

Có. API có invalid, validSent và validUnsent addresses. Cần xử lý theo kết quả thực tế thay vì retry toàn bộ.

**8. Tại sao lỗi TLS lại nằm trong MessagingException?**

Jakarta Mail transport có thể wrap các exception mạng/TLS phát sinh khi kết nối hoặc gửi, nên cần xem nested exception.

**9. Có thể lấy SMTP reply code trực tiếp từ MessagingException không?**

MessagingException tổng quát không cung cấp một thuộc tính SMTP reply code chung cho mọi trường hợp. Một số provider exception chuyên biệt có mã này; adapter phải đọc theo implementation hoặc dữ liệu được provider công bố.

**10. Lỗi 4xx có luôn retry không?**

Không. Cần backoff, giới hạn attempts và xem ngữ cảnh. Một lỗi 4xx kéo dài có thể cần cảnh báo hoặc điều tra.

**11. Lỗi 5xx có luôn là địa chỉ sai không?**

Không. Nó có thể là AUTH, sender/policy hoặc nội dung message. Cần giai đoạn SMTP và enhanced status.

**12. Nếu getNextException() trả null thì đã biết nguyên nhân cuối chưa?**

Chưa chắc. Cần xem cause, MailSendException message failures, các log được phép và kết quả provider.

**13. Có nên log toàn bộ stack trace trong production?**

Chỉ khi phù hợp chính sách bảo mật và dung lượng log. Không log credentials, raw MIME hoặc dữ liệu nhạy cảm; ưu tiên sự kiện có cấu trúc và correlation ID.

**14. Vì sao JavaMailSender trả thành công nhưng vẫn có bounce?**

SMTP relay có thể nhận message rồi thất bại ở bước chuyển phát sau đó. SMTP accept và delivery là những mốc khác nhau.

**15. Làm sao tránh gửi trùng khi timeout?**

Không có bảo đảm exactly-once tổng quát với SMTP. Dùng event ID ổn định, outbox, trạng thái UNKNOWN_OUTCOME, đối soát nếu có và thiết kế nội dung chịu được retry.

## 24. Ghi nhớ về MessagingException và nguyên nhân từ Jakarta Mail

**MessagingException là điểm bắt đầu chẩn đoán, không phải kết luận nguyên nhân.** Trong ứng dụng Spring Mail, hãy phân biệt exception phát sinh khi dựng MimeMessage với MailException từ JavaMailSender trong giai đoạn gửi. Đọc subtype, Java cause và **MessagingException.getNextException()**; nếu là **MailSendException**, xem các exception của từng message và kết quả recipient khi có.

**AuthenticationFailedException**, **SendFailedException** và **AddressException** mang ý nghĩa khác nhau. Lỗi xác thực không phải lỗi địa chỉ; lỗi cú pháp địa chỉ không chứng minh mailbox không tồn tại; lỗi gửi tổng quát không chứng minh email chưa được server chấp nhận. SMTP reply code, enhanced status code và phase giúp phân loại nguyên nhân, nhưng có thể thiếu hoặc khác nhau giữa provider.

Hãy chuyển lỗi gốc thành một kết quả chẩn đoán có cấu trúc để tầng điều phối quyết định sửa dữ liệu, tạm dừng tài khoản gửi, retry có backoff hoặc đối soát. Không retry mù, không suy diễn chính xác hơn dữ liệu lỗi thực tế, không log secrets và không đánh đồng **SMTP accepted**, **delivered** và **read**. Đây là nền tảng để Spring Framework Mail vận hành ổn định và xử lý sự cố có thể kiểm chứng.
