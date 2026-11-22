# Cấu hình nhiều sender cho nhiều mục đích

## 1. Vì sao ứng dụng cần nhiều mail sender?

Một ứng dụng Spring có thể gửi nhiều loại email: xác minh tài khoản, đặt lại mật khẩu, xác nhận đơn hàng, hóa đơn, thông báo vận hành, bản tin hoặc chiến dịch tiếp thị. Những loại thư này thường khác nhau về mức độ khẩn cấp, nhà cung cấp, tài khoản SMTP, địa chỉ gửi, hạn mức, chính sách retry và yêu cầu theo dõi.

Nếu mọi email đều sử dụng một cấu hình SMTP, một đợt gửi thư số lượng lớn có thể tiêu thụ hạn mức hoặc hàng đợi của email giao dịch. Một vấn đề xác thực, giới hạn tốc độ hoặc uy tín gửi của một nhóm thư cũng có thể ảnh hưởng đến nhóm khác.

Trong **Spring Framework Mail**, mỗi **JavaMailSenderImpl** có thể giữ cấu hình SMTP riêng và được đăng ký thành một Spring bean. Các service phụ thuộc vào **JavaMailSender** theo tên/qualifier để sử dụng đúng tài khoản và đường gửi cho từng mục đích.

Ví dụ hai nhóm email phổ biến:

| Mục đích | Transactional sender | Campaign sender |
|---|---|---|
| Loại thư | OTP, đặt lại mật khẩu, đơn hàng, hóa đơn | Bản tin, ưu đãi, thông báo tiếp thị |
| Yêu cầu | Độ trễ thấp, hạn chế mất thông báo | Kiểm soát tốc độ, chính sách người đăng ký |
| Địa chỉ From ví dụ | account@example.com | news@example.com |
| SMTP host ví dụ | smtp-transactional.example.com | smtp-campaign.example.com |
| Retry | Thận trọng với token, hạn sử dụng, khả năng trùng | Tôn trọng giới hạn gửi, danh sách ngừng nhận |
| Giám sát | Trạng thái giao dịch, lỗi xác thực, bounce | Bounce, complaint, unsubscribe, chất lượng danh sách |

Hai hostname trên chỉ là địa chỉ minh họa. Một hệ thống thực tế có thể dùng hai tài khoản của cùng một nhà cung cấp, hai nhà cung cấp khác nhau, hoặc nhiều SMTP relay nội bộ. Tạo nhiều JavaMailSender không bắt buộc phải có nhiều máy chủ vật lý.

### Phân biệt nhiều sender với nhiều địa chỉ From

Đổi trường **From** trong một thông điệp không đồng nghĩa đổi SMTP server, tài khoản xác thực hoặc chính sách vận chuyển. Một sender có thể được phép sử dụng nhiều địa chỉ From đã xác minh, nhưng mọi thư vẫn đi qua cấu hình SMTP của sender ấy.

Ngược lại, hai bean JavaMailSender có thể dùng cùng một miền From nhưng khác tài khoản SMTP hoặc dịch vụ vận chuyển, nếu nhà cung cấp cho phép. **From là header email; sender là cấu hình và hành vi gửi thư ở phía ứng dụng.**

## 2. Kiến trúc nhiều sender trong Spring

~~~text
                  Nghiệp vụ ứng dụng
                          |
              +-----------+-----------+
              |                       |
     Account/Order Service      Newsletter Service
              |                       |
              v                       v
    TransactionalMailService   CampaignMailService
              |                       |
              | @Qualifier            | @Qualifier
              v                       v
    transactionalMailSender     campaignMailSender
              |                       |
              v                       v
       JavaMailSenderImpl        JavaMailSenderImpl
              |                       |
         SMTP account A           SMTP account B
              |                       |
              v                       v
           Relay A                 Relay B
              |                       |
              +-----------+-----------+
                          |
                   Máy chủ nhận thư
~~~

Spring Dependency Injection quản lý hai bean khác tên nhưng có thể cùng kiểu **JavaMailSender**. Các service xác định rõ sender sẽ sử dụng. Việc định tuyến theo **loại thông báo** hoặc **mục đích nghiệp vụ** nên được quyết định tại tầng điều phối, thay vì để từng controller tự tạo cấu hình SMTP.

Nếu hai sender dùng cùng một host, chúng vẫn có thể khác username, password, TLS, timeout, proxy/network route hoặc quota. Tuy nhiên, **hai bean trong cùng JVM không tự tạo sự cô lập hạ tầng tuyệt đối**: cùng kết nối ra một ESP thì vẫn có thể chia sẻ giới hạn tài khoản, IP, domain hoặc reputation theo chính sách nhà cung cấp.

## 3. Tổ chức cấu hình trong application.yml

Spring Boot hỗ trợ cấu hình một sender thông dụng qua namespace **spring.mail**. Khi ứng dụng cần nhiều sender được quản lý tường minh, có thể tạo namespace ứng dụng riêng, chẳng hạn **app.mail**:

~~~yaml
app:
  mail:
    transactional:
      host: smtp-transactional.example.com
      port: 587
      username: transactional@example.com
      password: ${TRANSACTIONAL_SMTP_PASSWORD}
      from: account@example.com
      starttls: true
      timeout-millis: 5000
    campaign:
      host: smtp-campaign.example.com
      port: 587
      username: campaign@example.com
      password: ${CAMPAIGN_SMTP_PASSWORD}
      from: news@example.com
      starttls: true
      timeout-millis: 10000
~~~

Trong ví dụ:

- Mỗi nhóm có **host/port**, tài khoản SMTP và địa chỉ **From** riêng.
- **starttls** biểu thị yêu cầu kết nối TLS cho mô hình submission trên cổng 587.
- **timeout-millis** là thời gian chờ dùng làm cấu hình cho socket/mail transport; đây là thuộc tính tùy chỉnh của ứng dụng.
- Giá trị password được nạp từ biến môi trường, không viết bí mật thật trong file commit.
- Namespace **app.mail** là tên do ứng dụng chọn, **không phải** thuộc tính mà Spring Boot tự hiểu để tạo hai JavaMailSender.

Với một SMTP server sử dụng implicit TLS trên cổng 465, cấu hình transport phải khác: dùng thuộc tính **mail.smtp.ssl.enable=true** và các thiết lập chứng chỉ tương ứng. Không mặc định lấy ví dụ STARTTLS cổng 587 áp dụng nguyên vẹn cho mọi dịch vụ.

### Tài khoản và From phải tương thích

Đặt **from: news@example.com** không bảo đảm tài khoản campaign được phép gửi từ địa chỉ này. Nhiều nhà cung cấp yêu cầu xác minh miền hoặc địa chỉ gửi, đồng thời cần SPF/DKIM/DMARC phù hợp. Các điều kiện này thuộc chính sách hệ thống mail và DNS, ngoài việc cấu hình bean Spring.

## 4. Ánh xạ cấu hình thành đối tượng typed properties

Trong Spring Boot 3 trên Java 21, một **record** có thể được dùng với **@ConfigurationProperties** để nhận cấu hình:

**MailAccounts.java**

~~~java
package com.example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAccounts(
        Account transactional,
        Account campaign
) {
    public record Account(
            String host,
            int port,
            String username,
            String password,
            String from,
            boolean starttls,
            int timeoutMillis
    ) {
    }
}
~~~

Record chứa thông tin của hai sender theo cấu trúc **transactional** và **campaign** trong YAML. Spring Boot hỗ trợ constructor binding cho record nếu lớp được đăng ký làm configuration properties, chẳng hạn bằng **@EnableConfigurationProperties(MailAccounts.class)**.

Các giá trị nhạy cảm như password tuy được inject vào object, vẫn phải bảo vệ qua hệ thống lưu secret, quyền truy cập cấu hình và logging. Không in toàn bộ record cấu hình ra log, vì **toString() của record** có thể chứa trường password.

Đối với production, nên bổ sung validation để phát hiện host rỗng, cổng sai, password thiếu hoặc timeout không hợp lệ ngay lúc khởi động. Có thể dùng **jakarta.validation** cùng cơ chế validation của Spring Boot nếu dự án cài dependency phù hợp. Ví dụ cơ bản bên dưới tập trung vào cách khai báo các sender.

## 5. Tạo hai bean JavaMailSender

Một lớp cấu hình tạo hai triển khai riêng của interface **JavaMailSender**. Cả hai dùng chung một factory nội bộ để tránh sao chép logic dựng transport.

**MailSenderConfiguration.java**

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailAccounts.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender(MailAccounts accounts) {
        return createSender(accounts.transactional());
    }

    @Bean("campaignMailSender")
    public JavaMailSender campaignMailSender(MailAccounts accounts) {
        return createSender(accounts.campaign());
    }

    private JavaMailSender createSender(MailAccounts.Account account) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(account.host());
        sender.setPort(account.port());
        sender.setUsername(account.username());
        sender.setPassword(account.password());
        sender.setDefaultEncoding(StandardCharsets.UTF_8.name());

        Properties properties = sender.getJavaMailProperties();
        properties.setProperty("mail.transport.protocol", "smtp");
        properties.setProperty("mail.smtp.auth", "true");
        properties.setProperty(
                "mail.smtp.starttls.enable",
                Boolean.toString(account.starttls())
        );
        properties.setProperty(
                "mail.smtp.starttls.required",
                Boolean.toString(account.starttls())
        );

        String timeout = Integer.toString(account.timeoutMillis());
        properties.setProperty("mail.smtp.connectiontimeout", timeout);
        properties.setProperty("mail.smtp.timeout", timeout);
        properties.setProperty("mail.smtp.writetimeout", timeout);

        return sender;
    }
}
~~~

**Giải thích các bước:**

1. **@EnableConfigurationProperties** đăng ký cấu hình MailAccounts để Spring Boot bind từ **app.mail**.
2. Hai phương thức **@Bean** tạo hai bean cùng kiểu JavaMailSender nhưng khác tên: **transactionalMailSender** và **campaignMailSender**.
3. Factory **createSender(...)** gắn hostname, port, username, password, charset và các JavaMail properties của từng account.
4. **mail.smtp.auth** bật cơ chế SMTP AUTH của Jakarta Mail; **mail.smtp.starttls.enable** và **mail.smtp.starttls.required** điều khiển yêu cầu STARTTLS.
5. Các timeout đặt giới hạn cho kết nối/đọc/ghi, tránh chờ vô thời hạn khi máy chủ có sự cố.

Ví dụ này mô tả SMTP submission cần AUTH và tùy chọn STARTTLS. Với dịch vụ không yêu cầu AUTH, dùng cơ chế xác thực khác hoặc cổng TLS khác, hãy cấu hình riêng thay vì giữ nguyên factory. Không dùng **starttls=false** để vô tình gửi password qua kết nối không được bảo vệ; lựa chọn TLS phải theo chính sách bảo mật của SMTP server.

### Chú ý về Spring Boot auto-configuration

**spring-boot-starter-mail** giúp đưa các dependency và cơ chế tự cấu hình phù hợp vào ứng dụng. Spring Boot có thể tự cung cấp một mail sender khi điều kiện cấu hình thỏa mãn và chưa có bean thích hợp do ứng dụng định nghĩa.

Khi đã tạo các bean gửi mail thủ công như trên, cơ chế tự cấu hình mail sender của Boot có thể **back off**, vì vậy không nên giả định **spring.mail.host**, **spring.mail.username** hay các thuộc tính **spring.mail.*** tự động được áp dụng cho cả hai bean. Các giá trị của ví dụ được đọc từ **app.mail** rồi truyền vào từng JavaMailSenderImpl một cách tường minh.

Trong ví dụ không dùng **@Primary**, để việc phụ thuộc vào JavaMailSender phải nêu rõ bean cần chọn. Nếu một thành phần chỉ inject JavaMailSender theo kiểu mà không có qualifier, Spring có thể báo **NoUniqueBeanDefinitionException** vì có nhiều bean phù hợp.

## 6. Chọn sender bằng @Qualifier

Vì có hai bean cùng kiểu, một service có thể yêu cầu rõ sender phù hợp với chức năng bằng **@Qualifier**.

### Service gửi email giao dịch

**TransactionalMailService.java**

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalMailService {

    private final JavaMailSender sender;
    private final String from;

    public TransactionalMailService(
            @Qualifier("transactionalMailSender") JavaMailSender sender,
            MailAccounts accounts
    ) {
        this.sender = sender;
        this.from = accounts.transactional().from();
    }

    public void sendOrderConfirmation(String recipient, String orderCode) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn hàng " + orderCode);
        message.setText("Đơn hàng " + orderCode + " đã được ghi nhận.");
        sender.send(message);
    }
}
~~~

**@Qualifier("transactionalMailSender")** buộc Spring inject đúng sender dành cho email giao dịch. Điều này hạn chế rủi ro dùng nhầm tài khoản campaign trong những chức năng quan trọng như xác nhận đơn hàng hoặc khôi phục tài khoản.

### Service gửi bản tin

**CampaignMailService.java**

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailService {

    private final JavaMailSender sender;
    private final String from;

    public CampaignMailService(
            @Qualifier("campaignMailSender") JavaMailSender sender,
            MailAccounts accounts
    ) {
        this.sender = sender;
        this.from = accounts.campaign().from();
    }

    public void sendNewsletter(String recipient, String articleUrl) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Bản tin mới");
        message.setText("Đọc bản tin tại " + articleUrl);
        sender.send(message);
    }
}
~~~

Ví dụ dùng plain text để tập trung vào cấu hình và lựa chọn sender. Khi email cần HTML, multipart hoặc attachment, service có thể gọi **sender.createMimeMessage()**, dùng **MimeMessageHelper** rồi **sender.send(mimeMessage)**. Lựa chọn sender dựa trên qualifier vẫn giữ nguyên.

Đối với campaign thật, dịch vụ gửi phải kiểm tra người nhận đã đồng ý, có nằm trong danh sách hủy đăng ký hay không, và tuân thủ hạn mức/chính sách liên quan. **JavaMailSender** chỉ xử lý giao diện gửi, không tự quản lý consent hoặc unsubscribe.

## 7. Định tuyến động theo mục đích gửi

Một ứng dụng nhỏ có thể để từng service inject cố định một sender. Nếu hệ thống có nhiều loại thông báo đi qua một điểm điều phối chung, có thể tạo **MailRouter** dựa trên mục đích được định nghĩa rõ ràng.

~~~java
package com.example.mail;

public enum MailPurpose {
    TRANSACTIONAL,
    CAMPAIGN
}
~~~

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class MailSenderRouter {

    private final JavaMailSender transactional;
    private final JavaMailSender campaign;

    public MailSenderRouter(
            @Qualifier("transactionalMailSender") JavaMailSender transactional,
            @Qualifier("campaignMailSender") JavaMailSender campaign
    ) {
        this.transactional = transactional;
        this.campaign = campaign;
    }

    public JavaMailSender select(MailPurpose purpose) {
        return switch (purpose) {
            case TRANSACTIONAL -> transactional;
            case CAMPAIGN -> campaign;
        };
    }
}
~~~

Ví dụ lớp điều phối có thể dùng **router.select(MailPurpose.TRANSACTIONAL)** để lấy sender tương ứng, rồi tạo message:

~~~java
JavaMailSender sender = router.select(MailPurpose.TRANSACTIONAL);
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("account@example.com");
message.setTo("customer@example.net");
message.setSubject("Xác nhận đơn hàng");
message.setText("Đơn hàng của bạn đã được ghi nhận.");
sender.send(message);
~~~

Đoạn mã dùng địa chỉ ví dụ để minh họa thao tác chọn sender. Trong thiết kế thực tế, nên gắn **From** với cấu hình của route, tránh để các caller tự truyền From tùy ý.

### Vì sao enum phù hợp hơn chuỗi tùy tiện?

Nếu một controller nhận trực tiếp chuỗi như **"smtpHost"** hoặc **"senderName"** từ HTTP request rồi chọn bean gửi, người dùng có thể vô tình hoặc cố ý chọn sai hạ tầng. Một **MailPurpose** là tập mục đích được ứng dụng kiểm soát, giúp giới hạn những lựa chọn hợp lệ và giữ logic nghiệp vụ rõ ràng.

Không cần dùng **ApplicationContext.getBean(...)** trong mỗi lần gửi. Constructor injection với các sender cụ thể giúp phụ thuộc được kiểm tra sớm và dễ thay thế trong kiểm thử.

## 8. @Primary và các lỗi inject thường gặp

Khi có nhiều bean cùng kiểu JavaMailSender:

~~~text
Bean type: JavaMailSender
  ├── transactionalMailSender
  └── campaignMailSender
~~~

Constructor sau có thể gây mơ hồ:

~~~java
public NotificationService(JavaMailSender mailSender) {
    this.mailSender = mailSender;
}
~~~

Nếu không có chỉ dẫn khác và Spring không xác định được bean duy nhất, ứng dụng có thể không khởi động do **NoUniqueBeanDefinitionException**.

Ba cách xử lý thường dùng:

| Cách | Khi nào phù hợp | Lưu ý |
|---|---|---|
| **@Qualifier** tại injection point | Mỗi service có mục đích gửi rõ ràng | Là lựa chọn dễ đọc và tường minh. |
| **@Primary** trên một bean | Phần lớn chỗ inject cần một sender mặc định | Cẩn thận với tác vụ gửi nhầm default. |
| **MailSenderRouter** | Một điểm điều phối quyết định sender theo loại sự kiện | Giữ quy tắc route tập trung và dễ mở rộng. |

Ví dụ dùng @Primary:

~~~java
@Bean("transactionalMailSender")
@Primary
JavaMailSender transactionalMailSender(MailAccounts accounts) {
    return createSender(accounts.transactional());
}
~~~

Với cách này, dependency chỉ khai báo JavaMailSender có thể nhận sender ưu tiên theo quy tắc lựa chọn bean của Spring. Tuy nhiên, **@Primary không thay thế việc định tuyến theo mục đích**. Trong ứng dụng có email giao dịch và campaign, dùng @Qualifier hoặc router thường rõ ràng hơn.

## 9. Nhiều tài khoản cùng một SMTP provider và nhiều provider

Kiến trúc nhiều sender không nhất thiết có nghĩa sử dụng hai thương hiệu dịch vụ email khác nhau.

**Trường hợp A — Cùng một SMTP host, khác tài khoản**

~~~yaml
app:
  mail:
    transactional:
      host: smtp.mail-provider.example
      username: account-transactional@example.com
      # ...
    campaign:
      host: smtp.mail-provider.example
      username: account-campaign@example.com
      # ...
~~~

Hình thức này có thể giúp phân quyền hoặc tách quota theo tài khoản, **nếu** nhà cung cấp hỗ trợ. Tuy nhiên, hạn mức IP, domain, pool gửi hoặc reputation vẫn có thể được chia sẻ.

**Trường hợp B — Hai SMTP provider khác nhau**

~~~text
Transactional -> Provider A -> Internet mail
Campaign      -> Provider B -> Internet mail
~~~

Cách này cho phép mỗi nhóm thư có chính sách vận hành riêng, nhưng cần quản lý hai bộ credential, DNS, cấu hình DKIM/SPF, chi phí, webhook và dashboard trạng thái. Các lỗi của từng provider cũng có thể khác nhau.

**Trường hợp C — Nhiều sender để dự phòng**

~~~text
Transactional sender
     |
     +--> Primary SMTP
     |
     +--> Secondary SMTP (khi có sự cố được phân loại)
~~~

Nếu muốn failover, không nên đơn giản bắt mọi exception rồi lập tức gửi qua provider phụ. Một số timeout xảy ra **sau khi provider chính đã nhận email** nhưng client chưa nhận phản hồi; gửi lại ở provider khác có thể gây trùng. Hệ thống cần ghi attempt, kết quả **UNKNOWN**, chính sách đối soát và quyết định failover có điều kiện.

## 10. Chính sách vận hành theo mục đích

Việc cấu hình nhiều sender có giá trị lớn hơn khi từng nhóm thư có chính sách riêng.

| Chính sách | Email giao dịch | Campaign / newsletter |
|---|---|---|
| **Tốc độ gửi** | Ưu tiên độ trễ thấp trong giới hạn an toàn | Rate limit và batch theo năng lực provider |
| **Retry** | Chỉ với lỗi phù hợp; chú ý token/hạn hiệu lực | Giới hạn retry, tôn trọng throttle và unsubscribe |
| **Queue** | Hàng đợi riêng cho thông báo thiết yếu | Hàng đợi riêng cho số lượng lớn |
| **Sender identity** | From có miền/địa chỉ xác minh cho giao dịch | From xác minh cho chương trình đăng ký |
| **Theo dõi** | Thư xác nhận, bounce, timeout, trạng thái chưa rõ | Delivery, bounce, complaint, unsubscribe |
| **Xử lý sự cố** | Cảnh báo sớm, cơ chế dự phòng có kiểm soát | Tạm dừng chiến dịch để bảo vệ quota và reputation |
| **Quyền dữ liệu** | Chỉ gửi thông tin đúng chủ tài khoản | Chỉ gửi tới người đã đồng ý và còn đăng ký |

### Sender không phải queue

**JavaMailSender.send(...)** thông thường hoạt động đồng bộ đối với caller. Hai bean JavaMailSender khác nhau **không tự tạo hai hàng đợi**, cơ chế ưu tiên, retry hay worker nền.

Nếu cần quản lý số lượng lớn, ứng dụng phải tự thiết kế hoặc tích hợp:

- Hàng đợi hoặc **transactional outbox** để giữ ý định gửi.
- Worker/pool phù hợp cho từng loại email.
- Giới hạn tốc độ và đồng thời theo tài khoản/nhà cung cấp.
- Retry với backoff có giới hạn, trạng thái tạm thời và vĩnh viễn.
- Theo dõi message ID, bounce/complaint và webhook nếu provider hỗ trợ.

Một thiết kế đơn giản:

~~~text
Business event
     |
     v
Notification dispatcher
     |
     +----------------------------+
     |                            |
 Transactional queue          Campaign queue
     |                            |
 Transactional worker         Campaign worker
     |                            |
 transactionalMailSender      campaignMailSender
     |                            |
 SMTP provider A              SMTP provider B
~~~

Queue bảo đảm các mục đích không nhất thiết tranh cùng một luồng xử lý, nhưng mức độ cô lập tài nguyên thực tế còn phụ thuộc vào worker, giới hạn kết nối, provider và cách triển khai hạ tầng.

## 11. Retry, failover và nguy cơ gửi trùng

Ví dụ một worker gọi sender giao dịch, SMTP server nhận được toàn bộ dữ liệu nhưng kết nối bị ngắt trước khi ứng dụng nhận phản hồi thành công:

~~~text
Spring app                         SMTP server
    | -------- message DATA -------> |
    |                                | Chấp nhận và xếp hàng
    | <----- ACK bị mất --------X    |
    |
    +-- Ứng dụng thấy timeout
        nhưng không biết server đã nhận email hay chưa.
~~~

Nếu router chuyển sang sender dự phòng ngay, email có thể được gửi **hai lần** qua hai provider. Đây là tính chất của giao tiếp phân tán, không riêng Spring.

Khi điều phối retry/failover:

1. Ghi **notification ID** cho ý định gửi và **attempt ID** cho từng lần thử.
2. Phân loại lỗi cấu hình/xác thực vĩnh viễn và lỗi mạng/throttle tạm thời.
3. Ghi trạng thái **UNKNOWN** nếu không thể chắc chắn server đã chấp nhận hay chưa.
4. Đối chiếu trạng thái với provider bằng message ID hoặc logs khi có thể.
5. Chỉ failover theo chính sách đã định; không hứa bảo đảm exactly-once chỉ nhờ thay SMTP server.

Một số ESP có API idempotency hoặc khả năng tra cứu request, nhưng **SMTP thuần và JavaMailSender** không cung cấp cùng một hợp đồng idempotency xuyên nhiều provider.

### Transactional outbox giải quyết điều gì?

Nếu email là hậu quả của một giao dịch database (ví dụ tạo đơn hàng), có thể lưu **đơn hàng + bản ghi outbox** trong cùng transaction rồi để worker gửi sau khi commit. Điều này tránh việc database đã commit nhưng ý định gửi bị mất do lỗi xảy ra giữa hai thao tác ứng dụng.

Tuy vậy, outbox không tự loại bỏ trùng lặp: worker có thể gửi email rồi dừng trước khi đánh dấu bản ghi đã xử lý. Cần quản lý trạng thái, attempt, retry và xác minh từ hạ tầng gửi.

## 12. Bảo mật cấu hình nhiều sender

Khi số lượng sender tăng, số credential và chính sách truy cập cũng tăng theo. Cần tránh đặt toàn bộ thông tin SMTP trong source code hoặc ghi vào log.

**Các lưu ý chính:**

- Nạp password/API token từ biến môi trường hoặc secret manager có phân quyền.
- Không log toàn bộ **MailAccounts**, vì record chứa password.
- Dùng TLS phù hợp với máy chủ, kiểm tra chứng chỉ và tránh vô tình hạ cấp kết nối.
- Tách quyền gửi của tài khoản giao dịch và tài khoản campaign theo hỗ trợ của provider.
- Chỉ cho phép những địa chỉ **From** hợp lệ với tài khoản/miền đã được xác minh.
- Xử lý luồng xác minh tài khoản, OTP và đặt lại mật khẩu bằng kênh giao dịch phù hợp; tránh đưa nội dung nhạy cảm vào campaign.
- Không ghi OTP, đường dẫn đặt lại mật khẩu, token hoặc dữ liệu riêng của người nhận trong log thông thường.
- Bảo vệ dashboard, webhook và bảng quản trị cấu hình SMTP; sự kiện delivery/bounce cũng có thể chứa dữ liệu người dùng.

### SPF, DKIM và DMARC với nhiều provider

Khi dùng nhiều hệ thống gửi cho cùng một miền, cần cấu hình và kiểm tra:

| Cơ chế | Nội dung cần lưu ý |
|---|---|
| **SPF** | Quyền gửi từ các nguồn IP/hệ thống phù hợp theo định danh SMTP; tránh cấu hình thiếu nguồn hoặc vượt giới hạn tra cứu SPF. |
| **DKIM** | Mỗi provider có thể yêu cầu bản ghi selector/khóa ký riêng và cấu hình ký hợp lệ. |
| **DMARC** | Đảm bảo cơ chế xác thực phù hợp và **alignment** với domain header From theo chính sách miền. |
| **Bounce/return-path** | Địa chỉ envelope sender có thể do từng provider quản lý; khác header From. |
| **Reputation** | Sender riêng không tự bảo đảm uy tín riêng nếu các nguồn chia sẻ IP/domain hoặc bị liên đới theo chính sách nhận. |

Đây là cấu hình email infrastructure và DNS. **spring-boot-starter-mail** không tự tạo toàn bộ những bản ghi này.

## 13. Trạng thái và giám sát theo từng sender

Nếu hai sender có mục đích khác nhau, metrics nên có nhãn mục đích **transactional/campaign** thay vì gom mọi email vào một biểu đồ tổng.

Các tín hiệu hữu ích gồm:

| Tín hiệu | Mục đích |
|---|---|
| **Số email được yêu cầu** | Đo nhu cầu gửi theo mục đích. |
| **Số lần SMTP được chấp nhận/từ chối** | Phân biệt phản hồi từ nhà cung cấp tại bước submission. |
| **Thời gian gọi send()** | Nhận biết vấn đề mạng hoặc SMTP chậm. |
| **Lỗi authentication** | Phát hiện credential bị thu hồi/hết hạn hoặc sai cấu hình. |
| **Kết nối timeout** | Phát hiện SMTP host/network gặp sự cố. |
| **Queue depth và age** | Phát hiện backlog ảnh hưởng tới thời gian gửi. |
| **Bounce, complaint, delivered event** | Theo dõi kết quả sau submission nếu ESP cung cấp. |
| **Retry và UNKNOWN attempts** | Đo rủi ro gửi trùng hoặc thất bại không rõ trạng thái. |

Log nên có **notification ID**, **attempt ID**, **sender name/purpose**, **thời điểm**, **mã lỗi** và thông tin chẩn đoán tối thiểu. Địa chỉ người nhận nên được giảm thiểu hoặc che một phần tùy chính sách bảo vệ dữ liệu. **Không log secret, token, MIME body hoặc attachment**.

Chỉ nhìn thấy **sender.send(...)** trả về không ném lỗi không chứng minh thư đã vào Inbox của người nhận. Khi cần trạng thái tiếp theo, dùng webhook hoặc log của ESP và hiểu chính xác ý nghĩa các sự kiện của từng provider.

## 14. Kiểm thử luồng chọn sender

Khi có nhiều bean cùng kiểu, hai lỗi dễ xảy ra là **inject nhầm bean** hoặc **routing sai mục đích**. Có thể kiểm chứng cách service dùng sender bằng một phép thử đơn giản sử dụng mock.

Ví dụ kiểm tra TransactionalMailService:

~~~java
package com.example.mail;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class TransactionalMailServiceTest {

    @Test
    void sendsOrderConfirmationViaConfiguredSender() {
        JavaMailSender sender = mock(JavaMailSender.class);
        MailAccounts accounts = new MailAccounts(
                new MailAccounts.Account(
                        "smtp-transactional.example.com",
                        587,
                        "txn-user",
                        "dummy-secret",
                        "account@example.com",
                        true,
                        5000
                ),
                new MailAccounts.Account(
                        "smtp-campaign.example.com",
                        587,
                        "campaign-user",
                        "dummy-secret",
                        "news@example.com",
                        true,
                        10000
                )
        );

        TransactionalMailService service =
                new TransactionalMailService(sender, accounts);
        service.sendOrderConfirmation("buyer@example.net", "ORD-123");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("account@example.com", sent.getFrom());
        assertEquals("Xác nhận đơn hàng ORD-123", sent.getSubject());
        assertEquals("buyer@example.net", sent.getTo()[0]);
    }
}
~~~

Ví dụ dùng JUnit 5 và Mockito, giả định dự án đã có dependencies kiểm thử phù hợp. Nó kiểm tra service tạo đúng nội dung và gọi sender được inject; **không kiểm tra SMTP thật**. Nếu cần kiểm tra Spring chọn bean đúng qualifier, có thể bổ sung integration test cho ApplicationContext với cấu hình MailSenderConfiguration. Khi muốn kiểm tra luồng SMTP, nên sử dụng mail server thử nghiệm hoặc sandbox của provider.

Một môi trường kiểm thử có thể cấu hình hai host SMTP giả lập độc lập để xác nhận email giao dịch và campaign đi đúng tuyến. Không gửi email thật cho khách hàng chỉ để xác minh cấu hình.

## 15. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Khởi động lỗi **NoUniqueBeanDefinitionException** | Có nhiều JavaMailSender nhưng inject theo kiểu chung | Sử dụng @Qualifier, hoặc @Primary khi chủ ý có default. |
| Cấu hình **app.mail** không tạo sender | Đây là namespace tùy chỉnh, Boot không tự sinh bean | Khai báo @ConfigurationProperties và @Bean rõ ràng. |
| Thuộc tính **spring.mail** không tác động đến hai bean | Các sender thủ công không tự dùng cấu hình Boot mặc định | Bind riêng và gán vào từng JavaMailSenderImpl. |
| Thư giao dịch được gửi bằng tài khoản campaign | Inject sai qualifier hoặc router định tuyến sai | Đưa lựa chọn sender vào service/router rõ mục đích. |
| SMTP trả authentication error | Sai credential, tài khoản thiếu quyền, sai cơ chế AUTH | Kiểm tra secret và chính sách account/provider. |
| STARTTLS/SSL handshake thất bại | Chọn sai cổng/chế độ TLS, chứng chỉ không hợp lệ | Kiểm tra yêu cầu TLS của server, SSL/STARTTLS và trust configuration. |
| Email gửi đi nhưng bị từ chối do From | Miền/địa chỉ From chưa xác minh hoặc không được account cho phép | Xác minh identity, DNS và policy của ESP. |
| Một đợt campaign làm chậm email giao dịch | Chia sẻ quota, queue, connection pool, IP hoặc giới hạn toàn cục | Tách worker/rate limit và tài nguyên provider khi cần. |
| Gửi trùng khi failover | Provider đầu có thể đã nhận thư trước timeout | Ghi attempt, trạng thái UNKNOWN, đối soát rồi mới retry. |
| Gửi thành công nhưng người nhận không thấy | Spam, quarantine, bounce muộn hoặc vấn đề mailbox | Tra log ESP, kiểm tra policy và folder ở phía nhận. |
| Cấu hình có password bị lộ trong log | Ghi toàn bộ object properties hoặc exception không lọc | Không in secret, giảm chi tiết log và kiểm soát truy cập. |

## 16. Khi nào không cần nhiều sender?

Không phải mọi ứng dụng đều cần cấu hình nhiều SMTP connection.

**Một sender có thể đủ** nếu ứng dụng chỉ gửi một nhóm thư, khối lượng thấp, cùng một địa chỉ/miền đã xác minh, cùng chính sách bảo mật và cùng hạn mức vận hành. Việc tự tạo thêm nhiều bean trong trường hợp đó chỉ làm tăng cấu hình và điểm có thể sai.

**Nhiều sender có ích** khi có mục đích rõ ràng: email giao dịch cần độ tin cậy và ưu tiên riêng, email campaign cần quota/rate limit riêng, các tenant được cấp quyền gửi qua những tài khoản SMTP khác nhau, hoặc có yêu cầu cô lập provider.

Nếu chỉ muốn thay đổi **From** theo thông điệp mà vẫn dùng cùng tài khoản SMTP được cấp quyền, có thể vẫn chỉ cần một JavaMailSender. Nếu nhiều tenant thay đổi linh hoạt ở quy mô lớn, không nhất thiết tạo một bean cố định cho mọi tenant; có thể thiết kế một **sender registry** được cấu hình, quản lý vòng đời và lựa chọn sender theo tenant có quyền truy cập. Cần kiểm soát cache, cấu hình bí mật, tài nguyên kết nối và trách nhiệm dữ liệu trong trường hợp đó.

## 17. Tổng kết

Spring Framework Mail cho phép cấu hình **nhiều JavaMailSenderImpl** dưới các bean tên riêng để phục vụ nhiều mục đích. Ứng dụng nên lưu cấu hình của mỗi SMTP account trong namespace có cấu trúc, bind bằng **@ConfigurationProperties**, tạo bean bằng **@Bean**, rồi chọn đúng bean qua **@Qualifier** hoặc router dựa trên loại thông báo.

Điều quan trọng không chỉ là tạo hai kết nối SMTP: hệ thống cần gắn mỗi sender với **đúng loại email, địa chỉ From được phép dùng, chính sách bảo mật, hạn mức, retry và giám sát**. Hai bean chỉ giúp phân định đường gửi ở phía Spring; hàng đợi, failover, khả năng giao thư và theo dõi kết quả cuối vẫn phải được thiết kế ở các lớp phù hợp.
