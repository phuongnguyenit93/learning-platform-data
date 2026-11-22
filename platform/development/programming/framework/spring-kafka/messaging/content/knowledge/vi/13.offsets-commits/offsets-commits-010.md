# Đọc lại record sau khi xử lý lỗi

Kafka consumer đọc record theo offset của từng partition. Khi listener xử lý một record thất bại, ứng dụng cần quyết định sẽ thử lại record đó, chuyển nó sang dead-letter topic (DLT), hay chủ động đọc lại một đoạn log để khôi phục dữ liệu. Cơ chế này liên quan trực tiếp đến vị trí đọc hiện tại, offset đã commit và cách Spring Kafka xử lý lỗi.

Hiểu đúng offset giúp tránh hai rủi ro đối lập: commit quá sớm khiến record lỗi bị bỏ qua, còn commit quá muộn có thể làm record đã xử lý thành công bị đọc lại. Trong phần lớn ứng dụng messaging, nên thiết kế consumer chịu được việc xử lý lặp, sau đó chọn retry hoặc replay theo loại lỗi và yêu cầu nghiệp vụ.

## 1. Vì sao Kafka có thể đọc lại một record?

Kafka không xóa record khi consumer đọc xong. Consumer group lưu tiến độ đọc bằng offset đã commit cho từng topic-partition. Khi consumer khởi động hoặc được giao partition, nó tiếp tục từ vị trí đọc dựa trên offset đã commit và chính sách `auto.offset.reset`.

Giả sử partition `orders.events-0` có các record:

```text
offset:     40       41       42       43       44
record:  OrderA   OrderB   OrderC   OrderD   OrderE
```

Consumer xử lý thành công record offset `40` và `41`, nhưng record `42` gây lỗi. Nếu group đã commit vị trí tiếp theo là `42`, consumer có thể quay lại đọc record ở offset `42` sau khi retry, restart hoặc được gán partition lại.

Offset commit thường biểu diễn **vị trí tiếp theo cần đọc**, không phải offset cuối cùng đã xử lý:

| Record đã xử lý | Offset record | Offset commit tương ứng |
|---|---:|---:|
| `OrderA` | 40 | 41 nếu chỉ mới xử lý đến record này |
| `OrderB` | 41 | 42 nếu đã xử lý đến record này |
| `OrderC` | 42 | 43 nếu đã xử lý đến record này |

Vì vậy, `ConsumerRecord.offset()` bằng `42` và committed offset bằng `42` có ý nghĩa khác nhau: record hiện tại có offset 42, còn vị trí commit 42 yêu cầu consumer tiếp tục từ offset 42.

## 2. Hai rủi ro khi commit offset

Thời điểm commit phải phù hợp với thời điểm hoàn thành side effect nghiệp vụ.

### Commit trước khi xử lý xong

Nếu consumer commit offset `43` trước khi xử lý record offset `42` hoàn tất, rồi ứng dụng gặp lỗi hoặc tiến trình dừng, lần đọc tiếp theo có thể bắt đầu từ `43`. Record `42` đã bị vượt qua dù nghiệp vụ chưa hoàn thành.

```text
Đọc record 42
      |
      v
Commit offset 43
      |
      v
Ghi database thất bại
      |
      v
Restart -> đọc từ offset 43

Record 42 chưa được xử lý thành công nhưng đã bị bỏ qua.
```

### Xử lý xong nhưng chưa commit

Nếu listener đã ghi database thành công nhưng tiến trình dừng trước khi commit offset, Kafka vẫn xem record đó chưa được xác nhận. Khi consumer đọc lại, cùng side effect có thể được thực hiện lần nữa.

```text
Đọc record 42
      |
      v
Ghi database thành công
      |
      v
Tiến trình dừng trước khi commit
      |
      v
Restart -> đọc lại record 42

Side effect có thể bị thực hiện hai lần.
```

Đó là lý do consumer thường được thiết kế theo hướng at-least-once: ưu tiên không bỏ qua record, chấp nhận khả năng nhận lại và làm cho xử lý có tính idempotent.

## 3. Spring Kafka xử lý record listener lỗi như thế nào?

Khi một phương thức `@KafkaListener` ném exception, listener container chuyển lỗi tới `CommonErrorHandler` được cấu hình. Với record listener, `DefaultErrorHandler` là lựa chọn phổ biến để retry và phục hồi record lỗi.

Theo cơ chế seek mặc định, khi xử lý lỗi, error handler đưa consumer position trở lại record thất bại và các record tiếp theo trong kết quả poll cần được xử lý lại. Các record đã xử lý trước record lỗi có thể được commit theo acknowledgement mode. Khi consumer poll tiếp, record lỗi được đọc lại thay vì bị bỏ qua.

Ví dụ listener để exception truyền lên container:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        // Nếu xử lý thất bại, ném exception để container/error handler quyết định retry.
        process(record.key(), record.value());
    }

    private void process(String orderId, String payload) {
        // Thực hiện nghiệp vụ; ném exception nếu cần retry hoặc recover.
    }
}
```

Nếu listener bắt exception rồi chỉ ghi log mà không ném lại, container xem lần gọi listener đã hoàn tất bình thường và có thể commit offset. Chỉ bắt lỗi khi ứng dụng đã xử lý hoặc chuyển lỗi theo một quy trình có chủ đích.

## 4. Retry tại chỗ bằng DefaultErrorHandler

`DefaultErrorHandler` hỗ trợ retry với `BackOff`. Ví dụ sau chờ một giây giữa các lần thử và thực hiện tối đa hai lần retry sau lần xử lý đầu tiên. Nếu vẫn thất bại, `DeadLetterPublishingRecoverer` gửi record tới DLT.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        // Lỗi dữ liệu không hợp lệ không được retry vì retry không sửa được payload.
        handler.addNotRetryableExceptions(IllegalArgumentException.class);
        return handler;
    }
}
```

Để áp dụng error handler vào listener container factory, cấu hình factory như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<Object, Object> kafkaListenerContainerFactory(
            ConsumerFactory<Object, Object> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

        var factory = new ConcurrentKafkaListenerContainerFactory<Object, Object>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Trong Spring Boot, hãy bảo đảm factory được listener sử dụng thực sự nhận `CommonErrorHandler`. Nếu ứng dụng khai báo factory riêng, phải gắn handler vào factory đó; chỉ tạo bean error handler mà listener không sử dụng factory tương ứng sẽ không tạo ra hành vi retry mong muốn.

`FixedBackOff(interval, maxAttempts)` dùng `maxAttempts` làm số lần retry sau lần xử lý đầu. Với ví dụ trên, một record có thể được xử lý lần đầu và retry tối đa hai lần trước khi recover. Có thể dùng `ExponentialBackOff` hoặc backoff khác để tăng khoảng chờ giữa các lần thử.

### Chọn lỗi có thể retry

Không phải lỗi nào cũng nên retry:

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Timeout ngắn của database hoặc dịch vụ ngoài | Retry có giới hạn và backoff |
| Lỗi mạng tạm thời | Retry, đồng thời giới hạn thời gian và số lần thử |
| Payload sai schema hoặc dữ liệu nghiệp vụ không hợp lệ | Không retry hoặc retry sau khi có sửa đổi dữ liệu; thường chuyển DLT |
| Thiếu cấu hình hoặc quyền truy cập | Dừng/cảnh báo và khắc phục cấu hình; retry vô hạn không giải quyết nguyên nhân |
| Lỗi do hệ thống phụ thuộc quá tải | Backoff đủ dài, giới hạn retry và theo dõi áp lực lên dependency |

Nếu lỗi được đánh dấu non-retryable, error handler bỏ qua các lần retry thông thường và chuyển thẳng tới bước recover. Hãy cân nhắc kỹ danh sách exception vì phân loại sai có thể làm record bị đưa vào DLT quá sớm hoặc bị retry vô ích.

## 5. Đọc lại record sau khi hết retry: Dead-letter topic

Khi retry tại chỗ hết số lần cho phép, ứng dụng có thể chuyển record lỗi sang dead-letter topic để luồng chính tiếp tục. `DeadLetterPublishingRecoverer` thường tạo topic đích bằng cách thêm hậu tố `-dlt` vào tên topic nguồn và giữ partition tương ứng.

Ví dụ:

```text
orders.events, partition 2, offset 42
             |
             | xử lý lỗi, retry hết giới hạn
             v
orders.events-dlt, partition 2
```

Nếu dùng cách định tuyến mặc định và nguồn có partition 2, DLT cần có partition 2. Nói chung, DLT nên có số partition ít nhất bằng topic nguồn, trừ khi ứng dụng cấu hình destination resolver khác.

DLT chứa record để điều tra hoặc xử lý lại sau này. Spring Kafka thường bổ sung headers mô tả topic, partition, offset nguồn và exception xảy ra. Cần giữ cấu hình serializer/deserializer phù hợp với kiểu key/value mà recoverer gửi; nếu payload đã deserialize thành object, producer của DLT phải serialize được object đó.

Khi recoverer gửi DLT thành công, container có thể xác nhận record nguồn đã được xử lý theo acknowledgement mode và cấu hình error handler. Với cấu hình mặc định, `DefaultErrorHandler` có `ackAfterHandle` bật để container commit sau khi handler xử lý thành công mà không ném exception. Nếu recoverer gửi DLT thất bại và ném exception, không nên xem record đã recover; cần để cơ chế xử lý lỗi tiếp tục retry hoặc báo lỗi theo cấu hình.

Nếu dùng `AckMode.MANUAL_IMMEDIATE` và muốn error handler commit offset của record đã recover, có thể cấu hình `setCommitRecovered(true)`. Thuộc tính này yêu cầu acknowledgement mode phù hợp; không bật tùy tiện khi container đang dùng chế độ khác.

## 6. Retry tại chỗ và retry topic khác nhau thế nào?

Retry tại chỗ (blocking retry) giữ việc xử lý trên luồng consumer hiện tại. Error handler chờ backoff rồi seek để đọc lại record lỗi. Trong thời gian đó, các record phía sau trên cùng luồng có thể bị chặn bởi record lỗi.

Spring Kafka cũng hỗ trợ non-blocking retry bằng `@RetryableTopic`. Cơ chế này chuyển record lỗi sang retry topic có độ trễ, cho phép consumer tiếp tục đọc các record tiếp theo trên topic chính. Khi tới thời điểm retry, record được đọc từ retry topic; nếu hết retry, nó được chuyển tới DLT.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
class PaymentListener {

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(delay = 1_000, multiplier = 2.0),
            dltTopicSuffix = "-dlt"
    )
    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Xử lý thanh toán; ném exception nếu nghiệp vụ thất bại.
    }
}
```

Trong ví dụ, `attempts` biểu thị tổng số lần thử theo semantics của annotation, bao gồm lần xử lý ban đầu. Spring Kafka tạo các retry topic cần thiết theo cấu hình backoff và chuyển record tới DLT khi hết số lần thử. Cấu hình topic, naming và hành vi cụ thể có thể tùy phiên bản Spring Kafka.

| Tiêu chí | Retry tại chỗ | Retry topic |
|---|---|---|
| Cách retry | Seek và đọc lại trong consumer hiện tại | Publish sang topic retry rồi đọc lại sau |
| Consumer bị chặn bởi record lỗi | Có thể bị chặn trong thời gian backoff/retry | Topic chính có thể tiếp tục xử lý record sau |
| Thứ tự nghiệp vụ | Giữ luồng xử lý partition theo cơ chế seek | Có thể thay đổi thứ tự vì record sau được xử lý trước record đang chờ retry |
| Hạ tầng | Chủ yếu cấu hình error handler | Cần retry topic và DLT phù hợp |
| Trường hợp phù hợp | Lỗi ngắn, cần giữ thứ tự partition | Lỗi cần thời gian chờ dài và chấp nhận thay đổi thứ tự |

`DefaultErrorHandler` với seek và `@RetryableTopic` là hai cách retry khác nhau; hãy chọn cơ chế phù hợp cho listener thay vì mặc định xem chúng là hai tầng retry sẽ tự động nối tiếp nhau. Non-blocking retry có các giới hạn theo phiên bản và kiểu listener; trong các phiên bản Spring Kafka phổ biến, cơ chế này không hỗ trợ batch listener hoặc container transaction. Hãy kiểm tra tài liệu đúng phiên bản của dự án trước khi áp dụng. Không chọn retry topic chỉ vì nó giảm blocking nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key.

## 7. Đọc lại một record bằng seek trong Spring Kafka

Trong một số tình huống, ứng dụng cần chủ động đưa consumer về một offset cụ thể. Spring Kafka cung cấp `ConsumerSeekAware` để listener nhận callback seek trên luồng consumer, chẳng hạn khi partition được gán.

```java
import java.util.Map;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.ConsumerSeekAware.ConsumerSeekCallback;
import org.springframework.stereotype.Component;

@Component
class ReplayOrderListener implements ConsumerSeekAware {

    private final Map<TopicPartition, Long> replayOffsets = Map.of(
            new TopicPartition("orders.events", 0), 42L
    );

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.keySet().forEach(partition -> {
            Long targetOffset = replayOffsets.get(partition);
            if (targetOffset != null) {
                callback.seek(
                        partition.topic(),
                        partition.partition(),
                        targetOffset
                );
            }
        });
    }

    @KafkaListener(topics = "orders.events", groupId = "order-replay")
    public void consume(String payload) {
        processReplay(payload);
    }

    private void processReplay(String payload) {
        // Xử lý sự kiện trong luồng replay.
    }
}
```

Đây là ví dụ minh họa một replay offset đã được ứng dụng xác định. Trong hệ thống thực tế, offset mục tiêu nên được lấy từ cấu hình hoặc kho lưu trữ có kiểm soát; không hard-code offset vào mã nguồn.

`seek()` thay đổi vị trí đọc hiện tại của consumer trên partition. Nó không tự ghi committed offset mới vào Kafka. Nếu consumer dừng trước khi xử lý và commit tiến độ mới, lần gán partition tiếp theo có thể bắt đầu từ committed offset cũ. Vì vậy, seek phù hợp cho điều khiển replay trong phiên consumer; muốn thay đổi vị trí đọc bền vững qua lần restart, cần commit offset mới hoặc reset group offset.

Chỉ seek trên partition đang được consumer sở hữu và thực hiện qua callback/API của Spring Kafka để thao tác diễn ra trên đúng luồng consumer. Không gọi trực tiếp `KafkaConsumer.seek()` từ thread nghiệp vụ khác.

## 8. Reset committed offset để replay một đoạn log

Khi cần chạy lại dữ liệu cho cả consumer group, có thể dùng công cụ `kafka-consumer-groups.sh` để reset committed offset. Đây là thao tác thay đổi tiến độ đọc đã lưu của group, nên cần thực hiện có kế hoạch.

Ví dụ kiểm tra offset group hiện tại:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --describe
```

Để xem trước việc đưa partition 0 của topic về offset 42:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders.events:0 \
  --reset-offsets \
  --to-offset 42 \
  --dry-run
```

Sau khi xác minh đúng group, topic, partition và offset, thực thi:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group order-projection \
  --topic orders.events:0 \
  --reset-offsets \
  --to-offset 42 \
  --execute
```

Consumer group cần không có consumer đang hoạt động khi reset offset bằng công cụ quản trị. Hãy dừng các instance thuộc group trước, kiểm tra lại bằng `--describe`, chạy `--dry-run`, rồi mới dùng `--execute`. Sau khi reset, khởi động consumer và xác nhận lag/offset bắt đầu tại vị trí mong muốn.

`--to-offset 42` đặt vị trí tiếp theo cần đọc là 42, nghĩa là consumer có thể đọc lại record offset 42. Nếu chọn offset đã bị xóa do retention hoặc không còn hợp lệ, cần xác định lại phạm vi dữ liệu còn tồn tại trước khi reset.

Reset offset ảnh hưởng đến toàn bộ consumer group/partition được chỉ định. Nếu nhiều ứng dụng dùng chung group ID, tất cả sẽ chịu tác động. Muốn replay phục vụ điều tra mà không ảnh hưởng luồng production, cân nhắc tạo một consumer group riêng để đọc lại dữ liệu.

## 9. Replay có an toàn với database và dịch vụ ngoài không?

Replay khiến record được xử lý lại. Kafka chỉ quản lý log và offset; nó không tự hoàn tác side effect đã ghi vào database hoặc gửi tới HTTP service. Vì vậy, cần thiết kế thao tác nghiệp vụ idempotent.

Một số cách thường dùng:

- Mỗi event có `eventId` duy nhất; database lưu event ID đã xử lý với ràng buộc unique.
- Dùng upsert hoặc cập nhật trạng thái theo phiên bản để xử lý lặp không tạo bản ghi trùng.
- Với mô hình inbox, lưu event ID và thay đổi nghiệp vụ trong cùng transaction database.
- Nếu consumer vừa ghi database vừa publish event mới, cân nhắc transactional outbox để tránh trạng thái database đã cập nhật nhưng event đầu ra chưa được gửi.
- Đặt giới hạn replay và theo dõi số lượng record xử lý lại để tránh tạo tải đột biến lên hệ thống phụ thuộc.

Kafka transaction có thể phối hợp việc publish record Kafka và commit offset trong cùng transaction Kafka khi cấu hình đúng. Nó không tự động đưa database hoặc dịch vụ HTTP bên ngoài vào cùng transaction. Exactly-once ở ranh giới Kafka không đồng nghĩa side effect ngoài Kafka tự động chỉ xảy ra một lần.

## 10. Batch listener và record lỗi

Với batch listener, một lần poll có thể đưa nhiều record vào cùng một lần gọi listener. Khi chỉ một record trong batch lỗi, ứng dụng cần xác định record lỗi để tránh xử lý lại cả batch không cần thiết.

Spring Kafka hỗ trợ `BatchListenerFailedException` để chỉ ra index hoặc record gây lỗi. `DefaultErrorHandler` có thể commit các record đứng trước record lỗi và seek phần lỗi cùng các record phía sau để đọc lại theo cơ chế batch error handling.

Nếu batch listener không xác định được record lỗi, error handler có thể phải retry/replay toàn bộ batch tùy cấu hình và phiên bản. Hãy bảo đảm xử lý các record trong batch có thể lặp an toàn và không commit vượt qua record chưa xử lý thành công.

## 11. Transactional listener và xử lý lỗi sau rollback

Nếu listener container chạy trong Kafka transaction, exception có thể làm transaction rollback. Với mô hình này, việc xử lý lại sau rollback thường do `AfterRollbackProcessor` quản lý, thay vì chỉ dựa trên `DefaultErrorHandler` như container không transaction.

Sau rollback, consumer có thể seek về record hoặc batch cần xử lý lại. Khi vượt số lần retry, after-rollback processor có thể recover record, ví dụ publish sang DLT trong transaction phù hợp. Cần kiểm tra cấu hình transaction manager, producer transaction ID prefix, acknowledgement và after-rollback processor theo phiên bản Spring Kafka.

Transaction Kafka giúp phối hợp output record và offset commit trong Kafka. Nếu listener ghi database ngoài Kafka, cần cơ chế phối hợp riêng như database transaction kết hợp inbox/outbox hoặc distributed transaction nếu hệ thống hỗ trợ.

## 12. Quy trình chọn cách đọc lại record

| Tình huống | Cơ chế phù hợp |
|---|---|
| Lỗi dependency ngắn, có thể tự phục hồi | `DefaultErrorHandler` và backoff retry tại chỗ |
| Dữ liệu không hợp lệ hoặc lỗi không thể retry | Recoverer và DLT |
| Lỗi cần chờ lâu, muốn luồng chính tiếp tục | `@RetryableTopic` và retry topics nếu chấp nhận thay đổi thứ tự |
| Cần đọc lại một partition từ offset cụ thể trong runtime | `ConsumerSeekAware` hoặc API seek do Spring Kafka quản lý |
| Cần replay bền vững cho cả group | Dừng consumer và reset committed offset bằng công cụ quản trị |
| Cần phân tích lại dữ liệu mà không ảnh hưởng production | Dùng consumer group riêng |

Trước khi replay, hãy xác định phạm vi topic/partition/offset, kiểm tra retention, dừng hoặc cô lập consumer phù hợp, đánh giá side effect và chọn nơi ghi kết quả. Sau replay, theo dõi consumer lag, lỗi lặp, DLT và tải database để xác nhận luồng đã ổn định.

## 13. Những nhầm lẫn thường gặp

1. **Cho rằng offset record là offset commit.** Record offset `42` và committed offset `42` không đồng nghĩa; commit `42` biểu thị vị trí tiếp theo cần đọc.
2. **Bắt exception rồi không ném lại.** Container có thể xem listener đã xử lý thành công và commit offset, khiến record lỗi không được retry.
3. **Cho rằng seek thay đổi committed offset.** Seek chỉ thay đổi vị trí đọc hiện tại; muốn thay đổi tiến độ bền vững phải commit hoặc reset offset.
4. **Retry vô hạn mọi exception.** Lỗi dữ liệu hoặc cấu hình không tự biến mất; cần phân loại retryable và non-retryable.
5. **Cho rằng gửi DLT thất bại vẫn được coi là recover.** Chỉ khi recoverer hoàn tất theo cấu hình mới nên xác nhận record nguồn; lỗi publish DLT cần được xử lý.
6. **Dùng retry topic mà không xem xét thứ tự.** Record sau có thể được xử lý trước record đang chờ retry.
7. **Reset offset khi consumer group vẫn đang chạy.** Hãy dừng consumer và dry-run để tránh thay đổi tiến độ ngoài dự kiến.
8. **Cho rằng replay không tạo side effect lặp.** Database, email hoặc API có thể bị gọi lại; cần idempotency hoặc transaction phù hợp.
9. **Cho rằng Kafka transaction bao gồm database.** Transaction Kafka không tự động bao phủ tài nguyên ngoài Kafka.

Đọc lại record là khả năng quan trọng để khôi phục luồng messaging sau lỗi. Với Spring Kafka, hãy chọn retry tại chỗ, retry topic, DLT, seek hoặc reset offset theo đúng phạm vi cần khôi phục; đồng thời hiểu rõ thời điểm commit và bảo đảm side effect nghiệp vụ chịu được việc xử lý lặp.
