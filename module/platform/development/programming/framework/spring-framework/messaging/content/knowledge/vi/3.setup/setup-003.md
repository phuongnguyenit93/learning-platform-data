# Khai báo các bean hạ tầng bằng Java Configuration

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của `@Configuration`, `@Bean` và dependency injection khi dựng hạ tầng messaging.
- Phân biệt abstraction của Spring Messaging, các thành phần của Spring Integration và adapter kết nối broker.
- Khai báo `MessageChannel`, `IntegrationFlow` và các endpoint bằng Java Configuration.
- Chọn loại channel phù hợp với cách dispatch, buffering và xử lý đồng thời.
- Khai báo các bean RabbitMQ hoặc JMS cần thiết mà không hard-code thông tin môi trường.
- Kiểm tra cấu hình khi khởi động và tránh các lỗi thường gặp về bean, channel, thread và lifecycle.

## 1. Xác định lớp hạ tầng cần cấu hình

Từ “messaging” trong hệ sinh thái Spring có thể chỉ nhiều lớp khác nhau. Trước khi khai báo bean, cần xác định lớp mà ứng dụng đang sử dụng:

| Lớp | Vai trò | Ví dụ kiểu hoặc API |
|---|---|---|
| Spring Messaging | Mô hình message và giao diện giao tiếp chung | `Message<T>`, `MessageChannel`, `MessageHandler`, `MessageBuilder` |
| Spring Integration | Kênh, endpoint, bộ chuyển đổi và luồng tích hợp trong ứng dụng | `DirectChannel`, `QueueChannel`, `IntegrationFlow`, `@ServiceActivator` |
| Transport adapter / client | Kết nối tới hệ thống bên ngoài hoặc broker | Spring AMQP, Spring JMS, Spring for Apache Kafka, MQTT adapter |

Spring Framework cung cấp abstraction trong module `spring-messaging`. Những interface này mô tả message và cách gửi message; chúng không tự cung cấp broker, queue phân tán hay cơ chế lưu bền.

Spring Integration xây dựng các thành phần xử lý message trên các abstraction đó. `DirectChannel`, `PublishSubscribeChannel` và `QueueChannel` là các triển khai thuộc Spring Integration. Java DSL của Spring Integration cho phép ghép các endpoint thành một `IntegrationFlow`.

RabbitMQ, Kafka hoặc JMS provider là lớp vận chuyển riêng. Khi cần trao đổi giữa các tiến trình, ứng dụng phải cấu hình client hoặc adapter tương ứng. Một channel trong bộ nhớ của Spring Integration không tự trở thành message broker.

Một ứng dụng có thể phối hợp cả ba lớp:

~~~text
Business service
    |
    v
Spring Messaging: Message / MessageChannel
    |
    v
Spring Integration: channel -> transform -> handler
    |
    +----> xử lý nội bộ trong ApplicationContext
    |
    +----> outbound adapter -> RabbitMQ / Kafka / JMS
                                  |
                                  v
                             service khác
~~~

Phần tiếp theo tập trung vào cách đăng ký bean cho các lớp này bằng Java Configuration.

## 2. Cơ chế Java Configuration của Spring

### @Configuration và @Bean

`@Configuration` đánh dấu một lớp là nguồn định nghĩa bean. Mỗi phương thức có `@Bean` tạo hoặc cấu hình một đối tượng để Spring quản lý trong `ApplicationContext`.

~~~java
@Configuration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new DirectChannel();
    }
}
~~~

Tên bean mặc định là tên phương thức, trong ví dụ là `ordersChannel`. Có thể đặt tên khác bằng `@Bean("orderInputChannel")` hoặc khai báo alias khi cần.

Các nguyên tắc quan trọng:

1. **Khai báo kiểu trả về phù hợp:** dùng kiểu cụ thể khi thành phần khác cần tra cứu hoặc inject implementation; dùng interface khi muốn giảm phụ thuộc vào implementation.
2. **Để Spring inject dependency:** tham số của phương thức `@Bean` được Spring giải quyết từ các bean trong context, tương tự constructor injection.
3. **Không tự tạo lại dependency:** nếu một bean cần `ConnectionFactory`, nhận nó qua tham số phương thức thay vì gọi constructor tạo kết nối mới trong nhiều nơi.
4. **Hiểu proxy của configuration class:** `@Configuration` mặc định dùng cơ chế proxy để điều phối lời gọi giữa các phương thức `@Bean`. Với `@Configuration(proxyBeanMethods = false)`, các lời gọi Java trực tiếp giữa những phương thức đó không được intercept; hãy dùng tham số phương thức để nhận bean phụ thuộc.
5. **Chú ý scope và lifecycle:** bean mặc định là singleton. Với executor, connection factory hoặc listener container, cấu hình khởi tạo và đóng tài nguyên đúng vòng đời của context.

Ví dụ inject dependency qua tham số:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    public MessageConverter messageConverter() {
        return new StringMessageConverter();
    }

    @Bean
    public MessagePublisher messagePublisher(
            MessageChannel ordersChannel,
            MessageConverter messageConverter) {
        return new MessagePublisher(ordersChannel, messageConverter);
    }
}
~~~

Ví dụ trên minh họa cách truyền dependency; `StringMessageConverter` và `MessagePublisher` là các kiểu giả định do ứng dụng định nghĩa. Trong cấu hình thực tế, cần dùng implementation tương ứng với thư viện messaging đang chọn.

### Chia cấu hình thành nhiều lớp

Không nên dồn tất cả hạ tầng vào một lớp cấu hình lớn. Có thể tách theo trách nhiệm:

- `MessagingCoreConfiguration`: channel và các thành phần Spring Integration dùng chung.
- `OrderFlowConfiguration`: các flow xử lý nghiệp vụ của module Order.
- `RabbitInfrastructureConfiguration`: connection, exchange, queue, binding và listener container.
- `JmsInfrastructureConfiguration`: `JmsTemplate` và listener container của JMS.
- `MessagingProperties`: cấu hình có thể thay đổi theo môi trường.

Dùng `@Import` để ghép các lớp cấu hình:

~~~java
@Configuration
@Import({
    MessagingCoreConfiguration.class,
    OrderFlowConfiguration.class
})
public class ApplicationMessagingConfiguration {
}
~~~

Cách này giúp một ứng dụng chỉ import phần hạ tầng mà nó thực sự dùng. Nếu có nhiều môi trường, có thể dùng `@Profile` hoặc cơ chế điều kiện của Spring Boot để chọn adapter tương ứng.

## 3. Bật hạ tầng Spring Integration

Khi cấu hình Spring Integration hoàn toàn bằng Java, dùng `@EnableIntegration` trên lớp cấu hình:

~~~java
@Configuration
@EnableIntegration
public class IntegrationConfiguration {
    // Các bean MessageChannel và IntegrationFlow
}
~~~

Annotation này đăng ký hạ tầng nền cần thiết cho Spring Integration, bao gồm các processor hỗ trợ endpoint và annotation, các thành phần mặc định như `errorChannel`, cùng hạ tầng scheduler dùng cho poller.

`@EnableIntegration` không tự kết nối RabbitMQ, Kafka hoặc JMS. Nó bật hạ tầng Spring Integration trong `ApplicationContext`. Muốn gửi message qua mạng, phải khai báo adapter/client và kết nối tương ứng.

Nếu ứng dụng dùng Spring Boot và starter của Spring Integration, một số phần cấu hình có thể đã được auto-configuration cung cấp. Trước khi tạo bean trùng tên hoặc trùng chức năng, hãy kiểm tra cấu hình đang được ứng dụng bật.

## 4. Khai báo MessageChannel bằng bean

Một `MessageChannel` là điểm nhận message từ producer và chuyển message tới consumer. Loại channel quyết định cách message được dispatch hoặc buffer.

### DirectChannel

~~~java
@Bean
public MessageChannel orderInputChannel() {
    return new DirectChannel();
}
~~~

`DirectChannel` là channel dạng subscribe, thường dùng cho luồng xử lý đồng bộ. Khi producer gửi message, handler được gọi trong thread gửi message. Nếu có nhiều subscriber, dispatcher chọn subscriber xử lý từng message theo chiến lược phân phối của channel; mặc định có load balancing và failover.

Dùng khi một message cần được xử lý bởi một handler trong luồng hiện tại. Đây là lựa chọn phổ biến cho các bước nối tiếp trong một integration flow.

### PublishSubscribeChannel

~~~java
@Bean
public MessageChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

`PublishSubscribeChannel` phát một message tới tất cả subscriber đã đăng ký. Nó phù hợp khi nhiều thành phần cùng cần nhận một thông báo, ví dụ audit, cập nhật chỉ mục và gửi thông báo nội bộ.

Nếu truyền `TaskExecutor` vào channel, việc xử lý subscriber có thể được dispatch bất đồng bộ. Khi đó cần xem xét thứ tự hoàn tất, xử lý exception và giới hạn executor. Không có executor thì subscriber thường chạy trên thread gửi message.

### QueueChannel

~~~java
@Bean
public PollableChannel pendingOrdersChannel() {
    return new QueueChannel(100);
}
~~~

`QueueChannel` lưu message trong một queue để consumer có thể nhận bằng thao tác poll/receive. Đây là channel dạng pollable, có semantics point-to-point: một message được lấy bởi một consumer.

Nên đặt capacity cụ thể. Queue không giới hạn có thể giữ quá nhiều message trong heap khi producer nhanh hơn consumer. `QueueChannel` mặc định lưu trong bộ nhớ; message có thể mất khi process dừng. Muốn lưu bền cần cấu hình một `MessageStore` phù hợp, và ngay cả khi đó cũng phải đánh giá transaction, recovery và giới hạn của store.

### ExecutorChannel

`ExecutorChannel` dispatch message thông qua `TaskExecutor`, cho phép handler xử lý trên thread khác. Nó hữu ích khi cần tách thread producer khỏi consumer. Tuy nhiên, executor queue vẫn là tài nguyên trong process; nó không cung cấp durable delivery hay khả năng trao đổi liên tiến trình.

### Bảng chọn channel

| Channel | Cách phân phối | Thread xử lý mặc định | Buffer |
|---|---|---|---|
| `DirectChannel` | Một subscriber được chọn cho mỗi message | Thread gửi | Không có queue riêng |
| `PublishSubscribeChannel` | Tất cả subscriber | Thread gửi nếu không có executor | Không có queue riêng |
| `QueueChannel` | Một consumer nhận mỗi message | Consumer gọi receive/poll | Queue trong bộ nhớ hoặc store được cấu hình |
| `ExecutorChannel` | Một subscriber được chọn | Executor thread | Phụ thuộc executor |

Không nên dùng channel chỉ vì tên của nó nghe giống queue hoặc topic. Hãy xác định rõ số consumer cần nhận một message, có cần buffer không, có cần đổi thread không và yêu cầu lưu bền là gì.

## 5. Khai báo IntegrationFlow bằng Java DSL

Spring Integration Java DSL biểu diễn một luồng message bằng bean kiểu `IntegrationFlow`. Các bước như filter, transform, route và handle được ghép thành một chuỗi rõ ràng. Khi context khởi động, Spring Integration đăng ký các endpoint và channel cần thiết cho flow.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orderInputChannel")
                .<String, String>transform(String::trim)
                .filter((String payload) -> !payload.isBlank())
                .handle(String.class, (payload, headers) -> {
                    System.out.println("Handled order: " + payload);
                    return null;
                })
                .get();
    }
}
~~~

Giải thích:

- `IntegrationFlow.from("orderInputChannel")` bắt đầu flow từ channel có tên đó. Nếu channel bean đã tồn tại, flow dùng bean đó.
- `transform(String::trim)` biến đổi payload trước khi xử lý tiếp.
- `filter(...)` chỉ cho message có payload thỏa điều kiện đi tiếp.
- `handle(...)` gọi handler cuối. Trả về `null` có nghĩa không phát reply message từ endpoint này.
- `get()` hoàn tất việc xây dựng flow.

Các bước liền kề không khai báo channel riêng thường được nối bằng các channel nội bộ do DSL tạo ra, mặc định là `DirectChannel`. Nếu một channel cần được nhiều flow hoặc bean khác dùng chung, hãy khai báo nó thành bean có tên rõ ràng và tham chiếu bằng tên đó.

Có thể dùng `@ServiceActivator`, `@Transformer`, `@Filter` hoặc `@Router` trên bean/phương thức để khai báo endpoint theo annotation. Các annotation endpoint này thuộc Spring Integration; chúng không phải annotation của module Spring Messaging cốt lõi.

## 6. Ví dụ hoàn chỉnh có thể chạy

Ví dụ sau dùng Java 17 và Spring Integration 6.5.2. Nó tạo một channel nội bộ, chuẩn hóa chuỗi đầu vào rồi xử lý message. Không cần RabbitMQ hay broker bên ngoài.

Cấu trúc thư mục:

~~~text
java-configuration-messaging/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessagingApplication.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>java-configuration-messaging</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/MessagingApplication.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingApplication {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             MessagingConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orderInputChannel",
                    MessageChannel.class
            );

            boolean sent = input.send(
                    MessageBuilder.withPayload("  ORD-1001  ").build()
            );

            System.out.println("send returned: " + sent);
        }
    }
}

@Configuration(proxyBeanMethods = false)
@EnableIntegration
class MessagingConfiguration {

    @Bean
    public MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orderInputChannel")
                .<String, String>transform(String::trim)
                .handle(String.class, (payload, headers) -> {
                    System.out.println("Handled order: " + payload);
                    return null;
                })
                .get();
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.MessagingApplication
~~~

Kết quả stdout:

~~~text
Handled order: ORD-1001
send returned: true
~~~

Kết quả thể hiện rằng channel bean đã được đăng ký, flow được tạo khi context khởi động và message được xử lý đồng bộ trước khi lời gọi `send()` trả về. Nếu đổi `DirectChannel` thành `ExecutorChannel`, thời điểm handler hoàn tất có thể nằm sau khi `send()` trả về.

## 7. Khai báo hạ tầng RabbitMQ bằng Java Configuration

Khi cần kết nối broker RabbitMQ, Spring AMQP cung cấp các bean phổ biến:

- `ConnectionFactory`: quản lý kết nối tới broker.
- `RabbitTemplate`: gửi và nhận message theo request/reply hoặc các thao tác template.
- `Queue`, `Exchange`, `Binding`: mô tả topology.
- `RabbitAdmin`: khai báo topology lên broker.
- `SimpleRabbitListenerContainerFactory`: tạo listener container cho các phương thức `@RabbitListener`.

Ví dụ dưới đây giả định một bean `ConnectionFactory` đã được cung cấp, chẳng hạn bởi Spring Boot từ cấu hình môi trường:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class RabbitMessagingConfiguration {

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable("orders.queue").build();
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders.exchange");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("orders.created");
    }

    @Bean
    public RabbitAdmin rabbitAdmin(ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        return new RabbitTemplate(connectionFactory);
    }

    @Bean
    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(5);
        return factory;
    }
}
~~~

Các import chính:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

Một listener có thể tham chiếu queue và container factory:

~~~java
@Component
public class OrderListener {

    @RabbitListener(
            queues = "orders.queue",
            containerFactory = "rabbitListenerContainerFactory"
    )
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Lưu ý khi triển khai:

1. `@EnableRabbit` bật việc phát hiện và đăng ký endpoint `@RabbitListener`; nó không tự tạo broker hoặc thay thế `ConnectionFactory`.
2. `RabbitAdmin` có thể tự khai báo các bean topology như queue, exchange và binding khi kết nối tới broker.
3. Queue durable chỉ là một phần của độ bền. Cần cấu hình persistence của message, acknowledgement, retry, publisher confirms và chính sách DLQ theo yêu cầu nghiệp vụ.
4. Không ghi username, password hoặc địa chỉ broker nhạy cảm trong mã nguồn. Đưa chúng vào cấu hình ngoài, secret store hoặc biến môi trường.
5. Với Spring Boot, `ConnectionFactory`, `RabbitTemplate`, `RabbitAdmin` và listener factory có thể đã được auto-configure. Chỉ khai báo bean tùy chỉnh khi cần thay đổi hành vi hoặc ứng dụng không dùng Boot; tránh tạo bean trùng lặp.
6. Đưa các kiểu `Queue`, `Exchange` và `Binding` vào bean không có nghĩa message đã được gửi. Chúng mô tả topology; producer vẫn phải gọi `RabbitTemplate` hoặc adapter gửi message.

## 8. Khai báo hạ tầng JMS bằng Java Configuration

Với JMS provider, Spring JMS thường dùng `jakarta.jms.ConnectionFactory`, `JmsTemplate` và `DefaultJmsListenerContainerFactory`. Provider chịu trách nhiệm cung cấp kết nối thực tế.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsMessagingConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(
            jakarta.jms.ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            jakarta.jms.ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-5");
        return factory;
    }
}
~~~

Listener có thể nhận message bằng `@JmsListener`:

~~~java
@Component
public class BillingListener {

    @JmsListener(
            destination = "billing.events",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(String payload) {
        System.out.println("Billing event: " + payload);
    }
}
~~~

`@EnableJms` bật annotation-driven listener infrastructure; nó không tự tạo JMS broker hoặc cung cấp connection factory. Nếu dùng Spring Integration để nối JMS với flow, cần thêm adapter/module tương ứng và cấu hình channel/endpoint cho luồng đó.

## 9. Kiểm tra cấu hình khi khởi động

Một cấu hình messaging tốt cần được kiểm tra ngay khi context khởi tạo:

- **Bean tồn tại:** kiểm tra tên và kiểu bean bằng `ApplicationContext.getBean(...)` hoặc `getBeansOfType(...)`.
- **Dependency hợp lệ:** xác nhận mỗi `@Bean` nhận đúng `ConnectionFactory`, converter, executor hoặc channel.
- **Tên channel thống nhất:** `IntegrationFlow.from("...")`, `@ServiceActivator(inputChannel = "...")` và producer phải tham chiếu đúng cùng tên.
- **Flow được đăng ký:** kiểm tra log khởi tạo và bean endpoint do Spring Integration tạo.
- **Broker sẵn sàng:** xác nhận kết nối, authentication, exchange/queue/binding và quyền truy cập.
- **Message có thể đi qua:** gửi một message kiểm thử và quan sát handler/consumer nhận được.
- **Lifecycle:** đóng context phải dừng listener container và executor theo cấu hình; không để thread hoặc connection tồn tại ngoài vòng đời ứng dụng.

Có thể viết integration test bằng `AnnotationConfigApplicationContext` hoặc Spring Test để kiểm tra channel và flow. Với broker thật, dùng broker test hoặc Testcontainers để xác minh topology, serialization và acknowledgement. Test chỉ kiểm tra bean tồn tại chưa đủ chứng minh message được định tuyến và xử lý thành công.

## 10. Lỗi cấu hình thường gặp

1. **Quên `@EnableIntegration` trong cấu hình Java thuần.** Các annotation/endpoint hoặc Java DSL có thể không được xử lý đúng vì thiếu infrastructure của Spring Integration.
2. **Nhầm `MessageChannel` với broker queue.** `DirectChannel` và `QueueChannel` thuộc process hiện tại; chúng không gửi message qua mạng.
3. **Dùng `@Configuration(proxyBeanMethods = false)` rồi gọi trực tiếp phương thức `@Bean`.** Lời gọi đó là Java method call thông thường và có thể tạo object mới. Hãy inject bean qua tham số phương thức.
4. **Khai báo channel không cùng tên với flow.** Một lỗi chính tả trong `from("...")` hoặc `inputChannel` có thể làm endpoint không kết nối như dự kiến.
5. **Dùng `QueueChannel` không giới hạn.** Producer có thể đẩy message nhanh hơn consumer và làm heap tăng liên tục. Đặt capacity, timeout và chiến lược back-pressure phù hợp.
6. **Cho rằng `QueueChannel` mặc định lưu bền.** Nó lưu trong bộ nhớ; process dừng có thể làm mất message đang chờ.
7. **Dùng `PublishSubscribeChannel` khi chỉ muốn một consumer nhận.** Channel này broadcast tới tất cả subscriber; hãy dùng kiểu channel có semantics point-to-point nếu chỉ cần một consumer cho mỗi message.
8. **Tạo executor không giới hạn.** Số thread và queue tăng không kiểm soát có thể làm cạn tài nguyên. Cấu hình pool size, queue capacity và rejection policy.
9. **Khai báo listener factory nhưng quên bật annotation support.** Với RabbitMQ cần `@EnableRabbit`; với JMS cần `@EnableJms`.
10. **Tạo topology nhưng không có quyền khai báo trên broker.** RabbitAdmin cần quyền phù hợp để tạo queue, exchange và binding; xác minh quyền và tên tài nguyên ở môi trường triển khai.
11. **Tạo bean trùng với auto-configuration.** Kiểm tra bean hiện có trước khi thay thế hoặc đặt tên bean tùy chỉnh rõ ràng.
12. **Đặt thông tin kết nối trong mã nguồn.** Dùng cấu hình ngoài và quản lý secret theo môi trường.

## 11. Checklist thiết kế

- [ ] Xác định đang dùng Spring Messaging, Spring Integration hay adapter của broker.
- [ ] Bật đúng infrastructure annotation: `@EnableIntegration`, `@EnableRabbit` hoặc `@EnableJms`.
- [ ] Khai báo channel theo semantics cần thiết: direct, publish-subscribe, queue hoặc executor.
- [ ] Đặt tên bean và channel nhất quán, dễ truy vết.
- [ ] Inject dependency qua tham số phương thức `@Bean`.
- [ ] Không gọi trực tiếp phương thức `@Bean` khi dùng `proxyBeanMethods = false`.
- [ ] Đặt capacity cho queue và giới hạn cho executor.
- [ ] Tách cấu hình broker khỏi cấu hình flow nội bộ.
- [ ] Đưa host, credential và thông tin môi trường ra khỏi mã nguồn.
- [ ] Kiểm tra context startup, kết nối broker, topology và luồng message thực tế.
- [ ] Đảm bảo listener container, connection và executor được dừng đúng lifecycle.

## 12. Kết luận

Java Configuration biến hạ tầng messaging thành các bean có tên, kiểu và dependency rõ ràng trong `ApplicationContext`. `@Configuration` và `@Bean` tạo ra các thành phần; `@EnableIntegration` bật hạ tầng Spring Integration; `MessageChannel` quyết định cách message được chuyển trong ứng dụng; `IntegrationFlow` ghép các bước xử lý; còn RabbitMQ hoặc JMS cần connection factory, template, topology và listener container riêng. Khi thiết kế, hãy phân biệt channel nội bộ với transport liên tiến trình, cấu hình tài nguyên có giới hạn và kiểm thử toàn bộ đường đi của message.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference: Using the @Configuration annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html) — lớp cấu hình và dependency giữa các bean.
- [Spring Framework Reference: Using the @Bean annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html) — khai báo bean, dependency, lifecycle và scope.
- [Spring Integration Reference: Overview and @EnableIntegration](https://docs.spring.io/spring-integration/reference/overview.html) — hạ tầng được đăng ký khi bật Spring Integration.
- [Spring Integration Reference: Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — Java Configuration cho DirectChannel, PublishSubscribeChannel và QueueChannel.
- [Spring Integration Reference: Working With Message Flows](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html) — khai báo IntegrationFlow bằng Java DSL.
- [Spring Integration Reference: Service Activators and .handle()](https://docs.spring.io/spring-integration/reference/7.0/dsl/java-handle.html) — xử lý message bằng handler và lambda.
- [Spring AMQP Reference: Enable Listener Endpoint Annotations](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html) — @EnableRabbit và listener container factory.
- [Spring AMQP Reference: AmqpTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — gửi và nhận message bằng RabbitTemplate.
