# send callback và CompletableFuture

Trong Spring Kafka, gửi một record là thao tác bất đồng bộ. Ứng dụng gọi KafkaTemplate để chuyển record cho Kafka producer; producer thực hiện serialize, chọn partition, đưa record vào batch và gửi tới broker ở luồng nền. Kết quả gửi có thể thành công hoặc thất bại sau khi phương thức send() đã trả về.

Từ Spring Kafka 3.0, các phương thức send() của KafkaTemplate trả về CompletableFuture<SendResult<K, V>>. Future cho phép ứng dụng đăng ký callback, nối các bước xử lý bất đồng bộ và chuyển lỗi tới tầng gọi mà không phải chặn luồng chỉ để chờ broker phản hồi. Nội dung dưới đây tập trung vào Spring Kafka 3.x trở lên; phần cuối nêu khác biệt với các phiên bản cũ dùng ListenableFuture.

## 1. send() thực sự xác nhận điều gì?

Một lời gọi send() không đồng nghĩa record đã được ghi vào Kafka. Nó khởi động quá trình gửi và trả về một future đại diện cho kết quả. Khi producer hoàn tất thao tác theo cấu hình xác nhận, future được hoàn thành:

- Nếu broker xác nhận theo chính sách acks, future hoàn tất bình thường với một SendResult.
- Nếu gửi thất bại, hết thời hạn giao hàng hoặc producer gặp lỗi, future hoàn tất bất thường với exception.
- Một số lỗi như producer chưa được khởi tạo, record không serialize được hoặc tham số không hợp lệ có thể phát sinh ngay trong lời gọi send(), trước khi ứng dụng nhận được future. Vì vậy, đoạn gọi send() vẫn cần xử lý lỗi đồng bộ.

Mốc thành công phụ thuộc vào cấu hình producer. Với acks=all, broker leader chỉ xác nhận sau khi các replica hiện thuộc ISR đáp ứng điều kiện ghi. Với acks=1, chỉ cần leader xác nhận. Với acks=0, producer không chờ ACK từ broker, do đó future không mang cùng ý nghĩa xác nhận bền vững như hai chế độ còn lại.

Ngay cả khi future thành công, điều đó chỉ cho biết producer đã hoàn tất việc gửi theo chính sách acks. Nó không chứng minh consumer đã đọc record, listener đã chạy hay database nghiệp vụ đã commit. Producer acknowledgment và consumer processing acknowledgment là hai ranh giới khác nhau.

Luồng gửi điển hình:

    Ứng dụng
       |
       | KafkaTemplate.send(record)
       v
    KafkaTemplate / KafkaProducer
       |
       | serialize, partition, batch
       v
    Broker leader ----> ISR replicas
       |
       | ACK hoặc lỗi
       v
    CompletableFuture hoàn tất
       |
       +---- thành công: SendResult
       |
       +---- thất bại: exception

## 2. CompletableFuture và SendResult

CompletableFuture là một đối tượng đại diện cho kết quả có thể xuất hiện trong tương lai. Ngay sau khi gọi send(), ứng dụng có thể tiếp tục làm việc khác. Khi thao tác gửi kết thúc, các callback hoặc stage phụ thuộc sẽ được kích hoạt.

Với Spring Kafka 3.x, kiểu trả về thường gặp là:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", orderId, event);
~~~

Hai kiểu generic trong ví dụ biểu diễn kiểu key và value của record. SendResult chứa ProducerRecord đã gửi và RecordMetadata do broker trả về.

Thông tin metadata hữu ích cho log và theo dõi:

- topic: topic đích.
- partition: partition đã nhận record.
- offset: vị trí của record trong partition.
- timestamp: timestamp được broker ghi nhận theo chế độ timestamp của topic.
- serialized key/value size: kích thước dữ liệu đã serialize, nếu metadata cung cấp.

Ví dụ đọc metadata:

~~~java
SendResult<String, OrderCreated> result = future.join();
RecordMetadata metadata = result.getRecordMetadata();

String topic = metadata.topic();
int partition = metadata.partition();
long offset = metadata.offset();
~~~

Đoạn trên dùng join() để minh họa cách lấy kết quả sau khi future đã hoàn tất. Trong luồng xử lý bất đồng bộ thông thường, nên dùng callback thay vì gọi join() ngay sau send(), bởi gọi join() sẽ chặn luồng hiện tại cho tới khi có kết quả.

## 3. Đăng ký callback với whenComplete()

whenComplete() là cách trực tiếp để quan sát cả hai kết quả: thành công và thất bại. Callback nhận hai tham số:

- result: SendResult nếu thao tác hoàn tất bình thường.
- exception: exception nếu future hoàn tất bất thường; khi thành công, giá trị này là null.

Ví dụ:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Cannot publish eventId={}", event.eventId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
        "Published eventId={} topic={} partition={} offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Callback thành công chỉ nên ghi nhận kết quả gửi và metadata cần thiết. Callback lỗi nên lưu eventId, topic, key và nguyên nhân để có thể điều tra. Không ghi toàn bộ payload nhạy cảm vào log.

whenComplete() trả về một CompletableFuture mới đại diện cho stage có callback. Nếu callback hoàn tất bình thường, stage giữ nguyên kết quả thành công hoặc thất bại của future nguồn. Nếu chính callback ném exception, stage phụ thuộc cũng có thể thất bại. Khi callback chỉ dùng để ghi log hoặc cập nhật metric, tránh để thao tác phụ phát sinh exception làm thay đổi cách tầng gọi quan sát kết quả.

Nếu tầng gọi cần tiếp tục nhận trạng thái gửi, hãy giữ và trả về future gốc hoặc trả về stage phụ thuộc theo chủ đích. Đừng tạo một callback rồi bỏ qua mọi đường truyền lỗi trong khi ứng dụng cần biết việc publish đã thất bại.

## 4. Xử lý lỗi đồng bộ và lỗi bất đồng bộ

Có hai thời điểm cần xử lý exception.

**Lỗi đồng bộ** xảy ra ngay trong lúc gọi send(). Ví dụ producer chưa sẵn sàng, record không serialize được hoặc tham số đầu vào không hợp lệ. Vì chưa nhận được future, callback không thể xử lý lỗi này.

**Lỗi bất đồng bộ** xảy ra sau khi send() trả về future. Ví dụ broker không thể đáp ứng yêu cầu, request hết thời gian hoặc kết nối bị gián đoạn. Những lỗi này làm future hoàn tất bất thường và được truyền tới callback.

Có thể kết hợp try/catch với whenComplete():

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    try {
        CompletableFuture<SendResult<String, OrderCreated>> future =
                kafkaTemplate.send("orders.created", event.orderId(), event);

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Publish failed eventId={}",
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Publish succeeded eventId={} partition={} offset={}",
                event.eventId(),
                metadata.partition(),
                metadata.offset()
            );
        });

        return future;
    }
    catch (RuntimeException exception) {
        log.error(
            "Publish could not be started eventId={}",
            event.eventId(),
            exception
        );

        CompletableFuture<SendResult<String, OrderCreated>> failed =
                new CompletableFuture<>();

        failed.completeExceptionally(exception);
        return failed;
    }
}
~~~

Phương thức trên trả về future cho tầng gọi. Nếu lỗi xảy ra ngay khi khởi động thao tác gửi, nó trả về một future đã hoàn tất bất thường để hợp nhất cách quan sát kết quả. Tầng gọi vẫn phải xử lý trường hợp future thất bại; log trong callback không thay thế xử lý lỗi nghiệp vụ.

Không nên chỉ bắt exception rồi trả về null. Làm vậy khiến caller không phân biệt được publish thất bại, publish chưa bắt đầu hay một giá trị kết quả hợp lệ.

## 5. Các phương thức nối stage thường dùng

CompletableFuture cung cấp nhiều phương thức để nối các bước xử lý. Mỗi phương thức có mục đích riêng.

| Phương thức | Công dụng | Thời điểm phù hợp |
|---|---|---|
| whenComplete | Quan sát kết quả thành công hoặc lỗi và giữ trạng thái hoàn tất | Ghi log, metric, trace |
| thenApply | Biến đổi kết quả thành một giá trị khác | Lấy RecordMetadata hoặc ánh xạ SendResult |
| thenAccept | Nhận kết quả để thực hiện hành động, không trả giá trị | Ghi metric hoặc cập nhật một bộ đếm |
| thenRun | Chạy hành động sau khi stage thành công, không cần kết quả | Thực hiện bước độc lập sau publish |
| exceptionally | Phục hồi khi stage thất bại bằng cách cung cấp giá trị thay thế | Chỉ dùng khi có chiến lược phục hồi rõ ràng |
| handle | Xử lý cả kết quả và exception, rồi tạo kết quả mới | Chuẩn hóa trạng thái thành công/thất bại |
| thenCompose | Nối một thao tác bất đồng bộ khác và làm phẳng future lồng nhau | Gửi event tiếp theo hoặc gọi dịch vụ bất đồng bộ |

### 5.1. thenApply và thenAccept

Dùng thenApply khi cần chuyển SendResult thành metadata hoặc một giá trị khác:

~~~java
CompletableFuture<RecordMetadata> metadataFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .thenApply(SendResult::getRecordMetadata);
~~~

Dùng thenAccept khi chỉ cần nhận kết quả và thực hiện hành động:

~~~java
CompletableFuture<Void> logFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .thenAccept(result -> {
                    RecordMetadata metadata = result.getRecordMetadata();
                    log.info(
                        "Published to {}-{} at offset {}",
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                });
~~~

Nếu stage trước thất bại, thenApply và thenAccept không chạy phần xử lý thành công; lỗi được truyền tiếp sang stage mới. Vì vậy, cần đặt nhánh xử lý lỗi ở đúng vị trí trong chuỗi.

### 5.2. exceptionally và nguy cơ nuốt lỗi

exceptionally() được gọi khi stage trước thất bại. Nó có thể cung cấp một giá trị thay thế để phục hồi stage:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> recovered =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .exceptionally(exception -> {
                    log.error("Publish failed", exception);
                    return null;
                });
~~~

Ví dụ trên biến future thất bại thành future hoàn tất bình thường với giá trị null. Nếu tầng gọi chỉ kiểm tra future có lỗi hay không, nó sẽ tưởng publish đã hoàn tất bình thường. Đây là lỗi thiết kế phổ biến: log exception rồi trả về null đã vô tình nuốt lỗi.

Chỉ dùng exceptionally() để phục hồi khi có giá trị thay thế hợp lệ và caller hiểu ý nghĩa của giá trị đó. Nếu không thể phục hồi, hãy ném lại exception hoặc tạo một future thất bại:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> propagated =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .exceptionally(exception -> {
                    log.error("Publish failed", exception);
                    throw new CompletionException(exception);
                });
~~~

Khi mục tiêu chỉ là quan sát lỗi, whenComplete() thường rõ ràng hơn exceptionally() vì nó không chủ động biến lỗi thành kết quả thành công.

### 5.3. handle để chuẩn hóa kết quả

handle() luôn được gọi khi stage nguồn hoàn tất, dù thành công hay thất bại. Nó phù hợp khi cần ánh xạ hai nhánh thành một kiểu kết quả nghiệp vụ:

~~~java
CompletableFuture<PublishOutcome> outcomeFuture =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .handle((result, exception) -> {
                    if (exception != null) {
                        return PublishOutcome.failed(
                            event.eventId(),
                            exception.getMessage()
                        );
                    }

                    RecordMetadata metadata = result.getRecordMetadata();

                    return PublishOutcome.sent(
                        event.eventId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                });
~~~

PublishOutcome là kiểu dữ liệu do ứng dụng định nghĩa, có thể là record hoặc class. Vì handle() trả về kết quả bình thường ở cả hai nhánh, caller cần kiểm tra trạng thái trong PublishOutcome thay vì chỉ kiểm tra future có exception hay không.

### 5.4. thenCompose để nối nhiều thao tác bất đồng bộ

thenCompose() hữu ích khi bước tiếp theo cũng trả về CompletableFuture. Ví dụ, sau khi gửi event đầu tiên thành công, ứng dụng cần gửi một event tiếp theo:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> first =
        kafkaTemplate.send("orders.created", event.orderId(), event);

CompletableFuture<SendResult<String, OrderAudited>> chain =
        first.thenCompose(result ->
                kafkaTemplate.send(
                    "orders.audit",
                    event.orderId(),
                    OrderAudited.from(event)
                )
        );
~~~

Chuỗi này chỉ gửi event audit sau khi future đầu tiên hoàn tất bình thường. Nếu gửi event đầu tiên thất bại, thenCompose() không chạy và lỗi được truyền tới chain.

Hai lần gửi vẫn là hai thao tác producer độc lập. Nếu yêu cầu nghiệp vụ cần cả hai record cùng được ghi hoặc cùng không được ghi, việc nối future không tạo ra transaction nguyên tử. Hãy dùng Kafka transaction khi cả hai record thuộc cùng một luồng transactional và cần tính nguyên tử trong Kafka.

## 6. Callback chạy trên thread nào?

Các phương thức không có hậu tố Async, chẳng hạn whenComplete(), thenApply() và thenAccept(), có thể chạy trên thread hoàn tất future. Với send của Kafka producer, đó thường là thread xử lý phản hồi của producer. Nếu future đã hoàn tất trước khi callback được đăng ký, callback có thể chạy ngay trên thread đăng ký callback.

Vì vậy, không nên thực hiện công việc nặng trong callback mặc định. Các thao tác như gọi HTTP chậm, truy vấn database, xử lý file lớn hoặc chờ một future khác có thể làm chậm thread xử lý phản hồi và ảnh hưởng đến throughput gửi message.

Khi cần xử lý phụ tốn thời gian, dùng phương thức Async và một Executor có giới hạn:

~~~java
future.whenCompleteAsync((result, exception) -> {
    if (exception != null) {
        failureHandler.record(event.eventId(), exception);
        return;
    }

    auditService.recordPublished(
        event.eventId(),
        result.getRecordMetadata().offset()
    );
}, callbackExecutor);
~~~

callbackExecutor nên được quản lý như một bean hoặc thành phần có vòng đời rõ ràng. Cấu hình số thread và hàng đợi theo tải thực tế; hàng đợi không giới hạn có thể làm bộ nhớ tăng khi callback chậm hơn tốc độ gửi.

Không mặc định dùng ForkJoinPool.commonPool() cho mọi tác vụ nền. Nếu callback gọi dịch vụ blocking hoặc cần giới hạn concurrency, executor riêng giúp kiểm soát tài nguyên và cô lập tải.

Nếu callback async chạy thất bại, stage được trả về bởi whenCompleteAsync() cũng thất bại. Hãy giữ stage đó nếu kết quả callback là một phần của quy trình cần quan sát; nếu chỉ dùng callback để log, bảo đảm callback không ném exception ngoài dự kiến.

## 7. Chờ kết quả bằng get() và join()

CompletableFuture cung cấp hai phương thức chờ phổ biến:

- get() chặn thread cho tới khi có kết quả. Nó có thể ném InterruptedException hoặc ExecutionException; phiên bản get(timeout, unit) còn có TimeoutException.
- join() cũng chặn thread, nhưng thường bọc lỗi bất đồng bộ trong CompletionException thay vì ExecutionException.

Ví dụ chờ có giới hạn:

~~~java
try {
    SendResult<String, OrderCreated> result =
            kafkaTemplate.send("orders.created", event.orderId(), event)
                    .get(10, TimeUnit.SECONDS);

    log.info(
        "Published at offset {}",
        result.getRecordMetadata().offset()
    );
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting for Kafka", exception);
}
catch (ExecutionException | TimeoutException exception) {
    throw new IllegalStateException("Kafka publish did not complete successfully", exception);
}
~~~

Cách chờ đồng bộ có thể hữu ích trong bài kiểm tra tích hợp, tác vụ command-line hoặc một ranh giới xử lý buộc phải trả kết quả ngay. Trong request thread hoặc listener thread có tải cao, chặn chờ từng lần gửi sẽ làm giảm concurrency và throughput. Hãy ưu tiên trả future hoặc nối callback nếu luồng nghiệp vụ cho phép bất đồng bộ.

Timeout của get(timeout, unit) chỉ giới hạn thời gian thread hiện tại chờ kết quả. Nó không đồng nghĩa producer đã hủy request hoặc broker chắc chắn chưa ghi record. Nếu ứng dụng timeout rồi gửi lại ngay, record đầu tiên vẫn có thể được broker ghi sau đó; vì vậy, retry ở tầng ứng dụng có thể tạo duplicate.

Không dùng timeout của thread chờ thay cho delivery.timeout.ms của Kafka producer. delivery.timeout.ms là giới hạn thời gian producer cố gắng giao record; request.timeout.ms điều khiển thời gian chờ phản hồi cho một request. Cần đặt các giá trị phù hợp với SLA và hiểu rằng timeout không chứng minh record chưa được ghi.

## 8. Cấu hình producer để future có ý nghĩa vận hành

Callback chỉ phản ánh kết quả theo cấu hình producer. Với luồng cần độ bền, có thể bắt đầu từ cấu hình sau:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Ý nghĩa:

- acks=all yêu cầu leader chờ các replica trong ISR theo điều kiện ghi của cluster.
- enable.idempotence=true giúp producer tránh ghi trùng do retry ở tầng giao thức trong phạm vi producer session.
- delivery.timeout.ms giới hạn tổng thời gian producer cố gắng gửi record trước khi báo lỗi.
- request.timeout.ms giới hạn thời gian chờ phản hồi của một request.

Cần phối hợp acks=all với replication factor và min.insync.replicas phù hợp ở broker/topic. Nếu cluster không có đủ replica trong ISR, gửi có thể thất bại; future sẽ báo lỗi để ứng dụng và hệ thống giám sát xử lý. Đừng hạ mức xác nhận chỉ để làm callback thành công nhiều hơn nếu điều đó làm giảm mức an toàn dữ liệu cần thiết.

Kafka client có các ràng buộc tương thích giữa idempotence, acks, retries và số request đang bay trên mỗi connection. Không nên tùy ý đặt các giá trị xung đột với yêu cầu của idempotence. Hãy kiểm tra cấu hình producer thực tế và tài liệu đúng phiên bản Kafka client được Spring Kafka sử dụng.

## 9. Retry sau khi future thất bại

Khi future thất bại, trước tiên cần phân loại lỗi và xác định liệu record có thể đã được broker ghi hay chưa.

Một số lỗi cho biết request bị từ chối rõ ràng, ví dụ thiếu quyền hoặc record vượt giới hạn kích thước. Một số lỗi mạng hoặc timeout có trạng thái không chắc chắn: broker có thể đã ghi record nhưng ACK không tới producer. Nếu ứng dụng tạo một lần send mới cho cùng sự kiện, có thể xuất hiện hai record.

Idempotent producer giúp xử lý retry do Kafka producer thực hiện bên trong cùng producer session. Nó không tự khử trùng lặp khi ứng dụng gọi send() mới cho cùng event sau khi future cũ thất bại, cũng không thay thế idempotency của consumer.

Trước khi retry ở tầng ứng dụng, nên cân nhắc:

1. Phân loại exception và xác định lỗi có khả năng tạm thời hay không.
2. Giữ nguyên eventId của sự kiện qua mọi lần gửi.
3. Dùng backoff tăng dần và jitter, đồng thời giới hạn tổng số lần thử.
4. Không retry vô hạn với lỗi dữ liệu, xác thực hoặc cấu hình.
5. Thiết kế consumer idempotent để xử lý an toàn trường hợp record đã được ghi nhưng kết quả gửi không tới ứng dụng.
6. Ghi nhận lần thử, nguyên nhân và trạng thái cuối cùng để điều tra.

Không nên tự retry ngay trong callback bằng cách gọi send() đệ quy hoặc tạo vòng lặp không giới hạn. Cách này có thể tạo tải tăng đột biến, giữ nhiều future và che giấu lỗi cấu hình. Nên giao retry cho một thành phần có giới hạn rõ ràng hoặc dùng Transactional Outbox khi event cần được phát bền vững cùng thay đổi database.

### 9.1. Outbox cho sự kiện cần phát bền vững

Nếu ứng dụng cập nhật database rồi mới gửi Kafka, có một khoảng lỗi giữa commit database và lúc broker nhận record. Callback chỉ báo kết quả của lần gửi Kafka; nó không làm hai hệ thống trở thành một transaction.

Transactional Outbox xử lý khoảng lỗi này bằng cách ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database. Một relay đọc outbox và gửi record sang Kafka. Nếu relay dừng sau khi Kafka ghi record nhưng trước khi đánh dấu outbox đã gửi, relay có thể gửi lại sau khi khởi động. Vì vậy, eventId cần ổn định và consumer cần idempotent.

Callback từ KafkaTemplate có thể giúp relay biết lần gửi nào đã được xác nhận để cập nhật trạng thái outbox. Tuy nhiên, cập nhật trạng thái outbox cũng cần xử lý lỗi database và khả năng relay gửi lại.

## 10. Callback trong Kafka transaction

Khi dùng Kafka transaction, một lần send có thể được broker xác nhận ở cấp record trước khi transaction được commit. Consumer dùng isolation.level=read_committed sẽ chỉ nhìn thấy các record thuộc transaction đã commit.

Do đó, future của send thành công không đồng nghĩa transaction chứa record đã commit. Ứng dụng phải theo dõi kết quả hoàn tất của transaction, bao gồm commit hoặc abort, theo cách Spring Kafka quản lý transaction.

Ví dụ khái niệm:

    Bắt đầu Kafka transaction
       |
       v
    Gửi record A ----> send future hoàn tất
       |
       v
    Gửi record B ----> send future hoàn tất
       |
       v
    Commit transaction
       |
       +---- thành công: record được hiển thị cho read_committed consumer
       |
       +---- thất bại/abort: record không được xem là dữ liệu đã commit

Không dùng callback send thành công để đánh dấu toàn bộ quy trình transactional đã hoàn tất. Hãy đặt cập nhật trạng thái nghiệp vụ sau khi transaction commit thành công hoặc dùng cơ chế transaction synchronization phù hợp với cấu hình Spring Kafka.

Kafka transaction có thể kết hợp record đầu ra với offset consumer trong một transaction Kafka. Nó không tự bao trùm database, HTTP API hay email. Side effect bên ngoài vẫn cần outbox, inbox hoặc cơ chế idempotency riêng.

## 11. Ví dụ publisher hoàn chỉnh

Ví dụ sau minh họa một service gửi event, đăng ký callback để ghi metadata và trả future cho tầng gọi. Ví dụ giả định ứng dụng đã cấu hình KafkaTemplate với serializer tương ứng cho OrderCreated.

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private static final String TOPIC = "orders.created";

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        ProducerRecord<String, OrderCreated> record =
                new ProducerRecord<>(TOPIC, event.orderId(), event);

        record.headers().add(
                "event-id",
                event.eventId().getBytes(StandardCharsets.UTF_8)
        );

        final CompletableFuture<SendResult<String, OrderCreated>> future;

        try {
            future = kafkaTemplate.send(record);
        }
        catch (RuntimeException exception) {
            log.error(
                "Could not start publish for eventId={}",
                event.eventId(),
                exception
            );

            CompletableFuture<SendResult<String, OrderCreated>> failed =
                    new CompletableFuture<>();

            failed.completeExceptionally(exception);
            return failed;
        }

        future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed eventId={} topic={}",
                    event.eventId(),
                    TOPIC,
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Kafka send acknowledged eventId={} topic={} partition={} offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });

        return future;
    }
}
~~~

Các import chính:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;
~~~

Caller có thể nối xử lý sau khi publish:

~~~java
publisher.publish(event)
        .thenAccept(result -> {
            RecordMetadata metadata = result.getRecordMetadata();
            metrics.recordPublishSuccess(metadata.topic());
        })
        .exceptionally(exception -> {
            metrics.recordPublishFailure();
            return null;
        });
~~~

Trong ví dụ caller, exceptionally() biến stage thành hoàn tất bình thường sau khi ghi metric. Nếu tầng gọi cần báo lỗi cho người dùng hoặc chuyển event sang outbox, không nên nuốt lỗi như vậy; hãy truyền exception tiếp hoặc trả về một kiểu kết quả thể hiện rõ trạng thái thất bại.

## 12. Kiểm thử và quan sát kết quả gửi

Trong kiểm thử tích hợp, có thể chờ future với timeout hữu hạn để xác nhận producer đã nhận ACK và kiểm tra metadata:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders.created", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

assertThat(result.getRecordMetadata().topic())
        .isEqualTo("orders.created");
~~~

Đây là cách chờ đồng bộ phù hợp trong test. Trong ứng dụng production, không sao chép cách chờ này vào mọi request hoặc listener nếu không có lý do rõ ràng.

Nên theo dõi các tín hiệu sau:

- Số lượng send thành công và thất bại.
- Tỷ lệ future hoàn tất bất thường theo exception class.
- Độ trễ từ lúc gọi send() tới khi future hoàn tất.
- Số lần timeout, retry và lỗi serialize.
- Số lượng record gửi theo topic và partition.
- Số event outbox đang chờ gửi hoặc bị lỗi lâu.
- Sự chênh lệch giữa event ứng dụng dự kiến phát và record producer đã xác nhận.

Log và trace nên chứa eventId, topic, key, partition, offset và correlation ID khi có. Không dùng offset như event ID nghiệp vụ vì offset chỉ định vị một record trong một partition.

Callback là điểm thuận tiện để đo thời gian gửi và ghi nhận metadata, nhưng không phải bằng chứng consumer đã xử lý. Muốn quan sát end-to-end, cần thêm metric ở consumer và đối chiếu với kết quả nghiệp vụ.

## 13. Các lỗi triển khai thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Gọi send() rồi giả định đã gửi thành công | Future có thể hoàn tất bất thường sau đó | Đăng ký callback hoặc truyền future cho caller |
| Chỉ bắt lỗi trong whenComplete() | Lỗi đồng bộ trước khi future được tạo không đi qua callback | Bọc lời gọi send() bằng try/catch |
| Gọi get() hoặc join() ngay sau send() | Chặn thread và làm giảm throughput | Nối stage hoặc xử lý bất đồng bộ |
| Gọi dịch vụ blocking trong callback mặc định | Có thể làm chậm thread xử lý phản hồi producer | Dùng whenCompleteAsync() với executor có giới hạn |
| Dùng exceptionally() rồi trả null | Biến lỗi thành kết quả hoàn tất bình thường | Chỉ phục hồi khi có kết quả thay thế hợp lệ |
| Retry ngay khi timeout | Lần gửi đầu có thể đã được broker ghi | Giữ eventId và thiết kế consumer idempotent |
| Coi send future thành công là consumer đã xử lý | Producer ACK không phải consumer ACK | Theo dõi riêng consumer và kết quả nghiệp vụ |
| Coi send future thành công là Kafka transaction đã commit | Record có thể vẫn thuộc transaction chưa commit | Theo dõi kết quả transaction |
| Bỏ qua lỗi trong callback | Không có dấu vết để điều tra | Ghi log có eventId và phát metric/cảnh báo |
| Không giới hạn executor callback | Callback chậm có thể làm hàng đợi tăng vô hạn | Đặt giới hạn thread, queue và chính sách từ chối |

## 14. Khác biệt giữa Spring Kafka 2.x và 3.x

Các ví dụ trong bài sử dụng API CompletableFuture của Spring Kafka 3.0 trở lên. Trong những phiên bản Spring Kafka cũ, KafkaTemplate.send() trả về ListenableFuture<SendResult<K, V>>. Ứng dụng đăng ký callback bằng addCallback() thay vì whenComplete():

~~~java
ListenableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.addCallback(
    result -> log.info("Publish succeeded"),
    exception -> log.error("Publish failed", exception)
);
~~~

Khi nâng cấp lên Spring Kafka 3.x, kiểu trả về thay đổi sang CompletableFuture. Hãy kiểm tra import, kiểu biến, callback và các đoạn code dùng addCallback() khi nâng cấp. Không thể gọi trực tiếp whenComplete() trên ListenableFuture của phiên bản cũ nếu chưa chuyển đổi hoặc thay đổi API.

Cấu hình, cách quản lý transaction và các API hỗ trợ khác cũng phụ thuộc phiên bản Spring Kafka. Luôn đối chiếu dependency thực tế của ứng dụng trước khi áp dụng ví dụ.

## 15. Nguyên tắc sử dụng trong hệ thống production

- Xem future là kết quả của thao tác gửi theo cấu hình acks; không xem nó là xác nhận xử lý end-to-end.
- Xử lý cả exception đồng bộ từ lời gọi send() và exception bất đồng bộ từ future.
- Dùng whenComplete() để quan sát cả thành công và thất bại; dùng các stage khác khi cần biến đổi hoặc nối công việc.
- Giữ callback mặc định ngắn. Chuyển công việc nặng sang executor có giới hạn.
- Hạn chế get() và join() trong luồng phục vụ request hoặc consumer có tải cao.
- Cấu hình acks, idempotence và delivery timeout theo yêu cầu độ bền.
- Không retry mù khi timeout; một lần gửi có thể đã được broker ghi dù ứng dụng chưa nhận ACK.
- Giữ eventId ổn định, kết hợp consumer idempotency hoặc outbox để kiểm soát duplicate.
- Với Kafka transaction, phân biệt send future hoàn tất với transaction commit.
- Ghi log và metric đủ để nối event ở producer với record và consumer về sau.

CompletableFuture giúp ứng dụng xử lý kết quả gửi Kafka mà không phải chặn luồng chờ broker. Độ tin cậy vẫn phụ thuộc vào cách producer xác nhận, cách ứng dụng truyền lỗi, chính sách retry và khả năng consumer xử lý lặp an toàn. Khi các ranh giới này được thiết kế rõ ràng, callback trở thành một phần quan sát và điều phối đáng tin cậy trong quy trình phát event.