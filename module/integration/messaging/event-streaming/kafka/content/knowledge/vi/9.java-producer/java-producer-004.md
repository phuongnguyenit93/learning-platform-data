# send bất đồng bộ, Future và callback

## Mục tiêu bài học

Kafka Java Producer được thiết kế để gửi record bất đồng bộ. Khi gọi `send()`, ứng dụng đưa record vào luồng xử lý của producer; một thread nền gom batch, gửi request đến broker và nhận kết quả. Ứng dụng có thể lấy kết quả bằng `Future<RecordMetadata>` hoặc đăng ký callback để được thông báo khi gửi thành công hay thất bại.

Sau bài học, bạn có thể:

- Mô tả các bước chính xảy ra sau lời gọi `KafkaProducer.send()`.
- Phân biệt thời điểm `send()` trả về với thời điểm broker xác nhận record.
- Dùng `Future<RecordMetadata>` khi cần chờ kết quả và dùng callback để xử lý kết quả bất đồng bộ.
- Phân biệt lỗi xảy ra ngay trong `send()` với lỗi được báo sau đó qua Future/callback.
- Đọc `RecordMetadata` để lấy topic, partition, offset và timestamp.
- Dùng `flush()` và `close()` đúng cách, tránh làm mất lợi ích batching.
- Thiết kế callback ngắn gọn, xử lý backpressure và retry phù hợp.

## 1. Gửi bất đồng bộ nghĩa là gì?

### 1.1. `send()` không đợi broker xác nhận xong

Với Kafka Java client, lời gọi:

```java
Future<RecordMetadata> future = producer.send(record);
```

thường trả về ngay sau khi record đã được chấp nhận vào luồng gửi nội bộ của producer. Broker có thể chưa nhận request, chưa append record và chưa gửi response tại thời điểm `send()` trả về.

Producer sử dụng các thành phần nội bộ như:

- **Serializer:** chuyển key và value thành bytes.
- **Partitioner:** chọn partition nếu ứng dụng không chỉ định partition trực tiếp.
- **Record accumulator:** gom record thành batch theo partition.
- **Sender thread:** lấy batch đã sẵn sàng, gửi Produce request và xử lý response từ broker.
- **Callback/Future:** chuyển kết quả gửi về cho ứng dụng.

Luồng khái quát:

```text
Application thread
       |
       | send(record)
       v
Serialize key/value
       |
       v
Choose partition
       |
       v
Record accumulator (batch by partition)
       |
       | return Future
       v
Application continues

Background Sender thread
       |
       v
Send Produce request to broker
       |
       v
Broker append and respond
       |
       v
Complete Future / invoke callback
```

Do đó, `send()` trả về không có nghĩa record đã được ghi thành công. Kết quả cuối cùng cần được kiểm tra qua Future hoặc callback nếu ứng dụng cần xác nhận.

### 1.2. Bất đồng bộ không có nghĩa lời gọi `send()` tuyệt đối không chờ

`send()` có thể phải chờ trong một số tình huống trước khi trả về, ví dụ:

- Producer chưa có metadata cho topic/partition và phải chờ metadata được lấy.
- Record accumulator không còn đủ buffer memory và phải chờ buffer được giải phóng.
- Serializer hoặc interceptor thực hiện công việc tốn thời gian ngay trên thread gọi `send()`.

Thời gian chờ metadata hoặc buffer được giới hạn bởi `max.block.ms`. Nếu vượt giới hạn, `send()` có thể ném exception ngay tại chỗ. Vì vậy, không nên gọi `send()` trên một thread cần phản hồi tức thì nếu serializer/interceptor hoặc tình trạng buffer có thể gây chờ lâu.

`max.block.ms` không phải thời gian tối đa broker được phép xử lý một record sau khi request đã được gửi. Thời gian gửi và retry sau khi gửi được điều khiển bởi các timeout khác, trong đó có `delivery.timeout.ms` và `request.timeout.ms`.

## 2. Tạo Producer và gửi record đầu tiên

Ví dụ sau dùng String serializer và gửi một event vào topic `orders`:

```java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");

try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
    ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders",
        "ORD-101",
        "{\"eventType\":\"OrderCreated\",\"orderId\":\"ORD-101\"}"
    );

    producer.send(record);
}
```

Ví dụ tối giản này không đọc kết quả Future. Khi `close()` chạy, producer sẽ cố hoàn tất các record đã được gửi trước đó theo hành vi đóng producer. Trong ứng dụng thật, nếu cần quan sát kết quả từng record, hãy dùng Future hoặc callback.

`KafkaProducer` thread-safe và có thể được chia sẻ giữa nhiều thread ứng dụng. Thông thường nên tạo một producer dùng chung trong phạm vi service thay vì tạo producer mới cho từng record; mỗi producer có buffer, sender thread và kết nối riêng, nên tạo quá nhiều producer sẽ tăng chi phí tài nguyên.

## 3. Nhận kết quả bằng `Future<RecordMetadata>`

### 3.1. `Future.get()` chờ kết quả

`send()` trả về `Future<RecordMetadata>`. Khi cần xác nhận kết quả, ứng dụng có thể gọi `get()`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

import org.apache.kafka.clients.producer.RecordMetadata;

Future<RecordMetadata> future = producer.send(record);

try {
    RecordMetadata metadata = future.get();
    System.out.printf(
        "topic=%s partition=%d offset=%d%n",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting for Kafka send was interrupted", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Kafka send failed", ex.getCause());
}
```

`get()` là thao tác blocking: thread gọi sẽ dừng chờ cho đến khi producer hoàn tất việc gửi hoặc báo lỗi. Nếu gọi `get()` ngay sau mỗi `send()`, ứng dụng gần như biến luồng gửi thành tuần tự và giảm khả năng gom batch.

### 3.2. Dùng timeout khi chờ

`get()` không tham số có thể chờ lâu cho đến khi producer hoàn tất hoặc thất bại. Có thể dùng `get(timeout, unit)` để giới hạn thời gian thread ứng dụng chờ:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

try {
    RecordMetadata metadata = future.get(2, TimeUnit.SECONDS);
    System.out.println("offset=" + metadata.offset());
} catch (TimeoutException ex) {
    // Chưa có kết quả trong 2 giây; Future có thể vẫn đang được producer xử lý.
    System.err.println("Send result is not available yet");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ExecutionException ex) {
    System.err.println("Send failed: " + ex.getCause());
}
```

`TimeoutException` từ `Future.get(timeout, ...)` chỉ có nghĩa thread ứng dụng đã hết thời gian chờ. Nó không tự hủy request, không chứng minh broker đã từ chối record và cũng không chứng minh record chưa được ghi. Nếu gửi lại ngay mà không có idempotency hoặc event ID/deduplication, ứng dụng có thể tạo duplicate.

### 3.3. Khi nào nên dùng Future?

Future phù hợp khi:

- Một tác vụ nền có thể chờ kết quả mà không chặn request thread quan trọng.
- Cần ghép kết quả gửi với một bước xử lý tiếp theo.
- Cần chờ một nhóm gửi hoàn tất ở cuối một tác vụ batch.
- Cần xử lý lỗi theo kiểu exception trong một luồng điều khiển tuần tự.

Future không phù hợp nếu ứng dụng gọi `get()` ngay sau mỗi `send()` trong một vòng lặp throughput cao. Trong trường hợp đó, callback hoặc tập hợp Future rồi chờ sau khi đã gửi một nhóm record có thể hiệu quả hơn.

## 4. Nhận kết quả bằng callback

### 4.1. Callback được gọi khi gửi hoàn tất

Callback cho phép ứng dụng đăng ký một hành động khi producer nhận được kết quả gửi:

```java
import org.apache.kafka.clients.producer.Callback;
import org.apache.kafka.clients.producer.RecordMetadata;

producer.send(record, new Callback() {
    @Override
    public void onCompletion(RecordMetadata metadata, Exception exception) {
        if (exception != null) {
            System.err.println("Send failed: " + exception.getMessage());
            return;
        }

        System.out.printf(
            "Sent to topic=%s partition=%d offset=%d%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }
});
```

Callback có hai đầu vào:

- `metadata`: thông tin record sau khi gửi thành công; thường là `null` khi có lỗi.
- `exception`: exception nếu gửi thất bại; `null` nếu thành công.

Không nên giả định callback luôn có metadata hoặc luôn được gọi ngay sau khi `send()` trả về. Nó chỉ được gọi khi quá trình gửi tương ứng hoàn tất theo cơ chế producer.

### 4.2. Lambda callback

Vì `Callback` là functional interface, có thể viết ngắn hơn:

```java
producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        handleSendFailure(record, exception);
    } else {
        recordSendSuccess(metadata);
    }
});
```

Các hàm `handleSendFailure` và `recordSendSuccess` là logic do ứng dụng định nghĩa. Nên giữ chúng nhanh, không thực hiện thao tác I/O chậm hoặc chờ một Future khác bên trong callback.

### 4.3. Callback chạy trên thread nào?

Callback thường được gọi trên thread I/O của producer khi kết quả request được xử lý. Vì vậy, callback là một phần của đường xử lý nền của producer. Nếu callback chạy lâu, nó có thể làm chậm việc xử lý response và các callback khác.

Không nên thực hiện trực tiếp trong callback:

- Gọi HTTP service chậm hoặc truy vấn database đồng bộ.
- Gọi `future.get()` để chờ một lần gửi khác.
- Gọi `flush()` hoặc `close()` trên chính producer.
- Chạy xử lý CPU nặng hoặc chờ lock có thể bị giữ bởi thread khác.

Nếu cần xử lý nặng, hãy chuyển công việc sang executor riêng có giới hạn queue. Cần thiết kế backpressure cho executor đó; queue không giới hạn có thể làm ứng dụng dùng hết heap khi tốc độ callback cao hơn tốc độ xử lý.

### 4.4. Thứ tự callback

Producer bảo đảm callback của các record gửi đến cùng một partition được gọi theo thứ tự tương ứng với thứ tự gửi. Không có bảo đảm thứ tự callback chung giữa các partition khác nhau vì chúng có thể được xử lý song song.

Nếu callback đẩy công việc sang một thread pool, thứ tự hoàn tất của các tác vụ trong thread pool vẫn có thể khác thứ tự callback ban đầu. Nếu nghiệp vụ cần thứ tự theo key hoặc partition, executor phải giữ tuần tự cho phạm vi đó, hoặc ứng dụng cần cơ chế sequence/version để kiểm tra.

## 5. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Một lỗi gửi có thể xuất hiện ở hai thời điểm.

### 5.1. Lỗi xảy ra ngay trong `send()`

Một số lỗi có thể được ném ngay từ lời gọi `send()`, trước khi Future được trả về. Ví dụ:

- Serializer không serialize được key hoặc value.
- Interceptor ném exception.
- Không lấy được metadata trong giới hạn `max.block.ms`.
- Buffer memory không được giải phóng kịp trong giới hạn `max.block.ms`.
- Tham số hoặc trạng thái producer không hợp lệ.

Vì vậy, nếu ứng dụng cần bắt mọi lỗi, cần đặt `try/catch` quanh cả lời gọi `send()` và phần xử lý Future/callback.

```java
try {
    producer.send(record, (metadata, exception) -> {
        if (exception != null) {
            handleSendFailure(record, exception);
        } else {
            recordSendSuccess(metadata);
        }
    });
} catch (RuntimeException ex) {
    // Lỗi phát sinh đồng bộ khi chuẩn bị/đưa record vào producer.
    handleImmediateSendFailure(record, ex);
}
```

Tên và loại exception cụ thể phụ thuộc nguyên nhân và phiên bản client. Không nên chỉ bắt một lớp exception hẹp nếu ứng dụng cần xử lý mọi lỗi runtime có thể phát sinh trong giai đoạn gọi `send()`.

### 5.2. Lỗi được báo sau khi request được gửi

Các lỗi như timeout, lỗi broker, lỗi authorization hoặc lỗi mạng có thể được phát hiện sau khi record đã được đưa vào producer. Producer có thể tự retry các lỗi có thể retry theo cấu hình. Nếu cuối cùng không gửi thành công, lỗi được trả qua callback hoặc Future.

Với Future, lỗi gửi thường được bọc trong `ExecutionException`; nguyên nhân thật nằm ở `getCause()`. Với callback, exception được truyền trực tiếp vào tham số `exception`.

### 5.3. Phân loại lỗi trước khi retry ở tầng ứng dụng

Producer đã có cơ chế retry nội bộ. Nếu callback nhận lỗi cuối cùng và ứng dụng tự gửi lại, cần xác định lỗi có thể khắc phục hay không:

| Nhóm lỗi | Hướng xử lý |
|---|---|
| Lỗi tạm thời do mạng hoặc broker unavailable | Có thể retry với backoff nếu còn trong ngân sách thời gian |
| Timeout với kết quả không chắc chắn | Cần idempotency/event ID để xử lý khả năng record đã được ghi |
| Lỗi serialization | Sửa dữ liệu hoặc schema; retry cùng payload thường không giải quyết được |
| Authentication/authorization | Sửa credential hoặc ACL; không retry liên tục như lỗi tạm thời |
| Topic/partition không hợp lệ | Kiểm tra provisioning và metadata; xử lý cấu hình trước khi gửi lại |
| Producer buffer đầy hoặc `max.block.ms` hết hạn | Giảm tốc độ gửi, tăng năng lực xử lý hoặc điều chỉnh buffer sau khi đo |

Không nên viết vòng lặp retry vô hạn trong callback. Điều đó có thể tạo retry storm, làm broker quá tải và khiến ứng dụng không còn kiểm soát được thời gian giao hàng.

## 6. Đọc `RecordMetadata`

Khi gửi thành công, `RecordMetadata` cung cấp vị trí của record trong Kafka:

| Phương thức | Ý nghĩa |
|---|---|
| `topic()` | Tên topic nhận record |
| `partition()` | Partition được chọn |
| `offset()` | Offset của record trong partition |
| `timestamp()` | Timestamp của record theo chính sách timestamp |
| `serializedKeySize()` | Kích thước key sau serialize, nếu có |
| `serializedValueSize()` | Kích thước value sau serialize, nếu có |

Ví dụ:

```java
producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        log.error("Kafka publish failed", exception);
        return;
    }

    log.info(
        "Kafka publish succeeded: topic={}, partition={}, offset={}, timestamp={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset(),
        metadata.timestamp()
    );
});
```

Offset là vị trí record trong một partition, không phải event ID toàn cục. Nếu cần truy vết một sự kiện xuyên qua nhiều service hoặc topic, hãy giữ một `eventId` do ứng dụng tạo và log cùng metadata Kafka.

## 7. Gửi nhiều record mà không chờ từng record

### 7.1. Gửi một batch bằng nhiều lời gọi `send()`

Một cách đơn giản để tận dụng bất đồng bộ là gửi nhiều record rồi chờ ở cuối:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Future;

List<Future<RecordMetadata>> futures = new ArrayList<>();

for (OrderEvent event : events) {
    ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders",
        event.orderId(),
        event.toJson()
    );
    futures.add(producer.send(record));
}

for (Future<RecordMetadata> future : futures) {
    RecordMetadata metadata = future.get();
    System.out.printf(
        "topic=%s partition=%d offset=%d%n",
        metadata.topic(), metadata.partition(), metadata.offset()
    );
}
```

Các record được đưa vào producer trước khi ứng dụng chờ kết quả. Producer có cơ hội gom chúng thành batch theo partition. Ví dụ trên phù hợp với batch có kích thước vừa phải; nếu danh sách quá lớn, lưu tất cả Future có thể tốn bộ nhớ và tạo áp lực buffer.

### 7.2. Giới hạn số record đang chờ

Với luồng dữ liệu liên tục, hãy dùng cửa sổ gửi có giới hạn thay vì tích lũy Future vô hạn. Ví dụ, chỉ giữ tối đa một số lượng record đang chờ xác nhận, sau đó xử lý kết quả và tiếp tục gửi.

Các cách kiểm soát áp lực:

- Giới hạn số request hoặc record in-flight ở tầng ứng dụng.
- Dùng queue có giới hạn giữa business thread và producer worker.
- Theo dõi thời gian hoàn tất callback, buffer availability và số record đang chờ.
- Giảm tốc độ nhận đầu vào khi producer hoặc broker không theo kịp.
- Đặt timeout và chính sách từ chối/đưa vào durable queue khi vượt giới hạn.

Nếu queue đầy, ứng dụng cần quyết định rõ: chặn producer đầu vào, trả lỗi cho caller, lưu vào outbox hoặc bỏ sự kiện theo chính sách nghiệp vụ. Không nên âm thầm loại bỏ record quan trọng.

## 8. `flush()` và `close()`

### 8.1. `flush()`

`flush()` yêu cầu producer gửi các record đang được buffer và chờ các request đã gửi hoàn tất trước khi trả về. Nó hữu ích ở ranh giới công việc cần chắc chắn các record trước đó đã hoàn tất, ví dụ cuối một batch nhỏ hoặc trước khi chuyển sang giai đoạn shutdown.

Không gọi `flush()` sau từng record trong luồng throughput cao. Làm vậy giảm cơ hội batching, tăng số request nhỏ và làm tăng latency.

Ví dụ:

```java
for (ProducerRecord<String, String> record : batch) {
    producer.send(record, callback);
}

producer.flush();
```

`flush()` không biến một loạt send thành một transaction. Nó chỉ chờ các record đã gửi hoàn tất theo cơ chế producer; nếu cần atomicity giữa nhiều record, phải dùng Kafka transaction.

### 8.2. `close()`

`close()` đóng producer và giải phóng tài nguyên. Khi đóng bình thường, producer chờ các request đã được gửi hoàn tất trong giới hạn thời gian đóng theo API/cấu hình sử dụng. Nên đóng producer khi ứng dụng shutdown, không đóng sau mỗi record.

Dùng try-with-resources giúp bảo đảm `close()` được gọi:

```java
try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
    producer.send(record, callback);
    // Thực hiện các công việc khác...
}
```

Trong ứng dụng server lâu dài, producer thường được quản lý bởi lifecycle của framework hoặc bean singleton. Khi shutdown, cần ngừng nhận công việc mới, chờ các tác vụ đang gửi hoàn tất trong ngân sách thời gian rồi đóng producer.

## 9. Batching, retry và các cấu hình liên quan

Các tham số sau ảnh hưởng đến thời gian gửi và cách producer gom record:

| Cấu hình | Vai trò | Tác động cần hiểu |
|---|---|---|
| `linger.ms` | Thời gian producer chờ thêm record để gom batch | Tăng có thể cải thiện batch/compression nhưng tăng latency chờ |
| `batch.size` | Kích thước batch mục tiêu cho mỗi partition | Batch lớn cần buffer phù hợp và workload đủ dữ liệu |
| `buffer.memory` | Tổng bộ nhớ buffer dành cho record đang chờ gửi | Hết buffer có thể làm `send()` chờ đến `max.block.ms` |
| `max.block.ms` | Giới hạn thời gian chờ metadata/buffer trong các thao tác như `send()` | Không phải delivery timeout của broker |
| `delivery.timeout.ms` | Tổng thời gian tối đa producer cố gắng giao record, gồm retry và chờ response theo quy tắc client | Hết hạn thì Future/callback báo lỗi |
| `request.timeout.ms` | Thời gian chờ response cho một request | Request có thể retry nếu lỗi được xem là retriable và còn ngân sách delivery |
| `retries` | Số lần retry theo cấu hình client cũ/hiện hành tùy phiên bản | Cần đọc cùng `delivery.timeout.ms` và idempotence |
| `enable.idempotence` | Bật producer idempotence | Giảm duplicate do retry và hỗ trợ ordering theo các điều kiện Kafka |
| `compression.type` | Kiểu nén record batch | Có thể giảm network/disk nhưng tiêu tốn CPU |

Giá trị mặc định và quan hệ giữa các cấu hình thay đổi theo phiên bản Kafka client. Hãy xem tài liệu đúng phiên bản thay vì sao chép một bộ cấu hình cũ sang mọi ứng dụng.

### 9.1. Idempotence và retry

Producer idempotent dùng producer ID và sequence number để broker nhận diện retry của cùng một batch, giúp tránh ghi trùng do retry trong phạm vi đảm bảo của Kafka. Khi cần độ tin cậy cao, thường nên bật `enable.idempotence=true` và để client quản lý các cấu hình tương thích.

Idempotence không loại bỏ duplicate do ứng dụng gọi `send()` hai lần cho cùng một event như hai lần publish độc lập. Nó cũng không tự bảo vệ side effect ở database hoặc HTTP service bên ngoài Kafka. Event ID và logic idempotent ở consumer vẫn cần thiết khi nghiệp vụ đòi hỏi xử lý một lần theo hiệu quả cuối cùng.

### 9.2. Batching và callback

Batching được hình thành theo partition. Nếu ứng dụng gửi nhiều record có key phân tán trên nhiều partition, mỗi partition có batch riêng. Gọi `flush()` quá thường xuyên hoặc chờ Future sau mỗi send có thể khiến batch nhỏ hơn và làm giảm throughput.

Callback không làm producer tự động gửi một batch duy nhất cho tất cả record. Nó chỉ nhận kết quả của từng record; việc gom batch vẫn do accumulator và sender quản lý.

## 10. Ví dụ hoàn chỉnh: gửi bất đồng bộ với callback và xử lý shutdown

Ví dụ sau minh họa cấu hình producer, gửi nhiều event, ghi metadata khi thành công và ghi nhận lỗi khi thất bại:

```java
import java.util.Properties;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public class OrderPublisher {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put("bootstrap.servers", "localhost:9092");
        props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
        props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");
        props.put("acks", "all");
        props.put("enable.idempotence", "true");

        AtomicLong succeeded = new AtomicLong();
        AtomicLong failed = new AtomicLong();

        try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
            for (int i = 1; i <= 100; i++) {
                String orderId = "ORD-" + i;
                String payload = "{\"eventType\":\"OrderCreated\",\"orderId\":\""
                    + orderId + "\"}";

                ProducerRecord<String, String> record = new ProducerRecord<>(
                    "orders", orderId, payload
                );

                try {
                    producer.send(record, (metadata, exception) -> {
                        if (exception != null) {
                            failed.incrementAndGet();
                            System.err.printf(
                                "Failed to publish order=%s: %s%n",
                                orderId,
                                exception.getMessage()
                            );
                            return;
                        }

                        succeeded.incrementAndGet();
                        System.out.printf(
                            "Published order=%s topic=%s partition=%d offset=%d%n",
                            orderId,
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset()
                        );
                    });
                } catch (RuntimeException ex) {
                    failed.incrementAndGet();
                    System.err.printf(
                        "Could not enqueue order=%s: %s%n",
                        orderId,
                        ex.getMessage()
                    );
                }
            }

            producer.flush();
        }

        System.out.printf(
            "Publish completed: success=%d failed=%d%n",
            succeeded.get(), failed.get()
        );
    }
}
```

Ví dụ dùng callback nhanh và `flush()` ở cuối để chờ các record đã gửi hoàn tất trước khi đọc bộ đếm. Trong production, không nên chỉ in lỗi rồi bỏ qua nếu event là dữ liệu quan trọng. Hãy ghi nhận lỗi vào metric/log có correlation ID và đưa event vào quy trình phục hồi bền vững như outbox hoặc retry queue khi phù hợp.

Lưu ý: callback có thể cập nhật bộ đếm từ nhiều luồng thực thi; ví dụ dùng `AtomicLong` để cập nhật an toàn. Callback chỉ in thông tin và tăng bộ đếm, không gọi I/O nghiệp vụ chậm.

## 11. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách làm phù hợp |
|---|---|---|
| Gọi `future.get()` ngay sau mỗi `send()` | Chặn thread và giảm batching | Gửi một nhóm rồi chờ kết quả, hoặc dùng callback |
| Không kiểm tra Future/callback | Lỗi gửi có thể bị bỏ qua | Xử lý kết quả và ghi nhận lỗi |
| Callback gọi HTTP hoặc database đồng bộ | Chặn producer I/O thread | Chuyển tác vụ sang executor có giới hạn |
| Gọi `flush()` sau mỗi record | Làm batch nhỏ và tăng request overhead | Flush ở ranh giới batch hoặc shutdown |
| Tạo producer mới cho từng message | Tốn thread, buffer và connection | Dùng producer sống lâu, chia sẻ an toàn giữa thread |
| Retry vô hạn trong callback | Có thể tạo retry storm và duplicate | Retry có giới hạn, backoff và idempotency |
| Xem `TimeoutException` của Future là gửi thất bại chắc chắn | Kết quả có thể chưa rõ; broker có thể đã ghi | Dùng event ID/dedup và kiểm tra trạng thái theo nghiệp vụ |
| Không đóng producer khi shutdown | Có thể bỏ dở công việc và giữ tài nguyên | Ngừng nhận việc, flush/close theo lifecycle |
| Giả định callback giữa mọi partition có thứ tự | Các partition được xử lý song song | Chỉ dựa vào ordering trong phạm vi partition hoặc tự điều phối |

## 12. Checklist triển khai producer bất đồng bộ

Trước khi đưa producer vào production, hãy xác nhận:

- Producer được tạo một lần theo lifecycle service và được đóng khi shutdown.
- Key/value serializer tương thích với event schema.
- Topic metadata có thể truy cập và ACL cho phép ghi.
- Ứng dụng hiểu `send()` có thể chờ metadata/buffer trong giới hạn `max.block.ms`.
- Future hoặc callback được dùng để quan sát kết quả gửi.
- Cả lỗi đồng bộ và lỗi bất đồng bộ đều được xử lý.
- Callback ngắn, không chờ Future khác và không chạy I/O chậm.
- Queue/executor và số record in-flight có giới hạn.
- `delivery.timeout.ms`, `request.timeout.ms`, retry và idempotence phù hợp với SLA.
- `flush()` chỉ được gọi ở ranh giới cần thiết, không gọi từng record.
- Event ID và consumer idempotency được thiết kế nếu có khả năng retry/replay.
- Metric có số record thành công/thất bại, send latency, callback latency và buffer pressure.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `send()` trả về Future không có nghĩa broker đã xác nhận record?
2. Những tình huống nào khiến `send()` có thể chờ trước khi trả về?
3. `Future.get()` khác callback ở cách sử dụng thread như thế nào?
4. `TimeoutException` khi gọi `get(timeout, unit)` có chứng minh record chưa được ghi không?
5. Callback nhận `metadata` và `exception` trong những trường hợp nào?
6. Vì sao callback cần chạy nhanh và tránh gọi I/O đồng bộ?
7. Lỗi nào có thể xuất hiện ngay trong `send()`, lỗi nào được báo qua Future/callback?
8. `RecordMetadata.offset()` dùng để làm gì và vì sao không thay thế event ID?
9. Vì sao gọi `flush()` sau mỗi record làm giảm throughput?
10. `max.block.ms` khác `delivery.timeout.ms` như thế nào?
11. Producer idempotence giải quyết loại duplicate nào và giới hạn của nó là gì?
12. Nếu callback chuyển công việc sang thread pool, cần làm gì để giữ ordering theo partition hoặc key?

## Kết luận

`KafkaProducer.send()` đưa record vào luồng gửi bất đồng bộ và trả về `Future<RecordMetadata>`. Ứng dụng có thể chờ Future khi cần kết quả hoặc dùng callback để xử lý kết quả mà không chặn luồng nghiệp vụ. Cần nhớ rằng `send()` vẫn có thể chờ metadata/buffer, callback chạy trên luồng I/O của producer và `flush()` nên được dùng ở ranh giới công việc thay vì sau từng record. Khi kết hợp xử lý lỗi đồng bộ/bất đồng bộ, backpressure, batching và idempotence, producer có thể đạt throughput tốt mà vẫn quan sát được kết quả gửi.
