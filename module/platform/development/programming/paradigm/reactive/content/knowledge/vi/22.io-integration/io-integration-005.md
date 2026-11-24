# Kết nối hàng đợi thông điệp và kiểm soát tốc độ tiêu thụ

Hàng đợi thông điệp giúp các dịch vụ trao đổi dữ liệu mà không cần chạy cùng thời điểm. Producer ghi thông điệp vào broker; consumer nhận và xử lý chúng khi có khả năng. Trong ứng dụng reactive, consumer thường biểu diễn nguồn thông điệp thành `Flux`, sau đó kết hợp xử lý nghiệp vụ, kiểm soát concurrency, xác nhận thông điệp và xử lý lỗi trong cùng một pipeline.

Tuy nhiên, backpressure của Reactive Streams và cơ chế điều tiết của broker là hai lớp liên quan nhưng khác nhau. `request(n)` biểu thị demand tại ranh giới publisher/subscriber trong ứng dụng. Broker có thể dùng fetch batch, prefetch, credit, acknowledgement hoặc cơ chế pause/resume riêng. Adapter phải phối hợp hai lớp này để consumer không nhận quá nhiều dữ liệu, không xác nhận thông điệp trước khi xử lý thành công và không làm mất dữ liệu khi có lỗi.

Bài học thuộc chương **Tích hợp I/O** của module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, cùng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Ví dụ chính sử dụng Reactor Kafka để minh họa cách nhận thông điệp, điều tiết tốc độ, commit offset và xử lý lại khi consumer gặp sự cố.

## 1. Luồng dữ liệu từ producer đến consumer reactive

Một message broker thường đứng giữa producer và consumer:

```text
Producer A ----+
               |
Producer B ----+----> Message broker ----> Consumer adapter
               |                               |
Producer C ----+                               v
                                           Flux<Message>
                                                |
                                                v
                                      Reactive processing
                                                |
                                                v
                                      Acknowledge / commit
```

Broker lưu thông điệp theo chính sách của hệ thống. Consumer adapter đọc thông điệp và đưa chúng vào pipeline reactive. Khi xử lý xong, consumer xác nhận hoặc commit vị trí đọc theo giao thức broker.

Trong một consumer reactive, các bước thường là:

1. Cấu hình kết nối, consumer group, topic hoặc queue.
2. Subscribe vào nguồn thông điệp để tạo luồng `Flux`.
3. Chuyển payload thành kiểu domain và xác thực dữ liệu.
4. Xử lý nghiệp vụ với concurrency phù hợp.
5. Chỉ acknowledge hoặc commit sau khi xử lý thành công theo chính sách đã chọn.
6. Khi lỗi, retry có giới hạn, đưa thông điệp không xử lý được vào dead-letter queue (DLQ), hoặc để broker phát lại.
7. Khi service dừng hoặc subscription bị hủy, giải phóng consumer và tài nguyên liên quan.

Luồng nhận thông điệp thường sống lâu. Vì vậy, cần xem subscription như một tài nguyên của service, có vòng đời khởi động và shutdown rõ ràng.

## 2. Backpressure trong ứng dụng và flow control của broker

Reactive Streams định nghĩa demand qua `Subscription.request(n)`. Subscriber yêu cầu thêm `n` phần tử; publisher không được phát vượt quá tổng demand đã cấp. Điều này giúp các operator phối hợp tốc độ trong pipeline.

Broker có thể điều tiết theo cách riêng:

- Kafka đọc theo batch thông qua poll/fetch, quản lý offset và partition assignment.
- RabbitMQ có cơ chế prefetch/quality of service và acknowledgement cho delivery.
- Một số broker hoặc client dùng credit, flow control hoặc giới hạn số message chưa xác nhận.

Adapter reactive kết nối hai lớp này. Ví dụ, khi downstream không còn demand, adapter có thể giữ một lượng phần tử prefetch hữu hạn và tạm dừng đọc thêm từ broker. Khi downstream tiếp tục request, adapter có thể resume việc nhận.

Không nên hiểu `request(1)` luôn có nghĩa broker chỉ gửi đúng một message. Broker có thể đã fetch một batch và adapter có thể đang giữ một số record trong bộ đệm. Demand điều khiển việc phát từ publisher xuống subscriber; kích thước fetch, prefetch và queue nội bộ vẫn phụ thuộc cấu hình client.

### Những giới hạn cần phối hợp

| Lớp | Tham số hoặc cơ chế | Mục đích |
|---|---|---|
| Reactive Streams | `request(n)` | Giới hạn số phần tử subscriber yêu cầu. |
| Reactor Kafka | `receive(prefetch)` | Điều chỉnh lượng record được yêu cầu trước ở ranh giới receiver. |
| Kafka consumer | `max.poll.records` | Giới hạn số record tối đa trả về trong một lần poll. |
| Kafka consumer | `max.poll.interval.ms` | Giới hạn khoảng thời gian giữa các lần poll trước khi consumer có thể bị xem là không còn hoạt động. |
| RabbitMQ | `basic.qos` / prefetch count | Giới hạn số delivery chưa được acknowledge mà broker gửi cho consumer. |
| Pipeline | `flatMap` concurrency | Giới hạn số publisher con hoặc thao tác xử lý đang hoạt động. |
| Operator | `publishOn` prefetch, buffer | Giới hạn lượng phần tử được lấy trước hoặc chờ tại ranh giới bất đồng bộ. |

Các giới hạn này không thay thế nhau. Ví dụ, giới hạn `flatMap` concurrency không tự giới hạn số record mà client đã fetch vào bộ nhớ. Ngược lại, prefetch thấp ở broker không tự giới hạn số tác vụ mà downstream tạo ra nếu pipeline mở nhiều publisher con đồng thời.

## 3. Kết nối Kafka bằng Reactor Kafka

Reactor Kafka cung cấp `KafkaReceiver` để biểu diễn việc nhận record thành `Flux<ReceiverRecord<K, V>>`. Mỗi record chứa key, value, metadata Kafka và `ReceiverOffset` dùng để acknowledge hoặc commit.

Ví dụ cấu hình receiver:

```java
Map<String, Object> consumerProperties = new HashMap<>();
consumerProperties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProperties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
consumerProperties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class);
consumerProperties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class);
consumerProperties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

ReceiverOptions<String, String> receiverOptions =
    ReceiverOptions.<String, String>create(consumerProperties)
        .subscription(Set.of("order-events"))
        .commitInterval(Duration.ofSeconds(3))
        .commitBatchSize(100);

KafkaReceiver<String, String> receiver =
    KafkaReceiver.create(receiverOptions);
```

Ở ví dụ này:

- `bootstrap.servers` chỉ ra broker.
- `group.id` xác định consumer group.
- Deserializer chuyển key và value thành `String`.
- `enable.auto.commit=false` tắt auto-commit của Kafka client để ứng dụng kiểm soát acknowledgement/commit qua Reactor Kafka.
- `auto.offset.reset=earliest` chỉ định vị trí bắt đầu khi group chưa có offset hợp lệ; nó không làm consumer đọc lại từ đầu mỗi lần khởi động nếu offset đã được commit.
- `commitInterval` và `commitBatchSize` cấu hình việc commit các offset đã được acknowledge.

`ReceiverOptions` có thể nhận thêm các thuộc tính consumer Kafka như `max.poll.records`, `max.poll.interval.ms`, `session.timeout.ms` và các thiết lập bảo mật. Chọn giá trị dựa trên tốc độ xử lý, thời gian xử lý tối đa, số partition và cấu hình broker.

## 4. Nhận record thành `Flux` và xử lý tuần tự

`KafkaReceiver.receive()` cung cấp một `Flux` các record. Có thể truyền prefetch để điều chỉnh lượng record được lấy trước:

```java
Flux<ReceiverRecord<String, String>> records = receiver.receive(32);
```

Ví dụ xử lý từng record theo thứ tự nhận:

```java
Mono<Void> consumeOrders() {
    return receiver.receive(32)
        .concatMap(record -> processOrder(record.value())
            .then(Mono.fromRunnable(
                record.receiverOffset()::acknowledge
            ))
        )
        .then();
}
```

`concatMap` chỉ chuyển sang record tiếp theo sau khi publisher xử lý record hiện tại hoàn tất. Vì vậy, ví dụ đơn giản này giữ thứ tự xử lý trong luồng nhận. `acknowledge()` chỉ được gọi sau khi `processOrder` hoàn tất thành công.

`acknowledge()` đánh dấu offset đã xử lý để Reactor Kafka commit theo chính sách interval hoặc batch đã cấu hình. Nó không nhất thiết gửi commit ngay lập tức. Nếu cần commit ngay tại bước đó, `ReceiverOffset.commit()` trả về `Mono<Void>` để có thể kết hợp trực tiếp:

```java
Mono<Void> processAndCommit(ReceiverRecord<String, String> record) {
    return processOrder(record.value())
        .then(record.receiverOffset().commit());
}
```

Khi dùng `commit()`, pipeline chờ thao tác commit hoàn tất trước khi tiếp tục. Cách này dễ hiểu nhưng commit từng record có thể làm giảm throughput. Với tải lớn, acknowledge theo batch/interval thường hiệu quả hơn, miễn là hệ thống chấp nhận cửa sổ phát lại tương ứng.

## 5. Chọn concurrency mà vẫn giữ thứ tự trong partition

Kafka bảo đảm thứ tự record trong một partition. Nếu ứng dụng cần giữ thứ tự nghiệp vụ theo partition, không nên xử lý các record của cùng partition đồng thời rồi commit offset tùy ý.

Một cách tiếp cận là nhóm theo `TopicPartition`, xử lý tuần tự bên trong mỗi nhóm và cho phép các partition khác nhau chạy đồng thời:

```java
int maxAssignedPartitions = 12;

Flux<Void> processing = receiver.receive(64)
    .groupBy(record -> record.receiverOffset().topicPartition())
    .flatMap(partitionRecords ->
        partitionRecords.concatMap(record ->
            processOrder(record.value())
                .then(Mono.fromRunnable(
                    record.receiverOffset()::acknowledge
                ))
        ),
        maxAssignedPartitions
    );
```

Trong ví dụ này:

- `groupBy` tạo một nhóm cho mỗi partition đang được nhận.
- `concatMap` giữ thứ tự xử lý trong từng partition.
- `flatMap` cho phép các partition khác nhau được xử lý đồng thời.
- `maxAssignedPartitions` phải đủ để tiêu thụ tất cả nhóm partition có thể được gán cho receiver trong cấu hình đang dùng.

Nếu concurrency nhỏ hơn số nhóm có thể được tạo, một số `GroupedFlux` có thể chưa được subscribe. Những nhóm chưa được tiêu thụ có thể giữ record trong hàng đợi và làm nguồn bị tắc nghẽn. Hãy tính đến số partition tối đa được gán cho consumer, rebalance và giới hạn tài nguyên trước khi chọn concurrency.

Nếu không cần xử lý song song giữa partition, `concatMap` trên toàn bộ luồng nhận là cách đơn giản hơn. Nếu cần concurrency lớn hơn trong cùng partition, phải có thiết kế commit offset có kiểm soát. Không được commit offset cao hơn trong khi record trước đó cùng partition vẫn chưa xử lý xong, vì khi restart consumer có thể bỏ qua record chưa hoàn tất.

## 6. Acknowledge và commit offset đúng thời điểm

Với Kafka, offset commit cho biết vị trí consumer group sẽ tiếp tục đọc. Offset được commit là vị trí tiếp theo cần đọc, nên commit sau khi xử lý record là một bước quan trọng để cân bằng giữa không mất dữ liệu và không xử lý lặp quá nhiều.

Các nguyên tắc:

- Không acknowledge/commit trước khi xử lý nghiệp vụ thành công nếu muốn bảo đảm record được phát lại khi xử lý thất bại.
- Chỉ acknowledge record sau khi side effect cần thiết đã được ghi bền vững.
- Xử lý trùng lặp vì consumer có thể xử lý lại record sau crash hoặc trước khi offset commit thành công.
- Giữ thứ tự commit trong mỗi partition hoặc dùng cơ chế deferred commit đã được cấu hình và hiểu rõ.
- Không xem `acknowledge()` là bằng chứng broker đã lưu offset ngay lập tức; nó đánh dấu record đã xử lý và commit có thể diễn ra theo batch/interval.

### At-most-once, at-least-once và exactly-once

| Mô hình | Thời điểm xác nhận | Hệ quả |
|---|---|---|
| At-most-once | Commit trước khi xử lý. | Có thể mất record nếu xử lý thất bại sau commit. |
| At-least-once | Xử lý thành công rồi mới commit. | Có thể xử lý lặp nếu crash sau side effect nhưng trước commit. |
| Exactly-once ở phạm vi được hỗ trợ | Kết hợp transaction/idempotency và cơ chế broker phù hợp. | Cần thiết kế đồng bộ giữa offset và side effect; không tự đạt được chỉ bằng reactive operator. |

Với xử lý nghiệp vụ thông thường, at-least-once kết hợp idempotency thường là lựa chọn thực tế. Ví dụ, dùng `eventId` làm khóa duy nhất trong bảng đã xử lý hoặc dùng upsert theo aggregate version để record phát lại không tạo side effect trùng.

Nếu cần exactly-once xuyên qua Kafka và cơ sở dữ liệu ngoài, phải dùng một giao thức transaction hoặc outbox/inbox phù hợp. `Mono.then(commit())` chỉ sắp thứ tự các bước trong pipeline; nó không tạo transaction phân tán giữa broker và database.

## 7. Xử lý lỗi, retry và dead-letter queue

Khi một record gây lỗi, ứng dụng phải quyết định lỗi đó có thể thử lại hay là lỗi dữ liệu không thể xử lý. Không nên để một record độc hại làm dừng toàn bộ luồng vô hạn mà không có chính sách.

Ví dụ phân loại lỗi:

```java
Mono<Void> processRecord(ReceiverRecord<String, String> record) {
    return processOrder(record.value())
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
            .filter(this::isTransientFailure))
        .then(Mono.fromRunnable(
            record.receiverOffset()::acknowledge
        ))
        .onErrorResume(PermanentMessageException.class, error ->
            deadLetterPublisher.publish(
                    record.key(), record.value(), error
                )
                .then(Mono.fromRunnable(
                    record.receiverOffset()::acknowledge
                ))
        );
}
```

Luồng xử lý:

1. Gọi nghiệp vụ `processOrder`.
2. Chỉ retry lỗi được `isTransientFailure` xác định là tạm thời.
3. Nếu xử lý thành công, acknowledge record.
4. Nếu gặp `PermanentMessageException`, publish thông tin record và lỗi sang DLQ.
5. Chỉ acknowledge record gốc sau khi thao tác publish DLQ hoàn tất thành công.

Nếu publish DLQ thất bại, record gốc chưa được acknowledge nên có thể được phát lại. DLQ cần giữ đủ metadata như topic, partition, offset, key, timestamp, event ID và nguyên nhân lỗi để phục vụ điều tra.

Không nên retry vô hạn với backoff cố định. Retry không giới hạn có thể giữ partition không tiến triển, làm tăng lag và khiến lỗi tạm thời biến thành nghẽn kéo dài. Hãy giới hạn số lần thử, dùng exponential backoff có jitter khi phù hợp và phân loại lỗi rõ ràng.

### Lỗi không được phục hồi sẽ kết thúc subscription

Nếu một lỗi thoát khỏi `onErrorResume`, publisher nhận terminal `onError`. Subscription nhận thông điệp kết thúc và consumer có thể cần được khởi động lại theo chính sách service. Nếu muốn một record lỗi không kết thúc toàn bộ luồng, hãy xử lý lỗi ngay trong publisher con của record đó và bảo đảm quyết định acknowledge/DLQ được thực hiện đúng.

Không đặt `onErrorContinue` như một giải pháp tổng quát cho message consumer. Nó có thể bỏ qua lỗi ở operator cụ thể mà không bảo đảm record đã được lưu hoặc xử lý đúng; với thông điệp quan trọng, cần một nhánh lỗi tường minh.

## 8. RabbitMQ: prefetch và acknowledgement

Với RabbitMQ, broker gửi delivery cho consumer dựa trên prefetch/quality-of-service. Khi consumer chưa acknowledge các delivery trước đó, broker giới hạn số message đang outstanding theo prefetch count.

Một adapter reactive như Reactor RabbitMQ có thể biểu diễn delivery thành `Flux`. Với chế độ manual acknowledgement, ứng dụng xác nhận delivery sau khi xử lý thành công:

```java
Flux<AcknowledgableDelivery> deliveries =
    receiver.consumeManualAck("order-queue");

Flux<Void> handled = deliveries.concatMap(delivery ->
    processOrder(delivery.getBody())
        .then(Mono.fromRunnable(delivery::ack))
);
```

Đoạn mã minh họa manual ack: `ack()` chỉ chạy sau khi `processOrder` hoàn tất. Nếu xử lý thất bại, cần chọn `nack`/reject với chính sách requeue hoặc dead-letter phù hợp. API cụ thể và kiểu payload phụ thuộc phiên bản Reactor RabbitMQ đang sử dụng.

Prefetch count giới hạn số delivery chưa được xác nhận mà broker gửi cho consumer. Nếu prefetch quá lớn, consumer có thể giữ nhiều message trong bộ nhớ. Nếu quá nhỏ, throughput có thể giảm khi xử lý message có độ trễ cao. Hãy điều chỉnh dựa trên thời gian xử lý, số consumer và năng lực downstream.

### Auto ack và manual ack

| Chế độ | Khi broker coi message đã được xác nhận | Rủi ro |
|---|---|---|
| Auto ack | Khi delivery được gửi/nhận theo chế độ auto-ack. | Có thể mất message nếu consumer lỗi trước khi xử lý xong. |
| Manual ack | Khi ứng dụng gửi ack sau xử lý. | Có thể phát lại message nếu consumer lỗi trước ack; cần idempotency. |

Với công việc nghiệp vụ cần bảo đảm không bỏ sót, manual ack sau khi lưu kết quả bền vững thường phù hợp hơn. Nếu một message bị từ chối, hãy quyết định rõ có requeue hay đưa vào DLQ. Requeue liên tục một message không thể xử lý có thể tạo vòng lặp nóng.

## 9. Giới hạn concurrency và số công việc đang chờ

Một consumer có thể nhận record nhanh hơn tốc độ dịch vụ downstream xử lý. `flatMap` cho phép chạy nhiều publisher con đồng thời, nhưng cần giới hạn concurrency:

```java
Flux<Void> handled = receiver.receive(64)
    .flatMap(record -> processRecord(record), 8);
```

Trong ví dụ, tối đa tám publisher con được xử lý đồng thời. Prefetch 64 và concurrency 8 là hai giới hạn khác nhau: một giới hạn lượng record được lấy trước ở receiver, một giới hạn số tác vụ xử lý đồng thời ở operator.

Nếu mỗi tác vụ gọi một dịch vụ HTTP có giới hạn 20 request đồng thời, đặt `flatMap` concurrency cao hơn nhiều có thể làm quá tải dịch vụ. Ngược lại, concurrency quá thấp có thể không tận dụng được khả năng xử lý. Hãy đo throughput, latency, số connection, consumer lag và lượng record đang chờ.

### Tính lượng công việc đang chờ

Giả sử consumer nhận trung bình 700 message/giây nhưng downstream chỉ xử lý 500 message/giây. Chênh lệch 200 message/giây sẽ tích lũy thành khoảng 12.000 message trong một phút nếu nguồn không được điều tiết hoặc dừng.

Hàng đợi có thể xuất hiện ở nhiều lớp:

- Broker chưa được consumer đọc.
- Client đã fetch/poll nhưng record đang chờ trong receiver.
- Operator có prefetch hoặc buffer nội bộ.
- Publisher con đang chờ dịch vụ ngoài.
- Scheduler queue đang giữ tác vụ chưa chạy.
- DLQ publisher hoặc thao tác commit đang chờ.

Chỉ quan sát một queue có thể bỏ sót điểm tích tụ thực tế. Cần theo dõi consumer lag, prefetch, số record đang xử lý, queue size, thời gian xử lý và số lần retry.

## 10. Phối hợp scheduler với I/O và xử lý nghiệp vụ

Nếu consumer dùng driver reactive, có thể giữ pipeline non-blocking và không cần chuyển thread chỉ để xử lý message. Nếu một bước phải gọi API blocking như JDBC đồng bộ hoặc client cũ, cần cô lập lời gọi đó trên `boundedElastic`.

```java
Mono<Void> processOrder(String payload) {
    return Mono.fromCallable(() -> legacyOrderDao.apply(payload))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
```

Không gọi `block()` trong callback nhận record. Hãy trả về `Mono` của thao tác xử lý để `concatMap` hoặc `flatMap` quản lý vòng đời và concurrency.

Nếu bước xử lý CPU-bound nặng, có thể chuyển phần biến đổi đó sang `Schedulers.parallel()`:

```java
Mono<ValidatedOrder> validate(String payload) {
    return Mono.fromCallable(() -> expensiveValidation(payload))
        .subscribeOn(Schedulers.parallel());
}
```

Chỉ dùng `parallel` cho công việc CPU-bound không blocking. Đưa JDBC hoặc thao tác chờ mạng lên `parallel` có thể chặn worker và làm chậm các tác vụ khác.

## 11. Rebalance, shutdown và vòng đời consumer

Kafka consumer group có thể rebalance khi instance mới tham gia, instance cũ rời đi hoặc partition assignment thay đổi. Trong thời gian rebalance, consumer có thể mất quyền sở hữu partition và phải dừng xử lý các record thuộc partition đó theo giao thức của client.

Một số điểm cần quan tâm:

- Giữ thời gian xử lý trong giới hạn phù hợp với `max.poll.interval.ms` và cấu hình receiver.
- Không để tác vụ xử lý treo vô hạn mà không có timeout hoặc cơ chế hủy.
- Không commit offset của record chưa xử lý thành công.
- Khi revoke partition, hoàn tất hoặc dừng công việc đang chạy theo chính sách an toàn trước khi nhường partition.
- Khi service shutdown, dispose subscription nhận record và chờ các thao tác cleanup cần thiết trong giới hạn thời gian.

Reactor Kafka cung cấp callback assignment/revocation qua `ReceiverOptions` để ứng dụng quan sát thay đổi partition. Có thể dùng các callback này để ghi log, cập nhật metric hoặc phối hợp trạng thái xử lý. Không nên thực hiện công việc blocking kéo dài trong callback rebalance.

Ví dụ gắn listener quan sát assignment:

```java
ReceiverOptions<String, String> options =
    ReceiverOptions.<String, String>create(consumerProperties)
        .subscription(Set.of("order-events"))
        .addAssignListener(partitions ->
            log.info("Assigned partitions: {}", partitions)
        )
        .addRevokeListener(partitions ->
            log.info("Revoked partitions: {}", partitions)
        );
```

Tên callback chỉ nên dùng cho quan sát nhanh và cập nhật trạng thái nhẹ. Việc flush hoặc commit công việc đang chạy cần được thiết kế theo API receiver và giao thức của broker.

## 12. Kiểm thử consumer reactive

Nên tách logic xử lý một message khỏi adapter broker để có thể kiểm thử bằng `StepVerifier`. Adapter chịu trách nhiệm nhận record và acknowledge; business service chịu trách nhiệm biến payload thành kết quả.

Ví dụ một handler nhận message và hàm acknowledge:

```java
record IncomingMessage(String id, String payload) {}

interface Acknowledger {
    Mono<Void> acknowledge();
}

Mono<Void> handle(
    IncomingMessage message,
    Acknowledger acknowledger
) {
    return orderService.process(message.payload())
        .then(acknowledger.acknowledge());
}
```

Kiểm thử acknowledge chỉ sau khi xử lý thành công:

```java
AtomicBoolean acknowledged = new AtomicBoolean();
IncomingMessage message = new IncomingMessage("evt-1", "order-data");

StepVerifier.create(handle(
        message,
        () -> Mono.fromRunnable(() -> acknowledged.set(true))
    ))
    .verifyComplete();

assertTrue(acknowledged.get());
```

Kiểm thử khi nghiệp vụ thất bại:

```java
AtomicBoolean acknowledged = new AtomicBoolean();

StepVerifier.create(handle(
        message,
        () -> Mono.fromRunnable(() -> acknowledged.set(true))
    ))
    .expectError(ValidationException.class)
    .verify();

assertFalse(acknowledged.get());
```

Bài kiểm thử xác minh handler không acknowledge khi publisher nghiệp vụ phát lỗi. Trong test thực tế, có thể dùng mock cho service và acknowledger, nhưng cần xác minh thứ tự gọi: xử lý thành công trước, ack sau.

### Những trường hợp nên kiểm thử

- Subscriber hủy: receiver được dispose và không tiếp tục phát record xuống pipeline.
- Xử lý thành công: record được acknowledge/commit theo chính sách.
- Xử lý lỗi tạm thời: retry đúng số lần và có backoff.
- Lỗi vĩnh viễn: publish DLQ thành công rồi mới acknowledge record gốc.
- Publish DLQ thất bại: record gốc chưa được acknowledge.
- Record trùng: idempotency ngăn side effect lặp.
- Nhiều record cùng partition: thứ tự xử lý và commit được giữ theo yêu cầu.
- Nhiều partition: concurrency không vượt giới hạn đã định.
- Backpressure: prefetch và demand không làm queue tăng ngoài giới hạn.
- Rebalance và shutdown: công việc đang chạy được dừng hoặc hoàn tất theo chính sách.

Đối với kiểm thử tích hợp, có thể chạy broker thử nghiệm trong môi trường test và xác minh offset, redelivery, DLQ, partition assignment cùng hành vi khi consumer restart. Kiểm thử unit với `StepVerifier` không thay thế kiểm thử giao thức broker.

## 13. Tình huống thực tế: cập nhật projection đơn hàng từ Kafka

Một dịch vụ projection nhận `OrderEvent` từ topic `order-events`, cập nhật bảng trạng thái đơn hàng và cần bảo đảm sự kiện không bị đánh dấu đã xử lý trước khi transaction database hoàn tất.

Một cách tổ chức pipeline tuần tự:

```java
Flux<Void> consumeOrderEvents(KafkaReceiver<String, String> receiver) {
    return receiver.receive(32)
        .concatMap(record -> {
            OrderEvent event = deserialize(record.value());

            return reactiveTransactionManager.inTransaction(
                orderRepository.apply(event)
            ).then(Mono.fromRunnable(
                record.receiverOffset()::acknowledge
            ));
        });
}
```

Ví dụ giả định `inTransaction` trả về publisher chỉ hoàn tất sau khi transaction đã commit. Khi đó, offset chỉ được acknowledge sau khi cập nhật projection bền vững. Nếu ứng dụng crash sau database commit nhưng trước khi Kafka commit offset, event có thể được phát lại; `orderRepository.apply` cần idempotent theo `eventId` hoặc aggregate version.

Đối với throughput cao hơn, có thể xử lý song song giữa các partition và tuần tự trong từng partition như phần trước. Nếu database transaction và Kafka offset cần một bảo đảm atomic xuyên hệ thống, phải dùng kiến trúc transaction phù hợp hoặc outbox/inbox; chỉ đặt `then(acknowledge)` không tạo atomic commit giữa hai hệ thống.

## 14. Checklist thiết kế message consumer reactive

- Dùng adapter broker trả về `Flux` hoặc publisher phù hợp; giữ subscription trong lifecycle của service.
- Phân biệt demand Reactive Streams với fetch, poll, prefetch và acknowledgement của broker.
- Giới hạn prefetch, poll batch, buffer, scheduler queue và concurrency theo tài nguyên thực tế.
- Tắt auto-commit nếu ứng dụng cần kiểm soát offset theo kết quả xử lý.
- Chỉ acknowledge/commit sau khi side effect cần thiết đã được lưu bền vững.
- Giữ thứ tự xử lý và commit trong từng partition/queue khi nghiệp vụ yêu cầu.
- Thiết kế idempotency vì at-least-once có thể phát lại thông điệp.
- Phân loại lỗi tạm thời và lỗi vĩnh viễn; retry có giới hạn và backoff.
- Chỉ acknowledge record gốc sau khi DLQ publish thành công.
- Không dùng blocking I/O trên event loop hoặc scheduler CPU-bound.
- Xử lý cancellation, rebalance và shutdown để giải phóng consumer đúng cách.
- Theo dõi consumer lag, số record đang xử lý, thời gian xử lý, retry, DLQ và commit latency.
- Kiểm thử unit bằng `StepVerifier` và kiểm thử tích hợp với broker cho offset, redelivery và rebalance.

Kết nối message broker với Reactor hiệu quả khi adapter phối hợp đúng demand, prefetch và acknowledgement. Pipeline cần giới hạn lượng dữ liệu được lấy trước, kiểm soát concurrency, giữ thứ tự trong phạm vi partition khi cần và chỉ xác nhận thông điệp sau khi xử lý bền vững. Khi kết hợp những quy tắc này với idempotency, retry có giới hạn, DLQ và lifecycle cancellation, consumer có thể duy trì throughput ổn định mà vẫn bảo toàn khả năng phục hồi khi lỗi xảy ra.
