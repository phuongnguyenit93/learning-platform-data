# Dùng mock JavaMailSender rồi kết luận deliverability: lỗi thường gặp trong Spring Framework Mail

Khi kiểm thử tính năng gửi email bằng **Spring Framework Mail**, một bài unit test có thể chạy rất nhanh:

~~~java
verify(javaMailSender).send(any(SimpleMailMessage.class));
~~~

Kết quả xanh cho biết ứng dụng đã **gọi phương thức `send(...)` trên đối tượng mock theo kỳ vọng**. Nhưng nó **không chứng minh** có kết nối tới máy chủ SMTP, thư được relay chấp nhận, địa chỉ nhận tồn tại, email được giao đến mailbox, vượt qua bộ lọc spam hay xuất hiện trong **Inbox** của người nhận.

Đây là lỗi suy luận thường gặp: **lấy bằng chứng ở một tầng của hệ thống rồi kết luận kết quả ở những tầng mà bài test chưa từng quan sát**.

Bài học này phân biệt chính xác unit test với mock, integration test SMTP, kiểm thử nhà cung cấp thực, delivery và inbox placement; trình bày ví dụ JUnit/Mockito, MIME và SMTP, cách thiết kế trạng thái ứng dụng, đo deliverability bằng dữ liệu đủ tin cậy, các tình huống giả thành công và bộ kiểm thử cho production.

> **Quy tắc trọng tâm:** `verify(sender).send(...)` chứng minh tương tác với mock. SMTP reply cuối `250` chứng minh relay ở điểm quan sát đã chấp nhận submission. Provider `delivered` thường phản ánh một mốc giao thư theo định nghĩa của provider. Không điều nào trong ba bằng chứng đó, tự nó, chứng minh thư đã ở **Inbox** hoặc đã được người nhận đọc.

## 1. Bắt đầu từ định nghĩa: “gửi thành công” là thành công ở đâu?

Trong ngôn ngữ nghiệp vụ, các câu sau thường bị dùng lẫn:

- “Hàm gửi mail chạy không lỗi.”
- “Mail đã được gửi.”
- “Nhà cung cấp đã chấp nhận email.”
- “Mail đã tới mailbox người nhận.”
- “Mail đã vào Inbox.”
- “Người nhận đã đọc email.”

Chúng là **những mốc khác nhau**. Một sơ đồ đơn giản:

~~~mermaid
flowchart LR
    A["Business service"] --> B["JavaMailSender"]
    B --> C["SMTP relay / provider"]
    C --> D["Recipient mail server"]
    D --> E["Mailbox or spam filtering"]
    E --> F["Inbox / other folder"]
    F --> G["Human recipient"]
~~~

Mock `JavaMailSender` thường chỉ quan sát **mũi tên từ business service tới sender abstraction**. Nó không chạy các bước phía sau.

### Những mốc cần đặt tên rõ

| Mốc | Bằng chứng có thể quan sát | Điều **chưa** được chứng minh |
| --- | --- | --- |
| **Intent recorded** | Outbox record đã commit | SMTP đã được gọi |
| **Sender invoked** | Mock `verify(send)`, spy hoặc application instrumentation | Có kết nối SMTP thật |
| **Transport attempted** | Client mở socket/gửi SMTP commands tới server | Relay đã chấp nhận thư |
| **Submission accepted** | Relay trả final success response sau DATA hoặc API provider trả acceptance theo hợp đồng | Remote mail server đã giao thư |
| **Recipient server accepted** | Thông tin DSN/provider event đáng tin về next-hop acceptance | Thư được phân loại vào Inbox |
| **Provider delivered** | Event `delivered` theo định nghĩa provider | Người nhận nhìn thấy ở Inbox hoặc đã đọc |
| **Inbox placement** | Kiểm tra mailbox/seed account cụ thể thấy thư ở Inbox | Mọi người nhận khác đều có cùng kết quả |
| **Human engagement** | Hành động có ý nghĩa của người nhận | Không thể suy ra chắc chắn chỉ từ open pixel |

Không phải mọi SMTP provider đều cho bạn biết rõ từng mốc. Nếu nguồn dữ liệu chỉ hỗ trợ `accepted` và `bounced`, API và dashboard cần phản ánh chính mức bằng chứng đó.

## 2. Mock JavaMailSender thực sự làm gì?

Với Mockito:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
~~~

Mockito tạo một đối tượng thay thế implementing interface. Theo mặc định, các lời gọi void như `send(SimpleMailMessage)` **không thực hiện việc gửi thư thật**; test có thể cấu hình exception, answer hoặc ghi nhận invocation.

Một lời gọi:

~~~java
sender.send(message);
~~~

trên mock bình thường không mở socket SMTP, không thực hiện EHLO/STARTTLS/AUTH, không gửi MAIL FROM/RCPT TO/DATA và không nhận mã phản hồi thực từ relay.

### Test xanh chứng minh điều gì?

~~~java
verify(sender, times(1))
        .send(any(SimpleMailMessage.class));
~~~

Nó chứng minh, trong quá trình test được quan sát, lời gọi tới phương thức/overload phù hợp đã xảy ra **đúng một lần** trên mock. Nếu có argument captor, test còn có thể chứng minh đối tượng truyền vào chứa các trường đã kiểm tra.

### Test xanh **không** chứng minh điều gì?

Nó không xác minh:

- SMTP host, port và DNS đúng.
- TLS, STARTTLS, hostname verification hoặc chứng chỉ hợp lệ.
- Username/password/OAuth token hợp lệ.
- `MAIL FROM` và `RCPT TO` được relay chấp nhận.
- MIME thực được serialization đúng trên wire.
- Provider quota, rate limiting hoặc chính sách gửi đang cho phép.
- Domain gửi có SPF/DKIM/DMARC alignment phù hợp.
- Recipient mailbox có thật và không bounce.
- Email có vào spam/quarantine không.
- Inbox placement hoặc người nhận đã đọc.

**Không có lỗi trong mock** chỉ là không có lỗi đã được mô phỏng ở tầng mock.

## 3. Một ví dụ dễ tạo cảm giác an toàn giả

Giả sử ứng dụng có service gửi biên nhận:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public final class ReceiptMailService {

    private final JavaMailSender sender;

    public ReceiptMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendReceipt(String destination, String orderId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("billing@example.test");
        message.setTo(destination);
        message.setSubject("Receipt for order " + orderId);
        message.setText("Your order has been recorded.");

        sender.send(message);
    }
}
~~~

`example.test` là domain dùng trong ví dụ, **không phải địa chỉ sender được xác minh để gửi email ra Internet**. Service vẫn hoàn toàn có thể vượt qua unit test với mock vì test không chạm tới hạ tầng.

### Test Mockito

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.any;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailServiceTest {

    @Mock
    JavaMailSender sender;

    @InjectMocks
    ReceiptMailService service;

    @Captor
    ArgumentCaptor<SimpleMailMessage> messageCaptor;

    @Test
    void createsAndSubmitsReceiptToMailSender() {
        service.sendReceipt("buyer@example.test", "order-184");

        verify(sender).send(messageCaptor.capture());
        verifyNoMoreInteractions(sender);

        SimpleMailMessage actual = messageCaptor.getValue();
        assertEquals("billing@example.test", actual.getFrom());
        assertEquals("buyer@example.test", actual.getTo()[0]);
        assertEquals("Receipt for order order-184",
                actual.getSubject());
        assertEquals("Your order has been recorded.",
                actual.getText());
    }
}
~~~

Test hữu ích: nó xác minh ứng dụng đi đúng nhánh tạo receipt, đặt địa chỉ, subject và nội dung. Nhưng **tên test chính xác** là `createsAndSubmitsReceiptToMailSender`, không nên là `emailWasDeliveredSuccessfully`.

Nếu code production cấu hình SMTP sai, test này vẫn xanh. Nếu mailbox người nhận không tồn tại, test vẫn xanh. Nếu thư bị chuyển vào Spam, test cũng không có cách quan sát.

### Một kết luận sai

~~~text
Given: JavaMailSender is mocked
When:  receipt service calls send()
Then:  Mockito verifies the invocation

Wrong conclusion:
  "Deliverability = 100%, email reaches user"

Correct conclusion:
  "Service attempts to send via JavaMailSender
   with the asserted message fields"
~~~

## 4. Mock lại có ích rất lớn nếu đặt đúng mục tiêu

Vấn đề không nằm ở Mockito mà ở **điều chúng ta tuyên bố dựa trên kết quả kiểm thử**. Unit tests là nơi tốt để xác minh:

- Business event nào tạo yêu cầu gửi.
- Người nhận, sender, subject và template key có đúng không.
- Có bỏ qua email bị suppression/opt-out không.
- Có dùng plain text hay HTML theo yêu cầu không.
- Có gửi tối đa một lần ở cấp service method không.
- Có bắt/ném/chuyển đổi `MailException` theo policy không.
- Có ghi outbox thay vì gọi SMTP trong database transaction không.
- Có tôn trọng expiry, retry budget, category và permissions không.
- Có không gọi sender nếu validation thất bại không.

Điều quan trọng: với một ứng dụng dùng outbox, **unit test của business service có thể phải verify repository/event publisher**, không phải verify `JavaMailSender` ngay trong HTTP request. `JavaMailSender` chỉ được gọi bởi worker sau khi outbox đã commit.

### Ví dụ assertion tên và ý nghĩa tốt

| Tên test | Ý nghĩa |
| --- | --- |
| `sendsReceiptUsingExpectedRecipient` | Xác minh recipient truyền tới mock |
| `doesNotInvokeSenderWhenRecipientSuppressed` | Xác minh business guard |
| `propagatesMailSendException` | Xác minh error handling |
| `persistsNotificationAfterPaymentCommit` | Xác minh outbox boundary |
| `formatsMimeMessageWithPlainTextAndHtml` | Xác minh MIME composition |
| `smtpRelayAcceptsMessage` | Cần SMTP integration, không phải chỉ mock |
| `providerReportsRecipientDelivery` | Cần provider event/result |
| `mailAppearsInSeedInbox` | Cần kiểm tra mailbox thật phù hợp |

Viết tên test phản ánh đúng **mức quan sát** giúp reviewer không hiểu nhầm phạm vi bảo đảm.

## 5. Vì sao `send()` không đồng nghĩa `deliver()`?

Trong một kết nối SMTP thông thường:

~~~text
Application                    SMTP relay
    |                               |
    |---- TCP + optional TLS ------>|
    |---- EHLO -------------------->|
    |<--- 250 capabilities ---------|
    |---- AUTH (if required) ------>|
    |<--- authentication outcome ---|
    |---- MAIL FROM:<...> --------->|
    |<--- 250 ----------------------|
    |---- RCPT TO:<...> ----------->|
    |<--- 250 ----------------------|
    |---- DATA -------------------->|
    |<--- 354 ----------------------|
    |---- headers + body + "." ---->|
    |<--- 250 queued/accepted ------|
    |                               |
    v                               v
Application submission ends     Relay may deliver later
~~~

Đây là một ví dụ trình tự đơn giản: TLS có thể là implicit TLS, STARTTLS hoặc cơ chế khác theo provider; nhiều recipient có thể có nhiều `RCPT TO`. Server có thể từ chối ở các phase khác nhau.

### Ý nghĩa của final SMTP 250

Phản hồi success sau DATA nói rằng **relay tại điểm quan sát đã chấp nhận trách nhiệm xử lý thông điệp** theo SMTP. Sau đó relay có thể:

- Xếp hàng chờ gửi tới MX của recipient.
- Retry khi remote MX trả 4xx.
- Bị từ chối 5xx từ máy chủ đích.
- Sinh DSN/bounce.
- Gặp chính sách quota/reputation ở downstream.
- Chuyển giao nhưng thư được lọc vào Spam, Promotions, Quarantine hoặc không hiển thị ở Inbox.

Vì vậy, không thể từ final 250 của SMTP relay suy ra **Inbox placement**.

### Không thấy exception cũng không đủ

`JavaMailSender.send()` có thể trả về bình thường khi transport submission thành công. Nhưng trạng thái của thư sau relay vẫn là kết quả bất đồng bộ. Một phần mềm chỉ dùng `try { send(); } catch (...) { ... }` thường **chưa có nguồn dữ liệu về delivered/bounced hoặc placement**.

## 6. Phân biệt submission, delivery, deliverability và inbox placement

Các thuật ngữ thường dùng:

**Submission:** ứng dụng gửi email tới relay/provider và được chấp nhận xử lý.

**Delivery:** email được chuyển giao tới đích theo định nghĩa của nguồn đo (ví dụ provider báo remote server accepted); không nhất thiết là Inbox.

**Deliverability:** khả năng thư hợp lệ vượt qua các rào cản gửi và được tiếp nhận trong môi trường thực. Trong báo cáo marketing, thuật ngữ đôi khi được dùng rộng để gồm khả năng vào Inbox; do đó **phải định nghĩa metric cụ thể** thay vì dùng từ chung không có mẫu số.

**Inbox placement:** thư được phân loại và xuất hiện trong Inbox của mailbox nhận, thay vì Spam/Other/Quarantine. Muốn đo cần quan sát mailbox/seed testing hoặc nguồn đáng tin có định nghĩa tương ứng.

**Engagement:** tương tác của recipient như click hoặc hành động trong ứng dụng. Open tracking pixel không bảo đảm người thật đã mở thư vì có proxy tải ảnh, image prefetch, privacy settings và blocking.

### Không gộp mọi tầng thành boolean `sent=true`

Một model rõ hơn:

~~~text
requestStatus:  PENDING / PROCESSING / TERMINAL
submitStatus:   NOT_ATTEMPTED / ACCEPTED / REJECTED / UNKNOWN
deliveryStatus: NOT_KNOWN / DEFERRED / DELIVERED / BOUNCED
placement:      NOT_OBSERVED / INBOX / SPAM / OTHER / UNKNOWN
engagement:     optional, independent and privacy-scoped
~~~

Đây là **enum ứng dụng**, không phải kiểu được Spring Mail cung cấp sẵn. Không bắt buộc mọi sản phẩm phải triển khai đủ từng trạng thái; điều tối thiểu là không đặt tên `DELIVERED` cho một kết quả mock hoặc SMTP submission.

## 7. Một bảng bằng chứng đúng và sai

| Bằng chứng hiện có | Kết luận được phép | Kết luận không được phép |
| --- | --- | --- |
| Mockito verify sender.send | Service gọi đúng method/argument | SMTP kết nối thành công |
| `SimpleMailMessage` fields đúng | Dữ liệu ứng dụng đã xây đúng | Remote relay chấp nhận |
| MimeMessage parse hợp lệ | MIME nội bộ phù hợp test | Provider/domain authentication pass |
| Fake SMTP nhận DATA | Local transport tạo được submission vào fake server | Internet delivery thành công |
| Provider API trả “accepted” | Provider nhận yêu cầu theo hợp đồng | Người nhận đã nhận thư |
| Provider delivered webhook | Provider báo delivered theo định nghĩa | Inbox, đọc hay tương tác thật |
| Remote MX trả 250, nếu đo được | Hệ thống đích chấp nhận transfer | Message nằm Inbox |
| Seed account thấy Inbox | Inbox placement ở seed đó tại thời điểm đo | Mọi mailbox ngoài đời tương tự |
| Không có bounce sau 5 phút | Chưa ghi nhận bounce trong window | Không bao giờ bounce |
| Tracking pixel được tải | Hình ảnh trong mail được tải ở môi trường nào đó | Người dùng chắc chắn mở/đọc |

Mỗi claim phải gắn với **nguồn bằng chứng, thời điểm và phạm vi đo**. Nếu thiếu dữ liệu, ghi `UNKNOWN` thay vì tự điền `DELIVERED`.

## 8. Các kiểu lỗi mà Mockito mock thường bỏ qua

Mock sender mặc định không kiểm tra:

| Nhóm lỗi | Ví dụ | Nơi cần kiểm thử |
| --- | --- | --- |
| DNS/egress | Không phân giải hostname hoặc bị firewall chặn | SMTP integration/environment |
| TCP/TLS | Sai port, certificate, STARTTLS bị từ chối | SMTP integration/staging |
| Authentication | Password/token sai, account bị vô hiệu | Staging/provider smoke test |
| Sender policy | `MAIL FROM` hoặc `From:` không được phép | Provider integration |
| Recipient rejection | SMTP `550 5.1.1` ở RCPT TO | Scripted SMTP + real provider evidence |
| Temporary refusal | `421`/`451`/throttling | Scripted SMTP + retry integration |
| MIME encoding | HTML/attachment lỗi, charset sai | MIME parse + local SMTP capture |
| Size limits | Message lớn hơn provider cho phép | Provider-specific integration |
| Authentication DNS | SPF/DKIM/DMARC không aligned | DNS inspection và authentication results thực |
| Sender reputation | Domain/IP bị hạn chế hoặc tín hiệu xấu | Production analytics/provider reports |
| Recipient filtering | Spam/Promotions/Quarantine | Seed mailbox và operational evidence |
| Compliance/consent | Người nhận unsubscribe hoặc complaint | Business policy + suppression integration |
| Delayed bounce | Relay accepted, MX từ chối sau đó | Provider event/DSN processing |

Đừng “sửa” giới hạn này bằng cách viết Mockito stub trả `true` hoặc `Optional<Delivered>`: đó vẫn là dữ liệu giả lập, không biến unit test thành phép đo deliverability.

## 9. Chọn chiến lược nhiều tầng thay vì bỏ mock hoàn toàn

Một chiến lược cân bằng:

~~~mermaid
flowchart TD
    A["Unit tests with Mockito"] --> B["MIME composition tests"]
    B --> C["Local SMTP integration tests"]
    C --> D["Provider staging / sandbox validation"]
    D --> E["Controlled real-mailbox observations"]
    E --> F["Production event + reputation monitoring"]
~~~

**Không phải tầng sau thay thế tầng trước.** Mock tests nhanh, rẻ và giúp chỉ ra lỗi business. Local SMTP kiểm tra protocol/MIME. Provider test kiểm tra account/config. Kiểm tra seed mailbox quan sát một số trường hợp placement thực. Production monitoring theo dõi thay đổi theo domain, loại mail, chất lượng danh sách và reputation.

### Phạm vi mỗi tầng

| Tầng | Cái gì được đo? | Có cần mạng ra Internet? |
| --- | --- | --- |
| Unit mock | Calls, arguments, guards, error decisions | Không |
| MIME unit/contract | Serialized structure, encoding, multipart | Không |
| Local SMTP | Connect/auth simulation, SMTP conversation, received message | Không, nếu server chạy local |
| Provider sandbox | Provider API/schema/config như môi trường được cấp | Tùy môi trường |
| Controlled real provider | Real account auth/acceptance/events | Có |
| Seed inbox | Placement trên mailbox mẫu cụ thể | Có |
| Production monitoring | Kết quả trong lưu lượng thật, theo nguồn đo | Có |

Provider “sandbox” có thể cố ý **không giao thư thật**; nó hữu ích để kiểm tra API contract, không tự chứng minh external delivery.

## 10. Khi nào nên mock, khi nào không?

**Nên mock** khi câu hỏi cần trả lời là:

- Application có quyết định gửi thư đúng không?
- Message builder đã đặt đúng thuộc tính chưa?
- Retry policy gọi sender bao nhiêu lần?
- Suppression có chặn lời gọi không?
- Service có lưu/đẩy thông báo vào outbox đúng ranh giới giao dịch không?

**Không chỉ mock** khi câu hỏi là:

- Cấu hình `spring.mail.host`, `port`, STARTTLS có hoạt động không?
- `JavaMailSenderImpl` có thực sự gửi được MIME qua giao thức SMTP không?
- Attachment/inline resource có được serialize đúng không?
- Provider có chấp nhận credentials, sender domain, quota và content không?
- Remote mailboxes có thấy mail ở Inbox, Spam hay không?

Làm rõ **câu hỏi kiểm thử** trước khi chọn công cụ giúp không phải thay toàn bộ suite Mockito bằng những bài test Internet chậm, dễ không ổn định và khó kiểm soát.

## 11. Kiểm thử lỗi `MailException` bằng mock: đúng phạm vi

Một lợi ích của mock là mô phỏng lỗi **không phụ thuộc SMTP đang khỏe hay không**. Ví dụ buộc sender ném `MailSendException`:

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailFailureTest {

    @Test
    void propagatesSimulatedSenderFailure() {
        JavaMailSender sender = mock(JavaMailSender.class);
        ReceiptMailService service = new ReceiptMailService(sender);

        doThrow(new MailSendException("Simulated transport failure"))
                .when(sender).send(any(SimpleMailMessage.class));

        assertThrows(MailSendException.class,
                () -> service.sendReceipt(
                        "buyer@example.test", "order-184"));

        verify(sender, times(1))
                .send(any(SimpleMailMessage.class));
    }
}
~~~

Test xác minh service **xử lý một exception được dựng sẵn** theo kỳ vọng. Nó không kiểm tra SMTP server thật sẽ tạo exception class nào trong từng phase hoặc cách Jakarta Mail bọc nested exception.

### Có thể mô phỏng lỗi nhưng không mô phỏng nguyên nhân thật

Ví dụ:

~~~java
doThrow(new MailSendException("550 Invalid recipient"))
        .when(sender).send(any(SimpleMailMessage.class));
~~~

Đây chỉ là một chuỗi lỗi do test tạo ra. Nó **không chứng minh** ứng dụng đã đọc mã SMTP 550 thật, biết lỗi xuất hiện ở `RCPT TO` hay phân biệt hard bounce với một lỗi tài khoản. Muốn xác minh classifier dựa trên SMTP reply/phase, cần test với adapter có error metadata hoặc server SMTP lập trình được phản hồi.

### Phân tách trách nhiệm

Một suite nên có:

1. **Policy unit test:** input `INVALID_RECIPIENT` → dừng, input `PROVIDER_TEMPORARY` → retry nếu còn hạn.
2. **Adapter integration test:** SMTP reply/exception thực → `NormalizedMailFailure` tương ứng.
3. **End-to-end workflow test:** trạng thái outbox, retry budget và số physical attempts được cập nhật đúng.

Nếu chỉ có bước 1 với dữ liệu mock, hệ thống vẫn có thể sai khi chuyển exception thật thành category.

## 12. Verify không gửi cũng là một unit test có giá trị

Đối với ứng dụng gửi transactional/marketing mail, điều kiện **không được gửi** đôi khi quan trọng hơn kiểm tra đã gọi sender:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class MarketingMailService {

    private final JavaMailSender sender;
    private final RecipientPreference preference;

    public MarketingMailService(
            JavaMailSender sender,
            RecipientPreference preference) {
        this.sender = sender;
        this.preference = preference;
    }

    public void sendOffer(String recipient) {
        if (!preference.mayReceiveMarketing(recipient)) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(recipient);
        message.setSubject("Product update");
        message.setText("News from our service.");
        sender.send(message);
    }
}

interface RecipientPreference {
    boolean mayReceiveMarketing(String recipient);
}
~~~

Kiểm thử:

~~~java
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.any;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class MarketingMailServiceTest {

    @Test
    void suppressedRecipientNeverCallsSender() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPreference preference =
                mock(RecipientPreference.class);
        when(preference.mayReceiveMarketing(
                "blocked@example.test")).thenReturn(false);

        MarketingMailService service =
                new MarketingMailService(sender, preference);

        service.sendOffer("blocked@example.test");

        verify(sender, never())
                .send(any(SimpleMailMessage.class));
    }
}
~~~

Đây là bằng chứng tốt cho một business guard **trong phạm vi đơn vị mã đang test**. Nó vẫn chưa chứng minh có suppression check giống vậy trong async retry worker, provider fallback hoặc manual replay. Các đường gửi khác cần integration tests để tránh bypass.

## 13. Đừng mock `createMimeMessage()` mà quên đối tượng MIME thật

Một lỗi trong unit test HTML/attachment là:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage mimeMessage = sender.createMimeMessage();
// Với mock mặc định, giá trị trả về có thể là null.
~~~

Nếu production code dùng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(sender.createMimeMessage(), true);
~~~

một mock chưa stub `createMimeMessage()` có thể gây lỗi null, dù code production dùng sender thật tạo được message.

### Cách test MIME composition phù hợp

Có thể tạo `MimeMessage` thật từ Jakarta Mail `Session` trong test và chỉ mock thao tác send:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSender;
import static org.mockito.Mockito.*;

JavaMailSender sender = mock(JavaMailSender.class);
Session session = Session.getInstance(new Properties());

when(sender.createMimeMessage())
        .thenAnswer(invocation -> new MimeMessage(session));
~~~

Hoặc dùng một `JavaMailSenderImpl` cục bộ như **MIME factory**, không cấu hình kết nối SMTP, rồi kiểm tra message structure. Việc có một `MimeMessage` thật giúp test header, multipart, charset và attachment, nhưng vẫn không tự kiểm chứng transport/delivery.

### Đừng mock luôn `MimeMessage` nếu cần test cấu trúc MIME

Nếu `MimeMessage`, `MimeMessageHelper` và `JavaMailSender` đều là mocks, test có thể chỉ chứng minh một chuỗi method calls, không biết thực tế MIME có hợp lệ hay không. Với nội dung HTML/multipart, nên dùng Jakarta Mail thật để parse/serialize message ở tầng test tương ứng.

## 14. Viết một service soạn MIME có hai phiên bản nội dung

Ví dụ một email receipt có plain text và HTML:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlReceiptMailService {

    private final JavaMailSender sender;

    public HtmlReceiptMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String to, String orderId)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime, true, "UTF-8");

        helper.setFrom("billing@example.test");
        helper.setTo(to);
        helper.setSubject("Your receipt " + orderId);
        helper.setText(
                "Your receipt is ready.",
                "<html><body><p>Your receipt is ready.</p></body></html>"
        );

        sender.send(mime);
    }
}
~~~

Lớp này không có template engine, không có suppression hoặc audit; đây là **ví dụ giới hạn ở MIME composition**. Trong production, HTML phải xuất phát từ template/render pipeline có escaping an toàn. Việc mock sender không xác minh TLS, SPF/DKIM/DMARC hay inbox placement.

### Unit test MIME thật, sender mock

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class HtmlReceiptMailServiceTest {

    @Test
    void buildsMimeMessageWithExpectedHeaders()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        when(sender.createMimeMessage()).thenAnswer(
                invocation -> new MimeMessage(
                        Session.getInstance(new Properties())));

        HtmlReceiptMailService service =
                new HtmlReceiptMailService(sender);
        service.send("buyer@example.test", "ord-184");

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals("Your receipt ord-184",
                actual.getSubject());
        assertEquals("buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

Test trên xác minh các header chính và multipart, không xác minh đầy đủ mọi body part. Nếu cần khẳng định **plain text alternative và HTML đúng nội dung/charset**, hãy phân tích MIME parts thật theo cây, tìm `text/plain` và `text/html`, đối chiếu decoded content. **Không cố định rằng HTML luôn là part số 1**: một `multipart/mixed` có thể chứa `multipart/alternative` lồng trong và thứ tự có thể đổi khi thêm inline images/attachments.

## 15. MIME test có thể bắt nhiều lỗi hơn verify send

Một test tốt đối với MIME nên xem:

| Đối tượng kiểm tra | Vì sao |
| --- | --- |
| `From`, `To`, `Reply-To` | Địa chỉ/header được build đúng |
| Subject và charset | Unicode không bị hỏng |
| `text/plain` | Người dùng không xem HTML vẫn đọc được |
| `text/html` | Bố cục/template đúng |
| `multipart/alternative` | Plain và HTML là hai lựa chọn nội dung |
| Attachment disposition/name | File đính kèm được khai báo đúng |
| Content type | MIME metadata nhất quán với file |
| `Content-ID` và tham chiếu `cid:` | Inline resource tương ứng |
| Tổng kích thước MIME | Không vượt giới hạn sản phẩm/provider |
| Header injection | Input không tin cậy không tạo header sai |
| Bcc/envelope behavior | Không lộ Bcc trong header được chuyển phát |

Test bằng mock chỉ quan sát `helper.addAttachment(...)` hoặc `sender.send(...)` **không chắc** phản ánh encoding khi MIME được serialize. Test structure với Jakarta Mail rồi test transport bằng fake SMTP sẽ cung cấp bằng chứng rộng hơn.

### Content tests cũng có giới hạn

Một multipart hợp lệ không bảo đảm provider sẽ chấp nhận vì size policy, DKIM signature, domain reputation hoặc recipient-specific filtering. MIME composition là **điều kiện cần**, không phải bằng chứng deliverability.

## 16. Phân biệt SMTP envelope và message headers

Một bức thư có thể có:

~~~text
SMTP envelope:
  MAIL FROM: bounce@example.org
  RCPT TO: recipient@example.net
  RCPT TO: hidden@example.net

Message headers:
  From: billing@example.org
  To: recipient@example.net
  Subject: Invoice
  (Bcc not displayed as delivered header)
~~~

Điều này quan trọng khi test Bcc:

- Một unit test có thể chứng minh code gọi `helper.setBcc(...)`.
- Một SMTP integration test phải xác minh hidden recipient được đưa vào **envelope recipients**.
- Không dùng việc không thấy `Bcc:` trong captured raw message làm bằng chứng hidden recipient không nhận; Bcc thường không xuất hiện trong headers được giao.
- Không để địa chỉ Bcc bị đưa nhầm vào `To` hoặc HTML body.

Với SMTP fake server, quan sát **RCPT TO commands** và MIME headers ở các tầng riêng. Một số thư viện fake server chỉ đưa ra `receivedMessages`, không expose mọi envelope detail; nếu cần assert envelope, chọn server/transport instrumentation có API thích hợp.

## 17. Local SMTP integration test: có socket thật nhưng vẫn không đo Internet delivery

Để kiểm tra `JavaMailSenderImpl` thực sự kết nối và truyền MIME, có thể dùng một SMTP test server local như **GreenMail**, **SubEthaSMTP/Wiser** hoặc công cụ tương đương. Mailpit/MailHog cũng có thể dùng như SMTP capture trong môi trường phát triển.

Ở đây ví dụ GreenMail với một SMTP test port. Dependency test có thể gồm:

~~~gradle
dependencies {
    testImplementation("com.icegreen:greenmail-junit5:<compatible-version>")
}
~~~

`<compatible-version>` là placeholder cần chọn theo Java/Jakarta Mail/Spring version của dự án; nó không phải version có thể build nguyên dạng. Nếu dùng GreenMail test server core thay cho JUnit extension, thêm artifact phù hợp theo dependency management của dự án.

### Ví dụ chạy SMTP test server tại loopback

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class ReceiptSmtpIntegrationTest {

    private GreenMail smtpServer;

    @BeforeEach
    void startServer() {
        smtpServer = new GreenMail(ServerSetupTest.SMTP);
        smtpServer.setUser(
                "buyer@example.test", "buyer", "test-password");
        smtpServer.start();
    }

    @AfterEach
    void stopServer() {
        if (smtpServer != null) {
            smtpServer.stop();
        }
    }

    @Test
    void submitsMessageToLocalSmtpServer() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(ServerSetupTest.SMTP.getPort());

        ReceiptMailService service = new ReceiptMailService(sender);
        service.sendReceipt("buyer@example.test", "ord-184");

        MimeMessage[] received = smtpServer.getReceivedMessages();
        assertEquals(1, received.length);
        assertEquals("Receipt for order ord-184",
                received[0].getSubject());
    }
}
~~~

Ví dụ này dùng GreenMail test SMTP server và cổng của `ServerSetupTest.SMTP`; trong CI có thể chọn cổng khả dụng/cấu hình riêng để tránh đụng cổng giữa các test process. Trong ví dụ `ReceiptMailService` gửi text đơn giản, không có TLS/auth vì server local được thiết lập theo test. Khi dùng GreenMail version khác, cần chọn artifact và API tương thích.

### Bằng chứng thu được

Nếu test xanh, ta biết:

1. `JavaMailSenderImpl` đã dùng cấu hình test để thực hiện SMTP submission.
2. Local SMTP test server đã nhận message.
3. Subject có thể được parse từ message trong test server.

Nhưng không biết production host, TLS, account credentials, DNS records và real recipient MX có hoạt động hay không. **Local SMTP integration test nâng mức bằng chứng từ method invocation lên protocol submission, không nâng thẳng lên Internet deliverability.**

## 18. Test local SMTP với nhiều cấu hình và lỗi chủ động

Local test server có thể được cấu hình để giả lập:

- Không kết nối được socket.
- Timeout trước/during SMTP.
- Relay trả `421` tạm unavailable.
- `550 5.1.1` từ chối recipient.
- `535` authentication failure.
- `554` content/policy rejection.
- Mất kết nối sau DATA.
- Giới hạn kích thước hoặc nhiều người nhận.

Không phải công cụ test nào cũng hỗ trợ **scripted SMTP replies theo từng phase**. Với GreenMail hoặc Mailpit, khả năng mô phỏng failures có thể hạn chế; khi cần chính xác `RCPT TO`/DATA final reply, dùng một programmable fake SMTP server hoặc custom test fixture có xác nhận phase.

### Ví dụ kiểm thử kết nối thất bại

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpConnectionFailureTest {

    @Test
    void reportsTransportFailureWithoutAListeningServer() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(1); // Giả sử không có SMTP service

        sender.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "500");
        sender.getJavaMailProperties().put(
                "mail.smtp.timeout", "500");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("buyer@example.test");
        message.setSubject("Probe");
        message.setText("Test content");

        assertThrows(MailException.class,
                () -> sender.send(message));
    }
}
~~~

Chú ý: test dựa vào port 1 có thể thay đổi hành vi theo môi trường; trong production CI, nên cấp một port local **đã bảo đảm không có listener** hoặc dùng fake network boundary được kiểm soát, tránh flakiness. Đừng chạy bài test này trỏ vào SMTP account hoặc recipient thật.

### Tại sao phải test failure paths?

Một app có thể chạy đúng khi relay trả 250 nhưng sai nghiêm trọng khi:

- `550` bị coi là retryable và gửi vô hạn.
- `451` bị coi là permanent, bỏ thư.
- Lỗi account `535` làm toàn hệ thống reconnect storm.
- Timeout sau DATA bị coi là chắc chắn chưa gửi, gây duplicate.

Mock có thể kiểm tra policy sau khi được cung cấp failure category, còn SMTP integration giúp kiểm tra **phân loại lỗi thực tế** từ transport.

## 19. Test STARTTLS và SMTP authentication không nằm trong mock

Một hệ thống Spring Boot có thể cấu hình:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: application-identity
    password: FROM_SECRET_MANAGER
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Các giá trị là ví dụ cấu hình Spring Boot SMTP, không phải credentials dùng được; `FROM_SECRET_MANAGER` chỉ là placeholder không nên commit như password thật. Tùy provider, dùng implicit TLS trên port 465 thay vì STARTTLS, OAuth2 hoặc API riêng. Kiểm tra tài liệu provider/protocol.

Một test Mockito xanh **không thể** xác minh STARTTLS có được negotiation, certificate chain có hợp lệ hoặc AUTH được chấp nhận. Để kiểm tra:

- Dùng test relay TLS có certificate/truststore cấu hình rõ.
- Dùng environment staging hoặc provider account test được cấp quyền.
- Kiểm tra hostname verification, TLS mode, cổng và timeouts.
- Tách validation credential khỏi việc gửi thư tới recipient thật.

### Không trust-all để làm test xanh

Nếu SMTP test thật bị lỗi chứng chỉ, không sửa bằng cách tắt hostname verification hoặc chấp nhận mọi certificate trong production. Test phải phát hiện cấu hình TLS sai, không che giấu nó.

## 20. Kiểm thử với SMTP provider thật vẫn chưa phải deliverability end-to-end

Giả sử staging gửi tới provider và nhận final SMTP 250. Kết quả:

~~~text
Application -> provider SMTP: ACCEPTED
Provider queue: QUEUED
Remote MX: TEMPORARILY DEFERRED
Later: BOUNCED
~~~

Nếu chỉ xem log ứng dụng `Mail send succeeded`, team có thể báo “đã gửi thành công” dù người nhận không có thư. Muốn biết tiếp, phải quan sát:

- Provider dashboard hoặc API message status.
- Delivery/bounce/deferral events.
- SMTP DSN nếu tích hợp được, với các giới hạn và độ tin cậy tương ứng.
- Correlation giữa application notification ID và provider message ID.
- Thời điểm và trạng thái của từng người nhận.

Provider success là **bằng chứng về provider-side handling**, không tự xác nhận inbox placement. Một provider có thể chấp nhận message nhưng về sau drop, reject, defer hoặc chuyển qua nhiều relay theo hợp đồng.

## 21. Delivery events là dữ liệu bất đồng bộ, không phải kết quả của mock

Để theo dõi sau khi SMTP provider chấp nhận, một số dịch vụ cung cấp webhook hoặc API trạng thái. Một flow có thể là:

~~~mermaid
sequenceDiagram
    participant App as Spring application
    participant SMTP as SMTP provider
    participant MX as Recipient domain
    participant Hook as Webhook consumer
    App->>SMTP: SMTP submission
    SMTP-->>App: Accepted / queued
    SMTP->>MX: Delivery attempt
    MX-->>SMTP: Temporary / accept / reject
    SMTP-->>Hook: Delivered / bounced / deferred event
    Hook->>App: Update status projection
~~~

Lời gọi `sender.send(...)` chỉ tham gia giai đoạn đầu; webhook có thể đến sau vài giây, vài phút hoặc muộn hơn. Thậm chí event có thể đến **không theo thứ tự**, bị lặp, bị mất hoặc bị chậm do hệ thống tiếp nhận webhook.

### Một payload minh họa

~~~json
{
  "providerMessageId": "provider-msg-184",
  "recipient": "recipient@example.test",
  "eventType": "delivered",
  "occurredAt": "2026-11-12T10:05:10Z",
  "providerEventId": "evt-2048"
}
~~~

Đây là **JSON minh họa**, không phải schema chung của mọi provider. Những tên như `delivered`, `processed`, `deferred`, `dropped`, `bounce` và `complaint` có semantics khác nhau theo dịch vụ. Adapter phải chuẩn hóa nhưng cũng lưu được provider reason cần thiết.

### Những việc webhook consumer phải làm

1. Xác minh chữ ký/source theo đúng provider.
2. Kiểm tra timestamp/replay protection nếu hợp đồng hỗ trợ.
3. Correlate đúng provider account, message ID, attempt ID và recipient.
4. Deduplicate event ID theo scope phù hợp.
5. Lưu event bền vững trước khi ack thành công.
6. Cập nhật trạng thái bằng quy tắc không làm lùi lifecycle.
7. Giữ khả năng đối soát khi event bị trễ hoặc thiếu.
8. Không tự resend chỉ vì chưa thấy `delivered`.

**Webhook test với payload mock** có giá trị để kiểm tra consumer, nhưng vẫn không chứng minh provider ngoài đời sẽ gửi đủ events hay thư sẽ vào Inbox.

## 22. Kiểm tra provider event bằng test phù hợp

Một test nhận webhook có thể dùng dữ liệu fixture:

~~~text
Given:
  notification N submitted through provider P
  providerMessageId = m-184
  recipient = r-42

When:
  signed event delivered(m-184, r-42) arrives

Then:
  event is verified
  deduplicated by provider event identity
  status projection becomes DELIVERED
  no new SMTP submission is scheduled
~~~

Đối chứng:

~~~text
When:
  event with invalid signature arrives

Then:
  do not change delivery status
  do not expose raw event to business handler
  log sanitized security error
~~~

Và:

~~~text
When:
  same delivered event arrives twice

Then:
  one logical event is processed
  counters and user notifications are not doubled
~~~

### Bằng chứng đạt được

Đó là **consumer integration/contract evidence**, không phải chứng minh một email thật đã tới recipient. Nếu provider sandbox phát giả `delivered`, test chỉ chứng minh hệ thống xử lý event theo đúng hợp đồng mô phỏng.

Muốn đo thực tế, cần biết provider đã quan sát điều gì và đối chiếu với dữ liệu mail thực trong môi trường được kiểm soát.

## 23. Gửi một email tới nhiều người nhận: đừng gộp kết quả

Một MIME message có thể gửi tới nhiều `RCPT TO`:

~~~text
MAIL FROM: billing@example.org
RCPT TO: alice@example.net -> 250 accepted
RCPT TO: bob@example.net   -> 550 rejected
RCPT TO: carol@example.net -> 250 accepted
~~~

Tùy client/protocol/provider và cấu hình gửi từng phần, một số recipient có thể được chấp nhận, số khác bị từ chối. Nếu application chỉ lưu:

~~~text
notification.status = SENT
~~~

thì không thể biết người nào thất bại. Nếu retry gửi lại nguyên danh sách mà không kiểm soát recipient-level outcomes, có thể tạo duplicate cho Alice và Carol.

### Mô hình theo recipient

~~~text
notificationId: notice-184
  |
  +-- recipient Alice: SUBMITTED
  +-- recipient Bob:   REJECTED_PERMANENT
  +-- recipient Carol: SUBMITTED
~~~

Với gửi quan trọng hoặc volume cao, thường tốt hơn tạo **một notification/recipient record cho mỗi người nhận** để idempotency, suppression, retries và metrics rõ ràng.

### Test cần đo nhiều cấp

- Unit test mock: các recipient được chọn đúng.
- SMTP integration: từng RCPT TO được accepted/rejected theo script.
- Provider events: correlate delivery/bounce theo recipient.
- Inbox tests: kiểm tra riêng mailbox mẫu của từng provider/domain.

`MailSendException` và nested exceptions có thể chứa thông tin hữu ích về lỗi gửi, nhưng đừng giả định một `MailSendException` tổng hợp sẽ cung cấp chính xác mọi recipient outcome theo cùng schema ở mọi transport.

## 24. Lỗi nhận thức: “Có một mail ở Inbox test nên mọi mail đều deliver được”

Ngay cả khi gửi thành công tới một mailbox thử nghiệm, kết quả không có tính phổ quát:

- Gmail, Outlook, Yahoo và mail server doanh nghiệp có filtering khác nhau.
- Một tổ chức có thể quarantine attachment hoặc chặn domain gửi.
- Một mailbox mới ít tương tác có thể bị phân loại khác mailbox đã tin sender.
- Vùng địa lý, IP gửi, domain reputation và chiến dịch có thể ảnh hưởng.
- Cùng domain nhưng nội dung khác, volume khác hoặc người nhận khác có thể tạo kết quả khác.
- Provider có thể thay đổi chính sách mà code ứng dụng không đổi.

### Kết luận phù hợp

“Email kiểm thử X từ sender Y đã xuất hiện ở Inbox của mailbox seed Z vào thời điểm T” là một quan sát có giá trị.

“Deliverability của mọi email là 100%” từ một quan sát đó là **suy luận vượt phạm vi**.

## 25. Seed mailbox testing: quan sát Inbox thật có giới hạn

**Seed testing** dùng những mailbox thử nghiệm mà nhóm có quyền quản lý hoặc được cấp phép, thuộc nhiều nhà cung cấp/email domains khác nhau. Quy trình:

1. Tạo các địa chỉ seed theo provider/domain được phép.
2. Gửi nội dung test đại diện qua đúng SMTP provider, sender domain và route.
3. Gắn unique test correlation ID trong header/body phù hợp, không chứa secret.
4. Chờ một khoảng quan sát có giới hạn đã định nghĩa.
5. Đọc mailbox seed qua API/IMAP được cấp quyền.
6. Ghi **Inbox**, Spam/Junk, Other/Promotions, Quarantine, Not Found hoặc Unknown theo từng mailbox.
7. Correlate với provider accepted/delivered/bounce events.
8. Báo cáo thời điểm, sample size, provider/domain, template/category và điều kiện test.

### Ví dụ báo cáo giới hạn

| Seed mailbox | Kết quả quan sát | Kết luận |
| --- | --- | --- |
| Gmail seed A | Inbox | Vào Inbox của seed A |
| Outlook seed B | Junk | Bị phân loại Junk ở seed B |
| Mail server C | Quarantined | Chính sách của server C chặn |
| Yahoo seed D | Not observed trong window | Chưa có bằng chứng placement |

Các kết quả ở bảng này **chỉ là ví dụ**, không phải đo lường thực tế hay dự báo cho nhà cung cấp được nêu.

### Tránh những kết luận quá mức

Một bộ seed mailbox không nhất thiết đại diện toàn bộ user population. Nó có thể được dùng để **phát hiện sớm xu hướng bất thường**, so sánh thay đổi template/domain/route và theo dõi một số loại mailbox; không phải phép chứng minh email của mọi recipient đều nằm Inbox.

### Kiểm thử đúng quyền

Không đăng nhập mailbox của khách hàng hoặc gửi test mail tới người lạ để “đo deliverability” khi chưa được cho phép. Dùng seed accounts thuộc quyền quản lý hoặc môi trường được ủy quyền, và dùng test data không nhạy cảm.

## 26. SPF, DKIM và DMARC: unit mock không thể kiểm tra

Domain authentication là một phần quan trọng của email vận hành thật. Tuy nhiên cần hiểu chính xác:

### SPF

SPF đánh giá xem IP gửi có được phép gửi cho một **domain identity** sử dụng trong SMTP envelope/HELO theo SPF hay không. Nó không đơn giản xác nhận rằng `From:` header được phép chỉ vì text trùng domain.

### DKIM

DKIM sử dụng chữ ký trong message headers. Recipient có thể kiểm tra chữ ký bằng public key được công bố qua DNS của domain ký. Chữ ký có thể bị ảnh hưởng nếu nội dung/header bị thay đổi không tương thích.

### DMARC

DMARC kiểm tra alignment giữa **header From domain** và một identity xác thực thành công bởi SPF hoặc DKIM (theo quy tắc alignment), đồng thời domain có thể công bố policy như `none`, `quarantine` hoặc `reject`.

### Một số trường hợp dễ nhầm

| Trường hợp | Có nghĩa gì? |
| --- | --- |
| SPF pass nhưng envelope domain không aligned với From | Chưa đủ để kết luận DMARC pass bằng SPF |
| DKIM pass nhưng `d=` khác domain From không aligned | Chưa đủ để kết luận DMARC pass bằng DKIM |
| SPF aligned pass hoặc DKIM aligned pass | Có thể đáp ứng điều kiện DMARC alignment theo cấu hình |
| SPF/DKIM/DMARC pass | Không chứng minh nội dung an toàn, người nhận hợp lệ hoặc Inbox placement |
| DMARC policy `p=none` | Là chính sách theo dõi, không chứng minh domain reputation tốt |

### Vì sao mock không đo được?

Mock không gửi qua IP thật, không ký DKIM trên wire, không tra DNS tại receiving side và không nhận `Authentication-Results` do trusted ingress tạo. Một unit test như:

~~~java
assertEquals("sender@example.org", message.getFrom());
~~~

không hề kiểm tra SPF, DKIM hoặc DMARC.

### Cách kiểm tra ngoài mock

- Xác minh domain được cấu hình với provider theo tài liệu thực tế.
- Kiểm tra DNS SPF, DKIM selectors/public keys, DMARC policy và alignment với header From.
- Gửi message có kiểm soát tới test mailbox và xem authentication results từ **đường nhận đáng tin**.
- Đối chiếu envelope domain, DKIM `d=`, From domain và dấu xác thực thực.
- Theo dõi policy/reporting, lưu ý forwarding và mailing list có thể làm phức tạp kết quả.

Không tin một `Authentication-Results` header bất kỳ do sender tự thêm trong nội dung raw. Chỉ diễn giải kết quả do receiving system/đường ingress đáng tin tạo ra.

## 27. DKIM pass không bằng Inbox

Một email có thể:

~~~text
SPF:   PASS
DKIM:  PASS
DMARC: PASS
SMTP:  ACCEPTED
Placement: SPAM
~~~

Điều này không mâu thuẫn. Domain authentication chứng minh các khía cạnh nguồn gửi/chữ ký, trong khi spam filtering còn xem reputation, nội dung, lịch sử tương tác, mức độ mong muốn của người nhận, tần suất gửi và các tín hiệu khác.

Ngược lại, một mailbox seed có thể đặt thư vào Inbox trong một tình huống cụ thể dù cấu hình authentication cần cải thiện; điều đó không bảo đảm trạng thái ổn định hoặc phù hợp với chính sách của các receiving domains khác.

### Các điểm nên quan sát

- SPF/DKIM/DMARC authentication và alignment.
- Sender domain verification trong provider.
- IP/domain reputation khi có dữ liệu.
- Bounce/deferral/complaint rates.
- Recipient list hygiene, consent và unsubscribe.
- Loại nội dung, links, attachment, template version.
- Số lượng gửi và tốc độ tăng lưu lượng.
- Provider-level suppression và quota.

Không dùng một yếu tố đơn lẻ để kết luận tỷ lệ vào Inbox.

## 28. Reputation và lịch sử gửi: yếu tố mock bỏ trống

Thực tế email deliverability thay đổi theo:

- Lịch sử domain/IP gửi.
- Shared IP hay dedicated IP.
- Tốc độ gửi tăng đột ngột.
- Phản ánh spam và unsubscribe.
- Tỷ lệ địa chỉ không hợp lệ/hard bounce.
- Danh sách nhận được cập nhật và xác minh.
- Người nhận từng đánh dấu mail mong muốn hoặc không mong muốn.
- Domain sending bị giả mạo hoặc cấu hình authentication sai.
- Chiến dịch có nội dung/link/tệp đính kèm gây nghi ngờ.
- Provider throttling và chính sách riêng theo receiving domain.

Không có Mockito stub nào tạo được reputation ngoài đời. Thay vào đó, cần **operational monitoring, account/provider telemetry và experiment được kiểm soát**, diễn giải với độ bất định.

### Không cố “bypass bộ lọc”

Mục tiêu cải thiện deliverability hợp lệ không phải tìm cách lách spam filtering hay gửi tiếp khi người nhận không đồng ý. Ưu tiên:

1. Gửi cho recipient có cơ sở liên hệ và consent phù hợp.
2. Xử lý unsubscribe/suppression đúng.
3. Xác thực domain gửi.
4. Giữ nội dung đúng mục đích và minh bạch.
5. Giới hạn tần suất, tránh spam và retry storm.
6. Điều tra bounce/complaint thay vì đổi provider để gửi lại bằng mọi giá.

## 29. Địa chỉ hợp lệ cú pháp không chứng minh mailbox tồn tại

Đoạn kiểm tra địa chỉ có thể:

~~~java
new jakarta.mail.internet.InternetAddress(
        "buyer@example.test", true);
~~~

hoặc dùng một validator khác. Nhưng syntactic validity chỉ cho biết chuỗi **có thể** tuân thủ cú pháp địa chỉ; nó không chứng minh:

- Domain có MX hoặc mail routing phù hợp.
- Mailbox cụ thể tồn tại.
- Recipient nhận email từ sender hiện tại.
- Mailbox còn quota.
- Receiving policy cho phép message.
- Email vào Inbox.

Hơn nữa, một domain có thể chấp nhận mọi RCPT TO rồi gửi bounce sau. Một số receiving systems cũng không tiết lộ tồn tại mailbox tại SMTP phase. Không dựa vào một SMTP “address verification probe” như sự thật tuyệt đối.

### Kiểm tra địa chỉ nên nhằm mục tiêu gì?

- Loại input rõ ràng không hợp lệ trước khi tạo notification.
- Bảo vệ khỏi header injection.
- Chuẩn hóa theo quy tắc đã chọn, không phá địa chỉ hợp lệ.
- Không ngầm định canonicalization của mọi provider giống nhau.
- Xử lý hard bounce/suppression dựa trên bằng chứng đáng tin sau khi gửi.

Nếu người nhận chủ động xác minh địa chỉ qua link/OTP, đó là một bằng chứng về quyền kiểm soát mailbox tại thời điểm xác minh, nhưng cũng không bảo đảm các email tương lai luôn được giao vào Inbox.

## 30. Trạng thái `DELIVERED` trên dashboard cần có nguồn

Một lỗi thiết kế:

~~~java
sender.send(message);
notificationRepository.updateStatus(id, "DELIVERED");
~~~

Vì method trả bình thường chỉ chứng minh submission theo transport. Nên tách:

~~~java
sender.send(message);
notificationRepository.updateStatus(id, "SUBMITTED");
~~~

Sau đó nhận provider event (nếu có) để cập nhật delivery state.

### Cần lưu cả source của trạng thái

~~~json
{
  "notificationId": "notif-184",
  "submissionStatus": "SUBMITTED",
  "submissionEvidence": "SMTP_FINAL_SUCCESS",
  "submittedAt": "2026-11-12T10:00:05Z",
  "deliveryStatus": "DELIVERED",
  "deliveryEvidence": "PROVIDER_VERIFIED_EVENT",
  "deliveryObservedAt": "2026-11-12T10:05:10Z",
  "inboxPlacement": "UNKNOWN"
}
~~~

Đây là model ứng dụng. Một số providers không có delivery event; khi đó `deliveryStatus` phải giữ `UNKNOWN`, không tự đổi vì đã qua 5 phút hoặc không thấy bounce.

### Không dùng `sent=true` cho mọi mục đích

Nếu hệ thống bắt buộc một boolean để tương thích API cũ, hãy tài liệu hóa rõ:

~~~text
sent = true means "SMTP submission accepted"
~~~

Không dùng cùng trường này để tính inbox placement hay engagement.

## 31. Submission success trong batch cũng không chứng minh từng recipient delivered

Khi gọi `sender.send(SimpleMailMessage... messages)` hoặc gửi MIME nhiều recipients, lỗi có thể xảy ra ở một phần batch. Một `MailSendException` có thể chứa failed messages và nested causes. Nhưng:

- Một batch method không tạo một “atomic all-or-nothing delivery transaction”.
- SMTP conversation/transport/provider behavior có thể khác nhau.
- Một message đã accepted có thể bounce sau.
- Một message không ném lỗi cũng chưa chắc được giao cuối cùng.

### Cách thiết kế cho batch production

Lưu per-notification/per-recipient:

~~~text
notificationId
recipientId
messageCategory
attemptId
providerKey
submitStatus
deliveryStatus
normalizedFailureReason
~~~

Một worker nên biết đã attempt gì, provider accepted gì, recipient nào phải stop/retry. Tránh tạo metric “100 messages sent” từ việc gọi `send(messages)` một lần không ném exception.

## 32. SMTP outcome unknown: thậm chí có exception vẫn có thể đã gửi

Một trường hợp quan trọng:

~~~text
Application sends SMTP DATA
Relay receives final dot and perhaps accepts message
Connection drops before client receives final reply
JavaMailSender throws MailException
~~~

Từ góc nhìn ứng dụng, chưa biết relay đã accepted hay chưa. **Không nên** kết luận:

~~~text
Exception -> definitely not sent
~~~

hoặc:

~~~text
No exception -> delivered to Inbox
~~~

Cả hai suy luận đều sai.

### State hữu ích

`SUBMISSION_UNKNOWN` cho phép giữ correlation/attempt history và thực hiện reconciliation. Nếu provider cho phép tra cứu message status theo provider ID hoặc event stream, đối chiếu trước khi retry. Nếu không có nguồn xác định, cần quyết định dựa trên rủi ro gửi trùng và chính sách nghiệp vụ (ví dụ OTP, hóa đơn, marketing có mức chấp nhận duplicate khác nhau).

### Mock không kiểm tra được failure window thực

Một test `doThrow(new MailSendException(...))` không mô phỏng relay đã nhận DATA rồi mất phản hồi. Muốn kiểm chứng nhánh này, cần scripted SMTP server có thể:

1. Nhận đầy đủ DATA.
2. Đóng kết nối trước final reply.
3. Ghi log rằng server đã đọc body.
4. Để client nhận lỗi.
5. Kiểm tra worker chuyển `SUBMISSION_UNKNOWN` và **không resend mù**.

Vẫn không thể từ server scripted suy ra mọi transport ngoài đời sẽ phân loại chính xác; nhưng test này tốt hơn nhiều so với stub exception không có phase semantics.

## 33. Không suy ra “đã đọc” từ tracking pixel

Một email có thể chứa ảnh từ xa phục vụ open tracking. Số lượt tải ảnh không phải số người thật mở mail vì:

- Proxy/cache hoặc hệ thống bảo vệ riêng tư có thể fetch ảnh tự động.
- Người nhận đọc plain text hoặc tắt ảnh thì không phát pixel.
- Email client có thể prefetch hoặc trì hoãn tải ảnh.
- Security scanners có thể mở link/ảnh mà không có tương tác thực của người dùng.

**Open rate** vì thế là một proxy có giới hạn, không phải phép đo chính xác “đã đọc”. Nếu sản phẩm cần xác nhận một hành động quan trọng, dùng một thao tác có authentication trong ứng dụng hoặc một workflow xác nhận riêng, chứ không dùng pixel tracking.

### Click tracking cũng có nhiễu

Security scanners đôi khi truy cập links tự động. Không dùng một HTTP GET của tracking link làm bằng chứng user đã chủ động phê duyệt, thanh toán hoặc xác nhận điều khoản.

## 34. Không lấy absence of bounce làm bằng chứng delivered

Giả sử ứng dụng gửi 1.000 messages và sau 10 phút chưa có bounce. Có nhiều khả năng:

- Provider vẫn queue hoặc retry downstream.
- Webhook consumer bị lỗi nên event chưa được nhận.
- Một số servers không trả DSN như dự kiến.
- Bản ghi status chưa được đồng bộ.
- Message được chấp nhận nhưng lọc spam hoặc quarantine.

Vì vậy:

~~~text
No bounce observed != Delivered
No error observed  != Inbox
~~~

Khi chưa đủ bằng chứng, giữ trạng thái `UNKNOWN` hoặc `PENDING_PROVIDER_EVENT` theo mô hình hệ thống. Nếu cần policy kết thúc chờ, đánh dấu `OUTCOME_NOT_OBSERVED_WITHIN_WINDOW` chứ không tự chuyển sang `DELIVERED`.

## 35. Phải xác định mẫu số của metric deliverability

Một báo cáo kiểu “delivery rate = 99%” chưa đủ nếu không cho biết số nào được tính vào mẫu số.

Một số chỉ số riêng biệt:

\[
\text{Submission acceptance rate}
= \frac{\text{Số submission được relay chấp nhận}}
{\text{Số submission đã có kết quả được phân loại}}
\]

\[
\text{Provider-reported delivery rate}
= \frac{\text{Recipient submissions được provider báo delivered}}
{\text{Recipient submissions thuộc cohort đủ điều kiện quan sát}}
\]

\[
\text{Seed inbox placement rate}
= \frac{\text{Seed messages quan sát thấy ở Inbox}}
{\text{Seed messages có kết quả placement xác định}}
\]

Với chỉ số seed, phải báo cáo thêm **số messages chưa quan sát được**, không âm thầm loại bỏ hàng loạt test “not found” để làm tỷ lệ đẹp hơn. Với provider-reported delivery, phải quy định rõ observation window, handling unknown/deferred, provider event delays và dedup per recipient.

### Không trộn lẫn các đơn vị đếm

- Một notification có thể nhiều recipients.
- Một recipient submission có thể có nhiều provider events.
- Một business event có thể bị retry nhiều attempts.
- Một delivery event có thể bị webhook redelivery.

Nếu đếm `delivered` event rows làm số mail delivered mà không dedup, con số có thể vượt số message thật. Nên chọn **đơn vị thống kê** (notification/recipient/attempt) và cố định trong dashboard.

## 36. Nguy cơ một “integration test” thật ra vẫn đang dùng mock

Một số project dùng `@SpringBootTest` và xem đó là integration test. Nhưng nếu Spring context đã thay `JavaMailSender` bằng Mockito bean, bài test **vẫn không thực hiện SMTP I/O**, dù đã khởi động toàn bộ application context.

Ví dụ ở các phiên bản Spring hỗ trợ `@MockitoBean`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class MailApplicationContextTest {

    @MockitoBean
    JavaMailSender sender;

    @Autowired
    ReceiptMailService service;

    @Test
    void invokesSender() {
        service.sendReceipt("buyer@example.test", "ord-184");
        org.mockito.Mockito.verify(sender)
                .send(org.mockito.ArgumentMatchers.any(
                        org.springframework.mail.SimpleMailMessage.class));
    }
}
~~~

Trong project dùng phiên bản Spring Boot/Spring Framework cũ hơn, annotation thay bean mock có thể là `@MockBean` hoặc một cơ chế khác. **Cần kiểm tra version đang dùng** thay vì copy annotation không tương thích.

### Nó kiểm tra được gì?

Nó kiểm tra wiring của `ReceiptMailService` trong Spring context và việc service gọi mock. Nó vẫn **không xác minh** host/port/TLS/network/SMTP relay hoặc deliverability.

### Làm rõ hai loại integration test

**Wiring integration test có mock:** nhiều Spring beans chạy thật, nhưng transport bị thay bằng fake. Tốt cho orchestration và configuration boundaries.

**SMTP transport integration test:** ứng dụng dùng `JavaMailSenderImpl` thật kết nối tới server test hoặc provider test. Cần để kiểm tra protocol/config.

Tên test và báo cáo CI phải nói đúng loại. Không gắn nhãn “mail delivery integration passed” cho một context test mà transport vẫn là Mockito bean.

## 37. Kiểm tra cấu hình Spring Boot Mail cũng cần hơn mock

Spring Boot có thể tạo `JavaMailSenderImpl` dựa trên `spring.mail.*` khi có các điều kiện auto-configuration thích hợp. Nhưng một unit test với mock sẽ không kiểm tra:

- Có đúng sender bean được chọn khi có nhiều beans không.
- Host/port cấu hình theo environment.
- Properties `mail.smtp.auth`, `mail.smtp.starttls.required` được truyền tới Jakarta Mail như dự kiến.
- Credential lấy từ secret manager có hợp lệ không.
- Timeout áp dụng thật.
- Sender identity có được SMTP provider cho phép không.

### Thử ở tầng cấu hình

Có thể tạo một context test **không thay sender bằng mock** và assert các properties của `JavaMailSenderImpl`, không gửi ra mạng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

void assertExpectedSmtpConfig(JavaMailSenderImpl sender) {
    assertEquals("smtp.example.org", sender.getHost());
    assertEquals(587, sender.getPort());
    Properties props = sender.getJavaMailProperties();
    assertEquals("true", props.getProperty(
            "mail.smtp.starttls.required"));
}
~~~

Đây là **configuration assertion**, không chứng minh provider đang hoạt động. Một test tiếp theo phải kiểm tra kết nối tới SMTP endpoint theo network/security boundaries.

### Khi có nhiều `JavaMailSender`

Nếu ứng dụng có `primarySender` và `backupSender`, mock một bean rồi verify không chứng minh router đã chọn đúng host thật. Kiểm tra cả:

1. Business policy chọn route nào.
2. Dependency injection/bean qualifiers trỏ vào cấu hình nào.
3. SMTP integration của từng route.
4. Failover chỉ với lỗi phù hợp; không thử B khi recipient invalid hoặc A đã accepted.

Không dùng cùng một mock cho cả A và B nếu test cần xác nhận hai route độc lập.

## 38. Không để unit test mock thay đổi trạng thái production thành DELIVERED

Một ví dụ sai:

~~~java
public void send(Notification n) {
    sender.send(n.toMimeMessage());
    repository.markDelivered(n.id());
}
~~~

Test dùng `sender = mock(JavaMailSender.class)` sẽ chạy qua `send` mà không lỗi và gọi `markDelivered`, rồi developer có thể lầm tưởng nghiệp vụ hoạt động.

### Sửa về mặt domain model

~~~java
public void submit(Notification n) {
    MimeMessage message = renderer.render(n);
    sender.send(message);
    repository.recordSubmissionAccepted(
            n.id(), clock.instant());
}
~~~

Đây là pseudocode của ứng dụng. `repository.recordSubmissionAccepted` có nghĩa **đã nhận transport success theo hợp đồng**. `DELIVERED` chỉ được cập nhật bởi nguồn bằng chứng delivery được tin cậy; `INBOX` chỉ bởi một nguồn quan sát placement tương ứng.

### Mock không được tự tạo production delivery event

Một test có thể cung cấp fake `DELIVERED` event để kiểm tra consumer, nhưng đó là **dữ liệu kiểm thử**. Không lấy kết quả ấy làm bằng chứng một SMTP account thật đã deliver.

## 39. Thiết kế attempt ledger có loại bằng chứng

Một domain record hữu ích:

~~~java
package com.example.mail.delivery;

import java.time.Instant;

public enum SubmissionOutcome {
    NOT_ATTEMPTED,
    ACCEPTED,
    EXPLICITLY_REJECTED,
    UNKNOWN
}

public enum DeliveryOutcome {
    NOT_OBSERVED,
    DEFERRED,
    DELIVERED,
    BOUNCED,
    COMPLAINED
}

public record SubmissionAttemptResult(
        String notificationId,
        String attemptId,
        String providerKey,
        SubmissionOutcome outcome,
        String normalizedError,
        Instant observedAt) {
}
~~~

Các kiểu là ứng dụng tự định nghĩa, không phải API của `JavaMailSender`. Với unit tests mock, chỉ assert service đã gọi sender, không tự tạo record `ACCEPTED` vào production DB từ mock fixture.

### Một database schema minh họa

~~~sql
CREATE TABLE mail_submission_attempt (
    id                  VARCHAR(120) PRIMARY KEY,
    notification_id     VARCHAR(120) NOT NULL,
    provider_key        VARCHAR(120) NOT NULL,
    attempt_number      INTEGER NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP,
    submit_outcome      VARCHAR(40) NOT NULL,
    evidence_type       VARCHAR(60),
    smtp_phase          VARCHAR(60),
    smtp_code           VARCHAR(20),
    normalized_error    VARCHAR(100),
    UNIQUE (notification_id, attempt_number)
);

CREATE TABLE mail_recipient_delivery (
    notification_id     VARCHAR(120) NOT NULL,
    recipient_id        VARCHAR(120) NOT NULL,
    provider_key        VARCHAR(120),
    provider_message_id VARCHAR(250),
    delivery_outcome    VARCHAR(40) NOT NULL,
    observed_at         TIMESTAMP,
    evidence_source     VARCHAR(100),
    PRIMARY KEY (notification_id, recipient_id)
);
~~~

Cần thêm tenant isolation, indexes, idempotency, timestamp semantics và retention phù hợp. Với nhiều attempts/providers, một bảng delivery projection có thể cần lưu event history hoặc per-attempt correlation để không ghi đè một delivery đã biết bằng event cũ.

### Evidence type giúp ngăn suy luận sai

Ví dụ:

~~~text
SMTP_FINAL_250
PROVIDER_API_ACCEPTED
PROVIDER_VERIFIED_DELIVERY_EVENT
CONTROLLED_SEED_MAILBOX_OBSERVATION
UNKNOWN
~~~

`MOCK_INVOCATION` **không thuộc các loại evidence được phép dùng cho trạng thái production**; nó chỉ là bằng chứng trong unit test report.

## 40. Retry và deliverability: đừng dùng retry để “ép vào Inbox”

Một lỗi:

~~~text
JavaMailSender.send() returns normally
No inbox evidence within 1 minute
Application retries same message
~~~

Nếu relay đã accepted, một bản gửi mới có thể làm recipient nhận thư trùng. Nếu thư nằm trong Spam, gửi lại cùng nội dung có thể không cải thiện và có thể tăng tín hiệu không mong muốn.

### Chính sách đúng hơn

- Retry khi lỗi transport **được phân loại là temporary và an toàn để thử lại**.
- Không retry permanent recipient/content rejection.
- Không tự resend sau accepted submission.
- Không retry mù khi `SUBMISSION_UNKNOWN`.
- Tôn trọng TTL của OTP/links và consent/suppression.
- Không chuyển provider để lách spam complaint hoặc recipient policy.
- Khi cần resend, tạo một quyết định nghiệp vụ có idempotency và audit.

### `JavaMailSender.send()` không hỗ trợ giao dịch phân tán với database

Nếu relay trả 250 nhưng DB update lỗi, worker có thể crash với record vẫn `PROCESSING`. Retry tự động có thể gửi trùng. Cần transactional outbox, attempt ledger và reconciliation; ngay cả khi có những cơ chế này vẫn không thể hứa exactly-once end-to-end SMTP delivery.

## 41. Chiến lược đo thực tế theo từng loại email

Không phải loại email nào cũng cần cùng mức đo:

| Category | Quan sát quan trọng | Gợi ý |
| --- | --- | --- |
| OTP/verification | Latency, submit errors, expired codes, bounce | Bảo đảm token TTL, có kênh hỗ trợ khi gửi không thành công |
| Password reset | Provider acceptance và kết quả giao khi có | Không log token và không dựa vào open tracking |
| Receipt/invoice | Submission status, bounce, support case | Đối chiếu với business transaction, không gửi trùng |
| Security notification | Latency, account health, missed notifications | Ưu tiên route được phê duyệt, expiry phù hợp |
| Marketing | Bounce, complaint, suppression, placement trend | Consent, list hygiene, domain authentication |
| Support reply | Delivery attempt/response correlation | Theo dõi conversation/ticket đúng phạm vi |

### Với OTP, cần thêm tín hiệu nghiệp vụ

Nếu người dùng liên tục yêu cầu gửi mã mới, đó có thể là tín hiệu thư bị chậm hoặc khó tìm; nhưng **không tự chứng minh thư đã vào Spam**. Một tỷ lệ xác minh thành công thấp có thể do UX, lỗi ứng dụng, token expiry, security controls hoặc người dùng rời bỏ quy trình. Cần kết hợp nhiều nguồn và tránh kết luận nhanh.

### Với marketing, không nên đánh đồng open rate với deliverability

Open rate bị ảnh hưởng bởi cơ chế bảo vệ riêng tư của email clients và hành vi tải ảnh. Đo complaint, bounces, suppressions, provider reputation/placement observations với giải thích nguồn và độ tin cậy.

## 42. Đánh giá thực nghiệm khi đổi SMTP provider

Một nhóm có thể chuyển từ provider A sang B và thấy unit tests vẫn xanh. Điều đó là bình thường: mock test không nhận ra khác biệt hạ tầng.

### Quy trình thay đổi có kiểm soát

1. Kiểm tra domain verification, sender identity và authentication của B.
2. Kiểm tra configuration/TLS/credentials trong staging.
3. Chạy local SMTP/MIME regression tests.
4. Gửi tới seed mailboxes được phép với payload không nhạy cảm.
5. Giới hạn canary traffic của production theo category/tenant có quyền.
6. Theo dõi acceptance, deferral, bounce và complaint theo provider.
7. Quan sát placement trend, không suy luận từ một sample.
8. So sánh cùng observation window và các cohort tương đương.
9. Kiểm tra unsubscribe/suppression được chia sẻ và không bị bypass khi đổi route.
10. Rollback hoặc giảm lưu lượng nếu tác động xấu được xác nhận.

### Không A/B bằng cách gửi hai bản cho một recipient

Gửi đồng thời cùng một email qua A và B tới cùng recipient để “xem cái nào vào Inbox” có thể gây duplicate, làm khó correlation và tạo trải nghiệm kém. Thay vì vậy, dùng seed accounts, cohort được thiết kế có kiểm soát hoặc thời điểm gửi khác nhau theo chính sách; không tự gửi hai bản cho người thật.

### Không khẳng định causal impact thiếu kiểm soát

Nếu provider B có delivery rate cao hơn tuần trước, cũng có thể do domain reputation, loại chiến dịch, recipient mix, mùa vụ hoặc số lượng gửi thay đổi. Khi so sánh nên nêu cohort, sample, thời gian, category, provider health và các yếu tố nhiễu.

## 43. Kiểm tra đúng từ địa chỉ gửi tới route nhận

Một email outbound có ít nhất các identity/route cần quan sát:

~~~text
Application sender bean
  -> SMTP host/port/account
  -> envelope MAIL FROM
  -> header From
  -> DKIM signing domain
  -> provider queue
  -> recipient MX/domain
  -> mailbox filtering
~~~

Mock `JavaMailSender` có thể xác minh `setFrom(...)` trong Java object, nhưng không cho biết:

- Envelope sender thực tế provider sử dụng.
- Return-Path được đặt thế nào.
- DKIM được ký bằng domain/selector nào.
- Provider có rewrite headers hay không.
- Receiving system đánh giá DMARC alignment ra sao.
- Thư được phân loại vào Inbox/Spam ở đích.

Khi điều tra deliverability, cần lần theo **toàn bộ chuỗi** và phân loại bằng chứng từ mỗi tầng, không chỉ mở lại unit test.

## 44. Ma trận kiểm thử: mỗi case có mục tiêu và giới hạn bằng chứng

Một bộ kiểm thử tốt không chỉ có nhiều case; nó phải làm rõ **đang quan sát tầng nào** và **không được suy ra điều gì**.

| ID | Tình huống | Tầng test | Assertion chính | Không chứng minh |
| --- | --- | --- | --- | --- |
| M01 | Receipt service gọi sender | Unit/Mockito | `send(...)` được gọi đúng lần | SMTP đã kết nối |
| M02 | Địa chỉ/subject/body trong SimpleMailMessage | Unit/ArgumentCaptor | Trường message đúng | Relay chấp nhận |
| M03 | Marketing recipient unsubscribe | Unit/Mockito | `send()` không được gọi | Mọi đường retry đều chặn |
| M04 | MailException được giả lập | Unit/Mockito | Service xử lý exception đúng | Phân loại exception thật |
| M05 | Sender bị gọi hai lần do logic | Unit/Mockito | `times(1)` phát hiện trùng | Exactly-once toàn hệ thống |
| M06 | Không tạo thư khi template thiếu | Unit/Mockito | Không gọi sender | Production template repository hoạt động |
| M07 | Mock createMimeMessage trả null | Unit | Test fixture phải trả MIME thật | Cấu hình SMTP thật |
| M08 | Plain/HTML alternative | MIME unit | Hai body parts đúng | Inbox placement |
| M09 | Attachment filename/content type | MIME unit | Header/structure đúng | File đã qua malware scan |
| M10 | Unicode subject/body | MIME unit | Decoding đúng charset | Provider nhận Unicode |
| M11 | Inline image CID | MIME unit | Content-ID và HTML reference khớp | Email client hiển thị đúng |
| M12 | Bcc không lộ trong headers | MIME/local SMTP | Header và envelope được kiểm tra | Recipient đã đọc |
| I01 | JavaMailSenderImpl kết nối fake SMTP | Local integration | Test relay nhận thư | Internet delivery |
| I02 | Local SMTP trả final 250 | Local integration | Submission accepted tại relay giả | Provider thật accepted |
| I03 | SMTP server không lắng nghe | Local integration | Transport failure được xử lý | Mọi lỗi network giống nhau |
| I04 | STARTTLS negotiation | TLS-capable integration | TLS mode/cert phù hợp test | Authentication tại provider khác |
| I05 | AUTH 535 | Scripted SMTP | Account-level failure được phân loại | Recipient invalid |
| I06 | RCPT 550 5.1.1 | Scripted SMTP | Permanent rejection dừng retry | Bounce rules của mọi provider |
| I07 | RCPT 451 | Scripted SMTP | Temporary error được retry policy xử lý | Bảo đảm retry sẽ thành công |
| I08 | DATA 554 | Scripted SMTP | Explicit rejection đúng phase | Toàn bộ content reputation |
| I09 | Mất final reply sau DATA | Scripted SMTP | `SUBMISSION_UNKNOWN` | Chắc chắn relay đã nhận/chưa nhận |
| I10 | Nhiều recipients có partial rejection | Scripted SMTP | Recipient outcomes không bị gộp | Delivery cuối của người accepted |
| I11 | DB fail sau SMTP 250 | Integration + failure injection | Không auto resend mù | Exactly-once delivery tuyệt đối |
| I12 | Worker restart và broker redelivery | Integration | Idempotent enqueue/claim | Không có unknown external effect |
| I13 | Webhook invalid signature | Provider consumer integration | Không cập nhật delivery state | Webhook real luôn đến |
| I14 | Webhook duplicate | Provider consumer integration | Dedup event | Provider gửi đúng một lần |
| I15 | Event đến ngược thứ tự | Provider consumer integration | State projection không hồi quy | Inbox placement |
| I16 | Hard bounce sau SMTP accepted | Provider consumer integration | Delivery status `BOUNCED` | Mọi bounce có cùng semantics |
| I17 | Deferred sau provider accepted | Provider consumer integration | Không submit bản mới | Thư sẽ chắc chắn được giao |
| P01 | Provider credentials thật | Authorized staging integration | Account được chấp nhận | Recipient Inbox |
| P02 | Sender domain/From policy | Authorized provider integration | Provider cho phép submission | DMARC/Inbox pass |
| P03 | Provider event callback | Authorized provider integration | Event đến và correlate | Không có event nào bị mất về sau |
| P04 | SPF/DKIM/DMARC trên test receiver | Controlled real mail | Authentication results quan sát được | Không bị spam |
| P05 | Message size/provider quota | Authorized provider test | Provider handling theo quota | Mọi future volume thành công |
| P06 | Provider outage/rate limit | Controlled failure/canary | Backoff/circuit breaker | User nhận đúng giờ |
| S01 | Gmail seed mailbox | Controlled seed | Một placement cụ thể | Tất cả Gmail recipients |
| S02 | Outlook seed mailbox | Controlled seed | Một placement cụ thể | Toàn bộ doanh nghiệp Outlook |
| S03 | Seed khác content/template | Controlled seed | Phát hiện xu hướng theo template | Quan hệ nhân quả chắc chắn |
| S04 | Seed không có message trong window | Controlled seed | `UNKNOWN/NOT_OBSERVED` | Message chắc chắn đã mất |
| O01 | Provider bounce/complaint tăng | Production monitoring | Có tín hiệu chất lượng giảm | Nguyên nhân cụ thể duy nhất |
| O02 | Provider accepted nhưng không thấy delivered | Production monitoring | Mốc tiếp theo thiếu quan sát | Chắc chắn thất bại |
| O03 | Open pixel được tải | Engagement telemetry | Pixel request được ghi nhận | Con người đã đọc |
| O04 | Email vào Inbox nhưng không được click | Seed/analytics | Inbox quan sát, click không có | Nội dung không được đọc |
| O05 | Domain/IP reputation thay đổi | Operational trend | Tương quan với kết quả | Unit test có lỗi |
| O06 | Suppression bị bypass khi failover | End-to-end workflow | Không được tạo send attempt ở B | Mọi domain không spam |

Một test case có thể kiểm tra nhiều điều, nhưng tên và báo cáo phải ghi **bằng chứng mạnh nhất đã quan sát được**. Chẳng hạn `I02` không được xuất hiện trên dashboard CI với nhãn `DELIVERED_SUCCESS`.

### Không khẳng định đã chạy các test trong tài liệu

Bảng trên là **kế hoạch kiểm thử và tiêu chí kỳ vọng**, không phải kết quả từ một hệ thống thực. Muốn báo “test passed” phải có test runner, môi trường và dữ liệu chạy tương ứng.

## 45. Tổ chức test suite để vừa nhanh vừa có ý nghĩa

Một cấu trúc tham khảo:

~~~text
src/test/java/.../mail/
  ReceiptMailServiceTest.java
  MarketingMailServiceTest.java
  MimeCompositionTest.java
  MailFailurePolicyTest.java
  SmtpLocalIntegrationTest.java
  SmtpScriptedFailureTest.java
  MailOutboxIntegrationTest.java
  ProviderWebhookContractTest.java

src/integrationTest/java/.../mail/
  ProviderStagingSmokeTest.java
  SeedMailboxObservationTest.java
~~~

Đây là cấu trúc ví dụ; `integrationTest` source set phải được cấu hình nếu dự án chưa có. Không mặc định Gradle/Maven nhận directory mới mà không cấu hình task và dependencies.

### Tầng chạy theo CI

**Mỗi pull request:**

- Unit Mockito.
- MIME composition.
- Local SMTP.
- Database/outbox integration.
- Scripted SMTP failure.
- Provider webhook consumer tests với fixture.

**Theo lịch có kiểm soát hoặc trước release:**

- Staging provider auth/config.
- DNS/SPF/DKIM/DMARC validations.
- Provider event API/webhook compatibility.
- Seed mailbox tests trong phạm vi được phép.

**Production:**

- Continuous delivery metrics và alert.
- Synthetic canary với account được phép và test data.
- Review complaint/bounce, suppression và reputation trends.

Không để pull request CI bắt buộc gửi email thật tới một recipient ngoài quyền kiểm soát mỗi lần chạy. Nếu provider test bắt buộc dùng credentials, đặt trong secret store và tách khỏi tests có thể chạy bởi untrusted contributions.

### Kiểm soát tính lặp lại

Một test Internet phụ thuộc DNS, provider uptime, spam filtering và network egress; test có thể flaky dù application logic không đổi. Vì vậy:

- Unit/local integration phải deterministic.
- Staging/provider tests cần timeout và trạng thái `INCONCLUSIVE` khi nguồn ngoài unavailable.
- Không đánh dấu phần mềm “email deliverability tốt” chỉ vì seed test ngẫu nhiên xanh.
- Không dùng mock để che một provider outage rồi gọi đó là deliverability success.

## 46. Một synthetic canary có kiểm soát

Một canary có thể chạy định kỳ để phát hiện sự cố mà unit tests không thấy:

~~~text
Canary generator
   |
   v
Create synthetic notification with unique correlation ID
   |
   v
Real application send pipeline -> approved SMTP provider
   |
   +--> provider accepted / deferred / bounce events
   |
   v
Seed mailbox reader with authorized access
   |
   v
Correlate observed folder + provider status
   |
   v
Emit scoped monitoring result
~~~

### Điều kiện an toàn

- Recipient là test mailbox được cấp quyền.
- Nội dung không chứa OTP thật, tài liệu khách hàng hoặc secret.
- Tần suất thấp và có rate budget riêng.
- Có thể dừng canary khi provider throttling.
- Correlation ID duy nhất và TTL dữ liệu test.
- Không dùng canary để tự gửi vào các địa chỉ bên ngoài không đồng ý.
- Có cơ chế xóa email test ở mailbox seed theo quyền/retention.

### Kết quả không nên chỉ là pass/fail

~~~json
{
  "testId": "canary-184",
  "applicationSubmission": "ACCEPTED",
  "providerDelivery": "DELIVERED",
  "seedPlacement": "SPAM",
  "observationWindow": "PT10M",
  "mailboxType": "CONTROLLED_SEED"
}
~~~

Đây là kết quả **giả định minh họa**. Nó cho thấy có thể provider báo delivered nhưng mailbox seed đặt ở Spam: hai quan sát không xung đột.

### Nếu không thấy thư

`NOT_OBSERVED_WITHIN_WINDOW` khác với `BOUNCED`. Trước khi kết luận, kiểm tra:

- Provider event vẫn đang queue/deferred?
- Seed reader có quyền đúng mailbox/folder không?
- Mail có nằm Junk/Promotions/Quarantine không?
- Correlation ID có bị strip/format sai không?
- Seed mailbox indexing có độ trễ không?
- Có mailbox rules tự động di chuyển thư không?

Chỉ khi xác định nguyên nhân mới phát cảnh báo đúng mức.

## 47. Chỉ số vận hành theo từng tầng

Một dashboard dễ hiểu nên có nhiều panels thay vì một con số “email success”:

| Nhóm | Metric gợi ý | Dùng để |
| --- | --- | --- |
| Application intent | `mail_notifications_created_total` | Số yêu cầu gửi |
| Business validation | `mail_notifications_suppressed_total` | Những yêu cầu bị chặn hợp lệ |
| Outbox | `mail_outbox_oldest_age_seconds` | Độ trễ chờ |
| Transport | `mail_smtp_attempts_total` | Physical attempts |
| Submission | `mail_submission_accepted_total` | Relay/provider accepted |
| Rejection | `mail_submission_rejected_total` | Lỗi tại SMTP/API |
| Unknown | `mail_submission_unknown_total` | Cần đối soát |
| Provider events | `mail_provider_delivery_events_total` | Delivered/deferred/bounced/complained |
| Event pipeline | `mail_provider_event_lag_seconds` | Webhook delay |
| Data quality | `mail_hard_bounces_total` | Invalid recipients và reputation |
| Suppression | `mail_suppression_actions_total` | Opt-out/complaint handling |
| Seed placement | `mail_seed_placements_total` | Inbox/Spam/Other/Unknown theo seed |
| SMTP latency | `mail_smtp_submission_duration_seconds` | Chậm ở transport |
| API scheduling | `mail_dispatch_lateness_seconds` | Trễ so với lịch người dùng |
| Rate limiter | `mail_rate_limiter_denied_total` | Deferred trước SMTP |

Đây là **tên metric minh họa để ứng dụng tự triển khai**, không phải tập metric có sẵn của Spring Mail.

### Những chiều có ích

- `provider` hoặc route.
- `category`: OTP, transactional, marketing.
- `recipientDomainGroup` hoặc receiving provider theo nhóm hữu hạn nếu được phép.
- `failureKind`: auth, TLS, network, temp recipient, permanent recipient.
- `status`: accepted, deferred, bounced, unknown.
- `templateVersion` nếu cardinality được kiểm soát.

**Không dùng full recipient email, notification UUID, raw Message-ID, subject hoặc token làm metric label.** Đó là dữ liệu nhạy cảm và có thể gây cardinality rất lớn.

### Cảnh báo có ý nghĩa

| Dấu hiệu | Cách diễn giải ban đầu |
| --- | --- |
| `mail_submission_accepted_total` giảm mạnh | Lỗi transport/provider/route có thể xảy ra |
| SMTP 535 tăng | Credential/account/TLS auth cần điều tra |
| SMTP 550 tăng | Recipient list hoặc sender policy cần phân loại |
| `mail_provider_event_lag_seconds` tăng | Webhook pipeline bị chậm |
| Provider delivered giảm nhưng SMTP accepted ổn | Downstream delivery/provider issue có thể xảy ra |
| Seed Spam tăng | Có thể có placement/reputation/content issue |
| Complaint tăng | Cần xem consent, nội dung và tần suất |
| Unknown outcomes tăng | Socket/timeout/transaction issues, nguy cơ duplicate |
| Bounce/complaint A rồi sender B vẫn gửi | Shared suppression hoặc failover policy có thể lỗi |

Không kết luận nguyên nhân chỉ từ một metric. Cần correlation giữa message attempts, provider events, categories và receiving domains.

## 48. Logs cần nêu rõ bằng chứng, không phải cảm giác

Ví dụ log không tốt:

~~~text
INFO Email delivered successfully to buyer@example.org
~~~

nếu nó được ghi ngay sau `JavaMailSender.send()\).

Log đúng phạm vi hơn:

~~~json
{
  "event": "mail_submission_accepted",
  "notificationId": "notif-184",
  "providerKey": "smtp-primary",
  "evidence": "SMTP_FINAL_SUCCESS",
  "submitStatus": "SUBMITTED",
  "submittedAt": "2026-11-12T10:00:05Z"
}
~~~

Khi nhận webhook đã xác minh:

~~~json
{
  "event": "mail_provider_delivery_status",
  "notificationId": "notif-184",
  "providerKey": "smtp-primary",
  "evidence": "VERIFIED_PROVIDER_EVENT",
  "deliveryStatus": "DELIVERED",
  "observedAt": "2026-11-12T10:05:10Z"
}
~~~

Không log raw body, full recipient, OTP, reset URL, SMTP AUTH transcript hay toàn bộ webhook chứa PII. Dữ liệu correlation vẫn cần ACL và retention phù hợp.

### Quan trọng khi dùng `@Async`

Một phương thức gửi email chạy bất đồng bộ có thể trả future hoặc hoàn tất sau khi HTTP request đã trả response. Nếu controller log `Email delivered` ngay khi queue `@Async` task, thời điểm và ý nghĩa càng sai. Hãy log:

- Yêu cầu được tiếp nhận/queued khi ghi outbox.
- Attempt bắt đầu khi worker gọi transport.
- SMTP accepted khi thực sự nhận success.
- Provider delivery khi event đáng tin đến.

Không dùng `@Async` như cơ chế tự bảo đảm durable delivery; nếu JVM chết trước khi task chạy, in-memory work có thể mất. Outbox/queue bền vững mới giải quyết mục tiêu lưu yêu cầu khi cần.

## 49. Runbook: unit test xanh nhưng email production không tới

Một báo cáo thường gặp:

> “CI xác nhận gửi email thành công, nhưng khách hàng không thấy thư.”

Không nên bắt đầu bằng việc chạy lại Mockito test nhiều lần. Hãy truy vết **từ application intent đến điểm quan sát cuối cùng**, dừng ở nơi dữ liệu không còn hoặc xuất hiện lỗi.

### Bước 1 — Xác minh yêu cầu gửi thực sự được tạo

- Có business event đúng không?
- Outbox row có được commit?
- Có bị validation, permission hoặc suppression chặn?
- Recipient có thuộc tenant và category cho phép?
- Có phải email đã bị `CANCELLED`, `EXPIRED` hoặc chưa đến `scheduledAt`?

Nếu chưa có notification/outbox record, đây là lỗi business/orchestration, không phải deliverability của SMTP.

### Bước 2 — Xác minh worker đã attempt transport

- Job có status `PENDING`, `RETRY_PENDING`, `PROCESSING` hay `SUBMITTED`?
- Worker có chạy không? Có hàng đợi bị nghẽn không?
- Rate limiter có trì hoãn job?
- Có log/attempt ID nói rõ bắt đầu SMTP?
- Có secret/auth hoặc DNS/TLS error?

Nếu worker chưa gọi SMTP, mock test không giúp chứng minh tại sao môi trường production chưa dispatch.

### Bước 3 — Xem SMTP submission outcome

- Có final SMTP 250 sau DATA hoặc success từ provider API không?
- Có `421`, `451`, `535`, `550`, `554` hoặc timeout?
- Lỗi xảy ra ở connection, AUTH, MAIL FROM, RCPT TO hay DATA?
- Nếu mất phản hồi sau DATA, có `SUBMISSION_UNKNOWN` không?
- Attempt đã được ghi với provider key và correlation ID chưa?

Nếu relay từ chối rõ ràng, đây là submission failure; **không báo delivered**. Nếu outcome unknown, không resend bừa vì có thể đã gửi trùng.

### Bước 4 — Kiểm tra provider queue/events

- Provider có nhận message ID không?
- Message đang queued, deferred, delivered, dropped, bounced hay complained?
- Có webhook event nào chưa xử lý?
- Provider event lag có cao không?
- Correlation có trùng recipient/provider account không?
- Provider có suppression/complaint policy riêng không?

Nếu provider báo delivered theo hợp đồng nhưng người nhận không thấy Inbox, chuyển sang kiểm tra mailbox filtering/placement; đừng kết luận provider chắc chắn sai hoặc ứng dụng chắc chắn đúng.

### Bước 5 — Quan sát mailbox/recipient được phép

- Nhờ recipient kiểm tra Spam/Junk, Promotions, Other, Quarantine nếu phù hợp.
- Kiểm tra mail rules, forwarding, aliases, corporate gateway.
- Gửi controlled seed test qua cùng route/domain nếu được phép.
- Xem trusted authentication results từ mail nhận.
- So sánh sender address/domain, subject, content version và attachment.
- Không truy cập mailbox cá nhân của người dùng khi chưa được ủy quyền.

### Bước 6 — Kết luận bằng trạng thái có bằng chứng

Ví dụ:

~~~text
Notification created: YES
SMTP attempt started: YES
Provider accepted: YES
Provider delivery event: DEFERRED
Seed Inbox observation: NOT AVAILABLE

Conclusion:
  "Provider has accepted and deferred this recipient;
   final delivery and Inbox placement not yet observed."
~~~

Đây là kết luận có trách nhiệm hơn “mock test xanh, mail đã vào Inbox”.

## 50. Runbook: SMTP accepted nhưng tỷ lệ bounce tăng

Nếu một hệ thống nhiều message được provider accepted, sau đó hard bounce tăng:

1. Xác định receiving domain và category bị ảnh hưởng.
2. Kiểm tra event source/signature, dedup và correlation theo recipient.
3. Phân loại hard/soft bounce bằng provider-specific evidence, không đoán từ một chuỗi exception.
4. Kiểm tra domain list hygiene, những địa chỉ chưa xác minh hoặc import mới.
5. Cập nhật suppression cho invalid recipients theo policy.
6. Không retry cùng mailbox đã bị hard bounce đáng tin bằng provider khác.
7. Kiểm tra có chiến dịch gửi tới address không còn permission/consent không.
8. Xem có sender account/identity policy error chung bị nhận nhầm làm invalid recipient không.
9. Đo riêng accepted, bounced, deferred, unknown trong cùng cohort/time window.
10. Khi sửa, chạy canary có kiểm soát, không mass-resend mọi mail đã accepted.

### Một sai lầm cần tránh

Nếu hard bounce tăng, tăng `maxRetries` từ 3 lên 100 sẽ không sửa mailbox không tồn tại; nó có thể làm xấu reputation và gây gửi dư.

### Chú ý provider event types

Một `bounce` từ provider có thể phản ánh nhiều nguyên nhân (recipient, policy, domain, mailbox full...). Không áp dụng suppression vĩnh viễn cho mọi temporary bounce. Adapter phải giữ normalized reason và chứng cứ cần thiết.

## 51. Runbook: provider báo delivered nhưng seed mail nằm Spam

Đây là trường hợp đặc biệt cho thấy **delivery và Inbox placement khác nhau**.

### Triệu chứng

~~~text
SMTP submission: ACCEPTED
Provider event: DELIVERED
Seed mailbox folder: SPAM
Unit Mockito: PASSED
~~~

Không có mâu thuẫn: test mock kiểm tra code; SMTP accepted kiểm tra relay; provider delivered là kết quả provider; seed folder phản ánh placement ở mailbox đó.

### Các bước điều tra

1. Xác minh đây là đúng message, sender domain, template version và seed address.
2. Kiểm tra SPF/DKIM/DMARC và alignment ở trusted receiving headers.
3. Xem domain/IP reputation và provider account health nếu có telemetry.
4. Kiểm tra content, links, attachments, unsubscribe và sender identity.
5. So sánh với các seed mailboxes khác để xác định phạm vi.
6. Xem mail server/recipient rules nếu được quyền kiểm tra.
7. Đánh giá bounce/complaint trend ở cohort tương ứng.
8. Không thử lách filter bằng cách gửi thêm bản giống hệt tới cùng người dùng.
9. Chỉ điều chỉnh nội dung/cấu hình có lý do, rồi chạy experiment có kiểm soát.
10. Báo cáo “Spam observed on specific seed” thay vì tuyên bố toàn bộ recipients đều bị Spam.

### Những gì Mockito vẫn hữu ích

Nếu nghi template bị render sai hoặc xuất hiện một URL không mong muốn, Mockito/MIME unit test có thể giúp chứng minh application chọn đúng template/version. Nhưng để xác định tại sao receiving filter phân loại Spam, cần những dữ liệu ngoài mock.

## 52. Runbook: CI “mail integration” xanh nhưng SMTP production AUTH 535

Một nguyên nhân có thể là test dùng:

~~~java
@MockitoBean
JavaMailSender sender;
~~~

hoặc profile `test` dùng local SMTP. Unit/integration tests đó không exercise credentials thật của production.

### Các bước

1. Kiểm tra loại test: mock, fake SMTP, provider sandbox hay real SMTP account.
2. Xem production bean/qualifier đang dùng cấu hình nào.
3. Xác minh host, port, TLS mode và AUTH mechanism.
4. Kiểm tra secret rotation, account status, provider policy/permissions.
5. Phân biệt account-level AUTH 535 với recipient-level failure.
6. Dừng retry storm; không spam login liên tục bằng credential sai.
7. Thử một smoke submission trên staging/canary account được phê duyệt.
8. Bảo vệ account và template categories trước khi rollout lại.
9. Thêm config-contract test và alert phù hợp.
10. Không thay mock test thành kết nối production SMTP có thể gửi mail ngoài ý muốn trong mọi PR.

### Không khắc phục bằng tắt TLS

Nếu AUTH bị lỗi vì cấu hình TLS hoặc provider policy, không bỏ STARTTLS/certificate verification để test xanh. Sửa cấu hình và quyền thực sự.

## 53. Runbook: nhận final SMTP 250 rồi người nhận vẫn không có thư

Sau final 250:

1. Lưu provider/relay message ID và timestamp nếu có.
2. Kiểm tra provider activity log.
3. Xem deferred, delivered, bounced, dropped events.
4. Xác minh notification/recipient mapping, đặc biệt Bcc hoặc nhiều RCPT TO.
5. Nếu provider chưa có final event, giữ outcome tương ứng, không tự đánh dấu Inbox.
6. Nếu provider báo delivered, kiểm tra recipient filtering/Quarantine/Junk/Other theo quyền.
7. Nếu không có provider event, kiểm tra webhook health và event lag trước khi suy luận.
8. Không resend tự động vì có thể tạo duplicate.
9. Với email nhạy cảm/OTP, áp dụng expiry và kênh hỗ trợ thay thế theo policy.
10. Tài liệu hóa điểm quan sát cuối và phần chưa biết.

### Không coi Message-ID là exactly-once guarantee

Message-ID header hữu ích cho correlation, nhưng SMTP/receiving mailboxes không bắt buộc loại bỏ mọi duplicate có cùng Message-ID. Không tạo một resend mới dựa trên giả định “mailbox sẽ tự loại trùng”.

## 54. Những sai lầm thường gặp trong code và báo cáo

### 54.1. Đặt tên unit test `emailDeliveredSuccessfully`

Trong khi assert duy nhất là `verify(sender).send(...)`. Sửa tên thành đúng bằng chứng: `invokesMailSenderWithExpectedMessage`.

### 54.2. `@SpringBootTest` + mock transport rồi tự gọi E2E

Context thực không đồng nghĩa transport thực. Ghi rõ wiring integration có mock.

### 54.3. Dùng `assertDoesNotThrow(sender.send(...))` với sender mock

Void mock mặc định không ném lỗi; test không kiểm tra SMTP.

### 54.4. Stub `send()` thành công rồi xem là provider accepted

Một Mockito stub là dữ liệu giả. Chỉ provider/fake SMTP thật mới cung cấp bằng chứng ở tầng tương ứng.

### 54.5. Mock luôn `MimeMessage` khi muốn test MIME structure

Method calls không đủ để chứng minh multipart/charset/attachment được serialize đúng. Dùng Jakarta Mail `MimeMessage` thật trong MIME test.

### 54.6. Kiểm tra chỉ Subject và To

Bỏ qua From, Reply-To, plain-text alternative, MIME encoding, Bcc và attachment nếu nghiệp vụ cần. Đặt phạm vi rõ chứ không tuyên bố toàn bộ email được kiểm tra.

### 54.7. Coi localhost GreenMail là Internet delivery

GreenMail chứng minh local server nhận SMTP; nó không đánh giá real DNS, reputation hay recipient filtering.

### 54.8. Test SMTP nhưng tắt mọi TLS/auth rồi tuyên bố config production đúng

Cần test TLS/auth riêng với cấu hình tương ứng. Local plain SMTP chỉ kiểm tra logic transport cơ bản.

### 54.9. Coi SMTP final 250 là Inbox

Relay accepted không bảo đảm remote mailbox placement.

### 54.10. Coi provider `delivered` là người nhận đã đọc

Thường không đúng; provider không quan sát người dùng đọc nội dung.

### 54.11. Coi open pixel là “đã đọc”

Ảnh có thể bị tự động tải hoặc bị chặn. Dùng ngôn ngữ và mục tiêu đo phù hợp.

### 54.12. Không xem Bcc envelope

Vắng Bcc header không chứng minh SMTP đã/không gửi hidden recipient. Quan sát envelope riêng.

### 54.13. Gộp kết quả nhiều recipients thành một `sent=true`

Không phân biệt accepted/rejected/bounced từng người, dẫn đến retry trùng.

### 54.14. Không lưu provider message ID

Khó reconcile accepted, delivered, bounced và event đến muộn.

### 54.15. Tin mọi webhook không cần xác minh

Event giả mạo có thể làm ứng dụng ghi `DELIVERED` sai hoặc suppress sai recipient.

### 54.16. Đếm webhook redeliver thành nhiều deliveries

Cần dedup event ID và correlation per recipient.

### 54.17. Retry khi chưa thấy `delivered`

Provider có thể đã accepted và đang retry downstream; gửi thêm có nguy cơ duplicate.

### 54.18. Không có `SUBMISSION_UNKNOWN`

Mất final reply sau DATA có thể tạo một tình huống không thể xác minh ngay. Coi mọi exception là chắc chắn chưa gửi là sai.

### 54.19. Chỉ test một mailbox seed rồi kết luận 100% deliverability

Kết quả không đại diện mọi receiving domains và user conditions.

### 54.20. Không xác định mẫu số của tỷ lệ giao mail

Event count, recipient submission, attempt và notification là các đơn vị khác nhau. Không trộn trong một tỷ lệ.

### 54.21. Coi SPF pass là DMARC pass

SPF identity phải phù hợp alignment với From theo DMARC. DKIM cũng phải xét domain alignment.

### 54.22. Coi DMARC pass là chắc chắn không vào Spam

Authentication không đồng nghĩa reputation/placement. Theo dõi nhiều nguồn.

### 54.23. Gửi thử vào production recipients không có quyền

Kiểm thử không nên làm phiền người dùng hoặc vi phạm consent. Dùng seed account/authorized canary.

### 54.24. Giữ raw body/recipient trong metrics và logs

Rò PII/token và tăng cardinality. Dùng sanitized metadata, ACL và retention.

### 54.25. Báo “đã gửi thành công” ngay khi enqueue async task

Enqueue, dispatch, submit và delivery là các bước khác nhau. UI/log phải đặt tên trạng thái đúng.

### 54.26. Tăng retry để sửa bounce hoặc Spam

Retry không sửa mailbox invalid, DMARC/reputation hoặc consent. Có thể tạo duplicate và khiếu nại.

### 54.27. Bỏ qua suppression khi chuyển provider

Complaint/hard bounce từ provider A phải được xử lý theo policy dùng chung; không gửi qua B để né từ chối.

### 54.28. Kết luận lỗi nằm ở Spring Mail khi recipient filter đổi

Nếu SMTP/relay đã accepted, cần điều tra downstream reputation/filtering thay vì tự sửa MIME builder một cách vô căn cứ.

### 54.29. Không kiểm thử việc tích hợp sau đổi provider

Unit mocks vẫn xanh dù credentials, DKIM, From identity và provider event schema đổi. Cần smoke test/monitoring ở đúng tầng.

### 54.30. Không báo trạng thái UNKNOWN

Khi evidence thiếu, UI tự gán DELIVERED/FAILED có thể dẫn tới resend sai và điều tra sai. UNKNOWN là một trạng thái hữu ích và trung thực.

## 55. Checklist để review một PR có mock JavaMailSender

### Unit tests

- [ ] Test nêu rõ hành vi ứng dụng cần xác minh, không dùng tên “delivered” khi chỉ mock.
- [ ] `verify(sender.send(...))` xác minh đúng overload và số lần gọi.
- [ ] Có `ArgumentCaptor` hoặc matcher kiểm tra recipient/from/subject/body cần thiết.
- [ ] Các nhánh suppression/validation không gọi sender.
- [ ] Có test mô phỏng exception và chính sách retry/stop.
- [ ] Không cần kết nối Internet trong unit test.
- [ ] Nếu tạo MIME, dùng `MimeMessage` thật để kiểm tra structure/encoding.
- [ ] Không dùng mock MIME hoàn toàn khi mục tiêu là kiểm tra serialized parts.

### Integration tests

- [ ] Có test `JavaMailSenderImpl` kết nối SMTP server giả ở môi trường cô lập.
- [ ] Kiểm tra plain text/HTML, Unicode và attachment theo yêu cầu.
- [ ] Kiểm tra Bcc envelope riêng với header khi cần.
- [ ] Có scripted SMTP tests cho permanent/temporary/auth/unknown outcomes.
- [ ] Không coi local SMTP `250` là delivered tới mailbox thật.
- [ ] Có integration test outbox/DB và xử lý sau crash nếu hệ thống dùng async.
- [ ] Có test provider webhook signature, dedup, correlation và out-of-order events.
- [ ] Không để một Mockito bean ẩn trong test được gọi là “real SMTP E2E”.

### Provider và domain

- [ ] Provider account/sender identity được xác minh trong staging phù hợp.
- [ ] TLS/STARTTLS, DNS và network egress được kiểm tra đúng môi trường.
- [ ] Có kiểm tra SPF/DKIM/DMARC và alignment ở nguồn có thẩm quyền.
- [ ] Hiểu provider `accepted`, `delivered`, `deferred`, `bounced`.
- [ ] Có correlation giữa notification/attempt/recipient/provider event.
- [ ] Có test seed inbox được cấp phép nếu mục tiêu gồm Inbox placement.
- [ ] Có phương pháp nhận diện kết quả không xác định.

### Production và quyền riêng tư

- [ ] Dashboard tách `SUBMITTED`, `DELIVERED`, `BOUNCED`, `UNKNOWN`.
- [ ] Mỗi metric có mẫu số/observation window được định nghĩa.
- [ ] Không dùng mock success làm số liệu deliverability.
- [ ] Monitoring có bounce/complaint/suppression/provider event lag.
- [ ] Không tự resend khi provider accepted hoặc outcome unknown.
- [ ] Không lưu OTP, raw body, full email address trong logs/metric labels.
- [ ] Canary gửi tới mailbox được phép, không gửi tới người lạ.
- [ ] Có runbook khi unit test xanh nhưng production mail không đến.

Checklist hỗ trợ review và thiết kế. Một mục được tick trong tài liệu không chứng minh test đã được thực thi; cần test run và evidence thực ở mỗi môi trường.

## 56. Decision tree: muốn chứng minh điều gì?

~~~mermaid
flowchart TD
    A{"Câu hỏi kiểm thử là gì?"}
    A -- "Service có gọi sender đúng?" --> B["Mockito + ArgumentCaptor"]
    A -- "MIME có đúng cấu trúc?" --> C["Jakarta Mail MIME test"]
    A -- "SMTP client có truyền dữ liệu?" --> D["Local/scripted SMTP server"]
    A -- "Provider có nhận submission?" --> E["Authorized provider integration"]
    A -- "Remote recipient có được giao?" --> F["Trusted provider/DSN evidence"]
    A -- "Thư có vào Inbox?" --> G["Authorized seed mailbox observation"]
    A -- "Người dùng đã đọc?" --> H["Explicit product interaction if available"]
~~~

Từng nhánh trả lời một câu hỏi khác nhau. Không nhất thiết triển khai mọi nhánh cho mọi feature; điều quan trọng là **không gọi bằng chứng từ nhánh B là câu trả lời của G hoặc H**.

### Nguyên tắc đặt acceptance criteria

Ví dụ câu chuyện người dùng “Khi đơn hàng thanh toán thành công, hệ thống phải gửi biên nhận qua email” có thể tách thành:

1. Tạo notification đúng recipient sau business transaction commit.
2. Worker gửi MIME đúng nội dung qua SMTP relay đã cấu hình.
3. Nhận submission outcome và ghi trạng thái đúng.
4. Theo dõi provider bounce/delivery khi có.
5. Không gửi trùng một notification do retry/restart.
6. Có cảnh báo nếu tỉ lệ lỗi tăng.

Nếu yêu cầu nghiệp vụ là “cải thiện khả năng email vào Inbox”, cần thêm **measurement plan** với seed mailboxes, reputation/provider signals và thời gian quan sát; không thể đóng ticket chỉ vì unit test pass.

## 57. Ví dụ xuyên suốt: test xanh nhưng recipient không nhận receipt

Giả sử team có test:

~~~text
Test: ReceiptMailServiceTest
Status: PASSED
Assertion: verify(sender).send(expectedMessage)
~~~

Triển khai production, một số khách hàng báo không nhận email.

### Giai đoạn A: ứng dụng

Kiểm tra outbox:

~~~text
notificationId: receipt-184
status: PROCESSING
lastAttemptAt: 2026-11-12T10:00:03Z
provider: smtp-primary
~~~

Đây là một record ví dụ. `PROCESSING` chưa cho biết SMTP outcome.

### Giai đoạn B: SMTP

Log đã chuẩn hóa:

~~~text
smtpPhase=RCPT_TO
smtpCode=550
enhancedCode=5.1.1
failureKind=INVALID_RECIPIENT
~~~

Khi có bằng chứng đáng tin `550 5.1.1` tại recipient phase, ứng dụng nên dừng retry địa chỉ này theo policy và hỗ trợ xác minh/sửa địa chỉ. **Mock test vẫn đúng về mặt “service gọi sender”**, nhưng không kiểm tra được mailbox thực tế.

### Giai đoạn C: nếu SMTP relay accepted

Một recipient khác:

~~~text
notificationId: receipt-185
SMTP final reply: 250 accepted
provider status: deferred
last provider event: 10:02Z
~~~

Lúc này không còn là lỗi “service chưa gọi send”. Cần theo dõi provider/remote domain và chính sách retry downstream. Không gửi thêm ngay vì thư đã được accepted.

### Giai đoạn D: nếu provider delivered nhưng người dùng không thấy

~~~text
notificationId: receipt-186
SMTP: 250 accepted
provider: delivered
recipient feedback: "Not in Inbox"
seed mailbox observation: spam in an authorized test
~~~

Đây là vấn đề placement/recipient filtering cần điều tra. Không thể sửa bằng Mockito `when(sender.send(...))` vì đây là void method đã được mock trước đó và transport không được exercise trong unit test.

### Kết luận của ví dụ

Một bộ test xanh không vô nghĩa; nó đã chứng minh phần tạo lời gọi sender đúng. Sai lầm là **dùng kết quả đúng nhưng hẹp đó để tuyên bố một kết quả rộng hơn chưa được đo**.

## 58. Ví dụ xuyên suốt: test xanh nhưng UI báo sai trạng thái

Giả sử worker:

~~~java
try {
    javaMailSender.send(message);
    repository.markDelivered(notificationId);
} catch (MailException error) {
    repository.markFailed(notificationId);
}
~~~

Với sender mock:

1. `send()` không ném lỗi.
2. `markDelivered()` được gọi.
3. Test assert state `DELIVERED`.
4. Developer kết luận “delivery pipeline hoạt động”.

Thực ra test chỉ kiểm tra code gọi `markDelivered`, trong khi **tên method và trạng thái domain đã sai semantics ngay từ thiết kế**.

Một cải tiến:

~~~text
SMTP success -> SUBMITTED
Provider authenticated delivered event -> DELIVERED
Verified seed mailbox observation -> INBOX/OTHER/UNKNOWN
Real product action -> separate engagement/confirmation
~~~

Không bắt buộc một hệ thống transactional email phải biết Inbox placement mọi recipient. Việc có trạng thái UNKNOWN là bình thường khi nguồn ngoài không cung cấp dữ liệu.

## 59. Câu hỏi tự kiểm tra

**1. `verify(javaMailSender).send(...)` có chứng minh email đã tới mailbox không?**

Không. Nó chỉ chứng minh một lời gọi tới mock/spy với các argument đã kiểm tra trong test.

**2. `JavaMailSender` mock mặc định có mở TCP socket không?**

Không. Mockito void method không thực hiện SMTP transport nếu không được cấu hình một behavior đặc biệt.

**3. Nếu `assertDoesNotThrow` pass trên mock sender, có phải SMTP hoạt động không?**

Không. Mock mặc định không throw nên chỉ chứng minh không có exception đã được mô phỏng.

**4. `@SpringBootTest` có đủ làm bài test thành SMTP integration không?**

Không. Nếu sender bean bị thay bằng mock, test chỉ exercise Spring context và orchestration quanh mock.

**5. Khi nào dùng ArgumentCaptor?**

Khi cần xác minh message thực sự được service truyền tới sender: recipient, subject, body, category hoặc các thuộc tính phù hợp.

**6. Vì sao cần MIME thật trong test HTML/attachment?**

Để kiểm tra multipart, header, charset và cấu trúc sau serialization, thay vì chỉ verify các method calls của builder.

**7. Local GreenMail test có chứng minh production provider chấp nhận không?**

Không. Nó kiểm tra SMTP submission tới fake/local relay theo cấu hình test.

**8. Một test server trả 250 sau DATA chứng minh gì?**

Nó chứng minh relay **đó** đã accepted submission trong test, không phải remote Internet mailboxes.

**9. SMTP 250 sau DATA có nghĩa thư vào Inbox chưa?**

Chưa. Relay có thể queue, retry hoặc bounce downstream; receiving mailboxes còn lọc Spam/Junk.

**10. Provider báo delivered có nghĩa người nhận đã đọc không?**

Không. Delivered theo provider thường nói về giao thư/acceptance ở đích, không phải hành vi người nhận.

**11. Có nên dùng open pixel làm bằng chứng đọc thư không?**

Không như bằng chứng chắc chắn. Email clients, proxies và scanners có thể tự tải hoặc chặn ảnh.

**12. Một seed mailbox vào Inbox có đủ báo tỷ lệ Inbox 100% không?**

Không. Đó chỉ là quan sát trên một mailbox, một nội dung và một thời điểm.

**13. SPF pass có đồng nghĩa DMARC pass không?**

Không tự động. DMARC yêu cầu authentication có alignment với header From theo quy tắc SPF/DKIM thích hợp.

**14. DKIM pass có đồng nghĩa Inbox placement không?**

Không. Domain authentication và spam classification là hai vấn đề khác nhau.

**15. Có thể dùng Message-ID để chống mọi duplicate end-to-end không?**

Không. Header đó giúp correlation nhưng không bảo đảm mọi recipient server loại bỏ thư trùng.

**16. Vì sao cần status `SUBMISSION_UNKNOWN`?**

Vì mất final SMTP response sau DATA có thể khiến ứng dụng không biết relay đã accepted hay chưa, và retry mù có nguy cơ gửi trùng.

**17. Có nên resend sau khi provider accepted nhưng chưa có delivered event?**

Không tự động. Provider có thể đang queue/retry và event có thể trễ.

**18. Nếu provider delivered event đến hai lần, có phải hai email đã giao không?**

Không. Có thể là webhook redelivery; cần dedup event theo provider event identity và correlation.

**19. Vì sao cần lưu kết quả theo recipient?**

Vì nhiều recipient của cùng một message có thể có outcomes khác nhau; gộp một `sent=true` gây retry sai.

**20. Muốn đo inbox placement, phải dùng nguồn nào?**

Một nguồn quan sát mailbox được phép, như seed accounts hoặc hệ thống đo có định nghĩa placement rõ, kèm sample/window và giới hạn đại diện.

**21. Không thấy bounce sau vài phút có chứng minh delivered không?**

Không. Provider có thể vẫn retry, event bị trễ hoặc mailbox đã nhận nhưng lọc.

**22. Tại sao cần xác minh webhook signature?**

Để không cho một HTTP event giả mạo làm ứng dụng ghi trạng thái delivered/bounced sai.

**23. Nếu user không nhận OTP, nên tăng retry vô hạn không?**

Không. Cần kiểm tra expiry, transport/provider errors, recipient status, rate limits và trải nghiệm người dùng; retry phải có budget và không tạo mã cũ vô nghĩa.

**24. Email vào Spam ở seed có kết luận mọi recipients bị Spam không?**

Không. Kết quả có phạm vi theo seed, content và thời điểm. Có thể dùng để điều tra xu hướng.

**25. Vì sao đo deliverability cần mẫu số rõ?**

Vì attempts, notifications, recipients và provider events là đơn vị khác nhau; thiếu định nghĩa có thể làm tỷ lệ sai.

**26. Có nên dùng raw recipient email làm metric label không?**

Không. Có rủi ro riêng tư và cardinality lớn; dùng nhóm provider/category/domain được phép.

**27. Nếu hệ thống dùng `@Async`, controller trả 200 có nghĩa email đã gửi không?**

Không. HTTP response có thể chỉ xác nhận đã lên lịch một tác vụ trong memory. Cần durable outbox để giữ yêu cầu và transport evidence riêng.

**28. Khi đổi SMTP provider, unit mock xanh có đủ không?**

Không. Cần kiểm tra credentials, TLS, verified sender, DNS authentication, quota, provider events và seed observations phù hợp.

**29. Kết quả test giả lập provider `delivered` có bằng chứng giao thư thật không?**

Không. Nó chỉ chứng minh consumer xử lý một event fixture đúng.

**30. Câu nào mô tả chính xác nhất một unit test mock thành công?**

“Ứng dụng gọi `JavaMailSender.send(...)` với dữ liệu kỳ vọng trong tình huống kiểm thử.” Muốn nói “relay accepted”, “provider delivered” hoặc “Inbox” phải có thêm bằng chứng ở đúng tầng.

## Kết luận

**Dùng mock `JavaMailSender` rồi kết luận deliverability là lỗi suy luận về phạm vi kiểm thử, không phải lỗi của Mockito.** Mock là công cụ rất tốt để xác minh business branching, recipient, subject, template, suppression và error-handling decisions. Nhưng một lời gọi `verify(send)` không mở SMTP connection, không kiểm tra DNS/TLS/AUTH, không gửi RCPT TO/DATA và không quan sát provider, receiving server hay mailbox. Ngay cả khi `JavaMailSenderImpl` thực nhận final SMTP 250, đó vẫn chỉ là **submission accepted**, không phải thư đã xuất hiện trong Inbox hoặc đã được đọc.

Thiết kế production đáng tin cần **nhiều tầng bằng chứng**: unit tests với Mockito; MIME composition tests với Jakarta Mail thật; local/scripted SMTP integration; provider staging/real-account verification khi được phép; webhook delivery/bounce có xác thực, dedup và correlation; controlled seed mailbox observations khi mục tiêu bao gồm Inbox placement; và monitoring dài hạn về bounces, complaints, authentication, reputation và queue lag.

Cuối cùng, dùng trạng thái `SUBMITTED`, `DELIVERED`, `BOUNCED`, `SUBMISSION_UNKNOWN` và `INBOX` đúng **nguồn dữ liệu có thẩm quyền**, không đánh đồng những mốc này trong API hoặc dashboard. Đặt tên test theo điều nó thật sự chứng minh, định nghĩa mẫu số và observation window cho mọi tỷ lệ, và tránh retry/resend mù chỉ vì thiếu bằng chứng delivered. **Test xanh là tín hiệu tốt về phần mã đã được kiểm tra; deliverability thật chỉ có thể được đánh giá bằng quan sát phù hợp trên toàn hành trình email.**
