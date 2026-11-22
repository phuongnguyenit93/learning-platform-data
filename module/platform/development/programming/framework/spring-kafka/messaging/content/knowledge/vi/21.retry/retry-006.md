# Retry ảnh hưởng đến partition ordering

Kafka bảo đảm thứ tự record trong cùng một partition theo offset. Tuy nhiên, thứ tự ghi vào log và thứ tự hoàn tất xử lý ở consumer là hai việc khác nhau. Khi một record bị lỗi và phải retry, cách retry quyết định consumer có chờ record đó xử lý xong trước khi đi tiếp hay chuyển record sang một luồng khác để partition tiếp tục chạy.

Với retry đồng bộ (blocking retry) trong listener container, consumer thường xử lý lại record lỗi tại vị trí hiện tại trước khi tiếp tục các record phía sau trong partition. Cách này giữ thứ tự xử lý nhưng có thể làm partition bị nghẽn trong thời gian chờ. Với retry topic (non-blocking retry), record lỗi được chuyển sang topic retry để consumer của topic gốc tiếp tục đọc; record phía sau có thể hoàn tất trước record đang retry. Cách này tăng khả năng tiếp tục tiêu thụ nhưng không giữ ordering ban đầu.

Nếu nghiệp vụ yêu cầu sự kiện của cùng một aggregate phải được áp dụng đúng thứ tự, cần chọn chiến lược retry phù hợp ngay từ đầu. Không thể chỉ dựa vào việc producer dùng cùng key hoặc Kafka lưu record theo offset để suy ra thứ tự xử lý cuối cùng vẫn được bảo toàn.

## 1. Kafka bảo đảm ordering ở phạm vi nào?

Kafka chỉ bảo đảm thứ tự trong một partition. Record được append vào partition sẽ có offset tăng dần; consumer đọc các record của partition theo thứ tự đó. Kafka không cung cấp một thứ tự toàn cục giữa các partition trong cùng topic hoặc giữa nhiều topic.

Ví dụ topic `orders` có ba partition:

```text
orders-0: offset 10 -> offset 11 -> offset 12 -> ...
orders-1: offset 20 -> offset 21 -> offset 22 -> ...
orders-2: offset  5 -> offset  6 -> offset  7 -> ...
```

Consumer group có thể xử lý ba partition song song. Record offset 12 ở partition 0 không nhất thiết được xử lý trước record offset 21 ở partition 1. Nếu nghiệp vụ cần thứ tự theo `orderId`, producer nên dùng `orderId` làm key để các event của cùng đơn hàng được định tuyến vào cùng partition bằng partitioner ổn định.

Ví dụ:

```java
kafkaTemplate.send("orders", event.orderId(), event);
```

Key giúp định tuyến các event cùng đơn hàng về cùng partition, nhưng nó không tự bảo đảm consumer hoàn tất nghiệp vụ đúng thứ tự nếu listener xử lý bất đồng bộ hoặc chuyển record lỗi sang retry topic.

## 2. Phân biệt thứ tự ghi, thứ tự nhận và thứ tự hoàn tất

Khi nói ordering, cần xác định đang nói đến giai đoạn nào:

| Giai đoạn | Ý nghĩa |
|---|---|
| Producer append order | Thứ tự record được ghi vào một partition |
| Consumer delivery order | Thứ tự record được trả về cho consumer trong partition |
| Listener invocation order | Thứ tự listener bắt đầu xử lý các record |
| Business completion order | Thứ tự side effect nghiệp vụ thực sự hoàn tất |
| Retry/replay order | Thứ tự record được xử lý lại sau khi lỗi |

Kafka quản lý ordering của log và consumer delivery theo partition. Ứng dụng vẫn có thể làm đảo thứ tự hoàn tất nếu listener gửi công việc sang thread pool rồi trả về ngay, xử lý nhiều event cùng partition song song hoặc dùng retry topic.

Ví dụ consumer nhận offset 100 rồi 101 theo thứ tự, nhưng gửi cả hai sang executor:

```text
Nhận:       offset 100 -------- offset 101
Xử lý:      bắt đầu 100          bắt đầu 101
Hoàn tất:                    101 -------- 100
```

Nếu event 101 cập nhật trạng thái đơn hàng trước event 100, dữ liệu nghiệp vụ có thể bị lùi hoặc sai dù Kafka đã giao record đúng thứ tự. Khi ordering quan trọng, không để listener commit hoặc kết thúc xử lý trước khi công việc tương ứng hoàn tất; nếu cần song song, hãy tuần tự hóa theo key hoặc kiểm tra sequence/version của aggregate.

## 3. Producer cũng phải giữ thứ tự khi gửi lại

Ordering có thể bị ảnh hưởng ngay ở phía producer nếu một batch gửi thất bại và producer retry. Với producer không bật idempotence, nếu `max.in.flight.requests.per.connection` lớn hơn 1, một batch gửi sau có thể thành công trước batch gửi trước đang được retry; thứ tự record trong partition có thể bị đảo.

Để giữ thứ tự khi producer retry, bật idempotence và dùng cấu hình tương thích:

```yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
```

Idempotent producer dùng sequence number để broker nhận diện retry của cùng một batch và tránh ghi trùng do retry. Với idempotence bật, Kafka hỗ trợ tối đa năm request in-flight cho mỗi connection mà vẫn giữ thứ tự theo partition. Nếu tắt idempotence, cần giới hạn `max.in.flight.requests.per.connection` về 1 để tránh đảo thứ tự do retry, đổi lại throughput có thể giảm.

Trong Kafka client hiện đại, idempotence thường được bật mặc định khi các cấu hình liên quan tương thích; khai báo tường minh giúp contract dễ đọc và tránh thay đổi ngoài ý muốn. Producer idempotence chỉ xử lý retry của producer session; nó không chống duplicate nghiệp vụ do ứng dụng gọi `send()` lại như một request mới.

## 4. Blocking retry giữ thứ tự trong partition

Với record listener, `DefaultErrorHandler` có thể retry record lỗi bằng cách seek consumer về offset đó. Khi record lỗi được xử lý thành công hoặc được recover theo chính sách, consumer mới tiếp tục các record phía sau.

Ví dụ partition `orders-0`:

```text
Log:
offset 100: OrderUpdated(version=1)
offset 101: OrderUpdated(version=2)
offset 102: OrderUpdated(version=3)

Consumer:
1. Nhận offset 100
2. Xử lý lỗi tạm thời
3. Backoff và retry offset 100
4. Offset 100 thành công
5. Tiếp tục offset 101, rồi 102
```

Vì record 101 không được đưa qua listener trước khi offset 100 được xử lý/recover, blocking retry giữ thứ tự xử lý trong partition. Đây là lựa chọn phù hợp khi các event có quan hệ nhân quả và event sau không được phép vượt event trước.

Ví dụ cấu hình:

```java
@Bean
DefaultErrorHandler orderErrorHandler(KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    DefaultErrorHandler handler = new DefaultErrorHandler(recoverer, backOff);
    handler.setSeekAfterError(true);
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

`FixedBackOff(1000, 2)` chờ một giây giữa các lần retry và cho phép hai lần retry sau lần xử lý ban đầu. `setSeekAfterError(true)` thể hiện rõ chiến lược seek về record lỗi và các record còn lại. Đây là hành vi mặc định phổ biến của `DefaultErrorHandler`; có thể giữ mặc định nếu không cần ghi rõ.

## 5. Đổi lại: head-of-line blocking

Blocking retry giữ thứ tự bằng cách không cho record phía sau vượt qua record lỗi. Hệ quả là một record lỗi kéo dài có thể chặn cả partition. Đây là hiện tượng head-of-line blocking.

Ví dụ:

```text
Partition orders-0:

offset 100: Order A -> lỗi, retry 5 lần, chờ tổng cộng 30 giây
offset 101: Order B -> đang chờ
offset 102: Order C -> đang chờ

Trong lúc retry offset 100:
  B và C chưa được listener xử lý trên consumer thread đó.
```

Với consumer thread xử lý nhiều partition, blocking backoff mặc định có thể khiến các partition khác được gán cho cùng consumer thread cũng không được listener xử lý trong thời gian thread đang chờ. Các consumer thread khác trong group vẫn có thể tiếp tục partition riêng của chúng.

Blocking retry phù hợp khi:

- Ordering là yêu cầu nghiệp vụ bắt buộc.
- Lỗi có khả năng phục hồi trong thời gian ngắn.
- Số lần retry và backoff có giới hạn rõ ràng.
- Throughput có thể chấp nhận việc một partition tạm thời bị chặn.

Không nên retry blocking nhiều phút cho mọi loại lỗi. Một record poison message có thể làm lag tăng liên tục và giảm throughput của partition.

## 6. Cấu hình DefaultErrorHandler để retry tại chỗ

Ví dụ factory record listener dùng blocking retry:

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        ExponentialBackOffWithMaxRetries backOff =
                new ExponentialBackOffWithMaxRetries(3);
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(4_000L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);
        handler.addNotRetryableExceptions(
                InvalidOrderException.class,
                UnsupportedOrderStateException.class);
        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }
}
```

Listener xử lý đồng bộ:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    orderProjection.apply(event);
}
```

Với `AckMode.RECORD`, container xác nhận tiến độ theo record sau khi listener hoàn tất thành công. Khi listener ném lỗi, error handler áp dụng retry và recovery. Hãy bảo đảm DLT có đủ partition nếu recoverer giữ nguyên partition nguồn và kiểm tra publish DLT thành công trước khi cho record gốc được xem là recovered.

## 7. SeekAfterError và hành vi giữ record

`DefaultErrorHandler` thường seek consumer về offset của record lỗi và các record còn lại trong poll để chúng được trả lại ở lần poll tiếp theo. Đây là cơ chế giúp record lỗi không bị vượt qua trong partition.

Trong các phiên bản Spring Kafka hỗ trợ, có thể đặt `seekAfterError(false)` để container giữ lại các record chưa xử lý trong bộ nhớ và gửi lại sau khi thực hiện một lần poll ngắn nhằm giữ consumer group sống. Cách này tránh seek broker position theo cơ chế thông thường, nhưng vẫn không có nghĩa các record sau record lỗi được xử lý trước nó. Container giữ thứ tự danh sách record được gửi lại.

Hai cách khác nhau về cách container quản lý record còn lại; cả hai đều nhằm duy trì việc xử lý record lỗi trước phần tiếp theo theo flow blocking. Đừng nhầm `seekAfterError(false)` với non-blocking retry topics: nó không chuyển record lỗi sang một topic khác để partition gốc tự do đi tiếp.

## 8. Non-blocking retry topic có thể phá ordering

Với non-blocking retry, record lỗi được publish sang retry topic. Consumer của topic gốc có thể tiếp tục với record kế tiếp mà không chờ record lỗi hoàn tất retry. Điều này tăng khả năng tiến triển của partition nhưng cho phép record sau vượt record trước.

Ví dụ cùng partition và cùng key:

```text
Topic orders, partition 0:
offset 100: OrderUpdated(version=1) -> lỗi, chuyển orders-retry-1000
offset 101: OrderUpdated(version=2) -> xử lý thành công ngay

Sau thời gian delay:
orders-retry-1000:
version=1 -> retry và xử lý thành công

Thứ tự hoàn tất nghiệp vụ: version 2 rồi version 1
```

Việc dùng cùng key không ngăn được tình huống này vì record retry nằm trên topic khác, có consumer group và lịch xử lý riêng. Record retry có thể quay lại sau khi record mới hơn đã cập nhật trạng thái nghiệp vụ.

Spring Kafka cung cấp `@RetryableTopic` để cấu hình retry topic:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000))
@KafkaListener(topics = "orders", groupId = "order-projection")
public void onOrder(OrderEvent event) {
    orderProjection.apply(event);
}
```

Trong ví dụ, `attempts` là tổng số lần thử theo cấu hình retry topic, bao gồm lần xử lý ban đầu; kiểm tra phiên bản Spring Kafka và chính sách exception để biết record nào được chuyển sang retry topic. Cách cấu hình cụ thể của retry topic, số partition và naming strategy cần được kiểm tra trước khi triển khai.

Non-blocking retry phù hợp khi:

- Có thể chấp nhận event mới được xử lý trước event đang retry.
- Thời gian retry dài và không muốn chặn partition gốc.
- Nghiệp vụ idempotent và có version/sequence guard.
- Throughput và khả năng tiếp tục tiêu thụ quan trọng hơn strict ordering.

## 9. Retry topic và DLT là luồng khác với partition gốc

Retry topic và DLT là các topic riêng, có partition, offset và consumer group riêng. Dù retry topic được tạo với cùng số partition và cùng key, ordering chỉ được bảo đảm trong từng partition của từng topic. Không có một offset chung để ghép thứ tự giữa `orders-0` và `orders-retry-1000-0`.

Các điểm cần chú ý:

- Partition resolver có thể giữ partition number nguồn, nhưng không tạo ordering xuyên topic.
- Consumer retry topic có thể xử lý chậm hoặc nhanh khác consumer topic gốc.
- Nhiều retry level có thể làm record đi qua các topic với thời gian chờ khác nhau.
- Record đã hết retry và vào DLT có thể được replay nhiều giờ sau, khi các event mới hơn đã được áp dụng.
- DLT replay theo thứ tự file hoặc theo timestamp không nhất thiết khôi phục được thứ tự partition ban đầu.

Nếu cần replay có ordering, phải lưu metadata gốc như original topic, partition, offset, key và event sequence. Công cụ replay nên sắp xếp theo partition và offset hoặc theo aggregate version, đồng thời có cơ chế ngăn event cũ ghi đè trạng thái mới.

## 10. DLT recovery có thể tạo khoảng trống trong luồng

Sau khi retry hết số lần, recoverer có thể publish record lỗi sang DLT. Nếu publish thành công và error handler xác nhận record đã recovered, consumer tiếp tục với offset phía sau. Điều này có nghĩa partition gốc không còn chờ record đó.

Ví dụ:

```text
orders-0:
offset 100: version 1 -> lỗi hết retry -> orders.DLT
offset 101: version 2 -> xử lý thành công
offset 102: version 3 -> xử lý thành công

Sau đó:
orders.DLT:
original offset 100 -> được điều tra và replay
```

Nếu replay version 1 sau khi version 3 đã được áp dụng, projection có thể bị lùi nếu handler không kiểm tra version. Với strict ordering, không được coi việc chuyển record sang DLT rồi tiếp tục partition là bảo toàn đầy đủ thứ tự nghiệp vụ. Đó là quyết định bỏ qua tạm thời một sự kiện và chấp nhận xử lý gap.

Nếu record lỗi là điều kiện bắt buộc cho mọi event sau, lựa chọn an toàn có thể là dừng/pause partition hoặc consumer để sửa lỗi rồi tiếp tục. Nếu nghiệp vụ cho phép bỏ qua, cần ghi nhận gap và có quy tắc bù/reconcile rõ ràng.

## 11. Partition concurrency không tạo thứ tự toàn cục

`concurrency` của `ConcurrentKafkaListenerContainerFactory` tạo nhiều consumer trong cùng group. Kafka chỉ gán một partition cho tối đa một consumer trong group tại một thời điểm. Do đó, concurrency cho phép xử lý song song giữa các partition, nhưng không làm nhiều consumer cùng xử lý các record của một partition theo thứ tự tùy ý.

Ví dụ topic có 6 partition và concurrency bằng 3:

```text
Consumer 1: partition 0, 1
Consumer 2: partition 2, 3
Consumer 3: partition 4, 5
```

Mỗi consumer xử lý partition được gán theo thứ tự record. Tuy nhiên, nếu listener dùng async executor hoặc reactive pipeline và trả về trước khi xử lý xong, business completion order vẫn có thể bị đảo. Nếu cần xử lý song song trong cùng partition, phải có cơ chế sequencing theo key/aggregate và commit offset chỉ khi các record trước đã hoàn tất.

Tăng concurrency vượt số partition không tăng số luồng xử lý hữu ích cho topic đó; các consumer thừa sẽ không được gán partition. Cũng cần cân nhắc rebalance khi scale up/down và tác động tới tiến độ đang xử lý.

## 12. Giữ ordering khi xử lý bất đồng bộ

Một anti-pattern phổ biến là listener submit task vào executor rồi return:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.apply(event));
}
```

Container có thể coi listener đã hoàn tất và commit offset trong khi task thực tế vẫn chạy. Task của event sau có thể hoàn thành trước event trước. Nếu task lỗi, container cũng không nhận được exception để retry record đúng cách.

Nếu cần async processing, có thể dùng một trong các hướng:

- Chờ future hoàn tất trong listener để exception quay lại container; cách này vẫn giữ tuần tự trên consumer thread.
- Dùng executor theo partition/key để tuần tự hóa công việc có cùng ordering key.
- Dùng worker queue có checkpoint theo offset, chỉ commit liên tục tới offset đã hoàn tất an toàn.
- Đưa event vào một workflow riêng có version guard và idempotency.

Không để listener return trước khi đã chuyển trách nhiệm xử lý và commit sang một cơ chế bền vững khác. Nếu chỉ submit vào memory queue, process crash có thể làm mất task dù offset đã được commit.

## 13. Batch listener và ordering khi một phần batch thất bại

Batch listener nhận nhiều record trong một lần poll. Nếu record ở index 2 thất bại, ứng dụng có thể ném `BatchListenerFailedException` kèm index để `DefaultErrorHandler` xác định phần đã xử lý và record cần retry/recover.

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch-worker",
        containerFactory = "batchListenerFactory")
public void onOrders(List<OrderEvent> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            orderService.apply(events.get(i));
        } catch (TransientOrderException ex) {
            throw new BatchListenerFailedException(
                    "Batch lỗi tại index " + i, ex, i);
        }
    }
}
```

Khi index lỗi được chỉ rõ, framework có thể xử lý offset trước đó và seek/retry từ record lỗi theo partition. Nếu không xác định được index, fallback có thể retry toàn batch; các record đã xử lý có thể được giao lại và cần idempotency.

Batch có thể chứa record từ nhiều partition. Thứ tự list không phải thứ tự toàn cục; khi xử lý partial failure, cần hiểu semantics theo partition và error handler đang dùng. `@RetryableTopic` không hỗ trợ batch listener trong các phiên bản phổ biến; không áp dụng ví dụ retry topic record listener cho batch listener mà không kiểm tra giới hạn phiên bản.

## 14. Transaction và retry sau rollback

Với container transaction, listener thất bại làm transaction Kafka bị rollback; offset không được commit cùng transaction đó. `DefaultAfterRollbackProcessor` có thể seek về record lỗi và thực hiện retry sau rollback, giữ record chưa thành công ở đầu luồng xử lý của partition.

Sau số lần thử cấu hình, processor có thể recover record (ví dụ publish DLT) rồi cho partition tiếp tục. Nếu dùng transactional recoverer, việc publish DLT và commit offset nguồn có thể được phối hợp trong transaction theo cấu hình phù hợp. Cần phân biệt transaction Kafka với transaction database/HTTP bên ngoài; rollback Kafka không tự hoàn tác side effect đã xảy ra ở hệ thống khác.

`@RetryableTopic` non-blocking retry không tương thích với container transactions trong các cấu hình Spring Kafka phổ biến. Nếu cần strict ordering và transaction, thường dùng blocking retry/AfterRollbackProcessor. Kiểm tra đúng version Spring Kafka trước khi kết hợp retry topic, batch listener và transaction.

## 15. Bảo vệ thứ tự bằng version hoặc sequence của aggregate

Khi không thể tránh retry topic hoặc cần xử lý song song, nên để payload có version/sequence tăng dần theo aggregate:

```java
public record OrderEvent(
        String orderId,
        long aggregateVersion,
        String eventType,
        String status) {
}
```

Consumer có thể so sánh version với trạng thái đã lưu:

```java
public void apply(OrderEvent event) {
    long currentVersion = repository.currentVersion(event.orderId());

    if (event.aggregateVersion() <= currentVersion) {
        return; // duplicate hoặc event cũ đã được áp dụng
    }

    if (event.aggregateVersion() != currentVersion + 1) {
        throw new MissingPreviousEventException(
                "Thiếu version trước của order " + event.orderId());
    }

    repository.applyAndAdvanceVersion(event);
}
```

Trong ví dụ, event có version cũ hoặc trùng bị bỏ qua; event có gap bị trì hoãn/retry cho tới khi version trước được áp dụng. Việc cập nhật trạng thái và version phải atomic ở database, ví dụ dùng optimistic locking hoặc câu lệnh update có điều kiện. Nếu chỉ đọc version rồi ghi riêng, hai worker có thể race và cùng áp dụng sai thứ tự.

Version guard không tự giải quyết việc lưu trữ event bị thiếu. Cần có cơ chế retry/replay, timeout cho gap và cảnh báo nếu version trước không bao giờ đến. Với event độc lập không có quan hệ thứ tự, không cần áp đặt version tuần tự.

## 16. Tăng partition count có thể thay đổi thứ tự theo key

Key-based partitioning thường chọn partition dựa trên hash của key và số partition hiện tại. Khi tăng số partition, cùng một key có thể được định tuyến sang partition khác cho các record mới, trong khi record cũ vẫn nằm ở partition cũ.

Ví dụ trước khi mở rộng, `order-42` được ghi vào partition 1. Sau khi topic tăng partition, partitioner có thể đưa event mới của `order-42` sang partition 4. Hai partition được consumer xử lý độc lập nên không còn một ordering stream duy nhất cho order đó.

Nếu strict per-key ordering là yêu cầu lâu dài, hãy lập kế hoạch partition count trước, dùng partitioner ổn định có quản lý migration hoặc chuyển sang topic/version mới với quy trình cutover. Khi mở rộng topic hiện có, cần đánh giá các key đang có event dở dang và không giả định ordering xuyên partition cũ/mới.

## 17. Chọn chiến lược theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược phù hợp | Đánh đổi |
|---|---|---|
| Strict ordering theo partition/key | Blocking retry với `DefaultErrorHandler` hoặc `DefaultAfterRollbackProcessor` | Partition có thể bị chặn trong lúc retry |
| Dependency thường hồi phục trong vài giây | Blocking retry ngắn, bounded backoff | Tăng latency của record phía sau |
| Dependency cần chờ lâu, event sau vẫn xử lý độc lập | Retry topics/non-blocking retry | Ordering bị thay đổi; cần idempotency/version guard |
| Event cũ có thể bỏ qua nếu event mới đã áp dụng | Retry topics + aggregate version check | Cần lưu version và xử lý gap |
| Record poison làm các event sau vô nghĩa nếu vượt qua | Pause/stop partition, cảnh báo và sửa/replay | Giảm availability và cần runbook |
| Event lỗi có thể được quarantine và xử lý sau | DLT + audit gap + replay có kiểm soát | DLT/replay không tự khôi phục ordering |
| Xử lý song song nhiều partition | Concurrency theo số partition | Không có ordering toàn cục giữa partition |

## 18. Kiểm thử ordering khi có retry

Không chỉ kiểm thử rằng record cuối cùng được xử lý. Hãy ghi lại thứ tự business event được áp dụng và xác minh hành vi khi record đầu bị lỗi.

### Test blocking retry

1. Gửi ba event cùng key vào một partition: version 1, 2, 3.
2. Làm listener thất bại lần đầu với version 1 rồi thành công ở lần retry.
3. Ghi lại thứ tự listener hoàn tất.
4. Xác minh version 2 và 3 chỉ được áp dụng sau version 1.
5. Xác minh offset commit không vượt qua record lỗi trước khi xử lý/recover.

### Test non-blocking retry

1. Gửi version 1, 2, 3 cùng key vào một partition.
2. Làm version 1 thất bại và được chuyển sang retry topic.
3. Xác minh topic gốc có thể xử lý version 2 và 3 trước.
4. Chờ retry topic xử lý lại version 1.
5. Xác minh version guard ngăn event cũ ghi đè trạng thái mới hoặc phát hiện gap theo contract.

### Test producer ordering

1. Gửi nhiều record cùng key trong lúc mô phỏng lỗi broker/network.
2. Kiểm tra producer idempotence và cấu hình in-flight requests.
3. Xác minh offset trong partition phản ánh thứ tự gửi dự kiến.
4. Lặp lại test với idempotence tắt và nhiều in-flight requests để thấy rủi ro nếu cấu hình cho phép.

Nên chạy integration test với Kafka thật qua Testcontainers hoặc Embedded Kafka. Unit test mock listener có thể xác minh classifier/backoff nhưng không đủ để chứng minh partition assignment, offset, retry topic routing và ordering thực tế.

## 19. Quan sát ordering trong production

Các metric và log nên giúp trả lời: record nào đang chặn partition, retry có làm event sau vượt event trước không và DLT có tạo gap chưa được xử lý không?

- Consumer lag theo từng partition, không chỉ tổng lag của topic.
- Số lần retry, thời gian backoff và thời gian xử lý record.
- Số record được chuyển sang retry topic và DLT theo source topic/partition.
- Original topic, partition, offset, key và aggregate version trong log.
- Thời điểm listener bắt đầu và hoàn tất xử lý để phát hiện async completion đảo thứ tự.
- Số event bị bỏ qua do version đã cũ và số event bị trì hoãn do thiếu version trước.
- Số lần rebalance và thời gian partition không có consumer xử lý.

Không dùng order ID hoặc event ID làm metric label có cardinality cao. Đưa các ID vào structured log hoặc trace attribute; metric nên dùng topic, partition, exception category và retry destination có tập giá trị giới hạn.

## 20. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Cùng key đồng nghĩa luôn xử lý đúng thứ tự | Cùng key giúp định tuyến vào partition; retry topic và async processing vẫn có thể đảo thứ tự hoàn tất |
| Kafka đảm bảo thứ tự toàn topic | Ordering chỉ được bảo đảm trong từng partition |
| Retry luôn giữ record sau chờ record trước | Blocking retry thường giữ thứ tự; non-blocking retry có thể cho record sau vượt qua |
| Retry topic cùng partition number giữ ordering với topic gốc | Partition thuộc các topic khác nhau không có thứ tự chung |
| DLT rồi replay sẽ tự khôi phục thứ tự | Replay muộn có thể chạy sau event mới; cần version guard hoặc replay theo sequence |
| Tăng concurrency làm một partition xử lý nhanh hơn mà vẫn tuần tự | Concurrency tăng song song giữa partition; một partition chỉ được gán cho một consumer trong group tại một thời điểm |
| Listener submit task rồi return vẫn giữ ordering | Task có thể hoàn tất đảo thứ tự và offset có thể commit trước khi task xong |
| Producer retry không thể đảo thứ tự | Cần idempotence hoặc giới hạn in-flight requests phù hợp |
| Tăng partition count không ảnh hưởng key ordering | Key có thể được định tuyến sang partition mới sau khi mở rộng |

## Checklist trước khi bật retry cho luồng cần ordering

- Xác định ordering cần giữ ở mức partition, key hay aggregate.
- Producer dùng key ổn định để các event liên quan vào cùng partition.
- Producer idempotence và `max.in.flight.requests.per.connection` được cấu hình tương thích.
- Không xử lý bất đồng bộ rồi return trước khi công việc và offset được quản lý an toàn.
- Dùng blocking retry nếu record sau không được phép vượt record lỗi.
- Giới hạn số lần retry/backoff để tránh head-of-line blocking vô hạn.
- Chỉ dùng retry topic khi chấp nhận thay đổi ordering hoặc đã có version/sequence guard.
- DLT/replay có metadata nguồn và quy trình xử lý gap rõ ràng.
- Kiểm tra batch listener, transaction và giới hạn phiên bản Spring Kafka trước khi chọn retry mechanism.
- Kiểm thử event đầu lỗi, event sau thành công, retry thành công muộn và DLT replay.
- Theo dõi lag theo partition, retry duration, DLT và aggregate version gap.
- Đánh giá tác động khi tăng partition count hoặc thay partitioner.

Retry và partition ordering là một quyết định đánh đổi giữa tính đúng thứ tự và khả năng tiếp tục tiêu thụ. Blocking retry giữ record lỗi ở đầu luồng và bảo toàn thứ tự trong partition, nhưng có thể làm partition bị nghẽn. Retry topic giúp partition gốc tiến lên nhưng cho phép event sau được xử lý trước. Hãy chọn theo quan hệ nghiệp vụ giữa các event, kết hợp idempotency/version guard và kiểm thử thứ tự hoàn tất thực tế thay vì chỉ kiểm tra thứ tự offset.
