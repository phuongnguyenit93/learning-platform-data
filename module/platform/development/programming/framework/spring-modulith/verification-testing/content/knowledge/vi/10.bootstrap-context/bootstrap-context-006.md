# Profile, property source và test configuration

## 1. Vì sao ba cơ chế này quyết định module test có khởi động đúng?

Khi chạy `@ApplicationModuleTest` trong Spring Modulith, Spring Boot dựng một `ApplicationContext` cho phạm vi module được chọn. Các bean đưa vào context không chỉ phụ thuộc vào package và `BootstrapMode`; chúng còn phụ thuộc vào **profile đang kích hoạt, giá trị cấu hình trong `Environment` và những bean bổ sung bởi test configuration**.

Hãy xét module `orders` cần gọi API tồn kho của `inventory`. Ở chế độ `STANDALONE`, implementation nghiệp vụ của `inventory` không tự được nạp. Ta có thể tạo một fake cho bài test, nhưng fake ấy có thể được gắn `@Profile("module-test")` và cần property `orders.test.max-quantity`. Nếu quên bật profile, thiếu property hoặc đặt sai chỗ lớp `@TestConfiguration`, context có thể thất bại trước khi bất kỳ `@Test` nào chạy.

Ba thành phần có vai trò riêng:

| Cơ chế | Quyết định | Ví dụ |
| --- | --- | --- |
| **Profile** | Thành phần/cấu hình nào được kích hoạt theo môi trường | `@ActiveProfiles("module-test")` kích hoạt bean gắn `@Profile("module-test")` |
| **Property source** | Giá trị cấu hình đến từ đâu và nguồn nào được ưu tiên | `@TestPropertySource(properties = "orders.test.max-quantity=5")` |
| **Test configuration** | Những bean bổ sung riêng cho bài test được đăng ký thế nào | `static @TestConfiguration` hoặc `@Import(FakeInventoryConfiguration.class)` |

Còn `@ApplicationModuleTest` và `BootstrapMode` quyết định **phạm vi application module được chọn để bootstrap**. Cấu hình kiểm thử có thể bổ sung bean nhưng không thay đổi ý nghĩa của ranh giới kiến trúc.

Trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`, mục tiêu là dùng các cơ chế này để viết module test có thể tái lập, kiểm thử sự kiện/cơ sở dữ liệu/tích hợp và kết hợp `ApplicationModules.verify()` thành quality gate CI phát hiện phụ thuộc sai và hồi quy.

## 2. Bức tranh tổng thể khi Spring dựng test context

```mermaid
flowchart TD
    T[Module test: orders] --> M[@ApplicationModuleTest]
    T --> P[@ActiveProfiles]
    T --> S[@TestPropertySource]
    T --> C[@TestConfiguration / @Import]
    M --> B[BootstrapMode chọn application modules]
    P --> E[Environment: active profiles]
    S --> E
    C --> R[Bean bổ sung trong test]
    B --> X[ApplicationContext]
    E --> X
    R --> X
    X --> V[Khởi tạo bean và chạy @Test]
```

Có thể hình dung một quy trình logic, dù Spring thực tế xử lý các giai đoạn bootstrap và điều kiện cấu hình đan xen:

1. Xác định lớp cấu hình Spring Boot và module chứa bài test.
2. Áp dụng `BootstrapMode` để chọn module nghiệp vụ.
3. Tạo `Environment` với các active profile và property source.
4. Xử lý cấu hình, component scan, auto-configuration, `@Profile` và các điều kiện `@Conditional...`.
5. Đăng ký bean do test configuration/mock override cung cấp.
6. Tạo bean, inject dependency, khởi động context rồi thực hiện assertion.

Nếu một bean không có mặt, cần hỏi nó **chưa nằm trong phạm vi module**, **bị loại bởi profile/property**, hay **chưa được import/đăng ký**. Ba nguyên nhân dẫn đến cùng triệu chứng “thiếu bean” nhưng cách sửa khác nhau.

## 3. `@ActiveProfiles`: chọn profile cho bài kiểm thử

### 3.1. Kích hoạt profile

Spring Test cung cấp annotation `@ActiveProfiles`:

```java
package com.example.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.ActiveProfiles;

@ApplicationModuleTest
@ActiveProfiles("module-test")
class OrdersModuleTest {
    // Test dùng active profile "module-test".
}
```

`@ActiveProfiles` xác định những profile Spring Test kích hoạt trong `ApplicationContext`. Đây là quyết định của **lớp test**, khác với việc khởi chạy cả ứng dụng qua tham số `--spring.profiles.active=...`.

Profile có thể điều khiển bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
class InventoryAdapterConfiguration {

    @Bean
    @Profile("production")
    InventoryGateway productionGateway() {
        return new RemoteInventoryGateway();
    }
}
```

Đoạn trên chỉ minh họa cú pháp `@Profile`; `InventoryGateway` và `RemoteInventoryGateway` là các kiểu giả định của ứng dụng. Khi chỉ kích hoạt profile `module-test`, bean gắn `@Profile("production")` sẽ không được đăng ký bởi cấu hình này.

**Lưu ý:** một class `@Configuration` mang `@Profile` sẽ chỉ có hiệu lực khi class đó được đưa vào nguồn cấu hình/component scan phù hợp. Bật profile không tự làm Spring quét một module nghiệp vụ đang nằm ngoài phạm vi `STANDALONE`.

### 3.2. Profile và tệp cấu hình Spring Boot

Với Spring Boot, nếu dự án có `src/test/resources/application-module-test.yml`, cấu hình profile-specific có thể được nạp khi profile `module-test` đang hoạt động:

```yaml
# Minh họa nội dung application-module-test.yml, không phải file tạo ở bài này
orders:
  test:
    max-quantity: 3
logging:
  level:
    com.example.shop.orders: DEBUG
```

`application.yml` có thể chứa mặc định dùng chung; `application-module-test.yml` cung cấp giá trị dành cho profile đã bật. Tệp chỉ có hiệu lực nếu thực sự tồn tại trong classpath và được Spring Boot Config Data xử lý; annotation `@ActiveProfiles` không tự tạo file hay bean nào.

Không nên đặt tên profile là `production` trong module test nếu mục tiêu là cô lập tích hợp bên ngoài. Một profile test khác môi trường sản xuất sẽ giúp tránh tình cờ kích hoạt bean gọi dịch vụ thật.

### 3.3. Các hiểu nhầm về profile

- `@ActiveProfiles("module-test")` **không đồng nghĩa** `BootstrapMode.ALL_DEPENDENCIES`. Nó không làm Spring Modulith tự bootstrap mọi module.
- Profile không bảo đảm có database, broker hay external service. Nó chỉ ảnh hưởng việc chọn cấu hình/bean theo điều kiện tương ứng.
- Một bean không được đánh dấu `@Profile` vẫn có thể xuất hiện ở nhiều profile nếu các điều kiện đăng ký khác thỏa mãn.
- Có thể kích hoạt nhiều profile, ví dụ `@ActiveProfiles({"module-test", "integration"})`, nhưng khi nhiều profile cung cấp bean cùng kiểu thì phải kiểm tra xung đột/độ ưu tiên.

## 4. `@TestPropertySource`: cung cấp giá trị cụ thể cho test

### 4.1. Khai báo property trực tiếp

`@TestPropertySource` thuộc Spring Test; nó cho phép thêm property vào `Environment` của test:

```java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

@ApplicationModuleTest
@ActiveProfiles("module-test")
@TestPropertySource(properties = {
    "orders.test.max-quantity=5",
    "orders.test.allow-backorder=false"
})
class OrdersWithTestProperties {
}
```

Nếu có `application-module-test.yml` đặt `orders.test.max-quantity: 3` như ví dụ trên, giá trị inline `5` từ `@TestPropertySource` có mức ưu tiên cao hơn cấu hình data file đó khi Spring giải quyết property cho cùng khóa.

Có thể dùng placeholder trong bean hoặc `@ConfigurationProperties`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;

@TestConfiguration(proxyBeanMethods = false)
class InventoryRuleConfiguration {

    @Bean
    InventoryRule inventoryRule(
            @Value("${orders.test.max-quantity:1}") int maxQuantity) {
        return quantity -> quantity > 0 && quantity <= maxQuantity;
    }
}
```

`InventoryRule` là functional interface giả định. Phần `:1` trong placeholder cung cấp **giá trị mặc định khi không tìm thấy property**, không phải phép xác minh cấu hình đã đúng. Với property bắt buộc trong integration test, thường nên bỏ default để thiếu cấu hình gây lỗi rõ ràng.

### 4.2. Nạp một tệp .properties dành riêng cho test

Nếu cấu hình dài, có thể dùng location:

```java
@ApplicationModuleTest
@ActiveProfiles("module-test")
@TestPropertySource(
    locations = "classpath:/orders-module-test.properties")
class OrdersFromPropertyFileTest {
}
```

Ví dụ này giả định tệp `src/test/resources/orders-module-test.properties` **đã tồn tại** trong dự án. Spring Test nạp location vào property source, giúp quản lý nhiều key dễ hơn khi cấu hình không cần thay riêng từng lớp.

Với cơ chế tải resource mặc định của Spring Framework, `@TestPropertySource` thích hợp nhất cho `.properties` hoặc XML properties; không nên giả định trực tiếp một tệp `.yml` tùy ý sẽ được parse như Spring Boot Config Data nếu không có factory thích hợp. Nếu muốn dùng `application-<profile>.yml`, hãy ưu tiên cơ chế config data theo profile của Spring Boot.

### 4.3. Khác nhau giữa profile và property

| Câu lệnh | Chức năng | Không tự thực hiện |
| --- | --- | --- |
| `@ActiveProfiles("module-test")` | Chọn profile đang hoạt động | Không tự đặt `orders.test.max-quantity=5` |
| `@TestPropertySource(properties = "...")` | Đặt giá trị property cho test | Không tự kích hoạt profile `module-test` |
| `@Profile("module-test")` trên bean | Chỉ đăng ký bean khi điều kiện profile thỏa | Không tự tìm class ngoài module/bootstrap source |
| `@ConditionalOnProperty(...)` | Đăng ký bean tùy giá trị property | Không tự tạo property nếu thiếu |
| `@TestConfiguration` | Khai báo bean test | Không tự có hiệu lực nếu cấu hình top-level chưa được import |

Cần thiết lập đúng cả **điều kiện kích hoạt** và **nguồn giá trị**. Chỉ khai báo `@Profile` trên fake mà quên `@ActiveProfiles` là nguyên nhân thường gặp khiến module test không khởi động được.

## 5. `@TestConfiguration`: nơi đăng ký bean dùng trong test

Spring Boot cung cấp `@TestConfiguration` cho các bean chỉ phục vụ test, ví dụ clock cố định, fake gateway hoặc adapter in-memory.

Có hai cách tổ chức thông dụng.

### 5.1. Cấu hình lồng tĩnh trong test

```java
package com.example.shop.orders;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

class OrdersExampleTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        Clock fixedClock() {
            return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
        }
    }
}
```

Đây là ví dụ rút gọn về **vị trí khai báo cấu hình**; lớp `OrdersExampleTest` thực tế cần annotation test/bootstrap phù hợp. Spring Boot test thường tự nhận diện `static nested @TestConfiguration` và **bổ sung** các bean do nó khai báo vào context của lớp test chứa nó.

### 5.2. Cấu hình top-level và `@Import`

Nếu fake được dùng chung giữa nhiều bài test, có thể đặt nó vào `src/test/java/com/example/shop/testsupport`:

```java
// src/test/java/com/example/shop/testsupport/FixedClockTestConfig.java
package com.example.shop.testsupport;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfig {

    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC);
    }
}
```

Và nhập tại lớp test:

```java
import com.example.shop.testsupport.FixedClockTestConfig;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
@Import(FixedClockTestConfig.class)
class OrdersWithFixedClockTest {
}
```

Khác với cấu hình lồng tĩnh, một lớp `@TestConfiguration` top-level thường **không được Spring Boot component scan tự động nhận**, vì vậy `@Import` làm cho quyết định sử dụng cấu hình trở nên rõ ràng.

Cần lưu ý khi ví dụ có `Clock` sản xuất cùng tồn tại: hai bean cùng kiểu có thể dẫn tới injection mơ hồ; nếu cùng tên còn có thể có lỗi bean definition override. Chọn một bean duy nhất, dùng qualifier/primary có chủ đích hoặc cơ chế thay thế bean phù hợp. Không nên bật `spring.main.allow-bean-definition-overriding=true` cho mọi test để che giấu nguồn xung đột.

## 6. Ví dụ đầy đủ: kết hợp profile, property source và test configuration

Ta xây dựng module test trong ứng dụng `com.example.shop` gồm hai application module:

```text
src/main/java/com/example/shop/
├── ShopApplication.java              // @SpringBootApplication
├── orders/
│   └── CheckoutService.java           // @Service
└── inventory/
    ├── InventoryAvailability.java     // API public
    └── DatabaseInventoryAvailability.java // implementation thật

src/test/java/com/example/shop/orders/
└── CheckoutModuleTest.java
```

Trong ví dụ, `orders` gọi API được `inventory` công bố. Khi test `orders` ở `STANDALONE`, không tự nạp implementation thật của `inventory`. Ta khai báo fake chỉ bật khi profile `module-test` hoạt động và điều khiển giới hạn qua property.

### Bước 1. Định nghĩa API ranh giới module

```java
// src/main/java/com/example/shop/inventory/InventoryAvailability.java
package com.example.shop.inventory;

public interface InventoryAvailability {
    boolean isAvailable(String sku, int quantity);
}
```

### Bước 2. Tạo service thật trong module mục tiêu

```java
// src/main/java/com/example/shop/orders/CheckoutService.java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final InventoryAvailability inventory;

    public CheckoutService(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    public String submit(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }
        if (!inventory.isAvailable(sku, quantity)) {
            throw new IllegalStateException(
                "Inventory rejected: " + sku);
        }
        return "ACCEPTED:" + sku;
    }
}
```

### Bước 3. Viết module test dùng cả ba cơ chế

```java
// src/test/java/com/example/shop/orders/CheckoutModuleTest.java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryAvailability;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
@ActiveProfiles("module-test")
@TestPropertySource(
    properties = "orders.test.max-quantity=5")
class CheckoutModuleTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    Environment environment;

    @Test
    void usesPropertyFromTheTestEnvironment() {
        assertThat(environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("module-test")))
            .isTrue();
        assertThat(environment.getProperty(
            "orders.test.max-quantity", Integer.class))
            .isEqualTo(5);
    }

    @Test
    void acceptsQuantityWithinConfiguredLimit() {
        assertThat(checkout.submit("SKU-1", 4))
            .isEqualTo("ACCEPTED:SKU-1");
    }

    @Test
    void rejectsQuantityAboveConfiguredLimit() {
        assertThatThrownBy(() -> checkout.submit("SKU-1", 6))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("SKU-1");
    }

    @TestConfiguration(proxyBeanMethods = false)
    @Profile("module-test")
    static class InventoryStubConfiguration {

        @Bean
        InventoryAvailability inventoryAvailability(
            @Value("${orders.test.max-quantity}") int maxQuantity) {

            return (sku, quantity) ->
                sku.startsWith("SKU-")
                    && quantity > 0
                    && quantity <= maxQuantity;
        }
    }
}
```

### Phân tích chính xác context được tạo

1. `@ApplicationModuleTest` xác định `orders` là module mục tiêu và mặc định dùng `STANDALONE`.
2. `@ActiveProfiles("module-test")` kích hoạt profile cho Spring Test `Environment`.
3. `@TestPropertySource` thêm `orders.test.max-quantity=5` với phạm vi lớp test này.
4. Spring Boot thấy nested `@TestConfiguration`; điều kiện `@Profile("module-test")` cho phép đăng ký cấu hình đó.
5. Method `@Bean` đọc property, tạo fake `InventoryAvailability`, rồi Spring tiêm vào `CheckoutService` thật.
6. Assertion xác nhận cả active profile, giá trị property và hai nhánh nghiệp vụ.

Do đó một bean fake có kiểu API thuộc `inventory` **không chứng minh rằng module `inventory` thật được bootstrap**. Bài test xác minh logic của `CheckoutService` trước phản hồi giả lập từ ranh giới; nó chưa kiểm chứng repository/adapter tồn kho thật.

Nếu bỏ `@ActiveProfiles("module-test")` mà không có cách khác kích hoạt profile, cấu hình fake bị loại bởi điều kiện. Vì `CheckoutService` cần `InventoryAvailability`, context có thể gặp `UnsatisfiedDependencyException`. Nếu bỏ property và không có nguồn thay thế, placeholder `${orders.test.max-quantity}` không giải quyết được và context thường không khởi tạo bean fake.

## 7. Property source có thứ tự ưu tiên: tránh kết quả khác nhau giữa local và CI

Một property như `orders.test.max-quantity` có thể được khai báo đồng thời tại:

- `application.yml`: cấu hình mặc định.
- `application-module-test.yml`: cấu hình gắn với profile `module-test`.
- `@TestPropertySource(locations = "...")`: một tệp property riêng cho lớp test.
- `@TestPropertySource(properties = "...")`: property inline trong annotation.
- `@DynamicPropertySource`: giá trị động lấy từ container/server test.

Spring áp dụng quy tắc ưu tiên property source để chọn một giá trị khi khóa trùng nhau. Trong phạm vi Spring Test, **property inline của `@TestPropertySource` được ưu tiên hơn property nạp từ file bởi chính `@TestPropertySource`**, và những property test này có thể ghi đè giá trị cấu hình dữ liệu ứng dụng thông thường. `@DynamicPropertySource` có độ ưu tiên cao hơn `@TestPropertySource` theo cơ chế của Spring Test, phù hợp với địa chỉ/port được cấp động.

Không nên tự đoán giá trị cuối khi nhiều nguồn cùng đặt một khóa. Có thể quan sát trực tiếp:

```java
@Autowired
Environment environment;

@Test
void readsTheEffectiveValue() {
    assertThat(environment.getProperty(
        "orders.test.max-quantity", Integer.class))
        .isEqualTo(5);
}
```

Đây là đoạn trích nằm **bên trong** một test class đã có `@ApplicationModuleTest` và import assertion thích hợp, không phải class Java độc lập.

Khi test thất bại chỉ ở CI, hãy ghi nhận giá trị hiệu lực và active profiles (tránh log secret), rồi kiểm tra cấu hình được truyền bởi pipeline. Khác biệt profile/property giữa hai môi trường có thể gây bean condition khác nhau, thay đổi adapter được khởi tạo hoặc kết nối dịch vụ sai địa chỉ.

### Những lỗi cấu hình thường bị bỏ qua

| Tình huống | Hệ quả |
| --- | --- |
| Gõ nhầm `orders.test.max-quantity` thành `orders.tests.max-quantity` | Placeholder bắt buộc có thể không giải quyết được; property gốc không được ghi đè |
| Có default cho placeholder | Bean khởi động bằng default, test có thể xanh nhưng dùng cấu hình sai |
| Property cùng tên xuất hiện trong nhiều nguồn | Giá trị hiệu lực phụ thuộc thứ tự ưu tiên |
| Kích hoạt thêm profile `production` | Có nguy cơ kích hoạt adapter, scheduled job hoặc client thật |
| Import cùng lúc fake và configuration production | Có thể tạo hai bean cùng type/tên hoặc gây side effect ngoài dự kiến |

## 8. `@DynamicPropertySource` cho database và hạ tầng thay đổi theo từng lần chạy

Property inline phù hợp với giá trị cố định. Với Testcontainers, địa chỉ JDBC, user, password hay port có thể được cấp động. `@DynamicPropertySource` của Spring Test cho phép đăng ký giá trị thông qua một supplier.

Ví dụ minh họa một bài module integration test sử dụng PostgreSQL Testcontainers, với dependency Testcontainers tương ứng đã được cấu hình:

```java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@ApplicationModuleTest(
    mode = BootstrapMode.DIRECT_DEPENDENCIES)
@ActiveProfiles("integration-test")
class OrdersDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void registerDataSource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void validatesPersistenceWithProjectFixtures() {
        // Chuẩn bị dữ liệu và repository theo project thật;
        // thêm assertion về ghi/đọc và transaction.
    }
}
```

Ví dụ minh họa **cách đưa thuộc tính JDBC động vào `Environment`**, chưa phải integration test hoàn chỉnh vì phương thức test mới mô tả các bước phải viết tiếp theo model dữ liệu thật. Testcontainers JUnit extension quản lý vòng đời container static; code thực tế cần các dependency Testcontainers/PostgreSQL và môi trường Docker tương thích.

Cần phân biệt:

- `@DynamicPropertySource` đăng ký **giá trị** được tính tại runtime; nó không tự tạo bean repository hay chạy migration.
- `BootstrapMode.DIRECT_DEPENDENCIES` mở rộng **module nghiệp vụ** được chọn; nó không tự dựng PostgreSQL.
- `@ActiveProfiles("integration-test")` chọn **profile cấu hình**; nó không tự cung cấp URL hay schema.

Khi dùng test database, cần xác nhận schema, migration, transaction rollback hoặc cleanup, dữ liệu fixture và sự độc lập của mỗi test. Một câu lệnh query có thể chạy thành công nhưng vẫn không chứng minh mọi quy tắc nghiệp vụ liên module đã đúng.

## 9. Kết hợp `@ConditionalOnProperty` với profile

Bên cạnh `@Profile`, Spring Boot hỗ trợ các condition có thể bật/tắt bean theo property:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExternalAdapterConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "inventory.remote",
        name = "enabled",
        havingValue = "true")
    RemoteInventoryClient remoteInventoryClient() {
        return new RemoteInventoryClient();
    }
}
```

Ví dụ là cú pháp minh họa, `RemoteInventoryClient` là kiểu giả định. Khi `inventory.remote.enabled=false` hoặc property không thỏa condition, bean này không được đăng ký bằng cấu hình đó. Nếu một module khác cần bean ấy và không có ứng viên thay thế, có thể xuất hiện lỗi khởi động.

Cẩn trọng với `matchIfMissing`: nếu cấu hình dùng `matchIfMissing = true`, bean có thể được tạo ngay cả khi test không khai báo property. Điều này thuận tiện cho default production nhưng có thể khiến integration test vô tình gọi external service. Hãy kiểm tra condition và xác định explicit property khi cần tính tái lập.

`@ConditionalOnProperty` và `@Profile` tác động lên **việc đăng ký bean sau khi cấu hình được chọn**. Chúng không giúp vượt qua module boundary mà Spring Modulith đã giới hạn bằng bootstrap mode.

## 10. Profile và test configuration trong kiểm thử sự kiện

Giả sử module `orders` phát sự kiện `OrderSubmitted`; module `notifications` có listener gửi email.

Ở bài test `orders` dạng `STANDALONE`:

- Dùng `@ActiveProfiles("module-test")` để bảo đảm các adapter/test bean đúng điều kiện được kích hoạt.
- Dùng `@TestConfiguration` hoặc `@MockitoBean` để cung cấp ranh giới tồn kho/thanh toán giả lập.
- Giữ logic `orders` và `ApplicationEventPublisher` thật; dùng tiện ích `PublishedEvents` của Spring Modulith Test để xác nhận sự kiện được phát và đúng payload.

Nếu listener thật nằm trong module `notifications` không thuộc phạm vi bootstrap, listener ấy không tự xuất hiện dù event được phát. Vì vậy, assertion “`OrderSubmitted` đã công bố” **khác** với assertion “email đã gửi thành công”. Để kiểm chứng listener và tích hợp messaging, tạo bài kiểm thử có bean listener thật cùng profile/property của broker, email adapter hoặc test fixture phù hợp.

Nếu một profile khiến listener bị tắt, test tích hợp có thể cho kết quả sai dù module đã được chọn. Khi debug, kiểm tra đồng thời **module scope**, **active profile** và **condition theo property** của listener.

## 11. Kiến trúc module và context bootstrap là hai loại kiểm chứng

`@ApplicationModuleTest` có thể thành công với một fake do `@TestConfiguration` cung cấp, nhưng code production của `orders` vẫn có thể phụ thuộc sai vào package nội bộ của `inventory`. Để kiểm tra quan hệ module, dùng `ApplicationModules`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesArchitectureBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Phép kiểm tra trên xác minh các quy tắc phụ thuộc của mô hình application module. Nó **không cần khởi động context Spring Boot để test bean**. Ngược lại, module test phải xử lý profile/property/configuration mới khởi tạo được bean và chạy assertion hành vi.

| Phép kiểm chứng | Bắt được loại lỗi | Không tự bắt được |
| --- | --- | --- |
| `ApplicationModules.verify()` | Phụ thuộc sai chiều hoặc truy cập vượt ranh giới module | Sai profile, placeholder thiếu, DataSource không kết nối |
| `@ApplicationModuleTest` + fake/mock | Module mục tiêu không bootstrap hoặc xử lý sai một nhánh nghiệp vụ | Implementation thật của collaborator bên ngoài bị lỗi |
| Module test có dependency thật/integration test | Wiring, JPA, transaction, event listener và API tích hợp theo assertion | Toàn bộ vi phạm phụ thuộc tĩnh giữa các module |
| Kiểm tra giá trị `Environment` | Sai profile/property source trong test context | Quy tắc nghiệp vụ chính xác nếu không có assertion |

Vì vậy, không nên “sửa” một cảnh báo kiến trúc bằng cách mở rộng `BootstrapMode`, bật profile khác hoặc import thêm bean test. Các thao tác ấy chỉ thay đổi context runtime; quan hệ phụ thuộc trong code cần được sửa tại nguồn và xác minh bằng quy tắc module.

## 12. Thiết kế quality gate CI có thể tái lập

Một pipeline kiểm thử ổn định cần nói rõ những profile và property nào được sử dụng. Một cách tổ chức thực tế:

1. **Architecture verification:** chạy `ApplicationModules.of(ShopApplication.class).verify()` để chặn lỗi ranh giới ngay cả khi bean fake làm các module test chạy xanh.
2. **Module behavior tests:** chạy `@ApplicationModuleTest` với active profile và test property tường minh; giữ collaborator bên ngoài dưới dạng mock/fake khi đó là đúng mục tiêu.
3. **Database/event integration tests:** chạy các bài test có repository/listener/adapter thật và hạ tầng xác định bằng test config hoặc container.
4. **Configuration assertions:** với property quyết định nhánh quan trọng (ví dụ bật/tắt adapter), kiểm tra giá trị hiệu lực và bean được chọn trong context.
5. **Tách môi trường nhạy cảm:** không đưa secret, URL production hoặc thông tin truy cập thật vào test source; cấp property qua môi trường CI hoặc tài nguyên test thích hợp.

Nếu dùng nhiều lớp test có cấu hình khác nhau, Spring Test có thể cache và tái sử dụng `ApplicationContext` cho các cấu hình tương thích. Thay đổi profile, property override hoặc test configuration có thể làm cache key khác và tạo thêm context, ảnh hưởng thời gian chạy. Chỉ dùng `@DirtiesContext` khi thực sự cần vì trạng thái context đã bị thay đổi; với fake stateful nên ưu tiên reset rõ ràng để tránh phụ thuộc thứ tự test.

**Quality gate đúng nghĩa** không phải chỉ đếm test xanh. Mỗi nhóm test cần chứng minh điều mình được giao: quy tắc module, logic module, hay hành vi tích hợp có hạ tầng thật.

## 13. Chẩn đoán lỗi theo ba trục: profile, property, configuration

Khi module test không khởi động hoặc xuất hiện bean ngoài mong đợi, kiểm tra theo thứ tự:

1. **Module mục tiêu:** package của lớp test đúng module cần kiểm chứng chưa? `BootstrapMode` hiện tại là gì?
2. **Profile:** `@ActiveProfiles` đặt trên test chưa; bean/cấu hình có `@Profile` nào đang tắt/bật?
3. **Property source:** test có `@TestPropertySource` hay tệp profile tương ứng chưa? Giá trị hiệu lực của khóa là gì?
4. **Condition:** bean có `@ConditionalOnProperty`, `@ConditionalOnBean` hay các điều kiện auto-configuration khác không?
5. **Test configuration:** class `@TestConfiguration` lồng tĩnh hay top-level? Nếu top-level, đã có `@Import` chưa?
6. **Trùng bean:** fake có bị trùng kiểu/tên với bean production hoặc mock override không?
7. **Hạ tầng:** lỗi có đến từ DataSource, migration, HTTP client hay broker chưa được cấu hình cho profile test không?
8. **Assertion:** bài test đang chứng minh logic module hay tích hợp thật? Có kiểm tra đúng đường chạy đó không?

### Bảng triệu chứng thường gặp

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `UnsatisfiedDependencyException` dù đã viết fake | `@Profile` của fake không active; top-level `@TestConfiguration` chưa import | Bật đúng profile hoặc `@Import` cấu hình |
| `Could not resolve placeholder` | Thiếu key, gõ nhầm tên hoặc property source không nạp | Kiểm tra `Environment`, location và khóa thực tế |
| Bean test không dùng giá trị property mới | Source khác có ưu tiên cao hơn; đang đọc property sai | Xem property hiệu lực và nguồn ghi đè |
| Có bean adapter thật ngoài ý định | Profile production/condition đang bật; import cấu hình quá rộng | Giới hạn config test và profile |
| Hai bean cùng type/tên | Fake và production cùng được nạp | Chọn test double hoặc bean thật, hoặc qualifier/override rõ ràng |
| Local chạy, CI fail | Active profile, biến môi trường hoặc Testcontainers khác nhau | Ổn định cấu hình, dữ liệu, hạ tầng và property động |
| Event phát nhưng listener không chạy | Listener ở module chưa bootstrap hoặc bị profile/condition loại | Kiểm tra phạm vi module, bean listener và transaction/event setup |

Một nguyên tắc thực hành hữu ích là xác định **bean nào cần có**, **điều kiện để nó được tạo**, và **nguồn property điều khiển điều kiện** trước khi sửa test. Như vậy lỗi không bị che bởi việc import thêm hàng loạt cấu hình.

## 14. Bài tập tự kiểm tra

Giả sử bài `CheckoutModuleTest` thuộc `orders` dùng `@ApplicationModuleTest` ở `STANDALONE`. `CheckoutService` yêu cầu `InventoryAvailability` của `inventory`, còn fake được đăng ký qua `static @TestConfiguration` gắn `@Profile("module-test")` và đọc property `orders.test.max-quantity`.

1. Nếu bỏ `@ActiveProfiles("module-test")`, điều gì có thể xảy ra với bean fake và vì sao?
2. Nếu tệp `application-module-test.yml` đặt `max-quantity: 3` còn annotation `@TestPropertySource(properties = "orders.test.max-quantity=5")` đặt `5`, giá trị test thường đọc được là bao nhiêu?
3. `@TestPropertySource(properties = "orders.test.max-quantity=5")` có tự bật profile `module-test` không?
4. Nếu chuyển nested `@TestConfiguration` thành top-level `FakeInventoryConfiguration`, cách nhập cấu hình tường minh nào nên dùng?
5. Nếu mock API tồn kho khiến module test chạy xanh, có kết luận repository tồn kho thật hoạt động và phụ thuộc giữa module hợp lệ chưa?
6. Khi dùng PostgreSQL Testcontainers với port tự sinh, annotation nào phù hợp để đưa JDBC URL vào `Environment`?
7. Khi bean listener ở `notifications` không chạy, ngoài kiểm tra phát sự kiện cần xem ba yếu tố cấu hình nào?
8. Vì sao cần kết hợp `ApplicationModules.verify()` với các module test trong CI?

**Đáp án tham khảo:** (1) fake bị loại bởi `@Profile` và context có thể thiếu `InventoryAvailability`; (2) `5` vì test inline property ghi đè giá trị profile config data thông thường; (3) không; (4) `@Import(FakeInventoryConfiguration.class)`; (5) chưa, test mới chứng minh logic với fake; (6) `@DynamicPropertySource`; (7) module scope, active profile và property/condition của listener, cùng hạ tầng transaction/event; (8) một phép kiểm tra phụ thuộc kiến trúc, phép còn lại kiểm chứng bootstrap và hành vi runtime.

**Ghi nhớ:** khi debug `@ApplicationModuleTest`, hãy xem **`BootstrapMode` chọn module nào, `@ActiveProfiles` kích hoạt điều kiện nào, `@TestPropertySource`/`@DynamicPropertySource` cung cấp giá trị gì và `@TestConfiguration` đăng ký bean ra sao**. Bốn câu trả lời giúp ta giữ module test cô lập có chủ đích, mở rộng tích hợp khi thật sự cần và xây dựng CI đủ sức ngăn lỗi phụ thuộc lẫn hồi quy hành vi.
