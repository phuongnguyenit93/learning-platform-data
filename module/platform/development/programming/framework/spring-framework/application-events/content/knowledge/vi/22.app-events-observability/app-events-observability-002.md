# Vì sao @EventListener không tự tạo Observation trong Spring Framework?

## 1. Câu trả lời ngắn

`@EventListener` là cơ chế **đăng ký phương thức nhận Spring application event**; nó không phải annotation yêu cầu tạo metric, trace span hoặc `Micrometer Observation`. Khi gọi `ApplicationEventPublisher.publishEvent(event)`, Spring phân phối event đến listener thích hợp nhưng **không tự tạo một Observation riêng cho mỗi lần gọi `@EventListener`**.

Đây là lựa chọn có chủ đích về ngữ nghĩa, không phải lỗi thiếu `ObservationRegistry`. Theo tài liệu chính thức Spring Framework, các lần gọi `@EventListener` không được Framework tự sinh Observation vì chúng **không có ngữ nghĩa phù hợp để instrument như một operation độc lập**. Mặc định publish và xử lý event cùng thread, đồng bộ; event listener đã nằm bên trong call stack, logging context và thường cả trace hiện tại của publisher.

Muốn đo riêng thời gian xử lý event hoặc tạo span riêng cho handler, ta **chủ động instrument** vị trí cần quan sát: dùng `ObservationRegistry` và `Observation` trong listener, một service được bao bởi AOP/`@Observed` đã cấu hình, hoặc một abstraction chuyên trách phù hợp với kiến trúc.

> Quy tắc cần nhớ: Có `@EventListener` ≠ có Observation; có bean `ObservationRegistry` ≠ mọi method đều được tự instrument; có HTTP trace chứa handler ≠ Spring đã tạo span riêng cho handler.

## 2. Phân biệt ba lớp khái niệm

### Event

Một application event là đối tượng biểu thị một điều đã xảy ra. Ví dụ:

```java
public record OrderPlaced(String orderId) {}
```

Publisher có thể phát record trực tiếp bằng `publishEvent(new OrderPlaced("O-17"))`. Spring hỗ trợ POJO event, không bắt buộc record kế thừa `ApplicationEvent`.

### Listener

`@EventListener` đánh dấu một phương thức trong Spring-managed bean. `EventListenerMethodProcessor` xử lý metadata và adapter tương ứng; multicaster phân phối event đến listener thích hợp.

```java
@EventListener
public void handle(OrderPlaced event) {
    // Business handler.
}
```

Đây là đoạn minh họa, chưa phải chương trình độc lập. Annotation chỉ nói *khi nào gọi method* theo loại event và điều kiện lọc; không nói phải phát một meter hay trace span.

### Observation

Micrometer `Observation` là lifecycle của một hành động quan sát được: start, scope, stop, error và các key-value. `ObservationRegistry` điều phối `ObservationHandler` để xử lý lifecycle; khi có bridge phù hợp, handler có thể tạo metric, trace hoặc log correlation.

```text
publishEvent(event)
    |
    v
ApplicationEventMulticaster
    |
    +--> @EventListener OrderHandler.handle(...)
             |
             +--> KHÔNG có Observation mặc định cho lời gọi này
             |
             +--> Có Observation nếu ta chủ động tạo hoặc
                  dùng instrumentation đã cấu hình thực sự
```

**Observation không đồng nghĩa span**: Observation mô tả operation ở mức Micrometer; metrics/tracing phát sinh khi các handler tương ứng được đăng ký. Một Observation có thể là no-op nếu registry/instrumentation không có handler phù hợp.

## 3. Tại sao Spring không tạo Observation cho mọi @EventListener?

### 3.1. Ngữ nghĩa event không luôn giống một operation độc lập

Một domain event có thể được phát nhiều lần, được nhiều listener quan tâm hoặc không có listener nào. Nhiều event chỉ đơn giản thông báo một bước trong use case, không phải một "đơn vị công việc" có ý nghĩa nhất quán để tạo span tự động.

Ví dụ một HTTP request thực hiện `placeOrder()`:

```text
HTTP SERVER SPAN: POST /orders
    |
    +-- OrderService.place()
         |
         +-- publishEvent(OrderPlaced)
              |
              +-- @EventListener updateCache()
              +-- @EventListener recordAudit()
              +-- @EventListener updateCounter()
```

Nếu mọi listener luôn tự có một Observation, hệ thống có thể tạo lượng lớn span/timer cho các tác vụ nhỏ mà không được thiết kế naming, cardinality, phase hoặc ownership. Không phải listener nào cũng có cùng ý nghĩa "thành công": listener A cập nhật cache, listener B ghi audit, listener C ghi một metric.

### 3.2. Đồng bộ và cùng thread theo mặc định

`SimpleApplicationEventMulticaster` mặc định chạy listener tương thích trong publisher thread nếu không có executor async. Khi đó:

- MDC/logging context có thể được kế thừa tự nhiên trong call stack.
- `ThreadLocal` trace/context hiện tại vẫn dùng được khi listener chạy đồng bộ.
- Thời gian xử lý listener đã góp vào duration của operation bao quanh nó, chẳng hạn HTTP request Observation nếu request đang được instrument.
- Không mặc định cần dựng một trace span mới chỉ để truyền trace context.

Lưu ý: *đang nằm trong trace của request* không có nghĩa *có Observation riêng cho listener*. Trên hệ thống tracing, bạn có thể chỉ thấy HTTP span nhưng không có child span tên `event.handle`.

### 3.3. Event có thể async hoặc khác transaction phase

Một listener có thể gắn `@Async`, multicaster có executor, hoặc là `@TransactionalEventListener` được gọi ở phase commit/rollback. Lúc này:

- Nơi phát event và nơi handler chạy có thể thuộc **hai thread hoặc hai thời điểm**.
- Các listener không nhất thiết cùng một transaction hoặc scope.
- Không phải listener nào cũng được di chuyển qua executor: một số listener khai báo không hỗ trợ async execution.
- "Duration của publish" và "duration xử lý listener" không phải cùng một thứ.
- Tự đo bừa bằng một Observation trên publisher có thể bỏ sót thời gian listener xử lý bất đồng bộ.

Vì thế ứng dụng nên chọn **ranh giới operation**: đo thời gian publish, thời gian handler chạy, end-to-end latency, hay thời gian xử lý một batch từ broker. Không có một mặc định duy nhất đúng cho tất cả.

## 4. Spring có tự tạo Observation ở nơi khác không?

Có. Spring Framework instrument một số thành phần có ngữ nghĩa rõ ràng, ví dụ xử lý HTTP server, HTTP client, các tác vụ `@Scheduled` khi được cấu hình, và JMS publication/processing với instrumentation tương ứng. Spring Boot và các starter/actuator có thể cấu hình `ObservationRegistry`, metrics, tracing bridge và exporter.

Điểm cần phân biệt:

| Thành phần | Có Observation khi được cấu hình đúng? | Liên hệ với @EventListener |
| --- | --- | --- |
| HTTP server request | Có, với instrumentation thích hợp | Listener đồng bộ có thể chạy **bên trong** span HTTP |
| `RestClient`/`WebClient` HTTP client | Có nếu registry được cấu hình trên client/builder | Listener gọi HTTP có thể tạo **client span** nhưng không nhất thiết có handler span |
| `@Scheduled` | Có khi scheduler registrar nhận registry theo cơ chế Framework | Không chứng minh `@EventListener` được instrument |
| JMS publish/process | Có với integration được cấu hình | Khác Spring in-process application events |
| `@EventListener` thông thường | **Không tự đóng góp Observation mặc định** | Phải instrument chủ động nếu cần |
| `@Observed` với AOP được thiết lập | Có thể tạo Observation cho invocation được AOP intercept | Không tự chạy nếu chỉ thêm annotation và chưa cấu hình aspect/proxy |

Không nên suy luận "có Micrometer và Actuator trên classpath thì mọi listener đều thành span". Đồng thời đừng làm mất HTTP/JMS instrumentation sẵn có khi bổ sung handler span: nhiều span ở các tầng có thể là đúng nếu chúng đo **các boundary khác nhau**.

## 5. Ví dụ Java 17 chạy được: không có Observation mặc định, có Observation tự khai báo

Dự án dưới đây dùng Spring Framework 6.2.8 và Micrometer Observation. Hai phương thức cùng nhận một `OrderPlaced`:

1. `plainListener` chỉ nhận event; nó không mở Observation.
2. `observedListener` chủ động tạo `Observation` tên `app.event.handle` và thêm tag low-cardinality `event.type=order-placed`.

Để minh họa **Observation lifecycle** mà không cần Prometheus, Zipkin hoặc OpenTelemetry, ta đăng ký một `ObservationHandler` đơn giản in thông báo start/stop. **Đây là handler minh họa**, không xuất metric hay trace thật. Trong production, thay bằng Micrometer meter/tracing handlers phù hợp.

### Cấu trúc Maven

```text
event-observation-demo/
├── pom.xml
└── src/main/java/demo/EventObservationDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-observation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.14.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.EventObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/EventObservationDemo.java`:

```java
package demo;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventObservationDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderHandlers {
        private final ObservationRegistry registry;

        public OrderHandlers(ObservationRegistry registry) {
            this.registry = registry;
        }

        @Order(0)
        @EventListener
        public void plainListener(OrderPlaced event) {
            System.out.println("plain: " + event.orderId());
        }

        @Order(1)
        @EventListener
        public void observedListener(OrderPlaced event) {
            Observation.createNotStarted("app.event.handle", registry)
                    .lowCardinalityKeyValue("event.type", "order-placed")
                    .observe(() -> {
                        System.out.println(
                                "instrumented: " + event.orderId());
                    });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        ObservationRegistry observationRegistry() {
            ObservationRegistry registry = ObservationRegistry.create();

            registry.observationConfig().observationHandler(
                    new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(
                                Observation.Context context) {
                            return true;
                        }

                        @Override
                        public void onStart(Observation.Context context) {
                            System.out.println(
                                    "observation.start: " + context.getName());
                        }

                        @Override
                        public void onStop(Observation.Context context) {
                            System.out.println(
                                    "observation.stop: " + context.getName());
                        }
                    });
            return registry;
        }

        @Bean
        OrderHandlers orderHandlers(ObservationRegistry registry) {
            return new OrderHandlers(registry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderPlaced("O-17"));
        }
    }
}
```

Chạy khi có JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra do chính chương trình in (không tính log của Maven):

```text
plain: O-17
observation.start: app.event.handle
instrumented: O-17
observation.stop: app.event.handle
```

Lý giải:

- Hai method đều được `@EventListener` đăng ký; `@Order(0)` và `@Order(1)` sắp xếp thứ tự ưu tiên của listener.
- `plainListener` chạy nhưng **không** tạo Observation vì không có code instrument quanh nó.
- `observedListener` gọi `Observation.createNotStarted(...)` rồi `observe(...)`: Micrometer start/stop Observation và handler in hai dòng tương ứng.
- `event.type` được dùng như low-cardinality key: nên là tên loại event thuộc tập hữu hạn, không phải order ID.
- `ObservationHandler` in sự kiện lifecycle để demo; bản thân handler không tạo metrics/traces thật. Muốn metrics cần handler gắn `MeterRegistry`; muốn tracing cần bridge/handler tracing và exporter tương ứng.
- Việc publisher và listener đồng bộ không thay đổi: Observation thủ công chỉ bao bọc thời gian chạy thân method `observedListener`.

**Điểm kiểm chứng cốt lõi:** Nếu bỏ dòng `Observation.createNotStarted(...).observe(...)` mà giữ cả hai `@EventListener`, listener vẫn nhận event, nhưng các dòng `observation.start/stop` không còn xuất hiện. Chỉ thêm bean `ObservationRegistry` cũng không tự tạo Observation quanh method.

## 6. Đo cái gì: publish, handle hay latency toàn hành trình?

### 6.1. Đo thời gian publish

```java
Observation.createNotStarted("app.event.publish", registry)
        .observe(() -> publisher.publishEvent(event));
```

Đây là đoạn minh họa; cần publisher, registry, event có sẵn. Với multicaster đồng bộ, duration có thể bao gồm thời gian các listener được gọi. Với multicaster bất đồng bộ, nó thường chỉ đo thời gian **bàn giao** cho executor; không đo được việc listener hoàn tất sau đó.

Do vậy tên `app.event.publish` cần được định nghĩa rõ: đo một lần gọi `publishEvent`, không nhất thiết là toàn bộ việc xử lý event.

### 6.2. Đo thời gian handler

```java
Observation.createNotStarted("app.event.handle", registry)
        .lowCardinalityKeyValue("event.type", "order-placed")
        .observe(() -> handleBusinessLogic(event));
```

Đây là đoạn minh họa, `handleBusinessLogic` cần được định nghĩa trong dự án. Đặt Observation **bao quanh phần xử lý thật**. Nếu code chỉ enqueue một task rồi trả về, duration của đoạn này là enqueue, không phải duration của task trong worker.

### 6.3. Đo end-to-end latency

Từ lúc event được tạo đến khi consumer xử lý xong, có thể chênh lệch lớn nếu qua executor/queue/broker. Một Observation chỉ mở trong publisher thread không thể tự chạy xuyên qua thời gian chờ queue.

Muốn đo end-to-end latency, cần timestamps và correlation/event ID với mục đích rõ ràng, truyền context có kiểm soát, và instrument consumer ở boundary tương ứng. Nếu qua message broker, dùng instrumentation của công nghệ messaging hoặc một cơ chế tracing được thiết kế rõ.

## 7. Cấu hình @Observed và AOP: không nhầm annotation là instrumentation tự động

Micrometer cung cấp `@Observed` và `ObservedAspect` để tạo Observation cho **method invocation được aspect intercept**. Nhưng trên ứng dụng Spring, chỉ viết:

```java
@Observed(name = "app.event.handle")
public void handle(OrderPlaced event) {
    // ...
}
```

không đảm bảo có span/metric. Cần aspect, Spring AOP/AspectJ wiring phù hợp và `ObservationRegistry` có handlers. Nếu Spring proxy không intercept invocation (ví dụ self-invocation hoặc hạn chế proxy đối với một method/class), annotation không có tác dụng như mong đợi.

Với `@EventListener`, luồng dispatch đi qua Spring listener adapter và có thể tương tác với AOP proxy. Phải kiểm tra thực tế xem advice có chạy đúng trên bean/method đang được gọi; **không coi thêm `@Observed` vào listener là giải pháp phổ quát không cần cấu hình**.

Nếu cần minh bạch, dễ kiểm thử và đo chính xác một đoạn handler, cách thủ công `Observation.createNotStarted(...).observe(...)` là lựa chọn rõ ràng. Nếu nhiều handler phải theo cùng chính sách, có thể đóng gói helper instrumentation hoặc một wrapper ở tầng application; tránh sao chép code start/stop ở mọi nơi.

## 8. Khi có @Async hoặc custom ApplicationEventMulticaster

Mặc định `SimpleApplicationEventMulticaster` gọi listener đồng bộ. Khi cấu hình executor hoặc dùng `@Async`, event được xử lý ở thread khác:

```text
publisher thread:
  current Observation / trace scope
  publishEvent(event)
       |
       +-- executor.submit(task)
  return

worker thread:
  [không mặc định kế thừa ThreadLocal/trace context]
  @EventListener handler
       |
       +-- Observation mới nếu được instrument
```

Nếu không truyền trace context, span tạo trong worker có thể trở thành root span rời rạc hoặc không liên kết với trace của publisher. Trái lại, nếu chỉ có logging MDC ở publisher, worker có thể mất correlation ID.

Spring Framework cho phép cấu hình `ContextPropagatingTaskDecorator` trên executor cùng thư viện `io.micrometer:context-propagation` khi cần truyền context. Một ví dụ **trích đoạn ý tưởng**, không phải cấu hình tự chạy độc lập:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor();
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
multicaster.setTaskExecutor(executor);
```

Cần import/classpath và bean multicaster phù hợp. **Context propagation không tự tạo Observation cho @EventListener**; nó chỉ truyền ngữ cảnh đã có qua boundary bất đồng bộ. Ngoài ra không phải listener nào cũng hỗ trợ việc chạy async trong multicaster, đặc biệt listener cần transaction thread-bound.

Nếu dùng `@Async` trên listener, cần `@EnableAsync`, executor được cấu hình và chính sách propagation/error handling rõ. Async exception không tự quay về `publishEvent`. Observation nên bao quanh **công việc chạy thật trong worker**, không chỉ thời gian submit.

## 9. Observation, metric, tracing và logging: khác nhau ra sao?

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Observation | "Operation nào đang chạy và kết quả ra sao?" | `app.event.handle` start/stop/error |
| Metric | "Tần suất, độ trễ, lỗi tổng hợp thế nào?" | Timer cho xử lý `order-placed`, tag loại event |
| Trace/span | "Một request đi qua thành phần nào?" | HTTP span chứa child handler span được tạo có chủ đích |
| Log | "Điều gì đã xảy ra tại một thời điểm?" | Handler ghi mã kết quả hoặc lỗi đã redacted |
| Context propagation | "Làm sao liên hệ công việc ở thread khác?" | Truyền trace/correlation context qua executor |

Một Observation có thể tạo metric hoặc span nếu registry đã có handlers tương ứng. Một log có trace ID không chứng minh có child span cho listener. Một metric counter do handler tự tăng không chứng minh Micrometer đã tạo `Observation`.

Nên thiết kế tagging thận trọng:

- **Low-cardinality tags**: event type có tập hữu hạn, outcome (`success`/`error`), handler family cố định.
- **High-cardinality dữ liệu**: order ID, user ID, email, request ID; không dùng làm tag metrics vì gây bùng số series và có thể lộ thông tin.
- **Tên Observation**: đặt ổn định, nhất quán, không đưa dynamic IDs vào tên.
- **Payload nhạy cảm**: không đưa nguyên event vào `lowCardinalityKeyValue(...)`, `highCardinalityKeyValue(...)`, trace baggage hoặc log khi chưa có chính sách.

Dù high-cardinality fields có thể hữu ích trong span để điều tra, chúng vẫn phải tuân thủ phân quyền và chính sách bảo mật dữ liệu. Không "chuyển PII sang tracing" như một cách né giới hạn của metrics.

## 10. Error, rollback và thời gian của Observation

Một handler `@EventListener` có thể ném exception. Với callback thủ công:

```java
Observation.createNotStarted("app.event.handle", registry)
        .observe(() -> perform(event));
```

Micrometer quản lý start/stop trong các nhánh thực thi của `observe(...)` và có thể ghi exception vào Observation lifecycle theo API. Tuy nhiên một Observation kết thúc với lỗi **không tự rollback transaction**, không tự retry event và không có nghĩa event được lưu bền vững.

Khi dùng `@TransactionalEventListener(AFTER_COMMIT)`, handler chỉ chạy ở phase transaction thích hợp. Observation trong listener đo execution lúc đó, **không đo thời gian transaction trước commit**. Nếu listener lỗi sau commit, Observation có thể ghi error nhưng **không thể hoàn tác DB commit đã xảy ra**. Giám sát lỗi và retry phải nằm ở thiết kế khác.

Nếu listener chạy trong publisher thread và cùng transaction, exception chưa được xử lý có thể lan về `publishEvent` và làm transaction rollback. Việc mở Observation không thay đổi propagation/rollback policy đó.

## 11. Kiểm tra thế nào để biết đã instrument đúng?

Một bộ kiểm thử và checklist nên chứng minh cả **có event** và **có Observation đúng chỗ**:

1. **Event dispatch**: publish đúng `OrderPlaced`, handler chạy đúng một lần theo hợp đồng.
2. **Observer lifecycle**: handler quan sát nhận một start và một stop khi handler được instrument; không nhầm event được gọi với observation được gọi.
3. **Tên/low-cardinality tags**: `app.event.handle` và `event.type=order-placed` cố định.
4. **Không phát sinh Observation cho plain listener** trong demo, bất kể bean `ObservationRegistry` tồn tại.
5. **Exception**: handler ném lỗi nhưng Observation được dừng theo cơ chế an toàn; lỗi được báo về đúng boundary.
6. **AOP nếu dùng**: chứng minh `ObservedAspect`/proxy thực sự chạy, không chỉ dựa vào sự tồn tại của annotation.
7. **Async**: nếu dùng executor, xác định rõ scope, context propagation và cách liên hệ trace.
8. **Không thêm dữ liệu nhạy cảm** vào tags/trace/log.
9. **Không nhầm listener phase**: `@TransactionalEventListener` after-commit có ngữ nghĩa timing khác `@EventListener`.
10. **Metrics/traces export**: xác minh handler/registry/exporter đã cấu hình; demo in start/stop không chứng minh server đã nhận span.

### Các lỗi cấu hình thường gặp

**"Có ObservationRegistry nhưng dashboard trống"**: Registry không tự instrument listener. Cũng có thể thiếu meter/tracing handler, MeterRegistry exporter hoặc cấu hình sampling.

**"@EventListener đã chạy nhưng không có child span"**: Spring không đóng góp Observation mặc định cho listener; nếu cần child span hãy instrument chủ động.

**"@Observed không thấy tác dụng"**: Chưa đăng ký aspect, proxy không intercept, self-invocation, hay chính invocation path của listener không đi qua advice.

**"Publish duration ngắn nhưng handler mất nhiều giây"**: Có thể publish chỉ enqueue công việc async. Đo thời gian handler tại worker.

**"MDC/trace biến mất sau @Async"**: Thread-local context không tự truyền sang worker; xem `ContextPropagatingTaskDecorator` và Micrometer Context Propagation, đồng thời giới hạn dữ liệu được propagation.

**"Có event nhưng không có meter"**: Event API, Observation API và registry/exporter là các tầng khác nhau, không tự suy ra nhau.

## 12. Khi nào nên tạo Observation riêng cho listener?

Nên tạo khi handler thực sự là operation độc lập, có giá trị đo đạc: ví dụ xử lý domain event có thể thất bại, tốn thời gian, retry nhiều lần, gọi một dependency bên ngoài hoặc chạy trong worker async.

Có thể không cần khi listener chỉ cập nhật một giá trị trong bộ nhớ, một operation đã được bao bởi HTTP span rõ ràng, và thêm span riêng gây nhiễu/tăng chi phí. Không nhất thiết một `@EventListener` tương ứng một span hay một timer. Chọn theo điều tra sự cố, SLO, chi phí instrumentation và hợp đồng vận hành.

Một thiết kế thực dụng:

```text
HTTP/server observation (tự động theo integration)
   |
   +-- service business logic
        |
        +-- publishEvent(OrderPlaced)
             |
             +-- cheap listener: không thêm span
             |
             +-- external integration handler:
                  Observation("app.event.handle")
                    event.type=order-placed
                    result=success/error
                  -> HTTP client observation nếu client được cấu hình
```

Đo listener **không thay thế** việc thiết kế idempotency, durable outbox hoặc retry. Observation chỉ cho bạn biết điều gì xảy ra; nó không đảm bảo phân phối event hoặc xử lý đúng một lần.

## 13. Tự kiểm tra kiến thức

1. **`@EventListener` có luôn tạo Micrometer Observation không?** — Không. Spring Framework không tự đóng góp Observation cho lời gọi listener.
2. **Tại sao một HTTP trace có log listener nhưng không có child span listener?** — Handler đồng bộ có thể chạy trong scope hiện tại, không có operation Observation riêng.
3. **Đăng ký bean `ObservationRegistry` có đủ để đo mọi listener không?** — Không; cần instrument hoặc aspect phù hợp và handlers.
4. **Vì sao không instrument tự động mọi listener?** — Semantics khác nhau; cùng thread, nhiều consumer, sync/async/phase và chi phí/cardinality không có mặc định thống nhất.
5. **Muốn đo duration thực của handler async, instrument ở đâu?** — Bên trong worker xử lý, không chỉ quanh `publishEvent`.
6. **`@Observed` có hoạt động mà không có aspect/proxy không?** — Không thể mặc định như vậy.
7. **Context propagation làm gì?** — Chuyển những context được cấu hình qua thread boundary; nó không tự tạo span.
8. **Dùng order ID làm low-cardinality tag được không?** — Không nên; cardinality cao và có rủi ro lộ dữ liệu.
9. **Sau commit, Observation lỗi có rollback transaction đã commit không?** — Không.
10. **Muốn metrics/traces thật cần thêm gì ngoài Observation?** — Registry handlers, meter/tracing bridge và exporter theo cấu hình ứng dụng.

## Tài liệu tham khảo

- [Spring Framework — Observability Support: Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Framework — Async context propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html#integration.observability.application-events)
