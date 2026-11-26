# Lưu log scenario và thông tin bootstrap

## 1. Khi CI đỏ, phải biết scenario nào và context nào đã thất bại

Một test `@ApplicationModuleTest` của `orders` thành công trên máy phát triển nhưng thất bại ở CI. Báo cáo chỉ có câu `Failed to load ApplicationContext`, hoặc `Expected 1 event but found 0`. Nếu thiếu mã scenario, bootstrap mode, profile đang bật và giai đoạn xử lý event, người điều tra thường phải chạy lại cả suite để đoán nguyên nhân.

Chủ đề **“Lưu log scenario và thông tin bootstrap”** nằm trong chương *CI và quality gate* của `SPRING_MODULITH_VERIFICATION_TESTING`. Học phần kiểm chứng ranh giới kiến trúc bằng `ApplicationModules` và quy tắc phụ thuộc, kiểm thử module bằng `@ApplicationModuleTest`, sự kiện, database và tích hợp; ở đây ta xây dựng **hồ sơ log có thể đối chiếu** cho từng bài kiểm để các quality gate đó chẩn đoán được lỗi.

Một hồ sơ hữu ích cần trả lời:

1. **Scenario nào?** JUnit class/method, scenario ID, dữ liệu tổng hợp có thể tái tạo.
2. **Bootstrap gì?** Module mục tiêu, `BootstrapMode`, profile, property được phép công bố, bean/collaborator kỳ vọng.
3. **Bước nào đã hoàn tất?** Validation, gọi provider, publish domain event, commit/rollback, listener, broker acknowledgement nếu có test đến tầng đó.
4. **Sai ở đâu?** Exception type/root cause, assertion, timeout hoặc test discovery.
5. **Bằng chứng ở đâu?** JUnit XML/HTML, Gradle console, log có correlation ID, thông tin build commit/JDK.
6. **Có bảo vệ dữ liệu không?** Không ghi secret, raw credentials, token, dữ liệu cá nhân hoặc cả environment dump vào artifact.

**Hợp đồng quan sát không thay thế hợp đồng nghiệp vụ:** `PublishedEvents` xác minh domain publication, architecture test xác minh dependency graph, DB/broker integration xác minh side effect tương ứng. Log giúp **giải thích** vì sao các phép kiểm đỏ; không được thay assertion bằng `logger.info("OK")`.

### Ma trận yêu cầu của bài

| Contract ID | Điều phải có | Bằng chứng |
| --- | --- | --- |
| `LOG-01` | Log scenario có test identity và correlation ID | `scenario.start`, `stage=...`, `scenario.end` |
| `LOG-02` | Business assertion kiểm kết quả/event, không chỉ kiểm log | `PublishedEvents` và AssertJ |
| `BOOT-01` | Snapshot bootstrap chứa module/mode/profile/bean cần thiết | JUnit bootstrap snapshot test |
| `BOOT-02` | Startup fail trước method vẫn để lại dấu vết | Gradle failure log + JUnit/CI artifact khi có |
| `EVT-01` | Listener async/hậu commit có event ID xuyên thread | Event payload/handler log + integration assertion |
| `CI-01` | Fail gate vẫn lưu evidence của cả attempt thất bại | GitHub Actions `if: always()` |
| `SEC-01` | Log/attachment đã lọc dữ liệu nhạy cảm | Whitelist fields, review trước upload |

## 2. Thiết kế schema log: scenario ID, event ID và bootstrap fingerprint

Đừng tạo một dòng log dài chứa mọi bean và toàn bộ `Environment`. Chọn những trường **ổn định, có ích, được phép công bố**.

| Trường | Ví dụ | Nguồn | Lưu ý |
| --- | --- | --- | --- |
| `scenario_id` | `SCN-5e9...` | JUnit tạo một lần cho test | Nối các dòng cùng case |
| `test_id` | `OrdersScenarioLogTest#acceptedOrder` | JUnit `TestInfo` | Không dùng tên hiển thị làm định danh vĩnh viễn |
| `module` | `orders` | Annotation/test ownership | Phải đúng module mục tiêu |
| `bootstrap_mode` | `STANDALONE` | `@ApplicationModuleTest` | Phân biệt với `DIRECT_DEPENDENCIES` |
| `profiles` | `test` | Spring `Environment` | Chỉ log tên profile, không dump sources |
| `context_id` | `application` hoặc ID framework cấp | Spring `ApplicationContext` | ID không phải trace ID toàn hệ thống |
| `event_id` | UUID | Domain event/publication | Dùng được xuyên thread |
| `stage` | `attempt`, `accepted`, `published`, `after_commit` | Code xử lý | Không tự suy bước kế tiếp đã thành công |
| `outcome` | `PASS`, `REJECTED`, `FAIL` | Test/handler | Gắn với tầng đã được assert |
| `elapsed_ms` | `34` | Monotonic clock | Là thời gian scenario, không phải toàn bộ bootstrap |
| `commit_sha`/`run_id` | CI metadata | Runner | Không lấy từ request payload |

Một **trace contract** tối thiểu, có thể tìm bằng `scenario_id`:

```text
level=INFO  scenario_id=SCN-5e9 stage=scenario.start module=orders test_id=OrdersScenarioLogTest#acceptedOrder
level=INFO  scenario_id=SCN-5e9 stage=order.attempt order_ref=ORD-SYNTH-1
level=INFO  scenario_id=SCN-5e9 stage=order.accepted event_type=OrderAccepted event_id=3f0...
level=INFO  scenario_id=SCN-5e9 stage=scenario.end elapsed_ms=36
```

Các dòng trên là **định dạng mong muốn**, không phải log mẫu lấy từ ứng dụng thật. `event_id` xác định **event cụ thể**; `scenario_id` xác định **test invocation**. Một scenario có thể phát nhiều event và một event có thể đi qua nhiều listener; **đừng dùng một giá trị cho cả hai mục đích**.

### Bootstrap fingerprint không phải dump cấu hình

Một snapshot tốt:

```text
stage=bootstrap.snapshot module=orders declared_mode=STANDALONE
profiles=[test] context_id=application order_service_count=1
inventory_port_count=1 condition_sources=41
```

`condition_sources` là số nguồn điều kiện mà Spring Boot ghi nhận (số minh họa), **không** có nghĩa 41 auto-configuration đều được bật. Không log danh sách raw properties, password, datasource URL chứa credentials, token hoặc `System.getenv()`.

### MDC chỉ đi theo thread hiện tại

SLF4J MDC hỗ trợ đặt `scenario_id` lên log **trong cùng thread**. Với `@Async`, listener chạy trên executor khác có thể mất MDC nếu không có context propagation. Vì vậy:

- Test đồng bộ có thể dùng MDC để gom log cùng scenario.
- Với listener async, lưu `event_id` trong **domain event**, rồi ghi lại event ID ở consumer.
- Nếu dùng `TaskDecorator`/Micrometer context propagation, cần kiểm thử propagation thực; đừng mặc định MDC tự qua thread.

## 3. Ví dụ ứng dụng: log theo stage nhưng giữ public module boundary

Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Modulith tương thích. Module `orders` phụ thuộc API công khai của `inventory`.

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── inventory/
│   └── StockAvailability.java
└── orders/
    ├── package-info.java
    ├── OrderAccepted.java
    └── OrderService.java

src/test/java/com/example/shop/
├── ModuleArchitectureTest.java
└── orders/
    ├── OrdersScenarioLogTest.java
    └── OrdersBootstrapSnapshotTest.java
```

Application root:

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

API công khai của provider:

```java
// src/main/java/com/example/shop/inventory/StockAvailability.java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean available(String sku);
}
```

Domain event có identity để nối log phía listener:

```java
// src/main/java/com/example/shop/orders/OrderAccepted.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderAccepted(
    UUID eventId,
    String orderId,
    String sku
) {
}
```

Service thật của `orders`, không mock trong module test:

```java
// src/main/java/com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final StockAvailability stock;
    private final ApplicationEventPublisher events;

    public OrderService(
            StockAvailability stock,
            ApplicationEventPublisher events) {
        this.stock = stock;
        this.events = events;
    }

    public boolean place(String orderId, String sku) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()) {
            log.warn("stage=order.invalid_input");
            throw new IllegalArgumentException(
                "Invalid order input");
        }

        // Chỉ log mã tổng hợp trong test; ở production
        // cần phân loại/refactor trước khi log identifiers.
        log.info("stage=order.attempt order_ref={}", orderId);

        if (!stock.available(sku)) {
            log.info("stage=order.rejected reason=out_of_stock");
            return false;
        }

        var event = new OrderAccepted(
            UUID.randomUUID(), orderId, sku);

        events.publishEvent(event);

        log.info(
            "stage=order.accepted event_type=OrderAccepted event_id={}",
            event.eventId());

        return true;
    }
}
```

Chỉ cho `orders` phụ thuộc `inventory`:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.orders;
```

**Giới hạn ví dụ:** `publishEvent` công bố event trong JVM; log `stage=order.accepted` chỉ phản ánh lời gọi `publishEvent` đã trở về thành công trong flow này. Không có JPA, transaction commit, event publication registry hay Kafka acknowledgement. **Không đổi tên stage thành `kafka.delivered` khi chưa kiểm thử broker thật.**

Một module test `STANDALONE` sẽ mock `StockAvailability`; điều đó vẫn giữ đúng API boundary. Cần một bài integration khác nếu muốn chạy implementation `inventory` thật.

## 4. JUnit: gắn scenario ID, bắt console log, assert business event

JUnit 5 cung cấp `TestInfo` để nhận test identity; Spring Boot Test có `OutputCaptureExtension`/`CapturedOutput` để quan sát stdout/stderr của một bài test. Kết hợp với SLF4J MDC và `PublishedEvents`, ta kiểm được **hai loại bằng chứng khác nhau**: lời hứa nghiệp vụ và trace contract.

```java
// src/test/java/com/example/shop/orders/OrdersScenarioLogTest.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.extension.ExtendWith;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;

@ExtendWith(OutputCaptureExtension.class)
@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
@ActiveProfiles("test")
class OrdersScenarioLogTest {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersScenarioLogTest.class);

    @Autowired
    OrderService orders;

    @MockitoBean
    StockAvailability stock;

    private String scenarioId;
    private long startNanos;

    @BeforeEach
    void begin(TestInfo info) {
        scenarioId = "SCN-" + UUID.randomUUID();
        startNanos = System.nanoTime();
        MDC.put("scenarioId", scenarioId);

        String testId =
            getClass().getSimpleName() + "#"
            + info.getTestMethod().orElseThrow().getName();

        log.info(
            "stage=scenario.start module=orders "
                + "declared_mode=STANDALONE test_id={}",
            testId);
    }

    @AfterEach
    void end() {
        try {
            long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - startNanos);

            log.info(
                "stage=scenario.end elapsed_ms={}",
                elapsedMs);
        } finally {
            MDC.remove("scenarioId");
        }
    }

    @Test
    void acceptedOrderHasBusinessAndTraceEvidence(
            PublishedEvents events,
            CapturedOutput output) {

        String orderId = "ORD-SYNTH-" + scenarioId;

        given(stock.available("SKU-1")).willReturn(true);

        assertThat(orders.place(orderId, "SKU-1")).isTrue();

        assertThat(events.ofType(OrderAccepted.class))
            .singleElement()
            .satisfies(event -> {
                assertThat(event.eventId()).isNotNull();
                assertThat(event.orderId()).isEqualTo(orderId);
                assertThat(event.sku()).isEqualTo("SKU-1");
            });

        // Đây là assertion riêng cho logging contract.
        // Logback console appender ở mục 8 phải được nạp.
        assertThat(output.getAll())
            .contains(
                scenarioId,
                "stage=scenario.start",
                "stage=order.accepted",
                "event_type=OrderAccepted");
    }

    @Test
    void rejectedOrderDoesNotPublishSuccessEvent(
            PublishedEvents events,
            CapturedOutput output) {

        given(stock.available("SKU-X")).willReturn(false);

        assertThat(orders.place("ORD-SYNTH-X", "SKU-X"))
            .isFalse();

        assertThat(events.ofType(OrderAccepted.class))
            .isEmpty();

        assertThat(output.getAll())
            .contains("stage=order.rejected");
    }

    @Test
    void invalidInputStopsBeforePublication(
            PublishedEvents events,
            CapturedOutput output) {

        assertThatThrownBy(() -> orders.place("", "SKU-1"))
            .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderAccepted.class))
            .isEmpty();

        assertThat(output.getAll())
            .contains("stage=order.invalid_input");
    }
}
```

### Điều test thực sự chứng minh

- `OrderService` thật chạy; `StockAvailability` là port **ngoài module** nên có test double.
- Mỗi scenario nhận một ID mới ở `@BeforeEach`, MDC được xóa ở `@AfterEach` để không rò sang test khác dùng cùng thread.
- `PublishedEvents` xác minh đúng **một event** ở nhánh thành công và **không có event** ở nhánh lỗi.
- `CapturedOutput` kiểm tra trường log đã thống nhất, không thay assertion event bằng phép dò chuỗi.
- `getAll()` chứa stdout và stderr mà extension capture được; kết quả phụ thuộc cấu hình logging và test runtime. Nếu log dùng async appender hoặc logger chuyển output ra file riêng, cần chọn capture mechanism đúng.
- `@MockitoBean` cần Spring Framework 6.2+ cùng Boot/Modulith tương thích; ở stack cũ dùng annotation mock phù hợp, chẳng hạn `@MockBean`.

**Một ranh giới thời gian quan trọng:** `@BeforeEach` chạy **sau khi Spring test context đã bootstrap**. Scenario ID gắn ở đây không thể có trong những log lỗi xảy ra **trước lúc JUnit test method được gọi**. Những lỗi đó phải được giữ qua Gradle/Spring startup log ở mục 6–9.

### Không coi test metadata là dữ liệu nhạy cảm được công bố tự động

Chỉ dùng `ORD-SYNTH-*` làm dữ liệu giả. Với order ID, địa chỉ, email hoặc bearer token thật, cần chính sách masking/hash/redaction. Không log toàn bộ event object theo `toString()` nếu payload có trường nhạy cảm.

## 5. JUnit: snapshot bootstrap sau khi context được tạo thành công

Không nên viết `log.info("ApplicationContext đã lên")` rồi kết luận bootstrap đúng. Hãy **assert những điều kiện cần** và log một fingerprint không chứa secret.

Dùng file test profile versioned chung, ví dụ `src/test/resources/application-test.yml`:

```yaml
shop:
  orders:
    contract-mode: strict
spring:
  main:
    banner-mode: "off"
```

Test riêng ở `orders`:

```java
// src/test/java/com/example/shop/orders/
// OrdersBootstrapSnapshotTest.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
@ActiveProfiles("test")
class OrdersBootstrapSnapshotTest {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersBootstrapSnapshotTest.class);

    @Autowired
    ConfigurableApplicationContext context;

    @Autowired
    Environment environment;

    @MockitoBean
    StockAvailability stock;

    @Test
    void recordsTheEffectiveBootstrapContract() {
        assertThat(environment.getActiveProfiles())
            .containsExactly("test");

        assertThat(environment.getProperty(
            "shop.orders.contract-mode"))
            .isEqualTo("strict");

        assertThat(context.getBeansOfType(OrderService.class))
            .hasSize(1);

        assertThat(context.getBeansOfType(
            StockAvailability.class)).hasSize(1);

        var conditions = ConditionEvaluationReport.get(
            context.getBeanFactory());

        int conditionSourceCount =
            conditions.getConditionAndOutcomesBySource().size();

        log.info(
            "stage=bootstrap.snapshot module=orders "
                + "declared_mode=STANDALONE "
                + "profiles={} context_id={} "
                + "order_service_count={} "
                + "stock_port_count={} condition_sources={}",
            Arrays.toString(environment.getActiveProfiles()),
            context.getId(),
            context.getBeansOfType(OrderService.class).size(),
            context.getBeansOfType(StockAvailability.class).size(),
            conditionSourceCount);
    }
}
```

**Cách đọc snapshot:**

| Trường | Dùng để chẩn đoán | Không nên suy ra |
| --- | --- | --- |
| `module=orders`, `declared_mode=STANDALONE` | Xác định test bootstrap phạm vi nào | Framework chắc chắn đã nạp mọi phụ thuộc ngoài module |
| `profiles=[test]` | Có test profile hiệu lực | Tất cả properties từ YAML đều không bị override |
| `contract-mode=strict` assert | Không có drift cho key không nhạy cảm | Production config cũng giống test config |
| `order_service_count=1` | Service nội bộ được tạo | Business rule đúng |
| `stock_port_count=1` | Test double port đã được đăng ký | Provider `inventory` thật có hoạt động |
| `context_id` | Phân biệt một phần các context | ID luôn duy nhất giữa CI invocations |
| `condition_sources` | Số nguồn condition hiện diện | Tất cả auto-configs đều matched/enabled |

`ConditionEvaluationReport` của Spring Boot chứa **thông tin auto-configuration/condition diagnostics**, có thể lớn và bao gồm dữ liệu framework. Ví dụ chỉ log **số lượng nguồn**, không dump toàn bộ map. Nếu cần tìm bean auto-configuration bị loại trừ, xem condition report theo hướng dẫn framework trong môi trường kiểm soát và **lọc dữ liệu nhạy cảm trước khi lưu artifact**.

### Khi context cache ảnh hưởng cách diễn giải

Spring TestContext có thể tái sử dụng `ApplicationContext` giữa các test class có cấu hình tương đương. Một snapshot ghi khi **test method chạy** không chứng minh rằng context vừa được tạo mới cho method đó. Không dùng `context_id` làm bộ đếm bootstrap hoặc so hai thời gian test rồi suy cache behavior. Nếu điều tra cache, đọc Spring TestContext cache diagnostics/log cấp thích hợp và tách chi phí startup khỏi chi phí test method.

## 6. Bootstrap thất bại trước `@Test`: giữ nguyên nguyên nhân gốc

Một lỗi phổ biến:

```text
Failed to load ApplicationContext
└─ BeanCreationException
   └─ ConfigurationPropertiesBindException
      └─ invalid value for shop.orders.required-topic
```

Nếu context fail lúc Spring TestContext chuẩn bị test instance, `@BeforeEach` và `@Test` trong phần 4–5 **không chạy**. Vì vậy **không thể đòi scenario ID hay `bootstrap.snapshot` do chính method in ra** xuất hiện trong log đó.

Phải thu **lỗi bootstrap bằng console Gradle/JUnit report**, đồng thời có một negative configuration contract test để kiểm tra tình huống được dự kiến.

### Ví dụ `ApplicationContextRunner` quan sát startup failure

Record cấu hình dùng Jakarta Bean Validation:

```java
// src/main/java/com/example/shop/orders/internal/
// RequiredEventProperties.java
package com.example.shop.orders.internal;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop.orders")
public record RequiredEventProperties(
    @NotBlank String requiredTopic
) {
}
```

Trong một JUnit độc lập:

```java
// src/test/java/com/example/shop/orders/
// RequiredEventBootstrapContractTest.java
package com.example.shop.orders;

import com.example.shop.orders.internal.RequiredEventProperties;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RequiredEventBootstrapContractTest {

    private static final Logger log = LoggerFactory.getLogger(
        RequiredEventBootstrapContractTest.class);

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PropertiesOnly.class);

    @Test
    void blankRequiredTopicFailsWithRecordedFailureType() {
        runner.withPropertyValues(
            "shop.orders.required-topic="
        ).run(context -> {
            Throwable startupFailure =
                context.getStartupFailure();

            assertThat(startupFailure).isNotNull();

            log.warn(
                "scenario=BOOT-INVALID-TOPIC "
                    + "stage=bootstrap.expected_failure "
                    + "error_type={}",
                startupFailure.getClass().getSimpleName());
        });
    }

    @Test
    void validTopicBinds() {
        runner.withPropertyValues(
            "shop.orders.required-topic=shop.orders.v1"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context.getBean(
                RequiredEventProperties.class).requiredTopic())
                .isEqualTo("shop.orders.v1");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(
        RequiredEventProperties.class)
    static class PropertiesOnly {
    }
}
```

**Phạm vi đúng:** runner chỉ kiểm **property binding/validation** của type đó; nó không bootstrap `OrderService` hoặc Kafka. `RequiredEventProperties` là một **minh họa hợp đồng config riêng**; không thêm nó vào `OrdersBootstrapSnapshotTest` khi bài test kia đang mô phỏng module không bắt buộc Kafka. Ví dụ cần Spring Boot Test và Bean Validation provider như `spring-boot-starter-validation`.

### Nên ghi gì khi startup thất bại?

- Exception **root cause/class** và stack trace trong CI artifact.
- Tên test class, profile, build SHA/JDK/Gradle version.
- Module dự kiến bootstrap và `BootstrapMode` theo annotation/test source.
- Key/property *không nhạy cảm* liên quan lỗi; không xuất secret value.
- Bean type/conditional configuration liên quan từ Spring diagnostics nếu cần.
- Phân loại **missing bean**, **bind/validation**, **module boundary**, **DB/broker connection**; đừng gán tất cả là “flaky”.

**Không ghi:** toàn bộ `Environment`, `System.getenv()`, `--debug` tràn lan trên CI chung, stack trace từ hệ thống chứa credentials chưa được review. Nếu log ghi nhầm secret, artifact cần được xử lý theo chính sách incident của tổ chức.

## 7. Nối trace qua event sau commit, listener bất đồng bộ và Testcontainers

Trong kiến trúc event, `scenario_id` từ MDC của test thread **không tự vượt qua** transaction callback hoặc executor thread. Để tìm nguyên nhân “event đã publish nhưng listener không chạy”, cần một **event identity** xuất hiện ở cả producer và consumer.

### Mẫu listener hậu commit: log theo `event_id`

Trong module consumer `notifications`, listener nhận public event từ `orders`:

```java
// src/main/java/com/example/shop/notifications/internal/
// OrderAcceptedListener.java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderAccepted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderAcceptedListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderAcceptedListener.class);

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    void afterCommit(OrderAccepted event) {
        log.info(
            "stage=listener.after_commit event_type=OrderAccepted "
                + "event_id={}",
            event.eventId());

        // Delegate tới một consumer port/idempotent handler thật.
    }
}
```

**Cần hiểu chính xác:**

- Listener thuộc module khác **không nhất thiết nằm trong `@ApplicationModuleTest(STANDALONE)` của `orders`**. Muốn kiểm listener thật, dùng integration scope chứa consumer.
- Listener `AFTER_COMMIT` chỉ được gọi khi có **transaction commit phù hợp**. `OrderService` ở phần 3 **không có `@Transactional`**; tự gọi `orders.place(...)` rồi chờ listener sẽ không chứng minh gì về after-commit.
- `@TransactionalEventListener` không tự bảo đảm durability/retry; nếu dùng `@ApplicationModuleListener` của Spring Modulith, phải kiểm publication registry và async handling theo version đã dùng.
- Đoạn listener chỉ **log lúc được invoke**, không lưu business side effect. Log có thể giúp debug invocation nhưng **chưa đủ để khẳng định contract consumer thành công**.

### Integration test tối thiểu có commit thật (fragment)

```java
// Fragment trong @SpringBootTest chạy với transaction manager,
// publisher và listener thật đã được cấu hình.
UUID eventId = UUID.randomUUID();

new TransactionTemplate(transactionManager)
    .executeWithoutResult(status ->
        publisher.publishEvent(new OrderAccepted(
            eventId, "ORD-SYNTH-IT", "SKU-1")));

// Sau commit: assert một state/probe thật của listener.
// Với async listener: chờ điều kiện tối đa 5 giây,
// không dùng Thread.sleep cố định.
await().atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(notificationProbe.received(eventId))
            .isTrue());
```

`transactionManager`, `publisher` và `notificationProbe` là collaborator **do integration fixture cung cấp**; `await()` thuộc Awaitility. Fragment không phải test chạy độc lập. Để kiểm rollback, dùng một scenario tương đương với `status.setRollbackOnly()` rồi assert consumer **không** tạo side effect.

**Không đánh đồng ba tín hiệu:**

| Tín hiệu | Nó chứng minh | Nó chưa chứng minh |
| --- | --- | --- |
| `PublishedEvents` có `OrderAccepted` | Publisher đã công bố domain event trong context | Listener đã hoàn tất, commit, broker ack |
| Log `listener.after_commit` | Callback được invoke | Side effect bền vững hoặc idempotency đúng |
| Repository/consumer probe đã nhận `eventId` sau commit | Business effect quan sát được trong scope test | External delivery ngoài scope |
| Kafka consumer đọc được record | Broker/route/serialization trong case test | Exactly-once cho mọi failure/replay |

### Nếu có PostgreSQL/Kafka Testcontainers

Sử dụng ID riêng per scenario, ghi tên image/version/container startup lifecycle, readiness và timeout. Có thể gắn `Slf4jLogConsumer` của Testcontainers vào logger **sau khi đảm bảo log không chứa secret/PII**; chỉ upload container logs cần điều tra. Không thu toàn bộ Docker daemon logs hoặc dump config không lọc.

Một tình huống hiếm: context cache vẫn giữ connection tới container đã dừng. Hãy log **test class, container lifecycle, selected endpoint đã mask**, không ghi password; sửa lifecycle/cache isolation chứ không chỉ tăng retry.

## 8. Logback và Gradle: giữ stdout/stderr, stack trace, JUnit XML đúng mục đích

Để `CapturedOutput` ở mục 4 nhìn thấy `scenario_id` trong console, dùng một mẫu logging chung trong `src/test/resources/logback-test.xml`:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{HH:mm:ss.SSS} %-5level
                scenario_id=%X{scenarioId:-none}
                logger=%logger{36} %msg%n
            </pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

**Chú ý:**

- Đây là **mẫu Logback**; nếu project dùng Log4j2 hoặc logging config khác, không copy rồi kỳ vọng Logback được nạp.
- Ký pháp `%X{scenarioId:-none}` lấy MDC value, dùng `none` khi không có ID. Các lỗi bootstrap trước `@BeforeEach` bình thường sẽ có `none`; đó là đúng vì scenario chưa bắt đầu.
- Trong code production, không bắt buộc hardcode logging theo test. Schema stage và event ID nên có giá trị vận hành; test log pattern có thể bổ sung MDC/format có chủ đích.
- Nếu `OutputCaptureExtension` không capture được appender của runtime hiện tại, kiểm cấu hình logging/testing trước; đừng đổi assertion nghiệp vụ để test pass.

### Cấu hình task Gradle riêng cho log scenario

Ví dụ `build.gradle` Groovy DSL với source set `test` và JUnit Platform:

```groovy
tasks.register('scenarioTraceTest', Test) {
    group = 'verification'
    description =
        'Run module scenario, bootstrap and config-failure tests'

    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform()

    filter {
        includeTestsMatching(
            'com.example.shop.orders.OrdersScenarioLogTest')
        includeTestsMatching(
            'com.example.shop.orders.OrdersBootstrapSnapshotTest')
        includeTestsMatching(
            'com.example.shop.orders.RequiredEventBootstrapContractTest')
        failOnNoMatchingTests = true
    }

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
        showStandardStreams = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

tasks.named('check') {
    dependsOn tasks.named('scenarioTraceTest')
}
```

Chạy cùng command trên laptop và CI (Windows dùng wrapper `gradlew.bat`):

```bash
./gradlew --no-daemon --console=plain scenarioTraceTest
```

Gradle thường ghi:

```text
build/test-results/scenarioTraceTest/
    TEST-com.example.shop.orders.OrdersScenarioLogTest.xml
    TEST-com.example.shop.orders.OrdersBootstrapSnapshotTest.xml
    TEST-com.example.shop.orders.RequiredEventBootstrapContractTest.xml

build/reports/tests/scenarioTraceTest/
    index.html
```

**Không dựa vào `showStandardStreams=true` trong mọi production pipeline nếu logs chứa dữ liệu thật.** Chỉ bật ở test fixtures đã được redaction/whitelist và theo retention/security policy. `exceptionFormat='full'` hữu ích khi debug bootstrap, nhưng exception message đôi khi chứa URL/secret—cần kiểm soát đầu ra và quyền truy cập CI artifact.

### Cần bảo vệ test discovery

`failOnNoMatchingTests = true` từ chối trường hợp filter **không khớp bất kỳ test nào**. Tuy nhiên nếu một class bị đổi tên mà hai class khác vẫn match, task có thể pass. CI nên yêu cầu XML **từng class**, test count dương và skipped bằng 0. `@Disabled` có thể làm task xanh nhưng không chạy phép kiểm; đây là một lỗ hổng chất lượng log/gate nếu không kiểm report.

## 9. GitHub Actions: lưu bằng chứng ngay cả khi module/bootstrap test thất bại

Một workflow tối thiểu cho Gradle single-project và JUnit XML mặc định:

```yaml
# Ví dụ .github/workflows/modulith-scenario-evidence.yml
name: Modulith scenario and bootstrap evidence

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  scenario-evidence:
    name: Scenario and bootstrap quality gate
    runs-on: ubuntu-latest
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Record non-secret build metadata
        shell: bash
        run: |
          mkdir -p evidence
          java -version 2> evidence/java-version.txt
          ./gradlew --version > evidence/gradle-version.txt
          printf 'commit=%s\nrun_id=%s\n' \
            "$GITHUB_SHA" "$GITHUB_RUN_ID" \
            > evidence/build-identity.txt

      - name: Run scenario trace tests and preserve console
        shell: bash
        run: |
          set -o pipefail
          ./gradlew --no-daemon --console=plain \
            scenarioTraceTest \
            2>&1 | tee evidence/scenario-gradle.log

      - name: Verify required tests really executed
        shell: bash
        run: |
          for klass in \
            com.example.shop.orders.OrdersScenarioLogTest \
            com.example.shop.orders.OrdersBootstrapSnapshotTest \
            com.example.shop.orders.RequiredEventBootstrapContractTest; do
            xml="build/test-results/scenarioTraceTest/TEST-$klass.xml"
            test -s "$xml"
            grep -Eq 'tests="[1-9][0-9]*"' "$xml"
            grep -q 'skipped="0"' "$xml"
            grep -q 'failures="0"' "$xml"
            grep -q 'errors="0"' "$xml"
          done

      - name: Upload diagnostics on success or failure
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: modulith-scenario-bootstrap-evidence
          path: |
            evidence/
            build/test-results/scenarioTraceTest/
            build/reports/tests/scenarioTraceTest/
          if-no-files-found: warn
          retention-days: 7
```

### Các tình trạng quan trọng

| Tình huống | Gate | Evidence |
| --- | --- | --- |
| Scenario pass và log stage đủ | PASS | Console + XML/HTML |
| Event assertion fail | FAIL | Console/JUnit XML có failed assertion |
| `ApplicationContext` fail trước `@Test` | FAIL | Gradle console/stack trace, có thể không có JUnit XML hoàn chỉnh |
| Toàn bộ filter không match | FAIL | Gradle task failure |
| Một class bị `@Disabled` | FAIL ở per-class evidence | XML có skipped |
| Một class đổi tên nhưng class khác vẫn chạy | FAIL ở per-class evidence | XML của class cũ thiếu |
| Log chứa token và bị upload | **Sự cố bảo mật** | Redaction/quyền truy cập artifact phải được xử lý, không xem là PASS |
| Task fail nhưng `if: always()` upload | FAIL | Artifact còn lại phục vụ điều tra |

**Hai điểm phải phân biệt:**

1. `if: always()` giúp **bước upload artifact** chạy kể cả khi task fail; nó **không** khiến quality gate pass. Không dùng `continue-on-error: true` cho test step để giữ PR xanh.
2. Workflow YAML chưa tự chặn merge. Repository phải đánh dấu job **Scenario and bootstrap quality gate** là **required status check** trong branch protection/ruleset. Nếu chỉ là optional job, failure có thể bị bỏ qua.

### Giới hạn kỹ thuật của ví dụ CI

- `grep` phù hợp layout JUnit XML của Gradle trong demo; với multi-project hoặc report aggregator, dùng XML parser cộng số tests, failures, skipped/errors trên từng suite.
- Khi Gradle fail ở compile hoặc context creation, report có thể không tồn tại hoặc không đầy đủ; do đó lưu **console log ngay từ đầu**, không chỉ dựa vào `build/test-results`.
- `set -o pipefail` bảo toàn exit code thất bại của Gradle khi có `tee`; không để pipeline kết thúc với exit code 0 chỉ vì `tee` thành công.
- Không bao giờ dùng `--debug` hoặc upload toàn bộ `env` chỉ để điều tra test fail; log và artifact có thể lưu quá lâu hoặc được nhiều người truy cập.
- Với nhiều retry attempts, lưu từng attempt trong thư mục riêng; không để lần pass sau ghi đè log failed attempt đầu. Chính sách retry thuộc gate riêng, không nên âm thầm retry đến khi xanh.

## 10. Bài tập kiểm chứng và checklist vận hành log scenario/bootstrap

### Negative drills cần thử trên branch hoặc fixture riêng

| Drill | Thay đổi có chủ đích | Kỳ vọng |
| --- | --- | --- |
| **D1: Event bị bỏ** | Xóa `events.publishEvent(event)` | `PublishedEvents` assertion đỏ; log trace giúp thấy thiếu publication |
| **D2: Event phát hai lần** | Gọi `publishEvent` hai lần | `singleElement()` đỏ, tránh log “accepted” che duplicate |
| **D3: Port từ chối** | Mock `stock.available` trả `false` | Không có `OrderAccepted`, có `stage=order.rejected` |
| **D4: Mất scenario MDC** | Bỏ `MDC.put(...)` | Logging contract assertion không còn `scenario_id` khi appender đúng |
| **D5: Sai profile** | Đổi `@ActiveProfiles("test")` thành `dev` | Bootstrap snapshot test đỏ |
| **D6: Drift policy** | Override `shop.orders.contract-mode=loose` | Assertion effective config đỏ |
| **D7: Missing bean** | Cố ý bỏ `@MockitoBean StockAvailability` ở STANDALONE | Context fail trước method; Gradle console vẫn có root cause |
| **D8: Invalid config** | `shop.orders.required-topic=` | `ApplicationContextRunner` ghi loại expected startup failure và test case vẫn xanh theo contract |
| **D9: Test bị bỏ** | Đặt `@Disabled` lên một class required | CI per-class XML evidence step đỏ |
| **D10: Log leak** | Đưa token giả vào một log fixture rồi quét artifact | Phải phát hiện/mask; không upload lại fixture chứa token |
| **D11: Listener chậm** | Dùng integration listener async có timeout thực | `event_id` nối được publisher/consumer; timeout không bị che bằng sleep vô hạn |

**Không dùng production secret để thực hiện D10**; chỉ dùng chuỗi giả có định danh test rõ và xóa sau thử nghiệm. Không kiểm log schema bằng cách hardcode toàn bộ một timestamp hay thứ tự thread không được cam kết.

### Quy trình điều tra CI đỏ trong năm bước

1. **Xác định identity:** commit, test class/method và `scenario_id` nếu test đã vào `@BeforeEach`.
2. **Xác định phạm vi:** `module`, declared `BootstrapMode`, active profiles, critical bean counts và config key whitelist.
3. **Đọc stage cuối:** `order.attempt`, `order.rejected`, `order.accepted`, `listener.after_commit`. Thiếu log chỉ là **manh mối**, chưa chứng minh thiếu event nếu logging có lỗi.
4. **Đối chiếu evidence nguồn:** JUnit assertion/`PublishedEvents`, transaction/DB state, condition/root cause; với Kafka phải có producer/consumer transport evidence nếu gate yêu cầu.
5. **Sửa nguyên nhân và thử phản chứng:** kiểm code/config/timing, chạy lại scenario có ID mới và kiểm quality gate vẫn bắt được mutation tương ứng.

### Checklist Definition of Done

- [ ] Mỗi scenario log có test identity, correlation ID và stage có tên ổn định.
- [ ] `MDC` được clear ở `@AfterEach`, không dựa vào thread-local xuyên async executor.
- [ ] Domain event có `event_id` để nối log producer và listener.
- [ ] `@ApplicationModuleTest` công bố `BootstrapMode` trong bài kiểm; collaborator mock đúng boundary.
- [ ] `PublishedEvents` assert payload và số lượng; không chỉ dò log “published”.
- [ ] Bootstrap snapshot assert profile, key không nhạy cảm, bean nội bộ/port; chỉ log fingerprint.
- [ ] Startup failure trước `@Test` vẫn có Gradle console + stack trace được giữ.
- [ ] `ApplicationContextRunner` có case cấu hình sai và expected failure rõ.
- [ ] Listener after-commit/async được kiểm bằng **integration side effect**, không chỉ log invocation.
- [ ] Test log pattern chung cho local/CI; không hardcode machine path/OS-specific format.
- [ ] Gradle task ghi JUnit XML/HTML và failure diagnostics; không vô tình bật logging quá chi tiết chứa secret.
- [ ] CI có `set -o pipefail` khi kết hợp Gradle với `tee`.
- [ ] GitHub Actions `if: always()` upload artifact cả khi task fail; retention/quyền truy cập phù hợp.
- [ ] Per-class XML evidence chặn test bị disabled, đổi tên hoặc không được chạy.
- [ ] Branch protection đánh dấu gate là required; không `continue-on-error`.
- [ ] Log không chứa token, password, raw connection string có secret hoặc PII.
- [ ] Negative drills D1, D5, D7, D9 đã được thử ở branch tạm và revert.
- [ ] Nếu có retry, các attempt giữ artifact **riêng**, không ghi đè first failure.

### Definition of Done

Một quality gate về **lưu log scenario và thông tin bootstrap** đạt yêu cầu khi:

1. **Có correlation xuyên các stage** nhờ `scenario_id` và `event_id`, với giới hạn async được ghi rõ.
2. **Có bootstrap evidence đủ dùng** về module/mode/profile/bean mà không lộ secret.
3. **Có log cho cả failure trước test method** qua Gradle/Spring console và artifact.
4. **Có assertions thực sự kiểm hợp đồng**: event, exception, transaction/DB/broker ở đúng tầng; log chỉ bổ trợ.
5. **Có evidence được lưu và truy xuất** qua JUnit XML, Gradle console và CI artifact.
6. **Không có silent skip hoặc xanh giả**: required checks và các negative drills chứng minh gate sẽ đỏ khi mất bằng chứng.

**Ghi nhớ:** log scenario tốt không phải xuất mọi thứ ra console. Hãy lưu **đúng identity, đúng stage, đúng snapshot bootstrap và đúng failure evidence**; dùng MDC cho test thread, event ID cho xử lý bất đồng bộ, whitelist dữ liệu được phép log và giữ Gradle/JUnit artifacts ngay cả khi context không khởi động. Với Spring Modulith, các trace này giúp điều tra `@ApplicationModuleTest` và event/DB integrations, trong khi **assertions và required CI gates** vẫn là tiêu chuẩn quyết định PASS/FAIL.
