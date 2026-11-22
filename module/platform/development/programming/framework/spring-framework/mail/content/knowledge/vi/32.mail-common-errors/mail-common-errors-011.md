# Thử lại mọi exception với cùng một backoff

Trong **Spring Framework Mail**, retry thường được thêm vào sau khi ứng dụng bắt đầu gặp lỗi gửi email: SMTP server bận, kết nối timeout, account hết quyền gửi hoặc người nhận không hợp lệ. Một cách sửa nhanh thường thấy là **bắt mọi exception rồi thử gửi lại sau cùng một khoảng chờ**.

Ví dụ:

~~~java
try {
    javaMailSender.send(message);
} catch (Exception ex) {
    Thread.sleep(5_000);
    javaMailSender.send(message);
}
~~~

Cách làm này có vẻ tăng độ tin cậy, nhưng thực tế có thể gây ra nhiều vấn đề:

- **Sai địa chỉ người nhận** không được sửa chỉ nhờ chờ thêm 5 giây.
- **Sai SMTP password** sẽ tiếp tục tạo các lần AUTH thất bại, có thể gây khóa account.
- **Sai TLS certificate hoặc hostname** cần sửa cấu hình, không phải retry.
- **Rate limit của provider** cần lịch backoff và điều tiết phù hợp với quota; thử lại đồng loạt sau một khoảng cố định có thể tạo đợt tải mới.
- **SMTP 4xx tạm thời** có thể retry, nhưng không phải mọi mã 4xx đều cùng nguyên nhân.
- **SMTP 5xx** có thể là từ chối người nhận, chính sách sender, kích thước thư hoặc lỗi khác nhau; chuyển provider hay retry mù đều có rủi ro.
- **Timeout sau khi SMTP relay nhận DATA** có thể có kết quả chưa xác định. Gửi lại có thể tạo **hai email**.
- **Lỗi khi dựng MimeMessage, đọc attachment hoặc render template** thường cần xử lý trước transport, không phải mở thêm SMTP connection.
- Một vòng lặp sleep/retry trên request thread có thể giữ HTTP request hoặc database transaction rất lâu.
- Retry không có giới hạn khiến worker backlog, chi phí SMTP, log và alerts tăng mạnh.

Bài học này phân tích lỗi thiết kế **“Thử lại mọi exception với cùng một backoff”** trong chương **Lỗi thường gặp** của Spring Framework Mail. Trọng tâm không chỉ là dùng backoff bao nhiêu giây mà là **quyết định loại lỗi nào được retry, điều kiện nào đủ an toàn để retry, khi nào phải dừng, và khi nào phải đối soát kết quả SMTP trước khi làm gì tiếp theo**.

> Nguyên tắc trung tâm: **retry là một quyết định dựa trên ngữ nghĩa lỗi và trạng thái gửi, không phải phản xạ tự động của catch(Exception)**. Cùng là một exception được ném từ lời gọi gửi thư, hành động đúng có thể là retry, sửa cấu hình, sửa dữ liệu, hoãn vì rate limit, hoặc giữ lại để đối soát tránh gửi trùng.

## 1. Vì sao retry mọi exception là một anti-pattern?

Trong Spring Framework Mail, lỗi có thể phát sinh ở những tầng khác nhau:

~~~text
Business event / outbox
       |
       v
Validate recipient and sender
       |
       v
Render template
       |
       v
Build MIME / load attachment
       |
       v
DNS / TCP connection
       |
       v
SMTP STARTTLS / AUTH
       |
       v
MAIL FROM / RCPT TO
       |
       v
DATA / final SMTP reply
       |
       v
Relay queues message
       |
       v
Downstream delivery / bounce
~~~

Một exception ở bước render khác một exception ở bước SMTP AUTH. Một lỗi RCPT TO khác timeout khi đang chờ final reply sau DATA. Retry tất cả theo cùng một cơ chế sẽ che mất bối cảnh.

### 1.1. Retry không sửa một nguyên nhân cố định

Một lỗi recipient sai cú pháp hoặc mật khẩu đã bị thu hồi có thể xảy ra 10.000 lần giống hệt. Nếu worker tiếp tục thử, hệ thống tiêu thụ tài nguyên nhưng không tăng xác suất gửi thành công một cách đáng kể.

### 1.2. Retry có thể khiến sự cố lan rộng

Khi SMTP provider quá tải, tất cả workers cùng retry sau 5 giây sẽ tạo các **đỉnh lưu lượng đồng bộ**. Provider lại từ chối hoặc throttle, rồi các workers đồng loạt retry thêm. Đó là hiện tượng retry storm.

### 1.3. Retry có thể làm sai tính đúng đắn nghiệp vụ

Nếu provider đã chấp nhận message nhưng client không thấy phản hồi cuối, lần retry có thể khiến người nhận nhận email hai lần. Trường hợp này không chỉ là bài toán hiệu năng.

### 1.4. Cần ba câu hỏi trước mỗi lần retry

1. **Nguyên nhân gì?** Lỗi dữ liệu, cấu hình, provider tạm thời, rate limit hay kết quả chưa rõ?
2. **Có an toàn gửi lại không?** Đã chắc chắn relay chưa chấp nhận message hay chưa?
3. **Có còn đáng gửi không?** Đã hết deadline, token đã hết hạn, quá maxAttempts hoặc business event đã bị hủy chưa?

## 2. Phân biệt retry, reschedule, failover và resend

Những hành động thường bị gộp vào một từ “gửi lại”:

| Hành động | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Retry** | Thử lại cùng mail intent sau một lỗi | Gửi lại khi server tạm báo 421 |
| **Reschedule** | Chuyển thời gian xử lý sang tương lai | RETRY_WAIT tới nextAttemptAt |
| **Failover** | Chuyển sang SMTP provider/account khác | Provider A outage, dùng B nếu được phép |
| **Reconcile** | Điều tra trạng thái khi outcome chưa rõ | Hỏi provider về một submission khả nghi |
| **Manual resend** | Chủ đích gửi thêm một email mới | Nhân viên hỗ trợ gửi lại hóa đơn |
| **Re-render** | Tạo lại HTML/MIME | Template version hoặc token cần đổi |

### 2.1. Retry không có nghĩa re-render

Nếu outbox đã lưu một snapshot nội dung hợp lệ, retry transport có thể dùng lại nội dung đó. Render lại không cần thiết có thể thay đổi dữ liệu trong cùng một mail event.

### 2.2. Failover không luôn an toàn hơn retry cùng provider

Nếu provider A đã nhận message nhưng kết nối mất sau DATA, chuyển sang provider B cũng có thể gửi trùng. Đổi provider không xóa khả năng relay A đã chấp nhận.

### 2.3. Manual resend phải có audit

Nếu người dùng chủ động yêu cầu gửi lại hóa đơn hoặc email xác nhận, thao tác đó nên được ghi thành hành động nghiệp vụ mới có kiểm soát, thay vì tùy tiện đổi status SENT thành PENDING.

## 3. Các loại exception trong Spring Mail

**JavaMailSender** có thể ném những exception thuộc hệ phân cấp **org.springframework.mail.MailException** (unchecked). Những loại thường gặp:

| Spring exception | Bối cảnh thường gặp | Ý nghĩa đối với retry |
| --- | --- | --- |
| **MailAuthenticationException** | Lỗi xác thực SMTP | Điều tra credential/account; không retry mù |
| **MailSendException** | Lỗi khi gửi một hoặc nhiều messages | Phải đọc nguyên nhân và per-message result |
| **MailPreparationException** | Không thể chuẩn bị message | Sửa dữ liệu/template/resource hoặc đánh giá nguyên nhân |
| **MailParseException** | Lỗi diễn giải/parse mail message | Không tự retry nếu đầu vào cố định |
| **MailException** khác | Wrapper/implementation phụ thuộc đường gọi | Phân loại theo cause và phase thực tế |

Không thể dựa vào tên **MailSendException** để kết luận “lỗi này có thể retry”. Bên trong nó có thể là lỗi mạng tạm thời hoặc recipient bị từ chối vĩnh viễn.

### 3.1. Jakarta Mail là một tầng khác

Trong hệ Spring Framework 6 / Boot 3 thường dùng namespace:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.internet.AddressException;
~~~

Spring Mail có thể bọc **MessagingException** hoặc provider-specific exceptions vào MailException. Cấu trúc thực tế tùy lệnh gửi, provider và Jakarta Mail implementation.

### 3.2. Không chỉ xem exception class ngoài cùng

~~~text
MailSendException
  |
  +-- MessagingException
        |
        +-- SMTP server reply / linked exception
              |
              +-- IOException / address-specific information
~~~

Chỉ nhìn **ex.getClass().getSimpleName()** có thể đánh mất thông tin SMTP reply, recipient và phase.

### 3.3. Spring Mail exception thường không phải lỗi cuối cùng của delivery

Khi send() trả bình thường, relay có thể đã chấp nhận message nhưng downstream MX vẫn có thể bounce sau đó. Một delivery webhook/bounce event nếu có là luồng tín hiệu khác với synchronous Spring Mail exception.

## 4. Duyệt cause chain và MessagingException linked exceptions

**MessagingException** có API **getNextException()** ngoài **getCause()**. Nếu chỉ đi qua Throwable.getCause(), hệ thống có thể bỏ qua thông tin nằm ở linked exception chain.

Ví dụ utility an toàn để thu thập exception graph:

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public final class MailThrowableGraph {

    private MailThrowableGraph() {}

    public static List<Throwable> flatten(
            Throwable root
    ) {
        List<Throwable> result = new ArrayList<>();
        if (root == null) {
            return result;
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Map<Throwable, Boolean> seen =
                new IdentityHashMap<>();

        pending.add(root);

        while (!pending.isEmpty() && result.size() < 64) {
            Throwable current = pending.removeFirst();

            if (seen.put(current, Boolean.TRUE) != null) {
                continue;
            }

            result.add(current);

            Throwable cause = current.getCause();
            if (cause != null) {
                pending.addLast(cause);
            }

            if (current instanceof MessagingException mail) {
                Exception next = mail.getNextException();

                if (next != null) {
                    pending.addLast(next);
                }
            }
        }

        return result;
    }
}
~~~

### 4.1. Vì sao có IdentityHashMap?

Exception graph có thể chứa cùng một object qua nhiều liên kết hoặc các chu kỳ bất thường. Kiểm tra theo identity và giới hạn 64 nodes giúp tránh traversal vô hạn.

### 4.2. Flatten không tự quyết định retry

Utility chỉ tìm các node exception. Một classifier còn cần **SMTP phase**, reply code, provider context và việc relay có thể đã chấp nhận message không.

### 4.3. Không log nguyên cả exception graph ở mọi cấp

Stack traces và provider reply text có thể chứa địa chỉ email, host hoặc metadata nội bộ. Ghi errorCategory, mã SMTP và correlation ID theo nhu cầu; full diagnostic chỉ ở môi trường có phân quyền/sanitize thích hợp.

## 5. Ma trận quyết định retry theo loại lỗi

Một ma trận khởi đầu:

| Loại lỗi | Ví dụ | Hành động mặc định |
| --- | --- | --- |
| **Invalid recipient syntax** | AddressException | STOP và sửa dữ liệu |
| **Recipient permanently rejected** | 5.1.1 với ngữ cảnh phù hợp | STOP/suppress địa chỉ theo policy |
| **SMTP AUTH invalid** | 535, credentials sai | STOP; sửa account/secret |
| **TLS/certificate misconfiguration** | SSLHandshakeException | STOP; sửa trust/hostname |
| **Missing attachment/template** | Resource lỗi ổn định | STOP hoặc sửa dữ liệu |
| **Provider throttling** | Phản hồi throttle đã phân loại | RETRY với provider-aware delay |
| **Temporary SMTP rejection** | 421/450/451 theo ngữ cảnh | RETRY có backoff |
| **Connection failed before submission** | ConnectException trước DATA | RETRY nếu có bằng chứng chưa accepted |
| **Timeout after DATA** | Mất final reply | HOLD/RECONCILE, tránh retry mù |
| **Partial recipient result** | Một số RCPT TO bị từ chối | RETRY có chọn lọc, không gửi cả batch |
| **Unknown/unclassified** | Không đủ phase/reply | INVESTIGATE/HOLD hoặc policy thận trọng |
| **Deadline expired** | Link reset/OTP hết hạn | STOP dù lỗi có tính tạm thời |
| **Max attempts exhausted** | Quá retry budget | STOP/DEAD_LETTER |

Đây là **chính sách gợi ý**, không phải quy tắc tự động áp dụng cho mọi hệ thống. Một mã SMTP hoặc exception class không đủ tự mình chứng minh safety của retry.

### 5.1. Category và action là hai trường riêng

Ghi **errorCategory=rate_limit** và **retryAction=reschedule**. Không biến mọi category thành boolean retryable cố định nếu ngữ cảnh khác nhau.

### 5.2. Backoff không thay thế việc phân loại

Kể cả đặt khoảng chờ một giờ, retry một password chắc chắn sai vẫn vô ích. Phân loại và safety check phải đứng trước phép tính delay.

### 5.3. Retry cần xét nội dung email

Một email marketing có thể trì hoãn lâu; một OTP sắp hết hạn không nên đợi 30 phút. Policy nên dựa cả **mailKind**, deadline và mức quan trọng.

## 6. Sai địa chỉ người nhận không tự hết sau backoff

Ví dụ:

~~~text
Input recipient: "alice@@example.org"
Stage: address validation / MIME prepare
Category: invalid_address_syntax
Recommended: stop and correct data
~~~

Trong Jakarta Mail, một **AddressException** có thể xuất hiện khi parse/validate địa chỉ.

### 6.1. Cú pháp hợp lệ không chứng minh mailbox tồn tại

InternetAddress có thể kiểm tra syntax theo mức phù hợp, nhưng nó không xác minh server đích thực sự có mailbox đó.

### 6.2. SMTP 550 cần ngữ cảnh

Không phải mọi 550 là “mailbox không tồn tại”. Nó có thể phản ánh sender policy hoặc content restrictions. Nếu enhanced code là 5.1.1 và server reply thực sự nói user unknown, retry thường không hữu ích, nhưng cần phân loại từ nguồn tin đáng tin cậy.

### 6.3. Không retry invalid recipient qua nhiều providers

Gửi cùng địa chỉ không hợp lệ qua provider A, B, C chỉ tăng lỗi và chi phí. Nên giữ trạng thái recipient-level để tránh gửi lại mù.

## 7. Lỗi xác thực SMTP cần sửa cấu hình

Ví dụ:

~~~text
SMTP AUTH -> 535
Spring: MailAuthenticationException
Category: auth_invalid
Action: stop, investigate secret/account
~~~

Có thể do:

- Username/password đã đổi.
- SMTP account bị khóa/vô hiệu hóa.
- Provider yêu cầu App Password, OAuth hoặc mode AUTH khác.
- Secret không được deploy đúng.
- Account không có quyền gửi theo policy.

### 7.1. Vì sao retry 5 giây một lần nguy hiểm?

Nó tạo nhiều lần đăng nhập thất bại, có thể kích hoạt lockout, abuse alerts hoặc rate limit. Một sự cố secret có thể biến thành outage dài hơn.

### 7.2. AUTH temporary khác invalid credential

Một số mã SMTP liên quan AUTH có thể phản ánh sự cố dịch vụ tạm thời (ví dụ 454 trong ngữ cảnh phù hợp), khác với credential sai ổn định. Cần phân loại theo reply và provider semantics thay vì coi mọi AuthenticationFailedException giống nhau.

### 7.3. Không bật debug làm lộ credential

Đừng log password, bearer token hoặc AUTH payload. Chỉ ghi accountAlias, providerAlias và errorCategory đã được allowlist.

### 7.4. Retry sau khi sửa secret

Sau khi cấu hình được khắc phục, có thể cho những mail events chưa hết hạn quay lại queue theo một quy trình có kiểm soát; không cần giữ worker liên tục retry trong suốt outage.

## 8. Lỗi TLS không thể được giải bằng chờ đồng loạt

Các lỗi ví dụ:

~~~text
SSLHandshakeException
PKIX path building failed
No subject alternative name matching hostname
Unsupported protocol / cipher mismatch
~~~

Một certificate không hợp lệ sẽ không tự trở nên hợp lệ vì chờ thêm 10 giây, trừ khi hạ tầng/provider thực sự thay đổi.

### 8.1. Cần sửa root cause

Kiểm tra endpoint, STARTTLS vs implicit TLS, truststore, certificate chain, hostname verification và supported protocols.

### 8.2. Không tắt certificate validation để retry thành công

Vô hiệu hostname checking hoặc bỏ qua trust validation có thể dẫn tới kết nối không an toàn. Đây không phải chiến lược retry.

### 8.3. Có thể có TLS outage tạm thời, nhưng không đoán bừa

Một edge endpoint tạm lỗi có thể phục hồi, nhưng policy vẫn cần phân loại và giới hạn retry. Nếu lỗi là certificate/hostname mismatch, action mặc định nên là sửa cấu hình.

## 9. Lỗi chuẩn bị mail khác lỗi transport

Ví dụ:

- Render template thất bại.
- Missing placeholder quan trọng.
- Subject chứa dữ liệu không được phép.
- Attachment path không tồn tại.
- Tệp vượt giới hạn.
- Nội dung MIME không hợp lệ.
- InputStreamResource không thể mở lại.
- Bị chặn vì tenant không có quyền dùng From identity.

Những lỗi này xảy ra **trước hoặc trong quá trình tạo/serialize message**, không nhất thiết là sự cố SMTP server.

### 9.1. Lỗi có thể xuất hiện muộn

Một resource đính kèm có thể chỉ được đọc khi Jakarta Mail serialize message trong send(). Khi đó lỗi I/O có thể xuất hiện bên trong MailSendException dù nguyên nhân là nguồn attachment.

### 9.2. Không gán mọi IOException là provider down

Nếu file nằm trên object storage hoặc local disk, một IOException có thể đến từ resource. Instrument phase và resource loading giúp phân loại đúng.

### 9.3. Lỗi dữ liệu phải được sửa hoặc terminal

Retry không nên xoay vòng cùng template với dữ liệu đầu vào sai mãi mãi. Cần kiểm tra điều kiện retry, nguồn dữ liệu, deadline và quyền truy cập.

## 10. SMTP reply codes: 4xx và 5xx

Trong SMTP, mã phản hồi thường có chữ số đầu thể hiện lớp trạng thái.

| Nhóm | Ý nghĩa chung | Retry? |
| --- | --- | --- |
| **2xx** | Positive completion | Không phải lỗi để retry |
| **3xx** | Positive intermediate | Cần tiếp tục protocol |
| **4xx** | Transient negative completion | Có thể retry sau thời gian phù hợp |
| **5xx** | Permanent negative completion | Thường dừng hoặc sửa điều kiện |
| **Không có reply** | Connection/timeout | Phải xét phase và độ chắc chắn |

### 10.1. 421

Thường liên quan service not available hoặc đóng kết nối. Có thể là tín hiệu sự cố tạm thời; cần xem provider context, volume và giai đoạn.

### 10.2. 450, 451, 452

Có thể phản ánh mailbox tạm không dùng được, local processing error hoặc không đủ system storage theo ngữ cảnh SMTP. Không mặc định cả ba cùng một delay.

### 10.3. 535

Thông thường liên quan AUTH credentials invalid hoặc không được chấp nhận. Đây không phải lỗi recipient và không nên retry dồn dập.

### 10.4. 550, 552, 553, 554

Có thể biểu thị recipient/policy/size/transaction failure, tùy vị trí lệnh và enhanced code. Không chỉ phân loại bằng 3 chữ số mà bỏ qua ngữ cảnh.

### 10.5. 4xx không luôn là “an toàn gửi lại”

Nếu response bị mất sau DATA, client không biết relay đã accept hay chưa. Việc có một lỗi mạng ở thời điểm đó cần được quản lý như **ambiguous outcome**, dù các attempts khác có thể retry sau một SMTP 4xx rõ ràng.

## 11. Enhanced status codes giúp phân loại sâu hơn

Một số phản hồi SMTP cung cấp mã mở rộng theo cấu trúc:

~~~text
5.1.1  Mailbox/user not found (common usage)
5.7.8  Authentication credentials invalid (common usage)
4.7.0  Temporary policy/security-related condition
4.2.2  Mailbox full (may be temporary)
~~~

### 11.1. Không diễn giải enhancement như chân lý tuyệt đối

Providers có thể có mapping và thông báo khác nhau. Nên giữ **SMTP stage**, mã 3 chữ số, enhanced code nếu có, và provider-specific documented semantics.

### 11.2. Không dùng raw reply text làm retry key

Một reply có thể chứa recipient hoặc host cụ thể. Nếu dùng toàn chuỗi làm key/tag, policy khó ổn định và metrics cardinality tăng.

### 11.3. Phân loại ở nơi có dữ liệu tốt nhất

JavaMailSender không có API chuẩn luôn trả đầy đủ SMTP reply và phase cho mọi provider. Tầng Jakarta Mail/provider exception hoặc integration chuyên biệt có thể có chi tiết hơn; nếu không có thì ghi **unknown** thay vì bịa.

## 12. Rate limit cần cách chờ khác các lỗi tạm thời thông thường

Nếu provider giảm quota hoặc đang throttle, một retry sau 2 giây có thể sớm hơn thời điểm provider sẵn sàng.

Ví dụ:

~~~text
Provider: smtp-provider-a
Account: transactional
Error: throttled
Recommended by local policy: backoff at least 60s
Current concurrency: 50 connections
~~~

### 12.1. Không dùng một delay cho mọi account/provider

Provider A có quota khác provider B; account security có thể có priority khác marketing. Backoff có thể theo **providerAlias/accountAlias/mailKind** và capacity policy.

### 12.2. Đừng coi SMTP có header Retry-After chuẩn như HTTP

HTTP 429 có thể kèm **Retry-After**. SMTP không có một header Retry-After chuẩn dùng thống nhất cho mọi reply như HTTP. Nếu provider có hướng dẫn delay riêng, đó phải là dữ liệu **provider-specific và đã được kiểm tra**.

### 12.3. Rate limiting và backoff là hai lớp khác nhau

- Backoff: quyết định **khi nào** event được retry.
- Rate limiting: quyết định **tốc độ** và **độ song song** của attempts trên provider/account.

Retry đúng delay mà vẫn cho 1.000 workers cùng gửi có thể tiếp tục bị throttle.

### 12.4. Retry-After nếu dùng qua provider HTTP API

Nếu hệ thống chọn một email API thay vì SMTP, có thể áp dụng HTTP Retry-After khi provider cho phép và response đáng tin cậy. Không sao chép xử lý HTTP sang SMTP một cách mù quáng.

## 13. Lỗi mạng: phân biệt trước và sau khi submit

Một số exceptions:

~~~text
UnknownHostException
ConnectException
SocketTimeoutException
SocketException: Connection reset
SSLException
IOException during MIME transfer
~~~

Những class này **không tự cho biết** relay đã nhận message hay chưa.

### 13.1. DNS/connection failure trước SMTP transaction

Nếu chắc chắn không kết nối được, không có message nào được relay chấp nhận từ attempt đó. Retry với backoff có thể phù hợp sau khi xem health provider.

### 13.2. Timeout khi STARTTLS/AUTH

Thường xảy ra trước DATA, nhưng cần biết có phải đang xử lý cùng một SMTP session hay không. Không tự suy phase chỉ từ tên IOException.

### 13.3. Timeout khi truyền DATA

Client có thể đã truyền một phần message. Provider có thể từ chối hoặc connection drop; cần xử lý theo mức chắc chắn về acceptance.

### 13.4. Mất final reply sau DATA

Đây là trường hợp quan trọng nhất: provider có thể đã chấp nhận message nhưng lời đáp cuối không tới client. Không thể dùng một backoff cố định để giải quyết tính không chắc chắn này.

## 14. UNKNOWN_OUTCOME và nguy cơ gửi trùng

Một timeline:

~~~text
Client                            SMTP relay
  |-- MAIL FROM ---------------------->|
  |<-- 250 ---------------------------|
  |-- RCPT TO ------------------------>|
  |<-- 250 ---------------------------|
  |-- DATA -------------------------->|
  |<-- 354 ---------------------------|
  |-- message bytes + final dot ----->|
  |                                   |
  |        relay may commit mail      |
  |<--- final 250 reply lost ---------X
  |
  +-- SocketTimeoutException
~~~

Ứng dụng quan sát exception, nhưng **không biết chắc** relay đã chấp nhận message chưa.

### 14.1. Vì sao retry không an toàn?

Nếu relay đã accept, retry cùng provider hoặc provider dự phòng có thể tạo email thứ hai. Cùng MIME Message-ID không bảo đảm SMTP relay sẽ deduplicate.

### 14.2. Hành động phù hợp

Một số lựa chọn theo yêu cầu nghiệp vụ:

- Chuyển sang **UNKNOWN_OUTCOME**.
- Lưu mailEventId/attemptId/provider/phase đủ để đối soát.
- Kiểm tra provider dashboard/API/logs nếu có dữ liệu đáng tin.
- Chờ một khoảng observation window.
- Manual review hoặc policy chấp nhận duplicate risk.
- Nếu retry, ghi rõ đây là một quyết định có rủi ro, không phải “chắc chắn chưa gửi”.

### 14.3. Không đánh đồng unknown với permanent failure

Không có bằng chứng email bị từ chối vĩnh viễn. Nhưng cũng không có bằng chứng an toàn để gửi lại ngay. Cần trạng thái riêng.

## 15. Partial recipient acceptance

Với một MimeMessage có nhiều recipients:

~~~text
RCPT TO alice@example.net  -> accepted
RCPT TO bob@example.net    -> rejected
RCPT TO carol@example.net  -> accepted
~~~

Jakarta Mail có **SendFailedException** có thể cung cấp:

~~~java
SendFailedException ex = /* received exception */;
jakarta.mail.Address[] invalid =
        ex.getInvalidAddresses();

jakarta.mail.Address[] validSent =
        ex.getValidSentAddresses();

jakarta.mail.Address[] validUnsent =
        ex.getValidUnsentAddresses();
~~~

### 15.1. Không retry toàn bộ recipient list

Nếu một số người đã được relay chấp nhận, gửi lại cả danh sách có thể tạo duplicate ở nhóm đó.

### 15.2. Per-recipient outcome

Ứng dụng có thể cần lưu trạng thái recipient-level trong storage có quyền hạn chế, hoặc thiết kế **một mail event cho một recipient** nếu gửi email giao dịch/cá nhân hóa.

### 15.3. ValidSent không chứng minh inbox delivered

Đây là trạng thái do client/provider cung cấp về thao tác send, không phải xác nhận người nhận đã mở email.

### 15.4. Không log toàn danh sách addresses

Thông tin exception có thể chứa recipients. Khi đo metrics, chỉ dùng category/count phù hợp, không dùng địa chỉ làm label.

## 16. Batch send và MailSendException.getMessageExceptions()

Spring JavaMailSender có thể xử lý nhiều mail messages trong một lần gọi. Khi xảy ra lỗi từng message, **MailSendException** có thể cung cấp thông tin:

~~~java
import org.springframework.mail.MailSendException;
import java.util.Map;

void inspect(MailSendException ex) {
    Map<Object, Exception> failures =
            ex.getFailedMessages();

    Exception[] messages =
            ex.getMessageExceptions();

    int failedCount = failures.size();
    int exceptionCount = messages.length;

    // Dùng để ghi phân loại có kiểm soát;
    // không mặc định retry toàn bộ batch.
}
~~~

### 16.1. Một exception ngoài cùng có thể đại diện nhiều lỗi

Có thể một phần messages đã gửi thành công, phần khác thất bại. Retry toàn bộ batch có thể gửi trùng nhóm đã thành công.

### 16.2. Không coi failedMessages là danh sách toàn bộ kết quả

Nếu API trả thông tin messages bị lỗi, điều đó không tự tạo một bảng kết quả chính xác của mọi recipient hoặc downstream delivery. Cần biết chính xác contract của sender implementation.

### 16.3. Dùng batch với mục đích rõ

Một message/recipient hoặc một outbox event cho recipient thường dễ retry và đối soát hơn ở hệ thống giao dịch. Khi batch để tăng throughput, phải quản lý partial outcomes.

## 17. Retry budget: số lần, deadline, thời gian tổng

Một policy không thể chỉ có “sleep 5 giây”. Nên có:

- **maxAttempts:** số lần submit tối đa cho event.
- **firstAttemptAt:** mốc bắt đầu retry lifecycle.
- **deadlineAt:** sau thời điểm này email không còn giá trị.
- **baseDelay:** nền backoff theo category.
- **maxDelay:** trần delay do ứng dụng đặt.
- **jitter:** tránh retries đồng bộ.
- **provider cooldown:** tránh provider/account đang outage.
- **rate limit budget:** tổng concurrency/throughput.
- **unknown outcome policy:** quy tắc đối soát.
- **terminal handling:** FAILED, SUPPRESSED hoặc dead-letter.

### 17.1. Attempt cap là giới hạn thực

Nếu maxAttempts=5, sau 5 lần gửi lỗi không nên tiếp tục tạo một scheduled attempt thứ 6 chỉ vì cron đánh thức worker.

### 17.2. Deadline là điều kiện độc lập

Một email reset password có token hết hạn sau 10 phút không nên được gửi 30 phút sau, dù SMTP đã phục hồi.

### 17.3. Retry budget có thể theo provider và hệ thống

Nếu cả nghìn messages thất bại do provider down, mọi event đều có retry budget riêng nhưng tổng attempts cần được kiểm soát bằng circuit breaker/rate limiter.

## 18. Backoff cố định và exponential backoff

Giả sử một event lỗi nhiều lần.

**Fixed backoff:**

~~~text
Attempt 1 -> wait 5s
Attempt 2 -> wait 5s
Attempt 3 -> wait 5s
Attempt 4 -> wait 5s
~~~

**Exponential backoff (ví dụ base=2s):**

~~~text
Attempt 1 -> wait 2s
Attempt 2 -> wait 4s
Attempt 3 -> wait 8s
Attempt 4 -> wait 16s
Attempt 5 -> wait 32s
~~~

Một công thức thường dùng:

\[
d_n = \min(d_{\max}, d_{\text{base}}\times 2^{n-1})
\]

trong đó n là số attempt vừa thất bại, bắt đầu từ 1.

### 18.1. Exponential không tự giải quyết mọi lỗi

Exponential backoff vẫn không thích hợp để sửa invalid address hoặc AUTH password sai. **Phân loại trước, tính delay sau.**

### 18.2. Max delay và max attempts khác nhau

Trần 15 phút cho delay không tự ngăn một event retry trong nhiều ngày. Cần attempt cap và deadline.

### 18.3. Backoff không đồng nghĩa sleep thread

Tốt hơn là lưu **nextAttemptAt** và để scheduler/outbox worker xử lý sau, thay vì Thread.sleep khi giữ transaction, HTTP thread hoặc worker slot.

## 19. Jitter tránh retry storm

Nếu 10.000 events cùng thất bại lúc 12:00:00 và cùng dùng delay 30 giây, chúng có thể retry gần đồng loạt lúc 12:00:30.

**Full jitter** có thể lấy một giá trị ngẫu nhiên trong khoảng từ 0 đến exponential delay đã capped:

\[
d_n^{\text{jitter}} \sim U(0,d_n)
\]

Ví dụ base 10 giây, exponential delay của một lần là 40 giây; các events có thể được hẹn trong khoảng 0–40 giây thay vì cùng lúc.

### 19.1. Không dùng jitter để bỏ qua provider minimum delay

Nếu provider có một hướng dẫn đợi ít nhất 60 giây đáng tin cậy, không nên lấy full jitter rồi retry sau 2 giây. Kết hợp với giới hạn **not-before** theo provider.

### 19.2. Jitter cần dữ liệu ngẫu nhiên phù hợp

Trong code production có thể dùng ThreadLocalRandom cho scheduling jitter thông thường; unit test nên inject nguồn random hoặc fake jitter để assert deterministic.

### 19.3. Jitter không thay thế rate limiter

Giãn retries trong thời gian chỉ giảm đồng bộ. Nếu tổng load vẫn vượt quota, cần admission/rate-control riêng.

## 20. Provider cooldown, circuit breaker và backpressure

Khi SMTP provider bị lỗi hệ thống, retry từng email không đủ.

~~~text
Provider A outage
     |
     +-- Circuit breaker OPEN
     |
     +-- New attempts paused/routed if allowed
     |
     +-- Outbox events remain durable
     |
     +-- Controlled probe/half-open
     |
     +-- Resume at bounded rate
~~~

### 20.1. Circuit breaker xử lý sức khỏe provider

Một breaker có thể được điều khiển bởi tỷ lệ lỗi hệ thống, timeout hoặc health probes; **không nên** tính recipient 550 là provider outage rồi mở breaker toàn hệ thống.

### 20.2. Rate limiting theo account/provider

Provider A có quota 20 requests/giây không được vượt chỉ vì có 10 worker pods, mỗi pod tự cho 20 requests/giây. Cần chia ngân sách hoặc dùng shared limiter theo phạm vi quota.

### 20.3. Khi breaker OPEN

Không xóa mail outbox event. Nó có thể ở RETRY_WAIT hoặc trạng thái chờ khác cho đến khi provider có thể thử lại; tránh retry loop nóng.

### 20.4. Half-open không nên xả toàn bộ backlog

Khi provider vừa phục hồi, giới hạn số probes và tốc độ tăng traffic để không tạo outage lần hai.

## 21. Khác biệt giữa backoff theo category và theo business priority

Một bảng tham khảo **chỉ để minh họa**, không phải khuyến nghị số giây cho mọi provider:

| Nhóm | Base delay gợi ý để mô hình | Max delay | Điều kiện |
| --- | --- | --- | --- |
| Connection failure trước DATA | Vài giây | Vài phút | Có bằng chứng chưa accept |
| SMTP temporary 4xx | Vài chục giây | Nhiều phút | Reply tạm thời rõ |
| Provider throttling | Hàng chục giây đến phút | Theo quota/cooldown | Tôn trọng provider guidance |
| Temporary auth infrastructure | Theo runbook | Có giới hạn | Không phải invalid credentials |
| Invalid address | Không retry | — | Fix data |
| AUTH invalid | Không retry | — | Fix secret/account |
| TLS misconfiguration | Không retry | — | Fix transport security |
| Ambiguous after DATA | Không auto-retry | — | Reconcile |
| Deadline expired | Không retry | — | Suppress/terminal |

### 21.1. Ưu tiên business không được bỏ qua safety

Email OTP có tính thời gian cao, nhưng timeout sau DATA vẫn có duplicate risk. Priority chỉ thay đổi deadline/capacity policy, không biến một outcome mơ hồ thành “chắc chắn chưa gửi”.

### 21.2. Không ưu tiên vô hạn email quan trọng

Một provider down cần fail-fast/backpressure, không cho security messages retry vô hạn mỗi 100 ms chỉ vì chúng quan trọng.

## 22. Thiết kế FailureFacts tách exception khỏi quyết định

Một thiết kế rõ hơn catch(Exception) là chuẩn hóa dữ liệu từ adapter:

~~~text
FailureFacts:
  errorKind
  smtpPhase
  smtpReplyCode
  enhancedStatusCode
  providerAlias
  accountAlias
  definitelyNotAccepted
  providerMinimumDelay
  attemptNumber
  eventDeadline
~~~

Trong đó:

- **errorKind:** taxonomy hữu hạn như AUTH_INVALID, THROTTLED, TEMPORARY_SMTP.
- **smtpPhase:** connect, starttls, auth, mail_from, rcpt_to, data, after_data, unknown.
- **definitelyNotAccepted:** chỉ true khi có căn cứ đáng tin rằng relay chưa accept message cho attempt đó.
- **providerMinimumDelay:** thời gian tối thiểu từ provider/API nếu có hướng dẫn đáng tin cậy.
- **eventDeadline:** mốc nghiệp vụ không còn muốn gửi nữa.

### 22.1. Không suy definitelyNotAccepted từ exception class đơn lẻ

Một SocketTimeoutException không thể chứng minh kết quả SMTP nếu không biết phase. Nếu thiếu dữ liệu, dùng false hoặc UNKNOWN, không tự đặt true.

### 22.2. Phân loại lỗi là một component riêng

Tầng adapter quan sát/thu thập exception và SMTP phase. Tầng retry planner quyết định hành động từ dữ liệu chuẩn hóa. Tầng outbox ghi trạng thái bền vững.

### 22.3. Không dùng regex duy nhất trên getMessage()

Provider đổi wording hoặc localization có thể làm policy sai. Ưu tiên structured replies/enhanced codes, exception types và phase từ nguồn đáng tin.

## 23. Ví dụ Java: RetryPlanner theo loại lỗi

Ví dụ dưới đây minh họa một **decision engine thuần Java**, không trực tiếp mở SMTP connection, để unit test dễ dàng. Nó giả định tầng transport classifier đã xác định **FailureKind** và cờ **definitelyNotAccepted** dựa trên thông tin đáng tin cậy.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetryPlanner {

    public enum FailureKind {
        INVALID_ADDRESS,
        AUTH_INVALID,
        TLS_CONFIGURATION,
        MISSING_RESOURCE,
        PERMANENT_SMTP,
        TEMPORARY_SMTP,
        THROTTLED,
        CONNECT_BEFORE_DATA,
        AMBIGUOUS_AFTER_DATA,
        UNKNOWN
    }

    public enum Action {
        RETRY_LATER,
        STOP,
        RECONCILE
    }

    public record FailureFacts(
            FailureKind kind,
            boolean definitelyNotAccepted,
            Duration providerMinimumDelay
    ) {}

    public record Decision(
            Action action,
            Instant nextAttemptAt,
            String reasonCode
    ) {}

    @FunctionalInterface
    public interface Jitter {
        long pickMillis(long maxInclusive);
    }

    public static Jitter randomJitter() {
        return max -> ThreadLocalRandom.current()
                .nextLong(max + 1);
    }

    private final Clock clock;
    private final Jitter jitter;
    private final int maxAttempts;

    public MailRetryPlanner(
            Clock clock,
            Jitter jitter,
            int maxAttempts
    ) {
        this.clock = Objects.requireNonNull(clock);
        this.jitter = Objects.requireNonNull(jitter);

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive"
            );
        }

        this.maxAttempts = maxAttempts;
    }

    public Decision decide(
            FailureFacts failure,
            int attemptsCompleted,
            Instant deadline
    ) {
        Objects.requireNonNull(failure);
        Objects.requireNonNull(deadline);

        Instant now = clock.instant();

        if (now.isAfter(deadline) || now.equals(deadline)) {
            return new Decision(
                    Action.STOP, null, "deadline_expired"
            );
        }

        if (attemptsCompleted >= maxAttempts) {
            return new Decision(
                    Action.STOP, null, "max_attempts"
            );
        }

        switch (failure.kind()) {
            case INVALID_ADDRESS:
            case AUTH_INVALID:
            case TLS_CONFIGURATION:
            case MISSING_RESOURCE:
            case PERMANENT_SMTP:
                return new Decision(
                        Action.STOP, null, "non_retryable"
                );

            case AMBIGUOUS_AFTER_DATA:
            case UNKNOWN:
                return new Decision(
                        Action.RECONCILE, null,
                        "submission_not_confirmed"
                );

            default:
                break;
        }

        if (!failure.definitelyNotAccepted()) {
            return new Decision(
                    Action.RECONCILE, null,
                    "acceptance_uncertain"
            );
        }

        long baseMillis = switch (failure.kind()) {
            case THROTTLED -> 30_000L;
            case TEMPORARY_SMTP -> 10_000L;
            case CONNECT_BEFORE_DATA -> 2_000L;
            default -> throw new IllegalStateException(
                    "Unrecognized retry category"
            );
        };

        long capMillis = Duration.ofMinutes(15).toMillis();
        long window = baseMillis;

        for (int i = 1;
             i < Math.min(attemptsCompleted, 10);
             i++) {
            window = Math.min(capMillis, window * 2);
        }

        long jitterDelay = jitter.pickMillis(window);

        Duration minimum = failure.providerMinimumDelay() == null
                ? Duration.ZERO
                : failure.providerMinimumDelay();

        if (minimum.isNegative()) {
            minimum = Duration.ZERO;
        }

        long delayMillis = Math.max(
                jitterDelay,
                minimum.toMillis()
        );

        Instant next = now.plusMillis(delayMillis);

        if (!next.isBefore(deadline)) {
            return new Decision(
                    Action.STOP, null,
                    "retry_would_miss_deadline"
            );
        }

        return new Decision(
                Action.RETRY_LATER,
                next,
                "retryable_transient"
        );
    }
}
~~~

### 23.1. Action có ba nhánh

- **RETRY_LATER:** lưu nextAttemptAt, không sleep thread.
- **STOP:** terminal failure/suppression theo nghiệp vụ.
- **RECONCILE:** kết quả không đủ chắc để auto-resubmit.

### 23.2. definitelyNotAccepted là điều kiện safety

Ngay cả khi kind=TEMPORARY_SMTP, nếu chưa biết relay có accept message hay không, planner đưa về RECONCILE. Cờ này **không thể tự đặt từ tên SocketTimeoutException**.

### 23.3. Provider floor được tôn trọng

Nếu full jitter chọn 3 giây nhưng provider yêu cầu tối thiểu 60 giây, nextAttemptAt cách hiện tại ít nhất 60 giây. Đây là độ trễ đã được classifier/integration kiểm tra, không lấy từ một SMTP header chuẩn không tồn tại.

### 23.4. Deadline được kiểm tra trước và sau tính delay

Một event sắp hết hạn sẽ STOP nếu thời điểm retry tiếp theo vượt deadline.

### 23.5. Mẫu code cố ý không bao gồm toàn bộ production rules

Chưa xử lý per-recipient partial outcomes, circuit breaker state, provider failover, database transaction, per-category attempt budgets, policy configuration, clock/overflow ở giá trị bất thường hoặc manual operator overrides. Những thứ đó thuộc orchestration/persistence layer.

## 24. Ví dụ test RetryPlanner bằng JUnit 5

Một ưu điểm của việc tách planner khỏi transport là kiểm thử deterministic, không cần SMTP server.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class MailRetryPlannerTest {

    private final Clock clock =
            Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );

    private final MailRetryPlanner planner =
            new MailRetryPlanner(
                    clock,
                    max -> max / 2,
                    5
            );

    @Test
    void invalidAuthStopsImmediately() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.AUTH_INVALID,
                true,
                Duration.ZERO
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.STOP,
                result.action()
        );

        assertNull(result.nextAttemptAt());
    }

    @Test
    void timeoutAfterDataRequiresReconciliation() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.AMBIGUOUS_AFTER_DATA,
                false,
                Duration.ZERO
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.RECONCILE,
                result.action()
        );
    }

    @Test
    void throttleRespectsProviderMinimumDelay() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.THROTTLED,
                true,
                Duration.ofSeconds(90)
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.RETRY_LATER,
                result.action()
        );

        assertEquals(
                clock.instant().plusSeconds(90),
                result.nextAttemptAt()
        );
    }

    @Test
    void deadlineStopsRetry() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.THROTTLED,
                true,
                Duration.ofMinutes(5)
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(30)
        );

        assertEquals(
                MailRetryPlanner.Action.STOP,
                result.action()
        );
    }
}
~~~

### 24.1. Không cần Thread.sleep

Clock.fixed và jitter function deterministic giúp test kết quả nextAttemptAt mà không chờ thời gian thực.

### 24.2. Test safety quan trọng hơn test phép toán delay

Phải chắc rằng invalid AUTH dừng, timeout sau DATA không auto-retry, provider minimum delay được giữ, và deadline không bị vượt.

### 24.3. Test chỉ kiểm tra planner

Nó chưa xác thực tầng phân loại exception, database claim hay SMTP transport. Cần test riêng cho những layer đó.

## 25. Phân loại từ MailException cần cẩn trọng

Một classifier có thể bắt đầu:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailException;

String classifyHighLevel(MailException ex) {
    if (ex instanceof MailAuthenticationException) {
        return "auth_or_account";
    }

    if (ex instanceof MailParseException) {
        return "parse";
    }

    if (ex instanceof MailPreparationException) {
        return "prepare";
    }

    return "needs_transport_inspection";
}
~~~

Code trên **cố ý chưa trả boolean retryable**. Lý do: cùng một class có thể che nhiều nguyên nhân và không cung cấp SMTP phase.

### 25.1. Inspect nested exceptions

Có thể dùng MailThrowableGraph.flatten(ex) để tìm AddressException, SendFailedException, IOException hoặc provider-specific SMTP exceptions. Nhưng vẫn phải biết kết quả server và phase.

### 25.2. Lỗi không phân loại được phải có fallback an toàn

Nếu không thể chứng minh retry safe, không tự dán nhãn transient. Có thể đưa vào investigation queue hoặc policy thận trọng.

### 25.3. Không phân loại bằng contains("timeout") duy nhất

Exception message có thể đổi ngôn ngữ, wording, provider hoặc chứa dữ liệu người dùng. Sử dụng cấu trúc và instrumentation có kiểm soát.

## 26. Transactional outbox thay vòng lặp sleep

Anti-pattern:

~~~java
@Transactional
public void sendNow() {
    mailSender.send(message);

    Thread.sleep(10_000);

    mailSender.send(message);
}
~~~

Đoạn code vừa có thể gửi trùng, vừa giữ transaction/thread lâu.

Một mô hình vững hơn:

~~~text
Business transaction
     |
     +-- update business record
     +-- insert mail_outbox event
     |
     v
COMMIT
     |
     v
Scheduled worker
     |
     v
Claim due event
     |
     v
Prepare + submit via JavaMailSender
     |
     v
Classify result
     |
     +-- SENT
     +-- RETRY_WAIT with nextAttemptAt
     +-- FAILED
     +-- UNKNOWN_OUTCOME
~~~

### 26.1. Outbox lưu ý định gửi bền vững

Khi ứng dụng restart, những events chưa terminal vẫn ở database, không phụ thuộc vào thread.sleep bị mất.

### 26.2. Không giữ DB transaction qua SMTP call

SMTP không tham gia cùng transaction database. Gửi trong transaction rồi rollback có thể khiến người nhận nhận email dù business data đã rollback.

### 26.3. Outbox không tạo exactly-once SMTP

Nếu relay accept message nhưng worker crash trước khi ghi SENT, một lần claim lại có thể gửi trùng. Cần recovery/unknown handling.

## 27. Database schema cho retry và audit

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    payload_reference TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts_completed INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at TIMESTAMPTZ,
    claim_owner VARCHAR(128),
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ,
    last_error_category VARCHAR(64),
    last_provider_alias VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(business_key, mail_kind)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);

CREATE TABLE mail_attempt (
    attempt_id UUID PRIMARY KEY,
    mail_event_id UUID NOT NULL
        REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    provider_alias VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(32) NOT NULL,
    error_category VARCHAR(64),
    smtp_reply_code VARCHAR(16),
    smtp_phase VARCHAR(32),
    duration_ms BIGINT,
    UNIQUE(mail_event_id, attempt_number)
);
~~~

### 27.1. nextAttemptAt chỉ dùng cho events được phép retry

Không cứ gặp exception là đặt next_attempt_at về now()+5s. STOP/UNKNOWN_OUTCOME cần state khác, tránh scheduler liên tục lấy lại.

### 27.2. Deadline và maxAttempts thuộc policy

Lưu deadline ở event; maxAttempts có thể lấy từ policy theo mailKind. Không để một worker dùng giá trị khác mà không có version/consistency.

### 27.3. Attempt history giúp đối soát

Ghi per-attempt provider, phase nếu biết, category và elapsed duration. Nếu process crash, STARTED attempt không có final result là tín hiệu cần điều tra.

### 27.4. Không lưu credential/raw MIME vào bảng telemetry

Payload có thể chứa thông tin nhạy cảm, nên lưu reference tới storage được bảo vệ và chính sách retention phù hợp.

## 28. Atomic claim để tránh hai worker cùng retry

Một scheduler có nhiều replicas không được làm:

~~~text
Worker A: SELECT retry due
Worker B: SELECT retry due
Both call JavaMailSender.send
~~~

Với PostgreSQL, một claim pattern:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= now()
      AND (
          deadline_at IS NULL
          OR deadline_at > now()
      )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'PROCESSING',
    claim_owner = :worker_id,
    claim_token = :new_token,
    claim_version = m.claim_version + 1,
    claim_until = now() + INTERVAL '90 seconds',
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING m.id, m.claim_version, m.claim_token;
~~~

### 28.1. Commit trước SMTP

Transaction chỉ claim rows rồi commit; JavaMailSender.send chạy sau. Giữ database transaction mở trong send không giải quyết atomicity với SMTP.

### 28.2. Update phải kiểm tra ownership

Khi chuyển RETRY_WAIT, SENT hoặc FAILED:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :next_attempt_at,
    last_error_category = :category,
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

Nếu affected rows = 0, owner có thể đã hết lease hoặc bị reclaim. Không tự ghi đè một cách vô điều kiện.

### 28.3. Lease expiry không chứng minh chưa gửi

Worker có thể đang ở sau DATA. Stale worker bị từ chối cập nhật database nhưng SMTP side effect có thể đã xảy ra.

## 29. Một orchestrator retry an toàn ở mức khái niệm

~~~java
public void processClaimed(ClaimedMail job) {
    try {
        MimeMessage mime = composer.compose(job);

        attemptStore.recordStarted(job);
        transport.send(mime, job.providerAlias());

        outbox.markSentIfOwned(job);
        attemptStore.recordReturnedOk(job);

    } catch (RuntimeException ex) {
        FailureFacts facts =
                classifier.classify(ex, job.transportContext());

        RetryDecision decision =
                retryPlanner.decide(
                        facts,
                        job.attemptsCompleted(),
                        job.deadline()
                );

        switch (decision.action()) {
            case RETRY_LATER ->
                    outbox.rescheduleIfOwned(
                            job,
                            decision.nextAttemptAt(),
                            facts.kind()
                    );

            case STOP ->
                    outbox.failIfOwned(job, facts.kind());

            case RECONCILE ->
                    outbox.markUnknownIfOwned(
                            job,
                            facts.kind()
                    );
        }
    }
}
~~~

**ClaimedMail, composer, transport, classifier, attemptStore, outbox và RetryDecision** ở đây là abstractions minh họa của ứng dụng. Không phải các lớp tự có từ Spring Framework Mail.

### 29.1. Production cần tinh chỉnh thứ tự ghi trạng thái

Trong ví dụ, nếu SMTP send thành công nhưng markSentIfOwned lỗi, khối catch có thể nhận một database exception. **Không được phân loại database failure là SMTP failure rồi retry message.** Một implementation production phải tách **send try/catch** và **state persistence try/catch**, ghi rõ outcome của transport trước khi xử lý lỗi ghi state.

### 29.2. Tách lỗi render khỏi lỗi SMTP

Nếu composer.compose ném exception, không tạo SMTP attempt. Policy phải phân loại là preparation failure, không tự tăng transport retry count.

### 29.3. Không coi example là code copy-paste hoàn chỉnh

Nó minh họa nhánh quyết định. Cần có durable transaction boundaries, metadata, callbacks và error handling phù hợp dự án.

## 30. Spring Retry: dùng khi nào?

**Spring Retry** giúp xây retry policies và backoff cho các operations đồng bộ. Nhưng dùng một annotation chung cho mọi exception vẫn là anti-pattern.

Một cấu hình đơn giản như:

~~~java
@Retryable(
    retryFor = Exception.class,
    maxAttempts = 5,
    backoff = @Backoff(delay = 5000)
)
public void send(MimeMessage message) {
    javaMailSender.send(message);
}
~~~

thể hiện rõ vấn đề: retry **mọi Exception**, cùng delay, không xét SMTP phase, không xét đã được relay accept chưa, không xét mail kind/deadline, và có thể ngủ trên request thread.

### 30.1. Annotation trên chỉ là ví dụ anti-pattern

Để dùng các annotations này phải có Spring Retry dependencies và cấu hình hỗ trợ phù hợp. Không nên sao chép nó vào production.

### 30.2. Có thể dùng retry policy theo exception category

Spring Retry có RetryTemplate, retry policies, backoff policies và hooks/listeners phù hợp nhiều bài toán. Nhưng **classifier phải đáng tin** và phải phân biệt retryable với ambiguous outcome.

### 30.3. Synchronous retry phù hợp tác vụ ngắn, được giới hạn

Ví dụ một lỗi connect chắc chắn xảy ra trước DATA với tối đa một lần retry và tổng deadline ngắn có thể được xử lý đồng bộ trong một worker. Các retries kéo dài nhiều phút nên dùng outbox nextAttemptAt.

### 30.4. @Retryable không tự giải quyết self-invocation

Trong cấu hình Spring AOP proxy thông thường, gọi method annotated từ method khác của cùng instance có thể không đi qua proxy. Đừng nghĩ annotation có hiệu lực chỉ vì nó xuất hiện trong source.

## 31. Phân biệt retry trong worker với retry trong provider

Một ứng dụng có thể có nhiều lớp retry:

~~~text
HTTP request / event listener
        |
        v
Outbox worker retry
        |
        v
Spring Retry around JavaMailSender
        |
        v
SMTP provider queue/retry to next MX
~~~

Nếu không kiểm soát, một event có thể được thử nhiều lần hơn dự kiến.

### 31.1. Retry amplification

Ví dụ worker maxAttempts=5, JavaMailSender wrapper retry 3 lần mỗi attempt. Tổng SMTP invocations có thể lên tới 15, dù dashboard outbox chỉ thấy 5 worker attempts nếu tracking ở sai tầng.

### 31.2. Một tầng sở hữu quyết định retry

Đối với gửi mail quan trọng, nên xác định một **retry orchestrator chính** nắm maxAttempts, deadline và nextAttemptAt. Các retries thấp hơn, nếu có, phải được đo rõ và không che khuất side effects.

### 31.3. Provider downstream retry độc lập

Sau khi SMTP relay nhận message, provider có thể tự retry delivery tới receiving MX. Ứng dụng không nên tự gửi thêm chỉ vì downstream chưa có delivered webhook ngay.

## 32. Multi-provider failover cần policy riêng

Một kiến trúc:

~~~text
Mail event
    |
    v
Routing policy
    |
    +-- provider A / account A
    |       |
    |       +-- attempt 1 -> connect failure
    |
    +-- provider B / account B
            |
            +-- attempt 2 -> success
~~~

### 32.1. Failover chỉ khi phù hợp

Provider B phải được ủy quyền dùng From domain, có SPF/DKIM/DMARC config đúng và đáp ứng quota/policy.

### 32.2. Không failover để né recipient/content policy

Nếu A từ chối vì invalid recipient, sender authorization hoặc policy hợp lệ, chuyển B để cố vượt qua từ chối có thể không hợp lệ và không tăng deliverability.

### 32.3. UNKNOWN_OUTCOME vẫn tồn tại qua failover

Nếu A có thể đã accept sau DATA, gửi lại qua B tạo duplicate risk như retry cùng A.

### 32.4. Attribution theo từng attempt

Ghi providerAlias và accountAlias **thực sự được dùng ở attempt đó**. Không quy thành công của B cho A chỉ vì A là provider mặc định của mail event.

## 33. SLA, deadline và phân biệt email transaction với marketing

Các loại email có tính thời gian khác nhau:

| Mail kind | Đặc điểm | Retry cần lưu ý |
| --- | --- | --- |
| **Password reset** | Token hết hạn | Dừng sau deadline, không gửi link vô dụng |
| **OTP/security alert** | Nhạy thời gian và có thể gây nhầm | Timeout unknown cần chống duplicate |
| **Order confirmation** | Cần đúng giao dịch | Outbox và idempotency theo business key |
| **Invoice** | Nội dung cố định/snapshot | Giữ bản đúng version; attachment access |
| **Marketing newsletter** | Tải lớn, chịu trì hoãn | Rate limiting và quota |
| **Daily digest** | Nội dung theo kỳ | Idempotency theo business date |

### 33.1. Đừng đổi nội dung ở mỗi retry một cách vô ý

Nếu render template từ dữ liệu live trong lần retry thứ ba, cùng mailEventId có thể chứa thông tin khác lần đầu. Cần snapshot/version policy.

### 33.2. Retry deadline và token TTL

Nếu token không còn hợp lệ tại thời điểm retry, STOP hoặc tạo một business intent mới theo chính sách thay vì gửi token đã hết hạn.

### 33.3. Quan sát business time-to-submit

Một mail event có thể chờ 10 phút trong RETRY_WAIT dù send call của lần cuối chỉ 500 ms. Theo dõi event-to-relay latency cùng SMTP attempt latency.

## 34. Metrics: không chỉ đếm retry count

Một bộ số liệu gợi ý:

| Metric | Tags thấp cardinality | Ý nghĩa |
| --- | --- | --- |
| **mail.smtp.submit.attempts** | provider, outcome | Actual SMTP invocations |
| **mail.smtp.submit.duration** | provider, outcome | Lời gọi send mất bao lâu |
| **mail.retry.decisions** | kind, action | Quyết định retry/stop/reconcile |
| **mail.retry.scheduled** | category, provider | Events chuyển RETRY_WAIT |
| **mail.retry.delay** | category | Delay đã được chọn |
| **mail.retry.exhausted** | kind, category | MaxAttempts/deadline |
| **mail.outbox.pending** | mailKind/priority | Backlog |
| **mail.outbox.retry_wait** | kind | Events đang đợi |
| **mail.outbox.oldest_pending_age** | priority | Starvation |
| **mail.smtp.unknown_outcomes** | provider | Kết quả mơ hồ |
| **mail.provider.throttled** | provider/accountTier | Throttle |
| **mail.circuit_breaker.state** | provider | Provider bị pause hay mở |
| **mail.event.terminal_failed** | kind, category | Business intents không gửi được |

### 34.1. Đếm retry decision riêng với SMTP attempt

Một event có thể được reschedule trong database nhưng chưa thực hiện send. Đừng lấy mail.retry.scheduled làm số attempts.

### 34.2. Không dùng recipient, mailEventId làm tag

Những giá trị này có cardinality cao và có thể là PII. Dùng trong structured logs có phân quyền khi cần tra chi tiết.

### 34.3. Quan sát success sau retry không xóa failure trước

Nếu attempt 1 lỗi và attempt 2 success, phải ghi một failure và một success. Business event có thể hoàn tất thành công nhưng health của provider vẫn có một lỗi thật.

## 35. Structured logging cho retry decisions

Ví dụ:

~~~json
{
  "event": "mail.retry.decision",
  "mailEventId": "event-42",
  "attemptId": "attempt-2",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp-provider-a",
  "errorCategory": "temporary_smtp",
  "smtpPhase": "rcpt_to",
  "smtpReplyCode": "450",
  "action": "RETRY_LATER",
  "reasonCode": "retryable_transient",
  "attemptsCompleted": 2,
  "nextAttemptAt": "2026-11-12T10:05:00Z"
}
~~~

Một event unknown:

~~~json
{
  "event": "mail.retry.decision",
  "mailEventId": "event-43",
  "attemptId": "attempt-1",
  "providerAlias": "smtp-provider-a",
  "smtpPhase": "after_data",
  "errorCategory": "timeout_unknown",
  "action": "RECONCILE",
  "reasonCode": "submission_not_confirmed"
}
~~~

### 35.1. Log reason code, không log body

Không cần email body, Subject, OTP, password hay full attachment để biết vì sao retry được lên lịch.

### 35.2. Audit manual override

Nếu operator ép retry một UNKNOWN_OUTCOME, nên ghi actor, approval, business justification và accepted duplicate risk trong audit system có quyền phù hợp.

### 35.3. Không dùng raw exception.getMessage làm metric tag

Reply text có thể chứa địa chỉ, host, nội dung tùy biến và nhiều giá trị khác nhau. Map thành taxonomy hữu hạn.

## 36. Tracing để biết thời gian đang nằm ở đâu

Một luồng:

~~~text
mail.worker.process
       |
       +-- mail.validate
       +-- mail.render
       +-- mail.mime.build
       +-- mail.route.select
       +-- mail.smtp.submit
       |       provider=A
       |       outcome=failure
       |
       +-- mail.retry.plan
       |       action=RETRY_LATER
       |
       +-- mail.outbox.reschedule
~~~

### 36.1. Retry sau nhiều phút là luồng async

Không cần giữ một trace/span mở suốt thời gian chờ. Có thể liên kết attempts bằng mailEventId và span links/correlation fields phù hợp.

### 36.2. Timeout và queue delay phải tách

Một lần SMTP send chậm 30 giây khác một event chờ backoff 30 phút. Đo cả attempt duration và event-to-submit latency.

### 36.3. Không đưa PII vào tracing attributes

Trace backend cũng lưu dữ liệu. Không tự đưa recipient, HTML content hoặc SMTP credentials vào spans.

## 37. Cảnh báo retry storm và lỗi không thể tự phục hồi

Một số alerts có hành động:

- AUTH invalid tăng ở cùng accountAlias → dừng retries, kiểm tra secret.
- TLS handshake/certificate failures tăng → điều tra config, không disable TLS.
- Retry attempts/second tăng mạnh → kiểm tra outage và backoff policy.
- Provider throttled liên tục → giảm concurrency, kiểm tra quota.
- Oldest RETRY_WAIT/pending vượt SLA → xem capacity/route.
- UNKNOWN_OUTCOME tăng → xem network sau DATA và duplicate risk.
- Terminal failures tăng → phân loại invalid address/content/config.
- Circuit breaker OPEN dài → xác định provider và runbook phục hồi.
- Retry budget exhausted tăng → xem deadline/maxAttempts.
- Mail events có nhiều attempts nhưng ít completion → kiểm tra retry amplification.

### 37.1. Alert cần lượng mẫu phù hợp

Tỷ lệ lỗi 50% trên 2 attempts khác 50% trên 10.000 attempts. Xem failure count, rate, sample window và mailKind/provider mix.

### 37.2. Không dùng rate limit cảnh báo để tăng tốc ngay

Một provider đang throttle thường cần giảm tải, không phải mở thêm workers.

## 38. Test fake sender: không được gửi quá số lần

Một test có thể dùng **Mockito JavaMailSender**, fake clock và durable repository test double:

~~~text
Given:
  One event E
  maxAttempts = 3
  Provider raises temporary failure before DATA
When:
  Worker processes attempts at eligible times
Then:
  E may be attempted at most 3 times
  nextAttemptAt always respects backoff
  No attempt is launched before nextAttemptAt
  After exhaustion E is terminal
~~~

### 38.1. Không cần SMTP production

Unit tests nên mock JavaMailSender. Integration tests dùng SMTP capture server trong môi trường được kiểm soát, tránh gửi nhầm tới người nhận thật.

### 38.2. Giả lập exception causes

Test cả MailAuthenticationException, MailSendException với nested causes, AddressException, SendFailedException và lỗi có/không có SMTP reply.

### 38.3. Test không có phase

Nếu classifier không biết timeout xảy ra trước hay sau DATA, planner không được tự khẳng định definitelyNotAccepted=true.

### 38.4. Test partial recipients

Nếu một batch có recipients đã được accept, retry không được gửi lại toàn bộ nhóm mù quáng.

## 39. Test ma trận theo lỗi và hành động

| Tình huống | Expected policy |
| --- | --- |
| Address syntax invalid | STOP |
| Mailbox unknown 5.1.1 có nguồn rõ | STOP/suppress |
| SMTP AUTH 535 invalid | STOP + alert |
| TLS hostname mismatch | STOP + alert |
| Template missing variable | STOP/fix input |
| Attachment missing | STOP/fix resource |
| Temporary SMTP 421 đã rõ chưa accept | RETRY_LATER |
| Throttling với minimum delay | RETRY sau floor phù hợp |
| Connection refused trước DATA | RETRY_LATER có budget |
| Timeout sau DATA | RECONCILE |
| Unknown exception/phase | RECONCILE hoặc policy thận trọng |
| Partial recipient acceptance | Retry nhóm chưa accept phù hợp |
| Deadline expired | STOP |
| MaxAttempts reached | STOP |
| Provider breaker OPEN | Reschedule/suspend according to policy |
| Worker crash after SMTP success | Không replay nếu thiếu đối soát |
| Retry planner return RETRY_LATER | nextAttemptAt lưu bền, không sleep |
| Two workers claim same event | Chỉ một owner hợp lệ |
| Fencing token stale | State update bị từ chối |

### 39.1. Test trên database đúng semantics

Nếu dùng PostgreSQL FOR UPDATE SKIP LOCKED, concurrency tests nên chạy với PostgreSQL thực/Testcontainers. Mock/H2 không mặc định mô phỏng row locking.

### 39.2. Test crash window không được khẳng định exactly-once

Có thể giả lập fake SMTP accept rồi worker crash trước DB update. Test sẽ cho thấy cần reconciliation và policy duplicate, không thể chứng minh SMTP provider sẽ tự deduplicate.

### 39.3. Test deadline và jitter deterministic

Dùng Clock.fixed, fake jitter và assertion trên nextAttemptAt thay vì Thread.sleep gây flaky.

## 40. So sánh ba cách triển khai retry

| Cách | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Catch + Thread.sleep** | Rất đơn giản | Giữ thread, không durable, thường không phân loại, dễ storm |
| **Spring Retry trong worker** | Có policies/backoff cho lời gọi đồng bộ | Cần classifier/safety, không tự bền qua crash |
| **Transactional outbox + nextAttemptAt** | Durable, reschedule dài hạn, quan sát nhiều attempts | Cần schema, workers, claim/lease/recovery |
| **Broker delayed retry/DLQ** | Có infrastructure hỗ trợ queueing | Vẫn cần idempotency và SMTP unknown handling |

### 40.1. Không dùng Spring Retry để bỏ qua đúng nghĩa SMTP

Dù thư viện retry mạnh, nó không thể chứng minh relay chưa accept sau DATA.

### 40.2. Outbox không tự dừng retry storm

Nếu policy phân loại sai hoặc không có rate limiting, outbox có thể tạo hàng triệu retry attempts. Durable storage và policy đúng phải đi cùng nhau.

### 40.3. Chọn một tầng điều phối chính

Nếu Spring Retry, worker retry và broker delivery redelivery đều bật, cần tính tổng số transport invocations và cơ chế thống kê chính xác.

## 41. Runbook khi email liên tục thất bại

Khi on-call thấy cùng mail event được retry nhiều lần:

1. Tìm mailEventId, attempt history, providerAlias và mailKind.
2. Xem lỗi là preparation, SMTP AUTH/TLS, recipient, throttle hay network.
3. Xác định SMTP phase và có bằng chứng **chưa được relay accept** hay không.
4. Nếu AUTH/config/TLS cố định, dừng retry và sửa cấu hình.
5. Nếu recipient lỗi, sửa dữ liệu/suppress theo policy.
6. Nếu rate limit, xem quota/circuit breaker/concurrency.
7. Nếu temporary SMTP rõ ràng, bảo đảm exponential backoff+jitter và nextAttemptAt.
8. Nếu unknown sau DATA, tránh retry mù; đối soát provider hoặc xử lý theo approved policy.
9. Kiểm tra maxAttempts, deadline/token TTL và priority.
10. Kiểm tra event có nhiều active owners hay worker retry amplification không.
11. Chỉ manual retry sau khi biết trạng thái thật và có quyền thao tác.
12. Sau khi sửa sự cố, đưa backlog vào xử lý **có điều tiết**, không xả tất cả cùng lúc.
13. Đối soát dashboard attempts, unique mail events và terminal states.
14. Ghi lại incident cause để cải thiện classifier và policy.

### 41.1. Không chỉnh database status SENT thành PENDING tùy tiện

Một event đã được relay accept có thể gửi trùng nếu đổi lại PENDING. Resend phải là workflow nghiệp vụ có audit riêng.

### 41.2. Không tắt TLS để “giải quyết nhanh”

Nếu lỗi certificate, sửa trust/endpoint và deploy cấu hình đúng; bỏ xác thực TLS làm giảm bảo mật.

## 42. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Thay bằng |
| --- | --- | --- |
| catch(Exception) rồi retry | Retry lỗi không phục hồi | Failure classification |
| Một fixed delay cho mọi lỗi | Storm, sai retry schedule | Category-aware backoff |
| Retry invalid address | Tốn tài nguyên | STOP/fix data |
| Retry AUTH 535 liên tục | Lockout/account abuse | STOP/fix credentials |
| Bỏ qua TLS validation | Kết nối không an toàn | Fix TLS |
| Coi mọi 4xx giống nhau | Throttle không được điều tiết | SMTP/enhanced code context |
| Coi mọi 5xx là provider outage | Failover sai | Error taxonomy |
| Timeout nghĩa là chưa gửi | Duplicate sau DATA | UNKNOWN_OUTCOME |
| Retry toàn batch | Duplicate partial recipients | Per-message/recipient status |
| Không có maxAttempts | Retry vô hạn | Budget/deadline |
| Chỉ có maxDelay | Sự kiện retry nhiều ngày | Deadline + attempt cap |
| Không jitter | Herd effect | Full/decorrelated jitter |
| Dùng Thread.sleep trong transaction | Giữ DB locks/connections | Durable nextAttemptAt |
| Nhiều retry layers không kiểm soát | Retry amplification | One owner orchestrator |
| Outbox không có atomic claim | Hai workers gửi một event | Lease/claim/fencing |
| Không track SMTP phase | Không biết safe-to-retry | Transport instrumentation |
| Coi send success là inbox delivered | Dashboard/SLA sai | Separate downstream signals |
| Log raw provider replies/credentials | Rò rỉ dữ liệu | Structured safe logs |
| recipient/eventId làm metric label | High cardinality/PII | Allowlist tags |
| Rerender template tùy ý khi retry | Nội dung khác trong cùng intent | Snapshot/version |
| Đổi provider để né content policy | Sai compliance | Authorized routing |
| Retry khi token hết hạn | Mail vô dụng/nguy hiểm | Deadline check |
| Xả backlog đồng loạt sau outage | Provider lại throttle | Gradual ramp-up |

## 43. Câu hỏi thường gặp

**1. Vì sao không retry mọi MailException?**

Vì MailException bao phủ lỗi có nguyên nhân và khả năng phục hồi rất khác nhau. AUTH invalid, input sai, TLS config, temporary SMTP và timeout sau DATA không thể dùng cùng một quyết định.

**2. Spring Retry có tự hiểu SMTP 421 và 550 không?**

Không nên giả định. Cần classifier từ exception/reply/phase và policy của ứng dụng. Một annotation chung không đủ để biết email có được relay accept hay chưa.

**3. SMTP 4xx có luôn retry được không?**

Thường biểu thị transient negative reply, nhưng cần biết cụ thể reply ở phase nào, provider semantics, budget và liệu result có chắc chắn chưa accepted không.

**4. SMTP 5xx có luôn là lỗi vĩnh viễn của recipient không?**

Không. Có thể là sender policy, content hoặc size. Cần xem enhanced status, phase và provider documentation.

**5. 535 AUTH nên xử lý gì?**

Dừng retry dồn dập và kiểm tra credential/account/policy. Một temporary AUTH infrastructure error có thể cần policy khác invalid password.

**6. Timeout trước connect và sau DATA khác nhau thế nào?**

Trước connect, nếu chắc chắn không có SMTP submission, retry có thể an toàn. Sau DATA, relay có thể đã chấp nhận; cần UNKNOWN_OUTCOME/reconciliation.

**7. Jitter có bắt buộc không?**

Không phải luôn bắt buộc, nhưng rất hữu ích để tránh hàng nghìn events retry đồng loạt sau outage. Vẫn cần rate limiting và provider-specific minimum delay.

**8. Exponential backoff có tốt hơn fixed delay mọi trường hợp không?**

Không tự động. Nó phù hợp nhiều lỗi tạm thời, nhưng không giải quyết lỗi input/config hay kết quả ambiguous. Phân loại và safety quan trọng hơn công thức delay.

**9. maxDelay có thay maxAttempts được không?**

Không. Max delay chỉ giới hạn thời gian giữa hai attempts; maxAttempts/deadline mới ngăn retry vô hạn.

**10. Vì sao không Thread.sleep trong worker?**

Nó giữ thread/connection, khó khôi phục sau crash và không phù hợp các delay dài. Lưu nextAttemptAt trong outbox thường dễ vận hành hơn.

**11. SMTP có Retry-After như HTTP 429 không?**

Không có một Retry-After header chuẩn dùng thống nhất cho mọi SMTP reply. Hướng dẫn chờ từ provider là provider-specific; cần xác minh trước khi áp dụng.

**12. Thay provider có tránh được duplicate sau timeout không?**

Không. Provider A có thể đã accept trước khi response bị mất. Gửi qua B là thêm một submission có nguy cơ trùng.

**13. Message-ID có chống gửi trùng không?**

Không có bảo đảm SMTP relay sẽ bỏ message trùng Message-ID. Nó hữu ích cho correlation/threading nhưng không thay thế idempotency policy.

**14. Nếu một message có 10 recipients và 2 lỗi, retry cả 10 được không?**

Không nên retry mù nếu 8 người đã được accept. Cần per-recipient/partial outcome handling hoặc thiết kế một event mỗi recipient.

**15. MailSendException.getMessageExceptions có đủ quyết định retry không?**

Không. Nó giúp xem những exception cụ thể, nhưng vẫn cần phase, reply context, outcome safety và per-message status.

**16. Có thể retry nội bộ Spring Retry và outbox cùng lúc không?**

Có thể về kỹ thuật, nhưng phải tính tổng actual SMTP attempts, tránh retry amplification và có một tầng sở hữu budget/deadline.

**17. Lỗi attachment có phải SMTP provider lỗi không?**

Không nhất thiết. Resource có thể được đọc muộn lúc MIME serialize trong send, nên một IOException trong send có thể bắt nguồn từ file/storage.

**18. Có nên lưu full exception stack trace trong log không?**

Chỉ khi cần và có quyền thích hợp; diagnostic text có thể chứa recipient và metadata. Với metrics, dùng category/code hữu hạn.

**19. Có thể test retry mà không gửi email thật không?**

Có. Test planner với Clock.fixed/fake jitter; mock JavaMailSender; dùng SMTP capture server để test integration. Đừng gửi email production từ CI.

**20. Outbox có bảo đảm email exactly once không?**

Không. Nó giúp durable intent/claim/retry nhưng SMTP và database không commit nguyên tử. Crash sau SMTP accept trước SENT vẫn có duplicate window.

**21. Khi nào nên RECONCILE?**

Khi kết quả relay acceptance không đủ chắc chắn, như timeout sau DATA hoặc worker crash trong giai đoạn không rõ.

**22. Lỗi 4.7.0 có thể là rate limit không?**

Có thể liên quan policy/throttle tùy provider, nhưng không được suy một cách cứng nhắc khi thiếu context. Dùng provider-specific mapping và reply semantics.

**23. Provider đang outage mà nhiều email pending thì sao?**

Giữ outbox durable, mở circuit breaker/backoff, theo dõi quota và tăng lại tốc độ có kiểm soát khi phục hồi.

**24. Tại sao email OTP có thể dừng retry sớm hơn invoice?**

OTP/token có deadline ngắn, gửi sau khi hết hạn có thể vô ích hoặc gây nhầm. Invoice có thể chịu trì hoãn dài hơn nhưng vẫn cần snapshot và chính sách nghiệp vụ.

**25. Có nên tự retry mọi IOException?**

Không. IOException có thể đến từ socket, attachment stream hoặc storage, và không nói rõ phase/acceptance.

## 44. Ghi nhớ về thử lại mọi exception với cùng một backoff

**“Bắt mọi exception, chờ cùng một khoảng thời gian rồi gửi lại” là anti-pattern trong Spring Framework Mail.** Nó trộn lỗi không phục hồi (recipient sai, AUTH invalid, TLS config, template/resource lỗi), lỗi tạm thời (SMTP 4xx, provider throttling, kết nối thất bại trước submission) và **kết quả chưa xác định** (mất reply sau DATA). Ba nhóm này cần hành động khác nhau: **STOP**, **RETRY_LATER** hoặc **RECONCILE**.

Hãy phân loại dựa trên Spring Mail/Jakarta Mail exception chain, SMTP reply/enhanced code, transport phase, per-recipient outcome và mức chắc chắn rằng relay chưa accept message. **Backoff chỉ được tính sau khi đã quyết định retry thực sự phù hợp và đủ an toàn.** Với lỗi tạm thời, dùng exponential/capped backoff, jitter, provider minimum delay, maxAttempts, deadline và rate limiting/circuit breaker phù hợp.

Đối với các retries kéo dài, dùng **transactional outbox** với nextAttemptAt, atomic worker claim, durable attempt history và trạng thái RETRY_WAIT/FAILED/UNKNOWN_OUTCOME thay vì giữ thread ngủ. Không giữ database transaction qua SMTP send, không replay toàn batch, không tự gửi lại khi outcome mơ hồ và không coi JavaMailSender.send thành công là inbox delivery.

Theo dõi **attempts, error categories, backoff decisions, retry backlog, oldest pending age, provider throttling và unknown outcomes** bằng Micrometer, logs và tracing; kiểm thử policy với fake Clock/jitter, Mockito và database concurrency tests. Khi retry được thiết kế theo **nguyên nhân, an toàn và giá trị nghiệp vụ**, hệ thống vừa phục hồi tốt hơn sau lỗi tạm thời vừa tránh biến lỗi cấu hình hoặc sự cố mạng thành retry storm và email trùng.
