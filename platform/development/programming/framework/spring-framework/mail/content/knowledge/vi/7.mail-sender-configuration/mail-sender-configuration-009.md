# Sender cho email giao dịch và email marketing

Một ứng dụng Spring có thể gửi nhiều loại email: thư xác minh tài khoản, đặt lại mật khẩu, xác nhận đơn hàng, thông báo thanh toán, bản tin sản phẩm và chiến dịch khuyến mãi. Tất cả đều có thể được chuyển qua SMTP, nhưng **email giao dịch (transactional email)** và **email marketing** có mục tiêu, yêu cầu vận hành và chính sách nhận thư khác nhau. Vì vậy, cấu hình sender cần thể hiện rõ sự khác biệt giữa hai luồng.

Trong **Spring Framework Mail**, `JavaMailSender` là giao diện gửi thư. Chúng ta có thể dùng một sender cho bài toán đơn giản, hoặc khai báo **hai sender riêng** khi cần tài khoản SMTP, địa chỉ gửi, giới hạn tốc độ hay hạ tầng chuyển phát khác nhau. Việc tách sender ở mã nguồn giúp điều phối đúng kênh, nhưng để thực sự cách ly uy tín gửi và hạn mức cần cấu hình tương ứng ở nhà cung cấp email.

Bài học hướng dẫn lựa chọn kiến trúc, cấu hình nhiều bean `JavaMailSender`, sử dụng `@Qualifier` để định tuyến thư, thiết kế header người gửi và hủy đăng ký, đồng thời xử lý lỗi, hàng đợi, quota và theo dõi khả năng chuyển phát.

## 1. Email giao dịch và email marketing khác nhau ở đâu?

### 1.1. Email giao dịch

Email giao dịch được phát sinh từ **hành động hoặc trạng thái nghiệp vụ cụ thể** mà người dùng có liên quan. Ví dụ:

- Xác minh địa chỉ email khi đăng ký tài khoản.
- Gửi liên kết đặt lại mật khẩu.
- Xác nhận đơn hàng hoặc thanh toán.
- Gửi hóa đơn, biên nhận và thông báo thay đổi lịch hẹn.
- Thông báo trạng thái yêu cầu hỗ trợ hoặc sự kiện bảo mật tài khoản.

Đặc điểm thường gặp:

- Cần đến **đúng người**, trong thời gian ngắn và với nội dung chính xác.
- Khối lượng thường gắn với hoạt động của ứng dụng, có thể tăng đột biến.
- Gửi thất bại có thể ảnh hưởng trực tiếp tới chức năng như đăng nhập hoặc thanh toán.
- Cần truy vết theo user, sự kiện nghiệp vụ hoặc outbox ID và có chiến lược retry.
- Nội dung nên giới hạn vào mục đích giao dịch; không nên lồng quảng cáo không cần thiết vào thư bảo mật quan trọng.

Ví dụ subject: `Xác nhận đơn hàng #ORD-2081`.

### 1.2. Email marketing

Email marketing phục vụ hoạt động **giao tiếp, giới thiệu sản phẩm hoặc chiến dịch**. Ví dụ:

- Bản tin hằng tuần, cập nhật sản phẩm.
- Thông báo ưu đãi, chương trình khuyến mãi.
- Chiến dịch tái tương tác với nhóm người dùng đã đăng ký.
- Nội dung giới thiệu tính năng mới hoặc sự kiện tiếp thị.

Đặc điểm thường gặp:

- Người nhận được chọn từ **danh sách đăng ký và phân nhóm**.
- Có thể gửi theo lịch hoặc thành từng đợt lớn.
- Cần quản lý đồng ý nhận thư, hủy đăng ký, suppression list, bounce và complaint.
- Quan tâm đến tốc độ gửi, uy tín tên miền, khả năng vào Inbox và báo cáo chiến dịch.
- Có thể yêu cầu nền tảng marketing chuyên dụng khi cần automation, phân khúc và quản lý nội dung phức tạp.

Ví dụ subject: `Bản tin tháng 11: Các tính năng mới`.

### 1.3. Bảng đối chiếu để thiết kế sender

| Tiêu chí | Email giao dịch | Email marketing |
|---|---|---|
| Yếu tố kích hoạt | Sự kiện nghiệp vụ cụ thể. | Chiến dịch, lịch định kỳ hoặc phân khúc người nhận. |
| Ưu tiên | Độ trễ thấp, chính xác, có thể truy vết. | Quản lý tốc độ, danh sách, hiệu quả chiến dịch. |
| Đối tượng | Người dùng liên quan trực tiếp tới sự kiện. | Người dùng đủ điều kiện nhận nội dung marketing. |
| Kiểm soát gửi | Idempotency của yêu cầu nghiệp vụ, outbox, retry. | Consent, unsubscribe, suppression, quota, lịch gửi. |
| Địa chỉ gửi điển hình | `receipts@example.com`, `security@example.com`. | `news@example.com`, `offers@example.com`. |
| Reply-To | Hỗ trợ khách hàng hoặc kênh liên hệ giao dịch. | Kênh phản hồi chiến dịch hoặc hộp thư được theo dõi. |
| Theo dõi | Trạng thái tiếp nhận, delivery, bounce, lỗi gửi. | Delivery, bounce, complaint, unsubscribe và chỉ số chiến dịch. |
| Hậu quả khi nghẽn | Có thể cản trở trải nghiệm nghiệp vụ quan trọng. | Chiến dịch đến chậm hoặc giảm hiệu quả. |

**Không phải bất kỳ email nào được tự động hóa cũng là giao dịch.** Một bản tin gửi theo sự kiện “người dùng vừa xem sản phẩm” vẫn có thể là marketing. Hãy phân loại theo **mục đích nội dung và cơ sở người nhận được gửi**, không chỉ theo việc nó được sinh tự động hay thủ công.

## 2. Sender có những lớp cấu hình nào?

Từ “sender” trong dự án Spring thường bao hàm nhiều thành phần. Cần phân biệt để tránh giả định sai:

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| **Bean gửi trong Spring** | `JavaMailSender` | Tạo/gửi `MimeMessage` qua cấu hình transport. |
| **Tài khoản/hệ thống SMTP** | Host, port, username, password, TLS | Xác thực và tiếp nhận yêu cầu gửi thư. |
| **Danh tính trong header** | `From:`, `Reply-To:` | Cho người nhận biết ai gửi và trả lời về đâu. |
| **Phong bì SMTP** | `MAIL FROM` / envelope sender | Thường phục vụ routing và xử lý bounce; có thể khác header `From:`. |
| **Tên miền và xác thực** | SPF, DKIM, DMARC | Chứng minh quyền gửi, hỗ trợ danh tính và chính sách nhận thư. |
| **Chính sách phân phối** | Rate limit, queue, suppression | Điều tiết khối lượng và người nhận hợp lệ. |
| **Dịch vụ nhận/tracking** | Webhook, event, dashboard | Phản ánh giao hàng, bounce hoặc complaint sau khi tiếp nhận. |

Tạo hai bean `JavaMailSender` không tự động tạo hai tên miền uy tín, hai IP hay hai nhóm quota. Đó là tài nguyên do nhà cung cấp hoặc mail server kiểm soát. Ngược lại, nếu chỉ khác header `From:` nhưng cùng tài khoản SMTP và chung giới hạn tốc độ, chiến dịch marketing vẫn có thể ảnh hưởng đến thư giao dịch.

## 3. Ba phương án tổ chức sender

### Phương án A — Một JavaMailSender, nhiều loại nội dung

Ứng dụng dùng một tài khoản SMTP và một bean `JavaMailSender`, nhưng mỗi email có thể đặt `From`/`Reply-To` khác nhau **nếu nhà cung cấp cho phép các địa chỉ đó**.

```text
OrderService -------\
                     +--> JavaMailSender --> Một SMTP account/relay
CampaignService ----/
```

Phù hợp khi:

- Ứng dụng nhỏ, lượng thư không lớn.
- Cả hai luồng có chính sách hạ tầng và hạn mức tương tự.
- Nhà cung cấp cho phép các danh tính gửi mong muốn.
- Ứng dụng vẫn kiểm tra consent với marketing và không để chiến dịch chiếm hết năng lực gửi.

Nhược điểm: khó cách ly quota, kết nối, failure và uy tín gửi khi một chiến dịch tạo tải lớn. Chỉ đổi `From` không mang lại sự cách ly hạ tầng.

### Phương án B — Hai JavaMailSender với tài khoản hoặc cấu hình riêng

Ứng dụng tạo một sender cho transaction và một sender cho marketing:

```text
                   +--> transactionalMailSender
OrderService ------|         |
                   |         +--> SMTP transaction account / relay

                   +--> marketingMailSender
CampaignWorker ----|         |
                             +--> SMTP marketing account / relay
```

Phù hợp khi:

- Cần credential, SMTP host hoặc quota khác nhau.
- Cần chính sách retry, tốc độ và ưu tiên khác nhau.
- Muốn tránh chiến dịch marketing gây chậm email giao dịch.
- Muốn thay đổi nhà cung cấp từng luồng mà không ảnh hưởng phần còn lại.

Hai sender có thể dùng **hai host khác nhau**, hoặc cùng host nhưng khác username, subaccount, cấu hình domain hay pool được nhà cung cấp phân tách.

### Phương án C — Transactional qua Spring Mail, marketing qua dịch vụ chuyên biệt

```text
Order / Security
      |
      +--> JavaMailSender --> SMTP giao dịch

Campaign / Newsletter
      |
      +--> Provider SDK / HTTP API / marketing platform
                                  |
                                  +--> campaign, consent,
                                       suppression, analytics
```

Phù hợp khi marketing cần phân khúc, A/B test, lịch chiến dịch, báo cáo, unsubscribe tự động hoặc sự kiện delivery/bounce mà SMTP đơn thuần không cung cấp thuận tiện.

Tầng nghiệp vụ có thể phụ thuộc vào một interface như `TransactionalEmailGateway` và `MarketingEmailGateway`; mỗi implementation có thể gọi `JavaMailSender` hoặc API riêng. Việc lựa chọn công nghệ truyền tải không buộc phải thay đổi định nghĩa email giao dịch/marketing.

## 4. Thiết kế danh tính gửi: From, Reply-To và envelope sender

Giả sử ứng dụng có hai dòng thư:

| Thuộc tính | Transactional | Marketing |
|---|---|---|
| `From:` | `receipts@example.com` | `news@example.com` |
| Tên hiển thị | `Example Receipts` | `Example Newsletter` |
| `Reply-To:` | `support@example.com` | `campaigns@example.com` |
| Envelope sender | Địa chỉ/miền trả bounce do SMTP provider cấu hình cho luồng giao dịch | Địa chỉ/miền trả bounce của luồng marketing |
| Kênh quản lý | Sự kiện đơn hàng, tài khoản, bảo mật | Consent, danh sách, chiến dịch |

### 4.1. From là danh tính người gửi hiển thị

Ví dụ:

```text
From: "Example Receipts" <receipts@example.com>
Reply-To: support@example.com
```

`From` nói cho mail client biết ai là tác giả/người gửi hiển thị của thông điệp. Địa chỉ `From` phải thuộc danh tính/tên miền mà tài khoản hoặc dịch vụ SMTP **được phép gửi**. Không được tự ý giả mạo địa chỉ người khác chỉ bằng cách đặt header.

Trong Spring:

```java
helper.setFrom("receipts@example.com");
helper.setReplyTo("support@example.com");
```

Tên hiển thị Unicode có thể được đặt qua `MimeMessageHelper.setFrom(String, String)` và sẽ được mã hóa theo khả năng MIME của thư viện. Nếu cần sử dụng overload này, code phải xử lý cả `MessagingException` và `UnsupportedEncodingException` theo chữ ký API tương ứng.

### 4.2. Reply-To quyết định hướng phản hồi

`Reply-To` có thể khác `From`. Ví dụ sender marketing dùng `news@example.com` nhưng phản hồi cần đến hộp thư hỗ trợ chiến dịch. Không chọn một địa chỉ “no-reply” rồi khiến người dùng không có cách liên hệ nếu nghiệp vụ cần tiếp nhận phản hồi.

Trong email marketing, địa chỉ Reply-To nên được giám sát hoặc có quy trình xử lý. Hệ thống vẫn cần cơ chế hủy đăng ký độc lập; yêu cầu người dùng phải trả lời bằng tay để unsubscribe thường không phù hợp với trải nghiệm và chính sách gửi hàng loạt hiện đại.

### 4.3. Envelope sender và Return-Path

Ở SMTP, client khai báo:

```text
MAIL FROM:<bounces@bounce.example.com>
RCPT TO:<alice@example.net>
```

Địa chỉ `MAIL FROM` còn gọi là **envelope sender/reverse-path**, chủ yếu liên quan đến phản hồi lỗi chuyển phát. Nó **không nhất thiết trùng** header `From:` trong nội dung.

Thông thường máy chủ nhận sẽ tạo header `Return-Path` dựa trên đường chuyển thư; đừng giả định tự đặt `Return-Path` trên `MimeMessage` là cách hợp lệ để điều khiển địa chỉ bounce.

Với Jakarta Mail SMTP provider, property `mail.smtp.from` có thể được dùng để điều khiển envelope sender ở mức Transport. Tuy nhiên, các dịch vụ SMTP do nhà cung cấp quản lý có thể áp đặt hoặc ghi đè giá trị theo chính sách xác minh domain/return-path riêng.

Khi tách transaction và marketing, nên cân nhắc **bounce identity** riêng do nhà cung cấp hỗ trợ. Điều này giúp phân tích trạng thái từng luồng và quản lý uy tín gửi, nhưng phải cấu hình DNS, chính sách sender và xác thực phù hợp.

### 4.4. SPF, DKIM, DMARC và alignment

Chỉ có bean sender đúng chưa đủ để email được tin cậy:

- **SPF** công bố máy chủ/hạ tầng nào được phép gửi cho domain dùng trong cơ chế kiểm tra SPF, thường liên quan envelope sender.
- **DKIM** ký điện tử những phần được chọn của thông điệp bằng khóa gắn với domain ký để hệ thống nhận kiểm tra tính toàn vẹn và nguồn được khai báo.
- **DMARC** đặt chính sách đánh giá và xử lý dựa trên kết quả SPF/DKIM có **alignment** với domain của header `From:`.

Alignment không yêu cầu mọi chuỗi địa chỉ giống hệt nhau; nó tuân theo quy tắc domain và chế độ chính sách DMARC. Cần xác thực domain hoặc subdomain ở nhà cung cấp, kiểm tra các bản ghi DNS và đối chiếu kết quả thực tế.

Nếu transaction và marketing dùng các subdomain khác nhau, ví dụ `tx.example.com` và `news.example.com`, hãy cân nhắc quản lý DNS, DKIM và SPF phù hợp cho từng dòng thư. Việc tách subdomain **có thể** giúp phân loại luồng và vận hành danh tiếng, nhưng mức cách ly thực tế vẫn phụ thuộc hạ tầng/IP/pool và cách hệ thống nhận đánh giá.

## 5. Cấu hình hai JavaMailSender trong Spring Boot

Phần này minh họa **hai bean sender độc lập** trong Spring Boot 3.x, Spring Framework 6.x, Java 17 trở lên, dùng Jakarta Mail.

### 5.1. Thêm dependency

Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Starter cung cấp các thành phần Spring Mail và Jakarta Mail cần thiết cho trường hợp SMTP thông dụng.

### 5.2. Khai báo hai kênh trong application.yml

Thay vì dùng một nhóm thuộc tính `spring.mail.*` tự cấu hình mặc định, ví dụ này dùng namespace riêng `app.mail.*` để tự tạo **hai** `JavaMailSenderImpl`:

```yaml
app:
  mail:
    transactional:
      host: ${TX_SMTP_HOST}
      port: ${TX_SMTP_PORT:587}
      username: ${TX_SMTP_USERNAME}
      password: ${TX_SMTP_PASSWORD}
      from: receipts@example.com
      reply-to: support@example.com

    marketing:
      host: ${MKT_SMTP_HOST}
      port: ${MKT_SMTP_PORT:587}
      username: ${MKT_SMTP_USERNAME}
      password: ${MKT_SMTP_PASSWORD}
      from: news@example.com
      reply-to: campaigns@example.com
```

Các biến môi trường chứa credential phải được cấp qua nền tảng triển khai hoặc secret store. Dùng địa chỉ gửi đã được nhà cung cấp xác minh; các địa chỉ tên miền `example.com` chỉ là ví dụ.

### 5.3. Binding cấu hình bằng ConfigurationProperties

Tạo lớp record để Spring Boot bind dữ liệu cấu hình. Nếu codebase không dùng Java records, có thể thay bằng class với getters/setters phù hợp:

```java
package com.example.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailChannelsProperties(
    Channel transactional,
    Channel marketing
) {
    public record Channel(
        String host,
        int port,
        String username,
        String password,
        String from,
        String replyTo
    ) {}
}
```

Spring Boot hỗ trợ bind kebab-case `reply-to` vào trường `replyTo`. Cấu trúc record phù hợp khi hai luồng có cùng nhóm trường cấu hình.

### 5.4. Tạo hai bean sender theo từng channel

```java
package com.example.mail;

import java.util.Properties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailChannelsProperties.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender(MailChannelsProperties config) {
        return createSender(config.transactional());
    }

    @Bean("marketingMailSender")
    public JavaMailSender marketingMailSender(MailChannelsProperties config) {
        return createSender(config.marketing());
    }

    private JavaMailSender createSender(
            MailChannelsProperties.Channel channel) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(channel.host());
        sender.setPort(channel.port());
        sender.setUsername(channel.username());
        sender.setPassword(channel.password());
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.transport.protocol", "smtp");
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

Ý nghĩa từng phần:

1. `@EnableConfigurationProperties` đăng ký đối tượng `MailChannelsProperties` để Spring bind `app.mail.*`.
2. Mỗi `@Bean` gọi `createSender(...)` với một channel riêng, nên hai bean có host, port và credential độc lập.
3. `@Bean("transactionalMailSender")` và `@Bean("marketingMailSender")` tạo tên rõ ràng để inject đúng mục đích.
4. `mail.smtp.starttls.required=true` buộc nâng cấp TLS thành công nếu sử dụng cấu hình STARTTLS; thất bại thì không gửi trong chế độ kết nối kém an toàn hơn.
5. Timeout giúp tránh chờ vô hạn khi máy chủ SMTP chậm hoặc không phản hồi.

Đây là ví dụ cho các nhà cung cấp sử dụng **SMTP submission cổng 587 với STARTTLS và AUTH**. Nếu một channel dùng cổng 465 và implicit TLS, cần cấu hình `mail.smtp.ssl.enable=true` cùng cổng/cơ chế thích hợp. Nếu relay nội bộ không dùng SMTP AUTH, có thể cấu hình riêng theo tài liệu của relay thay vì áp dụng một bộ properties cho mọi môi trường.

Khi đã khai báo nhiều bean `JavaMailSender`, code injection **theo type đơn thuần** sẽ không biết chọn bean nào. Sử dụng `@Qualifier` hoặc một lớp adapter nghiệp vụ định tuyến rõ ràng; không dựa vào thứ tự khai báo bean.

### 5.5. Dùng @Qualifier để gửi đúng luồng

Service dưới đây nhận hai sender tách biệt và lấy địa chỉ From/Reply-To từ cấu hình đã bind:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ApplicationMailService {

    private final JavaMailSender transactionalSender;
    private final JavaMailSender marketingSender;
    private final MailChannelsProperties channels;

    public ApplicationMailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,
            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,
            MailChannelsProperties channels) {
        this.transactionalSender = transactionalSender;
        this.marketingSender = marketingSender;
        this.channels = channels;
    }

    public void sendOrderConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = transactionalSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, "UTF-8");

        helper.setFrom(channels.transactional().from());
        helper.setReplyTo(channels.transactional().replyTo());
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText(
            "Đơn hàng " + orderCode + " của bạn đã được ghi nhận."
        );

        transactionalSender.send(message);
    }

    public void sendNewsletter(
            String recipient,
            String htmlBody,
            String plainTextBody) throws MessagingException {
        // Lớp gọi phải kiểm tra consent và suppression trước khi gửi.
        MimeMessage message = marketingSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(channels.marketing().from());
        helper.setReplyTo(channels.marketing().replyTo());
        helper.setTo(recipient);
        helper.setSubject("Bản tin sản phẩm");
        helper.setText(plainTextBody, htmlBody);

        // Ví dụ cơ bản; chiến dịch thực tế cần header unsubscribe
        // hợp lệ và endpoint hoạt động, được trình bày bên dưới.
        marketingSender.send(message);
    }
}
```

Trong ví dụ:

- Thư xác nhận đơn hàng đi qua `transactionalSender`.
- Bản tin đi qua `marketingSender`.
- Mỗi email có `From` và `Reply-To` tương ứng với channel.
- `MimeMessageHelper.setText(plain, html)` giúp gửi cả văn bản thuần và HTML.
- Không có vòng lặp gửi hàng loạt trong request: chiến dịch nên do worker hoặc hệ thống campaign xử lý cùng các bước kiểm tra điều kiện nhận thư.

**Quan trọng:** `sendNewsletter(...)` minh họa định tuyến sender, chưa phải một hệ thống gửi marketing hoàn chỉnh. Trước khi sử dụng, cần triển khai đầy đủ kiểm soát consent, unsubscribe, suppression, địa chỉ gửi và chính sách tốc độ.

### 5.6. Phân biệt @Primary và @Qualifier

Khi có hai bean cùng interface `JavaMailSender`, nếu một service dùng:

```java
public AlertService(JavaMailSender sender) {
    this.sender = sender;
}
```

Spring có thể báo lỗi thiếu lựa chọn duy nhất (nếu không có cơ chế phân giải bean phù hợp). Dùng:

```java
public AlertService(
        @Qualifier("transactionalMailSender") JavaMailSender sender) {
    this.sender = sender;
}
```

Với ứng dụng hiện có nhiều service cũ chỉ dùng một sender, có thể cân nhắc `@Primary` để đặt mặc định **nếu ý nghĩa mặc định đã được xác định rõ**. Tuy vậy, ở những thao tác phân biệt transaction và marketing, `@Qualifier` làm cho lựa chọn kênh dễ nhận ra hơn khi đọc code.

## 6. Tách sender bằng interface nghiệp vụ

Khi hệ thống lớn dần, có thể tách:

```java
public interface TransactionalEmailGateway {
    void sendReceipt(String recipient, String orderCode);
}

public interface MarketingEmailGateway {
    void sendCampaignMessage(String recipient, String campaignId);
}
```

Implementation đầu tiên có thể gọi `transactionalMailSender`; implementation thứ hai gọi `marketingMailSender` hoặc SDK của dịch vụ campaign.

Ưu điểm:

- Service đơn hàng không thể vô tình dùng sender marketing chỉ vì cùng interface `JavaMailSender`.
- Có thể gắn queue, retry, logging và metrics riêng cho từng nghiệp vụ.
- Dễ chuyển nhà cung cấp cho một luồng mà không sửa các service gọi.
- Code nghiệp vụ nhận đầu vào theo mục đích (`orderCode`, `campaignId`) thay vì phải tự lắp tất cả SMTP header.

Với ứng dụng nhỏ, việc inject hai sender bằng `@Qualifier` có thể đã đủ; không cần thêm abstraction nếu chưa có nhu cầu cụ thể.

## 7. Yêu cầu riêng khi cấu hình sender marketing

### 7.1. Consent: ai được phép nhận?

Trước khi gửi marketing, ứng dụng cần biết người dùng đã đồng ý nhận đúng loại nội dung chưa và yêu cầu đồng ý đó còn hiệu lực hay không. Các thông tin thường cần quản lý gồm:

- Địa chỉ email và người dùng liên quan.
- Loại email được chọn nhận (newsletter, ưu đãi, thông báo sản phẩm).
- Thời điểm/nguồn đăng ký và bằng chứng đồng ý khi cần.
- Thời điểm hủy đăng ký và phạm vi hủy.
- Trạng thái bounce/complaint và suppression áp dụng.

Không nên cho rằng một người từng mua hàng đồng nghĩa đã đăng ký nhận mọi chiến dịch. Ngược lại, việc người dùng hủy đăng ký marketing **thường không phải lý do để ngừng mọi email giao dịch cần thiết**; chính sách gửi còn phụ thuộc yêu cầu pháp lý và mục đích nội dung ở môi trường thực tế.

### 7.2. Unsubscribe và header danh sách

Email marketing cần cơ chế hủy đăng ký thuận tiện, hoạt động thực tế và phản ánh nhanh vào danh sách gửi. Ví dụ nội dung footer:

```text
Bạn nhận email vì đã đăng ký bản tin Example.
Hủy đăng ký: https://example.com/email/unsubscribe?token=<opaque-token>
```

`<opaque-token>` ở đây chỉ là placeholder; trong hệ thống thực tế token phải được cấp an toàn, gắn với người nhận và phạm vi subscription, không chứa bí mật dễ đoán hoặc dữ liệu cá nhân lộ trực tiếp.

Ngoài liên kết trong nội dung, email marketing có thể dùng header `List-Unsubscribe`. Nếu muốn hỗ trợ **one-click unsubscribe theo RFC 8058**, header thường có dạng:

```text
List-Unsubscribe: <https://example.com/email/one-click/<opaque-token>>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Cần hiểu đúng:

1. Chỉ thêm các header trên khi URL thực sự là endpoint HTTPS hỗ trợ **POST one-click** theo quy trình tương ứng; không chỉ là trang mở form hoặc bắt đăng nhập lại.
2. Endpoint phải xác định đúng subscription bằng token có khả năng chống đoán và xử lý idempotent, để yêu cầu lặp lại không gây lỗi nghiệp vụ.
3. Không tự động hủy đăng ký chỉ vì một công cụ quét liên kết thực hiện GET; cần phân biệt yêu cầu POST one-click với lượt xem thông thường.
4. Theo cơ chế RFC 8058, header `List-Unsubscribe` và `List-Unsubscribe-Post` cần nằm trong một chữ ký DKIM hợp lệ để hệ thống nhận có thể tin cậy hành vi one-click.
5. Cần đảm bảo provider/SMTP relay bảo toàn hoặc hỗ trợ đúng các header đó; một số nền tảng marketing có hệ thống unsubscribe riêng và không cho ứng dụng tự quyết toàn bộ.

Trong `MimeMessage`, nếu đã có một URL HTTPS **được hệ thống tin cậy tạo ra**, có thể đặt header:

```java
MimeMessage message = marketingSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("news@example.com");
helper.setTo(recipient);
helper.setSubject("Bản tin tháng này");
helper.setText(plainTextBody, htmlBody);

// oneClickUrl: URL HTTPS hợp lệ, do ứng dụng tạo, không lấy thô từ user.
message.setHeader("List-Unsubscribe", "<" + oneClickUrl + ">");
message.setHeader("List-Unsubscribe-Post", "List-Unsubscribe=One-Click");

marketingSender.send(message);
```

Đoạn trên minh họa **phần đặt header**; nó giả định `recipient`, `oneClickUrl`, `plainTextBody`, `htmlBody`, `marketingSender` đã được cung cấp ở ngữ cảnh phương thức và hệ thống thực sự có endpoint one-click, DKIM và kiểm soát consent hoàn chỉnh. Tránh nhận URL tùy ý có newline rồi đưa trực tiếp vào header.

Chính sách hủy đăng ký và yêu cầu đối với thư gửi số lượng lớn phụ thuộc quốc gia, provider và dịch vụ nhận. Hãy áp dụng quy định cụ thể cho thị trường và danh sách gửi của ứng dụng.

### 7.3. Suppression list và phản hồi delivery

**Suppression list** ghi nhận những địa chỉ không nên gửi nữa theo một hoặc nhiều lý do: unsubscribe, hard bounce, complaint, danh sách từ chối thủ công hoặc yêu cầu người dùng.

Quy trình marketing cần:

1. Kiểm tra consent và suppression khi lập danh sách.
2. Kiểm tra lại gần thời điểm worker thực sự gửi, vì người dùng có thể unsubscribe sau khi campaign được lập.
3. Nhận bounce/complaint từ webhook hoặc event của nhà cung cấp, khi có hỗ trợ.
4. Cập nhật trạng thái người nhận và chặn gửi tiếp theo chính sách.
5. Phân biệt suppression marketing với khả năng tiếp tục gửi email giao dịch cần thiết, nếu chính sách và pháp luật cho phép.

Việc gọi `mailSender.send(...)` thành công **không cung cấp** đầy đủ dữ liệu bounce và complaint phát sinh sau khi SMTP relay chấp nhận thư. Nếu đây là yêu cầu cốt lõi, cần hệ thống event của provider hoặc một nền tảng email chuyên dụng.

### 7.4. Một người nhận trên mỗi message thường dễ quản lý hơn

Khi gửi bản tin cá nhân hóa, nên tạo **mỗi người nhận một thông điệp**:

- Dễ đặt liên kết unsubscribe và token riêng.
- Không làm lộ danh sách email người nhận qua `To` hoặc `Cc`.
- Dễ theo dõi bounce, complaint và trạng thái chiến dịch theo từng địa chỉ.
- Dễ kiểm soát retry và suppression với từng người.

Không nên tạo một email `To` chứa toàn bộ danh sách khách hàng. `Bcc` có thể che địa chỉ khỏi header hiển thị nhưng không thay thế được hệ thống gửi marketing có theo dõi, phân nhóm và xử lý hủy đăng ký theo người nhận.

## 8. Ưu tiên và tốc độ gửi: không để marketing làm chậm transaction

### 8.1. Cách tổ chức queue theo channel

```text
Sự kiện tạo đơn hàng
        |
        v
transactional_outbox / transaction_queue
        |
        v
Transactional worker ----> transactionalMailSender
                                    |
                                    v
                              SMTP giao dịch

Chiến dịch theo lịch
        |
        v
campaign_queue / marketing_jobs
        |
        v
Marketing worker --(rate limit)--> marketingMailSender
                                         |
                                         v
                                   SMTP marketing
```

Cách tổ chức này cho phép:

- Ưu tiên transaction khi hệ thống bận.
- Duy trì retry/backoff khác nhau.
- Tạm dừng chiến dịch mà không dừng email đặt lại mật khẩu.
- Theo dõi queue lag, throughput, lỗi và quota riêng.

**Hai bean sender không tự tạo queue hoặc concurrency control.** Muốn có các thuộc tính trên, phải triển khai ở application worker, broker hoặc nhà cung cấp email.

### 8.2. Rate limit và quota của provider

Các giới hạn có thể bao gồm số email/giây, số recipient/giờ, kích thước thông điệp, số kết nối SMTP đồng thời, hoặc quota theo tài khoản/domain/IP.

Nếu provider trả lỗi tạm thời do vượt tốc độ gửi, worker marketing cần:

- Giảm concurrency hoặc tốc độ gửi.
- Retry có backoff và jitter ở mức hợp lý.
- Tôn trọng giới hạn hoặc tín hiệu retry từ provider khi có.
- Không đẩy retry vô hạn gây quá tải.
- Có cơ chế dừng chiến dịch nếu lỗi kéo dài hoặc tỷ lệ bounce bất thường.

Với transaction, mục tiêu độ trễ có thể thấp hơn và cần cảnh báo sớm nếu queue tăng cao. Nếu hai sender vẫn dùng cùng quota tại provider, sự tách biệt trong Spring **chưa đủ** để bảo vệ transaction khỏi chiến dịch.

### 8.3. Phân loại retry theo lỗi

| Tình huống | Cách xử lý điển hình |
|---|---|
| Timeout kết nối trước khi gửi dữ liệu | Có thể retry theo backoff; kiểm tra điều kiện mạng và quota. |
| `4xx` tạm thời từ SMTP | Retry có kiểm soát nếu lỗi phù hợp; tôn trọng chính sách provider. |
| `535` xác thực thất bại | Kiểm tra credential/cấu hình; retry liên tục ít có giá trị. |
| `550 5.1.1` địa chỉ không tồn tại | Đánh dấu địa chỉ lỗi; không gửi lại vô điều kiện. |
| Timeout **sau khi đã truyền DATA** nhưng chưa nhận phản hồi cuối | Kết quả có thể chưa xác định; retry có thể tạo email trùng. |
| Bounce/complaint sau khi provider tiếp nhận | Cập nhật suppression và trạng thái từ event provider; không coi là lỗi connect. |

Một transaction như gửi biên nhận thường cần **mã sự kiện nghiệp vụ ổn định**, vì nhiều retry không nên tạo thêm nhiều yêu cầu gửi độc lập. Đối với marketing, cần thêm khóa chiến dịch/người nhận và kiểm tra unsubscribe ngay trước mỗi lần gửi.

## 9. Trạng thái gửi và Message-ID

Trong hệ thống email, một số định danh khác nhau thường cùng xuất hiện:

| ID | Nguồn | Mục đích |
|---|---|---|
| `outboxId` / `eventId` | Ứng dụng | Truy vết một yêu cầu gửi gắn với nghiệp vụ. |
| `campaignId` + `recipientId` | Hệ thống marketing | Phân biệt một lần phân phối chiến dịch tới từng người nhận. |
| Header `Message-ID` | Bên tạo thông điệp/Jakarta Mail/provider | Định danh thông điệp email. |
| SMTP queue ID | Máy chủ SMTP | Đối chiếu log của một lần tiếp nhận tại relay. |
| Provider message ID | Dịch vụ email | Tra cứu event và trạng thái bên nhà cung cấp. |

Đừng coi `Message-ID` là khóa idempotency được SMTP bảo đảm. Hai lần gửi có cùng Message-ID vẫn có thể được chuyển phát thành hai bản. Với transaction, nên duy trì outbox ID và theo dõi từng lần thử; với marketing, khóa chiến dịch + người nhận giúp tránh tạo duplicate jobs.

### 9.1. Các trạng thái nên phân biệt

```text
CREATED / QUEUED
      |
      v
SENDING
      |
      +--> ACCEPTED_BY_SMTP / ACCEPTED_BY_PROVIDER
      |            |
      |            +--> DELIVERED (khi có event)
      |            +--> BOUNCED (khi có event)
      |
      +--> TEMPORARY_FAILURE -> retry có giới hạn
      |
      +--> PERMANENT_FAILURE -> xử lý lỗi / suppression
      |
      +--> UNKNOWN -> đối soát / retry thận trọng
```

**`ACCEPTED_BY_SMTP` không bằng `DELIVERED`.** Nếu hệ thống không có event delivery đáng tin cậy, không tự gắn nhãn delivered sau một lần `send(...)` thành công.

Khi sử dụng `JavaMailSender`, `MailException` phản ánh lỗi trong thao tác chuẩn bị/gửi qua Spring. Thao tác trên `MimeMessage` hoặc `MimeMessageHelper` có thể ném `MessagingException` của Jakarta Mail. Nên tách lỗi tạo nội dung với lỗi transport hoặc lỗi delivery phát sinh sau đó.

## 10. Theo dõi và cảnh báo riêng cho từng kênh

Một cấu hình sender hữu ích cần đi cùng khả năng quan sát:

| Chỉ số | Transactional | Marketing |
|---|---|---|
| Số yêu cầu/đã tiếp nhận SMTP | Theo phút và theo loại nghiệp vụ. | Theo chiến dịch và theo đợt gửi. |
| Độ trễ | Từ sự kiện nghiệp vụ đến SMTP tiếp nhận. | Từ lịch chiến dịch đến xử lý từng người. |
| Queue lag | Cảnh báo sớm nếu tăng đột biến. | Điều chỉnh số worker và tốc độ gửi. |
| Lỗi theo loại | TLS/AUTH/timeout/recipient/size. | Rate limit, bounce, complaint, suppression. |
| Delivery event | Nếu provider hỗ trợ, theo dõi các thư quan trọng. | Theo dõi theo campaign, recipient và nhóm người nhận. |
| Tỷ lệ thư bị từ chối | Giúp xác định vấn đề sender/config. | Đặc biệt quan trọng để bảo vệ chất lượng danh sách. |

Ví dụ log có cấu trúc:

```text
channel=transactional event_id=evt-1028
recipient_hash=... status=accepted_by_smtp
duration_ms=420

channel=marketing campaign_id=nov-newsletter
recipient_hash=... status=rate_limited
attempt=2
```

Không ghi password SMTP, token đặt lại mật khẩu, URL unsubscribe mang token, nội dung thư nhạy cảm hoặc toàn bộ địa chỉ người nhận khi không có nhu cầu và kiểm soát phù hợp. Tách log theo channel giúp tìm sự cố mà không phải xem toàn bộ dữ liệu email.

### 10.1. Rủi ro khi chia sẻ cùng một provider

Nếu transaction và marketing dùng chung hạ tầng, cần làm rõ:

- Quota có tách theo API key/subaccount không?
- IP hoặc sending pool có tách không?
- Domain hoặc subdomain gửi có được xác minh riêng không?
- Bounce/complaint của marketing có ảnh hưởng quota hoặc uy tín transaction không?
- Có cơ chế dành năng lực gửi riêng cho giao dịch quan trọng không?

Câu trả lời phụ thuộc dịch vụ thực tế. Việc đổi username SMTP không tự động bảo đảm IP hoặc uy tín gửi được cách ly.

## 11. Các kịch bản lựa chọn kiến trúc

### 11.1. Ứng dụng nhỏ với vài trăm email mỗi ngày

Một website gửi xác nhận đặt hàng và thỉnh thoảng gửi bản tin cho những người đã đăng ký. Nhà cung cấp chỉ có một SMTP account và chưa cần webhook.

Có thể bắt đầu với một `JavaMailSender`, nhưng cần:

- Hai luồng service rõ ràng, tránh trộn nội dung.
- Kiểm tra consent/suppression khi gửi bản tin.
- Giới hạn tốc độ chiến dịch để không chiếm hết tài nguyên.
- Địa chỉ `From` được phép gửi và cơ chế unsubscribe hoạt động.
- Theo dõi số lỗi và khả năng gửi.

Khi khối lượng tăng hoặc mục tiêu giao hàng khác nhau, tách sender và hạ tầng tương ứng.

### 11.2. Thương mại điện tử cần email giao dịch ưu tiên

Đơn hàng, hóa đơn và đặt lại mật khẩu cần gửi nhanh; marketing gửi số lượng lớn theo ngày.

Nên dùng:

1. Transactional outbox hoặc queue được ưu tiên.
2. `transactionalMailSender` và cấu hình SMTP đủ quota cho giao dịch.
3. Marketing queue/worker tách riêng, `marketingMailSender` có rate limit và lịch gửi.
4. Provider events để ghi nhận bounce/delivery khi hệ thống cần.
5. Dashboard và cảnh báo theo từng channel.

Phân tách này vừa rõ ý nghĩa nghiệp vụ, vừa giảm khả năng chiến dịch ảnh hưởng các tác vụ tài khoản và thanh toán.

### 11.3. Marketing nhiều chiến dịch và phân nhóm phức tạp

Nếu cần quản lý danh sách, nội dung theo template, A/B testing, audience segmentation, tự động hóa hành trình khách hàng hoặc reporting, một **nền tảng email marketing** thường phù hợp hơn việc tự gửi vòng lặp hàng loạt qua `JavaMailSender`.

Spring vẫn có thể giữ sender giao dịch, còn kênh marketing được triển khai qua SDK/API hoặc workflow của nền tảng chuyên biệt. Điều quan trọng là application vẫn áp dụng chính sách consent và đồng bộ trạng thái theo đúng phạm vi từng kênh.

## 12. Lỗi thường gặp khi cấu hình sender

### 12.1. “Đã tạo hai JavaMailSender nên chắc chắn có hai sending reputations”

Không. Bean là cấu hình trong JVM. IP, pool, quota và uy tín gửi do provider/relay và hệ thống nhận đánh giá. Muốn tách thật, cần cấu hình nhà cung cấp tương ứng.

### 12.2. “Muốn gửi marketing chỉ cần đổi From của email giao dịch”

Không đủ nếu nội dung, tốc độ gửi, consent, unsubscribe và suppression chưa được kiểm soát. Header `From` không tạo ra quy trình marketing an toàn.

### 12.3. “Người dùng hủy nhận marketing thì ngừng toàn bộ email”

Cần phân biệt phạm vi unsubscribe và mục đích giao dịch. Thư đặt lại mật khẩu hoặc biên nhận cần được xử lý theo yêu cầu nghiệp vụ và chính sách áp dụng, không bị đưa vào chiến dịch chỉ vì dùng cùng SMTP.

### 12.4. “Gửi thành công trong JavaMailSender nghĩa là email đã đến”

Không. Lệnh gửi thành công thường chỉ phản ánh máy chủ SMTP đã tiếp nhận. Delivery cuối cùng, bounce và complaint có thể xảy ra về sau.

### 12.5. “Spring Boot tự biết bean nào dành cho giao dịch”

Không. Khi có nhiều bean cùng type, cần định tuyến có chủ đích qua `@Qualifier`, bean adapter hoặc cấu trúc nghiệp vụ khác; không nên chọn ngẫu nhiên.

### 12.6. “Đưa toàn bộ người nhận vào một To sẽ tiết kiệm và vẫn riêng tư”

Không. Header `To` và `Cc` có thể làm lộ danh sách người nhận cho nhau. Marketing cá nhân hóa thường cần mỗi người nhận một message cùng token unsubscribe và trạng thái riêng.

### 12.7. “List-Unsubscribe-Post có header là tự động đạt one-click”

Không. Cần endpoint HTTPS POST hoạt động theo cơ chế one-click, token an toàn, xử lý unsubscribe thực, DKIM ký các header liên quan và cấu hình provider phù hợp.

### 12.8. “Bật starttls.enable là đã bắt buộc mã hóa”

Chưa chắc. Nếu muốn yêu cầu STARTTLS phải thành công, thường cần thêm `mail.smtp.starttls.required=true` với SMTP provider Jakarta Mail thích hợp. Cổng 465 lại dùng mô hình implicit TLS khác.

### 12.9. “Thay đổi From tự động đổi nơi nhận bounce”

Không. `From` là header hiển thị; envelope sender và địa chỉ xử lý bounce có thể thuộc cấu hình khác ở SMTP/provider. Hãy kiểm tra domain sending và cấu hình return-path của dịch vụ.

## 13. Bài tập thực hành

### Bài 1 — Chọn sender

Một ứng dụng cần gửi mã xác minh sau đăng ký và bản tin hằng tháng. Luồng xác minh có mục tiêu giao thư nhanh; bản tin gửi cho 50.000 người đã đăng ký và có cơ chế unsubscribe.

**Câu hỏi:** Nên dùng một hay hai kênh gửi? Những thứ nào cần tách ngoài bean Spring?

**Gợi ý:** Hai kênh có queue/rate limit và chính sách riêng hợp lý hơn; cân nhắc credential, quota/provider, domain/subdomain và event tracking, đồng thời bảo đảm consent và suppression của marketing.

### Bài 2 — Viết cấu hình hai bean

Sử dụng `MailChannelsProperties` và `MailSenderConfiguration`, hãy thêm một kênh thứ ba `security` dành riêng cho email bảo mật nếu hệ thống yêu cầu. Bean mới nên mang tên rõ ràng, cấu hình SMTP riêng và được inject bằng `@Qualifier` trong service phù hợp.

**Gợi ý:** Không cần tạo `Session` bằng tay cho mỗi email; `JavaMailSenderImpl` đã quản lý Jakarta Mail phía dưới.

### Bài 3 — Phân biệt các địa chỉ

Email hiển thị:

```text
From: "Example Newsletter" <news@example.com>
Reply-To: campaigns@example.com
```

Nhà cung cấp cấu hình envelope sender là `bounce@bounces.example.com`.

**Câu hỏi:** Địa chỉ nào được người nhận thấy, địa chỉ nào nhận phản hồi khi bấm Reply, và địa chỉ nào liên quan đường trả bounce?

**Gợi ý:** `From` là danh tính hiển thị; `Reply-To` là hướng phản hồi; envelope sender gắn với xử lý trả lỗi chuyển phát. Ba địa chỉ có thể khác nhau.

### Bài 4 — Kiểm tra email marketing trước khi gửi

Một chiến dịch đã tạo danh sách 10.000 người. Sau khi tạo danh sách, 200 người đã hủy đăng ký. Nếu worker gửi theo snapshot cũ thì điều gì xảy ra?

**Gợi ý:** Gửi không đúng trạng thái consent hiện tại. Worker cần kiểm tra suppression/consent gần thời điểm gửi và xử lý các yêu cầu hủy đăng ký phát sinh trong lúc chiến dịch đang chạy.

### Bài 5 — Phân loại lỗi

Khi gửi transaction, SMTP trả `535 Authentication failed`. Khi gửi marketing, SMTP trả `451` tạm thời do hạn mức. Bạn sẽ xử lý hai tình huống này giống nhau không?

**Gợi ý:** Không. 535 cần kiểm tra credential/cấu hình, retry vô điều kiện không có ích; 451 thường cần backoff, giới hạn tốc độ và điều phối queue.

### Bài 6 — Thiết kế theo dõi email

Hãy xác định trường cần ghi để theo dõi một biên nhận giao dịch và một thư marketing. Tối thiểu gồm:

| Transactional | Marketing |
|---|---|
| `eventId`, `outboxId`, `attempt` | `campaignId`, `recipientId`, `attempt` |
| `channel=transactional` | `channel=marketing` |
| Thời gian từ sự kiện đến SMTP tiếp nhận | Thời gian xếp hàng và tốc độ xử lý |
| Lỗi transport / provider event | Bounce, complaint, unsubscribe, suppression |

**Gợi ý:** Cần biết ID nào do ứng dụng cấp và ID nào do provider hoặc SMTP relay cấp. Không dùng Message-ID một mình làm khóa chống gửi trùng.

## 14. Kết luận

Trong Spring Framework Mail, `JavaMailSender` là công cụ gửi thư, nhưng **sender cho email giao dịch** và **sender cho email marketing** cần được thiết kế theo yêu cầu nghiệp vụ khác nhau. Transaction ưu tiên độ trễ, tính chính xác và truy vết; marketing ưu tiên kiểm soát danh sách, unsubscribe, tốc độ gửi và khả năng chuyển phát theo chiến dịch.

Có thể bắt đầu với một sender khi hệ thống nhỏ và hạ tầng chung đáp ứng yêu cầu. Khi cần kiểm soát độc lập, cấu hình **hai bean `JavaMailSenderImpl`** với credential/host và identity riêng, định tuyến bằng `@Qualifier` hoặc gateway nghiệp vụ, đồng thời tách queue, rate limit và theo dõi trạng thái. Nếu marketing cần automation và analytics chuyên sâu, kết hợp Spring Mail cho giao dịch với một nền tảng email marketing có thể là lựa chọn phù hợp.

Điểm quyết định không phải số lượng bean, mà là **đúng mục đích thư, đúng người nhận, đúng danh tính gửi, đúng năng lực hạ tầng và đúng cách theo dõi kết quả**.
