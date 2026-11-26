# Bảo đảm CI và máy phát triển dùng cấu hình tương thích

## 1. “Chạy được trên máy tôi” là sai lệch hợp đồng môi trường nào?

Developer chạy `./gradlew test` trên máy cá nhân: toàn bộ test `orders` xanh. Cùng commit đó, CI thất bại khi tạo `ApplicationContext` vì thiếu `shop.orders.currency`. Hoặc cả hai cùng xanh nhưng developer đang chạy JDK 17/H2, CI chạy JDK 21/PostgreSQL; một lỗi mapping hay transaction chỉ xuất hiện trong một môi trường. Vấn đề không chỉ là khác máy, mà là **những giả định quan trọng của bài test không được chuẩn hóa hoặc kiểm chứng**.

Trong chương **CI và quality gate** của học phần `SPRING_MODULITH_VERIFICATION_TESTING`, chúng ta đã có các phép kiểm như `ApplicationModules.verify()`, `@ApplicationModuleTest`, kiểm thử sự kiện, database và tích hợp. Những phép kiểm đó chỉ là quality gate đáng tin khi **cùng commit được kiểm dưới cấu hình có ý nghĩa tương đương** ở máy phát triển và CI.

**Tương thích không có nghĩa hai máy giống hệt nhau.** Laptop có thể chạy macOS/Windows còn runner chạy Linux; dung lượng RAM, đường dẫn workspace và Docker daemon khác nhau. Điều cần đảm bảo là những khác biệt đó **không thay đổi hợp đồng mà test tuyên bố kiểm chứng**.

| Nhóm hợp đồng | Điều cần tương đương | Dấu hiệu drift phải phát hiện |
| --- | --- | --- |
| **Toolchain** | Phiên bản Java dùng để compile/chạy test, Gradle wrapper, dependency resolution | Local dùng JDK 17 nhưng CI 21; chạy `gradle` hệ thống thay wrapper |
| **Spring runtime** | Active profile, effective properties, bean conditions, module bootstrap scope | Local có env var bí mật, CI thiếu; một bên bật adapter khác |
| **Module contract** | `ApplicationModules` quét cùng application root và dependency graph | Local bỏ qua test kiến trúc, CI có chạy; hoặc ngược lại |
| **Behavior/event** | Test fixture, mock scope, event payload, transaction phase | Local mock collaborator, CI test provider thật nhưng cùng tên “module test” |
| **Infrastructure** | Database engine/schema/migration, broker protocol và version khi có cam kết liên quan | Local H2, CI PostgreSQL cho cùng bài kiểm SQL |
| **Determinism** | Timezone/locale, charset, clock/ID, parallelism và thứ tự dữ liệu test | Test pass UTC nhưng fail giờ Việt Nam; reuse state giữa test |
| **Evidence** | Tập test bắt buộc được chạy và báo cáo | CI báo BUILD SUCCESSFUL dù test bị `@Disabled` hoặc filter chọn 0 test |

**Mục tiêu bài:** khóa những điều kiện có ảnh hưởng đến kết quả, viết Java/JUnit **quan sát effective configuration**, và để CI thất bại khi cấu hình ngoài mong đợi hoặc bài test bắt buộc không thực sự được thực thi.

### Acceptance criteria

| ID | Cần đảm bảo | Bằng chứng |
| --- | --- | --- |
| `PARITY-01` | JDK test là 21; Gradle đến từ wrapper của repository | Gradle toolchain, version report, assertion JUnit |
| `PARITY-02` | Local và CI cùng profile `test` và chính sách `orders` | `@ActiveProfiles` + assert `@ConfigurationProperties` thực tế |
| `PARITY-03` | Thiếu/sai config bị từ chối tại bootstrap | `ApplicationContextRunner` negative tests |
| `PARITY-04` | SQL integration thực sự dùng PostgreSQL 16 trong cả hai môi trường | `@Testcontainers` + JDBC assertion |
| `PARITY-05` | Architecture và module contract không bị bỏ qua | `ApplicationModules.verify()`, `PublishedEvents`, JUnit XML evidence |
| `PARITY-06` | Thay đổi cấu hình gây drift phải làm gate đỏ | Các negative drills và required CI status check |

## 2. Khóa toolchain: JDK, Gradle wrapper và dependency versions

Khi local dùng Gradle hệ thống còn CI dùng wrapper, hoặc developer chạy JVM khác với test JVM, việc so sánh kết quả rất khó tin cậy. Hãy chọn **một nguồn chuẩn** trong repository:

1. Commit `gradlew`, `gradlew.bat` và wrapper JAR/properties theo chính sách repository.
2. Dùng `./gradlew` trên Unix/macOS và `gradlew.bat` trên Windows, **không trộn với lệnh `gradle` đã cài riêng**.
3. Chỉ rõ Java toolchain cho source và test.
4. Quản lý Spring Boot/Spring Modulith versions bằng BOM/dependency management tương thích; cân nhắc dependency locking và checksum verification nếu tổ chức áp dụng.
5. Trong CI, ghi lại JDK/Gradle versions để đối chiếu với local.

Ví dụ **`build.gradle` (Groovy DSL, trích đoạn)**:

```groovy
// Giả định dự án đã áp dụng Java/Spring Boot plugins
// và có Spring Boot + Spring Modulith BOM tương thích.

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    // Các giá trị này đi vào test JVM,
    // không phụ thuộc timezone/locale mặc định của runner.
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'user.language', 'en'
    systemProperty 'user.country', 'US'
}

dependencies {
    implementation(
        'org.springframework.modulith:spring-modulith-starter-core')
    implementation(
        'org.springframework.boot:spring-boot-starter-validation')

    testImplementation(
        'org.springframework.boot:spring-boot-starter-test')
    testImplementation(
        'org.springframework.modulith:spring-modulith-starter-test')
}
```

Trên CLI, developer kiểm tra:

```bash
java -version
./gradlew --version
./gradlew --no-daemon --console=plain test
```

`java -version` hiển thị Java của shell, **có thể khác Java của Gradle test toolchain**. Do đó vẫn cần assertion trong test JVM ở phần 4. Với Java toolchain, Gradle có thể dùng JDK 21 được tìm thấy hoặc tải theo cấu hình toolchain resolver; yêu cầu học thuật là **test thực sự chạy trên JDK 21**, không buộc mọi máy có cùng đường dẫn `JAVA_HOME`.

### Dependency drift dù JDK đã giống

Hai lần chạy Gradle cũng có thể khác vì dynamic version như `1.+`, SNAPSHOT/mốc thay đổi hoặc BOM khác nhau. Khi điều tra, dùng:

```bash
./gradlew dependencies --configuration testRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-modulith \
  --configuration testRuntimeClasspath
```

Commit version catalog/lockfiles và wrapper metadata nếu dự án sử dụng chúng. Không tự chạy `--refresh-dependencies` trên một bên rồi so với bên còn lại như thể cùng điều kiện. Nếu phụ thuộc cần cập nhật, cập nhật **trong PR có kiểm thử**, thay vì để hai môi trường resolve khác nhau một cách ngầm định.

### Không đồng nhất runtime parity với tính bất biến tuyệt đối

CI có thể dùng `temurin 21` còn máy phát triển dùng một vendor JDK 21 khác; về nhiều contract Java, điều đó có thể đủ tương thích, nhưng nếu dự án dùng native library, TLS provider hoặc GC-specific behavior thì cần ghi/ghim vendor trong chính sách. Công khai **tập điều kiện buộc phải tương đương**, không chỉ nói “hai bên dùng Java”.

## 3. Một nguồn test profile và quy tắc precedence rõ ràng

Để tránh “máy A có property trong environment, máy B không có”, đưa các **giá trị test không nhạy cảm** vào cùng repository.

Ví dụ `src/test/resources/application-test.yml`:

```yaml
shop:
  orders:
    currency: VND
    reservation-ttl: 15m
    max-attempts: 3
  notifications:
    external-enabled: false
```

Đây là **mẫu cấu hình trong bài**, không phải file được tạo bởi nhiệm vụ. Local và CI dùng chính file test versioned theo commit. Những giá trị như currency, TTL và feature flag phải được test assertion kiểm tra để phát hiện environment variable override.

Trong Spring Test:

```java
@org.springframework.modulith.test.ApplicationModuleTest
@org.springframework.test.context.ActiveProfiles("test")
class OrdersConfigurationParityTest {
    // Assertions xuất hiện ở mục 4.
}
```

`@ActiveProfiles("test")` giúp test chọn profile có chủ đích, không phụ thuộc việc developer đã bật `dev` trong IDE. Tuy vậy, profile **không khóa mọi property**: environment variables, system properties, `@TestPropertySource` và `@DynamicPropertySource` có thể ghi đè tùy ưu tiên của Spring Boot/TestContext.

Ví dụ environment override thường được bind theo relaxed naming:

```bash
# PHẢN VÍ DỤ: nếu test mong VND, override này tạo drift.
export SHOP_ORDERS_CURRENCY=USD
./gradlew test
```

Vì thế **chỉ có `application-test.yml` chưa đủ**. Test phải đọc **giá trị hiệu lực sau khi resolve/bind**, không chỉ so sánh nội dung YAML trong Git.

### Bảng nguồn cấu hình nên dùng

| Loại | Nguồn đề xuất | Cách bảo vệ |
| --- | --- | --- |
| Rule nghiệp vụ dùng trong test | `application-test.yml` versioned | Assert exact effective values |
| Secrets cho integration | CI secrets/local secret store, never commit | Test presence/ability to connect, không log giá trị |
| JDBC URL do Testcontainers tạo | `@DynamicPropertySource` | Assert dialect/version/schema thật |
| Override cho một scenario riêng | `@TestPropertySource` ở **test cụ thể** | Không áp dụng tràn lan lên smoke parity test |
| Feature flag của production | Deployment config riêng | Smoke test hoặc validation gate trước rollout |
| Local IDE setting | IDE run configuration | Phải không lén thay kỳ vọng của required tests |

**Một lỗi thường thấy:** `@TestPropertySource(properties = "shop.orders.currency=VND")` được đặt ngay trong “parity test”. Assertion sẽ luôn thấy VND dù `application-test.yml` hoặc environment lệch; test đã **che mất nguồn cấu hình mà nó định kiểm**. Hãy dùng `@TestPropertySource` cho scenario cần override, còn test parity chính đọc profile chung không override key nghiệp vụ.

## 4. JUnit module test quan sát effective configuration và hành vi thật

Bài ví dụ có hai application modules: `catalog` công bố API giá, `orders` dùng API đó và config riêng.

```text
com.example.shop/
├── ShopApplication.java
├── catalog/
│   ├── CatalogPrices.java
│   └── internal/StaticCatalogPrices.java
└── orders/
    ├── package-info.java
    ├── QuotePrepared.java
    ├── OrderQuoteService.java
    └── internal/
        ├── OrdersSettings.java
        └── OrdersConfiguration.java

src/test/java/com/example/shop/
├── ModuleArchitectureTest.java
└── orders/
    ├── OrdersConfigurationParityTest.java
    └── OrdersSettingsValidationTest.java
```

Root application và public API:

```java
// src/main/java/com/example/shop/ShopApplication.java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/shop/catalog/CatalogPrices.java
package com.example.shop.catalog;

public interface CatalogPrices {
    long priceMinor(String sku, String currency);
}
```

Một provider implementation tối thiểu, để full context có thể tạo được khi integration test không dùng mock:

```java
// src/main/java/com/example/shop/catalog/internal/StaticCatalogPrices.java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.CatalogPrices;
import org.springframework.stereotype.Service;

@Service
class StaticCatalogPrices implements CatalogPrices {

    @Override
    public long priceMinor(String sku, String currency) {
        if ("SKU-1".equals(sku) && "VND".equals(currency)) {
            return 125_000L;
        }
        throw new IllegalArgumentException(
            "Unsupported SKU or currency");
    }
}
```

Cấu hình lõi thuộc riêng module `orders`:

```java
// src/main/java/com/example/shop/orders/internal/OrdersSettings.java
package com.example.shop.orders.internal;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.orders")
public record OrdersSettings(
    @NotBlank String currency,
    @NotNull Duration reservationTtl,
    @Min(1) @Max(5) int maxAttempts
) {
    @AssertTrue(message = "reservationTtl must be positive")
    public boolean isReservationTtlPositive() {
        return reservationTtl != null
            && reservationTtl.compareTo(Duration.ZERO) > 0;
    }
}
```

```java
// src/main/java/com/example/shop/orders/internal/OrdersConfiguration.java
package com.example.shop.orders.internal;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(OrdersSettings.class)
class OrdersConfiguration {
}
```

`OrdersSettings` thuộc package internal nên module khác không tự lấy nó làm contract. Registration bằng `@EnableConfigurationProperties` cần nằm trong phạm vi scan của module test. `@Validated` cần Jakarta Bean Validation provider; dependency validation đã được khai báo ở mục 2.

Định nghĩa event/kết quả và service:

```java
// src/main/java/com/example/shop/orders/QuotePrepared.java
package com.example.shop.orders;

import java.time.Duration;

public record QuotePrepared(
    String orderId,
    String currency,
    long amountMinor,
    Duration reservationTtl
) {
}
```

```java
// src/main/java/com/example/shop/orders/OrderQuoteService.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogPrices;
import com.example.shop.orders.internal.OrdersSettings;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {

    private final CatalogPrices catalog;
    private final OrdersSettings settings;
    private final ApplicationEventPublisher events;

    public OrderQuoteService(
            CatalogPrices catalog,
            OrdersSettings settings,
            ApplicationEventPublisher events) {
        this.catalog = catalog;
        this.settings = settings;
        this.events = events;
    }

    public QuotePrepared prepare(String orderId, String sku) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid orderId/sku");
        }

        long amount = catalog.priceMinor(
            sku, settings.currency());

        if (amount <= 0) {
            throw new IllegalStateException(
                "Catalog price must be positive");
        }

        var event = new QuotePrepared(
            orderId, settings.currency(),
            amount, settings.reservationTtl());

        events.publishEvent(event);
        return event;
    }
}
```

Giới hạn phụ thuộc:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.example.shop.orders;
```

### Test đúng mục tiêu: giá trị hiệu lực + bean + sự kiện

```java
// src/test/java/com/example/shop/orders/
// OrdersConfigurationParityTest.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogPrices;
import com.example.shop.orders.internal.OrdersSettings;
import java.time.Duration;
import java.time.ZoneId;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@ApplicationModuleTest
@ActiveProfiles("test")
class OrdersConfigurationParityTest {

    @Autowired
    Environment environment;

    @Autowired
    OrdersSettings settings;

    @Autowired
    OrderQuoteService orders;

    @MockitoBean
    CatalogPrices catalog;

    @Test
    void testProfileAndEffectivePolicyAreIdentical(
            PublishedEvents events) {

        assertThat(environment.getActiveProfiles())
            .containsExactly("test");

        assertThat(settings.currency()).isEqualTo("VND");
        assertThat(settings.reservationTtl())
            .isEqualTo(Duration.ofMinutes(15));
        assertThat(settings.maxAttempts()).isEqualTo(3);

        // Assertions nằm trong test JVM, không chỉ java -version
        // ở shell của developer.
        assertThat(Runtime.version().feature()).isEqualTo(21);
        assertThat(ZoneId.systemDefault().getId())
            .isEqualTo("UTC");
        assertThat(Locale.getDefault()).isEqualTo(Locale.US);

        given(catalog.priceMinor("SKU-1", "VND"))
            .willReturn(125_000L);

        QuotePrepared result =
            orders.prepare("ORD-1", "SKU-1");

        assertThat(result).isEqualTo(new QuotePrepared(
            "ORD-1", "VND", 125_000L,
            Duration.ofMinutes(15)));

        assertThat(events.ofType(QuotePrepared.class))
            .singleElement()
            .satisfies(event ->
                assertThat(event).isEqualTo(result));
    }
}
```

Bài test chứng minh:

- Cùng test profile `test` và các giá trị `@ConfigurationProperties` **đã bind**; một environment variable đổi currency có thể khiến assertion fail.
- Test JVM thật là Java 21, timezone/locale tuân quy ước.
- Service `orders` thật chạy với property hiệu lực và public `CatalogPrices` port được mock có chủ đích ở `STANDALONE`.
- `PublishedEvents` ghi nhận đúng domain event; **không** suy Kafka/broker đã nhận.

**Version caveat:** `@MockitoBean` được cung cấp từ Spring Framework 6.2+, cần Boot/Spring Modulith phù hợp. Stack cũ có thể dùng `@MockBean` tương ứng. Test không nhất thiết chứng minh mọi bean trong full production context hoạt động; đó là mục đích integration/smoke test riêng.

## 5. Negative configuration test và cách phát hiện override từ máy developer

Một `@ApplicationModuleTest` với property cố ý sai thường chết ngay lúc khởi tạo context, trước khi JUnit method chạy. Để biến quy tắc **thiếu/sai cấu hình phải fail-fast** thành assertion rõ, dùng `ApplicationContextRunner` của Spring Boot.

```java
// src/test/java/com/example/shop/orders/
// OrdersSettingsValidationTest.java
package com.example.shop.orders;

import com.example.shop.orders.internal.OrdersSettings;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OrdersSettingsValidationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PropertiesOnly.class);

    @Test
    void completePolicyBindsSuccessfully() {
        runner.withPropertyValues(
            "shop.orders.currency=VND",
            "shop.orders.reservation-ttl=15m",
            "shop.orders.max-attempts=3"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();

            OrdersSettings policy =
                context.getBean(OrdersSettings.class);

            assertThat(policy.currency()).isEqualTo("VND");
            assertThat(policy.reservationTtl())
                .isEqualTo(java.time.Duration.ofMinutes(15));
        });
    }

    @Test
    void blankCurrencyIsRejected() {
        runner.withPropertyValues(
            "shop.orders.currency=",
            "shop.orders.reservation-ttl=15m",
            "shop.orders.max-attempts=3"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void zeroTtlIsRejected() {
        runner.withPropertyValues(
            "shop.orders.currency=VND",
            "shop.orders.reservation-ttl=0s",
            "shop.orders.max-attempts=3"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void invalidAttemptBudgetIsRejected() {
        runner.withPropertyValues(
            "shop.orders.currency=VND",
            "shop.orders.reservation-ttl=15m",
            "shop.orders.max-attempts=0"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(OrdersSettings.class)
    static class PropertiesOnly {
    }
}
```

**Vì sao dùng giá trị sai tường minh ở negative tests?** Một “missing property test” chỉ bỏ key ra khỏi `withPropertyValues(...)` có thể bị environment variable trên laptop vô tình cung cấp giá trị. Đặt `currency=` hoặc `reservation-ttl=0s` giúp scenario xấu không phụ thuộc việc máy đã có biến bên ngoài. Mặt khác, `OrdersConfigurationParityTest` không override key để **phát hiện** biến ngoài vô tình thay config chung.

Phạm vi kiểm chứng:

| Test | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `OrdersSettingsValidationTest` | Bind/validation và fail-fast | Component scan/service wiring của module |
| `OrdersConfigurationParityTest` | Profile và effective values trong module context | SQL dialect, broker, full production configuration |
| Full-context smoke test | Bean conditions/adapter của môi trường mục tiêu | Từng trường hợp network/transaction failure |
| Integration Testcontainers | DB/broker thật theo contract | Mọi production-specific setting |

**Đừng “sửa” CI thiếu property bằng cách mock `OrdersSettings` hoặc thêm default giả.** Sửa nguồn cấu hình/validation, giữ test phủ cả good và bad scenarios. Nếu project cần fail khi *key thực sự vắng mặt*, thêm một negative test với environment hoàn toàn cô lập và loại bỏ mọi property source bên ngoài, thay vì tin rằng process environment luôn trống.

## 6. Cùng database semantics: Testcontainers thay cho giả định H2 tương đương PostgreSQL

Một ứng dụng có thể dùng H2 ở module tests để chạy nhanh, nhưng test có H2 **không thể tự chứng minh** PostgreSQL SQL dialect, isolation, unique constraints hay migration production sẽ đúng. Khi contract liên quan DB, local và CI nên chạy **cùng loại database được kiểm chứng**.

Ví dụ PostgreSQL integration test, dùng `@Testcontainers` với image tag cố định và `@DynamicPropertySource` để inject JDBC URL/credentials động.

```java
// src/test/java/com/example/shop/DatabaseParityTest.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@ActiveProfiles("test")
class DatabaseParityTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username", postgres::getUsername);
        registry.add(
            "spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void databaseEngineIsPostgres16() {
        String version = jdbc.queryForObject(
            "select version()", String.class);

        assertThat(version)
            .startsWith("PostgreSQL 16.");
    }
}
```

**Điều kiện của ví dụ:** test runtime có Docker/Testcontainers, JDBC starter và PostgreSQL driver. `@DynamicPropertySource` cung cấp các thuộc tính thực của container. Không in JDBC password lên log; không sử dụng secret production. **Local thiếu Docker phải nhận lỗi điều kiện chạy**, không đánh dấu test `@Disabled` để giả vờ tương thích.

Mẫu dependency bổ sung cho project dùng BOM tương thích:

```groovy
dependencies {
    // Chỉ nếu ứng dụng/các test thực sự dùng JDBC.
    implementation(
        'org.springframework.boot:spring-boot-starter-jdbc')

    testImplementation('org.testcontainers:junit-jupiter')
    testImplementation('org.testcontainers:postgresql')
    testRuntimeOnly('org.postgresql:postgresql')

    // Nếu muốn embedded DB cho các module tests
    // không kiểm SQL dialect thì ghi rõ phạm vi.
    testRuntimeOnly('com.h2database:h2')
}
```

Nếu có H2 trên test classpath, Spring Boot có thể tự tạo embedded DataSource cho module test không cung cấp JDBC URL; điều đó **không vi phạm** mục tiêu cô lập module test, miễn test không tự nhận đã kiểm chứng PostgreSQL. Trong `DatabaseParityTest`, `@DynamicPropertySource` ghi đè URL/credentials để dùng PostgreSQL. Nếu app thật dùng migration Flyway/Liquibase, bật migration trong integration profile và kiểm tra schema sau migration bằng repository/JDBC assertions phù hợp.

**Test `select version()` mới chứng minh engine/version**, chưa chứng minh DDL, constraint, transaction hay event publication registry. Để bảo vệ những hợp đồng đó, thêm test đọc/ghi thật, flush/commit/rollback và migration từ dataset cũ. Nếu production dùng PostgreSQL 16 nhưng image `postgres:16.4` ở đây có patch level khác deployment, ghi rõ mức parity là **major version**; có thể pin image digest để tăng độ tái lập khi cần.

### Đừng nhầm `@ApplicationModuleTest` với môi trường tích hợp thật

`@ApplicationModuleTest(STANDALONE)` có thể mock API ngoài module; nó là đúng khi kiểm service riêng lẻ. `DatabaseParityTest` cố ý dùng `@SpringBootTest` vì phải nạp JDBC datasource thực. Chọn đúng tầng, **không biến mọi module test thành full context + container** làm CI chậm và dễ phát sinh flaky.

## 7. Timezone, locale, clock, parallel tests và khác biệt hệ điều hành

Hai máy khác OS vẫn có thể chạy cùng test contract nếu loại bỏ những phụ thuộc ngẫu nhiên vào môi trường.

### 7.1. Khóa timezone/locale ở JVM thực thi test

Ở mục 2, `tasks.withType(Test)` đặt:

```groovy
systemProperty 'user.timezone', 'UTC'
systemProperty 'user.language', 'en'
systemProperty 'user.country', 'US'
```

Và `OrdersConfigurationParityTest` assert `ZoneId.systemDefault().getId() == "UTC"`, `Locale.getDefault() == Locale.US`. Điều này bảo vệ các kiểm thử dùng định dạng ngày, currency formatting hoặc case conversion.

**Nhưng:** test không nên phụ thuộc `LocalDateTime.now()` để tạo business timestamp nếu cần deterministic outcome. Ưu tiên inject `Clock` vào service, với test clock cố định:

```java
// Java/JUnit thuần, dùng cho service có Clock dependency.
java.time.Clock fixed = java.time.Clock.fixed(
    java.time.Instant.parse("2026-01-01T00:00:00Z"),
    java.time.ZoneOffset.UTC);

assertThat(java.time.Instant.now(fixed))
    .isEqualTo(
        java.time.Instant.parse("2026-01-01T00:00:00Z"));
```

Đây là **fragment**, không phải một clock đã được wire vào `OrderQuoteService` của ví dụ chính. Khi service thật phụ thuộc `Clock`, dùng `@TestConfiguration`/bean override đúng phạm vi để đưa clock vào Spring context và assert event timestamps.

### 7.2. Không hardcode đường dẫn hoặc dấu xuống dòng

```java
// Ưu tiên giải pháp chạy được trên các hệ điều hành.
java.nio.file.Path path =
    java.nio.file.Path.of("build", "test-output", "result.json");
```

Tránh assert chuỗi path như `C:\\workspace\\...` trên Windows và `/home/runner/...` trên Linux. Với file text, chọn charset tường minh `StandardCharsets.UTF_8` thay vì dựa vào platform default; chuẩn hóa newline khi format không phải contract.

### 7.3. Parallelism và context cache

Một test có thể pass khi chạy riêng nhưng fail khi CI chạy song song vì cùng `orderId`, port, Kafka topic hoặc database row. Cần:

- Tạo test data ID duy nhất/fixture được cleanup sau test.
- Không lạm dụng static mutable state giữa module tests.
- Kiểm soát `maxParallelForks`/JUnit parallel execution có chủ đích; ghi cấu hình này khi so sánh CI/local.
- Với Testcontainers, để lifecycle rõ ràng, không tái sử dụng endpoint đã dừng khi Spring context còn cache.
- Nếu test listener async, chờ **điều kiện nghiệp vụ** bằng Awaitility/`Scenario` có timeout, không `Thread.sleep` cố định.
- Nếu test xử lý sự kiện **sau commit**, tạo commit/rollback thật; `PublishedEvents` không chứng minh transaction hoàn tất.

**Ranh giới:** CI có nhiều CPU hơn laptop không phải một lỗi parity. Thứ bắt buộc tương đương là **business assertions và các điều kiện test đã quy định**. Performance/reliability regression phải được đo riêng theo ngân sách nếu cần; không lấy timing biến động làm lý do xóa các architecture, event hoặc DB gates.

## 8. Gradle tasks: cùng câu lệnh, có bằng chứng từng test bắt buộc

Mục tiêu CI không chỉ chạy `./gradlew test` mà còn phải chứng minh **architecture contract** và **configuration parity contract** đã được chọn và thực thi. Dùng một task rõ ràng; database integration là task riêng để công khai yêu cầu Docker.

Ví dụ `build.gradle` Groovy DSL:

```groovy
tasks.register('parityContractTest', Test) {
    group = 'verification'
    description = 'Verify module boundaries and effective test config'

    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform()

    filter {
        includeTestsMatching(
            'com.example.shop.ModuleArchitectureTest')
        includeTestsMatching(
            'com.example.shop.orders.OrdersConfigurationParityTest')
        includeTestsMatching(
            'com.example.shop.orders.OrdersSettingsValidationTest')
        failOnNoMatchingTests = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

tasks.register('databaseParityTest', Test) {
    group = 'verification'
    description = 'Verify PostgreSQL integration via Testcontainers'

    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform()

    filter {
        includeTestsMatching(
            'com.example.shop.DatabaseParityTest')
        failOnNoMatchingTests = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

tasks.named('check') {
    dependsOn tasks.named('parityContractTest')
    dependsOn tasks.named('databaseParityTest')
}
```

Architecture test trong package root:

```java
// src/test/java/com/example/shop/ModuleArchitectureTest.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void boundariesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Chạy **giống nhau** ở CI và máy developer (trên Windows dùng wrapper `gradlew.bat`):

```bash
./gradlew --no-daemon --console=plain \
  parityContractTest databaseParityTest
```

Một số điểm cần xác minh:

- `parityContractTest` nạp các lớp contract tests trong source set `test`; không cần full Spring context chỉ để kiểm `ApplicationModules.verify()`.
- `databaseParityTest` chạy cùng `DatabaseParityTest` dùng PostgreSQL Testcontainers ở cả CI/local; cần Docker khả dụng.
- `check` phụ thuộc hai task, nhưng **lệnh `-x parityContractTest` hoặc task `enabled=false` vẫn có thể bỏ qua chúng**. Chính sách CI phải không sử dụng những đường tắt đó.
- `failOnNoMatchingTests=true` từ chối trường hợp **không match bất kỳ test nào**, **không** bảo đảm mọi class trong filter đều chạy khi các class khác vẫn match. CI cần kiểm report **từng class**.
- Vì các test cũng nằm trong source set `test` mặc định, `./gradlew test` có thể chạy lại chúng. Nếu suite lớn, có thể tổ chức source sets/test suites riêng mà vẫn giữ required gates.
- Task status `UP-TO-DATE`/`FROM-CACHE` không tự chứng minh test bị skip; kiểm report inputs/cache đúng, và chạy `--rerun-tasks` **chỉ khi điều tra** vì nó có thể làm build chậm thêm.

**Bài học về chi phí:** module parity tests tập trung properties và event; DB parity test dùng container và full Spring context. Tách task giúp dễ phân loại lỗi nhưng không đổi nội dung cam kết.

## 9. GitHub Actions: kiểm tra phiên bản, chạy gate và đọc JUnit XML

Một workflow CI dùng chính Gradle wrapper, Java 21 và cùng các task ở phần 8:

```yaml
# Ví dụ: .github/workflows/modulith-config-parity.yml
name: Modulith configuration parity

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  parity:
    name: Configuration parity gate
    runs-on: ubuntu-latest
    timeout-minutes: 35

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Record toolchain metadata
        shell: bash
        run: |
          mkdir -p evidence
          java -version 2> evidence/java-version.txt
          ./gradlew --version > evidence/gradle-version.txt

      - name: Run the same contract tasks as local
        run: >
          ./gradlew --no-daemon --console=plain
          parityContractTest databaseParityTest

      - name: Verify every required test actually ran
        shell: bash
        run: |
          for entry in \
            parityContractTest:com.example.shop.ModuleArchitectureTest \
            parityContractTest:com.example.shop.orders.OrdersConfigurationParityTest \
            parityContractTest:com.example.shop.orders.OrdersSettingsValidationTest \
            databaseParityTest:com.example.shop.DatabaseParityTest; do

            task="${entry%%:*}"
            klass="${entry#*:}"
            xml="build/test-results/$task/TEST-$klass.xml"

            test -s "$xml"
            grep -Eq 'tests="[1-9][0-9]*"' "$xml"
            grep -q 'skipped="0"' "$xml"
            grep -q 'failures="0"' "$xml"
            grep -q 'errors="0"' "$xml"
          done

      - name: Keep reports for parity investigation
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: modulith-configuration-parity-evidence
          path: |
            evidence/
            build/test-results/parityContractTest/
            build/reports/tests/parityContractTest/
            build/test-results/databaseParityTest/
            build/reports/tests/databaseParityTest/
          if-no-files-found: warn
          retention-days: 7
```

**Điều workflow thực sự bảo vệ:**

1. Setup Java 21 và chạy wrapper của commit; test còn assert `Runtime.version().feature()`.
2. Test profile `test` và effective settings có cùng kỳ vọng trên local/CI.
3. PostgreSQL test không bị thay bằng H2 khi chạy tại CI.
4. Nếu một class bị đổi tên, `@Disabled` hoặc filter không chọn đúng, JUnit evidence step thất bại.
5. Nếu runtime Testcontainers không có Docker, test FAIL: đó là **thiếu precondition integration**, không phải test PASS.
6. Artifact chứa phiên bản Java/Gradle và JUnit reports để đối chiếu; không chứa toàn bộ environment hoặc secrets.
7. Workflow không có `continue-on-error: true` ở quality gate, cũng không dùng `-x test`.

**Giới hạn thực tế:** đoạn `grep` giả định file JUnit XML theo layout Gradle thông dụng, phù hợp với các class riêng trong ví dụ. Với multi-project/custom report format, dùng XML parser chuẩn để đếm tests/skipped/failures/errors. `failOnNoMatchingTests` không thay thế per-class evidence. Và **job YAML không tự thành required check**: repository owner phải đánh dấu **Configuration parity gate** là required trong branch ruleset/protection phù hợp, không cho merge khi job fail/skip.

### Cẩn trọng khi đổi cấu hình production

Test profile có thể hoàn toàn tương thích local/CI mà production thiếu secrets, Kafka topic hoặc migration. Đây là **một hợp đồng khác**. Nếu service cần external adapter trong production, thêm smoke/integration gate với bộ config deployment đã phê duyệt; không mở broker thật cho mọi module test chỉ để tạo cảm giác parity.

## 10. Negative drills, điều tra lệch môi trường và Definition of Done

Muốn biết parity gate có “răng”, cần thử **làm môi trường lệch có chủ đích** trên branch hoặc local session thử nghiệm, rồi revert.

### Negative drills

| Thử nghiệm | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| **N1: Property override** | Đặt `SHOP_ORDERS_CURRENCY=USD` trước khi chạy `parityContractTest` | `OrdersConfigurationParityTest` FAIL vì effective currency không còn VND |
| **N2: Invalid setting** | Đặt `shop.orders.reservation-ttl=0s` trong scenario validation | Negative `ApplicationContextRunner` chứng minh bootstrap fail |
| **N3: Sai timezone** | Tạm đổi `user.timezone` của test JVM sang `Asia/Ho_Chi_Minh` | Runtime parity assertion FAIL |
| **N4: JDK khác** | Tạm chạy test bằng toolchain không phải 21 nếu cấu hình cho phép | JUnit assertion `Runtime.version().feature()` FAIL |
| **N5: Mất test class** | Đổi tên `OrdersConfigurationParityTest` nhưng không đổi Gradle filter/CI evidence | Thiếu file XML của class, gate FAIL |
| **N6: Disabled test** | Thêm `@Disabled` vào một required class/test | `skipped>0`; evidence step FAIL |
| **N7: Không có Docker** | Chạy `databaseParityTest` trên môi trường không hỗ trợ container | Test FAIL với precondition; không im lặng skip |
| **N8: Dùng DB khác** | Tạm trỏ integration datasource vào H2 | PostgreSQL version assertion FAIL |
| **N9: Dependency sai** | `orders` import `catalog.internal` hoặc tạo cycle | `ModuleArchitectureTest` FAIL |
| **N10: Event payload sai** | Service publish `QuotePrepared` với amount khác quote trả về | `PublishedEvents` assertion FAIL |

**Để thử N1 trên Unix/macOS:**

```bash
SHOP_ORDERS_CURRENCY=USD \
  ./gradlew --no-daemon parityContractTest
```

**Trên PowerShell:**

```powershell
$env:SHOP_ORDERS_CURRENCY = 'USD'
.\gradlew.bat --no-daemon parityContractTest
Remove-Item Env:SHOP_ORDERS_CURRENCY
```

Trong hai trường hợp, test fail **là kết quả mong đợi của negative drill**, không phải lý do đổi expectation sang USD hoặc bỏ `@Validated`. Cần chắc chắn biến được dọn sau thí nghiệm.

### Quy trình triage khi local PASS nhưng CI FAIL

1. **Xác nhận cùng commit và cùng test tasks.** `./gradlew test` và `./gradlew parityContractTest databaseParityTest` không phải cùng tập test.
2. **Đọc lỗi đầu tiên.** Compile/classpath lỗi, property bind lỗi, missing bean, failed assertion, Docker failure và timeout cần được phân loại khác nhau.
3. **So phiên bản.** JDK của test JVM, Gradle wrapper/distribution, Boot/Modulith BOM và resolved dependencies.
4. **Kiểm effective config**, profile và property sources. Không xuất secret value ra log; kiểm chỉ key và giá trị không nhạy cảm.
5. **Kiểm module scope**: `@ApplicationModuleTest(STANDALONE)` có mock public collaborator đúng hay một bên vô tình chạy full `@SpringBootTest`?
6. **Kiểm hạ tầng**: image PostgreSQL, DB URL, migration/schema, Docker availability, network và permission.
7. **Kiểm tính quyết định**: UTC/locale, file paths, encoding, test IDs, parallelism, context cache và Testcontainers lifecycle.
8. **Tái hiện bằng cùng wrapper/command/profile**, không sửa test bằng `@Disabled` hoặc môi trường giả.
9. **Giữ bằng chứng**: JUnit XML, stack trace, Gradle/JDK metadata, container logs đã lọc secret.
10. **Sửa một nguồn cấu hình/versioned contract** rồi chạy lại trên local và CI.

### Checklist trước khi coi parity gate hoàn thành

- [ ] Gradle wrapper và version management có trong repository.
- [ ] Java toolchain cho test được cố định và có JUnit assertion.
- [ ] Local và CI dùng cùng test tasks, không bỏ qua architecture/module tests.
- [ ] Shared `application-test.yml` có trong source control, chỉ chứa dữ liệu test an toàn.
- [ ] `@ActiveProfiles("test")` được dùng có chủ đích; effective properties được assert.
- [ ] Không đặt `@TestPropertySource` ngay trên parity smoke test để che sai lệch nguồn config.
- [ ] Missing/invalid settings có `ApplicationContextRunner` tests.
- [ ] `@ApplicationModuleTest` kiểm service thật, chỉ mock collaborator ngoài module.
- [ ] `ApplicationModules.verify()` chạy như quality gate độc lập.
- [ ] `PublishedEvents` kiểm payload/quantity, không suy Kafka/transaction commit.
- [ ] DB integration ở local và CI dùng PostgreSQL 16 Testcontainers thay vì khẳng định H2 tương đương.
- [ ] Docker/credentials/datasource prerequisites được công bố; không silently skip.
- [ ] JVM timezone/locale và clock policy rõ; file paths/encoding portable.
- [ ] Test state/parallelism/context cache không gây kết quả lệch giữa môi trường.
- [ ] Gradle filter và per-class JUnit XML verification chống “0 test PASS”.
- [ ] Job **Configuration parity gate** là required status check; failure artifacts đầy đủ.
- [ ] Negative drills N1, N5, N6 và N7 đã được thực hiện ở môi trường thử nghiệm rồi revert.
- [ ] Không ghi production secrets/PII vào YAML hoặc CI artifacts.
- [ ] Với production-specific adapter, có smoke/integration gate riêng; không hiểu test parity là bảo chứng mọi cấu hình production.

### Definition of Done

Một quality gate bảo đảm **CI và máy phát triển dùng cấu hình tương thích** đạt yêu cầu khi:

1. **Có nguồn chuẩn:** toolchain, wrapper/BOM và test profile được quản lý cùng commit.
2. **Có kiểm chứng runtime:** JUnit assert phiên bản Java, timezone/locale và effective configuration thực.
3. **Có validation phản chứng:** giá trị thiếu/sai phải fail trước khi đi vào nghiệp vụ.
4. **Có hạ tầng đúng tầng:** module tests có thể cô lập; DB integration dùng cùng engine/schema target.
5. **Không có silent skip:** JUnit XML của từng test bắt buộc được kiểm và job là required check.
6. **Có phép thử drift:** chủ động đổi env/profile/toolchain hoặc bỏ test khiến quality gate đỏ.

**Ghi nhớ:** “tương thích giữa CI và local” không phải sao chép mọi biến môi trường của laptop lên runner. Hãy **chốt toolchain và profile, kiểm tra effective configuration bằng Java/JUnit, dùng infrastructure thật khi hợp đồng đòi hỏi, và từ chối các test bị skip hoặc chạy sai phạm vi**. Khi đó `ApplicationModules.verify()`, `@ApplicationModuleTest`, `PublishedEvents` và các database/integration gates mới thực sự có cùng ý nghĩa trên máy phát triển và CI.
