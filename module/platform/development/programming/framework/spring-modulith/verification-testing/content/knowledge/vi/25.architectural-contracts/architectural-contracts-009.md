# Hợp đồng cấu hình cần có để bootstrap module

## 1. Khi kiến trúc đúng nhưng module không khởi động được

Một application module Spring Modulith có thể **đúng về quan hệ phụ thuộc** nhưng vẫn không tạo được Spring `ApplicationContext`. Ví dụ module `orders` cần cấu hình tiền tệ, thời hạn giữ báo giá và số lần thử tối đa. Test của developer xanh vì máy có sẵn environment variable; CI thiếu biến đó và gặp `BeanCreationException` trước khi logic nghiệp vụ được thực thi.

Ngược lại, module test có thể xanh vì đang mock mọi collaborator, trong khi production bật Kafka adapter nhưng thiếu topic hoặc producer. Vì vậy, trong chương **Architectural contracts** của `SPRING_MODULITH_VERIFICATION_TESTING`, cần coi **cấu hình để bootstrap một module** là một hợp đồng có thể kiểm chứng, không phải tập hợp các giá trị “miễn sao chạy được”.

Hợp đồng này trả lời:

- **Property nào bắt buộc?** Tên, type, unit, miền hợp lệ, default và nguồn cấp giá trị.
- **Bean nào phải có?** Bean nội bộ module, API từ module khác hay bean hạ tầng có điều kiện?
- **Khi nào adapter phải được bật?** Profile, feature flag và những dependency cần lúc bật.
- **Thiếu/sai cấu hình gây ra điều gì?** Fail-fast tại bootstrap hay fallback được phê duyệt?
- **Test nào chứng minh hợp đồng?** `ApplicationContextRunner`, `@ApplicationModuleTest`, architecture verification và integration test.

**Nguyên tắc:** “context load thành công” là điều kiện cần nhưng chưa đủ. Context phải nạp **đúng bean, đúng giá trị và đúng chế độ hoạt động** cho tình huống mà test tuyên bố kiểm chứng.

## 2. Bốn loại yêu cầu bootstrap khác nhau

| Hợp đồng | Ví dụ | Phép kiểm chứng phù hợp |
| --- | --- | --- |
| **Property binding** | `shop.checkout.reservation-ttl=15m` | Bind ra `Duration` và validate lớn hơn 0 |
| **Bean wiring** | `CheckoutService` cần `CheckoutProperties` và `CatalogPrices` | Module context tạo service và collaborator đúng |
| **Conditional activation** | `shop.order-events.enabled` | Chỉ tạo Kafka adapter khi bật; thiếu topic thì fail |
| **External infrastructure** | Kafka, DataSource, HTTP client | Integration/smoke test với dependency thực |

Phân biệt hai nhóm property:

1. **Bắt buộc với lõi module:** phải có ở mọi context dùng service tương ứng.
2. **Bắt buộc có điều kiện:** chỉ yêu cầu nếu profile hoặc feature flag bật một adapter.

Không bắt module test `STANDALONE` kết nối broker nếu chỉ kiểm tra service nội bộ. Nhưng nếu production bắt buộc externalize event, phải có **production-like gate** bảo đảm adapter không bị tắt ngầm.

## 3. Ví dụ xuyên suốt: module orders cần cấu hình và API catalog

```text
com.example.shop/
├── ShopApplication.java
├── catalog/
│   └── CatalogPrices.java                 // API công khai
└── orders/
    ├── CheckoutService.java
    ├── CheckoutPlan.java
    ├── CheckoutPlanned.java
    └── internal/
        ├── CheckoutProperties.java
        ├── ExternalEventProperties.java
        ├── OrdersBootstrapConfiguration.java
        └── KafkaOrderEventAdapter.java
```

Theo cách nhận diện application module mặc định thường gặp, `orders` và `catalog` là các module; `orders.internal` thuộc chính `orders`. Ví dụ dùng Java 17+, Spring Boot 3.x/Modulith tương thích và Jakarta Bean Validation. Cần điều chỉnh import/annotation theo version thực tế của dự án.

Ứng dụng gốc:

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

API của provider `catalog`:

```java
// src/main/java/com/example/shop/catalog/CatalogPrices.java
package com.example.shop.catalog;

public interface CatalogPrices {
    long priceMinor(String sku, String currency);
}
```

Module `orders` chỉ biết interface này, không import implementation `catalog.internal`.

## 4. Property contract của lõi module bằng `@ConfigurationProperties`

Thay vì nhiều `@Value` nằm rải rác trong service, gom các giá trị có cùng ownership vào một record và validate khi bind.

```java
// src/main/java/com/example/shop/orders/internal/CheckoutProperties.java
package com.example.shop.orders.internal;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.checkout")
public record CheckoutProperties(
    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    String currency,

    @NotNull
    Duration reservationTtl,

    @Min(1)
    @Max(5)
    int maxAttempts
) {
    @AssertTrue(message = "reservationTtl must be positive")
    public boolean isReservationTtlPositive() {
        return reservationTtl != null
            && reservationTtl.compareTo(Duration.ZERO) > 0;
    }
}
```

Đây là hợp đồng **bắt buộc với module checkout**:

| Property | Type | Giá trị ví dụ | Điều kiện hợp lệ |
| --- | --- | --- | --- |
| `shop.checkout.currency` | String | `VND` | Không rỗng; ba chữ hoa |
| `shop.checkout.reservation-ttl` | `Duration` | `15m` | Có giá trị và lớn hơn 0 |
| `shop.checkout.max-attempts` | int | `3` | Từ 1 đến 5 |

**Tại sao fail-fast quan trọng?** Thiếu `reservationTtl` không được phép âm thầm truyền `null` tới service. `maxAttempts` bị thiếu có thể bind thành `0` với primitive `int`, nhưng `@Min(1)` phải từ chối nó trong lúc bootstrap.

Lưu ý:

- `@Validated` cần một Bean Validation provider trên classpath, thông thường từ `spring-boot-starter-validation`. Thiếu dependency này có thể làm validation không vận hành như kỳ vọng.
- `@Pattern("[A-Z]{3}")` chỉ kiểm tra **format**, không chứng minh mã tiền tệ được nghiệp vụ hỗ trợ. Ví dụ dùng `VND`; ứng dụng thật cần quy định mã/đơn vị tiền riêng.
- `Duration` nên được cấu hình có đơn vị tường minh như `15m` hoặc `PT15M` để tránh hiểu sai milliseconds/seconds.
- Record giữ cấu hình bất biến theo lifecycle của bean, không phải “tự động cập nhật theo biến môi trường” giữa lúc ứng dụng chạy.

## 5. Property contract có điều kiện cho external adapter

Khi tính năng external event được tắt, module `orders` không cần Kafka. Khi bật, nó phải có topic.

```java
// src/main/java/com/example/shop/orders/internal/ExternalEventProperties.java
package com.example.shop.orders.internal;

import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.order-events")
public record ExternalEventProperties(
    boolean enabled,
    String topic
) {
    @AssertTrue(message = "topic is required when enabled")
    public boolean isTopicValidWhenEnabled() {
        return !enabled
            || (topic != null && !topic.isBlank());
    }
}
```

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không có `enabled` | Giá trị boolean mặc định `false` theo thiết kế ví dụ |
| `enabled=false`, không có `topic` | Property binding thành công |
| `enabled=true`, `topic` thiếu/blank | **Fail-fast** ở validation |
| `enabled=true`, `topic` hợp lệ | Property binding thành công; còn phải kiểm tra Kafka bean/broker |

Default `false` giúp module test lõi nhỏ và độc lập. **Nhưng** nếu event externalization là chức năng bắt buộc trong production, deployment phải ép `enabled=true` và CI phải kiểm tra trạng thái ấy; nếu không, “startup xanh” có thể đồng nghĩa adapter quan trọng bị tắt.

## 6. Đăng ký property beans trong đúng module

`@ConfigurationProperties` **không tự động trở thành bean trong mọi context** chỉ vì được gắn annotation. Cần cơ chế như `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` được áp dụng phù hợp.

```java
// src/main/java/com/example/shop/orders/internal/OrdersBootstrapConfiguration.java
package com.example.shop.orders.internal;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
    CheckoutProperties.class,
    ExternalEventProperties.class
})
class OrdersBootstrapConfiguration {
}
```

Configuration class ở package `orders.internal` là thành phần **thuộc module orders**, sẽ được component scan nhận diện khi module được bootstrap với cấu trúc package minh họa.

Đừng đồng thời dùng nhiều cơ chế đăng ký khiến một type config thành nhiều bean ngoài ý muốn. Ngược lại, nếu configuration class nằm ngoài phạm vi module test, service có thể thiếu bean `CheckoutProperties` dù toàn ứng dụng production vẫn quét thấy nó. Cần sửa **vị trí hoặc đăng ký cấu hình**, không mock properties bean để che lỗi.

### Bộ cấu hình hợp lệ khi tắt externalization

```yaml
shop:
  checkout:
    currency: VND
    reservation-ttl: 15m
    max-attempts: 3
  order-events:
    enabled: false
```

### Bộ cấu hình riêng khi bật externalization

```yaml
shop:
  order-events:
    enabled: true
    topic: shop.order-events.v1

spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Đây là **mẫu YAML**, không phải file đang được tạo. `KAFKA_BOOTSTRAP_SERVERS` được cung cấp từ environment/configuration deployment tương ứng. Không ghi secret production vào repository hoặc log effective config nhạy cảm.

## 7. Conditional bean: flag bật đúng adapter

Một adapter giả định dùng Spring Kafka:

```java
// src/main/java/com/example/shop/orders/internal/KafkaOrderEventAdapter.java
package com.example.shop.orders.internal;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "shop.order-events",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false)
class KafkaOrderEventAdapter {

    private final KafkaTemplate<String, String> kafka;
    private final ExternalEventProperties properties;

    KafkaOrderEventAdapter(
            KafkaTemplate<String, String> kafka,
            ExternalEventProperties properties) {
        this.kafka = kafka;
        this.properties = properties;
    }

    // Event mapper/listener/send thực tế cần kiểm thử riêng.
}
```

**Hợp đồng activation**:

- `enabled=false` → không có `KafkaOrderEventAdapter`.
- `enabled=true` + thiếu topic → validation của `ExternalEventProperties` phải fail.
- `enabled=true` + đủ topic nhưng thiếu `KafkaTemplate` → context phải fail vì bean collaborator bắt buộc thiếu.
- `enabled=true` + đủ cấu hình và bean → adapter có thể được tạo, **chưa chứng minh broker đang nhận message**.

`@ConditionalOnProperty` điều khiển bean registration, không thử gửi message. Kafka producer/template có thể được khởi tạo mà broker chưa reachable; cần broker integration test khi delivery là một cam kết nghiệp vụ.

## 8. Service thật dùng cấu hình đã bind

Hai record công khai của module `orders`:

```java
// src/main/java/com/example/shop/orders/CheckoutPlan.java
package com.example.shop.orders;

import java.time.Duration;

public record CheckoutPlan(
    String orderId,
    String currency,
    long amountMinor,
    Duration reservationTtl,
    int maxAttempts
) {
}
```

```java
// src/main/java/com/example/shop/orders/CheckoutPlanned.java
package com.example.shop.orders;

public record CheckoutPlanned(
    String orderId,
    String currency,
    long amountMinor
) {
}
```

Service:

```java
// src/main/java/com/example/shop/orders/CheckoutService.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogPrices;
import com.example.shop.orders.internal.CheckoutProperties;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final CatalogPrices catalog;
    private final CheckoutProperties configuration;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            CatalogPrices catalog,
            CheckoutProperties configuration,
            ApplicationEventPublisher events) {
        this.catalog = catalog;
        this.configuration = configuration;
        this.events = events;
    }

    public CheckoutPlan plan(String orderId, String sku) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid checkout input");
        }

        long amountMinor =
            catalog.priceMinor(sku, configuration.currency());

        if (amountMinor <= 0) {
            throw new IllegalStateException(
                "Catalog returned invalid price");
        }

        CheckoutPlan plan = new CheckoutPlan(
            orderId,
            configuration.currency(),
            amountMinor,
            configuration.reservationTtl(),
            configuration.maxAttempts());

        events.publishEvent(new CheckoutPlanned(
            orderId, plan.currency(), plan.amountMinor()));

        return plan;
    }
}
```

Cả ba property lõi đều ảnh hưởng kết quả. Test cần kiểm tra **giá trị service dùng**, không chỉ assert config bean tồn tại.

Ví dụ này không có JPA/transaction hoặc gửi Kafka thật: `CheckoutPlanned` là domain event được công bố trong JVM. Việc tạo context và ghi nhận `PublishedEvents` không tự chứng minh external delivery.

## 9. Module test kiểm chứng bootstrap với cấu hình hợp lệ

Với `@ApplicationModuleTest` ở package `orders`, dùng `@TestPropertySource` để không phụ thuộc biến môi trường trên máy developer. API `CatalogPrices` nằm ở module khác; trong `STANDALONE` cung cấp test double có chủ đích.

```java
// src/test/java/com/example/shop/orders/CheckoutModuleBootstrapTest.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogPrices;
import com.example.shop.orders.internal.CheckoutProperties;
import com.example.shop.orders.internal.ExternalEventProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@ApplicationModuleTest
@TestPropertySource(properties = {
    "shop.checkout.currency=VND",
    "shop.checkout.reservation-ttl=15m",
    "shop.checkout.max-attempts=3",
    "shop.order-events.enabled=false"
})
class CheckoutModuleBootstrapTest {

    @Autowired
    CheckoutProperties configuration;

    @Autowired
    ExternalEventProperties externalEvents;

    @Autowired
    CheckoutService checkout;

    @MockitoBean
    CatalogPrices catalog;

    @Test
    void bindsAndUsesModuleConfiguration(PublishedEvents events) {
        assertThat(configuration.currency()).isEqualTo("VND");
        assertThat(configuration.reservationTtl())
            .isEqualTo(java.time.Duration.ofMinutes(15));
        assertThat(configuration.maxAttempts()).isEqualTo(3);
        assertThat(externalEvents.enabled()).isFalse();

        given(catalog.priceMinor("SKU-1", "VND"))
            .willReturn(125000L);

        CheckoutPlan plan = checkout.plan("ORD-1", "SKU-1");

        assertThat(plan.currency()).isEqualTo("VND");
        assertThat(plan.reservationTtl())
            .isEqualTo(java.time.Duration.ofMinutes(15));
        assertThat(plan.maxAttempts()).isEqualTo(3);

        assertThat(events.ofType(CheckoutPlanned.class))
            .singleElement()
            .satisfies(event -> {
                assertThat(event.orderId())
                    .isEqualTo("ORD-1");
                assertThat(event.amountMinor())
                    .isEqualTo(125000L);
            });
    }
}
```

Bài test kiểm tra **bean registration, binding, validation, injection và việc sử dụng property bởi service thật**, đồng thời xác nhận domain event. Nó không chạy implementation `catalog` hoặc Kafka.

`@MockitoBean` có từ Spring Framework 6.2 với Spring Boot/Modulith tương thích; trên stack cũ có thể dùng `@MockBean` phù hợp. Đừng mock `CheckoutService` hay `CheckoutProperties` khi chính chúng là đối tượng cần xác minh.

## 10. Negative tests: thiếu/sai config phải fail ngay lúc bootstrap

Nếu tạo một `@ApplicationModuleTest` với cấu hình sai, JUnit có thể fail trước khi chạy bất kỳ method nào. Điều đó khiến khó khẳng định “context fail đúng lý do”. **`ApplicationContextRunner`** của Spring Boot Test thích hợp để cô lập và kiểm tra negative configuration.

```java
// src/test/java/com/example/shop/orders/CheckoutPropertiesContractTest.java
package com.example.shop.orders;

import com.example.shop.orders.internal.CheckoutProperties;
import com.example.shop.orders.internal.ExternalEventProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CheckoutPropertiesContractTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(PropertyOnlyConfiguration.class);

    @Test
    void validPropertiesAreBound() {
        runner.withPropertyValues(
            "shop.checkout.currency=VND",
            "shop.checkout.reservation-ttl=15m",
            "shop.checkout.max-attempts=3",
            "shop.order-events.enabled=false"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();

            CheckoutProperties props =
                context.getBean(CheckoutProperties.class);

            assertThat(props.currency()).isEqualTo("VND");
            assertThat(props.reservationTtl())
                .isEqualTo(java.time.Duration.ofMinutes(15));
            assertThat(props.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void missingCurrencyFailsFast() {
        runner.withPropertyValues(
            "shop.checkout.reservation-ttl=15m",
            "shop.checkout.max-attempts=3"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void zeroReservationTtlFailsFast() {
        runner.withPropertyValues(
            "shop.checkout.currency=VND",
            "shop.checkout.reservation-ttl=0s",
            "shop.checkout.max-attempts=3"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void retryBudgetOutOfRangeFailsFast() {
        runner.withPropertyValues(
            "shop.checkout.currency=VND",
            "shop.checkout.reservation-ttl=15m",
            "shop.checkout.max-attempts=0"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void enabledEventsWithoutTopicFailFast() {
        runner.withPropertyValues(
            "shop.checkout.currency=VND",
            "shop.checkout.reservation-ttl=15m",
            "shop.checkout.max-attempts=3",
            "shop.order-events.enabled=true"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void disabledEventsNeedNoTopic() {
        runner.withPropertyValues(
            "shop.checkout.currency=VND",
            "shop.checkout.reservation-ttl=15m",
            "shop.checkout.max-attempts=3",
            "shop.order-events.enabled=false"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context.getBean(
                ExternalEventProperties.class).topic())
                .isNull();
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties({
        CheckoutProperties.class,
        ExternalEventProperties.class
    })
    static class PropertyOnlyConfiguration {
    }
}
```

**Phạm vi bằng chứng chính xác:** runner chỉ tạo hai property beans; nó **không nạp module `orders` đầy đủ, không kiểm tra `@ConditionalOnProperty` của adapter, không khởi động Kafka**. Nó kiểm chứng property binding/validation độc lập và có thông báo startup failure có thể assert.

Nếu Bean Validation provider thiếu ở test classpath, negative tests không còn đúng ý nghĩa. Cần cấu hình dependency validation phù hợp; không xóa assertion để “cho test xanh”.

Khi muốn phân biệt lỗi `BindException` với validation failure, có thể kiểm tra cause tree, nhưng nên tránh assert nguyên văn toàn bộ message vì wording thay đổi giữa phiên bản Spring Boot.

## 11. Test properties và profiles không phải production config

`@ActiveProfiles("test")` chọn profile, trong khi `@TestPropertySource` cung cấp overrides dành cho test. Một bài test chỉ chạy với profile `test` **không chứng minh** cấu hình profile production đã đầy đủ.

```java
@ApplicationModuleTest
@org.springframework.test.context.ActiveProfiles("test")
@TestPropertySource(properties = {
    "shop.checkout.currency=VND",
    "shop.checkout.reservation-ttl=10m",
    "shop.checkout.max-attempts=2"
})
class TestProfileConfigurationContract {
    // Trong test thực, assert giá trị bean sau binding.
}
```

Đoạn này minh họa kết hợp annotation; không phải lớp test hoàn chỉnh. Với Spring Boot, một property có thể đến từ application config, environment, command line, profile-specific config, test source hoặc `@DynamicPropertySource`. Thứ tự ưu tiên phụ thuộc loại nguồn và cấu hình framework.

**Hãy kiểm tra effective value** mà config bean nhận được. Đừng chỉ nhìn `application.yml` và kết luận đó là giá trị runtime, cũng đừng log secret để điều tra.

### Khi dùng Testcontainers

```java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
        postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
        postgres::getUsername);
    registry.add("spring.datasource.password",
        postgres::getPassword);
}
```

`postgres` là Testcontainers instance giả định đã có lifecycle phù hợp. Đoạn code chỉ là fragment của integration test, không chạy độc lập. Hãy dùng khi **cần kiểm tra database adapter thật**, không bổ sung container vào mọi test binding.

Spring TestContext cache có thể tái sử dụng context giữa các test có cấu hình tương đương. Với giá trị dynamic phụ thuộc container lifecycle, thiết kế scope/reset/cache isolation để tránh dùng datasource trỏ tới container đã dừng.

## 12. Khác biệt giữa thiếu property, thiếu bean và hạ tầng lỗi

| Triệu chứng | Nguyên nhân hay gặp | Cách sửa đúng tầng |
| --- | --- | --- |
| Placeholder không resolve | Property thiếu hoặc key sai | Kiểm tra effective source/key/profile |
| `BindException` | Kiểu/unit không parse được | Sửa input và binding contract |
| Validation error | `maxAttempts=0`, TTL không dương | Sửa giá trị hoặc business policy |
| Thiếu `CheckoutProperties` bean | Không scan/enable config properties | Sửa registration trong module |
| Thiếu `CatalogPrices` ở `STANDALONE` | Provider module ngoài scope | Mock/fake API có chủ đích |
| Thiếu `KafkaTemplate` khi flag bật | Adapter thiếu bean infrastructure | Kafka auto-config/dependency |
| Adapter không có dù phải bật | Flag/profile/condition sai | Activation test với config mục tiêu |
| Adapter bean có nhưng send fail | Broker/serializer/network | Broker integration test |
| Full context xanh, module context fail | Module cấu hình phụ thuộc bean ngoài scope | Phân loại dependency và test scope |
| Module boot xanh, `verify()` fail | Import internal/allowed deps sai | Sửa public API, không mở boundary tùy tiện |

**Quan trọng:** `allowedDependencies` là quy tắc **kiến trúc**, không đăng ký bean hoặc điều khiển component scan. Một dependency được phép có thể vẫn vắng mặt trong `@ApplicationModuleTest(STANDALONE)`.

### Quy trình debug ngắn

1. Đọc **root cause đầu tiên** của `Failed to load ApplicationContext`.
2. Xác định module test thuộc `STANDALONE` hay `DIRECT_DEPENDENCIES`.
3. Kiểm tra config class có trong scan scope không; property bean có được đăng ký không.
4. Xác nhận effective property value, profile và condition; không lộ secret.
5. Phân biệt bean **nội bộ bắt buộc** với collaborator **ngoài module**.
6. Nếu flag bật adapter, kiểm tra bean activation rồi mới kiểm tra broker.
7. Chạy `ApplicationModules.verify()` riêng nếu nghi vi phạm dependency rule.

Không chữa lỗi thiếu configuration bean bằng cách mock configuration bean, và không chữa lỗi broker bằng cách nới `BootstrapMode`.

## 13. Kiểm chứng architecture riêng, không thay bằng context test

Với ví dụ `orders` gọi API public `catalog`, khai báo:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.example.shop.orders;
```

Và architecture test:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesModuleDependencyRules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Phép `verify()` kiểm tra kiến trúc module mà Spring Modulith nhận diện; nó không tạo `CheckoutProperties` và không bind `shop.checkout.*`. Ngược lại, module test có thể có mock đúng nhưng codebase vẫn có nơi import `catalog.internal` trái quy tắc.

Hai phép kiểm **đều bắt buộc** khi cần bảo vệ cấu hình bootstrap và ranh giới kiến trúc.

## 14. Matrix CI cho hợp đồng bootstrap

| Quality gate | Bài kiểm | Bảo vệ điều gì |
| --- | --- | --- |
| **Architecture** | `ApplicationModules.of(ShopApplication.class).verify()` | Quyền phụ thuộc, public/internal, cycles |
| **Property contract** | `CheckoutPropertiesContractTest` | Required/missing/invalid/conditional values |
| **Module bootstrap** | `CheckoutModuleBootstrapTest` | Bean registration, module scope, effective config |
| **Activation** | Test flag `enabled=false/true` có/không có adapter | Không bật nhầm hoặc tắt nhầm tính năng |
| **Production-like smoke** | Startup với bộ profile/property deployment đã phê duyệt | Không thiếu property khi chuyển môi trường |
| **Infrastructure integration** | Kafka/DB/HTTP test cho adapter cần thiết | Bean tồn tại **và** thực sự làm việc |

Module property/bootstrap tests thường đủ nhanh để chạy trong pull request. Integration với broker/database chạy ở gate phù hợp chi phí nhưng cần là **required check trước release** nếu đó là cam kết production.

### Checklist review khi thêm một config mới

- [ ] Property có owner module, tên, type, unit và miền hợp lệ.
- [ ] Bắt buộc hay conditional đã rõ; default được review về an toàn nghiệp vụ.
- [ ] Missing/invalid property có negative test fail-fast.
- [ ] Configuration class được đăng ký trong phạm vi module test.
- [ ] `@TestPropertySource`/profile trong test không phụ thuộc máy developer.
- [ ] Mock chỉ thay **API ngoài module** khi kiểm tra behavior/wiring nội bộ.
- [ ] Adapter bật/tắt có activation test, không chỉ test `@ConfigurationProperties`.
- [ ] Hạ tầng quan trọng có integration test; không suy delivery từ context load.
- [ ] Không expose internal type hoặc nới `allowedDependencies` để vá lỗi bootstrap.
- [ ] `ApplicationModules.verify()` chạy trong CI.
- [ ] Không hardcode token/password production trong code/config/log.

## 15. Bài tập tình huống

**A. TTL bằng 0:** cấu hình `shop.checkout.reservation-ttl=0s` có nên được bind? **Không**, vì contract yêu cầu positive duration. Negative `ApplicationContextRunner` test phải chứng minh failure.

**B. Quên đăng ký properties:** `CheckoutService` không inject được `CheckoutProperties` dù YAML có key. Cần thêm `@EnableConfigurationProperties`/scan phù hợp, **không mock CheckoutProperties** để test xanh.

**C. Kafka adapter bị bật nhưng không có topic:** `ExternalEventProperties` phải fail trong bootstrap. Nếu có topic nhưng thiếu `KafkaTemplate`, đó là lỗi **bean wiring** khác; nếu template đủ mà broker down, đó là lỗi **integration**.

**D. `STANDALONE` thiếu `CatalogPrices`:** đây là API từ module khác, nên có thể mock/fake khi test riêng `orders`. Không xem việc thiếu provider implementation là lý do đổi toàn bộ test sang `ALL_DEPENDENCIES`.

**E. Mọi test module xanh nhưng production không xuất event:** kiểm tra effective flag/profile, adapter activation, topic, Kafka producer và broker integration. Property binding xanh **không** chứng minh message được gửi.

## 16. Kết luận

Một hợp đồng bootstrap module có bốn thành phần rõ: **property cần có**, **quy tắc bind/validation**, **bean dependency** và **điều kiện kích hoạt adapter**. Thiếu hoặc sai cấu hình bắt buộc nên được phát hiện càng sớm càng tốt, thay vì đợi tới request đầu tiên trong production.

**Ghi nhớ:** dùng `ApplicationContextRunner` để kiểm tra missing/invalid properties; `@ApplicationModuleTest` để kiểm tra bean wiring và cách module dùng cấu hình; `ApplicationModules.verify()` để giữ đúng ranh giới phụ thuộc; integration/smoke tests để chứng minh adapter đang bật hoạt động với hạ tầng thật. Kết hợp các lớp đó trong quality gate CI giúp module **khởi động nhất quán, có thể tái lập và không che lỗi bằng mock hay default sai**.
