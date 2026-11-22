# Retry ở consumer bằng error handler

Consumer Kafka có thể gặp lỗi tạm thời khi xử lý sự kiện: database mất kết nối trong vài giây, dịch vụ HTTP timeout hoặc hệ thống phụ thuộc đang quá tải. Nếu listener ném exception ra ngoài, Spring Kafka có thể giao việc xử lý lỗi cho error handler để thử lại record theo chính sách đã cấu hình. Khi hết số lần thử mà vẫn thất bại, ứng dụng cần một quyết định phục hồi như chuyển record sang dead-letter topic (DLT), ghi nhận lỗi để xử lý thủ công hoặc dừng luồng theo yêu cầu nghiệp vụ.

Retry ở consumer giúp xử lý lỗi có khả năng tự hết, nhưng phải có giới hạn và cách xác nhận offset rõ ràng. Retry vô hạn có thể giữ partition ở một record lỗi, làm consumer lag tăng và ảnh hưởng các record phía sau. Bài học này trình bày cách cấu hình `DefaultErrorHandler`, chọn backoff, phân loại exception, kết hợp DLT và theo dõi hành vi retry trong Spring Kafka.

## 1. Luồng xử lý khi listener phát sinh lỗi

Khi `@KafkaListener` xử lý một record, Spring Kafka gọi phương thức listener trong listener container. Nếu phương thức kết thúc bình thường, container tiếp tục theo `AckMode` và chính sách commit offset. Nếu listener ném exception, container chuyển lỗi tới error handler đã cấu hình.

Với record listener, `DefaultErrorHandler` có thể thực hiện retry tại consumer hiện tại. Sau khi xử lý thành công, container tiếp tục và xác nhận offset theo cấu hình. Nếu đã hết retry, error handler gọi recoverer; recoverer có thể gửi record sang DLT. Khi recovery thành công, offset nguồn được xử lý theo chính sách của handler và container. Nếu recovery thất bại, record chưa được coi là đã phục hồi thành công và lỗi cần được xử lý tiếp.

```mermaid
flowchart TD
    A[Kafka giao record] --> B[@KafkaListener xử lý]
    B --> C{Có exception?}
    C -->|Không| D[Container xử lý commit theo AckMode]
    C -->|Có| E[DefaultErrorHandler]
    E --> F[Chờ theo BackOff]
    F --> G[Thử xử lý lại record]
    G --> H{Thành công?}
    H -->|Có| D
    H -->|Không, còn lượt| E
    H -->|Hết lượt| I[Recoverer]
    I --> J{Recovery thành công?}
    J -->|Có| K[Tiếp tục theo chính sách offset]
    J -->|Không| L[Giữ trạng thái lỗi và phát tín hiệu vận hành]
```

Điều kiện đầu tiên để retry hoạt động là listener phải để exception truyền ra ngoài. Nếu listener bắt exception, chỉ ghi log rồi trả về bình thường, container thường xem lần gọi đó là thành công và error handler không nhận được lỗi để retry.

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    orderService.process(event); // Exception được truyền tới container
}
```

Nếu cần bổ sung ngữ cảnh, hãy ghi log rồi ném lại exception hoặc bọc nó trong exception nghiệp vụ có giữ nguyên cause. Không bắt `Exception` chung chung rồi tiếp tục như thể record đã được xử lý thành công.

## 2. Cấu hình `DefaultErrorHandler` và backoff

`DefaultErrorHandler` là common error handler được Spring Kafka cung cấp cho listener container. Handler nhận một `BackOff` để quyết định thời gian chờ và số lần retry. Ví dụ dưới đây cho phép retry ba lần, mỗi lần cách nhau một giây:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler() {
        DefaultErrorHandler handler = new DefaultErrorHandler(
                new FixedBackOff(1_000L, 3L));
        return handler;
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
```

Listener dùng factory đã cấu hình:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

Với `FixedBackOff(1_000L, 3L)`, tham số đầu là khoảng nghỉ một giây và tham số thứ hai là số lần retry sau lần xử lý ban đầu. Vì vậy, một record có thể được gọi tối đa bốn lần: một lần đầu và ba lần retry. Nếu muốn chỉ xử lý một lần, hãy dùng chính sách không retry thay vì nhầm lẫn giữa số lần retry và tổng số lần gọi.

`BackOff` quyết định nhịp thử lại, không làm cho một lỗi vĩnh viễn trở thành lỗi tạm thời. Khoảng nghỉ ngắn phù hợp với gián đoạn ngắn; khoảng nghỉ dài có thể giảm áp lực lên dịch vụ đang quá tải nhưng làm record chờ lâu hơn. Hãy chọn cả số lần retry lẫn tổng thời gian chờ dựa trên thời gian phục hồi dự kiến và yêu cầu độ trễ của nghiệp vụ.

## 3. Chọn chiến lược backoff

Các chính sách phổ biến có đặc điểm khác nhau:

| Chính sách | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `FixedBackOff` | Chờ một khoảng cố định giữa các lần retry | Lỗi tạm thời có thời gian phục hồi tương đối ổn định; cấu hình đơn giản. |
| `ExponentialBackOff` | Tăng dần khoảng chờ sau mỗi lần thất bại, có giới hạn theo cấu hình | Dịch vụ phụ thuộc đang quá tải hoặc thời gian phục hồi khó dự đoán. |
| Backoff tùy biến | Ứng dụng quyết định thời gian chờ dựa trên loại lỗi hoặc ngữ cảnh | Các nhóm lỗi cần chính sách retry khác nhau. |

Ví dụ dùng `ExponentialBackOff`:

```java
ExponentialBackOff backOff = new ExponentialBackOff(500L, 2.0);
backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
```

Ví dụ này bắt đầu chờ 500 ms, tăng khoảng chờ theo hệ số 2 và giới hạn mỗi khoảng chờ ở 10 giây. Tổng thời gian backoff được giới hạn xấp xỉ 60 giây theo cấu hình. Cần kiểm tra phiên bản Spring Kafka đang dùng vì API và cách tính tổng thời gian của các lớp backoff có thể khác nhau giữa phiên bản.

Khi chọn backoff, hãy xem xét:

- Tổng thời gian retry có nằm trong thời gian chờ tối đa mà nghiệp vụ chấp nhận hay không.
- Listener có giữ consumer thread quá lâu khiến các lần `poll()` tiếp theo bị trễ hay không.
- Dịch vụ downstream có cần thời gian hồi phục trước khi nhận request tiếp theo hay không.
- Nhiều consumer có cùng retry một dịch vụ đang lỗi, tạo ra đợt request dồn dập hay không.
- Record phía sau trong cùng partition có thể chờ bao lâu trước khi được xử lý.

Retry tại consumer thường là retry có chờ trong luồng tiêu thụ. Nếu thời gian chờ dài, record đang lỗi có thể làm chậm tiến trình của partition đó. Với khoảng trì hoãn dài hoặc cần tiếp tục xử lý các record mới, cân nhắc retry topic với `@RetryableTopic`; đây là một mô hình khác với retry tại chỗ của `DefaultErrorHandler` và có trade-off riêng về thứ tự, topic và vận hành.

## 4. Phân loại exception để tránh retry sai

Không phải lỗi nào cũng nên retry. Timeout, lỗi kết nối tạm thời hoặc phản hồi 503 có thể tự hết sau một khoảng chờ. Dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ thường không thay đổi chỉ vì ứng dụng thử lại.

Spring Kafka `DefaultErrorHandler` có cơ chế phân loại exception. Có thể khai báo loại lỗi không retry bằng `addNotRetryableExceptions(...)`, hoặc thêm loại lỗi retry được bằng `addRetryableExceptions(...)`:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

handler.addRetryableExceptions(
        TransientDataAccessException.class,
        ResourceAccessException.class);
```

Trong ví dụ, dữ liệu đơn hàng không hợp lệ hoặc phiên bản sự kiện không được hỗ trợ sẽ đi tới recovery mà không trải qua các lần retry thông thường. Lỗi database hoặc truy cập HTTP tạm thời được retry theo backoff. Nếu bọc exception, cần bảo toàn cause và xác minh cách phân loại của handler đối với exception thực tế mà listener ném ra.

| Nhóm lỗi | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Tạm thời | Timeout, mất kết nối ngắn hạn, HTTP 503 | Retry có giới hạn với backoff. |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng, giá trị không chấp nhận | Không retry; chuyển DLT hoặc quy trình nghiệp vụ riêng. |
| Lỗi lập trình | Null ngoài dự kiến, sai mapping, bug | Tránh retry lặp kéo dài; cảnh báo, điều tra và quyết định phục hồi. |
| Lỗi deserialize | Payload không chuyển thành object | Xử lý ở tầng deserializer/container; listener có thể chưa được gọi. |

Spring Kafka có các loại exception mặc định được xem là không retry vì thường là lỗi nghiêm trọng hoặc không thể khắc phục bằng thử lại. Khi thay đổi phân loại, hãy kiểm tra danh sách mặc định của phiên bản đang sử dụng và chỉ ghi đè khi đã hiểu tác động. Không nên biến mọi exception thành retryable, vì lỗi dữ liệu cố định sẽ chiếm thời gian và làm tăng lag.

## 5. Chuyển record thất bại sang DLT

Sau khi hết retry, error handler cần một hành động phục hồi. `DeadLetterPublishingRecoverer` có thể gửi record cùng metadata lỗi sang topic DLT. Ví dụ dưới đây gửi record từ `orders` sang `orders.DLT` và giữ partition nguồn:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

Nếu resolver giữ nguyên số partition, topic DLT cần có đủ partition tương ứng với topic nguồn. Nếu DLT có cấu trúc partition khác, hãy ánh xạ rõ ràng theo một chính sách phù hợp. Cũng cần bảo đảm producer có quyền ghi DLT và serializer có thể serialize kiểu key/value mà recoverer gửi.

Khi DLT publish thành công, handler có thể xem record đã được phục hồi và tiếp tục theo chính sách offset. Nếu publish thất bại, cần giữ lỗi phục hồi ở trạng thái có thể quan sát và xử lý. Không được coi việc gọi recoverer là bằng chứng record đã tới DLT; phải theo dõi kết quả gửi và cảnh báo khi DLT không nhận được record.

DLT cần có người sở hữu và quy trình xử lý. Theo dõi số record vào DLT, lưu topic/partition/offset nguồn, exception, timestamp và event ID. Sau khi sửa dữ liệu hoặc code, phát lại có kiểm soát và bảo đảm consumer idempotent để tránh tác động nghiệp vụ lặp.

## 6. Retry ảnh hưởng tới offset và thứ tự ra sao?

Kafka lưu offset theo partition. Khi một record thất bại, error handler quyết định cách xử lý record đó và các record còn lại mà consumer đã poll. Với record listener, `DefaultErrorHandler` thường seek để consumer có thể đọc lại record chưa xử lý thành công trong lần poll tiếp theo. Cách commit cụ thể còn phụ thuộc `AckMode`, transaction và cấu hình container.

Một số điểm cần nắm:

- Không acknowledge hoặc commit offset trước khi công việc nghiệp vụ đã hoàn tất.
- Nếu record được retry tại chỗ, các record phía sau trong cùng partition có thể bị trì hoãn để giữ đúng tiến trình xử lý.
- Các partition khác có thể tiếp tục tiến triển tùy assignment và hoạt động của consumer; không nên suy ra toàn bộ topic bị dừng chỉ vì một partition có record lỗi.
- Sau khi chuyển record sang DLT thành công, offset nguồn có thể được xác nhận theo chính sách recoverer/error handler, cho phép partition tiếp tục.
- Nếu ứng dụng đã ghi database nhưng gặp lỗi trước khi commit offset, record có thể được giao lại. Logic nghiệp vụ cần idempotent hoặc có cơ chế chống xử lý trùng.

Với batch listener, nếu cần chỉ rõ record lỗi, Spring Kafka hỗ trợ `BatchListenerFailedException` kèm vị trí record thất bại. Điều này giúp handler phân biệt phần đã xử lý với phần cần retry. Chỉ báo đúng index khi ứng dụng chắc chắn trạng thái xử lý của từng record; nếu không, hãy dùng chính sách retry toàn batch phù hợp.

## 7. Khi nào nên dùng retry topic?

Retry tại chỗ bằng `DefaultErrorHandler` phù hợp với số lần thử ít và khoảng chờ ngắn. Listener container chờ theo backoff, nên record lỗi có thể làm chậm việc xử lý tiếp theo của partition. Khi cần trì hoãn dài, muốn tiếp tục xử lý record mới hoặc cần nhiều mức retry có thời gian chờ khác nhau, retry topic có thể phù hợp hơn.

Spring Kafka cung cấp `@RetryableTopic` để định tuyến record thất bại qua các retry topic rồi tới DLT. Mô hình này thường dùng khi cần retry không chặn luồng consumer chính trong suốt thời gian chờ. Tuy nhiên, record retry được xử lý ở topic khác nên thứ tự giữa các sự kiện cùng key có thể khác với luồng ban đầu. Cần đánh giá yêu cầu ordering, số topic, retention, partition, replication và quy trình replay trước khi chọn.

| Tiêu chí | `DefaultErrorHandler` retry tại chỗ | Retry topic (`@RetryableTopic`) |
|---|---|---|
| Cách chờ | Consumer container chờ theo backoff | Record được chuyển tới topic retry có thời gian chờ phù hợp |
| Phù hợp | Retry ngắn, ít lần, cần giữ tiến trình partition | Retry trì hoãn dài hoặc nhiều mức delay |
| Ảnh hưởng luồng chính | Record lỗi có thể chặn tiến trình partition | Consumer luồng chính có thể tiếp tục với record khác |
| Thứ tự | Dễ giữ tiến trình theo partition hơn khi retry tại chỗ | Có thể thay đổi thứ tự do record đi qua topic khác |
| Vận hành | Theo dõi error handler và DLT | Quản lý thêm retry topic, retention, routing và DLT |

Không nên dùng đồng thời nhiều tầng retry mà không tính tổng số lần thử. Ví dụ, ba lần retry tại chỗ cộng với ba lần retry topic có thể tạo ra nhiều lần gọi downstream hơn dự kiến. Hãy mô tả một chính sách retry thống nhất để nhóm vận hành hiểu được giới hạn cuối cùng.

## 8. Theo dõi và kiểm thử chính sách retry

Một chính sách retry chỉ đáng tin cậy khi có thể quan sát và kiểm chứng. Theo dõi ít nhất:

- Số lần listener thất bại và số lần retry theo loại exception.
- Thời gian chờ backoff và thời gian xử lý tổng của một record.
- Consumer lag theo partition, đặc biệt partition có record đang retry.
- Số record được recover thành công và số lần DLT publish thất bại.
- Số record vào DLT, tuổi của record cũ nhất và số record đã replay.
- Tỷ lệ lỗi và thời gian phản hồi của database hoặc dịch vụ downstream.

Các tình huống kiểm thử nên bao gồm:

1. Listener thất bại một lần rồi thành công: xác minh record được gọi lại và offset chỉ tiến sau khi xử lý hoàn tất.
2. Listener luôn thất bại: xác minh số lần retry đúng bằng backoff đã cấu hình, sau đó recover theo chính sách.
3. Exception không retry: xác minh không có các lần retry không cần thiết và record đi tới recovery.
4. DLT không khả dụng hoặc producer gửi thất bại: xác minh lỗi publish được phát hiện, không âm thầm coi record đã được lưu.
5. Có nhiều record trong một partition: xác minh retry không làm mất record phía sau và thứ tự được giữ theo chính sách.
6. Consumer restart giữa quá trình retry: xác minh hành vi giao lại và tính idempotent của xử lý nghiệp vụ.
7. Batch listener có record lỗi ở giữa batch: xác minh offset và các record được retry hoặc phục hồi đúng vị trí.

Log cần chứa topic, partition, offset, key hoặc event ID, tên exception và số lần thử nếu có. Tránh log payload nhạy cảm hoặc toàn bộ message nếu không cần thiết. Metric và cảnh báo nên giúp phát hiện retry tăng bất thường trước khi consumer lag vượt ngưỡng vận hành.

Retry ở consumer là cơ chế phục hồi có chủ đích: chỉ thử lại những lỗi có khả năng tự hết, giới hạn số lần và thời gian chờ, rồi chuyển sang recovery khi không thể tiếp tục. Khi kết hợp error handler, offset, DLT và xử lý idempotent một cách nhất quán, luồng Spring Kafka có thể chịu được gián đoạn tạm thời mà vẫn kiểm soát được độ trễ và rủi ro xử lý trùng.
