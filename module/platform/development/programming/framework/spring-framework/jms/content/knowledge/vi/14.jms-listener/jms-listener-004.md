# Khai báo destination và containerFactory trong @JmsListener (Spring Framework JMS)

## Mục tiêu học tập

Trong Spring Framework, `@JmsListener` đánh dấu một phương thức của **Spring-managed bean** làm điểm nhận thông điệp JMS bất đồng bộ. Hai thuộc tính quyết định hành vi của endpoint là:

- **`destination`**: *listener nhận message ở đâu?* Đây là tên destination được giải quyết thành `jakarta.jms.Queue` hoặc `jakarta.jms.Topic` theo chiến lược của listener container.
- **`containerFactory`**: *listener được tạo và vận hành bằng cấu hình nào?* Đây là **tên bean Spring** triển khai `JmsListenerContainerFactory`, được dùng để tạo `MessageListenerContainer` tương ứng.

Bài này tập trung trực tiếp vào **khai báo destination và containerFactory**. Kết thúc bài, bạn có thể:

1. Viết đúng `@JmsListener(destination = "...")` và `@JmsListener(destination = "...", containerFactory = "...")`.
2. Giải thích cơ chế `@EnableJms`, `JmsListenerAnnotationBeanPostProcessor`, `JmsListenerContainerFactory` và `JmsListenerEndpointRegistry` ở mức đủ để cấu hình, gỡ lỗi.
3. Phân biệt **tên destination**, **bean `Destination`**, **tên bean container factory** và **container instance** thực sự đang chạy.
4. Dùng factory mặc định tên `jmsListenerContainerFactory` hoặc tạo nhiều factory theo broker, Queue/Topic, transactions, concurrency, selector, converter và chính sách.
5. Khai báo destination từ `application.properties` bằng `${...}`, hiểu giới hạn của tên tính tại startup và chuyện broker provisioning/ACL.
6. Dùng Spring Boot 3.5 và `DefaultJmsListenerContainerFactoryConfigurer` để kế thừa cấu hình mặc định mà không bỏ sót những thiết lập quan trọng.
7. Chạy demo Java 17 nhận message trên **hai queue** với **hai factory khác nhau**, một factory có JMS selector.
8. Xử lý lỗi như bean name sai, Queue/Topic mismatch, không có listener, message đã ACK nhưng business thất bại, duplicate và cấu hình concurrency không phù hợp.

> **Nguyên tắc:** `destination` chọn *nguồn message*; `containerFactory` chọn *cách listener vận hành*. **`destination` không tự tạo một queue vật lý theo cam kết của Spring**, và **`containerFactory` không phải là class Java hay tên broker**.

## 1. Sơ đồ hoạt động

Một annotation ngắn:

~~~java
@Component
class OrderListener {
    @JmsListener(
        destination = "orders.commands",
        containerFactory = "ordersListenerFactory")
    public void onMessage(String payload) {
        System.out.println(payload);
    }
}
~~~

khi ứng dụng khởi động sẽ tạo cấu trúc logic như sau:

~~~text
Spring ApplicationContext
  |
  +--- @EnableJms bật hạ tầng annotation
  |
  +--- @Component OrderListener
  |      |
  |      +--- @JmsListener onMessage(...)
  |                destination = "orders.commands"
  |                containerFactory = "ordersListenerFactory"
  |
  +--- @Bean(name = "ordersListenerFactory")
  |      DefaultJmsListenerContainerFactory
  |                |
  |                +--- ConnectionFactory
  |                +--- DestinationResolver
  |                +--- MessageConverter
  |                +--- sessionTransacted / transactionManager
  |                +--- concurrency / error handler / selector
  |                |
  |                v
  |       tạo MessageListenerContainer riêng
  |                |
  |                +--- JMS Session + MessageConsumer
  |                +--- subscription tới destination
  |                |
  |                v
  |       Broker queue "orders.commands"
  |
  +--- JmsListenerEndpointRegistry quản lý container
~~~

Spring Framework tài liệu **Annotation-driven Listener Endpoints** xác nhận một container được tạo cho mỗi annotated endpoint thông qua `JmsListenerContainerFactory`. Container do `JmsListenerEndpointRegistry` quản lý; container đó không nhất thiết xuất hiện như một bean container độc lập thông thường trong ApplicationContext.

### Trách nhiệm tách biệt

| Thành phần | Chức năng |
|---|---|
| `@JmsListener` | Khai báo phương thức, tên destination, factory được dùng và một số override theo endpoint. |
| `@EnableJms` | Kích hoạt cơ chế phát hiện và đăng ký listener annotation. |
| `JmsListenerContainerFactory` | Tạo message listener container với các thiết lập đã định. |
| `DefaultJmsListenerContainerFactory` | Factory thường dùng, tạo `DefaultMessageListenerContainer` theo cấu hình Spring JMS. |
| `DestinationResolver` | Biến tên String thành `Queue` hoặc `Topic` thông qua JMS Session/JNDI. |
| `ConnectionFactory` | Cấp connection tới broker JMS. |
| `MessageListenerContainer` | Quản lý consumer/session, lifecycle, polling thread, xử lý lỗi, nhận và dispatch message. |
| `JmsListenerEndpointRegistry` | Truy xuất, start/stop, theo dõi các container của annotated endpoints. |
| JMS broker | Thực sự quản lý address/queue/topic, routing, ACL, retention, TTL, DLQ và durable subscriptions. |

Không nên đổ mọi vấn đề vào một annotation. Ví dụ, `destination="orders.commands"` có thể đúng chính tả nhưng broker chưa provision queue, không cấp quyền consume hoặc đang định tuyến kiểu Topic.

## 2. Cú pháp tối thiểu của `destination`

### 2.1. Khai báo trực tiếp một JMS queue

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.commands")
    public void handle(String body) {
        System.out.println("orders=" + body);
    }
}
~~~

Đây là **một file class Java** cần có ứng dụng Spring, JMS dependencies và hạ tầng listener thích hợp; tự chạy riêng với `javac` khi không có classpath Spring sẽ không được.

`destination` nhận một **String**. Nếu listener factory đang ở mặc định `pubSubDomain=false`, tên đó được hiểu theo **JMS Queue semantics**. Tên có chữ `.events` không tự biến nó thành Topic; tên có chữ `.queue` cũng không có khả năng thay đổi kiểu JMS.

### 2.2. Chọn factory bằng `containerFactory`

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
public void handle(String payload) {
    // Business processing.
}
~~~

Ở đây `containerFactory="ordersListenerFactory"` là **bean name** cần có trong Spring context, không phải:

- `org.springframework.jms.config.DefaultJmsListenerContainerFactory` — tên một class.
- `orders.commands` — tên destination.
- `"tcp://localhost:61616"` — broker URL.
- `"jmsListenerContainerFactory"` — tên mặc định trừ khi bạn chủ ý dùng nó.

Nếu bean `ordersListenerFactory` không tồn tại hoặc không là loại factory phù hợp, Spring thường báo lỗi khi đăng ký listener/start application. Không tự động tạo bean chỉ vì annotation có chuỗi tên đó.

### 2.3. Annotation chỉ có ý nghĩa trên Spring bean được quét

~~~java
public class OutsideSpring {
    @JmsListener(destination = "orders.commands")
    void receive(String msg) { }
}
~~~

Class không phải bean Spring sẽ **không** được đăng ký chỉ vì có annotation. Đưa class vào component scan qua `@Component`, khai báo `@Bean`, hoặc cấu hình bean theo cơ chế Spring. Đồng thời kích hoạt hạ tầng listener bằng `@EnableJms` hoặc auto-configuration phù hợp; trong các ví dụ bài này đặt `@EnableJms` để minh bạch.

## 3. `destination` thực sự được giải quyết thế nào?

### 3.1. Một String không tương đương tài nguyên vật lý

Với resolver động mặc định, cơ chế khái niệm là:

~~~java
// MÃ MINH HỌA Ý TƯỞNG resolver, không phải source copy của Spring.
Destination resolve(
        Session session, String name, boolean pubSubDomain)
        throws JMSException {
    return pubSubDomain
            ? session.createTopic(name)
            : session.createQueue(name);
}
~~~

`Session.createQueue` và `Session.createTopic` tạo một **đối tượng đại diện destination theo provider**, không phải API chuẩn để bảo đảm queue vật lý đã được cấp phát trên broker.

Khi listener container tạo consumer, broker có thể:

- Kết nối tới queue/topic đã được provision sẵn.
- Auto-create address/queue nếu được cấu hình và client có quyền.
- Từ chối consumer hoặc báo destination không tồn tại.
- Áp dụng routing, subscription, selector và permission khác với dự kiến.

Đây là hành vi broker/provider, không phải Spring tự đảm bảo. Trong production thường nên provision tài nguyên bằng cấu hình/IaC/management API và xác minh ACL.

### 3.2. `pubSubDomain` quyết định Queue hay Topic

| Cấu hình factory | `destination` | JMS semantics |
|---|---|---|
| `factory.setPubSubDomain(false)` | `"orders.commands"` | Queue, point-to-point |
| `factory.setPubSubDomain(true)` | `"orders.events"` | Topic, publish/subscribe |

Nếu cùng tên String nhưng producer gửi qua Queue còn listener subscribe như Topic, hai bên **không mặc nhiên gặp nhau**.

~~~text
Producer JmsTemplate: pubSubDomain=false
   "orders.events" -> Queue

ListenerFactory: pubSubDomain=true
   "orders.events" -> Topic

Cùng String, KHÁC loại JMS Destination!
~~~

Tránh đặt một topic listener dựa trên tên queue chỉ vì nó kết thúc bằng `.events`. Kiểm tra **cả producer và listener factory**.

### 3.3. `DynamicDestinationResolver` và `JndiDestinationResolver`

Spring có hai chiến lược phổ biến:

- **`DynamicDestinationResolver`**: gọi `Session.createQueue` hoặc `createTopic` theo `pubSubDomain`.
- **`JndiDestinationResolver`**: tra một `Destination` từ JNDI với tên quy định; có thể cấu hình cache và dynamic fallback theo API riêng.

Nếu môi trường doanh nghiệp yêu cầu destination đăng ký JNDI, dùng resolver JNDI hoặc inject trực tiếp `Destination` thay vì suy rằng tên trong annotation được JNDI tra cứu mặc định. Với `JndiDestinationResolver`, bật fallback về dynamic có thể che lỗi JNDI và phụ thuộc broker auto-create; đánh giá theo policy.

### 3.4. Tên destination có thể được cấu hình từ properties

`@JmsListener.destination` trong Spring hỗ trợ property placeholder theo cơ chế annotation processing:

~~~java
@JmsListener(
    destination = "${app.jms.orders-queue}",
    containerFactory = "ordersListenerFactory")
public void handle(String body) { }
~~~

Trong `application.properties`:

~~~properties
app.jms.orders-queue=dev.orders.commands
~~~

Lợi ích: code không hard-code environment-specific queue. Lưu ý:

- Placeholder phải được Spring resolve trong ngữ cảnh cấu hình.
- Giá trị sai/thiếu có thể khiến endpoint không đăng ký hoặc consumer startup lỗi.
- Đổi property ở runtime **không mặc nhiên di chuyển listener container** sang queue khác ngay lập tức.
- Không nối trực tiếp user-input/tenantId vào destination mà không kiểm tra; khi broker auto-create, typo hoặc input tùy ý có thể sinh hàng nghìn queue không mong muốn.
- Property key `app.jms.*` ở đây là **do ứng dụng định nghĩa**, không phải built-in `spring.jms.*`.

Spring có hỗ trợ expression resolution tùy tình huống, nhưng với nhu cầu cấu hình theo môi trường, `${...}` thường dễ đọc/kiểm thử hơn. Endpoint thường được đăng ký khi Spring khởi tạo, **không tính lại tên cho từng message**.

## 4. `containerFactory`: không phải tên container mà là factory bean

### 4.1. Contract

Annotation:

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
~~~

nghĩa là Spring đi tìm một **bean tên `ordersListenerFactory`** triển khai `JmsListenerContainerFactory` để tạo `MessageListenerContainer` tương ứng. Đừng đặt `containerFactory` thành tên một listener method hoặc một object `ConnectionFactory`.

Một factory có thể phục vụ **nhiều annotated listeners**. Mỗi listener endpoint sẽ có **container riêng** được factory tạo ra, không phải cả chục listener cùng sử dụng đúng **một instance container**.

~~~text
ordersListenerFactory (một bean)
      |
      +--- @JmsListener(destination="orders.commands")
      |         -> Container A
      |
      +--- @JmsListener(destination="orders.retry")
                -> Container B
~~~

Hai container có thể dùng cùng `ConnectionFactory` nhưng có lifecycle/consumer riêng. Nếu cùng Queue, chúng là competing consumers, không có nghĩa một message được giao cho cả hai.

### 4.2. Factory mặc định

Nếu annotation **không khai báo** `containerFactory`:

~~~java
@JmsListener(destination = "orders.commands")
public void receive(String text) { }
~~~

Spring listener infrastructure mặc định tìm bean mang tên:

~~~text
jmsListenerContainerFactory
~~~

Đây là **tên bean mặc định**, không phải tên class. Với Spring Boot và JMS infrastructure đủ điều kiện, Boot có thể auto-configure factory mặc định; tuy vậy không nên suy rằng một bean tự định nghĩa tên bất kỳ sẽ luôn thay thế chính xác factory mặc định.

Trong Spring Framework không dùng Boot, cấu hình thủ công ví dụ:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

Cần các import từ Spring và `jakarta.jms.ConnectionFactory`. Bean method tên `jmsListenerContainerFactory` đáp ứng tên mặc định. Annotation `@EnableJms` kích hoạt phát hiện listener; bản thân nó không tạo JMS broker, không cấp tài khoản hay destination.

### 4.3. Factory tùy chỉnh cho một listener

~~~java
@Bean("priorityQueueFactory")
DefaultJmsListenerContainerFactory priorityQueueFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");
    return factory;
}
~~~

Dùng bằng:

~~~java
@JmsListener(
    destination = "orders.priority",
    containerFactory = "priorityQueueFactory")
public void receivePriority(String payload) {
    // ...
}
~~~

Nếu muốn **hai factory**, hãy tạo hai bean tên khác nhau và dùng annotation chỉ định rõ. Nếu chỉ có một factory tùy chỉnh nhưng listener bỏ `containerFactory`, hãy đảm bảo vẫn có **default factory** đúng tên hoặc đăng ký default thông qua `JmsListenerConfigurer`. Đừng dựa vào thứ tự khởi tạo ngẫu nhiên.

### 4.4. Factory và JMS ConnectionFactory khác nhau

- `jakarta.jms.ConnectionFactory`: tạo JMS connection.
- `org.springframework.jms.config.JmsListenerContainerFactory`: tạo Spring listener container.
- `DefaultJmsListenerContainerFactory`: một implementation của factory Spring.
- `DefaultMessageListenerContainer`: container thực tế poll và dispatch message.

Dễ nhầm vì cả hai tên đều chứa `Factory`. `@JmsListener(containerFactory="...")` trỏ đến **Spring listener container factory**, không trực tiếp trỏ tới JMS provider ConnectionFactory.

## 5. Các thiết lập quan trọng của `DefaultJmsListenerContainerFactory`

Một số tùy chọn cốt lõi:

| Thiết lập | Vai trò | Rủi ro khi cấu hình sai |
|---|---|---|
| `setConnectionFactory(...)` | Kết nối broker thực sự. | Listener kết nối sai broker/credentials. |
| `setDestinationResolver(...)` | Mapping tên String thành Queue/Topic. | JNDI không resolve, typo hoặc mapping sai. |
| `setPubSubDomain(...)` | Chọn Queue (`false`) hay Topic (`true`). | Listener nghe nhầm loại destination. |
| `setSessionTransacted(true)` | Local JMS transaction cho nhận + xử lý. | Nếu thiếu, exception có thể không gây redelivery như kỳ vọng. |
| `setTransactionManager(...)` | Transaction manager ngoài, thường JTA khi dùng XA. | Transaction semantics/resource enlistment sai. |
| `setConcurrency("2-5")` | Số consumer đồng thời của container. | Mất ordering, topic duplicate hoặc quá tải downstream. |
| `setMessageConverter(...)` | Chuyển JMS Message thành payload Java. | Lỗi chuyển JSON/serialization. |
| `setErrorHandler(...)` | Xử lý/log lỗi khi listener thất bại. | Lỗi không được quan sát, nuốt sai exception. |
| `setMessageSelector(...)` | Bộ lọc JMS selector tại consumer/container. | Message tồn trong queue nhưng không listener nào nhận. |
| `setClientId(...)`, durable subscription | Liên quan định danh topic subscription. | Collision hoặc mất subscription expectations. |
| `setReceiveTimeout(...)` và cache settings | Ảnh hưởng polling/lifecycle/resource. | Thread chờ lâu, throughput không đúng. |

Không phải mọi cấu hình đều phù hợp mọi provider. Ví dụ, `setConcurrency("3-10")` hữu ích với nhiều Queue consumers nhưng Topic non-shared subscriptions có thể dẫn đến **mỗi consumer nhận một bản** hoặc gặp quy tắc provider khác, không phải tăng khả năng xử lý chia tải như Queue.

### 5.1. Concurrency ở factory và override ở annotation

Factory:

~~~java
factory.setConcurrency("2-5");
~~~

Endpoint có thể override:

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory",
    concurrency = "1")
public void receiveOrder(String payload) { }
~~~

Theo Javadoc `@JmsListener`, `concurrency` trên annotation **ghi đè** concurrency đặt trong factory cho endpoint tương ứng, nếu container hỗ trợ. Các giá trị `"5-10"` mô tả min/max consumer; `"10"` thường biểu thị max 10 với lower bound 1, tùy implementation container. Đừng giả định có 10 thread cố định khi chỉ ghi `"10"`.

### 5.2. Selector: thuộc tính theo endpoint

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory",
    selector = "priorityClass = 'HIGH'")
public void receiveHighPriority(String payload) { }
~~~

`selector` là JMS selector expression áp vào headers/properties được provider hỗ trợ. `priorityClass` ở ví dụ là **application String property**, không phải giá trị Java enum tự có trên mọi message. Producer phải gắn chính property này. Nếu không, message có thể ở lại queue chờ consumer phù hợp.

Nhiều listeners có selectors khác nhau trên **cùng Queue** đang cạnh tranh theo những điều kiện lọc; đây không tự động biến Queue thành Topic broadcast. Cần đo routing và queue depth.

### 5.3. `id`: định danh container khi quản lý lifecycle

~~~java
@JmsListener(
    id = "orders-listener",
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
public void handle(String payload) { }
~~~

`id` là định danh endpoint/container trong `JmsListenerEndpointRegistry`. Nó không phải destination, cũng không phải `clientId` của JMS connection. Một `id` nên duy nhất trong registry.

Ví dụ quản lý:

~~~java
// Snippet trong bean Spring đã inject JmsListenerEndpointRegistry.
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop();
}
~~~

Đây là snippet, không phải ứng dụng độc lập. Trong production, cần cân nhắc drain, timeout, in-flight transaction, readiness và coordination giữa các instance trước khi stop/start container.

## 6. Spring Boot 3.5: tận dụng default configurer

Khi dùng Boot cùng `spring-boot-starter-artemis` và JMS auto-configuration, Boot có thể tạo:

- `ConnectionFactory` theo `spring.artemis.*`.
- `JmsTemplate` gửi JMS.
- Default listener container factory khi thiếu một factory cần thiết theo điều kiện auto-configuration.
- Các defaults cho session transaction, caching, message converter, observation hoặc properties liên quan.

Nếu cần thêm một factory, Spring Boot cung cấp:

~~~java
org.springframework.boot.autoconfigure.jms
    .DefaultJmsListenerContainerFactoryConfigurer
~~~

Đây là một **helper của Boot** có nhiệm vụ áp cấu hình mặc định đã đọc từ properties, sau đó bạn bổ sung hoặc override thiết lập riêng.

### 6.1. Dùng `DefaultJmsListenerContainerFactoryConfigurer`

~~~java
@Bean("ordersListenerFactory")
DefaultJmsListenerContainerFactory ordersListenerFactory(
        DefaultJmsListenerContainerFactoryConfigurer configurer,
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();

    // Boot 3.5: ưu tiên native factory cho message listener container.
    configurer.configure(factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setPubSubDomain(false);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Import Boot 3.5:

~~~java
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
~~~

Đây là snippet khai báo bean. Spring Boot 3.5 documentation gợi ý `ConnectionFactoryUnwrapper.unwrapCaching(...)` để listener container dùng **native ConnectionFactory** thay vì giữ một connection cache bên ngoài: listener container có cơ chế quản lý và recovery riêng. Không dùng một `CachingConnectionFactory` vô điều kiện cho container rồi kỳ vọng nó sẽ xử lý restart/scaling giống native factory.

### 6.2. Vì sao nên dùng configurer thay vì `new` rồi set vài thuộc tính?

Hai cách đều có thể hợp lệ. Nhưng nếu chỉ:

~~~java
var factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
return factory;
~~~

thì bạn có thể bỏ sót những defaults từ Boot như transaction, converter, observation và listener properties. Đặc biệt, `DefaultMessageListenerContainer` với mặc định `AUTO_ACKNOWLEDGE` có cách ACK trước khi thực thi listener; exception không tự động bảo đảm redelivery trong chế độ đó. Với một factory tự viết, hãy chủ động cấu hình transaction semantics và kiểm thử.

**Mặc định của factory bạn tự `new` không nhất thiết bằng factory được Boot auto-configure.** Môi trường có JTA cũng có thể khác local transaction. Vì vậy bài ví dụ đặt `setSessionTransacted(true)` rõ ràng.

### 6.3. Properties của Boot và giới hạn

Ví dụ `application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

app.jms.orders-queue=lesson.orders.commands
app.jms.audit-queue=lesson.audit.commands
~~~

`spring.artemis.*` do Boot hiểu; `app.jms.*` là cấu hình tùy ý của ứng dụng, được annotation tham chiếu qua placeholder. Các thuộc tính `spring.jms.listener.*` (ví dụ concurrency/acknowledge settings theo phiên bản Boot) có thể được configurer áp dụng. Không giả định properties sẽ tự cấu hình một factory bạn khởi tạo thủ công **mà không gọi configurer**.

## 7. Hai factory hay một factory?

### 7.1. Một factory là đủ khi policy giống nhau

Nếu `orders.incoming`, `orders.retry` và `notifications.queue` đều là JMS Queue trên cùng broker, cùng Session transaction policy, converter và concurrency phù hợp, có thể dùng **cùng một factory bean**:

~~~java
@JmsListener(
    destination = "orders.incoming",
    containerFactory = "defaultQueueFactory")
void onIncoming(String payload) { }

@JmsListener(
    destination = "orders.retry",
    containerFactory = "defaultQueueFactory")
void onRetry(String payload) { }
~~~

Mỗi endpoint vẫn có container riêng, mặc dù được tạo từ cùng factory.

### 7.2. Tách factory khi policy khác

Nên cân nhắc tách factory nếu có khác biệt bền vững:

- Queue vs Topic (`pubSubDomain`).
- Native JMS ConnectionFactory khác nhau do broker/credentials.
- Local transaction vs JTA/transaction manager khác nhau.
- Message converter/schema hoặc custom error handler.
- Concurrency/selector/durable subscription policy khó diễn đạt bằng annotation override.
- Client ID/subscription setup khác nhau.
- Recovery, caching hoặc resource behavior đặc thù.

Không nhất thiết tạo một factory cho **mỗi queue** khi các queue dùng chính sách giống nhau; điều đó làm cấu hình dư thừa và khó bảo trì. Tuy nhiên việc chọn factory riêng để tách SLA/risk hoặc traffic class vẫn có thể hợp lý.

### 7.3. Khác `JmsTemplate`

`JmsTemplate` thường được dùng **gửi** hoặc nhận đồng bộ; `DefaultJmsListenerContainerFactory` tạo consumer container **nhận bất đồng bộ**. Hai object có thể cùng dùng `ConnectionFactory` nhưng không tự chia sẻ hết các settings.

Ví dụ `jmsTemplate.setPubSubDomain(true)` không tự khiến `ordersListenerFactory` nhận Topic. Phải kiểm tra factory thực tế. Ngược lại, `@JmsListener(destination="x")` không tự gán default destination cho template producer.

## 8. Demo hoàn chỉnh Java 17: hai destination, hai containerFactory

Ứng dụng sẽ:

1. Dùng Artemis chạy cục bộ.
2. Khai báo hai Queue bằng properties.
3. Tạo factory `ordersListenerFactory` và `auditListenerFactory`.
4. Tạo hai listener methods: một nhận order, một nhận audit có JMS selector.
5. Gửi hai message bằng `JmsTemplate`.
6. Quan sát log chứng minh cả hai listener được gọi, mỗi listener dùng policy riêng.

Ví dụ dùng Spring Boot **3.5.5**, Java **17** và `spring-boot-starter-artemis`. Không cần triển khai một `MessageListener` interface thủ công.

### 8.1. Chuẩn bị broker Artemis

Yêu cầu: JDK 17+, Maven 3.9+, Docker, port `61616` và `8161` còn rảnh. Chạy broker dành riêng cho demo:

~~~bash
docker run --detach --rm --name jms-listener-factory-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Kiểm tra broker startup:

~~~bash
docker logs jms-listener-factory-lab
~~~

Console Artemis thường ở `http://localhost:8161`. Image/demo thường bật auto-create address/queue. Nếu tổ chức tắt auto-create, phải provision hai queue có tên tương ứng và quyền `send`/`consume` trước khi chạy. Không dùng password demo ở production.

### 8.2. Cấu trúc project

~~~text
jms-listener-factory-lab/
├── pom.xml
└── src/main/
    ├── java/example/JmsListenerFactoryApplication.java
    └── resources/application.properties
~~~

### 8.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>jms-listener-factory-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 8.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Tên destination riêng theo cấu hình ứng dụng.
app.jms.orders-queue=lesson.orders.commands
app.jms.audit-queue=lesson.audit.commands
~~~

### 8.5. `src/main/java/example/JmsListenerFactoryApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsListenerFactoryApplication {

    private static final String ORDERS = "lesson.orders.commands";
    private static final String AUDIT = "lesson.audit.commands";

    public static void main(String[] args) {
        SpringApplication.run(JmsListenerFactoryApplication.class, args);
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setPubSubDomain(false);  // Queue
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("auditListenerFactory")
    DefaultJmsListenerContainerFactory auditListenerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setPubSubDomain(false);  // Queue
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);

        // Chỉ nhận các message có JMS property kind = "AUDIT".
        factory.setMessageSelector("kind = 'AUDIT'");
        return factory;
    }

    @Bean
    ApplicationRunner publishExamples(
            JmsTemplate jmsTemplate,
            Receivers receivers) {
        return args -> {
            jmsTemplate.convertAndSend(ORDERS, "order-42");

            jmsTemplate.convertAndSend(
                    AUDIT,
                    "audit-42",
                    message -> {
                        message.setStringProperty("kind", "AUDIT");
                        return message;
                    });

            System.out.println("sentTwo=true");
            System.out.println(
                    "receivedBoth=" + receivers.awaitBoth());
        };
    }

    @Component
    public static class Receivers {
        private final CountDownLatch received =
                new CountDownLatch(2);

        @JmsListener(
            id = "orders-listener",
            destination = "${app.jms.orders-queue}",
            containerFactory = "ordersListenerFactory")
        public void onOrder(String body) {
            System.out.println("ordersReceived=" + body);
            received.countDown();
        }

        @JmsListener(
            id = "audit-listener",
            destination = "${app.jms.audit-queue}",
            containerFactory = "auditListenerFactory")
        public void onAudit(TextMessage message)
                throws JMSException {

            System.out.println(
                    "auditReceived=" + message.getText()
                    + ";kind=" + message.getStringProperty("kind"));
            received.countDown();
        }

        boolean awaitBoth() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }
}
~~~

### 8.6. Kiểm tra cách mã kết nối các thành phần

- `@SpringBootApplication` bật component scan ở package `example` và Boot auto-configuration.
- `@EnableJms` cho phép đăng ký `@JmsListener`.
- `ordersListenerFactory` và `auditListenerFactory` là **tên bean từ `@Bean("...")`**.
- Mỗi factory được cấu hình bằng Boot `DefaultJmsListenerContainerFactoryConfigurer`, rồi override rõ `pubSubDomain`, concurrency, transacted session và selector của audit.
- Hai annotation dùng **`containerFactory` trùng đúng tên bean** tương ứng.
- Hai `destination` lấy từ `${app.jms.*}`. Các tên được resolve ở lúc startup/endpoint registration, không theo từng payload.
- `JmsTemplate` của Boot gửi message đến hai queue. Message audit có application property `kind="AUDIT"` để khớp selector.
- Một method nhận `String` payload thông qua message converter; method khác nhận `jakarta.jms.TextMessage` gốc và đọc property.
- `CountDownLatch` chỉ giúp đợi hai callback chạy tới phần cuối; nó **không thay thế JMS ACK**, không chứng minh exactly-once hay rằng database side effect đã durable.
- Factory dùng `sessionTransacted=true` để exception trong listener dẫn đến rollback JMS, cho phép redelivery tùy broker policy.
- Mã demo không có transaction DB và không tuyên bố xử lý trùng tự động.

### 8.7. Biên dịch và chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Khi broker sạch, chỉ có một instance ứng dụng, credentials và destination đúng, bạn thường quan sát **các dòng do ứng dụng in**:

~~~text
sentTwo=true
ordersReceived=order-42
auditReceived=audit-42;kind=AUDIT
receivedBoth=true
~~~

Thứ tự ba dòng đầu không cố định: listener container hoạt động trên thread khác. Dòng `receivedBoth=true` chỉ xuất hiện khi cả hai listener đã chạy trước hạn 15 giây. Nếu broker gặp lỗi, auto-create tắt hoặc đã có message cũ/consumer khác, output có thể khác. Spring Boot in thêm startup logs.

Để kiểm tra rõ, dùng Artemis console và xem hai queue:

~~~text
lesson.orders.commands
lesson.audit.commands
~~~

Nếu audit message không có property `kind`, selector `kind = 'AUDIT'` sẽ **không chọn** message đó; nó có thể nằm lại queue dù producer báo send thành công.

Dừng app bằng `Ctrl+C`, sau đó:

~~~bash
docker stop jms-listener-factory-lab
~~~

Container dùng `--rm` không mount volume nên dữ liệu demo không được giữ khi dừng. Không dùng cài đặt này làm broker production.

### 8.8. Thử thay đổi có kiểm soát

Thử từng thay đổi **một lần** để hiểu nguyên nhân:

1. Đổi `destination = "${app.jms.orders-queue}"` thành một property không tồn tại: quan sát lỗi placeholder/registration.
2. Đổi `containerFactory = "ordersListenerFactory"` thành một bean name không tồn tại: quan sát lỗi tìm bean factory.
3. Tắt `setSessionTransacted(true)` trong một factory ở broker thử nghiệm; thêm lỗi xử lý có kiểm soát và so sánh redelivery.
4. Đổi selector audit thành `kind = 'UNKNOWN'`: message audit sẽ không match và có thể tồn queue.
5. Đổi factory audit thành `pubSubDomain=true` trong khi producer vẫn gửi Queue: quan sát mismatch (không coi việc cùng String là đủ).
6. Nếu broker tắt auto-create, provision cả hai queues rồi chạy lại không đổi Java code.

Không thực hiện các thí nghiệm phá vỡ message flow trên queue đang có dữ liệu production.

## 9. Factory mặc định so với factory chỉ định: bảng quyết định

| Trường hợp | Annotation | Factory Spring sẽ chọn |
|---|---|---|
| Không khai báo `containerFactory` | `@JmsListener(destination="orders")` | Default `jmsListenerContainerFactory` hoặc default được registrar cấu hình. |
| Khai báo tường minh | `@JmsListener(destination="orders", containerFactory="ordersListenerFactory")` | Bean `ordersListenerFactory`. |
| Tên bean sai | `containerFactory="noSuchFactory"` | Thường lỗi đăng ký endpoint/startup, không tự tạo factory. |
| Hai factory cùng type | `containerFactory="auditListenerFactory"` | Theo **tên bean**, không chọn ngẫu nhiên theo type. |
| Hai method không khai báo factory nhưng chỉ có bean tên khác | Không rõ default | Cần bean mặc định hoặc cấu hình registrar; không trông chờ may rủi. |
| Cùng factory, hai destination khác nhau | Hai annotation khác `destination` | Hai containers riêng từ cùng factory. |
| Cùng Queue, hai listeners khác nhau | Hai annotation cùng `destination` | Competing consumers, không broadcast. |
| Topic listeners | Factory `pubSubDomain=true` | Semantics topic/subscriptions; không giống queue. |

Điểm quan trọng: **factory được lookup theo tên bean** trong `containerFactory`, còn **destination được resolve qua chiến lược `DestinationResolver`** của container. Chúng không nằm trong cùng namespace.

## 10. `@JmsListener` có những thuộc tính bổ sung nào?

Dù trọng tâm là hai thuộc tính chính, việc biết các thuộc tính khác giúp không đặt nhầm vào `containerFactory`:

| Thuộc tính | Công dụng | Ghi chú |
|---|---|---|
| `destination` | Tên queue/topic mà endpoint nghe | Bắt buộc khi dùng trực tiếp annotation. |
| `containerFactory` | Bean name của `JmsListenerContainerFactory` | Tùy chọn nếu có default. |
| `id` | Định danh endpoint/container | Dùng qua `JmsListenerEndpointRegistry`. |
| `selector` | JMS selector trên header/property | Ví dụ `kind = 'AUDIT'`. |
| `concurrency` | Override concurrency từ factory | Cẩn trọng khi dùng Topic. |
| `subscription` | Tên durable subscription nếu có | Cần factory/topic setup đúng. |

Spring còn cho phép `@JmsListener` lặp lại trên một method để đăng ký **nhiều endpoint**:

~~~java
@JmsListener(
    destination = "orders.region-a",
    containerFactory = "ordersListenerFactory")
@JmsListener(
    destination = "orders.region-b",
    containerFactory = "ordersListenerFactory")
public void onRegionalOrder(String payload) {
    // Một method xử lý hai endpoints.
}
~~~

Đây là snippet. Mỗi annotation tạo một endpoint/container riêng; business method có thể được gọi đồng thời trên các thread khác nhau. Nếu giữ state mutable trong bean, bạn vẫn phải bảo đảm thread safety và idempotency.

## 11. Topic, durable subscription và vì sao không chỉ đổi tên

Một listener cho Topic có thể được khai báo:

~~~java
@JmsListener(
    destination = "orders.events",
    containerFactory = "topicListenerFactory")
void onOrderEvent(String event) { }
~~~

Trong đó `topicListenerFactory` có `setPubSubDomain(true)`. Nhưng có các quy tắc quan trọng:

- Topic thường phát message cho **các subscription**, không phải một queue chia việc đơn thuần.
- Non-durable subscription thường chỉ nhận khi subscription hoạt động; consumer offline có thể mất message được publish trong khoảng vắng mặt.
- Durable subscription cần setup phù hợp, ví dụ durable flag, subscription name, client identity; cụ thể tùy JMS version, shared durable subscriptions và broker.
- `concurrency > 1` trên một Topic listener không có cùng ý nghĩa scaling với Queue; có thể tạo nhiều subscribers, mỗi subscriber nhận một bản hoặc gặp giới hạn không cho trùng client ID.
- Khi dùng durable subscriber, xem kỹ lifecycle, reconnect, tên subscription ổn định và thay đổi destination trên deployment.

Trong production, topic factory nên có cấu hình cụ thể thay vì copy queue factory và đổi duy nhất `pubSubDomain=true`.

## 12. Transaction, acknowledgement và xử lý lỗi phụ thuộc factory

Annotation không quy định transaction. Chính listener container/factory quyết định lúc nào message được acknowledge và khi nào cần rollback.

### 12.1. Local JMS transaction

~~~java
factory.setSessionTransacted(true);
~~~

Ở `DefaultMessageListenerContainer`, mỗi listener callback chạy trong phạm vi local JMS transaction. Nếu method ném exception để container nhận thấy lỗi, session có thể rollback và broker áp dụng redelivery policy.

~~~text
Queue M
  |
  v
Listener container nhận M (transaction mở)
  |
  +-- listener xử lý thành công
  |       |
  |       +-- commit JMS -> ACK M
  |
  +-- listener ném exception
          |
          +-- rollback -> broker có thể redeliver M
~~~

**Không nuốt exception rồi return bình thường** nếu bạn muốn rollback. Cần phân loại lỗi transient và permanent, áp dụng retry/DLQ có kiểm soát, idempotency, và không gửi lại một JMS message mới tùy tiện trong `catch`.

### 12.2. AUTO_ACKNOWLEDGE và factory tự tạo

Spring `DefaultMessageListenerContainer` với `AUTO_ACKNOWLEDGE` mặc định có thể thực hiện automatic acknowledge **trước khi listener code chạy**, nên exception **không dẫn đến redelivery chỉ vì nó được ném**. Do đó, khi tạo custom factory hãy chọn transaction policy có chủ ý hoặc dùng Boot configurer để kế thừa Boot defaults; không chỉ khai báo hai thuộc tính `destination` và `containerFactory` rồi nghĩ hệ thống đã có retry đúng.

### 12.3. DB transaction khác JMS transaction

`sessionTransacted=true` bảo đảm local JMS transaction, **không tự gom database update**. Trường hợp DB commit rồi JMS commit lỗi, broker có thể redeliver M trong khi DB side effect đã tồn tại.

Sử dụng business `eventId` ổn định và idempotency store/unique constraint trong cùng DB transaction với thay đổi nghiệp vụ. Với API bên ngoài (payment/email), cần idempotency hoặc outbox/saga phù hợp. Chỉ dựa vào `JMSRedelivered` hay `JMSXDeliveryCount` là không đủ để tránh duplicate.

## 13. Nhiều broker: mỗi factory có ConnectionFactory riêng

Nếu tổ chức dùng một Artemis broker cho orders và một broker khác cho audit, việc cùng một method nhận annotation không nói gì về broker đích. **Factory mới quyết định ConnectionFactory**.

~~~text
@JmsListener("orders.commands", containerFactory="ordersFactory")
      |
      +--- ordersFactory -> ordersConnectionFactory -> Broker A

@JmsListener("audit.commands", containerFactory="auditFactory")
      |
      +--- auditFactory  -> auditConnectionFactory  -> Broker B
~~~

Trong nhiều-broker setup, cần khai báo hai native JMS `ConnectionFactory` bean và inject đúng bean bằng `@Qualifier`; factory nào dùng connection factory nào phải kiểm tra rõ. `destination` có cùng tên `"events"` nhưng nằm trên hai broker là **hai nguồn dữ liệu khác nhau**.

Không thay đổi broker URL bằng cách mutate ConnectionFactory/Factory singleton đang chạy; thực hiện theo lifecycle/redeploy/reconnect policy. Phân quyền và TLS trên từng broker. Nếu broker A có Queue mà broker B không có, chỉ thay `containerFactory` có thể khiến listener không khởi chạy.

## 14. DestinationResolver, naming policy và quản lý tài nguyên

### 14.1. Không tạo queue bừa bãi

Với broker cho auto-create, typo:

~~~java
@JmsListener(destination = "orders.comands")
~~~

có thể tạo một queue không ai gửi vào, trong khi producer gửi `"orders.commands"`. Listener vẫn sống nhưng im lặng. Để hạn chế:

- Đặt tên qua constants hoặc configuration properties.
- Kiểm tra runtime effective property values.
- Dùng provisioning catalog/Infrastructure as Code.
- Tắt auto-create trong môi trường cần governance.
- Cấu hình ACL theo namespace, không cho app principal tạo hàng nghìn queue tùy ý.
- Có broker metrics cho queue depth, consumer count và unrouted message.

### 14.2. Đừng dùng raw user input làm destination

Nếu listener endpoint được đăng ký động theo tenant/request, cần mapping/allowlist và kiểm soát quota. Annotation thường được resolve khi Spring startup, không phù hợp với việc tạo một listener cho mỗi HTTP request. Với dynamic runtime subscriptions, cân nhắc `JmsListenerEndpointRegistry` và programmatic registration có lifecycle được quản lý.

### 14.3. Message selector không tương đương phân quyền

`selector = "tenant = 'a'"` chỉ là lọc delivery theo JMS properties, không phải ACL chống tenant khác đọc dữ liệu. Broker authentication/authorization và thiết kế isolation mới là ranh giới bảo mật. Đừng cho mọi tenant dùng chung credential có quyền consume toàn bộ queue rồi tin rằng selector đủ bảo mật.

## 15. Quan sát listener thực sự chạy hay không

### 15.1. Dùng `JmsListenerEndpointRegistry`

~~~java
// Snippet trong Spring bean có injected registry.
MessageListenerContainer c =
        registry.getListenerContainer("orders-listener");

if (c != null) {
    System.out.println("running=" + c.isRunning());
}
~~~

`JmsListenerEndpointRegistry` cung cấp cách lấy container theo `@JmsListener.id`, xem/truy cập trạng thái và thực hiện start/stop có kiểm soát. Đây không phải cách kiểm tra broker đã gửi/nhận nghiệp vụ thành công; còn cần delivery metrics, ACK, application logs.

### 15.2. Các mức cần kiểm tra

| Mức | Câu hỏi |
|---|---|
| Spring scan | Class có phải bean Spring không? |
| Annotation processing | `@EnableJms`/auto-config có hoạt động không? |
| Factory lookup | `containerFactory` trỏ tới bean đúng tên/type không? |
| Consumer initialization | `ConnectionFactory` kết nối được broker không? |
| Destination resolver | Queue/Topic và tên effective có đúng không? |
| Broker | Address/queue/subscription có tồn tại, đúng routing/ACL không? |
| Delivery | Broker thấy consumer count, deliveries, selector matches không? |
| Listener | Method có được gọi và message conversion có thành công không? |
| Transaction | Message đã commit hay rollback/đi DLQ? |
| Business | Side effect có thật sự hoàn tất, idempotent và quan sát được không? |

Một consumer `isRunning()==true` chưa chứng minh message được match bởi selector hoặc broker đã gửi được message phù hợp.

## 16. Chẩn đoán những lỗi thường gặp

### 16.1. `No bean named 'ordersListenerFactory'`

**Nguyên nhân thường gặp:** annotation ghi tên factory không tồn tại; method `@Bean` nằm ngoài component scan; bean có tên khác; cấu hình bị profile điều kiện không load.

**Cách kiểm tra:** xem ApplicationContext beans, đúng `@Bean("ordersListenerFactory")`, đúng package scan, profile và `containerFactory`. `containerFactory` cần tên bean, **không phải tên class**.

### 16.2. `No default JmsListenerContainerFactory`

Một endpoint không khai báo `containerFactory`, nhưng context không có default tên `jmsListenerContainerFactory` (và registrar không được cấu hình default). Tạo đúng bean mặc định hoặc thêm `containerFactory` tường minh. Đặc biệt cẩn trọng khi đã định nghĩa custom factory khiến auto-config của Boot không tạo default như bạn kỳ vọng.

### 16.3. Listener không nhận dù producer gửi thành công

Kiểm tra tuần tự:

1. Tên destination thực tế từ properties và chính tả.
2. `pubSubDomain` của **cả producer và listener**.
3. Broker host/port, vhost/cluster, user và quyền.
4. Resource vật lý có được provision đúng routing/queue không?
5. Listener container có start không?
6. Selector có chọn được message không?
7. Message có expire hoặc đã vào DLQ không?
8. Có consumer khác đang cạnh tranh cùng Queue không?
9. Message converter có lỗi trước khi gọi method không?

Đừng kết luận annotation sai nếu broker không có message được route tới consumer.

### 16.4. Đã định nghĩa factory nhưng thấy policy không được áp dụng

Có thể annotation đang bỏ `containerFactory` nên Spring dùng bean mặc định khác. Hoặc code gửi message đang dùng `JmsTemplate`, vốn có cấu hình riêng. Hãy log tên factory/bean và xem effective `DestinationResolver`, `ConnectionFactory`, transaction mode, concurrency của container.

### 16.5. Message được xử lý trùng

Nếu listener ném exception trong transacted session, broker có thể redeliver; nếu DB đã commit rồi JMS commit thất bại, message có thể bị xử lý lại. Dùng business event ID và idempotency; đừng coi việc có factory giao dịch là bảo đảm exactly-once với DB.

### 16.6. `concurrency` tăng làm message không còn đúng thứ tự

Nhiều Queue consumers có thể xử lý đồng thời và hoàn tất khác thứ tự. Nếu nghiệp vụ cần ordering, dùng consumer concurrency thích hợp, sharding theo key, hoặc một mô hình thứ tự do broker/ứng dụng bảo đảm. Không mặc định `"5-10"` tốt hơn `"1"`.

### 16.7. Topic nhận nhiều bản message

Với publish/subscribe, nhiều subscriptions có thể nhận cùng event. Nếu bạn tăng concurrency bằng cách tạo nhiều Topic consumers mà không dùng shared subscription semantics phù hợp, dữ liệu có thể được giao nhiều bản theo thiết kế. Xác định rõ Topic vs Queue và durable/shared subscription policy.

### 16.8. Listener dừng sau broker restart hoặc mạng đứt

Cần kiểm tra recovery interval, ConnectionFactory và container management. Spring Boot khuyên listener container dùng native ConnectionFactory khi phù hợp, để quản lý reconnect/recovery riêng. Đừng tự bọc cache bên ngoài listener container mà không hiểu tác động đến restart/scaling.

### 16.9. `@JmsListener` method không được phát hiện

Class có thể không là Spring bean, không nằm trong component scan, `@EnableJms` chưa được bật, annotation đặt trên đối tượng được tự tạo bằng `new`, hoặc bean bị loại bởi conditional/profile. Đừng bắt đầu bằng đổi `destination` nếu hạ tầng annotation chưa hoạt động.

### 16.10. Thông điệp không khớp selector

Một selector như `kind = 'AUDIT'` yêu cầu JMS property `kind` có giá trị String `AUDIT`. Nếu producer chỉ đưa JSON field `"kind"` vào body mà **không set JMS property**, broker không dùng JSON field đó để match selector. Gắn property bằng `MessagePostProcessor` và kiểm tra raw JMS message.

## 17. Những anti-pattern quan trọng

| Anti-pattern | Vì sao sai? | Thay bằng |
|---|---|---|
| `containerFactory="DefaultJmsListenerContainerFactory"` | Annotation cần **tên bean**, không phải class. | `containerFactory="ordersListenerFactory"`, có `@Bean` đúng tên. |
| Ghi `destination="orders"` rồi nghĩ Spring tự provision queue | JMS reference không bảo đảm resource broker. | Provision/verify address, queue, ACL. |
| Dùng default factory rồi kỳ vọng custom settings của factory khác | Annotation không tự chọn theo use case. | Chỉ định `containerFactory` tường minh. |
| Tăng concurrency Topic như Queue | Có thể nhận bản sao, subscription collision. | Thiết kế Topic/durable/shared đúng. |
| `selector` là JSON body query | JMS selector đọc JMS headers/properties. | Gắn JMS properties hoặc lọc ở application đúng chỗ. |
| Catch tất cả exception và return success | Listener có thể commit dù xử lý thất bại. | Propagate lỗi cần rollback, dùng retry/DLQ. |
| Tin rằng local JMS transaction cũng rollback DB | Hai resource độc lập. | Idempotency/outbox hoặc JTA/XA được thiết kế. |
| Đưa user input trực tiếp vào destination | Queue sprawl, abuse, ACL risk. | Mapping/allowlist và resource governance. |
| Đổi factory bean setter khi nhiều listeners đang chạy | Runtime state khó kiểm soát, behavior không đồng nhất. | Cấu hình trước khi start, thay đổi theo lifecycle rõ. |
| Nhận `String` khi payload cần JSON custom converter nhưng chưa cấu hình | Convert mismatch/schema error. | MessageConverter phù hợp, validate và test. |
| Đổi JmsTemplate sang Topic nhưng không đổi listener factory | Producer và consumer khác domain. | Đồng bộ cấu hình cả hai bên. |
| Chỉ xem container running rồi khẳng định business OK | Running không bằng delivered/committed. | Quan sát broker + application + transaction. |

## 18. Checklist triển khai

Trước khi đưa listener lên môi trường production:

- [ ] `@EnableJms`/auto-configuration kích hoạt và bean listener nằm trong component scan.
- [ ] `destination` đúng tên cấu hình, không còn placeholder unresolved.
- [ ] Phân biệt rõ Queue/Topic; `pubSubDomain` của listener và producer khớp.
- [ ] Broker address/queue/topic được provision, có routing, retention, DLQ và ACL đúng.
- [ ] `containerFactory` trỏ đúng **tên bean** `JmsListenerContainerFactory`.
- [ ] Nếu listener bỏ `containerFactory`, có default factory đúng tên hoặc registrar được cấu hình.
- [ ] Custom factory dùng `ConnectionFactory` phù hợp, ưu tiên Boot configurer và native listener connection khi dùng Boot 3.5.
- [ ] `sessionTransacted`/transaction manager/ack mode được kiểm thử với exception và redelivery.
- [ ] Concurrency/selector/durable subscription phù hợp loại destination và nhu cầu ordering.
- [ ] Message converter hỗ trợ payload thực tế, schema validation hợp lệ.
- [ ] Log listener ID, destination, message ID, event ID, redelivery count, lỗi và transaction outcome.
- [ ] Có idempotency khi business có DB/API side effects.
- [ ] Monitoring gồm consumer count, queue depth, delivery, DLQ và lỗi broker/connection.
- [ ] Đã thử broker restart, missing destination, credentials sai và factory bean name sai trong staging.
- [ ] Không cấp quyền tạo queue bừa bãi hoặc dùng user input làm destination trực tiếp.
- [ ] Có quy trình thay đổi cấu hình và start/stop container không làm mất in-flight message.

## 19. Câu hỏi tự kiểm tra

**1. `@JmsListener(destination="orders")` có bắt buộc phải khai báo `containerFactory` không?** Không, nếu Spring context có default `JmsListenerContainerFactory` hợp lệ. Tên bean mặc định là `jmsListenerContainerFactory`.

**2. `containerFactory` nhận tên class hay tên bean?** Tên bean Spring, ví dụ `"ordersListenerFactory"`.

**3. Chỉ khai báo `destination="orders.events"` có biến listener thành Topic không?** Không. Queue/Topic phụ thuộc `pubSubDomain` và resolver của container factory.

**4. Hai phương thức dùng cùng factory có chia sẻ một container không?** Không. Factory có thể tạo một container riêng cho mỗi listener endpoint.

**5. Khi dùng Boot 3.5, vì sao có `DefaultJmsListenerContainerFactoryConfigurer`?** Để áp các settings từ auto-configuration vào một custom factory rồi mới override những điểm cần thiết.

**6. Vì sao Boot khuyên dùng `ConnectionFactoryUnwrapper.unwrapCaching(...)` cho listener factory?** Container có quản lý connection/recovery riêng, và việc dùng wrapper cache ngoài có thể gây giới hạn lifecycle/restart/scaling.

**7. Hai listeners cùng Queue có phải mỗi listener đều nhận toàn bộ message không?** Không. Queue dùng competing consumers; một message được phân phối đến consumer phù hợp, không tự broadcast.

**8. Nếu tăng Queue concurrency lên `"3-10"` thì thứ tự hoàn tất message có còn bảo đảm không?** Không nên giả định; nhiều consumers xử lý đồng thời có thể làm thay đổi thứ tự.

**9. `selector = "kind = 'AUDIT'"` có tìm field `kind` trong JSON payload không?** Không. Nó lọc JMS headers/properties; producer phải set JMS property `kind`.

**10. Nếu method ném exception, broker có chắc redeliver không?** Phụ thuộc transaction/ack mode của container và broker redelivery policy. Dùng transacted sessions khi muốn rollback theo lỗi.

**11. Tại sao `@JmsListener` trên object tạo bằng `new` không có tác dụng?** Vì annotation processor chỉ quét Spring-managed beans.

**12. Một method có thể có hai `@JmsListener` khác destination không?** Có; annotation repeatable, mỗi declaration tạo một endpoint/container.

**13. `id="orders-listener"` dùng để làm gì?** Định danh container/endpoint qua `JmsListenerEndpointRegistry`, không phải tên queue hay JMS clientId.

**14. Đổi giá trị `app.jms.orders-queue` trong file lúc process đang chạy có chuyển listener ngay không?** Không mặc định; endpoint được resolve khi đăng ký, cần lifecycle/reconfiguration đúng.

**15. Factory `sessionTransacted=true` có tự bảo đảm exactly-once database transaction không?** Không. JMS local transaction và DB transaction khác resource, cần idempotency/thiết kế nhất quán.

**16. Vì sao `containerFactory` không nên chọn ngẫu nhiên khi ứng dụng có nhiều broker?** Vì mỗi factory ràng tới một ConnectionFactory/broker riêng. Cùng tên String trên broker khác là tài nguyên khác.

## 20. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): cú pháp `@JmsListener`, default bean `jmsListenerContainerFactory`, endpoint/container registry, method signature.
- [Spring Framework 6.2 — `@JmsListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `destination`, `containerFactory`, `id`, `selector`, `concurrency`, `subscription`.
- [Spring Framework 6.2 — `@EnableJms` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/EnableJms.html): registration và cấu hình default factory.
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html): listener container, transaction và acknowledgement.
- [Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): các setter và contract factory.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): auto-configuration `ConnectionFactory`, `JmsTemplate`, default listener factory.
- [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): cấu hình custom factory và transacted sessions.
- [Spring Boot 3.5 — `DefaultJmsListenerContainerFactoryConfigurer`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html): cách khởi tạo factory theo Boot settings.
- [Spring Boot 3.5 — `ConnectionFactoryUnwrapper`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/jms/ConnectionFactoryUnwrapper.html): unwrap cached ConnectionFactory khi cấu hình listener.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): demo annotation với `destination` và `containerFactory`.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): broker local cho bài thực hành.

**Ghi nhớ:** `@JmsListener(destination = "orders.commands", containerFactory = "ordersListenerFactory")` kết nối **tên nguồn message** với **một chính sách listener được định nghĩa bằng bean Spring**. `destination` được resolver xử lý theo Queue/Topic và broker provisioning; `containerFactory` chọn settings connection, transaction, concurrency, selector, conversion và lifecycle của **container nhận bất đồng bộ**. Kiểm tra đồng thời cả annotation, factory, Spring context và broker để đảm bảo listener chạy đúng.
