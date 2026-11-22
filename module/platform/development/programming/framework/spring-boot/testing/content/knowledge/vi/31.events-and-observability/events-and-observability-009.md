# Observation, trace context và tránh phụ thuộc exporter bên ngoài trong kiểm thử Spring Boot

## 1. Mục tiêu bài học

Khi một service Spring Boot được instrument để tạo metrics và distributed traces, kiểm thử có thể gặp một lỗi thiết kế: **JUnit test chỉ chạy được nếu bên ngoài đang có OTLP collector, Zipkin, Tempo, Jaeger hoặc một telemetry backend khác**. Điều này làm suite chậm, dễ lỗi mạng, khó cô lập nguyên nhân và đôi khi vô tình gửi dữ liệu test lên dịch vụ production.

Một ứng dụng có thể làm tốt cả ba việc dưới đây, nhưng **chúng không phải một phép kiểm tra**:

1. **Tạo Observation:** business method khởi tạo, mở scope, đánh dấu event/error và đóng observation đúng cách.
2. **Mang trace context:** parent/child spans chia sẻ trace ID, scope không rò sang request khác và context được chuyển qua executor/HTTP khi có cấu hình.
3. **Xuất dữ liệu:** exporter/reporter serialize và truyền spans/metrics tới một endpoint hoặc backend ngoài.

Bài này hướng dẫn chia tách các lớp trên để test nhanh, deterministic và **không phụ thuộc network exporter**. Phần code chính dùng **Java 17+, Spring Boot 3.5.x, Micrometer Observation, `micrometer-tracing-test`, JUnit Jupiter, AssertJ** và một in-memory `ObservationHandler`. Dự án test **không cần Docker, Internet, HTTP server hay collector**. Các ví dụ HTTP propagation/exporter phức tạp được mô tả riêng theo đúng mức độ xác minh, không bị gán nhầm thành thứ mà unit test đã chứng minh.

### 1.1. Đọc đúng ranh giới

```text
ShippingService.dispatch(shipmentId)
              |
              v
      Micrometer Observation
       start/scope/error/stop
              |
              v
       ObservationRegistry
              |
     +--------+-------------+
     |                      |
 test ObservationHandler   tracing handler, nếu được đăng ký
 (in-memory recorder)       |
                            v
                         Tracer/Span
                            |
                      exporter, nếu có
                            |
                        OTLP/Zipkin
                            |
                    collector/remote backend
```

Chỉ tạo `ObservationRegistry` **không tự sinh một span có traceId**. Cần một `ObservationHandler` thuộc tracing integration, hoặc phải dùng trực tiếp một `Tracer`. Tương tự, có `Tracer` không tự chứng minh span đã được exporter gửi thành công.

## 2. Các khái niệm cốt lõi

| Khái niệm | Vai trò | Test nên kiểm chứng |
|---|---|---|
| `Observation` | Lifecycle của một công việc | `start`, `openScope`, `event`, `error`, `stop` |
| `ObservationRegistry` | Registry chứa configuration, handlers, predicates/conventions | Đăng ký đúng handler và current observation trong scope |
| `ObservationHandler` | Nhận callback lúc lifecycle thay đổi | Ghi đúng tên, outcome, parent, exception |
| `Observation.Context` | Dữ liệu/tags/parent liên kết observation | Low/high-cardinality, tên và error |
| `Tracer` | Tạo/current/close spans | `currentSpan()`, parent span, ID |
| `Span` | Đơn vị trace riêng, có trace ID/span ID | Child cùng trace ID nhưng span ID khác |
| `traceparent` | W3C HTTP distributed trace context | Header thực trong outbound HTTP request |
| `ContextSnapshot` | Micrometer Context Propagation snapshot | Khôi phục context ở thread boundary |
| `ContextPropagatingTaskDecorator` | Bọc task để chuyển context | Worker đọc được parent, cleanup đúng |
| `SpanExporter` | Đẩy spans ra hệ thống khác | Fake/in-memory reporter hoặc local protocol stub |
| `MeterRegistry` | Lưu/xuất metrics | Timer/counter/low-cardinality labels |
| MDC | Dữ liệu log correlation theo thread | `traceId` nếu đúng tracing integration đã cấu hình |

**Phân biệt hai họ công cụ:** `Micrometer Observation` là abstraction cho metrics/tracing và vòng đời công việc; `Micrometer Tracing` là API `Tracer`, `Span`, scope và propagation. Observation có thể chạy mà không có tracer, và test trace context có thể chạy mà không gửi span đi đâu.

### 2.1. Logging, metrics, tracing khác nhau

Log giúp mô tả sự kiện cụ thể; metric là số liệu tổng hợp; trace cho biết đường đi qua spans và services. Một trace ID xuất hiện trong log **chỉ là correlation**, không phải bằng chứng span đã được lấy mẫu, flush và lưu thành công ở collector.

Một đơn hàng tạo thành công có thể được instrument với:
- Observation name: `shipment.dispatch` — ổn định.
- Low-card tag: `component=shipping`, `outcome=success` hoặc `failure`.
- High-card tag: `shipment.id=SHIP-101`, nếu identifier này được phép lưu trong trace.
- Event: `shipment.accepted`, `inventory.ready`.
- Error: `IllegalStateException` nếu reserve inventory fail.

Không tạo một observation name mới cho mỗi ID, ví dụ `shipment.dispatch.SHIP-101`: điều đó có thể làm metric time series phình to và khó aggregation.

## 3. Vòng đời Observation phải được đóng đúng cách

Một flow điển hình:

```java
Observation obs = Observation
        .createNotStarted("shipment.dispatch", registry)
        .lowCardinalityKeyValue("component", "shipping")
        .highCardinalityKeyValue("shipment.id", shipmentId)
        .start();

try (Observation.Scope scope = obs.openScope()) {
    doBusinessWork();
    obs.event(Observation.Event.of("shipment.accepted"));
} catch (RuntimeException ex) {
    obs.error(ex);
    throw ex;
} finally {
    obs.stop();
}
```

Đây là **mảnh phương thức minh họa**: `registry`, `shipmentId`, `doBusinessWork()` phải được khai báo trong class thực. Dự án đầy đủ được cung cấp ở phần 8.

- `createNotStarted`: tạo observation chưa bắt đầu.
- `start()`: kích hoạt lifecycle, thường dẫn tới `ObservationHandler.onStart`.
- `openScope()`: đặt observation làm current trong phạm vi thread, cho phép nested observations nhận parent.
- `event(...)`: đánh dấu một event trong observation; không phải Spring `@EventListener`.
- `error(ex)`: báo lỗi cho các handlers (không được giả định tự xuất hiện khi exception xảy ra).
- `stop()`: hoàn tất lifecycle, cho handler `onStop`/timer/span processing.

**Đóng scope không tự thay thế stop, và stop không tự thay thế đóng scope.** Dùng `try-with-resources` cho scope, `finally` cho stop. Khi xảy ra lỗi, vẫn phải dọn current observation/trace context; nếu không một pooled thread có thể mang parent của request trước.

### 3.1. Parent/child Observation

```text
shipment.dispatch.start()
  openScope() → current = shipment.dispatch
    inventory.reserve.start()
      parent = shipment.dispatch
      openScope() → current = inventory.reserve
      close child scope
    inventory.reserve.stop()
  close parent scope
shipment.dispatch.stop()
current observation = previous value, thường null
```

Trong một registry có handlers phù hợp, `Observation.Context.getParentObservation()` có thể được dùng để assert relationship. Nhưng quan hệ **parent Observation** chưa phải bằng chứng có **parentSpanId thực**; tracing bridge/handler mới chuyển các observations thành tracing spans.

### 3.2. Error event trong nested observations

Nếu `inventory.reserve` ném exception:
1. Child `Observation.error(ex)`, rồi `stop()`.
2. Exception được ném lên parent.
3. Parent `Observation.error(ex)`, gắn `outcome=failure`, rồi `stop()`.
4. Scope được restore đúng dù exception xảy ra.

Nếu test chỉ assert exception business mà bỏ qua observation, nó chưa chứng minh instrumentation đúng. Nếu code chỉ `finally { observation.stop(); }` mà không mark error, một số tracing/metrics handlers sẽ không biết span đó lỗi.

## 4. Low cardinality và high cardinality

Micrometer hỗ trợ:
- **Low cardinality:** số giá trị có kiểm soát, dùng được cho metrics và traces. Ví dụ `component=shipping`, `outcome=success|failure`, `operation=reserve`.
- **High cardinality:** số giá trị gần như vô hạn, thường chỉ đưa vào traces. Ví dụ shipment ID, request ID, path động (có cân nhắc privacy).

Đoạn minh họa:

```java
Observation.createNotStarted("shipment.dispatch", registry)
        .lowCardinalityKeyValue("component", "shipping")
        .highCardinalityKeyValue("shipment.id", "SHIP-101");
```

Tuyệt đối tránh `shipment.id`, `customer.email`, `user.id`, URL có ID hoặc request payload như low-cardinality metric tags. Mỗi giá trị mới có thể sinh thêm time series, tăng memory/cardinality/cost. High-cardinality cũng không cấp quyền ghi PII: cần whitelist và redaction trước khi ghi vào spans hoặc logs.

### 4.1. Tên metric/observation cũng có cardinality

`http.server.requests`, `shipment.dispatch`, `inventory.reserve` là tên ổn định. Không nối trực tiếp ID của người dùng vào observation name hoặc URI template label. Với HTTP, nên tag route `/shipments/{id}` chứ không tag mỗi path `/shipments/12345` thành một metric label riêng.

### 4.2. Context propagation không phải security propagation

Một traceId là dấu vết quan sát, không phải bằng chứng authentication. HTTP header `traceparent` đến từ client có thể bị giả mạo. Baggage cũng không phải authorization token. Khi cần user/tenant information, kiểm tra authentication/permissions trước, rồi chỉ gắn metadata an toàn.

## 5. Trace ID, Span ID và scope

Một trace có thể gồm:

```text
HTTP incoming request
  traceId = same-trace
  spanId  = server-A
    shipment.dispatch
      traceId = same-trace
      spanId  = internal-B
        inventory.reserve
          traceId = same-trace
          spanId  = internal-C
```

Các chuỗi ở sơ đồ là **nhãn minh họa**, không phải W3C trace IDs hợp lệ. Trong một test thực, **không assert hard-code** một traceId/spanId do tracer sinh ngẫu nhiên.

Thay vào đó:
- `child.context().traceId()` bằng `parent.context().traceId()`.
- `child.context().spanId()` khác `parent.context().spanId()`.
- Bên trong child scope, `tracer.currentSpan()` là child.
- Khi đóng child scope, current span trở về parent.
- Khi đóng parent scope, current span trở về trạng thái cũ (thường null).
- Khi kết thúc, spans được `end()` để reporter/in-memory tracer quan sát kết quả.

### 5.1. Scope khác span lifecycle

Một `Span` có thể được tạo/start nhưng **không nằm trong scope hiện tại**. Muốn dùng nó làm current span, mở `Tracer.SpanInScope` với `tracer.withSpan(span)` (theo API Micrometer Tracing). Đóng scope không kết thúc span; vẫn cần `span.end()`.

```java
Span child = tracer.nextSpan().name("inventory.reserve").start();
try (Tracer.SpanInScope scope = tracer.withSpan(child)) {
    doWork();
} finally {
    child.end();
}
```

Đây là fragment với `tracer` và `doWork()` đã được cung cấp, không phải file độc lập. `currentSpan()` trên thread mới hoặc sau khi scope đóng **có thể null** và đó có thể là kết quả đúng.

### 5.2. Sampling không giống instrumentation

Ngay cả khi code tạo observation/span:
- Sampling có thể chọn không export trace.
- Exporter có thể bị disable.
- Collector có thể unavailable.
- Batch processor có thể chưa flush.
- Span processor có thể lọc dữ liệu.
- Handler/observation predicate có thể bỏ qua một số observations.

Vì vậy test “đã tạo observation” không được suy ra “backend nhận spans”. Nếu test kiểm tra exporter thật, set sampling có kiểm soát (ví dụ `management.tracing.sampling.probability=1.0`) và dùng fake/in-memory exporter hoặc mock HTTP endpoint. Nếu `management.tracing.enabled=false`, setting sampling 1.0 **không tự bật tracer**.

## 6. Chọn đúng mức kiểm thử

| Test cần chứng minh | Thiết lập phù hợp | Có cần exporter ngoài? |
|---|---|---|
| Business output hoặc exception | Plain JUnit/Mockito | Không |
| Observation start/stop/error/tags | `ObservationRegistry` + in-memory handler hoặc `TestObservationRegistry` | **Không** |
| Parent/child Observation | Nested scopes + `Observation.Context` | Không |
| Tracer currentSpan và parent-child IDs | `micrometer-tracing-test SimpleTracer` | **Không** |
| Spring DI/ObservationHandler auto-registration | `@SpringBootTest` + Actuator + in-memory recorder | Không |
| HTTP `traceparent` propagation | Boot-managed HTTP client + tracing bridge + local mock HTTP server | Không cần remote collector |
| OTLP export serialization | In-memory exporter/local fake collector | Không cần remote service |
| Backend hiển thị traces thật | Dedicated smoke/operations test | Có backend, không phải unit test |
| Observability overhead/performance | Benchmark/load test | Tùy mục tiêu |

Mỗi test nên có **một scope kiểm chứng**. Không thêm đủ mọi dependency APM/tracing/export vào tất cả `@SpringBootTest` chỉ để assert một tag.

## 7. Spring Boot 3.5 testing defaults và tránh export

Theo tài liệu Spring Boot 3.5:
- Với `@SpringBootTest`, các tracing reporting components **không auto-configured để báo dữ liệu ra ngoài** theo cách production; đây là cơ chế giảm side effects trong test.
- Các `MeterRegistry` không phải loại in-memory cũng không được auto-configured để export như bình thường.
- Với sliced test có `@AutoConfigureObservability`, Boot có thể cung cấp `ObservationRegistry`, in-memory MeterRegistry và **no-op Tracer**; dữ liệu không được export trong test slice chỉ nhờ annotation.
- `@AutoConfigureObservability` dùng khi thực sự cần cấu hình observability cho test; nó **không có nghĩa** tất cả spans đều có traceId thực.
- Custom `SpanExporter` hoặc reporter do ứng dụng tự tạo có thể vẫn hoạt động khi test, trừ khi thiết kế conditional/mock override phù hợp.

### 7.1. Properties được xác nhận cho Spring Boot 3.5.x

```properties
# Khi test không cần tracing thực:
management.tracing.enabled=false

# Tắt các exporter cụ thể khi dependencies của chúng hiện diện:
management.otlp.tracing.export.enabled=false
management.zipkin.tracing.export.enabled=false

# Nếu có metrics exporters, chọn policy phù hợp:
management.defaults.metrics.export.enabled=false
management.otlp.metrics.export.enabled=false
```

Các properties trên giúp giảm phụ thuộc exporter và tạo ranh giới test rõ ràng. Tuy nhiên:
- `management.tracing.enabled=false` tắt **tracing auto-configuration**, không chỉ network export; test cần real propagation **không nên** disable tracing.
- Tắt OTLP/Zipkin không tự tắt custom publisher, Datadog/Wavefront exporter hoặc một background SDK agent khác.
- Nếu exporter class không có trên classpath, nó sẽ không được tạo dù thiếu các properties.
- Spring Boot **4.x** có thể đổi package/property names; không copy property 4.x vào project 3.5 rồi suy đoán nó có hiệu lực.

### 7.2. Cách cấu hình test thay vì sửa production

- `src/test/resources/application.properties`: cờ chung cho test module.
- `@SpringBootTest(properties = "...")`: override trực tiếp cho test class.
- `@ActiveProfiles("test")`: đọc `application-test.properties`.
- `@TestConfiguration`: đăng ký test-only handler/tracer/reporter.
- `@ConditionalOnEnabledTracing`: để custom reporting components tự tắt khi tracing disabled.
- `@MockitoBean`: thay thế network adapter khi mục tiêu chỉ là verify call.
- Network policy/test sandbox: nếu yêu cầu chính thức là “tests không tạo bất kỳ outbound socket”.

**Tránh** nhét credentials OTLP production vào test profile hoặc khởi động collector cloud chỉ để suite chạy. Nếu bạn dùng `@AutoConfigureObservability` ở full context, đọc đúng phạm vi auto-config và disable exporters thật sự nếu chúng có mặt.

## 8. Project Java 17+ / Spring Boot 3.5.8 đầy đủ

Cấu trúc:

```text
build.gradle
src/main/java/com/example/observe/
    ObserveApplication.java
    ShipmentReceipt.java
    ShippingService.java
    RecordingObservationHandler.java
src/test/resources/application.properties
src/test/java/com/example/observe/
    ShippingObservationUnitTest.java
    ShippingObservationSpringTest.java
    TraceContextTest.java
```

### 8.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-tracing-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- Actuator mang Micrometer Observation infrastructure; test có thể inject `ObservationRegistry`.
- `micrometer-tracing-test` chỉ nằm ở **test scope**, có `SimpleTracer` in-memory.
- Dự án cố ý **không** thêm `opentelemetry-exporter-otlp`, `zipkin-reporter-brave` hoặc Micrometer tracing bridges vào runtime.
- **Vì không có bridge**, `ShippingService` trong project này được test như Observation, không tự sinh distributed traces. Các `TraceContextTest` là bộ kiểm thử riêng của `SimpleTracer`.
- Spring Boot BOM quản lý dependencies tương thích; đừng tùy tiện mix Micrometer 1.15 và version lệch BOM.
- Không có Servlet starter, database hay Docker.

Project cần Gradle wrapper (`gradlew`, `gradlew.bat`) có sẵn để chạy lệnh tương ứng. Tệp `build.gradle` không tự sinh wrapper.

### 8.2. Application class

Tệp `src/main/java/com/example/observe/ObserveApplication.java`:

```java
package com.example.observe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObserveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObserveApplication.class, args);
    }
}
```

### 8.3. DTO cho kết quả diagnostic

Tệp `src/main/java/com/example/observe/ShipmentReceipt.java`:

```java
package com.example.observe;

public record ShipmentReceipt(
        String shipmentId,
        boolean parentWasCurrent,
        String threadName) {
}
```

`parentWasCurrent` chỉ là **test seam**. Business DTO production thông thường không cần expose internal observability flag. Nó cho phép kiểm chứng scope mà không buộc tracing/exporter hoạt động.

### 8.4. Service thật dùng Observation API

Tệp `src/main/java/com/example/observe/ShippingService.java`:

```java
package com.example.observe;

import java.util.Objects;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final ObservationRegistry registry;

    public ShippingService(ObservationRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public ShipmentReceipt dispatch(
            String shipmentId,
            boolean inventoryRejected) {

        Objects.requireNonNull(shipmentId, "shipmentId");

        Observation outer =
                Observation.createNotStarted(
                        "shipment.dispatch", registry)
                    .lowCardinalityKeyValue("component", "shipping")
                    .highCardinalityKeyValue("shipment.id", shipmentId)
                    .start();

        try (Observation.Scope scope = outer.openScope()) {
            boolean correctlyScoped =
                    registry.getCurrentObservation() == outer;

            reserveInventory(inventoryRejected);

            outer.lowCardinalityKeyValue("outcome", "success");
            outer.event(
                    Observation.Event.of("shipment.accepted"));

            return new ShipmentReceipt(
                    shipmentId,
                    correctlyScoped,
                    Thread.currentThread().getName());
        } catch (RuntimeException ex) {
            outer.lowCardinalityKeyValue("outcome", "failure");
            outer.error(ex);
            throw ex;
        } finally {
            outer.stop();
        }
    }

    private void reserveInventory(boolean reject) {
        Observation child =
                Observation.createNotStarted(
                        "inventory.reserve", registry)
                    .lowCardinalityKeyValue(
                        "component", "inventory")
                    .start();

        try (Observation.Scope scope = child.openScope()) {
            if (reject) {
                throw new IllegalStateException(
                        "Inventory unavailable");
            }
            child.event(
                    Observation.Event.of("inventory.ready"));
        } catch (RuntimeException ex) {
            child.error(ex);
            throw ex;
        } finally {
            child.stop();
        }
    }
}
```

**Đọc đúng logic:**
- `shipment.dispatch` là outer observation, đặt tên ổn định.
- `inventory.reserve` được tạo trong scope của outer, nên có parent observation.
- `shipment.id` nằm ở high-cardinality, `component/outcome` là low-cardinality.
- Success tạo `shipment.accepted` event và stop cả child lẫn parent.
- Failure đánh dấu exception cho child và parent; `finally` luôn stop cả hai.
- `registry.getCurrentObservation()` được đọc **trong scope**, không phải sau khi scope đóng.
- Không có outbound network, tracer bridge hay exporter trong service.

### 8.5. In-memory handler ghi lại lifecycle

Tệp `src/main/java/com/example/observe/RecordingObservationHandler.java`:

```java
package com.example.observe;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

import org.springframework.stereotype.Component;

@Component
public class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    public record Entry(
            String stage,
            String name,
            String parentName,
            String outcome,
            String shipmentId,
            String errorClass,
            String eventName) {
    }

    private final ConcurrentLinkedQueue<Entry> entries =
            new ConcurrentLinkedQueue<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        add("START", context, null);
    }

    @Override
    public void onStop(Observation.Context context) {
        add("STOP", context, null);
    }

    @Override
    public void onError(Observation.Context context) {
        add("ERROR", context, null);
    }

    @Override
    public void onEvent(
            Observation.Event event,
            Observation.Context context) {
        add("EVENT", context, event.getName());
    }

    private void add(
            String stage,
            Observation.Context context,
            String eventName) {
        KeyValue outcome =
                context.getLowCardinalityKeyValue("outcome");

        KeyValue shipment =
                context.getHighCardinalityKeyValue("shipment.id");

        String parent = context.getParentObservation() == null
                ? null
                : context.getParentObservation().getName();

        entries.add(new Entry(
                stage,
                context.getName(),
                parent,
                outcome == null ? null : outcome.getValue(),
                shipment == null ? null : shipment.getValue(),
                context.getError() == null
                        ? null
                        : context.getError()
                            .getClass().getSimpleName(),
                eventName));
    }

    public List<Entry> forName(String name) {
        return entries.stream()
                .filter(e -> name.equals(e.name()))
                .toList();
    }

    public List<Entry> forNameAndStage(
            String name, String stage) {
        return forName(name).stream()
                .filter(e -> stage.equals(e.stage()))
                .toList();
    }

    public void clear() {
        entries.clear();
    }
}
```

**Vì sao không mock `ObservationRegistry`?** Mục tiêu là kiểm tra thật `start/scope/error/stop`. Một Mockito mock registry có thể không xử lý scope và handlers theo semantics thực. Dùng real registry + in-memory handler thì framework lifecycle vẫn chạy, chỉ thay **đích xuất dữ liệu** bằng một queue nội bộ.

Demo gắn recorder ở `@Component` để Spring đăng ký handler tự động qua Actuator; production không nên giữ mọi observations trong một queue không giới hạn. Với production project, nên đặt `RecordingObservationHandler` trong **test source set** hoặc `@TestConfiguration` thay vì runtime component. Ở đây class đặt cùng main sources để vừa chạy plain JUnit (manual instantiation) vừa chạy Spring integration test mà không cần hai implementation.

### 8.6. Test-only properties

Tệp `src/test/resources/application.properties`:

```properties
management.tracing.enabled=false
management.otlp.tracing.export.enabled=false
management.zipkin.tracing.export.enabled=false
management.defaults.metrics.export.enabled=false
```

Khi đang test **chỉ Observation lifecycle**, không cần tracer/exporter. Khi đổi sang test cần real trace propagation, phải **bỏ `management.tracing.enabled=false` trong test class/profile thích hợp**, tiếp tục disable exporter hoặc dùng in-memory reporter.

## 9. Plain JUnit: 5 ca không cần Spring context

Tệp `src/test/java/com/example/observe/ShippingObservationUnitTest.java`:

```java
package com.example.observe;

import io.micrometer.observation.ObservationRegistry;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingObservationUnitTest {

    private ObservationRegistry registry;
    private RecordingObservationHandler recorder;
    private ShippingService shipping;

    @BeforeEach
    void setUp() {
        registry = ObservationRegistry.create();
        recorder = new RecordingObservationHandler();

        registry.observationConfig()
                .observationHandler(recorder);

        shipping = new ShippingService(registry);
    }

    @Test
    void successRecordsLifecycleAndEvent() {
        ShipmentReceipt result =
                shipping.dispatch("SHIP-A", false);

        assertThat(result.shipmentId()).isEqualTo("SHIP-A");
        assertThat(result.parentWasCurrent()).isTrue();

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "START")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "EVENT"))
            .extracting(RecordingObservationHandler.Entry::eventName)
            .containsExactly("shipment.accepted");

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "STOP")).hasSize(1);
    }

    @Test
    void parentAndChildAreRelated() {
        shipping.dispatch("SHIP-B", false);

        var child = recorder.forNameAndStage(
                "inventory.reserve", "START").get(0);

        assertThat(child.parentName())
                .isEqualTo("shipment.dispatch");

        assertThat(registry.getCurrentObservation()).isNull();
    }

    @Test
    void tagsUseIntendedCardinality() {
        shipping.dispatch("SHIP-C", false);

        var finished = recorder.forNameAndStage(
                "shipment.dispatch", "STOP").get(0);

        assertThat(finished.outcome()).isEqualTo("success");
        assertThat(finished.shipmentId()).isEqualTo("SHIP-C");
        assertThat(finished.errorClass()).isNull();

        // outcome đọc từ low-cardinality;
        // shipmentId đọc từ high-cardinality trong recorder.
    }

    @Test
    void exceptionIsRecordedAndScopesAreClosed() {
        assertThatThrownBy(
                () -> shipping.dispatch("SHIP-D", true))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Inventory unavailable");

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "ERROR")).hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "ERROR")).hasSize(1);

        var parentStop = recorder.forNameAndStage(
                "shipment.dispatch", "STOP").get(0);

        assertThat(parentStop.outcome()).isEqualTo("failure");
        assertThat(parentStop.errorClass())
                .isEqualTo("IllegalStateException");

        assertThat(registry.getCurrentObservation()).isNull();
    }

    @Test
    void consecutiveInvocationsDoNotLeakScope() {
        shipping.dispatch("SHIP-E", false);

        assertThat(registry.getCurrentObservation()).isNull();

        shipping.dispatch("SHIP-F", false);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP")).hasSize(2);

        assertThat(registry.getCurrentObservation()).isNull();
    }
}
```

**Kết quả dự kiến** là 5 test methods kiểm tra từng phần của contract: start/stop/event, parent relationship, tag category, exception và cleanup. Không có `Thread.sleep`, không có collector host, không có random IDs cần hard-code.

### 9.1. Dùng TestObservationRegistry nếu muốn AssertJ helpers

Micrometer cung cấp `io.micrometer:micrometer-observation-test` với `TestObservationRegistry` và fluent assertions:

```groovy
testImplementation 'io.micrometer:micrometer-observation-test'
```

```java
TestObservationRegistry registry =
        TestObservationRegistry.create();

new ShippingService(registry)
        .dispatch("SHIP-T", false);
```

Đây là **fragment** (import `io.micrometer.observation.tck.TestObservationRegistry`); có thể dùng assertion API tương ứng BOM để kiểm chứng observation đã dừng/tags/error. Main project dùng custom handler tránh phụ thuộc phiên bản của fluent matcher nhưng vẫn dựa vào real Micrometer lifecycle. Không cần custom handler trong mọi ứng dụng; đây chỉ là một lựa chọn test seam minh bạch.

## 10. @SpringBootTest: Spring wiring nhưng vẫn không export network

Tệp `src/test/java/com/example/observe/ShippingObservationSpringTest.java`:

```java
package com.example.observe;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = {
        "management.tracing.enabled=false",
        "management.otlp.tracing.export.enabled=false",
        "management.zipkin.tracing.export.enabled=false"
})
class ShippingObservationSpringTest {

    @Autowired
    ShippingService shipping;

    @Autowired
    RecordingObservationHandler recorder;

    @BeforeEach
    void clearRecorder() {
        recorder.clear();
    }

    @Test
    void springRegistryNotifiesObservationHandler() {
        ShipmentReceipt result =
                shipping.dispatch("BOOT-A", false);

        assertThat(result.parentWasCurrent()).isTrue();

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP"))
            .hasSize(1);
    }

    @Test
    void exceptionIsStillObservedInSpringContext() {
        assertThatThrownBy(
                () -> shipping.dispatch("BOOT-B", true))
            .isInstanceOf(IllegalStateException.class);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "ERROR"))
            .hasSize(1);

        assertThat(recorder.forNameAndStage(
                "shipment.dispatch", "STOP"))
            .hasSize(1);
    }

    @Test
    void childIsVisibleWithoutRemoteCollector() {
        shipping.dispatch("BOOT-C", false);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "START"))
            .hasSize(1);

        assertThat(recorder.forNameAndStage(
                "inventory.reserve", "STOP"))
            .hasSize(1);
    }
}
```

Có **3 test methods** tích hợp. Chúng kiểm tra Spring inject `ObservationRegistry` vào service và tự đăng ký bean `RecordingObservationHandler` vào registry theo Actuator auto-config. Khác với plain JUnit, đây là kiểm chứng **Spring configuration/wiring**.

**Không nói quá kết quả:** Không có exporter dependencies runtime nên test này không cần collector; nhưng việc chạy thành công không chứng minh “mọi ứng dụng có custom network reporter đều không gửi traffic”. Nếu compliance yêu cầu network-zero, phải dùng network firewall/test network namespace hoặc fake các adapter có khả năng mở socket.

### 10.1. Nếu slice test không có ObservationRegistry?

Với `@WebMvcTest`, `@DataJpaTest` hoặc slice khác, `ObservationRegistry` có thể không được tạo giống full Boot context. `@AutoConfigureObservability` có thể thêm registry/no-op tracer/in-memory meter registry theo Spring Boot 3.5 docs. Nhưng một no-op `Tracer` sẽ không cung cấp “span IDs thật” để assert. Với test business logic, bạn có thể inject test `ObservationRegistry` riêng; không nhất thiết bật toàn bộ Actuator trong slice.

## 11. Test trace context không cần bridge hoặc exporter

`micrometer-tracing-test` cung cấp `SimpleTracer`, có thể tạo spans và giữ current scope trong bộ nhớ. Nó tách rời khỏi `ShippingService` ở trên, vì project cố ý không thêm production tracing bridge.

Tệp `src/test/java/com/example/observe/TraceContextTest.java`:

```java
package com.example.observe;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.test.simple.SimpleTracer;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TraceContextTest {

    @Test
    void childSharesTraceButHasDifferentSpanId() {
        SimpleTracer tracer = new SimpleTracer();

        Span parent = tracer.nextSpan()
                .name("shipment.dispatch").start();

        try (Tracer.SpanInScope parentScope =
                tracer.withSpan(parent)) {

            assertThat(tracer.currentSpan()).isSameAs(parent);

            Span child = tracer.nextSpan()
                    .name("inventory.reserve").start();

            try (Tracer.SpanInScope childScope =
                    tracer.withSpan(child)) {

                assertThat(child.context().traceId())
                    .isNotBlank()
                    .isEqualTo(parent.context().traceId());

                assertThat(child.context().spanId())
                    .isNotBlank()
                    .isNotEqualTo(parent.context().spanId());

                assertThat(tracer.currentSpan()).isSameAs(child);
            } finally {
                child.end();
            }

            assertThat(tracer.currentSpan()).isSameAs(parent);
        } finally {
            parent.end();
        }

        assertThat(tracer.currentSpan()).isNull();
    }

    @Test
    void explicitParentPreservesTraceContext() {
        SimpleTracer tracer = new SimpleTracer();

        Span parent = tracer.nextSpan().name("root").start();

        try {
            Span child = tracer.nextSpan(parent)
                    .name("child").start();

            try {
                assertThat(child.context().traceId())
                    .isEqualTo(parent.context().traceId());

                assertThat(child.context().spanId())
                    .isNotEqualTo(parent.context().spanId());
            } finally {
                child.end();
            }
        } finally {
            parent.end();
        }
    }

    @Test
    void plainExecutorDoesNotPropagateThreadLocalSpan()
            throws Exception {

        SimpleTracer tracer = new SimpleTracer();
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        Span root = tracer.nextSpan()
                .name("caller").start();

        try (Tracer.SpanInScope rootScope =
                tracer.withSpan(root)) {

            assertThat(tracer.currentSpan()).isSameAs(root);

            Future<Boolean> absent = executor.submit(
                    () -> tracer.currentSpan() == null);

            assertThat(absent.get(5, TimeUnit.SECONDS)).isTrue();

            Future<String> explicit = executor.submit(() -> {
                Span child = tracer.nextSpan(root)
                        .name("worker").start();

                try (Tracer.SpanInScope scope =
                        tracer.withSpan(child)) {
                    return child.context().traceId();
                } finally {
                    child.end();
                }
            });

            assertThat(explicit.get(5, TimeUnit.SECONDS))
                    .isEqualTo(root.context().traceId());
        } finally {
            root.end();
            executor.shutdownNow();
        }

        assertThat(tracer.currentSpan()).isNull();
    }

    @Test
    void closingNestedScopeRestoresPreviousSpan() {
        SimpleTracer tracer = new SimpleTracer();

        Span first = tracer.nextSpan().name("first").start();

        try (Tracer.SpanInScope firstScope =
                tracer.withSpan(first)) {

            Span second = tracer.nextSpan().name("second").start();

            try (Tracer.SpanInScope secondScope =
                    tracer.withSpan(second)) {
                assertThat(tracer.currentSpan()).isSameAs(second);
            } finally {
                second.end();
            }

            assertThat(tracer.currentSpan()).isSameAs(first);
        } finally {
            first.end();
        }

        assertThat(tracer.currentSpan()).isNull();
    }
}
```

Bộ test có **4 ca**. Tổng dự án là **5 unit Observation + 3 Spring integration + 4 trace context = 12 ca `@Test`**.

**Test có thể kết luận:** parent/child same trace ID, different span ID, `currentSpan` được restore khi đóng scope, và plain ExecutorService không tự chuyển ThreadLocal trace context. **Test không thể kết luận:** Observation của `ShippingService` đã sinh spans thật qua bridge, HTTP header đã được inject hoặc exporter đã gửi spans. Đó là các cấp kiểm thử khác.

### 11.1. Không hard-code trace IDs

Một test không nên viết:

```java
assertThat(tracer.currentSpan().context().traceId())
        .isEqualTo("0000000000000001");
```

Đây là **anti-pattern minh họa**: trace ID do implementation/generator tạo và có thể khác mỗi lần chạy. Hãy assert IDs không rỗng và quan hệ ID giữa parent/child như test mẫu.

### 11.2. Chuyển Span parent bằng đối tượng trong test không phải propagation production

Test `plainExecutorDoesNotPropagateThreadLocalSpan` dùng `nextSpan(root)` để minh họa tường minh parent context của một child span. Production không nên gửi một mutable `Span` object qua HTTP, Kafka hoặc RPC. Giải pháp production phải dùng:
- W3C `traceparent`/`tracestate` hoặc configured propagation format.
- `ContextSnapshot`/`ContextPropagatingTaskDecorator` với executors trong JVM.
- Reactor Context khi đi qua reactive pipelines.
- Scope restoration/cleanup trong finally.

## 12. @Async và context propagation

### 12.1. Vì sao traceId biến mất ở worker?

Micrometer Tracing thường gắn current span vào ThreadLocal trong imperative code. Khi `@Async` hoặc `ExecutorService.submit` chuyển task sang pooled worker thread, ThreadLocal context của caller **không tự đi theo**.

```text
Caller thread                 Worker thread
   currentSpan = A              currentSpan = null
   MDC traceId = A    ---->     MDC traceId = null
              nếu không có propagation
```

Một implementation sai còn có thể rò MDC/traceId của request **trước** trên cùng worker thread nếu context không được restore/clear đúng.

### 12.2. ContextPropagatingTaskDecorator

Spring Framework 6.x có `ContextPropagatingTaskDecorator`, dùng Micrometer Context Propagation để chuyển contextual values sang executor task.

Đây là **fragment cấu hình**, không thuộc dự án runnable ở mục 8:

```java
@Bean
ThreadPoolTaskExecutor taskExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(40);
    executor.setThreadNamePrefix("observed-worker-");

    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());

    return executor;
}
```

Cần imports `@Bean`, `ThreadPoolTaskExecutor` và `ContextPropagatingTaskDecorator`. Khi Spring quản lý bean, executor được initialize/shutdown theo lifecycle. **Phải chắc chắn `@Async` thực sự chọn đúng executor này**, ví dụ `@Async("taskExecutor")`. Chỉ tạo bean decorator nhưng method chạy trong executor khác thì propagation không hoạt động.

Trong Spring Boot 3.5, `spring.task.execution.propagate-context=true` có thể bật propagation cho executor do Boot auto-configure, nhưng không tự động trang trí một `Executors.newFixedThreadPool()` do developer tự tạo. Kiểm tra version/auto-config và lựa chọn executor thật.

### 12.3. Test propagation có ý nghĩa

Một test cần:
1. Mở parent span/observation scope trên caller.
2. Submit task qua **real configured executor**.
3. Trong worker thread, đọc `tracer.currentSpan()` hoặc `registry.getCurrentObservation()`.
4. Assert traceId/context liên hệ đúng parent; không hard-code random value.
5. Đóng scope và dùng `Future.get(timeout)` để chờ task.
6. Gửi tiếp một task khác, xác minh không rò context của lần trước.

Không chỉ assert traceId trong caller thread rồi tuyên bố propagation đã đúng. Không sử dụng `Thread.sleep(100)` để đoán worker hoàn tất; điều đó gây test flaky khi CI chậm.

## 13. Reactor Context khác ThreadLocal

Ở WebFlux/Reactor, publisher có thể chuyển thread qua `publishOn` hoặc `subscribeOn`, trong khi Reactor Context đi cùng reactive sequence. Điều này khác một service JDBC imperative duy trì ThreadLocal đơn giản.

Khi test tracing trong WebFlux:
- Cần `StepVerifier` để thực sự subscribe.
- Quan sát current trace context trong operator đang thực thi, không chỉ lúc tạo `Mono`.
- Nếu dùng Micrometer Context Propagation, xác nhận mode/context transfer của Spring Boot/Project Reactor đúng version.
- Không `.block()` bừa trên event-loop.
- Không cho rằng test dùng `SimpleTracer` trong plain JUnit đã chứng minh WebFlux propagation qua `publishOn`.
- Không trộn JDBC `@Transactional` ThreadLocal với reactive `TransactionalOperator` rồi xem chúng cùng context.

Đây là kiến thức mở rộng; project runnable chỉ test imperative Observation và plain ExecutorService để tránh tạo một ví dụ reactive thiếu dependencies/semantics.

## 14. HTTP traceparent và propagation qua service boundaries

W3C Trace Context dùng `traceparent` header. Một giá trị minh họa hợp lệ:

```http
GET /v1/shipments/SHIP-101 HTTP/1.1
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Nó chứa version, 16-byte trace ID, 8-byte parent ID và flags. Ví dụ này **không phải một outbound request đã thực thi** trong bài.

Để test HTTP propagation đúng mức:
- Dùng Boot-managed `RestClient.Builder`, `RestTemplateBuilder` hoặc `WebClient.Builder` đã được instrumentation/tracing customizers của app áp dụng.
- Bật Micrometer Tracing bridge/tracer/propagator tương thích.
- Giữ tracing bật nhưng **disable/export-mock** external reporter.
- Dùng local `MockRestServiceServer`, `MockWebServer` hoặc WireMock để nhận outbound request.
- Assert header được **client thật sinh**, không tự thêm `traceparent` bằng code test rồi coi là đã instrument.
- Test incoming propagation bằng MockMvc/local HTTP server và assert server/child context liên hệ parent nếu service cần.
- Kiểm tra trace flags/sampling và format W3C/B3 theo cấu hình.

**Không thể suy luận HTTP propagation từ việc `SimpleTracer` có một traceId hợp lệ.** Muốn kiểm chứng header phải quan sát HTTP request thực trong test.

## 15. Test exporter mà không gọi Internet

Khi yêu cầu chuyển sang “span có được reporter gửi đúng không?”, hai cách phù hợp:

### 15.1. In-memory exporter (OpenTelemetry SDK)

Một `InMemorySpanExporter` trong test-only OpenTelemetry SDK có thể lưu `SpanData` tại chỗ. Test sẽ:
- Cấu hình SDK/bridge/SpanProcessor với exporter in-memory.
- Chạy code instrumented.
- Force-flush/shutdown khi test exporter lifecycle.
- Assert span name, attributes, parent IDs, error status.
- Reset exporter giữa các test.

Điều này mạnh hơn recorder chỉ kiểm tra `ObservationHandler`, nhưng vẫn không chứng minh collector thật reachable. Không thêm `opentelemetry-exporter-otlp` production song song khi test chỉ muốn in-memory.

### 15.2. Fake reporter hoặc local HTTP stub

Nếu producer tự viết một reporter:
- Inject fake implementation ghi call arguments vào list/queue.
- Assert payload và retry/error policy.
- Dùng local mock server khi cần kiểm chứng JSON/Protobuf/HTTP headers/timeouts.
- Ngăn production endpoint được dùng trong test bằng config isolation.
- Đóng resources/background exporter threads sau test.

Khi muốn verify exporter chính thức, local mock collector có giá trị hơn một cloud endpoint: tests có thể chạy offline, không cần credentials, và test có thể chủ động giả timeout/500/429.

### 15.3. Không gộp đơn vị đo và export transport

Business Observation test chỉ cần assert handler callback. Trace context test cần current span/parent. Export test mới cần reporter. Production monitoring/backend readiness là một bài vận hành khác, không phải unit test.

## 16. Các rủi ro và lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Observation chạy nhưng không có traceId | Không có tracing bridge/handler | Phân biệt Observation với Tracer |
| Test cần Zipkin/Tempo/OTLP đang chạy | Exporter bật trong test | Fake/in-memory exporter, disable network |
| @SpringBootTest có no-op/missing Tracer | Test tracing reporting bị vô hiệu | Dùng test tracer hoặc test config có mục tiêu |
| @AutoConfigureObservability có no-op tracer | Slice test cố tránh exporter | Không assert span IDs thật trên no-op |
| Missing `onStop` | Quên observation.stop | `finally` gọi stop |
| Missing `onError` | Exception không được đánh dấu | `observation.error(ex)` |
| Child observation không có parent | Không tạo child trong parent scope | Mở scope trước rồi tạo child |
| TraceId biến mất khi `@Async` | ThreadLocal không propagate | TaskDecorator/ContextSnapshot |
| Trace/MDC rò sang request tiếp | Scope không restore | `try-with-resources`/finally cleanup |
| Test asserts random traceId literal | ID generator nondeterministic | Assert quan hệ parent-child |
| Test dùng log snapshot | Timestamp/thread/order không ổn định | Assert semantics, không full log text |
| Dùng shipment ID làm metric tag | High cardinality explosion | Low-card labels có tập giới hạn |
| Sampling làm thiếu spans | Probability/processor lọc | Kiểm soát sampling khi test export |
| Disabled tracing nhưng vẫn kỳ vọng traceparent | Tắt cả tracing, không chỉ exporter | Giữ tracing on, export off |
| Test traceparent pass vì tự chèn header | Chưa kiểm tra instrumentation | Inspect real outbound request |
| Custom reporter vẫn gọi network | Bean riêng không theo Boot props | Disable/override custom bean trong test |
| Tests chạy song song mất record | Spring context recorder shared | Per-test handler hoặc test isolation |
| Boot 4 property tên khác | Copy config sai version | Tra appendix properties đúng Boot |
| Span được tạo nhưng backend không thấy | Exporter/sampling/flush/network | Test riêng từng tầng |
| Test timeout flake | Chờ Thread.sleep | Future/latch/await có deadline |
| External token bị lộ qua trace | High-card/PII không được kiểm soát | Redaction và whitelist |
| Sampling=1 nhưng không có spans | Tracing handler thiếu hoặc tracing disabled | Kiểm tra dependency và handler |
| Producer trả OK nhưng reporter lỗi background | Reporter asynchronous | Fake reporter, flush và log verification |

### 16.1. Quy trình debug ngắn

1. Chỉ rõ test muốn chứng minh Observation, trace context, HTTP propagation hay exporter.
2. Kiểm tra dependencies: actuator/observation, tracing bridge, exporter.
3. Kiểm tra `ObservationRegistry` có handler thích hợp.
4. Kiểm tra `management.tracing.enabled` và exporter flags.
5. Kiểm tra `start`, `openScope`, `error`, `stop` trong code.
6. Kiểm tra low/high cardinality và PII.
7. Kiểm tra parent context có được truyền qua thread/executor không.
8. Nếu HTTP, inspect request của instrumented client bằng mock server.
9. Nếu exporter, thay bằng in-memory/local fake, tránh cloud.
10. Đọc JUnit report và background exporter warnings, không chỉ build status.

## 17. Observability trong Spring Boot còn có @Observed và @NewSpan

Spring Boot 3.5 hỗ trợ opt-in annotation instrumentation khi:
- `management.observations.annotations.enabled=true`.
- AspectJ/AOP dependency được khai báo phù hợp (ví dụ `spring-boot-starter-aop`).
- Method được gọi **qua Spring proxy**, không self-invocation.
- Annotation không được chồng lên một method đã auto-instrumented gây duplicate observations.

Ví dụ **fragment**, không thuộc demo:

```java
@Observed(name = "shipment.dispatch")
public Receipt dispatch(String id) {
    return doDispatch(id);
}
```

Test muốn chứng minh `@Observed` hoạt động phải có Spring AOP context/proxy thật và configured observation registry. Một plain JUnit `new ShippingService()` không kích hoạt AOP. Nếu bạn đã instrument thủ công bằng `Observation.createNotStarted(...)`, đừng vô ý thêm `@Observed` lên cùng method rồi đếm hai observations.

Tương tự, `@NewSpan` cần tracing infrastructure thích hợp; không suy ra nó tạo span khi tracer disabled/no-op.

## 18. Kết quả kỳ vọng và giới hạn thực thi

Project demo có **12 methods `@Test`**:
- 5 ca `ShippingObservationUnitTest`: lifecycle, tags, parent, exception, cleanup.
- 3 ca `ShippingObservationSpringTest`: Spring DI/ObservationHandler registration.
- 4 ca `TraceContextTest`: trace/span IDs, explicit parent, executor ThreadLocal và scope restoration.

### 18.1. Lệnh chạy Gradle

Linux/macOS:

```bash
./gradlew test --tests "com.example.observe.ShippingObservationUnitTest"
./gradlew test --tests "com.example.observe.ShippingObservationSpringTest"
./gradlew test --tests "com.example.observe.TraceContextTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.observe.ShippingObservationUnitTest"
.\gradlew.bat test --tests "com.example.observe.ShippingObservationSpringTest"
.\gradlew.bat test --tests "com.example.observe.TraceContextTest"
```

Nếu project dùng Maven wrapper với `pom.xml`/BOM/Surefire tương đương:

```bash
./mvnw -Dtest=ShippingObservationUnitTest test
./mvnw -Dtest=ShippingObservationSpringTest test
./mvnw -Dtest=TraceContextTest test
```

Đây là **code ví dụ và hành vi dự kiến**, **không phải bằng chứng JUnit đã chạy thực tế** trong môi trường hiện tại. Phải kiểm tra `build/reports/tests/test/index.html` hoặc `target/surefire-reports/`: số methods được discover, executed, skipped, failed và background log warnings. Một task `NO-SOURCE` hoặc `BUILD SUCCESSFUL` với tests bị skip không chứng minh runtime PASS.

Dự án sử dụng dependencies Spring/Micrometer/JUnit nên chạy qua build tool, không dùng `javac` đơn lẻ thiếu classpath. Không có stdout cố định của business app vì main class không in kết quả; trace IDs, duration và thread names có thể thay đổi.

## 19. Checklist QA cho bài học

- [ ] Phân biệt Observation lifecycle, trace context và export transport.
- [ ] Không đồng nhất `ObservationRegistry` với một tracer có actual span IDs.
- [ ] Có ObservationHandler/TestObservationRegistry để kiểm tra callback thật.
- [ ] Test `onStart`, `onStop`, `onEvent`, `onError`, kể cả nhánh exception.
- [ ] Mở scope đúng lúc tạo child, assert parent/child Observation.
- [ ] Đóng scopes bằng try-with-resources và stop trong finally.
- [ ] Low-cardinality tags không chứa record ID/PII.
- [ ] High-cardinality attributes vẫn tuân thủ privacy policy.
- [ ] Dùng `SimpleTracer`/in-memory SDK để test trace IDs, không cần exporter.
- [ ] Assert IDs theo quan hệ, không snapshot random traceId.
- [ ] `@SpringBootTest` không có external reporter không cần collector.
- [ ] Custom exporter/reporters được disable/override trong test.
- [ ] `management.tracing.enabled=false` không bị nhầm với chỉ disable export.
- [ ] Nếu cần `traceparent`/B3, phải test qua instrumented HTTP client/server thật.
- [ ] Không tin test SimpleTracer chứng minh Micrometer tracing bridge đã được wiring.
- [ ] Khi cần export semantics, dùng fake/in-memory exporter hay local stub.
- [ ] Với `@Async`/Reactor, context propagation được kiểm tra ở worker/subscriber.
- [ ] Không dùng Thread.sleep cho async assertions.
- [ ] Tránh token/PII trong spans/logs/baggage.
- [ ] Có strategy cleanup recorder/scope/thread pools trong suite parallel.
- [ ] Kiểm tra đúng Boot 3.5 property names, không copy Boot 4 config tùy tiện.
- [ ] Đọc reports JUnit thật rồi mới báo runtime pass.

## 20. Tài liệu tham khảo

- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): ObservationRegistry, handlers, low/high cardinality.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): Micrometer Tracing, OTLP/Zipkin export.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): observability defaults và `@AutoConfigureObservability`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): tracing/exporter properties.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): `Observation`, `ObservationHandler` lifecycle.
- [Micrometer Tracing — Testing](https://docs.micrometer.io/tracing/reference/1.5/testing.html): `micrometer-tracing-test`, `SimpleTracer`.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): `Tracer`/`Span`/scope.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/purpose.html): ContextSnapshot, context restore.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor/task context.
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): assertions và test reports.

**Kết luận:** Kiểm thử observability tốt cần tách **lifecycle Observation**, **trace context** và **export transport**. Có `ObservationRegistry` không tự bảo đảm đã tạo span; một `SimpleTracer` đủ để xác minh quan hệ trace IDs mà không có collector; `@SpringBootTest` với exporter isolation và in-memory handler giúp kiểm tra wiring. Khi cần xác minh `traceparent`, hãy test HTTP client được instrument thật với mock endpoint; khi cần xuất OTLP, hãy test fake/in-memory exporter riêng. Không biến bài test business thường thành bài test phụ thuộc Internet, và không coi một traceId trên log là bằng chứng exporter đã gửi thành công.