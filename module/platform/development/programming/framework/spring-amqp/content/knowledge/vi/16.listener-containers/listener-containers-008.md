# Nhận từ nhiều queue và phân bổ consumer giữa các queue

Trong **Spring AMQP**, một ứng dụng không nhất thiết chỉ nhận message từ một queue. Ví dụ, dịch vụ xử lý đơn hàng có thể cần nghe đồng thời **orders.priority** (việc cần phản hồi nhanh) và **orders.normal** (việc thông thường). Cả hai đều được RabbitMQ định tuyến qua **exchange, binding**, rồi một hoặc nhiều listener container gọi **@RabbitListener** để xử lý.

Vấn đề quan trọng không phải chỉ là khai báo hai tên queue, mà là **số consumer được tạo cho mỗi queue, cách chúng chia sẻ luồng xử lý và cách cấp năng lực khi hai queue có tải khác nhau**. Điều này phụ thuộc loại listener container:

- **SimpleMessageListenerContainer (SMLC):** một consumer worker có thể subscribe nhiều queue; số worker được cấu hình bằng **concurrentConsumers**, **maxConcurrentConsumers** hoặc thuộc tính **concurrency**.
- **DirectMessageListenerContainer (DMLC):** tạo consumer **riêng cho từng queue**; số consumer trên **mỗi queue** được cấu hình bằng **consumersPerQueue**.

Đây là bài học thuộc chương **Listener container** của module **SPRING_AMQP**: học tích hợp RabbitMQ bằng **RabbitTemplate**, **@RabbitListener**, exchange/queue/binding, đồng thời xem xét ACK, retry, dead-letter, giao dịch và giám sát để xây xử lý bất đồng bộ đáng tin cậy.

Sau bài học, bạn có thể:

1. Cấu hình **một @RabbitListener nghe nhiều queue** và xác định message xuất phát từ queue nào.
2. Phân biệt chính xác **SMLC concurrency** với **DMLC consumersPerQueue**.
3. Ước lượng số consumer/subscription, channel và mức song song cho một hay nhiều instance.
4. Chọn **một listener chung** hay **nhiều listener riêng** khi mỗi queue cần mức ưu tiên/tài nguyên khác nhau.
5. Tinh chỉnh **prefetch, ACK, retry**, thêm/bớt queue lúc chạy và quan sát backlog/consumer count.

## 1. Nhiều queue nghĩa là gì trong RabbitMQ?

Một producer gửi message tới **exchange**, không trực tiếp “gửi cho listener”. Exchange dùng **binding** cùng **routing key** để chọn queue nhận message. Listener container đăng ký consumer ở một hay nhiều queue tương ứng.

~~~mermaid
flowchart LR
    P["Publisher / RabbitTemplate"] --> E{"Direct exchange<br/>lab.orders.events"}
    E -->|"order.priority"| Q1[("lab.orders.priority")]
    E -->|"order.normal"| Q2[("lab.orders.normal")]
    Q1 --> LC["Một listener container<br/>theo dõi cả hai queue"]
    Q2 --> LC
    LC --> H["@RabbitListener<br/>xử lý message"]
~~~

Trong mô hình này:

1. Message với key **order.priority** đến queue priority.
2. Message với key **order.normal** đến queue normal.
3. Cùng một phương thức listener có thể nhận delivery của **cả hai queue**.
4. Mỗi message vẫn thuộc về **một queue cụ thể**, với vòng đời Ready/Unacked/ACK riêng.
5. Nếu một event được route tới **hai queue**, mỗi queue giữ bản message độc lập; hai consumer của hai queue có thể xử lý cùng event cho hai mục đích khác nhau.

**Điểm phải nhớ:** listener nghe hai queue **không có nghĩa RabbitMQ tự chia đều message giữa hai queue**. Việc message đi vào queue nào do **exchange và binding** quyết định. Container chỉ quyết định consumer nào nhận và xử lý message **đã nằm trong queue**.

### Hai cấu hình có ý nghĩa khác nhau

| Topology | Ý nghĩa |
| --- | --- |
| **Một queue, nhiều consumer** | Các consumer **cạnh tranh** nhận các message của cùng queue để chia tải |
| **Hai queue, một listener chung** | Một handler nhận message từ cả hai queue; mỗi queue vẫn có consumer subscription của container |
| **Hai queue, hai listener riêng** | Mỗi queue có container/handler riêng; có thể đặt concurrency, retry, ACK và executor khác nhau |
| **Một fanout exchange, hai queue** | Cùng sự kiện được sao chép vào hai queue; các consumer xử lý độc lập |
| **Hai queue có Single Active Consumer** | Mỗi queue có **một active consumer riêng**; các consumer còn lại của từng queue chờ |

## 2. Phân biệt Simple và Direct trước khi đặt concurrency

Spring AMQP có hai kiểu container phổ biến cho RabbitMQ AMQP 0-9-1.

### 2.1. SimpleMessageListenerContainer (SMLC)

SMLC sử dụng một **hàng đợi nội bộ** để chuyển delivery từ RabbitMQ Java client sang những **consumer worker thread** của Spring. Một worker có thể đăng ký nhận message từ **tất cả queue** được cấu hình trên container; nó dùng một channel cho tập queue đó.

~~~mermaid
flowchart TD
    Q1[("orders.priority")] --> C1["SMLC consumer 1<br/>subscribe cả 2 queue"]
    Q2[("orders.normal")] --> C1
    Q1 --> C2["SMLC consumer 2<br/>subscribe cả 2 queue"]
    Q2 --> C2
    C1 --> H["Cùng một handler"]
    C2 --> H
~~~

Điều chỉnh SMLC bằng **concurrentConsumers** và **maxConcurrentConsumers**. Khi tải tăng, SMLC có thể tăng số worker tới mức tối đa theo các ngưỡng hoạt động và thời gian; khi idle có thể giảm trở lại. Đây là **co giãn tổng thể của container**, không phải phân bổ chủ động “4 consumer riêng cho priority, 1 consumer riêng cho normal”.

### 2.2. DirectMessageListenerContainer (DMLC)

DMLC gọi listener theo mô hình dùng thread của RabbitMQ Java client, không cần queue trung gian như SMLC. Mỗi queue có những consumer riêng; số lượng được điều chỉnh bằng **consumersPerQueue**.

~~~mermaid
flowchart TD
    Q1[("orders.priority")] --> P1["Priority consumer 1"]
    Q1 --> P2["Priority consumer 2"]
    Q2[("orders.normal")] --> N1["Normal consumer 1"]
    Q2 --> N2["Normal consumer 2"]
    P1 --> H["Cùng một handler"]
    P2 --> H
    N1 --> H
    N2 --> H
~~~

Ví dụ **consumersPerQueue=2** với hai queue tạo **hai consumer trên mỗi queue**, tổng cộng **bốn consumer**. Mỗi consumer DMLC dùng channel riêng. DMLC **không có auto-scaling min/max** giống SMLC; có thể đổi consumersPerQueue theo API hoặc tách nhiều container nếu muốn cấp mức khác nhau.

### 2.3. Bảng so sánh quan trọng

| Tiêu chí | SMLC | DMLC |
| --- | --- | --- |
| Đơn vị concurrency | Số worker của **toàn container** | Số consumer **trên từng queue** |
| Cấu hình chính | concurrentConsumers, maxConcurrentConsumers | consumersPerQueue |
| Ví dụ @RabbitListener concurrency | **"2"** hoặc **"2-4"** | **"2"**; không dùng khoảng "2-4" |
| Một consumer và nhiều queue | Một worker nhận delivery từ các queue được cấu hình | Một consumer gắn **một queue** |
| Channel | Một channel trên worker dù nghe nhiều queue | Mỗi consumer của một queue dùng channel riêng |
| Dispatch xử lý | Qua hàng đợi nội bộ đến worker Spring | Trực tiếp từ thread của RabbitMQ client |
| Tăng/giảm tự động theo tải | Có thể, nếu cấu hình max và trigger | Không theo kiểu min/max; điều chỉnh consumersPerQueue |
| Thêm/xóa queue lúc chạy | Có thể phải hủy/tạo lại **mọi consumer** sau khi xử lý prefetched messages | Thêm/hủy consumer cho queue thay đổi mà ít ảnh hưởng queue khác |
| batchSize và consumerBatchEnabled của SMLC | Có | Không có cùng tính năng; DMLC có messagesPerAck riêng |

**Không có loại nào luôn tốt hơn.** Chọn theo nhu cầu quản lý concurrency, số queue, khả năng thay đổi topology khi chạy, batching, latency và cách giám sát.

## 3. Ví dụ số lượng consumer: tính đúng trước khi scale

Giả sử **một instance** nghe **3 queue**: Q1, Q2, Q3.

| Cấu hình | Worker/consumer ở ứng dụng | Subscription trên mỗi queue | Tổng subscription trên broker | Channel điển hình |
| --- | --- | --- | --- | --- |
| SMLC concurrency = 1 | 1 worker | 1 | 3 | 1 channel cho worker |
| SMLC concurrency = 2 | 2 worker | 2 | 6 | 2 channel cho 2 worker |
| SMLC concurrency = 2-4 | 2–4 worker tùy tải | 2–4 | 6–12 | 2–4 channel |
| DMLC consumersPerQueue = 1 | 3 consumer riêng | 1 | 3 | 3 channel |
| DMLC consumersPerQueue = 2 | 6 consumer riêng | 2 | 6 | 6 channel |

*Những con số trên giả định tất cả queue tồn tại, container đã start, subscription thành công và không có instance khác.*

**Vì sao cùng thấy “6 consumer” trên broker mà tải có thể khác?** Với SMLC concurrency=2, có **hai worker** xử lý delivery từ cả ba queue, trong khi DMLC consumersPerQueue=2 có **sáu consumer riêng theo queue** và sử dụng tập thread RabbitMQ client. Không thể suy luận số thread xử lý thực từ mỗi con số **Consumers** trên Management UI.

Nếu triển khai **3 replica** của cùng ứng dụng, số subscription thường **nhân theo số replica**. Ví dụ DMLC 2 consumer/queue × 3 queue × 3 replica = **18 subscription** toàn hệ thống, còn mỗi queue có **6 consumer** đang đăng ký. Con số cuối còn phụ thuộc pod đã kết nối, lỗi queue, rebalancing hoặc SAC.

### Concurrency không phải thứ tự ưu tiên

Cấu hình nhiều consumer **không đảm bảo** message trong queue priority được xử lý trước message trong normal. Hai queue không chia sẻ một trật tự FIFO toàn cục; broker giao delivery dựa trên subscription và prefetch, còn thời gian hoàn tất phụ thuộc tác vụ thực tế. Nếu priority là yêu cầu SLA, cần thiết kế xử lý ưu tiên bằng **tài nguyên tách biệt**, scheduling hoặc queue topology phù hợp, chứ không dựa duy nhất vào tên queue.

## 4. Chuẩn bị project và topology hai queue

Các ví dụ dưới đây chọn **Java 17 + Spring Boot 3.x + Spring AMQP 3.x**, RabbitMQ AMQP 0-9-1 và tài khoản lab. Trong Spring Boot 3.x, dependency Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

**Chú ý theo phiên bản:** Spring Boot 4.x có tổ chức starter RabbitMQ mới, ví dụ **spring-boot-starter-rabbitmq** cho AMQP 0-9-1. Các API listener container cần được đối chiếu với đúng Spring AMQP/Boot mà dự án sử dụng; đoạn cấu hình này chủ đích dành cho Boot 3.x.

Cấu hình kết nối local trong **application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
~~~

Tài khoản và mật khẩu chỉ để minh họa lab; phải có user/vhost tương ứng trên broker. Production nên lấy secrets từ cấu hình bảo mật riêng.

### 4.1. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class MultiQueueTopology {
    public static final String EXCHANGE = "lab.orders.events";
    public static final String PRIORITY_QUEUE = "lab.orders.priority";
    public static final String NORMAL_QUEUE = "lab.orders.normal";
    public static final String PRIORITY_KEY = "order.priority";
    public static final String NORMAL_KEY = "order.normal";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue priorityQueue() {
        return QueueBuilder.durable(PRIORITY_QUEUE).build();
    }

    @Bean
    Queue normalQueue() {
        return QueueBuilder.durable(NORMAL_QUEUE).build();
    }

    @Bean
    Binding priorityBinding(
            @Qualifier("priorityQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(PRIORITY_KEY);
    }

    @Bean
    Binding normalBinding(
            @Qualifier("normalQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(NORMAL_KEY);
    }
}
~~~

Các bean trên mô tả topology. Khi có **RabbitAdmin** hoạt động và quyền RabbitMQ phù hợp, Spring AMQP thường tự khai báo exchange/queue/binding lúc kết nối cần thiết được mở. Kiểm tra **RabbitMQ Management → Exchanges, Queues, Bindings** trước khi thử; việc khai báo bean Java không bảo đảm broker đã có tài nguyên.

### 4.2. Publisher gửi vào đúng queue thông qua routing key

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class MultiQueuePublisher {
    private final RabbitTemplate rabbitTemplate;

    public MultiQueuePublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendPriority(String orderId) {
        rabbitTemplate.convertAndSend(
                MultiQueueTopology.EXCHANGE,
                MultiQueueTopology.PRIORITY_KEY,
                "priority:" + orderId
        );
    }

    public void sendNormal(String orderId) {
        rabbitTemplate.convertAndSend(
                MultiQueueTopology.EXCHANGE,
                MultiQueueTopology.NORMAL_KEY,
                "normal:" + orderId
        );
    }
}
~~~

Đây là **hai routing key**, không phải hai ConnectionFactory hay hai RabbitTemplate. Exchange đưa mỗi message đến queue phù hợp theo binding. Để giữ mục tiêu bài học, ta dùng String payload; khi chuyển sang JSON DTO, cần cấu hình **MessageConverter** và schema tương ứng.

## 5. Một @RabbitListener nhận từ nhiều queue

Spring AMQP cho phép khai báo **mảng queue name** trong annotation **@RabbitListener**:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class MultiQueueOrderListener {

    @RabbitListener(
            id = "multiQueueOrders",
            queues = {
                    MultiQueueTopology.PRIORITY_QUEUE,
                    MultiQueueTopology.NORMAL_QUEUE
            })
    public void handle(
            @Payload String payload,
            @Header(AmqpHeaders.CONSUMER_QUEUE) String queue) {

        System.out.printf("[queue=%s] %s%n", queue, payload);
    }
}
~~~

**Ý nghĩa:**

- Framework tạo **một listener endpoint/container** cho phương thức này.
- Container đăng ký consumer trên **hai queue** theo cách của SMLC hoặc DMLC.
- **AmqpHeaders.CONSUMER_QUEUE** cho biết delivery đến từ queue nào.
- Body được chuyển thành String theo **MessageConverter** đã cấu hình.
- Nếu container ở chế độ **AUTO acknowledge**, nó ACK khi handler kết thúc thành công; lỗi xử lý theo chính sách container.

Bạn cũng có thể nhận raw **MessageProperties**:

~~~java
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = {
    MultiQueueTopology.PRIORITY_QUEUE,
    MultiQueueTopology.NORMAL_QUEUE
})
public void inspect(String payload, MessageProperties properties) {
    System.out.println("queue=" + properties.getConsumerQueue());
    System.out.println("routingKey=" + properties.getReceivedRoutingKey());
    System.out.println("payload=" + payload);
}
~~~

Đây là **cách thay thế** cho listener trước, không nên chạy cả hai cùng subscribe cùng hai queue chỉ để quan sát: chúng trở thành competing consumers, nên mỗi method chỉ nhận **một phần** message.

### Phân nhánh theo queue mà không dựa vào content

~~~java
if (MultiQueueTopology.PRIORITY_QUEUE.equals(queue)) {
    // Áp dụng policy xử lý priority.
} else if (MultiQueueTopology.NORMAL_QUEUE.equals(queue)) {
    // Áp dụng policy xử lý normal.
} else {
    throw new IllegalArgumentException("Unknown source queue: " + queue);
}
~~~

Đoạn trên nằm **trong method handle**, dùng biến queue đã nhận bằng **@Header**. Không nên kiểm tra payload bằng tiền tố **priority:** để đoán queue khi broker đã cung cấp metadata queue đáng tin ở phía nhận. Tuy nhiên, queue name cũng **không phải cơ chế xác thực tenant hay phân quyền nghiệp vụ**; vẫn cần validate message và quyền ứng dụng.

### Cùng một method, không có thứ tự toàn cục

Nếu queue priority chứa P1, P2 và queue normal chứa N1, N2, container có thể xử lý xen kẽ:

~~~text
priority.queue: P1 -> P2
normal.queue:   N1 -> N2

Một trong nhiều lịch xử lý có thể:
P1, N1, N2, P2
~~~

Không có cam kết rằng P1/P2 đều được xử lý trước N1/N2, hoặc các tác vụ nghiệp vụ hoàn tất theo thứ tự chỉ vì listener nhận các queue qua cùng một annotation. Khi có nhiều consumer và prefetch lớn, thứ tự hoàn tất càng có thể khác thứ tự broker giao message.

## 6. Phương án A: SimpleMessageListenerContainer

Nếu ứng dụng cần một tập worker xử lý message từ nhiều queue và muốn SMLC co giãn min/max, cấu hình **application.yml** trên Spring Boot 3.x:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        concurrency: 2
        max-concurrency: 4
        prefetch: 5
        acknowledge-mode: auto
~~~

Với listener ở phần 5, SMLC khởi tạo khoảng **2 worker**, mỗi worker đăng ký nhận trên **hai queue**. Nếu tải kéo dài và đáp ứng điều kiện scaling của container, số worker có thể tăng tới **4** rồi giảm dần khi idle.

**Phân biệt rõ:**

- **concurrency=2** không có nghĩa priority được 1 worker, normal được 1 worker.
- Cũng **không phải** “priority có 2 worker và normal có thêm 2 worker độc lập”.
- Mỗi worker SMLC có thể nhận delivery của **cả hai queue**. Do đó tải của queue priority có thể chiếm đáng kể thời gian các worker, làm queue normal trễ.
- Trên RabbitMQ Management, có thể thấy khoảng **2 consumer subscription trên mỗi queue** khi container ổn định; số worker trong JVM vẫn là **2**.

### SMLC co giãn như thế nào?

Khi cấu hình **maxConcurrentConsumers** lớn hơn **concurrentConsumers**, SMLC quan sát những chu kỳ active/idle để tăng hoặc giảm consumer. Các thuộc tính như **consecutiveActiveTrigger**, **startConsumerMinInterval**, **consecutiveIdleTrigger** và **stopConsumerMinInterval** điều chỉnh hành vi này.

**Không phải autoscaler phân bổ từng queue.** Nếu priority có tải lớn còn normal gần như rỗng, thuật toán chủ yếu phản ứng với hoạt động của **toàn container**, chứ không tự tạo một nhóm worker cố định cho riêng priority.

Bạn có thể override concurrency trên từng **@RabbitListener** khi dùng SMLC:

~~~java
@RabbitListener(
    id = "multiQueueOrders",
    queues = {
        MultiQueueTopology.PRIORITY_QUEUE,
        MultiQueueTopology.NORMAL_QUEUE
    },
    concurrency = "2-4"
)
public void handle(String payload) {
    // ...
}
~~~

Đây là minh họa **thay thế cho annotation ở phần 5**. Với SMLC, **"2-4"** nghĩa là min=2, max=4. Giá trị trên annotation **ghi đè** concurrency lấy từ listener factory cho listener tương ứng.

### Khi SMLC phù hợp

- Nhiều queue có **cùng kiểu xử lý** và không cần cấp tài nguyên khác nhau theo queue.
- Cần auto-scaling giữa mức min/max của container.
- Cần các tính năng batching/truyền nhận phù hợp với SMLC.
- Số queue không thay đổi liên tục lúc runtime, hoặc có thể chấp nhận việc recycle consumers khi chỉnh danh sách queue.

## 7. Phương án B: DirectMessageListenerContainer

Nếu muốn **số consumer xác định trên từng queue**, cấu hình Direct container:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        consumers-per-queue: 2
        prefetch: 5
        acknowledge-mode: auto
~~~

Với **hai queue**, DMLC tạo **2 consumer cho priority** và **2 consumer cho normal**, tổng cộng **4 consumer** trong instance. Mỗi consumer có channel riêng. Thay đổi số queue làm thay đổi tổng số consumer:

~~~text
2 queue x 2 consumer/queue = 4 consumer
5 queue x 2 consumer/queue = 10 consumer
10 queue x 2 consumer/queue = 20 consumer
~~~

**Cần tính tài nguyên:** nhiều consumer/channel làm tăng chi phí bộ nhớ và quản trị trên ứng dụng/broker. DMLC không có auto-scaling **concurrentConsumers → maxConcurrentConsumers** như SMLC. Thread xử lý của DMLC phụ thuộc executor của RabbitMQ Java client, nên **số consumer không tự đồng nghĩa số thread vật lý riêng biệt**; cần giám sát thread pool khi nâng consumersPerQueue.

### Đặt concurrency cho từng Direct listener

Annotation **@RabbitListener(concurrency="3")** trên listener dùng Direct factory đặt **consumersPerQueue=3** cho **mỗi queue** mà listener đó theo dõi:

~~~java
@RabbitListener(
    id = "multiQueueOrders",
    queues = {
        MultiQueueTopology.PRIORITY_QUEUE,
        MultiQueueTopology.NORMAL_QUEUE
    },
    concurrency = "3"
)
public void handle(String payload) {
    // ...
}
~~~

Lúc này nếu cả hai queue đã tồn tại và kết nối hợp lệ, mỗi queue có **3 consumer**, tổng 6. Không dùng **"2-4"** ở Direct: dạng khoảng min/max là ngữ nghĩa của **Simple container**, không dành cho **consumersPerQueue**.

### Khi DMLC phù hợp

- Muốn chọn **n consumer cho mỗi queue** một cách dễ dự đoán.
- Danh sách queue có thể được thêm/bớt khi chạy và cần giảm việc recycle consumers của queue không liên quan.
- Muốn giảm bước chuyển message qua queue nội bộ của SMLC.
- Không cần các tính năng batch-only của SMLC và chấp nhận quản lý concurrency của DMLC/Java client.

### So sánh thực tế với hai queue

Giả sử hai queue đều có backlog:

| Thiết lập | Priority | Normal | Điều không được suy luận |
| --- | --- | --- | --- |
| SMLC concurrency=2 | Hai worker có thể nhận | Cũng hai worker đó có thể nhận | Không có hai nhóm worker độc lập |
| DMLC consumersPerQueue=2 | Hai consumer riêng | Hai consumer riêng khác | Không tự bảo đảm đủ CPU để chạy cả bốn cùng lúc |
| DMLC consumersPerQueue=4 | Bốn consumer | Bốn consumer | Tăng đều cho cả hai queue, kể cả queue ít việc |

**Lưu ý:** hai mô hình có thể hiện cùng con số **2 Consumers** trên mỗi queue trong Management UI, nhưng mô hình thực thi vẫn khác. Hãy quan sát **worker threads, channel count, throughput và latency** cùng nhau.

## 8. Muốn phân bổ không đều: tách listener theo queue

Một listener nghe nhiều queue có cùng chính sách concurrency cho tập queue của nó. Nếu priority cần nhiều tài nguyên hơn normal, **cách rõ ràng nhất** thường là khai báo **hai listener endpoint**, mỗi endpoint nghe một queue và có concurrency riêng.

Ví dụ trên **DMLC**, priority cần 4 consumer, normal chỉ cần 1:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SeparatedOrderListeners {
    private final OrderWorkService workService;

    public SeparatedOrderListeners(OrderWorkService workService) {
        this.workService = workService;
    }

    @RabbitListener(
            id = "priorityOrderListener",
            queues = MultiQueueTopology.PRIORITY_QUEUE,
            concurrency = "4")
    public void processPriority(String payload) {
        workService.handlePriority(payload);
    }

    @RabbitListener(
            id = "normalOrderListener",
            queues = MultiQueueTopology.NORMAL_QUEUE,
            concurrency = "1")
    public void processNormal(String payload) {
        workService.handleNormal(payload);
    }
}
~~~

Đoạn trên giả định ứng dụng có một service **OrderWorkService** do bạn định nghĩa. Hai method có hai container do infrastructure tạo; không có class service trong ví dụ vì logic nghiệp vụ tùy dự án.

Khi **spring.rabbitmq.listener.type=direct**, annotation concurrency="4" nghĩa **4 consumer trên priority queue** và concurrency="1" nghĩa **1 consumer trên normal queue**. Nếu chuyển sang SMLC, ý nghĩa từng annotation đổi thành **số worker riêng của container cho queue tương ứng**; hai endpoint vẫn tách biệt.

**Quan trọng:** hai listener ở phần này là một **phương án thay thế** cho **MultiQueueOrderListener** phần 5. Không chạy cả hai phương án cùng lúc khi thử phân bổ, nếu không broker sẽ có thêm consumer ngoài dự kiến.

### Có thể cấu hình hai factory khác nhau

Khi priority và normal cần **ACK, prefetch hoặc retry policy riêng**, có thể khai báo hai listener container factory và chọn bằng **containerFactory** trên mỗi annotation.

Ví dụ với SMLC và Spring Boot 3.x, giữ cấu hình nền bằng configurer:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderListenerFactories {

    @Bean("priorityListenerFactory")
    SimpleRabbitListenerContainerFactory priorityFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setConcurrentConsumers(4);
        factory.setPrefetchCount(2);
        return factory;
    }

    @Bean("normalListenerFactory")
    SimpleRabbitListenerContainerFactory normalFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(10);
        return factory;
    }
}
~~~

Gắn vào endpoint:

~~~java
@RabbitListener(
    queues = MultiQueueTopology.PRIORITY_QUEUE,
    containerFactory = "priorityListenerFactory"
)
public void priority(String payload) {
    // ...
}

@RabbitListener(
    queues = MultiQueueTopology.NORMAL_QUEUE,
    containerFactory = "normalListenerFactory"
)
public void normal(String payload) {
    // ...
}
~~~

Khi dùng cách này, **không thêm annotation concurrency ghi đè** nếu bạn muốn giữ mức từ factory. Cùng một ứng dụng có thể có nhiều listener factory; factory được chỉ định tại annotation mới là factory thực sự điều khiển listener đó.

### Tách khi nào là hợp lý?

| Nhu cầu | Gợi ý |
| --- | --- |
| Hai queue cùng SLA và handler giống nhau | Một @RabbitListener đa queue có thể đủ |
| Priority cần 4 consumer, normal chỉ cần 1 | Hai endpoint, concurrency riêng |
| Một queue cần prefetch thấp và một queue cần cao | Factory riêng hoặc container riêng |
| Một queue cần retry/DLQ khác queue kia | Tách listener để kiểm soát policy rõ ràng |
| Muốn tránh backlog priority làm ảnh hưởng normal trên SMLC | Tách container và tài nguyên; đo CPU/thread thực tế |
| Muốn giảm số consumer khi có hàng chục queue tải nhỏ | Đo lại SMLC và DMLC; đừng đặt consumersPerQueue lớn theo thói quen |

Tách container tạo miền quản lý tốt hơn, nhưng **chưa phải cô lập tài nguyên tuyệt đối** nếu các container vẫn dùng chung process, executor, connection, CPU hoặc database pool. Với SLA thật sự khác biệt, có thể cần tách service/instance hoặc tài nguyên hạ tầng.

## 9. Prefetch và phân phối tải: vì sao nhiều consumer vẫn không đều?

RabbitMQ có cơ chế **prefetch** giới hạn số message chưa được ACK mà broker có thể giao cho consumer theo thiết lập QoS. Khi một consumer đang giữ nhiều delivery chưa ACK, các message đó có thể nằm trong vùng chờ/đang xử lý của consumer, khiến một consumer khác rảnh nhưng không nhận được phần việc đã được giao trước đó.

Ví dụ minh họa:

~~~text
Queue A có 10 message

Consumer C1, prefetch=10:
  nhận nhiều message và giữ Unacked

Consumer C2 đến sau:
  có thể không nhận được message đã được C1 nhận trước
~~~

Với đa queue, prefetch tương tác với số subscription và cách container nhận message. Dù cùng một method xử lý A và B, **không có bảo đảm chia thời gian CPU 50/50** giữa hai queue, đặc biệt nếu một queue có lượng publish lớn hoặc xử lý chậm.

| Prefetch | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| **1** | Ít message Unacked mỗi consumer; thường giúp cân bằng tốt hơn và quan sát thứ tự dễ hơn | Tốn round-trip/overhead nhiều hơn, có thể giảm throughput |
| **5–20** | Điểm khởi đầu thử nghiệm với tác vụ trung bình | Một consumer có thể giữ một số message trước khi ACK |
| **Rất lớn** | Có thể tăng hiệu năng cho tác vụ nhanh và ổn định | Dễ tăng Unacked/bộ nhớ, phân phối không đều và phạm vi redelivery khi lỗi |

**Không có một con số prefetch tốt cho mọi hệ thống.** Cần đo thời gian xử lý, kích thước payload, độ trễ mạng, mức song song, yêu cầu thứ tự và tốc độ ACK. Spring AMQP các phiên bản hiện đại có mặc định prefetch lớn hơn 1; trong bài lab, ta chủ động dùng 5 hoặc 1 để dễ quan sát.

### Phạm vi của prefetch cần hiểu đúng

RabbitMQ AMQP 0-9-1 có cách áp dụng prefetch cho consumer subscription, trong khi SMLC và DMLC tạo channel/subscription theo hai mô hình khác nhau. Đừng suy ra một phép tính duy nhất về Unacked chỉ từ **worker count**. Kiểm tra **Consumer count, Unacked và prefetch thực** trong RabbitMQ Management, đồng thời đo latency từng queue.

### ACK và giao lại message

Trong chế độ **acknowledge-mode: auto** của Spring:

1. Container gọi handler với message.
2. Handler trả về thành công.
3. Container ACK delivery theo cấu hình.
4. Nếu handler lỗi, container/error handler quyết định reject/requeue theo policy.

**AUTO của Spring không đồng nghĩa AMQP no-ack.** Nếu cần manual ACK, cấu hình **MANUAL** và chịu trách nhiệm gọi basicAck/basicNack đúng delivery tag/channel. Không đưa manual ACK vào ví dụ AUTO ở trên vì có thể gây ACK hai lần.

Với nhiều queue và nhiều consumer, xử lý song song có thể làm thứ tự hoàn tất khác thứ tự publish. Nếu cần một luồng xử lý có thứ tự trên **một queue**, cân nhắc prefetch thấp, concurrency phù hợp hoặc **Single Active Consumer**; vẫn phải thiết kế idempotency và thứ tự dữ liệu khi redelivery.

## 10. Lỗi ở một queue có thể ảnh hưởng queue khác như thế nào?

Ví dụ listener chung gọi một API bên ngoài, nhưng tác vụ từ **orders.priority** bị lỗi tạm thời và phải retry lâu.

~~~mermaid
flowchart TD
    Q1[("Priority backlog")] --> H["Một shared listener"]
    Q2[("Normal backlog")] --> H
    H --> R{"Xử lý priority bị timeout"}
    R --> W["Retry/backoff kéo dài"]
    W -.->|"Chiếm worker đang chạy"| H
    H --> OK["Normal message có thể phải chờ"]
~~~

Với SMLC, cùng nhóm worker xử lý delivery từ tất cả queue, nên các lần xử lý lâu ở queue này có thể trì hoãn queue khác. Với DMLC, consumer được tạo riêng theo queue, nhưng **cùng process/thread executor/database pool** có thể vẫn bị tranh chấp nếu xử lý bất đồng bộ không được giới hạn.

### Không dùng một cơ chế retry cho mọi lỗi

| Loại lỗi | Hướng xử lý |
| --- | --- |
| API tạm thời không khả dụng | Retry có giới hạn và backoff; cân nhắc retry queue |
| JSON malformed hoặc header không hợp lệ | Phân loại là lỗi không thể tự hồi phục bằng retry lặp vô hạn |
| Database quá tải | Bảo vệ connection pool, giãn tải, backpressure |
| Consumer mất connection trước ACK | Chấp nhận khả năng redelivery, xử lý idempotent |
| Sai routing/binding dẫn tới queue không nhận event | Kiểm tra publisher confirms/returns và topology, không đổ lỗi cho listener |

**Dead-letter exchange (DLX)** giúp route message bị dead-letter khỏi queue chính khi được cấu hình phù hợp. Nó không tự xuất hiện chỉ vì bạn có hai queue. Nếu dùng **defaultRequeueRejected=true** hoặc retry không giới hạn, poison message có thể quay lại liên tục, làm giảm năng lực xử lý các queue còn lại.

### Hợp đồng idempotency trên nhiều queue

Khi cùng một sự kiện có thể xuất hiện ở **nhiều queue** để phục vụ các nhóm độc lập, chống trùng thường phải có phạm vi theo **consumer nghiệp vụ + eventId**. Chỉ dùng một khóa toàn cục eventId để chặn mọi consumer có thể khiến nhóm nghiệp vụ khác bị bỏ qua sai.

Khi một consumer gặp redelivery do crash trước ACK, cần giữ eventId ổn định. Concurrency lớn hoặc DMLC nhiều consumer không tự tạo exactly-once.

## 11. Thêm và xóa queue lúc ứng dụng đang chạy

Spring AMQP cho phép một listener container bổ sung hoặc loại bỏ tên queue đang listen tại runtime, khi phù hợp với phiên bản và loại container. Những API tiêu biểu: **addQueueNames(...)**, **addQueues(...)**, **removeQueueNames(...)**, **removeQueues(...)**.

**Khác biệt quan trọng:**

- **SMLC:** khi thay đổi danh sách queue, nó thường **cancel và tạo lại toàn bộ consumer** sau khi xử lý các message đã prefetch. Các queue không đổi vẫn có thể bị gián đoạn ngắn.
- **DMLC:** thêm/bớt **consumer của queue liên quan**, tránh cancel consumer của những queue không đổi.

Nếu yêu cầu thường xuyên thêm tenant queue, shard queue hoặc routing partition lúc chạy, đây là một lợi thế vận hành của DMLC.

### 11.1. Tìm listener container qua registry

Các container sinh ra từ annotation thường không phải bean ứng dụng trực tiếp; chúng được quản lý bởi **RabbitListenerEndpointRegistry**. Khi annotation có **id = "multiQueueOrders"** như phần 5, có thể tìm container theo ID:

~~~java
import org.springframework.amqp.rabbit.listener.AbstractMessageListenerContainer;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
public class ListenerQueueMembership {
    private final RabbitListenerEndpointRegistry registry;

    public ListenerQueueMembership(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void addQueue(String queueName) {
        MessageListenerContainer container =
                registry.getListenerContainer("multiQueueOrders");

        if (!(container instanceof AbstractMessageListenerContainer amlc)) {
            throw new IllegalStateException(
                    "Listener multiQueueOrders is unavailable");
        }

        amlc.addQueueNames(queueName);
    }

    public void removeQueue(String queueName) {
        MessageListenerContainer container =
                registry.getListenerContainer("multiQueueOrders");

        if (!(container instanceof AbstractMessageListenerContainer amlc)) {
            throw new IllegalStateException(
                    "Listener multiQueueOrders is unavailable");
        }

        amlc.removeQueueNames(queueName);
    }
}
~~~

Đoạn code dùng cú pháp Java 17 và API Spring AMQP 3.x để minh họa thay đổi subscription. **Không** cấp API HTTP công khai gọi add/remove queueName tùy ý: tên queue phải được xác thực/cho phép theo topology; phần triển khai production cần phân quyền thay đổi cấu hình và đồng bộ giữa các replica.

### 11.2. Container không tự tạo queue chỉ vì thêm tên

**addQueueNames("lab.orders.new")** có nghĩa container thử **đăng ký tiêu thụ từ queue đó**; nó **không thay thế** việc tạo queue và binding. Trước khi thêm queue cần:

1. Xác nhận queue đã được khai báo trên **đúng broker/vhost** và có quyền consume.
2. Đảm bảo exchange/binding gửi message tới queue theo thiết kế.
3. Chọn chính sách ACK, DLX, retry và schema phù hợp.
4. Thay đổi registry/container theo đúng thứ tự, đặc biệt khi có nhiều replica.
5. Quan sát consumer count và backlog sau thay đổi.

Nếu xóa queue khỏi danh sách nghe nhưng **không xóa queue trên RabbitMQ**, backlog có thể tiếp tục tích tụ khi publisher vẫn route tới đó. Việc xóa subscription khác với **RabbitAdmin.deleteQueue(...)**.

### 11.3. Queue bị thiếu khi start hoặc đang chạy

Khi container được cấu hình một số queue chưa tồn tại, Spring AMQP có cơ chế kiểm tra/retry tìm queue; hành vi cụ thể phụ thuộc **missingQueuesFatal**, **autoDeclare**, RabbitAdmin và phiên bản container. Với nhiều queue, một queue thiếu không nhất thiết khiến mọi queue khác dừng nhận, nhưng không nên giả định hệ thống luôn phục hồi mà không giám sát.

**Cần kiểm tra:**

- Queue có tồn tại trên vhost listener đang kết nối không?
- RabbitAdmin nào chịu trách nhiệm khai báo, có được auto-declare không?
- Listener dùng **ConnectionFactory** nào, có trỏ sai broker/vhost không?
- Có consumer-cancel notification do queue bị xóa không?
- Log listener container có cảnh báo passive declare/connection recovery không?

Nếu bạn **chủ động loại bỏ một queue vĩnh viễn**, hãy cập nhật danh sách queue container thay vì để nó tiếp tục thử consume một queue đã xóa.

## 12. Khởi động và kiểm chứng theo kịch bản

### 12.1. Kịch bản A: một multi-queue listener trên SMLC

Dùng topology và publisher phần 4, listener đa queue phần 5 và:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: simple
      simple:
        concurrency: 2
        max-concurrency: 2
        prefetch: 1
        acknowledge-mode: auto
~~~

Đặt **max-concurrency=2** để giữ số worker cố định, dễ quan sát trong lab. Tạo một số message từ publisher:

~~~java
for (int i = 1; i <= 10; i++) {
    publisher.sendPriority("P-" + i);
    publisher.sendNormal("N-" + i);
}
~~~

Vòng lặp này nằm trong **service/runner thử nghiệm** có tham chiếu **MultiQueuePublisher publisher**. Nếu muốn tạo runnable đầy đủ không cần REST API:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class DemoMultiQueueRunner {

    @Bean
    ApplicationRunner sendLabMessages(
            MultiQueuePublisher publisher,
            Environment environment) {

        return args -> {
            if (!environment.getProperty(
                    "demo.publish-on-start", Boolean.class, false)) {
                return;
            }

            for (int i = 1; i <= 10; i++) {
                publisher.sendPriority("P-" + i);
                publisher.sendNormal("N-" + i);
            }
        };
    }
}
~~~

**Mặc định demo.publish-on-start=false** để không gửi lặp mỗi lần khởi động consumer. Khi chủ động làm lab, bật cờ đúng **một lần**; nếu chạy nhiều instance đồng thời, chỉ bật ở một instance publisher.

Log có thể là:

~~~text
[queue=lab.orders.priority] priority:P-1
[queue=lab.orders.normal] normal:N-1
[queue=lab.orders.priority] priority:P-2
...
~~~

**Thứ tự log không phải yêu cầu cố định**. Kiểm tra trong Management rằng cả hai queue có consumer, message được deliver/ACK và Ready trở về 0 khi xử lý xong.

### 12.2. Kịch bản B: chuyển sang DMLC

Giữ topology/publisher/listener, **đổi duy nhất cấu hình listener**:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        consumers-per-queue: 2
        prefetch: 1
        acknowledge-mode: auto
~~~

Khởi động lại ứng dụng. Với hai queue, dự kiến **bốn consumer subscription** tổng cộng (hai mỗi queue) thay vì hai worker SMLC dùng chung cho hai queue. Quan sát **Channels** để xác nhận mỗi consumer Direct dùng channel riêng.

**Chỉ chạy một trong hai phương án khi so sánh.** Nếu vẫn còn instance SMLC đang nghe cùng queue, consumer count sẽ bị cộng dồn và bạn không thể quy kết log cho cấu hình riêng đang thử.

### 12.3. Kịch bản C: xử lý nhiều instance

Chạy hai instance cùng DMLC consumersPerQueue=2, cùng broker/vhost. Nếu mỗi instance có hai queue, RabbitMQ có thể thấy **4 consumer trên mỗi queue**, tổng 8 (khi không có container khác). Một message của một queue chỉ được một consumer trong các competing consumers nhận trên lần delivery thông thường; nó **không tự gửi một bản cho mỗi instance**.

**Lưu ý giới hạn của kết quả:** nếu queue bật **Single Active Consumer (SAC)**, dù đăng ký nhiều consumer, broker chỉ cấp message cho **một active consumer trên queue** tại một thời điểm; tính toán consumer count không đồng nghĩa throughput tăng theo cùng tỷ lệ.

## 13. Cách quan sát để điều chỉnh consumer

Trong **RabbitMQ Management**, với từng queue hãy theo dõi:

| Số liệu | Trả lời câu hỏi |
| --- | --- |
| **Consumers** | Có bao nhiêu subscription đang đăng ký vào queue? |
| **Ready** | Có bao nhiêu message đang chờ được broker giao? |
| **Unacked** | Có bao nhiêu message đã giao nhưng chưa ACK? |
| **Publish rate** | Producer đang đưa message vào queue nhanh đến mức nào? |
| **Deliver/Ack rate** | Consumer đang nhận và hoàn tất ACK nhanh đến đâu? |
| **Redelivered rate** | Có nhiều message bị giao lại hay không? |
| **Channels/Connections** | Số channel/connection có tương thích cấu hình container không? |

Nếu broker chạy với Docker Compose, service tên **rabbitmq**:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues -p / name consumers messages_ready messages_unacknowledged
docker compose exec rabbitmq rabbitmqctl list_channels connection number consumer_count
~~~

Tên service/vhost trong lệnh là ví dụ; dùng tên thực tế của môi trường bạn. **Consumers** trên broker là số subscription AMQP, không phải số thread Java hoặc số lần gọi handler. Với SMLC, một worker có thể có subscription trên nhiều queue; với DMLC mỗi consumer/queue dùng channel riêng.

### Diễn giải một số trạng thái

| Quan sát | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| Priority **Ready** tăng, Normal bình thường | Priority publish nhanh hơn xử lý hoặc tác vụ priority chậm | Tách listener, tăng concurrency đúng queue, đo dependency |
| Cả hai queue Ready tăng nhưng CPU rất cao | Cả hai dùng chung tài nguyên process, DB/API hoặc thread pool | Tối ưu xử lý, cân nhắc scale instance/tách workload |
| **Unacked** cao, ACK rate thấp | Prefetch cao, handler treo/chậm, transaction kéo dài | Giảm prefetch có đo lường, kiểm tra timeout/deadlock |
| Một queue Consumers=0 | Container chưa start, tên queue sai, thiếu quyền hoặc missing queue | Đối chiếu logs/ConnectionFactory/queue names |
| Consumer count gấp đôi dự kiến | Đã chạy hai phương án/lại thêm replica hoặc annotation khác cùng queue | Kiểm tra tất cả @RabbitListener và pod đang chạy |
| Redelivered tăng mạnh | Consumer crash, exception requeue lặp hoặc mất ACK | Kiểm tra retry, DLQ, idempotency |
| DMLC consumer tăng nhưng throughput không tăng | Hạn chế CPU, executor, database, SAC hoặc lock nghiệp vụ | Đo bottleneck end-to-end, không chỉ tăng consumersPerQueue |
| Nhiều queue ít tải nhưng channel quá nhiều | DMLC consumersPerQueue nhân với số queue và replica | Cân nhắc giảm consumersPerQueue hoặc dùng SMLC phù hợp |

### Quan sát trong ứng dụng

Một log có cấu trúc nên ghi ít nhất:

~~~text
listener=multiQueueOrders
queue=lab.orders.priority
eventId=evt-001
outcome=PROCESSED
processingMs=27
~~~

Không nên dùng **eventId** duy nhất của từng message làm metric label, vì có thể tạo cardinality cực lớn. Dùng **queue, listenerId, eventType, outcome** làm nhãn có giới hạn. Với Spring Boot/Micrometer, có thể bật Observation/Tracing theo phiên bản đang dùng để liên kết luồng publish/consume.

## 14. Lựa chọn kiến trúc theo mục tiêu thực tế

### Tình huống A: 20 queue ít tải, payload giống nhau

Nếu một ứng dụng phục vụ nhiều queue có cùng handler và mỗi queue chỉ phát sinh vài message/phút, DMLC consumersPerQueue=4 có thể tạo **80 consumer subscription trên mỗi replica** khi không cần. Có thể bắt đầu với SMLC ít worker chung, rồi đo latency và starvation trước khi tăng.

Nếu queue được thêm/xóa rất thường xuyên, chi phí recycle consumer của SMLC có thể quan trọng; lúc đó DMLC consumersPerQueue=1 đáng cân nhắc dù số channel cao hơn.

### Tình huống B: 1 queue có SLA 100 ms, 1 queue batch xử lý mất 5 giây

Nếu dùng một SMLC listener chung, handler batch kéo dài có thể chiếm worker và ảnh hưởng message cần SLA nhanh. Nên **tách listener container**, giới hạn prefetch và dùng tài nguyên/executor riêng khi cần. Thậm chí có thể tách thành hai service triển khai riêng nếu SLA quan trọng.

### Tình huống C: Một đội kỳ vọng tăng consumer để giữ thứ tự

Tăng consumer thường **tăng cạnh tranh** và có thể khiến message hoàn tất không theo thứ tự. Nếu bắt buộc giữ thứ tự theo aggregateId, hãy cân nhắc **partition theo khóa** vào nhiều queue, mỗi queue có một luồng xử lý thích hợp hoặc bật **Single Active Consumer**, rồi thiết kế redelivery và idempotency.

### Tình huống D: Hai chức năng đều phải xử lý một sự kiện

Nếu **Billing** và **Analytics** đều cần xử lý **order.created**, hãy tạo **hai queue riêng**, binding cả hai từ exchange. Đừng tạo hai @RabbitListener trên **cùng một queue** rồi chờ mỗi listener nhận cùng message: đó là **competing consumers**, không phải broadcast.

### Tình huống E: 4 consumer cho priority, 1 consumer cho normal

Dùng **hai listener endpoint** với concurrency khác nhau như phần 8, thay vì một DMLC container consumersPerQueue=4 trên cả hai queue. Điều này vừa dễ kiểm soát tài nguyên vừa giúp chỉ số backlog và lỗi theo từng nghiệp vụ rõ hơn.

## 15. Những lỗi và ngộ nhận thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Một listener nghe hai queue thì luôn có hai consumer” | Số consumer phụ thuộc loại container và concurrency; SMLC một worker subscribe nhiều queue | Xác định SMLC/DMLC và kiểm tra RabbitMQ Consumers |
| “SMLC concurrency=4 nghĩa là 4 consumer chỉ cho queue priority” | Worker SMLC có thể xử lý delivery từ **tất cả queue** của container | Nếu cần cấp riêng priority, tách endpoint |
| “DMLC consumersPerQueue=4 với 10 queue chỉ tạo 4 consumer” | Đây là **4 trên mỗi queue**, tổng lý thuyết 40 trong một instance | Nhân với số queue và replica trước khi triển khai |
| “@RabbitListener concurrency='2-4' chạy được cho DMLC” | DMLC nhận giá trị nguyên cho consumersPerQueue | Dùng giá trị như **"2"**, hoặc đổi sang SMLC |
| “Nhiều consumer luôn chia message đều” | Prefetch, thời gian xử lý, tốc độ publish và lịch broker gây lệch | Điều chỉnh prefetch dựa trên số liệu |
| “Priority queue tự được xử lý trước normal queue” | Hai queue độc lập, container không mặc nhiên có scheduler ưu tiên | Tách tài nguyên/SLA; đo độ trễ từng queue |
| “Thêm queue bằng addQueueNames sẽ tạo cả queue và binding” | Container chỉ điều chỉnh subscription | Khai báo topology riêng qua RabbitAdmin/hạ tầng |
| “Một queue bị thiếu thì chắc chắn tất cả queue dừng” | Hành vi recovery phụ thuộc cấu hình và phiên bản | Xem missingQueuesFatal, autoDeclare, logs |
| “Hai @RabbitListener trên cùng queue sẽ cùng nhận mọi event” | Chúng cạnh tranh delivery | Dùng queue riêng cho từng nhóm độc lập |
| “AUTO ACK nghĩa broker không yêu cầu ACK” | Spring AUTO ACK sau xử lý thành công; khác AMQP no-ack | Phân biệt AUTO/MANUAL/NONE |
| “Concurrency lớn bảo đảm đúng một lần” | Crash trước ACK có thể gây redelivery; retry publish có thể tạo trùng | Giữ eventId, idempotency và transaction |
| “DMLC consumer nhiều nhưng thread client không cần quan tâm” | DMLC phụ thuộc executor/thread pool của RabbitMQ client | Quan sát thread pool, CPU, blocked tasks |
| “Đã tăng consumer mà backlog vẫn tăng thì framework hỏng” | Có thể nghẽn DB/API, publisher quá nhanh hoặc SAC giới hạn | Đo tốc độ xử lý và nút thắt end-to-end |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một SMLC listener nghe ba queue, cấu hình concurrency=2 và max-concurrency=2. Có bao nhiêu worker thread, bao nhiêu subscription trên mỗi queue và khoảng bao nhiêu channel cho container?

**Câu 2.** Một DMLC listener nghe ba queue với consumersPerQueue=2. Có bao nhiêu consumer subscription trong một instance? Nếu triển khai hai replica, số subscription tổng cộng có thể là bao nhiêu?

**Câu 3.** Vì sao nhìn thấy “2 Consumers” trên cả queue priority và queue normal chưa đủ để biết ứng dụng dùng SMLC hay DMLC?

**Câu 4.** Priority cần bốn consumer, normal chỉ cần một. Nên dùng một multi-queue DMLC với consumersPerQueue=4 hay hai listener endpoint riêng?

**Câu 5.** Khi dùng DMLC, có thể viết **@RabbitListener(concurrency="2-4")** để bật autoscaling không?

**Câu 6.** Listener đã cấu hình nghe queue A và B. Khi dùng **addQueueNames("C")**, API có tự tạo queue C và binding trên broker không?

**Câu 7.** Vì sao hai listener trên cùng queue không bảo đảm mỗi listener thấy mọi message?

**Câu 8.** Một consumer giữ nhiều message Unacked khi prefetch lớn, khiến consumer khác rảnh. Bạn cần kiểm tra gì trước khi tăng số consumer?

**Câu 9.** Khi consumer mất kết nối trước ACK, một message có thể được giao lại qua queue nào và phải bảo vệ nghiệp vụ bằng cách nào?

**Đáp án gợi ý:**

1. **2 worker SMLC**, thường **2 subscription trên mỗi queue** (tổng 6), và **2 channel** tương ứng hai worker trong điều kiện ổn định.
2. **6 subscription** mỗi instance; **12** ở hai replica nếu tất cả subscribe thành công.
3. SMLC có worker chung cho cả tập queue, trong khi DMLC có consumer/channel riêng theo queue; số subscription giống nhau không phản ánh cấu trúc thực thi.
4. **Hai endpoint riêng** để đặt concurrency 4 và 1, không tăng đều cả hai.
5. **Không.** Direct nhận số nguyên cho consumersPerQueue; khoảng min-max thuộc Simple container.
6. **Không.** Queue/binding phải tồn tại hoặc được tạo riêng bởi RabbitAdmin/hạ tầng.
7. Vì các consumer cùng queue **cạnh tranh** nhận delivery; mỗi message bình thường được giao cho một consumer tại một thời điểm.
8. Kiểm tra **prefetch, Unacked, thời gian xử lý, ACK rate** và bottleneck thay vì chỉ tăng consumer count.
9. Có thể redelivery trên **cùng queue** tới consumer khác nếu delivery chưa ACK; bảo vệ bằng eventId ổn định, idempotency và transaction thích hợp.

## 17. Checklist cho môi trường production

Trước khi chọn listener container để nhận từ nhiều queue, hãy xác nhận:

1. **Topology:** exchange, routing key, binding và queue nào là chủ sở hữu của dịch vụ?
2. **Mục đích nghe nhiều queue:** cùng một handler/schema hay các nghiệp vụ có SLA khác nhau?
3. **Container type:** Simple hay Direct, chọn vì lý do kỹ thuật cụ thể nào?
4. **Consumer count:** đã tính theo **queue × consumersPerQueue × replica** với DMLC hay theo worker toàn container với SMLC chưa?
5. **Phân bổ không đều:** queue nào cần container, factory, prefetch và retry riêng?
6. **Prefetch/ACK:** có phù hợp thời gian xử lý, kích thước message và yêu cầu thứ tự không?
7. **Retry/dead-letter:** một poison message có gây vòng lặp hoặc nghẽn các queue còn lại không?
8. **Idempotency:** có xử lý an toàn khi redelivery, publisher retry hoặc crash trước ACK không?
9. **Runtime queue changes:** thêm/bớt queue có cần được điều phối với RabbitAdmin, broker và các replica không?
10. **Observability:** có theo dõi Consumers, Ready, Unacked, latency, ACK/redelivery rate, CPU, thread pool và DLQ từng queue không?
11. **Broker/vhost:** mọi consumer có thực sự dùng đúng ConnectionFactory và quyền consume không?
12. **Cách thử nghiệm:** đã đo hệ thống dưới workload lệch tải, queue thiếu, sự cố mạng và thay đổi số replica chưa?

**Kết luận:** **@RabbitListener có thể nghe nhiều queue**, nhưng cách phân bổ consumer phụ thuộc loại **listener container**. **SMLC** tổ chức một tập worker xử lý delivery từ các queue và có thể co giãn min/max; **DMLC** cấp **consumersPerQueue** riêng trên từng queue, phù hợp với mô hình thay đổi queue động và đếm consumer theo queue. Khi các queue có tải, SLA hoặc chính sách lỗi khác nhau, hãy cân nhắc **tách listener endpoint/container** thay vì cố ép một cấu hình chung. Kết hợp thiết kế container với **RabbitTemplate, exchange/binding, prefetch, ACK, retry, dead-letter, idempotency và quan sát hệ thống** để duy trì xử lý bất đồng bộ đáng tin cậy.

### Tài liệu tham khảo

- [Spring AMQP – Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html)
- [Spring AMQP – Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html)
- [Spring AMQP – Listener Container Queues](https://docs.spring.io/spring-amqp/reference/amqp/listener-queues.html)
- [Spring AMQP – Container Configuration Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring AMQP – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Spring AMQP – Container Management](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/container-management.html)
- [Spring Boot – AMQP (theo phiên bản)](https://docs.spring.io/spring-boot/reference/messaging/amqp.html)
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
