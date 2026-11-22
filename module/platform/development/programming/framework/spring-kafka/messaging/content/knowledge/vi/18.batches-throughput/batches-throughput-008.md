# Lỗi một record trong batch

Khi dùng Spring Kafka ở chế độ batch, một lần gọi `@KafkaListener` nhận nhiều record từ một lần `poll()` của Kafka. Nếu xử lý một record bị lỗi và listener ném exception, cả lần gọi batch bị xem là thất bại. Vì vậy, cách báo lỗi cần cho Spring Kafka biết chính xác record nào gây ra lỗi; nếu không, framework có thể phải phát lại toàn bộ batch.

Spring Kafka 2.8 trở lên cung cấp `BatchListenerFailedException` để chỉ ra vị trí record lỗi và `DefaultErrorHandler` để điều phối retry, phục hồi hoặc chuyển record sang dead-letter topic (DLT).

## 1. Vì sao một record có thể làm batch bị phát lại?

Một batch listener thường nhận `List<ConsumerRecord<K, V>>` hoặc một danh sách payload đã được convert. Ví dụ, batch có bốn record và record thứ ba không hợp lệ. Nếu listener chỉ ném `RuntimeException`, error handler không biết record nào đã xử lý thành công và record nào cần thử lại. Với lỗi không cung cấp vị trí, `DefaultErrorHandler` xử lý theo nhánh fallback và retry toàn bộ batch.

Điều này ảnh hưởng trực tiếp đến throughput. Những record đã xử lý xong có thể chạy lại, làm tăng thời gian xử lý và tạo tác dụng phụ trùng lặp nếu nghiệp vụ không idempotent.

## 2. Báo đúng vị trí record lỗi

Với batch listener, hãy bắt lỗi tại vòng lặp xử lý và ném `BatchListenerFailedException` cùng chỉ số của record trong danh sách. Chỉ số bắt đầu từ `0` và phải trỏ đúng phần tử đã gây lỗi.

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-processor",
    containerFactory = "batchKafkaListenerContainerFactory")
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record = records.get(index);
        try {
            orderService.process(record.value());
        } catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Cannot process record at batch index " + index, ex, index);
        }
    }
}
```

Ở ví dụ này, `index` là vị trí trong danh sách mà listener nhận được, không phải Kafka offset. Offset là số thứ tự của record trong một partition; chỉ số batch là vị trí của record trong danh sách hiện tại. Hai giá trị này có thể khác nhau.

Nếu listener nhận `List<OrderCreated>` thay vì `List<ConsumerRecord<String, OrderCreated>>`, chỉ số vẫn phải khớp với vị trí payload trong danh sách. Dùng `ConsumerRecord` khi cần log hoặc kiểm tra thêm topic, partition, offset và key.

Không nên bắt exception rồi chỉ ghi log và kết thúc listener như thể xử lý thành công. Khi listener trả về bình thường, container có thể commit offset theo acknowledgement mode đang dùng; record lỗi khi đó bị bỏ qua ở tầng nghiệp vụ.

## 3. Cấu hình retry và DLT bằng DefaultErrorHandler

`DefaultErrorHandler` là common error handler cho record listener và batch listener trong Spring Kafka 2.8+. Với batch listener, nó dùng `BatchListenerFailedException` để xác định vị trí lỗi. Ta có thể cấu hình backoff cho lỗi tạm thời và `DeadLetterPublishingRecoverer` để gửi record không thể xử lý sang DLT.

```java
@Bean
public DefaultErrorHandler batchErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT", record.partition()));

    // Lần xử lý đầu tiên, sau đó tối đa 2 lần retry, mỗi lần cách nhau 1 giây.
    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));

    // Lỗi dữ liệu không thể sửa bằng retry sẽ được chuyển thẳng sang DLT.
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

Gắn handler vào container factory đang bật batch mode:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler batchErrorHandler) {
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(batchErrorHandler);
    return factory;
}
```

`FixedBackOff(1_000L, 2L)` có nghĩa là chờ một giây giữa các lần thử lại và cho phép hai lần retry sau lần xử lý đầu tiên. Hãy đặt số lần retry phù hợp với loại lỗi: lỗi mạng ngắn hạn có thể cần retry; dữ liệu sai định dạng hoặc vi phạm quy tắc nghiệp vụ thường không tự hết lỗi khi thử lại.

Trong ví dụ DLT, record được gửi đến topic có hậu tố `.DLT` và giữ nguyên partition nguồn. Topic DLT vì vậy cần có đủ partition tương ứng với các partition nguồn. Producer dùng cho `KafkaTemplate` cũng phải có serializer phù hợp với key và value được gửi sang DLT.

## 4. Điều gì xảy ra với offset khi một record lỗi?

Kafka lưu offset riêng cho từng partition. Một batch có thể chứa record từ nhiều partition, nên offset được commit theo partition chứ không phải bằng một số thứ tự chung của batch.

| Cách listener báo lỗi | Cách xử lý của `DefaultErrorHandler` |
| --- | --- |
| Ném `BatchListenerFailedException` có chỉ số | Commit tiến độ của các record đứng trước record lỗi; seek record lỗi và các record còn lại để chúng được đọc lại. Khi hết retry, recoverer xử lý record lỗi. |
| Ném exception khác, không chỉ ra record lỗi | Retry toàn bộ batch theo nhánh fallback. Khi hết retry, recoverer được gọi cho các record trong batch. |
| Bắt lỗi, chỉ log rồi trả về | Listener được xem là hoàn tất; container tiếp tục quy trình commit offset theo acknowledgement mode. Record có thể bị bỏ qua ở tầng nghiệp vụ. |

Ví dụ, một partition có các offset `100`, `101`, `102`, `103`; listener xử lý thành công hai record đầu rồi lỗi ở offset `102`. Khi listener báo đúng chỉ số của record lỗi, Spring Kafka có thể commit tiến độ đến trước offset `102` và seek để đọc lại từ record lỗi. Record `100` và `101` không cần bị xử lý lại chỉ vì `102` thất bại.

Nếu batch chứa nhiều partition, hãy nhớ rằng mỗi partition có tiến độ riêng. Không suy ra offset đã commit chỉ bằng cách lấy chỉ số phần tử trong danh sách cộng thêm một.

## 5. Chọn retry, bỏ qua hay chuyển DLT

Hãy phân loại lỗi theo khả năng tự phục hồi:

- **Lỗi tạm thời:** timeout, dịch vụ phụ thuộc tạm mất kết nối hoặc lỗi tranh chấp ngắn hạn. Retry có backoff và giới hạn số lần.
- **Lỗi dữ liệu cố định:** thiếu trường bắt buộc, giá trị không hợp lệ hoặc payload không thể chuyển đổi. Chuyển DLT sớm để điều tra và xử lý lại sau khi dữ liệu được sửa.
- **Lỗi lập trình:** null ngoài dự kiến hoặc vi phạm invariant trong code. Cần log đầy đủ và cảnh báo; retry nhiều lần thường chỉ làm chậm consumer.

DLT nên giữ đủ thông tin để truy vết: topic, partition, offset, key, payload, thời điểm lỗi và metadata exception do recoverer cung cấp. Khi phát lại từ DLT, cần có quy trình kiểm soát để tránh đưa cùng một sự kiện vào hệ thống nhiều lần.

## 6. Bảo vệ nghiệp vụ khỏi xử lý trùng

Retry là một phần bình thường của messaging. Một record có thể được giao lại sau lỗi, rebalance, restart hoặc khi consumer chưa commit offset. Vì thế, handler nghiệp vụ nên có tính idempotent: xử lý cùng một event nhiều lần vẫn tạo ra cùng kết quả cuối cùng.

Một số cách thường dùng:

- Dùng `eventId` ổn định và lưu dấu đã xử lý bằng unique constraint trong cơ sở dữ liệu.
- Thực hiện cập nhật dữ liệu và ghi dấu xử lý trong cùng transaction của cơ sở dữ liệu.
- Chỉ xác nhận xử lý sau khi side effect đã được lưu bền vững.
- Nếu phát sinh event Kafka từ một thay đổi cơ sở dữ liệu, cân nhắc transactional outbox để tránh khoảng hở giữa commit DB và publish Kafka.

Kafka transaction có thể phối hợp việc đọc offset và ghi record Kafka trong một transaction Kafka. Nó không tự động làm cho thao tác với cơ sở dữ liệu bên ngoài trở thành exactly-once. Với container có bật transaction, lỗi listener thường đi qua cơ chế rollback và `DefaultAfterRollbackProcessor`; không áp dụng nguyên xi cấu hình `DefaultErrorHandler` ở trên mà không kiểm tra mô hình transaction của ứng dụng.

## 7. Kiểm thử trường hợp một record lỗi

Một bài kiểm thử batch nên tạo ít nhất ba record trong cùng partition: record đầu hợp lệ, record thứ hai gây lỗi và record thứ ba hợp lệ. Sau đó xác minh:

1. Listener báo đúng chỉ số của record thứ hai bằng `BatchListenerFailedException`.
2. Record đứng trước lỗi không bị xử lý lặp lại khi handler đã commit tiến độ của nó.
3. Record lỗi được retry đúng số lần và được chuyển sang DLT khi hết retry hoặc thuộc nhóm không retry.
4. Record đứng sau lỗi tiếp tục được xử lý sau khi record lỗi được recover.
5. Khi phát lại cùng `eventId`, nghiệp vụ không tạo side effect trùng.

Có thể dùng Embedded Kafka hoặc Testcontainers để kiểm tra hành vi thực của consumer, offset và DLT. Nên kiểm tra thêm trường hợp exception không phải `BatchListenerFailedException`, vì trường hợp đó có thể khiến toàn bộ batch được retry.

## 8. Những điểm cần theo dõi khi vận hành

Theo dõi consumer lag theo partition, thời gian xử lý mỗi batch, số lần retry, số record vào DLT và tỷ lệ batch thất bại. Nếu một record lỗi làm throughput giảm mạnh, kiểm tra xem listener đã nêu đúng index chưa, backoff có quá dài không và batch có đang quá lớn so với thời gian xử lý cho phép của consumer hay không.

Khi tăng `concurrency`, số consumer trong cùng group không thể vượt quá số partition đang được phân công hữu ích. Batch listener xử lý batch trên từng consumer; tăng concurrency không loại bỏ được một record lỗi và cũng không thay thế việc thiết kế retry, DLT và idempotency.

## Kết luận

Với batch listener, hãy nêu rõ vị trí record gây lỗi bằng `BatchListenerFailedException`. Kết hợp `DefaultErrorHandler`, backoff và DLT để kiểm soát retry; hiểu offset theo từng partition để dự đoán record nào sẽ được đọc lại. Cuối cùng, thiết kế xử lý idempotent để việc retry không làm sai lệch dữ liệu nghiệp vụ.
