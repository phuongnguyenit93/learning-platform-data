# commitRecovered sau khi recover

Trong Spring Kafka, `commitRecovered` là tùy chọn giúp listener container **commit offset của record đã được error handler phục hồi thành công**. Cơ chế này thường được dùng cùng `DefaultErrorHandler` và một recoverer như `DeadLetterPublishingRecoverer` để chuyển record không thể xử lý sang Dead Letter Topic (DLT), sau đó đưa committed offset của consumer group qua record đó.

Điểm quan trọng là commit chỉ được thực hiện sau khi recovery callback hoàn tất thành công. Nếu gửi record sang DLT thất bại và recoverer báo lỗi, offset không được tiến lên như thể record đã được xử lý xong. Nhờ đó, record có thể được thử lại sau khi nguyên nhân phục hồi được khắc phục.

`commitRecovered` giải quyết một bước trong vòng đời xử lý lỗi: sau khi ứng dụng đã quyết định record được phục hồi bằng một hành động thay thế, Kafka cần ghi nhận tiến độ để consumer không tiếp tục mắc kẹt ở record đó. Nó không tự gửi record sang DLT, không sửa dữ liệu lỗi và không thay thế retry policy. Các hành động này thuộc về recoverer và error handler được cấu hình cùng nhau.

## 1. Vì sao cần commit sau khi recover?

Với consumer group, Kafka giao record dựa trên committed offset của từng topic-partition. Khi listener xử lý record thất bại, Spring Kafka có thể retry theo backoff. Nếu mọi lần retry đều thất bại, ứng dụng cần quyết định record sẽ được xử lý theo cách nào:

- Chuyển record sang DLT để điều tra và replay sau.
- Ghi record vào một hệ thống lưu trữ lỗi có thể phục hồi.
- Bỏ qua record sau khi đã ghi nhận rõ quyết định nghiệp vụ.
- Thực hiện một hành động thay thế do ứng dụng định nghĩa.

Sau khi hành động recovery thành công, consumer group cần tiến lên để tiếp tục xử lý record tiếp theo. Nếu không commit offset của record đã recover, lần poll hoặc lần khởi động tiếp theo có thể đưa record đó trở lại luồng xử lý. Ứng dụng có thể gửi lặp cùng record sang DLT hoặc lặp lại thao tác recovery.

Ví dụ partition `orders-0` có các offset liên tiếp:

| Offset | Kết quả xử lý |
|---:|---|
| 40 | Xử lý thành công |
| 41 | Listener lỗi, retry hết, được gửi sang DLT thành công |
| 42 | Chờ xử lý tiếp theo |

Nếu record 41 đã được recover thành công nhưng committed offset vẫn ở 41, consumer có thể nhận lại record 41 sau khi restart hoặc rebalance. Khi `commitRecovered` hoạt động đúng, container commit vị trí tiếp theo là 42. Consumer group có thể tiếp tục với record 42.

```text
Poll record 41
      |
      v
Listener ném exception
      |
      v
Retry theo BackOff
      |
      +---- còn retry ----> gọi listener lại
      |
      v hết retry
Recoverer xử lý record 41
      |
      +---- recovery thất bại ----> không commit recovered offset
      |
      v recovery thành công
commitRecovered
      |
      v
Committed offset tiến đến 42
      |
      v
Consumer tiếp tục với record 42
```

Trong ví dụ này, committed offset là vị trí tiếp theo cần đọc. Commit offset 42 có nghĩa group đã hoàn tất xử lý record 41 theo chính sách của ứng dụng, kể cả khi record được xử lý bằng cách chuyển sang DLT thay vì listener nghiệp vụ hoàn tất bình thường.

## 2. `commitRecovered` trong DefaultErrorHandler

Với listener container không dùng giao dịch Kafka cho mỗi lần xử lý, `DefaultErrorHandler` là cơ chế phổ biến để xử lý exception, retry và recovery. Có thể truyền một `ConsumerRecordRecoverer` vào handler. Khi retry đã hết, handler gọi recoverer cho record thất bại.

`DefaultErrorHandler.setCommitRecovered(true)` yêu cầu container commit offset của record sau khi recoverer hoàn tất thành công. Với `DefaultErrorHandler`, container phải sử dụng acknowledgment mode `MANUAL_IMMEDIATE` để hỗ trợ chức năng này.

Điều kiện này cần được cấu hình rõ ràng. `MANUAL` và `MANUAL_IMMEDIATE` không giống nhau: `MANUAL` để container phối hợp commit theo quy tắc batch, trong khi `MANUAL_IMMEDIATE` cho phép commit ngay khi acknowledgment được gọi trên consumer thread. `commitRecovered` yêu cầu `MANUAL_IMMEDIATE` để offset của record đã recover được commit đúng thời điểm.

### 2.1. Cấu hình listener container

Ví dụ cấu hình Java cho record listener:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
```

Với factory này, listener cần nhận `Acknowledgment` và acknowledge sau khi xử lý nghiệp vụ thành công. Khi listener ném exception, acknowledgment không được gọi; error handler sẽ retry và thực hiện recovery theo cấu hình. Khi recoverer hoàn tất, `commitRecovered` xử lý offset của record thất bại.

Nếu dùng Spring Boot auto-configuration, có thể đặt acknowledgment mode ở cấu hình listener tương ứng, nhưng cần xác nhận factory thực tế được dùng bởi listener. Nếu ứng dụng có nhiều `ConcurrentKafkaListenerContainerFactory`, cấu hình `MANUAL_IMMEDIATE` trên một factory không tự áp dụng cho các factory còn lại.

### 2.2. Cấu hình DefaultErrorHandler và DLT recoverer

Ví dụ dưới đây gửi record lỗi sang DLT có tên `<topic>.DLT` và giữ nguyên partition nguồn:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Báo lỗi nếu việc publish DLT thất bại.
    recoverer.setFailIfSendResultIsError(true);

    // 2 lần retry sau lần delivery đầu tiên.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.setCommitRecovered(true);
    return handler;
}
```

Trong ví dụ, record được giao lần đầu, sau đó có tối đa hai lần retry cách nhau một giây. Nếu vẫn lỗi, `DeadLetterPublishingRecoverer` gửi record sang DLT. `setFailIfSendResultIsError(true)` giúp lỗi publish DLT được chuyển thành lỗi recovery; nếu không, ứng dụng có thể không nhận biết kết quả gửi thất bại trước khi tiến trình recovery tiếp tục. Hãy kiểm tra API này theo phiên bản Spring Kafka đang sử dụng và cấu hình timeout gửi phù hợp.

`handler.setCommitRecovered(true)` bật việc commit offset sau recovery. Cấu hình này phải đi cùng factory có `AckMode.MANUAL_IMMEDIATE`. Nếu thiếu điều kiện acknowledgment mode, ứng dụng không thể dựa vào `commitRecovered` để đảm bảo offset được commit đúng như mong muốn.

### 2.3. Listener acknowledge khi xử lý thành công

Ví dụ listener sử dụng manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
```

Khi `applyIdempotently()` hoàn tất, listener acknowledge để container commit record thành công. Nếu phương thức nghiệp vụ ném exception, dòng acknowledge không chạy. Error handler nhận lỗi, thực hiện retry và sau cùng gọi recoverer nếu cần. Khi recoverer thành công, `commitRecovered` commit offset của record được phục hồi.

Không gọi `acknowledgment.acknowledge()` trong `finally` hoặc trước khi side effect hoàn tất. Làm như vậy có thể commit offset của record mà nghiệp vụ chưa xử lý thành công, khiến Kafka không giao lại record sau sự cố.

## 3. Trình tự commit sau recovery

Để hiểu chính xác thời điểm commit, cần tách ba kết quả:

1. **Listener thành công:** xử lý nghiệp vụ hoàn tất và listener acknowledge. Container commit offset theo acknowledgment mode.
2. **Listener thất bại nhưng còn retry:** error handler chờ backoff rồi giao lại record theo chính sách retry. Offset chưa được coi là đã xử lý thành công.
3. **Retry hết và recovery thành công:** recoverer hoàn tất hành động thay thế; `commitRecovered` yêu cầu container commit offset của record đó.

Nếu recoverer ném exception, handler không nên coi record đã recover. Với `DeadLetterPublishingRecoverer`, cần cấu hình để lỗi publish được phản ánh về caller, theo dõi timeout và bảo đảm serializer/topic đích sẵn sàng. Khi recovery thất bại, record cần được retry hoặc xử lý lại theo chính sách error handler; offset không được commit như một record đã recover thành công.

Ví dụ với offset `41`:

| Bước | Hành động | Committed offset |
|---|---|---:|
| Trước khi xử lý | Group bắt đầu tại offset 41 | 41 |
| Listener lỗi | Exception được chuyển tới error handler | 41 |
| Retry | Các lần thử lại chưa thành công | 41 |
| Publish DLT | Recoverer publish record 41 thành công | Chưa commit trong lúc recoverer đang chạy |
| Commit recovered | Container commit vị trí kế tiếp | 42 |
| Poll tiếp | Consumer đọc record tiếp theo | 42 |

Commit offset sau recovery không có nghĩa record lỗi đã được sửa hoặc xử lý thành công ở dịch vụ nghiệp vụ ban đầu. Nó có nghĩa ứng dụng đã hoàn tất hành động recovery được thiết kế và có thể tiếp tục luồng chính.

## 4. Điều gì xảy ra khi DLT publish thất bại?

Một lỗi quan trọng cần xử lý là DLT không thể nhận record. Nguyên nhân có thể gồm broker không sẵn sàng, topic chưa được tạo, ACL thiếu quyền, hết quota, serializer không hỗ trợ kiểu dữ liệu hoặc timeout mạng.

Nếu recoverer không báo lỗi publish, error handler có thể tiếp tục như thể recovery đã hoàn tất và offset có nguy cơ được commit. Vì vậy, với `DeadLetterPublishingRecoverer`, hãy bật cơ chế báo lỗi khi send result thất bại bằng `setFailIfSendResultIsError(true)` ở phiên bản hỗ trợ, đồng thời thiết lập timeout và quan sát kết quả gửi.

Khi DLT publish lỗi và recoverer ném exception:

- Không xem record là đã recover thành công.
- Không commit recovered offset cho record đó.
- Ghi nhận lỗi publish DLT riêng để phân biệt với exception ban đầu từ listener.
- Kiểm tra broker, quyền ghi, topic, partition và serializer của DLT.
- Cho phép error handler thực hiện lại recovery theo chính sách retry phù hợp.

Không để một DLT outage tạo thành retry storm. Cần giới hạn backoff, cảnh báo khi recovery liên tục thất bại và xác định cách tạm dừng hoặc giảm tốc consumer nếu DLT không thể phục vụ. Khi DLT trở lại, theo dõi số record được phục hồi và lag của consumer group.

## 5. DLT topic và metadata của record

DLT nên giữ đủ thông tin để điều tra và replay. `DeadLetterPublishingRecoverer` mặc định bổ sung các header mô tả nguồn và exception, chẳng hạn topic, partition, offset, timestamp và thông tin lỗi. Tên header cụ thể phụ thuộc phiên bản Spring Kafka.

Trong ví dụ dùng resolver `record.topic() + ".DLT"` và giữ nguyên partition nguồn, DLT phải có số partition đủ để nhận mọi partition của topic gốc. Nếu topic nguồn có partition 0 đến 11, DLT cần có ít nhất 12 partition khi resolver gửi record tới cùng partition index. Nếu DLT có ít partition hơn, cần dùng resolver khác để ánh xạ partition đích hợp lệ.

DLT cần được vận hành như một topic quan trọng:

- Có replication factor, `min.insync.replicas` và placement phù hợp.
- Có retention đủ dài cho thời gian điều tra và khắc phục.
- Có ACL chỉ cấp quyền đọc/ghi cho dịch vụ và nhóm vận hành cần thiết.
- Có dashboard theo dõi tốc độ record đi vào DLT và số record tồn đọng.
- Có quy trình replay được kiểm soát, giữ nguyên event ID và chống duplicate.
- Có cảnh báo khi publish DLT thất bại hoặc tỷ lệ recovery tăng bất thường.

Serializer của `KafkaTemplate` dùng để publish DLT phải xử lý được kiểu key/value thực tế. Khi lỗi xảy ra trong quá trình deserialize, value có thể là `byte[]` thay vì đối tượng domain. Nếu ứng dụng dùng nhiều kiểu value, cần cấu hình serializer phù hợp, ví dụ serializer phân loại theo kiểu dữ liệu hoặc template chuyên dụng cho DLT.

## 6. Recovery thành công không đồng nghĩa xử lý nghiệp vụ thành công

Giả sử listener xử lý một sự kiện thanh toán nhưng payload thiếu trường bắt buộc. Sau số lần retry được phép, recoverer gửi record sang DLT. Khi DLT nhận record và offset được commit, group có thể tiếp tục xử lý các thanh toán tiếp theo.

Điều đó không có nghĩa khoản thanh toán đã được thực hiện. Đội vận hành cần theo dõi DLT, xác định lỗi dữ liệu hoặc lỗi code, sửa nguyên nhân và quyết định có replay record hay không. Nếu record được sửa và replay, consumer cần có idempotency để tránh áp dụng side effect hai lần trong trường hợp lần xử lý trước đã hoàn tất một phần.

Vì vậy, nên phân biệt các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Processed | Listener hoàn tất xử lý nghiệp vụ theo hợp đồng của ứng dụng |
| Retried | Listener được gọi lại do lỗi tạm thời hoặc lỗi đang được thử khắc phục |
| Recovered | Recoverer hoàn tất hành động thay thế, ví dụ publish record sang DLT |
| Committed | Consumer group đã lưu tiến độ đọc qua record tương ứng |
| Replayed | Record được đưa trở lại luồng xử lý sau khi nguyên nhân lỗi được khắc phục |

Một record có thể ở trạng thái recovered và committed nhưng vẫn cần điều tra nghiệp vụ. Dashboard không nên gộp số record recovered vào số record xử lý nghiệp vụ thành công.

## 7. Khoảng trống giữa DLT publish và offset commit

Trong cấu hình không dùng Kafka transaction, publish record sang DLT và commit offset nguồn thường là hai thao tác riêng biệt. Có thể xảy ra tình huống:

1. DLT nhận record thành công.
2. Ứng dụng hoặc broker dừng trước khi offset nguồn được commit.
3. Consumer khởi động lại và đọc lại record nguồn.
4. Recoverer publish cùng record sang DLT thêm một lần nữa.

Đây là khả năng duplicate ở DLT. `commitRecovered` giảm việc đọc lại sau khi commit đã hoàn tất, nhưng không biến hai thao tác publish và commit thành một giao dịch nguyên tử trong chế độ không transactional.

Để xử lý duplicate:

- Giữ lại event ID và metadata nguồn trong DLT.
- Dùng bộ khóa deduplication như `originalTopic + originalPartition + originalOffset` khi cần nhận diện cùng một record nguồn.
- Làm cho quy trình replay idempotent.
- Theo dõi record trùng trong DLT và có quy trình đối soát.

Nếu cần bảo đảm nguyên tử giữa publish DLT và commit offset, cân nhắc transactional recovery với container giao dịch và `DefaultAfterRollbackProcessor`. Trong mô hình này, DLT publish và offset recovered có thể được thực hiện trong một Kafka transaction mới, nếu producer factory, transaction manager và processor được cấu hình phù hợp.

## 8. `commitRecovered` với transactional container

Khi listener container dùng Kafka transaction, exception trong listener thường làm transaction hiện tại rollback. Cơ chế xử lý sau rollback là `DefaultAfterRollbackProcessor`, không phải chỉ dựa vào `DefaultErrorHandler` cho luồng commit không transactional.

`DefaultAfterRollbackProcessor` có tùy chọn `commitRecovered`. Khi bật cùng `KafkaTemplate` transactional, processor có thể thực hiện recovery và commit offset của record đã recover trong một transaction mới. Điều này giúp DLT record và tiến độ consumer group được ghi nhận nguyên tử trong phạm vi Kafka transaction.

Ví dụ minh họa cấu hình processor:

```java
@Bean
DefaultAfterRollbackProcessor<String, OrderCreated>
orderAfterRollbackProcessor(
        KafkaTemplate<String, OrderCreated> transactionalTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    transactionalTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);

    DefaultAfterRollbackProcessor<String, OrderCreated> processor =
            new DefaultAfterRollbackProcessor<>(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    processor.setCommitRecovered(true);
    processor.setKafkaTemplate(transactionalTemplate);
    return processor;
}
```

Gắn processor vào listener container factory đang dùng transaction:

```java
factory.setAfterRollbackProcessor(orderAfterRollbackProcessor);
```

Đây là cấu hình minh họa cho phiên bản Spring Kafka hỗ trợ API tương ứng. `transactionalTemplate` phải dùng `ProducerFactory` có transaction ID prefix và transaction manager phù hợp với container. Không dùng template không transactional rồi kỳ vọng DLT publish và offset commit tự trở thành một giao dịch nguyên tử.

Với transactional recovery, cần kiểm tra transaction timeout, quyền truy cập DLT, serializer và cách xử lý khi transaction recovery bị abort. Nếu transaction mới thất bại, cả việc publish DLT và commit offset trong transaction đó không được xem là hoàn tất; record cần được xử lý lại theo chính sách phục hồi.

## 9. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `commitRecovered` không commit offset | Container không dùng `MANUAL_IMMEDIATE` trong cấu hình `DefaultErrorHandler` | Kiểm tra `ContainerProperties.AckMode` trên đúng listener factory |
| Record vẫn được giao lại sau khi đã gửi DLT | DLT publish thành công nhưng offset chưa commit; commit lỗi hoặc process dừng giữa hai thao tác | Kiểm tra commit result, bật `commitRecovered`, đánh giá duplicate DLT và transactional recovery |
| Record bị bỏ qua dù DLT publish thất bại | Recoverer không báo lỗi send result; error handler hiểu nhầm recovery đã hoàn tất | Cấu hình `setFailIfSendResultIsError(true)` trên phiên bản hỗ trợ và theo dõi lỗi publish |
| Listener thành công nhưng offset không tiến | Dùng `MANUAL_IMMEDIATE` nhưng listener không gọi acknowledge | Gọi `acknowledge()` sau xử lý thành công hoặc chọn acknowledgment mode phù hợp |
| Record bị gửi sang DLT sai partition | DLT không có partition tương ứng hoặc resolver ánh xạ sai | Tạo DLT đủ partition hoặc cấu hình destination resolver phù hợp |
| DLT có record nhưng không tìm được nguồn | Thiếu event ID hoặc metadata nguồn trong header/log | Giữ metadata gốc và thiết kế correlation/deduplication key |
| Lỗi recovery lặp lại liên tục | DLT broker/ACL/serializer hỏng hoặc backoff không phù hợp | Sửa nguyên nhân, giới hạn retry, cảnh báo và giảm tốc consumer khi cần |
| DLT tăng mạnh sau release | Phiên bản mới gây lỗi schema, mapping hoặc dependency | Dừng rollout/rollback, phân loại exception và xác định tập record cần replay |

Một lỗi phổ biến là bật `commitRecovered` nhưng quên `MANUAL_IMMEDIATE`. Lỗi khác là cấu hình manual immediate nhưng listener không acknowledge các record xử lý thành công. Hai điều kiện này phải được kiểm tra cùng nhau trong cấu hình thực tế.

## 10. Quan sát recovery và committed offset

Để biết `commitRecovered` có hoạt động đúng, cần theo dõi các chỉ số ở cả listener, recoverer và consumer group:

- Số lần listener thất bại và số lần retry theo exception type.
- Số record recover thành công và số record recover thất bại.
- Tỷ lệ publish DLT thành công, lỗi và timeout.
- Consumer lag và committed offset theo từng partition.
- Số lần record nguồn được giao lại sau recovery.
- Số record DLT đang chờ điều tra hoặc replay.
- Thời gian từ lần xử lý đầu tiên đến khi recovery và commit hoàn tất.

Log recovery nên có topic nguồn, partition, offset, event ID, topic DLT, exception class và kết quả commit nếu có thể quan sát. Không ghi payload nhạy cảm vào log. Tránh dùng event ID hoặc offset riêng lẻ làm metric label có cardinality cao; hãy lưu chúng trong log hoặc trace.

Một quy trình xác nhận sau khi bật cấu hình:

1. Gửi một record hợp lệ và xác nhận listener xử lý, acknowledge, committed offset tiến lên.
2. Gửi một record khiến listener lỗi có thể retry; xác nhận số lần gọi listener theo BackOff.
3. Để retry hết; xác nhận recoverer gửi record sang đúng DLT và giữ metadata nguồn.
4. Xác nhận committed offset tiến qua record đã recover.
5. Khởi động lại consumer hoặc thực hiện rebalance có kiểm soát; xác nhận record đã recover không bị xử lý lại từ topic nguồn.
6. Mô phỏng DLT publish thất bại; xác nhận recovery báo lỗi và offset không được commit như một record đã recover.
7. Với transactional recovery, mô phỏng transaction abort để xác nhận DLT publish và offset commit cùng rollback.

## 11. Quy trình vận hành khi recovery không hoạt động

Khi record liên tục quay lại dù đã được gửi sang DLT, hãy điều tra theo trình tự:

1. Xác định group ID, topic, partition và offset của record nguồn.
2. Kiểm tra log của `DefaultErrorHandler` hoặc `DefaultAfterRollbackProcessor` để biết recoverer đã được gọi chưa.
3. Kiểm tra DLT có nhận record hay không, kết quả send future và lỗi publish.
4. Xác minh đúng listener container factory có `MANUAL_IMMEDIATE` nếu dùng `DefaultErrorHandler.setCommitRecovered(true)`.
5. Kiểm tra cấu hình transaction nếu đang dùng `DefaultAfterRollbackProcessor`.
6. Đối chiếu committed offset trước và sau recovery với log end offset.
7. Kiểm tra process restart, rebalance và commit exception ở thời điểm recovery.
8. Sau khi sửa, gửi lại record thử nghiệm và xác nhận không còn duplicate ngoài dự kiến.

Không reset offset thủ công chỉ để che giấu lỗi commit. Reset tiến lên có thể bỏ qua record; reset lùi có thể tạo replay và side effect trùng. Nếu phải reset, ghi lại offset cũ, offset mới và kế hoạch đối soát.

## 12. Nguyên tắc triển khai production

Khi triển khai `commitRecovered`, đội vận hành cần xác nhận các điểm sau:

1. Xác định rõ listener sử dụng `DefaultErrorHandler` không transactional hay `DefaultAfterRollbackProcessor` trong transactional container.
2. Với `DefaultErrorHandler`, cấu hình `AckMode.MANUAL_IMMEDIATE` trên đúng listener container factory.
3. Với manual acknowledgment, listener chỉ acknowledge sau khi side effect nghiệp vụ hoàn tất.
4. Bật `setCommitRecovered(true)` trên đúng error handler/processor.
5. Cấu hình recoverer có kết quả gửi đáng tin cậy; với DLT publishing, lỗi send phải được phản ánh về recovery.
6. DLT có đủ partition, replication, retention, ACL và serializer phù hợp.
7. Phân biệt rõ số record nghiệp vụ xử lý thành công với số record đã recovered.
8. Có idempotency/deduplication cho khả năng duplicate do crash giữa publish DLT và commit offset trong luồng không transactional.
9. Nếu cần nguyên tử, dùng transactional recovery với transaction manager và KafkaTemplate tương ứng.
10. Kiểm thử cả recovery thành công, DLT publish thất bại, commit failure, restart, rebalance và transaction abort.

`commitRecovered` giúp consumer group tiến qua một record sau khi hành động recovery đã hoàn tất. Khi kết hợp đúng acknowledgment mode, recoverer, DLT và cơ chế quan sát, ứng dụng có thể cô lập record lỗi mà vẫn tiếp tục xử lý luồng chính. Chất lượng của cơ chế này phụ thuộc vào việc xác định recovery thành công một cách đáng tin cậy và kiểm soát khoảng trống giữa publish record lỗi với commit offset.
