# Dependency injection vào test instance và constructor trong Spring TestContext

Trong JUnit Jupiter thuần Java, test thường tự tạo đối tượng bằng `new`. Khi cần kiểm tra hành vi của bean do Spring quản lý, test có thể nhận dependency từ **ApplicationContext**: ví dụ service đã có cấu hình, repository, bean được chọn theo profile hoặc giá trị từ `application-test.yml`. Spring TestContext Framework cung cấp **dependency injection (DI) vào test instance** bằng field hoặc setter, và **constructor injection** khi tích hợp JUnit Jupiter qua `SpringExtension`.

Hai kiểu injection khác nhau ở thời điểm gán giá trị, khả năng dùng field `final`, cách JUnit giải tham số constructor và tương tác với lifecycle/context cache. Chọn đúng kiểu giúp test dễ hiểu, không bị `null`, không gặp `ParameterResolutionException` và không giữ tham chiếu tới bean của context đã đóng.

## 1. JUnit, SpringExtension và TestContext phối hợp như thế nào?

JUnit Jupiter quản lý việc tạo test instance, chọn phương thức `@Test` và chạy các lifecycle callback. **SpringExtension** là cầu nối Spring TestContext với hệ thống extension của JUnit Jupiter. Spring TestContext nạp (hoặc lấy từ cache) ApplicationContext và dùng các bean trong đó để cung cấp dependency cho test.

```text
JUnit Jupiter runner
        |
        +--> SpringExtension / Spring TestContext
        |        |
        |        +--> @Configuration, @Bean, properties, profiles
        |        |           |
        |        |           v
        |        |      ApplicationContext
        |        |
        |        +--> Constructor parameter resolution (trước khi tạo test object)
        |        |
        |        +--> Field/setter injection (sau khi test object được tạo)
        |
        +--> @BeforeEach --> @Test --> @AfterEach --> report
```

Thành phần **`DependencyInjectionTestExecutionListener`** được đăng ký mặc định trong TestContext chịu trách nhiệm injection vào **field/setter của test instance**. Đối với **constructor** của test JUnit Jupiter, `SpringExtension` triển khai `ParameterResolver` để JUnit có thể tạo test object với bean Spring.

Những annotation thường gặp:

| Thành phần | Mục đích |
|---|---|
| `@ExtendWith(SpringExtension.class)` | Đăng ký tích hợp JUnit Jupiter và Spring TestContext |
| `@SpringJUnitConfig(MyConfig.class)` | Annotation kết hợp SpringExtension với `@ContextConfiguration` để nạp cấu hình xác định |
| `@SpringBootTest` | Nạp application context của Spring Boot và tích hợp SpringExtension |
| `@Autowired` | Yêu cầu DI qua field, setter, constructor hoặc parameter |
| `@Qualifier` | Chọn bean cụ thể khi có nhiều bean cùng type |
| `@Value` | Cung cấp property từ Spring Environment |
| `@TestConstructor(autowireMode = ALL)` | Yêu cầu Spring resolve toàn bộ tham số của test constructor |
| `@TestPropertySource` / `@ActiveProfiles` | Cung cấp property hoặc profile cho context test |
| `@TestInstance` | Kiểm soát JUnit tạo một test object cho mỗi method hay dùng chung một object |
| `@DirtiesContext` | Đánh dấu context phải đóng/bỏ khỏi cache theo thời điểm đã cấu hình |

**Không cần gắn `@ExtendWith(SpringExtension.class)` thêm lần nữa** khi annotation kiểm thử Spring Boot như `@SpringBootTest` hoặc `@SpringJUnitConfig` đã đăng ký nó. Một test chỉ có `@Test` và `@Autowired` mà thiếu tích hợp Spring phù hợp sẽ không tự được inject bean.

### Phân biệt test object với bean

`ShippingPolicyTest` là **test instance** do JUnit tạo. `ShippingPolicy` là **bean** do Spring ApplicationContext tạo. Test instance mặc định có thể được tạo lại trước mỗi method, trong khi bean singleton của cùng context có thể được tái sử dụng. Sự khác biệt này đặc biệt quan trọng với test có trạng thái mutable hoặc `@DirtiesContext`.

## 2. Field, setter và constructor injection khác nhau thế nào?

| Kiểu | Thời điểm inject | Điểm mạnh | Lưu ý |
|---|---|---|---|
| **Field** `@Autowired ShippingService service;` | Sau khi JUnit đã tạo test instance | Rất gọn cho test | Field không thể là `final` theo kiểu injection này; dependency ít hiện trên chữ ký constructor |
| **Setter** `@Autowired void setService(...)` | Sau khi instance được tạo | Có thể thay đổi/tái inject giá trị theo lifecycle | Thêm method setup; cần tránh state ẩn |
| **Constructor** `@Autowired Test(ShippingService service)` | Khi JUnit tạo instance, Spring resolve tham số | Đặt dependency rõ ràng; dùng được field `final` | Phải cấu hình constructor autowiring và lưu ý JUnit `ParameterResolver` |
| **Test method parameter** `@Test void test(@Autowired Service s)` | Khi JUnit gọi test method | Phù hợp bean chỉ dùng ở một method | Chỉ dùng khi có SpringExtension và bean tương ứng |

Một ví dụ field injection về mặt cú pháp:

```java
@SpringJUnitConfig(TestConfig.class)
class ServiceTest {
    @Autowired
    Service service;
}
```

Ví dụ trên chỉ minh họa vị trí annotation; `TestConfig` và `Service` phải được khai báo trong dự án, và cần thêm method `@Test` để có bài test hoàn chỉnh.

Setter injection cũng có thể được viết bên trong test class:

```java
private Service service;

@Autowired
void setService(Service service) {
    this.service = service;
}
```

Còn constructor injection cho phép khai báo biến `final`:

```java
private final Service service;

@Autowired
ServiceTest(Service service) {
    this.service = service;
}
```

**Không suy luận quy tắc test constructor từ production constructor:** Spring có thể tự chọn một constructor duy nhất của production bean mà không cần `@Autowired`, nhưng test class do JUnit tạo. Constructor test cần `@Autowired`, `@TestConstructor(ALL)` hoặc cơ chế parameter injection thích hợp; chỉ có một constructor chưa đủ để mặc định mọi tham số đều được Spring cấp.

## 3. Ví dụ hoàn chỉnh Java 17+: hai kiểu nhận cùng một bean

Ví dụ dùng quy tắc: đơn có subtotal dưới **500.000 VND** trả phí giao hàng **30.000 VND**, từ ngưỡng trở lên được miễn phí. Giá trị subtotal âm không hợp lệ. Ta đặt một bean trong cấu hình test để thấy rõ Spring đã inject đúng object.

Cấu trúc dự án:

```text
src/
├── main/java/com/example/shop/
│   └── ShippingPolicy.java
└── test/java/com/example/shop/
    ├── ShippingTestConfig.java
    ├── ShippingFieldAndSetterTest.java
    └── ShippingConstructorInjectionTest.java
```

### 3.1. Mã production

File **`src/main/java/com/example/shop/ShippingPolicy.java`**:

```java
package com.example.shop;

public final class ShippingPolicy {
    private final long freeShippingThresholdVnd;

    public ShippingPolicy(long freeShippingThresholdVnd) {
        if (freeShippingThresholdVnd < 0) {
            throw new IllegalArgumentException("threshold must be nonnegative");
        }
        this.freeShippingThresholdVnd = freeShippingThresholdVnd;
    }

    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("subtotal must be nonnegative");
        }
        return subtotalVnd >= freeShippingThresholdVnd ? 0L : 30_000L;
    }
}
```

Đây là Java thuần, có thể unit test bằng `new ShippingPolicy(500_000L)` mà không cần Spring. Trong bài này ta dùng Spring context để thực hành cơ chế inject test dependency.

### 3.2. Cấu hình Spring chỉ dành cho test

File **`src/test/java/com/example/shop/ShippingTestConfig.java`**:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ShippingTestConfig {

    @Bean
    ShippingPolicy shippingPolicy() {
        return new ShippingPolicy(500_000L);
    }
}
```

Test config chỉ nạp bean được khai báo, tránh việc phải boot toàn bộ ứng dụng chỉ để kiểm tra cách inject. Vì file nằm trong `src/test/java`, nó thuộc test source set, không phải source production.

### 3.3. Field và setter injection

File **`src/test/java/com/example/shop/ShippingFieldAndSetterTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringJUnitConfig(ShippingTestConfig.class)
class ShippingFieldAndSetterTest {

    @Autowired
    private ShippingPolicy policy;

    private ApplicationContext context;

    @Autowired
    void setContext(ApplicationContext context) {
        this.context = context;
    }

    @Test
    void fieldInjectionProvidesTheConfiguredPolicy() {
        assertEquals(30_000L, policy.feeVnd(499_999L));
        assertEquals(0L, policy.feeVnd(500_000L));
    }

    @Test
    void setterInjectionProvidesTheApplicationContext() {
        assertSame(policy, context.getBean(ShippingPolicy.class));
    }
}
```

Khi chuẩn bị test, Spring TestContext inject `policy` vào field và gọi setter `setContext`. Test thứ nhất kiểm rule của bean đã cấu hình; test thứ hai kiểm field trỏ tới cùng bean singleton mà `ApplicationContext` quản lý.

### 3.4. Constructor injection với `@TestConstructor(ALL)`

File **`src/test/java/com/example/shop/ShippingConstructorInjectionTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.test.context.TestConstructor;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(ShippingTestConfig.class)
@TestPropertySource(properties = "app.currency=VND")
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class ShippingConstructorInjectionTest {

    private final ShippingPolicy policy;
    private final String currency;

    ShippingConstructorInjectionTest(
            ShippingPolicy policy,
            @Value("${app.currency}") String currency) {
        this.policy = policy;
        this.currency = currency;
    }

    @Test
    void constructorProvidesFinalDependencies() {
        assertEquals(0L, policy.feeVnd(500_000L));
        assertEquals("VND", currency);
    }

    @Test
    void injectedPolicyRejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1L));
    }
}
```

Ở đây `@TestConstructor(ALL)` thông báo Spring chịu trách nhiệm resolve **tất cả parameter constructor**, nên tham số `ShippingPolicy` được tiêm theo type và `currency` lấy từ `@Value` dựa trên `@TestPropertySource`. Khi instance được tạo xong, hai field đều `final`.

Hai test class trên có tổng cộng **4 phương thức `@Test`**, dự kiến tất cả PASS khi context, test engine và dependency được cấu hình đúng. Không cần database, MockMvc hay web server. Các class Java và import trong bốn file đủ cho ví dụ với Java 17+ và một dự án Spring Boot có Spring TestContext/JUnit Jupiter tương thích.

### 3.5. Chạy ví dụ qua Maven hoặc Gradle

Dự án cần test dependency như `spring-boot-starter-test` và runner JUnit Jupiter tương thích. Chạy tại thư mục module chứa `pom.xml` hoặc `build.gradle` và wrapper:

```bash
# Maven: chạy riêng hai lớp ví dụ
./mvnw -Dtest=ShippingFieldAndSetterTest,ShippingConstructorInjectionTest test

# Hoặc Gradle: task test dùng JUnit Platform
./gradlew test --tests "com.example.shop.ShippingFieldAndSetterTest" --tests "com.example.shop.ShippingConstructorInjectionTest"
```

Trên Windows sử dụng `mvnw.cmd` hoặc `gradlew.bat`. Chỉ chọn lệnh theo build tool của dự án; không cần chạy cả hai. **Kết quả mong đợi: 4 test thành công, 0 thất bại**. Không có stdout nghiệp vụ cố định vì test báo kết quả qua Maven/Gradle/JUnit, và định dạng báo cáo tùy phiên bản.

Nếu chạy `./mvnw test` hoặc `./gradlew test` cho toàn module, số lượng test có thể lớn hơn 4 do còn các test khác.

## 4. Constructor của test được autowire theo quy tắc nào?

SpringExtension cung cấp việc resolve tham số constructor theo hai hướng:

1. **Từng tham số cụ thể:** nếu parameter mang `@Autowired`, `@Qualifier`, `@Value` hoặc có type `ApplicationContext` phù hợp, Spring có thể xử lý riêng tham số đó.
2. **Toàn bộ constructor:** nếu constructor gắn `@Autowired`, class gắn `@TestConstructor(autowireMode = ALL)`, hoặc cấu hình mặc định cho test constructor được đổi thành `ALL`, Spring đảm nhiệm **tất cả tham số constructor**.

Bảng phân biệt:

| Cấu hình | Cách resolve |
|---|---|
| `@Autowired` trên constructor | Toàn bộ tham số thuộc Spring |
| `@TestConstructor(autowireMode = ALL)` trên test class | Toàn bộ tham số thuộc Spring |
| `spring.test.constructor.autowire.mode=all` | Bật mặc định toàn bộ theo cấu hình Spring TestContext, trừ khi override |
| Mặc định `ANNOTATED` | Chỉ tham số được Spring nhận diện; parameter khác có thể do extension JUnit khác resolve |

Ví dụ **thay thế** constructor của `ShippingConstructorInjectionTest` ở phần 3.4 bằng một constructor có `@Autowired`:

```java
@Autowired
ShippingConstructorInjectionTest(
        ShippingPolicy policy,
        @Value("${app.currency}") String currency) {
    this.policy = policy;
    this.currency = currency;
}
```

Khi dùng cách trên, bỏ `@TestConstructor(ALL)` khỏi class và thêm import `org.springframework.beans.factory.annotation.Autowired`. Đây là **đoạn thay thế**, không tạo thêm constructor trùng chữ ký. Hai lựa chọn cho cùng mục tiêu: bean được cung cấp ngay khi tạo test instance, có thể lưu ở `final` field.

### Phân biệt resolver của Spring và JUnit Jupiter

JUnit cũng có resolver cho `TestInfo`, `TestReporter` và dữ liệu của `@ParameterizedTest`. Nếu constructor được Spring đánh dấu là **autowirable toàn phần**, Spring có trách nhiệm resolve mọi argument; extension khác **không** được giải parameter constructor đó.

Ví dụ không nên làm khi Spring sở hữu toàn bộ constructor:

```java
@Autowired
MyTest(ShippingPolicy policy, TestInfo testInfo) {
    // Spring cố resolve cả TestInfo trong constructor này.
}
```

Đây là ví dụ minh họa ý tưởng, không phải class độc lập. Nếu context không có bean `TestInfo`, việc tạo test object có thể thất bại. Khi cần `TestInfo`, đơn giản hơn là nhận nó tại một method JUnit:

```java
@Test
void usesTestInfo(TestInfo info) {
    assertFalse(info.getDisplayName().isBlank());
}
```

Snippet thứ hai nằm trong test class, cần import `org.junit.jupiter.api.TestInfo`, `org.junit.jupiter.api.Test` và `assertFalse`. JUnit cung cấp `TestInfo` cho method parameter; không cần ép nó thành Spring bean.

Nếu constructor **không** thuộc chế độ ALL, có thể khai báo `@Autowired` cho **một parameter cụ thể** và để JUnit xử lý parameter khác qua resolver riêng. Dù vậy, tách Spring dependencies trong constructor và JUnit metadata trong `@BeforeEach` hoặc `@Test` thường dễ bảo trì hơn.

### Version và cấu hình mặc định

Nếu `spring.test.constructor.autowire.mode` không được đặt thành `all`, chế độ mặc định là `ANNOTATED`. Tùy phiên bản, cấu hình có thể được đặt bằng system property, SpringProperties hoặc JUnit Platform configuration parameter. Nên khai báo `@TestConstructor(ALL)` tại test class khi muốn hành vi rõ, ít phụ thuộc thiết lập chung của máy/CI.

Với Spring Framework 7.0, `SpringExtension` yêu cầu JUnit Jupiter 6.0 trở lên; các dự án Spring Boot thường quản lý bộ phiên bản tương thích. Vì thế không nên copy dependency JUnit một cách tùy tiện từ bài viết cũ vào Spring Framework mới.

## 5. Lifecycle, context cache và `@DirtiesContext`

JUnit mặc định dùng `@TestInstance(PER_METHOD)`: **mỗi phương thức test nhận một test instance mới**. Constructor sẽ được gọi lại khi JUnit tạo instance mới, và field/setter injection được thực hiện cho instance tương ứng. Nhưng Spring TestContext thường **cache ApplicationContext** theo cấu hình. Nếu context được tái dùng, bean singleton có thể là **cùng một object** giữa nhiều test, dù test instance khác nhau.

Với `@TestInstance(PER_CLASS)`, JUnit dùng chung một test instance qua nhiều test method. Constructor thường chỉ chạy một lần cho instance ấy; các field mutable trong class test có nguy cơ bị sử dụng lại không mong muốn.

**Cảnh báo quan trọng:** tránh kết hợp *constructor injection + `PER_CLASS` + `@DirtiesContext` đóng context trước/sau từng test method*. Khi context bị đóng và thay thế, test instance cũ vẫn giữ bean đã inject ở constructor; constructor không chạy lại nên field có thể tham chiếu bean của context đã đóng.

Ví dụ **anti-pattern để nhận diện**, chưa độc lập do `SomeService` và import phụ thuộc ứng dụng:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
class RiskyTest {
    private final SomeService service;

    @Autowired
    RiskyTest(SomeService service) {
        this.service = service;
    }
}
```

Nếu thực sự cần `PER_CLASS` cùng `@DirtiesContext` theo từng method, **field/setter injection** cho phép TestContext tái inject vào instance sau khi context thay đổi. Đơn giản hơn, thường giữ `PER_METHOD` khi dùng constructor injection và hạn chế đóng context không cần thiết.

`@DirtiesContext` không phải cách thay thế cleanup database. Việc đóng/tạo mới context có thể rất tốn thời gian; nên dọn data test, dùng transaction/rollback hoặc fixture isolation khi thích hợp.

## 6. Kiểm soát nguồn bean và property trong Spring Boot

### Bean bị thiếu hoặc có nhiều ứng viên

Nếu test báo thiếu bean, hãy kiểm tra cấu hình test đang nạp. `@SpringJUnitConfig(ShippingTestConfig.class)` chỉ khai báo những bean có trong `ShippingTestConfig` và các import liên quan; nó không tự nạp toàn bộ `@SpringBootApplication`. `@SpringBootTest` thường nạp context lớn hơn. Nếu dùng slice như `@WebMvcTest`, service hoặc repository ngoài slice có thể không xuất hiện; cần cung cấp mock/bean phù hợp.

Khi có nhiều bean cùng interface, inject theo type có thể mơ hồ. Dùng `@Qualifier` để chọn rõ:

```java
@Autowired
PaymentTest(@Qualifier("sandboxGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Đây là snippet minh họa trong test giả định có type `PaymentGateway`, field `gateway` và bean tên `sandboxGateway`; cần import `@Autowired` và `@Qualifier`. Không thể tự chạy độc lập.

### Cấu hình property

Trong ví dụ hoàn chỉnh, `@TestPropertySource(properties = "app.currency=VND")` đặt một property cụ thể mà constructor lấy bằng `@Value`. Trong dự án Spring Boot thật, cũng có thể dùng `@ActiveProfiles("test")` với `src/test/resources/application-test.yml`, `@DynamicPropertySource` cho giá trị động của Testcontainers, hoặc cơ chế được hỗ trợ bởi phiên bản Spring Boot.

Hãy xác nhận test đang nạp profile/property nào. Nếu thiếu `app.currency`, `@Value` không tự sinh giá trị; test có thể thất bại trong khi tạo context/test instance. Tránh dùng nhầm configuration của production database hoặc secret khi test chỉ cần fixture.

### Mockito mock khác Spring bean mock

`@Mock` của Mockito tạo đối tượng mock trong phạm vi test, nhưng **không mặc định đăng ký nó vào ApplicationContext**. Khi muốn thay một bean trong Spring context, dùng cơ chế phù hợp version như `@MockitoBean` (Spring Framework mới) hoặc `@MockBean` trong những dự án Spring Boot trước. Kiểm tra dependency version và import thực tế; đừng gắn annotation theo một bài viết cũ rồi tưởng context được cấu hình đúng.

## 7. Inject dependency trực tiếp vào test method

SpringExtension cũng hỗ trợ parameter injection ở những method JUnit Jupiter thích hợp, không chỉ constructor:

```java
@Test
void shippingRuleWorks(@Autowired ShippingPolicy policy) {
    assertEquals(0L, policy.feeVnd(500_000L));
}
```

Đoạn này là **method đặt trong test class đã đăng ký SpringExtension và nạp bean `ShippingPolicy`**, cần import `@Test`, `@Autowired` và `assertEquals`. Injection ở parameter hữu ích khi dependency chỉ dùng tại một test. Nếu nhiều method cùng dùng một bean, constructor/field thường diễn đạt rõ hơn.

Với `@BeforeEach` và `@AfterEach`, SpringExtension cũng có thể resolve những parameter Spring được nhận diện. Nếu dùng `@ParameterizedTest` cùng Spring parameter, hãy phân biệt parameter nào do JUnit cung cấp từ `@CsvSource`/`@MethodSource` và parameter nào do Spring cung cấp; tránh xung đột giữa các resolver. `@Nested` cũng có thể kế thừa cấu hình Spring của lớp ngoài theo chế độ `@NestedTestConfiguration`, nhưng mỗi nhóm nested **không tự sở hữu một context mới**.

## 8. Chọn kiểu test theo phạm vi bằng chứng

Có DI chưa đồng nghĩa test đã kiểm được mọi ranh giới:

| Mục tiêu | Lựa chọn thường phù hợp |
|---|---|
| Logic thuần, không dùng bean Spring | JUnit thuần + `new`; nhanh và rõ nhất |
| Kiểm một cấu hình bean nhỏ và cách inject vào test | `@SpringJUnitConfig` với cấu hình test gọn |
| Kiểm tự cấu hình và phối hợp bean của ứng dụng Spring Boot | `@SpringBootTest` |
| Kiểm MVC request/status/validation/JSON | `@WebMvcTest` + `MockMvc` và các collaborator được cấu hình |
| Kiểm mapping/query JPA | `@DataJpaTest` hoặc integration test dùng database phù hợp |
| Chỉ cần dependency trong một method test | `@Autowired` parameter method hoặc field có scope rõ |

Nếu test một phép tính nhỏ, khởi động `@SpringBootTest` chỉ để có bean là chi phí không cần thiết. Ngược lại, unit test inject service có repository mock không tự chứng minh query thật hoạt động. Lựa chọn phạm vi vẫn dựa vào **lỗi nào cần phát hiện**.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Hướng kiểm tra |
|---|---|---|
| Field `@Autowired` vẫn `null` | Test không có SpringExtension hoặc listener injection bị loại khỏi cấu hình | Kiểm annotation tích hợp và `@TestExecutionListeners` |
| `ParameterResolutionException` | Constructor parameter không có resolver phù hợp | Dùng `@Autowired` constructor, `@TestConstructor(ALL)` hoặc annotation parameter đúng |
| `NoSuchBeanDefinitionException` | Test context không có bean cần inject | Kiểm `@SpringJUnitConfig`, `@SpringBootTest`, profile, bean definitions |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng type | `@Qualifier`, `@Primary` hoặc cấu hình chọn bean đúng |
| `@Value` không resolve | Property chưa được nạp | `@TestPropertySource`, profile hoặc test properties đúng |
| Constructor nhận `TestInfo` lỗi khi Spring mode ALL | Spring xử lý toàn bộ constructor, không còn resolver khác | Chuyển TestInfo sang method hoặc dùng parameter-level injection đúng |
| Không gán được bean vào field `final` | Field injection xảy ra sau constructor | Dùng constructor injection với `final` |
| Test sau lỗi với context đã đóng | `PER_CLASS` + constructor injection + `@DirtiesContext` theo method | Chọn PER_METHOD hoặc field/setter có tái inject phù hợp |
| Suite chạy chậm | Nạp toàn context, lạm dụng `@DirtiesContext`, thay đổi nhiều cấu hình | Dùng context nhỏ, tái sử dụng cấu hình, giữ state độc lập |
| Test “xanh” nhưng chỉ kiểm bean khác null | Assertion chưa chứng minh hành vi | Gọi method của bean và xác minh kết quả như ví dụ |

Nếu tự thay danh sách `@TestExecutionListeners`, đừng vô tình loại `DependencyInjectionTestExecutionListener`. Khi muốn thêm listener, dùng cơ chế merge đúng thay vì ghi đè mọi listener mặc định.

## 10. Checklist trước khi hoàn thành test dùng DI

- [ ] Tôi biết **vì sao test này cần Spring context**; nếu không cần, dùng unit test thuần.
- [ ] Test đã đăng ký `SpringExtension` trực tiếp hoặc qua annotation phù hợp.
- [ ] Bean, qualifier, profile và property đều đến từ cấu hình test xác định.
- [ ] Field/setter injection diễn ra sau khi JUnit tạo instance; không cố inject field `final`.
- [ ] Constructor injection có `@Autowired`, `@TestConstructor(ALL)` hoặc cơ chế nhận diện parameter tương ứng.
- [ ] Khi Spring nhận toàn constructor, không cho rằng JUnit resolver khác có thể giải các parameter ấy.
- [ ] Tôi phân biệt lifecycle `PER_METHOD`/`PER_CLASS` với Spring context cache.
- [ ] Tôi tránh constructor injection giữ bean cũ khi `@DirtiesContext` đóng context giữa các test method.
- [ ] Nếu có nhiều bean cùng type, `@Qualifier` hoặc cách chọn bean đã được chỉ rõ.
- [ ] Test kiểm **hành vi và kết quả**, không chỉ sự tồn tại của bean.
- [ ] Đã xác nhận build tool nhận diện test và các dependency Spring/JUnit tương thích.

**Ghi nhớ:** JUnit tạo và chạy test instance; Spring TestContext cung cấp bean từ ApplicationContext. **Field/setter injection** gán bean sau khi object được tạo; **constructor injection** nhận bean ngay tại bước tạo object, hỗ trợ dependency `final`. Lựa chọn đúng dựa trên ý định test, phạm vi Spring context và vòng đời thực thi.

### Tài liệu chính thức

- [Spring Framework — Dependency Injection of Test Fixtures](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/fixture-di.html)
- [Spring Framework — SpringExtension và Constructor Injection](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Framework — JUnit Jupiter Integration Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
