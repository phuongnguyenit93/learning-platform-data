# MeterRegistry thử nghiệm và kiểm chứng counter, timer, tag

## 1. Bối cảnh của nhóm Sự kiện và observability

Một ứng dụng Spring Boot có thể xử lý đúng nghiệp vụ nhưng xuất **metrics sai**. Ví dụ, order thanh toán thất bại được tính vào counter có tag `result=success`; timer không được dừng khi exception; tag `orderId` tạo hàng triệu series; hoặc một test dùng `SimpleMeterRegistry` riêng nên tưởng đã kiểm tra registry được Spring Boot inject. Những lỗi này không nhất thiết làm business test đỏ, nhưng sẽ làm dashboard, alert và điều tra sự cố trở nên thiếu tin cậy.

Với chủ đề **MeterRegistry thử nghiệm và kiểm chứng counter, timer, tag**, cần tách ba câu hỏi:

1. **Instrumentation có chạy?** Service tăng counter, ghi timer và giữ đúng outcome tag cả khi xử lý thành công lẫn thất bại.
2. **Meter nào được cập nhật?** Tên, kiểu meter, tag names/values, time unit và số samples có đúng không?
3. **Registry nào được dùng?** Unit test với registry in-memory riêng khác Spring Boot integration test dùng bean `MeterRegistry` thật, và còn khác việc kiểm tra exporter Prometheus/Datadog qua network.

Bài học dùng **Java 17, Spring Boot 3.3.0, Micrometer qua Actuator và JUnit 5**. Dự án có source và test class hoàn chỉnh: unit tests với `SimpleMeterRegistry` và `MockClock`; Spring Boot test kiểm tra wiring. Những kết quả JUnit nêu bên dưới là **expected**, không phải tuyên bố đã chạy Gradle trong quá trình biên soạn.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

- Tạo `SimpleMeterRegistry` cho unit tests và không phụ thuộc static `Metrics.globalRegistry`.
- Phân biệt `Counter`, `Timer`, `Gauge`, `DistributionSummary` và `ObservationRegistry`.
- Hiểu Counter là đại lượng chỉ tăng, Timer ghi số samples và tổng thời lượng.
- Dùng `Timer.Sample` để ghi thời gian với tag `result` xác định sau khi operation hoàn thành.
- Dùng `Timer.record(Duration)` và `MockClock` để assert durations deterministic.
- Truy vấn đúng meter theo tên và tags bằng `registry.find(name).tag(key,value)`.
- Phân biệt outcome=success và outcome=error thành hai series độc lập.
- Thiết kế test tăng counter/timer khi exception và khi success, không double-count.
- Kiểm tra tag cardinality; tránh order ID, user ID, request ID, raw URL và exception message.
- Cô lập metrics giữa các JUnit methods mà không `clear()` toàn bộ registry chung.
- Kiểm tra Spring Boot `@SpringBootTest` với bean `MeterRegistry` thực và delta trước/sau.
- Hiểu fallback `SimpleMeterRegistry` và khác biệt auto-configuration/exporter ở môi trường test.
- Biết `@Timed` không tự instrument mọi arbitrary method chỉ vì dependency Actuator tồn tại.
- Hiểu Prometheus naming, time units, histogram/percentiles và step registry.
- Biết khi nào cần kiểm thử exporters, HTTP Actuator endpoints, Observation và reactive pipelines.
- Giải thích những lỗi thường gặp: lookup sai tag, registry khác, TestContext cache, timer sample missing, async timing sai.
- Không coi một unit test metrics pass là bằng chứng production monitoring pipeline đã hoạt động.

## 3. Mô hình Micrometer MeterRegistry

```text
CheckoutService
    |
    +--> checkout.requests{result="success"} : Counter
    +--> checkout.requests{result="error"}   : Counter
    +--> checkout.duration{result="success"} : Timer
    +--> checkout.duration{result="error"}   : Timer
    |
    v
MeterRegistry (Micrometer facade)
    |
    +--> SimpleMeterRegistry (memory; unit tests)
    +--> CompositeMeterRegistry (delegates)
    +--> PrometheusMeterRegistry (scrape)
    +--> Datadog/Statsd/... (push/periodic)
    |
    v
Metrics backend -> dashboards/alerts
```

**Micrometer registry không phải backend monitoring**. `SimpleMeterRegistry` giữ meter values trong JVM, không gửi HTTP metrics sang máy chủ khác. `@SpringBootTest` có thể cung cấp registry in-memory, nhưng không mặc nhiên bật external exporter.

Đối với ứng dụng production, inject `MeterRegistry` vào service:

```java
@Service
public class CheckoutService {
    private final MeterRegistry registry;

    public CheckoutService(MeterRegistry registry) {
        this.registry = registry;
    }
}
```

Đây là **snippet khai báo ý tưởng** chưa có business method; phần full class ở chương 12. Spring Boot gắn meter customizers, common tags và filters lên Spring-managed registry; đó là lý do dùng bean injection thay vì gọi static `Metrics.counter(...)`.

## 4. Counter: đếm sự kiện tăng dần

`Counter` ghi số lần một sự kiện xảy ra. Nó không phù hợp làm “độ dài queue hiện tại” hay “số connection đang mở”, vì các giá trị trạng thái có thể giảm.

```java
registry.counter(
        "checkout.requests",
        "result", "success").increment();
```

Tương đương một builder với description/tag:

```java
Counter.builder("checkout.requests")
        .description("Checkout attempts")
        .tag("result", "success")
        .register(registry)
        .increment();
```

Khi gọi ba lần trên cùng meter ID:

```java
Counter c = registry.counter(
        "checkout.requests",
        "result", "success");

c.increment();
c.increment();
c.increment();

assertEquals(3.0, c.count(), 0.000001);
```

Test phải tạo registry riêng hoặc đo delta. Với registry được reuse giữa tests, `count()` có thể bắt đầu từ một giá trị khác 0.

### 4.1. Counter vs Gauge

- `Counter`: tổng số checkout attempts đã xảy ra kể từ khi series/registry bắt đầu.
- `Gauge`: trạng thái hiện tại như in-flight requests hoặc queue depth, có thể tăng/giảm.
- `DistributionSummary`: phân phối giá trị như payload size, order amount (không phải elapsed duration).
- `Timer`: số lượt và thời lượng hoạt động; phù hợp latency.

Không cố dùng Counter giảm bằng `increment(-1)`; điều đó trái semantic của Counter và có thể bị provider từ chối/không hỗ trợ.

### 4.2. Đếm logical requests hay physical retries?

Một checkout có thể gọi payment gateway ba lần vì retry. Nếu counter của bạn đếm mỗi network attempt, thì “3” không phải 3 đơn hàng. Tên và description phải nói rõ:

- `checkout.requests`: mỗi logical checkout invocation.
- `payment.gateway.attempts`: mỗi outbound attempt.
- `checkout.retries`: số retries.

Timer count có thể đếm mỗi attempt hoặc whole request; không cộng các metrics có scope khác nhau vào một request count.

## 5. Timer: số lượt, tổng thời lượng và max

`Timer` chuyên ghi duration. API thông dụng:

- `timer.record(Duration.ofMillis(100))` để ghi một sample.
- `timer.count()` để xem số samples.
- `timer.totalTime(TimeUnit.MILLISECONDS)` để xem tổng duration.
- `timer.max(TimeUnit.MILLISECONDS)` để xem max theo implementation và time window.
- `Timer.Sample.start(registry)` để bắt đầu stopwatch và `stop(timer)` để ghi vào series đích.

Ví dụ deterministic:

```java
Timer timer = Timer.builder("checkout.synthetic.duration")
        .tag("scenario", "unit")
        .register(registry);

timer.record(Duration.ofMillis(120));
timer.record(Duration.ofMillis(80));

assertEquals(2L, timer.count());
assertEquals(
        200.0,
        timer.totalTime(TimeUnit.MILLISECONDS),
        0.000001);
```

Với `TimeUnit.SECONDS`, tổng tương ứng là 0,2 giây. Prometheus exporters thường dùng seconds; Micrometer API yêu cầu TimeUnit khi đọc timer values. Đừng so 200 milliseconds với 200 seconds.

### 5.1. Timer có count riêng

Một `Timer` luôn ghi count và totalTime ở mức khái niệm. Nếu một checkout luôn ghi một sample, count này cũng phản ánh số lượt được đo. Một Counter riêng chỉ hữu ích nếu bạn muốn event count có semantic riêng hoặc dashboard/query contract yêu cầu, không phải để nhân đôi tổng traffic.

### 5.2. max không phải max mọi thời đại

Nhiều timers có **time-window max**: sau một khoảng không có samples, max có thể reset/roll over tùy registry. Một unit test có thể assert max ngay sau khi ghi durations, nhưng không nên đòi một max historical phải tồn tại vô thời hạn. Nếu muốn max kéo dài hoặc p95, cần design backend/query và histogram phù hợp.

### 5.3. Không dùng Timer cho giá trị âm

Timer chỉ nhận duration không âm. Nếu đo biến động số dư, latencies có thể không âm nhưng account delta có thể âm; dùng metric loại khác phù hợp.

## 6. Timer.Sample trong success và error paths

Dùng `Timer.Sample` khi outcome chỉ được biết sau khi operation hoàn thành:

```java
Timer.Sample sample = Timer.start(registry);
String result = "success";

try {
    return gatewayCall();
}
catch (RuntimeException e) {
    result = "error";
    throw e;
}
finally {
    sample.stop(
            Timer.builder("checkout.duration")
                    .tag("result", result)
                    .register(registry));
}
```

**Snippet**, biến `gatewayCall()` và registry được định nghĩa ở runnable service sau. `finally` giữ count/timer trên error path và exception business vẫn propagate. Nếu stop cả trong catch và finally, timer có thể bị ghi **hai lần**. Pattern nên là: start một lần, stop một lần.

### 6.1. Timer.Sample đo elapsed thật

`Timer.start(registry)` dùng clock của registry. Nếu gateway operation nhanh, sample duration có thể rất nhỏ; assert exact milliseconds dựa vào runtime scheduling sẽ flaky. Muốn test timer semantics, hãy dùng `MockClock` như chương 7.

### 6.2. Async/reactive không giống synchronous finally

Nếu method chỉ *tạo* `Mono` hoặc `CompletableFuture`, `finally` sync có thể chạy trước khi async operation thực hiện. Để đo end-to-end latency của publisher, phải start/stop quanh **subscription/termination** (doFinally/Observation) chứ không chỉ quanh assembly. Bài lab chính dùng method synchronous để assertions đơn nghĩa.

## 7. MockClock: test thời lượng chính xác không cần sleep

`MockClock` thuộc Micrometer test-friendly API; nó kiểm soát `monotonicTime` của registry. Với `SimpleMeterRegistry(SimpleConfig.DEFAULT, clock)`:

```java
MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(
                SimpleConfig.DEFAULT, clock);

Timer timer = registry.timer("demo.duration");

Timer.Sample sample = Timer.start(registry);
clock.add(Duration.ofMillis(125));
sample.stop(timer);

assertEquals(1L, timer.count());
assertEquals(
        125.0,
        timer.totalTime(TimeUnit.MILLISECONDS),
        0.000001);

registry.close();
```

Đây là deterministic test: đồng hồ được advance theo duration định trước, không `Thread.sleep(125)`. Nó không mô phỏng throughput/real CPU performance; chỉ chứng minh Timer.Sample và registry record đúng duration.

### 7.1. Vì sao không assert elapsed thực bằng nanoseconds tuyệt đối?

JIT, GC, scheduler, CPU quotas, system clock resolution và CI load đều thay đổi. Ví dụ anti-pattern:

```java
long start = System.nanoTime();
service.checkout("A");
long elapsed = System.nanoTime() - start;

assertEquals(5_000_000L, elapsed); // flakey
```

Một business metrics unit test nên assert meter count và outcome tags; một synthetic test kiểm tra duration chính xác; benchmark/performance test dùng methodology riêng.

### 7.2. MockClock vs fake business Clock

Micrometer `MockClock` dùng cho Timer.Sample và registry, khác với `java.time.Clock` của business code. Thay business clock không mặc nhiên thay thời gian monotic của Micrometer. Khi test deadline/TTL nghiệp vụ khác, nên inject đúng clock ở tầng đó.

## 8. Tags: định danh series

Hai counters dưới đây khác nhau vì có tag value khác:

```text
checkout.requests{result="success"} = 5
checkout.requests{result="error"}   = 2
```

Trong Micrometer, meter lookup theo name + tags tạo/tra một series. Khi muốn đọc:

```java
Counter success = registry.find("checkout.requests")
        .tag("result", "success")
        .counter();

Counter error = registry.find("checkout.requests")
        .tag("result", "error")
        .counter();
```

Trong test, `assertNotNull(success)` trước khi `success.count()`. Nếu một tag key bị đổi từ `result` thành `outcome`, test phải đỏ chứ không được âm thầm đọc nhầm meter cùng tên.

### 8.1. Tag names và values phải ổn định

Đặt `result=success|error` với một enum/constant set; đừng có `succes` và `success` tạo hai series khác nhau. Nếu hệ thống có outcomes `success`, `rejected`, `timeout`, ghi rõ contract và không dùng raw exception message làm label.

### 8.2. Tag ordering

Tập tags có cùng pairs theo thứ tự khác nhau vẫn diễn đạt cùng logical identity. Đừng viết unit tests phụ thuộc thứ tự string serialization của tags khi đây không phải exporter contract. Dùng `meter.getId().getTag("result")` để đọc cụ thể.

### 8.3. Tên meter không đủ nếu có nhiều series

`registry.find("checkout.requests").counter()` không rõ ràng khi nhiều values/tags. Dùng `.tag("result","success")` hoặc `get(name).tags(...)`. Với negative assertion, `find` trả null khi series chưa đăng ký.

### 8.4. Common tags

Spring Boot có thể thêm common tags như `application`, `environment` qua `MeterRegistryCustomizer` và `MeterFilter`. Business tests có thể query theo tag cần thiết thay vì assert toàn bộ set không cho thay đổi. Nếu common tags là contract của dashboard, cần assert riêng bằng Spring-managed registry.

## 9. Tag cardinality: nguyên tắc quan trọng nhất

Các tag tốt có tập giá trị hữu hạn, chẳng hạn:

- `result=success|error`.
- `method=GET|POST`.
- `operation=checkout|refund`.
- `status=2xx|4xx|5xx`.
- `payment_method=card|bank_transfer|wallet` khi phạm vi được kiểm soát.
- HTTP `uri=/orders/{id}` theo route template.

Các tag không nên dùng trực tiếp nếu tạo series vô hạn:

- `orderId`, `userId`, `sessionId`, `requestId`.
- Email, số điện thoại, raw IP và raw user agent.
- Raw exception message.
- Timestamp, random UUID, full SQL statement.
- HTTP raw path `/orders/1234`, full URL có query params/IDs.

Nếu có 2 outcomes × 3 operations × 1 triệu order IDs, bạn đã tạo hàng triệu unique series. Bộ nhớ registry và backend cost tăng rất mạnh; một test với 1 order không phát hiện vấn đề trừ khi có **tag policy assertion**.

### 9.1. Unit test guard

Trong test, inspect các meter IDs:

```java
for (Meter meter : registry.getMeters()) {
    assertNull(meter.getId().getTag("orderId"));
    assertNull(meter.getId().getTag("userId"));
}
```

Bộ test runnable chỉ inspect meters có prefix `checkout.`. Trong hệ thống lớn, review toàn bộ instrumentation và dùng `MeterFilter.maximumAllowableTags(...)` nếu cần lớp phòng vệ bổ sung.

### 9.2. Logs/traces dùng cho request identity

Nếu cần tra một order cụ thể, dùng structured logs hoặc traces có IDs, không tạo metric series riêng. Metrics phục vụ aggregate signals và alert; tracing/logging phục vụ một request cụ thể. Exemplars có thể liên kết nhưng không cần tạo label per request.

## 10. Isolation giữa JUnit tests

Một trong những nguyên nhân phổ biến của test flaky là registry tồn tại qua nhiều methods:

```java
@BeforeEach
void setUp() {
    registry = new SimpleMeterRegistry();
    service = new CheckoutService(
            new DemoPaymentGateway(), registry);
}

@AfterEach
void tearDown() {
    registry.close();
}
```

Mỗi method bắt đầu với registry rỗng. `close()` giải phóng resources và không động đến registry toàn cục. Không dùng static registry trong `@BeforeAll` nếu tests assert counts bắt đầu bằng 0.

### 10.1. Vì sao không gọi clear trên Spring Boot registry?

`MeterRegistry.clear()` xóa meters đã đăng ký. Với Spring-managed registry dùng chung, JVM/process instrumentation hoặc các beans khác có thể đã giữ references tới meters cũ. Sau clear, kết quả có thể không mong đợi; test khác cũng bị ảnh hưởng.

Nên làm:

- **Unit:** registry mới mỗi test.
- **Integration:** đo **baseline trước** rồi assert delta sau khi service chạy.
- **Isolated context:** chỉ reset context khi thật sự cần, hiểu chi phí và metric listeners.
- **Parallel tests:** không cho nhiều methods cập nhật cùng meter series trên một shared registry nếu muốn assert exact delta.

### 10.2. Metrics.globalRegistry là global state

`Metrics.globalRegistry` là static composite registry. Nếu test A thêm backend còn test B không remove, counts có thể bị tái sử dụng/đưa sang nơi ngoài ý muốn. Constructor inject `MeterRegistry`, không dùng static `Metrics.counter(...)` trong service mẫu.

### 10.3. @SpringBootTest không tự có registry trống

Spring TestContext cache có thể dùng lại ApplicationContext giữa classes. Spring Boot/Actuator tạo nhiều framework metrics, và một custom meter có thể tồn tại từ method trước. Cách đúng là baseline/delta hoặc context riêng; không assert mọi counter chắc chắn 0 mà không biết lifecycle.

## 11. Dự án runnable — cây thư mục và dependencies

```text
micrometer-test-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/metrics/
    │   ├── MetricsLabApplication.java
    │   ├── PaymentGateway.java
    │   ├── DemoPaymentGateway.java
    │   └── CheckoutService.java
    └── test/java/example/metrics/
        ├── CheckoutMetricsUnitTest.java
        └── CheckoutMetricsBootTest.java
```

### 11.1. settings.gradle

```groovy
rootProject.name = 'micrometer-test-lab'
```

### 11.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Actuator starter mang Micrometer/metrics auto-configuration vào project. JUnit, Assertions và Spring Boot test support đến từ starter-test. Không cần Kafka, database, Docker hay Prometheus cho ví dụ chính.

### 11.3. MetricsLabApplication.java

**src/main/java/example/metrics/MetricsLabApplication.java**

```java
package example.metrics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetricsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MetricsLabApplication.class, args);
    }
}
```

### 11.4. PaymentGateway.java

**src/main/java/example/metrics/PaymentGateway.java**

```java
package example.metrics;

public interface PaymentGateway {
    String pay(String orderId);
}
```

### 11.5. DemoPaymentGateway.java

**src/main/java/example/metrics/DemoPaymentGateway.java**

```java
package example.metrics;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {

    @Override
    public String pay(String orderId) {
        if (orderId.startsWith("FAIL")) {
            throw new IllegalStateException(
                    "Payment was rejected");
        }
        return "paid:" + orderId;
    }
}
```

Gateway demo không gọi payment API thật. Outcome được điều khiển qua orderId để unit/integration tests có positive/negative branches. Không dùng kết quả này để tuyên bố đã kiểm tra giao dịch thanh toán thật.

## 12. CheckoutService.java — Counter và Timer.Sample

**src/main/java/example/metrics/CheckoutService.java**

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;
    private final MeterRegistry registry;

    public CheckoutService(
            PaymentGateway gateway,
            MeterRegistry registry) {
        this.gateway = gateway;
        this.registry = registry;
    }

    public String checkout(String orderId) {
        Timer.Sample sample = Timer.start(registry);
        String result = "success";

        try {
            return gateway.pay(orderId);
        }
        catch (RuntimeException ex) {
            result = "error";
            throw ex;
        }
        finally {
            registry.counter(
                    "checkout.requests",
                    "result", result)
                    .increment();

            sample.stop(
                    Timer.builder("checkout.duration")
                            .description(
                                    "Checkout processing latency")
                            .tag("result", result)
                            .register(registry));
        }
    }
}
```

### 12.1. Semantics của hai metric

- `checkout.requests{result=success}`: số lần service.checkout() thành công.
- `checkout.requests{result=error}`: số lần service.checkout() throw RuntimeException.
- `checkout.duration{result=success}`: durations của successful executions.
- `checkout.duration{result=error}`: durations của failed executions.

Timer bắt đầu trước gateway, stop ở finally, do đó error branch cũng được đo. Tag `result` chỉ có success/error; không dùng `orderId` tag. Không ghi counter riêng vào catch rồi lại ghi trong finally: sẽ double-count errors.

### 12.2. Một điểm để review trong production

Nếu `gateway.pay` có một `Error` không phải RuntimeException, catch ở lab không đổi result thành error, dù finally vẫn chạy; bài chọn exception type phục vụ demo. Trong production, cần định nghĩa outcome policy cho Error, cancellation, retry, validation errors và unexpected exceptions một cách phù hợp; không phải catch mọi Throwable một cách vô tội vạ. Những lỗi của metrics backend nếu có cũng cần policy riêng để instrumentation không thay đổi business outcome.

### 12.3. Có thể cache Counter/Timer fields không?

Với tag cố định, có thể register Counter một lần và giữ field để tránh lookup mỗi call. Nhưng tag `result` chỉ biết cuối operation, nên có thể giữ hai fields `successCounter` và `errorCounter`, hoặc lookup theo bounded result tại finally như lab. Lookup là registry hash lookup, thường đủ nhẹ; tránh tạo unlimited series từ user-supplied tag.

## 13. CheckoutMetricsUnitTest.java — 9 tests

**src/test/java/example/metrics/CheckoutMetricsUnitTest.java**

```java
package example.metrics;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CheckoutMetricsUnitTest {

    private SimpleMeterRegistry registry;
    private CheckoutService service;

    @BeforeEach
    void setUp() {
        registry = new SimpleMeterRegistry();
        service = new CheckoutService(
                new DemoPaymentGateway(), registry);
    }

    @AfterEach
    void tearDown() {
        registry.close();
    }

    private Counter counter(String result) {
        Counter counter = registry.find("checkout.requests")
                .tag("result", result)
                .counter();
        assertNotNull(counter);
        return counter;
    }

    private Timer timer(String result) {
        Timer timer = registry.find("checkout.duration")
                .tag("result", result)
                .timer();
        assertNotNull(timer);
        return timer;
    }

    @Test
    void successIncrementsCounterAndRecordsTimer() {
        assertEquals(
                "paid:ORDER-1",
                service.checkout("ORDER-1"));

        assertEquals(1.0,
                counter("success").count(),
                0.000001);
        assertEquals(1L, timer("success").count());

        assertTrue(
                timer("success")
                        .totalTime(TimeUnit.NANOSECONDS) >= 0);

        assertNull(registry.find("checkout.requests")
                .tag("result", "error").counter());
    }

    @Test
    void errorHasItsOwnCounterAndTimer() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("FAIL-1"));

        assertEquals(
                "Payment was rejected",
                failure.getMessage());
        assertEquals(1.0,
                counter("error").count(),
                0.000001);
        assertEquals(1L, timer("error").count());

        assertNull(registry.find("checkout.requests")
                .tag("result", "success").counter());
    }

    @Test
    void successAndErrorHaveSeparateTaggedSeries() {
        assertEquals("paid:A", service.checkout("A"));

        assertThrows(
                IllegalStateException.class,
                () -> service.checkout("FAIL-B"));

        assertEquals("paid:C", service.checkout("C"));

        assertEquals(2.0,
                counter("success").count(),
                0.000001);
        assertEquals(1.0,
                counter("error").count(),
                0.000001);
        assertEquals(2L, timer("success").count());
        assertEquals(1L, timer("error").count());
    }

    @Test
    void repeatedSuccessesAccumulateOnSameMeter() {
        service.checkout("A");
        service.checkout("B");
        service.checkout("C");

        assertEquals(3.0,
                counter("success").count(),
                0.000001);
        assertEquals(3L,
                timer("success").count());

        assertSame(
                registry.counter(
                        "checkout.requests",
                        "result", "success"),
                counter("success"));
    }

    @Test
    void timerRecordsExactSyntheticDurations() {
        Timer synthetic = Timer.builder(
                "checkout.synthetic.duration")
                .tag("scenario", "deterministic")
                .register(registry);

        synthetic.record(Duration.ofMillis(120));
        synthetic.record(Duration.ofMillis(80));

        assertEquals(2L, synthetic.count());
        assertEquals(
                200.0,
                synthetic.totalTime(TimeUnit.MILLISECONDS),
                0.000001);
        assertEquals(
                120.0,
                synthetic.max(TimeUnit.MILLISECONDS),
                0.000001);
    }

    @Test
    void mockClockTestsSampleWithoutSleeping() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry isolated =
                new SimpleMeterRegistry(
                        SimpleConfig.DEFAULT, clock);

        try {
            Timer t = isolated.timer(
                    "checkout.clock.duration",
                    "scenario", "test");

            Timer.Sample sample = Timer.start(isolated);
            clock.add(Duration.ofMillis(125));
            sample.stop(t);

            assertEquals(1L, t.count());
            assertEquals(
                    125.0,
                    t.totalTime(TimeUnit.MILLISECONDS),
                    0.000001);
        }
        finally {
            isolated.close();
        }
    }

    @Test
    void sameNameDifferentTagValueIsDifferentSeries() {
        Counter success = registry.counter(
                "checkout.manual.requests",
                "result", "success");

        Counter error = registry.counter(
                "checkout.manual.requests",
                "result", "error");

        success.increment();
        error.increment();
        error.increment();

        assertEquals(1.0,
                success.count(), 0.000001);
        assertEquals(2.0,
                error.count(), 0.000001);

        assertEquals(
                "success",
                success.getId().getTag("result"));
        assertEquals(
                "error",
                error.getId().getTag("result"));
    }

    @Test
    void missingTagDoesNotMatchAnotherSeries() {
        service.checkout("A");

        assertNull(registry.find("checkout.requests")
                .tag("result", "cancelled")
                .counter());

        assertEquals(1.0,
                counter("success").count(),
                0.000001);
    }

    @Test
    void checkoutMetersNeverUseOrderIdTag() {
        service.checkout("PRIVATE-ORDER-123");

        for (Meter meter : registry.getMeters()) {
            if (meter.getId().getName()
                    .startsWith("checkout.")) {
                assertNull(
                        meter.getId().getTag("orderId"));
                assertNull(
                        meter.getId().getTag("userId"));
            }
        }

        assertFalse(registry.getMeters().isEmpty());
    }
}
```

### 13.1. Unit tests đang kiểm tra điều gì?

| Method | Bằng chứng |
| --- | --- |
| `successIncrementsCounterAndRecordsTimer` | Success counter + timer count tăng 1 |
| `errorHasItsOwnCounterAndTimer` | Error vẫn throw, metrics outcome=error |
| `successAndErrorHaveSeparateTaggedSeries` | Hai series tách biệt, tổng 2 success/1 error |
| `repeatedSuccessesAccumulateOnSameMeter` | Count cộng dồn và meter lookup reuse |
| `timerRecordsExactSyntheticDurations` | 120+80=200ms, count=2, max=120ms ngay sau record |
| `mockClockTestsSampleWithoutSleeping` | Sample 125ms với monotonic MockClock |
| `sameNameDifferentTagValueIsDifferentSeries` | Tags khác → hai meters độc lập |
| `missingTagDoesNotMatchAnotherSeries` | Query cancelled không ăn nhầm success |
| `checkoutMetersNeverUseOrderIdTag` | Không có orderId/userId high-cardinality tag |

### 13.2. Vì sao không mock MeterRegistry?

Mock `MeterRegistry` chỉ cho bạn verify lời gọi Java vào mock. Nó không kiểm tra cache of meter ID, tagged series, timer durations hay count semantics thật. `SimpleMeterRegistry` rất nhẹ, dùng real Micrometer behavior mà vẫn không có network. Đây là một **fake backend thực thi registry API thật**, không cần external monitoring service.

### 13.3. Vì sao assert duration >= 0 cho service, exact cho synthetic?

Thời gian chạy `DemoPaymentGateway.pay` phụ thuộc scheduling, JVM và CPU. Chúng ta chỉ biết nó phải có một timing sample và elapsed không âm. Với synthetic Timer/MockClock, test kiểm soát thời gian nên có thể assert 200/125ms chính xác mà không flaky.

### 13.4. Vì sao test same meter bằng assertSame?

Trong một SimpleMeterRegistry, hai đăng ký cùng name+tags+type đại diện cùng meter ID và có thể reuse cùng meter instance. Với backend/composite registries, vẫn nên dựa vào meter series semantics và counts, không đặt mọi dashboard logic trên Java object identity. Ở unit test local này, assertSame giúp minh họa registry caching.

## 14. CheckoutMetricsBootTest.java — 1 integration test

**src/test/java/example/metrics/CheckoutMetricsBootTest.java**

```java
package example.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutMetricsBootTest {

    @Autowired
    MeterRegistry registry;

    @Autowired
    CheckoutService service;

    private double currentCounterValue(String result) {
        Counter c = registry.find("checkout.requests")
                .tag("result", result)
                .counter();
        return c == null ? 0.0 : c.count();
    }

    private long currentTimerCount(String result) {
        Timer t = registry.find("checkout.duration")
                .tag("result", result)
                .timer();
        return t == null ? 0L : t.count();
    }

    @Test
    void springManagedServiceRecordsMetricsInInjectedRegistry() {
        assertNotNull(registry);
        assertNotNull(service);

        double beforeCounter =
                currentCounterValue("success");
        long beforeTimer =
                currentTimerCount("success");

        assertEquals(
                "paid:BOOT-1",
                service.checkout("BOOT-1"));

        assertEquals(
                beforeCounter + 1.0,
                currentCounterValue("success"),
                0.000001);
        assertEquals(
                beforeTimer + 1L,
                currentTimerCount("success"));

        Timer t = registry.find("checkout.duration")
                .tag("result", "success")
                .timer();
        assertNotNull(t);
        assertTrue(t.totalTime(
                java.util.concurrent.TimeUnit.NANOSECONDS)
                >= 0.0);
    }
}
```

Test này chạy full Spring context, inject `CheckoutService` và **MeterRegistry bean từ auto-configuration**. Bằng chứng mạnh hơn unit test: service thực dùng registry mà application cung cấp. Nó **không** chứng minh data đã export qua Prometheus/Datadog.

### 14.1. Vì sao đo baseline/delta?

Spring TestContext có thể cache context; các metrics có thể được tạo trước khi method chạy. Test đo số trước và sau, mong counter/timer cùng tăng một đơn vị. Không cố gọi `registry.clear()` trên Spring-managed registry vì sẽ xóa cả JVM metrics và meters do framework/other beans giữ.

### 14.2. Tại sao không assert registry là SimpleMeterRegistry ở Boot test?

Nếu project có Prometheus/other registry modules hoặc composite registry, bean concrete type có thể khác. Khi mục tiêu là kiểm tra business instrumentation qua Spring wiring, dùng interface `MeterRegistry` và query custom names/tags. Nếu mục tiêu là provider-specific exporter, test phải assert concrete backend và output riêng.

### 14.3. Nếu hai tests chạy song song trên cùng Spring context

Baseline/delta dễ bị ảnh hưởng nếu test khác cũng gọi service và cập nhật cùng series cùng lúc. Demo chỉ có một Boot metrics test method. Trong suite lớn, dùng separate context, unique test-only metric name/tag scope hoặc disable parallel cho shared metrics tests.

## 15. Chạy Gradle, đọc kết quả

Yêu cầu: JDK 17, Gradle Wrapper tương thích Boot 3.3 (ví dụ Gradle 8.7), dependencies có thể tải từ Maven Central hoặc đã cache.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.metrics.CheckoutMetricsUnitTest
./gradlew test --tests example.metrics.CheckoutMetricsBootTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.metrics.CheckoutMetricsUnitTest
```

| Test class | Methods | Spring context | External monitoring |
| --- | ---: | --- | --- |
| `CheckoutMetricsUnitTest` | 9 | Không | Không |
| `CheckoutMetricsBootTest` | 1 | Có | Không |
| **Tổng** | **10** | Tùy class | Không |

**Dự kiến:** 10 phương thức JUnit pass nếu code, dependencies và môi trường đúng. Đây không phải claim đã thực thi Gradle. Khi báo cáo công việc thật, đọc Gradle XML/HTML test report để xác nhận executed/passed/failed/skipped. Không có business stdout cố định; thread names, process metrics và startup log thay đổi.

### 15.1. Dữ liệu expected có thể tính chính xác

Hai synthetic durations 120ms và 80ms → count=2, total=200ms; MockClock advance 125ms → count=1, total=125ms. Số này dựa trên dữ liệu do test cung cấp chứ không đo CPU, vì vậy deterministic.

### 15.2. Tại sao không cần Docker?

`SimpleMeterRegistry` không gửi network. Spring Boot Actuator simple fallback cũng không cần external monitoring system. Docker/Prometheus chỉ cần nếu bạn chọn thêm exporter-specific integration tests.

## 16. Truy vấn đúng meter và tag

### 16.1. find vs get

`registry.find("checkout.requests").tag("result","success").counter()` trả null nếu không có series. Tốt cho negative assertions. `registry.get("checkout.requests").tags("result","success").counter()` biểu thị meter bắt buộc tồn tại và sẽ báo lỗi nếu thiếu, tùy API.

Đừng chỉ gọi `registry.get("checkout.requests").counter()` khi có nhiều series với cùng name; phải quy định tags để tránh nhầm.

### 16.2. Tags có cùng tên nhưng giá trị khác nhau

`result=success` và `result=error` khác identity. `Counter.builder("...").tag("result","success").register(registry)` được register nhiều lần với cùng ID không tạo một series mới cho mỗi lời gọi. Nhưng đổi giá trị tag sẽ tạo series mới.

### 16.3. Không trộn loại meter cùng tên và tags

Nếu một code path đăng ký Counter `checkout.duration` còn code khác đăng ký Timer cùng name/tags, registry có thể báo conflict hoặc output không hợp lệ. Giữ tên `checkout.requests` (Counter) và `checkout.duration` (Timer) riêng.

### 16.4. Unit vs exporter naming

Trong Micrometer code, name có thể là `checkout.requests`. Trong Prometheus, counter thường xuất tên dạng `checkout_requests_total`. Timers được xuất `_seconds_count`/`_seconds_sum` tùy backend/naming convention.

Ví dụ *minh họa*, không phải scrape thật:

```text
checkout_requests_total{result="success"} 10
checkout_duration_seconds_count{result="success"} 10
checkout_duration_seconds_sum{result="success"} 0.84
```

Không assert text formatting ở SimpleMeterRegistry; phải dùng concrete exporter/scrape khi format là contract.

## 17. Common tags và MeterFilter

Spring Boot có thể áp dụng `MeterRegistryCustomizer` để thêm `application`, `environment`, `region` tag, hoặc `MeterFilter` để rename, deny, cap tags. Unit registry tạo thủ công **không tự áp dụng** mọi Boot customizer đó. Vì thế nếu dashboard phụ thuộc common tags, cần một Spring integration test.

### 17.1. Customizer ví dụ

```java
@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags() {
    return registry -> registry.config()
            .commonTags(
                    "application", "checkout-service");
}
```

Đây là snippet minh họa, cần imports/configuration trong một `@Configuration` và thêm vào app nếu cần; **không thuộc runnable project chính**. Nó thêm tag để bạn lọc dashboard hoặc backend. Không để common tag value là request ID.

### 17.2. MeterFilter theo policy

`MeterFilter.maximumAllowableTags(...)` có thể bảo vệ khỏi unbounded series bằng cách deny/map meter registrations vượt ngưỡng. Đây là lớp phòng vệ, không là giấy phép dùng userId tags. Test của bạn có thể phát hiện meter bị deny vì `registry.find(...).counter()` không có series; hãy inspect filters thay vì xóa assertion.

### 17.3. Nguy cơ late common tags

Nên config filters/common tags **trước khi meters được đăng ký**, thường qua Spring Boot configurers. Thêm tag/filter sau khi instrumentation đã tạo meters có thể dẫn đến behavior không mong muốn; Spring Boot hỗ trợ sắp xếp configurers trong auto-configuration.

## 18. Timer, percentiles, histograms và SLO

Mặc định một Timer có count/totalTime. P95, histogram buckets và service-level objectives cần **distribution configuration** tương ứng và backend hỗ trợ. Ví dụ định hướng:

```properties
management.metrics.distribution.percentiles-histogram.checkout.duration=true
management.metrics.distribution.slo.checkout.duration=50ms,100ms,250ms,1s
```

Đây là cấu hình minh họa; verify thực tế với đúng Boot/Micrometer/backend versions. Histograms tăng số series theo buckets × tags. Khi cardinality đã cao, bật histogram không chọn lọc có thể tăng chi phí observability rất lớn.

### 18.1. Mean không phải p95

`totalTime/count` là average duration, không thể suy ra p95 từ một số tổng và count. Cần distribution/histogram hoặc percentile tracking. Histogram quantiles cũng là ước lượng tùy bucket resolution, không nhất thiết là exact quantile của sample list.

### 18.2. Timer.max trong unit test

Trong `timerRecordsExactSyntheticDurations`, assert max ngay sau khi ghi 120/80ms trong fresh SimpleMeterRegistry. Không dùng assertion đó làm quy luật max lịch sử trong mọi backend, vì time-window rollover.

### 18.3. Đơn vị trong queries

Prometheus client thường xuất seconds; Micrometer Timer API cần explicit TimeUnit. Khi viết alert, quy đổi SLA 250ms thành 0.25 seconds nếu query backend dùng seconds.

## 19. ObservationRegistry, @Timed và instrumentation thủ công

`@Timed` có trong Micrometer, nhưng **Spring Boot không tự kích hoạt timing cho mọi arbitrary method** chỉ vì Actuator starter được thêm. Một `TimedAspect`/AOP integration hoặc Micrometer Observation instrumentation đúng setup có thể cần thiết.

```java
@Timed(value = "checkout.annotated.duration")
public String calculate() {
    return "ok";
}
```

**Snippet minh họa**; annotation không bảo đảm meter xuất hiện nếu chưa cấu hình instrumentation. Muốn chứng minh:

1. Gọi method qua Spring bean/proxy thật, không `new` object.
2. Nạp TimedAspect/Observation integration phù hợp Spring Boot/Micrometer version.
3. Query meter sau khi method thực sự chạy.
4. Test negative khi thiếu instrumentation để tránh xanh giả.
5. Với reactive method, check timing tại **subscription/termination**.

### 19.1. ObservationRegistry là gì?

Micrometer Observations có thể phối hợp metrics, tracing và context propagation thông qua ObservationHandlers. Spring Boot 3.x sử dụng Observations cho nhiều HTTP server/client instrumentations. Nếu code tự dùng `Timer.Sample` cho cùng boundary mà Observation cũng ghi, bạn có thể bị duplicate metrics hoặc mất nhất quán names/tags. Xác định một source of truth cho từng semantic metric.

### 19.2. HTTP server metrics vs business checkout metrics

`http.server.requests` thường đo mỗi HTTP exchange; `checkout.requests` đo một lần CheckoutService được gọi. Một HTTP request có thể gọi service nhiều lần, hoặc checkout xuất phát từ message bus. Vì vậy không tự coi hai counters phải luôn bằng nhau.

## 20. Actuator và exporter-specific tests

`spring-boot-starter-actuator` cung cấp metrics infrastructure, nhưng để xem metrics qua HTTP endpoint, cần web stack và exposure configuration. Để export Prometheus, còn cần module exporter như `micrometer-registry-prometheus` và quyền expose endpoint theo security policy.

Ví dụ mở rộng, **không thuộc runnable project gốc**:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Ví dụ application.properties:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Chạy application với web starter, tạo một checkout event, sau đó scrape `/actuator/prometheus` từ HTTP client/test tool. Lưu ý: Boot app gốc chưa có HTTP route gọi CheckoutService; muốn tạo events trong live app cần controller/runner có chủ đích hoặc test method invoke service rồi request actuator endpoint. Đừng tuyên bố sample output trên giấy là đã được exporter thực sinh ra.

### 20.1. Testing external exporters

- Prometheus: test scrape text format và labels, exporter module/version đúng.
- Datadog/OTLP/StatsD: kiểm tra publishing steps, credentials, endpoints, retries và collector/test server theo backend.
- Multi-instance: query tổng hợp với instance/pod tags, không so một process Counter.count() với tổng cluster.
- Dashboard/alerts: cần E2E integration hoặc manual verification query và thresholds.

**Simple registry pass ≠ exporter pass**; đó là hai boundary khác nhau.

## 21. Spring Boot testing behavior

Spring Boot 3.3 tests thường có in-memory MeterRegistry khi Actuator present, nhưng external exporting registries không mặc định được auto-configure trong `@SpringBootTest`. `@AutoConfigureObservability` có thể được dùng để kích hoạt observability auto-configuration trong slices hoặc khi cần export theo chủ đích.

Nếu `@WebMvcTest`/`@WebFluxTest` slice không có MeterRegistry bean, đó có thể là do slice scope/auto-configuration, không chứng minh production thiếu metrics. Dùng test registry bean hoặc test annotation phù hợp mục tiêu.

### 21.1. Metrics disabled

Nếu cấu hình `management.metrics.enable.checkout=false` hoặc MeterFilter deny prefix, custom meters có thể không hiện ra. Test đúng phải fail khi metric contract bị tắt, trừ khi đây là môi trường intentionally metrics-disabled và test expectations được đổi rõ.

### 21.2. Spring context reuse

TestContext cache giữ Spring beans và metrics state. Delta assertions tránh phụ thuộc vào count chính xác trước method. Không lạm dụng `@DirtiesContext` cho mọi metrics test; nó tốn thời gian và có thể làm environment startup không ổn định hơn. Fresh SimpleMeterRegistry per unit test là chiến lược chính.

### 21.3. Không xóa toàn bộ meter registry bằng clear

`MeterRegistry.clear()` xóa mọi registered meters, không chỉ custom checkout series. Khi framework binder giữ references, registry clear giữa methods có thể làm metrics sau đó không phản ánh đúng. Nếu cần test reset, dùng registry riêng hoặc unregister targeted test-owned meters trong context có kiểm soát.

## 22. Async/retry semantics

### 22.1. Reactive Publisher assembly không phải execution

Sai:

```java
Timer.Sample sample = Timer.start(registry);
Mono<String> mono = actualReactiveOperation();
sample.stop(timer);
return mono;
```

**Snippet minh họa**, `actualReactiveOperation()`/registry/timer phải được cung cấp. Nó đo thời gian tạo publisher, không đo async response. Với reactive cần wrap trong `Mono.defer` rồi stop tại `doFinally` hoặc dùng Observation instrumentation hỗ trợ reactive lifecycle.

Ví dụ hướng tiếp cận:

```java
Mono<String> publisher = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);
    return actualReactiveOperation()
            .doFinally(signal -> {
                Timer t = Timer.builder("reactive.duration")
                        .tag("signal", signal.name())
                        .register(registry);
                sample.stop(t);
            });
});
```

Đây là snippet chưa đủ dependencies/method definitions; không nằm trong lab. `signal` có bounded enum values, nhưng cần thiết kế cách phân biệt success/error/cancel và tránh đo hai lần khi retry/resubscribe.

### 22.2. Retries

Một logical checkout có thể có 1–N attempts. Đừng ghi metric logical success/error trên mỗi retry attempt nếu dashboard muốn đếm yêu cầu business. Counter `attempts` và `logical.requests` là hai metrics độc lập. Tests cần assert đúng scopes.

### 22.3. Parallel updates

Micrometer metrics updates thường thread-safe theo implementations, nhưng một unit test đo delta trên shared registry vẫn có thể sai nếu requests khác cập nhật cùng series đồng thời. Test isolation là trách nhiệm của test design, không được “chữa” bằng sleep/retry test chạy lại.

## 23. Cách đọc lỗi

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| registry.find(...).counter() null | Sai metric name/tag hoặc code chưa chạy | Query chính xác name+tags, gọi service |
| Count luôn 0 | Code update registry khác/global | Constructor inject cùng MeterRegistry |
| Unit test riêng xanh, chạy suite đỏ | Registry static/context cached | Fresh per test hoặc delta |
| Timer count 0 | Sample chưa stop | finally + đúng timer ID |
| Error counter 0 | Catch không đổi outcome hoặc flow trả error khác | Test negative path |
| Timer total milliseconds sai | Sai TimeUnit/JVM timing | MockClock/record(Duration) |
| Timer.max giảm | Time-window max expiration | Đừng assert historical max |
| Có meter nhưng tags sai | Spelling/case/key drift | Assert getId().getTag |
| Too many time series | orderId/userId/raw URI tag | Cardinality policy + MeterFilter |
| Prometheus không thấy counter | Exporter thiếu/endpoint chưa exposed | Test exporter/Actuator riêng |
| Prometheus series khác tên Java | Naming conventions/_total suffix | Kiểm tra backend-specific name |
| @Timed không tạo timer | Thiếu TimedAspect/Observation | Cấu hình instrumentation |
| Metrics mất trong @WebMvcTest | Slice không include metrics bean | @AutoConfigureObservability/test bean |
| Histogram _bucket không có | Histogram/SLO chưa bật | Distribution config |
| Timer của Mono rất nhỏ | Đang đo publisher assembly | Measure subscription/terminal |
| Timer.count khác Counter.count | Hai scopes khác nhau hoặc double record | Rà semantics |
| Request ID xuất hiện trong tag | High-cardinality design bug | Dùng traces/logs |
| Negative test pass vì metrics bị deny | Only null assertion | Thêm positive assertion |
| Test đo 401/500 nhưng metric success | Outcome mapping sai | Paired success/error tests |

## 24. Bài tập thực hành

1. **Bỏ Counter.increment()** trong CheckoutService. Success test phải fail dù gateway trả đúng value.
2. **Bỏ sample.stop(...)**. Timer count assertion phải fail.
3. **Bỏ result = "error" trong catch**. Error test phát hiện series bị gắn nhãn success.
4. **Ghi metrics cả catch và finally**. Test counter/timer count cho thấy double-count.
5. **Thêm orderId tag**. Test cardinality guard phải fail; bỏ tag đó.
6. **Đổi result tag name thành outcome**. Test lookup name+tag fail; update contract có chủ đích nếu dashboard thay đổi.
7. **Thêm 3 success calls**. Dự kiến success counter=3, timer.count=3.
8. **MockClock advance 250ms**. Đổi expected totalTime thành 250ms, không dùng Thread.sleep.
9. **Timer synthetic 120+80ms**. Đọc TimeUnit.SECONDS, expected 0.2; không nhầm đơn vị.
10. **Dùng registry static chung**. Quan sát cách counts từ test trước ảnh hưởng tests sau; khôi phục @BeforeEach registry mới.
11. **Dùng Metrics.globalRegistry trong service**. Unit registry find không còn meter, giải thích sai dependency injection.
12. **Thêm Common tags**. Dùng MeterRegistryCustomizer bean trong Spring config test; verify application tag.
13. **@Timed arbitrary method**. Không thêm Aspect mà assert timer, quan sát không auto magically appear.
14. **Prometheus exporter**. Thêm module và web starter/test endpoint rồi query actual scrape; phân biệt với Simple registry.
15. **Histogram/SLO**. Bật distribution config cho checkout.duration; kiểm tra bucket cost và output.
16. **Retry gateway**. Định nghĩa logical counter và attempts counter; assert 1 logical checkout + 3 outbound attempts.
17. **Async Mono**. So sánh đo assembly time với subscriber completion time.
18. **Multiple outcomes**. Thêm enum outcome rejected/timeout và tests; không dùng raw exception messages.
19. **Check process metrics**. Khi Actuator bật, registry còn có JVM/process metrics. Không gọi clear toàn registry chỉ để test custom checkout.
20. **Dashboard contract**. Lập tài liệu metric name, unit, tag keys/values, alert query, owner và migration plan cho mỗi thay đổi.

## 25. Checklist QA trước khi merge

- [ ] Business instrumentation dùng `MeterRegistry` injected, không static global.
- [ ] Counter đo đúng logical event, chỉ tăng.
- [ ] Timer.Sample start/stop đúng một lần trên success/error.
- [ ] Timer có count/totalTime được xác minh với TimeUnit rõ.
- [ ] Unit timings deterministic qua Duration/MockClock, không assert wall time exact.
- [ ] Error path tạo series result=error, không cộng vào success.
- [ ] Positive và negative metrics assertions có mặt.
- [ ] Lookup meter theo đúng name và tags, không dựa vào vị trí list.
- [ ] Tags không chứa orderId/userId/requestId/raw URI/PII.
- [ ] Tag names/values bounded, stable, documented.
- [ ] Không dùng cùng name/tags cho meter types xung đột.
- [ ] Unit tests dùng new SimpleMeterRegistry mỗi method.
- [ ] @AfterEach close registry, không làm rò global state.
- [ ] SpringBootTest đo delta với injected registry.
- [ ] Không clear toàn Spring-managed registry để reset count.
- [ ] Parallel tests không cùng sửa shared meter series nếu đo delta.
- [ ] Timer.count được tính tới; không double-count với Counter.
- [ ] Common tags/MeterFilters được test ở context khi là contract.
- [ ] @Timed arbitrary method cần aspect/Observation instrumentation thật.
- [ ] Async/reactive metric đo subscription completion, không chỉ assembly.
- [ ] External exporter được test riêng nếu cần proof networking/export.
- [ ] Không coi SimpleMeterRegistry pass là Prometheus/Datadog verified.
- [ ] Histogram/percentiles/SLO chỉ bật có chủ đích và budget.
- [ ] Actuator endpoint exposure có security review.
- [ ] Báo executed/passed/failed/skipped từ JUnit report thật.
- [ ] Version Spring Boot/Micrometer/backend và naming conventions được theo dõi khi upgrade.

## 26. Quy tắc lựa chọn kiểm thử

```text
Cần kiểm tra gì?
      |
      +-- Business counter / timer / tags?
      |      -> JUnit + SimpleMeterRegistry per test.
      |
      +-- Exact durations?
      |      -> Timer.record(Duration) / MockClock.
      |
      +-- Spring-managed registry?
      |      -> @SpringBootTest + delta assertions.
      |
      +-- @Timed / Observation?
      |      -> Verify aspect/handlers + Spring bean proxy.
      |
      +-- Prometheus naming/export/histogram?
      |      -> Concrete exporter + scrape integration test.
      |
      +-- Monitoring backend/scraper/alerts?
             -> Dedicated staging/deployment verification.
```

**Tóm tắt:** Counter theo dõi sự kiện, Timer theo dõi count và elapsed time, tags phân chia series. `SimpleMeterRegistry` cho unit tests xác minh Micrometer behavior thật mà không cần network; `MockClock` làm phép đo chính xác, không flaky. `@SpringBootTest` kiểm chứng Spring bean wiring bằng before/after delta. Thiết kế tags bounded, có error path và không dùng `Metrics.globalRegistry` một cách vô ý. Nếu mục tiêu là exporter, phải test thêm concrete backend; không suy diễn từ in-memory registry.

## 27. Tài liệu chính thức

- Spring Boot 3.3 — Metrics và auto-configured MeterRegistry: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Testing, observability và @AutoConfigureObservability: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Micrometer — Registry và SimpleMeterRegistry: https://docs.micrometer.io/micrometer/reference/concepts/registry.html
- Micrometer — Counters: https://docs.micrometer.io/micrometer/reference/concepts/counters.html
- Micrometer — Timers và Timer.Sample: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Naming conventions: https://docs.micrometer.io/micrometer/reference/concepts/naming.html
- Micrometer — Histograms và percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Micrometer — Gauges: https://docs.micrometer.io/micrometer/reference/concepts/gauges.html
- Micrometer — MeterFilters và tag cardinality policy: https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html
- Micrometer — Observation components: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — API Javadoc: https://javadoc.io/doc/io.micrometer/micrometer-core/
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — User guide: https://docs.junit.org/current/user-guide/
