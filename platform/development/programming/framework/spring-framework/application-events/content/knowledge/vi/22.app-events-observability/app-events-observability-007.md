# Metric số lần phát event

## 1. Đếm “phát event” nghĩa là đếm điều gì?

Trong Spring Framework Application Events, một service có thể gọi `ApplicationEventPublisher.publishEvent(...)` để thông báo một sự việc nghiệp vụ: `OrderPlaced`, `PaymentCaptured`, `CustomerRegistered`. Khi hệ thống phát triển, câu hỏi vận hành thường là:

- Mỗi phút ứng dụng công bố bao nhiêu event?
- Loại event nào tăng đột biến hoặc ngừng xuất hiện?
- Có bao nhiêu lời gọi `publishEvent(...)` ném lỗi?
- Có phải tất cả event đã được listener xử lý thành công?
- Event được công bố trong transaction nhưng cuối cùng transaction rollback thì đếm thế nào?

**Câu trả lời phải bắt đầu từ định nghĩa metric.** “Đã gọi publisher” khác “publisher trả về bình thường”, “listener chạy” và “sự việc đã commit”. Một metric đơn lẻ không nên được diễn giải thay cho cả bốn trạng thái.

Ví dụ:

~~~text
PlaceOrder command
      |
      v
Application service
      |
      +-- publishEvent(OrderPlaced #101)  <--- đếm publish attempt
                 |
                 +-- @EventListener A     <--- có thể đếm listener invocation
                 |
                 +-- @EventListener B     <--- invocation thứ hai
                 |
                 +-- @Async listener C    <--- xử lý về sau, có thể thất bại
      |
      v
Transaction commit / rollback   <--- trạng thái nghiệp vụ độc lập
~~~

Trong ví dụ này, **một lần gọi publisher có thể kích hoạt nhiều listener**; ngược lại, một lần publish chưa chắc làm listener chạy ngay (đặc biệt với listener transaction-bound). Nếu tổng số invocation của ba listener là 3, đó **không phải** ba event đã được phát.

Mục tiêu của bài học: dùng **Micrometer `Counter`** để đo số lần phát event theo định nghĩa rõ ràng, phân loại bằng tag có cardinality thấp, tránh đếm trùng và xây dashboard có thể giải thích đúng.

## 2. Các mức đo nên đặt tên khác nhau

| Metric logic | Điểm tăng bộ đếm | Trả lời câu hỏi |
| --- | --- | --- |
| `event.publish.attempts` | Ngay trước khi gọi `publishEvent` | Có bao nhiêu lần ứng dụng thử công bố event qua entry point đã instrument? |
| `event.publish.calls` + tag `outcome=returned` | Sau khi `publishEvent` trả về bình thường | Có bao nhiêu lời gọi publisher **trả về**, không khẳng định tất cả listener thành công? |
| `event.publish.calls` + `outcome=threw` | Khi lời gọi `publishEvent` ném exception về thread hiện tại | Bao nhiêu lời gọi kết thúc bằng exception trực tiếp? |
| `event.listener.invocations` | Ngay trước khi bắt đầu một listener cụ thể | Listener đó đã được gọi bao nhiêu lần? |
| `event.listener.results` + success/error | Khi việc xử lý của listener **thật sự hoàn tất** | Bao nhiêu lần listener xử lý xong/thất bại? |
| `event.transaction.committed` | Khi nghiệp vụ/transaction xác nhận commit thành công | Có bao nhiêu sự việc đã được lưu bền vững theo hợp đồng này? |
| `integration.event.sent` | Sau kết quả gửi được transport xác nhận theo hợp đồng | Có bao nhiêu message đã được chấp nhận ở biên tích hợp? |

Đây là **tên metric gợi ý do ứng dụng tự tạo**, không phải tên chuẩn được Spring Framework tự động sinh ra cho mọi `ApplicationEventPublisher`.

Trong các ví dụ chính, dùng hai metric do mình quản lý:

1. **`demo.events.publish.attempts`**: tăng đúng một lần trước mỗi lời gọi thông qua wrapper.
2. **`demo.events.publish.calls`**: tăng một lần khi lời gọi hoàn tất, phân loại tag `outcome=returned` hoặc `outcome=threw`.

Vì vậy:

~~~text
attempts ~= calls{returned} + calls{threw}
~~~

Đẳng thức trên chỉ đúng khi mọi lời gọi đã **hoàn tất**, không bị tiến trình dừng giữa chừng, và tất cả đường phát event đều đi qua cùng wrapper. Nó không phải đẳng thức số lượng event nghiệp vụ đã commit.

**Đừng cộng `attempts` với các series `calls`** để suy ra “tổng event”: đó là hai phép đo của **cùng các lần gọi** ở hai thời điểm khác nhau.

## 3. Micrometer Counter: công cụ phù hợp để đếm

Micrometer cung cấp `MeterRegistry` và `Counter`. Mỗi lần gọi `increment()` làm counter tăng; counter phù hợp với những hiện tượng có số lần xảy ra tăng dần, chẳng hạn số lần service yêu cầu phát event. Counter không dùng để biểu diễn “bao nhiêu task đang chạy” (đó có thể là gauge) hay latency.

Ví dụ API cốt lõi:

~~~java
// Đoạn minh họa cần một MeterRegistry được cấu hình.
Counter published = Counter.builder("app.events.publish.attempts")
    .description("Attempts to publish application events")
    .tag("event_type", "order_placed")
    .register(meterRegistry);

published.increment();
~~~

Một `MeterRegistry` giữ các meter theo **tên và tập tag**. Đăng ký lại cùng tên + tag thường truy xuất cùng meter, không sinh một metric mới cho mỗi lời gọi. Trong ứng dụng tải cao, có thể lưu/cached reference tới các Counter có tập nhãn hữu hạn thay vì xây builder liên tục; tuyệt đối tránh tạo một tag value mới cho từng order ID.

**Counter của Micrometer không có ý nghĩa “tổng sự kiện toàn hệ thống kể từ đầu lịch sử”**: giá trị cục bộ có thể reset khi process restart và khác nhau giữa instance. Trên backend như Prometheus, ưu tiên phân tích **rate/increase trên khoảng thời gian** rồi cộng giữa các instance khi cần, thay vì so sánh số đếm thô của một process sống lâu với process vừa restart.

Micrometer khuyến nghị: nếu đã dùng `Timer` hoặc `DistributionSummary` để đo cùng thao tác, chúng vốn có **count**. Không tạo thêm counter trùng ý nghĩa chỉ vì muốn biết số lần hoàn thành, trừ khi định nghĩa khác nhau một cách có chủ đích (ví dụ `publish.attempts` đo trước lời gọi, còn timer đo thời lượng những lời gọi đã hoàn tất).

## 4. Đếm ở đâu để không đếm thiếu hoặc đếm trùng?

Có ba vị trí phổ biến:

### A. Instrument tại service gọi publisher

~~~java
// Minh họa; là một phần application service, không phải file độc lập.
counter.increment();
eventPublisher.publishEvent(new OrderPlaced(orderId));
~~~

Ưu điểm: đơn giản, thể hiện đúng nghiệp vụ. Nhược điểm: developer dễ quên ở service khác, hoặc một sự việc có nhiều code path đi qua publisher nhưng không được instrument.

### B. Tạo wrapper/decorator cho ApplicationEventPublisher

~~~text
OrderService
    -> MeteredPublisher.publish(event)
        -> increment attempts
        -> delegate.publishEvent(event)
        -> increment outcome=returned / threw
~~~

Ưu điểm: **một entry point** cho nhiều loại domain event. Hạn chế: mọi code path phải sử dụng wrapper này; các event do Spring Framework tự phát (ví dụ lifecycle events) hoặc code gọi thẳng vào `ApplicationEventPublisher` sẽ **không đi qua wrapper** và **không được tính**.

Đây là cách được dùng ở demo mục 6 vì định nghĩa và điểm đo rõ ràng. Tránh đặt một bean kiểu `ApplicationEventPublisher` mới rồi vô tình làm Spring tự inject chính wrapper vào nó; hãy dùng một **facade riêng** (ví dụ `MeteredPublisher`) nhận `ApplicationEventPublisher` gốc qua constructor.

### C. Instrument ở ApplicationEventMulticaster

Có thể mở rộng/customize multicaster để quan sát các lần dispatch hoặc invocation. Tuy nhiên, lúc này cần phân biệt:

- Một publication có thể gặp nhiều listener.
- Multicaster có thể dispatch đồng bộ hoặc dùng executor; callback có thể bị từ chối/được chạy về sau.
- `ApplicationListener.supportsAsyncExecution()` có thể khiến một số listener (như transaction-synchronized listener) không được chuyển sang executor chung.
- Custom multicaster có thể làm thay đổi hành vi mặc định và dễ ảnh hưởng event nội bộ của Spring.

Nếu mục tiêu chỉ là **đếm lời gọi publish của domain**, wrapper ở biên application thường đơn giản và ít rủi ro hơn.

## 5. Thiết kế tag: đo theo loại event, không theo từng ID

Micrometer hỗ trợ các tag để phân nhóm metric. Chọn **cardinality thấp**, tức số giá trị mỗi tag được kiểm soát và không tăng theo mỗi request/event.

| Tag | Nên dùng? | Lý do |
| --- | --- | --- |
| `event_type=order_placed / payment_captured` | **Có** | Tập loại event được định nghĩa hữu hạn |
| `outcome=returned / threw` | **Có** | Hai kết quả rời rạc của lời gọi |
| `service=checkout` | Có, nếu cần và được cấu hình thống nhất | Giá trị đến từ danh mục service |
| `environment=prod / staging` | Có, nếu backend chưa gắn nhãn sẵn | Danh mục môi trường hữu hạn |
| `event_id=UUID` | **Không** | Một giá trị mới cho mỗi event, gây bùng nổ time series |
| `order_id=101 / 102 / ...` | **Không** | Tăng theo đơn hàng |
| `customer_id / user_id / tenant_id` tùy ý | **Không** | Cardinality cao và có thể lộ thông tin nhạy cảm |
| `correlation_id / trace_id` | **Không** | Một ID cho mỗi workflow/trace, nên ở log/trace |
| `exception_message` | **Không** | Giá trị tự do, dễ lộ dữ liệu và khó kiểm soát |

Nếu muốn tag `exception`, nên map về **một danh mục lỗi hữu hạn** như `validation`, `downstream`, `unexpected`, không đưa nguyên thông điệp hoặc stack trace vào tag.

Đừng lấy `event.getClass().getName()` làm nhãn mà không giới hạn tập loại: trong những hệ thống có proxy/generated classes hoặc payload tùy ý, điều đó có thể tăng cardinality. Tốt hơn là có mapping cho các event nghiệp vụ được phép đếm, và nhóm phần còn lại thành `other`.

Số lượng time series tăng theo **tích** của các nhóm tag. Ví dụ 20 `event_type` × 3 `outcome` × 5 `service` × 3 `environment` đã có **900 tổ hợp** (chưa tính instance). Việc bổ sung `order_id` biến con số đó thành rất lớn và tốn chi phí lưu trữ/truy vấn.

## 6. Ví dụ chạy được: Spring Framework + Micrometer

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.19**, **Micrometer Core 1.15.12**. Không cần Spring Boot hoặc web server; metric được lưu trong `SimpleMeterRegistry` để đối chiếu chính xác.

Luồng demo:

1. Publish `OrderPlaced(101)`: listener đồng bộ xử lý bình thường.
2. Publish `OrderPlaced(102)`: listener cố ý ném lỗi; wrapper ghi `outcome=threw` và ném tiếp lỗi về caller.
3. Publish `PaymentCaptured(101)`: listener đồng bộ xử lý bình thường.
4. In các Counter chứng minh **số lần thử publish**, **lời gọi trả về** và **lời gọi ném lỗi** là các con số khác nhau.

### Cấu trúc

~~~text
spring-event-metrics/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/EventMetricsDemo.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'spring-event-metrics'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'io.micrometer:micrometer-core:1.15.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EventMetricsDemo'
}
~~~

### src/main/java/demo/EventMetricsDemo.java

~~~java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

@Configuration
public class EventMetricsDemo {

    public record OrderPlaced(long orderId) {}
    public record PaymentCaptured(long orderId) {}

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    MeteredPublisher meteredPublisher(
            ApplicationEventPublisher publisher,
            MeterRegistry registry) {
        return new MeteredPublisher(publisher, registry);
    }

    @Bean
    DomainListeners domainListeners() {
        return new DomainListeners();
    }

    public static class DomainListeners {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            if (event.orderId() == 102L) {
                throw new IllegalStateException(
                    "simulated listener failure");
            }
            System.out.println("handled order " + event.orderId());
        }

        @EventListener
        public void onPaymentCaptured(PaymentCaptured event) {
            System.out.println("handled payment " + event.orderId());
        }
    }

    public static class MeteredPublisher {
        private final ApplicationEventPublisher delegate;
        private final MeterRegistry registry;

        public MeteredPublisher(ApplicationEventPublisher delegate,
                                MeterRegistry registry) {
            this.delegate = delegate;
            this.registry = registry;
        }

        public void publish(Object event) {
            Objects.requireNonNull(event, "event");
            String type = eventType(event);

            // Tăng trước lời gọi, kể cả khi listener sẽ ném lỗi.
            Counter.builder("demo.events.publish.attempts")
                .description("Publication attempts through this facade")
                .tag("event_type", type)
                .register(registry)
                .increment();

            try {
                delegate.publishEvent(event);

                // Chỉ có nghĩa: publishEvent trả về bình thường.
                outcome(type, "returned");
            } catch (RuntimeException | Error ex) {
                // Lỗi đồng bộ xuất hiện ngay tại lời gọi publisher.
                outcome(type, "threw");
                throw ex;
            }
        }

        private void outcome(String type, String value) {
            Counter.builder("demo.events.publish.calls")
                .description("Completed publish calls by exit outcome")
                .tags("event_type", type, "outcome", value)
                .register(registry)
                .increment();
        }

        // Chỉ cho phép một tập tag hữu hạn do ứng dụng định nghĩa.
        private static String eventType(Object event) {
            if (event instanceof OrderPlaced) {
                return "order_placed";
            }
            if (event instanceof PaymentCaptured) {
                return "payment_captured";
            }
            return "other";
        }
    }

    private static long attempts(
            MeterRegistry registry, String type) {
        return Math.round(registry
            .get("demo.events.publish.attempts")
            .tag("event_type", type)
            .counter()
            .count());
    }

    private static long calls(
            MeterRegistry registry, String type, String outcome) {
        return Math.round(registry
            .get("demo.events.publish.calls")
            .tags("event_type", type, "outcome", outcome)
            .counter()
            .count());
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                EventMetricsDemo.class)) {

            var publisher = context.getBean(MeteredPublisher.class);
            var registry = context.getBean(MeterRegistry.class);

            publisher.publish(new OrderPlaced(101L));

            try {
                publisher.publish(new OrderPlaced(102L));
            } catch (RuntimeException ex) {
                System.out.println("caught publish 102");
            }

            publisher.publish(new PaymentCaptured(101L));

            System.out.println(
                "order attempts=" + attempts(registry, "order_placed"));
            System.out.println(
                "order returned=" + calls(
                    registry, "order_placed", "returned"));
            System.out.println(
                "order threw=" + calls(
                    registry, "order_placed", "threw"));
            System.out.println(
                "payment attempts=" + attempts(
                    registry, "payment_captured"));
            System.out.println(
                "payment returned=" + calls(
                    registry, "payment_captured", "returned"));
        }
    }
}
~~~

### Chạy

Với JDK 17+ và Gradle:

~~~bash
gradle run --quiet
# Nếu có Gradle Wrapper: ./gradlew run --quiet
# Windows nếu có wrapper: gradlew.bat run --quiet
~~~

Các dòng được in bằng `System.out` của demo (không tính log ngoài chương trình):

~~~text
handled order 101
caught publish 102
handled payment 101
order attempts=2
order returned=1
order threw=1
payment attempts=1
payment returned=1
~~~

### Vì sao số liệu này đúng?

- `OrderPlaced(101)`: wrapper tăng **attempts 1**, listener chạy xong, `publishEvent` trả về, wrapper tăng **returned 1**.
- `OrderPlaced(102)`: wrapper tăng **attempts thêm 1**, listener đồng bộ ném `IllegalStateException`; `SimpleApplicationEventMulticaster` mặc định không có error handler và không dùng executor, nên lỗi lan về lời gọi publish. Wrapper tăng **threw 1**, caller bắt lỗi.
- `PaymentCaptured(101)`: wrapper tăng **payment attempts 1** và **payment returned 1** sau khi listener xử lý xong.
- Counter theo `event_type` chỉ có các nhóm `order_placed` và `payment_captured` trong các lời gọi demo. Không có tag `order_id` nên không có time series theo từng đơn.
- Lỗi của listener 102 **không chứng minh event không được giao**: listener đã bắt đầu thực thi và ném lỗi. Metric `outcome=threw` chỉ mô tả kết quả của lời gọi publisher từ góc nhìn caller.

**Giới hạn của ví dụ:** demo chỉ dùng event nội bộ synchronous, không có database, transaction hay broker. Không được suy diễn metric `returned` là “đơn đã commit” hoặc “mọi xử lý bất đồng bộ đã thành công”.

## 7. Khi listener dùng @Async, metric publish đo được gì?

Với listener thông thường chạy đồng bộ, `SimpleApplicationEventMulticaster` mặc định gọi listener trong thread của publisher. Lỗi từ listener có thể lan ngược về publisher, như demo trên.

Khi có `@Async @EventListener` hoặc multicaster dùng executor, publisher thường **trả về trước khi listener hoàn tất**. Lúc đó:

~~~text
publishEvent(OrderPlaced)
    |
    +-- executor nhận task
    |     |
    |     +------ @Async listener chạy sau
    |                       |
    |                       +-- success / failure
    |
    +-- publishEvent có thể return trước bước trên
          |
          +-- metric outcome=returned tăng
~~~

Nếu listener chạy sau đó bị lỗi, **không thể dùng `outcome=threw` của wrapper để suy ra số lượng lỗi xử lý**. Ngoại lệ phát sinh ở task async cần quan sát tại listener, executor, `AsyncUncaughtExceptionHandler` hoặc cơ chế xử lý kết quả phù hợp.

Để quan sát listener, instrument tại **biên xử lý thực tế**:

~~~java
// Đoạn minh họa trong một bean, không phải file độc lập.
@Async
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Counter.builder("app.event.listener.invocations")
        .tags("listener", "order_notification",
              "event_type", "order_placed")
        .register(registry)
        .increment();

    try {
        notificationGateway.enqueue(event.orderId());

        Counter.builder("app.event.listener.results")
            .tags("listener", "order_notification",
                  "outcome", "success")
            .register(registry)
            .increment();
    } catch (RuntimeException ex) {
        Counter.builder("app.event.listener.results")
            .tags("listener", "order_notification",
                  "outcome", "error")
            .register(registry)
            .increment();
        throw ex;
    }
}
~~~

Đoạn trên giả định bean có `MeterRegistry registry`, `NotificationGateway notificationGateway` và các import/kiểu event tương ứng. **Không phải chương trình biên dịch độc lập**. Với handler trả `Mono`/`Flux`, phải đặt instrument tại tín hiệu hoàn tất/lỗi của reactive pipeline, không ở thời điểm tạo publisher; `Mono` có thể chưa được subscribe.

Đếm listener theo từng handler cũng có nghĩa **một event có thể tạo nhiều invocation**. Không nên cộng tổng invocation của các listener rồi gọi đó là “số lần phát event”.

## 8. Khi @TransactionalEventListener tham gia, cần phân biệt publication và commit

`@TransactionalEventListener` đăng ký xử lý theo phase transaction, ví dụ `AFTER_COMMIT`. Lời gọi `publishEvent(...)` có thể xảy ra **trước khi transaction commit**:

~~~text
BEGIN T1
  save(order)
  publishEvent(OrderPlaced)   -> attempt +1
  ...
ROLLBACK T1                  -> AFTER_COMMIT listener không chạy
~~~

Do đó:

- `publish.attempts` đã tăng 1; nó đo **lời gọi**, không đo commit.
- `outcome=returned` có thể cũng tăng: lời gọi publisher trả về bình thường sau khi đăng ký synchronization.
- `AFTER_COMMIT` listener **không chạy** vì T1 rollback.
- Không được lấy metric publish trả về bình thường làm bằng chứng đã có bản ghi đơn hàng trong database.

Nếu muốn đếm **event mà việc xử lý hậu commit bắt đầu**, có thể instrument trực tiếp trong listener:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    registry.counter("app.events.after_commit.invocations",
        "event_type", "order_placed").increment();
    // Gọi xử lý hậu commit...
}
~~~

Cần phân biệt: metric trên đếm **callback AFTER_COMMIT được gọi**, không bảo đảm một công việc phụ đã hoàn tất, và không phải số transaction đã commit (một transaction có thể công bố nhiều event, không có event hoặc nhiều event cùng loại).

Các chú ý thêm:

- Listener `@TransactionalEventListener` mặc định bỏ qua event **ngoài transaction** khi `fallbackExecution=false`. Bật fallback thay đổi ngữ nghĩa: chạy ngoài transaction không còn là after-commit.
- Callback sau commit xảy ra khi transaction gốc đã commit; lỗi listener không thể tự rollback T1. Muốn ghi DB từ callback có thể cần transaction độc lập rõ ràng.
- Với reactive transaction từ Spring Framework 6.1+, transaction context nằm trong **Reactor Context**. `TransactionalEventPublisher` hỗ trợ gắn `TransactionContext` vào event source; đếm ở wrapper đồng bộ không tự chứng minh reactive chain đã subscribe hoặc transaction đã commit.
- Khi cần bảo đảm không mất event sau crash, dùng **transactional outbox**: ghi outbox cùng transaction nghiệp vụ, rồi đếm riêng event được worker gửi/ACK. Counter trong bộ nhớ không thay thế event log bền vững.

## 9. Tích hợp Spring Boot Actuator và backend monitoring

Trong Spring Boot, Actuator có thể auto-configure `MeterRegistry` cho Micrometer. Khi đã inject `MeterRegistry`, có thể dùng cùng kỹ thuật wrapper hoặc ghi counter tại application service.

Maven dependencies thường cần:

~~~xml
<!-- Minh họa khi dùng Spring Boot với BOM quản lý version -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Chỉ thêm khi muốn Prometheus scrape format -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Ví dụ cấu hình tùy chọn:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
~~~

Lúc chạy, có thể kiểm tra metric qua endpoint `/actuator/metrics/demo.events.publish.attempts` (theo **tên Micrometer** trong code), lọc bằng query parameter `tag=event_type:order_placed`. Nếu có Prometheus registry và endpoint được bật, `/actuator/prometheus` hiển thị time series theo quy ước tên của backend.

**Không mặc định kỳ vọng Actuator tự tạo `demo.events.publish.attempts`:** tên này do ứng dụng instrument mới xuất hiện. Ứng dụng Spring Framework thuần trong demo không dùng Actuator, nên in từ `SimpleMeterRegistry`.

**Bảo mật:** chỉ expose endpoint cần thiết theo môi trường và áp dụng chính sách auth/network phù hợp; metrics có thể tiết lộ thông tin vận hành dù không chứa ID cá nhân.

### Gợi ý PromQL cho tốc độ publish

Với Prometheus, một Counter tên Micrometer `demo.events.publish.attempts` thường xuất hiện dưới tên kiểu `demo_events_publish_attempts_total` (tên cụ thể phụ thuộc registry, naming convention và phiên bản). Sau khi xác minh tên thật ở endpoint scrape, có thể dùng:

~~~promql
sum by (event_type) (
  rate(demo_events_publish_attempts_total[5m])
)
~~~

Kết quả là **số attempt trung bình mỗi giây trong 5 phút**, không phải tổng cộng tuyệt đối từ lúc hệ thống khởi động. Muốn tổng số attempt trong 5 phút, cân nhắc `increase(...[5m])`. Với nhiều instance, `sum` tổng hợp các time series nhưng vẫn cần kiểm tra label và cách scrape.

Để theo dõi tỷ lệ lỗi của **lời gọi publisher** (không phải lỗi async listener), có thể phân tích:

~~~promql
sum(rate(demo_events_publish_calls_total{outcome="threw"}[5m]))
/
clamp_min(
  sum(rate(demo_events_publish_calls_total[5m])),
  1e-9
)
~~~

Đây chỉ là **tỷ lệ lời gọi publisher ném lỗi trên các lời gọi hoàn tất**, không chứng minh tỷ lệ xử lý domain thất bại. Không dùng nó thay cho báo cáo handler error hoặc dead-letter queue.

## 10. Các lỗi đo lường phổ biến

### Sai 1 — Tăng counter trong từng listener rồi gọi đó là “event đã phát”

Một event được nhận bởi ba listener có thể làm counter tăng ba. Đúng hơn là đặt counter publication tại **một entry point** và đặt metric listener riêng, với tên/scope rõ ràng.

### Sai 2 — Đếm returned là tất cả listener đều thành công

Với `@Async`, transaction-bound listener hoặc custom multicaster, `publishEvent` trả về không có nghĩa handler chạy xong. Dùng metric handler completion riêng.

### Sai 3 — Tạo metric theo ID duy nhất mỗi event

~~~java
// Anti-pattern minh họa (không phải chương trình độc lập).
Counter.builder("app.events.publish.attempts")
    .tag("event_id", event.id().toString())
    .register(registry)
    .increment();
~~~

Mỗi event ID mới tạo time series mới. Đưa `eventId`, `correlationId` vào **structured logs hoặc tracing spans**, không vào metric label.

### Sai 4 — Đếm publish như số sự việc đã commit

Nếu event được publish trong transaction nhưng T1 rollback, counter vẫn tăng. Cần metric hậu commit hoặc số liệu domain bền vững (cơ sở dữ liệu/outbox) nếu nghiệp vụ đòi sự kiện đã lưu.

### Sai 5 — Tăng counter cả trong wrapper lẫn service rồi cộng như nhau

Khi service gọi wrapper, một event có thể được đo hai lần nếu cả hai nơi cùng tăng `app.events.publish.attempts`. Chọn **một điểm sở hữu phép đo**, tránh dùng hai metric cùng tên nhưng định nghĩa khác nhau.

### Sai 6 — Dùng Counter thay cho số công việc đang chờ

Counter chỉ tăng. Đối với queue depth, số job đang chạy hoặc số event pending, chọn gauge/long-task timer hoặc số liệu trạng thái phù hợp, thay vì cố trừ counter hoặc đặt tên nhầm.

### Sai 7 — Quên retry và duplicate delivery

`publish.attempts` tăng mỗi **lần thử**. Nếu retry gửi cùng event ba lần, số attempt có thể là 3 dù chỉ một business event ID. Nếu mục tiêu là unique business events, cần dữ liệu ID bền vững/deduplication rõ ràng, không thể suy từ Counter đơn giản.

### Sai 8 — Chỉ theo dõi Counter mà không theo dõi lỗi xử lý

Một service có thể publish đều đặn trong khi mọi handler async đều thất bại. Kết hợp publish rate, listener success/error, latency, backlog/outbox age và health tùy hệ thống.

## 11. Kiểm thử metric có đúng định nghĩa không?

Một bảng kiểm thử nên có:

| Test | Publish attempts | Publish returned | Publish threw | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| Một listener đồng bộ thành công | +1 | +1 | +0 | Không đồng nghĩa commit |
| Listener đồng bộ ném exception về publisher | +1 | +0 | +1 | Có thể một số listener trước đó đã được gọi |
| Listener async được schedule, sau đó lỗi | +1 | thường +1 | thường +0 | Handler error phải đo riêng |
| Phát event trong T1 rồi rollback | +1 | thường +1 | thường +0 | AFTER_COMMIT listener không chạy |
| Một event đi tới 3 listeners | +1 | 1 kết quả lời gọi | 0 hoặc 1 | Listener invocation có thể là 3 |
| Retry lại cùng event hai lần | +2 | tùy kết quả từng lời gọi | tùy kết quả từng lời gọi | Unique event ID có thể chỉ là 1 |

Các trường hợp “thường” phụ thuộc cấu hình executor, transaction, listener và đường lỗi cụ thể, không phải một bảo đảm của API `ApplicationEventPublisher`.

### Checklist vận hành

1. Định nghĩa chính xác cái được đếm: attempt, returned, handler success, after-commit hay broker ACK.
2. Xác định đúng entry point để metric không bị bypass.
3. Dùng `Counter` với tag hữu hạn, không đưa ID/request/correlation vào label.
4. Viết test tăng counter khi có lỗi đồng bộ và kiểm tra không đếm gấp đôi.
5. Thêm test `@Async` và `@TransactionalEventListener` để tránh diễn giải returned là handler success.
6. Cân nhắc `Timer` nếu cần latency; đừng tạo metric count trùng không cần thiết.
7. Dùng `rate`/`increase` trên dashboard và hiểu reset khi instance restart.
8. Kiểm tra tên thực tế của metric ở actuator/scrape trước khi dùng PromQL.
9. Giám sát backlog, retry, handler error hoặc outbox nếu nghiệp vụ cần đảm bảo xử lý.
10. Đánh giá overhead/cardinality khi số loại event hoặc nhãn thay đổi theo thời gian.

### Ghi nhớ

~~~text
Counter ở trước publishEvent()
    -> Số lần thử công bố qua entry point đã instrument.

Counter sau khi publishEvent() return
    -> Số lời gọi publisher trả về bình thường.

Counter trong listener
    -> Số lần listener được gọi / hoàn thành (theo điểm đo).

Counter ở AFTER_COMMIT
    -> Số callback sau commit được gọi, không phải mọi event đã publish.

Outbox/broker metric
    -> Mức bảo đảm khác; cần hợp đồng và retry/idempotency riêng.
~~~

**Metric số lần phát event chỉ có giá trị khi tên metric và điểm đếm khớp với nhau.** Với Spring, hãy instrument ở một biên công bố rõ ràng và dùng Micrometer `Counter`; đừng coi một lời gọi `publishEvent` là bảo đảm commit, delivery hoặc xử lý thành công.

## Tài liệu tham khảo

- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Meters và MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Boot — Metrics / Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
