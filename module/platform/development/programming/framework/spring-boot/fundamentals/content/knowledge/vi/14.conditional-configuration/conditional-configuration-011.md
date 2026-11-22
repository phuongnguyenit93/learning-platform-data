# Thứ tự xử lý cấu hình và nguyên nhân điều kiện bean cho kết quả khác dự đoán

Spring Boot có thể tự đăng ký nhiều bean dựa trên classpath, property, profile, loại ứng dụng và những bean đã được khai báo. Cơ chế này giúp ứng dụng có cấu hình mặc định hợp lý mà không cần viết mọi factory method bằng tay. Tuy nhiên, khi một bean xuất hiện dù ta nghĩ điều kiện phải sai, hoặc không xuất hiện dù đã đặt property và thêm dependency, nguyên nhân thường nằm ở **thời điểm Spring xử lý cấu hình và thời điểm điều kiện được đánh giá**.

Để hiểu kết quả, cần phân biệt ba giai đoạn:

1. Spring đọc và phân tích các lớp cấu hình, annotation và import.
2. Spring đăng ký các bean definition, đồng thời đánh giá những điều kiện liên quan đến bean.
3. Container khởi tạo instance, tiêm dependency và áp dụng lifecycle.

Các điều kiện không phải đều được kiểm tra cùng lúc. Một điều kiện về classpath có thể được đánh giá khi Spring đang phân tích cấu hình; một điều kiện như `@ConditionalOnMissingBean` cần biết những bean definition nào đã được đăng ký và vì vậy gắn với giai đoạn đăng ký bean. Thứ tự giữa các cấu hình, đặc biệt auto-configuration của Spring Boot, có thể làm thay đổi tập bean mà điều kiện nhìn thấy.

Bài học này giải thích trình tự xử lý ở mức cần thiết để đọc kết quả điều kiện, hiểu vì sao bean được tạo hoặc bị bỏ qua, và biết cách điều tra thay vì thay đổi thứ tự một cách ngẫu nhiên.

## 1. Điều kiện bean không phải một biểu thức được kiểm tra ở mọi thời điểm

Một cấu hình có thể khai báo:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true"
)
public class MailConfiguration {

    @Bean
    public MailSender mailSender() {
        return new SmtpMailSender();
    }
}
~~~

Nếu property phù hợp, cấu hình có thể được áp dụng và phương thức `mailSender()` cung cấp bean definition. Nếu property không phù hợp, cấu hình bị bỏ qua và bean này không được đăng ký từ nguồn đó.

Nhưng “có điều kiện” không đồng nghĩa Spring đợi đến lúc gọi `mailSender()` mới kiểm tra. Spring có thể đánh giá điều kiện khi xử lý configuration class hoặc khi xử lý bean method, tùy loại điều kiện và phase mà condition yêu cầu.

Ví dụ:

- `@ConditionalOnClass` quan tâm class có mặt trên classpath, nên có thể được đánh giá trong giai đoạn parse configuration.
- `@ConditionalOnProperty` kiểm tra property trong `Environment` và có thể được đánh giá ở giai đoạn xử lý cấu hình.
- `@ConditionalOnBean` và `@ConditionalOnMissingBean` cần xét những bean definition đã được đăng ký, nên liên quan đến giai đoạn đăng ký bean.

Nếu một điều kiện được đánh giá trước khi thông tin cần thiết xuất hiện, kết quả có thể khác với suy luận dựa trên trạng thái cuối cùng của ApplicationContext.

## 2. Trình tự xử lý cấu hình ở mức khái quát

Một ứng dụng Spring Boot khởi động qua:

~~~java
@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`SpringApplication.run(...)` chuẩn bị môi trường, tạo ApplicationContext phù hợp, nạp nguồn cấu hình và kích hoạt quá trình xử lý bean definitions.

Có thể mô tả luồng khái quát:

~~~text
SpringApplication.run(...)
          |
          v
Chuẩn bị Environment, profiles,
property sources và ApplicationContext
          |
          v
Đăng ký cấu hình khởi động
(@SpringBootApplication, @Import, ...)
          |
          v
ConfigurationClassPostProcessor
phân tích configuration classes
          |
          +--> component scan
          |
          +--> @Import và cấu hình được import
          |
          +--> deferred imports / auto-configuration
          |
          v
Đăng ký bean definitions
và đánh giá điều kiện tương ứng
          |
          v
BeanFactoryPostProcessor /
BeanPostProcessor và các bước container
          |
          v
Khởi tạo singleton, resolve dependency,
proxy và lifecycle callback
          |
          v
ApplicationContext sẵn sàng
~~~

Đây là sơ đồ giản lược để định hướng. Các bước nội bộ có thể đan xen, và một số extension point tham gia ở các thời điểm khác nhau. Nhưng có một phân biệt rất quan trọng: **đăng ký định nghĩa bean xảy ra trước khi phần lớn singleton bean được khởi tạo**.

### Configuration class được phân tích trước khi mọi bean instance tồn tại

`@Configuration` không đơn thuần là một class được gọi như service. Spring phân tích metadata của nó để tìm:

- `@Bean` methods.
- `@ComponentScan` và các component được phát hiện.
- `@Import`, `ImportSelector` và `ImportBeanDefinitionRegistrar`.
- `@PropertySource` và các chỉ thị cấu hình liên quan.
- Những condition quyết định cấu hình hoặc bean method có được áp dụng không.

Quá trình này chủ yếu làm việc với metadata và bean definitions. Nó không cần tạo tất cả service/repository trước rồi mới quyết định cấu hình.

### Deferred import và auto-configuration

`@EnableAutoConfiguration` (được bao gồm trong `@SpringBootApplication`) dùng cơ chế import chọn lọc các auto-configuration. Các auto-configuration thường được xử lý như deferred imports: Spring trước hết phân tích các cấu hình thông thường và những import liên quan, sau đó mới xử lý nhóm import được trì hoãn theo cơ chế tương ứng.

Điều này giúp auto-configuration có cơ hội quan sát các bean definition do ứng dụng khai báo trước đó. Vì vậy, các điều kiện như `@ConditionalOnMissingBean` thường có thể “nhường chỗ” cho bean do người dùng tự cấu hình.

Không nên coi đây là quy tắc rằng mọi bean của người dùng luôn được đăng ký trước mọi auto-configuration trong mọi cấu trúc phức tạp. `@Import`, cấu hình lồng nhau, nhiều context hoặc custom registrar có thể làm thứ tự thực tế khác đi. Khi điều kiện phụ thuộc vào bean, cần xem thứ tự đăng ký thực tế và báo cáo condition.

## 3. Hai phase của ConfigurationCondition

Spring Framework định nghĩa `ConfigurationCondition` để một condition có thể chỉ định thời điểm nó cần được đánh giá.

Hai phase chính:

| Phase | Ý nghĩa | Thông tin thường phù hợp |
|---|---|---|
| `PARSE_CONFIGURATION` | Trong lúc Spring phân tích configuration classes | Annotation metadata, classpath, cấu hình lớp |
| `REGISTER_BEAN` | Trong lúc Spring xử lý và đăng ký bean definitions | Những bean definition đã được đăng ký đến thời điểm đó |

Một condition thông thường chỉ triển khai `Condition` có thể được đánh giá trong quá trình kiểm tra cấu hình. Nếu triển khai `ConfigurationCondition`, nó có thể chỉ rõ phase phù hợp thông qua `getConfigurationPhase()`.

Ví dụ khái niệm:

~~~java
public class FeatureCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        return context.getBeanFactory()
                .containsBeanDefinition("featureRepository");
    }
}
~~~

Ví dụ này chỉ minh họa API và ý tưởng. Trong code thực tế, cần xử lý trường hợp `getBeanFactory()` không khả dụng hoặc dùng registry/metadata thích hợp; không nên giả định mọi loại context đều có cùng khả năng truy vấn.

Điểm cần nhớ: một condition cần quan sát bean definition không nên được thiết kế để chạy quá sớm ở phase parse. Ngược lại, điều kiện phụ thuộc classpath có thể được kiểm tra sớm để Spring không phải xử lý cấu hình không phù hợp.

## 4. Vì sao @ConditionalOnBean và @ConditionalOnMissingBean nhạy với thứ tự?

Hai annotation này rất phổ biến trong auto-configuration:

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
public JdbcHealthReporter jdbcHealthReporter(DataSource dataSource) {
    return new JdbcHealthReporter(dataSource);
}
~~~

~~~java
@Bean
@ConditionalOnMissingBean(DataSource.class)
public DataSource fallbackDataSource() {
    return createFallbackDataSource();
}
~~~

Chúng không chỉ hỏi “có class DataSource trên classpath không?”. Chúng hỏi về bean definition/bean có thể đáp ứng kiểu hoặc tiêu chí được chỉ định **tại thời điểm điều kiện được đánh giá**.

### Ví dụ thứ tự đăng ký

Giả sử có hai cấu hình:

~~~java
@Configuration
public class PrimaryConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

~~~java
@Configuration
public class ConditionalConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock fallbackClock() {
        return Clock.systemUTC();
    }
}
~~~

Nếu `applicationClock` đã được đăng ký trước khi Spring đánh giá điều kiện trên `fallbackClock`, bean fallback sẽ không được đăng ký. Nếu một cấu hình phức tạp khiến điều kiện được đánh giá trước khi bean definition phù hợp xuất hiện, kết quả có thể khác.

Vì vậy, Spring Boot khuyến nghị dùng `@ConditionalOnMissingBean` chủ yếu trong **auto-configuration**, nơi thứ tự import và các cơ chế sắp xếp được thiết kế để cấu hình mặc định có thể nhường chỗ cho cấu hình ứng dụng.

### Condition nhìn thấy definition, không phải mọi instance đang hoạt động

Điều kiện bean thường làm việc ở giai đoạn registry, trước khi instance được tạo. Vì thế, đừng hiểu `@ConditionalOnBean` là “đợi bean chạy thành công rồi mới kiểm tra”. Một bean definition có thể tồn tại nhưng instance về sau vẫn thất bại khi khởi tạo do thiếu dependency hoặc lỗi constructor.

Ngược lại, một object được tạo thủ công bên ngoài container không tự động trở thành bean definition mà điều kiện có thể nhìn thấy.

### Chỉ định kiểu, tên và annotation

Các annotation condition hỗ trợ nhiều cách xác định bean, ví dụ theo:

- Kiểu bean (`value` hoặc `type`).
- Tên bean (`name`).
- Annotation (`annotation`).
- Search strategy trong hierarchy của context.

Cần dùng đúng thuộc tính theo phiên bản Spring Boot đang dùng. Nếu kiểu bean được tạo qua factory method, Spring có thể dựa vào metadata return type; khai báo return type quá chung có thể làm việc suy luận kiểu khó chính xác hơn.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(Clock.class)
public Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Khai báo kiểu trả về `Clock` giúp Spring có thông tin phù hợp về loại bean mà phương thức cung cấp.

## 5. Auto-configuration ordering: @AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder

Spring Boot cung cấp các annotation để sắp xếp auto-configuration classes tương đối với nhau:

- `@AutoConfigureBefore`: chỉ định auto-configuration này được xử lý trước class được nêu.
- `@AutoConfigureAfter`: chỉ định xử lý sau class được nêu.
- `@AutoConfigureOrder`: chỉ định thứ tự tương đối bằng giá trị order.

Ví dụ:

~~~java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class ReportingAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    public ReportingRepository reportingRepository(DataSource dataSource) {
        return new JdbcReportingRepository(dataSource);
    }
}
~~~

Ý định là auto-configuration báo cáo được xử lý sau cấu hình DataSource để có thể xét bean liên quan. Cấu hình này là ví dụ minh họa; tên annotation và API cần khớp phiên bản Spring Boot của dự án.

Một ví dụ khác:

~~~java
@AutoConfiguration
@AutoConfigureBefore(CacheAutoConfiguration.class)
public class CustomCacheDefaultsAutoConfiguration {
    // Các bean hoặc cấu hình cache mặc định.
}
~~~

Các annotation ordering này dành cho **auto-configuration**, không phải công cụ tổng quát để sắp xếp mọi lớp Java hoặc mọi component scan.

### Ordering không tạo ra dependency

`@AutoConfigureAfter` không có nghĩa bean trong class đó tự động inject được mọi bean từ class trước. Nó chỉ điều khiển thứ tự xử lý auto-configuration. Bean vẫn phải được đăng ký và dependency phải tương thích.

Nếu bean A thực sự cần bean B, hãy khai báo dependency qua constructor hoặc phương thức `@Bean`. Không dùng ordering để thay cho quan hệ dependency.

### Không nhầm với @Order

`@Order` thường được dùng để sắp xếp thứ tự một số thành phần như ordered collection, handler, filter hoặc các đối tượng có hỗ trợ order. Nó **không phải** cách tổng quát để quyết định thứ tự đăng ký mọi bean definition hay thứ tự đánh giá mọi configuration class.

Ví dụ:

~~~java
@Component
@Order(1)
public class FirstHandler implements Handler {
    // ...
}
~~~

`@Order(1)` có thể ảnh hưởng thứ tự khi Spring cung cấp một tập các `Handler` theo cơ chế hỗ trợ ordering. Nó không bảo đảm `FirstHandler` được đăng ký trước mọi bean khác, và cũng không thay thế `@AutoConfigureBefore` trong auto-configuration.

### Không nhầm với @DependsOn

`@DependsOn("someBean")` biểu thị một bean cần bean khác được khởi tạo trước. Nó liên quan tới thứ tự khởi tạo/hủy instance, không phải thứ tự parse configuration hoặc đánh giá điều kiện auto-configuration.

Nếu điều kiện không thấy bean definition vì đăng ký quá muộn, thêm `@DependsOn` thường không giải quyết đúng vấn đề: `@DependsOn` không làm bean definition xuất hiện sớm hơn trong registry.

## 6. Component scan, @Import và @Bean cũng ảnh hưởng tập definition

Điều kiện bean nhận kết quả dựa trên những definition đã được đăng ký. Vì vậy, cần biết definition đến từ đâu.

### Component scan

~~~java
@Service
public class CustomerService {
    // ...
}
~~~

Nếu package nằm trong vùng scan, class có thể được đăng ký như bean definition. Nếu nằm ngoài vùng scan, bean không tự xuất hiện chỉ vì có `@Service`.

### @Import

~~~java
@Configuration
@Import(CustomerConfiguration.class)
public class StoreConfiguration {
}
~~~

`@Import` đưa cấu hình khác vào quá trình xử lý. Cấu hình được import có thể đăng ký thêm bean definitions và ảnh hưởng điều kiện được đánh giá sau đó.

### @Bean

~~~java
@Configuration
public class CustomerConfiguration {

    @Bean
    public CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}
~~~

Phương thức `@Bean` tạo bean definition. Nếu một auto-configuration kiểm tra `@ConditionalOnMissingBean(CustomerRepository.class)` sau khi definition này được đăng ký, auto-configuration có thể bỏ qua repository mặc định.

### ImportBeanDefinitionRegistrar

Một registrar có thể đăng ký nhiều bean definitions trực tiếp. Các definition này cũng có thể ảnh hưởng tới những condition được đánh giá ở bước sau. Nếu registrar và auto-configuration có quan hệ thứ tự, cần xem quá trình import và registration thực tế; không nên dựa vào giả định rằng mọi registrar luôn chạy trước mọi auto-configuration.

## 7. Điều kiện theo classpath: thư viện có mặt chưa chắc bean được tạo

`@ConditionalOnClass` kiểm tra class có tồn tại trên classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.search.SearchClient")
public class SearchAutoConfiguration {

    @Bean
    public SearchService searchService() {
        return new SearchService();
    }
}
~~~

Nếu class `SearchClient` không có trên classpath, auto-configuration có thể bị bỏ qua. Nếu có class, điều đó chỉ thỏa một điều kiện; các điều kiện khác vẫn có thể không đạt.

Một dependency có thể được khai báo trong build file nhưng không có trong runtime classpath vì scope/configuration, exclusion hoặc packaging. Khi đó `@ConditionalOnClass` có thể không match trong ứng dụng đang chạy.

### Dùng name để tránh resolve class quá sớm

Trong một số cấu hình thư viện optional, tham chiếu trực tiếp một class không có trên classpath có thể gây vấn đề khi JVM resolve annotation/configuration metadata. Dạng `name` cho phép mô tả class bằng tên:

~~~java
@ConditionalOnClass(
        name = "com.example.search.SearchClient"
)
~~~

Đối với auto-configuration, cần cẩn trọng đặt các method signature có kiểu thuộc thư viện optional trong một configuration class có thể được load khi thư viện vắng mặt. Có thể tách cấu hình nested hoặc class riêng được bảo vệ bởi điều kiện classpath để tránh class loading không mong muốn.

### @ConditionalOnMissingClass

Điều kiện ngược lại:

~~~java
@ConditionalOnMissingClass(
        "com.example.search.SearchClient"
)
@Configuration
public class SearchFallbackConfiguration {
    // Cấu hình fallback khi thư viện không có.
}
~~~

Điều kiện này hữu ích cho fallback khi một capability không hiện diện. Nhưng nếu class có mặt mà bean không được tạo vì property hoặc bean condition khác, `@ConditionalOnMissingClass` không giúp phát hiện điều đó.

## 8. Điều kiện theo property và thứ tự nguồn cấu hình

`@ConditionalOnProperty` kiểm tra giá trị trong Spring `Environment`. Ví dụ:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class SearchConfiguration {

    @Bean
    public SearchService searchService() {
        return new SearchService();
    }
}
~~~

Với cấu hình này:

| Giá trị hiệu lực của `app.search.enabled` | Kết quả |
|---|---|
| `true` | Condition match |
| `false` | Không match |
| Không có property | Không match vì `matchIfMissing = false` |
| `TRUE` | So sánh chuỗi không phân biệt hoa thường theo cách condition xử lý giá trị boolean thông thường; vẫn nên thống nhất cách viết |

Nếu không đặt `havingValue`, condition có quy tắc mặc định xem property có tồn tại và không có giá trị chuỗi `false` hay không. Vì thế, nếu property được đặt thành `no` hoặc một chuỗi khác `false`, kết quả có thể không như người viết tưởng tượng. Khi cần boolean rõ ràng, nên đặt `havingValue = "true"`.

### Property nào có hiệu lực?

Spring Boot có nhiều nguồn cấu hình: file application, file theo profile, biến môi trường, system properties, command line arguments, config data import và nguồn được thêm bởi code. Nguồn có độ ưu tiên cao hơn có thể ghi đè nguồn thấp hơn.

Ví dụ:

`application.yml`:

~~~yaml
app:
  search:
    enabled: false
~~~

Chạy ứng dụng với tham số:

~~~bash
java -jar app.jar --app.search.enabled=true
~~~

Giá trị command line có thể ghi đè giá trị file thông thường, nên condition có thể match dù YAML ghi false.

Nếu condition cho kết quả bất ngờ, hãy tìm **giá trị property hiệu lực** thay vì chỉ đọc một file YAML. Cần xét profile active, biến môi trường, tham số chạy, config import và custom property source.

### Placeholder và tên property

Spring Boot hỗ trợ relaxed binding cho nhiều cách đặt tên property, đặc biệt trong biến môi trường. Tuy nhiên, với condition và key được viết trong annotation, nên dùng canonical kebab-case, ví dụ `app.search.enabled`. Tránh tự đoán ánh xạ nếu property name có dấu gạch, chữ viết tắt hoặc tên phức tạp.

### Không dùng property chưa được nạp tại thời điểm condition chạy

Nếu một property source được đăng ký quá muộn trong lifecycle, condition đã được đánh giá trước đó sẽ không tự động chạy lại chỉ vì property xuất hiện sau. Đưa nguồn cấu hình vào đúng cơ chế và thời điểm nạp của Spring Boot, thay vì thêm property source trong một bean nghiệp vụ sau khi context đã bắt đầu khởi tạo.

## 9. Điều kiện theo bean: OnBeanCondition và các trường hợp khó hiểu

Các annotation phổ biến:

- `@ConditionalOnBean`: yêu cầu bean phù hợp đã có trong registry/context theo thời điểm condition.
- `@ConditionalOnMissingBean`: match khi không tìm thấy bean phù hợp.
- `@ConditionalOnSingleCandidate`: match khi có một candidate duy nhất phù hợp để inject (hoặc một candidate được đánh dấu primary trong trường hợp tương ứng).

Ví dụ:

~~~java
@Bean
@ConditionalOnSingleCandidate(DataSource.class)
public JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
~~~

Nếu có một DataSource candidate duy nhất hoặc một candidate primary theo quy tắc resolution, cấu hình có thể tạo `JdbcTemplate`. Nếu có nhiều DataSource mà không có lựa chọn primary rõ, condition có thể không match.

### Tại sao @ConditionalOnMissingBean đôi khi không nhường chỗ?

Các nguyên nhân thường gặp:

1. **Bean của ứng dụng chưa được đăng ký khi condition chạy.** Condition đánh giá trước khi bean definition dự kiến xuất hiện.
2. **Kiểu return của @Bean quá chung.** Metadata không cho biết chính xác kiểu bean mà factory method sẽ cung cấp.
3. **Bean nằm ngoài vùng component scan.** Lớp có `@Service` hoặc `@Repository` nhưng chưa được phát hiện.
4. **Bean chỉ tồn tại trong profile khác.** Profile hiện tại không đăng ký definition đó.
5. **Tên/kiểu được kiểm tra không đúng.** Bean có thể được đăng ký theo interface hoặc tên khác với điều kiện đang tìm.
6. **Condition có search strategy hoặc thuộc tính khác.** Một context parent/child có thể làm kết quả tìm kiếm khác dự kiến.
7. **Một cấu hình khác đăng ký bean sau đó.** Condition đã match ở thời điểm đánh giá không tự đảo ngược.

Điểm cuối rất quan trọng: condition không phải cơ chế phản ứng liên tục. Khi một bean definition được đăng ký sau, Spring không tự động quay lại và hủy những definition đã được condition trước đó chấp thuận.

### Khai báo return type cụ thể

Ví dụ dễ gây hạn chế metadata:

~~~java
@Bean
public Object customClock() {
    return Clock.systemUTC();
}
~~~

Spring chỉ thấy return type khai báo là `Object` ở mức metadata phương thức, nên các condition dựa trên kiểu `Clock` có thể không nhận diện definition như mong đợi trước khi instance được tạo.

Nên khai báo:

~~~java
@Bean
public Clock customClock() {
    return Clock.systemUTC();
}
~~~

Kiểu trả về cụ thể giúp container và condition hiểu tốt hơn loại bean được cung cấp. Nếu cần trả một implementation cụ thể, khai báo kiểu interface/contract phù hợp mà consumer sẽ sử dụng.

## 10. Thứ tự auto-configuration có thể làm thay đổi kết quả condition

Giả sử hai auto-configuration:

~~~java
@AutoConfiguration
public class DefaultStorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StorageClient.class)
    public StorageClient defaultStorageClient() {
        return new DefaultStorageClient();
    }
}
~~~

~~~java
@AutoConfiguration
public class CloudStorageAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.storage.cloud",
            name = "enabled",
            havingValue = "true"
    )
    public StorageClient cloudStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

Nếu `DefaultStorageAutoConfiguration` được xử lý trước, tại thời điểm đó chưa có `StorageClient` từ cloud config. Bean mặc định có thể được đăng ký. Khi cloud config được xử lý sau, nó có thể thêm một bean thứ hai nếu condition property match. Kết quả là hai candidate cùng kiểu, không phải cloud tự động thay thế default.

Nếu cloud config được xử lý trước, default config có thể nhìn thấy bean cloud và bỏ qua bean mặc định.

Khi auto-configuration có quan hệ phụ thuộc thứ tự, cần khai báo rõ:

~~~java
@AutoConfiguration
@AutoConfigureBefore(DefaultStorageAutoConfiguration.class)
public class CloudStorageAutoConfiguration {
    // ...
}
~~~

Hoặc sắp xếp theo hướng ngược lại tùy mục tiêu. Trong ví dụ, muốn cloud bean có mặt trước khi default condition đánh giá, cloud auto-configuration phải được xử lý trước default auto-configuration.

### Đừng dùng ordering để che một thiết kế condition không rõ

Nếu một auto-configuration cần cung cấp fallback khi người dùng không cấu hình storage, hãy thiết kế rõ điều kiện và thứ tự. Nếu hai implementation có thể cùng hợp lệ, có thể cần `@ConditionalOnMissingBean` cho default và một property/profile có chủ đích cho cloud. Đừng dựa vào việc “bean nào được đăng ký cuối cùng sẽ thắng”; Spring Boot thường không cho phép bean definition overriding theo mặc định ở nhiều cấu hình, và kể cả khi cho phép, kết quả phụ thuộc thứ tự và tên bean, rất khó bảo trì.

### Auto-configuration ordering không phải thứ tự bean instance

`@AutoConfigureBefore` và `@AutoConfigureAfter` điều khiển thứ tự xử lý auto-configuration classes. Chúng không trực tiếp nói singleton nào phải khởi tạo trước singleton nào. Khi cần thứ tự khởi tạo, hãy dùng quan hệ dependency hoặc `@DependsOn` cho trường hợp thật sự cần thiết.

## 11. Conditions ở cấp class và cấp @Bean method

Điều kiện có thể đặt trên configuration class:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }

    @Bean
    public AuditRepository auditRepository() {
        return new AuditRepository();
    }
}
~~~

Nếu condition trên class không match, toàn bộ cấu hình có thể bị bỏ qua, do đó các bean methods bên trong không được đăng ký từ configuration này.

Hoặc đặt điều kiện trên từng bean method:

~~~java
@Configuration
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "publisher-enabled",
            havingValue = "true"
    )
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "repository-enabled",
            havingValue = "true"
    )
    public AuditRepository auditRepository() {
        return new AuditRepository();
    }
}
~~~

Lúc này mỗi bean method có điều kiện riêng. Có thể một bean được đăng ký và bean còn lại bị bỏ qua.

Cần kiểm tra các dependency giữa chúng: nếu `AuditPublisher` bắt buộc cần `AuditRepository` nhưng repository bị tắt, context có thể lỗi khi tạo publisher. Điều kiện độc lập không tự hiểu rằng các bean có quan hệ logic và phải bật/tắt cùng nhau.

## 12. Conditions trên component và configuration import

Condition cũng có thể xuất hiện trên component class hoặc lớp được import. Nhưng cần hiểu cơ chế đăng ký tương ứng.

Ví dụ:

~~~java
@Component
@Profile("dev")
public class LocalPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Khi profile `dev` active, component scan có thể đăng ký bean. Khi profile khác, bean không được đăng ký từ class này.

Với cấu hình được import:

~~~java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {
    // ...
}
~~~

Nếu profile không phù hợp, cấu hình có thể bị bỏ qua, các bean definitions bên trong cũng không được tạo.

Một bean có thể bị loại vì condition ở nhiều tầng: lớp configuration không được xử lý, bean method không match, component scan không tìm thấy, hoặc một auto-configuration bị exclude. Khi điều tra, hãy xác định **condition nào thực sự được đánh giá và trên metadata nào**.

## 13. Custom Condition và phase phù hợp

Có thể tự tạo condition bằng cách implement `Condition`:

~~~java
public class ExternalFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        Environment environment = context.getEnvironment();

        return environment.getProperty(
                "app.external.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Dùng:

~~~java
@Configuration
@Conditional(ExternalFeatureCondition.class)
public class ExternalFeatureConfiguration {
    // ...
}
~~~

Nếu condition chỉ đọc property, có thể dùng `@ConditionalOnProperty` để code ngắn hơn. Custom condition hữu ích khi logic kiểm tra phức tạp hơn hoặc cần kết hợp nhiều yếu tố.

Nếu condition phụ thuộc vào bean definition đã đăng ký, nên xem xét `ConfigurationCondition` và phase `REGISTER_BEAN`:

~~~java
public class RepositoryPresentCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        BeanFactory factory = context.getBeanFactory();

        return factory instanceof ListableBeanFactory listable
                && listable.getBeanNamesForType(
                        CustomerRepository.class,
                        false,
                        false
                ).length > 0;
    }
}
~~~

Đoạn code là minh họa cho ý tưởng chọn phase; trong một condition thư viện cần tương thích nhiều loại registry/bean factory, phải xử lý trường hợp không có `ListableBeanFactory` hoặc không thể truy vấn kiểu theo cách mong muốn.

Một custom condition nên:

- Có kết quả xác định từ metadata/environment/registry mà nó được phép quan sát.
- Không tạo bean instance hoặc thực hiện side effect.
- Không gọi dịch vụ ngoài hoặc truy cập database để quyết định cấu hình.
- Tránh phụ thuộc vào bean được tạo sau phase của nó.
- Có thông báo rõ để điều tra khi condition không match.

Condition được gọi trong quá trình xây dựng context; thực hiện I/O hoặc thay đổi trạng thái trong `matches` sẽ làm khởi động khó dự đoán và có thể bị gọi nhiều lần.

## 14. @ConditionalOnExpression có thể gây bất ngờ

Spring Boot cung cấp `@ConditionalOnExpression` để dùng SpEL:

~~~java
@Configuration
@ConditionalOnExpression(
        "${app.feature.enabled:false} and '${app.region:local}' == 'local'"
)
public class LocalFeatureConfiguration {
    // ...
}
~~~

Cách này linh hoạt nhưng dễ làm biểu thức dài, khó đọc và khó chẩn đoán. Với điều kiện property đơn giản, `@ConditionalOnProperty` thường rõ ràng hơn.

Ngoài ra, dùng SpEL tham chiếu bean trong expression có thể khiến bean được khởi tạo rất sớm để đánh giá condition, trước khi các post-processor khác xử lý đầy đủ. Điều này có thể tạo side effect hoặc làm bean không được xử lý như kỳ vọng. Tránh dùng bean reference trong conditional expression để quyết định cấu hình; hãy dựa vào property hoặc metadata có sẵn.

## 15. Tại sao bean có mặt dù condition tưởng là false?

Một vài tình huống thường gặp:

### Một nguồn đăng ký khác cung cấp cùng kiểu bean

Bạn loại bean khỏi một auto-configuration hoặc condition không match, nhưng một component scan hoặc `@Bean` khác vẫn đăng ký implementation cùng kiểu. Condition chỉ ngăn một nguồn đăng ký, không xóa bean từ toàn context.

### Condition được đặt trên cấu hình khác với bean đang quan sát

Có thể condition đặt trên một class nhưng bean được đăng ký bởi một configuration khác, hoặc bean đến từ auto-configuration khác. Cần xác định bean name, resource/source và bean definition thực tế.

### Property hiệu lực khác file đang xem

Biến môi trường, command line, profile-specific config hoặc config import ghi đè YAML. Hãy xem property value hiệu lực và nguồn của nó.

### Điều kiện kiểm tra kiểu khác với kiểu đang inject

Bean được đăng ký theo implementation hoặc interface khác; condition có thể kiểm tra một kiểu cụ thể không trùng với kiểu khai báo/metadata mà Spring đang nhận diện.

### Component scan khác vẫn tìm thấy class

Exclude filter của một lần scan không phải lệnh loại bean toàn context. Nếu class nằm trong vùng scan của một configuration khác, nó có thể được đăng ký từ lần scan đó.

## 16. Tại sao bean vắng mặt dù condition tưởng là true?

### Class chỉ có trên compile classpath

Dependency có thể ở scope không được đưa vào runtime. Kiểm tra runtime classpath và artifact triển khai, không chỉ file build.

### Profile chưa active

`@Profile("prod")` không match nếu profile prod chưa được kích hoạt. Kiểm tra `spring.profiles.active` và profile group/configuration liên quan.

### Property không tồn tại hoặc có giá trị khác

Nếu `matchIfMissing` là false, thiếu property khiến condition không match. Nếu `havingValue` được khai báo, giá trị phải phù hợp. Kiểm tra property source có hiệu lực.

### Bean cần thiết chưa được đăng ký khi condition đánh giá

Đặc biệt với `@ConditionalOnBean`, cấu hình cung cấp bean có thể được xử lý sau. Xem thứ tự auto-configuration, import và phase condition.

### Có nhiều bean candidate

`@ConditionalOnSingleCandidate` có thể không match nếu nhiều candidate không có một primary candidate phù hợp.

### Configuration class không được import hoặc scan

Một lớp cấu hình tồn tại trong source code không có nghĩa Spring tự xử lý nó. Nó cần được component scan, import hoặc đăng ký theo cơ chế phù hợp.

### Một condition khác trên class hoặc method đã loại bean

Nhiều condition có thể được áp dụng cùng lúc. Chỉ cần một điều kiện không match là bean/configuration có thể bị bỏ qua.

## 17. Đọc Condition Evaluation Report

Spring Boot có thể cung cấp báo cáo giải thích auto-configuration nào match hoặc không match. Đây là một trong những công cụ hữu ích nhất khi bean xuất hiện hoặc biến mất ngoài dự kiến.

### Bật debug khi khởi động

Có thể chạy ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Hoặc cấu hình logging/debug phù hợp trong môi trường phát triển. Spring Boot sẽ ghi báo cáo condition evaluation với các nhóm:

- Positive matches: cấu hình/condition đã match.
- Negative matches: cấu hình không match.
- Exclusions: auto-configuration bị loại khỏi quá trình import.
- Unconditional classes: cấu hình không phụ thuộc condition theo cách tương ứng.

Báo cáo có thể cho biết một auto-configuration bị bỏ qua vì thiếu class, property không phù hợp hoặc bean đã tồn tại. Hãy đọc phần **negative match message** để tìm lý do cụ thể, thay vì chỉ tìm tên class.

### Actuator conditions endpoint

Nếu ứng dụng đã tích hợp Spring Boot Actuator và endpoint conditions được expose/configure phù hợp, thông tin condition có thể được quan sát qua endpoint quản trị tương ứng. Việc expose endpoint cần được kiểm soát bảo mật; không nên công khai thông tin cấu hình nội bộ trên production.

### Phân biệt condition report với danh sách bean

Condition report giải thích kết quả đánh giá condition, nhưng không thay thế việc kiểm tra bean definition thực tế. Một bean có thể được đăng ký từ nguồn khác dù auto-configuration liên quan không match. Khi cần, hãy truy vấn ApplicationContext hoặc xem metadata bean definition để xác định nguồn đăng ký.

## 18. Kiểm thử điều kiện bằng ApplicationContextRunner

Khi phát triển auto-configuration hoặc condition, `ApplicationContextRunner` giúp kiểm thử các biến thể cấu hình trong một context nhỏ mà không cần khởi động toàn bộ ứng dụng.

Ví dụ ý tưởng:

~~~java
class MailAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MailAutoConfiguration.class
                            )
                    );

    @Test
    void createsMailSenderWhenEnabled() {
        contextRunner
                .withPropertyValues("app.mail.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(MailSender.class);
                });
    }

    @Test
    void doesNotCreateMailSenderWhenDisabled() {
        contextRunner
                .withPropertyValues("app.mail.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(MailSender.class);
                });
    }
}
~~~

Đây là skeleton kiểm thử; các class `MailAutoConfiguration`, `MailSender` và assertion library cần có trong dự án. `ApplicationContextRunner` thuộc Spring Boot test support và đặc biệt hữu ích để kiểm tra auto-configuration.

Có thể bổ sung các tình huống:

- Property bị thiếu.
- Property được ghi đè bằng giá trị khác.
- Bean tùy chỉnh được đăng ký trước để kiểm tra `@ConditionalOnMissingBean`.
- Có hai bean candidate để kiểm tra `@ConditionalOnSingleCandidate`.
- Class optional có hoặc không có trên classpath.
- Profile khác nhau.
- Hai auto-configuration được sắp xếp trước/sau.

### Kiểm tra bean người dùng thay thế default

~~~java
contextRunner
        .withBean(MailSender.class, CustomMailSender::new)
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(MailSender.class);
            assertThat(context.getBean(MailSender.class))
                    .isInstanceOf(CustomMailSender.class);
        });
~~~

Đoạn này minh họa cách đưa bean tùy chỉnh vào context test để xem auto-configuration mặc định có nhường chỗ hay không. Cú pháp chính xác phụ thuộc phiên bản Spring Boot Test đang sử dụng.

## 19. Một quy trình chẩn đoán có hệ thống

Khi bean không xuất hiện hoặc xuất hiện ngoài dự kiến, hãy đi theo trình tự:

~~~text
Bean thực tế khác kỳ vọng
          |
          v
Xác định bean name và type
          |
          v
Tìm tất cả nguồn đăng ký:
component scan, @Bean, @Import,
registrar, auto-configuration
          |
          v
Xác định condition nào áp dụng
ở cấp class và method
          |
          v
Kiểm tra phase và thứ tự xử lý
(PARSE_CONFIGURATION / REGISTER_BEAN)
          |
          v
Kiểm tra classpath, property,
profile và các bean definitions
đã có ở thời điểm condition chạy
          |
          v
Đọc Condition Evaluation Report
          |
          v
Tạo context test tái hiện điều kiện
          |
          v
Sửa đúng nguồn đăng ký hoặc ordering
~~~

Một bảng câu hỏi nhanh:

| Triệu chứng | Cần kiểm tra trước |
|---|---|
| Default bean vẫn xuất hiện dù đã tự khai báo bean | Bean tùy chỉnh có được đăng ký trước condition không? Kiểu return có đủ cụ thể không? |
| Bean conditional không xuất hiện | Condition nào không match? Property/class/bean/profile nào thiếu? |
| Hai implementation cùng xuất hiện | Hai nguồn đăng ký nào cung cấp bean? Condition của default có thấy custom bean không? |
| Chỉ lỗi ở production | Runtime classpath, profile, property source, environment và hạ tầng khác gì? |
| ConditionOnBean không thấy bean | Bean definition đã có trước thời điểm condition chạy chưa? |
| Auto-configuration chạy sai thứ tự mong muốn | Có cần @AutoConfigureBefore/After/Order không? |
| @Order không thay đổi condition | Đang dùng @Order sai mục đích; cần ordering của auto-configuration hoặc dependency phù hợp |
| Bean được tạo nhưng khởi tạo thất bại | Phân biệt condition match với constructor/dependency/lifecycle failure |

## 20. Các nguyên tắc thiết kế điều kiện dễ dự đoán

1. **Dùng điều kiện phù hợp với loại thông tin.** Classpath dùng `@ConditionalOnClass`; property dùng `@ConditionalOnProperty`; profile dùng `@Profile`; bean hiện có dùng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`.
2. **Dùng @ConditionalOnMissingBean chủ yếu cho auto-configuration.** Đây là cách cung cấp default mà vẫn cho ứng dụng quyền override.
3. **Đừng dựa vào bean sẽ được đăng ký trong tương lai.** Condition nhìn thấy registry tại thời điểm đánh giá; nó không tự chạy lại sau đó.
4. **Khai báo return type của @Bean đủ cụ thể.** Metadata kiểu chính xác giúp condition và autowiring nhận diện bean đúng hơn.
5. **Dùng ordering chuyên biệt cho auto-configuration.** `@AutoConfigureBefore`, `@AutoConfigureAfter` và `@AutoConfigureOrder` có mục đích khác `@Order` và `@DependsOn`.
6. **Không dùng condition để thực hiện I/O.** Không gọi database, HTTP hoặc thay đổi trạng thái trong `matches`.
7. **Giữ điều kiện ở cấp phù hợp.** Nếu cả cấu hình cùng bật/tắt, đặt condition ở class; nếu từng bean độc lập, đặt ở bean method.
8. **Kiểm soát nhiều nguồn đăng ký.** Exclude một auto-configuration không loại bean cùng kiểu từ component scan hoặc `@Bean` khác.
9. **Kiểm thử cả trường hợp match và không match.** Property thiếu, profile khác, custom bean, nhiều candidate và classpath optional đều có thể thay đổi kết quả.
10. **Dùng condition report để giải thích kết quả.** Đừng suy luận chỉ từ một file YAML hoặc một annotation.

## Kết luận

Điều kiện bean trong Spring Boot được đánh giá trong quá trình phân tích cấu hình và đăng ký bean definitions, trước khi phần lớn instance được khởi tạo. Vì vậy, kết quả phụ thuộc vào **phase của condition, thứ tự xử lý configuration/auto-configuration, metadata classpath, property hiệu lực, profile và các bean definition đã tồn tại ở thời điểm đánh giá**.

`@ConditionalOnBean` và `@ConditionalOnMissingBean` đặc biệt nhạy với thứ tự registry; các điều kiện classpath và property dựa trên những nguồn thông tin khác. `@AutoConfigureBefore`, `@AutoConfigureAfter` và `@AutoConfigureOrder` giúp sắp xếp auto-configuration khi cần, còn `@Order` và `@DependsOn` giải quyết các vấn đề khác.

Khi kết quả khác dự đoán, hãy xác định bean đến từ nguồn nào, condition nào áp dụng, condition được đánh giá ở phase nào và giá trị/definition nào đã có tại thời điểm đó. Kết hợp Condition Evaluation Report với một context test nhỏ sẽ giúp giải thích chính xác vì sao Spring Boot chọn hoặc bỏ qua một cấu hình.
