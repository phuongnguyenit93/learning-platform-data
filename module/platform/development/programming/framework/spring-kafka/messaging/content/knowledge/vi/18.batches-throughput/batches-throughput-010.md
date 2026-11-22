# BatchToRecordAdapter

## 1. BatchToRecordAdapter giải quyết vấn đề gì?

Kafka consumer lấy dữ liệu bằng `poll()`. Một lần poll có thể trả về nhiều record từ một hoặc nhiều partition. Spring Kafka hỗ trợ batch listener để chuyển cả nhóm record đó vào một lần gọi phương thức listener. Cách này phù hợp khi nghiệp vụ xử lý theo lô, nhưng đôi khi ứng dụng vẫn cần xử lý và phục hồi lỗi theo từng record.

`BatchToRecordAdapter` là cơ chế kết hợp hai cách tiếp cận: listener container vẫn hoạt động ở chế độ batch, nhưng adapter lần lượt chuyển từng record trong batch đến một phương thức record listener. Nhờ vậy, ứng dụng có thể tận dụng poll theo lô trong khi logic nghiệp vụ nhận từng sự kiện riêng lẻ.

Adapter đặc biệt hữu ích khi:

- Muốn listener nhận từng payload để dễ viết logic nghiệp vụ.
- Muốn nhận diện record cụ thể gây lỗi trong một batch.
- Muốn phục hồi hoặc chuyển DLT cho một record rồi tiếp tục xử lý các record còn lại.
- Dùng batch listener container với transaction nhưng cần xử lý lỗi ở mức record.

`BatchToRecordAdapter` được Spring Kafka bổ sung từ phiên bản 2.4.2. API và chi tiết tích hợp có thể thay đổi theo phiên bản, vì vậy hãy đối chiếu tài liệu của Spring Kafka mà ứng dụng đang dùng.

## 2. Cách adapter hoạt động

Khi factory bật `batchListener`, consumer poll một nhóm record. Thay vì gọi listener một lần với `List<T>`, `BatchToRecordAdapter` duyệt các message trong batch và gọi callback cho từng record. Callback này được nối với record-oriented listener method.

```text
Kafka topic partitions
          |
          v
   KafkaConsumer.poll()
          |
          v
    Batch of records
          |
          v
  BatchToRecordAdapter
          |
          +---- record 1 ----> @KafkaListener(payload)
          |
          +---- record 2 ----> @KafkaListener(payload)
          |
          +---- record 3 ----> @KafkaListener(payload)
          |
          +---- record N ----> @KafkaListener(payload)
```

Điểm quan trọng là container vẫn nhận một poll batch. Adapter chỉ thay đổi cách chuyển batch tới phương thức ứng dụng. Nó không tạo thêm consumer, không tạo partition mới và không biến mỗi record thành một request poll độc lập.

Một batch có thể chứa record từ nhiều partition. Offset được quản lý riêng theo từng `TopicPartition`; adapter không tạo ra thứ tự tổng thể giữa các partition.

## 3. Phân biệt ba mô hình listener

| Mô hình | Chế độ container | Tham số listener | Đơn vị gọi phương thức |
|---|---|---|---|
| Record listener thông thường | Record | `T` hoặc `ConsumerRecord<K,V>` | Một record mỗi lần gọi |
| Batch listener | Batch | `List<T>`, `List<ConsumerRecord<K,V>>` hoặc `ConsumerRecords<K,V>` | Một batch mỗi lần gọi |
| Batch container + `BatchToRecordAdapter` | Batch | `T` hoặc `ConsumerRecord<K,V>` | Adapter gọi record listener từng record trong batch |

Ví dụ record listener thông thường:

```java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderCreated event) {
    orderService.process(event);
}
```

Ví dụ batch listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchListenerFactory")
public void listenBatch(List<OrderCreated> events) {
    orderService.processBatch(events);
}
```

Ví dụ dùng batch container với adapter vẫn nhận từng record:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchToRecordListenerFactory")
public void listenOne(OrderCreated event) {
    orderService.process(event);
}
```

Ở ví dụ thứ ba, factory được cấu hình `setBatchListener(true)` và có `BatchToRecordAdapter`. Phương thức vẫn nhận một `OrderCreated` mỗi lần gọi. Không đổi tham số thành `List<OrderCreated>` nếu muốn adapter gọi record listener.

## 4. Cấu hình DefaultBatchToRecordAdapter

Spring Kafka cung cấp `DefaultBatchToRecordAdapter`. Có thể cấu hình nó trên `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchToRecordListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setBatchToRecordAdapter(new DefaultBatchToRecordAdapter<>());
        factory.setConcurrency(3);
        return factory;
    }
}
```

Sau đó khai báo listener nhận một record:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchToRecordListenerFactory")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
```

Factory này tạo consumer batch và adapter gọi `onOrder()` lần lượt cho các payload trong batch. `concurrency=3` tạo tối đa ba consumer member cho endpoint trên mỗi application instance; số consumer có partition còn phụ thuộc số partition được gán trong group.

Nếu ứng dụng chỉ cần record listener thông thường, không cần cấu hình batch container chỉ để có callback từng record. Hãy dùng adapter khi muốn chủ động giữ batch container và cần cách xử lý lỗi record-level bên trong batch.

## 5. Cấu hình recoverer cho record lỗi

`DefaultBatchToRecordAdapter` có hai constructor thường dùng:

- Constructor không tham số: dùng recoverer mặc định chỉ ghi log record lỗi.
- Constructor nhận `ConsumerRecordRecoverer`: cho phép ứng dụng chỉ định cách phục hồi record lỗi.

Ví dụ dùng recoverer tùy chỉnh để ghi nhận record lỗi:

```java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error("Cannot process topic={}, partition={}, offset={}",
            record.topic(), record.partition(), record.offset(), exception);
    failedRecordRepository.save(record, exception);
};

factory.setBatchToRecordAdapter(
        new DefaultBatchToRecordAdapter<>(recoverer));
```

`ConsumerRecordRecoverer` nhận record gốc và exception từ lần gọi listener thất bại. Nếu recoverer xử lý xong và trả về bình thường, adapter tiếp tục với record kế tiếp trong batch. Nếu recoverer ném exception, batch bị abort; container có thể áp dụng error handling hoặc rollback theo cấu hình.

Đây là khác biệt quan trọng khi dùng constructor mặc định: recoverer mặc định chỉ log rồi tiếp tục. Log lỗi không đồng nghĩa record đã được lưu DLT hoặc xử lý nghiệp vụ thành công. Nếu cần bảo toàn record lỗi, hãy cấu hình recoverer có hành động phục hồi rõ ràng.

## 6. Chuyển record lỗi sang Dead Letter Topic

Một cách phục hồi phổ biến là dùng `DeadLetterPublishingRecoverer` làm `ConsumerRecordRecoverer`:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
batchToRecordListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaTemplate<Object, Object> dltTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchToRecordAdapter(
            new DefaultBatchToRecordAdapter<>(
                    new DeadLetterPublishingRecoverer(dltTemplate)));
    return factory;
}
```

Khi listener ném exception, adapter gọi recoverer với record lỗi. Nếu DLT publish thành công và recoverer trả về bình thường, adapter tiếp tục xử lý record tiếp theo. Nếu DLT publish thất bại và recoverer ném exception, batch bị abort để container xử lý theo cơ chế lỗi hiện có.

Khi triển khai DLT, cần cấu hình:

- DLT topic tồn tại và có số partition phù hợp với chiến lược định tuyến.
- Producer template serialize được key/value gốc và headers cần giữ lại.
- Retention, quyền truy cập và quy trình theo dõi DLT rõ ràng.
- Có cách replay record sau khi sửa lỗi dữ liệu hoặc consumer.

Nếu record có kiểu payload không đồng nhất hoặc chứa raw `byte[]` từ lỗi deserialization, template DLT cần serializer hỗ trợ các kiểu dữ liệu thực tế. Không giả định một `JsonSerializer` đơn giản luôn xử lý được mọi record lỗi.

## 7. Luồng xử lý lỗi theo từng record

Giả sử poll trả về ba record: `OrderCreated A`, `OrderCreated B`, `OrderCreated C`. Listener xử lý A thành công, B ném exception, còn C hợp lệ.

Với adapter và recoverer có thể phục hồi B:

```text
Poll batch: [A, B, C]
       |
       v
Adapter gọi listener(A) ── thành công
       |
       v
Adapter gọi listener(B) ── exception
       |
       v
Recoverer xử lý B (ví dụ publish DLT)
       |
       +── recoverer trả về bình thường
       |          |
       |          v
       |     Adapter tiếp tục
       |          |
       |          v
       |     Adapter gọi listener(C)
       |
       +── recoverer ném exception
                  |
                  v
             Abort batch
             container error handling / rollback
```

Khi recoverer trả về bình thường, adapter xem record lỗi đã được xử lý theo chính sách recoverer và tiếp tục batch. Vì vậy, recoverer cần thực sự hoàn tất hành động cần thiết trước khi trả về. Nếu chỉ ghi log nhưng nghiệp vụ yêu cầu phải giữ lại record, dữ liệu có thể bị bỏ qua sau khi batch được commit.

Nếu recoverer ném exception, container nhận biết batch chưa hoàn tất. Với container transactional, transaction có thể rollback và batch được xử lý lại theo cấu hình `AfterRollbackProcessor`. Với non-transactional container, hành vi retry/seek phụ thuộc error handler, AckMode và phiên bản Spring Kafka.

## 8. Quan hệ với transaction của batch listener

Khi dùng transaction với batch listener thông thường, nếu listener ném exception, Spring Kafka mặc định không biết record nào trong batch gây lỗi. Vì vậy, cả batch có thể được redeliver sau rollback.

`BatchToRecordAdapter` giải quyết một phần vấn đề này: container vẫn nhận batch, nhưng listener được gọi từng record. Adapter có thể gọi recoverer cho record thất bại và tiếp tục record sau nếu phục hồi thành công. Nếu recoverer ném exception, batch có thể bị abort để transaction rollback.

Điều này cho phép chọn chính sách rõ hơn:

| Kết quả xử lý record | Hành vi adapter |
|---|---|
| Listener thành công | Tiếp tục record tiếp theo |
| Listener lỗi, recoverer phục hồi thành công | Đánh dấu record đã được xử lý theo chính sách recoverer và tiếp tục |
| Listener lỗi, recoverer ném exception | Abort batch; container xử lý lỗi hoặc rollback |

Adapter không tự tạo một Kafka transaction độc lập cho từng record. Ranh giới transaction vẫn do listener container và transaction manager quyết định. Nếu container chạy một transaction cho batch, nhiều lần gọi record listener có thể nằm trong cùng transaction đó.

Nếu cần đảm bảo output Kafka và offset được commit nguyên tử, hãy cấu hình Kafka transaction đúng cách. Nếu listener cập nhật database hoặc gọi hệ thống ngoài Kafka, cần thiết kế phối hợp transaction hoặc idempotency phù hợp; `BatchToRecordAdapter` không tự cung cấp exactly-once cho side effect bên ngoài.

## 9. AckMode và commit offset

`BatchToRecordAdapter` không thay thế cơ chế commit offset của listener container. Adapter điều khiển việc gọi record listener và recoverer; container vẫn quản lý offset theo AckMode, transaction và trạng thái xử lý của batch.

Một số nguyên tắc:

- Không gọi `acknowledge()` trước khi listener hoặc recoverer hoàn tất hành động cần thiết.
- Nếu recoverer trả về bình thường sau khi lưu DLT, record có thể được xem là đã phục hồi để batch tiếp tục.
- Nếu recoverer ném exception, batch bị abort và offset chưa được commit theo cách hoàn tất bình thường của batch.
- Khi dùng manual acknowledgment, xác định rõ ai sở hữu việc acknowledge: listener, adapter tùy chỉnh hay quy trình xử lý batch.
- Không tự commit offset bằng consumer API bên trong callback nếu container đang quản lý commit, trừ khi có thiết kế nâng cao được kiểm soát rõ.

BatchToRecordAdapter không biến batch container thành record container. Vì vậy, đừng mặc định mọi đặc tính của record listener container như `AckMode.RECORD` hoặc ranh giới commit per-record đều tự động áp dụng. Kiểm tra tài liệu phiên bản và cấu hình thực tế trước khi dựa vào semantics commit cụ thể.

## 10. Ordering khi adapter xử lý từng record

Default adapter duyệt danh sách record theo thứ tự được cung cấp và gọi callback lần lượt. Điều này giữ trình tự invocation theo batch. Tuy nhiên, Kafka chỉ bảo đảm thứ tự trong một partition; một batch có thể chứa nhiều partition và không có thứ tự toàn cục giữa chúng.

Nếu listener xử lý đồng bộ, record cùng partition được gọi theo thứ tự đọc. Nếu listener tự gửi tác vụ sang executor hoặc trả về trước khi side effect hoàn tất, thứ tự hoàn tất nghiệp vụ có thể khác thứ tự invocation.

Ví dụ không nên làm nếu nghiệp vụ cần tuần tự:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchToRecordListenerFactory")
public void onOrder(OrderCreated event) {
    executor.submit(() -> orderService.process(event));
}
```

Listener trả về ngay sau khi submit, nên adapter có thể chuyển sang record tiếp theo trong khi xử lý trước vẫn đang chạy. Nếu các sự kiện của cùng `orderId` phụ thuộc thứ tự, hãy xử lý đồng bộ hoặc xây dựng cơ chế tuần tự hóa theo key/partition và chỉ acknowledge sau khi công việc cần thiết hoàn tất.

## 11. BatchToRecordAdapter có tăng throughput không?

Adapter không tự làm tăng throughput. Consumer vẫn poll theo batch, nhưng ứng dụng thực hiện một lần gọi listener cho mỗi record. Lợi ích chủ yếu là giữ batch polling trong khi có semantics xử lý lỗi theo record.

So với batch listener nhận `List<T>`:

- Có thể mất lợi ích bulk operation vì service được gọi từng record.
- Dễ xác định record lỗi và chuyển riêng record đó sang DLT.
- Có thêm chi phí callback/invocation cho từng record.
- Có thể giảm chi phí poll so với những mô hình tự thiết kế poll nhỏ, nhưng không nhất thiết nhanh hơn record listener container thông thường.

Nếu mục tiêu chính là bulk insert hoặc xử lý vector hóa, batch listener thực sự thường phù hợp hơn. Nếu mục tiêu là record-level recovery trong batch container hoặc transaction, `BatchToRecordAdapter` là lựa chọn đáng cân nhắc.

Hãy đo throughput, p95/p99 processing latency, số lần recover, DLT publish rate, batch size và consumer lag trước khi kết luận adapter cải thiện hiệu năng.

## 12. Tùy chỉnh BatchToRecordAdapter

Ứng dụng có thể dùng `DefaultBatchToRecordAdapter` với `ConsumerRecordRecoverer` hoặc triển khai `BatchToRecordAdapter` riêng khi cần điều khiển sâu hơn. Interface nhận danh sách Spring `Message<?>`, danh sách `ConsumerRecord<K,V>`, acknowledgment, consumer và callback để xử lý từng message.

Một custom adapter có thể:

- Thêm metric trước/sau mỗi record.
- Gắn context nghiệp vụ khi gọi callback.
- Phân loại exception để chọn recoverer phù hợp.
- Thực hiện quy tắc phục hồi riêng cho từng loại event.
- Quyết định tiếp tục hay abort batch theo chính sách ứng dụng.

Khi tự triển khai, cần giữ các nguyên tắc:

1. Không bỏ qua record hoặc callback ngoài chủ đích.
2. Không nuốt exception nếu record chưa được phục hồi an toàn.
3. Không acknowledge vượt qua record chưa hoàn tất.
4. Giữ metadata và headers của record khi chuyển tiếp hoặc DLT.
5. Không chạy callback đồng thời nếu chưa có thiết kế ordering/offset rõ ràng.
6. Kiểm thử shutdown, rebalance và exception của recoverer.

Nếu chỉ cần ghi DLT hoặc lưu record lỗi, `DefaultBatchToRecordAdapter` với recoverer thường đơn giản và dễ bảo trì hơn custom adapter.

## 13. Khi nào nên dùng BatchToRecordAdapter?

| Nhu cầu | Lựa chọn |
|---|---|
| Xử lý từng record độc lập, không cần batch container | Record listener thông thường |
| Bulk insert hoặc xử lý toàn bộ danh sách cùng nhau | Batch listener nhận `List<T>` |
| Dùng batch container nhưng gọi business listener từng record | `BatchToRecordAdapter` |
| Cần DLT riêng cho record lỗi trong batch | `DefaultBatchToRecordAdapter` với `DeadLetterPublishingRecoverer` |
| Cần transaction theo batch nhưng phân loại lỗi từng record | Batch container kết hợp adapter và recoverer phù hợp |
| Cần retry từng record với lịch retry độc lập, không chặn partition | Đánh giá retry topic/non-blocking retry; BatchToRecordAdapter tự nó không cung cấp lịch retry đó |

Không dùng adapter chỉ vì tên có chữ “batch”. Nó không biến phương thức record listener thành bulk listener và không tự quản lý retry policy phức tạp. Chọn adapter khi cần sự kết hợp cụ thể giữa poll batch và callback record.

## 14. Kiểm thử BatchToRecordAdapter

Kiểm thử tích hợp nên xác minh số lần gọi listener, cách xử lý lỗi và kết quả offset:

1. **Batch thành công:** gửi nhiều record và xác nhận listener được gọi một lần cho mỗi record trong poll batch.
2. **Record lỗi giữa batch:** cho record thứ hai ném exception, xác nhận recoverer nhận đúng record và record sau có được xử lý theo chính sách hay không.
3. **Recoverer trả về bình thường:** xác nhận adapter tiếp tục record tiếp theo.
4. **Recoverer ném exception:** xác nhận batch bị abort và container error handler hoặc transaction rollback hoạt động theo cấu hình.
5. **DLT:** xác nhận record lỗi được publish đúng topic, giữ key/value/header cần thiết và không làm mất record gốc.
6. **Transaction:** xác nhận hành vi commit/rollback khi listener hoặc recoverer lỗi.
7. **Ordering:** gửi chuỗi sự kiện cùng key và xác nhận invocation theo thứ tự partition; kiểm tra thêm nếu listener dispatch tác vụ bất đồng bộ.
8. **Rebalance/restart:** dừng consumer giữa batch, xác nhận record chưa commit có thể được giao lại và xử lý idempotent.
9. **Throughput:** so sánh batch listener, record listener và batch-to-record với cùng payload, partition count và workload.

Ghi `eventId`, topic, partition, offset và kết quả recover vào log test để xác định chính xác record nào đã thành công, record nào được DLT và record nào bị giao lại.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener nhận `List<T>` thay vì từng payload | Factory chạy batch mode nhưng chưa cấu hình `BatchToRecordAdapter`, hoặc listener signature được thiết kế cho batch | Gắn adapter vào đúng factory và dùng tham số record/payload đơn |
| Listener được gọi từng record nhưng batch vẫn rollback toàn bộ | Recoverer ném exception hoặc transaction batch bị abort | Kiểm tra exception gốc, recoverer và transaction boundary |
| Record lỗi chỉ được log rồi biến mất khỏi luồng chính | Đang dùng constructor mặc định chỉ log và tiếp tục | Cấu hình recoverer lưu bền vững hoặc publish DLT |
| Record sau không được xử lý sau một lỗi | Recoverer ném exception làm abort batch | Kiểm tra DLT publish, repository và chính sách abort/retry |
| DLT publish thất bại | Serializer không hỗ trợ kiểu record hoặc topic/permission sai | Kiểm tra template, serializer, topic và ACL |
| Nghĩ adapter tự retry record lỗi | Adapter chỉ gọi recoverer; nó không tự cung cấp backoff/retry schedule | Thiết kế recoverer hoặc error handling/transaction phù hợp |
| Thứ tự nghiệp vụ bị đảo | Listener trả về trước khi tác vụ nền hoàn tất | Xử lý đồng bộ hoặc tuần tự hóa theo partition/key |
| Không tăng throughput như kỳ vọng | Mỗi record vẫn cần một lần gọi listener; bottleneck nằm ở downstream | Đo batch size, thời gian xử lý và cân nhắc batch listener bulk thật sự |

## 16. Quy trình triển khai

1. Xác định cần batch polling vì throughput/transaction hay chỉ cần record listener thông thường.
2. Cấu hình factory `setBatchListener(true)`.
3. Gắn `DefaultBatchToRecordAdapter` hoặc custom adapter vào đúng factory.
4. Khai báo listener nhận một payload hoặc `ConsumerRecord`.
5. Chọn recoverer: ghi nhận lỗi, lưu quarantine hoặc publish DLT.
6. Quy định rõ recoverer trả về bình thường khi nào và ném exception khi nào.
7. Cấu hình AckMode/transaction phù hợp; không giả định commit per-record chỉ vì callback từng record.
8. Kiểm thử lỗi giữa batch, DLT, rollback, redelivery và ordering.
9. Đo throughput/latency/lag để xác nhận adapter phù hợp với workload.

## 17. Tổng kết

- `BatchToRecordAdapter` thích hợp khi container poll theo batch nhưng ứng dụng muốn gọi record listener từng record.
- Spring Kafka cung cấp `DefaultBatchToRecordAdapter` từ phiên bản 2.4.2.
- Có thể cấu hình adapter bằng `factory.setBatchToRecordAdapter(...)` sau khi bật `setBatchListener(true)`.
- `DefaultBatchToRecordAdapter` nhận `ConsumerRecordRecoverer`; nếu recoverer trả về bình thường, adapter tiếp tục record kế tiếp; nếu recoverer ném exception, batch bị abort.
- Constructor mặc định chỉ log record lỗi rồi tiếp tục; cần recoverer rõ ràng nếu phải lưu hoặc chuyển DLT.
- Adapter không tự tạo transaction per-record, không tự cung cấp retry schedule và không tự bảo đảm exactly-once.
- Commit offset vẫn do listener container quản lý theo AckMode/transaction; cần xác minh semantics theo phiên bản.
- Kafka giữ thứ tự trong partition; xử lý bất đồng bộ bên trong listener vẫn có thể làm đảo thứ tự hoàn tất nghiệp vụ.
- Adapter không tự tăng throughput; hãy chọn nó vì nhu cầu record-level recovery trong batch container và đo hiệu năng thực tế.

Với `BatchToRecordAdapter`, ứng dụng có thể giữ cách poll theo batch trong khi xử lý từng record theo logic nghiệp vụ riêng. Khi kết hợp đúng recoverer, DLT và transaction, luồng consumer có thể cô lập record lỗi mà vẫn kiểm soát được tiến độ và khả năng phục hồi của batch.

## Tài liệu tham khảo

- [Spring Kafka Reference — Transactions with Batch Listeners](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka API — DefaultBatchToRecordAdapter](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/adapter/DefaultBatchToRecordAdapter.html)
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
