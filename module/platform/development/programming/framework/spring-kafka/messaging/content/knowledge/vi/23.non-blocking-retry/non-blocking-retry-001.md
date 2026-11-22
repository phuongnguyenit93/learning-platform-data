# Mô hình retryable topic

Khi một Kafka listener xử lý record thất bại, cách retry truyền thống là giữ record trên partition hiện tại và thử lại sau một khoảng backoff. Cách này gọi là **blocking retry**: consumer thread phải chờ lần xử lý lại, khiến các record phía sau trên partition đó bị chặn.

Spring Kafka cung cấp **non-blocking retry** bằng retryable topics. Khi listener thất bại, framework publish record sang một retry topic có thời điểm xử lý phù hợp, sau đó consumer của topic gốc có thể tiếp tục nhận các record khác. Một listener khác xử lý retry topic khi thời gian chờ đã đến; nếu tiếp tục thất bại, record được chuyển sang retry topic tiếp theo hoặc dead-letter topic (DLT).

Mô hình này phù hợp khi cần cách ly record lỗi tạm thời khỏi luồng chính và chấp nhận rằng thứ tự xử lý giữa các record có thể thay đổi. Nó đặc biệt hữu ích khi downstream cần thời gian phục hồi nhưng ứng dụng vẫn muốn tiếp tục xử lý các event độc lập.

## 1. Vì sao cần retryable topic?

Giả sử topic `orders.created` có ba record theo thứ tự:

```text
orders.created, partition 0
  offset 10: order A
  offset 11: order B  -- xử lý lỗi do dịch vụ tồn kho timeout
  offset 12: order C
```

Với blocking retry, consumer giữ việc xử lý ở record B trong lúc retry. Record C phải chờ B xử lý xong hoặc được recovery. Nếu B cần chờ 30 giây, các record sau trong partition cũng bị chậm.

Với non-blocking retry, khi B thất bại, framework gửi B sang retry topic và xác nhận tiến độ của topic gốc sau khi việc chuyển tiếp được xử lý thành công. Consumer topic gốc có thể tiếp tục với C. B sẽ được xử lý lại ở retry topic sau khoảng chờ đã cấu hình.

Điều này giảm việc một record lỗi tạm thời chặn cả partition, nhưng tạo ra một đánh đổi: record C có thể được xử lý trước B. Non-blocking retry không bảo toàn thứ tự xử lý toàn cục của các record trong partition gốc.

## 2. Topology của retryable topics

Một luồng retryable topic thường có ba loại topic:

- **Main topic:** topic nghiệp vụ ban đầu, ví dụ `orders.created`.
- **Retry topics:** các topic trung gian chứa record cần thử lại sau những khoảng thời gian khác nhau.
- **Dead-letter topic:** nơi nhận record sau khi đã hết số lần thử hoặc không còn retry path phù hợp.

```text
                         thành công
                    +--------------------> xử lý xong
                    |
orders.created ---> Listener chính
                    |
                    | lỗi
                    v
              orders.created-retry-0
                    |
                    | đến thời điểm retry
                    v
              Retry listener 0
                    |
              +-----+------+
              |            |
          thành công       lỗi
              |            |
              v            v
           hoàn tất   orders.created-retry-1
                            |
                            v
                      Retry listener 1
                            |
                       +----+----+
                       |         |
                   thành công   lỗi/hết attempts
                       |         |
                       v         v
                    hoàn tất  orders.created-dlt
```

Tên topic minh họa trong sơ đồ. Spring Kafka tạo tên retry topic theo base topic, suffix và chiến lược đánh số/đặt tên được cấu hình. Hãy kiểm tra tên thực tế của topic được tạo thay vì phụ thuộc vào một hậu tố mặc định cụ thể.

Retry topic không tự tạo ra thời gian chờ chỉ bằng Kafka retention. Spring Kafka gắn metadata backoff vào record và điều phối listener của retry topic để record chỉ được xử lý khi thời điểm retry đến. Trong lúc chưa đến hạn, partition tương ứng có thể được pause; consumer vẫn được quản lý theo cơ chế listener container.

## 3. Non-blocking retry khác blocking retry như thế nào?

| Tiêu chí | Blocking retry | Non-blocking retry |
| --- | --- | --- |
| Cách thử lại | Retry tại consumer/listener hiện tại | Publish record sang retry topic |
| Consumer thread | Chờ backoff và retry | Không cần giữ thread chính chờ toàn bộ thời gian delay |
| Record phía sau | Có thể bị chặn trên partition đang retry | Có thể tiếp tục được xử lý từ main topic |
| Ordering | Giữ luồng partition dễ dự đoán hơn nếu xử lý tuần tự | Có thể đảo thứ tự giữa record lỗi và record phía sau |
| Hạ tầng | Chủ yếu cần main topic và error handler | Cần thêm retry topics, listener và DLT |
| Phù hợp | Retry ngắn, cần giữ ordering | Delay dài, muốn cách ly record lỗi |

Không có cách nào luôn tốt hơn. Nếu thứ tự event theo aggregate là yêu cầu bắt buộc, blocking retry có thể phù hợp hơn. Nếu các event độc lập và ưu tiên throughput, retryable topics có thể giảm ảnh hưởng của một record lỗi.

## 4. Bật retry topic infrastructure

Với cấu hình Java thuần, bật cơ chế retry topic bằng `@EnableKafkaRetryTopic`. Annotation này kích hoạt hạ tầng retry topic của Spring Kafka và bao gồm hỗ trợ listener cần thiết.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
```

Trong Spring Boot, vẫn cần bảo đảm retry topic infrastructure được bật theo cấu hình của phiên bản Spring Kafka đang sử dụng. Không đăng ký nhiều lần các cấu hình enable/retry infrastructure trùng nhau nếu ứng dụng đã có cấu hình tương đương.

Spring Kafka hỗ trợ non-blocking retry từ dòng 2.7. Hãy kiểm tra phiên bản Spring Kafka tương thích với Spring Boot và Kafka client của dự án trước khi sử dụng annotation hoặc thuộc tính mới.

## 5. Khai báo @RetryableTopic

Cách ngắn gọn nhất là đặt `@RetryableTopic` cùng với `@KafkaListener` trên phương thức xử lý chính:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            retryTopicSuffix = "-retry",
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-projection")
    public void onMessage(OrderCreatedEvent event) {
        orderService.process(event);
    }
}
```

Trong ví dụ, `attempts = "4"` là tổng số lần delivery tối đa, bao gồm lần đầu trên main topic. Vì vậy record có tối đa ba lần thử bổ sung trên retry path. Backoff tăng theo hệ số 2: khoảng chờ lần lượt là 1 giây, 2 giây, 4 giây, với giới hạn tối đa 10 giây nếu cần thêm các lần thử.

`retryTopicSuffix` và `dltTopicSuffix` giúp đặt quy ước tên topic. Các retry topic cụ thể được framework tạo theo chiến lược suffixing và cấu hình backoff. Annotation hỗ trợ nhiều thuộc tính hơn, nhưng nên bắt đầu với số lần thử, backoff, suffix và chính sách DLT đủ rõ ràng.

## 6. Hiểu attempts và backoff

`attempts` biểu thị tổng số lần listener có thể nhận record trong toàn bộ luồng, tính cả lần xử lý đầu tiên. Ví dụ:

| `attempts` | Lần đầu trên main topic | Số lần retry bổ sung |
| --- | ---: | ---: |
| `1` | 1 | 0 |
| `2` | 1 | 1 |
| `3` | 1 | 2 |
| `4` | 1 | 3 |

Backoff xác định khoảng thời gian chờ trước lần thử tiếp theo. Ví dụ:

```java
@Backoff(delay = 2_000)
```

Retry sau khoảng 2 giây cho mỗi lần thử. Với exponential backoff:

```java
@Backoff(delay = 1_000, multiplier = 2.0, maxDelay = 30_000)
```

Khoảng chờ tăng theo cấp số nhân và bị giới hạn ở 30 giây. Cách này giảm áp lực lên downstream đang phục hồi, thay vì liên tục gửi lại request với khoảng cách cố định rất ngắn.

Backoff không phải cam kết thời điểm xử lý chính xác đến mili giây. Consumer lag, scheduling, rebalance, broker load và thời gian xử lý record có thể khiến thời điểm thực tế muộn hơn.

## 7. Retry topic được chọn như thế nào?

Với nhiều khoảng backoff khác nhau, Spring Kafka tạo các retry topic tương ứng theo chiến lược suffixing. Ví dụ về mặt logic:

| Đường đi | Vai trò |
| --- | --- |
| `orders.created` | Lần giao đầu tiên |
| `orders.created-retry-0` | Retry sau khoảng chờ ngắn |
| `orders.created-retry-1` | Retry sau khoảng chờ dài hơn |
| `orders.created-dlt` | Nhận record sau khi hết attempts |

Các tên trên chỉ minh họa. Tùy `TopicSuffixingStrategy` và cấu hình tái sử dụng topic cùng khoảng delay, framework có thể dùng suffix theo chỉ số hoặc khoảng delay và có thể tái sử dụng retry topic cho nhiều lần thử cùng delay.

Khi cấu hình nhiều retry topic, cần tránh tạo quá nhiều topic cho một listener nếu không có nhu cầu rõ ràng. Mỗi topic kéo theo partition, metadata, consumer assignment và chi phí vận hành.

## 8. Phân loại exception: lỗi nào được retry?

Không phải exception nào cũng nên đưa vào retry path. Lỗi tạm thời như timeout hoặc lỗi kết nối có thể tự phục hồi. Lỗi dữ liệu như payload không hợp lệ thường không thay đổi sau một lần retry.

`@RetryableTopic` hỗ trợ chỉ định các exception được include hoặc exclude:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        include = {
                java.util.concurrent.TimeoutException.class,
                org.springframework.dao.TransientDataAccessException.class
        },
        exclude = {
                IllegalArgumentException.class,
                UnsupportedOperationException.class
        })
@KafkaListener(topics = "orders.created", groupId = "orders-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

Hãy kiểm tra cause chain nếu service bọc exception gốc trong exception khác. Spring Kafka có tùy chọn `traversingCauses` để xét các nguyên nhân lồng nhau khi phân loại. Nếu không cấu hình include/exclude, framework áp dụng classification mặc định; một số lỗi deserialize/conversion và lỗi không thể khắc phục bằng retry được xem là fatal và có thể đi thẳng tới DLT.

Nguyên tắc thực tế:

- Retry lỗi hạ tầng tạm thời: timeout, kết nối bị gián đoạn, rate limit có thể phục hồi.
- Không retry vô ích lỗi dữ liệu: schema không hợp lệ, thiếu trường bắt buộc, giá trị không thể chuyển đổi.
- Không retry lỗi logic vĩnh viễn: trạng thái nghiệp vụ không hợp lệ cần can thiệp hoặc sửa dữ liệu.
- Giới hạn số lần thử và thời gian tổng để tránh giữ record quá lâu trong hệ thống.

## 9. Xử lý record trong DLT bằng @DltHandler

Khi hết attempts, record được publish sang DLT. Có thể khai báo `@DltHandler` trong cùng bean với listener để xử lý record đó:

```java
import org.springframework.kafka.annotation.DltHandler;

@DltHandler
public void onDlt(OrderCreatedEvent event) {
    // Ghi nhận lỗi, lưu thông tin điều tra hoặc tạo cảnh báo.
    deadLetterService.recordFailure(event);
}
```

`@DltHandler` là listener xử lý message trên DLT tương ứng với endpoint retryable. Nếu không khai báo handler riêng, Spring Kafka sử dụng DLT handler mặc định để ghi log record. Trong production, nên có chính sách rõ ràng: lưu record lỗi, lưu exception metadata, cảnh báo, tạo ticket hoặc đưa vào quy trình replay.

Không nên chỉ ghi log rồi bỏ quên DLT. Cần theo dõi số lượng record, tuổi record cũ nhất, tỷ lệ tăng và trạng thái xử lý. DLT là hàng đợi cần được quản lý như một phần của quy trình vận hành.

## 10. Tạo retry topics và DLT

Spring Kafka có thể tự tạo retry topics và DLT thông qua Kafka Admin khi `autoCreateTopics` được bật. Có thể chỉ định số partition và replication factor cho các topic được tạo:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        autoCreateTopics = "true",
        numPartitions = "6",
        replicationFactor = "3")
@KafkaListener(topics = "orders.created", groupId = "orders-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

Ví dụ yêu cầu các topic retry/DLT được tạo với sáu partition và replication factor ba. Broker phải có đủ broker và cấu hình phù hợp để đáp ứng replication factor đó.

Trong production, nhiều đội vận hành chọn tạo topic bằng IaC hoặc quy trình quản trị cluster và đặt `autoCreateTopics = "false"`. Khi đó phải tạo sẵn toàn bộ retry topics và DLT đúng tên, partition count, replication factor, retention, cleanup policy và ACL. Nếu dùng partition resolver giữ nguyên partition của record gốc, retry topic/DLT phải có partition tương ứng.

Không nên chỉ dựa vào broker auto topic creation nếu hệ thống cần kiểm soát replication factor, retention hoặc quyền truy cập. Topic được tạo tự động có thể dùng cấu hình mặc định không phù hợp production.

## 11. Partition và key trên retry topic

Spring Kafka cố gắng giữ quan hệ partition khi chuyển record qua retry topic để việc định tuyến có thể dự đoán được. Do đó, retry topic cần có số partition tương thích với topic gốc. Nếu topic gốc có sáu partition nhưng retry topic chỉ có một partition, việc chuyển record theo partition index có thể thất bại.

Key của record thường được giữ khi publish sang retry topic, giúp tiếp tục nhận diện aggregate. Tuy nhiên, điều này không bảo đảm ordering xuyên suốt giữa main topic và retry topics: record sau có thể đã được xử lý trước khi record lỗi quay lại.

Khi tạo topic thủ công, hãy kiểm tra:

- Số partition đủ để ánh xạ partition từ topic gốc.
- Replication factor và min ISR phù hợp độ bền mong muốn.
- Retention đủ dài cho khoảng backoff và thời gian consumer outage.
- ACL cho producer publish retry/DLT và consumer đọc retry/DLT.
- Tên topic đúng suffixing strategy mà ứng dụng đang sử dụng.

## 12. Ordering và tính idempotent

Non-blocking retry cho phép record phía sau tiếp tục chạy trong khi record lỗi đang chờ retry. Vì vậy, thứ tự xử lý có thể thay đổi:

```text
Thứ tự ghi vào main topic:
  E1 -> E2 -> E3

Thứ tự xử lý có thể xảy ra:
  E1 -> E2 (lỗi, chuyển retry topic) -> E3 -> E2 (retry thành công)
```

Nếu E2 và E3 cùng cập nhật một aggregate, xử lý E3 trước E2 có thể tạo trạng thái sai. Cần đánh giá yêu cầu ordering theo nghiệp vụ trước khi chọn non-blocking retry.

Các biện pháp giảm rủi ro:

- Dùng event version hoặc sequence number theo aggregate để phát hiện event đến sai thứ tự.
- Thiết kế consumer idempotent để duplicate không tạo tác động lặp.
- Chỉ dùng non-blocking retry cho event có thể xử lý độc lập hoặc chấp nhận xử lý trễ.
- Nếu cần strict ordering theo partition, cân nhắc blocking retry hoặc thiết kế lại luồng event.
- Dùng inbox/unique event ID khi side effect ghi database có thể được thực hiện lại.

Non-blocking retry không phải cơ chế exactly-once. Việc publish record sang retry topic và commit offset gốc có thể có cửa sổ lỗi; consumer vẫn cần chịu được duplicate theo semantics thực tế của luồng.

## 13. Giới hạn: batch listener và Kafka transaction

Non-blocking retry có một số giới hạn kiến trúc quan trọng:

**Không hỗ trợ batch listener.** Retryable topic infrastructure được thiết kế quanh việc xử lý và chuyển tiếp từng record. Nếu listener nhận `List<ConsumerRecord<...>>` theo batch, không thể áp dụng nguyên xi `@RetryableTopic` như record listener.

**Không kết hợp với container transactions.** Non-blocking retry topic không hỗ trợ listener container chạy Kafka transaction để thực hiện EOS read-process-write. Khi dùng container transaction, hãy chọn retry/rollback theo transaction, chẳng hạn blocking retry và `DefaultAfterRollbackProcessor`.

**Không bảo toàn ordering của main topic.** Record lỗi có thể được xử lý sau các record phía sau.

**Có thêm hạ tầng vận hành.** Retry topics và DLT cần được tạo, giám sát, bảo vệ ACL và quản lý retention.

Nếu yêu cầu của hệ thống bao gồm batch, container transaction hoặc strict ordering, hãy xác nhận lại kiến trúc trước khi chọn retryable topics.

## 14. Cấu hình bằng RetryTopicConfigurationBuilder

Ngoài annotation, có thể cấu hình retry topic theo kiểu lập trình bằng `RetryTopicConfigurationBuilder`. Cách này hữu ích khi muốn áp dụng một chính sách cho nhiều topic hoặc tách cấu hình khỏi listener:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class RetryTopicConfigurationSetup {

    @Bean
    public RetryTopicConfiguration ordersRetryConfiguration(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .exponentialBackoff(1_000, 2.0, 10_000)
                .maxAttempts(4)
                .retryTopicSuffix("-retry")
                .dltSuffix("-dlt")
                .create(kafkaTemplate);
    }
}
```

Builder cho phép đặt backoff, số lần thử, suffix và phạm vi topic. Khi dùng builder, kiểm tra các method có sẵn trong đúng phiên bản Spring Kafka của dự án; API có thể được mở rộng giữa các phiên bản. Không cấu hình cùng một listener/topic bằng nhiều chính sách annotation và builder chồng chéo nếu chưa xác định rõ precedence và phạm vi áp dụng.

## 15. Dùng DLT như một quy trình vận hành

DLT không chỉ là nơi chứa message lỗi. Cần thiết kế vòng đời xử lý:

1. Ghi nhận topic, partition, offset và event ID gốc.
2. Lưu exception type, message và delivery attempt dưới dạng metadata có kiểm soát.
3. Cảnh báo khi số lượng DLT tăng bất thường hoặc record tồn tại quá lâu.
4. Phân loại lỗi dữ liệu, lỗi code và lỗi hạ tầng.
5. Sửa nguyên nhân trước khi replay.
6. Replay về main topic hoặc topic xử lý riêng với idempotency để tránh tác động trùng.
7. Lưu audit về người thực hiện và kết quả replay nếu đó là quy trình vận hành nhạy cảm.

Không replay hàng loạt DLT vào main topic khi lỗi gốc chưa được sửa. Điều đó có thể tạo vòng lặp lỗi và làm backlog tăng nhanh hơn.

## 16. Kiểm thử mô hình retryable topic

Integration test nên kiểm tra toàn bộ topology thay vì chỉ kiểm tra listener method.

Một kịch bản cơ bản:

1. Khởi tạo broker kiểm thử và topic `orders.created`.
2. Cấu hình listener với `@RetryableTopic`, số attempts nhỏ và backoff ngắn.
3. Gửi event mà service cố tình thất bại ở hai lần đầu rồi thành công.
4. Xác nhận event đi qua retry path và cuối cùng được xử lý thành công.
5. Gửi event luôn thất bại và xác nhận nó xuất hiện trên DLT sau khi hết attempts.
6. Xác nhận `@DltHandler` nhận đúng payload và metadata lỗi.

Các trường hợp nên kiểm thử thêm:

- Exception nằm trong `include` được retry.
- Exception nằm trong `exclude` không đi qua retry path thông thường.
- Backoff nhiều mức tạo đúng retry path theo cấu hình.
- Topic retry/DLT có partition phù hợp với topic gốc.
- Key và custom headers được giữ theo mong muốn.
- Record phía sau được xử lý trong lúc record trước đang chờ retry, xác nhận tác động ordering.
- DLT handler thất bại và chính sách DLT error được áp dụng.
- Consumer restart/rebalance trong lúc record đang chờ retry.

Sử dụng `CountDownLatch`, `BlockingQueue` hoặc Awaitility để chờ event và DLT với timeout. Không dùng `Thread.sleep` ngắn rồi kết luận retry topic không hoạt động; thời gian xử lý gồm poll, backoff, scheduling và consumer assignment.

## 17. Monitoring và vận hành

Khi chạy non-blocking retry, cần theo dõi cả main topic, retry topics và DLT:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Main consumer lag | Luồng chính có tiếp tục xử lý kịp hay không |
| Retry topic lag | Record retry có được xử lý đúng hạn không |
| DLT record count | Số lượng lỗi đã hết attempts |
| Age of oldest retry record | Record retry chờ lâu nhất đã tồn tại bao lâu |
| Retry rate theo exception | Nhóm lỗi nào đang tạo nhiều retry |
| DLT publish failure | Việc chuyển record lỗi có thất bại không |
| Processing latency | Độ trễ thực tế từ lúc nhận record đến khi xử lý xong |
| Rebalance count | Consumer group có thường xuyên tái phân bổ không |

Một main topic có lag thấp không có nghĩa toàn bộ event đã xử lý xong: record có thể đang nằm trong retry topic. Cần tổng hợp trạng thái của cả topology để đo thời gian xử lý end-to-end.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Record không được retry | Exception bị phân loại non-retryable hoặc retry infrastructure chưa bật | Kiểm tra include/exclude, fatal exceptions và `@EnableKafkaRetryTopic` |
| Retry topic không được tạo | Thiếu quyền Admin, `autoCreateTopics=false` hoặc cấu hình topic chưa đúng | Kiểm tra AdminClient/ACL và tạo topic thủ công |
| Lỗi khi publish sang retry topic | Retry topic thiếu partition tương ứng hoặc serializer không phù hợp | Đồng bộ partition count và producer configuration |
| Record xuất hiện trên DLT sớm | `attempts` tính cả lần đầu hoặc exception bị xem là fatal | Kiểm tra số attempts và classification |
| Event xử lý sai thứ tự | Main topic tiếp tục trong lúc record cũ đang chờ retry | Dùng blocking retry hoặc thiết kế ordering/versioning |
| Retry delay dài hơn cấu hình | Consumer lag, pause, rebalance hoặc broker load | Theo dõi retry topic lag và thời điểm thực tế |
| DLT tăng liên tục | Lỗi dữ liệu hoặc downstream chưa được khắc phục | Phân loại lỗi, cảnh báo và quy trình replay |
| Listener batch không dùng được retryable topic | Non-blocking retry không hỗ trợ batch listener | Chuyển sang record listener hoặc dùng blocking retry |
| Transactional listener không tương thích | Non-blocking retry không kết hợp container transaction | Dùng retry/rollback theo transaction |

## 19. Kết luận

Mô hình retryable topic của Spring Kafka thực hiện non-blocking retry bằng cách chuyển record lỗi từ main topic sang các retry topic có thời gian xử lý phù hợp. Khi retry tiếp tục thất bại, record đi qua các retry stage và cuối cùng có thể được chuyển sang DLT. `@RetryableTopic` giúp khai báo số attempts, backoff, exception classification và quy tắc đặt tên; `@DltHandler` xử lý record đã hết retry.

Mô hình này giúp luồng chính tiếp tục xử lý record khác trong lúc record lỗi chờ retry, nhưng có thêm topic, consumer và yêu cầu vận hành. Đổi lại, ordering có thể thay đổi; batch listener và container transactions không được hỗ trợ. Hãy chọn non-blocking retry khi nghiệp vụ chấp nhận xử lý trễ/khác thứ tự, dùng idempotency để chịu được redelivery, quản lý partition/retention/ACL của retry topics và coi DLT là một quy trình vận hành có giám sát.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring for Apache Kafka — @RetryableTopic API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/annotation/RetryableTopic.html)
- [Spring for Apache Kafka — @DltHandler API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/annotation/DltHandler.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
