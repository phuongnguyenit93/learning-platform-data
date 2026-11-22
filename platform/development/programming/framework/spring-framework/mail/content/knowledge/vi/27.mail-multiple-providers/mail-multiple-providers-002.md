# Cấu hình sender theo tenant hoặc miền

Một ứng dụng **Spring Framework Mail** thường bắt đầu bằng một SMTP account và một `JavaMailSender`: mọi email dùng chung host, username, password và địa chỉ `From`. Cách đó phù hợp với sản phẩm chỉ có một tổ chức. Nhưng ở hệ thống **multi-tenant**, mỗi khách hàng doanh nghiệp có thể sử dụng miền gửi riêng, danh tính thương hiệu riêng, chính sách thông báo khác nhau hoặc thậm chí một SMTP provider khác.

Giả sử một nền tảng phục vụ hai tổ chức:

~~~text
Tenant Acme:
  Sending domain: mail.acme.example
  From: orders@mail.acme.example
  SMTP provider: Relay A
  Account: acme-transactional

Tenant Beta:
  Sending domain: notify.beta.example
  From: notices@notify.beta.example
  SMTP provider: Relay B
  Account: beta-primary
~~~

Nếu ứng dụng chỉ đổi `helper.setFrom(...)` nhưng tiếp tục dùng credential của Acme để gửi email Beta, hệ thống **chưa thực sự chọn sender theo tenant**. Provider có thể từ chối message, DNS authentication không phù hợp, hoặc hai tenant bị gộp chung quota và quyền của một account. Ngược lại, nếu client được tự nhập SMTP host, password và sender account cho mỗi request, ứng dụng có nguy cơ trở thành một kênh gửi thư trái phép.

**Cấu hình sender theo tenant hoặc miền** nghĩa là ứng dụng có một **routing policy có thẩm quyền**: xác minh tenant thực, chọn sending domain đã được phê duyệt, xác định purpose email, chọn provider/account có quyền dùng miền đó, nạp credential an toàn, tạo MIME message với From/Reply-To phù hợp và gửi qua transport được chọn. Bài học này trình bày kiến trúc, Spring Boot configuration, `JavaMailSenderImpl`, registry động, bảo mật, DNS, failover, outbox, quota, feedback và các chiến lược kiểm thử.

## 1. Các khái niệm phải tách biệt

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tenant | `tenant-acme` | Đơn vị khách hàng có dữ liệu và quyền riêng |
| Sending domain | `mail.acme.example` | Miền được dùng cho identity và xác thực email |
| Provider | Relay A | Nhà cung cấp dịch vụ gửi |
| Provider account/subaccount | `acme-tx` | Phạm vi credential, quota và chính sách tại provider |
| SMTP endpoint | `smtp.relay-a.example:587` | Host/port nhận kết nối |
| SMTP credential | Username/password/token | Bí mật cho SMTP AUTH |
| Header From | `orders@mail.acme.example` | Danh tính người gửi hiển thị với recipient |
| Reply-To | `support@acme.example` | Địa chỉ nhận trả lời |
| Envelope sender | `bounce@bounces.acme.example` | SMTP MAIL FROM, liên quan bounce |
| Mail purpose | `SECURITY` / `TRANSACTIONAL` | Phân loại thông báo theo nghiệp vụ |
| Sender route | Tenant + domain + purpose → account | Quy tắc chọn transport được phép |

Các quan hệ không nhất thiết một-một. Một tenant có thể dùng nhiều domain, một domain có thể có nhiều account, một provider có thể phục vụ nhiều tenant, và một tenant cũng có thể có cả primary lẫn backup provider.

Phải phân biệt **sender identity** với **SMTP principal**. Header From hiển thị một địa chỉ không chứng minh SMTP account có quyền gửi thay miền đó. Đổi From không đồng nghĩa đổi account.

## 2. Vì sao cần routing theo tenant?

Các động lực chính:

1. **Thương hiệu:** email tới khách hàng của Acme dùng identity của Acme đã được xác minh.
2. **Quyền hạn:** tenant A không sử dụng credential hoặc domain của tenant B.
3. **Cách ly sự cố:** credential của một tenant bị thu hồi không mặc nhiên dừng toàn bộ các tenant khác.
4. **Quota:** có thể phân bổ và đo traffic theo tenant, account, purpose và provider.
5. **Uy tín gửi:** bounce/complaint của bulk marketing không nên làm hỏng luồng security nhiều hơn mức hạ tầng bắt buộc.
6. **Tuân thủ:** có tenant cần giới hạn provider, vùng xử lý hoặc retention.
7. **Vận hành:** có thể chuyển provider, rotate credential, tạm dừng domain và audit route.
8. **Phát triển:** thêm tenant mới không cần sửa business logic gửi email.

Tách SMTP username chưa chắc tách hoàn toàn quota/reputation. Một provider có thể áp hạn mức ở cấp **organization, account cha, IP pool hoặc sending domain**. Nếu đây là yêu cầu quan trọng, phải kiểm tra nhà cung cấp thực sự cách ly ở mức nào.

## 3. Những mô hình phân tách sender phổ biến

| Mô hình | Đặc điểm | Điểm mạnh | Rủi ro/chi phí |
| --- | --- | --- | --- |
| Một account platform | Tất cả tenant dùng chung credential | Đơn giản | Chia sẻ quota, khó cô lập |
| Account theo nhóm tenant | Các tenant được gom theo gói/vùng | Cân bằng tài nguyên | Cần policy mapping |
| Account riêng mỗi tenant | Credential/subaccount độc lập | Dễ thu hồi và audit | Nhiều secret và cấu hình |
| Domain riêng mỗi tenant | From theo verified domain | Thương hiệu rõ | Phải onboard DNS |
| BYO provider | Tenant cung cấp account/provider | Linh hoạt | Egress, TLS, secret và abuse |
| Hybrid | Tenant nhỏ dùng shared, tenant lớn dedicated | Phù hợp SLA | Router và billing phức tạp |

Một nền tảng nhỏ có thể bắt đầu bằng một nhóm account platform đã xác minh và tách theo purpose. Khi một tenant có nhu cầu domain/credential riêng, router có thể chọn dedicated account. Không cần bắt mọi tenant tạo SMTP credential riêng nếu sản phẩm không yêu cầu.

## 4. Tenant, domain và purpose cùng quyết định route

Một khóa định tuyến hợp lý có thể là:

~~~text
environment
  + authenticatedTenantId
  + mailPurpose
  + verifiedSendingDomainId
  -> approved provider account
~~~

Ví dụ:

| Tenant | Sending domain | Purpose | Account |
| --- | --- | --- | --- |
| Acme | `mail.acme.example` | Transactional | `acme-tx` |
| Acme | `security.acme.example` | Security | `acme-security` |
| Acme | `news.acme.example` | Marketing | `acme-marketing` |
| Beta | `notify.beta.example` | Transactional | `beta-primary` |
| Beta | `notify.beta.example` | Security | `beta-security` |

Nếu một tenant có nhiều domain cùng phục vụ transactional, chỉ dùng khóa `(tenantId, purpose)` có thể không đủ; cần domain/brand ID đã được xác thực.

Không lấy domain bằng phép nối chuỗi từ tên tenant rồi tin rằng tenant sở hữu nó. Danh sách domain được phép phải đến từ **bản ghi onboarding/verification đáng tin cậy**.

## 5. Bốn ranh giới phải được kiểm soát

~~~mermaid
flowchart TD
    A["Authenticated principal / trusted event"] --> B["Tenant authorization"]
    B --> C["Recipient + business policy"]
    C --> D["Verified domain + mail purpose"]
    D --> E["TenantSenderRouter"]
    E --> F["Approved account"]
    F --> G["SenderRegistry"]
    G --> H["JavaMailSender"]
    H --> I["SMTP provider"]
~~~

**Tenant authorization:** người gọi có quyền thao tác trên dữ liệu của tenant nào?

**Recipient policy:** thông báo được gửi tới ai? Địa chỉ người nhận có thuộc workflow và có được phép nhận dữ liệu này không?

**Sender policy:** tenant được dùng domain/From nào, theo mục đích gì?

**Transport policy:** credential, provider, TLS, quota, retry và fallback nào được phép?

Không được thay thế bốn ranh giới bằng một điều kiện `request.getTenantId() != null` hoặc bằng việc SMTP AUTH thành công. Một message có thể gửi thành công nhưng vẫn gửi sai dữ liệu/recipient giữa các tenant.

## 6. Header From không phải SMTP AUTH

Một email có thể có thông tin:

~~~text
SMTP AUTH username:
  smtp-user-acme-tx

SMTP MAIL FROM:
  bounce@bounces.acme.example

Message headers:
  From: Orders <orders@mail.acme.example>
  Reply-To: support@acme.example
  To: buyer@example.org
~~~

- SMTP AUTH chứng minh quyền sử dụng account với relay.
- From là danh tính người gửi xuất hiện trong thư.
- Reply-To chỉ gợi ý nơi nhận câu trả lời.
- SMTP MAIL FROM là envelope identity phục vụ delivery status/bounce.
- Return-Path thường được thêm ở giai đoạn delivery; không nên tự đặt một header Return-Path để thay thế cấu hình envelope.

Trong Jakarta Mail SMTP transport, một số trường hợp dùng property `mail.smtp.from` để xác định envelope sender. Nó là cấu hình thuộc transport/session, không phải field đơn giản có thể thay theo mỗi mail trên singleton `JavaMailSenderImpl` mà không sợ race. Nhiều provider còn quản lý bounce domain/custom MAIL FROM bằng dashboard hoặc API riêng.

## 7. SPF, DKIM và DMARC theo miền gửi

Khi tenant muốn dùng `mail.acme.example`, application/provider cần xác minh và cấu hình miền. Các lớp liên quan:

| Cơ chế | Mục đích |
| --- | --- |
| Domain verification | Chứng minh quyền sử dụng sending domain với provider |
| SPF | Cho phép IP/relay gửi theo envelope sender domain |
| DKIM | Ký message với domain `d=` và selector |
| DMARC | Kiểm tra alignment của domain header From với SPF hoặc DKIM |
| Custom bounce domain | Xử lý email trả về/Return-Path theo provider |

**SMTP credential hợp lệ không bảo đảm SPF/DKIM/DMARC pass.** Domain có thể chưa được xác minh, chữ ký DKIM sai, hoặc SPF pass ở envelope domain nhưng không đạt alignment với From theo DMARC policy.

Nếu cùng một domain được gửi qua hai provider:

- Cả hai phải được phép sử dụng sender identity.
- DNS record của mỗi provider cần thiết lập đúng, tránh xung đột.
- DKIM selectors có thể riêng cho từng provider.
- Bounce/return-path setup phải phù hợp.
- Cần kiểm tra alignment, không chỉ xem một bản ghi SPF tồn tại.
- Không thêm record DNS bằng cách phỏng đoán mà không theo contract của provider.

Một DNS record đúng cho Relay A không tự có nghĩa Relay B sẵn sàng làm backup sender.

## 8. Onboarding sending domain có trạng thái

Tenant không thể chỉ nhập domain bất kỳ rồi cho gửi production ngay. Một workflow có thể là:

~~~mermaid
flowchart TD
    A["Tenant admin đăng ký domain"] --> B["Kiểm tra quyền + uniqueness"]
    B --> C["Tạo verification challenge"]
    C --> D["Hướng dẫn DNS record"]
    D --> E["Kiểm tra DNS / provider"]
    E --> F{"Verified?"}
    F -->|"Chưa"| G["PENDING_DNS"]
    G --> E
    F -->|"Có"| H["Kiểm tra sender identity và DNS auth"]
    H --> I["ACTIVE"]
    I --> J["Cho phép route production"]
~~~

Các trạng thái minh họa:

~~~text
REQUESTED
PENDING_DNS
VERIFYING
ACTIVE
SUSPENDED
REVOKED
~~~

Chỉ `ACTIVE` mới cho gửi production theo chính sách. Nếu verification mất hiệu lực hoặc tenant không còn quyền dùng domain, cần ngừng route phù hợp.

Các trường cần lưu có thể gồm: `tenantId`, `domainId`, `canonicalDomain`, `verificationStatus`, `providerVerificationId`, `allowedFromIdentities`, `allowedPurposes`, `configVersion`, `verifiedAt` và `revokedAt`.

**Một domain thuộc tenant khác** phải được xử lý như xung đột ownership, không được tự cho phép vì hai tenant cùng nhập chuỗi giống nhau.

## 9. Một tenant có nhiều miền

Tenant Acme có thể dùng:

~~~text
mail.acme.example       -> Orders
security.acme.example   -> Password reset
news.acme.example       -> Newsletter
~~~

Một mô hình routing bằng domain ID giúp tránh việc nhận raw string từ request:

~~~java
public record RouteKey(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId) {
}
~~~

Dùng domain ID đã được phê duyệt còn giúp xử lý đổi tên/ownership, IDN canonicalization và versioning.

Không nên kiểm tra domain bằng:

~~~java
email.endsWith("acme.example")
~~~

Địa chỉ có domain `evil-acme.example` cũng có hậu tố tương tự. Phải parse địa chỉ và so sánh domain đã chuẩn hóa theo cấu trúc, không so suffix chuỗi tùy tiện. Nếu hỗ trợ internationalized domains, cần canonicalization nhất quán và kiểm tra ownership trên dạng tên miền chuẩn.

## 10. Spring Boot một sender mặc định

Khi chỉ có một SMTP relay, cấu hình quen thuộc:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

Spring Boot có thể tự cấu hình một `JavaMailSender` khi các điều kiện auto-configuration phù hợp. Nhưng `spring.mail.*` không tự suy ra tenant/domain account từ database.

Với multi-tenant, cần một tầng cấu hình và routing riêng. Nếu tự khai báo `JavaMailSender` beans, Boot mail auto-configuration có thể back off theo điều kiện bean. Không nên cho rằng Boot luôn tạo thêm một sender mặc định ngoài các bean tự định nghĩa.

## 11. Cấu hình nhiều account cố định

Ví dụ một ứng dụng có hai tenant/account đã biết lúc deploy:

~~~yaml
app:
  mail:
    accounts:
      acme-tx:
        provider: relay-a
        host: ${ACME_SMTP_HOST}
        port: 587
        username: ${ACME_SMTP_USER}
        password: ${ACME_SMTP_PASSWORD}
        implicit-tls: false
        sending-domain: mail.acme.example
        from: orders@mail.acme.example
        reply-to: support@acme.example

      beta-primary:
        provider: relay-b
        host: ${BETA_SMTP_HOST}
        port: 465
        username: ${BETA_SMTP_USER}
        password: ${BETA_SMTP_PASSWORD}
        implicit-tls: true
        sending-domain: notify.beta.example
        from: notices@notify.beta.example
        reply-to: help@beta.example

    routes:
      tenant-acme:
        transactional: acme-tx
      tenant-beta:
        transactional: beta-primary
~~~

Đây là một **namespace custom** `app.mail.*`. Spring Boot không tự bind nó thành nhiều sender trừ khi ứng dụng tự định nghĩa `@ConfigurationProperties` và factory.

Không commit password thật. Các placeholder được inject qua deployment/secret manager. Trường `provider` chỉ là metadata định tuyến; nó không tự cấu hình DKIM hoặc provider account.

Khi tenant hàng nghìn, không nên sinh ra hàng nghìn YAML entries rồi restart mỗi lần onboarding. Routing metadata có thể nằm trong database với cache/versioning; credential lưu riêng trong secret manager.

## 12. Tách provider endpoint, account và route

Một model rõ ràng gồm ba object:

~~~java
public record SmtpEndpoint(
        String providerId,
        String host,
        int port,
        boolean implicitTls) {
}
~~~

~~~java
public record SenderAccount(
        String accountId,
        String providerId,
        String credentialReference,
        long credentialVersion) {
}
~~~

~~~java
public record ApprovedSenderRoute(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId,
        String sendingDomain,
        String accountId,
        String fromAddress,
        String replyToAddress,
        long policyVersion) {
}
~~~

Các record minh họa cho schema/config. Ưu điểm:

- Endpoint mô tả kết nối provider.
- Account mô tả principal và secret reference.
- Route mô tả tenant/domain/purpose nào được quyền sử dụng account.
- Khi rotate credential, không nhất thiết sửa quy tắc From/domain.
- Khi đổi provider, không cần thay template rendering/business workflow.

Không log toàn bộ object chứa password. Record có `toString()` tự sinh có thể đưa field nhạy cảm vào log nếu lưu secret thẳng bên trong.

## 13. Định nghĩa MailPurpose từ use case

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING,
    OPERATIONS
}
~~~

Application layer quyết định purpose. Ví dụ, email reset password luôn là `SECURITY` dù HTTP request cố đưa giá trị `MARKETING` hoặc một SMTP account tùy ý.

Không dùng API dạng:

~~~json
{
  "tenantId": "tenant-beta",
  "smtpAccount": "acme-security",
  "from": "security@mail.acme.example",
  "purpose": "SECURITY"
}
~~~

rồi tin mọi field. Client không có quyền chọn SMTP credential bằng cách đặt một chuỗi.

Một `MailRoutingPolicy` cần nhận context đã authorize rồi chọn account đã duyệt, thay vì request DTO chưa tin cậy.

## 14. Tạo JavaMailSenderImpl theo SMTP account

Một factory có thể tạo sender riêng cho từng account đã được duyệt:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    public JavaMailSender create(
            String host,
            int port,
            String username,
            String password,
            boolean implicitTls) {

        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding(
                StandardCharsets.UTF_8.name()
        );

        Properties properties =
                sender.getJavaMailProperties();

        properties.put(
                "mail.transport.protocol", "smtp"
        );
        properties.put("mail.smtp.auth", "true");

        if (implicitTls) {
            properties.put(
                    "mail.smtp.ssl.enable", "true"
            );
            properties.put(
                    "mail.smtp.starttls.enable", "false"
            );
        } else {
            properties.put(
                    "mail.smtp.ssl.enable", "false"
            );
            properties.put(
                    "mail.smtp.starttls.enable", "true"
            );
            properties.put(
                    "mail.smtp.starttls.required", "true"
            );
        }

        properties.put(
                "mail.smtp.ssl.checkserveridentity",
                "true"
        );

        properties.put(
                "mail.smtp.connectiontimeout", "5000"
        );
        properties.put(
                "mail.smtp.timeout", "10000"
        );
        properties.put(
                "mail.smtp.writetimeout", "10000"
        );

        return sender;
    }
}
~~~

Port 587 thường đi với STARTTLS; port 465 thường đi với implicit TLS, nhưng cần dùng chế độ mà nhà cung cấp thật sự yêu cầu. Ví dụ đặt TLS verification, không dùng `mail.smtp.ssl.trust=*` để bỏ qua kiểm tra chứng chỉ trong production.

**Không mutate một sender singleton** mỗi lần tenant thay đổi:

~~~java
sharedSender.setUsername(account.user());
sharedSender.setPassword(account.password());
sharedSender.send(message);
~~~

Nếu hai thread xen kẽ setter, email của tenant A có thể gửi bằng credential B. Tạo sender cấu hình cố định theo account và dùng registry để chọn đúng instance.

## 15. Named beans khi số sender nhỏ

Với một số account đã biết tại build/deploy time:

~~~java
@Configuration
public class MailSenderBeans {

    @Bean("acmeMailSender")
    JavaMailSender acmeMailSender(
            SmtpSenderFactory factory,
            AcmeMailProperties settings) {

        return factory.create(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password(),
                settings.implicitTls()
        );
    }

    @Bean("betaMailSender")
    JavaMailSender betaMailSender(
            SmtpSenderFactory factory,
            BetaMailProperties settings) {

        return factory.create(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password(),
                settings.implicitTls()
        );
    }
}
~~~

`AcmeMailProperties` và `BetaMailProperties` là kiểu cấu hình do ứng dụng định nghĩa; factory bean cũng cần được đăng ký trong Spring context.

Khi dùng:

~~~java
public AcmeAdapter(
        @Qualifier("acmeMailSender")
        JavaMailSender sender) {
    this.sender = sender;
}
~~~

Tuy nhiên, nếu ứng dụng có hàng nghìn tenant hoặc account được thêm lúc runtime, tạo một bean tĩnh cho mỗi account không phù hợp. Chuyển sang một sender registry có quản lý.

## 16. SenderRegistry cho account động

Một interface đơn giản:

~~~java
public interface SenderRegistry {
    JavaMailSender requireSender(
            String approvedAccountId);
}
~~~

Nó cần thực hiện:

1. Chỉ nhận account ID thuộc danh mục platform đã duyệt.
2. Đọc account metadata/provider endpoint.
3. Resolve secret từ secret manager.
4. Tạo `JavaMailSenderImpl` với TLS và timeout.
5. Cache sender theo account ID + config/credential version.
6. Không expose password qua API hoặc log.
7. Invalidate/recreate sender khi rotation hoặc suspension.
8. Giới hạn số entry và idle retention.

**Không dùng raw host/password do HTTP client gửi trực tiếp** làm input factory trong shared workload. Điều đó có thể tạo đường kết nối outbound trái phép hoặc gửi mail không kiểm soát.

Một `ConcurrentHashMap` sender không tự giải quyết toàn bộ: còn cache eviction, stale secret, đồng thời tạo object, lifecycle và thông báo thay đổi giữa nhiều JVM.

### Cache nên có thời hạn và version

Một cache key minh họa:

~~~text
accountId: acme-tx
endpointVersion: 4
credentialVersion: 9
~~~

Khi credential rotate, tạo sender mới theo version, không sửa password trên instance đang được thread khác dùng. Cần chính sách xử lý những send đang in-flight và thời điểm thu hồi credential cũ.

## 17. TenantSenderRouter chỉ trả route hợp lệ

Định nghĩa contract:

~~~java
public interface TenantSenderRouter {

    ApprovedSenderRoute resolve(
            String authenticatedTenantId,
            MailPurpose purpose,
            String selectedSendingDomainId);
}
~~~

Router kiểm tra:

- Tenant tồn tại, active và có quyền gửi.
- Purpose phù hợp use case.
- Domain ID thuộc tenant, verified và active.
- From identity đã được tenant/provider phê duyệt.
- Account được phép gửi domain/purpose đó.
- Môi trường hiện tại cho phép provider này.
- Account chưa suspended/revoked.
- Không có route mơ hồ hoặc default nguy hiểm.

Khi không có route: **fail closed** bằng lỗi rõ, không chọn phần tử đầu tiên trong map hoặc tự chuyển sang account marketing/security khác.

### Ví dụ router với map bất biến

~~~java
import java.util.Map;
import java.util.Objects;

public record RouteKey(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId) {
}

public final class StaticTenantRouter
        implements TenantSenderRouter {

    private final Map<RouteKey, ApprovedSenderRoute> routes;

    public StaticTenantRouter(
            Map<RouteKey, ApprovedSenderRoute> routes) {
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ApprovedSenderRoute resolve(
            String tenantId,
            MailPurpose purpose,
            String domainId) {

        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(purpose);
        Objects.requireNonNull(domainId);

        ApprovedSenderRoute route =
                routes.get(new RouteKey(
                        tenantId, purpose, domainId
                ));

        if (route == null) {
            throw new MailRouteDeniedException(
                    "Không có sender route được phép"
            );
        }

        return route;
    }
}
~~~

`MailRouteDeniedException` là exception runtime do ứng dụng định nghĩa. Implementation này giả định map đã được nạp từ **verified active configuration**. Với production, router phải xét trạng thái live/TTL/revocation thay vì chỉ tin snapshot mãi mãi.

## 18. Gateway chọn transport trước khi dựng MIME

Một DTO chứa dữ liệu đã đi qua application policy:

~~~java
public record AuthorizedMail(
        String tenantId,
        MailPurpose purpose,
        String sendingDomainId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

Tên `AuthorizedMail` là hợp đồng lập trình; nó không tự chứng minh dữ liệu đã được kiểm tra. Chỉ application service đã xác minh actor, business object và recipient mới nên tạo DTO này.

Một gateway:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MultiTenantMailGateway {

    private final TenantSenderRouter router;
    private final SenderRegistry registry;

    public MultiTenantMailGateway(
            TenantSenderRouter router,
            SenderRegistry registry) {
        this.router = router;
        this.registry = registry;
    }

    public void send(AuthorizedMail mail)
            throws MessagingException {

        ApprovedSenderRoute route =
                router.resolve(
                        mail.tenantId(),
                        mail.purpose(),
                        mail.sendingDomainId()
                );

        JavaMailSender sender =
                registry.requireSender(
                        route.accountId()
                );

        MimeMessage message =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message, true, "UTF-8"
                );

        helper.setFrom(route.fromAddress());

        if (route.replyToAddress() != null) {
            helper.setReplyTo(
                    route.replyToAddress()
            );
        }

        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(
                mail.plainText(),
                mail.htmlText()
        );

        sender.send(message);
    }
}
~~~

Gateway quyết định transport qua approved route. Nó **không nhận SMTP password/From từ request**, không đổi credential trên singleton và không tự tính tenant identity từ ThreadLocal khi worker chạy async.

Nếu provider cần custom bounce/envelope sender, đó là cấu hình transport/account riêng; không cố ép Return-Path bằng một header.

## 19. Tenant identity phải lấy từ nguồn đáng tin

Một request:

~~~json
{
  "tenantId": "tenant-beta",
  "orderId": "order-981"
}
~~~

không đủ để chứng minh caller có quyền gửi mail của Beta. Cần kiểm tra token/session/workload identity và ownership của order.

Ví dụ luồng use case:

~~~java
public void sendOrderConfirmation(
        AuthenticatedActor actor,
        UUID orderId) {

    Order order =
            orderRepository.require(orderId);

    tenantPolicy.requireAccess(
            actor, order.tenantId()
    );

    MailPurpose purpose =
            MailPurpose.TRANSACTIONAL;

    String domainId =
            domainPolicy.requireDomainFor(
                    order.tenantId(), purpose
            );

    // Render template và enqueue một AuthorizedMail
    // hoặc outbox job dựa trên dữ liệu đã xác minh.
}
~~~

Các type/method ở ví dụ là abstraction ứng dụng. Quan trọng là **tenant được suy ra/xác minh từ business resource và principal**, không phải tin trường raw của HTTP.

Với `@Async` hoặc outbox, không phụ thuộc TenantContext `ThreadLocal` của HTTP request đã kết thúc. Persist tenant ID và context cần thiết vào job, rồi kiểm tra chính sách khi worker xử lý.

## 20. Sender domain và identity allowlist

Một tenant có thể quản lý `mail.acme.example`, nhưng không nhất thiết được phép đặt mọi From address tùy ý. Một số hệ thống chỉ cho:

~~~text
orders@mail.acme.example
support@mail.acme.example
alerts@mail.acme.example
~~~

Policy có thể giới hạn theo local-part, mailbox xác minh hoặc toàn bộ domain tùy hợp đồng provider.

Đừng cho một endpoint công khai tùy ý truyền:

~~~java
helper.setFrom(request.getFrom());
~~~

Ngay cả khi domain đúng, From có thể đại diện một phòng ban hoặc danh tính nhạy cảm mà caller không có quyền dùng.

**Mail purpose quyết định sender identity.** Ví dụ reset password dùng `security@security.acme.example` đã duyệt; marketing dùng `newsletter@news.acme.example`.

## 21. Multi-provider không đồng nghĩa mọi transport là SMTP

Một nhà cung cấp có thể hỗ trợ SMTP và HTTP API. Khi dùng HTTP API, cần adapter khác với `JavaMailSender`.

~~~java
public interface MailTransport {
    SubmissionResult submit(
            ApprovedSenderRoute route,
            AuthorizedMail mail);
}
~~~

Các implementations minh họa:

~~~text
SmtpMailTransport
ProviderAHttpApiTransport
ProviderBHttpApiTransport
~~~

Khác biệt cần lưu ý:

- SMTP trả reply code 2xx/4xx/5xx.
- HTTP email API có thể trả status 429 và Retry-After.
- API có thể có provider message ID hoặc idempotency key riêng.
- Attachment format, feedback events và error details khác nhau.
- Domain verification, custom return-path và quota khác nhau.

Đừng giả định `JavaMailSender` tự hiểu HTTP 429. Nếu tất cả provider được sử dụng qua SMTP, có thể dùng chung `JavaMailSenderImpl` factory cho tầng transport và vẫn giữ domain verification/feedback provider-specific ở tầng khác.

## 22. Cách ly quota và rate limit theo tenant

Một nhà cung cấp có thể giới hạn:

~~~text
Provider organization
  -> SMTP account / subaccount
     -> Sending domain
        -> Tenant policy
           -> Mail purpose
~~~

Một limiter chỉ theo tenant có thể cho nhiều tenant cùng lúc vượt global provider account quota. Một limiter chỉ theo account có thể khiến một tenant chiếm toàn bộ capacity, làm chậm tenant khác.

Kết hợp:

- Global provider/account cap.
- Tenant-level quota.
- Purpose-based rate policy.
- Concurrency cap theo account.
- Priority cho security và transactional.
- Queue riêng cho bulk marketing.
- Backoff khi provider throttling.
- Audit usage/chargeback theo tenant.

Nếu có nhiều worker JVM, limiter local ở mỗi process không bảo đảm global cap. Cần quota authority dùng chung hoặc phân bổ capacity có kiểm soát.

**Nhiều SMTP username không chứng minh quota provider độc lập.** Cần xác minh phạm vi thực tế qua tài liệu, dashboard hoặc hợp đồng nhà cung cấp.

## 23. Failover giữa các provider phải được phê duyệt trước

Khi Relay A lỗi, có nên chuyển sang Relay B? Có thể, nhưng chỉ khi:

1. Relay B có account được phép cho tenant.
2. Domain identity đã verified và DKIM/SPF/DMARC phù hợp.
3. Mục đích email vẫn được cho phép.
4. Credential/secret B có quyền hợp lệ.
5. Quota và egress policy cho phép.
6. Không vi phạm yêu cầu data residency hoặc hợp đồng tenant.
7. Lỗi của lần gửi A đã được phân loại.
8. Rủi ro duplicate được đánh giá.

Ví dụ fallback policy:

~~~text
tenant: tenant-acme
purpose: TRANSACTIONAL
sendingDomain: mail.acme.example
primary: relay-a/acme-tx
secondary: relay-b/acme-tx-backup
secondaryVerified: true
fallbackFor:
  - PROVIDER_UNAVAILABLE
  - TEMPORARY_CONNECT_FAILURE
~~~

Đây là cấu hình minh họa, không phải syntax tự có của Spring. Không tự động fallback marketing sang account security để vượt throttling. Không đổi From sang domain platform nếu tenant chưa phê duyệt.

## 24. SMTP timeout có thể gây gửi trùng khi fallback

Một failure window quan trọng:

~~~text
Worker gửi SMTP DATA tới Relay A
Relay A chấp nhận message
Network đứt trước khi worker nhận phản hồi
Worker thấy timeout
Worker fallback tới Relay B và gửi lại
Recipient có thể nhận hai email
~~~

Do đó hệ thống cần phân biệt:

- Failure chắc chắn trước khi gửi dữ liệu.
- SMTP rejection rõ ràng.
- Provider rate limit.
- AUTH/TLS configuration failure.
- Timeout với **unknown outcome**.
- Partial acceptance khi message có nhiều recipient.

`Message-ID` hữu ích cho tracing nhưng không bắt buộc mọi relay tự dedupe. Transactional outbox có thể bảo đảm ý định gửi được lưu và không enqueue trùng theo key, nhưng **không tạo giao dịch nguyên tử giữa database và SMTP**.

Khi outcome unknown, retry/fallback phải tuân thủ policy và ghi nhận nguy cơ duplicate, không tự tuyên bố exactly-once.

## 25. Outbox lưu route intent, không lưu SMTP password

Một job có thể chứa:

~~~json
{
  "mailJobId": "job-981",
  "tenantId": "tenant-acme",
  "purpose": "TRANSACTIONAL",
  "sendingDomainId": "domain-acme-tx",
  "recipientContactId": "contact-77",
  "templateVersion": 3,
  "routingPolicyVersion": 12,
  "idempotencyKey": "evt-981:tenant-acme:contact-77",
  "status": "PENDING"
}
~~~

Không lưu SMTP password hoặc API key provider trong job. Chỉ lưu ID, business data cần thiết và version/metadata.

### Pin route khi enqueue hay resolve lúc send?

**Pin route** giúp audit và giữ identity ổn định nhưng account có thể bị revoked trước khi worker gửi.

**Resolve lại route** cho phép dùng credential mới hoặc provider đã được thay đổi, nhưng có thể vô tình gửi cùng job bằng From/domain khác.

Một hướng cân bằng:

- Persist tenant, purpose, verified domain ID và template/version.
- Lưu routing policy version hoặc intended account khi có yêu cầu audit.
- Worker kiểm tra account/domain vẫn active tại send time.
- Credential có thể được rotate theo account policy.
- Không tự thay đổi brand/From/recipient khi retry nếu không có quy tắc.
- Mỗi attempt ghi account/provider thực sự sử dụng.

Nếu tenant thu hồi quyền domain, queued job không nên tự động tiếp tục với route cũ chỉ vì nó đã được enqueue.

## 26. Secrets và credential rotation

SMTP credential có khả năng gửi thư thay mặt tenant. Cần:

- Không commit password vào Java/YAML/Git.
- Dùng secret manager hoặc storage mã hóa được bảo vệ.
- Chỉ workload phù hợp được đọc secret.
- Audit khi tạo, sửa, xem, rotate hoặc revoke credential.
- Không dump toàn bộ Spring properties/log object có password.
- Không đưa secret vào outbox payload hay HTTP error.
- Không lưu token reset/password trong feedback log.

Một record metadata có thể gồm:

~~~text
account_id
tenant_id / pooled_scope
provider_id
endpoint_id
credential_ref
credential_version
status
rotated_at
~~~

`credential_ref` là tham chiếu, không phải raw password.

### Rotation phải làm mới sender cache

Đổi password trong secret manager không tự động cập nhật `JavaMailSenderImpl` đã được tạo. Quy trình:

1. Tạo secret version mới.
2. Cập nhật account metadata và cache version.
3. Tạo sender instance mới cho request/send mới.
4. Hoàn tất hoặc dừng in-flight send cũ theo policy.
5. Thu hồi credential cũ.
6. Kiểm tra AUTH failure và alert.

Không gọi `setPassword` trên singleton đang hoạt động song song để rotate.

## 27. Khi tenant tự nhập SMTP host: rủi ro outbound connection

Nếu platform cho tenant nhập:

~~~json
{
  "smtpHost": "custom.example.org",
  "smtpPort": 587,
  "smtpUsername": "tenant-user"
}
~~~

thì cần cân nhắc nghiêm túc. Một host do tenant kiểm soát có thể trỏ tới network nội bộ, metadata endpoint hoặc dịch vụ nhạy cảm, hoặc bị đổi DNS sau khi validation. Cơ chế “thử kết nối SMTP” cũng có thể bị lạm dụng để quét port.

Các lớp bảo vệ:

1. Tenant admin phải được ủy quyền.
2. Ưu tiên allowlisted providers/endpoints.
3. Network egress policy hạn chế IP/range/port được phép.
4. DNS rebinding và name resolution được kiểm soát.
5. TLS bắt buộc, hostname verification, không bỏ qua certificate.
6. Timeout và connection/rate limits.
7. Credential được lưu trong secret manager, không trả lại qua API.
8. Onboarding/sandbox test trước khi gửi traffic thật.
9. Giám sát abuse, quota và anomalous egress.
10. Cô lập workload nếu yêu cầu hỗ trợ arbitrary endpoint.

Không xem một phép kiểm `host != "localhost"` là đủ chống outbound abuse; có nhiều cách biểu diễn/định tuyến tới IP nội bộ.

## 28. Feedback delivery theo tenant/account

SMTP submit thành công không chứng minh email đã delivered. Provider có thể gửi event:

~~~text
DELIVERED
BOUNCED
DEFERRED
COMPLAINED
UNSUBSCRIBED
~~~

Với nhiều provider, mỗi provider có webhook schema và cách xác minh riêng. Có thể normalize:

~~~java
public record ProviderMailEvent(
        String providerId,
        String providerAccountId,
        String providerMessageId,
        String mailJobId,
        String eventType,
        Instant occurredAt) {
}
~~~

Để xử lý webhook:

1. Xác minh chữ ký/nguồn của provider.
2. Parse schema/version đúng.
3. Dùng provider/account/message ID đáng tin cậy để tìm mail job.
4. Map job về tenant/domain/purpose.
5. Chống xử lý event trùng lặp.
6. Cập nhật đúng tenant suppression/delivery status.
7. Ghi audit và xử lý unknown mapping.

**Không tin raw tenantId trong webhook khi chưa xác minh và đối chiếu.** Nếu webhook có thể tác động suppression list của tenant khác, đây là một điểm có nguy cơ cross-tenant state corruption.

## 29. Isolation cả nội dung và attachment

Chọn đúng SMTP sender vẫn chưa đủ nếu body hoặc recipient chứa dữ liệu tenant khác.

Cần bảo vệ:

- Order/invoice thuộc tenant đang xử lý.
- Contact/recipient thuộc workflow được phép.
- Template data model đúng tenant.
- Brand/logo/assets thuộc tenant.
- Attachment storage key có quyền tenant.
- Domain/From active và thuộc tenant.
- Provider account không bị chọn từ raw user input.
- Feedback map đúng job/tenant.
- Logs và metrics không làm lộ dữ liệu nhạy cảm.

Đối với `@Async` và worker outbox, không nên lấy tenant từ một request-scoped bean hoặc `ThreadLocal` không được truyền qua thread. Persist tenant ID/authorization intent đáng tin cậy và revalidate tại boundary worker khi cần.

## 30. Local, staging và production phải có tuyến riêng

| Môi trường | Sender | Recipient policy |
| --- | --- | --- |
| Local | Mail catcher | Không gửi Internet |
| Unit test | Fake/mocked gateway | Fixtures, không SMTP thật |
| Staging | Provider sandbox / SMTP test server | Allowlist hoặc sink |
| Production | Approved provider accounts | Business authorization đầy đủ |

Không cấp credential production cho staging chỉ để test giống production. Nếu staging có thể nhận dữ liệu khách hàng thật, cần thêm policy data handling và recipient guard; một profile sai không được khiến môi trường test gửi email tới khách hàng.

Ví dụ cấu hình local:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: localhost
    port: 1025
~~~

Mail catcher phải được chạy riêng. Với ứng dụng custom multi-sender, profile local cần override cả registry/router, không chỉ `spring.mail.*` nếu custom sender không đọc cấu hình đó.

## 31. Unit test routing không cần SMTP

Một test xác nhận mapping:

~~~java
@Test
void acmeTransactionalUsesApprovedAccount() {
    ApprovedSenderRoute route =
            router.resolve(
                    "tenant-acme",
                    MailPurpose.TRANSACTIONAL,
                    "domain-acme-tx"
            );

    assertEquals(
            "acme-tx",
            route.accountId()
    );

    assertEquals(
            "orders@mail.acme.example",
            route.fromAddress()
    );
}
~~~

Một test negative:

~~~java
@Test
void rejectsForeignTenantDomain() {
    assertThrows(
            MailRouteDeniedException.class,
            () -> router.resolve(
                    "tenant-acme",
                    MailPurpose.TRANSACTIONAL,
                    "domain-beta"
            )
    );
}
~~~

Các trường hợp nên bao phủ:

| Trường hợp | Kết quả |
| --- | --- |
| Tenant active, domain verified, purpose hợp lệ | Route được duyệt |
| Domain của tenant khác | Từ chối |
| Domain đang chờ DNS | Từ chối |
| Domain revoked | Từ chối |
| Account suspended | Từ chối hoặc backup đã duyệt |
| Tenant không được phép dùng purpose | Từ chối |
| Marketing không có account | Không fallback security |
| Staging chọn production route | Từ chối |
| From identity nằm ngoài allowlist | Từ chối |
| Backup chưa được DKIM verified | Không sử dụng |
| Route trùng/mơ hồ | Fail configuration |

Test này không cần Spring context, SMTP network hoặc secret thật nếu router là logic thuần.

## 32. Gateway test chọn đúng JavaMailSender

Có thể dùng Mockito và một `MimeMessage` thật trong bộ nhớ:

~~~java
JavaMailSender acmeSender =
        mock(JavaMailSender.class);

JavaMailSender betaSender =
        mock(JavaMailSender.class);

when(acmeSender.createMimeMessage())
        .thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(
                                new Properties()
                        )
                )
        );

// Registry test trả acmeSender cho account acme-tx.
// Router test trả route Acme được duyệt.
// Gateway nhận AuthorizedMail của Acme.

gateway.send(authorizedAcmeMail);

verify(acmeSender, times(1))
        .send(any(MimeMessage.class));

verify(betaSender, never())
        .send(any(MimeMessage.class));
~~~

Đây là test skeleton: `gateway`, `authorizedAcmeMail` và test registry/router cần tạo theo project. Có thể dùng `ArgumentCaptor<MimeMessage>` để assert recipient, From, Reply-To, decoded subject và MIME content, không chỉ số lần gọi.

Không mock toàn bộ `MimeMessage` nếu mục tiêu cần xác nhận header và multipart semantics. Dùng Jakarta Mail object thật trong RAM, mock sender để không mở kết nối SMTP.

## 33. Integration test với hai SMTP test server

Một cách kiểm chứng tách route end-to-end:

~~~text
GreenMail/Mailpit A:
  SMTP port A
  Account route: Acme

GreenMail/Mailpit B:
  SMTP port B
  Account route: Beta
~~~

Test:

1. Start hai test server với port riêng.
2. Register hai `JavaMailSenderImpl` trỏ tới port A/B.
3. Tạo tenant fixture/verified domain fixture.
4. Gửi một message Acme, một message Beta.
5. Kiểm tra server A chỉ nhận message Acme.
6. Kiểm tra server B chỉ nhận message Beta.
7. Kiểm tra From, To và correlation ID.
8. Cleanup server, fixture và queue thuộc test.

Không dùng inbox dùng chung rồi lấy message mới nhất theo array index. Với async worker, đợi theo correlation ID và deadline có kiểm soát thay vì `Thread.sleep` cố định.

SMTP test server không tự chứng minh SPF/DKIM/DMARC hoặc provider domain verification thật. Với những yêu cầu đó, cần contract tests trong provider sandbox và domain onboarding tests riêng.

## 34. Observability theo tenant/provider/account

Log một lần submit có thể chứa:

~~~text
mail_job_id: job-981
tenant_id: tenant-acme
purpose: TRANSACTIONAL
sender_domain_id: domain-acme-tx
provider_id: relay-a
provider_account_id: acme-tx
routing_policy_version: 12
credential_version: 9
attempt: 1
smtp_result: ACCEPTED
latency_ms: 842
~~~

Không log password, reset token, toàn bộ mail body hoặc attachment. Với recipient, có thể dùng contact ID hoặc masking theo chính sách.

Metrics hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_submission_total` | Số attempt theo provider/account |
| `mail_smtp_auth_failure_total` | Lỗi credential |
| `mail_tls_failure_total` | Lỗi TLS/certificate |
| `mail_provider_throttle_total` | Throttling |
| `mail_domain_verification_state` | Domain active/pending/revoked |
| `mail_route_fallback_total` | Số lần dùng backup |
| `mail_unknown_outcome_total` | Attempt có kết quả mơ hồ |
| `mail_bounce_total` | Bounce theo account/domain |
| `mail_complaint_total` | Complaint theo account/domain |
| `mail_outbox_oldest_age_seconds` | Job chờ lâu |
| `mail_sender_cache_entries` | Registry cache size |
| `mail_provider_quota_remaining` | Quota còn lại theo provider |

Nếu có hàng trăm nghìn tenant, đưa tenant ID vào mọi metric label có thể tạo cardinality rất lớn. Cần thiết kế metrics aggregate và log/tracing tra cứu tenant có kiểm soát.

### Những alert quan trọng

- Một domain active bị mất verification.
- Credential tenant bị AUTH failure lặp lại.
- Quota account gần cạn hoặc traffic tăng đột biến.
- Provider outage và fallback tăng bất thường.
- DKIM/DMARC alignment lỗi theo domain.
- Bounce/complaint tăng.
- Webhook không map được message.
- Security mail bị backlog lâu.
- Sender registry cache tăng không giới hạn.

## 35. Những lỗi triển khai thường gặp

### 35.1. Chỉ đổi From

Không đổi SMTP principal nên có thể gửi sai account, quota hoặc bị provider từ chối. Phải route account/transport.

### 35.2. Tin tenant ID trong request

Caller có thể giả danh tenant. Phải xác minh principal và resource ownership.

### 35.3. Chọn account từ raw HTTP field

Có thể cho người dùng đổi purpose hoặc chiếm credential khác. Policy nội bộ mới được chọn route.

### 35.4. Cho domain chưa verified gửi

Rủi ro giả mạo và DMARC fail. Chỉ active domain sau verification.

### 35.5. Không tách provider account và sending domain

Một account có thể dùng nhiều domain, một domain có thể nhiều account. Cần mapping explicit.

### 35.6. Dùng @Primary che thiếu route

Một service quên qualifier có thể gửi qua default account sai. Dùng router tường minh.

### 35.7. Mutate JavaMailSenderImpl giữa nhiều thread

Credential bị race. Tạo instance cố định cấu hình.

### 35.8. Cache sender vô hạn

Có thể giữ hàng nghìn object và secret. Giới hạn cache và invalidate theo version.

### 35.9. Rotation không cập nhật sender

Instance vẫn giữ password cũ. Phải recreate/swap theo credential version.

### 35.10. Arbitrary SMTP host cho tenant

Có nguy cơ outbound abuse và kết nối nội bộ. Dùng allowlist, egress protection, TLS và onboarding.

### 35.11. Coi Reply-To là envelope sender

Reply-To không thay thế SMTP MAIL FROM hoặc provider bounce config.

### 35.12. Tự đặt Return-Path để cấu hình bounce

Return-Path thuộc delivery processing; cần provider/custom MAIL FROM theo contract.

### 35.13. Fallback sang provider chưa verified

Có thể gửi sai DNS auth và identity. Backup route phải sẵn sàng trước.

### 35.14. Retry unknown outcome không có kiểm soát

SMTP timeout sau DATA có thể gây duplicate. Cần trạng thái và policy riêng.

### 35.15. Outbox không lưu tenant/domain

Worker có thể chọn nhầm account hoặc không audit được. Lưu trusted identity và route intent.

### 35.16. Domain bị revoked nhưng job cũ vẫn gửi

Phải revalidate permission khi gửi.

### 35.17. Nhiều SMTP user được coi là quota riêng tuyệt đối

Provider có thể áp global organization/IP cap. Kiểm tra thực tế.

### 35.18. Webhook không xác minh signature

Có thể cập nhật suppression/status sai tenant. Verify và map trusted IDs.

### 35.19. Dùng ThreadLocal tenant context trong async worker

Context có thể mất hoặc rò giữa task. Persist tenant ID đáng tin cậy.

### 35.20. Cho rằng SMTP accepted là delivered

Provider chỉ có thể nhận để chuyển tiếp; delivery/bounce cần feedback riêng.

## 36. Câu hỏi thực hành

**Câu 1.** Hai tenant dùng hai header From khác nhau nhưng chung một SMTP username. Đã tách account chưa?

Chưa. Chúng có thể chỉ tách sender identity; credential/quota vẫn dùng chung.

**Câu 2.** Tenant A gửi request có `tenantId=B`. Router có nên dùng account B không?

Không nếu actor/business resource chưa chứng minh quyền thuộc B.

**Câu 3.** Tenant nhập domain, DNS chưa verified. Có cho gửi production?

Không nên. Domain phải active theo provider/platform policy.

**Câu 4.** Tenant Acme có hai domain transactional. RouteKey chỉ có tenant và purpose đủ chưa?

Chưa. Cần thêm domain ID/brand hoặc quy tắc chọn được phê duyệt.

**Câu 5.** Đổi `helper.setFrom` sang domain Beta có làm `JavaMailSenderImpl` dùng credential Beta?

Không. Account lựa chọn ở sender/registry.

**Câu 6.** Credential được rotate trong secret manager. Sender cache cũ tự biết cập nhật?

Không mặc định. Cần invalidation/recreate theo version.

**Câu 7.** Provider A có DKIM đúng, provider B chưa xác minh domain. Có được fallback sang B?

Không nên. Backup phải đủ điều kiện DNS/provider identity.

**Câu 8.** SMTP A timeout sau khi gửi DATA, worker chuyển B ngay. Nguy cơ?

Email có thể được gửi trùng vì kết quả từ A chưa chắc chắn.

**Câu 9.** Tenant tự nhập SMTP host trỏ tới IP private. Có an toàn không?

Không. Cần kiểm soát outbound egress, host/port và DNS.

**Câu 10.** Provider webhook nói tenant B nhưng signature không hợp lệ. Có cập nhật bounce list B?

Không. Phải xác minh callback và đối chiếu với message/account đáng tin.

**Câu 11.** Nhiều SMTP credential trong cùng provider organization có quota độc lập không?

Không thể mặc định. Cần xác nhận quota ở cấp nào.

**Câu 12.** Có nên dùng account security khi marketing bị giới hạn?

Không. Chỉ dùng tuyến dự phòng đã duyệt cho cùng purpose.

**Câu 13.** Đã pin route lúc enqueue nhưng domain bị revoke trước khi worker send. Làm gì?

Revalidate trạng thái/quyền tại send time, fail closed hoặc xử lý theo policy, không cố gửi với quyền cũ.

**Câu 14.** SMTP AUTH thành công có nghĩa DKIM/DMARC đúng không?

Không. Đó là những cơ chế độc lập.

**Câu 15.** Một mail của tenant A dùng sender A nhưng attachment đọc từ tenant B. Routing đã bảo đảm isolation chưa?

Chưa. Content/attachment authorization cũng là phần bắt buộc của tenant isolation end-to-end.

## 37. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Trusted actor / business event"] --> B["Xác định tenant + quyền"]
    B --> C["Kiểm tra recipient + nội dung"]
    C --> D["MailPurpose + verified domain"]
    D --> E["TenantSenderRouter"]
    E --> F{"Route hợp lệ?"}
    F -->|"Không"| G["Fail closed / giữ job"]
    F -->|"Có"| H["SenderRegistry"]
    H --> I["Account metadata + secret version"]
    I --> J["JavaMailSenderImpl"]
    J --> K["MimeMessageHelper"]
    K --> L["SMTP provider"]
    L --> M["Ghi account/provider/attempt"]
    M --> N["Provider feedback"]
    N --> O["Verify + map đúng tenant"]
~~~

Các nguyên tắc:

1. **Tenant, sending domain, provider, SMTP account và From không phải cùng một thứ.**
2. **Đổi From không đồng nghĩa đổi credential.** Phải chọn transport/account phù hợp.
3. **Tenant identity phải đáng tin**, không lấy account tùy ý từ request.
4. **Domain phải verified và active**; provider permission và SPF/DKIM/DMARC cần phù hợp.
5. **Route key có thể bao gồm tenant, purpose và domain ID**, nhất là tenant có nhiều brand/domain.
6. **Spring Boot một `spring.mail.*` không tự routing multi-tenant.** Dùng named beans hoặc registry.
7. **Không mutate sender singleton giữa các thread**; rotation qua instance/version.
8. **Secrets và registry cache phải được kiểm soát**, tránh lưu/log credential bừa bãi.
9. **BYO SMTP endpoint có rủi ro egress/SSRF-style**, cần security controls mạnh.
10. **Provider failover chỉ khi tuyến backup đã được phê duyệt**, không phá purpose/domain policy.
11. **SMTP outcome unknown có thể gửi trùng**, không dựa vào Message-ID để bảo đảm exactly once.
12. **Outbox giữ tenant/domain/purpose và routing intent**, không lưu password; revalidate permission khi send.
13. **Quota có thể chung ở cấp organization/IP**, dù nhiều account.
14. **Provider webhook phải xác minh và map đúng tenant**, tránh cập nhật trạng thái cross-tenant.
15. **Test routing, transport và provider integration ở các ranh giới riêng**, tránh phụ thuộc SMTP thật trong unit test.

Trong Spring Framework Mail với nhiều nhà cung cấp, yếu tố quan trọng nhất không phải số lượng `JavaMailSenderImpl` mà là **chính sách chọn sender có thể kiểm tra, bảo vệ và audit**. Khi tenant identity, verified sending domain, mail purpose, provider account và credential được ràng buộc rõ, ứng dụng có thể gửi email dưới thương hiệu từng tenant mà vẫn quản lý được bảo mật, quota, vòng đời secret, phản hồi từ provider và sự cố failover.
