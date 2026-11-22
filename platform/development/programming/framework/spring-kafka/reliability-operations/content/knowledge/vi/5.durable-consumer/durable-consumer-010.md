# max.partition.fetch.bytes

`max.partition.fetch.bytes` là cấu hình của Kafka consumer xác định lượng dữ liệu tối đa mà broker được yêu cầu trả về cho **mỗi partition trong một fetch response**. Đây là một tham số quan trọng khi vận hành consumer có payload lớn, nhiều partition hoặc throughput cao. Cấu hình này ảnh hưởng đến kích thước fetch, số lần trao đổi dữ liệu giữa consumer và broker, bộ nhớ đệm của consumer và khả năng xử lý các record batch lớn.

Trong Spring Kafka, đây vẫn là cấu hình của Kafka Java Consumer ở bên dưới. Spring Kafka và Spring Boot giúp truyền giá trị cấu hình vào consumer; listener container không thay đổi ý nghĩa của tham số này.

## 1. Tham số này kiểm soát điều gì?

Kafka lưu record theo các record batch. Khi consumer gọi `poll()`, Kafka client gửi Fetch request tới broker để lấy dữ liệu từ những partition mà consumer đang sở hữu. Broker trả về dữ liệu theo các batch.

`max.partition.fetch.bytes` đặt giới hạn dữ liệu broker trả về cho một partition trong một lần fetch. Giá trị mặc định của Kafka consumer là **1 MiB**. Ví dụ, nếu cấu hình là 4 MiB, consumer cho phép broker trả về tối đa khoảng 4 MiB dữ liệu cho mỗi partition trong fetch response, tùy theo lượng dữ liệu sẵn có và giới hạn tổng của fetch request.

Tham số này là một giới hạn cho hoạt động fetch. Nó không quy định kích thước tối đa mà producer được phép gửi, không quy định số record mà một lần `poll()` trả về và cũng không phải giới hạn cứng cho toàn bộ heap của consumer.

### 1.1. Giới hạn theo partition

Giả sử một consumer đang được gán ba partition: `orders-0`, `orders-1` và `orders-2`. Với `max.partition.fetch.bytes = 4 MiB`, mỗi partition có giới hạn fetch riêng trong một request. Nếu dữ liệu sẵn có nhỏ hơn giới hạn, broker chỉ trả lượng dữ liệu hiện có. Nếu nhiều partition đều có dữ liệu, tổng response còn chịu ảnh hưởng của `fetch.max.bytes`.

Ví dụ giả định mỗi partition đều có đủ dữ liệu và tổng fetch chưa chạm giới hạn toàn cục:

| Partition | Giới hạn riêng |
|---|---:|
| `orders-0` | 4 MiB |
| `orders-1` | 4 MiB |
| `orders-2` | 4 MiB |

Giới hạn 4 MiB được áp dụng riêng cho từng partition; tổng dữ liệu của response còn phụ thuộc `fetch.max.bytes` và dữ liệu thực tế.

Không nên suy ra rằng consumer luôn nhận đúng 12 MiB trong ví dụ này. Broker có thể trả ít hơn vì partition chưa có đủ dữ liệu, fetch request bị giới hạn bởi `fetch.max.bytes`, hoặc dữ liệu nằm trên các broker khác nhau và được fetch theo những request khác nhau.

### 1.2. Ngoại lệ cho record batch lớn để bảo đảm tiến triển

Kafka có một ngoại lệ quan trọng: nếu record batch đầu tiên trong partition không rỗng của fetch lớn hơn giới hạn được cấu hình, batch đó vẫn có thể được trả về để consumer tiếp tục tiến triển. Vì vậy, `max.partition.fetch.bytes` không phải một hard cap tuyệt đối cho kích thước dữ liệu nhận được.

Cơ chế này giúp tránh tình trạng consumer không thể đọc batch tiếp theo chỉ vì batch lớn hơn giới hạn fetch. Tuy nhiên, không nên dựa vào ngoại lệ đó làm chiến lược cấu hình. Hãy đặt giới hạn phù hợp với kích thước batch lớn nhất mà ứng dụng dự kiến xử lý và tính đến khả năng một batch vượt mức cấu hình.

## 2. Phân biệt với các cấu hình fetch và poll khác

Các thuộc tính Kafka consumer liên quan đến fetch và poll có phạm vi khác nhau. Nhầm lẫn chúng dễ dẫn đến cấu hình thiếu hiệu quả hoặc đánh giá sai mức sử dụng bộ nhớ.

| Thuộc tính | Phạm vi kiểm soát | Ý nghĩa chính |
|---|---|---|
| `max.partition.fetch.bytes` | Mỗi partition trong fetch | Giới hạn dữ liệu trả về cho một partition |
| `fetch.max.bytes` | Tổng dữ liệu của một fetch response | Giới hạn dữ liệu tối đa broker trả về cho một fetch request |
| `max.poll.records` | Mỗi lần gọi `poll()` | Giới hạn số record trả về cho ứng dụng |
| `fetch.min.bytes` | Fetch response | Lượng dữ liệu tối thiểu consumer muốn nhận trước khi broker trả response |
| `fetch.max.wait.ms` | Thời gian chờ fetch | Thời gian tối đa broker chờ để đáp ứng `fetch.min.bytes` |
| `max.poll.interval.ms` | Khoảng cách giữa các lần poll | Thời gian tối đa giữa hai lần gọi `poll()` trước khi consumer có thể bị xem là không còn hoạt động trong group |

### 2.1. max.partition.fetch.bytes và fetch.max.bytes

Hai tham số này bổ sung cho nhau:

- `max.partition.fetch.bytes` giới hạn dữ liệu theo từng partition.
- `fetch.max.bytes` giới hạn tổng dữ liệu mà broker trả về cho một fetch request.

Giá trị mặc định thường dùng của `fetch.max.bytes` là 50 MiB. Nếu consumer đọc nhiều partition, giới hạn tổng này có thể đạt trước khi mọi partition đều dùng hết giới hạn riêng. Ngược lại, một partition có record batch lớn có thể cần nhiều hơn giới hạn riêng thông thường; ngoại lệ batch đầu tiên vẫn có thể áp dụng để bảo đảm tiến triển.

Một consumer có thể fetch dữ liệu từ nhiều broker. Kafka client có thể thực hiện các fetch request song song, vì vậy không nên xem `fetch.max.bytes` là giới hạn tổng bộ nhớ của toàn bộ consumer process.

### 2.2. max.partition.fetch.bytes và max.poll.records

`max.poll.records` giới hạn số record mà một lần `poll()` trả cho ứng dụng. Nó không giới hạn trực tiếp số byte được fetch từ broker và không thay đổi cách client fetch dữ liệu nền.

Ví dụ, một poll trả về 500 record nhỏ có thể sử dụng ít bộ nhớ hơn một poll trả về 50 record có payload lớn. Vì vậy, giảm `max.poll.records` không thay thế việc cấu hình fetch byte khi vấn đề chính là batch hoặc payload lớn.

Nếu listener xử lý record lâu, hãy xem xét cả `max.poll.interval.ms`, concurrency và cách xử lý batch. Tăng hoặc giảm `max.partition.fetch.bytes` không tự giải quyết việc consumer không gọi `poll()` đủ thường xuyên.

### 2.3. fetch.min.bytes và fetch.max.wait.ms

`fetch.min.bytes` cho broker biết consumer muốn nhận tối thiểu bao nhiêu dữ liệu trước khi trả fetch response nếu có thể chờ thêm. `fetch.max.wait.ms` giới hạn thời gian broker chờ điều kiện đó.

Tăng `fetch.min.bytes` có thể giúp gom nhiều dữ liệu hơn trong một response và cải thiện hiệu quả throughput ở workload có lưu lượng đều, nhưng có thể tăng độ trễ khi lưu lượng thấp. Hai tham số này điều chỉnh cách gom dữ liệu theo thời gian; `max.partition.fetch.bytes` điều chỉnh lượng dữ liệu tối đa theo partition.

## 3. Mối liên hệ với kích thước message và cấu hình broker

Consumer chỉ có thể đọc những record batch đã được producer ghi thành công vào Kafka. Giới hạn chấp nhận batch ở phía broker/topic và giới hạn fetch ở phía consumer là hai giai đoạn khác nhau.

Một số cấu hình cần phân biệt:

- Producer `max.request.size`: giới hạn kích thước request mà producer gửi.
- Broker `message.max.bytes`: giới hạn kích thước record batch broker chấp nhận.
- Topic `max.message.bytes`: giới hạn kích thước record batch được chấp nhận cho topic.
- Consumer `max.partition.fetch.bytes`: giới hạn dữ liệu broker trả về cho mỗi partition trong fetch.

Khi ứng dụng cần hỗ trợ payload lớn, phải xem xét toàn bộ đường đi từ producer đến broker rồi đến consumer. Chỉ tăng `max.partition.fetch.bytes` không giúp producer gửi được một batch mà broker từ chối. Tương tự, tăng giới hạn ở broker không bảo đảm consumer có đủ bộ nhớ hoặc xử lý kịp batch lớn.

Compression cũng cần được tính đến. Kafka gửi và lưu record theo batch; kích thước truyền tải có thể khác kích thước payload sau giải nén. Hãy đo batch thực tế trong workload có cấu hình compression giống production thay vì chỉ lấy kích thước JSON hoặc object trong ứng dụng làm căn cứ.

## 4. Cấu hình trong Kafka client thuần

Có thể cấu hình bằng tên thuộc tính:

```java
Properties props = new Properties();

props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-service");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          ByteArrayDeserializer.class);

// Cho phép tối đa khoảng 4 MiB dữ liệu cho mỗi partition trong fetch.
props.put(ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG,
          4 * 1024 * 1024);

// Giới hạn tổng dữ liệu của một fetch response.
props.put(ConsumerConfig.FETCH_MAX_BYTES_CONFIG,
          50 * 1024 * 1024);

try (KafkaConsumer<String, byte[]> consumer =
         new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));
    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, byte[]> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, byte[]> record : records) {
            process(record);
        }
    }
}
```

Đây là ví dụ cấu hình minh họa. Trong ứng dụng thực tế, cần có xử lý lỗi, shutdown/wakeup, commit offset và chính sách xử lý record phù hợp. Các thuộc tính byte được tính theo byte, nên 4 MiB tương ứng với `4 * 1024 * 1024`, không phải số record.

Nếu dùng `Map<String, Object>` để tạo `DefaultKafkaConsumerFactory`, có thể đặt cùng key `ConsumerConfig.MAX_PARTITION_FETCH_BYTES_CONFIG` trong map cấu hình consumer. Spring Kafka chuyển thuộc tính này xuống Kafka Java Consumer.

## 5. Cấu hình trong Spring Boot và Spring Kafka

Với Spring Boot, có thể khai báo trực tiếp trong `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: kafka-1:9092,kafka-2:9092
      group-id: orders-service
      max-partition-fetch-bytes: 4194304
      properties:
        "[fetch.max.bytes]": 52428800
```

Trong ví dụ:

- `max-partition-fetch-bytes: 4194304` tương đương 4 MiB cho mỗi partition.
- `fetch.max.bytes: 52428800` tương đương 50 MiB cho tổng fetch response.

Spring Boot ánh xạ `max-partition-fetch-bytes` vào cấu hình consumer tương ứng. Nếu ứng dụng tự khai báo `ConsumerFactory` hoặc cung cấp map cấu hình riêng, cần bảo đảm giá trị mong muốn được đưa vào factory thực sự được listener container sử dụng.

Với listener concurrency, mỗi consumer instance có cấu hình fetch riêng và được gán một phần partition của group. Ví dụ:

```java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service",
    concurrency = "3"
)
public void consume(OrderEvent event) {
    orderService.handle(event);
}
```

Concurrency bằng 3 có nghĩa container chạy ba consumer instance cho listener này. Nó không biến `max.partition.fetch.bytes` thành một giới hạn tổng cho cả listener. Khi đánh giá bộ nhớ, cần tính đến số consumer instance, số partition mỗi consumer được gán, số broker đang fetch và kích thước batch thực tế.

## 6. Cách chọn giá trị phù hợp

Không có một giá trị tối ưu cho mọi hệ thống. Giá trị phù hợp phụ thuộc vào kích thước record batch, số partition được gán cho mỗi consumer, số consumer instance, throughput, độ trễ mục tiêu và bộ nhớ khả dụng.

### Bước 1: Xác định kích thước batch lớn nhất

Tìm hiểu kích thước batch thực tế mà producer tạo ra trong điều kiện production. Xem xét:

- Payload lớn nhất được nghiệp vụ cho phép.
- Số record trong một producer batch.
- Compression codec và tỷ lệ nén.
- Giới hạn `max.request.size` ở producer.
- Giới hạn `message.max.bytes` ở broker và `max.message.bytes` ở topic.

Cần phân biệt kích thước một record với kích thước record batch. Consumer fetch theo batch, do đó một batch chứa nhiều record có thể lớn hơn một record đơn lẻ.

### Bước 2: Đặt giới hạn partition đủ cho batch dự kiến

Đặt `max.partition.fetch.bytes` sao cho batch thông thường và batch lớn hợp lệ có thể được fetch hiệu quả. Nếu ứng dụng thường tạo batch vài MiB nhưng consumer chỉ đặt giới hạn rất nhỏ, client có thể phải fetch theo nhiều lượt hơn hoặc dựa vào ngoại lệ batch đầu tiên để tiếp tục đọc.

Không nên tăng giá trị lên mức rất lớn khi chưa có dữ liệu đo. Một giới hạn lớn làm tăng lượng dữ liệu mà consumer có thể nhận và giữ trong bộ nhớ, đặc biệt khi consumer sở hữu nhiều partition.

### Bước 3: Kiểm tra giới hạn tổng fetch

Đối chiếu `fetch.max.bytes` với số partition có dữ liệu đồng thời và mức throughput mong muốn. Nếu giới hạn tổng quá nhỏ so với lượng dữ liệu cần lấy từ nhiều partition, nó có thể trở thành nút thắt dù giới hạn mỗi partition đã đủ lớn.

Cần nhớ rằng Kafka có thể fetch từ nhiều broker song song. Vì vậy, không thể tính chính xác heap tối đa chỉ bằng cách nhân `fetch.max.bytes` với một con số cố định.

### Bước 4: Tính đến concurrency và số partition

Trong Spring Kafka, concurrency tạo nhiều consumer instance. Mỗi instance có fetch buffer và partition assignment riêng. Khi tăng concurrency, tổng mức sử dụng bộ nhớ và số request fetch của ứng dụng cũng có thể tăng.

Ví dụ, một service có 24 partition và concurrency bằng 6 sẽ có tối đa sáu consumer instance trong listener container đó; mỗi consumer được phân bổ partition theo assignment của group. Việc tăng `max.partition.fetch.bytes` lên 8 MiB không có nghĩa heap của toàn listener bị giới hạn ở 8 MiB. Cần thử nghiệm trên toàn bộ container với dữ liệu lớn và lưu lượng thực tế.

### Bước 5: Đo và điều chỉnh

Thay đổi từng nhóm cấu hình có kiểm soát. Quan sát các chỉ số như:

- Fetch size trung bình và lớn nhất.
- Fetch latency trung bình và cao nhất.
- Bytes consumed rate và records consumed rate.
- Consumer lag theo partition.
- Heap usage, allocation rate và GC pause.
- Thời gian xử lý listener và khoảng cách giữa các lần poll.

Nếu fetch size thường xuyên chạm giới hạn và consumer vẫn có lag, hãy xem xét kích thước batch, giới hạn tổng fetch, số partition, throughput của broker và tốc độ xử lý. Nếu tăng giới hạn làm heap hoặc GC tăng mạnh, hãy cân nhắc giảm batch, giảm số partition trên mỗi consumer, điều chỉnh concurrency hoặc tăng tài nguyên phù hợp.

## 7. Ảnh hưởng đến độ tin cậy và vận hành

### 7.1. Giá trị quá thấp

Giới hạn thấp có thể làm giảm lượng dữ liệu lấy được trong mỗi fetch và tăng số lượt trao đổi khi consumer cần đọc nhiều dữ liệu. Kafka có cơ chế cho phép batch đầu tiên lớn hơn giới hạn trong trường hợp cần thiết để consumer tiến triển, nên không thể xem giá trị thấp là một cách chặn tuyệt đối batch lớn.

Tuy nhiên, dựa vào ngoại lệ này khiến mức sử dụng bộ nhớ và kích thước response khó dự đoán hơn. Nếu workload có batch lớn hợp lệ, hãy cấu hình giới hạn tương ứng và kiểm thử bằng batch thực tế.

### 7.2. Giá trị quá cao

Giới hạn lớn cho phép consumer nhận nhiều dữ liệu hơn trong một fetch. Với nhiều partition và nhiều consumer instance, lượng dữ liệu đang chờ xử lý có thể tăng, kéo theo heap pressure, GC và nguy cơ ảnh hưởng đến các thành phần khác trong process.

Một giá trị cao không tự động làm tăng throughput. Nếu listener xử lý chậm, database là bottleneck hoặc broker không đủ năng lực, fetch lớn chỉ có thể làm tăng dữ liệu đang chờ trong bộ nhớ.

### 7.3. Không dùng tham số này để sửa lỗi producer hoặc broker

Nếu producer nhận lỗi record/batch quá lớn khi gửi, cần kiểm tra `max.request.size`, `message.max.bytes` và `max.message.bytes`. Tăng `max.partition.fetch.bytes` ở consumer không thay đổi quyết định chấp nhận ghi của broker.

Nếu consumer không đọc được do deserialize lỗi, payload không hợp lệ hoặc listener xử lý exception, tăng giới hạn fetch cũng không giải quyết nguyên nhân. Cần phân biệt lỗi ghi, lỗi fetch, lỗi deserialize và lỗi xử lý nghiệp vụ.

### 7.4. Kết hợp với chính sách xử lý và commit offset

Fetch size chỉ điều chỉnh cách dữ liệu đến consumer. Nó không quyết định thời điểm commit offset hay delivery semantics. Với Spring Kafka, cần chọn AckMode và error handler phù hợp; với Kafka client thuần, cần xác định rõ commit đồng bộ/bất đồng bộ và offset được commit sau khi xử lý thành công.

Nếu listener xử lý batch lớn hoặc nhiều record trong một poll, thời gian xử lý có thể tăng. Hãy kiểm tra `max.poll.interval.ms` và thiết kế xử lý để consumer tiếp tục gọi `poll()` trong giới hạn phù hợp. Đặt fetch byte lớn mà không tính thời gian xử lý có thể làm tăng nguy cơ consumer bị loại khỏi group khi xử lý kéo dài.

## 8. Chẩn đoán sự cố liên quan đến fetch size

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| Consumer lag tăng khi có payload lớn | Kích thước batch, fetch size, throughput broker và thời gian xử lý listener |
| Fetch size lớn, heap tăng hoặc GC kéo dài | Số partition được gán, concurrency, fetch.max.bytes và tốc độ xử lý |
| Consumer đọc chậm dù fetch limit lớn | Broker/network throughput, số partition, deserialize, downstream và listener latency |
| Producer báo batch/request quá lớn | Producer max.request.size và broker/topic message size limits |
| Listener bị rebalance khi xử lý batch | Thời gian xử lý giữa các lần poll, max.poll.interval.ms và max.poll.records |
| Chỉ một partition có lag cao | Phân bố key, kích thước batch, dữ liệu bất thường và tốc độ xử lý partition đó |

Khi điều tra, hãy kiểm tra cấu hình consumer thực tế sau khi Spring Boot binding và custom factory đã hoàn tất. Một giá trị trong file YAML chưa chắc là giá trị đang chạy nếu ứng dụng có cấu hình riêng ghi đè.

Một quy trình điều tra hữu ích:

1. Xác định consumer group, listener container và consumer instance đang có lag.
2. Xem partition nào có lag và partition đó có record batch lớn bất thường hay không.
3. Đọc cấu hình runtime của consumer, đặc biệt `max.partition.fetch.bytes`, `fetch.max.bytes`, `max.poll.records` và `max.poll.interval.ms`.
4. So sánh fetch size, fetch latency, bytes consumed rate, heap và GC trong cùng khoảng thời gian.
5. Kiểm tra giới hạn ghi ở producer, broker và topic nếu lỗi xuất hiện từ lúc publish.
6. Thử lại với batch lớn nhất hợp lệ và tải đồng thời gần production trước khi áp dụng thay đổi rộng.

## 9. Các lỗi cấu hình thường gặp

**Cho rằng đây là giới hạn kích thước một record.** Tham số điều chỉnh dữ liệu fetch theo partition và Kafka truyền record theo batch. Cần kiểm tra kích thước batch thực tế.

**Cho rằng đây là giới hạn tổng bộ nhớ.** Một consumer có thể fetch từ nhiều broker, giữ dữ liệu cho nhiều partition và chạy cùng các consumer instance khác. Tham số này không phải heap cap.

**Chỉ tăng max.partition.fetch.bytes mà bỏ qua fetch.max.bytes.** Khi nhiều partition có dữ liệu đồng thời, giới hạn tổng fetch cũng ảnh hưởng đến lượng dữ liệu nhận được.

**Dùng max.poll.records để thay thế giới hạn byte.** Một giới hạn số record không kiểm soát được kích thước byte khi payload có độ lớn khác nhau.

**Tăng concurrency mà không tính chi phí bộ nhớ.** Mỗi consumer instance có hoạt động fetch riêng. Tăng concurrency có thể làm tăng số fetch request và dữ liệu đệm trong process.

**Chỉ thay đổi consumer khi broker đang từ chối batch.** Lỗi ghi quá lớn cần được xử lý ở producer và broker/topic. Cấu hình fetch chỉ có tác dụng sau khi dữ liệu đã được Kafka chấp nhận.

**Dựa vào giá trị mặc định trong mọi môi trường.** Kích thước batch, partition count và concurrency giữa môi trường test và production có thể khác nhau. Cần kiểm thử theo tải và payload thực tế.

## 10. Checklist triển khai

Trước khi thay đổi `max.partition.fetch.bytes`, hãy xác nhận:

- [ ] Đã đo hoặc ước lượng có cơ sở kích thước record batch lớn nhất.
- [ ] Producer và broker/topic cho phép ghi batch có kích thước đó.
- [ ] Giá trị partition fetch phù hợp với batch dự kiến.
- [ ] `fetch.max.bytes` phù hợp với lượng dữ liệu có thể đến từ nhiều partition.
- [ ] Đã tính đến số partition mỗi consumer sở hữu và listener concurrency.
- [ ] Đã kiểm tra heap, GC và thời gian xử lý listener khi có payload lớn.
- [ ] Đã kiểm tra `max.poll.records` và `max.poll.interval.ms` nếu thời gian xử lý tăng.
- [ ] Đã thử nghiệm với batch lớn nhất hợp lệ, nhiều partition có dữ liệu đồng thời và tải gần production.
- [ ] Có dashboard hoặc cảnh báo cho consumer lag, fetch latency và bộ nhớ.

`max.partition.fetch.bytes` là một nút điều chỉnh kích thước fetch theo partition. Hãy chọn giá trị dựa trên kích thước batch hợp lệ và năng lực bộ nhớ của toàn bộ consumer deployment, sau đó kiểm chứng bằng metrics và thử nghiệm tải. Trong Spring Kafka, cấu hình này được truyền xuống Kafka consumer mà listener container sử dụng; các quyết định về commit, retry, xử lý lỗi và thời gian poll vẫn cần được thiết kế riêng.

