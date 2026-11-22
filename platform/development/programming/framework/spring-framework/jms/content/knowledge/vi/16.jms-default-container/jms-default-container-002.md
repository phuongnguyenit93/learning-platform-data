# DefaultJmsListenerContainerFactory và container được tạo ra trong Spring JMS

## 1. Bản chất: factory khác runtime container

Khi xây dựng ứng dụng Spring JMS, một phương thức Java có thể lắng nghe thông điệp chỉ bằng annotation:

~~~java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.queue")
    public void onOrder(String payload) {
        System.out.println(payload);
    }
}
~~~

Đây là snippet Spring, chưa phải chương trình Java độc lập. Nhưng annotation không tự mở Connection, Session, consumer threads, quản lý transaction hay tự khôi phục khi broker lỗi. Spring triển khai một tầng infrastructure làm những công việc đó.

Hai lớp rất dễ nhầm:

- **DefaultJmsListenerContainerFactory** thuộc org.springframework.jms.config: một factory thường được đăng ký thành **Spring bean**, chứa cấu hình và tạo listener container từ mỗi endpoint.
- **DefaultMessageListenerContainer** thuộc org.springframework.jms.listener: **runtime container** mà factory tạo ra. Nó trực tiếp quản lý JMS Connection, Session, MessageConsumer, polling, invocation, transaction, concurrency và recovery.

Một factory có thể tạo **nhiều DefaultMessageListenerContainer**. Mỗi @JmsListener endpoint thông thường sinh một container riêng, còn mỗi container có thể chứa nhiều JMS consumers nếu concurrency lớn hơn một.

Ví dụ: một bean factory với hai listeners (orders và audit) có thể tạo hai runtime containers; orders container có một consumer, audit container có hai consumers. Khi có thêm 100 message, Spring không tạo thêm 100 factory hoặc 100 container cho 100 message đó.

**Mục tiêu:** hiểu luồng từ factory tới container, các hook API, lifecycle và registry, sự khác nhau giữa số lượng factories/containers/consumers, các cấu hình quan trọng của DMLC, và cách quan sát hai containers sinh ra từ một factory trong project Java 17 + Spring Boot + ActiveMQ Artemis.

## 2. Sơ đồ từ @JmsListener tới broker

~~~mermaid
flowchart TD
    App["ApplicationContext"] --> Infra["@EnableJms hoặc Boot JMS auto-configuration"]
    App --> F["Bean: jmsListenerContainerFactory"]
    Infra --> BPP["JmsListenerAnnotationBeanPostProcessor"]
    BPP --> E1["Endpoint: orders"]
    BPP --> E2["Endpoint: audit"]
    E1 --> R["JmsListenerEndpointRegistrar / Registry"]
    E2 --> R
    F --> R
    R --> C1["DefaultMessageListenerContainer #1"]
    R --> C2["DefaultMessageListenerContainer #2"]
    C1 --> JMS1["Session/MessageConsumer/invoker"]
    C2 --> JMS2["Session/MessageConsumer/invoker(s)"]
    JMS1 --> Broker["JMS Broker"]
    JMS2 --> Broker
~~~

| Thành phần | Vai trò | Có trực tiếp nhận message không? |
| --- | --- | --- |
| @JmsListener | Khai báo method endpoint, destination, ID, selector | Không. |
| DefaultJmsListenerContainerFactory | Tạo runtime container, đặt policy chung | Không. |
| DefaultMessageListenerContainer | Polling, JMS resources, gọi listener và transaction | Có. |
| MethodJmsListenerEndpoint | Metadata của một annotated method | Không. |
| JmsListenerEndpointRegistry | Quản lý các containers theo endpoint IDs | Không. |
| JMS ConnectionFactory | Tạo JMS Connections cho provider | Không trực tiếp xử lý method. |
| JmsTemplate | Template gửi/nhận đồng bộ từ code | Không tạo @JmsListener containers. |

Một factory và một JMS ConnectionFactory cũng là hai đối tượng khác nhau. DefaultJmsListenerContainerFactory nhận một ConnectionFactory để cấu hình containers; ConnectionFactory thuộc Jakarta Messaging API (jakarta.jms.ConnectionFactory), không phải interface tạo Spring listener container.

### 2.1. Ba con số cần đếm riêng

Giả sử:

~~~text
Factory bean:
  jmsListenerContainerFactory

Annotated endpoints:
  ordersEndpoint
  auditEndpoint

Containers:
  DMLC ordersEndpoint: concurrency 1-1
  DMLC auditEndpoint:  concurrency 2-2

=> Factory beans = 1
=> Runtime containers = 2
=> Configured core consumers = 1 + 2 = 3
~~~

Cùng một factory tạo hai containers nhưng **không dùng một container chung cho cả hai queue**. Tổng số consumers không bằng số factory beans; cũng không nhất thiết bằng số endpoint methods.

### 2.2. Containers từ @JmsListener không nhất thiết là Spring beans

Theo Spring reference, những containers do annotated endpoint infrastructure tạo **không được đăng ký thành bean độc lập thông thường trong ApplicationContext**, nhưng có thể lấy qua JmsListenerEndpointRegistry. @JmsListener(id="ordersEndpoint") dùng ID cho registry, không có nghĩa tồn tại một @Bean tên ordersEndpoint.

Vì thế khi không tìm thấy bean DefaultMessageListenerContainer tên ordersEndpoint, đừng kết luận listener không được tạo. Cần kiểm tra registry.

## 3. Các lớp và chữ ký then chốt

Spring Framework 6.x mô tả factory:

~~~java
// Chữ ký rút gọn để hiểu type; không phải file cần định nghĩa lại:
public class DefaultJmsListenerContainerFactory
        extends AbstractJmsListenerContainerFactory<
                DefaultMessageListenerContainer> {
}
~~~

Nó triển khai JmsListenerContainerFactory<DefaultMessageListenerContainer> thông qua superclass. Đây là lý do type runtime được tạo là DefaultMessageListenerContainer chứ không phải SimpleMessageListenerContainer.

Một số API/hook:

~~~java
// Chữ ký rút gọn từ API Spring:
protected DefaultMessageListenerContainer createContainerInstance();

protected void initializeContainer(
        DefaultMessageListenerContainer container);

// Hạ tầng làm việc qua phương thức factory:
// createListenerContainer(JmsListenerEndpoint endpoint)
~~~

- **createContainerInstance()** xây một instance DefaultMessageListenerContainer rỗng.
- **initializeContainer(...)** áp thêm setting của DefaultJmsListenerContainerFactory.
- **createListenerContainer(endpoint)** tổ chức việc dựng và cấu hình container từ một endpoint.
- Endpoint chứa method, destination, selector, subscription, concurrency override và các thông tin liên quan.
- Registry xử lý registration, initialization và lifecycle.

Đây là mô tả kiến trúc, không phải code gọi protected methods từ business service. Developer thông thường không tự gọi createContainerInstance; Spring gọi khi đăng ký endpoints.

### 3.1. Package cần nhớ

| Class/interface | Package |
| --- | --- |
| DefaultJmsListenerContainerFactory | org.springframework.jms.config |
| AbstractJmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerEndpointRegistry | org.springframework.jms.config |
| DefaultMessageListenerContainer | org.springframework.jms.listener |
| SimpleMessageListenerContainer | org.springframework.jms.listener |
| SimpleJmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerAnnotationBeanPostProcessor | org.springframework.jms.annotation |
| @EnableJms / @JmsListener | org.springframework.jms.annotation |
| ConnectionFactory / Session / MessageConsumer | jakarta.jms |

Trong Spring Framework 6 và Spring Boot 3, tránh import javax.jms.* từ các tutorial cũ; dùng jakarta.jms.* nhất quán.

## 4. Quy trình tạo container theo thời gian

~~~mermaid
sequenceDiagram
    autonumber
    participant A as ApplicationContext
    participant B as AnnotationBeanPostProcessor
    participant R as EndpointRegistrar/Registry
    participant F as DefaultJmsListenerContainerFactory
    participant C as DefaultMessageListenerContainer
    participant P as JMS Provider
    A->>B: Scan beans có @JmsListener
    B->>R: Register MethodJmsListenerEndpoint
    R->>F: createListenerContainer(endpoint)
    F->>F: createContainerInstance()
    F->>C: Áp config và endpoint setup
    F->>C: initializeContainer(...)
    F-->>R: Trả container đã cấu hình
    R->>C: Initialize và quản lý lifecycle
    C->>P: Start và tạo JMS resources
    P-->>C: Message matching selector/destination
    C->>A: Gọi annotated method
~~~

Sơ đồ thể hiện **các trách nhiệm**, không phải thứ tự bytecode bất biến trong mọi Spring phiên bản. Những điểm quan trọng:

1. Hạ tầng tìm @JmsListener trên Spring-managed beans.
2. Mỗi annotation được mô hình hóa thành endpoint metadata.
3. Registrar/registry chọn factory theo tên bean hoặc default.
4. Factory tạo một runtime container mới và áp cấu hình.
5. Endpoint kết nối adapter gọi method tới container.
6. Registry chuẩn bị lifecycle, start container theo chính sách.
7. Container kết nối broker, tạo sessions/consumers, nhận message.
8. Hết message này, container tiếp tục nhận message khác trên cùng runtime object.

### 4.1. Không tạo container cho từng message

Sai: mỗi message gửi tới queue sẽ gọi createContainerInstance(). Đúng: factory tạo runtime container khi endpoint được triển khai; container tồn tại lâu và quản lý các lần nhận, có thể **tái tạo JMS resources** khi broker outage.

### 4.2. Thay đổi bean factory sau startup không tự cập nhật container

~~~java
factory.setConcurrency("3-8");
~~~

Nếu gọi sau khi registry đã tạo containers, không có hợp đồng rằng mọi container cũ lập tức thay đổi cấu hình theo. Mỗi container đã có state riêng. Muốn đổi concurrency runtime, dùng API/management của container phù hợp hoặc rollout configuration, sau khi kiểm thử.

### 4.3. Ai tạo bean factory, ai tạo DMLC?

- Spring ApplicationContext tạo DefaultJmsListenerContainerFactory từ @Bean.
- Annotation infrastructure yêu cầu factory tạo DMLC.
- Registry giữ và điều khiển các DMLC.
- DMLC tạo/lấy JMS Connection/Session/MessageConsumer qua ConnectionFactory.
- Broker không tạo Spring DMLC; broker cung cấp JMS destinations và giao messages.

## 5. Đăng ký default bean cho @JmsListener

Tên mặc định Spring tìm khi annotation không chỉ định factory:

~~~text
jmsListenerContainerFactory
~~~

Ví dụ:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Đây là lớp cấu hình Spring có cú pháp hợp lệ khi dự án có Spring JMS và ConnectionFactory bean; nó chưa tự tạo một project có broker.

Nếu listener:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(String payload) {
    // ...
}
~~~

không có containerFactory attribute thì default bean trên sẽ được chọn. Nếu đặt:

~~~java
@JmsListener(
        destination = "orders.priority",
        containerFactory = "priorityFactory")
public void handlePriority(String payload) {
    // ...
}
~~~

thì ứng dụng phải có bean tên priorityFactory. Attribute này là **Spring bean name**, không phải Queue name hay class name.

### 5.1. Tạo nhiều factory không tạo nhiều containers ngay lập tức

Có thể đăng ký ba beans (default, priority, topic). Nhưng nếu chưa có annotated endpoint sử dụng chúng, không thể suy đã có ba DMLC runtime. Container count phụ thuộc endpoint registrations, không bằng số factory beans.

### 5.2. Một method có nhiều endpoints

@JmsListener là repeatable annotation:

~~~java
@JmsListener(id = "importsA", destination = "imports.a")
@JmsListener(id = "importsB", destination = "imports.b")
public void importData(String payload) {
    // Cùng một Java method, hai endpoint registrations.
}
~~~

Đây là snippet. Spring có thể tạo hai DMLC cho hai annotations, dù business code chỉ có một method.

### 5.3. Default lookup khác @Primary

Đừng tự cho rằng @Primary trên một factory bean sẽ thay quy ước tên jmsListenerContainerFactory cho mọi @JmsListener. Lựa chọn factory có cơ chế riêng: default bean name, annotation containerFactory, hoặc JmsListenerConfigurer registrar default.

## 6. Bên trong DefaultMessageListenerContainer

DefaultMessageListenerContainer (DMLC) là **polling listener container**. Nó sử dụng consumer invokers và JMS MessageConsumer.receive(...) trong các task để lấy message. Đây không chỉ là một POJO callback.

~~~text
DefaultMessageListenerContainer (ordersEndpoint)
  |
  +-- JMS Connection / recovery coordination
  |
  +-- consumer invoker #1
  |     +-- JMS Session
  |     +-- JMS MessageConsumer
  |     +-- receive(timeout)
  |     +-- listener adapter -> handler method
  |
  +-- consumer invoker #2 (nếu concurrency cho phép)
        +-- JMS Session
        +-- JMS MessageConsumer
        +-- receive(timeout)
        +-- listener adapter -> handler method
~~~

Sơ đồ khái niệm: JMS Connection có thể được share/giữ hoặc tạo mới tùy cache level, transaction manager và ConnectionFactory wrapper. Không khẳng định mỗi invoker có một TCP connection riêng.

### 6.1. Những bước của một message

1. Consumer nhận message hợp lệ cho destination/selector.
2. DMLC gọi Spring listener adapter.
3. MessageConverter/argument resolution biến TextMessage, MapMessage, headers thành tham số method.
4. Handler xử lý trên thread consumer invoker.
5. Kết quả hoặc exception quay lại container.
6. Container commit/rollback/ack theo cấu hình.
7. Invoker tiếp tục receive hoặc kết thúc theo stop, failure hay scale down.

Một handler nhận String thường đi từ TextMessage với SimpleMessageConverter. Muốn DTO JSON, hãy cấu hình converter ObjectMapper/type ID và schema validation. **Factory type** không tự quyết định mọi kiểu payload Java.

### 6.2. Không chuyển JMS Session sang background thread

~~~java
@JmsListener(destination = "jobs.queue")
public void receive(String body, jakarta.jms.Session session) {
    // Không tự session.close().
    // Không lưu session để sử dụng ngoài callback.
}
~~~

Đây là snippet. Session thuộc container và có lifecycle/transaction/threading constraints. Dùng một Session sau khi container đã rollback/recovery hoặc trên thread khác có thể gây lỗi và dữ liệu không nhất quán.

### 6.3. DMLC có gì khác SimpleMessageListenerContainer?

| Đặc điểm | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Factory | DefaultJmsListenerContainerFactory | SimpleJmsListenerContainerFactory |
| Mô hình nhận | Polling qua consumer invokers | Callback JMS provider qua setMessageListener |
| Dynamic scale consumer | Có | Không theo mô hình DMLC |
| Recovery/cache tuning | Linh hoạt hơn | Ít lựa chọn hơn |
| External transaction management | Có hỗ trợ | Hạn chế hơn |
| Phù hợp | Phần lớn Spring JMS workloads | Hệ thống đơn giản cần ít policy |

Không coi một loại luôn nhanh hơn trong mọi provider. Chọn dựa trên transaction/recovery/concurrency yêu cầu, đo trên broker thật.

## 7. Concurrency: một container không đồng nghĩa một consumer

Factory có:

~~~java
factory.setConcurrency("2-6");
~~~

Theo DMLC API, mỗi container có core/min=2, max=6 và có thể scale số invokers khi tải tăng. Đây là cấu hình **cho mỗi endpoint container**, không phải giới hạn toàn ApplicationContext.

**Lỗi tinh vi:** một String chỉ có một số, chẳng hạn "6", là **upper limit 6 với lower mặc định 1**. Nó không tương đương cố định sáu consumers.

| Cấu hình | Core/min | Max | Giải thích |
| --- | ---: | ---: | --- |
| "1-1" | 1 | 1 | Cố định một consumer. |
| "2-2" | 2 | 2 | Cố định hai consumers. |
| "1-6" | 1 | 6 | Dynamic tối đa sáu. |
| "6" | 1 | 6 | Một số đơn là max. |
| "3-10" | 3 | 10 | Ba core, max mười. |

### 7.1. Annotation override

~~~java
@JmsListener(
    id = "auditEndpoint",
    destination = "audit.queue",
    concurrency = "2-2")
public void audit(String payload) { /* ... */ }
~~~

Nếu factory có setConcurrency("1-1"), endpoint audit được cấu hình 2/2 riêng, nhưng endpoint orders vẫn 1/1. Như vậy một factory tạo hai DMLC có settings khác nhau.

### 7.2. Core/max khác current consumer count

~~~java
int core = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();
int active = container.getActiveConsumerCount();
int scheduled = container.getScheduledConsumerCount();
~~~

Snippet này cần container kiểu DefaultMessageListenerContainer. Core và max là các giá trị cấu hình; active/scheduled là runtime metrics, có thể đổi theo load. Không lấy max=6 làm bằng chứng broker luôn có đúng sáu consumers.

### 7.3. Tính tổng resource budget

Nếu có bốn endpoints, mỗi endpoint core 2/max 5, tổng configured core có thể là 8 và max 20 consumers. Broker session limits, DB connection pool, CPU và executor phải đủ cho **toàn bộ endpoints**, chứ không chỉ một factory.

### 7.4. Queue ordering và Topic fan-out

Nhiều Queue consumers cạnh tranh có thể khiến message B xử lý xong trước A dù producer gửi A trước B. Nếu domain yêu cầu strict ordering, dùng concurrency thấp, grouping hoặc partitioning/serial processing.

Topic subscriptions có semantics khác Queue. Tăng concurrency trên Topic không có nghĩa tăng throughput an toàn như Queue; durable/shared subscriptions cần thiết kế và test provider-specific. Tách factory topic với pubSubDomain=true nếu cần.

## 8. Polling, TaskExecutor và receiveTimeout

DMLC có các setter:

~~~java
factory.setReceiveTimeout(1_000L);
factory.setConcurrency("1-4");
// factory.setTaskExecutor(taskExecutor); // Khi có custom executor.
~~~

receiveTimeout là thời gian chờ của **một lần MessageConsumer.receive**, không phải TTL của message và cũng không phải timeout business method. DMLC có thể tiếp tục polling nhiều lần dù một lần receive trả null.

Consumer invoker tasks có thể chạy lâu và giữ thread. Nếu gắn custom TaskExecutor pool nhỏ dùng chung với HTTP/cron, có nguy cơ thread starvation. Hãy giới hạn concurrency và cân nhắc executor riêng. DMLC đã có default executor cho use case thông thường.

API setMaxMessagesPerTask(...) giới hạn số receive attempts của một consumer task trước khi reschedule; đây **không phải batch size của message payload** hoặc số JMS messages được nhận trong một lần receive. Cần đo trước khi tùy chỉnh.

Java 17 chưa có stable virtual threads. Đừng copy ví dụ Java 21+ về DMLC virtual threads rồi kỳ vọng chạy trong demo Java 17.

## 9. JMS cache, native ConnectionFactory và ownership

DMLC có các cache levels:

| Cache level | Ý nghĩa |
| --- | --- |
| CACHE_NONE | Không cache JMS resources ở mức DMLC như các level cao. |
| CACHE_CONNECTION | Cache Connection phù hợp. |
| CACHE_SESSION | Cache Connection và Session. |
| CACHE_CONSUMER | Cache Connection, Session và MessageConsumer. |
| CACHE_AUTO | Spring lựa chọn dựa trên transaction strategy. |

~~~java
factory.setCacheLevelName("CACHE_CONSUMER");
~~~

Đây là snippet. Không luôn chọn cache cao nhất; nó có thể không phù hợp với XA/JTA, recovery hoặc provider-specific behavior.

Spring có CachingConnectionFactory wrapper, thường hữu ích cho JmsTemplate. DMLC tự quản lý resource caching/recovery; lồng một wrapper cache ở bên ngoài có thể làm phức tạp việc đóng/mở lại connections/consumers.

Spring Boot 3.x có helper ConnectionFactoryUnwrapper:

~~~java
// Cần import org.springframework.boot.jms.ConnectionFactoryUnwrapper.
configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
~~~

Đây là snippet, biến configurer/factory/connectionFactory phải có sẵn. Trong ứng dụng thật cần kiểm tra JTA/XA/managed provider proxies; không unwrap tùy tiện mọi ConnectionFactory wrapper.

**Không gọi close() trên JMS Session/Connection do DMLC cung cấp**, không giữ chúng vượt lifecycle method hoặc đưa sang thread khác. Container/transaction manager có quyền tái tạo resources khi recovery.

## 10. Transaction, ack và redelivery

### 10.1. Local transacted Session

~~~java
factory.setSessionTransacted(true);
~~~

Với local JMS transaction, listener method được gọi trong bối cảnh JMS Session transacted; thành công thường dẫn tới commit, exception phù hợp thoát ra dẫn tới rollback. Broker có thể redeliver theo retry policy. JMS transaction không tự bao trùm JDBC transaction, HTTP call hoặc gửi email.

### 10.2. AUTO_ACKNOWLEDGE trong DMLC

Theo Spring DMLC Javadoc, AUTO_ACKNOWLEDGE thường acknowledge trước user listener, nên exception trong handler không mang bảo đảm redelivery đáng tin. Spring khuyến nghị setSessionTransacted(true) hoặc external transaction manager thích hợp khi cần khả năng rollback.

### 10.3. Đừng nuốt exception và báo thành công giả

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    try {
        processOrder(payload);
    } catch (RuntimeException ex) {
        // Chỉ log rồi return có thể khiến container commit/ack.
    }
}
~~~

Đây là anti-pattern; processOrder là business method giả định. Nếu nghiệp vụ cần retry, phải propagate hoặc áp dụng failure policy tường minh, không chỉ return thành công.

### 10.4. Idempotency và transaction ngoài JMS

DB có thể commit rồi JMS commit thất bại: broker redeliver, business side effect lặp. Cần business event ID, idempotent inbox/unique constraint, transactional outbox hoặc reconciliation. JTA/XA có thể giúp atomic multi-resource nhưng chỉ khi thực sự cấu hình hạ tầng/resource hỗ trợ.

### 10.5. Boot default và manual default

Spring Boot auto-configured listener factory thường transactional theo thiết kế: dùng JTA transaction manager nếu có, hoặc local JMS transacted session. Factory do developer new thủ công **không mặc nhiên kế thừa mọi defaults Boot**. Nếu cần giữ properties/transaction/converter, dùng DefaultJmsListenerContainerFactoryConfigurer hoặc tự set tường minh.

## 11. Recovery khi broker bị ngắt

DMLC có logic refresh JMS resources khi provider error. Factory có thể cấu hình:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

Hoặc dùng BackOff. Đây là khoảng kiểm soát retry behavior, không phải lời hứa reconnect hoàn tất chính xác trong năm giây.

~~~text
Container RUNNING
  → Consumer.receive gặp JMS exception
  → Đóng/làm sạch handles lỗi
  → Recovery/backoff
  → Tạo lại Connection/Session/Consumer
  → Tiếp tục polling trên runtime container
~~~

Factory bean không tự bị tạo lại vì broker restart. Phải phân biệt **khôi phục JMS resources bên trong DMLC** với **tạo lại DMLC instance của endpoint**.

### 11.1. isRunning không đồng nghĩa broker healthy

Container có thể báo isRunning=true nhưng đang recovery. Theo dõi broker consumer count, connection metrics, queue lag, last successful receive, recovery log, DLQ và active/scheduled counts, không chỉ registry state.

### 11.2. Start/stop lifecycle qua registry

~~~java
registry.stop();
registry.start();
~~~

Snippet này tác động lên registry-managed containers. Stop không purge queue, không xóa message và không nhất thiết đảm bảo mọi in-flight transaction đã commit tức thì. Rolling deployment cần graceful drain, readiness và idempotency.

## 12. JmsListenerEndpointRegistry: quan sát cái gì được tạo?

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer c =
        registry.getListenerContainer("ordersEndpoint");

if (c == null) {
    throw new IllegalStateException("Endpoint missing");
}
System.out.println(c.getClass().getSimpleName());
System.out.println(c.isRunning());
~~~

Snippet này cần registry bean được inject. Một DMLC tạo từ annotation có thể không xuất hiện trong ApplicationContext bằng tên ID, nhưng registry có thể cung cấp nó.

### 12.1. Registry ID khác destination

~~~java
@JmsListener(
    id = "ordersEndpoint",
    destination = "orders.queue")
public void onOrder(String payload) { /* ... */ }
~~~

ordersEndpoint là ID để quản lý container, orders.queue là tên JMS destination. Hai listeners có thể cùng nghe một Queue nhưng ID khác nhau: chúng là competing consumers, không tự nhận hai bản sao. Với Topic, subscription semantics lại khác.

### 12.2. Registry có nhiều containers

~~~java
for (MessageListenerContainer c :
        registry.getListenerContainers()) {
    System.out.println(c.getClass().getSimpleName());
}
~~~

Snippet giúp quan sát tổng số containers, nhưng khi cần phân biệt endpoint cụ thể nên dùng getListenerContainer(id) với ID rõ ràng.

### 12.3. Không dựa duy nhất vào bean name

Khi có nhiều factories hoặc Boot auto-configuration, endpoint có thể dùng custom factory qua containerFactory attribute. Hãy kiểm tra runtime type và các settings của mỗi container, không suy rằng mọi endpoint luôn dùng cùng một bean chỉ vì đều có @JmsListener.

## 13. Demo Java 17, Spring Boot 3.3, Artemis: hai containers từ một factory

Demo này thực sự tạo một bean factory và hai @JmsListener endpoints:

- ordersEndpoint: queue demo.runtime.orders, concurrency từ factory là "1-1".
- auditEndpoint: queue demo.runtime.audit, annotation override concurrency="2-2".

Registry trả hai DMLC **khác identity**, cùng class. JmsTemplate gửi một TextMessage tới mỗi queue; handlers dùng CountDownLatch để ứng dụng in stdout theo thứ tự ổn định.

### 13.1. Môi trường

Yêu cầu Java 17+, Maven 3, Docker, cổng 61616 còn trống. Dùng một broker Artemis dành riêng cho demo:

~~~bash
docker run --detach --rm --name dmlc-runtime-demo \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ Artemis khởi động trước khi chạy Maven. Tài khoản artemis/artemis là ví dụ môi trường học, không dành cho production. Nếu broker tắt auto-create, tạo hai queues theo ACL hợp lệ trước khi chạy. Dùng broker/queues sạch để tránh nhận messages từ lần chạy trước.

Cấu trúc:

~~~text
dmlc-runtime-demo/
├── pom.xml
└── src/main/
    ├── java/example/dmlcruntime/
    │   ├── DemoApplication.java
    │   ├── JmsConfig.java
    │   └── TwoQueueListener.java
    └── resources/application.properties
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>dmlc-runtime-demo</artifactId>
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

Cố định version để người học tái lập API Spring 6/Jakarta JMS; khi triển khai production nên dùng bản được hỗ trợ theo chính sách tổ chức.

### 13.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Không chạy HTTP server. Listener containers có thể tiếp tục chạy sau khi CommandLineRunner in xong.

### 13.4. JmsConfig.java

~~~java
package example.dmlcruntime;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory factory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        f.setConnectionFactory(connectionFactory);
        f.setPubSubDomain(false);
        f.setSessionTransacted(true);
        f.setConcurrency("1-1");
        f.setReceiveTimeout(1_000L);
        return f;
    }
}
~~~

Đây là một Spring configuration class độc lập. Một factory bean cung cấp policy; chưa có DMLC nếu infrastructure chưa đăng ký endpoints.

### 13.5. TwoQueueListener.java

~~~java
package example.dmlcruntime;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class TwoQueueListener {

    private final CountDownLatch ordersLatch = new CountDownLatch(1);
    private final CountDownLatch auditLatch = new CountDownLatch(1);
    private final AtomicReference<String> order =
            new AtomicReference<>();
    private final AtomicReference<String> audit =
            new AtomicReference<>();

    @JmsListener(
            id = "ordersEndpoint",
            destination = "demo.runtime.orders")
    public void orders(String text) {
        order.set(text);
        ordersLatch.countDown();
    }

    @JmsListener(
            id = "auditEndpoint",
            destination = "demo.runtime.audit",
            concurrency = "2-2")
    public void audit(String text) {
        audit.set(text);
        auditLatch.countDown();
    }

    public boolean awaitBoth(long seconds)
            throws InterruptedException {
        if (!ordersLatch.await(seconds, TimeUnit.SECONDS)) {
            return false;
        }
        return auditLatch.await(seconds, TimeUnit.SECONDS);
    }

    public String orderValue() {
        return order.get();
    }

    public String auditValue() {
        return audit.get();
    }
}
~~~

CountDownLatch ở đây chỉ giúp demo có output xác định; không chứng nhận JMS commit, không thay thế business idempotency/store.

### 13.6. DemoApplication.java

~~~java
package example.dmlcruntime;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            JmsTemplate jms,
            JmsListenerEndpointRegistry registry,
            TwoQueueListener listener) {

        return args -> {
            MessageListenerContainer orders =
                    registry.getListenerContainer("ordersEndpoint");
            MessageListenerContainer audit =
                    registry.getListenerContainer("auditEndpoint");

            if (!(orders instanceof DefaultMessageListenerContainer)
                    || !(audit instanceof DefaultMessageListenerContainer)) {
                throw new IllegalStateException(
                        "Expected two DMLC instances");
            }

            DefaultMessageListenerContainer oc =
                    (DefaultMessageListenerContainer) orders;
            DefaultMessageListenerContainer ac =
                    (DefaultMessageListenerContainer) audit;

            System.out.println(
                    "runtime: "
                    + oc.getClass().getSimpleName()
                    + ", " + ac.getClass().getSimpleName());
            System.out.println("distinct: " + (oc != ac));
            System.out.println(
                    "orders core/max: "
                    + oc.getConcurrentConsumers() + "/"
                    + oc.getMaxConcurrentConsumers());
            System.out.println(
                    "audit core/max: "
                    + ac.getConcurrentConsumers() + "/"
                    + ac.getMaxConcurrentConsumers());

            jms.convertAndSend("demo.runtime.orders", "ORDER-42");
            jms.convertAndSend("demo.runtime.audit", "AUDIT-42");

            if (!listener.awaitBoth(10L)) {
                throw new IllegalStateException(
                        "Listeners not invoked in time");
            }
            System.out.println(
                    "payloads: " + listener.orderValue()
                    + " | " + listener.auditValue());
        };
    }
}
~~~

Trong mã trên, hai endpoint IDs được lấy qua registry; factory mặc định tạo hai runtime DMLC objects. Cả hai cùng class nhưng khác object identity. Vì audit annotation ghi concurrency="2-2", audit config khác orders.

### 13.7. Chạy

Tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Nếu broker sẵn sàng, queues sạch, không có competing consumers và cả hai listeners nhận trong timeout, stdout từ những lệnh System.out.println là:

~~~text
runtime: DefaultMessageListenerContainer, DefaultMessageListenerContainer
distinct: true
orders core/max: 1/1
audit core/max: 2/2
payloads: ORDER-42 | AUDIT-42
~~~

Spring Boot/Artemis có thể in thêm logs. Nếu broker chưa kết nối, queue không được phép auto-create hoặc listener xử lý thất bại, demo sẽ báo exception thay vì in thành công giả.

**Giới hạn phép thử:** latch mở khi handler chạy, trước khi container có thể hoàn tất JMS commit. Vì vậy output chứng minh annotated endpoint đã được triển khai và method đã chạy, **chưa chứng minh** exactly-once hay commit/ack thành công. Khi chạy xong, Ctrl+C để dừng app, sau đó:

~~~bash
docker stop dmlc-runtime-demo
~~~

### 13.8. Bài thử mở rộng

- Đổi audit concurrency="2" rồi so với core/max hiện tại. Theo DMLC API, chuỗi đơn là upper bound 2, lower mặc định 1.
- Tạo listener thứ ba dùng cùng factory; kiểm chứng runtime container count tăng thành ba.
- Chạy hai listeners cùng destination Queue để quan sát competing consumers thay vì broadcast.
- Dừng container qua registry rồi khởi động lại; xem message pending và broker metrics.
- Ném exception trong transacted handler, quan sát redelivery và idempotency.
- Cắt kết nối broker rồi bật lại, xem recovery logs và JMS consumer count.

## 14. Spring Boot auto-configuration và factory tự tạo

Trong Spring Boot có JMS starter/ConnectionFactory hợp lệ, framework có thể tự tạo factory mặc định cho @JmsListener. Không luôn phải khai báo @EnableJms và @Bean thủ công chỉ để có một endpoint cơ bản.

Nếu tự khai báo bean tên jmsListenerContainerFactory, Boot có thể back off theo auto-configuration conditions; manual bean **không tự nhận tất cả Boot properties**.

### 14.1. DefaultJmsListenerContainerFactoryConfigurer

Trong Spring Boot 3.x có class:

~~~java
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
~~~

Một custom factory có thể nhận defaults của Boot:

~~~java
@Configuration
public class BulkConfig {

    @Bean("bulkListenerFactory")
    DefaultJmsListenerContainerFactory bulkFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(f, connectionFactory);
        f.setConcurrency("2-6");
        return f;
    }
}
~~~

Đây là snippet, cần imports Jakarta JMS, Spring Bean/Configuration và Spring JMS class. Gọi configure trước rồi override các policy cụ thể. Với CachingConnectionFactory, xem hướng dẫn dùng native connection factory và helper unwrap đúng Boot version.

### 14.2. Những Boot properties liên quan

~~~properties
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=4
spring.jms.listener.auto-startup=true
~~~

Chúng có thể được áp bởi Boot configurer, nhưng manual factory chỉ gọi setConnectionFactory sẽ không tự nhận đầy đủ mọi setting. Khi một listener bị sai concurrency hoặc transaction policy, xác minh **factory thực tế mà endpoint sử dụng**, không chỉ nhìn application.properties.

### 14.3. Transaction policy khác nhau

Tài liệu Boot mô tả factory auto-configured thường transactional; manual factory vừa new có thể không có cùng default. Cần setSessionTransacted(true) rõ ràng hoặc dùng configurer phù hợp để tránh khác biệt không chủ ý về acknowledge/retry.

## 15. Chẩn đoán sự cố

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Có @JmsListener nhưng registry không thấy | Chưa bật JMS infrastructure hoặc component scan thiếu | Kiểm tra @EnableJms/Boot và @Component. |
| Không tìm thấy default factory | Bean tên khác jmsListenerContainerFactory | Đúng @Bean name hoặc containerFactory attribute. |
| Có factory bean mà chưa có DMLC | Không có endpoint được đăng ký | Kiểm tra @JmsListener methods. |
| Không thấy DMLC Spring bean | DMLC do registry quản lý, không đăng ký bean riêng | Dùng registry.getListenerContainer(id). |
| Lấy đúng ID nhưng isRunning=false | AutoStartup tắt hoặc container đã stop | Kiểm tra lifecycle/registry. |
| isRunning=true mà broker không có consumer | Recovery/network/ACL/wrong domain | Xem logs và broker connections. |
| Một factory mà có nhiều sessions | Có nhiều endpoints hoặc concurrency >1 | Tính tổng consumer budget. |
| Concurrency "4" chỉ thấy một core | "4" là max, không phải 4-4 | Dùng "4-4" nếu cần cố định. |
| Listener đổi thứ tự xử lý | Multiple concurrent consumers | Grouping/partition hoặc giảm concurrency. |
| Broker restart nhưng listener không hồi phục | Cache wrapper, recovery strategy | Xem DMLC recovery, native CF. |
| Không có redelivery khi handler lỗi | AUTO_ACKNOWLEDGE hoặc nuốt exception | Cấu hình transaction và propagate error. |
| Lỗi deserialize JSON | Converter/DTO/schema mismatch | Kiểm tra raw JMS Message và MessageConverter. |
| Topic nhận message trùng | Subscription/concurrency sai | Tách topic factory, test shared/durable config. |
| Queue có message nhưng listener không nhận | Selector không match, domain/resolver sai | Inspect JMS properties và broker topology. |
| Manual factory bỏ qua Boot properties | Không qua configurer | Dùng configurer hoặc set trực tiếp. |
| Sửa factory settings runtime không có tác dụng | Container được tạo trước đó | Điều khiển container phù hợp hoặc rollout. |

### 15.1. Quy trình debug có thứ tự

1. Kiểm tra ConnectionFactory/ACL và broker thực.
2. Kiểm tra factory bean name/type.
3. Kiểm tra @EnableJms/Boot infrastructure, Spring-managed listener beans.
4. Kiểm tra @JmsListener ID, destination, selector, containerFactory, concurrency.
5. Tra registry và class thực của runtime container.
6. Đọc core/max/active/scheduled consumers, recovery logs, broker metrics.
7. Kiểm tra MessageConverter, arguments, transaction/ack, redelivery/DLQ.
8. Chạy integration test đúng broker/provider và versions.

## 16. Những nhầm lẫn cần nhớ

**Sai 1:** Một factory chỉ tạo một DMLC. **Đúng:** Factory có thể tạo DMLC riêng cho mỗi registered endpoint.

**Sai 2:** Mỗi message tới lại tạo một DMLC. **Đúng:** Container sống qua nhiều lần receive; JMS resources bên trong có thể refresh.

**Sai 3:** @JmsListener ID chính là bean name của DMLC. **Đúng:** Nó chủ yếu là key trong JmsListenerEndpointRegistry.

**Sai 4:** Một DMLC chỉ có một JMS consumer. **Đúng:** Concurrency có thể tạo nhiều consumer invokers.

**Sai 5:** setConcurrency("4") luôn tạo cố định bốn core consumers. **Đúng:** DMLC diễn giải chuỗi đơn là maximum, dùng "4-4" để cố định.

**Sai 6:** isRunning=true có nghĩa broker connection khỏe. **Đúng:** Container có thể vẫn đang recovery; xem broker logs/metrics.

**Sai 7:** Transaction JMS đồng thời commit DB. **Đúng:** Local JMS transaction chỉ quản lý JMS; cần XA/JTA hoặc design khác.

**Sai 8:** Simple factory và Default factory luôn tạo cùng runtime type. **Đúng:** Một bên tạo SimpleMessageListenerContainer, bên kia tạo DefaultMessageListenerContainer.

**Sai 9:** Config factory sau khi start sẽ tự cập nhật tất cả DMLC. **Đúng:** Containers đã tồn tại có state riêng; cần quản lý runtime hoặc rollout.

**Sai 10:** JMS MessageConverter tự xử lý retry. **Đúng:** Converter chuyển payload; ack/recovery/transaction do container policies quản lý.

## 17. Checklist và bài tập

### Checklist production

- [ ] Biết factory bean đang phục vụ mỗi endpoint.
- [ ] Biết số annotated endpoint registrations và runtime DMLC instances.
- [ ] Tính tổng consumer count từ concurrency của mọi container.
- [ ] Đặt endpoint IDs duy nhất, ổn định.
- [ ] Queue/Topic và selector/resolver đúng contract.
- [ ] Cấu hình transaction/ack có idempotency.
- [ ] Kiểm thử retry/backoff, recovery và DLQ.
- [ ] Resource caching/native ConnectionFactory/JTA được xác minh.
- [ ] TaskExecutor, broker connection/session limits, DB pool có capacity.
- [ ] Runtime monitoring dùng registry kết hợp broker metrics.
- [ ] Graceful shutdown/drain và rolling deployment được test.
- [ ] Không kỳ vọng mutate factory sau startup tự thay đổi containers.
- [ ] Integration/load tests chạy trên broker và Spring versions thực.

### Bài tập

1. Chạy demo và xác nhận hai DMLC instances distinct.
2. Thêm @JmsListener thứ ba và quan sát registry có thêm container.
3. So sánh concurrency "2" và "2-2" qua getConcurrentConsumers/getMaxConcurrentConsumers.
4. Gửi 50 messages để quan sát active/scheduled counts theo tải.
5. Dùng hai listeners cùng Queue, giải thích competing-consumer semantics.
6. Tạo topic factory riêng và kiểm tra subscription behavior.
7. Tắt broker trong lúc app đang chạy, xem recovery logs rồi khởi động lại.
8. Với JMS transaction bật, ném exception rồi quan sát redelivery.
9. Đổi factory bean name và dùng annotation containerFactory để chọn đúng.
10. Dùng Boot configurer tạo bulkFactory và đối chiếu Boot properties.
11. Viết integration test assert registry IDs, runtime class, distinct identities.
12. So sánh DefaultMessageListenerContainer với SimpleMessageListenerContainer dưới cùng workload.

## 18. Tài liệu tham khảo

- Spring Framework — Annotation-driven JMS Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using JMS / Listener Containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Receiving and Transactions: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — AbstractJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html
- Spring Framework 6.2 — DefaultMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS guide (cùng dòng API với demo Boot 3.3): https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot — Getting Started with JMS: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
