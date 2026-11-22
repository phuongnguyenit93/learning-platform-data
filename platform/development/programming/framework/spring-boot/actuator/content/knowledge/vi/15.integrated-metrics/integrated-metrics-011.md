# Nhận diện metrics Kafka, RabbitMQ và thư viện tích hợp theo dependency

## 1. Vì sao hai ứng dụng cùng có Actuator lại hiện các số đo khác nhau?

Một ứng dụng chỉ phục vụ HTTP và một ứng dụng nhận bản tin Kafka có thể cùng dùng Spring Boot Actuator, nhưng danh sách số đo (metrics) của chúng không giống nhau. Actuator cung cấp cơ chế quan sát; những thành phần thực sự có trong ứng dụng mới quyết định các nguồn dữ liệu để quan sát.

**Phụ thuộc thư viện (dependency)** là điểm khởi đầu để dự đoán khả năng đo, không phải bằng chứng rằng mọi số đo của thư viện đã tồn tại hoặc có lưu lượng. Ví dụ, thêm Spring Kafka có thể tạo `KafkaTemplate` trong Spring context. Producer thực tế vẫn có thể chưa được tạo nếu ứng dụng chưa gửi bản tin nào.

Để nhận diện một số đo tích hợp, cần nối được chuỗi sau:

```text
Thư viện có trên classpath
        ↓
Điều kiện cấu hình tự động được thỏa mãn
        ↓
Bean hoặc tài nguyên thực tế được tạo
        ↓
Bộ kết nối số đo được gắn vào đúng đối tượng
        ↓
Meter được đăng ký, có thể trước hoặc sau thao tác đầu tiên
        ↓
Thao tác thực tế làm thay đổi số đo
        ↓
Registry xuất dữ liệu qua endpoint hoặc hệ thống giám sát
```

Có thể thất bại ở bất kỳ mắt xích nào. Vì vậy, “không thấy số đo” không tự động có nghĩa là thiếu thư viện, và “thấy tên số đo” không tự động chứng minh bản tin đã được xử lý.

Bài này dùng Spring Boot **3.3.x**, Spring Kafka **3.2.x**, Spring AMQP **3.1.x** và Micrometer **1.13.x** làm ngữ cảnh. Ví dụ Java dùng cú pháp Java 17 trở lên; dự án minh họa chọn JDK 21. Khi làm việc với dự án thực tế, đọc phiên bản đã được giải quyết trong cây phụ thuộc thay vì lấy tài liệu của phiên bản mới nhất để suy ngược hành vi cũ.

## 2. Tách ba lớp quan sát trước khi nhìn tên meter

Một hệ thống nhắn tin có ít nhất ba nơi cung cấp thông tin:

| Lớp | Đối tượng đang được đo | Câu hỏi thường trả lời |
| --- | --- | --- |
| Client trong JVM | Kafka producer/consumer hoặc RabbitMQ Java client | Client gửi/nhận bao nhiêu, có retry/lỗi không, có bao nhiêu kết nối/kênh? |
| Tích hợp của Spring | Template, listener container, thành phần của luồng tích hợp | Một thao tác gửi hoặc một lần gọi bộ xử lý mất bao lâu, thành công hay thất bại? |
| Broker/hạ tầng | Kafka broker, RabbitMQ node/queue và cụm | Bản sao phân vùng có khỏe không, hàng đợi còn bao nhiêu bản tin, broker có thiếu tài nguyên không? |

Các số đo client và Spring được thu thập trong tiến trình ứng dụng. Số đo broker cần nguồn thu thập từ broker hoặc một công cụ theo dõi tương ứng. Việc thêm thư viện Kafka/RabbitMQ vào ứng dụng không biến `/actuator/metrics` thành bảng thống kê đầy đủ của cụm bên ngoài.

Ví dụ, “consumer đã lấy bản ghi khỏi Kafka”, “phương thức listener đã chạy xong” và “nghiệp vụ đã lưu dữ liệu thành công” là ba sự kiện có thể khác nhau. Thời gian của một timer phải được hiểu theo đúng đoạn xử lý mà nó bao quanh.

### Các nhóm tên thường gặp

| Nhóm tên Micrometer | Nguồn thường gặp | Cách hiểu ban đầu |
| --- | --- | --- |
| `kafka.producer.*` | Kafka producer client | Số đo gốc của producer được đưa vào registry |
| `kafka.consumer.*` | Kafka consumer client | Số đo gốc của consumer, tùy client và phân vùng được gán |
| `kafka.stream.*` | Kafka Streams | Hoạt động client/luồng/tác vụ Streams, khi thực sự có Streams runtime |
| `spring.kafka.template` | Spring Kafka | Timer của thao tác qua `KafkaTemplate` |
| `spring.kafka.listener` | Spring Kafka | Timer của lần gọi listener |
| `rabbitmq.*` | RabbitMQ Java client | Số đo kết nối, kênh và thao tác bản tin phía client |
| `spring.rabbitmq.listener` | Spring AMQP, cơ chế timer trước Observation | Thời gian gọi listener, với nhãn kết quả/lỗi của cơ chế này |
| `spring.rabbit.listener`, `spring.rabbit.template` | Spring AMQP Observation | Timer do cơ chế Observation tạo, với quy ước nhãn tương ứng |
| `spring.integration.*` | Spring Integration | Số đo các channel, handler, source hoặc observation của luồng tích hợp |

Dấu `*` ở đây mô tả **nhóm tên**, không phải một meter tên nguyên văn có ký tự `*`. Danh sách thực tế phụ thuộc phiên bản, tài nguyên đã tạo và cấu hình đo.

## 3. Kafka: nhận diện đúng số đo client và số đo Spring

### 3.1. Phụ thuộc nào mở ra khả năng tích hợp?

Trong dự án được Spring Boot quản lý phiên bản, hai phụ thuộc chính cho thí nghiệm Kafka là:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'org.springframework.kafka:spring-kafka'
```

Spring Kafka kéo theo Kafka Java client thông qua các phụ thuộc của nó. Nếu chỉ thêm `org.apache.kafka:kafka-clients`, ứng dụng có thể tự tạo producer/consumer Java, nhưng chưa có nghĩa Boot đã tạo `KafkaTemplate` và các factory của Spring Kafka.

Với factory producer/consumer do Boot tự cấu hình, Boot gắn `MicrometerProducerListener` và `MicrometerConsumerListener`. Các listener này nối số đo của client vào `MeterRegistry` theo vòng đời tạo/đóng client. Boot cũng có tích hợp `KafkaStreamsMicrometerListener` cho `StreamsBuilderFactoryBean` khi các điều kiện tương ứng được đáp ứng. [Cấu hình Kafka metrics của Boot 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/KafkaMetricsAutoConfiguration.java).

Điểm cần kiểm tra là **factory có listener đo** và **client đã được tạo**. Một `ProducerFactory` tồn tại chưa đủ để kết luận producer đã gửi bản tin. Tương tự, có cấu hình consumer chưa đủ để kết luận container đang chạy và đã được gán phân vùng.

Kafka Streams là một khả năng riêng: thêm Spring Kafka không tự tạo topology, tác vụ xử lý hay state store. Chỉ tìm các meter Streams khi ứng dụng thực sự có thư viện và cấu hình Streams tương ứng.

### 3.2. Cách nhận diện một số meter gốc

Micrometer ánh xạ tên nhóm và tên số đo của Kafka thành tên dạng chấm. Ví dụ, nhóm `producer-metrics` với `record-send-total` có thể trở thành `kafka.producer.record.send.total`. Những nhãn của Kafka như `client-id` được chuyển sang dạng `client.id`; listener của Spring có thể thêm nhãn `spring.id`. [Bộ ánh xạ KafkaMetrics của Micrometer 1.13](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/kafka/KafkaMetrics.java).

| Tên Micrometer thường gặp | Ý nghĩa cần nhận diện |
| --- | --- |
| `kafka.producer.record.send.total` | Tổng số bản ghi đã gửi theo thống kê producer |
| `kafka.producer.record.error.total` | Số lỗi gửi bản ghi theo producer |
| `kafka.producer.record.retry.total` | Số lần gửi lại theo producer |
| `kafka.consumer.fetch.manager.records.consumed.total` | Số bản ghi được consumer lấy về theo bộ thống kê fetch |
| `kafka.consumer.fetch.manager.records.lag.max` | Giá trị độ trễ theo số bản ghi được consumer báo cáo |

Đây là các tên để **định hướng tìm kiếm**, không phải cam kết mọi client luôn có đủ các chuỗi ngay lúc khởi động. Số đo theo topic/partition có thể chỉ xuất hiện khi client có những tài nguyên hoặc hoạt động tương ứng.

Riêng `records-lag-max` của Kafka client dựa trên vị trí hiện tại của consumer, không phải mặc nhiên dựa trên offset đã commit. Do đó, nó không đồng nghĩa với toàn bộ lượng nghiệp vụ chưa hoàn thành hoặc độ trễ commit của cả consumer group. Muốn theo dõi độ trễ của group trên toàn cụm phải xác định nguồn và định nghĩa phép đo phù hợp. [Tài liệu giám sát Kafka 3.7](https://kafka.apache.org/37/operations/monitoring/#consumer-fetch-metrics).

### 3.3. Timer của Spring Kafka là lớp khác

`spring.kafka.template` đo thao tác gửi qua `KafkaTemplate`; `spring.kafka.listener` đo lần gọi listener. Ở cơ chế timer truyền thống, các nhãn thường có `name`, `result` và `exception`. Với listener đồng thời, tên có thể phân biệt các luồng xử lý. [Hướng dẫn monitoring của Spring Kafka 3.2](https://docs.spring.io/spring-kafka/reference/3.2/kafka/micrometer.html).

Một timer vừa có số lần được ghi nhận (`COUNT`), vừa có tổng thời gian (`TOTAL_TIME`), và có thể có giá trị cực đại (`MAX`). Vì vậy:

- Tên `spring.kafka.template` có trong registry nhưng `COUNT = 0` không chứng minh đã gửi bản tin.
- `COUNT` của listener không phải số bản tin nghiệp vụ duy nhất nếu có xử lý lại, lỗi hoặc batching.
- Số bản ghi consumer lấy về có thể khác số lần listener hoàn tất; đừng ép hai bộ đếm phải luôn bằng nhau.
- Độ trễ của template không đo toàn bộ thời gian từ lúc gửi đến lúc bên nhận hoàn tất nghiệp vụ.

Không cần tự thêm `@Timed` lên mọi listener chỉ để lặp lại khả năng đo sẵn có. Nếu đo thêm một giai đoạn nghiệp vụ riêng, đặt tên và phạm vi riêng để phân biệt với timer của framework.

### 3.4. Khi ứng dụng tự tạo factory hoặc client

Bean do ứng dụng tự tạo có thể làm cấu hình tự động của Boot lùi lại. Khi đó, không được mặc định các bước tùy biến của Boot đã chạy trên factory của mình.

Ví dụ dưới đây là **phương thức trong một lớp cấu hình**, dùng khi chủ động sở hữu factory producer. Nó không phải chương trình độc lập và không cần thêm vào thí nghiệm chỉ dùng factory tự động:

```java
import java.util.HashMap;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.MicrometerProducerListener;

@Bean
DefaultKafkaProducerFactory<String, String> producerFactory(MeterRegistry registry) {
    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "127.0.0.1:9092");
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    var factory = new DefaultKafkaProducerFactory<String, String>(properties);
    factory.addListener(new MicrometerProducerListener<>(registry));
    return factory;
}
```

Địa chỉ trên là broker của môi trường thí nghiệm; không phải broker được tạo bởi đoạn cấu hình. Đây cũng chưa phải cấu hình hoàn chỉnh cho xác thực, giao dịch hoặc vận hành production. Consumer factory có listener tương ứng là `MicrometerConsumerListener`.

Nếu đã dùng factory được Boot cấu hình và đã có listener đo, không thêm một đường đăng ký thứ hai chỉ vì chưa nhìn thấy số liệu. Với raw `KafkaProducer`/`KafkaConsumer` ngoài các factory của Spring, phải quản lý riêng việc gắn và đóng `KafkaClientMetrics`; một đối tượng được tạo bằng `new` không tự trở thành tài nguyên được Boot theo dõi.

## 4. RabbitMQ: số đo của Java client và số đo listener

### 4.1. Điều kiện phụ thuộc và cấu hình

Đối với tích hợp AMQP của Spring Boot, dùng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'org.springframework.boot:spring-boot-starter-amqp'
```

Starter AMQP đưa vào Spring Rabbit và RabbitMQ Java client. Boot có thể cấu hình connection factory và `RabbitTemplate` theo các thuộc tính `spring.rabbitmq.*`. Một template tồn tại chưa xác nhận đã có kết nối đến broker hoặc đã gửi thành công bản tin. [Tích hợp AMQP trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/messaging/amqp.html).

Boot hỗ trợ đo RabbitMQ connection factory; nhóm số đo client dùng tiền tố `rabbitmq`. Cần kiểm tra factory thực tế đang được quản lý và các collector/tùy biến hiện có, đặc biệt nếu ứng dụng tự tạo factory hoặc dùng nhiều factory. [RabbitMQ metrics trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.rabbitmq).

### 4.2. Nhận diện số đo client

Các số đo thông dụng của RabbitMQ Java client gồm:

| Tên Micrometer | Loại thường gặp | Phạm vi |
| --- | --- | --- |
| `rabbitmq.connections` | Gauge | Số kết nối mà collector phía client theo dõi |
| `rabbitmq.channels` | Gauge | Số kênh mà collector phía client theo dõi |
| `rabbitmq.published` | Counter | Hoạt động publish được collector ghi nhận |
| `rabbitmq.consumed` | Counter | Hoạt động nhận bản tin được collector ghi nhận |
| `rabbitmq.acknowledged` | Counter | Thao tác xác nhận nhận bản tin theo collector |
| `rabbitmq.rejected` | Counter | Thao tác từ chối bản tin theo collector |

Danh sách và các số đo chi tiết hơn phụ thuộc phiên bản Java client. Tên `rabbitmq` chỉ là tiền tố của một họ meter, không phải một số đo duy nhất gom mọi thông tin. [Triển khai MicrometerMetricsCollector của RabbitMQ Java client](https://github.com/rabbitmq/rabbitmq-java-client/blob/main/src/main/java/com/rabbitmq/client/impl/MicrometerMetricsCollector.java).

Phải phân biệt các ý nghĩa sau:

- Publish được client ghi nhận không tự chứng minh bản tin đã được định tuyến vào đúng queue hoặc đã được bên nhận xử lý.
- Publisher confirm là một cơ chế khác với consumer acknowledgement.
- Bộ đếm acknowledgement phụ thuộc chế độ xác nhận và đường xử lý thực tế; không mặc định mọi lần consume đều làm nó tăng tương ứng.
- Số kết nối/kênh tại một thời điểm là gauge, không phải tổng số kết nối từng được tạo từ khi ứng dụng chạy.

Để kết luận “đơn hàng đã hoàn tất”, cần bằng chứng nghiệp vụ tương ứng. Bộ đếm của thư viện chỉ chứng minh sự kiện mà thư viện định nghĩa và thu thập.

### 4.3. Timer listener và giới hạn của dữ liệu client

Ở cơ chế timer truyền thống của Spring AMQP, listener container có thể đăng ký `spring.rabbitmq.listener`, với các nhãn như `listenerId`, `queue`, `result`, `exception`. `MeterRegistry` và cài đặt `micrometerEnabled` là những điều kiện cần kiểm tra. [Tích hợp Micrometer trong Spring AMQP 3.1](https://docs.spring.io/spring-amqp/reference/3.1/amqp/receiving-messages/micrometer.html).

Timer này đo việc gọi listener, không phải phép đo trực tiếp số bản tin còn trong queue. Khi cần số bản tin sẵn sàng giao, số bản tin chưa được xác nhận, dung lượng node hoặc tình trạng cụm, dùng dữ liệu broker RabbitMQ thích hợp. Plugin `rabbitmq_prometheus` là một nguồn giám sát phía broker; đó là đường thu thập riêng với endpoint Actuator của ứng dụng. [Giám sát RabbitMQ phía broker](https://www.rabbitmq.com/docs/monitoring).

Ví dụ: consumer nhận được bản tin rồi xử lý chậm. Bộ đếm consumed có thể tăng, nhưng queue còn backlog và số bản tin chưa được xác nhận vẫn có thể cao. Không suy ra queue rỗng từ việc consumed đang tăng.

## 5. Observation có thể đổi đường tạo timer và bộ nhãn

Micrometer Observation là cơ chế mô tả một thao tác đang được quan sát. Với các handler phù hợp, cùng thao tác đó có thể sinh metrics và thông tin tracing. Metrics không đòi hỏi phải cấu hình đầy đủ hệ thống tracing mới hoạt động; ngược lại, có registry metrics chưa đồng nghĩa các thao tác tùy chọn đã bật Observation.

Trong cấu hình tự động Boot 3.3, các thuộc tính sau cho phép bật Observation trên thành phần tương ứng:

```properties
spring.kafka.template.observation-enabled=true
spring.kafka.listener.observation-enabled=true

spring.rabbitmq.template.observation-enabled=true
spring.rabbitmq.listener.simple.observation-enabled=true
```

Nếu dùng Rabbit direct container thay vì simple container, thuộc tính cần xét là `spring.rabbitmq.listener.direct.observation-enabled`. Hãy chọn đúng loại container; cấu hình simple không tự chuyển thành cấu hình direct. [Thuộc tính cấu hình Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Trong Spring Kafka 3.2, bật Observation trên template/container sẽ chuyển việc tạo timer sang cơ chế Observation thay cho timer Micrometer truyền thống. Tên cơ bản `spring.kafka.template` và `spring.kafka.listener` vẫn có thể giống nhau, nhưng không được mặc định bộ nhãn cũ giữ nguyên. Với batch listener, cần kiểm tra khả năng hỗ trợ riêng của phiên bản này trước khi áp dụng kết luận cho record listener. [Monitoring và Observation của Spring Kafka 3.2](https://docs.spring.io/spring-kafka/reference/3.2/kafka/micrometer.html#micrometer-observation).

Với Spring AMQP 3.1, Observation cũng cần bật trên template/container tương ứng. Tên timer Observation thường là `spring.rabbit.template` và `spring.rabbit.listener`, khác với tên legacy `spring.rabbitmq.listener`. Đây là lý do tìm riêng một tiền tố cũ có thể bỏ sót số đo đang có. [Observation của Spring AMQP 3.1](https://docs.spring.io/spring-amqp/reference/3.1/amqp/receiving-messages/micrometer-observation.html), [tên các observation Rabbit](https://docs.spring.io/spring-amqp/reference/appendix/micrometer.html).

Các tên mới có thể đi kèm timer theo dõi thao tác đang diễn ra với hậu tố `.active`. Chúng không phải số lỗi hoặc số bản tin đang chờ trong broker. Luôn đọc loại meter, mô tả và đơn vị trước khi đặt tên biểu đồ.

Bật Observation không thay thế các số đo gốc của Kafka/RabbitMQ Java client. Một nhóm giúp nhìn hoạt động của thư viện client; nhóm còn lại đặt ranh giới quanh thao tác của Spring. Cả hai có thể cùng tồn tại và phục vụ những câu hỏi khác nhau.

## 6. Thí nghiệm: thay dependency, giữ nguyên mã kiểm tra

Thí nghiệm này giúp phân biệt ba trạng thái: **có lớp thư viện**, **có bean tích hợp**, **có meter được đăng ký**. Không cần dựng broker để chạy hai bước đầu vì chương trình không tạo listener nghiệp vụ và không gửi bản tin.

### 6.1. Dự án nền

Tạo một dự án minh họa riêng, dùng JDK 21 và Gradle 8.5 hoặc bản tương thích. Cấu trúc tối thiểu:

```text
integration-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/integrationmetrics/IntegrationMetricsApplication.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'integration-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Bước Kafka: bỏ dấu chú thích ở dòng tương ứng rồi khởi động lại.
    // implementation 'org.springframework.kafka:spring-kafka'

    // Bước RabbitMQ: chỉ thêm khi làm thí nghiệm RabbitMQ.
    // implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
```

Đây là các lựa chọn phụ thuộc có chủ đích cho thí nghiệm, không phải yêu cầu thêm cả hai hệ nhắn tin vào mọi ứng dụng. Để BOM của Boot quản lý phiên bản thư viện, thay vì tự phối Micrometer và Spring Kafka/AMQP không tương thích.

`application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

Cấu hình này phục vụ thí nghiệm trên máy cá nhân. Quyền truy cập endpoint trong một ứng dụng có bảo mật vẫn do cấu hình bảo mật của ứng dụng quyết định.

### 6.2. Chương trình kiểm tra

Lưu nguyên nội dung sau vào `IntegrationMetricsApplication.java` đúng thư mục đã nêu:

```java
package example.integrationmetrics;

import java.util.Arrays;
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class IntegrationMetricsApplication {
    private static final List<String> PREFIXES = List.of(
            "kafka.", "rabbitmq.", "spring.kafka.",
            "spring.rabbit.", "spring.rabbitmq.", "spring.integration.");

    public static void main(String[] args) {
        SpringApplication.run(IntegrationMetricsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ApplicationContext context, MeterRegistry registry) {
        return args -> {
            printBeans(context, "kafka", "org.springframework.kafka.core.KafkaTemplate");
            printBeans(context, "rabbit", "org.springframework.amqp.rabbit.core.RabbitTemplate");

            List<String> names = registry.getMeters().stream()
                    .map(meter -> meter.getId().getName())
                    .filter(name -> PREFIXES.stream().anyMatch(name::startsWith))
                    .distinct()
                    .sorted()
                    .toList();
            System.out.println("DEMO integrationMeters=" + names);
        };
    }

    private static void printBeans(ApplicationContext context, String label,
            String className) {
        ClassLoader loader = IntegrationMetricsApplication.class.getClassLoader();
        boolean present = ClassUtils.isPresent(className, loader);
        String[] beans = present
                ? context.getBeanNamesForType(ClassUtils.resolveClassName(className, loader))
                : new String[0];
        Arrays.sort(beans);
        System.out.println("DEMO " + label + ".classpath=" + present
                + " beans=" + Arrays.toString(beans));
    }
}
```

Chương trình chỉ đọc trạng thái đã có, không tự tạo các counter tên Kafka/RabbitMQ để mô phỏng việc tích hợp. Phép lọc trong `PREFIXES` là danh sách định hướng cho bài học, không phải bộ nhận diện mọi công nghệ có thể có trong một ứng dụng.

Chạy bằng Gradle wrapper nếu dự án có wrapper:

```powershell
.\gradlew.bat bootRun
```

Hoặc dùng Gradle đã cài tương thích:

```powershell
gradle bootRun
```

Lần đầu có thể cần tải plugin và thư viện từ kho phụ thuộc.

### 6.3. Lần chạy nền: chưa thêm Kafka/AMQP

Với đúng dự án nền, các dòng stdout có tiền tố `DEMO` là:

```text
DEMO kafka.classpath=false beans=[]
DEMO rabbit.classpath=false beans=[]
DEMO integrationMeters=[]
```

Ứng dụng vẫn có các số đo khác như JVM hoặc thời gian khởi động. Danh sách `integrationMeters=[]` chỉ nói rằng không có tên nào khớp các tiền tố đang lọc; nó không nói registry rỗng.

### 6.4. Chỉ thêm Spring Kafka

Bỏ dấu chú thích của phụ thuộc `spring-kafka`, dừng ứng dụng rồi khởi động lại. Giữ nguyên mã Java và không bật Observation trong lần so sánh này. Khi không có tùy biến khác và chỉ dùng các bean mặc định, phần stdout định hướng là:

```text
DEMO kafka.classpath=true beans=[kafkaTemplate]
DEMO rabbit.classpath=false beans=[]
DEMO integrationMeters=[spring.kafka.template]
```

Đã có timer của template, nhưng chương trình chưa gửi bản tin và chưa chạy một consumer. Hãy đọc meter để kiểm tra giá trị:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template"
```

Trong thí nghiệm chưa gửi, `COUNT` của timer vẫn là 0. Việc timer có thể được đăng ký sớm là bằng chứng cụ thể rằng **meter tồn tại** và **thao tác đã xảy ra** là hai điều khác nhau.

Chưa có nhóm `kafka.producer.*`/`kafka.consumer.*` trong trạng thái trên là hợp lý: các client thực tế chưa được tạo. Ngược lại, nếu thêm listener hoặc mã gửi vào một dự án khác, client có thể được tạo trước thời điểm runner in danh sách; không áp nguyên stdout này cho dự án đã có hoạt động.

### 6.5. Thử với RabbitMQ và với lưu lượng thực tế

Để so sánh riêng RabbitMQ, bỏ phụ thuộc Spring Kafka của thí nghiệm rồi thêm starter AMQP và khởi động lại. Kiểm tra lớp `RabbitTemplate`, bean thực tế và các meter `rabbitmq.*` được đăng ký. Không mặc định danh sách tên hoặc số đếm của RabbitMQ giống Kafka; collector có thể đăng ký một số meter trước khi có kết nối hay bản tin.

Khi chuyển sang quan sát lưu lượng thật, cần một broker thí nghiệm có thể truy cập và cấu hình kết nối phù hợp. Các thuộc tính dưới đây là cấu hình mẫu, không khởi tạo broker hoặc dữ liệu bên ngoài:

```properties
# Chỉ dùng nhóm Kafka khi làm thí nghiệm Kafka.
spring.kafka.bootstrap-servers=127.0.0.1:9092
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.consumer.group-id=metrics-demo
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer

# Chỉ dùng nhóm RabbitMQ khi làm thí nghiệm RabbitMQ.
spring.rabbitmq.host=127.0.0.1
spring.rabbitmq.port=5672
```

Với Kafka, chuẩn bị topic thí nghiệm và gửi/nhận qua `KafkaTemplate`/listener được Spring quản lý. Với RabbitMQ, chuẩn bị queue, exchange/binding và quyền truy cập phù hợp rồi gửi/nhận qua các thành phần tương ứng. Cách Boot cấu hình các thành phần Kafka được mô tả trong [tài liệu tích hợp Kafka 3.3](https://docs.spring.io/spring-boot/3.3/reference/messaging/kafka.html).

Ghi lại các tên meter trước và sau thao tác, rồi đối chiếu cả các bộ đếm và timer liên quan. Đừng kỳ vọng một tổng số cố định trong mọi môi trường: retries, lỗi, rebalance và cách listener xử lý batch có thể làm số lần thao tác khác số bản tin ban đầu.

Runner trong ví dụ chỉ in **snapshot lúc khởi động**. Sau khi phát sinh hoạt động, dùng endpoint metrics để xem trạng thái mới; stdout cũ không tự cập nhật theo registry.

Nếu chỉ muốn chạy phần kiểm tra stdout mà không mở HTTP, có thể dùng:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

Khi đó không dùng các lệnh `curl` để truy vấn ứng dụng này.

## 7. Tìm số đo từ bằng chứng runtime

### 7.1. Kiểm tra phụ thuộc thực tế

Đối với dự án Gradle, dùng cây `runtimeClasspath`, không chỉ nhìn các dòng khai báo trong `build.gradle`:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-kafka --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-rabbit --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency amqp-client --configuration runtimeClasspath
```

Trong build nhiều module, thêm đường dẫn project cụ thể trước tên task. Kiểm tra dependency trực tiếp lẫn dependency bắc cầu: một starter khác có thể đưa thư viện vào mà module không khai báo tên thư viện đó trực tiếp. Cũng phân biệt phụ thuộc chỉ có trong test với phụ thuộc của ứng dụng đang chạy.

Nếu thư viện có trên classpath nhưng bean không xuất hiện, xem các điều kiện cấu hình tự động: cấu hình bị exclude, bean ứng dụng làm auto-configuration lùi lại, profile đang dùng, hoặc điều kiện lớp/bean khác còn thiếu. Có thể chạy ứng dụng với `--debug` để xem báo cáo điều kiện; không cần đoán thêm dependency một cách tuần tự rồi hy vọng số đo xuất hiện.

### 7.2. Liệt kê tên, sau đó mới truy vấn từng meter

Trong PowerShell:

```powershell
$inventory = Invoke-RestMethod "http://localhost:8080/actuator/metrics"
$inventory.names |
    Where-Object { $_ -match '^(kafka\.|rabbitmq\.|spring\.(kafka|rabbitmq|rabbit|integration)\.)' } |
    Sort-Object
```

Sau khi thấy một tên thực tế, truy vấn chi tiết. Ví dụ:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template"
curl.exe "http://localhost:8080/actuator/metrics/rabbitmq.connections"
```

Chỉ dùng lệnh tương ứng với meter đang tồn tại. Xem `description`, `baseUnit`, `measurements`, `availableTags`, rồi dùng `tag=KEY:VALUE` để thu hẹp một bean/client hoặc kết quả xử lý. Giá trị không lọc có thể tổng hợp nhiều chuỗi cùng tên. [API metrics của Actuator](https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html).

Ví dụ sau **chỉ áp dụng cơ chế timer Kafka truyền thống**, sau khi đã xác nhận nhãn `name` và `result` trong response:

```powershell
curl.exe "http://localhost:8080/actuator/metrics/spring.kafka.template?tag=name:kafkaTemplate&tag=result:success"
```

Không dùng bộ lọc cũ cho Observation rồi kết luận ứng dụng mất số đo. Nhãn cùng ý nghĩa có thể đổi tên theo quy ước observation hoặc theo phiên bản.

### 7.3. Giữ nguyên khác biệt giữa ba trạng thái

| Kết quả quan sát | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Tên meter không có | Meter đó chưa được thấy trong registry này tại lúc đọc | Không thể kết luận giá trị của nó bằng 0 |
| Meter có, counter/count bằng 0 | Đã có chuỗi số đo nhưng chưa ghi nhận sự kiện tương ứng trong phạm vi của nó | Không chứng minh toàn broker không có hoạt động |
| Meter tăng sau thao tác | Đường đo đó ghi nhận được hoạt động | Chưa chứng minh thành công toàn bộ nghiệp vụ xuyên nhiều dịch vụ |
| Endpoint không truy cập được | Có vấn đề ở đường truy cập endpoint hoặc ứng dụng | Chưa biết meter bên trong registry có tồn tại không |

Khi truy vấn nhiều instance, kiểm tra đúng instance đang tạo lưu lượng. Một request gửi đến instance thứ nhất và một lần đọc metrics ở instance thứ hai có thể tạo ra cảm giác “bộ đếm không tăng” dù cả hai đều hoạt động đúng.

## 8. Các thư viện tích hợp khác: áp cùng cách suy luận

Không cần ghi nhớ toàn bộ danh mục metric. Hãy biết từ thư viện và thành phần nào để tìm sang nhóm tên nào:

| Phụ thuộc/thành phần có trong ứng dụng | Nhóm tên để tìm | Điều kiện cần đối chiếu |
| --- | --- | --- |
| Spring Integration | `spring.integration.*` | Có channel/handler/source thực tế và registry; cách đo truyền thống hay Observation |
| Spring Data repository | `spring.data.repository.invocations` | Repository được Spring tạo và được thực thi; cấu hình đo tương ứng |
| MongoDB driver qua cấu hình Boot | `mongodb.driver.commands`, `mongodb.driver.pool.*` | MongoClient được gắn listener đo, có thao tác/kết nối tương ứng |
| JPA/Hibernate | `hibernate.*` | Có `hibernate-micrometer` và bật thống kê Hibernate; chỉ starter JPA chưa đủ |
| Spring Batch | Các meter của job/step như `spring.batch.job`, `spring.batch.step` | Có Batch infrastructure và thực thi job/step; kiểm tra phiên bản và Observation |

Đây là bản đồ định hướng, không phải danh sách dependency cần thêm vào mọi module. Boot mô tả các tích hợp MongoDB, repository và Hibernate cùng điều kiện riêng trong [danh mục số đo được hỗ trợ của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Với Spring Integration 6.3, ví dụ các timer `spring.integration.send` và counter `spring.integration.receive` gắn với các loại thành phần cụ thể; còn gauges `spring.integration.channels`, `handlers`, `sources` đếm thành phần trong ứng dụng. Những gauges này không phải số Kafka partition hoặc số queue trên broker RabbitMQ. Khi bật đường Observation, cần kiểm tra tên và convention theo đường đó. [Metrics của Spring Integration 6.3](https://docs.spring.io/spring-integration/reference/6.3/metrics.html).

Cùng một bản tin có thể đi qua Kafka client, listener của Spring Kafka rồi handler của Spring Integration. Khi đó nó tạo dữ liệu ở nhiều lớp. Cộng mọi counter của các lớp thành một “tổng số bản tin” sẽ đếm chồng các sự kiện khác nghĩa.

## 9. Đọc dữ liệu xuất ra đúng tên và đúng loại

Để dùng endpoint Prometheus trong dự án minh họa, bổ sung registry rồi expose endpoint tương ứng:

```groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Tên để truy vấn `/actuator/metrics/{name}` là tên Micrometer, chẳng hạn `spring.kafka.listener`. Trong dữ liệu Prometheus, timer thường được biểu diễn thành các chuỗi như `spring_kafka_listener_seconds_count` và `spring_kafka_listener_seconds_sum`. Bộ đếm `rabbitmq.published` thường thành `rabbitmq_published_total`. Kiểm tra output thực tế vì registry, convention và phiên bản có thể ảnh hưởng tên/nhãn.

```powershell
curl.exe "http://localhost:8080/actuator/prometheus" |
    Select-String "kafka_|rabbitmq_|spring_kafka_|spring_rabbit"
```

Ví dụ PromQL cho tốc độ các thao tác publish được RabbitMQ Java client ghi nhận, khi đã xác nhận tên này tồn tại:

```promql
sum by (job) (rate(rabbitmq_published_total[5m]))
```

Đây là tốc độ sự kiện publish phía client được scrape trong các job đó. Nó không phải chiều dài queue và không chứng minh từng bản tin đã xử lý thành công.

Đối với timer Kafka listener, có thể tính thời gian trung bình trong cửa sổ quan sát bằng tổng thời gian tăng chia cho số lần tăng, với cùng bộ lọc/nhãn nhóm:

```promql
sum by (job) (rate(spring_kafka_listener_seconds_sum[5m]))
/
sum by (job) (rate(spring_kafka_listener_seconds_count[5m]))
```

Nếu không có lần xử lý trong cửa sổ, mẫu số có thể bằng 0 và tỷ lệ không có giá trị hữu ích. Đây không phải phép tính p95/p99 và không phải độ trễ đầu cuối của toàn bộ hệ thống.

Với gauge kết nối/kênh hoặc lag, đọc giá trị theo ý nghĩa hiện tại; không áp `rate` chỉ vì thấy một số trên dashboard. Với số đo vốn đã là tốc độ do Kafka client tính sẵn, cũng không lấy `rate` lần nữa như với counter tích lũy. Trước khi viết truy vấn, xác định loại meter và đơn vị từ nguồn thực tế.

## 10. Chẩn đoán thiếu metrics theo từng mắt xích

| Dấu hiệu | Bước kiểm tra tiếp theo |
| --- | --- |
| Có Actuator nhưng không có tên Kafka nào | Kiểm tra Spring Kafka trong runtime classpath và các bean thực tế; ứng dụng có thật sự dùng Kafka không? |
| Có `KafkaTemplate`, có `spring.kafka.template`, nhưng không có `kafka.producer.*` | Producer đã được tạo chưa, hay ứng dụng mới chỉ khởi tạo template? |
| Đã gửi qua Kafka nhưng thiếu số đo gốc | Xác định factory nào tạo client và listener đo nào đang gắn vào nó; xem có tự tạo raw client hay không |
| Không có số đo consumer | Kiểm tra listener/container có chạy, client đã tạo và được gán partition chưa; producer metrics không thay thế consumer metrics |
| RabbitMQ có tên meter nhưng connection count bằng 0 | Kiểm tra ứng dụng đã mở kết nối chưa; collector có thể tồn tại trước kết nối đầu tiên |
| RabbitMQ có consumed nhưng không biết backlog | Chuyển sang nguồn số liệu queue phía broker; counter client không mô tả trực tiếp queue depth |
| Bật Observation rồi truy vấn theo nhãn cũ không ra | Liệt kê lại tên meter và `availableTags`; xác nhận quy ước và kiểu listener của phiên bản đang chạy |
| Dependency đã khai báo nhưng bean không có | Xem phiên bản thực tế, phạm vi dependency, profile, exclusions và báo cáo điều kiện cấu hình tự động |
| Meter có trong registry nhưng không thấy trong Prometheus | Kiểm tra registry export, expose endpoint, các bộ lọc metric và đúng scrape target |
| Thấy metrics khi bật debug nhưng count không đổi | Debug giúp thấy cấu hình; vẫn phải tạo thao tác đi qua thành phần đang đo |

Các thuộc tính lọc meter cũng có thể làm mất cả một nhóm. Ví dụ `management.metrics.enable.kafka=false` nhắm đến tên bắt đầu bằng `kafka`; nhóm `spring.kafka.*` là tên khác và phải được xét riêng. Đừng dùng việc một nhóm còn tồn tại để kết luận nhóm kia chưa từng bị tắt.

Tùy biến nhãn nên dùng các giá trị có số lượng hữu hạn như tên ứng dụng, môi trường, tên listener ổn định. Không gắn payload, message ID hoặc order ID thay đổi theo từng bản tin vào metrics: mỗi tổ hợp nhãn mới có thể sinh thêm chuỗi thời gian và khiến việc lưu trữ/so sánh tốn kém.

## 11. Thực hành tự xác minh

1. **Dự án nền:** chạy ví dụ không có Spring Kafka/AMQP. Giải thích vì sao vẫn có JVM metrics nhưng danh sách tích hợp đang lọc lại rỗng.
2. **Chỉ thêm Spring Kafka:** xác minh ba bằng chứng riêng: dependency runtime, bean `KafkaTemplate`, và `COUNT` của `spring.kafka.template` trước khi gửi.
3. **Tạo hoạt động trên broker thí nghiệm:** chụp danh sách meter trước/sau gửi và trước/sau khởi động consumer. Phân loại từng tên mới vào client, timer của Spring hoặc dữ liệu broker.
4. **Đổi cơ chế đo có kiểm soát:** bật Observation cho đúng template/listener, khởi động lại và so sánh tên/nhãn. Không dùng dashboard có bộ lọc cũ làm bằng chứng duy nhất rằng dữ liệu biến mất.
5. **Phân tích tình huống RabbitMQ:** consumed tăng nhưng queue còn nhiều bản tin chưa được xác nhận. Nêu vì sao điều đó không mâu thuẫn và cần nguồn broker nào để xác minh.
6. **Kiểm tra một thư viện khác:** chọn một dependency thực sự có trong ứng dụng, lần theo bean/tài nguyên/bộ kết nối rồi mới tìm nhóm meter. Không thêm thư viện chỉ để danh sách metrics dài hơn.

Sau các thí nghiệm, với mỗi biểu đồ phải chỉ ra được **thành phần đang đo, thư viện/phiên bản tạo số đo, đường đăng ký, loại meter, nhãn phân biệt và thao tác làm nó thay đổi**. Đây là cơ sở để đọc đúng metrics tích hợp khi dependency hoặc kiến trúc ứng dụng thay đổi.
