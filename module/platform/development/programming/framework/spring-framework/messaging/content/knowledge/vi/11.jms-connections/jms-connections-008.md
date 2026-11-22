# pubSubDomain và phân giải Queue hoặc Topic

## Mục tiêu

Trong Spring JMS, cùng một tên như `orders.in` có thể được dùng để chỉ một Queue hoặc một Topic. Spring cần biết ứng dụng đang làm việc trong domain nào để phân giải tên thành đúng loại JMS `Destination`. Thuộc tính `pubSubDomain` cung cấp thông tin đó cho `JmsTemplate` và listener container.

Sau bài này, bạn có thể:

- Giải thích `pubSubDomain` điều khiển việc phân giải destination như thế nào.
- Biết giá trị mặc định và phạm vi tác động của thuộc tính.
- Phân biệt phân giải tên String với việc truyền trực tiếp một `Destination` object.
- Cấu hình `JmsTemplate`, `DefaultJmsListenerContainerFactory` và `@JmsListener` cho Queue hoặc Topic.
- Cấu hình Spring Boot và ứng dụng sử dụng đồng thời cả hai domain.
- Nhận diện lỗi khi sender và receiver dùng sai domain.

## 1. Queue và Topic là hai JMS domain

Jakarta Messaging định nghĩa hai loại destination phổ biến:

- **Queue (point-to-point):** các consumer trên cùng Queue cạnh tranh nhận message; mỗi lần giao một message chỉ được phân phối cho một consumer.
- **Topic (publish/subscribe):** mỗi subscription độc lập nhận một bản sao của message đã publish lên Topic. Nhiều consumer cùng shared subscription có thể chia nhau các message của subscription đó.

Queue và Topic đều triển khai `jakarta.jms.Destination`, nhưng chúng thuộc hai domain khác nhau. Cùng một chuỗi tên không làm cho Queue và Topic trở thành cùng một đích đến.

Ví dụ:

~~~text
Queue domain:
Producer -> orders.in -> một consumer trong nhóm nhận mỗi message

Topic domain:
Publisher -> orders.events -> subscription A
                           -> subscription B
                           -> subscription C
Mỗi subscription độc lập nhận một bản sao.
~~~

Spring JMS cần chọn đúng domain khi nó chỉ được cung cấp tên destination dạng String. Đó là vai trò chính của `pubSubDomain`.

## 2. pubSubDomain là gì?

`pubSubDomain` là thuộc tính boolean trên lớp `JmsDestinationAccessor`, được dùng bởi `JmsTemplate` và các lớp listener container.

| Giá trị | JMS domain | Loại destination được tạo khi phân giải động |
|---|---|---|
| `false` | Point-to-point | Queue |
| `true` | Publish/subscribe | Topic |

Giá trị mặc định là `false`, tức Queue domain.

Cấu hình trên `JmsTemplate`:

~~~java
JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setPubSubDomain(false); // Queue, cũng là mặc định

JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setPubSubDomain(true);  // Topic
~~~

Tên thuộc tính dễ khiến người đọc nghĩ nó bật hoặc tắt cơ chế publish/subscribe nói chung. Chính xác hơn, nó cho biết JMS domain mà accessor đang sử dụng, đặc biệt khi destination được phân giải động từ tên String.

## 3. pubSubDomain tham gia vào bước phân giải tên

Khi ứng dụng gọi phương thức nhận tên destination dạng String, Spring sử dụng `DestinationResolver` để lấy JMS `Destination` object.

Hợp đồng resolver có dạng:

~~~java
Destination resolveDestinationName(
    Session session,
    String destinationName,
    boolean pubSubDomain
) throws JMSException;
~~~

Resolver nhận ba thông tin:

- `session`: JMS Session dùng để phân giải, nếu resolver cần đến nó.
- `destinationName`: tên Queue hoặc Topic.
- `pubSubDomain`: `false` cho Queue và `true` cho Topic.

Với `DynamicDestinationResolver`, Spring thực hiện tương đương:

~~~java
if (pubSubDomain) {
    return session.createTopic(destinationName);
}
return session.createQueue(destinationName);
~~~

Đây là mã giả minh họa quyết định của resolver. `Session.createQueue(name)` và `Session.createTopic(name)` tạo đối tượng JMS đại diện cho tên destination. Theo Jakarta Messaging, hai phương thức đó không tự provision tài nguyên vật lý trên broker. Broker có thể tự tạo tài nguyên khi được sử dụng nếu chính sách auto-create của provider cho phép.

## 4. Phạm vi tác động: tên String và Destination object

Đây là điểm quan trọng nhất khi cấu hình.

### 4.1. Truyền tên String

Khi truyền tên String, Spring cần resolver để tạo hoặc tra cứu Destination object:

~~~java
// pubSubDomain=false: resolve "orders.in" thành Queue.
queueTemplate.convertAndSend("orders.in", payload);

// pubSubDomain=true: resolve "orders.events" thành Topic.
topicTemplate.convertAndSend("orders.events", event);
~~~

Với dynamic resolver, giá trị `pubSubDomain` quyết định Spring gọi `Session.createQueue` hay `Session.createTopic`.

Các thao tác nhận bằng tên String cũng cần domain tương ứng:

~~~java
Object queueMessage = queueTemplate.receive("orders.in");
Object topicMessage = topicTemplate.receive("orders.events");
~~~

### 4.2. Truyền Destination object trực tiếp

Nếu ứng dụng đã có một đối tượng `Queue` hoặc `Topic`, có thể truyền trực tiếp:

~~~java
import jakarta.jms.Queue;
import jakarta.jms.Topic;

import org.springframework.jms.core.JmsTemplate;

public class DestinationObjectExample {
    private final JmsTemplate queueTemplate;
    private final JmsTemplate topicTemplate;
    private final Queue ordersQueue;
    private final Topic ordersTopic;

    public DestinationObjectExample(
            JmsTemplate queueTemplate,
            JmsTemplate topicTemplate,
            Queue ordersQueue,
            Topic ordersTopic) {
        this.queueTemplate = queueTemplate;
        this.topicTemplate = topicTemplate;
        this.ordersQueue = ordersQueue;
        this.ordersTopic = ordersTopic;
    }

    public void publish(Object payload, Object event) {
        queueTemplate.convertAndSend(ordersQueue, payload);
        topicTemplate.convertAndSend(ordersTopic, event);
    }
}
~~~

Trong trường hợp này, chính kiểu và giá trị của Destination object xác định đích đến. `pubSubDomain` không biến Queue object thành Topic object hoặc ngược lại; Spring không cần phân giải tên String cho overload nhận object.

Điều đó cũng có nghĩa một template được cấu hình Queue domain vẫn có thể làm việc với một Topic object nếu ứng dụng truyền trực tiếp object đó và provider hỗ trợ thao tác tương ứng. Tuy nhiên, để code dễ hiểu và tránh nhầm lẫn, nên dùng template có cấu hình phù hợp với domain dự kiến.

## 5. Ảnh hưởng của DestinationResolver

`pubSubDomain` chỉ có tác dụng khi resolver sử dụng thông tin domain để phân giải tên. Các resolver phổ biến có cách xử lý khác nhau.

| Resolver | Cách phân giải | Vai trò của pubSubDomain |
|---|---|---|
| `DynamicDestinationResolver` | Gọi `Session.createQueue` hoặc `Session.createTopic` | Quyết định trực tiếp Queue hay Topic |
| `SimpleDestinationResolver` | Dynamic resolution và cache Destination object theo tên | Domain được dùng khi tạo object; cache tái sử dụng kết quả |
| `JndiDestinationResolver` | Tra cứu administered object theo tên JNDI | Kiểu object đã đăng ký quyết định Queue/Topic; flag chủ yếu liên quan fallback dynamic |
| Custom resolver | Theo logic do ứng dụng triển khai | Phải xử lý tham số domain đúng theo hợp đồng nếu cần hỗ trợ cả hai loại |

### 5.1. DynamicDestinationResolver

Resolver này phân giải tên bằng JMS Session:

- `pubSubDomain=false`: tạo Queue object.
- `pubSubDomain=true`: tạo Topic object.

Nó là lựa chọn phù hợp khi ứng dụng dùng tên động và provider hỗ trợ cách phân giải tương ứng.

### 5.2. SimpleDestinationResolver

Resolver này kế thừa cơ chế dynamic resolution và cache các Destination object theo tên. Trong các phiên bản Spring Framework mới, đây là resolver mặc định của nhiều JMS accessor. Cache giúp tái sử dụng object đã phân giải.

Khi ứng dụng dùng cả Queue và Topic có cùng chuỗi tên, cần bảo đảm resolver hoặc cache được sử dụng theo đúng domain và cấu hình. Cách đơn giản là dùng tên rõ nghĩa, template riêng và resolver phù hợp.

### 5.3. JndiDestinationResolver

Resolver này tra cứu một administered object đã được đăng ký trong JNDI. Ví dụ tên JNDI có thể là:

~~~text
java:comp/env/jms/OrdersQueue
java:comp/env/jms/OrdersTopic
~~~

JNDI lookup trả về object đã đăng ký. `pubSubDomain` không chuyển đổi object đó; nếu object là Queue thì nó vẫn là Queue, nếu là Topic thì nó vẫn là Topic.

Nếu bật fallback sang dynamic resolution, flag domain sẽ được dùng khi resolver cần tạo destination theo tên sau khi lookup không thành công. Fallback thường nên được cấu hình có chủ đích để tránh che giấu lỗi tên JNDI trong production.

## 6. Cấu hình JmsTemplate cho Queue và Topic

`JmsTemplate` mặc định dùng Queue domain. Để gửi hoặc nhận từ Topic bằng tên String, đặt `pubSubDomain=true`.

Ví dụ tạo hai template:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsTemplateConfiguration {

    @Bean
    JmsTemplate queueJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean
    JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Sử dụng:

~~~java
queueJmsTemplate.convertAndSend("orders.in", new OrderCreated("order-42"));
topicJmsTemplate.convertAndSend("orders.events", new OrderCreated("order-42"));
~~~

Hai template có thể cùng dùng một `ConnectionFactory`, nhưng giữ cấu hình domain riêng giúp người đọc thấy ngay ý định gửi tới Queue hay Topic.

Không nên thay đổi `pubSubDomain` liên tục trên một template singleton trong lúc ứng dụng đang xử lý nhiều request. Đây là thuộc tính cấu hình của template. Khi ứng dụng cần cả hai domain, hãy tạo hai bean hoặc truyền Destination object đúng loại.

## 7. Cấu hình listener container cho Queue và Topic

`@JmsListener` nhận destination dưới dạng tên String. Loại destination được xác định bởi listener container factory mà endpoint sử dụng.

`DefaultJmsListenerContainerFactory` có phương thức `setPubSubDomain(boolean)`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Gắn đúng factory cho từng listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListeners {

    @JmsListener(
        destination = "orders.in",
        containerFactory = "queueListenerFactory"
    )
    public void handleQueueOrder(OrderCreated order) {
        // Một consumer trong nhóm Queue xử lý message.
    }

    @JmsListener(
        destination = "orders.events",
        containerFactory = "topicListenerFactory"
    )
    public void observeOrderEvent(OrderCreated event) {
        // Subscription của listener nhận bản sao từ Topic.
    }
}
~~~

Nếu bỏ `containerFactory`, Spring dùng factory mặc định theo cấu hình listener endpoint. Nếu factory đó đang ở Queue domain, một listener có destination String sẽ được phân giải theo Queue domain.

Bản thân annotation `@JmsListener` không có thuộc tính `pubSubDomain`. Hãy đặt domain trên factory được endpoint sử dụng.

## 8. Cấu hình Spring Boot

Spring Boot cung cấp thuộc tính:

~~~properties
spring.jms.pub-sub-domain=true
~~~

Với JMS auto-configuration, thuộc tính này cấu hình domain mặc định cho `JmsTemplate` và listener container được auto-configure. Giá trị mặc định là `false`, tức Queue.

Ví dụ dùng Topic làm domain mặc định:

~~~yaml
spring:
  jms:
    pub-sub-domain: true
~~~

Điều cần kiểm tra:

- Sender và receiver phải dùng cùng domain.
- Nếu dùng custom `JmsTemplate`, đặt `setPubSubDomain` rõ ràng trên bean đó.
- Nếu tự tạo `DefaultJmsListenerContainerFactory`, đặt `setPubSubDomain` rõ ràng hoặc cấu hình factory qua Boot configurer phù hợp.
- Nếu ứng dụng dùng cả Queue và Topic, tạo template và listener factory riêng cho từng domain thay vì cố dùng một giá trị mặc định chung.

Thuộc tính Boot là cấu hình mặc định cho hạ tầng được auto-configure. Nó không tự biến mọi Queue thành Topic và không thay thế cấu hình của các bean tùy chỉnh.

## 9. pubSubDomain không điều khiển những gì?

Một số cấu hình JMS khác có thể bị nhầm với `pubSubDomain`:

| Cấu hình | Điều khiển | Có được quyết định bởi pubSubDomain không? |
|---|---|---|
| Queue/Topic domain | Loại destination khi phân giải tên động | Có |
| Durable subscription | Có giữ message cho subscriber khi offline hay không | Không |
| Shared subscription | Nhiều consumer có chia sẻ một subscription hay không | Không |
| Delivery mode | Persistent hay non-persistent message | Không |
| Message selector | Lọc message theo header/property | Không |
| MessageConverter | Chuyển đổi payload và Message | Không |
| Acknowledgement/transaction | Xác nhận hoặc rollback việc nhận message | Không |
| Broker auto-create | Broker có tự tạo tài nguyên vật lý hay không | Không |

Ví dụ, đặt `pubSubDomain=true` chỉ chọn Topic domain khi resolver cần phân giải tên. Nó không tự tạo durable subscription. Muốn nhận message khi subscriber offline, cần cấu hình durable subscription và provider phù hợp.

Tương tự, `pubSubDomain=true` không tự bật persistent delivery. Delivery mode là chính sách gửi message riêng.

## 10. Lỗi do sender và receiver dùng khác domain

Giả sử producer gửi:

~~~java
queueJmsTemplate.convertAndSend("orders.events", event);
~~~

nhưng listener lại dùng factory Topic domain:

~~~java
@JmsListener(
    destination = "orders.events",
    containerFactory = "topicListenerFactory"
)
public void receive(OrderCreated event) {
    // ...
}
~~~

Producer đã phân giải tên thành Queue; listener phân giải cùng tên thành Topic. Dù chuỗi tên giống nhau, hai phía có thể đang làm việc với hai destination khác nhau. Kết quả là listener không nhận message từ Queue mà producer đã gửi.

Các tình huống tương tự:

- Producer cấu hình Topic nhưng consumer dùng Queue.
- Spring Boot property đặt Topic nhưng custom listener factory vẫn dùng Queue.
- Listener dùng default factory không đúng domain.
- JNDI binding trỏ tới Queue trong khi ứng dụng mong Topic.
- Một custom DestinationResolver bỏ qua tham số `pubSubDomain`.
- Tên Queue/Topic đúng nhưng broker chưa provision tài nguyên hoặc principal thiếu quyền.

Cách kiểm tra:

1. Xác định sender truyền tên String hay Destination object.
2. Xác định `pubSubDomain` của template đang gửi.
3. Xác định `containerFactory` mà listener đang sử dụng.
4. Kiểm tra `pubSubDomain` của factory.
5. Kiểm tra resolver và loại Destination object mà resolver trả về.
6. Kiểm tra tài nguyên vật lý, JNDI binding, auto-create policy và quyền trên broker.

## 11. Khi ứng dụng cần cả Queue và Topic

Một service có thể vừa gửi command vào Queue, vừa publish event lên Topic. Ví dụ:

- `orders.commands`: các worker chia nhau xử lý command.
- `orders.events`: Billing, Analytics và Notification có subscription độc lập.

Thiết kế dễ đọc:

~~~text
Order Service
   | 
   +-- queueJmsTemplate (pubSubDomain=false)
   |       |
   |       v
   |   orders.commands
   |
   +-- topicJmsTemplate (pubSubDomain=true)
           |
           v
       orders.events
           |
           +--> Billing subscription
           +--> Analytics subscription
           +--> Notification subscription
~~~

Ở chiều nhận, tạo một queue listener factory và một topic listener factory. Đặt tên bean thể hiện domain để tránh vô tình chọn nhầm factory trong `@JmsListener`.

Nếu Topic cần durable subscription, cấu hình thêm subscription name, durable flag và client ID theo yêu cầu của JMS provider. Không suy ra durable chỉ từ `pubSubDomain=true`.

## 12. Kiểm thử cấu hình domain

Nên kiểm thử cả sender lẫn receiver bằng broker/provider được dùng trong môi trường thực tế hoặc một embedded broker tương thích.

Các trường hợp nên có:

- Queue template gửi tới Queue và Queue listener nhận được message.
- Topic template publish và hai subscription độc lập đều nhận được bản sao.
- Queue template và Topic listener dùng cùng chuỗi tên nhưng không nhận nhầm message của nhau.
- Listener dùng sai factory được phát hiện trong test cấu hình.
- JNDI resolver trả về đúng loại Destination.
- Custom resolver nhận và xử lý đúng giá trị `pubSubDomain`.
- Cấu hình Boot và custom factory không vô tình ghi đè domain dự kiến.

Khi test, kiểm tra cả broker destination hoặc subscription đang hoạt động. Chỉ kiểm tra chuỗi tên trong annotation chưa đủ để chứng minh Spring đã tạo đúng loại consumer.

## 13. Lỗi thường gặp

- **Cho rằng `pubSubDomain=true` chỉ bật tính năng pub/sub:** nó chọn Topic domain khi phân giải destination.
- **Quên giá trị mặc định là false:** tên String sẽ được phân giải theo Queue domain.
- **Chỉ đặt flag trên JmsTemplate:** listener container có cấu hình riêng và cũng phải dùng đúng domain.
- **Dùng chung một template cho Queue và Topic rồi đổi flag khi chạy:** dễ tạo cấu hình không nhất quán giữa các thao tác.
- **Nghĩ `@JmsListener` có thuộc tính pubSubDomain:** domain nằm ở listener container factory.
- **Cho rằng flag đổi được Destination object đã có:** object được truyền trực tiếp vẫn giữ loại Queue hoặc Topic ban đầu.
- **Cho rằng JNDI resolver sẽ đổi Queue thành Topic:** JNDI lookup trả về administered object đã đăng ký.
- **Bật Topic domain và nghĩ subscription tự durable:** durable là cấu hình subscription riêng.
- **Chỉ cấu hình Spring Boot property nhưng bỏ qua custom factory:** bean tự tạo cần được cấu hình domain rõ ràng.
- **Dùng cùng chuỗi tên và nghĩ hai phía chắc chắn cùng destination:** Queue và Topic là hai domain riêng.

## 14. Checklist triển khai

- [ ] Đã xác định destination cần là Queue hay Topic.
- [ ] Đã biết `pubSubDomain` mặc định là `false`.
- [ ] Đã xác định code truyền tên String hay Destination object.
- [ ] Nếu dùng String, resolver nhận đúng giá trị domain.
- [ ] `JmsTemplate` sender được cấu hình đúng domain.
- [ ] Listener container factory được cấu hình đúng domain.
- [ ] Mỗi `@JmsListener` dùng đúng `containerFactory`.
- [ ] Spring Boot property phù hợp với domain mặc định của ứng dụng.
- [ ] Ứng dụng dùng cả hai domain có template/factory riêng.
- [ ] JNDI binding hoặc custom resolver trả đúng loại Destination.
- [ ] Durable/shared subscription được cấu hình riêng khi cần.
- [ ] Đã kiểm thử sender, receiver và trạng thái destination trên broker.

## 15. Tài liệu tham khảo

- [Spring Framework — JmsDestinationAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
- [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework — DestinationResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html)
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
