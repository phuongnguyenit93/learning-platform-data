# Cấu hình producer cơ bản

Producer là thành phần gửi record từ ứng dụng tới Kafka. Trong Spring Kafka, ứng dụng thường dùng `KafkaTemplate` để gửi dữ liệu; cấu hình producer quyết định client kết nối broker nào, chuyển key/value thành byte ra sao, yêu cầu broker xác nhận ở mức nào, xử lý lỗi gửi thế nào và sử dụng bộ đệm, batch cùng compression ra sao.

Một cấu hình producer tốt cần đáp ứng đồng thời ba mục tiêu: gửi đúng dữ liệu đến đúng cluster, có mức độ tin cậy phù hợp với nghiệp vụ và sử dụng tài nguyên hợp lý. Không có một bộ thông số tối ưu cho mọi hệ thống. Cấu hình nên bắt đầu từ yêu cầu nghiệp vụ, sau đó mới điều chỉnh độ trễ, throughput và độ bền.

Bài học thuộc chương **Cấu hình kết nối** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, hiểu topic, partition, offset và consumer group, đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Producer nằm ở đâu trong luồng gửi?

Một lần gửi event bằng Spring Kafka đi qua các thành phần chính:

1. Service nghiệp vụ tạo event và chọn topic, key cùng payload.
2. `KafkaTemplate` tạo record và chuyển yêu cầu gửi tới producer do `ProducerFactory` cung cấp.
3. Serializer chuyển key/value thành byte.
4. Partitioner xác định partition đích dựa trên partition được chỉ định, key hoặc chiến lược mặc định.
5. Kafka producer gửi record đến broker leader của partition.
6. Broker xử lý record và phản hồi theo cấu hình xác nhận.
7. Future của thao tác gửi hoàn tất thành công hoặc lỗi; ứng dụng có thể quan sát kết quả này.

~~~mermaid
flowchart LR
    A[Service tạo event] --> B[KafkaTemplate]
    B --> C[ProducerFactory]
    C --> D[Kafka Producer]
    D --> E[Serializer]
    E --> F[Partitioner]
    F --> G[Broker leader]
    G --> H[ACK hoặc lỗi]
    H --> I[SendResult / Exception]
~~~

Producer chỉ chịu trách nhiệm gửi record và nhận kết quả theo giao thức producer-broker. Việc consumer đọc, xử lý nghiệp vụ và commit offset là các bước riêng. Vì vậy, kết quả gửi thành công không có nghĩa consumer đã xử lý event.

## 2. Cấu hình tối thiểu trong Spring Boot

Nếu ứng dụng dùng Spring Boot và Spring Kafka, có thể khai báo địa chỉ cluster cùng serializer trong `application.yml`. Spring Boot sử dụng các thuộc tính này để cấu hình producer factory và KafkaTemplate mặc định khi auto-configuration được áp dụng.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Các thuộc tính trên có ý nghĩa:

- `bootstrap-servers`: địa chỉ broker mà client dùng để kết nối ban đầu và lấy metadata của cluster.
- `key-serializer`: chuyển key từ kiểu Java thành byte.
- `value-serializer`: chuyển payload từ kiểu Java thành byte.
- `StringSerializer`: phù hợp khi key là chuỗi.
- `JsonSerializer`: serializer của Spring Kafka để chuyển object thành JSON.

Khai báo serializer phải khớp với kiểu key/value mà ứng dụng gửi. Ví dụ `KafkaTemplate<String, OrderCreated>` cần serializer xử lý được String ở key và OrderCreated ở value. Nếu kiểu generic và serializer không tương thích, lỗi có thể xuất hiện khi gửi hoặc serialize record.

Với cấu hình tối thiểu, producer có thể dùng các giá trị mặc định của Kafka client cho acknowledgement, retry, batching và timeout. Khi đưa ứng dụng vào môi trường thật, cần chủ động xem xét các thuộc tính quan trọng ở các phần tiếp theo thay vì dựa hoàn toàn vào default của phiên bản thư viện.

## 3. Kết nối tới Kafka cluster bằng bootstrap servers

### 3.1. Bootstrap servers là địa chỉ khởi đầu

`bootstrap.servers` là danh sách địa chỉ broker mà producer sử dụng để thiết lập kết nối ban đầu và lấy metadata. Có thể khai báo một hoặc nhiều broker:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal:9092
      - kafka-2.internal:9092
      - kafka-3.internal:9092
~~~

Khai báo nhiều địa chỉ giúp client có thêm lựa chọn khi một broker bootstrap không sẵn sàng. Sau khi lấy metadata, Kafka client kết nối đến broker đang giữ vai trò leader của partition đích. Vì vậy, danh sách bootstrap không phải danh sách cố định các broker mà mọi record đều được gửi tuần tự qua.

### 3.2. Địa chỉ quảng bá của broker cũng phải truy cập được

Một tình huống thường gặp là ứng dụng kết nối được tới bootstrap broker nhưng sau đó không gửi được record. Nguyên nhân có thể là broker quảng bá địa chỉ trong `advertised.listeners` mà máy chạy ứng dụng không thể truy cập.

Ví dụ, broker có thể quảng bá `localhost:9092`. Địa chỉ này chỉ phù hợp khi producer chạy cùng môi trường mạng với broker. Nếu producer chạy trong container hoặc máy khác, `localhost` có thể trỏ về chính container/máy ứng dụng thay vì Kafka broker.

Khi điều tra kết nối, cần kiểm tra:

- DNS có phân giải hostname broker không.
- Port có được mở từ môi trường chạy ứng dụng không.
- Firewall, network policy hoặc security group có chặn kết nối không.
- `advertised.listeners` có trả về hostname và port mà producer truy cập được không.
- Ứng dụng có dùng đúng listener dành cho client nội bộ, bên ngoài hoặc container không.

Không nên xử lý lỗi kết nối bằng cách đổi ngẫu nhiên bootstrap server. Cần xác định địa chỉ mà Kafka cluster công bố cho client và bảo đảm địa chỉ đó có thể truy cập từ đúng môi trường triển khai.

### 3.3. Cấu hình theo môi trường

Địa chỉ cluster thường khác nhau giữa local, test, staging và production. Không nên hard-code địa chỉ production trong mã Java.

Có thể đặt cấu hình mặc định trong YAML và override bằng biến môi trường:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Khi triển khai, cấu hình môi trường có thể cung cấp giá trị `SPRING_KAFKA_BOOTSTRAP_SERVERS` hoặc cấu hình tương đương qua hệ thống quản lý deployment. Cách này giúp một artifact ứng dụng có thể chạy ở nhiều môi trường mà không phải build lại chỉ để đổi địa chỉ broker.

## 4. Serializer cho key và value

Kafka lưu record dưới dạng byte. Producer serializer chịu trách nhiệm chuyển kiểu Java thành byte trước khi gửi đến broker.

### 4.1. Chọn serializer theo kiểu dữ liệu

| Serializer | Dữ liệu phù hợp | Ghi chú |
| --- | --- | --- |
| `StringSerializer` | String | Thường dùng cho key hoặc payload dạng text. |
| `ByteArraySerializer` | byte[] | Dùng khi ứng dụng đã tự mã hóa payload. |
| `IntegerSerializer` | Integer | Dùng khi key/value là số nguyên tương ứng. |
| Spring Kafka `JsonSerializer` | Object Java | Chuyển object thành JSON và có thể thêm type information vào header theo cấu hình. |
| Serializer Avro/Protobuf | Schema-based payload | Thường dùng khi hệ thống có schema registry hoặc cơ chế quản lý schema riêng. |

Ví dụ event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Producer có thể gửi event bằng key là orderId:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Trong ví dụ, key là String và value là OrderCreated. Spring Kafka sử dụng serializer đã cấu hình để chuyển chúng thành byte.

### 4.2. Key ảnh hưởng tới partitioning

Key không chỉ là metadata để consumer đọc. Nó còn được producer dùng khi chọn partition. Với partitioner mặc định và key không null, các record có cùng key thường được định tuyến tới cùng partition trong cùng topology partition.

Chọn `orderId` làm key giúp các event của cùng một đơn hàng có cơ hội được xử lý theo thứ tự trong một partition. Chọn key không phù hợp, chẳng hạn một giá trị giống nhau cho mọi record, có thể làm tải dồn vào một partition và giảm khả năng song song.

Nếu không có yêu cầu giữ thứ tự theo thực thể, có thể gửi record không key để partitioner phân phối theo chiến lược mặc định. Quyết định key cần dựa trên ngữ nghĩa nghiệp vụ và cách consumer xử lý dữ liệu.

### 4.3. Producer và consumer phải thống nhất contract

Producer serialize thành công không có nghĩa mọi consumer đều giải mã được payload. Hai phía cần thống nhất:

- Định dạng payload, ví dụ JSON, Avro hoặc Protobuf.
- Quy tắc tên field và kiểu dữ liệu.
- Cách xử lý field mới, field bị thiếu hoặc giá trị null.
- Type header hoặc schema identifier nếu định dạng sử dụng metadata kiểu/schema.
- Quy tắc tương thích khi producer và consumer được phát hành ở các thời điểm khác nhau.

Với JSON, Spring Kafka JsonSerializer có thể thêm type header. Consumer có thể dùng type header, mapping hoặc default type để xác định kiểu đích. Không nên để package Java nội bộ của một service trở thành contract bắt buộc cho tất cả service khác nếu các service cần phát hành độc lập. Khi cần, hãy định nghĩa schema hoặc type mapping ổn định.

## 5. Mức xác nhận gửi với acks

`acks` quyết định producer chờ mức xác nhận nào từ broker trước khi xem một lần gửi là thành công.

| Giá trị | Hành vi | Đánh đổi |
| --- | --- | --- |
| `0` | Producer không chờ broker xác nhận record đã được ghi. | Độ trễ thấp hơn nhưng producer khó phát hiện lỗi gửi và có thể mất record. |
| `1` | Leader xác nhận sau khi append record vào log cục bộ. | Có thể mất record nếu leader gặp sự cố trước khi replica khác sao chép dữ liệu. |
| `all` | Leader chờ các replica trong ISR xác nhận theo giao thức replication. | Tăng mức bảo vệ dữ liệu nhưng phụ thuộc tình trạng ISR và cấu hình replication. |

Với event nghiệp vụ quan trọng, `acks=all` thường là lựa chọn nên cân nhắc. Tuy nhiên, `acks=all` không tự động có nghĩa mọi replica trong cluster đều đã ghi record. Nó liên quan đến tập replica đang nằm trong ISR. Cần phối hợp replication factor và `min.insync.replicas` để đặt yêu cầu độ bền phù hợp.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
~~~

Khi future của send hoàn tất thành công, producer đã nhận acknowledgement theo cấu hình đã chọn. Kết quả này không cho biết consumer group đã đọc record hay chưa.

## 6. Retry và idempotence ở producer

### 6.1. Retry xử lý lỗi gửi tạm thời

Producer có thể gặp lỗi tạm thời như broker leader thay đổi, request timeout hoặc lỗi mạng ngắn hạn. Kafka client có thể gửi lại request khi lỗi thuộc loại có thể retry và còn trong giới hạn thời gian gửi.

Không nên chỉ tăng `retries` thật lớn rồi cho rằng dữ liệu đã an toàn. Tổng thời gian gửi còn bị giới hạn bởi `delivery.timeout.ms`. Khi hết thời gian này, thao tác gửi có thể thất bại dù client còn có thể thử lại theo số lần retry đã cấu hình.

Các thuộc tính liên quan:

| Thuộc tính | Vai trò |
| --- | --- |
| `retries` | Số lần client có thể thử gửi lại khi gặp lỗi có thể retry. |
| `delivery.timeout.ms` | Giới hạn tổng thời gian để send hoàn tất, gồm thời gian chờ và retry theo cơ chế producer. |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request tới broker. |
| `retry.backoff.ms` | Khoảng nghỉ giữa các lần thử lại trong những trường hợp áp dụng. |

Nên xem `delivery.timeout.ms` như giới hạn tổng thể cho một lần gửi. `request.timeout.ms` chỉ liên quan một request. Nếu cấu hình timeout không nhất quán, producer có thể hết thời gian tổng trước khi cơ hội retry được sử dụng hết.

### 6.2. Idempotent producer hạn chế duplicate do retry

Nếu producer gửi record nhưng acknowledgement bị mất trên đường về, client có thể không biết broker đã append record hay chưa. Khi gửi lại, có nguy cơ tạo record trùng nếu không có cơ chế chống trùng ở tầng producer.

Kafka hỗ trợ idempotent producer. Khi bật `enable.idempotence`, producer dùng producer ID và sequence number để broker nhận diện các lần gửi lại thuộc cùng luồng producer, qua đó tránh append duplicate do retry trong phạm vi bảo đảm của cơ chế này.

Cấu hình thường dùng:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "enable.idempotence": true
~~~

Idempotence cần được sử dụng cùng các điều kiện cấu hình tương thích của Kafka client, bao gồm acknowledgement, retry và số request đang bay tối đa trên một kết nối. Các phiên bản Kafka client hiện đại tự kiểm tra một số điều kiện này; nếu override các thuộc tính liên quan, cần đọc tài liệu đúng phiên bản để tránh xung đột.

Idempotent producer không loại bỏ mọi duplicate ở cấp ứng dụng. Ví dụ, service có thể gọi send hai lần cho cùng một event vì logic nghiệp vụ chạy lại; đó là hai lần gửi mới từ ứng dụng, không phải retry nội bộ mà idempotent producer có thể tự nhận diện là cùng một thao tác. Để chống lặp nghiệp vụ, cần event ID và consumer idempotency phù hợp.

## 7. Batch, linger và compression

Producer không nhất thiết gửi từng record thành một request riêng. Kafka client gom record thành batch theo partition để giảm số request và tăng hiệu quả mạng.

Các thuộc tính thường được điều chỉnh:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `batch.size` | Kích thước batch mục tiêu theo partition. |
| `linger.ms` | Thời gian producer có thể chờ thêm record để batch đầy hơn trước khi gửi. |
| `buffer.memory` | Bộ nhớ producer dùng để đệm record chờ gửi. |
| `compression.type` | Kiểu nén record batch, ví dụ none, gzip, snappy, lz4 hoặc zstd tùy client/broker hỗ trợ. |

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "linger.ms": 5
        "compression.type": zstd
~~~

Các con số trên chỉ là ví dụ để minh họa cách cấu hình, không phải giá trị tối ưu cho mọi hệ thống. Tăng `linger.ms` có thể giúp batch lớn hơn và cải thiện throughput, nhưng cũng làm tăng độ trễ chờ của record khi lưu lượng thấp. Tăng `batch.size` hoặc `buffer.memory` có thể tăng mức sử dụng bộ nhớ.

Compression có thể giảm băng thông mạng và dung lượng truyền, đổi lại producer và broker/consumer phải dùng CPU để nén/giải nén. Nên chọn compression dựa trên kích thước payload, CPU, băng thông và latency thực tế.

Batch được tổ chức theo partition. Nếu key phân phối không đều, một partition có thể nhận phần lớn record và tạo batch lớn trong khi các partition khác ít dữ liệu. Do đó, điều chỉnh batch không thể thay thế việc thiết kế key và partitioning hợp lý.

## 8. Các timeout và backpressure quan trọng

Một producer có nhiều điểm có thể chờ: khởi tạo kết nối, lấy metadata, đợi buffer, gửi request và chờ acknowledgement. Các timeout khác nhau kiểm soát những giai đoạn khác nhau.

| Thuộc tính | Khi nào có tác dụng |
| --- | --- |
| `max.block.ms` | Giới hạn thời gian một số lời gọi đồng bộ của producer chờ metadata hoặc buffer khả dụng; KafkaTemplate.send có thể bị chặn trong giai đoạn lấy metadata/cấp buffer. |
| `request.timeout.ms` | Giới hạn thời gian chờ phản hồi cho một request. |
| `delivery.timeout.ms` | Giới hạn tổng thời gian hoàn tất một lần gửi. |
| `linger.ms` | Thời gian chờ gom batch trước khi gửi trong điều kiện áp dụng. |
| `metadata.max.age.ms` | Chu kỳ tối đa trước khi client làm mới metadata theo cơ chế Kafka client. |

Khi producer gửi nhanh hơn tốc độ broker tiếp nhận, buffer có thể đầy. Lúc đó, lời gọi gửi có thể chờ tối đa theo `max.block.ms`, sau đó phát sinh timeout nếu không có buffer hoặc metadata cần thiết. Đây là một dạng backpressure: ứng dụng cảm nhận việc hạ tầng không theo kịp tốc độ tạo dữ liệu.

Không nên đặt timeout quá lớn để che giấu tình trạng broker quá tải. Cần theo dõi buffer availability, request latency, record queue time, retry rate và error rate. Nếu producer liên tục đầy buffer, hãy tìm nguyên nhân gốc như broker chậm, mạng nghẽn, partition mất cân bằng hoặc tốc độ phát event vượt năng lực cluster.

## 9. Cấu hình producer hoàn chỉnh bằng Spring Boot

Một cấu hình cơ bản có cân nhắc độ tin cậy và hiệu năng có thể như sau:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      batch-size: 32768
      buffer-memory: 67108864
      properties:
        "enable.idempotence": true
        "delivery.timeout.ms": 120000
        "request.timeout.ms": 30000
        "linger.ms": 5
        "compression.type": zstd
~~~

Cấu hình này thể hiện các quyết định:

- Dùng StringSerializer cho key và JsonSerializer cho payload.
- Yêu cầu acknowledgement ở mức all.
- Bật idempotent producer.
- Đặt thời gian tổng cho một lần gửi và timeout cho từng request.
- Cho phép producer gom batch trong một khoảng ngắn.
- Dùng compression để giảm lượng byte truyền.

Các giá trị phải được kiểm tra với phiên bản Kafka client, broker, Spring Boot và yêu cầu vận hành thực tế. Nếu chưa có số liệu tải, nên bắt đầu từ cấu hình đơn giản, đo latency và throughput rồi điều chỉnh từng nhóm thuộc tính.

## 10. Cấu hình bằng Java khi cần tự tạo ProducerFactory

Spring Boot auto-configuration thường đủ cho ứng dụng chỉ dùng một cluster và một bộ serializer. Nếu cần tự quản lý factory, có thể khai báo ProducerFactory và KafkaTemplate bằng Java configuration.

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
        props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
        props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }
}
~~~

Ví dụ này minh họa cách truyền producer properties cho DefaultKafkaProducerFactory. Các import được lược bỏ để tập trung vào phần cấu hình.

Không nên tự tạo ProducerFactory chỉ để đổi một thuộc tính nếu Spring Boot đã hỗ trợ thuộc tính tương ứng. Dùng application.yml giúp cấu hình dễ override theo môi trường và giữ ít mã hạ tầng hơn. Tự tạo factory phù hợp khi cần nhiều cluster, nhiều serializer hoặc cấu hình producer độc lập.

Khi tự khai báo bean, cần kiểm tra bean KafkaTemplate nào được inject vào service. Nếu có nhiều ProducerFactory hoặc KafkaTemplate cùng kiểu generic, dùng tên bean và `@Qualifier` để tránh inject nhầm.

## 11. Gửi record và quan sát kết quả

KafkaTemplate cung cấp API gửi bất đồng bộ. Ví dụ:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("order-events", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Không gửi được event orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Đã gửi topic={} partition={} offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

Khi gửi thành công, `SendResult` cung cấp `RecordMetadata` với topic, partition, offset và timestamp. Các thông tin này hữu ích để đối chiếu record với log consumer và điều tra sự cố.

Trong Spring Kafka 3.x, phương thức send trả về `CompletableFuture`. Ở các phiên bản cũ hơn, API có thể trả về `ListenableFuture`. Cần dùng đúng kiểu future theo phiên bản dependency của dự án.

Nếu nghiệp vụ cần biết chắc broker đã xác nhận trước khi trả response cho caller, có thể chờ future trong giới hạn timeout đã chọn. Tuy nhiên, không nên chặn thread một cách tùy tiện trong mọi lần gửi vì sẽ làm giảm khả năng xử lý đồng thời. Với API bất đồng bộ, cần quan sát callback/future và có chính sách xử lý lỗi rõ ràng.

Không nên log toàn bộ payload theo mặc định. Thường chỉ cần event ID, business key, topic, partition, offset và correlation ID; payload có thể chứa dữ liệu cá nhân hoặc thông tin nhạy cảm.

## 12. Bảo mật kết nối producer

Trong môi trường thật, producer có thể cần TLS và SASL để xác thực, mã hóa kết nối với Kafka cluster. Các thuộc tính bảo mật có thể được cấu hình ở cấp `spring.kafka.properties` để dùng chung hoặc ở nhánh producer properties nếu cần tách riêng.

Ví dụ minh họa SASL_SSL với SCRAM:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="producer-user" password="injected-secret";
~~~

Đoạn cấu hình trên chỉ minh họa tên thuộc tính và cơ chế. Không commit username/password thật vào source control. Trong triển khai, lấy thông tin xác thực từ secret manager, Kubernetes Secret hoặc biến môi trường được bảo vệ. Cũng cần cấu hình truststore/certificate theo yêu cầu TLS của cluster và xác nhận hostname verification không bị tắt tùy tiện.

Nếu producer và consumer dùng credential khác nhau, hãy đặt cấu hình theo đúng client thay vì chia sẻ toàn bộ properties ở cấp gốc. Quyền ACL của principal producer nên chỉ đủ để ghi vào những topic cần thiết.

## 13. Kiểm thử cấu hình producer

Cấu hình producer nên được kiểm tra ở nhiều mức:

### 13.1. Kiểm tra cấu hình khởi tạo

Kiểm tra application context tạo được ProducerFactory và KafkaTemplate với đúng kiểu key/value, bootstrap server và serializer. Bước này phát hiện lỗi binding hoặc thiếu dependency, nhưng chưa chứng minh producer gửi được record.

### 13.2. Kiểm thử tích hợp với Kafka

Dùng Embedded Kafka hoặc Testcontainers để chạy broker trong test. Gửi record bằng KafkaTemplate rồi đọc record từ consumer test hoặc kiểm tra kết quả listener. Nên xác nhận:

- Topic nhận đúng record.
- Key và payload được serialize đúng.
- Metadata trả về có topic, partition và offset hợp lệ.
- Consumer có thể deserialize payload theo contract.
- Khi broker không sẵn sàng hoặc cấu hình sai, ứng dụng nhận được lỗi gửi có thể quan sát.

Testcontainers phù hợp khi cần kiểm tra với broker thật gần với môi trường triển khai. Embedded Kafka có thể phù hợp với một số test Spring Kafka nhanh hơn. Lựa chọn phụ thuộc phiên bản và hạ tầng test của dự án.

### 13.3. Không chỉ kiểm tra lời gọi send không ném exception

Do send bất đồng bộ, việc phương thức gọi KafkaTemplate.send trả về mà không ném exception đồng bộ không chứng minh record đã được broker xác nhận. Test cần chờ future hoàn tất và kiểm tra kết quả hoặc lỗi trong thời gian giới hạn.

Một test tích hợp khái quát:

~~~java
@Test
void shouldPublishOrderCreated() throws Exception {
    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    );

    SendResult<String, OrderCreated> result =
        kafkaTemplate.send("order-events", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("order-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
    assertThat(result.getRecordMetadata().offset())
        .isGreaterThanOrEqualTo(0);
}
~~~

Đây là ví dụ minh họa; test cần có broker, topic và bean KafkaTemplate tương ứng. Không nên dựa vào offset cố định vì offset phụ thuộc trạng thái topic và dữ liệu của test khác.

## 14. Theo dõi producer trong vận hành

Một producer có thể vẫn hoạt động nhưng chất lượng gửi đang giảm. Nên theo dõi các tín hiệu:

- **Record send rate:** số record gửi mỗi giây.
- **Request latency:** thời gian request tới broker và nhận phản hồi.
- **Record queue time:** thời gian record nằm trong producer buffer trước khi gửi.
- **Retry rate:** số lần request được thử lại.
- **Error rate:** lỗi gửi theo loại exception.
- **Buffer availability:** dung lượng buffer còn khả dụng.
- **Batch size và compression rate:** hiệu quả gom batch và nén.
- **Metadata refresh và connection errors:** tình trạng kết nối, broker metadata.

Nếu retry rate tăng, hãy kiểm tra broker leader, network và request timeout. Nếu queue time tăng, producer có thể đang gom batch lâu hoặc broker/network không theo kịp. Nếu buffer availability thường xuyên thấp, producer đang bị backpressure hoặc cấu hình buffer/tốc độ gửi không phù hợp.

Không nên chỉ tăng buffer memory để che giấu tình trạng broker chậm. Buffer lớn hơn có thể trì hoãn thời điểm ứng dụng cảm nhận backpressure và làm tăng bộ nhớ sử dụng, nhưng không làm tăng năng lực xử lý của broker.

## 15. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không kết nối được broker | Sai bootstrap server, DNS, port hoặc advertised.listeners | Kiểm tra địa chỉ từ đúng môi trường chạy ứng dụng và broker metadata |
| Kết nối được bootstrap nhưng gửi timeout | Địa chỉ broker leader không truy cập được hoặc network không ổn định | Kiểm tra advertised.listeners, route, firewall và broker leader |
| SerializationException | Serializer không hỗ trợ kiểu key/value hoặc payload sai định dạng | Kiểm tra generic KafkaTemplate và serializer đã cấu hình |
| Broker từ chối gửi | ACL, topic authorization, ISR không đủ hoặc quota | Kiểm tra exception, principal, topic ACL và trạng thái ISR |
| Gửi thành công nhưng event xuất hiện nhiều lần | Ứng dụng gửi lại cùng event hoặc retry ở tầng nghiệp vụ | Kiểm tra event ID, callback, retry của ứng dụng và idempotency |
| Producer đầy buffer | Broker xử lý chậm hoặc tốc độ gửi vượt năng lực cluster | Theo dõi buffer availability, queue time, request latency và record rate |
| Latency tăng khi lưu lượng thấp | linger.ms hoặc batching chờ lâu | Đo queue time và điều chỉnh linger theo mục tiêu latency |
| CPU tăng mạnh | Compression tốn CPU hoặc serialize payload lớn | So sánh compression type, payload size và CPU profile |
| Future hoàn tất lỗi sau khi service đã trả về | Gửi bất đồng bộ, lỗi chỉ xuất hiện khi nhận acknowledgement | Quan sát future/callback và quyết định có cần chờ kết quả hay không |

## 16. Checklist trước khi đưa producer vào môi trường thật

Trước khi phát hành, hãy xác nhận:

1. Bootstrap server trỏ tới đúng cluster và broker advertised address có thể truy cập từ môi trường chạy.
2. Serializer key/value tương thích với kiểu dữ liệu và contract của consumer.
3. Key được chọn phù hợp với yêu cầu phân vùng và thứ tự của nghiệp vụ.
4. Acknowledgement (`acks`) phù hợp với mức độ quan trọng của event.
5. Idempotence và retry được cấu hình nhất quán với yêu cầu độ tin cậy.
6. Delivery timeout, request timeout và max block timeout có giá trị phù hợp.
7. Batch, linger, buffer và compression đã được cân nhắc theo latency, throughput và bộ nhớ.
8. TLS/SASL và ACL được cấu hình đúng nếu cluster yêu cầu xác thực.
9. Future/callback của send được quan sát; lỗi gửi không bị bỏ qua.
10. Có kiểm thử tích hợp và metric để phát hiện lỗi kết nối, retry, buffer pressure và latency.

Cấu hình producer cơ bản không chỉ là khai báo một địa chỉ broker và serializer. Đó là tập hợp quyết định về kết nối, định dạng dữ liệu, độ bền, thời gian chờ và sử dụng tài nguyên. Khi những quyết định này được ghi rõ và kiểm thử, KafkaTemplate có thể cung cấp một đường gửi event ổn định cho các service nghiệp vụ.

