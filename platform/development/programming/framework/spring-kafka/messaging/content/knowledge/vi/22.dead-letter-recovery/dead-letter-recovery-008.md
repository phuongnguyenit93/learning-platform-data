# Thực hiện recovery sau số lần thử

Retry cho listener cơ hội xử lý lại một record khi lỗi có thể chỉ là tạm thời. Tuy nhiên, số lần thử cần có giới hạn. Khi `BackOff` hết lượt hoặc exception được phân loại là không retry, Spring Kafka chuyển sang bước recovery để quyết định cách xử lý record thất bại. Một lựa chọn phổ biến là gửi record sang dead-letter topic (DLT) để điều tra và phát lại sau.

Recovery là bước kết thúc một chu kỳ xử lý lỗi tại consumer. Cần cấu hình rõ record được chuyển đi đâu, làm sao biết việc chuyển đã thành công và khi nào offset được phép tiến lên.

## 1. Recoverer được gọi khi nào?

Trong Spring Kafka 2.8 trở lên, `DefaultErrorHandler` dùng `BackOff` để điều phối retry. Khi listener ném exception, handler kiểm tra loại exception và trạng thái backoff:

- Nếu exception có thể retry và còn lượt, handler chờ theo backoff rồi giao record lại cho listener.
- Nếu exception không retry, handler bỏ qua các lượt còn lại và gọi recoverer.
- Nếu đã hết lượt retry, handler gọi recoverer để xử lý record thất bại.

Recoverer nhận `ConsumerRecord` cùng exception đã làm listener thất bại. Với record listener, kiểu hợp đồng này được biểu diễn bởi `ConsumerRecordRecoverer`. Recoverer có thể ghi log, lưu thông tin lỗi vào hệ thống khác, bỏ qua record theo chính sách được phê duyệt hoặc publish record sang DLT.

```java
public interface ConsumerRecordRecoverer {
    void accept(ConsumerRecord<?, ?> record, Exception exception);
}
```

Nếu recoverer hoàn tất bình thường, error handler xem record đã được phục hồi. Nếu recoverer ném exception, recovery chưa hoàn tất; record có thể tiếp tục đi qua cơ chế xử lý lỗi của container. Vì vậy, recoverer phải chỉ trả về bình thường sau khi hành động recovery cần thiết đã hoàn tất.

## 2. Chuyển record sang DLT bằng DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` là recoverer có sẵn của Spring Kafka. Nó dùng `KafkaTemplate` để publish record thất bại sang một topic khác, thường có hậu tố `.DLT`.

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);

    // Xem lỗi gửi DLT là lỗi recovery để container không âm thầm bỏ qua.
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

Với destination resolver mặc định, record từ topic `orders` được chuyển đến `orders.DLT` và giữ số partition tương ứng với partition nguồn. Vì thế, nếu topic nguồn có nhiều partition, DLT cần có đủ partition để nhận các record được định tuyến theo cách này.

`FixedBackOff(1_000L, 2L)` cho phép hai lần retry sau lần xử lý đầu tiên. Khi cả ba lần xử lý đều thất bại, recoverer publish record sang DLT. `InvalidOrderException` được đánh dấu không retry nên record thuộc lỗi này đi thẳng đến recovery.

## 3. Tùy chỉnh topic nhận record lỗi

Trong thực tế, có thể muốn DLT theo từng loại sự kiện, theo tenant hoặc theo nhóm lỗi. `DeadLetterPublishingRecoverer` nhận một destination resolver để chọn topic và partition đích:

```java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) -> {
            String dltTopic = record.topic() + ".DLT";
            return new TopicPartition(dltTopic, record.partition());
        });
```

Resolver có thể dựa trên topic nguồn, partition, key hoặc loại exception. Hãy bảo đảm topic đích tồn tại và partition được chọn hợp lệ. Nếu định tuyến về cùng số partition nguồn, DLT cần có số partition ít nhất tương ứng; nếu gom vào một partition, cần đánh giá tải và thứ tự xử lý.

Không nên tạo topic đích dựa trên nội dung exception một cách tùy tiện. Tên topic nên có quy ước ổn định, được quản lý và có chính sách retention rõ ràng để dữ liệu lỗi không tồn tại vô thời hạn.

## 4. Bảo đảm việc publish DLT được xác nhận

Một lỗi quan trọng là listener thất bại, nhưng chính thao tác gửi record sang DLT cũng thất bại. Ví dụ, broker không sẵn sàng, topic đích chưa tồn tại hoặc producer gặp lỗi serialization. Nếu handler xem recovery là thành công trong khi record chưa được lưu vào DLT, consumer có thể commit offset và làm mất khả năng xử lý lại record.

Với `DeadLetterPublishingRecoverer`, `setFailIfSendResultIsError(true)` yêu cầu recoverer xem lỗi từ kết quả gửi là lỗi recovery và ném exception tương ứng. Cách này giúp error handler biết việc publish chưa thành công. Hãy kiểm tra API theo phiên bản Spring Kafka đang sử dụng và cấu hình timeout chờ kết quả gửi phù hợp với môi trường.

Producer của `KafkaTemplate` phải có serializer tương thích với key và value. Điều này đặc biệt quan trọng khi xử lý lỗi deserialize: record có thể chứa byte array gốc hoặc value không được chuyển đổi thành kiểu domain mong muốn. Ứng dụng cần cấu hình template có thể gửi được cả dạng dữ liệu lỗi mà luồng recovery thực tế nhận được.

`DeadLetterPublishingRecoverer` bổ sung các header chứa thông tin nguồn, thường gồm topic, partition, offset và exception. Khi tiêu thụ DLT, dùng các header này để xác định record gốc và nguyên nhân lỗi. Không chỉ dựa vào nội dung exception trong log vì record cần được truy vết ngay cả khi log đã hết thời gian lưu.

## 5. Offset tiến lên sau recovery như thế nào?

Kafka lưu offset theo từng partition. Khi recoverer hoàn tất và error handler trả về bình thường, `DefaultErrorHandler` mặc định cho phép container xác nhận tiến độ sau khi xử lý lỗi thông qua `ackAfterHandle` (mặc định là `true`). Offset thực tế được commit theo `AckMode` và cơ chế commit của container.

Có tùy chọn `commitRecovered` để handler tự commit offset của record đã phục hồi; tùy chọn này yêu cầu `AckMode.MANUAL_IMMEDIATE`. Chỉ bật khi ứng dụng chủ động dùng acknowledgement thủ công và đã xác định rõ nơi commit offset.

Nếu recoverer ném exception vì gửi DLT thất bại, recovery chưa hoàn tất. Record không được xem là đã xử lý xong; error handler tiếp tục áp dụng cơ chế xử lý lỗi theo cấu hình. Đây là lý do cần kiểm tra kết quả gửi DLT trước khi cho phép luồng offset tiến lên.

## 6. Tự viết recoverer cho nghiệp vụ riêng

Không phải hệ thống nào cũng cần DLT. Một số ứng dụng muốn lưu record lỗi vào bảng audit hoặc phát tín hiệu cho một quy trình vận hành riêng. Có thể triển khai `ConsumerRecordRecoverer` bằng lambda hoặc class riêng:

```java
@Bean
public DefaultErrorHandler kafkaErrorHandler(FailureAuditService auditService) {
    ConsumerRecordRecoverer recoverer = (record, exception) -> {
        auditService.saveFailure(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.value(),
            exception.getClass().getName(),
            exception.getMessage());
    };

    return new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
}
```

Ví dụ chỉ trả về sau khi `saveFailure` hoàn tất. Nếu lưu audit thất bại, service nên ném runtime exception để recovery được xem là thất bại. Khi ghi cơ sở dữ liệu, cần có khóa idempotent dựa trên topic, partition, offset hoặc event ID: ứng dụng có thể chạy lại record nếu tiến trình dừng sau khi lưu audit nhưng trước khi Kafka commit offset.

Nếu chính sách là bỏ qua một loại record, hãy thể hiện rõ bằng recoverer có log và metric, đồng thời ghi lại metadata cần thiết. Một recoverer rỗng hoặc chỉ bắt exception rồi bỏ qua có thể làm mất dữ liệu nghiệp vụ mà không ai nhận ra.

## 7. Xử lý batch listener

Với batch listener, recovery phụ thuộc vào cách listener báo vị trí record lỗi. Khi ném `BatchListenerFailedException` với index hợp lệ, `DefaultErrorHandler` có thể xử lý phần record trước lỗi và tập trung retry/recover record thất bại cùng phần còn lại theo semantics của batch. Nếu listener ném exception không chỉ ra record, handler có thể phải retry hoặc phục hồi toàn bộ batch theo nhánh fallback.

Nếu batch listener cần chuyển đúng một record sang DLT, hãy cung cấp index chính xác trong `BatchListenerFailedException` và kiểm thử cả record đứng trước, record lỗi và record đứng sau. Đừng tự suy ra index từ Kafka offset: index là vị trí trong danh sách batch, còn offset thuộc về partition.

## 8. Phát lại record từ DLT

DLT là nơi cách ly record cần điều tra; nó không tự sửa dữ liệu hoặc tự đưa record trở lại luồng chính. Quy trình replay nên có các bước:

1. Đọc metadata nguồn từ header DLT để xác định topic, partition, offset và exception ban đầu.
2. Phân tích nguyên nhân, sửa dữ liệu hoặc triển khai bản sửa lỗi trước khi replay.
3. Gửi record về topic đích hoặc một luồng replay có kiểm soát, giữ event ID để truy vết.
4. Ghi nhận kết quả replay và giới hạn số lần phát lại; nếu tiếp tục thất bại, record quay lại quy trình recovery.

Consumer replay cần idempotent vì record có thể được gửi lại hoặc xử lý lại nếu offset chưa được commit. Nếu record gây side effect ở cơ sở dữ liệu, hãy dùng event ID với unique constraint hoặc lưu dấu xử lý trong cùng transaction dữ liệu.

## 9. Kiểm thử recovery và các tình huống lỗi

Một kiểm thử tích hợp nên tạo record khiến listener thất bại liên tục, xác minh số lần retry, rồi xác nhận record xuất hiện trên DLT với đúng key, payload và header nguồn. Tiếp theo, kiểm thử exception không retry để xác minh recovery xảy ra ngay sau lần đầu.

Cần có thêm các trường hợp:

- Topic DLT không tồn tại hoặc producer không gửi được record.
- Serializer không xử lý được kiểu key/value thực tế.
- Recoverer tùy chỉnh ném exception khi lưu audit.
- Ứng dụng dừng sau khi recovery hoàn tất nhưng trước khi offset được commit.
- Record được replay nhiều lần nhưng nghiệp vụ vẫn không tạo side effect trùng.

Dùng Embedded Kafka hoặc Testcontainers để xác minh hành vi broker, consumer và offset. Có thể dùng Awaitility để đợi record xuất hiện trên DLT thay vì sleep cố định. Kiểm thử cần xác nhận recovery thất bại không làm offset tiến lên như thể record đã được xử lý.

## 10. Theo dõi khi vận hành

Theo dõi số record được chuyển sang DLT theo topic nguồn, exception type, tỷ lệ publish DLT thất bại, tuổi của record cũ nhất trong DLT và số lần replay. Cảnh báo khi DLT tăng đột biến hoặc publish recovery lỗi kéo dài. Đặt retention đủ dài cho việc điều tra, nhưng cũng cần quy trình dọn dữ liệu sau khi hết thời hạn lưu trữ.

Recovery hoàn tất khi hành động đã chọn được xác nhận thành công: publish DLT, lưu audit hoặc một quyết định bỏ qua có chủ đích. Kết hợp recoverer đáng tin cậy, xác nhận kết quả gửi, commit offset đúng thời điểm và quy trình replay idempotent sẽ giúp luồng Spring Kafka xử lý được record lỗi mà vẫn giữ khả năng truy vết và khôi phục.
