# Phân tầng kiểm thử hàm, binding và broker thực

Ứng dụng Spring Cloud Stream có nhiều thành phần cùng tham gia xử lý một message: hàm nghiệp vụ, message conversion, binding, binder và broker. Một unit test xác nhận hàm trả đúng kết quả chưa chứng minh binding dùng đúng destination; một test với binder giả lập chưa chứng minh Kafka commit offset, RabbitMQ ACK message hoặc Pulsar redeliver message sau NACK.

Vì vậy, nên tổ chức kiểm thử theo từng tầng. Tầng hàm kiểm tra logic nhanh và cô lập; tầng binding xác nhận Spring Cloud Stream kết nối function với message channel đúng cách; tầng broker thực xác nhận ứng dụng tương tác đúng với Kafka, RabbitMQ hoặc Pulsar đang được triển khai. Với Kafka Streams, `TopologyTestDriver` bổ sung một tầng kiểm thử topology không cần broker.

Bài học này trình bày cách chọn đúng công cụ cho từng tầng, cách cấu hình Spring Integration Test Binder, cách khởi chạy broker thử nghiệm bằng Testcontainers và các kịch bản cần có trước khi triển khai.

## 1. Bức tranh tổng thể của một luồng kiểm thử

Một luồng xử lý điển hình có thể được kiểm thử theo ba ranh giới:

~~~mermaid
flowchart TD
    A[JUnit test] --> B[Hàm nghiệp vụ]
    B --> C[Spring Cloud Stream binding]
    C --> D[Binder]
    D --> E[(Kafka / RabbitMQ / Pulsar)]
    E --> F[Consumer hoặc ứng dụng đích]

    G[Tầng 1: Unit test] -. kiểm tra .-> B
    H[Tầng 2: Test Binder] -. kiểm tra .-> C
    I[Tầng 3: Broker thật] -. kiểm tra .-> D
    I -. kiểm tra .-> E
~~~

| Tầng | Thành phần được kiểm tra | Công cụ thường dùng | Tốc độ và phạm vi |
|---|---|---|---|
| 1. Hàm | Supplier, Function, Consumer và quy tắc nghiệp vụ | JUnit, AssertJ, Mockito | Nhanh; không cần Spring context hoặc broker. |
| 2. Binding | Function activation, binding name, payload conversion, header và luồng vào/ra | Spring Integration Test Binder | Chạy trong JVM; không kết nối middleware thật. |
| 3. Broker | Binder implementation, kết nối, provision destination, routing, group, partition, ACK, retry, DLQ và giao nhận | Testcontainers hoặc broker thử nghiệm tương đương | Chậm hơn; xác minh giao thức và hành vi broker thực. |

Không phải mọi test đều cần chạy qua cả ba tầng. Hãy đặt phần lớn trường hợp nghiệp vụ ở tầng hàm, các trường hợp tích hợp function/binding ở tầng hai, rồi chọn một tập kịch bản có giá trị cao để chạy với broker thật.

## 2. Tầng 1 — Unit test cho Supplier, Function và Consumer

Function bean trong Spring Cloud Stream vẫn là hàm Java thông thường. Nếu logic không phụ thuộc Spring hoặc broker, có thể gọi trực tiếp hàm trong JUnit.

Ví dụ hàm làm giàu sự kiện đơn hàng:

~~~java
import java.math.BigDecimal;
import java.util.function.Function;

public record OrderCreated(String orderId, BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        BigDecimal amount,
        String currency) {
}

public class OrderEnricher {

    public Function<OrderCreated, EnrichedOrder> enrichOrder() {
        return event -> new EnrichedOrder(
                event.orderId(),
                event.amount(),
                "VND"
        );
    }
}
~~~

Unit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderEnricherTest {

    private final OrderEnricher enricher = new OrderEnricher();

    @Test
    void enrichesOrderWithCurrency() {
        OrderCreated event =
                new OrderCreated("order-101", new BigDecimal("250000"));

        EnrichedOrder result = enricher.enrichOrder().apply(event);

        assertThat(result.orderId()).isEqualTo("order-101");
        assertThat(result.amount()).isEqualByComparingTo("250000");
        assertThat(result.currency()).isEqualTo("VND");
    }
}
~~~

Unit test nên tập trung vào:

- Quy tắc tính toán, lọc, chuẩn hóa và làm giàu dữ liệu.
- Giá trị biên, dữ liệu thiếu, dữ liệu sai định dạng và ngoại lệ.
- Điều kiện idempotency hoặc quy tắc bỏ qua sự kiện trùng.
- Thứ tự xử lý trong function composition nếu các bước được gọi trực tiếp.
- Kết quả và side effect của Consumer thông qua collaborator.

### Kiểm thử Consumer có collaborator

Consumer thường gọi service hoặc repository. Hãy mock collaborator để xác nhận hành vi mà không khởi tạo binder:

~~~java
import static org.mockito.Mockito.verify;

import java.math.BigDecimal;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

interface OrderService {
    void handle(OrderCreated event);
}

@ExtendWith(MockitoExtension.class)
class OrderConsumerTest {

    @Mock
    private OrderService orderService;

    @Test
    void delegatesEventToOrderService() {
        OrderCreated event =
                new OrderCreated("order-101", new BigDecimal("250000"));
        Consumer<OrderCreated> consumer = orderService::handle;

        consumer.accept(event);

        verify(orderService).handle(event);
    }
}
~~~

Nếu Consumer có logic điều kiện trước khi gọi service, hãy kiểm tra cả nhánh được gọi và nhánh bị bỏ qua. Không cần mock MessageChannel, Binder hoặc KafkaTemplate trong một test chỉ nhằm xác nhận quy tắc nghiệp vụ.

### Kiểm thử Supplier

Supplier không có input message; mỗi lần gọi get() tạo ra hoặc lấy một giá trị mới. Có thể kiểm tra nội dung, định dạng và nguồn dữ liệu trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

record Heartbeat(String service, String status) {
}

class HeartbeatSupplierTest {

    @Test
    void createsHeartbeatEvent() {
        Supplier<Heartbeat> supplier =
                () -> new Heartbeat("inventory-service", "UP");

        Heartbeat event = supplier.get();

        assertThat(event.service()).isEqualTo("inventory-service");
        assertThat(event.status()).isEqualTo("UP");
    }
}
~~~

Nếu Supplier phụ thuộc clock, UUID hoặc nguồn ngẫu nhiên, hãy tiêm dependency để test có thể kiểm soát thời gian và dữ liệu. Tránh dùng Thread.sleep() để chờ Supplier phát message; việc phát định kỳ thuộc tầng binding hoặc scheduler và cần được kiểm tra ở tầng tích hợp.

## 3. Tầng 2 — Spring Integration Test Binder

Spring Cloud Stream cung cấp **Spring Integration Test Binder** để kiểm tra ứng dụng mà không cần kết nối Kafka, RabbitMQ hoặc Pulsar. Test Binder hoạt động như một message broker trong JVM, dựa trên Spring Integration channels.

Nó phù hợp để kiểm tra:

- Function nào được kích hoạt qua spring.cloud.function.definition.
- Binding name và destination mapping.
- Message đi từ input binding tới function và output binding.
- Payload conversion, content type và header trong phạm vi test binder hỗ trợ.
- Nhiều input/output hoặc nhiều function độc lập.
- Hành vi của StreamBridge và PollableMessageSource trong luồng test phù hợp.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

Hãy để Spring Cloud BOM quản lý phiên bản tương thích với Spring Boot và Spring Cloud Stream của ứng dụng; không tự ghim một phiên bản test binder khác dòng với dependency runtime.

### Dùng InputDestination và OutputDestination

Ví dụ ứng dụng có Function chuyển chuỗi thành chữ hoa:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableAutoConfiguration
@EnableTestBinder
public class UppercaseTestConfiguration {

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    public Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(
        classes = UppercaseTestConfiguration.class,
        properties = "spring.cloud.function.definition=uppercase")
class UppercaseBindingTest {

    @Autowired
    private InputDestination input;

    @Autowired
    private OutputDestination output;

    @Test
    void sendsMessageThroughFunctionBinding() {
        input.send(new GenericMessage<>("hello".getBytes()),
                "uppercase-in-0");

        Message<byte[]> result =
                output.receive(1_000, "uppercase-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), java.nio.charset.StandardCharsets.UTF_8))
                .isEqualTo("HELLO");
    }
}
~~~

InputDestination gửi message vào input binding. OutputDestination lấy message đã được function phát ra output binding. Tham số tên binding giúp test chỉ rõ cổng đang kiểm tra; timeout của receive tính bằng mili giây.

Trong dự án thực tế, có thể đặt function definition qua cấu hình test thay vì cấu hình cứng trong class:

~~~properties
spring.cloud.function.definition=uppercase
~~~

Điều này hữu ích khi một ứng dụng có nhiều function bean nhưng mỗi test chỉ muốn kích hoạt một function hoặc một chuỗi composition cụ thể.

## 4. Kiểm thử binding name và nhiều input/output

Binding name là hợp đồng giữa function và cấu hình destination. Một test có thể chạy đúng function nhưng gửi message nhầm binding, đặc biệt khi ứng dụng có nhiều function.

Ví dụ kích hoạt hai function độc lập:

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase;reverse"
~~~

Hai function có input/output binding riêng:

| Function | Input binding | Output binding |
|---|---|---|
| uppercase | uppercase-in-0 | uppercase-out-0 |
| reverse | reverse-in-0 | reverse-out-0 |

Test cần gửi và nhận theo đúng binding:

~~~java
Message<byte[]> inputMessage =
        new GenericMessage<>("Hello".getBytes());

input.send(inputMessage, "uppercase-in-0");
input.send(inputMessage, "reverse-in-0");

Message<byte[]> upper = output.receive(1_000, "uppercase-out-0");
Message<byte[]> reversed = output.receive(1_000, "reverse-out-0");

assertThat(new String(upper.getPayload())).isEqualTo("HELLO");
assertThat(new String(reversed.getPayload())).isEqualTo("olleH");
~~~

Nếu cấu hình destination alias, hãy gửi và nhận theo destination đã ánh xạ. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: order-input
        uppercase-out-0:
          destination: order-output
~~~

Khi đó test có thể gọi input.send(message, "order-input") và output.receive(1_000, "order-output"). Kiểm tra alias giúp phát hiện cấu hình đang dùng nhầm tên mặc định và tên destination.

### Nhiều input

Với BiFunction hoặc curried function, hãy gửi message vào từng input binding theo thứ tự khai báo:

~~~java
input.send(customerMessage, "enrichOrder-in-0");
input.send(productMessage, "enrichOrder-in-1");
~~~

Test nên xác nhận function nhận đúng dữ liệu từ từng nguồn, không chỉ xác nhận output cuối cùng khác null. Nếu function cần hai input có liên hệ theo key, hãy tạo test có key trùng và key không trùng để kiểm tra quy tắc join.

## 5. Kiểm thử message conversion và header

Spring Cloud Stream chuyển đổi message dựa trên content type, payload type và cấu hình binding. Tầng Test Binder phù hợp để kiểm tra hợp đồng chuyển đổi trong phạm vi ứng dụng:

- application/json chuyển payload JSON sang DTO.
- Kiểu chuỗi và byte array được chuyển đổi đúng.
- Message header nghiệp vụ được đọc bởi function.
- Header được giữ hoặc loại bỏ theo cấu hình và chính sách header propagation.
- Message không hợp lệ đi vào nhánh lỗi mà ứng dụng đã thiết kế.

Ví dụ gửi message có header:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> message = MessageBuilder
        .withPayload("{\"orderId\":\"order-101\"}".getBytes())
        .setHeader("event-type", "OrderCreated")
        .setHeader("correlation-id", "corr-101")
        .build();

input.send(message, "orders-in-0");
~~~

Nếu function sử dụng event-type hoặc correlation-id, hãy kiểm tra giá trị mà function thực sự nhận. Đừng mặc định mọi header đều được truyền nguyên vẹn qua mọi binder: một số header là nội bộ, một số header cần cấu hình mapping, và broker có giới hạn riêng về kiểu hoặc kích thước metadata.

Với schema Avro, Protobuf hoặc JSON Schema, hãy kiểm tra cả serializer/deserializer và quy tắc tương thích schema. Test Binder có thể kiểm tra logic sau khi conversion, nhưng không chứng minh Schema Registry hoặc schema negotiation của broker đang hoạt động đúng.

## 6. Giới hạn của Test Binder

Test Binder là một broker giả lập trong JVM. Nó giúp kiểm tra kết nối giữa Spring Cloud Stream channels và function, nhưng không chạy giao thức Kafka, AMQP hoặc Pulsar.

Không dùng riêng Test Binder để kết luận rằng các hành vi sau đã đúng:

- Kafka consumer group coordination, offset commit, partition assignment và rebalance.
- Kafka transaction, idempotent producer, broker replication hoặc log retention.
- RabbitMQ exchange, queue declaration, binding, routing key, publisher confirm, mandatory return, ACK/NACK và DLQ của broker.
- Pulsar subscription type, broker acknowledgement, redelivery, dead-letter topic và broker schema enforcement.
- TLS, SASL, credential, network partition, broker restart hoặc quyền truy cập thực tế.

Một test binder thành công chỉ chứng minh luồng message trong môi trường test binder hoạt động như mong đợi. Nó không thay thế kiểm thử với middleware binder thật.

### Không trộn Test Binder với real binder trong cùng test runtime

Khi Test Binder nằm trên test classpath, Spring Cloud Stream có thể chọn nó cho các binding cần giao tiếp. Vì vậy, nếu cùng một module test vừa muốn dùng Test Binder vừa muốn dùng Kafka/Rabbit/Pulsar binder thực, test có thể vô tình kết nối tới kênh trong JVM thay vì broker.

Tài liệu Spring Cloud Stream khuyến nghị tách test dùng Test Binder và test dùng middleware binder thật thành module riêng để mỗi nhóm có classpath rõ ràng. Nếu kiến trúc dự án không thể tách module, hãy cấu hình loại trừ/ưu tiên auto-configuration một cách tường minh và xác minh binder thực tế được khởi tạo trong test context.

Không chỉ dựa vào việc test không báo lỗi kết nối để kết luận đang dùng broker thật. Hãy kiểm tra log khởi tạo binder, connection tới broker và một message được đọc từ broker bằng client độc lập.

## 7. Kafka Streams — dùng TopologyTestDriver cho logic topology

Kafka Streams cung cấp TopologyTestDriver trong artifact kafka-streams-test-utils. Driver cho phép đưa record vào topology và đọc output mà không cần chạy Kafka broker. Nó phù hợp để kiểm thử DSL, processor, join, aggregate, window và state store ở mức topology.

Ví dụ topology chuyển chuỗi thành chữ hoa:

~~~java
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Produced;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderTopologyTest {

    @Test
    void transformsInputRecord() {
        StreamsBuilder builder = new StreamsBuilder();
        builder.stream(
                        "orders",
                        Consumed.with(Serdes.String(), Serdes.String()))
                .mapValues(String::toUpperCase)
                .to("orders-uppercase",
                        Produced.with(Serdes.String(), Serdes.String()));

        Properties properties = new Properties();
        properties.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-test");
        properties.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");
        properties.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
                Serdes.String().getClass().getName());
        properties.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
                Serdes.String().getClass().getName());

        try (TopologyTestDriver driver =
                     new TopologyTestDriver(builder.build(), properties)) {
            TestInputTopic<String, String> input =
                    driver.createInputTopic(
                            "orders",
                            Serdes.String().serializer(),
                            Serdes.String().serializer());
            TestOutputTopic<String, String> output =
                    driver.createOutputTopic(
                            "orders-uppercase",
                            Serdes.String().deserializer(),
                            Serdes.String().deserializer());

            input.pipeInput("order-101", "created");

            assertThat(output.readValue()).isEqualTo("CREATED");
        }
    }
}
~~~

TopologyTestDriver xử lý input đồng bộ, nên test nhanh và dễ tái lập. Driver mô phỏng producer/consumer ở mức byte array và hỗ trợ TestInputTopic, TestOutputTopic để serialize/deserialize dữ liệu test.

Driver không chạy broker thật. Nó không kiểm chứng Kafka consumer group, broker partition assignment, transaction giữa broker, network, replication hoặc hành vi của Spring Cloud Stream Kafka Streams binder khi provision topic. Với những yêu cầu đó, cần thêm integration test chạy ứng dụng binder với Kafka thực.

## 8. Tầng 3 — Kiểm thử với broker thật

Để kiểm chứng binder, cần khởi động broker tương thích và cấu hình ứng dụng test kết nối tới địa chỉ động mà broker cung cấp. Testcontainers có module cho Kafka, RabbitMQ và Pulsar; container được khởi tạo trong test và dừng sau khi test hoàn tất.

Các module Testcontainers thường dùng:

| Broker | Module Testcontainers | Thông tin kết nối cần lấy |
|---|---|---|
| Kafka | testcontainers-kafka | Bootstrap servers. |
| RabbitMQ | testcontainers-rabbitmq | Host, AMQP port, username/password nếu thay mặc định. |
| Pulsar | testcontainers-pulsar | Pulsar broker URL và HTTP/admin URL. |

Với Gradle, các dependency test có thể khai báo như sau; hãy quản lý phiên bản bằng Testcontainers BOM hoặc dependency management đang dùng trong dự án:

~~~kotlin
testImplementation("org.testcontainers:testcontainers-junit-jupiter")
testImplementation("org.testcontainers:testcontainers-kafka")
testImplementation("org.testcontainers:testcontainers-rabbitmq")
testImplementation("org.testcontainers:testcontainers-pulsar")
~~~

Chỉ thêm module của broker mà test suite thực sự sử dụng. JUnit Jupiter integration cung cấp `@Testcontainers` và `@Container` để quản lý vòng đời container.

Dùng Testcontainers giúp test có broker độc lập, trạng thái khởi đầu có thể kiểm soát và không phụ thuộc broker cài sẵn trên máy lập trình viên. Chọn image tương thích với phiên bản production; không dùng image latest cho test ổn định.

### Khởi tạo Kafka container

Ví dụ với JUnit Jupiter và Kafka module của Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class KafkaBinderIntegrationTest {

    @Container
    static final KafkaContainer KAFKA =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                KAFKA::getBootstrapServers);
    }

    @Test
    void applicationStartsWithRealKafkaBinder() {
        // Gửi message qua binding và xác nhận ở consumer/output thực tế.
    }
}
~~~

Image apache/kafka-native:3.8.0 chỉ là ví dụ minh họa API. Hãy thay bằng phiên bản broker mà hệ thống triển khai hỗ trợ và pin tag cụ thể. Kafka binder lấy địa chỉ broker từ spring.cloud.stream.kafka.binder.brokers.

Spring Kafka cũng cung cấp spring-kafka-test với @EmbeddedKafka và KafkaTestUtils. Embedded broker phù hợp cho nhiều integration test cục bộ; Testcontainers hữu ích khi muốn chạy đúng image broker, kiểm tra network/container và gần với môi trường triển khai hơn. Với Kafka 4.x, embedded broker dùng KRaft.

### Khởi tạo RabbitMQ container

RabbitMQ binder mặc định dùng Spring Boot ConnectionFactory, nên cấu hình kết nối sử dụng prefix spring.rabbitmq.

Ví dụ ánh xạ địa chỉ container:

~~~java
@DynamicPropertySource
static void rabbitProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.rabbitmq.host", RABBIT::getHost);
    registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
    registry.add("spring.rabbitmq.username", RABBIT::getAdminUsername);
    registry.add("spring.rabbitmq.password", RABBIT::getAdminPassword);
}
~~~

RABBIT là instance RabbitMQ container được quản lý bởi Testcontainers. Dependency module testcontainers-rabbitmq cung cấp container phù hợp. Nếu image test dùng credential mặc định, vẫn nên đọc credential từ container thay vì hard-code vào test.

Với RabbitMQ, test nên xác nhận queue và exchange được binder provision, message được route theo binding key, queue group hoạt động, ACK/NACK đúng và dead-letter exchange/queue nhận message theo cấu hình.

### Khởi tạo Pulsar container

Pulsar module của Testcontainers cung cấp PulsarContainer. Spring for Apache Pulsar sử dụng spring.pulsar.client.service-url cho client và spring.pulsar.administration.service-url cho administration client khi binder cần provision topic.

Ví dụ:

~~~java
@DynamicPropertySource
static void pulsarProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.pulsar.client.service-url",
            PULSAR::getPulsarBrokerUrl);
    registry.add(
            "spring.pulsar.administration.service-url",
            PULSAR::getHttpServiceUrl);
}
~~~

PULSAR là container được Testcontainers quản lý. Nếu phiên bản Spring for Apache Pulsar/Spring Boot trong dự án dùng tên property administration khác, hãy đối chiếu configuration metadata của đúng phiên bản BOM. Client URL và admin URL là hai endpoint khác nhau; không thay URL HTTP bằng Pulsar binary protocol URL.

## 9. Kiểm thử ứng dụng qua real binder

Một integration test có giá trị phải đi qua binder implementation thật. Có thể kiểm tra cả producer lẫn consumer:

1. Khởi động Spring Boot application với function definition và destination cần test.
2. Khởi động broker container và đưa địa chỉ động vào cấu hình binder.
3. Gửi message bằng StreamBridge hoặc producer client độc lập.
4. Xác nhận message được binder consumer nhận và function xử lý.
5. Đọc output từ broker bằng consumer client độc lập hoặc kiểm tra side effect có thể quan sát.
6. Dọn topic/queue/subscription sau test nếu chúng không được quản lý tự động.

Ví dụ gửi message động qua StreamBridge:

~~~java
boolean accepted = streamBridge.send("orders", event);
assertThat(accepted).isTrue();
~~~

Kết quả true từ StreamBridge.send chỉ cho biết message đã được chấp nhận vào đường gửi theo API. Với test yêu cầu bảo đảm giao nhận, vẫn cần chờ và xác nhận ở phía consumer hoặc đọc message từ broker. Không dùng kết quả trả về này thay cho publisher confirm, consumer ACK hoặc bằng chứng message đã được xử lý.

Để xác nhận consumer bất đồng bộ, dùng Awaitility hoặc CountDownLatch có timeout. Ví dụ:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                verify(orderService).handle(event));
~~~

Timeout phải đủ cho broker khởi động, topic provision và consumer assignment trong môi trường CI. Khi timeout, log broker, application và binder giúp xác định test thất bại do kết nối, provision, routing hay function.

## 10. Các hành vi cần xác minh theo từng broker

Không chỉ kiểm tra một message đi qua được. Hãy chọn kịch bản phản ánh các semantics mà ứng dụng đang dùng.

### Kafka binder

- Topic được provision với partition count và replication phù hợp.
- Message key được chuyển đúng và cùng key được route nhất quán tới partition theo partitioner.
- Consumer group chia partition giữa các instance như mong đợi.
- Offset được commit theo acknowledgement/auto-commit policy đã cấu hình.
- Khi consumer dừng hoặc khởi động lại, message chưa commit được xử lý lại theo semantics đã chọn.
- Retry, DLT và error handler hoạt động với lỗi chuyển đổi hoặc lỗi xử lý.
- Schema/Serde tương thích giữa producer và consumer.
- Với Kafka Streams, topology chạy qua binder, state store và changelog được khởi tạo; kiểm thử restore/rebalance bằng broker thật khi cần.

Một Kafka container đơn node có thể kiểm tra luồng cơ bản, nhưng không chứng minh replication hoặc khả năng chịu lỗi của cluster nhiều broker. Nếu yêu cầu production phụ thuộc replication factor, ISR hoặc broker failover, cần một test topology phù hợp hơn.

### RabbitMQ binder

- Exchange, queue và binding được khai báo đúng.
- Named consumer group tạo queue dùng chung; anonymous consumer tạo queue tạm theo cấu hình.
- Routing key và pattern binding đưa message tới đúng queue.
- Durable queue và persistent message giữ dữ liệu theo kỳ vọng qua restart.
- Consumer ACK, NACK, reject và requeue có hành vi đúng.
- Retry, DLX/DLQ, TTL và queue expiration hoạt động như cấu hình.
- Publisher confirm và publisher return được xử lý khi ứng dụng cần bảo đảm publish.
- Queue/exchange được tạo sẵn có thuộc tính tương thích với khai báo của binder.

Nếu test chỉ dùng TestRabbitTemplate, message listener có thể được gọi trực tiếp trong JVM; test đó không xác nhận exchange, queue, routing hoặc broker ACK. Với yêu cầu broker semantics, hãy chạy RabbitMQ thật trong container.

### Pulsar binder

- Topic và subscription được tạo với tên, tenant, namespace và partition count đúng.
- Subscription type phù hợp: Exclusive, Failover, Shared hoặc Key_Shared.
- Message key và ordering được bảo toàn theo subscription/partition semantics.
- Ack, negative ack và redelivery hoạt động theo cấu hình.
- Retry letter topic và dead letter topic nhận đúng message sau số lần xử lý thất bại.
- Schema được đăng ký và kiểm tra tương thích theo cấu hình.
- Authentication, authorization và TLS được kiểm tra nếu ứng dụng sử dụng.

Pulsar test container có thể bật transactions hoặc Functions Worker khi test cần các tính năng này. Không giả định một container mặc định đã bật mọi tính năng mở rộng.

## 11. Kiểm thử schema, serialization và message contract

Một message có thể đi qua broker nhưng consumer vẫn không hiểu payload. Vì vậy, contract test nên kiểm tra hợp đồng dữ liệu độc lập với logic xử lý:

- Tên field, kiểu dữ liệu, nullability và default.
- Encoding/decoding với đúng serializer và deserializer.
- Schema version được producer ghi ra và consumer hỗ trợ.
- Header, content type, correlation ID và event ID.
- Quy tắc tương thích khi thêm, xóa hoặc đổi field.
- Hành vi khi nhận message sai schema hoặc payload bị cắt/hỏng.

Nếu dùng Avro/Protobuf và Schema Registry, hãy thêm Registry container hoặc test service tương ứng vào integration suite. Test serializer/deserializer trực tiếp có thể kiểm tra format nhanh; real-broker test xác nhận cấu hình binder và registry endpoint thực sự được dùng.

Không chỉ assert object sau deserialize. Với contract quan trọng, hãy giữ fixture message đã version hóa để kiểm tra backward/forward compatibility theo chính sách của hệ thống.

## 12. Cô lập dữ liệu và tránh test bất định

Message broker xử lý bất đồng bộ và giữ trạng thái giữa các lần test. Nếu dùng lại topic, queue hoặc consumer group mà không dọn đúng cách, test có thể đọc nhầm message cũ hoặc chia sẻ offset với test khác.

Áp dụng các nguyên tắc:

1. Dùng topic, queue, subscription hoặc group riêng cho mỗi test class/test case khi cần isolation.
2. Gắn UUID hoặc test run ID vào tên tài nguyên để tránh đụng nhau khi chạy song song.
3. Chờ bằng Awaitility, latch hoặc API receive có timeout; không dựa vào Thread.sleep() cố định.
4. Đặt auto.offset.reset và group ID rõ ràng trong Kafka probe consumer.
5. Purge queue hoặc xóa tài nguyên sau test khi cần; không xóa queue dùng chung của suite.
6. Đóng producer, consumer, admin client và application context đúng vòng đời.
7. Không assert thứ tự toàn cục giữa các Kafka partition hoặc Rabbit/Pulsar consumer chạy song song nếu hệ thống không bảo đảm thứ tự đó.
8. Giữ event ID ổn định để xác định duplicate khi retry hoặc restart.

Với Kafka, consumer group mới thường cần auto.offset.reset=earliest nếu test gửi record trước khi probe consumer được khởi động. Nếu dùng latest, consumer có thể chỉ đọc record được gửi sau khi nó đã có assignment. Hãy chủ động chọn policy để test không phụ thuộc thời điểm khởi động.

Với RabbitMQ, queue cần được provision trước khi gửi message nếu test muốn xác nhận message được lưu. Message publish trước khi queue được bind có thể không xuất hiện ở queue được tạo sau đó, tùy exchange và cấu hình alternate exchange.

Với Pulsar, hãy kiểm tra subscription initial position và subscription name. Subscription dùng lại có thể tiếp tục từ cursor cũ, làm test nhận dữ liệu từ lần chạy trước.

## 13. Test matrix cho một ứng dụng Spring Cloud Stream

Ma trận dưới đây giúp chọn tầng kiểm thử và bằng chứng cần thu được:

| Kịch bản | Tầng phù hợp | Bằng chứng cần xác nhận |
|---|---|---|
| Tính toán trong Function | Unit test | Output đúng với input và các trường hợp biên. |
| Consumer gọi service | Unit test | Collaborator nhận đúng event và số lần gọi. |
| Supplier tạo event | Unit test | Event có dữ liệu, thời gian và định dạng đúng. |
| Function activation | Test Binder | Đúng function được kích hoạt theo definition. |
| Binding name/destination alias | Test Binder | Message đi vào và ra đúng binding. |
| Payload conversion | Test Binder + contract test | DTO/bytes và content type đúng. |
| Header mapping | Test Binder + real broker nếu phụ thuộc broker | Header nghiệp vụ được đọc/ghi đúng. |
| StreamBridge dynamic binding | Test Binder + real broker | Binding động được tạo và message thực sự tới destination. |
| Kafka partition key | Kafka thật | Key, partition và phân phối record đúng. |
| Kafka consumer group/rebalance | Kafka thật | Assignment, offset và xử lý lại đúng. |
| Kafka Streams transform/join/aggregate | TopologyTestDriver | Kết quả topology và state store đúng. |
| Kafka Streams binder integration | Kafka thật | Binding, topic, application ID, state restore và output đúng. |
| Rabbit exchange/queue/routing | RabbitMQ thật | Message tới đúng queue. |
| Rabbit ACK/NACK/retry/DLQ | RabbitMQ thật | Delivery, requeue và dead-letter đúng. |
| Pulsar subscription/ack/redelivery | Pulsar thật | Subscription cursor, ack và redelivery đúng. |
| Schema Registry hoặc schema broker | Broker + Registry thật | Schema được đăng ký và serialize/deserialize đúng. |
| Broker restart hoặc mất kết nối | Broker thật, có thể cần fault injection | Ứng dụng phục hồi và xử lý message theo semantics đã định. |

## 14. Ví dụ cấu trúc test suite

Một dự án có thể tổ chức test theo package hoặc module:

~~~text
src/test/java/
  function/
    OrderEnricherTest.java
    OrderConsumerTest.java
  binding/
    OrderFunctionBindingTest.java
    FunctionRoutingTest.java
  kafka/
    KafkaBinderIntegrationTest.java
    KafkaStreamsTopologyTest.java
  rabbit/
    RabbitBinderIntegrationTest.java
  pulsar/
    PulsarBinderIntegrationTest.java
~~~

Nếu Test Binder và real binder không thể chạy an toàn trong cùng module do xung đột auto-configuration/classpath, tách thành module test riêng:

~~~text
application/
application-test-binder/
application-broker-integration-tests/
~~~

Module application-test-binder chứa spring-cloud-stream-test-binder. Module application-broker-integration-tests chứa binder thật và Testcontainers modules tương ứng. Cả hai cùng kiểm thử ứng dụng chính hoặc test fixtures chung, nhưng mỗi module có classpath và cấu hình binder rõ ràng.

Không cần tách module nếu dự án đã có cách loại trừ Test Binder auto-configuration đáng tin cậy; điều quan trọng là test phải chứng minh được binder nào đang được dùng.

## 15. Chạy test trong CI

CI cần môi trường có container runtime để chạy Testcontainers. Trước khi chạy integration suite, xác nhận runner có Docker/compatible container runtime và có thể tải image broker.

Một chiến lược pipeline:

| Giai đoạn | Test được chạy | Mục tiêu |
|---|---|---|
| Pull request nhanh | Unit test và Test Binder | Phát hiện lỗi logic, binding và conversion sớm. |
| Pull request hoặc merge | Kafka/Rabbit/Pulsar integration subset | Xác minh binder và broker cho các luồng quan trọng. |
| Nightly hoặc trước release | Full broker suite, restart/retry/DLQ, schema và fault scenarios | Kiểm tra hành vi vận hành và độ tin cậy. |

Tối ưu thời gian bằng cách tái sử dụng container ở phạm vi test class/suite phù hợp, nhưng vẫn tạo tài nguyên logic riêng cho từng test. JUnit Jupiter extension của Testcontainers đã được kiểm thử cho chạy tuần tự; chạy test song song với extension này chưa được hỗ trợ và có thể gây side effect. Nếu bật parallel execution, hãy thiết kế vòng đời container và isolation riêng thay vì mặc định dựa vào `@Testcontainers`. Chỉ bật container reuse trên máy phát triển khi hiểu rõ trạng thái dữ liệu còn tồn tại; CI thường nên bắt đầu từ môi trường sạch để tránh test phụ thuộc dữ liệu cũ.

Khi test thất bại, lưu log của ứng dụng và container broker cùng test report. Với Kafka, log consumer group và topic/partition; với RabbitMQ, log connection, exchange/queue và unacked count; với Pulsar, log topic/subscription và redelivery giúp khoanh vùng nguyên nhân.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test Binder không tìm thấy output | Sai binding name hoặc function chưa được kích hoạt. | Kiểm tra function definition và tên *-out-0. |
| Test Binder nhận payload byte[] thay vì DTO | Test gửi payload thô hoặc content type/converter chưa được cấu hình. | Kiểm tra content type và gửi message theo đúng hợp đồng. |
| Test Binder chạy nhưng broker không nhận message | Test runtime đang chọn binder giả lập. | Tách test module hoặc loại trừ Test Binder auto-configuration và kiểm tra log binder. |
| Kafka test không đọc được record đã gửi | Consumer group bắt đầu ở latest hoặc chưa được assign. | Dùng group riêng, đặt offset reset rõ ràng và chờ assignment. |
| Kafka test đọc message cũ | Topic/group được dùng lại giữa test. | Dùng topic/group riêng hoặc reset offset có kiểm soát. |
| Kafka Streams test không có output | TopologyTestDriver chưa tạo đúng input/output topic hoặc Serde. | Đối chiếu topic name, serializer và deserializer. |
| RabbitMQ test không nhận message | Queue chưa tồn tại hoặc chưa bind đúng exchange/routing key. | Kiểm tra topology broker trước khi publish. |
| RabbitMQ test nhận message trùng | Consumer NACK/requeue hoặc test dùng lại queue. | Kiểm tra acknowledgement mode, retry và cleanup. |
| Pulsar test tiếp tục từ cursor cũ | Dùng lại subscription name. | Tạo subscription riêng hoặc reset theo kịch bản test. |
| Integration test chập chờn | Dùng sleep cố định hoặc broker chưa sẵn sàng. | Dùng readiness check và Awaitility/latch có timeout. |
| Test chạy song song bị nhiễm dữ liệu | Trùng topic, queue, group hoặc subscription. | Thêm test run ID và tài nguyên riêng. |
| CI không khởi động được container | Runner thiếu Docker hoặc không truy cập được image registry. | Kiểm tra container runtime, quyền socket và image pull. |
| Test schema pass cục bộ nhưng fail ở broker | Serializer, Registry URL hoặc schema compatibility khác môi trường. | Kiểm thử Registry và cấu hình binder với container thật. |

Khi điều tra, hãy xác định tầng test trước. Nếu unit test đã fail thì tập trung vào logic; nếu Test Binder fail thì kiểm tra function definition, binding name và conversion; nếu chỉ real broker test fail thì kiểm tra connection, provisioner, broker topology, group/subscription, serializer và acknowledgement.

## 17. Checklist trước khi triển khai

- [ ] Function và business rules có unit test độc lập.
- [ ] Supplier, Function và Consumer được kiểm tra với dữ liệu biên.
- [ ] Consumer side effect được xác nhận qua collaborator.
- [ ] Test Binder được dùng để kiểm tra function activation và binding.
- [ ] InputDestination/OutputDestination dùng đúng binding name hoặc destination alias.
- [ ] Payload conversion, content type và header quan trọng được kiểm tra.
- [ ] Đã hiểu Test Binder là in-JVM broker và không chứng minh broker semantics.
- [ ] Test Binder không vô tình thay thế real binder trong integration suite.
- [ ] Kafka Streams topology có test bằng TopologyTestDriver khi phù hợp.
- [ ] Real binder integration test chạy với Kafka, RabbitMQ hoặc Pulsar container.
- [ ] Broker image được pin theo phiên bản tương thích production.
- [ ] Test dùng topic, queue, group hoặc subscription riêng để cô lập dữ liệu.
- [ ] Có timeout và cơ chế chờ bất đồng bộ xác định.
- [ ] Đã kiểm tra partition, group/subscription, ACK, retry và DLQ theo broker đang dùng.
- [ ] Schema/Serde được kiểm tra với serializer và Registry thực tế nếu có.
- [ ] CI có container runtime và lưu log khi integration test thất bại.

Kiểm thử Spring Cloud Stream nên đi từ hàm đến binding rồi tới broker thực. Unit test giúp xác nhận logic nhanh; Spring Integration Test Binder kiểm tra function, binding, conversion và luồng message trong JVM; Testcontainers cùng binder thật xác minh protocol, destination, group/subscription, partition, acknowledgement, retry và dead-letter. Với Kafka Streams, TopologyTestDriver kiểm tra topology nhanh, còn integration test với Kafka xác nhận phần kết nối và vận hành. Phân tầng đúng giúp phát hiện lỗi ở đúng ranh giới, giữ test suite nhanh và vẫn có bằng chứng đáng tin cậy trước khi triển khai.

## Tài liệu tham khảo

- [Spring Cloud Stream — Testing with Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring for Apache Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Apache Kafka — TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html)
- [Spring AMQP — Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html)
- [Spring for Apache Pulsar — Testing Applications](https://docs.spring.io/spring-pulsar/reference/reference/testing-applications.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/)
- [Testcontainers — Apache Pulsar Module](https://java.testcontainers.org/modules/pulsar/)
- [Spring Cloud Stream — Kafka Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/binder-properties.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
