# Meta-annotation và annotation tổ hợp cho kiểm thử

Một dự án Spring thường có nhiều test class lặp lại cùng một nhóm annotation: `@SpringBootTest`, `@ActiveProfiles`, `@Transactional`, `@AutoConfigureMockMvc`, `@Import` hoặc một test slice. Khi mỗi class tự khai báo nhóm annotation đó, cấu hình dễ bị lệch giữa các test và việc thay đổi quy ước chung đòi hỏi sửa nhiều nơi.

Java cho phép một annotation được gắn lên một annotation khác. Cách kết hợp này gọi là **meta-annotation**. Từ đó, ta có thể định nghĩa annotation tổ hợp (composed annotation) mang nhiều annotation có sẵn, rồi sử dụng một tên ngắn thể hiện ý nghĩa của nhóm test. Spring Test, Spring Boot và JUnit Jupiter đều hỗ trợ nhiều hình thức annotation composition, giúp tái sử dụng cấu hình test mà vẫn giữ được khả năng tùy biến.

## 1. Meta-annotation trong Java là gì?

Annotation trong Java cũng là một kiểu khai báo. Vì vậy, một annotation có thể được gắn các annotation khác để mô tả nơi được phép sử dụng, thời gian lưu giữ hoặc cách công cụ xử lý nó.

Ví dụ, một annotation tự định nghĩa thường có các meta-annotation sau:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface FastTest {
}
```

Các annotation ở đây có ý nghĩa:

- `@Target` xác định annotation được phép đặt ở đâu, chẳng hạn trên class, method, field hoặc annotation declaration.
- `@Retention` xác định annotation được giữ đến giai đoạn nào: source, class file hay runtime.
- `@Documented` yêu cầu annotation xuất hiện trong tài liệu Javadoc của phần tử sử dụng nó.
- `@Inherited` có thể làm annotation cấp class được kế thừa từ superclass theo quy tắc Java.

Để một annotation được JUnit hoặc Spring đọc lúc chạy, thông thường cần `RetentionPolicy.RUNTIME`. Nếu chỉ giữ annotation đến lúc compile, framework không thể dựa vào reflection runtime để phát hiện nó.

### 1.1. Annotation cũng có thể mang annotation khác

Một annotation có thể được đánh dấu bằng annotation có sẵn:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@Tag("fast")
public @interface FastTest {
}
```

`FastTest` là một meta-annotation của JUnit vì nó mang `@Test` và `@Tag`. Khi JUnit phát hiện method có `@FastTest`, method đó được xem là một test và có tag `fast`.

Annotation như vậy thường được gọi là *composed annotation* hoặc *annotation tổ hợp*. Nó không tạo ra một cơ chế thực thi test mới; nó đóng gói những annotation mà framework đã hiểu thành một cấu hình có tên dễ sử dụng.

## 2. Annotation tổ hợp trong JUnit Jupiter

JUnit Jupiter hỗ trợ annotation composition. Những annotation như `@Test`, `@Tag`, `@ExtendWith` có thể được sử dụng trực tiếp hoặc thông qua một annotation do dự án định nghĩa.

Ví dụ, dự án có nhiều test cần cùng gắn tag và cùng extension:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Test
@Tag("integration")
@ExtendWith(DatabaseCleanupExtension.class)
public @interface DatabaseIntegrationTest {
}
```

Test sử dụng annotation này:

```java
class CustomerRepositoryTest {
    @DatabaseIntegrationTest
    void savesCustomerAndCleansDatabase() {
        // JUnit thực thi như một test method.
    }
}
```

JUnit nhận diện `@Test` qua meta-annotation, gắn tag `integration` và đăng ký extension được khai báo. Khi cần chạy riêng nhóm test, có thể lọc theo tag bằng cấu hình build hoặc JUnit Platform.

### 2.1. Kết hợp extension theo một quy ước chung

Nếu nhiều test đều cần một extension để cấp fake clock, cấu hình security context hoặc dọn tài nguyên, có thể đóng gói extension vào annotation:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@ExtendWith(FixedClockExtension.class)
public @interface FixedTimeTest {
}
```

Sau đó test chỉ cần:

```java
class ExpirationPolicyTest {
    @FixedTimeTest
    void expiresAtTheConfiguredInstant() {
        // FixedClockExtension cung cấp clock theo quy ước của dự án.
    }
}
```

Extension vẫn phải tuân theo JUnit Extension API. Annotation tổ hợp chỉ là cách đăng ký extension thống nhất, không tự tạo dependency hoặc trạng thái nếu extension chưa triển khai việc đó.

### 2.2. Không trộn các annotation test method không tương thích

Không nên gom nhiều annotation thực thi test khác nhau vào cùng một composed annotation, ví dụ vừa `@Test` vừa `@ParameterizedTest` hoặc vừa `@TestFactory`. Chúng đại diện cho các mô hình thực thi khác nhau và có thể tạo cách khám phá test khó hiểu.

Hãy tạo annotation riêng cho từng kiểu test method, hoặc tạo annotation chỉ gắn tag/extension để dùng kèm với annotation thực thi phù hợp. Một composed annotation nên có một ý nghĩa rõ ràng.

## 3. Annotation tổ hợp trong Spring Test

Spring Test dùng meta-annotation để cung cấp các annotation tiện ích. Ví dụ, `@SpringJUnitConfig` kết hợp cơ chế extension của Spring với `@ContextConfiguration`, giúp khai báo test context ngắn gọn hơn.

```java
@SpringJUnitConfig(CustomerTestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    private CustomerService customerService;
}
```

Annotation này tương đương với việc khai báo `@ExtendWith(SpringExtension.class)` cùng `@ContextConfiguration(classes = ...)`. Người viết test không cần lặp lại cả hai annotation ở mọi class.

Spring Boot cũng cung cấp nhiều annotation tổ hợp chuyên biệt:

- `@SpringBootTest` kết nối test với cơ chế bootstrap ứng dụng Spring Boot và Spring Test.
- `@WebMvcTest` thiết lập web MVC slice và các cấu hình liên quan.
- `@DataJpaTest` thiết lập persistence slice và transaction test.
- `@JsonTest` thiết lập slice cho JSON serialization/deserialization.
- `@RestClientTest` thiết lập môi trường test cho REST client.

Các annotation slice này đóng gói nhiều cấu hình, filter và bootstrap metadata. Khi tạo annotation riêng, nên bắt đầu từ annotation có sẵn phù hợp nhất thay vì sao chép thủ công mọi meta-annotation bên trong nó.

## 4. Tạo composed annotation cho Spring Boot integration test

Giả sử nhiều test class trong dự án cần cùng một môi trường:

- Khởi động Spring Boot application context.
- Dùng profile `integration`.
- Tự cấu hình `MockMvc`.
- Cho phép từng class chỉ định application configuration và inline properties.

Có thể định nghĩa annotation dùng lại:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface WebIntegrationTest {

    @AliasFor(annotation = SpringBootTest.class, attribute = "classes")
    Class<?>[] classes() default {};

    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Sử dụng:

```java
@WebIntegrationTest(
        classes = ShopApplication.class,
        properties = "feature.checkout.enabled=true")
class CheckoutControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsCheckoutPage() throws Exception {
        mockMvc.perform(get("/checkout"))
                .andExpect(status().isOk());
    }
}
```

Test class chỉ thể hiện những khác biệt riêng của nó. Các quy ước chung về web environment, profile và MockMvc được đặt ở annotation `WebIntegrationTest`.

Trong ví dụ, `classes` và `properties` là thuộc tính của composed annotation. `@AliasFor` ánh xạ chúng tới thuộc tính cùng tên trên `@SpringBootTest`, vì vậy Spring sử dụng giá trị người dùng truyền vào khi hợp nhất metadata.

Nếu mọi test luôn dùng cùng application class và property, không cần mở các thuộc tính đó ra. Một annotation cố định ít khả năng bị sử dụng sai hơn. Chỉ expose thuộc tính mà test class thực sự cần tùy chỉnh.

## 5. `@AliasFor` dùng để làm gì?

Khi tạo composed annotation, ta thường muốn cho người dùng cấu hình một thuộc tính của meta-annotation mà không phải đặt meta-annotation trực tiếp lên test class. Spring cung cấp `@AliasFor` để khai báo mối liên hệ đó.

`@AliasFor` thường được dùng theo hai cách:

1. Tạo alias giữa hai thuộc tính trong cùng một annotation.
2. Override thuộc tính của một meta-annotation.

### 5.1. Alias giữa hai thuộc tính trong cùng annotation

Một annotation có thể cung cấp hai tên khác nhau cho cùng một giá trị:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ContextFilesTest {
    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
```

Hai thuộc tính `value` và `locations` là alias đối ứng. Người dùng có thể viết:

```java
@ContextFilesTest("classpath:/test-context.xml")
class LegacyRepositoryTest {
}
```

Hoặc:

```java
@ContextFilesTest(locations = "classpath:/test-context.xml")
class LegacyRepositoryTest {
}
```

Đây là alias trong cùng annotation. Các thuộc tính phải có kiểu trả về tương thích và cùng giá trị mặc định để Spring có thể hợp nhất chúng nhất quán.

### 5.2. Override thuộc tính của meta-annotation

Giả sử annotation dùng lại cần cho phép test thay đổi web environment của `@SpringBootTest`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
public @interface ApplicationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "webEnvironment")
    SpringBootTest.WebEnvironment webEnvironment()
            default SpringBootTest.WebEnvironment.MOCK;
}
```

Người dùng có thể chọn môi trường:

```java
@ApplicationTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
}
```

Giá trị `RANDOM_PORT` được ánh xạ vào thuộc tính `webEnvironment` của `@SpringBootTest`. Nếu không truyền giá trị, default `MOCK` của composed annotation được sử dụng.

Khi override thuộc tính meta-annotation, kiểu trả về phải tương thích với thuộc tính đích. Giá trị mặc định của alias cần tương thích với giá trị mặc định của thuộc tính được override. Nếu hai thuộc tính không cùng kiểu hoặc default không hợp lệ, Spring có thể báo lỗi khi phân tích merged annotation.

### 5.3. Alias thuộc tính `classes` và `properties`

Ví dụ `WebIntegrationTest` ở phần trước dùng:

```java
@AliasFor(annotation = SpringBootTest.class, attribute = "classes")
Class<?>[] classes() default {};

@AliasFor(annotation = SpringBootTest.class, attribute = "properties")
String[] properties() default {};
```

Điều này có nghĩa người dùng có thể cấu hình composed annotation mà không phải viết thêm `@SpringBootTest` trực tiếp. Spring hợp nhất các thuộc tính của annotation tổ hợp và meta-annotation để tạo cấu hình cuối cùng.

Nếu thuộc tính của meta-annotation không được expose, giá trị khai báo ngay trong meta-annotation sẽ được giữ. Ví dụ `@ActiveProfiles("integration")` cố định profile cho tất cả test dùng `@WebIntegrationTest`; test class không thể đổi profile qua annotation này nếu composed annotation không định nghĩa alias tương ứng.

## 6. Alias trong nhiều tầng meta-annotation

Annotation tổ hợp có thể được xây dựng từ annotation tổ hợp khác. Ví dụ, một annotation dùng chung cho integration test có thể được sử dụng bởi annotation chuyên biệt cho MVC hoặc persistence.

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
public @interface IntegrationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Annotation chuyên biệt cho web:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@IntegrationTest
@AutoConfigureMockMvc
public @interface WebLayerIntegrationTest {
}
```

Test dùng:

```java
@WebLayerIntegrationTest
class AccountControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;
}
```

Spring hỗ trợ tìm metadata qua các tầng meta-annotation. Tuy nhiên, càng nhiều tầng thì càng khó biết giá trị cuối cùng đến từ đâu. Hãy giới hạn độ sâu composition và đặt tên thể hiện rõ vai trò của từng annotation.

Khi cần expose một thuộc tính qua nhiều tầng, phải khai báo alias tương ứng ở các tầng cần thiết và bảo đảm các đường alias không mâu thuẫn. Nếu test thường xuyên cần override profile, property hoặc context classes, có thể một annotation duy nhất với các thuộc tính tường minh dễ hiểu hơn nhiều tầng annotation.

## 7. Kết hợp annotation của Spring Test và Spring Boot

Một composed annotation có thể kết hợp nhiều annotation cấp class, miễn là chúng tương thích về mục tiêu bootstrap và cấu hình.

Ví dụ, annotation cho repository integration test:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
@ActiveProfiles("repository-test")
public @interface RepositoryIntegrationTest {
}
```

Sử dụng:

```java
@RepositoryIntegrationTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;
}
```

Annotation này thống nhất persistence slice và profile dành cho repository test. `@DataJpaTest` đã cung cấp bootstrap và transaction semantics phù hợp; không cần gắn thêm `@SpringBootTest` vào cùng composed annotation.

### 7.1. Tránh kết hợp các bootstrap annotation xung đột

Một test class không nên vô tình nhận nhiều bootstrap strategy không tương thích. Ví dụ, `@SpringBootTest` và `@WebMvcTest` đều mô tả cách tạo test context theo những mục tiêu khác nhau. Kết hợp cả hai trong một composed annotation có thể dẫn đến xung đột `@BootstrapWith` hoặc cấu hình context khó dự đoán.

Hãy chọn một bootstrap annotation làm nền:

- Full application context: `@SpringBootTest`.
- MVC slice: `@WebMvcTest`.
- JPA slice: `@DataJpaTest`.
- Spring context thuần: `@ContextConfiguration` hoặc `@SpringJUnitConfig`.

Sau đó thêm các annotation bổ trợ tương thích như `@ActiveProfiles`, `@TestPropertySource`, `@Import`, `@AutoConfigureMockMvc`, `@Transactional` hoặc `@DirtiesContext` khi thực sự cần.

## 8. Phạm vi áp dụng của composed annotation

`@Target` của annotation tổ hợp phải bao gồm nơi người dùng sẽ đặt nó. Ví dụ, annotation dùng ở cấp class:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceIntegrationTest {
}
```

Annotation dùng ở cấp method:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
public @interface ServiceTest {
}
```

Nếu annotation có thể dùng ở cả class và method, khai báo rõ cả hai:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface TestCategory {
    String value();
}
```

Khi tạo meta-annotation, annotation cần được phép xuất hiện trên một annotation declaration. Điều đó có nghĩa `@Target` của annotation gốc phải hỗ trợ `ElementType.ANNOTATION_TYPE` nếu annotation đó được dùng làm meta-annotation. Những annotation của JUnit và Spring được thiết kế để composition thường đã cho phép vị trí này.

Đừng khai báo `@Target` rộng hơn nhu cầu chỉ để tránh lỗi compile. Một annotation chỉ có ý nghĩa ở cấp test class nên giữ `TYPE`, giúp IDE và compiler ngăn việc sử dụng nhầm trên method hoặc field.

## 9. `@Inherited` và việc kế thừa annotation

`@Inherited` là meta-annotation của Java, cho phép một annotation cấp class được kế thừa từ superclass khi đọc annotation qua cơ chế Java reflection. Nó không làm annotation được kế thừa từ interface và không áp dụng cho annotation trên method hoặc field.

Ví dụ:

```java
@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles("integration")
public @interface IntegrationProfile {
}
```

Lớp con có thể nhận annotation từ superclass:

```java
@IntegrationProfile
abstract class BaseIntegrationTest {
}

class CustomerServiceTest extends BaseIntegrationTest {
}
```

Tuy nhiên, Spring Test có cơ chế merged annotation và quy tắc kế thừa riêng cho một số annotation cấu hình. Ví dụ, `@ContextConfiguration`, `@ActiveProfiles` và `@TestPropertySource` có thuộc tính điều khiển việc kế thừa. Không nên dựa riêng vào `@Inherited` để suy luận toàn bộ cách Spring hợp nhất metadata.

### 9.1. Kế thừa qua superclass khác với meta-annotation

Hai khái niệm này độc lập:

- Meta-annotation: annotation A được đặt trên định nghĩa annotation B; framework tìm A khi test sử dụng B.
- Annotation inheritance: class con nhận annotation từ superclass theo quy tắc của Java hoặc Spring Test.

Một annotation tổ hợp có thể không dùng `@Inherited` nhưng Spring Test vẫn có thể tìm thấy cấu hình qua các quy tắc merged annotation của nó. Ngược lại, `@Inherited` không biến một annotation bất kỳ thành meta-annotation của annotation khác.

### 9.2. Cẩn thận với method override

Java `@Inherited` không làm annotation trên method của superclass tự động xuất hiện trên method override của subclass. Nếu test method được override, hãy kiểm tra quy tắc của framework đang sử dụng thay vì suy luận từ kế thừa class-level.

## 10. Annotation tổ hợp và Spring TestContext Framework

Spring TestContext Framework dùng cơ chế merged annotations để tìm và hợp nhất cấu hình từ test class, superclass, enclosing class và meta-annotation. Vì vậy, composed annotation có thể cung cấp thông tin cho quá trình bootstrap context như:

- `@ContextConfiguration` hoặc `@SpringBootTest`.
- `@ActiveProfiles`.
- `@TestPropertySource`.
- `@ContextHierarchy`.
- `@Transactional`.
- `@DirtiesContext`.
- Các annotation bean override của Spring Test.

Spring không chỉ kiểm tra annotation được đặt trực tiếp trên class. Nó có thể đi qua meta-annotation để tìm cấu hình. `@AliasFor` giúp các thuộc tính của composed annotation được hợp nhất đúng với thuộc tính meta-annotation tương ứng.

### 10.1. Giá trị cuối cùng đến từ đâu?

Khi một test class có nhiều nguồn cấu hình, giá trị cuối cùng phụ thuộc vào:

- Giá trị khai báo trực tiếp trên annotation tổ hợp.
- Giá trị cố định trong meta-annotation.
- Thuộc tính được expose qua `@AliasFor`.
- Quy tắc override và kế thừa của annotation Spring tương ứng.

Không nên đặt cùng một thuộc tính ở nhiều tầng mà không có quy ước. Ví dụ, nếu composed annotation cố định profile `integration` nhưng superclass cũng khai báo `@ActiveProfiles("repository")`, kết quả hợp nhất có thể không như người đọc mong đợi. Hãy thống nhất một nơi sở hữu profile hoặc khai báo rõ quy tắc kế thừa.

### 10.2. Ảnh hưởng đến context cache

Spring TestContext Framework cache `ApplicationContext` dựa trên cấu hình đã hợp nhất. Các giá trị đến từ composed annotation có thể ảnh hưởng đến cache key, chẳng hạn classes, properties, profiles, context customizers hoặc bean overrides.

Nếu nhiều test dùng cùng một composed annotation với cùng giá trị, chúng có cơ hội tái sử dụng context. Nếu mỗi class truyền properties hoặc classes khác nhau qua `@AliasFor`, context key có thể khác và Spring phải tạo context riêng.

Đây là hành vi đúng: hai test cần cấu hình khác nhau không nên dùng chung một context nếu cấu hình đó làm thay đổi bean graph hoặc hành vi ứng dụng. Tuy nhiên, nếu khác biệt chỉ là dữ liệu của test method, hãy cân nhắc đưa dữ liệu vào fixture thay vì tạo một annotation attribute khác nhau cho từng class.

## 11. Ví dụ annotation tổ hợp cho các nhóm test phổ biến

### 11.1. Web integration test

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface WebIntegrationTest {
    @AliasFor(annotation = SpringBootTest.class, attribute = "properties")
    String[] properties() default {};
}
```

Test:

```java
@WebIntegrationTest(properties = "feature.catalog.enabled=true")
class CatalogControllerIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
```

### 11.2. Repository slice test

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
@ActiveProfiles("repository-test")
public @interface JpaSliceTest {
}
```

Test:

```java
@JpaSliceTest
class ProductRepositoryTest {
    @Autowired
    ProductRepository products;
}
```

### 11.3. Unit test có tag và extension

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Test
@Tag("fast")
@ExtendWith(FixedClockExtension.class)
public @interface FastFixedTimeTest {
}
```

Test:

```java
class SubscriptionPolicyTest {
    @FastFixedTimeTest
    void evaluatesSubscriptionAtTheFixedInstant() {
        // Test dùng clock do extension cung cấp.
    }
}
```

Ba annotation tổ hợp trên phục vụ ba mục đích khác nhau. Không nên tạo một annotation duy nhất vừa đại diện cho unit test, web slice và JPA slice vì phạm vi bootstrap và chi phí của chúng khác nhau.

## 12. Các lỗi thường gặp khi tạo composed annotation

### Thiếu runtime retention

Nếu annotation dùng `RetentionPolicy.CLASS` hoặc `SOURCE`, framework có thể không đọc được nó lúc chạy. Với annotation dành cho JUnit và Spring Test, dùng `RetentionPolicy.RUNTIME`.

### `@Target` không cho phép vị trí sử dụng

Annotation có thể compile lỗi khi đặt trên annotation declaration nếu `@Target` của nó không bao gồm `ANNOTATION_TYPE`. Hãy kiểm tra cả nơi annotation tổ hợp được khai báo và nơi người dùng áp dụng nó.

### `@AliasFor` sai kiểu hoặc sai default

Thuộc tính alias phải tương thích với thuộc tính đích. Alias trong cùng annotation cần khai báo đối ứng; default value phải phù hợp. Khi Spring báo lỗi merged annotation, kiểm tra tên attribute, kiểu và giá trị mặc định trước.

### Đặt nhiều bootstrap annotation xung đột

Kết hợp `@SpringBootTest` với `@WebMvcTest` hoặc `@DataJpaTest` trong cùng annotation tổ hợp có thể tạo nhiều bootstrap strategy không tương thích. Chọn một annotation nền duy nhất rồi thêm annotation bổ trợ.

### Annotation tổ hợp chứa quá nhiều cấu hình

Một annotation gom profile, property, transaction, mock, web environment và cleanup cho mọi loại test sẽ khó hiểu. Tách thành các annotation theo mục tiêu: web integration, repository slice, service integration hoặc unit test.

### Không rõ thuộc tính nào được expose

Nếu test cần thay đổi một thuộc tính nhưng composed annotation không có alias, người dùng có thể thêm annotation gốc bên cạnh và tạo cấu hình chồng chéo. Hãy expose đúng những thuộc tính cần tùy biến hoặc giữ annotation cố định nếu không có nhu cầu thay đổi.

### Dùng `@Inherited` với kỳ vọng sai

`@Inherited` chỉ áp dụng cho annotation cấp class qua superclass theo quy tắc Java. Nó không áp dụng cho interface, method override hoặc mọi quy tắc merged annotation của Spring.

### Đặt annotation ở sai cấp

Một annotation kết hợp `@SpringBootTest` thường dùng ở cấp class; một annotation kết hợp `@Test` dùng ở cấp method. Đặt đúng `@Target` để compiler giúp ngăn việc sử dụng sai.

## 13. Quy trình thiết kế annotation tổ hợp

Khi muốn chuẩn hóa một nhóm test annotation, hãy thực hiện theo trình tự:

1. Xác định loại test: unit test, Spring context test, full Boot integration test hay slice test.
2. Chọn một annotation nền phù hợp như `@Test`, `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc `@ContextConfiguration`.
3. Thêm các annotation bổ trợ thực sự dùng chung, chẳng hạn `@Tag`, `@ExtendWith`, `@ActiveProfiles`, `@Transactional` hoặc `@AutoConfigureMockMvc`.
4. Khai báo `@Target`, `@Retention(RUNTIME)` và `@Documented` cho annotation mới.
5. Dùng `@AliasFor` để expose những thuộc tính meta-annotation mà test class cần tùy chỉnh.
6. Giữ default value tương thích và tránh nhiều nguồn ghi đè cùng một thuộc tính.
7. Áp dụng annotation vào một test đại diện và xác nhận framework nạp đúng context, profile, extension hoặc tag.
8. Dùng cùng annotation ở nhóm test có cùng cấu hình để tăng tính nhất quán và khả năng tái sử dụng context.

Annotation tổ hợp nên phản ánh một quy ước có ý nghĩa trong dự án. Nếu hai nhóm test có lifecycle hoặc bootstrap khác nhau, hãy tạo hai annotation thay vì thêm nhiều cờ boolean để một annotation cố gắng phục vụ mọi trường hợp.

## 14. Nguyên tắc cần nhớ

- Meta-annotation là annotation được đặt trên định nghĩa annotation khác; composed annotation đóng gói nhiều cấu hình để dùng lại.
- Dùng `RetentionPolicy.RUNTIME` để JUnit và Spring có thể đọc annotation trong lúc chạy.
- `@Target` phải cho phép vị trí mà annotation được sử dụng, bao gồm `ANNOTATION_TYPE` khi annotation đó sẽ làm meta-annotation.
- JUnit Jupiter cho phép kết hợp `@Test`, `@Tag` và `@ExtendWith` trong annotation dùng lại.
- Spring cung cấp các annotation tổ hợp như `@SpringJUnitConfig`, `@SpringBootTest`, `@WebMvcTest` và `@DataJpaTest` cho những phạm vi kiểm thử khác nhau.
- `@AliasFor` tạo alias trong cùng annotation hoặc ánh xạ thuộc tính của composed annotation tới meta-annotation.
- Chọn một bootstrap annotation nền; tránh kết hợp các annotation context có chiến lược khởi tạo xung đột.
- `@Inherited` điều khiển kế thừa class-level qua superclass và không thay thế cơ chế merged annotation của Spring.
- Giá trị từ composed annotation có thể ảnh hưởng đến cấu hình và context cache key.
- Giữ annotation ngắn, có mục đích rõ ràng và chỉ expose những thuộc tính thật sự cần tùy chỉnh.

Meta-annotation và annotation tổ hợp giúp dự án đóng gói quy ước kiểm thử thành những tên có ý nghĩa. Khi chọn đúng annotation nền, khai báo alias chính xác và giữ phạm vi áp dụng rõ ràng, các test class sẽ nhất quán hơn, ít lặp cấu hình hơn và vẫn có thể tùy chỉnh những thuộc tính cần thiết cho từng kịch bản.
