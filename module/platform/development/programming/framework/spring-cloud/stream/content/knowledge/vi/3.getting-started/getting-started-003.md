# Chọn thư viện lõi, binder và thư viện kiểm thử

Khi khởi tạo một ứng dụng Spring Cloud Stream, cần chọn đúng ba nhóm phụ thuộc: thư viện nền tảng của ứng dụng, binder kết nối tới broker và thư viện phục vụ kiểm thử. Việc chọn dependency cần bắt đầu từ mô hình xử lý sự kiện và broker đích, sau đó mới quyết định phiên bản và công cụ kiểm thử.

Spring Cloud Stream cung cấp mô hình hàm `Supplier`, `Function`, `Consumer` cùng cơ chế binding. Binder hiện thực việc kết nối binding với Kafka, RabbitMQ, Pulsar hoặc một hệ thống nhắn tin khác. Thư viện kiểm thử lại có mục tiêu riêng: kiểm tra logic hàm, kiểm tra binding trong bộ nhớ và xác minh hành vi thật của broker. Một dependency không thay thế được tất cả các lớp này.

## 1. Phân chia dependency theo trách nhiệm

Một ứng dụng thường có các lớp phụ thuộc sau:

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Spring Boot và Spring Cloud | Nền tảng ứng dụng, quản lý cấu hình và tương thích phiên bản | Spring Boot, Spring Cloud release train |
| Spring Cloud Stream core | Mô hình hàm, binding, message và binder abstraction | `spring-cloud-stream` |
| Broker binder | Kết nối binding với broker cụ thể | Kafka binder, Rabbit binder, Pulsar binder |
| Xử lý luồng chuyên biệt | Xây dựng topology và trạng thái trên Kafka | Kafka Streams binder |
| Kiểm thử ứng dụng | JUnit, Mockito, AssertJ và Spring Test | `spring-boot-starter-test` |
| Kiểm thử binding | Binder giả lập trong bộ nhớ | `spring-cloud-stream-test-binder` |
| Kiểm thử broker thật | Khởi tạo broker cô lập cho integration test | Testcontainers Kafka, RabbitMQ hoặc Pulsar |

Trong đa số ứng dụng, binder starter đã kéo theo Spring Cloud Stream core dưới dạng dependency bắc cầu. Có thể khai báo core trực tiếp nếu mã ứng dụng cần phụ thuộc rõ ràng vào API của core, nhưng không nên thêm nhiều starter chỉ để có các lớp đã được kéo theo.

Cần phân biệt ba khái niệm:

- **Core** định nghĩa cách ứng dụng khai báo và xử lý message.
- **Binder** kết nối binding với broker và ánh xạ các cấu hình chung sang ngữ nghĩa broker.
- **Test Binder** thay broker bằng môi trường trong bộ nhớ để kiểm tra luồng message ở cấp ứng dụng.

## 2. Chọn phiên bản Spring Boot và Spring Cloud trước

Spring Boot và Spring Cloud được phát hành theo các dòng phiên bản có ma trận tương thích. Một binder có thể biên dịch được nhưng vẫn không tương thích với phiên bản Spring Boot, Spring Framework hoặc Spring Cloud Stream mà ứng dụng đang sử dụng.

Với Maven, nên import Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. BOM quản lý phiên bản cho các module thuộc release train, giúp tránh khai báo một phiên bản riêng cho từng binder:

```xml
<properties>
    <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Giá trị `SPRING_CLOUD_RELEASE_TRAIN` là placeholder để thay bằng release train được công bố tương thích với phiên bản Spring Boot của dự án. Không sao chép một con số phiên bản từ hướng dẫn cũ mà chưa kiểm tra ma trận tương thích hiện hành.

Một số nguyên tắc khi quản lý phiên bản:

1. Chọn phiên bản Spring Boot theo nền tảng đang dùng.
2. Tra ma trận tương thích Spring Cloud và chọn release train tương ứng.
3. Để BOM quản lý phiên bản Spring Cloud Stream và binder thuộc release train.
4. Kiểm tra tài liệu của binder bên ngoài release train, đặc biệt với Pulsar hoặc binder do bên thứ ba duy trì.
5. Chỉ override phiên bản thư viện Kafka, RabbitMQ, Pulsar hoặc Spring khi có lý do rõ ràng và đã kiểm tra tương thích.

Không nên ghép tùy ý một binder mới với Spring Cloud Stream cũ. Khi nâng cấp, cần xem lại dependency tree để phát hiện các phiên bản Spring Cloud Stream hoặc client broker bị kéo vào ngoài dự kiến.

## 3. Chọn thư viện lõi theo mô hình ứng dụng

Nếu ứng dụng dùng mô hình hàm của Spring Cloud Stream, binder starter thường là dependency chính cần khai báo. Ví dụ, một hàm nhận sự kiện và cập nhật trạng thái đơn hàng có thể được viết như sau:

```java
@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderCreated> recordOrder(OrderService orderService) {
        return event -> orderService.record(event);
    }
}
```

Hàm nghiệp vụ không cần import API Kafka hoặc RabbitMQ. Binding và binder sẽ đảm nhiệm việc nhận message từ broker.

Nếu chỉ cần gửi và nhận message theo mô hình hàm, Spring Cloud Stream core cùng một binder là đủ. Nếu cần tích hợp trực tiếp với Kafka, có thể chọn Spring for Apache Kafka (`spring-kafka`) với `KafkaTemplate` và `@KafkaListener`. Nếu cần tích hợp trực tiếp với RabbitMQ/AMQP, Spring AMQP (`spring-rabbit`) cung cấp `RabbitTemplate` và `@RabbitListener`.

Không nên thêm Spring Cloud Stream, Spring for Apache Kafka và Spring AMQP cùng lúc theo thói quen. Chỉ thêm API trực tiếp khi ứng dụng thực sự sử dụng chúng, ví dụ cần một thành phần quản trị Kafka chuyên biệt bên cạnh các hàm Cloud Stream. Việc có nhiều abstraction cho cùng một luồng dữ liệu làm tăng số cấu hình, listener và cách xử lý lỗi cần vận hành.

## 4. Chọn binder theo broker và kiểu xử lý

### Kafka message binder

Với ứng dụng dùng Kafka như một broker message thông thường, có thể dùng starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
```

Starter này cung cấp Kafka binder cho Spring Cloud Stream. Ứng dụng cấu hình destination thành topic và group thành consumer group. Binder xử lý việc tạo producer/consumer, chuyển đổi message và ánh xạ cấu hình binding sang các thuộc tính Kafka.

Chọn Kafka binder khi ứng dụng cần nhận hoặc phát sự kiện theo mô hình message, dùng topic, partition, consumer group và offset do Kafka quản lý. Không cần thêm Kafka Streams binder nếu chỉ xử lý từng message bằng `Consumer` hoặc `Function` thông thường.

### RabbitMQ binder

Với RabbitMQ, dùng starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
</dependency>
```

Rabbit binder kết nối binding với exchange và queue. Các cấu hình như destination, group, durable subscription, partitioning và dead-letter cần được đọc theo tài liệu của Rabbit binder vì chúng được ánh xạ sang mô hình AMQP.

Chọn Rabbit binder khi ứng dụng cần mô hình hàng đợi và định tuyến qua exchange, routing key, queue. Không nên suy luận rằng mọi thuộc tính Kafka đều có tương đương một-một trong Rabbit binder.

### Pulsar binder

Nếu hệ thống dùng Apache Pulsar, cần chọn một Spring Cloud Stream binder tương thích với phiên bản Spring Cloud Stream và Pulsar client đang dùng. Một số bản phân phối cung cấp artifact có tên `spring-cloud-stream-binder-pulsar`; cần xác minh groupId, phiên bản, trạng thái duy trì và ma trận tương thích theo tài liệu của chính binder đó trước khi thêm vào dự án.

Không nhầm `spring-boot-starter-pulsar` với Spring Cloud Stream Pulsar binder. Starter của Spring Boot cung cấp tích hợp Pulsar ở cấp Spring Boot/Spring Pulsar; nó không tự đăng ký một binder cho các binding của Spring Cloud Stream. Nếu ứng dụng chọn API Spring Pulsar trực tiếp, đó là một lựa chọn tích hợp khác với mô hình binder.

Khi đánh giá Pulsar binder, cần kiểm tra các tính năng quan trọng có được hỗ trợ trong phiên bản đó hay không: subscription type, consumer group semantics, partitioned topic, schema, retry, dead-letter, acknowledgement, transaction và health indicator. Không giả định rằng mọi tính năng chung của Spring Cloud Stream đã được binder triển khai giống nhau.

### Kafka Streams binder

Kafka Streams binder dành cho ứng dụng xử lý luồng có trạng thái bằng `KStream` và `KTable`, chẳng hạn tổng hợp, join hoặc window. Artifact được dùng là:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
```

Đây là binder chuyên biệt, khác với Kafka message binder. Nếu ứng dụng chỉ có hàm `Consumer<OrderCreated>`, Kafka message binder thường phù hợp hơn. Nếu ứng dụng cần topology Kafka Streams và state store, chọn Kafka Streams binder. Chỉ đưa cả hai vào classpath khi một ứng dụng thật sự có nhu cầu dùng cả hai mô hình và đã cấu hình rõ binding, function definition cùng tài nguyên Kafka.

## 5. Ma trận chọn dependency

| Nhu cầu | Dependency chính | Ghi chú |
|---|---|---|
| Hàm nhận/gửi message qua Kafka | `spring-cloud-starter-stream-kafka` | Kafka message binder |
| Hàm nhận/gửi message qua RabbitMQ | `spring-cloud-starter-stream-rabbit` | Rabbit binder |
| Hàm nhận/gửi message qua Pulsar | Pulsar binder tương thích | Xác minh artifact và ma trận phiên bản của binder |
| Xử lý stateful stream trên Kafka | `spring-cloud-stream-binder-kafka-streams` | Dùng KStream/KTable và topology |
| Dùng API Kafka trực tiếp | `spring-kafka` hoặc starter Spring Boot tương ứng | Không phải binder Cloud Stream |
| Dùng API AMQP trực tiếp | `spring-rabbit` hoặc starter Spring Boot tương ứng | Không phải binder Cloud Stream |
| Dùng API Pulsar trực tiếp | Spring Pulsar / starter tương ứng | Không tự cung cấp Cloud Stream binder |

Một dịch vụ xử lý sự kiện thông thường nên có một binder chính. Nhiều binder chỉ hợp lý khi dịch vụ cần kết nối nhiều hệ thống nhắn tin, chuyển tiếp giữa broker hoặc di chuyển dữ liệu. Khi đó, phải cấu hình rõ binder mặc định, binder được gắn với từng binding, tên destination, group và các thuộc tính riêng của từng broker.

## 6. Chọn thư viện kiểm thử theo tầng

Không có một thư viện kiểm thử nào chứng minh được toàn bộ hành vi của ứng dụng event-driven. Nên dùng các lớp kiểm thử bổ sung cho nhau.

### Kiểm thử logic hàm

Dùng JUnit 5, Mockito và AssertJ thông qua dependency test của Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Có thể gọi trực tiếp hàm `Consumer` hoặc `Function` trong unit test, truyền dữ liệu đầu vào và xác minh lời gọi service hoặc kết quả trả về. Kiểu kiểm thử này chạy nhanh và giúp kiểm tra quy tắc nghiệp vụ, xử lý dữ liệu không hợp lệ, idempotency và các trường hợp lỗi.

Ví dụ:

```java
class OrderFunctionsTest {

    @Test
    void recordsCreatedOrder() {
        OrderService service = mock(OrderService.class);
        OrderFunctions functions = new OrderFunctions();

        Consumer<OrderCreated> consumer =
            functions.recordOrder(service);

        OrderCreated event = new OrderCreated("order-42");

        consumer.accept(event);

        verify(service).record(event);
    }
}
```

Unit test không cần khởi động Spring context hoặc broker nếu mục tiêu chỉ là xác minh logic của hàm.

### Kiểm thử binding trong bộ nhớ

Thêm Spring Cloud Stream Test Binder trong phạm vi test:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
```

Test Binder cung cấp `InputDestination` và `OutputDestination` để gửi/nhận message trong bộ nhớ. Nó phù hợp để kiểm tra function definition, tên binding, chuyển đổi message và luồng xử lý ở cấp ứng dụng mà không cần khởi chạy Kafka hay RabbitMQ.

Ví dụ với hàm chuyển nội dung thành chữ hoa:

```java
@SpringBootTest(properties = {
    "spring.cloud.function.definition=uppercase"
})
class UppercaseBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void sendsMessageThroughFunction() {
        input.send(
            new GenericMessage<>("hello".getBytes(StandardCharsets.UTF_8)),
            "uppercase-in-0"
        );

        Message<byte[]> result =
            output.receive(1000, "uppercase-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(), StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }
}
```

Ví dụ minh họa giả định ứng dụng có bean `Function<String, String> uppercase()` và cấu hình binding đầu ra `uppercase-out-0`. Trong dự án thực tế, kiểu payload, content type và message converter phải nhất quán với hàm đang kiểm thử.

Test Binder không khởi động broker thật. Nó không xác minh partition assignment, offset commit, consumer rebalance, exchange routing, acknowledgement, transaction, broker retry, DLQ, bảo mật hoặc khả năng tương thích của serializer với broker. Không dùng kết quả Test Binder để kết luận rằng cấu hình Kafka/RabbitMQ/Pulsar production đã đúng.

### Kiểm thử tích hợp với broker thật

Dùng Testcontainers hoặc môi trường broker dùng riêng cho kiểm thử khi cần xác minh hành vi phụ thuộc broker. Có thể khởi chạy container Kafka, RabbitMQ hoặc Pulsar trong vòng đời integration test, cấu hình ứng dụng kết nối tới địa chỉ broker được container cung cấp rồi gửi và nhận message như khi triển khai thật.

Các module Testcontainers thường được dùng gồm:

- Kafka: module `org.testcontainers:kafka`.
- RabbitMQ: module `org.testcontainers:rabbitmq`.
- Pulsar: module `org.testcontainers:pulsar`.

Tên artifact và package Java có thể thay đổi giữa các phiên bản Testcontainers; dùng BOM hoặc hướng dẫn của phiên bản đã chọn để đồng bộ chúng. Không tự thêm phiên bản ngẫu nhiên cho từng module.

Integration test nên kiểm tra các hành vi quan trọng với hệ thống: tạo topic/queue hoặc binding, serialization/deserialization, key và partition, consumer group, acknowledgement, retry, DLQ, cấu hình bảo mật và xử lý khi broker tạm thời không sẵn sàng. Không phải mọi bài test đều cần bao phủ tất cả các hành vi; chọn những hành vi mà ứng dụng thực sự cấu hình hoặc phụ thuộc.

### Thư viện kiểm thử chuyên biệt

Một số tích hợp có công cụ riêng:

| Thành phần | Thư viện kiểm thử | Mục tiêu |
|---|---|---|
| Spring for Apache Kafka | `spring-kafka-test` | Công cụ kiểm thử listener và Kafka; có thể dùng embedded broker tùy phiên bản |
| Kafka Streams | `kafka-streams-test-utils` | `TopologyTestDriver` để kiểm tra topology và state store |
| Spring AMQP | `spring-rabbit-test` | Test harness và công cụ hỗ trợ kiểm thử listener |
| Spring Cloud Stream | `spring-cloud-stream-test-binder` | Kiểm thử binding trong bộ nhớ |
| Spring Boot | `spring-boot-starter-test` | JUnit, Mockito, AssertJ và Spring Test |

Các thư viện chuyên biệt chỉ cần thiết khi ứng dụng sử dụng đúng tích hợp tương ứng. Ví dụ, không cần thêm `spring-kafka-test` chỉ vì ứng dụng có Kafka binder; nếu chỉ kiểm tra function và binding, Test Binder có thể đủ cho tầng đó. Nếu cần kiểm tra topology Kafka Streams, `TopologyTestDriver` là công cụ phù hợp hơn một bài unit test gọi trực tiếp hàm nghiệp vụ.

## 7. Ví dụ cấu hình Maven cho một ứng dụng Kafka

Ví dụ sau minh họa một dịch vụ dùng Kafka message binder và hai lớp kiểm thử: Spring Boot Test cùng Spring Cloud Stream Test Binder.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-test-binder</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

BOM Spring Cloud được khai báo trong `dependencyManagement` ở phần trước. Nhờ đó, không cần gắn phiên bản riêng vào các dependency thuộc release train.

Nếu dự án cần kiểm thử với Kafka thật, có thể bổ sung module Testcontainers Kafka trong scope test và quản lý phiên bản Testcontainers bằng BOM phù hợp. Khi dùng RabbitMQ hoặc Pulsar, thay module container theo broker tương ứng. Không cần đóng gói Testcontainers vào artifact production.

Một cấu hình test nên giữ các dependency kiểm thử ở scope `test`, để thư viện giả lập và container không bị đưa vào classpath runtime của ứng dụng triển khai.

## 8. Kiểm tra dependency tree và tránh xung đột

Sau khi thêm dependency, kiểm tra dependency tree để biết binder đã kéo theo phiên bản core, Spring Kafka, Kafka client, Spring AMQP hoặc Pulsar client nào. Với Maven có thể chạy:

```bash
mvn dependency:tree
```

Tập trung kiểm tra:

- Chỉ có release train và phiên bản Spring Cloud Stream dự kiến.
- Binder đúng với broker và mô hình xử lý.
- Không có hai phiên bản khác nhau của cùng Spring Framework hoặc client broker do override không chủ ý.
- Thư viện test nằm trong scope test.
- Không đóng gói Test Binder hoặc Testcontainers vào runtime.
- Các module chuyên biệt như Kafka Streams binder và `kafka-streams-test-utils` có phiên bản tương thích.

Nếu Maven báo lỗi phân giải dependency hoặc ứng dụng khởi động với lỗi `NoSuchMethodError`, `ClassNotFoundException` hay `NoClassDefFoundError`, hãy kiểm tra BOM và dependency tree trước khi thêm thủ công một phiên bản khác. Những lỗi này thường cho thấy classpath không đồng bộ hoặc một thư viện không tương thích.

## 9. Quy trình lựa chọn thực tế

Có thể dùng trình tự sau khi tạo một dịch vụ mới:

1. Xác định ứng dụng cần API hàm của Spring Cloud Stream hay API trực tiếp của Kafka, AMQP hoặc Pulsar.
2. Chọn phiên bản Spring Boot, sau đó chọn Spring Cloud release train tương thích.
3. Chọn đúng một binder theo broker và kiểu xử lý; với Kafka Streams, chọn Kafka Streams binder thay cho Kafka message binder nếu topology có trạng thái là yêu cầu chính.
4. Thêm `spring-boot-starter-test` để kiểm thử logic và Spring context.
5. Thêm `spring-cloud-stream-test-binder` để kiểm tra binding trong bộ nhớ.
6. Bổ sung Testcontainers hoặc thư viện test chuyên biệt khi cần xác minh hành vi broker.
7. Kiểm tra dependency tree và chạy các bài test đại diện trước khi triển khai.

Ví dụ, dịch vụ chỉ nhận sự kiện đơn hàng từ Kafka thường cần Kafka binder, Spring Boot Test và Test Binder. Nếu yêu cầu kiểm chứng offset, partition hoặc retry topic, bổ sung integration test với Kafka thật. Nếu dịch vụ tổng hợp đơn hàng theo khách hàng bằng cửa sổ thời gian và state store, dùng Kafka Streams binder và kiểm tra topology bằng `TopologyTestDriver`.

Chọn đúng thư viện ngay từ đầu giúp mã nghiệp vụ tập trung vào sự kiện, binder chịu trách nhiệm kết nối broker, còn bộ kiểm thử xác minh từng lớp theo đúng phạm vi. Trước khi nâng cấp phiên bản hoặc đổi broker, hãy kiểm tra lại tương thích binder, ngữ nghĩa giao nhận và các bài integration test đang bảo vệ hệ thống.

