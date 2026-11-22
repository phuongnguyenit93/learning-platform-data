# enable.idempotence

## 1. Mục đích của idempotent producer

Trong một hệ thống Spring Kafka, producer có thể phải gửi lại record khi gặp lỗi mạng, timeout hoặc broker tạm thời không khả dụng. Một tình huống khó nhận biết xảy ra khi broker đã ghi record nhưng acknowledgement bị mất trên đường về client. Producer không biết chắc broker đã ghi hay chưa, vì vậy nó cần retry.

Nếu mỗi lần retry được broker xem là một record mới, cùng một event có thể xuất hiện nhiều lần trong topic. Điều này làm consumer phải xử lý duplicate và có thể gây ra tác động nghiệp vụ lặp lại, chẳng hạn tạo hai yêu cầu giao hàng hoặc cộng tồn kho hai lần.

Thuộc tính `enable.idempotence` bật cơ chế idempotence ở Kafka producer. Cơ chế này cho phép broker nhận biết và loại bỏ những lần gửi lặp lại do chính producer retry cùng một batch trong cùng producer session. Producer có thể retry khi acknowledgement bị mất mà không làm phát sinh thêm bản ghi trong log cho lần gửi đó.

Trong Spring Kafka, `KafkaTemplate` sử dụng Kafka producer ở phía dưới. Vì vậy, idempotence được cấu hình trên Kafka producer mà `ProducerFactory` tạo ra. Spring Kafka không thay thế cơ chế này bằng một lớp chống duplicate riêng.

## 2. Cơ chế hoạt động bên trong Kafka

Kafka dùng producer ID (PID), producer epoch và sequence number để nhận diện thứ tự gửi của một producer.

Khi producer khởi tạo, broker cấp một PID. Với mỗi partition mà producer gửi tới, client quản lý sequence number tăng dần. Mỗi batch gửi đi mang thông tin nhận diện producer và sequence tương ứng. Broker lưu trạng thái sequence theo producer và partition để xác định batch mới, batch bị lặp hoặc batch đến sai thứ tự.

Một luồng retry điển hình:

1. Producer gửi batch có sequence number N tới leader của partition.
2. Broker ghi batch vào log và cập nhật trạng thái sequence.
3. Acknowledgement bị mất do kết nối mạng bị ngắt.
4. Producer chưa nhận được kết quả nên retry chính batch đó với cùng thông tin sequence.
5. Broker nhận ra batch đã được ghi và không append thêm một bản sao.
6. Producer nhận được kết quả thành công hoặc tiếp tục xử lý lỗi theo chính sách retry.

```text
Spring application
       |
       | send(event)
       v
KafkaProducer
       |
       | PID + partition + sequence N
       v
Partition leader
       |
       | append batch N
       | update producer sequence state
       v
Kafka log
       |
       | acknowledgement bị mất
       v
KafkaProducer
       |
       | retry batch N với cùng sequence
       v
Partition leader
       |
       | nhận ra batch trùng
       | không append thêm bản sao
       v
KafkaProducer nhận kết quả
```

Điểm quan trọng là broker nhận diện lần retry dựa trên metadata của producer và batch. Producer không gửi một event mới với sequence mới cho mỗi lần retry nội bộ.

### 2.1. Producer ID và sequence number

- **Producer ID:** định danh producer mà broker dùng để theo dõi trạng thái ghi.
- **Producer epoch:** phiên bản/epoch của producer ID, hỗ trợ phát hiện producer cũ hoặc trạng thái producer không còn hợp lệ. Epoch cũng là một phần của cơ chế fencing trong các tình huống có producer transactional.
- **Sequence number:** số thứ tự của batch theo từng partition. Broker dùng nó để kiểm tra batch mới, batch lặp và batch sai thứ tự.

Sequence number được quản lý theo partition, do đó idempotence bảo vệ việc ghi lặp trong phạm vi producer-partition. Nó không tạo ra một thứ tự toàn cục giữa nhiều partition.

### 2.2. Vì sao retry thông thường có thể tạo duplicate?

Giả sử producer gửi một record và broker đã append record vào log. Nếu response bị mất, producer chỉ nhìn thấy timeout. Khi không bật idempotence, retry có thể được append như một record mới vì broker không có đủ thông tin để nhận diện nó là lần gửi lặp của cùng một producer sequence.

Với idempotence, lần retry giữ nguyên producer identity và sequence của batch ban đầu. Broker có thể xác định rằng batch đó đã được xử lý.

Cơ chế này bảo vệ retry ở tầng Kafka producer. Nếu ứng dụng gọi `kafkaTemplate.send()` lần thứ hai như một thao tác mới, producer sẽ tạo một lần gửi mới. Kafka không tự biết hai lần gửi đó có cùng `orderId`, `paymentId` hoặc business event hay không.

## 3. Các cấu hình liên quan và điều kiện bắt buộc

Khi bật idempotence, các cấu hình producer phải tương thích:

| Property | Yêu cầu khi bật idempotence | Vai trò |
|---|---|---|
| `enable.idempotence` | `true` | Bật cơ chế producer deduplication |
| `acks` | `all` | Chờ acknowledgement từ các replica hiện có trong ISR |
| `retries` | Lớn hơn 0 | Cho phép producer retry các lỗi có thể thử lại |
| `max.in.flight.requests.per.connection` | Nhỏ hơn hoặc bằng 5 | Giới hạn số request đang chờ trên một kết nối để giữ thứ tự phù hợp với idempotence |

Kafka client hiện đại kiểm tra tính tương thích của các cấu hình này. Nếu bật idempotence nhưng đặt các giá trị xung đột, producer có thể từ chối khởi tạo bằng lỗi cấu hình.

### 3.1. `acks=all`

`acks=all` yêu cầu leader chờ các replica hiện có trong ISR xác nhận trước khi trả kết quả thành công. Nó tăng độ bền của record đã được xác nhận, nhưng không có nghĩa mọi replica được cấu hình ban đầu luôn phải phản hồi.

Ví dụ topic có replication factor bằng 3 và `min.insync.replicas=2`. Khi ISR còn đủ hai replica, producer có thể ghi với `acks=all`. Nếu ISR giảm xuống dưới ngưỡng tối thiểu, broker từ chối ghi thay vì âm thầm chấp nhận một mức replication thấp hơn chính sách.

Idempotence và replication giải quyết hai khía cạnh liên quan nhưng khác nhau:

- Idempotence ngăn retry nội bộ tạo thêm bản ghi trùng trong log.
- Replication cùng `acks` và `min.insync.replicas` xác định điều kiện xác nhận và mức bảo vệ dữ liệu.

### 3.2. `retries` và `delivery.timeout.ms`

`retries` xác định khả năng thử lại các lỗi retriable. Đặt số lần retry rất lớn không có nghĩa producer retry vô hạn. `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất một lần gửi, tính cả thời gian chờ batch, request và các lần retry.

Một cấu hình phổ biến là để retry ở mức cao và dùng `delivery.timeout.ms` để giới hạn thời gian tối đa ứng dụng chờ kết quả. Hãy chọn thời hạn phù hợp với latency SLO của luồng event và thời gian downstream có thể chấp nhận.

`request.timeout.ms` giới hạn thời gian chờ phản hồi cho một request. Theo hướng dẫn của Kafka, `delivery.timeout.ms` nên lớn hơn hoặc bằng tổng `request.timeout.ms` và `linger.ms`.

### 3.3. `max.in.flight.requests.per.connection`

Đây là số request produce có thể đang chờ acknowledgement trên một kết nối. Khi idempotence được bật, Kafka hỗ trợ giá trị tối đa là 5.

Không cần đặt giá trị bằng 1 chỉ để có idempotence. Giá trị 5 vẫn cho phép producer giữ nhiều request đang bay và có thể cải thiện throughput, trong khi client và broker phối hợp sequence để duy trì thứ tự phù hợp. Giá trị 1 có thể giảm concurrency và throughput nếu không có yêu cầu riêng.

### 3.4. Mặc định theo phiên bản Kafka client

Từ Kafka 3.0, `enable.idempotence` mặc định là `true`. Các phiên bản client cũ có mặc định khác. Spring Boot quản lý phiên bản `kafka-clients` thông qua dependency management, nên cần xác định phiên bản client thực tế của ứng dụng trước khi dựa vào mặc định.

Khai báo tường minh giúp người đọc cấu hình nhận biết chủ đích reliability, tránh việc nâng cấp hoặc thay đổi dependency làm hành vi mặc định khó đoán. Dù client có mặc định bật, vẫn cần kiểm tra các cấu hình liên quan để đảm bảo producer thực sự khởi tạo với idempotence.

## 4. Cấu hình trong Spring Boot và Spring Kafka

Với ứng dụng Spring Boot, cách đơn giản là cấu hình các property của producer trong `application.yml` hoặc `application.properties`. Spring Boot chuyển các giá trị này vào Kafka producer mà `DefaultKafkaProducerFactory` sử dụng.

### 4.1. Ví dụ application.yml

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[retries]": 2147483647
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
```

Các key Kafka có dấu chấm được đặt trong ngoặc vuông để Spring Boot giữ nguyên tên key khi bind map `properties`. Các giá trị thời gian trong ví dụ tính bằng milliseconds.

Có thể biểu diễn cùng cấu hình trong `application.properties`:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[retries]=2147483647
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[linger.ms]=5
```

Ví dụ đặt `delivery.timeout.ms=120000`, `request.timeout.ms=30000` và `linger.ms=5`. Thời hạn gửi 120 giây là giá trị minh họa; hệ thống có latency budget thấp hơn có thể cần thời hạn ngắn hơn. Nếu thay đổi `request.timeout.ms` hoặc `linger.ms`, hãy xem lại ràng buộc giữa các thời hạn.

`retries=2147483647` là giá trị lớn thường dùng để producer tiếp tục retry trong giới hạn delivery timeout. Nó không khiến một lần gửi chiếm tài nguyên vô thời hạn vì `delivery.timeout.ms` vẫn giới hạn thời gian hoàn tất.

### 4.2. Cấu hình bằng Java

Nếu ứng dụng tự tạo `ProducerFactory`, có thể đặt các property tương ứng bằng `ProducerConfig`:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
public ProducerFactory<String, OrderCreated> producerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
    props.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5
    );

    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

    return new DefaultKafkaProducerFactory<>(props);
}

@Bean
public KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Đây là ví dụ khi ứng dụng chủ động sở hữu cấu hình `ProducerFactory`. Nếu đang dùng Spring Boot auto-configuration, nên ưu tiên cấu hình qua `spring.kafka.producer.*` để tránh tạo thêm một factory không cần thiết hoặc vô tình bỏ qua các thiết lập chung như security, serializer và metrics.

## 5. Gửi event qua KafkaTemplate

Khi `KafkaTemplate` gửi record, Kafka producer xử lý batching, request, acknowledgement và retry. Ứng dụng nhận kết quả bất đồng bộ qua future.

Ví dụ với Spring Kafka hiện đại, nơi `send()` trả về `CompletableFuture`:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private static final Logger log = LoggerFactory.getLogger(OrderEventPublisher.class);

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
```

Có thể ghi nhận kết quả gửi mà không chặn thread gọi:

```java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.send("orders.created", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Could not publish OrderCreated, orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info(
                "Published OrderCreated, topic={}, partition={}, offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
```

Future hoàn tất thành công nghĩa là Kafka producer nhận được kết quả xác nhận thành công theo cấu hình producer. Nó không chứng minh consumer đã nhận hoặc hoàn tất xử lý event. Nếu SLO của dịch vụ đo thời gian xử lý nghiệp vụ, cần một SLI riêng ở consumer hoặc ở hệ thống đích.

Không nên bỏ qua exception trong callback. Idempotence làm cho retry nội bộ an toàn hơn, nhưng producer vẫn có thể hết delivery timeout hoặc gặp lỗi không thể retry. Ứng dụng cần ghi nhận lỗi, quyết định có retry ở tầng nghiệp vụ hay không và đảm bảo cách retry đó không tạo duplicate logic.

## 6. Idempotence bảo vệ điều gì và giới hạn ở đâu?

Cần phân biệt ba lớp:

| Tình huống | Idempotent producer xử lý? | Giải thích |
|---|---|---|
| Broker đã append batch nhưng acknowledgement bị mất; producer retry cùng batch | Có | Broker nhận diện cùng PID và sequence |
| Producer retry batch do lỗi retriable trong cùng producer session | Có | Retry nội bộ dùng metadata sequence tương ứng |
| Ứng dụng gọi `send()` lần thứ hai cho cùng một business event | Không | Đây là một lần gửi mới theo góc nhìn producer |
| Ứng dụng khởi động lại và phát lại event từ nguồn ngoài | Không tự động | Producer mới có thể có PID mới và sequence mới |
| Consumer xử lý lại record sau khi crash trước khi commit offset | Không | Đây là vấn đề delivery/offset ở phía consumer |
| Consumer ghi DB thành công nhưng commit offset thất bại | Không | Kafka có thể giao lại record; cần idempotent consumer hoặc transaction phù hợp |
| Ghi đồng thời Kafka và một hệ thống DB ngoài Kafka | Không tự động | Idempotence không tạo transaction phân tán giữa Kafka và DB |

### 6.1. Duplicate ở tầng ứng dụng

Ví dụ API nhận yêu cầu tạo đơn hàng. API gọi Kafka producer nhưng hết thời gian chờ trước khi nhận kết quả. Client gọi lại API và ứng dụng phát cùng event lần nữa. Lần gửi thứ hai là một thao tác publish mới, không phải retry batch nội bộ của Kafka producer. Idempotence không thể suy luận rằng hai record có cùng ý nghĩa nghiệp vụ.

Các cách xử lý thường dùng:

- Gán business event ID ổn định, ví dụ `eventId` hoặc `orderId + eventVersion`.
- Dùng transactional outbox để lưu event cùng transaction với thay đổi dữ liệu nghiệp vụ, sau đó relay outbox sang Kafka.
- Ở consumer, lưu khóa đã xử lý trong bảng inbox/deduplication có unique constraint.
- Thiết kế thao tác cập nhật theo hướng idempotent, chẳng hạn cập nhật trạng thái theo version thay vì cộng dồn không kiểm soát.

Business ID có thể nằm trong header hoặc payload để consumer tra cứu. Không đưa từng ID vào label metric vì cardinality sẽ tăng rất nhanh.

### 6.2. Duplicate ở consumer

Kafka consumer mặc định thường phối hợp xử lý theo mô hình at-least-once khi offset được commit sau khi xử lý. Nếu consumer hoàn tất side effect nhưng crash trước khi commit offset, record có thể được giao lại sau khi khởi động.

Idempotent producer không ngăn lần xử lý lại này. Consumer cần có chiến lược riêng:

- Ghi nhận event ID đã xử lý bằng unique key.
- Dùng transaction của cơ sở dữ liệu để ghi side effect và đánh dấu event đã xử lý cùng nhau.
- Chọn thời điểm commit offset phù hợp với semantics xử lý.
- Nếu side effect nằm ngoài Kafka, thiết kế retry và deduplication ở ranh giới hệ thống.

## 7. Idempotence và Kafka transactions

Idempotent producer và Kafka transactions có liên hệ nhưng không đồng nghĩa.

Idempotence tập trung ngăn duplicate do retry nội bộ của producer. Kafka transaction mở rộng khả năng đó để nhiều lần gửi tới nhiều partition có thể được commit hoặc abort như một đơn vị. Khi dùng consume-transform-produce, ứng dụng có thể đưa offset của record đầu vào vào cùng transaction với các record đầu ra.

Trong Spring Kafka, giao dịch được cấu hình thông qua transactional producer factory và transaction ID prefix. Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID}-
```

Prefix cần phân biệt giữa các instance đang chạy trong cùng cluster để tránh các instance vô tình dùng chung transactional identity. Spring Kafka quản lý việc tạo transactional producer dựa trên prefix này.

Một ví dụ gửi trong transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.validated", orderId, validatedEvent);
    operations.send("orders.audit", orderId, auditEvent);
    return true;
});
```

Khi callback kết thúc bình thường, transaction được commit; nếu có exception phù hợp, transaction bị abort. Consumer muốn chỉ đọc dữ liệu đã commit cần cấu hình `isolation.level=read_committed`.

Với luồng consume-transform-produce, Spring Kafka có thể phối hợp container transaction và producer transaction để gửi output cùng offset đã xử lý vào transaction. Cách triển khai cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình listener container.

Transactions vẫn chỉ cung cấp atomicity trong phạm vi Kafka transaction. Nếu callback đồng thời ghi vào một cơ sở dữ liệu quan hệ, Kafka transaction không tự rollback transaction DB. Cần outbox, inbox hoặc một cơ chế phối hợp khác cho ranh giới Kafka-DB.

## 8. Ảnh hưởng tới thứ tự và throughput

Idempotence giúp producer retry mà vẫn giữ thứ tự batch phù hợp trong từng partition. Điều này quan trọng khi nhiều request đang chờ và một request cũ phải retry.

Thứ tự Kafka được bảo đảm trong phạm vi một partition. Nếu hai event có cùng key và được partitioner đưa vào cùng partition, consumer có thể đọc chúng theo thứ tự log của partition đó. Không có thứ tự toàn cục giữa các partition khác nhau.

Khi bật idempotence:

- Giữ `max.in.flight.requests.per.connection` không vượt quá 5.
- Không cần giảm xuống 1 trừ khi có lý do về thứ tự hoặc tải cụ thể.
- Chọn key ổn định để các event cần thứ tự được đưa vào cùng partition.
- Theo dõi batching và latency khi thay đổi `linger.ms`, `batch.size` hoặc concurrency.

Idempotence có một phần chi phí quản lý sequence và trạng thái producer, nhưng thường phù hợp cho producer cần độ tin cậy. Tác động throughput thực tế phụ thuộc phiên bản client, broker, kích thước batch, số partition, network và tải. Không nên giả định rằng chỉ bật idempotence sẽ làm throughput giảm mạnh; hãy đo trên workload đại diện.

## 9. Xử lý lỗi và chẩn đoán

Idempotence giảm rủi ro duplicate từ retry, nhưng không làm mọi lỗi producer biến mất. Vẫn cần theo dõi lỗi và hiểu loại lỗi trước khi quyết định retry ở tầng ứng dụng.

| Triệu chứng hoặc lỗi | Ý nghĩa có thể gặp | Hướng xử lý |
|---|---|---|
| Retry rate tăng | Broker phản hồi chậm, network chập chờn hoặc throttling | Kiểm tra broker request latency, network, quota và ISR |
| Delivery timeout | Producer không hoàn tất gửi trong thời hạn cấu hình | Kiểm tra tải, batch, broker, request timeout và latency SLO |
| NotEnoughReplicasException | ISR không đáp ứng `min.insync.replicas` cho yêu cầu ghi | Kiểm tra replica, broker health và replication |
| OutOfOrderSequenceException | Broker nhận sequence không khớp trạng thái mong đợi | Kiểm tra lỗi producer/broker, vòng đời producer và cách xử lý exception theo client version |
| Buffer exhaustion hoặc send chờ lâu | Producer không giải phóng buffer đủ nhanh hoặc broker không theo kịp | Kiểm tra throughput, buffer memory, batch và thời gian block |
| Duplicate business event vẫn xuất hiện | Ứng dụng phát lại event mới hoặc consumer xử lý lại | Kiểm tra business ID, API retry, outbox và consumer deduplication |

Không nên tự động retry vô hạn mọi exception. Một số lỗi là retriable, một số lỗi cấu hình hoặc serialization cần sửa nguyên nhân. Với lỗi sequence hoặc producer state, hãy tuân theo semantics của Kafka client version và tránh tiếp tục dùng một producer đã rơi vào trạng thái fatal.

### 9.1. Metric nên theo dõi

Kafka producer phát ra các metric hữu ích như:

| Metric | Câu hỏi cần trả lời |
|---|---|
| `record-retry-rate` / `record-retry-total` | Producer phải retry thường xuyên đến mức nào? |
| `record-error-rate` / `record-error-total` | Có bao nhiêu record send thất bại? |
| `record-send-rate` / `record-send-total` | Lưu lượng gửi hiện tại là bao nhiêu? |
| `request-latency-avg` và latency phân vị | Broker phản hồi producer nhanh hay chậm? |
| `record-queue-time-avg` | Record chờ trong producer buffer/batch bao lâu? |
| `buffer-available-bytes` | Producer còn bao nhiêu buffer khả dụng? |
| `batch-size-avg` | Producer gom batch hiệu quả đến đâu? |
| `produce-throttle-time-avg` | Broker/quota đang throttle producer bao lâu? |

Tên metric chính xác và cách expose phụ thuộc Kafka client, JMX exporter, Micrometer và phiên bản Spring Kafka. Hãy xác nhận metric đang có trong môi trường trước khi viết alert rule.

Một dashboard producer bền vững nên kết hợp:

- Publish success rate và p95/p99 publish latency.
- Retry rate và error rate.
- Buffer availability và record queue time.
- Broker request latency, quota throttling và ISR health.
- Số event nghiệp vụ phát ra so với số event consumer hoàn tất.

Retry rate tăng chưa chắc đã tạo duplicate khi idempotence hoạt động đúng, nhưng nó vẫn là dấu hiệu chất lượng kết nối hoặc broker đang suy giảm. Nếu chỉ quan sát duplicate count, đội vận hành có thể bỏ lỡ vấn đề latency và delivery timeout.

## 10. Kiểm tra cấu hình trong môi trường chạy

Khi triển khai, cần xác nhận producer thực sự dùng cấu hình mong muốn:

1. Xác định phiên bản `kafka-clients` mà ứng dụng chạy cùng, không chỉ phiên bản Spring Boot.
2. Kiểm tra cấu hình cuối cùng được truyền vào `ProducerFactory`, đặc biệt nếu ứng dụng có nhiều factory hoặc nhiều `KafkaTemplate`.
3. Xác nhận `enable.idempotence=true`, `acks=all`, `retries>0` và `max.in.flight.requests.per.connection<=5`.
4. Kiểm tra `delivery.timeout.ms` phù hợp với request timeout, linger và latency budget.
5. Quan sát retry, error, latency và broker replication khi chạy tải đại diện.
6. Thử nghiệm tình huống kết nối bị gián đoạn hoặc acknowledgement bị mất trong môi trường kiểm thử để xác nhận retry nội bộ không tạo thêm log entry cho cùng batch.
7. Kiểm tra riêng hành vi khi ứng dụng phát lại cùng business event hoặc consumer xử lý lại record; hai tình huống này cần cơ chế deduplication ở tầng ứng dụng.

Không log toàn bộ cấu hình producer nếu trong đó có password, token hoặc thông tin xác thực. Khi debug, chỉ hiển thị các property cần thiết và che giá trị nhạy cảm.

## 11. Ví dụ thực tế: producer gửi OrderCreated

Giả sử ứng dụng Order Service phát event `OrderCreated` vào topic `orders.created`. Event có key là `orderId` để các thay đổi của cùng đơn hàng được định tuyến nhất quán vào một partition.

```java
public record OrderCreated(
    String eventId,
    String orderId,
    Instant createdAt
) {}
```

Publisher:

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
```

Producer được cấu hình idempotence. Nếu broker append batch nhưng acknowledgement bị mất, Kafka producer có thể retry cùng batch và broker sẽ loại bỏ bản ghi lặp dựa trên PID/sequence.

Giả sử API gateway gửi lại request tạo đơn hàng do timeout. Nếu Order Service tạo một event publish mới cho request lặp đó, event mới có sequence mới. Idempotent producer không tự nhận ra hai event có cùng ý nghĩa. Order Service cần idempotency key ở API hoặc transaction DB để tránh tạo hai đơn hàng; outbox có thể đảm bảo event được phát nhất quán sau khi đơn hàng được lưu.

Ở phía consumer fulfillment, event ID có thể được lưu trong inbox table với unique constraint. Khi record được giao lại sau consumer restart, consumer kiểm tra ID đã xử lý và tránh tạo tác động nghiệp vụ lần thứ hai.

Ví dụ này cho thấy idempotent producer là một lớp bảo vệ quan trọng trên đường gửi, còn độ tin cậy end-to-end cần phối hợp cả producer, Kafka, consumer và hệ thống lưu trữ.

## 12. Các sai lầm thường gặp

**Cho rằng idempotence đồng nghĩa với exactly-once toàn hệ thống.** Idempotence bảo vệ retry nội bộ của producer. Nó không tự phối hợp transaction với DB hoặc ngăn consumer xử lý lại record.

**Bật idempotence nhưng cấu hình `acks` không tương thích.** Idempotent producer yêu cầu `acks=all`. Hãy để Kafka client xác thực cấu hình khi khởi tạo và kiểm tra log startup.

**Đặt `max.in.flight.requests.per.connection` lớn hơn 5.** Giá trị này không tương thích với idempotence. Dùng giá trị tối đa 5 hoặc thấp hơn.

**Đặt `retries` lớn và nghĩ producer sẽ thử mãi.** `delivery.timeout.ms` vẫn giới hạn tổng thời gian một lần gửi. Chọn timeout theo SLO và chính sách xử lý lỗi.

**Retry lại bằng một lời gọi send mới khi chưa biết kết quả lần đầu.** Đây là một logical publish operation khác và có thể tạo duplicate nghiệp vụ. Cần business ID, outbox hoặc deduplication ở tầng ứng dụng.

**Dựa vào mặc định mà không kiểm tra phiên bản client.** Mặc định idempotence thay đổi theo Kafka client version. Kiểm tra dependency thực tế và cấu hình tường minh.

**Bỏ qua lỗi vì nghĩ idempotence đã xử lý mọi trường hợp.** Producer vẫn có thể timeout, lỗi serialization, thiếu ISR hoặc gặp lỗi fatal. Cần ghi nhận và phân loại exception.

**Dùng idempotence để giải quyết duplicate từ consumer.** Consumer re-delivery có nguyên nhân ở offset và thời điểm commit. Xử lý bằng consumer idempotency hoặc transaction phù hợp.

## 13. Quy trình áp dụng cho producer bền vững

Khi đưa idempotence vào một Spring Kafka service, có thể thực hiện theo trình tự sau:

1. Xác định phiên bản Kafka client và cách ứng dụng tạo `ProducerFactory`.
2. Bật `enable.idempotence=true` trên tất cả producer cần bảo vệ.
3. Đặt `acks=all`, `retries>0` và `max.in.flight.requests.per.connection<=5`.
4. Chọn `delivery.timeout.ms`, `request.timeout.ms` và `linger.ms` phù hợp với latency SLO.
5. Xác nhận topic có replication factor và `min.insync.replicas` phù hợp với yêu cầu durability.
6. Theo dõi retry, error, latency, buffer và replication health.
7. Bổ sung business event ID, outbox hoặc consumer deduplication cho duplicate ngoài phạm vi producer retry.
8. Nếu cần atomic consume-transform-produce trong Kafka, đánh giá Kafka transactions và cấu hình Spring Kafka tương ứng.
9. Ghi rõ phạm vi bảo đảm trong tài liệu vận hành để đội phát triển không nhầm idempotent producer với exactly-once end-to-end.

## 14. Ghi nhớ

`enable.idempotence=true` giúp Kafka producer retry an toàn hơn bằng cách gắn PID và sequence number vào các batch. Broker dùng trạng thái producer theo partition để nhận ra lần gửi lặp và tránh append duplicate do retry nội bộ.

Trong Spring Kafka, cấu hình này nằm ở producer được `ProducerFactory` tạo ra và được `KafkaTemplate` sử dụng. Để hoạt động đúng, producer cần `acks=all`, `retries>0` và `max.in.flight.requests.per.connection<=5`.

Idempotence là nền tảng quan trọng cho producer bền vững. Để bảo vệ nghiệp vụ qua cả luồng event, hệ thống vẫn cần quản lý business identity, consumer processing, offset commit, outbox/inbox hoặc Kafka transactions tùy yêu cầu.

