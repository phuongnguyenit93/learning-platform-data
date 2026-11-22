# Managed endpoint và các thuộc tính runtime trong Spring Integration

## 1. Managed endpoint là gì và tại sao cần quản trị lúc chạy?

Trong **SPRING_INTEGRATION_RUNTIME**, một flow có thể gồm inbound adapter, message channel, consumer endpoint, handler, poller, executor và outbound adapter. Khi ứng dụng đã chạy, hệ thống vận hành thường cần biết **endpoint nào đang hoạt động**, có thể **tạm dừng nhận công việc** hay không, cách đo độ trễ/thông lượng và làm sao điều chỉnh flow khi bảo trì hoặc sự cố.

Chủ đề **Control và quản trị → Managed endpoint và các thuộc tính runtime** tập trung vào năng lực:

1. Nhận diện đúng **endpoint ID**, bean handler và channel; tránh quản trị nhầm đối tượng.
2. Hiểu vòng đời `SmartLifecycle`: `autoStartup`, `phase`, `start()`, `stop()`, `isRunning()`.
3. Phân biệt thuộc tính **cấu hình** với trạng thái/operation **có thể quản trị ở runtime**.
4. Điều khiển endpoint qua Java API, Control Bus, JMX hoặc công cụ quan sát thích hợp.
5. Theo dõi graph, metrics, logging, thread, poller, transaction, retry và trạng thái message đang xử lý.
6. Vận hành an toàn khi stop/restart, rolling deployment và đăng ký/xóa `IntegrationFlow` động.

**Managed endpoint không đồng nghĩa với một REST endpoint.** Trong bài này, *endpoint* là thành phần Spring Integration kết nối channel với handler hoặc message source, chẳng hạn `EventDrivenConsumer`, `PollingConsumer` và inbound adapter. *Managed* mô tả việc endpoint có trạng thái/vòng đời/thuộc tính được công cụ quản trị hoặc ứng dụng kiểm tra và điều khiển.

~~~mermaid
flowchart LR
    S["Inbound source"] --> C["MessageChannel"]
    C --> E["Consumer endpoint (SmartLifecycle)"]
    E --> H["MessageHandler"]
    H --> O["Output channel / downstream"]
    M["Control Bus / Java / JMX"] -.->|"start / stop / trạng thái"| E
    E -.-> P["Management / Metrics / Graph"]
    P -.-> A["Dashboard / operator"]
~~~

Khi endpoint được dừng, tác động thực tế phụ thuộc loại channel và source. Một `DirectChannel` không có consumer khác có thể từ chối message mới, trong khi queue bền vững có thể tiếp tục chứa message chờ poller khởi động trở lại. Không được suy rằng mọi lệnh `stop()` đều mang nghĩa "đóng băng toàn flow mà không có công việc nào đang chạy".

## 2. Phân biệt component, handler, endpoint và flow

Spring Integration không quản lý mọi đối tượng theo một kiểu giống nhau:

| Thành phần | Ví dụ | Vai trò | Thao tác runtime cần chú ý |
| --- | --- | --- | --- |
| **Channel** | `DirectChannel`, `QueueChannel`, `ExecutorChannel` | Vận chuyển message, xác định synchronous/async boundary | Subscriber, queue depth, send/receive metrics |
| **Handler** | `ServiceActivatingHandler`, `MessageHandler` tùy biến | Xử lý payload/headers, tạo reply hoặc side effect | Exception, latency, retry, advice, transaction |
| **Endpoint** | `EventDrivenConsumer`, `PollingConsumer` | Kết nối channel/source với handler và quản lý vòng đời | `start`, `stop`, `isRunning`, `autoStartup`, `phase` |
| **Source adapter** | JDBC/file/JMS/HTTP inbound adapter | Tạo/nhận message từ hệ thống ngoài | Poll/listener lifecycle, acknowledgement |
| **Poller** | `SourcePollingChannelAdapter` hoặc polling consumer | Chủ động lấy message theo trigger | Poll interval, `maxMessagesPerPoll`, executor |
| **Integration flow** | Các endpoint/channels ghép bằng Java DSL | Logic điều phối theo đường đi | Start/stop các endpoint, đăng ký động, hủy registration |
| **Management view** | Graph, metrics, JMX MBeans | Quan sát và điều khiển theo contract được công bố | Không tự tạo transaction, queue hoặc retry |

Một method `@ServiceActivator` được Spring Integration biến thành **message handler** và một **consumer endpoint** đứng trước handler. Người vận hành có thể cần dừng **consumer endpoint** mà không xóa bean chứa nghiệp vụ.

### ID không phải tên class

~~~text
Bean nghiệp vụ:        orderService
Handler adapter:       service-activating handler (framework tạo)
Consumer endpoint ID:  orderConsumer
Input channel:         orders
Flow registration ID:  ordersFlow
~~~

Những ID này có thể liên quan nhưng **không luôn giống nhau**. Khi cấu hình explicit ID cho endpoint, bạn tránh phụ thuộc tên bean do framework sinh từ annotation/DSL. ID ổn định cũng giúp log, JMX object naming, flow graph, alert và Control Bus rõ ràng qua các lần deploy.

**Quy tắc:** muốn `start()`/`stop()` chính xác, xác định bean nào implement `Lifecycle`/`SmartLifecycle` và ID tương ứng. Một bean `MessageHandler` tùy biến không tự nhiên có lifecycle endpoint chỉ vì tên method mang annotation.

## 3. SmartLifecycle: API nền tảng của managed endpoint

Nhiều endpoint Spring Integration kế thừa `AbstractEndpoint` và triển khai `SmartLifecycle` của Spring Framework. Các điểm quản trị thường gặp:

~~~java
import org.springframework.context.SmartLifecycle;

SmartLifecycle endpoint = ...;

boolean running = endpoint.isRunning();
boolean auto = endpoint.isAutoStartup();
int phase = endpoint.getPhase();

endpoint.start();
endpoint.stop();
~~~

`Lifecycle`/`SmartLifecycle` là contract của Spring, không riêng Spring Integration. Một số adapter có lifecycle đặc thù nhưng vẫn cần xem trạng thái và hành vi start/stop thực tế của implementation.

| API/thuộc tính | Vai trò | Hiệu lực cần hiểu |
| --- | --- | --- |
| `start()` | Bắt đầu lifecycle component | Kích hoạt subscription hoặc lịch polling/listener theo loại endpoint |
| `stop()` | Dừng component | Thường ngăn nhận việc mới; xử lý in-flight phụ thuộc component |
| `isRunning()` | Cho biết lifecycle state của component | **Không** đồng nghĩa healthy, không backlog, không lỗi |
| `isAutoStartup()` | Có tự start khi Spring context refresh không | Là chính sách khởi động, không phải công tắc tự thay đổi mỗi lần poll |
| `getPhase()` | Giá trị pha lifecycle dùng để sắp thứ tự | Giá trị lớn thường start sau và stop trước giá trị nhỏ |
| `stop(Runnable callback)` | Hỗ trợ dừng lifecycle theo callback | Một số component dừng bất đồng bộ; callback thể hiện hoàn tất shutdown theo contract |

### Phase và thứ tự khởi động

Trong một nhóm `SmartLifecycle` được quản lý bởi lifecycle processor của Spring:

- Khi **startup**, component có `phase` nhỏ hơn được khởi động trước component có `phase` lớn hơn.
- Khi **shutdown**, component có `phase` lớn hơn được dừng trước component có `phase` nhỏ hơn.
- Dependency rõ ràng giữa bean có thể ảnh hưởng thứ tự thực tế; `phase` không thay thế việc định nghĩa dependency.

Ví dụ muốn outbound resources/channel infrastructure sẵn sàng trước khi listener bắt đầu nhận traffic, có thể dùng phase/config/dependencies phù hợp. Nhưng không dùng số phase "thần kỳ" mà không kiểm thử startup/shutdown của adapter cụ thể.

~~~mermaid
sequenceDiagram
    participant C as ApplicationContext
    participant D as Downstream infrastructure
    participant P as Poller consumer
    participant O as Operator
    C->>D: start() phase nhỏ
    C->>P: start() phase lớn
    O->>P: stop()
    P-->>O: isRunning() = false
    O->>P: start()
    P-->>O: isRunning() = true
    C->>P: stop() khi shutdown
    C->>D: stop() khi shutdown
~~~

Nếu endpoint có `autoStartup=false`, nó **không tự chạy khi context refresh**, nhưng có thể được start bằng API hoặc cơ chế quản trị khi đã sẵn sàng.

## 4. Thuộc tính nào thực sự đổi được tại runtime?

Đây là khác biệt rất quan trọng giữa **managed property**, **configuration property** và **runtime state**.

| Thuộc tính/đối tượng | Đặt ở đâu | Thay đổi được khi đang chạy? | Ghi chú |
| --- | --- | --- | --- |
| Endpoint ID / bean name | DSL, annotation, XML, bean registration | **Không nên** đổi trên bean đang sống | Dùng để định danh component và quản trị |
| `autoStartup` | Cấu hình endpoint trước khi start context | Thường coi là **startup configuration** | Muốn bật/tắt ngay dùng `start()`/`stop()` |
| `phase` | Cấu hình lifecycle | Thường là **startup/shutdown configuration** | Đổi khi component đang chạy không lập tức sắp lại flow |
| `isRunning()` | Lifecycle runtime | **Đọc được** | Không bảo đảm xử lý message cuối đã commit |
| `start()`/`stop()` | Operation của endpoint | **Có** khi component hỗ trợ | Cần quyền vận hành, hiểu in-flight work |
| Input/output channel | Cấu hình endpoint | Không xem là runtime hot-switch mặc định | Có thể cần dừng và tạo lại flow/endpoint |
| Poller `fixedDelay`/`cron` | Trigger/poller config | Tùy implementation và API trigger | Không có nút chung bảo đảm mọi poller đổi được live |
| `maxMessagesPerPoll` | Poller config | Tùy endpoint/setter/JMX API thực tế | Không đồng nhất với giới hạn concurrency |
| Executor pool/queue capacity | Bean executor | Tùy loại executor và cấu hình | Chỉnh pool có thể ảnh hưởng backpressure |
| Retry/advice chain | Endpoint/handler config | Thường cần cấu hình lại/đăng ký lại | Thay advice tùy tiện khi inflight có thể sai semantics |
| Transaction manager / message store | Endpoint/source wiring | **Không** đổi tùy tiện live | Đổi resource có thể ảnh hưởng atomicity/durability |
| Metrics/observability | Integration management/registry | Tùy version/config | Không mọi component đều có cùng counter/JMX operation |

**Không kết luận từ việc có setter trong Java class rằng setter an toàn để gọi khi endpoint đang running.** Nhiều setter nhằm cấu hình *trước initialization*. Với thay đổi cấu trúc (channel, poller, retry policy), phương án an toàn thường là chuẩn bị phiên bản flow mới, kiểm thử, dừng/drain flow cũ rồi chuyển đổi có kiểm soát.

## 5. Ví dụ Java hoàn chỉnh: start/stop EventDrivenConsumer

Ví dụ Java 17+, Spring Boot và Spring Integration. Đặt toàn bộ code vào file `ManagedEndpointDemoApplication.java` thuộc package `demo.integration`. Cần dependency Spring Integration core hoặc `spring-boot-starter-integration` tương thích Spring Boot.

Demo có:

- Một `DirectChannel` tên `orders`.
- Một `EventDrivenConsumer` tên `orderConsumer` với `autoStartup=false`.
- `ApplicationRunner` chủ động start consumer, gửi message thành công, stop và thử gửi sau stop.
- Một message handler đơn giản để thấy message nào thực sự tới endpoint.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class ManagedEndpointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagedEndpointDemoApplication.class, args);
    }

    @Bean("orders")
    SubscribableChannel orders() {
        return new DirectChannel();
    }

    @Bean("orderConsumer")
    EventDrivenConsumer orderConsumer(
            @Qualifier("orders") SubscribableChannel orders) {

        MessageHandler handler = message -> {
            System.out.printf("HANDLE payload=%s traceId=%s thread=%s%n",
                    message.getPayload(),
                    message.getHeaders().get("traceId"),
                    Thread.currentThread().getName());
        };

        EventDrivenConsumer endpoint =
                new EventDrivenConsumer(orders, handler);
        endpoint.setAutoStartup(false);
        endpoint.setPhase(100);
        return endpoint;
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("orderConsumer") EventDrivenConsumer endpoint,
            @Qualifier("orders") MessageChannel orders) {

        return args -> {
            System.out.println("BEFORE running=" + endpoint.isRunning());

            endpoint.start();
            try {
                System.out.println("AFTER_START running="
                        + endpoint.isRunning());

                orders.send(MessageBuilder
                        .withPayload("ORD-101")
                        .setHeader("traceId", "trace-101")
                        .build());

                endpoint.stop();
                System.out.println("AFTER_STOP running="
                        + endpoint.isRunning());

                try {
                    orders.send(MessageBuilder
                            .withPayload("ORD-102")
                            .setHeader("traceId", "trace-102")
                            .build());
                }
                catch (MessageDeliveryException ex) {
                    System.out.println("SEND_AFTER_STOP_FAILED: "
                            + ex.getClass().getSimpleName());
                }
            }
            finally {
                endpoint.stop();
            }
        };
    }
}
~~~

Kết quả về mặt hành vi:

~~~text
BEFORE running=false
AFTER_START running=true
HANDLE payload=ORD-101 traceId=trace-101 thread=...
AFTER_STOP running=false
SEND_AFTER_STOP_FAILED: MessageDeliveryException
~~~

Giải thích:

1. Bean consumer được tạo nhưng `autoStartup=false` nên Spring context không tự bật.
2. `endpoint.start()` đăng ký consumer vào `SubscribableChannel` tương ứng.
3. `DirectChannel` gọi handler **đồng bộ** trên thread gửi; message `ORD-101` được xử lý.
4. `endpoint.stop()` dừng subscription của consumer.
5. Khi `DirectChannel` **không còn subscriber nào**, gửi `ORD-102` có thể ném `MessageDeliveryException` vì không có người nhận.
6. `isRunning()` cho biết state của consumer, **không phải** chứng nhận database/HTTP đã thành công hoặc backlog bằng không.

Nếu có **consumer khác** trên cùng `orders` channel, việc stop một consumer không bảo đảm mọi message mới bị từ chối; dispatcher có thể gửi tới subscriber còn lại. Với channel có executor/poller, thời điểm commit và lỗi cũng khác.

### Vì sao nên lấy bean endpoint thay vì gọi handler?

Nếu code chỉ có:

~~~java
orderService.process(order);
~~~

thì bạn đã gọi **method nghiệp vụ trực tiếp**, bỏ qua messaging endpoint, channel, transaction/advice/retry wiring và lifecycle. Một lệnh `start()/stop()` cần nhắm vào endpoint được Spring Integration quản lý, không phải method nghiệp vụ.

## 6. Annotation và Java DSL: ID để quản trị

Trong dự án thực tế, phần lớn endpoint được tạo từ annotation hoặc DSL chứ không khai báo `EventDrivenConsumer` thủ công.

Ví dụ Java DSL (một phương án thay thế ví dụ mục 5):

~~~java
@Bean
IntegrationFlow processingFlow(OrderService service) {
    return IntegrationFlow.from("orders")
        .handle(service, "process", e -> e
            .id("ordersHandlerEndpoint")
            .autoStartup(false))
        .get();
}
~~~

Đoạn trên yêu cầu `OrderService`/channel đã được định nghĩa và import DSL phù hợp. Endpoint ID `ordersHandlerEndpoint` có thể được tra cứu/điều khiển theo bean mà DSL đăng ký trong context. **Không** đồng thời giữ một consumer khác trên cùng channel nếu ví dụ của bạn giả định đúng một consumer.

Một số annotation endpoint cho phép cấu hình lifecycle, ví dụ `@ServiceActivator` có input channel, `autoStartup` và `phase` theo phiên bản hỗ trợ. Khi dùng annotation, cần quan sát **bean endpoint được sinh** và ID của nó; không suy từ tên class handler. Dùng annotation/DSL nào cũng phải kiểm tra phiên bản dependency trước khi copy thuộc tính.

### ID và tên endpoint trong runtime graph

- Bean name của handler tùy biến có thể là `orderService`.
- Endpoint ID do DSL đặt rõ có thể là `ordersHandlerEndpoint`.
- Flow ID có thể là `processingFlow`.
- Input channel là `orders`.

Graph và JMX có thể hiển thị các identity này theo cách khác nhau, không được dùng string tìm kiếm ngẫu nhiên rồi stop nhầm adapter.

## 7. Control Bus: điều khiển endpoint qua message

**Control Bus** trong Spring Integration là mẫu chuyển một **message chứa biểu thức điều khiển** thành invocation tới bean/operation được phép. Nó thuận tiện khi cần vận hành bằng messaging, nhưng là **kênh điều khiển nhạy cảm**, cần được bảo vệ kỹ.

Ví dụ cấu hình Java DSL:

~~~java
@Bean
IntegrationFlow controlFlow() {
    return IntegrationFlow.from("controlCommands")
            .controlBus()
            .get();
}
~~~

Yêu cầu channel `controlCommands` và các bean endpoint trong context. Một payload SpEL được phép truy cập bean có thể gọi:

~~~text
@orderConsumer.stop()
@orderConsumer.start()
@orderConsumer.isRunning()
~~~

Có thể gửi command từ code nội bộ đã được cấp quyền:

~~~java
MessageChannel commands = ...;

commands.send(MessageBuilder
        .withPayload("@orderConsumer.stop()")
        .build());
~~~

**Lưu ý quan trọng:** Control Bus không phải một HTTP endpoint công khai. SpEL có thể thực thi operation trên bean; không để payload từ client không tin cậy chạy trực tiếp qua control bus. Giới hạn nguồn gửi, xác thực/phân quyền, allowlist command, ghi audit (người thực hiện, thời điểm, lý do), timeout và đảm bảo có quy trình khôi phục khi stop nhầm.

Ngoài ra, câu lệnh đã được channel chấp nhận **không phải** luôn đồng nghĩa việc dừng endpoint đã hoàn tất nếu có async boundary. Với thay đổi ảnh hưởng traffic, xác minh `isRunning()` và đo số công việc in-flight.

### Khi nào Control Bus hợp lý?

| Nhu cầu | Có nên dùng Control Bus? | Ghi chú |
| --- | --- | --- |
| Dừng tạm một poller nội bộ đã biết ID | Có thể | Có audit và quyền thao tác |
| Khởi động lại consumer theo runbook | Có thể | Chỉ khi không làm mất message |
| Cho tất cả HTTP client gửi SpEL tự do | **Không** | Rủi ro gọi bean/operation không được phép |
| Đổi transaction manager trong khi flow chạy | Không giải quyết bằng `start/stop` | Cần migration/re-registration có kiểm chứng |
| Xem `isRunning()` trong code quản trị | Có thể dùng Java API trực tiếp | Thường đơn giản hơn nếu cùng process |
| Điều khiển cluster nhiều instance | Phải thiết kế thêm | Mỗi context có endpoints/lifecycle riêng |

Một lệnh gửi tới Control Bus của instance A **không tự stop** endpoint tương ứng ở instance B. Cần điều phối đa node hoặc thực hiện hành động trên từng instance theo cơ chế vận hành được kiểm soát.

## 8. JMX và các thuộc tính quản lý

Spring Integration hỗ trợ JMX management qua các cơ chế exporter/integration management tùy phiên bản. Khi JMX được cấu hình, endpoint/channel/handler đủ điều kiện có thể hiển thị thành **MBeans** với attributes/operations được framework export.

Các khả năng quan sát thường gặp:

| Nhóm quản trị | Ví dụ cần xem | Không nên giả định |
| --- | --- | --- |
| Lifecycle | Running, start/stop trên endpoint hỗ trợ | Mọi class có bean name đều có MBean |
| Handler/channel stats | Send count, receive count, error count, duration | Tên metric/MBean attribute giống nhau ở mọi version |
| Polling | Poller đang active, số message mỗi poll | `fixedDelay` có thể hot-update ở mọi implementation |
| Channel | Queue depth, active subscribers, dispatch behavior | Mọi channel có persistent backlog |
| Dynamic flows | Flow registrations, endpoint state | JMX tự cập nhật chính xác mọi custom state không đăng ký |
| Errors | Tỷ lệ exception và error flow | Có error count đồng nghĩa có DLQ bền vững |

**JMX MBean object name không đơn thuần là bean name.** `IntegrationMBeanExporter` có naming domain, type và object name mapping phụ thuộc integration configuration/version. Đừng hardcode chuỗi JMX object name nếu chưa xem instance thực tế.

Spring Boot Actuator cũng có thể cung cấp **`integrationgraph`** và metrics endpoints khi đã cài các dependency/module cần thiết và bật exposure tương ứng. Graph chủ yếu phục vụ **quan sát topology**, không thay thế endpoint management với quyền chạy lệnh.

Về bảo mật:

- Đừng mở JMX remote công khai khi chưa có authentication, TLS và network policy.
- Đừng phơi bày toàn bộ Actuator endpoints nhạy cảm trên Internet.
- Giới hạn thông tin headers/payload chứa dữ liệu riêng tư trong graph/metrics/log.
- Tách read-only monitoring khỏi quyền Control Bus/JMX operation ghi trạng thái.

## 9. Graph và observability: đang chạy không đồng nghĩa khỏe

Spring Integration có thể mô tả topology runtime: channels, handlers, endpoints, links và flow components. Graph giúp trả lời:

- Message đi từ channel nào tới handler nào?
- Endpoint nào có ID phải stop?
- Có nhánh nào không có consumer?
- Có async boundary giữa hai handlers?
- Một flow động vừa đăng ký có những components nào?

Tuy nhiên graph thể hiện **cấu trúc và một phần state**, không phải chứng minh message đã commit. Một endpoint running vẫn có thể:

- Bị kẹt I/O và không hoàn thành message.
- Có poller chạy nhưng không nhận được message.
- Có executor queue đầy, thread pool bão hòa.
- Retry/backoff liên tục khiến throughput gần 0.
- Gửi message đến error channel nhưng recovery consumer thất bại.
- Giữ message group lâu vì correlation/release strategy không hoàn tất.

### Ba lớp quan sát

| Lớp | Câu hỏi | Tín hiệu |
| --- | --- | --- |
| **Topology/lifecycle** | Endpoint có tồn tại, running không? | Graph, `isRunning()`, bean state, JMX |
| **Flow-level performance** | Input → output mất bao lâu, throughput ra sao? | Metrics, tracing, queue/backlog, poll duration |
| **Business-level completion** | Order có commit, broker đã ack, error được lưu chưa? | DB/broker/DLQ/outbox, eventId và traceId |

Không đưa `orderId`, `eventId`, `correlationId` thô vào metric tags vì cardinality lớn. Dùng endpoint, channel, outcome, exception class và nhóm traffic làm tags; ID nghiệp vụ đặt trong trace/log được kiểm soát.

## 10. Thuộc tính poller và ảnh hưởng runtime

Polling consumer chủ động lấy message từ `PollableChannel` hoặc inbound message source. Các tham số thường gặp:

- `fixedDelay` / `fixedRate` / `cron`: lịch kích hoạt poll.
- `maxMessagesPerPoll`: giới hạn số message xử lý trong một lần poll.
- `receiveTimeout`: thời gian đợi khi channel không có message.
- `taskExecutor`: nơi thực thi poll tasks khi được cấu hình.
- `adviceChain`: có thể bao transactional polling, retry hoặc custom advice.
- `errorChannel`/error handler: nơi ghi nhận exception từ polling boundary.

Ví dụ XML **minh họa**, không phải file XML độc lập:

~~~xml
<int:service-activator
        id="ordersPollingConsumer"
        input-channel="ordersQueue"
        ref="orderHandler"
        method="process"
        auto-startup="false"
        phase="100">
    <int:poller fixed-delay="1000"
                max-messages-per-poll="10"/>
</int:service-activator>
~~~

Cần cấu hình namespace `int`, channel `ordersQueue` có kiểu `PollableChannel`, bean `orderHandler` và transaction/error infrastructure khi cần. Đây là ví dụ **thiết lập trước khi chạy**, không phải lời hứa mọi attribute poller có thể đổi trực tiếp bằng JMX khi đang running.

### Khi stop polling consumer

~~~text
QueueChannel + persistent MessageStore
       |
       v
PollingConsumer stop()
       |
       +-- Không poll thêm khi đã dừng
       +-- Message mới có thể tiếp tục nằm trong queue nếu producer/store cho phép
       +-- In-flight handling/transaction cần quan sát đến khi hoàn tất
       +-- Queue depth tăng nếu producer tiếp tục gửi
~~~

Không suy rằng `stop()` sẽ undo một `receive()` đã diễn ra, rollback transaction đang chạy hoặc tự trả message về queue. Điều đó tùy source/store, transaction manager, retry/error policy và thời điểm stop.

### Các phép đo poller nên có

| Metric | Giá trị giúp điều tra |
| --- | --- |
| Poll trigger count | Poller có thực sự được schedule? |
| Message received/processed | Poll rỗng hay có dữ liệu? |
| Poll duration p95/p99 | Poll có bị kéo dài bởi handler/transaction? |
| Oldest queued message age | Backlog có nghiêm trọng? |
| Queue depth | Producer nhanh hơn consumer? |
| Executor active/queued tasks | Thread pool có nghẽn? |
| Errors/retries/recoveries | Lỗi có khiến throughput giảm? |

Nếu poller bị dừng tạm, dashboard nên hiển thị trạng thái **paused intentionally** thay vì báo hệ thống hoàn toàn lỗi; đồng thời theo dõi queue capacity và retention để tránh mất dữ liệu do backlog.

## 11. ExecutorChannel: stop endpoint và in-flight tasks

Với `ExecutorChannel`, message được giao cho worker thread sau async handoff. Việc gọi `stop()` trên một consumer endpoint không có nghĩa các task đã handoff đều bị hủy hoặc rollback.

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as ExecutorChannel
    participant W as Worker
    participant O as Operator
    S->>C: send(M1)
    C->>W: submit task M1
    C-->>S: handoff accepted
    O->>W: stop consumer endpoint
    Note over W: M1 có thể đang xử lý
    W->>W: handler/transaction/retry
    Note over O,W: Phải quan sát in-flight tasks
~~~

Các điểm cần nhớ:

- Sender có thể coi handoff là thành công trước khi handler thực sự chạy.
- Exception trên worker không tự lan tới caller đã rời call stack.
- Transaction context kiểu imperative thường không tự truyền sang thread worker.
- Stop có thể ngăn tiếp nhận công việc mới nhưng nhiệm vụ đang chạy chưa chắc kết thúc.
- Khi shutdown executor, phải xác định policy đối với queued tasks, active tasks, interruption và rejection.
- Nếu message không lưu bền vững trước handoff, restart có thể làm mất việc đã được chấp nhận nhưng chưa xử lý xong.

**Quản trị endpoint khác quản trị executor.** Endpoint `isRunning()` và executor `activeCount`/`queueSize` là những tín hiệu khác nhau. Một endpoint đã stop có thể vẫn còn tasks đang hoàn tất.

## 12. Transaction, retry và ErrorMessage khi điều khiển endpoint

| Tình huống | Rủi ro | Cách vận hành |
| --- | --- | --- |
| Stop trước khi handler kết thúc | In-flight chưa commit, caller có thể timeout | Có graceful drain, kiểm tra outstanding work |
| Stop trong chu kỳ poll có transaction | Message đã receive nhưng chưa commit/rollback | Đợi transaction boundary, kiểm tra nguồn redelivery |
| Start lại cùng consumer | Message backlog có thể đổ vào đột ngột | Rate limit, concurrency, quan sát downstream capacity |
| Retry/backoff đang chạy | Worker giữ tài nguyên sau khi ra lệnh stop | Xem retry policy, timeout và số active invocations |
| Recovery gửi ErrorMessage | Error consumer có thể đang stop hoặc không tồn tại | Đảm bảo error flow được giữ hoạt động trước khi start input |
| Dynamic flow bị destroy | Địa chỉ reply/error hoặc subscription có thể biến mất | Drain và kiểm tra tất cả in-flight/correlation |
| Rolling deployment | Hai bản ứng dụng cùng tiêu thụ một nguồn | Kiểm tra message ownership, idempotency và compatibility |

### Stop không phải rollback

Một handler đã ghi DB và commit trước khi endpoint stop **không bị hoàn tác** chỉ vì lifecycle state đổi. Ngược lại, một inbound adapter có transaction có thể rollback khi xử lý lỗi, khiến broker redeliver sau khi consumer restart.

**Không nhầm:** `errorChannel` là đường đi của `ErrorMessage`; nó không tự động kéo transaction cũ về hoặc bảo đảm một message đã được lưu DLQ. Khi stop/restart, luôn xác nhận **business state** và **acknowledgement state** ở tài nguyên thật.

### Thứ tự an toàn để tạm ngừng xử lý

1. Ngăn nguồn tạo thêm message hoặc dừng inbound endpoint phù hợp.
2. Kiểm tra các task in-flight, poller đang chạy, transaction đang mở.
3. Đảm bảo error/recovery path vẫn có consumer để nhận lỗi cuối.
4. Đợi hoặc áp dụng timeout/drain policy có kiểm soát.
5. Ghi trạng thái đã đạt được: số event đã commit, queue depth, DLQ và những công việc chưa hoàn tất.
6. Thực hiện bảo trì/deploy/đổi cấu hình.
7. Khởi động downstream dependencies trước, rồi mới bật inbound/consumer theo thứ tự.
8. Theo dõi tốc độ xả backlog, retry storms, duplicate và latency sau restart.

## 13. Start/stop theo cluster: mỗi ApplicationContext là một phần riêng

Trong hệ thống nhiều pods, mỗi pod có ApplicationContext, registry, endpoint lifecycle và executor **riêng**.

~~~text
Pod A: endpoint ordersConsumer -> running
Pod B: endpoint ordersConsumer -> running
Pod C: endpoint ordersConsumer -> stopped
~~~

Stop endpoint ở pod C **không có nghĩa** pod A/B cũng stop. Nếu cùng đọc từ một broker/queue, việc dừng một consumer có thể chuyển tải sang các consumer khác và làm chúng nóng lên.

Đối với cluster:

- Có controller/runbook với danh sách instance đích, quyền quản trị và kết quả từ từng instance.
- Phân biệt **drain một instance** với **pause toàn logical flow**.
- Nếu dùng shared message store/lock registry, bảo đảm ownership và concurrency đúng.
- Khi scale in/rolling restart, xử lý ack, rebalance, pending tasks và retry dựa trên adapter.
- Xác minh dynamic registration không tạo ID conflict trong cùng context, và cùng ID ở nhiều context không đồng nghĩa cùng bean object.
- Đừng để network Control Bus tự biến thành cluster-wide remote code execution.

## 14. Đăng ký và hủy IntegrationFlow động

Spring Integration cung cấp `IntegrationFlowContext` để đăng ký flow runtime. Đây là công cụ phù hợp khi cần tạo/tắt một nhóm endpoint có vòng đời riêng (ví dụ theo tenant), thay vì sửa cấu hình của bean đã initialized.

Một đoạn minh họa theo Java DSL:

~~~java
IntegrationFlow newFlow = flow -> flow
        .filter(String.class, s -> !s.isBlank())
        .handle(message -> System.out.println(message.getPayload()));

IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(newFlow)
                .id("tenantAFlow")
                .autoStartup(false)
                .register();

registration.start();
// ... sử dụng flow qua input channel hoặc messaging template của registration ...
registration.stop();
registration.destroy();
~~~

Đây là snippet thiết kế, cần bean `IntegrationFlowContext` và imports theo version; input channel cần xác định trước khi gửi message thực tế. Các API builder/registration có thể có khác biệt nhỏ giữa dòng Spring Integration. **Không** viết code tự động destroy flow ngay khi đang có reply pending mà chưa kiểm chứng cleanup và ack.

### Phân biệt stop với destroy

| Thao tác | Tác dụng | Dùng khi |
| --- | --- | --- |
| `start()` | Cho endpoint/flow registration nhận và xử lý theo contract | Khôi phục flow đã chuẩn bị sẵn |
| `stop()` | Ngăn hoặc hạn chế tiếp nhận công việc mới | Bảo trì, giảm tải, pause có thể resume |
| `destroy()` registration | Hủy bean/registration động khỏi context | Tenant/service không còn cần flow, deploy cấu hình mới |
| Stop inbound adapter | Ngăn tạo/nhận message từ source cụ thể | Pause nguồn, drain downstream |
| Stop polling consumer | Ngừng poll queue | Giữ lại backlog nếu queue/store hỗ trợ |

Flow động có thể chia sẻ bean infrastructure với flow khác: message store, executor, transaction manager, `RequestHandlerRetryAdvice`, error channel. Destroy một flow **không có nghĩa** mọi dependency dùng chung cũng bị xóa.

## 15. Quản lý thuộc tính runtime khác dynamic reconfiguration

Giả sử muốn thay poll interval từ 1 giây thành 5 giây. Có ít nhất ba chiến lược:

| Chiến lược | Ưu điểm | Điều phải kiểm tra |
| --- | --- | --- |
| Sửa thuộc tính qua một management operation **được component hỗ trợ** | Không cần restart nếu API bảo đảm | Có an toàn thread, trigger cập nhật lịch đúng không? |
| Stop/reconfigure/start endpoint bằng API chính thức | Có boundary rõ hơn | Setter có được phép sau initialization, có tasks đang chạy? |
| Dựng registration/flow mới rồi chuyển tải | Dễ kiểm thử rollback cấu hình | Không nhân đôi consumer, không mất in-flight, ID/key phù hợp |

**Không** thay đổi arbitrary Spring bean fields từ JMX/SpEL rồi giả định scheduler, transaction interceptor và handler dispatcher tự đọc lại. Mọi hot-update cần được kiểm chứng theo **implementation và phiên bản**. Với thay đổi cấu trúc, phiên bản hóa config, đăng ký flow mới và cutover có kiểm soát thường dễ tin cậy hơn.

### Concurrency và throughput

Thay `maxMessagesPerPoll` hoặc executor pool size có thể tăng throughput, nhưng:

- Poller có thể đang chờ `receiveTimeout`/I/O, không chỉ bị giới hạn bởi max messages.
- `DirectChannel` đồng bộ thì tăng executor khác không giúp nếu vẫn chạy trên sender thread.
- Aggregator/`LockRegistry` có một hot correlation key vẫn phải giữ critical section tuần tự.
- Database/remote API có rate limit, tăng worker có thể gây retry storm.
- Stop/start liên tục không sửa lỗi serialization, message store hoặc correlation strategy.

Cần quan sát p95/p99 latency, queue depth, retry/error rate và số active threads trước/sau điều chỉnh.

## 16. Cách chẩn đoán endpoint “running nhưng không có kết quả”

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| `isRunning()=true` nhưng không có message | Source/poller rỗng, upstream stopped, sai channel | Graph, send/receive count, source metrics |
| `start()` xong DirectChannel vẫn lỗi no subscribers | Start nhầm bean, wrong input channel, endpoint init lỗi | Endpoint ID, actual subscribers, logs |
| `stop()` nhưng vẫn có log xử lý | In-flight worker/poller hoặc consumer khác | Active tasks, correlation, thread timeline |
| Một consumer stop nhưng message vẫn đi tiếp | Channel có subscriber khác | Topology/dispatcher |
| Poller running nhưng queue depth tăng | Handler chậm, DB lock, `maxMessagesPerPoll` nhỏ | Poll duration, executor, store latency |
| Executor queue đầy dù endpoint running | Thread pool saturation, blocking I/O/retry | Queue size, active workers, reject count |
| Một flow restart rồi xử lý trùng | Broker redelivery, source replay, không có idempotency | eventId, ack logs, inbox/outbox |
| JMX không thấy endpoint | Chưa bật export hoặc tên/điều kiện export khác | Management config, MBeanServer registry |
| Integration graph không hiện flow vừa tạo | Graph snapshot chưa refresh/management chưa enable | Registration state và graph endpoint |
| Error count tăng nhưng errorChannel trống | Lỗi sync tới caller, publisher signal hoặc error handler khác | Thread/boundary, error publishing config |
| Stop xong vẫn lock/transaction | In-flight operation, TTL/lease, chưa drain | Thread dump, transaction duration, lock ownership |
| `autoStartup=false` nhưng consumer vẫn nhận | Có consumer/flow khác cùng source | Graph, bean IDs, handler subscriptions |

### Quy trình debug theo bằng chứng

1. **Xác định ID:** endpoint bean, handler bean, input channel, source adapter và flow registration.
2. **Đọc state:** `isRunning`, startup phase, auto startup config và version build.
3. **Vẽ topology:** từ source qua channel → endpoint → handler → output/error channels.
4. **Lấy dữ liệu traffic:** message in/out, queue depth, oldest message age, poll rate, success/failure.
5. **Đánh dấu ranh giới async:** executor, poller, broker listener, reactive publisher.
6. **Đối chiếu transaction/retry:** nơi commit, exception có bị nuốt/trap, retry callback và DLQ.
7. **Thử stop/start trên môi trường kiểm soát:** xác nhận không mất message, không nhân đôi consumer.
8. **Đánh giá hậu quả:** backlog, side effects, correlation groups và resource cleanup.

Có thể bật DEBUG logging có kiểm soát cho Spring Integration endpoint/dispatcher và Spring transaction. Không log payload hoặc headers nhạy cảm trên môi trường production chỉ để debug.

## 17. Kịch bản vận hành có runbook

### Kịch bản A — Dừng poller để bảo trì database

**Bối cảnh:** `QueueChannel` có persistent message store, consumer polling để ghi DB. DB sắp nâng cấp.

**Đề xuất vận hành:**

1. Xác nhận queue bền vững, nguồn upstream có thể tiếp tục tạo backlog và dung lượng đủ.
2. Dừng poller consumer (đúng endpoint ID).
3. Chờ các transaction active kết thúc, kiểm tra không còn in-flight database writes.
4. Thực hiện bảo trì DB; đảm bảo error flow không bị vô hiệu hóa ngoài ý muốn.
5. Start poller; quan sát tốc độ drain và lỗi redelivery.
6. Đối chiếu eventId/record DB với broker/store để xác nhận không thiếu hoặc tạo trùng.

**Cạm bẫy:** nếu queue chỉ trong memory và pod restart trong bảo trì, backlog có thể mất. `stop()` không biến in-memory queue thành persistent store.

### Kịch bản B — Tạm dừng inbound adapter khi downstream lỗi

**Bối cảnh:** API thanh toán trả 503; handler đang retry và chiếm workers.

**Đề xuất:** giảm đầu vào từ inbound endpoint, bảo đảm messages nguồn được giữ theo ack policy; đợi các attempt hiện tại hoàn tất hoặc timeout, duy trì error/recovery consumer, sau đó resume theo tốc độ có giới hạn.

**Cạm bẫy:** một source adapter đã đọc và ack message trước khi stop có thể không phát lại; phải kiểm tra adapter contract chứ không dựa vào lifecycle flag.

### Kịch bản C — Đăng ký flow mới cho tenant

**Bối cảnh:** tenant A cần routing handler riêng.

**Đề xuất:** đăng ký flow với ID ổn định, `autoStartup=false`, xác nhận output/error dependencies, start đúng thời điểm, theo dõi eventId/correlation, stop/drain rồi destroy khi tenant rời hệ thống.

**Cạm bẫy:** không tạo hai competing consumers ngoài ý muốn cùng input channel; tránh destroy khi request-reply gateway còn đợi trả lời.

## 18. Bài thực hành

1. **Lifecycle cơ bản:** chạy `ManagedEndpointDemoApplication`, xác nhận `isRunning()` trước/sau start và khi stop; kiểm tra lỗi gửi message khi DirectChannel không có subscriber.
2. **Nhiều consumer:** thêm subscriber khác vào cùng channel, stop một consumer và giải thích tại sao `send()` vẫn có thể thành công.
3. **Startup phase:** tạo hai endpoint có phase khác nhau, ghi log start/stop để quan sát thứ tự lifecycle khi context khởi động/dừng.
4. **Control Bus:** cấu hình channel nội bộ và flow `.controlBus()`, gửi `@orderConsumer.stop()`/`start()`; giới hạn nguồn lệnh và ghi audit.
5. **Poller:** thay `DirectChannel` bằng `QueueChannel` với polling consumer; kiểm tra backlog khi stop và sau restart (so sánh memory vs persistent store).
6. **Executor:** dùng `ExecutorChannel`; chạy task chậm, gọi stop; xác minh trạng thái endpoint và số task in-flight là hai đại lượng khác.
7. **JMX:** bật integration management trên môi trường test phù hợp version; tìm endpoint bằng ID, đọc running state và counter được exporter hỗ trợ.
8. **Graph:** bật Actuator integration graph theo version, đối chiếu endpoint/channels với định nghĩa flow và phát hiện nhánh không có consumer.
9. **Fault injection:** cho handler throw sau khi ghi DB; so sánh exception trên `DirectChannel`, executor và poller.
10. **Retry/backoff:** tạo message tạm lỗi và dừng endpoint khi retry đang chờ; ghi lại lúc stop yêu cầu và lúc inflight hoàn tất.
11. **Flow động:** đăng ký `IntegrationFlow` mới, start/stop/destroy theo ID; kiểm tra không còn subscription hoặc reply handler mồ côi.
12. **Rolling restart:** chạy hai application instances với shared broker/message store, dừng một instance rồi bật lại; đo redelivery và duplicate.
13. **Monitoring:** xây dashboard gồm running state, in/out throughput, p95 latency, queue age, error rate và DLQ depth.
14. **Runbook:** viết quy trình pause/drain/resume có điều kiện xác minh, không chỉ một thao tác stop/start.

### Câu hỏi tự kiểm tra

- Bean handler và consumer endpoint khác nhau thế nào?
- `autoStartup=false` khác việc gọi `stop()` sau khi chạy như thế nào?
- `phase` nhỏ hơn ảnh hưởng thứ tự start và stop ra sao?
- Vì sao `isRunning()=true` không chứng minh message nghiệp vụ đã commit?
- Khi stop một consumer của `DirectChannel` có nhiều subscriber, message mới có bị từ chối không?
- Với `QueueChannel` và poller, backlog sau stop nằm ở đâu?
- Vì sao một lệnh Control Bus có thể gây rủi ro bảo mật?
- Khi gửi message tới `ExecutorChannel`, tại sao sender có thể trả thành công trước handler?
- Thay poller trigger khi ứng dụng running có bảo đảm được áp ngay không?
- Stop một endpoint trong pod A có stop toàn cluster không?
- Khi nào cần registration/destroy flow mới thay vì chỉnh bean đang sống?

## 19. Checklist trước production

- Endpoint IDs/flow IDs ổn định; có sơ đồ source-channel-endpoint-handler-error path.
- Xác định component nào hỗ trợ `start/stop` và trạng thái nào có thể đọc.
- `autoStartup`/`phase` được test cùng bean dependencies; không dùng phase thay cho transaction semantics.
- Quyền Control Bus/JMX giới hạn, có audit và allowlist commands.
- Có kế hoạch drain in-flight tasks, transaction và broker ack khi stop/restart.
- Poller stop không làm backlog vượt capacity/retention; queue durability được kiểm chứng.
- Retry, recovery/error consumer và message store vẫn hoạt động theo contract khi pause source.
- Với cluster, có orchestration từng instance, không suy một local control tác động mọi pod.
- Chỉ hot-update properties qua API có contract rõ; đổi cấu trúc dùng cutover/re-registration.
- Metrics/graph/alert bao gồm health, queue depth, throughput, p95 latency và failure rate.
- Có fault injection để chứng minh không mất message hoặc side effect trùng ngoài contract.

## 20. Tài liệu tham khảo chính thức

- [Spring Integration — System Management](https://docs.spring.io/spring-integration/reference/system-management.html): quản trị component, control bus, monitoring, graph.
- [Spring Integration — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): SpEL control command và message-based management.
- [Spring Integration — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html): quản lý MBeans và các thuộc tính/operations được export.
- [Spring Integration — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): polling/event-driven consumers và endpoint lifecycle.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/polling-consumer.html): poller trigger và `maxMessagesPerPoll`.
- [Spring Integration — Java DSL Dynamic and Runtime Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): đăng ký flow động bằng `IntegrationFlowContext`.
- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html): topology và integration graph management.
- [Spring Integration Javadoc — AbstractEndpoint](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractEndpoint.html): lifecycle, startup và phase.
- [Spring Framework — Lifecycle / SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): quản lý start/stop và pha.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cấu hình exposure và security cho management endpoints.
