# Kích thước batch và thời gian poll

Khi tiêu thụ sự kiện bằng Spring Kafka, ứng dụng có thể nhận từng record hoặc nhận nhiều record trong một lần gọi listener. Nhận theo batch giúp giảm chi phí gọi hàm, chuyển đổi dữ liệu và commit offset, từ đó tăng throughput khi topic có lưu lượng lớn. Tuy nhiên, batch lớn cũng làm tăng lượng dữ liệu cần giữ trong bộ nhớ và thời gian xử lý giữa hai lần `poll()`. Nếu cấu hình không phù hợp, consumer có thể tăng độ trễ, xử lý quá lâu hoặc rời consumer group do vi phạm thời gian poll.

Bài học này giải thích cách Kafka tạo batch cho consumer, vai trò của các tham số kích thước và thời gian chờ, cách cấu hình batch listener trong Spring Kafka và cách chọn giá trị dựa trên thời gian xử lý thực tế.

## 1. Batch được hình thành như thế nào?

Một consumer không nhất thiết nhận từng record ngay khi record được ghi vào topic. Kafka client gửi yêu cầu fetch tới broker, nhận dữ liệu từ các partition được gán, lưu dữ liệu đã fetch vào bộ đệm nội bộ rồi trả record cho ứng dụng qua `poll()`.

Với batch listener, Spring Kafka chuyển các record mà một lần `poll()` trả về thành một lần gọi listener. Có thể hình dung luồng dữ liệu như sau:

```mermaid
flowchart LR
    A[Topic và partition] --> B[Kafka broker trả dữ liệu fetch]
    B --> C[Kafka consumer lưu dữ liệu đệm]
    C --> D[consumer.poll() trả về records]
    D --> E[Spring Kafka batch listener]
    E --> F[Xử lý và commit offset theo cấu hình]
```

Kích thước batch thực tế là số record trong kết quả của một lần `poll()`. Giá trị này có thể nhỏ hơn giới hạn cấu hình vì broker chưa có đủ dữ liệu, consumer chỉ được gán một số partition, giới hạn fetch theo byte hoặc thời điểm dữ liệu đến. Vì vậy, đặt giới hạn 500 record không có nghĩa mỗi lần listener luôn nhận đúng 500 record.

Kafka consumer còn có thể đã fetch nhiều dữ liệu vào bộ đệm nhưng chỉ trả tối đa số record được phép trong lần `poll()` hiện tại. Phần còn lại có thể được trả ở các lần poll tiếp theo. Điều này giúp phân biệt giới hạn số record ứng dụng nhận mỗi lần poll với lượng dữ liệu broker gửi trong một fetch response.

## 2. Các tham số ảnh hưởng đến batch và poll

Các tham số sau giải quyết những vấn đề khác nhau. Cần hiểu đúng vai trò trước khi điều chỉnh chúng cùng lúc.

| Tham số | Phạm vi | Ý nghĩa và tác động |
|---|---|---|
| `max.poll.records` | Kafka consumer | Giới hạn số record tối đa mà một lần `poll()` trả về. Đây là giới hạn trực tiếp đối với số phần tử trong batch listener. Tăng giá trị có thể tăng throughput, nhưng cũng làm tăng bộ nhớ và thời gian xử lý một batch. |
| `fetch.min.bytes` | Kafka consumer / broker fetch | Số byte dữ liệu tối thiểu mà consumer mong muốn nhận trong một fetch response. Broker có thể chờ thêm dữ liệu để đạt ngưỡng này. Giá trị cao có thể giúp gom dữ liệu hiệu quả khi lưu lượng lớn, nhưng tăng độ trễ khi lưu lượng thấp. |
| `fetch.max.wait.ms` | Broker fetch | Thời gian tối đa broker chờ để đáp ứng `fetch.min.bytes` trước khi trả fetch response. Đây là một phần của cơ chế gom dữ liệu phía broker. |
| `max.partition.fetch.bytes` | Kafka consumer | Giới hạn lượng dữ liệu fetch cho mỗi partition trong một request. Tham số này ảnh hưởng lượng dữ liệu và bộ nhớ, không trực tiếp đặt số record trong batch. |
| `fetch.max.bytes` | Kafka consumer | Giới hạn tổng lượng dữ liệu trong một fetch response. Đây là giới hạn theo byte, khác với `max.poll.records` là giới hạn theo số record. Kafka có ngoại lệ để consumer vẫn có thể tiến triển khi batch đầu tiên của một partition lớn hơn giới hạn cấu hình. |
| `pollTimeout` | Spring Kafka container | Thời gian container chờ trong lời gọi `consumer.poll(Duration)`. Nếu dữ liệu đã có sẵn, poll có thể trả về sớm. Tham số này không phải thời gian cho phép listener xử lý batch. |
| `max.poll.interval.ms` | Kafka consumer | Khoảng thời gian tối đa được phép giữa hai lần gọi `poll()`. Thời gian listener xử lý batch nằm trong khoảng giữa hai lần poll. Nếu xử lý quá lâu và vượt giới hạn, consumer có thể bị xem là không còn hoạt động và group thực hiện rebalance. |

Hai cặp tham số thường bị nhầm lẫn:

- `pollTimeout` quyết định một lần poll có thể chờ dữ liệu bao lâu; `max.poll.interval.ms` giới hạn khoảng cách giữa hai lần poll, bao gồm cả thời gian ứng dụng xử lý dữ liệu vừa nhận.
- `max.poll.records` giới hạn số record trả về; `fetch.min.bytes` và các tham số fetch điều chỉnh lượng dữ liệu theo byte và cách broker chờ dữ liệu. Tăng `max.poll.records` không buộc broker tạo ra đủ record cho một batch.

## 3. Bật batch listener trong Spring Kafka

Để listener nhận nhiều record trong một lần gọi, container factory phải được cấu hình ở chế độ batch. Ví dụ dưới đây tạo một factory riêng cho luồng đơn hàng và đặt thời gian chờ poll là một giây:

```java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, Order> orderBatchFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, Order> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.getContainerProperties().setPollTimeout(1_000L);
        return factory;
    }
}
```

Listener có thể nhận danh sách `ConsumerRecord` để truy cập cả key, value, partition, offset và timestamp:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-worker",
        containerFactory = "orderBatchFactory")
public void consume(List<ConsumerRecord<String, Order>> records) {
    for (ConsumerRecord<String, Order> record : records) {
        process(record.value());
    }
}
```

Nếu ứng dụng chỉ cần payload, listener có thể dùng kiểu danh sách payload phù hợp với cấu hình message converter và deserializer. Dù dùng kiểu tham số nào, listener batch phải được ghép với container factory có `setBatchListener(true)`; nếu dùng factory record listener, chữ ký nhận danh sách sẽ không khớp chế độ xử lý.

Các giới hạn phía Kafka consumer có thể cấu hình qua Spring Boot. Ví dụ sau minh họa một cấu hình khởi đầu cho workload có lưu lượng tương đối cao; các con số cần được đo và điều chỉnh theo kích thước message, năng lực xử lý và yêu cầu độ trễ của hệ thống:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 65536
        "[fetch.max.wait.ms]": 100
```

Cú pháp đặt key trong ngoặc vuông giúp Spring Boot giữ nguyên tên thuộc tính Kafka có dấu chấm khi bind map `properties`. `pollTimeout` trong ví dụ Java là cấu hình của Spring Kafka container; các thuộc tính còn lại được chuyển tới Kafka consumer.

## 4. Chọn kích thước batch theo thời gian xử lý

Batch lớn chỉ có lợi khi consumer xử lý được batch đó trong khoảng thời gian an toàn. Nếu listener xử lý tuần tự từng record, có thể ước lượng thời gian xử lý như sau:

\[
T_{batch} \approx T_{overhead} + B \times T_{record}
\]

Trong đó:

- `B` là số record thực tế trong batch.
- `T_record` là thời gian xử lý một record; nên xem cả phân vị cao như p95 hoặc p99, không chỉ nhìn giá trị trung bình.
- `T_overhead` gồm chi phí cố định như chuyển đổi message, truy cập cơ sở dữ liệu, ghi log và commit offset.

Ví dụ, nếu mỗi record cần khoảng 15 ms và listener xử lý tuần tự 200 record, riêng phần xử lý record đã có thể mất khoảng 3 giây. Thời gian thực tế còn phụ thuộc I/O, tranh chấp tài nguyên, GC và các thao tác cuối batch. Nếu tổng thời gian này tiến sát `max.poll.interval.ms`, consumer có nguy cơ bỏ lỡ lần poll kế tiếp và gây rebalance. Hãy giữ khoảng dự phòng đáng kể cho biến động tải thay vì đặt giới hạn vừa khít với thời gian đo trung bình.

Throughput của một consumer có thể ước lượng ở mức khái quát bằng số record xử lý chia cho thời gian của một chu kỳ, gồm thời gian chờ poll, xử lý batch và overhead. Khi có nhiều consumer chạy song song, năng lực tổng có thể tăng theo số consumer đang hoạt động, nhưng còn bị giới hạn bởi số partition, tài nguyên downstream và cách phân phối tải. `max.poll.records` áp dụng cho từng consumer; không nên coi nó là giới hạn tổng của toàn bộ listener container.

Một số nguyên tắc thực tế:

1. **Bắt đầu từ batch vừa phải.** Đo thời gian xử lý và bộ nhớ trước khi tăng `max.poll.records`. Thay đổi từng tham số để biết yếu tố nào tạo ra cải thiện hoặc làm tăng độ trễ.
2. **Tăng batch khi chi phí cố định chiếm tỷ trọng lớn.** Nếu mỗi lần gọi listener hoặc commit có chi phí đáng kể, gom nhiều record có thể giảm chi phí trên mỗi record.
3. **Giảm batch khi xử lý kéo dài hoặc bộ nhớ tăng cao.** Message lớn, danh sách payload lớn hoặc xử lý tuần tự chậm đều là lý do để giảm `max.poll.records`.
4. **Điều chỉnh fetch theo lưu lượng.** `fetch.min.bytes` cao có thể phù hợp khi topic luôn có dữ liệu và ưu tiên throughput. Với topic ít sự kiện hoặc yêu cầu phản hồi nhanh, ngưỡng byte thấp và thời gian chờ ngắn thường phù hợp hơn.
5. **Chỉ tăng `max.poll.interval.ms` khi đã hiểu thời gian xử lý.** Nếu batch cần nhiều thời gian hợp lý để hoàn thành, có thể tăng khoảng poll tương ứng. Nhưng tăng vô hạn chỉ che giấu listener chậm và làm thời gian phát hiện consumer bị treo dài hơn.
6. **Chọn concurrency theo partition.** Mỗi consumer trong container có phân vùng được gán riêng. Tăng số luồng consumer vượt quá số partition có thể không tăng năng lực tiêu thụ, trong khi vẫn làm tăng tài nguyên sử dụng.

## 5. Theo dõi để biết cấu hình có hiệu quả

Không đánh giá cấu hình chỉ bằng số record trong một batch. Cần quan sát đồng thời throughput, độ trễ và độ ổn định của consumer:

| Chỉ số cần theo dõi | Cách diễn giải |
|---|---|
| Số record mỗi lần listener được gọi | Cho biết batch thực tế có gần giới hạn `max.poll.records` hay thường xuyên nhỏ hơn. |
| Records consumed rate và consumer lag | Cho biết tốc độ tiêu thụ có theo kịp tốc độ phát sinh sự kiện hay không. |
| Thời gian xử lý batch, đặc biệt p95/p99 | Cho biết listener có đủ thời gian gọi poll tiếp theo trước `max.poll.interval.ms` hay không. |
| Bộ nhớ heap và hoạt động GC | Batch lớn có thể giữ nhiều payload và đối tượng trung gian cùng lúc. |
| Số lần rebalance và lỗi xử lý | Rebalance tăng bất thường có thể liên quan tới xử lý batch quá lâu hoặc consumer không ổn định. |
| Thời gian commit offset và thao tác downstream | Giúp nhận ra nút thắt nằm ở commit, cơ sở dữ liệu hay dịch vụ phụ thuộc. |

Nếu batch thường xuyên nhỏ dù `max.poll.records` cao, hãy kiểm tra lưu lượng trên các partition và các giới hạn fetch trước khi tăng thêm giới hạn record. Nếu batch thường đầy nhưng lag vẫn tăng, hãy kiểm tra thời gian xử lý, năng lực downstream và số consumer có thể hoạt động song song. Nếu độ trễ tăng trong khi throughput không cải thiện, hãy xem lại `fetch.min.bytes`, `fetch.max.wait.ms` và `pollTimeout`.

## 6. Những điểm cần nhớ khi xử lý batch

- Kafka giữ thứ tự record trong từng partition; batch có thể chứa record từ nhiều partition nên không có một thứ tự toàn cục giữa các partition.
- Việc listener nhận cả danh sách không đồng nghĩa offset của mọi record được commit ngay lúc bắt đầu xử lý. Thời điểm commit phụ thuộc `AckMode`, transaction và cấu hình error handler của Spring Kafka.
- Nếu xử lý batch có thể được chạy lại sau lỗi, retry hoặc rebalance, logic nghiệp vụ nên có tính idempotent hoặc có cơ chế chống xử lý trùng phù hợp.
- `pollTimeout` không thay thế `max.poll.interval.ms`. Một lần poll chờ ngắn không giúp ích nếu listener mất quá nhiều thời gian xử lý batch trước lần poll kế tiếp.
- Không có một kích thước batch tối ưu cho mọi hệ thống. Giá trị phù hợp phải cân bằng throughput, độ trễ, bộ nhớ, thời gian xử lý và khả năng của các dịch vụ phía sau.

Khi tối ưu, hãy bắt đầu từ thời gian xử lý batch và consumer lag, sau đó điều chỉnh giới hạn record, tham số fetch và thời gian poll theo từng bước. Mục tiêu là để consumer nhận đủ dữ liệu nhằm giảm overhead, đồng thời luôn hoàn tất một chu kỳ xử lý với đủ thời gian dự phòng trước lần `poll()` tiếp theo.
