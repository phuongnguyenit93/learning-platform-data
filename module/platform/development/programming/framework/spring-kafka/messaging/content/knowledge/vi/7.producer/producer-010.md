# Lỗi khi gửi và khả năng thử lại

## 1. Vì sao thao tác gửi Kafka có thể thất bại?

Khi ứng dụng gọi `KafkaTemplate.send(...)`, producer phải chuyển key và value thành byte, lấy metadata của topic, đưa record vào bộ đệm, gửi request đến broker và chờ xác nhận theo cấu hình `acks`. Bất kỳ bước nào cũng có thể phát sinh lỗi.

Một số nguyên nhân thường gặp:

| Nhóm nguyên nhân | Ví dụ | Hướng xử lý |
|---|---|---|
| Kết nối và broker | Broker mất kết nối, leader partition đang thay đổi, request timeout | Kiểm tra cluster, mạng và để producer retry trong giới hạn cấu hình |
| Cấu hình và quyền | Sai địa chỉ broker, thiếu quyền ghi topic, lỗi xác thực | Sửa cấu hình hoặc quyền; retry liên tục không giải quyết được lỗi cố định |
| Dữ liệu và serialization | Serializer không hỗ trợ kiểu object, payload sai định dạng | Sửa serializer hoặc dữ liệu trước khi gửi |
| Giới hạn tài nguyên | Record vượt giới hạn kích thước, producer buffer đầy | Kiểm tra kích thước record, cấu hình broker và tải producer |
| Xác nhận bản ghi | Không đủ replica trong ISR để đáp ứng `acks=all` | Kiểm tra replication factor, ISR và `min.insync.replicas` |

Không phải mọi lỗi đều có thể khắc phục bằng cách gửi lại. Lỗi kết nối tạm thời có thể biến mất sau một khoảng chờ; lỗi serializer, quyền truy cập hoặc topic sai thường vẫn xảy ra cho đến khi cấu hình hay dữ liệu được sửa.

## 2. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Trong Spring Kafka 3.x, `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K, V>>`. Tuy nhiên, việc gọi `send` vẫn có thể phát sinh lỗi ngay trong thread hiện tại, ví dụ khi không thể lấy metadata trong thời gian cho phép hoặc producer không thể chấp nhận record. Sau khi lời gọi trả về future, lỗi từ quá trình gửi thường được báo qua trạng thái exceptional của future.

Vì vậy, cần quan sát cả hai đường lỗi:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.support.SendResult;

public void publish(OrderCreatedEvent event) {
    CompletableFuture<SendResult<String, OrderCreatedEvent>> future;

    try {
        future = kafkaTemplate.send("orders", event.orderId(), event);
    } catch (RuntimeException ex) {
        // Lỗi xảy ra ngay khi gọi send().
        log.error("Không thể khởi tạo thao tác gửi Kafka", ex);
        throw ex;
    }

    future.whenComplete((result, error) -> {
        if (error != null) {
            log.error("Gửi sự kiện thất bại", error);
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Gửi thành công topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
}
~~~

Future hoàn tất thành công có nghĩa producer nhận được acknowledgement theo cấu hình `acks`. Nó không có nghĩa consumer đã nhận hoặc xử lý xong sự kiện. Hai tiến trình gửi và tiêu thụ có cơ chế xác nhận riêng.

Nếu chỉ gọi `send(...)` rồi bỏ qua future, ứng dụng có thể không quan sát được lỗi xảy ra sau đó. Với sự kiện quan trọng, phải có nơi ghi nhận kết quả, đo lường và quyết định cách xử lý khi gửi thất bại.

## 3. Producer tự retry ở tầng Kafka client

Kafka producer có cơ chế retry cho các lỗi mà client xem là có thể thử lại, chẳng hạn một số lỗi mạng, lỗi leader tạm thời hoặc lỗi xác nhận replica. Producer có thể gửi lại request trong khoảng thời gian cho phép mà ứng dụng không cần gọi `KafkaTemplate.send(...)` lần nữa.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `retries` | Giới hạn số lần producer thử lại với lỗi retriable; giá trị hữu hiệu còn chịu giới hạn thời gian giao record |
| `delivery.timeout.ms` | Tổng thời gian tối đa để producer hoàn tất việc gửi, bao gồm chờ metadata, thời gian gửi và retry |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request gửi đến broker |
| `retry.backoff.ms` | Khoảng chờ ban đầu giữa các lần retry |
| `retry.backoff.max.ms` | Giới hạn trên của khoảng chờ retry khi client hỗ trợ backoff tăng dần |
| `acks` | Mức xác nhận mà producer yêu cầu từ broker |
| `enable.idempotence` | Bật producer idempotence để chống ghi trùng do retry nội bộ của producer |

Có thể cấu hình trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        retry.backoff.ms: 500
        retry.backoff.max.ms: 10000
        linger.ms: 5
~~~

`delivery.timeout.ms` phải lớn hơn hoặc bằng tổng `request.timeout.ms` và `linger.ms`. Nếu đặt thời gian giao quá ngắn, producer có thể hết hạn trước khi cơ hội retry đủ để khôi phục kết nối hoặc chờ broker ổn định.

Với Kafka client hiện đại, `enable.idempotence` thường đã được bật mặc định khi các cấu hình liên quan tương thích. Khai báo tường minh giúp ý định cấu hình dễ nhận biết hơn. Khi idempotence được bật, producer cần các điều kiện tương thích như `acks=all`, `retries` lớn hơn 0 và `max.in.flight.requests.per.connection` không vượt quá giới hạn Kafka hỗ trợ (hiện là 5). Kafka client hiện đại tự kiểm tra hoặc điều chỉnh các ràng buộc này tùy phiên bản.

`acks=all` yêu cầu leader chờ các replica đang nằm trong ISR xác nhận. Nó không có nghĩa mọi replica của topic đều phải phản hồi. Mức bảo vệ dữ liệu còn phụ thuộc replication factor và `min.insync.replicas`.

### Retry nội bộ không đồng nghĩa retry vô hạn

Producer chỉ thử lại trong giới hạn `delivery.timeout.ms` và các điều kiện của request. Khi hết thời gian, future hoàn tất thất bại. Cấu hình retry lớn không làm một broker ngừng hoạt động trở thành hoạt động trở lại; nó chỉ cho producer thêm cơ hội vượt qua lỗi tạm thời.

Không nên đặt timeout rất dài một cách tùy tiện. Timeout dài làm tăng thời gian ứng dụng phải chờ kết quả và có thể giữ record trong bộ đệm lâu hơn. Hãy chọn thời gian dựa trên SLA gửi tin, khả năng phục hồi của cluster và mức chậm mà nghiệp vụ chấp nhận.

## 4. Producer idempotence giúp retry an toàn hơn như thế nào?

Khi broker đã ghi record nhưng acknowledgement bị mất trên đường về, producer có thể không biết chắc record đã được ghi hay chưa. Nếu gửi lại, cùng một record có nguy cơ xuất hiện hai lần.

Producer idempotence sử dụng producer ID và sequence number để broker nhận diện các lần gửi lại thuộc cùng một producer session. Khi được cấu hình đúng, Kafka có thể loại bỏ bản ghi trùng phát sinh từ retry nội bộ đó trong phạm vi bảo đảm của producer idempotence.

Tuy nhiên, idempotence không tự loại bỏ bản ghi trùng do ứng dụng gọi `send(...)` thêm lần nữa. Hai lời gọi send mới được xem là hai thao tác gửi riêng biệt, dù payload giống nhau.

Cần phân biệt:

| Tình huống | Producer idempotence xử lý ra sao? |
|---|---|
| Producer tự gửi lại request do lỗi mạng trong cùng producer session | Có thể chống ghi trùng theo cơ chế sequence number |
| Ứng dụng gọi `send` lần thứ hai sau khi future đầu tiên thất bại hoặc timeout | Không tự nhận biết đó là cùng một sự kiện nghiệp vụ |
| Ứng dụng khởi động lại và phát lại sự kiện từ database | Không tự khử trùng lặp theo event ID nghiệp vụ |
| Consumer xử lý xong nhưng chưa commit offset rồi nhận lại record | Không thuộc phạm vi bảo đảm của producer idempotence |

Với sự kiện nghiệp vụ quan trọng, nên có `eventId` duy nhất và thiết kế consumer idempotent. Consumer có thể lưu `eventId` đã xử lý cùng kết quả nghiệp vụ trong một giao dịch phù hợp để bỏ qua lần nhận lại.

## 5. Khi nào cần retry ở tầng ứng dụng?

Retry nội bộ của producer thường là lựa chọn đầu tiên vì nó hoạt động ngay trong một lần gửi. Retry ở tầng ứng dụng chỉ nên thêm khi nghiệp vụ cần chính sách riêng, ví dụ:

- Muốn giới hạn số lần thử lại khác với chính sách chung của producer.
- Cần backoff, jitter hoặc thời gian chờ riêng theo loại sự kiện.
- Cần ghi nhận trạng thái gửi thất bại để vận hành hoặc xử lý lại.
- Cần chuyển sự kiện sang một luồng phục hồi riêng sau khi hết số lần thử.

Trước khi retry, phải phân loại lỗi:

| Loại lỗi | Ví dụ | Có nên tự động gửi lại? |
|---|---|---|
| Lỗi tạm thời, có thể phục hồi | Một số lỗi mạng hoặc leader thay đổi | Có thể, với giới hạn và backoff |
| Kết quả chưa xác định | Timeout sau khi broker có thể đã ghi record nhưng acknowledgement chưa đến | Chỉ khi chấp nhận khả năng trùng và có cơ chế idempotent |
| Lỗi dữ liệu | Serialization lỗi, record quá lớn | Không; sửa dữ liệu hoặc cấu hình trước |
| Lỗi quyền hoặc cấu hình cố định | Authentication/authorization thất bại, topic sai | Không; sửa nguyên nhân trước |
| Lỗi nghiệp vụ | Dữ liệu không hợp lệ theo quy tắc nghiệp vụ | Không; cần xử lý dữ liệu hoặc đưa vào quy trình nghiệp vụ riêng |

Một timeout cần được xem xét cẩn thận: producer có thể đã ghi record nhưng ứng dụng chưa nhận được acknowledgement. Nếu ứng dụng gửi lại ngay, sự kiện có thể được ghi hai lần. Đừng coi mọi future thất bại là bằng chứng broker chưa nhận record.

### Ví dụ retry có giới hạn bằng Spring Retry

Khi nghiệp vụ chấp nhận khả năng gửi trùng và consumer đã có cơ chế idempotent, có thể dùng `RetryTemplate` của Spring Retry để bổ sung số lần thử lại ở tầng ứng dụng. Ví dụ sau chỉ retry lỗi được phân loại rõ là lỗi tạm thời; lỗi timeout không xác định kết quả được ném ra riêng để xử lý theo chính sách khác.

Cần có dependency `org.springframework.retry:spring-retry`:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class ProducerRetryConfiguration {

    @Bean
    RetryTemplate producerRetryTemplate() {
        var retryPolicy = new SimpleRetryPolicy(
            3,
            Map.of(TransientPublishException.class, true),
            false
        );

        var backOffPolicy = new ExponentialBackOffPolicy();
        backOffPolicy.setInitialInterval(200);
        backOffPolicy.setMultiplier(2.0);
        backOffPolicy.setMaxInterval(2000);

        var template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backOffPolicy);
        return template;
    }
}
~~~

Trong cấu hình này, `maxAttempts = 3` tính cả lần gọi đầu tiên, tức tối đa hai lần retry bổ sung. `SimpleRetryPolicy` chỉ nhận `TransientPublishException`, nên các lỗi khác không bị thử lại tự động.

Exception riêng để biểu diễn lỗi mà chính sách cho phép thử lại:

~~~java
public class TransientPublishException extends RuntimeException {

    public TransientPublishException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PublishOutcomeUnknownException extends RuntimeException {

    public PublishOutcomeUnknownException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Phương thức gửi đồng bộ dưới đây minh họa cách chờ kết quả và chuyển lỗi sang loại exception phù hợp. Đặt phương thức này trên worker thread hoặc luồng xử lý nền vì `get()` chặn thread hiện tại:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.common.errors.RetriableException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;

@Component
public class RetryingOrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final RetryTemplate producerRetryTemplate;

    public RetryingOrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            RetryTemplate producerRetryTemplate) {
        this.kafkaTemplate = kafkaTemplate;
        this.producerRetryTemplate = producerRetryTemplate;
    }

    public SendResult<String, OrderCreatedEvent> publish(
            String topic,
            OrderCreatedEvent event) {

        return producerRetryTemplate.execute(context -> {
            try {
                return kafkaTemplate.send(
                    topic,
                    event.orderId(),
                    event
                ).get(15, TimeUnit.SECONDS);

            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Luồng gửi Kafka bị gián đoạn", ex
                );

            } catch (TimeoutException ex) {
                throw new PublishOutcomeUnknownException(
                    "Hết thời gian chờ; chưa xác định broker đã ghi record hay chưa",
                    ex
                );

            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();

                if (cause instanceof org.apache.kafka.common.errors.TimeoutException) {
                    throw new PublishOutcomeUnknownException(
                        "Producer timeout; cần kiểm tra khả năng ghi trùng trước khi gửi lại",
                        cause
                    );
                }

                if (cause instanceof RetriableException) {
                    throw new TransientPublishException(
                        "Gặp lỗi Kafka có thể phục hồi", cause
                    );
                }

                throw new IllegalStateException(
                    "Lỗi gửi Kafka không thể retry tự động", cause
                );
            }
        });
    }
}
~~~

Ví dụ này có một chủ đích quan trọng: chỉ `TransientPublishException` được `RetryTemplate` thử lại. `PublishOutcomeUnknownException` không nằm trong retry policy. Trong thực tế, cần kiểm tra loại lỗi cụ thể, phiên bản Kafka client và tình huống broker để quyết định một lỗi có an toàn để gửi lại hay không. Ngay cả lỗi retriable cũng có thể có kết quả ghi chưa rõ; vì vậy chỉ bật retry ứng dụng khi nghiệp vụ chịu được duplicate hoặc có cơ chế khử trùng lặp bằng `eventId`.

`RetryTemplate` chạy đồng bộ và giữ thread trong thời gian chờ. Với lưu lượng lớn, hãy cân nhắc worker queue, scheduler hoặc một tiến trình gửi nền có lưu trạng thái thay vì chặn request thread.

## 6. Backoff và giới hạn retry

Nếu retry liên tục ngay khi gặp lỗi, nhiều producer có thể cùng dồn request vào broker đang quá tải. Hiện tượng này làm tăng áp lực và kéo dài thời gian phục hồi.

Exponential backoff tăng dần khoảng chờ giữa các lần thử:

| Lần thử | Khoảng chờ minh họa |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |

Có thể thêm jitter (một độ lệch ngẫu nhiên nhỏ) để các instance không cùng retry đúng một thời điểm. Cần đặt giới hạn số lần thử, tổng thời gian retry và chính sách khi hết lượt.

Một chính sách retry cần trả lời:

- Thử lại lỗi nào?
- Tối đa bao nhiêu lần?
- Khoảng chờ tăng như thế nào?
- Tổng thời gian tối đa là bao lâu?
- Kết quả timeout chưa rõ được xử lý ra sao?
- Sau khi hết lượt, sự kiện được lưu ở đâu để không mất?
- Ai hoặc thành phần nào chịu trách nhiệm xử lý lại?

Không retry vô hạn trong thread của request. Cách đó có thể làm cạn thread pool, giữ tài nguyên và khiến hệ thống khó phục hồi khi broker ngừng hoạt động dài.

## 7. Hết retry thì làm gì?

Khi producer không gửi được sự kiện sau các lần thử, ứng dụng cần một chính sách cuối cùng. Với sự kiện không quan trọng, có thể ghi log và trả lỗi cho luồng gọi. Với sự kiện nghiệp vụ quan trọng, chỉ ghi log thường không đủ vì ứng dụng có thể mất cơ hội gửi lại sau khi tiến trình kết thúc.

Một số cách xử lý:

| Cách xử lý | Phù hợp khi |
|---|---|
| Trả lỗi cho caller | Caller có thể giữ yêu cầu và quyết định thử lại |
| Lưu trạng thái thất bại trong database | Cần tra cứu, hỗ trợ vận hành và xử lý lại |
| Transactional Outbox | Cần bảo đảm ý định phát sự kiện được lưu cùng giao dịch cập nhật database |
| Hàng đợi phục hồi riêng | Hệ thống có một kênh lưu trữ bền vững để worker xử lý lại sau |
| Bỏ sự kiện sau khi ghi nhận | Chỉ phù hợp với sự kiện có thể mất theo yêu cầu nghiệp vụ đã thống nhất |

### Transactional Outbox cho sự kiện quan trọng

Một tình huống phổ biến là ứng dụng vừa cập nhật đơn hàng trong database vừa phát `OrderCreated` lên Kafka. Nếu database commit thành công nhưng gửi Kafka thất bại, trạng thái đơn hàng và luồng sự kiện bị lệch nhau.

Transactional Outbox giải quyết vấn đề bằng cách ghi dữ liệu nghiệp vụ và một bản ghi outbox trong cùng transaction database. Một worker riêng đọc outbox, gửi sự kiện lên Kafka, rồi đánh dấu bản ghi đã phát thành công. Nếu Kafka tạm ngừng, worker có thể tiếp tục thử lại sau khi hệ thống phục hồi.

~~~mermaid
flowchart TD
    A["Application service"] --> B["Database transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["KafkaTemplate"]
    G --> H["Kafka topic"]
    H --> I["Mark outbox as published"]
~~~

Outbox không loại bỏ hoàn toàn khả năng gửi trùng: worker có thể gửi thành công rồi dừng trước khi đánh dấu outbox. Vì thế, outbox publisher thường phát theo cơ chế at-least-once và consumer vẫn cần idempotent theo `eventId`.

## 8. Producer failure khác với consumer failure và dead-letter topic

Cần phân biệt nơi phát sinh lỗi:

- **Producer failure:** ứng dụng chưa xác nhận được record đã được Kafka ghi. Không có một record đầu vào trong Kafka để framework tự động chuyển sang dead-letter topic.
- **Consumer failure:** record đã nằm trong topic nhưng listener xử lý thất bại. Spring Kafka có thể dùng error handler, retry topic hoặc dead-letter publishing để xử lý record lỗi theo cấu hình.
- **Business rejection:** dữ liệu đã được đọc nhưng không hợp lệ theo quy tắc nghiệp vụ. Đây có thể là kết quả nghiệp vụ cần ghi nhận riêng, không nhất thiết là lỗi gửi Kafka.

Vì vậy, không nên dùng `DeadLetterPublishingRecoverer` hoặc `@RetryableTopic` như cơ chế mặc định để retry một lần gửi producer thất bại. Với producer failure, hãy dùng retry của producer, chính sách retry ở tầng ứng dụng và một nơi lưu bền vững như outbox khi cần.

## 9. Quan sát lỗi gửi trong Spring Kafka

Ngoài callback của future, Spring Kafka cung cấp `ProducerListener` để nhận thông báo khi gửi thành công hoặc thất bại. Có thể dùng listener này để ghi log hoặc cập nhật metric tập trung:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.ProducerListener;

public class LoggingProducerListener
        implements ProducerListener<String, OrderCreatedEvent> {

    @Override
    public void onSuccess(
            ProducerRecord<String, OrderCreatedEvent> record,
            RecordMetadata metadata) {
        log.info(
            "Kafka send success topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }

    @Override
    public void onError(
            ProducerRecord<String, OrderCreatedEvent> record,
            RecordMetadata metadata,
            Exception exception) {
        log.error(
            "Kafka send failed topic={}, key={}",
            record.topic(),
            record.key(),
            exception
        );
    }
}
~~~

Đăng ký listener vào template bằng cấu hình Spring hoặc gọi `kafkaTemplate.setProducerListener(...)` khi tạo template. `ProducerListener` phù hợp cho logging và metric chung. Nếu một luồng nghiệp vụ cần quyết định có trả lỗi cho caller, lưu outbox hay đánh dấu trạng thái, hãy quan sát future tại nơi gọi và truyền kết quả về đúng application service.

Nên theo dõi ít nhất:

- Số record gửi thành công và thất bại.
- Số lần retry và tỷ lệ lỗi sau retry.
- Độ trễ từ lúc gọi send đến lúc nhận acknowledgement.
- Timeout, lỗi serialization, lỗi xác thực và lỗi broker.
- Số bản ghi outbox đang chờ gửi và tuổi của bản ghi cũ nhất.
- Tỷ lệ duplicate mà consumer phát hiện nếu có cơ chế khử trùng lặp.

Không ghi payload nhạy cảm vào log chỉ để điều tra lỗi. Hãy ưu tiên `eventId`, correlation ID, topic, key đã được phép ghi, partition và mã lỗi.

## 10. Checklist thiết kế retry cho producer

- [ ] Đã quan sát cả lỗi đồng bộ khi gọi `send()` và lỗi bất đồng bộ từ future.
- [ ] Đã cấu hình `acks`, idempotence và thời gian giao phù hợp với yêu cầu.
- [ ] Hiểu giới hạn của `delivery.timeout.ms` và `request.timeout.ms`.
- [ ] Phân loại lỗi tạm thời, lỗi cố định và kết quả timeout chưa xác định.
- [ ] Dùng retry nội bộ của producer trước khi thêm retry tầng ứng dụng.
- [ ] Retry ứng dụng có giới hạn, backoff và chỉ áp dụng cho lỗi được chọn.
- [ ] Consumer có cơ chế idempotent khi nghiệp vụ có thể nhận sự kiện trùng.
- [ ] Sự kiện quan trọng có nơi lưu bền vững, chẳng hạn Transactional Outbox.
- [ ] Không nhầm producer failure với consumer failure và dead-letter topic.
- [ ] Có log, metric và cảnh báo khi lỗi gửi hoặc outbox tồn đọng tăng.

Khả năng retry giúp producer vượt qua lỗi tạm thời, nhưng không thể thay thế thiết kế lưu trữ bền vững và xử lý trùng lặp. Trong Spring Kafka, hãy bắt đầu với retry nội bộ của Kafka producer, quan sát kết quả qua future, chỉ bổ sung retry tầng ứng dụng khi có chính sách rõ ràng, và dùng Transactional Outbox cho những sự kiện không được phép mất.
