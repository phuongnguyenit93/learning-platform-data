# @AutoConfigureObservability theo khả năng hỗ trợ của phiên bản Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Sự kiện và observability  
> **Đề bài:** `@AutoConfigureObservability` theo khả năng hỗ trợ của phiên bản  
> **Mục tiêu:** Hiểu đúng vai trò của Micrometer Observation trong tests, phạm vi `@AutoConfigureObservability` của Spring Boot 3.x, sự thay đổi trong Spring Boot 4.x, cấu hình metrics/traces và test slices, kiểm tra event observation bằng JUnit/JVM in-memory mà không phụ thuộc exporter thật. Có project minh họa Java 17 + Spring Boot 3.5.0 + Maven với mã kiểm thử độc lập và integration/slice tests.

## 1. Vấn đề: test có ghi event nhưng không thấy metric/trace

Một service có thể publish `ApplicationEvent`, listener có thể xử lý đúng, và `ObservationRegistry` bean vẫn có mặt, nhưng một test vẫn không tìm thấy metric hoặc trace như kỳ vọng.

Các nguyên nhân không đồng nhất:

1. Spring Boot test configuration chủ động giới hạn **metric export/tracing reporting** để tests không đẩy dữ liệu sang backend thật.
2. Test đang dùng `@WebMvcTest` hoặc slice khác, không tải đầy đủ actuator/tracing auto-configuration giống production.
3. `ObservationRegistry` hiện diện nhưng không có `ObservationHandler` phù hợp để tạo `Timer` hoặc span.
4. Service không thực sự gọi `Observation.start/stop` hoặc không có `@Observed` aspect được bật.
5. Metric đã tạo nhưng tên/tags không đúng; test tra sai registry hoặc timer chưa kết thúc.
6. Tracer trong slice có thể là **no-op**, nên bean tồn tại không chứng minh có span export.
7. Test quan sát một `ApplicationEvent` nhưng lại không tạo Observation quanh listener; một việc không tự kéo theo việc kia.
8. Test dùng import annotation theo **phiên bản Spring Boot khác** nên thậm chí không compile.
9. Exporter ngoài mạng không khả dụng hoặc bị disable trong test, trong khi business outcome hoàn toàn đúng.
10. Tests chạy song song/chung context làm registry chứa metric từ tests trước, khiến assert count bằng một trở nên flaky.

**Điểm trọng tâm của bài:** `@AutoConfigureObservability` **không phải một annotation bất biến của mọi Spring Boot version**, cũng không phải “bật tất cả logging, metrics, tracing và exporters”. Trước khi áp dụng cần xác định version, artifact, package, test level và bằng chứng thực sự muốn kiểm tra.

## 2. Ma trận phiên bản: phải đọc trước khi copy annotation

| Dòng phiên bản | Annotation phù hợp | Phạm vi và lưu ý |
| --- | --- | --- |
| **Spring Boot 2.7.x** | **Không có** `@AutoConfigureObservability` của Boot 3.x | Có cơ chế metrics test cũ, nhưng Micrometer Observation/tracing model không tương đương Boot 3.x; không copy package 3.x |
| **Spring Boot 3.0–3.5.x** | `@AutoConfigureObservability` | Package `org.springframework.boot.test.autoconfigure.actuate.observability`, có từ **3.0.0** |
| **Spring Boot 4.0.x** | `@AutoConfigureMetrics` và/hoặc `@AutoConfigureTracing` | Test infrastructure chia module theo concern; annotation `@AutoConfigureObservability` cũ **không còn trong Boot 4.0** |
| **Các bản Boot 4.x mới hơn** | Kiểm tra Javadoc/test module tương ứng trước khi dùng | Dùng documentation chính xác với version trong `pom.xml`/Gradle dependency graph, không dựa vào blog của version khác |

### 2.1. Import cho Spring Boot 3.5

```java
import org.springframework.boot.test.autoconfigure.actuate.observability
        .AutoConfigureObservability;
```

**Đây là cách bẻ dòng hợp lệ ở Java import? Không.** Trong source Java thực tế, phải viết import trên **một dòng**, không xuống dòng giữa package và class:

```java
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
```

Một test:

```java
@SpringBootTest
@AutoConfigureObservability
class OrdersObservabilityIntegrationTest {
    // ...
}
```

`@AutoConfigureObservability` thuộc **test autoconfiguration**, không phải annotation của production business bean. Test cần test dependencies của Boot và actuator/Micrometer phù hợp; phần project hoàn chỉnh bên dưới cung cấp chúng.

### 2.2. Import đúng hướng ở Spring Boot 4.0

Boot 4.0 chia metrics và tracing test support:

```java
// Spring Boot 4.0: dùng artifact test support tương ứng
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.micrometer.tracing.test.autoconfigure.AutoConfigureTracing;
```

Ví dụ lựa chọn theo mục đích:

```java
@AutoConfigureMetrics
class MetricsIntegrationTest {
    // kiểm tra in-memory MeterRegistry/metrics
}

@AutoConfigureTracing
class TracingIntegrationTest {
    // kiểm tra tracing setup
}
```

Đây là **đoạn chuyển đổi định hướng**, không thuộc project Boot 3.5 bên dưới. Khi thực hiện Boot 4 phải thêm những modules liên quan, ví dụ `org.springframework.boot:spring-boot-micrometer-metrics-test` và `org.springframework.boot:spring-boot-micrometer-tracing-test` trong test scope, căn BOM chính xác; với servlet test slices, các `@WebMvcTest` imports cũng chuyển theo module Boot 4. **Không cố thêm cả annotation 3.x và 4.x trong một source set**.

Tài liệu Spring Boot 4 mô tả `@AutoConfigureMetrics` cho slice sẽ cung cấp in-memory `MeterRegistry` và `ObservationRegistry`; `@AutoConfigureTracing` cho tracing slice. Test slices vẫn không được coi là đang phát dữ liệu ra exporters ngoài hệ thống.

### 2.3. Vì sao nói “theo khả năng hỗ trợ của phiên bản”?

Thấy một bài blog cũ viết `@AutoConfigureMetrics` không có nghĩa cần thay tất cả bằng `@AutoConfigureObservability`; thấy Boot 4 dùng `@AutoConfigureTracing` cũng không có nghĩa annotation này tồn tại ở Boot 3.5. Cần kiểm tra lần lượt:

1. `spring-boot-starter-parent` / Spring Boot BOM version.
2. Artifact test tương ứng nằm trong dependency tree.
3. Package/class trên Javadoc chính xác với version.
4. Annotation đang dùng cho full context hay slice.
5. Các feature đã auto-configure/disabled theo test policy.
6. Assert đang kiểm tra registration, metric tại JVM, span tại JVM hay exporter ngoài hệ thống.

Ví dụ những lỗi compile:

```text
package org.springframework.boot.test.autoconfigure.actuate.observability does not exist

cannot find symbol: class AutoConfigureObservability

package org.springframework.boot.micrometer.metrics.test.autoconfigure does not exist
```

**Không giải quyết bằng cách đổi mỗi import ngẫu nhiên**. Cần xác nhận BOM/module version và đường migration. `@AutoConfigureObservability` của 3.x không phải API có thể giả định luôn tồn tại trong 4.x.

## 3. Observability: logging, metrics, traces và Observation khác nhau ra sao?

### 3.1. Ba trụ cột

- **Logging:** sự kiện/chi tiết do ứng dụng ghi vào log; `@AutoConfigureObservability` không tự biến mọi log thành trace/span.
- **Metrics:** số đo tổng hợp như request count, latency, error rate; Micrometer `MeterRegistry` lưu/đẩy chúng.
- **Traces:** quan hệ và thời lượng spans trong một trace; Micrometer Tracing `Tracer`/tracing handlers và backend như Zipkin/OTLP là những thành phần khác.

`Observation` (Micrometer Observation API) cung cấp một abstraction cho instrumentation có thể dẫn tới metrics và traces nếu có handlers tương ứng:

```text
Business call / ApplicationEvent
          |
          v
Observation.createNotStarted("orders.created.event", registry)
          |
       start / scope
          |
     business handler
          |
      stop / error
          |
       ObservationRegistry
          |
       ObservationHandlers
        /          \
       v            v
Meter handler    Tracing handler
       |            |
     Timer         Span
       |            |
SimpleMeterRegistry  no-op/test tracer or actual reporter
       |
assert in JVM
```

Tạo Observation nhưng **không có ObservationHandler** thường không sinh ra timer hoặc spans hữu ích. Ngược lại, một `SimpleMeterRegistry` bean có mặt không tự chứng minh custom Observation đã được xử lý và tạo timer.

### 3.2. Các loại dữ liệu cần phân biệt

| API | Chức năng | Test bằng gì? |
| --- | --- | --- |
| `ObservationRegistry` | Quản lý observation lifecycle/handlers/current context | Bean wiring, handler invocation |
| `Observation` | start/stop/error, tên/tags/scope | Recorded event, error context |
| `MeterRegistry` | Meters như Timer, Counter, Gauge | `find(name).timer()`, count/tags |
| `SimpleMeterRegistry` | Metrics in-memory | Unit/integration assertions, không exporter |
| `Tracer` | Tạo/current span, trace IDs | In-memory/test span handler hoặc fake exporter |
| `ObservationHandler` | Xử lý start/stop/events | Test handlers nhận đúng lifecycle |
| `@Observed` | Annotation instrumentation qua aspect | Cần annotation scanning/AOP config riêng |
| `ApplicationEventPublisher` | Phát Spring application events | Listener được invoke; không tự có Observation |

### 3.3. Low vs high cardinality key values

Micrometer phân biệt:

- **Low cardinality:** tập giá trị nhỏ/bị chặn, ví dụ `event.type=created`, `result=success/failure`. Dùng được làm metric tags.
- **High cardinality:** order ID, user ID, request ID hoặc URI đầy đủ. Thường chỉ thuộc trace context, **không** nên thành metric tag vì tạo hàng triệu time series và lộ identifiers.
- Không đưa token, raw PII, passwords hoặc thông tin nhạy cảm vào trace/log/tags không cần thiết.

Ví dụ:

```java
Observation.createNotStarted("orders.created.event", registry)
        .lowCardinalityKeyValue("event.type", "created")
        .highCardinalityKeyValue("order.id", orderId)
        .observe(() -> businessWork());
```

Đây là snippet với biến `registry`/`orderId` và `businessWork()` giả định, không phải file riêng. `orders.created.event` có thể sinh ra Timer cùng tên nếu metric handler được đăng ký; `order.id` không nên xuất hiện trong Timer ID tags.

### 3.4. Tên metric khi có Observation

`DefaultMeterObservationHandler` thường tạo timer khi observation **stop**, tên meter khớp tên observation:

```text
Observation name: orders.created.event
low cardinality: event.type=created
high cardinality: order.id=O-123

Timer name: orders.created.event
Timer tag event.type: created
Timer tag order.id: [absent]
Timer count: 1 after one completed observation
```

Trên registry đã chứa meters từ những tests trước, không assert total count bằng 1. Đo `before`/`after` hoặc dùng registry mới tạo per test.

## 4. `@AutoConfigureObservability` làm gì trong Spring Boot 3.x?

Theo Spring Boot 3.5 reference và Javadoc:

- `@SpringBootTest` không tự kích hoạt toàn bộ reporting/export của mọi metric registry/tracer dù classpath có exporters. In-memory meter registries có xử lý riêng.
- Với **sliced tests** như `@WebMvcTest`, `@AutoConfigureObservability` auto-configure một `ObservationRegistry` và một **in-memory `MeterRegistry`**; tài liệu cũng nói tới **no-op Tracer** trong phạm vi tracing slice.
- **Không hỗ trợ export dữ liệu thực ra ngoài từ sliced tests** chỉ bằng annotation đó.
- Khi integration test cần xác nhận external metrics/tracing exporter thực, hãy bật phần reporting tương ứng ở full context, dùng test-only backend và assert việc nhận dữ liệu.
- Annotation không tự tạo business observations: vẫn cần instrumentation code/framework instrumentation hoặc `@Observed` annotation scanning.
- Sự có mặt của `Tracer` không phải bằng chứng một trace đã được gửi tới collector.
- Context/test policy giữa versions có thay đổi; không diễn giải annotation này là cờ “everything on” bất biến.

### 4.1. Các attributes `metrics` và `tracing` ở Boot 3.5

Javadoc:

```java
@AutoConfigureObservability(
        metrics = true,
        tracing = true)
```

Hai attributes có default `true` và mô tả liên quan đến việc **report ra external systems trong test**. Không đọc chúng như một công tắc duy nhất quyết định có `ObservationRegistry` bean hay không. Đặc biệt trên slice, documentation nêu in-memory/no-op support và **không support data exporting** bằng annotation này.

Để giữ các tests ổn định, ví dụ runnable bên dưới chỉ dựa vào in-memory meter observation; không cấu hình external collector. Nếu muốn test exporter thật, đó là một suite tích hợp khác, có collector/container endpoint kiểm soát được.

### 4.2. Tại sao test bằng `@WebMvcTest` không giống full context?

`@WebMvcTest(OrdersController.class)` chỉ nạp phần MVC, một số converters/filters/advice, không nạp mọi `@Service`. Muốn controller dùng `OrderService`, ta đặt `@MockitoBean`, không đợi service thật từ component scan.

Khi gắn `@AutoConfigureObservability` vào slice, nhận được in-memory registry phù hợp để kiểm tra cấu hình hoặc observation nhẹ trong JVM; điều này **không** chứng minh production service đang có handlers/exporters/trace propagation giống full app.

### 4.3. Khi nào không cần annotation?

- Pure unit test service/listener với `ObservationRegistry.create()` và một manual `ObservationHandler`.
- Test domain logic không có yêu cầu metrics/traces: không cần mở exporter.
- Test tích hợp chỉ cần phát/nhận Spring `ApplicationEvent` mà không assert observability: kiểm tra event wiring, không cần enable observability reporting.
- Test cần timer cụ thể nhưng Boot version chưa hỗ trợ annotation: dùng một **test-only in-memory setup** rõ ràng, không ép nâng Boot chỉ vì một annotation.
- Test backend OTLP/Zipkin thật: cần full integration context với trace/exporter config, không dựa vào slice no-op tracer.

## 5. Quy tắc test events và observability

Một `ApplicationEvent` là một thông báo trong cùng ApplicationContext:

```text
OrderService.create(orderId)
       |
       v
ApplicationEventPublisher.publishEvent(OrderCreatedEvent)
       |
       v
@EventListener OrderCreatedListener.on(event)
       |
       v
ObservationRegistry / timers / trace handlers
```

Với `@EventListener` thông thường và `ApplicationEventMulticaster` mặc định của Spring, listeners chạy **đồng bộ** trong publisher thread. Nếu ứng dụng cấu hình async multicaster hoặc `@Async` trên listener, execution chuyển sang thread khác; phải dùng bounded waits và cân nhắc context propagation.

Các hợp đồng khác nhau:

1. Publish call được thực hiện với payload hợp lệ.
2. Listener được register và được gọi.
3. Business side effect của listener đúng.
4. Listener tạo observation với name/tags đúng và gọi start/stop.
5. Metric handler tạo timer và count chính xác.
6. Tracing handler tạo span nếu có tracing được cấu hình.
7. Exporter ngoài môi trường nhận dữ liệu nếu đó là mục tiêu.
8. Event propagation across threads/services là yêu cầu riêng.

**Không kết luận “event được xử lý” chỉ vì metric count tăng** nếu business method có thể fail; nếu exception thì observation.error() cũng cần được record. Ngược lại, test event xanh không chứng minh timer hoặc span đã tồn tại.

## 6. Project mẫu Spring Boot 3.5.0 / Java 17 / Maven

Mẫu này minh họa **Spring application event** được listener tiếp nhận, listener tạo Micrometer Observation, và cả unit tests/full-context tests/slice tests. Không cần Redis, database, Docker hay external collector.

### 6.1. Cấu trúc project

```text
observability-test-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/obs/
    │   ├── ObservabilityLabApplication.java
    │   ├── OrderCreatedEvent.java
    │   ├── OrderService.java
    │   ├── OrderCreatedListener.java
    │   └── OrdersController.java
    └── test/java/com/example/obs/
        ├── OrderServiceUnitTest.java
        ├── OrderCreatedListenerUnitTest.java
        ├── OrdersObservabilityIntegrationTest.java
        └── OrdersControllerSliceTest.java
```

Tổng cộng **9 JUnit `@Test` methods**: 2 OrderService unit, 2 listener/Micrometer unit, 3 `@SpringBootTest` integration, 2 `@WebMvcTest` slice. Mọi file Java thuộc package `com.example.obs`; public types đặt trong file đúng tên.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>observability-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao ba dependencies?**

- `starter-web`: `@RestController` và `MockMvc`-compatible MVC stack.
- `starter-actuator`: Spring Boot observability, Micrometer Observation và meter registry auto-configuration.
- `starter-test`: JUnit Jupiter/AssertJ/Mockito/`@WebMvcTest`/`@AutoConfigureObservability` trong Boot 3.5 test support.

Không thêm Prometheus, OTLP hoặc Zipkin exporter: mục tiêu test là **in-memory instrumentation**, không network export. Giữ Spring Boot version cố định trong ví dụ; với Boot 4 phải thay test annotations/modules như phần 2.

### 6.3. `ObservabilityLabApplication.java`

```java
// src/main/java/com/example/obs/ObservabilityLabApplication.java
package com.example.obs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObservabilityLabApplication.class, args);
    }
}
```

`@SpringBootTest` tự tìm `@SpringBootApplication` từ package của tests. Không cần ghi server port cố định: full test mặc định dùng mock web environment và `@WebMvcTest` cũng không chạy embedded HTTP server.

### 6.4. `OrderCreatedEvent.java`

```java
// src/main/java/com/example/obs/OrderCreatedEvent.java
package com.example.obs;

public record OrderCreatedEvent(String orderId) {
}
```

Java record là payload sự kiện. Nó không kế thừa `ApplicationEvent` nhưng Spring Framework cho phép publish arbitrary objects qua `ApplicationEventPublisher`; `@EventListener` có thể nhận kiểu record.

Tài liệu này không yêu cầu serialization/network; đây là **in-process Spring event**. Nếu cần Kafka/RabbitMQ/event bus giữa processes, phải có broker integration tests riêng.

### 6.5. `OrderService.java`

```java
// src/main/java/com/example/obs/OrderService.java
package com.example.obs;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public String create(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        publisher.publishEvent(new OrderCreatedEvent(orderId));
        return "created:" + orderId;
    }
}
```

`OrderService` chỉ validate và publish event. Một unit test verify payload; integration test sẽ chứng minh Spring đã đăng ký listener và tạo observation.

### 6.6. `OrderCreatedListener.java`

```java
// src/main/java/com/example/obs/OrderCreatedListener.java
package com.example.obs;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final ObservationRegistry observations;
    private final AtomicInteger handled = new AtomicInteger();
    private final AtomicReference<String> latestOrderId =
            new AtomicReference<>();

    public OrderCreatedListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @EventListener
    public void on(OrderCreatedEvent event) {
        Observation.createNotStarted(
                        "orders.created.event", observations)
                .lowCardinalityKeyValue("event.type", "created")
                .highCardinalityKeyValue(
                        "order.id", event.orderId())
                .observe(() -> {
                    latestOrderId.set(event.orderId());
                    handled.incrementAndGet();
                });
    }

    public int handledCount() {
        return handled.get();
    }

    public String latestOrderId() {
        return latestOrderId.get();
    }
}
```

**Giải thích kỹ:**

- `ObservationRegistry` được tiêm từ Spring Boot actuator trong full context.
- `@EventListener` nhận `OrderCreatedEvent` từ `OrderService`.
- `Observation.createNotStarted` tạo observation với tên ổn định.
- `lowCardinalityKeyValue("event.type","created")` được phép thành metric tag.
- `highCardinalityKeyValue("order.id", event.orderId())` không nên thành metric tag; đây là dimension độ phân giải cao, nên production cần xem policy PII/trace retention.
- `observe(Runnable)` tự bao lifecycle start/stop và xử lý exceptions theo API Micrometer; code demo giữ handler đơn giản.
- `AtomicInteger` và `AtomicReference` là dấu hiệu quan sát được giữa các tests, **không** thay database/business persistence.
- Với default Spring multicaster đồng bộ, listener hoàn thành trước khi `publishEvent` trả về; nếu đổi sang `@Async` phải dùng bounded await và đảm bảo thread context propagation.

### 6.7. `OrdersController.java`

```java
// src/main/java/com/example/obs/OrdersController.java
package com.example.obs;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    private final OrderService service;

    public OrdersController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/{id}")
    public String create(@PathVariable String id) {
        return service.create(id);
    }
}
```

Controller phục vụ slice test minh họa. Không bật security/authentication trong demo; production endpoints xử lý đơn hàng cần authentication và authorization riêng. `@AutoConfigureObservability` không phải security control.

## 7. Unit test: kiểm tra service publish Spring event

### 7.1. `OrderServiceUnitTest.java`

```java
// src/test/java/com/example/obs/OrderServiceUnitTest.java
package com.example.obs;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderServiceUnitTest {

    @Test
    void validOrderPublishesExpectedEvent() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        OrderService service = new OrderService(publisher);

        assertThat(service.create("O-123"))
                .isEqualTo("created:O-123");

        verify(publisher).publishEvent(
                new OrderCreatedEvent("O-123"));
    }

    @Test
    void blankOrderIdDoesNotPublish() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        OrderService service = new OrderService(publisher);

        assertThatThrownBy(() -> service.create(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId must not be blank");

        verifyNoInteractions(publisher);
    }
}
```

Hai tests **không load Spring context**. Chúng bảo vệ validate/publish call, nhưng không chứng minh Spring listener được register hoặc có Metric Timer.

## 8. Unit test: Micrometer registry và metric handler hoàn toàn in-memory

Một lựa chọn mạnh, **không phụ thuộc annotation Spring Boot 3.x hay 4.x**, là tự tạo `ObservationRegistry` + `SimpleMeterRegistry` cho pure unit test. Cấu hình `DefaultMeterObservationHandler` để có bằng chứng deterministic rằng Observation tạo Timer.

### 8.1. `OrderCreatedListenerUnitTest.java`

```java
// src/test/java/com/example/obs/OrderCreatedListenerUnitTest.java
package com.example.obs;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderCreatedListenerUnitTest {

    @Test
    void eventCreatesTimerInManualInMemoryRegistry() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations =
                    ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(
                            new DefaultMeterObservationHandler(meters));

            OrderCreatedListener listener =
                    new OrderCreatedListener(observations);
            listener.on(new OrderCreatedEvent("O-123"));

            assertThat(listener.handledCount()).isEqualTo(1);
            assertThat(listener.latestOrderId())
                    .isEqualTo("O-123");

            Timer timer = meters.find("orders.created.event")
                    .tag("event.type", "created")
                    .timer();
            assertThat(timer).isNotNull();
            assertThat(timer.count()).isEqualTo(1);
        }
        finally {
            meters.close();
        }
    }

    @Test
    void highCardinalityOrderIdIsNotMeterTag() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry observations =
                    ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(
                            new DefaultMeterObservationHandler(meters));

            OrderCreatedListener listener =
                    new OrderCreatedListener(observations);
            listener.on(new OrderCreatedEvent("O-SECRET-123"));

            Timer timer = meters.find("orders.created.event")
                    .tag("event.type", "created")
                    .timer();
            assertThat(timer).isNotNull();
            assertThat(timer.getId().getTag("order.id")).isNull();
        }
        finally {
            meters.close();
        }
    }
}
```

**Vì sao test này đáng tin?**

- `ObservationRegistry.create()` và `SimpleMeterRegistry` thuộc Micrometer, không phụ thuộc Spring Boot test autoconfiguration.
- `DefaultMeterObservationHandler` nhận `start/stop` từ Observation và tạo Timer.
- `Timer.count()` bằng 1 vì mỗi test tự tạo registry mới, không chịu ảnh hưởng context cache.
- `order.id` là high-cardinality key, không xuất hiện trong meter tags.
- `SimpleMeterRegistry.close()` dọn resources thuộc unit test.
- Hai tests không chứng minh Boot tự thêm handler hoặc exporter. Đó là mục tiêu của full-context integration tests tiếp theo.

**Chú ý API/version:** `DefaultMeterObservationHandler` thuộc package `io.micrometer.core.instrument.observation`. Dự án dùng Micrometer versions do Spring Boot 3.5 BOM quản lý. Nếu project khác dùng Micrometer major khác, đối chiếu Javadoc thay vì copy mù.

## 9. Full-context test Spring Boot 3.5: `@AutoConfigureObservability`

### 9.1. `OrdersObservabilityIntegrationTest.java`

```java
// src/test/java/com/example/obs/OrdersObservabilityIntegrationTest.java
package com.example.obs;

import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureObservability
class OrdersObservabilityIntegrationTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderCreatedListener listener;

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @Test
    void fullContextProvidesObservationAndMeterRegistries() {
        assertThat(observations).isNotNull();
        assertThat(meters).isNotNull();
    }

    @Test
    void springEventProducesMetricAfterHandlerCompletes() {
        int handledBefore = listener.handledCount();
        Timer previous = meters.find("orders.created.event")
                .tag("event.type", "created").timer();
        long countBefore =
                previous == null ? 0 : previous.count();

        String orderId = "O-" + UUID.randomUUID();
        String response = service.create(orderId);

        assertThat(response).isEqualTo("created:" + orderId);
        assertThat(listener.handledCount())
                .isEqualTo(handledBefore + 1);
        assertThat(listener.latestOrderId())
                .isEqualTo(orderId);

        Timer after = meters.find("orders.created.event")
                .tag("event.type", "created").timer();
        assertThat(after).isNotNull();
        assertThat(after.count()).isEqualTo(countBefore + 1);
    }

    @Test
    void orderIdDoesNotLeakIntoTimerTags() {
        service.create("O-" + UUID.randomUUID());

        Timer timer = meters.find("orders.created.event")
                .tag("event.type", "created").timer();

        assertThat(timer).isNotNull();
        assertThat(timer.getId().getTag("order.id")).isNull();
    }
}
```

**Đây là 3 integration test methods**.

- Test thứ nhất chỉ bảo vệ bean wiring.
- Test thứ hai đi qua `OrderService` → Spring event system → `@EventListener` → Micrometer Observation → in-memory metric handler. Nó kiểm tra **delta** timer count thay vì hard-code count=1 trong registry đã được cache.
- Test thứ ba bảo vệ cardinality/security contract: `order.id` không trở thành metric tag.
- `@AutoConfigureObservability` trong Boot 3.5 cho phép kiểm tra các metrics của observation trong test; **không** chứng minh trace được gửi tới Zipkin/OTLP.
- Không dùng `Thread.sleep`: listener đồng bộ theo default event multicaster. Nếu production cấu hình async listener, đây phải là test async riêng với timeout.
- Không assert Timer totalTime/max bằng một số millisecond chính xác: CI scheduling và JVM warmup làm duration thay đổi.
- `@SpringBootTest` mặc định không khởi động real HTTP server; đó không phải e2e test qua network.
- Dự án mẫu không cấu hình exporter; tất cả test có thể chạy offline sau khi Maven dependencies được tải.

### 9.2. Vì sao dùng count delta?

Spring TestContext có thể cache `ApplicationContext`, và registry meters có thể chứa dữ liệu từ những test methods khác. Một assertion:

```java
assertThat(meters.get("orders.created.event")
        .timer().count()).isEqualTo(1);
```

có nguy cơ fail theo thứ tự chạy. Bằng cách đọc `countBefore` và khẳng định đúng một event vừa phát, test bảo vệ hành vi của chính lời gọi đó. Nếu listener chạy async, cần bounded polling khi đo delta, không gọi assert ngay lập tức.

## 10. Test slice: `@WebMvcTest` và `@AutoConfigureObservability`

### 10.1. `OrdersControllerSliceTest.java`

```java
// src/test/java/com/example/obs/OrdersControllerSliceTest.java
package com.example.obs;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrdersController.class)
@AutoConfigureObservability
class OrdersControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObservationRegistry observations;

    @Autowired
    MeterRegistry meters;

    @MockitoBean
    OrderService service;

    @Test
    void slicedContextHasTestObservationInfrastructure() {
        assertThat(observations).isNotNull();
        assertThat(meters).isNotNull();
    }

    @Test
    void controllerCallsMockWithoutLoadingRealEventListener()
            throws Exception {
        given(service.create("O-7"))
                .willReturn("created:O-7");

        mvc.perform(post("/orders/O-7"))
                .andExpect(status().isOk())
                .andExpect(content().string("created:O-7"));

        verify(service).create("O-7");
    }
}
```

**Đây là 2 slice test methods**.

- `@WebMvcTest` chỉ load MVC slice; `OrderCreatedListener` thông thường không được scan như full application component.
- `@MockitoBean` thay `OrderService` bằng Mockito bean để controller test không publish một event thật.
- `@AutoConfigureObservability` bổ sung in-memory `MeterRegistry` và `ObservationRegistry` theo Spring Boot 3.5 docs.
- Test có `ObservationRegistry` không có nghĩa có tracing reporter hoặc HTTP metrics exporter. Sliced tests không hỗ trợ data export ngoài hệ thống bằng annotation này.
- `MockMvc` chạy trong mock Servlet environment, **không** khởi động embedded server lắng nghe port thật.
- Nếu muốn kiểm tra sự kiện xử lý/Observation thật, dùng full-context test phần 9, không phải controller slice với mock service.

## 11. Tổng hợp test cases và lệnh chạy

| Test class | `@Test` methods | Có Spring context? | Điều bảo vệ |
| --- | ---: | --- | --- |
| `OrderServiceUnitTest` | 2 | Không | Validate/publish event call |
| `OrderCreatedListenerUnitTest` | 2 | Không | Observation → Timer trong JVM, high-cardinality |
| `OrdersObservabilityIntegrationTest` | 3 | Full context | Event listener, metric registration, count delta |
| `OrdersControllerSliceTest` | 2 | MVC slice | Registry trong slice, controller→mock service |
| **Tổng** | **9** | Có cả unit/full/slice | Ranh giới rõ ràng |

### 11.1. Chạy riêng từng nhóm

```bash
java -version
mvn -version

# Unit tests không cần Spring context:
mvn -B -ntp -Dtest=OrderServiceUnitTest,OrderCreatedListenerUnitTest test

# Full-context observability:
mvn -B -ntp -Dtest=OrdersObservabilityIntegrationTest test

# MVC slice với @AutoConfigureObservability:
mvn -B -ntp -Dtest=OrdersControllerSliceTest test

# Cả 9 tests:
mvn -B -ntp test
```

**Kỳ vọng theo source:** các tests chạy không cần Docker hoặc exporter. Đây là lệnh để tự thực thi; **không phải báo cáo rằng project đã được compile/executed** trong môi trường soạn tài liệu. Stdout Maven/Spring logs có thể khác, không đưa một log giả “BUILD SUCCESS” làm bằng chứng.

### 11.2. Triệu chứng khi thiếu dependency

```text
error: package io.micrometer.observation does not exist
error: package org.springframework.boot.test.autoconfigure.actuate.observability does not exist
No qualifying bean of type 'io.micrometer.observation.ObservationRegistry'
No qualifying bean of type 'io.micrometer.core.instrument.MeterRegistry'
```

Phân loại lần lượt:

1. Micrometer/Actuator/starter có trên classpath hay không?
2. Parent/BOM đúng Boot version chưa?
3. Test starter/module đúng version chưa?
4. Import annotation dùng 3.5 hay 4.x?
5. Test slice có thêm annotation đúng không?
6. Test đã load main app hay chỉ slice?
7. Có explicit `@ImportAutoConfiguration(exclude=...)` hoặc custom context loại Observation auto-config không?
8. Có registry custom/no-op/handler thiếu không?

Không “chữa” bằng cách xóa assertions chỉ để compiler pass; cần khớp semantics thực sự mong muốn.

## 12. Khi nào cần test tracing thật?

### 12.1. No-op tracer không phải export test

Trong Boot 3.5, sliced test dùng `@AutoConfigureObservability` có thể có no-op `Tracer`. Điều này giúp code cần tracer hoạt động trong context nhưng không tạo spans có thể xuất ra collector thật.

Nếu test chỉ cần bảo vệ event handler **gọi Observation** và metric tags, in-memory MeterRegistry thường đủ. Nếu test cần bảo vệ **propagation và reporting**, dùng dedicated full-context test với test tracer/exporter:

- OpenTelemetry in-memory exporter hoặc collector test-only.
- Một `SpanExporter` test implementation / `SpanHandler` kiểm soát được.
- IDs, parent/child relationships, attributes và error status.
- Sampling config/test parent context rõ.
- Không gửi dữ liệu sang production OTLP/Zipkin endpoints.
- Bounded await nếu export batch bất đồng bộ.
- Cleanup resources và không giữ test registry giữa unrelated suites.

### 12.2. Không chỉ nhìn số lượng spans bằng 0 rồi kết luận code sai

Một trace không xuất hiện có thể do sampling, no-op tracer, bị disable exporter trong test, async batch chưa flush, parent context mất qua thread boundary, hoặc observation chưa có tracer handler. Điều tra mỗi bước trước khi thay application code.

### 12.3. Propagation khi Spring event bất đồng bộ

Default Spring `@EventListener` thường đồng bộ. Nếu dùng `@Async` hoặc custom `ApplicationEventMulticaster` với executor, span context thường không tự truyền qua mọi arbitrary ThreadLocal boundary nếu không cấu hình context propagation. Spring Boot/Micrometer có các hook để hỗ trợ tùy môi trường, nhưng cần test bằng task executor thực, traceparent/parent-child spans và đúng version.

Không lấy một unit test gọi `listener.on(event)` trực tiếp rồi tuyên bố đã kiểm chứng trace propagation qua thread pool.

## 13. `@Observed` có giống `@AutoConfigureObservability` không?

**Không.** Chúng hoạt động ở hai tầng khác nhau:

- `@AutoConfigureObservability`: annotation **cấu hình test auto-configuration** ở Boot 3.x.
- `@Observed`: Micrometer annotation **đánh dấu method instrumentation**, cần scanning/AOP support và cấu hình phù hợp.

Spring Boot 3.5 tài liệu hóa:

```properties
management.observations.annotations.enabled=true
```

Đồng thời cần dependency `org.aspectj:aspectjweaver`, thường có qua `spring-boot-starter-aop`, để hỗ trợ annotation scanning như `@Observed`, `@Timed`, `@Counted`, `@MeterTag`, `@NewSpan` tùy dependencies.

**Project runnable không dùng `@Observed`**; nó gọi `Observation.createNotStarted` trực tiếp nên không cần AspectJ. Nếu chỉ thêm `@Observed` lên method nhưng chưa bật annotation aspects, kỳ vọng metric có thể sai.

### 13.1. Instrumentation kép

Spring MVC đã có HTTP server observations. Nếu vừa dùng auto-instrumentation controller, vừa đánh `@Observed` trên cùng method, metrics/traces có thể bị trùng/đổi nghĩa. Chọn một chiến lược quan sát có chủ đích và test metric names/counts/tags để phát hiện duplication.

### 13.2. `@Timed`, Timer và Observation

`@Timed` không phải cách duy nhất để có Timer; `DefaultMeterObservationHandler` có thể tạo Timer từ Observation start/stop. Đừng cộng đồng thời một `Timer.record(...)` thủ công với Observation cùng mục đích mà không hiểu bạn đang tạo hai đo lường.

## 14. Kiểm soát exporter: test không nên gửi dữ liệu ra ngoài

### 14.1. Vì sao Boot hạn chế reporters trong tests?

Nếu mọi test tự push metrics/traces tới collector mặc định, suite có thể:

- Phụ thuộc network hoặc OTLP/Zipkin server đang sống.
- Làm đục dữ liệu monitoring thật.
- Gửi PII/test IDs hoặc HTTP URLs không mong muốn.
- Làm tăng latency và tạo flaky behavior.
- Gây cardinality explosion từ test cases/random IDs.
- Làm tests bị fail vì backend exporter dù nghiệp vụ đúng.

Vì vậy ở các test business không có yêu cầu export, dùng in-memory registry hoặc no-op tracer. Chỉ dedicated exporter integration tests mới bật reporting ra test backend, với endpoints/credentials rõ.

### 14.2. Test nào cần external collector?

| Mục đích | Cần exporter thật? | Test nên chọn |
| --- | --- | --- |
| Service tạo Observation đúng | Không | Pure Micrometer registry test |
| Metric tên/tags/count đúng | Không | `SimpleMeterRegistry` |
| Event listener được invoke | Không | SpringBootTest / event integration |
| Controller mapping/HTTP status | Không | WebMvcTest + MockMvc |
| Tracer bean được autowire | Không | Slice/no-op hoặc mock |
| Parent-child spans nội JVM | Không bắt buộc | In-memory/test span reporter |
| OTLP JSON/gRPC payload thật | Có | Full integration + test collector |
| Prometheus scrape endpoint | Có endpoint thực | Full web/management integration |
| Trace propagation cross-service | Có nhiều thành phần | Multi-service test environment |
| Production alert/dashboard correctness | Thường staging | E2E with monitoring backend |

### 14.3. `metrics=true` / `tracing=true` không đủ

Ngay cả khi test annotation có hai flags true, nếu không có exporter dependency, config/endpoint và enabled conditions thích hợp, không thể suy ra dữ liệu đã ra ngoài. Trên sliced test, documentation Boot 3.5 nói **data exporting is not supported** bằng `@AutoConfigureObservability`. Bằng chứng phải đến từ receiver/test collector hoặc in-memory observation assertions đúng phạm vi.

## 15. Migration checklist khi nâng Boot 3.5 lên 4.x

1. Đọc `pom.xml`, Gradle dependency lock và Spring Boot BOM thực tế.
2. Tìm đúng import `org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability` trong tests.
3. Với Boot 4.0, bỏ import/annotation này; không assume alias tồn tại.
4. Nếu cần metrics test support, thêm `spring-boot-micrometer-metrics-test` và dùng `@AutoConfigureMetrics` theo docs Boot 4.
5. Nếu cần tracing test support, thêm `spring-boot-micrometer-tracing-test` và dùng `@AutoConfigureTracing`.
6. Kiểm tra các imports thay đổi của `@WebMvcTest`, `@AutoConfigureMockMvc` và các test slices/module migrations khác.
7. Không giữ nguyên các attributes `metrics/tracing` của Boot 3.5 trên một annotation Boot 4 khác: API `@AutoConfigureMetrics` có attribute `export`, không phải hai flags cũ.
8. Test cả `ObservationRegistry`/`MeterRegistry` provisioning và timer behavior; đừng chỉ sửa để compiler pass.
9. Xác nhận no-op tracer và test reporter semantics theo version.
10. Kiểm tra các tracing exporter beans do tổ chức tự tạo (nếu có), tránh gửi tới collector production từ CI.
11. Test cardinality, observation names, HTTP client/server instrumentation và async propagation.
12. Dùng dependency tree và official Javadoc để kiểm tra artifact/package; không import 3.x + 4.x song song.
13. Đừng dùng `@AutoConfigureMetrics` Boot 4 rồi assume nó đồng nghĩa `@AutoConfigureObservability` Boot 3.x ở mọi trường hợp.
14. Khi nhiều modules dùng các Boot BOM khác nhau, không chỉ xem parent project mà bỏ qua module override.
15. Chạy compile-test và tests tại từng version target; không coi chỉ có Gradle refresh/Maven dependency resolve là đủ.

### 15.1. Ví dụ dependency migration (chỉ Boot 4.x)

```xml
<!-- Chỉ minh họa module Boot 4; KHÔNG thêm vào pom Boot 3.5 ở trên -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-micrometer-metrics-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-micrometer-tracing-test</artifactId>
    <scope>test</scope>
</dependency>
```

Xác minh Spring Boot 4 BOM quản lý version và các Spring test starters khác trước khi chạy. Đây là migration **snippet**, không phải một second project runnable; test sample hoàn chỉnh trong bài được pin 3.5.0.

## 16. Hướng tiếp cận không lệ thuộc annotation khi test một observation

Nếu project có nhiều modules đang chuyển tiếp Boot versions, một **Micrometer-only unit test** như `OrderCreatedListenerUnitTest` có thể duy trì ổn định hơn vì:

- Không cần biết `@AutoConfigureObservability` có tồn tại ở Boot version đó không.
- Dùng `ObservationRegistry.create()` và `DefaultMeterObservationHandler` cho test được một event.
- Dùng `SimpleMeterRegistry` in-memory, không cần collector, Docker hoặc network.
- Tên observation và low-cardinality tags được kiểm tra trực tiếp.
- Logic event handler có thể được gọi độc lập khỏi Spring container.

Nhưng test đó cũng có giới hạn:

- Không xác nhận Spring auto-configuration tạo `ObservationRegistry` bean.
- Không xác nhận `@EventListener` đã được register.
- Không xác nhận Spring Boot đã chọn MeterRegistry phù hợp.
- Không kiểm tra proxy/AOP instrumentation của `@Observed`.
- Không kiểm tra asynchronous event context propagation.
- Không xác nhận real trace/span exporter.

**Kết hợp unit và integration tests**, không dùng một loại để thay cho tất cả.

## 17. Những nhầm lẫn thường gặp và cách debug

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Cannot find `AutoConfigureObservability` | Boot 2.7 hoặc 4.x / import sai | BOM, Javadoc đúng phiên bản |
| Boot 4 test vẫn import Boot 3 path | Annotation đã bị thay đổi | Dùng Metrics/Tracing test modules Boot 4 |
| `ObservationRegistry` bean không có | Thiếu actuator/micrometer hoặc slice auto-config | Dependencies, test annotation/slice config |
| `MeterRegistry` có nhưng timer null | Observation không stop, handler thiếu | Manual handler test và observation lifecycle |
| Timer count không bằng 1 | Context cache/shared meter, extra calls | So sánh count delta hoặc isolated registry |
| High-cardinality ID xuất hiện ở meter | Gắn sai low-cardinality key | Dùng highCardinalityKeyValue, đo tags |
| Có bean Tracer nhưng không có spans | No-op tracer/sampling/reporting disabled | Test reporter/tracer config |
| Mất trace parent khi async listener | Thread context không được propagate | Executor/context propagation tests |
| Slice xanh, full integration fail | Slice chỉ có mock components | Full context đúng test scope |
| `@Observed` không tạo metric | Chưa bật annotation scanning/AOP | management.observations.annotations.enabled, aspectjweaver |
| Metrics bị đếm hai lần | Double instrumentation | Kiểm tra Observation names/handlers |
| CI test cố connect OTLP collector | Exporter/test config gây side effect | In-memory registry hoặc test-only endpoint |
| `@WebMvcTest` test không load service | Slice loại business beans | `@MockitoBean`/`@Import` có chủ đích |
| Không thấy HTTP server port | Mock web environment | Dùng RANDOM_PORT nếu cần network |
| Test chạy thành công nhưng backend không có dữ liệu | Slice không hỗ trợ export, hoặc no exporter | Separate exporter integration test |
| No class definition for Micrometer | Maven modules/BOM mismatch | dependency:tree, test classpath |
| Unknown `@AutoConfigureMetrics(metrics=...)` | Attributes khác giữa versions | Mở Javadoc của annotation đang dùng |

### 17.1. Có `ObservationRegistry` nhưng instrumentation là no-op

Kiểm tra `ObservationRegistry` có handlers nào được register không. Pure JVM registry tạo bằng `ObservationRegistry.create()` có thể giữ observation lifecycle nhưng nếu không `observationHandler(...)` thì không có metric exporter/timer; thêm `DefaultMeterObservationHandler` khi muốn test metric.

Spring Boot Actuator autoconfig có thể đăng ký handlers tùy dependencies/config. Trong `@SpringBootTest`, `@AutoConfigureObservability` cho phép test assertions tương ứng với test policy; trong slice, kiểm tra in-memory support thay vì mong real exporter.

### 17.2. Timer có trong registry nhưng sai tên/tag

`MeterRegistry.find(name)` cần đúng observation name, low-cardinality tags đúng. High-cardinality `order.id` không phải metric tag. Micrometer có thể thêm `error=none` theo handler nên test nên tìm theo một tag quan trọng hoặc kiểm tra theo `Meter.Id`, không hard-code toàn bộ tag set nếu module có common tags.

### 17.3. No-op tracer không có nghĩa application không quan sát được gì

Trong slice, một no-op Tracer giúp code cần tracer có bean mà không phát spans; cùng lúc in-memory MeterRegistry vẫn ghi metrics. Tracing và metrics reporters là hai khả năng tách biệt.

### 17.4. Assertion event count không bằng timer count

Một listener có thể xử lý nhiều events, nhưng observation có thể bị drop bởi `ObservationPredicate`, disabled name prefix, missing handler hoặc error handling. Phải so sánh hai tín hiệu trong test có cấu hình rõ, không mặc định 1 event = 1 backend span trên mọi sampler.

## 18. Test security, cardinality và độ tin cậy

### 18.1. Không gắn userId/orderId vào low-cardinality metrics

Một metric như:

```text
orders.created.event{event.type="created", order.id="O-123"}
```

với `order.id` khác nhau hàng triệu lần sẽ gây cardinality explosion. Dùng `highCardinalityKeyValue` cho IDs nếu thực sự cần trong traces, và cân nhắc mã hóa/redaction/PII policy. Trong project mẫu, unit/integration tests cố ý assert timer không có tag `order.id`.

### 18.2. Không test exporter bằng production secrets

Các test OTLP/Zipkin/Prometheus cần collector test-only, credentials riêng hoặc in-memory span exporter. CI không được gửi trace/meter có test data nhạy cảm sang production collector. Không nhầm một biến môi trường exporter có trong CI với việc backend nhận dữ liệu đúng.

### 18.3. Async events và thời gian

Nếu `@Async` trên event listener:

- `ApplicationEventPublisher.publishEvent` có thể trả trước khi listener xử lý xong.
- Test phải chờ bounded latch/queue/condition, không fixed sleep.
- Observation context/parent span cần propagation qua executor.
- Không dùng `@Transactional` của test method để suy ra rollback của listener thread.
- Error có thể được chuyển tới async exception handler, không được throw trở lại publisher.
- Tracing sampling có thể làm số spans không bằng số events; test policy cụ thể.
- Context cache và test teardown phải dừng worker threads khi test kết thúc.

### 18.4. Event không phải message broker

`@EventListener` trong demo nhận Spring in-process events. Nếu muốn test Kafka/RabbitMQ hoặc distributed outbox, phải dùng broker service/testcontainers và kiểm tra delivery semantics, retries, dead letters, idempotency. `@AutoConfigureObservability` chỉ ảnh hưởng observability auto-configuration, **không** biến `ApplicationEvent` thành Kafka message.

## 19. Ma trận test nên có cho sản phẩm thực

| Mục tiêu | Unit | Full context | Slice | Dedicated external integration |
| --- | --- | --- | --- | --- |
| Event payload đúng | Có | Có thể | Không cần | Khi qua broker |
| Listener business logic | Có | Có | Thường không | Khi có side effects |
| Observation name/tags | Manual Micrometer | Có | Có thể | Không cần |
| Meter Timer count | SimpleMeterRegistry | Có | In-memory nếu cần | Không cần |
| Meter exporter end-to-end | Không | Có config test | Không hỗ trợ chỉ qua slice | **Có** |
| Span parent-child | Test tracer | Full tracing config | No-op không đủ | Khi cần propagation |
| HTTP controller mapping | Không cần | Có thể | **Có** | Khi cần network |
| Trace/exporter error handling | Không | Partial | Không | **Có** |
| Upgrade Boot 3→4 compatibility | Compile-time check | Context test | Slice import check | Build matrix CI |
| Privacy/cardinality | Validate tags | Có | Có | Backend policy test |

### 19.1. CI tổ chức thế nào?

- Chạy pure unit tests nhanh, không cần network.
- Chạy Boot full-context và MVC slice tests với test policies tách biệt.
- Dedicated exporter tests có thể yêu cầu collector container, port/network và credentials test-only.
- Không bật exporters cho mọi `@SpringBootTest` trong suite.
- Test classpath phải pin Boot BOM/versions; không thay đổi dependency phiên bản ngầm qua transitive imports.
- Nếu CI dùng nhiều Boot major versions, chạy build/test matrix tương ứng; **không compile cùng một test class chứa hai annotation package không có ở một trong các versions**.
- Báo rõ UNIT PASS, FULL CONTEXT PASS, SLICE PASS, EXPORTER PASS/FAIL và SKIPPED; đừng gọi external reporting PASS khi chỉ kiểm tra bean registry có mặt.

## 20. Checklist trước khi chốt bài test observability

- [ ] Xác nhận Spring Boot version ở build/BOM, không suy từ bài blog.
- [ ] Boot 3.0–3.5: import `@AutoConfigureObservability` đúng package.
- [ ] Boot 4.0: dùng `@AutoConfigureMetrics`/`@AutoConfigureTracing` và test modules phù hợp.
- [ ] Không trộn Boot 3.x và 4.x annotation imports trong cùng project.
- [ ] Biết mục tiêu là registry existence, timer, span, hay exporter delivery.
- [ ] Hiểu `ObservationRegistry`, `MeterRegistry`, `Tracer` có trách nhiệm khác nhau.
- [ ] Slice test chỉ kỳ vọng in-memory meters/no-op tracer theo docs; không assert external export.
- [ ] Full context test có Actuator/Micrometer dependencies đúng.
- [ ] `@Observed` annotations nếu dùng có AOP/scanning support đúng.
- [ ] Không kỳ vọng `@AutoConfigureObservability` tự instrument mọi business method.
- [ ] `@EventListener` và Micrometer Observation là hai cơ chế khác nhau.
- [ ] Event tests kiểm tra payload/handler và observation tests kiểm tra metric separately.
- [ ] Metric tags dùng low cardinality; không dùng raw orderId/userId.
- [ ] Test count từ registry cache dùng deltas hoặc registry mới per test.
- [ ] Không assert latency milliseconds bằng một con số cố định.
- [ ] External collectors khi test thật phải là test-only endpoints.
- [ ] Tracing test không lấy presence of no-op tracer làm bằng chứng span export.
- [ ] Khi async events, test bounded wait và context propagation.
- [ ] Không đưa secrets/PII vào metrics/logs/traces.
- [ ] Version migration được kiểm tra bằng compile-test và Javadoc thực.
- [ ] Code sample phân biệt snippet cho Boot4 với runnable project Boot3.5.

## 21. Bài tập thực hành

**Bài 1 — Version compatibility.** Dùng Boot 3.5 chạy `OrdersObservabilityIntegrationTest`. Thử thay annotation import bằng package Boot 4 trong một nhánh demo, quan sát compile error. Trình bày tại sao cần thay dependency và module cùng lúc.

**Bài 2 — Không có handler.** Trong `OrderCreatedListenerUnitTest`, bỏ `DefaultMeterObservationHandler` và xem Timer có còn được sinh không. Giải thích vì sao registry bean một mình không phải bằng chứng ghi metric.

**Bài 3 — High cardinality.** Chuyển `order.id` từ `highCardinalityKeyValue` sang `lowCardinalityKeyValue` trong nhánh test học tập. Quan sát meter ID tags và giải thích nguy cơ cardinality explosion; khôi phục trước khi merge.

**Bài 4 — Test full vs slice.** So sánh `OrdersObservabilityIntegrationTest` và `OrdersControllerSliceTest`: service/real event listener có mặt ở test nào? Vì sao slice chỉ kiểm tra controller + Mockito service?

**Bài 5 — Exporter.** Thêm một in-memory/test-only SpanExporter hoặc test collector và Spring Boot tracing dependencies tương ứng. Viết assertion trên span data đã export, không chỉ `Tracer` bean presence.

**Bài 6 — Async event.** Đưa `@Async` vào listener và cấu hình executor trong test context; chuyển assertions sang bounded await và test parent-span context propagation.

**Bài 7 — Spring Boot 4 migration.** Tạo một project Boot 4 riêng, thêm `spring-boot-micrometer-metrics-test`, `spring-boot-micrometer-tracing-test`, import đúng annotations. Kiểm tra test compilation, in-memory meters, no-op tracer behavior và external export limitations.

**Bài 8 — `@Observed`.** Bật `management.observations.annotations.enabled=true` và `spring-boot-starter-aop` trong một sample tách biệt; so sánh metric từ `@Observed` với Observation tự tạo, tránh double instrumentation.

**Bài 9 — Fault case.** Làm event listener throw một exception; dùng `Observation.error(...)`/try-finally theo API và kiểm tra error tag/status mà không dựa vào string log chứa secret.

**Bài 10 — Dependency tree.** Chạy `mvn dependency:tree` rồi chỉ ra module nào cung cấp `@AutoConfigureObservability` trong Boot3.5 và vì sao module đó khác Boot4.

## 22. Câu hỏi tự kiểm tra

**1.** Spring Boot 3.5 có `@AutoConfigureObservability` không?  
**Đáp án:** Có, trong test autoconfigure package của Spring Boot, được giới thiệu từ Boot 3.0.

**2.** Annotation `@AutoConfigureObservability` đó có dùng nguyên xi trong Boot 4.0 không?  
**Đáp án:** Không. Boot 4.0 tách test support thành `@AutoConfigureMetrics` và `@AutoConfigureTracing` với modules/packages riêng.

**3.** Có `ObservationRegistry` nghĩa là chắc chắn có Timer không?  
**Đáp án:** Không. Cần Observation được start/stop và metric handler phù hợp.

**4.** Có `MeterRegistry` nghĩa là metrics đã export tới backend thật chưa?  
**Đáp án:** Không; `SimpleMeterRegistry` là in-memory, không tự có exporter network.

**5.** Có `Tracer` trong sliced test nghĩa là đã tạo và xuất spans chưa?  
**Đáp án:** Không; Boot 3.5 có thể cung cấp no-op tracer trong slice.

**6.** `@WebMvcTest` có tự load mọi `@Service`/`@EventListener` không?  
**Đáp án:** Không; slice cần mock hoặc import dependencies có chủ đích.

**7.** `@EventListener` có tự sinh metric không?  
**Đáp án:** Không. App event xử lý business; để có metric/trace còn cần instrumentation + handlers.

**8.** Vì sao không đưa order ID thành metric tag?  
**Đáp án:** Vì high-cardinality IDs tạo quá nhiều time series và có thể lộ dữ liệu nhạy cảm.

**9.** Vì sao integration test đọc countBefore?  
**Đáp án:** Để không phụ thuộc state từ Spring TestContext cache hoặc tests khác.

**10.** Vì sao không assert timer duration đúng 5ms?  
**Đáp án:** Timing phụ thuộc JVM/CPU/CI; chỉ kiểm tra duration nếu có SLA test hợp lý và measurement conditions.

**11.** `@AutoConfigureObservability` có tự bật `@Observed` AOP ở Boot 3.5 không?  
**Đáp án:** Không. Annotation scanning cần `management.observations.annotations.enabled=true` và AspectJ support.

**12.** Khi nào cần collector thật?  
**Đáp án:** Khi test contract bao gồm việc reporter gửi dữ liệu ra external backend; không phải khi chỉ assert observation/timer trong JVM.

## 23. Tài liệu tham khảo chính thức theo phiên bản

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): các mục Using Observations, Using Metrics, Using Tracing; `@AutoConfigureObservability` với sliced/full tests.
- [Spring Boot 3.5 — AutoConfigureObservability Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/actuate/observability/AutoConfigureObservability.html): package, `Since 3.0.0`, `metrics` và `tracing` attributes.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, low/high cardinality, annotation scanning.
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): `@AutoConfigureMetrics` và `@AutoConfigureTracing` trong test modules riêng.
- [Spring Boot 4.0 — AutoConfigureMetrics Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/micrometer/metrics/test/autoconfigure/AutoConfigureMetrics.html): Boot4 metrics test annotation.
- [Spring Boot 4.0 — AutoConfigureTracing Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/micrometer/tracing/test/autoconfigure/AutoConfigureTracing.html): Boot4 tracing test annotation.
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): test modules/package migration.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/1.15/observation/components.html): `DefaultMeterObservationHandler` và Timer lifecycle.
- [Micrometer — Observation API](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): `ObservationRegistry`, observation handlers.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `ApplicationEventPublisher` và `@EventListener`.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): framework observation instrumentation.
- [Spring Framework — MockitoBean Test Overrides](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean replacement trong Spring tests.

**Kết luận:** Với Spring Boot 3.0–3.5, `@AutoConfigureObservability` có giá trị khi test cần bật observability infrastructure phù hợp, đặc biệt là in-memory support trong slices. Với Boot 4.0, dùng các annotations/test modules `@AutoConfigureMetrics` và `@AutoConfigureTracing` theo mục đích. Ở mọi phiên bản, đừng đồng nhất có bean `ObservationRegistry` với có Timer, có `Tracer` với có span export, hoặc có `ApplicationEvent` với có observation. Hãy viết tests xác minh đúng boundary: event publication, handler execution, Micrometer observation lifecycle, in-memory metric tags/count, và cuối cùng exporter delivery nếu cần.