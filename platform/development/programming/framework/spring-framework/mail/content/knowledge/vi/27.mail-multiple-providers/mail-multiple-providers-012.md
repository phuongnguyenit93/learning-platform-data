# Báo cáo nguồn gửi trong observability

Khi một hệ thống Spring Framework Mail gửi email qua **nhiều SMTP provider**, câu hỏi “email này được gửi từ nguồn nào?” có nhiều nghĩa. Email có thể xuất phát từ một dịch vụ nghiệp vụ, sử dụng địa chỉ From của một thương hiệu, được định tuyến tới provider chính rồi chuyển sang provider dự phòng sau lỗi. Nếu chỉ ghi “gửi thành công” hoặc tổng số email, đội vận hành sẽ không biết hệ thống nào tạo tải, nhà cung cấp nào được sử dụng thực tế, lỗi xảy ra ở đâu, hay failover đã ảnh hưởng kết quả gửi như thế nào.

**Báo cáo nguồn gửi trong observability** là thiết kế dữ liệu quan sát có cấu trúc để theo dõi chính xác **nguồn nghiệp vụ**, **nhà cung cấp SMTP**, **account/route**, **lần thử gửi**, **kết quả thực tế phía client** và **trạng thái cuối của mail event**. Mục tiêu là hỗ trợ chẩn đoán, đánh giá độ tin cậy, cân bằng lưu lượng, nhận biết sự cố nhà cung cấp và đối soát retry mà không làm lộ thông tin riêng tư.

Trong bài học này, một email có thể trải qua các bước:

~~~text
Order / Identity / Billing service
                 |
                 v
          Durable mail event
                 |
                 v
           Routing policy
              /       \
             /         \
     Provider A       Provider B
         |                 |
         v                 v
  JavaMailSender A    JavaMailSender B
         |                 |
         +---- attempt ----+
                 |
                 v
       Outcome and telemetry
                 |
                 v
      Outbox / retry / delivery
~~~

Các nguyên tắc:

- Không đánh đồng **nguồn nghiệp vụ**, **provider** và **địa chỉ From**.
- Mỗi **SMTP attempt** phải ghi đúng provider và account được dùng thực sự.
- Phân biệt **route selected**, **send attempted**, **send returned successfully**, **failed** và **unknown outcome**.
- Khi failover, giữ lịch sử cả provider trước và provider sau.
- Tách **attempt metrics** khỏi số **unique mail events**.
- Dùng **metrics cho tổng hợp**, **structured logs cho từng event**, và **traces cho luồng xử lý**.
- Không đưa email người nhận, Subject, body, token, password hoặc event ID vào metric labels.
- Gọi send thành công không chứng minh message đã vào inbox hoặc được đọc.
- Đo lường phải giúp quyết định vận hành, không chỉ tạo nhiều biểu đồ.

## 1. “Nguồn gửi” có thể chỉ những khái niệm nào?

Trong hệ thống đa nhà cung cấp, phải định nghĩa chính xác từng thực thể.

| Khái niệm | Ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| **Logical source** | order-service, identity-service | Nghiệp vụ nào yêu cầu gửi? |
| **Mail kind** | order_confirmation, password_reset | Loại thông báo nào? |
| **Provider identity** | smtp_provider_a, smtp_provider_b | Nhà cung cấp SMTP nào thực hiện? |
| **Transport account** | provider_a_transactional | Account/cấu hình xác thực nào được dùng? |
| **Route role** | primary, backup | Provider giữ vai trò gì khi chọn? |
| **Endpoint/region** | apac_submission | Kết nối được đưa tới vùng nào? |
| **Visible From** | orders@example.org | Người nhận nhìn thấy danh tính nào? |
| **Envelope sender** | Bounce address được provider cấp | MAIL FROM/return path dùng làm gì? |
| **DKIM domain** | d=example.org | Domain ký email là gì? |
| **Outbox worker** | mail-worker-pool | Tiến trình nào thực thi attempt? |

Một logical source có thể gửi qua nhiều SMTP providers. Một provider có thể phục vụ nhiều nguồn nghiệp vụ, nhiều account hoặc nhiều From identities.

### 1.1. From không nhất thiết cho biết provider

~~~text
From: Orders <orders@example.org>
~~~

Message với From như trên có thể được gửi qua cả provider A và provider B nếu hai hệ thống đã được cấu hình và ủy quyền hợp lệ. Không thể xem header From rồi suy ra provider nào đã nhận kết nối SMTP.

Tương tự, **From header**, **MAIL FROM**, SMTP AUTH username và DKIM signing domain có thể khác nhau. Không đặt tất cả vào một trường **sender** mơ hồ.

### 1.2. Nên dùng ít nhất hai trường attribution

- **source_alias**: nguồn nghiệp vụ tạo ý định gửi.
- **provider_alias**: SMTP provider thực sự nhận attempt.

Các trường bổ sung như **account_alias**, **mail_kind**, **route_reason** hoặc **region_alias** chỉ được thêm nếu có câu hỏi vận hành cụ thể.

### 1.3. Provider identity khác route role

Hôm nay provider A là primary, ngày mai có thể chuyển thành backup. Nếu dùng chuỗi **primary** làm provider identity rồi đổi mapping theo thời gian, các biểu đồ lịch sử có thể trộn dữ liệu của hai nhà cung cấp.

Nên có cả **provider_alias ổn định** và **route_role** như primary/backup.

## 2. Vì sao phải theo dõi từng attempt?

Một mail event có thể trải qua:

~~~text
mailEventId = event-1842
source = order-service
kind = order_confirmation
          |
          v
Attempt 1: provider_a
          |
          +-- Read timeout
          |
          v
Evaluate retry/failover policy
          |
          v
Attempt 2: provider_b
          |
          +-- send() returns normally
~~~

Nếu chỉ lưu provider cuối cùng, lỗi của provider A biến mất khỏi lịch sử. Nếu chỉ lưu provider đầu tiên, thành công của provider B bị quy sai.

**Đơn vị đo cơ bản cho SMTP transport là một attempt trên một provider cụ thể.** Mỗi attempt phải liên kết được với mail event gốc.

### 2.1. Event, attempt và recipient không tương đương

- **Mail event** là ý định gửi theo nghiệp vụ.
- **Attempt** là một lần thực thi transport.
- **Recipient** là địa chỉ nhận trong SMTP envelope.
- **Provider selection** là một quyết định route, chưa chắc đã tạo attempt.

Một event có thể có nhiều attempts. Một attempt có thể có nhiều recipients nếu gửi batch/message nhiều người nhận. Vì vậy, không lấy một counter “send” rồi gọi nó là số email duy nhất.

### 2.2. Sử dụng hai định danh riêng

~~~text
mailEventId = mail-1842
attemptId   = mail-1842-attempt-02
provider    = smtp_provider_b
~~~

Event ID phục vụ đối soát nghiệp vụ và retry. Attempt ID phục vụ phân tích một lần gọi. Cả hai có thể dùng trong log/trace có phân quyền, nhưng **không nên làm metric tags** vì cardinality rất cao.

### 2.3. Không xóa attempt lỗi sau khi event thành công

Business event cuối cùng có thể hoàn tất qua backup, nhưng provider A vẫn tạo ra một lần lỗi thật. Thành công cuối không làm thay đổi lịch sử chất lượng của các provider.

## 3. Kiến trúc gửi với nhiều JavaMailSender

Spring cung cấp interface **JavaMailSender** để tạo MimeMessage và gửi qua mail transport. Trong ứng dụng nhiều provider, thường có các bean **JavaMailSenderImpl** với SMTP host, account và security settings riêng.

~~~text
Mail event
    |
    v
MailRouter.select(...)
    |
    +-- RouteDecision(provider A, account A)
    |
    +-- RouteDecision(provider B, account B)
    |
    v
Sender registry
    |
    +-- account A -> JavaMailSenderImpl A
    +-- account B -> JavaMailSenderImpl B
    |
    v
send selected MimeMessage
~~~

### 3.1. Không cấu hình một bean sender rồi đổi host tùy tiện mỗi lần gửi

Sửa thuộc tính trên một JavaMailSenderImpl singleton dùng chung giữa nhiều thread có thể dẫn đến nhầm provider/credential. Tốt hơn là các sender đã được cấu hình độc lập, rồi chọn instance theo registry.

### 3.2. Không lấy SMTP host trực tiếp từ request

Router nên chọn từ **allowlist route/provider/account** được quản lý. Nếu chấp nhận hostname do người dùng cung cấp rồi kết nối, hệ thống có thể tạo nguy cơ SSRF hoặc truy cập hạ tầng ngoài ý muốn.

### 3.3. Có nhiều bean cần thiết kế injection rõ ràng

Khi dự án có nhiều JavaMailSender beans, phải đặt tên, qualifier hoặc inject một registry phù hợp. Spring Boot có thể auto-configure một sender theo điều kiện, nhưng không tự tạo đầy đủ router/failover/metrics theo ý nghĩa đa provider của ứng dụng.

## 4. Quyết định route cần có lý do

Provider được chọn có thể phụ thuộc:

- Loại email: security, transactional, marketing.
- Tenant/branding và From domain được cấp quyền.
- Vùng địa lý.
- Health của provider.
- Quota hoặc rate limit.
- Cost/capacity policy.
- Manual override trong sự cố.
- Khả năng hỗ trợ SMTPUTF8 hoặc giới hạn attachment.
- Chính sách retry sau một lỗi đã phân loại.

Một route decision có thể biểu diễn bằng:

~~~java
public record MailRouteDecision(
        String sourceAlias,
        String providerAlias,
        String accountAlias,
        String fromAddress,
        String routeRole,
        String routeReason,
        String policyVersion
) {}
~~~

### 4.1. routeReason phải là mã ổn định

Ví dụ:

~~~text
tenant_default
kind_policy
region_policy
provider_unhealthy
rate_limit_fallback
capacity_policy
manual_override
failover_after_transient_error
~~~

Không dùng nguyên văn thông báo lỗi hay chuỗi do người dùng nhập làm routeReason.

### 4.2. policyVersion để giải thích lịch sử

Một route được chọn hôm nay có thể khác sau khi policy thay đổi. Lưu **policyVersion** trong structured log hoặc attempt record giúp điều tra quyết định tại thời điểm thực thi, thay vì tra cấu hình hiện tại rồi suy ngược.

### 4.3. Route đã chọn chưa chắc được gọi

Nếu router chọn provider A nhưng factory không tạo được MimeMessage do resource thiếu hoặc địa chỉ không hợp lệ, chưa có SMTP attempt. Cần báo cáo **route selection** khác **send invocation**.

## 5. Phân biệt các mốc observability

Một hệ thống có thể ghi những mốc:

~~~text
MAIL_EVENT_CREATED
        |
        v
ROUTE_SELECTED
        |
        v
MIME_PREPARING
        |
        v
MIME_READY
        |
        v
SMTP_ATTEMPT_STARTED
        |
        +-- SUBMIT_RETURNED_OK
        |
        +-- SUBMIT_FAILED
        |
        +-- UNKNOWN_OUTCOME
        |
        v
OUTBOX_STATE_UPDATED
~~~

Đây là schema trạng thái minh họa, **không phải các enum được Spring Mail tự cung cấp**.

### 5.1. Selected khác attempted

Lỗi validation hoặc render xảy ra sau route selection nhưng trước send. Nếu ghi attempts dựa vào selection, sẽ báo cáo sai số lần transport thực sự được gọi.

### 5.2. Attempted khác accepted

Gọi JavaMailSender.send(...) chưa có nghĩa SMTP server chấp nhận message. Phải ghi kết quả sau khi lời gọi hoàn tất hoặc exception.

### 5.3. Send returned normally khác delivered

JavaMailSender.send trả void khi lời gọi hoàn tất bình thường. Điều đó thường được hiểu là bước submit qua transport đã hoàn tất theo phản hồi SMTP. Nó **không** khẳng định email đã tới inbox, không bị lọc spam hoặc đã được mở.

### 5.4. Exception có thể tạo outcome chưa xác định

Nếu kết nối mất sau DATA, server có thể đã nhận message nhưng response không tới client. Trạng thái **UNKNOWN_OUTCOME** cần được cân nhắc thay vì mặc định “chưa gửi”.

## 6. Ba lớp quan sát bổ sung nhau

| Lớp | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Metrics** | Đếm, tỷ lệ, xu hướng, latency, SLO | Attempts theo provider/outcome |
| **Structured logs** | Điều tra một event/attempt cụ thể | Event ID, attempt ID, route decision |
| **Traces** | Hiểu quan hệ và thời gian các bước | Business → outbox → route → SMTP |

### 6.1. Metrics trả lời câu hỏi tổng hợp

Ví dụ: provider nào có failure ratio cao, p95 submit-call duration ra sao, failover rate tăng chưa.

### 6.2. Logs trả lời ai, khi nào và tại sao

Một structured log có thể nối event với attempt, provider và mã lỗi. Không cần in body email, recipient hay credentials để biết luồng xử lý.

### 6.3. Traces nối các bước đồng bộ và bất đồng bộ

Trong outbox, worker có thể chạy vài phút sau request gốc. Cần propagating trace context hoặc correlation phù hợp; không mặc định trace tự xuyên qua database queue.

## 7. Schema log cho route selection

Ví dụ JSON:

~~~json
{
  "event": "mail.route.selected",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-2",
  "sourceAlias": "order-service",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp_provider_b",
  "accountAlias": "backup_transactional",
  "routeRole": "backup",
  "routeReason": "failover_after_transient_error",
  "policyVersion": "v7"
}
~~~

Các tên trường là convention minh họa; nên chọn một schema nhất quán giữa log, trace, outbox và dashboard.

### 7.1. Không gắn recipient vào route log trừ khi cần

Nếu cần tra cứu recipient, có thể dùng mailEventId rồi truy vấn hệ thống có phân quyền. Email address có thể là dữ liệu cá nhân và làm tăng phạm vi lưu giữ dữ liệu của log collector.

### 7.2. Tách business source và provider

Nếu chỉ có source=order-service mà không có provider, không thể biết SMTP provider nào xử lý. Nếu chỉ có provider mà không có source, khó biết loại traffic nào gây lỗi.

### 7.3. Không log password hay token

Account alias là định danh logic, không phải credential. Secrets phải nằm trong secret manager/runtime configuration, không trong metrics và logs.

## 8. Schema log khi một attempt hoàn tất

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-2",
  "sourceAlias": "order-service",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp_provider_b",
  "accountAlias": "backup_transactional",
  "phase": "smtp_submit",
  "outcome": "success",
  "durationMs": 910,
  "errorCategory": "none"
}
~~~

Một attempt thất bại có thể dùng:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "mail-1842",
  "attemptId": "mail-1842-1",
  "sourceAlias": "order-service",
  "providerAlias": "smtp_provider_a",
  "accountAlias": "primary_transactional",
  "phase": "after_data",
  "outcome": "failure",
  "errorCategory": "timeout_unknown",
  "durationMs": 10025
}
~~~

### 8.1. Cẩn thận với phase

Không phải mọi exception đều cho biết chính xác giai đoạn SMTP. Nếu không có dữ liệu đáng tin cậy, ghi **phase=unknown**, không tự suy diễn after_data chỉ từ thời gian timeout.

### 8.2. Kết quả caller-observed

Đặt **outcome=success** khi send trả bình thường; **outcome=failure** khi ném lỗi. Nếu phân loại kết quả không chắc chắn, lưu **deliveryUncertainty=unknown** hoặc trạng thái outbox **UNKNOWN_OUTCOME** riêng.

### 8.3. Không dùng full exception message làm tag

Diagnostic text từ provider có thể chứa recipient, host, policy hoặc giá trị bất định. Dùng **errorCategory** hữu hạn và SMTP reply/enhanced code đã được xử lý thích hợp.

## 9. Metric cần có cho nhiều provider

| Metric minh họa | Loại | Nhãn hữu ích | Mục đích |
| --- | --- | --- | --- |
| **mail.route.selections** | Counter | source, provider, reason | Đếm quyết định route |
| **mail.smtp.submit.attempts** | Counter | source, provider, outcome | Đếm lời gọi send hoàn tất |
| **mail.smtp.submit.call.duration** | Timer | provider, kind, outcome | Đo latency phía caller |
| **mail.smtp.submit.failures** | Counter | provider, error_category | Phân loại lỗi |
| **mail.smtp.failovers** | Counter | from_provider, to_provider, reason | Đếm chuyển tuyến |
| **mail.message.prepare.failures** | Counter | source, kind, category | Lỗi trước SMTP |
| **mail.outbox.pending** | Gauge | priority/kind | Backlog |
| **mail.outbox.queue.delay** | Timer | source/kind | Độ trễ chờ worker |
| **mail.event.terminal_failures** | Counter | source, kind | Ý định gửi thất bại cuối |
| **mail.event.submit_completed** | Counter | source, final_provider | Event hoàn tất submit |

Các metric này cần **ứng dụng chủ động instrument**. Không giả định chỉ cần thêm Spring Boot Actuator là toàn bộ routing metrics tự xuất hiện.

### 9.1. Đừng gắn mọi nhãn vào mọi metric

Nếu mỗi metric có source, provider, account, tenant, kind, region, reason, outcome, errorCategory thì số time series có thể tăng theo tích các tập giá trị. Chỉ giữ nhãn phục vụ câu hỏi của metric.

### 9.2. Attempts và unique events là hai mẫu số

Một event retry ba lần sẽ có ba attempts. Nếu cần số ý định gửi duy nhất, phải dùng state/outbox hoặc logic đếm riêng, không suy từ attempts.

### 9.3. Health là metric có nghĩa riêng

Một provider “healthy” cần có nguồn đo như probe, rolling error rate hoặc circuit breaker state. Bean JavaMailSender tồn tại không chứng minh endpoint hoặc SMTP AUTH còn hoạt động.

## 10. Cấu hình nhiều JavaMailSenderImpl

Ví dụ cấu hình SMTP STARTTLS với hai sender:

~~~java
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SenderFactory {

    public JavaMailSenderImpl startTlsSender(
            String host,
            int port,
            String username,
            String password
    ) {
        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(props);

        return sender;
    }
}
~~~

Ứng dụng tạo các instance độc lập từ cấu hình và secret đã được cấp:

~~~java
JavaMailSender senderA =
        factory.startTlsSender(
                primaryHost,
                primaryPort,
                primaryUsername,
                primaryPassword
        );

JavaMailSender senderB =
        factory.startTlsSender(
                backupHost,
                backupPort,
                backupUsername,
                backupPassword
        );
~~~

Biến primaryHost, primaryPort, username/password là dữ liệu cấu hình runtime, không phải giá trị để hard-code trong source.

### 10.1. Provider implicit TLS cần mode tương ứng

Ví dụ trên dành cho một endpoint STARTTLS. Nếu provider dùng implicit TLS trên cổng submission phù hợp (thường 465), phải dùng **mail.smtp.ssl.enable=true** và cấu hình mode đúng. Không bật đồng thời các mode tùy tiện.

### 10.2. Tạo registry có account alias rõ ràng

~~~java
Map<String, JavaMailSender> sendersByAccount =
        Map.of(
                "primary_transactional", senderA,
                "backup_transactional", senderB
        );
~~~

Router trả về account alias, rồi adapter tra sender tương ứng. Mapping phải do hệ thống quản lý, không lấy account tùy ý từ request.

### 10.3. Tên account nên ổn định

Một provider có thể có nhiều account, ví dụ transactional/security/marketing. Lỗi AUTH ở một account không chứng minh toàn provider gặp sự cố.

## 11. DTO gửi mail và route decision

Định nghĩa dữ liệu:

~~~java
public record OutboundMailJob(
        String mailEventId,
        String sourceAlias,
        String mailKind,
        String recipient,
        String subject,
        String plainText
) {}

public record MailRouteDecision(
        String sourceAlias,
        String providerAlias,
        String accountAlias,
        String fromAddress,
        String routeReason
) {}
~~~

**mailEventId** thuộc về một ý định gửi. **MailRouteDecision** thuộc về quyết định tại một attempt. Không gắn provider từ lúc tạo event nếu provider có thể thay đổi do retry/failover.

### 11.1. From phải là cấu hình đã được cho phép

Một request bất kỳ không nên được quyền chỉ định From domain và SMTP account tùy ý. Router/validation cần bảo đảm route đã được ủy quyền gửi thay identity đó.

### 11.2. Không truyền toàn DTO vào logger

OutboundMailJob chứa recipient, Subject và text. Không log nguyên object vì nó có thể làm lộ dữ liệu nghiệp vụ.

### 11.3. Một event có thể dùng cùng content snapshot nhiều lần

Với outbox, dữ liệu gửi nên có chính sách snapshot. Retry sang provider khác không nhất thiết phải render lại template nếu content còn hợp lệ.

## 12. Adapter gửi và ghi đúng provider attribution

Một adapter minh họa dùng **MeterRegistry** và JavaMailSender cho attempt:

~~~java
import java.util.Map;
import java.util.Objects;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MultiProviderMailSubmitter {

    private static final Logger log =
            LoggerFactory.getLogger(
                    MultiProviderMailSubmitter.class
            );

    private final Map<String, JavaMailSender> senders;
    private final MeterRegistry registry;

    public MultiProviderMailSubmitter(
            Map<String, JavaMailSender> senders,
            MeterRegistry registry
    ) {
        this.senders = Map.copyOf(senders);
        this.registry = Objects.requireNonNull(registry);
    }

    public void submit(
            OutboundMailJob job,
            MailRouteDecision route,
            String attemptId
    ) {
        JavaMailSender sender =
                senders.get(route.accountAlias());

        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unknown SMTP account alias"
            );
        }

        MimeMessage message =
                sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom(route.fromAddress());
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());
            helper.setText(job.plainText(), false);

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare mail message",
                    ex
            );
        }

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "source", route.sourceAlias(),
                            "provider", route.providerAlias(),
                            "account", route.accountAlias(),
                            "outcome", outcome
                    )
            );

            registry.counter(
                    "mail.smtp.submit.attempts",
                    "source", route.sourceAlias(),
                    "provider", route.providerAlias(),
                    "account", route.accountAlias(),
                    "outcome", outcome
            ).increment();

            log.info(
                    "mail.smtp.attempt.finished eventId={} attemptId={} "
                  + "source={} provider={} account={} outcome={}",
                    job.mailEventId(),
                    attemptId,
                    route.sourceAlias(),
                    route.providerAlias(),
                    route.accountAlias(),
                    outcome
            );
        }
    }
}
~~~

### 12.1. Vị trí instrument là quan trọng

- Sender được chọn bằng account alias trong route.
- MIME được tạo bởi sender đó.
- Timer bắt đầu ngay trước send.
- Counter tăng khi send trả về hoặc ném exception.
- Provider được gắn trên metric là **provider của sender thật**.
- Trước khi send, lỗi prepare không bị tính như một SMTP attempt.

### 12.2. Log và metric phục vụ hai mục tiêu khác

Structured log có **eventId/attemptId** để tra một lần gửi. Metric chỉ dùng alias hữu hạn và outcome để tổng hợp. Không thêm eventId vào registry.timer hay counter.

### 12.3. Đo result chưa phải phân loại cause

Adapter chỉ ghi **success/failure** phía caller. Tầng điều phối cần kiểm tra exception chain, SMTP reply, phase và unknown outcome để quyết định retry/failover. Không khẳng định catch RuntimeException có thể xác định chính xác relay có nhận thư hay chưa.

### 12.4. Cẩn thận với lỗi runtime khi render/prepare

Nếu helper ném lỗi chuẩn bị trước sample timer, không có SMTP attempt. Đây là hành vi mong muốn nếu metric được định nghĩa là số lần gọi send. Nên có metric prepare failures riêng.

### 12.5. Không thay thế transaction/outbox

Adapter không tự persist event state, retry hay chống duplicate. Những trách nhiệm đó thuộc service điều phối/outbox.

## 13. Metric cho route selection

Một router có thể ghi:

~~~java
MailRouteDecision decision =
        router.choose(
                job.sourceAlias(),
                job.mailKind()
        );

registry.counter(
        "mail.route.selections",
        "source", decision.sourceAlias(),
        "provider", decision.providerAlias(),
        "reason", decision.routeReason()
).increment();
~~~

**router** là thành phần do ứng dụng xây dựng.

### 13.1. Route selection count khác attempt count

- Router chọn provider nhưng validation lỗi → selection tăng, attempt không tăng.
- Worker bị dừng trước khi gọi send → có thể đã selected nhưng chưa attempted.
- Retry chọn lại route → một event tạo thêm selection.
- Một batch gửi nhiều message → số lời gọi send và event có thể khác.

Không ép hai counter luôn bằng nhau.

### 13.2. Không dùng selected provider làm final provider

Nếu failover, selected provider ở attempt đầu có thể khác provider cuối cùng. Lưu lịch sử decisions thay vì một field bị ghi đè.

### 13.3. routeReason phải đến từ allowlist

Nếu reason là exception.getMessage(), metrics sẽ chứa vô số giá trị và có thể lộ thông tin. Dùng taxonomy nhỏ và log cause chi tiết qua kênh có quyền hạn chế.

## 14. Attribution khi failover

Giả sử:

~~~text
mailEventId=mail-1842

Attempt #1
  source=order-service
  provider=smtp_provider_a
  account=primary_transactional
  result=failure
  category=temporary_smtp

Attempt #2
  source=order-service
  provider=smtp_provider_b
  account=backup_transactional
  routeReason=failover_after_transient_error
  result=success
~~~

Các số đếm:

~~~text
SMTP attempts provider A, failure: +1
SMTP attempts provider B, success: +1
Failover A -> B: +1
Unique mail event submit completed: +1
~~~

### 14.1. Không cộng hai successes

Thành công cuối của B không khiến attempt lỗi của A thành công. Báo cáo provider quality dựa trên thực tế từng attempt.

### 14.2. Đừng đánh mất provider ban đầu

Nếu outbox chỉ có lastProviderAlias, có thể dùng thêm bảng attempts hoặc structured logs bền vững để giữ lịch sử. Trường lastProviderAlias hữu ích cho trạng thái mới nhất nhưng không đủ cho phân tích lỗi đã xảy ra.

### 14.3. Ghi reason của failover

Các mã ví dụ:

~~~text
connection_failure
provider_unhealthy
rate_limit
timeout_before_data
manual_override
quota_exhaustion
~~~

Đây là reason codes ứng dụng tự định nghĩa. Không tự cho phép failover chỉ vì category có tên timeout; phải đánh giá phase và nguy cơ duplicate.

## 15. Unknown outcome sau DATA

Một trường hợp nguy hiểm:

~~~text
Client                           SMTP relay
  |--- MAIL FROM -------------------->|
  |<-- 250 ---------------------------|
  |--- RCPT TO ---------------------->|
  |<-- 250 ---------------------------|
  |--- DATA / message bytes -------->|
  |       connection lost            |
  |      final reply unknown         |
~~~

Relay có thể đã nhận message nhưng client không thấy response. Nếu tự động đổi sang provider B và gửi lại, người nhận có thể nhận **hai thư giống nhau**.

### 15.1. Không mặc định failure là unsent

Một exception chỉ cho biết lời gọi sender không hoàn tất bình thường. Nó không chứng minh chắc chắn server đã không accept.

### 15.2. Trạng thái outbox cần phản ánh độ chắc chắn

Có thể dùng **UNKNOWN_OUTCOME** hoặc một flag riêng cho attempt có nguy cơ đã gửi. Cần đối soát hoặc áp dụng policy retry thận trọng.

### 15.3. Metric riêng cho unknown outcome

Một counter minh họa:

~~~text
mail.smtp.submit.unknown_outcomes{
  provider="smtp_provider_a"
}
~~~

Không chỉ gộp toàn bộ vào failure rate rồi quyết định failover mù.

### 15.4. Exactly-once không được đảm bảo bởi cache hoặc outbox

Outbox giữ ý định gửi bền vững và có thể quản lý idempotency nghiệp vụ, nhưng SMTP send và cập nhật database không nằm trong một transaction nguyên tử. Có cửa sổ gửi trùng.

## 16. Lỗi nào phù hợp để route sang backup?

| Nhóm lỗi | Ví dụ | Failover tự động? |
| --- | --- | --- |
| **Connection failure** | Provider unreachable | Có thể, sau khi đánh giá kết quả chưa gửi |
| **TLS configuration** | Certificate không khớp hostname | Dừng/sửa cấu hình; không bypass TLS |
| **AUTH 535** | Credentials/account sai | Xử lý account; backup chỉ nếu đã được ủy quyền |
| **SMTP 421/450** | Tạm thời không sẵn sàng | Có thể với backoff/policy |
| **Rate limit** | Quota/throttle | Có thể điều tiết hoặc chuyển có kiểm soát |
| **Invalid recipient** | Mailbox không tồn tại | Thường không có ích chuyển provider |
| **From not authorized** | Sender identity chưa được cấp quyền | Sửa domain/account authorization |
| **Policy/content rejection** | Content bị từ chối | Không chuyển chỉ để né chính sách |
| **Timeout after DATA** | Outcome không rõ | Cần xử lý duplicate risk |
| **Missing attachment** | Lỗi chuẩn bị nội dung | Không phải lỗi provider |

### 16.1. Không quy mọi lỗi SMTP 5xx thành provider down

Mã 550 có thể phản ánh recipient không tồn tại hoặc sender policy. Phải xem SMTP enhanced status và ngữ cảnh provider trước khi đánh giá health.

### 16.2. Đừng đổi provider để tránh policy

Failover không phải cách vượt qua chính sách chống spam, sender verification hoặc bảo mật. Route dự phòng cần được cấu hình hợp lệ cho đúng From domain, loại email và tenant.

### 16.3. Retry và failover khác nhau

Retry có thể dùng lại cùng provider sau backoff. Failover là chuyển sang provider khác. Observability nên tách **retry_count** và **failover_count**.

## 17. Phân loại lỗi theo SMTP phase và category

Taxonomy có thể gồm:

~~~text
prepare_invalid_address
prepare_missing_resource
connect
tls
auth
rate_limit
temporary_smtp
permanent_smtp
recipient_rejected
timeout_unknown
unexpected
~~~

### 17.1. Exception ngoài cùng chưa đủ

Spring có thể bọc Jakarta Mail MessagingException hoặc SendFailedException vào các MailException. Để phân loại đáng tin cậy, cần kiểm tra cause chain, nested exceptions và mã lỗi có cấu trúc từ SMTP provider.

### 17.2. Không phỏng đoán phase

Nếu không có đủ dữ liệu để biết lỗi trước hay sau DATA, dùng **phase=unknown**. Không gán **after_data** chỉ vì timeout kéo dài.

### 17.3. Chỉ log mã lỗi cần thiết

SMTP reply code như 421, 535, 550 và enhanced status giúp chẩn đoán. Tuy nhiên raw reply text có thể chứa người nhận, account hoặc domain nội bộ, nên không mặc định đưa vào mọi log/metric.

## 18. Partial-recipient failure làm attribution phức tạp

Một message có thể gửi cho nhiều recipients:

~~~text
RCPT TO alice@example.net -> accepted
RCPT TO bob@example.net   -> rejected
RCPT TO carol@example.net -> accepted
~~~

Tùy cấu hình provider/Jakarta Mail, có thể có thông tin partial acceptance và SendFailedException chứa nhóm địa chỉ hợp lệ/không hợp lệ.

### 18.1. One attempt không tương đương one recipient

Nếu chỉ ghi attempt failure, không biết recipients nào đã được relay chấp nhận. Nếu nghiệp vụ cần đối soát từng người, phải lưu recipient-level state trong hệ thống có quyền hạn chế.

### 18.2. Tránh retry toàn bộ nhóm

Gửi lại toàn bộ recipients qua provider B sau một partial failure có thể tạo duplicate cho những người đã được accept. Cần xác định chính xác nhóm nào cần retry.

### 18.3. Với email cá nhân hóa, cân nhắc một event/recipient

Một message mỗi recipient thường dễ kiểm soát privacy, retry và attribution hơn. Trade-off là overhead kết nối/transport và quota; phải đo và thiết kế theo nhu cầu.

## 19. Báo cáo hiệu năng theo provider

Một **Timer** bao ngoài JavaMailSender.send đo latency từ lúc caller bắt đầu gửi tới khi trả về/exception:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    selectedSender.send(message);
} finally {
    sample.stop(
            registry.timer(
                    "mail.smtp.submit.call.duration",
                    "provider", selectedProviderAlias
            )
    );
}
~~~

### 19.1. Tên submit-call phản ánh đúng scope

Lời gọi send có thể gồm DNS, TCP connect, TLS handshake, SMTP AUTH, MIME serialization, attachment I/O, DATA transfer và server reply. Nó không đơn thuần là thời gian server xử lý một request.

### 19.2. Không gán mọi latency cao cho provider

Nếu provider B nhận chủ yếu message có PDF lớn, send duration có thể cao do số byte phải truyền và lazy resource read. Nên phân nhóm mail kind/size bucket và đo resource loading nếu cần.

### 19.3. Đo theo outcome

Timer failure timeout có thể lâu hơn nhiều successful sends. Một p95 trộn hai nhóm có thể gây hiểu nhầm. Theo dõi p95/p99 cùng success rate và error categories.

### 19.4. Đo queue delay riêng

Nếu outbox chờ 10 phút trước khi worker gửi trong 300 ms, vấn đề nằm ở queue/scheduling hoặc retry policy, không phải SMTP call chậm 10 phút.

## 20. Kiểm soát metric cardinality

| Tag | Giá trị ví dụ | Có nên dùng? |
| --- | --- | --- |
| **source** | order-service | Có, nếu ít giá trị |
| **provider** | smtp_provider_a | Có |
| **kind** | order_confirmation | Có, nếu allowlist |
| **outcome** | success/failure | Có |
| **error_category** | auth/tls/timeout | Có |
| **route_role** | primary/backup | Có điều kiện |
| **account_alias** | primary_transactional | Có điều kiện |
| **region** | apac | Có điều kiện |
| **tenant_id** | tenant UUID | Thường không nếu nhiều tenant |
| **mail_event_id** | unique UUID | Không |
| **attempt_id** | unique UUID | Không |
| **recipient** | user@example.net | Không |
| **subject** | nội dung tùy ý | Không |

### 20.1. Số series tăng theo tổ hợp tags

Chẳng hạn 5 sources × 3 providers × 8 mail kinds × 3 outcomes × 7 error categories tạo ra nhiều series khả dĩ trước khi tính region/account.

Không đặt mọi chiều vào mọi metric. Một counter failover có thể chỉ cần from_provider, to_provider, reason; Timer latency chỉ cần provider, kind và outcome.

### 20.2. Account alias có thể rất lớn trong SaaS

Nếu mỗi tenant có SMTP account riêng, account alias không còn tập nhỏ. Khi đó, metrics nên tổng hợp ở provider/account tier, còn tra cứu account cụ thể qua log hoặc bảng vận hành có phân quyền.

### 20.3. Không dùng host tùy ý làm provider label

Provider alias nên lấy từ registry cố định. Raw hostname có thể thay đổi nhiều, hoặc lộ thông tin hạ tầng.

## 21. Structured logs cần bảo mật

Một log đủ để chẩn đoán:

~~~text
eventId=mail-1842
attemptId=mail-1842-2
source=order-service
provider=smtp_provider_b
account=backup_transactional
routeReason=failover
phase=smtp_submit
outcome=success
durationMs=910
~~~

Những dữ liệu không nên xuất rộng:

- SMTP password, OAuth token, AUTH payload.
- Địa chỉ email người nhận không cần thiết.
- Subject/body/HTML đầy đủ.
- Attachment bytes.
- Link reset password, OTP, signed URL.
- Raw MimeMessage.
- Thông tin provider reply không được sanitize.

### 21.1. SMTP debug không phải lựa chọn mặc định

Jakarta Mail **mail.debug** có thể xuất protocol transcript. Dữ liệu xuất có thể gồm envelope sender/recipient, SMTP replies và metadata. Một số debug mode liên quan AUTH có rủi ro nghiêm trọng hơn. Không bật debug thường trực chỉ để lấy provider metrics.

### 21.2. TLS không bảo vệ dữ liệu đã ghi log

STARTTLS/implicit TLS bảo vệ kết nối ứng dụng–SMTP server. Nó không tự mã hóa hoặc giới hạn quyền đọc stdout, file log, collector hay trace backend.

### 21.3. Đối soát bằng eventId vẫn cần permission

Event ID có thể liên kết tới người dùng hoặc đơn hàng qua database khác. Audit, retention, access control và chính sách export vẫn cần áp dụng.

## 22. Tracing luồng gửi và failover

Một trace minh họa:

~~~text
business.order.confirm
       |
       v
outbox.enqueue
       |
       v
mail.worker.process
       |
       +-- mail.route.select
       |      provider=smtp_provider_a
       |
       +-- mail.mime.prepare
       |
       +-- mail.smtp.submit
       |      provider=smtp_provider_a
       |      outcome=failure
       |
       +-- mail.route.select
       |      provider=smtp_provider_b
       |
       +-- mail.smtp.submit
              provider=smtp_provider_b
              outcome=success
~~~

### 22.1. Một span cho mỗi attempt

Mỗi SMTP attempt nên có span hoặc log event riêng. Nếu gộp các attempts vào một span chỉ có provider cuối, mất khả năng phân tích latency và lỗi provider đầu.

### 22.2. Thuộc tính đặt tên rõ nghĩa

Có thể dùng custom attributes như **mail.source_alias**, **mail.provider_alias**, **mail.account_alias**, **mail.route_reason**, **mail.submit.outcome**. Đây là convention ứng dụng, không mặc định là semantic attributes chuẩn của OpenTelemetry.

### 22.3. Async/outbox cần correlation thích hợp

Worker có thể chạy sau request hàng phút. Trace context có thể được truyền an toàn trong event, hoặc dùng span links và business correlation ID. Không dựa vào một trace ID làm business identifier bền vững duy nhất.

### 22.4. High-cardinality trace attributes vẫn có rủi ro

Không đưa token, recipient hay nội dung email vào trace chỉ vì nó không giống metric labels. Dữ liệu vẫn được backend lưu và chia sẻ theo quyền truy cập.

## 23. Outbox lưu provider attempt history

Một schema khái niệm:

~~~text
mail_outbox
  mail_event_id
  source_alias
  mail_kind
  payload_reference
  status
  created_at
  next_attempt_at
  attempts
  last_provider_alias

mail_attempt
  attempt_id
  mail_event_id
  attempt_number
  provider_alias
  account_alias
  route_reason
  policy_version
  started_at
  finished_at
  outcome
  error_category
  smtp_reply_code
  elapsed_ms
~~~

Đây là model ứng dụng, không phải schema được Spring Mail tự tạo.

### 23.1. Last provider không đủ cho lịch sử

Outbox có thể lưu lastProviderAlias cho truy vấn nhanh, nhưng cần thêm attempt history hoặc structured logs để biết thất bại trước đó thuộc provider nào.

### 23.2. Tránh ghi full MIME vào bảng telemetry

Nếu workflow cần lưu nội dung đã render để retry, lưu trong storage có chính sách riêng về truy cập/retention. Không biến mail_attempt thành nơi sao chép body, token và attachment.

### 23.3. Trạng thái bền vững và metrics có thể khác nhau

Worker có thể cập nhật metric rồi crash trước khi commit trạng thái, hoặc ngược lại. Metrics dùng để quan sát xu hướng, còn nguồn sự thật cho xử lý nghiệp vụ thường là durable state của outbox.

## 24. Tỷ lệ thành công: chọn mẫu số đúng

Một định nghĩa:

\[
\text{Attempt success rate}
=
\frac{\text{Attempts mà send trả bình thường}}
{\text{Tổng completed attempts có outcome}}
\]

Nhưng phải quyết định **UNKNOWN_OUTCOME** được tính như thế nào. Nếu loại khỏi mẫu số, cần hiển thị count unknown riêng để không che giấu rủi ro.

### 24.1. Success rate của provider A không được dùng final business result

Một event được backup hoàn tất có thể đóng góp business success nhưng vẫn chứa failure của provider A. Đánh giá provider cần dựa vào attempts gắn với provider đó.

### 24.2. Mail event success rate là phép đo khác

Một mail event có thể retry qua ba provider rồi cuối cùng thành công. Tỷ lệ event completed dựa trên **unique events**, không dựa trên attempts.

### 24.3. Cần xem volume

Một provider có 2/2 success không chứng minh nó đáng tin cậy hơn provider có 99.900/100.000 success. Hiển thị window, count và event mix khi so sánh.

## 25. Prometheus: tốc độ attempts theo provider

Giả sử exporter phát counter:

~~~text
mail_smtp_submit_attempts_total{
  provider="smtp_provider_a",
  outcome="success"
}
~~~

Tốc độ attempts:

~~~promql
sum by (provider) (
  rate(mail_smtp_submit_attempts_total[5m])
)
~~~

### 25.1. Attempt success ratio

~~~promql
sum by (provider) (
  rate(
    mail_smtp_submit_attempts_total{
      outcome="success"
    }[5m]
  )
)
/
sum by (provider) (
  rate(mail_smtp_submit_attempts_total[5m])
)
~~~

Cần xử lý mẫu số bằng 0 và thống nhất danh sách outcomes. Công thức này không đo inbox delivery.

### 25.2. Error categories

~~~promql
sum by (provider, error_category) (
  rate(mail_smtp_submit_failures_total[5m])
)
~~~

Nếu có metric failures tương ứng, mỗi category phải đến từ tập hữu hạn. Không tạo error_category từ raw exception message.

### 25.3. Đọc đúng semantics

Một event retry có thể tạo nhiều attempts. Biểu đồ rate của attempts không tương đương số unique customers nhận email mỗi giây.

## 26. Prometheus: latency theo provider

Với Timer có histogram, có thể có series:

~~~text
mail_smtp_submit_call_duration_seconds_count
mail_smtp_submit_call_duration_seconds_sum
mail_smtp_submit_call_duration_seconds_bucket
~~~

Tên thực tế tùy Micrometer/Prometheus registry và cấu hình; buckets chỉ có khi histogram/SLO được bật phù hợp.

### 26.1. p95 send call thành công

~~~promql
histogram_quantile(
  0.95,
  sum by (provider, le) (
    rate(
      mail_smtp_submit_call_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

### 26.2. Không average p95 giữa nodes

Percentiles không phải đại lượng cộng tuyến tính. Cần tổng hợp histogram buckets chính xác thay vì lấy trung bình các p95 của instance.

### 26.3. Coi latency cùng size/traffic mix

Một nhà cung cấp nhận chủ yếu PDF 5 MB có thể có send latency cao hơn nhà cung cấp chuyên gửi OTP ngắn. Cần phân tích mail kind, size buckets và client-side preparation để không so sánh sai.

## 27. Dashboard tối thiểu cho nhiều provider

| Khu vực | Chỉ số/biểu đồ |
| --- | --- |
| **Route distribution** | Selection count theo source/provider/reason |
| **Actual usage** | Attempts/second theo provider/account |
| **Submission outcome** | Success, failure, unknown theo provider |
| **Latency** | p50/p95/p99 send-call theo outcome |
| **Error breakdown** | Auth, TLS, connect, recipient, throttling |
| **Failover** | Số lần A→B, lý do, xu hướng |
| **Outbox** | Pending, oldest age, retries, deadline misses |
| **Business mail events** | Unique completed vs terminal failed |
| **Capacity** | Worker saturation, provider rate limit/quota |
| **Downstream** | Bounce/delivery webhook nếu có integration |

### 27.1. Có biểu đồ cả selected và attempted

Nếu traffic của provider A giảm, cần biết router ít chọn A hay chọn A nhưng chuẩn bị message lỗi trước send.

### 27.2. Dùng filters theo source và mail kind

Ví dụ identity-service có AUTH failures nhưng order-service không bị ảnh hưởng. Điều đó gợi ý lỗi account/security route riêng hơn là outage của toàn SMTP provider.

### 27.3. Hiển thị count đi cùng ratio

Một tỷ lệ 50% của hai samples có ý nghĩa khác với tỷ lệ 50% của 100.000 samples. Dashboard có thể giảm nhiễu bằng cửa sổ và ngưỡng lượng mẫu thích hợp.

## 28. Alert vận hành theo provider

Những cảnh báo có hành động rõ:

- **Auth failure tăng theo account alias**: kiểm tra secret/permission, dừng retry dồn dập.
- **TLS failures tăng**: kiểm tra hostname, certificate chain, endpoint mode.
- **Timeout rate tăng**: phân biệt connect/read/write/unknown outcome.
- **SMTP 421/450 tăng**: xem provider throttling và backoff.
- **Failover frequency tăng**: kiểm tra primary và khả năng chịu tải của backup.
- **Backup traffic gần quota**: cân bằng lại, hạn chế load.
- **Outbox oldest pending vượt SLO**: xem queue/worker/retry.
- **Unknown outcomes tăng**: cần đối soát duplicate risk.
- **Provider A không có attempts dù còn là primary**: kiểm tra router/circuit breaker/config.

### 28.1. Không đánh giá provider down bằng một recipient lỗi

Một SMTP 550 ở RCPT TO có thể xuất phát từ địa chỉ không tồn tại. Điều này không chứng minh provider mất khả năng phục vụ toàn bộ.

### 28.2. Circuit breaker cần metric riêng

Nếu circuit breaker OPEN, provider có thể không nhận attempts mới; tỷ lệ lỗi từ traffic ít hoặc bằng 0 không có nghĩa nó đã phục hồi. Ghi breaker state và routing suppressions theo reason.

### 28.3. Alert cần phù hợp traffic

Một provider chỉ có vài attempts mỗi giờ nên có chính sách alert khác provider có hàng chục nghìn attempts/phút, để tránh phản ứng quá mức trước nhiễu.

## 29. Provider health không đồng nghĩa delivery health

Một số ứng dụng dùng JavaMailSenderImpl.testConnection() hoặc TCP/TLS probe.

Cần hiểu:

- Probe có thể kiểm tra kết nối/login ở một mức nhất định.
- Không thay thế việc gửi và serialize MIME thật.
- Không xác minh quyền gửi From domain với mọi account.
- Không chứng minh inbox delivery.
- Không chứng minh mọi recipient được chấp nhận.

### 29.1. Đừng testConnection trước mọi message

Mỗi lần testConnection có thể tạo overhead mạng, tăng số kết nối và làm chậm throughput. Chỉ probe với cadence phù hợp và sử dụng metrics traffic thật để bổ sung.

### 29.2. Health theo provider và account

Endpoint provider có thể còn sống trong khi một account bị khóa. Cần đủ chiều attribution để thấy tình trạng ở đúng cấp độ.

### 29.3. Probe cũng cần đo outcome

Một health check gặp TLS failure hoặc timeout phải được log/metric với provider alias tương ứng. Nhưng probe traffic không nên bị tính nhầm vào business SMTP submit attempts.

## 30. Configuration và historical attribution

Khi route config được đổi:

~~~text
10:00 account=transactional -> provider A
10:30 operator changes mapping
11:00 account=transactional -> provider B
~~~

Nếu lịch sử chỉ lưu account alias và dashboard tra mapping hiện tại, những attempt cũ có thể bị gán nhầm provider B.

### 30.1. Lưu provider identity ở thời điểm attempt

Mỗi attempt nên giữ provider_alias thực tế và config/policy version khi cần.

### 30.2. Không biến primary thành provider identity

Primary/backup là vai trò, có thể đổi. Một alias định danh nhà cung cấp phải ổn định hơn vai trò route.

### 30.3. Audit manual overrides

Manual route overrides cần ghi thời điểm, lý do và người thực hiện theo chính sách audit. Không đưa free-text ticket hoặc danh tính nhạy cảm vào metric labels.

### 30.4. Không lưu credential snapshots

Để điều tra một thay đổi cấu hình, chỉ cần alias/version và thông tin không nhạy cảm. Không dump password hoặc OAuth token vào log.

## 31. Test attribution bằng Mockito và Micrometer

Unit test có thể mock hai JavaMailSender, tạo MimeMessage trong bộ nhớ và xác nhận đúng provider nhận lời gọi.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Map;
import java.util.Properties;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class MultiProviderMailSubmitterTest {

    @Test
    void recordsActualProviderForSelectedAttempt() {
        SimpleMeterRegistry metrics =
                new SimpleMeterRegistry();

        JavaMailSender primary =
                mock(JavaMailSender.class);

        JavaMailSender backup =
                mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(primary.createMimeMessage())
                .thenReturn(mime);

        MultiProviderMailSubmitter submitter =
                new MultiProviderMailSubmitter(
                        Map.of(
                                "primary_transactional", primary,
                                "backup_transactional", backup
                        ),
                        metrics
                );

        OutboundMailJob job =
                new OutboundMailJob(
                        "mail-1842",
                        "order-service",
                        "order_confirmation",
                        "an@example.net",
                        "Xác nhận đơn hàng",
                        "Đơn hàng đã được xác nhận."
                );

        MailRouteDecision route =
                new MailRouteDecision(
                        "order-service",
                        "smtp_provider_a",
                        "primary_transactional",
                        "orders@example.org",
                        "tenant_default"
                );

        submitter.submit(job, route, "mail-1842-attempt-1");

        verify(primary, times(1))
                .send(any(MimeMessage.class));

        verifyNoInteractions(backup);

        Counter counter = metrics
                .find("mail.smtp.submit.attempts")
                .tag("provider", "smtp_provider_a")
                .tag("outcome", "success")
                .counter();

        assertNotNull(counter);
        assertEquals(1.0, counter.count(), 0.0001);

        assertNull(
                metrics.find("mail.smtp.submit.attempts")
                        .tag("provider", "smtp_provider_b")
                        .counter()
        );
    }
}
~~~

### 31.1. Test chứng minh gì?

- Sender của account primary được dùng.
- Sender backup không được gọi.
- Metric thuộc smtp_provider_a, không phải provider khác.
- Không mở kết nối SMTP thật.
- Không cần recipient thật.

### 31.2. Test failure path riêng

Cho primary.send ném MailSendException; kiểm tra **outcome=failure** của A tăng, success không tăng. Sau đó unit test router/retry policy riêng có thể giả lập quyết định chuyển sang B nếu lỗi được phân loại là an toàn cho failover.

### 31.3. Test route không hợp lệ

Nếu account alias không nằm trong registry, ứng dụng phải báo lỗi cấu hình. Không nên âm thầm dùng default sender rồi gắn metric của provider được yêu cầu ban đầu.

## 32. Test failover không làm sai số đếm

Kịch bản:

~~~text
attempt A -> failure
policy decides failover
attempt B -> success
~~~

Expected behavior:

1. A được gọi đúng một lần.
2. B được gọi đúng một lần nếu policy cho phép.
3. Counter A/failure tăng một.
4. Counter B/success tăng một.
5. Failover counter A→B tăng một.
6. Unique event completed count tăng một khi event thực sự chuyển sang terminal success, không tăng ở mỗi attempt.
7. Attempt history giữ cả hai provider.
8. Log không chứa credential, full message hoặc recipient nếu không cần.

### 32.1. Có test unknown outcome

Nếu lỗi sau DATA có thể đã được server chấp nhận, policy không được mặc định chuyển sang B. Test cần kiểm tra trạng thái UNKNOWN_OUTCOME, đối soát hoặc xử lý khác theo quy định nghiệp vụ.

### 32.2. Có test partial recipients

Nếu một message có nhiều recipients, kiểm tra nhóm đã accept không bị gửi lại mù quáng.

### 32.3. Kiểm tra render không lặp khi không cần

Nếu mail event có rendered content snapshot và failover không đổi nội dung, chuyển provider không nhất thiết phải render Thymeleaf lại. Điều này là tối ưu độc lập với attribution, nhưng cần test để không tạo dữ liệu khác giữa hai attempts.

## 33. Tình huống: provider A lỗi AUTH

Giả sử telemetry:

~~~text
source=identity-service
kind=password_reset
provider=smtp_provider_a
account=security_primary
phase=auth
smtpReplyCode=535
errorCategory=auth
~~~

Diễn giải:

- Account security_primary đã được sử dụng.
- Lỗi xảy ra ở SMTP AUTH.
- Không cần log password để chẩn đoán.
- Có thể là credential sai, account bị vô hiệu hóa hoặc policy AUTH khác.
- Không kết luận toàn provider down nếu các account khác vẫn gửi được.
- Retry liên tục sẽ không sửa một password sai.
- Backup chỉ được dùng nếu account/From domain/loại email đã được cấp quyền và chính sách cho phép.

Theo dõi metrics **per-account** hoặc tra cứu có phân quyền khi lỗi tập trung ở một account.

## 34. Tình huống: provider bị throttling

Giả sử SMTP server trả phản hồi tạm thời theo chính sách hạn mức.

~~~text
source=order-service
provider=smtp_provider_a
errorCategory=rate_limit
routeReason=tenant_default
~~~

Hệ thống có thể cần:

- Backoff có giới hạn.
- Giảm concurrency/rate.
- Theo dõi quota.
- Điều chỉnh điều phối outbox.
- Chuyển provider nếu policy và quota cho phép.
- Bảo vệ deadline của email quan trọng.

Dashboard giúp biết có bao nhiêu attempts thất bại vì throttling, lượng traffic chuyển sang backup và backlog có tiếp tục tăng hay không.

### 34.1. Không coi tất cả 4xx là throttling

SMTP 4xx có nhiều nguyên nhân. Cần map chính xác category từ reply/enhanced status và thông tin provider.

### 34.2. Không để backup bị quá tải dây chuyền

Failover toàn bộ traffic từ A sang B có thể vượt quota của B. Quan sát công suất B và policy capacity trước khi chuyển.

## 35. Tình huống: cùng From domain, hai nhà cung cấp

~~~text
Visible From: billing@example.org

Provider A:
  account=primary_transactional
  host=smtp-a.example.net

Provider B:
  account=backup_transactional
  host=smtp-b.example.net
~~~

Cả hai có thể sử dụng cùng visible From khi domain và provider đã được cấu hình ủy quyền phù hợp.

### 35.1. Cần tách From identity và provider

Log/metric có thể dùng:

~~~text
fromIdentityAlias=billing_domain
providerAlias=smtp_provider_b
~~~

Không phải vì From giống nhau mà hai attempts có nguồn transport giống nhau.

### 35.2. SPF/DKIM/DMARC liên quan nhưng không thay thế attribution

Khi chuyển provider, cần đánh giá SPF, DKIM, DMARC, envelope return path và alignment phù hợp. Những cơ chế này hỗ trợ xác thực domain, không tự cho biết Spring Mail đã chọn provider nào.

### 35.3. Không khẳng định deliverability từ send success

Ngay cả khi sender.send trả bình thường, email có thể bị xử lý downstream. Nếu provider có webhook delivery/bounce, cần tách hệ thống nhận event đó và liên kết với mailEventId/providerMessageId khi có.

## 36. Tình huống: ứng dụng multi-tenant

Một nền tảng nhiều khách hàng có thể dùng nhiều account trên cùng provider. Nếu accountAlias bằng UUID riêng của từng tenant và gắn vào mọi metric label, số time series sẽ rất lớn.

Giải pháp phân cấp:

- Metrics tổng hợp theo provider, region, mail kind và outcome.
- Nhóm account theo tier nhỏ nếu cần.
- Tra account/tenant chi tiết qua structured logs hoặc database có phân quyền.
- Audit truy cập cho dashboard tenant-specific.
- Không đưa raw tenant/customer ID vào metric labels đại trà.

### 36.1. Account alias không đồng nghĩa provider

Một provider có nhiều accounts; một account credential lỗi không có nghĩa toàn provider down. Có chiều account đủ kiểm soát sẽ giúp phân biệt vấn đề.

### 36.2. Cách ly tenant

Observability cũng phải giữ tenant isolation. Một khách hàng không được xem lịch sử mail events, người nhận hoặc account của khách hàng khác chỉ vì dùng chung SMTP provider.

## 37. Checklist triển khai báo cáo nguồn gửi

Một quy trình thực tế:

1. Định nghĩa các trường **source_alias**, **provider_alias**, **account_alias**, **route_role** và **mail_kind**.
2. Xây registry aliases ổn định, không dùng raw hostname/credential làm label.
3. Tách event ID khỏi attempt ID.
4. Ghi route decision với reason và policy version.
5. Chỉ tăng SMTP attempt metric khi thật sự gọi send.
6. Gắn provider/account thật tại thời điểm attempt, không suy từ mapping hiện tại.
7. Ghi timer bao ngoài JavaMailSender.send và cả nhánh exception.
8. Phân biệt success phía caller, failure và unknown outcome.
9. Lưu attempt history khi retry/failover.
10. Ghi unique event completion riêng với attempts.
11. Đặt category từ exception/cause và SMTP phase khi có dữ liệu.
12. Không tự động failover mọi 4xx/5xx hoặc timeout.
13. Kiểm soát partial recipient results khi dùng batch/multi-recipient.
14. Đặt low-cardinality metric tags.
15. Không log recipient/Subject/body/password/token không cần thiết.
16. Dùng trace spans riêng theo attempts nếu có tracing.
17. Đo queue delay, retry wait và end-to-end separately.
18. Tạo dashboard route distribution, actual usage, latency và error.
19. Alert theo account/provider/rate limit/unknown outcome.
20. Có runbook xử lý TLS, AUTH và failover.
21. Kiểm tra backup capacity và From authorization.
22. Test attribution bằng Mockito và fake transport.
23. Kiểm tra dữ liệu lịch sử khi route policy đổi.
24. Đối soát metrics với outbox state định kỳ để nhận biết chênh lệch.

## 38. Câu hỏi thường gặp

**1. Báo cáo “nguồn gửi” nên dùng From hay provider?**

Cần có ít nhất hai trường: nguồn nghiệp vụ và provider thực tế. From identity là chiều riêng, không thay thế transport attribution.

**2. Làm sao biết provider nào thực sự được dùng?**

Ghi metric/log ngay tại adapter gọi JavaMailSender được chọn. Không suy provider từ event ban đầu nếu route có thể thay đổi.

**3. Một mail event retry ba lần có phải ba email không?**

Không phải ba unique business events. Nó tạo ba attempts; có thể gửi trùng trên thực tế trong failure window, nhưng số attempts không tự chứng minh số mailbox nhận.

**4. Failover thành công có xóa lỗi của provider trước không?**

Không. Provider đầu vẫn có attempt lỗi, provider sau có attempt thành công. Business event cuối cùng có thể completed.

**5. Có nên ghi SMTP username vào metric không?**

Không cần. Dùng account alias đã được quản lý. Không ghi password/token.

**6. Spring Mail có tự trả provider message ID không?**

JavaMailSender chuẩn không bảo đảm trả một provider-specific message ID sau send. Một số provider có API/webhook riêng để đối soát downstream.

**7. Send trả bình thường có nghĩa delivered không?**

Không. Đây là hoàn tất submit theo transport. Inbox delivery/bounce và người nhận mở là các mốc khác.

**8. Timeout có chắc chắn email chưa gửi không?**

Không. Timeout sau DATA có thể xảy ra khi relay đã chấp nhận. Cần unknown outcome và policy đối soát/retry.

**9. Có nên failover mọi SMTP 5xx?**

Không. 5xx có thể do recipient, sender authorization hoặc content policy; đổi provider chưa chắc giúp và có thể vi phạm chính sách.

**10. Tại sao không dùng recipient làm metric tag?**

Recipient là PII và tạo high cardinality. Dùng correlation ID trong log có phân quyền nếu cần.

**11. p95 của provider nào cũng đo giống nhau phải không?**

Cần dùng cùng scope Timer, cùng cách xử lý outcome và xem mail mix/kích thước message. Nếu không, so sánh có thể sai.

**12. Health probe có thay thế metrics gửi thật không?**

Không. Probe có thể kiểm tra connection/AUTH nhưng không chứng minh mọi MIME messages đều được provider accept hay delivered.

**13. Khi provider role đổi từ primary sang backup thì sao?**

Giữ provider identity ổn định và route_role riêng. Lưu provider thực tế ở attempt để không gán sai lịch sử.

**14. Có nên lưu toàn bộ SMTP transcript để attribution chính xác?**

Thường không cần. Route decision, attempt outcome, mã lỗi và correlation đủ cho nhiều tình huống. Raw debug có rủi ro lộ dữ liệu và nên giới hạn.

**15. Có thể kiểm thử attribution mà không có SMTP thật không?**

Có. Mock nhiều JavaMailSender, dùng SimpleMeterRegistry, verify đúng sender được gọi và counter đúng provider/outcome.

**16. Có thể gắn tenant ID vào metric không?**

Nếu số tenant lớn hoặc dữ liệu nhạy cảm, không nên đưa vào label đại trà. Tổng hợp theo provider/tier và tra chi tiết trong hệ thống có phân quyền.

**17. Có nên theo dõi route selection và actual attempts riêng?**

Có. Router có thể chọn provider nhưng lỗi chuẩn bị message khiến send chưa được gọi. Hai counter trả lời hai câu hỏi khác nhau.

**18. Một SMTP message có nhiều recipients có nguy cơ gì?**

Có thể có partial acceptance, khó retry từng người và nguy cơ lộ danh sách To/CC. Cần thiết kế recipient-level result khi nghiệp vụ yêu cầu.

**19. OpenTelemetry có semantic convention riêng cho mọi field này không?**

Không nên giả định. Có thể dùng custom attributes rõ nghĩa và kiểm tra những conventions hiện có để tránh xung đột.

**20. Quan sát provider A bị lỗi nhưng event thành công qua B có nghĩa SLA tốt?**

Business SLA có thể còn tốt, nhưng provider A vẫn cần được điều tra; failover cũng có thể tăng chi phí, latency và duplicate risk.

## 39. Ghi nhớ về báo cáo nguồn gửi trong observability

**Trong Spring Framework Mail nhiều nhà cung cấp, “nguồn gửi” phải được phân tách thành nguồn nghiệp vụ, provider/account SMTP thực sự được dùng và danh tính email hiển thị.** Một provider được chọn chưa chắc có attempt; một attempt đã bắt đầu chưa chắc được relay chấp nhận; send trả thành công không chứng minh inbox delivery.

**Attribution nên gắn với từng attempt, không chỉ event cuối cùng.** Khi retry hoặc failover, giữ lịch sử provider trước và sau, phân loại lỗi, đo duration và trạng thái không chắc chắn sau DATA. Đếm **SMTP attempts** tách khỏi **unique mail events** để không thổi phồng số email nghiệp vụ.

Sử dụng **Micrometer counters/timers** cho tổng hợp, **structured logs** chứa eventId/attemptId cho đối soát và **tracing** cho luồng nghiệp vụ → outbox → route → SMTP. Metric labels phải ít giá trị và được allowlist; không đưa recipient, Subject, body, attachment, password, token hoặc event ID vào time series.

Báo cáo nguồn gửi tốt giúp đội vận hành biết **ai tạo ý định gửi, provider nào đã thực sự được thử, attempt nào thành công hoặc thất bại, lúc nào cần failover và kết quả cuối chắc chắn đến đâu**. Đây là nền tảng để quản lý độ tin cậy của hệ thống đa SMTP provider một cách chính xác, an toàn và có thể kiểm chứng.
