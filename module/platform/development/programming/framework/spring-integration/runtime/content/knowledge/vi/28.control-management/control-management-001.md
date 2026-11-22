# Control Bus và điều khiển lifecycle bằng message trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một hệ thống có thể có hàng chục IntegrationFlow, inbound adapter, gateway, poller, consumer, channel và executor. Khi bảo trì một nguồn dữ liệu hoặc khi downstream quá tải, người vận hành có thể cần **tạm dừng nhận message**, kiểm tra trạng thái endpoint và **khởi động lại có kiểm soát** mà không phải restart toàn bộ JVM.

**Control Bus** là một Enterprise Integration Pattern (EIP) trong Spring Integration cho phép đưa **thông điệp điều khiển** qua một message channel. Payload của message được xử lý như **biểu thức quản trị**; biểu thức có thể gọi phương thức trên các Spring bean, chẳng hạn phương thức **start()**, **stop()** hoặc **isRunning()** của endpoint có hỗ trợ lifecycle.

Sau bài học, bạn có thể:

- Giải thích Control Bus khác gì so với channel chuyên chở dữ liệu nghiệp vụ.
- Gửi lệnh **start/stop** và truy vấn **isRunning** cho endpoint theo tên bean rõ ràng.
- Phân biệt **Lifecycle**, **SmartLifecycle**, **endpoint**, **IntegrationFlow** và đăng ký flow động.
- Cấu hình Control Bus bằng Spring Integration XML và Java DSL, kiểm tra reply/error một cách có chủ đích.
- Hiểu tác động của điều khiển lifecycle đối với **poller, message-driven adapter, executor, transaction, retry, MessageStore và message đang xử lý dở**.
- Thiết kế đường quản trị an toàn: **không cho caller không tin cậy gửi biểu thức SpEL tùy ý**.
- Kiểm thử việc tạm dừng/khôi phục một flow, xác minh trạng thái thực tế và chuẩn bị runbook vận hành.

> **Nguyên tắc vận hành:** Control Bus giúp phát **lệnh điều khiển** tới bean/endpoint. Nó không tự cung cấp giao dịch phân tán, không tự drain queue, không chắc chắn thu hồi side effect đã diễn ra và không tự bảo đảm kết quả nghiệp vụ của các message đang in-flight.

## 1. Control plane và data plane trong message flow

Hãy phân biệt hai loại message:

| Đặc điểm | Message nghiệp vụ (data plane) | Message điều khiển (control plane) |
| --- | --- | --- |
| Ví dụ payload | OrderCreated, PaymentCommand, InventoryResult | Biểu thức start/stop/isRunning |
| Mục tiêu | Thực hiện chức năng nghiệp vụ | Thay đổi hoặc quan sát trạng thái runtime |
| Channel điển hình | ordersInput, paymentRequests | controlBus |
| Người gửi | Service, adapter, broker, gateway nghiệp vụ | Thành phần quản trị được cấp quyền |
| Hệ quả | Ghi DB, gửi event, gọi API | Bật/tắt endpoint, kiểm tra lifecycle |
| Rủi ro | Duplicate, mất message, transaction, correlation | Dừng nhầm flow, thực thi biểu thức nguy hiểm, mất kiểm soát lifecycle |

~~~mermaid
flowchart LR
    SRC["File / Broker / HTTP source"] --> IN["ordersInput"]
    IN --> POLL["Order processor"]
    POLL --> OUT["Downstream service"]

    ADMIN["Admin service (đã xác thực)"] --> CB["controlBus channel"]
    CB --> HANDLER["Control Bus endpoint"]
    HANDLER -. "start / stop / inspect" .-> SRC
~~~

Control Bus **không phải** một channel tự động chặn tất cả message nghiệp vụ. Nó là một **endpoint xử lý các lệnh**: lệnh chỉ tác động lên những bean/phương thức được biểu thức nhắm tới và những thành phần thực sự có khả năng thay đổi lifecycle.

**Trường hợp sử dụng điển hình:** Đội vận hành nhận thấy một inbound file adapter đang tạo backlog nhanh hơn khả năng xử lý của downstream. Họ dừng **nguồn phát sinh message mới**, xử lý backlog đang có, rồi khởi động lại khi hệ thống ổn định.

## 2. Cơ chế EIP của Spring Integration Control Bus

Một Control Bus nhận message, diễn giải **payload là một biểu thức Spring Expression Language (SpEL)** trong application context phù hợp, rồi gọi phương thức tương ứng.

~~~text
Admin command
  payload = "@orderInboundEndpoint.stop()"
       |
       v
MessageChannel: controlBus
       |
       v
Control Bus handler
       |
       v
SpEL: tìm bean "orderInboundEndpoint", gọi stop()
       |
       v
Lifecycle state của bean thay đổi (nếu bean hỗ trợ)
~~~

Ba biểu thức thường gặp:

~~~text
@orderInboundEndpoint.stop()
@orderInboundEndpoint.start()
@orderInboundEndpoint.isRunning()
~~~

Ký hiệu **@** trong SpEL dùng để tham chiếu Spring bean theo tên. Nếu bean name chứa dấu chấm, dấu gạch hoặc ký tự không tiện viết như identifier, có thể dùng cú pháp tên bean trong dấu nháy:

~~~text
@'orders.inbound.endpoint'.stop()
@'orders.inbound.endpoint'.isRunning()
~~~

Đây là **ví dụ biểu thức**. Bean phải **tồn tại trong cùng ApplicationContext/BeanFactory mà Control Bus truy cập được**, và phải có phương thức được gọi; nếu không, bước đánh giá biểu thức sẽ phát sinh lỗi.

### Control Bus có thể làm hơn start/stop

Về mặt kỹ thuật, SpEL có thể gọi phương thức public phù hợp trên bean mà evaluation context cho phép truy cập. Vì vậy:

- **isRunning()** thường dùng để quan sát trạng thái.
- **start()/stop()** thường dùng cho bean có Lifecycle/SmartLifecycle.
- Các setter/method quản trị khác có thể gọi được nếu được expose.

**Đây cũng là bề mặt tấn công đáng kể.** Không nên coi Control Bus như một API văn bản chung cho mọi client. Đừng chuyển nguyên payload từ HTTP request hoặc broker công khai tới channel Control Bus.

### Giá trị trả về và kết quả thực thi

Một biểu thức truy vấn như **isRunning()** có thể trả Boolean. Một lệnh như **start()/stop()** thường có return type void, do đó có thể không sinh reply có payload hữu ích. Khi muốn xác nhận trạng thái sau lệnh, hãy **truy vấn lại isRunning()** hoặc đọc bean trực tiếp qua một service quản trị, kết hợp kiểm tra các tiêu chí runtime khác.

Giá trị true của **MessageChannel.send(...)** có nghĩa message được gửi/được channel chấp nhận theo contract của channel, **không mặc định chứng minh** toàn bộ flow đã dừng/drain thành công. Điều này đặc biệt quan trọng nếu control channel sử dụng executor hoặc lệnh triển khai lifecycle bất đồng bộ.

## 3. Lifecycle trong Spring: Lifecycle, SmartLifecycle và endpoint

Các bean cần điều khiển thường hỗ trợ một trong các hợp đồng:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

**SmartLifecycle** mở rộng Lifecycle để hỗ trợ thêm ngữ nghĩa khởi động tự động và thứ tự lifecycle thông qua phase, cùng khả năng stop sử dụng callback:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    // Còn có các phương thức được cung cấp/kế thừa tùy phiên bản.
}
~~~

Trong Spring Integration, nhiều **endpoint** (ví dụ polling consumer, message-driven consumer, inbound adapter) có hỗ trợ quản lý lifecycle. Nhưng **không được suy đoán rằng mọi bean IntegrationFlow, transformer, message channel hoặc service tùy ý đều có start()/stop()**.

| Đối tượng | Điều Control Bus có thể tác động | Cần xác minh |
| --- | --- | --- |
| **Polling endpoint** | Dừng/khởi động tác vụ poll hoặc consumer thích hợp | Bean ID của endpoint, lịch poll, số message đang chạy |
| **Message-driven inbound adapter** | Dừng/khởi động tiếp nhận từ nguồn theo lifecycle của adapter | Ack/redelivery theo broker/adapter, message in-flight |
| **Event-driven consumer endpoint** | Thay đổi lifecycle nếu endpoint implementation hỗ trợ | Subscriber có bị ngắt khỏi channel không, producer có lỗi send không |
| **IntegrationFlow** | Phụ thuộc implementation/đăng ký; không mặc định mọi flow bean là một Lifecycle | Có thể cần điều khiển các endpoint cấu thành hoặc flow registration |
| **MessageChannel** | Chủ yếu định tuyến/truyền message | Không mặc định có lifecycle start/stop |
| **Executor/TaskScheduler** | Có lifecycle shutdown/management riêng | Dừng nguồn không tự hủy mọi task đã xếp hàng |
| **Ứng dụng Spring Boot** | Có lifecycle toàn application | Dừng một endpoint không phải đóng cả ApplicationContext |

**Đừng dùng sai bean name:** ID của flow, ID của endpoint, ID của channel và ID của handler có thể khác nhau. Lệnh SpEL phải tham chiếu **bean thực sự cung cấp start()/stop()**. Trong Java DSL, nên đặt **endpoint ID tường minh** để dễ điều khiển và tìm lỗi. Trong XML, đặt ID nhất quán cho adapter/endpoint cần quản trị.

### SmartLifecycle phase là gì?

Khi application context khởi động/dừng có điều phối, **phase** có thể được dùng để xác định thứ tự khởi động/dừng giữa các SmartLifecycle bean. Đây là cơ chế của Spring context lifecycle processor, **không phải một transaction cho mọi endpoint**.

Một loạt lệnh Control Bus gửi riêng lẻ **không tự động tuân theo một runbook phase toàn cục** như quy trình đóng toàn context. Nếu cần dừng nhiều endpoint theo trình tự, một service quản trị phải thực thi và quan sát từng bước.

## 4. Cấu hình bằng XML

Ví dụ XML khai báo một channel dành riêng cho lệnh và một Control Bus endpoint:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="controlBus"/>

    <int:control-bus input-channel="controlBus"/>
</beans>
~~~

Khi channel **controlBus** là channel point-to-point đồng bộ phù hợp, lệnh được xử lý trên đường gửi message. Với một Control Bus endpoint, nên tránh có nhiều subscriber khác nhau cùng nhận các lệnh có side effect mà không có chiến lược định tuyến rõ ràng.

**Đây chỉ là phần cấu hình control plane.** Flow cần điều khiển và bean ID của nó được khai báo riêng. Hệ thống thật còn phải cấu hình thành phần **admin command producer**, xác thực/ủy quyền và observability.

## 5. Java DSL: tạo một Control Bus dành riêng cho quản trị

Với Spring Integration Java DSL, có thể khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class ControlBusConfiguration {

    @Bean
    MessageChannel controlBus() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow controlBusFlow() {
        return IntegrationFlow.from("controlBus")
                .controlBus()
                .get();
    }
}
~~~

Ý nghĩa:

1. **DirectChannel** giúp lệnh chạy theo đường đồng bộ và dễ quan sát lỗi trong cùng thread gửi; việc stop/start của bean đích vẫn tuân theo implementation lifecycle của bean.
2. **controlBusFlow** tạo Control Bus consumer nhận message từ channel đã đặt tên.
3. **Tên channel** và **tên endpoint đích** là hai việc khác nhau. controlBus nhận lệnh, còn orderInboundEndpoint là một bean có lifecycle được SpEL truy cập.
4. Đây là cấu hình minh họa; application thực tế phải có **Spring Integration core/DSL dependencies**, component scan, flow nghiệp vụ và biện pháp hạn chế quyền gửi control message.

### Đặt endpoint ID tường minh

Giả sử một polling endpoint do Java DSL tạo ra. Điểm quan trọng là ID nằm trên **endpoint**, không chỉ nằm trên channel:

~~~java
// Pseudocode Java DSL minh họa ý nghĩa của endpoint ID:
IntegrationFlow.from(
        myMessageSource,
        sourceSpec -> sourceSpec
                .id("ordersPollingEndpoint")
                .poller(pollerSpec))
        .channel("ordersInput")
        .get();
~~~

Khi triển khai thật, cách dựng **MessageSource**, poller và method overload phụ thuộc vào component/phiên bản. Mục đích của ví dụ là cho thấy **ordersPollingEndpoint** phải là ID của endpoint được tạo và có lifecycle. Kiểm tra bean ID thực tế trong context trước khi gửi lệnh:

~~~text
@ordersPollingEndpoint.stop()
@ordersPollingEndpoint.start()
@ordersPollingEndpoint.isRunning()
~~~

Không đoán ID từ tên method **@Bean IntegrationFlow** hay từ tên thư mục cấu hình. Việc đặt ID rõ ràng, kiểm tra trong integration test và đưa vào runbook sẽ giảm nguy cơ dừng nhầm đối tượng.

## 6. Gửi message điều khiển bằng Java

Ứng dụng quản trị có thể gửi command đến controlBus channel bằng Spring Messaging:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class InternalControlBusSender {
    private final MessageChannel controlBus;

    InternalControlBusSender(
            @Qualifier("controlBus") MessageChannel controlBus) {
        this.controlBus = controlBus;
    }

    void stopOrdersPolling() {
        boolean sent = controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.stop()")
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Control Bus rejected stop command");
        }
    }

    void startOrdersPolling() {
        boolean sent = controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.start()")
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Control Bus rejected start command");
        }
    }
}
~~~

**Cảnh báo về ví dụ:** Lệnh ở đây là **chuỗi cố định trong code đáng tin cậy**, không ghép từ input tùy ý của người dùng. Cần xác minh endpoint bean tồn tại, nhận được lệnh và đạt trạng thái mong đợi; kết quả send không đủ để kết luận operation thành công trong mọi topology.

### Truy vấn trạng thái và reply

Một biểu thức **isRunning()** trả Boolean, khác với lệnh stop()/start() thường trả void. Trong flow request–reply phù hợp, response có thể được gửi qua **replyChannel**:

~~~java
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

MessagingTemplate template = new MessagingTemplate();
Message<?> reply = template.sendAndReceive(
        controlBus,
        MessageBuilder.withPayload(
                "@ordersPollingEndpoint.isRunning()").build());

if (reply != null) {
    Boolean running = (Boolean) reply.getPayload();
    // Sử dụng running để hiển thị trạng thái quản trị.
}
~~~

Trong ví dụ này, **controlBus** là channel đồng bộ có Control Bus consumer và bean đích có isRunning(). Nếu reply bằng null hoặc quá hạn, phải kiểm tra **timeout, replyChannel, lỗi đánh giá biểu thức và trạng thái consumer**; không diễn giải null là false.

Với code quản trị nội bộ chạy cùng ApplicationContext, một cách khác là inject bean hỗ trợ **Lifecycle** hoặc tra cứu trực tiếp qua BeanFactory rồi gọi **isRunning()**. Control Bus đặc biệt hữu ích khi cần giữ **giao diện quản trị dưới dạng message flow**, không phải bắt buộc cho mọi thao tác lifecycle trong cùng process.

## 7. Khi lệnh stop() được gửi: hệ thống thực sự dừng cái gì?

Ví dụ một inbound file adapter với polling endpoint:

~~~mermaid
flowchart LR
    FS["File directory"] --> P["ordersPollingEndpoint"]
    P --> Q["ordersInput / QueueChannel"]
    Q --> H["Order handler"]
    H --> DB[("Business DB")]
    CB["Control Bus"] -. "stop()" .-> P
~~~

Lệnh **stop()** nhắm vào polling endpoint thường dừng **các lượt poll mới** do endpoint đó khởi tạo. Nó **không tự động**:

- Xóa message đã có trong QueueChannel hoặc MessageStore.
- Rollback các DB transaction đã commit.
- Thu hồi HTTP request đã gửi tới đối tác.
- Hủy mọi tác vụ nằm sẵn trong executor queue.
- Bảo đảm các message đang xử lý dở đã hoàn thành.
- Dừng tất cả endpoint khác cùng gửi vào channel đó.

**Nếu muốn tạm dừng nhận message mới**, cần kiểm tra **tất cả inbound endpoints** đưa dữ liệu vào đường xử lý, không chỉ một adapter. Nếu một broker consumer có cơ chế ack riêng, stop có thể làm thay đổi cách giải phóng/nhận lại message in-flight theo implementation.

### Stop và drain là hai thao tác khác nhau

**Stop ingress** = không nhận thêm message mới tại một nguồn theo điều khiển lifecycle.

**Drain backlog** = đợi hoặc xử lý có kiểm soát những message đã nhận/đang nằm trong queue hoặc executor.

**Stop consumers** = dừng các endpoint đang đọc backlog.

Nếu dừng consumer trước khi drain, backlog có thể **không bao giờ giảm**. Nếu chỉ dừng ingress nhưng một producer khác vẫn gửi vào channel, backlog có thể tiếp tục tăng. Runbook cần quyết định thứ tự theo topology thực tế.

## 8. Runbook tạm dừng và tiếp tục một message flow

Giả sử một ứng dụng nhập đơn hàng có topology:

~~~text
ordersPollingEndpoint
  → ordersInput
  → QueueChannel (MessageStore)
  → orderProcessingPoller
  → orderHandler
  → JDBC / outbound broker
~~~

Mục tiêu là tạm dừng đầu vào để nâng cấp downstream, nhưng không mất các đơn đã nhận.

### Pha A — Dừng nhận mới (pause ingress)

1. Xác định **đúng endpoint ID** đại diện nguồn cần tạm dừng. Ghi cả **application instance** chứa endpoint.
2. Bảo đảm nguồn có thể dừng mà không gây mất message: xem transaction, adapter acknowledgement, remote source và message in-flight.
3. Gửi **@ordersPollingEndpoint.stop()** qua controlBus trên instance đó.
4. Truy vấn **@ordersPollingEndpoint.isRunning()**; xác minh trạng thái theo lifecycle contract.
5. Quan sát số lần poll/message mới: nguồn thật sự không tiếp tục tạo backlog ngoài dự kiến.

### Pha B — Drain backlog

1. Giữ **orderProcessingPoller** đang hoạt động để tiếp tục xử lý message đã có trong queue.
2. Theo dõi **queue depth**, số task in-flight, transaction đang chạy, retry pending và số lỗi.
3. Chờ tới tiêu chí được định nghĩa trước, ví dụ backlog về 0 **và** in-flight về 0, hoặc xử lý hết một batch/checkpoint cụ thể.
4. Nếu một message không thể hoàn thành, đưa vào cơ chế **recovery/DLQ/quarantine** đã xác định thay vì chờ vô hạn.
5. Chỉ khi đạt điều kiện mới dừng consumer phía sau nếu mục tiêu bảo trì đòi hỏi điều đó.

### Pha C — Khởi động lại

1. Kiểm tra DB, broker, message store và downstream đã sẵn sàng.
2. Khởi động các consumer và endpoint xử lý cần thiết **trước khi mở lại lượng đầu vào lớn**, nếu topology phù hợp.
3. Gửi **@ordersPollingEndpoint.start()** trên đúng instance.
4. Truy vấn trạng thái, kiểm tra các lần poll và message thực sự được xử lý.
5. Theo dõi backlog, retry rate, error channel và latency cho tới khi flow ổn định.

~~~mermaid
flowchart TD
    A["Xác minh quyền và mục tiêu"] --> S["Stop ingress"]
    S --> V{"isRunning=false?<br/>Inbound rate giảm?"}
    V -- "Không" --> ERR["Điều tra / không tiếp tục bảo trì"]
    V -- "Có" --> D["Drain queued + in-flight work"]
    D --> Q{"Backlog/in-flight đạt tiêu chí?"}
    Q -- "Không" --> R["Theo dõi retry, error, DLQ"]
    R --> D
    Q -- "Có" --> M["Bảo trì / triển khai"]
    M --> C["Start consumer nếu cần"]
    C --> U["Start ingress"]
    U --> H["Xác minh health + traffic + errors"]
~~~

**Không đặt một thời gian sleep cố định rồi mặc định backlog đã drain.** Khi có poller, executor, broker và HTTP call, một số công việc đang chạy có thể chưa nằm trong queue depth. Cần đo **in-flight** qua metrics/application state hoặc một cơ chế quiescence được thiết kế riêng.

### Một số tình huống đặc biệt

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| **File inbound adapter** | File đang được xử lý, filter/MetadataStore và việc file có được poll lại sau restart không |
| **Broker inbound adapter** | Hành vi đóng consumer, ack/nack/offset, redelivery và rebalance |
| **QueueChannel persistent** | Message còn trong store khi stop, transaction của polling consumer, khả năng resume |
| **ExecutorChannel** | Task đã được đưa vào executor nhưng chưa chạy; source đã ack hay chưa |
| **Aggregator/resequencer** | Group chưa release, group timeout, cleanup và late arrival |
| **HTTP inbound gateway** | Dừng endpoint có thể ảnh hưởng request mới thế nào; load balancer và request đang mở |
| **Outbound adapter** | Có công việc đang gửi và nhận response chưa chắc chắn; idempotency nếu phát lại |

**Không có một lệnh Control Bus phổ quát tên “drain everything safely”.** Hành động pause/resume theo message chỉ là một công cụ trong chiến lược graceful operation và recovery.

## 9. Tác động tới transaction, retry và message đang in-flight

Một lệnh start/stop thay đổi **lifecycle của endpoint**, không tự đổi semantics của transaction hiện tại.

### Poller đang chạy transaction

~~~text
Poller thread:
  begin transaction
    receive message A
    handler update DB
    ...

Admin thread:
  @ordersPollingEndpoint.stop()
~~~

Nếu lệnh stop đến khi poller đang xử lý A, kết quả cụ thể phụ thuộc implementation và thời điểm. Không được giả định stop **đã rollback transaction A** hoặc **đã chờ A commit**. Transaction sẽ theo cấu hình transaction manager/advice và quá trình xử lý thực tế.

**Tiêu chí vận hành an toàn:** Theo dõi in-flight và transaction outcome riêng; chỉ công bố “đã drain” khi các tiêu chí thực tế đạt, không chỉ nhìn isRunning=false.

### RetryAdvice và errorChannel

Giả sử handler đang retry một HTTP call với backoff. Stop một **inbound endpoint** không nhất thiết hủy các lần retry **đang diễn ra trong handler**. Nếu một endpoint bị stop trong khi retry/executor queue đang bận:

- Handler có thể hoàn thành, lỗi hoặc tiếp tục retry theo advice.
- ErrorMessage có thể được gửi vào **errorChannel** theo cơ chế endpoint, kể cả khi nguồn đã bị stop.
- Recovery callback có thể quyết định ACK/rollback theo hợp đồng nguồn; Control Bus không định nghĩa lại chính sách đó.
- Sau resume, nguồn có thể **redeliver** message chưa ack; business handler phải idempotent.

**Chống nhầm lẫn:** Một lệnh stop đã được gửi thành công không đồng nghĩa retry đã dừng hoặc tất cả lỗi đã được xử lý. Một lần start sau đó không được xem là “retry tất cả message lỗi”; retry/replay phải có logic riêng.

### Thread boundary

| Ranh giới | Điều đáng chú ý |
| --- | --- |
| **DirectChannel** | Handler chạy đồng bộ trong thread gửi; lỗi có thể truyền lại sender nếu không bị bắt |
| **ExecutorChannel** | Worker chạy thread khác; transaction/lifecycle của sender không mặc định bao trùm task đã giao |
| **QueueChannel + poller** | Consumer được điều khiển có thể dừng lấy message mới nhưng queue vẫn còn dữ liệu |
| **Broker** | Dừng container/consumer có thể làm broker giao lại message theo cấu hình ack/transaction |
| **Control Bus DirectChannel** | Lệnh điều khiển chạy theo thread gửi; code admin không nên bị kẹt bởi handler nghiệp vụ lâu |

Control channel nên tách khỏi những queue/thread pool đã bị bão hòa vì nghiệp vụ. Nếu chính controlBus phụ thuộc một executor đang hết worker, lệnh stop dùng để giảm tải **có thể cũng không được xử lý kịp**.

## 10. Điều khiển nhiều endpoint và nhiều instance

**Control Bus nội bộ chỉ nhìn thấy các bean mà ApplicationContext của nó quản lý**. Nếu một service có ba replica A, B, C, gửi lệnh dừng tới instance A **không tự động dừng** B và C.

~~~mermaid
flowchart TD
    ADM["Admin orchestration"] --> A["Replica A: controlBus"]
    ADM --> B["Replica B: controlBus"]
    ADM --> C["Replica C: controlBus"]
    A --> EA["ordersPollingEndpoint A"]
    B --> EB["ordersPollingEndpoint B"]
    C --> EC["ordersPollingEndpoint C"]
~~~

Nếu yêu cầu **tạm dừng toàn bộ hệ thống nhập đơn**, phải có cơ chế điều phối ở cấp cluster:

1. Liệt kê instance đang hoạt động và xác định mục tiêu mỗi instance.
2. Gửi lệnh đã được xác thực đến đúng instance, hoặc dùng một management mechanism phù hợp kiến trúc.
3. Thu thập trạng thái cho **từng replica**; không suy luận “cluster đã dừng” từ một response thành công.
4. Kiểm tra instance mới scale up trong lúc bảo trì có **autoStartup** và có thể bắt đầu nhận message trở lại hay không.
5. Dùng **desired state bền vững** nếu trạng thái pause phải tiếp tục có hiệu lực qua deploy/restart.

### Desired state khác actual state

~~~text
Desired state (do bộ điều phối quản trị lưu):
    order-import = PAUSED

Actual state:
    replica A: STOPPED
    replica B: STOPPED
    replica C: RUNNING  <-- chưa đạt desired state
~~~

Lệnh **stop()** qua Control Bus chỉ thay đổi trạng thái hiện tại trong process phù hợp. Khi JVM restart, các bean SmartLifecycle có **isAutoStartup()** có thể được Spring khởi động lại. Nếu yêu cầu “pause vẫn giữ sau deploy”, cần một **control/desired-state store** và logic khởi động/reconciliation có kiểm soát thay vì chỉ dựa vào trạng thái in-memory của endpoint.

### Tránh gửi cùng lệnh điều khiển nhiều lần ngoài ý muốn

Start/stop thường có ngữ nghĩa idempotent tại mức lifecycle của nhiều implementation, nhưng **đừng khái quát rằng mọi method có side effect đều idempotent**. Nếu một admin operation làm nhiều việc (ví dụ rotate credentials, trigger manual replay), cần **commandId**, dedup và audit để tránh chạy lặp do client retry.

## 11. Security: Control Bus là bề mặt đặc quyền cao

Vì payload được dùng để đánh giá **SpEL**, Control Bus **không được mở trực tiếp cho message hoặc HTTP request không tin cậy**. Một client gửi biểu thức tùy ý có thể gọi phương thức trên bean mà evaluation context cho phép, vượt xa phạm vi bật/tắt một endpoint.

### Thiết kế quyền truy cập nên theo nguyên tắc mặc định từ chối

- **Không** nối trực tiếp một inbound HTTP gateway, Kafka/JMS consumer công khai hoặc channel nhận dữ liệu nghiệp vụ với **controlBus**.
- Tạo **admin façade** với **các operation cố định**: PAUSE_ORDERS, RESUME_ORDERS, CHECK_ORDERS; không nhận chuỗi SpEL nguyên bản.
- Xác thực và kiểm tra quyền **trước** khi tạo message điều khiển; bảo vệ cả đường gọi nội bộ.
- Áp dụng **allowlist tên endpoint/bean**, không cho caller tự chọn tùy ý bean name.
- Phân quyền riêng **read-only** và **mutating commands**. Đọc isRunning ít rủi ro hơn gọi stop, nhưng không phải lúc nào cũng vô hại.
- Ghi **audit log** gồm actor thực đã xác thực, commandId, target, thời điểm, outcome; giới hạn tốc độ và chống replay khi cần.
- Không để secrets, SpEL expression hoặc dữ liệu bí mật xuất hiện trong payload/log không được kiểm soát.
- Bảo vệ network, management port và message broker transport nếu command đi qua ranh giới tiến trình.

**Các header như requestedBy hoặc role không chứng minh người gửi đã được xác thực**. Chúng chỉ là metadata trừ khi được một lớp bảo mật đáng tin cậy gắn và kiểm tra.

### Ví dụ façade với allowlist cố định

~~~java
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

enum AdminAction {
    PAUSE_ORDERS,
    RESUME_ORDERS
}

final class RestrictedAdminCommands {
    private final MessageChannel controlBus;

    RestrictedAdminCommands(
            @Qualifier("controlBus") MessageChannel controlBus) {
        this.controlBus = controlBus;
    }

    void execute(AdminAction action, Set<String> trustedAuthorities) {
        // Tập quyền này phải lấy từ security context đáng tin cậy,
        // KHÔNG lấy trực tiếp từ request body/header của người gọi.
        if (!trustedAuthorities.contains("OPERATE_ORDER_FLOW")) {
            throw new SecurityException("Not authorized");
        }

        String expression = switch (action) {
            case PAUSE_ORDERS -> "@ordersPollingEndpoint.stop()";
            case RESUME_ORDERS -> "@ordersPollingEndpoint.start()";
        };

        if (!controlBus.send(
                MessageBuilder.withPayload(expression).build())) {
            throw new IllegalStateException("Command not delivered");
        }
    }
}
~~~

Đoạn code minh họa **allowlist ở application layer**, chưa bao gồm một security filter chain hoặc cơ chế xác thực hoàn chỉnh. Nếu nhiều thành phần trong cùng JVM có thể inject trực tiếp controlBus channel, cần quản trị quyền truy cập ở cấp thiết kế/cấu hình ứng dụng; một façade đơn lẻ không tự ngăn mọi đường gọi khác.

**Không ghép biểu thức bằng string concatenation từ input**, ví dụ nhận tên bean do người dùng nhập rồi tạo lệnh. Như vậy một allowlist có thể bị vô hiệu hóa bởi parser/trick ở chuỗi đầu vào.

## 12. Lỗi lệnh điều khiển và đường khôi phục

Control Bus cũng là một message handler và có thể gặp lỗi:

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| **Bean không tồn tại** | SpEL không resolve được tên endpoint | Kiểm tra ID và context thực tế |
| **Bean không hỗ trợ lifecycle** | Không có phương thức start()/stop()/isRunning() như kỳ vọng | Nhắm đúng endpoint hoặc bọc trong một quản trị viên typed |
| **Biểu thức không hợp lệ** | Parsing/evaluation error | Chỉ cho phép các biểu thức do code đáng tin cậy tạo |
| **Control channel không có subscriber** | Send thất bại hoặc bị từ chối theo loại channel | Kiểm tra bean/controlBusFlow đã khởi động |
| **Endpoint target đang stop/start** | State tức thời thay đổi hoặc không như mong đợi | Serialize command theo target, đối chiếu actual state |
| **Thread pool của control channel bận** | Lệnh đến chậm hoặc không kịp deadline | Dùng control plane độc lập, giám sát độ trễ |
| **Target stop nhưng backlog còn** | isRunning=false, queue vẫn đầy | Thực hiện runbook drain/in-flight |
| **Service restart** | Endpoint có thể tự start trở lại | Reconcile với desired state bền vững |

**Đường lỗi phụ thuộc channel:** Với một **DirectChannel**, lỗi của Control Bus handler thường truyền lại người gọi send khi không bị intercept/handler khác bắt. Với **ExecutorChannel**, lỗi xuất hiện ở worker thread; cần error flow và cơ chế xác nhận riêng. Không nên dùng một lời gọi send thành công làm kết quả cuối cùng của operation bất đồng bộ.

### Quy tắc trả trạng thái cho người vận hành

Nên phân biệt:

~~~text
REQUESTED   = đã yêu cầu gửi lệnh
DISPATCHED  = message đã được channel nhận
APPLIED     = bean đã xử lý lệnh theo contract
VERIFIED    = trạng thái + điều kiện runtime mong muốn được xác nhận
FAILED      = lệnh thất bại, có lý do
TIMED_OUT   = chưa xác định kết quả trong deadline
~~~

Đây là **state model do ứng dụng tự định nghĩa**, không phải enum built-in của Control Bus. Nếu client timeout sau khi lệnh stop đã thực thi, nó không nên tự động gửi thêm một lệnh bất kỳ có tác dụng không idempotent; nên **đọc trạng thái thực tế trước**.

## 13. IntegrationFlow động và Control Bus

Spring Integration có cơ chế **IntegrationFlowContext** để đăng ký/quản lý IntegrationFlow động ở runtime. Điều đó khác với gửi SpEL lệnh start/stop đến một endpoint đã tồn tại:

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Dừng/tái khởi động một endpoint có lifecycle đang đăng ký | Control Bus hoặc gọi Lifecycle trực tiếp qua service quản trị |
| Truy vấn bean endpoint đang chạy không | isRunning() hoặc API lifecycle tương đương |
| Đăng ký một flow mới lúc runtime | **IntegrationFlowContext.registration(...).register()** theo API/version |
| Dừng hoặc hủy một flow đã đăng ký động | API lifecycle/registration của **IntegrationFlowContext** phù hợp |
| Thay đổi wiring của flow theo cấu hình mới | Cần kế hoạch đăng ký/unregister/replace, không chỉ gọi start() |

**Control Bus không tự tạo flow mới** và **stop() không xóa định nghĩa bean khỏi ApplicationContext**. Nếu cần thay đổi topology thay vì chỉ trạng thái chạy/dừng, hãy dùng cơ chế đăng ký flow động phù hợp, kết hợp kiểm soát ownership và cleanup.

Một operation “thay flow A bằng flow B” không phải transaction atomic: cần trình tự **ngừng ingress, drain, đăng ký/check flow mới, chuyển nguồn, xóa flow cũ**, kèm rollback plan nếu không thể hoàn tất.

## 14. Quan sát Control Bus và lifecycle trong production

Cần quan sát **cả control commands và data plane**:

| Chỉ số / log | Câu hỏi cần trả lời |
| --- | --- |
| **command_requested / verified / failed** | Lệnh nào đã được thực thi và xác minh? |
| **control command latency** | Gửi lệnh tới lúc endpoint đạt trạng thái mong muốn mất bao lâu? |
| **actual vs desired state** | Replica nào không đồng bộ trạng thái? |
| **isRunning** theo endpoint/instance | Endpoint nào còn chạy hoặc đã dừng? |
| **poll count / inbound rate** | Stop nguồn có thật sự ngăn message mới không? |
| **QueueChannel depth / store backlog** | Backlog đã được drain hay vẫn tăng? |
| **in-flight count** | Có handler, transaction, external request chưa hoàn tất? |
| **retry, errorChannel, DLQ** | Sau pause có lỗi hoặc redelivery tăng đột biến không? |
| **executor active/queue/rejection** | Task vẫn đang chạy hoặc bị reject dù nguồn đã dừng? |
| **last restart / auto startup state** | Service restart có làm endpoint tự bật lại không? |

Một log quản trị có cấu trúc:

~~~text
commandId=ops-20261122-17
operation=PAUSE_ORDERS
targetBean=ordersPollingEndpoint
instance=orders-service-pod-b
actor=operations-team
requestedAt=2026-11-22T02:10:00Z
commandOutcome=APPLIED
actualRunning=false
queueDepth=184
inFlight=7
drained=false
~~~

Log này minh họa rằng **endpoint đã stop nhưng backlog/in-flight vẫn còn**. Đừng báo “flow đã hoàn tất shutdown an toàn” khi chỉ có **actualRunning=false**.

**Spring Integration management/Actuator/JMX/metrics** có thể hỗ trợ quan sát tùy các module và cấu hình đã bật. Control Bus chuyên thực thi lệnh; nó **không tự tạo dashboard đầy đủ**, và một câu truy vấn isRunning đơn lẻ không thay thế tracing, error monitoring hay metrics.

## 15. Unit và integration test cho Control Bus lifecycle

Trước khi dùng command trong production, hãy kiểm thử **Control Bus thật sự nhận biểu thức**, gọi đúng bean và trả kết quả theo lifecycle contract. Test đơn giản có thể dùng một bean giả lập Lifecycle thay vì khởi động broker/DB.

### Test với Spring context và một Lifecycle bean

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        ControlBusConfiguration.class,
        ControlBusLifecycleTest.EndpointFixture.class
})
class ControlBusLifecycleTest {

    @Autowired
    @Qualifier("controlBus")
    MessageChannel controlBus;

    @Autowired
    @Qualifier("ordersPollingEndpoint")
    Lifecycle endpoint;

    @Test
    void commandsChangeLifecycleOfNamedBean() {
        assertTrue(controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.start()")
                        .build()));
        assertTrue(endpoint.isRunning());

        assertTrue(controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.stop()")
                        .build()));
        assertFalse(endpoint.isRunning());
    }

    @Configuration
    static class EndpointFixture {
        @Bean("ordersPollingEndpoint")
        Lifecycle endpoint() {
            return new Lifecycle() {
                private volatile boolean running;

                @Override
                public void start() {
                    running = true;
                }

                @Override
                public void stop() {
                    running = false;
                }

                @Override
                public boolean isRunning() {
                    return running;
                }
            };
        }
    }
}
~~~

**Điều test này chứng minh:** Biểu thức SpEL tìm được bean có ID tường minh; Control Bus trên DirectChannel gọi được start/stop; trạng thái bean thay đổi. Nó **chưa chứng minh** hành vi của một file/JMS/Kafka adapter, sự an toàn với transaction hoặc việc drain executor queue.

**Chú ý khi chạy cùng project:** Bean ControlBusConfiguration ở phần trước phải được biên dịch, Spring Integration libraries phải hiện diện, test dependency JUnit 5/Spring Test được cấu hình. Tên class/package và cách khởi tạo context cần điều chỉnh theo dự án thật.

### Test truy vấn trạng thái

Sử dụng **MessagingTemplate** với biểu thức trả kết quả:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

MessagingTemplate template = new MessagingTemplate();

Message<?> reply = template.sendAndReceive(
        controlBus,
        MessageBuilder.withPayload(
                "@ordersPollingEndpoint.isRunning()").build());

assertNotNull(reply);
assertEquals(Boolean.FALSE, reply.getPayload());
~~~

Đây là **fragment chạy trong cùng fixture sau khi endpoint đã stop**. Với Control Bus handler đồng bộ trả Boolean và reply channel được wiring đúng, kết quả mong đợi là false. Với lệnh stop() trả void, **đừng viết test yêu cầu có reply Boolean**: thay vào đó truy vấn riêng isRunning() hoặc bean state.

### Test lỗi bean không tồn tại

~~~java
assertThrows(RuntimeException.class, () ->
        controlBus.send(
                MessageBuilder.withPayload(
                        "@endpointDoesNotExist.stop()").build()));
~~~

Đây là ví dụ cho **đường đồng bộ**: một số failure có thể bị bọc trong MessagingException/MessageHandlingException hoặc một exception SpEL khác. Không nên buộc test phụ thuộc chính xác vào một lớp exception nội bộ nếu mục đích là chứng minh **lỗi không bị bỏ qua**.

## 16. Integration test với endpoint thật: pause, drain, resume

Sau test Lifecycle stub, phải kiểm tra **inbound adapter hoặc polling endpoint thật**:

1. Tạo một source kiểm thử có thể đo số lần **receive()/poll()**.
2. Tạo endpoint với **ID cố định**, channel output kiểm thử và consumer có bộ đếm.
3. Khởi động context; đợi chứng cứ poller thực sự chạy bằng **CountDownLatch, Awaitility hoặc điều kiện có deadline**, tránh sleep tùy tiện.
4. Gửi stop command qua controlBus và xác minh **isRunning=false**.
5. Cung cấp thêm dữ liệu đầu vào; xác minh source không được poll tiếp **sau khi việc stop hoàn tất** theo semantics của endpoint.
6. Nếu có **QueueChannel**, kiểm tra message đã nằm trong queue trước stop **không tự biến mất**.
7. Gửi start command; xác minh polling tiếp tục và message còn chờ được xử lý.
8. Đóng context sạch sẽ; xác minh không còn thread/task/resource leak.

Nếu polling đã bắt đầu trước khi lệnh stop tới, một lượt xử lý in-flight có thể vẫn hoàn tất. Test không nên cấm mọi output xuất hiện **ngay sau thời điểm gửi stop** mà không phân biệt lượt poll đang chạy và lượt poll mới.

### Ma trận test runtime cần có

| Ca kiểm thử | Điều kiện thử | Assertion quan trọng |
| --- | --- | --- |
| **Command hợp lệ** | Gửi start/stop cho endpoint có lifecycle | Trạng thái đúng, target đúng |
| **Truy vấn** | Gửi isRunning() | Có reply Boolean phù hợp khi flow request–reply được cấu hình |
| **Sai bean ID** | Gửi lệnh tới bean không tồn tại | Có lỗi, không biến thành trạng thái thành công |
| **Bean không Lifecycle** | Gửi stop tới channel bean | Lỗi được quan sát, không điều khiển nhầm |
| **Pause khi idle** | Không có message in-flight | Nguồn dừng poll/receive mới |
| **Pause khi handler đang chạy** | Giữ một message in-flight bằng latch | Không mặc định hủy/rollback message đang xử lý |
| **Backlog còn trong QueueChannel** | Queue có message trước stop ingress | Message vẫn theo chính sách store; drain có kiểm chứng |
| **Resume** | Start lại endpoint sau pause | Source tiếp tục poll, không nhân đôi xử lý nghiệp vụ |
| **Async worker lỗi** | ExecutorChannel có task thất bại sau pause | ErrorMessage/transaction/retry có thể truy vết |
| **Restart JVM** | Stop endpoint rồi restart process | Kiểm tra autoStartup, desired state và input mới |
| **Nhiều replica** | Chỉ stop instance A | B và C không được mặc định coi là stopped |
| **Unauthorized request** | Caller không đủ quyền yêu cầu PAUSE | Façade từ chối, controlBus không nhận biểu thức |
| **Command timeout** | Lệnh đã dispatch nhưng chưa xác minh | Không trả success giả; đọc lại actual state |

### Test lỗi và recovery

Điều khiển lifecycle tác động tới nhịp nhận message nên cần kết hợp:

- **Transaction test:** Stop giữa lúc xử lý DB; chứng minh commit/rollback theo ranh giới thực tế, không do giả định.
- **Retry test:** Source stop nhưng handler đang retry; xác minh retry có budget và error flow không mất message.
- **Redelivery test:** Sau restart, message chưa ack có thể được giao lại; idempotency key ngăn side effect trùng.
- **MessageStore test:** Queue/group persistent giữ state sau stop/start hoặc restart theo hợp đồng store.
- **Cluster coordination test:** Gửi pause tới mọi replica, quan sát actual state từng node và tình huống một node mới gia nhập.

Đừng kết luận **flow đã pause toàn diện** từ unit test gọi Lifecycle stub. Nó chỉ xác minh cơ chế gọi lệnh; xác minh vận hành phải quan sát **end-to-end data plane**.

## 17. Những anti-pattern nên tránh

### Anti-pattern 1: dùng Control Bus như endpoint HTTP chạy SpEL tùy ý

~~~text
POST /admin/execute
body = "<biểu thức do client cung cấp>"
  → controlBus
~~~

Đây là thiết kế có nguy cơ **thực thi biểu thức tùy ý trên bean ứng dụng**. Hướng thay thế: các operation typed, allowlist rõ ràng, authn/authz, audit và quản lý network.

### Anti-pattern 2: dừng consumer trước, kỳ vọng queue tự drain

~~~text
stop(orderProcessingPoller)
wait(queue.size == 0)
~~~

Nếu poller là consumer duy nhất, queue không có ai xử lý để giảm kích thước. Cần dừng **ingress trước**, để consumer tiếp tục drain rồi mới dừng consumer khi đạt tiêu chí.

### Anti-pattern 3: coi isRunning=false đồng nghĩa không còn in-flight

Một task đã gửi sang executor hoặc một DB transaction đang xử lý vẫn có thể còn chạy. Cần đo queue, in-flight và transaction thay vì chỉ dựa trên cờ lifecycle.

### Anti-pattern 4: gửi stop vào một replica rồi báo toàn cluster đã pause

Mỗi replica có ApplicationContext riêng. Nếu chỉ stop A, B và C có thể vẫn xử lý message. Cần management orchestration theo instance và reconcile desired state.

### Anti-pattern 5: stop rồi để autoStartup bật lại sau restart

Lệnh Control Bus không phải durable desired state. Nếu cần giữ pause qua deploy, lưu trạng thái quản trị bên ngoài process và áp dụng lại khi instance gia nhập.

### Anti-pattern 6: gửi control command trong chính đường đang bị nghẽn

Nếu controlBus dùng cùng queue/executor đang bị saturate, lệnh giảm tải có thể bị kẹt. Tách control plane hoặc dự phòng một đường quản trị có giới hạn và được bảo mật.

### Anti-pattern 7: tự động retry mọi lệnh quản trị mà không kiểm tra state

Khi client timeout, lệnh đầu có thể **đã chạy**. Với start/stop thường có thể đọc trạng thái để đối chiếu; với operation khác có side effect, cần commandId/idempotency hoặc cơ chế nhận kết quả bền vững.

## 18. Bài thực hành: bảo trì flow nhập đơn không mất message

**Đề bài:** Một service Spring Integration có:

~~~text
FTP/File inbound poller (ordersPollingEndpoint)
   → QueueChannel backed by persistent MessageStore
   → orderProcessingPoller
   → service activator
   → DB transaction
   → outbound event
~~~

Ứng dụng có **hai replica**, đang bị backlog do DB tạm chậm. Cần tạm dừng nguồn trong lúc nâng DB, không làm mất message đã nhận và mở lại an toàn.

### Yêu cầu

- Admin chỉ được gửi **PAUSE_ORDERS, RESUME_ORDERS, QUERY_STATUS**; không nhận raw SpEL.
- Phải xác minh **cả hai replica** đã dừng ingress, kể cả một replica khởi động lại trong thời gian bảo trì.
- Các message đã có trong persistent MessageStore vẫn được xử lý hoặc lưu để tiếp tục sau bảo trì.
- Không ACK/đánh dấu success đối với DB transaction thất bại chỉ vì endpoint bị stop.
- Event outbound không được phát hai lần về mặt nghiệp vụ nếu message bị redelivery khi restart.
- Có cách nhận ra pause command **đã thực thi nhưng chưa drain**.

### Hướng giải

1. **Định danh endpoint:** Khai báo ordersPollingEndpoint và orderProcessingPoller với ID tường minh; kiểm tra bean hỗ trợ Lifecycle.
2. **Control channel:** Tạo DirectChannel riêng và Control Bus consumer nội bộ; chỉ admin façade được quyền gửi lệnh hợp lệ.
3. **Cluster control:** Lưu desired state PAUSED; phát lệnh tới từng replica và xác minh actual state.
4. **Ngăn nhận thêm:** Stop ordersPollingEndpoint trên cả hai replica; theo dõi inbound count và số message mới vào queue.
5. **Drain:** Để orderProcessingPoller chạy; giám sát queue depth + in-flight + transactions; đặt deadline và recovery cho message lỗi.
6. **Bảo trì:** Chỉ tiến hành khi đạt tiêu chí; nếu không drain hết, ghi rõ message đang pending trong persistent store.
7. **Khôi phục:** Bật consumer trước, kiểm tra DB/broker; start ingress theo desired state RUNNING; quan sát throughput.
8. **Chống trùng:** Handler dùng eventId/idempotency key và transaction/outbox phù hợp vì redelivery có thể xảy ra sau crash.
9. **Kiểm thử:** Pause khi có một transaction đang xử lý, stop một replica, restart replica khi desired state PAUSED, rồi resume trên cả hai.

### Câu hỏi tự kiểm tra

**Câu 1:** Gửi payload **@ordersPollingEndpoint.stop()** vào controlBus và send trả true. Có chắc tất cả message nghiệp vụ đã được xử lý hết?

**Không.** Kết quả gửi control message và trạng thái running không thay thế việc đo queue depth, in-flight và transaction. Stop ingress không tự drain mọi backlog.

**Câu 2:** Trong application có hai replica, một lệnh stop gửi tới controlBus của replica A có dừng luôn replica B?

**Không.** Control Bus ở A quản lý beans trong context của A. Cần điều phối toàn cluster hoặc quản lý nguồn chung bằng cơ chế khác được thiết kế rõ.

**Câu 3:** Có nên cho admin HTTP endpoint nhận nguyên chuỗi SpEL để “linh hoạt” hơn không?

**Không.** Đây là đường thực thi phương thức trên Spring beans có đặc quyền cao. Cần operation allowlist typed, xác thực/ủy quyền, audit và giới hạn quyền.

**Câu 4:** Sau khi stop endpoint, ứng dụng restart và poller tự chạy trở lại. Đó có phải Control Bus không hoạt động?

**Không.** Lệnh stop thường thay đổi state runtime; cơ chế autoStartup của lifecycle khi tạo ApplicationContext mới là vấn đề riêng. Muốn giữ pause qua restart phải quản lý desired state bền vững.

**Câu 5:** Vì sao không được dùng một kênh Control Bus bất đồng bộ bận cùng executor với data plane cho lệnh emergency stop?

**Vì** command có thể chờ sau các task nghiệp vụ đang kẹt, làm mục tiêu giảm tải không đạt kịp thời. Nên có control plane được cách ly và có chiến lược kiểm tra kết quả.

## 19. Checklist trước khi đưa vào production

- Control Bus channel đã được **tách khỏi đầu vào nghiệp vụ** và giới hạn người gửi chưa?
- Mọi operation đã đi qua **allowlist + authentication + authorization + audit**?
- Tên bean/endpoint target có **ID tường minh, đúng ApplicationContext** không?
- Target có thực sự cung cấp **Lifecycle/SmartLifecycle** và semantics start/stop mong đợi?
- Có phân biệt send accepted, command applied và **actual state verified**?
- Có cấu hình reply cho isRunning() và xử lý trường hợp null/timeout?
- Không giả định stop() đã **drain queue, hủy task, rollback DB hoặc thu hồi external side effect**?
- Có runbook dừng **ingress trước**, drain backlog, rồi dừng consumer theo topology?
- Đã tính **QueueChannel/MessageStore, executor in-flight, poller backlog, retry và errorChannel**?
- Có kiểm tra broker acknowledgement/redelivery theo adapter khi stop/start và restart?
- Có tránh retry lồng và giữ idempotency key ổn định khi message được xử lý lại?
- Với nhiều replica, có **per-instance control + desired state reconciliation**?
- Có cách giữ trạng thái PAUSED qua application restart, không bị autoStartup vô tình mở lại?
- Lệnh quản trị có deadline, commandId, audit outcome và cơ chế đọc lại actual state?
- Control plane có đường thực thi tách khỏi executor đang có nguy cơ quá tải?
- Có test lifecycle đơn vị, test polling thật, async in-flight, restart, multi-instance và quyền truy cập?

## Kết luận

**Control Bus** là cách dùng **message** để gửi biểu thức quản trị tới Spring beans trong một application context, đặc biệt hữu ích để **start/stop** các endpoint và quan sát **isRunning**. Nó giúp hệ thống Spring Integration có một control plane thống nhất với mô hình message-driven.

Tuy nhiên, **lifecycle không phải kết quả nghiệp vụ**: một nguồn đã stop vẫn có thể còn message trong queue, task trong executor, transaction đang xử lý và retry pending. Khi vận hành cần kết hợp **quy trình pause–drain–resume**, xác minh trạng thái thật, error handling, persistence, idempotency và điều phối nhiều instance.

Vì Control Bus có khả năng đánh giá **SpEL** lên Spring beans, phải xem nó là **giao diện đặc quyền cao**. Một thiết kế phù hợp production cần **operation allowlist**, bảo vệ đường gửi command, audit và kiểm thử các tình huống lỗi, không chỉ là gửi được chuỗi start()/stop().

## Tài liệu tham khảo

- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Framework API — Lifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/Lifecycle.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
