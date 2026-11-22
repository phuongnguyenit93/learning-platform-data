# buffer.memory, max.block.ms và áp lực ngược lên bên gửi

## Mục tiêu bài học

Kafka producer nhận record từ ứng dụng nhanh hơn hoặc chậm hơn tốc độ broker có thể tiếp nhận. Để hấp thụ các đợt tăng tải ngắn, producer giữ record trong bộ nhớ đệm và gom chúng thành batch trước khi gửi. Nếu dữ liệu đầu vào liên tục nhanh hơn tốc độ gửi, buffer dần đầy. Khi đó producer phải tạo áp lực ngược (backpressure) lên ứng dụng bằng cách chờ cấp phát bộ nhớ hoặc báo lỗi khi hết thời gian chờ.

Sau bài học, bạn có thể:

- Giải thích vai trò của `buffer.memory` trong record accumulator và buffer pool.
- Phân biệt `buffer.memory`, `batch.size`, `linger.ms` và `max.request.size`.
- Mô tả khi nào `KafkaProducer.send()` phải chờ và khi nào ném `TimeoutException`.
- Phân biệt `max.block.ms` với `request.timeout.ms` và `delivery.timeout.ms`.
- Nhận diện tình trạng producer bị nghẽn do tốc độ đầu vào vượt tốc độ gửi.
- Thiết kế giới hạn số record đang chờ, queue có giới hạn và cách phản hồi khi quá tải.
- Theo dõi buffer pressure và điều chỉnh producer dựa trên metric thay vì tăng bộ nhớ theo cảm tính.

## 1. Vì sao producer cần buffer?

Ứng dụng có thể tạo record theo từng request, trong khi Kafka producer gửi dữ liệu theo batch. Nếu gửi một request mạng cho mỗi record, chi phí network, protocol và broker sẽ cao. Producer vì vậy giữ record tạm thời, phân nhóm theo partition rồi gửi nhiều record trong cùng một Produce request.

Luồng đơn giản:

```text
Business threads
      |
      | send(record)
      v
Serialize key/value
      |
      v
Select partition
      |
      v
Record accumulator / buffer pool
      |
      | batch ready
      v
Sender thread
      |
      v
Broker
```

Buffer giúp producer hấp thụ burst ngắn, gom batch và tiếp tục nhận record trong lúc sender thread đang chờ response hoặc gửi batch khác. Nhưng buffer có dung lượng hữu hạn. Nếu producer nhận dữ liệu nhanh hơn khả năng gửi trong thời gian đủ dài, lượng record chờ sẽ tăng cho đến khi không còn buffer có thể cấp phát.

Backpressure là cách hệ thống phản hồi tình trạng này bằng cách làm chậm, giới hạn hoặc từ chối đầu vào để tốc độ tạo dữ liệu không vượt quá khả năng xử lý trong thời gian dài. Với Kafka producer, việc chờ cấp phát buffer có thể tạo backpressure trực tiếp lên thread gọi `send()`. Ứng dụng cũng nên chủ động kiểm soát tốc độ đầu vào thay vì phụ thuộc hoàn toàn vào thời gian chờ bên trong producer.

## 2. `buffer.memory` quản lý bộ nhớ nào?

### 2.1. Bộ nhớ dành cho record đang chờ gửi

`buffer.memory` đặt tổng lượng bộ nhớ mà producer dùng cho việc buffer record đang chờ gửi đến broker. Producer quản lý vùng này thông qua buffer pool và record accumulator. Record được serialize, phân vào partition rồi lưu vào batch trong accumulator.

Ví dụ cấu hình:

```java
props.put("buffer.memory", 64L * 1024 * 1024); // 64 MiB
```

Giá trị trên là ví dụ cú pháp, không phải khuyến nghị cho mọi workload. Kích thước phù hợp phụ thuộc số partition mà producer ghi đồng thời, kích thước record, batch, throughput, thời gian broker phản hồi và giới hạn heap/container.

### 2.2. `buffer.memory` không phải giới hạn toàn bộ heap

Không nên hiểu `buffer.memory` là tổng RAM tối đa mà process producer được phép sử dụng. Kafka producer còn cần bộ nhớ cho metadata, request/response, compression, serializer, interceptor, thread stack, object Java và các cấu trúc nội bộ khác. Một số vùng nhớ có thể nằm ngoài phần buffer được tính bởi cấu hình này.

Vì vậy, nếu đặt `buffer.memory=64 MiB`, tổng heap hoặc resident memory của ứng dụng không bị giới hạn ở 64 MiB. Cần dự trù bộ nhớ cho toàn bộ process và các thư viện chạy cùng ứng dụng.

### 2.3. Buffer pool được dùng chung giữa các partition

Producer ghi vào nhiều partition có thể cần nhiều batch đang mở cùng lúc. Buffer pool được dùng chung để cấp phát bộ nhớ cho các batch. Khi số partition hoạt động tăng, số batch có thể tồn tại đồng thời cũng tăng; do đó, một producer ghi vào rất nhiều partition có thể tiêu thụ buffer theo cách khác với producer chỉ ghi vào một vài partition.

Nếu buffer pool không còn vùng nhớ đủ để cấp phát batch, producer có thể phải chờ cho đến khi sender gửi batch và giải phóng bộ nhớ, hoặc cho đến khi hết `max.block.ms`.

## 3. Phân biệt các cấu hình bộ nhớ và batching

Các cấu hình sau liên quan với nhau nhưng không thay thế nhau:

| Cấu hình | Phạm vi | Vai trò |
|---|---|---|
| `buffer.memory` | Producer | Tổng bộ nhớ buffer dành cho record đang chờ gửi |
| `batch.size` | Mỗi partition/batch | Kích thước batch mục tiêu khi gom record |
| `linger.ms` | Producer/batch | Thời gian chờ thêm record để batch có cơ hội đầy hơn |
| `max.request.size` | Produce request | Giới hạn kích thước request mà producer có thể gửi; cũng ảnh hưởng giới hạn record batch |
| `max.block.ms` | Lời gọi ứng dụng | Thời gian tối đa `send()`/`partitionsFor()` chờ metadata hoặc buffer |
| `delivery.timeout.ms` | Từng record gửi | Tổng thời gian tối đa producer cố gắng hoàn tất gửi sau khi `send()` trả về |
| `request.timeout.ms` | Một request | Thời gian chờ response cho request mạng |

### 3.1. `batch.size`

`batch.size` đặt kích thước batch mục tiêu cho một partition. Record cùng partition có thể được gom chung để giảm số request và tăng hiệu quả nén.

Ví dụ:

```java
props.put("batch.size", 32 * 1024); // 32 KiB
```

Nếu batch đầy trước khi hết `linger.ms`, producer có thể gửi batch sớm. Nếu lưu lượng thấp, batch có thể nhỏ hơn `batch.size` nhưng vẫn được gửi khi hết thời gian chờ hoặc khi có điều kiện gửi khác.

Tăng `batch.size` có thể cải thiện throughput khi workload đủ dữ liệu, nhưng cần nhiều buffer hơn và có thể làm tăng thời gian chờ để batch được lấp đầy. Nó không có nghĩa producer sẽ luôn cấp phát chính xác một batch lớn cho mọi partition ngay khi khởi động.

### 3.2. `linger.ms`

`linger.ms` cho producer thêm thời gian để gom record trước khi gửi batch chưa đầy. Giá trị lớn hơn có thể tăng batch size trung bình và hiệu quả compression, đổi lại tăng latency chờ trong trường hợp lưu lượng thấp.

`linger.ms` không phải thời gian chờ buffer khi buffer đã đầy. Khi thiếu bộ nhớ, cơ chế cấp phát buffer và `max.block.ms` mới quyết định `send()` phải chờ bao lâu.

### 3.3. `max.request.size`

`max.request.size` giới hạn kích thước request mà producer có thể gửi. Nó có liên quan đến kích thước record batch tối đa, nhưng không phải cấu hình tổng dung lượng buffer. Một record quá lớn vẫn có thể bị từ chối dù `buffer.memory` còn nhiều.

Khi điều chỉnh kích thước message, cần xem đồng thời giới hạn ở producer, broker và topic, ví dụ `max.request.size`, `message.max.bytes` và `max.message.bytes`. Tên và hành vi chi tiết có thể phụ thuộc phiên bản Kafka.

## 4. Khi nào `send()` bị block?

### 4.1. Chờ metadata

Producer cần metadata để biết partition và broker leader. Nếu chưa có metadata cho topic hoặc metadata cần được làm mới, `send()` có thể chờ lấy metadata. Thời gian chờ này thuộc phạm vi `max.block.ms`.

Các nguyên nhân thường gặp:

- Topic chưa tồn tại hoặc chưa được tạo xong.
- Broker bootstrap không truy cập được.
- DNS, listener hoặc `advertised.listeners` sai.
- Metadata request bị timeout hoặc cluster chưa sẵn sàng.

Trong tình huống này, tăng `buffer.memory` không giải quyết được gốc rễ vì producer đang thiếu metadata chứ không nhất thiết thiếu buffer.

### 4.2. Chờ cấp phát buffer

Khi producer đã xác định partition nhưng buffer pool không còn bộ nhớ để cấp phát batch, thread gọi `send()` có thể chờ cho đến khi sender giải phóng buffer hoặc hết `max.block.ms`.

Ví dụ:

```text
Ứng dụng gửi record liên tục
          |
          v
Buffer pool còn bộ nhớ?
      /           \
    Có             Không
    |                |
    v                v
Đưa record vào    Chờ buffer được giải phóng
accumulator       hoặc hết max.block.ms
    |                |
    v                v
send() trả về    Buffer có lại?
Future              /    \
                   Có     Không
                   |        |
                   v        v
               Tiếp tục   TimeoutException
```

### 4.3. `max.block.ms` giới hạn điều gì?

`max.block.ms` đặt giới hạn thời gian các thao tác như `KafkaProducer.send()` và `partitionsFor()` có thể chờ metadata hoặc buffer allocation. Nếu không hoàn tất trong giới hạn, producer có thể ném `TimeoutException` ngay từ lời gọi.

Lưu ý:

- `max.block.ms` không phải timeout cho toàn bộ quá trình broker xử lý record sau khi `send()` đã trả về.
- Thời gian thực thi serializer hoặc partitioner do ứng dụng cung cấp không được tính như một timeout tổng quát cho logic tùy chỉnh đó.
- Nếu `send()` ném exception đồng bộ, callback của record đó không phải cơ chế để nhận lỗi; ứng dụng cần `try/catch` quanh chính lời gọi.
- Tăng `max.block.ms` chỉ cho producer chờ lâu hơn. Nếu đầu vào tiếp tục vượt khả năng gửi, vấn đề buffer pressure vẫn còn.

Ví dụ:

```java
props.put("max.block.ms", 10_000); // 10 giây

try {
    producer.send(record, callback);
} catch (org.apache.kafka.common.errors.TimeoutException ex) {
    // Có thể là chờ metadata hoặc buffer quá lâu.
    // Phân loại lỗi và áp dụng backpressure ở tầng ứng dụng.
    handleSendCouldNotBeEnqueued(record, ex);
}
```

Đừng tự động gửi lại record vô hạn ngay trong `catch`. Nếu lỗi do broker chậm hoặc buffer đã đầy, retry lập tức sẽ làm tăng áp lực và khiến tình trạng quá tải kéo dài.

## 5. Phân biệt ba loại timeout quan trọng

`max.block.ms`, `request.timeout.ms` và `delivery.timeout.ms` điều khiển các giai đoạn khác nhau:

| Cấu hình | Thời điểm áp dụng | Ý nghĩa |
|---|---|---|
| `max.block.ms` | Trước khi `send()` trả về | Giới hạn chờ metadata hoặc buffer allocation |
| `request.timeout.ms` | Khi một request đã được gửi | Giới hạn thời gian chờ response của request đó |
| `delivery.timeout.ms` | Sau khi `send()` trả về | Giới hạn tổng thời gian producer cố gắng giao record, bao gồm batching, request và retry |

Ví dụ timeline:

```text
T0                  T1                    T2                  T3
|-------------------|---------------------|-------------------|
send() được gọi     send() trả Future     Produce request     Kết quả cuối
                    ^                     ^                   ^
                    |                     |                   |
              max.block.ms          request.timeout.ms   delivery.timeout.ms
              chờ metadata/         chờ response         hết hạn tổng thể
              buffer
```

Sơ đồ mang tính khái niệm: producer có thể gửi nhiều request và retry trong khoảng delivery deadline. `request.timeout.ms` có thể xảy ra nhiều lần trong một lần giao record; `delivery.timeout.ms` là ngân sách tổng thể để producer báo kết quả cuối cùng.

Nếu `send()` trả về thành công nhưng broker không phản hồi đúng hạn, Future/callback sẽ hoàn tất theo kết quả retry và delivery timeout. Nếu `send()` chưa thể đưa record vào accumulator vì metadata hoặc buffer, lỗi có thể xuất hiện đồng bộ qua `max.block.ms`.

## 6. Backpressure hình thành như thế nào?

### 6.1. Tốc độ đầu vào và tốc độ đầu ra

Gọi:

- `R_in`: tốc độ ứng dụng tạo và đưa record vào producer.
- `R_out`: tốc độ producer gửi record thành công và giải phóng buffer.
- `B`: lượng buffer còn khả dụng.

Nếu trong một khoảng thời gian dài `R_in > R_out`, lượng dữ liệu chờ tăng. Khi buffer pool đầy, producer bắt đầu chờ cấp phát buffer. Nếu tình trạng kéo dài, `send()` có thể hết `max.block.ms` và ném lỗi.

Ví dụ:

```text
Tốc độ ứng dụng tạo record:  80 MB/s
Tốc độ producer gửi đi:      50 MB/s
Chênh lệch tích lũy:         30 MB/s

Buffer trống ban đầu:        300 MB
Thời gian lấp đầy xấp xỉ:    300 / 30 = 10 giây
```

Đây là phép tính minh họa, giả định tốc độ ổn định, bỏ qua batching, compression, overhead và thay đổi tốc độ broker. Nó cho thấy tăng buffer có thể kéo dài thời gian hấp thụ burst, nhưng không khắc phục tình trạng mất cân bằng kéo dài.

### 6.2. Buffer đầy là dấu hiệu, không phải nguyên nhân gốc duy nhất

Producer buffer có thể đầy do:

- Broker xử lý produce request chậm.
- Network giữa producer và broker bị nghẽn hoặc mất gói.
- Broker đang rebalance, unavailable hoặc partition leader thay đổi.
- Lưu lượng đầu vào tăng đột biến.
- `linger.ms` hoặc batching làm record ở lại accumulator lâu hơn.
- Producer gửi đến quá nhiều partition và tạo nhiều batch cùng lúc.
- Callback hoặc thread ứng dụng xử lý kết quả chậm, khiến hệ thống phía trên không giải phóng được công việc đang chờ.

Chỉ tăng `buffer.memory` khi cần hấp thụ burst ngắn và process có đủ bộ nhớ. Nếu broker chỉ xử lý được 50 MB/s trong khi ứng dụng tạo 80 MB/s liên tục, mọi buffer hữu hạn cuối cùng đều đầy.

### 6.3. Backpressure cần truyền ngược lên nguồn tạo event

Nếu producer chỉ block một thread nhưng ứng dụng tiếp tục nhận request và đưa chúng vào một queue không giới hạn, áp lực chỉ chuyển từ buffer Kafka sang heap của ứng dụng. Kết quả có thể là OutOfMemoryError hoặc độ trễ tăng không kiểm soát.

Một hệ thống có backpressure tốt cần giới hạn hàng đợi ở các tầng:

```text
Incoming requests
       |
       v
Bounded application queue
       |
       v
Producer in-flight limit
       |
       v
Kafka producer buffer
       |
       v
Broker capacity
```

Khi tầng dưới không theo kịp, tầng trên phải có một hành động rõ ràng: giảm tốc độ nhận, chặn có thời hạn, trả lỗi quá tải, hoặc ghi vào một kho bền vững để xử lý sau. Không nên dùng queue vô hạn để che giấu tình trạng thiếu năng lực xử lý.

## 7. Thiết kế giới hạn công việc đang chờ

### 7.1. Giới hạn số record in-flight bằng semaphore

Một cách đơn giản là giới hạn số record đang chờ kết quả. Khi một record được gửi thành công hoặc thất bại, callback giải phóng một permit. Nếu không còn permit trong khoảng chờ cho phép, ứng dụng áp dụng backpressure ngay ở tầng business.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

private final Semaphore inFlight = new Semaphore(500);

public void publish(ProducerRecord<String, String> record) throws InterruptedException {
    if (!inFlight.tryAcquire(1, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Publisher is overloaded");
    }

    AtomicBoolean released = new AtomicBoolean(false);
    Runnable releasePermit = () -> {
        if (released.compareAndSet(false, true)) {
            inFlight.release();
        }
    };

    try {
        producer.send(record, (metadata, exception) -> {
            try {
                if (exception != null) {
                    handleFailure(record, exception);
                } else {
                    handleSuccess(metadata);
                }
            } finally {
                releasePermit.run();
            }
        });
    } catch (RuntimeException ex) {
        releasePermit.run();
        throw ex;
    }
}
```

Ví dụ giới hạn tối đa 500 record đang chờ kết quả và chờ tối đa một giây để lấy permit. `AtomicBoolean` bảo đảm permit chỉ được trả lại một lần trong các nhánh xử lý lỗi. Trong ứng dụng thực tế, `handleFailure` và `handleSuccess` cần nhanh; nếu xử lý lâu, hãy chuyển chúng sang executor có queue giới hạn.

Giới hạn này là kiểm soát ở tầng ứng dụng. Nó không thay thế `buffer.memory`, vì mỗi record có kích thước khác nhau. 500 record nhỏ có thể chiếm ít bộ nhớ hơn 500 record lớn rất nhiều. Với workload có kích thước record biến động mạnh, có thể cần giới hạn theo byte hoặc kết hợp semaphore với bounded queue.

### 7.2. Dùng queue có giới hạn

Nếu business thread không nên gọi producer trực tiếp, có thể đưa event vào `ArrayBlockingQueue` và dùng một hoặc nhiều worker để gửi. Queue cần có capacity cố định và chính sách khi đầy.

```java
BlockingQueue<OrderEvent> queue = new ArrayBlockingQueue<>(1_000);

public boolean submit(OrderEvent event) {
    return queue.offer(event); // false nếu queue đã đầy
}
```

Khi `offer()` trả về `false`, ứng dụng phải quyết định trả lỗi cho caller, thử lại có giới hạn, lưu event vào outbox hoặc áp dụng chính sách nghiệp vụ khác. Không nên bỏ qua giá trị trả về rồi giả định event đã được nhận.

Nếu dùng `put()` thay cho `offer()`, thread gọi sẽ block cho đến khi queue có chỗ. Đây cũng là backpressure, nhưng cần giới hạn thời gian hoặc kiểm soát lifecycle để tránh làm nghẽn thread pool phía trên.

### 7.3. Giới hạn theo byte

Giới hạn số record phù hợp khi kích thước payload tương đối đồng đều. Nếu một record có thể lớn gấp hàng trăm lần record khác, nên ước lượng serialized size và quản lý ngân sách byte.

Một bộ giới hạn theo byte có thể:

1. Ước lượng hoặc đo kích thước serialized key/value.
2. Giữ một ngân sách byte tối đa cho record đang chờ.
3. Từ chối hoặc chờ khi không còn ngân sách.
4. Hoàn trả ngân sách khi callback hoàn tất.

Kích thước trước serialize có thể khác kích thước sau serialize hoặc sau compression. Vì vậy, giới hạn byte của ứng dụng là cơ chế kiểm soát gần đúng; vẫn cần theo dõi buffer metrics của Kafka producer.

## 8. Điều chỉnh producer khi buffer pressure tăng

Không có một bộ giá trị đúng cho mọi ứng dụng. Hãy điều chỉnh dựa trên dấu hiệu đo được:

| Quan sát | Hướng kiểm tra/điều chỉnh |
|---|---|
| `buffer-available-bytes` liên tục gần 0 | Kiểm tra producer throughput, broker/network và số record đang chờ; cân nhắc tăng buffer nếu chỉ là burst ngắn |
| `waiting-threads` tăng | `send()` đang phải chờ buffer; kiểm tra tốc độ đầu vào và tốc độ giải phóng batch |
| `record-queue-time-avg/max` tăng | Record ở lâu trong accumulator; kiểm tra `linger.ms`, batch, broker response và tải partition |
| Batch size trung bình nhỏ | Xem số record theo partition, `linger.ms`, tần suất flush và tốc độ đầu vào |
| Produce request latency tăng | Điều tra broker, network, request queue và disk; tăng buffer đơn thuần chỉ trì hoãn lúc đầy |
| Retry/error rate tăng | Kiểm tra broker availability, timeout, leader changes và network |
| Heap/container memory gần giới hạn | Không tăng `buffer.memory` trước khi dự trù toàn bộ bộ nhớ process |

### 8.1. Khi nào tăng `buffer.memory`?

Tăng `buffer.memory` có thể phù hợp khi:

- Lưu lượng tăng theo burst ngắn, sau đó giảm về mức broker có thể xử lý.
- Sender vẫn giải phóng buffer đều nhưng buffer hiện tại quá nhỏ để hấp thụ burst.
- Process còn đủ heap/RAM và số producer/partition đã được tính đến.
- Metric cho thấy chờ buffer chứ không phải chờ metadata hoặc broker/network lỗi kéo dài.

Không nên tăng buffer khi:

- Tốc độ đầu vào cao hơn năng lực broker liên tục.
- Producer bị nghẽn do broker unavailable hoặc network partition.
- Ứng dụng có queue vô hạn phía trước producer.
- Heap/container đã gần giới hạn.
- Nhiều producer instance cùng tăng buffer khiến tổng memory vượt ngân sách.

### 8.2. Khi nào điều chỉnh `batch.size` và `linger.ms`?

Nếu batch nhỏ do lưu lượng thấp trên từng partition, tăng `linger.ms` có thể cho producer thêm thời gian gom record. Nếu workload có nhiều record cùng partition, tăng `batch.size` có thể cải thiện batching và compression.

Nếu batch đã lớn nhưng broker không thể xử lý đủ nhanh, tăng batch hoặc linger có thể chỉ làm record nằm trong buffer lâu hơn. Hãy đo throughput, latency, batch-size và queue-time trước khi thay đổi.

### 8.3. Khi nào tăng `max.block.ms`?

Tăng `max.block.ms` chỉ hợp lý khi ứng dụng chấp nhận chờ lâu hơn để metadata hoặc buffer được giải phóng và việc chờ đó là tạm thời. Nếu cần SLA phản hồi thấp, chờ lâu hơn có thể làm thread request bị chiếm dụng và tạo hàng đợi ở các tầng trên.

Khi `max.block.ms` hết hạn thường xuyên, hãy điều tra lý do producer không lấy được metadata hoặc buffer. Không dùng giá trị rất lớn để che giấu tình trạng broker không theo kịp.

## 9. Quan sát producer buffer và backpressure

### 9.1. Các metric hữu ích

Kafka producer cung cấp metric qua `producer.metrics()` và JMX. Tên metric cụ thể có thể khác theo phiên bản client và hệ thống exporter; các metric thường hữu ích gồm:

| Metric | Ý nghĩa vận hành |
|---|---|
| `buffer-available-bytes` | Số byte buffer còn khả dụng |
| `buffer-total-bytes` | Tổng dung lượng buffer pool |
| `waiting-threads` | Số thread đang chờ buffer allocation |
| `bufferpool-wait-time-total` | Tổng thời gian chờ buffer pool |
| `record-queue-time-avg` / `record-queue-time-max` | Thời gian record ở trong queue/accumulator trước khi gửi |
| `batch-size-avg` / `batch-size-max` | Kích thước batch được gửi |
| `records-per-request-avg` | Số record trung bình trong mỗi request |
| `request-latency-avg` / `request-latency-max` | Độ trễ request đến broker |
| `record-retry-rate` / `record-error-rate` | Tỷ lệ retry và lỗi record |

Không phải mọi metric đều xuất hiện dưới cùng tên ở mọi phiên bản. Hãy kiểm tra `producer.metrics()` hoặc danh sách MBean thực tế trước khi cấu hình dashboard và alert.

### 9.2. Theo dõi cùng metric của ứng dụng và broker

Metric producer chỉ cho thấy một phần bức tranh. Cần đối chiếu:

- Tốc độ ứng dụng nhận event và tốc độ gọi `send()`.
- Số record đang in-flight và độ dài queue ứng dụng.
- Producer buffer availability và thời gian chờ buffer.
- Produce request latency, retry và lỗi.
- Broker request queue, CPU, disk latency và network throughput.
- Consumer lag nếu consumer xử lý chậm làm downstream pipeline bị nghẽn.

Nếu buffer giảm trong khi broker request latency tăng, có thể broker/network đang làm chậm tốc độ giải phóng buffer. Nếu buffer giảm ngay sau burst nhưng phục hồi nhanh, có thể buffer chỉ đang hấp thụ burst bình thường.

### 9.3. Alert theo xu hướng

Không nên chỉ cảnh báo khi buffer bằng 0. Hãy kết hợp:

- Buffer availability thấp liên tục trong một khoảng thời gian.
- `waiting-threads` lớn hơn 0 hoặc tăng nhanh.
- Buffer pool wait time tăng.
- Record queue time và produce latency vượt ngưỡng SLA.
- Ứng dụng bắt đầu từ chối event do queue/in-flight limit.

Một cảnh báo sớm cho phép giảm tốc độ đầu vào hoặc mở rộng năng lực broker trước khi producer liên tục ném timeout.

## 10. Ví dụ cấu hình và chẩn đoán

### 10.1. Cấu hình minh họa

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");

props.put("buffer.memory", 64L * 1024 * 1024); // 64 MiB
props.put("batch.size", 32 * 1024);             // 32 KiB
props.put("linger.ms", 5);
props.put("max.block.ms", 5_000);
props.put("request.timeout.ms", 30_000);
props.put("delivery.timeout.ms", 120_000);

KafkaProducer<String, String> producer = new KafkaProducer<>(props);
```

Các giá trị chỉ nhằm minh họa mối quan hệ giữa cấu hình. Trong Kafka client hiện đại, `delivery.timeout.ms` phải đáp ứng các ràng buộc liên quan đến `request.timeout.ms` và `linger.ms`; kiểm tra validation và tài liệu của phiên bản đang dùng. Không sao chép nguyên bộ giá trị này vào production mà chưa đo tải.

### 10.2. Phân biệt ba tình huống

**Tình huống A: thiếu metadata**

- `send()` chờ trước khi trả Future.
- Log có thể báo metadata request timeout hoặc broker không truy cập được.
- Tăng `buffer.memory` không giải quyết được vấn đề.
- Kiểm tra bootstrap server, DNS, listener, topic và quyền truy cập.

**Tình huống B: buffer pool cạn**

- `buffer-available-bytes` gần 0.
- `waiting-threads` hoặc buffer pool wait time tăng.
- `send()` có thể ném `TimeoutException` khi hết `max.block.ms`.
- Kiểm tra tốc độ đầu vào, batch drain, broker latency, partition count và backpressure ở ứng dụng.

**Tình huống C: record đã được gửi nhưng broker phản hồi chậm**

- `send()` đã trả Future.
- Request latency tăng hoặc producer retry.
- Kết quả cuối cùng được báo qua Future/callback khi hoàn tất hoặc hết delivery timeout.
- Kiểm tra broker, network, `request.timeout.ms` và `delivery.timeout.ms`.

Ba tình huống có thể cùng xuất hiện khi cluster quá tải, nhưng cần xác định điểm nghẽn đầu tiên trước khi thay đổi cấu hình.

## 11. Checklist thiết kế backpressure

Trước khi triển khai producer, hãy xác nhận:

- `buffer.memory` phù hợp với ngân sách bộ nhớ toàn process và container.
- `batch.size` và `linger.ms` phù hợp với throughput, latency và số partition.
- `max.block.ms` phù hợp với thời gian chờ metadata/buffer mà ứng dụng chấp nhận.
- `request.timeout.ms` và `delivery.timeout.ms` được thiết kế theo SLA và khả năng retry.
- Ứng dụng bắt lỗi đồng bộ từ `send()` và lỗi bất đồng bộ qua callback/Future.
- Queue ứng dụng và số record in-flight có giới hạn.
- Khi queue đầy, ứng dụng có chính sách rõ ràng: block có thời hạn, trả lỗi, giảm tốc độ hoặc lưu bền vững.
- Callback ngắn và không làm nghẽn sender thread.
- Metric buffer availability, waiting threads, queue time và request latency được theo dõi.
- Alert phát hiện buffer pressure trước khi liên tục hết `max.block.ms`.
- Tăng buffer chỉ để hấp thụ burst có giới hạn, không dùng để che giấu throughput thiếu hụt kéo dài.

## 12. Câu hỏi tự kiểm tra

1. `buffer.memory` được dùng cho phần nào trong Kafka producer?
2. Vì sao `buffer.memory` không phải giới hạn tổng heap của process?
3. `batch.size` khác `buffer.memory` ở phạm vi áp dụng nào?
4. `linger.ms` giúp tăng batch size như thế nào và có đánh đổi gì?
5. Những tình huống nào khiến `send()` phải chờ trước khi trả về?
6. `max.block.ms` giới hạn việc chờ nào và không giới hạn việc gì?
7. `max.block.ms` khác `request.timeout.ms` và `delivery.timeout.ms` ra sao?
8. Vì sao tăng `buffer.memory` không giải quyết được tình trạng `R_in` cao hơn `R_out` liên tục?
9. Làm thế nào dùng semaphore hoặc bounded queue để giới hạn số record đang chờ?
10. Những metric nào giúp phân biệt thiếu buffer với broker/network phản hồi chậm?
11. Vì sao queue không giới hạn phía trước producer chỉ chuyển vị trí xảy ra quá tải?
12. Khi `send()` ném `TimeoutException` đồng bộ, callback có nhận lỗi đó không? Ứng dụng cần làm gì?

## Kết luận

`buffer.memory` cung cấp vùng đệm hữu hạn cho record đang chờ gửi; `batch.size` và `linger.ms` quyết định cách gom batch; `max.block.ms` giới hạn thời gian `send()` chờ metadata hoặc buffer. Nếu ứng dụng tạo record nhanh hơn producer có thể gửi trong thời gian dài, buffer sẽ đầy và backpressure cần truyền ngược lên nguồn tạo event. Kết hợp giới hạn in-flight, queue có giới hạn, xử lý timeout rõ ràng và metric producer/broker giúp hệ thống giữ được độ trễ cùng mức sử dụng bộ nhớ trong giới hạn có thể vận hành.
