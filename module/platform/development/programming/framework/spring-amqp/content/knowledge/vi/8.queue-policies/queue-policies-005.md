# Priority queue và giới hạn ưu tiên theo loại queue, phiên bản RabbitMQ

Trong chương **Chính sách hàng đợi** của **SPRING_AMQP**, *message priority* giúp RabbitMQ ưu tiên giao công việc quan trọng hơn khi **nhiều message cùng đang chờ trong queue**. Ví dụ một nền tảng xử lý ảnh nhận yêu cầu xem trước khẩn cấp và tác vụ xử lý hàng loạt; khi backlog tăng, yêu cầu khẩn cấp nên được nhận trước.

Bài học tập trung vào lựa chọn queue phù hợp theo **loại queue và phiên bản RabbitMQ**, khai báo bằng **Spring AMQP**, publish bằng **RabbitTemplate**, nhận bằng **@RabbitListener**, điều chỉnh **prefetch/ACK**, và phân biệt ưu tiên với retry, dead-letter hay chính sách vận hành.

> **Chú ý về phiên bản:** Quorum queue trước RabbitMQ 4.0 **không hỗ trợ message priority**. Quorum 4.0–4.2 dùng **hai nhóm normal/high**; từ RabbitMQ **4.3** hỗ trợ **32 mức nghiêm ngặt (0–31)**. Classic queue có priority khi đã khai báo **x-max-priority**; RabbitMQ stream không hỗ trợ sắp xếp message theo priority.

## 1. Message priority thực sự làm gì?

Queue thường giao message theo thứ tự vào trước ra trước (*FIFO*) khi bỏ qua competing consumers, prefetch, requeue và redelivery. Priority có thể làm thay đổi cách broker **lựa chọn message đang ở trạng thái Ready**.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"Job A: priority 1"| E["Exchange"]
    P -->|"Job B: priority 4"| E
    P -->|"Job C: priority 2"| E
    E --> Q[("Queue có backlog<br/>priority được hỗ trợ")]
    Q -->|"Nếu đều Ready:<br/>B có thể được giao trước"| C["Consumer<br/>@RabbitListener"]
~~~

**Priority thuộc từng message**, được gửi qua thuộc tính AMQP 0-9-1 **BasicProperties.priority**. **Queue type** và **phiên bản broker** quyết định có thực thi ưu tiên không, có bao nhiêu mức và dùng thuật toán nào.

Không nhầm lẫn:

| Cơ chế | Áp dụng cho | Tác dụng |
|---|---|---|
| **Message priority** | Từng message | Thay đổi thứ tự chọn message đang chờ để giao |
| **Consumer priority** | Consumer đăng ký vào queue | Ưu tiên *consumer nào* nhận delivery; không thay thế message priority |
| **Prefetch** | Consumer/channel theo cấu hình | Giới hạn delivery chưa ACK, ảnh hưởng lượng message còn ở Ready |
| **TTL và queue length** | Message/queue | Quy định thời gian tồn tại hoặc giới hạn backlog |

**Priority không ngắt công việc đã được một consumer nhận và đang xử lý.** Nó có tác dụng tại thời điểm broker có nhiều message chưa giao để lựa chọn.

## 2. Ma trận hỗ trợ: classic, quorum và stream

Các mốc dưới đây dựa trên tài liệu RabbitMQ đến phiên bản 4.3.

| Queue type / phiên bản | Có message priority? | Cách hoạt động | Có cần x-max-priority? |
|---|---|---|---|
| **Classic queue** | Có nếu bật khi tạo queue | Mức message **0–255**; cấu hình giới hạn tối đa **1–255**; message vượt trần dùng mức trần | **Có**, khai báo một lần |
| **Quorum trước 4.0** | **Không** | Không ưu tiên theo message property | Không áp dụng |
| **Quorum 4.0–4.2** | **Có, hai nhóm** | **Normal: 0–4** hoặc không đặt; **high: 5 trở lên**; chia lượt thiên về high khoảng **2:1** | **Không** |
| **Quorum từ 4.3** | **Có, 32 mức** | Priority **0–31**, giá trị lớn hơn bị giới hạn về **31**; không đặt tương đương **4** | **Không**, luôn bật |
| **Stream/superstream** | **Không** | Xử lý theo log/offset, không lập lịch giao bằng priority của message | Không áp dụng |

Những hệ quả thường bị bỏ qua:

- **Classic:** Nếu không có **x-max-priority**, queue không sắp xếp theo priority, dù producer có gửi property đó. Message không đặt priority được xem là mức **0**.
- **Quorum 4.0–4.2:** Priority 6 và 100 **cùng nhóm high**. Priority 1 và 4 **cùng nhóm normal**. Cơ chế 2:1 không phải thuật toán xếp đủ 256 mức số.
- **Quorum từ 4.3:** Priority 10 khác priority 20, nhưng priority 40 và 255 đều được coi là **31**; không đặt priority là **4**.
- **Stream:** Không thêm **x-max-priority** để mong stream trở thành priority queue.

Kiểm tra **RabbitMQ server version**, không suy đoán từ phiên bản thư viện Spring AMQP. Đọc thêm: [RabbitMQ Priority Support](https://www.rabbitmq.com/docs/priority), [Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues) và [Streams](https://www.rabbitmq.com/docs/streams).

## 3. Classic queue: bật priority bằng x-max-priority

### 3.1. Cấu hình là thuộc tính cố định lúc khai báo

Đối với **classic queue**, đặt optional queue argument **x-max-priority** khi tạo queue.

~~~text
Queue: jobs.priority.classic.q
x-queue-type: classic
x-max-priority: 4

Message priority 0  -> mức 0
Message priority 1  -> mức 1
Message priority 3  -> mức 3
Message priority 4  -> mức 4
Message priority 9  -> xử lý như mức 4
Message thiếu priority -> xử lý như mức 0
~~~

Giá trị **x-max-priority** được phép nằm trong khoảng **1–255**, nhưng tài liệu RabbitMQ khuyên chọn **ít mức ưu tiên**, thường chỉ **2–4**. Mỗi mức tăng thêm có chi phí CPU, RAM và xử lý nội bộ. Giá trị lớn không tự làm job nhanh hơn.

**Không thể cấu hình hoặc thay đổi x-max-priority qua RabbitMQ policy.** Các policy có thể đổi động để điều chỉnh nhiều thiết lập khác như TTL hoặc queue length, trong khi số mức priority của classic queue phải được quyết định khi queue được tạo. Nếu khai báo lại cùng queue với argument khác, broker có thể báo **406 PRECONDITION_FAILED** do thuộc tính không tương đương.

### 3.2. Ví dụ Spring Boot và Spring AMQP

Thêm dependency trong dự án Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Khai báo exchange, classic queue và binding:

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class PriorityDemoTopology {
    public static final String EXCHANGE = "jobs.priority.exchange";
    public static final String ROUTING_KEY = "jobs.priority";
    public static final String QUEUE = "jobs.priority.classic.q";

    @Bean
    public Declarables priorityResources() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);

        Queue queue = QueueBuilder.durable(QUEUE)
                .withArgument("x-queue-type", "classic")
                .maxPriority(4)
                .build();

        return new Declarables(
                exchange,
                queue,
                BindingBuilder.bind(queue)
                        .to(exchange)
                        .with(ROUTING_KEY)
        );
    }
}
~~~

Giải thích:

- **QueueBuilder.maxPriority(4)** thêm argument **x-max-priority=4** vào định nghĩa queue.
- **x-queue-type=classic** chỉ rõ kiểu queue, tránh phụ thuộc default queue type của vhost.
- **durable** giữ định nghĩa exchange và queue qua restart broker; độ bền message còn liên quan persistence, publisher confirms và cấu hình broker.
- RabbitAdmin của Spring AMQP có thể active-declare các bean này khi kết nối được thiết lập, nếu auto-declaration đang bật.

Chạy thử với **queue mới** hoặc queue cũ có định nghĩa tương đương. Không xóa queue đang chứa message quan trọng để sửa lỗi khai báo.

### 3.3. Publish priority bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class PriorityJobPublisher {
    private final RabbitTemplate rabbitTemplate;

    public PriorityJobPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void submit(String jobId, int priority) {
        if (priority < 0 || priority > 4) {
            throw new IllegalArgumentException("Priority must be 0..4");
        }

        rabbitTemplate.convertAndSend(
                PriorityDemoTopology.EXCHANGE,
                PriorityDemoTopology.ROUTING_KEY,
                jobId,
                message -> {
                    message.getMessageProperties().setPriority(priority);
                    return message;
                }
        );
    }
}
~~~

Ở đây **MessagePostProcessor** thiết lập property priority trước publish. Việc dùng validation **0–4** là hợp đồng nghiệp vụ của ứng dụng; nếu gửi 9 vào classic queue có trần 4, RabbitMQ sẽ xử lý nó tương đương 4.

**Routing key không phải priority.** Producer publish vào exchange theo routing key, binding chọn queue, và chỉ sau đó queue mới áp dụng cơ chế ưu tiên delivery.

## 4. Thực hành: phải có backlog để quan sát thứ tự

Một bẫy khi kiểm tra priority là bật consumer trước rồi gửi lần lượt các message. Nếu queue trống và consumer có thể nhận ngay, message priority thấp **đã được giao** trước khi message cao xuất hiện; broker không thể lấy lại delivery đang xử lý.

Để thử đúng, hãy publish **khi chưa có consumer**, sau đó mới bật consumer.

### 4.1. Tạo dữ liệu trong profile producer

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("producer")
public class SeedPriorityMessages {
    @Bean
    ApplicationRunner publishSamples(PriorityJobPublisher publisher) {
        return args -> {
            publisher.submit("low-1", 1);
            publisher.submit("high-1", 4);
            publisher.submit("low-2", 1);
            publisher.submit("medium-1", 3);
            publisher.submit("high-2", 4);
        };
    }
}
~~~

### 4.2. Đặt một consumer, prefetch = 1

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PriorityConsumerConfig {
    @Bean
    public SimpleRabbitListenerContainerFactory priorityListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setPrefetchCount(1);

        return factory;
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("consumer")
public class PriorityJobConsumer {
    @RabbitListener(
            queues = PriorityDemoTopology.QUEUE,
            containerFactory = "priorityListenerFactory"
    )
    public void receive(String jobId) {
        System.out.println("Received: " + jobId);
        // Thành công: container ACK theo AUTO mặc định.
    }
}
~~~

Các class ở mục 3–4 có thể nằm trong cùng Spring Boot application. Chạy trên RabbitMQ đã kết nối đúng **host**, **port**, **virtual-host**, **username**, **password**.

Quy trình:

1. Đảm bảo **jobs.priority.classic.q** đang rỗng và không có consumer nào khác.
2. Chạy ứng dụng với profile **producer**, cho tất cả 5 message vào queue, rồi dừng.
3. Xác nhận RabbitMQ Management UI hiển thị **5 Ready**.
4. Chạy ứng dụng với profile **consumer** và quan sát log.

Ví dụ lệnh với ứng dụng đã đóng gói thành file JAR:

~~~bash
java -jar app.jar --spring.profiles.active=producer
java -jar app.jar --spring.profiles.active=consumer
~~~

Nếu cả 5 message còn Ready trước khi listener chạy, kết quả thường thấy:

~~~text
Received: high-1
Received: high-2
Received: medium-1
Received: low-1
Received: low-2
~~~

Bằng nhau về priority thì thông thường message vẫn theo thứ tự vào queue, nếu không có redelivery/requeue hoặc concurrency làm xáo trộn. Thứ tự **nhận** không tự động bảo đảm thứ tự **hoàn thành** khi tăng số consumer.

## 5. Quorum queue: thuật toán thay đổi qua các bản RabbitMQ

Quorum queue là queue durable có replication dựa trên Raft, thường được lựa chọn khi nghiệp vụ cần an toàn dữ liệu và tính sẵn sàng cao. Nhưng **priority quorum queue không có cùng hành vi với classic queue**.

### 5.1. Trước phiên bản 4.0: không hỗ trợ

Quorum queue trong các phiên bản trước **4.0** không phân phối message theo priority. Việc publisher đặt property vẫn có thể là thông tin ở message, nhưng queue không dùng nó để chọn delivery.

Nếu cần phân loại công việc trên RabbitMQ 3.x, xem xét **tách các queue theo cấp độ quan trọng**, điều chỉnh consumer pool và SLA riêng.

### 5.2. Phiên bản 4.0–4.2: nhóm normal và high

| Giá trị priority | Nhóm trong quorum 4.0–4.2 |
|---|---|
| Không có property priority | **normal** |
| **0, 1, 2, 3, 4** | **normal** |
| **5–255** | **high** |

Khi cả hai nhóm đang có message chờ, cơ chế ưu tiên **tương đối** cố gắng giao khoảng **2 message high cho mỗi 1 message normal**. Điều này giúp nhóm normal có cơ hội tiến triển, thay vì chỉ lấy hết high trước.

Ví dụ khi có **A(1), B(2), C(8)** cùng chờ, C thuộc high và có thể được giao trước A và B. Nhưng **priority 8 và priority 200 không tạo thành hai nhóm khác nhau** ở giai đoạn này.

Không cần bật **x-max-priority**: quorum queue hỗ trợ cơ chế tương ứng với phiên bản mà không cần argument opt-in.

### 5.3. Từ phiên bản 4.3: 32 mức strict priority

RabbitMQ **4.3** giới thiệu **0–31** mức ưu tiên và xếp thứ tự nghiêm ngặt đối với những message sẵn sàng giao:

~~~text
A: priority 1
B: priority 5
C: priority 12
D: priority 40  -> giới hạn hiệu lực thành 31

Nếu cả bốn cùng Ready, thứ tự ưu tiên:
D -> C -> B -> A
~~~

Các điểm đặc thù:

- Không có **priority** được coi như **4** (khác classic queue: **0**).
- Giá trị cao hơn **31** được coi là **31**. Không có mức 32 hoặc 255 riêng.
- **x-max-priority không cần thiết và không dùng để cấu hình quorum**; các mức đã có sẵn.
- Nếu message bị **reject/nack/modify** và trả lại queue, quorum 4.3 dùng luồng message trả lại và thứ tự trả lại; đó là **ngoại lệ** đối với strict priority của message Ready mới.
- Khi luồng message priority cao liên tục, message thấp **có thể bị trì hoãn vô thời hạn**. Nếu cần đảm bảo năng lực cho nhóm thấp, tách queue/consumer pool là phương án dễ kiểm soát hơn.

### 5.4. Khai báo quorum queue với Spring AMQP

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuorumPriorityConfig {
    @Bean
    public Queue quorumPriorityQueue() {
        return QueueBuilder.durable("jobs.priority.quorum.q")
                .quorum()
                .build();
    }
}
~~~

Đây là **queue khác tên** so với classic queue ở mục 3. Muốn publish vào queue này, cần khai báo exchange/binding tương ứng. Phần publish có thể dùng chính **RabbitTemplate.convertAndSend(...)** kết hợp **setPriority(...)**; broker sẽ thực thi thuật toán theo phiên bản của mình.

Không thể nâng classic queue đang tồn tại thành quorum queue bằng cách đổi code rồi khai báo lại cùng tên. RabbitMQ có thể trả về **406 PRECONDITION_FAILED** nếu **x-queue-type** không tương đương.

## 6. Stream và superstream không phải priority queue

RabbitMQ stream phục vụ lưu message dạng log, consumer đọc theo **offset** và có thể đọc lại dữ liệu trong thời gian retention. Đây là mô hình khác queue tiêu thụ và gỡ message sau ACK.

| Tiêu chí | Classic/quorum priority queue | Stream/superstream |
|---|---|---|
| Cách consumer nhận dữ liệu | Broker chọn delivery để giao | Consumer đọc theo offset/partition |
| Message priority | Có tùy loại và phiên bản | **Không** |
| Cấu hình ưu tiên | **x-max-priority** cho classic; quorum có hỗ trợ riêng | Không hỗ trợ lập lịch message priority |
| Đọc lại dữ liệu | Theo mô hình queue, message ACK có thể được loại bỏ | Có thể đọc lại theo retention/offset |

Nếu hệ thống cần lưu event dài hạn nhưng một số tác vụ phải xử lý gấp, có thể dùng **stream lưu sự kiện** và **queue riêng cho công việc** được tạo từ sự kiện. Thiết kế này cần xử lý trùng, checkpoint và bảo đảm không bỏ sót message.

## 7. Prefetch, ACK và concurrency ảnh hưởng hiệu quả priority

~~~mermaid
flowchart LR
    Q[("Queue<br/>Ready messages")] -->|"Delivery"| U["Consumer<br/>Unacked message"]
    U -->|"ACK"| D["Hoàn thành"]
    H["Message priority cao mới đến"] --> Q
    U -.->|"Broker không thể<br/>ngắt việc đang chạy"| U
~~~

Giả sử consumer đang chạy với **prefetch=20**:

1. Broker đã giao 20 job priority thấp, tất cả ở trạng thái **Unacked**.
2. Producer publish một job priority rất cao.
3. Job mới phải chờ đến khi consumer còn hạn mức delivery, dù queue có khả năng ưu tiên cao.
4. Khi ACK làm giảm Unacked, broker mới chọn message phù hợp tiếp theo từ Ready.

Các trường hợp cần phân biệt:

| Trạng thái | Điều xảy ra |
|---|---|
| Queue trống, consumer rảnh | Message có thể được giao ngay, không có backlog để xếp ưu tiên |
| Queue có backlog, prefetch thấp | Nhiều message còn Ready, priority có cơ hội thể hiện |
| Prefetch lớn | Message thấp đã nằm ở consumer, job cao phải đợi |
| Nhiều consumer | Thứ tự hoàn thành khác thứ tự giao |
| NACK/requeue hoặc mất kết nối | Redelivery có thể thay đổi thứ tự quan sát được |

Bắt đầu thử với **prefetch=1** và một consumer để hiểu thuật toán. Sau đó đo throughput, latency và Unacked trước khi tăng prefetch/concurrency.

Trong Spring AMQP, **AcknowledgeMode.AUTO** là listener container tự xác nhận khi phương thức listener xử lý thành công, khác với chế độ broker auto-ack ngay khi giao. Nếu cần **MANUAL**, phải ACK/NACK đúng delivery tag trên đúng channel. ACK sai thời điểm có thể gây mất hoặc lặp lại công việc.

## 8. Tương tác với TTL, max-length, retry và dead-letter

### 8.1. TTL có thể tác động bất ngờ

Ở **classic priority queue**, message hết TTL có thể chưa bị loại khỏi chỉ số ngay nếu chưa đến vị trí queue xử lý expiration. Một message priority thấp có thể vượt TTL trong lúc vẫn xuất hiện ở thống kê, nhưng khi đã hết hạn thì không nên được giao cho consumer.

Ở **quorum 4.3**, cơ chế expiry có thể quét theo từng mức priority, giải quyết một số hạn chế của classic. Dù vậy, priority không thay thế **deadline nghiệp vụ**: job quá thời hạn vẫn phải được ứng dụng phát hiện và xử lý phù hợp.

### 8.2. Queue length và overflow không bảo vệ message ưu tiên cao

Giới hạn **max-length** hoặc **max-length-bytes** có thể khiến broker loại bỏ message hoặc từ chối publish khi hàng đợi đầy. **Không mặc định RabbitMQ sẽ chọn bỏ message priority thấp nhất**. Một cơ chế loại bỏ đầu queue có thể làm mất message quan trọng ngoài mong muốn.

Nếu ưu tiên là yêu cầu SLA nghiêm ngặt, cần kiểm thử overflow, persistence, publisher confirms và chính sách độ dài, không chỉ nhìn thứ tự dequeue.

### 8.3. Retry và DLQ

- **NACK requeue=true liên tục** có thể tạo vòng lặp lỗi và phá kỳ vọng thứ tự.
- **Retry có delay và giới hạn** cho phép xử lý lỗi tạm thời; cần bảo toàn hoặc chủ động thay đổi priority khi republish.
- **Dead-letter queue** dùng để giữ message bị loại hoặc xử lý thất bại theo cấu hình; DLQ cũng có thể có chính sách priority riêng nếu cần.
- Đặc biệt với **quorum 4.3**, message được trả lại không nhất thiết vào lại thứ tự strict priority của các message mới.

### 8.4. Priority không cung cấp exactly-once

Nếu consumer ghi database thành công nhưng mất kết nối trước ACK, message có thể được giao lại. Cần **jobId/eventId**, transaction và cơ chế **idempotency** để tránh tác dụng phụ lặp lại. Message priority không thay thế những bảo đảm đó.

## 9. Vì sao x-max-priority không nên đặt trong RabbitMQ policy?

Đây là khác biệt giữa **chính sách vận hành có thể thay đổi động** và **thuộc tính cấu trúc queue khi tạo**:

1. Classic queue cần biết trần ưu tiên ngay khi được khởi tạo.
2. RabbitMQ không cho thay số mức ưu tiên động trên queue đã tồn tại.
3. RabbitMQ policies thường có thể cập nhật trong lúc chạy, nên **không hỗ trợ khai báo priority queue bằng policy**.
4. Cấu hình cần đặt trong định nghĩa topology hoặc tham số khai báo queue lúc tạo.

Ví dụ khai báo và publish đặt ở hai nơi khác nhau:

~~~java
QueueBuilder.durable("jobs.priority.classic.q")
        .maxPriority(4)
        .build();
~~~

~~~java
rabbitTemplate.convertAndSend(
        "jobs.priority.exchange",
        "jobs.priority",
        "urgent-job",
        message -> {
            message.getMessageProperties().setPriority(4);
            return message;
        }
);
~~~

Sửa số **4** ở QueueBuilder thành **8** rồi khởi động lại **không thay đổi** queue cũ. Nếu thuộc tính khác, active declaration có thể bị RabbitMQ từ chối. Không xóa queue đang có dữ liệu chỉ để bỏ lỗi.

## 10. Chẩn đoán: vì sao message cao không được xử lý trước?

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Classic có priority property nhưng giao gần FIFO | Chưa khai báo x-max-priority | Xem **Arguments** của queue |
| Quorum 4.2 không phân biệt 6 và 30 | Cả hai cùng nhóm high | Kiểm tra server version |
| Quorum 4.3 không có mức 100 | Priority bị clamp về 31 | Kiểm tra rule 0–31 |
| Job gấp chờ dù mới publish | Hạn mức prefetch đầy hoặc job thấp đã Unacked | Theo dõi Ready/Unacked |
| **406 PRECONDITION_FAILED** lúc startup | Queue cũ có argument/type khác định nghĩa mới | So sánh x-max-priority, x-queue-type |
| Stream không ưu tiên message | Stream không hỗ trợ | Tách queue hoặc thiết kế nhiều stream |
| Message thấp chờ quá lâu ở quorum 4.3 | Có nguồn job cao liên tục | Tách queue theo SLA |
| Message biến mất | TTL, overflow, NACK, DLX hoặc lỗi publish | Xem policies, DLQ, publisher confirms/returns |

Có thể kiểm tra server và topology bằng RabbitMQ CLI trong môi trường có quyền:

~~~bash
rabbitmq-diagnostics server_version
rabbitmqctl list_queues -p app_dev name arguments messages_ready messages_unacknowledged consumers
~~~

Trong **RabbitMQ Management UI**, chọn đúng virtual host, kiểm tra **Queue Type**, **Arguments**, **Ready**, **Unacked**, số consumer; trên quorum 4.3 có thể xem thêm chỉ số theo mức priority.

**Phiên bản Spring Boot/Spring AMQP không quyết định queue thuật toán nào.** Broker RabbitMQ là phía thực thi cơ chế priority. Với managed RabbitMQ, cần xác nhận chính xác server version và các giới hạn nhà cung cấp.

## 11. Khi nào nên tách queue theo mức ưu tiên?

Một priority queue là lựa chọn hợp lý khi số mức ít, cùng nhóm worker có thể xử lý tất cả công việc và backlog chưa gây ra yêu cầu SLA đối nghịch.

Nên cân nhắc **nhiều queue** nếu:

- Workload khẩn cấp cần worker riêng luôn sẵn sàng.
- Nhóm công việc thông thường phải có **năng lực tối thiểu bảo đảm**, tránh starvation.
- Các lớp công việc cần **TTL, DLQ, retry, quota hoặc quyền** khác nhau.
- Muốn điều chỉnh concurrency và prefetch độc lập.
- Đang sử dụng stream hoặc phiên bản quorum không cung cấp priority như mong đợi.

~~~mermaid
flowchart LR
    E["jobs.exchange"] -->|"jobs.urgent"| U[("jobs.urgent.q")]
    E -->|"jobs.normal"| N[("jobs.normal.q")]
    U --> WU["Urgent worker pool<br/>SLA riêng"]
    N --> WN["Normal worker pool<br/>SLA riêng"]
~~~

Hai queue tách biệt giúp đặt consumer pool, giám sát backlog và điều chỉnh tài nguyên rõ hơn. Đổi lại, hệ thống cần định tuyến chính xác và quản trị thêm topology.

Đặc biệt, khi quorum 4.3 dùng strict priority, **luồng message cao liên tục có thể trì hoãn message thấp vô thời hạn**. Tách queue và dành tài nguyên xử lý riêng thường dễ đáp ứng yêu cầu công bằng hơn một queue ưu tiên nghiêm ngặt.

## 12. Bài tập thực hành

### Bài A — Classic queue

1. Tạo queue **jobs.priority.classic.q** với x-max-priority=4.
2. Gửi backlog gồm priority 1, 4, 1, 3, 4 khi **không có consumer**.
3. Chạy listener **prefetch=1**, kiểm tra các job mức 4 có được giao trước.
4. So sánh với một classic queue **không khai báo x-max-priority**.
5. Thử priority 9 bằng publisher không giới hạn ở 4; giải thích vì sao không hình thành mức thứ 9.

### Bài B — Quorum 4.0–4.2

Chỉ làm với broker thực sự chạy trong dải phiên bản này:

1. Tạo quorum queue mới không có x-max-priority.
2. Gửi priority 1, 4, 5, 10 khi chưa có consumer.
3. Quan sát hai nhóm normal và high.
4. Tạo backlog đủ lớn thuộc hai nhóm để thấy ưu tiên thiên về high theo tỷ lệ 2:1, không phải strict priority theo 256 giá trị.

### Bài C — Quorum từ 4.3

1. Tạo queue mới bằng QueueBuilder.quorum().
2. Gửi message priority 0, 4, 7, 20, 40 vào queue khi chưa có consumer.
3. Bật listener; ghi nhận giá trị 40 được xem như 31.
4. Gửi một message **không có priority** và xác định mức hiệu lực của nó.
5. Thử NACK/requeue ở môi trường học để thấy hành vi ngoại lệ đối với message trả lại.

### Bài D — Prefetch và concurrency

1. Lặp lại bài A với prefetch=1 và một consumer.
2. Tăng prefetch lên 10, publish job thấp trước rồi job cao trong lúc consumer đang bận.
3. Đo thời gian từ lúc publish đến lúc job cao **bắt đầu được xử lý**.
4. Tăng số consumer lên 3, so sánh **thứ tự được giao** và **thứ tự hoàn tất**.
5. Giải thích vì sao priority không thể lấy lại một message đã giao.

### Câu hỏi tự kiểm tra

1. Classic queue đã được tạo với x-max-priority=4; code mới đổi thành 8. Vì sao có thể phát sinh lỗi 406?
2. Trong quorum 4.2, priority 7 có khác nhóm với priority 31 không?
3. Trong quorum 4.3, message không đặt priority được xem như mức nào? Classic queue thì sao?
4. Vì sao không có cơ chế policy động cho x-max-priority của classic queue?
5. Nếu consumer nhận message ngay khi queue trống, priority có thể đảm bảo job cao xuất hiện sau được xử lý trước không?
6. Khi nào tách queue và worker pool theo SLA tốt hơn dùng một priority queue?

## 13. Những điều cần nhớ

- **Classic:** Bật priority bằng **x-max-priority** lúc khai báo queue; dùng ít mức, không đổi động bằng policy.
- **Quorum trước 4.0:** không có message priority; **4.0–4.2:** hai nhóm normal/high; **từ 4.3:** 32 mức strict priority 0–31, tự bật, không sử dụng x-max-priority.
- **Stream:** Không lập lịch message theo property priority.
- **Message priority**, **consumer priority** và **prefetch** là các cơ chế khác nhau.
- Priority áp dụng khi chọn delivery tiếp theo, không ngắt công việc đang xử lý, không bảo đảm thứ tự hoàn tất và không thay thế ACK, retry, DLQ, idempotency.
- Tính tin cậy khi xử lý bất đồng bộ với **RabbitTemplate** và **@RabbitListener** cần cả topology, cách ACK, cách xử lý lỗi và quan sát backlog.

### Tài liệu tham khảo chính thức

- [RabbitMQ — Priority Support in Queues](https://www.rabbitmq.com/docs/priority): classic/quorum, x-max-priority, prefetch và các giới hạn.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): thuật toán quorum và ngoại lệ redelivery.
- [RabbitMQ — Priority (4.2)](https://www.rabbitmq.com/docs/4.2/priority): hành vi hai nhóm của quorum 4.0–4.2.
- [RabbitMQ — Streams](https://www.rabbitmq.com/docs/streams): những tính năng stream không hỗ trợ.
- [Spring AMQP — Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): QueueBuilder và khai báo tài nguyên.
