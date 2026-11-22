# UNLIMITED_ATTEMPTS và rủi ro

Trong Spring Kafka, retry vô hạn cho phép một record tiếp tục được thử xử lý cho đến khi thành công hoặc cho đến khi hệ thống/người vận hành chủ động dừng luồng. Với cơ chế backoff của Spring, hằng số **UNLIMITED_ATTEMPTS** biểu thị rằng không đặt một số lần retry hữu hạn. Cách dùng thường gặp là kết hợp **FixedBackOff** với **DefaultErrorHandler**.

Retry vô hạn có thể hữu ích khi ứng dụng không được phép bỏ qua một record và lỗi chắc chắn chỉ tạm thời. Tuy nhiên, nó cũng có thể giữ một partition tại một record lỗi, làm lag tăng, giữ tài nguyên lâu dài và trì hoãn dữ liệu phía sau. Nếu lỗi thực tế là permanent, retry vô hạn chỉ lặp lại cùng thất bại.

Vì vậy, UNLIMITED_ATTEMPTS là một lựa chọn về chính sách phục hồi, không phải một bảo đảm rằng record cuối cùng sẽ được xử lý thành công. Muốn dùng an toàn, cần xác định rõ loại exception được retry, backoff, timeout, khả năng phục hồi thủ công, idempotency và cách quan sát record đang bị kẹt.

## 1. UNLIMITED_ATTEMPTS có nghĩa gì?

Với retry hữu hạn, error handler dừng thử sau số lần được cấu hình. Khi hết retry, handler có thể gọi recoverer, chuyển record sang Dead Letter Topic (DLT) hoặc thực hiện hành động phục hồi khác.

Với retry vô hạn, không có ngưỡng số lần retry để tự kết thúc chuỗi thử lại. Record có thể được giao lại nhiều lần trong thời gian dài. Nếu dependency phục hồi và lần xử lý sau thành công, luồng tiếp tục. Nếu nguyên nhân không thay đổi, record tiếp tục thất bại.

Điều quan trọng là phân biệt:

- **Lần xử lý ban đầu:** lần đầu listener nhận record.
- **Retry attempt:** lần giao lại sau khi lần xử lý trước thất bại.
- **Tổng số lần listener được gọi:** gồm lần đầu và các lần retry.
- **Recovery:** hành động sau khi chính sách retry kết thúc, ví dụ gửi DLT.

Với retry vô hạn, không có thời điểm tự động hết số lần thử để chuyển sang recovery theo giới hạn attempts. Muốn có đường thoát, ứng dụng phải có một điều kiện khác, chẳng hạn phân loại exception không retry, dừng container có chủ đích, can thiệp dữ liệu hoặc chuyển record qua một quy trình riêng.

## 2. Cấu hình với FixedBackOff và DefaultErrorHandler

Spring Kafka dùng **DefaultErrorHandler** để xử lý exception từ listener non-transactional. Error handler nhận một **BackOff** để quyết định khoảng chờ giữa các lần retry.

Ví dụ cấu hình retry vô hạn với khoảng chờ cố định:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff =
        new FixedBackOff(2_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    return new DefaultErrorHandler(backOff);
}
~~~

Trong ví dụ, listener được thử lại sau mỗi khoảng chờ 2 giây và không dừng theo số lần retry. **FixedBackOff.UNLIMITED_ATTEMPTS** là sentinel của Spring Framework để biểu thị số lần retry không giới hạn; hãy xác nhận package và API theo phiên bản Spring Framework/Spring Kafka của ứng dụng.

Nếu muốn có recovery cho các lỗi khác, có thể truyền recoverer:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff =
        new FixedBackOff(2_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

Ở đây, exception được đánh dấu non-retryable có thể đi tới recovery mà không chờ chuỗi retry vô hạn. Các lỗi khác vẫn theo classification của error handler và BackOff. Cần kiểm tra các exception mặc định được xem là fatal/non-retryable trong phiên bản đang dùng.

### 2.1. Retry vô hạn không đồng nghĩa retry ngay lập tức

Số lần retry không giới hạn không quyết định khoảng chờ. Hai tham số có trách nhiệm khác nhau:

- **UNLIMITED_ATTEMPTS:** không đặt ngưỡng số lần retry.
- **BackOff interval:** xác định khoảng chờ trước lần retry tiếp theo.

Ví dụ:

| Cấu hình | Hành vi |
|---|---|
| FixedBackOff(0, UNLIMITED_ATTEMPTS) | Thử lại liên tục gần như không có khoảng chờ |
| FixedBackOff(1000, UNLIMITED_ATTEMPTS) | Thử lại vô hạn, chờ khoảng 1 giây giữa các lần |
| FixedBackOff(10000, UNLIMITED_ATTEMPTS) | Thử lại vô hạn, chờ khoảng 10 giây giữa các lần |

Retry vô hạn với delay bằng 0 thường rất nguy hiểm: consumer có thể tạo vòng lặp lỗi liên tục, tiêu thụ CPU và gây áp lực lớn lên dependency. Luôn chọn backoff hữu hạn và có chủ đích.

### 2.2. Đăng ký error handler với listener container

Ví dụ factory:

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

Chỉ khai báo bean DefaultErrorHandler là chưa đủ nếu listener container thực tế không sử dụng bean đó. Hãy xác nhận factory được gắn vào @KafkaListener và cấu hình error handler của container đang hoạt động.

## 3. Retry vô hạn khác gì ExponentialBackOff?

Retry limit và backoff schedule là hai chiều độc lập. Có thể có số lần retry hữu hạn với exponential backoff, hoặc số lần retry vô hạn với fixed delay. Không nên nhầm max interval với max attempts.

| Chính sách | Số lần retry | Khoảng chờ |
|---|---:|---|
| FixedBackOff hữu hạn | Có giới hạn | Cố định |
| FixedBackOff với UNLIMITED_ATTEMPTS | Không giới hạn | Cố định |
| ExponentialBackOff với max elapsed time | Kết thúc theo ngân sách thời gian | Tăng dần, có giới hạn |
| ExponentialBackOffWithMaxRetries | Có giới hạn theo số lần | Tăng dần, có giới hạn |

Spring Framework **ExponentialBackOff** có giới hạn max elapsed time. Nếu dùng nó, chuỗi retry dừng khi hết ngân sách thời gian, dù delay cuối chưa đạt một số lần retry cụ thể. **ExponentialBackOffWithMaxRetries** của Spring Kafka phù hợp khi muốn xác định số lần retry rõ ràng.

Nếu yêu cầu là retry vô hạn với delay tăng dần, cần một BackOff có semantics phù hợp và phải xác minh giới hạn thời gian của implementation. Không nên giả định chỉ cần đặt max interval lớn là số lần retry trở thành vô hạn.

## 4. Retry vô hạn và blocking retry

Với DefaultErrorHandler, retry blocking thường diễn ra trong luồng xử lý của listener container. Khi một record lỗi, container chờ BackOff rồi thử lại record đó trước khi tiếp tục theo semantics của container.

Luồng khái quát:

~~~
poll() nhận record
       |
       v
Listener xử lý record
       |
       v
Exception
       |
       v
DefaultErrorHandler
       |
       v
Chờ BackOff
       |
       v
Gọi listener lại
       |
       +---- Thành công -> tiếp tục và commit theo AckMode
       |
       +---- Thất bại -> quay lại chờ và retry
~~~

Với UNLIMITED_ATTEMPTS, nhánh thất bại có thể lặp vô hạn. Điều này tạo ra một số hệ quả:

- Record lỗi có thể chặn việc xử lý các record phía sau trong cùng partition.
- Consumer thread bị giữ bởi retry và backoff.
- Consumer lag ở partition có thể tiếp tục tăng.
- Nếu tổng thời gian không poll vượt max.poll.interval.ms, group có thể rebalance.
- Sau rebalance hoặc restart, record chưa commit có thể được đọc lại và side effect có thể lặp.

Blocking retry có thể phù hợp khi thứ tự trong partition phải được giữ và lỗi dự kiến phục hồi nhanh. Với lỗi kéo dài hoặc cần retry trong nhiều phút/giờ, retry vô hạn blocking thường không phải lựa chọn tốt.

## 5. Retry vô hạn và non-blocking retry topic

Spring Kafka hỗ trợ non-blocking retry qua **@RetryableTopic** và các retry topic. Record lỗi được chuyển sang topic retry theo lịch backoff; consumer chính có thể tiếp tục xử lý record khác.

Một số phiên bản Spring Kafka cung cấp sentinel **UNLIMITED_ATTEMPTS** cho cấu hình retry topic. Vị trí constant, kiểu dữ liệu và cách truyền vào annotation/builder phụ thuộc phiên bản. Hãy dùng constant được tài liệu/Javadoc của phiên bản ứng dụng chỉ định, thay vì tự thay bằng một số rất lớn hoặc chuỗi đoán định.

Khái niệm cấu hình:

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

Đây là ví dụ retry topic hữu hạn để minh họa cách khai báo backoff. Khi cần unlimited attempts, thay giá trị attempts bằng sentinel được hỗ trợ trong phiên bản Spring Kafka đang sử dụng. Không nên sao chép một hằng số từ phiên bản khác mà chưa xác minh API.

Retry topic có lợi thế không giữ consumer chính chờ backoff dài, nhưng có các rủi ro riêng:

- Record có thể được xử lý sau các record mới hơn, làm thay đổi ordering.
- Retry topic tiếp tục tích tụ nếu dependency không phục hồi.
- Consumer group của retry topic vẫn tiêu thụ tài nguyên.
- Nếu số lần retry không giới hạn, không có mốc attempts để tự động chuyển record sang DLT sau khi hết số lần.
- Retention của retry topic có thể làm record hết hạn trước khi được xử lý lại.

Retry topic không làm cho lỗi biến mất. Nó chuyển vị trí chờ và cách quản lý backlog sang một luồng khác.

## 6. Rủi ro 1: Poison record giữ partition không tiến triển

Poison record là record luôn gây lỗi do payload, schema hoặc business state không thể xử lý. Với retry vô hạn, record này có thể được giao lại mãi mãi.

Ví dụ:

1. Consumer đọc record offset 100.
2. Listener deserialize hoặc validate thất bại.
3. Error handler chờ rồi retry offset 100.
4. Lỗi tiếp tục xảy ra vì payload không đổi.
5. Offset 101, 102 và các record sau trong partition không được xử lý theo thứ tự thông thường.

Kết quả là lag tăng và một phần dữ liệu bị chặn. Nếu record là permanent exception, retry vô hạn không đem lại cơ hội phục hồi.

Giải pháp:

- Phân loại permanent exception là non-retryable.
- Chuyển record không thể xử lý sang DLT hoặc quy trình từ chối.
- Lưu topic, partition, offset, event ID và root cause.
- Tạo quy trình sửa payload/schema rồi replay có kiểm soát.
- Theo dõi partition lag và tuổi record cũ nhất.

## 7. Rủi ro 2: Retry storm và làm dependency quá tải

Nếu nhiều consumer cùng gặp lỗi, retry vô hạn có thể tạo một lượng request liên tục lên database hoặc HTTP service. Khi dependency đã quá tải, các request retry làm nó khó phục hồi hơn.

Ví dụ, 40 consumer cùng retry mỗi 100 ms có thể tạo hàng trăm request mỗi giây. Nếu không có backoff, giới hạn concurrency hoặc circuit breaker, tải retry có thể lớn hơn tải nghiệp vụ ban đầu.

Các biện pháp giảm rủi ro:

- Dùng backoff có khoảng chờ đủ lớn.
- Cân nhắc exponential backoff với max interval.
- Thêm jitter để phân tán retry giữa các instance.
- Giới hạn concurrency và số request đồng thời tới dependency.
- Dùng circuit breaker hoặc pause consumer khi dependency không sẵn sàng.
- Đặt timeout hữu hạn cho mỗi lần gọi dependency.
- Theo dõi retry rate và dependency error rate.

Circuit breaker không thay thế retry policy. Khi circuit mở, listener cần một hành vi rõ ràng: chờ, chuyển retry topic, dừng container có kiểm soát hoặc để error handler xử lý theo chính sách.

## 8. Rủi ro 3: Consumer lag và max.poll.interval.ms

Với blocking retry, thời gian backoff và thời gian gọi dependency được tính vào thời gian consumer chưa quay lại poll tiếp theo. Nếu retry vô hạn, chu kỳ xử lý có thể kéo dài không giới hạn.

Khi consumer vượt **max.poll.interval.ms**, group có thể xem consumer không còn tiến triển và thu hồi partition. Consumer khác có thể nhận lại partition và đọc từ committed offset gần nhất. Record đang xử lý có thể được giao lại trong khi consumer cũ vẫn còn side effect đang chạy.

Điều này có thể tạo:

- Rebalance lặp lại.
- Duplicate side effect.
- Lag tăng nhanh.
- Nhiều consumer cùng xử lý lại một nghiệp vụ nếu tác vụ cũ chưa dừng.

Không nên tăng max.poll.interval.ms lên một giá trị rất lớn để hợp thức hóa retry vô hạn. Hãy đặt giới hạn cho mỗi lần gọi dependency, tính retry budget, và chọn retry topic hoặc pause/resume nếu cần chờ lâu.

## 9. Rủi ro 4: Side effect bị lặp

Giả sử listener thực hiện:

1. Gọi API tạo hóa đơn thành công.
2. Sau đó gặp lỗi khi ghi trạng thái hoặc commit offset.
3. Record được retry.
4. Listener gọi API tạo hóa đơn lần nữa.

Nếu API không idempotent, có thể tạo hai hóa đơn cho cùng một đơn hàng. Retry vô hạn làm xác suất lặp tăng theo số lần thử.

Hãy dùng event ID hoặc idempotency key ổn định qua mọi lần retry. Consumer có thể lưu event ID đã xử lý trong cùng database transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Nếu event ID đã tồn tại, bỏ qua side effect lặp. Việc ghi nhận event ID và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction để tránh race condition.

Với HTTP API hoặc dịch vụ ngoài, truyền idempotency key nếu API hỗ trợ. Nếu không có cơ chế idempotency, cần tra cứu trạng thái thao tác trước khi gửi lại một lệnh có kết quả chưa rõ ràng.

## 10. Rủi ro 5: Không có điểm kết thúc và DLT không nhận được record

Trong retry hữu hạn, khi hết attempts, error handler có thể gọi recoverer để gửi record sang DLT. Với retry vô hạn, số lần thử không bao giờ cạn, vì vậy không có sự kiện "hết attempts" để tự động kích hoạt recovery theo ngưỡng đó.

Điều này có nghĩa:

- DLT không tự động trở thành nơi chứa mọi record bị lỗi khi retry vô hạn.
- Record có thể nằm mãi trong retry loop hoặc retry topic.
- Người vận hành cần một điều kiện chuyển hướng riêng nếu muốn dừng retry.
- Permanent exception cần được phân loại non-retryable hoặc có một recovery path độc lập.

Nếu yêu cầu là "thử lỗi tạm thời vô hạn, nhưng dữ liệu sai phải vào DLT", hãy cấu hình exception classification rõ ràng. Unlimited attempts chỉ áp dụng cho nhóm exception được phép retry; lỗi permanent cần đi tới recovery ngay hoặc sau một số lần thử hữu hạn.

## 11. Rủi ro 6: Retention và mất cơ hội replay

Retry topic là topic Kafka bình thường và chịu ảnh hưởng của retention policy. Nếu record chờ quá lâu và retention hết hạn trước khi consumer retry đọc tới, record có thể bị xóa theo chính sách log retention.

Với retry vô hạn, thời gian tồn tại của record không có giới hạn theo số lần retry. Do đó, retention phải đủ dài so với thời gian outage tối đa mà nghiệp vụ muốn chịu đựng. Nếu cần lưu record lỗi lâu hơn, DLT hoặc một kho lưu trữ bền vững riêng có thể phù hợp hơn.

Đừng mặc định unlimited attempts đồng nghĩa với lưu trữ vĩnh viễn. Retry count không giới hạn và retention là hai cơ chế độc lập.

## 12. Rủi ro 7: Ordering bị thay đổi

Blocking retry thường giữ record lỗi ở đầu luồng xử lý partition, vì vậy các record phía sau có thể phải chờ. Điều này duy trì thứ tự xử lý theo partition nhưng làm giảm tiến độ.

Non-blocking retry topic cho phép consumer chính tiếp tục, nhưng record lỗi có thể quay lại sau các record mới hơn. Ví dụ:

~~~text
Topic chính:   A1 -> A2 -> A3
                  |
                  +-- A2 lỗi, chuyển sang retry topic

Consumer chính tiếp tục: A1 -> A3
Retry topic xử lý sau:   A2
~~~

Kết quả xử lý có thể thành A1, A3, A2. Nếu A2 và A3 thay đổi cùng một aggregate theo thứ tự bắt buộc, kết quả nghiệp vụ có thể sai.

Trước khi dùng non-blocking retry vô hạn, xác định ordering requirement theo key/partition. Nếu cần giữ thứ tự, cân nhắc blocking retry có giới hạn, tách luồng xử lý lỗi hoặc thiết kế state machine có version/sequence để từ chối cập nhật sai thứ tự.

## 13. Rủi ro 8: Tài nguyên và chi phí vận hành tăng

Retry vô hạn có thể làm tăng:

- Số lần gọi dependency và chi phí API.
- Thời gian giữ consumer thread và bộ nhớ.
- Kích thước backlog của retry topic.
- Số lượng metric/log và chi phí lưu trữ.
- Công việc điều tra và replay của đội vận hành.
- Thời gian record nằm ngoài SLO.

Nếu record không thể được xử lý trong nhiều giờ, cần quyết định có nên giữ nó trong retry loop hay chuyển sang một workflow có trạng thái rõ ràng. Một record chờ vô hạn mà không có owner hoặc alert sẽ trở thành dữ liệu bị bỏ quên.

## 14. Khi nào nên dùng retry vô hạn?

Retry vô hạn chỉ phù hợp khi tất cả điều kiện quan trọng sau được đáp ứng:

- Lỗi thuộc nhóm transient hoặc có khả năng tự phục hồi mà không cần sửa payload.
- Nghiệp vụ không cho phép bỏ qua record.
- Việc giữ record chờ không làm vi phạm SLO hoặc có một quy trình chấp nhận độ trễ rất dài.
- Có backoff và timeout hữu hạn cho mỗi lần gọi dependency.
- Có cơ chế idempotency cho side effect.
- Có dashboard/alert để phát hiện record retry kéo dài.
- Có cách dừng, sửa hoặc chuyển hướng record khi điều kiện thay đổi.
- Retention của retry topic phù hợp với thời gian outage cần chịu đựng.

Ví dụ có thể cân nhắc: một consumer nội bộ xử lý command có tính bền vững, phụ thuộc một service có SLA phục hồi rõ ràng, và việc xử lý sau vài phút/giờ vẫn có giá trị. Ngay cả trong trường hợp đó, cần kiểm soát tải và có cơ chế vận hành để phát hiện backlog.

## 15. Khi nào không nên dùng?

Tránh retry vô hạn khi:

- Exception thường là permanent như schema sai hoặc business validation thất bại.
- Record lỗi có thể chặn toàn bộ partition quan trọng.
- Dependency không có timeout hoặc không thể giới hạn concurrency.
- Side effect không idempotent và không thể tra cứu kết quả trước khi retry.
- Retry làm vi phạm max.poll.interval.ms hoặc gây rebalance liên tục.
- Retry topic có retention ngắn hơn thời gian chờ có thể xảy ra.
- Không có alert, owner hoặc quy trình xử lý record bị kẹt.
- Nghiệp vụ yêu cầu thông báo lỗi cuối cùng trong một thời hạn cụ thể.

Trong những trường hợp này, retry hữu hạn với DLT, retry topic có giới hạn, hoặc workflow lưu trạng thái chờ có thể dễ vận hành hơn.

## 16. Kết hợp unlimited attempts với exception classification

Một thiết kế an toàn thường không áp dụng retry vô hạn cho tất cả exception. Chỉ một tập exception transient được retry vô hạn; exception permanent đi thẳng tới recovery hoặc DLT.

Ví dụ:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff =
        new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class,
        InvalidCustomerStateException.class
    );

    return handler;
}
~~~

Ví dụ này cho thấy lỗi validation được loại khỏi retry vô hạn. Các exception khác vẫn chịu classification mặc định, vì vậy cần xem xét danh sách exception retryable/non-retryable của phiên bản Spring Kafka và khai báo rõ theo nghiệp vụ.

Nếu dùng custom exception wrapper, hãy đảm bảo error handler nhìn thấy loại exception mà bạn đã phân loại. Một RuntimeException chung bọc lỗi validation có thể khiến policy không hoạt động như mong đợi nếu classification không xem xét cause.

## 17. Chiến lược thay thế: retry hữu hạn rồi DLT

Với nhiều hệ thống production, retry hữu hạn dễ kiểm soát hơn:

1. Thử lại một số lần với exponential backoff.
2. Khi hết retry, publish record sang DLT.
3. Ghi metadata về nguyên nhân, offset và event ID.
4. Phát cảnh báo để người vận hành hoặc workflow xử lý.
5. Sau khi sửa lỗi, replay record có kiểm soát.

Cách này tạo điểm kết thúc rõ ràng. Nó tránh việc một record lỗi chiếm consumer mãi mãi và cho phép đội vận hành phân loại backlog.

Ví dụ:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

Retry hữu hạn không tự động bảo đảm record không bị mất. Recoverer phải publish thành công và offset gốc chỉ được tiến lên theo chính sách đã chọn. Cần theo dõi cả lỗi DLT publish và quy trình replay.

## 18. Quan sát và cảnh báo retry vô hạn

Nếu cho phép retry vô hạn, dashboard phải thể hiện record đang retry trong bao lâu và dependency có phục hồi hay không.

Các tín hiệu nên theo dõi:

| Tín hiệu | Điều cần phát hiện |
|---|---|
| Retry attempts theo exception và topic | Lỗi nào đang lặp nhiều lần |
| Age của lần retry đầu tiên | Record đã bị giữ bao lâu |
| Retry rate theo consumer/member | Instance nào tạo tải retry lớn |
| Backoff duration | Consumer đang chờ bao lâu |
| Consumer lag theo partition | Partition nào không tiến triển |
| Oldest record age | Độ trễ nghiệp vụ thực tế |
| Dependency availability/latency | Nguyên nhân transient đã phục hồi chưa |
| Rebalance count | Retry blocking có làm consumer mất nhịp poll không |
| Retry topic lag | Backlog retry đang tích tụ ở đâu |
| DLT publish/recovery failure | Record có bị kẹt trong bước phục hồi không |

Log nên có topic, partition, offset, event ID, exception class, root cause, retry count hoặc retry timestamp và correlation ID. Không log toàn bộ payload nhạy cảm.

Đặt cảnh báo theo tuổi record và thời gian retry, không chỉ theo số lần. Với retry vô hạn, số lần có thể rất lớn nhưng một record chờ 30 giây có thể chấp nhận được; ngược lại, một record chờ nhiều giờ có thể đã vi phạm SLO dù retry count không cao.

## 19. Runbook xử lý record retry vô hạn

Khi phát hiện một record retry kéo dài:

### Bước 1: Xác định record và phạm vi ảnh hưởng

- Topic, partition, offset và event ID là gì?
- Consumer group nào đang xử lý?
- Record đang bị blocking retry hay nằm trong retry topic?
- Lag của partition và tuổi record tăng như thế nào?

### Bước 2: Xác định nguyên nhân

- Lỗi có transient hay permanent?
- Dependency có đang phục hồi không?
- Có schema, ACL, cấu hình hoặc business state sai không?
- Có một record duy nhất bị lỗi hay toàn bộ consumer đang gặp lỗi?

### Bước 3: Bảo vệ dependency

- Kiểm tra retry rate và request rate.
- Giảm concurrency hoặc dùng circuit breaker/pause nếu dependency quá tải.
- Đặt timeout và backoff phù hợp.
- Tránh restart hàng loạt consumer khi nguyên nhân chưa được xử lý.

### Bước 4: Chọn hướng phục hồi

- Nếu lỗi transient: khôi phục dependency và để retry tiếp tục.
- Nếu lỗi permanent: dừng retry cho loại exception đó, chuyển DLT hoặc sửa dữ liệu.
- Nếu side effect chưa rõ kết quả: tra cứu bằng event ID/idempotency key trước khi replay.
- Nếu ordering quan trọng: đánh giá tác động của việc bỏ qua hoặc chuyển record sang retry topic.

### Bước 5: Xác nhận tiến triển

Theo dõi record thành công, committed offset tiến lên, lag giảm, retry rate giảm và dependency ổn định. Ghi lại nguyên nhân và điều chỉnh classification để cùng lỗi không bị retry vô hạn lần nữa.

## 20. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Retry vô hạn mọi exception | Permanent exception giữ partition không tiến triển | Phân loại exception và loại lỗi permanent khỏi retry |
| Dùng delay bằng 0 | Retry storm, CPU và dependency quá tải | Dùng backoff có khoảng chờ và giới hạn tải |
| Nghĩ UNLIMITED_ATTEMPTS bảo đảm eventual success | Record có thể lỗi mãi nếu nguyên nhân không đổi | Theo dõi, phân loại và có quy trình can thiệp |
| Không đặt timeout cho dependency | Một lần retry có thể treo vô hạn | Đặt timeout hữu hạn cho mỗi lần gọi |
| Không kiểm tra max.poll.interval.ms | Blocking retry có thể gây rebalance | Tính poll budget hoặc dùng retry topic |
| Cho rằng retry vô hạn tự chuyển sang DLT | Không có ngưỡng attempts để kích hoạt recovery theo số lần | Định tuyến permanent exception riêng và có điều kiện recovery |
| Dùng retry topic nhưng retention quá ngắn | Record có thể hết hạn trước khi retry | Đặt retention theo outage window và SLO |
| Không idempotent side effect | Replay tạo nghiệp vụ trùng | Dùng event ID/idempotency key và inbox |
| Không cảnh báo record cũ | Backlog bị bỏ quên | Alert theo oldest record age và retry duration |
| Restart consumer liên tục | Rebalance và duplicate tăng | Xử lý root cause trước khi restart |

## 21. Checklist trước khi bật UNLIMITED_ATTEMPTS

Trước khi triển khai, hãy trả lời:

1. Retry vô hạn áp dụng cho loại exception nào?
2. Permanent exception có được loại khỏi retry và đưa vào recovery không?
3. BackOff có khoảng chờ hữu hạn, hợp lý và tránh retry storm không?
4. Mỗi lần gọi database/HTTP có timeout không?
5. Blocking retry có thể vượt max.poll.interval.ms không?
6. Nếu dùng retry topic, retention có đủ dài cho outage window không?
7. Ordering của partition có bị thay đổi nếu chuyển sang non-blocking retry không?
8. Side effect có idempotent khi cùng record được xử lý nhiều lần không?
9. Có dashboard cho retry rate, oldest record age, lag, rebalance và dependency health không?
10. Ai sẽ nhận alert và quy trình dừng/sửa/replay record là gì?
11. Có cách xác nhận record đã thành công trước khi replay một thao tác có kết quả chưa rõ không?
12. Có thể thay retry vô hạn bằng retry hữu hạn và DLT mà vẫn đáp ứng yêu cầu nghiệp vụ không?

UNLIMITED_ATTEMPTS phù hợp với một số lỗi transient mà nghiệp vụ không cho phép bỏ qua, nhưng nó loại bỏ điểm kết thúc dựa trên số lần thử. Khi dùng, hãy giới hạn tải bằng backoff, phân loại permanent exception, bảo vệ side effect bằng idempotency và theo dõi tuổi record. Nếu không có những cơ chế đó, retry vô hạn có thể biến một lỗi đơn lẻ thành partition bị kẹt, consumer lag kéo dài và sự cố lan sang dependency khác.
