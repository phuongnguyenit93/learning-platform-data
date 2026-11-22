# Xử lý từng record trong một batch

Khi consumer đọc Kafka, một lần `poll()` có thể trả về nhiều record thuộc một hoặc nhiều partition. Spring Kafka có thể chuyển cả nhóm record đó vào một lần gọi `@KafkaListener`. Ứng dụng vẫn có thể xử lý từng record theo thứ tự trong vòng lặp, đồng thời tận dụng việc nhận dữ liệu theo batch để giảm chi phí gọi listener và điều phối.

Bài học này tập trung vào cách cấu hình batch listener, xử lý từng record, báo lỗi tại đúng vị trí trong batch và cân bằng kích thước batch với thời gian xử lý. Ví dụ sử dụng sự kiện `OrderCreated`; kiểu dữ liệu và service là các thành phần nghiệp vụ của ứng dụng.

## 1. Batch là cách nhận dữ liệu, không phải một record duy nhất

Producer có thể gửi sự kiện bằng `KafkaTemplate` vào một topic. Kafka lưu record trong partition và gán offset riêng cho từng record. Consumer thuộc một consumer group nhận các partition được phân công; mỗi lần lấy dữ liệu, consumer có thể nhận nhiều record. Khi bật chế độ batch, Spring Kafka chuyển danh sách record đó cho listener.

Mỗi phần tử trong batch vẫn là một `ConsumerRecord` độc lập, có các thông tin như:

- `topic()`: topic chứa record.
- `partition()`: partition chứa record.
- `offset()`: vị trí của record trong partition đó.
- `key()` và `value()`: khóa và payload của sự kiện.
- `headers()`: metadata đi kèm record.

Một batch có thể chứa record từ nhiều partition. Kafka bảo đảm thứ tự trong từng partition; không nên suy luận rằng các record thuộc nhiều partition có một thứ tự toàn cục duy nhất. Nếu listener duyệt danh sách tuần tự, thứ tự record của từng partition được giữ trong quá trình xử lý tuần tự đó.

## 2. Bật batch listener

Tạo một `ConcurrentKafkaListenerContainerFactory` dành cho listener nhận danh sách. Điểm cấu hình quyết định là `setBatchListener(true)`. Nếu không bật thuộc tính này, listener thông thường nhận từng record thay vì một danh sách record.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaBatchConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler batchErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);
        return factory;
    }

    @Bean
    DefaultErrorHandler batchErrorHandler() {
        // Một lần xử lý ban đầu và tối đa hai lần retry, cách nhau một giây.
        return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
    }
}
```

Listener sử dụng factory vừa cấu hình bằng thuộc tính `containerFactory`:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    private final OrderService orderService;

    OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "${app.kafka.orders-topic}",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onMessage(List<ConsumerRecord<String, OrderCreated>> records) {
        for (int index = 0; index < records.size(); index++) {
            ConsumerRecord<String, OrderCreated> record = records.get(index);
            try {
                orderService.handle(record.value());
            }
            catch (Exception ex) {
                throw new BatchListenerFailedException(
                        "Không xử lý được sự kiện OrderCreated", ex, index);
            }
        }
    }
}
```

Vòng lặp xử lý từng payload bằng service nghiệp vụ. Giữ `ConsumerRecord` thay vì chỉ nhận `List<OrderCreated>` khi cần dùng key, partition, offset hoặc headers để ghi log, kiểm tra nguồn sự kiện hay chẩn đoán lỗi. `index` trong ví dụ là chỉ số bắt đầu từ 0 của record trong danh sách hiện tại.

## 3. Xử lý lỗi tại đúng record

Trong batch listener, nếu một record lỗi sau khi các record đứng trước đã được xử lý, ứng dụng cần cho container biết vị trí lỗi. `BatchListenerFailedException` mang theo chỉ số record bị lỗi. Khi dùng cùng `DefaultErrorHandler`, Spring Kafka có thể xử lý phần batch đã thành công và phần cần thử lại theo vị trí đó.

Với cấu hình phù hợp, hành vi thường là:

1. Các record đứng trước chỉ số lỗi được xem là đã xử lý và offset tương ứng có thể được commit.
2. Record lỗi cùng các record phía sau được seek để container nhận và xử lý lại.
3. `BackOff` quyết định khoảng chờ và số lần retry. Khi retry cạn, recoverer của error handler quyết định cách xử lý record không thể phục hồi, chẳng hạn ghi log hoặc chuyển sang dead-letter topic (DLT).

`FixedBackOff(1_000L, 2L)` trong ví dụ đặt khoảng nghỉ một giây và tối đa hai lần retry sau lần xử lý ban đầu. Trong ứng dụng thực tế, hãy cấu hình recoverer phù hợp với chính sách dữ liệu; nếu cần DLT, có thể dùng `DeadLetterPublishingRecoverer` cùng `KafkaTemplate` để xuất record lỗi sang topic riêng.

Nếu listener ném một exception thông thường mà không chỉ rõ vị trí lỗi, error handler có thể phải xem toàn bộ batch là thất bại và xử lý lại batch từ đầu. Khi đó, các record đã tạo side effect thành công trước lúc lỗi có thể được giao lại. Vì vậy, việc báo đúng chỉ số lỗi giúp giảm xử lý lặp, nhưng không biến batch thành một giao dịch nguyên tử.

### Tránh bỏ qua lỗi ngoài ý muốn

Đoạn mã sau có vẻ giúp listener tiếp tục xử lý record tiếp theo, nhưng nó nuốt lỗi:

```java
for (OrderCreated event : events) {
    try {
        orderService.handle(event);
    }
    catch (Exception ex) {
        log.warn("Không xử lý được order", ex);
    }
}
```

Nếu listener kết thúc bình thường, container có thể commit batch. Record lỗi khi đó không được retry; chỉ ghi log không đủ để bảo đảm dữ liệu được xử lý. Chỉ nên bắt lỗi rồi tiếp tục khi ứng dụng đã thực hiện một hành động phục hồi có chủ đích, ví dụ lưu record lỗi vào kho bền vững hoặc gửi DLT thành công. Nếu chưa có cơ chế đó, hãy truyền lỗi cho container bằng exception phù hợp.

## 4. Offset, side effect và tính idempotent

Offset thuộc về từng partition, còn batch chỉ là nhóm record được giao trong một lần poll. Với batch listener, chế độ xác nhận mặc định thường commit theo batch sau khi listener xử lý thành công. Vòng lặp Java không tự tạo ra một lần commit cho mỗi record. Khi dùng `BatchListenerFailedException` với `DefaultErrorHandler`, container có thêm thông tin để xử lý offset trước và sau vị trí lỗi.

Commit offset của Kafka không tự hoàn tác thao tác đã thực hiện ở hệ thống khác. Ví dụ, listener cập nhật cơ sở dữ liệu cho ba đơn hàng rồi record thứ tư thất bại; khi ba record đầu được giao lại, thao tác cập nhật có thể chạy lần nữa. Hãy thiết kế consumer idempotent, chẳng hạn:

- Dùng event ID ổn định để nhận diện sự kiện đã xử lý.
- Đặt ràng buộc duy nhất hoặc dùng thao tác upsert phù hợp trong cơ sở dữ liệu.
- Lưu trạng thái xử lý sự kiện cùng thay đổi nghiệp vụ trong một transaction cơ sở dữ liệu khi có thể.
- Chỉ xác nhận record sau khi kết quả nghiệp vụ đã được lưu bền vững.

Nếu cần phối hợp transaction Kafka với cơ sở dữ liệu, phải thiết kế riêng ranh giới transaction và cơ chế phục hồi. Không nên xem việc nhận một danh sách trong listener là bảo đảm tất cả side effect trong danh sách cùng thành công hoặc cùng rollback.

## 5. Kích thước batch và throughput

Batch có thể giảm overhead của poll và lời gọi listener, nhưng mỗi record vẫn cần được deserialize, kiểm tra và xử lý nghiệp vụ. Với vòng lặp tuần tự, thời gian xử lý batch gần bằng tổng thời gian xử lý các record cộng với overhead chung.

Các yếu tố cần theo dõi khi điều chỉnh:

| Yếu tố | Ảnh hưởng | Cách cân nhắc |
| --- | --- | --- |
| `max.poll.records` | Giới hạn số record tối đa consumer lấy trong một lần poll; batch thực tế có thể nhỏ hơn | Tăng dần và đo thời gian xử lý, bộ nhớ, độ trễ |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần `poll()` trước khi consumer có thể bị xem là không còn hoạt động | Bảo đảm thời gian xử lý batch và các khoảng chờ nằm trong giới hạn phù hợp |
| Số partition | Quyết định mức độ song song tối đa có thể phân bổ cho consumer trong cùng group | Tạo đủ partition cho mức song song mong muốn và tải thực tế |
| Concurrency của listener container | Tạo nhiều consumer/container để xử lý các partition được phân công song song | Điều chỉnh theo số partition, CPU, I/O và khả năng của hệ thống đích |
| Thời gian xử lý từng record | Một record chậm có thể kéo dài thời gian hoàn tất cả batch khi xử lý tuần tự | Đo p95/p99, tìm tác vụ I/O chậm và đặt timeout phù hợp |

Tăng `max.poll.records` không đồng nghĩa throughput luôn tăng. Batch quá lớn có thể làm tăng bộ nhớ, thời gian xử lý trước lần poll kế tiếp và số record bị ảnh hưởng khi phải retry. Nếu thời gian xử lý vượt `max.poll.interval.ms`, consumer có thể rời group và gây rebalance.

Concurrency của container giúp nhiều consumer trong cùng group xử lý các partition khác nhau. Một vòng lặp tuần tự trong một listener vẫn xử lý các phần tử của batch lần lượt. Nếu xử lý song song bên trong batch, cần giới hạn số tác vụ đồng thời, chờ tất cả tác vụ hoàn tất trước khi listener trả về, tổng hợp lỗi theo đúng record và bảo toàn thứ tự theo key/partition nếu nghiệp vụ yêu cầu. Không nên gửi tác vụ bất đồng bộ rồi trả về ngay, vì container có thể commit offset trước khi công việc thực sự hoàn tất.

## 6. Chọn cách xử lý phù hợp

Xử lý tuần tự từng phần tử trong batch phù hợp khi ứng dụng muốn giảm overhead nhận dữ liệu nhưng vẫn cần logic nghiệp vụ rõ ràng cho từng record. Cách này cũng thuận tiện khi cần đọc metadata của từng record và xác định chính xác phần tử gây lỗi.

Listener nhận từng record phù hợp hơn nếu mỗi lần gọi cần có vòng đời xử lý, retry hoặc xác nhận độc lập theo record. Batch listener phù hợp hơn khi ứng dụng cần xử lý một nhóm dữ liệu cùng lúc hoặc muốn kiểm soát rõ cách chia batch. Quyết định nên dựa trên yêu cầu ordering, retry, side effect và phép đo throughput của hệ thống.

## 7. Checklist khi triển khai

- [ ] Factory của listener đã bật `setBatchListener(true)`.
- [ ] `@KafkaListener` dùng đúng `containerFactory` và nhận kiểu danh sách phù hợp.
- [ ] Vòng lặp xử lý từng record và giữ metadata cần cho quan sát, chẩn đoán.
- [ ] Lỗi được gắn với đúng chỉ số bằng `BatchListenerFailedException` khi cần xử lý lỗi từng record.
- [ ] `DefaultErrorHandler`, BackOff và recoverer/DLT khớp với chính sách retry của ứng dụng.
- [ ] Side effect có khả năng chịu được việc record được giao lại.
- [ ] `max.poll.records`, `max.poll.interval.ms` và concurrency được điều chỉnh dựa trên số liệu đo.
- [ ] Nếu xử lý song song, listener chỉ trả về sau khi mọi tác vụ của batch đã hoàn tất.

Khi kiểm thử, hãy gửi nhiều record thuộc cùng một partition và nhiều partition, xác minh listener nhận danh sách, kiểm tra thứ tự trong từng partition, cố ý làm một record thất bại và quan sát offset/retry/DLT. Đồng thời kiểm tra trường hợp một record đã tạo side effect trước khi batch gặp lỗi để xác nhận cơ chế idempotency hoạt động đúng.
