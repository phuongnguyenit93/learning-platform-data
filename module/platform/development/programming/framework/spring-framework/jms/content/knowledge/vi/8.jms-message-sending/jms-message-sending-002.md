# Gửi tới Destination hoặc tên được phân giải

> **Module:** Spring Framework – JMS  
> **Nhóm:** Gửi thông điệp  
> **Chủ đề:** Chọn địa chỉ gửi bằng `jakarta.jms.Destination` có sẵn hoặc bằng tên `String` được Spring phân giải sang Destination.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu `Destination` là địa chỉ logic trong Jakarta Messaging; `Queue` và `Topic` là hai loại có semantics phân phối khác nhau.
2. Phân biệt **gửi bằng object `Destination`** với **gửi bằng tên `String` qua `DestinationResolver`** trong `JmsTemplate`: bước nào xảy ra và bước nào không.
3. Dùng đúng các overload `send(...)`, `convertAndSend(...)` và dạng không có tham số đích khi đã cấu hình default destination.
4. Giải thích cách `DynamicDestinationResolver`, `JndiDestinationResolver`, `pubSubDomain` và cấu hình broker/JNDI tương tác.
5. Cấu hình hai đường gửi queue/topic trong một ứng dụng Spring JMS, sử dụng cả tên và object, và đối chiếu listener đúng loại.
6. Nhận biết lỗi “tên giống nhau nhưng sai kiểu Queue/Topic”, thiếu JNDI binding, auto-create sai kỳ vọng, tên do người dùng nhập không được kiểm soát, và lỗi xử lý giao dịch.
7. Kiểm thử có căn cứ: kiểm tra loại Destination sau phân giải, tài nguyên vật lý, quyền send, đường đi của message và kết quả nghiệp vụ.

## 1. Bức tranh tổng quan: “gửi đến đâu” gồm hai quyết định

JMS giúp ứng dụng gửi message tới một **Destination** chứ không phải tới trực tiếp một địa chỉ IP của consumer. Destination là interface chuẩn; provider/broker triển khai việc routing.

```text
Application                            JMS provider / broker

Message payload
      |
      |      [Cách A] Destination object --------------------+
      |                                                     |
      +----> JmsTemplate.send(...)                           |
      |                                                     v
      |      [Cách B] "orders.work" (String)          [Queue orders.work]
      |                  |                                  |
      |                  v                                  v
      |             DestinationResolver                 Worker group
      |                  |
      |                  +--> Queue object ----------------> queue
      |
      +----> "orders.events" (String)
                        |
                        v
                DestinationResolver
                 pubSubDomain = true
                        |
                        +--> Topic object ----------------> topic
                                                            |
                                                   Subscriber A, B, ...
```

Hai quyết định độc lập nhưng phải nhất quán:

- **Chọn đích nào?** Một `Destination` đã có hay một tên cần resolver biến thành `Destination`?
- **Đích thuộc loại gì?** `Queue` thường chuyển một message cho một worker tại một lần delivery; `Topic` cho mỗi subscription độc lập một bản sao phù hợp.

**Không đồng nhất chuỗi tên với object địa chỉ.** `"orders.events"` có thể là tên vật lý mà provider hiểu, tên JNDI binding, hoặc tên logic do ứng dụng tự ánh xạ. Bản thân String không mang thông tin kiểu queue/topic. Với cách gửi qua tên, resolver và `pubSubDomain` quyết định cách tra cứu/tạo object.

### 1.1. Những interface cần nhớ

```java
import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Topic;
```

Quan hệ kiểu theo Jakarta Messaging:

```text
         Destination  (interface)
            /    \
           /      \
         Queue    Topic
            |      |
     TemporaryQueue  TemporaryTopic
```

Hai dòng cuối trong hình chỉ rằng `TemporaryQueue extends Queue` và `TemporaryTopic extends Topic`, **không có nghĩa mọi queue/topic đều tạm thời**.

Một method nhận `Destination` có thể được gọi với `Queue` hoặc `Topic` do subtype phù hợp. Nhưng `Destination` không có `getName()` chung. Cần biết subtype hoặc tra cứu metadata của provider nếu muốn hiện tên.

```java
public static String describe(Destination d)
        throws jakarta.jms.JMSException {
    if (d instanceof Queue queue) {
        return "Queue: " + queue.getQueueName();
    }
    if (d instanceof Topic topic) {
        return "Topic: " + topic.getTopicName();
    }
    return "Destination type unknown";
}
```

Đây là đoạn minh họa trong project có Jakarta Messaging API, không phải tệp Java chạy độc lập; tên và cách render của provider là phụ thuộc môi trường.

### 1.2. Queue và Topic không thay đổi theo kiểu body

- `TextMessage`, `BytesMessage` và các loại message khác **đều có thể** gửi đến queue hoặc topic.
- `Queue` phù hợp chia việc giữa worker. Khi message lỗi, acknowledgment/transaction có thể dẫn đến redelivery.
- `Topic` phù hợp fan-out sự kiện cho nhiều subscription. Subscriber non-durable offline thường không nhận hồi tố message khi subscription không còn.
- Bật `DeliveryMode.PERSISTENT` không biến queue thành topic và không tự tạo durable subscription.

**Destination quyết định đường phân phối; Message/MessageConverter quyết định body và metadata.** Không dùng lựa chọn message type để suy diễn loại destination.

## 2. Hai đường gửi của JmsTemplate: object và tên

Spring JMS cung cấp `org.springframework.jms.core.JmsTemplate`. Mọi đường gửi cuối cùng đều cần một `jakarta.jms.Destination`; khác nhau là application đã có object đó **trước khi gọi** hay Spring phải **phân giải tên**.

### Đường A — truyền trực tiếp object Destination

```java
// queue là jakarta.jms.Queue/Destination được inject từ JNDI
// hoặc do provider cung cấp.
jmsTemplate.send(queue, session ->
        session.createTextMessage("generate-invoice:42"));
```

- Overload này có dạng `send(Destination, MessageCreator)`.
- `JmsTemplate` nhận object `queue` **đã xác định**, dùng nó trong thao tác gửi.
- **Không cần gọi `DestinationResolver.resolveDestinationName(...)` để chuyển chuỗi**, vì không có chuỗi destination cần phân giải.
- `pubSubDomain` không phải phép “ép” một `Queue` object có sẵn thành `Topic`. Loại thực tế của `queue` vẫn là queue.
- Object cần thuộc provider tương thích với `ConnectionFactory` dùng bởi `JmsTemplate`; không lấy handle provider X rồi mặc định gửi được qua provider Y.

Ưu điểm: kiểu đích rõ ràng ở code và cấu hình, tận dụng object do JNDI/quản trị cung cấp, giảm khả năng nhầm kiểu khi dùng tên tùy ý. Đổi lại phải inject/tra cứu và quản lý lifecycle cấu hình của object.

### Đường B — truyền String để Spring phân giải

```java
jmsTemplate.send("orders.work", session ->
        session.createTextMessage("generate-invoice:42"));
```

- Overload là `send(String destinationName, MessageCreator)`.
- Spring gọi `DestinationResolver` được cấu hình để tìm/tạo object `Destination` phù hợp từ tên.
- Resolver thường cần biết **đang dùng queue hay topic**; thuộc tính `pubSubDomain` của template tham gia quyết định này.
- Phân giải tên **không đồng nghĩa bảo đảm broker đã có physical destination**: có thể tìm object từ JNDI hoặc tạo object theo tên provider-specific; broker thực hiện provision theo cơ chế riêng.

Ưu điểm: ứng dụng không cần mỗi địa chỉ là một Java bean riêng; tiện với danh sách destination đã được quản trị theo convention. Rủi ro: cấu hình resolver, `pubSubDomain`, tên logic/physical và quyền broker nếu không đồng nhất.

### Quy tắc dễ nhớ

> `send(Destination, ...)`: **đã có địa chỉ** → gửi.  
> `send(String, ...)`: **có tên** → resolver tạo/tìm địa chỉ → gửi.

Đây là khác biệt về **cách tìm địa chỉ**, không phải hai giao thức gửi khác nhau hay sự khác nhau về độ tin cậy của message.

## 3. Các overload gửi quan trọng của JmsTemplate

| Cách gọi | Ý nghĩa đích | Message body |
| --- | --- | --- |
| `send(Destination, MessageCreator)` | Object đích đã có | Callback tạo `jakarta.jms.Message` |
| `send(String, MessageCreator)` | Tên được `DestinationResolver` phân giải | Callback tạo JMS message |
| `send(MessageCreator)` | Đích mặc định đã cấu hình | Callback tạo JMS message |
| `convertAndSend(Destination, Object)` | Object đích đã có | Converter biến Java object thành JMS message |
| `convertAndSend(String, Object)` | Tên được resolver phân giải | Converter biến Java object thành JMS message |
| `convertAndSend(Object)` | Đích mặc định đã cấu hình | Converter biến Java object thành JMS message |
| `convertAndSend(..., MessagePostProcessor)` | Đích theo overload đã chọn | Converter chạy trước, post-processor bổ sung header/properties sau |

**Lưu ý về `String`:** Trong `send("orders.work", creator)`, String là **tên destination**. Trong `convertAndSend("hello")` một tham số, String lại là **payload** gửi tới **default destination**. Còn `convertAndSend("orders.work", "hello")` gồm tên destination và payload. Phân biệt bằng **chữ ký hàm và số tham số**, không bằng kiểu String đơn lẻ.

### 3.1. send và convertAndSend khác nhau ở đâu?

`send(...)` dùng `MessageCreator`; callback nhận `jakarta.jms.Session` để tạo message, chỉnh header/properties:

```java
jmsTemplate.send("orders.work", session -> {
    var m = session.createTextMessage("invoice-42");
    m.setStringProperty("eventType", "GENERATE_INVOICE");
    m.setJMSCorrelationID("request-42");
    return m;
});
```

`convertAndSend(...)` dùng `MessageConverter` được gắn với template:

```java
jmsTemplate.convertAndSend("orders.work", "invoice-42");
jmsTemplate.convertAndSend("binary.tasks", new byte[] {1, 2, 3});
```

Converter mặc định `SimpleMessageConverter` hỗ trợ cơ bản `String → TextMessage`, `byte[] → BytesMessage`, `Map → MapMessage` (khi giá trị thuộc các kiểu phù hợp). Với DTO custom hay JSON versioning, phải chọn converter/schema rõ ràng; **không mặc định một Java record bất kỳ sẽ tự serialize sang JSON**.

Nếu muốn sau conversion vẫn đặt property:

```java
jmsTemplate.convertAndSend(
        "orders.work",
        "invoice-42",
        message -> {
            message.setStringProperty("eventType", "GENERATE_INVOICE");
            message.setJMSCorrelationID("request-42");
            return message;
        });
```

Trong đoạn này, `MessagePostProcessor` chạy **sau converter, trước send**. Cả ba ví dụ là đoạn code trong ứng dụng đã có `JmsTemplate`, broker, dependency `spring-jms`; không chạy độc lập bằng `javac`.

### 3.2. Gửi đến default destination

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPubSubDomain(false);
template.setDefaultDestinationName("orders.work");

// Một tham số là payload; đích gửi lấy từ cấu hình mặc định.
template.convertAndSend("invoice-42");

// Callback message creator dùng default destination.
template.send(session ->
        session.createTextMessage("invoice-43"));
```

`connectionFactory` ở đây do môi trường/provider cung cấp. `setDefaultDestinationName(...)` là một cách cấu hình; cũng có thể `setDefaultDestination(Destination)` khi đã có object. Nếu gọi overload không có destination mà **chưa cấu hình mặc định**, Spring sẽ báo lỗi.

Nên cấu hình template **một lần rồi chia sẻ**; `JmsTemplate` an toàn cho nhiều thread **sau khi đã cấu hình xong**, không nên liên tục đổi `pubSubDomain` hay default destination trên một singleton đang phục vụ request song song.

## 4. DestinationResolver: mắt xích giữa tên và object

Interface cốt lõi của Spring:

```java
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain
    ) throws JMSException;
}
```

Đây là chữ ký được rút gọn cho mục đích học tập; khi dùng thật, import các interface từ `org.springframework.jms.support.destination` và `jakarta.jms`. Resolver trả object `Destination` để JmsTemplate sử dụng.

Luồng thông thường:

```text
JmsTemplate.send("orders.work", creator)
      |
      +--> DestinationResolver.resolveDestinationName(
      |        session,
      |        "orders.work",
      |        pubSubDomain
      |    )
      |           |
      |           +--> Queue hoặc Topic object
      |
      +--> MessageCreator.createMessage(session)
      |
      +--> provider MessageProducer.send(destination, message)
      |
      +--> release Session/Producer theo template
```

Sơ đồ mô tả **quan hệ chính**, không hứa mọi provider/đường callback thực hiện tuần tự giống hoàn toàn từng bước nội bộ. Điều chắc chắn về API là: khi dùng tên, phải có một resolver biến tên thành destination; khi truyền object, không cần bước phân giải tên.

### 4.1. DynamicDestinationResolver — đường mặc định

Khi không cấu hình resolver khác, `JmsTemplate` mặc định dùng `DynamicDestinationResolver`. Nó sử dụng `Session.createQueue(name)` hoặc `Session.createTopic(name)` theo `pubSubDomain`.

```text
JmsTemplate
  setPubSubDomain(false)   -- "billing.jobs" --> Session.createQueue(...)
  setPubSubDomain(true)    -- "order.events" --> Session.createTopic(...)
```

**Mặc định `pubSubDomain=false`**: tên String được resolve theo miền **queue**, không phải topic. Vì thế:

```java
JmsTemplate queueSender = new JmsTemplate(connectionFactory);
queueSender.convertAndSend("orders.events", "hello");
```

Đoạn này **không tự tạo một topic chỉ vì tên chứa “events”**. Với DynamicDestinationResolver và default queue domain, Spring yêu cầu một `Queue` handle có tên `"orders.events"`. Nếu ứng dụng mong topic, phải cấu hình `setPubSubDomain(true)` hoặc truyền `Topic` object thực sự.

### 4.2. createQueue(String) không bắt buộc provision broker queue

Jakarta Messaging quy định `Session.createQueue(String)` và `JMSContext.createQueue(String)` tạo **Queue object** chứa tên provider-specific; tương tự với Topic. Chúng **không phải API chuẩn để tạo physical queue/topic** trên broker.

Hệ quả:

- Broker A có thể cho auto-create destination khi client sử dụng; broker B có thể yêu cầu tạo thủ công.
- Broker có thể từ chối vì tên không hợp lệ, thiếu quyền tạo/sử dụng, không có address/binding, hoặc sai routing type.
- `send(...)` thành công theo API không chứng minh consumer đã xử lý.
- Một resolver hoạt động đúng trên object level vẫn có thể thất bại khi provider cố gửi message.

Với production, khai báo queue/topic và các chính sách retention, quota, DLQ, ACL, clustering bằng công cụ của provider; không dựa vào “gọi createQueue tự sinh queue” như một bảo đảm chuẩn.

### 4.3. JndiDestinationResolver — tra tên đã đăng ký

Nếu đội vận hành dùng JNDI administered destinations:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(resolver);
template.setPubSubDomain(false);

// "jms/queue/BillingJobs" là tên binding JNDI do môi trường đặt.
template.send("jms/queue/BillingJobs",
        session -> session.createTextMessage("invoice-42"));
```

Đây là đoạn tích hợp trong ứng dụng có **JNDI context đã thiết lập**, broker và Spring JMS, không chạy độc lập. `JndiDestinationResolver` tìm object theo binding; binding có thể trỏ tới queue/provider name khác với chuỗi tra cứu.

Theo cấu hình mặc định của resolver JNDI này, **fallback sang dynamic khi lookup thất bại bị tắt**. Khi cố ý bật `setFallbackToDynamicDestination(true)`, nếu JNDI không có tên, Spring có thể dùng dynamic resolver. Tuy nhiên bật fallback vô tình ở production có thể **che lỗi binding** và dẫn tới một queue/topic khác được tạo/resolve theo tên không mong muốn. Nên chủ động quyết định dựa vào chính sách triển khai.

`setCache(true)` có thể giảm overhead lookup nhưng cần lưu ý thay đổi JNDI binding, hot restart và quản lý cache. Cấu hình tùy provider; đừng dùng một tên logic cho queue và topic khác nhau trong cùng cache/resolver rồi giả định phân biệt hoàn hảo.

### 4.4. Custom DestinationResolver

Ứng dụng phức tạp có thể tự triển khai `DestinationResolver` khi cần ánh xạ địa chỉ logic:

```java
// PSEUDOCODE minh họa hợp đồng, không phải implementation hoàn chỉnh:
resolve("billing.commands", false) -> physical Queue "v1.billing.jobs"
resolve("orders.events", true)     -> physical Topic "v1.order.created"
```

Một resolver custom cần:

- Định nghĩa **mapping có kiểm soát**, không tạo địa chỉ từ input chưa xác thực.
- Tôn trọng `pubSubDomain`, trả object đúng loại; phát hiện mismatch ngay.
- Dùng đúng ConnectionFactory/provider hoặc JNDI scope.
- Có chính sách cache, refresh, error reporting, test tên không tồn tại.
- Tránh side effect nguy hiểm khi lookup thất bại (ví dụ tự tạo queue mới ngoài kế hoạch).

Khi chỉ có vài destination cố định, cách rõ ràng hơn thường là inject trực tiếp `Queue`/`Topic` hoặc dùng hai template chuyên biệt. Custom resolver chỉ cần khi mapping là yêu cầu nghiệp vụ thật.

## 5. pubSubDomain điều khiển bước nào?

`setPubSubDomain(boolean)` trên `JmsTemplate` chủ yếu thông báo cho **bước phân giải tên** nên yêu cầu queue hay topic. Một giá trị mặc định `false` tương ứng queue, `true` tương ứng topic.

| Tình huống | `pubSubDomain` | Đích thực tế được chọn như thế nào? |
| --- | --- | --- |
| `send("orders.work", ...)` với DynamicDestinationResolver | `false` | Resolver tạo `Queue` handle |
| `send("orders.events", ...)` với DynamicDestinationResolver | `true` | Resolver tạo `Topic` handle |
| `send(queueObject, ...)` | `true` hoặc `false` | Dùng **queueObject**, không tự ép thành Topic |
| `send(topicObject, ...)` | `true` hoặc `false` | Dùng **topicObject**, không tự ép thành Queue |
| `send("jms/billing", ...)` với JndiDestinationResolver | Cấu hình phù hợp | Lookup binding; kết quả phải đúng loại kỳ vọng, không đoán chỉ từ tên |
| `send(creator)` với default `Destination` object | Tùy template | Dùng object mặc định |
| `send(creator)` với default tên String | Cấu hình phù hợp | Phân giải tên mặc định rồi gửi |

Cùng một chuỗi `"orders.events"` có thể bị xem là Queue trong template A và Topic trong template B. Không nên dùng `pubSubDomain` như flag toàn cục thay đổi runtime theo từng request trên một `JmsTemplate` singleton; hãy có **hai bean template** cố định hoặc truyền explicit Destination object phù hợp.

Trong `@JmsListener`, container factory cũng có `setPubSubDomain(...)` để listener resolve tên đúng kiểu. **Producer dùng topic và listener dùng queue cùng tên** là một lỗi cấu hình thường gặp.

## 6. Ví dụ Spring JMS: một ứng dụng gửi queue và topic đúng cách

Giả định:

- Spring Framework 6+ / Jakarta Messaging `jakarta.jms`, Java 17+, dependency `spring-jms`.
- Đã có `jakarta.jms.ConnectionFactory` nối broker thật.
- Queue `billing.jobs` và Topic `orders.events` đã được quản trị/provision hoặc broker được cấu hình auto-create đúng cách.
- Có component scanning và `@EnableJms`; trong ứng dụng Spring Boot, cấu hình listener có thể được auto-provision theo điều kiện tương ứng.
- Chưa yêu cầu durable subscription; topic listeners ở ví dụ này chỉ minh họa fan-out khi các subscriber đang hoạt động.

### 6.1. Hai JmsTemplate có cấu hình ổn định

**File `JmsSenderConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsSenderConfig {

    @Bean("queueTemplate")
    public JmsTemplate queueTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(false); // String -> Queue
        return template;
    }

    @Bean("topicTemplate")
    public JmsTemplate topicTemplate(ConnectionFactory cf) {
        JmsTemplate template = new JmsTemplate(cf);
        template.setPubSubDomain(true);  // String -> Topic
        return template;
    }

    @Bean("queueListenerFactory")
    public DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicListenerFactory")
    public DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Dùng tên bean riêng để tránh ambiguity khi inject hai `JmsTemplate`. `setSessionTransacted(true)` cho listener giúp rollback/redelivery trong local JMS transaction khi xử lý thất bại, **không gộp tự động một transaction database** với JMS transaction.

### 6.2. Producer gửi đến tên được phân giải

**File `MessagingPublisher.java`:**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class MessagingPublisher {

    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;

    public MessagingPublisher(
            @Qualifier("queueTemplate") JmsTemplate queueTemplate,
            @Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
    }

    public void requestInvoice(String invoiceId) {
        queueTemplate.convertAndSend("billing.jobs", invoiceId);
    }

    public void publishOrderCreated(String orderId) {
        topicTemplate.convertAndSend("orders.events", orderId);
    }

    public void requestInvoiceWithProperties(String invoiceId) {
        queueTemplate.send("billing.jobs", session -> {
            var message = session.createTextMessage(invoiceId);
            message.setStringProperty("eventType", "CREATE_INVOICE");
            message.setStringProperty("schemaVersion", "1");
            return message;
        });
    }
}
```

`queueTemplate` phân giải chuỗi `"billing.jobs"` thành queue object; `topicTemplate` phân giải `"orders.events"` thành topic object. `String` payload có thể được converter mặc định chuyển thành `TextMessage`. Khi cần JMS properties/header chủ động, dùng `send(..., MessageCreator)` hoặc `convertAndSend(..., MessagePostProcessor)`.

### 6.3. Listener tương ứng

**File `InvoiceJobListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {
    @JmsListener(
            destination = "billing.jobs",
            containerFactory = "queueListenerFactory")
    public void onInvoiceJob(String invoiceId) {
        System.out.println("Invoice: " + invoiceId);
    }
}
```

**File `OrderAuditListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {
    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void audit(String orderId) {
        System.out.println("Audit: " + orderId);
    }
}
```

**File `OrderMetricsListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMetricsListener {
    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicListenerFactory")
    public void collect(String orderId) {
        System.out.println("Metrics: " + orderId);
    }
}
```

Khi broker hoạt động, listener đã đăng ký từ trước và không gặp lỗi, gọi:

```java
publisher.requestInvoice("INV-42");
publisher.publishOrderCreated("ORD-42");
```

Có thể tạo log:

```text
Invoice: INV-42
Audit: ORD-42
Metrics: ORD-42
```

**Đây là output điều kiện, không bảo đảm thứ tự**. Listener có thể chạy ở các thread/tiến trình khác nhau; redelivery có thể xảy ra, và non-durable topic consumer offline có thể bỏ lỡ event. Hệ thống cần business idempotency và chính sách retry phù hợp.

**Tại sao dùng hai listener topic?** Để minh họa hai subscription độc lập cùng cần event. Nếu tạo nhiều replica của cùng một non-durable listener mà không thiết kế shared/durable subscription, mỗi replica có thể nhận một bản event, không tự trở thành worker group chia tải như queue.

### 6.4. Gửi bằng Destination object được inject

Giả sử môi trường đã bind một `jakarta.jms.Queue billingQueue` qua JNDI hoặc provider adapter. Một service khác có thể nhận thẳng object:

```java
import jakarta.jms.Queue;
import org.springframework.jms.core.JmsTemplate;

public final class ExplicitDestinationSender {
    private final JmsTemplate jmsTemplate;
    private final Queue billingQueue;

    public ExplicitDestinationSender(
            JmsTemplate jmsTemplate, Queue billingQueue) {
        this.jmsTemplate = jmsTemplate;
        this.billingQueue = billingQueue;
    }

    public void sendInvoiceId(String invoiceId) {
        jmsTemplate.send(billingQueue,
                session -> session.createTextMessage(invoiceId));
    }
}
```

Class này thuộc một project Spring/JMS đã được inject `JmsTemplate` và `Queue`; không phải file standalone. Không có lệnh `resolveDestinationName("...")` ở path này. Việc bean `billingQueue` được cấu hình đúng provider/cùng broker vẫn là trách nhiệm của ứng dụng.

**Không tạo một Queue object từ broker A rồi tự động giả định một JmsTemplate kết nối broker B gửi vào đó được.** Tính portable của handle phụ thuộc JMS provider và namespace; test integration cần dùng đúng infrastructure.

## 7. Ví dụ Jakarta Messaging thuần: chỉ dùng Destination object

Phân biệt với Spring String API: ở Jakarta Messaging simplified API, `JMSProducer.send(...)` nhận `Destination` chứ không có overload portable `send(String destinationName, body)`.

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.Topic;

public final class RawJmsPublisher {
    private final ConnectionFactory connectionFactory;

    public RawJmsPublisher(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void publish() {
        try (JMSContext context = connectionFactory.createContext()) {
            Queue queue = context.createQueue("billing.jobs");
            Topic topic = context.createTopic("orders.events");

            context.createProducer().send(queue, "INV-42");
            context.createProducer().send(topic, "ORD-42");
        }
    }
}
```

Đây là class đầy đủ về mặt cú pháp trong **một ứng dụng có Jakarta Messaging dependency và provider hợp lệ**; không thể biên dịch chỉ với JDK mà thiếu thư viện. `createQueue/Topic(String)` tạo object handle theo tên provider-specific, **không bảo đảm provision physical resource**. `JMSContext` đóng bằng try-with-resources.

Classic API cho phép `MessageProducer` gắn đích lúc khởi tạo:

```java
// session là jakarta.jms.Session đang hoạt động.
Destination queue = session.createQueue("billing.jobs");
MessageProducer producer = session.createProducer(queue);
producer.send(session.createTextMessage("INV-42"));
producer.close();
```

Hoặc không gắn đích trước để chỉ định ở từng lần gửi:

```java
MessageProducer producer = session.createProducer(null);
producer.send(queue, session.createTextMessage("INV-42"));
producer.send(replyTo, session.createTextMessage("READY"));
producer.close();
```

Ở ví dụ cuối, `replyTo` là `Destination` nhận được từ một request có `JMSReplyTo`; hai mảnh code giả định session đã được tạo, xử lý checked `JMSException` phù hợp. Theo JMS classic API, một producer **unidentified** tạo với null mới nhận destination tại `send(destination, message)`; không gọi overload này tùy tiện trên producer bị buộc vào một destination khác.

Trong simplified API, `JMSProducer` nhận Destination ở **mỗi lần send**. Hai cách đều cuối cùng gửi tới một object `Destination`; Spring bổ sung tầng giải tên String nhằm giảm boilerplate.

## 8. Cấu hình mặc định hay explicit: nên chọn gì?

### Nếu destination cố định, kiểu rõ và được quản trị

Dùng `Destination` object inject từ JNDI hoặc cấu hình provider:

- Biểu thị rõ queue/topic bằng Java type.
- Dễ kiểm soát binding và quyền deploy.
- Không phải đoán `pubSubDomain` trên send path dùng object.
- Phù hợp nơi thay đổi physical address do vận hành quản lý.

### Nếu có nhiều tên hợp lệ, nhưng cùng một domain

Dùng `String + DynamicDestinationResolver` với template chuyên dụng theo domain:

- Queue sender chỉ gửi queue; topic sender chỉ gửi topic.
- Có tên cố định theo cấu hình thay vì ghép tùy ý từ input.
- Với provider cho auto-create, cần quy trình quota/ACL/cleanup tránh bùng nổ destinations.
- Mỗi tên dùng thuộc đúng namespace và broker của ứng dụng.

### Nếu tên logic được quản lý tập trung qua JNDI

Dùng `String + JndiDestinationResolver`:

- Tách tên logic khỏi tên vật lý provider.
- Ưu tiên tắt dynamic fallback trong production nếu JNDI bắt buộc.
- Kiểm thử startup/fail-fast với thiếu binding và sai loại.
- Cân nhắc cache invalidation và quy trình thay đổi JNDI mapping.

### Nếu đích thay đổi theo tenant hoặc event

Không lấy nguyên chuỗi từ HTTP request rồi gọi:

```java
// ANTI-PATTERN: destinationName do client tùy ý cung cấp.
jmsTemplate.convertAndSend(destinationNameFromRequest, payload);
```

Một chuỗi được tự do ghép có thể gây gửi nhầm tenant, tự tạo resource ngoài chính sách, làm quá tải namespace hoặc chuyển dữ liệu sang queue/topic sai. An toàn hơn là ánh xạ các giá trị từ một **allowlist**:

```java
public String destinationForRegion(String region) {
    return switch (region) {
        case "north" -> "billing.north.jobs";
        case "south" -> "billing.south.jobs";
        default -> throw new IllegalArgumentException(
                "Unsupported region");
    };
}
```

Đây là method Java 17 thuần có thể đặt trong project, dùng switch expression để định tuyến theo mapping cho phép. Ở production, cần quyền broker theo từng tenant/vhost, audit, kiểm tra JSON/schema đầu vào và tách environment dev/staging/prod.

## 9. Những điểm khác với MessageConverter, QoS và transaction

### 9.1. Đường chọn destination không quyết định kiểu body

- `send(..., MessageCreator)` cho phép tạo `TextMessage`, `BytesMessage`, `MapMessage`… bằng `Session`.
- `convertAndSend(..., Object)` cho phép Spring converter tự chuyển payload theo cấu hình.
- Chọn cách truyền Destination object hay String **không thay đổi** quy tắc chuyển body.
- Với payload JSON/Avro/protobuf, cần schema và converter tương ứng; không suy ra broker tự giải mã.

### 9.2. QoS không đến từ DestinationResolver

`DeliveryMode.PERSISTENT`/`NON_PERSISTENT`, priority và time-to-live là thuộc tính giao nhận. `DestinationResolver` chỉ tìm/khởi tạo **địa chỉ** theo hợp đồng; nó không tự bảo đảm message persistent, durable topic subscription hoặc xử lý exactly-once.

`JmsTemplate` có thể được cấu hình:

```java
import jakarta.jms.DeliveryMode;

jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setTimeToLive(60_000L);
```

**Lưu ý:** muốn Spring áp dụng các QoS override của template thì phải bật `setExplicitQosEnabled(true)`; nếu không, producer/provider có thể sử dụng mặc định riêng. TTL 60 giây ở đây chỉ là ví dụ, **không** phải cấu hình khuyến nghị cho mọi message. Với task dài, TTL quá ngắn có thể làm message expire trước khi consumer xử lý.

### 9.3. Transaction không được giải quyết bằng “send thành công”

Gọi `send(...)` hoặc `convertAndSend(...)` thành công cho biết thao tác gửi đáp ứng điều kiện của API/provider, **không chứng minh consumer đã commit nghiệp vụ**. Đặc biệt:

1. Producer ghi đơn vào database.
2. Database commit thành công.
3. Ứng dụng crash trước khi publish `OrderCreated`.

Dù đã chọn đúng topic và resolver, event vẫn có thể không xuất hiện. Đó là bài toán **dual write** giữa DB và JMS. Để giải quyết, cân nhắc transactional outbox hoặc cơ chế giao dịch phối hợp phù hợp.

Ở consumer, message có thể được giao lại khi lỗi xảy ra trước ack/commit. Với nghiệp vụ nhạy cảm, dùng business event ID, idempotency hoặc unique constraint để tránh side effect trùng. Queue không tự hứa exactly-once business effect, topic cũng không.

### 9.4. Header `JMSDestination` và địa chỉ gửi

`JMSDestination` là header cho biết đích đã dùng khi message được gửi theo ngữ nghĩa provider. Không đặt `message.setJMSDestination(...)` rồi chờ broker dùng header đó như tham số routing; **đích gửi** được quyết định từ `Destination` truyền cho `send(...)` hoặc từ default destination đã cấu hình.

`JMSReplyTo` là header khác, báo cho responder nơi gửi trả lời; service có thể lấy object này và dùng `jmsTemplate.send(request.getJMSReplyTo(), ...)`. Với reply destination kiểu temporary, lifecycle và connection ownership còn áp dụng.

## 10. Debug khi gửi đúng tên mà listener không nhận

### Trường hợp A: queue/topic bị mismatch

Producer:

```java
JmsTemplate template = new JmsTemplate(cf); // pubSubDomain mặc định false
template.convertAndSend("orders.events", "ORD-42");
```

Listener:

```java
@JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerFactory")
public void onOrderCreated(String payload) { /* ... */ }
```

Producer yêu cầu Queue handle, listener yêu cầu Topic handle cùng tên. Tùy broker, thao tác gửi có thể thành công vào queue không ai nghe, bị từ chối vì routing không phù hợp, hoặc tạo resource khác theo chính sách auto-create. **Tên giống nhau chưa đủ**.

Cách sửa: cấu hình `setPubSubDomain(true)` cho producer nếu ý định là topic; hoặc truyền `Topic` object chính xác. Kiểm tra physical destination và subscription sau deploy.

### Trường hợp B: nhầm tên JNDI với tên broker

Ví dụ JNDI có binding `jms/queue/Invoice` trỏ tới physical queue `billing.v2.jobs`. Một template dùng `DynamicDestinationResolver` sẽ cố tạo Queue handle theo **chính chuỗi `"jms/queue/Invoice"`**; nó **không tự biết** JNDI binding đó. Template dùng `JndiDestinationResolver` mới tra JNDI theo binding.

Cách sửa: thống nhất resolver và naming convention; log tên logic, object type và destination vật lý theo công cụ provider. Không mặc định mọi String đều là JNDI lookup.

### Trường hợp C: auto-create thiếu quyền hoặc bị cấm

`DynamicDestinationResolver` chỉ tạo object handle; khi gửi, provider có thể cần destination đã tồn tại hoặc được phép tự tạo. Nếu broker cấm auto-create hoặc principal không có quyền send/create, gửi có thể lỗi.

Cách sửa: quản trị destination ngoài ứng dụng, cấp ACL tối thiểu, kiểm tra namespace/vhost và error code của broker. Đừng bật quyền auto-create toàn hệ thống chỉ để che lỗi sai tên.

### Trường hợp D: default destination không có hoặc sai

`jmsTemplate.convertAndSend("HELLO")` khi chưa có `defaultDestination` hoặc `defaultDestinationName` sẽ lỗi; nếu default name đang trỏ sai queue, message đi sai nơi. Cần phân biệt overload một đối số với hai đối số trong code review.

### Trường hợp E: topic subscription được tạo quá muộn

Topic dùng non-durable subscription. Producer publish lúc 10:00 nhưng listener chỉ startup lúc 10:01; listener không được mặc định nhận event đã xảy ra. Cần tạo durable subscription **trước khi publish**, đặt định danh ổn định, delivery mode và retention thích hợp nếu yêu cầu nhận trong lúc offline.

### Trường hợp F: lỗi body conversion

Destination đúng nhưng converter không xử lý DTO custom, payload sai schema hoặc consumer không giải mã được. Đây là vấn đề **body/schema** chứ không phải resolver. Tách log gửi/nhận và xác thực message type/contentType/version.

### Trường hợp G: gửi xong nhưng business action chạy trùng

Có thể JMS redelivery do consumer lỗi trước ack/commit. Không sửa bằng cách đổi Queue thành Topic hay ngược lại; thiết kế idempotency và transaction trên business effect.

## 11. Lỗi xử lý với JmsTemplate và chiến lược kiểm thử

`JmsTemplate` chuyển checked `jakarta.jms.JMSException` thành các ngoại lệ runtime thuộc Spring JMS như `org.springframework.jms.JmsException`. Caller không cần khai báo checked `throws JMSException` chỉ để gọi template, nhưng **phải có chính sách phân loại lỗi**: chưa resolve được tên, invalid destination, quyền gửi, broker down, conversion failure hay transaction rollback.

Một ranh giới hữu ích:

| Lỗi | Có thể phát sinh ở bước nào? | Hướng xử lý |
| --- | --- | --- |
| Binding JNDI không tồn tại | Resolver lookup | Fail fast, kiểm tra naming và môi trường |
| Tên hợp lệ nhưng Queue/Topic sai | Resolver/provider | Kiểm tra `pubSubDomain` và kiểu object |
| Destination vật lý không được tạo | Broker send | Provision và kiểm tra provider policy |
| Không có quyền send | Broker/security | Cấp ACL phù hợp, không retry vô hạn khi lỗi quyền |
| Conversion exception | MessageConverter/creator | Sửa contract/schema/codec |
| Mạng/broker tạm lỗi | Connection/send | Retry có giới hạn, backoff và idempotency |
| Listener không online khi topic publish | Subscription lifecycle | Durable subscription nếu bắt buộc không bỏ lỡ |
| Consumer xử lý trùng | Ack/transaction/redelivery | Business ID và deduplication |
| Payload quá lớn | Converter/broker quota | Giới hạn size hoặc gửi reference tới object storage |

Đừng chỉ log `"JMS send failed"` và nuốt mọi exception. Nên ghi tên logic, loại destination mong đợi, environment, event ID, correlation ID và error class; tránh ghi payload nhạy cảm.

### Quy trình xác minh từng bước

1. **Đọc cấu hình producer:** template bean nào, resolver nào, `pubSubDomain`, default destination và converter nào?
2. **Xác định kiểu đích:** String hay `Destination` object? Nếu String, resolver cho ra Queue hay Topic?
3. **Kiểm tra broker:** physical destination, vhost/namespace, provisioning, binding, routing type, ACL và capacity.
4. **Kiểm tra consumer:** listener factory, domain, subscription/durable/shared status, selector, connection và session transaction.
5. **Gửi event có ID kiểm chứng:** đặt business ID và correlation ID duy nhất, ghi timestamp an toàn.
6. **Quan sát ở broker:** queue depth/subscription backlog, số consumer, accepted/sent/enqueued counters, redelivery và DLQ.
7. **Kiểm tra end-to-end:** consumer có nhận và hoàn thành side effect không? Chỉ một log “send done” là chưa đủ.
8. **Test negative cases:** sai domain, thiếu binding, không có quyền, broker down, subscriber offline và timeout/expiration.

## 12. Java 17 chạy độc lập: mô phỏng lựa chọn Destination

Ví dụ dưới đây giúp nhìn trực quan khác biệt **explicit Destination** và **String được resolve theo domain**, không cần JMS jar hay broker. Đây chỉ là mô hình Java thuần; trong JMS thật, `Destination` là interface do provider cung cấp và tên có thể được ánh xạ JNDI.

Tạo tệp **`DestinationChoiceDemo.java`**:

```java
public final class DestinationChoiceDemo {
    enum Domain { QUEUE, TOPIC }

    record Address(String name, Domain domain) {}

    static Address resolve(String name, boolean pubSubDomain) {
        return new Address(
                name,
                pubSubDomain ? Domain.TOPIC : Domain.QUEUE);
    }

    static String describe(Address destination) {
        return destination.domain() + ":" + destination.name();
    }

    public static void main(String[] args) {
        Address explicit =
                new Address("billing.jobs", Domain.QUEUE);

        // Tên không đủ thông tin để quyết định domain.
        Address byNameQueue = resolve("orders.events", false);
        Address byNameTopic = resolve("orders.events", true);

        System.out.println("Explicit -> " + describe(explicit));
        System.out.println("Name, false -> " + describe(byNameQueue));
        System.out.println("Name, true -> " + describe(byNameTopic));
        System.out.println("Same name: " +
                byNameQueue.name().equals(byNameTopic.name()));
        System.out.println("Same domain: " +
                (byNameQueue.domain() == byNameTopic.domain()));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac DestinationChoiceDemo.java
java DestinationChoiceDemo
```

Đầu ra chính xác:

```text
Explicit -> QUEUE:billing.jobs
Name, false -> QUEUE:orders.events
Name, true -> TOPIC:orders.events
Same name: true
Same domain: false
```

Bài học rút ra từ demo:

- Explicit object đã chứa loại queue/topic (ở demo là enum).
- Một String name không đủ; domain flag hoặc resolver có chính sách rõ ràng mới xác định Queue/Topic.
- Hai destination cùng tên có thể khác domain, vì vậy so khớp chuỗi không phải xác minh routing.
- Demo **không** gửi message thật, không có JNDI, broker auto-create, transaction, headers hoặc JMS semantics. Mọi kiểm thử routing cuối cùng cần integration test với provider mục tiêu.

## 13. Bài tập thực hành với broker thực

### Bài 1 — Hai overload, cùng một Queue

1. Provision queue `billing.jobs` và tạo listener queue tương ứng.
2. Lấy `Queue` object của provider hoặc binding JNDI.
3. Gửi message A bằng `jmsTemplate.send(queueObject, creator)`.
4. Gửi message B bằng `jmsTemplate.send("billing.jobs", creator)` với DynamicDestinationResolver và `pubSubDomain=false`.
5. So sánh message ID, body và nơi listener nhận. Xác minh **cả hai đi cùng destination** nếu resolver/binding/provider đều tương đương.
6. Cố tình cấu hình tên sai để chứng minh string path không tự được kiểm chứng bằng object path.

### Bài 2 — Một tên, hai miền Queue/Topic

1. Tạo hai template, một có `pubSubDomain=false`, một có `true`.
2. Thử cùng tên `"demo.route"` trong môi trường thử nghiệm cho phép tạo cả hai loại.
3. Dùng admin console xác minh provider tạo/resolve hai loại destination riêng biệt, hoặc trả lỗi nếu broker cấm trùng tên/routing.
4. Cấu hình consumer queue và subscriber topic, quan sát hành vi.
5. Ghi nhận đây là **chi tiết provider**, không lấy kết quả của một broker làm quy tắc chung cho mọi broker.

### Bài 3 — JNDI mapping

1. Cấu hình binding `jms/queue/Invoice` tới physical queue của broker.
2. Dùng `JndiDestinationResolver` để gửi theo binding, xác minh đúng nơi nhận.
3. Đổi sang `DynamicDestinationResolver` và thử cùng String trong môi trường test: có thể map sang tên physical khác hoặc bị từ chối.
4. Giữ `fallbackToDynamicDestination=false` rồi xóa binding: thao tác phải báo lỗi lookup thay vì lặng lẽ dùng dynamic destination.
5. Nếu có cache, kiểm tra cơ chế refresh sau thay đổi binding; không đổi JNDI nóng mà chưa đánh giá.

### Bài 4 — Default destination

1. `setDefaultDestinationName("billing.jobs")` cho một template queue.
2. Gửi `convertAndSend("INV-10")` và `send(creator)`, xác nhận cả hai dùng default destination.
3. Xóa cấu hình default trong một phiên kiểm thử khác: xác minh overload không có đích báo lỗi.
4. Truyền explicit `Queue` khác vào `send(Destination, creator)`: xác minh explicit destination thay thế default cho lần gửi đó.

### Bài 5 — Reliability và failure

1. Gửi message có business ID; kiểm tra listener ghi trạng thái xử lý thành công.
2. Dừng consumer, gửi vào queue; quan sát backlog và TTL.
3. Mở lại consumer, cố tình ném exception trước commit; kiểm tra redelivery và business idempotency.
4. Với topic, dừng non-durable subscriber và publish; kiểm tra không kỳ vọng hồi tố.
5. Mất broker connection trước/during send: xác minh exception, chính sách retry và deduplication khi kết quả gửi không rõ.

## 14. Checklist cho code review và vận hành

Trước khi duyệt một lệnh gửi JMS trong Spring, hãy trả lời:

- [ ] **Đúng contract nghiệp vụ?** Queue để một nhóm xử lý công việc hay Topic cho nhiều subscription độc lập?
- [ ] **Đúng overload?** `send(Destination,...)`, `send(String,...)` hay `send(creator)` dùng default?
- [ ] **Nếu String, resolver nào?** Dynamic, JNDI hay custom? Có thể fail-fast khi tên không hợp lệ không?
- [ ] **Đúng pubSubDomain?** Producer và listener resolve String về cùng domain?
- [ ] **Đúng môi trường?** Broker endpoint, vhost/namespace, queue/topic resource và ACL?
- [ ] **Đúng tên/binding?** Tên ứng dụng, JNDI và physical provider name đã được phân biệt và ghi tài liệu?
- [ ] **Không auto-create nguy hiểm?** Có allowlist, quota và quyền giới hạn khi tên do dữ liệu đầu vào quyết định?
- [ ] **Default destination có chủ đích?** Không gọi overload không đích khi chưa cấu hình.
- [ ] **Body đúng schema?** MessageCreator hoặc MessageConverter phù hợp với consumer?
- [ ] **QoS rõ ràng?** Delivery mode, TTL, priority và `explicitQosEnabled` đúng yêu cầu?
- [ ] **Transaction/ack rõ ràng?** Gửi thành công không đồng nghĩa consumer xử lý thành công.
- [ ] **Có idempotency?** Redelivery/retry hoặc dual write có thể gây lặp/mất nghiệp vụ.
- [ ] **Quan sát được?** Log business ID và destination/domain mong đợi, broker counters, DLQ và alerting.
- [ ] **Cấu hình ổn định?** Không đổi template singleton theo từng request khi multi-thread.
- [ ] **Có test thực?** Cả đường explicit Destination và đường String đều được kiểm thử trên broker/provider thật.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Trong `jmsTemplate.send(queue, creator)`, `queue` là `jakarta.jms.Queue` object. Spring có nhất thiết phải gọi `DestinationResolver` để biến tên thành Queue object lần nữa không?

**Đáp án:** Không. Đường object đã có Destination, gửi trực tiếp đến object đó; resolver cần cho đường String name.

**Câu 2.** `JmsTemplate` mới không set `pubSubDomain`. Gửi `"orders.events"` bằng String qua DynamicDestinationResolver thì đây là Queue hay Topic?

**Đáp án:** Queue theo `pubSubDomain=false` mặc định. Đuôi tên “events” không tạo topic tự động.

**Câu 3.** `context.createQueue("billing.jobs")` có bảo đảm broker đã tạo physical queue và cấp send permission không?

**Đáp án:** Không. API tạo object handle theo tên provider-specific; provisioning và quyền thuộc provider/administration.

**Câu 4.** `jmsTemplate.convertAndSend("invoice-42")` có nghĩa gửi tới destination tên `invoice-42` không?

**Đáp án:** Không. Một tham số là **payload**; đích là default destination đã cấu hình. Với hai tham số `convertAndSend("billing.jobs", "invoice-42")` thì tham số đầu là destination name.

**Câu 5.** `send(String, creator)` lúc nào cũng dùng JNDI lookup?

**Đáp án:** Không. Resolver mặc định là DynamicDestinationResolver. Chỉ dùng JNDI khi cấu hình resolver phù hợp, chẳng hạn JndiDestinationResolver.

**Câu 6.** `JndiDestinationResolver` tìm tên không có trong JNDI. Theo mặc định nó có tự fallback sang dynamic không?

**Đáp án:** Không. `fallbackToDynamicDestination` mặc định false; phải bật rõ nếu thực sự muốn.

**Câu 7.** Đổi `setPubSubDomain(true)` trên JmsTemplate có biến object `Queue` truyền thẳng vào `send(queue, creator)` thành `Topic` không?

**Đáp án:** Không. Domain flag chủ yếu dùng khi resolve **tên**; object Queue giữ nguyên loại.

**Câu 8.** Vì sao message có thể được gửi thành công nhưng topic listener vẫn không nhận?

**Đáp án:** Có thể sai domain, nhầm JNDI/physical resource, subscription non-durable chưa tồn tại khi publish, message expire, selector không khớp hoặc listener/transaction/broker gặp lỗi. Phải kiểm tra cả sender, resolver, broker và subscriber.

**Câu 9.** Với một ứng dụng cần gửi cả Queue và Topic bằng String, có nên dùng một singleton JmsTemplate rồi luân phiên đổi `pubSubDomain` theo request không?

**Đáp án:** Không nên. Có rủi ro race condition/misrouting trong ứng dụng concurrent. Dùng hai template được cấu hình ổn định hoặc explicit Destination object.

**Câu 10.** String payload chuyển sang `TextMessage` là quyết định của DestinationResolver hay MessageConverter?

**Đáp án:** MessageConverter, ví dụ SimpleMessageConverter mặc định. Resolver chỉ xác định destination.

**Câu 11.** Dùng `setDeliveryMode(PERSISTENT)` nhưng không `setExplicitQosEnabled(true)`, có chắc override của JmsTemplate đã được dùng khi send không?

**Đáp án:** Chưa chắc. Phải bật explicit QoS nếu cần template áp dụng setting; xác minh provider behavior trong integration test.

**Câu 12.** Một event đã publish, nhưng service ghi DB rồi crash trước khi gửi JMS. Lỗi thuộc DestinationResolver không?

**Đáp án:** Không. Đây là bài toán dual write; cần transaction/outbox hoặc phối hợp nhất quán, độc lập với cách resolve tên.

## Kết luận

- `Destination` là **địa chỉ gửi JMS**; Queue/Topic quyết định semantics phân phối.
- Với Spring, **`send(Destination, ...)`** dùng object đã có; **`send(String, ...)`** thêm bước `DestinationResolver` để tìm/tạo object từ tên.
- `DynamicDestinationResolver` là mặc định; `pubSubDomain=false` chọn Queue và `true` chọn Topic **khi phân giải tên**.
- `JndiDestinationResolver` tra binding do vận hành cung cấp; fallback dynamic không bật mặc định.
- `createQueue(String)` và `createTopic(String)` tạo handle, **không hứa provision physical resource**.
- `send(...)` tạo message qua `MessageCreator`; `convertAndSend(...)` chuyển payload qua `MessageConverter`; QoS, transaction và business idempotency là các mối quan tâm riêng.
- Chọn đúng overload và cấu hình rõ producer, listener, broker, ACL, schema để tránh “gửi đúng tên nhưng sai nơi”.

### Tài liệu tham khảo chính thức

1. [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): `JmsTemplate.send`/`convertAndSend`, default destination, callback, converter và post-processor.
2. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `DestinationResolver`, `DynamicDestinationResolver`, `JndiDestinationResolver`, `pubSubDomain`, connection và QoS.
3. [Spring JMS – JmsOperations API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsOperations.html): các overload nhận `Destination`, `String` và default destination.
4. [Spring JMS – DestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html): contract `resolveDestinationName(Session, String, boolean)`.
5. [Spring JMS – JndiDestinationResolver](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html): JNDI lookup, cache và fallback.
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Destination`, `JMSProducer`, `MessageProducer`, queue/topic, delivery mode và producer send contract.
7. [Jakarta Messaging 3.1 – JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): `createQueue(String)`, `createTopic(String)` và quản lý provider-specific destination handles.
