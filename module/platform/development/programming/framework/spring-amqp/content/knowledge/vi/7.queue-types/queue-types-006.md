# Single Active Consumer và điều kiện sử dụng

Trong RabbitMQ, nhiều consumer có thể đăng ký nhận message từ cùng một queue. Mặc định, broker có thể phân phối công việc cho nhiều consumer để chia tải. Nhưng một số nghiệp vụ cần **mỗi thời điểm chỉ một consumer được broker giao message từ queue**, trong khi những consumer khác vẫn kết nối sẵn để tiếp quản nếu consumer hiện tại mất khả dụng. RabbitMQ hỗ trợ cơ chế **Single Active Consumer (SAC)** cho trường hợp đó.

Trong **Spring AMQP**, SAC được bật bằng queue argument **x-single-active-consumer=true**. Ứng dụng vẫn dùng **RabbitTemplate** để publish, **@RabbitListener** để consume và exchange/queue/binding như bình thường. SAC là thuộc tính **cấp queue trên broker**, không phải một cờ riêng của Spring Boot.

Bài học thuộc chương **Các loại hàng đợi**. Sau bài này, bạn có thể giải thích active/standby, biết khi nào nên chọn SAC, cấu hình bằng Java, thực hành failover, phân biệt classic và quorum queue, và hiểu các giới hạn liên quan đến ack, thứ tự, retry, dead-letter và tính nhất quán nghiệp vụ.

## 1. SAC hoạt động như thế nào?

Queue bật SAC có các đặc điểm:

1. Nhiều consumer được phép **đăng ký** cùng một queue.
2. Broker chọn **một consumer active** và chỉ giao message của queue cho consumer đó.
3. Các consumer khác ở trạng thái **standby/waiting**, không cùng chia tải.
4. Khi consumer active hủy subscription, mất channel/connection hoặc không còn khả dụng đối với broker, một standby có thể được chọn làm active mới.
5. Chỉ có **một active consumer trên mỗi queue**; queue khác có thể có active riêng.

~~~mermaid
flowchart LR
    P["Producer / RabbitTemplate"] --> E{"Exchange"}
    E --> Q[("Queue: orders.sac<br/>SAC=true")]
    Q -->|"Giao message"| A["Consumer A<br/>ACTIVE"]
    Q -.->|"Chờ"| B["Consumer B<br/>STANDBY"]
    Q -.->|"Chờ"| C["Consumer C<br/>STANDBY"]
~~~

**SAC giới hạn việc broker giao message cho consumer.** Nó không tự khóa tài nguyên bên ngoài, không tự đảm bảo mỗi message chỉ gây tác dụng nghiệp vụ một lần và không thay thế cơ chế transaction hay idempotency.

### SAC khác competing consumers thông thường ở đâu?

| Tiêu chí | Queue thông thường có nhiều consumer | Queue bật SAC |
| --- | --- | --- |
| Số consumer có thể subscribe | Nhiều | Nhiều |
| Số consumer được giao message đồng thời | Có thể nhiều | Một active |
| Mục tiêu | Chia tải, tăng throughput | Giới hạn luồng nhận, có standby để failover |
| Thêm consumer | Có thể tăng song song | Chủ yếu tăng dự phòng |
| Active bị mất kết nối | Broker tiếp tục giao cho consumer còn lại | Broker chọn standby thành active |
| Exactly-once | Không mặc nhiên | Vẫn không mặc nhiên |
| Thứ tự hoàn tất nghiệp vụ | Không mặc nhiên | Không tuyệt đối nếu có retry, redelivery, bất đồng bộ |

## 2. SAC thuộc queue, không thuộc exchange

Publisher đưa message vào **exchange**. Exchange định tuyến qua **binding** đến một hoặc nhiều queue. SAC chỉ kiểm soát **consumer của queue đã bật SAC**.

~~~mermaid
flowchart TD
    P["Publisher: order.created"] --> F{"Fanout exchange"}
    F --> Q1[("billing.queue<br/>SAC=true")]
    F --> Q2[("analytics.queue<br/>SAC=false")]
    Q1 --> B1["Billing A<br/>ACTIVE"]
    Q1 -.-> B2["Billing B<br/>STANDBY"]
    Q2 --> A1["Analytics A"]
    Q2 --> A2["Analytics B"]
~~~

Ví dụ trên, Billing nhận sự kiện qua queue riêng có một active consumer; Analytics dùng queue riêng và chia việc giữa hai consumer. Cùng một sự kiện có thể xuất hiện ở **hai queue** vì exchange định tuyến đến hai đích. Việc bật SAC ở Billing **không** giới hạn Analytics và cũng không khiến Billing A, Billing B đều nhận cùng một message.

## 3. Điều kiện sử dụng: khi nào nên bật?

SAC phù hợp nếu công việc từ **cùng một queue** cần hạn chế tiêu thụ song song nhưng vẫn muốn nhiều instance có thể dự phòng:

| Tình huống | SAC phù hợp? | Lý do |
| --- | --- | --- |
| Xử lý tuần tự một luồng cập nhật sổ cái | Có thể phù hợp | Hạn chế hai consumer nhận các cập nhật cạnh tranh |
| Gửi lệnh đến thiết bị chỉ chịu được một luồng điều khiển | Phù hợp nếu queue tương ứng phạm vi cần tuần tự | Một active điều phối, standby tiếp quản |
| Muốn một instance làm việc và instance khác chờ dự phòng | Phù hợp | Broker có thể chuyển active khi subscription hiện tại mất |
| Resize hàng nghìn ảnh độc lập | Thường không | Competing consumers có thể tận dụng xử lý song song |
| Tăng throughput một queue bằng 20 worker | Không | SAC chỉ có một active tại một thời điểm |
| Cần tuần tự theo accountId nhưng các account khác xử lý song song | Một queue SAC có thể quá hạn chế | Cân nhắc partition nhiều queue theo khóa |
| Muốn một event được Billing và Notification đều nhận | Không phải chức năng SAC | Cần exchange định tuyến đến hai queue |
| Cần exactly-once giữa RabbitMQ và DB | Không đủ | Cần idempotency và phương án nhất quán dữ liệu |

**Ví dụ:** nếu mọi cập nhật đến một sổ cái phải được kiểm tra và áp dụng lần lượt, SAC giúp broker không giao song song các message của queue cho nhiều consumer. Tuy nhiên, khi failover, tiến trình cũ có thể còn đang chạy một thao tác DB trong khi tiến trình mới được giao message. Vì vậy không được bỏ qua khóa nghiệp vụ, số phiên bản và idempotency.

### Đánh đổi về thông lượng

Giả sử active consumer xử lý tối đa 50 message/giây trong khi publisher gửi 200 message/giây, backlog có thể tăng khoảng 150 message/giây trong mô hình đơn giản. Thêm standby không làm năng lực xử lý cùng queue tăng thành 100 hay 200 message/giây. Nếu throughput là ưu tiên, hãy tối ưu active consumer hoặc chia workload thành các queue độc lập khi nghiệp vụ cho phép.

## 4. Cách khai báo SAC trong Spring AMQP

RabbitMQ kích hoạt cơ chế bằng **queue argument**:

~~~text
x-single-active-consumer = true
~~~

Khai báo qua **QueueBuilder**:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SacQueueConfig {
    public static final String QUEUE_NAME = "demo.orders.sac";

    @Bean
    Queue ordersSacQueue() {
        return QueueBuilder.durable(QUEUE_NAME)
                .withArgument("x-single-active-consumer", true)
                .build();
    }
}
~~~

**QueueBuilder.durable(...)** tạo mô tả queue durable, còn **withArgument(...)** chỉ định SAC. Việc Spring tạo bean chưa đảm bảo RabbitMQ đã có queue: cần **RabbitAdmin** hoặc một cơ chế quản trị khác thực hiện khai báo. Với dự án Spring Boot dùng **spring-boot-starter-amqp**, auto-configuration thường cung cấp **AmqpAdmin/RabbitAdmin** nếu đáp ứng điều kiện tương ứng.

### SAC chỉ được quyết định khi tạo queue

RabbitMQ không cho bật/tắt SAC trên queue đang tồn tại qua **policy động**. Nếu queue cùng tên đã có mà thiếu argument SAC, khai báo lại bằng code mới có thể bị từ chối:

~~~text
PRECONDITION_FAILED - inequivalent arg 'x-single-active-consumer'
~~~

Cách xử lý:

1. Kiểm tra queue đang tồn tại và lượng message chưa xử lý.
2. Xác định ai sở hữu topology.
3. Lập kế hoạch tạo queue mới có SAC rồi chuyển binding/consumer và xử lý backlog; hoặc tái tạo queue ở môi trường lab khi chắc chắn không còn dữ liệu cần giữ.
4. Kiểm chứng **Arguments** của queue mới trên RabbitMQ Management.

Không dùng thao tác xóa queue chứa dữ liệu production chỉ để lệnh declare chạy thành công.

## 5. Classic queue và quorum queue với SAC

SAC được RabbitMQ hỗ trợ ở cả **classic queue** và **quorum queue**. Cơ chế một active consumer giống nhau ở mục đích, nhưng lựa chọn queue type quyết định cách lưu trữ và một số hành vi chọn consumer.

| Tiêu chí | Classic queue + SAC | Quorum queue + SAC |
| --- | --- | --- |
| Bật SAC | **x-single-active-consumer=true** | Cùng argument |
| Consumer được giao message | Một active | Một active |
| Consumer priority khi chọn active | Không dùng consumer priority như quorum queue | Có hỗ trợ xét consumer priority |
| Độ bền/khả dụng dữ liệu | Theo đặc tính classic queue và triển khai broker | Có cơ chế replication/consensus của quorum queue |
| Thêm standby để tăng throughput | Không | Không |

Để khai báo một **quorum queue SAC** trong Spring AMQP:

~~~java
@Bean
Queue ordersQuorumSacQueue() {
    return QueueBuilder.durable("demo.orders.quorum.sac")
            .withArgument("x-queue-type", "quorum")
            .withArgument("x-single-active-consumer", true)
            .build();
}
~~~

Đoạn code dùng các import **Queue**, **QueueBuilder**, **Bean** như phần trên và khai báo **queue khác tên**. Không thể biến queue classic đã tồn tại thành quorum đơn giản bằng cách khai báo lại với cùng tên.

**Hai tầng dự phòng khác nhau:** quorum queue tập trung vào tính sẵn sàng/dữ liệu của **queue trên broker**; SAC tập trung vào khả năng **consumer standby** tiếp quản. Một queue có thể có quorum nhưng chỉ một consumer; hoặc có nhiều consumer standby nhưng không có HA dữ liệu cấp broker.

Với quorum queue, consumer priority có thể tham gia quyết định consumer nào active, theo quy tắc và thời điểm chuyển đổi của RabbitMQ. Priority không chia tỷ lệ message cho các consumer. Bài lab cơ bản không cần cấu hình priority.

## 6. Thực hành với Spring Boot và hai instance

Mục tiêu: một queue SAC, hai instance Spring Boot có @RabbitListener cùng nghe queue đó, chỉ một instance nhận message trong điều kiện bình thường. Sau khi dừng active, standby tiếp quản.

### 6.1. Dependency và kết nối

Với Gradle:

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

Ví dụ **application.yml** cho RabbitMQ cục bộ có tài khoản lab phù hợp:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /

    listener:
      simple:
        concurrency: 1
        max-concurrency: 1
        prefetch: 1
        acknowledge-mode: auto

app:
  instance-id: worker-local
~~~

Bạn phải tạo user tương ứng trên broker hoặc chỉnh lại credentials theo môi trường. Với production, không đưa mật khẩu trực tiếp vào file cấu hình đã commit.

- **concurrency: 1, max-concurrency: 1**: với simple listener container, mỗi instance tạo một consumer; hai process có hai consumer cùng queue.
- **prefetch: 1**: hạn chế mỗi consumer/channel giữ nhiều message chưa ack, giúp minh họa xử lý gần như nối tiếp.
- **acknowledge-mode: auto**: container gửi ack khi phương thức listener hoàn thành thành công; **khác** chế độ AMQP auto-ack/no-ack (không đợi consumer ack).
- **app.instance-id**: tên do ứng dụng tự đặt để biết instance nào đang xử lý.

Nếu dùng loại listener container khác, cần chỉnh prefetch/ack/concurrency trên container factory thực sự được @RabbitListener sử dụng.

### 6.2. Khai báo queue

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class SacTopology {
    public static final String QUEUE = "demo.orders.sac";

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .withArgument("x-single-active-consumer", true)
                .build();
    }
}
~~~

Ở ví dụ này, publisher dùng **default exchange** (exchange tên rỗng) đã được broker bind ngầm với queue theo routing key là **tên queue**. Có thể thay bằng direct/topic/fanout exchange cùng binding mà không thay đổi cơ chế SAC của queue.

### 6.3. Viết listener hiển thị instance

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class OrderSacListener {
    private final String instanceId;

    public OrderSacListener(Environment environment) {
        this.instanceId = environment.getProperty(
                "app.instance-id", "unknown");
    }

    @RabbitListener(queues = SacTopology.QUEUE)
    public void process(String message) throws InterruptedException {
        System.out.printf("[%s] START %s%n", instanceId, message);

        // Chỉ mô phỏng thời gian xử lý, không dùng sleep để retry.
        Thread.sleep(400);

        System.out.printf("[%s] DONE  %s%n", instanceId, message);
    }
}
~~~

Listener dùng **String** làm payload cho ví dụ đơn giản. Nếu phương thức hoàn thành thành công, container ack message theo chế độ **AUTO**. Nếu phương thức ném exception, hành vi redelivery/requeue/retry/dead-letter phụ thuộc cấu hình; SAC không tự xử lý lỗi nghiệp vụ.

### 6.4. Publisher gửi bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderSacPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderSacPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void send(String orderId) {
        rabbitTemplate.convertAndSend(
                "",                 // Default exchange
                SacTopology.QUEUE,  // Routing key là tên queue
                "order.created:" + orderId
        );
    }
}
~~~

Trong một luồng nghiệp vụ, gọi **send("O-1001")**, **send("O-1002")** để publish. Bạn cũng có thể vào **RabbitMQ Management → Exchanges → AMQP default → Publish message**, điền routing key **demo.orders.sac**, payload **order.created:O-1001** và content type **text/plain** nếu giao diện hỗ trợ.

Để thử gửi một loạt message khi ứng dụng chạy mà không tạo HTTP endpoint, có thể thêm bean **ApplicationRunner** (tắt mặc định bằng publish-count = 0):

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class DemoPublisherConfiguration {
    @Bean
    ApplicationRunner demoPublisher(
            OrderSacPublisher publisher, Environment environment) {
        return args -> {
            int count = environment.getProperty(
                    "demo.publish-count", Integer.class, 0);
            for (int i = 1; i <= count; i++) {
                publisher.send("O-" + i);
            }
        };
    }
}
~~~

Khi hai instance chỉ đóng vai trò consumer, giữ **demo.publish-count=0** và gửi message thủ công bằng UI. Nếu muốn dùng ApplicationRunner publish, chỉ bật trên instance bạn chủ động chọn để tránh publish trùng.

### 6.5. Chạy hai tiến trình

Giả sử đã build JAR thành **sac-demo.jar**. Mở hai terminal:

**Terminal A:**

~~~bash
java -jar sac-demo.jar --app.instance-id=worker-a --demo.publish-count=0
~~~

**Terminal B:**

~~~bash
java -jar sac-demo.jar --app.instance-id=worker-b --demo.publish-count=0
~~~

Tên JAR trên chỉ để minh họa, hãy dùng đường dẫn artifact thực tế. Nếu ứng dụng chứa HTTP server, mỗi instance cần cổng web khác nhau, chẳng hạn **--server.port=8081** và **--server.port=8082**.

Trên RabbitMQ Management, mở queue **demo.orders.sac** và kiểm tra argument **x-single-active-consumer=true**, số consumer đã đăng ký là **2** nếu cả hai kết nối thành công. Tùy phiên bản UI, trạng thái consumer sẽ có thông tin active/waiting.

Publish O-1001, O-1002, O-1003. Dự kiến chỉ một terminal có log:

~~~text
[worker-a] START order.created:O-1001
[worker-a] DONE  order.created:O-1001
[worker-a] START order.created:O-1002
[worker-a] DONE  order.created:O-1002
[worker-a] START order.created:O-1003
[worker-a] DONE  order.created:O-1003
~~~

Active có thể là **worker-a** hoặc **worker-b**. Không nên dự đoán cứng instance nào được chọn dựa vào tên hoặc thứ tự chạy.

### 6.6. Kiểm chứng failover

1. Giữ hai instance đang subscribe queue, xác định instance active qua log.
2. Publish thêm message để thấy active đang làm việc.
3. Dừng instance active trong môi trường lab, giữ standby chạy.
4. Khi RabbitMQ phát hiện subscription active không còn khả dụng, broker chọn một standby làm active.
5. Publish message mới và quan sát log ở instance vừa được kích hoạt.

Nếu active bị mất kết nối **trước khi ack**, message đã nhận có thể được **redeliver** cho active mới. Cùng một message có thể xuất hiện trong log ở cả hai instance. Nếu tiến trình cũ vẫn thực hiện side effect bên ngoài khi connection bị cắt, consumer mới không tự ngăn tiến trình cũ ghi dữ liệu. Cần **idempotency**, khóa/phiên bản nghiệp vụ hoặc cơ chế phòng vệ tương ứng.

Thời gian failover còn phụ thuộc việc channel/connection đóng, heartbeat phát hiện lỗi mạng và khả năng khôi phục; SAC không hứa thời gian chuyển đổi cố định.

## 7. Ack, prefetch và giới hạn thứ tự xử lý

SAC giới hạn **consumer được broker giao message**, không đồng nghĩa tại mọi thời điểm chỉ một tác vụ nghiệp vụ đang chạy.

| Mong muốn | SAC một mình đủ không? | Điều cần thêm |
| --- | --- | --- |
| Chỉ một active consumer trên queue | Có khi queue và consumer hợp lệ | Quan sát broker |
| Một message xử lý tại một thời điểm | Chưa chắc | Prefetch 1, xử lý đồng bộ và ack đúng lúc |
| Side effect DB hoàn tất đúng thứ tự | Chưa chắc | Không chạy task bất đồng bộ chồng nhau, versioning |
| Exactly-once sau failover | Không | Idempotency và transaction nghiệp vụ |
| Message lỗi không làm kẹt queue | Không | Retry có giới hạn, dead-letter |
| Queue vẫn hoạt động khi node RabbitMQ lỗi | Không | Chọn queue type và triển khai HA phù hợp |

Ví dụ nếu active có prefetch 3 rồi đẩy việc vào executor:

~~~text
Queue SAC: M1, M2, M3
       |
       v
Active consumer (prefetch=3)
       |-- Task M1: chậm
       |-- Task M2: nhanh
       '-- Task M3: nhanh

Thứ tự hoàn tất có thể: M2, M3, M1
~~~

Để xử lý gần như nối tiếp, hãy phối hợp **SAC**, **prefetch 1**, listener xử lý đồng bộ, ack sau khi side effect cần thiết hoàn thành, idempotency và retry/DLQ. Ngay cả vậy, redelivery, retry, đổi routing hoặc crash vẫn đòi hỏi thiết kế thứ tự nghiệp vụ và kiểm tra số thứ tự event nếu yêu cầu nghiêm ngặt.

### Phân biệt consumer ack, publisher confirm và retry

| Cơ chế | Xác nhận gì? | Quan hệ với SAC |
| --- | --- | --- |
| Publisher confirm | Broker xử lý lệnh publish theo cơ chế confirm | Không chứng minh consumer đã xử lý |
| Consumer ack | Lần giao message đã được xác nhận | Message được ack rời queue |
| Nack/reject/requeue | Consumer từ chối hoặc yêu cầu giao lại | Có thể giao lại cho active hiện tại hoặc active sau failover |
| Dead-letter | Định tuyến message bị dead-letter theo cấu hình | Không tự có chỉ vì bật SAC |
| Idempotency | Ngăn tác dụng phụ lặp khi message xử lý lại | Vẫn bắt buộc khi nghiệp vụ yêu cầu |

**Ví dụ:** consumer đã ghi DB thành công nhưng mất connection trước khi broker nhận ack. Standby tiếp quản và có thể nhận lại message. SAC không ngăn ghi trùng. Dùng **eventId/orderId làm khóa idempotency** và transaction phù hợp ở nơi lưu trạng thái.

Một lần listener ném exception không đồng nghĩa active consumer đã chết. Nếu lỗi dẫn đến requeue liên tục, cùng active có thể nhận lặp một message; standby vẫn chờ. Cần cấu hình retry, dead-letter và phân loại lỗi thay vì xem failover là chiến lược xử lý message lỗi.

## 8. SAC, exclusive consumer và concurrency=1 khác nhau

| Cơ chế | Phạm vi | Có consumer dự phòng chờ sẵn? | Khi consumer hiện tại dừng |
| --- | --- | --- | --- |
| SAC trên queue | Broker, cho queue cụ thể | Có | Broker chọn standby thành active |
| Exclusive consumer | Subscription độc quyền nếu loại queue hỗ trợ | Không theo kiểu SAC; consumer khác có thể bị từ chối | Consumer khác phải subscribe hợp lệ |
| @RabbitListener concurrency=1 | Một listener container của một instance | Instance khác vẫn có thể consume bình thường | Các instance khác vẫn chia tải nếu queue không SAC |
| Một instance duy nhất | Triển khai ứng dụng | Không | Cần khởi chạy instance mới |

**Ngộ nhận:** hai pod mỗi pod cấu hình **concurrency=1** không có nghĩa toàn hệ thống chỉ một active. Nếu cả hai nghe queue thường, RabbitMQ có hai consumer cạnh tranh. Bật SAC ở queue mới tạo được ngữ nghĩa một active trên toàn queue.

Không cần kết hợp SAC với exclusive consumer: subscription độc quyền có thể ngăn standby đăng ký hoặc không được queue type hỗ trợ như kỳ vọng.

## 9. Muốn tăng throughput mà vẫn tuần tự theo khóa: partition

Nếu chỉ cần tuần tự theo **accountId** nhưng các account khác nhau xử lý độc lập, có thể thiết kế nhiều queue SAC:

~~~mermaid
flowchart LR
    P["Publisher<br/>accountId"] --> R{"Routing theo khóa ổn định"}
    R --> Q0[("partition-0<br/>SAC")]
    R --> Q1[("partition-1<br/>SAC")]
    R --> Q2[("partition-2<br/>SAC")]
    Q0 --> C0["1 active"]
    Q1 --> C1["1 active"]
    Q2 --> C2["1 active"]
~~~

Mọi message của cùng accountId phải được route nhất quán vào **cùng queue**. Mỗi partition xử lý nối tiếp trong phạm vi của nó; các partition có thể chạy song song. Nếu thay số partition, phải lập kế hoạch routing và backlog cũ để tránh một khóa xuất hiện cùng lúc trên queue cũ và queue mới làm sai thứ tự.

## 10. Quan sát SAC trên broker

Trong RabbitMQ Management, mở **Queues → demo.orders.sac** và kiểm tra:

- **Arguments:** có **x-single-active-consumer=true**.
- **Consumers:** số đăng ký; bài lab hai instance thường có hai consumer.
- **Active/waiting:** nếu UI phiên bản hiện tại hỗ trợ hiển thị trạng thái, xác định active và standby.
- **Ready:** message đang chờ giao.
- **Unacked:** message đã giao nhưng chưa ack.
- **Message rates:** tốc độ publish, deliver và acknowledge.

Nếu broker chạy qua Docker Compose với service tên **rabbitmq**, có thể xem:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues -p / name arguments consumers messages_ready messages_unacknowledged
~~~

Lệnh kiểm tra argument, consumer count, ready/unacked trong vhost **/**. Đây là kiểm tra broker; để xác nhận thứ tự xử lý nghiệp vụ còn cần log/trace và kết quả ghi DB.

Nếu hai instance cùng xuất hiện log, kiểm tra queue thật sự đã bật SAC, cả hai có kết nối **cùng broker/vhost/queue** không, và log có thể là công việc chưa hoàn tất từ consumer cũ sau khi mất kết nối hay không. SAC trên hai queue/broker trùng tên **không tạo ra một active chung**.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| PRECONDITION_FAILED khi thêm SAC | Queue cũ không có argument phù hợp | Xác nhận queue, lên kế hoạch migration |
| Hai consumer cùng được giao message | Queue không SAC hoặc kết nối khác queue/vhost/broker | Kiểm tra Arguments và kết nối thực |
| Standby không nhận message dù active chậm | SAC luôn chỉ một active | Tối ưu active, cân nhắc partition |
| Active mất kết nối, message bị xử lý lại | Message chưa ack được redelivery | Idempotency, theo dõi trạng thái ghi dữ liệu |
| Concurrency=1 nhưng hai pod chạy song song | Chỉ giới hạn số consumer trên mỗi pod | Bật SAC trên queue |
| Message lỗi được giao liên tục | Requeue/retry chưa giới hạn | Retry có giới hạn, dead-letter queue |
| Active treo nhưng không failover | Broker vẫn thấy subscription/connection active | Heartbeat, liveness, timeout, giám sát backlog |
| Có standby nhưng broker hỏng thì ngừng phục vụ | SAC không tạo replication cho queue | Chọn queue type/kiến trúc HA phù hợp |
| Code bật SAC nhưng broker chưa có | RabbitAdmin chưa khai báo hoặc đang dùng queue cũ | Kiểm tra auto-declare, log và queue definition |

## 12. Bài tập tự kiểm tra

**Câu 1.** Có ba replica Spring Boot, mỗi replica tạo hai consumer cùng nghe một queue SAC. Bình thường có bao nhiêu consumer được broker giao message đồng thời?

**Câu 2.** Consumer active ghi DB thành công nhưng chưa ack thì mất connection. Standby tiếp quản. Message có thể bị giao lại không? SAC có tự ngăn ghi trùng không?

**Câu 3.** Vì sao tăng replica từ 2 lên 20 không nhất thiết tăng throughput trên một queue SAC?

**Câu 4.** Có thể bật SAC cho queue cũ không SAC bằng RabbitMQ policy động không?

**Câu 5.** Một luồng cần tuần tự theo accountId nhưng account A và B có thể chạy song song. Nên cân nhắc topology nào?

**Đáp án:**

1. **Một active consumer trên queue**; các consumer khác standby.
2. **Có thể redelivery** và SAC không bảo đảm exactly-once; dùng idempotency/kiểm soát trạng thái.
3. Vì broker vẫn chỉ giao message cho **một active consumer** trên queue đó.
4. **Không**; cần tạo queue đã bật SAC và kế hoạch chuyển đổi phù hợp.
5. **Partition theo accountId** vào nhiều queue với routing ổn định, có thể bật SAC trên từng partition.

## 13. Checklist quyết định triển khai

Trước khi dùng SAC trong hệ thống bất đồng bộ đáng tin cậy, hãy xác định: phạm vi dữ liệu cần tuần tự hóa (toàn queue hay theo khóa), mức throughput chấp nhận được, số consumer standby, kiểu classic/quorum và HA broker, cấu hình prefetch/ack, chiến lược retry/dead-letter, idempotency/transaction, cách xử lý message chưa ack khi failover và khả năng quan sát backlog/consumer state.

SAC giúp **chỉ một consumer active nhận message từ mỗi queue và các consumer khác chờ tiếp quản**. Trong Spring AMQP, bật chế độ này bằng queue argument **x-single-active-consumer=true**, sau đó kiểm chứng bằng Management UI và thử failover. Để đạt độ tin cậy nghiệp vụ, vẫn cần thiết kế đầy đủ **RabbitTemplate, @RabbitListener, exchange/binding, ack, retry, dead-letter, giao dịch và quan sát hệ thống**.

### Tài liệu đọc thêm

- [RabbitMQ – Consumers: Single Active Consumer](https://www.rabbitmq.com/docs/consumers#single-active-consumer)
- [RabbitMQ – Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Spring AMQP – Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html)
- [Spring AMQP – Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
