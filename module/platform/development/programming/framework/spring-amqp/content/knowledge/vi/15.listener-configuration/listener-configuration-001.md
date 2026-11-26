# @EnableRabbit trong Spring thuần và tự cấu hình trong Spring Boot

Với Spring AMQP, phương thức được đánh dấu `@RabbitListener` có thể trở thành consumer nhận message từ một queue RabbitMQ. Nhưng **chỉ đặt annotation lên phương thức là chưa đủ trong mọi kiểu ứng dụng**: framework còn cần một bộ xử lý annotation, một listener container factory, connection tới broker và queue đã tồn tại.

Trong **Spring thuần** (không dùng Spring Boot), lập trình viên thường bật hạ tầng lắng nghe bằng **`@EnableRabbit`** và tự khai báo các bean cần thiết. Trong **Spring Boot**, dependency `spring-boot-starter-amqp` và cơ chế auto-configuration thường cung cấp sẵn connection factory, `RabbitTemplate`, listener container factory và hạ tầng nhận diện `@RabbitListener`. Hiểu sự khác nhau này giúp tránh lỗi “annotation có nhưng consumer không chạy”, đồng thời dễ quyết định khi nào cần tự cấu hình.

Bài thuộc chương **Listener khai báo** của module **SPRING_AMQP**. Chúng ta sẽ thực hành tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding; sau đó liên hệ đến acknowledgment, retry, dead-letter, transaction và quan sát hệ thống để xây dựng xử lý bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích nhiệm vụ của `@EnableRabbit` và những thành phần nó **không** tự tạo.
2. Viết một ứng dụng **Spring thuần** có `@RabbitListener` hoạt động bằng Java configuration.
3. Viết ví dụ tương đương với **Spring Boot auto-configuration** và `application.yml`.
4. Phân biệt `ConnectionFactory`, `RabbitTemplate`, `RabbitAdmin`, `RabbitListenerEndpointRegistry` và `RabbitListenerContainerFactory`.
5. Tùy chỉnh concurrency, prefetch, acknowledgment, lỗi/requeue và converter mà không vô tình bỏ qua cấu hình Boot.
6. Chẩn đoán listener không nhận message, ACK không đúng, queue chưa khai báo hoặc consumer hoạt động sai chế độ.

## 2. Một `@RabbitListener` cần những gì?

Xét listener đơn giản:

~~~java
@RabbitListener(queues = "demo.listener.orders")
public void onOrder(String orderId) {
    System.out.println("Đã nhận đơn: " + orderId);
}
~~~

Để phương thức được gọi, những thành phần dưới đây phải cùng hoạt động:

~~~mermaid
flowchart TB
    A["Bean có @RabbitListener"] --> B["RabbitListenerAnnotationBeanPostProcessor<br/>đọc annotation"]
    B --> R["RabbitListenerEndpointRegistry<br/>quản lý listener containers"]
    R --> F["RabbitListenerContainerFactory<br/>tạo listener container"]
    F --> C["AMQP ConnectionFactory<br/>tạo connection/channel"]
    C --> Q["RabbitMQ queue<br/>demo.listener.orders"]
    P["RabbitTemplate<br/>producer"] --> X["Direct exchange<br/>demo.listener.events"]
    X -->|"Binding: order.created"| Q
    Q -->|"Deliver message"| C
~~~

| Thành phần | Trách nhiệm | Điểm cần lưu ý |
|---|---|---|
| `@RabbitListener` | Khai báo method/class nhận message | Không phải bản thân consumer đang chạy; phải được hạ tầng đăng ký |
| `@EnableRabbit` | Kích hoạt xử lý các annotation listener trong Spring application context | Không tự tạo connection tới RabbitMQ, queue hay exchange |
| `RabbitListenerAnnotationBeanPostProcessor` | Phát hiện `@RabbitListener` trong bean và tạo endpoint | Listener class phải là **Spring-managed bean** |
| `RabbitListenerEndpointRegistry` | Quản lý vòng đời các listener container được tạo từ annotation | Có thể tìm container theo `id` listener |
| `RabbitListenerContainerFactory` | Tạo container thực tế, cấu hình concurrency, prefetch, ack, converter... | Factory mặc định thường mang tên `rabbitListenerContainerFactory` |
| `ConnectionFactory` | Tạo và quản lý AMQP connection/channel tới broker | Cần host, port, credentials, vhost, TLS phù hợp |
| `RabbitTemplate` | Gửi message, có thể nhận request/reply | Không phải consumer; không tự bảo đảm message được xử lý |
| `RabbitAdmin` / `AmqpAdmin` | Khai báo exchange, queue, binding do Spring quản lý | Cần được cấu hình nếu muốn ứng dụng tự khai báo topology |

**Quan trọng:** `@EnableRabbit` bật *khả năng đọc listener annotation*, còn **listener container factory** quyết định cách listener chạy. Một ứng dụng có thể kết nối RabbitMQ bằng `RabbitTemplate` thành công nhưng **không có consumer** nếu thiếu hạ tầng listener hoặc không có bean chứa `@RabbitListener`.

### `@EnableRabbit` làm gì và không làm gì?

Ở Spring AMQP, `@EnableRabbit` import cơ sở hạ tầng annotation-driven để tìm `@RabbitListener` và đăng ký các endpoint lắng nghe. Nó **không** tự:

- Đoán RabbitMQ đang ở máy nào hay tạo tài khoản đăng nhập.
- Tạo queue/exchange/binding theo tên trong `queues = "..."`.
- Cung cấp `RabbitTemplate` hoặc JSON converter theo yêu cầu riêng của ứng dụng.
- Quyết định chính sách retry, giới hạn giao nhận, DLX hoặc idempotency.

Muốn gọi `@RabbitListener(queues = "orders")` mà queue chưa có, bạn phải **khai báo queue** ở broker bằng ứng dụng, CLI/Management hay hệ thống provisioning khác. Annotation `queues` thông thường chỉ là **tham chiếu tên**, không phải mệnh lệnh tạo queue.

## 3. Khởi tạo RabbitMQ cho các ví dụ

Để tự chạy các ví dụ, cần một RabbitMQ broker. Trong môi trường học tập, có thể dùng Docker:

~~~bash
docker run -d --name rabbitmq-listener-lab -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -e RABBITMQ_DEFAULT_USER=lab -e RABBITMQ_DEFAULT_PASS=lab123456 rabbitmq:4-management
~~~

- AMQP: `localhost:5672`.
- RabbitMQ Management: `http://localhost:15672`.
- Tài khoản lab: `lab` / `lab123456`.

Nếu broker/cổng đã được sử dụng, dùng broker có sẵn hoặc đổi cổng tương ứng. Đây là tài khoản minh họa dành cho local, **không ghi mật khẩu thật vào source code**, không mở Management ra Internet và nên dùng secrets/TLS/permissions tối thiểu cho môi trường production.

Ta dùng topology chung để so sánh hai cách khởi tạo:

~~~text
RabbitTemplate
  -> Direct exchange: demo.listener.events
  -> Routing key:     order.created
  -> Queue:           demo.listener.orders
  -> @RabbitListener
~~~

**Hai phần Spring thuần và Spring Boot là hai ứng dụng demo thay thế nhau**: không khởi động đồng thời cả hai listener cùng tiêu thụ một queue nếu mục đích là so sánh kết quả của từng ứng dụng. Khi cùng nghe một queue, chúng trở thành **competing consumers**, mỗi message thường chỉ được giao cho một consumer.

## 4. Spring thuần: tự bật `@EnableRabbit` và khai báo hạ tầng

### 4.1. Dependency

Trong ứng dụng Maven Spring Framework không dùng Spring Boot, cần `spring-rabbit` và các module Spring tương thích. Ví dụ **phần dependency** với phiên bản Spring AMQP do BOM/dependency management dự án kiểm soát:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.amqp</groupId>
        <artifactId>spring-rabbit</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
</dependencies>
~~~

Nếu không có BOM/dependency management, bạn phải chọn **phiên bản tương thích** cho các thư viện trên; không sao chép ví dụ không ghi `<version>` vào một dự án Maven trống rồi mong Maven tự tìm phiên bản. Các API được trình bày theo dòng Spring AMQP hiện đại (ví dụ 3.x trên Java 17+) và không cần Spring Boot.

### 4.2. Khai báo `@Configuration` đầy đủ

File `PlainRabbitConfig.java`:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class PlainRabbitConfig {

    @Bean
    ConnectionFactory rabbitConnectionFactory() {
        CachingConnectionFactory factory =
                new CachingConnectionFactory("localhost");
        factory.setPort(5672);
        factory.setUsername("lab");
        factory.setPassword("lab123456");
        return factory;
    }

    @Bean
    RabbitAdmin rabbitAdmin(ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    @Bean
    RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        return new RabbitTemplate(connectionFactory);
    }

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(3);
        factory.setPrefetchCount(10);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }

    @Bean
    DirectExchange listenerExchange() {
        return new DirectExchange("demo.listener.events", true, false);
    }

    @Bean
    Queue listenerQueue() {
        return QueueBuilder.durable("demo.listener.orders").build();
    }

    @Bean
    Binding listenerBinding(Queue listenerQueue,
                            DirectExchange listenerExchange) {
        return BindingBuilder.bind(listenerQueue)
                .to(listenerExchange)
                .with("order.created");
    }

    @Bean
    PlainOrderListener plainOrderListener() {
        return new PlainOrderListener();
    }
}
~~~

**Giải thích các điểm quan trọng:**

1. `@EnableRabbit` kích hoạt xử lý `@RabbitListener` trong context. Đây là phần **Spring thuần cần bật rõ ràng** nếu không có một cấu hình khác đã thực hiện việc đó.
2. `rabbitConnectionFactory()` khai báo cách liên lạc với RabbitMQ; `CachingConnectionFactory` tái sử dụng connection/channel cho ứng dụng.
3. `rabbitListenerContainerFactory()` có **đúng tên mặc định** để listener không chỉ định `containerFactory` tìm thấy nó. Nếu đặt tên khác, cần chỉ rõ trên annotation hoặc dùng `RabbitListenerConfigurer`.
4. `RabbitAdmin` sử dụng ConnectionFactory để khai báo các bean exchange, queue, binding lên broker khi cơ chế auto-declare được kích hoạt và có kết nối.
5. `RabbitTemplate` dùng làm publisher; nó không phát sinh consumer.
6. `PlainOrderListener` được đăng ký qua `@Bean`, vì chỉ những **Spring beans** được hậu xử lý mới có annotation listener được phát hiện.

`setDefaultRequeueRejected(false)` là lựa chọn rõ ràng cho lab: khi listener báo lỗi theo đường reject thông thường, message **không bị tự động requeue mãi**. Trong môi trường thật, hãy phân biệt lỗi dữ liệu cố định với lỗi hạ tầng tạm thời và cấu hình retry/backoff/DLQ thích hợp; không sao chép thông số này mà không xem xét nghiệp vụ.

### 4.3. Tạo listener bean

File `PlainOrderListener.java`:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;

public class PlainOrderListener {

    @RabbitListener(
            id = "plainOrderListener",
            queues = "demo.listener.orders")
    public void receive(String orderId) {
        System.out.println("[Spring thuần] Nhận đơn: " + orderId);
    }
}
~~~

Listener này không cần `@Component` bởi `PlainRabbitConfig` đã tạo bean bằng `@Bean`. Nếu dùng cách quét component thay thế, hãy cấu hình `@ComponentScan` và gắn `@Component`; **không tạo hai bean listener vô tình cùng tiêu thụ queue**.

### 4.4. Khởi động context và publish message

File `PlainRabbitMain.java`:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class PlainRabbitMain {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PlainRabbitConfig.class)) {

            RabbitTemplate template =
                    context.getBean(RabbitTemplate.class);

            template.convertAndSend(
                    "demo.listener.events",
                    "order.created",
                    "ORD-1001");

            System.out.println("Đã gọi publish; Enter để kết thúc...");
            System.in.read(); // Giữ chương trình console chạy để listener nhận.
        }
    }
}
~~~

Sau khi context khởi tạo thành công và kết nối broker, bạn sẽ thấy log tương tự:

~~~text
Đã gọi publish; Enter để kết thúc...
[Spring thuần] Nhận đơn: ORD-1001
~~~

**Không nhầm:** `convertAndSend` kết thúc không đồng nghĩa broker đã xác nhận publication hoặc listener đã xử lý thành công. Khi cần theo dõi publication riêng, cấu hình publisher confirms/returns; khi cần xác nhận nghiệp vụ, lưu kết quả nghiệp vụ và xử lý consumer ack thích hợp.

### 4.5. Điều gì xảy ra nếu bỏ từng phần?

| Bỏ hoặc khai báo sai | Triệu chứng điển hình |
|---|---|
| Thiếu `@EnableRabbit` trong Spring thuần | Method có `@RabbitListener` nhưng không được hạ tầng listener đăng ký |
| Thiếu `ConnectionFactory` | Listener container không có cách lấy kết nối tới RabbitMQ |
| Thiếu bean mặc định `rabbitListenerContainerFactory` | Listener không chỉ định factory không tìm được factory để tạo container |
| Thiếu bean listener / quên `@ComponentScan` | Không có annotated Spring bean để scanner đăng ký |
| Thiếu queue trên broker và không có nguồn khai báo topology | Listener có thể không kết nối/consume được queue, báo lỗi khai báo/không tồn tại |
| Thiếu hoặc sai binding | Consumer chạy nhưng không nhận publication với routing key mong muốn |
| Thiếu `RabbitAdmin` trong lab chỉ khai báo topology bằng Spring | Các bean Queue/Exchange/Binding chưa chắc đã được đưa lên broker |

## 5. Spring Boot: auto-configuration tạo phần lớn hạ tầng

Trong ứng dụng **Spring Boot** thông thường, chỉ cần starter AMQP và cấu hình kết nối. Spring Boot auto-configure các thành phần quan trọng khi dependency có trên classpath và chưa bị thay thế bởi bean do ứng dụng tự định nghĩa.

### 5.1. Maven starter

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Đặt dependency trong dự án Spring Boot có parent/BOM đang quản lý phiên bản. Starter kéo các thư viện Spring AMQP, RabbitMQ client và hạ tầng thiết yếu; **không cần tự thêm Spring Framework thủ công** như phần Spring thuần.

### 5.2. `application.yml`

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      type: simple
      simple:
        concurrency: 1
        max-concurrency: 3
        prefetch: 10
        acknowledge-mode: auto
        default-requeue-rejected: false
~~~

Trong trường hợp mặc định, Boot cung cấp:

- Một `ConnectionFactory` (thường là `CachingConnectionFactory`), sử dụng thông tin `spring.rabbitmq.*`.
- Một `RabbitTemplate` và khả năng auto-declare tài nguyên AMQP qua `AmqpAdmin`/`RabbitAdmin` khi các điều kiện cấu hình phù hợp.
- Một listener container factory mặc định, thông thường tên `rabbitListenerContainerFactory`, được thiết lập bằng các thuộc tính `spring.rabbitmq.listener.*`.
- Hạ tầng nhận diện `@RabbitListener` ở ứng dụng Boot có auto-configuration AMQP phù hợp.

**Trong ứng dụng Boot thông thường dùng `spring-boot-starter-amqp`, bạn không bắt buộc phải tự thêm `@EnableRabbit` chỉ để `@RabbitListener` hoạt động.** Boot có cấu hình annotation-driven cho trường hợp này. Thêm `@EnableRabbit` một cách tường minh thường là lựa chọn hợp lệ khi muốn làm rõ chủ đích, nhưng **nó không thay cho starter, connection factory và container factory**. Khi tự loại trừ auto-configuration hoặc tự thay cấu hình hạ tầng, phải xác minh các bean còn tồn tại.

Các lớp và điều kiện auto-configuration thay đổi giữa các dòng Spring Boot. Điều đáng tin cậy nhất là kiểm tra **các bean thực tế**, dependency, cấu hình và logs của phiên bản dự án đang dùng, không suy rằng mọi ứng dụng có chữ "Boot" đều được bật AMQP.

### 5.3. Ứng dụng Boot hoàn chỉnh ở mức tối thiểu

File `BootRabbitApplication.java`:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootRabbitApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootRabbitApplication.class, args);
    }

    @Bean
    DirectExchange bootListenerExchange() {
        return new DirectExchange("demo.listener.events", true, false);
    }

    @Bean
    Queue bootListenerQueue() {
        return QueueBuilder.durable("demo.listener.orders").build();
    }

    @Bean
    Binding bootListenerBinding(Queue bootListenerQueue,
                                DirectExchange bootListenerExchange) {
        return BindingBuilder.bind(bootListenerQueue)
                .to(bootListenerExchange)
                .with("order.created");
    }

    @Bean
    CommandLineRunner demoPublisher(RabbitTemplate rabbitTemplate) {
        return args -> rabbitTemplate.convertAndSend(
                "demo.listener.events",
                "order.created",
                "ORD-BOOT-1001");
    }
}
~~~

File `BootOrderListener.java` (đặt trong package được `@SpringBootApplication` component-scan):

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BootOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(BootOrderListener.class);

    @RabbitListener(
            id = "bootOrderListener",
            queues = "demo.listener.orders")
    public void receive(String orderId) {
        log.info("[Spring Boot] Nhận đơn: {}", orderId);
    }
}
~~~

**Không có `@EnableRabbit` hoặc các bean `RabbitTemplate`, `ConnectionFactory` và `rabbitListenerContainerFactory` khai báo thủ công** trong ví dụ Boot tối thiểu này: chính đó là điểm cần quan sát. Tuy nhiên exchange, queue và binding vẫn được khai báo **rõ ràng** để broker biết định tuyến message đi đâu. Spring Boot không tự biến mọi tên queue trong annotation thành topology hoàn chỉnh.

Ở lần khởi động bình thường, `CommandLineRunner` phát một đơn minh họa, listener có thể nhận và ghi log. **Mỗi lần khởi động lại ứng dụng demo đều phát một event mới.** Để đánh giá nghiệp vụ thật, hãy sinh event ID riêng, publisher confirms, idempotency và trạng thái giao dịch phù hợp.

## 6. So sánh Spring thuần và Spring Boot

| Khía cạnh | Spring thuần | Spring Boot với starter AMQP |
|---|---|---|
| Kích hoạt `@RabbitListener` | Thường thêm `@EnableRabbit` | Thường được hạ tầng auto-configuration AMQP thiết lập |
| `ConnectionFactory` | Tự tạo bean và gán broker credentials | Boot tạo theo `spring.rabbitmq.*` nếu chưa có bean thay thế |
| `RabbitTemplate` | Tự tạo bean | Boot thường tạo sẵn |
| Listener factory mặc định | Tự tạo `rabbitListenerContainerFactory` hoặc dùng `RabbitListenerConfigurer` | Boot thường tạo sẵn và áp các thuộc tính listener |
| Cấu hình concurrency/prefetch/ack | Java setters trên container factory | `application.yml` hoặc customizer/factory của Boot |
| Exchange/queue/binding | Tự khai báo hoặc provision trên broker | **Vẫn phải** tự khai báo/provision; Boot có thể auto-declare các bean tương ứng |
| Converter tùy chỉnh | Gắn thủ công cho producer và listener | Có thể đăng ký `MessageConverter` bean và để Boot configurer áp dụng khi phù hợp |
| Kiểm soát sâu cơ chế | Rõ ràng, linh hoạt nhưng nhiều boilerplate | Ít code hơn; cần hiểu auto-configuration và điều kiện override |

**Chọn Spring thuần** khi ứng dụng không dùng Boot hoặc cần kiểm soát framework trực tiếp. **Chọn Spring Boot** khi dự án đã dùng Boot và muốn giảm boilerplate, cấu hình thống nhất theo môi trường. Không có lợi ích kỹ thuật chỉ vì một ứng dụng Boot viết lại toàn bộ bean cấu hình bằng tay nếu không có yêu cầu đặc biệt.

## 7. Khi nào cần tự định nghĩa listener container factory trong Boot?

Auto-configuration không ngăn bạn tùy biến sâu. Ví dụ một queue quan trọng cần `prefetch=5`, hai consumer và thiết lập riêng, trong khi các listener khác vẫn dùng cấu hình mặc định.

Với Spring Boot 3.x, có thể tận dụng **`SimpleRabbitListenerContainerFactoryConfigurer`** để kế thừa các thuộc tính Boot rồi ghi đè có chủ đích:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SpecializedListenerConfig {

    @Bean("importantOrdersFactory")
    SimpleRabbitListenerContainerFactory importantOrdersFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        // Kế thừa các thiết lập Boot: converter, lỗi, retry, prefetch...
        configurer.configure(factory, connectionFactory);

        // Các override riêng cho listener quan trọng:
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(5);
        return factory;
    }
}
~~~

Sử dụng ở listener:

~~~java
@RabbitListener(
        id = "importantOrders",
        queues = "demo.listener.orders",
        containerFactory = "importantOrdersFactory")
public void receiveImportant(String orderId) {
    // Xử lý theo hợp đồng nghiệp vụ.
}
~~~

**Đây là phương án thay thế listener trước đó**, không phải lời khuyên để thêm listener thứ hai cùng đọc queue `demo.listener.orders` trong cùng demo. Nếu cả hai listener đều chạy, chúng **cạnh tranh** các message; không có chuyện mọi đơn tự đi qua cả hai listener.

Phương thức `configurer.configure(...)` có ý nghĩa quan trọng: nếu bạn tự `new SimpleRabbitListenerContainerFactory()` rồi chỉ set connection factory, **các thuộc tính và converter Boot đã cấu hình có thể không được mang sang**. Tùy trường hợp, bạn có thể dùng customizer để điều chỉnh factory hiện hữu thay vì tạo factory mới.

### `containerFactory` và tên bean mặc định

| Cách khai báo listener | Factory được chọn |
|---|---|
| `@RabbitListener(queues = "demo.listener.orders")` | Factory mặc định, thường bean tên `rabbitListenerContainerFactory` |
| `@RabbitListener(queues = "...", containerFactory = "importantOrdersFactory")` | Bean `importantOrdersFactory` |
| Cấu hình qua `RabbitListenerConfigurer` | Có thể thay factory mặc định hoặc thiết lập endpoint registrar |

Khi listener không hoạt động, hãy kiểm tra **factory nào thực tế được chọn** trước khi chỉnh `spring.rabbitmq.listener.simple.*`. Đặc biệt, nếu chuyển `spring.rabbitmq.listener.type=direct`, Boot dùng một kiểu container factory và nhóm property riêng (`listener.direct.*`), không nên mong mọi tùy chỉnh `listener.simple.*` có cùng tác dụng.

## 8. Khai báo queue: `queues`, `queuesToDeclare` và `bindings`

Đây là khác biệt giữa **tham chiếu queue** và **khai báo topology**.

### 8.1. Chỉ tham chiếu queue hiện có

~~~java
@RabbitListener(queues = "demo.listener.orders")
public void receive(String orderId) {
    // Queue phải tồn tại ở broker hoặc được khai báo bằng cơ chế khác.
}
~~~

`queues` không tự khai báo `demo.listener.orders`.

### 8.2. Muốn listener khai báo queue đơn giản

Spring AMQP cho phép sử dụng `queuesToDeclare`:

~~~java
@RabbitListener(
        queuesToDeclare = @org.springframework.amqp.rabbit.annotation.Queue(
                value = "demo.listener.simple", durable = "true"))
public void onSimple(String text) {
    // Ví dụ minh họa queue do annotation khai báo.
}
~~~

`queuesToDeclare` hỗ trợ khai báo queue; với exchange mặc định của RabbitMQ, queue thường có binding mặc định dùng tên queue làm routing key. Nếu nghiệp vụ cần **direct/topic exchange riêng**, khai báo binding tương ứng bằng Java `@Bean` hoặc thuộc tính `bindings`, không suy rằng tạo queue có nghĩa là nó tự bind vào mọi exchange.

### 8.3. Khai báo exchange + queue + binding từ annotation

~~~java
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(bindings = @QueueBinding(
        value = @Queue(value = "demo.listener.annotated", durable = "true"),
        exchange = @Exchange(
                value = "demo.listener.annotated.events",
                type = "direct",
                durable = "true"),
        key = "order.created"))
public void onAnnotated(String orderId) {
    // Endpoint đi kèm topology do annotation mô tả.
}
~~~

**Đừng trộn ba ví dụ trên trong cùng một demo nếu không chủ đích tạo thêm queue.** Chúng thể hiện các cách khai báo khác nhau. Nếu queue đã có cấu hình arguments/durability khác, việc redeclare không tương thích sẽ khiến RabbitMQ báo lỗi (chẳng hạn `PRECONDITION_FAILED inequivalent arg`); không xóa queue production để “sửa” lỗi mà không lập kế hoạch migration.

## 9. Acknowledgment: Spring `AUTO` khác RabbitMQ auto-ack

Một listener hoạt động chưa đủ; cần quyết định **khi nào broker được ACK**.

| Chế độ Spring AMQP | Ý nghĩa thực tế | Khi nào dùng? |
|---|---|---|
| `AcknowledgeMode.AUTO` | Container ACK sau khi listener chạy thành công, xử lý exception theo cấu hình | Lựa chọn thường dùng cho consumer nghiệp vụ |
| `AcknowledgeMode.MANUAL` | Ứng dụng tự gọi `basicAck/basicNack/basicReject` trên channel | Khi cần kiểm soát chính xác thời điểm và quyết định ACK |
| `AcknowledgeMode.NONE` | RabbitMQ `autoAck`: broker coi là ACK khi giao, không đợi kết quả listener | Chỉ khi chấp nhận rủi ro mất message nếu consumer lỗi |

**Spring `AUTO` không phải RabbitMQ `autoAck=true`.** Với `AUTO`, nếu listener ném exception, container không coi message thành công và sẽ áp quy tắc retry/requeue/reject. Với `NONE`, broker không giữ delivery chờ ACK nên message có thể mất nếu consumer chết trong lúc xử lý.

### Ví dụ listener manual ACK

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.rabbitmq.client.Channel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderListener {
    private static final Logger log =
            LoggerFactory.getLogger(ManualOrderListener.class);

    @RabbitListener(
            queues = "demo.listener.manual",
            ackMode = "MANUAL")
    public void receive(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties().getDeliveryTag();
        String orderId = new String(
                message.getBody(), StandardCharsets.UTF_8);

        if (orderId.isBlank()) {
            // Không requeue message sai dữ liệu.
            channel.basicReject(tag, false);
            return;
        }

        // Trong production: gọi xử lý idempotent và commit phù hợp.
        log.info("Đã xử lý orderId={}", orderId);
        channel.basicAck(tag, false);
    }
}
~~~

Để chạy ví dụ độc lập này, **cần khai báo queue `demo.listener.manual` trên broker** hoặc đổi `queues` sang queue lab bạn đã tạo, đồng thời **không chạy listener `AUTO` khác đang cùng tiêu thụ queue nếu muốn đối chiếu riêng MANUAL**.

**Cực kỳ quan trọng:** `deliveryTag` chỉ có ý nghĩa trên **channel giao message đó**. ACK sai channel hoặc ACK hai lần có thể làm RabbitMQ đóng channel với lỗi `unknown delivery tag`. Khi dùng `MANUAL`, phải định nghĩa đầy đủ đường ACK/NACK cho cả thành công, lỗi dữ liệu và lỗi tạm thời; đoạn code chỉ minh họa nhánh hợp lệ và nhánh reject dữ liệu rỗng.

### Retry và DLQ có ảnh hưởng gì?

Nếu listener ném lỗi hoặc NACK:

- `requeue=true` có thể khiến message được giao lại, cờ `redelivered` có thể là `true`; requeue vô hạn có thể tạo vòng lặp nóng.
- `requeue=false`, với queue có DLX/binding phù hợp, có thể dead-letter sang DLQ; nếu không có đường DLX thích hợp, message có thể bị loại.
- Khi ứng dụng sử dụng retry interceptor/backoff, cần giới hạn số lần và phân loại lỗi trước khi trả quyết định cuối.

**Publisher confirms** của `RabbitTemplate` chỉ xác nhận publication ở phía producer; **consumer ACK** của listener là một xác nhận khác. Đừng đánh đồng broker ACK publisher với việc đơn hàng đã được database xử lý, và đừng mong `@EnableRabbit` tự kích hoạt publisher confirms.

## 10. Converter và kiểu tham số listener

Một listener nhận `String` có thể hoạt động ngay với converter mặc định. Khi producer gửi JSON object và listener nhận record/DTO, cần đảm bảo converter và hợp đồng message phù hợp.

Ví dụ với **Spring Boot 3.x / Spring AMQP 3.x / Jackson 2**:

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ListenerJsonConfig {

    @Bean
    MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
~~~

Khi Boot tự tạo `RabbitTemplate` và listener factory bằng configurer, nó có thể áp dụng bean converter tương ứng. **Nếu tự tạo factory hoặc template bằng tay**, phải đảm bảo converter được đặt ở đúng chỗ; một bean converter nằm trong context **không đủ** nếu bean tùy chỉnh bỏ qua nó.

Với **Spring thuần**, ví dụ:

~~~java
Jackson2JsonMessageConverter json =
        new Jackson2JsonMessageConverter();

rabbitTemplate.setMessageConverter(json);
listenerContainerFactory.setMessageConverter(json);
~~~

Đoạn trên là minh họa các setter trên **đúng đối tượng đã được cấu hình thành bean** (không phải file Java chạy độc lập). Nếu chuyển sang dòng framework dùng Jackson 3, chọn JSON converter và mapper API phù hợp phiên bản, không trộn import giữa hai dòng.

**Liên hệ với hạ tầng listener:** `@EnableRabbit` chỉ giúp nhận diện `@RabbitListener`, còn việc chuyển byte sang `String`, record hay DTO là trách nhiệm của **message converter**. Nếu listener không nhận đúng dữ liệu, kiểm tra `content_type`, converter, Java type và JSON contract trước khi thay đổi concurrency.

## 11. Quan sát listener hoạt động

### 11.1. Kiểm tra RabbitMQ Management

Mở `http://localhost:15672`, chọn **Queues and Streams** (hoặc **Queues** tùy phiên bản), sau đó kiểm tra queue `demo.listener.orders`:

| Chỉ số | Diễn giải | Gợi ý chẩn đoán |
|---|---|---|
| `Consumers` | Số consumer đang đăng ký trên queue | 0 có thể do listener chưa chạy, sai queue/vhost hoặc lỗi kết nối |
| `Ready` | Message đang chờ được giao | Tăng liên tục khi consumer không theo kịp |
| `Unacked` | Message đã giao nhưng chưa được ACK | Tăng kéo dài khi listener chậm, quên ACK hoặc prefetch lớn |
| Publish/deliver/ack rate | Tốc độ message được xuất bản, giao và xác nhận | Chỉ là số liệu vận hành, không chứng minh transaction nghiệp vụ thành công |
| Connections / Channels | Connection AMQP và channel đang mở | Giúp chẩn đoán reconnect, channel lỗi và việc tăng concurrency |

Với listener xử lý quá nhanh, snapshot `Ready=0, Unacked=0` có thể chỉ phản ánh rằng message đã được nhận/ACK trước khi UI cập nhật. Dùng log có `eventId`/`orderId`, listener ID, consumer tag và timestamp để xác định chính xác luồng.

### 11.2. Kiểm tra listener registry theo `id`

Hạ tầng annotation-driven tạo container trong `RabbitListenerEndpointRegistry`. Trong một bean đang được Spring quản lý, có thể kiểm tra:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ListenerRegistryInspector {

    public ListenerRegistryInspector(RabbitListenerEndpointRegistry registry) {
        // Nên gọi việc tra cứu sau khi context đã khởi động.
        this.registry = registry;
    }

    private final RabbitListenerEndpointRegistry registry;

    public boolean ordersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("bootOrderListener");
        return container != null && container.isRunning();
    }
}
~~~

Các container sinh bởi `@RabbitListener` thường được quản lý thông qua registry thay vì luôn xuất hiện như các bean container độc lập. `id` của listener giúp tra cứu chính xác container; nó **không phải** message ID, delivery tag hoặc consumer tag do broker dùng.

Khi muốn start/stop listener trong vận hành, registry cung cấp API quản lý vòng đời; cần thận trọng với in-flight messages và cơ chế shutdown/ack. Đừng dùng start/stop tùy tiện như cách xử lý lỗi định tuyến hoặc lỗi dữ liệu.

### 11.3. Metrics và cảnh báo

Trong môi trường production, có thể kết hợp Spring Boot Actuator/Micrometer (khi được bật và cấu hình phù hợp), log ứng dụng và RabbitMQ Management. Những chỉ số có ích:

- Số consumer thực tế, queue depth, unacked, tốc độ deliver/ack.
- Thời gian xử lý listener, tỉ lệ exception, retry, số message dead-letter.
- Connection/channel churn, authentication failures, startup/recovery errors.
- Độ trễ từ event creation đến lúc xử lý nghiệp vụ, dùng `eventId` hoặc correlation/trace ID.

`@EnableRabbit` không tự tạo dashboard hay bảo đảm mọi metrics được bật sẵn; cần kiểm tra phiên bản, dependencies, cấu hình và hệ thống quan sát thực tế.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Có `@RabbitListener` nhưng không có consumer trong Spring thuần | Thiếu `@EnableRabbit`, bean listener chưa được đăng ký | Thêm `@EnableRabbit`; dùng `@Bean` hoặc `@ComponentScan` đúng |
| Spring Boot có starter nhưng không tạo listener | Auto-configuration bị exclude/override; class ngoài package scan | Kiểm tra dependency, bean factory/registry, package của `@SpringBootApplication` |
| Lỗi thiếu `rabbitListenerContainerFactory` | Factory mặc định không tồn tại hoặc đặt tên khác | Tạo bean tên mặc định; hoặc chỉ định `containerFactory` |
| Connection refused hoặc authentication failure | Broker không chạy, host/port/sai user/vhost/TLS | Kiểm tra broker và cấu hình `spring.rabbitmq.*` |
| Listener liên tục báo queue not found | Queue chưa có hoặc đúng tên nhưng ở vhost khác | Khai báo queue/binding hợp lệ hoặc sửa tên/vhost |
| `PRECONDITION_FAILED inequivalent arg` | Queue/exchange đã có arguments, durability hoặc type khác | Đồng bộ cấu hình, migration có kế hoạch; không xóa dữ liệu tùy tiện |
| Consumer đếm được nhưng không nhận event | Sai exchange/routing key/binding hoặc consumer khác đang lấy | Xem bindings, Ready/Unacked, competing consumers |
| Listener xử lý một phần rồi message được nhận lại | Lỗi trước consumer ACK hoặc mất channel/connection | Thiết kế idempotency, transaction nghiệp vụ, retry hợp lý |
| Message liên tục redelivered | Requeue nóng hoặc exception liên tiếp | Retry có giới hạn, backoff, DLQ; sửa lỗi gốc |
| Hệ thống báo `unknown delivery tag` | Manual ACK sai channel/tag, ACK hai lần | Kiểm tra `MANUAL` vs `AUTO`, không dùng tag từ channel khác |
| DTO JSON không parse được | Factory dùng converter mặc định, content type/type mismatch | Cấu hình JSON converter trên đúng factory; kiểm tra schema |
| Thay property Boot nhưng listener không đổi | Listener dùng custom factory không gọi configurer hoặc dùng `direct` thay `simple` | Xác định factory thực tế và nhóm property tương ứng |
| Tăng concurrency nhưng throughput không tăng | Broker/DB chậm, prefetch không phù hợp, lock hoặc backpressure | Đo latency, DB pool, queue rates và số consumer thực tế |

**Gợi ý kiểm tra theo thứ tự:** xác nhận broker kết nối được → kiểm tra exchange/queue/binding → xác nhận listener bean có được Spring quản lý → xác nhận hạ tầng annotation-driven và container factory → xem Consumers/Ready/Unacked → kiểm tra ack/retry và lỗi converter. Cách này giúp tránh sửa concurrency khi vấn đề thật sự chỉ là sai tên queue.

## 13. Bài tập thực hành

### Bài A — Bật/tắt `@EnableRabbit` trong Spring thuần

Chạy `PlainRabbitMain` và ghi log listener. Trong một bản lab tách biệt, bỏ `@EnableRabbit` khỏi `PlainRabbitConfig` và quan sát hạ tầng listener có đăng ký consumer hay không. Sau đó khôi phục annotation và giải thích vai trò của nó. **Không dùng ứng dụng production để thử**.

### Bài B — Spring Boot không viết `@EnableRabbit`

Chạy `BootRabbitApplication` với starter và `application.yml` như bài. Xem `Consumers` trên `demo.listener.orders` và log `BootOrderListener`. Bổ sung `@EnableRabbit` vào Boot app để kiểm tra vì sao annotation đó không thay thế factory, connection và topology.

### Bài C — Factory riêng và khả năng kế thừa cấu hình Boot

Tạo `importantOrdersFactory` bằng `SimpleRabbitListenerContainerFactoryConfigurer`, gán cho listener đang có thay vì chạy thêm listener cùng queue. Điều chỉnh `prefetch` và concurrency; xem số consumer thực tế trong Management. So sánh với cấu hình property chung.

### Bài D — AUTO, MANUAL và lỗi nghiệp vụ

Tạo queue lab riêng cho `ManualOrderListener`. Gửi message hợp lệ, rỗng và message gây lỗi tạm thời. Dự đoán khi nào `Ready`, `Unacked` và DLQ thay đổi. Tự thiết kế chính sách retry/backoff và giới hạn requeue; không dùng NACK requeue vô hạn.

### Bài E — Sai routing key

Publish một event vào `demo.listener.events` nhưng dùng key `order.unknown`. Kiểm tra exchange bindings và kết quả queue. Nếu yêu cầu producer biết rằng message không vào queue nào, cần thêm **publisher returns/mandatory** và publisher confirms; listener config không tự giải quyết lỗi này.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Trong Spring thuần, `@EnableRabbit` có tự tạo một connection tới RabbitMQ và queue tên `orders` không?

**Đáp án:** Không. Nó kích hoạt hạ tầng xử lý `@RabbitListener`; ConnectionFactory, container factory, broker và topology cần được cung cấp riêng.

**Câu 2.** Spring Boot có `spring-boot-starter-amqp`, `@RabbitListener` và `application.yml`. Có nhất thiết tự tạo `SimpleRabbitListenerContainerFactory` không?

**Đáp án:** Không trong trường hợp auto-configuration thông thường. Boot thường tạo factory mặc định và áp cấu hình `spring.rabbitmq.listener.*`.

**Câu 3.** Trong Spring thuần, listener không ghi `containerFactory` sẽ tìm factory tên nào theo quy ước mặc định?

**Đáp án:** `rabbitListenerContainerFactory`, trừ khi ứng dụng đã cấu hình cơ chế chọn factory mặc định khác.

**Câu 4.** Tại sao listener có `queues = "orders"` nhưng vẫn lỗi queue not found?

**Đáp án:** `queues` tham chiếu queue cần tiêu thụ, không tự khai báo queue. Phải tạo queue đúng broker/vhost, có binding phù hợp để nhận publication.

**Câu 5.** Spring `AcknowledgeMode.AUTO` có tương đương với `autoAck=true` ở RabbitMQ client không?

**Đáp án:** Không. Spring `AUTO` thường ACK sau listener thành công; `NONE` mới tương ứng với broker không đợi consumer ACK.

**Câu 6.** Vì sao không nên tạo custom factory Boot chỉ với `new SimpleRabbitListenerContainerFactory()` và `setConnectionFactory(...)`?

**Đáp án:** Bạn có thể bỏ sót converter, prefetch, lỗi/retry và các tùy chỉnh Boot. Nếu muốn kế thừa cấu hình Boot, dùng `SimpleRabbitListenerContainerFactoryConfigurer` rồi override thuộc tính cần thiết.

**Câu 7.** Có hai listener đều tiêu thụ `demo.listener.orders`. Mỗi event có chắc chắn được cả hai nhận không?

**Đáp án:** Không. Hai listener là **competing consumers** trên cùng một queue. Muốn mỗi nhóm xử lý nhận một bản sao sự kiện, tạo các queue riêng với binding phù hợp.

## 15. Ghi nhớ

- **Spring thuần:** dùng `@EnableRabbit` để kích hoạt `@RabbitListener`, đồng thời tự cấu hình `ConnectionFactory`, `RabbitListenerContainerFactory`, `RabbitTemplate`, `RabbitAdmin` và topology khi cần.
- **Spring Boot:** `spring-boot-starter-amqp` thường cung cấp hạ tầng annotation-driven, connection factory, template và listener factory qua auto-configuration; `@EnableRabbit` thủ công thường không bắt buộc trong cấu hình tiêu chuẩn.
- **Tùy biến có chủ đích:** xác định factory mà listener dùng; trong Boot, cân nhắc `SimpleRabbitListenerContainerFactoryConfigurer` để kế thừa properties thay vì tạo factory thiếu cấu hình.
- **Listener chạy không đồng nghĩa giao nhận đáng tin cậy:** vẫn cần exchange/queue/binding đúng, consumer ACK, publisher confirms/returns, retry có giới hạn, dead-letter, idempotency, transaction/outbox và quan sát hệ thống.
