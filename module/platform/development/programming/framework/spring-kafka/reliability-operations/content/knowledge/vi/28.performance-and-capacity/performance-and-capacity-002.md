# Batch size và max.poll.records

Trong Spring Kafka, hiệu năng của producer và consumer chịu ảnh hưởng lớn từ cách gom dữ liệu thành lô. Producer gom nhiều record trước khi gửi lên broker; consumer lấy record theo từng đợt khi gọi `poll()`. Hai cấu hình thường được nhắc cùng nhau là `batch.size` và `max.poll.records`, nhưng chúng điều khiển hai phía khác nhau và dùng hai đơn vị khác nhau:

- `batch.size` là kích thước mục tiêu tính bằng **byte** cho một batch của producer trên từng partition.
- `max.poll.records` là số lượng **record tối đa** mà một lần gọi `poll()` trả về cho ứng dụng consumer.

Hiểu đúng hai giới hạn này giúp tăng throughput mà vẫn kiểm soát độ trễ, bộ nhớ, thời gian xử lý và nguy cơ rebalance của consumer group.

## 1. Hai loại batch ở hai phía của Kafka

Kafka không có một cấu hình batch duy nhất dùng chung cho producer và consumer. Producer và consumer có cơ chế gom, truyền và xử lý dữ liệu riêng.

| Cấu hình | Thành phần | Đơn vị | Tác động chính |
|---|---|---|---|
| `batch.size` | Producer | Byte | Giới hạn mục tiêu kích thước batch mà producer gom cho mỗi partition |
| `linger.ms` | Producer | Millisecond | Thời gian producer có thể chờ thêm để gom được nhiều record hơn |
| `max.poll.records` | Consumer | Record | Số record tối đa được trả về trong một lần `poll()` |
| `max.partition.fetch.bytes` | Consumer | Byte | Giới hạn dữ liệu fetch cho mỗi partition trong một response, có ngoại lệ để bảo đảm tiến triển với batch đầu tiên |
| `fetch.max.bytes` | Consumer | Byte | Giới hạn tổng dữ liệu fetch trong một response, cũng có ngoại lệ để consumer không bị kẹt bởi batch đầu tiên |
| `max.poll.interval.ms` | Consumer | Millisecond | Khoảng thời gian tối đa giữa các lần gọi `poll()` trước khi consumer bị xem là không còn tiến triển trong group |

Vì một bên đo bằng byte và bên kia đo bằng record, không thể suy ra `max.poll.records` trực tiếp từ `batch.size`. Kích thước thực tế của một record thay đổi theo schema, payload, header và mức độ nén.

## 2. Producer: `batch.size` và `linger.ms`

Khi ứng dụng gọi `KafkaTemplate.send()`, producer thường không gửi từng record thành một request độc lập. Kafka producer lưu record vào bộ đệm và gom chúng thành batch theo topic-partition trong cơ chế accumulator. Một request gửi tới broker có thể chứa các batch thuộc nhiều partition.

### `batch.size` giới hạn điều gì?

`batch.size` đặt kích thước mục tiêu tối đa cho batch mà producer gom trên **mỗi partition**. Giá trị thường được cấu hình bằng byte. Ví dụ, `65536` tương đương 64 KiB cho một batch của một partition.

Giá trị này không có nghĩa mọi batch đều sẽ đạt đúng kích thước đã cấu hình. Nếu lưu lượng đến thưa, batch có thể được gửi đi khi còn nhỏ. Nếu nhiều record đến liên tục trên cùng partition, batch có thể đầy nhanh và được gửi trước khi hết thời gian chờ.

Tăng `batch.size` có thể giúp producer gom nhiều dữ liệu hơn trong một lần gửi, giảm số request và cải thiện hiệu quả nén. Tuy nhiên, batch lớn hơn cũng cần thêm bộ nhớ và có thể làm tăng thời gian chờ khi lưu lượng thấp. Nếu ứng dụng có nhiều partition hoạt động đồng thời, tổng bộ nhớ dành cho các batch có thể tăng đáng kể.

### `linger.ms` tạo cơ hội gom thêm record

`linger.ms` là khoảng thời gian producer có thể chờ trước khi gửi một batch chưa đầy. Khi batch đạt kích thước mục tiêu, producer có thể gửi ngay; khi chưa đầy, hết thời gian chờ cũng là một điều kiện để gửi.

Ví dụ, nếu `linger.ms` bằng 5 ms, producer có thể chờ tối đa khoảng thời gian đó để nhận thêm record cho batch. Đây là sự đánh đổi giữa throughput và latency:

- Linger thấp giúp record được gửi sớm, phù hợp với luồng ưu tiên độ trễ.
- Linger cao tạo thêm cơ hội gom batch và nén hiệu quả hơn khi lưu lượng đủ đều, nhưng có thể tăng độ trễ đầu cuối.

Không nên tăng `linger.ms` một cách máy móc. Nếu lưu lượng vốn đã đủ cao để batch thường xuyên đầy, tăng thời gian chờ có thể không đem lại lợi ích tương xứng.

### Các cấu hình producer liên quan

`batch.size` cần được xem cùng các cấu hình sau:

- `buffer.memory`: dung lượng bộ nhớ producer dùng để đệm record đang chờ gửi. Khi buffer cạn, thao tác gửi có thể phải chờ tối đa theo `max.block.ms` rồi phát sinh lỗi nếu vẫn không lấy được chỗ trống.
- `compression.type`: thuật toán nén batch, chẳng hạn `lz4`, `zstd`, `snappy` hoặc `gzip`. Nén thường hiệu quả hơn khi batch có đủ dữ liệu, nhưng cũng tiêu tốn CPU.
- `max.request.size`: giới hạn kích thước request mà producer có thể gửi. Đây là giới hạn khác với `batch.size`; request có thể chứa batch của nhiều partition.
- `acks`, `enable.idempotence` và retry: ảnh hưởng đến độ tin cậy khi gửi. Tối ưu batch không nên làm mất các bảo đảm giao nhận mà hệ thống cần.

Producer có thể gom các lần gọi `KafkaTemplate.send()` vào cùng batch nếu chúng được gửi qua cùng producer và cùng partition trong khoảng thời gian phù hợp. Gọi `flush()` sau từng record thường làm mất cơ hội gom batch, vì vậy chỉ nên flush khi ngữ nghĩa ứng dụng thực sự yêu cầu.

## 3. Consumer: `max.poll.records`

Consumer lấy dữ liệu từ broker thông qua fetch request. Khi ứng dụng gọi `poll()`, Kafka trả về tối đa số record được quy định bởi `max.poll.records` trong một lần gọi.

Ví dụ, với `max.poll.records=300`, một lần `poll()` có thể trả về 300 record hoặc ít hơn nếu hiện tại chưa có đủ dữ liệu. Đây là mức trần, không phải cam kết mỗi lần poll đều có đủ 300 record.

`max.poll.records` điều khiển số record ứng dụng nhận trong một lần poll. Nó không trực tiếp đặt giới hạn byte của response fetch và không thay thế `fetch.min.bytes`, `fetch.max.wait.ms`, `fetch.max.bytes` hay `max.partition.fetch.bytes`. Consumer có thể fetch dữ liệu trước và giữ dữ liệu đã fetch trong bộ đệm nội bộ; giới hạn số record trả về cho ứng dụng được áp dụng khi `poll()` lấy dữ liệu từ phần đã có đó.

### Vì sao cần giới hạn số record mỗi lần poll?

Sau khi poll, consumer phải xử lý các record trước khi quay lại poll tiếp. Nếu một lần poll trả về quá nhiều record, ứng dụng có thể gặp các vấn đề sau:

1. **Thời gian xử lý kéo dài:** consumer mất nhiều thời gian hơn trước khi gọi `poll()` lần tiếp theo.
2. **Áp lực bộ nhớ tăng:** record đã deserialize, object trung gian và dữ liệu nghiệp vụ có thể chiếm nhiều bộ nhớ hơn payload thô trên mạng.
3. **Tăng thời gian phục hồi khi lỗi:** nếu một batch xử lý thất bại, nhiều record có thể phải được xử lý lại tùy cấu hình commit và error handler.
4. **Nguy cơ vượt `max.poll.interval.ms`:** nếu thời gian giữa hai lần poll vượt ngưỡng, consumer có thể bị rời khỏi group và partition được phân phối lại.

Ngược lại, nếu `max.poll.records` quá thấp, ứng dụng có thể phải poll thường xuyên với những lô nhỏ, làm tăng overhead và giảm khả năng tận dụng throughput, nhất là khi mỗi lần xử lý có chi phí cố định đáng kể.

### Quan hệ với `max.poll.interval.ms`

`max.poll.interval.ms` đặt giới hạn thời gian giữa hai lần gọi `poll()` của consumer đang tham gia group. Đây là cấu hình đặc biệt quan trọng khi listener xử lý record đồng bộ.

Giả sử một lần poll trả về 300 record và listener xử lý tuần tự trung bình khoảng 8 ms cho mỗi record. Thời gian xử lý phần record vào khoảng 2,4 giây, chưa tính thời gian deserialize, gọi dịch vụ bên ngoài, ghi database, commit offset và các khoảng dừng của JVM. Đây chỉ là phép ước lượng để lập ngân sách thời gian; khi vận hành cần đo phân phối thời gian thực tế, đặc biệt là p95 và p99.

Hãy giữ đủ khoảng dự phòng để consumer hoàn thành xử lý và quay lại poll trước khi chạm `max.poll.interval.ms`. Nếu một batch thường xuyên mất quá nhiều thời gian, giảm `max.poll.records`, tối ưu xử lý hoặc tăng năng lực xử lý có thể phù hợp hơn. Chỉ tăng `max.poll.interval.ms` khi thời gian xử lý dài là chủ đích và hệ thống có đủ bộ nhớ, khả năng chịu lỗi cũng như cơ chế phục hồi tương ứng.

`session.timeout.ms` có vai trò khác: nó liên quan đến việc coordinator phát hiện consumer mất heartbeat. Với consumer Java hiện đại, heartbeat có thể được duy trì nền trong khi ứng dụng xử lý, nhưng vượt `max.poll.interval.ms` vẫn có thể khiến consumer bị xem là không tiến triển và kích hoạt rời group/rebalance. Không nên dùng hai timeout này thay thế cho nhau.

## 4. Cấu hình trong Spring Boot

Ví dụ dưới đây cấu hình producer gom batch 64 KiB, chờ tối đa 5 ms và dùng LZ4; consumer nhận tối đa 300 record mỗi lần poll. Các giá trị chỉ là điểm bắt đầu để thử nghiệm, không phải bộ thông số tối ưu cho mọi workload.

```yaml
spring:
  kafka:
    producer:
      acks: all
      batch-size: 65536
      buffer-memory: 67108864
      compression-type: lz4
      properties:
        linger.ms: 5
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      max-poll-records: 300
      properties:
        max.poll.interval.ms: 300000
        fetch.min.bytes: 1
        fetch.max.wait.ms: 500
        max.partition.fetch.bytes: 1048576
```

Trong cấu hình trên:

- `batch-size` là thuộc tính Spring Boot ánh xạ tới `batch.size` của Kafka producer.
- `max-poll-records` ánh xạ tới `max.poll.records` của Kafka consumer.
- Những thuộc tính Kafka chưa có trường Spring Boot chuyên biệt có thể được truyền qua `properties`.
- `enable-auto-commit: false` cho phép Spring Kafka container quản lý việc commit theo acknowledgment mode đã chọn. Cần cấu hình acknowledgment mode và xử lý lỗi phù hợp với yêu cầu giao nhận của ứng dụng.

Nếu dùng Spring Kafka trực tiếp qua Java configuration, có thể đặt các thuộc tính tương ứng trong `ProducerConfig` và `ConsumerConfig` rồi truyền vào `DefaultKafkaProducerFactory` và `DefaultKafkaConsumerFactory`. Dù dùng YAML hay Java config, tên và ý nghĩa của các thuộc tính Kafka vẫn như nhau.

## 5. `max.poll.records` và batch listener trong Spring Kafka

`max.poll.records` giới hạn số record trả về từ một lần poll ở Kafka client. Cấu hình này **không tự động biến listener đang nhận từng record thành listener nhận một danh sách**.

Với record listener, Spring Kafka gọi phương thức listener cho từng record. Nếu muốn ứng dụng nhận cả lô trong một lần gọi listener, hãy bật batch listener cho container factory hoặc chọn kiểu listener batch trong cấu hình Spring Boot.

Ví dụ với cấu hình Spring Boot:

```yaml
spring:
  kafka:
    listener:
      type: batch
```

Listener có thể nhận danh sách record như sau:

```java
@KafkaListener(topics = "orders", groupId = "order-worker")
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
```

Khi listener batch trả về bình thường, container áp dụng acknowledgment mode đã cấu hình để commit offset. Cần xác định rõ thời điểm commit và cách xử lý exception. Nếu xử lý thất bại giữa lô, các record đã xử lý trước đó có thể được gửi lại tùy error handler, offset đã commit và chiến lược retry. Vì vậy, thao tác nghiệp vụ nên có tính idempotent hoặc có cơ chế chống xử lý trùng.

Với record listener, ứng dụng vẫn chịu ảnh hưởng của số record trong lần poll: container phải xử lý các record nhận được trước khi tiếp tục vòng poll. Batch listener thay đổi cách listener nhận dữ liệu, không loại bỏ yêu cầu kiểm soát tổng thời gian xử lý.

## 6. Cách chọn giá trị theo workload

Không có một cặp giá trị `batch.size` và `max.poll.records` phù hợp cho mọi hệ thống. Hãy chọn theo kích thước record, lưu lượng, thời gian xử lý và mục tiêu latency.

### Với producer

1. Đo kích thước record điển hình và lưu lượng trên từng partition.
2. Quan sát `batch-size-avg` và `batch-size-max` để biết batch thực tế có gần kích thước cấu hình hay không.
3. Nếu batch thường nhỏ vì record đến rải rác, thử tăng `linger.ms` từng bước nhỏ và theo dõi latency.
4. Nếu batch thường xuyên đầy nhưng số request vẫn cao, thử tăng `batch.size` trong giới hạn bộ nhớ và request size.
5. Theo dõi compression ratio, CPU, thời gian chờ buffer và request latency để xác định lợi ích có lớn hơn chi phí hay không.

Nếu producer phục vụ giao dịch cần phản hồi tức thì, ưu tiên latency và chỉ tăng thời gian chờ khi số liệu chứng minh lợi ích. Nếu producer gửi luồng sự kiện lớn, đều và có thể chấp nhận vài millisecond chờ thêm, batch lớn hơn có thể cải thiện throughput.

### Với consumer

1. Đo thời gian xử lý một record và thời gian xử lý cả poll trong điều kiện tải thực tế.
2. Chọn `max.poll.records` sao cho thời gian xử lý một poll thấp hơn đáng kể `max.poll.interval.ms`, kể cả khi có record chậm hoặc dependency bên ngoài bị trễ.
3. Theo dõi heap, allocation, GC và kích thước payload. Cùng một số record nhưng payload lớn có thể tạo áp lực bộ nhớ rất khác.
4. Kiểm tra lag và tốc độ tiêu thụ khi thay đổi số record. Tăng batch không giải quyết được nút thắt ở database hoặc dịch vụ downstream.
5. Thử nghiệm với dữ liệu lệch partition, burst traffic, record lớn, retry và rebalance để kiểm tra hành vi khi điều kiện không lý tưởng.

Một ước lượng ban đầu cho xử lý tuần tự là:

\[
N_{poll} \times T_{record} + T_{overhead} < T_{poll\ interval\ budget}
\]

Trong đó `N_poll` là số record xử lý trong một poll, `T_record` là thời gian xử lý đại diện cho một record, còn `T_overhead` gồm deserialize, commit, gọi dependency và các chi phí khác. Hãy dùng số đo p95/p99 và tải đỉnh để đặt ngân sách thực tế; không nên chỉ dựa trên thời gian trung bình.

Ví dụ, nếu một record thường cần 20 ms và xử lý tuần tự, lô 500 record đã cần khoảng 10 giây cho phần xử lý chính. Nếu một số record đôi khi mất vài giây vì gọi dịch vụ ngoài, thời gian cả poll có thể tăng mạnh. Trong tình huống đó, giảm kích thước lô, đặt timeout cho dependency, dùng retry có kiểm soát hoặc thiết kế xử lý bất đồng bộ có thể cần thiết.

## 7. Các dấu hiệu cấu hình chưa phù hợp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Producer gửi nhiều request nhỏ | Lưu lượng thấp trên từng partition, `linger.ms` quá thấp hoặc batch nhỏ | Xem `batch-size-avg`, thử tăng linger hoặc batch size và đo latency |
| Producer tăng latency khi tăng linger | Thời gian chờ gom batch vượt ngân sách latency | Giảm `linger.ms`, kiểm tra latency theo percentile |
| Producer chờ buffer hoặc send bị block | Buffer thiếu chỗ, broker chậm, request bị nghẽn hoặc lưu lượng vượt năng lực gửi | Xem buffer pool wait, request latency, broker và `buffer.memory` |
| Consumer lag tăng dù poll nhận nhiều record | Xử lý nghiệp vụ hoặc dependency downstream là nút thắt | Đo thời gian listener, database, API và tốc độ xử lý thực tế |
| Consumer thường xuyên rebalance | Thời gian xử lý giữa hai lần poll quá dài, consumer bị treo hoặc mất kết nối | So sánh thời gian poll với `max.poll.interval.ms`, xem log group và GC pause |
| Consumer dùng nhiều heap hoặc GC tăng | Một poll giữ quá nhiều record hoặc payload lớn | Giảm `max.poll.records`, xem kích thước object sau deserialize và heap |
| Throughput thấp với các lô rất nhỏ | Poll/listener overhead cao hoặc consumer chưa tận dụng đủ dữ liệu | Tăng dần `max.poll.records` và đo throughput, latency, bộ nhớ |

Các dấu hiệu trên là điểm bắt đầu điều tra. Cần đối chiếu metric producer, consumer, broker và dependency để xác định đúng nút thắt.

## 8. Metric nên theo dõi

Khi điều chỉnh batch, cần theo dõi đồng thời throughput, latency và tài nguyên.

**Producer:**

- `batch-size-avg`, `batch-size-max`: kích thước batch thực tế.
- `records-per-request-avg`: số record trung bình trong request gửi đi.
- `compression-rate-avg`: hiệu quả nén.
- `record-queue-time-avg`: thời gian record nằm trong queue trước khi gửi.
- `bufferpool-wait-time`: thời gian chờ lấy buffer.
- Request latency, retry và error rate: ảnh hưởng của broker hoặc mạng tới việc gửi.

**Consumer:**

- `records-consumed-rate`: tốc độ tiêu thụ record.
- `records-lag-max`: lag lớn nhất quan sát được ở partition.
- `fetch-size-avg` và `fetch-rate`: kích thước và tần suất fetch.
- `fetch-latency-avg`: độ trễ fetch.
- `poll-idle-ratio-avg` và thời gian xử lý listener: mức độ bận của consumer và ứng dụng.
- Heap, GC pause, commit latency và số lần rebalance: tác động của batch tới tiến trình.

Tên metric cụ thể có thể khác theo phiên bản Kafka client và hệ thống giám sát. Hãy kiểm tra metric thực sự được export trong môi trường đang chạy trước khi tạo cảnh báo.

## 9. Nguyên tắc vận hành

- Thay đổi từng nhóm cấu hình một và giữ lại baseline để có thể so sánh.
- Đo cả throughput lẫn p95/p99 latency; throughput tăng nhưng latency hoặc error rate vượt SLO vẫn là kết quả xấu.
- Kiểm tra theo từng partition. Một partition nóng có thể tạo batch lớn trong khi các partition khác có batch nhỏ.
- Khi tăng `max.poll.records`, kiểm tra cả bộ nhớ sau deserialize và thời gian xử lý, không chỉ dung lượng fetch trên mạng.
- Duy trì idempotency cho xử lý consumer nếu retry hoặc batch failure có thể khiến record được giao lại.
- Khi cần tăng năng lực tiêu thụ, kiểm tra số partition và concurrency. Tăng số consumer vượt số partition được gán không tự tạo thêm khả năng xử lý song song cho cùng group.
- Đưa cấu hình đã kiểm chứng qua thử tải và quan sát production vào quản lý cấu hình có kiểm soát; tránh thay đổi đồng thời nhiều tham số khiến khó xác định nguyên nhân.

## 10. Kết luận kỹ thuật

`batch.size` quyết định mức gom dữ liệu theo byte ở producer; `linger.ms` quyết định producer có thể chờ thêm bao lâu để gom batch. `max.poll.records` quyết định số record tối đa consumer nhận từ một lần poll; `max.poll.interval.ms` giới hạn thời gian ứng dụng có thể xử lý trước lần poll tiếp theo.

Hãy tối ưu producer theo kích thước batch thực tế, request rate, compression và latency. Hãy tối ưu consumer theo thời gian xử lý mỗi poll, bộ nhớ, lag và độ ổn định của consumer group. Khi điều chỉnh dựa trên metric và thử tải đại diện, hệ thống có thể đạt throughput tốt hơn mà vẫn giữ được độ trễ và khả năng phục hồi phù hợp.
