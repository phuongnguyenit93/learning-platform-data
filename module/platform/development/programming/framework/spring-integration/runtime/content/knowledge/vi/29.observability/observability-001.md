# IntegrationManagement và managed component

Khi một hệ thống Spring Integration chạy qua nhiều <code>MessageChannel</code>, consumer endpoint, handler, poller và executor, một lỗi “message đã gửi nhưng chưa được xử lý” rất khó chẩn đoán chỉ từ log nghiệp vụ. Người vận hành cần biết channel nào đang nhận message, handler nào thất bại, endpoint nào đã dừng, queue nào đang tích tụ và vì sao latency tăng sau một lần thay đổi topology.

Spring Integration có cơ chế **management cho các runtime component**, với giao diện trung tâm <code>IntegrationManagement</code>. Cơ chế này giúp đặt tên, cấu hình logging và kết nối các thành phần được hỗ trợ với Micrometer/Observation. Bên cạnh đó có JMX exporter và integration graph để kiểm tra hoặc điều khiển runtime theo các đường riêng.

Bài học thuộc chương **Observability** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ hiểu rõ thế nào là một *managed component*, cách bật management bằng <code>@EnableIntegrationManagement</code>, cách quan sát channel/handler/source, phân biệt metrics với traces và JMX, cũng như liên hệ với lifecycle <code>IntegrationFlow</code>, transaction, retry, message store, error flow, correlation, threading và hiệu năng.

> **Nguyên tắc:** Một component triển khai <code>IntegrationManagement</code> **không có nghĩa** nó tự trở thành JMX MBean công khai, tự có trace hoặc tự cung cấp tất cả số liệu nghiệp vụ. Khả năng quản lý, đăng ký meter, tạo observation và xuất dữ liệu ra bên ngoài là **các lớp cấu hình khác nhau**.

## 1. Managed component là gì?

Spring Integration có nhiều loại đối tượng runtime. Một số là kênh truyền message, một số đọc nguồn theo lịch, một số xử lý message, và một số quản lý lifecycle hoặc điều phối flow. Các thành phần framework thường kế thừa từ lớp cơ sở đã hỗ trợ management.

| Thành phần | Ví dụ | Vai trò runtime | Dữ liệu quan sát có ích |
|---|---|---|---|
| Message channel | <code>DirectChannel</code>, <code>ExecutorChannel</code>, <code>QueueChannel</code> | Vận chuyển message, dispatch đến consumer | Số lượt send/receive, lỗi, latency thao tác channel, độ sâu queue khi hỗ trợ |
| Message handler | Service activator, transformer, router, outbound gateway | Thực thi tác vụ đối với message | Thời gian xử lý, số lượt lỗi, tên handler, span xử lý |
| Message source | JDBC/File/Kafka polling source, nguồn tự viết dựa trên <code>AbstractMessageSource</code> | Tạo message bằng cơ chế poll | Số lần nhận thành công, khả năng tạo message, lỗi source |
| Inbound producer/gateway | Message-driven adapter, <code>MessagingGatewaySupport</code> | Nhận sự kiện/request từ hệ thống khác | Thời gian xử lý, kết quả, trace context |
| Endpoint lifecycle | <code>SourcePollingChannelAdapter</code>, <code>EventDrivenConsumer</code>, <code>PollingConsumer</code> | Start/stop, đăng ký consumer hoặc lịch poll | <code>isRunning()</code>, trạng thái task, lỗi scheduling |
| Message group store | Aggregator/resequencer persistence | Giữ fragment và correlation metadata | Số group đang chờ, tuổi group, tỷ lệ timeout; có thể cần instrumentation riêng |

**Không phải mọi hàng trong bảng đều là cùng một interface.** Channel, handler và nhiều source hỗ trợ <code>IntegrationManagement</code>; endpoint lifecycle thường được điều khiển qua <code>SmartLifecycle</code> hoặc registration tương ứng. Một số thống kê chuyên biệt cần lấy từ store, executor, adapter hay application metrics, không nhất thiết là thuộc tính của <code>IntegrationManagement</code>.

~~~mermaid
flowchart LR
    P["Inbound adapter / Source"] --> C["orders.input<br/>Managed channel"]
    C --> H["orders.process<br/>Managed handler"]
    H --> O["Outbound channel / Gateway"]
    M["IntegrationManagementConfigurer"] -. "Tên, logging và instrument" .-> C
    M -. "Tên, logging và instrument" .-> H
    R["MeterRegistry / ObservationRegistry"] -. "Metrics / spans" .-> C
    R -. "Metrics / spans" .-> H
    E["Optional JMX exporter"] -. "MBean view" .-> C
    E -. "MBean view" .-> H
~~~

Các mũi tên nét đứt là mối liên hệ cấu hình/quản trị; không phải message channel vận chuyển những dữ liệu quản trị này.

## 2. Giao diện IntegrationManagement

Trong Spring Integration 6.x, giao diện <code>org.springframework.integration.support.management.IntegrationManagement</code> kế thừa <code>NamedComponent</code> và <code>DisposableBean</code>. Đây là hợp đồng để framework biết cách cấu hình một **managed component**.

Những API cần nhớ:

| API | Chức năng |
|---|---|
| <code>getManagedName()</code> / <code>setManagedName(...)</code> | Tên quản lý được dùng cho nhận diện/hiển thị và instrumentation khi component hỗ trợ |
| <code>getManagedType()</code> / <code>setManagedType(...)</code> | Phân loại managed component |
| <code>isLoggingEnabled()</code> / <code>setLoggingEnabled(...)</code> | Điều khiển logging debug thông thường của framework tại component |
| <code>registerMetricsCaptor(...)</code> | Cấp cơ chế thu thập meter Micrometer cho component, theo cơ chế hỗ trợ của phiên bản |
| <code>registerObservationRegistry(...)</code> | Cấp <code>ObservationRegistry</code> để component phát Observation |
| <code>isObserved()</code> | Cho biết component đang dùng ObservationRegistry khác NOOP theo hợp đồng interface |
| <code>getOverrides()</code> | Thông tin những thuộc tính management đã cấu hình thủ công, để configurer không ghi đè |
| <code>destroy()</code> | Hook lifecycle của interface; không đồng nghĩa xóa message store hoặc hạ tầng ngoài |

<code>IntegrationManagement.ManagementOverrides</code> là cấu trúc phục vụ **ưu tiên cấu hình**: nếu một thuộc tính đã được chỉnh trực tiếp trên bean, <code>IntegrationManagementConfigurer</code> có thể không áp dụng lại giá trị mặc định cho thuộc tính đó.

Ví dụ một managed channel được cấu hình tường minh:

~~~java
@Bean(name = "orders.input")
DirectChannel ordersInput() {
    DirectChannel channel = new DirectChannel();
    channel.setManagedName("orders.input");
    channel.setLoggingEnabled(false);
    return channel;
}
~~~

<code>DirectChannel</code> thuộc <code>org.springframework.integration.channel</code>. Cách đặt <code>managedName</code> thủ công giúp tên dễ nhận ra khi đọc số liệu; nhưng không nên đặt ngẫu nhiên theo request hoặc message ID. Logging tắt ở đây chỉ nhắm đến **log dòng chảy thông thường** do component phát, không tắt exception hay hệ thống log nói chung.

### ManagedName, componentName và beanName khác gì?

Một endpoint Java DSL có thể tạo nhiều bean nội bộ. Vì thế:

- **Bean name** là khóa trong <code>ApplicationContext</code>, dùng để tìm bean và quản lý vòng đời.
- **Component name/type** xuất phát từ hợp đồng <code>NamedComponent</code>, giúp biểu diễn phần tử trong graph.
- **Managed name/type** là metadata phục vụ quản trị và metric/observation theo API của component.
- **Flow ID** hoặc **endpoint ID** nhận diện phần đăng ký/lifecycle; không được coi đương nhiên là tên của mọi handler ở bên trong.

Khi debug một metric thiếu dữ liệu, hãy **in ra metadata từ runtime** thay vì đoán rằng tên ghi trong Java DSL chắc chắn là tag của meter.

## 3. Management không đồng nghĩa với Lifecycle

Một channel có thể tồn tại trong <code>ApplicationContext</code> và có metric nhưng không phải đối tượng thực thi poller. Ngược lại, một <code>SourcePollingChannelAdapter</code> có thể được <code>start()</code>/<code>stop()</code> mà các message đã nằm trong queue vẫn còn chờ.

| Công việc | API chủ yếu | Có xóa dữ liệu tồn đọng không? |
|---|---|---|
| Bật/tắt logging debug | <code>IntegrationManagement.setLoggingEnabled(...)</code> | Không |
| Đặt tên/quản lý component | <code>setManagedName(...)</code>, configurer | Không |
| Dừng/khởi động endpoint | <code>SmartLifecycle</code>, registration của dynamic flow | Không tự xóa |
| Gỡ flow động | <code>IntegrationFlowContext.remove(flowId)</code> / registration destroy | Không mặc nhiên xóa persistent store |
| Xuất metric/trace | <code>MeterRegistry</code>, <code>ObservationRegistry</code> | Không |
| Công bố JMX attributes/operations | <code>IntegrationMBeanExporter</code> | Không |
| Xử lý lỗi | <code>ErrorMessage</code> / error channel và adapter error handling | Không tự quyết định rollback |

Vì vậy, khi một dashboard cho thấy “handler không có traffic”, cần phân biệt endpoint chưa start, source không tạo message, channel bị chặn, queue backlog hay handler đã bị gỡ khỏi topology.

## 4. Bật quản lý với @EnableIntegrationManagement

<code>@EnableIntegrationManagement</code> nằm trong package <code>org.springframework.integration.config</code>. Nó import cấu hình management và tạo bean <code>IntegrationManagementConfigurer</code> với tên chuẩn <code>integrationManagementConfigurer</code>.

Ví dụ cơ bản:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "true",
    observationPatterns = { "orders.*" })
public class ManagedOrderFlowConfig {
    // Các bean managed component của flow được khai báo tại đây.
}
~~~

Giải thích:

1. <code>@EnableIntegration</code> khởi tạo hạ tầng Spring Integration.
2. <code>@EnableIntegrationManagement</code> bật cấu hình mặc định cho các component có hỗ trợ management.
3. <code>defaultLoggingEnabled</code> là chuỗi <code>"true"</code>/<code>"false"</code> và có thể dùng property placeholder; nó không đổi level của SLF4J/Logback.
4. <code>observationPatterns</code> là tập mẫu tên component được **chọn để inject ObservationRegistry** khi có registry trong context. Mặc định là rỗng, nghĩa là không có component nào được bật Observation một cách vô điều kiện.
5. Mẫu có thể dùng dấu <code>*</code> và dấu <code>!</code> để loại trừ theo quy tắc pattern matching của framework. Phải xác nhận tên thực tế và thứ tự xử lý khi dùng nhiều mẫu.

Ví dụ cấu hình:

~~~java
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = { "orders.*" })
~~~

Thiết lập trên giảm log debug thông thường của các managed component theo mặc định, đồng thời chỉ định phạm vi observation hẹp hơn toàn ứng dụng. Nó **không tự tạo** <code>ObservationRegistry</code>, không tự kết nối Prometheus/Zipkin/OTLP và không bật JMX MBean exporter.

Nếu thử nghiệm trong một ứng dụng nhỏ, <code>observationPatterns = "*"</code> có thể giúp kiểm tra instrumented component. Tuy nhiên, bật cho tất cả component ở production có thể tăng số spans, metric series và overhead đáng kể.

### Vì sao cấu hình thủ công có thể ghi đè giá trị chung?

Nếu một channel đã gọi <code>setLoggingEnabled(true)</code>, việc đặt <code>defaultLoggingEnabled = "false"</code> không nhất thiết làm channel đó im lặng: configurer tôn trọng những thuộc tính đã được đánh dấu cấu hình thủ công thông qua cơ chế override. Bởi vậy, khi thấy chỉ một vài component vẫn log, hãy kiểm tra cấu hình bean/DSL cụ thể.

## 5. Ví dụ Java DSL hoàn chỉnh: managed channel và handler

Ứng dụng nhận <code>OrderCommand</code>, thực thi service activator và muốn quan sát số lượt handler chạy, số lỗi và thời gian xử lý. Để tên metric ổn định, ta đặt tên channel và ID endpoint rõ ràng.

**Bước 1 — payload và service nghiệp vụ:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }
        // Thao tác nghiệp vụ, ví dụ ghi OrderStore hoặc gọi service khác.
    }
}
~~~

**Bước 2 — khai báo flow và management:**

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    observationPatterns = { "orders.*" },
    defaultLoggingEnabled = "true")
public class OrderIntegrationConfig {

    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        DirectChannel channel = new DirectChannel();
        channel.setManagedName("orders.input");
        return channel;
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process", e -> e.id("orders.process"))
            .get();
    }
}
~~~

Import chính: <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.config.EnableIntegrationManagement</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, cùng <code>org.springframework.context.annotation.Configuration</code>/<code>Bean</code> và <code>org.springframework.stereotype.Service</code>.

Flow dùng <code>DirectChannel</code>, nên trong đường đi đồng bộ, exception từ <code>process()</code> có thể truyền về thread gọi <code>send()</code>. Với <code>ExecutorChannel</code> hoặc poller, cùng một handler có thể được thực thi trên thread khác; điều đó làm thay đổi nơi lỗi được nhận và cách diễn giải duration.

**Bước 3 — tạo registry cho ví dụ không dùng Spring Boot auto-configuration:**

~~~java
@Configuration
class LocalTelemetryConfig {

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    ObservationRegistry observationRegistry(MeterRegistry meters) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
            .observationHandler(new DefaultMeterObservationHandler(meters));
        return registry;
    }
}
~~~

Các kiểu: <code>io.micrometer.core.instrument.MeterRegistry</code>, <code>io.micrometer.core.instrument.simple.SimpleMeterRegistry</code>, <code>io.micrometer.core.instrument.observation.DefaultMeterObservationHandler</code> và <code>io.micrometer.observation.ObservationRegistry</code>.

**Giải thích phần dễ bỏ sót:** <code>ObservationRegistry</code> là nơi phát observations; <code>DefaultMeterObservationHandler</code> mới chuyển chúng thành Micrometer meters trong registry này. Nếu đã dùng Spring Boot Actuator và Boot đã tạo registry/handlers, **không tạo thêm** các bean ví dụ để tránh cấu hình trùng hoặc xung đột auto-configuration. Mã này minh họa cấu hình tối thiểu ở một Spring context tự quản lý.

**Bước 4 — gửi message:**

~~~java
Message<OrderCommand> valid = MessageBuilder
    .withPayload(new OrderCommand("O-101", 2))
    .setHeader("correlationId", "checkout-O-101")
    .build();

ordersInput.send(valid);
~~~

<code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Chỉ xem <code>send()</code> là kết quả của *send operation*. Trong topology bất đồng bộ, send thành công có thể chỉ có nghĩa task được chấp nhận, không chứng minh toàn bộ downstream hoàn tất.

## 6. Kiểm tra trực tiếp managed component đang tồn tại

Sau khi application context được khởi tạo, có thể liệt kê các bean triển khai <code>IntegrationManagement</code>:

~~~java
Map<String, IntegrationManagement> managed =
    applicationContext.getBeansOfType(IntegrationManagement.class);

managed.forEach((beanName, component) -> {
    log.info(
        "bean={}, managedName={}, managedType={}, observed={}, logging={}",
        beanName,
        component.getManagedName(),
        component.getManagedType(),
        component.isObserved(),
        component.isLoggingEnabled());
});
~~~

<code>IntegrationManagement</code> thuộc <code>org.springframework.integration.support.management</code>; <code>applicationContext</code> là <code>ApplicationContext</code> hiện tại. Nếu component nội bộ do framework tạo ra không được liệt kê như một bean dễ truy cập, cần kiểm tra endpoint ID, graph và cấu hình DSL tương ứng, thay vì khẳng định nó không tồn tại.

Có thể kiểm tra một bean cụ thể:

~~~java
DirectChannel channel =
    applicationContext.getBean("orders.input", DirectChannel.class);

IntegrationManagement management = channel;
assertEquals("orders.input", management.getManagedName());
management.setLoggingEnabled(false);
assertFalse(management.isLoggingEnabled());
~~~

Các assertion thuộc JUnit 5. Thay đổi <code>setLoggingEnabled(...)</code> là cấu hình tại runtime của bean cụ thể; nó không cần khởi động lại flow, nhưng không tạo hoặc xóa meter đã đăng ký và không thay đổi logging level chung của ứng dụng.

### Khi nào nên đặt managed name thủ công?

- Khi muốn metric ổn định giữa các lần deploy, thay vì tên endpoint do DSL tạo tự động.
- Khi nhiều flow cùng xử lý một nghiệp vụ nhưng cần tách theo logical component.
- Khi dynamic flow có ID xác định và muốn truy vết thao tác stop/restart hoặc metrics theo đúng ID.

Không dùng message ID, order ID hoặc tenant ID có hàng triệu giá trị làm managed name. Với Micrometer, tên hoặc tag quá nhiều giá trị gây **cardinality explosion**, ảnh hưởng bộ nhớ collector và chi phí hệ thống giám sát.

## 7. Phân biệt Micrometer meters truyền thống và Observation API

Spring Integration hỗ trợ hai con đường thu thập thông tin hiệu năng có liên quan nhưng **không đồng nhất**:

| Tiêu chí | Micrometer meters truyền thống | Micrometer Observation (Spring Integration 6.0+) |
|---|---|---|
| Đầu vào | <code>MeterRegistry</code>, <code>MetricsCaptor</code> | <code>ObservationRegistry</code> và các <code>ObservationHandler</code> |
| Giá trị chính | Counter/timer/gauge cho send, receive và handler | Một abstraction có thể tạo metrics và tracing spans |
| Cấu hình chọn component | Component được framework hỗ trợ và meter filters | <code>@EnableIntegrationManagement(observationPatterns=...)</code> |
| Tên metric điển hình | <code>spring.integration.send</code>, <code>spring.integration.receive</code> | <code>spring.integration.handler</code>, <code>spring.integration.producer</code>, <code>spring.integration.gateway</code> |
| Dữ liệu trace | Không tự tạo span chỉ vì có timer | Có thể tạo span khi có tracing ObservationHandler phù hợp |
| Khi cả hai cơ chế hiện diện | Tùy phiên bản/cấu hình; không nên giả định cả hai đều ghi | Khi component đã có ObservationRegistry, <code>MetricsCaptor</code> độc lập có thể bị bỏ qua |

Theo Javadoc, <code>registerMetricsCaptor(...)</code> được **bỏ qua nếu đã có ObservationRegistry** được dùng cho component. Meter của Observation không được thu độc lập theo cách legacy, mà được chuyển tới handler trong <code>ObservationRegistry</code>. Vì thế, một dashboard từng đọc <code>spring.integration.send</code> có thể cần đổi truy vấn khi chuyển sang observations.

### Metric names và tags cần biết

**Nhánh meters truyền thống:**

| Meter | Loại | Tag quan trọng |
|---|---|---|
| <code>spring.integration.send</code> | Timer của channel send hoặc handler | <code>type</code> (channel/handler), <code>name</code>, <code>result</code>, <code>exception</code> |
| <code>spring.integration.receive</code> | Counter của pollable channel hoặc source | <code>type</code>, <code>name</code>, <code>result</code>, <code>exception</code> |
| <code>spring.integration.channels</code> | Gauge tổng số channel | Phụ thuộc cấu hình registry |
| <code>spring.integration.handlers</code> | Gauge tổng số handler | Phụ thuộc cấu hình registry |
| <code>spring.integration.sources</code> | Gauge tổng số source | Phụ thuộc cấu hình registry |
| <code>spring.integration.channel.queue.size</code> | Gauge độ sâu <code>QueueChannel</code> được hỗ trợ | <code>type=channel</code>, <code>name</code> |

**Nhánh Observation API (6.x):**

| Observation/meter | Ý nghĩa | Key mặc định đáng chú ý |
|---|---|---|
| <code>spring.integration.handler</code> | Nhận/xử lý message ở handler, thường là timer | <code>spring.integration.name</code>, <code>spring.integration.type=handler</code> |
| <code>spring.integration.gateway</code> | Request–reply gateway | <code>spring.integration.name</code>, <code>spring.integration.outcome</code>, <code>spring.integration.type=gateway</code> |
| <code>spring.integration.producer</code> | Thao tác gửi ở channel/producer | <code>spring.integration.name</code>, <code>spring.integration.type=producer</code> |
| Các <code>.active</code> long-task meter | Theo dõi observation đang hoạt động khi handler hỗ trợ | Key có sẵn lúc observation bắt đầu; có thể chưa chứa thông tin outcome |

Tên meter cuối cùng phụ thuộc <code>ObservationHandler</code>, convention và phiên bản Micrometer được dùng. Hãy kiểm tra meter đang có trong registry thực tế trước khi cố định query Prometheus/Grafana.

### Kiểm tra nhanh metric trong ví dụ

~~~java
List<Timer> handlerTimers =
    meterRegistry.find("spring.integration.handler").timers();

long attemptsObserved = handlerTimers.stream()
    .mapToLong(Timer::count)
    .sum();

assertTrue(attemptsObserved >= 1);
~~~

Đoạn trên giả định flow ở mục 5 đã nhận ít nhất một message và <code>ObservationRegistry</code> có <code>DefaultMeterObservationHandler</code>. <code>Timer</code> thuộc <code>io.micrometer.core.instrument</code>. Trong ứng dụng thật, cần dùng tag chính xác (managed name, loại component) để tránh cộng timer của các flow khác vào nhau.

Nếu không có <code>spring.integration.handler</code>, trước tiên kiểm tra pattern, component ID, <code>ObservationRegistry</code> và handlers. Đừng ngay lập tức kết luận “Spring Integration không tạo metric”.

## 8. Observability không miễn phí: chọn phạm vi instrument

Một message có thể đi qua nhiều channel và handler. Nếu tất cả bước đều tạo span/timer, lượng metric và trace có thể tăng rất nhanh.

~~~text
HTTP inbound → input channel → transformer → router
             → executor channel → service activator
             → output channel → outbound gateway
~~~

Với một message, bạn có thể thấy nhiều observation khác nhau theo các **ranh giới framework**, không phải một số đo duy nhất cho toàn bộ business transaction.

Quy tắc lựa chọn:

1. Bắt đầu ở những endpoint có SLA hoặc lỗi quan trọng: inbound gateway, handler xử lý đơn hàng, outbound adapter.
2. Bật thêm channel observations khi cần tìm điểm nghẽn hoặc cần truyền trace context qua distributed/persistent channel.
3. Chỉ thêm low-cardinality tags như <code>spring.integration.type</code>, tên endpoint ổn định, loại thao tác.
4. Đưa order ID, tenant ID hoặc request correlation ID vào trace context/log có chính sách lưu trữ phù hợp, **không** dùng làm meter tags có cardinality không giới hạn.
5. Lấy sampling cho traces khi traffic cao; metrics thường tổng hợp toàn bộ để tránh mất xu hướng.
6. Đo overhead CPU/memory và chi phí collector trước/sau thay đổi instrumentation.

<code>observationPatterns = "*"</code> hữu ích cho khám phá trên staging, nhưng không nhất thiết là cấu hình tối ưu cho môi trường production tải lớn.

## 9. JMX MBean exporter là một cơ chế khác

Muốn xem/điều khiển channel và handler bằng JMX, cần thêm cơ chế **JMX export**. Spring Integration có <code>IntegrationMBeanExporter</code> và annotation <code>@EnableIntegrationMBeanExport</code> trong module <code>spring-integration-jmx</code>.

Ví dụ:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement
@EnableIntegrationMBeanExport(
    managedComponents = { "orders.*" })
public class JmxOrderManagementConfig {
}
~~~

Import <code>@EnableIntegrationMBeanExport</code> từ <code>org.springframework.integration.jmx.config</code> trong Spring Integration 6.x. Cần dependency JMX tương ứng, MBean server và cấu hình hạ tầng phù hợp. Ví dụ chỉ mô tả lớp export; không nên thêm một cấu hình tương tự nếu ứng dụng đã có exporter do hệ thống khác quản lý.

**Ba điểm phân biệt:**

- <code>@EnableIntegrationManagement</code> và <code>IntegrationManagement</code> cung cấp các cài đặt management và instrumentation cho component.
- <code>@EnableIntegrationMBeanExport</code> tạo đường **JMX MBean** riêng; chỉ các bean đáp ứng điều kiện exporter/pattern mới được đưa ra.
- Spring Boot Actuator có thể cung cấp endpoint về metrics/health và một số tích hợp khác tùy dependency/cấu hình; nó không đồng nghĩa mọi bean <code>IntegrationManagement</code> tự có MBean.

JMX có thể bộc lộ thuộc tính runtime và một số managed operations. Chỉ cấp quyền truy cập cho người vận hành đáng tin cậy; không mở cổng JMX ra mạng công cộng. Đặc biệt, các operation điều khiển stop/start/shutdown có thể ảnh hưởng tính sẵn sàng và giao dịch đang chạy.

## 10. IntegrationGraphServer và managed topology

Khi flow phức tạp, metric đơn lẻ chưa cho biết **message đã đi qua những node nào**. Spring Integration có <code>IntegrationGraphServer</code> biểu diễn topology runtime bằng graph của channel, handler, endpoint và các kết nối.

Ví dụ đọc graph:

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

Graph graph = graphServer.getGraph();
log.info("Integration graph: {}", graph);
~~~

Các kiểu thuộc <code>org.springframework.integration.graph</code>. Đoạn mã giả định application context đã có <code>IntegrationGraphServer</code> phù hợp. <code>getGraph()</code> trả mô hình được cache; metadata và thống kê có thể thay đổi theo runtime.

Với **dynamic flow** được thêm/gỡ trong khi ứng dụng chạy, cần gọi:

~~~java
Graph refreshed = graphServer.rebuild();
~~~

Điều này tạo lại snapshot topology và cache. Nếu không rebuild, đồ thị có thể vẫn phản ánh flow đã bị xóa hoặc chưa hiển thị flow vừa tạo. Không gọi rebuild liên tục trên mỗi message; đó là thao tác quản trị, có chi phí.

Graph rất hữu ích để trả lời:

- Message đang gửi qua channel nào và endpoint nào đang subscribe?
- Có handler nào là điểm cuối, không còn output?
- Một error flow đang nhận message từ những ranh giới nào?
- Sau khi đăng ký dynamic <code>IntegrationFlow</code>, topology đã thay đổi ra sao?

**Graph không phải distributed trace.** Một cạnh nối hai node mô tả cấu trúc; nó không chứng minh một message cụ thể đã đi qua cạnh đó, không lưu lịch sử replay và không thay thế correlation ID.

## 11. Quan sát thread, poller, transaction và error flow

Cùng một metric <code>spring.integration.handler</code> có thể được đo tại một điểm nhưng diễn giải khác nhau theo topology.

| Topology | Thread xử lý | Diễn giải metric/tracing |
|---|---|---|
| <code>DirectChannel</code> → handler | Thread sender | Handler latency có thể là một phần của thời gian <code>send()</code> đồng bộ |
| <code>ExecutorChannel</code> → handler | Worker thread | Sender có thể trả về trước handler; tách thời gian enqueue, chờ queue và thực thi |
| <code>QueueChannel</code> + poller | Poller/scheduler worker | Handler timer không tự đo thời gian message **nằm chờ trong queue** |
| <code>PublishSubscribeChannel</code> có executor | Executor của subscriber | Subscriber thất bại có thể được xử lý ở thread khác; send thành công chưa đồng nghĩa tất cả subscriber thành công |
| Reactive endpoint | Reactor worker/subscription | Observation phải đi qua reactive context và subscription thích hợp |
| Message broker adapter | Listener/container thread và worker sau handoff | ACK, redelivery và transport latency cần metric riêng của adapter/broker |

### Transaction commit không nằm trong mọi handler timer

Nếu <code>@Transactional</code> được áp dụng cho method của service, timer ở handler có thể bao quanh một phần hoặc toàn bộ method có proxy, nhưng transaction **bao ngoài flow** có thể commit sau khi handler đã trả về. Do đó:

- Handler duration không tự chứng minh transaction đã commit.
- Lỗi xảy ra sau handoff executor không làm bộ đếm lỗi của sender tăng theo cách giống lỗi đồng bộ.
- Retry advice đặt bên ngoài hay bên trong điểm instrument có thể thay đổi số attempt/duration được ghi nhận.
- Nếu error consumer bắt exception rồi hoàn tất bình thường, metric có thể coi endpoint đã recovery, không đồng nghĩa nghiệp vụ thành công.

Để có **business outcome** đáng tin cậy, cần metric ở biên use case hoặc khi transaction commit/recovery đã xác định, không chỉ ở channel.

### Poller có thể không tạo message vì nhiều nguyên nhân

Nếu source <code>receive()</code> trả <code>null</code> hoặc consumer đang dừng, metric handler có thể không đổi dù scheduler vẫn tick. Để chẩn đoán, kiểm tra cả:

1. <code>SmartLifecycle.isRunning()</code> của endpoint.
2. Lịch poll, <code>maxMessagesPerPoll</code>, <code>receiveTimeout</code> và khả năng scheduler còn worker.
3. Metric source receive, queue depth và adapter-specific metric.
4. Exception khi poll, error channel và transaction rollback.
5. Connection pool, executor saturation và network timeout.

Không biến một chỉ số <code>handler.count == 0</code> thành kết luận duy nhất rằng endpoint đã stop.

## 12. Correlation, trace propagation và message history

<code>correlationId</code> của Spring Integration thường là header nghiệp vụ dùng để nối các message, đặc biệt trong aggregator/splitter. **Trace ID** thuộc hệ thống tracing (OpenTelemetry/Brave qua Micrometer) và **message ID** là định danh một message. Chúng có vai trò khác nhau:

| Định danh | Dùng để | Không nên giả định |
|---|---|---|
| <code>MessageHeaders.ID</code> | Phân biệt message cụ thể | Ổn định qua mọi transformer, redelivery và tạo message mới |
| <code>correlationId</code> | Ghép message thuộc một request/batch | Chính là trace ID hoặc transaction ID |
| Trace/span ID | Theo dõi các observation qua các biên phân tán | Tự có mặt nếu chưa cấu hình tracing |
| Business event/idempotency ID | Ngăn side effect trùng khi retry/redelivery | Bằng message ID ngẫu nhiên |

Trong Spring Integration 6.x, Observation trên channel và consumer có thể hỗ trợ **propagate tracing context qua message headers**. Với persistent hoặc distributed channel, cần instrumentation phù hợp **cả phía gửi lẫn phía nhận** để trace context được gắn vào message trước khi chuyển qua thread/node và được khôi phục khi consumer đọc.

Nếu chỉ bật Observation ở một handler nhưng không bật ở channel phân tán, trace có thể bị tách thành hai đoạn. Điều này không có nghĩa message không đến; nó có thể chỉ thiếu propagation.

**Message history** là cơ chế khác, có thể được bật để ghi tên/loại component đã xử lý message vào headers khi được hỗ trợ. Nó không thay cho tracing spans, không tự duy trì lịch sử sau khi payload bị xóa khỏi store và có overhead riêng. Chỉ bật khi thật sự cần điều tra đường đi qua nhiều endpoint.

## 13. Tạo custom managed component khi cần

Nếu ứng dụng viết một handler hoặc source tùy chỉnh, lựa chọn dễ bảo trì là **kế thừa lớp cơ sở của Spring Integration**, chẳng hạn <code>AbstractMessageHandler</code> hoặc <code>AbstractMessageSource</code>. Những lớp này đã có vòng đời và instrumentation/framework contract thích hợp.

Ví dụ handler tùy chỉnh:

~~~java
public final class ValidationMessageHandler extends AbstractMessageHandler {

    @Override
    protected void handleMessageInternal(Message<?> message) {
        Object payload = message.getPayload();
        if (payload == null) {
            throw new IllegalArgumentException("Payload không hợp lệ");
        }
        // Chỉ thực hiện kiểm tra; tùy use case, handler khác sẽ phát reply.
    }

    @Override
    public String getComponentType() {
        return "validation-handler";
    }
}
~~~

<code>AbstractMessageHandler</code> thuộc <code>org.springframework.integration.handler</code>; <code>Message</code> thuộc <code>org.springframework.messaging</code>. Đoạn này là handler terminal; nếu cần biến đổi và gửi reply, nên kế thừa đúng lớp reply-producing hoặc dùng transformer Java DSL thay vì giả định <code>handleMessageInternal()</code> tự phát output.

Nếu viết bean chỉ là POJO tùy ý rồi tự triển khai <code>IntegrationManagement</code>, không nên giả định <code>IntegrationManagementConfigurer</code> sẽ biến mọi method của POJO thành observation tự động. Hãy xem điểm instrument thực tế, handler wrappers và test cho message gửi đến.

**Không nên** gọi <code>registerObservationRegistry()</code> thủ công cho mọi bean nếu <code>@EnableIntegrationManagement</code> đã quản lý phù hợp; việc tiêm instrumentation ở nhiều nơi có thể dẫn tới đo lường trùng hoặc cấu hình khó kiểm soát.

## 14. Kiểm thử observability đúng cách

Test management cần kiểm tra **cả cấu hình lẫn sự kiện quan sát thực tế**. Việc application context có <code>ObservationRegistry</code> chưa chứng minh một handler cụ thể đã instrument.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Channel managed name ổn định | <code>getManagedName()</code> đúng, không phụ thuộc UUID ngẫu nhiên |
| Bật <code>observationPatterns</code> cho handler | Có observation/timer sau khi gửi message |
| Handler ném runtime exception | Error outcome được phản ánh theo convention; caller nhận lỗi nếu flow đồng bộ |
| Pattern không khớp component | Không có Observation ở component đó theo cấu hình, nhưng flow vẫn xử lý message |
| <code>setLoggingEnabled(false)</code> | Giảm framework debug log của component; error handling vẫn hoạt động |
| Thay channel bằng <code>ExecutorChannel</code> | Sender và worker completion được phân biệt |
| Dynamic flow được tạo/gỡ | <code>IntegrationGraphServer.rebuild()</code> phản ánh topology mới |
| Queue backlog | Độ sâu queue có thể đo được từ queue gauge hoặc store, không suy từ handler timer |
| Correlation qua message store/broker | Trace nối được khi producer/consumer instrumentation thích hợp |

**Ví dụ JUnit 5** (giả định Spring test context đã nạp các bean ở mục 5):

~~~java
@Test
void managedChannelAndHandlerAreInstrumented() {
    DirectChannel channel = applicationContext.getBean(
        "orders.input", DirectChannel.class);

    assertEquals("orders.input", channel.getManagedName());

    channel.send(MessageBuilder
        .withPayload(new OrderCommand("O-T1", 2))
        .build());

    List<Timer> timers =
        meterRegistry.find("spring.integration.handler").timers();

    assertFalse(timers.isEmpty());
    assertTrue(timers.stream().mapToLong(Timer::count).sum() > 0);
}
~~~

Với <code>DirectChannel</code> trong ví dụ này, send xử lý đồng bộ nên assertion có thể chạy ngay sau call. Nếu đổi sang executor, dùng latch/Awaitility hoặc chờ điều kiện có timeout thay vì <code>Thread.sleep()</code> một thời gian cố định.

### Kiểm tra failure mà không dựa vào số timer đoán mò

~~~java
@Test
void failureDoesNotDisappearBecauseManagementIsEnabled() {
    DirectChannel channel = applicationContext.getBean(
        "orders.input", DirectChannel.class);

    assertThrows(RuntimeException.class, () -> channel.send(
        MessageBuilder
            .withPayload(new OrderCommand("O-BAD", 0))
            .build()));
}
~~~

<code>@EnableIntegrationManagement</code> không nuốt exception, tự retry hoặc điều khiển transaction; test này giữ ranh giới xử lý đồng bộ để kiểm chứng điều đó. Nếu flow có recovery advice, output/error channel hoặc interceptor, expected exception phải theo hợp đồng thực tế thay vì giả định luôn được ném cho sender.

## 15. Những lỗi thường gặp khi không thấy metric hoặc trace

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Có <code>MeterRegistry</code> nhưng không có <code>spring.integration.handler</code> | Đang dùng meters truyền thống, không có ObservationRegistry hoặc pattern | Xác định nhánh instrumentation, kiểm tra cả <code>spring.integration.send</code> |
| Có <code>ObservationRegistry</code> nhưng không thấy meter | Thiếu <code>ObservationHandler</code> chuyển thành metrics hoặc component không match | Kiểm tra handler đã đăng ký, <code>observationPatterns</code> và tên thực |
| Một handler không được đo | Bean/component name khác ID tưởng tượng, hoặc handler wrapper không instrument như mong đợi | Liệt kê <code>IntegrationManagement</code> và graph runtime |
| Metric có nhưng tag không khớp | Managed name/type hoặc naming convention thay đổi | Đọc tag thật từ registry trước khi sửa dashboard |
| Metrics và traces không nối nhau | Thiếu tracing handler/exporter hoặc context propagation qua channel | Cấu hình producer và consumer observation, tracer/exporter phù hợp |
| Queue tồn đọng nhưng handler latency thấp | Thời gian nằm chờ queue không nằm trong handler timer | Đo queue size, enqueue-to-start lag và executor saturation |
| Không thấy lỗi trên sender | Consumer chạy ở executor/poller, lỗi ở worker | Kiểm tra error channel/adapter và worker telemetry |
| Sau restart chỉ còn một phần số liệu | In-memory meter không phải persistent store; exporter chưa scrape hoặc backend retention | Xem topology scrape/export và khoảng lưu giữ |
| Sau đổi dynamic flow metric không cập nhật | Cached graph hoặc tên mới/series cũ | Rebuild graph, áp dụng meter filters và quản lý lifecycle |
| Cardinality tăng mạnh | Dùng tenant ID/message ID làm tag/managed name | Dùng tên component ổn định và low-cardinality tags |

### Quy trình điều tra đề xuất

1. Xác định phiên bản Spring Integration, Micrometer và việc ứng dụng đang dùng **meters truyền thống**, **Observation** hay cả hai ở các component khác nhau.
2. Xác nhận <code>@EnableIntegrationManagement</code>, pattern, tên component, cấu hình thủ công và việc có registry/handler.
3. Gửi một message test tới đúng channel, kiểm tra handler thật có chạy rồi mới đọc meter.
4. Kiểm tra ranh giới thread (Direct/Executor/Poller/Reactive) và nơi lỗi được phát lại.
5. So sánh metric ở channel, handler, source với queue depth, source polling và business outcome.
6. Kiểm tra tracer/propagator qua message headers nếu span bị đứt giữa các node.
7. Kiểm tra exporter/scrape/retention của hệ thống giám sát khi dữ liệu chỉ xuất hiện cục bộ.

## 16. Checklist triển khai production

- [ ] Có danh sách managed component quan trọng, tên ổn định và topology tương ứng.
- [ ] Dùng <code>IntegrationManagement</code> để cấu hình component; không nhầm với <code>SmartLifecycle</code> hoặc việc xuất MBean.
- [ ] Đã bật <code>@EnableIntegrationManagement</code> và chỉ chọn <code>observationPatterns</code> cần thiết; xác minh matching trên bean thật.
- [ ] Có <code>MeterRegistry</code>/<code>ObservationRegistry</code> phù hợp, ObservationHandler và exporter/scrape được cấu hình rõ ràng.
- [ ] Dashboard biết phân biệt legacy meter names với observation metric names; không giả định mọi metric tồn tại ở mọi phiên bản.
- [ ] Mọi alert quan trọng kết hợp handler error rate, latency, queue lag, poller status, executor saturation và business outcome.
- [ ] Traces được propagate qua message headers tại các biên async/persistent/distributed; correlation và idempotency ID được quản lý độc lập.
- [ ] JMX/Actuator/Control Bus chỉ được mở theo nguyên tắc least privilege, không để lộ thao tác điều khiển nhạy cảm.
- [ ] Không dùng raw tenant/message ID làm tag metric; đã đánh giá cardinality, sampling, chi phí và payload privacy.
- [ ] Có test đo metric/thất bại, lifecycle và dynamic graph; có runbook khi “không thấy message” hoặc “timer tăng nhưng request timeout”.

**Kết luận:** <code>IntegrationManagement</code> cung cấp hợp đồng **nhận diện và quản trị** các channel, handler, source và nhiều thành phần Spring Integration khác. <code>@EnableIntegrationManagement</code> đưa các cài đặt chung vào managed component; Micrometer/Observation tạo số liệu, JMX cung cấp đường quản lý riêng và graph mô tả topology. Khi kết hợp những lớp này với hiểu biết về thread, transaction, retry, message store và correlation, observability giúp trả lời không chỉ “thành phần nào chạy chậm” mà còn “message đang ở ranh giới nào và vì sao chưa hoàn tất”.

## Tài liệu tham khảo

- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration 6.5 Javadoc — IntegrationManagement](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/management/IntegrationManagement.html)
- [Spring Integration 6.5 Javadoc — EnableIntegrationManagement](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/EnableIntegrationManagement.html)
- [Spring Integration Reference — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Micrometer Reference — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
