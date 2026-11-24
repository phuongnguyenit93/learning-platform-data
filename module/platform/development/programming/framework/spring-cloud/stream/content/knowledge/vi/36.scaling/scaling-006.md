# Binder SPI và hợp đồng bindConsumer, bindProducer

**Spring Cloud Stream** cho phép một hàm nghiệp vụ nhận hoặc phát sự kiện qua Kafka, RabbitMQ, Pulsar mà không cần trực tiếp sử dụng toàn bộ API của từng broker. Thành phần nối ứng dụng với hệ thống truyền thông điệp được gọi là **Binder**; tập hợp giao diện và điểm mở rộng để triển khai thành phần này được gọi là **Binder SPI** (*Service Provider Interface*).

Bài học đi từ chữ ký của Binder, hợp đồng bindConsumer và bindProducer, lifecycle của Binding, rồi đến ví dụ custom binder, consumer group, partitioning, retry/DLQ, bảo đảm giao nhận và các phép kiểm thử. Đây là kiến thức phục vụ module **SPRING_CLOUD_STREAM** về lập trình sự kiện theo mô hình Supplier/Function/Consumer, bindings và mở rộng workload trên các binder khác nhau.

## 1. Binder là ranh giới giữa ứng dụng và broker

Tách trách nhiệm làm ứng dụng ít phụ thuộc vào giao thức broker:

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| Function bean | Xử lý nghiệp vụ từ payload | Function<OrderCreated, OrderValidated> |
| Binding | Nối điểm input/output của function với destination | validateOrder-in-0, validateOrder-out-0 |
| Binder SPI | Cung cấp hợp đồng tạo kết nối inbound/outbound | bindConsumer, bindProducer |
| Binder implementation | Ánh xạ cấu hình và event vào client API của broker | Kafka, RabbitMQ, Pulsar |
| Transport | Lưu, phân phối và xác nhận message | Kafka partition, Rabbit queue, Pulsar subscription |

~~~mermaid
flowchart LR
  A[Supplier / Function / Consumer] <--> B[Spring Cloud Stream bindings]
  B <--> C{Binder SPI}
  C --> D[Kafka binder]
  C --> E[RabbitMQ binder]
  C --> F[Pulsar binder]
  C --> G[Custom binder]
  D --> H[(Kafka)]
  E --> I[(RabbitMQ)]
  F --> J[(Pulsar)]
  G --> K[(Middleware khác)]
~~~

SPI giúp viết một luồng xử lý bằng cùng mô hình Spring Messaging. Nó **không** khiến các broker tự động có cùng semantics về ordering, transaction, retry, DLQ hoặc exactly-once. Các đặc điểm đó phải được đối chiếu với middleware và binder cụ thể.

## 2. Chữ ký giao diện Binder<T, C, P>

Giao diện trung tâm thuộc package **org.springframework.cloud.stream.binder**:

~~~java
public interface Binder<
        T,
        C extends ConsumerProperties,
        P extends ProducerProperties> {

    Binding<T> bindConsumer(
            String bindingName,
            String group,
            T inboundBindTarget,
            C consumerProperties);

    Binding<T> bindProducer(
            String bindingName,
            T outboundBindTarget,
            P producerProperties);
}
~~~

| Tham số kiểu | Mô tả |
| --- | --- |
| T | Loại target phía ứng dụng. Với binder theo MessageChannel, target thường là MessageChannel |
| C | Lớp properties dành cho consumer, kế thừa ConsumerProperties |
| P | Lớp properties dành cho producer, kế thừa ProducerProperties |

Đây là hợp đồng tạo **đường kết nối lâu dài**, không phải API gửi một message hay gọi function một lần. Mỗi lần bind thành công trả về một Binding<T> để quản lý vòng đời.

Tên đối số **bindingName** trong chữ ký API hiện hành chỉ định logical destination phía binder. Trong cấu hình Spring Cloud Stream còn có *binding key* như validateOrder-in-0, dùng để đọc properties; hai tên này có thể khác nhau.

## 3. Hai hướng dữ liệu của SPI

~~~mermaid
flowchart LR
  D[(Broker destination)]
  C[Consumer endpoint - MessageProducer]
  IN[Inbound MessageChannel]
  F[Business Function]
  OUT[Outbound MessageChannel]
  P[Producer endpoint - MessageHandler]
  D --> C --> IN --> F --> OUT --> P --> D
~~~

Điểm thường gây nhầm là chữ **MessageProducer** trong Spring Integration: ở phía consumer, adapter nhận message từ broker rồi **sản xuất message cho Spring channel**. Ở chiều producer, một **MessageHandler** gắn với output channel để gửi message ra broker.

Một custom binder phải nối đúng hai hướng và định nghĩa cách khởi tạo, dừng, giải phóng endpoint.

## 4. Hợp đồng bindConsumer

~~~java
Binding<T> bindConsumer(
        String bindingName,
        String group,
        T inboundBindTarget,
        C consumerProperties);
~~~

| Đối số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| bindingName | Logical destination cần nhận | orders.created |
| group | Tên nhóm consumer/subscription | order-service |
| inboundBindTarget | Điểm nhận message trong ứng dụng | Input MessageChannel |
| consumerProperties | Concurrency, retry, partition, startup và cấu hình khác | ConsumerProperties |

Các trách nhiệm chính khi triển khai:

1. Kiểm tra tên destination, group và các thuộc tính được hỗ trợ.
2. Resolve hoặc provision topic/queue/subscription cần thiết.
3. Tạo consumer endpoint và kết nối nó với input target.
4. Đăng ký error handling, conversion và acknowledgment theo binder.
5. Khởi động/điều khiển consumer theo binding lifecycle.
6. Trả Binding<T> để framework dừng, start lại hoặc unbind.

Ví dụ **mô tả SPI**, không phải cách gọi thông thường trong business code:

~~~java
Binding<MessageChannel> inbound = binder.bindConsumer(
        "orders.created",
        "order-service",
        ordersInputChannel,
        consumerProperties);
~~~

bindConsumer thiết lập subscription/lắng nghe liên tục. Nó không đồng nghĩa với hành động poll đúng một record. Pollable consumers có SPI mở rộng riêng.

## 5. Hợp đồng bindProducer

~~~java
Binding<T> bindProducer(
        String bindingName,
        T outboundBindTarget,
        P producerProperties);
~~~

| Đối số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| bindingName | Logical destination outbound | orders.validated |
| outboundBindTarget | Nguồn phát message phía ứng dụng | Output MessageChannel |
| producerProperties | Partition key/count, startup, các thuộc tính producer khác | ProducerProperties |

Binder thường resolve/provision destination, tạo producer client hoặc handler, đăng ký handler trên output channel, thiết lập serialization/header mapping, và trả về Binding<T>.

~~~java
// Pseudocode để hiểu giao diện; framework thường gọi thay ứng dụng.
Binding<MessageChannel> outbound = binder.bindProducer(
        "orders.validated",
        ordersOutputChannel,
        producerProperties);
~~~

**bindProducer không phải send(message).** Nó tạo đường gửi; message được publish khi ứng dụng đẩy dữ liệu qua outbound target. Một binding tạo thành công cũng không bảo đảm mọi lần publish về sau được broker xác nhận.

## 6. Binding key, group và destination

Giả sử một function bean:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder() {
    return order -> new OrderValidated(order.orderId(), true);
}
~~~

Cấu hình Spring Cloud Stream:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          destination: orders.validated
~~~

| Giá trị | Loại | Chức năng |
| --- | --- | --- |
| validateOrder-in-0 | Binding key | Tra consumer binding configuration |
| orders.created | Logical destination | Broker source mà bindConsumer kết nối |
| validation-service | Group | Tập consumer phối hợp xử lý |
| validateOrder-out-0 | Binding key | Tra producer binding configuration |
| orders.validated | Logical destination | Broker target mà bindProducer kết nối |

Nếu không khai báo destination, Spring Cloud Stream có thể dùng binding name làm destination mặc định. Nhưng khi đã khai báo, không suy luận topic vật lý từ binding key. Rabbit binder có thể ánh xạ destination vào exchange, rồi theo group tạo queue; Kafka có topic và group; Pulsar dùng topic/subscription theo config.

## 7. Consumer group và hành vi phân phối

Ở mức trừu tượng, nhiều group khác nhau có thể nhận cùng luồng event, còn nhiều instance cùng group chia sẻ công việc:

~~~mermaid
flowchart TB
  P[Producer] --> D[(orders.created)]
  D --> A[Group billing: instance 1]
  D --> B[Group billing: instance 2]
  D --> C[Group analytics: instance 1]
~~~

Thực tế theo middleware:

| Binder | Ánh xạ group | Giới hạn |
| --- | --- | --- |
| Kafka message binder | Kafka consumer group | Partition được phân phối cho active members trong group |
| RabbitMQ binder | Queue/subscriber group, competing consumers | Prefetch, queue arguments và acknowledgment tác động đến phân phối |
| Pulsar binder | Subscription name/type | Shared, Exclusive, Failover, Key_Shared có semantics khác nhau |
| Kafka Streams binder | Application ID, tasks và consumer groups nội bộ | Có state restoration và repartition/changelog topology |

Group rỗng/null thường đại diện anonymous subscription; đừng dùng group vô danh nếu ứng dụng cần định danh consumer bền vững và phục hồi sau restart.

Không đồng nhất group với exactly-once. Broker có thể redeliver sau crash/rebalance hoặc khi acknowledgment thất bại. Với side effects như thanh toán, hãy dùng event ID và idempotency.

## 8. Common ConsumerProperties và ProducerProperties

Các cấu hình chung thường thấy:

| Phía | Thuộc tính | Ý nghĩa |
| --- | --- | --- |
| Consumer | autoStartup | Consumer endpoint có tự chạy không |
| Consumer | concurrency | Số consumer threads/containers mong muốn |
| Consumer | maxAttempts, backoff | Retry xử lý message nếu binder hỗ trợ theo cơ chế đó |
| Consumer | partitioned | Binding tiêu thụ luồng phân vùng |
| Producer | autoStartup | Producer adapter có tự start không |
| Producer | partitionKeyExpression | Trích key để phân vùng |
| Producer | partitionCount | Số partition mong muốn hoặc gợi ý theo binder |
| Producer | partitionSelectorName | Strategy chọn partition từ key |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
          consumer:
            concurrency: 3
            max-attempts: 4
        validateOrder-out-0:
          destination: orders.validated
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
~~~

Một binder phải xử lý các thuộc tính nó hỗ trợ và làm rõ giới hạn. Ví dụ concurrency=4 không có nghĩa sẽ có bốn luồng đang xử lý khi Kafka topic chỉ có hai partition. Retry ở Kafka message binder có thể do binder hoặc listener container đảm nhiệm tùy configuration.

## 9. ExtendedPropertiesBinder và thuộc tính đặc thù

Các binder cần thêm config riêng mà common properties không diễn đạt đầy đủ:

- Kafka: acks, partitions, topic properties, deserializer và consumer config.
- RabbitMQ: prefetch, exchange/queue arguments, dead-letter exchange, requeue.
- Pulsar: subscription type, schema, retry letter/dead letter policy.

Spring Cloud Stream hỗ trợ các lớp như **ExtendedConsumerProperties<X>**, **ExtendedProducerProperties<Y>** và giao diện **ExtendedPropertiesBinder**.

~~~text
ConsumerProperties
  + ExtendedConsumerProperties<KafkaConsumerProperties>

ProducerProperties
  + ExtendedProducerProperties<KafkaProducerProperties>
~~~

Cấu hình chung dùng namespace **spring.cloud.stream.bindings.<binding>.consumer/producer**. Cấu hình mở rộng dùng namespace **spring.cloud.stream.<binderType>.bindings.<binding>.consumer/producer** theo tài liệu binder cụ thể.

Không áp Kafka property cho Pulsar hoặc RabbitMQ chỉ vì mọi binder implement cùng một interface. Nếu tính năng không tồn tại ở broker, documentation và validation phải nói rõ.

## 10. Binding<T> và lifecycle

Kết quả của bindConsumer/bindProducer là một handle **Binding<T>**, dùng để điều khiển liên kết:

| Phương thức | Hợp đồng |
| --- | --- |
| isRunning() | Hỏi lifecycle target có đang chạy không |
| start() | Start target hoặc hoạt động rebind/restart được implementation hỗ trợ |
| stop() | Stop target |
| pause() / resume() | Tạm dừng/tiếp tục nếu middleware hỗ trợ |
| unbind() | Tháo liên kết và giải phóng các thành phần active |
| getName() | Trả tên binding |
| getExtendedInfo() | Trả metadata mở rộng nếu có |

**unbind() cần idempotent**: gọi lại không làm hỏng tài nguyên hoặc gây lỗi không cần thiết. Sau unbind, handle cũ nên bị loại bỏ; muốn kết nối lại phải tạo binding mới.

Stop thường giữ lại cấu hình để start lại, còn unbind tháo adapter và cleanup. Việc unbind **không** nên tự xóa topic/queue nghiệp vụ, vì tài nguyên broker có vòng đời độc lập. Pause/resume có thể không được binder hỗ trợ; không giả định mọi message consumer đều tạm dừng theo cùng cách.

## 11. Ai thực sự gọi bindConsumer và bindProducer?

Một ứng dụng dùng Spring Cloud Function hiếm khi gọi hai phương thức SPI. Quy trình thường là:

1. Framework phát hiện function bean và các binding tương ứng.
2. Binding service đọc destination, group, properties, binder selection.
3. BinderFactory tìm binder implementation thích hợp.
4. Framework gọi bindConsumer hoặc bindProducer.
5. Binder provision tài nguyên và tạo endpoint.
6. Framework giữ Binding<T> để lifecycle, shutdown và Actuator kiểm soát.

~~~mermaid
flowchart TD
  A[Function beans] --> B[Binding service]
  C[application.yml] --> B
  B --> D[BinderFactory và discovery]
  D --> E[Binder implementation]
  E --> F[ProvisioningProvider]
  F --> G[Consumer/producer endpoint]
  G --> H[Binding handle]
  H --> I[Start / stop / unbind]
~~~

Đây là sơ đồ trách nhiệm, không phải call stack cố định ở mọi binder hoặc topology. Kafka Streams binder có cơ chế tạo KafkaStreams topology và lifecycle riêng.

## 12. Khi nào cần custom binder?

Chỉ nên viết binder mới khi có middleware chưa có adapter đủ tốt hoặc một hạ tầng event nội bộ cần chia sẻ cách tích hợp cho nhiều ứng dụng.

Nếu chỉ muốn đổi Kafka serializer, Rabbit queue arguments hoặc Pulsar subscription type, ưu tiên extension properties, customizer hoặc header mapper của binder sẵn có. Custom binder kéo theo nghĩa vụ duy trì client lifecycle, retry, ack/commit, backpressure, metrics, security và tương thích version lâu dài.

Các thành phần thường có trong custom binder:

| Thành phần | Chức năng |
| --- | --- |
| ProvisioningProvider | Resolve/provision destination từ tên logic |
| ProducerDestination | Mô tả đích publish |
| ConsumerDestination | Mô tả nguồn consume |
| MessageHandler | Nhận message từ output channel rồi publish |
| MessageProducer | Nhận event từ transport rồi phát vào input channel |
| AbstractMessageChannelBinder | Tái sử dụng logic bind/lifecycle, wiring và error infrastructure |
| Spring Configuration | Tạo binder và kết nối transport |
| META-INF/spring.binders | Đăng ký binder type cho discovery |

## 13. ProvisioningProvider: logical thành physical destination

Cần phân biệt tên logical trong binding config với resources thực tế trên broker. Giao diện provisioning có hai phương thức chính:

~~~java
public interface ProvisioningProvider<
        C extends ConsumerProperties,
        P extends ProducerProperties> {

    ProducerDestination provisionProducerDestination(
            String name, P producerProperties);

    ConsumerDestination provisionConsumerDestination(
            String name, String group, C consumerProperties);
}
~~~

Ví dụ **demo** chỉ xác thực tên, không tạo tài nguyên từ xa:

~~~java
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class DemoProvisioner
        implements ProvisioningProvider<ConsumerProperties, ProducerProperties> {

    @Override
    public ProducerDestination provisionProducerDestination(
            String name, ProducerProperties props) {
        return new DemoDestination(validate(name));
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name, String group, ConsumerProperties props) {
        return new DemoDestination(validate(name));
    }

    private static String validate(String name) {
        if (name == null || !name.matches("[a-zA-Z0-9._-]{1,120}")) {
            throw new IllegalArgumentException("Invalid destination");
        }
        return name;
    }

    private static final class DemoDestination
            implements ConsumerDestination, ProducerDestination {

        private final String name;

        DemoDestination(String name) {
            this.name = name;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public String getNameForPartition(int partition) {
            return name + "-" + partition;
        }
    }
}
~~~

Quy tắc suffix partition chỉ dùng để minh họa interface. Kafka dùng native partition, RabbitMQ có exchange/queue, Pulsar có topic/partition riêng; không copy cách tạo tên demo vào production. Provisioner thật còn phải xử lý ACL, số partition, queue arguments, resource đã tồn tại, race conditions và idempotent provisioning.

## 14. AbstractMessageChannelBinder và các hook

Spring Cloud Stream cung cấp lớp cơ sở để không phải triển khai trực tiếp toàn bộ bindConsumer/bindProducer cho message-channel binder:

~~~java
AbstractMessageChannelBinder<C, P, PP>
~~~

Hai hook thiết yếu:

~~~java
protected MessageHandler createProducerMessageHandler(
        ProducerDestination destination,
        P producerProperties,
        MessageChannel errorChannel) throws Exception;

protected MessageProducer createConsumerEndpoint(
        ConsumerDestination destination,
        String group,
        C consumerProperties) throws Exception;
~~~

Tên method có vẻ ngược: createConsumerEndpoint tạo **MessageProducer** vì nó phát message vào Spring input channel; createProducerMessageHandler tạo **MessageHandler** vì handler nhận message từ Spring output channel để publish.

Đây là điểm mở rộng hợp lý nếu middleware cung cấp SDK event-driven, client subscribe và publish. API phụ có thể khác theo phiên bản; cần đối chiếu BOM trước khi build.

## 15. Ví dụ custom binder dùng AuditTransport

Giả sử tổ chức có SDK AuditBus dùng chung. Hợp đồng transport demo:

~~~java
import java.util.function.Consumer;
import org.springframework.messaging.Message;

public interface AuditTransport {
    void publish(String destination, Message<?> message);

    Registration subscribe(
            String destination,
            String group,
            Consumer<Message<?>> callback);

    interface Registration extends AutoCloseable {
        @Override
        void close();
    }
}
~~~

Consumer endpoint kế thừa MessageProducerSupport:

~~~java
import org.springframework.integration.endpoint.MessageProducerSupport;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;

public final class AuditInboundEndpoint extends MessageProducerSupport {

    private final AuditTransport transport;
    private final ConsumerDestination destination;
    private final String group;
    private AuditTransport.Registration registration;

    public AuditInboundEndpoint(
            AuditTransport transport,
            ConsumerDestination destination,
            String group) {
        this.transport = transport;
        this.destination = destination;
        this.group = group;
    }

    @Override
    protected void doStart() {
        registration = transport.subscribe(
                destination.getName(), group, this::sendMessage);
    }

    @Override
    protected void doStop() {
        if (registration != null) {
            registration.close();
            registration = null;
        }
    }
}
~~~

Bản demo chỉ cho thấy chiều chuyển message và lifecycle. Transport thật cần thread safety, message acknowledgment, error callback và chiến lược reconnect. Close registration phải dừng đúng consumer instance; không được xóa queue/topic dùng chung.

Binder gắn producer và consumer endpoints:

~~~java
import org.springframework.cloud.stream.binder.AbstractMessageChannelBinder;
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.integration.core.MessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

public final class AuditBinder
        extends AbstractMessageChannelBinder<
                ConsumerProperties, ProducerProperties, DemoProvisioner> {

    private final AuditTransport transport;

    public AuditBinder(AuditTransport transport, DemoProvisioner provisioner) {
        super(null, provisioner);
        this.transport = transport;
    }

    @Override
    protected MessageHandler createProducerMessageHandler(
            ProducerDestination destination,
            ProducerProperties props,
            MessageChannel errorChannel) {
        return message -> transport.publish(destination.getName(), message);
    }

    @Override
    protected MessageProducer createConsumerEndpoint(
            ConsumerDestination destination,
            String group,
            ConsumerProperties props) {
        return new AuditInboundEndpoint(transport, destination, group);
    }
}
~~~

**Đây là khung giảng giải SPI, chưa phải binder production.** AuditTransport cần implementation kết nối broker thật; ví dụ chưa triển khai confirm/ack, async error, retry/DLQ, backpressure và chính sách ownership của clients. Nếu middleware không có nhóm consumer như Spring Cloud Stream yêu cầu, phải xây dựng semantics nhóm hoặc ghi rõ giới hạn.

## 16. Đăng ký binder qua cấu hình Spring và spring.binders

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditBinderConfiguration {

    @Bean
    DemoProvisioner auditProvisioner() {
        return new DemoProvisioner();
    }

    @Bean
    AuditBinder auditBinder(
            AuditTransport transport,
            DemoProvisioner provisioner) {
        return new AuditBinder(transport, provisioner);
    }
}
~~~

Bean AuditTransport phải được cung cấp riêng thông qua SDK/configuration của middleware.

Trong thư viện binder tạo file **META-INF/spring.binders**:

~~~properties
auditBus=com.acme.audit.AuditBinderConfiguration
~~~

Tên auditBus là binder type; configuration class cần tồn tại trên classpath và cung cấp đúng binder bean.

Ứng dụng sử dụng:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          binder: auditBus
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          binder: auditBus
          destination: orders.validated
~~~

Đây là lý do SPI có tính plug-in: mã nghiệp vụ chỉ khai báo Function, còn tên binder và destination được chọn bằng cấu hình.

## 17. Nhiều binder trên cùng classpath

Một function có thể nhận Kafka và gửi RabbitMQ:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          binder: kafka
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          binder: rabbit
          destination: orders.validated
~~~

Khi có nhiều binder, Spring Cloud Stream cần biết binder nào phục vụ từng binding; có thể chỉ định **spring.cloud.stream.defaultBinder** ở cấp ứng dụng hoặc **binder** theo binding.

Binder type được khai báo trong META-INF/spring.binders, không phải tên bean business function. Kafka Streams binder và regular Kafka message binder là những cơ chế khác nhau dù cùng dùng Kafka.

## 18. Nhiều broker cùng loại

Để nối hai Kafka clusters, khai báo binder configurations riêng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          binder: kafkaPrimary
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          binder: kafkaSecondary
          destination: orders.validated
      binders:
        kafkaPrimary:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-primary:9092
        kafkaSecondary:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-secondary:9092
~~~

Cần bổ sung security configuration theo môi trường. Chuyển event giữa hai clusters **không** tự có giao dịch nguyên tử chung giữa commit offset input và publish output; cần thiết kế error recovery/idempotency/outbox nếu yêu cầu độ tin cậy cao.

Thuộc tính binder configuration:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| type | Tên binder type được đăng ký |
| environment | Cấu hình riêng cho binder instance |
| inheritEnvironment | Có kế thừa environment ứng dụng hay không |
| defaultCandidate | Binder instance có được xét làm default hay không |

Khi khai báo binder configurations tường minh, cơ chế tạo binder mặc định thay đổi; hãy khai báo rõ tất cả binder được dùng.

## 19. Scale consumer bằng SPI: giới hạn của broker

SPI cho phép yêu cầu **concurrency** và **group**, nhưng hiệu năng thực tế còn phụ thuộc middleware:

- Kafka: active consumers trong cùng group thường không tăng song song hiệu dụng vượt số partition.
- RabbitMQ: competing consumers chia sẻ queue, với prefetch và acknowledgment ảnh hưởng fairness.
- Pulsar: Shared subscription hỗ trợ phân phối cạnh tranh; Key_Shared cần giữ ordering theo key.
- Kafka Streams: scale theo stream tasks/partitions và phải tính state restoration/changelog.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            concurrency: 4
~~~

Đây là **yêu cầu** với binder; số consumer thật có thể khác theo implementation. Tăng concurrency khi downstream DB đang nghẽn có thể chỉ tăng contention và retry load.

## 20. Producer partitioning và ordering

ProducerProperties hỗ trợ partition key và partition selection:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-out-0:
          producer:
            partition-key-expression: payload.orderId
            partition-count: 8
~~~

Chọn key có phân phối đều và ổn định nếu cần ordering theo entity. Không tính partition bằng thuật toán tùy ý ở cả function và binder; phải hiểu native partition mapping của middleware. Tăng partition count không phải lúc nào cũng giữ nguyên routing/ordering history của key.

Một custom binder cần mô tả rõ nó có hỗ trợ native partitioning, partition selector hay routing khác. Nếu chưa hỗ trợ, không âm thầm bỏ qua yêu cầu partition quan trọng.

## 21. Retry, DLQ và giao nhận nằm ngoài chữ ký SPI

bindConsumer và bindProducer **không hứa hẹn** exactly-once. Chúng chỉ tạo adapter/binding. Reliability phụ thuộc:

| Loại lỗi | Nơi xảy ra | Hướng xử lý |
| --- | --- | --- |
| Không bind được broker/destination | Thời điểm bind | Binding retry/fail-fast, provisioning diagnostics |
| Lỗi parse payload | Consumer adapter | Deserializer/converter error handler, DLQ |
| Hàm business ném exception | Sau khi inbound | Retry policy, recoverer, DLQ/DLT |
| Publish thất bại | Producer adapter | Confirm/callback, async error channel, retry |
| Consumer crash trước ack | Middleware/container | Redelivery, idempotency |
| Stop/unbind khi có in-flight message | Binding lifecycle | Graceful shutdown, flush, commit/ack |

Nếu một custom binder chỉ gọi transport.publish rồi trả thành công trước khi broker xác nhận, phải mô tả rõ đây là semantics bất đồng bộ; không báo gửi bền vững nếu chưa có ack.

Với Kafka, RabbitMQ và Pulsar, cấu hình retry/DLQ khác nhau. Không sao chép tên property của broker này sang broker khác chỉ vì cùng cài Binder SPI.

## 22. Header và schema conversion

Binder là chỗ giao thoa Spring MessageHeaders với native headers/metadata của broker:

- Kafka record headers mang byte arrays.
- RabbitMQ dùng AMQP headers và message properties.
- Pulsar custom user properties là cặp chuỗi, ngoài metadata riêng.

Cần có chính sách copy header, content type, schema/serde, trusted types và exception mapping. Type header Java từ producer ngoài không phải bằng chứng class đó được phép deserialize. Trace context cần được propagator thích hợp inject/extract; business correlation ID và event ID cần giữ riêng.

Một custom binder nên giới hạn payload/header size, không forward access token hoặc toàn bộ internal headers, và phải có test với producer khác ngôn ngữ nếu dự kiến tích hợp đa nền tảng.

## 23. Resource ownership và partial failure

Các trường hợp phải kiểm thử khi viết binder:

1. Provision được topic/queue nhưng consumer endpoint không tạo được.
2. Khởi tạo client thành công nhưng đăng ký callback thất bại.
3. Framework retry bind sau lỗi tạm thời.
4. Nhiều bindings dùng chung một connection pool.
5. Một binding stop/unbind trong khi binding khác vẫn dùng cùng client.
6. Shutdown trong khi producer còn pending sends và consumer còn in-flight records.

Không đóng shared client khi chỉ một binding unbind. Ngược lại, phải đóng registration/listener, worker thread và resource thuộc riêng binding để tránh leak. Provisioning nên idempotent; retry không được tạo thêm queue/subscription trùng lặp.

**Không xóa tài nguyên broker trong unbind()** theo mặc định. Topic và queue thường là shared resource; adapter lifecycle và resource lifecycle là hai vấn đề khác nhau.

## 24. Bảo mật của binder tùy chỉnh

Binder có thể có quyền tạo tài nguyên, nên cần kiểm soát:

- Tên dynamic destination hợp lệ hoặc thuộc allowlist.
- TLS/SASL/token lấy từ secret manager; không hard-code.
- Quyền producer/consumer/provisioner theo nguyên tắc tối thiểu.
- Không ghi credentials, raw payload nhạy cảm vào logs.
- Hạn chế message size, header count, retry concurrency và pending queue.
- Phân biệt lỗi ACL cố định với lỗi broker tạm thời để tránh retry nóng.
- Xác thực schema và payload trước khi xử lý nghiệp vụ.
- Rate limit việc tạo destination động.
- Không tin tenantId/role trong message header làm nguồn authorization.

## 25. Giám sát và quản trị bindings

Spring Cloud Stream có Actuator bindings endpoint nếu bật:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Ví dụ truy vấn:

~~~bash
curl -fsS http://localhost:8080/actuator/bindings
curl -fsS http://localhost:8080/actuator/bindings/validateOrder-in-0
~~~

Endpoint có thể điều khiển STARTED/STOPPED và PAUSED/RESUMED tùy khả năng binder, vì vậy cần bảo vệ bằng authentication/authorization và mạng quản trị.

Các metric cần có: bind success/failure, bind latency, số connections, producer send errors, consumer lag/delivery rate, retries/DLQ, resource leaks, time to ready. Binding STARTED chưa chứng minh message được xử lý end-to-end.

## 26. Chiến lược kiểm thử binder

| Tầng | Test | Kỳ vọng |
| --- | --- | --- |
| Provisioner unit test | Name/group/properties → destination | Mapping đúng, validation, idempotency |
| Producer adapter unit test | Output Message → transport publish | Header/payload, error propagation |
| Consumer adapter unit test | Transport callback → input Message | Lifecycle, conversion, error handling |
| Binding lifecycle | Bind/start/stop/unbind/unbind lại | Không leak listener hoặc resources |
| Binder discovery | META-INF/spring.binders + Spring context | Binder type và bean được phát hiện |
| Integration test | Transport/broker thật | Ack/commit, retry, DLQ, schema |
| Scale test | Nhiều instance/group/partition | Competition, fan-out, ordering |
| Fault injection | Broker outage, partial provisioning | Recover/rebind đúng, không mất resource |

Test Binder là công cụ kiểm thử function và binding ở tầng ứng dụng; **không đủ** để xác minh một binder tùy chỉnh có semantics đúng với broker. Với Kafka/Rabbit/Pulsar dùng Testcontainers hoặc broker test; với middleware riêng phải có môi trường transport thật.

### Test vòng đời bắt buộc

1. Sau bind, message đi đúng input/output.
2. Stop không còn nhận message mới theo contract.
3. Start lại không tạo duplicate listener.
4. Unbind giải phóng registration và client thuộc binding.
5. Unbind lặp lại là idempotent.
6. Bind mới sau unbind hoạt động đúng.
7. Shared destination và shared client của binding khác không bị xóa.

## 27. Test consumer groups và xử lý bản sao

Dùng một destination có group billing gồm hai instance và group analytics gồm một instance. Gửi N event với eventId khác nhau.

Kiểm tra mỗi group nhận đúng tập message theo semantics broker. Trong group billing, công việc được phân phối giữa hai instance; khi một instance chết, instance còn lại tiếp tục. Dưới tình huống replay/redelivery, duplicate là điều có thể xảy ra. Kiểm tra event ID, idempotency store và stop giữa lúc đang xử lý.

Không dùng test “một lần gửi, một lần nhận” để tuyên bố exactly-once end-to-end.

## 28. Lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Business function gọi Binder trực tiếp | Nhầm SPI với nghiệp vụ | Để framework tạo bindings bằng cấu hình |
| Nhầm binding key với topic | Không tách bindingName/destination | Kiểm tra destination property |
| Consumer không chia sẻ công việc | Group trống hoặc subscription semantics sai | Cấu hình group và kiểm tra native behavior |
| Concurrency tăng nhưng throughput không tăng | Partition/downstream bottleneck | Đo partition count, lag và tài nguyên |
| Binding STARTED nhưng không có data | ACL, assignment, schema hoặc broker lỗi | Kiểm tra group, metadata và errors |
| unbind xóa topic dùng chung | Nhầm resource ownership | Cleanup adapter, không xóa shared destination |
| Pause không có tác dụng | Binder không hỗ trợ | Dùng stop/start hoặc native API phù hợp |
| Restart tạo duplicate listener | doStart/doStop không idempotent | Quản lý registration và test repeated cycles |
| Publisher báo thành công quá sớm | Bỏ qua acknowledgment | Định nghĩa send semantics rõ |
| Multi-binder gửi sai cluster | Binder selection không tường minh | Dùng binding.binder và kiểm tra config instance |
| Dynamic destination bị lạm dụng | Thiếu validate/rate limit | Allowlists, ACL, quotas |
| DLQ không nhận record | Error handler/recoverer chưa triển khai | Integration test broker-specific flow |

## 29. Checklist trước production

- Xác định rõ kiểu T, C, P và contract input/output.
- Mapping binding key, logical destination, physical resource rõ ràng.
- Consumer group/anonymous behavior được mô tả.
- Provisioning có kiểm tra đầu vào và tính idempotent.
- MessageProducer và MessageHandler nối đúng chiều.
- Lifecycle start/stop/unbind giải phóng chính xác tài nguyên.
- Concurrency và partitioning phản ánh khả năng broker.
- Serialization/schema/header và trusted input được kiểm thử.
- Retry, ack/commit, DLT/DLQ, backpressure, duplicate rõ ràng.
- Binder registration qua Spring configuration và META-INF/spring.binders.
- Multi-binder, multi-cluster selection được kiểm thử.
- Secrets, ACL, dynamic destination được giới hạn.
- Có metrics, tracing, health indicators và runbook.
- Integration test/failover test trên transport thực tế.
- Ghi rõ chức năng chưa hỗ trợ thay vì ngầm giả định có.

## 30. Tài liệu tham khảo

- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html)
- [Spring Cloud Stream — Binder abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binders.html)
- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html)
- [Spring Cloud Stream — Binder Detection](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-detection.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Producer/Consumer Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producer-consumer-partitioning.html)

Tên class, package, method và extended properties có thể thay đổi theo Spring Cloud Stream release train. Ví dụ AuditTransport/AuditBinder dùng để minh họa extension points và cần bổ sung broker SDK, acknowledgment, retry, DLQ, validation, metrics trước khi triển khai thực tế.

## Kết luận

**Binder<T,C,P>** là hợp đồng nối application target với middleware. **bindConsumer** tạo inbound adapter theo destination/group/properties; **bindProducer** tạo outbound adapter theo destination/properties. Hai phương thức trả về **Binding<T>** để framework quản lý lifecycle. Khi cần binder riêng, nên dùng ProvisioningProvider và AbstractMessageChannelBinder để tái sử dụng cơ chế chuẩn, đồng thời tự chịu trách nhiệm về transport semantics. Scale đúng đòi hỏi hiểu group, partition, retry, DLQ, ack và idempotency của từng binder; SPI giúp chuẩn hóa cách kết nối nhưng không thay thế thiết kế độ tin cậy.
