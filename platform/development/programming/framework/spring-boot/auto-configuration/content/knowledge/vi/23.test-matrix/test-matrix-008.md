# Kiểm thử tính năng độc lập và trường hợp tích hợp nhiều tính năng trong Spring Boot Auto Configuration

Một custom starter có thể cung cấp nhiều tính năng: infrastructure dùng chung, metrics, audit, adapter web hoặc các integration tùy chọn. Mỗi tính năng có thể hoạt động đúng khi được kiểm thử riêng, nhưng khi cùng xuất hiện trong một ứng dụng, chúng vẫn có thể xung đột về bean, condition, property, thứ tự đăng ký hoặc cách phối hợp.

Vì vậy, bộ kiểm thử auto-configuration cần hai góc nhìn bổ sung nhau:

- **Kiểm thử từng tính năng độc lập:** cô lập auto-configuration và các đầu vào cần thiết của đúng feature. Mục tiêu là biết condition nào bật/tắt, bean mặc định nào được tạo và user bean nào khiến cấu hình back off.
- **Kiểm thử tích hợp nhiều tính năng:** nạp nhiều auto-configuration vào cùng một context, dùng chung infrastructure và xác nhận các feature cùng tồn tại, phối hợp đúng, tôn trọng property riêng và không tạo bean trùng hoặc dependency thiếu.

`ApplicationContextRunner` phù hợp cho cả hai góc nhìn. Mỗi test dựng một context có đầu vào xác định, có thể chọn auto-configuration, property, user configuration và classpath. Khi cần kiểm tra toàn bộ ứng dụng, discovery từ JAR, cấu hình môi trường, component scan hoặc HTTP server, bổ sung integration test bằng `@SpringBootTest`.

## 1. Vì sao cần cả test độc lập lẫn test tích hợp?

Giả sử một custom starter cung cấp ba thành phần:

- `EventBus`: hạ tầng phát sự kiện dùng chung.
- `MetricsListener`: nhận sự kiện để đếm hoạt động.
- `AuditListener`: nhận sự kiện để lưu lịch sử.

Mỗi feature có condition riêng:

- Event bus có bean mặc định nếu ứng dụng chưa tự cung cấp `EventBus`.
- Metrics chỉ bật khi `demo.metrics.enabled=true`.
- Audit chỉ bật khi `demo.audit.enabled=true`.
- Cả hai listener đều cần `EventBus`.

Nếu chỉ test từng feature trong context riêng, ta chưa biết hai listener có cùng nhận được một event hay không. Nếu chỉ test một context chứa mọi feature, khi một bean thiếu hoặc condition sai sẽ khó xác định lỗi thuộc feature nào.

| Loại test | Phạm vi context | Câu hỏi chính | Ví dụ |
| --- | --- | --- | --- |
| Feature độc lập | Infrastructure cần thiết + một auto-configuration | Feature có bật đúng, tạo đúng bean và xử lý dependency riêng không? | EventBus + Metrics, không nạp Audit. |
| Feature độc lập khác | Infrastructure cần thiết + auto-configuration khác | Feature thứ hai có thể chạy riêng không? | EventBus + Audit, không nạp Metrics. |
| Tích hợp nhiều feature | Nhiều auto-configuration trong cùng context | Các feature có dùng chung bean và phối hợp đúng không? | EventBus + Metrics + Audit cùng nhận một event. |
| Ma trận property | Một tập auto-configuration, thay đổi tổ hợp property | Tắt một feature có vô tình tắt feature khác không? | Metrics bật, Audit tắt; rồi đảo lại. |
| Integration của ứng dụng | ApplicationContext gần với ứng dụng thật, có thể kèm server | Starter có được phát hiện, cấu hình và vận hành đúng trong ứng dụng consumer không? | `@SpringBootTest` với cấu hình thực tế. |

Hai lớp đầu giúp chẩn đoán chính xác. Lớp tích hợp phát hiện lỗi tương tác. Integration test xác nhận các thành phần hoạt động trong cách ứng dụng thực sự được khởi động.

## 2. Dựng context xác định bằng `ApplicationContextRunner`

`ApplicationContextRunner` cho phép xây một context nhỏ cho mỗi tình huống. Thay vì khởi động toàn bộ ứng dụng, test chỉ nạp những auto-configuration cần khảo sát.

Một runner cơ sở thường được khai báo thành field:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class
                ));
```

Các điểm quan trọng:

- `withConfiguration(AutoConfigurations.of(...))` chọn những auto-configuration cần nạp.
- `withPropertyValues(...)` kiểm soát Environment cho từng test.
- `withUserConfiguration(...)` thêm cấu hình bean do ứng dụng cung cấp.
- `withBean(...)` thêm một bean trực tiếp vào runner khi chỉ cần mô phỏng một dependency.
- `withClassLoader(new FilteredClassLoader(...))` mô phỏng thư viện hoặc class không có trên runtime classpath.
- `withInitializer(...)` thêm thao tác khởi tạo context, ví dụ bật `ConditionEvaluationReportLoggingListener`.
- `run(context -> ...)` tạo context, cho phép assertion rồi đóng context sau callback.

Runner có API theo kiểu builder: mỗi lần gọi phương thức `with...` trả về runner đã được tùy chỉnh. Giữ giá trị trả về hoặc nối các lời gọi; đừng gọi một phương thức rồi bỏ qua runner mới.

**Mỗi lần gọi `run` là một lần thử nghiệm riêng.** Không dựa vào bean instance của test trước. Hãy tạo dependency trong context/supplier hoặc dùng dữ liệu bất biến để tránh rò trạng thái giữa các test.

### 2.1. Nạp nhiều auto-configuration

Có thể truyền nhiều class vào một `AutoConfigurations.of`:

```java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                EventBusAutoConfiguration.class,
                MetricsAutoConfiguration.class,
                AuditAutoConfiguration.class
        ));
```

Spring Boot áp dụng các auto-configuration theo cùng thứ tự như khi chạy ứng dụng; không cần cố sắp xếp danh sách đối số để mô phỏng thứ tự runtime. Nếu một cấu hình thật sự phụ thuộc vào cấu hình khác, hãy khai báo quan hệ rõ ràng bằng `@AutoConfiguration(after = ...)`, `before` hoặc `@AutoConfigureAfter`/`@AutoConfigureBefore`.

Thứ tự auto-configuration ảnh hưởng **thứ tự bean definition được xử lý**. Nó không quyết định thứ tự tạo instance của mọi bean; việc khởi tạo instance phụ thuộc dependency graph và các quan hệ `@DependsOn`.

## 3. Xác định ranh giới giữa test độc lập và test tích hợp

Một test độc lập vẫn phải nạp **infrastructure bắt buộc** của feature. “Độc lập” có nghĩa là không nạp các feature không liên quan, chứ không phải cố tình bỏ dependency mà feature cần.

Ví dụ:

- Test Metrics: nạp EventBus + Metrics.
- Test Audit: nạp EventBus + Audit.
- Test phối hợp: nạp EventBus + Metrics + Audit.

Không nên nạp mọi auto-configuration của starter vào tất cả test chỉ để tiện dùng một runner chung. Hãy tạo runner cơ sở theo từng ranh giới test:

```java
private final ApplicationContextRunner metricsRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class
                ));

private final ApplicationContextRunner auditRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        AuditAutoConfiguration.class
                ));

private final ApplicationContextRunner combinedRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        EventBusAutoConfiguration.class,
                        MetricsAutoConfiguration.class,
                        AuditAutoConfiguration.class
                ));
```

Cách chia này tạo ra ba loại bằng chứng:

1. Mỗi feature chạy được với infrastructure tối thiểu.
2. Hai feature có thể cùng dùng infrastructure trong một context.
3. Lỗi xuất hiện chỉ khi kết hợp sẽ được khoanh vùng ở lớp tích hợp.

## 4. Ví dụ xuyên suốt: EventBus, Metrics và Audit

Ta xây một thí nghiệm Spring Boot 3.3.5 / Java 17. Hai feature có property riêng nhưng dùng chung một `EventBus`. Mục tiêu là chứng minh:

- Metrics chạy khi được bật, dù Audit không được nạp.
- Audit chạy khi được bật, dù Metrics không được nạp.
- Khi bật cả hai, mỗi event được cả hai listener nhận đúng một lần.
- Tắt một property không làm tắt feature còn lại.
- Nếu không có EventBus, các feature phụ thuộc vào nó sẽ back off.
- Bean infrastructure hoặc listener do ứng dụng cung cấp được tôn trọng.

### 4.1. Cấu trúc dự án

```text
feature-matrix-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── FeatureMatrixTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>feature-matrix-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 4.2. File test đầy đủ

Tạo `src/test/java/demo/FeatureMatrixTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureMatrixTest {

    static final class EventBus {
        private final String source;
        private final List<Consumer<String>> subscribers =
                new CopyOnWriteArrayList<>();

        EventBus(String source) {
            this.source = source;
        }

        String source() {
            return this.source;
        }

        void subscribe(Consumer<String> subscriber) {
            this.subscribers.add(subscriber);
        }

        void publish(String event) {
            this.subscribers.forEach(subscriber -> subscriber.accept(event));
        }
    }

    static final class MetricsListener implements Consumer<String> {
        private final String source;
        private final AtomicInteger received = new AtomicInteger();

        MetricsListener(String source) {
            this.source = source;
        }

        String source() {
            return this.source;
        }

        int count() {
            return this.received.get();
        }

        @Override
        public void accept(String event) {
            this.received.incrementAndGet();
        }
    }

    static final class AuditListener implements Consumer<String> {
        private final List<String> events = new CopyOnWriteArrayList<>();

        @Override
        public void accept(String event) {
            this.events.add(event);
        }

        List<String> events() {
            return List.copyOf(this.events);
        }
    }

    @AutoConfiguration
    static class EventBusAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(EventBus.class)
        EventBus eventBus() {
            return new EventBus("auto-configured");
        }
    }

    @AutoConfiguration(after = EventBusAutoConfiguration.class)
    @ConditionalOnBean(EventBus.class)
    @ConditionalOnProperty(
            prefix = "demo.metrics",
            name = "enabled",
            havingValue = "true"
    )
    static class MetricsAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(MetricsListener.class)
        MetricsListener metricsListener(EventBus eventBus) {
            MetricsListener listener = new MetricsListener("auto-configured");
            eventBus.subscribe(listener);
            return listener;
        }
    }

    @AutoConfiguration(after = EventBusAutoConfiguration.class)
    @ConditionalOnBean(EventBus.class)
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true"
    )
    static class AuditAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditListener.class)
        AuditListener auditListener(EventBus eventBus) {
            AuditListener listener = new AuditListener();
            eventBus.subscribe(listener);
            return listener;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEventBusConfiguration {

        @Bean
        EventBus eventBus() {
            return new EventBus("user");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserMetricsConfiguration {

        @Bean
        MetricsListener metricsListener(EventBus eventBus) {
            MetricsListener listener = new MetricsListener("user");
            eventBus.subscribe(listener);
            return listener;
        }
    }

    private final ApplicationContextRunner metricsRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            MetricsAutoConfiguration.class
                    ));

    private final ApplicationContextRunner auditRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            AuditAutoConfiguration.class
                    ));

    private final ApplicationContextRunner combinedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            EventBusAutoConfiguration.class,
                            MetricsAutoConfiguration.class,
                            AuditAutoConfiguration.class
                    ));

    @Test
    void metricsWorksWithoutLoadingAuditFeature() {
        metricsRunner
                .withPropertyValues("demo.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).doesNotHaveBean(AuditListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);

                    bus.publish("order-created");

                    assertThat(metrics.count()).isEqualTo(1);
                });
    }

    @Test
    void auditWorksWithoutLoadingMetricsFeature() {
        auditRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(AuditListener.class);
                    assertThat(context).doesNotHaveBean(MetricsListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    AuditListener audit = context.getBean(AuditListener.class);

                    bus.publish("payment-approved");

                    assertThat(audit.events())
                            .containsExactly("payment-approved");
                });
    }

    @Test
    void bothFeaturesReceiveTheSameEventThroughOneBus() {
        combinedRunner
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).hasSingleBean(AuditListener.class);

                    EventBus bus = context.getBean(EventBus.class);
                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);
                    AuditListener audit = context.getBean(AuditListener.class);

                    bus.publish("invoice-issued");

                    assertThat(metrics.count()).isEqualTo(1);
                    assertThat(audit.events()).containsExactly("invoice-issued");
                });
    }

    @ParameterizedTest
    @CsvSource({
            "false, false, false, false",
            "true,  false, true,  false",
            "false, true,  false, true",
            "true,  true,  true,  true"
    })
    void featurePropertiesAreIndependent(
            boolean metricsEnabled,
            boolean auditEnabled,
            boolean expectMetrics,
            boolean expectAudit) {

        combinedRunner
                .withPropertyValues(
                        "demo.metrics.enabled=" + metricsEnabled,
                        "demo.audit.enabled=" + auditEnabled
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(EventBus.class);

                    assertThat(context.getBeansOfType(MetricsListener.class))
                            .hasSize(expectMetrics ? 1 : 0);

                    assertThat(context.getBeansOfType(AuditListener.class))
                            .hasSize(expectAudit ? 1 : 0);
                });
    }

    @Test
    void featureBacksOffWhenSharedInfrastructureIsNotImported() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MetricsAutoConfiguration.class
                ))
                .withPropertyValues("demo.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(EventBus.class);
                    assertThat(context).doesNotHaveBean(MetricsListener.class);
                });
    }

    @Test
    void userInfrastructureIsSharedByBothFeatures() {
        combinedRunner
                .withUserConfiguration(UserEventBusConfiguration.class)
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBeansOfType(EventBus.class))
                            .containsOnlyKeys("eventBus");

                    EventBus bus = context.getBean(EventBus.class);
                    assertThat(bus.source()).isEqualTo("user");

                    bus.publish("shipment-dispatched");

                    assertThat(context.getBean(MetricsListener.class).count())
                            .isEqualTo(1);
                    assertThat(context.getBean(AuditListener.class).events())
                            .containsExactly("shipment-dispatched");
                });
    }

    @Test
    void userMetricsListenerOverridesOnlyTheMetricsDefault() {
        combinedRunner
                .withUserConfiguration(UserMetricsConfiguration.class)
                .withPropertyValues(
                        "demo.metrics.enabled=true",
                        "demo.audit.enabled=true"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MetricsListener.class);
                    assertThat(context).hasSingleBean(AuditListener.class);

                    MetricsListener metrics =
                            context.getBean(MetricsListener.class);
                    assertThat(metrics.source()).isEqualTo("user");

                    context.getBean(EventBus.class).publish("refund-created");

                    assertThat(metrics.count()).isEqualTo(1);
                    assertThat(context.getBean(AuditListener.class).events())
                            .containsExactly("refund-created");
                });
    }
}
```

Chạy từ thư mục `feature-matrix-lab` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả kỳ vọng:** tất cả test thành công. Có bảy phương thức test; phương thức `featurePropertiesAreIndependent` chạy bốn tổ hợp property bằng JUnit parameterized test. Tổng cộng có mười lần tạo context. Test không gọi `System.out.println` nên không có stdout nghiệp vụ cố định; Maven Surefire báo kết quả theo số test invocation thực tế.

## 5. Hiểu điều gì đang được kiểm chứng trong ví dụ

### 5.1. Test độc lập kiểm tra contract của từng feature

`metricsWorksWithoutLoadingAuditFeature` chỉ nạp EventBus và Metrics. Nó xác nhận Metrics hoạt động khi Audit không có trong context. Test tương ứng cho Audit chứng minh feature thứ hai không phụ thuộc vào việc Metrics được bật.

Nếu test độc lập thất bại, phạm vi điều tra thường hẹp:

- Property có được truyền đúng không?
- Condition trên feature class có khớp không?
- Infrastructure có tồn tại trước khi `@ConditionalOnBean` được đánh giá không?
- Bean method có back off vì user bean hoặc một bean cùng kiểu không?
- Constructor/dependency của listener có tạo được không?

Không cần phân tích tương tác giữa hai feature khi test còn chưa chứng minh feature chạy độc lập.

### 5.2. Test tích hợp xác nhận hành vi, không chỉ sự hiện diện

Trong `bothFeaturesReceiveTheSameEventThroughOneBus`, assertion quan trọng không dừng ở việc có đủ ba bean. Test phát một event qua EventBus rồi xác nhận:

- Metrics nhận event đúng một lần.
- Audit ghi đúng event đó.
- Chỉ có một EventBus trong context.

Nếu chỉ assert `hasSingleBean`, test có thể bỏ sót lỗi listener không subscribe, subscribe hai lần hoặc dùng nhầm một EventBus khác. Hãy kiểm tra **hành vi phối hợp** giữa các feature.

### 5.3. Ma trận property tìm lỗi bật/tắt chéo

`featurePropertiesAreIndependent` kiểm tra đủ bốn tổ hợp:

| `demo.metrics.enabled` | `demo.audit.enabled` | Metrics | Audit |
| --- | --- | --- | --- |
| `false` | `false` | Không có | Không có |
| `true` | `false` | Có | Không có |
| `false` | `true` | Không có | Có |
| `true` | `true` | Có | Có |

Đây là ma trận Boolean hai feature. Với ba feature Boolean, toàn bộ tổ hợp là `2³ = 8`; với bốn feature là `2⁴ = 16`. Không nhất thiết phải chạy mọi tổ hợp nếu có thể chứng minh một số điều kiện độc lập, nhưng cần kiểm tra những tổ hợp có khả năng tương tác theo dependency hoặc property chung.

Khi số feature tăng, hãy nhóm theo dependency graph và rủi ro tương tác. Ví dụ, nếu cả Metrics và Audit đều phụ thuộc EventBus, ưu tiên các trường hợp:

- Từng feature cùng EventBus.
- Cả hai feature cùng EventBus.
- Một feature bật, feature kia tắt.
- EventBus do ứng dụng cung cấp.
- EventBus vắng mặt hoặc optional dependency không có.

### 5.4. Kiểm tra backoff ở cấp infrastructure và cấp feature

Test `featureBacksOffWhenSharedInfrastructureIsNotImported` không nạp EventBusAutoConfiguration. Dù property Metrics là `true`, Metrics vẫn không xuất hiện vì condition `@ConditionalOnBean(EventBus.class)` không khớp.

Test `userInfrastructureIsSharedByBothFeatures` thêm EventBus của ứng dụng. Bean mặc định của starter nhường chỗ; cả hai feature dùng chung bean do user cung cấp.

Test `userMetricsListenerOverridesOnlyTheMetricsDefault` chứng minh một override có phạm vi hẹp: listener Metrics mặc định back off, nhưng Audit vẫn được tạo. Một feature bị override không được vô tình vô hiệu hóa các feature khác nếu contract không yêu cầu điều đó.

## 6. Thứ tự auto-configuration và dependency giữa các feature

Một lỗi tích hợp thường xảy ra khi feature B có `@ConditionalOnBean` phụ thuộc bean do feature A cung cấp, nhưng A và B không có quan hệ thứ tự rõ ràng.

Ví dụ:

```java
@AutoConfiguration
class EventBusAutoConfiguration {
    // Đăng ký EventBus.
}

@AutoConfiguration(after = EventBusAutoConfiguration.class)
@ConditionalOnBean(EventBus.class)
class MetricsAutoConfiguration {
    // Chỉ áp dụng khi EventBus đã có bean definition.
}
```

`@AutoConfiguration(after = EventBusAutoConfiguration.class)` diễn đạt quan hệ phụ thuộc khi xử lý bean definitions. Nó hữu ích khi Metrics cần biết EventBus đã được đăng ký trước lúc condition chạy.

Một số quy tắc quan trọng:

- `@ConditionalOnBean` và `@ConditionalOnMissingBean` đánh giá các bean definition đã được xử lý tới thời điểm condition chạy.
- Auto-configuration của Boot được xử lý sau user-defined bean definitions; đây là lý do các condition backoff phù hợp để cho phép ứng dụng thay default.
- Nếu một auto-configuration khác cung cấp infrastructure, khai báo `before`/`after` rõ ràng thay vì dựa vào thứ tự ngẫu nhiên của danh sách.
- `@AutoConfigureOrder` phù hợp khi cần thứ tự giữa các auto-configuration không muốn phụ thuộc trực tiếp vào nhau.
- Thứ tự định nghĩa bean khác với thứ tự khởi tạo instance; dependency injection và `@DependsOn` chi phối việc tạo instance.

Trong test tích hợp, hãy nạp cùng tập auto-configuration mà ứng dụng sẽ dùng. `AutoConfigurations.of` áp dụng cơ chế ordering của Boot; không cần tự đảo thứ tự đối số để mô phỏng runtime.

## 7. Dùng Condition Evaluation Report khi một feature không xuất hiện

Khi một test tích hợp có nhiều feature, report giúp xác định configuration class hoặc bean method nào không khớp condition.

Có thể bật log report trong runner:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(AutoConfigurations.of(
                EventBusAutoConfiguration.class,
                MetricsAutoConfiguration.class,
                AuditAutoConfiguration.class
        ));
```

Hoặc đọc `ConditionEvaluationReport` trực tiếp từ BeanFactory của context. Khi điều tra, tập trung vào:

- `positiveMatches`: source có condition khớp.
- `negativeMatches`: source có ít nhất một condition không khớp; đọc lý do cụ thể.
- `ClassName#beanMethod`: condition ở cấp bean method, có thể khác kết quả condition cấp class.
- Bean name/type thực tế trong context: xác nhận condition khớp có dẫn đến bean definition như mong đợi không.

Ví dụ, Metrics class có thể match property, nhưng method tạo `MetricsListener` vẫn back off vì ứng dụng đã cung cấp listener custom. Đó là kết quả đúng nếu contract cho phép thay thế. Ngược lại, nếu class-level `@ConditionalOnBean(EventBus.class)` không khớp, hãy kiểm tra EventBus có được đăng ký trước Metrics hay không.

## 8. Khi nào cần `@SpringBootTest` thay cho runner?

`ApplicationContextRunner` chủ động nạp các auto-configuration đã chọn và tạo context nhỏ. Đây là lựa chọn tốt để test logic điều kiện, bean registration và tương tác giữa các feature. Tuy nhiên, nó không tự chứng minh toàn bộ quá trình khởi động ứng dụng thật.

Dùng `@SpringBootTest` hoặc một integration test consumer khi cần kiểm tra:

- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trong JAR đã publish có được Boot phát hiện không.
- Ứng dụng consumer có load đúng starter qua dependency graph không.
- Property từ `application.yml`, profile, environment variable hoặc command line có tạo kết quả mong đợi không.
- Component scan, user configuration và các auto-configuration mặc định của Boot có tương tác đúng không.
- Servlet/Reactive server, HTTP route, filter, security chain hoặc resource thực tế có vận hành đúng không.
- Kết nối database, broker, cache hoặc dịch vụ ngoài có hoạt động trong môi trường tích hợp.

Ví dụ skeleton cho ứng dụng consumer:

```java
@SpringBootTest(
        classes = ConsumerApplication.class,
        properties = {
                "demo.metrics.enabled=true",
                "demo.audit.enabled=true"
        }
)
class StarterConsumerIntegrationTest {

    @Autowired
    EventBus eventBus;

    @Autowired
    MetricsListener metrics;

    @Autowired
    AuditListener audit;

    @Test
    void bothFeaturesAreAvailableInConsumerApplication() {
        eventBus.publish("integration-event");

        assertThat(metrics.count()).isEqualTo(1);
        assertThat(audit.events()).containsExactly("integration-event");
    }
}
```

Đây là skeleton cho dự án consumer có starter và auto-configuration imports đã được đóng gói đúng. `ConsumerApplication` là ứng dụng Spring Boot thực tế. Nếu cần test web server, đặt `webEnvironment` phù hợp và gọi endpoint qua HTTP client test.

**Phân biệt phạm vi:** runner nạp các class đã chỉ định, nên rất phù hợp để chứng minh hành vi của các auto-configuration đó. Integration test consumer còn kiểm tra artifact discovery và cách ứng dụng thật khởi động. Hai test trả lời hai câu hỏi khác nhau.

## 9. Ma trận kiểm thử nên thiết kế thế nào khi có nhiều feature?

Không cần tạo mọi hoán vị một cách máy móc. Hãy xây ma trận dựa trên **dependency graph**, **điều kiện bật/tắt** và **điểm giao nhau**.

| Nhóm tình huống | Câu hỏi cần trả lời | Ví dụ ưu tiên |
| --- | --- | --- |
| Default behavior | Không có user config thì starter cung cấp gì? | Infrastructure mặc định và từng feature mặc định. |
| Feature riêng | Mỗi feature có chạy độc lập với dependency bắt buộc không? | Core + Metrics; Core + Audit. |
| Property isolation | Tắt feature A có ảnh hưởng feature B không? | A=true/B=false và A=false/B=true. |
| Combined behavior | Các feature có phối hợp qua infrastructure chung không? | Một event được hai listener nhận. |
| User override | User bean thay đúng default và giữ feature còn lại không? | Custom EventBus; custom MetricsListener. |
| Missing optional dependency | Thiếu thư viện ngoài có làm hỏng feature khác không? | Dùng `FilteredClassLoader` để loại dependency của một adapter. |
| Ordering | Condition phụ thuộc bean từ auto-config khác có chạy đúng không? | Feature sau Core infrastructure. |
| Conflict/ambiguity | Có nhiều bean cùng kiểu hoặc cùng tên không? | Hai implementation, `@Primary`, qualifier và bean names. |
| Full application | Artifact và cấu hình consumer có được nạp đúng không? | `@SpringBootTest` với starter đã publish. |

Nếu feature chỉ hoạt động trong Servlet hoặc Reactive context, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` tương ứng. Nếu feature phụ thuộc thư viện tùy chọn, dùng `FilteredClassLoader` để mô phỏng class/package vắng mặt; assertion nên xác nhận đúng bean/configuration đã back off.

Một quy trình thực tế:

1. Vẽ dependency graph: feature nào cần infrastructure nào, feature nào có thể chạy độc lập.
2. Viết test default cho từng feature.
3. Viết test property bật/tắt từng feature.
4. Viết test user override ở từng điểm mở rộng.
5. Viết test kết hợp cho các nhóm feature dùng chung bean hoặc thứ tự.
6. Chỉ thêm test full application cho các rủi ro không thể quan sát bằng context runner.

Với n feature độc lập hoàn toàn, không cần kiểm tra mọi tập con có thể có. Với các feature chia sẻ bean hoặc condition chéo, hãy kiểm tra những tổ hợp chạm vào cùng dependency.

## 10. Lỗi thường gặp trong test nhiều tính năng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Feature chạy riêng nhưng mất khi chạy cùng feature khác | Bean condition, bean name/type hoặc ordering khác dự kiến | Đọc report cho cả class và method; kiểm tra bean definitions đã có tại thời điểm condition chạy. |
| Cả hai feature tạo hai infrastructure bean | Mỗi auto-configuration không dùng chung contract type hoặc thiếu `@ConditionalOnMissingBean` | Chuẩn hóa interface/type dùng chung và backoff theo type. |
| Tắt property của A làm B biến mất | B phụ thuộc class-level configuration hoặc property chung của A | Tách condition theo feature; chỉ dùng property chung khi đó là contract có chủ đích. |
| Listener tồn tại nhưng không nhận event | Listener không subscribe vào đúng EventBus hoặc subscribe hai lần | Assert hành vi publish/receive và kiểm tra bean cùng bus instance. |
| Test pass riêng nhưng lỗi khi nạp chung | Trùng bean name, nhiều candidate cùng type, condition không khớp hoặc cấu hình xung đột | Assert bean map, kiểm tra ambiguity và thử user override. |
| Kết quả thay đổi theo thứ tự class trong test | Dựa vào thứ tự import thay vì khai báo ordering | Dùng `@AutoConfiguration(after/before = ...)` hoặc `@AutoConfigureOrder`. |
| Test dùng một context lớn quá khó chẩn đoán | Nạp quá nhiều auto-configuration không liên quan | Quay về test độc lập, rồi thêm từng feature có quan hệ. |
| Runner test pass nhưng app consumer không nạp feature | Chưa kiểm tra AutoConfiguration.imports, dependency artifact hoặc discovery | Thêm integration test consumer bằng `@SpringBootTest` và kiểm tra JAR. |
| Test phụ thuộc vào database/broker thật | Test condition kéo side effect hoặc bean kết nối ngoài vào context | Thay dependency bằng fake/in-memory test configuration; dành kiểm thử kết nối thật cho integration suite riêng. |
| Condition report match nhưng bean không dùng được | Bean definition được đăng ký nhưng khởi tạo hoặc tương tác runtime thất bại | Kiểm tra startup failure và test hành vi bean sau khi context refresh. |

## 11. Tổ chức bộ test để dễ bảo trì

Một cấu trúc thư mục có thể chia theo feature và integration:

```text
src/test/java/
└── com/example/starter/
    ├── autoconfigure/
    │   ├── EventBusAutoConfigurationTests.java
    │   ├── MetricsAutoConfigurationTests.java
    │   └── AuditAutoConfigurationTests.java
    ├── integration/
    │   ├── MetricsAndAuditIntegrationTests.java
    │   ├── CustomInfrastructureIntegrationTests.java
    │   └── StarterConsumerIntegrationTests.java
    └── support/
        ├── TestEventBus.java
        └── TestListeners.java
```

Gợi ý phân chia:

- File test của feature chứa các trường hợp property, classpath, missing bean và custom bean của feature đó.
- File integration chứa các feature cần phối hợp, shared infrastructure, ordering và xung đột.
- Test support chứa fake hoặc in-memory infrastructure có thể tái sử dụng.
- Test consumer kiểm tra artifact, imports resource và cấu hình gần với ứng dụng thật.

Không đưa mọi test vào một class khổng lồ. Tên test nên diễn đạt hành vi, ví dụ `auditBacksOffWhenUserAuditListenerExists` hoặc `metricsAndAuditShareOneEventBus`.

## 12. Checklist trước khi kết luận auto-configuration đã được kiểm thử đầy đủ

- [ ] Mỗi feature có ít nhất một test độc lập với infrastructure tối thiểu.
- [ ] Property bật/tắt của từng feature được kiểm tra.
- [ ] User bean override được kiểm tra theo đúng type/name condition.
- [ ] Các feature dùng chung infrastructure có test trong cùng context.
- [ ] Test tích hợp phát sinh hành vi thực tế, không chỉ kiểm tra bean có mặt.
- [ ] Tổ hợp property quan trọng được kiểm tra để phát hiện bật/tắt chéo.
- [ ] Condition phụ thuộc bean từ auto-configuration khác có thứ tự khai báo rõ ràng.
- [ ] Tình huống thiếu optional dependency và web context được test bằng runner phù hợp.
- [ ] Không chia sẻ mutable bean state giữa các lần `run`.
- [ ] Condition Evaluation Report được dùng khi cần giải thích nhánh không khớp.
- [ ] Có integration test consumer nếu cần xác nhận AutoConfiguration.imports, artifact và startup thực tế.
- [ ] External service được fake trong context test và chỉ kiểm tra thật trong integration suite có chủ đích.

**Ghi nhớ:** kiểm thử độc lập chứng minh từng feature đáp ứng contract riêng; kiểm thử tích hợp chứng minh các feature cùng tồn tại và phối hợp đúng trong một ApplicationContext. Hãy dùng `ApplicationContextRunner` để kiểm soát chính xác các tổ hợp configuration/property/bean, rồi dùng `@SpringBootTest` khi cần xác minh quá trình khởi động ứng dụng consumer và discovery từ artifact. Đừng chỉ kiểm tra bean được tạo; hãy phát event, gọi collaborator và xác nhận hành vi giữa các feature.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Testing Your Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Testing Spring Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-applications.html
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — `AutoConfigurations`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html