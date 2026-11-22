# ExponentialBackOff

Trong Spring Kafka, **ExponentialBackOff** là chiến lược tăng dần khoảng chờ giữa các lần retry khi listener xử lý record thất bại. Thay vì thử lại liên tục với một khoảng chờ cố định, exponential backoff bắt đầu bằng một delay nhỏ rồi nhân delay với một hệ số sau mỗi lần thất bại, cho đến khi chạm giới hạn tối đa.

Chiến lược này hữu ích khi lỗi có khả năng tự phục hồi, chẳng hạn database tạm thời quá tải, HTTP service đang khởi động lại hoặc dependency cần thời gian để khôi phục. Các lần retry đầu diễn ra tương đối nhanh; nếu lỗi tiếp tục, khoảng chờ dài hơn giúp giảm áp lực lên hệ thống đang gặp sự cố.

Trong Spring Kafka, backoff thường được gắn với **DefaultErrorHandler** để điều khiển retry blocking của record listener. Có thể dùng **ExponentialBackOff** của Spring Framework để giới hạn theo tổng thời gian, hoặc **ExponentialBackOffWithMaxRetries** của Spring Kafka khi muốn đặt số lần retry cụ thể. Cần phân biệt backoff với chính sách phân loại exception: backoff quyết định chờ bao lâu, còn error handler quyết định exception nào được retry và khi nào chuyển sang recovery như Dead Letter Topic (DLT).

## 1. Vì sao cần exponential backoff?

Giả sử listener nhận một record và gọi Inventory API. API đang phục hồi sau một lần triển khai, vì vậy các request đầu tiên trả về lỗi tạm thời.

Nếu consumer retry ngay lập tức, nó có thể gửi hàng trăm request liên tiếp vào một dependency đang quá tải. Điều này làm tăng tải, kéo dài thời gian phục hồi và ảnh hưởng các client khác.

Nếu dùng khoảng chờ cố định rất dài, những lỗi chỉ kéo dài vài trăm mili giây cũng bị trì hoãn không cần thiết. Exponential backoff cân bằng hai trường hợp: bắt đầu bằng khoảng chờ ngắn, sau đó tăng dần nếu lỗi vẫn tiếp diễn.

Ví dụ với delay ban đầu 500 ms, hệ số nhân 2 và giới hạn 8 giây:

| Lần retry | Khoảng chờ trước lần thử |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| 5 | 8 giây |
| Các lần tiếp theo | 8 giây |

Khoảng chờ tăng theo cấp số nhân nhưng không vượt max interval. Khi số lần retry đã hết theo cấu hình, error handler chuyển record sang recovery hoặc DLT.

## 2. Công thức và các tham số

Exponential backoff thường có ba tham số chính:

- **Initial interval:** khoảng chờ ở lần retry đầu tiên.
- **Multiplier:** hệ số nhân delay sau mỗi lần retry.
- **Max interval:** giới hạn trên của một khoảng chờ.

Khoảng chờ ở lần retry thứ n có thể mô tả bằng:

~~~text
delay(n) = min(initialInterval × multiplier^(n - 1), maxInterval)
~~~

Trong đó n bắt đầu từ 1 cho lần retry đầu tiên sau lần xử lý ban đầu thất bại.

Ví dụ:

~~~text
initialInterval = 500 ms
multiplier      = 2
maxInterval     = 8.000 ms

delay(1) = min(500 × 2^0, 8.000) = 500 ms
delay(2) = min(500 × 2^1, 8.000) = 1.000 ms
delay(3) = min(500 × 2^2, 8.000) = 2.000 ms
delay(4) = min(500 × 2^3, 8.000) = 4.000 ms
delay(5) = min(500 × 2^4, 8.000) = 8.000 ms
delay(6) = min(500 × 2^5, 8.000) = 8.000 ms
~~~

Multiplier phải lớn hơn 1 để khoảng chờ tăng dần. Nếu multiplier bằng 1, chiến lược trở thành khoảng chờ cố định. Max interval cần lớn hơn hoặc bằng initial interval để chuỗi delay có ý nghĩa.

### 2.1. Tổng thời gian chờ

Khi thiết kế retry, không chỉ xem delay lớn nhất. Cần tính tổng thời gian chờ trước khi kết thúc tất cả lần retry.

Với ví dụ trên và năm lần retry:

~~~text
totalBackoff = 0,5 + 1 + 2 + 4 + 8
             = 15,5 giây
~~~

Tổng thời gian thực tế còn bao gồm thời gian mỗi lần listener xử lý, timeout của dependency, thời gian commit/recovery và scheduling overhead.

Một policy có delay cuối là 30 giây có thể tiêu tốn vài phút nếu có nhiều lần retry và mỗi lần gọi dependency cũng chờ timeout dài. Hãy tính cả retry budget vào SLO xử lý record và giới hạn poll của consumer.

### 2.2. Max interval và max elapsed time

Hai giới hạn này có vai trò khác nhau:

- **Max interval** giới hạn thời gian chờ của một lần retry.
- **Max elapsed time** giới hạn tổng thời gian backoff được phép tiếp tục.

Nếu chỉ giới hạn max interval mà không giới hạn số lần retry hoặc tổng thời gian, chuỗi retry có thể tiếp tục vô hạn ở mức delay tối đa.

Khi cần giới hạn số lần retry cụ thể, dùng **ExponentialBackOffWithMaxRetries**. Khi muốn dừng theo tổng thời gian, có thể dùng **ExponentialBackOff** của Spring Framework với max elapsed time. Chọn một cơ chế phù hợp với cách vận hành và yêu cầu nghiệp vụ.

## 3. Các lớp backoff trong Spring

Spring Kafka sử dụng hợp đồng **org.springframework.util.backoff.BackOff** của Spring Framework. Một BackOff tạo ra một **BackOffExecution**, và mỗi lần error handler cần chờ sẽ gọi **nextBackOff()** để lấy khoảng chờ tiếp theo.

Khi không còn lần retry nào, BackOffExecution trả về giá trị đặc biệt **BackOffExecution.STOP**. Error handler sau đó thực hiện recovery theo cấu hình, ví dụ gọi recoverer để publish record vào DLT.

Các lựa chọn thường gặp:

| Lớp | Cách giới hạn | Khi phù hợp |
|---|---|---|
| FixedBackOff | Một khoảng chờ cố định và số lần retry | Lỗi phục hồi nhanh, cần policy đơn giản |
| ExponentialBackOff | Delay tăng theo multiplier, giới hạn max interval và max elapsed time | Muốn giới hạn retry theo ngân sách thời gian |
| ExponentialBackOffWithMaxRetries | Delay tăng theo multiplier, giới hạn số lần retry rõ ràng | Muốn quy định chính xác số lần thử lại |
| Custom BackOff | Ứng dụng tự quyết định delay hoặc dừng retry | Cần jitter, lịch retry riêng hoặc policy theo nghiệp vụ |

### 3.1. ExponentialBackOff của Spring Framework

Lớp **org.springframework.util.backoff.ExponentialBackOff** cho phép cấu hình initial interval, multiplier, max interval và max elapsed time.

Ví dụ:

~~~java
import org.springframework.util.backoff.ExponentialBackOff;

ExponentialBackOff backOff = new ExponentialBackOff();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(8_000L);
backOff.setMaxElapsedTime(30_000L);
~~~

Trong ví dụ, khoảng chờ bắt đầu ở 500 ms, tăng gấp đôi và không vượt 8 giây. Tổng thời gian backoff bị giới hạn bởi 30 giây. Khi ngân sách thời gian đã hết, BackOffExecution trả về STOP.

Max elapsed time không phải timeout của một lần gọi HTTP hoặc database. Nó chỉ kiểm soát chuỗi backoff. Nếu listener xử lý mỗi lần mất 10 giây, tổng thời gian xử lý record vẫn có thể vượt 30 giây dù backoff đã bị giới hạn ở 30 giây.

### 3.2. ExponentialBackOffWithMaxRetries của Spring Kafka

Spring Kafka cung cấp **ExponentialBackOffWithMaxRetries** như một tiện ích dựa trên ExponentialBackOff, giúp cấu hình số lần retry thay vì phải tự tính max elapsed time.

Ví dụ:

~~~java
import org.springframework.kafka.support.ExponentialBackOffWithMaxRetries;

ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(8_000L);
~~~

Trong ví dụ, backoff được cấu hình cho tối đa năm lần retry sau lần xử lý ban đầu thất bại. Khoảng chờ tăng từ 500 ms, nhân 2 và bị giới hạn ở 8 giây.

Tên package, constructor và các setter cần được kiểm tra theo phiên bản Spring Kafka đang sử dụng. Đây là API thuộc Spring Kafka; **ExponentialBackOff** cơ bản thuộc Spring Framework.

## 4. Gắn ExponentialBackOff với DefaultErrorHandler

Với record listener non-transactional, **DefaultErrorHandler** có thể nhận một BackOff để điều khiển retry khi listener ném exception.

Ví dụ đầy đủ:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(5);

        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(8_000L);

        return new DefaultErrorHandler(recoverer, backOff);
    }
}
~~~

DefaultErrorHandler gọi listener lại theo BackOff khi exception được phân loại là retryable. Khi BackOff hết lần retry, handler gọi **DeadLetterPublishingRecoverer** để xử lý record lỗi. Nếu recoverer publish thành công, container có thể tiếp tục và commit offset theo AckMode.

BackOff chỉ định thời gian và số lần retry. Nó không tự cấu hình topic DLT, serializer, metadata hoặc chính sách commit offset sau recovery.

### 4.1. Khai báo recoverer cho DLT

Ví dụ định tuyến record từ topic gốc sang topic có hậu tố .DLT:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(
        template,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
}
~~~

Topic DLT cần tồn tại và có đủ partition nếu muốn giữ nguyên số partition của record gốc. Cần cấu hình serializer tương thích với key/value và header. Trong môi trường production, hãy xác định replication factor, retention, quyền ghi/đọc và quy trình replay DLT.

### 4.2. Đăng ký DefaultErrorHandler với listener container

Nếu tự tạo listener container factory, có thể gắn error handler:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Một số cấu hình Spring Boot có thể tự đăng ký bean CommonErrorHandler cho listener container. Hãy xác nhận factory thực tế đang sử dụng bean này; chỉ khai báo một bean mà container không tham chiếu đến sẽ không thay đổi hành vi retry.

## 5. Cách retry diễn ra với một record

Giả sử listener đọc record ở topic orders, partition 2, offset 41. Listener gọi Inventory API và nhận lỗi tạm thời.

Với initial interval 500 ms, multiplier 2, max interval 8 giây và năm lần retry, luồng khái quát:

~~~
Lần xử lý ban đầu
        |
        v
Inventory API lỗi
        |
        v
Chờ 500 ms
        |
        v
Retry 1
        |
        v
Vẫn lỗi
        |
        v
Chờ 1 giây
        |
        v
Retry 2
        |
        v
Chờ 2 giây -> Retry 3
        |
        v
Chờ 4 giây -> Retry 4
        |
        v
Chờ 8 giây -> Retry 5
        |
        +---- Thành công: tiếp tục và commit theo AckMode
        |
        +---- Hết retry: gọi recoverer / DLT
~~~

Nếu một lần retry thành công, handler kết thúc xử lý lỗi và container tiếp tục theo semantics của listener. Nếu tất cả lần retry thất bại, recoverer được gọi. Khi recovery thành công, record được xem là đã phục hồi theo chính sách; nếu recovery thất bại, cần xử lý trạng thái lỗi theo cấu hình để không vô tình bỏ qua record.

Số lần gọi listener bao gồm lần xử lý ban đầu cộng số lần retry được cấu hình. Ví dụ năm lần retry có thể dẫn đến tối đa sáu lần giao record cho listener trước khi recovery. Hãy kiểm tra cách đếm theo BackOff cụ thể và phiên bản thư viện.

## 6. Phân loại exception trước khi áp dụng backoff

Không nên retry mọi exception theo cùng một exponential schedule. Backoff chỉ quyết định khoảng chờ sau khi error handler đã quyết định lỗi có thể retry.

Ví dụ:

| Exception/điều kiện | Chính sách gợi ý |
|---|---|
| Inventory service tạm thời unavailable | Retry với exponential backoff |
| Database connection tạm thời reset | Retry có backoff, đồng thời kiểm tra pool và database health |
| HTTP 429 có Retry-After | Tôn trọng thời gian server yêu cầu hoặc dùng policy tương đương |
| Payload sai format | Không retry cùng payload; chuyển DLT |
| Business validation thất bại | Non-retryable nếu business state không thể thay đổi trong thời gian ngắn |
| Authentication/authorization failure | Dừng retry record và sửa credential/ACL |
| Schema version không được hỗ trợ | Chuyển DLT hoặc chờ quy trình nâng cấp có kiểm soát |

Có thể cấu hình exception không retry:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);

handler.addNotRetryableExceptions(
    InvalidOrderException.class,
    UnsupportedEventVersionException.class
);
~~~

Và đánh dấu một số exception dependency là retryable:

~~~java
handler.addRetryableExceptions(
    InventoryServiceUnavailableException.class,
    TemporaryDatabaseException.class
);
~~~

Tên method và classification mặc định có thể thay đổi theo phiên bản. Nếu listener bọc lỗi dependency trong một RuntimeException chung, hãy xem xét root cause hoặc chuyển đổi sang domain exception để error handler phân loại chính xác.

## 7. Chọn initial interval

Initial interval quyết định thời gian chờ trước lần retry đầu tiên. Nếu quá nhỏ, consumer có thể gửi lại request trước khi dependency kịp phục hồi. Nếu quá lớn, lỗi ngắn cũng làm record bị trì hoãn.

Hãy căn cứ:

- Thời gian phục hồi điển hình của dependency.
- Timeout của request ban đầu.
- SLO xử lý record.
- Mức độ tải mà retry tạo ra.
- Có Retry-After hoặc hướng dẫn backoff từ dependency hay không.

Ví dụ, một API thường phục hồi trong khoảng 1 đến 3 giây sau một đợt deploy. Initial interval 500 ms có thể tạo hai hoặc ba lần retry khá gần nhau trước khi API ổn định. Initial interval 1 giây có thể giảm số request sớm, nhưng cũng làm tăng thời gian xử lý khi lỗi chỉ kéo dài 300 ms.

Không chọn initial interval chỉ theo cảm tính. Đo latency và thời gian phục hồi thực tế, sau đó thử nghiệm trong môi trường tải đại diện.

## 8. Chọn multiplier

Multiplier điều khiển tốc độ tăng của delay:

- Multiplier gần 1: delay tăng chậm, số lần retry đầu có khoảng cách tương đối gần nhau.
- Multiplier 2: delay tăng gấp đôi sau mỗi lần retry, thường dễ giải thích và tính toán.
- Multiplier lớn: delay đạt max interval nhanh, giảm tần suất gọi dependency nhưng có thể làm record chờ lâu.

Ví dụ initial interval 1 giây và max interval 30 giây:

| Multiplier | Chuỗi delay minh họa |
|---:|---|
| 1,5 | 1s, 1,5s, 2,25s, 3,375s, 5,06s, ... |
| 2 | 1s, 2s, 4s, 8s, 16s, 30s |
| 3 | 1s, 3s, 9s, 27s, 30s |

Multiplier lớn giúp giảm nhanh tốc độ retry khi sự cố kéo dài. Tuy nhiên, nếu dependency phục hồi ngay sau lần retry thứ hai, delay lớn có thể làm record phải chờ lâu hơn cần thiết.

## 9. Chọn max interval

Max interval giới hạn thời gian chờ giữa hai lần retry. Không nên đặt max interval vượt quá khoảng thời gian mà nghiệp vụ chấp nhận chờ một record.

Nếu dependency có thể mất 30 giây để phục hồi, max interval 10 giây cho phép thử lại định kỳ mà không tạo request liên tục. Nếu SLO chỉ cho phép xử lý trong 5 giây, max interval 30 giây không phù hợp dù nó giúp giảm tải dependency.

Max interval cũng cần được xem cùng max retries hoặc max elapsed time. Một policy có delay tối đa 30 giây và 20 lần retry có thể giữ record trong thời gian rất dài.

## 10. ExponentialBackOff và ngân sách thời gian

Khi chọn số lần retry, hãy tính cả thời gian gọi dependency.

Giả sử:

- Initial interval: 500 ms.
- Multiplier: 2.
- Max interval: 8 giây.
- Số lần retry: 5.
- Mỗi lần listener gọi dependency có timeout tối đa 3 giây.

Tổng thời gian backoff là 15,5 giây. Nếu có một lần xử lý ban đầu và năm lần retry, tổng thời gian gọi dependency tối đa theo timeout là 18 giây. Tổng thời gian ước lượng đã là 33,5 giây, chưa tính commit, recovery và scheduling.

Với blocking retry, thời gian này nằm trong poll cycle hoặc ảnh hưởng trực tiếp đến khả năng container tiếp tục xử lý. Cần so sánh với **max.poll.interval.ms** và chừa khoảng dự phòng cho GC, network, commit và tải biến động.

Nếu thời gian retry dài, cân nhắc non-blocking retry topic hoặc cơ chế pause container phù hợp. Không tăng max.poll.interval.ms chỉ để che một retry policy vô hạn hoặc một dependency không có timeout.

## 11. Backoff và blocking retry

Với **DefaultErrorHandler**, retry blocking thường giữ record lỗi trong luồng xử lý trước khi consumer tiếp tục theo semantics của container.

Ưu điểm:

- Dễ giữ thứ tự xử lý trong partition hơn.
- Không cần thêm retry topic.
- Phù hợp với lỗi transient có thời gian phục hồi ngắn.
- Dễ quan sát lần thử lại và recovery trong cùng listener flow.

Nhược điểm:

- Consumer thread phải chờ trong các khoảng backoff.
- Record lỗi có thể chặn các record phía sau trong partition.
- Tổng thời gian retry có thể vượt max.poll.interval.ms.
- Nhiều consumer cùng retry có thể tạo tải đồng thời lên dependency.

Exponential backoff giảm tần suất retry theo thời gian nhưng không loại bỏ các rủi ro này. Hãy đặt timeout cho dependency và giới hạn retry budget.

## 12. Backoff và non-blocking retry topic

Với non-blocking retry, record được publish sang một hoặc nhiều retry topic. Consumer chính có thể tiếp tục xử lý các record khác trong lúc record lỗi chờ đến thời điểm retry.

Spring Kafka hỗ trợ cơ chế này qua **@RetryableTopic** và các cấu hình backoff tương ứng. Ví dụ:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 10_000
    )
)
@KafkaListener(topics = "orders", groupId = "billing")
public void handle(OrderEvent event) {
    billingService.process(event);
}
~~~

Đây là ví dụ minh họa cho retry topic; annotation, thuộc tính và cách đếm attempts cần được kiểm tra theo phiên bản Spring Kafka. Cấu hình retry topic không phải cùng một cơ chế với BackOff truyền trực tiếp vào DefaultErrorHandler.

Ưu điểm là không giữ consumer chính chờ backoff dài. Đổi lại, record có thể được xử lý sau các record mới hơn, nên ordering trong partition có thể thay đổi. Cần quản lý số lượng retry topic, routing, retention, DLT và consumer group của từng retry stage.

Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, hãy đánh giá kỹ tác động trước khi chuyển sang non-blocking retry.

## 13. Jitter và tránh retry đồng loạt

Exponential backoff cơ bản tạo ra cùng một chuỗi delay cho các consumer có cùng cấu hình. Nếu nhiều instance cùng gặp sự cố tại một thời điểm, chúng có thể retry gần như đồng thời ở các mốc 1, 2, 4 và 8 giây. Hiện tượng này tạo thành một đợt tải lặp lại lên dependency, thường gọi là thundering herd.

Jitter thêm một lượng ngẫu nhiên vào delay để phân tán các lần retry theo thời gian. Ví dụ, thay vì mọi instance chờ đúng 4 giây, mỗi instance có thể chờ một khoảng quanh giá trị đó theo policy đã chọn.

Các lớp ExponentialBackOff cơ bản không nhất thiết cung cấp jitter theo cấu hình. Nếu cần jitter, hãy dùng custom BackOff hoặc cơ chế retry ở tầng dependency có hỗ trợ. Đảm bảo delay sau jitter vẫn nằm trong giới hạn thời gian nghiệp vụ và poll budget.

## 14. Backoff theo từng record hoặc từng exception

Không phải mọi record đều cần cùng một lịch retry. Một lỗi database tạm thời có thể cần retry ngắn, trong khi lỗi rate limit từ API có thể cần khoảng chờ dài hơn.

Ở các phiên bản Spring Kafka hỗ trợ, **FailedRecordProcessor** cho phép cấu hình BackOff function để chọn policy dựa trên record và exception. Cần kiểm tra API tương ứng của phiên bản đang dùng trước khi áp dụng.

Ví dụ về ý tưởng phân loại:

~~~java
handler.setBackOffFunction((record, exception) -> {
    if (exception instanceof InventoryServiceUnavailableException) {
        return inventoryBackOff;
    }
    if (exception instanceof RateLimitedException) {
        return rateLimitBackOff;
    }
    return defaultBackOff;
});
~~~

Đây là ví dụ minh họa API theo các phiên bản có hỗ trợ BackOff function. Các BackOff instance có thể chứa trạng thái thực thi; tránh dùng chung một BackOffExecution đã được tiêu thụ giữa nhiều record. Hãy trả về một BackOff phù hợp cho mỗi lần xử lý theo contract của phiên bản thư viện.

Nếu policy phụ thuộc HTTP Retry-After, có thể cần exception domain chứa thời gian chờ hoặc custom BackOff đọc thông tin đó. Không nên chuyển mọi lỗi 429 thành cùng một delay cố định nếu server đã cung cấp hướng dẫn cụ thể.

## 15. Backoff khi dùng transactional listener

Với listener container sử dụng Kafka transaction manager, exception có thể làm transaction abort. Spring Kafka dùng **DefaultAfterRollbackProcessor** để điều khiển retry và recovery sau rollback.

DefaultErrorHandler và DefaultAfterRollbackProcessor phục vụ các ngữ cảnh khác nhau:

| Ngữ cảnh | Thành phần thường dùng | Vai trò của BackOff |
|---|---|---|
| Listener non-transactional | DefaultErrorHandler | Retry record và gọi recoverer khi hết retry |
| Listener transactional | DefaultAfterRollbackProcessor | Retry sau rollback và phục hồi record sau số lần thử |
| Retry topic | @RetryableTopic | Lập lịch chuyển record qua retry topics |

Khi transaction abort, output records và offset input trong transaction không được commit. Record đầu vào có thể được đọc lại. Backoff chỉ điều khiển thời gian chờ trước lần xử lý lại; nó không rollback side effect database hoặc HTTP đã thực hiện ngoài Kafka.

Nếu dùng transactional listener, hãy cấu hình retry/recovery ở đúng processor và kiểm tra việc publish DLT có transactional theo yêu cầu hay không. Không gắn DefaultErrorHandler rồi giả định nó điều khiển toàn bộ retry sau rollback.

## 16. Cấu hình lỗi và recovery

Một retry policy hoàn chỉnh cần kết hợp:

1. Classification: exception nào retry được?
2. BackOff: chờ bao lâu giữa các lần retry?
3. Retry limit: khi nào dừng thử?
4. Recoverer: xử lý record sau khi hết retry ra sao?
5. Offset policy: khi nào offset gốc được commit?
6. Observability: làm sao biết retry đang phục hồi hay đang tích tụ lỗi?

Ví dụ cấu hình:

~~~java
@Bean
DefaultErrorHandler defaultErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

Trong ví dụ, lỗi validation và event version không được retry; các exception khác được xử lý theo classification mặc định và backoff. Hãy xem xét việc khai báo rõ các exception retryable nếu ứng dụng cần policy chặt chẽ, thay vì dựa hoàn toàn vào mặc định của framework.

## 17. Quan sát retry và backoff

Theo dõi lag tổng thể không đủ để hiểu retry policy có hoạt động hay không. Cần đo cả số lần retry, thời gian chờ, tỷ lệ phục hồi và lượng record chuyển sang DLT.

Các tín hiệu nên theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| Retry attempts theo exception | Loại lỗi nào khiến consumer phải retry |
| Retry success rate | Bao nhiêu record phục hồi trước khi hết retry |
| Backoff duration | Thời gian consumer chờ giữa các lần thử |
| Exhausted retry count | Số record đã dùng hết retry budget |
| DLT publish rate | Số record được chuyển sang DLT |
| DLT oldest record age | Lỗi đang tồn đọng bao lâu |
| Listener processing latency | Thời gian xử lý mỗi lần thử |
| Consumer lag theo partition | Retry có làm partition bị nghẽn không |
| Rebalance count | Retry/backoff có làm consumer mất nhịp poll không |
| Dependency error rate | Hệ thống đích đã phục hồi hay chưa |

Log nên có topic, partition, offset, event ID, exception class, root cause, retry count và correlation ID. Không log toàn bộ payload nếu có dữ liệu nhạy cảm.

Nếu retry attempts tăng nhưng retry success rate vẫn cao và lag ổn định, policy có thể đang xử lý đúng các lỗi transient. Nếu exhausted retry và DLT publish tăng liên tục, cần điều tra permanent exception hoặc dependency outage kéo dài.

## 18. Kiểm thử ExponentialBackOff

Kiểm thử nên xác nhận lịch delay, giới hạn retry và hành vi recovery, thay vì chỉ xác nhận object được khởi tạo.

### 18.1. Kiểm tra lịch backoff

Có thể kiểm tra trực tiếp BackOffExecution:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(8_000L);

BackOffExecution execution = backOff.start();

long first = execution.nextBackOff();
long second = execution.nextBackOff();
long third = execution.nextBackOff();
~~~

Trong test, xác nhận các delay theo cấu hình và xác nhận lần gọi tiếp theo sau khi hết retry trả về **BackOffExecution.STOP**. Có thể kiểm tra theo contract của class thay vì hard-code kỳ vọng không phù hợp với phiên bản.

### 18.2. Kiểm tra listener và recoverer

Các tình huống nên có:

- Listener lỗi lần đầu rồi thành công ở lần retry sau.
- Listener lỗi liên tục đến khi hết retry.
- Exception permanent được phục hồi mà không chờ hết chuỗi retry.
- Recoverer publish thành công vào DLT.
- Recoverer publish thất bại và offset gốc được xử lý đúng chính sách.
- Record được retry không tạo side effect duplicate.
- Backoff dài không làm consumer vượt max.poll.interval.ms.

Dùng test broker hoặc môi trường Kafka thử nghiệm để xác nhận hành vi container. Tránh dùng Thread.sleep dài và kiểm thử dựa trên timing quá chặt; có thể dùng clock/test support hoặc spy vào recoverer và listener khi phù hợp.

## 19. Các lỗi cấu hình thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ đặt initial interval mà không giới hạn retry | Record có thể retry quá lâu hoặc vô hạn tùy BackOff | Đặt maxRetries hoặc maxElapsedTime |
| Multiplier quá lớn | Delay đạt max interval quá sớm, record chờ lâu | Tính chuỗi delay và tổng retry budget |
| Max interval quá cao | Một record có thể bị trì hoãn vượt SLO | Giới hạn theo thời gian nghiệp vụ |
| Retry mọi exception | Permanent exception làm consumer lặp vô ích | Cấu hình retryable/non-retryable classification |
| Không cấu hình recoverer | Record hết retry không có quy trình xử lý phù hợp | Dùng recoverer/DLT và giám sát recovery |
| Backoff dài trong consumer thread | Có thể vượt max.poll.interval.ms và gây rebalance | Tính poll budget hoặc dùng retry topic/container pause phù hợp |
| Nhiều instance retry cùng thời điểm | Thundering herd lên dependency | Cân nhắc jitter và giới hạn concurrency |
| Dùng DefaultErrorHandler cho transactional rollback mà không hiểu processor | Retry/recovery không theo transaction flow mong muốn | Cấu hình DefaultAfterRollbackProcessor cho transactional listener |
| Chỉ nhìn số lần retry | Không biết retry có phục hồi hay làm lag tăng | Theo dõi success rate, duration, DLT và dependency health |

## 20. Quy trình chọn exponential backoff

Khi thiết kế retry cho một listener:

1. Xác định dependency gây lỗi và phân biệt transient với permanent.
2. Đo thời gian phục hồi thường gặp và timeout của dependency.
3. Chọn initial interval dựa trên thời gian phục hồi ngắn.
4. Chọn multiplier để giảm tần suất request khi sự cố kéo dài.
5. Đặt max interval phù hợp với SLO và khả năng phục hồi.
6. Chọn max retries hoặc max elapsed time để giới hạn retry budget.
7. Cộng thời gian xử lý và backoff, so sánh với max.poll.interval.ms.
8. Chọn blocking retry hay retry topic dựa trên yêu cầu ordering.
9. Cấu hình recoverer/DLT và bảo đảm offset chỉ tiến lên sau recovery thành công.
10. Kiểm thử listener, backoff, recovery, duplicate và rebalance ở tải đại diện.

ExponentialBackOff là công cụ điều tiết nhịp retry, không phải cơ chế tự sửa lỗi. Khi kết hợp đúng với exception classification, retry limit, recovery và idempotency, nó giúp consumer có thời gian chờ dependency phục hồi mà vẫn giữ được giới hạn vận hành và khả năng truy vết record lỗi.
