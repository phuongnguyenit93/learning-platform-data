# AnonymousQueue, tên queue do broker sinh và vòng đời kết nối

## Mục tiêu bài học

Trong **Spring AMQP**, không phải queue nào cũng cần một tên cố định như **orders.created**. Khi ứng dụng cần nhận message trong một phiên ngắn, mỗi instance có một subscription riêng hoặc cần một queue hồi đáp tạm thời, ta có thể dùng queue được tạo tên tự động.

Bài này thuộc chương **Khai báo tài nguyên** của module **SPRING_AMQP**, hướng tới tích hợp RabbitMQ bằng RabbitTemplate, @RabbitListener, exchange, queue và binding. Sau bài học, bạn sẽ:

- Phân biệt **AnonymousQueue** với queue có **tên do RabbitMQ broker sinh**.
- Hiểu **durable**, **exclusive**, **autoDelete** và việc queue bị xóa khi consumer/connection kết thúc.
- Khai báo **AnonymousQueue + exchange + binding**, publish bằng RabbitTemplate và nhận bằng @RabbitListener.
- Sử dụng **Queue("")**, RabbitAdmin và **getActualName()** đúng cách khi cần broker sinh tên.
- Phân tích phục hồi sau reconnect, nhiều instance, race condition và rủi ro mất message.

## 1. Phân biệt ngay hai cách sinh tên

**AnonymousQueue trong Spring AMQP được Spring sinh tên, không phải RabbitMQ broker.** Đây là điểm dễ nhầm nhất của chủ đề.

| Tiêu chí | AnonymousQueue | Broker-named queue |
| --- | --- | --- |
| Cách tạo | **new AnonymousQueue()** | **new Queue("", false, true, true)** |
| Thành phần sinh tên | **Spring AMQP** | **RabbitMQ broker** |
| Lúc sinh tên | Khi tạo object Java | Khi broker xử lý **queue.declare** có name rỗng |
| Tên thường thấy | **spring.gen-...** | **amq.gen-...** (tiền tố do broker quản lý) |
| Lấy tên | **getName()** | **getActualName()** sau khi RabbitAdmin khai báo |
| Khi reconnect trong cùng ApplicationContext | RabbitAdmin có thể khai báo lại **cùng tên bean đã sinh** | Broker cấp **tên mới** khi khai báo lại |
| Khi restart toàn bộ tiến trình Java | Object mới thường sinh tên mới | Broker thường cấp tên mới |

Mặc định, Spring AMQP dùng **Base64UrlNamingStrategy**: tên **spring.gen-** cộng UUID mã hóa Base64 URL-safe. Chiến lược tạo tên có thể thay đổi, nhưng phải đảm bảo tên đủ duy nhất giữa các instance.

~~~java
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Base64UrlNamingStrategy;

AnonymousQueue queue1 = new AnonymousQueue();
System.out.println(queue1.getName());   // Ví dụ: spring.gen-...

AnonymousQueue queue2 = new AnonymousQueue(
        new Base64UrlNamingStrategy("dashboard.temp-"));
System.out.println(queue2.getName());   // Ví dụ: dashboard.temp-...
~~~

Với broker-named queue, name được truyền dưới dạng chuỗi rỗng:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitAdmin;

Queue queue = new Queue("", false, true, true);
String nameFromBroker = rabbitAdmin.declareQueue(queue);

System.out.println(nameFromBroker);       // Tên RabbitMQ trả về
System.out.println(queue.getActualName()); // Tên thực tế sau declare
~~~

Trong ví dụ trên, **rabbitAdmin** là bean RabbitAdmin đã được cấu hình. Trước khi declare, object **Queue** chưa biết tên do broker sinh. Sau khi declare, RabbitAdmin cập nhật **actualName**. **Không dùng getName() làm tên thực tế** cho kiểu queue name rỗng.

RabbitAdmin cũng cung cấp **declareQueue()** không tham số để khai báo một queue do broker đặt tên với các thuộc tính **non-durable**, **exclusive**, **auto-delete**. Cách này vẫn khác **new AnonymousQueue()**.

### Vì sao Spring khuyến nghị AnonymousQueue?

Các bean **Queue**, **Binding** và listener thường được tạo và liên kết **trước** khi connection thực sự được mở tới broker. AnonymousQueue có tên ngay ở thời điểm wiring, nên các bean khác có thể tham chiếu tên đó. Khi mất connection, RabbitAdmin có thể dùng tên đã có trong object để khai báo lại. Nếu broker sinh tên, mỗi lần khai báo mới tên thường thay đổi và cần cập nhật nơi đang sử dụng.

## 2. Thuộc tính quyết định vòng đời

Một **AnonymousQueue** được tạo mặc định là **non-durable**, **exclusive** và **auto-delete**.

| Thuộc tính | Mặc định | Diễn giải |
| --- | --- | --- |
| **durable** | **false** | Queue không được giữ qua lần broker restart theo cơ chế durable |
| **exclusive** | **true** | Queue thuộc về **connection khai báo**; connection khác không được quyền dùng như queue chung; bị xóa khi connection khai báo không còn |
| **autoDelete** | **true** | Queue được tự xóa khi **consumer cuối cùng rời đi**, sau khi queue **đã từng có consumer** |
| **name** | Sinh tự động | Phân biệt queue tạm của từng instance/phiên |

**Exclusive và auto-delete là hai điều kiện khác nhau:**

- **exclusive=true**: nếu connection khai báo bị đóng hoặc broker xác định đã mất, broker xóa queue, kể cả queue chưa từng có consumer.
- **autoDelete=true**: sau khi queue đã từng có consumer, broker xóa nó khi consumer cuối cùng được cancel hoặc biến mất. Queue chỉ có auto-delete nhưng chưa từng có consumer không tự động bị xóa vì thuộc tính đó.
- **durable=false**: queue không tồn tại qua broker restart; dữ liệu trong queue cũng không được bảo vệ như mô hình queue durable.

**Connection khác channel:** AMQP connection là kết nối mạng logic đến broker, còn channel là phiên ở trong connection. Một connection có thể có nhiều channel và consumer. **Exclusive gắn với connection khai báo**, không đồng nghĩa chỉ có một consumer trong connection ấy. Nếu connection khác truy cập exclusive queue, broker có thể trả lỗi **RESOURCE_LOCKED**.

**Dừng listener không nhất thiết đóng connection.** Listener container có thể cancel consumer nhưng CachingConnectionFactory tiếp tục giữ connection dùng chung. Khi đó queue có thể bị xóa theo **autoDelete**, trong khi connection còn mở.

### Có cần x-expires?

**x-expires** là queue TTL: broker xóa queue sau thời gian không được sử dụng theo chính sách. Đây là một cơ chế độc lập với **exclusive** và **autoDelete**. **x-message-ttl** lại áp dụng cho message, không phải vòng đời queue. Không nên mặc định cho rằng mọi AnonymousQueue đều có **x-expires=60000**: đó không phải thuộc tính mặc định cần có của AnonymousQueue.

## 3. Vòng đời qua các mốc kết nối

~~~mermaid
flowchart TD
    A["Spring khởi tạo AnonymousQueue bean"] --> B["Sinh tên spring.gen-X"]
    B --> C["RabbitAdmin khai báo queue<br/>khi có connection"]
    C --> D["Listener consume message"]
    D --> E{"Sự kiện"}
    E -->|"Consumer cuối rời đi"| F["Auto-delete xóa queue"]
    E -->|"Connection khai báo mất"| G["Exclusive xóa queue"]
    E -->|"Broker restart"| H["Non-durable queue biến mất"]
    F --> I["Có thể khai báo lại nếu<br/>container/admin còn hoạt động"]
    G --> I
    H --> I
    I -->|"Kết nối và cấu hình hợp lệ"| C
~~~

Sơ đồ mô tả khả năng phục hồi khi RabbitAdmin và listener container được cấu hình phù hợp. Kết quả thực tế còn phụ thuộc quyền truy cập, cấu hình connection factory, trạng thái broker và thứ tự khởi tạo.

| Sự kiện | AnonymousQueue | Queue do broker sinh |
| --- | --- | --- |
| Khởi tạo ApplicationContext | Sinh tên ở Java | Tên chưa biết cho đến khi declare |
| RabbitAdmin declare | Queue trên broker được tạo theo tên đã biết | Broker trả tên mới |
| Dừng consumer cuối | Có thể bị auto-delete | Tương tự nếu autoDelete=true |
| Connection khai báo mất | Broker xóa vì exclusive | Tương tự nếu exclusive=true |
| Reconnect trong ApplicationContext còn sống | Có thể tạo lại với **cùng tên** | Thường được broker cấp **tên khác** |
| Restart cả ứng dụng | Bean mới sinh tên khác | Broker tạo tên mới |
| Queue đã bị xóa | Message đang nằm trong queue cũ cũng mất | Tương tự |

**Tái khai báo với cùng tên không đồng nghĩa khôi phục dữ liệu.** Sau khi queue exclusive cũ bị xóa, RabbitAdmin tạo **queue mới rỗng**. Những message đã mất cùng queue không được broker phục hồi chỉ vì tên trùng.

Ví dụ một tiến trình đang hoạt động:

~~~text
T0: Spring tạo bean, tên spring.gen-X
T1: RabbitAdmin khai báo spring.gen-X trên connection A
T2: Listener nhận sự kiện trên connection A
T3: Mạng đứt, broker phát hiện connection A biến mất
T4: Broker xóa queue spring.gen-X; message còn trong queue bị mất
T5: Connection B được lập, RabbitAdmin khai báo lại spring.gen-X
T6: Listener đăng ký lại, nhận các sự kiện mới
~~~

Nếu Java process restart giữa T4 và T5, ApplicationContext và bean tạo mới nên tên có thể khác.

## 4. Ví dụ ứng dụng: thông báo broadcast cho mỗi instance

Giả sử Notification Service có nhiều instance, và mỗi instance cần nhìn thấy **mọi** sự kiện **DashboardUpdated** trong lúc nó online. Mỗi instance nên sở hữu **một AnonymousQueue**, cùng bind vào một fanout exchange.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> X{"Fanout exchange<br/>dashboard.events"}
    X --> Q1[("spring.gen-A<br/>instance A")]
    X --> Q2[("spring.gen-B<br/>instance B")]
    X --> Q3[("spring.gen-C<br/>instance C")]
    Q1 --> C1["@RabbitListener A"]
    Q2 --> C2["@RabbitListener B"]
    Q3 --> C3["@RabbitListener C"]
~~~

Nếu ba instance nghe **cùng một queue**, mỗi message thường được giao cho **một** consumer đang cạnh tranh nhận việc; đó là mô hình **chia tải**, khác với **fan-out đến từng instance**.

### 4.1. Khai báo exchange, AnonymousQueue và binding

Ví dụ giả định dự án có dependency Spring AMQP/Boot tương ứng, cấu hình kết nối RabbitMQ và RabbitAdmin hỗ trợ auto-declaration.

~~~java
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class DashboardAmqpConfig {
    @Bean
    public FanoutExchange dashboardExchange() {
        return new FanoutExchange("dashboard.events", true, false);
    }

    @Bean
    public AnonymousQueue dashboardTemporaryQueue() {
        return new AnonymousQueue();
    }

    @Bean
    public Binding dashboardBinding(
            AnonymousQueue dashboardTemporaryQueue,
            FanoutExchange dashboardExchange) {
        return BindingBuilder.bind(dashboardTemporaryQueue)
                .to(dashboardExchange);
    }
}
~~~

Mỗi ApplicationContext tạo một object AnonymousQueue riêng, có tên khác nhau. **RabbitAdmin** khai báo queue và binding với tên đó. Fanout exchange định tuyến một bản sao message tới **mỗi queue đã bind**.

### 4.2. Consumer lắng nghe tên do Spring sinh

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class DashboardListener {
    @RabbitListener(queues = "#{dashboardTemporaryQueue.name}")
    public void onDashboardEvent(String eventJson) {
        System.out.println("Received: " + eventJson);
        // Nghiệp vụ thực tế: cập nhật dashboard / đẩy WebSocket.
    }
}
~~~

Biểu thức SpEL **#{dashboardTemporaryQueue.name}** tham chiếu thuộc tính **name** của bean. Viết **queues = "dashboardTemporaryQueue"** sẽ bị coi là **tên queue trên RabbitMQ**, không phải tên bean Spring.

### 4.3. Producer phát thông báo

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class DashboardPublisher {
    private final RabbitTemplate template;

    public DashboardPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String eventJson) {
        template.convertAndSend(
                "dashboard.events",
                "",   // Fanout exchange không cần routing key.
                eventJson);
    }
}
~~~

Producer chỉ cần biết **exchange**. Nó không cần biết queue ngẫu nhiên nào đang tồn tại. Instance khởi động muộn chỉ nhận message được route sau khi queue và binding của nó xuất hiện; **không có replay** các message gửi trước đó.

### 4.4. Quan sát bằng RabbitMQ Management

1. Chạy hai instance của ứng dụng, tìm hai queue tên **spring.gen-...** khác nhau trong RabbitMQ Management.
2. Kiểm tra cả hai queue đều bind với **dashboard.events**.
3. Publish một message; quan sát cả hai listener nhận cùng event.
4. Dừng một instance. Queue của instance đó sẽ bị xóa khi thỏa điều kiện auto-delete/exclusive.
5. Publish tiếp trong lúc một instance offline. Khởi động lại instance và xác minh event lúc offline **không tự xuất hiện lại**.

**Giới hạn nghiệp vụ:** Queue tạm phù hợp với live updates theo phiên. Đối với email, hóa đơn hoặc thanh toán cần xử lý dù consumer offline, hãy dùng queue durable đặt tên ổn định và cơ chế xác nhận/retry phù hợp.

## 5. Khi thực sự cần broker sinh tên

Để sử dụng **Queue("")** trong listener container Spring AMQP, phải tính tới việc **actualName thay đổi** khi connection mất và queue được khai báo lại.

### 5.1. Khai báo queue name rỗng

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerNamedQueueConfig {
    @Bean
    public Queue brokerNamedQueue() {
        return new Queue("", false, true, true);
    }
}
~~~

### 5.2. Container phải giữ object Queue

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BrokerNamedListenerConfig {
    @Bean
    public SimpleMessageListenerContainer brokerNamedListener(
            ConnectionFactory connectionFactory,
            @Qualifier("brokerNamedQueue") Queue queue) {

        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer(connectionFactory);

        container.setQueues(queue);
        container.setMessageListener(message -> {
            String text = new String(
                    message.getBody(), StandardCharsets.UTF_8);
            System.out.println("Received: " + text);
        });
        container.setMissingQueuesFatal(false);
        return container;
    }
}
~~~

**setQueues(queue)** cho container truy cập object được RabbitAdmin cập nhật **actualName**; chỉ truyền tên cũ qua **setQueueNames(...)** không đủ. **missingQueuesFatal(false)** giúp container tiếp tục phục hồi khi có race giữa việc xóa queue cũ, declare queue mới và listener khởi động lại.

**Không thêm broker-named queue vào container đang chạy.** Tạo topology và gắn object Queue trước khi start. Khi cần publish trực tiếp tới queue do broker sinh, phải lấy tên thực tế sau declare; với fanout/direct/topic exchange có thể dùng binding phù hợp để producer chỉ cần biết tên exchange/routing key ổn định.

Về thực hành, **Spring AMQP ưu tiên AnonymousQueue** để thuận lợi trong wiring bean và phục hồi theo tên hiện có. Tài liệu RabbitMQ khuyến khích server-named queue cho các exclusive queue tạo trực tiếp bằng AMQP client vì tránh tranh chấp tên cố định. Hai hướng tiếp cận xuất phát từ các lớp API khác nhau.

## 6. Những lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **RESOURCE_LOCKED** khi listener consume | Listener và RabbitAdmin sử dụng **hai connection khác nhau** cho cùng exclusive queue | Dùng cấu hình ConnectionFactory nhất quán, tránh khai báo qua publisher-only connection |
| **NOT_FOUND** khi listener khởi động | Queue đã auto-delete hoặc chưa được khai báo lại | Kiểm tra RabbitAdmin, listener startup và quyền declare |
| Queue broker-named đổi tên sau reconnect | Tên do broker sinh lại khi **queue.declare** | Dùng **setQueues(Queue)** và lấy **getActualName()** khi cần |
| Queue bị xóa khi consumer dừng dù connection vẫn còn | Queue có **autoDelete=true** và consumer cuối đã rời | Đây là hành vi vòng đời dự kiến; chọn queue khác nếu cần lưu backlog |
| Queue biến mất sau network outage | **exclusive=true** gắn queue với connection khai báo | Chấp nhận tính tạm thời hoặc chuyển sang queue durable |
| Message bị mất giữa lúc reconnect | Queue cũ bị xóa, queue mới chưa bind hoặc chưa tồn tại | Tránh queue tạm cho nghiệp vụ cần bảo đảm giao nhận |
| Nhiều instance chỉ một instance nhận mỗi message | Nhiều consumer cùng chia sẻ **một** queue | Mỗi instance tự có queue/binding riêng nếu cần broadcast |
| Cấu hình **x-expires** và tưởng message được giữ lâu | Nhầm queue TTL với message TTL | Chọn chính sách lưu trữ và loại queue theo yêu cầu |

### ConnectionFactory, RabbitAdmin và listener phải phối hợp

Với Spring AMQP, RabbitAdmin thường tự khai báo tài nguyên lúc connection mở, và có thể khai báo lại khi connection được thiết lập lại. Cơ chế này thường gắn với **CachingConnectionFactory ở cache mode CHANNEL**. Nếu RabbitAdmin khai báo exclusive queue bằng **connection A**, nhưng listener dùng **connection B**, broker từ chối truy cập dù tên hoàn toàn chính xác.

Không cấu hình RabbitAdmin để khai báo exclusive queue trên một **publisher connection** tách riêng rồi mong listener connection khác consume được. Khi có nhiều ConnectionFactory hoặc vhost, cần xác định rõ broker, quyền, connection quản lý queue và listener.

### Không hiểu auto-delete là chiến lược đảm bảo giao nhận

Queue bị xóa thì message đang nằm trong queue cũng có thể mất. Publisher confirm chỉ báo broker đã xử lý thao tác publish theo cơ chế xác nhận; nó **không hứa** queue tạm sẽ còn tồn tại khi consumer kết nối trở lại. Với nghiệp vụ quan trọng:

- Dùng **queue durable, non-exclusive, non-auto-delete** cho backlog cần giữ qua restart.
- Cấu hình persistence, publisher confirms/returns, acknowledgement của consumer, retry giới hạn và dead-letter khi cần.
- Thiết kế **idempotency** vì consumer vẫn có thể nhận lại message khi sự cố xảy ra trước ACK.
- Cân nhắc **transactional outbox** khi cần phát event nhất quán với commit vào database.

## 7. Chọn loại queue theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Một bản sao thông báo **cho từng instance đang online** | **AnonymousQueue mỗi instance + fanout exchange** | Broadcast và tự dọn tài nguyên theo phiên |
| Queue hồi đáp riêng cho phiên request/reply | Queue tạm hoặc **amq.rabbitmq.reply-to** tùy mô hình RPC | Giảm xung đột tên, không cần giữ dữ liệu dài hạn |
| Cần chính RabbitMQ đặt tên | **Queue("") + RabbitAdmin** | Có tên do broker sinh; cần quản lý actualName |
| Nhiều worker cùng nhận job trong một backlog | **Queue durable đặt tên cố định**, nhiều consumer | Chia tải; job vẫn chờ khi worker rời |
| Event cho hóa đơn/thanh toán phải được xử lý khi service offline | **Queue durable** với retry và DLQ | Tránh mất sự kiện khi connection đóng |
| Lịch sử event cần replay theo offset | **RabbitMQ Streams** | Khác queue tạm; có log, retention và offset |

## 8. Bài tập thực hành

1. **Nguồn gốc tên:** Khởi tạo AnonymousQueue và in **getName()** trước khi broker chạy. Sau khi kết nối broker, gọi RabbitAdmin.declareQueue với **new Queue("", false, true, true)** rồi so sánh tên trả về và **getActualName()**.
2. **Vòng đời consumer:** Chạy ví dụ mục 4. Dừng consumer cuối mà vẫn giữ connection; quan sát queue tự xóa. Sau đó bật listener lại và kiểm tra nó có được khai báo lại hay không.
3. **Vòng đời connection:** Cắt connection, quan sát queue bị xóa theo exclusive, đợi hệ thống phục hồi và so sánh tên. Thử lại sau khi restart cả tiến trình Java.
4. **Mở rộng nhiều instance:** Chạy ba instance cùng bind fanout exchange, phát 10 event. Đếm số lần nhận ở mỗi instance rồi chuyển sang dùng một queue cố định chung để so sánh.
5. **Tình huống thật:** Payment Service phát **PaymentCompleted**, Invoice Service offline 20 phút nhưng bắt buộc nhận event. Giải thích vì sao AnonymousQueue không phù hợp và thiết kế lại bằng queue durable, publisher confirm, retry, DLQ và idempotency.

**Câu hỏi tự đánh giá:** Vì sao AnonymousQueue có thể biết tên trước khi kết nối? Khi nào autoDelete kích hoạt? Exclusive gắn với channel hay connection? Vì sao reconnect dùng lại tên spring.gen-... không có nghĩa message cũ tồn tại? Vì sao broker-named queue nên dùng **setQueues(Queue)** thay vì truyền tên dạng String?

## 9. Tài liệu tham khảo

- [Spring AMQP — Configuring the Broker](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html): AnonymousQueue, naming strategy, RabbitAdmin và queue do broker đặt tên.
- [Spring AMQP — Containers and Broker-Named Queues](https://docs.spring.io/spring-amqp/reference/amqp/containers-and-broker-named-queues.html): actualName, setQueues và missingQueuesFatal.
- [Spring AMQP — Resilience and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): cơ chế auto-declaration khi mất rồi lập lại connection.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): server-named, exclusive, auto-delete và hành vi queue tạm.
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl): queue TTL so với message TTL.

---

**Ghi nhớ:** **AnonymousQueue** do Spring sinh tên, mặc định **non-durable + exclusive + auto-delete**; **Queue("")** yêu cầu RabbitMQ broker sinh tên. Exclusive gắn với connection, auto-delete phụ thuộc consumer cuối rời queue sau khi queue từng được consume. RabbitAdmin có thể khai báo lại sau reconnect, nhưng **không khôi phục message đã mất cùng queue cũ**. Queue tạm phù hợp với sự kiện theo phiên; nghiệp vụ phải nhận dù offline cần queue bền vững và cơ chế reliability thích hợp.
