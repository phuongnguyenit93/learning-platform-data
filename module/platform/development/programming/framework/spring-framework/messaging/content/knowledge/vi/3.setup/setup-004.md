# Phân biệt cấu hình Framework thủ công và tự cấu hình của Spring Boot

Khi xây dựng ứng dụng Spring, ta cần tạo các object, kết nối dependency và cấu hình hạ tầng để các thành phần làm việc với nhau. Spring Framework cung cấp IoC container và cơ chế cấu hình để lập trình viên khai báo những thành phần đó. Spring Boot xây dựng trên Spring Framework, bổ sung cơ chế auto-configuration để tự thiết lập nhiều thành phần phổ biến dựa trên thư viện có trong classpath, các bean hiện có và cấu hình bên ngoài.

Điểm khác biệt chính nằm ở mức độ cấu hình mà ứng dụng phải khai báo. Với cấu hình thủ công, lập trình viên chủ động tạo và kết nối các bean. Với Spring Boot, framework tự cung cấp các cấu hình mặc định khi những điều kiện cần thiết được đáp ứng; ứng dụng chỉ bổ sung các bean hoặc thuộc tính riêng của nghiệp vụ. Hai cách có thể cùng tồn tại trong một ứng dụng.

## 1. Spring Framework và Spring Boot có vai trò gì?

### Spring Framework

Spring Framework cung cấp nền tảng cho ứng dụng Java, trong đó có:

- **IoC container:** tạo, quản lý vòng đời và kết nối các object (bean).
- **Dependency Injection:** cung cấp dependency cho một bean thông qua constructor, setter hoặc field.
- **Java configuration:** dùng **@Configuration** và **@Bean** để khai báo bean.
- **Component scanning:** tìm các class được đánh dấu như **@Component**, **@Service**, **@Repository** và **@Controller**.
- **Các module tích hợp:** hỗ trợ web, dữ liệu, giao dịch, messaging và nhiều chức năng khác.

Spring Framework không tự suy đoán toàn bộ hạ tầng mà ứng dụng cần. Trong ứng dụng dùng Framework thuần, lập trình viên phải chọn và đăng ký các thành phần cần thiết, chẳng hạn connection factory, template, channel, adapter hoặc message listener.

### Spring Boot

Spring Boot sử dụng Spring Framework và bổ sung các tiện ích để khởi tạo ứng dụng nhanh hơn:

- **Auto-configuration:** tự khai báo những bean phổ biến khi điều kiện phù hợp.
- **Starter dependencies:** nhóm các thư viện thường dùng để dễ khai báo dependency.
- **Externalized configuration:** đọc cấu hình từ application.properties, application.yaml, biến môi trường, tham số dòng lệnh và các nguồn được hỗ trợ.
- **Embedded server và ứng dụng chạy độc lập:** với ứng dụng web, có thể đóng gói và chạy bằng một lệnh.
- **Cơ chế quan sát và chẩn đoán:** hỗ trợ xem tình trạng ứng dụng và lý do một cấu hình được hoặc không được áp dụng.

Spring Boot không thay thế IoC container, bean hay Dependency Injection của Spring Framework. Auto-configuration cũng được triển khai bằng chính cơ chế cấu hình và điều kiện của Spring.

## 2. Cấu hình Framework thủ công hoạt động như thế nào?

Với cấu hình thủ công, lập trình viên xác định rõ những bean nào cần có và cách chúng phụ thuộc vào nhau. Có thể dùng XML hoặc Java configuration. Trong các ứng dụng Spring hiện đại, Java configuration thường được thể hiện bằng **@Configuration** và **@Bean**.

Ví dụ, một cấu hình Java có thể khai báo service và dependency của nó:

~~~java
@Configuration
public class ApplicationConfig {

    @Bean
    public OrderRepository orderRepository() {
        return new JdbcOrderRepository();
    }

    @Bean
    public OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Spring gọi các phương thức **@Bean**, đăng ký kết quả trong ApplicationContext và tự inject bean **OrderRepository** vào **OrderService**. Lập trình viên quyết định implementation được dùng, cách tạo object và những dependency cần thiết.

Ứng dụng có thể khởi tạo context từ cấu hình đó:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(ApplicationConfig.class)) {
    OrderService service = context.getBean(OrderService.class);
    service.processPendingOrders();
}
~~~

Đây là ví dụ khởi tạo một Spring Framework context bằng Java configuration. Để chạy, project phải có Spring Context và các class nghiệp vụ tương ứng. Ví dụ không phải một ứng dụng Spring Boot hoàn chỉnh.

Cấu hình thủ công hữu ích khi:

- Muốn kiểm soát rõ cách tạo và cấu hình từng bean.
- Ứng dụng có hạ tầng đặc thù hoặc yêu cầu tích hợp riêng.
- Cần thay thế implementation mặc định bằng implementation của tổ chức.
- Đang xây dựng thư viện hoặc module cần hành vi cấu hình tường minh.
- Muốn giảm sự phụ thuộc vào quy ước hoặc auto-configuration của một phiên bản Spring Boot.

Đổi lại, lập trình viên phải tự chịu trách nhiệm về nhiều chi tiết hơn: dependency, bean, connection, timeout, converter, listener, retry và vòng đời tài nguyên.

## 3. Spring Boot auto-configuration hoạt động như thế nào?

Auto-configuration là cơ chế Spring Boot đăng ký các bean mặc định khi những điều kiện được định nghĩa trong thư viện cấu hình được thỏa mãn. Một cấu hình tự động thường xét các yếu tố sau:

- **Class có trên classpath hay không:** ứng dụng có thêm thư viện cần thiết không.
- **Bean đã tồn tại hay chưa:** ứng dụng đã tự khai báo bean tương đương chưa.
- **Property có bật tính năng hay không:** cấu hình bên ngoài có cho phép chức năng đó không.
- **Các dependency khác đã sẵn sàng chưa:** một cấu hình có thể chỉ hoạt động khi bean hoặc module liên quan đã tồn tại.

Một số annotation điều kiện thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| **@ConditionalOnClass** | Chỉ áp dụng cấu hình khi class được chỉ định có trên classpath |
| **@ConditionalOnMissingBean** | Chỉ tạo bean mặc định khi chưa có bean phù hợp |
| **@ConditionalOnBean** | Chỉ áp dụng khi một bean cần thiết đã tồn tại |
| **@ConditionalOnProperty** | Chỉ áp dụng khi property có giá trị hoặc trạng thái phù hợp |

Ví dụ minh họa một cấu hình tự động:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(ReportClient.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public ReportClient reportClient() {
        return new DefaultReportClient();
    }
}
~~~

Đây là ví dụ minh họa cách viết auto-configuration, không phải cấu hình có sẵn của Spring Boot. Nếu **ReportClient** có trên classpath và ứng dụng chưa cung cấp bean **ReportClient**, cấu hình này tạo một implementation mặc định. Nếu ứng dụng đã tự khai báo bean tương ứng, điều kiện **@ConditionalOnMissingBean** không còn đúng và bean mặc định sẽ không được tạo.

Trong ứng dụng, **@SpringBootApplication** thường được đặt trên class khởi động:

~~~java
@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

**@SpringBootApplication** kết hợp ba vai trò chính:

- **@SpringBootConfiguration:** đánh dấu class cấu hình chính của ứng dụng.
- **@EnableAutoConfiguration:** bật cơ chế auto-configuration.
- **@ComponentScan:** quét các component trong package của class khởi động và các package con.

Component scanning và auto-configuration là hai cơ chế khác nhau. Component scanning tìm các component do ứng dụng khai báo. Auto-configuration áp dụng những cấu hình thư viện đã được Spring Boot đăng ký khi các điều kiện tương ứng đúng.

## 4. So sánh qua ví dụ messaging với RabbitMQ

Module **spring-messaging** định nghĩa các abstraction chung như **Message**, **MessageHeaders**, **MessageChannel**, **MessageHandler** và **MessageBuilder**. Những abstraction này mô tả cấu trúc và cách trao đổi message trong ứng dụng. Chúng không tự tạo kết nối tới RabbitMQ, Kafka hay một message broker khác.

Muốn giao tiếp với RabbitMQ, ứng dụng cần thư viện tích hợp như Spring AMQP. Ví dụ dưới đây sử dụng RabbitMQ để thấy rõ phần nào do lập trình viên cấu hình và phần nào Spring Boot có thể tự cấu hình.

### 4.1. Cấu hình thủ công với Spring Framework

Trong ứng dụng không dùng Spring Boot auto-configuration, ta có thể tự khai báo connection factory, template, admin và topology của broker.

Ví dụ cấu hình Java với Spring AMQP:

~~~java
@Configuration
public class RabbitManualConfiguration {

    @Bean
    public CachingConnectionFactory connectionFactory() {
        CachingConnectionFactory factory =
                new CachingConnectionFactory("localhost");
        factory.setUsername("guest");
        factory.setPassword("guest");
        return factory;
    }

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        return new RabbitTemplate(connectionFactory);
    }

    @Bean
    public RabbitAdmin rabbitAdmin(
            ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue("orders.created", true);
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Các bean trong ví dụ có trách nhiệm cụ thể:

- **CachingConnectionFactory** quản lý kết nối tới RabbitMQ.
- **RabbitTemplate** cung cấp API gửi và nhận message theo kiểu request/reply hoặc gửi message thông thường.
- **RabbitAdmin** hỗ trợ khai báo queue, exchange và binding lên broker.
- **Queue**, **DirectExchange** và **Binding** mô tả topology mà ứng dụng cần.

Ví dụ dùng thông tin guest/guest cho RabbitMQ local phục vụ học tập. Môi trường thực tế nên lấy thông tin đăng nhập từ biến môi trường hoặc secret store và cấu hình bảo mật phù hợp.

Để sử dụng đoạn cấu hình này, project cần các dependency Spring Context và Spring AMQP/RabbitMQ tương ứng. Đây là cấu hình Spring Java minh họa, không phải chương trình độc lập có thể biên dịch chỉ bằng JDK.

### 4.2. Dùng Spring Boot auto-configuration

Với Spring Boot, ta thêm dependency **spring-boot-starter-amqp**. Starter đưa các thư viện tích hợp RabbitMQ cần thiết vào classpath. Spring Boot có thể tự cấu hình các bean hạ tầng phổ biến như connection factory, RabbitTemplate và AmqpAdmin khi các điều kiện tương ứng được đáp ứng.

Khai báo cấu hình kết nối trong **application.yaml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Class khởi động có thể khai báo topology nghiệp vụ:

~~~java
@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue("orders.created", true);
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Ta vẫn khai báo queue, exchange và binding vì đây là topology cụ thể của nghiệp vụ. Spring Boot hỗ trợ phần hạ tầng kết nối phổ biến dựa trên dependency và property đã cung cấp.

Một service có thể gửi message bằng **RabbitTemplate** được inject:

~~~java
@Service
public class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderCreated() {
        rabbitTemplate.convertAndSend(
                "orders",
                "order.created",
                "{"orderId":"ORD-42"}"
        );
    }
}
~~~

Consumer có thể nhận message từ queue:

~~~java
@Component
public class OrderListener {

    @RabbitListener(queues = "orders.created")
    public void handle(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Để các ví dụ gửi và nhận hoạt động, cần có RabbitMQ đang chạy và các dependency Spring Boot/Spring AMQP tương thích. Payload dạng chuỗi được dùng ở đây để tránh phải cấu hình thêm JSON message converter. Trong ứng dụng thực tế, nên xác định rõ schema, converter và phiên bản payload khi trao đổi object nghiệp vụ.

### 4.3. Phần nào được tự động và phần nào vẫn phải cấu hình?

| Thành phần | Spring Framework cấu hình thủ công | Spring Boot với auto-configuration |
|---|---|---|
| Dependency RabbitMQ | Tự thêm các thư viện cần thiết | Có thể dùng starter để nhóm dependency |
| ConnectionFactory | Tự khai báo và cấu hình bean | Tự cấu hình theo classpath và property |
| RabbitTemplate | Tự khai báo bean và kết nối | Tự cung cấp mặc định khi đủ điều kiện |
| RabbitAdmin | Tự khai báo nếu cần | Có thể được auto-configure khi phù hợp |
| Queue/exchange/binding | Tự khai báo theo nghiệp vụ | Vẫn thường do ứng dụng khai báo |
| Host, port, credential | Tự lấy và gán vào bean | Có thể khai báo bằng spring.rabbitmq.* |
| Message payload và schema | Ứng dụng tự thiết kế | Ứng dụng vẫn tự thiết kế |
| Logic xử lý message | Tự viết handler/listener | Ứng dụng vẫn tự viết handler/listener |

Bảng này mô tả cách triển khai phổ biến. Bean cụ thể có được tạo hay không còn phụ thuộc phiên bản Spring Boot, dependency, property và các bean mà ứng dụng đã cung cấp.

## 5. Cơ chế thay thế cấu hình mặc định (back-off)

Một nguyên tắc quan trọng của Spring Boot là auto-configuration thường cho phép ứng dụng thay thế bean mặc định. Khi ứng dụng cung cấp bean riêng, một số cấu hình tự động có thể dừng tạo bean mặc định tương ứng.

Ví dụ, nếu ứng dụng tự khai báo **RabbitTemplate**, auto-configuration có điều kiện thiếu bean tương ứng có thể không tạo **RabbitTemplate** mặc định nữa. Các bean tự động khác như connection factory vẫn có thể được giữ lại nếu điều kiện của chúng còn đúng.

Điều này được gọi là **back-off**. Không nên hiểu rằng chỉ cần tạo một bean tùy chỉnh là toàn bộ auto-configuration bị tắt. Mỗi cấu hình và mỗi bean có điều kiện riêng.

Ví dụ thay thế template mặc định:

~~~java
@Configuration
public class CustomRabbitConfiguration {

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template =
                new RabbitTemplate(connectionFactory);
        template.setMandatory(true);
        return template;
    }
}
~~~

Ứng dụng có thể tùy chỉnh template theo yêu cầu như message converter, confirm/callback hoặc routing behavior. Cần hiểu rõ bean mặc định nào sẽ được thay thế và bean nào vẫn được Boot cung cấp.

Nếu muốn loại bỏ hẳn một auto-configuration cụ thể, có thể dùng thuộc tính **spring.autoconfigure.exclude** hoặc thuộc tính **exclude** trên **@SpringBootApplication**. Chỉ nên làm vậy khi đã xác định đúng auto-configuration cần loại bỏ và có kế hoạch tự cung cấp các thành phần thay thế.

## 6. Cấu hình property và thứ tự ưu tiên

Spring Boot cho phép đưa cấu hình ra ngoài mã nguồn. Với RabbitMQ, ta có thể đặt host, port, username và password trong **application.yaml** hoặc **application.properties**.

Trong môi trường triển khai, thông tin nhạy cảm nên được truyền qua biến môi trường hoặc secret store. Ví dụ YAML dùng giá trị mặc định cho môi trường local:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Các nguồn cấu hình bên ngoài của Spring Boot có thứ tự ưu tiên. Ví dụ, biến môi trường hoặc tham số dòng lệnh có thể ghi đè giá trị trong file cấu hình theo quy tắc property source của Boot. Vì vậy, cùng một file application.yaml có thể dùng cho nhiều môi trường mà không phải sửa mã nguồn.

Cần phân biệt property của Boot với bean cấu hình thủ công. Property chỉ có tác dụng khi cấu hình tương ứng đọc property đó. Nếu ta tự tạo connection factory và không gắn nó với các property cần thiết, việc đổi **spring.rabbitmq.host** có thể không làm bean thủ công thay đổi theo.

## 7. Khi nào nên chọn cách nào?

Cấu hình thủ công phù hợp khi:

- Ứng dụng cần kiểm soát chính xác từng bean và vòng đời của nó.
- Cần cấu hình nhiều broker, nhiều connection factory hoặc topology phức tạp.
- Có yêu cầu bảo mật, kết nối hoặc routing đặc biệt.
- Đang tích hợp trong ứng dụng Spring Framework không sử dụng Boot.
- Muốn cấu hình tối thiểu, chỉ đưa vào những thành phần thực sự cần thiết.

Spring Boot auto-configuration phù hợp khi:

- Bắt đầu một ứng dụng Spring Boot mới.
- Dùng các tích hợp phổ biến như RabbitMQ, Kafka, JMS hoặc web.
- Muốn giảm boilerplate và sử dụng các mặc định đã được kiểm thử của hệ sinh thái.
- Cần cấu hình khác nhau giữa môi trường phát triển, kiểm thử và triển khai.
- Muốn thêm tính năng bằng dependency và property, sau đó chỉ tùy chỉnh phần nghiệp vụ cần thiết.

Trong nhiều ứng dụng, cách hợp lý là kết hợp cả hai: để Boot tạo hạ tầng mặc định, còn ứng dụng tự khai báo queue, exchange, listener, converter hoặc bean nghiệp vụ đặc thù.

## 8. Cách kiểm tra vì sao auto-configuration được áp dụng hoặc bị bỏ qua

Khi một bean mong đợi không xuất hiện, hãy kiểm tra theo thứ tự:

1. Dependency hoặc starter có thực sự nằm trong classpath không?
2. Property có đúng tên, đúng profile và đúng giá trị không?
3. Có bean tùy chỉnh nào khiến điều kiện **@ConditionalOnMissingBean** không còn thỏa mãn không?
4. Cấu hình có bị loại trừ bằng **exclude** hoặc **spring.autoconfigure.exclude** không?
5. Package chứa class ứng dụng có bao phủ các component cần scan không?
6. Broker có đang chạy và thông tin kết nối có đúng không?

Có thể khởi chạy ứng dụng với tùy chọn **--debug** để xem Condition Evaluation Report. Báo cáo này cho biết nhiều auto-configuration đã khớp hoặc không khớp điều kiện nào. Nếu có Spring Boot Actuator và endpoint được bật, bảo vệ và expose phù hợp, endpoint **/actuator/conditions** cũng cung cấp thông tin về các điều kiện cấu hình.

Một số lỗi thường gặp:

- **Thiếu starter hoặc thư viện client:** class điều kiện không có trên classpath nên auto-configuration không chạy.
- **Sai property:** Boot tạo bean nhưng kết nối tới broker sai host, port hoặc credential.
- **Tạo bean trùng hoặc thay thế ngoài ý muốn:** bean tùy chỉnh khiến bean mặc định không được tạo.
- **Nhầm component scan với auto-configuration:** component không được tìm thấy vì package nằm ngoài vùng scan.
- **Kỳ vọng Boot tự tạo topology nghiệp vụ:** ứng dụng vẫn phải định nghĩa queue, topic, exchange, binding hoặc subscription theo yêu cầu.
- **Nhầm abstraction với transport:** spring-messaging có Message và MessageChannel nhưng không tự cung cấp broker hoặc bảo đảm message được lưu bền vững.

## 9. Ghi nhớ khi thiết kế ứng dụng messaging

Khi đọc một cấu hình Spring, hãy xác định bean nào đến từ ứng dụng, bean nào do thư viện tích hợp cung cấp và bean nào do Boot auto-configure. Sau đó kiểm tra dependency, property và điều kiện tạo bean tương ứng.

Với messaging, cần phân biệt rõ ba lớp:

1. **Abstraction:** các kiểu Message, MessageHeaders, MessageChannel và MessageHandler của Spring Messaging.
2. **Transport/integration:** thư viện kết nối với RabbitMQ, Kafka, JMS hoặc hệ thống khác.
3. **Application behavior:** payload, schema, queue/topic, routing, listener và logic nghiệp vụ.

Cấu hình thủ công cho phép ta kiểm soát tường minh từng thành phần. Spring Boot auto-configuration giảm công việc thiết lập các thành phần phổ biến bằng cách áp dụng cấu hình có điều kiện. Hiểu ranh giới giữa ba lớp này giúp ta biết phần nào cần tự khai báo, phần nào có thể giao cho Boot và cách tùy chỉnh mà không vô tình phá vỡ cấu hình mặc định.