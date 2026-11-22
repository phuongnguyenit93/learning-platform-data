# Ranh giới giữa Spring Boot auto-configuration và cấu hình thủ công

Spring Kafka cung cấp các thành phần để gửi và nhận record như `KafkaTemplate`, `ProducerFactory`, `ConsumerFactory` và listener container. Spring Boot có thể tự tạo và kết nối phần lớn các thành phần này dựa trên dependency có trong classpath cùng các thuộc tính `spring.kafka.*`. Khi ứng dụng có yêu cầu riêng, ta có thể bổ sung một bean hoặc thay thế đúng thành phần cần tùy chỉnh. Chỉ nên chuyển sang cấu hình thủ công toàn bộ khi ứng dụng thực sự cần kiểm soát vòng đời và cách tạo các Kafka client.

Ranh giới này quan trọng vì cấu hình tự động giúp ứng dụng khởi đầu nhanh và giữ cấu hình nhất quán; cấu hình thủ công đem lại quyền kiểm soát sâu hơn nhưng cũng khiến ứng dụng chịu trách nhiệm nối các thành phần, quản lý nhiều cấu hình và duy trì chúng khi nâng cấp.

## 1. Các lớp cấu hình trong một ứng dụng Spring Kafka

Một ứng dụng Spring Boot dùng Spring Kafka thường có các lớp sau:

1. **Dependency:** thư viện Spring Kafka và Kafka client có mặt trên classpath.
2. **External configuration:** `application.yml`, biến môi trường hoặc nguồn cấu hình khác cung cấp broker, serializer, deserializer, group id, security và các tùy chọn listener.
3. **Spring Boot auto-configuration:** đọc `KafkaProperties`, kiểm tra điều kiện và đăng ký các bean mặc định nếu ứng dụng chưa cung cấp bean tương ứng.
4. **Application configuration:** khai báo thêm bean hoặc thay thế một phần cấu hình mặc định cho yêu cầu nghiệp vụ.
5. **Application code:** gửi sự kiện qua `KafkaTemplate` và nhận sự kiện qua `@KafkaListener`.

Luồng khởi tạo có thể hình dung như sau:

```mermaid
flowchart TD
    A[Dependency Spring Kafka] --> C[Kafka auto-configuration]
    B[application.yml / environment] --> D[KafkaProperties]
    D --> C
    C --> E[ProducerFactory và KafkaTemplate]
    C --> F[ConsumerFactory và listener container factory]
    C --> G[KafkaAdmin và các thành phần liên quan]
    H[Bean tùy chỉnh của ứng dụng] --> C
    E --> I[Producer code]
    F --> J[@KafkaListener]
    I --> K[Kafka cluster]
    J <--> K
    G <--> K
```

Sơ đồ thể hiện ranh giới trách nhiệm: Boot dựng các bean nền tảng khi đủ điều kiện; ứng dụng quyết định phần nào cần điều chỉnh theo yêu cầu thực tế.

## 2. Auto-configuration làm gì?

Khi dependency cần thiết có mặt, Spring Boot đăng ký các cấu hình tự động liên quan đến Kafka. Tùy phiên bản Boot và các điều kiện của ứng dụng, nhóm bean được cung cấp thường bao gồm:

- `ProducerFactory` để tạo Kafka producer.
- `ConsumerFactory` để tạo Kafka consumer.
- `KafkaTemplate` để gửi record.
- `KafkaAdmin` để thực hiện các thao tác quản trị như khai báo topic qua bean `NewTopic`.
- `ConcurrentKafkaListenerContainerFactory` mặc định để tạo listener container cho `@KafkaListener`.
- Các thành phần hỗ trợ transaction hoặc Kafka Streams khi có cấu hình và dependency tương ứng.

Các bean cụ thể còn phụ thuộc vào classpath, thuộc tính cấu hình và bean do ứng dụng đăng ký. Không nên coi danh sách trên là cam kết rằng mọi bean luôn xuất hiện trong mọi ứng dụng.

`KafkaProperties` là đối tượng cấu hình có kiểu, được bind từ nhóm thuộc tính `spring.kafka`. Boot dùng nó để xây dựng cấu hình cho Kafka client và listener infrastructure. Ví dụ, `spring.kafka.producer.*` dành cho producer, `spring.kafka.consumer.*` dành cho consumer, `spring.kafka.listener.*` dành cho listener container, còn `spring.kafka.template.*` dành cho `KafkaTemplate`.

Auto-configuration thường dựa trên các điều kiện như:

| Điều kiện | Ý nghĩa |
|---|---|
| Classpath condition | Chỉ áp dụng khi lớp hoặc thư viện cần thiết có mặt |
| Missing-bean condition | Chỉ tạo bean mặc định khi chưa có bean phù hợp trong context |
| Property condition | Chỉ kích hoạt một nhánh cấu hình khi thuộc tính thỏa điều kiện |
| Configuration import | Nạp cấu hình liên quan khi cấu hình nền tảng được kích hoạt |

Điều này giải thích vì sao thêm dependency có thể làm xuất hiện bean Kafka mà ứng dụng không khai báo trực tiếp, và vì sao một bean do ứng dụng tự khai báo có thể khiến bean mặc định tương ứng không còn được tạo.

## 3. Bắt đầu bằng thuộc tính `spring.kafka.*`

Nếu yêu cầu chỉ là chọn broker, serializer, deserializer, consumer group hoặc acknowledgement mode, cấu hình bằng thuộc tính thường là lựa chọn phù hợp nhất. Ví dụ:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    consumer:
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
```

Trong ví dụ này, Boot dùng cùng địa chỉ broker cho các client nếu không có cấu hình riêng ở producer hoặc consumer. Producer gửi key dạng chuỗi và value JSON; consumer dùng group `billing-v1`, bắt đầu từ phần log còn giữ khi chưa có committed offset hợp lệ, và listener container commit theo từng record sau khi listener xử lý xong.

Các nhóm thuộc tính có phạm vi khác nhau:

| Nhóm | Ví dụ | Thành phần chịu ảnh hưởng |
|---|---|---|
| `spring.kafka.bootstrap-servers` | `localhost:9092` | Broker mặc định cho client |
| `spring.kafka.producer.*` | `acks`, serializer, retries | Producer và producer factory |
| `spring.kafka.consumer.*` | `group-id`, deserializer, reset policy | Consumer và consumer factory |
| `spring.kafka.listener.*` | `ack-mode`, concurrency, poll timeout | Listener container |
| `spring.kafka.template.*` | `default-topic`, timeout | `KafkaTemplate` |
| `spring.kafka.admin.*` | fail-fast, operation timeout | `KafkaAdmin` |
| `spring.kafka.properties.*` | native Kafka client properties | Các client dùng cấu hình chung |

Với thuộc tính bảo mật như SASL, SSL hoặc truststore, có thể dùng các thuộc tính được Spring Boot hỗ trợ hoặc native Kafka properties tương ứng. Thông tin bí mật nên được cấp qua biến môi trường hoặc hệ thống quản lý secret; không commit mật khẩu hay private key vào repository. Khi một native property và một thuộc tính có kiểu cùng cấu hình một khóa, hãy tránh khai báo trùng và kiểm tra cấu hình client thực tế theo phiên bản Boot đang dùng.

Ưu tiên thuộc tính có kiểu khi Boot đã cung cấp sẵn vì tên thuộc tính rõ ràng và dễ kiểm tra. Dùng `spring.kafka.*.properties` cho những tùy chọn Kafka client chưa có thuộc tính Boot chuyên biệt.

## 4. Tùy chỉnh một phần mà vẫn giữ auto-configuration

Một nhu cầu riêng không có nghĩa phải tự tạo tất cả Kafka bean. Auto-configuration được thiết kế để ứng dụng có thể thay thế từng phần. Ví dụ, nếu chỉ muốn đặt topic mặc định cho `KafkaTemplate`, có thể khai báo bean `KafkaTemplate` riêng và tiếp tục dùng `ProducerFactory` mà Boot cung cấp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaTemplateConfiguration {

    @Bean
    KafkaTemplate<Object, Object> kafkaTemplate(
            ProducerFactory<Object, Object> producerFactory) {

        KafkaTemplate<Object, Object> template =
                new KafkaTemplate<>(producerFactory);
        template.setDefaultTopic("orders");
        return template;
    }
}
```

Khi context đã có bean `KafkaTemplate` phù hợp, phương thức auto-configuration tạo `KafkaTemplate` mặc định có điều kiện thiếu bean sẽ lùi lại. `ProducerFactory` vẫn có thể tiếp tục đến từ Boot, vì vậy serializer, broker và các thuộc tính producer đã cấu hình vẫn được sử dụng.

Đây là ví dụ của nguyên tắc **thay đúng bean cần thay**. Cần đọc điều kiện của bean trong phiên bản Spring Boot đang dùng: một số điều kiện kiểm tra theo kiểu bean, một số kiểm tra theo tên bean. Đừng giả định rằng chỉ cần tạo một bean bất kỳ cùng chức năng là toàn bộ cấu hình Kafka tự động bị tắt.

## 5. Tạo listener container factory riêng cho một nhóm listener

Giả sử phần lớn listener xử lý từng record, nhưng một listener cần nhận batch để tối ưu thao tác ghi dữ liệu. Ta có thể tạo thêm một container factory dùng chung `ConsumerFactory` của Boot:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class BatchListenerConfiguration {

    @Bean("ordersBatchFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object> ordersBatchFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<Object, Object>();
        configurer.configure(factory, consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Listener chọn factory này bằng tên bean:

```java
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.kafka.annotation.KafkaListener;

@Component
class OrdersBatchListener {

    private final OrderBatchService orderBatchService;

    OrdersBatchListener(OrderBatchService orderBatchService) {
        this.orderBatchService = orderBatchService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "billing-batch-v1",
            containerFactory = "ordersBatchFactory")
    public void onOrders(List<OrderCreated> orders) {
        orderBatchService.processBatch(orders);
    }
}
```

Ví dụ dùng `ConcurrentKafkaListenerContainerFactoryConfigurer` để áp dụng các thuộc tính listener chung của Boot vào factory mới trước khi bật batch và đặt concurrency riêng. Nhờ đó, các thiết lập chung như acknowledgement mode và các tùy chỉnh container do Boot hỗ trợ vẫn được kế thừa. Kiểu payload và chữ ký tham số cần khớp với cấu hình deserializer, message converter và phiên bản Spring Kafka của ứng dụng. Factory mặc định vẫn phục vụ các listener khác. Vì thế, một yêu cầu concurrency hoặc batch riêng có thể được khoanh vùng mà không phải thay toàn bộ consumer infrastructure.

Lưu ý rằng `concurrency` tạo số consumer thread cho container. Số consumer thực sự được gán partition còn phụ thuộc số partition, group membership và trạng thái rebalance. Đặt concurrency cao hơn số partition không làm tăng số partition có thể xử lý song song trong cùng group.

## 6. Khi nào cần thay `ProducerFactory` hoặc `ConsumerFactory`?

`ProducerFactory` và `ConsumerFactory` là ranh giới gần Kafka client hơn. Cân nhắc thay hoặc bổ sung chúng khi có yêu cầu mà thuộc tính đơn thuần không diễn đạt đủ, ví dụ:

- Producer và consumer phải kết nối đến các cluster khác nhau.
- Một luồng cần serializer, deserializer hoặc interceptor riêng.
- Cần điều chỉnh cách cache, tạo mới hoặc đóng Kafka client.
- Một số listener cần consumer có isolation level, client id hoặc security identity riêng.
- Ứng dụng có nhiều tenant hoặc nhiều luồng xử lý cần cấu hình Kafka độc lập.

Trước khi viết factory mới, hãy xác định liệu cấu hình chuẩn `spring.kafka.producer.*` hoặc `spring.kafka.consumer.*` đã giải quyết được yêu cầu chưa. Nếu chỉ cần thay một vài native client properties, thêm các thuộc tính đó vào cấu hình thường đơn giản hơn việc tự xây dựng map.

Khi thực sự tạo factory riêng, cần chịu trách nhiệm cho toàn bộ thuộc tính quan trọng của client tương ứng: bootstrap servers, serializer/deserializer, security, timeout, retry, acknowledgment, isolation level và các cấu hình liên quan. Nếu factory mới vẫn phải dùng chung cấu hình với Boot, hãy lấy cấu hình từ `KafkaProperties` hoặc cơ chế customizer được phiên bản Boot hỗ trợ, rồi chỉ thay đổi phần cần thiết. Tránh chép lại một map cấu hình rời rạc vì nó dễ bỏ sót thay đổi bảo mật hoặc thuộc tính mới khi ứng dụng nâng cấp.

Khi có nhiều factory cùng kiểu, đặt tên bean rõ ràng và dùng `@Qualifier` ở điểm inject. Nếu có một bean mặc định cần được inject khi không chỉ rõ qualifier, có thể cân nhắc `@Primary`; không dùng `@Primary` để che giấu việc chọn nhầm cluster.

## 7. Cấu hình thủ công toàn bộ và loại trừ auto-configuration

Chỉ nên loại trừ Kafka auto-configuration khi ứng dụng cần tự chịu trách nhiệm tạo và kết nối các thành phần nền tảng, chẳng hạn một ứng dụng multi-cluster có kiến trúc riêng hoặc một runtime tích hợp Kafka theo cách đặc thù.

Có thể loại trừ cấu hình tự động bằng annotation ở lớp ứng dụng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration;

@SpringBootApplication(exclude = KafkaAutoConfiguration.class)
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
```

Sau khi loại trừ, ứng dụng phải chủ động khai báo những bean cần thiết cho thiết kế của mình, ví dụ:

- `ProducerFactory` và `KafkaTemplate` cho luồng gửi.
- `ConsumerFactory` và `ConcurrentKafkaListenerContainerFactory` cho luồng nhận.
- `KafkaAdmin` nếu ứng dụng cần quản trị topic bằng Spring.
- Transaction manager và cấu hình transaction nếu cần giao dịch Kafka.
- Hạ tầng annotation-driven cho `@KafkaListener` nếu cấu hình bị loại trừ trước đó cung cấp hạ tầng này.

Với cấu hình listener hoàn toàn thủ công, thường cần bật hạ tầng annotation bằng `@EnableKafka` và đăng ký listener container factory phù hợp. Kiểm tra danh sách auto-configuration bị loại trừ và các cấu hình khác trong ứng dụng để tránh vô tình bỏ một thành phần mà ứng dụng vẫn đang sử dụng.

Loại trừ `KafkaAutoConfiguration` là một thay đổi phạm vi rộng. Nó không phải công cụ để chỉnh một timeout hoặc thay serializer. Nếu chỉ cần một bean riêng, hãy giữ auto-configuration và thay bean ở phạm vi hẹp hơn.

## 8. Chọn mức cấu hình phù hợp

Bảng sau giúp quyết định điểm dừng hợp lý:

| Nhu cầu | Mức cấu hình nên chọn | Lý do |
|---|---|---|
| Đổi broker, group id, serializer, deserializer, retry hoặc security property | `application.yml` / environment | Boot đã có thuộc tính tương ứng hoặc hỗ trợ native client properties |
| Đặt default topic, message converter hoặc listener behavior chung | Bean tùy chỉnh hoặc customizer | Thay đúng phần cần thay và giữ factory mặc định |
| Một listener cần batch, concurrency hoặc error handling riêng | Container factory bổ sung | Cô lập hành vi cho nhóm listener đó |
| Một luồng cần consumer/producer có cấu hình khác | Factory riêng và qualifier | Có thể giữ các luồng còn lại dùng cấu hình mặc định |
| Nhiều cluster, nhiều tenant hoặc vòng đời client đặc thù | Cấu hình thủ công có chủ đích | Ứng dụng cần kiểm soát rõ từng factory, template và listener container |

Một quy tắc thực tế là bắt đầu từ thuộc tính, sau đó tùy chỉnh bean, rồi mới tự xây dựng factory hoặc loại trừ auto-configuration. Mỗi bước đi sâu hơn đều tăng phần cấu hình mà nhóm phát triển phải duy trì.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| Có `spring.kafka.*` nghĩa là không cần hiểu bean | Thuộc tính chỉ là đầu vào; Boot dùng chúng để tạo và kết nối bean | Biết bean nào nhận cấu hình khi cần debug hoặc mở rộng |
| Tạo một bean Kafka tùy chỉnh sẽ tắt toàn bộ auto-configuration | Điều kiện missing-bean thường chỉ làm lùi bean cụ thể bị thay thế | Kiểm tra điều kiện và kiểu bean của từng cấu hình |
| Thêm `@Primary` sẽ sửa được mọi xung đột | `@Primary` chỉ ưu tiên một candidate khi inject; nó không thay thế bean theo mọi điều kiện | Dùng qualifier để chọn rõ factory hoặc cluster |
| Mọi listener đều phải dùng một container factory | Có thể khai báo nhiều factory và chọn bằng `containerFactory` | Tách listener theo batch, concurrency hoặc error handling |
| Cấu hình thủ công luôn cho hiệu năng tốt hơn | Factory tùy chỉnh không tự làm Kafka nhanh hơn | Đo bottleneck trước khi thay đổi kiến trúc |
| Exclude auto-configuration là cách đơn giản để đổi một thuộc tính | Exclude làm mất cả nhóm bean mặc định liên quan | Chỉ exclude khi muốn tự quản lý toàn bộ phần bị ảnh hưởng |
| `@KafkaListener` tự tạo mọi thứ mà không cần cấu hình | Listener cần container factory, consumer factory và cấu hình deserialize phù hợp | Kiểm tra factory được listener sử dụng và cấu hình payload |

## 10. Chẩn đoán khi bean tự động không xuất hiện hoặc bị thay thế

Khi một bean Kafka không có trong context hoặc ứng dụng dùng nhầm factory, hãy kiểm tra theo thứ tự:

1. **Classpath:** dependency Spring Kafka và Kafka client có nằm trong runtime classpath không?
2. **Properties:** các khóa `spring.kafka.*` có đúng prefix, kiểu dữ liệu và profile đang chạy không?
3. **Condition evaluation:** auto-configuration có được import không, và điều kiện nào đã match hoặc không match?
4. **Bean cạnh tranh:** có bean do ứng dụng hoặc thư viện khác đăng ký với cùng kiểu/tên không?
5. **Injection point:** `@Qualifier`, `@Primary` hoặc generic type có khiến Spring chọn một bean khác không?
6. **Listener mapping:** `@KafkaListener` có trỏ đúng `containerFactory` không?

Có thể bật báo cáo điều kiện bằng tùy chọn `--debug` khi chạy Spring Boot:

```bash
java -jar messaging-service.jar --debug
```

Condition evaluation report cho biết cấu hình nào được áp dụng và vì sao một số cấu hình bị bỏ qua. Nếu ứng dụng bật Spring Boot Actuator, endpoint `conditions` cũng có thể hỗ trợ kiểm tra; chỉ expose endpoint này theo chính sách vận hành và bảo mật của môi trường.

Trong lúc debug, hãy ghi nhận bean thực tế được inject và cấu hình client cuối cùng. Việc chỉ nhìn file YAML không đủ để kết luận consumer đang dùng đúng group, cluster hoặc deserializer, nhất là khi có nhiều profile và factory tùy chỉnh.

## 11. Checklist trước khi đưa cấu hình vào production

- Bắt đầu bằng `spring.kafka.*` cho mọi tùy chọn Boot hỗ trợ.
- Xác định bean cụ thể cần thay trước khi thêm `@Bean`.
- Dùng factory riêng khi có khác biệt thực sự về cluster, serializer, security hoặc listener behavior.
- Đặt tên và qualifier rõ ràng khi có nhiều `ProducerFactory`, `ConsumerFactory` hoặc container factory.
- Không trộn cấu hình cùng một native property ở nhiều nơi nếu chưa hiểu thứ tự áp dụng.
- Quản lý credential ngoài mã nguồn và kiểm tra cấu hình theo từng profile môi trường.
- Chỉ exclude auto-configuration khi đã liệt kê đầy đủ các bean mà ứng dụng sẽ tự quản lý.
- Dùng condition report và kiểm tra bean thực tế khi hành vi khởi tạo khác kỳ vọng.

Trong ứng dụng Spring Kafka, auto-configuration là nền tảng mặc định để kết nối các client và listener. Cấu hình thủ công là công cụ mở rộng ở những điểm có yêu cầu cụ thể. Nắm rõ điều kiện tạo bean và ranh giới giữa properties, factory, template và listener container giúp ứng dụng giữ được cấu hình dễ hiểu trong khi vẫn đáp ứng được các luồng messaging phức tạp.
