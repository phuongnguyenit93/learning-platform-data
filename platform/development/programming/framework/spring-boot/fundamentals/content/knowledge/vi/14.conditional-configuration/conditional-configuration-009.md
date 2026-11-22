# @ConditionalOnExpression và giới hạn khi biểu thức tham chiếu bean sớm

Trong Spring Boot, một cấu hình có thể chỉ được kích hoạt khi một điều kiện nhất định được thỏa mãn. Ví dụ, ứng dụng chỉ tạo bean gửi email khi tính năng email được bật, chỉ cấu hình tích hợp JDBC khi thư viện JDBC có mặt, hoặc chỉ đăng ký một implementation mặc định khi ứng dụng chưa cung cấp bean thay thế.

`@ConditionalOnExpression` cho phép dùng **Spring Expression Language (SpEL)** để biểu diễn điều kiện dưới dạng biểu thức. Annotation này linh hoạt vì có thể kết hợp property, giá trị boolean, phép so sánh và thậm chí tham chiếu bean trong Spring container.

Chính khả năng tham chiếu bean cũng là giới hạn quan trọng: điều kiện được đánh giá trong quá trình xây dựng application context, trước khi toàn bộ bean đã khởi tạo và hoàn tất mọi bước xử lý. Nếu biểu thức gọi một bean, Spring có thể phải khởi tạo bean đó **quá sớm**. Bean được tạo sớm có thể chưa được áp dụng đầy đủ các BeanPostProcessor, chẳng hạn cơ chế bind `@ConfigurationProperties`. Vì vậy, nên dùng expression chủ yếu với giá trị cấu hình và metadata; tránh dùng bean instance làm nguồn quyết định cấu hình.

## 1. @ConditionalOnExpression dùng để làm gì?

Annotation thuộc package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
~~~

Nó nhận một biểu thức SpEL. Nếu biểu thức đánh giá thành `true`, cấu hình hoặc bean được đánh dấu có thể được đăng ký; nếu kết quả là `false`, Spring bỏ qua phần cấu hình tương ứng.

Ví dụ đơn giản:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("true")
public class DemoConfiguration {

    @Bean
    DemoService demoService() {
        return new DemoService();
    }
}
~~~

Trong ví dụ này điều kiện luôn đúng, nên cấu hình được xét để đăng ký bean `demoService`. Biểu thức hằng chỉ có ý nghĩa minh họa; trong code thực tế, một điều kiện luôn đúng thường không cần annotation.

Điều kiện có thể đặt trên lớp cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
public class AuditConfiguration {
    // Các bean thuộc tính năng audit.
}
~~~

Hoặc trên một phương thức `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class IntegrationConfiguration {

    @Bean
    @ConditionalOnExpression("${app.integration.partner:false}")
    PartnerClient partnerClient() {
        return new PartnerClient();
    }
}
~~~

Khi điều kiện trên lớp không thỏa, cấu hình lớp đó không đóng góp các bean của nó. Khi điều kiện trên phương thức không thỏa, bean do phương thức đó khai báo không được đăng ký.

## 2. SpEL và property placeholder trong biểu thức

`@ConditionalOnExpression` dùng SpEL để đánh giá giá trị. Spring Boot cũng phân giải property placeholder dạng `${...}` trong biểu thức trước khi đánh giá.

### 2.1. Kiểm tra một property boolean

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

Trong `application.yml`:

~~~yaml
app:
  feature:
    audit: true
~~~

Placeholder `${app.feature.audit:false}` được thay bằng giá trị property. Nếu property không tồn tại, giá trị mặc định sau dấu hai chấm là `false`. Sau khi phân giải, SpEL đánh giá biểu thức boolean.

### 2.2. So sánh chuỗi

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "'${app.environment:local}' == 'production'"
)
class ProductionIntegrationConfiguration {
}
~~~

Trong biểu thức này:

- Dấu nháy đơn bao quanh giá trị placeholder để tạo một chuỗi SpEL.
- Toán tử `==` so sánh chuỗi với `production`.
- Nếu property thiếu, mặc định là `local` nên điều kiện sai.

Ví dụ cấu hình:

~~~yaml
app:
  environment: production
~~~

### 2.3. Kết hợp điều kiện

SpEL hỗ trợ các toán tử logic như `and`, `or` và `not`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "${app.feature.audit:false} and '${app.environment:local}' == 'production'"
)
class ProductionAuditConfiguration {
}
~~~

Biểu thức chỉ đúng khi audit được bật và môi trường là production.

Với những điều kiện property đơn giản, `@ConditionalOnProperty` thường dễ đọc và ít rủi ro hơn. Không nên chọn SpEL chỉ vì có thể viết nhiều phép logic trên một dòng; điều kiện càng phức tạp càng khó đọc, kiểm thử và chẩn đoán.

## 3. Tham chiếu bean trong SpEL có cú pháp gì?

Trong SpEL, có thể tham chiếu bean trong BeanFactory bằng ký hiệu `@beanName`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.auditEnabled")
class AuditConfiguration {
}
~~~

Hoặc gọi phương thức:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.isAuditEnabled()")
class AuditConfiguration {
}
~~~

Giả sử ứng dụng có bean:

~~~java
@Component("featureSwitches")
public class FeatureSwitches {

    public boolean isAuditEnabled() {
        return true;
    }
}
~~~

> Khi biểu thức được đánh giá, SpEL cần resolve tên `featureSwitches` qua BeanFactory và gọi phương thức trên instance. Điều đó có thể khiến Spring khởi tạo bean này ngay trong giai đoạn đánh giá điều kiện.

Đây là điểm khác biệt giữa hai loại biểu thức:

~~~text
Property expression:
    ${app.feature.audit:false}
             |
             v
       Environment
             |
             v
        true / false

Bean expression:
    @featureSwitches.isAuditEnabled()
             |
             v
       BeanFactory resolve bean
             |
             v
       Có thể khởi tạo instance sớm
             |
             v
       Gọi method trên instance
~~~

Tham chiếu bean không chỉ đọc metadata của bean definition. Nó yêu cầu một **bean instance** để đánh giá biểu thức. Vì vậy, không nên dùng một bean nghiệp vụ làm công tắc cấu hình cho một cấu hình khác.

## 4. Điều kiện được đánh giá khi nào?

Spring xử lý configuration class và các điều kiện trong quá trình xây dựng application context. Những quyết định này diễn ra trước khi toàn bộ singleton thông thường được khởi tạo và trước khi ứng dụng hoàn tất startup.

Luồng khái quát:

~~~text
SpringApplication.run(...)
        |
        v
Chuẩn bị Environment và BeanFactory
        |
        v
Đọc, phân tích configuration classes
        |
        v
Đánh giá các điều kiện @Conditional
        |
        v
Đăng ký các bean definitions thỏa điều kiện
        |
        v
Đăng ký và chạy các BeanFactory/BeanPostProcessor
        |
        v
Khởi tạo các singleton eager
        |
        v
Context refresh hoàn tất
        |
        v
Ứng dụng sẵn sàng
~~~

Sơ đồ là trình tự khái quát; Spring có nhiều giai đoạn xử lý cấu hình và đăng ký processor chi tiết hơn. Điều quan trọng là **condition không đợi toàn bộ ứng dụng chạy ổn định mới được đánh giá**.

Nếu condition tham chiếu bean, BeanFactory phải cung cấp instance để SpEL gọi thuộc tính/phương thức. Việc tạo instance đó có thể xảy ra trong giai đoạn cấu hình còn đang được phân tích và đăng ký.

## 5. Vì sao tham chiếu bean sớm nguy hiểm?

Spring Boot cảnh báo việc tham chiếu bean trong `@ConditionalOnExpression` có giới hạn đáng kể. Bean bị khởi tạo rất sớm và có thể không còn đủ điều kiện để được xử lý bởi tất cả BeanPostProcessor.

### 5.1. BeanPostProcessor có thể chưa áp dụng đầy đủ

Spring dùng BeanPostProcessor để bổ sung hành vi cho bean, ví dụ xử lý annotation, tạo proxy AOP hoặc hỗ trợ các cơ chế cấu hình. Một bean bị khởi tạo trước khi toàn bộ processor được đăng ký có thể bị bỏ qua một số bước xử lý.

Một ví dụ đáng chú ý là `@ConfigurationProperties` binding. Nếu bean được khởi tạo sớm do biểu thức condition tham chiếu đến nó, bean có thể chưa được xử lý bởi processor thực hiện binding như kỳ vọng. Kết quả là thuộc tính vẫn giữ giá trị mặc định hoặc trạng thái chưa hoàn chỉnh tại thời điểm condition đọc bean.

Không nên hiểu rằng mọi bean tham chiếu sớm chắc chắn mất tất cả BeanPostProcessor. Vấn đề phụ thuộc thứ tự đăng ký và loại processor; rủi ro nằm ở việc không thể bảo đảm bean được xử lý đầy đủ như một bean được khởi tạo đúng giai đoạn.

### 5.2. Gọi method khi trạng thái chưa hoàn tất

Giả sử:

~~~java
@Component
@ConfigurationProperties(prefix = "app.features")
public class FeatureSwitches {
    private boolean auditEnabled;

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
~~~

Và:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.auditEnabled")
class AuditConfiguration {
}
~~~

Nếu `featureSwitches` bị khởi tạo sớm trước khi configuration-properties binding được áp dụng, biểu thức có thể đọc giá trị mặc định `false` dù file cấu hình đặt `app.features.audit=true`. Condition khi đó đưa ra quyết định dựa trên trạng thái chưa được bind.

Đây là ví dụ về rủi ro timing, không phải kết quả tất yếu trong mọi phiên bản/cấu hình. Cách đúng là condition đọc trực tiếp property từ `Environment` bằng `@ConditionalOnProperty` hoặc một custom Condition không khởi tạo bean.

### 5.3. Gây khởi tạo sớm cả chuỗi dependency

Một bean được tham chiếu có thể phụ thuộc vào nhiều bean khác:

~~~text
@ConditionalOnExpression("@featureSwitches.enabled")
                    |
                    v
             FeatureSwitches
                    |
                    v
              RemoteConfigClient
                    |
                    v
               HTTP client
                    |
                    v
         cấu hình kết nối / credentials
~~~

Chỉ để đánh giá một condition, Spring có thể phải khởi tạo cả chuỗi dependency. Điều này có thể:

- Làm startup chậm hơn.
- Kích hoạt kết nối mạng hoặc thao tác I/O quá sớm.
- Khiến một lỗi cấu hình dịch vụ ngoài làm context thất bại trước khi cấu hình chính hoàn tất.
- Làm thứ tự khởi tạo khó dự đoán.

Condition nên là phép quyết định nhẹ dựa trên cấu hình và metadata, không nên là nơi chạy nghiệp vụ hoặc khởi tạo client bên ngoài.

### 5.4. Tạo vòng phụ thuộc hoặc phụ thuộc vào cấu hình chưa được đăng ký

Ví dụ, bean `featureSwitches` lại cần một service chỉ được đăng ký trong `AuditConfiguration`, trong khi `AuditConfiguration` chỉ được kích hoạt khi biểu thức gọi `featureSwitches`. Đây là quan hệ vòng:

~~~text
AuditConfiguration cần đánh giá condition
             |
             v
   Tạo FeatureSwitches
             |
             v
 FeatureSwitches cần AuditService
             |
             v
 AuditService chỉ tồn tại nếu AuditConfiguration được bật
~~~

Spring không thể giải quyết một quyết định điều kiện phụ thuộc vào bean mà chính điều kiện đó mới cho phép đăng ký. Kết quả có thể là lỗi không tìm thấy bean, lỗi tạo bean hoặc lỗi khởi tạo context.

Ngoài ra, condition được đánh giá khi một phần cấu hình có thể chưa được đăng ký. Không nên tham chiếu bean chỉ được khai báo trong một cấu hình chưa được xử lý tại thời điểm đó.

### 5.5. Condition không phải feature toggle runtime

`@ConditionalOnExpression` quyết định cấu hình/bean definition trong quá trình tạo context. Nó không tự theo dõi biểu thức sau khi ứng dụng chạy.

Nếu property đổi từ `false` thành `true` sau khi context đã refresh, cấu hình bị bỏ qua không tự động xuất hiện chỉ vì giá trị mới. Nếu cần bật/tắt tính năng theo thời gian chạy, hãy kiểm tra feature flag trong service hoặc dùng một cơ chế refresh/configuration chuyên biệt với semantics rõ ràng.

## 6. Cách ưu tiên: @ConditionalOnProperty cho điều kiện cấu hình

Nếu điều kiện chỉ phụ thuộc vào property, hãy dùng `@ConditionalOnProperty`:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

Cấu hình:

~~~yaml
app:
  feature:
    audit: true
~~~

Spring kiểm tra property trong Environment, không cần khởi tạo bean `FeatureSwitches` để đọc cờ này.

Một số thuộc tính quan trọng:

- `prefix`: tiền tố của property.
- `name`: một hoặc nhiều tên property cần kiểm tra.
- `havingValue`: giá trị cần khớp.
- `matchIfMissing`: có coi property bị thiếu là điều kiện đúng hay không.

Nếu không đặt `havingValue`, điều kiện mặc định thường khớp khi property có mặt và giá trị không phải chuỗi `false` (không phân biệt hoa thường). Để hành vi rõ ràng, đặc biệt với boolean feature flag, nên đặt `havingValue = "true"`.

### 6.1. Giá trị mặc định khi thiếu property

~~~java
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true",
        matchIfMissing = false
)
~~~

Với cấu hình này, nếu property thiếu thì condition không khớp. Có thể đặt `matchIfMissing = true` nếu thiết kế yêu cầu bật mặc định khi không khai báo; hãy chọn rõ chính sách thay vì dựa vào mặc định không được giải thích.

### 6.2. Nhiều property

~~~java
@ConditionalOnProperty(
        prefix = "app.integration",
        name = {"partner-enabled", "credentials-present"},
        havingValue = "true"
)
~~~

Khi khai báo nhiều tên, các điều kiện property được kiểm tra theo quan hệ AND: tất cả phải thỏa. Nếu cần logic OR hoặc biểu thức phức tạp, cân nhắc cấu hình lồng nhau, custom Condition hoặc SpEL chỉ khi thật sự cần; đừng chuyển sang tham chiếu bean để làm điều đó.

Lưu ý, `@ConditionalOnProperty` không phù hợp để kiểm tra chắc chắn sự tồn tại của property dạng collection/index như `app.values[0]`. Với cấu trúc cấu hình phức tạp, custom Condition đọc Environment hoặc binding metadata thích hợp có thể rõ ràng hơn.

## 7. Dùng điều kiện chuyên biệt thay cho một biểu thức tổng hợp

Spring Boot cung cấp nhiều annotation condition mô tả trực tiếp mục đích:

| Nhu cầu | Annotation phù hợp | Điều nó kiểm tra |
|---|---|---|
| Property bật/tắt | `@ConditionalOnProperty` | Giá trị trong Environment |
| Có thư viện/class trên classpath | `@ConditionalOnClass` | Sự hiện diện của class |
| Không có class cụ thể | `@ConditionalOnMissingClass` | Class không tồn tại |
| Đã có bean phù hợp | `@ConditionalOnBean` | Bean definition/ứng viên trong BeanFactory |
| Chưa có bean phù hợp | `@ConditionalOnMissingBean` | Chưa có bean thỏa điều kiện |
| Ứng dụng Servlet hoặc Reactive | `@ConditionalOnWebApplication` | Loại web application |
| Không phải ứng dụng web | `@ConditionalOnNotWebApplication` | Loại ứng dụng |
| Profile đang hoạt động | `@Profile` | Active profiles |

Ví dụ kiểm tra một dependency có mặt:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.audit.AuditClient")
class VendorAuditConfiguration {
    // Cấu hình chỉ có ý nghĩa khi thư viện client hiện diện.
}
~~~

Ví dụ chỉ cung cấp implementation mặc định nếu ứng dụng chưa có bean:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultPaymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

`@ConditionalOnBean` và `@ConditionalOnMissingBean` được thiết kế để đánh giá sự hiện diện của bean trong cấu hình, thay vì gọi method trên một bean instance. Với auto-configuration, thứ tự cấu hình và điều kiện cũng quan trọng: Boot cung cấp cơ chế sắp xếp auto-configuration để những bean nền tảng có thể được đăng ký trước khi điều kiện phụ thuộc vào chúng được xét.

## 8. Khi nào thật sự cần @ConditionalOnExpression?

`@ConditionalOnExpression` có ích khi một điều kiện SpEL ngắn gọn diễn đạt được logic mà các annotation chuyên biệt không biểu đạt thuận tiện, chẳng hạn kết hợp nhiều giá trị property:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "${app.features.audit:false} and '${app.region:local}' matches 'prod|staging'"
)
class RegionalAuditConfiguration {
}
~~~

Biểu thức này chỉ dùng giá trị property từ Environment. Không có bean instance nào cần được khởi tạo để tính điều kiện.

Trước khi dùng, hãy cân nhắc:

1. Có thể viết bằng `@ConditionalOnProperty` hay không?
2. Có thể tách thành nhiều điều kiện chuyên biệt để người đọc hiểu rõ hơn không?
3. Biểu thức có phụ thuộc property ngoài dự kiến hoặc thiếu default không?
4. Có bảo đảm kết quả là boolean không?
5. Có thể kiểm thử cả nhánh true/false một cách độc lập không?

Tránh biểu thức dài, nhiều phép gọi method hoặc logic nghiệp vụ. Condition là quyết định đăng ký bean, không phải nơi thay thế service layer.

## 9. Nếu cần điều kiện phức tạp, viết custom Condition

Khi logic không thể biểu đạt rõ bằng annotation có sẵn, có thể triển khai `Condition`. Custom condition nhận `ConditionContext` và `AnnotatedTypeMetadata`, nhờ đó đọc Environment và metadata cấu hình.

Ví dụ kiểm tra hai property mà không tra cứu bean instance:

~~~java
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class ProductionAuditCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String environment = context.getEnvironment()
                .getProperty("app.environment", "local");
        boolean auditEnabled = context.getEnvironment()
                .getProperty("app.feature.audit", Boolean.class, false);

        return auditEnabled && "production".equals(environment);
    }
}
~~~

Gắn condition:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(ProductionAuditCondition.class)
class ProductionAuditConfiguration {
}
~~~

Custom Condition giúp đặt logic có tên và kiểm thử riêng. Trong `matches()`, ưu tiên đọc Environment, classpath và metadata/bean definitions thông qua các API phù hợp. **Không gọi `context.getBeanFactory().getBean(...)` để lấy bean instance**; việc đó lặp lại rủi ro khởi tạo sớm mà bài học đang đề cập.

Nếu condition cần biết có bean definition, hãy sử dụng API metadata của BeanFactory/registry phù hợp và lưu ý giai đoạn condition được đánh giá. Không cần khởi tạo instance chỉ để biết bean definition có tồn tại.

## 10. So sánh các cách viết cùng một ý định

Giả sử yêu cầu là chỉ đăng ký `AuditPublisher` khi `app.feature.audit=true`.

**Cách nên dùng:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "audit",
        havingValue = "true"
)
class AuditConfiguration {
    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

**Cách có thể chạy nhưng không cần thiết:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("${app.feature.audit:false}")
class AuditConfiguration {
}
~~~

**Cách nên tránh:**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression("@featureSwitches.isAuditEnabled()")
class AuditConfiguration {
}
~~~

Ở cách cuối, condition cần một bean instance để gọi method. Nếu bean đó có binding, AOP, dependency hoặc side effect khởi tạo, kết quả có thể phụ thuộc thứ tự startup. Hai cách đầu dựa trên property nên không cần khởi tạo bean công tắc.

## 11. Nếu cần bật/tắt tính năng khi ứng dụng đang chạy

Condition không phải cơ chế feature flag động. Nếu yêu cầu là một thao tác có thể thay đổi kết quả theo thời gian, hãy để bean luôn được đăng ký và kiểm tra trạng thái tại thời điểm thực hiện nghiệp vụ:

~~~java
@Service
public class AuditService {
    private final FeatureFlagService featureFlags;
    private final AuditPublisher publisher;

    public AuditService(
            FeatureFlagService featureFlags,
            AuditPublisher publisher) {
        this.featureFlags = featureFlags;
        this.publisher = publisher;
    }

    public void record(AuditEvent event) {
        if (!featureFlags.isEnabled("audit")) {
            return;
        }
        publisher.publish(event);
    }
}
~~~

Trong thiết kế này, `FeatureFlagService` là dependency runtime bình thường. Mỗi lần `record()` được gọi, service đọc trạng thái hiện hành theo semantics của feature flag provider. Cơ chế cache, refresh và đồng bộ giá trị do hệ thống feature flag quyết định.

Nếu chỉ dùng `@ConditionalOnProperty` hoặc `@ConditionalOnExpression`, bean definition được quyết định khi context xây dựng. Đổi property sau đó không tự đăng ký hoặc gỡ bean khỏi context. Muốn thay đổi cấu trúc context cần một cơ chế refresh/restart được thiết kế rõ ràng; không nên kỳ vọng annotation condition tự quan sát thay đổi.

## 12. Kiểm thử điều kiện và hành vi startup

Điều kiện cấu hình nên được kiểm tra ở cả nhánh bật và tắt. Với Spring Boot, `ApplicationContextRunner` là công cụ hữu ích để kiểm thử auto-configuration hoặc cấu hình có điều kiện mà không phải khởi động toàn bộ ứng dụng.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AuditConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(AuditConfiguration.class);

    @Test
    void registersAuditPublisherWhenEnabled() {
        contextRunner
                .withPropertyValues("app.feature.audit=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditPublisher.class));
    }

    @Test
    void skipsAuditPublisherWhenDisabled() {
        contextRunner
                .withPropertyValues("app.feature.audit=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditPublisher.class));
    }
}
~~~

Ví dụ giả định `AuditConfiguration` sử dụng `@ConditionalOnProperty` như phần trước và `AuditPublisher` có thể được khởi tạo độc lập.

Với `@ConditionalOnExpression`, có thể tạo các test tương tự để kiểm tra property, phép so sánh chuỗi và toán tử logic. Nếu biểu thức tham chiếu bean, hãy kiểm tra thêm thứ tự khởi tạo và BeanPostProcessor liên quan; nhưng hướng sửa tốt hơn thường là bỏ tham chiếu bean khỏi condition.

### Kiểm tra lỗi SpEL

Các lỗi phổ biến:

- Biểu thức sai cú pháp SpEL.
- Placeholder không tồn tại và không có giá trị mặc định phù hợp.
- Chuỗi không được đặt trong dấu nháy đúng cách.
- Biểu thức trả về kiểu không thể chuyển thành boolean.
- Bean được tham chiếu không tồn tại hoặc không thể khởi tạo.

Khi lỗi xảy ra, xem nguyên nhân gốc trong log khởi động. Không nên mặc định mọi biểu thức không hợp lệ sẽ được coi là `false`; lỗi parse hoặc resolve có thể làm quá trình xây dựng context thất bại.

## 13. Chẩn đoán condition trong Spring Boot

Spring Boot có thể in **Condition Evaluation Report** khi chạy ứng dụng với `--debug` hoặc cấu hình `debug=true`:

~~~properties
debug=true
~~~

Báo cáo cho biết các auto-configuration/condition được match hay không match và thường kèm lý do. Điều này giúp trả lời:

- Cấu hình có được xét không?
- Điều kiện property có đúng không?
- Class yêu cầu có trên classpath không?
- Bean cần thiết đã được đăng ký theo điều kiện hay chưa?
- Auto-configuration có bị exclude không?

Đối với `@ConditionalOnExpression` trên cấu hình ứng dụng, log khởi động và lỗi SpEL có thể cung cấp thông tin về biểu thức không đánh giá được. Nếu cần xác nhận bean nào đã được đăng ký, có thể quan sát `ApplicationContext` hoặc Actuator endpoint `conditions`/`beans` khi đã bật và bảo vệ endpoint thích hợp.

Condition report không thay thế kiểm thử. Một condition được match chỉ cho biết điều kiện cấu hình được đáp ứng; bean vẫn có thể thất bại khi khởi tạo vì dependency hoặc kết nối bên ngoài.

## 14. Nguyên tắc sử dụng an toàn

1. Dùng `@ConditionalOnExpression` cho biểu thức SpEL ngắn gọn dựa trên property/giá trị đơn giản khi annotation chuyên biệt chưa đủ diễn đạt.
2. Dùng `@ConditionalOnProperty` cho feature flag và cấu hình boolean; khai báo default và `havingValue` rõ ràng.
3. Dùng `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean` và `@Profile` đúng mục đích thay vì gom mọi thứ vào một expression.
4. Tránh tham chiếu `@beanName` trong condition. Bean có thể bị khởi tạo sớm, trước khi tất cả BeanPostProcessor đã sẵn sàng.
5. Không gọi service nghiệp vụ, truy cập database hoặc dịch vụ mạng để quyết định có đăng ký một cấu hình hay không.
6. Nếu cần logic điều kiện phức tạp, viết custom `Condition` dựa trên Environment, classpath và metadata; không gọi `getBean()` trong `matches()`.
7. Nếu cần feature toggle khi runtime, kiểm tra cờ trong service ở thời điểm thao tác thay vì dùng condition để tạo/gỡ bean động.
8. Kiểm thử cả trường hợp điều kiện đúng, sai, thiếu property và cấu hình bean thay thế.

`@ConditionalOnExpression` giúp diễn đạt điều kiện cấu hình linh hoạt bằng SpEL, nhưng cần nhớ nó được đánh giá trong lúc Spring xây dựng application context. Một biểu thức chỉ đọc property từ Environment thường có thể dự đoán được; biểu thức gọi `@beanName` có thể ép Spring tạo bean quá sớm trong giai đoạn cấu hình và khiến bean chưa được xử lý đầy đủ bởi các BeanPostProcessor. Với đa số cấu hình ứng dụng, hãy ưu tiên condition chuyên biệt hoặc property-based condition để việc đăng ký bean rõ ràng, ổn định và dễ kiểm thử.
