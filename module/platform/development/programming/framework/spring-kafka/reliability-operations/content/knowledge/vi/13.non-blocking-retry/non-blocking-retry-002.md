# RetryTopicConfiguration trong Spring Kafka

Trong Spring Kafka, **RetryTopicConfiguration** cho phép định nghĩa **non-blocking retry** bằng một Spring bean tạo qua RetryTopicConfigurationBuilder. Khi một listener xử lý record thất bại, framework có thể chuyển record sang retry topic. Consumer của topic nguồn tiếp tục xử lý record khác; consumer của retry topic thử xử lý lại sau khoảng chờ được cấu hình. Khi hết số lần thử, record được chuyển tới dead-letter topic (DLT) hoặc xử lý theo chính sách recovery.

Cách này phù hợp khi hệ thống muốn tránh giữ một partition nguồn chờ dependency phục hồi trong nhiều giây hoặc nhiều phút. Nó đặc biệt hữu ích khi cần quản lý chính sách retry tập trung cho nhiều listener. Đổi lại, retry topic làm tăng số topic, cần quyền ghi/đọc, phải được giám sát và có thể thay đổi thứ tự xử lý nghiệp vụ.

## 1. Non-blocking retry giải quyết vấn đề gì?

Giả sử listener tiêu thụ OrderCreated và gọi một dịch vụ bên ngoài. Dịch vụ đang trả HTTP 503. Nếu dùng blocking retry với một backoff dài, consumer có thể giữ record hiện tại và làm record phía sau phải chờ. Với non-blocking retry, record lỗi được chuyển sang topic riêng để xử lý lại ở thời điểm khác.

~~~text
orders.created
      |
      v
@KafkaListener
      |
      +--> Thành công ------------------> Hoàn tất
      |
      +--> Exception retryable
                 |
                 v
        Retry destination 1
                 |
                 | Đủ thời gian chờ
                 v
        Listener retry
                 |
                 +--> Thành công ------> Hoàn tất
                 |
                 +--> Vẫn lỗi
                          |
                          v
                  Retry destination 2
                          |
                          v
                    Listener retry
                          |
                          +--> Thành công
                          |
                          +--> Hết attempts
                                  |
                                  v
                                 DLT
~~~

Đây là các *giai đoạn logic*. Số retry topic vật lý có thể khác nhau theo backoff policy và cách framework tái sử dụng topic có cùng delay. Không nên mặc định mỗi lần retry sẽ tạo một topic riêng.

Lợi ích chính là consumer nguồn có thể tiến lên sau khi việc chuyển tiếp record lỗi thành công. Điều này hữu ích khi các record độc lập và không cần giữ thứ tự tuyệt đối giữa các sự kiện.

## 2. RetryTopicConfiguration khác RetryTopicConfigurationBuilder thế nào?

RetryTopicConfiguration là đối tượng biểu diễn cấu hình retry topic được Spring Kafka sử dụng để tạo các destination topic và listener endpoint liên quan. RetryTopicConfigurationBuilder là API để xây dựng đối tượng đó.

Ví dụ tạo bean:

~~~java
@Bean
RetryTopicConfiguration ordersRetryConfiguration(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}
~~~

Ý nghĩa:

- fixedBackOff(2_000L): khoảng chờ logic hai giây trước khi xử lý lại.
- maxAttempts(4): tối đa bốn lần gọi listener, bao gồm lần đầu tại topic nguồn và ba lần retry.
- includeTopics("orders.created"): áp chính sách cho topic được chỉ định.
- create(kafkaTemplate): tạo cấu hình, cung cấp template để framework phát record sang retry/DLT topic.

Một bean RetryTopicConfiguration **không** tự thay đổi hành vi của mọi KafkaTemplate.send trong ứng dụng. Nó điều khiển luồng xử lý lỗi của các listener endpoint có topic phù hợp.

Builder có các nhóm tùy chọn như topic selection, backoff, số attempts, DLT strategy, tên destination topic, cấu hình tạo topic và exception classification. Một số phương thức/overload chuyên biệt khác nhau theo phiên bản Spring Kafka; cần sử dụng API đúng phiên bản project.

## 3. Cấu hình tối thiểu trong Spring Boot

Một cấu hình minh họa:

~~~java
@Configuration
@EnableKafka
@EnableKafkaRetryTopic
public class OrdersKafkaRetryConfiguration {

    @Bean
    RetryTopicConfiguration ordersRetryTopics(
            KafkaTemplate<String, Object> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .fixedBackOff(3_000L)
                .maxAttempts(4)
                .includeTopics("orders.created")
                .create(kafkaTemplate);
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersCreatedListener",
            topics = "orders.created",
            groupId = "orders-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.processIdempotently(event);
    }
}
~~~

Cấu hình kết nối broker, consumer group và serializer, ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.events
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

Đây là ví dụ định hướng cho một ứng dụng dùng JSON. Type mapping, serializers, deserializers và KafkaTemplate phải khớp với event contract thực tế.

Tùy phiên bản, Spring Kafka cung cấp cách kích hoạt retry infrastructure bằng @EnableKafkaRetryTopic hoặc cấu hình dựa trên RetryTopicConfigurationSupport. Không nên đồng thời đăng ký hai cơ chế infrastructure trùng lặp. Spring Boot auto-configuration cũng có thể cung cấp một phần các thành phần cần thiết; hãy xác nhận cách cấu hình phù hợp với phiên bản đang chạy.

## 4. maxAttempts tính cả lần xử lý ban đầu

maxAttempts là **tổng số attempts**, không phải chỉ số lần retry.

Với:

~~~java
.maxAttempts(4)
~~~

khi record luôn lỗi và được phép retry, chuỗi logic là:

| Attempt | Vị trí xử lý | Nếu thất bại |
|---:|---|---|
| 1 | Topic nguồn | Chuyển tới retry destination |
| 2 | Retry destination | Chuyển tới retry destination kế tiếp |
| 3 | Retry destination | Chuyển tới retry destination kế tiếp |
| 4 | Retry destination | Hết attempts, gọi recovery/DLT |

Như vậy có tối đa ba lần retry sau lần xử lý ban đầu. Nếu exception được phân loại không retryable, record có thể chuyển thẳng tới recovery sớm hơn.

Đừng nhầm attempts ở listener với thuộc tính retries của Kafka producer. Kafka producer retry một ProduceRequest bị lỗi; non-blocking retry thử lại **logic nghiệp vụ ở listener** sau khi record được chuyển tới topic retry.

## 5. Fixed backoff và exponential backoff

### Fixed backoff

Fixed backoff tạo khoảng chờ bằng nhau giữa các lần retry:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .fixedBackOff(5_000L)
        .maxAttempts(4)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

Ví dụ dùng delay 5 giây và tối đa ba lần retry. Nó phù hợp khi dependency thường phục hồi sau một thời gian ngắn và việc retry đồng đều không gây quá tải.

### Exponential backoff

Exponential backoff tăng delay sau mỗi lần thất bại:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .exponentialBackoff(1_000L, 2.0, 8_000L)
        .maxAttempts(5)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

Đây là ví dụ về initial delay một giây, hệ số nhân hai và max delay tám giây. Các khoảng chờ logic có thể là một, hai, bốn và tám giây. Hỗ trợ overload, jitter hoặc randomization tùy thuộc phiên bản API.

| Lần retry | Fixed delay 2 giây | Exponential minh họa |
|---:|---:|---:|
| 1 | 2 giây | 1 giây |
| 2 | 2 giây | 2 giây |
| 3 | 2 giây | 4 giây |
| 4 | 2 giây | 8 giây |

Thời điểm xử lý thực tế không chính xác tới mili giây. Retry consumer dựa vào timestamp và vòng poll để biết khi nào record đủ điều kiện chạy lại; độ trễ broker, rebalance và tải hệ thống có thể khiến record được gọi muộn hơn thời gian dự định.

Chọn backoff theo thời gian phục hồi của dependency, yêu cầu SLA, tải của hệ thống đích và tổng thời gian được phép trì hoãn sự kiện. Nếu nhiều instance retry cùng lúc, jitter giúp giảm hiệu ứng đồng loạt.

## 6. Vì sao non-blocking retry không giữ consumer nguồn?

Khi listener nguồn thất bại, framework chuyển tiếp record vào retry destination. Sau khi bước recovery/chuyển tiếp hoàn tất theo chính sách, listener container nguồn có thể xử lý record tiếp theo.

~~~text
Topic nguồn:
  Offset 100: A --> thất bại, chuyển A sang retry topic
  Offset 101: B --> xử lý thành công
  Offset 102: C --> xử lý thành công

Retry topic:
  A --> chờ tới retry timestamp --> thử lại
~~~

Retry topic consumer có thể pause partition trong lúc chờ tới thời điểm đủ điều kiện xử lý, nhưng tiếp tục poll để duy trì membership consumer group. Điều này khác việc đặt Thread.sleep dài ngay trong listener nguồn.

Một hệ thống non-blocking retry không phải bộ hẹn giờ nghiệp vụ chính xác tuyệt đối. Nếu sự kiện phải xảy ra đúng một thời điểm cố định hoặc phải có khả năng tái lập lịch độc lập với Kafka polling, cần một scheduler/queue bền vững chuyên dụng.

## 7. Retry topic naming, số topic và topic reuse

Khi bật retry topic, framework phải xây dựng một topology gồm topic nguồn, các retry destinations và DLT.

Ví dụ tên topic minh họa:

~~~text
orders.created
    |
    +--> orders.created-retry-2000
    +--> orders.created-retry-4000
    +--> orders.created-dlt
~~~

Tên thực tế phụ thuộc suffix strategy, backoff delays, các tùy chọn tái sử dụng topic và phiên bản. Với fixed delay, nhiều lần retry có thể dùng cùng retry topic hoặc được ánh xạ thành những topic khác nhau. Không suy luận một cách máy móc rằng maxAttempts(4) sẽ luôn tạo ba topic retry.

Trong production, cần biết chính xác các topic sẽ tồn tại vì chúng ảnh hưởng đến:

- Topic/partition count và tài nguyên broker.
- Quyền đọc và ghi của principal Kafka.
- Chính sách retention, replication factor, min.insync.replicas.
- Metrics consumer lag theo từng retry stage.
- Quy trình provision và cleanup topic khi thay đổi retry policy.

Nếu đặt tên retry topics tùy chỉnh, hãy bảo đảm không trùng với tên topic nghiệp vụ hoặc cấu hình khác, nhất là khi có nhiều listener trong cùng application context.

## 8. Auto-create retry/DLT topics hay provision thủ công

Framework có thể tạo các retry/DLT topics thông qua KafkaAdmin trong những cấu hình cho phép. Với môi trường production có IaC, tổ chức có thể muốn tạo trước toàn bộ topic bằng Terraform/Helm hoặc pipeline quản trị.

Ví dụ đặt số partition và replication factor thông qua builder:

~~~java
RetryTopicConfigurationBuilder.newInstance()
        .fixedBackOff(2_000L)
        .maxAttempts(4)
        .autoCreateTopicsWith(6, (short) 3)
        .includeTopics("orders.created")
        .create(kafkaTemplate);
~~~

Cấu hình trên minh họa sáu partition và replication factor ba cho các topic được tạo theo cơ chế hỗ trợ. Cluster phải có ít nhất ba broker phù hợp để tạo topic với replication factor ba.

Nếu quản trị topic thủ công, cần tạo đúng những destination topics mà framework sẽ dùng, đặt đủ partition, bảo đảm retention, và cấp ACL ghi cho producer chuyển tiếp và ACL đọc cho các retry/DLT consumers.

Đừng mặc định retry topic có cùng mọi cấu hình retention, cleanup hoặc quota với topic nguồn. Đây là các topic có vòng đời vận hành riêng.

## 9. Key, partition và nguy cơ xử lý sai thứ tự

Kafka giữ thứ tự offset trong một partition của một topic. Non-blocking retry di chuyển record sang topic khác, do đó **không bảo đảm thứ tự nghiệp vụ xuyên suốt topic nguồn và retry topic**.

~~~text
Cùng key order-9:
  A: status = CREATED --> lỗi, sang retry topic
  B: status = PAID    --> xử lý thành công tại nguồn
  A: retry sau        --> có thể cập nhật trạng thái ngược lại
~~~

Giữ nguyên Kafka key giúp record cùng key vào cùng partition ở từng topic khi phân vùng được cấu hình tương ứng, nhưng không ép record đang retry được xử lý trước record mới ở topic nguồn.

Nếu một aggregate yêu cầu thứ tự:

1. Gắn event version/sequence và kiểm tra trước khi cập nhật.
2. Dùng optimistic locking hoặc state transition validation.
3. Chặn sự kiện mới cùng aggregate khi có sự kiện cũ chưa hoàn tất, nếu nghiệp vụ cho phép.
4. Chọn blocking retry cho luồng đòi hỏi thứ tự tuyệt đối.
5. Thiết kế idempotency và reconciliation để khôi phục trạng thái nhất quán.

Non-blocking retry phù hợp hơn khi các record độc lập hoặc nghiệp vụ có khả năng phát hiện event đến không đúng thứ tự.

## 10. KafkaTemplate dùng để chuyển tiếp record

Phương thức create(kafkaTemplate) nhận template được framework sử dụng để publish record sang retry/DLT destinations. Template cần:

- Kết nối và xác thực được với Kafka cluster.
- Có quyền ghi retry/DLT topics.
- Key/value serializers tương thích với payload sẽ được chuyển tiếp.
- Có producer acknowledgement và timeout phù hợp.
- Xử lý lỗi gửi để không đánh dấu recovery thành công khi chưa lưu được record cần thiết.

Nếu consumer nhận JSON object, template có thể dùng JsonSerializer. Tuy nhiên, lỗi deserialization có thể cần gửi raw bytes sang DLT. Khi đó, hãy dùng serializer có thể xử lý cả object lẫn byte[] hoặc template/serializer chuyên dụng.

KafkaTemplate dùng cho retry topic có thể tự retry ProduceRequest ở tầng Kafka client. Đó là cơ chế khác với listener retry; không được tính producer retries vào maxAttempts của RetryTopicConfiguration.

Nếu publish sang retry topic thành công nhưng ứng dụng dừng trước khi offset nguồn được commit, record nguồn có thể được giao lại và tạo thêm bản sao retry. Vì vậy, non-blocking retry không tự bảo đảm exactly-once end-to-end.

## 11. Exception nào nên retry?

Không nên retry mọi exception theo cùng một policy.

| Lỗi | Hướng xử lý thường phù hợp |
|---|---|
| Database tạm mất kết nối | Retry với backoff hữu hạn |
| HTTP 429 hoặc 503 | Retry, cân nhắc Retry-After và jitter |
| Gọi API timeout | Retry có giới hạn, dùng idempotency key |
| JSON sai cú pháp | Non-retryable, DLT/quarantine |
| Field bắt buộc không hợp lệ | Non-retryable, sửa dữ liệu/producer |
| Authorization bị từ chối | Non-retryable, cảnh báo |
| Logic bug xác định | Giới hạn retries, DLT để điều tra |
| Dependency ngừng hoạt động hàng giờ | Delay dài và policy backlog rõ ràng |

RetryTopicConfigurationBuilder hỗ trợ các tùy chọn phân loại exception retryable/non-retryable, với tên phương thức và tùy chọn duyệt nested causes phụ thuộc phiên bản Spring Kafka. Nên định nghĩa exception domain như InvalidEventException hoặc TemporaryDependencyException và kiểm tra chính sách phân loại tại listener.

Nếu cùng một payload luôn gây lỗi validation, retry sau vài phút vẫn sẽ thất bại. Chuyển DLT sớm giúp giảm lag, chi phí broker và tải dependency.

## 12. DLT: điểm kết thúc cần vận hành

DLT giữ record không thể xử lý sau khi hết attempts hoặc gặp lỗi không retryable. DLT là điểm để điều tra và phục hồi, không phải bằng chứng nghiệp vụ đã thành công.

~~~text
orders.created
     |
     +--> Retry stage 1
     |
     +--> Retry stage 2
     |
     +--> Hết attempts / non-retryable
                    |
                    v
              orders.created-dlt
                    |
                    v
            Điều tra / sửa lỗi
                    |
                    v
              Replay kiểm soát
~~~

Có thể cấu hình một DLT handler hoặc chính sách xử lý lỗi của DLT theo API của phiên bản. Một handler riêng có thể ghi metadata lỗi, phát cảnh báo hoặc lưu incident:

~~~java
public void handleDeadLetter(
        ConsumerRecord<String, OrderCreated> record) {

    incidentService.recordFailure(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
    );
}
~~~

Đây là logic minh họa, chưa phải toàn bộ wiring endpoint DLT. Cần đăng ký đúng DLT listener/handler với framework và xử lý riêng trường hợp DLT handler cũng ném exception.

Vận hành DLT nên xác định quyền truy cập, retention, cách xử lý thông tin nhạy cảm, giám sát DLT backlog, chủ sở hữu xử lý và quy trình replay. Đừng tự động replay hàng loạt nếu chưa khắc phục nguyên nhân lỗi.

## 13. @RetryableTopic và RetryTopicConfiguration

Hai cách cấu hình cùng một nhóm chức năng:

| Tiêu chí | @RetryableTopic | RetryTopicConfiguration |
|---|---|---|
| Nơi định nghĩa | Annotation trên listener | Spring bean dùng builder |
| Phạm vi | Gắn gần listener | Có thể áp policy cho các topic được chọn |
| Tái sử dụng | Đơn giản với ít listener | Hữu ích khi có policy tập trung |
| Tùy biến theo Java config | Chủ yếu qua annotation attributes | Tạo chính sách bằng code |
| Khả năng đọc | Thấy ngay trên listener | Cần tra configuration bean |

Ví dụ annotation:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void onOrderCreated(OrderCreated event) {
    orderService.process(event);
}
~~~

Ví dụ builder tương đương về ý tưởng:

~~~java
@Bean
RetryTopicConfiguration ordersRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}
~~~

Không vô tình khai báo đồng thời annotation và bean cho cùng endpoint mà không hiểu quy tắc chọn cấu hình. Một listener nên có một chính sách retry được sở hữu rõ ràng.

## 14. Kết hợp blocking và non-blocking retry

Có trường hợp muốn thử ngay một vài lần bằng DefaultErrorHandler rồi mới đưa record sang retry topic để chờ lâu hơn.

~~~text
Listener thất bại
       |
       +--> Blocking retry 1-2 lần (ngắn)
       |           |
       |           +--> Thành công
       |           |
       |           +--> Vẫn lỗi
       |
       v
Publish retry topic (chờ lâu)
       |
       v
Listener retry tiếp
       |
       +--> Thành công
       |
       +--> Hết attempts --> DLT
~~~

Cấu hình kết hợp phải xác định tổng số lần xử lý thực tế. Ví dụ có bốn non-blocking stages và mỗi stage thử thêm hai blocking retries thì có thể chạy nghiệp vụ tối đa mười hai lần, tùy phiên bản và error handler configuration.

Đừng tính maxAttempts(4) như giới hạn tuyệt đối của toàn bộ pipeline nếu đã bổ sung retry blocking ở từng stage.

Cũng cần kiểm tra giới hạn non-blocking retry với batch listener và container transactions theo phiên bản. Không giả định mọi cơ chế DefaultErrorHandler có thể dùng cùng RetryTopicConfiguration mà không cấu hình riêng.

## 15. Non-blocking retry, transaction và idempotency

Khi chuyển record từ topic nguồn sang retry topic, việc publish và commit offset có thể không nguyên tử nếu không có transaction chung. Vì vậy có một cửa sổ lỗi:

~~~text
Listener nguồn thất bại
      |
      v
Publish retry record thành công
      |
      v
Process dừng trước khi commit offset nguồn
      |
      v
Record nguồn được giao lại
      |
      v
Có khả năng tạo retry record thứ hai
~~~

Với nhiều phiên bản Spring Kafka, non-blocking retry không hỗ trợ kết hợp trực tiếp với container transactions; cần kiểm tra rõ compatibility trước khi dùng KafkaTransactionManager ở listener này.

Dù sử dụng Kafka transaction hay không, database transaction và lời gọi HTTP bên ngoài không được Kafka tự động rollback. Một consumer an toàn nên dùng event ID ổn định và xử lý idempotent.

Ví dụ:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal amount
) {}
~~~

~~~java
@Transactional
public void process(OrderCreated event) {
    boolean firstDelivery =
            processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.applyOrderCreated(event);
}
~~~

insertIfAbsent đại diện thao tác insert có unique constraint trên event_id. Việc ghi nhận event đã xử lý và cập nhật dữ liệu nghiệp vụ cần nằm trong cùng transaction database.

Giữ nguyên event ID khi đi qua retry topics và khi replay DLT. Nếu gọi payment gateway hoặc một API có side effect, dùng idempotency key của hệ thống đích và reconciliation nếu kết quả lần gọi trước không chắc chắn.

## 16. Retention và resource planning

Retry topics lưu record trong Kafka. Nếu retention quá ngắn so với tổng thời gian chờ và downtime, record có thể bị xóa trước khi consumer có cơ hội thử lại.

Khi thiết kế retention:

- Tính tổng các khoảng backoff qua các stages.
- Thêm thời gian dự phòng cho consumer downtime và deployment.
- Dự phòng backlog khi dependency lỗi hàng giờ.
- Kiểm soát disk usage và broker quotas.
- Theo dõi tuổi record cũ nhất và consumer lag.
- Đặt retention của DLT đủ phục vụ điều tra, replay và yêu cầu dữ liệu.

Nếu retention của retry topic là 10 phút nhưng chính sách chờ tổng cộng có thể kéo dài 30 phút, record có nguy cơ hết hạn trước khi retry hoàn tất.

Topic được tạo tự động cũng cần đủ partition và replication factor. Tránh tạo vô hạn số topic mỗi lần tăng attempts hoặc thêm delay mới mà không đo chi phí metadata và vận hành broker.

## 17. Nhiều RetryTopicConfiguration beans

Một service có thể cần chính sách riêng cho các topic khác nhau.

~~~java
@Bean
RetryTopicConfiguration orderRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .fixedBackOff(2_000L)
            .maxAttempts(4)
            .includeTopics("orders.created")
            .create(kafkaTemplate);
}

@Bean
RetryTopicConfiguration emailRetry(
        KafkaTemplate<String, Object> kafkaTemplate) {

    return RetryTopicConfigurationBuilder.newInstance()
            .exponentialBackoff(5_000L, 2.0, 60_000L)
            .maxAttempts(6)
            .includeTopics("notifications.email")
            .create(kafkaTemplate);
}
~~~

Các topic khác nhau có SLA và lỗi khác nhau. Ví dụ notification có thể trì hoãn lâu hơn order processing, còn payment cần idempotency nghiêm ngặt.

Phải giữ phạm vi includeTopics rõ ràng. Nếu nhiều cấu hình cùng match một listener, kết quả chọn policy có thể khó dự đoán; tránh chồng lấn hoặc xác định quy tắc ưu tiên theo phiên bản.

## 18. Monitoring và khắc phục sự cố

Các tín hiệu cần theo dõi:

| Metric/tín hiệu | Điều cần biết |
|---|---|
| Retry topic ingress rate | Có nhiều record thất bại ở nguồn không |
| Retry consumer lag | Retry flow có theo kịp tốc độ gửi không |
| Attempt count | Record thường cần bao nhiêu lần chạy lại |
| DLT publish rate | Có bao nhiêu record hết attempts |
| DLT oldest age/backlog | Record lỗi tồn đọng bao lâu |
| Producer send errors | Có thất bại khi publish retry/DLT không |
| End-to-end event latency | Tổng thời gian hoàn thành nghiệp vụ |
| Rebalance count | Retry bị ảnh hưởng bởi chuyển partition không |
| Error count by class | Lỗi tạm thời hay cố định |
| Duplicate detection | Idempotency đang từ chối bao nhiêu lần giao lại |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter; một số metric cần ứng dụng chủ động ghi.

Log nên có eventId, topic nguồn, partition/offset, retry topic hiện tại, exception class, attempt và kết quả recovery. Tránh log raw payload nhạy cảm hoặc đưa eventId làm metric label có cardinality lớn.

### Các lỗi hay gặp

**Có bean nhưng không tạo retry flow:** kiểm tra infrastructure, includeTopics, bean registration, listener endpoint và factory.

**Retry topic không tồn tại:** kiểm tra topic creation policy, KafkaAdmin, naming, ACL và partition count.

**Serializer lỗi khi chuyển tiếp:** kiểm tra KafkaTemplate, payload type, raw byte[] và serializers.

**Đếm sai số lần:** maxAttempts gồm cả lần đầu ở topic nguồn.

**Record xử lý sai thứ tự:** retry topic cho phép record sau ở nguồn vượt qua record lỗi; cần versioning/state checks hoặc blocking retry.

**Dữ liệu không hợp lệ retry nhiều lần:** phân loại non-retryable và chuyển DLT sớm.

**DLT có record nhưng không được xử lý:** đặt ownership, alert và quy trình replay.

**Retry backlog tăng kéo dài:** kiểm tra dependency, topic consumer lag, retention, attempts và tổng thời gian chờ.

**Batch listener/transaction không tương thích:** kiểm tra giới hạn non-blocking retry của Spring Kafka version sử dụng.

## 19. Quy trình thiết kế một policy non-blocking retry

1. Xác định record có thể xử lý độc lập hay bắt buộc giữ thứ tự.
2. Phân loại exception retryable và non-retryable.
3. Xác định maxAttempts, bao gồm lần xử lý ban đầu.
4. Chọn fixed/exponential backoff theo thời gian dependency phục hồi.
5. Tạo RetryTopicConfiguration bean và giới hạn includeTopics.
6. Kích hoạt retry infrastructure bằng cơ chế phù hợp phiên bản.
7. Chọn KafkaTemplate và serializers tương thích với retry/DLT payload.
8. Provision topic, partition, replication, retention và ACL.
9. Thiết kế DLT handler, alert và quy trình replay.
10. Giữ event ID ổn định và xây idempotent consumer.
11. Đo lag, actual retry delay, DLT rate và end-to-end latency.
12. Kiểm tra các tình huống broker outage, dependency 503, restart và rebalance trước khi triển khai rộng.

Một cấu hình khởi đầu dễ hiểu cho một topic là:

~~~java
@Configuration
@EnableKafkaRetryTopic
public class RetryConfiguration {

    @Bean
    RetryTopicConfiguration ordersRetry(
            KafkaTemplate<String, Object> kafkaTemplate) {

        return RetryTopicConfigurationBuilder.newInstance()
                .fixedBackOff(3_000L)
                .maxAttempts(4)
                .includeTopics("orders.created")
                .create(kafkaTemplate);
    }
}
~~~

Listener đơn giản:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-service"
)
public void onOrderCreated(OrderCreated event) {
    orderService.processIdempotently(event);
}
~~~

Nếu xử lý thành công, event hoàn tất. Nếu listener ném lỗi retryable, Spring Kafka chuyển record qua retry flow. Khi hết attempts, record đi đến DLT hoặc recovery theo cấu hình. Cần xác nhận topology, serializer, exception policy và DLT handler trong ứng dụng thực tế.

RetryTopicConfiguration giúp chuẩn hóa chính sách non-blocking retry bằng code: số lần xử lý, khoảng chờ, topic được áp dụng và đường chuyển tiếp khi thất bại. Thiết kế vận hành cần bổ sung quản lý topic, idempotency, xử lý thứ tự và giám sát DLT để sự kiện lỗi được phục hồi hoặc được lưu lại an toàn, thay vì biến thành backlog không giới hạn.

