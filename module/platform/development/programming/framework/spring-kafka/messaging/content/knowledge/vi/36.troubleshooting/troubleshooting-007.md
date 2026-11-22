# Offset commit không như mong đợi

Offset commit là mốc Kafka lưu lại để consumer group biết vị trí sẽ tiếp tục đọc sau khi consumer restart hoặc partition được assign cho consumer khác. Khi offset không tăng, tăng muộn, nhảy qua record chưa xử lý hoặc khiến record bị giao lại, nguyên nhân thường nằm ở acknowledgment mode, cách listener kết thúc, error handler, transaction hoặc consumer group rebalance.

Để chẩn đoán đúng, cần tách ba sự kiện: consumer đã poll record, listener đã xử lý xong và broker đã lưu committed offset. Ba thời điểm này không nhất thiết trùng nhau. Một record xử lý thành công vẫn có thể được giao lại nếu commit thất bại; ngược lại, commit quá sớm có thể khiến record bị bỏ qua dù nghiệp vụ chưa hoàn tất.

## 1. Committed offset là vị trí tiếp theo sẽ đọc

Kafka lưu offset theo quy ước vị trí tiếp theo mà consumer group sẽ đọc. Nếu listener xử lý thành công record có offset `42`, vị trí commit thông thường là `43`.

```text
Partition orders-0:

offset:       40    41    42    43    44
              |     |     |     |     |
listener:     done  done  done  next  next
                            |
committed offset --------> 43
                            |
restart sẽ tiếp tục từ 43
```

Committed offset không phải offset của record cuối cùng đã xử lý; nó là offset tiếp theo cần đọc. Vì vậy, nếu dashboard hiển thị `CURRENT-OFFSET=43`, record `42` đã nằm trước vị trí tiếp tục đọc theo committed offset.

Consumer còn có `position`, là vị trí tiếp theo sẽ nhận khi poll. Position có thể đi xa hơn committed offset khi consumer đã poll hoặc xử lý record nhưng chưa commit. Khi consumer restart, position trong bộ nhớ mất đi và group tiếp tục từ committed offset đã lưu trên broker.

## 2. Spring Kafka quản lý commit bằng AckMode

Với listener container, Spring Kafka quản lý offset theo `ContainerProperties.AckMode`. Từ Spring Kafka 2.3, nếu không cấu hình rõ `enable.auto.commit`, container mặc định đặt nó thành `false` để container kiểm soát commit theo acknowledgment mode.

| AckMode | Khi nào container commit offset? | Trường hợp thường dùng |
| --- | --- | --- |
| `RECORD` | Sau khi từng record listener xử lý thành công | Muốn commit theo từng record |
| `BATCH` | Sau khi tất cả record trong poll được xử lý thành công | Mặc định phổ biến; giảm số lần commit |
| `TIME` | Khi đủ thời gian commit đã cấu hình, tại ranh giới xử lý poll | Muốn giới hạn thời gian giữa các lần commit |
| `COUNT` | Khi đủ số record đã xử lý, tại ranh giới xử lý poll | Muốn giới hạn số record giữa các lần commit |
| `COUNT_TIME` | Khi đạt điều kiện thời gian hoặc số record | Kết hợp hai ngưỡng |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; commit được thực hiện theo ranh giới batch/poll | Listener quyết định record nào đã hoàn tất |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge trên consumer thread; nếu gọi từ thread khác, yêu cầu được xử lý theo luồng container | Cần xác nhận offset ngay tại điểm acknowledge |

Với record listener, `RECORD` có thể commit sau từng lần gọi listener. Với batch listener, container xử lý một batch trong một lần gọi nên ranh giới commit tương ứng với batch và acknowledgment của batch. Hãy đối chiếu kiểu listener và AckMode thực tế thay vì suy luận chỉ từ annotation.

Ví dụ cấu hình `RECORD`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
```

Nếu không chỉ định AckMode, container thường dùng `BATCH`. Việc đổi sang `RECORD` có thể tăng số lần commit và ảnh hưởng throughput; cần cân nhắc cùng yêu cầu redelivery và tải broker.

## 3. Auto commit và container-managed commit

Kafka consumer có thuộc tính `enable.auto.commit`. Khi bật, Kafka client tự commit offset theo chu kỳ `auto.commit.interval.ms`, độc lập với thời điểm listener hoàn tất công việc. Đây là nguồn gây hiểu nhầm nếu ứng dụng kỳ vọng commit chỉ xảy ra sau xử lý nghiệp vụ.

Spring Kafka listener container mặc định tắt auto commit nếu ứng dụng chưa cấu hình thuộc tính này. Nên để container quản lý acknowledgment và commit thông qua AckMode. Tránh bật `enable.auto.commit=true` trong ứng dụng dùng `@KafkaListener` trừ khi đã hiểu rõ hệ quả và có chủ đích đặc biệt.

Ví dụ cấu hình consumer rõ ràng:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
```

`auto-offset-reset` không điều khiển commit thường xuyên. Nó chỉ được dùng khi group chưa có committed offset hợp lệ hoặc offset đã nằm ngoài phạm vi log hiện có. `earliest` bắt đầu từ phần dữ liệu còn lưu sớm nhất; `latest` bắt đầu từ cuối log; `none` làm consumer báo lỗi khi không có offset hợp lệ.

## 4. Manual acknowledgment phải đặt đúng thời điểm

Khi dùng `MANUAL` hoặc `MANUAL_IMMEDIATE`, listener nhận `Acknowledgment` và chủ động xác nhận record sau khi công việc đã hoàn tất:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    private final OrderService orderService;

    OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "manualAckListenerFactory")
    public void onOrder(OrderCreated event, Acknowledgment acknowledgment) {
        orderService.handleAndPersist(event);
        acknowledgment.acknowledge();
    }
}
```

Factory phải được cấu hình `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`. Trong ví dụ, service phải hoàn tất side effect bền vững trước khi acknowledge. Nếu gọi `acknowledge()` ngay sau khi đưa event vào một queue chỉ nằm trong bộ nhớ, offset có thể được commit trong khi worker chưa xử lý xong; khi ứng dụng crash, event có thể bị mất khỏi quy trình nghiệp vụ.

Với `MANUAL_IMMEDIATE`, lời gọi acknowledge trên consumer thread có thể kích hoạt commit ngay. Nếu gọi từ thread khác, container phải chuyển yêu cầu về luồng consumer và việc commit không còn mang ý nghĩa tức thời tại chính thread gọi. Tránh chia sẻ acknowledgment tùy tiện giữa nhiều thread.

## 5. Vì sao listener thành công nhưng offset vẫn chưa tăng?

Đây có thể là hành vi đúng theo AckMode:

- Với `BATCH`, record đầu tiên trong poll đã xử lý xong nhưng container còn chờ các record khác của poll hoàn tất.
- Với `TIME`, `COUNT` hoặc `COUNT_TIME`, ngưỡng commit có thể chưa đạt.
- Với `MANUAL`, listener chưa gọi `acknowledge()` hoặc các acknowledgment của poll chưa đủ điều kiện commit.
- Với transaction, offset chỉ có hiệu lực khi transaction commit.
- Consumer position đã tiến nhưng committed offset vẫn phản ánh mốc commit trước đó.

Không nên coi committed offset đứng yên trong vài mili giây là lỗi ngay lập tức. Hãy xem AckMode, thời gian xử lý poll, commit interval và trạng thái transaction trước khi kết luận.

Nếu offset không tăng lâu hơn giới hạn vận hành, kiểm tra listener có bị block, acknowledgment có được gọi, commit có lỗi và consumer group có đang rebalance hay không.

## 6. Khi listener ném exception

Nếu listener ném exception, container không coi lần xử lý đó là thành công. `CommonErrorHandler` hoặc `DefaultErrorHandler` quyết định retry, seek, recover và thời điểm offset có thể được xác nhận.

Luồng phổ biến với `DefaultErrorHandler`:

1. Listener xử lý record và ném exception.
2. Error handler áp dụng retry/backoff cho exception được phân loại retryable.
3. Nếu retry thành công, container tiếp tục theo AckMode và commit policy.
4. Nếu retry hết hoặc exception không retryable, recoverer xử lý record, ví dụ gửi sang DLT.
5. Nếu recovery thành công và error handler trả về bình thường, offset của record đã phục hồi có thể được commit theo cấu hình error handler/container.

`DefaultErrorHandler` có tùy chọn `ackAfterHandle` (mặc định bật trong các phiên bản hiện đại) để container xác nhận offset của record khi error handler đã xử lý lỗi và trả về bình thường. Tùy chọn `commitRecovered` dùng để yêu cầu commit offset của record đã recover trong chế độ `MANUAL_IMMEDIATE`; cần cấu hình đúng AckMode theo tài liệu phiên bản Spring Kafka đang dùng.

Nếu đặt `ackAfterHandle=false`, container không tự xác nhận offset chỉ vì error handler đã trả về bình thường. Hãy chọn giá trị này khi có quy trình acknowledgment riêng và kiểm thử kỹ để tránh record đã recover bị giao lại ngoài dự kiến.

Nếu recoverer ném exception vì không gửi được DLT hoặc không lưu được record, recovery chưa hoàn tất. Đừng bắt rồi nuốt exception recovery, vì container có thể hiểu sai rằng record đã được xử lý.

## 7. Listener error handler có thể làm offset commit

`KafkaListenerErrorHandler` chạy ở tầng adapter của `@KafkaListener`. Nếu handler bắt exception và trả về bình thường, container có thể xem lời gọi listener đã kết thúc thành công. Khi đó offset có thể được commit theo AckMode dù nghiệp vụ ban đầu thất bại.

Ví dụ không nên dùng nếu muốn container retry:

```java
@Bean
KafkaListenerErrorHandler unsafeSwallowingHandler() {
    return (message, exception) -> {
        System.getLogger("listener-error").log(
                System.Logger.Level.ERROR, "Listener failed", exception);
        return null; // Adapter coi lỗi đã được xử lý
    };
}
```

Nếu muốn `DefaultErrorHandler` thực hiện retry hoặc recovery, listener error handler cần ném exception tiếp thay vì trả về bình thường. Chỉ trả về bình thường khi handler đã thực hiện một hành động phục hồi bền vững và chủ động chấp nhận không retry.

## 8. Commit trong Kafka transaction

Khi listener container dùng Kafka transaction, output record được gửi qua `KafkaTemplate` và offset đầu vào có thể được đưa vào cùng transaction. Offset chỉ được lưu cùng kết quả output khi transaction commit thành công.

```text
Begin Kafka transaction
        |
        v
Listener xử lý record đầu vào
        |
        v
KafkaTemplate.send(output record)
        |
        v
Send offset đầu vào vào transaction
        |
        v
Commit transaction
   /             \
commit           abort
  |                |
output + offset   không có output/offset được commit
đều có hiệu lực   input có thể được đọc lại
```

Nếu listener ném exception, transaction abort, output không được consumer `read_committed` nhìn thấy và input offset chưa commit trong transaction đó. Nếu transaction timeout hoặc producer bị fencing, commit có thể thất bại dù listener đã chạy xong. Hãy kiểm tra transaction coordinator, transaction ID prefix, timeout và rebalance.

Kafka transaction chỉ bao phủ tài nguyên Kafka. Nếu listener cập nhật database rồi Kafka transaction abort, database không tự rollback theo. Side effect ngoài Kafka cần idempotency hoặc Outbox/phối hợp transaction riêng.

## 9. Commit thất bại và record bị giao lại

Một commit có thể thất bại do:

- Consumer mất partition assignment trong lúc rebalance.
- `CommitFailedException` hoặc `RebalanceInProgressException` xảy ra khi group generation đã thay đổi hoặc rebalance chưa hoàn tất.
- Broker/coordinator tạm thời không sẵn sàng hoặc request commit timeout.
- Transaction bị abort, timeout hoặc producer bị fencing.
- Ứng dụng dừng trước khi commit được gửi hoặc xác nhận.

Nếu listener đã hoàn tất nghiệp vụ nhưng commit chưa được broker lưu, record có thể được giao lại sau restart hoặc rebalance. Đây là lý do consumer cần idempotent: cùng một event ID có thể được nhận nhiều lần mà không tạo side effect lặp.

Đừng kết luận rằng record đã mất chỉ vì offset không tăng. Trước hết xác minh record có được giao lại, có nằm trong retry/DLT hay bị bỏ qua bởi offset reset. Nếu commit lỗi, log cần có group ID, topic, partition, offset, consumer ID và nguyên nhân commit để truy vết.

## 10. Rebalance và thời gian xử lý listener

Consumer group có thể rebalance khi consumer mới tham gia, consumer cũ rời group, subscription thay đổi hoặc consumer không poll đúng hạn. Nếu listener xử lý quá lâu và vượt `max.poll.interval.ms`, broker có thể xem consumer không còn đáp ứng poll loop và chuyển partition sang thành viên khác.

Khi partition bị revoke, commit offset có thể không còn hợp lệ nếu consumer đã mất quyền sở hữu hoặc group generation thay đổi. Điều này có thể làm commit thất bại và record được giao lại.

Hãy kiểm tra:

- Thời gian xử lý một record/batch so với `max.poll.interval.ms`.
- Consumer có bị block bởi REST, database, lock hoặc `Thread.sleep()` không.
- Số record mỗi poll và `max.poll.records` có quá lớn không.
- `session.timeout.ms`, heartbeat và rebalance rate.
- Log `onPartitionsRevoked`/`onPartitionsAssigned` hoặc các listener/container event tương ứng.

Tăng `max.poll.interval.ms` không tự sửa được listener bị treo. Cần tối ưu xử lý, giới hạn batch, dùng pause/backpressure có kiểm soát hoặc tách tác vụ bất đồng bộ với acknowledgment an toàn.

## 11. Acknowledgment bất đồng bộ và thứ tự ack

Nếu listener xử lý record bất đồng bộ hoặc nhiều record từ cùng poll hoàn tất không theo thứ tự, việc commit offset cần được thiết kế cẩn thận. Kafka chỉ lưu một committed offset liên tục cho mỗi partition. Không thể commit qua một record chưa hoàn tất mà vẫn kỳ vọng record đó chắc chắn được giao lại.

Spring Kafka hỗ trợ `asyncAcks` trong các phiên bản hiện đại để cho phép acknowledgment không theo thứ tự đối với các record của cùng một poll. Container giữ các acknowledgment cho đến khi khoảng trống được lấp đầy và có thể pause consumer trong lúc chờ. Cơ chế này giúp xử lý song song, nhưng có thể làm tăng khả năng redelivery sau crash; cần kiểm thử với version đang dùng.

Với listener trả về kiểu bất đồng bộ được Spring Kafka hỗ trợ, container có thể dùng cơ chế acknowledgment gắn với completion của future/result. Chỉ acknowledge khi tác vụ thực sự hoàn tất. Không trả về bình thường trước khi future hoàn tất rồi hy vọng container tự biết worker còn chạy.

## 12. Phân biệt auto offset reset với commit

`auto.offset.reset` chỉ quyết định vị trí bắt đầu khi group chưa có committed offset hợp lệ. Nó không làm commit offset thường xuyên và không sửa một commit bị lỗi.

| Giá trị | Hành vi khi không có offset hợp lệ |
| --- | --- |
| `earliest` | Đọc từ offset sớm nhất còn tồn tại trong log |
| `latest` | Bắt đầu từ cuối log, bỏ qua dữ liệu cũ hơn vị trí bắt đầu |
| `none` | Ném lỗi nếu không tìm thấy committed offset hợp lệ |

Nếu committed offset nằm trước log start offset vì retention đã xóa dữ liệu cũ, consumer có thể gặp `OffsetOutOfRangeException`; khi đó reset policy có thể được áp dụng. Đừng thay `auto.offset.reset` chỉ để che lỗi commit. Hãy xác định group đang thiếu offset, offset ngoài phạm vi hay commit thực sự không thành công.

## 13. Chẩn đoán bằng kafka-consumer-groups

Kiểm tra committed offset và lag theo group:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group order-service
```

Các cột cần xem:

| Cột | Ý nghĩa |
| --- | --- |
| `CURRENT-OFFSET` | Committed offset của group; vị trí tiếp theo sẽ đọc |
| `LOG-END-OFFSET` | End offset được công cụ dùng để tính lag |
| `LAG` | Khoảng cách offset giữa end và committed offset |
| `CONSUMER-ID` | Consumer đang được assign partition |
| `CLIENT-ID` | Client ID dùng để nhận diện consumer |

Nếu `CURRENT-OFFSET` đứng yên, so sánh với consumer position/record rate và log commit. Nếu không có consumer ID, group có thể đang không có thành viên hoặc partition chưa được assign. Kiểm tra trạng thái group:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group order-service `
  --state
```

Tên option và cột đầu ra có thể khác theo phiên bản Kafka CLI. Kết hợp CLI với log của Spring Kafka container và metric commit để xác định nguyên nhân.

## 14. Checklist điều tra offset commit

Thực hiện theo thứ tự để tránh đổi cấu hình khi chưa xác định nguyên nhân:

1. Xác nhận đúng `group.id`, topic và partition; kiểm tra group có đang ổn định hay rebalance.
2. Đọc AckMode của listener container; xác định commit theo record, batch, time/count hay manual.
3. Kiểm tra `enable.auto.commit`; với Spring Kafka container thông thường, nên để container quản lý commit.
4. Xác định listener đã kết thúc bình thường, ném exception hay listener error handler đã nuốt exception.
5. Nếu manual ack, tìm đường code gọi `acknowledge()` và xác nhận nó chạy sau khi side effect bền vững hoàn tất.
6. Nếu có error handler, kiểm tra retry, recoverer, `ackAfterHandle` và `commitRecovered`.
7. Nếu dùng transaction, kiểm tra transaction commit/abort, timeout và fencing.
8. Kiểm tra commit exception, rebalance, `max.poll.interval.ms` và thời gian xử lý listener.
9. So sánh committed offset với consumer position và end offset; không nhầm khoảng cách position với committed lag.
10. Nếu record bị giao lại, kiểm tra idempotency và event ID để tránh side effect trùng.

## 15. Những cấu hình và lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener xử lý xong nhưng offset chưa tăng | AckMode `BATCH`, `TIME`, `COUNT`; chưa ack; transaction chưa commit | Kiểm tra ranh giới commit và trạng thái transaction |
| Offset tăng trước khi xử lý nghiệp vụ hoàn tất | Auto commit hoặc listener trả về sau khi chỉ enqueue tác vụ | Tắt auto commit; acknowledge sau xử lý bền vững |
| Record bị xử lý lặp sau restart | Commit thất bại hoặc crash sau side effect trước commit | Làm consumer idempotent và kiểm tra commit log |
| Offset nhảy qua record lỗi | Listener error handler trả về bình thường hoặc recoverer đánh dấu thành công | Kiểm tra exception propagation và recovery policy |
| Offset không commit sau rebalance | Consumer mất partition ownership hoặc group generation đổi | Điều tra rebalance, poll interval và commit failure |
| Manual ack không có hiệu lực | Chưa cấu hình MANUAL/MANUAL_IMMEDIATE hoặc ack gọi sai thread/thời điểm | Kiểm tra factory AckMode và luồng gọi acknowledgment |
| CommitRecovered không hoạt động | AckMode không phải `MANUAL_IMMEDIATE` hoặc cấu hình error handler chưa đúng | Kiểm tra điều kiện của `DefaultErrorHandler` theo version |
| Lag cao dù listener vẫn nhận record | Position tiến nhưng committed offset chưa tiến | So sánh position, committed offset và commit cadence |

## 16. Checklist triển khai an toàn

- [ ] `enable.auto.commit` được tắt để listener container quản lý offset.
- [ ] AckMode phù hợp với record listener/batch listener và yêu cầu redelivery.
- [ ] Manual acknowledgment chỉ gọi sau khi xử lý bền vững hoàn tất.
- [ ] Listener error handler không vô tình nuốt exception cần retry.
- [ ] Error handler/recoverer có hành vi commit sau recovery được hiểu rõ.
- [ ] Transactional listener commit output và input offset trong cùng Kafka transaction khi cần EOS.
- [ ] Consumer idempotent để chịu được record giao lại sau commit failure.
- [ ] Thời gian xử lý phù hợp `max.poll.interval.ms` và cấu hình rebalance.
- [ ] Theo dõi commit rate, commit latency, rebalance, retry, DLT và lag theo partition.
- [ ] Đã kiểm thử listener success, exception, recovery success/failure, restart và rebalance.

Offset commit không như mong đợi thường là hệ quả của ranh giới acknowledgment, error handling hoặc transaction chưa được hiểu đúng. Hãy xác định listener đã xử lý đến đâu, AckMode yêu cầu commit lúc nào và broker đã lưu committed offset hay chưa. Khi acknowledgment chỉ diễn ra sau xử lý bền vững, exception được chuyển đúng tới error handler và consumer idempotent, hệ thống có thể xử lý an toàn cả commit chậm lẫn record được giao lại.
