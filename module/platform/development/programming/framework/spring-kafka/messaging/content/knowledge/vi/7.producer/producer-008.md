# Callback khi send hoàn tất

Khi producer gửi một record bằng **KafkaTemplate**, thao tác gửi thường diễn ra bất đồng bộ. Ứng dụng không cần dừng luồng hiện tại để chờ broker trả kết quả; thay vào đó, nó nhận một đối tượng future và đăng ký callback để xử lý khi thao tác gửi thành công hoặc thất bại.

Callback giúp producer ghi nhận kết quả gửi, lấy metadata của record, cập nhật metric, ghi log phục vụ truy vết và phản ứng với lỗi. Đây là một phần quan trọng khi xây dựng luồng messaging bằng Spring Kafka: gửi sự kiện không chỉ là gọi send, mà còn phải biết broker đã xác nhận điều gì và ứng dụng cần làm gì khi kết quả không như mong đợi.

Bài học thuộc chương **Producer** của module **SPRING_KAFKA_MESSAGING**, tập trung vào callback của KafkaTemplate, cách đọc SendResult và RecordMetadata, xử lý lỗi bất đồng bộ, tổ chức retry an toàn và kiểm thử kết quả gửi.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vì sao KafkaTemplate gửi record bất đồng bộ và callback được gọi khi nào.
- Dùng CompletableFuture và whenComplete trong Spring Kafka 3.x.
- Đọc topic, partition, offset và timestamp từ SendResult.
- Phân biệt lỗi xảy ra ngay trong lời gọi send với lỗi hoàn tất bất đồng bộ.
- Ghi log và metric trong callback mà không làm chậm producer I/O.
- Hiểu quan hệ giữa callback, acks, retries và idempotence.
- Tránh retry mù gây phát sinh sự kiện trùng.
- Kiểm thử cả nhánh gửi thành công và thất bại.
- Phân biệt broker đã xác nhận record với consumer đã xử lý nghiệp vụ.

## 1. Vòng đời của một lần gửi

KafkaTemplate là abstraction của Spring Kafka để gửi record. Khi gọi send, template chuyển record tới Kafka producer. Producer thực hiện serialization, chọn partition, đưa record vào bộ đệm và gửi theo cơ chế batch/network của Kafka client.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Spring Service
    participant KT as KafkaTemplate
    participant KP as Kafka Producer
    participant Broker as Kafka Broker
    App->>KT: send(topic, key, value)
    KT->>KP: Tạo và gửi ProducerRecord
    KT-->>App: CompletableFuture
    KP->>Broker: Produce request
    Broker-->>KP: Produce response
    KP-->>App: Hoàn tất future
    App->>App: Callback success hoặc failure
~~~

Các bước chính:

1. Ứng dụng gọi KafkaTemplate.send với topic, key và value.
2. KafkaTemplate trả về future để ứng dụng theo dõi kết quả.
3. Kafka producer serialize key/value và xác định partition.
4. Producer gửi record tới broker quản lý partition leader.
5. Broker trả kết quả theo cấu hình acknowledgement của producer.
6. Future hoàn tất; callback nhận SendResult hoặc exception.

Việc gọi send và việc gửi hoàn tất là hai thời điểm khác nhau. Nếu ứng dụng gọi get trên future ngay sau send, luồng hiện tại sẽ bị chặn cho tới khi có kết quả hoặc timeout. Nếu đăng ký callback, ứng dụng có thể tiếp tục làm công việc khác trong lúc producer xử lý gửi record.

Callback thường được dùng cho thao tác hậu xử lý nhẹ: ghi metadata, cập nhật bộ đếm, ghi log hoặc chuyển kết quả tới một thành phần điều phối khác.

## 2. CompletableFuture trong Spring Kafka 3.x

Từ Spring Kafka 3.0, các phương thức send của KafkaTemplate trả về CompletableFuture<SendResult<K, V>>. Có thể dùng whenComplete để đăng ký một hành động chạy khi future hoàn tất, bất kể thành công hay thất bại.

Ví dụ publisher đơn giản:

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send(
                        "orders.created",
                        event.orderId(),
                        event
                );

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Cannot publish order eventId={}, orderId={}",
                        event.eventId(),
                        event.orderId(),
                        exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                    "Published eventId={}, topic={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    }
}
~~~

Ở ví dụ trên:

- KafkaTemplate gửi OrderCreatedEvent vào topic orders.created.
- orderId được dùng làm key để các record cùng đơn hàng thường đi vào cùng partition theo partitioner mặc định.
- whenComplete nhận hai tham số: result và exception.
- Khi thành công, SendResult cung cấp metadata từ broker.
- Khi thất bại, exception mô tả nguyên nhân mà producer không thể hoàn tất gửi theo cấu hình hiện tại.

Để biên dịch ví dụ, cần import các kiểu tương ứng như CompletableFuture, SendResult, RecordMetadata và Logger. Ví dụ dùng API Spring Kafka 3.x; hãy kiểm tra phiên bản dependency của dự án trước khi áp dụng.

## 3. Đọc SendResult và RecordMetadata

SendResult chứa ProducerRecord đã gửi và RecordMetadata do broker trả về. Metadata giúp ứng dụng xác định record đã được ghi vào đâu.

Một số trường thường dùng:

| Trường | Ý nghĩa |
|---|---|
| topic() | Tên topic nhận record. |
| partition() | Partition mà record được ghi vào. |
| offset() | Vị trí record trong partition đó. |
| timestamp() | Timestamp của record theo metadata trả về. |
| serializedKeySize() | Kích thước key sau serialization. |
| serializedValueSize() | Kích thước value sau serialization. |

Ví dụ ghi log đầy đủ hơn:

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Kafka send failed for eventId={}", event.eventId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
            "Kafka send acknowledged: eventId={}, topic={}, partition={}, " +
            "offset={}, timestamp={}, keySize={}, valueSize={}",
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            metadata.timestamp(),
            metadata.serializedKeySize(),
            metadata.serializedValueSize()
    );
});
~~~

Offset chỉ có ý nghĩa trong một partition. Không so sánh offset của hai partition như thể chúng thuộc cùng một dãy số toàn cục. Nếu cần truy vết một event, hãy kết hợp eventId với topic, partition và offset.

RecordMetadata hữu ích khi điều tra lỗi, đo lưu lượng và đối chiếu log producer với log consumer. Không nên ghi toàn bộ payload vào log chỉ để theo dõi kết quả gửi; eventId và metadata thường đủ để tìm record trong hệ thống.

## 4. Xử lý cả lỗi đồng bộ và lỗi bất đồng bộ

Không phải mọi lỗi đều xuất hiện trong callback. Một số lỗi có thể phát sinh ngay trong lời gọi send, ví dụ cấu hình producer không hợp lệ, lỗi serialization xảy ra trước khi request được gửi hoặc lỗi sử dụng API. Các lỗi khác được thể hiện khi future hoàn tất bất thường, chẳng hạn timeout, broker không khả dụng hoặc lỗi gửi sau các lần retry nội bộ.

Vì vậy, nếu publisher cần kiểm soát cả hai tình huống, hãy đặt lời gọi send trong try/catch và vẫn đăng ký callback cho future:

~~~java
public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
        OrderCreatedEvent event) {

    try {
        CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
                kafkaTemplate.send(
                        "orders.created",
                        event.orderId(),
                        event
                );

        return future.whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Asynchronous send failed, eventId={}",
                        event.eventId(),
                        exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                    "Send completed, eventId={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.partition(),
                    metadata.offset()
            );
        });
    } catch (RuntimeException exception) {
        log.error(
                "Send could not be started, eventId={}",
                event.eventId(),
                exception
        );
        throw exception;
    }
}
~~~

Cần hiểu hai đường lỗi:

- **Lỗi đồng bộ:** phương thức send không thể bắt đầu hoặc chuẩn bị record; exception được ném ngay trong lời gọi.
- **Lỗi bất đồng bộ:** producer đã nhận thao tác gửi nhưng future hoàn tất với exception sau đó.

Nếu publisher bắt lỗi đồng bộ rồi trả về null, caller sẽ khó phân biệt lỗi với một kết quả hợp lệ. Hãy giữ hợp đồng trả về nhất quán: ném lỗi đồng bộ để caller xử lý hoặc chuyển đổi thành một kết quả lỗi có kiểu rõ ràng. Không âm thầm bỏ qua lỗi.

Trong thực tế, exception có thể được bọc bởi CompletionException hoặc ExecutionException tùy cách future được quan sát. Khi cần phân loại lỗi, hãy lấy nguyên nhân gốc một cách an toàn và ghi nhận cả context của event.

## 5. whenComplete, thenAccept và exceptionally

CompletableFuture cung cấp nhiều cách nối các bước xử lý. Hãy chọn theo mục đích của callback.

| API | Khi nào chạy | Mục đích |
|---|---|---|
| whenComplete | Khi future thành công hoặc thất bại | Quan sát kết quả, ghi log hoặc metric mà vẫn giữ kết quả/exception gốc nếu callback không ném lỗi. |
| thenAccept | Khi future thành công | Xử lý SendResult khi không cần trả về giá trị mới. |
| thenApply | Khi future thành công | Chuyển SendResult thành một giá trị khác. |
| exceptionally | Khi future thất bại | Chuyển exception thành một giá trị thay thế hoặc thực hiện fallback. |
| handle | Khi future thành công hoặc thất bại | Biến cả kết quả và exception thành một kết quả mới. |

Ví dụ chỉ xử lý thành công:

~~~java
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

Ví dụ xử lý lỗi và trả về kết quả thay thế:

~~~java
CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

CompletableFuture<SendResult<String, OrderCreatedEvent>> recovered =
        future.exceptionally(exception -> {
            log.error("Send failed for eventId={}", event.eventId(), exception);
            return null;
        });
~~~

Ví dụ exceptionally ở trên chỉ minh họa cơ chế phục hồi của CompletableFuture. Trả về null làm mất thông tin kiểu về thất bại và buộc caller phải kiểm tra null. Trong ứng dụng nghiệp vụ, nên dùng một kiểu kết quả rõ ràng hoặc để future tiếp tục thất bại để caller quyết định.

Khi chỉ cần quan sát kết quả gửi mà không muốn biến đổi kết quả, whenComplete thường phù hợp. Nếu muốn chuyển lỗi thành một kết quả nghiệp vụ, hãy thiết kế kiểu kết quả riêng thay vì che giấu lỗi bằng null.

## 6. Callback chạy trên thread nào?

Callback không nên được xem như một phần của request thread đang gọi publisher. Future thường được hoàn tất bởi luồng xử lý kết quả của producer; callback đồng bộ như whenComplete có thể chạy trên luồng hoàn tất future.

Vì vậy, callback nên thực hiện công việc ngắn và không chặn:

- Ghi log có cấu trúc.
- Cập nhật counter hoặc timer metric.
- Ghi nhận topic, partition và offset.
- Phát tín hiệu tới một hàng đợi nội bộ có giới hạn.
- Hoàn tất một future khác hoặc thông báo cho thành phần điều phối.

Tránh các việc sau trong callback đồng bộ:

- Gọi HTTP chậm hoặc truy vấn database đồng bộ.
- Dùng Thread.sleep.
- Chờ một future khác bằng get hoặc join.
- Thực hiện retry vòng lặp không giới hạn.
- Ghi file hoặc xử lý payload lớn kéo dài.

Nếu hậu xử lý tốn thời gian, có thể dùng whenCompleteAsync với một Executor được quản lý bởi ứng dụng:

~~~java
future.whenCompleteAsync((result, exception) -> {
    if (exception != null) {
        failureHandler.record(event.eventId(), exception);
        return;
    }

    successHandler.record(
            event.eventId(),
            result.getRecordMetadata()
    );
}, callbackExecutor);
~~~

Executor cần có giới hạn thread và queue phù hợp, chính sách từ chối tác vụ rõ ràng và vòng đời được quản lý bởi Spring. Nếu queue đầy, ứng dụng cần có metric và cách xử lý; không nên tạo thread mới vô hạn để chạy callback.

Đừng dùng executor tùy tiện chỉ để đổi thread. Việc chuyển callback sang executor không làm cho gửi Kafka nhanh hơn; nó chỉ tách công việc hậu xử lý khỏi luồng hoàn tất send.

## 7. Callback thành công có nghĩa là gì?

Callback thành công có nghĩa producer nhận được kết quả thành công theo cấu hình acknowledgement của nó. Mức xác nhận phụ thuộc vào thuộc tính acks:

| acks | Ý nghĩa khái quát |
|---|---|
| 0 | Producer không chờ broker xác nhận. Kết quả hoàn tất không chứng minh broker đã ghi record. |
| 1 | Leader xác nhận record đã được ghi vào log cục bộ của leader. |
| all | Leader chờ các replica trong ISR đáp ứng điều kiện xác nhận theo cấu hình cluster, bao gồm min.insync.replicas. |

Với sự kiện nghiệp vụ quan trọng, thường cần đánh giá acks=all kết hợp replication factor và min.insync.replicas phù hợp. Cấu hình này tăng mức bảo vệ dữ liệu nhưng có thể làm lần gửi thất bại khi ISR không đáp ứng điều kiện.

Dù callback thành công, nó không có nghĩa:

- Consumer đã poll record.
- Listener đã xử lý thành công.
- Database của consumer đã commit.
- Một dịch vụ downstream đã hoàn tất nghiệp vụ.
- Toàn bộ transaction phân tán đã hoàn tất.

Callback phản ánh kết quả gửi của producer ở ranh giới Kafka. Nếu cần biết kết quả xử lý ở phía consumer, cần thiết kế phản hồi nghiệp vụ riêng, ví dụ event kết quả, trạng thái xử lý hoặc một API truy vấn.

## 8. Retry của producer và retry của ứng dụng

Kafka producer có cơ chế retry nội bộ. Các cấu hình như retries, delivery.timeout.ms, request.timeout.ms và reconnect backoff ảnh hưởng thời gian producer thử gửi lại trước khi future hoàn tất.

Khi producer được cấu hình idempotence phù hợp, Kafka có thể tránh ghi trùng do retry nội bộ của cùng producer session theo các bảo đảm của idempotent producer. Spring Kafka và Kafka client hiện đại có thể bật idempotence theo mặc định trong nhiều cấu hình tương thích; hãy kiểm tra cấu hình hiệu lực và phiên bản đang dùng.

Không nên mặc định rằng callback thất bại thì có thể gọi send lại ngay lập tức. Một số lỗi như timeout có thể tạo ra trạng thái không chắc chắn: client không nhận được xác nhận nhưng broker có thể đã ghi record. Nếu ứng dụng gửi lại cùng sự kiện, record trùng có thể xuất hiện.

Một chiến lược an toàn cần cân nhắc:

1. Gán eventId ổn định cho mỗi sự kiện nghiệp vụ.
2. Dùng producer idempotence để bảo vệ retry nội bộ trong phạm vi Kafka hỗ trợ.
3. Nếu ứng dụng cần retry sau khi future thất bại, giữ nguyên eventId và payload của sự kiện gốc.
4. Để consumer xử lý lặp an toàn bằng inbox, unique constraint hoặc idempotency key.
5. Với dữ liệu được ghi vào database rồi phát Kafka, cân nhắc outbox pattern để tránh mất event giữa hai thao tác.

Ví dụ callback chỉ ghi nhận thất bại và chuyển event vào một hàng đợi retry có kiểm soát:

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        retryQueue.submit(new FailedPublish(
                event.eventId(),
                event,
                exception
        ));
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    metrics.recordPublished(metadata.topic());
});
~~~

retryQueue ở đây là thành phần minh họa. Trong ứng dụng thật, queue phải có giới hạn, chính sách backoff, số lần thử tối đa, lưu bền nếu cần và cơ chế xử lý khi queue đầy. Nếu không, lỗi Kafka có thể khiến bộ nhớ ứng dụng tăng không kiểm soát.

Không retry vô hạn trong callback. Khi vượt ngưỡng, cần lưu trạng thái lỗi để vận hành hoặc chuyển sang luồng xử lý riêng. Retry producer cũng khác retry consumer: producer retry việc ghi record; consumer retry việc xử lý record đã đọc.

## 9. Kết hợp callback với transaction

Trong luồng gửi bình thường, future hoàn tất khi producer nhận kết quả gửi theo cấu hình acks. Nếu gửi record trong một Kafka transaction, việc một send được broker xác nhận chưa đồng nghĩa transaction đã commit.

Ví dụ transaction có thể gửi nhiều record rồi commit hoặc abort toàn bộ. Ứng dụng phải quan sát kết quả của transaction ở cấp transaction boundary, không chỉ dựa vào callback của từng send.

Một quy trình consume-transform-produce có thể:

1. Nhận record đầu vào.
2. Bắt đầu transaction.
3. Gửi một hoặc nhiều record đầu ra.
4. Commit offset đầu vào cùng transaction theo cấu hình Spring Kafka.
5. Commit transaction.

Nếu transaction abort, record đầu ra không được hiển thị cho consumer dùng isolation.level=read_committed. Vì vậy, không dùng log "send callback success" như bằng chứng rằng toàn bộ transaction đã commit. Hãy ghi nhận riêng trạng thái commit/abort của transaction.

Kafka transaction cũng không tự bao phủ database hoặc API bên ngoài. Nếu nghiệp vụ có cập nhật database, cần idempotency hoặc outbox/inbox để bảo đảm nhất quán qua các ranh giới đó.

## 10. Kiểm thử callback gửi thành công và thất bại

Kiểm thử callback nên xác minh cả kết quả gửi và hành động hậu xử lý. Unit test với mock KafkaTemplate hữu ích để kiểm tra cách publisher phản ứng với future thành công hoặc thất bại; integration test với broker thật xác minh serialization, network, metadata và acknowledgement.

Ví dụ kiểm tra gửi thành công trong integration test:

~~~java
@Test
void shouldPublishEventAndReceiveMetadata() throws Exception {
    OrderCreatedEvent event = new OrderCreatedEvent(
            "evt-1001",
            "order-1001",
            Instant.now(),
            new BigDecimal("125.50")
    );

    SendResult<String, OrderCreatedEvent> result =
            kafkaTemplate.send(
                    "orders.created",
                    event.orderId(),
                    event
            ).get(10, TimeUnit.SECONDS);

    RecordMetadata metadata = result.getRecordMetadata();

    assertThat(metadata.topic()).isEqualTo("orders.created");
    assertThat(metadata.partition()).isGreaterThanOrEqualTo(0);
    assertThat(metadata.offset()).isGreaterThanOrEqualTo(0);
}
~~~

Test này chờ future hoàn tất vì đây là mã kiểm thử; trong luồng xử lý production, không nên chặn bằng get nếu không có lý do rõ ràng. Broker và topic phải được khởi tạo trong test context, chẳng hạn bằng EmbeddedKafka hoặc Testcontainers.

Để kiểm thử callback, có thể đăng ký whenComplete và dùng Awaitility hoặc CompletableFuture phụ để đợi tín hiệu callback. Không dùng Thread.sleep cố định để đoán lúc callback đã chạy.

Các tình huống nên có:

- Gửi thành công và callback nhận được RecordMetadata.
- Broker không sẵn sàng hoặc producer timeout và callback nhận exception.
- Serialization lỗi trước khi gửi và publisher xử lý được lỗi đồng bộ.
- Callback ghi metric hoặc log đúng eventId.
- Callback không chặn luồng producer bằng I/O chậm.
- Retry có giới hạn và không tạo tác động nghiệp vụ trùng.
- Transaction abort không bị ghi nhận nhầm là transaction đã commit.

## 11. Theo dõi kết quả gửi trong production

Callback là nơi thuận tiện để cập nhật một số metric producer, nhưng cần chọn chỉ số có ý nghĩa:

- Số lần gửi thành công và thất bại.
- Thời gian từ lúc gọi send đến lúc future hoàn tất.
- Số lỗi theo loại exception.
- Tỷ lệ timeout hoặc lỗi broker.
- Số tác vụ hậu xử lý callback bị từ chối bởi executor.
- Số event đang chờ retry và số event vượt ngưỡng retry.

Log nên có eventId, topic, key nghiệp vụ phù hợp, partition và offset khi thành công. Với lỗi, ghi exception và context đủ để tìm nguyên nhân. Tránh log payload nhạy cảm hoặc credential.

Nếu cần đo latency, hãy ghi nhận thời điểm bắt đầu gửi và thời điểm callback hoàn tất. Đây là thời gian end-to-end của thao tác producer ở phía client, chịu ảnh hưởng của serialization, batching, network, broker và acknowledgement. Nó không phải thời gian consumer xử lý.

Metric cần có tag giới hạn cardinality. Không dùng eventId hoặc orderId làm label metric vì số lượng giá trị có thể tăng rất lớn. Các ID này phù hợp với log hoặc trace.

## 12. Phiên bản Spring Kafka cũ

Ví dụ chính của bài học dùng CompletableFuture, phù hợp với Spring Kafka 3.0 trở lên. Ở các phiên bản Spring Kafka 2.x, KafkaTemplate.send trả về ListenableFuture và cách đăng ký callback thường dùng addCallback.

Ví dụ theo API cũ:

~~~java
ListenableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.addCallback(
        result -> {
            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                    "Published to {} partition {} offset {}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
        },
        exception -> log.error("Kafka send failed", exception)
);
~~~

Không trộn hai kiểu API trong cùng ví dụ. Khi nâng cấp Spring Kafka 2.x lên 3.x, hãy cập nhật cách xử lý future và kiểm tra các đoạn code đang dùng ListenableFuture.

## 13. Bài tập tổng hợp: publisher có callback và retry an toàn

Hãy xây dựng OrderEventPublisher gửi OrderCreatedEvent tới topic orders.created.

Yêu cầu:

1. Dùng KafkaTemplate<String, OrderCreatedEvent> để gửi event với orderId làm key.
2. Trả về CompletableFuture<SendResult<String, OrderCreatedEvent>> cho caller.
3. Đăng ký whenComplete để xử lý cả success và failure.
4. Khi thành công, ghi eventId, topic, partition, offset và thời gian hoàn tất.
5. Khi thất bại, ghi exception và chuyển thông tin tới thành phần retry có giới hạn.
6. Bắt lỗi đồng bộ có thể phát sinh ngay trong lời gọi send.
7. Cấu hình producer acknowledgement và idempotence theo yêu cầu độ bền.
8. Viết integration test xác minh metadata sau khi gửi thành công.
9. Viết test lỗi để xác minh callback nhận exception và retry không chạy vô hạn.
10. Thêm consumer có idempotency để chứng minh gửi lại cùng eventId không lặp tác động nghiệp vụ.
11. Nếu bật Kafka transaction, kiểm tra riêng send acknowledgment và transaction commit/abort.
12. Theo dõi metric gửi thành công, thất bại và thời gian hoàn tất.

Bài tập hoàn thành khi publisher có thể gửi bất đồng bộ, trả kết quả rõ ràng, quan sát được metadata, xử lý được lỗi đồng bộ và bất đồng bộ, đồng thời có chính sách retry không tạo vòng lặp hoặc tác động trùng.

## 14. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Send lifecycle | KafkaTemplate và producer | Mô tả được từ lời gọi send tới kết quả broker. |
| 2. Future | CompletableFuture và whenComplete | Đăng ký callback thành công/thất bại đúng cách. |
| 3. Metadata | SendResult và RecordMetadata | Đọc được topic, partition, offset và timestamp. |
| 4. Error handling | Lỗi đồng bộ và bất đồng bộ | Phân biệt và xử lý được cả hai đường lỗi. |
| 5. Threading | whenCompleteAsync và Executor | Không chặn luồng hoàn tất producer bằng tác vụ chậm. |
| 6. Acknowledgement | acks, retries, idempotence | Giải thích được mức xác nhận mà callback success thể hiện. |
| 7. Reliability | Retry, eventId, idempotency, outbox | Retry có giới hạn và consumer chịu được record trùng. |
| 8. Transaction | Send result và commit/abort | Không nhầm send acknowledgment với transaction commit. |
| 9. Testing/Monitoring | Integration test, metric, log | Có kiểm thử success/failure và theo dõi được kết quả gửi. |

Bài học hoàn thành khi bạn có thể dùng callback của KafkaTemplate để quan sát kết quả gửi, đọc metadata, xử lý lỗi mà không chặn producer, và giải thích rõ giới hạn của acknowledgement. Callback giúp ứng dụng biết kết quả ở phía producer; tính tin cậy của toàn luồng còn phụ thuộc vào acks, retry, idempotence, transaction và khả năng xử lý lặp an toàn của consumer.

