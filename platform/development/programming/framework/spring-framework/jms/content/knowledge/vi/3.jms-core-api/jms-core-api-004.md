# Destination, Queue và Topic trong API JMS

> **Module:** Spring Framework – JMS  
> **Nhóm kiến thức:** API JMS cốt lõi  
> **Bài học:** Destination, Queue và Topic trong API

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `Destination` là kiểu địa chỉ chung trong Jakarta Messaging, còn `Queue` và `Topic` quyết định cách message được phân phối.
2. Nhận biết các giao diện `jakarta.jms.Destination`, `Queue`, `Topic`, `TemporaryQueue` và `TemporaryTopic`; dùng đúng chúng trong `JMSContext` hoặc `Session`.
3. Phân biệt tạo **đối tượng Destination** bằng API với **tạo tài nguyên vật lý trên broker**; biết khi nào dùng JNDI, broker administration hoặc cơ chế cấp phát động của provider.
4. Dự đoán cách nhiều consumer nhận message từ queue so với nhiều subscription trên topic, kể cả khi consumer offline, selector, acknowledgment và redelivery.
5. Chọn queue/topic phù hợp cho yêu cầu nghiệp vụ, gửi/nhận bằng API gốc và cấu hình Spring JMS sao cho producer, listener cùng dùng đúng loại destination.
6. Hiểu `JMSReplyTo`, temporary destination, lifecycle và các lỗi cấu hình phổ biến như gửi sang queue trong khi listener đang đăng ký topic cùng tên.

## 1. Destination là gì?

Trong Jakarta Messaging (tên quen thuộc trước đây: JMS), ứng dụng gửi message **đến một destination** và tạo consumer **trên một destination**. `Destination` biểu diễn địa chỉ logic mà message broker/JMS provider hiểu, giúp mã ứng dụng không phải biết chi tiết kết nối đến từng consumer.

```text
                         Jakarta Messaging API
                                 |
                +----------------+----------------+
                |                                 |
           Producer                          Consumer
                |                                 ^
                v                                 |
          Destination ----------------------------+
            /       \
           /         \
        Queue        Topic
          |             |
     worker group   subscriptions
```

Ví dụ, Order Service có thể gửi `OrderCreated` đến destination tên `orders.events`. Nó không cần biết máy chủ của Analytics Service hay Audit Service; provider nhận message và chuyển giao theo loại destination, subscription và cấu hình.

**Điểm quan trọng:** `Destination` chỉ là **giao diện địa chỉ**. Nó không tự nói “gửi broadcast” hay “gửi một lần”; queue/topic và trạng thái subscription mới quy định cách phân phối. Nó cũng không phải biến kiểu Java lưu tất cả message trong bộ nhớ của producer.

Trong Jakarta Messaging 3.1, quan hệ kiểu:

```java
public interface Destination { /* địa chỉ chung */ }

public interface Queue extends Destination {
    String getQueueName() throws JMSException;
}

public interface Topic extends Destination {
    String getTopicName() throws JMSException;
}

public interface TemporaryQueue extends Queue {
    void delete() throws JMSException;
}

public interface TemporaryTopic extends Topic {
    void delete() throws JMSException;
}
```

Đoạn trên là **phác họa cấu trúc** của các giao diện chuẩn để giải thích quan hệ kế thừa, không phải tệp nguồn cần tự tạo trong project. Trong ứng dụng thực, import `jakarta.jms.*` từ dependency Jakarta Messaging.

### Những điều Destination không quy định

- Không có cú pháp địa chỉ thống nhất trên mọi broker. Chuỗi `"orders.events"` là **tên do ứng dụng và provider thỏa thuận**, không phải một URL JMS chuẩn chung.
- Giao diện `Destination` không có phương thức chung `getName()`; chỉ subtype `Queue` có `getQueueName()`, `Topic` có `getTopicName()`.
- Mã Java tạo đối tượng `Queue`/`Topic` không tự bảo đảm broker đã tạo vật thể tương ứng, cấp quyền, persistence hoặc binding.
- Sử dụng chung một **tên chuỗi** không làm queue và topic trở thành cùng một destination. Broker có thể cho phép hai loại đích cùng tên nhưng semantics khác, tùy provider.

`Destination` là một **administered object** trong cách triển khai truyền thống của JMS: nhà quản trị cấu hình destination và ứng dụng có thể lấy reference qua JNDI. Để tiện, API hiện đại cũng cho phép tạo đối tượng địa chỉ bằng tên provider-specific ngay trong code.

## 2. Queue trong API — Point-to-point

`jakarta.jms.Queue` đại diện cho destination theo mô hình **point-to-point**. Một message trong queue được chuyển đến **một consumer** đủ điều kiện cho mỗi lần giao. Nhiều consumer cùng queue thường là nhóm worker cạnh tranh nhận công việc.

```text
       Producer 1 -----\
                        \
       Producer 2 -------> [ Queue: invoice.generate ]
                                     |             |
                                  Worker A     Worker B
                                     \             /
                           các message được chia công việc
```

Nếu có ba đơn vị công việc `J1`, `J2`, `J3` và hai worker, mỗi message được đưa cho một worker theo cơ chế phân phối của provider. JMS **không bắt buộc** broker chia theo vòng tròn hay bằng nhau tuyệt đối. Worker nào nhận message nào còn tùy tốc độ, selector, priority, trạng thái kết nối và broker.

### Khi có hai consumer cùng queue

```text
[orders.work]
  M1 --> Consumer A (hoặc B)
  M2 --> Consumer B (hoặc A)
  M3 --> Consumer A (hoặc B)
```

**Không hiểu “một consumer” là “nghiệp vụ chạy chính xác một lần”.** Nếu consumer xử lý rồi lỗi trước khi acknowledgment/commit, provider có thể giao lại message (có thể cho worker khác). Ứng dụng cần idempotency khi tác dụng phụ như trừ tiền, gửi email hoặc cập nhật database không được nhân đôi.

Nếu consumer tắt, message có thể ở lại queue để consumer quay lại nhận, nhưng thời gian giữ và hậu quả khi đầy queue phụ thuộc `PERSISTENT`/`NON_PERSISTENT`, TTL, transaction và chính sách provider. Không suy ra message được lưu vĩnh viễn chỉ vì destination là queue.

### Message selector trên queue

Một consumer có thể tạo selector, ví dụ:

```java
JMSConsumer vipConsumer = context.createConsumer(
        queue, "priorityGroup = 'VIP'");
```

`priorityGroup` ở đây là property do ứng dụng đặt, không phải header tiêu chuẩn. Consumer này chỉ đủ điều kiện nhận message khớp biểu thức. Message không khớp selector có thể được consumer khác nhận hoặc vẫn nằm trong queue. Điều này không đồng nghĩa queue tự tạo một bản sao cho mỗi selector.

Queue phù hợp khi nhiệm vụ cần **một nhóm worker thực hiện một lần thành công**: gửi email, chuyển mã video, tạo hóa đơn, gọi hệ thống vận chuyển, thực hiện job nền.

## 3. Topic trong API — Publish/subscribe

`jakarta.jms.Topic` đại diện cho destination **publish/subscribe**. Producer publish message vào topic; **mỗi subscription độc lập** đang đủ điều kiện có thể nhận một bản sao message đó.

```text
                 Producer
                    |
                    v
          [ Topic: orders.events ]
                /         \
               /           \
    Subscription A      Subscription B
       Analytics             Audit
          |                   |
      Consumer A          Consumer B
```

Nếu Analytics và Audit là **hai subscription độc lập**, một `OrderCreated` có thể được xử lý bởi cả hai. Việc Audit xác nhận đã nhận **không** xác nhận giúp Analytics, vì chúng có phần message chờ và ranh giới xử lý riêng.

**Phân biệt subscriber với instance consumer.** Khi một nhóm triển khai *shared subscription*, nhiều consumer instance có thể chia message của **cùng một subscription**; khi đó một message dành cho subscription đó chỉ cần một instance xử lý, thay vì cả nhóm cùng nhận. Còn hai subscription độc lập thường dùng để fan-out đến hai trách nhiệm nghiệp vụ.

### Non-durable và durable subscription

- **Non-durable:** thông thường chỉ tồn tại khi có consumer đang hoạt động; nếu subscription không còn và event mới được publish, consumer khởi động lại không được JMS tự phát lại lịch sử bị bỏ lỡ.
- **Durable:** subscription có danh tính bền vững và được provider giữ khi consumer tạm offline. Khi quay lại đúng identity, consumer có thể nhận message còn chờ theo delivery mode, TTL, selector và chính sách lưu giữ của broker.

`PERSISTENT` ở producer **không thay thế durable subscription**. Nếu consumer dùng non-durable subscription đã biến mất, publish `PERSISTENT` không tạo một subscription cho consumer offline. Ngược lại durable subscription không miễn trừ các điều kiện mất message khi dùng `NON_PERSISTENT` hoặc TTL quá ngắn.

### Một topic không tự biến thành “stream lịch sử có replay”

Một subscription mới thường nhận những message được publish **từ lúc subscription đó tồn tại**. JMS không hứa tự phát lại toàn bộ lịch sử topic từ trước khi subscription được tạo. Nếu ứng dụng cần đọc lại sự kiện từ nhiều tháng trước theo offset, hãy thiết kế kho lưu lịch sử hoặc dùng công nghệ có hợp đồng event log phù hợp; không ngầm gán khả năng này cho Topic.

Topic hợp lý khi một sự kiện cần nhiều nhóm quan tâm cùng xử lý: đơn đã tạo được Audit, Analytics và Notification sử dụng độc lập; một cập nhật giá được gửi cho nhiều hệ thống quan sát.

## 4. Bảng so sánh Queue và Topic chính xác theo API

| Đặc điểm | `Queue` | `Topic` |
| --- | --- | --- |
| Mô hình | Point-to-point | Publish/subscribe |
| Đối tượng Java | `jakarta.jms.Queue` | `jakarta.jms.Topic` |
| Một message đến bao nhiêu bên? | Một consumer đủ điều kiện **trong mỗi lần giao**; redelivery vẫn có thể xảy ra | Một bản sao cho **mỗi subscription độc lập** đủ điều kiện |
| Nhiều instance | Thường cạnh tranh và chia tải trên queue | Khác subscription thì mỗi nhóm nhận; cùng shared subscription thì chia tải |
| Khi mọi consumer tắt | Queue có thể giữ công việc chờ theo policy và mode | Non-durable có thể bỏ lỡ; durable có thể giữ backlog cho subscription đã tồn tại |
| Tạo đối tượng địa chỉ | `context.createQueue(name)` | `context.createTopic(name)` |
| Truy cập tên | `queue.getQueueName()` | `topic.getTopicName()` |
| Bài toán phù hợp | Job cần một người xử lý | Event nhiều hệ thống cần biết |
| Điều không được hứa | Chính xác một lần nghiệp vụ, FIFO toàn hệ thống, lưu vô hạn | Mọi consumer luôn online, có lịch sử để replay, mọi subscription là durable |

**Lựa chọn theo hợp đồng nghiệp vụ:**

- “Tạo một hóa đơn PDF, tăng worker khi tải tăng” → thường là **queue**.
- “Thông báo rằng hóa đơn đã tạo để kế toán, báo cáo và kiểm toán đều phản ứng” → thường là **topic với nhiều subscription**.
- “Mỗi vùng triển khai phải nhận một bản sao, trong mỗi vùng có 3 worker chia tải” → **mỗi vùng có một shared subscription riêng**, không chỉ đặt tất cả worker trong một subscription toàn hệ thống.
- “Cần một kết quả ngay trong HTTP request” → có thể chọn xử lý đồng bộ; JMS queue/topic không tự làm thay đổi yêu cầu thời gian phản hồi.

## 5. API gốc: tạo và dùng Destination như thế nào?

Java hiện đại có hai phong cách JMS thường gặp:

1. **Simplified API:** `ConnectionFactory.createContext(...)` trả `JMSContext`; dùng `JMSProducer` và `JMSConsumer`, thường ít boilerplate hơn.
2. **Classic API:** `ConnectionFactory.createConnection()`, `Connection.createSession(...)`, `Session.createProducer(...)` / `createConsumer(...)`; vẫn phổ biến và có trong thư viện tích hợp.

Spring JMS bọc các thao tác này bằng `JmsTemplate` và listener container, nhưng hiểu API gốc giúp đọc log, cấu hình và xử lý lỗi chính xác.

### 5.1. Tạo đối tượng Queue/Topic bằng JMSContext

Giả sử đã có một `jakarta.jms.ConnectionFactory` hợp lệ từ provider:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public class DestinationHandles {
    private final ConnectionFactory connectionFactory;

    public DestinationHandles(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void inspectDestinationNames() throws Exception {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("orders.work");
            Topic topic = context.createTopic("orders.events");

            System.out.println("Queue name: " + queue.getQueueName());
            System.out.println("Topic name: " + topic.getTopicName());
        }
    }
}
```

**Đây là class dùng trong một project có JMS provider, không phải chương trình chạy độc lập bằng `javac`.** Nó chỉ tạo các object handle theo tên và in tên do provider trả về; kết quả log phụ thuộc provider. Sự tồn tại của object `queue` không chứng minh đã có broker-side queue thật hoặc đầy đủ quyền truy cập.

Đặc tả Jakarta Messaging ghi rõ `JMSContext.createQueue(String)` và `createTopic(String)` chỉ tạo object đại diện cho **tên provider-specific**. API **không chuẩn hóa thao tác tạo physical destination lâu dài**. Một số broker tự tạo destination ở lần sử dụng đầu tiên, nhưng đó là tính năng/chính sách riêng của provider.

### 5.2. Producer và consumer nhận tham số Destination

Ví dụ đơn giản với queue:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Queue;

public class QueueApiExample {
    private final ConnectionFactory connectionFactory;

    public QueueApiExample(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String sendThenReceive() {
        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = context.createQueue("orders.work");
            JMSConsumer consumer = context.createConsumer(queue);

            context.createProducer().send(queue, "ORD-42");
            return consumer.receiveBody(String.class, 3_000L);
        }
    }
}
```

Khi broker hoạt động, destination tồn tại/được auto-create, không có worker khác cạnh tranh nhận, thao tác gửi thành công và consumer nhận kịp, phương thức có thể trả `"ORD-42"`.

Nhưng **không được xem đây là output chắc chắn**: nếu timeout 3 giây hoặc lỗi kết nối, `receiveBody(...)` có thể trả `null`/ném ngoại lệ. Trong thực tế producer và consumer thường là **hai tiến trình khác nhau**, và xử lý tại consumer cần transaction, retry, logging và idempotency thích hợp.

Các thành phần cần hiểu:

- `context.createQueue(name)` → tạo object `Queue`.
- `context.createConsumer(queue)` → đăng ký consumer với provider trên queue.
- `context.createProducer().send(queue, "ORD-42")` → gửi message tới destination.
- `receiveBody(String.class, timeout)` → nhận body theo kiểu được yêu cầu hoặc `null` khi hết thời gian chờ; có thể lỗi nếu body không chuyển được sang kiểu đó.
- `try (JMSContext ...)` → giải phóng tài nguyên context khi xong.

**Lưu ý sequencing:** khi tạo `JMSConsumer`, `JMSContext` mặc định tự bắt đầu connection để nhận nếu `autoStart` chưa bị tắt. Đây là lý do mẫu có thể thực hiện receive mà không gọi `context.start()` bằng tay.

### 5.3. Gửi/nhận trên Topic với JMSContext

```java
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Topic;

Topic topic = context.createTopic("orders.events");
JMSConsumer audit = context.createConsumer(topic);
JMSConsumer analytics = context.createConsumer(topic);

// Hai non-durable subscription đã được tạo trước khi publish.
context.createProducer().send(topic, "OrderCreated: ORD-42");

String auditEvent = audit.receiveBody(String.class, 3_000L);
String analyticsEvent = analytics.receiveBody(String.class, 3_000L);
```

Đây là **đoạn code minh họa nằm trong scope đã có `JMSContext context`** và provider hoạt động, không phải file Java standalone. Hai consumer này đăng ký **hai subscription non-durable độc lập** trên cùng topic. Nếu cả hai còn active và broker xử lý bình thường, mỗi consumer có thể nhận một bản sao; nếu tạo consumer **sau** khi publish, đừng kỳ vọng nó nhận hồi tố event.

`createConsumer(topic)` mặc định tạo non-durable subscription. Muốn durable, dùng API tương ứng như `createDurableConsumer(topic, subscriptionName)` với client identity cấu hình thích hợp; shared durable cần `createSharedDurableConsumer(...)` và provider có hỗ trợ. Tên subscription và client ID phải ổn định để nối lại backlog.

### 5.4. Classic API và việc dùng Destination chung

```java
// Giả định session là jakarta.jms.Session đã tạo từ Connection.
Destination target = session.createQueue("orders.work");
MessageProducer producer = session.createProducer(target);
MessageConsumer consumer = session.createConsumer(target);

producer.send(session.createTextMessage("ORD-42"));
```

API chung nhận tham số `Destination`, nên logic mức cao có thể nhận một biến `Destination` thay vì biết toàn bộ provider-specific queue/topic. **Nhưng ứng dụng vẫn phải hiểu ngữ nghĩa của subtype**. Dùng một biến `Destination` không giúp chuyển đổi queue thành topic hoặc tạo broadcast khi gửi.

Trong classic API, có thể tạo `MessageProducer` không gắn destination (`session.createProducer(null)`) và truyền `Destination` ở từng lần `send(destination, message)`. Trường hợp này hữu ích với reply destination thay đổi theo request. Trong simplified API, `JMSProducer.send(destination, ...)` luôn cần destination ở lần gửi.

### 5.5. Xem loại đích ở runtime

```java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public static String destinationKind(Destination destination) {
    if (destination instanceof Queue) {
        return "QUEUE";
    }
    if (destination instanceof Topic) {
        return "TOPIC";
    }
    return "UNKNOWN";
}
```

Hàm nhận một object `Destination` do provider tạo, sau đó kiểm tra subtype. Vì `TemporaryQueue extends Queue` và `TemporaryTopic extends Topic`, chúng được phân loại tương ứng. Đây **không phải phép kiểm tra xem physical destination còn tồn tại trong broker**; nó chỉ đọc kiểu object Java.

Có thể đọc header `message.getJMSDestination()` để biết destination producer gửi đến theo thông tin provider ghi nhận. `JMSReplyTo` là một field khác, chỉ địa chỉ nơi gửi câu trả lời, **không phải** chính destination inbound.

## 6. Administered destination, JNDI và dynamic destination

Đây là chỗ nhiều ứng dụng “chạy local thì được, lên production thì lỗi”.

### 6.1. Destination object không phải tài nguyên vật lý

```text
Java client                               JMS provider/broker
----------                                -------------------
context.createQueue("billing.work")  -->  object Queue(name="billing.work")
                                          (chưa bảo đảm queue thật tồn tại)

producer.send(queue, msg)             -->  provider tìm/kiểm tra destination
                                          -> dùng nếu đã có
                                          -> có thể auto-create nếu cho phép
                                          -> hoặc báo InvalidDestination / quyền
```

**Tài nguyên vật lý** thường có những thuộc tính không được `Destination` interface chuẩn diễn đạt hết: số consumer tối đa, address routing, persistence, quota, storage, security policy, dead-letter policy, auto-delete, retention, cluster topology.

JMS không có một API portable để tạo và quản trị toàn bộ các loại tài nguyên này. Mỗi broker có CLI, API quản trị, cấu hình hoặc console riêng. Vì vậy, tài nguyên quan trọng trong production thường được **định nghĩa và quản lý rõ ràng theo provider**.

### 6.2. JNDI: tra cứu object đã cấu hình

Trong JMS truyền thống, `ConnectionFactory` và `Destination` có thể là administered objects lưu trong JNDI:

```java
// Minh họa: JNDI phải được cấu hình sẵn phù hợp môi trường.
javax.naming.Context naming = new javax.naming.InitialContext();
jakarta.jms.Queue queue =
        (jakarta.jms.Queue) naming.lookup("jms/queue/OrdersWork");
```

`javax.naming` ở đây thuộc **Java Naming and Directory Interface của JDK**, hoàn toàn bình thường ngay cả khi JMS dùng `jakarta.jms`. Không nhầm `javax.naming` với phiên bản `javax.jms` cũ.

Tên `"jms/queue/OrdersWork"` là **tên binding JNDI do môi trường triển khai quy định**, không nhất thiết là tên vật lý mà broker sử dụng. Spring có thể inject administered destination qua JNDI. Mô hình này thuận tiện khi cấu hình vật lý, permission và đường dẫn được quản trị độc lập với source code.

### 6.3. Dynamic destination resolution

Spring `JmsTemplate` nhận cả `Destination` object lẫn tên destination dạng `String`. Khi nhận `String`, Spring phải dùng `DestinationResolver` để chuyển nó thành object theo đúng miền queue/topic.

- `DynamicDestinationResolver` là chiến lược thường dùng mặc định và gọi API tạo object `Queue`/`Topic` từ tên.
- `JndiDestinationResolver` tra cứu object trong JNDI; tùy cấu hình có thể fallback sang dynamic.
- Provider có thể tự tạo physical destination khi được tham chiếu hoặc được sử dụng, **nhưng đó không phải bảo đảm phổ quát của JMS**.

```text
"orders.work" (String)
        |
        v
DestinationResolver.resolveDestinationName(
    session, "orders.work", pubSubDomain=false)
        |
        v
Queue handle -> broker provider
```

Nếu `pubSubDomain=true`, resolver tìm/tạo `Topic` handle. Vì vậy cùng một tên `"orders.events"` có thể dẫn đến Queue hoặc Topic tùy cấu hình Spring. Cần xem kiểu destination, không chỉ xem chuỗi.

## 7. Spring JMS: dùng đúng Queue và Topic

Spring Framework 6+ dựa trên `jakarta.jms`. `JmsTemplate` giải phóng ứng dụng khỏi phần lớn boilerplate gửi nhận, còn `@JmsListener` + container factory quản lý listener. **Cả producer và consumer phải trỏ cùng loại destination đã thiết kế**.

### 7.1. Một ứng dụng Spring có cả queue và topic

Giả định project Spring có `spring-jms`, đã cấu hình `jakarta.jms.ConnectionFactory` đến một JMS provider thật và có hai destination hợp lệ: queue `orders.work`, topic `orders.events`. Ví dụ gồm **nhiều file trong cùng một Spring project**, sử dụng Java 17+, không thể biên dịch riêng từng file chỉ với JDK.

**File `JmsDestinationConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsDestinationConfig {

    @Bean("queueTemplate")
    public JmsTemplate queueTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // Tên String được resolve thành Queue
        return template;
    }

    @Bean("topicTemplate")
    public JmsTemplate topicTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);  // Tên String được resolve thành Topic
        return template;
    }

    @Bean("queueListenerFactory")
    public DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicListenerFactory")
    public DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Trong Spring, `setPubSubDomain(false)` là lựa chọn queue; `true` là topic. Mặc định của `JmsTemplate` trong trường hợp resolve String thường là queue, vì vậy **không được quên bật topic khi cần pub/sub**.

**File `OrderPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;

    public OrderPublisher(
            @Qualifier("queueTemplate") JmsTemplate queueTemplate,
            @Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
    }

    public void requestFulfillment(String orderId) {
        queueTemplate.convertAndSend("orders.work", orderId);
    }

    public void publishCreatedEvent(String orderId) {
        topicTemplate.convertAndSend("orders.events", orderId);
    }
}
```

Một `String` là payload ví dụ nên `SimpleMessageConverter` thông thường chuyển thành `TextMessage`. Khi dùng DTO/JSON/protobuf thực tế, cần thiết kế message converter và schema; cách chọn Queue/Topic **độc lập** với kiểu body.

**File `FulfillmentWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FulfillmentWorker {

    @JmsListener(
            destination = "orders.work",
            containerFactory = "queueListenerFactory")
    public void handleWork(String orderId) {
        System.out.println("Fulfillment: " + orderId);
    }
}
```

Nếu triển khai nhiều instance của `FulfillmentWorker` cùng queue, chúng cạnh tranh nhận các công việc; một message thường đến một worker trong mỗi lần giao. Lỗi xử lý có thể dẫn đến redelivery theo transaction và cấu hình provider.

**File `OrderAuditSubscriber.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditSubscriber {

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void recordEvent(String orderId) {
        System.out.println("Audit: " + orderId);
    }
}
```

**File `OrderMetricsSubscriber.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMetricsSubscriber {

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void updateMetrics(String orderId) {
        System.out.println("Metrics: " + orderId);
    }
}
```

Khi hai listener topic đã được khởi tạo và đều online **trước** khi `publishCreatedEvent("ORD-42")` được gọi, cả Audit và Metrics có thể nhận event tương ứng. Thứ tự hai dòng log không được bảo đảm. Với queue, lần gửi `requestFulfillment("ORD-42")` có thể tạo log:

```text
Fulfillment: ORD-42
```

Với topic, log minh họa (có thể đảo thứ tự):

```text
Audit: ORD-42
Metrics: ORD-42
```

Đây là **output có điều kiện**, không phải stdout bắt buộc của mọi lần chạy. Broker cần hoạt động, listener cần đăng ký đúng, message chưa hết hạn, delivery/transaction không lỗi và không có subscriber nào bị offline tại thời điểm publish. Hai listener topic ở ví dụ này là **non-durable** theo cấu hình hiện tại; nếu muốn nhận lại event sau khi offline, phải cấu hình durable/shared subscription có danh tính thích hợp.

### 7.2. Gửi với Destination object có sẵn

Ngoài chuỗi tên:

```java
// queue là jakarta.jms.Queue đã được provider/JNDI cung cấp.
queueTemplate.convertAndSend(queue, "ORD-42");
```

Khi truyền **Destination object**, Spring dùng object đó trực tiếp. `pubSubDomain` chủ yếu cần thiết khi Spring phải **resolve String** thành queue hay topic, chứ không phải phép chuyển `Queue` thành `Topic` trên một object đã có. Nếu truyền nhầm object `Topic` vào logic muốn queue, việc đổi tên hay bật flag không sửa bản chất đích.

### 7.3. Cấu hình bền vững cho topic listener

Ví dụ phía trên không có durable subscription. Nếu một subscription kiểm toán phải tích lũy event khi ứng dụng tắt, có thể tạo factory chuyên dụng:

```java
@Bean("durableAuditFactory")
public DefaultJmsListenerContainerFactory durableAuditFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("audit-service");
    factory.setSessionTransacted(true);
    factory.setConcurrency("1"); // Unshared durable: chỉ một consumer active
    return factory;
}
```

```java
@JmsListener(
        destination = "orders.events",
        subscription = "audit-orders-v1",
        containerFactory = "durableAuditFactory")
public void recordDurableEvent(String orderId) {
    // Xử lý event và kiểm tra idempotency theo eventId.
}
```

Hai đoạn là **mảnh cấu hình minh họa trong project Spring**, cần import các type như ví dụ trước, không phải file chạy độc lập. Durable unshared subscription dựa vào danh tính client/subscription ổn định; không chạy đồng thời nhiều instance dùng cùng client ID như thể đó là hàng đợi chia tải. Với multi-instance, phải nghiên cứu shared durable, identity, selectors và hỗ trợ cụ thể của provider.

Producer vẫn cần chọn delivery mode, TTL và transaction đúng yêu cầu; durable subscription không tự bảo đảm “exactly once” hoặc giữ message vô hạn.

### 7.4. Nhận diện lỗi Queue/Topic mismatched

Triệu chứng thường gặp: producer log “send OK” nhưng `@JmsListener` không nhận.

Kiểm tra:

1. Producer gửi bằng `JmsTemplate` nào? `pubSubDomain` có đúng với ý định không?
2. Listener dùng `containerFactory` nào? `setPubSubDomain(...)` có cùng loại đích không?
3. Resolver đang dùng `DynamicDestinationResolver`, JNDI hay custom strategy?
4. Broker có queue/topic thật, routing type và permission phù hợp không?
5. Đúng tên **theo provider**, namespace/vhost/address và môi trường không?
6. Với topic, subscription tồn tại **trước** publish hay chưa; durable có dùng đúng `clientId` và `subscription` không?
7. Message có selector, TTL, priority, delivery mode hay trạng thái transaction nào khiến không được giao?
8. Consumer đang receive, bị retry/backoff hay đã đi DLQ theo broker policy?

Tạo cùng tên `"orders.events"` ở hai phía không đủ chứng minh chúng là cùng loại destination.

## 8. TemporaryQueue và TemporaryTopic

Jakarta Messaging cung cấp subtype của destination có vòng đời gắn với **connection**:

- `TemporaryQueue extends Queue`.
- `TemporaryTopic extends Topic`.

Chúng được hệ thống/provider cấp phát danh tính duy nhất khi gọi `Session.createTemporaryQueue()`/`createTemporaryTopic()` hoặc API tương đương của `JMSContext`. Khác với `createQueue(String)`, các phương thức temporary này thực sự yêu cầu provider tạo temporary destination.

**Chỉ connection tạo temporary destination mới được tạo consumer trên đó.** Producer thuộc connection khác có thể gửi trả vào temporary destination nếu có reference phù hợp; rất hữu ích cho mẫu request/reply.

```text
Service A                                    Service B
    |                                            ^
    | create TemporaryQueue (replyTo)             |
    |                                            |
    +---- request (JMSReplyTo=temporaryQueue) ---->|
    |                                            |
    |<----------- reply to temporaryQueue --------+
    |
  consume reply on owning connection
```

Ví dụ phần request ở một context đã có:

```java
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;

TemporaryQueue replyQueue = context.createTemporaryQueue();
Queue requests = context.createQueue("reports.request");

TextMessage request = context.createTextMessage("report-42");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("request-42");

context.createProducer().send(requests, request);

// Consumer dùng cùng connection/context tạo replyQueue.
String reply = context.createConsumer(replyQueue)
        .receiveBody(String.class, 5_000L);
```

**Đây là mảnh API minh họa**, không chạy độc lập: cần provider, consumer xử lý `reports.request`, giải thích rõ correlation và thời điểm gửi reply. Nếu không có responder hoặc reply đến muộn, `reply` có thể là `null`. Responder cần gửi reply vào destination trong `getJMSReplyTo()` của request và đặt `JMSCorrelationID` theo hợp đồng giữa hai hệ thống.

Temporary destination bị xóa khi connection đóng (hoặc `delete()` sớm khi hợp lệ); **không dùng nó làm địa chỉ cố định** cho job tồn tại qua nhiều phiên ứng dụng. Nó cũng không thay thế một queue có lưu giữ bền vững cho các bước nghiệp vụ kéo dài.

## 9. Message header và Destination có vai trò khác nhau

Có ba địa chỉ cần phân biệt:

- **Đích gửi thật:** object `Destination` truyền cho `send(...)` hay tên đã resolve bởi `JmsTemplate`.
- **`JMSDestination`:** header do provider gán thể hiện destination gửi của message; consumer có thể đọc để debug/routing.
- **`JMSReplyTo`:** địa chỉ do producer đặt khi yêu cầu trả lời, thường là queue/topic phản hồi hoặc temporary destination.

```text
Request message:
  sent to Destination = queue reports.request
  JMSDestination      = queue reports.request
  JMSReplyTo          = temporary queue client-123/reply-456

Response message:
  sent to Destination = temporary queue client-123/reply-456
  JMSCorrelationID    = request-42 (theo hợp đồng ứng dụng)
```

`JMSReplyTo` không biến một message thành RPC tự động: ứng dụng nhận request phải chủ động đọc header, thực hiện xử lý, tạo reply và gửi tới destination được chỉ định. Producer thường cần timeout và xử lý tình huống responder lỗi; correlation ID giúp ghép reply với request.

Không dùng `message.setJMSDestination(...)` để điều hướng gửi: destination của thao tác gửi được quyết định qua producer/`send(...)`. Header `JMSDestination` có thể được provider ghi hoặc ghi đè theo hợp đồng JMS.

## 10. Những yếu tố vận hành không được bỏ qua khi chọn Destination

### 10.1. Message body không quyết định queue hay topic

Cùng một `TextMessage`, `BytesMessage` hoặc `MapMessage` có thể gửi vào queue hoặc topic. **Kiểu payload** trả lời “message chứa dữ liệu gì?”; **kiểu destination** trả lời “đưa dữ liệu tới ai?”. Không giả định JSON buộc phải đi topic hoặc binary buộc phải đi queue.

### 10.2. Delivery mode, TTL và acknowledgment là trục riêng

- `DeliveryMode.PERSISTENT`/`NON_PERSISTENT` quyết định mức bảo vệ giao nhận của **từng message**.
- `timeToLive`/`JMSExpiration` quyết định thời hạn message có thể được giao.
- `acknowledgment`/transaction quyết định lúc broker được coi message đã xử lý phía JMS.
- `Queue`/`Topic` quyết định cách phân phối và subscription.

Một queue có `PERSISTENT` cũng không hứa lưu vô hạn nếu message hết hạn hoặc broker thiếu tài nguyên. Một topic dùng `PERSISTENT` cũng không tự bảo vệ event cho một non-durable subscriber đã tắt.

### 10.3. Thứ tự và tính công bằng

JMS có các quy tắc thứ tự trong phạm vi producer/session/consumer, nhưng không cho phép suy rộng rằng nhiều producer, nhiều worker, selector và redelivery sẽ tạo một thứ tự toàn hệ thống giống nhau ở mọi nơi. Nếu nghiệp vụ cần xử lý theo `aggregateId`, hãy thiết kế khóa phân hoạch, concurrency và quy tắc ordering theo broker/provider.

JMS cũng không bắt broker chia message cho worker theo round-robin. Dùng metric throughput và queue backlog để quan sát phân phối; tránh dùng “worker A xử lý đúng mọi message thứ nhất, worker B mọi message thứ hai” làm hợp đồng.

### 10.4. Bảo mật và vòng đời

Destination có thể được cấu hình quyền **send**, **consume**, **browse**, tạo/xóa hoặc quản trị riêng; tên đúng vẫn có thể bị từ chối nếu principal không có quyền. Kết nối đến broker nên có TLS/xác thực phù hợp. Temporary queue hoặc auto-created destination cũng có rủi ro tạo tài nguyên quá nhiều nếu không giới hạn.

Dùng tên đích ổn định, phân tách môi trường (dev/test/prod), quản lý quyền và naming convention có thể kiểm soát, ví dụ:

```text
orders.work.v1       queue: một nhóm fulfillment xử lý
orders.events.v1     topic: nhiều hệ thống nhận event
reports.reply.<id>   temporary reply destination do provider sinh
```

Đây là **ví dụ convention**, không phải cú pháp chuẩn JMS. Trong môi trường có quy tắc address riêng, cần tuân thủ naming/routing của provider.

### 10.5. Quy tắc nhất quán khi phát event sau khi ghi DB

Nếu Order Service commit đơn rồi crash trước khi publish `OrderCreated`, downstream có thể không biết đơn đã có. Nếu publish trước khi commit DB mà transaction DB rollback, consumer lại thấy event của giao dịch không tồn tại.

Cân nhắc **transactional outbox** hoặc một cơ chế phối hợp giao dịch được thiết kế rõ để đảm bảo tính nhất quán giữa DB và publishing. Chỉ chọn `Topic` không giải quyết được “dual write”, còn chọn `Queue` cũng không tự bảo đảm các tác dụng phụ xảy ra chính xác một lần.

## 11. Ví dụ Java 17 chạy độc lập để mô phỏng cách phân phối

Để kiểm tra trực quan sự khác nhau giữa “một message cho một worker” và “một bản cho mỗi subscriber”, ví dụ sau dùng collection thuần Java. **Đây là mô phỏng trong bộ nhớ, hoàn toàn không phải JMS provider**: nó không có persistence, acknowledgment, selector, transaction, subscription lifecycle hay broker.

Tạo tệp `DestinationRoutingDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Queue;

public class DestinationRoutingDemo {
    public static void main(String[] args) {
        // Một queue dùng chung cho hai worker.
        Queue<String> work = new ArrayDeque<>();
        work.add("job-42");

        System.out.println("Queue Worker A: " + work.poll());
        System.out.println("Queue Worker B: " + work.poll());

        // Hai subscription độc lập giữ mỗi bản sao của cùng event.
        Queue<String> auditSubscription = new ArrayDeque<>();
        Queue<String> metricsSubscription = new ArrayDeque<>();

        String event = "OrderCreated: ORD-42";
        auditSubscription.add(event);
        metricsSubscription.add(event);

        System.out.println("Topic Audit: " + auditSubscription.poll());
        System.out.println("Topic Metrics: " + metricsSubscription.poll());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac DestinationRoutingDemo.java
java DestinationRoutingDemo
```

Đầu ra chính xác:

```text
Queue Worker A: job-42
Queue Worker B: null
Topic Audit: OrderCreated: ORD-42
Topic Metrics: OrderCreated: ORD-42
```

`Queue Worker B: null` xuất hiện vì chỉ có **một** đơn vị công việc, đã bị worker A lấy trong mô phỏng tuần tự. Trong JMS thật, bạn không thể suy ra worker A luôn giành được message hay worker B luôn đứng sau. Hai queue `auditSubscription` và `metricsSubscription` trong demo mô phỏng **hai subscription riêng**, mỗi cái có bản sao event. Việc fan-out được viết bằng tay ở đây để giải thích semantics; trong hệ thống JMS, provider thực hiện routing theo subscriptions và chính sách cấu hình.

## 12. Checklist chọn và kiểm tra đích trong ứng dụng thật

Khi thiết kế một producer/consumer mới, hãy lần lượt xác nhận:

1. **Thông điệp là command hay event?** Một công việc có một nhóm xử lý hay một sự kiện nhiều nhóm cần nhận?
2. **Loại destination?** Queue hay Topic, mô hình chia tải và fan-out mong muốn?
3. **Tên và provisioning?** Tên provider-specific nào, tài nguyên được admin tạo hay broker auto-create, namespace theo môi trường?
4. **Resolver?** Producer và consumer dùng JNDI object, explicit Destination hay chuỗi + resolver?
5. **Spring config?** `JmsTemplate.pubSubDomain` và listener factory có khớp không?
6. **Subscription?** Với topic, bao nhiêu subscription, mỗi cái durable hay non-durable, shared hay unshared; identity ổn định ra sao?
7. **Lỗi và độ tin cậy?** TTL, delivery mode, acknowledgment/transaction, retry, DLQ, idempotency?
8. **Metadata?** Correlation ID, message type, schema version, business key, monitoring và audit?
9. **Security?** Ai được gửi/nhận/browse, broker connection được bảo vệ không?
10. **Quan sát?** Message pending, số consumer, backlog theo subscription, expiration, redelivery, DLQ, processing latency?

Không coi “send không ném lỗi” là đủ kiểm thử. Nó cho biết thao tác gửi đạt điều kiện API/provider, **không** chứng minh consumer xử lý xong hay mọi subscriber đã nhận.

## 13. Kịch bản thực hành để phân biệt Queue và Topic

**Tình huống A — Queue có hai worker**

1. Tạo/provision queue `orders.work` theo broker đang dùng.
2. Khởi động hai listener queue trên cùng destination.
3. Publish mười message có business ID khác nhau.
4. Quan sát cả nhóm xử lý tổng mười message thành công và mỗi business ID chỉ tác động một lần nhờ logic idempotent; phân phối giữa worker **không cần 5–5**.
5. Cố tình lỗi sau tác dụng phụ nhưng trước commit JMS và quan sát redelivery theo provider. Kiểm tra kết quả không nhân đôi.

**Tình huống B — Topic có hai subscription**

1. Tạo/provision topic `orders.events`.
2. Khởi động hai listener non-durable (Analytics và Audit) **trước khi publish**.
3. Publish một `OrderCreated`.
4. Xác minh từng listener có thể nhận một bản sao tương ứng. Dừng Analytics, publish event khác, rồi khởi động lại: không kỳ vọng non-durable nhận hồi tố.
5. Nếu yêu cầu giữ event lúc offline, cấu hình durable subscription trước, chọn delivery mode phù hợp và xác minh backlog khi quay lại.

**Tình huống C — Cùng tên, sai loại**

1. Cấu hình producer `JmsTemplate` với `pubSubDomain=false` và listener với `pubSubDomain=true` nhưng cùng chuỗi tên.
2. Quan sát behavior/error theo broker: có thể gửi vào queue hoặc không có consumer đúng loại, dù text name giống nhau.
3. Sửa cho cả hai cùng Queue hoặc cùng Topic **đúng với nghiệp vụ**; kiểm tra broker-side resource cùng subscription/cấu hình.
4. Ghi nhận lesson: tên đích và loại đích đều là một phần hợp đồng triển khai.

**Tình huống D — Request/reply**

1. Client tạo `TemporaryQueue` và gửi request vào queue xử lý với header `JMSReplyTo`.
2. Service trả kết quả tới destination đó, đặt `JMSCorrelationID` theo hợp đồng.
3. Client nhận trong timeout; đóng connection trước khi response và quan sát khả năng mất reply.
4. Rút ra: temporary destination gắn connection lifecycle; không dùng cho quy trình dài cần trả kết quả sau nhiều giờ.

## 14. Lỗi phổ biến

**“`Destination` và `Queue`/`Topic` là ba nơi lưu message khác nhau.”** Sai. `Destination` là giao diện cha; Queue/Topic là subtype xác định mô hình routing.

**“`Destination` có `getName()`.”** Sai. Các subtype có `getQueueName()` và `getTopicName()`. Cú pháp tên do provider quy định.

**“`createQueue("name")` tạo luôn queue vật lý trong broker theo chuẩn.”** Sai. Nó tạo object handle; tài nguyên vật lý và auto-creation thuộc provider/administration.

**“Queue bảo đảm exactly-once business effect.”** Sai. Một message được giao cho một consumer ở mỗi lần giao, nhưng retry/redelivery có thể làm xử lý lặp.

**“Topic phát mỗi message cho mọi thread trong tất cả instance.”** Sai. Fan-out là theo **subscription độc lập**; các consumer trong shared subscription chia nhau message.

**“`PERSISTENT` giúp non-durable subscriber nhận event khi offline.”** Sai. Bảo đảm message delivery không tự tạo subscription đang vắng mặt.

**“JMS topic tự lưu mọi sự kiện để subscriber mới replay.”** Sai. Durable subscription phải tồn tại trước lúc publish nếu muốn có backlog của nó; replay lịch sử là yêu cầu riêng.

**“Spring chỉ cần cùng tên String để kết nối.”** Sai. Producer/consumer phải cùng loại destination và resolve đúng resource; `pubSubDomain` quan trọng khi dùng tên String.

**“Đổi `setPubSubDomain(true)` có thể chuyển một `Queue` object đã inject thành `Topic`.”** Sai. Flag chi phối resolver, không đổi subtype của object explicit.

**“`JMSReplyTo` là destination gốc của request.”** Sai. Nó là địa chỉ hồi đáp; `JMSDestination` mới là header phản ánh đích gửi.

**“Temporary queue là queue bền vững tự động dọn khi không còn message.”** Sai. Nó có lifecycle gắn với connection, không phù hợp làm địa chỉ xử lý bền vững nhiều phiên.

**“Mọi Queue/Topic đều có cùng semantics trên mọi JMS provider.”** Sai ở các phần ngoài đặc tả: provisioning, storage quota, auto-create, security, DLQ, cluster, routing-specific behaviors và retention vẫn phải kiểm tra theo broker.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Có một message `GenerateInvoice` và ba worker cùng đợi. Mỗi message cần một worker xử lý thành công. Chọn gì?

**Đáp án:** Queue. Nhiều consumer trên queue chia công việc; vẫn cần xử lý trùng nếu xảy ra redelivery.

**Câu 2.** `OrderCreated` phải được Audit và Analytics xử lý độc lập. Hai consumer đọc cùng queue có đủ không?

**Đáp án:** Không. Chúng cạnh tranh trên một queue; một message thường đến một bên. Chọn topic với **hai subscription độc lập** hoặc một thiết kế fan-out tương đương.

**Câu 3.** `Destination d = context.createQueue("billing.work");` có bảo đảm broker tạo queue vật lý chưa?

**Đáp án:** Không. API tạo object handle theo tên; physical provisioning có thể do administrator hoặc broker auto-create tùy provider.

**Câu 4.** Ở Spring, producer `convertAndSend("a", msg)` dùng `pubSubDomain=false` và listener `@JmsListener(destination="a")` dùng factory topic. Vì tên giống nhau, listener chắc chắn nhận được không?

**Đáp án:** Không. Producer resolve queue, listener resolve topic. Cần nhất quán loại đích và resource thực tế.

**Câu 5.** Hai instance cùng **shared durable subscription** trên topic có mỗi instance nhận mọi message không?

**Đáp án:** Không. Chúng chia tải trong một subscription; muốn hai nhóm cùng nhận toàn bộ các event phù hợp, tạo **hai subscription độc lập**.

**Câu 6.** Topic non-durable consumer tắt lúc 10:00, producer publish lúc 10:05, consumer bật lại 10:10. Có quyền đòi phát lại sự kiện theo đặc tả JMS không?

**Đáp án:** Không. Subscription non-durable đã không còn; một producer dùng `PERSISTENT` cũng không tự tạo backlog cho nó.

**Câu 7.** `JMSReplyTo` chỉ định gì?

**Đáp án:** Destination để responder gửi câu trả lời, thường là queue/topic phản hồi hay `TemporaryQueue`. Nó khác `JMSDestination` của request.

**Câu 8.** Ai được tạo consumer trên temporary queue?

**Đáp án:** Chỉ connection đã tạo temporary queue; producer ở connection khác vẫn có thể gửi đến nó khi có reference đúng.

**Câu 9.** Gửi message vào queue báo thành công, nhưng business effect xảy ra hai lần. Điều này có mâu thuẫn với mô hình queue không?

**Đáp án:** Không. Ack/transaction chưa hoàn tất có thể gây redelivery; phải xây dựng business idempotency.

**Câu 10.** Java method nhận `Destination` có thể gọi `destination.getQueueName()` ngay không?

**Đáp án:** Không. `Destination` không khai báo phương thức này; phải biết/cast đúng subtype `Queue` hoặc dùng resolver/metadata riêng.

## Ghi nhớ

- `Destination` là **địa chỉ chung** của JMS; `Queue` và `Topic` là subtype biểu diễn hai mô hình phân phối khác nhau.
- **Queue:** một message được chuyển cho một consumer đủ điều kiện tại mỗi lần giao, thích hợp chia công việc giữa worker.
- **Topic:** mỗi subscription độc lập có thể nhận bản sao phù hợp, thích hợp fan-out sự kiện cho nhiều trách nhiệm.
- `createQueue(String)`/`createTopic(String)` tạo object **theo tên provider**, không bảo đảm provision tài nguyên vật lý. Tạo/chính sách broker vẫn phải được quản lý.
- Spring dùng `DestinationResolver` và `pubSubDomain` khi biến **tên String** thành đích; phải đối chiếu producer và listener trên cả tên, loại và broker resource.
- Delivery mode, TTL, durable subscription, ack, transaction, retry và idempotency là những lựa chọn **độc lập** cần thiết kế rõ, không tự có chỉ vì đã chọn Queue hoặc Topic.

### Tài liệu tham khảo chính thức

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — `Destination`, Queue/Topic semantics, `JMSContext`, `Session`, temporary destinations và delivery rules.
2. [Jakarta Messaging 3.1 — Destination API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/destination) — giao diện địa chỉ chung và quan hệ subtype.
3. [Jakarta Messaging 3.1 — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext) — `createQueue`/`createTopic`, `createConsumer`, temporary destinations và `createDurableConsumer`.
4. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — JNDI, dynamic destination resolution, `DestinationResolver` và `pubSubDomain`.
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` và gửi bằng destination name hoặc object.
6. [Spring Framework — Annotated JMS Listeners](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` và listener factory.
7. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — listener lifecycle, transaction và acknowledgment.