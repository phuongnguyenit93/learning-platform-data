# Retain và resubmit record

## 1. Ý nghĩa của retain và resubmit trong DefaultErrorHandler

Trong Spring Kafka, `DefaultErrorHandler` xử lý record listener gặp exception. Sau một lần xử lý thất bại, error handler quyết định record nào cần thử lại, khi nào thử lại và khi nào chuyển sang recovery, ví dụ publish sang dead-letter topic (DLT).

Cách truyền thống là seek consumer về offset của record lỗi để Kafka fetch lại record đó cùng các record chưa xử lý phía sau. Từ Spring Kafka 2.9, có thể cấu hình `DefaultErrorHandler` dùng chế độ retain và resubmit bằng `setSeekAfterError(false)`.

Với chế độ này:

- Container giữ các record chưa xử lý trong bộ nhớ.
- Error handler thực hiện retry theo backoff đã cấu hình.
- Sau khi error handler kết thúc, container giao lại các record chưa xử lý cho listener.
- Container thực hiện một lần poll khi consumer đang pause để duy trì hoạt động của group và heartbeat theo cơ chế Kafka client.
- Container không seek partition về offset lỗi để fetch lại các record đó ngay trong chu kỳ retry này.

Cần phân biệt hai khái niệm:

- **Retain**: giữ record chưa xử lý trong bộ nhớ của listener container.
- **Resubmit**: chuyển lại các record được giữ đến listener để xử lý tiếp.

Resubmit ở đây không phải producer gửi lại record vào Kafka và cũng không phải broker tạo bản sao mới. Đây là cơ chế container giao lại record đã fetch nhưng chưa được xử lý thành công.

Chế độ này hữu ích khi muốn giảm các thao tác seek và giữ nguyên tập record đã fetch trong quá trình retry. Tuy nhiên, record được giữ trong bộ nhớ, nên cần quan tâm đến batch size, thời gian retry, memory và hành vi khi consumer bị dừng hoặc rebalance.

## 2. Hai cách xử lý record sau lỗi

### 2.1. Seek và fetch lại (mặc định)

Theo hành vi mặc định, khi listener thất bại, container/error handler seek các partition về offset cần xử lý lại. Lần poll tiếp theo, Kafka consumer fetch lại record lỗi và các record chưa xử lý sau nó.

Ví dụ một lần poll trả về các record offset 20, 21 và 22 trên cùng partition. Listener xử lý 20 thành công nhưng lỗi ở 21:

~~~text
Poll:
  offset 20
  offset 21  <-- listener ném exception
  offset 22

Error handling:
  commit tiến độ đã xử lý trước record lỗi (nếu phù hợp với ack mode)
  seek partition về offset 21

Poll tiếp theo:
  fetch lại 21, 22
~~~

Cách này dựa vào offset của Kafka để lấy lại dữ liệu. Record chưa xử lý được broker cung cấp lại từ log, miễn là record còn nằm trong retention và partition vẫn có thể được đọc.

### 2.2. Retain và resubmit

Khi cấu hình `seekAfterError=false`, container không seek partition để fetch lại phần còn lại. Thay vào đó, nó giữ các record chưa xử lý và resubmit chúng sau khi error handler kết thúc.

~~~text
Poll:
  offset 20
  offset 21  <-- listener ném exception
  offset 22

Retain:
  giữ record 21 và 22 trong container

Retry/backoff:
  error handler xử lý lỗi của 21

Resubmit:
  listener nhận lại 21 và phần record chưa xử lý 22
~~~

Record 20 đã được xử lý thành công có thể được commit theo acknowledgment mode. Phần chưa xử lý được giữ lại để tiếp tục, thay vì yêu cầu consumer seek rồi fetch lại từ broker.

Trong một batch, danh sách retained records có thể chứa record lỗi và các record đứng sau chưa được xử lý. Với record listener, container có thể giữ record cần retry cùng các record chưa xử lý còn lại của lần poll.

### 2.3. So sánh nhanh

| Tiêu chí | Seek và fetch lại | Retain và resubmit |
|---|---|---|
| Cách lấy lại record | Seek partition rồi poll/fetch từ broker | Giữ record đã fetch trong bộ nhớ container |
| Thao tác seek | Có | Không seek để xử lý lại phần retained |
| Nguồn record trong lần thử tiếp | Kafka log | Danh sách record container đang giữ |
| Bộ nhớ container | Không cần giữ toàn bộ phần còn lại ngoài xử lý hiện tại | Cần giữ các record chưa xử lý |
| Tác động đến broker fetch | Có fetch lại sau seek | Tránh fetch lại phần retained trong lần retry |
| Hành vi sau process restart | Fetch lại theo committed offset | Retained records trong RAM mất; Kafka có thể giao lại từ committed offset |
| Phiên bản | Hành vi mặc định truyền thống | Hỗ trợ từ Spring Kafka 2.9 |

Hai chế độ vẫn hướng đến cùng mục tiêu: tiếp tục xử lý record chưa hoàn tất và không commit vượt qua tiến độ chưa được xử lý. Khác biệt chính là cách container có được record ở lần thử tiếp theo.

## 3. Cấu hình DefaultErrorHandler để retain và resubmit

### 3.1. Cấu hình bằng Java

Có thể tạo `DefaultErrorHandler`, cấu hình backoff và tắt seek-after-error:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public DefaultErrorHandler defaultErrorHandler() {
        BackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(backOff);

        errorHandler.setSeekAfterError(false);

        return errorHandler;
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler defaultErrorHandler
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(defaultErrorHandler);

        return factory;
    }
}
~~~

Trong ví dụ:

- `FixedBackOff(1_000L, 2L)` chờ một giây giữa các lần retry và cho phép hai lần retry sau lần gọi đầu tiên.
- `setSeekAfterError(false)` yêu cầu container retain các record chưa xử lý rồi resubmit.
- `setCommonErrorHandler(...)` gắn handler vào listener container factory.

Số lần thử và backoff chỉ là giá trị minh họa. Cần chọn theo loại lỗi, SLA và thời gian phục hồi của downstream.

### 3.2. Dùng bean error handler cho nhiều factory

Nếu ứng dụng có nhiều listener container factory, cần gắn error handler vào từng factory muốn sử dụng chế độ retain. Việc khai báo bean `DefaultErrorHandler` không tự bảo đảm mọi factory tùy chỉnh đều sử dụng bean đó.

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
        paymentKafkaListenerContainerFactory(
            ConsumerFactory<String, PaymentEvent> paymentConsumerFactory,
            DefaultErrorHandler defaultErrorHandler
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();

    factory.setConsumerFactory(paymentConsumerFactory);
    factory.setCommonErrorHandler(defaultErrorHandler);

    return factory;
}
~~~

Nếu mỗi factory cần retry policy khác nhau, tạo handler riêng cho từng loại workload. Ví dụ listener thanh toán có thể cần backoff dài hơn listener telemetry; dùng chung một handler có thể khiến chính sách của hai luồng khó điều chỉnh độc lập.

### 3.3. Kiểm tra phiên bản

`setSeekAfterError(false)` được hỗ trợ từ Spring Kafka 2.9. Nếu ứng dụng dùng phiên bản cũ hơn, API này có thể không tồn tại. Hãy kiểm tra phiên bản Spring Kafka thực tế trong dependency tree và Javadoc tương ứng.

Spring Boot quản lý phiên bản Spring Kafka và Kafka client theo dependency management của từng release. Không nên nâng riêng một thư viện mà bỏ qua compatibility matrix của Boot.

## 4. Luồng retry khi retain và resubmit

### 4.1. Một record listener gặp lỗi

Giả sử consumer poll một số record và listener xử lý từng record. Record offset 31 gặp exception tạm thời:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant C as Listener container
    participant L as Listener
    participant E as DefaultErrorHandler

    K-->>C: Poll records 30, 31, 32
    C->>L: Process record 30
    L-->>C: Success
    C->>L: Process record 31
    L-->>C: Exception
    C->>E: Handle failure at offset 31
    E->>E: Apply BackOff and retry policy
    E-->>C: Return with unprocessed records retained
    C->>K: Paused poll to maintain group activity
    C->>L: Resubmit record 31
    L-->>C: Success
    C->>L: Process record 32
    L-->>C: Success
    C->>K: Commit eligible offsets
~~~

Sơ đồ là luồng khái quát. Số lần gọi listener, thời điểm commit và cách handler tiến hành recovery phụ thuộc ack mode, loại listener, BackOff và cấu hình container.

### 4.2. Record trước record lỗi

Nếu record 30 đã được xử lý thành công trước khi record 31 lỗi, container có thể commit offset thể hiện tiến độ qua record 30, theo acknowledgment mode và cơ chế commit đang sử dụng.

Không được commit offset vượt qua record 31 khi record đó chưa được xử lý hoặc phục hồi theo chính sách. Nếu commit vượt qua record lỗi, consumer có thể bỏ qua nó sau restart.

### 4.3. Record sau record lỗi

Record 32 chưa được gọi listener trong ví dụ trên. Nó thuộc phần chưa xử lý và được giữ cùng record 31 để resubmit theo cơ chế container.

Điều này quan trọng với thứ tự trong partition. Container cần tiếp tục từ record lỗi và phần còn lại theo thứ tự mà consumer đã nhận, thay vì xử lý record phía sau rồi commit offset vượt qua record chưa hoàn tất.

Với nhiều partition, mỗi partition có tiến độ riêng. Không được suy ra offset của partition này từ offset của partition khác.

## 5. BackOff quyết định khoảng chờ retry

Retain và resubmit chỉ quyết định cách giữ và giao lại record. BackOff quyết định thời điểm thử lại.

### 5.1. FixedBackOff

`FixedBackOff` dùng khoảng chờ cố định giữa các lần thử:

~~~java
BackOff backOff = new FixedBackOff(2_000L, 3L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);

handler.setSeekAfterError(false);
~~~

Trong ví dụ này, mỗi lần retry cách nhau hai giây và có ba lần retry sau lần gọi ban đầu. Khi đã hết retry, handler chuyển sang recovery theo recoverer được cấu hình hoặc hành vi mặc định.

Không nên hiểu số lần retry là tổng số lần listener được gọi. Cần phân biệt lần gọi đầu tiên và số lần retry bổ sung theo semantics của BackOff.

### 5.2. ExponentialBackOff

Với downstream có thời gian phục hồi biến động, exponential backoff tăng dần khoảng chờ:

~~~java
ExponentialBackOff backOff = new ExponentialBackOff(
    1_000L,
    2.0
);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);

handler.setSeekAfterError(false);
~~~

Ví dụ bắt đầu chờ một giây, tăng khoảng chờ theo hệ số 2, giới hạn mỗi khoảng ở mười giây và tổng thời gian theo cấu hình. API và giá trị mặc định của `ExponentialBackOff` cần đối chiếu với Spring Framework version mà dự án dùng.

Backoff giúp tránh retry dồn dập vào một service đang lỗi. Tuy nhiên, thời gian chờ dài cũng làm record nằm lại lâu hơn và có thể khiến consumer lag tăng.

### 5.3. BackOff không phải timeout của listener

BackOff chỉ quyết định thời gian chờ giữa các lần thử. Nó không giới hạn thời gian listener xử lý một record.

Nếu listener gọi database hoặc HTTP service có thể treo vô hạn, cần timeout riêng cho thao tác đó. Nếu listener mất quá lâu giữa các lần poll, consumer còn có thể vi phạm `max.poll.interval.ms` và bị rebalance.

## 6. Recovery sau khi hết retry

Khi BackOff báo đã hết lượt thử, `DefaultErrorHandler` có thể gọi recoverer để xử lý record không phục hồi được. Một lựa chọn phổ biến là publish record sang DLT.

### 6.1. DeadLetterPublishingRecoverer

~~~java
@Bean
public DefaultErrorHandler defaultErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setSeekAfterError(false);

    return handler;
}
~~~

Recoverer mặc định có thể định tuyến record đến DLT theo quy ước tên topic, thường thêm hậu tố `-dlt`, và sử dụng partition tương ứng nếu cấu hình mặc định được áp dụng. Cần bảo đảm topic DLT tồn tại, có partition phù hợp và producer có serializer xử lý được payload.

Khi record được recover thành công, handler có thể hoàn tất xử lý lỗi và container tiếp tục với record kế tiếp theo chính sách commit. Nếu publish DLT thất bại, cần kiểm tra handler/recoverer để tránh coi record đã được phục hồi khi bản ghi DLT chưa được ghi thành công.

### 6.2. Recoverer tùy chỉnh

Có thể tạo recoverer để ghi nhận lỗi hoặc route record theo nghiệp vụ:

~~~java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
        "Recovering record topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception
    );

    // Có thể publish DLT hoặc ghi metadata vào hệ thống phục hồi.
};

DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setSeekAfterError(false);
~~~

Recoverer cần có semantics rõ ràng: khi nào xem record đã được phục hồi, khi nào ném exception để yêu cầu thử lại recovery và khi nào cho phép container tiến offset. Không nên chỉ ghi log rồi xem như record đã được lưu an toàn nếu nghiệp vụ yêu cầu DLT hoặc quy trình replay.

### 6.3. Phân loại lỗi retryable và non-retryable

Không phải lỗi nào cũng nên retry. Ví dụ:

- Timeout database hoặc lỗi kết nối tạm thời có thể retry.
- HTTP 503 có thể retry với backoff.
- Payload sai định dạng hoặc thiếu trường bắt buộc thường không thể khắc phục bằng retry.
- Lỗi authorization thường cần sửa cấu hình hoặc credential.
- Vi phạm unique constraint có thể là duplicate hợp lệ hoặc lỗi nghiệp vụ, cần phân loại theo use case.

`DefaultErrorHandler` cho phép đánh dấu exception không retry bằng cơ chế phân loại như `addNotRetryableExceptions(...)` hoặc cấu hình retryable exception tương ứng.

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.addNotRetryableExceptions(
    IllegalArgumentException.class,
    DeserializationException.class
);

handler.setSeekAfterError(false);
~~~

Danh sách exception chỉ là ví dụ. Cần bảo đảm exception thực tế được Spring bọc hoặc ném ra đúng loại mà handler phân loại; nếu không, một lỗi đáng lẽ không retry có thể vẫn đi qua retry path.

## 7. Retain và resubmit với record listener

Record listener nhận từng record trong một lần poll. Khi một record lỗi, error handler xử lý lỗi đó. Với `seekAfterError=false`, container giữ record lỗi và các record chưa xử lý của lần poll để giao lại.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.process(event);
}
~~~

Nếu listener xử lý offset 40 thành công rồi lỗi ở offset 41:

- Offset 40 có thể được commit theo `AckMode.RECORD`.
- Offset 41 được giữ để retry.
- Các record sau 41 chưa được xử lý cũng được giữ.
- Sau khi retry thành công hoặc recovery hoàn tất, container tiếp tục xử lý phần còn lại.

Nếu lỗi xảy ra liên tục ở một record, record đó có thể làm chậm tiến độ của các record phía sau cùng partition. Backoff và recovery policy cần có giới hạn để tránh một poison record giữ luồng quá lâu.

## 8. Retain và resubmit với batch listener

### 8.1. Batch listener nhận nhiều record

Batch listener nhận danh sách record trong một lần poll:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

Nếu batch listener ném exception, handler cần biết record nào gây lỗi để xác định phần đã xử lý và phần cần retry. Với Spring Kafka, có thể ném `BatchListenerFailedException` và chỉ rõ record/index bị lỗi.

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrders(
    List<OrderCreated> events,
    Acknowledgment acknowledgment
) {
    for (int i = 0; i < events.size(); i++) {
        try {
            billingService.process(events.get(i));
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Cannot process batch record at index " + i,
                ex,
                i
            );
        }
    }

    acknowledgment.acknowledge();
}
~~~

Đoạn code minh họa ý tưởng chỉ ra record lỗi; chữ ký constructor của `BatchListenerFailedException` cần khớp phiên bản Spring Kafka đang sử dụng. Với batch listener, cách handler xác định offset đã xử lý và phần retained phụ thuộc thông tin lỗi mà listener cung cấp.

### 8.2. Nếu không xác định được record lỗi

Nếu batch listener ném exception chung mà không chỉ rõ record lỗi, handler có thể phải xử lý lại toàn bộ batch theo fallback behavior. Điều này có thể khiến record đã xử lý trước đó được gọi lại.

Vì vậy, nếu xử lý từng phần tử trong batch, hãy xác định rõ record/index gây lỗi. Nếu batch được xử lý nguyên tử ở tầng database, exception của cả batch có thể là lựa chọn hợp lý, nhưng phải bảo đảm transaction database rollback toàn bộ side effect tương ứng.

### 8.3. Retained batch và memory

Ở chế độ retain, container cần giữ các record chưa xử lý. Với batch lớn hoặc payload lớn, memory sử dụng có thể tăng đáng kể trong thời gian retry.

Cần kiểm soát:

- `max.poll.records`.
- Kích thước record và batch.
- Số partition được gán cho consumer.
- Thời gian backoff và số lần retry.
- Số consumer đồng thời gặp lỗi.
- Heap và garbage collection.

Không nên tăng `max.poll.records` quá cao nếu payload lớn và downstream đang lỗi kéo dài. Retain làm giảm fetch lại nhưng đổi lại giữ record trong bộ nhớ cho đến khi retry/recovery hoàn tất.

## 9. Paused poll và giữ group membership

Khi dùng retain và resubmit, container có thể cần giữ các record trong bộ nhớ trong thời gian backoff. Trong lúc đó, nó pause consumer và thực hiện một poll để consumer tiếp tục duy trì hoạt động trong group.

Mục tiêu của paused poll:

- Tiếp tục xử lý hoạt động group coordination/heartbeat theo Kafka client.
- Giảm nguy cơ consumer bị loại khỏi group chỉ vì đang chờ retry.
- Giữ partition assignment trong khi container hoàn tất error handling.
- Tránh fetch thêm dữ liệu mới không cần thiết khi phần retained chưa được xử lý.

Paused poll không có nghĩa listener tiếp tục xử lý record mới trong lúc đang pause. Nó phục vụ vòng đời consumer và group membership.

Nếu thời gian retry và listener processing quá dài, vẫn cần xem `max.poll.interval.ms`, session/heartbeat configuration và phiên bản group protocol. Một paused poll giúp container duy trì consumer activity theo thiết kế, nhưng không phải giấy phép để listener block vô hạn.

## 10. Quan hệ với acknowledgment mode và commit

Retain/resubmit không thay thế acknowledgment mode. Ack mode vẫn quyết định container commit offset khi nào sau khi record được xử lý hoặc được recover.

Một số mode phổ biến:

| AckMode | Ảnh hưởng tổng quát |
|---|---|
| `RECORD` | Commit sau từng record listener thành công |
| `BATCH` | Commit sau khi batch từ poll được xử lý thành công |
| `MANUAL` | Listener đánh dấu acknowledgment; container commit theo semantics manual |
| `MANUAL_IMMEDIATE` | Có thể commit ngay khi acknowledge trên consumer thread |

Khi record lỗi, container không nên commit vượt qua record đó nếu chưa xử lý hoặc recover thành công. Nếu một record trước đó trong cùng partition đã hoàn tất, tiến độ tương ứng có thể được commit theo ack mode.

Khi recoverer xử lý record thành công, commit behavior còn phụ thuộc các thuộc tính của error handler như `ackAfterHandle`, `commitRecovered` và ack mode. Đặc biệt, `commitRecovered` có yêu cầu cụ thể về manual immediate acknowledgment trong các phiên bản hỗ trợ. Hãy xác nhận Javadoc phiên bản đang chạy trước khi dùng.

Không được giả định `setSeekAfterError(false)` tự quyết định commit offset. Thuộc tính này chỉ chọn cách giữ/giao lại record chưa xử lý.

## 11. Retain/resubmit và rebalance

### 11.1. Consumer bị rebalance trong lúc retry

Trong lúc record được giữ trong memory và handler chờ backoff, group có thể cần rebalance do consumer khác tham gia/rời group, partition thay đổi hoặc consumer mất kết nối.

Khi partition bị thu hồi, container cần tuân thủ quy trình rebalance và quyền sở hữu partition. Record retained chưa commit có thể cần được xử lý lại từ Kafka khi partition được giao cho consumer khác hoặc khi consumer khởi động lại.

Không nên coi record trong memory là bản lưu bền vững. Nếu process crash, memory mất; committed offset là cơ sở để consumer khôi phục tiến độ.

### 11.2. Không xử lý side effect ở thread nền sau khi partition đã chuyển

Nếu listener tự gửi task sang executor, task có thể còn chạy khi partition bị revoke. Consumer mới có thể nhận cùng record trong khi task cũ vẫn đang ghi database.

Cần:

- Theo dõi task theo topic-partition.
- Dừng nhận task mới khi partition bị revoke.
- Chờ hoặc hủy task đang chạy theo deadline.
- Không commit offset vượt qua task chưa hoàn tất.
- Dùng idempotency cho side effect để chịu được redelivery.

Retain/resubmit chỉ quản lý record trong listener container; nó không tự quản lý executor hoặc task do ứng dụng tạo.

## 12. Retry, delivery attempt và quan sát

Để theo dõi record đã được thử bao nhiêu lần, Spring Kafka cung cấp delivery attempt header trong các phiên bản hỗ trợ. Có thể bật delivery attempt header trên container properties và đọc header trong listener hoặc DLT.

Ví dụ cấu hình:

~~~java
factory.getContainerProperties()
    .setDeliveryAttemptHeader(true);
~~~

Sau đó có thể đọc header tương ứng từ message hoặc record theo API của phiên bản. Delivery attempt hỗ trợ chẩn đoán nhưng không nên dùng làm event ID hoặc khóa idempotency. Một lần redelivery sau process restart có thể có lịch sử attempt khác với lần retry trong memory.

Các thông tin nên ghi nhận:

- Topic, partition, offset.
- Key và event ID.
- Consumer group và client/member ID nếu có.
- Exception class và root cause.
- Delivery attempt.
- Thời gian xử lý và thời gian backoff.
- Kết quả recovery/DLT.
- Committed offset sau khi xử lý.

Metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Listener failure count | Số lần listener ném exception |
| Retry attempt count | Số lần retry |
| Recovery count | Số record đã đi qua recoverer |
| DLT publish success/error | Kết quả gửi record lỗi sang DLT |
| Retained record count/age | Số record giữ lại và thời gian chờ nếu ứng dụng tự instrument |
| Consumer lag | Mức chậm của group |
| Listener duration | Thời gian xử lý một record/batch |
| Heap/GC | Áp lực bộ nhớ khi giữ record |

Tên metric cụ thể phụ thuộc Spring Kafka, Kafka client và hệ thống metrics. Không phải mọi phiên bản đều xuất sẵn metric cho retained record count; có thể cần instrumentation bổ sung.

## 13. Những tình huống nên dùng retain và resubmit

### 13.1. Hạn chế seek trong retry flow

Khi consumer đã fetch một batch và chỉ một record lỗi, retain có thể giúp container giữ phần chưa xử lý rồi giao lại mà không cần seek partition. Điều này hữu ích khi muốn tiếp tục từ dữ liệu đã fetch và giảm thao tác fetch lại phần record còn lại.

### 13.2. Batch processing có chi phí fetch cao

Nếu record có payload lớn hoặc việc fetch lại batch tạo thêm tải đáng kể, retain có thể tránh một vòng fetch lại trong retry. Tuy nhiên, lợi ích phải được cân bằng với heap giữ payload và thời gian record nằm trong bộ nhớ.

### 13.3. Muốn kiểm soát retry trong container

Retain/resubmit giúp hành vi retry diễn ra trong listener container với BackOff và error handler. Nó không cần một producer gửi lại record hoặc một topic retry chỉ để thử lại ngay record đã fetch.

Nếu cần delay dài, retry qua nhiều giờ hoặc tách retry workload khỏi partition chính, retry topic có thể phù hợp hơn. Retain không phải giải pháp lưu trữ retry lâu dài.

## 14. Khi nào cần cân nhắc seek hoặc retry topic?

Retain/resubmit không phải lựa chọn tốt nhất cho mọi tình huống.

| Tình huống | Hướng cân nhắc |
|---|---|
| Retry ngắn, record đã fetch và muốn giữ phần còn lại | Retain/resubmit |
| Muốn hành vi mặc định, fetch lại từ Kafka | Seek và fetch lại |
| Retry cần delay dài, không muốn giữ record trong heap | Retry topic hoặc một cơ chế lưu trữ retry |
| Cần tách luồng lỗi khỏi partition chính | DLT hoặc retry topic |
| Payload lớn, nhiều record lỗi cùng lúc | Đánh giá memory trước khi retain |
| Listener xử lý batch nguyên tử | Batch retry/recovery theo transaction |
| Consumer thường xuyên rebalance hoặc restart | Kiểm tra nguyên nhân group instability và khả năng replay từ committed offset |

Retry topic có thể cho phép partition chính tiếp tục với record phía sau, nhưng có thể làm thay đổi thứ tự xử lý. Retain thường giữ phần record chưa xử lý của poll và tiếp tục theo luồng hiện tại; nó không tạo một lịch retry bền vững ngoài Kafka.

## 15. Các lỗi thường gặp khi dùng retain và resubmit

**Cho rằng record được publish lại:** resubmit là container giao lại record đã giữ trong memory, không phải producer gửi một bản ghi mới đến Kafka.

**Quên cấu hình `setSeekAfterError(false)`:** handler vẫn dùng hành vi seek mặc định. Chỉ khai báo `DefaultErrorHandler` không tự bật retain.

**Dùng phiên bản Spring Kafka quá cũ:** API retain/resubmit không có trong một số phiên bản trước 2.9.

**Không tính memory:** payload và batch được giữ trong container trong thời gian retry, có thể gây heap pressure khi batch lớn hoặc nhiều listener cùng lỗi.

**Retry vô hạn:** poison record giữ partition không tiến triển, consumer lag tăng và các record phía sau bị trì hoãn.

**Không phân loại exception:** lỗi schema hoặc dữ liệu không thể khắc phục vẫn bị retry như lỗi tạm thời.

**Giả định restart vẫn giữ retained records:** retained records nằm trong memory và mất khi process dừng. Kafka sẽ khôi phục từ committed offset, vì vậy record chưa commit có thể được giao lại.

**Commit offset trước khi xử lý/recovery:** làm mất cơ hội xử lý record nếu process lỗi sau commit.

**Để task nền tiếp tục sau revoke:** có thể gây side effect đồng thời khi partition được giao cho consumer khác.

**Coi recovery log là recovery bền vững:** chỉ log lỗi không đủ nếu nghiệp vụ yêu cầu DLT, lưu trữ hoặc replay.

## 16. Quy trình điều tra khi record liên tục được resubmit

Khi một record liên tục lỗi và được giao lại:

1. Ghi nhận topic, partition, offset, key và event ID.
2. Xác định listener nhận record ở lần đầu và exception/root cause.
3. Kiểm tra `seekAfterError` có được đặt thành false trên đúng container factory hay không.
4. Xác định record được giữ trong memory hay đang được fetch lại sau seek.
5. Kiểm tra BackOff, số lần retry và exception classification.
6. Xác định error handler có chuyển record sang recoverer/DLT sau khi hết retry hay không.
7. Kiểm tra committed offset để xác định group có tiến qua record lỗi không.
8. Theo dõi consumer lag, heap, GC và thời gian listener.
9. Kiểm tra rebalance/restart có xảy ra trong thời gian retry không.
10. Nếu side effect có thể đã thành công trước exception, xác nhận listener có idempotency để tránh duplicate.

Khi record được resubmit, log có thể hiển thị cùng topic/partition/offset nhiều lần. Đây là dấu hiệu retry cùng một record, không tự chứng minh producer đã publish duplicate.

## 17. Kiểm thử retain và resubmit

Nên kiểm thử bằng Kafka test broker hoặc môi trường tích hợp riêng với topic và group ID thử nghiệm.

### 17.1. Kiểm thử record listener

1. Tạo topic có một partition và gửi ba record có offset liên tiếp.
2. Cấu hình `DefaultErrorHandler` với `FixedBackOff` ngắn và `setSeekAfterError(false)`.
3. Cho listener xử lý record đầu thành công.
4. Cho record thứ hai ném exception ở lần đầu và thành công ở lần retry.
5. Ghi lại thứ tự topic/partition/offset được listener nhận.
6. Xác nhận record lỗi được giao lại và record chưa xử lý phía sau tiếp tục được xử lý.
7. Kiểm tra committed offset sau khi các record hoàn tất.

### 17.2. So sánh với seek mode

Chạy cùng kịch bản với `seekAfterError(true)` hoặc giữ mặc định:

1. Ghi nhận số lần poll/fetch và thứ tự record.
2. Quan sát partition seek trong log/debug.
3. So sánh việc container giữ record với việc consumer fetch lại từ broker.
4. Giữ nguyên backoff, batch, concurrency và tải để so sánh có ý nghĩa.

### 17.3. Kiểm thử batch listener

1. Gửi một batch có nhiều record.
2. Cho listener ném `BatchListenerFailedException` tại một index cụ thể.
3. Xác nhận các record trước index được xử lý/commit theo policy.
4. Xác nhận record lỗi và phần chưa xử lý được retry/resubmit.
5. Kiểm tra recovery khi đã hết retry.
6. Xác nhận record được recover không làm offset tiến vượt qua record chưa xử lý khác.

### 17.4. Kiểm thử restart trong lúc retained

1. Tạo một record lỗi và cấu hình backoff đủ dài.
2. Khi container đang chờ retry, dừng process theo cách có kiểm soát.
3. Khởi động lại cùng group ID.
4. Xác nhận record chưa commit được fetch lại từ Kafka.
5. Xác nhận side effect idempotent không bị lặp.

Kiểm thử này chứng minh retained records chỉ là trạng thái trong bộ nhớ. Commit offset mới là tiến độ bền vững được Kafka lưu cho group.

## 18. Nguyên tắc triển khai trong production

- Dùng Spring Kafka 2.9 trở lên nếu cần `setSeekAfterError(false)`.
- Gắn đúng `DefaultErrorHandler` vào listener container factory thực sự được listener sử dụng.
- Chọn BackOff có giới hạn và phân loại exception retryable/non-retryable.
- Dùng retain/resubmit khi muốn giữ record đã fetch trong memory và giao lại qua container.
- Giữ `max.poll.records` và payload size ở mức phù hợp với heap.
- Theo dõi retry, recovery, DLT, consumer lag, listener duration và memory.
- Không coi retained records là lưu trữ bền vững; process restart sẽ làm mất trạng thái giữ trong RAM.
- Để container commit offset sau khi listener/recovery hoàn tất theo acknowledgment mode.
- Bảo vệ side effect bằng event ID, inbox hoặc thao tác idempotent.
- Dùng retry topic hoặc DLT khi cần lịch retry dài, tách workload hoặc quy trình replay độc lập.
- Kiểm thử cả lỗi listener, lỗi recoverer, rebalance và restart trước khi triển khai rộng.

Retain và resubmit cho phép `DefaultErrorHandler` giữ record chưa xử lý trong listener container rồi giao lại sau retry mà không seek partition để fetch lại phần đó. Cơ chế này giúp kiểm soát retry ngay trong container, nhưng phụ thuộc memory và vòng đời consumer. Cần phối hợp BackOff, recovery, acknowledgment mode, idempotency và giám sát để record lỗi không làm nghẽn partition hoặc gây side effect trùng.
