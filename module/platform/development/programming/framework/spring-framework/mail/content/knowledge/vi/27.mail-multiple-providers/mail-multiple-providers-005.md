# Định tuyến theo loại email hoặc khu vực

## 1. Bài toán gửi email qua nhiều nhà cung cấp

Trong **Spring Framework Mail**, `JavaMailSender` thường được cấu hình để kết nối một SMTP server. Mô hình này đủ cho hệ thống nhỏ. Tuy nhiên, một sản phẩm có nhiều nhóm thông báo, nhiều tenant hoặc người dùng ở nhiều khu vực có thể cần **định tuyến từng email tới nhà cung cấp SMTP phù hợp** thay vì gửi mọi thứ qua một tài khoản duy nhất.

Ví dụ, một hệ thống thương mại điện tử có thể phát sinh:

- Email xác minh đăng nhập và khôi phục tài khoản: cần gửi nhanh, tránh trì hoãn.
- Email xác nhận đơn hàng, hóa đơn, thông báo vận chuyển: cần độ tin cậy và lịch sử gửi.
- Email bản tin, ưu đãi hoặc chiến dịch marketing: có lưu lượng lớn, phải kiểm soát consent/unsubscribe.
- Email phục vụ khách hàng ở các vùng khác nhau: có thể cần xem xét yêu cầu lưu trú dữ liệu, hạ tầng mạng, quyền sử dụng provider hoặc quy định địa phương.

Nếu dùng chung một đường SMTP cho tất cả, chiến dịch marketing có thể tiêu hết quota của luồng reset mật khẩu; một sự cố của provider có thể làm gián đoạn mọi loại email; và dữ liệu gửi đi có thể đi qua vùng hạ tầng không phù hợp với cam kết xử lý dữ liệu của sản phẩm.

**Định tuyến mail** là quá trình quyết định *ai sẽ gửi một delivery cụ thể, bằng cấu hình và danh tính nào, tại thời điểm nào*, dựa trên những tiêu chí đã được xác thực.

~~~text
Business event / mail outbox
               |
               v
       Normalize mail command
          - category
          - tenant
          - recipient region
          - sending identity
          - priority
               |
               v
          Routing policy
               |
         +-----+------+----------------+
         |            |                |
         v            v                v
     SMTP EU       SMTP APAC       Marketing pool
         |            |                |
         +------------+----------------+
                      |
                      v
           Submission outcome + audit
                      |
                      v
          Provider feedback / metrics
~~~

Trong Spring Mail, phần **tạo MIME và gửi qua SMTP** đã có API hỗ trợ, nhưng phần **chính sách định tuyến nhiều provider, health, quota, retry, failover và đối soát sự kiện** cần được xây dựng ở tầng ứng dụng hoặc tích hợp hạ tầng khác.

> **Nguyên tắc:** Quy tắc định tuyến phải đủ rõ để từ một delivery và phiên bản cấu hình có thể giải thích vì sao hệ thống chọn provider A thay vì B. Không để lựa chọn phụ thuộc vào một biến toàn cục thay đổi ngẫu nhiên giữa các thread.

## 2. Các tiêu chí định tuyến phổ biến

| Tiêu chí | Ví dụ | Giá trị | Rủi ro nếu áp dụng sai |
| --- | --- | --- | --- |
| **Loại email** | `SECURITY`, `TRANSACTIONAL`, `MARKETING` | Bảo vệ quota, reputation, SLA riêng | Marketing gây nghẽn email khẩn cấp |
| **Khu vực** | `EU`, `VN`, `US` | Tuân thủ quy tắc vùng, độ trễ, provider availability | Chuyển dữ liệu qua vùng không được phép |
| **Tenant** | Doanh nghiệp A, B | Tách credential, ngân sách, branding | Dùng nhầm sender hoặc lộ thông tin tenant |
| **Mức ưu tiên** | Critical, normal, bulk | Điều phối công suất và deadline | Một chiến dịch làm chậm OTP |
| **Provider health** | Healthy, throttled, unavailable | Tránh endpoint lỗi | Chuyển sai provider khi kết quả SMTP chưa rõ |
| **Quota/rate limit** | Số thư/phút, số kết nối | Không vượt hợp đồng provider | Retry storm, bị chặn tài khoản |
| **Danh tính gửi** | Domain, envelope sender, DKIM key | Đảm bảo xác thực và thương hiệu | SPF/DKIM/DMARC fail hoặc bounce sai |
| **Loại nội dung** | Attachment, kích thước, yêu cầu mã hóa | Chọn provider hỗ trợ policy | Message bị từ chối do SIZE/type |
| **Chi phí** | Giá theo email, data transfer | Tối ưu chi phí theo điều kiện | Chọn rẻ nhưng không đáp ứng SLA/tuân thủ |

Tiêu chí **khu vực** cần đặc biệt cẩn thận: vị trí người nhận không tự động xác định tất cả nghĩa vụ pháp lý. Data residency có thể áp dụng cho **nơi lưu queue, log, webhook, attachment, metadata và hạ tầng provider**, không chỉ địa chỉ SMTP host. Chính sách thực tế cần được xác định bởi chủ sản phẩm/bộ phận pháp chế và thỏa thuận với nhà cung cấp, không suy luận chỉ từ tên vùng.

### 2.1. Email type nên là enum nghiệp vụ

Thay vì dựa vào subject hoặc template name tự do:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

Một số ứng dụng có thể thêm `SYSTEM_ALERT`, `BILLING` hoặc `LEGAL_NOTICE`. Danh mục phải ổn định, có định nghĩa nghiệp vụ và không biến trực tiếp chuỗi tùy ý từ HTTP request thành đặc quyền đi qua provider ưu tiên cao.

Ví dụ:

- `SECURITY`: xác minh email, cảnh báo thay đổi mật khẩu, xác nhận đăng nhập bất thường.
- `TRANSACTIONAL`: biên nhận, thông tin đơn hàng, thay đổi lịch hẹn.
- `MARKETING`: bản tin và chiến dịch quảng bá có yêu cầu đồng ý nhận.

Không nên gán mọi email “có vẻ quan trọng” thành `SECURITY` chỉ để hưởng quota/latency tốt. Loại email phải được quyết định từ use case đáng tin cậy.

### 2.2. Region nên được chuẩn hóa, không lấy từ TLD email

~~~java
public enum DeliveryRegion {
    VN,
    EU,
    US,
    OTHER
}
~~~

Một địa chỉ có đuôi `.com` không chứng minh người nhận sống tại Mỹ; `.vn` cũng không chứng minh mọi dữ liệu người nhận được phép xử lý tại Việt Nam. Đừng định tuyến bằng cách tìm quốc gia trong domain email.

Nguồn region có thể là:

- Cấu hình residency của tenant đã được xác minh.
- Khu vực pháp lý/địa chỉ đã lưu trong domain model với chính sách nghiệp vụ.
- Thiết lập của tổ chức hoặc vùng triển khai đã được người quản trị ủy quyền.

Nếu thiếu region hoặc có nhiều nguồn mâu thuẫn, policy nên có trạng thái **unresolved** để cần bổ sung dữ liệu hoặc route mặc định được phê duyệt; không tự chọn vùng rẻ nhất khi chưa biết quyền xử lý dữ liệu.

### 2.3. Loại email và khu vực là hai chiều độc lập

Không nên viết những quy tắc rời rạc như:

~~~text
If recipient contains ".eu" => provider EU
Else if subject contains "sale" => provider marketing
Else => provider default
~~~

Quy tắc trên sai cả nguồn region lẫn mức ưu tiên. Một email marketing gửi cho người dùng EU vẫn phải thỏa điều kiện **marketing và EU** cùng lúc. Cách tốt hơn là đánh giá một bộ điều kiện:

~~~text
RoutingContext = {
  category: MARKETING,
  region: EU,
  tenant: tenant-42,
  sendingIdentity: marketing-eu,
  allowedProviders: [smtp-eu-bulk-a, smtp-eu-bulk-b]
}
~~~

`allowedProviders` phải được policy nội bộ suy ra, không phải danh sách do người gọi chưa có quyền tự cung cấp.

## 3. Ma trận route và thứ tự chính sách

Một bảng định tuyến ví dụ:

| Region | Email category | Primary | Secondary có điều kiện | Quota class |
| --- | --- | --- | --- | --- |
| VN | SECURITY | `smtp-vn-critical-a` | `smtp-vn-critical-b` | Critical |
| VN | TRANSACTIONAL | `smtp-vn-tx-a` | `smtp-vn-tx-b` | Normal |
| VN | MARKETING | `smtp-vn-bulk-a` | Không mặc định | Bulk |
| EU | SECURITY | `smtp-eu-critical-a` | `smtp-eu-critical-b` | Critical |
| EU | TRANSACTIONAL | `smtp-eu-tx-a` | `smtp-eu-tx-b` | Normal |
| EU | MARKETING | `smtp-eu-bulk-a` | `smtp-eu-bulk-b` | Bulk |
| US | SECURITY | `smtp-us-critical-a` | `smtp-us-critical-b` | Critical |
| US | TRANSACTIONAL | `smtp-us-tx-a` | `smtp-us-tx-b` | Normal |
| US | MARKETING | `smtp-us-bulk-a` | Theo policy | Bulk |

Các tên provider này là **logical IDs minh họa**, không đại diện cho hãng cụ thể hoặc cam kết rằng hãng nào đó có cơ sở hạ tầng tại vùng được đặt tên. Một route chỉ được triển khai sau khi đối chiếu năng lực thật, quyền gửi, domain và yêu cầu dữ liệu của provider.

### 3.1. Thứ tự đánh giá đề xuất

~~~text
Validate command / recipient / tenant
                  |
                  v
Check consent, suppression and business deadline
                  |
                  v
Resolve category + permitted sending identity
                  |
                  v
Resolve approved data-processing region
                  |
                  v
Build set of policy-allowed providers
                  |
                  v
Filter by identity, size, capability and tenant rights
                  |
                  v
Filter by health/capacity within allowed set
                  |
                  v
Select primary or approved alternative
                  |
                  v
Persist route decision + version
                  |
                  v
Submit through chosen JavaMailSender
~~~

**Không kiểm tra health trước rồi cho phép nó phá luật:** một provider có thể đang khỏe nhưng không được phép xử lý loại email hoặc region đó. Trạng thái hệ thống chỉ giúp **chọn trong tập các route đã được phép**.

### 3.2. Chính sách fail-closed cho dữ liệu giới hạn vùng

Nếu không còn provider hợp lệ trong khu vực mà một delivery bị ràng buộc, hành vi an toàn thường là:

~~~text
No eligible provider in permitted region
        |
        v
RETRY / HOLD / NEEDS_OPERATOR
        |
        v
Alert + audit
~~~

Không tự động chuyển email sang một provider ngoài vùng chỉ để đạt tỷ lệ gửi thành công, trừ khi chính sách đã được phê duyệt cho phép và mọi điều kiện liên quan được đáp ứng.

### 3.3. Policy version để đối soát

Quy tắc định tuyến có thể thay đổi theo thời gian. Khi một email được gửi, nên lưu:

~~~text
deliveryId: opaque-id
routePolicyVersion: 2026-11-routing-03
category: TRANSACTIONAL
region: VN
providerId: smtp-vn-tx-a
identityId: transactional-vn
routeReason: PRIMARY_ELIGIBLE
~~~

Các trường này giúp giải thích vì sao một email đã chọn provider trong quá khứ dù cấu hình hôm nay đã khác. Không cần lưu secret/password vào audit.

## 4. Trách nhiệm của Spring Mail trong mô hình multi-provider

`JavaMailSender` là interface gửi `SimpleMailMessage` và `MimeMessage`. Với SMTP, `JavaMailSenderImpl` là implementation thông dụng để cấu hình host, port, username, password, protocol và các thuộc tính Jakarta Mail.

Một ứng dụng dùng nhiều SMTP endpoint có thể:

1. Định nghĩa nhiều bean `JavaMailSender` có `@Qualifier`.
2. Tạo một **registry nội bộ** quản lý nhiều `JavaMailSenderImpl` theo ID.
3. Tạo sender từ factory theo cấu hình runtime, với cache và lifecycle được quản lý.
4. Dùng email provider API ngoài SMTP qua adapter riêng, nếu hệ thống cần kết hợp SMTP và HTTP API.

Không có sẵn một “router tất cả provider” chỉ vì Spring Boot đã bật `spring-boot-starter-mail`. Quyết định chọn sender là trách nhiệm của lớp dịch vụ định tuyến.

### 4.1. Nhiều bean tĩnh với @Qualifier

~~~java
@Configuration
public class StaticMailSendersConfiguration {

    @Bean("criticalMailSender")
    JavaMailSender criticalMailSender() {
        return createSender(
                "critical-smtp.example.net",
                587,
                System.getenv("CRITICAL_SMTP_USERNAME"),
                System.getenv("CRITICAL_SMTP_PASSWORD"));
    }

    @Bean("bulkMailSender")
    JavaMailSender bulkMailSender() {
        return createSender(
                "bulk-smtp.example.net",
                587,
                System.getenv("BULK_SMTP_USERNAME"),
                System.getenv("BULK_SMTP_PASSWORD"));
    }

    private static JavaMailSender createSender(
            String host,
            int port,
            String username,
            String password) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
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

Các import thông thường: `java.util.Properties`, `org.springframework.context.annotation.Bean`, `Configuration` và các lớp trong `org.springframework.mail.javamail`.

Đây là ví dụ ngắn cho hai sender tĩnh. Trong production không nên phân tán cách đọc secret bằng `System.getenv` ở nhiều bean; nên inject secret qua cấu hình runtime được kiểm soát và validate khi khởi động. Hai hostname là placeholder, không phải endpoint thật.

Khi có nhiều bean cùng kiểu:

~~~java
@Service
public class SeparateChannels {

    private final JavaMailSender critical;
    private final JavaMailSender bulk;

    public SeparateChannels(
            @Qualifier("criticalMailSender") JavaMailSender critical,
            @Qualifier("bulkMailSender") JavaMailSender bulk) {
        this.critical = critical;
        this.bulk = bulk;
    }
}
~~~

Nếu dùng auto-configuration của Spring Boot, phải hiểu cơ chế conditional: khi ứng dụng đã định nghĩa mail sender riêng, auto-configuration có thể **back off**. Không giả định các thuộc tính `spring.mail.*` được tự động bind vào mọi bean `JavaMailSenderImpl` do ứng dụng tự tạo.

### 4.2. Vì sao registry phù hợp khi có nhiều route?

Khi có hàng chục route kết hợp region × category × tenant, tạo mỗi route một bean thủ công có thể khó bảo trì. Một registry hỗ trợ:

~~~text
providerId -> JavaMailSender
            -> identity and credential reference
            -> capability and region metadata
            -> rate limiter / circuit breaker
~~~

**Logical provider ID khác route ID.** Một provider SMTP có thể phục vụ nhiều loại email được phép; một route có thể có nhiều provider ứng viên. Không đặt provider ID bằng tên người nhận hoặc tenant chưa kiểm chứng.

## 5. Khai báo nhiều SMTP provider qua Spring Boot configuration

Khi số provider tăng, nên quản lý endpoint dưới một prefix riêng, ví dụ `app.mail.providers`, thay vì tạo hàng loạt biến `spring.mail.host-1` không có quy ước binding. Một cấu hình minh họa:

~~~yaml
app:
  mail:
    providers:
      smtp-vn-critical-a:
        host: critical-vn.example.net
        port: 587
        username: ${SMTP_VN_CRITICAL_USER}
        password: ${SMTP_VN_CRITICAL_PASSWORD}
      smtp-vn-tx-a:
        host: transactional-vn.example.net
        port: 587
        username: ${SMTP_VN_TX_USER}
        password: ${SMTP_VN_TX_PASSWORD}
      smtp-eu-tx-a:
        host: transactional-eu.example.net
        port: 587
        username: ${SMTP_EU_TX_USER}
        password: ${SMTP_EU_TX_PASSWORD}
      smtp-eu-bulk-a:
        host: bulk-eu.example.net
        port: 587
        username: ${SMTP_EU_BULK_USER}
        password: ${SMTP_EU_BULK_PASSWORD}
~~~

Đây là **tập endpoint ví dụ**, không phải sơ đồ bắt buộc và không xác nhận khả năng residency của server thật. Hostnames kết thúc bằng `example.net` chỉ dùng minh họa. Với production, giá trị password phải được cấp từ secret manager, environment hoặc file secret ở runtime, không commit vào repository.

### 5.1. Bind cấu hình vào record

Với Spring Boot 3 và Java 17+, có thể dùng immutable `@ConfigurationProperties` record:

~~~java
package com.example.mail.routing;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MultiProviderMailProperties(
        Map<String, SmtpEndpoint> providers) {

    public record SmtpEndpoint(
            String host,
            int port,
            String username,
            String password) {
    }
}
~~~

Đăng ký properties class:

~~~java
@Configuration
@EnableConfigurationProperties(
        MultiProviderMailProperties.class)
public class MultiProviderMailConfiguration {
    // Bean registry được khai báo bên dưới.
}
~~~

Nếu dự án dùng Spring Boot phiên bản khác, cần điều chỉnh cách constructor binding và validation theo phiên bản thực tế. Không đưa password vào `toString()`/log: một Java record mặc định có `toString` chứa tất cả component, kể cả secret. Không log toàn bộ `MultiProviderMailProperties`.

### 5.2. Registry tạo sender riêng cho mỗi endpoint

~~~java
package com.example.mail.routing;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class MailSenderRegistry {

    private final Map<String, JavaMailSender> senders;

    public MailSenderRegistry(
            MultiProviderMailProperties settings) {

        if (settings.providers() == null
                || settings.providers().isEmpty()) {
            throw new IllegalStateException(
                    "No mail providers configured");
        }

        Map<String, JavaMailSender> built = new HashMap<>();
        settings.providers().forEach((id, endpoint) ->
                built.put(id, createSender(id, endpoint)));
        this.senders = Map.copyOf(built);
    }

    public JavaMailSender requireSender(String providerId) {
        JavaMailSender sender = senders.get(providerId);
        if (sender == null) {
            throw new IllegalArgumentException(
                    "Unknown mail provider ID");
        }
        return sender;
    }

    private static JavaMailSender createSender(
            String id,
            MultiProviderMailProperties.SmtpEndpoint endpoint) {

        if (endpoint == null
                || endpoint.host() == null
                || endpoint.host().isBlank()
                || endpoint.port() <= 0
                || endpoint.port() > 65535
                || endpoint.username() == null
                || endpoint.username().isBlank()
                || endpoint.password() == null
                || endpoint.password().isBlank()) {
            throw new IllegalStateException(
                    "Incomplete mail provider configuration: " + id);
        }

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(endpoint.host());
        sender.setPort(endpoint.port());
        sender.setUsername(endpoint.username());
        sender.setPassword(endpoint.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.setProperty("mail.smtp.auth", "true");
        props.setProperty("mail.smtp.starttls.enable", "true");
        props.setProperty("mail.smtp.starttls.required", "true");
        props.setProperty("mail.smtp.ssl.checkserveridentity", "true");
        props.setProperty("mail.smtp.connectiontimeout", "5000");
        props.setProperty("mail.smtp.timeout", "12000");
        props.setProperty("mail.smtp.writetimeout", "12000");
        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Wire registry:

~~~java
@Bean
MailSenderRegistry mailSenderRegistry(
        MultiProviderMailProperties settings) {
    return new MailSenderRegistry(settings);
}
~~~

Mỗi `JavaMailSenderImpl` được cấu hình riêng; không thay đổi host, port, username hoặc password của một sender đang dùng trong nhiều thread **ngay trước từng lần gửi**. Việc cấu hình một lần ở startup và dùng sender theo ID giúp tránh race khi nhiều worker chọn các endpoint khác nhau.

Đây là cấu hình **SMTP submission qua STARTTLS/port 587**. Với nhà cung cấp dùng implicit TLS/port 465, cấu hình `mail.smtp.ssl.enable=true` theo endpoint. Với provider dùng OAuth2, cơ chế xác thực sẽ khác password thông thường; cần adapter/transport đúng SASL/protocol và không giả định chỉ gán access token vào `setPassword` là hoàn tất.

Ngoài code trên, production cần cấu hình capability của provider, verified sender identity, giới hạn tốc độ và credential rotation. Không coi việc tạo được `JavaMailSenderImpl` là bằng chứng server thuộc region được ghi tên.

### 5.3. Tại sao không dùng một JavaMailSenderImpl rồi setHost liên tục?

Ví dụ **không nên làm**:

~~~java
// Singleton được nhiều worker dùng đồng thời.
sender.setHost(routeForCurrentRequest.host());
sender.setUsername(routeForCurrentRequest.username());
sender.setPassword(routeForCurrentRequest.password());
sender.send(mimeMessage);
~~~

Hai worker có thể thay host/credential xen kẽ, dẫn đến một message dùng sai account hoặc sai vùng. Một mail sender không nên bị xem là một “request context” có thể sửa tự do.

Giải pháp:

- Tạo sender/transport riêng theo provider ID, cấu hình bất biến trong vòng đời gửi.
- Dùng registry để lookup.
- Nếu phải cập nhật config khi rotate secret, sử dụng quy trình thay instance/bean và quản lý in-flight sends thay vì sửa nhiều field tuần tự.

## 6. Routing policy bằng Java

Trước khi gửi, ứng dụng cần chuyển thông tin nghiệp vụ tin cậy thành một route decision. Có thể biểu diễn khóa:

~~~java
package com.example.mail.routing;

public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}

public enum DeliveryRegion {
    VN, EU, US, OTHER
}

public record RouteKey(
        DeliveryRegion region,
        MailCategory category) {
}

public record RouteDecision(
        String primaryProviderId,
        String identityId,
        String policyVersion) {
}
~~~

Với Java, các top-level `public` class, enum và record phải nằm ở những file phù hợp, không copy tất cả vào một file. Các khai báo trên là các thành phần độc lập.

Một policy với vài route tĩnh:

~~~java
package com.example.mail.routing;

import java.util.Map;

public final class MailRoutingPolicy {

    private static final String VERSION = "routing-v3";

    private final Map<RouteKey, RouteDecision> routes = Map.of(
            new RouteKey(
                    DeliveryRegion.VN,
                    MailCategory.SECURITY),
            new RouteDecision(
                    "smtp-vn-critical-a",
                    "identity-vn-security",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.VN,
                    MailCategory.TRANSACTIONAL),
            new RouteDecision(
                    "smtp-vn-tx-a",
                    "identity-vn-transactional",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.EU,
                    MailCategory.TRANSACTIONAL),
            new RouteDecision(
                    "smtp-eu-tx-a",
                    "identity-eu-transactional",
                    VERSION),
            new RouteKey(
                    DeliveryRegion.EU,
                    MailCategory.MARKETING),
            new RouteDecision(
                    "smtp-eu-bulk-a",
                    "identity-eu-marketing",
                    VERSION)
    );

    public RouteDecision requireRoute(
            DeliveryRegion region,
            MailCategory category) {

        RouteDecision decision =
                routes.get(new RouteKey(region, category));
        if (decision == null) {
            throw new IllegalStateException(
                    "No approved mail route for this category and region");
        }
        return decision;
    }
}
~~~

Đây là policy minh họa chỉ có **bốn combination**. Những route chưa khai báo phải bị từ chối/giữ chờ thay vì âm thầm chọn default. Khi triển khai nhiều tenant/provider, thông thường cấu hình route được quản lý ở database hoặc declarative config có version, và policy phải lọc thêm consent, quota, health, sender identity và residency.

### 6.1. Đừng để người dùng tự chọn category ưu tiên cao

Không dùng DTO của API công khai như một bằng chứng chính sách:

~~~json
{
  "recipient": "unknown@example.com",
  "category": "SECURITY",
  "region": "EU",
  "providerId": "smtp-eu-critical-a"
}
~~~

Nếu bất kỳ user nào được chọn `SECURITY` và `providerId`, họ có thể lách quota hoặc gửi qua provider/identity không được ủy quyền. Service nên xác định category dựa trên use case đã xác thực, region từ dữ liệu nghiệp vụ được tin cậy, còn provider được quyết định bởi policy nội bộ.

### 6.2. Thứ tự ưu tiên của routing rule

Một số ứng dụng muốn có rule theo độ cụ thể:

~~~text
1. Explicit authorized tenant override
2. Region + category
3. Region default category
4. Global default (only if allowed by policy)
~~~

Không phải hệ thống nào cũng nên có `global default`. Với yêu cầu residency nghiêm ngặt, thiếu rule ở vùng tương ứng phải dừng gửi. Nếu có tenant override, cần validate nó vẫn nằm trong tập provider được phép về region, identity, quota và chính sách bảo mật.

### 6.3. Không route theo tỷ lệ ngẫu nhiên nếu không có traceability

Weighted routing (80% provider A, 20% provider B) hữu ích khi thử nghiệm sức tải hoặc chuyển dần provider. Nhưng các thay đổi cần lưu lại:

~~~text
routePolicyVersion
candidateProviderIds
selectedProviderId
selectionReason
experimentBucket or stable hash key (if used)
~~~

Đối với retry của **cùng delivery**, random lại provider ở mỗi lần có thể khiến hành vi không dự đoán được. Một lựa chọn thường tốt hơn là pin provider ở attempt đầu, rồi chỉ đổi khi một **fallback decision mới hợp lệ** đã được ghi nhận cùng audit.

## 7. Kết hợp routing với danh tính gửi email

Một route không chỉ là hostname SMTP. Một provider có thể yêu cầu sử dụng domain hoặc địa chỉ `From` đã verify, SPF/DKIM phù hợp và bounce/Return-Path riêng.

Ví dụ:

| Route | Header From | Reply-To | Envelope sender / bounce | DKIM identity |
| --- | --- | --- | --- | --- |
| VN security | `security@example.com` | `support@example.com` | `bounce@bounces.example.com` | `example.com` |
| VN transactional | `orders@example.com` | `orders-help@example.com` | `bounce@bounces.example.com` | `example.com` |
| EU marketing | `newsletter@news.example.com` | `marketing-help@example.com` | `bounce@bounces.news.example.com` | `news.example.com` |

Đây là **bộ tên minh họa**, không phải đảm bảo rằng một account SMTP tự động được phép gửi những địa chỉ đó. Các domain/subdomain và DKIM key cần được xác minh trong từng provider.

### 7.1. From, Reply-To và envelope sender khác nhau

~~~java
helper.setFrom("security@example.com");
helper.setReplyTo("support@example.com");
~~~

Hai lệnh này đặt **MIME headers**. Chúng không trực tiếp bảo đảm `MAIL FROM` của SMTP envelope trỏ tới bounce domain mong muốn. Với Jakarta Mail SMTP transport, thuộc tính `mail.smtp.from` có thể cấu hình envelope sender theo transport; provider cũng có thể override Return-Path. Không tự set `Return-Path` header để giả lập envelope.

Nếu một provider endpoint dùng chung cho nhiều sender identity có bounce khác nhau, không nên thay `mail.smtp.from` trên `Properties` của sender singleton trước từng request. Dùng sender riêng theo identity, cơ chế per-message của transport được hỗ trợ, hoặc custom return-path của provider.

### 7.2. SPF, DKIM và DMARC là yêu cầu của route

Khi thêm provider mới, cần:

- Xác minh quyền sở hữu domain dùng trong Header From.
- Cấu hình SPF cho hạ tầng gửi theo hướng dẫn provider; tránh bản ghi SPF chồng chéo hoặc vượt quá giới hạn DNS lookup.
- Cấu hình DKIM signing và verify key/domain phù hợp.
- Xem xét DMARC alignment giữa Header From với SPF domain (envelope sender) và/hoặc DKIM `d=`.
- Thiết lập MX/route cho bounce domain nếu dùng inbound DSN.
- Thử gửi tới môi trường test và kiểm tra kết quả xác thực.

Không giả định provider A gửi được domain X thì provider B cũng gửi được domain X. Khi failover, **identity và authentication configuration phải tương thích**; nếu không, email có thể được SMTP relay chấp nhận nhưng bị phía nhận đánh spam hoặc từ chối.

### 7.3. Reputation và quota không phải thuộc tính của một IP duy nhất

Provider có thể áp đặt giới hạn và theo dõi chất lượng gửi ở nhiều mức:

- SMTP credential/account.
- Sender domain/subdomain.
- IP pool, tenant hoặc vùng.
- Recipient domain, complaint/bounce rate.
- Loại traffic hoặc thỏa thuận dịch vụ.

Tách `MARKETING` khỏi `SECURITY` có thể giúp tránh cạnh tranh quota và giảm rủi ro reputation, nhưng chỉ thực sự có tác dụng nếu cấu hình account/domain/pool và chính sách provider hỗ trợ phân tách đó.

## 8. Service dispatch: chọn sender rồi tạo MIME bằng chính sender đó

Một lỗi thiết kế dễ mắc là tạo `MimeMessage` bằng sender A, sau đó chọn sender B dựa trên region. Có thể message vẫn là một Jakarta Mail object hợp lệ, nhưng charset, Session, envelope properties hoặc transport-specific behavior có thể không đồng nhất giữa hai cấu hình.

Trong routing service, nên quyết định provider **trước khi** gọi `createMimeMessage()` và dùng cùng sender cho toàn bộ attempt:

~~~text
Validated mail command
         |
         v
Select approved route
         |
         v
Resolve providerId -> JavaMailSender
         |
         v
sender.createMimeMessage()
         |
         v
MimeMessageHelper: From / To / body / attachment
         |
         v
sender.send(mimeMessage)
         |
         v
Store SMTP submission result
~~~

### 8.1. Một command có kiểu rõ ràng

~~~java
package com.example.mail.routing;

import java.util.UUID;

public record ValidatedMailCommand(
        UUID deliveryId,
        String tenantId,
        DeliveryRegion region,
        MailCategory category,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

Tên `ValidatedMailCommand` có nghĩa command được tạo **sau** khi tầng nghiệp vụ kiểm tra recipient, tenant, category, region, permission, suppression/consent và business deadline. Chỉ đặt tên record như vậy **không tự tạo validation**.

Một identity registry riêng:

~~~java
package com.example.mail.routing;

import java.util.Map;

public record SenderIdentity(
        String fromAddress,
        String replyToAddress) {
}

public final class SenderIdentityRegistry {

    private final Map<String, SenderIdentity> identities =
            Map.of(
                    "identity-vn-security",
                    new SenderIdentity(
                            "security@example.com",
                            "support@example.com"),
                    "identity-vn-transactional",
                    new SenderIdentity(
                            "orders@example.com",
                            "orders-help@example.com"),
                    "identity-eu-transactional",
                    new SenderIdentity(
                            "orders@example.com",
                            "orders-help@example.com"),
                    "identity-eu-marketing",
                    new SenderIdentity(
                            "newsletter@news.example.com",
                            "marketing-help@example.com"));

    public SenderIdentity requireIdentity(String id) {
        SenderIdentity identity = identities.get(id);
        if (identity == null) {
            throw new IllegalArgumentException(
                    "Unconfigured sender identity");
        }
        return identity;
    }
}
~~~

Identity ở đây là cấu hình minh họa; production cần kết hợp provider verification, domain alignment, bounce address và quy tắc tenant.

### 8.2. RoutingMailDispatcher

~~~java
package com.example.mail.routing;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public final class RoutingMailDispatcher {

    private final MailRoutingPolicy policy;
    private final MailSenderRegistry senderRegistry;
    private final SenderIdentityRegistry identities;

    public RoutingMailDispatcher(
            MailRoutingPolicy policy,
            MailSenderRegistry senderRegistry,
            SenderIdentityRegistry identities) {
        this.policy = policy;
        this.senderRegistry = senderRegistry;
        this.identities = identities;
    }

    public RouteDecision submit(
            ValidatedMailCommand command)
            throws MessagingException {

        RouteDecision route = policy.requireRoute(
                command.region(), command.category());

        SenderIdentity identity =
                identities.requireIdentity(route.identityId());

        JavaMailSender sender =
                senderRegistry.requireSender(
                        route.primaryProviderId());

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(identity.fromAddress());
        helper.setReplyTo(identity.replyToAddress());
        helper.setTo(command.recipient());
        helper.setSubject(command.subject());
        helper.setText(
                command.plainText(), command.htmlText());

        sender.send(message);
        return route;
    }
}
~~~

Đây là **đường gửi đồng bộ tối thiểu**. Nó cho thấy route selection và sender lookup, chưa có outbox, health, rate limiting, circuit breaker hoặc failover. Khi triển khai đáng tin cậy, không lưu route **chỉ sau** `send`: nếu JVM chết sau SMTP accepted thì có thể mất dấu vết provider đã được chọn. Nên ghi route decision/attempt record **trước** khi gọi SMTP, trong một transaction ngắn như phần sau.

Các thành phần `MailRoutingPolicy` và `SenderIdentityRegistry` có thể được khai báo thành Spring bean bằng `@Bean` hoặc `@Component`; ở ví dụ chúng là class thường để tập trung vào cơ chế chính. Không nên thêm `@Primary` cho một provider chỉ để tránh lỗi injection rồi vô tình khiến tất cả service gửi qua provider đó.

### 8.3. Khi dùng SimpleMailMessage

`SimpleMailMessage` phù hợp email text đơn giản:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom(identity.fromAddress());
mail.setTo(recipient);
mail.setSubject(subject);
mail.setText(text);
sender.send(mail);
~~~

Nó không có các khả năng HTML/multipart/attachment như `MimeMessageHelper`. Routing policy vẫn là một vấn đề độc lập: sender được chọn theo category/region, rồi gửi bằng loại message phù hợp.

### 8.4. Với một delivery nhiều recipient

Giả sử gửi cùng nội dung tới:

~~~text
user-a@example.vn   -> region VN
user-b@example.eu   -> region EU
user-c@example.us   -> region US
~~~

Không nên đưa cả ba vào **một** MIME message rồi chọn một provider dựa trên recipient đầu tiên. Vì các recipient có thể thuộc route, privacy policy, consent và quota khác nhau, nên tạo **một delivery cho mỗi recipient**, hoặc chia thành các nhóm có route và nghĩa vụ tương thích rõ ràng.

Điều này còn giúp theo dõi partial SMTP failures, retry count, suppression và bounce theo từng người nhận.

## 9. Cố định route trong transactional outbox

Một hệ thống cần gửi mail đáng tin cậy thường không nên gọi SMTP trực tiếp trong database transaction của nghiệp vụ. Thay vào đó:

~~~text
Create order / user event
           |
           v
BEGIN transaction
   +-- save business data
   +-- create mail_outbox row
   +-- assign category, region, tenant
COMMIT
           |
           v
Worker claims delivery
           |
           v
Routing policy resolves approved candidates
           |
           v
Persist route decision + attempt STARTED
COMMIT
           |
           v
JavaMailSender for providerId
           |
     +-----+------+
     |            |
     v            v
 SMTP accepted   Error / unknown
     |            |
     v            v
  mark SENT    RETRY / FAILED / UNKNOWN
~~~

Tách database transaction khỏi network call ngăn worker giữ lock database trong lúc SMTP hoặc attachment generation chậm.

### 9.1. Schema minh họa

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    delivery_key VARCHAR(180) NOT NULL UNIQUE,
    recipient VARCHAR(320) NOT NULL,
    category VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(80),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    selected_provider_id VARCHAR(100),
    selected_identity_id VARCHAR(100),
    route_policy_version VARCHAR(100),
    route_reason VARCHAR(100),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(40),
    smtp_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);

CREATE INDEX ix_mail_outbox_provider
    ON mail_outbox(selected_provider_id, status);
~~~

Schema này là **bản minh họa**: cần thêm cấu trúc lưu body/model hoặc reference bền vững tới template data, ownership/concurrency controls, retention và encryption/PII policy tùy ứng dụng.

### 9.2. Attempt history phải ghi provider thật được chọn

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INT NOT NULL,
    provider_id VARCHAR(100) NOT NULL,
    identity_id VARCHAR(100) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    route_reason VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'STARTED',
    error_code VARCHAR(100),
    failure_stage VARCHAR(60),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(outbox_id, attempt_no)
);
~~~

Lịch sử có thể là:

| Attempt | Provider | Trạng thái | Nguyên nhân |
| --- | --- | --- | --- |
| 1 | `smtp-vn-tx-a` | RETRYABLE_FAILURE | SMTP connect refused |
| 2 | `smtp-vn-tx-a` | RETRYABLE_FAILURE | Temporary throttle |
| 3 | `smtp-vn-tx-b` | SMTP_ACCEPTED | Approved failover |

Nhờ có `provider_id` trong từng attempt, người vận hành phân biệt retry cùng provider với fallback sang provider khác.

### 9.3. Ghi route decision trước SMTP call

Trong transaction claim/route:

1. Claim delivery atomically bằng row lock/lease.
2. Kiểm tra category, region và suppression vẫn hợp lệ.
3. Chọn route dựa trên phiên bản policy có thể audit.
4. Ghi provider/identity/policy version vào attempt record.
5. Tăng `attempt_count` và commit.
6. Chỉ sau đó thực hiện SMTP send.

Nếu worker chết sau khi chọn route nhưng trước khi send, attempt vẫn là `STARTED`. Một reconciler có thể phát hiện attempt quá hạn. Không suy ra SMTP đã nhận message chỉ vì có route decision.

### 9.4. Khi policy thay đổi giữa các attempt

Ví dụ delivery được tạo trong vùng VN ở thời điểm T1. Ở T2, operator chuyển primary từ `smtp-vn-tx-a` sang `smtp-vn-tx-b`. Hai chiến lược:

- **Pin policy version cho delivery:** dùng đúng chính sách đã ghi khi enqueue, phù hợp nhu cầu audit/reproducibility.
- **Re-evaluate khi retry:** dùng chính sách mới đã được duyệt, nhưng ghi decision/version riêng cho mỗi attempt.

Không mặc định lựa chọn nào cũng đúng. Với yêu cầu cư trú dữ liệu, policy mới có thể thu hẹp tập provider hợp lệ và cần có hiệu lực ngay. Với các email campaign gửi số lượng lớn, pin policy giúp tránh thay đổi route bất ngờ giữa các batch. Trong cả hai trường hợp, **thay đổi route phải là hành vi có ghi nhận**, không phải do config bị ghi đè không kiểm soát.

## 10. Failover không phải cứ gặp exception là đổi provider

Giả sử primary SMTP bị lỗi, ứng dụng muốn chuyển sang secondary. Phân biệt quan trọng nhất là **primary đã chấp nhận email hay chưa**.

~~~text
SMTP attempt to provider A
          |
          +--> Definite failure before message submission
          |      |
          |      v
          |  Evaluate eligible fallback candidates
          |
          +--> Definite permanent error
          |      |
          |      v
          |  Fix recipient/credential/policy; no blind failover
          |
          +--> SMTP accepted
          |      |
          |      v
          |  Record accepted; do not send again
          |
          +--> Unknown after DATA/timeout
                 |
                 v
            Reconcile / duplicate-aware policy
            (do not blindly submit to B)
~~~

### 10.1. Lỗi có thể cho phép fallback

Ví dụ có thể xem xét:

- Endpoint của primary không kết nối được **trước khi gửi message**.
- Provider tạm unavailable, có bằng chứng message chưa được chấp nhận.
- Provider trả `421`/`4xx` ở giai đoạn an toàn để thử sang endpoint khác.
- Primary hết quota trong khi secondary được phép, còn capacity và sender identity tương thích.

Ngay cả khi lỗi có vẻ tạm thời, phải bảo đảm secondary **được phép xử lý region/category/tenant** và không vi phạm deadline/consent/size policy.

### 10.2. Lỗi không nên fallback ngay

| Lỗi | Vì sao không tự đổi provider? |
| --- | --- |
| Invalid recipient | Đổi SMTP relay không biến địa chỉ sai thành đúng |
| Missing template variable | Cần sửa dữ liệu/render, provider khác cũng lỗi |
| Authentication failure do secret sai | Có thể là cấu hình hoặc credential bị revoke; cần kiểm tra và cảnh báo |
| Sender domain chưa verified | Secondary có thể cũng không được phép dùng From/Return-Path |
| Message quá lớn | Secondary chỉ có ích khi policy/capability thực sự chấp nhận loại/size đó |
| Security/suppression restriction | Failover không được vượt consent hoặc danh sách chặn |
| SMTP result unknown | Có thể primary đã nhận; gửi B tạo duplicate |
| Region restriction | Không cho phép chuyển qua vùng khác chỉ vì endpoint chính hỏng |

### 10.3. Tình huống khó: timeout sau DATA

~~~text
App -> A: DATA + MIME bytes
A   -> App: [connection lost before final response]

Did A accept the email?
  - Possibly yes
  - Possibly no
~~~

Nếu ứng dụng ngay lập tức gửi cùng message tới B, người nhận có thể nhận **hai bản**, và bounces/delivery events có thể đến từ cả hai provider.

Với SMTP thuần, không có một transaction chung với database, nên thường chỉ đạt **at-least-once**. `Message-ID` giúp correlate nhưng không bắt buộc SMTP server loại bỏ duplicate. Nếu provider cung cấp API có idempotency key, có thể sử dụng theo hợp đồng riêng; không mặc định SMTP hỗ trợ exactly-once.

Một chính sách hợp lý:

1. Đánh dấu kết quả `UNKNOWN` hoặc lưu attempt có kết quả chưa chắc chắn.
2. Ghi provider ID và giai đoạn xảy ra timeout.
3. Đối soát provider logs/API nếu có.
4. Dùng business deadline và duplicate tolerance để quyết định retry/redrive.
5. Nếu retry, lưu một attempt mới và lý do quyết định, không lặng lẽ chuyển provider.

### 10.4. Failover có kiểm soát bằng candidate allowlist

Một route có thể lưu:

~~~text
primary: smtp-eu-tx-a
approvedFallbacks:
  - smtp-eu-tx-b
disallowed:
  - smtp-us-tx-a
  - smtp-eu-bulk-a
~~~

`smtp-eu-tx-b` chỉ được chọn nếu đã cấu hình identity/domain, data policy, capacity và hợp đồng tương thích. Không nên tự tạo danh sách fallback từ tất cả key trong registry.

**Thứ tự an toàn:** policy eligibility trước, provider health/capacity sau, rồi mới chọn từ tập hợp còn lại.

## 11. Rate limit và circuit breaker cho từng provider

Một route đúng vẫn có thể thất bại nếu cả hệ thống dồn quá nhiều email vào cùng một SMTP account. Mỗi provider hoặc sending identity nên có giới hạn:

- Số message/phút, giờ hoặc ngày.
- Số recipient/message và tổng recipient/phút.
- Số SMTP connection đồng thời.
- Kích thước MIME message.
- Loại email được phép, giờ gửi hoặc giới hạn campaign.
- Số retry trong một khoảng và chính sách backoff.

~~~text
Ready mail deliveries
          |
          v
Route + provider eligibility
          |
          v
Per-provider quota / limiter
          |
          +--> Capacity available
          |      |
          |      v
          |  Submit via sender
          |
          +--> No capacity
                 |
                 v
            Schedule later
            (do not claim and spin)
~~~

Một **circuit breaker** có thể tạm dừng gọi provider nếu tỷ lệ timeout/unavailable tăng mạnh. Nhưng circuit open không chứng minh từng delivery thất bại vĩnh viễn; thường cần giữ delivery ở trạng thái chờ hoặc retry theo backoff. Tránh biến mọi lần circuit open thành một SMTP attempt thất bại nếu thực tế không hề gọi SMTP.

### 11.1. Tách capacity cho security và marketing

Nếu cả hai loại email dùng chung SMTP account và quota, chỉ có code route riêng **chưa đủ** đảm bảo OTP không bị một campaign làm chậm. Có thể dùng:

- Account/IP pool riêng khi provider hỗ trợ.
- Queue và concurrency giới hạn riêng.
- Scheduler có ưu tiên hoặc reserved capacity.
- Token bucket theo provider và category.
- Bulkhead cho thread pool/connection pool.

### 11.2. Backoff và jitter

Một retry policy minh họa:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^{n-1})
\]

Với `d_0 = 30 giây` và jitter, lỗi tạm thời không khiến hàng nghìn worker cùng kết nối lại đúng một thời điểm. `max_attempts`, retry deadline và backoff cần khác nhau theo loại email: đường reset password có thời hạn ngắn hơn newsletter không khẩn cấp.

Không dùng retry vô hạn để che việc không còn provider hợp lệ; hãy phát tín hiệu `NO_ELIGIBLE_ROUTE` hoặc `PROVIDER_UNAVAILABLE` có thể quan sát và xử lý.

## 12. Một route phải có cả đường nhận bounce/feedback

Sau khi gửi, ứng dụng có thể nhận lỗi bất đồng bộ: provider chấp nhận SMTP message nhưng server đích từ chối giao thư sau đó. Một chiến lược multi-provider phải biết **bounce/webhook nào thuộc delivery nào**.

~~~text
Outbox delivery D1
     |
     +--> Provider A submit -> providerMessageId A-100
     |
     +--> (if approved, later attempt) Provider B
                -> providerMessageId B-240

Provider A webhook / DSN ----+
                             |
Provider B webhook / DSN ----+--> verify source
                             |    normalize event
                             |    match delivery + attempt + recipient
                             v
                      Delivery feedback history
~~~

Không nên có một webhook handler duy nhất nhận payload từ mọi provider rồi chỉ đọc trường `email` để quyết định chặn gửi. Event phải được xác minh bằng **chữ ký/credential do provider định nghĩa**, và correlate với provider ID/attempt/recipient cụ thể.

### 12.1. Các ID cần phân biệt

| ID | Sinh ở đâu? | Vai trò |
| --- | --- | --- |
| `deliveryId` | Hệ thống ứng dụng | Định danh một delivery tới một recipient |
| `attemptId` | Hệ thống ứng dụng | Định danh một lượt nộp SMTP |
| `providerId` | Routing registry | Đường SMTP/API đã dùng |
| `providerMessageId` | Nhà cung cấp | Correlate provider event khi được trả về |
| `Message-ID` | MIME/transport | Truy vết email nhưng không bảo đảm unique theo recipient |
| `eventId` | Provider/webhook | Deduplicate delivery/bounce/complaint event |

Một số provider không trả providerMessageId trong giao thức SMTP một cách chuẩn hóa, hoặc chỉ cung cấp ID thông qua header/API/log. Vì vậy, ứng dụng phải thiết kế cách correlation theo năng lực thật của từng nhà cung cấp, không giả định `JavaMailSender.send` luôn trả một external ID.

### 12.2. Normalize provider events

Provider A có thể phát `delivered` và `bounce`; provider B có `deferred`, `failed` hoặc DSN `Action: failed`. Tầng adapter nên chuyển chúng về mô hình chung:

~~~java
public enum MailFeedbackType {
    SMTP_ACCEPTED,
    RECEIVER_ACCEPTED,
    DELAYED,
    HARD_BOUNCE,
    FINAL_SOFT_BOUNCE,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedMailFeedback(
        String providerId,
        String providerEventId,
        String providerMessageId,
        java.util.UUID deliveryId,
        String recipient,
        MailFeedbackType type,
        String safeErrorCode,
        java.time.Instant occurredAt) {
}
~~~

Đây là model ứng dụng minh họa, không phải API Spring Mail. Event `DELAYED` thường có nghĩa provider còn đang thử giao, **không tự động yêu cầu ứng dụng gửi lại qua provider B**. Nếu ứng dụng tạo một message mới trong khi provider A đang retry nội bộ, nguy cơ trùng rất cao.

### 12.3. Hard bounce và complaint áp dụng xuyên provider

Nếu một địa chỉ đã được xác minh không tồn tại, chuyển sang một provider khác thường không giúp gì. Nên có **suppression policy** ở tầng ứng dụng:

~~~text
Verified hard bounce / spam complaint
              |
              v
Central suppression policy
              |
        +-----+------+
        |            |
        v            v
     Provider A   Provider B
     cannot send  cannot send
     outside policy for same recipient
~~~

Không chỉ dựa vào suppression list riêng của provider A, vì khi failover B có thể không biết recipient đã bị bounce/complaint. Với marketing cần áp dụng consent/unsubscribe theo phạm vi phù hợp; với transactional/security cần có chính sách xử lý địa chỉ không hợp lệ, không được “lách” suppression chỉ bằng đổi provider.

### 12.4. Domain alignment và bounce route khi failover

Nếu provider A và B dùng bounce domain khác nhau:

- Phải kiểm tra MX/Return-Path của từng provider.
- Có webhook/IMAP credential và secret riêng cho từng luồng.
- Nên lưu provider/attempt ở lúc gửi để biết event đến từ đường nào.
- Không ghi đè `providerMessageId` của attempt cũ chỉ vì retry qua provider mới.
- Chỉ cập nhật state tổng hợp theo quy tắc event ordering và confidence.

Địa chỉ `Reply-To` cho người dùng trả lời **không phải** nơi SMTP DSN bắt buộc quay về. Địa chỉ bounce thường gắn với envelope `MAIL FROM` hoặc chính sách Return-Path của provider.

## 13. Định tuyến theo khu vực và kiểm soát dữ liệu

Các tên như `smtp-eu-a` hoặc `smtp-vn-a` chỉ là **logical labels**. Không được coi tên đó là bằng chứng:

- Provider lưu dữ liệu trong khu vực tương ứng.
- Bản sao lưu/log/webhook metadata cũng ở vùng đó.
- Email không đi qua relay hoặc mạng ở khu vực khác.
- Subprocessor/cơ sở xử lý dữ liệu tuân thủ mọi yêu cầu pháp lý.

Chính sách dữ liệu có thể cần xem xét:

| Dữ liệu/hệ thống | Câu hỏi cần xác định |
| --- | --- |
| Mail body/attachment | Có dữ liệu cá nhân hoặc tài liệu bị hạn chế truyền qua vùng khác? |
| Outbox database | Queue/payload đang được lưu ở vùng nào? |
| SMTP provider | Provider xử lý, lưu tạm, log và backup ở đâu? |
| Webhook/DSN | Phản hồi giao thư có chứa recipient, body/headers? Về region nào? |
| Observability | Log, traces, metrics có PII hoặc định danh tenant không? |
| Support/admin access | Ai có quyền truy cập message và metadata? |
| Retention | Dữ liệu tồn tại bao lâu ở từng nhà cung cấp? |
| Encryption/keys | TLS, encryption at rest và quyền khóa được quản lý thế nào? |

**Route selection chỉ là một phần của đáp ứng yêu cầu residency.** Một hệ thống gửi bằng SMTP EU nhưng ghi toàn bộ body vào central queue ở một vùng không được phép thì chưa đạt mục tiêu tổng thể.

### 13.1. Resolve region từ nguồn tin cậy

Ví dụ một dịch vụ xác định vùng:

~~~java
public interface RecipientRegionResolver {
    DeliveryRegion resolveFor(
            String tenantId,
            String recipientAccountId);
}
~~~

Implementation có thể dựa vào policy tenant, địa chỉ đã được xác minh hoặc hợp đồng khách hàng. Không tự suy vùng từ địa chỉ email có hậu tố quốc gia, IP truy cập gần nhất hoặc một field request không có kiểm chứng.

### 13.2. Chuyển vùng chỉ khi được phép

Một policy có thể quy định:

~~~text
EU transactional:
  primary = smtp-eu-tx-a
  permitted fallback = smtp-eu-tx-b
  cross-region fallback = prohibited
~~~

Nếu cả hai provider EU đều unavailable, hệ thống phải chờ hoặc ghi nhận không có route hợp lệ, **không tự chuyển sang US chỉ vì US đang khỏe**. Một chính sách khác có thể cho phép cross-region khi đã có cơ sở ủy quyền, thỏa thuận và điều kiện đáp ứng; quyết định đó phải được thể hiện tường minh trong policy version và audit.

### 13.3. Multi-tenant isolation

Nếu ứng dụng phục vụ nhiều doanh nghiệp:

- Tenant A không được chọn SMTP account, sender domain hoặc quota của tenant B.
- Route rule và secret reference cần được kiểm soát theo tenant.
- Khi nhận feedback, phải kiểm tra `tenantId` của event/delivery.
- Không nhận `providerId` tùy ý trong API công khai rồi lookup secret.
- Dashboard/trace phải giới hạn dữ liệu theo quyền truy cập tenant.

Một provider có thể phục vụ nhiều tenant nếu hợp đồng/phân quyền cho phép. Tuy nhiên, phải giữ identity, quota, From domain, suppression và webhook correlation riêng khi cần.

## 14. Quy tắc chọn provider dựa trên khả năng

Không phải SMTP provider nào cũng chấp nhận cùng loại message. Một registry có thể lưu metadata:

~~~java
public record ProviderCapability(
        String providerId,
        DeliveryRegion approvedRegion,
        boolean transactionalAllowed,
        boolean marketingAllowed,
        long maxMessageBytes,
        int maxRecipients,
        boolean supportsRequiredTls,
        java.util.Set<String> verifiedIdentityIds) {
}
~~~

Các field trên là **thông tin do operator hoặc hệ thống tích hợp xác minh**, không được suy ra từ việc provider khởi tạo thành công. Các capability quan trọng khác có thể gồm support for custom Return-Path, dedicated IP, DKIM, API feedback, deliverability reporting, attachment restrictions hoặc regional data policy.

### 14.1. Ví dụ filter có chủ đích

Một provider chỉ được coi là eligible khi tất cả điều kiện đều đúng:

~~~text
provider.region approved for this delivery
AND category allowed
AND identityId is verified by provider
AND estimatedMessageBytes <= provider message limit
AND recipient count within policy
AND required TLS and authentication available
AND tenant authorized to use provider
AND sender health/capacity acceptable
~~~

Nếu không có provider hợp lệ, không dùng một global fallback bất chấp điều kiện. Lưu lỗi routing có cấu trúc như `NO_ELIGIBLE_PROVIDER`, `IDENTITY_NOT_VERIFIED`, `REGION_RESTRICTED` hoặc `MESSAGE_SIZE_UNSUPPORTED`; tùy lỗi, có thể chuyển `HOLD`, `RETRY` hoặc `FAILED` theo policy.

### 14.2. Thay provider khi message có attachment

Khi secondary có size limit nhỏ hơn primary, một message được primary chấp nhận có thể bị secondary từ chối. Vì vậy, không chỉ lọc theo type và region, mà còn kiểm tra **ước lượng kích thước MIME sau transfer encoding**. Đính kèm nhị phân thường tăng kích thước vì Base64; một file 20 MiB có thể tạo message lớn hơn đáng kể.

Để giảm rủi ro, có thể:

- Dùng link tải an toàn thay attachment khi business policy cho phép.
- Giới hạn đầu vào trước khi tạo MIME.
- Chọn route có hỗ trợ kích thước đã tính.
- Không retry vô hạn lỗi message quá lớn qua nhiều provider.

### 14.3. Loại email cũng ảnh hưởng delivery deadline

Ví dụ chính sách minh họa:

| Category | Priority | Deadline mẫu | Hành vi khi provider unavailable |
| --- | --- | --- | --- |
| SECURITY | Highest | Trước khi OTP/reset token hết hạn | Retry nhanh nhưng có giới hạn, không gửi token hết hạn |
| TRANSACTIONAL | Normal/high | Theo SLA nghiệp vụ | Retry/backoff, theo dõi outbox |
| MARKETING | Bulk | Campaign window | Delay/pause khi quota thấp, không vượt consent |

Đây không phải các giá trị deadline mặc định của Spring Mail. Nếu một link đặt lại mật khẩu hết hạn sau 10 phút mà email đến chậm hơn, việc gửi thư không còn giá trị có thể gây khó hiểu cho người dùng.

## 15. Cấu hình thay đổi và quá trình rollout

Khi thêm hoặc thay một provider:

1. Tạo credential qua secret manager, cấp đúng quyền/tenant/region.
2. Xác minh sender domain, SPF/DKIM/DMARC và bounce domain.
3. Kiểm tra TLS, hostname/certificate, AUTH và endpoint network.
4. Xác minh giới hạn message, quota, throughput, retention và data policy.
5. Định nghĩa capability metadata và route eligibility.
6. Tạo một **routing policy version** mới, không sửa ngầm một rule đang dùng.
7. Thử trong staging với test identities/recipients được kiểm soát.
8. Canary traffic theo một tỷ lệ nhỏ trong tập eligible.
9. Quan sát SMTP acceptance, latency, error rate, bounce/complaint và quota.
10. Tăng dần lưu lượng; có kế hoạch rollback và audit.

### 15.1. Vì sao canary cần sticky choice?

Nếu cùng một delivery được retry nhiều lần, dùng random per-attempt có thể làm một mail đi qua cả A và B. Với canary, có thể xác định nhóm thử nghiệm bằng một stable hash trên delivery/tenant hoặc một sampling key được kiểm soát, rồi **ghi route decision** vào outbox.

~~~text
stableBucket(deliveryId or tenantId)
  0..4 -> canary provider B
  5..99 -> existing provider A
~~~

Không dùng hash cố định trên email recipient làm public metric label hoặc chia sẻ giá trị có PII. Nếu cần sticky theo tenant, lưu bucket một cách an toàn và kiểm tra chính sách dữ liệu trước khi phân nhóm.

### 15.2. Rollback cấu hình không thay đổi lịch sử đã gửi

Khi canary thất bại, có thể đưa traffic mới về provider cũ. Nhưng:

- Attempt đã được SMTP accepted phải giữ provider ID ban đầu.
- Event bounce/delivery của provider canary có thể đến sau khi rollback.
- Những job còn ở `UNKNOWN` không tự động được resend.
- Credential và webhook endpoint của provider canary có thể cần giữ hoạt động trong thời gian đối soát.

Tắt toàn bộ event ingestion của provider vừa rollback có thể làm mất feedback về những email đã gửi trước đó.

## 16. Quan sát định tuyến qua metrics, logs và tracing

Một hệ thống nhiều provider cần trả lời được:

- Trong 15 phút gần đây, có bao nhiêu mail mỗi loại được gửi qua provider A và B?
- Vì sao provider EU secondary bắt đầu nhận traffic?
- Provider nào đang tăng `4xx`, `5xx`, authentication error hoặc timeout?
- Những email nào không có route hợp lệ?
- Có cross-region routing hoặc identity mismatch nào được phát hiện?
- Có message bị nộp hai lần vì failover/retry không?
- Chi phí, quota và latency thay đổi thế nào sau khi canary?

### 16.1. Metrics đề xuất

| Metric | Loại | Ý nghĩa |
| --- | --- | --- |
| `mail_route_decisions_total` | Counter | Số lần chọn route theo category/region/provider/reason |
| `mail_route_rejected_total` | Counter | Không có route hợp lệ hoặc bị policy chặn |
| `mail_provider_submissions_total` | Counter | Lượt SMTP submission theo provider/outcome |
| `mail_provider_send_duration_seconds` | Timer/Histogram | Thời gian transport theo provider |
| `mail_provider_failover_total` | Counter | Số attempt chọn secondary được phê duyệt |
| `mail_provider_retry_total` | Counter | Lượt retry bắt đầu, không phải chỉ được lên lịch |
| `mail_provider_capacity_denied_total` | Counter | Provider hết quota/concurrency ở tầng ứng dụng |
| `mail_provider_circuit_open` | Gauge | Circuit breaker đang mở hay không |
| `mail_provider_inflight` | Gauge | Số attempt đang dùng provider |
| `mail_outbox_due_count` | Gauge | Số delivery đến hạn chưa được gửi |
| `mail_outbox_oldest_due_age_seconds` | Gauge | Độ quá hạn lớn nhất |
| `mail_feedback_events_total` | Counter | Delivery/bounce/complaint đã xác minh theo provider |

Nếu dùng Micrometer:

~~~java
public void recordRoute(
        MeterRegistry registry,
        RouteDecision route,
        MailCategory category,
        DeliveryRegion region,
        String reason) {

    Counter.builder("mail.route.decisions")
            .tag("provider", route.primaryProviderId())
            .tag("category", category.name())
            .tag("region", region.name())
            .tag("reason", reason)
            .register(registry)
            .increment();
}
~~~

`MeterRegistry` và `Counter` thuộc `io.micrometer.core.instrument`. Trong code production, `reason` phải nằm trong danh mục **hữu hạn** như `PRIMARY`, `FALLBACK_AFTER_PRE_SUBMISSION_FAILURE`, `CAPACITY_SHIFT`. Không dùng raw exception message làm tag.

**Không** dùng `recipientEmail`, `tenantId` có cardinality lớn, `deliveryId`, `Message-ID` hoặc SMTP response nguyên văn làm metric labels. Dùng structured log/audit có quyền truy cập kiểm soát để điều tra từng delivery.

### 16.2. Đừng cộng trùng metric giữa các replica

Counter được phát ở từng worker có thể tổng hợp theo instance để tính tốc độ. Tuy nhiên, nếu mỗi worker query **cùng outbox database** rồi export một gauge queue toàn cục, cộng tất cả gauge sẽ nhân đôi/nhân N backlog. Với global snapshot, nên có collector authoritative hoặc dùng aggregation phù hợp (ví dụ max cho cùng phạm vi) và ghi rõ nguồn số liệu.

### 16.3. Structured log cho mỗi routing attempt

~~~json
{
  "event": "mail.routing.attempt_started",
  "deliveryId": "opaque-id",
  "attempt": 2,
  "category": "TRANSACTIONAL",
  "region": "VN",
  "providerId": "smtp-vn-tx-b",
  "identityId": "identity-vn-transactional",
  "routePolicyVersion": "routing-v3",
  "routeReason": "APPROVED_FALLBACK",
  "workerId": "worker-02"
}
~~~

Đây là log minh họa, không chứa username/password, email recipient, subject, MIME body hay token. Sau mỗi attempt nên có event outcome với `smtpResult`, `failureStage`, `safeErrorCode`, `durationMs` và kết quả commit outbox.

Nếu dữ liệu region/tenant được coi là nhạy cảm theo policy, giới hạn quyền đọc log và mức độ chi tiết. Đừng serialize nguyên object `MultiProviderMailProperties` chứa password chỉ để debug route.

### 16.4. Một số cảnh báo hữu ích

| Tín hiệu | Ý nghĩa | Hành động đầu tiên |
| --- | --- | --- |
| `NO_ELIGIBLE_PROVIDER` tăng | Policy thiếu hoặc provider bị vô hiệu hóa | Kiểm tra ma trận route/capabilities |
| Security email quá deadline | Đường ưu tiên bị nghẽn | Xem queue, quota và endpoint critical |
| SMTP auth failure tăng | Credential/provider thay đổi | Kiểm tra secret version, không retry dồn dập |
| Failover rate tăng | Primary có thể không ổn định | Kiểm tra lỗi/health/capacity của primary |
| Secondary cũng bị throttle | Cả pool thiếu capacity | Rate limit, backpressure, giảm bulk |
| Sender identity rejected | Domain chưa verified hoặc policy thay đổi | Kiểm tra From/DKIM/Return-Path ở provider |
| Cross-region attempt bị chặn | Policy hoạt động như thiết kế hoặc request sai region | Điều tra nguồn dữ liệu region/tenant |
| Bounce/complaint tăng sau rollout | Reputation/deliverability suy giảm | Dừng canary, xem DNS/consent |
| UNKNOWN attempts tăng | Timeout sau DATA hoặc DB state-update lỗi | Đối soát trước khi retry/fallback |

Ngưỡng cảnh báo phải dựa trên SLO và lưu lượng. Một lỗi cá biệt không nhất thiết là incident, còn sự cố 100% authentication của đường reset password có thể cần cảnh báo ngay.

### 16.5. Health check không phải bằng chứng delivery

`JavaMailSenderImpl.testConnection()` có thể kiểm tra kết nối/xác thực theo transport; nếu dùng làm health probe quá thường xuyên có thể tạo lưu lượng, phụ thuộc provider/network và quota. Không nên dùng việc gửi email thật vào health endpoint chạy mỗi vài giây.

Health thường nên kết hợp:

- Circuit-breaker state.
- Tỷ lệ kết nối/gửi thành công gần đây.
- Hạn mức/quota còn khả dụng theo provider API nếu có.
- Worker progress và queue latency.
- Probes thực sự cần thiết với tần suất thấp, timeout giới hạn.

Một provider “đang connect được” vẫn có thể bị từ chối khi nộp message vì From/domain/size/quota. Health là **tín hiệu chọn route**, không phải bảo đảm kết quả.

## 17. Kiểm thử routing policy

Tách policy khỏi SMTP transport cho phép kiểm thử phần quyết định bằng unit test nhanh, còn integration test kiểm tra mỗi sender có thể kết nối và nhận đúng message.

### 17.1. Unit test ma trận loại × vùng

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MailRoutingPolicyTest {

    private final MailRoutingPolicy policy =
            new MailRoutingPolicy();

    @Test
    void choosesEuBulkForEuMarketing() {
        RouteDecision decision = policy.requireRoute(
                DeliveryRegion.EU,
                MailCategory.MARKETING);

        assertThat(decision.primaryProviderId())
                .isEqualTo("smtp-eu-bulk-a");
        assertThat(decision.identityId())
                .isEqualTo("identity-eu-marketing");
    }

    @Test
    void rejectsCombinationWithoutApprovedRoute() {
        assertThrows(
                IllegalStateException.class,
                () -> policy.requireRoute(
                        DeliveryRegion.OTHER,
                        MailCategory.SECURITY));
    }
}
~~~

Những test này kiểm tra policy minh họa được định nghĩa ở phần 6. Test production cần cover **toàn bộ combination được hỗ trợ**, route thiếu, tenant override, fallback restriction, suppression, capability, message size và thay đổi policy version.

### 17.2. Property-based hoặc table-driven test

Thay vì viết một test riêng cho hàng chục route:

~~~text
Input:
  (VN, SECURITY)       -> smtp-vn-critical-a
  (VN, TRANSACTIONAL)  -> smtp-vn-tx-a
  (EU, TRANSACTIONAL)  -> smtp-eu-tx-a
  (EU, MARKETING)      -> smtp-eu-bulk-a

Invariant:
  region matches approved processing region
  category allowed by provider capability
  identity verified on selected provider
  no rule bypasses tenant policy
~~~

Có thể dùng `@ParameterizedTest` với `@MethodSource` trong JUnit 5 để kiểm tra bảng; nếu route lưu trong cấu hình, test còn nên xác nhận **mọi provider ID trong policy tồn tại trong registry**. Những test cấu hình này giúp phát hiện thay đổi YAML nhưng quên thêm credential/endpoint.

### 17.3. Test hai provider bằng SMTP sink

Một integration test có thể chạy **hai container Mailpit hoặc GreenMail** riêng biệt:

~~~text
                    Spring Boot test
                          |
                RoutingMailDispatcher
                   /            \
                  v              v
         JavaMailSender VN   JavaMailSender EU
                  |              |
                  v              v
             Mailpit VN       Mailpit EU
                  |              |
                  +------+-------+
                         |
                         v
                    Test assertions
~~~

Test cases:

1. Gửi một `TRANSACTIONAL/VN`; Mailpit VN nhận, Mailpit EU không nhận.
2. Gửi một `MARKETING/EU`; đúng marketing sender/route nhận, không dùng security pool.
3. Kiểm tra MIME `From` và `Reply-To` theo identity đã cấu hình.
4. Nếu một loại/vùng không có route, không SMTP server nào nhận message.
5. Gửi song song hai region, bảo đảm không hoán đổi credential/host.
6. Gửi lại cùng command sau khi state `SENT`; outbox/idempotency policy phải chặn nếu không cho phép gửi trùng.

Với Testcontainers, dùng `getHost()` và `getMappedPort(1025)` cho từng container thay vì giả định cả hai cùng host port. Dùng subject hoặc correlation ID riêng cho mỗi test; tránh test flake vì mailbox chứa message cũ hoặc `@Async` chưa hoàn tất.

### 17.4. Integration test failover

Cần một fake SMTP server có thể **tạo lỗi có kiểm soát** để test giai đoạn protocol:

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Primary không kết nối được trước submit | Secondary chỉ được dùng nếu nằm trong approved fallback |
| Primary trả lỗi recipient vĩnh viễn | Không gửi lại qua secondary |
| Primary báo 250 accepted | Không gửi secondary |
| Mất kết nối sau DATA, outcome không rõ | Không fallback mù; chuyển UNKNOWN/reconciliation |
| Secondary không được phép xử lý region | Fail closed, không gửi |
| Primary auth fail | Cảnh báo credential/config, không retry dồn dập |
| Primary throttle, secondary đã đầy quota | Schedule retry, không ép gửi |
| Policy bị thay giữa attempts | Attempt history giữ đủ policy/provider đã chọn |

SMTP sink mặc định chủ yếu nhận và giữ mail, có thể không hỗ trợ giả lập mọi lỗi 4xx/5xx hoặc timeout sau DATA. Với các kịch bản đó, dùng fake SMTP có programmable responses, mock tầng transport cho logic thuần và integration harness phù hợp.

### 17.5. Test webhook và suppression

Với hai provider, kiểm tra:

- Webhook A không vượt được verifier B.
- Event ID trùng được deduplicate theo namespace provider.
- Event tới trễ sau failover vẫn map đúng attempt/delivery.
- Một hard bounce đã xác minh chặn những lượt gửi tiếp theo **ở cả A và B** theo policy.
- Complaint của marketing không bị coi là lỗi SMTP submission.
- `DELAYED` từ provider A không kích hoạt nộp message mới tới B khi A còn retry nội bộ.
- Một DSN không map được delivery/recipient không tự xóa recipient hợp lệ.

### 17.6. Kiểm thử bảo mật và residency

Test các bất biến:

1. User không thể chọn `providerId` từ request để lách quyền.
2. Tenant A không dùng credential/From domain của tenant B.
3. Route thiếu approved region **không có fallback toàn cục**.
4. Logging và metrics không lộ SMTP password/token.
5. Marketing email thiếu consent không được nộp cho bất kỳ provider nào.
6. Test account/SMTP sink không tự gửi ra Internet.
7. Secondary chưa verified domain không được chọn.
8. Khi không có provider hợp lệ, job có trạng thái/cause rõ, không mất lặng lẽ.

Trong production, cần kiểm thử với các quy tắc xử lý dữ liệu đã được phê duyệt; một enum `EU` không tự chứng minh toàn bộ hạ tầng tuân thủ.

## 18. Tình huống vận hành: lỗi provider chính tại một khu vực

Giả sử vào 09:00, SMTP primary dành cho transactional email ở vùng VN bị mất kết nối. Hệ thống có một secondary trong cùng tập provider đã được phê duyệt.

~~~text
09:00  smtp-vn-tx-a starts timing out before SMTP handshake
09:01  Queue VN/TRANSACTIONAL age begins rising
09:02  Circuit breaker opens for primary A
09:02  Routing policy confirms secondary B is eligible
09:03  New, not-yet-submitted deliveries are routed to B
09:04  Retryable attempts with proven pre-submission failure
       may route to B according to policy
09:05  A's unknown-outcome attempts remain for reconciliation
09:06  Dashboard shows increased route_reason=APPROVED_FALLBACK
09:10  A recovers; rollout back to A follows recovery policy
~~~

**Không trộn hai nhóm job**:

- **Chưa từng nộp SMTP hoặc chắc chắn thất bại trước submission:** có thể chọn B nếu policy cho phép.
- **Có khả năng A đã accepted nhưng client không biết:** cần đối soát và xử lý duplicate risk trước khi resend qua B.

### 18.1. Runbook khi fallback tăng nhanh

**Bước 1 — Xác nhận tín hiệu.** Kiểm tra failover rate, SMTP timeout/auth failure, queue age và nguồn số liệu. Không kết luận provider bị outage chỉ từ một error request.

**Bước 2 — Xác định nhóm ảnh hưởng.** Bao nhiêu delivery `SECURITY`, `TRANSACTIONAL` hay `MARKETING` bị tác động, ở region nào và còn bao nhiêu thời gian trước deadline?

**Bước 3 — Kiểm tra primary.** Xem DNS/network, TLS, authentication, quota, rate limit, thay đổi secret và provider status.

**Bước 4 — Kiểm tra secondary eligibility.** Secondary có sender identity verified, domain alignment, policy vùng, quota còn trống và feedback route không?

**Bước 5 — Tạm điều chỉnh throughput.** Hạn chế bulk traffic nếu cần dành capacity cho security email; không vượt rate limit của B.

**Bước 6 — Tách UNKNOWN.** Không redrive hàng loạt những attempt có timeout sau DATA hoặc lỗi commit `SENT`.

**Bước 7 — Xác nhận phục hồi.** Queue age giảm, SMTP accepted rate hồi phục, bounce/complaint không tăng bất thường; tiếp tục giám sát feedback tới muộn từ A.

### 18.2. Khi secondary không hợp lệ

Nếu B hết quota, chưa verified sender domain hoặc không đáp ứng residency:

~~~text
no eligible secondary
      |
      v
hold/retry while still within business deadline
      |
      v
alert owner with safe error code
      |
      v
operator fixes capacity/configuration
      |
      v
dispatch if still allowed
~~~

Đây có thể là kết quả **đúng** theo policy, dù SLO bị ảnh hưởng. Không khắc phục vấn đề bằng cách xóa kiểm tra region hoặc bypass suppression.

## 19. Tình huống vận hành: marketing chiếm quota transactional

Một ứng dụng có hai rule `MARKETING` và `TRANSACTIONAL`, nhưng cả hai đều map đến cùng SMTP account. Campaign lớn bắt đầu vào 08:00, provider áp quota theo account và các email giao dịch bị throttle.

~~~text
Marketing campaign 50,000 messages
            |
            v
Shared SMTP account quota
            |
            +--> bulk traffic uses capacity
            |
            +--> invoice/order mail receives temporary failures
~~~

Chỉ đổi class Java route không tự tạo capacity isolation. Cần xác định giới hạn thật của provider:

1. Có thể tách account/IP pool hoặc credential để độc lập quota không?
2. Nếu chung quota, có thể dùng rate limiter với **reserved tokens** cho security/transactional không?
3. Scheduler có kiểm tra priority và deadline trước khi claim bulk job không?
4. Marketing retry có làm traffic tăng đột biến không?
5. Có circuit/bulkhead riêng để error storm của marketing không giữ hết worker thread không?

Một chính sách thực tế có thể tạm dừng marketing trong lúc transactional backlog cao. Nhưng cần ghi log/metric rõ lý do `BULK_PAUSED_FOR_CAPACITY` và biết thời điểm tiếp tục campaign.

## 20. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tất cả email đều gửi qua provider mặc định | Service inject nhầm `@Primary` hoặc bỏ qua routing service | Dùng registry + policy; kiểm tra route trong attempt history |
| `NoUniqueBeanDefinitionException` khi inject `JavaMailSender` | Nhiều bean cùng kiểu không có `@Qualifier` | Inject rõ tên bean hoặc registry |
| `spring.mail.host` không tác động tới sender custom | Spring Boot auto-configuration back off hoặc bean không bind property | Bind `app.mail.providers`, cấu hình sender trong factory |
| Thread A gửi qua endpoint của thread B | Mutate `JavaMailSenderImpl`/Session properties dùng chung | Sender riêng theo endpoint/identity, tránh mutable per-request |
| Security email đi qua marketing pool | Category do request tự khai hoặc fallback global | Quy định category từ use case, validate candidate set |
| Email EU đi qua provider US | Resolve region sai hoặc health override policy | Fail-closed region/tenant constraint trước khi chọn health |
| Provider B từ chối From/domain | Domain/identity chưa verified | Cấu hình verified identities, SPF/DKIM/DMARC |
| SMTP auth thất bại chỉ trên một provider | Secret sai hoặc rotation chưa reload | Kiểm tra secret version, permission, TLS/AUTH |
| SMTP gửi thành công nhưng event không tới | Webhook/DSN route chưa cấu hình hoặc provider bị rollback | Giữ feedback ingestion, kiểm tra signature/MX/Return-Path |
| Email bị gửi trùng sau failover | Primary outcome UNKNOWN nhưng ứng dụng gửi B ngay | Lưu UNKNOWN, đối soát và retry có audit |
| Retry liên tục dù recipient đã bounce | Suppression chỉ có ở provider cũ | Central suppression theo recipient/tenant và policy |
| Mất một số người nhận trong batch | Gửi nhiều recipient chung delivery và xử lý partial failure sai | Tách delivery per-recipient, lưu trạng thái riêng |
| Routing policy thay đổi gây khó audit | Không lưu policy version/provider ID theo attempt | Bổ sung route decision history |
| Bulk gửi nhanh nhưng OTP chậm | Chung quota/worker pool | Reserved capacity, limiter theo category |
| Latency cao dù provider khỏe | Outbox backlog, DNS/TLS, attachment I/O | Đo queue wait, MIME build và SMTP duration riêng |
| Route rejected do file lớn | Secondary có message size limit thấp | Tính MIME overhead, chọn link tải nếu hợp lệ |
| Dashboard báo queue rỗng nhưng vẫn không gửi | Worker treo in-flight, producer không enqueue, collector stale | Theo dõi in-flight, last progress, metric freshness |
| Một region không có route | Cấu hình thiếu combination | Fail-closed và alert `NO_ELIGIBLE_ROUTE` |

### 20.1. Provider đang khỏe nhưng route bị chặn

Đây không nhất thiết là bug:

~~~text
Provider health: HEALTHY
Delivery category: SECURITY
Provider capability: MARKETING only
Result: REJECTED_BY_POLICY
~~~

Một provider hoạt động tốt ở tầng SMTP **không tự động đủ điều kiện** xử lý mọi loại email.

### 20.2. “Region mismatch” do nguồn dữ liệu mâu thuẫn

Ví dụ tenant có policy `EU_ONLY` nhưng user profile mới cập nhật địa chỉ sang VN. Đừng dùng vị trí mới để âm thầm bỏ nghĩa vụ xử lý dữ liệu của tenant. Hệ thống cần ưu tiên policy được phê duyệt và đưa trường hợp mâu thuẫn vào luồng xác minh dữ liệu hoặc quản trị.

### 20.3. Rotation credential trong hệ thống nhiều sender

Với một provider bị rotate password, đừng log nguyên `MultiProviderMailProperties` để kiểm tra cấu hình. Cần:

- Lưu secret version/reference không chứa giá trị bí mật.
- Tạo hoặc refresh sender theo vòng đời có kiểm soát.
- Thử xác thực bằng health/smoke test không tiết lộ password.
- Không làm gián đoạn attempt đang gửi nếu có thể tránh.
- Ngăn route mới tới sender cũ đã bị revoke.
- Tiếp tục nhận webhook/bounce của các email được gửi trước rotation.

Một bean đã nhận password lúc startup không tự động đổi chỉ vì file secret manager đã cập nhật. Nếu framework không có refresh an toàn, dùng rolling restart/replace registry theo chính sách.

## 21. Câu hỏi thường gặp

**“Spring Framework Mail tự chọn provider theo khu vực được không?”**  
Không tự động. `JavaMailSender` gửi qua transport đã cấu hình; application cần policy xác định region/category, chọn sender và ghi nhận route.

**“Có thể dùng nhiều JavaMailSender bean không?”**  
Có. Dùng `@Qualifier` khi inject hoặc dùng registry cấu hình các sender theo provider ID. Tránh một bean mutable dùng chung và đổi host/password ngay trước mỗi request.

**“Có nên dùng @Primary cho provider mặc định?”**  
Chỉ khi ứng dụng chủ ý có default và các service không ràng buộc được phép dùng nó. Trong hệ thống route theo region/tenant, một default implicit có thể khiến code mới gửi nhầm provider. Registry + explicit policy thường dễ kiểm soát hơn.

**“Có thể dùng spring.mail.host cho nhiều endpoint?”**  
`spring.mail.*` thường mô tả một auto-configured sender. Với nhiều endpoint, tạo cấu trúc `app.mail.providers` và bind vào registry, hoặc định nghĩa nhiều sender bean cụ thể.

**“Nên route theo domain .vn/.eu/.com của người nhận?”**  
Không. TLD không chứng minh vị trí của người nhận hay nghĩa vụ residency. Dùng dữ liệu region đã được xác thực theo tenant/account policy.

**“Email SECURITY khác TRANSACTIONAL thế nào?”**  
`SECURITY` thường cần thời gian xử lý ngắn và deadline chặt vì có token xác minh/cảnh báo. `TRANSACTIONAL` liên quan giao dịch/hoạt động tài khoản. Cả hai là danh mục nghiệp vụ cần định nghĩa nhất quán, không phải nhãn do người gọi chọn tùy ý.

**“Nếu provider của vùng EU bị lỗi, có thể gửi ngay qua US không?”**  
Chỉ khi chính sách dữ liệu, thỏa thuận và các điều kiện provider/identity đã cho phép route đó. Nếu có ràng buộc EU-only, cần fail-closed hoặc chờ provider EU, không chuyển vùng chỉ vì endpoint US khỏe.

**“Một SMTP provider phục vụ nhiều region được không?”**  
Có thể về mặt kỹ thuật, nhưng phải xem khả năng xử lý vùng thực tế, dữ liệu, quota, legal constraints và policy. Tên logical provider không đủ chứng minh location.

**“Có thể failover khi JavaMailSender ném MailSendException?”**  
Không phải mọi `MailSendException` đều an toàn để retry/failover. Cần xác định lỗi tại giai đoạn nào, SMTP đã accepted hay chưa và có khả năng duplicate không.

**“Nếu timeout sau DATA, có nên gửi provider B?”**  
Không nên tự động. Primary có thể đã nhận message; gửi B sẽ tạo bản trùng. Lưu outcome UNKNOWN, đối soát hoặc áp dụng chính sách retry chấp nhận rủi ro trùng có audit.

**“Có thể dùng Message-ID để bảo đảm exactly-once?”**  
Không. Message-ID là thông tin truy vết, không buộc SMTP server deduplicate. Nếu provider API hỗ trợ idempotency key, dùng theo hợp đồng của họ; SMTP thuần thường có cửa sổ trùng.

**“Failover và retry có khác nhau không?”**  
Có. Retry là thực hiện một attempt mới, có thể với cùng provider. Failover là chọn provider khác theo policy. Mỗi sự kiện nên được ghi riêng để phân tích hiệu quả và nguyên nhân.

**“Có nên random provider cho mỗi email?”**  
Có thể dùng weighted routing với tập eligible, nhưng cần stable assignment, capacity policy và audit. Random per-attempt khiến retry không dự đoán được và khó điều tra.

**“Marketing và security có cần domain riêng không?”**  
Không bắt buộc trong mọi sản phẩm, nhưng tách sending identity/traffic pool có thể hỗ trợ reputation và quota khi hạ tầng/provider hỗ trợ. Cần SPF/DKIM/DMARC và verified sender domain tương ứng.

**“Bật SPF cho provider A có đủ cho provider B?”**  
Không chắc. SPF/DKIM và domain verification phải phù hợp hạ tầng gửi của từng provider. Một identity đã verified ở A có thể chưa được phép gửi qua B.

**“Bounce khi dùng nhiều provider xử lý thế nào?”**  
Mỗi provider có webhook/DSN format và xác minh nguồn riêng. Normalize event, correlate theo provider ID + attempt/delivery/recipient, lưu lịch sử và áp dụng suppression ở tầng chung khi cần.

**“Nếu provider A báo deferred thì nên gửi bản mới qua B?”**  
Không tự động. Provider A có thể vẫn đang retry nội bộ. Chờ final outcome hoặc làm theo policy phối hợp với nhà cung cấp để tránh gửi trùng.

**“Sau khi đổi provider, webhook của provider cũ có còn cần không?”**  
Có, nếu những email trước đó có thể tạo event giao thư/bounce muộn. Không tắt ingestion ngay khi chuyển traffic mới sang provider khác.

**“Làm sao bảo đảm tenant A không dùng credential tenant B?”**  
Áp dụng authorization và tenant-scoped routing/identity mapping, không cho caller gửi provider ID tùy ý. Tách secret reference và audit theo tenant.

**“Provider khỏe mà quota hết có nên gửi không?”**  
Không ép gửi vượt quota. Có thể chọn secondary được phép/còn capacity hoặc schedule retry/backoff. Health và quota là hai điều kiện độc lập.

**“Có nên tăng thread pool khi provider throttling?”**  
Thường không giúp, có thể làm lỗi nhiều hơn. Cần rate limiter, backoff, bulkhead và điều chỉnh traffic theo quota thực tế.

**“Outbox SENT có nghĩa người nhận đã vào inbox?”**  
Không nếu `SENT` nghĩa SMTP accepted. Provider delivery feedback, bounce và spam filtering là lớp theo dõi khác.

**“Nên lưu route policy version ở đâu?”**  
Ít nhất lưu trên delivery hoặc từng attempt, cùng provider/identity/reason. Điều này giúp đối soát sau khi policy đã thay đổi.

**“Có cần giữ route cố định khi retry?”**  
Tùy policy. Pin route có lợi cho consistency; re-evaluate khi retry giúp phục hồi sau provider outage. Dù chọn cách nào, mỗi attempt cần ghi lại route thực tế và không được vượt ràng buộc region/identity.

**“Khi không có provider hợp lệ, có nên tạo message lỗi cho người nhận?”**  
Không nên mặc định gửi email khác khi chính hạ tầng mail đang lỗi. Ghi state/cause, cảnh báo operator và dùng kênh thay thế được nghiệp vụ cho phép nếu cần.

## 22. Checklist triển khai routing nhiều nhà cung cấp

### Thiết kế nghiệp vụ

1. Xác định các category (`SECURITY`, `TRANSACTIONAL`, `MARKETING` hoặc nhóm phù hợp sản phẩm).
2. Chuẩn hóa khu vực từ nguồn tin cậy, không suy region chỉ từ email TLD/IP.
3. Xác định policy theo category × region × tenant/sending identity.
4. Có quy tắc consent, unsubscribe, suppression và business deadline.
5. Quy định trường hợp thiếu route: hold, retry hay fail, không fallback im lặng.
6. Khi gửi nhiều recipient thuộc nhiều region, tạo delivery/route riêng cho từng recipient hoặc nhóm tương thích.

### Provider và danh tính gửi

7. Mỗi SMTP endpoint có cấu hình host/port/TLS/AUTH và secret runtime riêng.
8. Không sửa thuộc tính của singleton sender theo từng request.
9. Mỗi From/domain/Return-Path được verified ở provider được phép.
10. Kiểm tra SPF, DKIM, DMARC và bounce route.
11. Lưu metadata capability: category, region, message size, quota, identity support.
12. Kiểm tra quyền tenant sử dụng provider/sending identity.
13. Không đẩy secret vào log, database audit, Docker image hoặc CI report.

### Route decision và trạng thái

14. Route policy có version, audit và test bao phủ combinations.
15. Chọn provider trước khi tạo MIME và gửi bằng cùng `JavaMailSender`.
16. Lưu provider/identity/policy version trước SMTP attempt.
17. Tăng attempt count theo quy ước nhất quán, lưu claim token/lease khi concurrency.
18. Phân biệt `SMTP_ACCEPTED`, `RETRY`, `FAILED` và `UNKNOWN`.
19. Không xem `Message-ID` như một cơ chế exactly-once.
20. Outbox/broker retry cần backoff, jitter và max attempts/deadline.

### Failover và quota

21. Fallback chỉ chọn trong tập provider đã được policy phê duyệt.
22. Không failover khi outcome SMTP chưa rõ mà không xét duplicate risk.
23. Không bypass region, suppression hoặc sender identity để tăng delivery rate.
24. Có rate limit và capacity isolation cho critical/transactional/bulk traffic.
25. Có circuit breaker và kịch bản dừng gửi khi provider toàn vùng unavailable.
26. Route theo capability message size và giới hạn attachment.

### Feedback và vận hành

27. Nhận webhook/DSN của từng provider với xác minh nguồn riêng.
28. Correlate provider event theo attempt/delivery/recipient; deduplicate.
29. Giữ feedback ingestion của provider cũ sau rollout/rollback tới khi hoàn tất đối soát.
30. Central suppression áp dụng đúng phạm vi qua các provider.
31. Có metrics route decisions, rejected, failover, SMTP outcomes, latency, quota và queue age.
32. Alerts có thể hành động khi security mail quá deadline, no eligible route hoặc auth failures tăng.
33. Có runbook outage/secret rotation/identity mismatch và redrive được kiểm soát.

### Kiểm thử

34. Test ma trận route và các tổ hợp không được phép.
35. Test hai fake SMTP server để chứng minh VN/EU không hoán đổi endpoint.
36. Test gửi đồng thời không có race do thay sender properties.
37. Test partial SMTP failure, timeout sau DATA và state-update failure.
38. Test fallback chưa approved và fallback không đáp ứng region đều bị chặn.
39. Test gửi đúng From/Reply-To, MIME/attachment và kích thước giới hạn.
40. Test webhook trùng, phản hồi đến muộn, bounce/complaint và suppression xuyên provider.
41. Test canary policy rollback có giữ lịch sử route.
42. Không dùng credential hoặc recipient production trong integration test.

## 23. Mô hình tổng kết

~~~text
                  Trusted business event
                            |
                            v
                    Recipient delivery
                     (one recipient)
                            |
                            v
                   Transactional outbox
                            |
                            v
               Validate consent / suppression
                            |
                            v
                 Resolve category + region
                            |
                            v
                Versioned routing policy
                            |
                            v
           Provider candidates permitted by policy
                            |
            +---------------+----------------+
            |                                |
            v                                v
     Capability and identity          Health / rate limit
     TLS, domain, region, size         quota, circuit state
            |                                |
            +---------------+----------------+
                            |
                            v
              Select and persist route attempt
                            |
                 +----------+-----------+
                 |                      |
                 v                      v
           Primary SMTP            Approved secondary
                 |                      |
                 +----------+-----------+
                            |
                            v
                  JavaMailSender.send
                            |
            +---------------+----------------+
            |               |                |
            v               v                v
       Accepted         Safe failure       Unknown
            |               |                |
            v               v                v
          SENT           RETRY/FAILED     Reconciliation
            |               |                |
            +---------------+----------------+
                            |
                            v
                    Attempt history / audit
                            |
                            v
                   Metrics / alert / runbook
                            |
                            v
           Provider webhook / DSN processing
                            |
                            v
              Delivery feedback + suppression
~~~

Mô hình cho thấy **routing** không đứng riêng một lớp if/else. Nó gắn với nguồn dữ liệu nghiệp vụ, sender identity, provider capability, quota, retry, event feedback và data policy.

### Những điểm cần ghi nhớ

- **Loại email và khu vực là hai chiều độc lập**; một email marketing cho người nhận EU phải đồng thời đáp ứng quy tắc marketing và EU.
- **Không route theo dữ liệu không tin cậy** như provider ID từ request hay TLD của email.
- **Mỗi provider/identity dùng sender được cấu hình riêng**, không sửa host/credential của singleton trước từng send.
- **Failover chỉ trong tập được phép**, và chỉ khi biết đủ về kết quả SMTP để tránh resend nguy hiểm.
- **Submission không bằng inbox delivery**; cần DSN/webhook và đối soát đúng từng attempt.
- **Data residency là vấn đề end-to-end**, không chỉ tên hostname SMTP.
- **Audit policy version và provider ID** để truy lại quyết định sau khi cấu hình thay đổi.
- **Security/transactional traffic phải được bảo vệ khỏi bulk quota**, bằng route, capacity reservation và giới hạn phù hợp.

## Kết luận

**Định tuyến theo loại email hoặc khu vực** trong Spring Framework Mail là bài toán phối hợp chính sách nghiệp vụ với nhiều SMTP transport. Một triển khai có thể bắt đầu bằng nhiều `JavaMailSenderImpl` cấu hình riêng và một `MailRoutingPolicy` quyết định theo `MailCategory`, `DeliveryRegion` và danh tính đã xác thực. Khi quy mô tăng, cần thêm registry, capability filtering, quota, health, outbox, audit và pipeline phản hồi giao thư.

Giải pháp đáng tin cậy không chỉ chọn được một provider “đang chạy”. Nó phải chứng minh provider **được phép xử lý delivery cụ thể**, dùng đúng sender identity, không làm sai giới hạn khu vực, không gửi trùng mù quáng khi SMTP outcome mơ hồ và vẫn theo dõi được bounce/complaint sau chuyển provider. Khi các ranh giới này được thiết kế rõ, hệ thống có thể phân tách luồng bảo mật, giao dịch và marketing, vận hành đa vùng và phục hồi có kiểm soát mà không đánh đổi tính đúng đắn, bảo mật hoặc khả năng kiểm toán.
