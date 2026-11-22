# @ContextConfiguration và khai báo cấu hình tối thiểu trong Spring TestContext

## 1. Vấn đề cần giải quyết

Khi kiểm thử ứng dụng Spring Boot, có những hành vi cần **Spring thực sự tạo bean và tiêm phụ thuộc**, nhưng không cần mở toàn bộ ứng dụng, kết nối database, chạy web server hay nạp hàng loạt auto-configuration. Ví dụ: một service phụ thuộc `Clock` được khai báo bằng `@Bean`, và ta cần xác nhận service có thể được Spring tạo ra với đồng hồ cố định rồi tính đúng thời hạn.

`@ContextConfiguration` là annotation thuộc **Spring TestContext Framework** dùng để chỉ định cấu hình tạo `ApplicationContext` cho bài test: các lớp cấu hình Java, địa chỉ tài nguyên cấu hình hoặc `ApplicationContextInitializer` phù hợp. Khi kết hợp với tích hợp test runner, Spring xây dựng context, quản lý vòng đời/caching và hỗ trợ `@Autowired` vào đối tượng test.

Một cấu hình tối thiểu là **tập bean đủ cho hành vi đang kiểm tra**, bao gồm phụ thuộc và hạ tầng thật sự cần thiết; không phải phiên bản thu nhỏ máy móc của toàn bộ cấu hình production. Nó giúp:

- Kiểm tra **wiring và bean creation** của một nhóm thành phần thực thay vì chỉ gọi constructor bằng tay.
- Cô lập cấu hình thiếu bean, sai qualifier, property hoặc profile ở phạm vi có thể hiểu.
- Kiểm soát phụ thuộc bên ngoài bằng bean fake/stub hoặc mock được đăng ký rõ ràng.
- Giảm thời gian khởi tạo, biến số môi trường và stack trace nhiễu so với context toàn ứng dụng trong những tình huống phù hợp.
- Giữ test đủ gần cơ chế Dependency Injection của Spring trong khi vẫn dễ chạy lặp lại.

**Điểm phân biệt:** `@ContextConfiguration` **không tự kích hoạt Spring Boot auto-configuration** và cũng không mặc nhiên khởi chạy server. Nếu test cần hành vi của auto-configuration, Security filter chain, MVC stack, JPA mapping hoặc một luồng triển khai thật, nên chọn test slice hoặc integration test tương ứng.

## 2. @ContextConfiguration thực sự làm gì?

Ví dụ cú pháp cơ bản:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyTestConfig.class)
class SomeServiceTest {
    @Autowired
    SomeService service;
}
```

Đoạn trên là **mẫu annotation**: `MyTestConfig` và `SomeService` là những kiểu cần định nghĩa trong dự án, không phải một file Java độc lập. Ý nghĩa từng phần:

1. `@ExtendWith(SpringExtension.class)` nối **JUnit Jupiter** với Spring TestContext. Extension hỗ trợ chuẩn bị test instance, dependency injection, lifecycle callbacks và truy cập `ApplicationContext`.
2. `@ContextConfiguration(classes = MyTestConfig.class)` cho Spring biết **cấu hình phải dùng** để dựng context. Với Java config, Spring đăng ký các bean được định nghĩa trong lớp cấu hình và những cấu hình mà nó import/scan một cách chủ đích.
3. `@Autowired` đưa bean từ context vào trường của test (hoặc tham số/constructor theo cơ chế injection tương ứng). Nếu không có bean phù hợp, test có thể fail **trước khi thực hiện thân phương thức `@Test`**.
4. Spring TestContext có thể **cache ApplicationContext** giữa những test có cấu hình tương đương. Context không nhất thiết được tạo lại cho mỗi test method.

Với JUnit 4 đời cũ, tích hợp có thể dùng `@RunWith(SpringRunner.class)`. Ví dụ trong bài sử dụng **JUnit Jupiter (JUnit 5+)**; không ghép `@RunWith` với `@ExtendWith` rồi coi đó là một cơ chế duy nhất.

`@ContextConfiguration` có thể chỉ định:

| Thuộc tính | Tác dụng | Khi nào phù hợp |
|---|---|---|
| `classes` | Một hoặc nhiều lớp cấu hình/component được đăng ký vào context | Java-based config, ví dụ `@Configuration` với `@Bean` |
| `locations` | Đường dẫn tài nguyên cấu hình được `ContextLoader` tương ứng xử lý | Dự án còn dùng XML hoặc tài nguyên cấu hình khác |
| `initializers` | Các lớp `ApplicationContextInitializer` tham gia chuẩn bị context | Cần tùy biến context trước khi refresh |
| `loader` | Chọn `ContextLoader` khi không dùng loader mặc định | Nhu cầu đặc thù, hiếm khi cần cho test cơ bản |
| `inheritLocations`, `inheritInitializers` | Điều khiển kế thừa cấu hình/initializer từ lớp test cha | Bộ test có cấu hình chung ở superclass |

Đối với một bài học Java 17+ thông thường, **`classes = ...` cùng `@Configuration`/`@Bean` là điểm bắt đầu dễ đọc nhất**. Không cần dùng các thuộc tính nâng cao chỉ để nạp hai bean.

## 3. Chọn đúng mức kiểm thử trước khi tạo context

| Câu hỏi muốn kiểm chứng | Công cụ thường thích hợp | Có tải Spring context? |
|---|---|---|
| Hàm tính giá trị hoặc quy tắc thuần Java có đúng? | JUnit, tạo object qua `new`; Mockito nếu cần | Không |
| Hai hoặc vài bean có được Spring nối đúng và phối hợp đúng? | `@ContextConfiguration` + `SpringExtension` | Có, context nhỏ do ta khai báo |
| Service hoạt động với cấu hình Boot/auto-configuration thật? | `@SpringBootTest` với phạm vi phù hợp | Có, thường rộng hơn |
| MVC mapping, controller validation, JSON, filter trong web slice? | `@WebMvcTest` + `MockMvc` hoặc test web phù hợp | Có, context MVC slice |
| Repository/JPA query hoặc ánh xạ entity đúng? | `@DataJpaTest` hoặc integration test database | Có, context persistence slice |
| Endpoint thật cần server HTTP đang chạy? | Integration test có `webEnvironment = RANDOM_PORT` | Có và có server HTTP |

`@ContextConfiguration` không phải lựa chọn mặc định cho mọi test: nếu có thể kiểm tra phương thức thuần Java bằng `new Service(fakeDependency)` thì unit test trực tiếp thường đơn giản hơn. Ngược lại, nếu nguy cơ cần kiểm chứng chính là **Spring bean wiring**, test thuần Java không quan sát được lỗi cấu hình; một context tối thiểu có mục tiêu cụ thể sẽ có giá trị.

Không lấy `@ContextConfiguration` để thay `@SpringBootTest` cho một test đang phụ thuộc vào các bean được Boot tự cấu hình: những bean đó không tự xuất hiện trong minimal context. Một test chỉ nạp hai bean không thể chứng minh toàn bộ ứng dụng Boot khởi động thành công.

## 4. Ví dụ hoàn chỉnh Java 17+: nạp đúng hai bean nghiệp vụ cần thiết

### 4.1. Yêu cầu

Một service xác định yêu cầu có được tham gia đợt xử lý trước thời điểm chốt hay không. Quy tắc: **chỉ được chấp nhận khi thời điểm hiện tại nhỏ hơn deadline** (`now < deadline`); đúng deadline và sau deadline phải bị từ chối.

Service nhận `Clock` qua constructor. Trong test, `Clock` được Spring tạo với thời gian **cố định**, không phụ thuộc đồng hồ thực. Cấu hình chỉ khai báo:

- Một bean `Clock` cố định.
- Một bean `DeadlinePolicy` dùng chính `Clock` đó.

Không cần database, repository, web server, `@SpringBootApplication` hay component scan rộng.

### 4.2. Mã production

Tệp `src/main/java/com/example/testing/DeadlinePolicy.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class DeadlinePolicy {
    private final Clock clock;

    public DeadlinePolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean acceptsBefore(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return clock.instant().isBefore(deadline);
    }
}
```

Đây là class Java độc lập, không có annotation Spring. Chính điều này giúp minh họa **Spring có thể quản lý một object được tạo qua `@Bean` mà class đó không nhất thiết phải gắn `@Service`**. Với logic `isBefore`, khi `now == deadline` kết quả là `false`.

### 4.3. Lớp test và @Configuration tối thiểu

Tệp `src/test/java/com/example/testing/DeadlinePolicyTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {

    private static final Instant NOW =
            Instant.parse("2026-03-01T10:00:00Z");

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }

        @Bean
        DeadlinePolicy deadlinePolicy(Clock clock) {
            return new DeadlinePolicy(clock);
        }
    }

    @Autowired
    DeadlinePolicy policy;

    @Autowired
    ApplicationContext context;

    @Test
    void acceptsWhenDeadlineIsInTheFuture() {
        assertTrue(policy.acceptsBefore(NOW.plusMillis(1)));
    }

    @Test
    void rejectsAtExactDeadline() {
        assertFalse(policy.acceptsBefore(NOW));
    }

    @Test
    void rejectsAfterDeadline() {
        assertFalse(policy.acceptsBefore(NOW.minusMillis(1)));
    }

    @Test
    void rejectsNullDeadline() {
        assertThrows(NullPointerException.class,
                () -> policy.acceptsBefore(null));
    }

    @Test
    void injectsExactlyTheExpectedBusinessBeans() {
        assertNotNull(policy);
        assertSame(context.getBean(DeadlinePolicy.class), policy);
        assertEquals(1, context.getBeansOfType(Clock.class).size());
        assertEquals(1, context.getBeansOfType(DeadlinePolicy.class).size());
        assertFalse(context.containsBean("dataSource"));
    }
}
```

### 4.4. Đọc đúng cơ chế trong ví dụ

- `MinimalConfig` là **static nested configuration class**, có thể tham chiếu rõ ràng qua `DeadlinePolicyTest.MinimalConfig.class`. Việc dùng nested class giúp cấu hình chỉ phục vụ nhóm test này.
- `@Configuration(proxyBeanMethods = false)` cho biết Spring xử lý các `@Bean` như factory methods nhưng không dùng proxy inter-bean methods theo kiểu `proxyBeanMethods=true`. Vì bean `deadlinePolicy` **nhận `Clock` qua tham số** thay vì gọi trực tiếp `clock()`, Spring tiêm đúng singleton đã quản lý.
- `@Bean Clock clock()` tạo đồng hồ cố định tại `NOW`, nên các ca trước/bằng/sau hạn có kết quả quyết định và không cần `Thread.sleep`.
- `@Bean DeadlinePolicy deadlinePolicy(Clock clock)` yêu cầu Spring tìm một bean `Clock` phù hợp rồi đưa vào constructor. Thiếu bean hoặc có nhiều bean `Clock` không phân biệt được có thể khiến context fail lúc tạo.
- `@Autowired DeadlinePolicy policy` chứng minh test nhận bean từ **ApplicationContext**, không phải tự `new` trong test.
- `getBeansOfType` kiểm tra **bean theo kiểu cần thiết**. Không nên tuyên bố context chỉ có tổng cộng hai bean vì Spring còn đăng ký các bean hạ tầng riêng.
- `containsBean("dataSource")` chứng minh cấu hình ví dụ **không tự nạp DataSource mang tên đó**. Đây là quan sát giới hạn của context đã khai báo, không phải một bài test tích hợp database.

Với hai tệp và các dependency đúng, **năm test được thiết kế để đạt**. Chúng không có lệnh `System.out.println`, vì thế không có stdout nghiệp vụ cố định để sao chép. Kết quả được hiển thị theo phiên bản Gradle/Maven, JUnit Platform và cấu hình báo cáo. Trong ứng dụng thật, chỉ khẳng định đạt sau khi chạy test và xem report.

### 4.5. Chạy test trong dự án Spring Boot

Dự án cần Java 17+ và dependency kiểm thử chứa Spring TestContext, JUnit Jupiter (và runner Jupiter). Với nhiều dự án Spring Boot, `spring-boot-starter-test` cung cấp các thành phần chính. Cần cấu hình Gradle/Maven phù hợp với phiên bản dự án; Gradle thường khai báo `useJUnitPlatform()` cho task test.

Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.DeadlinePolicyTest"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.DeadlinePolicyTest"
```

Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=DeadlinePolicyTest test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=DeadlinePolicyTest test
```

Với convention thường gặp, Gradle cung cấp HTML report tại `build/reports/tests/test/index.html`; Maven Surefire ghi kết quả tại `target/surefire-reports/`. Nếu dự án đa module hoặc có test task khác, dùng đúng report của task/module đã chạy.

## 5. Cấu hình tối thiểu: nên khai báo gì, tránh khai báo gì?

Trước khi viết `@Configuration`, hãy vẽ sơ đồ phụ thuộc của hành vi cần kiểm tra, ví dụ:

```text
DeadlinePolicyTest
  └── DeadlinePolicy (bean thật)
        └── Clock (bean fixed dùng trong test)
```

Chỉ có hai bean nghiệp vụ liên quan. Cần thêm bean khi có lý do kiểm chứng cụ thể, chẳng hạn service cần interface `ExchangeRatePort` thì có thể khai báo một fake bean cho interface đó. Đừng thêm `@ComponentScan("com.example")` chỉ để khỏi phải viết hai factory methods: cách quét rộng có thể vô tình nạp controller, scheduler, repository, bean điều kiện hoặc thành phần cần hạ tầng ngoài.

### 5.1. @Configuration với @Bean

Dùng `@Configuration` và `@Bean` khi muốn biết chính xác các bean được đăng ký. Đó là cách đơn giản và ổn định để đặt:
- Một giá trị cấu hình cố định như `Clock.fixed(...)`, policy test hoặc fake gateway.
- Một service thật với dependency được khai báo tường minh.
- Những bean phụ trợ cần cho test (validator, formatter, mapper) nếu hành vi thực sự phụ thuộc chúng.

Không cần gọi trực tiếp các method `@Bean` bên trong nhau. Với `proxyBeanMethods=false`, lời gọi `deadlinePolicy(clock())` trong mã Java thuần sẽ tạo object bằng lời gọi method thông thường, có thể khác bean do Spring quản lý. **Ưu tiên tiêm dependency qua tham số method `@Bean`**, như `deadlinePolicy(Clock clock)`.

### 5.2. @Import để ghép cấu hình có chọn lọc

Nếu đã có cấu hình sản phẩm nhỏ và độc lập, có thể dùng `@Import` trong một test config để đăng ký nó cùng những bean cần bổ sung. Ví dụ minh họa cú pháp:

```java
@Configuration(proxyBeanMethods = false)
@Import(SharedDomainConfiguration.class)
class TargetedTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Đoạn này **không phải file Java độc lập**: `SharedDomainConfiguration` và imports cần được định nghĩa theo dự án. Dù dùng `@Import`, vẫn phải kiểm tra cấu hình được import có kéo theo component scan/auto-configuration hoặc phụ thuộc không mong đợi hay không. Mục tiêu là tải **đúng những bean cần thiết**, không phải kéo toàn bộ ứng dụng vào test một cách gián tiếp.

### 5.3. Nạp nhiều cấu hình bằng classes

`@ContextConfiguration(classes = {DomainConfig.class, TestClockConfig.class})` có thể nạp hai cấu hình được chọn rõ ràng. Nếu `DomainConfig` đã khai báo bean `Clock` khác, context có thể có nhiều bean cùng kiểu; khi đó giải quyết bằng `@Primary`, `@Qualifier` hoặc điều chỉnh cấu hình test theo hợp đồng. Đừng dựa vào việc Spring luôn chọn một bean bất kỳ.

### 5.4. Điều gì không tự xuất hiện?

Một context chỉ khai báo `MinimalConfig` không mặc nhiên có:
- Auto-configured `DataSource`, JPA repositories, transaction manager.
- MVC controllers, `DispatcherServlet`, embedded HTTP server hay Security filter chain.
- Các `@Service` nằm trong package nếu không được đăng ký/import/scan.
- Các bean của ứng dụng Boot được điều khiển bởi `@SpringBootApplication` nếu cấu hình đó không được nạp.
- Mọi property và môi trường khởi động đặc thù của Boot.

Điều này là **đặc tính cần có** của cấu hình tối thiểu. Nếu test bị lỗi vì thiếu một trong các thành phần trên, trước hết xác định test có thật sự cần nó không. Nếu cần thì khai báo đúng bean hoặc chuyển sang loại test phù hợp, thay vì mở rộng context một cách thiếu kiểm soát.

## 6. @SpringJUnitConfig: cách viết gọn tương đương cho JUnit Jupiter

Spring cung cấp `@SpringJUnitConfig`, một composed annotation kết hợp tích hợp `SpringExtension` với khai báo `@ContextConfiguration`. Vì thế, với Java config của ví dụ, có thể thay:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {
    // ...
}
```

bằng:

```java
@SpringJUnitConfig(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {
    // ...
}
```

Hai đoạn là **mẫu annotation minh họa**, phần thân lớp đã được rút gọn; dùng import `org.springframework.test.context.junit.jupiter.SpringJUnitConfig`. Nếu dùng `@SpringJUnitConfig`, không cần khai báo thêm `@ExtendWith(SpringExtension.class)` chỉ để kích hoạt cùng một extension.

Đừng nhầm `@SpringJUnitConfig` với `@SpringBootTest`: cái đầu là tiện ích cho Spring TestContext Java config, còn cái sau khởi động test context có cơ chế của **Spring Boot**, thường bao gồm auto-configuration theo phạm vi đã chọn.

## 7. Khi cần cấu hình property và profile trong minimal context

Có những bean phụ thuộc vào property hoặc `@Profile`. Spring TestContext có các annotation chuyên dụng để kiểm soát đầu vào:

- `@ActiveProfiles("test")`: kích hoạt profile trong context được load, ảnh hưởng những bean hoặc cấu hình có điều kiện theo profile.
- `@TestPropertySource(properties = "feature.mode=sandbox")`: thêm property nguồn riêng cho test, hữu ích khi một bean đọc qua `Environment` hoặc `@Value`.
- `@DynamicPropertySource`: đăng ký property động trong những tình huống như port hoặc URL được tạo lúc chạy test; thích hợp khi có nguồn động.
- `@ContextConfiguration(initializers = ...)`: initializer tùy chỉnh khi bài test thực sự cần chuẩn bị context trước khi refresh.

Ví dụ các annotation sau là **minh họa đặt trên lớp test**, không phải tệp đầy đủ:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = FeatureTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.mode=sandbox")
class FeaturePolicyTest {
    // ...
}
```

Ở đây `FeatureTestConfig` phải là một cấu hình có thật đọc `feature.mode`, và imports tương ứng phải có trong dự án. `@TestPropertySource` không tự biến mọi string thành một bean nghiệp vụ. Nên đọc giá trị từ `Environment` hoặc binding mechanism thực sự được cấu hình; nếu code dùng `@ConfigurationProperties` của Boot, một minimal context thường cần đăng ký/bật cơ chế binding đó một cách rõ ràng.

**Phân biệt với `application.yml`:** Minimal context dùng cấu hình Spring TestContext trực tiếp không mặc nhiên chạy toàn bộ pipeline nạp cấu hình bên ngoài và auto-configuration của Spring Boot. Nếu một test cần kiểm chứng cách Boot nạp `application.yml`, profile files, configuration properties hoặc conditional auto-configuration, `@SpringBootTest` hay một Boot test slice có thể phù hợp hơn.

## 8. Đưa mock hoặc fake vào context nhỏ đúng cách

Một service có thể phụ thuộc repository hoặc external client. Với một test minimal context, thay dependency bằng một **fake có hành vi xác định**, hoặc đăng ký một Mockito mock như một bean.

Minh họa bên trong test config khi `RateGateway` và `PricingService` đã được định nghĩa:

```java
@Configuration(proxyBeanMethods = false)
static class PricingTestConfig {
    @Bean
    RateGateway rateGateway() {
        return org.mockito.Mockito.mock(RateGateway.class);
    }

    @Bean
    PricingService pricingService(RateGateway gateway) {
        return new PricingService(gateway);
    }
}
```

Đây là đoạn minh họa, **không phải chương trình độc lập**. Một test có `@Autowired RateGateway gateway` và `@Autowired PricingService service` có thể thiết lập `when(gateway.findRate(...)).thenReturn(...)`, gọi service thật và xác minh kết quả. Nếu không cần Spring container thì tạo service với mock trực tiếp sẽ gọn hơn.

**Chú ý vòng đời mock:** Spring TestContext có thể cache context chứa cùng instance mock giữa nhiều test method/class. Khi mock là bean tự tạo, các tương tác và stubbing có thể tồn tại ngoài một method nếu không quản lý reset. Dùng cấu hình/cơ chế reset phù hợp hoặc tạo fake không chia sẻ trạng thái; nếu cần `Mockito.reset(mock)` trong `@BeforeEach`, hãy làm có chủ đích và tránh làm mất cấu hình cho test khác. Đừng dựa vào cache như một cách chia sẻ kết quả giữa các bài test.

Trong các phiên bản Spring Framework/Spring Boot có hỗ trợ, `@MockitoBean` hoặc các cơ chế mock bean tương ứng có thể thay bean trong context và xử lý vòng đời theo integration tương ứng. Chi tiết annotation phụ thuộc phiên bản thư viện của dự án. Một trường `@Mock` độc lập trên lớp test **không tự động trở thành bean** mà `@Autowired` của service trong Spring context sử dụng.

Với repository thật, `@ContextConfiguration` + một mock repository chỉ chứng minh **service gọi đúng interface và dữ liệu**. Muốn kiểm tra JPA query, mapping, SQL dialect, transaction hoặc commit, cần test repository/integration với database phù hợp.

## 9. Context cache, trạng thái dùng chung và @DirtiesContext

Spring TestContext có cơ chế cache `ApplicationContext` để không phải dựng lại cùng một cấu hình cho mọi test. Khi nhiều lớp có cùng cấu hình, profile, property và các yếu tố của context cache key, chúng có thể dùng lại context trong cùng tiến trình test.

Điều này cải thiện tốc độ nhưng có một hệ quả quan trọng: **bean singleton mutable có thể giữ trạng thái giữa các test**, ví dụ fake repository in-memory, bộ đếm, cache nghiệp vụ hoặc mock chứa lịch sử invocation. Test có thể chạy xanh khi chạy một mình nhưng đỏ khi chạy cả suite.

Để tránh phụ thuộc thứ tự:
1. Dùng dữ liệu bất biến hoặc bean stateless khi phù hợp.
2. Chuẩn bị/reset dữ liệu giả cho từng test bằng `@BeforeEach`/`@AfterEach` hoặc cơ chế transaction/test fixture có kiểm soát.
3. Đừng sửa cấu hình hay singleton dùng chung từ một test rồi mong test khác nhận giá trị ban đầu.
4. Dùng `@DirtiesContext` khi test **thực sự làm bẩn context** và cần loại context khỏi cache, vì nó có thể khiến Spring dựng lại context và tăng thời gian chạy.

Không nên gắn `@DirtiesContext` vào mọi test chỉ để tránh suy nghĩ về isolation. Với `DeadlinePolicyTest`, bean `Clock.fixed` và `DeadlinePolicy` không có trạng thái biến đổi, nên không cần làm bẩn context sau từng phương thức.

Context cache không phải một hợp đồng rằng cùng một instance sẽ sống qua các lần chạy Maven/Gradle hoặc qua nhiều tiến trình JVM. Luôn dựa vào kết quả test và cấu hình runner đang dùng.

## 10. Đọc lỗi khi cấu hình tối thiểu bị thiếu hoặc sai

Vì context thường được nạp **trước thân phương thức test**, lỗi cấu hình có thể làm toàn bộ các test trong lớp thất bại lúc setup. Khi thấy `Failed to load ApplicationContext`, hãy đọc chuỗi `Caused by` và xác định bean/configuration gây lỗi.

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Thiếu bean phụ thuộc của `@Bean` method/constructor hoặc không có bean theo kiểu | Liệt kê cấu hình đã khai báo và đường phụ thuộc; thêm đúng bean/fake |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng kiểu mà không có qualifier hoặc primary phù hợp | Chọn `@Qualifier`, `@Primary` hoặc giảm cấu hình |
| `BeanCreationException` | Factory method ném lỗi, property thiếu, dependency khởi tạo lỗi | Tìm `Caused by` sâu hơn và method `@Bean` |
| `UnsatisfiedDependencyException` | Spring không thể giải quyết tham số/constructor | Kiểm tra kiểu bean, generic, qualifier và profile |
| Test field `@Autowired` là `null` | Chưa kích hoạt SpringExtension/test runner hoặc test instance không do TestContext chuẩn bị | Kiểm tra annotation JUnit Jupiter và import |
| Spring context load được nhưng thiếu Boot-specific behavior | Test chỉ nạp cấu hình Java nhỏ, chưa bật Boot auto-configuration | Dùng đúng test slice/`@SpringBootTest` nếu hành vi đó thuộc phạm vi kiểm chứng |
| Test lúc chạy riêng xanh, chạy cả suite đỏ | Singleton mutable, mock state hoặc context thay đổi giữa các test | Làm sạch fixture, quản lý state và cache |
| Nạp quá nhiều bean hoặc lỗi database ngoài | Cấu hình import/scan quá rộng, test vô tình kéo phụ thuộc hạ tầng | Rút về các `@Bean` tối thiểu hoặc chọn integration test có hạ tầng thích hợp |

Ví dụ nếu `DeadlinePolicy` được khai báo bean nhưng `Clock` bị xóa khỏi `MinimalConfig`, Spring không thể tiêm `Clock` cho `deadlinePolicy(Clock clock)`. Thông báo lỗi sẽ chỉ về dependency chưa giải quyết, **không phải bằng chứng phương thức `acceptsBefore` tính sai** vì nó có thể chưa từng được gọi.

Không nên bắt đầu sửa bằng cách thêm `@SpringBootTest` cho mọi lỗi thiếu bean. Hãy xác định test đang kiểm chứng DI của một tập nhỏ hay hệ thống Boot thật, rồi khai báo đúng cấu hình tương ứng.

## 11. Tối ưu phạm vi khi dự án lớn

Với một hệ thống nhiều module, cấu hình tối thiểu nên dễ trả lời:
- Những bean nào phải là **implementation thật** để chứng minh hợp đồng?
- Những phụ thuộc nào chỉ cần fake/mock để tái hiện đầu vào?
- Có cần AOP, validation method-level, transaction, cache advice hoặc security proxy không? Nếu **cần kiểm tra các cơ chế đó**, phải nạp chính cấu hình hạ tầng liên quan hoặc dùng integration test.
- Property/profile nào ảnh hưởng quyết định nghiệp vụ? Chúng có được khai báo rõ trong test không?
- Service có tạo thread, gọi mạng, đọc file hoặc sử dụng database ngay trong constructor/`@PostConstruct` không? Nếu có, xem lại việc dùng implementation thật trong minimal context.
- Có cần so sánh cấu hình Boot thực tế không? Nếu có, đừng coi minimal context là bằng chứng đủ.

Một bài test `@ContextConfiguration` thành công chứng minh **những bean đã khai báo có thể tạo và phối hợp theo các assertion của bài test**. Nó không chứng minh những cấu hình bị loại ra khỏi context hoạt động đúng. Để tránh báo cáo quá mức, ghi rõ phạm vi, ví dụ:

> Test với `DeadlinePolicyTest.MinimalConfig` nạp một bean `Clock` cố định và một `DeadlinePolicy`. Các assertion trước/bằng/sau deadline đạt. Bài test không nạp JPA, MVC hoặc cấu hình auto-configuration của ứng dụng.

Đây là mẫu trình bày kết quả có kiểm chứng; khi báo cáo thật phải dựa trên log/test report thuộc đúng lần chạy.

## 12. Checklist trước khi hoàn thành test dùng @ContextConfiguration

- [ ] Đã xác định lý do thực sự cần Spring context thay vì unit test thuần Java.
- [ ] Đã chọn `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration` hoặc `@SpringJUnitConfig` tương đương trong JUnit Jupiter.
- [ ] `classes` trỏ đúng lớp cấu hình; `@Configuration` khai báo đủ bean thật, fake/mock tối thiểu.
- [ ] Các phụ thuộc của `@Bean` được inject đúng theo kiểu/qualifier, không vô tình tạo object mới bằng lời gọi method `@Bean` với `proxyBeanMethods=false`.
- [ ] Không mở component scan toàn ứng dụng hoặc auto-configuration rộng khi không cần.
- [ ] Test dùng `@Autowired` và assertion kiểm tra **hành vi thực**, không chỉ `assertNotNull`.
- [ ] Input biến động như thời gian được cố định hoặc kiểm soát bằng test fixture.
- [ ] Profile/property quan trọng được khai báo rõ, không phụ thuộc tình cờ vào môi trường máy.
- [ ] Bean singleton mutable/mock không rò trạng thái giữa các test; dùng cache/`@DirtiesContext` đúng lúc.
- [ ] Đã phân biệt bằng chứng wiring tối thiểu với integration test của MVC, Security, JPA và Boot auto-configuration.
- [ ] Đã chạy đúng task, kiểm tra report và stack trace trước khi tuyên bố kết quả thực tế là PASS.

**Kết luận:** `@ContextConfiguration` cho phép kiểm thử cơ chế Dependency Injection của Spring bằng **một ApplicationContext được khai báo có chủ đích**. Với `SpringExtension`, một lớp `@Configuration` nhỏ và vài `@Bean` cần thiết, test có thể kiểm tra wiring cùng quy tắc nghiệp vụ một cách quyết định, dễ chẩn đoán. Cấu hình tối thiểu có giá trị khi vừa đủ để chứng minh hành vi được chọn; nếu cần hạ tầng Boot, MVC hoặc database thật, hãy mở phạm vi bằng loại test tương ứng và nêu rõ điều đã được kiểm chứng.