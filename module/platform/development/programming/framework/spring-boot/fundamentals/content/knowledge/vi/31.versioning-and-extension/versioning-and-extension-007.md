# @Fallback và các tiện ích chỉ có ở Spring Framework mới

Khi một ứng dụng Spring có nhiều bean cùng triển khai một interface, container cần quyết định bean nào sẽ được inject vào một dependency. Trước đây, các lựa chọn thường dùng là `@Primary`, `@Qualifier`, profile và các điều kiện tạo bean. Từ **Spring Framework 6.2**, cơ chế chọn bean có thêm `@Fallback` và thuộc tính `defaultCandidate` của `@Bean`, giúp mô tả rõ hơn bean mặc định và bean dự phòng.

Spring Framework 6.2 cũng đưa vào Spring Test các annotation override bean như `@TestBean`, `@MockitoBean` và `@MockitoSpyBean`. Chúng cung cấp cách thay thế hoặc spy bean trong test context theo cơ chế thống nhất của Spring Test.

Bài học này tập trung vào những tiện ích đó và cách dùng chúng trong ứng dụng Spring Boot:

- Hiểu `@Fallback` và cách nó ảnh hưởng đến autowiring.
- Phân biệt `@Fallback`, `@Primary`, `@Qualifier` và `@Bean(defaultCandidate = false)`.
- Hiểu cách chọn bean theo tên tham số trong các tình huống injection phù hợp.
- Dùng `@TestBean`, `@MockitoBean` và `@MockitoSpyBean` để thay bean trong test.
- Xác định Spring Framework version thực tế mà Spring Boot đang quản lý.
- Tránh dùng API mới trên runtime cũ hoặc nâng riêng Spring Framework gây lệch dependency.

## 1. Spring Framework và Spring Boot là hai lớp khác nhau

Spring Boot xây dựng trên Spring Framework và quản lý một tập dependency tương thích thông qua dependency management/BOM.

- **Spring Framework** cung cấp IoC container, dependency injection, AOP, transaction, web stack và Spring Test.
- **Spring Boot** cung cấp auto-configuration, starters, externalized configuration, Actuator và quy ước để xây dựng ứng dụng nhanh hơn.
- **Spring Boot version** thường quyết định phiên bản Spring Framework được quản lý trong một project.

Ví dụ, `@Fallback` là annotation của **Spring Framework**, nằm trong package:

```java
org.springframework.context.annotation.Fallback
```

Các annotation bean override như `@MockitoBean` cũng thuộc Spring Test, không phải annotation riêng của Spring Boot.

Điều này quan trọng khi đọc tài liệu: một tính năng được giới thiệu trong Spring Framework 6.2 có thể dùng trong ứng dụng Spring Boot nếu project đang chạy với Spring Framework tương thích. Chỉ nâng Spring Boot starter hoặc chỉ thêm một import không tự làm cho class mới xuất hiện nếu runtime vẫn dùng Framework cũ.

## 2. Xác định phiên bản giới thiệu tính năng

Các tiện ích chính trong bài được giới thiệu trong **Spring Framework 6.2**:

| Tiện ích | Spring Framework | Package chính |
|---|---:|---|
| `@Fallback` | 6.2+ | `org.springframework.context.annotation` |
| `@Bean(defaultCandidate = false)` | 6.2+ | `org.springframework.context.annotation.Bean` |
| Cải thiện shortcut chọn bean theo parameter name | 6.2+ | Autowire candidate resolution |
| `@TestBean` | 6.2+ | `org.springframework.test.context.bean.override.convention` |
| `@MockitoBean` | 6.2+ | `org.springframework.test.context.bean.override.mockito` |
| `@MockitoSpyBean` | 6.2+ | `org.springframework.test.context.bean.override.mockito` |

Spring Boot 3.4 trở lên thường quản lý Spring Framework 6.2.x; các dòng Boot cũ hơn có thể quản lý Framework 6.1.x hoặc cũ hơn. Đây là quan hệ theo BOM của từng dòng phát hành, nên hãy kiểm tra version hiệu lực của project thay vì suy luận chỉ từ tên starter.

Nếu project đang ở Framework 6.1, code import `@Fallback` hoặc dùng `defaultCandidate` có thể không compile. Không nên nâng riêng `spring-context` lên một minor version khác với các module Spring còn lại để ép tính năng hoạt động.

## 3. Bài toán nhiều bean cùng interface

Giả sử ứng dụng có interface:

```java
public interface PaymentGateway {
    String providerName();

    PaymentResult charge(PaymentRequest request);
}
```

Có một implementation dùng nhà cung cấp thanh toán chính:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "remote";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        // Gọi payment provider qua client đã cấu hình.
        return PaymentResult.accepted();
    }
}
```

Và một implementation dự phòng hoặc mô phỏng:

```java
@Component
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "local";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        // Behavior minh họa dành cho local/test.
        return PaymentResult.accepted();
    }
}
```

Một service inject theo interface:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedProvider() {
        return paymentGateway.providerName();
    }
}
```

Nếu cả hai bean đều được đăng ký và không có quy tắc chọn candidate, Spring có thể báo `NoUniqueBeanDefinitionException`.

Câu hỏi không chỉ là “bean nào tồn tại?” mà còn là “bean nào nên được xem là lựa chọn mặc định khi consumer chỉ yêu cầu một `PaymentGateway`?”

## 4. @Primary: đánh dấu bean được ưu tiên

`@Primary` đã có từ lâu trong Spring. Nó đánh dấu một bean được ưu tiên khi có nhiều candidates phù hợp cho một injection point đơn trị.

Ví dụ:

```java
@Component
@Primary
public class RemotePaymentGateway implements PaymentGateway {
    // Implementation chính.
}
```

```java
@Component
public class LocalPaymentGateway implements PaymentGateway {
    // Implementation phụ.
}
```

Khi `CheckoutService` inject một `PaymentGateway`, `RemotePaymentGateway` được chọn vì nó là primary candidate.

Các điểm cần nhớ:

- `@Primary` không ngăn bean khác được tạo.
- Bean không primary vẫn có thể được inject bằng qualifier.
- Nếu có nhiều primary candidates cùng phù hợp, Spring vẫn có thể không xác định được một bean duy nhất.
- `@Primary` chủ yếu ảnh hưởng đến việc chọn một bean cho injection point đơn trị; nó không phải cách lọc collection.

Ví dụ:

```java
@Autowired
PaymentGateway paymentGateway;
```

có thể nhận `RemotePaymentGateway`, trong khi:

```java
@Autowired
List<PaymentGateway> paymentGateways;
```

vẫn có thể nhận cả hai implementation phù hợp.

## 5. @Fallback là gì?

Spring Framework 6.2 giới thiệu `@Fallback` để đánh dấu một bean là **ứng viên dự phòng**.

```java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Component
@Fallback
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "local";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return PaymentResult.accepted();
    }
}
```

Bean chính không cần `@Primary`:

```java
@Component
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public String providerName() {
        return "remote";
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return PaymentResult.accepted();
    }
}
```

Với một injection point yêu cầu một `PaymentGateway`, nếu có một regular candidate và một fallback candidate, regular candidate được ưu tiên. Trong ví dụ này, service nhận `RemotePaymentGateway`.

Nếu không có regular candidate phù hợp và chỉ có một fallback candidate, Spring có thể chọn bean fallback đó.

**Ý nghĩa:** `@Fallback` không phải annotation tạo bean hay kích hoạt profile. Nó thay đổi cách container xếp hạng các bean đã được đăng ký khi giải quyết autowiring.

## 6. So sánh @Primary và @Fallback

Hai annotation thể hiện hai ý định đối lập:

- `@Primary`: bean này là lựa chọn ưu tiên.
- `@Fallback`: bean này chỉ nên được chọn khi không có lựa chọn thông thường phù hợp.

| Tình huống | Kết quả chọn bean đơn trị |
|---|---|
| Một regular bean, một fallback bean | Regular bean |
| Chỉ có một fallback bean | Fallback bean |
| Một primary bean và các candidate khác | Primary bean |
| Nhiều regular bean, không có primary/qualifier | Có thể ambiguous |
| Nhiều fallback bean, không có regular candidate | Có thể ambiguous |
| Có qualifier xác định rõ candidate | Candidate phù hợp qualifier được chọn theo quy tắc resolution |

Ví dụ dễ nhớ:

```text
PaymentGateway candidates
       │
       ├── RemotePaymentGateway (regular)
       │
       └── LocalPaymentGateway  (@Fallback)
                    │
                    ▼
       Inject một PaymentGateway
                    │
                    ▼
           RemotePaymentGateway
```

Nếu bỏ remote bean khỏi context và local là fallback candidate duy nhất, local có thể được chọn.

Không nên gắn `@Primary` và `@Fallback` lên cùng một bean để biểu đạt hai ý định trái nhau. Hãy chọn annotation phản ánh chính sách rõ ràng.

## 7. @Fallback không phải fallback nghiệp vụ

`@Fallback` chỉ điều khiển candidate resolution của Spring. Nó không tự thực hiện retry, circuit breaker, failover hoặc chuyển request khi remote provider gặp lỗi.

Ví dụ, nếu `RemotePaymentGateway` tồn tại và được chọn nhưng khi gọi network bị timeout, Spring không tự chuyển sang `LocalPaymentGateway` chỉ vì bean local có `@Fallback`.

Đây là hai tầng khác nhau:

| Tầng | Cơ chế |
|---|---|
| Chọn bean lúc tạo/inject context | `@Primary`, `@Fallback`, `@Qualifier`, candidate rules |
| Chuyển provider khi runtime call thất bại | Resilience logic, routing service, circuit breaker, retry hoặc failover code |

Không dùng `@Fallback` để giả định ứng dụng tự chuyển sang provider khác khi request thất bại. Nếu cần failover runtime, hãy xây dựng một component điều phối và test hành vi đó riêng.

## 8. @Fallback trên @Bean method

Có thể đánh dấu bean fallback bằng annotation trên method `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway remotePaymentGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Fallback
    PaymentGateway localPaymentGateway() {
        return new LocalPaymentGateway();
    }
}
```

Ở đây, hai bean cùng type được đăng ký. Bean local vẫn tồn tại trong context nhưng được đánh dấu là fallback candidate.

Cách này hữu ích khi implementation được tạo từ factory method hoặc cần cấu hình constructor dependencies trước khi tạo object.

Có thể đặt `@Fallback` trực tiếp trên class bean như ví dụ component ở phần trước. Chọn một cách đăng ký phù hợp, tránh đăng ký cùng một implementation hai lần qua component scanning và `@Bean`.

## 9. Dùng fallback khi không có bean thông thường

Ví dụ một module cần `Clock`. Ứng dụng có thể cung cấp clock chính, còn module library có clock mặc định:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @Fallback
    Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

Application configuration có thể cung cấp clock chính:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Một service inject `Clock` theo type sẽ nhận regular `businessClock` khi cả hai đều tồn tại.

Nếu application không cung cấp clock riêng, `defaultClock` có thể trở thành lựa chọn duy nhất.

Thiết kế này thường hữu ích cho reusable configuration hoặc library muốn cung cấp default behavior mà vẫn cho phép ứng dụng ghi đè.

**Chú ý:** fallback chỉ phù hợp nếu default thực sự an toàn. Không nên cung cấp một fallback giả cho payment gateway hoặc security provider nếu nó khiến ứng dụng có vẻ hoạt động nhưng bỏ qua yêu cầu nghiệp vụ bắt buộc.

## 10. @Qualifier vẫn dùng khi cần chọn chính xác

`@Qualifier` thể hiện rằng một injection point cần một candidate cụ thể theo qualifier.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Qualifier("primary")
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Qualifier("local")
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Consumer cần local một cách tường minh:

```java
@Service
public class OfflineCheckoutService {

    private final PaymentGateway paymentGateway;

    public OfflineCheckoutService(
            @Qualifier("local") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Consumer thông thường không ghi qualifier có thể nhận regular candidate.

Đừng dùng `@Fallback` để thay thế qualifier nếu consumer cần **một implementation cụ thể theo chức năng**. Fallback là chính sách ưu tiên chung; qualifier là chỉ dẫn chọn candidate cho injection point.

## 11. @Bean(defaultCandidate = false) trong Spring Framework 6.2

Spring Framework 6.2 bổ sung thuộc tính `defaultCandidate` cho `@Bean`.

```java
@Bean(defaultCandidate = false)
@Qualifier("special")
SpecialClient specialClient() {
    return new SpecialClient();
}
```

Bean vẫn được đăng ký trong application context, nhưng không được xem là default candidate cho autowiring không chỉ định rõ. Nó vẫn có thể được lấy bằng tên hoặc được chọn qua qualifier phù hợp.

Ví dụ consumer cần bean đặc biệt:

```java
@Service
public class SpecialJob {

    private final SpecialClient client;

    public SpecialJob(
            @Qualifier("special") SpecialClient client) {
        this.client = client;
    }
}
```

Điều này hữu ích khi một module cung cấp một bean bổ sung cùng type để phục vụ use case riêng, nhưng không muốn bean đó gây ambiguity cho các injection point thông thường.

`defaultCandidate = false` không có nghĩa bean bị disable hoặc không được tạo. Nó vẫn là một bean trong container và có thể được truy cập theo cách tường minh.

## 12. Phân biệt @Fallback và defaultCandidate = false

Hai cơ chế đều ảnh hưởng đến candidate selection nhưng thể hiện ý định khác nhau:

- `@Fallback`: bean vẫn là ứng viên dự phòng cho autowiring; có thể được chọn nếu không còn regular candidate phù hợp.
- `@Bean(defaultCandidate = false)`: bean không phải default autowire candidate; muốn dùng nó thì nên chỉ định rõ qualifier hoặc bean name.

| Tình huống | `@Fallback` | `defaultCandidate=false` |
|---|---|---|
| Bean được tạo trong context | Có | Có |
| Được chọn khi có regular candidate | Thường không cho injection đơn trị | Không phải default candidate |
| Có thể dùng làm lựa chọn khi chỉ còn fallback | Có, nếu candidate resolution xác định được một bean | Không phải mục đích của cơ chế này |
| Có thể chọn tường minh bằng qualifier/name | Có | Có |
| Cách khai báo | Annotation trên class hoặc `@Bean` method | Thuộc tính trên `@Bean` |
| Ý định | Dự phòng tự động | Bean phụ, chỉ dùng khi yêu cầu rõ |

Không dùng hai cơ chế thay thế cho nhau chỉ vì cả hai đều làm một bean ít được chọn hơn.

## 13. Ví dụ defaultCandidate=false với hai client cùng type

Giả sử có client chính và client dành riêng cho audit:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    ApiClient apiClient() {
        return new ApiClient("general");
    }

    @Bean(defaultCandidate = false)
    @Qualifier("audit")
    ApiClient auditApiClient() {
        return new ApiClient("audit");
    }
}
```

Consumer thông thường:

```java
@Service
public class CatalogService {

    private final ApiClient apiClient;

    public CatalogService(ApiClient apiClient) {
        this.apiClient = apiClient;
    }
}
```

Consumer audit:

```java
@Service
public class AuditService {

    private final ApiClient apiClient;

    public AuditService(@Qualifier("audit") ApiClient apiClient) {
        this.apiClient = apiClient;
    }
}
```

Mục tiêu là để `CatalogService` nhận client chung, còn `AuditService` chọn client audit theo qualifier.

Nếu bỏ `defaultCandidate=false` và không có qualifier/primary nào khác, việc có hai default candidates cùng type có thể khiến injection đơn trị trở nên ambiguous.

## 14. Candidate resolution và injection collection

`@Primary` và `@Fallback` chủ yếu giúp giải quyết injection cần một bean duy nhất. Khi inject collection, ứng dụng thường muốn nhận toàn bộ candidates phù hợp.

Ví dụ:

```java
@Service
public class GatewayRegistry {

    private final List<PaymentGateway> gateways;

    public GatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
```

Collection injection là một use case khác với việc chọn một bean duy nhất. Đừng dùng `@Fallback` với kỳ vọng bean fallback sẽ tự biến mất khỏi mọi danh sách hoặc map bean.

Nếu logic nghiệp vụ cần chỉ lấy một nhóm bean, hãy dùng qualifier phù hợp, thiết kế marker interface, custom qualifier annotation hoặc lọc theo metadata/domain rule rõ ràng.

Ví dụ lấy tất cả bean theo type:

```java
Map<String, PaymentGateway> allGateways =
        applicationContext.getBeansOfType(PaymentGateway.class);
```

Bean fallback vẫn là bean trong context và có thể được nhìn thấy qua các API liệt kê bean. Candidate ranking không phải cơ chế xóa bean khỏi container.

## 15. Parameter name matching trong injection

Spring có thể dùng tên tham số để phân giải dependency trong một số tình huống khi không có chỉ dẫn khác rõ ràng.

Ví dụ có hai bean:

```java
@Bean
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}
```

Constructor:

```java
public CheckoutService(PaymentGateway remoteGateway) {
    this.paymentGateway = remoteGateway;
}
```

Nếu parameter name metadata được giữ lại và các điều kiện resolution phù hợp, tên `remoteGateway` có thể giúp Spring chọn bean cùng tên khi không có qualifier/primary rule chi phối.

Tuy nhiên, đây là một cơ chế resolution dựa trên tên trong ngữ cảnh nhất định, không nên dùng như thay thế cho contract rõ ràng của `@Qualifier`.

Trong Spring Framework 6.2, việc matching theo bean name có một fast shortcut trong các trường hợp phù hợp, giúp tránh toàn bộ quá trình tìm candidates khi tên parameter khớp bean name. Cơ chế này không biến mọi constructor parameter thành một qualifier bất biến.

## 16. Vì sao cần compiler giữ parameter names?

Tên parameter Java có thể không được giữ trong bytecode nếu project không bật compiler option tương ứng.

Với Maven compiler plugin, cấu hình thường dùng:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Với Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Nếu parameter name không có trong metadata, Spring không thể dựa vào tên source code mà compiler đã loại bỏ.

Hãy ưu tiên `@Qualifier` cho những injection point có ý nghĩa nghiệp vụ cụ thể. Parameter-name matching nên được xem là tiện ích bổ sung, không phải cách duy nhất bảo đảm bean resolution.

## 17. Khi nào nên dùng @Primary, @Fallback, Qualifier hay defaultCandidate?

| Nhu cầu | Cơ chế nên cân nhắc |
|---|---|
| Có một implementation mặc định rõ ràng | `@Primary` |
| Có một implementation dự phòng nếu không có lựa chọn thông thường | `@Fallback` |
| Consumer cần implementation cụ thể | `@Qualifier` |
| Bean phụ chỉ nên được dùng khi gọi tên/qualifier rõ | `@Bean(defaultCandidate=false)` |
| Chọn bean theo profile/môi trường | `@Profile` |
| Chỉ tạo bean khi property/condition thỏa | `@Conditional...` |

Ví dụ quyết định:

- `RemotePaymentGateway` là provider chính: có thể là regular bean hoặc `@Primary`.
- `LocalPaymentGateway` chỉ dùng khi không có provider khác: `@Fallback`.
- `AuditApiClient` chỉ dùng trong `AuditService`: `@Qualifier` kết hợp `defaultCandidate=false`.
- `DevPaymentGateway` chỉ tồn tại ở dev: `@Profile("dev")`.

Các cơ chế này có thể kết hợp, nhưng mỗi annotation nên diễn tả một quy tắc có chủ đích. Tránh xếp chồng annotation chỉ để làm Spring “chọn được một cái”.

## 18. Spring Test bean overriding là gì?

Spring Framework 6.2 đưa cơ chế bean overriding vào Spring Test với các annotation:

- `@TestBean`: thay bean bằng object do test factory method cung cấp.
- `@MockitoBean`: tạo Mockito mock và đăng ký/ghi đè bean trong test context.
- `@MockitoSpyBean`: tạo spy từ bean hiện có.

Các annotation này cho phép test thay một dependency mà không cần tự viết một configuration class riêng cho mọi trường hợp.

Ví dụ, `CheckoutService` cần `PaymentGateway`, nhưng test chỉ muốn kiểm tra cách service phản ứng với kết quả bị từ chối. Có thể thay bean thật bằng Mockito mock trong test context.

Cơ chế override thuộc Spring Test. Nó không thay đổi cách production application đăng ký bean và không nên được import vào main source code.

## 19. @MockitoBean: thay bean bằng Mockito mock

Ví dụ:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void handlesAcceptedPayment() {
        given(paymentGateway.providerName())
                .willReturn("mock-provider");

        assertThat(checkoutService.selectedProvider())
                .isEqualTo("mock-provider");
    }
}
```

`@MockitoBean` tạo mock và đưa nó vào test application context. Theo mặc định, cơ chế override có thể thay bean phù hợp nếu tồn tại hoặc đăng ký mock mới tùy cấu hình/target resolution.

Nếu có nhiều beans cùng type, hãy xác định bean mục tiêu bằng qualifier hoặc tên field phù hợp. Đừng để test vô tình mock nhầm implementation.

Các static import `given`, `willReturn` đến từ Mockito BDD API; có thể dùng `when(...).thenReturn(...)` nếu project dùng style đó.

## 20. Dùng @MockitoBean khi cần bảo đảm bean phải tồn tại

Khi mục tiêu là thay thế **một bean đã được application context khai báo**, có thể yêu cầu override mode thay thế bean hiện có thay vì âm thầm tạo bean mới, bằng thuộc tính `enforceOverride` trong các API tương ứng.

Ví dụ:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
```

Cách này giúp test thất bại nếu không tìm thấy bean để thay thế, tùy candidate/qualifier resolution của test context.

Hữu ích khi muốn bảo đảm test đang mock đúng dependency của production wiring. Nếu bean không tồn tại vì profile sai hoặc component scan sai, test không nên tạo một mock mới rồi che lấp lỗi đó.

Hãy xác minh các thuộc tính annotation theo Spring Framework version đang dùng; không copy API 6.2 vào project chạy Framework cũ.

## 21. Chọn bean cụ thể để mock

Nếu application có hai `PaymentGateway`, chỉ ghi:

```java
@MockitoBean
PaymentGateway paymentGateway;
```

có thể không đủ thông tin để chọn một bean mục tiêu trong context.

Có thể kết hợp qualifier:

```java
@MockitoBean
@Qualifier("remoteGateway")
PaymentGateway paymentGateway;
```

Hoặc dùng tên field tương ứng bean name khi resolution hỗ trợ:

```java
@MockitoBean
PaymentGateway remoteGateway;
```

Đặt tên field rõ ràng và dùng qualifier tường minh khi có nhiều ứng viên là cách dễ đọc trong test dài hạn.

Nếu muốn test `LocalPaymentGateway` hay `RemotePaymentGateway` được chọn bởi `@Fallback`, không mock chính `PaymentGateway` đang kiểm thử. Giữ bean thật và assert concrete type để test không che mất candidate resolution.

## 22. @MockitoSpyBean: theo dõi bean thật

`@MockitoSpyBean` tạo spy từ một bean hiện có. Khác với mock, spy giữ behavior thật theo mặc định, nhưng test có thể stub một số method và verify invocation.

Ví dụ:

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class RemoteGatewaySpyTest {

    @MockitoSpyBean
    RemotePaymentGateway remotePaymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void invokesRemoteGateway() {
        checkoutService.selectedProvider();

        then(remotePaymentGateway)
                .should()
                .providerName();
    }
}
```

Ví dụ minh họa mục đích verify; test thực tế cần đảm bảo method đang được gọi qua bean spy được inject vào consumer.

Một spy cần bean mục tiêu hiện có và phải phân giải được candidate duy nhất phù hợp. Nếu không có bean hoặc có nhiều candidate không phân biệt được, test context có thể thất bại.

Không dùng spy khi muốn thay hoàn toàn external side effect. Một spy vẫn chạy method thật trừ khi bạn stub method tương ứng.

## 23. Mock và spy khác nhau

| Tiêu chí | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Object trong context | Mockito mock | Spy bọc bean thật |
| Behavior mặc định | Mock không thực thi implementation thật | Method gọi thật nếu không stub |
| Mục tiêu | Cô lập dependency | Quan sát hoặc stub một phần bean thật |
| Bean hiện có | Có thể thay thế hoặc tạo theo override mode | Cần bean phù hợp để spy |
| Side effects | Không chạy behavior thật nếu chưa stub/delegate | Có thể chạy side effects thật |
| Rủi ro | Mock nhầm bean làm test không phản ánh wiring | Spy có thể gọi network/database thật |

Dùng mock để cô lập boundary. Dùng spy khi có lý do cần quan sát một bean thật trong context. Đừng spy một client production có thể gửi request thật nếu test không kiểm soát side effect đó.

## 24. @TestBean: thay bean bằng factory method của test

`@TestBean` phù hợp khi muốn thay một bean bằng implementation hoặc object do chính test cung cấp, không cần Mockito.

Ví dụ:

```java
import org.springframework.test.context.bean.override.convention.TestBean;

@SpringBootTest
class CheckoutWithStubGatewayTest {

    @TestBean(methodName = "paymentGatewayOverride")
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGatewayOverride() {
        return new StubPaymentGateway();
    }

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesStubGateway() {
        assertThat(checkoutService.selectedProvider())
                .isEqualTo("stub");
    }
}
```

Factory method cung cấp object dùng để override bean mục tiêu. Method thường được khai báo static trong test class và phải trả về type phù hợp với field.

Tên method có thể được chỉ định tường minh qua thuộc tính `methodName`; nếu bỏ qua, Spring Test dùng quy ước tên theo field. Dùng tên tường minh giúp người đọc hiểu ngay object nào đang thay thế bean nào.

`StubPaymentGateway` là test implementation do bạn tự viết; không phải class có sẵn của Spring.

## 25. Khi nào dùng @TestBean thay cho @MockitoBean?

Chọn `@TestBean` khi:

- Muốn một fake/stub có behavior xác định.
- Muốn test nhiều lần gọi với state nội bộ đơn giản.
- Không cần Mockito verification hoặc stubbing API.
- Muốn code test tự mô tả implementation thay thế.

Chọn `@MockitoBean` khi:

- Muốn stub method theo từng test.
- Muốn verify invocation/arguments.
- Dependency là boundary dễ mock.
- Muốn thay bean bằng mock một cách nhanh chóng.

Chọn `@MockitoSpyBean` khi:

- Cần giữ behavior thật.
- Cần verify method invocation.
- Chỉ muốn stub một phần behavior và đã kiểm soát side effects.

Không cần chọn một annotation duy nhất cho toàn bộ suite. Mỗi test nên dùng công cụ phù hợp với điều nó muốn chứng minh.

## 26. Bean override và test slice

Các bean override annotations có thể dùng trong các Spring Test contexts phù hợp, bao gồm full `@SpringBootTest` và nhiều test slice.

Ví dụ với MVC slice:

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @MockitoBean
    CheckoutService checkoutService;

    @Autowired
    MockMvc mockMvc;
}
```

`@WebMvcTest` chỉ tải một phần context cho web layer. Mock service ở đây là hợp lý vì test đang kiểm tra controller mapping/serialization.

Nhưng nếu mục tiêu là kiểm tra `@Fallback` chọn implementation nào trong toàn application, một MVC slice với `@MockitoBean PaymentGateway` không chứng minh điều đó. Hãy viết một context test riêng giữ các candidate bean thật.

## 27. Spring Framework 6.2 và các annotation Boot cũ

Trước Spring Framework 6.2, nhiều dự án Spring Boot dùng:

- `@MockBean`.
- `@SpyBean`.

Đây là annotation do Spring Boot Test cung cấp. Trong các dòng Spring Boot mới tương thích với Spring Framework 6.2, Spring Test có `@MockitoBean` và `@MockitoSpyBean` làm cơ chế bean override thuộc Framework.

Spring Boot 3.4 đã đánh dấu các annotation cũ `@MockBean` và `@SpyBean` deprecated để hướng tới annotation mới của Spring Test. Khi nâng cấp, hãy kiểm tra version Boot và migration notes tương ứng.

Không tự động thay mọi annotation trong một lần nếu test suite có custom configuration hoặc semantics khác nhau. Đọc warning/deprecation và xác nhận test vẫn thay đúng bean.

## 28. Các lỗi thường gặp khi dùng annotation test mới

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `@MockitoBean` | Spring Test version quá cũ | Kiểm tra Spring Framework dependency |
| `@Fallback` không compile | Spring Context dưới 6.2 | Nâng dòng Boot/BOM tương thích |
| Không nhận `defaultCandidate` | API `@Bean` cũ | Kiểm tra `spring-context` compile version |
| Test mock nhầm bean | Có nhiều candidates cùng type | Dùng `@Qualifier`/bean name rõ |
| Spy không tìm được bean | Bean chưa tồn tại hoặc candidate ambiguous | Kiểm tra context/profile/qualifier |
| `@TestBean` không tìm được factory | Method name/visibility/static/type không phù hợp | Chỉ định `methodName`, kiểm tra signature |
| Test pass dù production bean thiếu | Mock override tạo bean mới thay vì bắt buộc replace | Dùng chế độ enforce override phù hợp |
| Test không kiểm tra `@Fallback` thật | Candidate đã bị mock/override | Giữ bean implementations thật |
| Test slice không thấy bean | Slice không load cấu hình đó | Dùng full context hoặc runner phù hợp |
| `NoSuchMethodError` lúc runtime | Compile/runtime Spring versions lệch | Đồng bộ dependency management |
| Nhiều Spring module khác version | Override BOM/dependency thủ công | Dùng một Spring Boot BOM thống nhất |

## 29. Kiểm tra version Spring Framework thực tế

Đừng dựa vào phiên bản Spring Boot trong `build.gradle` hoặc `pom.xml` một cách máy móc. Hãy xem dependency đã resolve.

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
```

Có thể kiểm tra Spring Core:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-context
```

Hoặc:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
```

Các lệnh này giúp tìm version được chọn sau dependency mediation/BOM management.

Nếu output cho thấy `spring-context` và `spring-core` lệch minor version bất thường, hãy điều tra dependency override hoặc dependency management trước khi chạy ứng dụng.

## 30. Không nâng riêng một module Spring

Spring Framework gồm nhiều module có liên hệ, ví dụ:

- `spring-core`.
- `spring-beans`.
- `spring-context`.
- `spring-aop`.
- `spring-expression`.
- `spring-test`.
- Các module web, transaction, JDBC và ORM.

Một số API mới có thể được khai báo trong `spring-context`, nhưng quá trình runtime còn phụ thuộc các module khác.

Nếu project dùng Spring Boot dependency management, hãy ưu tiên để BOM quản lý các Spring Framework artifacts. Tránh đặt một version riêng cho `spring-context` mà không đồng bộ các module liên quan.

Một dependency graph không đồng nhất có thể dẫn đến:

- `NoSuchMethodError`.
- `NoClassDefFoundError`.
- `ClassNotFoundException`.
- Behavior khác nhau giữa compile test và runtime.
- Test context khởi tạo thất bại trước khi test method chạy.

## 31. Cách kiểm tra classpath trong IDE và CI

Một project có thể compile ở máy phát triển nhưng CI dùng dependency cache hoặc build configuration khác.

Kiểm tra:

1. Gradle/Maven wrapper version.
2. JDK mà build tool thực sự sử dụng.
3. Spring Boot plugin/parent/BOM version.
4. `spring-context` và `spring-test` resolved versions.
5. Dependency exclusions và forced versions.
6. Test runtime classpath, không chỉ main runtime classpath.
7. IDE delegated build có cùng build tool với CI không.

Đối với test annotations, `spring-test` thuộc test classpath. Đối với `@Fallback` và `@Bean(defaultCandidate=...)`, `spring-context` thuộc application compile/runtime classpath.

Nếu annotation tồn tại ở compile time nhưng class/method không có ở runtime, hãy tìm version mismatch thay vì sửa import.

## 32. Viết test kiểm chứng @Fallback

Giả sử configuration:

```java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Test context:

```java
@SpringBootTest(
    classes = GatewayConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class FallbackSelectionTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Autowired
    ApplicationContext context;

    @Test
    void regularCandidateWinsOverFallback() {
        assertThat(paymentGateway)
                .isInstanceOf(RemotePaymentGateway.class);

        assertThat(context.getBeansOfType(PaymentGateway.class))
                .hasSize(2);
    }
}
```

Test chứng minh:

- Cả hai bean tồn tại.
- Consumer inject một `PaymentGateway`.
- Regular candidate được chọn trong khi fallback candidate vẫn có trong context.

Đây là test candidate resolution; nó không chứng minh runtime failover khi remote call thất bại.

## 33. Kiểm thử fallback khi regular bean không có

Có thể tạo một configuration chỉ cung cấp fallback:

```java
@Configuration(proxyBeanMethods = false)
class FallbackOnlyConfiguration {

    @Bean
    @Fallback
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Và test:

```java
@Test
void usesFallbackWhenItIsTheOnlyCandidate() {
    new ApplicationContextRunner()
        .withUserConfiguration(FallbackOnlyConfiguration.class)
        .run(context -> {
            assertThat(context)
                    .hasSingleBean(PaymentGateway.class);

            assertThat(context.getBean(PaymentGateway.class))
                    .isInstanceOf(LocalPaymentGateway.class);
        });
}
```

`ApplicationContextRunner` phù hợp vì chỉ cần dựng một context nhỏ với configuration đang kiểm thử.

Nếu có nhiều fallback beans cùng type và không có candidate khác, không mặc định Spring tự chọn một bean tùy ý. Hãy thêm qualifier/primary hoặc thiết kế candidate set để có một kết quả duy nhất.

## 34. Kiểm thử defaultCandidate=false

Ví dụ configuration:

```java
@Configuration(proxyBeanMethods = false)
class ApiClientConfiguration {

    @Bean
    ApiClient generalClient() {
        return new ApiClient("general");
    }

    @Bean(defaultCandidate = false)
    @Qualifier("audit")
    ApiClient auditClient() {
        return new ApiClient("audit");
    }
}
```

Test consumer mặc định:

```java
class GeneralClientConsumer {

    private final ApiClient client;

    GeneralClientConsumer(ApiClient client) {
        this.client = client;
    }

    String mode() {
        return client.mode();
    }
}
```

Test có thể xác nhận injection không qualifier nhận general client, còn lookup tường minh nhận audit client:

```java
new ApplicationContextRunner()
    .withUserConfiguration(
        ApiClientConfiguration.class,
        GeneralClientConsumerConfiguration.class
    )
    .run(context -> {
        assertThat(context.getBean(GeneralClientConsumer.class).mode())
                .isEqualTo("general");

        assertThat(context.getBean("auditClient", ApiClient.class).mode())
                .isEqualTo("audit");
    });
```

Đây là test cho ý định “bean phụ vẫn có trong context nhưng không tham gia default autowiring”.

Nếu test cần inject audit client theo qualifier, hãy thêm một consumer có `@Qualifier("audit")` và xác nhận riêng.

## 35. Kiểm tra bean được inject khác với kiểm tra bean tồn tại

Ba assertion trả lời các câu hỏi khác nhau:

```java
// Bean có tồn tại không?
assertThat(context.containsBean("localGateway")).isTrue();

// Có bao nhiêu bean cùng contract?
assertThat(context.getBeansOfType(PaymentGateway.class)).hasSize(2);

// Consumer thực sự nhận implementation nào?
assertThat(checkoutService.selectedProvider()).isEqualTo("remote");
```

Một test chỉ kiểm tra `containsBean` có thể pass dù consumer inject sai bean. Một test chỉ kiểm tra consumer behavior có thể bỏ sót một bean dư thừa nếu cả hai implementation trả cùng kết quả.

Với configuration có candidate ranking, nên kiểm tra cả context inventory và injection outcome theo contract cần bảo vệ.

## 36. Context caching và bean override annotations

Spring Test có cơ chế cache application context. Các yếu tố cấu hình test, gồm bean override customizers, có thể ảnh hưởng đến context cache key.

Hệ quả:

- Test có cùng configuration và cùng override declarations có thể tái sử dụng context.
- Test có override khác nhau có thể cần context riêng.
- Một mock được reset theo lifecycle của Spring Test/Mockito integration; không nên dựa vào state của mock giữa các test methods.
- `@DirtiesContext` có thể buộc context bị loại khỏi cache, nhưng không nên dùng như mặc định cho mọi test có mock.

Hãy giữ test độc lập: mỗi test method tự thiết lập stubbing và verification cần thiết, không phụ thuộc thứ tự chạy.

Nếu test suite quá chậm, xem số lượng context khác nhau và cách cấu hình annotations trước khi thêm `@DirtiesContext` hàng loạt.

## 37. Các tiện ích mới không thay thế điều kiện profile/property

`@Fallback` và `defaultCandidate` chỉ giúp candidate resolution. Chúng không thay thế:

- `@Profile`: bean có được đăng ký trong profile hiện tại không?
- `@ConditionalOnProperty`: bean có được đăng ký khi property thỏa không?
- `@ConditionalOnClass`: bean có được đăng ký khi class có trên classpath không?
- `@Qualifier`: injection point cần candidate nào?
- `@Primary`: candidate nào được ưu tiên?

Ví dụ:

```java
@Bean
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment",
    name = "remote-enabled",
    havingValue = "true"
)
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
@Fallback
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}
```

Nếu `prod` active và `payment.remote-enabled=true`, remote bean tồn tại và regular candidate được chọn.

Nếu remote bean không được tạo, local fallback là candidate duy nhất và có thể được chọn. Điều đó chỉ đúng nếu local fallback thực sự được phép trong production; nếu không, hãy thiết kế fail-fast thay vì cung cấp fallback không an toàn.

## 38. Những giới hạn cần nhớ

1. `@Fallback` không tự tạo bean.
2. `@Fallback` không tự chuyển request khi provider chính lỗi.
3. `@Fallback` không loại bean khỏi application context.
4. `@Fallback` không giải quyết ambiguity giữa nhiều regular candidates.
5. `defaultCandidate=false` không disable bean.
6. `@Qualifier` vẫn là lựa chọn rõ ràng cho dependency cần implementation cụ thể.
7. `@Primary` và `@Fallback` không thay thế `@Profile` hoặc `@Conditional...`.
8. `@MockitoBean` có thể che mất bean selection mà test đang định kiểm tra.
9. `@MockitoSpyBean` có thể chạy method thật và tạo side effects.
10. `@TestBean` cần factory method tương thích với bean được override.
11. Các API 6.2 không có trong Spring Framework cũ hơn.
12. Spring Boot BOM nên quản lý các Spring Framework module tương thích.

## 39. Quy trình chọn công cụ

Khi gặp nhiều bean cùng interface:

1. Xác định consumer cần một bean hay collection.
2. Xác định có một implementation chính hay một fallback thực sự.
3. Dùng `@Primary` nếu có một default ưu tiên.
4. Dùng `@Fallback` nếu một implementation chỉ nên được chọn khi không có regular candidate.
5. Dùng `@Qualifier` nếu consumer yêu cầu một implementation cụ thể.
6. Dùng `defaultCandidate=false` cho bean phụ không nên tham gia default autowiring.
7. Dùng profile/property conditions nếu bean chỉ nên tồn tại trong một môi trường/trạng thái cấu hình.
8. Viết context test xác nhận candidate count và bean consumer nhận.
9. Dùng `@MockitoBean`, `@MockitoSpyBean` hoặc `@TestBean` cho test isolation, nhưng không thay bean đang được kiểm tra selection.
10. Xác nhận Spring Framework version thực tế hỗ trợ API được dùng.

## 40. Bài tập thực hành

### Bài tập A — Hai candidate và @Fallback

Tạo `PaymentGateway` với `RemotePaymentGateway` và `LocalPaymentGateway`. Đánh dấu local bằng `@Fallback`. Inject interface vào `CheckoutService`, sau đó xác nhận remote được chọn và cả hai beans vẫn tồn tại.

### Bài tập B — Chỉ còn fallback

Tạo một test context chỉ đăng ký `LocalPaymentGateway` có `@Fallback`. Xác nhận injection đơn trị có thể nhận bean fallback khi nó là candidate duy nhất.

### Bài tập C — Nhiều regular candidates

Đăng ký hai `PaymentGateway` không có primary/fallback/qualifier. Quan sát lỗi ambiguity. Sau đó thử `@Primary` và `@Qualifier`, ghi lại khác biệt.

### Bài tập D — defaultCandidate=false

Tạo hai `ApiClient` beans, đánh dấu bean audit với `@Bean(defaultCandidate=false)`. Xác nhận consumer mặc định nhận general client và consumer có `@Qualifier("audit")` nhận audit client.

### Bài tập E — Fallback kết hợp profile

Tạo remote bean chỉ trong `prod` và chỉ khi property `payment.remote-enabled=true`; tạo local fallback. Kiểm tra từng tổ hợp profile/property. Xác định liệu local fallback có thực sự an toàn khi remote không được cấu hình.

### Bài tập F — Bean parameter name

Tạo hai bean cùng type và một constructor parameter có tên trùng bean name. Bật compiler option `-parameters`. Kiểm tra behavior và sau đó thêm `@Qualifier` để thể hiện dependency tường minh.

### Bài tập G — @MockitoBean

Viết `@SpringBootTest` cho `CheckoutService`, dùng `@MockitoBean` thay `PaymentGateway`. Stub kết quả và kiểm tra service. Sau đó thử enforce override để bảo đảm bean mục tiêu phải tồn tại.

### Bài tập H — @MockitoSpyBean

Dùng spy cho một bean hiện có. Verify một method được gọi khi service xử lý request. Đảm bảo method thật không tạo network/database side effect ngoài ý muốn.

### Bài tập I — @TestBean

Tạo một `StubPaymentGateway` và factory method trong test class. Dùng `@TestBean` thay bean production. So sánh cách đọc test với Mockito mock.

### Bài tập J — Kiểm tra compatibility

Xem dependency tree của project, xác định version `spring-context` và `spring-test`. Kiểm tra version đó có hỗ trợ `@Fallback`, `defaultCandidate`, `@MockitoBean` và `@TestBean` hay không.

## 41. Ghi nhớ

1. `@Fallback` được giới thiệu trong **Spring Framework 6.2** để đánh dấu bean dự phòng trong autowiring candidate resolution.
2. Khi có một regular candidate và một fallback candidate cho injection đơn trị, regular candidate được ưu tiên.
3. Nếu chỉ có một fallback candidate phù hợp, Spring có thể chọn fallback đó.
4. `@Fallback` không tạo bean, không thay thế profile/property conditions và không cung cấp runtime failover.
5. `@Primary` biểu thị lựa chọn ưu tiên; `@Fallback` biểu thị lựa chọn dự phòng.
6. `@Qualifier` dùng khi consumer cần một bean cụ thể.
7. `@Bean(defaultCandidate=false)` đánh dấu bean không phải default candidate, nhưng bean vẫn tồn tại và có thể được chọn tường minh.
8. Parameter-name matching là tiện ích bổ sung; cần metadata tên tham số và không nên thay qualifier cho dependency quan trọng.
9. Spring Framework 6.2 cung cấp `@TestBean`, `@MockitoBean` và `@MockitoSpyBean` cho bean override trong Spring Test.
10. Mock thay behavior; spy giữ behavior thật trừ khi stub; test bean factory cung cấp implementation tùy chỉnh.
11. Không mock bean mà test đang muốn chứng minh `@Fallback` hoặc `@Primary` đã chọn đúng.
12. Spring Boot BOM quản lý version Framework; kiểm tra dependency đã resolve thay vì chỉ nhìn version starter.
13. Không nâng riêng một module Spring Framework mà không đồng bộ các module liên quan.
14. Khi nâng version, xử lý deprecation của `@MockBean`/`@SpyBean` theo migration path của dòng Boot tương ứng.
15. Luôn test cả bean inventory và bean thực sự được inject nếu candidate selection là contract quan trọng.

**Tư duy cốt lõi:** `@Primary` trả lời “bean nào được ưu tiên?”, `@Fallback` trả lời “bean nào chỉ nên dùng khi không có lựa chọn thông thường?”, `@Qualifier` trả lời “consumer cần bean nào cụ thể?”, còn `defaultCandidate=false` trả lời “bean này có nên tham gia lựa chọn mặc định không?”. Các annotation test mới giúp thay bean có kiểm soát trong test context. Dùng đúng từng cơ chế sẽ làm cấu hình Spring rõ ràng và dễ kiểm chứng hơn.
