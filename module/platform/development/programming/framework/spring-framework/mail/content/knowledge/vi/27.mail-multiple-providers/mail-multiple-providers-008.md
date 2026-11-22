# Quản lý credential và quota riêng

## 1. Bài toán khi Spring Framework Mail sử dụng nhiều nhà cung cấp

Trong một ứng dụng sử dụng **Spring Framework Mail**, gửi email qua một SMTP server thường tương đối đơn giản: cấu hình `spring.mail.host`, `spring.mail.username`, `spring.mail.password`, tạo `MimeMessage` rồi gọi `JavaMailSender.send(...)`. Nhưng khi hệ thống gửi mail qua **nhiều nhà cung cấp (multi-provider)**, việc chỉ thay đổi host khi có sự cố không đủ.

Mỗi nhà cung cấp có thể có:

- Một hoặc nhiều **credential** (SMTP username/password, API key hoặc OAuth2 token).
- Những **sender identity** và domain được xác minh riêng.
- Chính sách SMTP AUTH, TLS, port và authentication mechanism khác nhau.
- **Quota** tính theo message, recipient, request, số kết nối, giờ/ngày hoặc phạm vi account.
- Các giới hạn tốc độ, burst, concurrency và phản hồi throttling khác nhau.
- Dashboard, audit, message trace, bounce/complaint và quota telemetry riêng.
- Cơ chế khóa credential, rotate key và vô hiệu hóa tài khoản riêng.

Nếu dùng chung một biến `SMTP_PASSWORD` và một bộ đếm `mailSentToday` cho tất cả provider, hệ thống rất dễ gửi bằng sai danh tính, vượt quota hoặc làm hỏng tuyến dự phòng khi thay đổi secret.

**Mục tiêu:** mỗi đường gửi phải có một **provider profile** với credential, sender permission, quota policy và trạng thái vận hành tách biệt; việc chọn tuyến phải có kiểm soát, không để mail job tự mang mật khẩu hoặc chọn arbitrary SMTP host.

~~~text
Business events / Notification requests
                  |
                  v
          Mail outbox / queue
                  |
                  v
            Mail dispatcher
                  |
          Approved route policy
                  |
          +-------+--------+
          |                |
          v                v
    Provider A          Provider B
    Account A           Account B
    Credential A        Credential B
    Allowed From A      Allowed From B
    Rate/Quota A        Rate/Quota B
          |                |
          v                v
    JavaMailSender A    JavaMailSender B
          |                |
          v                v
      SMTP A             SMTP B
~~~

**Không có một cách phân quyền và đếm quota chung cho mọi provider.** Trong bài, các thông số và tên provider profile là ví dụ thiết kế, không phải giới hạn được công bố của một nhà cung cấp cụ thể. Khi vận hành thật phải đối chiếu tài liệu và console của account đang dùng.

## 2. Tách bốn khái niệm: provider, account, credential và sender identity

Những thuật ngữ này dễ bị dùng thay thế nhau nhưng có thể là bốn thực thể khác nhau:

| Thực thể | Vai trò | Ví dụ giả định |
|---|---|---|
| Provider | Dịch vụ cung cấp SMTP hoặc email API | `PRIMARY_SMTP` |
| Provider account / organization | Đơn vị sở hữu gói và quota | `company-prod-account` |
| Credential / service identity | Định danh được phép xác thực để gửi | `orders-smtp-key-v3` |
| Sender identity | Địa chỉ/domain có thể đứng trong `From` | `orders@example.com` |
| Route profile | Cấu hình ứng dụng liên kết các thành phần | `PROD_ORDERS_PRIMARY` |

Một provider account có thể cấp nhiều credentials. Những credentials đó **có thể cùng chia quota account**, thay vì mỗi key được tăng thêm quota. Ngược lại, provider khác có thể cấp hạn mức riêng cho từng sending pool hoặc identity.

Một credential cũng không mặc định được phép sử dụng mọi `From`: provider có thể yêu cầu verified sender, quyền Send As hoặc một cơ chế delegation cụ thể.

### Vì sao không dùng username làm provider ID?

Một số SMTP providers dùng username không phải địa chỉ email; có nơi username là token identifier, có nơi SMTP username khác account ID. Khi rotate credential, username có thể thay đổi trong khi tuyến `PROD_ORDERS_PRIMARY` vẫn là tuyến cũ.

Vì vậy nên sử dụng các ID logic ổn định:

~~~text
providerId        = PRIMARY_SMTP
providerAccountId = PRIMARY_PROD_ACCOUNT
senderProfileId   = ORDERS
credentialRef     = secret://mail/primary/orders/current
quotaScope        = PRIMARY_PROD_ACCOUNT
~~~

Đây là thông tin mô hình hóa, không phải URI secret manager bắt buộc. Không ghi giá trị secret vào route profile, outbox hoặc log.

## 3. Mô hình ranh giới bảo mật và quota

Hai provider không tự nhiên tạo ra hai miền độc lập nếu ứng dụng dùng chung khóa, account hoặc đường gửi:

~~~text
                         Spring Mail Application
                                   |
                        Approved profile resolver
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
            Provider A                        Provider B
           secret scope A                    secret scope B
           SMTP identity A                   SMTP identity B
           sender policy A                   sender policy B
           quota counter A                   quota counter B
           provider audit A                  provider audit B
                  |                                 |
                  v                                 v
            Accepted / failed                 Accepted / failed
~~~

Những ranh giới cần giữ:

1. **Secret:** Workload A hoặc sender A không mặc định đọc được credential B.
2. **Provider selection:** Job chỉ sử dụng route đã được ứng dụng phê duyệt, không lấy host/username/password từ HTTP request.
3. **Sender authorization:** `From` phải được phép trên provider đang được chọn.
4. **Quota:** Counter/limiter dùng đúng provider-account scope, không trừ nhầm ngân sách của account khác.
5. **Outcome:** Thất bại của provider A không bị ghi nhầm thành thống kê của provider B.
6. **Audit:** Có thể biết job nào thử qua tuyến nào, với attempt nào, mà không phơi credential hoặc địa chỉ người nhận.

### Sự cố nếu không tách đúng

| Thiết kế sai | Hệ quả |
|---|---|
| Dùng chung một SMTP password trong cấu hình cả hai route | Sự cố lộ secret kéo theo nhiều tuyến; có thể auth sai provider |
| Dùng một `JavaMailSenderImpl` mutable rồi `setHost/setPassword` theo request | Race giữa thread, nguy cơ gửi bằng identity sai |
| Dùng một rate bucket cho mọi provider | Provider A có thể làm cạn permit của B dù quota độc lập |
| Dùng bucket riêng cho mỗi credential dù cùng account quota | Tổng lượng gửi có thể vượt quota account |
| Fallback mọi lỗi sang B | Gửi trùng khi A đã accepted nhưng response thất lạc |
| Chỉ đổi SMTP host nhưng giữ `From` cũ | Provider B có thể từ chối sender chưa được xác minh |
| Log đầy đủ SMTP credentials để debug | Rò thông tin xác thực sang hệ thống quan sát |

## 4. Quyết định dùng nhiều provider vì lý do gì?

Trước khi thiết kế registry và routing, cần phân biệt những mục tiêu:

- **High availability:** có đường dự phòng khi primary ngừng cung cấp dịch vụ.
- **Workload isolation:** email OTP, hóa đơn và marketing có tài khoản/quota khác nhau.
- **Cost optimization:** chọn tuyến theo giá và nhu cầu hợp lệ, trong giới hạn chính sách.
- **Geography/compliance:** dữ liệu và việc gửi phải đi qua provider/khu vực được phê duyệt.
- **Deliverability:** domain, sender reputation và bounce/complaint handling theo tuyến.
- **Provider migration:** chuyển dần traffic sang hệ thống mới mà không mất kiểm soát.

Những mục tiêu này ảnh hưởng cách chọn quota key:

| Mục tiêu | Cách phân tách thường cân nhắc |
|---|---|
| HA | Primary và secondary có credentials và quota chính sách độc lập |
| OTP ưu tiên cao | Sender identity/account/lane riêng hoặc ngân sách được bảo vệ |
| Marketing khối lượng lớn | Tách queue/credential/quota khỏi transactional |
| Multi-tenant | Provider profile và policy authorization theo tenant |
| Migration | Route weight và khóa quota riêng theo mỗi account, rollout có đo đạc |

**Nhiều nhà cung cấp không phải cách né anti-spam hoặc quota của một nhà cung cấp.** Route/failover phải tuân thủ hợp đồng, consent, sender verification và yêu cầu deliverability. Nếu một account bị hạn chế vì hành vi gửi không phù hợp, chuyển toàn bộ lưu lượng để tiếp tục hành vi đó là một vấn đề bảo mật và tuân thủ, không phải HA.

## 5. Nguyên tắc ít đặc quyền cho mỗi credential

Credential của đường gửi chỉ nên có khả năng thực hiện đúng tác vụ được cấp:

- Gửi email từ danh tính hoặc domain đã được xác minh.
- Không có quyền quản trị organization/tenant nếu chỉ cần SMTP submission.
- Không có quyền đọc/xóa mailbox nếu ứng dụng không dùng IMAP/POP hoặc mail API để đọc.
- Không dùng lại credential của nhân viên hay quản trị viên.
- Tách credential giữa production và development/staging.
- Hạn chế nguồn kết nối theo IP/relay policy hoặc workload identity khi provider hỗ trợ.
- Có quota/rate và cảnh báo khi lưu lượng bất thường.
- Có thể revoke độc lập mà không làm mất quyền truy cập các tuyến khác.

Một ví dụ ma trận:

| Quyền | Transactional sender A | Marketing sender B |
|---|---|---|
| SMTP submit từ sender đã cấp | Cho phép | Cho phép |
| Send As mọi mailbox trong tổ chức | Không | Không |
| Đọc mailbox nhân viên | Không | Không |
| Thay đổi DNS/domain settings | Không | Không |
| Quản trị user/account | Không | Không |
| Gửi qua endpoint/sending region được phép | Cho phép | Cho phép |
| Dùng trong staging bằng secret production | Không | Không |

Provider có thể không có role gọi là “send-only” theo tên này. Nếu chức năng phân quyền của nhà cung cấp rộng hơn yêu cầu, phải ghi nhận rủi ro và dùng các lớp kiểm soát khác, hoặc cân nhắc account/provider phù hợp hơn.

## 6. Credential riêng không đồng nghĩa quota riêng

Ví dụ:

~~~text
Provider A / Production account
  |
  +-- SMTP credential order-mailer
  +-- SMTP credential security-mailer
  |
  +-- Shared quota: recipients/day

Provider B / Independent account
  |
  +-- SMTP credential newsletter-mailer
  |
  +-- Own quota: messages/second
~~~

Trong giả định này, order-mailer và security-mailer của provider A dùng **hai credential khác nhau nhưng cùng ngân sách ngày**. Tạo hai token bucket độc lập và mỗi bucket cho dùng toàn quota A sẽ làm vượt tổng hạn mức.

Do đó cần **phân tách hai chiều**:

1. Phân tách **credential** theo mục đích bảo mật và quyền sử dụng.
2. Phân tách/ghép **quota accounting** theo đúng scope nhà cung cấp công bố.

Một job có thể cần đồng thời thỏa mãn quota **account tổng**, rate theo **credential**, rate theo **sender** và fairness theo **tenant**. Thiết kế hạn mức không nhất thiết trùng với cách chia mật khẩu.

## 7. Lưu credential bằng secret manager, không nhúng vào source

Một anti-pattern:

~~~yaml
app:
  mail:
    providers:
      primary:
        password: real-smtp-password-committed-to-git
      secondary:
        password: another-real-smtp-password-committed-to-git
~~~

Ngay cả khi xóa mật khẩu khỏi file ở commit sau, secret có thể còn trong git history, bản build, CI logs và container image. Mỗi provider cần một **secret reference riêng**, với quyền đọc giới hạn cho workload thực sự sử dụng.

Thiết kế có thể là:

~~~text
Production secret store
   |
   +-- /mail/primary/transactional/current
   |      +-- SMTP username / password
   |      +-- access limited to transactional workload
   |
   +-- /mail/secondary/transactional/current
   |      +-- distinct credentials
   |      +-- access limited to approved fallback workload
   |
   +-- /mail/primary/marketing/current
          +-- isolated campaign sender identity
~~~

Trong ứng dụng, các giá trị cấu hình có thể được inject thông qua environment, mounted secret hoặc một secret-manager integration. **Environment variable không tự nó là một kho bí mật**: người có quyền đọc process/environment hoặc crash dump có thể lấy được nội dung. Cần bảo vệ runtime, secret access, audit và vòng đời deployment.

### Không đưa secret vào outbox

Một job cần được lưu bền vững để gửi sau khi application restart, nhưng không nên snapshot mật khẩu:

~~~json
{
  "jobId": "mail-job-381",
  "senderProfileId": "ORDERS",
  "preferredProvider": "PRIMARY",
  "recipientId": "customer-42",
  "notificationType": "ORDER_RECEIPT"
}
~~~

`preferredProvider` và `senderProfileId` là ID logic. Worker sẽ tra cứu provider profile và credential đã được cấp ở thời điểm gửi. Nếu job phải “đóng băng” một số thông số chính sách tại thời điểm tạo, chỉ lưu **version ID** không chứa secret.

### Không in cấu hình toàn bộ bean

Tránh:

~~~java
log.debug("SMTP configuration: {}", smtpConfig);
~~~

Nếu `smtpConfig` là record chứa trường password, `toString()` có thể vô tình đưa giá trị ra log. Với configuration DTO chứa secret, không dùng automatic logging hoặc serialization bừa bãi; chỉ log `providerId`, `configVersion` và các thông tin đã được làm sạch.

## 8. Cấu hình Spring Boot cho hai provider

`spring.mail.*` trong Spring Boot thường diễn tả một sender mặc định. Khi có nhiều SMTP routes, nên thiết kế một namespace cấu hình riêng để biểu diễn **từng provider profile**, rồi tạo nhiều `JavaMailSender` bean.

Ví dụ `application.yml`:

~~~yaml
app:
  mail:
    providers:
      primary:
        host: smtp-primary.example.test
        port: 587
        username: ${PRIMARY_SMTP_USERNAME}
        password: ${PRIMARY_SMTP_PASSWORD}
        allowed-from: orders@example.com
        auth: true
        starttls: true
        max-concurrent: 4
      secondary:
        host: smtp-secondary.example.test
        port: 587
        username: ${SECONDARY_SMTP_USERNAME}
        password: ${SECONDARY_SMTP_PASSWORD}
        allowed-from: orders@example.com
        auth: true
        starttls: true
        max-concurrent: 2
~~~

Những host và hạn mức là ví dụ. `allowed-from` chỉ là **quy tắc do ứng dụng kiểm tra**; đặt nó trong YAML không tự cấp quyền sender ở provider. Trước khi sử dụng production, địa chỉ From phải được xác minh/ủy quyền ở từng provider.

Các placeholder được runtime cung cấp; không bao giờ commit credential thật.

### Một record để binding cấu hình

~~~java
import org.springframework.boot.context.properties
        .ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.providers")
public record MultiProviderMailProperties(
        SmtpEndpoint primary,
        SmtpEndpoint secondary) {

    public record SmtpEndpoint(
            String host,
            int port,
            String username,
            String password,
            String allowedFrom,
            boolean auth,
            boolean starttls,
            int maxConcurrent) {
    }
}
~~~

Đăng ký với Spring:

~~~java
import org.springframework.boot.context.properties
        .EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(
        MultiProviderMailProperties.class)
public class MailProviderPropertiesConfiguration {
}
~~~

`@ConfigurationProperties` chỉ **bind** giá trị. Nó không tự chọn provider cho mỗi email và không tự thực thi quota. Có thể thêm Jakarta Bean Validation trên các trường `port`, `host` và `maxConcurrent` để fail fast khi thiếu cấu hình hoặc giá trị không hợp lệ.

### Không mặc định trộn auto-config sender với các bean tùy chỉnh

Trong ứng dụng đa provider, nên biết chính xác bean nào phục vụ route nào. Khi đã định nghĩa nhiều `JavaMailSender`, injection không có `@Qualifier` có thể dẫn đến ambiguity. Không dựa vào một bean default với tài khoản có quyền rộng rồi để các feature không kiểm soát được tự sử dụng.

## 9. Tạo JavaMailSender riêng cho mỗi SMTP provider

Ví dụ sau chỉ dùng API Spring Mail và JavaMail, không gọi SMTP trong giai đoạn tạo bean:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultiProviderMailConfiguration {

    private JavaMailSenderImpl createSender(
            MultiProviderMailProperties.SmtpEndpoint cfg) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(cfg.host());
        sender.setPort(cfg.port());
        sender.setUsername(cfg.username());
        sender.setPassword(cfg.password());
        sender.setDefaultEncoding("UTF-8");

        Properties mailProps = sender.getJavaMailProperties();
        mailProps.put("mail.smtp.auth",
                Boolean.toString(cfg.auth()));
        mailProps.put("mail.smtp.starttls.enable",
                Boolean.toString(cfg.starttls()));
        mailProps.put("mail.smtp.starttls.required",
                Boolean.toString(cfg.starttls()));
        mailProps.put("mail.smtp.ssl.checkserveridentity", "true");
        mailProps.put("mail.smtp.connectiontimeout", "5000");
        mailProps.put("mail.smtp.timeout", "10000");
        mailProps.put("mail.smtp.writetimeout", "10000");
        mailProps.put("mail.debug", "false");
        return sender;
    }

    @Bean("primaryMailSender")
    JavaMailSender primaryMailSender(
            MultiProviderMailProperties props) {
        return createSender(props.primary());
    }

    @Bean("secondaryMailSender")
    JavaMailSender secondaryMailSender(
            MultiProviderMailProperties props) {
        return createSender(props.secondary());
    }
}
~~~

Hai bean có cấu hình riêng, nhưng **không tự bảo đảm provider quotas được áp**. Việc đặt `maxConcurrent` trong configuration DTO chỉ mang ý nghĩa cho bộ điều phối SMTP ở bước sau.

### Chọn bean bằng @Qualifier

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class ProviderSenderRegistry {
    private final JavaMailSender primary;
    private final JavaMailSender secondary;

    public ProviderSenderRegistry(
            @Qualifier("primaryMailSender")
            JavaMailSender primary,
            @Qualifier("secondaryMailSender")
            JavaMailSender secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    public JavaMailSender resolve(ProviderId provider) {
        return switch (provider) {
            case PRIMARY -> primary;
            case SECONDARY -> secondary;
        };
    }
}

enum ProviderId {
    PRIMARY, SECONDARY
}
~~~

`ProviderId` là enum nội bộ. Đừng nhận chuỗi `providerHost` hoặc `smtpPassword` từ HTTP request và tạo `JavaMailSenderImpl` theo bất kỳ thông số nào mà client truyền vào.

### Không mutate singleton sender trước mỗi lần gửi

Sai trong môi trường concurrent:

~~~java
// Một bean dùng chung; hai thread có thể ghi đè cấu hình nhau.
sender.setHost(route.host());
sender.setUsername(route.username());
sender.setPassword(route.password());
sender.send(message);
~~~

Nếu thread A đang chuẩn bị credential primary nhưng thread B vừa thay thành secondary, ứng dụng có thể authenticate sai hoặc gửi từ một đường không mong muốn. Hãy giữ sender theo provider profile riêng, cấu hình bất biến trong một phiên triển khai/rotation; nếu cần thay token động, sử dụng cơ chế authentication được thiết kế rõ, không sửa ngẫu nhiên các thuộc tính toàn cục trước mỗi call.

## 10. Tách danh tính người gửi khỏi API nghiệp vụ

Một controller không nên cho người gọi chọn:

~~~json
{
  "smtpHost": "random-host.example",
  "smtpPassword": "supplied-by-client",
  "from": "ceo@example.com",
  "to": "victim@example.net",
  "html": "arbitrary-content"
}
~~~

API như vậy có thể biến backend thành một email relay bị lạm dụng. Thay vào đó, client chỉ mô tả **hành động nghiệp vụ**:

~~~java
public record OrderReceiptCommand(
        String orderId,
        String customerId,
        String locale) {
}
~~~

Application service:

1. Kiểm tra quyền đối với đơn hàng.
2. Lấy người nhận từ nguồn tin cậy.
3. Chọn template đã phê duyệt.
4. Chọn sender profile `ORDERS` và tuyến hợp lệ.
5. Lưu job trong outbox.
6. Để dispatcher quyết định quota/route khi gửi.

Việc một job yêu cầu gửi email không có nghĩa job được phép vượt quota hoặc đổi sang provider bất kỳ. Authorization nghiệp vụ, sender permission và quota admission là các lớp bảo vệ khác nhau.

## 11. Xác minh địa chỉ From trên từng provider

Một email có thể sử dụng:

~~~text
SMTP authentication identity: api-user-a
Header From: orders@example.com
SMTP envelope MAIL FROM: bounce-a@example.com
Reply-To: support@example.com
~~~

Provider A có thể đã xác minh `orders@example.com`. Provider B **chưa chắc** đã cho phép địa chỉ này dù cùng được tổ chức sở hữu. Khi dùng B, các vấn đề sau phải được giải quyết:

- Verified sender/verified domain hoặc quyền Send As theo mô hình B.
- DKIM selector và DNS records phù hợp với B.
- SPF hoặc custom return-path theo cấu hình gửi qua B.
- DMARC alignment và chính sách domain.
- Bounce/complaint endpoint cho B.
- Reputation và các giới hạn riêng của tài khoản B.

Trong Spring:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;

var message = selectedSender.createMimeMessage();
var helper = new MimeMessageHelper(message, true, "UTF-8");
helper.setFrom(route.allowedFrom());
helper.setTo(recipient);
helper.setSubject("Xác nhận đơn hàng");
helper.setText(plainText, htmlText);

selectedSender.send(message);
~~~

`route.allowedFrom()` phải đến từ server-side approved configuration; đặt giá trị đó trong mã Java **không tự cấp quyền gửi từ địa chỉ tương ứng**. Nếu provider từ chối sender, không fallback sang tài khoản quản trị có quyền gửi mọi mailbox để “sửa nhanh”.

## 12. SMTP AUTH, OAuth2 và email API credentials

Không phải nhà cung cấp nào cũng sử dụng một cặp username/password theo cùng cơ chế:

| Cơ chế | Credential thường có | Việc cần quản lý |
|---|---|---|
| SMTP AUTH username/password | Username, password/app password | Secret store, rotation, TLS, chính sách account |
| SMTP với XOAUTH2 | Access token, cơ chế lấy/refresh token | Scope, audience, expiry, client credential |
| HTTPS email API | API key hoặc OAuth token | Scope, endpoint, key rotation, HTTP 429 |
| SMTP relay theo connector/IP/cert | Network identity hoặc certificate | IP egress, mTLS/TLS, connector policy, chống open relay |

`JavaMailSender` là abstraction dành cho gửi qua Jakarta Mail/SMTP. Nếu Provider B chỉ cung cấp **HTTP email API**, ứng dụng thường cần một adapter HTTP riêng; không nên ép mọi credential/API gọi qua `JavaMailSenderImpl`.

### OAuth2 không tự đồng nghĩa ít đặc quyền

Một access token ngắn hạn có thể tốt hơn mật khẩu tĩnh nếu được quản lý đúng. Nhưng token vẫn có thể bị cấp scope quá rộng, ví dụ quyền đọc hộp thư hoặc quản trị tenant. Cần kiểm tra:

- Grant type: delegated hay application/service identity.
- Scope/audience thực sự được phép SMTP submit/send.
- Sender/mailbox nào có thể bị đại diện.
- Quyền quản trị hoặc đọc mailbox có được cấp ngoài nhu cầu không.
- Cơ chế refresh, token expiry, revoke và rotation private key/client secret.

Đặc biệt với XOAUTH2, không chỉ thay password bằng một token cố định rồi deploy lâu dài. Adapter phải lấy token mới khi cần theo authentication lifecycle, tránh token hết hạn trong khi connection/bean đang sử dụng và không log token khi xảy ra lỗi.

## 13. Rotation credential riêng cho từng provider

Một hệ thống multi-provider cần cho phép rotate credential A mà không làm hỏng tuyến B. Đây là lợi ích lớn của việc **không dùng chung secret hoặc singleton mutable sender**.

Quy trình rotate credential primary:

1. Kiểm tra secret version hiện tại, danh sách workload sử dụng và quyền đã cấp.
2. Cấp credential mới ở provider A với **cùng phạm vi tối thiểu**, không tự thêm quyền admin hoặc sender wildcard.
3. Lưu credential mới trong secret manager như phiên bản mới.
4. Deploy/reload ứng dụng để instance mới dùng credential mới.
5. Kiểm thử submission từ sender được phép bằng recipient sandbox.
6. Kiểm tra không còn instance hoặc queue consumer dùng credential cũ.
7. Thu hồi credential cũ sau cutover, theo chính sách an ninh.
8. Xác nhận metric authentication failure trở về bình thường và ghi audit việc rotate.

Nếu provider hỗ trợ **hai credential hoạt động song song**, có thể thực hiện blue/green rotation:

~~~text
Secret A v1 ------- production current
            \
             +---- issue A v2
                        |
                        +---- deploy new instances with v2
                        |
                        +---- verify SMTP success
                        |
                        +---- drain old instances / sessions
                        |
                        +---- revoke v1

Secret B --------- unchanged
~~~

Nếu provider chỉ cho một password, đổi mật khẩu có thể làm instance cũ authenticate thất bại. Khi đó cần kế hoạch deployment phối hợp và xử lý retry; không giả định zero-downtime rotation luôn khả thi.

### Secret rotation và connection reuse

Một kết nối SMTP đã xác thực có thể tiếp tục tồn tại sau khi secret được thay đổi, tùy server và implementation. Đồng thời những connection mới có thể bắt đầu thất bại nếu dùng credential cũ.

Vì vậy cần:

- Xác định cơ chế reuse SMTP transport/connection của adapter.
- Không lấy “một email vừa gửi thành công” làm bằng chứng tất cả instance đang dùng secret mới.
- Kiểm tra đường tạo connection **mới** với credential mới.
- Đóng/drain những session cũ theo kế hoạch.
- Giám sát auth failures theo provider và secret version đã được làm sạch.

Không log password/token để kiểm tra version. Có thể log một **configuration version ID** không nhạy cảm được cấp bởi hệ thống deployment.

## 14. Xử lý khi credential bị lộ hoặc bị thu hồi

Một số tín hiệu đáng chú ý:

- SMTP auth attempts từ IP/region chưa được phê duyệt.
- Bất thường về số thư được gửi so với job outbox nội bộ.
- Provider trả lỗi auth hàng loạt sau khi secret rotate.
- Quota tăng dù application dashboard không ghi nhận submission tương ứng.
- Credential xuất hiện trong repository, CI output, error trace hoặc support ticket.

Quy trình sự cố nên giới hạn vào đúng tuyến bị ảnh hưởng:

~~~text
Credential A suspected compromised
      |
      +-- Disable/revoke A credential or route
      +-- Stop A submissions / quarantine suspicious jobs
      +-- Review A grants, From permissions, provider trace
      +-- Rotate A secret and re-verify sender identity
      +-- Determine impact on shared quota and reputation
      |
      +-- Provider B remains independently managed
             |
             +-- Only allowed jobs can use B
             +-- Apply B quotas and sender permissions
~~~

Không tự động chuyển **mọi** job A sang B ngay khi nghi compromise. Job có thể chứa nội dung chưa được phê duyệt hoặc có thể đã submit qua A với outcome chưa rõ. Cần policy failover, kiểm tra nguồn gốc nghiệp vụ và phân loại trạng thái.

### Cách ly môi trường là bắt buộc

Development/staging nên dùng SMTP sink hoặc sandbox profile và credential riêng. Nếu staging dùng key production, một lệnh test với dữ liệu khách hàng sao chép có thể gửi email thật. Ngay cả khi ứng dụng có câu lệnh `if (profile.equals("staging"))`, **provider-side recipient restriction** vẫn là lớp bảo vệ tốt hơn nếu nền tảng hỗ trợ.

## 15. Mô hình version và trạng thái của provider profile

Một profile nên có nhiều thuộc tính hơn host/password:

~~~java
public enum ProviderHealth {
    ACTIVE,
    DEGRADED,
    PAUSED,
    RETIRED
}

public record ProviderRoutePolicy(
        ProviderId providerId,
        String accountId,
        String senderProfileId,
        String allowedFrom,
        String quotaScopeKey,
        String configurationVersion,
        ProviderHealth health) {
}
~~~

Từng field có mục đích:

- `providerId`: định danh tuyến logic.
- `accountId`: xác định account/gói dịch vụ.
- `senderProfileId`: nhóm email được phép sử dụng.
- `allowedFrom`: địa chỉ gửi hợp lệ theo cấu hình ứng dụng.
- `quotaScopeKey`: nơi hạch toán năng lực provider thực tế.
- `configurationVersion`: phục vụ audit thay đổi.
- `health`: trạng thái cho dispatcher, không phải quyền auth.

**ProviderHealth.ACTIVE không có nghĩa token hợp lệ, quota còn hay From được phép.** Nó chỉ là một phần của trạng thái vận hành; ứng dụng vẫn phải kiểm tra quota, sender policy và xử lý phản hồi provider.

Nếu cần lựa chọn tuyến bằng tỷ trọng, thêm cấu hình trọng số ở route layer nhưng không thay đổi secret/quota scope tùy tiện theo từng request.

## 16. Quota theo provider có nhiều đơn vị và cửa sổ

Một provider có thể tính:

| Giới hạn | Đơn vị | Ví dụ minh họa |
|---|---|---|
| Submission rate | messages/second | 8 messages/s |
| Recipient rate | recipients/second | 15 recipients/s |
| Daily sending quota | recipients/rolling 24h | 20.000 recipients |
| API request quota | API calls/minute | 300 calls/min |
| SMTP concurrency | submissions in-flight | 4 operations |
| Per-message recipients | RCPT TO/message | 50 recipients |
| Message size | raw MIME bytes/message | 15 MiB |
| Sender/domain throttle | variable/provider-specific | Giảm tốc khi reputation thấp |

Đây không phải con số của bất kỳ provider cụ thể nào. Một **credential riêng** không phải bằng chứng rằng mỗi dòng trong bảng có limit riêng theo credential.

### Cost model thay vì một biến limit chung

~~~java
public record MailQuotaCost(
        int messages,
        int recipients,
        long mimeBytes) {

    public MailQuotaCost {
        if (messages <= 0 || recipients <= 0 || mimeBytes < 0) {
            throw new IllegalArgumentException(
                    "Invalid mail quota cost");
        }
    }
}
~~~

Ví dụ một `MimeMessage` có 1 message, 5 SMTP envelope recipients:

~~~text
message quota     -> cost 1
recipient quota   -> cost 5
byte-size check   -> số byte serialized MIME
concurrency       -> cost 1 in-flight slot
~~~

Không trừ `1` từ mọi bucket cho một message nhiều recipient. Nếu provider tính quota dựa trên recipients, cần kiểm tra cả To/Cc/Bcc hoặc tập envelope recipients thực sự; không chỉ xét header To.

### Quota reset cần chính xác

Một quota “mỗi ngày” có thể nghĩa:

- Calendar day theo timezone provider.
- Rolling 24 giờ.
- Window kể từ thời điểm kích hoạt gói.
- Reset theo billing period.

Nếu provider dùng rolling 24h mà ứng dụng reset bộ đếm lúc nửa đêm, có thể gửi gần hai lần ngưỡng trong thời gian ngắn quanh mốc reset và bị throttled. **Phải biết đơn vị quota, phạm vi, window và nguồn đo.**

## 17. Provider-aware policy: không dùng giới hạn mặc định cho mọi tuyến

Một cấu hình rate/quota minh họa:

~~~yaml
app:
  mail:
    quota:
      primary:
        scope-key: PRIMARY_PROD_ACCOUNT
        rate-unit: recipients
        tokens-per-second: 4.0
        burst-capacity: 12
        max-concurrent: 3
        safe-daily-recipient-budget: 15000
      secondary:
        scope-key: SECONDARY_PROD_ACCOUNT
        rate-unit: messages
        tokens-per-second: 2.0
        burst-capacity: 6
        max-concurrent: 2
        safe-daily-recipient-budget: 3000
~~~

`app.mail.quota.*` là cấu hình **do ứng dụng tự thiết kế**. Spring Boot không tự giới hạn số thư/giây hoặc số người nhận/ngày chỉ vì các thuộc tính này xuất hiện.

Ngoài ra, cấu hình giả định primary và secondary dùng hai account quota khác nhau. Nếu hai profile cùng một provider account, `scope-key` cần phản ánh **một quota chung**, không tạo hai bucket độc lập với cùng toàn bộ budget.

### Một record quota policy

~~~java
public enum RateUnit {
    MESSAGES,
    RECIPIENTS
}

public record ProviderQuotaPolicy(
        String scopeKey,
        RateUnit unit,
        double tokensPerSecond,
        int burstCapacity,
        int maxConcurrent,
        long safeDailyRecipientBudget) {

    public ProviderQuotaPolicy {
        if (scopeKey == null || scopeKey.isBlank()
                || !Double.isFinite(tokensPerSecond)
                || tokensPerSecond <= 0
                || burstCapacity <= 0
                || maxConcurrent <= 0
                || safeDailyRecipientBudget < 0) {
            throw new IllegalArgumentException(
                    "Invalid provider quota policy");
        }
    }
}
~~~

Với policy thực, cần thêm `quotaWindow`, `accountId`, rate limit theo nhiều đơn vị nếu provider áp đồng thời, và policy version. Đừng cố dùng một field `unit` nếu provider vừa giới hạn messages/second vừa recipients/day; phải có các bộ đếm riêng.

## 18. Giới hạn tốc độ và concurrency là hai bộ điều khiển khác nhau

Giả sử hai provider có cấu hình:

~~~text
Primary:
  safe rate = 4 recipient/s
  max concurrent SMTP submissions = 3

Secondary:
  safe rate = 2 messages/s
  max concurrent SMTP submissions = 2
~~~

**Rate** giới hạn số đơn vị tiêu thụ theo thời gian; **concurrency** giới hạn số thao tác mạng đang chạy. Một thread có thể gửi nhiều message/giây; giới hạn `maxPoolSize=3` không có nghĩa 3 messages/giây.

~~~text
Outbox
  |
  v
Quota reservation by account/sender
  |
  v
Rate gate by provider policy
  |
  v
Concurrency semaphore / connection gate
  |
  v
JavaMailSender.send(...)
  |
  v
Release concurrency slot in finally
~~~

Khi không có permit, không nên giữ SMTP thread trong `Thread.sleep(...)` lâu. Hãy chuyển job về trạng thái chờ, cập nhật `available_at` và giải phóng worker.

### Tại sao semaphore cục bộ có thể không đủ?

Nếu 4 replicas đều đặt `maxConcurrent=3` cho cùng provider account, toàn cụm có thể tạo đến 12 submissions đồng thời. Nếu provider giới hạn 3 connections/transactions cho toàn account, cần **global concurrency admission** hoặc một dispatcher tập trung. Một setting local không tự kiểm soát quota chung.

## 19. Đồng bộ hạn mức nhiều replica

Một ứng dụng Spring Boot thực tế có thể chạy trên Kubernetes:

~~~text
Primary quota account
      ^
      |
  +---+----+----+
  |        |    |
Pod 1    Pod 2 Pod 3
  |        |    |
local    local local
limiter  limiter limiter
~~~

Nếu mỗi pod có bucket `4 recipients/second`, tổng có thể lên tới 12 recipients/second. **Rate limit theo provider account phải được thực thi ở phạm vi toàn cụm**.

Một số cách:

1. **Single dispatcher per quota scope:** dễ tính quota, nhưng cần high availability và kế hoạch lease khi dispatcher restart.
2. **Redis atomic token bucket:** nhiều replica cùng lấy permit từ shared store qua script/transaction nguyên tử.
3. **Database-backed reservation:** trừ budget trong transaction với row-level lock hoặc optimistic concurrency.
4. **Distributed rate limiter library:** chọn implementation hỗ trợ atomicity và quota scopes cần thiết.
5. **Static share theo replica:** chỉ phù hợp khi số replica và sender khác được kiểm soát; autoscaling có thể làm vượt quota.

**Redis GET rồi Redis SET riêng không đủ**:

~~~text
Bucket remaining = 1
Worker A reads 1
Worker B reads 1
Worker A sends
Worker B sends

2 submissions consumed a 1-token budget.
~~~

Phải kiểm tra rồi trừ token **trong cùng một atomic operation**, đồng thời quản lý clock, TTL, failover và cách làm mới bucket khi instance restart.

### Một interface cho quota gate

~~~java
import java.time.Duration;

public record QuotaDecision(
        boolean allowed,
        Duration retryAfter,
        String reason) {
}

public interface ProviderQuotaGate {
    QuotaDecision reserve(
            String quotaScopeKey,
            MailQuotaCost cost);
}
~~~

`ProviderQuotaGate` là interface do ứng dụng tự xây dựng. Nó không được tích hợp sẵn trong `JavaMailSender`. Tên `quotaScopeKey` đại diện account/provider policy đã được cấu hình, không phải raw email hoặc credential.

Khi một send phải vượt nhiều hạn mức (account daily budget, credential rate, sender rate), reservation cần được **phối hợp/atomic** hoặc có cơ chế bù trừ được thiết kế. Không đơn giản trừ bucket A rồi trừ bucket B, để nếu B từ chối thì A bị tiêu thụ vô hạn.

## 20. Database-backed quota budget cho provider account

Nếu ứng dụng đã có outbox và PostgreSQL, có thể lưu quota window riêng theo scope:

~~~sql
CREATE TABLE mail_provider_quota_window (
    quota_scope_key VARCHAR(150) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    quota_unit VARCHAR(30) NOT NULL,
    capacity BIGINT NOT NULL CHECK (capacity > 0),
    reserved BIGINT NOT NULL DEFAULT 0
        CHECK (reserved >= 0),
    PRIMARY KEY (
        quota_scope_key,
        quota_unit,
        window_start
    ),
    CHECK (window_end > window_start)
);
~~~

Reservation có điều kiện:

~~~sql
UPDATE mail_provider_quota_window
SET reserved = reserved + :cost
WHERE quota_scope_key = :quota_scope_key
  AND quota_unit = :quota_unit
  AND window_start = :window_start
  AND reserved + :cost <= capacity
RETURNING reserved;
~~~

Nếu trả một row, reservation thành công. Nếu không trả row, có thể budget đã hết hoặc key/window không tồn tại; ứng dụng phải phân biệt và không tự coi đó là còn quota.

PostgreSQL cập nhật cùng một row trong transaction với row-level locking, giúp điều kiện `reserved + :cost <= capacity` không bị hai worker ghi đè đơn giản. Tuy nhiên:

- Cửa sổ phải được khởi tạo đúng và không race.
- Nếu provider dùng rolling window, bảng calendar window này **chưa đủ**.
- Nếu provider ghi nhận các lần gửi bên ngoài ứng dụng, counter nội bộ không phản ánh hết usage.
- Không mở transaction DB xuyên suốt quá trình `JavaMailSender.send(...)`.
- Nếu worker chết sau khi reserve nhưng trước khi gửi, có thể mất một ít budget ảo; đây là đánh đổi cần quản lý, không được hoàn quota khi SMTP outcome còn không chắc chắn.

### Credential rotation không được tự reset daily quota

Nếu quota scope là account, thay `credentialId` từ version 1 sang version 2 **không làm account quota trở về 0**. Counter phải gắn `quotaScopeKey` ổn định, không gắn phiên bản password rồi vô tình khởi tạo lại toàn bộ budget.

## 21. Quota ngày: đếm đúng provider và chu kỳ reset

Đối với daily quota, cần định nghĩa ít nhất:

- `quotaScopeKey`: account, tenant hoặc pool nào chia hạn mức.
- `quotaUnit`: recipients, messages, API requests hoặc byte.
- `windowType`: calendar day, rolling 24h hay loại riêng.
- `timezone/resetAt`: thời điểm reset do provider chỉ định.
- `capacity`: ngưỡng hợp đồng hoặc **safe operating budget**.
- `usageSource`: counter nội bộ hay usage API của provider.
- `reconciliationLag`: dữ liệu nhà cung cấp được đồng bộ chậm bao lâu.

Ví dụ giả định:

~~~text
PRIMARY_PROD_ACCOUNT:
  daily recipient quota  = 20,000
  already reserved       = 17,600
  available safe budget  = 2,400

SECONDARY_PROD_ACCOUNT:
  daily recipient quota  = 5,000
  already reserved       = 700
  available safe budget  = 4,300
~~~

Không cộng `2,400 + 4,300` rồi dùng tổng như một pool duy nhất nếu các tuyến chỉ được phép gửi những loại thư khác nhau hoặc sender identity chưa xác minh trên cả hai provider.

### Hạn mức cứng và hạn mức mềm

Có thể có:

- **Hard cap:** không cho phép vượt hạn mức được nhà cung cấp áp dụng.
- **Safe cap:** một mức thấp hơn để chừa headroom cho sai số, traffic từ hệ thống khác hoặc biến động provider.
- **Lane reservation:** giữ lại năng lực cho email bảo mật/giao dịch.

Headroom là quyết định vận hành dựa vào dữ liệu; không có một tỷ lệ phần trăm cố định bảo đảm phù hợp mọi account.

### Nếu daily quota đã hết

Thay vì gọi SMTP liên tục:

1. Không cấp admission cho job mới ở quota scope đó.
2. Đưa job về `available_at` phù hợp với kỳ reset hoặc thời điểm kiểm tra lại.
3. Giữ ý định gửi trong outbox/broker bền vững.
4. Theo dõi tuổi backlog theo từng loại notification.
5. Không gửi các job đã quá deadline nghiệp vụ.
6. Chỉ sử dụng provider B nếu route được phê duyệt, quota B còn và message chưa được accepted qua A.

Một bộ đếm “hết ngày” không nên được reset dựa trên local midnight nếu provider dùng rolling 24-hour window hoặc thời điểm reset khác.

## 22. Cấu trúc outbox giữ ngữ cảnh nhiều tuyến

Email quan trọng không nên mất chỉ vì provider hết quota hoặc một process restart. Có thể lưu mail intent:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    notification_type VARCHAR(80) NOT NULL,
    sender_profile_id VARCHAR(80) NOT NULL,
    preferred_provider VARCHAR(40),
    selected_provider VARCHAR(40),
    provider_account_id VARCHAR(100),
    recipient_ref VARCHAR(100) NOT NULL,
    payload_ref VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ,
    claim_token UUID,
    last_error_code VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Đây là schema minh họa, không phải schema bắt buộc. Với nhu cầu multi-provider, nên tách:

- **Preferred/eligible provider list:** các tuyến được phép theo policy.
- **Selected provider:** tuyến được chọn cho lượt gửi hiện tại.
- **Attempt history:** provider/attempt/outcome riêng cho từng lần submit.
- **Quota reservation:** mã reservation, quota scope và cost, không chứa credential.
- **Recipient/payload:** lưu trong bảng/đối tượng được bảo vệ; không dump ra log.

### Bảng attempt history

~~~sql
CREATE TABLE mail_submission_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL REFERENCES mail_outbox(id),
    provider_id VARCHAR(40) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    route_version VARCHAR(60) NOT NULL,
    attempt_number INT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(30),
    error_code VARCHAR(60),
    UNIQUE (mail_job_id, attempt_number)
);
~~~

Việc ghi `providerId` và `routeVersion` vào attempt record giúp truy vết sau khi thay credential hoặc chuyển tuyến mà không lưu password/token.

### Claim theo batch nhỏ

Một worker nên claim số job có thể thực sự xử lý trong ngắn hạn, không đưa toàn bộ backlog vào hàng đợi RAM:

~~~text
100,000 pending jobs
     |
     v
Small batch of ready jobs
     |
     v
Check route and capacity
     |
     +-- no quota -> defer
     |
     +-- permit -> SMTP submit
~~~

Nếu quota chỉ 5 mail/giây, claim 100.000 job vào một executor sẽ gây RAM pressure, lease expiry và có thể duplicate work khi nhiều replica cùng xử lý.

## 23. Tách “chưa có permit” khỏi “SMTP gửi thất bại”

Khi quota gate từ chối:

~~~text
mail_job.status = WAITING_PROVIDER_QUOTA
mail_job.available_at = next_allowed_time
mail_job.attempt_count unchanged
~~~

Không nên tăng `SMTP attempt_count` vì chưa gọi provider. Ngược lại, khi đã bắt đầu SMTP:

~~~text
mail_submission_attempt:
  provider = PRIMARY
  outcome  = ACCEPTED / REJECTED / UNKNOWN
~~~

Ví dụ state machine:

~~~mermaid
flowchart TD
    A[PENDING] --> B[Claim job]
    B --> C{Allowed provider route?}
    C -- No --> D[BLOCKED_POLICY]
    C -- Yes --> E{Quota and concurrency?}
    E -- No --> F[WAITING_QUOTA]
    F --> A
    E -- Yes --> G[SMTP submission]
    G --> H{Outcome}
    H -- Accepted --> I[SUBMITTED]
    H -- Temporary reject --> J[RETRY_LATER]
    H -- Permanent reject --> K[FAILED_PERMANENT]
    H -- Unknown --> L[UNKNOWN_OUTCOME]
    J --> A
~~~

`WAITING_QUOTA`, `BLOCKED_POLICY` và các trạng thái khác là enum nghiệp vụ gợi ý. Không có sẵn trong Spring Mail.

### Chỉ đánh dấu SUBMITTED sau khi có bằng chứng

`JavaMailSender.send(...)` trả thành công có nghĩa SMTP submission được ứng dụng nhìn nhận là hoàn tất, **không phải bảo đảm email đã vào inbox**. Provider có thể bounce hoặc hệ thống nhận có thể lọc sau đó.

Nếu connection đứt sau DATA và trước phản hồi cuối, client có thể không biết provider đã accepted hay chưa. Đánh dấu `FAILED_SAFE_TO_RETRY` rồi gửi lại ngay qua provider B có thể tạo hai email.

## 24. Routing theo policy và eligibility, không theo quota đơn thuần

Một provider chỉ nên nhận job nếu thỏa mãn:

1. Provider được phép cho notification type/tenant và môi trường.
2. Sender identity/domain đã được xác minh trên provider đó.
3. Loại nội dung, dữ liệu và region được policy cho phép.
4. Credential/config đang ở trạng thái sử dụng được.
5. Quota còn và circuit/health policy cho phép.
6. Outcome của lượt gửi trước không rơi vào trạng thái không chắc chắn.

Một enum route:

~~~java
public enum NotificationClass {
    SECURITY,
    TRANSACTIONAL,
    SUBSCRIPTION
}

public record RouteRequest(
        String tenantId,
        NotificationClass notificationClass,
        String senderProfileId) {
}

public interface MailRoutingPolicy {
    java.util.List<ProviderId> eligibleRoutes(
            RouteRequest request);
}
~~~

`eligibleRoutes(...)` phải trả danh sách đã được server phê duyệt, không dựa trực tiếp vào một tham số provider do client tùy ý truyền vào. Đối với ứng dụng đa tenant, policy phải xác định tenant được phép dùng sender/account nào trước khi xét quota.

### Route order và provider weights

Có thể chọn:

- Primary-first, secondary chỉ khi primary unavailable.
- Weighted split 90/10 trong giai đoạn migration.
- Tách email security và subscription sang những provider khác nhau.
- Region-based routing theo yêu cầu data handling.

Nhưng **weighted routing không tự đảm bảo quota**, và mỗi lần đổi tỷ trọng đều có thể ảnh hưởng reputation, Sender authentication và dải traffic của provider.

## 25. Ví dụ route dispatcher với sender registry và quota gate

Đây là khung minh họa nhấn mạnh thứ tự xử lý. Nó không phải module production hoàn chỉnh vì còn cần transaction/lease/transport classification.

~~~java
import jakarta.mail.internet.MimeMessage;
import java.time.Duration;
import org.springframework.mail.MailException;

public final class MultiProviderDispatcher {
    private final MailRoutingPolicy routingPolicy;
    private final ProviderSenderRegistry senders;
    private final ProviderQuotaGate quotas;
    private final MailJobRepository jobs;
    private final MailMessageFactory messages;

    public MultiProviderDispatcher(
            MailRoutingPolicy routingPolicy,
            ProviderSenderRegistry senders,
            ProviderQuotaGate quotas,
            MailJobRepository jobs,
            MailMessageFactory messages) {
        this.routingPolicy = routingPolicy;
        this.senders = senders;
        this.quotas = quotas;
        this.jobs = jobs;
        this.messages = messages;
    }

    public void dispatch(ClaimedMailJob job) {
        var eligible = routingPolicy.eligibleRoutes(
                job.routeRequest());

        if (eligible.isEmpty()) {
            jobs.blockByPolicy(job.id());
            return;
        }

        // Việc chọn route thực tế cần xét health và lịch sử attempt.
        ProviderId provider = eligible.get(0);
        ProviderRoutePolicy profile = job.policyFor(provider);

        MailQuotaCost cost = job.quotaCost();
        QuotaDecision decision = quotas.reserve(
                profile.quotaScopeKey(), cost);

        if (!decision.allowed()) {
            jobs.defer(
                    job.id(),
                    decision.retryAfter(),
                    "WAITING_PROVIDER_QUOTA");
            return;
        }

        try {
            var sender = senders.resolve(provider);
            MimeMessage message =
                    messages.compose(sender, job, profile);
            sender.send(message);
            jobs.markSubmitted(job.id(), provider);
        } catch (MailException ex) {
            jobs.recordSubmissionFailure(
                    job.id(), provider,
                    SafeMailErrorClassifier.classify(ex));
        } catch (Exception ex) {
            jobs.recordPreparationFailure(job.id(), provider);
        }
    }
}
~~~

`ClaimedMailJob`, `MailJobRepository`, `MailMessageFactory` và `SafeMailErrorClassifier` là các abstraction do ứng dụng xây dựng. `ProviderQuotaGate.reserve(...)` phải thực hiện nhiều hạn mức phối hợp theo policy thật; `MailQuotaCost` đã mô tả ở phần trước.

Trong production:

- Cần validate recipient, expiry, consent, tenant/sender authorization trước khi xin permit.
- Cần concurrency slot và giải phóng trong `finally`.
- `claim_token` phải được kiểm tra trong mọi state update.
- Không nên để một `catch(Exception)` gộp lỗi save trạng thái job với lỗi compose; phải tách các phase để tránh ghi sai outcome.
- Không hoàn permit khi chưa biết provider đã tính quota hay chưa.
- Nếu `send(...)` có outcome UNKNOWN, không tự ghi thành lỗi an toàn để fallback.
- Phải thiết kế khi `jobs.markSubmitted(...)` thất bại sau khi SMTP accepted.

**Giới hạn của ví dụ được nêu rõ:** nó minh họa việc resolve route, lấy quota riêng và chọn sender tương ứng; các đảm bảo exactly-once, distributed transactions và retry an toàn cần kiến trúc bổ sung.

## 26. Thứ tự compose và reserve quota

Một câu hỏi thiết kế là: nên tạo `MimeMessage` trước hay sau khi xin permit?

| Cách | Ưu điểm | Rủi ro |
|---|---|---|
| Compose trước reserve | Có thể tính raw MIME size và validation trước | Tốn CPU/IO cho job chưa được phép gửi |
| Reserve trước compose | Không render hàng loạt email khi hết quota | Compose fail có thể làm mất quota reservation |
| Preflight rồi reserve, compose cuối | Tránh lỗi hiển nhiên và vẫn giảm CPU | Raw MIME final size có thể khác estimate |

Một giải pháp kết hợp:

1. Preflight recipient, sender, size policy và tài nguyên cần thiết.
2. Tính cost message/recipient theo envelope.
3. Với provider có size hard limit, có thể cần compose/serialize để đo chính xác trước khi nộp.
4. Xin quota admission theo đúng cost.
5. Compose/serialize nếu chưa thực hiện và bắt đầu SMTP trong thời gian lease permit còn hợp lệ.
6. Hạch toán outcome theo semantics đã thiết kế.

Nếu một quota reservation được cấp rồi quá lâu mới dùng (vì queue executor), tốc độ submit thực tế có thể lệch policy. Vì thế permit thời gian ngắn cần được cấp **gần lúc thực sự gửi**, không reserve 10.000 token cho backlog rồi dùng kéo dài nhiều giờ mà không tính cửa sổ.

### SMTP accepted không phải delivered

Thông số `mail_submission_accepted_total` chỉ phản ánh việc provider nhận message; kết quả delivery và bounce cần webhook/DSN/message trace phù hợp với provider. Nếu provider A accepted rồi bounce sau đó, chuyển cùng job ngay sang B có thể là quyết định nghiệp vụ khác với retry cho một lỗi SMTP temporary rejection.

## 27. Retry theo lỗi từng provider, không dùng một chính sách chung cho tất cả

Khi Provider A từ chối một lần gửi, không phải lỗi nào cũng cho phép retry hoặc failover:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Invalid recipient syntax | Lỗi dữ liệu đầu vào | Từ chối/sửa dữ liệu; không retry provider khác |
| Sender not authorized | `From` chưa được phép tại A | Sửa sender policy; B chỉ nếu route hợp lệ |
| SMTP AUTH rejected | Credential A sai/hết quyền | Tạm dừng tuyến A, kiểm tra secret/token |
| Quota/rate throttled | Provider A tạm giới hạn | Defer theo quota và backoff; giữ job |
| SMTP temporary rejection trước acceptance | Chưa accepted theo bằng chứng có được | Retry có backoff khi policy cho phép |
| SMTP permanent rejection | Lỗi không được chấp nhận theo phản hồi | Không retry mù; phân loại nguyên nhân |
| Network failure trước khi kết nối | Submission chưa xảy ra | Có thể retry/failover theo policy |
| Connection lost sau DATA | Outcome có thể không rõ | Trạng thái UNKNOWN; tránh resend tự động |
| SMTP accepted | Provider nhận trách nhiệm xử lý | Mark SUBMITTED; delivery tracking riêng |
| HTTP API 429 | API rate limit | Tôn trọng `Retry-After` nếu có, theo provider |

**SMTP không có mã HTTP 429 chung.** Nó sử dụng SMTP replies như `421`, `450`, `451`, `452` và enhanced status code tùy ngữ cảnh/provider. Không phải mọi SMTP 4xx đều có nghĩa “hết quota”, và không phải mọi `MailSendException` đều là lỗi an toàn để thử lại.

### Không log nguyên provider exception

SMTP server có thể echo recipient trong response:

~~~text
451 4.7.0 Temporarily throttled recipient <user@example.net>
~~~

Log vận hành nên là:

~~~text
event=mail_submission_failure
jobId=mail-job-381
provider=PRIMARY
providerAccount=PRIMARY_PROD_ACCOUNT
failureCode=RATE_THROTTLED
attempt=2
~~~

Không log raw password, token, subject, địa chỉ người nhận hay toàn bộ MIME message. Ngoài bảo mật, log theo mã chuẩn hóa còn giúp so sánh lỗi giữa hai nhà cung cấp có format phản hồi khác nhau.

## 28. Exponential backoff, jitter và cửa sổ quota

Khi 10.000 job cùng bị Provider A từ chối, không nên lập lịch tất cả thử lại đúng sau 1 giây. Điều này tạo **retry storm**:

~~~text
Provider throttle → 10,000 jobs retry after 1s
                       |
                       v
          10,000 requests arrive together
                       |
                       v
             Provider throttles again
~~~

Một công thức:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

`n` là số lần lỗi liên tiếp; `d0` là delay cơ bản, `dmax` là trần. Thêm jitter:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

Nếu không muốn delay gần 0, đặt thêm minimum wait hoặc dùng biến thể jitter có sàn.

### Kết hợp backoff với quota

Thời điểm job được thử lại phải không sớm hơn các ràng buộc liên quan:

~~~text
nextAttemptAt =
  max(
    providerRateLimiterNextPermit,
    providerDailyQuotaResetOrRecheck,
    temporaryErrorBackoff,
    providerRetryAfterIfAvailable
  )
~~~

`Retry-After` là cơ chế của **HTTP**, phù hợp với provider dùng HTTPS email API. SMTP không có một header Retry-After HTTP chuẩn phổ quát; cần đọc response code và tài liệu provider.

Khi job đến hạn, dispatcher **vẫn xin permit**. Chờ hết backoff không đồng nghĩa quota provider đã còn.

### Deadline theo loại email

OTP có thể chỉ còn hiệu lực vài phút; email marketing có thể có lịch gửi dài hơn. Nếu `expires_at` đã qua, không nên gửi một OTP hết hạn chỉ vì cuối cùng quota cũng được cấp.

~~~java
if (job.expiresAt() != null
        && !clock.instant().isBefore(job.expiresAt())) {
    jobStore.markExpired(job.id());
    return;
}
~~~

`clock` và `jobStore` là dependency do ứng dụng tự định nghĩa. Không dùng một thời hạn retry chung cho mọi notification type.

## 29. Failover giữa hai nhà cung cấp không bảo đảm exactly-once

Một scenario quan trọng:

~~~text
Job J
  |
  +-- Provider A:
  |      SMTP DATA accepted by server
  |      connection drops before client sees final reply
  |
  +-- Client observes timeout
  |
  +-- Immediate retry to Provider B
         |
         +-- B accepts

Result: recipient may receive two emails.
~~~

Do SMTP delivery và database transaction không cùng một atomic commit, application thường không thể chứng minh **exactly-once email delivery** chỉ bằng outbox hoặc một request ID.

Các biện pháp:

- Ghi `attemptId` và `Message-ID` hoặc provider message ID nếu có theo thiết kế.
- Phân biệt trạng thái `UNKNOWN_OUTCOME` với rejected trước acceptance.
- Đối soát provider submission audit/message trace khi khả thi.
- Đối với thông báo có thể nhận trùng, thiết kế nội dung/idempotent business action phù hợp.
- Đối với email nhạy cảm hoặc có hậu quả nếu gửi trùng, xác định chính sách quyết định thủ công/đợi đối soát.
- Không tự động coi connection timeout là “chắc chắn chưa gửi”.

**Message-ID không tự ngăn provider gửi trùng**, và receiver không có nghĩa vụ deduplicate theo Message-ID. Nó là một tín hiệu correlation hữu ích, không phải bảo đảm exactly-once.

### Failover phải xét quota B như lần gửi mới

Nếu A đã bị throttle, B có thể vẫn còn quota. Nhưng chuyển job sang B cần:

1. B nằm trong `eligibleRoutes` của job.
2. B có sender permission và policy hợp lệ.
3. B còn rate/daily budget và concurrency capacity.
4. Không có trạng thái UNKNOWN gây nguy cơ duplicate chưa xử lý.
5. Attempt history ghi nhận việc chuyển tuyến.

Không lấy credential B ra chỉ để “đi vòng” một giới hạn của A khi hành vi gửi chưa đáp ứng chính sách chống lạm dụng.

## 30. Tách ưu tiên email bảo mật và marketing

Một hệ thống multi-provider thường gửi các loại thư có yêu cầu khác nhau:

| Lane | Ví dụ | Đặc điểm |
|---|---|---|
| SECURITY | OTP, thông báo đăng nhập bất thường | Deadline ngắn, cần ưu tiên |
| TRANSACTIONAL | Hóa đơn, xác nhận đơn hàng | Cần độ tin cậy và audit |
| SUBSCRIPTION | Bản tin, nội dung đăng ký | Có thể schedule và trải tải |
| BULK_CAMPAIGN | Chiến dịch marketing hợp lệ | Burst lớn, yêu cầu consent/suppression |

Nếu tất cả chạy chung một provider account quota, chiến dịch có thể chiếm hết budget khiến OTP chậm. Có thể:

- Tách provider/account/credential theo lane khi chính sách thực sự cho quota độc lập.
- Dành ngân sách riêng cho email ưu tiên.
- Dùng weighted fair queueing giữa các lane.
- Tạm dừng campaign khi quota thấp hoặc provider degraded.
- Đặt deadline cho job nhạy thời gian và skip khi hết hiệu lực.

**Tạo credential mới trên cùng account chưa chắc tăng quota.** Phải biết provider tính hạn mức ở cấp nào trước khi quyết định tách tài khoản.

### Fairness trong nhiều tenant

Nếu nhiều khách hàng tổ chức dùng chung provider account, một tenant có thể chiếm toàn bộ capacity. Một policy hai cấp:

~~~text
Global account quota
         |
         +-- Tenant A fair share
         +-- Tenant B fair share
         +-- Tenant C fair share
         |
         +-- Security reserved lane
~~~

Tenant quota chỉ **phân phối** năng lực còn lại; không tạo thêm quota provider. Khi tenant không dùng share, có thể cho các tenant khác mượn theo policy rõ ràng, tránh starvation và không vượt global cap.

## 31. Monitoring theo provider, account, lane và quota scope

Một hệ thống multi-provider phải trả lời:

- Provider nào đang được dùng, với tỷ lệ bao nhiêu?
- Credential/auth lỗi trên account nào?
- Quota còn bao nhiêu ở từng scope và reset khi nào?
- Có provider nào throttling nhiều hơn?
- Bao nhiêu job đang chờ vì quota so với chờ vì lỗi transport?
- Failover có làm tăng số email trùng/UNKNOWN không?
- Lane OTP có vượt SLA khi campaign đang chạy?

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| `mail_submission_total` | Số attempts/accepted/rejected theo provider |
| `mail_provider_auth_failure_total` | Phát hiện credential sai/hết hạn |
| `mail_provider_throttle_total` | Tỷ lệ throttling theo provider/account |
| `mail_provider_quota_remaining` | Budget ước tính, có thể có độ trễ |
| `mail_quota_reservation_denied_total` | Số job chưa được gửi vì quota |
| `mail_outbox_pending` | Backlog theo lane/provider |
| `mail_outbox_oldest_age_seconds` | Thời gian chờ lâu nhất, đối chiếu SLA |
| `mail_submission_duration_seconds` | Latency submission p50/p95/p99 |
| `mail_provider_failover_total` | Số job được route dự phòng |
| `mail_submission_unknown_total` | Số attempt không chắc outcome |
| `mail_credential_rotation_failure_total` | Sự cố khi thay secret |
| `mail_quota_gate_error_total` | Redis/DB quota service lỗi |

### Metric labels phải có cardinality thấp

Nên dùng các giá trị cố định:

~~~text
provider=PRIMARY
account=PROD_ORDERS
lane=TRANSACTIONAL
outcome=THROTTLED
~~~

Không dùng:

~~~text
recipient=user@example.net
passwordVersionSecret=...
jobId=unique-for-every-message
subject="Invoice #12345 for Alice"
~~~

Recipient là PII; jobId có cardinality cao; secret không được log; subject có thể chứa nội dung nhạy cảm. Sử dụng job ID trong log/tracing được bảo vệ, không làm metric label.

### Thực hiện cảnh báo theo ảnh hưởng

Ví dụ:

- Primary authentication failure tăng sau rotation secret.
- Secondary quota gần hết dù là tuyến dự phòng.
- Provider A throttle kéo dài và `mail_outbox_oldest_age_seconds` tăng.
- Account usage trên console tăng nhưng app logs không có submission tương ứng — có thể còn ứng dụng khác dùng cùng credential/account.
- Tỷ lệ fallback tăng đột biến sau deployment mới.
- OTP backlog vượt mục tiêu dù campaign vẫn được gửi.

Đừng chỉ cảnh báo khi SMTP error rate cao. Một limiter có thể **đang hoạt động chính xác** nhưng backlog vẫn không giảm vì nguồn job vào vượt quota; đó vẫn là tình huống cần vận hành giải quyết.

## 32. Unit test: chọn đúng JavaMailSender theo provider

Khi có hai bean `JavaMailSender`, một lỗi wiring có thể khiến tuyến secondary dùng nhầm primary sender. Có thể kiểm thử registry bằng Mockito:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class ProviderSenderRegistryTest {

    @Test
    void resolvesDistinctSendersForEachRoute() {
        JavaMailSender primary =
                mock(JavaMailSender.class);
        JavaMailSender secondary =
                mock(JavaMailSender.class);

        ProviderSenderRegistry registry =
                new ProviderSenderRegistry(
                        primary, secondary);

        assertThat(registry.resolve(ProviderId.PRIMARY))
                .isSameAs(primary);
        assertThat(registry.resolve(ProviderId.SECONDARY))
                .isSameAs(secondary);
        assertThat(registry.resolve(ProviderId.PRIMARY))
                .isNotSameAs(
                        registry.resolve(ProviderId.SECONDARY));
    }
}
~~~

Test này xác minh logic registry, **không** xác minh Spring đã inject đúng qualifier vào hai bean. Để kiểm tra wiring thật, có thể dùng `@SpringBootTest` hoặc một context slice với cấu hình test không chứa credential thật.

### Test không vô tình gọi send của provider còn lại

Trong test service/dispatcher:

~~~java
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.ArgumentMatchers.any;

// Khi policy chỉ cho PRIMARY:
dispatcher.dispatch(job);

verify(primary).send(any(jakarta.mail.internet.MimeMessage.class));
verifyNoInteractions(secondary);
~~~

Đây là khung assertion dựa trên test fixture và mock `dispatcher`, `primary`, `secondary` do dự án xây dựng. Nếu application có logic dự phòng, cần chủ động thiết lập failure/route policy rồi xác minh **chỉ** những nhánh được phê duyệt mới chạy.

## 33. Test tách credential và bảo vệ configuration

Unit test không nên chứa secret production. Với cấu hình test:

~~~text
PRIMARY_USERNAME=test-primary-user
PRIMARY_PASSWORD=fake-primary-password
SECONDARY_USERNAME=test-secondary-user
SECONDARY_PASSWORD=fake-secondary-password
~~~

Các test nên xác minh:

1. Bean primary dùng đúng host/port/username test của primary.
2. Bean secondary dùng đúng giá trị secondary.
3. Cả hai dùng TLS policy đúng cấu hình.
4. Một profile thiếu secret fail fast trước khi nhận job.
5. `toString()` của đối tượng cấu hình hoặc logging không hiển thị password/token.
6. Một SMTP authentication failure ở A không làm ứng dụng tự thay password của B.
7. Route profile chỉ chứa secret **reference/version**, không chứa secret trong outbox hoặc job log.

Ví dụ test bean properties:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class MultiSenderConfigurationTest {
    @Test
    void keepsTwoProviderConnectionsSeparate() {
        var configs = new MultiProviderMailProperties(
                new MultiProviderMailProperties.SmtpEndpoint(
                        "smtp-a.example.test", 587,
                        "user-a", "fake-a",
                        "orders@example.com", true, true, 2),
                new MultiProviderMailProperties.SmtpEndpoint(
                        "smtp-b.example.test", 587,
                        "user-b", "fake-b",
                        "orders@example.com", true, true, 3));

        MultiProviderMailConfiguration factory =
                new MultiProviderMailConfiguration();
        JavaMailSenderImpl a = (JavaMailSenderImpl)
                factory.primaryMailSender(configs);
        JavaMailSenderImpl b = (JavaMailSenderImpl)
                factory.secondaryMailSender(configs);

        assertThat(a.getHost()).isEqualTo("smtp-a.example.test");
        assertThat(b.getHost()).isEqualTo("smtp-b.example.test");
        assertThat(a.getUsername()).isEqualTo("user-a");
        assertThat(b.getUsername()).isEqualTo("user-b");
        assertThat(a.getPassword()).isNotEqualTo(b.getPassword());
    }
}
~~~

Đây là test factory không kết nối SMTP. Kiểm tra `getPassword()` trong test fixture giả không có nghĩa production code được phép log/hiển thị password.

### Test rotation cần kiểm tra connection mới

Khi rotate secret, một test cấu hình có thể xác nhận instance mới được tạo với secret version mới. Nhưng một SMTP connection cũ còn authenticated vẫn có thể hoạt động; nên có integration test với sandbox provider/test double để xác nhận connection mới dùng credential mới và credential cũ đã bị revoke theo chính sách.

## 34. Test quota độc lập và quota dùng chung

Đây là hai trường hợp quan trọng:

### Trường hợp A: hai provider quota độc lập

~~~text
Primary remaining = 1
Secondary remaining = 3

Reserve cost 1 for PRIMARY
  -> Primary remaining = 0
  -> Secondary remains 3

Reserve cost 1 for SECONDARY
  -> Secondary remaining = 2
~~~

Test phải khẳng định việc dùng provider A **không tiêu thụ budget B** khi hai scope thực sự độc lập.

### Trường hợp B: hai credential cùng quota account

~~~text
Account quota remaining = 1
Credential ORDER uses account PRIMARY_PROD
Credential SECURITY uses account PRIMARY_PROD

Both request 1 permit concurrently:
    exactly one granted
    one denied
~~~

Test phải xác nhận quota key là **account scope**, không phải credential ID. Nếu hai worker cùng nhìn thấy một token, phép reserve phải nguyên tử.

### Test với nhiều replica

Một integration test distributed limiter có thể mô phỏng 100 worker đồng thời xin 1 token từ bucket capacity 10 trong cùng một cửa sổ không refill:

~~~text
Expected:
    10 grants
    90 denials
    total reserved = 10
~~~

Không chỉ dùng local in-memory limiter của mỗi instance để thử multi-replica. Kiểm tra trạng thái shared store sau phép reserve và bảo đảm test có clock/window xác định.

### Test quota theo recipient và window

Những tình huống khác:

| ID | Điều kiện | Kết quả mong đợi |
|---|---|---|
| QT-01 | 1 message, 1 recipient | Trừ đúng cost |
| QT-02 | 1 message, 20 recipients | Trừ 20 ở recipient quota, 1 ở message quota |
| QT-03 | Message vượt max recipients | Từ chối/chia theo policy trước send |
| QT-04 | Cost lớn hơn burst capacity | Phát hiện cấu hình/admission sai, không chờ vô hạn |
| QT-05 | Primary cạn, secondary còn | Route B chỉ khi eligible và outcome A an toàn |
| QT-06 | Cả hai cạn | Job vẫn trong durable outbox |
| QT-07 | Rotate credential cùng account | Account quota không tự reset |
| QT-08 | Provider dùng rolling 24h | Không dùng reset calendar day sai |
| QT-09 | Distributed store timeout | Không uncontrolled fail-open |
| QT-10 | Worker crash sau reserve | Reservation và job state được phục hồi theo policy |
| QT-11 | Lỗi auth trên A | Chỉ A bị degrade/paused, không mutate B |
| QT-12 | Multi-tenant một account | Tổng quota vẫn được giới hạn, fairness theo tenant |

## 35. Kiểm thử tích hợp bằng SMTP sink và provider sandbox

Unit test kiểm tra bean/route/quota algorithm; nhưng cần kiểm thử tích hợp để biết đúng credential thực sự được dùng trên đường SMTP.

Một cấu hình test có thể dùng:

~~~text
App under test
        |
        +-- PRIMARY   -> SMTP sink A / test port A
        |
        +-- SECONDARY -> SMTP sink B / test port B
~~~

Kịch bản:

1. Gửi job có route PRIMARY, xác nhận sink A nhận và sink B không nhận.
2. Gửi job có route SECONDARY, xác nhận ngược lại.
3. Mô phỏng SMTP AUTH failure ở A, xác nhận trạng thái A và retry/failover theo policy.
4. Mô phỏng temporary 4xx, xác nhận job defer và không retry storm.
5. Mô phỏng cạn quota B, xác nhận không route B bất chấp giới hạn.
6. Mô phỏng connection rơi sau DATA, xác nhận outcome UNKNOWN chứ không tự retry qua cả A và B.
7. Kiểm tra sender From và MIME khi chuyển tuyến.
8. Kiểm tra tài khoản test không có permission đọc mailbox hoặc Send As không được cấp theo provider-specific policy.

Một SMTP sink như Mailpit hoặc GreenMail có thể capture message mà không gửi đến người nhận thật. Tuy nhiên, sink đơn giản không tự mô phỏng quota thực tế. Cần test double có khả năng chủ động trả mã SMTP/giữ connection, hoặc dùng sandbox provider được phê duyệt cho tình huống authentication/throttling.

**Không cố tình vượt quota hoặc tạo spam trên production để “kiểm tra” tính đúng đắn.** Test rate/credential cần sử dụng tài khoản test và địa chỉ giả.

## 36. Kiểm soát quyền truy cập secret trong CI/CD và runtime

Quản lý credential riêng không dừng ở việc đặt hai biến environment. Cần kiểm soát vòng đời:

| Giai đoạn | Nguy cơ | Kiểm soát |
|---|---|---|
| Development | Developer copy key production về laptop | Dùng sandbox credentials; không cấp quyền production |
| Build | Secret nằm trong source/image layer | Không inject secret khi build nếu không cần |
| CI test | Print config/stack trace chứa password | Fake secrets, masking và log policy |
| Deploy | Secret bị gắn vào sai environment | Scope theo workload/namespace, approval |
| Runtime | Pod/service đọc được key của provider khác | RBAC/secret mount theo workload cần thiết |
| Rotation | Key cũ vẫn hoạt động | Audit, revoke và verify |
| Incident | Exports/backup lưu raw credential | Access control, retention, encryption |
| Decommission | Credential/profile vẫn tồn tại | Revoke key, ngừng queue/route và xóa quyền |

### Workload identity và namespace

Nếu có thể, secret của Provider B chỉ được mount/inject cho worker được phép gửi qua B. Nếu tất cả provider credentials đều được cấp vào một process, process đó trở thành một điểm có khả năng sử dụng mọi tuyến; thiết kế như vậy có thể chấp nhận khi router là thành phần tin cậy nhưng phải coi nó là **high-value workload** với audit, least privilege và network egress phù hợp.

Với yêu cầu phân tách nghiêm ngặt, có thể dùng các **dispatcher process riêng cho từng provider** thay vì một monolith giữ tất cả secrets.

## 37. Khi nào nên tách provider adapter thành service riêng?

Trong ứng dụng nhỏ, hai `JavaMailSender` bean có thể đủ. Khi hệ thống lớn, một sender service độc lập cho mỗi provider có ưu điểm:

~~~text
Shared notification / outbox service
                    |
            Approved route policy
                    |
             Internal broker
             /             \
            v               v
    Provider A worker   Provider B worker
    A secret only       B secret only
    A quota only        B quota only
            |               |
            v               v
          SMTP A          SMTP B
~~~

Lợi ích:

- Workload A không cần đọc credential B.
- Provider-specific libraries/token refresh không nằm trong toàn ứng dụng.
- Lỗi hoặc dependency outage của A có thể được cô lập.
- Quota admission và connection pool theo provider dễ được đo.
- Có thể scale worker theo throughput/latency của từng tuyến.

Đánh đổi:

- Tăng số dịch vụ, deployment, queue và monitoring phải quản lý.
- Cần idempotency, attempt history và routing state chia sẻ.
- Việc chuyển provider có thể phát sinh duplicate nếu outcome chưa rõ.
- Có thể phức tạp khi một account quota được chia bởi nhiều worker service.

Không nên tách thành microservice chỉ để có hai SMTP passwords. Quy mô, blast radius, yêu cầu compliance và nhu cầu vận hành mới quyết định.

## 38. Runbook khi một provider gặp sự cố

### Tình huống A: authentication của primary bắt đầu thất bại

Ví dụ:

~~~text
PRIMARY auth failures ↑
SECONDARY healthy
ORDER_RECEIPT backlog age ↑
~~~

Hướng xử lý:

1. Kiểm tra provider A, account/credential và thời điểm bắt đầu lỗi.
2. Xem lịch rotate secret, deployment, thay đổi OAuth scopes hoặc policy SMTP AUTH.
3. Không log/copy password hay raw access token vào incident ticket.
4. Tạm dừng A nếu tiếp tục gửi chỉ tạo auth failures.
5. Kiểm tra B có route eligibility, sender verification, quota và permission hợp lệ không.
6. Chỉ chuyển các job có outcome chưa từng accepted/không thuộc UNKNOWN theo policy.
7. Sửa secret/config A, kiểm tra connection mới rồi khôi phục dần.
8. Đối soát số attempts và queue state để không bỏ sót/duplicate.

### Tình huống B: quota primary cạn sớm

~~~text
PRIMARY daily recipient quota remaining = 0
SECONDARY account quota remaining > 0
Outbox pending = 12,000
~~~

Không chuyển ngay 12.000 job sang B:

- Xác định chính sách B có cho phép loại nội dung này không.
- Xác định quota B thật và account/sender scope.
- Xem các job đã accepted qua A chưa.
- Giữ ngân sách cho email quan trọng; tạm dừng lane thấp nếu cần.
- Đặt lịch gửi theo capacity B, không flood B trong một đợt.
- Theo dõi error/complaint/reputation của B sau khi chuyển tuyến.

### Tình huống C: quota store (Redis/DB) bị lỗi

Giải pháp mặc định với workload không khẩn cấp có thể là **fail closed**: chưa gửi, giữ outbox. Với email quan trọng, có thể dùng bounded fallback **đã được phê duyệt trước** và có giới hạn toàn cụm. Không cho tất cả replica bỏ qua quota gate và gửi tự do.

### Tình huống D: credential nghi bị lộ

- Disable hoặc revoke secret bị ảnh hưởng.
- Đối soát provider submission audit với job hợp lệ.
- Kiểm tra provider-side Send As, mailbox/API grants và IP allowlist.
- Cấp secret mới với quyền tối thiểu.
- Không tự cho route khác kế thừa quyền rộng hơn.
- Ghi nhận/quản lý backlog trong thời gian ngừng gửi.

## 39. Anti-pattern trong quản lý credential và quota đa provider

### 39.1. Một SMTP username/password cho tất cả provider

Mỗi provider/account cần credential tương ứng. Không copy một password vào nhiều tuyến vì sự cố lộ sẽ ảnh hưởng toàn hệ thống, và cơ chế auth có thể khác nhau.

### 39.2. Dùng chung account quản trị thay cho service identity

Ứng dụng chỉ cần gửi thư không cần quyền đọc mọi mailbox hoặc quản trị tenant. Dùng tài khoản chuyên dụng và grants tối thiểu.

### 39.3. Hai JavaMailSender nhưng chung global credential

Hai bean không làm tăng cách ly nếu vẫn tham chiếu chung một secret có quyền quá rộng. Hãy kiểm tra quyền, account scope, không chỉ class/bean name.

### 39.4. Cập nhật host/username/password trên một singleton giữa các request

Đây là race condition trong môi trường nhiều thread; có thể gửi sai tuyến hoặc authenticate với danh tính khác. Dùng adapter/sender riêng, cấu hình ổn định.

### 39.5. Cho request chọn arbitrary SMTP endpoint

Đây có thể dẫn đến SSRF hoặc lạm dụng relay. Client không được tự truyền host, port, credential và From không qua authorization.

### 39.6. Cứ tạo API key mới là có quota mới

Provider có thể hạch toán quota ở cấp organization/account. Phải xác định `quotaScopeKey` thật và dùng shared counter.

### 39.7. Một rate limiter chung cho tất cả provider độc lập

Quota A cạn có thể làm B bị chặn dù B còn capacity. Nên có counter theo đúng quota scope, đồng thời cân nhắc giới hạn toàn organization nếu thực sự tồn tại.

### 39.8. Một local token bucket cho mỗi pod trên account shared

Khi số replica tăng, tổng rate tăng vượt quota. Cần distributed limiter hoặc dispatcher tập trung.

### 39.9. Dùng maxPoolSize làm rate limit

Số worker đồng thời không phải số messages/second hay recipients/day. Cần rate quota và concurrency gate riêng.

### 39.10. Không tính Cc/Bcc trong recipient quota

Một send call có thể gửi cho nhiều envelope recipients. Hạch toán theo đơn vị provider yêu cầu, không chỉ theo số lời gọi `send`.

### 39.11. Chuyển sang secondary ngay sau mọi exception

SMTP outcome có thể UNKNOWN và gây duplicate. Phải phân loại điểm lỗi/acceptance trước failover.

### 39.12. Không kiểm tra quyền From trên secondary

Một địa chỉ đã verified ở A chưa chắc hợp lệ ở B. Provider B có thể từ chối hoặc rewrite sender; DKIM/SPF/DMARC cũng cần được cấu hình đúng.

### 39.13. Giữ credential trong job outbox

Credential có thể nằm lâu trong database và được export qua log/support. Outbox chỉ giữ route/profile ID và dữ liệu nghiệp vụ được bảo vệ.

### 39.14. Rotate key rồi reset quota counter

Credential version thay đổi không đồng nghĩa account đã có ngân sách mới. Quota key phải ổn định theo quota scope.

### 39.15. Gửi trước, kiểm tra quota sau

Kiểm đếm sau khi `send(...)` đã xảy ra không ngăn được burst vượt quota. Reserve/cấp permit trước submission; ghi outcome riêng sau đó.

### 39.16. Hoàn toàn bộ permit mỗi khi gặp MailException

Provider có thể đã tính quota hoặc accepted message dù client thấy lỗi. Chỉ refund khi chắc chắn an toàn và mechanism có semantics rõ.

### 39.17. Dùng HTTP 429 parser cho mọi SMTP exception

HTTP email API và SMTP là hai giao thức khác nhau. `Retry-After` thuộc HTTP, còn SMTP dùng response codes/enhanced codes theo provider.

### 39.18. Claim hàng chục nghìn job vào RAM khi quota thấp

Đây là lỗi backpressure: giữ worker/lease, tăng nguy cơ mất trạng thái khi restart. Dùng batch nhỏ, outbox bền vững và `available_at`.

### 39.19. Cho marketing chiếm hết ngân sách OTP

Quản lý credential/quota riêng nhằm giảm blast radius và bảo vệ email quan trọng. Không dùng chung một budget không ưu tiên khi các luồng có SLA khác biệt.

### 39.20. Chỉ theo dõi SMTP errors mà không theo dõi quota denials

Một limiter hoạt động đúng có thể giữ toàn bộ backlog trong queue mà không phát sinh SMTP errors. Theo dõi waiting age và accepted throughput bên cạnh errors.

## 40. Quy trình triển khai nhiều provider trong ứng dụng Spring

Một lộ trình thực tế:

1. **Inventory tuyến gửi:** provider, account, credential, sender identity, domain, environment và notification class.
2. **Thiết lập boundary:** provider profile IDs và các workload được quyền đọc secret tương ứng.
3. **Xác minh sender:** From/Reply-To, Send As, domain, DKIM/SPF/DMARC ở từng provider.
4. **Thu thập quota thật:** rate theo message/recipient, daily budget, window reset, concurrency, size và quota scope.
5. **Lưu secret an toàn:** secret manager, workload identity, rotation, revoke, audit.
6. **Tạo sender/adapter riêng:** `JavaMailSender` với qualifier cho SMTP, HTTP adapter riêng nếu dùng API.
7. **Định nghĩa route policy:** chỉ các provider được phê duyệt theo tenant, category và environment.
8. **Xây quota gate:** shared/distributed khi quota cùng chia giữa replica, unit/cost rõ ràng.
9. **Thêm concurrency control:** riêng từng provider/account, không đồng nhất với rate.
10. **Tạo durable outbox:** lưu intent, route eligibility, attempt history, `available_at` và expiry.
11. **Định nghĩa retry/failover:** throttling, permanent, temporary và UNKNOWN riêng.
12. **Bảo vệ lane quan trọng:** OTP, giao dịch, newsletter bằng priority/fairness và budget phù hợp.
13. **Bổ sung metrics và logs an toàn:** provider, route, version, quota, result, attempt, backlog; không raw secret/recipient.
14. **Kiểm thử:** wiring, fake credentials, quota isolation/shared scope, multi-replica races, SMTP failure/failover.
15. **Rollout:** sandbox rồi traffic nhỏ, đo accepted throughput, auth errors, quota consumption và bounce.
16. **Vận hành:** runbook revoke/rotate, provider outage, quota depleted và queue recovery.
17. **Decommission:** dừng route, drain hoặc reroute job hợp lệ, thu hồi key, xóa quyền và cập nhật tài liệu quota.

### Tiêu chí hoàn tất triển khai

| Điều kiện | Bằng chứng kỹ thuật |
|---|---|
| Credential A và B độc lập | Secret references và quyền truy cập workload tách biệt |
| Quyền sender giới hạn | Provider verified sender / Send As grants chính xác |
| Đúng tuyến cho từng job | Route integration test và attempt history |
| Quota không bị dùng chéo sai | Unit/distributed integration tests cho quota scope |
| Hết quota không mất email | Durable queue + defer state |
| Credential rotation không phá B | Sandbox rotation/drain test |
| Retry không làm flood provider | Backoff, jitter, rate-gate admission |
| UNKNOWN outcome được xử lý | Job state và chính sách replay/failover |
| Không lộ password/token | Secret scanning, log policy, CI review |
| Operability đầy đủ | Dashboard, alerts, runbook và audit |

## 41. Câu hỏi thường gặp

**Có thể chỉ dùng một `spring.mail.*` khi có hai provider không?** Spring Boot thường auto-configure một sender mặc định. Với nhiều tuyến SMTP, nên tạo các `JavaMailSender` bean hoặc adapter riêng có cấu hình rõ ràng và dùng qualifier/registry.

**Hai bean JavaMailSender có tự tách quota không?** Không. Quota được provider áp theo account/organization/credential/sender và phải được dispatcher điều phối theo scope thực tế.

**Một API key mới có đồng nghĩa quota ngày mới không?** Không. Nhiều keys có thể cùng share account quota. Cần kiểm tra chính sách provider.

**Có nên cấp một account có mọi quyền để gửi từ nhiều domain?** Không mặc định. Least privilege và sender verification theo từng provider/profile giảm hậu quả khi credential bị lộ.

**Có thể dùng cùng địa chỉ From cho cả hai provider?** Có thể nếu cả hai được phép gửi từ địa chỉ/domain đó và các yêu cầu authentication/deliverability được đáp ứng.

**Nên để credential ở `application.yml` không?** Không lưu giá trị thật trong source. Có thể sử dụng placeholder đọc từ secret manager hoặc runtime secret injection.

**Có nên truyền SMTP password vào queue job để gửi lại sau restart?** Không. Queue/outbox nên giữ provider profile ID và thông tin cần thiết; worker tra cứu secret được cấp ở runtime.

**Credential rotation có làm provider quota reset không?** Không nếu quota scope là account hoặc organization. Counter phải gắn đúng quota key, không theo mật khẩu.

**OAuth2 có tự xử lý refresh nếu cấu hình token vào password field?** Không. Cần cơ chế lấy và làm mới token theo hạn sử dụng và provider protocol; không dùng token tĩnh hết hạn.

**Khi Provider A cạn quota, có thể gửi qua B không?** Chỉ khi B được phê duyệt cho job đó, sender hợp lệ, B còn quota và outcome của lần gửi A đủ rõ để tránh duplicate.

**Nếu provider trả temporary 4xx, có nên retry ngay?** Không. Phân loại lỗi, đặt backoff/jitter và xin permit lại; không phải mọi 4xx đều là rate limit.

**Có thể dùng `maxPoolSize=5` để bảo đảm không vượt 5 thư/giây?** Không. Pool size giới hạn concurrent tasks, không giới hạn tốc độ dài hạn.

**Khi nhiều pod cùng dùng một provider account phải làm gì?** Dùng shared quota limiter/dispatcher hoặc cơ chế phân chia quota toàn cụm được kiểm soát. Local limiter độc lập không đủ.

**Tại sao cần attempt history riêng theo provider?** Để biết job đã được gửi thử qua tuyến nào, outcome ra sao và có khả năng duplicate khi failover không.

**Đã gửi qua A thành công có cần gửi lại qua B nếu chưa thấy inbox?** Không tự động. SMTP acceptance không đảm bảo inbox delivery, nhưng retry từ B có thể tạo thư trùng. Cần theo dõi bounce/delivery và chính sách nghiệp vụ riêng.

**Có nên route tự động theo giá thấp nhất?** Chỉ sau khi đáp ứng sender authorization, consent, region/compliance, quota, SLA và policy của nhà cung cấp. Giá không phải tiêu chí duy nhất.

**Làm sao bảo vệ OTP khỏi marketing batch?** Tách lane/account khi thực sự có budget riêng hoặc bảo lưu quota và ưu tiên dispatch trên account dùng chung.

**Nếu Redis limiter hỏng, có được gửi không giới hạn để không mất OTP?** Không nên. Cần fail-closed hoặc bounded fallback đã được thiết kế với giới hạn toàn cụm, và outbox giữ job đến khi có capacity.

**Có nên log SMTP username/password khi lỗi auth?** Không. Chỉ log provider ID, account ID, config version, failure code và job ID an toàn.

**Một provider dự phòng không có SMTP mà chỉ có HTTP API thì sao?** Dùng adapter tương ứng. `JavaMailSender` cho SMTP; email API qua HTTP cần client/adaptor riêng, cùng chung routing/quota/outbox abstraction.

## 42. Tổng kết

Trong **Spring Framework Mail** với nhiều nhà cung cấp, **credential và quota phải được quản lý như hai trục độc lập nhưng có quan hệ**:

- **Credential** trả lời: ứng dụng xác thực bằng danh tính nào, được phép gửi từ sender nào, và ai có quyền đọc/rotate/revoke secret?
- **Quota** trả lời: provider/account/sender nào bị giới hạn, giới hạn theo đơn vị gì, ở cửa sổ nào và bao nhiêu năng lực còn có thể sử dụng?

Một kiến trúc đầy đủ:

~~~text
Business command
     |
     v
Authorized notification intent
     |
     v
Durable outbox / attempt history
     |
     v
Route eligibility (tenant, type, sender)
     |
     +---------------------+
     |                     |
     v                     v
Provider A profile     Provider B profile
  - secret A             - secret B
  - allowed From A       - allowed From B
  - quota scope A        - quota scope B
  - rate/concurrency A   - rate/concurrency B
     |                     |
     v                     v
JavaMailSender A       JavaMailSender B
     |                     |
     +----------+----------+
                |
                v
       Outcome classification
       Accepted / Retry / Unknown
                |
                v
           Outbox state
~~~

**Những nguyên tắc then chốt:**

1. Tách secret/provider/production environment và cấp quyền gửi tối thiểu.
2. Không cho client tự quyết định host, credential, From hoặc provider không được phê duyệt.
3. Xác định quota theo scope thật, **không đồng nhất credential ID với quota account ID**.
4. Dùng rate, daily quota và concurrency controls với đơn vị đúng, phối hợp toàn cụm khi cần.
5. Giữ ý định gửi bền vững; thiếu permit nghĩa là **chưa đến lượt gửi**, không phải lỗi SMTP.
6. Rotation/failover không được xóa trạng thái quota hoặc bỏ qua nguy cơ submission UNKNOWN.
7. Giám sát provider/account/route/outcome và bảo vệ dữ liệu credential/recipient trong log.

Khi các giới hạn được mô hình hóa đúng, việc thêm nhà cung cấp mới không chỉ là cấu hình một host SMTP khác. Đó là mở thêm một **miền credential, sender permission, năng lực gửi và trách nhiệm vận hành** được quản lý độc lập, trong khi toàn bộ job vẫn được kiểm soát nhất quán bởi chính sách nghiệp vụ và trạng thái gửi.
