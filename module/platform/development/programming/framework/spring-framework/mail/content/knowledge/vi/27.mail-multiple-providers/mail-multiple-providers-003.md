# Chọn provider dự phòng khi provider chính lỗi

Trong một ứng dụng dùng **Spring Framework Mail**, hệ thống thường gửi email qua một SMTP server hoặc dịch vụ email (Email Service Provider, viết tắt **ESP**) duy nhất. Khi provider này gặp sự cố kết nối, bị giới hạn lưu lượng, thay đổi chính sách hoặc tạm ngừng tiếp nhận thư, các thông báo quan trọng như xác nhận đơn hàng, đặt lại mật khẩu và biên nhận có thể bị trì hoãn. Một kiến trúc **nhiều nhà cung cấp** cho phép chọn provider dự phòng nhằm giảm phụ thuộc vào một điểm lỗi.

Tuy nhiên, **chọn provider dự phòng không đồng nghĩa với “cứ gọi provider A lỗi thì gửi ngay qua provider B”**. Lỗi có thể xuất hiện **sau khi provider A đã chấp nhận email**, nhưng ứng dụng không nhận được phản hồi cuối vì timeout hoặc mất kết nối. Nếu gửi lại qua B, người nhận có thể nhận **hai bản**. Bởi vậy, failover phải dựa trên loại lỗi, bằng chứng về trạng thái submission, khả năng chấp nhận thư của provider còn lại và chính sách chấp nhận rủi ro gửi trùng.

Bài học này giải thích cách thiết kế lựa chọn provider chính/dự phòng trong Spring Framework Mail, phân biệt **SMTP** và **HTTP mail API**, xây chính sách failover an toàn, kết hợp transactional outbox, health checks, circuit breaker, rate limit, suppression, quan sát vận hành và kiểm thử tình huống provider lỗi.

> **Nguyên tắc cốt lõi:** Chỉ chuyển sang provider dự phòng tự động khi có cơ sở cho rằng **chưa có một email nào được provider trước chấp nhận**, hoặc có cơ chế idempotency được provider hỗ trợ với bảo đảm phù hợp. Nếu kết quả là **UNKNOWN**, cần đối soát hoặc xử lý theo chính sách rủi ro thay vì failover mù.

## 1. Multi-provider giải quyết vấn đề gì?

Một luồng email chỉ có một provider:

~~~text
Ứng dụng Spring
      |
      v
JavaMailSender
      |
      v
SMTP Provider A
      |
      v
Hệ thống nhận thư
~~~

Nếu A không sẵn sàng, việc tạo notification trong database vẫn có thể thành công, nhưng **SMTP submission** bị chặn. Khi có provider dự phòng:

~~~text
                       +--> Provider A (primary) --+
Ứng dụng -> MailRouter -|                          +--> Recipient
                       +--> Provider B (backup) --+
~~~

Kiến trúc này có thể:

- Giảm thời gian không thể gửi thư khi provider chính ngừng tiếp nhận.
- Tách khả năng phục hồi theo loại thông báo: security/transactional có thể cần ưu tiên hơn marketing.
- Tận dụng vùng địa lý hoặc hạ tầng vận chuyển khác, nếu nhà cung cấp và chính sách dữ liệu cho phép.
- Duy trì luồng gửi khi xảy ra **lỗi tạm thời** có thể xác định chắc chắn trước khi submission.
- Cung cấp khả năng bảo trì/di chuyển provider có kiểm soát.

Nhưng nó **không tự giải quyết**:

- Hai provider đều mất kết nối Internet hoặc cùng phụ thuộc một DNS/CA/network.
- Dữ liệu recipient sai hoặc đã unsubscribe.
- Domain gửi chưa được xác minh với provider B.
- Lỗi template/MIME do ứng dụng tạo ra.
- SMTP accepted nhưng thư bị bounce, spam filtering hoặc chặn ở phía nhận.
- Timeout mà kết quả gửi qua A không rõ.

Chọn dự phòng phải được thiết kế cùng **business policy** và **transport observability**, không chỉ thêm một hostname SMTP nữa.

## 2. Phân biệt provider, transport, route và notification

Trong hệ thống nhiều nhà cung cấp, một số khái niệm nên tách riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Notification** | Một ý định gửi email logic từ nghiệp vụ | Gửi xác nhận cho đơn ORD-1528 |
| **Attempt** | Một lần thử nộp notification tới provider | Attempt #1 qua A |
| **Provider** | Nhà cung cấp mail có tài khoản và chính sách riêng | A, B |
| **Transport** | Cách gửi qua provider | SMTP bằng JavaMailSender hoặc HTTP API |
| **Route** | Provider/transport được chọn cho attempt cụ thể | transactional -> A |
| **Failover** | Chọn route dự phòng khi route chính không thể dùng an toàn | A unavailable -> B |
| **Idempotency key** | Định danh logic bền vững để hạn chế gửi trùng | ORDER_CONFIRMED:ORD-1528:R |
| **Correlation ID** | Dấu vết cho log, provider events và đối soát | mail-notification-6b91 |

**Notification ID** không nên thay đổi mỗi lần chọn provider mới. **Attempt ID** có thể thay đổi để ghi rõ từng lần thử. Nếu provider có idempotency API chính thức, cần xem liệu khóa đó có hiệu lực với chính provider ấy hay không: **khóa của provider A thường không có tác dụng chống trùng tại provider B**.

### Ví dụ vòng đời một notification

~~~text
Notification #42
  business key: ORDER_CONFIRMED:ORD-1528:user-392
  recipient:   customer@example.test
  purpose:     ORDER_RECEIPT
  status:      PENDING

  Attempt #1 -> Provider A -> không kết nối được (chưa nộp)
  Attempt #2 -> Provider B -> SMTP accepted

Notification #42 -> ACCEPTED
~~~

Với tình huống **không thể chứng minh attempt #1 chưa được nộp**, không thể tự động tạo attempt #2 mà vẫn khẳng định không có khả năng gửi trùng.

## 3. Khi nào failover thật sự hữu ích?

Một provider dự phòng có ích nhất khi lỗi phát sinh **trước ranh giới gửi có thể gây side effect**.

Ví dụ:

~~~text
Kết nối đến Provider A thất bại trước khi có SMTP session
                 |
                 v
Xác định chắc chắn không có MAIL FROM / RCPT TO / DATA nào
được gửi trên kết nối thất bại
                 |
                 v
Provider B có cấu hình/health/authorization hợp lệ?
          |                      |
          v                      v
         Có                     Không
          |                      |
          v                      v
  Failover an toàn hơn         Đợi/retry sau
          |
          v
      Provider B
~~~

Ngược lại:

~~~text
Provider A nhận xong DATA
       |
       v
SMTP server có thể đã ghi mail vào queue
       |
       v
Mất phản hồi 250 / read timeout
       |
       v
Outcome = UNKNOWN
       |
       v
KHÔNG tự động gửi cùng notification qua B
~~~

Một số HTTP mail API có cơ chế idempotency key hoặc truy vấn submission; điều đó giúp giảm rủi ro **trong phạm vi API và provider đó**. Tuy nhiên, chuyển sang vendor khác vẫn cần bằng chứng vendor đầu chưa chấp nhận email hoặc một thiết kế phối hợp đặc biệt; không có idempotency toàn cầu chỉ vì ứng dụng gửi cùng một khóa cho A và B.

## 4. Phân loại lỗi trước khi chuyển provider

Một chiến lược failover cần lớp **error classification**, không chỉ catch mọi exception rồi gọi backup.

| Nhóm lỗi | Ví dụ | Có nên chuyển ngay sang B? | Giải thích |
| --- | --- | --- | --- |
| **Unavailable trước submission** | Connect refused, DNS không resolve trước khi mở kết nối | Có thể, nếu có bằng chứng chưa gửi | Không phát sinh submission |
| **TLS handshake fail trước gửi** | CA/certificate/hostname không hợp lệ | Không mặc định | Có thể là lỗi bảo mật/cấu hình; không nên lách kiểm soát |
| **Authentication/config error** | SMTP AUTH sai, sender chưa được phép | Không mặc định | Sửa cấu hình hoặc policy, không phải lỗi năng lực |
| **Rate limit/quota** | Provider báo quota hoặc tạm giới hạn trước khi nhận DATA | Có điều kiện | Tùy response, quota B, luật phân tải, consent |
| **Temporary recipient rejection** | RCPT TO bị từ chối tạm thời | Cẩn trọng | Có thể do recipient/policy chung, không nên quay vòng gây spam |
| **Permanent recipient rejection** | Địa chỉ không hợp lệ, bị suppression | Không | Gửi qua B không làm recipient hợp lệ |
| **SMTP final 2xx accepted** | Server đã xác nhận nhận message | Không | Notification đã submitted |
| **Read timeout sau DATA** | Server có thể đã accepted | Không tự động | Outcome UNKNOWN |
| **Crash sau submission** | Worker chết trước cập nhật DB | Không tự động | Provider có thể đã nhận |
| **HTTP API 2xx + request ID** | Provider đã accept request | Không | Đã nộp qua A |
| **HTTP API timeout sau request body** | Không rõ provider đã xử lý chưa | Không tự động | Outcome UNKNOWN, cần tra cứu/idempotency |
| **Ứng dụng render template lỗi** | Dữ liệu thiếu, MIME invalid | Không | Lỗi chung của message, đổi provider không giải quyết |

Không phải mọi mã **4xx/5xx** của SMTP hoặc HTTP có cùng ý nghĩa. SMTP 4xx là phản hồi tạm thời, 5xx thường là lỗi vĩnh viễn ở một giai đoạn cụ thể; HTTP 429 thường là rate limit, HTTP 5xx có thể xuất hiện sau khi xử lý một phần request. **Giai đoạn giao thức và bằng chứng accepted** quan trọng hơn chỉ dựa vào con số status.

### Đừng suy diễn từ exception class chung

Spring có các loại lỗi như **MailAuthenticationException**, **MailSendException**, **MailParseException**, nhưng không phải mọi instance của một loại exception đều cho biết chính xác provider đã nhận thư chưa. Ví dụ một **MailSendException** bao bọc socket read timeout có thể phát sinh trước hoặc sau các bước quan trọng của SMTP.

Phân loại kết quả cần dựa trên thông tin transport/provider thực sự quan sát được. Nếu lớp transport chỉ cung cấp một exception tổng quát và không có bằng chứng, hãy chọn **UNKNOWN** thay vì tự suy ra “chắc chắn chưa gửi”.

## 5. Ba kết quả an toàn cho mỗi attempt

Để không gộp mọi exception thành cùng một lựa chọn, có thể định nghĩa:

~~~text
                    Attempt Result
                           |
               +-----------+------------+
               |           |            |
               v           v            v
          ACCEPTED     NOT_ACCEPTED    UNKNOWN
                          |
                  +-------+-------+
                  |               |
                  v               v
              RETRYABLE       PERMANENT
~~~

- **ACCEPTED:** có bằng chứng provider/SMTP đã chấp nhận submission, không failover.
- **NOT_ACCEPTED_RETRYABLE:** có bằng chứng không được chấp nhận và lỗi cho phép thử route khác/sau thời gian chờ.
- **NOT_ACCEPTED_PERMANENT:** có bằng chứng bị từ chối vĩnh viễn; không quay vòng provider.
- **UNKNOWN:** không thể xác định đã accepted hay chưa; không failover tự động mặc định.

Ví dụ kiểu Java:

~~~java
public enum SubmissionOutcome {
    ACCEPTED,
    NOT_ACCEPTED_RETRYABLE,
    NOT_ACCEPTED_PERMANENT,
    UNKNOWN
}
~~~

Các trạng thái này là **mô hình ứng dụng**, không phải trạng thái Spring Framework Mail tự trả về. Chúng giúp tách **logic chọn provider** khỏi chi tiết ngoại lệ của từng SDK/transport.

### Failover là một quyết định, không chỉ là retry

Một attempt mới có thể vẫn dùng provider A sau backoff, chuyển sang B hoặc dừng chờ đối soát. Quyết định phụ thuộc:

1. Outcome của attempt trước.
2. Quy tắc retry/failover theo loại lỗi.
3. Health, quota và khả năng của provider dự phòng.
4. Thông điệp vẫn còn đủ điều kiện gửi?
5. Thời gian còn lại của yêu cầu (deadline, OTP expiry, business SLA).
6. Ràng buộc pháp lý, địa lý và quyền riêng tư.

Không thể thiết kế đúng chỉ bằng mệnh đề **if (!providerA.available()) sendViaB()**.

## 6. Các tiêu chí chọn provider dự phòng

Một provider dự phòng chỉ hữu ích khi **thực sự có thể gửi loại notification đang cần xử lý**. Tình trạng health tốt không đồng nghĩa mọi sender, loại file, kích thước và vùng địa lý đều được hỗ trợ.

| Tiêu chí | Câu hỏi thực tế |
| --- | --- |
| **Sender identity** | Domain và địa chỉ From có được xác minh với B không? |
| **SPF/DKIM/DMARC** | B có được ủy quyền gửi, ký DKIM và đáp ứng alignment theo chính sách domain không? |
| **Transport security** | SMTP của B yêu cầu STARTTLS/SMTPS, chứng chỉ và hostname có được kiểm tra không? |
| **Capabilities** | B hỗ trợ SMTP/API, MIME multipart, HTML, inline CID và attachment cần thiết không? |
| **Message size** | B có chấp nhận tổng dung lượng email sau MIME/base64 encoding không? |
| **Rate limits** | Quota/concurrency gửi còn đủ hay đang bị giới hạn? |
| **Purpose** | B được phép gửi SECURITY, TRANSACTIONAL hay MARKETING nào? |
| **Geography/privacy** | Việc truyền nội dung/PII tới B có được phép theo chính sách dữ liệu không? |
| **Suppression** | Opt-out, complaint và bounce suppression có được áp dụng nhất quán trước gửi không? |
| **Webhook** | Có theo dõi accepted, delivered, bounce và complaint khi chuyển sang B không? |
| **Cost** | Failover có mức phí/giới hạn kinh doanh cần tính tới không? |
| **Reliability** | B độc lập đến đâu với cùng DNS, network, cloud region và hạ tầng khác của A? |

### Ví dụ chính sách theo purpose

~~~text
SECURITY_ALERT:
  primary = provider-a
  backup  = provider-b
  priority = HIGH

ORDER_RECEIPT:
  primary = provider-a
  backup  = provider-b
  priority = MEDIUM

MARKETING_NEWSLETTER:
  primary = provider-a
  backup  = NONE
  priority = LOW
~~~

Ở ví dụ này, marketing không được tự chuyển sang B. Có thể B chỉ được thiết kế để cứu các email giao dịch, hoặc giới hạn pháp lý/consent cho luồng marketing chưa được đồng bộ. Không nên cho mọi loại thư quyền failover chỉ vì B đang có kết nối SMTP hoạt động.

### Chất lượng dự phòng phụ thuộc tính độc lập

Nếu A và B chạy ở hai nhà cung cấp khác nhau nhưng ứng dụng chỉ có một NAT gateway hoặc một DNS resolver lỗi, cả hai route đều có thể mất kết nối. Tương tự, nếu dùng chung một domain chưa cấu hình DKIM ở B, tình trạng giao thư qua B có thể kém dù SMTP trả 250.

Nên phân tích những **shared dependencies**: network egress, DNS, TLS truststore, secret manager, message composer, database outbox, queue workers và sender domain.

## 7. Các chiến lược định tuyến phổ biến

### Primary–backup (active–passive)

~~~text
Notification -> Provider A
                    |
               A không dùng được?
                    |
                    v
                Provider B
~~~

**Ưu điểm:** đơn giản, chi phí quản lý thấp, dễ xác định sender mặc định.

**Nhược điểm:** nếu không thường xuyên thử B, cấu hình/certificate/credentials của B có thể đã hỏng mà hệ thống không biết. Backup phải được kiểm tra định kỳ bằng cách an toàn, không nhất thiết gửi mail thật tới người dùng.

### Active–active có trọng số

~~~text
                +--- 80% ---> Provider A
Notification ---|
                +--- 20% ---> Provider B
~~~

**Ưu điểm:** provider B được dùng liên tục, dễ thấy lỗi sớm và phân phối capacity.

**Nhược điểm:** cần quản lý sender reputation, quotas, recipient suppression và provider webhooks ở cả hai nơi. Với một notification, hãy chọn **một route ban đầu**, không gửi đồng thời hai bản chỉ để “tăng độ tin cậy”.

### Định tuyến theo purpose hoặc khu vực

Ví dụ SECURITY_ALERT đi B tại một khu vực, còn marketing đi A tại khu vực khác. Đây là **policy routing**, không nhất thiết là failover; một route có thể là default do đặc tính loại mail.

### Manual failover

Operator chuyển luồng gửi mới từ A sang B sau khi điều tra incident. Cách này thường an toàn hơn **automatic failover** đối với lỗi mơ hồ, vì cho phép đánh giá provider B, kiểm tra domain identity và chọn phạm vi job.

### Không gửi hedged requests cho SMTP

Hedged request là kỹ thuật gửi cùng request qua nhiều đường để lấy response nhanh hơn. Với một phép đọc idempotent, đôi khi kỹ thuật này hữu ích. Với **gửi email**, việc gọi A và B song song có thể tạo hai SMTP submissions.

~~~text
                  +--> send to A --> accepted
One notification -|
                  +--> send to B --> accepted

Result: Hai thư có thể tới người nhận.
~~~

Đừng dùng active–active song song cho **cùng một logical notification**, trừ khi có cơ chế phối hợp/idempotency toàn cục được bảo đảm thực sự — điều SMTP thông thường không cung cấp.

## 8. Chọn route phải tách khỏi hành động gửi

Một kiến trúc thuận tiện:

~~~text
Business Event / API
        |
        v
Transactional Outbox
        |
        v
Mail Dispatcher
        |
        v
Delivery Policy (recipient, suppression, purpose)
        |
        v
Provider Route Policy
        |
        +--> Provider Registry / capabilities
        +--> Health / circuit breaker
        +--> Quota / rate limit
        +--> Allowed sender domains
        |
        v
Mail Provider Adapter
        |
        +--> SMTP / JavaMailSender A
        '--> SMTP / JavaMailSender B
        |
        v
Attempt History + Outcome
~~~

Chức năng nên phân lớp:

1. **Business service** xác định nội dung và người nhận được phép nhận.
2. **Outbox** lưu công việc bền vững, chống tạo notification logic trùng.
3. **Delivery policy** kiểm tra consent/suppression, loại email và thời hạn.
4. **Route policy** chọn provider phù hợp; không có quyền bỏ qua suppression.
5. **Provider adapter** biến MIME/API data thành submission cụ thể và trả outcome có bằng chứng.
6. **Attempt repository** lưu provider, thời gian, trạng thái và correlation.
7. **Recovery/reconciler** xử lý UNKNOWN hoặc provider events.

### Route policy không được tạo side effect vô tình

Hàm **selectProvider(...)** nên quyết định lựa chọn mà không gửi mail hoặc ghi đè outcome. Điều này giúp unit test nhiều tình huống mà không kết nối SMTP:

~~~java
public record MailRouteRequest(
        String tenantId,
        String notificationId,
        MailPurpose purpose,
        String fromDomain,
        long estimatedMessageBytes
) {
}

public enum MailPurpose {
    SECURITY_ALERT,
    ORDER_RECEIPT,
    MARKETING_NEWSLETTER
}

public interface MailRoutePolicy {
    ProviderId selectInitialProvider(MailRouteRequest request);
}

public enum ProviderId {
    PRIMARY,
    BACKUP
}
~~~

Các loại ở trên là **API thiết kế của ứng dụng**, không phải class có sẵn trong Spring Mail. Ở production, validation còn cần recipient domain, tenant capability, region, cost và quyền gửi phù hợp.

## 9. Định nghĩa kết quả provider rõ ràng cho router

Một interface có thể giấu sự khác biệt giữa SMTP và HTTP API:

~~~java
public record MailSubmission(
        String notificationId,
        MailPurpose purpose,
        String recipientEmail,
        String subject,
        String plainBody,
        String htmlBody
) {
}

public enum FailureCategory {
    NONE,
    CONNECT_UNAVAILABLE,
    PROVIDER_THROTTLED,
    PROVIDER_TEMPORARY,
    RECIPIENT_REJECTED,
    AUTHENTICATION,
    TLS_SECURITY,
    CONFIGURATION,
    AMBIGUOUS_TIMEOUT,
    UNKNOWN_FAILURE
}

public record ProviderResult(
        ProviderId providerId,
        SubmissionOutcome outcome,
        FailureCategory failureCategory,
        String providerMessageId
) {
}

public interface MailProvider {
    ProviderId id();

    ProviderResult submit(MailSubmission submission);
}
~~~

**providerMessageId** là ID/queue ID khi provider có cung cấp; không nên tự tạo một giá trị rồi khẳng định đó là ID đã được provider xác nhận. Với SMTP, không phải mọi server đều đưa ra queue ID có thể sử dụng qua API. Với HTTP API, có thể nhận request ID theo hợp đồng riêng.

### Adapter phải giữ semantics về lỗi

Nếu provider HTTP trả một response **đã xác nhận rejected trước submission**, adapter có thể trả **NOT_ACCEPTED_RETRYABLE** hoặc **NOT_ACCEPTED_PERMANENT** phù hợp.

Nếu bị **timeout sau khi đã truyền request**, adapter không được suy luận “không nhận” chỉ vì client không đọc được response. Hãy trả **UNKNOWN**.

Nếu adapter chỉ bắt mọi RuntimeException và trả **NOT_ACCEPTED_RETRYABLE**, router sẽ sai một cách nguy hiểm. Cần thiết kế exception mapping bảo thủ, lưu giai đoạn giao thức khi có bằng chứng và cho phép outcome mơ hồ.

## 10. Bảng quyết định failover

Một policy nên thể hiện được điều kiện cho phép/chặn rõ ràng:

| Outcome A | Failure category | B sẵn sàng và đúng capability? | Quyết định |
| --- | --- | --- | --- |
| ACCEPTED | NONE | Bất kỳ | Không failover |
| NOT_ACCEPTED_RETRYABLE | CONNECT_UNAVAILABLE, đã chứng minh chưa submission | Có | Có thể thử B |
| NOT_ACCEPTED_RETRYABLE | PROVIDER_THROTTLED có phản hồi rejection rõ | Có, còn quota | Có thể thử B sau policy |
| NOT_ACCEPTED_RETRYABLE | PROVIDER_TEMPORARY có bằng chứng chưa accepted | Có | Có thể thử B hoặc chờ A |
| NOT_ACCEPTED_PERMANENT | RECIPIENT_REJECTED | Có | Không gửi B |
| NOT_ACCEPTED_PERMANENT | AUTHENTICATION/CONFIGURATION | Có | Dừng/escalate, không lách policy |
| UNKNOWN | AMBIGUOUS_TIMEOUT | Có | Không tự động failover |
| UNKNOWN | UNKNOWN_FAILURE | Có | Giữ UNKNOWN/đối soát |

Ngay cả với lỗi có khả năng thử B, phải kiểm tra **notification còn đủ điều kiện gửi** tại thời điểm failover. Một người có thể unsubscribe trong thời gian A bị lỗi; retry qua B không được bỏ qua suppression.

### Không dùng một cờ “primaryHealthy” làm điều kiện duy nhất

Tình trạng A bị circuit breaker OPEN cho biết **không nên mở attempt mới với A**. Nó không nói gì về kết quả attempt trước đó. Một notification đang UNKNOWN qua A không trở nên an toàn để gửi B chỉ vì A hiện bị đánh dấu unhealthy.

Route choice và outcome của từng notification phải được lưu và kiểm tra độc lập.

## 11. Ví dụ chính sách failover bảo thủ bằng Java

Giả sử ứng dụng chỉ tự động chuyển từ A sang B đối với hai tình huống đã xác minh **chưa có submission**: thất bại kết nối trước khi mở SMTP session, hoặc provider trả về rejection do quota trước khi chấp nhận message. Các lỗi khác phải được xử lý bằng chính sách riêng.

~~~java
public record FailoverDecision(
        boolean allowed,
        String reason
) {
    public static FailoverDecision allow(String reason) {
        return new FailoverDecision(true, reason);
    }

    public static FailoverDecision deny(String reason) {
        return new FailoverDecision(false, reason);
    }
}
~~~

~~~java
import java.util.EnumSet;
import java.util.Set;

public final class ConservativeFailoverPolicy {

    private static final Set<FailureCategory> SAFE_CATEGORIES =
            EnumSet.of(
                    FailureCategory.CONNECT_UNAVAILABLE,
                    FailureCategory.PROVIDER_THROTTLED
            );

    public FailoverDecision evaluate(
            ProviderResult previous,
            boolean backupEligible,
            boolean notificationStillEligible
    ) {
        if (previous.outcome()
                != SubmissionOutcome.NOT_ACCEPTED_RETRYABLE) {
            return FailoverDecision.deny(
                    "Previous submission was accepted, permanent or unknown"
            );
        }

        if (!SAFE_CATEGORIES.contains(
                previous.failureCategory()
        )) {
            return FailoverDecision.deny(
                    "Failure is not in safe-failover allowlist"
            );
        }

        if (!notificationStillEligible) {
            return FailoverDecision.deny(
                    "Notification no longer eligible"
            );
        }

        if (!backupEligible) {
            return FailoverDecision.deny(
                    "Backup capability or health not sufficient"
            );
        }

        return FailoverDecision.allow(
                "Safe failure with eligible backup"
        );
    }
}
~~~

**Quan trọng:** Có giá trị **CONNECT_UNAVAILABLE** trong allowlist **không tự chứng minh an toàn**. Adapter chỉ được trả loại này cùng outcome NOT_ACCEPTED_RETRYABLE khi xác định được lỗi xảy ra **trước bất kỳ external submission nào**. Nếu không xác định được giai đoạn, phải trả UNKNOWN. Tương tự, PROVIDER_THROTTLED chỉ có thể được failover khi provider đưa bằng chứng rejection trước khi tạo submission.

### Không biến decision thành một vòng retry vô hạn

Ví dụ route policy phải đặt **giới hạn attempts**, chống lặp A→B→A→B, và không bỏ qua yêu cầu trì hoãn từ provider:

~~~text
Attempt #1: A -> proven NOT_ACCEPTED_RETRYABLE
Policy:      B eligible
Attempt #2: B -> ACCEPTED
Stop:        notification ACCEPTED
~~~

Nếu B cũng thất bại theo cách có thể retry, có thể đặt job vào RETRY_WAIT với backoff hoặc chọn route theo một kế hoạch cụ thể. Không có yêu cầu nào buộc phải thử mọi provider trong cùng một HTTP request.

### Provider đang khỏe nhưng không được phép gửi

Provider B có thể trả health=UP nhưng chưa được cấu hình sender identity cho tenant X. Khi đó **backupEligible=false**. Người dùng và data policy quan trọng hơn việc có thể kết nối TCP tới B.

## 12. Tạo hai JavaMailSenderImpl trong Spring

Spring Mail có **JavaMailSenderImpl** để gửi qua SMTP. Khi có hai tài khoản/provider, nên tạo hai sender độc lập, mỗi sender có host, port, credentials, TLS và timeout riêng.

Ví dụ cấu hình:

~~~yaml
app:
  mail:
    providers:
      primary:
        host: smtp-a.example.test
        port: 587
        username: ${SMTP_A_USER}
        password: ${SMTP_A_PASSWORD}
      backup:
        host: smtp-b.example.test
        port: 587
        username: ${SMTP_B_USER}
        password: ${SMTP_B_PASSWORD}
~~~

Các host, username và biến môi trường là placeholder. Secret thật phải nằm trong secret manager hoặc môi trường bảo vệ, không commit vào Git. Vì cấu hình sử dụng tiền tố **app.mail.providers**, Spring Boot sẽ **không tự động tạo hai JavaMailSender chỉ từ đoạn YAML**; ứng dụng phải tự bind và tạo beans tương ứng.

### Bind properties bằng record

Với Spring Boot hiện đại hỗ trợ record-based configuration properties:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.providers")
public record ProviderMailProperties(
        Smtp primary,
        Smtp backup
) {
    public record Smtp(
            String host,
            int port,
            String username,
            String password
    ) {
    }
}
~~~

### Factory tạo sender SMTP có TLS bắt buộc

~~~java
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    private SmtpSenderFactory() {
    }

    public static JavaMailSenderImpl create(
            ProviderMailProperties.Smtp cfg
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(cfg.host());
        sender.setPort(cfg.port());
        sender.setUsername(cfg.username());
        sender.setPassword(cfg.password());
        sender.setDefaultEncoding("UTF-8");

        var props = sender.getJavaMailProperties();
        props.put("mail.transport.protocol", "smtp");
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        return sender;
    }
}
~~~

Các timeout tính bằng mili giây, là ví dụ cần điều chỉnh theo SLA. Factory minh họa **STARTTLS trên submission SMTP**; nếu provider B chỉ hỗ trợ **implicit TLS**, phải dùng cấu hình thích hợp với **mail.smtp.ssl.enable=true**, không giả định cùng bộ thuộc tính hoạt động cho mọi provider.

### Khai báo hai bean rõ tên

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(ProviderMailProperties.class)
public class MultiProviderMailConfiguration {

    @Bean("primaryMailSender")
    public JavaMailSenderImpl primaryMailSender(
            ProviderMailProperties cfg
    ) {
        return SmtpSenderFactory.create(cfg.primary());
    }

    @Bean("backupMailSender")
    public JavaMailSenderImpl backupMailSender(
            ProviderMailProperties cfg
    ) {
        return SmtpSenderFactory.create(cfg.backup());
    }
}
~~~

Vì ứng dụng có nhiều bean cùng kiểu, injection tại adapter nên chỉ rõ **@Qualifier**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;

public SmtpPrimaryMailProvider(
        @Qualifier("primaryMailSender")
        JavaMailSender sender
) {
    this.sender = sender;
}
~~~

Đoạn constructor chỉ minh họa cách định danh dependency; class hoàn chỉnh sẽ có thêm logic compose và xử lý outcome. Với Spring Boot, việc tự khai báo hai mail sender có thể ảnh hưởng tới auto-configuration mặc định và các injection khác. Cần xác định mọi nơi dùng sender nào, không để **NoUniqueBeanDefinitionException** hoặc vô tình dùng sai bean.

### Không đổi host/credentials của một sender tại runtime cho mỗi message

Một thiết kế dễ lỗi:

~~~java
sharedSender.setHost(selectHost(job));
sharedSender.setPassword(selectPassword(job));
sharedSender.send(message);
~~~

Khi nhiều thread cùng gửi, cấu hình có thể bị thay đổi giữa các attempt, khiến thư dùng sai credentials/host. Thay vào đó, **mỗi provider có JavaMailSenderImpl riêng**, cấu hình bất biến sau khởi tạo; router chọn instance phù hợp. Secret rotation cần quy trình cập nhật bean/connection/session an toàn, không tùy tiện mutate một singleton đang dùng đồng thời.

## 13. Provider adapter SMTP phải kiểm soát MIME và outcome

Ví dụ một adapter xây email bằng JavaMailSender, tách khỏi route policy:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SmtpMailProvider implements MailProvider {

    private final ProviderId id;
    private final JavaMailSender sender;
    private final String verifiedFrom;

    public SmtpMailProvider(
            ProviderId id,
            JavaMailSender sender,
            String verifiedFrom
    ) {
        this.id = id;
        this.sender = sender;
        this.verifiedFrom = verifiedFrom;
    }

    @Override
    public ProviderId id() {
        return id;
    }

    @Override
    public ProviderResult submit(MailSubmission notification) {
        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            MimeMessageHelper.MULTIPART_MODE_MIXED,
                            "UTF-8"
                    );

            helper.setFrom(verifiedFrom);
            helper.setTo(notification.recipientEmail());
            helper.setSubject(notification.subject());
            helper.setText(
                    notification.plainBody(),
                    notification.htmlBody()
            );

            sender.send(message);
            return new ProviderResult(
                    id,
                    SubmissionOutcome.ACCEPTED,
                    FailureCategory.NONE,
                    null
            );
        } catch (MessagingException ex) {
            // Lỗi compose, không phải transport failover.
            throw new IllegalArgumentException(
                    "Unable to compose MIME message",
                    ex
            );
        } catch (MailException ex) {
            // Không mặc định rằng SMTP chưa nhận email.
            return new ProviderResult(
                    id,
                    SubmissionOutcome.UNKNOWN,
                    FailureCategory.UNKNOWN_FAILURE,
                    null
            );
        }
    }
}
~~~

**Ví dụ này cố ý bảo thủ:** khi JavaMailSender ném MailException mà adapter chưa có đủ bằng chứng giao thức, outcome là UNKNOWN. Điều đó có nghĩa router **không tự động thử B**. Trong hệ thống thật, có thể bổ sung một lớp phân loại có bằng chứng từ transport để xử lý các lỗi connect chưa submission; không biến mọi exception thành retryable.

**Cần phân biệt:** nếu lỗi đến từ việc xây MIME, địa chỉ hoặc dữ liệu không hợp lệ, việc gọi provider khác không giải quyết vấn đề. Validation người nhận, From, Subject và HTML/template phải được thực hiện trong lớp composer/policy đáng tin trước khi nộp.

### Trả về ACCEPTED không phải DELIVERED

Khi lời gọi sender.send(...) hoàn tất bình thường, ứng dụng có thể ghi **SMTP submission accepted** theo semantics transport; không thể suy ra Inbox đã nhận hoặc người đọc đã mở thư. Bounce, complaint và delivery status cần được theo dõi riêng qua nhà cung cấp khi cần.

### Provider-specific senders và sender identity

Provider A có thể dùng **orders@example.test**, trong khi B có thể yêu cầu một sender identity khác đã được xác minh cho cùng thương hiệu. Không được lấy From tùy ý từ request hoặc đổi sang một domain không thuộc quyền kiểm soát chỉ để gửi bằng được.

Nếu sender domain thay đổi khi failover, cần đánh giá tác động tới SPF/DKIM/DMARC, reply routing, bounce address và niềm tin người nhận. Tốt nhất là chuẩn bị các verified identities và DNS records **trước incident**.

## 14. Điều phối failover qua service riêng

Một router cần giới hạn số attempts, bảo đảm mỗi attempt có provider ID riêng, kiểm tra eligibility và dừng khi outcome không an toàn để thử tiếp.

Ví dụ sau chỉ thể hiện **logic quyết định**, không tự triển khai transaction, persistent outbox hoặc rate limiter:

~~~java
import java.util.Map;

public final class ConservativeMailRouter {

    private final Map<ProviderId, MailProvider> providers;
    private final ConservativeFailoverPolicy failoverPolicy;
    private final BackupEligibility backupEligibility;
    private final MailEligibility mailEligibility;

    public ConservativeMailRouter(
            Map<ProviderId, MailProvider> providers,
            ConservativeFailoverPolicy failoverPolicy,
            BackupEligibility backupEligibility,
            MailEligibility mailEligibility
    ) {
        this.providers = Map.copyOf(providers);
        this.failoverPolicy = failoverPolicy;
        this.backupEligibility = backupEligibility;
        this.mailEligibility = mailEligibility;
    }

    public ProviderResult submitWithConservativeFailover(
            MailRouteRequest route,
            MailSubmission submission
    ) {
        if (!mailEligibility.allowed(route)) {
            throw new IllegalStateException(
                    "Recipient/purpose not eligible"
            );
        }

        ProviderResult primaryResult =
                providers.get(ProviderId.PRIMARY).submit(submission);

        if (primaryResult.outcome()
                == SubmissionOutcome.ACCEPTED) {
            return primaryResult;
        }

        boolean backupReady = backupEligibility.allowed(
                ProviderId.BACKUP,
                route
        );

        FailoverDecision decision = failoverPolicy.evaluate(
                primaryResult,
                backupReady,
                mailEligibility.allowed(route)
        );

        if (!decision.allowed()) {
            return primaryResult;
        }

        return providers.get(ProviderId.BACKUP).submit(submission);
    }
}
~~~

Interface minh họa cho các kiểm tra:

~~~java
public interface BackupEligibility {
    boolean allowed(
            ProviderId provider,
            MailRouteRequest request
    );
}

public interface MailEligibility {
    boolean allowed(MailRouteRequest request);
}
~~~

Mẫu router này **không phải mã hoàn chỉnh cho production**. Chẳng hạn, các ngoại lệ từ adapter cần chuyển thành outcome có policy rõ; trạng thái attempt phải được ghi bền vững trước external I/O; việc kiểm tra eligibility hai lần không loại trừ hoàn toàn race khi người dùng unsubscribe; và sender.send(...) cần timeouts phù hợp. Những điểm này được giải quyết bằng outbox/worker ở phần tiếp theo.

### Không giữ một request HTTP mở để thử vô hạn

Failover có thể cần vài giây mỗi provider, hoặc cần chờ circuit breaker, retry-after. Một endpoint nghiệp vụ không nên block vô thời hạn khi SMTP bất ổn. Với email giao dịch, **transactional outbox + worker** thường tạo ranh giới tốt hơn: API lưu ý định gửi, trả theo nghiệp vụ, còn worker xử lý attempt theo deadline và retry policy.

### Khi provider A đã unhealthy trước attempt

Nếu circuit breaker của A đã OPEN, router có thể chọn B **ngay từ đầu** cho notification **chưa có attempt**. Đây không phải failover sau một submission thất bại; nó là **initial routing dựa trên health**.

~~~text
New notification
  No attempts yet
  Primary breaker OPEN
  Backup eligible and healthy
          |
          v
      Choose B first
~~~

Điều đó thường an toàn hơn việc cố gửi qua A đang chắc chắn không hoạt động rồi mới qua B. Nhưng vẫn phải kiểm tra B đủ quyền và phù hợp purpose, đồng thời có chính sách khi cả hai provider không dùng được.

## 15. Transactional outbox giúp failover bền vững

Một luồng đáng tin cậy:

~~~text
Business transaction
       |
       +--> Save business state
       '--> Insert mail_outbox(PENDING, stable_notification_key)
       |
       v
      COMMIT
       |
       v
Worker claim job atomically
       |
       v
Check consent / suppression / deadline
       |
       v
Choose provider (primary or backup)
       |
       v
Create persisted attempt with provider + identity
       |
       v
Submit via provider outside database transaction
       |
       +-- ACCEPTED ------------------------> Outbox ACCEPTED
       |
       +-- Proven NOT_ACCEPTED_RETRYABLE ---> Re-evaluate route / retry
       |
       +-- PERMANENT -----------------------> Outbox PERMANENT_FAILED
       |
       '-- UNKNOWN -------------------------> Outbox UNKNOWN
                                                 |
                                                 v
                                            Reconciliation
~~~

Outbox lưu **một notification logic**; attempt history ghi **mỗi lần thử**. Dùng unique constraint ngăn cùng event được enqueue nhiều lần vì message broker redelivery hoặc client retry.

### Ví dụ schema cơ bản

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    notification_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_provider VARCHAR(80),
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_outbox_notification
        UNIQUE (tenant_id, notification_key)
);

CREATE TABLE mail_attempt (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL REFERENCES mail_outbox(id),
    provider VARCHAR(80) NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    failure_category VARCHAR(80),
    provider_message_id VARCHAR(250),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    correlation_id VARCHAR(150) NOT NULL
);

CREATE INDEX idx_mail_attempt_notification_time
ON mail_attempt (notification_id, started_at);

CREATE INDEX idx_mail_outbox_due
ON mail_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Schema trên là ví dụ PostgreSQL, không phải tính năng Spring Mail tạo sẵn. Để hỗ trợ retry/attempt parallel fencing nghiêm ngặt, hệ thống thực tế còn cần version/cas constraints, durable message snapshot, timeout, unique attempt identities và cách persist từng bước transaction.

### Cùng notification không được tự sinh key mới khi failover

Không nên:

~~~text
Attempt qua A: notification key = ORDER-1528-primary
Attempt qua B: notification key = ORDER-1528-backup
~~~

Vì điều này khiến hai lần thử bị đối xử như **hai công việc nghiệp vụ khác nhau** và làm mất cơ chế chống enqueue trùng. Thay vào đó:

~~~text
Notification key = ORDER_CONFIRMED:ORD-1528:user-392
Attempt #1       = provider A, attempt id = a1
Attempt #2       = provider B, attempt id = a2
~~~

Nếu có thay đổi email/nội dung do resend có chủ đích, phải tạo notification mới theo quy trình nghiệp vụ và liên kết tới notification gốc, không lặng lẽ đổi payload dưới cùng key.

## 16. Claim job nguyên tử khi có nhiều worker

Nếu hai worker cùng tìm thấy một job PENDING và đều chọn B, người nhận có thể nhận hai email. Provider router **không** thay thế cơ chế claim của outbox.

Một ví dụ PostgreSQL:

~~~sql
WITH next_job AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY available_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS m
SET
    status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = m.lease_token + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM next_job
WHERE m.id = next_job.id
RETURNING
    m.id,
    m.tenant_id,
    m.notification_key,
    m.purpose,
    m.lease_token;
~~~

Transaction claim cần commit **trước khi mở SMTP connection**, tránh giữ database row lock khi network chậm. Worker lưu attempt trước khi gửi, nộp message rồi cập nhật kết quả trong một transaction ngắn và có điều kiện lease token.

### Fencing token bảo vệ gì?

Nếu worker A bị pause quá lâu và lease hết hạn, recovery có thể thay trạng thái job. A không được cập nhật row sau khi đã mất quyền:

~~~sql
UPDATE mail_outbox
SET
    status = 'ACCEPTED',
    last_provider = :provider,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :notification_id
  AND status = 'IN_FLIGHT'
  AND lease_owner = :worker_id
  AND lease_token = :lease_token;
~~~

Nếu UPDATE ảnh hưởng 0 row, worker cũ cần xử lý late outcome theo attempt/reconciliation, không ghi đè trạng thái mới.

**Giới hạn:** fencing token chỉ ngăn ghi dữ liệu sai vào database, **không thu hồi email đã được nộp SMTP**. Đối với expired lease, không tự hiểu là chưa gửi; chuyển sang UNKNOWN/reconciliation nếu không có bằng chứng.

## 17. Tránh failover sau crash hoặc timeout không rõ kết quả

Xét tình huống:

~~~text
T1 Worker claim notification N
T2 Worker chọn A và persist attempt A1
T3 A nhận SMTP DATA
T4 A trả lời 250 nhưng response bị mất trên đường truyền
T5 Worker ghi timeout hoặc process chết
T6 Lease hết hạn
T7 Recovery thấy N chưa ACCEPTED
~~~

Nếu T7 chuyển thẳng sang B, người nhận có thể nhận cả email từ A và B. Đúng hơn:

~~~text
Expired IN_FLIGHT
       |
       v
UNKNOWN (possible accepted by A)
       |
       v
Provider A logs/API/events hoặc operator review
       |
       +--> accepted confirmed -> ACCEPTED, no B
       |
       +--> not accepted proven -> eligible for retry/B
       |
       '--> evidence incomplete -> HOLD / manual risk decision
~~~

### Khác nhau giữa delivery failure và submission ambiguity

Nếu provider A đã **ACCEPTED** nhưng sau đó gửi webhook **BOUNCED**, notification đã từng được submitted. Có thể có một workflow nghiệp vụ riêng để xử lý bounce, sửa recipient hoặc chọn kênh liên lạc khác. Không nên tự coi bounce như “A chưa gửi được nên failover B” vì có thể gây spam hoặc vi phạm suppression.

Nếu provider A trả **temporary 4xx trước khi nhận message**, tùy giai đoạn và bằng chứng, retry B có thể hợp lý hơn. Phải phân biệt **provider rejected the submission** với **provider accepted then downstream delivery failed**.

### Reconciliation là điều tra, không phải tên khác của retry

Một reconciler nên đọc:

- Attempt ID, provider ID và thời gian gửi.
- Correlation ID/Message-ID nếu provider có lưu dấu vết.
- Provider request/queue ID nếu đã nhận được.
- Webhook accepted/delivered/bounced có chữ ký hợp lệ.
- SMTP server logs/API tra cứu nếu có và semantics rõ.

**SMTP thuần không cung cấp một API tiêu chuẩn để hỏi “message với key K đã được nhận chưa?”**. Không thể đảm bảo exactly-once email delivery bằng cách tự chèn một header Message-ID giống nhau qua A và B.

## 18. Health check provider: kết nối được chưa chắc đã gửi được

Tình trạng provider có thể có nhiều mức:

| Mức kiểm tra | Xác nhận được điều gì? | Không xác nhận được điều gì? |
| --- | --- | --- |
| DNS resolve | Host có bản ghi truy vấn được | SMTP đang nhận mail |
| TCP connect | Có endpoint lắng nghe trên port | TLS, AUTH, quota hoặc sender permissions |
| SMTP greeting/EHLO | Có phản hồi giao thức SMTP | Có chấp nhận credentials/mail không |
| TLS handshake | Server có TLS/certificate hợp lệ | Tài khoản còn được phép gửi |
| AUTH thành công | Credentials được chấp nhận | Recipient/message cụ thể sẽ được nhận |
| Test submission cô lập | Có thể nộp một mail test | Mọi message production đều deliver |
| Provider status API | Provider tự báo health | Không bảo đảm không có sự cố cục bộ |
| Tỷ lệ accepted gần đây | Lưu lượng thật đang có kết quả | Khi traffic bằng 0 không có đủ mẫu |

Ví dụ **JavaMailSenderImpl.testConnection()** có thể xác minh kết nối transport và AUTH tùy cấu hình mà **không gửi MIME message**. Tuy nhiên, gọi nó thường xuyên cũng tốn connection/handshake và có thể bị rate limit hoặc khiến provider hiểu nhầm là traffic bất thường.

### Không dùng một phép TCP ping làm oracle duy nhất

Một provider có thể trả lời TCP nhưng chứng chỉ TLS sai hoặc SMTP AUTH bị revoke. Ngược lại, một lần testConnection lỗi do transient network chưa đủ để đánh dấu toàn bộ provider DOWN trong thời gian dài.

Health tốt nên kết hợp:

- Passive health: kết quả từ các submissions thực tế, lỗi theo loại.
- Active health: probe có giới hạn tần suất và scope.
- Provider status page/API khi có hỗ trợ.
- Circuit breaker state, rate limiter và capacity còn lại.
- Đánh giá theo region/tenant/sender identity nếu provider có chính sách khác nhau.

### Tách liveness, readiness và mail provider availability

Nếu SMTP provider A DOWN, Spring application không nhất thiết phải bị Kubernetes restart liên tục. Liveness của process vẫn có thể UP, trong khi **mail route availability** báo degraded.

Một readiness check có thể phản ánh khả năng ứng dụng phục vụ request quan trọng, nhưng cần cẩn trọng: nếu hệ thống dùng outbox và có B khả dụng, việc đánh dấu toàn bộ app DOWN chỉ vì A lỗi sẽ làm mất cả API nghiệp vụ dù outbox có thể vẫn nhận job. Nên có health indicator riêng cho mail subsystem và alert tương ứng thay vì gắn tất cả vào liveness.

## 19. Circuit breaker để không dồn request vào provider đang lỗi

**Circuit breaker** là cơ chế tạm dừng gọi provider khi các phép gọi trước đó thất bại nhiều, sau đó cho một số request thăm dò để xem provider đã hồi phục chưa.

~~~text
           Calls healthy
                |
                v
              CLOSED
                |
        Failures exceed threshold
                |
                v
               OPEN
                |
         Wait open duration
                |
                v
             HALF_OPEN
          +-----+------+
          |            |
       Probe OK      Probe fail
          |            |
          v            v
        CLOSED        OPEN
~~~

### Circuit breaker không phải bằng chứng result của notification

Nếu A đã OPEN, notification mới chưa có attempt có thể được route thẳng sang B. Nhưng một notification đã **UNKNOWN từ attempt A** phải giữ UNKNOWN; breaker OPEN không cho biết attempt đó đã được SMTP nhận hay chưa.

### Không tính mọi lỗi là lỗi sức khỏe provider

Ví dụ lỗi **recipient invalid**, sender chưa được ủy quyền, template invalid hoặc opt-out không có nghĩa provider A đang chết. Nếu những lỗi này làm circuit breaker OPEN, hệ thống có thể chuyển hàng loạt traffic hợp lệ sang B mà vẫn không xử lý được nguyên nhân.

Một bảng phân loại:

| Failure | Có thể tính vào breaker health? |
| --- | --- |
| Connect refused, network unavailable | Có |
| Server 5xx do outage, nếu semantics rõ | Có thể |
| Rate limit 429/SMTP throttle | Thường cần rate limiter/backoff riêng |
| TLS certificate mismatch | Không nên tự failover; báo sự cố bảo mật/config |
| Wrong credentials | Không phải health của provider thuần; cần xử lý config |
| Invalid recipient / hard bounce | Không |
| Suppressed by consent | Không |
| Message rendering error | Không |
| Ambiguous timeout | Có thể đóng góp vào health signal, nhưng notification vẫn UNKNOWN |

Việc một timeout được tính vào breaker health **không có nghĩa cùng notification được phép retry/failover**. Đây là hai quyết định độc lập.

### Ví dụ dùng health gate trừu tượng

~~~java
public interface ProviderHealth {

    boolean canTryNewSubmission(ProviderId provider);
}

public final class HealthAwareBackupEligibility
        implements BackupEligibility {

    private final ProviderHealth health;
    private final ProviderCapabilities capabilities;

    public HealthAwareBackupEligibility(
            ProviderHealth health,
            ProviderCapabilities capabilities
    ) {
        this.health = health;
        this.capabilities = capabilities;
    }

    @Override
    public boolean allowed(
            ProviderId provider,
            MailRouteRequest request
    ) {
        return health.canTryNewSubmission(provider)
                && capabilities.supports(provider, request);
    }
}

public interface ProviderCapabilities {
    boolean supports(ProviderId provider, MailRouteRequest request);
}
~~~

**ProviderHealth** có thể được backed bởi Resilience4j CircuitBreaker, internal state hoặc provider health metrics. Các type trên là API tự định nghĩa, không phải hàm của thư viện. Nếu dùng Resilience4j, cần cấu hình đúng exception/result predicates và số mẫu tối thiểu; không để lỗi invalid recipient mở breaker toàn hệ thống.

### Half-open phải có giới hạn thử lại

Khi A từ OPEN chuyển HALF_OPEN, đừng đưa ngay toàn bộ backlog hàng chục nghìn notification trở lại A. Chỉ cho một số probe/attempt mới, rồi tăng traffic dần nếu tỷ lệ accepted ổn định. Cách này tránh một đợt **retry storm** ngay khi provider mới hồi phục.

## 20. Rate limiter, quota và backpressure

Một provider có thể khỏe nhưng không còn **quota** cho phút hoặc ngày hiện tại. Chọn B lúc đó có thể phù hợp với policy, nhưng cần giới hạn theo năng lực thật của B.

Các loại giới hạn có thể gặp:

- Số message/giây hoặc phút.
- Số recipient/giây.
- Số connections đồng thời.
- Số messages mỗi phiên SMTP.
- Giới hạn theo account, tenant, sender domain hoặc region.
- Giới hạn tổng dung lượng email.
- Daily quota hoặc budget cost.

### Backpressure thay vì cố gửi mọi thứ ngay

~~~text
Outbox due jobs: 50.000

Provider A quota: 100 messages/second
Provider B quota: 30 messages/second

Router + rate limiters
       |
       +--> A capacity 100/s
       '--> B capacity 30/s

Excess jobs -> REMAIN PENDING/RETRY_WAIT
~~~

Nếu B chỉ được cấp 30 messages/s nhưng worker tăng lên 300 threads và dồn mọi attempt qua B, hệ thống sẽ tiếp tục bị throttle. **Failover không tạo thêm quota vô hạn**.

### Provider B có thể có rate limit rất khác A

Một phương án disaster recovery nên dự trù: liệu B có đủ capacity cho tất cả email critical không? Nếu không, cần **priority policy**:

1. Giữ capacity cho SECURITY/TRANSACTIONAL.
2. Tạm dừng marketing hoặc gửi theo lô nhỏ.
3. Trì hoãn các notification không thiết yếu.
4. Điều chỉnh concurrency theo accepted latency và quota thực tế.

Tăng tốc gửi phải tôn trọng suppression và provider retry-after/backoff. Không đổi available_at hàng loạt để buộc mọi job chạy ngay.

### Dùng Retry-After nếu provider cung cấp

Một provider HTTP API có thể trả **429 Too Many Requests** kèm Retry-After. SMTP có phản hồi tạm thời riêng nhưng không phải mọi provider hỗ trợ cùng format retry hint. Adapter nên chuẩn hóa **retryAt** hoặc backoff advice nếu có bằng chứng, và worker lưu thời điểm retry đúng policy.

Không chuyển A→B vô điều kiện khi A đang rate-limited nếu điều đó vi phạm terms of service, gây vượt quota tài khoản khác hoặc tạo một làn sóng email không mong đợi.

## 21. Retry và failover cần phối hợp theo thời gian

Một chiến lược có thể có các mức:

~~~text
T0: Notification due
  |
  v
Choose A
  |
  +-- ACCEPTED ------------------------------> DONE
  |
  +-- NOT_ACCEPTED_RETRYABLE, B eligible
  |        |
  |        v
  |      Choose B, at most once in this cycle
  |        |
  |        +-- ACCEPTED ----------------------> DONE
  |        |
  |        +-- NOT_ACCEPTED_RETRYABLE --------> RETRY_WAIT
  |        |
  |        '-- UNKNOWN ----------------------> RECONCILE
  |
  +-- NOT_ACCEPTED_RETRYABLE, B not eligible -> RETRY_WAIT
  |
  +-- NOT_ACCEPTED_PERMANENT ----------------> PERMANENT_FAILED
  |
  '-- UNKNOWN ------------------------------> RECONCILE
~~~

Một lần thử khác có thể diễn ra sau **exponential backoff + jitter** và phải kiểm tra lại health, suppression, message TTL và quota. Không dùng chỉ một biến **retries=3** mà không định nghĩa khi nào đã chuyển provider, timeout gì là safe và outcome gì là UNKNOWN.

### Ví dụ chính sách thời gian minh họa

~~~text
Initial attempt -> A
Safe reject     -> thử B nếu trong budget/đủ điều kiện
Both unavailable -> retry after 30s + jitter
Retry #2         -> chọn route theo health mới
Retry #3         -> backoff dài hơn
Deadline reached -> DEADLINE_EXPIRED / NEEDS_REVIEW
UNKNOWN          -> không tiếp tục automatic retry
~~~

Các giá trị thời gian/phép thử là ví dụ, không phải cấu hình mặc định của Spring Mail. Một email OTP có thời hạn ngắn có thể không nên retry khi mã đã hết hạn; một biên nhận có thể cho phép trì hoãn lâu hơn. Phải kiểm tra **business deadline**, không chỉ network policy.

### Không retry khi suppression thay đổi

Trong thời gian A lỗi, người nhận newsletter có thể unsubscribe. Mỗi lần chuyển provider hoặc retry phải gọi lại **MailDeliveryPolicy**. Provider B không được trở thành đường обход qua opt-out, complaint hoặc hard bounce đã lưu.

### Không reset attempt history khi failover

Nếu một notification thử A rồi B, lịch sử phải thể hiện cả hai. Xóa attempt A vì đã đổi provider khiến reconciliation khó biết liệu A đã từng nhận email hay chưa và làm tăng nguy cơ retry trùng.

## 22. Failback: quay về provider chính sau khi phục hồi

Failover là chọn B khi A không thể sử dụng; **failback** là đưa lưu lượng mới quay lại A sau khi A phục hồi.

Không nên chuyển tất cả traffic về A ngay khi một health probe đầu tiên thành công:

~~~text
A DOWN -> All eligible new traffic to B
         |
       A reports UP once
         |
       Immediate all-to-A
         |
       A throttles again
         |
       All-to-B
       ...
~~~

Hiện tượng luân phiên này gọi là **flapping**. Giải pháp có thể dùng:

- Circuit breaker HALF_OPEN cho vài phép thử có kiểm soát.
- Cooldown period trước khi failback.
- Threshold/hysteresis: cần nhiều dấu hiệu thành công hơn để đóng breaker.
- Canary: 1%, 5%, 20% rồi tăng dần.
- Giới hạn tăng throughput theo tốc độ ổn định.
- Giữ các notification UNKNOWN tại route cũ cho đến khi đối soát.

### Không đổi provider của attempt đang chạy

Khi failback, chỉ quyết định route cho **attempt mới hợp lệ**. Không sửa provider ID của attempt đang IN_FLIGHT hoặc UNKNOWN; thông tin này là bằng chứng cần thiết để tra cứu log/webhook sau sự cố.

### Failback có thể tạo áp lực mới lên reputational signals

Khi chuyển nhiều email giữa providers, DKIM selector, return-path và outbound IP reputation có thể khác nhau. A vừa hồi phục về kỹ thuật nhưng chưa chắc có thể chịu lại toàn bộ lưu lượng hoặc delivery reputation đang tốt. Cần theo dõi cả accepted rate, bounce và complaint, không chỉ TCP health.

## 23. Sender domain, SPF, DKIM, DMARC khi dùng B

Một sự cố phổ biến: provider A chấp nhận được mail từ **example.test**; provider B cũng kết nối SMTP được nhưng domain gửi chưa được xác minh.

Một số thứ cần chuẩn bị trước khi bật failover:

| Thành phần | Provider A | Provider B | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Verified sender domain | Đã cấu hình | Phải cấu hình sẵn | Không gửi nhân danh domain ngoài quyền |
| DKIM signing | Selector/key A | Selector/key B | Public DNS và signing hoạt động |
| SPF authorization | Route phù hợp A | Route phù hợp B | Không vô ý vượt SPF DNS lookup limits |
| DMARC alignment | From phù hợp | From cũng phải phù hợp | Xem alignment SPF/DKIM |
| Bounce/return-path | Domain/subdomain A | Domain/subdomain B | Xử lý bounce đúng route |
| Feedback loop/webhook | Event pipeline A | Event pipeline B | Đồng bộ suppression và trạng thái |
| Reply-To | Hộp thư được quản lý | Có thể dùng chung | Tránh làm mất thư phản hồi |

**SPF, DKIM và DMARC** không phải cơ chế JavaMailSender tự bật chỉ bằng việc cấu hình host. Chúng liên quan DNS domain authentication, chính sách outbound mail server và provider. Một provider backup cần được cấu hình và xác minh trước, không nên bắt đầu thêm DNS trong lúc incident mới phát hiện thư bị từ chối.

### DKIM khác nhau không nghĩa cùng một message được dedup

Hai providers có thể ký DKIM bằng các selectors khác nhau. Dù Subject, Message-ID và body giống nhau, người nhận vẫn có thể nhận hai message. DKIM xác thực nguồn/signature theo domain, **không thực hiện exactly-once**.

### SPF có giới hạn và không phải cứ thêm mọi provider là xong

Việc thêm nhiều **include:** vào SPF phải tôn trọng cú pháp và giới hạn đánh giá DNS của tiêu chuẩn. Không tự thêm mọi include được vendor đưa mà không kiểm tra, vì SPF có thể trở nên không hợp lệ hoặc kết thúc bằng permerror.

### Nội dung giao dịch nhất quán

Email nhận từ provider A hoặc B nên có cùng sự thật nghiệp vụ: mã đơn, số tiền, địa chỉ trả lời và các liên kết từ domain tin cậy. Không để fallback tự thay nội dung hóa đơn, tạo token OTP mới hoặc đổi tenant branding một cách không được ủy quyền.

## 24. Privacy, data residency và suppression xuyên provider

Failover sang provider B nghĩa là gửi dữ liệu email — có thể gồm địa chỉ, tên khách hàng, giao dịch và attachment — đến một bên xử lý khác. Việc B có khả năng kỹ thuật không đủ để cho phép chuyển dữ liệu sang đó.

Các chính sách cần được kiểm tra:

- B đã được phê duyệt xử lý loại dữ liệu đang gửi chưa?
- Có hợp đồng bảo vệ dữ liệu và phạm vi xử lý phù hợp không?
- B lưu/truyền dữ liệu ở vùng địa lý nào?
- Có giới hạn loại attachment hoặc dữ liệu nhạy cảm không?
- Retention, khả năng xóa, audit và support access ra sao?
- Webhook/track pixel có được phép cho loại email này không?
- Tenant nào bị cấm sử dụng provider B theo cam kết?

### Suppression không thể chỉ nằm ở provider A

Giả sử người nhận đã bấm unsubscribe trong email marketing gửi qua A; A ghi suppression vào hệ thống của họ, nhưng ứng dụng không cập nhật dữ liệu trung tâm. Khi A gặp lỗi, router gửi cùng email marketing qua B, và B chưa biết người nhận đã hủy.

~~~text
Provider A: recipient UNSUBSCRIBED
          |
          X Webhook chưa cập nhật app
          |
MailRouter -> Provider B (không có suppression)
          |
          v
Recipient nhận tiếp marketing không mong muốn
~~~

**Giải pháp:** delivery policy/suppression ở tầng ứng dụng là hàng rào chung trước cả A và B, đồng thời đồng bộ provider events và suppression lists theo hợp đồng API. Cần xử lý webhook lặp/trễ và đối soát khi event bị mất.

### Không chọn B để lách hard bounce hoặc complaint

Khi A ghi nhận hard bounce hoặc spam complaint, không thử B đơn giản vì hy vọng thư sẽ “đến được”. Có thể B vẫn chấp nhận SMTP, nhưng điều đó làm xấu deliverability và bỏ qua ý định/khả năng nhận của recipient.

Lưu **suppression reason** riêng:

~~~text
OPT_OUT
COMPLAINT
HARD_BOUNCE
MANUAL_DO_NOT_CONTACT
INVALID_RECIPIENT
~~~

Các reason có quy trình phục hồi khác nhau. Một lần resubscribe không tự động xóa mọi suppression do complaint hay bounce.

### Token email và secret trong route logs

Nếu notification chứa password reset token hoặc OTP, không log raw MIME body, link token, username/password SMTP, bearer token provider API hoặc full recipient address. Logs có thể dùng notification ID opaque, attempt ID, provider ID, error category và duration.

## 25. Giám sát multi-provider bằng Micrometer

Một dashboard giúp người vận hành biết hệ thống đã chuyển sang B vì sao và failover có thực sự cải thiện submission rate hay không.

### Các metric đề xuất

| Metric | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **mail_provider_attempts** | Counter | Số attempt theo provider/outcome |
| **mail_provider_failover_decisions** | Counter | Quyết định allow/deny và reason |
| **mail_provider_submission_seconds** | Timer | Thời gian submission theo provider |
| **mail_provider_circuit_state** | Gauge | Trạng thái breaker CLOSED/OPEN/HALF_OPEN |
| **mail_provider_health_probe_failures** | Counter | Lỗi chủ động thăm dò health |
| **mail_provider_rate_limited** | Counter | Số lần bị throttle |
| **mail_provider_inflight** | Gauge | Số request/SMTP attempts đang thực thi |
| **mail_outbox_due** | Gauge | Job đã đến hạn nhưng chưa xử lý |
| **mail_outbox_unknown** | Gauge | Job kết quả không xác định |
| **mail_provider_reconciliation** | Counter | Đối soát thành công/thất bại/không có bằng chứng |
| **mail_provider_webhook_events** | Counter | Accepted/delivered/bounce/complaint theo provider |

Đây là **tên metric do ứng dụng thiết kế**, không phải metrics Spring Mail có sẵn. Với Prometheus, Counter có thể được export với hậu tố **_total** và tên được chuẩn hóa; cần xem dữ liệu thực tại endpoint metrics trước khi viết alert.

### Những tags nên và không nên dùng

Tags có cardinality thấp:

~~~text
provider=primary|backup
purpose=security|transactional|marketing
outcome=accepted|retryable|permanent|unknown
reason=connect_unavailable|throttled|...
~~~

Không đưa **recipient email**, **order ID**, **notification ID**, **message ID** hoặc raw exception message vào metric labels. Dữ liệu high-cardinality có thể làm metrics backend quá tải và lộ thông tin nhạy cảm.

### Instrument duration

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class MeteredMailProvider implements MailProvider {

    private final MailProvider delegate;
    private final MeterRegistry registry;

    public MeteredMailProvider(
            MailProvider delegate,
            MeterRegistry registry
    ) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public ProviderId id() {
        return delegate.id();
    }

    @Override
    public ProviderResult submit(MailSubmission submission) {
        Timer.Sample sample = Timer.start(registry);
        ProviderResult result = null;
        try {
            result = delegate.submit(submission);
            registry.counter(
                    "mail_provider_attempts",
                    "provider", delegate.id().name(),
                    "outcome", result.outcome().name()
            ).increment();
            return result;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail_provider_submission_seconds",
                            "provider", delegate.id().name()
                    )
            );
        }
    }
}
~~~

Đây là ví dụ đo duration, không phải implementation hoàn chỉnh cho exception metrics. Nếu delegate có thể ném exception, wrapper cần phân loại lỗi phù hợp trước khi tăng Counter và bảo đảm outcome được lưu ở attempt history. Không đo trạng thái ACCEPTED chỉ vì bắt được exception rồi tự cho rằng lần gửi thất bại.

### Alerts nên phản ánh sự phục hồi, không chỉ provider A DOWN

Ví dụ:

- A breaker OPEN, B healthy: cảnh báo **degraded**, nhưng notification critical vẫn có thể được xử lý.
- A và B đều unavailable: báo sự cố nghiêm trọng theo purpose.
- Failover rate tăng, backup quota sắp hết: cảnh báo capacity.
- UNKNOWN tăng: cảnh báo reconciliation, không chỉ SMTP availability.
- Due backlog/oldest age tăng: người dùng bắt đầu bị ảnh hưởng.
- Webhook provider B bị lỗi: có nguy cơ thiếu bounce/complaint suppression.

Không nên tạo alert chỉ từ một health probe lỗi ngắn mà bỏ qua accepted rate và mức ảnh hưởng. Ngược lại, một provider health xanh nhưng outbox không gửi được vẫn phải phát hiện qua due backlog và terminal throughput.

## 26. Log và trace cho từng lần chọn provider

Một log structured có thể là:

~~~text
event=mail_provider_attempt_finished
notification_id=6b91...
attempt_id=1f20...
provider=primary
purpose=ORDER_RECEIPT
outcome=NOT_ACCEPTED_RETRYABLE
failure_category=CONNECT_UNAVAILABLE
elapsed_ms=5021
route_decision=ALLOW_BACKUP
~~~

Attempt tiếp theo:

~~~text
event=mail_provider_attempt_finished
notification_id=6b91...
attempt_id=7b13...
provider=backup
purpose=ORDER_RECEIPT
outcome=ACCEPTED
failure_category=NONE
elapsed_ms=764
route_decision=COMPLETE
~~~

Những logs này giúp giải thích vì sao cùng notification dùng hai providers mà không cần in recipient/HTML body. Dùng correlation ID giữa business event, outbox job, attempt và provider event.

### Trace spans theo ranh giới

~~~text
mail.dispatch.notification
  |
  +-- mail.policy.check
  |
  +-- mail.route.select
  |
  +-- mail.attempt.persist
  |
  +-- mail.provider.submit (A)
  |
  +-- mail.failover.decide
  |
  '-- mail.provider.submit (B)
~~~

Không đưa password, OTP, reset token hoặc raw MIME vào span attributes. Trace có thể chứa **provider**, **purpose**, **notification opaque ID**, **outcome** và nhóm lỗi.

### Provider events đến trễ phải gắn đúng attempt

Webhook từ A có thể đến sau khi notification đã được thử B. Event handler cần phân biệt **providerMessageId** và provider ID, ánh xạ đúng attempt, xử lý event lặp/khác thứ tự, tránh chuyển toàn bộ notification sai trạng thái.

Một webhook DELIVERED từ A khi notification đã ACCEPTED qua B có thể là dấu hiệu đã gửi trùng hoặc bằng chứng quan trọng cho reconciliation. Không nên bỏ qua chỉ vì “A hiện là provider dự phòng” hoặc vì provider route đã thay đổi.

## 27. Kiểm thử router bằng fake providers

Unit test routing cần mô phỏng được nhiều kết quả mà không kết nối SMTP thật. Mục tiêu là chứng minh:

- A accepted -> B không được gọi.
- A không thể kết nối **và chắc chắn chưa submission** -> B được thử nếu eligible.
- A timeout mơ hồ -> B **không được gọi**.
- A lỗi recipient vĩnh viễn -> B không được gọi.
- B không đủ quyền/capability -> không thử B.
- Recipient đã bị suppression -> không gửi qua bất kỳ provider nào.
- B accepted -> notification hoàn tất, không thử lần thứ ba.

### Fake provider đếm số lần gọi

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class FakeMailProvider implements MailProvider {

    private final ProviderId providerId;
    private final ProviderResult result;
    private final AtomicInteger calls = new AtomicInteger();

    public FakeMailProvider(
            ProviderId providerId,
            SubmissionOutcome outcome,
            FailureCategory failureCategory
    ) {
        this.providerId = providerId;
        this.result = new ProviderResult(
                providerId,
                outcome,
                failureCategory,
                null
        );
    }

    @Override
    public ProviderId id() {
        return providerId;
    }

    @Override
    public ProviderResult submit(MailSubmission submission) {
        calls.incrementAndGet();
        return result;
    }

    public int callCount() {
        return calls.get();
    }
}
~~~

### Test không failover khi kết quả UNKNOWN

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ConservativeMailRouterTest {

    private static final MailSubmission MAIL = new MailSubmission(
            "notification-42",
            MailPurpose.ORDER_RECEIPT,
            "customer@example.test",
            "Xác nhận đơn hàng",
            "Đơn hàng đã xác nhận.",
            "<p>Đơn hàng đã xác nhận.</p>"
    );

    private static final MailRouteRequest ROUTE =
            new MailRouteRequest(
                    "tenant-7",
                    "notification-42",
                    MailPurpose.ORDER_RECEIPT,
                    "example.test",
                    1000
            );

    @Test
    void unknownFromPrimaryDoesNotTriggerBackup() {
        FakeMailProvider primary = new FakeMailProvider(
                ProviderId.PRIMARY,
                SubmissionOutcome.UNKNOWN,
                FailureCategory.AMBIGUOUS_TIMEOUT
        );
        FakeMailProvider backup = new FakeMailProvider(
                ProviderId.BACKUP,
                SubmissionOutcome.ACCEPTED,
                FailureCategory.NONE
        );

        ConservativeMailRouter router =
                new ConservativeMailRouter(
                        Map.of(
                                ProviderId.PRIMARY, primary,
                                ProviderId.BACKUP, backup
                        ),
                        new ConservativeFailoverPolicy(),
                        (provider, route) -> true,
                        route -> true
                );

        ProviderResult result =
                router.submitWithConservativeFailover(
                        ROUTE, MAIL
                );

        assertEquals(SubmissionOutcome.UNKNOWN, result.outcome());
        assertEquals(1, primary.callCount());
        assertEquals(0, backup.callCount());
    }

    @Test
    void provenConnectFailureCanUseEligibleBackup() {
        FakeMailProvider primary = new FakeMailProvider(
                ProviderId.PRIMARY,
                SubmissionOutcome.NOT_ACCEPTED_RETRYABLE,
                FailureCategory.CONNECT_UNAVAILABLE
        );
        FakeMailProvider backup = new FakeMailProvider(
                ProviderId.BACKUP,
                SubmissionOutcome.ACCEPTED,
                FailureCategory.NONE
        );

        ConservativeMailRouter router =
                new ConservativeMailRouter(
                        Map.of(
                                ProviderId.PRIMARY, primary,
                                ProviderId.BACKUP, backup
                        ),
                        new ConservativeFailoverPolicy(),
                        (provider, route) -> true,
                        route -> true
                );

        ProviderResult result =
                router.submitWithConservativeFailover(
                        ROUTE, MAIL
                );

        assertEquals(SubmissionOutcome.ACCEPTED, result.outcome());
        assertEquals(ProviderId.BACKUP, result.providerId());
        assertEquals(1, primary.callCount());
        assertEquals(1, backup.callCount());
    }
}
~~~

Các test trên chứng minh **logic policy**, không chứng minh một exception cụ thể của JavaMailSender thực sự xảy ra trước submission. Chỗ quan trọng cần integration test riêng là **adapter mapping từ SMTP/HTTP failure sang ProviderResult**.

### Test không sử dụng B khi recipient đã opt-out

Một tình huống:

~~~text
Primary A: proven connection failure
Backup B: healthy
Recipient: vừa unsubscribe marketing

Expected:
  MailEligibility.allowed() = false
  Backup submit count = 0
~~~

Policy cần kiểm tra lại eligibility trước failover, vì consent có thể thay đổi trong lúc kết nối A bị lỗi.

### Test B không đủ sender/domain capability

~~~text
Primary A: proven unavailable
Backup B: health UP, fromDomain not verified

Expected:
  backupEligible = false
  job stays waiting/failure according to policy
  no attempt sent through B
~~~

Health UP không thể bỏ qua sender identity hoặc giới hạn theo tenant.

## 28. Kiểm thử tích hợp với hai SMTP servers cô lập

Unit test có thể chỉ ra quyết định đúng, nhưng multi-provider còn phụ thuộc wiring **hai JavaMailSenderImpl** và network transport. Với integration test, có thể dùng hai SMTP servers thử nghiệm chạy trên loopback/container network.

~~~text
Spring Test Context
        |
        +--> JavaMailSender A --> SMTP fixture A
        |                         - Local mailbox A
        |                         - Dynamic port A
        |
        '--> JavaMailSender B --> SMTP fixture B
                                  - Local mailbox B
                                  - Dynamic port B
~~~

**GreenMail** có thể phục vụ bài test gửi/capture MIME cơ bản; nếu cần mô phỏng SMTP commands, lỗi từng giai đoạn DATA hoặc TLS/AUTH chi tiết, có thể sử dụng một SMTP test fixture được dự án điều khiển hoặc server container với khả năng fault injection. Không giả định mọi SMTP catcher mặc định có thể tạo “server accepted nhưng mất response” theo cách chính xác.

### Các kịch bản tích hợp cần có

| Test | A | B | Kỳ vọng |
| --- | --- | --- | --- |
| Normal primary | Healthy | Healthy | Chỉ A nhận message |
| A down trước connect | Connection refused | Healthy | B nhận message nếu policy cho phép |
| A accepted | Accepted | Healthy | B không nhận |
| A read timeout sau DATA | Có thể accepted | Healthy | B không nhận tự động, job UNKNOWN |
| A TLS identity mismatch | Security failure | Healthy | Không tự vượt policy sang B |
| A SMTP AUTH invalid | Config/auth error | Healthy | B không được gọi theo policy bảo thủ |
| A provider throttled trước accept | Proven rejected | Healthy và quota đủ | B có thể nhận |
| A recipient permanent rejected | Rejected | Healthy | Không gửi qua B |
| A down, B down | Connection failure | Connection failure | RETRY_WAIT theo backoff, không loop |
| A down, B sender unverified | Connection failure | Config invalid | Không gửi B |
| B accepted, app crash before DB commit | Accepted | Không còn route thứ ba | Recovery UNKNOWN, không retry mù |
| User unsubscribe sau enqueue | A lỗi | B healthy | Không gửi marketing |
| A recovery | Half-open healthy | Healthy | Canary/failback tăng dần |

### Thử cố tình cho primary không mở được socket

Trong test fixture, có thể tạo một provider A trỏ tới **cổng loopback không có server** và xác nhận kết nối thất bại **trước khi gửi SMTP DATA**. Để kiểm tra failover end-to-end, adapter phải được cấu hình rõ rằng lỗi connect này là proven not accepted.

Một cách test tương đối bền vững là dùng **fake transport có stage tracking**: client không đi qua ngưỡng kết nối/SMTP submission thì mới trả NOT_ACCEPTED_RETRYABLE. Không nên chỉ thấy **MailSendException** rồi gán proven not accepted cho mọi lỗi bên trong.

### Fault injection sau DATA

Trường hợp quan trọng nhất:

~~~text
1. Worker gửi MAIL FROM và RCPT TO tới A
2. Worker truyền xong DATA + end-of-data marker
3. A ghi nhận message accepted
4. Kết nối đứt trước khi client nhận final response
5. Adapter trả UNKNOWN
6. Router không gọi B
7. Reconciler tìm bằng chứng accepted của A
~~~

Nếu fixture có thể chứng minh A đã accepted trong khi client mất acknowledgement, test này phát hiện lỗi **failover gây gửi trùng**. Mock ném exception trước khi tạo external side effect không đủ để kiểm tra tình huống trên.

### Không sử dụng tài khoản email thật

Integration test nên dùng:

- SMTP fixtures không relay Internet.
- Recipient thuộc domain thử nghiệm.
- Username/password chỉ dành cho test.
- Host/port động được inject vào Spring test context.
- TLS certificate/truststore test nếu kiểm tra STARTTLS/SMTPS.
- Dọn mailbox/fixture sau test, tránh các test đọc thư của nhau.

Không dùng SMTP production để mô phỏng failover, vì nó có thể gửi email thật, làm ảnh hưởng quota, sender reputation hoặc rò rỉ thông tin người dùng.

### Kiểm tra cả nội dung được chọn khi failover

Nếu provider B gửi thành công, test không chỉ đếm messages mà còn kiểm tra:

- Subject, recipient và From đã được xác minh.
- Template version và nội dung nghiệp vụ giống logical notification đã tạo.
- HTML/plain và attachment tương ứng.
- Không tạo OTP/token mới chỉ vì đổi provider.
- Correlation ID cho phép truy vết attempt.
- Bản ghi outbox chỉ đạt ACCEPTED một lần.

Không so sánh raw MIME byte-for-byte khi Message-ID, header folding hoặc multipart boundaries được sinh tự động; dùng parser kiểm tra nội dung và cấu trúc có nghĩa.

## 29. Runbook khi provider chính lỗi

Khi hệ thống cảnh báo **provider A degraded/down**, không nên lập tức chỉnh tất cả job sang B. Cần xác định lỗi thuộc loại nào, notification nào đã có attempt và provider B có thể xử lý những loại mail đó không.

### Bước 1 — Xác minh triệu chứng

Kiểm tra:

- Tỷ lệ accepted, rejected, UNKNOWN và latency của A.
- Lỗi kết nối TCP, DNS, TLS, AUTH, provider quota hay business validation.
- Circuit breaker state và thời điểm nó chuyển OPEN.
- Có deploy, secret rotation, DNS update hoặc policy change gần đây không.
- SMTP status page/API và phạm vi region/account đang lỗi.
- Outbox due backlog, oldest due age và loại notification bị ảnh hưởng.

Nếu A trả **authentication failed** sau khi secret rotation, chuyển mọi thư sang B có thể che một cấu hình sai và khiến vấn đề bảo mật không được xử lý. Tìm nguyên nhân trước khi mở rộng route policy.

### Bước 2 — Xác định provider B đủ điều kiện

Kiểm tra độc lập:

~~~text
B account enabled?
B sender domain verified?
B DKIM/DMARC alignment suitable?
B TLS/auth configuration valid?
B accepts required MIME/attachments?
B quota + concurrency sufficient?
B allowed for affected tenant/purpose/region?
B suppression and webhook sync working?
~~~

**Health check TCP thành công không đủ.** Cần bảo đảm B đã được chuẩn bị sẵn cho sản phẩm và quyền riêng tư.

### Bước 3 — Phân loại các job theo trạng thái

| Nhóm | Có được đổi sang B ngay? |
| --- | --- |
| **PENDING, chưa có attempt** | Có thể chọn B nếu B eligible |
| **RETRY_WAIT có bằng chứng chưa accepted** | Có thể theo policy/backoff |
| **IN_FLIGHT A** | Không sửa route của attempt đang chạy |
| **UNKNOWN A** | Không tự động, phải đối soát |
| **ACCEPTED A** | Không gửi lại |
| **PERMANENT_FAILED recipient** | Không lách qua B |
| **SUPPRESSED** | Không gửi |
| **CANCELLED** | Không gửi |

Một incident thường có nhiều nhóm cùng lúc. Không chạy một câu lệnh **UPDATE provider='backup' WHERE status <> 'ACCEPTED'**.

### Bước 4 — Chọn cách failover

Nếu A mất kết nối rõ ràng và B đã được phê duyệt, có thể:

1. Mở policy route **new PENDING notifications** sang B.
2. Đối với những attempt đã có proven NOT_ACCEPTED_RETRYABLE, cho phép B theo quota/backoff.
3. Giữ UNKNOWN ở trạng thái cần đối soát.
4. Không thay đổi trạng thái các job SUPPRESSED, PERMANENT_FAILED hoặc ACCEPTED.
5. Giới hạn throughput theo provider B và ưu tiên email thiết yếu.

Lưu **operator, thời điểm, lý do, phạm vi tenant/purpose** của việc chuyển route nếu thao tác thủ công. Khi policy tự động quyết định, ghi reason code tương ứng trong attempt history/logs.

### Bước 5 — Quan sát sau failover

Theo dõi:

- Accepted rate của B có tăng đúng kỳ vọng không.
- Backlog due/oldest age của transactional/security mail có giảm không.
- B có bắt đầu rate-limit hoặc báo lỗi sender identity không.
- UNKNOWN có phát sinh ở B không.
- Bounce/complaint/suppression có được cập nhật qua B không.
- Có dấu hiệu duplicate hoặc nhận nhiều email cho cùng notification không.

Không tuyên bố “đã phục hồi” chỉ vì B health=UP. Cần xác nhận **thông báo quan trọng thực sự được chấp nhận kịp thời** và backlog được giải phóng có kiểm soát.

### Bước 6 — Failback từng phần

Khi A hồi phục:

- Xác minh TLS/AUTH/sender identity và accepted rate.
- Đưa một phần nhỏ **new eligible notifications** về A.
- Tăng dần tỷ lệ khi kết quả ổn định.
- Không replay UNKNOWN hoặc ACCEPTED từ A/B.
- Đối soát mọi attempt chưa rõ trước khi đóng incident.

### Bước 7 — Postmortem

Ghi lại:

- Root cause và thời gian outage.
- Bao nhiêu notification chậm/không gửi, theo purpose.
- Bao nhiêu attempt đã qua B, có bị throttle hoặc bounce không.
- Bao nhiêu UNKNOWN và cách đối soát.
- Có duplicate hay violation of suppression không.
- Có cần tăng capacity, mở rộng health checks hoặc thay đổi route policy không.
- Test integration/fault injection nào cần được thêm để ngăn tái diễn.

## 30. Những lỗi triển khai thường gặp

### Lỗi 1 — Catch MailException rồi gọi B vô điều kiện

~~~java
try {
    primaryMailSender.send(message);
} catch (MailException ex) {
    backupMailSender.send(message);
}
~~~

**Vấn đề:** ngoại lệ có thể xảy ra sau khi A đã accepted; gửi B có thể tạo bản trùng. **Cách xử lý:** phân loại outcome theo bằng chứng; UNKNOWN không tự động failover.

### Lỗi 2 — Cho rằng SMTP timeout nghĩa là message chưa tới server

Read timeout sau DATA có thể xuất hiện khi server đã xếp message vào queue nhưng phản hồi bị mất.

**Cách xử lý:** lưu UNKNOWN và đối soát hoặc ra quyết định rủi ro có audit.

### Lỗi 3 — Hai nhà cung cấp cùng nhận một notification song song

Việc gửi song song chỉ để “provider nào nhanh hơn thì dùng” có thể làm cả hai gửi thư.

**Cách xử lý:** một logical notification chỉ có một attempt active theo claim/lease, chọn route rồi mới nộp; không dùng hedging cho SMTP.

### Lỗi 4 — Dùng cùng Message-ID để giả định dedup toàn cầu

SMTP không bắt buộc provider loại bỏ message cùng Message-ID.

**Cách xử lý:** giữ Message-ID/correlation để tra cứu, không coi đó là hợp đồng exactly-once.

### Lỗi 5 — Coi SMTP AUTH/TLS error là provider outage thông thường

Chuyển sang B có thể che lỗi sai secret, truststore hoặc hostname.

**Cách xử lý:** phân loại CONFIGURATION/TLS_SECURITY và báo sự cố; không tự động hạ chuẩn bảo mật để gửi.

### Lỗi 6 — Provider B chưa được xác minh domain

B kết nối được nhưng DKIM/DMARC không phù hợp hoặc From bị provider từ chối.

**Cách xử lý:** chuẩn bị sender identity, DNS, TLS và quotas từ trước; thử nghiệm định kỳ.

### Lỗi 7 — Dùng một JavaMailSenderImpl và setHost mỗi request

Khi nhiều thread đồng thời, sender có thể bị mutate giữa attempts.

**Cách xử lý:** tạo beans/adapters riêng, mỗi provider giữ configuration ổn định.

### Lỗi 8 — Bypass suppression khi đổi provider

Recipient opt-out được lưu ở provider A nhưng B không nhận webhook/suppression.

**Cách xử lý:** policy/suppression chung ở ứng dụng; cập nhật và đối soát provider events.

### Lỗi 9 — Dùng provider B để vượt hard bounce

Một mailbox đã bị A báo hard bounce không tự nhiên trở thành hợp lệ khi thử B.

**Cách xử lý:** phân loại recipient failure; không dùng failover để tránh suppression.

### Lỗi 10 — Tăng concurrency quá mức của B

B có quota thấp hơn A, gặp rate limit liên tục.

**Cách xử lý:** rate limiter, backpressure, priority theo purpose và giới hạn attempts.

### Lỗi 11 — Circuit breaker OPEN vì invalid recipient

Lỗi recipient không phản ánh health của toàn provider.

**Cách xử lý:** chỉ tính các failure categories phù hợp vào breaker metrics.

### Lỗi 12 — A hồi phục là chuyển toàn bộ traffic về ngay

A bị quá tải lại, tạo flapping.

**Cách xử lý:** half-open, canary, hysteresis, gradual ramp-up.

### Lỗi 13 — Không ghi provider ID vào attempt

Khi webhook đến hoặc cần điều tra, không biết tra cứu ở A hay B.

**Cách xử lý:** lưu provider, attempt ID, correlation ID, timestamps, outcome và provider message ID khi có.

### Lỗi 14 — Tạo notification_key mới khi failover

Hai attempts bị coi thành hai thông báo nghiệp vụ khác nhau, khiến dedup không hoạt động.

**Cách xử lý:** một notification key ổn định, nhiều attempt IDs.

### Lỗi 15 — Chỉ kiểm tra health lúc tạo campaign

Đến khi worker gửi, B có thể bị quota hoặc sender capability thay đổi.

**Cách xử lý:** kiểm tra health/capability tại lúc chọn route, tôn trọng deadline, rate limit và policy mới.

### Lỗi 16 — Coi SMTP accepted là delivered

Ngay cả khi B SMTP trả thành công, mailbox vẫn có thể bounce hoặc phân loại spam.

**Cách xử lý:** theo dõi provider delivery events riêng, không gộp ACCEPTED với DELIVERED.

### Lỗi 17 — Đưa PII sang vendor chưa được phê duyệt

Failover kỹ thuật có thể vi phạm data residency hoặc hợp đồng dữ liệu.

**Cách xử lý:** dùng allowlist provider theo tenant/purpose/data class; kiểm tra governance trước khi enable route.

### Lỗi 18 — Không kiểm thử backup cho tới lúc A bị sự cố

Credentials của B đã hết hạn hoặc chứng chỉ TLS/hostname không khớp.

**Cách xử lý:** probe an toàn, smoke tests cô lập, canary hoặc kiểm thử định kỳ có hạn chế tác động.

### Lỗi 19 — Retry lại UNKNOWN khi worker restart

Sau crash, outbox còn IN_FLIGHT hoặc UNKNOWN nên hệ thống gửi lại B.

**Cách xử lý:** recovery qua UNKNOWN/reconciliation và fencing, không coi lease expiry là chưa gửi.

### Lỗi 20 — Không phân biệt policy error với provider error

Một template invalid hoặc request gửi tới recipient không được phép sẽ bị thử qua cả A và B.

**Cách xử lý:** validate content/recipient/sender và authorization trước route, không dùng failover cho lỗi chung của message.

## 31. Tình huống luyện tập về chọn provider dự phòng

### Tình huống A — Không thể mở TCP connection tới provider A

Kết nối bị từ chối ngay khi khởi tạo socket; chưa có SMTP session và chưa nộp message.

**Hỏi:** có thể thử B không?

**Đáp:** có thể nếu lỗi được xác định chắc chắn là **NOT_ACCEPTED_RETRYABLE**, B đủ health/capability, recipient vẫn đủ điều kiện và rate limit/attempt budget cho phép. Ghi attempt A rồi thử B, không tạo notification mới.

### Tình huống B — Read timeout sau khi client đã gửi DATA

SMTP server A có thể đã chấp nhận message, nhưng client không nhận final 250.

**Hỏi:** nên tự động gửi B?

**Đáp:** không. Ghi UNKNOWN, giữ provider A ở attempt history, tìm bằng chứng ở logs/provider API khi có; không đổi sang B chỉ vì A hiện unhealthy.

### Tình huống C — Provider A trả lỗi sai password

SMTP AUTH trả lỗi do secret vừa được rotate.

**Hỏi:** đây có phải tín hiệu để failover mọi job qua B?

**Đáp:** không mặc định. Đây là lỗi cấu hình/xác thực; cần alert và sửa secret. Nếu tổ chức có manual disaster recovery policy đã cho phép dùng B cho notification mới, đó là một quyết định vận hành có scope rõ, không phải catch-all retry cho attempt đã có outcome không rõ.

### Tình huống D — Provider A throttle, B còn quota

A trả một lỗi throttling rõ ràng trước khi chấp nhận submission; B đã được kiểm tra và còn quota.

**Hỏi:** có thể failover?

**Đáp:** có thể theo policy nếu outcome là proven NOT_ACCEPTED_RETRYABLE, giới hạn retry/attempt, suppression và hợp đồng provider cho phép. Không xem mọi lỗi tạm thời là đã rejected trước submission.

### Tình huống E — B chưa ký DKIM cho domain From

B health UP và chấp nhận SMTP AUTH nhưng domain gửi chưa xác minh.

**Hỏi:** có được gửi critical mail qua B?

**Đáp:** không nên bypass sender identity. Cần cấu hình domain và DNS sẵn, hoặc dùng một verified sender identity đã được phê duyệt theo policy. Health check TCP không đủ.

### Tình huống F — Recipient đã unsubscribe newsletter

Notification marketing nằm trong outbox từ hôm qua; A down và B khỏe.

**Hỏi:** có nên failover marketing sang B?

**Đáp:** không nếu recipient không còn đủ điều kiện. Delivery policy chung phải được kiểm tra trước mỗi attempt, không phụ thuộc route.

### Tình huống G — A accepted trước khi worker crash

A gửi SMTP 250, worker chết trước UPDATE ACCEPTED; lease hết hạn.

**Hỏi:** job có thể chuyển ngay sang B?

**Đáp:** không. Recovery đánh dấu UNKNOWN hoặc trạng thái đối soát theo chính sách; tìm bằng chứng đã accepted và ngăn duplicate.

### Tình huống H — B cùng provider group, khác hostname

A và B là hai endpoint dùng chung một control plane, cùng quota và cùng region.

**Hỏi:** đây có phải dự phòng độc lập?

**Đáp:** có thể chỉ dự phòng được một số lỗi endpoint; chưa chắc chịu được outage của control plane hoặc quota. Cần threat model shared dependencies và kiểm thử điều kiện lỗi chung.

### Tình huống I — Provider A trả accepted, vài phút sau webhook bounce

Mailbox từ chối thư dù SMTP đã accepted.

**Hỏi:** tự động gửi lại qua B?

**Đáp:** không như một failover của submission. Bounce là một event delivery khác; cần phân loại và xử lý theo recipient/delivery policy. Gửi qua B có thể không giúp hoặc làm phát tán thư không mong muốn.

### Tình huống J — Circuit breaker của A OPEN

Một notification mới chưa có attempt; A hiện bị tạm ngưng gọi, B đủ quyền và khỏe.

**Hỏi:** có phải thử A một lần trước khi qua B không?

**Đáp:** không nhất thiết. Initial routing có thể chọn B ngay. Nhưng các notification UNKNOWN từ A trước đó vẫn phải đối soát, không được tự động reroute.

### Tình huống K — Circuit breaker của A HALF_OPEN

A bắt đầu hồi phục và một phép thử đã thành công.

**Hỏi:** có nên đẩy ngay 100% backlog về A?

**Đáp:** không. Dùng canary/ramp-up, theo dõi errors, latency, quota và accepted rate. Tránh flapping hoặc retry storm.

### Tình huống L — Email OTP hết hạn trong lúc chờ

A down, B còn quota nhưng mã OTP của notification đã hết hạn.

**Hỏi:** có nên failover gửi mã cũ?

**Đáp:** thường không còn ý nghĩa. Áp business deadline; người dùng yêu cầu mã mới sẽ tạo event mới với token và chính sách riêng, không dùng retry để âm thầm tạo OTP mới dưới cùng notification key.

### Tình huống M — Cùng Message-ID qua A và B

Hai provider đều chấp nhận thư có cùng Message-ID.

**Hỏi:** có cơ chế giao thức chung buộc mailbox chỉ nhận một bản?

**Đáp:** không. Message-ID là dữ liệu giúp correlation/threading; không phải idempotency guarantee across providers.

### Tình huống N — Provider API A có Idempotency-Key

A hỗ trợ HTTP API và có idempotency theo tài liệu. Request đầu timeout, B là một vendor khác.

**Hỏi:** gửi cùng Idempotency-Key qua B có an toàn không?

**Đáp:** không mặc định. Idempotency của A thường chỉ có hiệu lực trong A. Cần tra trạng thái A hoặc bằng chứng A chưa accepted trước khi gửi B.

### Tình huống O — Ứng dụng có ba replica worker

Ba worker cùng đọc một PENDING notification và mỗi worker chọn một provider.

**Hỏi:** làm sao ngăn gửi trùng?

**Đáp:** atomic claim/lease với transaction và fencing, không dùng SELECT rồi gửi khi chưa sở hữu job. Router một mình không đủ.

### Tình huống P — Nhà cung cấp B bị giới hạn khu vực lưu trữ

Tenant X yêu cầu email xử lý trong một vùng cụ thể, B dùng hạ tầng ngoài vùng.

**Hỏi:** có thể dùng B khi A outage nặng?

**Đáp:** chỉ khi chính sách dữ liệu/hợp đồng/ủy quyền cho phép. Nếu B không eligible, phải giữ job chờ hoặc kích hoạt quy trình được phê duyệt; ưu tiên gửi nhanh không tự thay thế quyền riêng tư.

### Tình huống Q — Provider B bị lỗi AUTH

A lỗi connect đã chứng minh chưa gửi; B lại có credentials sai.

**Hỏi:** có nên quay ngay về A và lặp vô hạn?

**Đáp:** không. Phân loại lỗi B, giới hạn attempts, ghi audit, alert cấu hình và chờ recovery. Không loop A→B→A vô hạn.

### Tình huống R — Backup nhận được thư nhưng không có bounce webhook

B SMTP accepted, dashboard outbox chuyển ACCEPTED, nhưng provider event pipeline chưa cấu hình.

**Hỏi:** có thể tuyên bố deliverability đã đầy đủ?

**Đáp:** chưa. Cần tích hợp event/bounce/complaint/suppression cho B hoặc ghi rõ giới hạn quan sát; không suy ra đã delivered từ accepted.

### Tình huống S — Người dùng nhấn “gửi lại email xác nhận”

Notification trước đã ACCEPTED, người dùng chủ động yêu cầu gửi thêm.

**Hỏi:** có cần dùng failover của notification cũ?

**Đáp:** không. Đây là **resend có chủ đích** và thường nên tạo một notification mới với business event/key riêng, liên kết notification gốc. Vẫn áp rate limit, consent và identity policy.

### Tình huống T — Metrics cho biết 100% failover nhưng inbox rate thấp

B nhận SMTP submissions nhưng tăng bounce/spam placement.

**Hỏi:** chỉ nhìn HTTP/SMTP 2xx đã đủ?

**Đáp:** không. Cần quan sát bounce, complaint, delivery events và sender reputation; chuyển provider chỉ giải quyết một phần tuyến gửi.

## 32. Checklist triển khai multi-provider failover

Trước khi bật failover trong production, nhóm phát triển có thể xác nhận các điểm sau:

### Về nghiệp vụ và dữ liệu

- Có **notification key** ổn định theo event nghiệp vụ.
- Recipient/purpose/tenant được authorization và kiểm tra suppression trước gửi.
- Template/payload ổn định qua attempts; không sinh token hoặc hóa đơn mới trong retry.
- Có deadline phù hợp cho OTP, security, transactional và marketing.
- Provider B được phép xử lý dữ liệu theo tenant/region/data class.

### Về hạ tầng gửi

- A và B có beans/adapters riêng, credentials riêng và TLS/hostname checking.
- Verified sender identities, SPF/DKIM/DMARC đã được chuẩn bị cho B.
- Giới hạn kích thước, attachment và MIME capabilities được kiểm tra.
- Rate limit/quota và provider webhook của cả hai đều hoạt động.
- Backup được probe/canary định kỳ một cách an toàn.
- Network/DNS/region shared dependencies đã được đánh giá.

### Về quyết định route

- Có phân loại **ACCEPTED / NOT_ACCEPTED_RETRYABLE / NOT_ACCEPTED_PERMANENT / UNKNOWN**.
- UNKNOWN không tự động failover.
- Chỉ failover các lỗi có bằng chứng chưa accepted và policy cho phép.
- Circuit breaker không bị mở do invalid recipient hoặc content errors.
- Provider health, quota, capabilities và sender policy được kiểm tra khi chọn route.
- Có giới hạn attempts, backoff, jitter và không ping-pong giữa providers.
- Có cơ chế gradual failback, tránh flapping.

### Về outbox và vận hành

- Worker claim notification nguyên tử, có lease/fencing token.
- Attempt history lưu provider ID, kết quả, thời điểm và correlation.
- Crash/expired lease được xử lý qua UNKNOWN khi outcome mơ hồ.
- Có reconciliation với provider khi hỗ trợ, và manual review cho trường hợp còn thiếu bằng chứng.
- Dashboard hiển thị accepted, retryable, unknown, due backlog, quota và provider health.
- Runbook cho phép rollback/route change có audit, không reset trạng thái hàng loạt.
- Integration tests bao gồm failover an toàn, timeout mơ hồ, duplicate prevention, sender identity và suppression.

Một checklist được đánh dấu đầy đủ vẫn chưa chứng minh hệ thống có exactly-once delivery; điều đó cần hợp đồng của external provider hoặc tradeoff nghiệp vụ rõ. Checklist nhằm giảm các lỗi thiết kế dễ tạo **gửi trùng, mất email hoặc sai quyền nhận**.

## 33. Sơ đồ quyết định tổng hợp

~~~text
                Notification đến hạn
                          |
                          v
            Còn đủ điều kiện gửi?
                |               |
               Không            Có
                |               |
                v               v
            SUPPRESSED     Đã có attempt UNKNOWN?
                              |            |
                             Có           Không
                              |            |
                              v            v
                        RECONCILE      Chọn initial route
                                         |
                         +---------------+---------------+
                         |                               |
                         v                               v
                    A healthy?                        A unhealthy
                         |                               |
                        Có                               v
                         |                         B eligible?
                         v                         |         |
                    Attempt A                    Có        Không
                         |                         |         |
                +--------+--------+                v         v
                |        |        |            Attempt B    RETRY_WAIT
                v        v        v                |
            ACCEPTED   UNKNOWN  Proven rejected    |
                |        |        |                |
                v        v        v                |
              DONE   RECONCILE  Error policy        |
                                  |                 |
                        Safe failover allowed?      |
                           |          |             |
                          Có         Không          |
                           |          |             |
                           v          v             |
                      B eligible?  RETRY_WAIT /     |
                           |       PERMANENT_FAILED |
                        +--+--+                     |
                        |     |                      |
                       Có    Không                   |
                        |     |                      |
                        v     v                      |
                   Attempt B RETRY_WAIT              |
                        |                            |
                        +----------------------------+
                        |
                        v
              ACCEPTED / RETRY_WAIT /
               PERMANENT / UNKNOWN
~~~

Sơ đồ chỉ tóm tắt chính sách; triển khai thật phải gắn mỗi attempt với database transaction, lease token và cơ chế recovery. Trạng thái **RETRY_WAIT** phải chứa thời điểm được phép thử lại, không trở thành vòng lặp ngay lập tức.

## 34. Các nguyên tắc cần ghi nhớ

~~~text
Primary down                      != mọi notification đều có thể gửi backup
Provider health UP                != sender/tenant/purpose đều hợp lệ
MailException                     != chắc chắn chưa gửi
SMTP 250 accepted                 != email đã tới Inbox
Timeout after DATA                -> UNKNOWN
UNKNOWN                           -> reconciliation, không auto failover
Message-ID giống nhau             != cross-provider deduplication
Provider A idempotency key        != provider B idempotency
Circuit breaker OPEN              != bằng chứng attempt cũ thất bại
Verified sender A                 != verified sender B
Recipient opt-out                 -> không gửi qua A hoặc B
Provider B rate limit             -> phải backpressure, không retry storm
Outbox UNIQUE + atomic claim      -> giảm logical duplicates
Outbox và fencing                 != exactly-once external SMTP
Failback                          -> canary, hysteresis, không đảo route mù
~~~

**Chọn provider dự phòng khi provider chính lỗi** là quyết định kết hợp **business eligibility**, **provider capabilities**, **transport outcome**, **health/circuit breaker**, **quota** và **khả năng đối soát**. Trong Spring Framework Mail, có thể cấu hình hai **JavaMailSenderImpl** và định tuyến qua adapter riêng, nhưng lựa chọn B phải xảy ra theo policy, không phải trong một khối catch chung cho mọi MailException. Khi A rõ ràng chưa nhận message, failover có thể giúp duy trì thông báo quan trọng. Khi kết quả gửi qua A không rõ, trạng thái **UNKNOWN** và reconciliation là hàng rào tránh bản trùng. Một thiết kế multi-provider bền vững cần outbox/attempt history, kiểm soát quyền gửi, DNS authentication, suppression chung, giám sát từng provider và quy trình failback có kiểm soát — đồng thời thừa nhận những giới hạn của SMTP thay vì hứa hẹn exactly-once delivery mà giao thức không bảo đảm.
