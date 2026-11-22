# Kế thừa profile và ActiveProfilesResolver

Spring Profiles cho phép một ứng dụng chọn các bean và cấu hình phù hợp với từng môi trường hoặc mục đích chạy. Trong kiểm thử, profile quyết định những thành phần nào được nạp vào `ApplicationContext`, ví dụ cấu hình dùng database kiểm thử, dịch vụ giả lập hoặc các bean dành riêng cho integration test.

Spring TestContext Framework cung cấp annotation `@ActiveProfiles` để khai báo profile cho một test class. Khi các test class có quan hệ kế thừa, Spring có thể kết hợp profile từ lớp cha và lớp con. Nếu cách kết hợp mặc định không phù hợp, thuộc tính `inheritProfiles` cho phép thay thế profile kế thừa. Với những trường hợp cần chọn profile dựa trên môi trường hoặc quy tắc riêng, `ActiveProfilesResolver` cho phép xác định danh sách profile bằng code.

## 1. Profile trong Spring có vai trò gì?

Một profile là tên đại diện cho một nhóm bean hoặc cấu hình. Thành phần được đánh dấu bằng `@Profile` chỉ được đăng ký khi profile tương ứng đang active.

Ví dụ:

```java
@Configuration
@Profile("test")
class TestDataConfiguration {

    @Bean
    DataSource dataSource() {
        return createTestDataSource();
    }
}
```

Cấu hình trên chỉ được sử dụng khi profile `test` active. Một cấu hình khác có thể cung cấp DataSource cho môi trường phát triển:

```java
@Configuration
@Profile("dev")
class DevelopmentDataConfiguration {

    @Bean
    DataSource dataSource() {
        return createDevelopmentDataSource();
    }
}
```

Các phương thức `createTestDataSource()` và `createDevelopmentDataSource()` ở ví dụ là phần khởi tạo được lược bỏ để tập trung vào điều kiện profile.

Cần phân biệt hai annotation:

- `@Profile` đặt trên cấu hình hoặc bean để quyết định thành phần đó có được đăng ký hay không.
- `@ActiveProfiles` đặt trên test class để khai báo profile Spring cần kích hoạt khi tạo test context.

Ví dụ, test class có thể kích hoạt `test`, còn cấu hình `@Profile("test")` cung cấp những bean phù hợp cho test đó.

## 2. Khai báo profile bằng @ActiveProfiles

Có thể dùng `@ActiveProfiles` trên test class:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        Order order = orderService.createOrder(
                new CreateOrderCommand("CUSTOMER-42")
        );

        assertNotNull(order.getId());
    }
}
```

Trong ví dụ:

1. `@SpringBootTest` yêu cầu Spring Boot tạo application context phục vụ integration test.
2. `@ActiveProfiles("test")` khai báo profile `test` cho test context.
3. Spring nạp các bean và cấu hình tương ứng với profile đang active.
4. Test sử dụng bean được inject từ context.

Với ứng dụng Spring Boot, profile `test` thường được dùng để chọn cấu hình trong `application-test.properties` hoặc `application-test.yml`. Các cấu hình đó có thể chỉ định database kiểm thử, endpoint nội bộ hoặc những thuộc tính thích hợp cho test.

Ví dụ:

```yaml
# application-test.yml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test
    username: sa
    password:
```

Đây là ví dụ minh họa; dependency và cấu hình database cụ thể phụ thuộc dự án. Không nên đưa mật khẩu hoặc thông tin kết nối production vào file cấu hình kiểm thử.

Nếu test cần nhiều profile, có thể khai báo một danh sách:

```java
@ActiveProfiles({"test", "stub-payment"})
class CheckoutIntegrationTest {
    // ...
}
```

Cả `test` và `stub-payment` đều được kích hoạt. Một bean có thể được giới hạn bằng một profile hoặc biểu thức profile tùy theo nhu cầu cấu hình.

## 3. Profile được kế thừa giữa test class như thế nào?

Khi test class kế thừa một lớp kiểm thử khác, Spring TestContext Framework mặc định cho phép kế thừa các profile được khai báo ở lớp cha. Nếu lớp con cũng khai báo `@ActiveProfiles`, profile của lớp cha và lớp con được kết hợp.

Ví dụ:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
    // Cấu hình và hành vi chung cho integration test
}

@ActiveProfiles("database")
class CustomerRepositoryTest extends BaseIntegrationTest {
    // Kiểm tra repository
}
```

Với mặc định `inheritProfiles = true`, test class `CustomerRepositoryTest` có cả hai profile:

```text
BaseIntegrationTest
    @ActiveProfiles("integration")
              |
              v
CustomerRepositoryTest
    @ActiveProfiles("database")
              |
              v
Active profiles của test context:
    integration
    database
```

Cách kết hợp này hữu ích khi lớp cha định nghĩa profile chung cho một nhóm test, còn lớp con bổ sung profile chuyên biệt. Ví dụ, mọi integration test đều dùng profile `integration`, trong khi test repository bổ sung `database` và test thanh toán bổ sung `payment-stub`.

Nếu lớp con không khai báo `@ActiveProfiles`, profile được tìm thấy từ lớp cha vẫn có thể được sử dụng. Cơ chế kế thừa giúp tránh lặp lại cùng một khai báo trên nhiều test class.

### Kế thừa nhiều cấp

Profile có thể được kết hợp qua nhiều lớp trong chuỗi kế thừa:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("database")
abstract class BaseRepositoryTest extends BaseIntegrationTest {
}

@ActiveProfiles("postgres-test")
class CustomerRepositoryTest extends BaseRepositoryTest {
}
```

Với chính sách kế thừa mặc định, context của `CustomerRepositoryTest` nhận các profile được khai báo trên chuỗi lớp:

```text
BaseIntegrationTest       -> integration
BaseRepositoryTest        -> database
CustomerRepositoryTest    -> postgres-test
                           ----------------
Active profiles           -> integration, database, postgres-test
```

Cách tổ chức này phù hợp khi mỗi cấp lớp đại diện cho một phạm vi cấu hình rõ ràng. Tuy nhiên, không nên tạo nhiều tầng kế thừa chỉ để cộng dồn profile. Nếu profile của từng test class dễ hiểu hơn khi khai báo trực tiếp, cấu trúc đơn giản thường dễ bảo trì hơn.

## 4. Tắt kế thừa bằng inheritProfiles = false

Có những trường hợp lớp con cần một bộ profile độc lập. Ví dụ, lớp cha dùng cấu hình database tích hợp, nhưng lớp con kiểm tra một cấu hình hoàn toàn khác và không được kích hoạt profile của lớp cha.

Khi đó, đặt `inheritProfiles = false`:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
    // Chỉ sử dụng profile isolated
}
```

Profile của `IsolatedConfigurationTest` chỉ gồm `isolated`. Profile `integration` của lớp cha không được gộp vào context của lớp con.

Có thể biểu diễn:

```text
BaseIntegrationTest
    @ActiveProfiles("integration")
              |
              v
IsolatedConfigurationTest
    @ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
    )
              |
              v
Active profiles:
    isolated
```

`inheritProfiles = false` có ý nghĩa tại khai báo `@ActiveProfiles` của lớp con. Nó điều khiển việc gộp profile từ lớp cha vào danh sách của lớp hiện tại.

Hãy dùng thuộc tính này khi thực sự cần tách biệt cấu hình. Nếu tắt kế thừa tùy tiện, lớp con có thể mất profile chung mà các bean hoặc cấu hình của test vẫn đang cần.

## 5. @ActiveProfiles có thể kết hợp với profile từ nhiều nguồn không?

Khi xây dựng test context, Spring cần một danh sách profile cụ thể trước khi nạp các bean phụ thuộc vào profile. Danh sách này có thể đến từ `@ActiveProfiles` hoặc từ một resolver được chỉ định trên annotation.

Trong test thông thường, nên khai báo rõ profile cần thiết để kết quả không phụ thuộc vào cấu hình môi trường của máy đang chạy test. Ví dụ:

```java
@ActiveProfiles("test")
@SpringBootTest
class CustomerServiceTest {
    // ...
}
```

Cách này làm ý định của test hiển thị ngay trong mã nguồn. Khi một test cần profile khác, có thể khai báo riêng hoặc sử dụng resolver.

Không nên nhầm `@ActiveProfiles` với việc đặt `spring.profiles.active` trong một file cấu hình hoặc biến môi trường cho toàn bộ tiến trình. `@ActiveProfiles` là metadata của Spring TestContext dành cho test class và được sử dụng khi Spring xác định profile cho test context. Nếu test class khai báo annotation này, Spring sử dụng profile được xác định từ annotation hoặc resolver tương ứng để tạo context. Khi cần điều khiển profile bằng một quy tắc bên ngoài, hãy thể hiện quy tắc đó bằng `ActiveProfilesResolver` thay vì giả định rằng một biến môi trường sẽ tự ghi đè annotation.

## 6. ActiveProfilesResolver là gì?

`ActiveProfilesResolver` là một interface của Spring TestContext Framework. Nó cho phép test tự xác định danh sách profile cần active bằng code.

Interface có phương thức:

```java
public interface ActiveProfilesResolver {

    String[] resolve(Class<?> testClass);
}
```

Spring truyền test class hiện tại vào `resolve`. Resolver trả về một mảng tên profile. Spring sử dụng danh sách đó khi tạo test context.

Resolver phù hợp khi profile phụ thuộc vào:

- System property được truyền từ lệnh chạy test.
- Environment variable do CI cung cấp.
- Quy ước theo package hoặc loại test class.
- Annotation tùy chỉnh trên test class.
- Một quy tắc chọn cấu hình riêng của dự án.

Resolver nên chỉ thực hiện việc xác định profile. Nó không nên khởi tạo application context hoặc phụ thuộc vào bean trong context, vì profile phải được xác định trước khi context được tạo.

## 7. Viết resolver đơn giản

Ví dụ, dự án muốn cho phép truyền profile bằng system property `test.profile`. Nếu không truyền, test sử dụng profile `test`.

Tạo resolver:

```java
import org.springframework.test.context.ActiveProfilesResolver;

public class TestProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getProperty("test.profile");

        if (profile == null || profile.isBlank()) {
            return new String[] {"test"};
        }

        return new String[] {profile.trim()};
    }
}
```

Đăng ký resolver trên test class:

```java
@SpringBootTest
@ActiveProfiles(resolver = TestProfileResolver.class)
class CustomerServiceTest {
    // ...
}
```

Khi chạy test mà không truyền system property, resolver trả về `test`. Khi truyền `-Dtest.profile=integration`, resolver trả về `integration`.

Ví dụ chạy bằng Gradle:

```bash
./gradlew test -Dtest.profile=integration
```

Tùy cách cấu hình Gradle và test task của dự án, system property cần được chuyển tiếp đến JVM chạy test. Có thể cấu hình task `Test` để truyền property một cách tường minh nếu JVM của Gradle và JVM test là hai tiến trình riêng.

Ví dụ cấu hình Groovy:

```groovy
tasks.withType(Test).configureEach {
    systemProperty "test.profile",
            System.getProperty("test.profile", "test")
}
```

Đây là cấu hình minh họa. Dự án cần đặt nó ở đúng build script và phạm vi task theo cấu trúc build hiện có.

## 8. Resolver có thể dựa trên environment variable

Nếu CI hoặc môi trường chạy test quản lý cấu hình bằng environment variable, resolver có thể đọc biến đó:

```java
import org.springframework.test.context.ActiveProfilesResolver;

public class EnvironmentProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getenv("TEST_PROFILE");

        if (profile == null || profile.isBlank()) {
            return new String[] {"test"};
        }

        return new String[] {profile.trim()};
    }
}
```

Đăng ký:

```java
@ActiveProfiles(resolver = EnvironmentProfilesResolver.class)
class CustomerRepositoryTest {
    // ...
}
```

Khi biến `TEST_PROFILE` không tồn tại hoặc rỗng, resolver chọn `test`. Khi biến được thiết lập, resolver trả về tên profile tương ứng.

Nếu cần hỗ trợ cả system property và environment variable, nên xác định rõ thứ tự ưu tiên:

```java
public class EnvironmentProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String profile = System.getProperty("test.profile");

        if (profile == null || profile.isBlank()) {
            profile = System.getenv("TEST_PROFILE");
        }

        if (profile == null || profile.isBlank()) {
            profile = "test";
        }

        return new String[] {profile.trim()};
    }
}
```

Trong ví dụ này, system property được ưu tiên, sau đó đến environment variable, cuối cùng là giá trị mặc định. Quy tắc rõ ràng giúp CI và lập trình viên hiểu cùng một test sẽ chọn profile nào.

Không nên để resolver chọn profile một cách ngẫu nhiên hoặc phụ thuộc vào trạng thái máy không được kiểm soát. Nếu profile thay đổi không rõ lý do, test có thể nạp một context khác nhau giữa máy lập trình viên và CI, khiến lỗi khó tái hiện.

## 9. Resolver nhận testClass để làm gì?

Tham số `testClass` cho phép resolver biết class đang yêu cầu profile. Dựa trên class, resolver có thể áp dụng quy ước theo package, tên class hoặc annotation.

Ví dụ, một dự án có thể phân loại integration test theo package:

```java
public class PackageProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String packageName = testClass.getPackageName();

        if (packageName.contains(".repository.")) {
            return new String[] {"test", "database"};
        }

        if (packageName.contains(".web.")) {
            return new String[] {"test", "web"};
        }

        return new String[] {"test"};
    }
}
```

Resolver được đăng ký như sau:

```java
@ActiveProfiles(resolver = PackageProfilesResolver.class)
@SpringBootTest
class CustomerRepositoryIntegrationTest {
    // ...
}
```

Test class thuộc package có tên chứa `.repository.` sẽ nhận thêm profile `database`. Test thuộc package `.web.` sẽ nhận thêm profile `web`.

Đây là ví dụ về quy ước tổ chức dự án. Nếu tên package không phải hợp đồng ổn định, việc đổi package có thể vô tình thay đổi profile. Khi đó, khai báo tường minh hoặc annotation tùy chỉnh có thể an toàn và dễ đọc hơn.

Resolver cũng có thể kiểm tra annotation tùy chỉnh:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DatabaseTest {
}
```

```java
public class AnnotationProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        if (testClass.isAnnotationPresent(DatabaseTest.class)) {
            return new String[] {"test", "database"};
        }

        return new String[] {"test"};
    }
}
```

Cách này phù hợp khi dự án có một số loại test được phân loại theo metadata. Tuy nhiên, nếu chỉ có một vài test class, khai báo `@ActiveProfiles` trực tiếp thường đơn giản hơn việc tạo thêm annotation và resolver.

## 10. Resolver và kế thừa profile

Resolver tham gia vào quá trình xác định profile cho test class có khai báo `@ActiveProfiles(resolver = ...)`. Sau khi resolver trả về danh sách cho class đó, Spring TestContext Framework xử lý chính sách kế thừa theo `inheritProfiles`.

Ví dụ:

```java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@ActiveProfiles(
        resolver = TestProfileResolver.class,
        inheritProfiles = true
)
class CustomerRepositoryTest extends BaseIntegrationTest {
}
```

Trong trường hợp này:

- Resolver xác định profile cho `CustomerRepositoryTest`.
- Do `inheritProfiles = true`, profile từ lớp cha được kết hợp theo chính sách kế thừa.
- Context của lớp con nhận profile do resolver trả về cùng profile được kế thừa từ lớp cha.

Nếu lớp con không cần profile từ lớp cha:

```java
@ActiveProfiles(
        resolver = TestProfileResolver.class,
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
}
```

Khi đó danh sách profile của lớp con được xác định bởi resolver, không gộp profile kế thừa từ `BaseIntegrationTest`.

Khi chỉ định resolver, danh sách profile do resolver trả về là nguồn xác định profile cho khai báo đó; không nên kỳ vọng các giá trị ghi trong `profiles` đồng thời được tự động cộng thêm vào kết quả resolver. Hãy để toàn bộ quy tắc cần thiết nằm trong resolver hoặc trong chính sách kế thừa đã chọn, nhằm tránh việc người đọc hiểu nhầm nguồn profile thực tế.

## 11. Resolver nên có tính xác định và dễ kiểm soát

Resolver được gọi trong quá trình Spring xác định profile trước khi xây dựng context. Vì vậy, code trong resolver nên nhỏ, rõ ràng và có kết quả ổn định.

Một resolver tốt thường có các đặc điểm:

- Trả về mảng profile không null.
- Chỉ trả về tên profile hợp lệ mà dự án đã định nghĩa.
- Có giá trị mặc định rõ ràng khi cấu hình ngoài không tồn tại.
- Có thứ tự ưu tiên cụ thể nếu đọc nhiều nguồn cấu hình.
- Không truy cập database, HTTP service hoặc bean trong ApplicationContext.
- Không phụ thuộc vào thời gian hoặc dữ liệu ngẫu nhiên.
- Có thể giải thích vì sao một test class nhận một danh sách profile nhất định.

Không nên tạo resolver phức tạp đến mức người đọc phải debug nhiều tầng mới biết context sẽ được khởi tạo với profile nào. Nếu profile chỉ là `test` cho toàn bộ test class, `@ActiveProfiles("test")` trực tiếp dễ hiểu hơn.

### Kiểm tra resolver bằng unit test

Resolver là một lớp Java thông thường nên có thể kiểm tra độc lập bằng JUnit:

```java
class TestProfileResolverTest {

    private final TestProfileResolver resolver =
            new TestProfileResolver();

    @Test
    void usesTestProfileWhenPropertyIsMissing() {
        // Cần kiểm soát property trong môi trường test
        String[] profiles = resolver.resolve(CustomerServiceTest.class);

        assertArrayEquals(new String[] {"test"}, profiles);
    }
}
```

Ví dụ trên chỉ minh họa mục tiêu kiểm tra. Vì system property là trạng thái toàn cục của JVM, test thực tế cần lưu và khôi phục giá trị cũ trong `try/finally` hoặc dùng một thư viện quản lý system properties. Không để test thay đổi property rồi làm ảnh hưởng đến test khác.

Nếu resolver đọc environment variable, việc kiểm soát trong unit test thường khó hơn vì environment variable không thể thay đổi trực tiếp một cách portable trong JVM. Có thể tách việc đọc cấu hình thành một thành phần nhỏ có thể truyền giá trị vào, rồi kiểm tra resolver bằng dữ liệu giả lập hoặc kiểm tra quy tắc chọn profile qua một hàm thuần.

## 12. Profile và Spring TestContext cache

Danh sách active profiles là một phần của cấu hình được Spring TestContext Framework sử dụng khi xây dựng và cache `ApplicationContext`. Hai test class có cấu hình context giống nhau có thể dùng chung context đã cache. Nếu profile khác nhau, Spring thường phải tạo context riêng vì tập bean và thuộc tính cấu hình có thể khác.

Ví dụ:

```java
@SpringBootTest
@ActiveProfiles("test")
class CustomerServiceTest {
}

@SpringBootTest
@ActiveProfiles("test", "stub-payment")
class CheckoutServiceTest {
}
```

Hai test class có profile khác nhau. Context của test thanh toán có thể nạp thêm bean hoặc cấu hình thuộc profile `stub-payment`, do đó không thể mặc nhiên xem hai context là giống nhau.

Resolver chọn profile dựa trên environment variable hoặc system property cũng có thể khiến các lần chạy tạo ra context khác nhau. Điều này có thể làm tăng số context trong cache và thời gian chạy test suite. Hãy giữ tập profile ổn định trong một lượt chạy và chỉ thay đổi khi mục tiêu test thực sự yêu cầu.

Context caching không thay thế việc quản lý dữ liệu test. Profile quyết định cấu hình và bean được nạp; transaction, fixture, database cleanup và trạng thái mutable vẫn cần chiến lược riêng.

## 13. Kết hợp @ActiveProfiles với @TestPropertySource và thuộc tính Spring Boot

Profile chọn nhóm cấu hình và bean cần active. `@TestPropertySource` có vai trò khác: bổ sung hoặc ghi đè property source dành cho test.

Ví dụ:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.checkout.enabled=true",
        "checkout.retry-limit=1"
})
class CheckoutServiceTest {
    // ...
}
```

Trong ví dụ, profile `test` chọn cấu hình theo môi trường kiểm thử, còn `@TestPropertySource` cung cấp hai thuộc tính cụ thể cho test class.

Có thể dùng file property riêng:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:/checkout-test.properties")
class CheckoutServiceTest {
    // ...
}
```

Không nên dùng profile để thay thế mọi property override. Nếu chỉ cần đổi một hoặc hai giá trị trong một test class, `@TestPropertySource` có thể diễn đạt mục tiêu trực tiếp hơn. Nếu cần chọn một nhóm bean/cấu hình theo môi trường, profile phù hợp hơn.

## 14. Những lỗi thường gặp khi kế thừa profile và dùng resolver

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Test class con active cả profile lớp cha | `inheritProfiles` mặc định là `true` | Xem khai báo `@ActiveProfiles` ở các lớp cha |
| Test class con nạp profile không mong muốn | Lớp con kế thừa profile mà không chủ ý | Đặt `inheritProfiles = false` khi cần tách biệt |
| Resolver trả về profile sai | Quy tắc đọc system property/environment chưa rõ | Kiểm tra thứ tự ưu tiên và giá trị mặc định |
| Resolver không được gọi | Annotation chưa chỉ định resolver hoặc test dùng context metadata khác | Kiểm tra `@ActiveProfiles(resolver = ...)` trên test class |
| Profile trong `profiles` không xuất hiện như kỳ vọng | Resolver tùy chỉnh đang xác định danh sách profile | Đưa các profile cần thiết vào kết quả resolver hoặc dùng khai báo trực tiếp |
| Bean không được đăng ký | Tên profile không khớp với điều kiện `@Profile` | Kiểm tra tên profile và cấu hình bean |
| Test chạy khác nhau giữa máy và CI | Resolver phụ thuộc environment khác nhau | Ghi rõ nguồn cấu hình và đặt giá trị CI ổn định |
| Context được tạo nhiều lần | Nhiều danh sách profile tạo ra các cấu hình context khác nhau | Kiểm tra profile và metadata của các test class |
| Test bị ảnh hưởng bởi test khác | Dữ liệu mutable hoặc property toàn cục không được khôi phục | Làm sạch trạng thái và quản lý property trong phạm vi test |

Khi profile không như mong đợi, hãy xem danh sách profile cuối cùng mà context sử dụng, annotation được khai báo trên lớp nào, chính sách kế thừa có được bật hay không và resolver trả về những gì. Sau đó mới kiểm tra bean có điều kiện `@Profile` tương ứng.

## 15. Cách chọn giữa khai báo tĩnh và resolver

Không phải test class nào cũng cần `ActiveProfilesResolver`. Có thể chọn theo mức độ biến động của profile:

| Nhu cầu | Cách phù hợp |
|---|---|
| Tất cả test trong lớp dùng một profile cố định | `@ActiveProfiles("test")` |
| Lớp con bổ sung profile chung của lớp cha | Kế thừa mặc định với `inheritProfiles = true` |
| Lớp con cần bộ profile độc lập | `inheritProfiles = false` |
| Profile được quyết định bởi system property hoặc environment variable | Custom `ActiveProfilesResolver` |
| Profile phụ thuộc quy ước theo loại test class | Resolver kiểm tra metadata hoặc package |
| Chỉ cần thay đổi vài property trong một test class | Cân nhắc `@TestPropertySource` |

Hãy ưu tiên khai báo tĩnh khi profile đã biết trước và không cần thay đổi theo môi trường. Resolver có giá trị khi thật sự tồn tại một quy tắc chọn profile cần được dùng chung hoặc phụ thuộc dữ liệu runtime.

Kế thừa profile giúp chia sẻ cấu hình chung giữa các test class có quan hệ cha–con. `inheritProfiles = false` cho phép một lớp con tách khỏi cấu hình đó. `ActiveProfilesResolver` đưa ra danh sách profile theo một quy tắc có thể lập trình. Khi ba cơ chế này được dùng có chủ đích, test context sẽ được khởi tạo với đúng nhóm bean và thuộc tính cần thiết, đồng thời người đọc có thể lần theo nguồn gốc của từng profile khi chẩn đoán lỗi.

