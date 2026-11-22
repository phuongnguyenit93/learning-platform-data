# Điều kiện lớp ngoài và điều kiện trên từng bean

Trong Spring Boot, một auto-configuration thường đăng ký nhiều bean có liên quan. Có bean chỉ cần khi thư viện tích hợp xuất hiện, có bean chỉ cần khi một property được bật, và có bean mặc định chỉ nên được tạo nếu ứng dụng chưa tự cung cấp implementation.

Spring Boot cho phép đặt điều kiện ở hai phạm vi quan trọng:

- **Điều kiện trên configuration class**: quyết định cả cấu hình có được xử lý hay không. Nếu điều kiện không thỏa, các phương thức @Bean và cấu hình nằm trong class đó không được đưa vào context theo nhánh cấu hình ấy.
- **Điều kiện trên từng phương thức @Bean**: quyết định riêng bean được khai báo bởi phương thức đó có được đăng ký hay không. Các bean khác trong cùng configuration class vẫn có thể được đăng ký.

Hiểu đúng phạm vi giúp tránh hai lỗi thiết kế phổ biến: tắt cả một nhóm cấu hình chỉ vì một bean tùy chọn không cần thiết, hoặc vô tình đăng ký một phần cấu hình khi điều kiện chung của tích hợp chưa thỏa.

## 1. Bắt đầu từ một auto-configuration có nhiều bean

Giả sử thư viện cung cấp tích hợp cho hệ thống đối tác. Nó có thể đăng ký:

- Một PartnerClient để gọi API đối tác.
- Một PartnerService dùng client đó.
- Một PartnerHealthIndicator để kiểm tra trạng thái tích hợp.
- Một PartnerMetricsCollector để thu thập metric nếu người dùng bật tính năng.

Không phải ứng dụng nào cũng dùng tất cả thành phần. Ta muốn:

1. Chỉ bật tích hợp khi thư viện client có trên classpath và property tổng thể cho phép.
2. Cho phép ứng dụng thay thế PartnerService mặc định.
3. Chỉ tạo health indicator khi health integration được bật.
4. Chỉ tạo metrics collector khi metrics được bật.

Một cách nhìn khái niệm:

~~~text
PartnerAutoConfiguration
        │
        ├── Điều kiện chung của cả cấu hình
        │       ├── SDK có trên classpath?
        │       └── partner.enabled = true?
        │
        ├── PartnerService
        │       └── Chưa có bean do ứng dụng cung cấp?
        │
        ├── PartnerHealthIndicator
        │       └── partner.health.enabled = true?
        │
        └── PartnerMetricsCollector
                └── partner.metrics.enabled = true?
~~~

Điều kiện chung đặt ở configuration class tạo thành **cổng ngoài**. Các điều kiện trên phương thức @Bean tạo thành **cổng riêng** cho từng bean.

## 2. Điều kiện ở cấp configuration class

Trong Spring Boot 3, auto-configuration thường được khai báo bằng **@AutoConfiguration**. Annotation này đóng vai trò một configuration class được Boot phát hiện qua cơ chế đăng ký auto-configuration.

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    // Các phương thức @Bean thuộc cấu hình này.
}
~~~

Điều kiện trên class yêu cầu property **partner.enabled** có giá trị true. Nếu property không tồn tại hoặc có giá trị khác, class cấu hình không được áp dụng theo điều kiện này.

Nếu configuration class bị loại, các phương thức @Bean bên trong không được xử lý để đăng ký bean từ cấu hình đó. Đây là phạm vi ảnh hưởng rộng hơn so với điều kiện đặt trên một phương thức riêng lẻ.

### 2.1. Một điều kiện ngoài có thể kiểm soát toàn bộ nhóm bean

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Bean
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(properties.getBaseUrl());
    }

    @Bean
    PartnerService partnerService(PartnerClient client) {
        return new PartnerService(client);
    }

    @Bean
    PartnerHealthIndicator partnerHealthIndicator(PartnerClient client) {
        return new PartnerHealthIndicator(client);
    }
}
~~~

Ví dụ minh họa một tích hợp trong đó cả ba bean đều cần SDK và chỉ hoạt động khi partner.enabled được bật. Điều kiện class-level giúp tránh đăng ký toàn bộ nhóm khi SDK không có mặt hoặc tính năng bị tắt.

Nếu bất kỳ điều kiện class-level nào không thỏa, toàn bộ cấu hình này bị bỏ qua. Không có riêng PartnerClient, PartnerService hay PartnerHealthIndicator được đăng ký từ class này.

### 2.2. Nhiều điều kiện trên cùng một class được kết hợp

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnProperty(
        prefix = "partner",
        name = "mode",
        havingValue = "remote"
)
public class PartnerAutoConfiguration {
    // ...
}
~~~

Các điều kiện đều phải thỏa để cấu hình được áp dụng. Có thể hiểu logic:

~~~text
PartnerClient có mặt
        AND
partner.enabled = true
        AND
partner.mode = remote
        │
        ▼
Áp dụng PartnerAutoConfiguration
~~~

Nếu một điều kiện không thỏa, toàn bộ configuration class bị bỏ qua. Đây là cách phù hợp khi các điều kiện đều là yêu cầu bắt buộc cho mọi bean trong cấu hình.

### 2.3. Khi nào nên đặt điều kiện ở class?

Đặt condition ở cấp class khi:

- Mọi bean trong cấu hình đều cần cùng một thư viện tùy chọn.
- Mọi bean đều chỉ có ý nghĩa khi một feature tổng thể được bật.
- Một cấu hình chỉ phù hợp với một loại ứng dụng hoặc môi trường nhất định.
- Muốn loại bỏ toàn bộ một nhóm auto-configuration khi điều kiện nền không thỏa.

Ví dụ, nếu mọi bean trong PartnerAutoConfiguration đều gọi PartnerClient, việc SDK không có mặt là lý do hợp lý để bỏ qua toàn bộ class.

Không nên đặt điều kiện quá rộng nếu trong cùng class còn có bean độc lập với điều kiện đó. Khi ấy một điều kiện class-level có thể vô tình chặn cả những bean vẫn hữu ích.

## 3. Điều kiện trên từng phương thức @Bean

Điều kiện trên một phương thức @Bean chỉ quyết định bean do phương thức đó tạo ra.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PartnerFeatureAutoConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    PartnerHealthIndicator partnerHealthIndicator() {
        return new PartnerHealthIndicator();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    PartnerMetricsCollector partnerMetricsCollector() {
        return new PartnerMetricsCollector();
    }
}
~~~

Trong ví dụ này:

- PartnerService luôn được khai báo nếu class cấu hình được áp dụng.
- PartnerHealthIndicator chỉ được đăng ký khi property health được bật.
- PartnerMetricsCollector chỉ được đăng ký khi property metrics được bật.

Nếu partner.metrics.enabled là false, chỉ bean metrics bị bỏ qua. PartnerService và PartnerHealthIndicator vẫn có thể tồn tại nếu các điều kiện riêng của chúng thỏa.

### 3.1. Phạm vi ảnh hưởng của method condition

~~~text
PartnerFeatureAutoConfiguration được áp dụng
        │
        ├── partnerService()
        │       └── Không có method condition
        │               └── Đăng ký bean
        │
        ├── partnerHealthIndicator()
        │       └── health.enabled = true?
        │               ├── Có → Đăng ký bean
        │               └── Không → Bỏ qua bean này
        │
        └── partnerMetricsCollector()
                └── metrics.enabled = true?
                        ├── Có → Đăng ký bean
                        └── Không → Bỏ qua bean này
~~~

Đây là điểm khác biệt cốt lõi: method-level condition không tự động tắt các phương thức @Bean còn lại trong cùng class.

### 3.2. Khi nào nên đặt điều kiện trên method?

Đặt condition trên từng phương thức @Bean khi:

- Các bean trong cùng cấu hình có yêu cầu khác nhau.
- Một bean là tính năng bổ sung, có thể bật/tắt độc lập.
- Chỉ một bean phụ thuộc vào một bean khác.
- Một bean mặc định chỉ nên tồn tại nếu người dùng chưa tự cung cấp.
- Muốn tránh việc một property nhỏ làm mất toàn bộ nhóm bean.

Method-level condition giúp cấu hình có tính mô-đun hơn, vì mỗi bean có thể có chính sách đăng ký riêng.

## 4. So sánh trực tiếp class-level và method-level

| Tiêu chí | Condition trên configuration class | Condition trên @Bean method |
|---|---|---|
| Phạm vi | Toàn bộ configuration class và cấu hình được xử lý từ class đó | Chỉ bean do method đó khai báo |
| Khi không match | Bỏ qua cấu hình ở cấp class | Bỏ qua bean tương ứng |
| Các method @Bean khác | Không được đăng ký từ cấu hình bị loại | Vẫn có thể được đăng ký |
| Trường hợp phù hợp | Điều kiện nền chung cho mọi bean trong nhóm | Điều kiện riêng cho từng tính năng/bean |
| Ví dụ | SDK bắt buộc cho toàn bộ tích hợp | Chỉ bật metrics khi property metrics bật |
| Rủi ro khi đặt sai | Tắt quá nhiều bean | Đăng ký bean phụ thuộc trong khi điều kiện nền chưa được bảo vệ |

Không có quy tắc rằng class-level luôn tốt hơn hoặc method-level luôn tốt hơn. Hãy đặt điều kiện ở phạm vi nhỏ nhất vẫn diễn đạt đúng yêu cầu cấu hình.

## 5. Kết hợp điều kiện class-level và method-level

Một auto-configuration thực tế thường dùng cả hai. Điều kiện lớp ngoài xác nhận tích hợp có thể hoạt động; điều kiện trên từng bean quyết định những phần nào được đăng ký.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    PartnerService partnerService(PartnerClient client) {
        return new PartnerService(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    PartnerHealthIndicator partnerHealthIndicator(PartnerClient client) {
        return new PartnerHealthIndicator(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    PartnerMetricsCollector partnerMetricsCollector(PartnerClient client) {
        return new PartnerMetricsCollector(client);
    }
}
~~~

Trong ví dụ:

1. SDK phải có trên classpath.
2. partner.enabled phải là true.
3. PartnerService mặc định chỉ được tạo nếu chưa có bean phù hợp.
4. Health indicator và metrics collector được bật độc lập theo property của chúng.

Nếu điều kiện class-level không thỏa, không bean nào từ cấu hình này được đăng ký, bất kể các property cấp method có giá trị gì.

Nếu điều kiện class-level thỏa, Spring tiếp tục xét điều kiện của từng phương thức @Bean.

## 6. @ConditionalOnMissingBean thường nên đặt ở đâu?

Một mục tiêu phổ biến của auto-configuration là cung cấp bean mặc định nhưng cho phép ứng dụng tự thay thế. Đây là trường hợp điển hình của **@ConditionalOnMissingBean**.

Ví dụ:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Nếu ứng dụng đã đăng ký GreetingService, bean mặc định không được tạo. Nếu chưa có, Boot cung cấp DefaultGreetingService.

### 6.1. Vì sao thường đặt @ConditionalOnMissingBean trên từng method?

Giả sử một configuration class cung cấp ba bean:

- GreetingService.
- GreetingFormatter.
- GreetingMetrics.

Ứng dụng muốn tự cung cấp GreetingService nhưng vẫn dùng formatter và metrics mặc định.

Nếu đặt:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingAutoConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    GreetingMetrics greetingMetrics() {
        return new DefaultGreetingMetrics();
    }
}
~~~

Khi ứng dụng có GreetingService riêng, **toàn bộ GreetingAutoConfiguration** bị loại. Formatter và metrics mặc định cũng không được đăng ký, dù chúng không nhất thiết phải nhường chỗ.

Thông thường, ý định đúng là:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    @ConditionalOnMissingBean(GreetingFormatter.class)
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    @ConditionalOnMissingBean(GreetingMetrics.class)
    GreetingMetrics greetingMetrics() {
        return new DefaultGreetingMetrics();
    }
}
~~~

Khi ứng dụng tự cung cấp GreetingService, chỉ bean mặc định GreetingService bị bỏ qua. Hai bean khác vẫn có thể được đăng ký.

### 6.2. Class-level @ConditionalOnMissingBean vẫn có trường hợp hợp lý

Nếu toàn bộ cấu hình là một implementation thay thế hoàn chỉnh và không bean nào trong nhóm được dùng khi ứng dụng đã cung cấp một integration khác, condition class-level có thể phù hợp.

Ví dụ một configuration chỉ gồm các bean nội bộ của một adapter mặc định; khi ứng dụng có adapter cấp cao hơn, cả nhóm mặc định không còn ý nghĩa. Khi ấy class-level condition có thể biểu đạt đúng ý định.

Nhưng nếu các bean có thể được tùy biến độc lập, method-level condition thường rõ ràng và linh hoạt hơn.

## 7. Thứ tự đánh giá và giới hạn của @ConditionalOnBean/@ConditionalOnMissingBean

Không phải mọi condition đều chỉ kiểm tra classpath hoặc property. Một số condition kiểm tra **bean definitions đã được đăng ký trong context tại thời điểm điều kiện được đánh giá**.

Đặc biệt:

- **@ConditionalOnBean** kiểm tra đã có bean phù hợp hay chưa.
- **@ConditionalOnMissingBean** kiểm tra chưa có bean phù hợp hay chưa.

Các điều kiện này phụ thuộc vào những bean definitions mà Spring đã xử lý đến thời điểm đó. Vì vậy thứ tự auto-configuration có thể ảnh hưởng kết quả.

### 7.1. Ví dụ bean mặc định phụ thuộc bean khác

~~~java
@AutoConfiguration
public class PartnerMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PartnerService.class)
    @ConditionalOnMissingBean(PartnerMetricsCollector.class)
    PartnerMetricsCollector partnerMetricsCollector(
            PartnerService partnerService) {
        return new DefaultPartnerMetricsCollector(partnerService);
    }
}
~~~

Bean metrics chỉ được đăng ký khi:

1. PartnerService đã được nhận diện là bean phù hợp.
2. Chưa có PartnerMetricsCollector do ứng dụng cung cấp.

Nếu PartnerService được đăng ký bởi một auto-configuration khác, thứ tự xử lý hai auto-configuration cần được thiết kế phù hợp để điều kiện nhìn thấy bean definition cần thiết.

### 7.2. Dùng @AutoConfiguration(after = ...)

Spring Boot hỗ trợ sắp xếp auto-configuration tương đối:

~~~java
@AutoConfiguration(after = PartnerCoreAutoConfiguration.class)
public class PartnerMetricsAutoConfiguration {
    // ...
}
~~~

Điều này yêu cầu PartnerCoreAutoConfiguration được xử lý trước PartnerMetricsAutoConfiguration theo thứ tự auto-configuration. Khi dùng condition dựa trên bean, thứ tự như vậy giúp điều kiện có thể nhìn thấy definition đã được đăng ký từ cấu hình trước.

Các thuộc tính liên quan gồm:

- **before**: xử lý auto-configuration này trước một cấu hình khác.
- **after**: xử lý sau một cấu hình khác.
- **beforeName/afterName**: dùng tên class khi không muốn tham chiếu class trực tiếp.

Đây là thứ tự giữa các auto-configuration, không phải một cơ chế tổng quát để sắp xếp mọi bean trong toàn ứng dụng.

### 7.3. Vì sao không nên dùng @ConditionalOnBean ở cấp class một cách tùy tiện?

Nếu đặt @ConditionalOnBean trên configuration class, toàn bộ class phụ thuộc vào những bean được nhận diện tại thời điểm đánh giá class condition. Nếu bean cần thiết được đăng ký bởi một cấu hình xử lý sau, condition có thể không match dù cuối cùng context vẫn có bean đó.

Trong auto-configuration, tài liệu Spring Boot thường khuyến nghị đặt condition về bean trên phương thức @Bean khi có thể, vì method-level condition được đánh giá trong quá trình đăng ký bean method và thường phù hợp hơn với việc tạo bean mặc định.

Không có nghĩa class-level @ConditionalOnBean luôn sai. Nó phù hợp khi toàn bộ configuration thực sự chỉ có ý nghĩa sau khi một nhóm bean nền đã tồn tại và thứ tự cấu hình được kiểm soát rõ. Nhưng hãy cân nhắc thứ tự và phạm vi ảnh hưởng trước khi dùng.

## 8. Điều kiện lớp ngoài và nested configuration

Nested configuration là một kỹ thuật hữu ích để tách các nhóm bean có điều kiện nền khác nhau.

Ví dụ thư viện có hai tích hợp độc lập:

- Partner HTTP SDK.
- Partner messaging SDK.

Không nên đặt cả hai nhánh trong một outer class có @ConditionalOnClass yêu cầu cả hai thư viện nếu ứng dụng chỉ cần một tích hợp.

Có thể tổ chức:

~~~java
@AutoConfiguration
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.http.PartnerHttpClient")
    static class HttpConfiguration {

        @Bean
        PartnerHttpService partnerHttpService(
                PartnerHttpClient client) {
            return new PartnerHttpService(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.messaging.PartnerMessageClient")
    static class MessagingConfiguration {

        @Bean
        PartnerMessagingService partnerMessagingService(
                PartnerMessageClient client) {
            return new PartnerMessagingService(client);
        }
    }
}
~~~

Mỗi nested configuration có condition riêng. Nếu chỉ có HTTP SDK, nhánh HTTP có thể được áp dụng trong khi nhánh messaging bị bỏ qua.

### 8.1. Condition của outer class vẫn có hiệu lực với nested class

Nếu đặt thêm một condition trên outer PartnerAutoConfiguration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {
    // Các nested configuration...
}
~~~

thì property tổng thể trở thành cổng chung. Khi partner.enabled không phải true, cả hai nested configuration đều không được xử lý qua outer configuration đó.

Có thể hiểu điều kiện được lồng:

~~~text
PartnerAutoConfiguration
    partner.enabled = true?
          │
          ├── Không → Bỏ qua toàn bộ
          │
          ▼ Có
    ├── HttpConfiguration
    │      PartnerHttpClient có mặt?
    │
    └── MessagingConfiguration
           PartnerMessageClient có mặt?
~~~

Nếu hai tích hợp cần bật/tắt độc lập hoàn toàn, hãy cân nhắc đặt property riêng trên từng nested configuration thay vì dùng một cổng ngoài quá rộng.

### 8.2. Nested configuration giúp cô lập optional class

Khi một SDK là optional, các kiểu của SDK đó không nên xuất hiện tùy tiện trong outer auto-configuration luôn được nạp.

Ví dụ an toàn hơn:

~~~java
@AutoConfiguration
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
    static class PartnerClientConfiguration {

        @Bean
        PartnerService partnerService(PartnerClient client) {
            return new PartnerService(client);
        }
    }
}
~~~

Spring Boot có thể đọc metadata của nested configuration và bỏ qua nhánh chứa kiểu optional khi class không có. Điều này tránh việc JVM phải resolve một kiểu SDK vắng mặt quá sớm trong quá trình xử lý outer configuration.

Đặt name trong class condition giúp không cần tham chiếu trực tiếp kiểu SDK ở annotation. Tuy nhiên, điều quan trọng hơn là **chữ ký method và code dùng SDK nằm trong nested class được bảo vệ**. Chỉ đổi class literal thành chuỗi không bảo vệ các method signature khác đang tham chiếu optional type.

## 9. Class-level condition và method-level condition với @ConditionalOnClass

Hai cách sau có phạm vi khác nhau.

Condition trên class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
public class PartnerConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

Nếu PartnerClient vắng mặt, cả PartnerService và PartnerMetrics đều không được đăng ký từ class này.

Condition trên method:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerConfiguration {

    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }

    @Bean
    @ConditionalOnClass(name = "com.partner.sdk.PartnerClient")
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

Ở đây, chỉ PartnerMetrics bị chặn khi class không có mặt; PartnerService vẫn có thể được đăng ký.

Tuy nhiên, nếu method-level condition kiểm tra một class nhưng chữ ký hoặc return type của chính method lại tham chiếu class tùy chọn, có nguy cơ class bị resolve trước khi method condition bảo vệ được nó. Khi đó hãy đưa method vào nested configuration có class-level condition.

## 10. Nhiều điều kiện trên cùng một bean

Một phương thức @Bean có thể có nhiều điều kiện:

~~~java
@Bean
@ConditionalOnClass(name = "com.partner.metrics.MetricsClient")
@ConditionalOnProperty(
        prefix = "partner.metrics",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(PartnerMetricsCollector.class)
PartnerMetricsCollector partnerMetricsCollector() {
    return new DefaultPartnerMetricsCollector();
}
~~~

Bean chỉ được đăng ký khi tất cả điều kiện áp dụng tại injection point đó đều thỏa:

1. MetricsClient có mặt trên classpath.
2. partner.metrics.enabled có giá trị true.
3. Chưa có PartnerMetricsCollector phù hợp trong context tại thời điểm condition được đánh giá.

Sơ đồ:

~~~text
MetricsClient có mặt?
       │
       ├── Không → Bỏ qua bean
       ▼ Có
metrics.enabled = true?
       │
       ├── Không → Bỏ qua bean
       ▼ Có
Đã có PartnerMetricsCollector?
       │
       ├── Có → Bỏ qua bean mặc định
       ▼ Không
Đăng ký DefaultPartnerMetricsCollector
~~~

Đây là cách kết hợp classpath, property và bean condition ở đúng phạm vi bean.

## 11. Một ví dụ hoàn chỉnh: core bean và hai tính năng tùy chọn

Giả sử ứng dụng có core service không phụ thuộc SDK metrics hoặc SDK health. Chỉ một nhánh cần client tương ứng.

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class PartnerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    PartnerFacade partnerFacade() {
        return new DefaultPartnerFacade();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.health.HealthClient")
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    static class HealthConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerHealthIndicator partnerHealthIndicator(
                HealthClient client) {
            return new PartnerHealthIndicator(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.metrics.MetricsClient")
    @ConditionalOnProperty(
            prefix = "partner.metrics",
            name = "enabled",
            havingValue = "true"
    )
    static class MetricsConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerMetricsCollector partnerMetricsCollector(
                MetricsClient client) {
            return new PartnerMetricsCollector(client);
        }
    }
}
~~~

Trong thiết kế này:

- partner.enabled là cổng chung của tích hợp.
- PartnerFacade mặc định có thể được thay thế bởi ứng dụng.
- HealthConfiguration chỉ được xem xét nếu health SDK có mặt và property health bật.
- MetricsConfiguration chỉ được xem xét nếu metrics SDK có mặt và property metrics bật.
- Thiếu một SDK tùy chọn không nhất thiết làm mất core facade hoặc nhánh tích hợp còn lại.

Các class PartnerFacade, HealthClient, MetricsClient và implementation là kiểu minh họa; trong code thực tế cần cung cấp dependency và bean phù hợp.

## 12. Kiểm thử phạm vi của class-level condition

Khi viết auto-configuration, không chỉ kiểm tra một bean có xuất hiện hay không. Cần kiểm tra **toàn bộ nhóm bean bị ảnh hưởng bởi condition ở class**.

Giả sử:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureAutoConfiguration {

    @Bean
    CoreFeatureService coreFeatureService() {
        return new CoreFeatureService();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
~~~

Test dùng ApplicationContextRunner:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class FeatureAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    @Test
    void registersAllBeansWhenOuterConditionMatches() {
        runner.withPropertyValues("feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreFeatureService.class);
                    assertThat(context).hasSingleBean(FeatureMetrics.class);
                });
    }

    @Test
    void registersNoBeansWhenOuterConditionDoesNotMatch() {
        runner.withPropertyValues("feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CoreFeatureService.class);
                    assertThat(context).doesNotHaveBean(FeatureMetrics.class);
                });
    }
}
~~~

Hai test xác nhận class-level condition tác động đến cả hai bean. Nếu chỉ kiểm tra CoreFeatureService, bạn có thể bỏ sót việc FeatureMetrics vẫn bị đăng ký ngoài ý muốn do cấu trúc condition sai.

## 13. Kiểm thử phạm vi của method-level condition

Giả sử class luôn được áp dụng, nhưng metrics có condition riêng:

~~~java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    CoreFeatureService coreFeatureService() {
        return new CoreFeatureService();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "feature.metrics",
            name = "enabled",
            havingValue = "true"
    )
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
~~~

Test:

~~~java
@Test
void keepsCoreBeanWhenOptionalMethodConditionDoesNotMatch() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class))
            .withPropertyValues("feature.metrics.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CoreFeatureService.class);
                assertThat(context).doesNotHaveBean(FeatureMetrics.class);
            });
}
~~~

Test chứng minh condition trên method chỉ chặn FeatureMetrics; CoreFeatureService vẫn được đăng ký.

### 13.1. Test khi method condition match

~~~java
@Test
void registersOptionalBeanWhenMethodConditionMatches() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class))
            .withPropertyValues("feature.metrics.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CoreFeatureService.class);
                assertThat(context).hasSingleBean(FeatureMetrics.class);
            });
}
~~~

Kiểm thử cả hai phía giúp chứng minh property điều khiển đúng bean mục tiêu.

## 14. Kiểm thử @ConditionalOnMissingBean và khả năng override

Auto-configuration nên cho phép ứng dụng cung cấp bean riêng. Ví dụ:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Test trường hợp không có bean tùy chỉnh:

~~~java
@Test
void createsDefaultWhenUserBeanIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(DefaultGreetingService.class);
            });
}
~~~

Test trường hợp ứng dụng cung cấp implementation:

~~~java
@Test
void backsOffWhenUserProvidesGreetingService() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class))
            .withBean(
                    GreetingService.class,
                    () -> new CustomGreetingService()
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(CustomGreetingService.class);
            });
}
~~~

Test thứ hai chứng minh method-level @ConditionalOnMissingBean chỉ bỏ qua bean mặc định; bean do test cung cấp vẫn tồn tại và được sử dụng.

### 14.1. Vì sao test cả hai nhánh quan trọng?

Nếu chỉ test khi không có bean tùy chỉnh, bạn biết auto-configuration tạo được default bean. Nhưng bạn chưa biết nó có nhường chỗ đúng cách khi consumer cung cấp bean riêng hay không.

Một bộ test auto-configuration nên xác nhận ít nhất:

- Default bean được tạo khi không có user bean.
- Default bean không được tạo khi user bean phù hợp đã có.
- Các bean độc lập khác vẫn được tạo khi một default bean nhường chỗ.

## 15. Thứ tự auto-configuration trong test và ứng dụng

Khi dùng @ConditionalOnBean hoặc @ConditionalOnMissingBean, hãy chú ý thứ tự đăng ký.

Ví dụ:

~~~java
@AutoConfiguration
public class PartnerCoreAutoConfiguration {
    @Bean
    PartnerService partnerService() {
        return new PartnerService();
    }
}
~~~

~~~java
@AutoConfiguration(after = PartnerCoreAutoConfiguration.class)
public class PartnerMetricsAutoConfiguration {
    @Bean
    @ConditionalOnBean(PartnerService.class)
    PartnerMetrics partnerMetrics(PartnerService service) {
        return new PartnerMetrics(service);
    }
}
~~~

PartnerMetricsAutoConfiguration được xử lý sau PartnerCoreAutoConfiguration, nên điều kiện bean có thể thấy PartnerService đã được đăng ký.

Nếu không khai báo thứ tự phù hợp, điều kiện có thể được đánh giá trước khi bean mong đợi xuất hiện trong quá trình xử lý auto-configuration. Điều này đặc biệt quan trọng với @ConditionalOnMissingBean trong các thư viện starter.

Không nên cố sửa vấn đề thứ tự bằng cách khởi tạo bean thủ công trong condition hoặc gọi ApplicationContext.getBean() bên trong cấu hình. Hãy dùng metadata condition và thứ tự auto-configuration được hỗ trợ.

## 16. Điều kiện ở class ngoài và thứ tự xử lý nested configuration

Khi có nested configuration, có thể kết hợp điều kiện ở nhiều cấp:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "partner",
        name = "enabled",
        havingValue = "true"
)
public class PartnerAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.partner.health.HealthClient")
    @ConditionalOnProperty(
            prefix = "partner.health",
            name = "enabled",
            havingValue = "true"
    )
    static class HealthConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PartnerHealthIndicator partnerHealthIndicator(
                HealthClient client) {
            return new PartnerHealthIndicator(client);
        }
    }
}
~~~

Để bean health xuất hiện, cả ba lớp điều kiện phải thỏa:

1. partner.enabled = true ở outer configuration.
2. HealthClient có mặt ở nested configuration.
3. partner.health.enabled = true ở phương thức @Bean.

Nếu outer condition không thỏa, Spring không đi vào nhánh nested configuration này. Nếu outer thỏa nhưng SDK không có, nested configuration bị bỏ qua. Nếu cả hai lớp trên thỏa nhưng property health tắt, chỉ bean indicator bị bỏ qua.

~~~text
partner.enabled = true?
       │
       ├── Không → Không có nhánh Partner nào
       ▼ Có
HealthClient có mặt?
       │
       ├── Không → Không có HealthConfiguration
       ▼ Có
partner.health.enabled = true?
       │
       ├── Không → Không có PartnerHealthIndicator
       ▼ Có
Đăng ký PartnerHealthIndicator
~~~

Đây là cách kết hợp điều kiện theo phạm vi lồng nhau. Mỗi lớp condition có một trách nhiệm rõ ràng.

## 17. Những lỗi thiết kế thường gặp

### 17.1. Đặt condition của một tính năng nhỏ lên outer class

Một metrics bean là tùy chọn, nhưng condition metrics lại đặt ở class-level. Khi metrics tắt, service chính và health indicator cũng biến mất.

**Cách xử lý:** chuyển condition metrics xuống phương thức @Bean hoặc nested configuration riêng nếu cả một nhóm metrics phụ thuộc cùng điều kiện.

### 17.2. Đặt condition nền ở method quá muộn

Một nhóm bean đều cần SDK, nhưng chỉ một method có @ConditionalOnClass. Những method còn lại vẫn được xem xét và có thể tham chiếu SDK vắng mặt.

**Cách xử lý:** đặt class condition ở nested configuration bao quanh toàn bộ method cần SDK. Nếu có bean không phụ thuộc SDK, giữ nó ở cấu hình ngoài hoặc một nested configuration riêng.

### 17.3. Dùng class-level @ConditionalOnMissingBean làm mất các bean không liên quan

Ứng dụng cung cấp một service tùy chỉnh, khiến cả configuration class bị loại, bao gồm formatter và metrics mà ứng dụng vẫn cần.

**Cách xử lý:** đặt @ConditionalOnMissingBean trên từng bean mặc định cần cho phép override độc lập.

### 17.4. Dùng @ConditionalOnBean nhưng không kiểm soát thứ tự

Một auto-configuration phụ thuộc bean của auto-configuration khác nhưng được xử lý trước. Condition không thấy bean và cấu hình bị bỏ qua.

**Cách xử lý:** xem dependency giữa các auto-configuration và khai báo before/after phù hợp. Kiểm tra thứ tự trong context test.

### 17.5. Dùng method-level class condition nhưng chữ ký tham chiếu optional type

Method có @ConditionalOnClass nhưng tham số hoặc return type dùng class từ thư viện có thể vắng mặt. JVM có thể resolve kiểu đó quá sớm.

**Cách xử lý:** chuyển method vào nested configuration có class-level condition. Giữ outer class không tham chiếu kiểu optional trong field, superclass, interface hoặc method signature.

### 17.6. Cho rằng condition trên nested class bỏ qua mọi lỗi của outer class

Nested configuration giúp cô lập kiểu tùy chọn, nhưng nếu outer class vẫn có method hoặc field tham chiếu SDK trực tiếp, vấn đề nạp class có thể vẫn xảy ra.

**Cách xử lý:** kiểm tra toàn bộ outer class và các kiểu mà nó tham chiếu. Chỉ để optional API trong nhánh đã được bảo vệ.

### 17.7. Tạo bean cùng kiểu từ nhiều nhánh mà không có quy tắc

Hai nested configuration cùng match và cùng đăng ký một service type. Consumer inject dependency đơn có thể gặp NoUniqueBeanDefinitionException hoặc xung đột tên tùy cách đặt tên.

**Cách xử lý:** bảo đảm condition loại trừ lẫn nhau, dùng @ConditionalOnMissingBean cho default bean, hoặc dùng qualifier/collection nếu thật sự cần nhiều implementation.

## 18. Chẩn đoán condition không được áp dụng

Khi một bean không xuất hiện, đừng chỉ kiểm tra annotation trên phương thức. Hãy xác định condition nào đã chặn nó.

### Bước 1: Xác định bean được khai báo ở đâu

- Configuration class nào chứa phương thức @Bean?
- Bean nằm trong nested configuration không?
- Có condition trên outer class không?
- Có condition trên nested class không?
- Có condition riêng trên method không?

Một method condition không thể cứu một configuration class đã bị loại ở cấp ngoài.

### Bước 2: Kiểm tra property và profile

Với @ConditionalOnProperty, xác nhận key chính xác, giá trị, havingValue và matchIfMissing. Với @Profile, xác nhận profile active thực tế.

### Bước 3: Kiểm tra classpath

Với @ConditionalOnClass hoặc @ConditionalOnMissingClass, kiểm tra class có trong runtime classpath của process không. Test classpath có thể khác executable JAR.

### Bước 4: Kiểm tra bean condition

Với @ConditionalOnBean hoặc @ConditionalOnMissingBean, xem bean nào đã được đăng ký tại thời điểm condition được đánh giá và auto-configuration nào cần xử lý trước.

### Bước 5: Đọc Condition Evaluation Report

Chạy ứng dụng với tùy chọn debug:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể in condition report với các nhóm positive match và negative match. Tìm tên auto-configuration, configuration class hoặc condition liên quan.

### Bước 6: Xác nhận bean trong context

Sau khi ứng dụng khởi động, có thể dùng ApplicationContext hoặc Actuator /actuator/beans nếu endpoint đã được expose và bảo vệ phù hợp. Điều này giúp phân biệt bean không được đăng ký với bean đã đăng ký nhưng khởi tạo thất bại.

## 19. Kiểm thử ma trận điều kiện

Với một auto-configuration có nhiều lớp condition, hãy viết test theo ma trận. Ví dụ:

| SDK | partner.enabled | metrics.enabled | Kết quả mong đợi |
|---|---:|---:|---|
| Có | true | true | Core service và metrics bean có thể được đăng ký. |
| Có | true | false | Core service có, metrics bean không có. |
| Có | false | true | Toàn bộ cấu hình ngoài bị bỏ qua; metrics không xuất hiện. |
| Không | true | true | Nhánh cần SDK bị bỏ qua. |

Đối với classpath condition, test có SDK và test không SDK phải dùng runtime classpath tương ứng. Không thể giả lập class vắng mặt chỉ bằng thay property.

Đối với @ConditionalOnMissingBean, cần thêm một nhánh test cung cấp user bean và xác nhận default bean nhường chỗ mà các bean độc lập vẫn hoạt động.

Với nhiều condition, không nhất thiết phải tạo mọi tổ hợp nếu số lượng quá lớn. Hãy ưu tiên kiểm thử:

- Mỗi condition có một test match.
- Mỗi condition có một test không match.
- Các điều kiện ngoài và trong được kết hợp đúng.
- Các bean không liên quan không bị tắt ngoài ý muốn.
- Trường hợp người dùng override bean mặc định.

## 20. Những hiểu nhầm thường gặp

**“Condition trên @Bean method không match thì cả configuration class bị bỏ qua.”**  
Không. Chỉ bean do method đó khai báo bị bỏ qua; các method khác vẫn có thể được xử lý.

**“Condition trên configuration class không match chỉ bỏ qua một bean.”**  
Không. Toàn bộ cấu hình ở cấp class bị loại khỏi quá trình xử lý theo nhánh đó, bao gồm các method @Bean và cấu hình liên quan được khai báo từ class.

**“Nên đặt mọi @ConditionalOnMissingBean lên configuration class để gọn.”**  
Không. Nếu các bean có thể được override độc lập, đặt condition trên từng method giúp giữ lại các bean mặc định không liên quan.

**“@ConditionalOnBean luôn thấy mọi bean cuối cùng sẽ có trong context.”**  
Không. Bean condition được đánh giá dựa trên các bean definitions đã được xử lý tại thời điểm đó. Thứ tự auto-configuration có thể ảnh hưởng kết quả.

**“@Order có thể thay thế before/after của auto-configuration.”**  
Không. @Order chủ yếu sắp xếp một số collection có thứ tự; before/after điều khiển thứ tự tương đối giữa auto-configuration.

**“Method-level @ConditionalOnClass luôn an toàn với optional class trong chữ ký.”**  
Không. Kiểu trong method signature có thể bị JVM resolve trước khi condition method bảo vệ được nó. Dùng nested configuration để cô lập optional type.

**“Dùng name thay class literal là đủ để bảo vệ mọi tham chiếu tới optional type.”**  
Không. Thuộc tính name chỉ thay cách chỉ định class trong annotation. Outer class vẫn có thể lỗi nếu field, method signature hoặc superclass tham chiếu class vắng mặt.

**“Nếu một nested configuration có condition riêng thì condition outer không ảnh hưởng nó.”**  
Không. Nếu outer configuration bị loại, nested configuration được khai báo từ nhánh đó cũng không được xử lý.

**“Condition match nghĩa bean đã được tạo thành công.”**  
Không. Condition quyết định có đăng ký cấu hình/bean definition hay không; constructor, factory method hoặc dependency vẫn có thể lỗi khi khởi tạo.

## Ghi nhớ cốt lõi

**Condition ở configuration class** là cổng chung: nếu không match, toàn bộ cấu hình đó bị bỏ qua. **Condition ở từng @Bean method** là cổng riêng: chỉ bean do method đó khai báo bị bỏ qua, còn các bean khác trong cùng class vẫn có thể tồn tại.

Trong auto-configuration, hãy đặt điều kiện ở phạm vi nhỏ nhất phản ánh đúng yêu cầu. Dùng class-level condition cho yêu cầu nền chung của một nhóm; dùng method-level condition cho bean tùy chọn hoặc bean mặc định có thể được override độc lập. Với @ConditionalOnBean và @ConditionalOnMissingBean, chú ý thứ tự auto-configuration vì điều kiện dựa trên bean definitions đã được xử lý. Khi một nhóm bean phụ thuộc SDK tùy chọn, nested configuration giúp cô lập classpath condition và tránh nạp kiểu không có trên runtime classpath. Kiểm thử cả trường hợp condition match, không match và user bean override để bảo đảm mỗi điều kiện chỉ ảnh hưởng đúng phạm vi mong muốn.
