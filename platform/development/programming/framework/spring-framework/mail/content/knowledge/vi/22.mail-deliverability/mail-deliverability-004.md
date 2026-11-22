# Tách miền gửi giao dịch với miền marketing

Trong ứng dụng dùng **Spring Framework Mail**, email xác nhận đơn hàng, mã xác thực và thông báo bảo mật có yêu cầu rất khác với newsletter hoặc chiến dịch khuyến mãi. Email giao dịch cần chính xác và đến đúng lúc; marketing có thể gửi theo lô với lưu lượng lớn, chịu tác động mạnh bởi unsubscribe, spam complaint, danh sách cũ và tỷ lệ tương tác.

Nếu hai loại thư dùng cùng một danh tính gửi, SMTP account, hàng đợi và giới hạn provider, một chiến dịch marketing bị đánh dấu spam hoặc gửi vượt quota có thể khiến email OTP hay hóa đơn bị trì hoãn. Vì vậy, **tách miền gửi giao dịch với miền marketing** là một kỹ thuật quản trị **deliverability** nhằm giảm phạm vi ảnh hưởng của sự cố và giúp áp dụng chính sách phù hợp cho từng loại mail.

Một cách tổ chức theo thương hiệu `example.com`:

~~~text
Giao dịch:
  From: orders@notify.example.com
  DKIM signing domain: notify.example.com
  SMTP/API stream: transactional

Marketing:
  From: newsletter@offers.example.com
  DKIM signing domain: offers.example.com
  SMTP/API stream: marketing
~~~

Hai địa chỉ vẫn thể hiện cùng thương hiệu, nhưng dùng **subdomain khác nhau** để dễ phân biệt, xác thực và vận hành.

**Giới hạn quan trọng:** subdomain riêng không tự bảo đảm danh tiếng hoàn toàn độc lập. Mailbox provider có thể đánh giá domain gốc, IP/pool, provider account, URL, nội dung và lịch sử nhận thư. Tách miền là một thành phần của kiến trúc gửi mail lành mạnh, không phải mẹo đảm bảo inbox placement.

## 1. Phân loại email trước khi chọn domain

### 1.1. Email giao dịch (transactional)

Thường phát sinh do một sự kiện hoặc hành động nghiệp vụ cụ thể:

- xác minh địa chỉ email, đăng nhập OTP hoặc đặt lại mật khẩu;
- xác nhận đơn hàng, tình trạng giao hàng, thanh toán, hoàn tiền;
- hóa đơn, biên nhận và thông báo thay đổi tài khoản;
- cảnh báo bảo mật hoặc thay đổi thông tin quan trọng.

Đặc tính:

- người nhận gắn với một giao dịch/tài khoản đã được phép;
- cần độ trễ thấp và theo dõi rõ trạng thái;
- nội dung phải khớp dữ liệu nghiệp vụ;
- có thể có link/token hết hạn nhanh;
- phải thiết kế retry và tránh gửi trùng phù hợp.

### 1.2. Email marketing

Thường nhằm quảng bá, giới thiệu nội dung hoặc duy trì tương tác:

- newsletter định kỳ;
- chương trình khuyến mãi;
- thông báo sản phẩm/tính năng mới;
- thư mời webinar hoặc chiến dịch nuôi dưỡng khách hàng;
- nhắc giỏ hàng bỏ quên và gợi ý mua thêm trong các ngữ cảnh quảng bá.

Đặc tính:

- thường gửi tới nhiều người theo campaign/segment;
- cần chính sách consent và unsubscribe;
- dễ bị ảnh hưởng bởi complaint và danh sách không còn hợp lệ;
- cần rate limiting, warm-up và kiểm soát tần suất;
- có thể hoãn hoặc dừng campaign nếu có dấu hiệu deliverability xấu.

### 1.3. Thư kết hợp: không được phân loại chỉ bằng tên method

Một email xác nhận thanh toán có một banner giảm giá lớn không nhất thiết còn là thư giao dịch thuần túy theo cách phân loại của nhà cung cấp và các quy định áp dụng.

~~~text
Subject: Thanh toán thành công A123

Đơn hàng A123 đã thanh toán.

Mua thêm hôm nay! Giảm 40% cho mọi sản phẩm!
~~~

Không nên đưa email khuyến mãi vào transactional stream bằng cách gọi nó là `sendReceipt(...)`. Hãy tách nội dung giao dịch khỏi quảng cáo nếu có thể.

| Loại thư | Stream thường phù hợp | Lý do |
| --- | --- | --- |
| OTP đăng nhập | Transactional | Thời hạn ngắn, thiết yếu |
| Xác nhận đơn | Transactional | Sự kiện nghiệp vụ |
| Hóa đơn | Transactional | Biên nhận/thông tin giao dịch |
| Cảnh báo bảo mật | Transactional | An toàn tài khoản |
| Bản tin tuần | Marketing | Nội dung quảng bá/đăng ký |
| Mã giảm giá | Marketing | Khuyến mãi |
| Nhắc gia hạn dịch vụ | Cần đánh giá | Phụ thuộc nội dung và mục đích |
| Biên nhận kèm upsell lớn | Cần đánh giá | Có thể mang tính marketing |

Việc phân loại ở đây là hướng dẫn kiến trúc. Yêu cầu pháp lý và chính sách provider phải được xem xét theo khu vực và loại sản phẩm cụ thể.

## 2. Tại sao dùng cùng một domain tạo rủi ro?

Mailbox provider có thể xét:

- domain trong header `From`;
- DKIM signing domain;
- envelope sender/Return-Path;
- IP và pool IP gửi;
- lượng gửi, mức tăng đột biến và lịch sử gửi;
- hard bounce, spam complaint, số lần bị từ chối;
- nội dung, link/tracking domain và tín hiệu tương tác.

Ví dụ một đợt marketing gửi tới danh sách cũ:

~~~text
Marketing gửi 100.000 mail
    |
    +-- nhiều địa chỉ không tồn tại
    +-- tăng spam complaint
    +-- ESP áp dụng throttling/quota
    |
    v
Transactional đang dùng chung SMTP account/pool
    |
    v
OTP và email xác nhận cũng có thể bị chậm
~~~

Nếu tách stream tốt, hệ thống có thể tạm dừng campaign mà vẫn giữ năng lực gửi email giao dịch.

**Không nhầm tách From với tách hạ tầng.** Hai From subdomain vẫn có thể chia sẻ cùng một ESP account và IP pool. Cũng có trường hợp chính sách suspend ở cấp account/domain gốc tác động cả hai luồng. Cần biết ranh giới thực tế mà provider hỗ trợ.

## 3. Thiết kế cây domain

Ví dụ:

~~~text
example.com
  |
  +-- www.example.com               Website
  +-- app.example.com               Application
  +-- notify.example.com            Transactional From
  +-- offers.example.com            Marketing From
  +-- bounce.notify.example.com     Transactional bounce/envelope
  +-- bounce.offers.example.com     Marketing bounce/envelope
~~~

| Vai trò | Địa chỉ hoặc domain |
| --- | --- |
| Sender đơn hàng | `orders@notify.example.com` |
| Sender bảo mật | `security@notify.example.com` |
| Sender newsletter | `news@offers.example.com` |
| Sender ưu đãi | `promotions@offers.example.com` |
| Reply-To giao dịch | `support@example.com` |
| Reply-To marketing | `marketing-support@example.com` |
| Envelope/bounce giao dịch | `bounce.notify.example.com` |
| Envelope/bounce marketing | `bounce.offers.example.com` |

Thông thường, **subdomain của domain thương hiệu** dễ nhận diện hơn các domain hoàn toàn khác nhau. Không nhất thiết mua thêm hai domain gốc.

### 3.1. Phân biệt các tên miền liên quan

Một message có thể có:

~~~text
From: orders@notify.example.com
Reply-To: support@example.com
MAIL FROM: bounces@bounce.notify.example.com
DKIM-Signature: ... d=notify.example.com; s=txn1; ...
SMTP host: smtp.provider.example
~~~

Các giá trị này không phải một:

- **From:** hiển thị người gửi và là domain tham chiếu cho DMARC.
- **Reply-To:** hộp thư nhận phản hồi của người dùng.
- **MAIL FROM / Return-Path:** envelope sender phục vụ bounce, liên quan SPF.
- **DKIM d=:** domain ký xác thực.
- **SMTP host:** server transport, có thể thuộc nhà cung cấp và không giống From domain.

Tách From subdomain có ý nghĩa khi **SPF/DKIM/DMARC và provider identity** cũng được cấu hình chính xác.

### 3.2. Có cần domain gốc độc lập?

Một tổ chức có thể dùng domain gốc khác cho từng thương hiệu độc lập, nhưng không nên đổi sang domain lạ chỉ để trốn reputation kém. Domain mới có ít lịch sử, có thể gây khó nhận biết hoặc làm người nhận nghi ngờ giả mạo.

Tách subdomain là điểm khởi đầu hợp lý khi vẫn giữ một thương hiệu.

## 4. SPF, DKIM và DMARC: nền tảng của từng miền gửi

Tách domain **không tự xác thực email**. Mỗi stream cần được cấu hình với nhà cung cấp gửi thật sự.

### 4.1. SPF và envelope identity

SPF kiểm tra liệu SMTP server có được domain dùng làm danh tính SMTP cho phép gửi hay không, thường là domain của `MAIL FROM` (hoặc HELO trong những trường hợp phù hợp).

Ví dụ:

~~~text
Visible From: orders@notify.example.com
Envelope MAIL FROM: bounce@bounce.notify.example.com
~~~

Trong trường hợp này, SPF được kiểm tra đối với `bounce.notify.example.com` chứ **không tự động** đối với `notify.example.com` trong header From.

Bản ghi **minh họa**, không dùng nguyên xi:

~~~dns
bounce.notify.example.com. TXT "v=spf1 include:_spf.tx-provider.invalid -all"
~~~

`_spf.tx-provider.invalid` là tên ví dụ, không phải hostname thật. Hãy dùng DNS record do ESP cung cấp. Có provider yêu cầu CNAME/MX cho custom Return-Path, có provider quản lý phần này theo cách khác.

SPF cần được cấu hình đúng domain và không có nhiều SPF record `v=spf1` cạnh tranh trên cùng tên. SPF cũng có giới hạn số cơ chế truy vấn DNS; tránh ghép vô tội vạ tất cả nhà cung cấp vào một record.

### 4.2. DKIM và signing domain

DKIM ký email bằng khóa riêng, cho bên nhận tra public key qua DNS và xác minh phần nội dung/header được ký.

~~~text
Transactional:
  From: orders@notify.example.com
  DKIM d=notify.example.com
  Selector: txn1

Marketing:
  From: news@offers.example.com
  DKIM d=offers.example.com
  Selector: mkt1
~~~

Địa chỉ DKIM selector trong DNS có dạng:

~~~text
txn1._domainkey.notify.example.com
mkt1._domainkey.offers.example.com
~~~

ESP có thể yêu cầu TXT public key hoặc CNAME tới hạ tầng của họ. Không tự đặt record theo suy đoán. Có thể tách selector và khóa để quản lý/rotate độc lập cho mỗi stream.

DKIM pass không bảo đảm thư sẽ vào Inbox. Nó chỉ chứng minh khía cạnh xác thực chữ ký, không chứng minh người nhận muốn nhận thông điệp.

### 4.3. DMARC alignment với From

DMARC lấy domain trong **header From** làm điểm tham chiếu. Để DMARC pass, cần ít nhất một trong hai đường:

1. SPF pass **và** SPF identity aligned với From.
2. DKIM pass **và** DKIM `d=` aligned với From.

Ví dụ:

~~~text
From: orders@notify.example.com
DKIM d=notify.example.com           -> aligned exact
MAIL FROM: bounce.notify.example.com
~~~

DKIM `d=notify.example.com` khớp chính xác với From domain nên có thể pass DMARC nếu chữ ký hợp lệ.

SPF domain `bounce.notify.example.com` không bằng chính xác `notify.example.com`; strict SPF alignment không đạt, nhưng relaxed alignment có thể đạt khi chúng cùng organizational domain. Dù SPF strict không aligned, DKIM aligned pass vẫn đủ để DMARC pass.

| From domain | Authenticated domain | Relaxed alignment | Strict alignment |
| --- | --- | --- | --- |
| `notify.example.com` | DKIM `d=notify.example.com` | Có | Có |
| `notify.example.com` | DKIM `d=example.com` | Có trong ví dụ domain tổ chức | Không |
| `notify.example.com` | SPF `bounce.notify.example.com` | Có trong ví dụ domain tổ chức | Không |
| `notify.example.com` | DKIM `d=another.invalid` | Không | Không |

Relaxed alignment dựa trên organizational domain theo quy tắc DMARC/Public Suffix List, không đơn giản là so sánh một chuỗi chứa chuỗi khác.

### 4.4. DMARC riêng cho subdomain

Ví dụ record giai đoạn quan sát:

~~~dns
_dmarc.notify.example.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
_dmarc.offers.example.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
~~~

`p=none` dùng cho giám sát và thu thập report. Sau khi đã xác minh các nguồn gửi hợp lệ, tổ chức có thể chuyển dần sang `p=quarantine` hoặc `p=reject` nếu phù hợp.

DMARC có quy tắc kế thừa/chính sách subdomain, gồm tag `sp=` ở organizational domain khi áp dụng. Nếu subdomain có record riêng, quá trình tra cứu sẽ dùng record tương ứng theo chuẩn. Không giả định một bản ghi DMARC ở root kiểm soát mọi subdomain theo cùng cách trong mọi cấu hình.

Nếu địa chỉ nhận aggregate report `rua` nằm ngoài domain liên quan, có thể cần cơ chế DNS xác thực đích nhận report bên ngoài. Tuân theo tài liệu DMARC và ESP.

**Không tắt chính sách DMARC chỉ để chữa lỗi gửi** mà chưa điều tra alignment. Nếu đang có nhiều nguồn gửi hợp lệ chưa được cấu hình, hãy liệt kê và chuyển lần lượt.

## 5. Tách danh tính và tách nguồn lực gửi

Hai subdomain From là bước đầu; mức độ cô lập thực tế có nhiều tầng:

~~~mermaid
flowchart TD
    A["Application"] --> B{"Mail type"}
    B -->|"Transactional"| C["TX queue/outbox"]
    B -->|"Marketing"| D["MKT queue/campaign"]
    C --> E["TX sender credential/stream"]
    D --> F["MKT sender credential/stream"]
    E --> G["notify.example.com + TX DKIM"]
    F --> H["offers.example.com + MKT DKIM"]
    G --> I["Mail receivers"]
    H --> I
~~~

| Thành phần | Transactional | Marketing |
| --- | --- | --- |
| From domain | `notify.example.com` | `offers.example.com` |
| DKIM domain | `notify.example.com` | `offers.example.com` |
| Bounce identity | `bounce.notify.example.com` | `bounce.offers.example.com` |
| ESP stream | TX nếu hỗ trợ | Marketing nếu hỗ trợ |
| Credential/API key | Riêng hoặc quyền hẹp | Riêng hoặc quyền hẹp |
| Queue | Ưu tiên độ trễ | Batch, scheduling, pacing |
| Quota/rate limiting | Dự trữ capacity cho thông báo thiết yếu | Giới hạn campaign |
| Suppression | Theo loại thông báo và khả năng nhận | Consent, opt-out, complaint |
| Observability | OTP/order latency, failure | Complaint, bounce, unsubscribe |

### 5.1. IP pool và account-level quota

Nếu cả hai stream dùng chung một **shared IP pool**, reputation IP và quota có thể vẫn liên hệ với nhau. Dedicated IP có thể tạo mức kiểm soát khác, nhưng yêu cầu warm-up và lượng gửi ổn định; không phải nâng cấp bắt buộc cho mọi ứng dụng.

Một số nhà cung cấp dùng tên tính năng như message streams, subaccounts, IP pools hoặc sending identities. Cần đối chiếu hướng dẫn cụ thể:

- Stream có quota riêng hay vẫn quota account?
- Suspension vì spam ảnh hưởng stream hay toàn account?
- Suppression list tách stream hay toàn account?
- Có thể tách webhook/bounce event và quyền credential không?
- IP dùng chung hay riêng?

**Chỉ đặt hai tên bean trong Java không tự tạo hai pool reputation.** Phải cấu hình tương ứng trên ESP.

### 5.2. Tách queue để tránh head-of-line blocking

Nếu dùng một queue chung:

~~~text
Shared queue:
  50.000 newsletter jobs
  1 reset-password job
  1 order-confirmation job
~~~

OTP có thể phải đợi những job marketing phía trước. Nên cân nhắc:

~~~text
Transactional:
  business event -> outbox -> high-priority worker -> TX stream

Marketing:
  campaign segment -> queue -> paced worker -> MKT stream
~~~

Ngay cả khi queue khác nhau, nếu SMTP provider có quota chung, marketing vẫn có thể chiếm capacity. Rate limiter cần dành ngân sách phù hợp cho transactional hoặc tách account/stream thực sự khi nhà cung cấp hỗ trợ.

## 6. Cấu hình nhiều JavaMailSender trong Spring Boot

Spring Boot thường tự cấu hình một `JavaMailSender` từ `spring.mail.*`. Khi cần hai transport/sender identity, có thể đăng ký **hai bean `JavaMailSender`** và dùng `@Qualifier` để chọn đúng sender.

### 6.1. application.yml

~~~yaml
app:
  mail:
    transactional:
      host: ${TX_SMTP_HOST}
      port: ${TX_SMTP_PORT:587}
      username: ${TX_SMTP_USER}
      password: ${TX_SMTP_PASSWORD}
      from: orders@notify.example.com
      reply-to: support@example.com
    marketing:
      host: ${MKT_SMTP_HOST}
      port: ${MKT_SMTP_PORT:587}
      username: ${MKT_SMTP_USER}
      password: ${MKT_SMTP_PASSWORD}
      from: newsletter@offers.example.com
      reply-to: marketing-support@example.com
~~~

Đây là các thuộc tính **tùy biến** `app.mail.*` do ứng dụng định nghĩa, không phải `spring.mail.*` mặc định. Credentials lấy từ secret store/biến môi trường, không hard-code.

Hai host có thể trùng nhau nếu cùng ESP nhưng sử dụng credentials/stream riêng theo chính sách; **không coi host trùng hoặc khác là bằng chứng duy nhất về tách quota/reputation**.

### 6.2. Configuration properties

Ví dụ Spring Boot 3 / Java 17+:

~~~java
package com.example.mail.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailStreamsProperties(
        SenderProperties transactional,
        SenderProperties marketing) {
}

record SenderProperties(
        String host,
        int port,
        String username,
        String password,
        String from,
        String replyTo) {
}
~~~

Trong production, nên validate host, port, email From và cấu hình bắt buộc. Nếu provider sử dụng OAuth2, hãy dùng adapter/token provider phù hợp thay vì đặt access token hết hạn vào một password cố định.

### 6.3. Hai sender bean

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MailStreamsProperties.class)
public class MailSenderConfiguration {

    @Bean("transactionalMailSender")
    JavaMailSender transactional(MailStreamsProperties settings) {
        return createSender(settings.transactional());
    }

    @Bean("marketingMailSender")
    JavaMailSender marketing(MailStreamsProperties settings) {
        return createSender(settings.marketing());
    }

    private JavaMailSender createSender(SenderProperties config) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(config.host());
        sender.setPort(config.port());
        sender.setUsername(config.username());
        sender.setPassword(config.password());
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

Với cổng SMTP yêu cầu **implicit TLS** thay vì STARTTLS, phải dùng thuộc tính và port phù hợp, chẳng hạn `mail.smtp.ssl.enable`; ví dụ trên dành cho một endpoint STARTTLS tương ứng. Không tắt TLS hoặc hostname verification để sửa lỗi certificate.

Vì có hai bean cùng type, injection không có qualifier có thể gây ambiguity. Tầng application cần chọn stream rõ ràng.

### 6.4. Model luồng gửi

~~~java
public enum MailStream {
    TRANSACTIONAL,
    MARKETING
}

public record OutgoingMail(
        MailStream stream,
        String recipient,
        String subject,
        String plainText,
        String htmlText,
        String messageKey) {
}
~~~

Request thực tế nên có validation: người nhận, subject, nội dung, nguồn dữ liệu, template, giới hạn kích thước và message key. `MailStream` không được lấy trực tiếp từ một tham số do người dùng ngoài hệ thống tự chọn để né chính sách marketing.

### 6.5. Router dùng đúng sender và From

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RoutedMailService {
    private final JavaMailSender transactionalSender;
    private final JavaMailSender marketingSender;
    private final MailStreamsProperties config;

    public RoutedMailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,
            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,
            MailStreamsProperties config) {
        this.transactionalSender = transactionalSender;
        this.marketingSender = marketingSender;
        this.config = config;
    }

    public void send(OutgoingMail request) throws MessagingException {
        boolean marketing = request.stream() == MailStream.MARKETING;
        JavaMailSender sender = marketing
                ? marketingSender : transactionalSender;
        SenderProperties identity = marketing
                ? config.marketing() : config.transactional();

        MimeMessage message = sender.createMimeMessage();
        boolean hasHtml = request.htmlText() != null
                && !request.htmlText().isBlank();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, hasHtml, "UTF-8");
        helper.setFrom(identity.from());
        helper.setTo(request.recipient());
        helper.setReplyTo(identity.replyTo());
        helper.setSubject(request.subject());

        if (hasHtml) {
            helper.setText(request.plainText(), request.htmlText());
        } else {
            helper.setText(request.plainText());
        }

        sender.send(message);
    }
}
~~~

Đoạn code minh họa việc **route đúng SMTP sender và From**. Nó chưa có:

- phân loại email theo use case;
- validation/authorization;
- consent và unsubscribe marketing;
- suppression checks;
- attachment/inline resources;
- retry và outbox;
- header `List-Unsubscribe`;
- kiểm thử end-to-end SPF/DKIM/DMARC.

Các trách nhiệm này nên được tổ chức thành component riêng thay vì cho một router đơn giản gánh hết.

## 7. Phân loại ở application boundary, không bằng một boolean tùy ý

Một API không rõ:

~~~java
mailService.send(to, subject, body, true);
~~~

`true` có thể vô tình có nghĩa “bỏ qua opt-out”. Tốt hơn là dùng use case:

~~~java
public interface TransactionalNotificationService {
    void sendOrderConfirmation(OrderConfirmationData data);
    void sendSecurityAlert(SecurityAlertData data);
}

public interface MarketingCampaignService {
    void sendNewsletter(NewsletterJob job);
}
~~~

Transactional service yêu cầu sự kiện nghiệp vụ hợp lệ; marketing service xác minh danh sách có consent và chính sách unsubscribe.

Nếu dùng outbox, lưu stream cùng logical job:

~~~text
MailJob(
  stream=TRANSACTIONAL,
  template=order-confirmation,
  recipient=user-88,
  messageKey=order-confirmed:evt-12:user-88
)
~~~

Khi worker retry, stream phải được giữ ổn định; không tự chuyển thư marketing sang transactional chỉ vì provider từ chối hoặc campaign đã dùng hết quota.

## 8. Unsubscribe và preference theo từng stream

**Marketing opt-out** khác với lựa chọn nhận email bảo mật/giao dịch.

Ví dụ:

~~~text
User preferences:
  marketingNewsletter = false
  productOffers       = false
  orderReceipts       = true
  securityAlerts      = true
~~~

Nếu áp dụng marketing unsubscribe cho cả SMTP stream giao dịch, người dùng có thể mất email khôi phục mật khẩu hoặc hóa đơn cần thiết. Ngược lại, nếu gửi nội dung marketing qua transactional để bỏ qua opt-out, hệ thống đã phá vỡ phân loại và có thể làm tổn hại deliverability.

### 8.1. List-Unsubscribe và one-click

Với email marketing trong phạm vi áp dụng, có thể cung cấp header:

~~~text
List-Unsubscribe: <https://offers.example.com/unsubscribe/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

RFC 2369 mô tả `List-Unsubscribe`; RFC 8058 mô tả one-click HTTPS unsubscribe dùng HTTP POST. Endpoint cần thật sự xử lý hủy đăng ký, bảo vệ token, chống abuse và không dựa vào GET gây side effect vì hệ thống bảo mật email có thể tự mở liên kết.

Không phải chỉ thêm hai header là mọi mailbox client sẽ hiển thị nút unsubscribe. Provider có yêu cầu riêng về xác thực và chức năng của endpoint. Nội dung marketing cũng nên cung cấp cách quản lý sở thích/hủy đăng ký dễ nhìn.

### 8.2. Consent và trạng thái suppression

Phân biệt các lý do:

| Trạng thái | Ý nghĩa | Ảnh hưởng |
| --- | --- | --- |
| Marketing unsubscribed | Không muốn nhận quảng cáo | Chặn marketing liên quan |
| Hard bounce | Địa chỉ không nhận được thư dứt khoát | Có thể chặn mọi stream theo policy hợp lý |
| Soft bounce | Lỗi tạm thời | Retry/backoff theo giới hạn |
| Spam complaint | Người nhận báo spam | Chặn marketing, điều tra nguồn gửi |
| Security notification enabled | Chính sách/thỏa thuận cần cảnh báo | Không tự chặn chỉ vì marketing opt-out |

Chính sách cuối phải phù hợp nghĩa vụ thông báo, consent và quyền riêng tư. Transactional mail vẫn cần kiểm tra recipient thuộc tài khoản/giao dịch hợp lệ và không được gửi vô điều kiện.

### 8.3. Suppression list của ESP có thể là toàn account

Dù ứng dụng đã tách domain, ESP vẫn có thể chia sẻ suppression list giữa các stream. Cần xác minh:

- hard bounce suppression áp dụng toàn account hay riêng stream;
- marketing opt-out nằm trong ESP hay application preference center;
- webhook nào có quyền cập nhật recipient status;
- khi khôi phục một địa chỉ, stream nào được gửi lại.

Không xử lý mọi loại suppression bằng một cờ Boolean `emailBlocked` thiếu ngữ cảnh.

## 9. Bounce, complaint và delivery events

SMTP submission thành công **không đồng nghĩa email đã tới Inbox**. Có thể nhận bounce sau đó hoặc bị mailbox provider phân loại spam.

Một state model:

~~~text
PENDING -> SUBMITTING -> SUBMITTED
                          |
                          +-- DELIVERED (provider event)
                          +-- BOUNCED (provider event)
                          +-- DEFERRED (provider event)
~~~

Với marketing, còn các sự kiện:

~~~text
COMPLAINT
UNSUBSCRIBED
~~~

Thường cần xử lý:

- Hard bounce: cập nhật trạng thái địa chỉ, tránh gửi tiếp bừa bãi.
- Soft bounce: backoff và kiểm soát số lần thử.
- Complaint: chặn marketing và điều tra nguồn consent.
- Unsubscribe: cập nhật preference đúng phạm vi.
- Delivered: đánh dấu theo semantics của provider, không suy ra người nhận đã đọc.

### 9.1. Webhook độc lập theo stream

~~~text
TX provider webhook
    -> transactional delivery events

MKT provider webhook
    -> marketing delivery events

Both:
    -> normalized recipient delivery store
~~~

Webhook phải được xác thực bằng cơ chế provider công bố (ví dụ chữ ký và timestamp), xử lý idempotent và kiểm tra mapping message/job ID. Không tin vào một event HTTP chưa xác thực để thay đổi suppression hoặc trạng thái tài khoản.

## 10. Nội dung, URL và tracking cũng cần phân biệt

Email giao dịch có thể chứa:

~~~text
https://app.example.com/orders/A123
~~~

Marketing có thể dùng:

~~~text
https://offers.example.com/campaign/summer
~~~

Nếu ESP sử dụng click tracking, có thể cấu hình branded tracking domain riêng cho marketing. Domain tracking và URL đích cũng có thể là tín hiệu spam, vì vậy cần:

- tránh open redirect;
- chỉ dùng HTTPS;
- giới hạn đích redirect;
- không nhúng credential vào link;
- không ghi log token reset password;
- đánh giá kỹ việc bật click tracking trong thông báo bảo mật.

SPF/DKIM/DMARC xác thực **danh tính gửi**, không bảo đảm link vô hại hoặc nội dung được người nhận mong muốn.

## 11. Warm-up subdomain và IP pool mới

Một subdomain marketing mới chưa có lịch sử gửi. Gửi ngay khối lượng lớn có thể dẫn tới deferral hoặc spam filtering mạnh hơn. Có thể bắt đầu với người nhận đã đồng ý và tương tác tốt, sau đó tăng dần lượng gửi dựa trên tín hiệu thực tế.

Lộ trình khái quát:

1. Xác thực DNS/domain với ESP.
2. Gửi thử các email nhỏ, kiểm tra raw headers.
3. Bắt đầu từ phân khúc nhận thư hợp lệ và có tương tác.
4. Tăng lưu lượng có kiểm soát.
5. Giám sát hard bounce, complaint, deferral và provider feedback.
6. Dừng tăng hoặc giảm tốc khi tín hiệu xấu.

Không có lịch warm-up cố định áp dụng cho mọi provider. Dedicated IP mới có thể cần kế hoạch warm-up riêng; shared IP được ESP quản lý có thể có cách tiếp cận khác.

### 11.1. Không xoay subdomain để tránh reputation xấu

Nếu `offers.example.com` phát sinh nhiều complaint, đổi sang `deals1.example.com` rồi tiếp tục gửi cùng một danh sách kém chất lượng **không giải quyết nguyên nhân**. Hãy kiểm tra consent, dọn danh sách, giảm tần suất và cải thiện nội dung. Receiver có thể liên hệ reputation ở cấp domain gốc và nhiều tín hiệu khác.

## 12. DNS migration mà không làm gián đoạn mail hiện hữu

Tách miền cần kiểm kê những dịch vụ đang dùng domain gốc:

- email nhân viên trên Google Workspace, Microsoft 365 hoặc hệ thống khác;
- SPF/DKIM/DMARC hiện tại;
- MX phục vụ mail đến;
- domain alias và sender identities;
- custom bounce domain hoặc tracking domain đã đăng ký;
- các job đã xếp hàng và thư đang lưu chuyển.

### 12.1. Không đổi MX domain gốc chỉ để gửi qua ESP

MX chủ yếu phục vụ **nhận** thư. Nếu nhân viên đang nhận tại `example.com`, không cần chuyển MX gốc sang transactional ESP chỉ vì thêm `notify.example.com` làm From.

Một số ESP yêu cầu MX cho **bounce subdomain** riêng; đó là một cấu hình khác. Chỉ thay record đúng hostname mà provider xác định.

### 12.2. Giữ DKIM key cũ đủ lâu

Khi đổi ESP, không xóa ngay selector public key đang dùng cho thư đã gửi trước đó. Message có thể tiếp tục được chuyển tiếp hoặc kiểm tra chữ ký sau thời điểm gửi. Cần có thời gian chuyển tiếp và chính sách key rotation.

### 12.3. Theo dõi DMARC khi chuyển

Đừng chuyển ngay toàn bộ sang `p=reject` mà không biết các hệ thống đang gửi thay mặt domain. Có thể quan sát báo cáo ở `p=none`, xác minh từng nguồn, rồi tăng mức enforcement khi thích hợp.

## 13. Metrics cho deliverability theo stream

Không nên chỉ có dashboard “đã gửi tổng cộng bao nhiêu email”.

| Metric | Transactional | Marketing |
| --- | --- | --- |
| Submission attempts/success | Có | Có |
| SMTP/API latency | Ưu tiên | Có |
| Queue depth/oldest age | Ưu tiên cảnh báo | Dùng để điều tiết campaign |
| Deferral và 4xx response | Có | Có |
| Hard/soft bounce | Có | Có |
| Complaint | Theo dõi | Cực kỳ quan trọng |
| Unsubscribe | Tùy loại | Bắt buộc quan sát |
| DKIM/DMARC failures | Có | Có |
| Provider quota usage | Có | Có |
| Delivery event | Nếu provider cung cấp | Nếu provider cung cấp |

Ví dụ log:

~~~text
event=mail_submission
stream=transactional
senderDomain=notify.example.com
mailType=ORDER_CONFIRMATION
jobId=job-752
result=SUBMITTED
latencyMs=420
~~~

Không đặt recipient email, full subject hoặc message key riêng lẻ vào metric labels có cardinality cao. Log cần giảm dữ liệu cá nhân và không chứa SMTP passwords, OAuth tokens hoặc nội dung thư không cần thiết.

### 13.1. SLO theo nghiệp vụ

Transactional cần đo:

~~~text
OrderConfirmed event
    -> outbox persisted
    -> worker picked up
    -> SMTP/API submitted
    -> delivery event (nếu có)
~~~

Email OTP cần quan tâm thời gian đến được người nhận trước khi token hết hạn. Marketing quan tâm khả năng tiếp cận hợp lệ, complaint, unsubscribe và danh sách chất lượng. Hai luồng không nên dùng một chỉ số “send success” chung rồi suy ra đều vận hành tốt.

### 13.2. Cảnh báo đáng quan tâm

- Transactional queue age tăng dù marketing đang gửi bình thường.
- SMTP authentication failure của một sender identity.
- DMARC alignment failure sau khi đổi DNS.
- Marketing complaint hoặc hard bounce tăng mạnh.
- Provider quota có nguy cơ hết vì campaign.
- Bounce webhook bị lỗi khiến suppression cập nhật chậm.
- ESP suspend account ở cấp rộng hơn stream.

## 14. Test việc tách miền

### 14.1. Unit test router

Với hai sender mock, có thể kiểm tra đúng route:

~~~java
@Test
void orderConfirmationUsesTransactionalSender() throws Exception {
    routedMailService.send(transactionalMail);

    verify(transactionalSender).send(any(MimeMessage.class));
    verifyNoInteractions(marketingSender);
}

@Test
void newsletterUsesMarketingSender() throws Exception {
    routedMailService.send(marketingMail);

    verify(marketingSender).send(any(MimeMessage.class));
    verifyNoInteractions(transactionalSender);
}
~~~

Đây là ý tưởng test. Nếu mock `JavaMailSender`, cần cấu hình `createMimeMessage()` để trả về đối tượng MIME hợp lệ và dùng fixture khớp router implementation.

Các trường hợp test thêm:

- From/Reply-To theo stream;
- giao dịch không lấy nhầm marketing SMTP credential;
- marketing bị chặn khi không có consent;
- unsubscribe chỉ áp dụng đúng loại thông báo;
- sender không được chọn bằng dữ liệu client tùy ý;
- job retry giữ nguyên stream;
- lỗi một provider được ghi nhận cho đúng stream/job.

### 14.2. Integration test SMTP và DNS

Dùng mailbox thử nghiệm được phép để kiểm tra:

1. From giao dịch thực sự là `notify.example.com`.
2. From marketing thực sự là `offers.example.com`.
3. DKIM `d=` đúng với từng stream.
4. SPF pass trên envelope domain phù hợp.
5. DMARC pass với alignment đúng.
6. Return-Path/bounce mapping đúng.
7. Unsubscribe marketing hoạt động.
8. Event provider được gắn đúng job/stream.
9. Không thay đổi nhầm MX email nhân viên.

Hộp thư thử nghiệm có thể cung cấp `Authentication-Results` và raw MIME. Nhưng unit test Java hoặc SMTP mock không chứng minh inbox placement thật; receiver khác nhau có thể đánh giá reputation khác nhau.

### 14.3. Test vận hành

- Tạm dừng marketing worker: giao dịch vẫn được xử lý.
- Marketing vượt rate limit: không kéo transactional vào backlog theo thiết kế.
- Provider account bị chặn: xác nhận kế hoạch ứng phó cấp account.
- Webhook gửi lặp: handler idempotent.
- Một hard bounce từ marketing: cập nhật suppression theo policy, không tự sửa mọi loại preference.
- Retry transport sau timeout: giữ trạng thái UNKNOWN khi chưa biết provider có nhận thư hay không.

## 15. Kế hoạch chuyển từ một domain sang hai

Giả sử trạng thái ban đầu:

~~~text
From: no-reply@example.com
SMTP account: shared
Queue: one queue for all mail
Templates: mixed transactional and marketing
~~~

Quy trình chuyển đổi có thể gồm các giai đoạn:

### Giai đoạn A — Kiểm kê và phân loại

Liệt kê mọi email type, template, event source, From, reply-to, domain, provider credentials, quota, queue và webhook. Tách các email có nội dung lai. Xác định quyền người nhận và marketing opt-out.

### Giai đoạn B — Cấu hình danh tính mới

Thiết kế:

~~~text
TX:  notify.example.com  + transactional provider identity
MKT: offers.example.com  + marketing provider identity
~~~

Thiết lập DKIM, SPF cho đúng envelope domain, DMARC và bounce domain. Cấu hình stream/subaccount/quota ở ESP khi cần.

### Giai đoạn C — Triển khai routing

Tạo hai sender bean hoặc adapter; đưa stream vào outbox/job; áp dụng consent/opt-out cho marketing; tách queue và rate limiter.

### Giai đoạn D — Canary và warm-up

Gửi thử bằng account/mailbox kiểm soát được; xác minh Authentication-Results, webhook, logging và domain alignment. Tăng transactional traffic trước theo kế hoạch an toàn, rồi marketing theo phân khúc đủ điều kiện.

### Giai đoạn E — Quan sát, mở rộng, thu hồi cũ

Theo dõi latency, complaint, bounce, DMARC reports, deferral và quota. Giữ record/credential cũ khi còn traffic hợp lệ; thu hồi theo kế hoạch sau khi migration hoàn tất.

**Tránh đổi tất cả cùng lúc**: provider, SMTP host, domain, DKIM, queue và template đều thay đổi một ngày thì rất khó chẩn đoán nếu deliverability giảm.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Chỉ đổi From nhưng dùng chung mọi sender/queue | Rủi ro quota/backlog vẫn chung | Tách hạ tầng phù hợp |
| Không cấu hình DKIM cho subdomain mới | DMARC có thể không pass | Xác minh `d=` và DNS selector |
| SPF pass nhưng sai alignment | DMARC có thể fail | Kiểm tra domain envelope và From |
| Dùng Reply-To để suy ra DMARC | Sai cơ chế | DMARC căn cứ header From |
| Ghi nhiều SPF record trên cùng hostname | SPF permerror | Dùng một SPF policy đúng |
| Xóa selector DKIM cũ quá sớm | Email đang chuyển có thể fail DKIM | Giữ key trong giai đoạn chuyển |
| Marketing gửi qua transactional để né unsubscribe | Consent/policy sai, ảnh hưởng uy tín TX | Phân loại theo nội dung và use case |
| Marketing unsubscribe chặn cả OTP | Mất thông báo thiết yếu | Preference theo scope |
| Không theo dõi bounce/suppression theo stream | Không biết nguồn sự cố | Event mapping và dashboards riêng |
| Cho campaign dùng hết quota chung | OTP bị chậm/từ chối | Reserve capacity/tách stream hoặc account |
| Domain mới gửi ồ ạt | Deferral và lọc spam | Warm-up, theo dõi |
| Coi mọi subdomain có reputation độc lập | Kỳ vọng sai | Theo dõi cả root domain/IP/provider |
| Dùng domain mới để tiếp tục spam danh sách cũ | Vấn đề không được giải quyết | Làm sạch danh sách và consent |
| Coi SMTP `250` là đã vào Inbox | Báo sai delivery | Theo dõi delivery event riêng |
| Failover rồi retry mù khi kết quả chưa rõ | Người nhận có thể nhận trùng | Idempotency/UNKNOWN policy |

## 17. Tình huống tổng hợp: cửa hàng trực tuyến

Ứng dụng cần gửi xác nhận đặt hàng và newsletter:

~~~text
Đơn hàng A123 được xác nhận
    |
    v
Transactional outbox
    |
    v
TX MailWorker
    |
    v
orders@notify.example.com
    |
    v
SMTP/API transactional stream

Campaign sản phẩm cuối tuần
    |
    v
Marketing segment đã đủ điều kiện
    |
    v
MKT MailWorker (pacing + unsubscribe)
    |
    v
newsletter@offers.example.com
    |
    v
SMTP/API marketing stream
~~~

Khi chiến dịch marketing tạo nhiều hard bounce:

1. Marketing monitoring phát hiện số lượng bounce/complaint tăng.
2. Campaign được giảm tốc hoặc tạm dừng.
3. Hệ thống cập nhật danh sách suppression và nguồn consent.
4. Transactional queue và sender tiếp tục làm việc theo năng lực đã được dự trữ.
5. Nếu ESP áp dụng quota hay suspension cấp account, người vận hành vẫn phải xử lý vì ranh giới này chưa chắc đã độc lập.

Kết quả mong muốn là khả năng **khoanh vùng, nhận biết và ứng phó** chứ không phải hứa hẹn rằng email nào cũng vào Inbox.

## 18. Checklist trước production

### Phân loại và quyền gửi

- [ ] Mỗi email type có stream rõ ràng.
- [ ] Nội dung transactional không bị trộn quảng cáo tùy tiện.
- [ ] Marketing có consent, unsubscribe và preference policy phù hợp.
- [ ] Caller không tự ý chuyển marketing sang transactional.

### Domain và xác thực

- [ ] From subdomain riêng cho hai luồng.
- [ ] DKIM ký bằng signing domain đúng.
- [ ] SPF record đúng envelope/bounce identity và ESP.
- [ ] DMARC alignment pass, policy/report phù hợp.
- [ ] MX domain gốc và inbox hiện có không bị ảnh hưởng.
- [ ] Reply-To, bounce và tracking hostname được xác định rõ.

### Hạ tầng

- [ ] Credentials và stream được cấu hình đúng theo provider.
- [ ] Queue/worker/limiter tránh marketing làm tắc giao dịch.
- [ ] Hiểu rõ quota, IP pool và suppression áp dụng theo cấp nào.
- [ ] Retry có message key và không gửi lại mù sau timeout.
- [ ] Webhook được xác thực và xử lý idempotent.

### Vận hành

- [ ] Dashboard phân biệt TX/MKT.
- [ ] Có cảnh báo latency, bounce, complaint, deferral và authentication failure.
- [ ] Có kế hoạch warm-up, migration và rollback.
- [ ] Không log SMTP password, API key hoặc nội dung cá nhân không cần thiết.
- [ ] Có runbook tạm dừng campaign mà không dừng thông báo quan trọng.

## 19. Những điều cần nhớ

- **Tách email giao dịch và marketing theo mục đích trước khi tách domain.**
- Có thể dùng `notify.example.com` và `offers.example.com` dưới cùng một domain thương hiệu.
- From, DKIM, SPF envelope identity, Return-Path và SMTP host là các khái niệm khác nhau.
- Mỗi stream cần cấu hình xác thực DNS và DMARC alignment chính xác.
- Tách From subdomain **không** bảo đảm tách IP reputation, quota hoặc account-level restriction.
- Marketing cần consent/unsubscribe, list hygiene, pacing và complaint handling; transactional cần độ trễ thấp và tính chính xác.
- Nên tách queue, worker, credentials, stream và monitoring theo khả năng của hệ thống.
- Subdomain/IP mới có thể cần warm-up; không tăng đột ngột khi chưa theo dõi tín hiệu.
- Xác thực tốt chưa đồng nghĩa deliverability tốt, cũng không bảo đảm mọi thư tới Inbox.

Trong Spring Framework Mail, tách miền gửi giao dịch với miền marketing là **một quyết định kiến trúc và vận hành**, không chỉ là đổi chuỗi `setFrom(...)`. Phân loại đúng use case, xác thực subdomain, cô lập nguồn lực gửi và theo dõi kết quả riêng giúp giảm khả năng một chiến dịch marketing làm ảnh hưởng tới những email quan trọng, đồng thời giúp vận hành marketing có trách nhiệm hơn.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** mail auto-configuration và properties.
- **RFC 5321 — Simple Mail Transfer Protocol:** `MAIL FROM`, `RCPT TO` và SMTP submission.
- **RFC 5322 — Internet Message Format:** `From`, `Reply-To` và message headers.
- **RFC 7208 — Sender Policy Framework (SPF):** kiểm tra domain SMTP và giới hạn DNS lookup.
- **RFC 6376 — DomainKeys Identified Mail (DKIM):** ký/xác minh domain và selector.
- **RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC):** identifier alignment, policy, report.
- **RFC 2369 — URLs as Meta-Syntax for Core Mail List Commands:** `List-Unsubscribe`.
- **RFC 8058 — Signaling One-Click Functionality for List Email Headers:** one-click unsubscribe.
- **Tài liệu ESP/mailbox provider hiện sử dụng:** sending domain verification, quota, bounce handling, suppression và deliverability guidance.
