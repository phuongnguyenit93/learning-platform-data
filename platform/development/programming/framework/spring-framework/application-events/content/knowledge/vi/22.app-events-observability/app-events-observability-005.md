# Trace context khi event đồng bộ trong Spring Application Events

## 1. Bài toán: event có giữ được trace đang hoạt động không?

Khi một ứng dụng Spring dùng distributed tracing, một request hoặc một tác vụ nền có thể đang chạy bên trong một **trace** với **span hiện hành**. Một service phát domain event để các listener xử lý nghiệp vụ phụ:

```java
applicationEventPublisher.publishEvent(new OrderSubmitted("O-100"));
```

Câu hỏi quan trọng trong nhóm **Observability** là: listener nhận event trên luồng nào, có nhìn thấy `traceId`/`spanId` đang hoạt động ở publisher không, và Spring có tự tạo một span mới cho event không?

Với `SimpleApplicationEventMulticaster` mặc định của Spring Framework, câu trả lời là:

1. **Đồng bộ, cùng luồng:** các listener thông thường được gọi trực tiếp trên thread đã gọi `publishEvent(...)`. Publisher chờ listener kết thúc trước khi lời gọi publish trả về.
2. **Context hiện hành còn trong scope:** nếu publisher đang có trace/span được kích hoạt thông qua cơ chế context của tracing library, listener đồng bộ thường đọc được **cùng context đang hoạt động**, vì không có chuyển thread.
3. **Không tự sinh span riêng:** riêng thao tác publish/dispatch thông thường **không có nghĩa Spring tạo một observation hoặc một child span mới cho mỗi listener**. Spring Framework không tự thêm Observations cho `@EventListener` theo mặc định.
4. **Không mặc nhiên có trace:** nếu publisher không có active span, listener không bỗng có một trace hợp lệ chỉ vì đã được gọi đồng bộ.
5. **Khi đổi cơ chế dispatch**, nhất là `@Async` hoặc cấu hình task executor bất đồng bộ cho multicaster, phải đánh giá lại việc truyền context.

Đây là đặc tính rất hữu ích: log/telemetry từ listener đồng bộ có thể được tương quan với thao tác phát event mà không phải tự đưa `traceId` vào mọi domain payload. Nhưng cũng có giới hạn: **cùng trace không đồng nghĩa listener có span riêng**, **cùng thread không đồng nghĩa transaction đã commit**, và **trace context không phải thông tin phân quyền**.

## 2. Phân biệt trace, span và context

| Khái niệm | Ý nghĩa | Quan hệ với synchronous listener |
| --- | --- | --- |
| `traceId` | Định danh một trace, nối những span thuộc cùng chuỗi xử lý | Nếu cùng active span thì listener thấy cùng traceId |
| `spanId` | Định danh một span cụ thể | Nếu listener không tạo span mới, thường cùng spanId với publisher |
| `parentSpanId` | Mối liên kết cha–con trong cây trace | Chỉ có child span khi instrumentation thực sự tạo nó |
| **Active/current span** | Span được gắn vào execution context hiện hành | Listener đồng bộ có thể truy cập cùng active span khi scope còn mở |
| **Trace context** | Thông tin như SpanContext và propagation state | Có thể đọc từ tracing API, không phải lúc nào cũng có valid span |
| **Baggage** | Metadata do ứng dụng/quy ước tracing mang theo | Dùng cẩn thận vì có thể lan qua ranh giới hệ thống |
| **MDC logging context** | Dữ liệu trong thread-local map để bổ sung vào log | Có thể giống publisher ở sync listener nếu logging integration đã cấu hình |
| **Correlation ID nghiệp vụ** | Định danh workflow/domain do ứng dụng quy định | Có thể khác traceId và có vòng đời dài hơn một trace |

Một trace có thể chứa nhiều span. Ví dụ request HTTP có một server span và một database call có client span là con. Nếu chỉ gọi một phương thức Java đồng bộ không được instrument, phương thức đó vẫn chạy **trong active span của caller**, chứ không tự trở thành một span.

Do đó, dòng sau không chứng minh đã có span riêng cho listener:

```text
traceId=abc... spanId=123...  OrderService publishing
traceId=abc... spanId=123...  OrderListener handling
```

Cả hai log cùng `spanId` có thể hoàn toàn đúng: listener đang làm việc bên trong span của request hoặc use case phát event.

Ngược lại, nếu hệ thống chủ động tạo child span trong listener:

```text
traceId=abc... spanId=123...  OrderService publishing
traceId=abc... spanId=456...  OrderListener handling
parentSpanId=123...         Child span created by explicit instrumentation
```

Khi ấy hai log vẫn cùng trace, nhưng listener có spanId khác. Không nên đặt một tiêu chí kiểm thử “spanId bắt buộc luôn bằng nhau” cho mọi hệ thống; nó chỉ đúng khi **không có lớp instrumentation nào tạo span mới**.

## 3. Tại sao Spring Application Events mặc định giữ được context?

Theo tài liệu Spring Framework, khi không chỉ định task executor đặc biệt, `SimpleApplicationEventMulticaster` phân phối các listener **đồng bộ trên calling thread**. Từ góc nhìn ứng dụng:

```text
Thread: http-nio-8080-exec-1
|
+-- HTTP observation/span đang active
    |
    +-- OrderService.placeOrder(...)
        |
        +-- publisher.publishEvent(OrderSubmitted)
            |
            +-- OrderAuditListener.on(...)
            |       -> cùng thread
            |       -> nhìn thấy active span hiện hành
            |
            +-- OrderMetricsListener.on(...)
            |       -> cùng thread
            |       -> nhìn thấy active span hiện hành
            |
            +-- publishEvent(...) trả về
        |
        +-- OrderService tiếp tục
    |
    +-- HTTP span kết thúc ở boundary tương ứng
```

Với cơ chế thông dụng dùng ThreadLocal, giá trị đang được gắn vào current thread vẫn có hiệu lực khi stack gọi Java đi vào listener rồi trở về. Không cần đưa context vào queue để chuyển thread, vì chưa có thread hand-off.

Các lớp công nghệ có thể tham gia:

- **OpenTelemetry Java:** `Context.current()` và `Span.current()` truy cập context/span hiện hành, trong cấu hình mặc định context storage sử dụng ThreadLocal; `Scope` đóng để khôi phục context trước đó.
- **Micrometer Tracing:** `Tracer.currentSpan()` truy cập span hiện hành; backend có thể là OpenTelemetry hoặc Brave.
- **Micrometer Observation:** một `Observation` có thể đang active tại boundary HTTP/service; cách kết nối sang span phụ thuộc tracing configuration.
- **SLF4J/Logback MDC:** thông tin traceId/spanId có thể được logging integration cập nhật; không phải cứ bật Spring Events là MDC tự có trace fields.

**Chữ “thường” rất quan trọng:** sự bảo toàn context phụ thuộc một active context được tạo đúng và còn scope, đồng thời listener không tự tắt/thay thế context. Nếu trong publisher không có active span, listener đồng bộ cũng thấy context không hợp lệ hoặc rỗng.

## 4. Chữ “đồng bộ” có ba hệ quả kỹ thuật

### 4.1. Listener chạy trước khi publishEvent trả về

Ví dụ:

```java
System.out.println("BEFORE");
publisher.publishEvent(new OrderSubmitted("O-100"));
System.out.println("AFTER");
```

Nếu một listener đồng bộ in `HANDLED`, đầu ra theo thứ tự khái quát là:

```text
BEFORE
HANDLED
AFTER
```

Đây là minh họa khi chỉ có listener ấy và không có exception. Với nhiều listener, thứ tự gọi có thể chịu ảnh hưởng bởi `@Order`; với async, thứ tự hoàn tất có thể khác.

### 4.2. Listener dùng thời gian của publisher

Nếu listener gọi API ngoài chậm 2 giây, lời gọi publish trong request cũng có thể bị chặn tương ứng. Đồng bộ giúp trace context đơn giản nhưng **không miễn phí về latency**. Cần cân nhắc listener nào thực sự phù hợp đường request.

### 4.3. Exception có thể quay ngược về publisher

Trong cấu hình mặc định không có `ErrorHandler` để suppress, exception từ listener đồng bộ có thể thoát khỏi `publishEvent(...)` và làm luồng gọi thất bại. Nếu instrumentation cần đánh dấu span lỗi, phải ghi nhận exception ở nơi có trách nhiệm, không dựa vào việc tạo span listener tự động.

**Không khẳng định một listener lỗi luôn rollback DB:** việc rollback còn phụ thuộc transaction boundary, exception type, transaction manager và code đã thực thi trước đó.

## 5. Spring không tự tạo observation cho @EventListener

Đây là điểm rất dễ nhầm khi xem trace UI.

Tài liệu **Spring Framework Observability Support** nói rằng framework **không góp Observations cho các lời gọi `@EventListener`** theo mặc định. Lý do liên quan đến semantics instrumentation của event listener. Việc một listener thừa hưởng current observation/span không có nghĩa framework tạo một span như:

```text
server.request
   |
   +-- application.event.publish (KHÔNG mặc định được tạo)
        |
        +-- order.listener (KHÔNG mặc định được tạo)
```

Nếu một dashboard hiện span `order.listener`, cần xác định span ấy do **custom instrumentation, `@Observed`, AOP, agent hoặc thư viện thứ ba** tạo ra, không tự quy cho event framework.

Các hướng hợp lý:

1. **Muốn cùng trace, không cần span mới:** dùng sync listener mặc định và bảo đảm publisher đang có context hoạt động. Đây là lựa chọn tối giản.
2. **Muốn đo duration listener độc lập:** chủ động instrument operation có giá trị bằng Observation API hoặc tracing span, có scope rõ ràng.
3. **Muốn gắn một sự kiện nhẹ lên current span:** cân nhắc span event/annotation với thông tin được phép lưu; tránh tạo hàng nghìn spans cho các event vụn.
4. **Muốn đo mọi listener trên hệ thống:** đánh giá overhead, cardinality, semantics, tỷ lệ lấy mẫu và loại event, thay vì tự động instrument mọi event.

Nguyên tắc: một child span mới nên biểu diễn **đơn vị công việc cần đo**, chứ không bắt buộc biểu diễn mỗi dispatch callback.

## 6. Ví dụ Java 17, Spring Framework và OpenTelemetry chạy được

Để quan sát hiện tượng bằng dữ liệu xác thực thay vì giả định, ta tạo một trace/span hiện hành ngay trong code, publish một Java record qua Spring, rồi kiểm tra span context ở listener.

Phiên bản được dùng trong ví dụ:

- Java 17+.
- Spring Framework `spring-context:6.2.12`.
- OpenTelemetry Java `opentelemetry-api:1.43.0` và `opentelemetry-sdk-trace:1.43.0`.
- Maven.

Đây là **demo standalone** dùng SDK OpenTelemetry trực tiếp; một ứng dụng Spring Boot production thường cấu hình OpenTelemetry/Micrometer qua starter, agent hoặc hạ tầng instrumentation phù hợp. Mục tiêu của demo là kiểm tra **truyền context trong cùng thread**, không phải xuất telemetry đến collector.

### 6.1. Cấu trúc dự án

```text
sync-event-trace/
├── pom.xml
└── src/main/java/demo/SyncEventTraceDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-event-trace</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-api</artifactId>
            <version>1.43.0</version>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-sdk-trace</artifactId>
            <version>1.43.0</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.SyncEventTraceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/SyncEventTraceDemo.java`:

```java
package demo;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class SyncEventTraceDemo {

    public record OrderSubmitted(String orderId) {}

    public static final class AuditListener {
        private SpanContext observed;
        private Thread observedThread;

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            observed = Span.current().getSpanContext();
            observedThread = Thread.currentThread();
            System.out.println("LISTENER_VALID=" + observed.isValid());
            System.out.println("EVENT_ID=" + event.orderId());
        }

        public SpanContext observed() {
            return observed;
        }

        public Thread observedThread() {
            return observedThread;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        SdkTracerProvider provider = SdkTracerProvider.builder().build();
        try {
            Tracer tracer = provider.get("sync-event-demo");

            try (var context =
                    new AnnotationConfigApplicationContext(Config.class)) {
                AuditListener listener = context.getBean(AuditListener.class);
                Span publisherSpan =
                        tracer.spanBuilder("submit-order").startSpan();

                try (Scope ignored = publisherSpan.makeCurrent()) {
                    SpanContext published =
                            Span.current().getSpanContext();
                    Thread publisherThread = Thread.currentThread();

                    System.out.println(
                            "PUBLISHER_VALID=" + published.isValid());
                    context.publishEvent(new OrderSubmitted("O-100"));

                    // Chỉ hợp lệ ngay sau publish vì dispatch mặc định đồng bộ.
                    SpanContext observed = listener.observed();
                    if (observed == null) {
                        throw new IllegalStateException(
                                "Listener did not receive event");
                    }
                    System.out.println(
                            "SAME_TRACE=" + published.getTraceId()
                                    .equals(observed.getTraceId()));
                    System.out.println(
                            "SAME_SPAN=" + published.getSpanId()
                                    .equals(observed.getSpanId()));
                    System.out.println(
                            "SAME_THREAD=" + (publisherThread
                                    == listener.observedThread()));
                } finally {
                    publisherSpan.end();
                }
            }
        } finally {
            provider.shutdown();
        }
    }
}
```

Lệnh chạy:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in ra:

```text
PUBLISHER_VALID=true
LISTENER_VALID=true
EVENT_ID=O-100
SAME_TRACE=true
SAME_SPAN=true
SAME_THREAD=true
```

### 6.2. Giải thích vì sao kết quả là true

1. `SdkTracerProvider` được cấu hình làm SDK tracer provider tối giản. Demo bắt đầu một span tên `submit-order`, sau đó dùng `publisherSpan.makeCurrent()` để gắn nó vào OpenTelemetry context đang hoạt động ở main thread.
2. `Span.current().getSpanContext()` trong publisher chứa một `traceId` và `spanId` hợp lệ vì đang nằm trong scope của span SDK vừa tạo.
3. `AnnotationConfigApplicationContext` dùng event multicaster đồng bộ mặc định. Khi `publishEvent(OrderSubmitted)` gọi `AuditListener.onOrderSubmitted(...)`, listener được thực hiện trên **cùng Java thread**.
4. Listener chỉ **đọc** `Span.current()` mà không tạo thêm span, nên `traceId` và `spanId` giống publisher. Đây là lý do của hai dòng `SAME_TRACE=true` và `SAME_SPAN=true`.
5. Listener đã chạy xong trước khi `publishEvent` trả về; do đó sau publish có thể đọc `listener.observed()` mà không cần latch hay future.
6. `Scope.close()` do `try-with-resources` đảm nhiệm để khôi phục context trước; `publisherSpan.end()` kết thúc span; `provider.shutdown()` giải phóng SDK provider.

**Lưu ý:** demo không thêm SpanExporter, nên không tự gửi dữ liệu tới Jaeger/Tempo/Zipkin hay in raw trace ID. Kết quả chỉ chứng minh context **đang hoạt động trong tiến trình**. Trong một ứng dụng thực, việc tạo span và xuất trace tới backend còn phụ thuộc sampler, exporter, collection pipeline và tracing instrumentation.

### 6.3. Vì sao cần cả SAME_TRACE, SAME_SPAN và SAME_THREAD?

Nếu chỉ in `traceId` thì hai tình huống sau dễ bị lẫn:

- **Cùng span:** listener không tạo span mới, chỉ thừa hưởng active span của publisher.
- **Child span:** listener được instrument, có span ID khác nhưng vẫn cùng trace ID và parent đúng.

Kiểm tra `SAME_THREAD` xác nhận tính chất đồng bộ ở mức execution thread. Nó không chứng minh mọi tình huống production luôn đồng bộ: đổi `SimpleApplicationEventMulticaster.setTaskExecutor(...)` hoặc gắn `@Async` có thể làm kết quả đổi.

Kiểm tra `SAME_SPAN` trong demo là **chủ đích**, để minh họa rằng Spring event **không tự sinh một span**. Đừng biến đây thành tiêu chí bắt buộc cho listener có chủ ý tạo span riêng.

## 7. Micrometer Tracing trong Spring Boot: nhìn current span

Ở ứng dụng Spring Boot đã cấu hình Micrometer Tracing, có thể inject `io.micrometer.tracing.Tracer` vào một bean và xem `currentSpan()`.

Ví dụ trong một Spring bean có `Tracer` đã được cấu hình (đoạn minh họa, **không thuộc chương trình Maven ở phần 6**):

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.context.event.EventListener;

public class PaymentEventObserver {
    private final Tracer tracer;

    public PaymentEventObserver(Tracer tracer) {
        this.tracer = tracer;
    }

    @EventListener
    public void onPaymentCompleted(PaymentCompleted event) {
        Span span = tracer.currentSpan();
        if (span == null) {
            // Không có active span ở thời điểm listener chạy.
            return;
        }

        String traceId = span.context().traceId();
        String spanId = span.context().spanId();
        // Ghi telemetry có kiểm soát nếu thật sự cần.
    }
}
```

Đoạn trên cần `PaymentCompleted` của ứng dụng, bean đăng ký đúng cách và các dependency Micrometer Tracing phù hợp. Nó **không** bảo đảm luôn có span: có thể publish từ scheduled job hoặc entrypoint chưa được instrument.

Nếu application sử dụng OpenTelemetry API trực tiếp, cú pháp tương ứng là:

```java
SpanContext sc = io.opentelemetry.api.trace.Span
        .current().getSpanContext();
if (sc.isValid()) {
    String traceId = sc.getTraceId();
    String spanId = sc.getSpanId();
}
```

Với Micrometer, `currentSpan()==null` là một dấu hiệu thường gặp khi không có active span; với OpenTelemetry, `Span.current()` có thể trả một invalid span context thay vì `null`. **Không trộn quy tắc null/invalid của hai API.**

### Có nên lấy traceId trong handler rồi đưa ngược vào domain event?

Thông thường **không cần**, nếu mục tiêu chỉ là tương quan log/trace của các listener đồng bộ cùng scope. Context hiện hành đủ để tracing integration sử dụng.

Nếu sự kiện cần được lưu bền vững, chuyển qua queue hoặc xử lý sau khi request đã kết thúc, nên thiết kế metadata correlation/provenance riêng theo yêu cầu và dùng tracing propagation chuẩn ở ranh giới transport. Không bắt business payload phải có `traceId` chỉ vì callback đồng bộ đang chạy.

## 8. Truyền trace context không có nghĩa Spring tự truyền dữ liệu nghiệp vụ

Một điểm cần phân biệt:

```text
Execution context: current span, tracing baggage, MDC, security/threadlocals
Domain event payload: orderId, amount, occurredAt, tenantId, actorId
```

Ở listener đồng bộ, execution context trên cùng thread thường giữ nguyên **trong scope hiện hành**. Nhưng event payload vẫn là dữ liệu nghiệp vụ cần được tạo rõ ràng. **Không nên lấy tenantId hoặc actorId chỉ bằng cách nhìn traceId**; tracing ID không có semantics authentication/authorization.

Ví dụ log có thể cùng trace nhưng xử lý nhầm tenant nếu service lấy tenant từ một header không đáng tin; observability không bảo vệ được quyền truy cập dữ liệu.

Nếu cần audit ai phát sự kiện hoặc tenant nào sở hữu giao dịch, đưa **định danh đã kiểm chứng** vào event/envelope phù hợp. Nếu chỉ cần theo dõi quan hệ thời gian thực giữa publisher và listener, trace context tại runtime thường là đủ.

### Trace context có thể chứa baggage

Baggage có thể lan qua boundary và cuối cùng xuất hiện trong logs/spans tùy cấu hình. Tránh đưa access token, session, email, số thẻ, PII hoặc secrets vào baggage. Việc cùng thread bảo toàn baggage không khiến dữ liệu đó tự nhiên an toàn hơn.

## 9. Spring @EventListener không phải một công cụ tracing riêng

`@EventListener` là cách đăng ký phương thức nghe event, ví dụ:

```java
@EventListener
public void on(OrderSubmitted event) {
    // Logic của listener; event object do publisher cung cấp.
}
```

Annotation này **không tự thiết lập root span**. Nó không ngụ ý `@Observed` hay `@WithSpan` được áp dụng.

Nếu muốn định danh một đơn vị công việc bằng span riêng, có thể dùng API tracing khi thật sự có giá trị quan sát. Ví dụ OpenTelemetry **minh họa**:

```java
public void handleWithSpan(OrderSubmitted event, Tracer tracer) {
    Span child = tracer.spanBuilder("order.audit").startSpan();
    try (Scope scope = child.makeCurrent()) {
        // Xử lý audit; child mặc định nhận current span làm parent
        // nếu publisher vẫn có một active span.
        writeAudit(event);
    } catch (RuntimeException ex) {
        child.recordException(ex);
        child.setStatus(StatusCode.ERROR);
        throw ex;
    } finally {
        child.end();
    }
}
```

Đoạn này không chạy độc lập: cần `Tracer`, `Span`, `Scope`, `StatusCode` và `writeAudit(...)` trong một class phù hợp. `child` có cùng `traceId` với parent, nhưng `spanId` riêng.

**Thời điểm tạo child span quan trọng:** gọi `spanBuilder(...).startSpan()` khi parent vẫn active thì span mới tự nhận parent. Nếu vô tình tạo child sau khi parent scope đã đóng, có thể khởi tạo root span mới và làm đứt trace.

### Dùng span event thay vì child span khi cần rất ít dữ liệu

Nếu chỉ muốn ghi nhận “order event đã được dispatch” trong parent span, có thể:

```java
Span.current().addEvent("order.submitted");
```

Đoạn trên là OpenTelemetry API minh họa. Hãy tránh nhét toàn bộ `OrderSubmitted` hay thông tin riêng tư vào span event attributes. Đây là **telemetry event** nằm trong một span, **khác** domain `ApplicationEvent` của Spring.

Đồng thời, nếu đang không có valid recording span, lệnh trên có thể không tạo dữ liệu hiển thị trong tracing backend.

## 10. Cấu hình logging: vì sao traceId/spanId có thể xuất hiện trong MDC?

Khi application dùng tracing bridge/integration hỗ trợ correlation, log format có thể bổ sung trường:

```text
traceId=4c8d... spanId=a2f1... OrderService publish OrderSubmitted
traceId=4c8d... spanId=a2f1... OrderAuditListener handled OrderSubmitted
```

Trong cùng scope và cùng thread, hai log có thể mang cùng giá trị. Nhưng log MDC và active span **không phải cùng một API**:

- **Tracing context:** nguồn để tracing library xác định active span và parent-child relationships.
- **MDC:** map được logger dùng đưa fields vào log; nhiều cấu hình dùng ThreadLocal.
- **Log pattern:** quyết định trường MDC nào thực sự xuất hiện trên stdout/log file.
- **Sampling/export:** quyết định dữ liệu span nào thực sự được gửi đến tracing backend.

Không thấy `traceId` trong log chưa đủ để kết luận active span đã mất; có thể log pattern chưa include, tracing bridge chưa cấu hình hoặc phần mềm dùng naming khác. Ngược lại, thấy `traceId` trong MDC không bảo đảm hiện tại có **valid recording span**: MDC có thể còn giá trị cũ nếu cleanup sai.

### Cách kiểm chứng đúng

Trong listener, đối chiếu **tracing API** (`currentSpan()`/`Span.current()`) với **MDC** tại đúng thời điểm. Nếu có chênh lệch, xem scope lifecycle, instrumentation và logging integration trước khi kết luận lỗi Spring Events.

Đừng dựa vào screenshot log chứa một traceId cố định để xác minh source; các trace IDs thực tế thay đổi trên mỗi lượt chạy.

## 11. Trace context có thể thay đổi bên trong callback đồng bộ

Việc listener chạy trên cùng thread không có nghĩa context bất biến trong suốt call stack.

Ví dụ:

```text
Publisher span: order.submit (spanId=P)
    |
    +-- publishEvent(OrderSubmitted)
            |
            +-- AuditListener
                    |
                    +-- startSpan("audit.write")
                            -> current spanId=C trong nested Scope
                    |
                    +-- close Scope
                            -> current spanId=P lại
            |
            +-- publishEvent trả về
                    -> current spanId=P
```

Nếu child span được tạo/đóng đúng cách, parent được phục hồi. Nhưng nếu một listener:

- quên đóng `Scope`,
- gọi tracing API gắn context mới rồi không restore,
- đổi MDC mà không khôi phục,
- gọi nested event trong một child span khác,

thì listener khác hoặc publisher có thể quan sát context không như kỳ vọng. **Không phải lỗi do đồng bộ bị hỏng**; chính mã listener đã thay đổi thread-local context.

Một quy tắc an toàn:

```java
Span span = tracer.spanBuilder("some-operation").startSpan();
try (Scope scope = span.makeCurrent()) {
    doWork();
} finally {
    span.end();
}
```

Đoạn trên là snippet, cần biến `tracer`/`doWork()` thực tế và import OpenTelemetry. `try-with-resources` bảo đảm `Scope.close()` ngay cả khi `doWork()` ném exception; `finally` kết thúc span.

**Không bao giờ cache `Span.current()` trong một singleton field để tái sử dụng trên những request khác.** “Current” có nghĩa tại scope/thời điểm hiện hành, không phải trạng thái chung của ứng dụng.

## 12. Khi publisher không có active trace

Không phải mọi event đều phát từ request HTTP có instrumentation. Ví dụ:

- `@Scheduled` job chạy một thao tác không được instrument.
- CLI command chạy trên background thread.
- Message consumer chưa được cấu hình tracing instrumentation.
- Test tạo `AnnotationConfigApplicationContext` thuần.
- Domain event được phát sau khi một scope đã đóng.

Khi đó synchronous listener vẫn chạy cùng thread, nhưng không có span hợp lệ để thừa hưởng. Không nên “sửa” bằng cách tự tạo ID ngẫu nhiên rồi đặt nó là `traceId` trên log: nếu không có span/trace context đúng, ID đó không tạo được trace hợp lệ trong backend.

Có hai hướng hợp lý:

1. **Không yêu cầu trace:** cứ xử lý bình thường; dùng business correlation ID khi cần audit.
2. **Cần quan sát công việc nền:** tạo observation/root span tại **boundary có ý nghĩa**, đặt scope và kết thúc đúng; event đồng bộ bên trong sẽ thừa hưởng.

Nếu muốn một trace nối từ request sang batch/job chạy nhiều giờ sau đó, không nên giữ ThreadLocal hay span của HTTP request mở hàng giờ. Hãy sử dụng context propagation/links và một đơn vị công việc mới có contract tracing rõ ràng.

## 13. So sánh đồng bộ và bất đồng bộ: ranh giới chính là thread hand-off

| Tình huống | Same thread? | Có thể đọc active trace của publisher? | Lưu ý |
| --- | --- | --- | --- |
| Default `@EventListener` với `SimpleApplicationEventMulticaster` | **Có** | **Có**, nếu scope đang active | Spring không tự tạo listener span |
| Listener tạo child span đồng bộ | Có | Có, cùng trace; spanId mới trong scope con | Phải đóng scope |
| Event publisher không có active span | Có | Không có valid span để thừa hưởng | Bắt đầu span ở boundary phù hợp nếu cần |
| `@Async @EventListener` | **Thường không** | Không bảo đảm nếu thiếu propagation | Async proxy/task executor quyết định |
| Custom multicaster có executor async | **Thường không** | Không bảo đảm nếu thiếu propagation | Dùng context propagation có kiểm soát |
| `@TransactionalEventListener(AFTER_COMMIT)` | Có thể cùng thread khi callback transaction | **Phụ thuộc lúc commit và scope** | Không mặc nhiên có span/request context cũ |
| Event phát ra message broker | Khác process/worker | Cần propagation qua message metadata | Không truyền Java ThreadLocal qua mạng |

Điểm cốt lõi: **đồng bộ giúp tránh hand-off**, nhưng không phải một hợp đồng mãi mãi cho mọi cách cấu hình listener.

### Một lời gọi publish có thể chạy listener trên nhiều thread?

Mặc định Spring Framework không làm vậy. Nhưng ứng dụng có thể đăng ký `applicationEventMulticaster` bean với `TaskExecutor` khác:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor executor) {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

Đây là đoạn cấu hình minh họa, cần Spring `@Configuration`, `@Bean`, bean `ThreadPoolTaskExecutor` và imports. Trong cấu hình như vậy, những listener **hỗ trợ async dispatch** có thể chạy trên worker thread khác. Một số loại listener vòng đời/transaction có semantics đặc biệt, không nên mặc định mọi listener đều bị chuyển sang executor.

Với Spring Framework có `ContextPropagatingTaskDecorator` và Micrometer Context Propagation, một executor được cấu hình đúng có thể chụp và restore các context được hỗ trợ tại thời điểm submit task. Nếu chủ đích của bài chỉ là **event đồng bộ**, không cần decorator này; thêm không đúng chỗ có thể tạo overhead hoặc khiến người học nghĩ async context luôn tự được giữ.

## 14. Trường hợp @TransactionalEventListener: cùng thread chưa chắc cùng span

Một `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` có thể thực thi callback khi transaction commit, không nhất thiết ngay tại dòng `publishEvent`.

Giả sử:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderSubmitted event) {
    // Chạy ở transaction phase AFTER_COMMIT.
}
```

Đây là đoạn minh họa nằm trong một Spring bean có transaction manager. Nếu transaction commit xảy ra khi span HTTP/service vẫn active, listener có thể nhìn thấy context ấy. Nếu application thay đổi scope hoặc callback chạy ở một boundary khác, điều đó không được bảo đảm chỉ vì chữ “transactional”.

Nên kiểm tra:

- Mốc callback thực sự chạy ở đâu so với scope của span.
- Có dùng reactive transactions hay không; Reactor Context khác ThreadLocal và cần cách xử lý phù hợp.
- Listener có `@Async` hoặc gọi executor khác bên trong không.
- Việc đọc traceID có phục vụ observability hay đang bị dùng nhầm làm identity của transaction.
- Dữ liệu cần giữ lâu dài có được lưu trong event envelope phù hợp không.

**Không được xem `@TransactionalEventListener` như cơ chế tự động giữ tracing scope sau khi publisher đã kết thúc**, và cũng không suy từ việc có trace sang bảo đảm commit/delivery.

## 15. Xử lý exception, span status và log khi listener lỗi

Khi listener đồng bộ ném exception, lời gọi publish có thể fail. Nếu có active span ở publisher, tracing instrumentation bên ngoài có thể ghi nhận lỗi **nếu được cấu hình**. Spring Events không tự cam kết sẽ gắn exception vào span hiện hành.

Ví dụ minh họa trong listener hoặc service có OpenTelemetry:

```java
try {
    handleOrder(event);
} catch (RuntimeException ex) {
    Span current = Span.current();
    if (current.isRecording()) {
        current.recordException(ex);
        current.setStatus(StatusCode.ERROR);
    }
    throw ex;
}
```

Đây là snippet, cần `handleOrder`, `event`, `Span` và `StatusCode` phù hợp. Nó chỉ thay đổi telemetry trên **current span**, có thể là span của publisher nếu listener không tạo span riêng. Việc gắn lỗi lên span chung có thể là điều bạn muốn, hoặc có thể làm parent span bị đánh dấu thất bại dù ứng dụng đã có chính sách phục hồi. Chọn semantics theo nghiệp vụ.

Nếu listener lỗi nhưng ứng dụng vẫn có thể tiếp tục, cân nhắc chính sách lỗi của multicaster, retry hoặc handling logic. Đừng mặc định “listener đã fail thì trace tự báo error” hay “cùng trace thì transaction tự rollback”.

## 16. Kiểm thử đúng trace context khi event đồng bộ

Ví dụ hoàn chỉnh ở phần 6 là một **integration smoke test** của Spring event dispatch và OpenTelemetry context. Trong project lớn, có thể thêm test bằng JUnit để chặn regression khi ai đó thay đổi multicaster từ synchronous sang async.

Các assertion đáng có:

- Publisher có một valid active span trước publish.
- Listener được gọi **trước khi** publish trả về.
- Listener và publisher có cùng `traceId`.
- Nếu không instrument listener, hai bên có cùng `spanId`.
- Listener chạy trên **cùng Java thread**.
- Nested spans do listener tạo/đóng đúng và current span được restore.
- Khi publisher không có span, listener không tự xuất hiện một valid span.
- Exception của listener được xử lý theo policy và scope không bị rò rỉ.
- Khi bật async riêng trong test, propagation được cấu hình và kiểm tra tường minh; không ép async phải có same thread.
- Khi thay đổi logging, log correlation không bị mất do MDC bridge/pattern.

### Test quan sát kết quả không phụ thuộc UUID

Một test vững chắc không so sánh traceId với một chuỗi hex cụ thể: mỗi lượt chạy có thể sinh ID mới. Thay vào đó:

```java
assertTrue(publisherContext.isValid());
assertTrue(listenerContext.isValid());
assertEquals(
        publisherContext.getTraceId(),
        listenerContext.getTraceId());
assertEquals(
        publisherContext.getSpanId(),
        listenerContext.getSpanId());
```

Đoạn trên minh họa JUnit, cần JUnit dependencies và khai báo hai `SpanContext` đã được ghi lại. Với async listener có chủ đích tạo child span, chỉ kiểm tra `traceId` và quan hệ parent/links như thiết kế, không nhất thiết `spanId` bằng nhau.

### Test khi không có trace

Phát `OrderSubmitted` ngoài bất kỳ span scope nào trong một test isolated. Trong một process sạch dùng API OpenTelemetry, `Span.current().getSpanContext().isValid()` thường là false. Đừng viết test giả định luôn false nếu agent/instrumentation của test runner tự tạo span; hãy kiểm soát test environment và scope.

## 17. Debug khi traceId của listener khác publisher

Một quy trình chẩn đoán theo thứ tự:

1. **Đọc event multicaster config:** có custom `applicationEventMulticaster` hay task executor không?
2. **Kiểm tra @Async:** method listener hoặc service bên trong có chuyển task sang executor khác không?
3. **Kiểm tra current span bằng API**, không chỉ MDC hoặc log pattern.
4. **Kiểm tra Scope lifecycle:** publisher có đóng scope trước khi listener chạy không?
5. **Xem listener có tự tạo span mới không:** traceId giống nhưng spanId khác có thể hoàn toàn đúng.
6. **Xem nested event:** callback khác có thể tạm thay current span và phải restore.
7. **Kiểm tra instrumentation setup:** có SDK/tracer bridge và sampler phù hợp hay chỉ no-op API?
8. **Kiểm tra logging correlation:** MDC config có thiếu trace/span fields hoặc cleanup sai không?
9. **Đừng giả định transaction phase** giống thời điểm publish.
10. **Nếu đã qua broker/async**, kiểm tra extraction/injection, header propagation và context restoration theo transport.
11. **Không dùng traceId để truy ra user/tenant** nếu thông tin đó không có contract/bảo vệ phù hợp.

Một bảng triệu chứng:

| Triệu chứng | Khả năng cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| TraceId có ở publisher, không có ở listener | Listener chạy ngoài scope hoặc trên worker thread | Đối chiếu dispatch, scope, task decorator |
| Same traceId, khác spanId | Listener/custom instrumentation tạo child span | Kiểm tra parent/child; không coi mặc định là lỗi |
| Same traceId và spanId, nhưng không có “listener span” | Framework không tự tạo Observation cho @EventListener | Instrument chủ động nếu cần đo duration |
| Không bên nào có valid span | Chưa có tracing instrumentation hoặc scope | Khởi tạo trace tại boundary có ý nghĩa |
| Log không có traceId nhưng API có span | MDC bridge/log pattern | Kiểm tra logging config |
| TraceId đổi sau callback | Scope không restore hoặc listener tự mở context | Đóng Scope trong finally/try-with-resources |
| Async test chập chờn | Đọc kết quả trước khi task hoàn thành | Chờ bằng latch/future và timeout rõ |
| Trace liên tục nhưng tenant sai | Dùng trace context thay xác thực/tenant logic | Sửa authorization và event business metadata |

## 18. Tối ưu quan sát và tránh tạo dữ liệu dư thừa

Không phải mỗi domain event đều đáng có một span riêng. Khi một request phát hàng trăm event nội bộ cực nhanh, instrument mọi dispatch có thể tăng:

- CPU và allocation do tạo span/observation.
- Khối lượng traces phải xuất và lưu.
- Cardinality của attributes khi lưu event IDs/user IDs làm nhãn.
- Noise khi xem flame graph.
- Nguy cơ lộ dữ liệu business qua tracing backend.

Một hướng thực hành cân bằng:

- Dùng **active span hiện có** để tương quan các listener đồng bộ.
- Tạo child span cho listener thực sự chậm, ranh giới hệ thống, các phép I/O quan trọng hoặc bước nghiệp vụ cần đo.
- Dùng business metrics (counter/timer) với **low-cardinality labels** đã kiểm soát, không đưa raw `orderId` hay userId vào mọi metric tag.
- Ghi trace attributes cần thiết theo allowlist, tránh dữ liệu bí mật.
- Đảm bảo traces có lifecycle chính xác (scope đóng, span kết thúc).
- Phân biệt span duration với **thời gian tổng ở publishEvent**; số listener nhiều và ordering có thể ảnh hưởng tổng thời gian.
- Kiểm tra tính hiệu quả của sampling và storage trước khi tăng độ chi tiết instrumentation.

## 19. Các lỗi thường gặp

1. **Cho rằng `@EventListener` tự tạo một span.** Spring Framework không mặc định instrument mỗi event listener bằng Observation.
2. **Nhầm traceId và spanId.** Cùng traceId, khác spanId có thể là quan hệ parent-child hợp lệ.
3. **Cho rằng cùng thread thì luôn có trace.** Nếu publisher không có active span, listener không có gì để thừa hưởng.
4. **Cho rằng same thread có nghĩa Spring đã propagate qua network.** Không có network hand-off trong đồng bộ.
5. **Chỉ nhìn MDC rồi khẳng định span hợp lệ.** MDC có thể chưa được nối với tracing hoặc còn giá trị cũ.
6. **Không đóng Scope sau khi mở child span.** Làm hỏng current context cho listener kế tiếp hoặc caller.
7. **Giữ Span.current() vào singleton field.** Dễ trộn request và tạo race.
8. **Bật `@Async` mà không kiểm tra context propagation.** ThreadLocal hiện hành thường không tự đi qua executor boundary.
9. **Đưa raw traceId vào domain event chỉ để log đồng bộ.** Tăng coupling và thiếu mục đích nếu current context đã đủ.
10. **Dùng traceId làm khóa nghiệp vụ hoặc tenant ID.** Trace là observability identifier, không phải business ownership.
11. **Log cả event payload hoặc baggage.** Có thể lộ PII, token hoặc dữ liệu nội bộ.
12. **Bắt exception nhưng không xét span status.** Có thể khiến trace báo thành công hoặc thất bại trái với semantics cần thiết.
13. **Tưởng `@TransactionalEventListener(AFTER_COMMIT)` luôn còn HTTP span.** Nó chạy theo transaction phase, không cam kết scope tracing.
14. **So sánh raw traceId cố định trong test.** ID thay đổi ở mỗi lần chạy; hãy so sánh tương quan.
15. **Xem một trace hiện đủ log rồi suy ra event đã được lưu bền vững.** Spring Application Events là cơ chế trong tiến trình, không tự cung cấp outbox/retry.
16. **Thêm span cho mọi listener mà không đo overhead.** Có thể tăng chi phí observability mà không mang lại khả năng chẩn đoán tốt hơn.

## 20. Checklist áp dụng vào một ứng dụng Spring

- [ ] Event đang được phân phối bằng multicaster đồng bộ mặc định hay có executor?
- [ ] Listener có `@Async` hoặc tự spawn task không?
- [ ] Publisher có active span/observation tại thời điểm `publishEvent(...)`?
- [ ] Đã phân biệt tracing API với MDC/log pattern?
- [ ] Cần cùng trace hay cần child span để đo duration độc lập?
- [ ] Nếu child span được tạo, scope có được restore và span kết thúc đúng?
- [ ] Với transaction-phase listener, đã xem xét scope còn hoạt động tại callback?
- [ ] Nếu có hand-off, đã cấu hình propagation tại boundary đúng chưa?
- [ ] Event payload có tránh secrets, PII, runtime span objects và thread-local references?
- [ ] Có test bảo đảm current traceId trong listener đồng bộ khớp publisher?
- [ ] Có test không active span và test listener exception?
- [ ] Các metric/trace attributes có được quản lý cardinality và chi phí?

**Tóm tắt:** Khi Spring Application Events chạy **đồng bộ**, listener thông thường được gọi ngay trên thread của publisher. Nếu một span đang active trong scope ấy, listener có thể nhìn thấy **cùng trace context** mà không cần chuyển context qua executor; nếu không có span, nó không tự xuất hiện. Spring **không mặc định tạo Observation/child span cho `@EventListener`**, nên cùng traceId và spanId là điều bình thường. Muốn thêm span riêng phải instrument có chủ đích, quản lý Scope đúng cách và phân biệt quan sát vận hành với ý nghĩa nghiệp vụ của event.

## Tài liệu tham khảo

- [Spring Framework Reference — Observability Support, Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework Reference — Additional Capabilities of ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [OpenTelemetry Java — Record Telemetry with API](https://opentelemetry.io/docs/languages/java/api/)
- [OpenTelemetry Specification — Context](https://opentelemetry.io/docs/specs/otel/context/)
