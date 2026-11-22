# SpEL trong @Bean method và giá trị khởi tạo trong Spring Framework

Trong Spring, bean có thể được tạo bằng phương thức được đánh dấu @Bean. Phương thức này trả về một đối tượng do Spring container quản lý. Các giá trị truyền vào constructor hoặc setter của đối tượng có thể đến từ property bên ngoài, bean khác hoặc một biểu thức Spring Expression Language (SpEL).

Một cách phổ biến là dùng @Value trên tham số của phương thức @Bean:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingSettings billingSettings(
            @Value("#{2 * 60}") int timeoutSeconds) {
        return new BillingSettings(timeoutSeconds);
    }
}
~~~

Spring đánh giá biểu thức rồi truyền kết quả vào timeoutSeconds trước khi gọi phương thức tạo bean. Phần thân billingSettings vẫn là mã Java thông thường.

SpEL cũng có thể được dùng trong giá trị property của bean definition, trong XML hoặc các cấu hình Spring hỗ trợ biểu thức. Bài này giải thích vị trí đánh giá, cách khởi tạo bean với giá trị động, tham chiếu bean, placeholder, chuyển đổi kiểu và những điểm cần chú ý về vòng đời.

## 1. @Bean method là gì?

Một phương thức @Bean nằm trong lớp cấu hình Spring và trả về đối tượng cần đăng ký vào container.

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

Khi container xử lý cấu hình, Spring gọi phương thức greetingService() và đăng ký đối tượng trả về thành một bean. Theo mặc định, tên bean là tên phương thức, trong ví dụ này là greetingService.

Phương thức @Bean có thể nhận tham số. Spring giải quyết các tham số đó từ container, bao gồm dependency khác hoặc giá trị được inject qua @Value.

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public GreetingService greetingService(
            MessageCatalog messageCatalog) {
        return new GreetingService(messageCatalog.defaultGreeting());
    }
}
~~~

Ở đây, MessageCatalog là dependency được Spring inject trực tiếp. Khi tham số cần là một giá trị được tính từ biểu thức, có thể đặt @Value trên tham số đó.

## 2. SpEL trong tham số của @Bean method

@Value có thể được đặt trên tham số phương thức @Bean. Nếu giá trị có dạng #{...}, Spring đánh giá phần bên trong bằng SpEL rồi chuyển kết quả sang kiểu tham số nếu cần.

~~~java
@Configuration
public class ReportConfiguration {

    @Bean
    public ReportSettings reportSettings(
            @Value("#{10 + 5}") int pageSize,
            @Value("#{true}") boolean includeSummary) {

        return new ReportSettings(pageSize, includeSummary);
    }
}
~~~

Khi tạo ReportSettings:

1. Spring xử lý các tham số của phương thức @Bean.
2. Biểu thức #{10 + 5} được đánh giá thành số 15.
3. Biểu thức #{true} được đánh giá thành Boolean true.
4. Các kết quả được chuyển đổi sang kiểu tham số tương ứng nếu cần.
5. Spring gọi phương thức reportSettings(...) với các giá trị đã chuẩn bị.
6. Đối tượng trả về được đăng ký trong container.

Cách này phù hợp với những giá trị khởi tạo ngắn gọn như giới hạn, cờ bật/tắt hoặc một giá trị được tính từ cấu hình.

## 3. Kết hợp property placeholder với SpEL

Property placeholder có cú pháp ${property.name:default}. Placeholder lấy giá trị từ Environment hoặc property source. SpEL có cú pháp #{...} và dùng để tính toán hoặc truy cập đối tượng.

Có thể kết hợp hai cơ chế khi một property cần được tính toán trước khi truyền vào @Bean method.

Ví dụ, cấu hình số giây trong application.properties:

~~~properties
app.cache.ttl-seconds=45
~~~

Dùng property đó để tạo Duration:

~~~java
@Configuration
public class CacheConfiguration {

    @Bean
    public CacheSettings cacheSettings(
            @Value("#{T(java.time.Duration).ofSeconds(${app.cache.ttl-seconds:30})}")
            Duration ttl) {

        return new CacheSettings(ttl);
    }
}
~~~

Placeholder được phân giải thành giá trị cấu hình, sau đó SpEL gọi Duration.ofSeconds(...) để tạo đối tượng Duration. Nếu property không được cung cấp, placeholder sử dụng giá trị mặc định 30.

Nếu chỉ cần inject giá trị cấu hình mà không tính toán, dùng placeholder trực tiếp thường đơn giản hơn:

~~~java
@Bean
public CacheSettings cacheSettings(
        @Value("${app.cache.ttl-seconds:30}") long ttlSeconds) {
    return new CacheSettings(Duration.ofSeconds(ttlSeconds));
}
~~~

Chọn placeholder cho cấu hình theo môi trường. Chỉ thêm SpEL khi cần phép tính, truy cập bean hoặc tạo giá trị phức tạp hơn.

## 4. Tham chiếu bean trong giá trị khởi tạo

SpEL có thể tham chiếu bean khác trong container bằng ký hiệu @ trước tên bean. Điều này cho phép giá trị của bean mới phụ thuộc vào property hoặc method của một bean đã đăng ký.

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingSettings billingSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {

        return new BillingSettings(currency);
    }
}
~~~

Ở đây, Spring đánh giá biểu thức để lấy defaultCurrency từ bean pricingService rồi truyền kết quả vào constructor BillingSettings.

Cũng có thể gọi method của bean:

~~~java
@Bean
public ShippingSettings shippingSettings(
        @Value("#{ @pricingService.defaultShippingThreshold() }")
        BigDecimal threshold) {

    return new ShippingSettings(threshold);
}
~~~

Bean được tham chiếu phải có thể phân giải trong ApplicationContext. Tên bean hoặc alias trong biểu thức phải khớp với tên đã đăng ký.

Khi dependency là một object mà phương thức @Bean cần sử dụng trong nhiều thao tác, ưu tiên inject dependency trực tiếp qua tham số phương thức thay vì lấy một property đơn lẻ qua SpEL:

~~~java
@Bean
public BillingService billingService(PricingService pricingService) {
    return new BillingService(pricingService);
}
~~~

Dependency injection trực tiếp làm quan hệ giữa các bean rõ ràng hơn. SpEL bean reference phù hợp hơn khi cần tính một giá trị cấu hình ngay tại điểm inject.

## 5. SpEL trong giá trị constructor và setter của bean

Một phương thức @Bean thường khởi tạo đối tượng bằng constructor hoặc tạo đối tượng rồi thiết lập property. SpEL có thể cung cấp giá trị cho các tham số đầu vào của phương thức @Bean, còn mã Java quyết định cách sử dụng các giá trị đó để tạo instance.

Ví dụ constructor:

~~~java
public class RetryPolicy {
    private final int maxAttempts;
    private final Duration delay;

    public RetryPolicy(int maxAttempts, Duration delay) {
        this.maxAttempts = maxAttempts;
        this.delay = delay;
    }
}

@Configuration
public class RetryConfiguration {

    @Bean
    public RetryPolicy retryPolicy(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("#{T(java.time.Duration).ofMillis(500)}") Duration delay) {

        return new RetryPolicy(maxAttempts, delay);
    }
}
~~~

Giá trị maxAttempts đến từ property placeholder. Giá trị delay được tạo bằng SpEL thông qua static method của Duration.

Nếu cần thiết lập property sau khi tạo đối tượng, phương thức @Bean có thể gọi setter như mã Java thông thường:

~~~java
@Bean
public ReportSettings reportSettings(
        @Value("#{ 'Monthly report' }") String title) {

    ReportSettings settings = new ReportSettings();
    settings.setTitle(title);
    return settings;
}
~~~

SpEL chỉ cung cấp giá trị cho tham số. Việc gọi setter trong thân phương thức vẫn do Java thực hiện.

## 6. SpEL trong XML bean definition

Trong XML bean definition, một giá trị property có thể chứa biểu thức SpEL. Spring đánh giá biểu thức khi tạo và cấu hình bean.

~~~xml
<bean id="reportSettings"
      class="com.example.ReportSettings">
    <property name="pageSize" value="#{10 + 5}" />
    <property name="title" value="#{'Monthly report'}" />
</bean>
~~~

Có thể dùng placeholder kết hợp với SpEL:

~~~xml
<bean id="cacheSettings"
      class="com.example.CacheSettings">
    <property name="ttlSeconds"
              value="#{${app.cache.ttl-seconds:30}" />
</bean>
~~~

Trong ví dụ, placeholder cung cấp số giây và SpEL đánh giá giá trị đó. Cấu hình XML cần tuân thủ quy tắc escape của XML nếu biểu thức có ký tự đặc biệt.

SpEL trong XML bean definition là một điểm tích hợp của Spring container. Không nên suy luận rằng mọi thuộc tính XML hoặc mọi annotation đều tự động hỗ trợ SpEL.

## 7. Tạo collection và map làm giá trị khởi tạo

SpEL hỗ trợ inline list và inline map. Chúng có thể được dùng làm giá trị cấu hình của bean nếu kiểu đích và cơ chế chuyển đổi hỗ trợ.

Ví dụ:

~~~java
@Configuration
public class AccessConfiguration {

    @Bean
    public AccessSettings accessSettings(
            @Value("#{ {'reader', 'editor', 'admin'} }")
            List<String> roles) {

        return new AccessSettings(roles);
    }
}
~~~

Inline map:

~~~java
@Bean
public FeatureSettings featureSettings(
        @Value("#{ {'checkout': true, 'new-search': false} }")
        Map<String, Boolean> flags) {

    return new FeatureSettings(flags);
}
~~~

Các phần tử inline collection được đánh giá theo kiểu của từng biểu thức. Nếu collection có nhiều kiểu phần tử khác nhau, hãy dùng kiểu nhận tổng quát và kiểm tra kiểu thực tế trước khi sử dụng.

Nếu bean cần collection mutable, hãy cân nhắc tạo defensive copy trong constructor. Không nên giả định một collection literal trong SpEL là nơi lưu trạng thái có thể sửa đổi an toàn.

## 8. Sử dụng type reference và static method

Toán tử T(...) cho phép SpEL tham chiếu kiểu Java. Có thể gọi static method để tạo đối tượng hoặc tính giá trị.

Ví dụ:

~~~java
@Bean
public Duration requestTimeout(
        @Value("#{T(java.time.Duration).ofSeconds(20)}")
        Duration timeout) {

    return timeout;
}
~~~

Một ví dụ khác dùng Math:

~~~java
@Bean
public Integer maximumBatchSize(
        @Value("#{T(java.lang.Math).max(50, 100)}")
        int maximum) {

    return maximum;
}
~~~

Type reference có ích khi tạo một giá trị nhỏ từ API Java. Nếu logic khởi tạo phức tạp hoặc cần kiểm thử độc lập, hãy chuyển logic sang phương thức Java hoặc một bean chuyên trách.

## 9. Giá trị mặc định, Elvis và null

Có thể dùng giá trị mặc định trong placeholder:

~~~java
@Bean
public RegionSettings regionSettings(
        @Value("${app.region:unknown}") String region) {

    return new RegionSettings(region);
}
~~~

Toán tử Elvis trong SpEL cung cấp giá trị thay thế khi vế trái là null hoặc chuỗi rỗng:

~~~java
@Bean
public RegionSettings regionSettings(
        @Value("#{ @applicationSettings.region ?: 'unknown' }")
        String region) {

    return new RegionSettings(region);
}
~~~

Hai cơ chế có mục đích khác nhau:

- Placeholder default xử lý trường hợp property key không có giá trị được phân giải.
- Elvis xử lý kết quả của một biểu thức SpEL.

Nếu biểu thức truy cập property lồng nhau có thể null, dùng safe navigation:

~~~java
@Value("#{ @applicationSettings.contact?.email ?: 'support@example.com' }")
private String supportEmail;
~~~

Safe navigation bảo vệ đường dẫn property tại vị trí được dùng. Nó không tự xử lý bean name không tồn tại hoặc mọi lỗi đánh giá khác.

## 10. Chuyển đổi kiểu trước khi gọi @Bean method

Giá trị SpEL có kiểu runtime. Tham số phương thức @Bean có kiểu Java cụ thể. Spring có thể chuyển đổi giá trị khi có converter phù hợp.

Ví dụ:

~~~java
@Bean
public RetryPolicy retryPolicy(
        @Value("#{ '5' }") int maxAttempts,
        @Value("#{ 'true' }") boolean enabled) {

    return new RetryPolicy(maxAttempts, enabled);
}
~~~

Các giá trị chuỗi có thể được chuyển đổi sang int và boolean nhờ cơ chế chuyển đổi của Spring. Nếu không có converter phù hợp, việc giải quyết tham số có thể thất bại trong quá trình tạo bean.

Với kiểu phức tạp, tạo trực tiếp giá trị có kiểu rõ ràng trong SpEL thường dễ hiểu hơn:

~~~java
@Bean
public CacheSettings cacheSettings(
        @Value("#{T(java.time.Duration).ofMinutes(5)}")
        Duration ttl) {

    return new CacheSettings(ttl);
}
~~~

Khi cấu hình converter tùy chỉnh, hãy kiểm tra nó được đăng ký trong môi trường conversion mà cơ chế @Value đang sử dụng. Đừng giả định mọi context tự tạo hoặc mọi điểm tích hợp đều dùng chung một ConversionService.

## 11. Thời điểm đánh giá và vòng đời bean

Giá trị trong @Value được phân giải trong quá trình Spring tạo và inject bean. Giá trị kết quả được truyền vào constructor, field hoặc setter tại thời điểm xử lý bean.

Ví dụ:

~~~java
@Bean
public StartupInfo startupInfo(
        @Value("#{T(java.lang.System).currentTimeMillis()}")
        long createdAt) {

    return new StartupInfo(createdAt);
}
~~~

createdAt phản ánh thời điểm biểu thức được đánh giá khi bean được khởi tạo. Nó không tự cập nhật sau đó.

Nếu biểu thức tham chiếu bean khác, bean đó phải có thể được phân giải khi Spring đánh giá tham số. Nếu hai bean phụ thuộc vòng tròn trong giai đoạn khởi tạo, SpEL không tự giải quyết được chu trình.

Ví dụ, nếu BillingSettings cần PricingService để lấy currency nhưng PricingService lại cần BillingSettings trong constructor, ứng dụng có thể gặp lỗi vòng phụ thuộc. Hãy xem lại đồ thị dependency, tách cấu hình chung hoặc inject dependency theo cách phù hợp.

Không nên dùng biểu thức khởi tạo để gọi method có tác dụng phụ hoặc thực hiện công việc dài. Bean creation nên có thể dự đoán và dễ kiểm thử.

## 12. @Bean method, @Configuration và lời gọi giữa các bean

Trong lớp @Configuration đầy đủ, Spring có thể proxy các lời gọi giữa những phương thức @Bean để bảo đảm ngữ nghĩa singleton của bean do container quản lý.

Ví dụ:

~~~java
@Configuration
public class ServiceConfiguration {

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService(pricingService());
    }
}
~~~

Trong cấu hình @Configuration đầy đủ, lời gọi pricingService() từ checkoutService() được container xử lý thông qua proxy để lấy bean được quản lý.

Nếu dùng chế độ lite configuration, chẳng hạn một lớp chỉ có @Bean mà không phải @Configuration đầy đủ, lời gọi trực tiếp một phương thức @Bean có thể là lời gọi Java thông thường và tạo instance mới. Khi cần dependency, tham số phương thức @Bean thường rõ ràng hơn:

~~~java
@Bean
public CheckoutService checkoutService(PricingService pricingService) {
    return new CheckoutService(pricingService);
}
~~~

SpEL không thay đổi quy tắc proxy hoặc lời gọi Java giữa các phương thức @Bean. Hãy phân biệt biểu thức được Spring đánh giá với lời gọi phương thức thực hiện trong thân Java.

## 13. Phân biệt giá trị SpEL với mã Java trong @Bean method

Đây là khác biệt quan trọng khi đọc cấu hình.

Trong ví dụ:

~~~java
@Bean
public ReportSettings reportSettings(
        @Value("#{10 + 5}") int pageSize) {

    return new ReportSettings(pageSize);
}
~~~

SpEL chỉ xuất hiện trong annotation @Value trên tham số. Spring đánh giá biểu thức và đưa số 15 vào phương thức. Câu lệnh new ReportSettings(pageSize) là mã Java, không phải SpEL.

Tương tự:

~~~java
@Bean
public ReportSettings reportSettings(Environment environment) {
    int pageSize = environment.getProperty(
            "app.report.page-size",
            Integer.class,
            15
    );

    return new ReportSettings(pageSize);
}
~~~

Đây là cách Java đọc trực tiếp Environment. Không có biểu thức SpEL trong ví dụ.

Có thể chọn giữa hai cách theo nhu cầu:

- Dùng @Value với SpEL cho giá trị ngắn, khai báo ngay tại tham số.
- Dùng Environment hoặc mã Java khi cần nhiều bước xử lý, validation hoặc nhánh điều kiện.
- Dùng dependency injection trực tiếp khi cần một bean khác làm dependency lâu dài.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ thân phương thức @Bean tự động là SpEL | SpEL chỉ được đánh giá tại các điểm tích hợp hỗ trợ biểu thức. | Đặt biểu thức trong @Value hoặc bean-definition value phù hợp. |
| Dùng placeholder khi cần tính toán | Placeholder chỉ lấy property theo key. | Dùng #{...} để đánh giá SpEL. |
| Quên dấu phân cách #{...} | Spring không nhận diện vùng biểu thức. | Kiểm tra cú pháp annotation hoặc XML value. |
| Bean reference không được phân giải | Tên bean sai hoặc bean không thuộc container hiện tại. | Kiểm tra bean name, alias và context. |
| Tham số không chuyển đổi được | Kiểu kết quả không tương thích kiểu Java đích. | Dùng kiểu literal phù hợp hoặc converter. |
| Bean phụ thuộc vòng tròn | Giá trị khởi tạo tham chiếu qua lại giữa các bean. | Tách dependency hoặc thay đổi thiết kế khởi tạo. |
| Gọi phương thức có tác dụng phụ khi khởi tạo | Biểu thức chạy trong quá trình tạo bean. | Ưu tiên phép tính thuần và method chỉ đọc. |
| Dùng lời gọi @Bean như lời gọi Java thông thường | Lite configuration không có proxy đầy đủ cho inter-bean method call. | Inject bean qua tham số phương thức @Bean. |
| Mong giá trị @Value tự cập nhật | Giá trị được inject tại thời điểm xử lý bean. | Truy vấn dependency khi cần giá trị mới hoặc dùng cơ chế cấu hình động. |
| Đưa biểu thức không đáng tin cậy vào cấu hình | Biểu thức có thể truy cập nhiều khả năng của evaluation context. | Chỉ đánh giá biểu thức cấu hình đáng tin cậy và giới hạn quyền truy cập. |

Khi chẩn đoán, phân biệt lỗi phân giải placeholder, lỗi parse SpEL, lỗi tìm bean, lỗi chuyển đổi kiểu và lỗi trong thân phương thức Java. Những lỗi này xảy ra ở các giai đoạn khác nhau của quá trình tạo bean.

## 15. Nguyên tắc thực hành

1. Dùng tham số @Bean để làm rõ các giá trị và dependency cần cho quá trình tạo đối tượng.
2. Dùng @Value("#{...}") khi cần đánh giá SpEL tại một điểm inject được Spring hỗ trợ.
3. Dùng placeholder cho property phụ thuộc môi trường và thêm SpEL khi cần tính toán.
4. Ưu tiên inject bean trực tiếp nếu phương thức cần sử dụng dependency như một đối tượng.
5. Dùng type reference cho phép tính hoặc tạo giá trị nhỏ; chuyển logic phức tạp sang Java.
6. Xử lý null và giá trị mặc định rõ ràng.
7. Kiểm tra chuyển đổi kiểu giữa kết quả biểu thức và tham số phương thức.
8. Tránh vòng phụ thuộc giữa các bean trong quá trình khởi tạo.
9. Không nhầm mã Java trong thân @Bean method với biểu thức SpEL.
10. Giữ biểu thức ngắn, dễ đọc và không có tác dụng phụ.

## 16. Ghi nhớ

- @Bean method là phương thức Java tạo bean và trả về đối tượng do Spring quản lý.
- @Value trên tham số @Bean method cho phép Spring đánh giá SpEL trước khi gọi phương thức.
- SpEL cũng có thể được dùng trong giá trị property của bean definition, chẳng hạn XML configuration.
- Placeholder ${key:default} lấy cấu hình; #{...} đánh giá biểu thức.
- Biểu thức có thể tham chiếu bean, property, method, type, phép toán và inline collection.
- Spring chuyển đổi kết quả sang kiểu tham số nếu có converter phù hợp.
- Giá trị được đánh giá trong quá trình tạo và inject bean; không tự cập nhật liên tục.
- SpEL không thay đổi quy tắc Java hoặc proxy giữa các phương thức @Bean.
- Dùng dependency injection trực tiếp cho dependency lâu dài; dùng SpEL cho giá trị cấu hình được tính tại điểm inject.
- Giữ logic khởi tạo dễ dự đoán, tránh tác dụng phụ và vòng phụ thuộc.
