# @ConditionalOnProperty với havingValue và matchIfMissing

Trong Spring Boot, không phải bean hoặc cấu hình nào cũng cần được đăng ký trong mọi môi trường. Ứng dụng có thể chỉ bật email notification khi người vận hành cho phép, chỉ tạo integration với dịch vụ ngoài khi feature flag được bật, hoặc chỉ cung cấp implementation mặc định khi người dùng chưa khai báo bean thay thế.

`@ConditionalOnProperty` là annotation của Spring Boot dùng để **đánh giá một hoặc nhiều property trong Environment trước khi áp dụng cấu hình hoặc đăng ký bean**. Hai thuộc tính quan trọng nhất là:

- `havingValue`: xác định giá trị property cần khớp.
- `matchIfMissing`: xác định điều kiện có được xem là đạt khi property không tồn tại hay không.

Hiểu đúng hai thuộc tính này giúp tránh lỗi phổ biến: tưởng rằng property chỉ cần “có mặt” là cấu hình được bật, trong khi giá trị thực tế có thể là `false`, hoặc property chưa được khai báo nhưng `matchIfMissing` lại khiến tính năng hoạt động theo mặc định.

## 1. Cấu hình theo điều kiện là gì?

Một bean thông thường có thể được đăng ký trong context khi cấu hình chứa nó được nạp. Nhưng đôi khi bạn muốn bean chỉ xuất hiện khi môi trường đáp ứng một điều kiện.

Ví dụ ứng dụng có tính năng gửi thông báo email:

- Khi `notification.email.enabled=true`, đăng ký email sender.
- Khi property là `false`, không đăng ký email sender.
- Nếu property không được khai báo, có thể chọn mặc định tắt để tránh ứng dụng tự kết nối SMTP ngoài ý muốn.

Thay vì kiểm tra property trong mọi method:

```java
@Service
public class NotificationService {

    @Value("\${notification.email.enabled:false}")
    private boolean enabled;

    public void send(String message) {
        if (!enabled) {
            return;
        }
        // Gửi email...
    }
}
```

bạn có thể điều kiện hóa chính cấu hình đăng ký bean:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true"
)
public class EmailNotificationConfiguration {

    @Bean
    public EmailSender emailSender() {
        return new EmailSender();
    }
}
```

Khi điều kiện không thỏa, cấu hình này không được áp dụng và bean `emailSender` không được đăng ký từ cấu hình đó. Các thành phần khác vẫn có thể khởi động nếu chúng không bắt buộc dependency này.

**Điểm khác biệt:** `@Value` đọc giá trị để một bean đã được tạo sử dụng; `@ConditionalOnProperty` quyết định cấu hình/bean có được đăng ký hay không. Hai cơ chế có mục đích khác nhau.

## 2. Annotation nằm ở đâu và dùng trên thành phần nào?

`@ConditionalOnProperty` thuộc package:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
```

Nó được cung cấp bởi Spring Boot auto-configuration module, không phải annotation cốt lõi của Spring Framework. Ứng dụng Spring Boot thường có dependency phù hợp thông qua starter và dependency management của dự án.

Annotation có thể được đặt trên:

- **Configuration class**: điều kiện áp dụng cho cả lớp cấu hình; nếu không thỏa, các bean definitions khai báo trong lớp đó không được áp dụng.
- **Phương thức `@Bean`**: điều kiện áp dụng riêng cho bean do method đó cung cấp.
- **Auto-configuration class**: cách dùng phổ biến khi viết starter hoặc thư viện tích hợp Spring Boot.

Ví dụ điều kiện ở cấp bean method:

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "notification.email",
        name = "enabled",
        havingValue = "true"
    )
    public EmailSender emailSender() {
        return new EmailSender();
    }

    @Bean
    public SmsSender smsSender() {
        return new SmsSender();
    }
}
```

Ở đây điều kiện chỉ kiểm soát `emailSender`. `smsSender` vẫn được khai báo nếu configuration class được nạp bình thường.

Nếu đặt annotation trên class `NotificationConfiguration`, cả cấu hình class sẽ chịu điều kiện đó.

## 3. Prefix và name: xác định property cần kiểm tra

Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled"
)
```

Spring Boot kiểm tra property có tên đầy đủ:

```text
notification.email.enabled
```

- `prefix` là phần tiền tố chung của tên property.
- `name` là tên property cần kiểm tra sau prefix.
- `value` là alias của `name`; trong code mới nên dùng `name` để dễ đọc.

Có thể kiểm tra nhiều property:

```java
@ConditionalOnProperty(
    prefix = "notification",
    name = {"email.enabled", "provider"}
)
```

Khi khai báo nhiều tên, **tất cả property được liệt kê phải thỏa điều kiện** để condition match. Đây là logic AND, không phải chỉ cần một property đúng.

Ví dụ tương đương về tên đầy đủ:

```text
notification.email.enabled
notification.provider
```

Nếu một property không tồn tại và `matchIfMissing` là false (mặc định), điều kiện tổng thể không đạt.

### Quy tắc viết prefix

Prefix không rỗng nên kết thúc bằng dấu chấm. Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "app.integration.payment",
    name = "enabled"
)
```

Tên property nên dùng dạng canonical kebab-case trong annotation và file cấu hình:

```text
app.integration.payment.enabled
```

Spring Boot hỗ trợ relaxed binding cho nhiều loại property binding, nhưng không nên dựa vào việc viết tên tùy tiện trong condition. Dùng tên canonical giúp dễ đối chiếu giữa annotation, `application.yml`, environment variable và tài liệu cấu hình.

## 4. havingValue: giá trị nào được xem là khớp?

`havingValue` xác định giá trị property cần có để condition match.

Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
```

Cấu hình chỉ match khi property `feature.report` có giá trị `true` theo phép so sánh của điều kiện.

Các trường hợp thường gặp:

| Property value | havingValue = "true" | havingValue = "false" | havingValue = "" (mặc định) |
|---|---:|---:|---:|
| `true` | Match | Không match | Match |
| `false` | Không match | Match | Không match |
| `TRUE` | Match | Không match | Match |
| `enabled` | Không match | Không match | Match |
| `smtp` | Không match | Không match | Match |
| Property không tồn tại | Phụ thuộc matchIfMissing | Phụ thuộc matchIfMissing | Phụ thuộc matchIfMissing |

Khi `havingValue` không được khai báo hoặc để chuỗi rỗng, quy tắc mặc định là: **property phải tồn tại và giá trị không được bằng chuỗi `false` (không phân biệt hoa/thường)**. Do đó giá trị như `enabled` hoặc `smtp` vẫn có thể match ở chế độ mặc định.

Đây là điểm dễ gây hiểu nhầm. Nếu bạn muốn một feature flag chỉ bật khi giá trị đúng là boolean true, hãy khai báo rõ:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
```

Không nên dựa vào `havingValue` rỗng khi property có thể nhận các chuỗi khác nhau.

### Ví dụ với giá trị dạng enum/string

Giả sử ứng dụng chọn provider:

```properties
payment.provider=stripe
```

Bạn có thể dùng:

```java
@ConditionalOnProperty(
    prefix = "payment",
    name = "provider",
    havingValue = "stripe"
)
```

Điều kiện match khi giá trị property là `stripe`; nếu là `bank` thì không match. Cách này phù hợp khi property có tập giá trị hữu hạn và bạn muốn đăng ký riêng từng implementation.

`havingValue` là phép so sánh giá trị property, không phải biểu thức điều kiện tổng quát. Nếu cần so sánh số, pattern phức tạp, quan hệ nhiều property hoặc logic động, hãy cân nhắc custom condition.

## 5. matchIfMissing: điều gì xảy ra khi property chưa được khai báo?

`matchIfMissing` có kiểu boolean và mặc định là `false`.

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true",
    matchIfMissing = false
)
```

Với cấu hình này:

- Property tồn tại và là `true`: match.
- Property tồn tại và là `false`: không match.
- Property không tồn tại: không match vì `matchIfMissing = false`.

Nếu đặt `matchIfMissing = true`:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true",
    matchIfMissing = true
)
```

thì property không tồn tại được xem là đạt điều kiện. Khi property có mặt, `havingValue` vẫn được áp dụng như bình thường.

Bảng tổng hợp:

| Property | havingValue="true", matchIfMissing=false | havingValue="true", matchIfMissing=true |
|---|---:|---:|
| Không tồn tại | Không match | Match |
| true | Match | Match |
| false | Không match | Không match |
| enabled | Không match | Không match |

**`matchIfMissing=true` không có nghĩa mọi giá trị đều được chấp nhận.** Nó chỉ thay đổi cách xử lý trường hợp property không tồn tại. Khi property có mặt, `havingValue` vẫn quyết định giá trị có hợp lệ hay không.

### Khi nào nên bật matchIfMissing?

- `false` (mặc định): tính năng phải được bật rõ ràng; phù hợp với integration tùy chọn hoặc kết nối ngoài có thể gây tác dụng phụ.
- `true`: muốn tính năng hoạt động theo mặc định khi người dùng chưa cấu hình; phù hợp khi đó là behavior mặc định có chủ đích và an toàn.

Không nên chọn `true` chỉ để tránh thiếu property. Hãy quyết định theo behavior mong muốn khi ứng dụng được triển khai mà chưa có cấu hình đó.

## 6. Kết hợp havingValue và matchIfMissing đúng ý định

Bốn cấu hình sau có behavior khác nhau.

### Trường hợp A — Mặc định tắt, bật khi true

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "export",
    havingValue = "true"
)
```

Do `matchIfMissing` mặc định là false, feature chỉ bật khi người vận hành khai báo property là true.

```properties
feature.export=true
```

Không có property hoặc property là false đều không đăng ký bean.

### Trường hợp B — Mặc định bật, chỉ tắt khi false

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = "export",
    havingValue = "true",
    matchIfMissing = true
)
```

Property không có thì feature bật. Khi property có mặt, chỉ true mới match; false không match.

Cách này diễn đạt chính sách “enabled by default, explicit false disables”.

### Trường hợp C — Mặc định tắt, kiểm tra property có giá trị khác false

```java
@ConditionalOnProperty(
    prefix = "integration",
    name = "provider"
)
```

Vì `havingValue` mặc định rỗng và `matchIfMissing` mặc định false:

- Không có `integration.provider`: không match.
- Giá trị `false`: không match.
- Giá trị `stripe`, `bank`, `enabled` hoặc chuỗi không rỗng khác `false`: match.

Điều kiện này kiểm tra sự hiện diện và giá trị không phải false; nó **không** xác nhận provider có thuộc danh sách hợp lệ. Nếu chỉ cho phép stripe/bank, dùng `havingValue` riêng hoặc custom condition.

### Trường hợp D — Mặc định bật với giá trị property không phải false

```java
@ConditionalOnProperty(
    prefix = "integration",
    name = "provider",
    matchIfMissing = true
)
```

Property không tồn tại: match. Property có mặt và bằng false: không match. Các giá trị khác false: match.

Đây là behavior rộng; nếu property là provider name, việc coi mọi chuỗi khác false là hợp lệ có thể không phải điều bạn muốn. Hãy dùng giá trị tường minh khi property đại diện một lựa chọn có tập giá trị.

## 7. Ví dụ feature flag: bật/tắt email integration

Giả sử ứng dụng có interface:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}
```

Implementation dùng email:

```java
public class EmailNotificationSender implements NotificationSender {

    private final MailClient mailClient;

    public EmailNotificationSender(MailClient mailClient) {
        this.mailClient = mailClient;
    }

    @Override
    public void send(String recipient, String message) {
        mailClient.send(recipient, message);
    }
}
```

Cấu hình bean có điều kiện:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class EmailNotificationConfiguration {

    @Bean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(
                properties.host(),
                properties.port(),
                properties.username(),
                properties.password()
        );
    }

    @Bean
    public NotificationSender emailNotificationSender(
            MailClient mailClient) {
        return new EmailNotificationSender(mailClient);
    }
}
```

Khi property bật, cả hai bean trong cấu hình được đăng ký. Khi property tắt hoặc không tồn tại, cấu hình không được áp dụng.

### application.yml

```yaml
notification:
  email:
    enabled: true
```

Tắt tính năng:

```yaml
notification:
  email:
    enabled: false
```

Nếu không khai báo `notification.email.enabled`, `matchIfMissing=false` khiến cấu hình không match.

**Chú ý dependency của consumer:** nếu một service luôn yêu cầu `NotificationSender` bằng constructor, khi email configuration bị tắt và không có implementation nào khác, ứng dụng có thể lỗi vì thiếu bean. Điều kiện hóa producer mà không thiết kế consumer sẽ tạo lỗi startup.

Có thể giải quyết bằng cách cung cấp implementation no-op, điều kiện hóa cả consumer, hoặc inject `ObjectProvider<NotificationSender>` nếu dependency thực sự tùy chọn. Cách phù hợp tùy behavior nghiệp vụ.

## 8. Cung cấp implementation mặc định bằng @ConditionalOnMissingBean

`@ConditionalOnProperty` và `@ConditionalOnMissingBean` thường được dùng cùng nhau trong auto-configuration, nhưng chúng trả lời hai câu hỏi khác nhau:

- `@ConditionalOnProperty`: người dùng đã bật tính năng bằng cấu hình chưa?
- `@ConditionalOnMissingBean`: người dùng đã tự cung cấp bean tương ứng chưa?

Ví dụ một thư viện notification có implementation mặc định:

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "notification.email",
    name = "enabled",
    havingValue = "true"
)
public class EmailNotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    public NotificationSender notificationSender(
            MailClient mailClient) {
        return new EmailNotificationSender(mailClient);
    }
}
```

Khi property bật và chưa có `NotificationSender` do ứng dụng cung cấp, auto-configuration tạo implementation mặc định. Nếu người dùng tự đăng ký một bean `NotificationSender`, điều kiện missing bean không thỏa và bean mặc định back off.

Có thể biểu diễn:

```text
notification.email.enabled == true?
          │
      ┌───┴────┐
     Không     Có
      │         │
      ▼         ▼
 Không tạo   Đã có NotificationSender?
 email bean          │
                 ┌──┴───┐
                Có     Không
                 │       │
                 ▼       ▼
             Dùng bean  Tạo default
             người dùng email bean
```

Kết hợp này phù hợp với starter vì ứng dụng kiểm soát việc bật integration bằng property và vẫn có thể thay implementation mặc định.

## 9. Đặt condition trên class hay trên @Bean method?

Vị trí đặt annotation quyết định phạm vi ảnh hưởng.

### Condition trên configuration class

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "feature",
    name = "analytics",
    havingValue = "true"
)
public class AnalyticsConfiguration {

    @Bean
    public AnalyticsClient analyticsClient() {
        return new AnalyticsClient();
    }

    @Bean
    public AnalyticsService analyticsService(
            AnalyticsClient client) {
        return new AnalyticsService(client);
    }
}
```

Nếu điều kiện không thỏa, configuration class không được áp dụng; cả hai bean method trong class đều không cung cấp bean.

### Condition trên từng method

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "analytics",
        havingValue = "true"
    )
    public AnalyticsClient analyticsClient() {
        return new AnalyticsClient();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "audit",
        havingValue = "true"
    )
    public AuditClient auditClient() {
        return new AuditClient();
    }
}
```

Mỗi bean method có condition độc lập. Có thể bật analytics mà không bật audit.

Tuy nhiên, nếu một bean method luôn cần dependency do một method khác cung cấp theo condition, phải đảm bảo các điều kiện nhất quán. Ví dụ, `AnalyticsService` không nên luôn yêu cầu `AnalyticsClient` nếu client có thể bị tắt.

## 10. Nhiều property: tất cả điều kiện đều phải thỏa

`name` có thể chứa nhiều property:

```java
@ConditionalOnProperty(
    prefix = "app.integration",
    name = {"enabled", "provider"},
    havingValue = "true"
)
```

Cách viết này không phù hợp nếu `enabled` là boolean nhưng `provider` là tên như `stripe`, vì `havingValue` được áp dụng cho từng property. Nếu đặt `havingValue="true"`, cả hai property đều phải có giá trị true.

Muốn diễn đạt hai điều kiện với giá trị khác nhau, hãy dùng các annotation condition riêng hoặc tách configuration class:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "app.integration",
    name = "enabled",
    havingValue = "true"
)
public class IntegrationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "stripe"
    )
    public PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "bank"
    )
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Ở đây:

1. Configuration chỉ được áp dụng nếu integration bật.
2. Chỉ một trong hai bean provider được đăng ký nếu property có giá trị phù hợp.
3. Nếu provider không phải stripe hoặc bank, configuration có thể được nạp nhưng không có gateway bean nào từ hai method đó.

Nếu consumer yêu cầu `PaymentGateway`, cần định nghĩa behavior cho trường hợp provider không hợp lệ hoặc thiếu.

## 11. matchIfMissing với nhiều tên property

Khi khai báo nhiều `name`, tất cả đều phải match. Nếu `matchIfMissing=true`, property thiếu có thể được xem là đạt điều kiện tương ứng; các property có mặt vẫn phải thỏa `havingValue`.

Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "feature",
    name = {"reports", "enabled"},
    havingValue = "true",
    matchIfMissing = true
)
```

Để condition match, mỗi property được liệt kê phải:

- Có giá trị true; hoặc
- Không tồn tại và `matchIfMissing=true`.

Nếu `feature.reports=false`, condition không match dù `feature.enabled` bị thiếu. `matchIfMissing` không ghi đè một giá trị đã tồn tại nhưng không khớp.

Dù hợp lệ, khai báo nhiều property có chung `havingValue` dễ khó đọc nếu các property đại diện loại dữ liệu khác nhau. Nên tách condition hoặc dùng custom condition để mỗi điều kiện có ý nghĩa rõ.

## 12. Property lấy từ đâu?

`@ConditionalOnProperty` kiểm tra property qua Spring `Environment`. Property có thể đến từ nhiều nguồn, chẳng hạn:

- `application.properties`.
- `application.yml`.
- File cấu hình theo profile như `application-prod.yml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Các property source được ứng dụng hoặc test đăng ký.

Ví dụ `application.properties`:

```properties
feature.invoice.enabled=true
```

Ví dụ YAML:

```yaml
feature:
  invoice:
    enabled: true
```

Environment variable trên hệ thống triển khai có thể biểu diễn property theo quy ước relaxed binding của Spring Boot, ví dụ:

```text
FEATURE_INVOICE_ENABLED=true
```

Command line:

```bash
java -jar app.jar --feature.invoice.enabled=true
```

Các nguồn property có thứ tự ưu tiên. Nếu cùng một property xuất hiện trong nhiều nguồn, giá trị hiệu lực phụ thuộc precedence của `Environment`. Khi condition cho kết quả khác mong đợi, hãy kiểm tra **giá trị hiệu lực lúc startup**, không chỉ file cấu hình bạn đang mở.

`@ConditionalOnProperty` được đánh giá trong quá trình xử lý configuration. Thay đổi file cấu hình sau khi context đã khởi tạo không tự động đăng ký hoặc gỡ bean. Muốn thay đổi feature flag runtime cần một thiết kế khác, chẳng hạn dynamic configuration/feature flag service; condition chủ yếu phục vụ quyết định lúc tạo context.

## 13. Property theo profile và condition

Có thể kết hợp `@Profile` và `@ConditionalOnProperty`, nhưng mỗi annotation thể hiện một chiều điều kiện khác nhau:

- `@Profile`: cấu hình chỉ áp dụng khi profile được kích hoạt.
- `@ConditionalOnProperty`: cấu hình chỉ áp dụng khi property có giá trị phù hợp.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment.gateway",
    name = "enabled",
    havingValue = "true"
)
public class ProductionPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new RemotePaymentGateway();
    }
}
```

Cả hai điều kiện đều phải thỏa: profile `prod` active và property `payment.gateway.enabled=true`.

Có thể dùng profile để chọn nhóm cấu hình theo môi trường và property để bật/tắt tính năng trong môi trường đó. Tránh dùng profile thay thế mọi feature flag nếu nhu cầu thực tế là bật/tắt từng tính năng độc lập.

## 14. havingValue là so sánh chuỗi, không phải biểu thức boolean tổng quát

Một property thường được viết như boolean:

```properties
feature.cache.enabled=true
```

Nhưng `@ConditionalOnProperty` kiểm tra property value theo chuỗi. Nó không thực hiện một biểu thức như:

- `count > 10`.
- `provider in (stripe, bank)`.
- `url startsWith https`.
- `enabled == true && region == ap-southeast-1`.

Với những điều kiện phức tạp, có thể:

1. Tách thành nhiều configuration/bean method với các condition đơn giản.
2. Dùng `@ConditionalOnExpression` nếu biểu thức SpEL thực sự phù hợp và dễ bảo trì.
3. Viết custom condition implement `Condition` hoặc dùng `SpringBootCondition` để có logic rõ, thông báo phù hợp.

Không nên dùng SpEL phức tạp chỉ để tránh viết một custom condition nhỏ. Điều kiện đăng ký bean nên dễ hiểu và dễ chẩn đoán.

## 15. Hạn chế với property dạng collection hoặc indexed value

`@ConditionalOnProperty` phù hợp với property đơn như boolean, string hoặc một giá trị scalar. Annotation **không bảo đảm hoạt động đúng để phát hiện một property collection chỉ qua indexed key**.

Ví dụ cấu hình:

```properties
app.servers[0]=server-a
app.servers[1]=server-b
```

Bạn có thể thấy các key `app.servers[0]` và `app.servers[1]`, nhưng không nhất thiết có property gốc `app.servers`. Condition kiểm tra `name = "servers"` có thể không match như mong muốn.

Nếu cần kiểm tra collection/list/map, hãy cân nhắc:

- Bind cấu hình bằng `@ConfigurationProperties`.
- Viết custom `Condition` đọc cấu trúc property phù hợp.
- Dùng một property scalar riêng, ví dụ `app.servers.enabled`, làm cờ bật/tắt.

Đây là giới hạn cần nhớ để không dùng `@ConditionalOnProperty` cho loại dữ liệu mà nó không được thiết kế để kiểm tra.

## 16. Khác nhau giữa @ConditionalOnProperty và @ConditionalOnMissingBean

Hai annotation có thể cùng xuất hiện trong một auto-configuration, nhưng chúng kiểm tra hai nguồn thông tin khác nhau:

| Annotation | Kiểm tra | Câu hỏi |
|---|---|---|
| `@ConditionalOnProperty` | Giá trị trong `Environment` | Người vận hành đã bật cấu hình này chưa? |
| `@ConditionalOnMissingBean` | Bean definitions/beans phù hợp trong context | Ứng dụng đã cung cấp bean thay thế chưa? |
| `@ConditionalOnClass` | Classpath | Thư viện cần thiết có mặt không? |
| `@ConditionalOnBean` | Bean phù hợp đã được đăng ký | Integration phụ thuộc có sẵn chưa? |

Ví dụ auto-configuration cho một client:

```java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
@ConditionalOnProperty(
    prefix = "remote.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public RemoteClient remoteClient(RemoteClientProperties properties) {
        return new RemoteClient(properties.endpoint());
    }
}
```

Điều kiện ở class yêu cầu thư viện có trên classpath và property bật. Điều kiện trên bean method chỉ tạo default client khi ứng dụng chưa có bean `RemoteClient`.

Thứ tự auto-configuration và thời điểm condition được đánh giá có ý nghĩa, đặc biệt với điều kiện dựa trên bean. Khi viết starter, nên tuân theo convention của Spring Boot và kiểm tra report thay vì giả định mọi bean do ứng dụng khai báo luôn được nhìn thấy trong mọi phase.

## 17. Cấu hình property an toàn và dễ vận hành

Feature flag và integration property thường ảnh hưởng đến kết nối ngoài hoặc chi phí vận hành. Nên thiết kế cấu hình rõ ràng:

```yaml
app:
  notification:
    email:
      enabled: false
      host: \${MAIL_HOST:localhost}
      port: \${MAIL_PORT:1025}
```

Ở đây email mặc định tắt. Khi cần bật, người vận hành đặt:

```text
APP_NOTIFICATION_EMAIL_ENABLED=true
MAIL_HOST=smtp.example.net
MAIL_PORT=587
```

Ví dụ dùng placeholder là minh họa cấu hình; secret thực tế nên lấy từ secret manager hoặc môi trường triển khai phù hợp, không commit password vào source repository.

Một số nguyên tắc:

- Đặt default trong tài liệu và cấu hình mẫu.
- Với integration có tác dụng phụ, thường nên mặc định tắt nếu chưa được cấu hình đầy đủ.
- Dùng `havingValue="true"` để chỉ bật khi giá trị boolean rõ ràng.
- Đặt `matchIfMissing` tường minh khi default behavior quan trọng.
- Không nhầm property “được khai báo” với property “đã được xác thực”.
- Validate các giá trị cấu hình bằng `@ConfigurationProperties`/validation khi cần; condition không thay thế validation.

## 18. Kiểm tra behavior bằng test

Có thể dùng `ApplicationContextRunner` để kiểm thử auto-configuration theo từng tổ hợp property. Đây là cách gọn khi viết thư viện hoặc starter.

Ví dụ:

```java
class EmailNotificationAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EmailNotificationAutoConfiguration.class
                    ));

    @Test
    void createsSenderWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "notification.email.enabled=true"
                )
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);
                });
    }

    @Test
    void doesNotCreateSenderWhenDisabled() {
        contextRunner
                .withPropertyValues(
                        "notification.email.enabled=false"
                )
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);
                });
    }

    @Test
    void doesNotCreateSenderWhenPropertyIsMissing() {
        contextRunner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
        });
    }
}
```

Ví dụ giả định có auto-configuration `EmailNotificationAutoConfiguration`, class `NotificationSender`, các dependency và test libraries phù hợp. `ApplicationContextRunner` giúp tạo context nhỏ với property cụ thể mà không phải khởi động cả web server.

Nếu test cấu hình `matchIfMissing=true`, cần thêm test cho trường hợp property không tồn tại và xác nhận bean có mặt. Đừng chỉ test true/false mà bỏ quên trường hợp missing, vì đây chính là khác biệt của thuộc tính này.

### Test với @SpringBootTest

Trong integration test của ứng dụng, có thể ghi property ngay trên test:

```java
@SpringBootTest(properties = {
    "feature.report.enabled=true"
})
class ReportFeatureTests {
    // ...
}
```

Hoặc kiểm tra trường hợp tắt:

```java
@SpringBootTest(properties = {
    "feature.report.enabled=false"
})
class ReportFeatureDisabledTests {
    // ...
}
```

Mỗi test context cần được cấu hình theo property mong muốn. Spring Test có thể cache application contexts theo cấu hình; không nên thay đổi Environment sau khi context đã refresh rồi mong condition được đánh giá lại.

## 19. Debug condition không match

Khi bean không xuất hiện, đừng đoán `havingValue` sai ngay. Hãy kiểm tra theo thứ tự:

1. **Configuration class có được nạp không?** Component scan, import hoặc auto-configuration metadata đã đưa nó vào context chưa?
2. **Tên property có chính xác không?** Ghép `prefix` và `name`, kiểm tra dấu chấm, chính tả và canonical kebab-case.
3. **Property có tồn tại trong Environment không?** File profile, environment variable, command-line và property source precedence có thể làm thay đổi giá trị.
4. **Giá trị thực tế là gì?** `true`, `false`, `enabled`, chuỗi rỗng hay không tồn tại?
5. **`havingValue` đang yêu cầu gì?** Nếu rỗng, mặc định là match mọi giá trị có mặt ngoại trừ false.
6. **`matchIfMissing` có bật không?** Khi property thiếu, behavior có thể ngược với kỳ vọng.
7. **Có nhiều property trong `name` không?** Tất cả phải thỏa.
8. **Condition đặt ở class hay method?** Xác định phạm vi bean bị ảnh hưởng.
9. **Có condition khác cùng chặn không?** `@Profile`, `@ConditionalOnClass`, `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` có thể ảnh hưởng.

### Bật condition evaluation report

Chạy ứng dụng với `--debug`:

```bash
java -jar app.jar --debug
```

Hoặc đặt:

```properties
debug=true
```

Spring Boot có thể in **conditions evaluation report**, cho biết các auto-configuration được áp dụng và không được áp dụng, cùng lý do condition không match.

Nếu điều kiện nằm trên một `@Configuration` thông thường do ứng dụng tự viết, log/report có thể không trình bày chi tiết như với auto-configuration. Khi đó, kiểm tra Environment, cấu hình đã nạp và bean definitions trực tiếp trong test/context.

### Quan sát giá trị property hiệu lực

Trong một runner hoặc debug session, có thể đọc property:

```java
@Component
public class FeaturePropertyInspector implements ApplicationRunner {

    private final Environment environment;

    public FeaturePropertyInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String enabled = environment.getProperty(
                "notification.email.enabled"
        );
        System.out.println("notification.email.enabled = " + enabled);
    }
}
```

Đây là cách quan sát giá trị đã được Environment resolve. Không nên in secret hoặc toàn bộ environment ra log production.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Property là true nhưng bean không có | Sai `prefix`/`name`, cấu hình chưa nạp, hoặc condition khác không thỏa. | Kiểm tra tên đầy đủ, Environment và conditions report. |
| Property là false nhưng cấu hình vẫn match | Với `havingValue` mặc định, false không match; có thể bean đến từ nguồn đăng ký khác. | Tìm các component/configuration khác cũng đăng ký bean cùng type. |
| Không khai báo property nhưng feature vẫn bật | `matchIfMissing=true` hoặc condition khác đăng ký bean. | Xem default có chủ đích không và kiểm tra mọi nguồn bean. |
| `havingValue="true"` nhưng giá trị enabled không match | Property có giá trị khác true, có thể yes, 1, enabled, chuỗi rỗng. | Dùng giá trị canonical true/false hoặc quy định enum rõ ràng. |
| Condition có nhiều property nhưng chỉ một cái được cấu hình | Tất cả property trong `name` phải thỏa. | Bổ sung property còn thiếu hoặc tách điều kiện. |
| Bean bị thiếu làm ứng dụng startup fail | Consumer luôn yêu cầu bean dù feature bị tắt. | Điều kiện hóa consumer, cung cấp no-op bean hoặc dùng provider cho dependency tùy chọn. |
| Collection property không được phát hiện | Annotation không được thiết kế để kiểm tra indexed collection theo cách đó. | Dùng `@ConfigurationProperties` hoặc custom condition. |
| Đổi property lúc runtime nhưng bean không đổi | Condition được đánh giá trong quá trình xây context. | Dùng cơ chế dynamic configuration/feature flag runtime nếu cần. |
| Test pass nhưng production condition khác | Property source, profile hoặc precedence khác nhau. | Kiểm tra giá trị hiệu lực trong đúng môi trường triển khai. |

## 21. Bài tập thực hành

### Bài tập A — Thử havingValue

Tạo bean `ReportClient` với:

```java
@Bean
@ConditionalOnProperty(
    prefix = "feature",
    name = "report",
    havingValue = "true"
)
public ReportClient reportClient() {
    return new ReportClient();
}
```

Thử các property:

- Không khai báo.
- `feature.report=true`.
- `feature.report=false`.
- `feature.report=enabled`.

Ghi lại trường hợp nào bean được đăng ký và giải thích bằng quy tắc `havingValue`.

### Bài tập B — Thử matchIfMissing

Giữ condition trên và lần lượt đặt:

- `matchIfMissing=false`.
- `matchIfMissing=true`.

Chỉ xóa property, không thay giá trị khác. Quan sát sự khác nhau của context khi property missing.

### Bài tập C — Giá trị mặc định rỗng của havingValue

Bỏ thuộc tính `havingValue`. Thử property bằng `true`, `false`, `enabled`, `smtp` và chuỗi rỗng. So sánh với bảng ở phần 4.

### Bài tập D — Hai property cùng lúc

Khai báo `name = {"email.enabled", "email.provider"}` và thử các giá trị. Giải thích vì sao cùng một `havingValue` áp dụng cho cả hai tên có thể không diễn đạt đúng ý định nếu một property là boolean còn một property là provider name.

### Bài tập E — Condition kết hợp với missing bean

Tạo auto-configuration chỉ bật khi `feature.client.enabled=true`, đồng thời chỉ tạo client mặc định khi chưa có bean `Client`. Tự khai báo bean thay thế trong ứng dụng và quan sát cơ chế back-off.

### Bài tập F — Kiểm tra property precedence

Đặt cùng một property trong `application.yml`, profile-specific file và command line với giá trị khác nhau. Chạy ứng dụng và xác định giá trị Environment dùng để đánh giá condition.

## 22. Nguyên tắc cần nhớ

1. **`@ConditionalOnProperty` kiểm tra property trong Spring Environment** để quyết định configuration hoặc bean method có được áp dụng hay không.
2. **`prefix` + `name`** tạo tên property đầy đủ; dùng canonical kebab-case và đặt tên rõ ràng.
3. **`havingValue` mặc định rỗng** có nghĩa property phải tồn tại và không bằng `false`; nếu muốn boolean true rõ ràng, ghi `havingValue="true"`.
4. **`matchIfMissing` mặc định là false**; khi bật true, property không tồn tại được xem là đạt điều kiện.
5. `matchIfMissing=true` không làm giá trị `false` hoặc giá trị sai `havingValue` trở thành hợp lệ.
6. Nếu có nhiều property trong `name`, **tất cả phải match**.
7. Condition trên configuration class ảnh hưởng cả cấu hình; condition trên `@Bean` method chỉ ảnh hưởng bean method đó.
8. `@ConditionalOnProperty` không thay thế `@ConfigurationProperties` validation và không phù hợp để kiểm tra indexed collection.
9. Condition được đánh giá khi xây dựng context; thay đổi property runtime không tự đăng ký/gỡ bean.
10. Khi viết auto-configuration, thường kết hợp property condition với `@ConditionalOnClass` và `@ConditionalOnMissingBean` để cung cấp default có kiểm soát.

Khi sử dụng annotation này, hãy xác định rõ ba điều trước: **property nào được kiểm tra, giá trị nào được chấp nhận và ứng dụng phải làm gì khi property không tồn tại**. Viết tường minh `havingValue` và `matchIfMissing` khi default behavior quan trọng sẽ giúp cấu hình Spring Boot dễ đọc, dễ kiểm thử và dễ vận hành.
