# Tiêm registry vào bean và tách cấu hình khỏi mã nghiệp vụ

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, Micrometer cung cấp API thống nhất để ứng dụng Java ghi nhận `Counter`, `Gauge`, `Timer`, `DistributionSummary` và các meter khác. Khi dùng Spring Boot Actuator, ứng dụng thường được tự cấu hình một `MeterRegistry` dựa trên dependency registry có trong classpath. Các bean cần ghi nhận metrics có thể nhận registry qua dependency injection.

Thiết kế tốt nên tách ba trách nhiệm: cấu hình exporter và chính sách chung ở lớp cấu hình ứng dụng; đăng ký meter trong bean instrumentation; gọi các phương thức có ý nghĩa nghiệp vụ từ service. Cách tổ chức này giữ code nghiệp vụ dễ đọc, giúp thay đổi backend hoặc tag chung ít ảnh hưởng đến luồng xử lý, đồng thời làm cho instrumentation dễ kiểm thử.

## 1. Spring Boot tạo MeterRegistry như thế nào?

Khi có Spring Boot Actuator và dependency của một Micrometer registry, auto-configuration của Spring Boot tạo và cấu hình registry tương ứng. Ví dụ, dependency `micrometer-registry-prometheus` cung cấp `PrometheusMeterRegistry`; Spring Boot kết nối nó với Actuator để expose endpoint Prometheus khi endpoint được bật và expose.

Với Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Với Maven, dùng starter Actuator và dependency registry tương ứng, đồng thời để Spring Boot dependency management quản lý phiên bản Micrometer tương thích:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Khi registry đã được auto-configure, Spring quản lý vòng đời bean và có thể inject `MeterRegistry` vào các component. Không cần tự khởi tạo `PrometheusMeterRegistry` trong từng service hoặc controller.

## 2. Inject MeterRegistry bằng constructor

Constructor injection làm rõ bean cần registry nào và giúp phụ thuộc được kiểm tra ngay khi Spring tạo bean:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class OrderMetrics {
    private final Counter ordersCreated;
    private final Timer createDuration;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("orders.created")
            .description("Number of successfully created orders")
            .register(registry);
        this.createDuration = Timer.builder("orders.create.duration")
            .description("Time spent creating an order")
            .register(registry);
    }

    public void orderCreated() {
        ordersCreated.increment();
    }

    public <T> T recordCreate(Supplier<T> operation) {
        return createDuration.record(operation);
    }
}
```

Spring tìm một bean phù hợp với kiểu `MeterRegistry` và truyền vào constructor. Bean `OrderMetrics` đăng ký meter một lần trong lúc khởi tạo, giữ tham chiếu đến `Counter`, sau đó cập nhật counter qua phương thức `orderCreated()`.

Constructor injection có một số lợi ích:

- Phụ thuộc của bean được thể hiện rõ trong chữ ký constructor.
- Field có thể khai báo `final`, tránh thay đổi registry sau khi khởi tạo.
- Unit test có thể truyền một `SimpleMeterRegistry` mà không cần khởi động Spring.
- Không cần gọi `Metrics.globalRegistry` hoặc truy cập một registry static toàn cục.

Nếu ứng dụng có nhiều registry riêng biệt và bean cần một registry cụ thể, hãy thiết kế rõ registry nào được inject, có thể thông qua composite registry do Spring Boot quản lý hoặc qualifier phù hợp. Với cấu hình thông thường, inject `MeterRegistry` là đủ.

## 3. Đăng ký meter một lần, dùng lại trong các lần xử lý

Không tạo builder và đăng ký meter mới cho mỗi request. Hãy tạo meter khi bean instrumentation được khởi tạo và giữ tham chiếu để tái sử dụng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.function.Supplier;

@Component
public class CheckoutMetrics {
    private final Counter accepted;
    private final Counter rejected;
    private final Timer processingTime;

    public CheckoutMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("checkout.requests")
            .tag("result", "accepted")
            .register(registry);

        this.rejected = Counter.builder("checkout.requests")
            .tag("result", "rejected")
            .register(registry);

        this.processingTime = Timer.builder("checkout.processing.duration")
            .description("Time spent processing a checkout")
            .register(registry);
    }

    public void accepted() {
        accepted.increment();
    }

    public void rejected() {
        rejected.increment();
    }

    public <T> T recordProcessing(Supplier<T> operation) {
        return processingTime.record(operation);
    }
}
```

Hai counter có cùng tên nhưng tag `result` khác nhau nên là hai meter khác nhau. Mỗi meter được đăng ký trong constructor; các lần xử lý chỉ gọi phương thức ghi nhận. Registry sẽ quản lý meter theo định danh và exporter đọc số liệu từ registry đó.

Đăng ký meter tập trung cũng giúp reviewer nhận ra metric nào tồn tại, tên và tag nào được sử dụng, cũng như loại meter có đúng ý nghĩa hay không.

## 4. Giữ mã nghiệp vụ độc lập với chi tiết MeterRegistry

Service nghiệp vụ nên mô tả sự kiện ở mức ý nghĩa như “đơn hàng được tạo” hoặc “checkout bị từ chối”. Không nên rải tên metric, tag key, cấu hình histogram và logic export trong nhiều nhánh nghiệp vụ.

```java
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final OrderMetrics metrics;

    public OrderApplicationService(
            OrderRepository repository,
            OrderMetrics metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }

    public Order create(CreateOrderCommand command) {
        return metrics.recordCreate(() -> {
            Order order = repository.save(Order.from(command));
            metrics.orderCreated();
            return order;
        });
    }
}
```

Ở đây `OrderApplicationService` biết sự kiện cần ghi nhận thông qua `OrderMetrics`, nhưng không biết metric được đặt tên ra sao, tag nào được gắn hoặc dữ liệu được gửi tới Prometheus hay backend khác. Các chi tiết đó nằm trong bean instrumentation và cấu hình registry.

Nếu ứng dụng cần tách sâu hơn, có thể định nghĩa một interface nhỏ như `OrderTelemetry` trong lớp application và cung cấp implementation Micrometer ở lớp infrastructure. Cách này hữu ích khi module nghiệp vụ cần được kiểm thử độc lập hoặc có nhiều implementation telemetry. Với ứng dụng nhỏ, một component `OrderMetrics` riêng có thể đã đủ rõ ràng.

Lưu ý về transaction: ví dụ trên tăng counter sau khi `repository.save()` trả về. Nếu metric phải có nghĩa “transaction đã commit”, thao tác tăng counter cần diễn ra sau commit, chẳng hạn qua transaction synchronization hoặc sự kiện after-commit. Counter không tham gia transaction database và không tự rollback khi giao dịch bị hủy.

## 5. Dùng MeterBinder khi muốn đóng gói một nhóm meter

`MeterBinder` là một cơ chế của Micrometer để đóng gói việc đăng ký một nhóm meter. Bean triển khai `MeterBinder` định nghĩa phương thức `bindTo(MeterRegistry)`; Spring Boot có thể tự động bind các bean này vào registry được quản lý.

Ví dụ, một binder theo dõi độ sâu queue:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
public class OrderQueueMetrics implements MeterBinder {
    private final AtomicInteger queueDepth = new AtomicInteger();

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
            .description("Number of orders waiting for processing")
            .register(registry);
    }

    public void taskEnqueued() {
        queueDepth.incrementAndGet();
    }

    public void taskDequeued() {
        queueDepth.updateAndGet(current -> Math.max(0, current - 1));
    }
}
```

`queueDepth` là field của bean nên có tham chiếu mạnh và sống cùng bean. `bindTo` đăng ký gauge cho registry được truyền vào; code xử lý queue chỉ cập nhật trạng thái. Nếu binder được bind vào nhiều registry, mỗi registry có meter riêng nhưng cùng quan sát object trạng thái này.

Nên dùng `MeterBinder` khi muốn tái sử dụng một nhóm instrumentation, đóng gói các meter của một thành phần hoặc để Spring Boot quản lý việc bind vào registry. Với một vài meter đơn giản chỉ dùng trong một bean, constructor injection trực tiếp có thể dễ đọc hơn.

## 6. Dùng MeterRegistryCustomizer cho cấu hình chung

`MeterRegistryCustomizer` cho phép tùy chỉnh registry trước khi meter được đăng ký, ví dụ thêm tag chung cho mọi meter. Đây là nơi phù hợp cho cấu hình áp dụng ở cấp ứng dụng, không phải nơi service nghiệp vụ tự thêm tag.

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags(
            @Value("${spring.application.name:application}") String applicationName,
            @Value("${DEPLOYMENT_REGION:local}") String region) {
        return registry -> registry.config().commonTags(
            "application", applicationName,
            "region", region);
    }
}
```

Các tag `application` và `region` được áp dụng nhất quán cho meter của registry. Giá trị phải có tập hữu hạn và ổn định; không dùng user ID, request ID hoặc URL có ID thực tế làm common tag.

`MeterRegistryCustomizer` và `MeterBinder` có trách nhiệm khác nhau:

| Cơ chế | Trách nhiệm |
| --- | --- |
| `MeterRegistryCustomizer` | Tùy chỉnh registry, ví dụ common tags hoặc cấu hình chung |
| `MeterBinder` | Đăng ký một nhóm meter cụ thể vào registry |
| Bean instrumentation inject `MeterRegistry` | Đăng ký và cập nhật meter gắn với một thành phần ứng dụng |
| `MeterFilter` | Chấp nhận, từ chối, đổi tên, sửa tag hoặc cấu hình thống kê cho meter phù hợp |

Giữ mỗi cơ chế ở đúng vai trò giúp tránh một lớp cấu hình phải biết quá nhiều về nghiệp vụ.

## 7. Đặt cấu hình exporter trong application.yml

Thông tin backend và exporter nên được quản lý bằng cấu hình môi trường thay vì hard-code trong service. Ví dụ với Spring Boot và Prometheus:

```yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    tags:
      environment: ${APP_ENV:local}
```

Ứng dụng expose endpoint `/actuator/prometheus` khi Prometheus registry có trong classpath, endpoint được bật và được expose. Prometheus server cấu hình scrape target ở phía server; ứng dụng không cần biết địa chỉ Prometheus để phục vụ scrape.

Với registry push như Datadog, cấu hình endpoint, API key và step trong cấu hình môi trường. Ví dụ minh họa cho Spring Boot 3.x:

```yaml
management:
  datadog:
    metrics:
      export:
        api-key: ${DD_API_KEY}
        step: 30s
```

Prefix cấu hình có thể thay đổi theo phiên bản Spring Boot và registry. Kiểm tra configuration metadata của phiên bản dự án trước khi áp dụng. Không lưu API key trong source control; cấp credentials bằng secret manager hoặc biến môi trường của nền tảng triển khai.

## 8. Cấu hình phân phối tập trung

Các cấu hình histogram và SLO cũng nên nằm ở lớp cấu hình thay vì lặp lại trong mọi service. Có thể dùng properties của Spring Boot hoặc `MeterFilter` tùy phạm vi cần áp dụng.

Ví dụ cấu hình histogram và SLO cho HTTP request qua application properties:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,1s
```

Tên property và cách hỗ trợ phụ thuộc phiên bản Spring Boot. Khi cần quy tắc phức tạp theo loại meter, prefix hoặc tag, có thể khai báo `MeterFilter` trong `@Configuration`. Cần nhớ Timer sử dụng đơn vị thời gian; DistributionSummary sử dụng đơn vị do ứng dụng ghi nhận. Không áp dụng một ngưỡng SLO cho hai meter có đơn vị khác nhau.

## 9. Tránh những cách quản lý registry gây khó bảo trì

Một số cách triển khai làm phụ thuộc telemetry lan rộng hoặc khiến registry bị tách khỏi exporter:

**Tạo registry thủ công trong service:**

```java
// Không nên dùng trong service được Spring quản lý.
SimpleMeterRegistry registry = new SimpleMeterRegistry();
```

Registry này độc lập với registry mà Spring Boot cấu hình. Meter ghi vào đó có thể không xuất hiện trong endpoint production.

**Dùng static global registry:**

```java
// Tránh phụ thuộc ngầm vào global registry.
Metrics.counter("orders.created").increment();
```

Static global registry khiến phụ thuộc khó thấy trong constructor và có thể gây khác biệt giữa môi trường test, ứng dụng và nhiều registry. Ưu tiên inject registry hoặc một bean metrics.

**Đăng ký meter mỗi lần xử lý:**

```java
// Không nên tạo và đăng ký builder theo mỗi request.
Counter.builder("orders.created").register(registry).increment();
```

Registry có thể tái sử dụng meter cùng tên/tag, nhưng code vẫn phải tra cứu/đăng ký lặp lại và làm ranh giới khai báo metric khó kiểm soát. Hãy giữ tham chiếu meter trong bean sống lâu.

**Đưa dữ liệu không giới hạn vào tag:**

```java
// Tránh: mỗi orderId có thể tạo một time series.
registry.counter("orders.created", "orderId", orderId).increment();
```

Tag cần có cardinality thấp. Nếu cần tra cứu một đơn hàng cụ thể, dùng log hoặc trace.

## 10. Kiểm thử bean instrumentation mà không khởi động Spring

Bean nhận `MeterRegistry` qua constructor có thể được kiểm thử bằng `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderMetricsTest {
    @Test
    void incrementsCreatedCounter() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.orderCreated();

        assertEquals(
            1.0,
            registry.get("orders.created").counter().count());
    }
}
```

Test tập trung vào hành vi bean và không cần tạo Spring ApplicationContext. Với code nghiệp vụ, có thể mock `OrderMetrics` để xác minh service phát tín hiệu ở đúng nhánh thành công/thất bại mà không phụ thuộc vào Micrometer.

## 11. Kiểm thử tích hợp với Spring Boot

Unit test không xác minh auto-configuration, customizer, binder hoặc endpoint export. Một integration test có thể khởi động Spring context và lấy registry đã được Boot cấu hình:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MetricsContextTest {
    @Autowired
    MeterRegistry registry;

    @Autowired
    OrderMetrics orderMetrics;

    @Test
    void registersAndUpdatesOrderCounter() {
        orderMetrics.orderCreated();

        assertThat(registry.get("orders.created").counter().count())
            .isEqualTo(1.0);
    }
}
```

Với Prometheus, có thể kiểm tra thêm endpoint `/actuator/prometheus` để xác nhận metric được export với tên và label đúng. Với registry push, dùng test server hoặc collector để xác nhận request gửi đi, đồng thời kiểm tra timeout và lỗi xác thực.

## 12. Vòng đời bean và registry

Registry do Spring quản lý thường sống trong vòng đời `ApplicationContext`. Bean metrics singleton có thể đăng ký meter trong constructor hoặc `bindTo()` và giữ tham chiếu đến meter trong suốt thời gian ứng dụng hoạt động.

Tránh đăng ký meter từ bean prototype hoặc request-scoped nếu meter thực chất là thống kê toàn ứng dụng. Việc tạo nhiều bean có thể dẫn đến đăng ký lặp, giữ object nguồn không cần thiết hoặc tạo tag/meter không ổn định. Với Gauge, object nguồn cần được giữ sống bởi bean hoặc thành phần sở hữu trạng thái; registry không nhất thiết giữ tham chiếu mạnh tới object được quan sát.

Khi ứng dụng có nhiều registry, cần hiểu binder/customizer được áp dụng cho registry nào. Không giữ một registry tự tạo trong static field rồi mong Spring Boot tự export nó. Hãy để cấu hình Spring quyết định registry và inject đúng bean được quản lý.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Không inject được `MeterRegistry` | Thiếu Actuator/registry dependency hoặc auto-configuration bị loại trừ |
| Meter xuất hiện trong unit test nhưng không có ở endpoint | Test dùng `SimpleMeterRegistry`; production registry khác hoặc endpoint chưa expose |
| Common tag không xuất hiện | `MeterRegistryCustomizer` chưa được tạo, cấu hình sai hoặc meter đăng ký trong registry khác |
| MeterBinder không được gọi | Bean binder không nằm trong ApplicationContext hoặc cấu hình auto-configuration không nhận bean |
| Có hai series giống nghĩa | Meter được đăng ký ở nhiều nơi với tên/tag khác nhau hoặc binder và bean metrics trùng nhau |
| Counter tăng hai lần | Service và listener cùng ghi nhận một sự kiện, hoặc retry bị tính như sự kiện mới |
| Gauge chuyển thành NaN | Object nguồn không còn tham chiếu mạnh hoặc hàm đọc không còn giá trị |
| Cardinality tăng nhanh | Tag chứa ID, URL thô hoặc dữ liệu đầu vào tùy ý |
| API key xuất hiện trong log/repository | Credentials được hard-code hoặc log cấu hình nhạy cảm |

Khi chẩn đoán, kiểm tra theo thứ tự: dependency registry, auto-configuration, bean `MeterRegistry`, customizer/binder, meter ID và tag, cuối cùng là endpoint export. Không kết luận exporter lỗi chỉ vì một unit test với `SimpleMeterRegistry` đã chạy thành công.

## 14. Nguyên tắc áp dụng

Inject `MeterRegistry` bằng constructor vào bean instrumentation sống lâu. Đăng ký meter một lần và giữ tham chiếu để ghi nhận nhiều lần. Để service nghiệp vụ gọi các phương thức có ý nghĩa như `orderCreated()` hoặc `recordProcessing()` thay vì biết tên metric, tag và giao thức export.

Dùng `MeterBinder` để đóng gói một nhóm meter có thể tái sử dụng; dùng `MeterRegistryCustomizer` cho cấu hình chung như common tags; dùng `MeterFilter` cho quy tắc lọc và cấu hình meter; đặt endpoint, credentials và step của exporter trong cấu hình môi trường. Cuối cùng, kiểm thử bean bằng `SimpleMeterRegistry` và kiểm thử tích hợp endpoint/transport bằng registry production. Cách phân chia này giúp instrumentation nhất quán, dễ thay đổi backend và dễ bảo trì khi ứng dụng mở rộng.
