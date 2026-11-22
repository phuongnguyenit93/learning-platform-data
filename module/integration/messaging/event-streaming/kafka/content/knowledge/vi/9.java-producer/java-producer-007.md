# Quản lý producer dùng chung và đặc tính an toàn đa luồng

Trong ứng dụng Java, một Kafka producer thường được tạo một lần và dùng chung cho nhiều luồng xử lý. Đây là cách sử dụng phù hợp vì **KafkaProducer được thiết kế thread-safe**: nhiều thread có thể đồng thời gọi send trên cùng một instance. Producer quản lý buffer, batch và một luồng I/O nền để gửi dữ liệu đến broker.

Tạo một producer mới cho từng request hoặc từng message thường gây lãng phí kết nối, buffer, thread và tài nguyên broker. Với Spring Kafka, KafkaTemplate cũng được thiết kế để dùng chung trong ứng dụng; template sử dụng ProducerFactory để quản lý producer phía dưới.

Dùng chung instance không có nghĩa mọi đối tượng liên quan đều tự động an toàn đa luồng. State trong service, custom serializer, partitioner, interceptor và callback vẫn cần được thiết kế cẩn thận. Đặc biệt, transaction có trạng thái riêng và không cho phép nhiều transaction đồng thời trên cùng một producer.

## 1. Vì sao nên dùng chung KafkaProducer?

Một KafkaProducer không chỉ là một đối tượng giữ cấu hình. Khi khởi tạo, nó thiết lập và quản lý nhiều thành phần phục vụ gửi dữ liệu:

- Kết nối đến broker và quá trình lấy metadata topic/partition.
- RecordAccumulator để gom record thành batch theo partition.
- Buffer để giữ dữ liệu đang chờ gửi.
- Sender thread nền để gửi request và nhận phản hồi từ broker.
- Serializer, partitioner và interceptor theo cấu hình.
- Metrics và trạng thái retry, idempotence hoặc transaction nếu được bật.

Nếu tạo producer cho từng request, ứng dụng có thể tạo ra rất nhiều kết nối, thread và buffer. Việc khởi tạo và đóng producer liên tục cũng làm mất lợi ích batching, tăng overhead và gây áp lực lên broker.

Mô hình thường phù hợp:

~~~text
Application
    |
    +-- Request thread 1 ----+
    +-- Request thread 2 ----+----> Shared KafkaProducer
    +-- Worker thread 3 -----+             |
    +-- Worker thread 4 -----+             v
                                      RecordAccumulator
                                             |
                                             v
                                        Sender thread
                                             |
                                             v
                                      Kafka brokers
~~~

Nhiều thread gọi send trên cùng producer. Producer gom record theo partition và gửi batch qua luồng I/O nền. Ứng dụng không cần tự tạo một sender thread cho mỗi request.

## 2. KafkaProducer thread-safe có nghĩa gì?

KafkaProducer cho phép nhiều thread cùng gọi các API của producer trên một instance. Ví dụ, nhiều request có thể đồng thời gọi:

- send(record)
- partitionsFor(topic)
- metrics()
- flush()

Producer phối hợp trạng thái nội bộ để các thao tác gửi có thể diễn ra đồng thời an toàn.

Ví dụ đơn giản:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>("orders", "order-42", "created");

producer.send(record);
~~~

Nếu producer là một instance dùng chung, nhiều thread có thể gọi send đồng thời mà không cần tự đồng bộ toàn bộ lời gọi bằng synchronized.

Tuy nhiên, thread-safe của KafkaProducer không làm cho dữ liệu ứng dụng hoặc những component tùy biến trở nên thread-safe. Cần phân biệt:

| Thành phần | Có thể dùng chung? | Điều cần chú ý |
|---|---|---|
| KafkaProducer | Có | Được thiết kế thread-safe; quản lý lifecycle đúng cách |
| KafkaTemplate | Có | Thread-safe khi dùng với ProducerFactory phù hợp |
| ProducerFactory | Có | Dùng cấu hình và chiến lược quản lý producer nhất quán |
| Service publisher | Có | Tránh giữ state mutable theo từng request trong field |
| Custom Serializer | Có thể được gọi đồng thời | Nên stateless hoặc tự bảo vệ state mutable |
| Custom Partitioner | Có thể được gọi đồng thời | Không dùng dữ liệu mutable không được đồng bộ |
| ProducerInterceptor | Có thể nhận callback ở nhiều luồng | Xử lý đồng thời giữa onSend và onAcknowledgement |
| Callback | Có thể chạy trên luồng I/O | Không block lâu hoặc thực hiện công việc nặng |

Một nguyên tắc dễ áp dụng là giữ producer và cấu hình dùng chung, còn dữ liệu của từng lần gửi nên nằm trong biến cục bộ hoặc object bất biến.

## 3. Quản lý lifecycle của producer

Producer cần được khởi tạo, sử dụng và đóng theo vòng đời của ứng dụng.

### 3.1. Tạo producer một lần

Với Java thuần, có thể tạo producer ở tầng quản lý ứng dụng rồi truyền nó cho các service cần gửi sự kiện:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.common.serialization.StringSerializer;

public final class KafkaProducerProvider {
    private final KafkaProducer<String, String> producer;

    public KafkaProducerProvider(String bootstrapServers) {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", bootstrapServers);
        properties.put(
            "key.serializer",
            StringSerializer.class.getName()
        );
        properties.put(
            "value.serializer",
            StringSerializer.class.getName()
        );
        properties.put("acks", "all");
        properties.put("enable.idempotence", "true");

        this.producer = new KafkaProducer<>(properties);
    }

    public KafkaProducer<String, String> getProducer() {
        return producer;
    }

    public void close() {
        producer.close();
    }
}
~~~

Đối tượng provider cần được quản lý ở cấp ứng dụng. Các service nhận cùng instance producer thông qua dependency injection hoặc constructor injection.

Không nên để mỗi controller hoặc mỗi lần xử lý message tự tạo một KafkaProducer mới.

### 3.2. Đóng producer khi ứng dụng dừng

close() giải phóng kết nối, buffer và thread nền. Khi đóng producer, Kafka cố gắng hoàn tất các request đang chờ theo hành vi close và timeout được cấu hình.

Với Java thuần, try-with-resources là một cách quản lý rõ ràng khi producer có phạm vi sống xác định:

~~~java
Properties properties = new Properties();
// Cấu hình bootstrap server, serializer và các thuộc tính khác.

try (KafkaProducer<String, String> producer =
         new KafkaProducer<>(properties)) {
    producer.send(
        new ProducerRecord<>("orders", "order-42", "created")
    );
    producer.flush();
}
~~~

Trong service chạy lâu dài, producer thường sống cùng application context. Chỉ đóng nó khi ứng dụng shutdown hoặc thành phần sở hữu nó kết thúc.

Không gọi close() sau mỗi lần send(). Sau khi producer đóng, các thread khác không thể tiếp tục sử dụng instance đó.

### 3.3. Không đóng producer trong khi thread khác còn gửi

Một lỗi thường gặp là một request gọi close trong khi các request khác vẫn đang dùng producer. Khi đó, các thao tác gửi có thể thất bại hoặc không hoàn thành như mong muốn.

Quy trình shutdown nên có thứ tự:

1. Ngừng nhận công việc mới cần gửi Kafka.
2. Chờ các tác vụ đang gửi hoàn tất việc gọi send.
3. Flush hoặc chờ các future gửi hoàn tất theo chính sách ứng dụng.
4. Đóng producer.
5. Hoàn tất shutdown của application.

Trong Spring Boot, nên để container quản lý lifecycle của bean và producer factory thay vì tự đóng producer bên trong từng service method.

## 4. Gửi đồng thời từ nhiều thread

Ví dụ dưới đây dùng một producer duy nhất cho nhiều worker thread:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class ConcurrentProducerExample {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", "localhost:9092");
        properties.put(
            "key.serializer",
            StringSerializer.class.getName()
        );
        properties.put(
            "value.serializer",
            StringSerializer.class.getName()
        );
        properties.put("acks", "all");
        properties.put("enable.idempotence", "true");

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {

            ExecutorService workers =
                Executors.newFixedThreadPool(4);

            try {
                List<Future<?>> tasks = new ArrayList<>();

                for (int i = 0; i < 100; i++) {
                    final int eventNumber = i;

                    tasks.add(workers.submit(() -> {
                        String key = "order-" + (eventNumber % 10);
                        String value = "event-" + eventNumber;

                        producer.send(
                            new ProducerRecord<>(
                                "orders",
                                key,
                                value
                            )
                        );
                    }));
                }

                for (Future<?> task : tasks) {
                    task.get();
                }

                // Chờ các record đã gửi hoàn tất trước khi thoát.
                producer.flush();
            } finally {
                workers.shutdown();
                if (!workers.awaitTermination(1, TimeUnit.MINUTES)) {
                    workers.shutdownNow();
                }
            }
        }
    }
}
~~~

Trong ví dụ này:

- Chỉ có một KafkaProducer được tạo.
- Bốn worker thread cùng gọi send.
- Mỗi lần gửi có key và value riêng.
- flush() được gọi sau khi các worker đã hoàn tất việc gọi send.
- Producer được đóng khi thoát khỏi try-with-resources.

send() là bất đồng bộ, vì vậy việc lời gọi send trả về không đồng nghĩa broker đã xác nhận record. flush() ở cuối ví dụ chờ các record đã được gửi hoàn tất trước khi đóng producer.

Trong ứng dụng production, cần xử lý exception của từng tác vụ, kiểm soát thời gian shutdown và quan sát kết quả gửi. Không nên dùng một vòng lặp vô hạn tạo thêm task nếu producer buffer hoặc broker không theo kịp tốc độ đầu vào.

## 5. send() bất đồng bộ và luồng callback

KafkaProducer.send() thông thường trả về ngay sau khi record được thêm vào buffer nội bộ, thay vì chờ broker ghi xong. Sender thread nền gom batch và gửi request đến broker.

Có hai nơi lỗi có thể xuất hiện:

- **Lỗi đồng bộ trong lúc gọi send:** ví dụ serializer lỗi, record không hợp lệ hoặc không thể lấy buffer/metadata trong giới hạn chờ.
- **Lỗi bất đồng bộ:** broker từ chối request, request timeout hoặc lỗi xảy ra trong quá trình gửi; ứng dụng nhận lỗi qua Future hoặc callback.

Ví dụ dùng callback:

~~~java
producer.send(
    new ProducerRecord<>("orders", "order-42", "created"),
    (metadata, exception) -> {
        if (exception != null) {
            // Ghi nhận lỗi gửi và chuyển vào chính sách xử lý phù hợp.
            return;
        }

        System.out.printf(
            "topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
);
~~~

Callback của KafkaProducer thường được thực thi trên luồng I/O của producer. Vì vậy:

- Không thực hiện truy vấn database chậm trong callback.
- Không gọi dịch vụ HTTP đồng bộ trong callback.
- Không chờ một future khác có thể phụ thuộc vào chính producer.
- Không thực hiện phép tính nặng làm chặn sender thread.
- Nếu cần công việc tiếp theo, chuyển nó sang executor riêng có giới hạn tài nguyên.

Callback có thể được gọi trong quá trình xử lý phản hồi của producer. Nếu callback làm chậm luồng I/O, những request khác cũng có thể bị chậm theo.

### 5.1. Future và chờ kết quả

Có thể chờ kết quả gửi bằng Future.get(), nhưng không nên gọi get ngay sau mọi send trong đường xử lý cần throughput cao:

~~~java
Future<RecordMetadata> future = producer.send(record);
RecordMetadata metadata = future.get();
~~~

Cách này biến thao tác bất đồng bộ thành đồng bộ tại thread gọi. Nếu nhiều request cùng chờ broker, số thread bị giữ có thể tăng nhanh.

Nên chọn cách phù hợp:

- Callback hoặc CompletableFuture cho xử lý tiếp theo bất đồng bộ.
- Chờ future khi cần kết quả đồng bộ ở ranh giới nghiệp vụ cụ thể.
- Gom nhiều future và chờ theo batch khi cần đồng bộ có kiểm soát.
- Thiết lập timeout và xử lý lỗi rõ ràng nếu phải chờ.

### 5.2. send() không hoàn toàn không block

Mặc dù gửi bất đồng bộ, send() vẫn có thể chờ trong một số trường hợp, chẳng hạn chờ metadata hoặc chờ buffer khả dụng. Thời gian chờ liên quan đến các cấu hình như max.block.ms và trạng thái của producer.

Nếu producer liên tục nhận dữ liệu nhanh hơn khả năng gửi, buffer có thể đầy. Khi đó ứng dụng cần backpressure hoặc giới hạn lượng công việc đang chờ, thay vì tạo thêm thread và task không giới hạn.

## 6. Dùng producer dùng chung trong Spring Kafka

Trong Spring Boot, KafkaTemplate là abstraction phổ biến để gửi record. Có thể khai báo ProducerFactory và KafkaTemplate thành bean dùng chung.

Ví dụ cấu hình:

~~~java
@Configuration
public class KafkaProducerConfig {

    @Bean
    public ProducerFactory<String, OrderCreated> producerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        properties.put(
            ProducerConfig.ACKS_CONFIG,
            "all"
        );
        properties.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> kafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

Ví dụ minh họa các bean cần thiết; ứng dụng cần khai báo import và dependency Spring Kafka tương ứng. Trong môi trường thực tế, bootstrap server, serializer, security và các thuộc tính khác nên được đưa vào external configuration.

KafkaTemplate được thiết kế thread-safe và có thể được inject vào nhiều singleton service. ProducerFactory quản lý việc tạo, tái sử dụng hoặc cache producer tùy cấu hình. Vì vậy, không cần tạo một KafkaTemplate mới cho mỗi request.

### 6.1. Service publisher dạng singleton

Spring service mặc định thường là singleton. Có thể dùng chung KafkaTemplate như sau:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "orders",
            event.orderId(),
            event
        );
    }
}
~~~

Service không giữ biến mutable đại diện cho request hiện tại. Mỗi lần gọi nhận event qua tham số và gửi bằng KafkaTemplate dùng chung.

Nếu cần log kết quả:

~~~java
publisher.publish(event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            // Ghi event ID và nguyên nhân lỗi.
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();
        // Ghi topic, partition và offset.
    });
~~~

Không nên gọi get() hoặc join() trong mọi request chỉ để chờ kết quả nếu ứng dụng có thể xử lý bất đồng bộ. Cũng không nên dùng callback để thực hiện công việc downstream nặng.

## 7. Những đối tượng tùy biến cần chú ý khi dùng chung

KafkaProducer thread-safe, nhưng các thành phần do ứng dụng cung cấp có thể được gọi từ nhiều thread.

### 7.1. Custom Serializer

Serializer có thể được gọi đồng thời khi nhiều thread gửi record. Nếu serializer giữ bộ đếm, buffer tái sử dụng hoặc cache mutable, cần đảm bảo truy cập an toàn.

Ví dụ serializer không nên dùng một StringBuilder mutable dùng chung mà không đồng bộ:

~~~java
public class UnsafeSerializer implements Serializer<MyEvent> {
    private final StringBuilder builder = new StringBuilder();

    @Override
    public byte[] serialize(String topic, MyEvent data) {
        builder.setLength(0);
        builder.append(data.id());
        builder.append(":");
        builder.append(data.name());
        return builder.toString().getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Trong ví dụ này, hai thread có thể đồng thời sửa cùng StringBuilder, khiến kết quả serialize bị trộn lẫn.

Cách an toàn hơn là dùng biến cục bộ:

~~~java
public class SafeSerializer implements Serializer<MyEvent> {

    @Override
    public byte[] serialize(String topic, MyEvent data) {
        if (data == null) {
            return null;
        }

        String value = data.id() + ":" + data.name();
        return value.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Nếu serializer dùng thư viện có object mutable hoặc buffer dùng lại, cần đọc tài liệu thư viện và bảo vệ state tương ứng.

### 7.2. Custom Partitioner

Partitioner có thể được gọi khi nhiều thread gửi record. Không nên lưu state mutable dùng chung trong partitioner nếu không có cơ chế đồng bộ phù hợp.

Nếu logic phân vùng cần cache hoặc bảng định tuyến, hãy dùng cấu trúc chỉ đọc sau khi khởi tạo, hoặc cơ chế concurrent phù hợp. Quy tắc partitioning cũng cần nhất quán giữa các producer nếu ứng dụng yêu cầu các event cùng key luôn đi về cùng partition.

### 7.3. ProducerInterceptor

ProducerInterceptor có hai điểm cần lưu ý:

- onSend() được gọi trong luồng gọi send.
- onAcknowledgement() được gọi khi producer xử lý kết quả gửi, thường trên luồng I/O.

Do đó, cùng một interceptor có thể được truy cập từ nhiều luồng và các phương thức có thể chạy đồng thời. Tránh dùng một biến mutable không được bảo vệ để lưu trạng thái của từng record. Nếu cần correlation ID, hãy gắn nó vào record header hoặc một object theo từng lần gửi.

### 7.4. Callback và state của service

Một callback có thể chạy sau khi method publish đã trả về. Không nên giữ tham chiếu đến request object có thể bị thay đổi hoặc giải phóng bởi thread khác.

Nên:

- Dùng event immutable.
- Sao chép dữ liệu cần thiết vào biến cục bộ.
- Không cập nhật collection mutable dùng chung nếu không có đồng bộ.
- Chuyển công việc nặng sang executor có giới hạn.
- Đưa correlation ID vào log để nối kết producer request với callback.

## 8. Dùng chung producer và ordering

Nhiều thread có thể gọi send trên cùng producer, nhưng điều đó không tự bảo đảm thứ tự theo thứ tự request bắt đầu ở các thread.

Nếu hai thread đồng thời gửi event cho cùng một key, thứ tự record được xác định theo thứ tự producer thực tế chấp nhận và append record vào partition, không nhất thiết theo thời điểm nghiệp vụ mà hai thread được tạo hoặc bắt đầu chạy.

Ví dụ:

~~~text
Thread A: bắt đầu gửi OrderCreated
Thread B: bắt đầu gửi PaymentAuthorized

Do scheduling:
  Thread B gọi send trước
  Thread A gọi send sau

Partition có thể nhận:
  PaymentAuthorized
  OrderCreated
~~~

Nếu nghiệp vụ cần thứ tự, cần kiểm soát thứ tự phát sự kiện ở tầng ứng dụng:

- Tuần tự hóa thao tác phát event theo từng aggregate hoặc key.
- Dùng sequence number hoặc version cho mỗi thực thể.
- Chỉ phát event tiếp theo sau khi bước trước đã được xác nhận theo yêu cầu nghiệp vụ.
- Dùng cùng key để các record đi về cùng partition.
- Ở consumer, kiểm tra version và xử lý duplicate hoặc event đến sai thứ tự.

Kafka đảm bảo thứ tự trong một partition. Producer dùng chung chỉ đảm bảo an toàn truy cập API; nó không thay thế cơ chế sắp xếp nghiệp vụ giữa các thread.

## 9. Transaction và giới hạn khi chia sẻ producer

KafkaProducer hỗ trợ transaction, nhưng transaction có trạng thái: bắt đầu, gửi record, commit hoặc abort. Một producer transactional chỉ có thể có một transaction đang mở tại một thời điểm.

Không nên để nhiều thread cùng thao tác beginTransaction(), commitTransaction() hoặc abortTransaction() trên một producer mà không có cơ chế phối hợp. Nếu hai luồng đan xen thao tác transaction, ranh giới dữ liệu của mỗi nghiệp vụ có thể bị trộn hoặc một luồng kết thúc transaction của luồng khác.

Với Java producer thuần:

~~~java
producer.beginTransaction();
try {
    producer.send(recordA);
    producer.send(recordB);
    producer.commitTransaction();
} catch (Exception exception) {
    producer.abortTransaction();
    throw exception;
}
~~~

Đoạn mã trên minh họa một transaction được điều khiển tuần tự bởi một luồng logic. Không dùng cùng producer để mở nhiều transaction đồng thời từ nhiều thread.

### 9.1. Spring Kafka và transaction theo thread

Spring Kafka hỗ trợ quản lý producer transactional thông qua ProducerFactory, KafkaTransactionManager và transaction support của KafkaTemplate.

Trong mô hình Spring, transaction thường được gắn với thread thực thi. ProducerFactory cung cấp transactional producer phù hợp và quản lý cache/lifecycle. Điều này cho phép KafkaTemplate được inject và dùng chung trong ứng dụng, trong khi transaction resource được quản lý theo ngữ cảnh thread.

Ví dụ khái quát:

~~~java
@Configuration
public class KafkaTransactionConfig {

    @Bean
    public ProducerFactory<String, OrderCreated> transactionalProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        properties.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        DefaultKafkaProducerFactory<String, OrderCreated> factory =
            new DefaultKafkaProducerFactory<>(properties);

        factory.setTransactionIdPrefix("orders-service-");
        return factory;
    }

    @Bean
    public KafkaTransactionManager<String, OrderCreated>
            kafkaTransactionManager(
                ProducerFactory<String, OrderCreated> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
~~~

Trong ứng dụng thật, transaction ID prefix phải được cấu hình duy nhất cho từng application instance đang chạy đồng thời và ProducerFactory cần có khả năng cấp transactional producer phù hợp với concurrency. Không để hai producer đang hoạt động đồng thời dùng cùng transactional ID vì producer mới có thể fence producer cũ.

Cấu hình transaction của Spring Kafka phụ thuộc phiên bản Spring Kafka và cách tích hợp transaction manager. Hãy đồng bộ cấu hình listener, KafkaTemplate và transaction manager theo cùng ProducerFactory khi muốn tham gia cùng transaction.

### 9.2. Kafka transaction không bao phủ mọi hệ thống bên ngoài

Kafka transaction có thể bảo đảm tính nguyên tử cho các thao tác Kafka được đưa vào transaction, chẳng hạn ghi nhiều topic/partition và phối hợp offset consumer trong mô hình consume-transform-produce phù hợp.

Nó không tự động tạo một transaction phân tán bao trùm database hoặc REST service. Nếu service vừa cập nhật database vừa gửi Kafka, cần thiết kế outbox hoặc cơ chế phối hợp khác để xử lý lỗi giữa hai hệ thống.

## 10. Cấu hình producer hỗ trợ vận hành ổn định

Dùng chung producer cần đi cùng cấu hình phù hợp. Một số thuộc tính quan trọng:

| Cấu hình | Vai trò |
|---|---|
| bootstrap.servers | Danh sách broker dùng lấy metadata ban đầu |
| acks | Mức xác nhận khi ghi |
| enable.idempotence | Giảm duplicate do retry ở producer |
| retries | Số lần thử lại request lỗi có thể retry |
| delivery.timeout.ms | Thời gian tối đa để hoàn tất một lần gửi |
| request.timeout.ms | Thời gian chờ phản hồi request |
| max.block.ms | Giới hạn thời gian một số API đồng bộ chờ metadata hoặc buffer |
| buffer.memory | Dung lượng buffer giữ record chờ gửi |
| batch.size | Kích thước batch mục tiêu theo partition |
| linger.ms | Thời gian chờ thêm record để gom batch |
| compression.type | Cơ chế nén batch |

Không nên tăng buffer.memory hoặc số thread vô hạn khi broker không theo kịp. Cần giới hạn lượng request đang chờ, theo dõi send latency, buffer availability và lỗi timeout.

Với producer cần durability, có thể cân nhắc acks=all và idempotence. Cấu hình idempotence cần tương thích với các thuộc tính retries, acks và số request in-flight theo yêu cầu của phiên bản Kafka client. Các client hiện đại tự áp dụng một số giá trị tương thích khi idempotence được bật, nhưng vẫn cần kiểm tra cấu hình hiệu lực.

## 11. Những lỗi thường gặp khi quản lý producer dùng chung

- **Tạo producer cho mỗi request:** tăng kết nối, thread, buffer và chi phí khởi tạo.
- **Đóng producer sau mỗi lần gửi:** làm các request khác dùng instance đã đóng và phá vỡ lifecycle.
- **Cho rằng mọi object được gọi bởi producer đều thread-safe:** custom serializer, partitioner, interceptor và state của service cần được kiểm tra riêng.
- **Block callback:** làm chậm sender I/O thread và ảnh hưởng các request khác.
- **Gọi future.get() ngay sau mỗi send:** biến luồng gửi bất đồng bộ thành đồng bộ, làm giảm khả năng xử lý đồng thời.
- **Không giới hạn đầu vào:** producer buffer đầy khi tốc độ nhận lớn hơn tốc độ gửi, khiến send có thể chờ đến max.block.ms.
- **Dùng một producer cho nhiều transaction đồng thời:** transaction state bị xung đột; cần quản lý transaction theo thread hoặc producer riêng do framework cấp.
- **Dùng chung transactional ID giữa nhiều instance:** có thể khiến producer bị fencing.
- **Dựa vào thứ tự thread bắt đầu để suy ra thứ tự record:** scheduling có thể khiến send được gọi theo thứ tự khác.
- **Không chờ gửi hoàn tất khi shutdown:** các record đang buffer có thể không được hoàn thành theo mong đợi.

## 12. Checklist thiết kế producer dùng chung

Trước khi triển khai, hãy xác nhận:

| Câu hỏi | Hướng xử lý |
|---|---|
| Producer được tạo ở đâu? | Tạo một lần trong application lifecycle hoặc do ProducerFactory quản lý |
| Có dùng chung instance giữa các thread không? | Có thể dùng chung KafkaProducer/KafkaTemplate |
| Service có state mutable theo request không? | Đưa state về biến cục bộ hoặc dùng cơ chế concurrent phù hợp |
| Serializer/partitioner/interceptor có thread-safe không? | Dùng implementation stateless hoặc bảo vệ state |
| Callback có làm việc nặng không? | Chuyển sang executor riêng và giới hạn queue |
| Có kiểm soát tốc độ gửi không? | Dùng backpressure, giới hạn task và theo dõi buffer |
| Shutdown có đúng thứ tự không? | Ngừng nhận việc, chờ gửi hoàn tất, rồi đóng producer |
| Có dùng transaction không? | Một transaction đang mở trên mỗi transactional producer; quản lý producer theo thread |
| Nhiều instance có transactional ID riêng không? | Cấu hình prefix/ID không trùng giữa các instance đồng thời |
| Có yêu cầu ordering theo key không? | Kiểm soát phát event và dùng key ổn định |

## 13. Kết luận

KafkaProducer được thiết kế thread-safe và thường nên được tạo một lần để nhiều thread dùng chung. Producer quản lý buffer, batch và sender thread nền, vì vậy chia sẻ một instance giúp giảm overhead kết nối và tận dụng batching tốt hơn. Trong Spring Kafka, KafkaTemplate cũng có thể được inject vào nhiều singleton service và dùng đồng thời.

Điều cần quản lý là lifecycle, callback và các thành phần tùy biến. Không đóng producer khi còn request đang sử dụng, không block sender thread trong callback và không giả định serializer, partitioner hoặc state của service tự động an toàn đa luồng. Với transaction, mỗi transactional producer chỉ nên có một transaction đang mở tại một thời điểm; Spring Kafka quản lý producer transactional theo ngữ cảnh thread thông qua ProducerFactory và transaction manager.

Thiết kế producer dùng chung tốt kết hợp instance sống theo application lifecycle, gửi bất đồng bộ có kiểm soát, idempotence phù hợp, backpressure và quy trình shutdown rõ ràng. Nhờ đó, ứng dụng có thể gửi sự kiện đồng thời từ nhiều thread mà vẫn giữ được khả năng quan sát lỗi và tính nhất quán nghiệp vụ.
