# max.poll.records và kích thước lô đọc

Kafka consumer không nhất thiết chuyển từng record cho ứng dụng ngay sau khi broker trả dữ liệu. Consumer gọi `poll()` để lấy các record đang sẵn sàng từ những partition được gán. Thuộc tính `max.poll.records` giới hạn số record tối đa mà một lần gọi `poll()` trả về cho ứng dụng. Trong Spring Kafka, giới hạn này ảnh hưởng trực tiếp đến số record được xử lý trong một chu kỳ poll và kích thước danh sách mà batch listener nhận được.

Chọn kích thước lô đọc phù hợp giúp cân bằng thông lượng, độ trễ, bộ nhớ và thời gian xử lý. Lô quá nhỏ có thể làm giảm hiệu quả của xử lý theo nhóm; lô quá lớn có thể khiến listener xử lý quá lâu, vượt `max.poll.interval.ms` và kích hoạt rebalance. Để cấu hình đúng, cần phân biệt giới hạn số record của `max.poll.records` với giới hạn dữ liệu theo byte của cơ chế fetch.

## 1. Consumer đọc dữ liệu qua poll()

Kafka consumer duy trì các partition được gán và thường lặp qua chu trình sau:

1. Consumer gửi các yêu cầu fetch tới broker để lấy dữ liệu từ những partition được gán.
2. Kafka client nhận và lưu các record đã fetch trong bộ đệm nội bộ.
3. Ứng dụng gọi `poll(Duration)` để lấy các record hiện có.
4. Consumer hoặc listener container xử lý record, cập nhật tiến độ và tiếp tục gọi `poll()`.

Có thể hình dung một consumer đang đọc ba partition như sau:

```text
Consumer của group order-projection
          |
          +---- Partition 0: records A, B, C, ...
          +---- Partition 1: records D, E, F, ...
          +---- Partition 2: records G, H, I, ...
          |
          v
      poll(Duration)
          |
          v
   ConsumerRecords tối đa N record
          |
          v
   Spring Kafka listener container
          |
          +---- Record listener: gọi handler cho từng record
          |
          +---- Batch listener: gọi handler với một danh sách record
```

`poll()` lấy record từ tất cả partition đang được gán cho consumer. Một lần poll có thể trả về record từ nhiều partition; giới hạn số record được tính trên tổng kết quả của lần poll đó, không phải áp dụng riêng cho từng partition.

## 2. `max.poll.records` giới hạn điều gì?

`max.poll.records` là thuộc tính của Kafka consumer, quy định số record tối đa được trả về trong một lần gọi `poll()`. Giá trị mặc định của Kafka consumer là `500`.

Ví dụ, một consumer được gán ba partition và cấu hình:

```properties
max.poll.records=100
```

Một lần `poll()` có thể trả về tối đa 100 record cộng lại từ cả ba partition. Nó không có nghĩa mỗi partition được trả về 100 record. Nếu hiện tại chỉ có 27 record sẵn sàng, kết quả poll có thể chỉ chứa 27 record. Nếu chưa có record nào sẵn sàng trong khoảng chờ của poll, kết quả có thể rỗng.

Các điểm cần nhớ:

- Đây là giới hạn trên, không phải cam kết rằng lần poll nào cũng trả đủ số record đã cấu hình.
- Giới hạn áp dụng trên từng đối tượng `KafkaConsumer`, không phải một giới hạn tổng cho toàn bộ consumer group.
- Giá trị này đếm record, không đếm byte và không giới hạn số record của từng partition riêng lẻ.
- Kafka client có thể đã fetch và đệm dữ liệu trước khi ứng dụng lấy chúng qua `poll()`. Giảm `max.poll.records` không đồng nghĩa broker chỉ gửi đúng số record đó trong mỗi fetch request.
- `max.poll.records` không làm thay đổi số partition của topic và không tự tạo thêm khả năng xử lý song song.

Nếu một consumer group chạy nhiều consumer, mỗi consumer có giới hạn poll riêng. Vì vậy, tổng số record đang được xử lý đồng thời trong group có thể lớn hơn `max.poll.records`, tùy số consumer, số partition được gán và lượng dữ liệu sẵn sàng.

## 3. Phân biệt số record với kích thước fetch theo byte

Kafka có các cấu hình fetch khác với `max.poll.records`. Một số cấu hình quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `max.poll.records` | Số record tối đa được trả về cho ứng dụng trong một lần `poll()` |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition trong một yêu cầu fetch |
| `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch mà broker trả về cho một yêu cầu fetch |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu consumer mong muốn nhận trước khi broker trả lời fetch, nếu có thể chờ thêm |
| `fetch.max.wait.ms` | Thời gian tối đa broker chờ để đáp ứng điều kiện `fetch.min.bytes` trước khi trả lời fetch |

Hai nhóm cấu hình giải quyết hai câu hỏi khác nhau:

- Fetch theo byte quyết định Kafka client lấy dữ liệu từ broker theo các giới hạn dung lượng và thời gian nào.
- `max.poll.records` quyết định tối đa bao nhiêu record được đưa ra cho ứng dụng trong một lần poll.

Do đó, cấu hình `max.poll.records=200` không bảo đảm mỗi lần poll có đủ 200 record. Fetch có thể chưa lấy đủ dữ liệu, các partition có thể đang ít dữ liệu, hoặc dữ liệu đã có trong bộ đệm nhưng số record sẵn sàng ít hơn giới hạn. Ngược lại, fetch có thể đã đệm nhiều dữ liệu hơn số record mà lần poll hiện tại trả về; phần còn lại có thể được trả ở những lần poll tiếp theo.

Số record cũng không phản ánh chính xác bộ nhớ cần dùng. Một trăm record nhỏ có thể nhẹ hơn nhiều so với một trăm record chứa payload lớn. Bộ nhớ thực tế còn phụ thuộc kích thước message, batch dữ liệu đã fetch, object sau deserialize và dữ liệu tạm mà ứng dụng tạo ra khi xử lý.

Các giới hạn fetch theo byte cũng không phải lúc nào là ranh giới tuyệt đối cho một record batch. Kafka có thể trả về batch đầu tiên lớn hơn giới hạn cấu hình trong một số trường hợp để consumer vẫn đọc tiến lên được. Vì vậy, hãy xem các giá trị fetch là giới hạn điều tiết dữ liệu thông thường và kiểm tra thêm kích thước message tối đa mà hệ thống cho phép.

## 4. `max.poll.records` liên hệ với listener của Spring Kafka

Spring Kafka dùng listener container để quản lý `KafkaConsumer`, gọi poll, chuyển record cho listener và quản lý offset. Có hai cách nhận record thường gặp.

### Record listener

Với record listener, phương thức `@KafkaListener` nhận từng `ConsumerRecord`. Một lần poll có thể lấy nhiều record, nhưng container gọi phương thức listener riêng cho từng record trong kết quả đó.

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderRecordListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void onEvent(ConsumerRecord<String, String> record) {
        System.out.printf(
                "partition=%d, offset=%d, key=%s%n",
                record.partition(), record.offset(), record.key()
        );

        process(record.value());
    }

    private void process(String payload) {
        // Xử lý một sự kiện đơn hàng.
    }
}
```

Trong chế độ này, `max.poll.records=100` có thể khiến container nhận tối đa 100 record trong một lần poll. Phương thức `onEvent` vẫn được gọi lần lượt cho từng record theo cơ chế xử lý của container. Vì vậy, không nên hiểu cấu hình này là listener sẽ nhận một danh sách 100 phần tử.

### Batch listener

Với batch listener, container chuyển các record nhận được từ một lần poll thành một lô để listener xử lý cùng lúc. Đây là lựa chọn phù hợp khi tầng nghiệp vụ hoặc hệ thống lưu trữ phía sau hỗ trợ thao tác hàng loạt, ví dụ ghi nhiều bản ghi vào cơ sở dữ liệu bằng một batch insert.

Hai ví dụ record listener và batch listener dưới đây minh họa hai cách triển khai thay thế. Khi thử nghiệm, hãy chọn một kiểu listener cho luồng tiêu thụ đó; nếu chạy đồng thời nhiều listener cùng topic và cùng group ID, chúng sẽ tham gia cùng consumer group và chia sẻ các partition theo cơ chế phân công của Kafka.

Có thể tạo listener container factory dành riêng cho batch listener:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        return factory;
    }
}
```

Listener có thể nhận danh sách `ConsumerRecord`:

```java
import java.util.List;
import java.util.stream.Collectors;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderBatchListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onEvents(List<ConsumerRecord<String, String>> records) {
        if (records.isEmpty()) {
            return;
        }

        for (ConsumerRecord<String, String> record : records) {
            System.out.printf(
                    "partition=%d, offset=%d%n",
                    record.partition(), record.offset()
            );
        }

        processBatch(records.stream()
                .map(ConsumerRecord::value)
                .collect(Collectors.toList()));
    }

    private void processBatch(List<String> payloads) {
        // Xử lý lô sự kiện bằng một thao tác nghiệp vụ phù hợp.
    }
}
```

Trong ví dụ, `max.poll.records` là giới hạn trên cho số phần tử container có thể chuyển trong một lần gọi batch listener. Lô thực tế có thể nhỏ hơn giới hạn. Nếu listener cần biết record đến từ partition nào hoặc offset nào, nhận `ConsumerRecord` sẽ cung cấp metadata đó.

Một batch có thể chứa record từ nhiều partition được gán cho cùng consumer. Kafka giữ thứ tự trong từng partition, nhưng danh sách batch không tạo ra một thứ tự nghiệp vụ toàn cục giữa các partition. Nếu xử lý cần đúng thứ tự theo một thực thể, producer phải định tuyến các sự kiện của thực thể đó về cùng partition bằng key phù hợp.

Với Spring Boot, có thể chọn kiểu listener mặc định bằng `spring.kafka.listener.type=batch`. Khi cần cấu hình record listener và batch listener song song, tạo các container factory riêng và chỉ định `containerFactory` trên từng `@KafkaListener` sẽ giúp cấu hình rõ ràng hơn.

## 5. Cấu hình trong Spring Boot

Thuộc tính Kafka consumer có thể cấu hình trực tiếp trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      type: batch
      ack-mode: batch
```

Ý nghĩa các thiết lập chính:

- `max-poll-records: 100`: mỗi consumer lấy tối đa 100 record trong một lần poll.
- `max.poll.interval.ms: 300000`: giới hạn thời gian tối đa giữa hai lần gọi poll theo cấu hình Kafka consumer, ở đây là 5 phút.
- `listener.type: batch`: Spring Boot cấu hình listener container mặc định theo chế độ batch.
- `listener.ack-mode: batch`: container commit offset sau khi xử lý xong các record nhận từ poll theo cơ chế batch.
- `enable-auto-commit: false`: để Spring Kafka quản lý việc commit offset theo cấu hình container và acknowledgement mode.

Nếu ứng dụng dùng record listener, có thể bỏ `listener.type: batch` hoặc đặt `record`. Nếu đã khai báo container factory riêng trong Java, cấu hình kiểu listener cần nhất quán với factory được listener sử dụng. Cú pháp cấu hình và các thuộc tính được hỗ trợ cần đối chiếu với phiên bản Spring Boot/Spring Kafka đang dùng trong dự án.

`AckMode.BATCH` là một lựa chọn phổ biến khi xử lý theo lô. Các chế độ acknowledgement khác có thời điểm commit khác nhau; không nên thay đổi `max.poll.records` mà bỏ qua cách ứng dụng commit offset. Nếu ứng dụng dùng manual acknowledgement, phải chỉ acknowledge sau khi phần công việc tương ứng đã hoàn thành theo đúng quy tắc của ứng dụng.

## 6. Quan hệ với `max.poll.interval.ms` và rebalance

`max.poll.interval.ms` quy định khoảng thời gian tối đa consumer được phép không gọi `poll()` tiếp theo. Nếu ứng dụng xử lý một lô quá lâu, consumer có thể vượt khoảng thời gian này. Kafka khi đó xem consumer không còn đáp ứng nhịp poll và có thể đưa partition của nó vào quá trình rebalance để giao cho consumer khác.

Trong Spring Kafka, listener thường được gọi trên luồng quản lý consumer. Trong lúc listener xử lý đồng bộ một lô, luồng đó chưa thể tiếp tục poll. Vì vậy, thời gian xử lý lô có ảnh hưởng trực tiếp đến khoảng cách giữa các lần poll.

Giả sử batch listener xử lý tuần tự và mỗi record mất trung bình 80 ms. Nếu một poll trả về 100 record, riêng phần xử lý có thể mất khoảng 8 giây, chưa tính truy cập cơ sở dữ liệu, gọi dịch vụ khác, deserialize, commit và các khoảng chờ retry. Khi số record tăng lên 500, thời gian xử lý có thể tăng đáng kể.

Một ước lượng ban đầu cho xử lý tuần tự là:

\[
T_{batch} \approx N \times T_{record} + T_{overhead}
\]

Trong đó:

- `N` là số record thực tế trong lô, tối đa bằng `max.poll.records`.
- `T_record` là thời gian xử lý một record trong điều kiện tải đại diện.
- `T_overhead` bao gồm thời gian xử lý lô, truy cập tài nguyên, retry và các công việc phụ.

Hãy bảo đảm thời gian xử lý lô ở trường hợp tải cao vẫn thấp hơn `max.poll.interval.ms` với khoảng dự phòng hợp lý. Không nên chỉ lấy thời gian trung bình để cấu hình; cần quan sát các trường hợp chậm như truy vấn database kéo dài, dịch vụ phụ thuộc phản hồi chậm hoặc retry nhiều lần.

Nếu consumer vượt `max.poll.interval.ms`, rebalance có thể làm partition được giao cho consumer khác trong khi công việc trước đó chưa hoàn tất. Tùy thời điểm commit và cách xử lý lỗi, record có thể được xử lý lại. Vì vậy, consumer nên có khả năng xử lý lặp an toàn và không commit tiến độ trước khi nghiệp vụ tương ứng hoàn thành.

## 7. Cách chọn kích thước lô đọc

Không có một giá trị `max.poll.records` tối ưu cho mọi ứng dụng. Hãy chọn dựa trên đặc điểm payload, thời gian xử lý, khả năng xử lý batch của hệ thống phụ thuộc và yêu cầu độ trễ.

| Tình huống | Hướng cấu hình ban đầu | Lý do |
|---|---|---|
| Mỗi sự kiện xử lý nhanh, độc lập | Có thể thử lô lớn hơn | Giảm số lần gọi listener và tận dụng thông lượng |
| Xử lý từng record có truy vấn hoặc gọi API chậm | Bắt đầu với lô nhỏ hoặc vừa | Giữ thời gian xử lý mỗi poll trong giới hạn |
| Database hỗ trợ batch insert/update | Thử lô vừa rồi tăng dần | Tận dụng thao tác hàng loạt mà vẫn kiểm soát thời gian |
| Payload lớn hoặc deserialize tốn bộ nhớ | Giữ lô nhỏ hơn | Hạn chế số object lớn cùng tồn tại trong quá trình xử lý |
| Cần phản hồi nhanh cho từng sự kiện | Chọn lô vừa/nhỏ và đo độ trễ | Tránh gom quá nhiều việc vào một lần xử lý |

Một quy trình tuning thực tế:

1. Bắt đầu với giá trị vừa phải, chẳng hạn `100`, thay vì tăng ngay lên hàng nghìn record.
2. Đo số record mỗi poll, thời gian xử lý lô, thời gian chờ poll, độ trễ từ lúc producer gửi đến lúc listener xử lý và mức sử dụng bộ nhớ.
3. Kiểm tra số partition và số consumer đang hoạt động. Trong cùng group, mỗi partition tại một thời điểm chỉ được gán cho tối đa một consumer; tăng concurrency vượt số partition không tạo thêm khả năng đọc song song từ topic đó.
4. Tăng hoặc giảm `max.poll.records` từng bước và so sánh kết quả dưới tải gần với production.
5. Kiểm tra thời gian xử lý ở percentile cao và đối chiếu với `max.poll.interval.ms`; để lại khoảng dự phòng cho các đợt tải tăng hoặc dependency chậm.
6. Kiểm tra commit, retry, rebalance và khả năng xử lý lại record sau khi thay đổi cấu hình.

Nếu mục tiêu là tăng thông lượng, chỉ tăng `max.poll.records` chưa chắc giải quyết được nút thắt. Consumer có thể đang bị giới hạn bởi số partition, thời gian xử lý nghiệp vụ, database, mạng hoặc fetch theo byte. Cần quan sát toàn bộ đường đi của record trước khi kết luận lô đọc là nguyên nhân.

## 8. Những nhầm lẫn thường gặp

1. **Coi `max.poll.records` là số record của mỗi partition.** Đây là giới hạn tổng số record trả về trong một lần poll của một consumer trên tất cả partition được gán.
2. **Coi giá trị cấu hình là kích thước lô luôn nhận được.** Đây chỉ là mức tối đa; số record thực tế phụ thuộc dữ liệu sẵn sàng và kết quả fetch.
3. **Coi `max.poll.records` là giới hạn byte.** Dung lượng fetch được điều khiển bởi các cấu hình fetch; payload lớn vẫn có thể làm tăng bộ nhớ dù số record không cao.
4. **Coi record listener nhận cả danh sách.** Record listener được gọi cho từng record; batch listener mới nhận một lô record trong một lần gọi.
5. **Tăng lô mà không xem `max.poll.interval.ms`.** Lô lớn làm thời gian xử lý kéo dài và có thể gây rebalance nếu consumer không poll đúng hạn.
6. **Cho rằng tăng concurrency luôn tăng throughput.** Một group chỉ có thể xử lý song song hữu ích theo số partition được gán; consumer dư có thể không nhận partition.
7. **Commit offset trước khi xử lý xong.** Nếu tiến trình dừng sau commit nhưng trước khi hoàn thành nghiệp vụ, record có thể bị bỏ qua khi consumer đọc tiếp.

Khi cấu hình `max.poll.records`, hãy xem nó như giới hạn kích thước công việc mà mỗi consumer lấy ra trong một chu kỳ poll. Kết hợp giới hạn này với kiểu listener, thời gian xử lý, cách commit offset và các giới hạn fetch sẽ giúp Spring Kafka duy trì thông lượng ổn định mà không làm tăng nguy cơ rebalance ngoài dự kiến.
