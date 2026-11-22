# Delivery attempts header trong Spring Kafka

Khi một Kafka listener xử lý record thất bại, Spring Kafka có thể giao lại chính record đó theo chính sách retry của listener container. Trong vận hành, câu hỏi rất thường gặp là: “Record này đang được xử lý lần đầu hay đã thất bại nhiều lần?”. **Delivery attempts header** giúp trả lời câu hỏi ấy bằng cách gắn số lần giao record vào header mà listener có thể đọc được.

Trong Spring Kafka, tên header dùng cho cơ chế này là `KafkaHeaders.DELIVERY_ATTEMPT`. Số lần giao được đếm từ **1** cho lần xử lý đầu tiên và tăng khi record được giao lại theo cơ chế hỗ trợ của container/error handler. Header phục vụ chẩn đoán retry, logging và observability. Nó không phải dấu xác nhận offset đã commit, không phải số lần gửi của producer và không bảo đảm toàn bộ lịch sử retry sẽ được giữ vĩnh viễn qua restart.

Bài học này trình bày cách bật header, đọc giá trị trong listener, hiểu chính xác phạm vi đếm, phối hợp với `DefaultErrorHandler` và retry topics, sau đó ứng dụng vào giám sát và xử lý sự cố.

## 1. Phân biệt delivery attempt với các loại attempt khác

Một sự kiện có thể được thử lại ở nhiều lớp. Nếu trộn các bộ đếm, dashboard và runbook sẽ đưa ra kết luận sai.

| Khái niệm | Đối tượng được đếm | Ví dụ |
|---|---|---|
| Producer retry | Producer client thử gửi lại request đến broker | Request bị timeout rồi gửi lại |
| Record delivery attempt | Listener container giao một record cho listener để xử lý | Listener nhận offset 42 lần 1, 2, 3 |
| Retry-topic attempt | Một event được chuyển qua các retry topic theo chính sách non-blocking | Event đi từ topic chính sang retry topic |
| HTTP client retry | Client thử gọi lại downstream API | Một lần xử lý Kafka gọi HTTP ba lần |
| Business retry | Workflow nghiệp vụ được thực hiện lại ở mức application | Yêu cầu thanh toán được phát lại sau đối soát |

Ví dụ, listener nhận record ở delivery attempt 2, nhưng trong mỗi lần xử lý service HTTP có thể thử gọi API ba lần. Tổng số HTTP request có thể lên đến sáu, trong khi Kafka delivery attempt vẫn chỉ là 2.

Delivery attempts header cho biết **lần giao trong ngữ cảnh container và cơ chế retry đang dùng**. Không dùng nó làm bộ đếm toàn cục xuyên suốt producer, DLT, replay và mọi instance.

## 2. Delivery attempts header hoạt động như thế nào?

Khi container được cấu hình để đưa thông tin delivery attempt vào record và error handler hỗ trợ theo dõi lần giao, Spring Kafka thêm header tương ứng trước khi record được cung cấp cho listener.

Đối với một record lỗi tạm thời, luồng xử lý có thể là:

~~~text
Kafka poll nhận record ở offset 42
                 |
                 v
       Listener, attempt = 1
                 |
          Xảy ra exception
                 |
                 v
        DefaultErrorHandler
           chờ backoff
                 |
                 v
       Listener, attempt = 2
                 |
          Xảy ra exception
                 |
                 v
           Chờ backoff
                 |
                 v
       Listener, attempt = 3
                 |
         Xử lý thành công
                 |
                 v
     Container xác nhận offset
~~~

Header được thêm để listener nhận biết trạng thái giao lại. Đường đi retry cụ thể phụ thuộc error handler, các thiết lập seek/retain, transaction và phiên bản Spring Kafka.

### 2.1. Lần đầu là 1, không phải 0

Giả sử cấu hình cho phép hai lần retry sau lần xử lý ban đầu:

| Lần gọi listener | Giá trị attempt | Kết quả giả định |
|---:|---:|---|
| 1 | 1 | Timeout |
| 2 | 2 | Timeout |
| 3 | 3 | Thành công hoặc hết retry |

Vì vậy, **delivery attempt = 3 không có nghĩa đã retry ba lần**. Nó thường tương ứng lần giao thứ ba, tức hai lần xử lý trước đã thất bại trong chuỗi retry đó.

Nếu record thất bại ngay với loại exception được phân loại non-retryable, recoverer có thể được gọi sau attempt 1. Không nên suy ra một record vào DLT bắt buộc phải có attempt lớn.

### 2.2. Header không thay đổi nội dung nghiệp vụ

Kafka record gồm key, value, timestamp, offset, partition và headers. Delivery attempts header nằm trong phần metadata của record được listener nhìn thấy; nó không sửa payload nghiệp vụ.

Listener có thể dùng header để ghi log hoặc xác định mức độ nghiêm trọng khi một lỗi kéo dài. Tuy nhiên, việc quyết định retry hay recovery cuối cùng vẫn thuộc chính sách của error handler hoặc retry-topic infrastructure. Không tự ý đặt lại offset hoặc commit chỉ vì thấy số attempt lớn.

## 3. Điều kiện cần để bật delivery attempts header

Trong các phiên bản Spring Kafka hỗ trợ tính năng, container có thuộc tính `deliveryAttemptHeader`. Có thể bật bằng phương thức `ContainerProperties.setDeliveryAttemptHeader(true)`.

Error handler cũng cần có khả năng cung cấp số lần giao, thường thông qua hợp đồng `DeliveryAttemptAware`. Các handler phổ biến như `DefaultErrorHandler` hỗ trợ cơ chế này. Với luồng transaction, `DefaultAfterRollbackProcessor` trong những phiên bản phù hợp cũng có khả năng theo dõi delivery attempt.

Các điều kiện thực tế:

1. Listener được tạo từ container có bật delivery attempt header.
2. Error handler hoặc after-rollback processor đang dùng có hỗ trợ delivery attempt.
3. Listener nhận record qua cơ chế container mà Spring Kafka quản lý.
4. Code đọc đúng header và xử lý trường hợp header không hiện diện.

Nếu chỉ tạo Kafka consumer client thuần rồi tự gọi `poll()`, không có lý do để mong Spring Kafka tự gắn header này. Đây là tính năng ở tầng listener container.

### 3.1. Cấu hình trên listener container factory

Một ví dụ cấu hình Java cho record listener:

~~~java
@Configuration
public class OrderListenerConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.getContainerProperties()
                .setDeliveryAttemptHeader(true);
        return factory;
    }

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }
}
~~~

Đoạn code minh họa cách kết nối listener factory với error handler. Trong ứng dụng thực tế, các import, serializer, generic type và DLT topic cần được cấu hình đồng bộ. Cần kiểm tra API tương ứng với phiên bản Spring Kafka của dự án.

Ở đây, `FixedBackOff(1_000L, 2L)` cho phép hai lần retry với khoảng chờ một giây sau lần xử lý ban đầu. Nếu listener tiếp tục thất bại, recoverer sẽ được gọi theo chính sách xử lý lỗi.

### 3.2. Chỉ bật trên đúng factory

Một ứng dụng có thể có nhiều listener factory. Ví dụ, listener của đơn hàng dùng `ordersListenerFactory`, nhưng listener audit dùng một factory khác. Bật `deliveryAttemptHeader` cho factory đơn hàng không có nghĩa tất cả listener đều có header.

~~~java
@KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(OrderEvent event) {
    // Logic xử lý đơn hàng.
}
~~~

Nếu listener không dùng factory mong đợi, cấu hình header có thể không được áp dụng. Khi điều tra header bị thiếu, hãy xác định chính xác container factory mà annotation sử dụng.

### 3.3. Cấu hình khi tạo container trực tiếp

Với container tạo bằng Java thay vì `@KafkaListener`:

~~~java
ContainerProperties properties =
        new ContainerProperties("orders.events");
properties.setGroupId("billing");
properties.setDeliveryAttemptHeader(true);

var container = new KafkaMessageListenerContainer<>(
        consumerFactory, properties);
~~~

Ví dụ này chỉ thể hiện vị trí đặt thuộc tính. Để có listener hoạt động, ứng dụng vẫn phải gắn message listener và các thành phần cần thiết trước khi start container.

## 4. Đọc header bằng @Header trong listener

Đối với listener dùng annotation, có thể yêu cầu Spring Kafka chuyển giá trị header vào một tham số Java:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        OrderEvent event,
        @Header(
                name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false)
        Integer attempt) {

    int currentAttempt = attempt == null ? 1 : attempt;

    log.info(
            "Processing order event, attempt={}",
            currentAttempt);

    orderService.processIdempotently(event);
}
~~~

Ở các phiên bản hỗ trợ argument conversion của Spring Kafka, `@Header(KafkaHeaders.DELIVERY_ATTEMPT) int` có thể nhận giá trị số nguyên đã được chuyển đổi từ header. Sử dụng `required = false` với `Integer` giúp listener tương thích với môi trường chưa bật header hoặc các loại record không có header này.

Trong ví dụ, giá trị mặc định 1 là **quy ước dự phòng của ứng dụng** khi header không tồn tại. Nó không chứng minh record thật sự được giao lần đầu. Nếu cần độ chính xác để chẩn đoán, nên ghi trạng thái “không có header” thay vì ép mọi trường hợp thành attempt 1:

~~~java
String attemptLabel =
        attempt == null ? "unknown" : attempt.toString();
~~~

Không nên khiến listener thất bại chỉ vì thiếu header giám sát. Nếu header là dữ liệu bắt buộc theo một hợp đồng nội bộ, hãy kiểm soát rõ phiên bản và cách cấu hình trước khi chuyển thành tham số required.

## 5. Đọc header từ ConsumerRecord

Khi listener nhận `ConsumerRecord`, có thể truy cập Kafka headers trực tiếp. Giá trị delivery attempt của cơ chế này được biểu diễn dưới dạng một số nguyên 4 byte.

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record) {

    Header header = record.headers()
            .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

    Integer attempt = null;
    if (header != null
            && header.value() != null
            && header.value().length == Integer.BYTES) {
        attempt = ByteBuffer.wrap(header.value()).getInt();
    }

    log.info(
            "Received topic={}, partition={}, offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attempt == null ? "unknown" : attempt);

    orderService.processIdempotently(record.value());
}
~~~

`ByteBuffer` mặc định sử dụng big-endian, phù hợp với cách biểu diễn số nguyên 4 byte trong header này. Ví dụ nên dùng đúng `KafkaHeaders.DELIVERY_ATTEMPT` thay vì tự gõ chuỗi tên header để tránh nhầm tên.

### 5.1. Vì sao cần kiểm tra header có tồn tại?

Header có thể không xuất hiện khi:

- Container chưa bật `deliveryAttemptHeader`.
- Listener dùng factory khác với factory đã cấu hình.
- Error handler đang dùng không cung cấp delivery attempt theo hợp đồng tương ứng.
- Record được xử lý qua đường đi khác không được Spring Kafka container gắn header.
- Hệ thống vừa nâng cấp hoặc đổi cách triển khai và cấu hình chưa thống nhất.

Nếu cố gọi `ByteBuffer.wrap(header.value())` khi header bằng `null`, listener sẽ gặp lỗi mới chỉ vì logic quan sát. Vì vậy, kiểm tra `null` và độ dài 4 byte là biện pháp an toàn khi đọc trực tiếp raw header.

### 5.2. Không giải mã mọi header theo cách này

Kafka Headers là tập các cặp key/byte-array. Mỗi header có thể dùng kiểu mã hóa khác nhau. Không có quy tắc chung rằng mọi attempt header của mọi thư viện đều là 4 byte, hoặc mọi số đều big-endian.

Ví dụ, header do producer tự tạo, header retry topic và header từ middleware có thể dùng format khác. Chỉ áp dụng quy tắc giải mã khi đã xác nhận hợp đồng của đúng header và phiên bản thư viện.

## 6. Kết hợp với DefaultErrorHandler

`DefaultErrorHandler` được Spring Kafka dùng để quyết định record thất bại sẽ được retry như thế nào. Delivery attempt cung cấp tín hiệu cho biết lần xử lý hiện tại đang nằm ở đâu trong chuỗi retry do handler quản lý.

Ví dụ:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> template) {

    var recoverer =
            new DeadLetterPublishingRecoverer(template);

    var backOff = new FixedBackOff(2_000L, 3L);

    var handler = new DefaultErrorHandler(
            recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class);

    return handler;
}
~~~

Với một exception retryable luôn xảy ra, listener có thể được gọi lần đầu và tối đa ba lần retry. Giá trị delivery attempt của các lần gọi thường lần lượt là 1, 2, 3, 4 trong chuỗi đó. Nếu exception thuộc nhóm non-retryable, error handler có thể chuyển sang recovery ngay từ lần đầu.

Không nên thêm logic `if (attempt >= 4) ...` trong listener để thay thế chính sách retry của handler. Mốc tối đa phải được quản lý ở một nơi thống nhất; nếu handler đã kiểm soát số lần thử, listener chỉ cần xử lý nghiệp vụ và ném exception đúng loại.

### 6.1. Phân loại exception quan trọng hơn attempt

Một record lỗi validation cần được chuyển sang recovery ngay, dù đang ở attempt 1. Một record bị timeout tạm thời có thể hợp lý để retry với backoff. Chỉ nhìn số attempt mà bỏ qua exception type sẽ tạo chính sách không nhất quán.

Ví dụ:

| Exception | Retry? | Lý do |
|---|---|---|
| Timeout ngắn hạn | Có, hữu hạn | Có thể phục hồi khi dependency ổn định |
| HTTP 503 | Có, theo ngân sách thời gian | Dịch vụ phụ thuộc có thể sẵn sàng trở lại |
| Database deadlock | Có giới hạn | Transaction có thể chạy lại nếu idempotent |
| Payload sai schema | Thường không | Payload không tự sửa sau backoff |
| Business rule rejection | Thường không | Kết quả nghiệp vụ đã được xác định |
| Lỗi phân quyền lâu dài | Thường không retry dày | Cần thay đổi config/ACL |

Delivery attempt là **thông tin bổ trợ**, còn quyết định retry dựa trên kết hợp loại lỗi, thời gian đã tiêu tốn, số attempt và quy tắc nghiệp vụ.

## 7. Header trong retry topics khác gì?

Spring Kafka có hai mô hình retry được sử dụng rộng rãi:

1. **Blocking retry:** Error handler giữ record trong đường xử lý container, sử dụng backoff rồi cho listener xử lý lại. `KafkaHeaders.DELIVERY_ATTEMPT` là tín hiệu phù hợp để theo dõi lần giao theo cơ chế này.
2. **Non-blocking retry:** Record lỗi được publish sang một hoặc nhiều retry topic. Consumer của topic chính tiếp tục xử lý dữ liệu khác; một listener container khác tiêu thụ record từ retry topic theo thời gian chờ.

Retry topic infrastructure có thông tin số lần thử và các header chuyên dụng của nó, ví dụ `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` trong các phiên bản Spring Kafka hỗ trợ API đó. Bộ đếm này có phạm vi khác với delivery attempt của một listener container.

| Tình huống | Điều có thể thay đổi |
|---|---|
| Blocking retry của cùng record trong container | Delivery attempt tăng theo lần giao của handler |
| Record được publish sang retry topic | Record mới trên topic khác, kèm metadata retry-topic |
| DLT consumer đọc record | Một lần giao mới ở container DLT; không mặc nhiên nối tiếp attempt ở listener nguồn |
| Replay DLT về topic chính | Một luồng xử lý mới, cần event id để nhận diện sự kiện gốc |
| Consumer restart/rebalance | Trạng thái đếm attempt có thể bị thiết lập lại hoặc thay đổi |

Không cộng thẳng `KafkaHeaders.DELIVERY_ATTEMPT` với attempt của retry topic hoặc xem chúng là cùng một bộ đếm bền vững. Nếu hệ thống cần thống kê tổng số lần xử lý xuyên suốt các topic, hãy thiết kế metadata riêng với hợp đồng rõ ràng và giữ nó qua mỗi lần republish.

### 7.1. Ví dụ @RetryableTopic

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Ở đây, `attempts = "4"` là tổng số lần thử của chính sách non-blocking retry, bao gồm lần xử lý ban đầu. Cách tạo topic, tên header và behavior cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình retry topic.

Ví dụ này không tự bật delivery attempt header của container. Nếu ứng dụng muốn đọc cả hai loại thông tin, cần cấu hình và phân biệt rõ các nguồn attempt.

### 7.2. Thứ tự nghiệp vụ khi retry topic

Record được đưa sang retry topic có thể được xử lý **sau** các record mới hơn từ topic chính, kể cả khi chúng có cùng business key. Vì vậy, retry topic có thể làm thay đổi thứ tự hoàn tất nghiệp vụ. Delivery attempts header không giải quyết được vấn đề này.

Nếu nghiệp vụ cần thứ tự nghiêm ngặt, hãy cân nhắc blocking retry, xử lý tuần tự theo key hoặc version check/idempotency ở database.

## 8. Delivery attempt có được lưu bền vững không?

Không nên xem delivery attempt của listener container là một bộ đếm persisted xuyên suốt mọi sự cố. Tùy handler và phiên bản, trạng thái thất bại của record được duy trì trong memory hoặc trong phạm vi xử lý của container.

Các tình huống cần chú ý:

- **Restart ứng dụng:** Consumer đọc lại record chưa commit. Một chuỗi retry mới có thể bắt đầu từ attempt 1.
- **Rebalance:** Partition chuyển sang consumer khác. Member mới có thể không biết lịch sử retry trong memory của member cũ.
- **Recovery thành công:** Trạng thái retry của record thường được xóa hoặc đặt lại khi handler chuyển sang record khác.
- **Replay DLT:** Event được xử lý trong một luồng mới; attempt container mới không phản ánh toàn bộ lịch sử trước đó.
- **Retry topic:** Attempt do retry infrastructure quản lý có phạm vi khác và có thể được mang qua Kafka headers của record được republish.

Nếu quy định nghiệp vụ yêu cầu tối đa N lần xử lý trong nhiều ngày hoặc qua nhiều lần deploy, hãy dùng một bộ đếm bền vững ở database hoặc trong metadata event được quản lý rõ ràng. Không dựa vào delivery attempt header để thực thi chính sách dài hạn.

## 9. Quan hệ với offset commit và acknowledgement

Header thể hiện lần giao record; nó không xác nhận record đã được xử lý và không thay đổi thời điểm commit offset.

Với at-least-once:

1. Listener nhận record.
2. Listener thực hiện nghiệp vụ.
3. Nếu thành công, container ack/commit theo cấu hình.
4. Nếu thất bại, error handler retry/recovery.
5. Nếu đã hoàn tất side effect nhưng process dừng trước commit offset, record có thể được giao lại.

Trong bước 5, một lần giao lại có thể bắt đầu một bộ đếm attempt mới sau restart dù nghiệp vụ đã hoàn tất trước đó. Vì vậy, ứng dụng vẫn cần idempotency.

Ví dụ một inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Ghi event id và thay đổi nghiệp vụ trong cùng transaction database. Nếu event được giao lại, unique constraint giúp nhận diện đã xử lý và tránh side effect lặp.

Không lấy giá trị delivery attempt làm idempotency key. Nó không duy nhất và có thể lặp lại trên các record khác nhau.

## 10. Log delivery attempt đúng cách

Khi cần điều tra retry, log nên chứa cả định danh record và lần giao. Ví dụ listener nhận `ConsumerRecord` cùng header:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "ordersListenerFactory")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        @Header(name = KafkaHeaders.DELIVERY_ATTEMPT,
                required = false) Integer attempt) {

    log.info(
            "Kafka record received: topic={}, partition={}, " +
            "offset={}, key={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            attempt == null ? "unknown" : attempt);

    orderService.processIdempotently(record.value());
}
~~~

Chỉ log key khi được phép theo chính sách bảo mật. Kafka key có thể chứa thông tin định danh hoặc nhạy cảm; khi cần có thể chỉ log correlation id đã được ẩn danh hoặc hash thích hợp. Không log toàn bộ payload chỉ để biết attempt.

Trong hệ thống có nhiều instance, nên có thêm service name, consumer group, listener id và trace id (trong trace/log) để nối các lần xử lý. Không đưa event id hoặc trace id trực tiếp vào metric tag có cardinality cao.

### 10.1. Ghi log theo mức độ cần thiết

Ghi log INFO cho mọi record ở hệ thống nhiều triệu record mỗi ngày có thể rất tốn dung lượng. Một số lựa chọn:

- Ghi DEBUG cho attempt đầu tiên, WARN khi attempt vượt ngưỡng.
- Ghi ERROR khi record hết retry hoặc recovery thất bại.
- Dùng metric tổng hợp để theo dõi xu hướng, dùng log để điều tra record cụ thể.
- Lấy mẫu có kiểm soát khi volume quá lớn, nhưng không làm mất log của các lỗi nghiêm trọng.

Header giúp xây dựng thông điệp có ngữ cảnh; nó không bắt buộc ứng dụng ghi một dòng log cho từng delivery.

## 11. Metrics và alert liên quan đến delivery attempts

Metrics nên phản ánh cả **lần giao lại** và **hậu quả nghiệp vụ**. Chỉ số attempt cao có thể gợi ý dependency bất ổn, nhưng bản thân attempt không chỉ ra nguyên nhân.

| Chỉ số | Mục đích |
|---|---|
| Record processing duration | Thời gian listener xử lý mỗi lần gọi |
| Retry/re-delivery rate | Tốc độ record được xử lý lại |
| Delivery attempt distribution | Tỷ lệ record ở attempt 1, 2, 3 hoặc nhóm vượt ngưỡng |
| Listener exception rate | Phân loại lỗi gây retry |
| Consumer lag | Phát hiện backlog do retry kéo dài |
| Oldest record age | Đo mức độ trễ theo SLA |
| DLT incoming rate | Phát hiện record hết retry cần điều tra |
| Recovery failure count | Phát hiện đường recovery không khả dụng |

Nếu muốn thêm attempt vào metric tag, hãy gom thành tập giá trị nhỏ và ổn định, ví dụ `first`, `retry_2_3` và `retry_4_plus`. Không dùng offset, event id, order id hay exception message nguyên văn làm tag.

### 11.1. Một số alert hữu ích

- Retry/delivery attempt trung bình tăng bất thường sau deploy.
- Tỷ lệ record đạt attempt cao tăng kéo dài.
- Listener exception rate tăng cùng consumer lag.
- DLT nhận nhiều record hơn baseline.
- Dependency timeout tăng trong cùng khoảng thời gian.
- Recovery/DLT publish failure xuất hiện.

Ngưỡng nên dựa vào SLO và đặc điểm workload. Một luồng gọi API phụ thuộc có thể chấp nhận retry ngắn; một luồng xác nhận thanh toán có thể cần quy trình đối soát ngay khi kết quả timeout không rõ ràng.

## 12. Runbook khi attempt tăng bất thường

### 12.1. Nhiều record chuyển từ attempt 1 sang 2 hoặc 3

1. Nhóm lỗi theo exception class và service phụ thuộc.
2. So sánh thời điểm bắt đầu tăng retry với release/config gần nhất.
3. Kiểm tra timeout, throttling, network và broker/consumer health.
4. Đo tổng thời gian backoff và số lần gọi downstream.
5. Xác nhận exception có thực sự retryable không.
6. Giới hạn concurrency hoặc điều chỉnh backoff nếu retry đang gây thêm tải.
7. Theo dõi consumer lag và tuổi record cũ nhất cho tới khi phục hồi.

### 12.2. Record được giao lại nhưng header vẫn bằng 1

Có thể đây là chuỗi retry mới sau consumer restart/rebalance, listener chưa bật header, hoặc record đã được chuyển sang topic khác. Các bước:

1. Xác nhận container có bật delivery attempt header.
2. Xác nhận listener dùng đúng factory và error handler.
3. Kiểm tra consumer restart, rebalance và partition assignment.
4. Xác định record đến từ topic chính, retry topic hay DLT.
5. Kiểm tra có đang trộn retry-topic attempt với delivery attempt không.
6. Dựa vào event id và log trước đó để xác nhận lịch sử thực tế.

### 12.3. Listener không nhận được header

1. Kiểm tra phiên bản Spring Kafka.
2. Kiểm tra `setDeliveryAttemptHeader(true)` trên container đang chạy.
3. Kiểm tra handler có hỗ trợ `DeliveryAttemptAware`.
4. Nếu dùng annotation, kiểm tra tên và `required = false`.
5. Nếu đọc raw header, kiểm tra `lastHeader(...)` và độ dài byte array.
6. Xem listener có chạy qua đường consumer custom ngoài container hay không.

Không vội thêm một custom header của producer có cùng tên để “bù” vào. Header do producer tạo không phản ánh số lần container giao record và có thể làm chẩn đoán sai.

### 12.4. DLT tăng nhưng attempt chỉ bằng 1

Điều này có thể đúng nếu exception đã được phân loại non-retryable. Hãy kiểm tra error classification, cấu hình `addNotRetryableExceptions(...)` và nguyên nhân thực tế. Không tăng retry chỉ để attempt lớn hơn; đối với payload sai schema hoặc validation error, retry nhiều lần có thể chỉ tăng lag.

## 13. Kiểm thử delivery attempts header

Integration test nên xác nhận cả giá trị header và hành vi retry. Một kịch bản minh họa:

1. Tạo topic test và listener container có bật delivery attempt header.
2. Cấu hình `DefaultErrorHandler` với hai lần retry ngắn.
3. Gửi một record có event id ổn định.
4. Cho listener ném exception retryable trong hai lần đầu.
5. Cho listener thành công ở lần ba.
6. Ghi nhận các giá trị attempt mà listener nhìn thấy.
7. Xác nhận ba lần gọi tương ứng attempt 1, 2, 3 trong chuỗi retry.
8. Kiểm tra offset chỉ được xác nhận sau xử lý thành công.
9. Thử loại exception non-retryable và xác nhận không cần đi qua nhiều attempt.
10. Thử restart giữa retry để quan sát giới hạn của bộ đếm trong memory.

Cũng nên thử listener không bật header để xác nhận code xử lý trường hợp thiếu header mà không tạo lỗi mới. Nếu dùng retry topic, kiểm tra riêng attempt metadata của retry-topic infrastructure, vì phạm vi đếm khác với blocking retry.

### 13.1. Mẫu kiểm tra trong listener thử nghiệm

Có thể lưu các lần nhận để xác minh:

~~~java
List<Integer> observedAttempts =
        new CopyOnWriteArrayList<>();

@KafkaListener(
        topics = "orders.test",
        containerFactory = "ordersListenerFactory")
public void testListener(
        OrderEvent event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {

    observedAttempts.add(attempt);

    if (attempt < 3) {
        throw new TemporaryInventoryException(
                "Injected test failure");
    }
}
~~~

Đây là đoạn minh họa cơ chế ghi nhận attempt, không phải một test class hoàn chỉnh. Trong kiểm thử tích hợp, cần đồng bộ việc chờ ba lần xử lý, cách reset trạng thái test và việc xác nhận offset để tránh flaky test.

## 14. Những sai lầm thường gặp

**Coi attempt 1 là “chưa từng lỗi”:** Consumer có thể vừa restart hoặc record được replay. Header không phải lịch sử retry bền vững.

**Hiểu attempt 3 là ba lần retry:** Attempt tính cả lần giao đầu tiên, nên thường tương ứng hai lần retry sau lần đầu.

**Không bật header trên đúng container:** Chỉ cấu hình factory khác hoặc dùng Kafka client property sẽ không làm listener nhận header.

**Buộc header luôn có mặt:** Một số đường xử lý không có header. Dùng kiểu nullable và kiểm tra trước khi giải mã raw bytes.

**Đọc raw bytes như chuỗi UTF-8:** Delivery attempt của cơ chế này được mã hóa thành số nguyên 4 byte; giải mã sai sẽ cho giá trị vô nghĩa.

**Dùng attempt làm idempotency key:** Attempt không duy nhất, có thể reset và thay đổi. Cần event id nghiệp vụ ổn định.

**Trộn blocking và non-blocking attempt:** Retry topic có cơ chế metadata riêng. Xác định rõ bộ đếm đang nói đến.

**Tăng retry chỉ vì header có giá trị thấp:** Quyết định retry dựa trên exception và SLA, không nhằm làm attempt tăng.

**Đưa event id vào metric tag:** Cardinality sẽ tăng mạnh; lưu định danh chi tiết trong log/trace.

## 15. Checklist triển khai và vận hành

### Cấu hình

- [ ] Đã xác định phiên bản Spring Kafka và API hỗ trợ.
- [ ] `deliveryAttemptHeader` được bật trên đúng `ContainerProperties`.
- [ ] Error handler hỗ trợ delivery attempt.
- [ ] Listener đang sử dụng đúng container factory.
- [ ] Giá trị header được đọc an toàn khi có thể vắng mặt.

### Chính sách retry

- [ ] Đã phân loại exception retryable và non-retryable.
- [ ] Có giới hạn số lần retry và backoff.
- [ ] Đã phân biệt delivery attempt với producer retry và retry-topic attempts.
- [ ] DLT/recovery chỉ xác nhận thành công khi lưu record an toàn.
- [ ] Consumer có idempotency khi record được giao lại.

### Observability

- [ ] Log chứa topic, partition, offset và attempt khi phù hợp.
- [ ] Metrics theo dõi retry, exception, lag và DLT.
- [ ] Không dùng key hoặc event id động làm metric tag.
- [ ] Có alert khi attempt cao kéo dài hoặc retry tăng bất thường.
- [ ] Runbook xử lý trường hợp header thiếu hoặc reset sau restart.

### Kiểm thử

- [ ] Record thành công ngay có attempt ban đầu phù hợp.
- [ ] Retry hữu hạn làm attempt tăng trong cùng chuỗi xử lý.
- [ ] Non-retryable exception chuyển recovery theo chính sách.
- [ ] Header thiếu không làm hỏng listener.
- [ ] Restart/rebalance và DLT replay được kiểm thử nếu liên quan tới hệ thống.

## Kết luận

`KafkaHeaders.DELIVERY_ATTEMPT` cung cấp tín hiệu trực tiếp về lần giao record mà listener đang xử lý. Khi bật `ContainerProperties.setDeliveryAttemptHeader(true)` và sử dụng error handler phù hợp, Spring Kafka có thể đưa số attempt vào header để listener đọc qua `@Header` hoặc `ConsumerRecord.headers()`. Giá trị bắt đầu từ 1 và tăng theo những lần giao lại trong phạm vi cơ chế retry tương ứng. Hãy dùng nó để quan sát lỗi, giải thích retry và hỗ trợ vận hành; để bảo đảm độ tin cậy lâu dài, vẫn cần phân loại exception, backoff có giới hạn, recovery/DLT, idempotency và cơ chế lưu trạng thái riêng nếu nghiệp vụ cần đếm attempt xuyên qua nhiều lần restart hoặc replay.
