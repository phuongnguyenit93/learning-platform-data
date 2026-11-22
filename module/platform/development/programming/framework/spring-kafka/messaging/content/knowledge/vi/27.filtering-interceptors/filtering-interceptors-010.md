# Chọn filter hay routing logic

Trong một hệ thống Kafka, không phải record nào consumer nhận được cũng cần đi vào listener nghiệp vụ. Có record cần bỏ qua vì không thuộc phạm vi xử lý, đã hết hạn hoặc không thỏa điều kiện. Cũng có record cần được chuyển đến một luồng khác tùy loại sự kiện, tenant, vùng dữ liệu hoặc trạng thái nghiệp vụ. Hai nhu cầu này trông giống nhau ở chỗ đều có thể khiến một record không đi tiếp vào listener hiện tại, nhưng chúng có mục đích và hệ quả khác nhau.

Filtering quyết định record có được listener hiện tại xử lý hay bị loại khỏi luồng của listener đó. Routing quyết định record được chuyển đến đâu hoặc listener/nhánh xử lý nào sẽ nhận nó. Nếu dùng filter để thay cho routing, record có thể bị bỏ qua và mất khỏi luồng nghiệp vụ mà không có nơi nhận tiếp theo. Nếu dùng routing cho trường hợp chỉ cần bỏ record, ứng dụng có thể tạo thêm topic, producer và độ phức tạp không cần thiết.

Trong Spring Kafka, RecordFilterStrategy là cơ chế lọc record ở listener container. RecordInterceptor là hook trước listener để quan sát hoặc biến đổi record, và có thể bỏ qua listener khi trả về null. Routing thường được thực hiện bằng cách chọn topic ngay ở producer, phân nhánh trong listener/router hoặc dùng các listener riêng cho từng topic. Bài học giúp chọn đúng cơ chế, cấu hình và kiểm thử hành vi của từng lựa chọn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt filter, interceptor và routing.
- Xác định khi nào nên discard record và khi nào phải chuyển record sang nhánh khác.
- Cấu hình RecordFilterStrategy trên listener container factory.
- Hiểu ý nghĩa giá trị boolean của filter và cách xử lý record bị loại.
- Chọn filter theo payload, header, key hoặc metadata Kafka.
- Phân biệt record filtering với batch filtering.
- Sử dụng RecordInterceptor cho logic cross-cutting trước listener.
- Chọn routing ở producer, listener hoặc một router chuyên biệt.
- Bảo toàn key, partition ordering và metadata khi forward record.
- Xử lý route không xác định, retry, DLT và lỗi publish.
- Tránh dùng filter làm cơ chế idempotency hoặc bảo mật.
- Kiểm thử để bảo đảm record không bị bỏ mất hoặc xử lý hai lần.

## 1. Phân biệt filter và routing

Filter trả lời câu hỏi: record này có cần được listener hiện tại xử lý không?

Routing trả lời câu hỏi: record này phải đi đến nhánh hoặc topic nào?

Ví dụ topic orders có các sự kiện:

- OrderCreated: xử lý tạo đơn.
- OrderCancelled: xử lý hủy đơn.
- OrderArchived: chuyển sang lưu trữ.
- InternalHeartbeat: không phải dữ liệu nghiệp vụ của listener.

Nếu listener chỉ quan tâm OrderCreated và OrderCancelled, nó có thể filter các record không thuộc phạm vi. Nhưng nếu OrderArchived cần được chuyển sang topic archive, record đó phải được route; discard nó sẽ làm mất cơ hội lưu trữ.

| Nhu cầu | Cơ chế phù hợp | Kết quả |
|---|---|---|
| Bỏ record không liên quan đến listener | Filter | Listener không được gọi cho record |
| Chuyển event theo eventType sang topic khác | Routing | Record được gửi đến destination phù hợp |
| Chọn handler theo kiểu payload trong cùng ứng dụng | Dispatch/handler selection | Một handler phù hợp được gọi |
| Ghi log, đo thời gian, bổ sung context trước listener | Interceptor | Record được quan sát hoặc biến đổi |
| Loại record do lỗi dữ liệu và cần điều tra | Reject/quarantine route | Record được lưu ở luồng xử lý lỗi |

Một record bị filter ở consumer group này vẫn tồn tại trong Kafka và các consumer group khác vẫn có thể đọc nó. Filtering không xóa record khỏi topic và không tác động đến subscription của service khác.

## 2. Vị trí của filter và router trong luồng Kafka

Filtering thường diễn ra ở phía consumer, sau khi Kafka consumer poll record và trước khi listener nghiệp vụ được gọi.

~~~mermaid
flowchart TD
    A["Kafka topic"] --> B["KafkaConsumer.poll()"]
    B --> C["Listener container"]
    C --> D["RecordInterceptor"]
    D --> E["Filtering adapter / RecordFilterStrategy"]
    E -->|Discard| F["Không gọi listener"]
    E -->|Keep| G["@KafkaListener"]
    G --> H["Nghiệp vụ"]
    H --> I{"Cần chuyển nhánh?"}
    I -->|Có| J["Router / KafkaTemplate"]
    I -->|Không| K["Hoàn tất"]
    J --> L["Destination topic"]
~~~

Với record listener, container gọi RecordInterceptor trước khi gọi listener adapter; adapter có thể là FilteringMessageListenerAdapter. Vì vậy interceptor nằm trước filter adapter trong đường gọi này. Dù vậy, hai cơ chế có trách nhiệm khác nhau: RecordFilterStrategy quyết định discard theo chính sách lọc, còn RecordInterceptor phục vụ hook cross-cutting. Không chuyển cùng một quy tắc domain sang interceptor chỉ để né cấu hình filter.

Routing có thể diễn ra sớm hơn, ngay ở producer:

~~~text
Producer
   |
   +-- OrderCreated  -> orders.created
   +-- OrderCancelled -> orders.cancelled
   +-- OrderArchived -> orders.archive
~~~

Hoặc routing diễn ra ở consumer sau khi đọc một topic chung:

~~~text
orders.events
      |
      v
Order router
      |
      +-- OrderCreated   -> orders.created
      +-- OrderCancelled -> orders.cancelled
      +-- OrderArchived  -> orders.archive
~~~

Chọn vị trí route dựa trên nơi có đủ thông tin để quyết định và nơi chịu trách nhiệm về topology topic. Nếu producer đã biết event type và destination, routing ở producer thường đơn giản hơn. Nếu destination phụ thuộc vào dữ liệu đã được enrich hoặc kiểm tra ở consumer, route sau khi consume có thể phù hợp hơn.

## 3. Khi nào nên dùng filter?

Dùng filter khi record không cần tạo ra bất kỳ side effect nào trong listener hiện tại và việc bỏ qua là một quyết định nghiệp vụ có chủ đích.

Các tình huống thường gặp:

- Listener chỉ xử lý một tập event type trong topic dùng chung.
- Record có cờ enabled=false và được xác định là không thuộc luồng xử lý này.
- Event đã hết hạn và chính sách nghiệp vụ cho phép bỏ qua.
- Record là heartbeat hoặc control event mà listener nghiệp vụ không quan tâm.
- Một listener chỉ nhận một nhóm tenant hoặc loại dữ liệu được phân công.
- Record là tombstone mà listener cụ thể không cần xử lý, sau khi đã xác định rõ semantics của compacted topic.
- Record trùng đã được xác nhận xử lý trong một kho idempotency bền vững và listener này không cần thực hiện side effect lần nữa.

Trước khi filter, hãy trả lời ba câu hỏi:

1. Có ai hoặc luồng nào khác cần xử lý record này không?
2. Có cần lưu lại lý do bỏ qua để audit hoặc điều tra không?
3. Nếu điều kiện filter thay đổi trong tương lai, record cũ có cần được replay không?

Nếu câu trả lời cho câu hỏi đầu là có, hoặc record cần được sửa rồi xử lý lại, hãy cân nhắc route sang topic khác thay vì discard.

Không dùng filter để che giấu lỗi schema, lỗi deserialize hoặc lỗi nghiệp vụ cần retry. Record không deserialize được có thể chưa đi đến RecordFilterStrategy; lỗi đó thuộc tầng deserialization và cần ErrorHandlingDeserializer hoặc cơ chế xử lý lỗi phù hợp.

## 4. Khi nào nên dùng routing?

Dùng routing khi record vẫn có giá trị và phải được chuyển đến một consumer hoặc destination khác.

Ví dụ:

- Event theo vùng địa lý cần đi đến topic riêng.
- Event theo loại nghiệp vụ cần được xử lý bởi service chuyên biệt.
- Event có priority cao cần đi đến luồng ưu tiên.
- Event đã được xác thực cần chuyển đến topic downstream.
- Event không hợp lệ cần được cách ly để điều tra.
- Một topic đầu vào chứa nhiều loại event và router cần phân nhánh.

Routing thường phải tạo ra một hành động có thể quan sát: publish record đến topic đích, chọn một handler hoặc chuyển vào một workflow. Vì vậy, route cần xác định destination, key, headers và chính sách khi destination không tồn tại.

Nếu không tìm thấy route, không nên âm thầm bỏ record. Hãy chọn rõ một trong các hành vi: ném exception để retry, gửi quarantine, ghi nhận rejected event hoặc dừng container tùy mức độ nghiêm trọng.

## 5. Cấu hình RecordFilterStrategy

Spring Kafka cung cấp RecordFilterStrategy để quyết định có loại một ConsumerRecord hay không. Phương thức filter() trả về true nghĩa là record bị loại; false nghĩa là record được chuyển tiếp đến listener.

Ví dụ factory chỉ nhận các order event đang active:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> inactiveOrderFilter() {
    return record -> {
        OrderEvent event = record.value();

        return event == null || !event.isActive();
    };
}
~~~

Gắn strategy vào ConcurrentKafkaListenerContainerFactory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                RecordFilterStrategy<String, OrderEvent> inactiveOrderFilter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordFilterStrategy(inactiveOrderFilter);

    return factory;
}
~~~

Listener dùng factory:

~~~java
@KafkaListener(
    id = "active-orders-listener",
    topics = "orders",
    groupId = "active-orders-service",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong ví dụ, event có active=false không được chuyển vào consume(). Event vẫn còn trong topic orders và các consumer group khác không bị ảnh hưởng.

Ví dụ cũng loại payload null. Chỉ làm vậy nếu tombstone không mang ý nghĩa nghiệp vụ đối với listener này; với compacted topic, tombstone thường biểu diễn việc xóa key và có thể cần được xử lý riêng.

Tên bean filter và factory nên thể hiện phạm vi nghiệp vụ. Nếu nhiều listener có tiêu chí khác nhau, tạo strategy/factory riêng để tránh một filter dùng chung vô tình loại record mà listener khác cần.

Từ Spring Kafka 2.8.4, có thể chọn filter riêng cho từng @KafkaListener bằng thuộc tính filter, ghi tên bean RecordFilterStrategy. Cách này hữu ích khi các endpoint dùng chung một factory nhưng có tiêu chí lọc khác nhau:

~~~java
@KafkaListener(
    id = "active-orders-listener",
    topics = "orders",
    groupId = "active-orders-service",
    filter = "inactiveOrderFilter"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

## 6. Đọc metadata khi filter

Filter nhận ConsumerRecord nên có thể kiểm tra payload, key, topic, partition, offset, timestamp và headers.

Ví dụ loại event heartbeat theo header:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> heartbeatFilter() {
    return record -> {
        Header header = record.headers().lastHeader("event-kind");

        if (header == null) {
            return false;
        }

        String eventKind = new String(
                header.value(),
                StandardCharsets.UTF_8
        );

        return "heartbeat".equals(eventKind);
    };
}
~~~

Filter chỉ loại heartbeat. Record thiếu header vẫn được chuyển đến listener để listener hoặc validator quyết định xử lý. Nếu thiếu header là lỗi hợp đồng dữ liệu, nên route sang quarantine hoặc ném exception thay vì tự động discard.

Không đọc header bằng cách giả định luôn tồn tại. Kafka header có thể thiếu, lặp tên hoặc chứa byte không hợp lệ. Nếu cùng tên có nhiều header, chọn lastHeader() hay duyệt toàn bộ phải theo hợp đồng producer.

Có thể dùng topic hoặc key trong filter:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> topicScopeFilter() {
    return record ->
            !"orders".equals(record.topic())
                    || record.key() == null
                    || record.key().trim().isEmpty();
}
~~~

Ví dụ này loại record ngoài topic orders hoặc thiếu key. Chỉ áp dụng nếu key là bắt buộc trong hợp đồng topic. Nếu key null có ý nghĩa hợp lệ, filter này sẽ làm mất record.

## 7. Xử lý record bị discard và offset

Filter loại record khỏi listener invocation. Consumer vẫn đã poll record đó, nên ứng dụng cần hiểu cách offset được xác nhận theo AckMode và cấu hình container.

Spring Kafka cung cấp ackDiscarded trên listener container factory. Giá trị mặc định là false. Khi bật true, filtering adapter acknowledge record bị discard; thời điểm commit thực tế vẫn tuân theo AckMode, transaction và cơ chế commit của container:

~~~java
factory.setAckDiscarded(true);
~~~

AckMode, auto commit và transaction ảnh hưởng thời điểm offset được commit. Không nên bật ackDiscarded mà không hiểu tác động của nó đối với retry và redelivery. Nếu để false, adapter không chủ động acknowledge record bị discard; hãy kiểm thử hành vi offset theo AckMode đang dùng, đặc biệt sau restart hoặc rebalance.

Nguyên tắc vận hành:

- Xác định rõ AckMode của listener.
- Kiểm tra ackDiscarded theo phiên bản Spring Kafka.
- Kiểm thử restart/rebalance sau khi filter loại record.
- Không coi discard là một lần xử lý nghiệp vụ thành công nếu record cần được audit.
- Nếu cần lưu lý do reject, hãy route hoặc ghi nhận bền vững trước khi xác nhận offset.

Filtering không gọi listener nên logic trong listener như metrics nghiệp vụ, audit hoặc outbox sẽ không chạy. Nếu cần ghi nhận record bị bỏ qua, hãy dùng metrics/filter observability phù hợp hoặc chọn reject route.

## 8. Filter cho batch listener

Khi container chạy batch mode, listener nhận nhiều record trong một lần gọi. RecordFilterStrategy hỗ trợ filterBatch() để quyết định tập record nào còn lại sau khi lọc.

Ví dụ chỉ giữ các event active:

~~~java
@Bean
public RecordFilterStrategy<String, OrderEvent> activeOrderBatchFilter() {
    return new RecordFilterStrategy<>() {

        @Override
        public boolean filter(
                ConsumerRecord<String, OrderEvent> record) {
            return record.value() == null || !record.value().isActive();
        }

        @Override
        public List<ConsumerRecord<String, OrderEvent>> filterBatch(
                List<ConsumerRecord<String, OrderEvent>> records) {

            return records.stream()
                    .filter(record -> !filter(record))
                    .collect(Collectors.toList());
        }
    };
}
~~~

Gắn strategy vào factory batch:

~~~java
factory.setBatchListener(true);
factory.setRecordFilterStrategy(activeOrderBatchFilter);
~~~

Listener nhận danh sách đã lọc:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "active-orders-batch",
    containerFactory = "ordersBatchListenerFactory"
)
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Filter batch nên giữ nguyên thứ tự tương đối của các record còn lại. Nếu nghiệp vụ cần metadata từng record, dùng List<ConsumerRecord<K,V>> hoặc batch headers phù hợp thay vì chỉ nhận List payload. FilteringBatchMessageListenerAdapter không áp dụng cho listener nhận ConsumerRecords<?, ?> vì kiểu này immutable; muốn filter batch, hãy dùng List<ConsumerRecord<K,V>> hoặc List payload.

Từ Spring Kafka 3.3, RecordFilterStrategy có ignoreEmptyBatch(). Mặc định false nghĩa là listener vẫn được gọi với batch rỗng nếu tất cả record bị filter. Nếu trả true, listener không được gọi khi batch rỗng, nhưng container vẫn thực hiện commit theo cơ chế của nó. Với phiên bản cũ hơn 3.3, không có tùy chọn này; hãy kiểm tra hành vi tương ứng của version đang chạy.

## 9. Filter và RecordInterceptor khác nhau thế nào?

Từ Spring Kafka 2.2.7, RecordInterceptor là hook chạy trước khi record được chuyển đến record listener. Nó phù hợp với logic cross-cutting như logging, tracing, đo thời gian, kiểm tra context hoặc biến đổi record theo quy tắc chung.

Ví dụ interceptor gắn log context dựa trên topic và key:

~~~java
@Bean
public RecordInterceptor<String, OrderEvent> orderRecordInterceptor() {
    return (record, consumer) -> {
        log.debug(
                "Before listener: topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key()
        );

        return record;
    };
}
~~~

Gắn vào factory:

~~~java
factory.setRecordInterceptor(orderRecordInterceptor);
~~~

RecordInterceptor có thể trả về một ConsumerRecord đã biến đổi hoặc trả null để bỏ qua listener. Việc trả null không đi qua cơ chế ackDiscarded của RecordFilterStrategy; offset behavior cần được kiểm thử kỹ và có thể gây lag nếu record bị skip mà không được xác nhận theo cách mong muốn. Vì vậy, nếu mục tiêu là lọc theo điều kiện nghiệp vụ, RecordFilterStrategy diễn đạt ý định rõ ràng hơn và có cơ chế ackDiscarded riêng.

Nếu interceptor tạo ConsumerRecord mới, giữ nguyên topic, partition và offset của record gốc để tránh thay đổi vị trí mà container đang quản lý. Không gọi seek(), commitSync() hoặc các thao tác thay đổi consumer position/offset từ interceptor; container phải là thành phần quản lý tiến độ.

Không dùng interceptor để thực hiện nghiệp vụ nặng, gọi HTTP đồng bộ hoặc ghi database cho từng record. Interceptor chạy trên đường xử lý consumer và có thể làm tăng poll processing time, ảnh hưởng max.poll.interval.ms và consumer lag.

### BatchInterceptor

RecordInterceptor chỉ áp dụng cho record listener. Từ Spring Kafka 2.7, Spring Kafka có BatchInterceptor để quan sát hoặc biến đổi cả batch trước khi listener chạy. Không dùng RecordInterceptor cho một batch nếu chữ ký và container mode không tương thích.

Nếu chỉ cần bỏ một số record khỏi batch, dùng batch filtering. Nếu cần tracing hoặc context chung cho batch, cân nhắc BatchInterceptor.

## 10. ConsumerInterceptor ở Kafka client và Spring RecordInterceptor

Hai loại interceptor có tên gần giống nhau nhưng nằm ở hai tầng khác nhau:

| Loại | API | Vị trí | Phạm vi |
|---|---|---|---|
| Kafka ConsumerInterceptor | org.apache.kafka.clients.consumer.ConsumerInterceptor | Bên trong KafkaConsumer, quanh poll | Cấp Kafka client |
| Spring RecordInterceptor | org.springframework.kafka.listener.RecordInterceptor | Trước listener invocation | Cấp listener container |
| Spring BatchInterceptor | org.springframework.kafka.listener.BatchInterceptor | Trước batch listener | Cấp batch listener container |

Kafka ConsumerInterceptor được cấu hình qua consumer property interceptor.classes. Nó tác động ở tầng Kafka client và có thể ảnh hưởng đến mọi listener dùng consumer factory đó. Interceptor có thể quan sát hoặc thay đổi tập ConsumerRecords trả về từ poll, nhưng thay đổi tập record ở tầng client có hệ quả riêng với tiến độ offset; không dùng nó như cách lọc domain đơn giản. Nếu chỉ muốn lọc cho một endpoint Spring cụ thể, RecordFilterStrategy thường rõ ràng và dễ quản lý hơn.

Spring RecordInterceptor gắn vào container factory, nên có thể cấu hình khác nhau theo listener. Hãy chọn API ở đúng tầng thay vì tạo một ConsumerInterceptor toàn cục để thực hiện quy tắc nghiệp vụ của riêng một listener.

## 11. Routing ở producer

Nếu producer biết loại event và destination ngay lúc tạo event, hãy route ở producer. Cách này giúp consumer chỉ subscribe topic mà nó thực sự cần xử lý.

Ví dụ:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public void publish(OrderEvent event) throws Exception {
        String destination;
        switch (event.getType()) {
            case CREATED:
                destination = "orders.created";
                break;
            case CANCELLED:
                destination = "orders.cancelled";
                break;
            case ARCHIVED:
                destination = "orders.archive";
                break;
            default:
                throw new IllegalArgumentException(
                        "Unsupported order event type: " + event.getType()
                );
        }

        kafkaTemplate.send(
                destination,
                event.getOrderId(),
                event
        ).get(10, TimeUnit.SECONDS);
    }
}
~~~

Producer chọn topic trước khi publish. Key là orderId để các event của cùng một đơn hàng có thể đi cùng partition trong từng topic, tùy partitioner và số partition.

Producer cũng cần quan sát kết quả send future và xử lý lỗi publish theo hợp đồng của ứng dụng. Việc chọn đúng topic không đồng nghĩa record đã được broker xác nhận ghi thành công.

Routing ở producer phù hợp khi:

- Event type đã biết tại nguồn.
- Producer sở hữu hợp đồng destination.
- Muốn giảm số consumer phải đọc topic chung.
- Muốn mỗi downstream service có topic và ACL riêng.

Nếu nhiều producer phải lặp lại cùng một quy tắc route, hãy đưa quy tắc vào một component dùng chung hoặc chuẩn hóa contract topic. Không để mỗi producer tự đặt tên topic theo cách khác nhau.

## 12. Routing trong consumer bằng KafkaTemplate

Đôi khi producer không thể quyết định destination vì route phụ thuộc dữ liệu được enrich hoặc xác thực ở consumer. Khi đó, listener có thể gọi router và publish sang topic đích.

Ví dụ:

~~~java
@Component
public class OrderEventRouter {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public void route(OrderEvent event) throws Exception {
        String destination;
        switch (event.getRegion()) {
            case "VN":
                destination = "orders.vn";
                break;
            case "SG":
                destination = "orders.sg";
                break;
            case "TH":
                destination = "orders.th";
                break;
            default:
                throw new UnsupportedOrderRegionException(event.getRegion());
        }

        kafkaTemplate.send(
                destination,
                event.getOrderId(),
                event
        ).get(10, TimeUnit.SECONDS);
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "orders-router"
)
public void consume(OrderEvent event) throws Exception {
    orderEventRouter.route(event);
}
~~~

Trong ví dụ, route không được thực hiện bằng cách discard record. Router đợi kết quả send tối đa 10 giây; nếu publish thất bại hoặc hết thời gian chờ, exception được truyền về listener để error handler xử lý theo retry/DLT policy. Việc chờ đồng bộ giữ consumer thread trong thời gian gửi; hãy chọn timeout phù hợp và cân nhắc Kafka transaction nếu cần phối hợp publish với source offset.

Nếu publish destination thất bại, listener không nên trả về thành công rồi commit source offset. Hãy xử lý send future và chỉ xác nhận source record khi publish đã được xác nhận theo chính sách reliability.

## 13. Đảm bảo consume-and-route đáng tin cậy

Khi consumer đọc source rồi publish sang topic khác, có hai thao tác độc lập:

1. Đọc và xác nhận offset source.
2. Publish record đến destination.

Nếu publish thành công nhưng commit source offset thất bại, record có thể được đọc lại và publish lần nữa. Nếu commit source offset trước khi publish thành công, record có thể bị mất khỏi luồng đích.

Các lựa chọn:

- Dùng Kafka transaction để kết hợp publish output và commit offset input trong một transaction Kafka khi cấu hình listener container và KafkaTemplate dùng transaction manager phù hợp.
- Dùng idempotency ở consumer đích để chịu duplicate.
- Dùng outbox nếu quyết định route phụ thuộc thay đổi database và cần phối hợp database với Kafka.
- Ghi trạng thái route bền vững để có thể phục hồi sau lỗi.

Với transactional listener container, Spring Kafka có thể bắt đầu Kafka transaction cho mỗi record hoặc batch; KafkaTemplate dùng cùng transactional ProducerFactory gửi output trong transaction đó. Khi listener hoàn tất, offset input được gửi vào transaction. Nếu transaction abort, output không được commit và offset cũng không được xác nhận trong transaction đó.

Kafka transaction không tự bao gồm database transaction thông thường. Nếu listener vừa ghi database vừa publish Kafka, cần outbox hoặc một cơ chế phối hợp phù hợp để tránh trạng thái lệch giữa hai hệ thống.

## 14. Chọn key và giữ ordering khi route

Routing sang topic khác có thể thay đổi partition mapping. Kafka chỉ bảo đảm thứ tự trong một partition của một topic, không bảo đảm thứ tự toàn cục giữa các topic.

Nếu orderId là key của source record, khi route hãy giữ key đó nếu muốn event cùng order tiếp tục có cơ hội vào cùng partition ở destination:

~~~java
        kafkaTemplate.send(
                destination,
                record.key(),
                routedEvent
        );
~~~

Tuy nhiên, giữ cùng key không bảo đảm partition number giống source nếu số partition hoặc partitioner khác nhau. Nếu nghiệp vụ cần thứ tự nghiêm ngặt, hãy xác định rõ:

- Tất cả event của aggregate có cùng key.
- Destination topic có partitioning tương thích.
- Router không publish bất đồng bộ theo thứ tự hoàn tất khác nhau.
- Consumer đích xử lý tuần tự theo partition.
- Có version/sequence guard nếu event có thể đến trễ.

Không route event của cùng aggregate sang nhiều topic rồi giả định consumer sẽ thấy một thứ tự duy nhất giữa các topic.

## 15. Route theo topic hay dispatch theo payload?

Một topic có thể chứa nhiều event type. Có hai cách tổ chức phổ biến:

**Một topic cho nhiều event type:** consumer đọc topic chung rồi dispatch theo eventType hoặc payload type. Cách này giảm số topic nhưng listener phải hiểu nhiều loại event và quản lý schema chung.

**Topic riêng theo event type:** producer route event vào topic phù hợp. Consumer subscribe đúng topic, đơn giản hóa quyền truy cập và ownership nhưng tăng số topic và cấu hình.

Có thể dùng nhiều method trong một class listener với @KafkaHandler để Spring Kafka dispatch theo kiểu payload khi một class có @KafkaListener ở cấp class:

~~~java
@Component
@KafkaListener(
    id = "order-events",
    topics = "orders.events",
    groupId = "order-event-handlers"
)
public class OrderEventHandlers {

    @KafkaHandler
    public void onCreated(OrderCreated event) {
        orderService.create(event);
    }

    @KafkaHandler
    public void onCancelled(OrderCancelled event) {
        orderService.cancel(event);
    }

    @KafkaHandler(isDefault = true)
    public void onUnknown(Object event) {
        log.warn("Unsupported event type: {}", event.getClass().getName());
    }
}
~~~

Đây là dispatch đến method trong cùng listener endpoint, không phải publish sang topic khác. Nếu cần route đến destination topic, hãy dùng router/KafkaTemplate hoặc quyết định topic ngay ở producer.

Với JSON, việc dispatch theo type cần cấu hình type mapping/deserializer phù hợp. Không để class name tùy ý từ header điều khiển type resolution nếu nguồn message không đáng tin cậy.

## 16. Route không xác định và rejected event

Một router phải định nghĩa hành vi khi không tìm thấy destination. Có ba chính sách thường gặp:

| Chính sách | Khi phù hợp | Hệ quả |
|---|---|---|
| Ném exception | Route thiếu là lỗi cấu hình hoặc dữ liệu có thể sửa | Retry rồi DLT theo error handler |
| Quarantine/rejected topic | Event cần điều tra hoặc sửa sau | Record được giữ để vận hành |
| Discard | Event được xác định rõ là không cần xử lý | Không có luồng downstream |

Không dùng default route tùy tiện như "mọi route lạ đều gửi vào orders.created". Điều đó có thể khiến event sai loại đi vào nghiệp vụ không phù hợp.

Destination nên được kiểm tra bằng allowlist:

~~~java
private static final Map<String, String> DESTINATIONS = createDestinations();

private static Map<String, String> createDestinations() {
    Map<String, String> destinations = new HashMap<>();
    destinations.put("VN", "orders.vn");
    destinations.put("SG", "orders.sg");
    destinations.put("TH", "orders.th");
    return Collections.unmodifiableMap(destinations);
}

private String destinationFor(String region) {
    String destination = DESTINATIONS.get(region);

    if (destination == null) {
        throw new UnsupportedOrderRegionException(region);
    }

    return destination;
}
~~~

Allowlist giúp giới hạn topic mà router có thể publish. Không ghép tên topic trực tiếp từ dữ liệu user hoặc header không được xác thực.

## 17. Không dùng filter làm idempotency

Một filter có thể kiểm tra eventId đã tồn tại trong database hay chưa rồi discard duplicate. Tuy nhiên, đây thường không phải nơi phù hợp để bảo đảm idempotency.

Nếu filter đánh dấu event đã xử lý trước khi listener thực hiện nghiệp vụ, lỗi giữa hai bước có thể làm record bị discard ở lần giao lại dù side effect chưa hoàn tất. Nếu filter chỉ kiểm tra rồi listener xử lý, hai consumer có thể cùng vượt qua kiểm tra khi chạy đồng thời.

Idempotency nên được thực hiện tại ranh giới nghiệp vụ bằng transaction và unique constraint/inbox:

~~~java
@Transactional
public void process(OrderEvent event) {
    if (inboxRepository.existsByEventId(event.getEventId())) {
        return;
    }

    orderService.apply(event);
    inboxRepository.save(new InboxEntry(event.getEventId()));
}
~~~

Trong production, cần unique constraint trên eventId và xử lý conflict khi hai lần giao cùng event chạy đồng thời. Kiểm tra và ghi inbox cùng transaction với side effect database.

Filter có thể loại các record chắc chắn không thuộc phạm vi listener, còn idempotency bảo vệ việc thực thi nghiệp vụ khỏi duplicate delivery.

## 18. Không dùng filter thay cho bảo mật

Filtering không phải cơ chế authorization. Record bị filter chỉ không được listener hiện tại xử lý; nó vẫn nằm trong Kafka và có thể được consumer group khác đọc.

Nếu một service không được phép đọc topic, hãy dùng Kafka ACL và identity phù hợp. Nếu tenant không được phép truy cập dữ liệu, kiểm tra authorization tại service và bảo vệ dữ liệu trước khi publish.

Không dựa vào filter theo tenant để bảo vệ dữ liệu nhạy cảm nếu service vẫn có quyền đọc toàn bộ topic. Filter có thể sai, bị cấu hình nhầm hoặc không chạy ở listener khác.

## 19. Retry và DLT có áp dụng cho record bị filter không?

Record bị filter không làm listener ném exception. Vì vậy, nó không tự động đi qua retry/DLT như một lỗi xử lý listener thông thường.

Nếu record bị discard do điều kiện nghiệp vụ nhưng cần điều tra, hãy route sang rejected/quarantine topic thay vì filter. Nếu filter bỏ qua record do một điều kiện tạm thời, ví dụ dữ liệu tham chiếu chưa sẵn sàng, filter có thể làm mất cơ hội retry. Khi cần retry, hãy để listener xử lý và ném exception phù hợp hoặc dùng retry topic.

Phân biệt:

- Filter: record không cần listener xử lý.
- Exception: listener đã cố xử lý nhưng thất bại.
- Reject route: record bị từ chối nhưng vẫn cần lưu.
- Retry: record cần được thử lại sau một khoảng thời gian.

Không dùng filter để né một lỗi deserialization hoặc lỗi validation. Các lỗi này cần error handling ở tầng tương ứng.

## 20. Quan sát filter và routing trong production

Filtering có thể làm số record listener nhận thấp hơn số record consumer poll. Cần quan sát số record bị loại để phát hiện filter quá rộng hoặc thay đổi dữ liệu đầu vào.

Các metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| records_polled_total | Số record consumer poll |
| records_filtered_total | Số record bị filter |
| records_listener_invoked_total | Số record được chuyển vào listener |
| records_routed_total | Số record được publish sang destination |
| route_unknown_total | Số record không tìm được route |
| route_publish_failure_total | Số lần publish destination thất bại |
| rejected_records_total | Số record được đưa vào reject/quarantine |
| filter_rate_by_reason | Tỷ lệ filter theo lý do |
| listener_processing_latency | Thời gian xử lý listener |

Gắn các trường sau vào log:

- eventId.
- topic, partition, offset.
- key.
- filter reason hoặc route decision.
- destination topic.
- correlation/trace ID.
- exception type nếu route/publish thất bại.

Không log toàn bộ payload nhạy cảm. Nên ghi mã lý do ổn định như OUT_OF_SCOPE, EXPIRED hoặc INTERNAL_EVENT để dashboard và alert không phụ thuộc vào nội dung message.

Nếu filter rate tăng đột biến, kiểm tra producer version, schema, header mapping và điều kiện filter. Nếu route failure tăng, kiểm tra topic metadata, ACL, serializer, broker và producer send result.

## 21. Kiểm thử filter và routing

Kiểm thử cần xác nhận cả record được giữ, record bị loại và record được route.

Các kịch bản quan trọng:

1. Filter trả false: listener được gọi.
2. Filter trả true: listener không được gọi.
3. Record thiếu header tùy chọn: hành vi đúng với chính sách đã định nghĩa.
4. Tombstone/null payload: không bị loại nhầm nếu compacted topic cần xử lý tombstone.
5. Filter theo key: key null hoặc blank có hành vi rõ ràng.
6. Batch filter: chỉ record đạt điều kiện còn trong batch.
7. Batch rỗng sau filter: xác nhận hành vi listener theo phiên bản Spring Kafka.
8. ackDiscarded và AckMode: offset được xác nhận đúng sau restart/rebalance.
9. RecordInterceptor: record được quan sát/biến đổi đúng và null skip được hiểu rõ.
10. Producer routing: event type tạo đúng destination.
11. Consumer router: route theo region/event type đúng topic.
12. Route không xác định: ném exception hoặc vào quarantine theo chính sách.
13. Publish destination thất bại: source offset không được xác nhận sớm.
14. Duplicate delivery: idempotency bảo vệ side effect.
15. Ordering: cùng key được xử lý theo quy tắc partition đã thiết kế.
16. Security: consumer không có ACL không thể đọc topic dù filter có thể loại record.
17. Metrics: filter count, route count và reject count phản ánh đúng số record.

Dùng EmbeddedKafka hoặc Testcontainers để kiểm thử integration. Dùng latch/Awaitility để đợi listener và assert theo eventId; không dùng sleep cố định để kết luận listener đã bỏ qua hoặc đã route record.

## 22. Các lỗi thiết kế thường gặp

**Dùng filter để chuyển record sang topic khác.** Filter chỉ discard record khỏi listener hiện tại. Dùng router và KafkaTemplate để publish destination.

**Discard record cần audit.** Record bị loại không tự động đi vào DLT. Route sang rejected/quarantine topic hoặc ghi nhận bền vững.

**Dùng topicPattern quá rộng.** Listener có thể nhận cả retry, DLT hoặc topic nội bộ. Dùng topics tường minh hoặc regex có kiểm thử.

**Filter gọi HTTP/database cho từng record.** Consumer thread bị chặn, tăng lag và nguy cơ vượt max.poll.interval.ms. Dùng predicate nhẹ, deterministic và local.

**Filter để thay idempotency.** Kiểm tra trước khi xử lý có race condition. Dùng inbox/unique constraint trong transaction nghiệp vụ.

**Không kiểm tra ackDiscarded.** Offset của record bị loại có thể không được xác nhận theo mong đợi tùy AckMode và container config. Kiểm thử commit sau restart/rebalance.

**Bỏ tombstone trên compacted topic.** Tombstone có thể biểu diễn xóa key. Chỉ filter nếu listener thực sự không cần semantics này.

**Route mà không giữ key.** Event cùng aggregate có thể đi sang partition khác và mất ordering mong muốn. Giữ key và thiết kế partitioning tương thích.

**Publish destination rồi commit source quá sớm.** Lỗi giữa hai thao tác có thể làm mất hoặc duplicate record. Dùng Kafka transaction hoặc idempotent downstream.

**Dùng interceptor cho nghiệp vụ domain.** Cross-cutting hook trở thành nơi chứa logic khó kiểm thử. Đưa business decision vào router/service rõ ràng.

**Không định nghĩa route mặc định.** Event type lạ bị gửi nhầm vào topic không phù hợp. Dùng allowlist và hành vi unknown route tường minh.

## 23. Checklist chọn filter hay routing

- [ ] Đã xác định record cần bỏ qua hay cần được chuyển sang nhánh khác.
- [ ] Filter chỉ loại record không cần listener hiện tại xử lý.
- [ ] Record cần audit/replay được route sang rejected/quarantine.
- [ ] RecordFilterStrategy trả true khi muốn discard.
- [ ] Filter không gọi dependency từ xa hoặc thực hiện side effect nặng.
- [ ] Đã xác định semantics của tombstone và null payload.
- [ ] Đã cấu hình ackDiscarded phù hợp AckMode.
- [ ] Batch filter giữ đúng thứ tự record còn lại.
- [ ] RecordInterceptor chỉ dùng cho cross-cutting logic.
- [ ] Routing có allowlist destination và unknown-route policy.
- [ ] Producer-side routing được ưu tiên khi destination đã biết tại nguồn.
- [ ] Consumer-side routing có xử lý send result và offset an toàn.
- [ ] Key được giữ khi ordering theo aggregate là yêu cầu.
- [ ] Consume-and-route dùng transaction hoặc idempotency phù hợp.
- [ ] Filter không được dùng thay authorization hoặc idempotency.
- [ ] Có metrics cho filtered, routed, rejected và route failures.
- [ ] Integration test bao gồm discard, route, retry, offset và ordering.

## Kết luận

Chọn filter khi record thực sự không cần listener hiện tại xử lý; chọn routing khi record vẫn có giá trị và phải được chuyển đến một nhánh hoặc topic khác. Trong Spring Kafka, RecordFilterStrategy là lựa chọn rõ ràng cho filtering, RecordInterceptor dành cho hook cross-cutting trước listener, còn routing nên nằm ở producer hoặc một router/service có destination allowlist. Hãy làm rõ hành vi offset của record bị discard, không dùng filter thay cho retry, DLT, idempotency hay authorization, và bảo đảm consume-and-route không commit source trước khi publish destination an toàn.

## Tài liệu tham khảo

- [Spring Kafka – Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
- [Spring Kafka – Message Listener Containers and Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)

