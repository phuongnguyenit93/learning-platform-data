# `@MockBean`, `@SpyBean` và chuyển sang `@MockitoBean`, `@MockitoSpyBean`

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot có `CheckoutService` dùng hai dependencies: `StockGateway` (có thể gọi dịch vụ kiểm tồn kho ngoài) và `PricePolicy` (tính tiền). Với integration test, bạn muốn chạy **service thật trong Spring ApplicationContext** nhưng thay StockGateway bằng Mockito mock; ở test khác, bạn muốn **spy** PricePolicy, giữ phương thức thật khi không stub, đồng thời đếm số lần gọi hoặc thay một kết quả có chủ ý. Khi nâng Spring Boot, annotation dùng để override Spring beans cũng đổi.

Trong **Spring Boot 3.3.5**, sử dụng:
- `org.springframework.boot.test.mock.mockito.MockBean`
- `org.springframework.boot.test.mock.mockito.SpyBean`

Từ **Spring Boot 3.4.0**, API cũ được **deprecated** để thay bằng Spring Framework 6.2:
- `org.springframework.test.context.bean.override.mockito.MockitoBean`
- `org.springframework.test.context.bean.override.mockito.MockitoSpyBean`

Theo Spring Boot 4.0 migration guide, **Boot 4 đã loại bỏ** `@MockBean` và `@SpyBean` cũ; không thể tiếp tục import chúng như trước. Việc chuyển không chỉ là đổi tên: cách chọn target, scope, vị trí annotation, default behavior và context cache key có khác biệt. Bài có **hai dự án Gradle độc lập** chứng minh cùng nghiệp vụ với hai thế hệ annotation, tránh trộn Spring Framework versions. <Cite> Các kết luận phiên bản được nêu ở nguồn chính thức mục cuối. 

**Ngữ cảnh cha:** *Phiên bản và chuyển đổi* — Spring Boot testing.

**Mục tiêu học tập:**

1. Phân biệt Mockito object mock/spy với **Spring-managed mock/spy bean override**.
2. Chọn đúng annotation và import theo Boot3.3, Boot3.4/3.5 và Boot4.
3. Hiểu cơ chế `REPLACE_OR_CREATE`, `REPLACE` và `WRAP`, kể cả `enforceOverride=true`.
4. Phân biệt mock trả giá trị mặc định, stubbed mock, spy gọi phương thức thật và stubbed spy.
5. Biết `Mockito.doReturn`/`doThrow` trên spy tránh gọi real method ngay tại lúc stubbing.
6. Nhận diện khi nào type, `name`, `@Qualifier` và field-name fallback chọn sai bean.
7. Không chuyển nguyên vị trí `@MockBean` nằm trong `@Configuration` class sang `@MockitoBean`.
8. Hiểu singleton scope, bean cardinality, FactoryBean, AOP proxy và TestContext cache implications.
9. Hiểu Mockito reset `AFTER` và vì sao mock reset không reset dữ liệu ngoài Spring.
10. Xây dựng **Java 17 + Spring Boot 3.3.5** và **Java 17 + Spring Boot 3.4.13**, cùng source application, test version riêng.
11. Kiểm đủ **16 JUnit Jupiter `@Test` methods**, chia 6 legacy và 10 modern, không phụ thuộc thứ tự.
12. Có checklist nâng cấp Boot4, debugging compilation/bean overrides, các bài tập tự luyện.

**Cố định phiên bản cho source runnable:** Java 17; Spring Boot 3.3.5 / Spring Framework 6.1.x cho bản legacy; Spring Boot 3.4.13 / Spring Framework 6.2.x cho bản modern. Boot4 dùng Spring Framework7 và còn có thay đổi test modules, nên **không tự tuyên bố các build files của Boot3.4 chạy nguyên trạng với Boot4**.

## 2. Ma trận phiên bản và import quan trọng

| Runtime/test stack | Khả dụng | Trạng thái |
|---|---|---|
| Boot3.3.5 + Framework6.1 | `@MockBean`, `@SpyBean` từ Boot | Dùng được, chưa có Framework `@MockitoBean` trong stack quản lý |
| Boot3.4.x + Framework6.2 | Cả annotation Boot cũ và Framework mới | Boot cũ **deprecated** từ 3.4.0; migrate dần |
| Boot3.5.x + Framework6.2 | Framework `@MockitoBean`, `@MockitoSpyBean` | Ưu tiên API mới, chuẩn bị Boot4 |
| Boot4.0+ + Framework7 | Framework Mockito annotations | **Đã remove** Boot `@MockBean`, `@SpyBean`; kiểm module test tương ứng |

**Legacy imports (Boot3.3):**

~~~java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
~~~

**Modern imports (Boot3.4+):**

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

**Không làm:** thêm duy nhất `spring-test:6.2` vào dependency tree Boot3.3 chỉ để compiler tìm thấy annotation, vì Spring Boot BOM đang quản lý Framework6.1 và việc trộn minor versions có thể phá compatibility. Nâng **Spring Boot platform nhất quán**, chạy lại toàn bộ tests.

### 2.1. Mock thuần không tự thay Spring bean

~~~java
// Minh họa unit test không chạy Spring context.
@ExtendWith(MockitoExtension.class)
class PureCheckoutUnitTest {

    @Mock
    StockGateway stockGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void example() { }
}
~~~

Đoạn trên là **snippet**, cần imports Mockito/JUnit và `CheckoutService` constructor phù hợp. `@Mock` tạo Mockito object trong JUnit, `@InjectMocks` thử inject vào Java object, nhưng **không thay một `@Autowired` Spring bean** đang có trong cached ApplicationContext. Với `@SpringBootTest`, nếu service được lấy từ Spring, phải override **bean đúng type/name** hoặc tạo test configuration thích hợp.

**Chọn mock ở đúng tầng:** Nếu muốn kiểm `CheckoutService.quote()` thật, mock StockGateway — **không** mock CheckoutService. Nếu mock chính service-under-test, test không kiểm business branching/tính tiền nữa.

## 3. Hiểu mock và spy qua hành vi

| Loại | Đối tượng gốc | Hành vi không stub | Có được Spring inject? |
|---|---|---|---|
| Mockito `@Mock` | Không cần | Default Mockito answer: primitive `int` thường 0, reference null | Không tự động |
| Mockito `@Spy` | Object Java có sẵn | Gọi real methods | Không tự động |
| Boot `@MockBean` | Bean Spring có thể tồn tại hoặc được bổ sung mock | Mock behavior | Có |
| Boot `@SpyBean` | Spring bean được spy | Real behavior khi không stub | Có |
| Framework `@MockitoBean` | Bean override hoặc mới | Mock behavior | Có |
| Framework `@MockitoSpyBean` | Bean Spring gốc đang tồn tại | WRAP và gọi real behavior khi không stub | Có |

Nếu method `StockGateway.available("SKU-1")` trả `int`, một Mockito mock **không stub** thường trả `0`. Service kiểm `available < units` sẽ báo thiếu hàng. Nếu dùng spy `PricePolicy`, method `totalWithFee(2,100)` có thể thực hiện logic thật ra **220** khi không stub.

### 3.1. Stubbing spies: tránh real method chạy ngay

~~~java
// Với Mockito mock, cách này bình thường:
when(stockGateway.available("SKU-1")).thenReturn(4);

// Với Mockito spy, cách sau CÓ THỂ gọi real method ngay:
when(pricePolicy.totalWithFee(2, 100)).thenReturn(900);

// Thường an toàn hơn khi spy có side effect:
doReturn(900).when(pricePolicy).totalWithFee(2, 100);

// Mô phỏng failure:
doThrow(new IllegalStateException("Pricing unavailable"))
        .when(pricePolicy)
        .totalWithFee(2, 100);
~~~

`when(spy.method())` phải đánh giá lời gọi `spy.method()` trong biểu thức Java, vì vậy real logic có thể chạy **trước khi stubbing hoàn tất**. Nếu method gửi HTTP, mutate DB, gọi Kafka hoặc throw, việc này rất nguy hiểm. `doReturn`/`doThrow` là mẫu thường dùng để tránh real method thực thi tại lúc stub.

Khi bạn muốn spy real behavior, **không stub** và dùng `verify(spy).method(...)`; đây là mục tiêu khác hoàn toàn.

## 4. Framework 6.2 bean override strategies

### 4.1. `@MockitoBean` = `REPLACE_OR_CREATE`

~~~java
@MockitoBean
StockGateway stockGateway;
~~~

Spring TestContext tìm bean phù hợp trong application context. Nếu có bean, nó bị **thay bởi mock**. Nếu không có, mặc định **đăng ký thêm mock bean mới**, theo strategy `REPLACE_OR_CREATE`.

Đây là lựa chọn hợp lý khi test slice cố ý không tạo collaborator thật (ví dụ controller slice cần một mocked service). Nhưng ở full integration test, một bean quan trọng biến mất do sai component scan mà test vẫn xanh vì mock được thêm mới có thể che lỗi kiến trúc.

### 4.2. `@MockitoBean(enforceOverride = true)` = `REPLACE`

~~~java
@MockitoBean(enforceOverride = true)
StockGateway stockGateway;
~~~

Muốn **phải có bean gốc**, dùng `enforceOverride=true`. Nếu bean target không tồn tại, context setup báo lỗi thay vì bổ sung mock mới. Trong dự án demo modern, `LocalStockGateway` thực sự tồn tại dưới `@Component` nên điều kiện này hợp lệ.

**Không bắt buộc enforce cho mọi test.** Nếu service ngoài `@WebMvcTest` slice vốn không được nạp, `REPLACE_OR_CREATE` có thể là chính sách đúng.

### 4.3. `@MockitoSpyBean` = `WRAP`

~~~java
@MockitoSpyBean
PricePolicy pricePolicy;
~~~

`@MockitoSpyBean` **bọc bean thật bằng spy**, yêu cầu **đúng một candidate hiện hữu** để wrap. Nếu không có bean hoặc nhiều candidates không được phân biệt, context setup fail. Spring Framework bean overrides hiện đại chỉ hỗ trợ **singleton**; non-singleton/prototype/request-scoped target không thể override theo cách này.

Spy và mock không cùng bản chất:
- Mock dùng stubbed/default behavior; thường bỏ real dependencies, tránh network.
- Spy giữ real behavior trừ các methods đã stub; nguy cơ side effects vẫn tồn tại.
- Spy trên bean có Spring AOP proxy/`@Transactional` không tự chứng minh transaction interceptor đã chạy; phải kiểm proxy/target behavior riêng.

### 4.4. FactoryBean, AOP và scope

Nếu bean được `FactoryBean<T>` tạo:
- MockitoBean thay FactoryBean bằng một singleton mock của **object type T**.
- MockitoSpyBean tạo spy cho **object mà FactoryBean trả ra**, không spy bản thân factory.
- `@Transactional`, `@Cacheable`, `@Async` proxies có thể bị thay/bọc với behavior khác legacy: việc verify chỉ Mockito interactions **không chứng minh** transaction/security/cache behavior thật.
- Spring Framework annotation không hỗ trợ overriding non-singleton targets; nếu test cũ nhắm prototype, phải thiết kế lại fixture/bean scope.

**Khi cần kiểm AOP thật, đừng mock layer mang interceptor.** Mock client thấp hơn hoặc chạy integration test giữ real service bean, rồi assert DB transaction/cache/security semantics.

## 5. Tìm bean đúng: type, name, qualifier, field name và context cache

### 5.1. Chỉ một bean cùng type

Trong app có `LocalStockGateway implements StockGateway` là **duy nhất**. Field:

~~~java
@MockitoBean
StockGateway stockGateway;
~~~

chọn target theo type; không có ambiguity. Field cũng được framework inject mock sau khi override, không cần `@Autowired` riêng.

### 5.2. Nhiều beans cùng interface

Nếu có hai StockGateway implementations, cần chỉ rõ tên/qualifier:

~~~java
@MockitoBean(name = "primaryStockGateway")
StockGateway stockGateway;
~~~

hoặc:

~~~java
@MockitoBean
@Qualifier("primaryStockGateway")
StockGateway stockGateway;
~~~

Hai snippets này **chỉ minh họa**, production code mẫu không có `primaryStockGateway`. Khi annotation đặt trên field, `@Qualifier` được dùng để phân biệt; nếu không có qualifier, **tên field** có thể là *fallback qualifier*. Khác field names giữa test classes có thể khiến TestContext cache key khác nhau và tăng startup count.

**Bẫy:** `StockGateway stockGateway` và `StockGateway inventory` tuy cùng Java type nhưng metadata qualifier fallback khác. Đừng dùng những tên tùy tiện nếu nhiều classes mong chia sẻ một context key.

### 5.3. Annotation ở type level

Với Spring Framework6.2 tương ứng Boot3.4.13:

~~~java
@SpringBootTest
@MockitoBean(
        name = "localStockGateway",
        types = StockGateway.class,
        enforceOverride = true)
class ExampleTest {
}
~~~

Đoạn này chỉ minh họa, cần imports Spring và JUnit trong class thật. Khi annotation được đặt trên **test type**, dùng thuộc tính `types`, khác legacy `classes`/`value` của `@MockBean`. Khi chỉ định `name`, danh sách `types` **phải có một type**. Có thể lặp annotations ở type level hoặc tạo **composed annotation** dùng lại giữa tests.

**Bài chạy thật** ở mục 11 có class `ModernByNameTest` minh họa đầy đủ.

### 5.4. Context hierarchy

Nếu dùng `@ContextHierarchy`, mock/spy override mới có thể được áp dụng đến các context levels theo mặc định. Khi cần đúng một level, Framework 6.2 hỗ trợ `contextName` khớp với `@ContextConfiguration(name=...)`:

~~~java
@MockitoBean(contextName = "app-config")
StockGateway stockGateway;
~~~

Đây là snippet cho hierarchy đã được cấu hình bên ngoài bài runnable. Không đặt `contextName` nếu project không có named hierarchy. Với nhiều child contexts, ghi rõ bean owner/level để tránh mock sai parent hay tạo contexts dư thừa.

## 6. Không copy annotation cũ trong `@Configuration` sang bản mới

Boot legacy cho phép các fields `@MockBean`/`@SpyBean` trên `@Configuration`/`@TestConfiguration` classes trong một số pattern:

~~~java
// Legacy placement: cần di chuyển khi migration.
@Configuration
class LegacyMockConfig {

    @MockBean
    StockGateway stockGateway;
}
~~~

Spring Framework `@MockitoBean`/`@MockitoSpyBean` **không hỗ trợ cách dùng field đó trên `@Configuration` class** như Boot legacy. Đổi nguyên văn:

~~~java
// KHÔNG nên làm:
@Configuration
class NewMockConfig {

    @MockitoBean
    StockGateway stockGateway;
}
~~~

không phải migration hợp lệ. Đây là **phản mẫu**, không thuộc project runnable.

**Cách đúng đơn giản nhất:** đặt annotation trên field của JUnit test class:

~~~java
@SpringBootTest
class CheckoutTest {

    @MockitoBean
    StockGateway stockGateway;
}
~~~

**Nếu nhiều classes cần cùng mock:** tạo composed annotation ở cấp test type:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = StockGateway.class)
@interface WithMockStockGateway {
}
~~~

Đoạn annotation là snippet với `StockGateway` giả định đã định nghĩa và thêm `package demo.migration;` nếu đặt trong file. Áp `@WithMockStockGateway` trên test classes cần mock; không dùng để đánh dấu production `@Configuration`.

**Lựa chọn khác:** tạo Mockito mock thủ công trong một `@TestConfiguration @Bean` để kiểm riêng bean factory behavior, nhưng cần hiểu duplicate bean names, primary/qualifier, reset policy. Cách này không có auto-reset equivalent nếu bạn không cấu hình nó. Đừng bật global `spring.main.allow-bean-definition-overriding=true` chỉ để che bean graph conflicts.

## 7. Mock reset và test isolation

Trong Boot legacy, enum `MockReset` là:

~~~java
import org.springframework.boot.test.mock.mockito.MockReset;

@MockBean(reset = MockReset.AFTER)
StockGateway stockGateway;
~~~

Trong Framework mới:

~~~java
import org.springframework.test.context.bean.override.mockito.MockReset;

@MockitoBean(reset = MockReset.AFTER)
StockGateway stockGateway;
~~~

`AFTER` là default phổ biến: Mockito stubbings và interaction history được reset **sau mỗi JUnit test method**. Hai packages có enum riêng, không thay import một nửa. `BEFORE`/`NONE` có use cases nhưng có thể gây test order dependencies nếu lạm dụng.

**Không reset:**
- Database writes do real spy method thực hiện.
- Kafka/Redis contents.
- Static fields hoặc ThreadLocal state.
- Files trên disk.
- Background tasks vẫn chạy sau test.

Nếu hai JUnit methods chạy đồng thời trên **cùng cached Spring ApplicationContext** và cùng một mock, một test có thể reset/stub mock khi test khác đang dùng. Dùng fixture độc lập, chạy tuần tự nhóm shared mocks hoặc JUnit `@ResourceLock` (cùng key cho mọi participants trong một Jupiter JVM). Khóa JUnit **không đồng bộ giữa Gradle forks/CI jobs**; không dùng `@DirtiesContext` đại trà để “chữa” mock reset, vì context rebuild tốn kém và có thể gây thêm race.

## 8. Hai dự án runnable tách phiên bản

Cùng năm file production Java được dùng **trong hai Gradle projects độc lập**:

~~~text
legacy-boot33/
  settings.gradle
  build.gradle
  src/main/java/demo/migration/MockMigrationApplication.java
  src/main/java/demo/migration/StockGateway.java
  src/main/java/demo/migration/LocalStockGateway.java
  src/main/java/demo/migration/PricePolicy.java
  src/main/java/demo/migration/CheckoutService.java
  src/test/java/demo/migration/LegacyMockBeanTest.java
  src/test/java/demo/migration/LegacySpyBeanTest.java

modern-boot34/
  settings.gradle
  build.gradle
  src/main/java/demo/migration/MockMigrationApplication.java
  src/main/java/demo/migration/StockGateway.java
  src/main/java/demo/migration/LocalStockGateway.java
  src/main/java/demo/migration/PricePolicy.java
  src/main/java/demo/migration/CheckoutService.java
  src/test/java/demo/migration/ModernMockitoBeanTest.java
  src/test/java/demo/migration/ModernMockitoSpyBeanTest.java
  src/test/java/demo/migration/ModernByNameTest.java
~~~

**Hướng dẫn tạo chính xác:** tạo **cả năm file** của mục 9 với **cùng nội dung** ở đường dẫn `src/main/java/demo/migration/` trong **cả legacy và modern**. Các file cấu hình Gradle và test Java được tách theo version ở mục 10/11. Đừng đặt Modern test vào Boot3.3 project vì class `@MockitoBean` của Framework6.2 chưa có.

Bài dùng hai project độc lập thay vì cố nạp hai Spring Boot Gradle plugin versions trong cùng Gradle root classloader. Mỗi project tự quản BOM/dependencies phù hợp.

## 9. Năm class production Java chung cho cả hai versions

### 9.1. `MockMigrationApplication.java`

~~~java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockMigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MockMigrationApplication.class, args);
    }
}
~~~

**File:** `src/main/java/demo/migration/MockMigrationApplication.java` trong mỗi project.

### 9.2. `StockGateway.java`

~~~java
package demo.migration;

public interface StockGateway {

    int available(String sku);
}
~~~

**File:** `src/main/java/demo/migration/StockGateway.java`. Đây là boundary được mock trong các integration tests. Production có thể gọi external inventory API, nhưng demo dùng implementation local để không cần internet/Docker.

### 9.3. `LocalStockGateway.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Component;

@Component
public class LocalStockGateway implements StockGateway {

    @Override
    public int available(String sku) {
        return "OUT".equals(sku) ? 0 : 8;
    }
}
~~~

**File:** `src/main/java/demo/migration/LocalStockGateway.java`. Bean name mặc định là `localStockGateway` và đây là **StockGateway implementation duy nhất** trong context. Stock cho SKU khác OUT là 8; đủ cho spy tests mà không cần stubs.

### 9.4. `PricePolicy.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Component;

@Component
public class PricePolicy {

    public int totalWithFee(int units, int pricePerUnit) {
        if (units < 1 || pricePerUnit < 0) {
            throw new IllegalArgumentException(
                    "Invalid price input");
        }

        return Math.addExact(
                Math.multiplyExact(units, pricePerUnit),
                20);
    }
}
~~~

**File:** `src/main/java/demo/migration/PricePolicy.java`. Real result `totalWithFee(2,100)` là **220**, `totalWithFee(1,100)` là **120**. Math exact giúp không silently overflow int; project thật tính tiền nên cân nhắc BigDecimal/currency policy.

`PricePolicy` là concrete, singleton mặc định, không có AOP proxy và không gọi resource ngoài. Đây là target lý tưởng để học `@MockitoSpyBean` WRAP behavior mà không lẫn các trường hợp phức tạp.

### 9.5. `CheckoutService.java`

~~~java
package demo.migration;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockGateway stockGateway;
    private final PricePolicy pricePolicy;

    public CheckoutService(
            StockGateway stockGateway,
            PricePolicy pricePolicy) {

        this.stockGateway = stockGateway;
        this.pricePolicy = pricePolicy;
    }

    public int quote(String sku, int units) {
        if (sku == null || sku.isBlank() || units < 1) {
            throw new IllegalArgumentException(
                    "Invalid order input");
        }

        if (stockGateway.available(sku) < units) {
            throw new IllegalStateException(
                    "Insufficient stock");
        }

        return pricePolicy.totalWithFee(units, 100);
    }
}
~~~

**File:** `src/main/java/demo/migration/CheckoutService.java`. Constructor DI là rõ ràng; không `new LocalStockGateway()` thủ công bên trong service, nên test override ở Spring context thực sự thay đúng dependency.

**Đường hành vi:**
- `quote("SKU-1",2)` với gateway thật available=8: price=220.
- Với gateway mocked trả 4: price=220.
- Với gateway mocked không stub: available int=0, ném `"Insufficient stock"`.
- Với units=0/sku rỗng: ném `"Invalid order input"` **trước khi gọi gateway**.
- Với spy pricing stubbed `doReturn(777)` ở `(2,100)`: result=777.

Không tạo test-only `@Configuration` ở package `demo.migration` làm bean scan bị ảnh hưởng ngoài ý muốn. Tất cả override annotations trong ví dụ đều nằm trên **JUnit test class/field**.

## 10. Project legacy: Spring Boot 3.3.5

### 10.1. `legacy-boot33/settings.gradle`

~~~groovy
rootProject.name = 'legacy-mock-bean'
~~~

### 10.2. `legacy-boot33/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

`starter-test` đã quản lý Mockito, JUnit Jupiter, Spring TestContext và Boot legacy Mockito support. Không cần pin `spring-test`6.2 khi vẫn dùng Boot3.3.5.

### 10.3. `LegacyMockBeanTest.java`: 3 JUnit tests

**File:** `legacy-boot33/src/test/java/demo/migration/LegacyMockBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LegacyMockBeanTest {

    @MockBean
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesStubbedStockAndRealCheckout() {
        when(stockGateway.available("SKU-1")).thenReturn(4);

        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void unstubbedMockReturnsZero() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Insufficient stock", error.getMessage());
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void inputValidationPrecedesExternalDependency() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.quote(" ", 2));

        assertEquals("Invalid order input", error.getMessage());
        verifyNoInteractions(stockGateway);
    }
}
~~~

**Đúng 3 `@Test`.** Mock StockGateway thay Spring bean, nhưng `CheckoutService` và `PricePolicy` vẫn thật. Test không stub kỳ vọng Mockito trả 0 cho method int. `verifyNoInteractions` kiểm guard validation chạy trước gateway call.

### 10.4. `LegacySpyBeanTest.java`: 3 JUnit tests

**File:** `legacy-boot33/src/test/java/demo/migration/LegacySpyBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LegacySpyBeanTest {

    @SpyBean
    PricePolicy pricePolicy;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void unstubbedSpyCallsRealMethod() {
        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doReturnOverridesOneMethod() {
        doReturn(777).when(pricePolicy).totalWithFee(2, 100);

        assertEquals(777, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doThrowSimulatesPricingFailure() {
        doThrow(new IllegalStateException("Pricing unavailable"))
                .when(pricePolicy)
                .totalWithFee(1, 100);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Pricing unavailable", error.getMessage());
        verify(pricePolicy).totalWithFee(1, 100);
    }
}
~~~

**Đúng 3 `@Test`.** Không mock StockGateway ở spy class; bean `LocalStockGateway` thật trả 8. `PricePolicy` real method được gọi ở test đầu, còn các test sau dùng `doReturn`/`doThrow`.

**Tổng legacy = 6 JUnit tests.** Vì các test contexts có mock vs spy definitions khác nhau, không giả định hai classes phải chia sẻ đúng một ApplicationContext instance.

## 11. Project modern: Spring Boot 3.4.13

### 11.1. `modern-boot34/settings.gradle`

~~~groovy
rootProject.name = 'modern-mockito-bean'
~~~

### 11.2. `modern-boot34/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Boot3.4.13 dependency management cung cấp Spring Framework6.2.x và API bean overriding mới. `spring-boot-starter-test` mang Mockito; không khai báo `mockito-core` version lẻ khiến framework mock resolver dùng sai phiên bản.

### 11.3. `ModernMockitoBeanTest.java`: 4 JUnit tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernMockitoBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernMockitoBeanTest {

    @MockitoBean(enforceOverride = true)
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationContext context;

    @Test
    void mockReplacesRealStockDependency() {
        when(stockGateway.available("SKU-1")).thenReturn(4);

        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void missingStubDoesNotCallRealGateway() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Insufficient stock", error.getMessage());
        verify(stockGateway).available("SKU-1");
    }

    @Test
    void invalidInputIsRejectedWithoutGatewayCall() {
        assertThrows(
                IllegalArgumentException.class,
                () -> checkoutService.quote(null, 2));

        verifyNoInteractions(stockGateway);
    }

    @Test
    void mockedObjectIsTheActualSpringBean() {
        assertSame(
                stockGateway,
                context.getBean(StockGateway.class));

        assertTrue(
                Mockito.mockingDetails(stockGateway).isMock());
    }
}
~~~

**Đúng 4 `@Test`.** `enforceOverride=true` hợp lệ vì application có `LocalStockGateway` singleton implementing StockGateway. Nếu bean production bị xóa hoặc profile loại bỏ, context setup fail thay vì tạo mock mới. `ApplicationContext` interface **có `getBean`**, nên assertion có API hợp lệ; không gọi `isActive()` trên interface.

### 11.4. `ModernMockitoSpyBeanTest.java`: 4 JUnit tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernMockitoSpyBeanTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ModernMockitoSpyBeanTest {

    @MockitoSpyBean
    PricePolicy pricePolicy;

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationContext context;

    @Test
    void spyUsesRealPricePolicyByDefault() {
        assertEquals(220, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doReturnOverridesSpySafely() {
        doReturn(999).when(pricePolicy).totalWithFee(2, 100);

        assertEquals(999, checkoutService.quote("SKU-1", 2));
        verify(pricePolicy).totalWithFee(2, 100);
    }

    @Test
    void doThrowHandlesPricingFailure() {
        doThrow(new IllegalStateException("Pricing unavailable"))
                .when(pricePolicy)
                .totalWithFee(1, 100);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-1", 1));

        assertEquals("Pricing unavailable", error.getMessage());
        verify(pricePolicy).totalWithFee(1, 100);
    }

    @Test
    void spyIsTheBeanRegisteredWithSpring() {
        assertSame(
                pricePolicy,
                context.getBean(PricePolicy.class));

        assertTrue(
                Mockito.mockingDetails(pricePolicy).isSpy());
    }
}
~~~

**Đúng 4 `@Test`.** `PricePolicy` là một singleton component cụ thể, không có transaction/AOP proxy, nên WRAP chọn được chính xác target. Tests verify real method và stubbing có chủ đích. Spy mặc định reset AFTER mỗi JUnit test; không phụ thuộc thứ tự bốn methods.

### 11.5. `ModernByNameTest.java`: 2 JUnit tests

**File:** `modern-boot34/src/test/java/demo/migration/ModernByNameTest.java`

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@MockitoBean(
        name = "localStockGateway",
        types = StockGateway.class,
        enforceOverride = true)
class ModernByNameTest {

    @Autowired
    StockGateway stockGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void typeLevelOverrideTargetsExistingBeanByName() {
        when(stockGateway.available("SKU-2")).thenReturn(3);

        assertEquals(320, checkoutService.quote("SKU-2", 3));
        verify(stockGateway).available("SKU-2");
    }

    @Test
    void eachTestMustConfigureItsOwnStub() {
        assertThrows(
                IllegalStateException.class,
                () -> checkoutService.quote("SKU-2", 1));

        verify(stockGateway).available("SKU-2");
    }
}
~~~

**Đúng 2 `@Test`.** Tên component mặc định là `localStockGateway`, và chỉ có một StockGateway trong app. Class-level annotation có một `types` khi `name` được chỉ định. Test thứ hai không cần dựa test thứ nhất đã chạy để assert Mockito default behavior; reset AFTER đảm bảo không kế thừa stubbing trong cached context.

**Tổng modern = 4+4+2 = 10 JUnit tests.**

**Tổng hai builds độc lập = 6+10 = 16 JUnit Jupiter `@Test` methods.**

## 12. Chạy Gradle và kết quả mong đợi

Cần JDK17, Gradle tương thích với hai Boot plugins (Gradle8.x phù hợp), quyền tải dependencies từ Maven Central nếu chưa cache. Hai projects **không** dùng web server/DB/containers.

Nếu đã có Gradle wrapper trong từng project:

~~~bash
cd legacy-boot33
./gradlew test
cd ../modern-boot34
./gradlew test
~~~

Windows PowerShell:

~~~powershell
Set-Location legacy-boot33
.\gradlew.bat test
Set-Location ../modern-boot34
.\gradlew.bat test
~~~

Nếu chỉ tạo files như bài mà **chưa có wrapper scripts/JAR**, `./gradlew` không tồn tại. Có thể chạy `gradle test` bằng Gradle đã cài hoặc tạo Gradle Wrapper trước:

~~~bash
cd legacy-boot33
gradle test
cd ../modern-boot34
gradle test
~~~

Chạy riêng lớp trong đúng thư mục dự án:

~~~bash
# Trong legacy-boot33:
./gradlew test --tests demo.migration.LegacyMockBeanTest
./gradlew test --tests demo.migration.LegacySpyBeanTest

# Trong modern-boot34:
./gradlew test --tests demo.migration.ModernMockitoBeanTest
./gradlew test --tests demo.migration.ModernMockitoSpyBeanTest
./gradlew test --tests demo.migration.ModernByNameTest
~~~

**Bảng số tests:**

| Build | Lớp | Số phương thức `@Test` |
|---|---|---:|
| Boot3.3.5 | `LegacyMockBeanTest` | 3 |
| Boot3.3.5 | `LegacySpyBeanTest` | 3 |
| Boot3.4.13 | `ModernMockitoBeanTest` | 4 |
| Boot3.4.13 | `ModernMockitoSpyBeanTest` | 4 |
| Boot3.4.13 | `ModernByNameTest` | 2 |
| **Tổng** | 5 classes | **16** |

Báo cáo Gradle nằm thường tại `build/reports/tests/test/index.html`. **Kết quả được thiết kế để PASS**, nhưng đây là kỳ vọng theo APIs/source và không phải tuyên bố đã chạy Gradle trên máy người đọc. Khi copy vào project thật với custom bean profiles, AOP proxies hoặc test slices, cần chạy compile/tests trên nhánh version tương ứng.

**Vì sao assertions có ý nghĩa:**
- Mock StockGateway thay bean nhưng real CheckoutService vẫn chạy.
- Mock chưa stub trả 0, làm service báo thiếu stock; không âm thầm gọi local implementation (vốn trả 8).
- Spy real PricePolicy trả 220, `doReturn` trả 777/999, `doThrow` mô phỏng failure.
- `verify` kiểm business collaboration và arguments.
- `context.getBean(...)` chứng minh object là Spring-managed mock/spy, không chỉ một Mockito field riêng.
- `enforceOverride` chứng minh bean production tồn tại.
- By-name class-level annotation chọn target theo tên.
- Không có tests cố tình fail hoặc tests phụ thuộc test order.

## 13. Quy trình chuyển đổi repo thật

1. **Chụp baseline:** phiên bản Boot/JDK, test count, failures, Spring ContextCache stats, test task runtime.
2. **Nâng platform nhất quán:** Boot3.3 → patch Boot3.4/3.5 được hỗ trợ phù hợp; không pin spring-test6.2 vào Boot3.3.
3. **Audit tất cả imports** `org.springframework.boot.test.mock.mockito.*`, kể cả class-level annotations và custom test annotations.
4. **Đổi field-level straightforward** sang Framework imports và annotations.
5. **Rà old @Configuration fields**: di chuyển lên test class/type-level/composed annotations; không copy nguyên vị trí.
6. **Rà @MockBean(classes=...)**: đổi thành `@MockitoBean(types=...)` khi type-level theo version hỗ trợ, kiểm bean names.
7. **Rà @SpyBean target cardinality**: cần đúng một existing bean; nếu nhiều candidates, dùng explicit name/qualifier.
8. **Rà target existence**: quyết định khi nào `enforceOverride=true` và khi nào cần create mock trong test slice.
9. **Rà singleton scope**: non-singleton bean tests có thể phải chuyển strategy.
10. **Rà `MockReset` package/behavior**: reset AFTER, BEFORE/NONE và ảnh hưởng giữa methods.
11. **Rà AOP/FactoryBean**: đừng assume proxyTargetAware hoặc factory bean semantics như cũ.
12. **Rà context cache keys**: field names/qualifiers khác nhau tạo variants; thống nhất metadata.
13. **Rà parallel tests**: stubbing/reset shared Mockito objects có thể race trong cached Spring contexts.
14. **Rà tests đang mock SUT**: giữ dependency boundary mocked, còn service cần kiểm thật.
15. **Chạy representative tests + full suite** trên nhánh mới, kiểm JUnit reports và bean override errors.
16. **Chuẩn bị Boot4**: loại hoàn toàn legacy API, đối chiếu testing module reorganizations và migration notes khác.
17. **Code review** thay đổi behavior; không merge chỉ vì compiler hết deprecated warnings.
18. **Giữ migration guardrail tests** bắt missing target, wrong qualifier, accidental mock creation và AOP behavior regressions.

### 13.1. Những diff phổ biến

**Field-level mock:**

~~~diff
-import org.springframework.boot.test.mock.mockito.MockBean;
+import org.springframework.test.context.bean.override.mockito.MockitoBean;

-@MockBean
+@MockitoBean
 StockGateway stockGateway;
~~~

**Field-level spy:**

~~~diff
-import org.springframework.boot.test.mock.mockito.SpyBean;
+import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

-@SpyBean
+@MockitoSpyBean
 PricePolicy pricePolicy;
~~~

**Class-level mock:**

~~~diff
-@MockBean(classes = StockGateway.class)
+@MockitoBean(types = StockGateway.class)
 class CheckoutTest {
 }
~~~

Các đoạn là **diff fragments minh họa**, không là Java standalone files. Chúng chỉ áp dụng khi target bean, annotation placement, Framework version và semantics phù hợp; không dùng chúng làm regex rewrite cho mọi file.

## 14. Các ca khó cần kiểm riêng

### 14.1. Type không có bean

~~~java
@MockitoBean
OptionalGateway optionalGateway;
~~~

Mặc định có thể **tạo mock mới** nếu không có corresponding bean. Với full integration test kỳ vọng bean production thật phải tồn tại:

~~~java
@MockitoBean(enforceOverride = true)
OptionalGateway optionalGateway;
~~~

để fail khi missing. Snippet dùng type `OptionalGateway` giả định, không thuộc source runnable. Test slice lại có thể cần REPLACE_OR_CREATE, vì service collaborator không được tạo trong slice.

### 14.2. Nhiều implementations cùng interface

Legacy `@SpyBean(classes=...)` có thể spy nhiều matching beans theo Boot behavior; `@MockitoSpyBean` mới phải chọn đúng một candidate. Ví dụ:

~~~java
@MockitoSpyBean(name = "primaryPaymentClient")
PaymentClient primaryClient;
~~~

Cần có `PaymentClient`/bean name đó trong app thật; snippet chỉ minh họa. Nếu muốn spy hai clients, khai báo hai targets riêng và kiểm actual object matching. Tránh bỏ qualifier rồi để fallback field name vô tình chọn bean khác.

### 14.3. AOP proxy và security/transaction

Nếu `@Transactional` service bị `@MockitoBean` thay bằng mock, real transaction logic không được kiểm. Nếu spy của một @Cacheable service có AOP proxy, `Mockito.verify` vào target/proxy có thể cần resolver tương ứng, và số lần real method chạy có thể bị cache làm khác. Hãy kiểm behavior thật: database rollback/commit, cache hits, authorization; đừng lấy mock interaction count làm bằng chứng mọi cross-cutting concern đều hoạt động.

### 14.4. FactoryBean

`FactoryBean` có thể tạo type mà code inject. Mock mới có thể thay `FactoryBean` bằng singleton mock của produced type, spy wrap produced object. Không suy rằng `@MockitoSpyBean` spy bản thân factory. Đặt test rõ object/bean name nếu có phức tạp.

### 14.5. Shared mocks và parallel JUnit

Cùng cached context mock có thể bị reset sau Test A trong khi Test B concurrent vẫn đang stub/read. Test clean nhất là tránh mutable cross-test state, run related classes tuần tự khi cần, hoặc dùng `@ResourceLock` cùng key cho mọi participating Jupiter nodes. Vì khóa JUnit không cross Gradle JVMs, với DB/Kafka shared ngoài JVM vẫn phải tách test namespaces.

### 14.6. Khi nào không cần Spring context?

Pure service unit test với Java constructor + Mockito `@Mock`/`@InjectMocks` không cần khởi tạo SpringBootTest. Nó nhanh hơn và tránh bean overriding complexities, nhưng **không chứng minh Spring DI wiring**. Dùng đúng loại test:
- Unit: service logic nhanh, mocked collaborators trong Java.
- Slice: controller/repository/JSON subset; mock những bean không được slice nạp.
- Full context: wiring, transaction, real service integration.
- HTTP real server/DB: khi cần chứng minh transport/persistence và external side effects.

## 15. Lỗi thường gặp và hướng xử lý

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `MockitoBean cannot be resolved` trên Boot3.3 | Framework6.1 không có API | Giữ legacy API hoặc nâng Boot cả stack |
| `MockBean cannot be resolved` trên Boot4 | Legacy API đã remove | Dùng Framework bean override imports và test modules |
| `MockitoSpyBean cannot be resolved` | Sai package/dependency | Kiểm `org.springframework.test.context.bean.override.mockito` và BOM |
| Mock field có nhưng service dùng bean thật | Chỉ dùng Mockito `@Mock`, hoặc service tự `new` dependency | Dùng Spring override và constructor DI |
| Mock thêm bean không mong muốn | REPLACE_OR_CREATE khi target vắng | `enforceOverride=true` khi muốn kiểm target tồn tại |
| Spy không start vì missing bean | WRAP cần target thật | Đăng ký singleton bean đúng scope |
| Spy không start do ambiguous type | Nhiều candidate beans | Explicit `@Qualifier`/`name` |
| Legacy @Configuration mock fields không migrate | Framework mới không hỗ trợ placement đó | Test class/type-level/composed annotation |
| Class annotation `classes=` không compile | API mới dùng `types=` | Chuyển đúng attributes |
| Legacy `proxyTargetAware` không compile | New SpyBean không giữ thuộc tính y hệt | Review proxy-target verification |
| `MockReset` import lỗi kiểu | Boot enum khác Framework enum | Dùng MockReset đúng package |
| Spy stubbing gọi real method | `when(spy.method())` | `doReturn`/`doThrow` |
| Spy reset nhưng DB còn dữ liệu | Mockito reset không rollback DB | Transaction/cleanup fixture |
| Test pass nhưng business service chưa được kiểm | Mock nhầm chính SUT | Mock external boundary, giữ SUT thật |
| Test suite startup chậm hơn | Khác field names/qualifiers tạo nhiều contexts | Chuẩn hóa metadata, xem ContextCache stats |
| Parallel tests chập chờn | Shared mock bị reset/stub giữa methods | Disable parallel ở nhóm này, fixture isolation |
| Multiple bean candidates | Type không đủ rõ | `@Qualifier`/`name` chính xác |
| Bean prototype không override | Framework chỉ singleton override | Chọn chiến lược test khác |
| Test slice không có bean để enforce | Full app vs slice graph khác nhau | Đổi enforce policy có chủ đích |
| Boot4 upgrade fail sau đổi mock annotations | Các testing modules/deps khác cũng đổi | Theo Boot4 migration guide đầy đủ |
| @ContextHierarchy override sai level | Default override lan levels | `contextName` matching named level |

## 16. Checklist review, QA và bài tập

**Checklist trước merge:**

- [ ] Dùng đúng Boot/Framework version theo BOM, không trộn Spring6.1 và 6.2.
- [ ] Imports Boot cũ đã đổi ở nhánh hiện đại, không còn API removed khi lên Boot4.
- [ ] Bean target **thật sự được Spring quản lý**, không khởi tạo `new` trong SUT.
- [ ] Đã quyết định rõ REPLACE_OR_CREATE hay enforceOverride.
- [ ] Spy có đúng một candidate, existing singleton; không áp vào prototype.
- [ ] Nếu nhiều beans cùng type, qualifiers/names đúng và ổn định.
- [ ] Không giữ `@MockitoBean` field trong `@Configuration` class.
- [ ] Class-level annotations dùng `types`, một type nếu có explicit `name`.
- [ ] Dùng `MockReset` đúng package, các tests không phụ thuộc stubbing test trước.
- [ ] Tránh `when(spy...)` có thể gây side effect khi stubbing.
- [ ] Các AOP/transaction/security tests vẫn giữ real behavior cần kiểm.
- [ ] Field names/qualifiers nhất quán để cache reuse hợp lý.
- [ ] Parallel tests không restub/reset shared mocks ngoài synchronization.
- [ ] Có test bean identity/Mockito mockingDetails nếu cần đảm bảo override thật.
- [ ] Chạy compile và JUnit tests cho cả legacy và modern project.
- [ ] Đã xem Boot4 testing-module migration khác, không chỉ annotation names.

**Bài tập tự luyện:**

1. Xóa `@Component` của `LocalStockGateway`. Giải thích vì sao `@MockitoBean(enforceOverride=true)` phải fail trong modern full-context test.
2. Đổi `StockGateway` mock sang `@Mock` của Mockito, giữ `@Autowired CheckoutService`. Vì sao service có thể không dùng Mockito object test field?
3. Thử `when(pricePolicy.totalWithFee(0,100)).thenReturn(1)` với spy. Tại sao việc setup có thể throw `Invalid price input` trước test body logic?
4. Thêm `@Qualifier("localStockGateway")` lên modern field, kiểm bean target selection.
5. Tạo hai StockGateway implementations rồi migration spy; thiết kế qualifiers cho từng bean.
6. Thêm `@MockitoBean(types=StockGateway.class)` ở test type, so với field-level injection.
7. Migrate legacy mock annotation từ `@TestConfiguration` field sang composed type-level annotation.
8. Chọn `MockReset.NONE` thử trong sandbox và quan sát nguy cơ state leak; revert sau thí nghiệm.
9. Giữ real `PricePolicy` nhưng mock StockGateway khi viết transaction test; đánh giá còn kiểm được điều gì.
10. Cho Mockito spy method ghi DB thật; sau test, vì sao phải rollback/cleanup dù Mockito đã reset?
11. Viết một `@WebMvcTest` nơi target service không có sẵn; `enforceOverride=true` có phải policy đúng không?
12. Đổi field name của một MockitoBean ở test class khác và đo context-cache keys/hits.
13. Bật parallel tests trên shared mock rồi điều chỉnh bằng fixtures hoặc resource locks; không dùng `Thread.sleep`.
14. Lập migration plan Boot3.3 → 3.5 → Boot4 gồm compiler, bean targets, coverage và CI reports.
15. Thêm regression test xác nhận bean được override là chính bean mà service sử dụng.
16. Trình bày rõ vì sao annotation migration **không chứng minh** system concurrent safety, database correctness hoặc HTTP contract compatibility.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot 3.4 API — `MockBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): deprecated since 3.4.0, for removal.
- [Spring Boot 3.4 API — `SpyBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html): legacy spy options và deprecation.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): removal của Boot `@MockBean`/`@SpyBean` và giới hạn khi chuyển annotation trên `@Configuration`.
- [Spring Framework 6.2 — MockitoBean và MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): target selection, qualifiers, contextName, strategy, singleton và FactoryBean.
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): REPLACE_OR_CREATE, REPLACE, WRAP.
- [Spring Framework 6.2 API — MockitoBean](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): `types`, `name`, `reset`, `enforceOverride`.
- [Spring Framework 6.2 API — MockitoSpyBean](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): WRAP và singleton behavior.
- [Spring Framework 6.2 API — MockReset](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/bean/override/mockito/MockReset.html): AFTER, BEFORE, NONE.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): SpringBootTest, MockBean, test slices.
- [Spring Boot 3.4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html): Boot3.4 testing và Mockito support.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): customizers, qualifier fallback, cache reuse.
- [Mockito Java API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html): doReturn/doThrow/verify.
- [Gradle Testing](https://docs.gradle.org/current/userguide/java_testing.html): Gradle test task/JUnit Platform.

**Kết luận:** `@MockBean`/`@SpyBean` thuộc Spring Boot Test cũ (Boot3.3), deprecated từ 3.4 và bị remove ở Boot4. Từ Framework6.2, sử dụng `@MockitoBean`/`@MockitoSpyBean` với quy tắc rõ ràng: **mock = REPLACE_OR_CREATE** (hoặc **REPLACE** với `enforceOverride=true`), **spy = WRAP existing singleton**. Không thay imports một cách máy móc trên fields ở `@Configuration`, AOP proxies, nhiều bean candidates hoặc non-singletons. Migrate cả Spring Boot stack, giữ service-under-test thật, kiểm bean target/qualifier, mock reset, context caching và chạy lại test suite trên phiên bản đích.
