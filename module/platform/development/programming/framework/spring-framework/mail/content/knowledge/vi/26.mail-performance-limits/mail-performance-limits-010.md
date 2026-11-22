# Xử lý nhiều tenant và cô lập quota

## 1. Bài toán gửi email trong ứng dụng đa tenant

Trong một hệ thống dùng **Spring Framework Mail**, một ứng dụng có thể phục vụ đồng thời nhiều **tenant**: doanh nghiệp, tổ chức, cửa hàng, nhóm khách hàng hoặc môi trường làm việc được cô lập về dữ liệu. Mỗi tenant có thể sở hữu người gửi, domain, mẫu email, danh sách người nhận, ngân sách và chính sách bảo mật khác nhau.

Khi mọi tenant dùng chung **JavaMailSender** và cùng một SMTP provider, các lỗi về giới hạn và hiệu năng có thể lan rộng:

- Tenant A gửi một chiến dịch lớn và chiếm hết quota, khiến email OTP của tenant B bị trì hoãn.
- Một tenant liên tục retry khi SMTP trả lỗi 4xx, làm tăng áp lực lên provider và ảnh hưởng tất cả tenant còn lại.
- Các worker lấy job theo thứ tự tạo ra (FIFO) khiến tenant gửi nhiều lấn át tenant gửi ít.
- Cấu hình sender hoặc **mail.smtp.from** bị thay đổi trên một bean singleton khi xử lý tenant khác, dẫn tới gửi sai From/Return-Path.
- Các request nhập nhiều file đính kèm lớn làm cạn bộ nhớ, thread hoặc băng thông của toàn dịch vụ.
- Rate limit chỉ nằm trong bộ nhớ một instance nên không còn hiệu lực khi ứng dụng scale lên nhiều pod.
- Một lỗi xác thực hoặc tài khoản bị khóa của tenant A khiến toàn bộ mail worker dùng chung thất bại.

Do đó, bài toán **xử lý nhiều tenant và cô lập quota** không chỉ là đếm số email. Nó đòi hỏi thiết kế từ **nhận diện tenant**, **phân quyền**, **quota**, **scheduler**, **SMTP provider**, **tài nguyên hệ thống**, **retry** đến **giám sát**.

Mục tiêu của bài là xây dựng kiến trúc giúp tenant sử dụng đúng phần năng lực được cấp, không đọc hoặc dùng nhầm tài nguyên của tenant khác, đồng thời vẫn cho phép chia sẻ hạ tầng gửi mail một cách hiệu quả.

## 2. Tenant là ranh giới quyền và tài nguyên

Một tenant có thể được xác định bằng một **tenantId** ổn định. Tuy nhiên, tenantId không đơn giản là một chuỗi lấy từ HTTP header rồi tin ngay.

Ví dụ luồng yêu cầu:

~~~text
HTTP request / authenticated event
               |
               v
Authentication + authorization
               |
               v
Trusted tenant context
  tenantId = tenant-A
  permission = MAIL_SEND
               |
               v
Notification request
               |
               v
Outbox / quota / sender routing
               |
               v
SMTP submission
~~~

Các nguyên tắc:

1. TenantId phải đến từ **ngữ cảnh đã được xác thực và phân quyền**, không dựa vào một trường tenantId do client tự khai mà không kiểm tra.
2. Mọi truy vấn notification, template, sender configuration và quota phải được ràng buộc với tenant tương ứng.
3. Tenant không được chọn tùy ý SMTP credential, From domain, bounce address hoặc provider account thuộc tenant khác.
4. Background worker phải mang tenant identity **cùng với job đã lưu**, vì thread xử lý không còn HTTP request context gốc.
5. Khi một tác vụ chuyển giữa queue, database, scheduler và SMTP, phải giữ tenantId nhất quán để không dùng nhầm quota hoặc template.

**Cô lập quota mà không cô lập quyền truy cập dữ liệu là chưa đủ.** Ngược lại, phân quyền đúng nhưng mọi tenant dùng chung một quota không có điều phối cũng có thể gây ảnh hưởng chéo về hiệu năng.

## 3. Các tầng cô lập trong hệ thống mail

Một kiến trúc đa tenant có thể chia thành những lớp:

~~~text
                       APPLICATION
          +----------------+----------------+
          |                |                |
       Tenant A         Tenant B         Tenant C
          |                |                |
          +------- Authenticated API -------+
                           |
                           v
                  Notification Outbox
                 (tenant_id + event_id)
                           |
                           v
                 Quota + Admission Gate
                 /         |          \
            Per tenant  Per stream   Global limits
                 \         |          /
                           |
                           v
                    Fair Scheduler
                           |
                           v
                  Worker / In-flight Gate
                           |
                           v
              SMTP Sender / Provider Router
                 /         |          \
            Provider 1  Provider 2  Dedicated account
                           |
                           v
                      SMTP servers
                           |
                           v
                    Delivery feedback
                           |
                           v
             Per-tenant status and metrics
~~~

Các tầng này giải quyết các mục tiêu khác nhau:

| Tầng | Nhiệm vụ |
|---|---|
| Authorization | Ngăn tenant truy cập hoặc giả danh tài nguyên của tenant khác |
| Admission/quota | Giới hạn số lượng thông báo hoặc tài nguyên được phép sử dụng |
| Scheduler | Phân bổ thời gian xử lý công bằng khi nhiều tenant có việc |
| In-flight gate | Giới hạn số kết nối/gửi đồng thời |
| Sender routing | Chọn SMTP account, domain, credential và provider hợp lệ |
| Retry policy | Không để lỗi của một tenant tạo vòng lặp retry vô hạn |
| Delivery feedback | Ghi nhận bounce, deferred và delivery vào đúng tenant |
| Monitoring | Phát hiện một tenant hoặc provider chiếm tài nguyên bất thường |

Không có **một cấu hình spring.mail duy nhất** tự động giải quyết toàn bộ vấn đề này. **JavaMailSender** cung cấp API gửi mail; việc kiểm soát tenant/quota là trách nhiệm của kiến trúc ứng dụng hoặc dịch vụ điều phối xung quanh nó.

## 4. Những loại quota cần phân biệt

Từ “quota” thường bị dùng cho nhiều giới hạn khác nhau. Chúng không tương đương.

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| **Daily volume** | 50.000 recipient/ngày | Giới hạn tổng lượng gửi theo ngày |
| **Hourly volume** | 5.000 recipient/giờ | Ngăn tenant dồn khối lượng lớn vào một giờ |
| **Rate** | 20 recipient/giây | Giới hạn tốc độ trung bình hoặc burst ngắn |
| **Burst** | Tối đa 100 token tích lũy | Cho phép những đợt gửi ngắn, có giới hạn |
| **Concurrency** | Tối đa 4 SMTP submissions đồng thời | Giới hạn tài nguyên in-flight |
| **Payload bytes** | Tổng 200 MB MIME/ngày | Giới hạn băng thông/dung lượng mail |
| **Per-message size** | Tối đa 10 MB MIME/message | Ngăn một message quá lớn |
| **Recipient count** | Tối đa 50 recipient/message | Hạn chế fan-out và nguy cơ lộ danh sách |
| **Pending backlog** | Tối đa 10.000 job đang chờ | Ngăn queue phình vô hạn |
| **Retry budget** | Tối đa 4 attempts/notification | Chống retry storm |
| **Provider quota** | 100 message/s trên một account | Tránh vượt giới hạn do ESP áp dụng |

Nhiều provider tính quota theo **recipient**, không phải theo lần gọi send. Một MimeMessage gửi đến 5 recipient có thể tiêu thụ 5 đơn vị quota ở provider đó. Ngược lại, một số giới hạn tính theo message hoặc API request. **Phải đọc hợp đồng quota của provider và định nghĩa đơn vị tính trong ứng dụng**; không giả định mọi SMTP server đều dùng cùng quy tắc.

### Quota cứng và mềm

- **Hard quota:** không cho cấp phát thêm khi đã hết ngân sách.
- **Soft quota:** chấp nhận vượt một mức nhất định nhưng tạo cảnh báo hoặc chuyển sang hàng chờ.
- **Burst capacity:** cho phép tốc độ cao trong thời gian ngắn rồi buộc chờ hồi token.
- **Reserved capacity:** giữ một phần năng lực cho stream quan trọng như OTP/security.

Một hệ thống có thể dùng cả bốn, nhưng các trạng thái chấp nhận, hoãn và từ chối phải được mô tả rõ để caller không tưởng rằng thông báo đã gửi khi mới chỉ được đưa vào queue.

## 5. Phân biệt quota theo tenant, stream và provider

Giả sử một tenant có cả email giao dịch và marketing:

~~~text
Tenant A
    |
    +-- transactional: 1.000 recipients/giờ
    +-- security:      500 recipients/giờ
    +-- marketing:   10.000 recipients/ngày
    |
    +-- tổng tenant: 12.000 recipients/ngày

SMTP Provider P
    |
    +-- account-wide: 50 recipients/giây
    +-- 5 SMTP sends đồng thời

Mail service
    |
    +-- global CPU/thread/memory limit
~~~

Một lần gửi chỉ được thực hiện khi thỏa **tất cả những giới hạn áp dụng**, ví dụ:

~~~text
ALLOW_SEND =
    authorizedTenant
    AND tenantDailyBudget
    AND streamBudget
    AND providerRateBudget
    AND tenantConcurrencyAvailable
    AND globalConcurrencyAvailable
    AND messageSizeAllowed
~~~

Không thể dùng quota tenant làm thay cho quota provider: mỗi tenant có thể nằm dưới ngưỡng riêng nhưng tổng tất cả tenant vẫn vượt rate limit của ESP.

### Vì sao cần quota theo stream?

Nếu marketing và security dùng chung đúng một quota cho tenant, một chiến dịch có thể sử dụng hết số lượng gửi, khiến OTP bị trì hoãn. Một lựa chọn là có **ngân sách security riêng** hoặc reserved capacity, nhưng vẫn duy trì giới hạn toàn hệ thống và chính sách chống lạm dụng.

Điều này không có nghĩa email security phải được bỏ qua mọi quota. Thông báo nhạy cảm vẫn cần kiểm soát phát sinh hàng loạt, abuse và expiry.

## 6. Chọn đơn vị quota: message, recipient hay byte?

Ví dụ một email:

~~~text
From: notices@example.com
To:   10 địa chỉ
Cc:    2 địa chỉ
Bcc:   3 địa chỉ
Attachment: 4 MB
~~~

Có thể tính:

| Hệ đo | Mức tiêu thụ của ví dụ |
|---|---:|
| SMTP message count | 1 |
| Recipient count | 15 |
| MIME transfer bytes | Kích thước message sau khi encode, có thể lớn hơn 4 MB |
| SMTP send attempts | 1 ở lần đầu, tăng nếu retry |
| Notification-recipient records | Có thể là 15, tùy model nghiệp vụ |

Nếu quota tenant đặt theo recipient, việc đếm **một lần gọi JavaMailSender.send(...)** là không đủ. Cần tính số recipient thực tế được yêu cầu, tách kết quả thành công/từ chối một phần khi provider trả thông tin tương ứng.

Đối với Bcc, số recipient vẫn cần được tính vào quota. **Ẩn địa chỉ trong header không có nghĩa Bcc được miễn chi phí provider hoặc rate limit**.

### Kích thước MIME khác kích thước file gốc

Attachment thường được mã hóa base64 và có thêm header, boundary, line wrapping. Vì thế **file 4 MB không đồng nghĩa email MIME chỉ 4 MB**. Khi giới hạn kích thước, có thể:

1. Đặt giới hạn kích thước nguồn từ trước khi tạo MIME.
2. Ước lượng kích thước MIME với một biên an toàn.
3. Nếu cần chính xác, đo kích thước sau serialize hoặc theo thông tin provider trước khi submit.

Tránh serialize một email khổng lồ nhiều lần chỉ để kiểm tra quota nếu điều đó gây áp lực bộ nhớ hoặc I/O. Với attachment lớn, cân nhắc object storage và link tải bảo mật thay cho đính kèm trực tiếp.

## 7. Quota admission khác retry throttling

Giả sử một tenant được phép gửi 1.000 notification/ngày. Một notification được gửi ba lần do SMTP 451:

~~~text
Notification N100
  |
  +-- Attempt 1: SMTP 451
  +-- Attempt 2: TCP timeout
  +-- Attempt 3: Accepted
~~~

Có hai cách tính:

- **Business quota:** một notification (hoặc số recipient tương ứng) được tính một lần khi được chấp nhận vào hệ thống hoặc khi submission được xác nhận, tùy hợp đồng sản phẩm.
- **Transport capacity:** ba attempts được tính vào rate/concurrency/tài nguyên SMTP, vì server và worker thực sự đã phải xử lý ba lần.

Nếu trừ **business quota** mỗi lần retry, tenant có thể mất hết ngân sách chỉ vì provider lỗi. Nhưng nếu không giới hạn attempts, một job có thể giữ worker và liên tục gây tải.

Do đó nên tách:

~~~text
Tenant business allowance
      |
      v
Notification accepted once
      |
      v
Outbox
      |
      +-- Retry 1
      +-- Retry 2   -> tất cả chịu transport rate/concurrency
      +-- Retry 3
~~~

Chính sách tính quota phải nêu rõ thời điểm bị trừ, khi nào hoàn trả và thế nào là một notification duy nhất. Nó không nên được quyết định ngẫu nhiên bởi nơi đặt một câu lệnh Counter.increment().

## 8. Khi nào từ chối, khi nào xếp hàng?

Khi tenant gửi vượt tốc độ, có ít nhất ba lựa chọn:

| Trạng thái | Ý nghĩa | Khi phù hợp |
|---|---|---|
| **REJECTED_QUOTA** | Yêu cầu vượt hard quota, không được nhận xử lý | Hết ngân sách hoặc vượt chính sách |
| **DEFERRED_RATE** | Yêu cầu hợp lệ nhưng phải chờ slot/token | Hạn chế tốc độ ngắn hạn |
| **ACCEPTED_QUEUED** | Ý định gửi đã lưu, worker xử lý sau | Gửi bất đồng bộ với SLA |

Ví dụ API trả về:

~~~json
{
  "notificationId": "N-100",
  "status": "ACCEPTED_QUEUED",
  "tenantId": "tenant-A"
}
~~~

**ACCEPTED_QUEUED không đồng nghĩa SMTP SUBMITTED**. Nếu ứng dụng cần trả trạng thái cho UI, nên dùng tên rõ nghĩa và cung cấp API tra cứu trạng thái.

Với giới hạn “quota ngày đã hết”, xếp hàng tới ngày tiếp theo có thể hợp lý với marketing nhưng không hữu ích với OTP sẽ hết hạn sau vài phút. Quyết định phải tính tới **deadline/TTL của notification**.

## 9. Cô lập tenant không đồng nghĩa mỗi tenant phải có SMTP server riêng

Có nhiều mô hình triển khai:

| Mô hình | Đặc điểm | Đánh đổi |
|---|---|---|
| **Shared SMTP account** | Nhiều tenant đi qua cùng credential/account | Chi phí thấp, nhưng quota và reputation gắn với cùng account |
| **Per-tenant SMTP account** | Mỗi tenant có credential/account riêng | Cô lập quota/provider tốt hơn, cấu hình và vận hành phức tạp hơn |
| **Shared provider, dedicated pools** | Cùng ESP nhưng có pool/account/IP/stream riêng theo nhóm | Cân bằng cô lập với chi phí |
| **Multiple ESPs** | Router chọn provider theo tenant/stream | Dự phòng và kiểm soát quota, nhưng phức tạp về bounce, DKIM và đối soát |

**Cô lập logic** có thể ngăn tenant chiếm worker/queue của nhau, nhưng một shared SMTP account vẫn có **giới hạn vật lý và reputation chung**. Không được hứa hẹn “tenant hoàn toàn độc lập” nếu provider giới hạn toàn account.

Khi yêu cầu cô lập mạnh (pháp lý, compliance, reputation, customer-owned domain, quota riêng), mô hình dedicated account hoặc dedicated pool có thể phù hợp hơn.

## 10. Mô hình dữ liệu đa tenant cho email

Một hệ thống nên có những thực thể độc lập:

~~~text
tenant
  id, status, plan, region
     |
     +-- mail_sender_profile
     |     tenant_id, provider_id, verified_from_domain,
     |     secret_ref, tls_policy, active_version
     |
     +-- mail_quota_policy
     |     tenant_id, stream, window, limit_units,
     |     max_inflight, max_message_bytes
     |
     +-- notification_outbox
           tenant_id, notification_id, event_id,
           stream, recipient_ref, status,
           next_attempt_at, expires_at
                    |
                    +-- mail_attempt
                    |     attempt_id, result, provider_id,
                    |     failure_category, created_at
                    |
                    +-- delivery_event
                          provider_event_id, recipient_ref,
                          delivered/bounced/deferred, event_at
~~~

Các khóa và quan hệ quan trọng:

- Mỗi **notification_outbox** cần tenantId rõ ràng và định danh nghiệp vụ ổn định.
- **Idempotency key** nên duy nhất trong phạm vi tenant và loại notification phù hợp, không nhất thiết toàn hệ thống.
- Sender profile và quota policy phải được lấy theo tenantId đã xác thực.
- Retry attempt và delivery event phải liên kết được về notification/recipient thuộc tenant tương ứng.
- Không dùng một mã notification dễ trùng giữa các tenant mà thiếu tenantId trong truy vấn.

Ví dụ ràng buộc duy nhất:

~~~sql
CREATE UNIQUE INDEX uq_notification_intent
ON notification_outbox (
    tenant_id,
    business_event_id,
    notification_kind,
    recipient_key
);
~~~

Đây là SQL minh họa; tên cột và khóa thực tế phụ thuộc cách hệ thống định nghĩa một notification. Mục tiêu là ngăn **cùng một sự kiện nghiệp vụ tạo nhiều ý định gửi** do HTTP retry hoặc event replay.

### Có cần lưu email recipient trong quota record?

Thông thường **không**. Quota chỉ cần tenant, stream, cửa sổ và số lượng đã dùng. Đưa địa chỉ email vào khóa quota sẽ làm tăng dữ liệu nhạy cảm, số hàng và nguy cơ tính sai giới hạn cộng dồn.

## 11. Tenant context trong request và background worker

Trong một HTTP request, ứng dụng có thể lấy tenantId từ security context đã được xác thực. Nhưng **worker** chạy sau, có thể ở process khác, không còn request context.

Không nên:

~~~java
// Anti-pattern: worker bất đồng bộ phụ thuộc vào tenant
// đang nằm trong ThreadLocal của HTTP request trước đó.
String tenantId = TenantContextHolder.getCurrentTenant();
sendOutboxEmail(tenantId);
~~~

Các vấn đề:

- Thread khác không có ThreadLocal đó.
- Thread pool tái sử dụng thread và có thể mang context cũ nếu không xóa.
- Một scheduled job không hề có HTTP request.
- Tenant identity có thể bị thay đổi giữa lúc tạo notification và lúc worker chạy.

Nên lưu tenantId **trong outbox record** tại thời điểm ghi ý định gửi và truyền nó một cách tường minh:

~~~java
public record ClaimedNotification(
        String notificationId,
        String tenantId,
        String stream,
        String recipientRef,
        String businessEventId
) {
}
~~~

Worker truy vấn profile và quota theo **claimed.tenantId()**, sau khi kiểm tra record và quyền xử lý. Nếu hệ thống còn có request security context cho một số bước, đừng để context đó tự override tenantId của outbox.

### Tenant context không phải chỉ có ý nghĩa cho log

TenantId phải là tham số thực sự tham gia:

1. Query lấy notification.
2. Load sender profile.
3. Resolve template và From domain.
4. Reserve business quota.
5. Reserve concurrency/rate capacity.
6. Ghi attempt và delivery status.

Chỉ gắn một tag tenantId vào log mà các query không dùng tenantId vẫn có thể gây **cross-tenant data leak**.

## 12. Chọn sender theo tenant một cách an toàn

**JavaMailSender** là interface. **JavaMailSenderImpl** có thể được cấu hình với SMTP host, port, username, password và các Jakarta Mail properties.

Trong ứng dụng đa tenant có thể thiết kế:

~~~java
public interface TenantMailSenderResolver {
    org.springframework.mail.javamail.JavaMailSender resolve(
            String tenantId,
            String stream
    );
}
~~~

Một kiến trúc:

~~~text
Outbox record (tenantId, stream)
        |
        v
TenantMailSenderResolver
        |
        +-- Load authorized sender profile
        +-- Validate active status and domain
        +-- Resolve secret reference
        +-- Select provider account
        +-- Return configured JavaMailSender
        |
        v
MailService builds MimeMessage
        |
        v
JavaMailSender.send(...)
~~~

Không lấy **providerId**, SMTP host hay credential trực tiếp từ request của tenant nếu tenant không có quyền quản trị chúng. Nếu cho phép khách hàng tự kết nối SMTP server riêng, cần cơ chế xác minh ownership, kiểm soát network egress/SSRF, host allowlist hoặc isolation thích hợp và quản lý secret chặt chẽ.

## 13. Tạo cấu hình sender cho từng tenant

Một profile bất biến có thể mô tả sender:

~~~java
public record SmtpSenderProfile(
        String host,
        int port,
        String username,
        String password,
        String fromAddress,
        String bounceAddress,
        boolean implicitTls,
        boolean requireStartTls
) {
}
~~~

Trong code production, có thể không muốn chứa password trong một record tồn tại lâu trong bộ nhớ; tùy chính sách có thể chỉ giữ **secret reference** và truy xuất credential qua credential provider. Ví dụ dưới đây tập trung vào mapping Jakarta Mail properties:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SenderFactory {

    public JavaMailSender create(SmtpSenderProfile profile) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(profile.host());
        sender.setPort(profile.port());
        sender.setUsername(profile.username());
        sender.setPassword(profile.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");
        props.put("mail.smtp.ssl.checkserveridentity", "true");

        if (profile.implicitTls()) {
            props.put("mail.smtp.ssl.enable", "true");
        } else if (profile.requireStartTls()) {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        } else {
            throw new IllegalArgumentException(
                    "SMTP submission must use approved TLS"
            );
        }

        if (profile.bounceAddress() != null) {
            props.put("mail.smtp.from", profile.bounceAddress());
        }

        return sender;
    }
}
~~~

Ví dụ này thể hiện cách **chọn một chế độ TLS phù hợp với endpoint**. Trong hệ thống thật, phải kiểm tra profile hợp lệ, port được phép, domain và account đã được xác minh; không cho người dùng tự chọn cổng bất kỳ hoặc tắt TLS theo ý muốn.

### Vì sao cần profile bất biến?

Một sender dùng cho tenant A không nên bất ngờ thay host, credential hoặc envelope sender khi một thread khác bắt đầu xử lý tenant B. Dùng cấu hình bất biến hoặc sender được tạo theo phiên bản cấu hình giúp tránh **race condition** và dễ truy vết.

## 14. Không thay đổi JavaMailSenderImpl singleton theo tenant

Một anti-pattern:

~~~java
// Một bean singleton dùng chung cho mọi tenant.
JavaMailSenderImpl sharedSender;

void send(String tenantId, MimeMessage message) {
    sharedSender.setUsername(loadUsername(tenantId));
    sharedSender.setPassword(loadPassword(tenantId));
    sharedSender.getJavaMailProperties().put(
            "mail.smtp.from",
            loadBounceAddress(tenantId)
    );
    sharedSender.send(message);
}
~~~

Khi nhiều request chạy đồng thời:

~~~text
Thread A: set credential của tenant A
Thread B: set credential của tenant B
Thread A: sender.send(...) -> có thể dùng credential B
~~~

Hậu quả không chỉ là gửi sai tài khoản hoặc vượt quota; nó còn có thể gây **rò rỉ thông tin tenant**, sai SPF/DMARC alignment và khó đối soát bounce.

Các hướng thay thế:

- Có **sender riêng theo tenant/profile version**.
- Có **sender factory** tạo object cấu hình đầy đủ trước khi gửi.
- Nếu cache sender, cache theo **tenantId + configVersion** và không sửa thuộc tính có thể thay đổi khi đang gửi.
- Quản lý TTL/eviction và rotation secret rõ ràng.
- Nếu provider hỗ trợ per-message envelope sender, dùng API chính thức thay vì sửa property chung giữa các thread.

**Không coi việc JavaMailSenderImpl có thể được gọi từ nhiều thread là lý do được phép mutate cấu hình của nó trong lúc gửi.**

## 15. Quản lý vòng đời sender và credential rotation

Nếu có hàng nghìn tenant, tạo sẵn một JavaMailSender cho mọi tenant có thể gây tốn bộ nhớ, chi phí secret lookup và khó cập nhật cấu hình. Nhưng tạo lại mọi object/profile cho mỗi notification cũng có thể làm tăng tải database/secret manager.

Một cơ chế hợp lý:

~~~text
Tenant + Stream
       |
       v
Sender registry
       |
       +-- Check active config version
       +-- Cache bounded by size and inactivity
       +-- Resolve secret via controlled credential provider
       +-- Create sender if missing
       |
       v
Configured sender
~~~

Khi credential được đổi:

1. Ghi profile version mới và cập nhật secret.
2. Làm vô hiệu cache key của version cũ.
3. Cho các sends đang chạy theo version cũ hoàn thành hoặc xử lý lỗi theo chính sách.
4. Gửi job mới bằng profile mới.
5. Giám sát lỗi AUTH trong quá trình chuyển đổi.

Tùy môi trường, một số SMTP transport có cơ chế giữ connection hoặc session dài hơn lời gọi send. Cần xem vòng đời transport thực tế khi triển khai cache/pool, không giả định mọi API đang dùng đều tự có connection pool an toàn.

### Không dùng Spring profile làm tenant selector duy nhất

**spring.profiles.active=production** chỉ phân biệt môi trường cấu hình. Nó không đại diện cho hàng nghìn tenant đang chạy trong cùng một process. Tenant routing nên dựa trên dữ liệu đã được xác thực, sender registry và policy ở runtime.

## 16. Cô lập From, Reply-To và Return-Path theo tenant

Ví dụ:

~~~text
Tenant A:
  From:     billing@brand-a.example
  Reply-To: support@brand-a.example
  MAIL FROM: bounces@bounces.brand-a.example

Tenant B:
  From:     billing@brand-b.example
  Reply-To: support@brand-b.example
  MAIL FROM: bounces@bounces.brand-b.example
~~~

Địa chỉ **From** là header hiển thị. **Reply-To** dành cho phản hồi của người dùng. **MAIL FROM** là envelope sender dùng cho reverse-path/bounce routing.

Trong Spring:

~~~java
MimeMessage message = sender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8"
);

helper.setFrom(approvedTenantFrom);
helper.setReplyTo(approvedTenantReplyTo);
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(body, false);

sender.send(message);
~~~

Các giá trị **approvedTenantFrom**, **approvedTenantReplyTo** và **recipient** là dữ liệu đã được ứng dụng xác thực theo quyền tenant. Cấu hình **mail.smtp.from** ở sender có thể yêu cầu envelope sender, nhưng ESP có thể giới hạn hoặc viết lại địa chỉ này.

Nếu các domain từ tenant không có SPF/DKIM/DMARC alignment phù hợp, gửi vẫn có thể bị từ chối hoặc vào Spam dù JavaMailSender không báo lỗi ngay. Vì vậy sender profile phải gắn với trạng thái **domain ownership và DNS verification** theo provider.

## 17. Thiết kế quota window bền vững

Đối với một giới hạn cố định như **5.000 recipients trong một giờ UTC**, có thể lưu số lượng đã dùng theo window:

~~~sql
CREATE TABLE tenant_mail_quota_window (
    tenant_id     VARCHAR(120) NOT NULL,
    stream        VARCHAR(50)  NOT NULL,
    window_start  TIMESTAMP WITH TIME ZONE NOT NULL,
    used_units    BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, stream, window_start),
    CHECK (used_units >= 0)
);
~~~

Ví dụ:

~~~text
tenant_id = tenant-A
stream = marketing
window_start = 2026-11-12 10:00:00 UTC
used_units = 3800
limit_units = 5000
~~~

Nếu cần gửi thêm 1.300 recipients, hệ thống không thể cấp phát toàn bộ vì sẽ vượt **5.100**. Tùy chính sách, có thể từ chối cả batch, chia batch thành những phần được phép, hoặc xếp lịch chờ cửa sổ tiếp theo.

### Thống nhất cách tính cửa sổ

Nếu dùng cửa sổ giờ:

~~~text
10:00:00 UTC <= event time < 11:00:00 UTC
~~~

Mọi application instance phải tính cùng một thời điểm window_start. Dùng đồng hồ nhất quán và chuẩn UTC giúp tránh sai lệch do múi giờ/Daylight Saving Time.

**Fixed window có đặc điểm burst ở ranh giới:** tenant có thể dùng gần hết quota vào 10:59 và tiếp tục dùng đầy quota mới lúc 11:00. Nếu cần điều tiết tốc độ mượt hơn, kết hợp **token bucket/sliding window** hoặc provider rate limiter.

## 18. Cấp phát quota nguyên tử trong PostgreSQL

Một lỗi phổ biến là:

~~~text
Thread A: SELECT used = 4900
Thread B: SELECT used = 4900
Thread A: nếu thêm 100 <= 5000 thì UPDATE used = 5000
Thread B: nếu thêm 100 <= 5000 thì UPDATE used = 5000

Kết quả: hai request đã được cho phép,
          nhưng database chỉ ghi used = 5000.
~~~

Đây là **check-then-act race**. Thay vì đọc rồi ghi riêng, cần một thao tác có điều kiện nguyên tử.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO tenant_mail_quota_window (
    tenant_id,
    stream,
    window_start,
    used_units
)
SELECT
    :tenantId,
    :stream,
    :windowStart,
    :units
WHERE :units > 0
  AND :units <= :limitUnits
ON CONFLICT (tenant_id, stream, window_start)
DO UPDATE
SET used_units =
    tenant_mail_quota_window.used_units + EXCLUDED.used_units
WHERE tenant_mail_quota_window.used_units
      + EXCLUDED.used_units <= :limitUnits
RETURNING used_units;
~~~

Ý nghĩa:

- Nếu chưa có row, tạo row khi số đơn vị yêu cầu hợp lệ và không vượt limit.
- Nếu đã có row, chỉ tăng khi **used + requested <= limit**.
- Nếu không được cấp phát, truy vấn không trả row.
- PostgreSQL xử lý conflict và cập nhật hàng dưới cơ chế concurrency control, tránh hai worker cùng đọc một used value rồi cấp phát trùng.

### Một caveat quan trọng

Limit **:limitUnits** trong ví dụ là giá trị đã được load từ policy và xác minh phù hợp với tenant/stream. Nếu quota plan thay đổi đồng thời, phải định nghĩa policy version và cách xử lý reservation đã có. Không để client truyền một **limitUnits** tùy ý.

Nếu cần kiểm tra **tenant total**, **stream quota** và **daily quota** trong cùng một operation, cần cấp phát các ngân sách liên quan **trong cùng transaction** và rollback nếu bất kỳ mức nào không đạt. Không cấp phát stream trước rồi để tenant total thất bại mà vẫn commit stream usage.

## 19. Quota reservation phải gắn với notification intent

Giả sử ứng dụng:

1. Trừ quota.
2. Process crash trước khi insert outbox.

Tenant đã mất ngân sách nhưng không có notification nào được gửi.

Ngược lại:

1. Insert outbox.
2. Process crash trước khi trừ quota.

Worker có thể gửi một notification chưa được tính vào ngân sách.

Với hard business quota, nên thực hiện **quota reservation và ghi outbox trong một transaction database**, nếu hai dữ liệu nằm cùng kho transactional:

~~~text
BEGIN TRANSACTION
    |
    +-- Kiểm tra idempotency key / notification intent
    |
    +-- Reserve tenant + stream quota
    |
    +-- INSERT notification_outbox
    |      tenant_id, event_id, status=PENDING
    |
COMMIT
~~~

Nếu không đủ quota hoặc insert thất bại, rollback toàn bộ. Nếu cùng request được retry, unique idempotency key giúp trả lại notification đã tạo thay vì trừ ngân sách lần nữa.

Khi có nhiều kho dữ liệu hoặc dịch vụ quota tách rời, không có transaction ACID chung, phải thiết kế **reservation ID, expiry, reconciliation và idempotency** thay vì giả định mọi bước luôn thành công cùng nhau.

## 20. Khi nào hoàn quota, khi nào không?

Quy tắc hoàn trả không nên chỉ dựa vào việc xuất hiện exception.

| Trạng thái | Cách xử lý business quota tham khảo |
|---|---|
| Request bị từ chối trước khi nhận | Không trừ |
| Notification đã được nhận và xếp hàng | Giữ reservation |
| User hủy trước khi SMTP submission | Có thể hoàn theo chính sách |
| Message preparation thất bại vĩnh viễn | Có thể giải phóng reservation sau khi xác nhận chưa gửi |
| SMTP trả từ chối rõ ràng, chưa accepted | Có thể hoàn nếu hợp đồng tính theo accepted |
| Timeout sau DATA, kết quả UNKNOWN | Giữ trạng thái cần đối soát; không hoàn mù |
| SMTP accepted | Tính/commit quota theo hợp đồng |
| Delivery bounce sau acceptance | Thường vẫn tiêu thụ transport/provider capacity; business refund phụ thuộc hợp đồng |

Nếu quota được bán như **số lần cố gắng gửi**, một SMTP failure cũng có thể tiêu thụ ngân sách; nếu quota là **số notification được chấp nhận**, chính sách khác. Điều quan trọng là **định nghĩa rõ và thực hiện nhất quán**.

### Vì sao không hoàn ngay khi timeout?

Nếu SMTP server đã chấp nhận email nhưng phản hồi cuối bị mất, ứng dụng nhận SocketTimeoutException. Hoàn quota ngay và gửi lại có thể khiến provider thực tế nhận hai message trong khi application chỉ đếm một.

Đối với trạng thái **UNKNOWN**, nên tra cứu provider, ghi attempt và quyết định retry hoặc đối soát theo loại notification.

## 21. Fixed window, sliding window và token bucket

Một hệ thống gửi mail thường có hai loại giới hạn cần thuật toán khác nhau:

- **Budget theo kỳ:** tổng số đơn vị được dùng trong một giờ hoặc một ngày.
- **Rate theo thời gian ngắn:** tốc độ SMTP/ESP chấp nhận gửi, ví dụ 20 recipients/giây với burst 40.

Các thuật toán:

| Thuật toán | Ý tưởng | Phù hợp với |
|---|---|---|
| **Fixed window counter** | Đếm theo mốc giờ/ngày cố định | Quota theo kỳ, triển khai đơn giản |
| **Sliding window** | Đếm trong khoảng liên tục tính từ hiện tại | Hạn chế burst qua ranh giới window |
| **Token bucket** | Tích lũy token theo tốc độ, mỗi lần gửi tiêu token | Provider rate limit và burst có kiểm soát |
| **Leaky bucket / paced queue** | Làm phẳng tốc độ xử lý đầu ra | Điều tiết đều các SMTP submissions |
| **Semaphore** | Giới hạn thao tác đồng thời | In-flight SMTP connections/worker load |

**Rate limiter không thay thế concurrency limiter**. Một yêu cầu gửi attachment rất lớn có thể giữ socket lâu dù tốc độ trung bình thấp.

**Concurrency limiter không thay thế rate limiter**. Một worker có thể gửi 100 message rất nhanh khi mỗi message mất 10 ms, dù chỉ cho một message in-flight.

Thông thường cần phối hợp cả hai và thêm ngân sách theo ngày/giờ khi sản phẩm có giới hạn số lượng gửi.

## 22. Token bucket cho một tenant

Với một bucket:

- **capacity**: số token tối đa có thể tích lũy.
- **refill rate**: số token bổ sung mỗi giây.
- **tokens available**: token hiện có, không vượt capacity.
- **cost**: số token mà một thao tác cần, có thể theo recipient count.

Ví dụ:

~~~text
Tenant A
capacity = 30 recipient tokens
refill = 10 tokens / second

t = 0:
  available = 30
  gửi 20 recipients -> remaining 10

t = 1s:
  thêm 10 tokens -> available 20
  gửi 25 recipients -> chưa đủ, phải chờ

t = 2s:
  thêm 10 tokens -> available 30
  gửi 25 recipients -> remaining 5
~~~

Nếu không có traffic trong 10 giây, bucket chỉ tích lũy tối đa **30 tokens**, không phải 100 tokens. **Capacity** là giới hạn burst.

### Công thức minh họa

~~~text
elapsed = max(0, now - lastRefillTime)
tokens = min(capacity, tokens + elapsed * refillRate)

if tokens >= requestedCost:
    tokens = tokens - requestedCost
    ALLOW
else:
    WAIT_OR_REJECT
~~~

Đây là logic khái niệm. Khi dùng nhiều instance, việc đọc/cập nhật tokens phải được thực hiện **nguyên tử trong một nguồn dữ liệu dùng chung** hoặc qua một dịch vụ rate limit có khả năng đảm bảo consistency.

Một **RateLimiter trong bộ nhớ mỗi pod** chỉ giới hạn pod đó. Nếu có 6 pod và mỗi pod cho phép 20 recipients/s, toàn hệ thống có thể phát tới 120 recipients/s dù quota tenant mong muốn là 20.

## 23. Rate limiting phân tán với Redis

Redis thường được dùng để lưu state của token bucket hoặc sliding window vì có thao tác atomic script, TTL và độ trễ thấp. Một thiết kế:

~~~text
Worker A ----------+
Worker B ----------+--> Redis quota state
Worker C ----------+        |
                             +-- tenant:<tenant>:<stream>
                             +-- provider:<provider>:rate
                             +-- global:rate
                                      |
                                      v
                             ALLOW / WAIT
~~~

Các yêu cầu:

1. **Key được namespaced** theo tenant, stream, provider và phiên bản policy phù hợp.
2. **Refill + consume phải nguyên tử**, tránh hai worker cùng tiêu token cuối cùng.
3. Dùng thời gian nhất quán, chẳng hạn clock do rate-limit service quản lý; không để clock lệch giữa instance quyết định refill trái nhau.
4. Đặt TTL hợp lý để không giữ state của tenant không còn hoạt động mãi mãi.
5. Xử lý restart/failover Redis theo mức độ đảm bảo quota yêu cầu.
6. Khi Redis không truy cập được, có **fail-closed** hoặc chế độ degradation đã được phê duyệt; không mặc định cho tất cả tenant gửi không giới hạn.

### Redis nhanh nhưng không đồng nghĩa hard quota tuyệt đối

Nếu hệ thống yêu cầu **giới hạn kinh phí hoặc pháp lý** không được vượt trong mọi trường hợp, một Redis cluster với failover/replication không đồng bộ cần đánh giá kỹ tính bền vững và khả năng thất thoát state. Khi yêu cầu chính xác cao, có thể đặt **hard business quota trong transactional database** và dùng Redis cho **soft operational rate limiting**.

Không dùng Redis key kiểu:

~~~text
quota:customer@example.com
~~~

vì lộ thông tin cá nhân và giới hạn sai ranh giới tenant. Nên dùng tenant ID opaque, stream và các dimension được chuẩn hóa.

## 24. Giới hạn đồng thời bằng semaphore

**JavaMailSender.send(...)** trong mô hình thông thường là một lời gọi **blocking** khi giao tiếp SMTP. Nếu cho phép quá nhiều worker gọi đồng thời, có thể tăng:

- Số socket đang mở.
- Số thread bị giữ chờ network/TLS.
- Áp lực CPU để encode MIME/attachment.
- Bộ nhớ tạm cho nội dung và dữ liệu đính kèm.
- Số kết nối tới provider khiến account bị rate limit.

Trong một JVM, có thể dùng **Semaphore** làm giới hạn cục bộ:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.mail.javamail.JavaMailSender;

public final class InProcessSmtpGate {

    private final Semaphore slots;
    private final JavaMailSender sender;

    public InProcessSmtpGate(
            JavaMailSender sender,
            int maxConcurrentSends
    ) {
        if (maxConcurrentSends < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrentSends must be positive"
            );
        }
        this.sender = sender;
        this.slots = new Semaphore(maxConcurrentSends, true);
    }

    public boolean submit(
            MimeMessage message
    ) throws InterruptedException {

        if (!slots.tryAcquire(200, TimeUnit.MILLISECONDS)) {
            return false;  // caller xếp lịch lại
        }

        try {
            sender.send(message);
            return true;
        } finally {
            slots.release();
        }
    }
}
~~~

Đây là ví dụ minh họa **một gate trong một JVM**, không phải giải pháp toàn bộ đa tenant. Nếu **sender.send(...)** ném MailException, finally vẫn giải phóng permit. Caller phải phân loại lỗi và cập nhật outbox/attempt bên ngoài thay vì hiểu mọi exception là “chưa gửi”.

### Semaphore và scaling

Nếu mỗi pod cho 5 sends đồng thời và có 10 pod, tổng in-flight có thể lên tới **50**. Khi provider chỉ cho 20 kết nối, cần có:

- Một **distributed lease/semaphore** được thiết kế an toàn; hoặc
- Phân bổ slot cứng theo pod dựa trên số replica tối đa; hoặc
- Một tầng SMTP dispatch service có tổng concurrency được kiểm soát.

Với distributed lease, cần TTL, heartbeat và **fencing/ownership token** để worker cũ không tiếp tục ghi trạng thái sau khi mất quyền. TTL hết hạn không đồng nghĩa lời gọi SMTP cũ chắc chắn đã dừng; không thể coi giới hạn kết nối là tuyệt đối nếu worker bị treo và lease đã hết.

## 25. Phân cấp giới hạn in-flight

Một email chỉ nên tiến tới SMTP khi còn năng lực ở các mức liên quan:

~~~text
Global limit: 40 sends in-flight
   |
   +-- Provider P: 20
   |      |
   |      +-- Tenant A: 4
   |      +-- Tenant B: 4
   |      +-- Tenant C: 2
   |
   +-- Provider Q: 20
          |
          +-- Tenant D: 8
          +-- Tenant E: 2
~~~

Ví dụ tenant A còn 2 slot nhưng provider P đã hết slot, tenant A phải chờ. Ngược lại, provider P còn 10 slot nhưng tenant A đã đạt 4, tenant A cũng phải chờ.

### Tránh deadlock khi giữ nhiều slot

Nếu worker A lấy global slot rồi chờ provider slot, trong khi worker B lấy provider slot rồi chờ global slot, hệ thống có thể tạo vòng chờ.

Giải pháp:

- Xác lập **thứ tự lấy tài nguyên thống nhất**.
- Dùng tryAcquire có timeout và nhả các slot đã lấy nếu không đủ slot ở tầng tiếp theo.
- Không giữ quota reservation/DB transaction mở trong lúc chờ mạng lâu.
- Với distributed limits, dùng một service/giao thức reservation thiết kế rõ timeout và rollback.

Không để một tenant giữ global slot nhiều phút chỉ vì đang chờ đến lượt provider rate token. **Rate wait** nên xảy ra trước khi chiếm những tài nguyên in-flight đắt đỏ, hoặc qua scheduler có khả năng đặt lại thời gian chạy.

## 26. Fair scheduling: tránh một tenant chiếm hết hàng đợi

Một hàng đợi FIFO chung có thể gây **head-of-line blocking**:

~~~text
Queue:
  A A A A A A A A A A A A A A A B C

Worker lấy theo FIFO:
  xử lý rất nhiều job A trước khi tới B/C
~~~

Tenant B chỉ có một email OTP nhưng phải đứng sau hàng nghìn email marketing của A.

Một cách cải thiện là giữ các **logical queue theo tenant/stream**, hoặc đánh chỉ số những job đủ điều kiện theo tenant và áp dụng scheduler công bằng:

~~~text
Tenant A:  A1 A2 A3 A4 ...
Tenant B:  B1
Tenant C:  C1 C2
             |
             v
       Fair Scheduler
             |
       A1 -> B1 -> C1 -> A2 -> C2 ...
~~~

Trong thực tế, cần kết hợp:

- Rate/quota của từng tenant.
- Độ ưu tiên theo stream.
- Số job đang chờ.
- Deadline/TTL.
- Số slot provider/global.
- Trạng thái retry và thời gian next_attempt_at.

**Công bằng không có nghĩa mỗi tenant luôn có tốc độ bằng nhau.** Một tenant trả phí cho capacity lớn hơn có thể được cấp trọng số cao hơn, nhưng vẫn cần tránh để tenant nhỏ bị starvation.

## 27. Round-robin và weighted fair queueing

### Round-robin đơn giản

~~~text
Tenant A, B, C cùng có job

Lượt 1: A
Lượt 2: B
Lượt 3: C
Lượt 4: A
...
~~~

Ưu điểm là trực quan. Nhược điểm: một message có 1 recipient và một message có 500 recipients không tiêu thụ tài nguyên như nhau.

### Weighted fair scheduling

Giả sử:

~~~text
Tenant A: weight 4
Tenant B: weight 2
Tenant C: weight 1
~~~

Scheduler có thể cho A nhiều cơ hội phục vụ hơn B/C theo tỷ lệ trọng số khi tất cả đều có backlog, nhưng không được vượt quota tenant/provider.

Trong hệ thống có email size hoặc recipient count rất khác nhau, có thể xem **chi phí một job** bằng số recipient, byte hoặc một cost estimate kết hợp để scheduler không coi mọi job bằng nhau.

Một số thuật toán có thể dùng:

- **Weighted Round Robin** cho job có chi phí gần đồng đều.
- **Deficit Round Robin** khi job có kích thước khác nhau.
- **Weighted Fair Queueing** khi cần phân phối dựa trên trọng số và thời gian chờ.

Không nhất thiết phải triển khai thuật toán phức tạp ngay từ đầu. Có thể bắt đầu với **per-tenant queue + round-robin + giới hạn per-tenant concurrency**, sau đó đo queue wait time trước khi nâng cấp.

## 28. Giữ ưu tiên cho notification quan trọng

Một tenant có thể gửi:

~~~text
security:      OTP, login alert
transactional: receipt, order update
marketing:     campaign, newsletter
~~~

Nếu chỉ dùng một queue, marketing có thể lấn át OTP. Có thể định nghĩa **priority classes**:

| Stream | Đặc điểm | Chiến lược |
|---|---|---|
| **security** | TTL ngắn, chậm là mất giá trị | Reserved capacity, deadline-aware scheduling |
| **transactional** | Gắn với nghiệp vụ, yêu cầu ổn định | Quota ổn định, retry được kiểm soát |
| **marketing** | Thường có batch lớn, dễ defer | Rate cap riêng, fair scheduling, có thể tạm dừng |

Một scheduler chỉ ưu tiên tuyệt đối security vô hạn cũng có thể khiến marketing không bao giờ được phục vụ nếu security stream bị abuse. Nên có **fairness trong cùng lớp** và bảo vệ chống lạm dụng stream priority.

### TTL và deadline

Nếu OTP hết hạn lúc 10:05, một job đến lượt lúc 10:10 không còn ý nghĩa:

~~~text
now > expiresAt  ->  EXPIRED_NOT_SENT
~~~

Nên kiểm tra deadline trước khi chiếm quota/rate token và trước khi gửi. Không dùng cùng retry schedule cho OTP và email hóa đơn nếu business semantics khác nhau.

## 29. Backpressure khi tenant tạo job nhanh hơn khả năng gửi

Một queue không giới hạn chỉ dời vấn đề từ SMTP sang database/queue storage.

Ví dụ:

~~~text
Tenant A tạo: 5.000 jobs/phút
Hệ thống xử lý: 1.000 jobs/phút

Backlog tăng: ~4.000 jobs/phút
Sau 60 phút: ~240.000 jobs chờ
~~~

Các biện pháp:

- Giới hạn **outstanding jobs/tenant** và tổng queue size.
- Trả về trạng thái **throttled/deferred/rejected** có ý nghĩa.
- Cho caller biết **Retry-After** ở tầng HTTP nếu API và chính sách phù hợp; không nhầm với SMTP protocol.
- Giới hạn batch ingestion và kích thước payload.
- Sử dụng deadline/TTL, loại bỏ notification đã hết giá trị theo quy tắc nghiệp vụ.
- Dùng backpressure tới producer hoặc delay campaign scheduling.
- Theo dõi **oldest due age** thay vì chỉ queue depth.

Với hệ thống nhiều tenant, nên bảo đảm **tenant A không thể làm đầy toàn bộ queue storage** khiến tenant B không tạo được thông báo quan trọng.

### API trả về khi vượt quota

Nếu HTTP endpoint trực tiếp từ chối do rate/quota, có thể dùng HTTP 429 cho một chính sách rate limiting, nhưng một số trường hợp hard-plan quota hoặc validation có thể có mã lỗi nghiệp vụ khác.

Ví dụ body:

~~~json
{
  "code": "MAIL_TENANT_RATE_EXCEEDED",
  "status": "DEFERRED_RATE",
  "retryAfterSeconds": 30
}
~~~

Đây là hợp đồng API do ứng dụng định nghĩa, không phải HTTP response mặc định của Spring Mail. Nếu notification đã được nhận vào outbox, thường không nên trả 429 như thể hệ thống chưa nhận; cần trả mã/response thể hiện trạng thái chấp nhận rõ ràng.

## 30. Global quota, provider quota và mức giới hạn thấp nhất

Khi có nhiều tenant, một lần gửi có thể cùng lúc tiêu thụ:

~~~text
Tenant A quota: còn 1.000 recipients/giờ
Tenant A stream security: còn 100 recipients/giờ
Provider P quota: còn 50 recipients/giờ
Global limit: còn 500 recipients/giờ

Request = 80 recipients
~~~

Request vượt số còn lại của **provider P** dù tenant A, stream và global vẫn đủ.

Hệ thống có thể:

1. Defer tới khi provider P có năng lực.
2. Chia batch thành các phần nhỏ hơn nếu contract cho phép và dữ liệu/recipient được xử lý độc lập.
3. Định tuyến sang provider khác đã được phê duyệt, có sender identity và domain verification phù hợp.
4. Từ chối với lý do quota provider nếu không thể đáp ứng SLA.

**Không tự động chuyển sang một SMTP account khác chỉ vì account ban đầu hết quota**. Account dự phòng phải được phép gửi cho tenant, sử dụng domain đã xác minh, có cơ chế bounce và reputation tương ứng.

## 31. Retry budget phải được cô lập theo tenant

Một tenant có thể gặp sự cố email liên tục vì:

- SMTP provider của tenant đó không khả dụng.
- Credential bị thu hồi hoặc hết hạn.
- Domain chưa được xác minh.
- SMTP server trả 421/451 tạm thời.
- Đường mạng của một region bị lỗi.

Nếu worker retry không giới hạn:

~~~text
Tenant A: 2.000 notifications bị lỗi
          mỗi notification retry 20 lần

=> 40.000 attempts tạo áp lực lên worker/SMTP
=> Tenant B/C bị ảnh hưởng mặc dù mail của họ hợp lệ
~~~

Chính sách retry nên đặt giới hạn ở nhiều mức:

| Mức | Ví dụ | Tác dụng |
|---|---|---|
| **Per-notification attempts** | Tối đa 5 lần | Ngăn một job retry vô hạn |
| **Per-tenant retry rate** | Tối đa 10 attempts/s | Ngăn tenant có nhiều job lỗi chiếm SMTP |
| **Provider retry rate** | Giới hạn tổng attempts tới một ESP | Chống retry storm khi ESP gặp sự cố |
| **Max notification age** | Không gửi sau 24 giờ hoặc TTL riêng | Tránh thư quá hạn |
| **Consecutive-failure threshold** | Tạm dừng account có auth lỗi lặp lại | Ngăn cấu hình sai gây tải |
| **Global retry budget** | Giữ năng lực cho job mới hợp lệ | Bảo vệ toàn dịch vụ |

Một notification được retry vẫn tiêu tốn **transport resources** dù business quota có thể đã tính một lần. Nên ưu tiên scheduler phân bổ công bằng cả **new jobs** và **retry jobs**.

### Exponential backoff và jitter

~~~text
baseDelay = min(maxDelay, initialDelay * 2^(attemptNumber - 1))
actualDelay = baseDelay + jitter
~~~

Ví dụ ban đầu 30 giây, multiplier 2, tối đa 30 phút và jitter ngẫu nhiên. Giá trị cụ thể phải được chọn theo đặc tính của từng stream và chính sách ESP.

**Không dùng @Retryable một cách không giới hạn quanh toàn bộ nghiệp vụ** nếu phương thức vừa xử lý thanh toán, vừa tạo outbox rồi gửi email. Retry chỉ nên tác động tới bước có thể thực hiện lại an toàn theo thiết kế.

## 32. UNKNOWN sau SMTP DATA và quota reservation

Giả sử tenant A gửi email:

~~~text
Attempt N100
    |
    +-- SMTP connection OK
    +-- MAIL FROM / RCPT TO OK
    +-- DATA đã truyền
    +-- Mất final reply do socket timeout
    |
    v
Result = UNKNOWN
~~~

Server có thể đã chấp nhận email rồi. Nếu worker lập tức gửi lại, người nhận có thể nhận trùng.

Tại thời điểm này cần:

1. Giữ trạng thái **UNKNOWN** với attempt ID, phase và provider liên quan.
2. Không tùy tiện hoàn **business quota reservation**.
3. Tra cứu provider trace/message ID nếu có.
4. Chọn chính sách **reconcile, manual review hoặc retry có chấp nhận rủi ro duplicate** tùy loại email.
5. Không đưa notification vào vòng retry nóng mỗi lần worker quét queue.
6. Khi có kết quả xác nhận accepted hoặc rejected, cập nhật quota và state theo chính sách.

**Outbox và idempotency key không tự biến SMTP thành exactly-once delivery**. Chúng chủ yếu giúp kiểm soát việc tạo ý định gửi và tránh trùng ở phía ứng dụng. Trường hợp mất phản hồi ở chặng cuối vẫn cần quy trình đối soát.

## 33. Xử lý partial recipients khi một MIME gửi nhiều người

Một MimeMessage có thể có nhiều To/Cc/Bcc. Ở SMTP, các recipient có thể được chấp nhận hoặc từ chối khác nhau.

Ví dụ:

~~~text
Message M100:
  RCPT TO customer-A -> accepted
  RCPT TO customer-B -> rejected
  RCPT TO customer-C -> accepted
~~~

Nếu retry lại cả MimeMessage chỉ vì recipient B lỗi, A và C có thể nhận thêm bản trùng.

Để đơn giản hóa quản lý tenant quota và delivery, có thể chọn:

- **Một notification-recipient cho một email transaction** ở những luồng quan trọng.
- Tạo **batch hợp lệ** nhưng lưu mapping từng recipient và kết quả từng phần.
- Nếu Jakarta Mail ném **SendFailedException** hoặc Spring **MailSendException**, phân tích thông tin recipient/message failures mà implementation thực sự cung cấp.
- Không khẳng định toàn bộ batch failed chỉ vì một exception.

Các provider có cách tính quota khi một số recipient được chấp nhận khác nhau. Cần căn cứ vào hợp đồng của ESP để đối soát số recipient được tính phí, thay vì lấy số lượng địa chỉ trong request làm kết quả cuối chắc chắn.

### Vì sao một recipient/email giúp cô lập?

Nó làm tăng số SMTP messages và overhead, nhưng giúp:

- Đếm quota theo recipient rõ ràng.
- Cá nhân hóa nội dung mà không tiết lộ địa chỉ người khác.
- Quản lý bounce và suppression theo một recipient.
- Retry có mục tiêu, tránh gửi trùng những người đã được chấp nhận.

Đánh đổi throughput cần đo theo provider và khả năng batching. Không có một chiến lược đúng cho mọi loại email.

## 34. Circuit breaker theo tenant/provider

Nếu một SMTP account đang trả lỗi authentication lặp lại, tiếp tục gửi nhiều nghìn job không giúp khôi phục:

~~~text
Tenant A -> Account A -> AUTH rejected
Tenant B -> Account B -> Healthy

Desired:
  Pause/throttle Tenant A account
  Keep Tenant B processing
~~~

Có thể kết hợp **circuit breaker** với rate limiting:

| Trạng thái | Hành vi |
|---|---|
| **CLOSED** | Cho phép gửi bình thường, ghi thống kê lỗi |
| **OPEN** | Không gọi SMTP cho tuyến đang lỗi, tạm hoãn job |
| **HALF_OPEN** | Thử số ít request để xác nhận phục hồi |

Circuit breaker nên có **key** phù hợp:

- **Per tenant account** khi lỗi xuất phát từ credential/config riêng.
- **Per provider endpoint** khi tất cả tenant qua cùng ESP gặp sự cố.
- **Per stream** nếu một loại nội dung bị chặn theo chính sách.

Không nên mở circuit breaker toàn hệ thống chỉ vì một tenant nhập credential sai. Ngược lại, nếu một shared provider bị outage, nên tránh để tất cả tenant cùng retry nóng dù circuit breaker per tenant riêng rẽ.

### Phân loại lỗi trước khi mở breaker

- Lỗi auth/certificate ổn định: cần cảnh báo và sửa cấu hình, không liên tục thăm dò với tần suất cao.
- SMTP 4xx/throttling: backoff theo chính sách, có thể tạm giảm throughput.
- DNS/TCP outage: quan sát phạm vi instance/region/provider.
- Lỗi MIME/template: sửa dữ liệu/code, không mở circuit breaker provider như thể ESP down.

## 35. Failover provider cần bảo toàn tenant identity

Một router có thể có hai ESP:

~~~text
Tenant A
  |
  +-- Primary ESP P
  |
  +-- Secondary ESP Q
~~~

Trước khi chuyển tenant sang Q, cần xác nhận:

1. Q được quyền gửi thay tenant A.
2. Domain From đã được xác minh trên Q.
3. DKIM signing domain và SPF/DMARC alignment phù hợp.
4. Bounce address/webhook của Q có thể đối chiếu đúng tenant/notification.
5. Q còn quota và capacity.
6. Q nằm trong region/jurisdiction mà dữ liệu tenant được phép xử lý.
7. Event và provider message ID từ P/Q không bị gộp nhầm.
8. Lỗi từ P **chắc chắn chưa accepted** hoặc đã được đối soát trước khi replay qua Q.

**Failover không giải quyết được tính exactly-once.** Nếu P đã chấp nhận DATA nhưng phản hồi bị mất, gửi lại qua Q có thể tạo duplicate còn khó đối soát hơn vì hai provider khác nhau.

### Không dùng failover để né chính sách provider

Nếu một provider giới hạn account do spam complaint, reputation hoặc vi phạm chính sách, chuyển toàn bộ traffic sang provider khác để vượt chặn có thể làm trầm trọng vấn đề và vi phạm hợp đồng. Failover phải tuân thủ quy định, consent và nguyên nhân sự cố.

## 36. Bộ điều phối worker cho đa tenant

Một worker lý tưởng chỉ được gọi SMTP sau khi vượt qua các cổng điều kiện:

~~~text
Acquire eligible job
    |
    v
Validate tenant status, stream and deadline
    |
    v
Resolve authorized sender profile
    |
    v
Verify business quota reservation
    |
    v
Check tenant/provider circuit breakers
    |
    v
Reserve short-term rate tokens
    |
    v
Acquire tenant/provider/global in-flight slots
    |
    v
Create MimeMessage from tenant-owned template
    |
    v
JavaMailSender.send(...)
    |
    +-- ACCEPTED --> SUBMITTED
    +-- TRANSIENT --> RETRY_WAIT
    +-- PERMANENT --> FAILED
    +-- AMBIGUOUS --> UNKNOWN
    |
    v
Release slots and persist result
~~~

### Ví dụ skeleton điều phối

~~~java
public final class MultiTenantMailWorker {

    private final SenderProfileResolver profileResolver;
    private final MailCapacityGate capacityGate;
    private final NotificationMessageFactory messageFactory;
    private final MailAttemptService attemptService;

    public MultiTenantMailWorker(
            SenderProfileResolver profileResolver,
            MailCapacityGate capacityGate,
            NotificationMessageFactory messageFactory,
            MailAttemptService attemptService
    ) {
        this.profileResolver = profileResolver;
        this.capacityGate = capacityGate;
        this.messageFactory = messageFactory;
        this.attemptService = attemptService;
    }

    public void process(ClaimedNotification notification) {
        SenderRoute route = profileResolver.resolve(
                notification.tenantId(),
                notification.stream()
        );

        // Admission phải dựa trên quota đã được reserve từ lúc
        // notification được ghi nhận, không trừ trùng mỗi retry.
        if (!capacityGate.tryReserve(notification, route)) {
            attemptService.deferForCapacity(notification);
            return;
        }

        try {
            // createMimeMessage() của sender đã được chọn
            // và tạo nội dung theo tenant/profile hợp lệ.
            attemptService.submit(
                    notification,
                    route,
                    messageFactory
            );
        } finally {
            capacityGate.release(notification, route);
        }
    }
}
~~~

Các kiểu **SenderProfileResolver**, **SenderRoute**, **MailCapacityGate**, **NotificationMessageFactory** và **MailAttemptService** là abstraction của ứng dụng, không phải class mặc định của Spring. Ví dụ minh họa ranh giới trách nhiệm, **không phải implementation hoàn chỉnh để copy chạy production**.

Một triển khai thực cần:

- **Claim token/lease** để worker không ghi đè kết quả của worker khác.
- Ghi attempt trước/sau SMTP theo transaction phù hợp.
- Không giữ database transaction mở trong lúc chờ SMTP.
- Phân loại exception/partial outcomes.
- Release capacity theo ownership token, kể cả khi gặp exception.
- Xử lý lỗi ngay cả khi ghi trạng thái kết quả vào DB thất bại.
- Có timeout và watchdog cho các job PROCESSING bị kẹt.

### Chú ý thứ tự render và reserve

Nếu tạo MIME rất tốn CPU/đọc attachment trước khi có capacity, hàng nghìn job có thể cùng render và gây tải. Nhưng nếu giữ slot SMTP trong lúc render file lớn, provider slots lại bị lãng phí.

Một lựa chọn là tách thành:

~~~text
Validate/prepare cheap metadata
       |
       v
Admission + limited render pool
       |
       v
Render/prepare MIME
       |
       v
Short-lived SMTP capacity reservation
       |
       v
Submit
~~~

Ranh giới cụ thể cần đo thực tế và phụ thuộc attachment strategy. Có thể áp dụng **hai semaphore/pool riêng**: một cho rendering/storage I/O, một cho SMTP submission.

## 37. Spring @Async không phải quota isolation

Spring cho phép chạy tác vụ bất đồng bộ với **@Async** và executor:

~~~java
@Async("mailTaskExecutor")
public void sendLater(NotificationJob job) {
    // ...
}
~~~

Nhưng chỉ thêm @Async không bảo đảm:

- Per-tenant rate limit.
- Công bằng giữa tenant.
- Quota bền vững qua restart.
- Exactly-once hoặc idempotency.
- Không vượt provider account quota.
- Đảm bảo job không mất khi process crash.

Nếu executor queue vô hạn, một tenant gửi nhiều có thể khiến toàn bộ bộ nhớ chứa job tăng. Nếu executor có queue giới hạn, cần có **rejection/backpressure policy** và trạng thái phản hồi rõ.

Với email nghiệp vụ quan trọng, **outbox/queue bền vững** thường là cơ chế điều phối chính. @Async có thể là chi tiết thực thi, không phải nguồn bảo đảm delivery.

## 38. Đừng giữ database transaction trong lúc gửi SMTP

Một đoạn code có vẻ thuận tiện:

~~~java
@Transactional
public void createInvoiceAndSendMail(Invoice invoice) {
    invoiceRepository.save(invoice);
    mailSender.send(...);
}
~~~

nhưng có thể tạo ra hai vấn đề:

**Giữ tài nguyên database quá lâu.** Gửi SMTP bao gồm DNS, TCP, TLS, AUTH và DATA; mỗi bước có thể chậm hoặc timeout. Trong thời gian đó, transaction vẫn mở, làm tăng lock duration và gây áp lực connection pool.

**Không có rollback xuyên hệ thống.** SMTP server có thể đã chấp nhận email nhưng transaction database sau đó rollback. Email không tự bị thu hồi.

Mô hình outbox:

~~~text
BEGIN DB TRANSACTION
  save invoice
  reserve notification quota
  insert tenant-scoped outbox intent
COMMIT
        |
        v
Worker later:
  claim notification
  resolve tenant sender/limits
  send SMTP outside business transaction
  persist result in short DB transaction
~~~

Lưu ý: nếu database transaction của bước đầu chỉ quản lý invoice nhưng quota nằm ở một dịch vụ ngoài, cần có reservation protocol và reconciliation; không có ACID mặc định giữa hai hệ thống.

Nếu SMTP accepted nhưng update trạng thái SUBMITTED thất bại, hãy khôi phục/đối soát kết quả thay vì tự gửi lại vì database báo lỗi.

## 39. Cô lập memory, file attachment và băng thông

Quota theo số message chưa đủ nếu tenant có thể gửi email với attachment lớn:

~~~text
Tenant A: 100 messages, mỗi message 25 MB
Tenant B: 100 messages, mỗi message 10 KB
~~~

Cùng một message count nhưng chi phí CPU, disk, network và bộ nhớ rất khác nhau.

Các điểm cần kiểm soát:

- **Max attachment size** và **max total message MIME size**.
- Số attachment tối đa trong một message.
- Tổng bytes in-flight ở các worker.
- Số file descriptors / InputStreams đang mở.
- Nguồn attachment đã được kiểm soát quyền truy cập theo tenant.
- Giới hạn concurrent download từ object storage.
- Tối đa thời gian render template/đọc stream.
- Kích thước batch trong queue để tránh tải toàn bộ binary vào RAM.

### InputStreamSource và stream có thể đọc lại

**MimeMessageHelper.addAttachment(...)** có thể cần đọc nội dung trong quá trình chuẩn bị/serialize message. Với dữ liệu nằm trong bộ nhớ hoặc filesystem, có thể sử dụng **ByteArrayResource**, **FileSystemResource** hoặc **ClassPathResource** tùy trường hợp.

Nếu dùng một **InputStreamResource** gói một stream chỉ đọc được một lần, quá trình MIME serialization có thể thất bại khi cần mở stream lại. Một attachment source nên cấp được **InputStream mới cho mỗi lần đọc** khi contract yêu cầu.

Với dữ liệu lấy từ object storage, phải kiểm tra tenant ownership và version/snapshot của object. Không cho phép tenant A chỉ định tùy ý đường dẫn object thuộc tenant B.

### Có nên giữ bytes của tất cả attachment trong outbox?

Thường không nên đối với file lớn. Có thể lưu:

~~~text
attachment_reference:
  tenantId: tenant-A
  objectKey: opaque-storage-key
  objectVersion: immutable-version
  declaredContentType: application/pdf
  sizeBytes: ...
~~~

Worker đọc file tại thời điểm gửi bằng quyền truy cập phù hợp. Cần xử lý trường hợp object bị xóa, thay đổi version hoặc quyền truy cập không còn hợp lệ.

## 40. Bảo mật và chống tenant abuse

Cô lập quota là một phần của chống lạm dụng, không phải toàn bộ giải pháp.

Một tenant có thể tìm cách:

- Gửi email tới danh sách recipient rất lớn.
- Trộn recipient của tenant khác trong payload.
- Chọn From domain hoặc SMTP account không thuộc quyền.
- Tạo nhiều notification giống nhau để vượt business quota.
- Dùng hàng loạt request song song để vượt limit nếu cấp phát không nguyên tử.
- Dùng attachment hoặc URL remote cực lớn để làm cạn tài nguyên.
- Đặt priority=security nhằm vượt giới hạn marketing.
- Cố tạo nhiều event UNKNOWN rồi ép retry qua provider dự phòng.

Các rào chắn:

1. **Tenant authorization** độc lập với quota.
2. **Sender/domain ownership verification**.
3. **Idempotency** theo business event và notification purpose.
4. **Atomic quota reservation** trước khi chấp nhận job.
5. **Per-tenant/stream rate và concurrency limits**.
6. **Payload/attachment size limits** và object ownership checks.
7. **Controlled priority mapping**; caller không tự nâng cấp stream.
8. **Authenticated bounce/webhook events** trước khi thay đổi state/suppression.
9. **Audit trail** cho thay đổi quota policy, sender profile và secret rotation.
10. **Circuit breaker** để chặn retry storm của account lỗi.

Không nên xem một client-supplied **tenantId** hoặc một giá trị JWT claim bất kỳ là bằng chứng quyền sử dụng SMTP sender; quyền phải được kiểm tra theo mô hình xác thực của ứng dụng.

### Multi-tenant SMTP là ranh giới dữ liệu nhạy cảm

Header From, To, Cc/Bcc, Subject, attachment filename, bounce address và delivery event có thể chứa thông tin cá nhân. Tất cả cần được liên kết với đúng tenant và bảo vệ khi log, export hoặc xem trên dashboard.

## 41. Metric và dashboard cho hệ thống đa tenant

Nên đo các nhóm:

| Nhóm | Metric logic | Cách diễn giải |
|---|---|---|
| Submission | **mail_attempts_total** | Attempts accepted/failed/unknown |
| Per-tenant quota | **tenant_mail_quota_remaining** | Năng lực business quota còn lại |
| Rate limit | **mail_rate_limit_denied_total** | Số lần không cấp được rate token |
| Concurrency | **mail_inflight_sends** | Số SMTP attempts đang chạy |
| Fairness | **mail_queue_wait_seconds** | Thời gian job đủ điều kiện chờ lượt |
| Outbox | **mail_pending_jobs** | Số notification đang chờ |
| Outbox age | **mail_oldest_due_age_seconds** | Tuổi của job đến hạn lâu nhất |
| Retry | **mail_retry_attempts_total** | Số attempts do retry |
| Delivery | **mail_bounced_notifications_total** | Unique bounced notification-recipient |
| Resource | **mail_attachment_bytes_total** | Bytes được xử lý theo định nghĩa đã chọn |
| Provider | **mail_provider_throttled_total** | Lỗi throttle/rate-limit từ ESP |
| Security | **mail_sender_policy_rejected_total** | Request sai quyền sender/domain |

Nên phân đoạn theo **provider, stream, result, region và error category** thuộc tập hữu hạn.

### Tenant ID trong Prometheus label: cần cân nhắc kỹ

Nếu có 50 tenant, gắn tenantId vào một vài metric có thể còn quản lý được. Nếu có 500.000 tenant, mỗi tổ hợp tenantId/provider/stream/result có thể tạo hàng triệu series.

Các hướng thay thế:

- Dashboard tổng hợp theo provider/stream/region.
- Metrics per-tier hoặc per-plan thay vì per-tenant.
- Hệ thống phân tích/quota database cho truy vấn tenant cụ thể.
- Tracing/logs có tenantId hoặc opaque correlation ID, với quyền truy cập và retention phù hợp.
- Chỉ export metrics cho tenant cần giám sát chuyên biệt theo danh sách có kiểm soát, khi nhu cầu thực tế đòi hỏi.

**Không dùng email người nhận, subject, notification ID hoặc token làm metrics label**. Nếu đưa tenantId vào log, áp dụng kiểm soát tenant-level authorization.

## 42. Phân biệt metric quota với sự thật kế toán

Ví dụ Redis token bucket cho thấy số tokens còn lại, nhưng database có thể đang giữ reservation chưa gửi. Nếu ứng dụng crash:

~~~text
Quota reservation committed
    |
    X process crash trước SMTP send
    |
Metric counter không được flush
    |
Outbox vẫn PENDING
~~~

Điều này có thể làm metric và số liệu kế toán khác nhau.

Nên định nghĩa nguồn sự thật:

| Loại dữ liệu | Nguồn đáng tin cậy điển hình |
|---|---|
| Hard business quota đã reserve/commit | Transactional quota ledger/database |
| Số attempts quan sát ở worker | Micrometer metrics/logs |
| Rate tokens hiện tại | Redis/rate-limit service |
| Notification intent | Outbox database |
| Provider acceptance | SMTP result + provider logs/IDs |
| Delivery/bounce | Provider event/DSN được xác minh |

Metrics nên được dùng để **giám sát và cảnh báo**; nếu cần tính chi phí, xuất hóa đơn hoặc áp dụng hard policy, dựa trên ledger/records bền vững có khả năng đối soát.

### Tính chính xác và time windows

Trong một hệ thống phân tán, application clock, database clock, Redis time và provider timestamp có thể khác nhau. Định nghĩa rõ:

- Khi nào quota window bắt đầu/kết thúc?
- Dùng UTC hay timezone tenant?
- Notification được tính theo **created_at**, **accepted_at** hay **submitted_at**?
- Một retry qua ranh giới ngày có được trừ thêm quota business không?
- Những late provider events có làm điều chỉnh ledger cũ hay chỉ bổ sung trạng thái delivery?

Đối với quota thương mại, hợp đồng hiển thị cho tenant phải phù hợp với thuật toán thật. Không để UI hiển thị “0/1000 đã dùng” chỉ vì metric counter bị reset sau restart.

## 43. Kịch bản kiểm thử quota và fairness

Các unit/integration tests quan trọng:

| Kịch bản | Điều cần chứng minh |
|---|---|
| Tenant A đã hết quota | A bị từ chối/defer theo chính sách; B vẫn hoạt động |
| Hai request đồng thời sát ngưỡng quota | Chỉ số request được phép đúng giới hạn, không cấp phát trùng |
| Ghi quota thành công nhưng insert outbox lỗi | Transaction rollback quota |
| Cùng event được submit hai lần | Không tạo hai notification hoặc trừ quota hai lần |
| Worker retry một notification | Business quota không bị trừ lặp nếu chính sách chỉ tính một lần |
| Rate limiter có nhiều pod | Tổng rate của tenant không vượt theo thiết kế |
| Global limit hết | Các worker không bypass global limiter |
| Tenant A backlog lớn, B một OTP | B không phải chờ toàn bộ hàng của A |
| Credential tenant A sai | Chỉ A bị lỗi/circuit breaker, B dùng sender đúng |
| Sender profile bị đổi trong lúc gửi | In-flight message không dùng nhầm credential của tenant mới |
| Timeout sau DATA | Status UNKNOWN; không hoàn quota/retry mù |
| SMTP batch có partial success | Kết quả và quota được ghi theo recipient phù hợp |
| Attachment thuộc tenant khác | Gửi bị chặn trước SMTP |
| Email vượt max size | Không gửi vào SMTP; lỗi có category phù hợp |
| Job quá expiresAt | Chuyển EXPIRED theo chính sách, không gửi |
| Provider P hết quota, Q còn quota | Chỉ failover nếu tenant/domain/quyền hợp lệ |
| Webhook bounce trùng | Chỉ một delivery transition hợp lệ được ghi |

### Test race condition tại quota boundary

Giả sử limit chỉ còn **10 units** và có **20 threads**, mỗi thread xin 1 unit. Kết quả đúng là **tối đa 10 reservations thành công**, bất kể thứ tự thread.

Không dùng một HashMap trong bộ nhớ làm giả lập rồi kết luận SQL reservation an toàn. Kiểm thử concurrency quota phải chạy với **database và transaction isolation phù hợp với production**, hoặc dùng test container có cùng loại database.

Một bài test có thể:

1. Khởi tạo tenant quota window còn 10 units.
2. Dùng barrier cho 20 requests đến gần đồng thời.
3. Mỗi request gọi reservation service thực.
4. Đếm số responses được phép.
5. Xác nhận database used_units không vượt limit.

### Test fairness cần đo wait time

Nếu enqueue 1.000 job A và 1 job B, xác nhận B được lấy trong một giới hạn số lượt hoặc thời gian hợp lý theo thuật toán scheduler. Không chỉ assert “cuối cùng B cũng chạy” vì B có thể phải chờ hàng giờ.

## 44. Test với SMTP server giả và nhiều tenant

Để kiểm tra integration với Spring Mail, có thể dùng **GreenMail**, **Mailpit**, **MailHog** hoặc SMTP capture server phù hợp.

Test scenario:

~~~text
Tenant A -> profile A -> SMTP test mailbox A
Tenant B -> profile B -> SMTP test mailbox B

Inject:
  A From: tenant-a@example.com
  B From: tenant-b@example.com
  A recipient: customer-a@localhost
  B recipient: customer-b@localhost

Assert:
  A message không có From/To/Bcc của B
  B message không có From/To/Bcc của A
  A quota usage chỉ cập nhật A
  B quota usage chỉ cập nhật B
  provider routing và bounce mapping không bị tráo
~~~

Nếu hai tenant dùng cùng SMTP test server, phải kiểm tra **sender profile/credential** bằng test double hoặc server có hỗ trợ authentication và logging tương ứng. Chỉ nhìn message đến cùng một SMTP inbox chưa đủ chứng minh JavaMailSender đã dùng đúng credential cho mỗi tenant.

### Không cần SMTP thật cho mọi test

- Unit test cho policy/quota arithmetic.
- Database integration test cho atomic reservation và idempotency.
- Concurrency test cho race conditions.
- Scheduler test cho fairness và TTL.
- SMTP integration test cho sender selection và MIME/envelope.
- Provider sandbox test cho custom MAIL FROM/quota webhook nếu được phép.

Đừng chạy tất cả ca kiểm thử qua SMTP production hoặc thật ngoài Internet. Việc đó vừa không ổn định vừa có nguy cơ gửi mail nhầm người.

## 45. Runbook khi một tenant chiếm quá nhiều capacity

Khi dashboard báo queue delay hoặc provider throttling tăng:

**Bước 1 — Xác định tầng nghẽn**

- Tenant daily quota đã hết?
- Stream rate token cạn?
- Provider throttle hoặc connection cap?
- Global JVM thread/memory bị saturation?
- Database outbox claim/poll bị chậm?
- Object storage/attachment rendering bị chậm?

**Bước 2 — Xác định phạm vi**

- Một tenant hay toàn bộ provider?
- Một stream marketing hay cả transactional/security?
- Một region/pod hay tất cả instance?
- Có deploy/quota policy mới không?

**Bước 3 — Kiểm tra ảnh hưởng tenant khác**

- Queue wait của tenant B/C có tăng theo không?
- OTP/security có vượt TTL không?
- Tenant nhỏ có bị starvation?
- Rate limiter dùng chung giữa pod có hoạt động không?

**Bước 4 — Chọn biện pháp**

- Nếu một tenant đang burst: hạ rate/queue theo policy, không tắt toàn bộ service.
- Nếu provider quota cạn: điều tiết tổng throughput, không chỉ giảm per-tenant quota.
- Nếu auth/TLS lỗi ở một account: tạm dừng account đó và sửa cấu hình.
- Nếu attachment lớn gây nghẽn: giảm concurrent render, áp dụng size policy.
- Nếu FIFO gây starvation: dùng fair scheduling và reserved capacity.
- Nếu outbox backlog tăng nhanh: áp dụng backpressure ở producer.

**Bước 5 — Đối soát sau sự cố**

- Có notification nào ở UNKNOWN không?
- Có job quá hạn cần EXPIRED không?
- Quota reservation có bị treo?
- Provider acceptance có khác database result không?
- Có recipient nào nhận duplicate vì retry/failover không?

**Bước 6 — Xác nhận phục hồi**

Theo dõi accepted rate, error categories, retry backlog, oldest due age, concurrency usage và latency của từng stream quan trọng.

## 46. Các ngộ nhận và anti-pattern thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng đúng |
|---|---|---|
| Chỉ dùng một quota gửi chung | Tenant có lưu lượng lớn làm cạn capacity của tenant khác | Per-tenant quota kết hợp provider/global limits |
| Dùng rate limiter trong từng pod | Tổng rate tăng khi scale nhiều replica | Distributed limiter hoặc phân bổ capacity có kiểm soát |
| Dùng Semaphore để giới hạn recipients/s | Semaphore giới hạn concurrent operations, không phải rate theo thời gian | Kết hợp rate limiter và concurrency gate |
| Chỉ có rate limiter, không giới hạn in-flight | Send lâu giữ quá nhiều socket/thread | Thêm concurrency cap |
| Trừ quota trên mọi retry | Provider lỗi khiến tenant hết business budget | Tách business quota và transport attempt budget |
| Không trừ transport budget khi retry | Retry storm chiếm SMTP capacity | Rate/circuit breaker cho retries |
| SELECT rồi UPDATE quota không điều kiện | Race condition làm cấp phát vượt giới hạn | Atomic conditional update/transaction |
| Dùng request tenantId không xác thực | Truy cập sender/quota của tenant khác | Tenant identity từ auth + authorization |
| Gửi qua sender singleton rồi đổi username | Race giữa các tenant, nguy cơ gửi sai credential | Sender profile bất biến và routing an toàn |
| Dùng ThreadLocal tenant context trong worker | Thread pool có thể mất/giữ nhầm context | TenantId tường minh trong outbox |
| Coi email tới một recipient và 100 recipients có cùng chi phí | Vượt recipient quota/provider policies | Định nghĩa đơn vị quota theo hợp đồng |
| Chỉ quản lý số email, bỏ qua attachment | Cạn memory, I/O và băng thông | Giới hạn bytes, size, render concurrency |
| FIFO chung không có fairness | Tenant nhỏ bị starvation | Per-tenant queue/fair scheduling |
| Ưu tiên tuyệt đối không giới hạn cho security | Có thể bị abuse, các stream khác không được phục vụ | Reserved capacity + anti-abuse |
| Không có giới hạn số job PENDING | Queue tăng vô hạn | Backpressure và backlog quota |
| SMTP accepted = email đã tới Inbox | Sai ngữ nghĩa delivery | Tách submission và delivery feedback |
| Timeout sau DATA = chưa gửi | Có thể tạo email trùng | UNKNOWN/reconcile |
| Failover sang provider bất kỳ | Domain/credential/quyền không phù hợp | Approved tenant-provider routing |
| Retry cả batch sau partial failure | Recipient đã thành công nhận trùng | Per-recipient outcome và targeted retry |
| Đưa tenantId/recipient vào mọi metrics label | Cardinality và privacy risk | Metrics tổng hợp + logs/ledger tenant-scoped |
| Cho rằng Micrometer counter là sổ cái quota | Counter có thể reset và không atomic với DB | Durable quota ledger |
| Giữ DB transaction mở trong lúc SMTP send | Lock lâu và không rollback được email | Outbox + transaction ngắn |
| Chỉ kiểm thử trên một instance | Không bắt được race và global oversubscription | Concurrency/distributed integration tests |

## 47. Lộ trình triển khai từng bước

Không phải hệ thống nào cũng cần lập tức xây một quota platform phân tán phức tạp. Có thể triển khai theo mức độ trưởng thành:

### Giai đoạn 1 — Đúng tenant và không gửi nhầm

1. Xác định tenantId tin cậy và kiểm tra quyền ở request/event boundary.
2. Thêm tenantId vào mọi notification, template, sender profile và delivery event.
3. Dùng **From/Reply-To** được kiểm soát và domain đã xác minh.
4. Không mutate sender singleton trong lúc gửi.
5. Dùng fixture/test khác nhau cho từng tenant để phát hiện rò rỉ.

Ở giai đoạn này, mục tiêu số một là **đúng dữ liệu và đúng sender** trước khi tối ưu throughput.

### Giai đoạn 2 — Hard quota và xử lý bền vững

1. Chọn đơn vị quota: recipient, notification, bytes hoặc tổ hợp.
2. Thiết kế bảng policy, reservation và outbox.
3. Dùng **atomic conditional reservation** trong transaction.
4. Có idempotency key cho event replay.
5. Phân biệt rejected, queued, submitted và unknown.
6. Xử lý retry có giới hạn và tránh gửi trùng.

### Giai đoạn 3 — Cô lập hiệu năng

1. Rate limit theo tenant/stream và provider.
2. Concurrency cap theo tenant/provider/global.
3. Fair scheduler hoặc per-tenant queue để tránh starvation.
4. Backpressure khi queue tăng nhanh.
5. Giới hạn attachment bytes và render I/O.
6. Reserved capacity cho luồng quan trọng.

### Giai đoạn 4 — Multi-provider và vận hành

1. Quản lý sender/credential profile version và cache có giới hạn.
2. Phân tuyến provider theo policy/quyền tenant.
3. Có circuit breaker tại đúng scope sự cố.
4. Thu bounce và delivery feedback có tenant correlation.
5. Dashboard theo provider, stream, lỗi, quota và queue wait.
6. Runbook khôi phục reservation, UNKNOWN và partial success.

### Giai đoạn 5 — Scale và tối ưu chi phí

- Phân tích chi phí provider theo recipient/bytes.
- Dùng weighted fairness nếu các tenant có mức dịch vụ khác nhau.
- Tối ưu batch size và connection usage trong giới hạn provider.
- Kiểm tra distributed rate limit khi scale pod.
- Tách compute pool cho MIME rendering và SMTP I/O nếu một bên lấn át bên kia.
- So sánh latency p95/p99, throughput và tài nguyên theo từng loại stream.

Mỗi giai đoạn nên có **test và metric chứng minh kết quả** trước khi tăng concurrency. Tăng thread/pod khi provider quota không đổi có thể chỉ làm tăng số lỗi throttling.

## 48. Bảng kiểm thiết kế cho production

Trước khi chạy hệ thống Spring Mail đa tenant ở lưu lượng lớn, cần trả lời được:

**Danh tính và quyền**

- TenantId đến từ nguồn đáng tin cậy không?
- Worker có mang tenantId qua outbox, queue và retry không?
- Sender profile, domain, template và attachment có được kiểm tra ownership không?
- From, Reply-To và MAIL FROM có thể bị tenant khác override không?

**Quota**

- Quota được tính theo message, recipient, attempt hay bytes?
- Có giới hạn theo tenant, stream, provider và global không?
- Reservation có atomic khi có nhiều thread/pod không?
- Admission và outbox có được ghi bền vững, không mất/quá trừ khi crash không?
- Có định nghĩa hoàn quota và xử lý UNKNOWN không?
- Time window và timezone có thống nhất không?

**Hiệu năng**

- Có limiter cho rate và concurrency riêng biệt không?
- Khi scale pod, tổng rate có còn nằm trong chính sách không?
- Có fair scheduling cho tenant ít traffic không?
- Stream quan trọng có reserved capacity/TTL không?
- Queue có backpressure và giới hạn kích thước không?
- Payload, attachment và download có giới hạn tài nguyên không?

**SMTP và độ tin cậy**

- Sender profile dùng TLS và xác minh hostname đúng không?
- Không mutate credential trên singleton phải không?
- Có timeout hữu hạn cho connection/read/write không?
- Retry có phân loại lỗi và max attempts không?
- Lỗi sau DATA có được ghi UNKNOWN để đối soát không?
- Partial recipient success được xử lý thế nào?
- Provider failover có tuân thủ domain/quyền/region và chống duplicate không?

**Quan sát và kiểm thử**

- Có metric attempts, rate denied, in-flight, backlog age và bounce không?
- Có thể tìm mọi attempt của notification theo tenant và trace ID không?
- Metric labels có tránh high cardinality và PII không?
- Đã test quota boundary bằng concurrent requests và database thật chưa?
- Đã test A không làm chậm B quá SLA chưa?
- Đã test secret rotation, credential lỗi và provider outage chưa?
- Đã test webhook duplicate, queue crash recovery và UNKNOWN chưa?

Một hệ thống không nhất thiết có tất cả các tính năng cao cấp ngay lập tức, nhưng phải biết rõ **giới hạn nào là hard guarantee, giới hạn nào chỉ là best effort** và tenant nào có thể chịu ảnh hưởng khi shared provider gặp sự cố.

## 49. Ghi nhớ

**Xử lý nhiều tenant và cô lập quota trong Spring Framework Mail** là thiết kế bảo vệ cả **danh tính, dữ liệu, ngân sách và năng lực xử lý** của từng tenant. Không có một property trong **spring.mail** hoặc một lời gọi **JavaMailSender.send(...)** nào tự giải quyết toàn bộ bài toán.

Những nguyên tắc cốt lõi:

1. **Tenant identity phải đáng tin cậy** và đi cùng notification qua request, outbox, worker, sender routing và delivery feedback.
2. **Business quota, transport rate và concurrency là ba giới hạn khác nhau**. Một notification retry nhiều lần có thể tiêu thụ nhiều SMTP attempts nhưng chỉ một business intent.
3. **Hard quota phải được cấp phát nguyên tử** và gắn với idempotent outbox reservation. Rate limit phân tán phải xem xét nhiều pod, failover và thời gian tính token.
4. **Fair scheduling, reserved capacity và backpressure** ngăn một tenant lớn làm chậm hoặc làm cạn tài nguyên của tenant khác.
5. **JavaMailSenderImpl không nên bị sửa cấu hình giữa các request của nhiều tenant**. Dùng sender profile được cấp quyền, bất biến theo phiên bản và quản lý credential an toàn.
6. **Retry/partial success/UNKNOWN** cần được xử lý theo notification-recipient và bằng chứng SMTP, tránh gửi trùng hoặc hoàn quota sai.
7. **Provider quotas và reputation có thể vẫn là tài nguyên chung**, kể cả khi đã cô lập logic trong ứng dụng. Khi cần isolation mạnh, chọn account/pool riêng và xác minh domain.
8. **Đo và kiểm thử** đúng đơn vị: quota ledger, attempts, unique notifications, queue wait, bytes, bounce và mức ảnh hưởng tới tenant khác.

**Mục tiêu cuối cùng không chỉ là ngăn một tenant vượt số lượng email được cấp, mà là bảo đảm khi một tenant gửi nhiều hoặc gặp lỗi, những tenant còn lại vẫn được phục vụ theo quyền, quota và SLA đã cam kết.**





