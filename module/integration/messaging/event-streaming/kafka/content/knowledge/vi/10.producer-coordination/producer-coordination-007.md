# `request.timeout.ms` và `delivery.timeout.ms`

## Mục tiêu

Kafka producer có nhiều lớp timeout vì một record có thể phải chờ metadata, chờ batch, gửi request tới broker, chờ acknowledgement và retry khi gặp lỗi tạm thời. Hai cấu hình thường bị nhầm là `request.timeout.ms` và `delivery.timeout.ms`.

`request.timeout.ms` giới hạn thời gian client chờ phản hồi cho một request tới broker. `delivery.timeout.ms` giới hạn tổng thời gian producer được phép hoàn tất hoặc báo lỗi cho một record sau khi `send()` trả về. Hiểu đúng phạm vi của từng timeout giúp tránh retry quá sớm, tránh chờ quá lâu và phân biệt lỗi mạng với việc record đã hết hạn gửi.

Sau bài học này, bạn có thể:

- Phân biệt timeout của một request với deadline giao một record.
- Giải thích quan hệ giữa `request.timeout.ms`, `delivery.timeout.ms` và `linger.ms`.
- Phân biệt hai cấu hình trên với `max.block.ms`, `Future.get(timeout)` và timeout của transaction.
- Hiểu cách retry bị giới hạn bởi delivery deadline.
- Nhận biết kết quả không xác định khi broker đã append record nhưng acknowledgement bị mất.
- Cấu hình timeout trong Java Kafka Producer và Spring Kafka.
- Chẩn đoán lỗi timeout bằng log, callback, producer metrics và thực nghiệm.

## 1. Một record đi qua nhiều khoảng chờ

Khi ứng dụng gọi `producer.send(record)`, record chưa nhất thiết được gửi ngay lập tức. Producer có thể cần metadata để tìm partition leader, đợi thêm record để gom batch, sau đó gửi Produce request và chờ broker phản hồi. Nếu gặp lỗi tạm thời, producer có thể thử lại request trong giới hạn deadline.

```mermaid
flowchart TD
    A[Ứng dụng gọi send(record)] --> B[Chờ metadata / cấp phát buffer]
    B --> C[Record được enqueue]
    C --> D[Chờ batch: linger.ms]
    D --> E[Gửi request tới broker]
    E --> F{Có response trước request timeout?}
    F -->|Có, thành công| G[Hoàn tất record thành công]
    F -->|Có, lỗi| H{Lỗi có thể retry?}
    F -->|Không| H
    H -->|Có| I{Còn delivery time?}
    I -->|Còn| E
    I -->|Hết| J[Hoàn tất record với lỗi timeout]
    H -->|Không| K[Hoàn tất record với lỗi cuối cùng]
```

Hai timeout này bảo vệ hai phạm vi khác nhau:

- `request.timeout.ms`: một request đã gửi tới broker có bao lâu để nhận response.
- `delivery.timeout.ms`: một record đã được `send()` chấp nhận có bao lâu để producer báo thành công hoặc thất bại.

Một record có thể trải qua nhiều request/retry trong một delivery deadline. Vì vậy `delivery.timeout.ms` thường lớn hơn `request.timeout.ms`.

## 2. `request.timeout.ms`: thời gian chờ một request

`request.timeout.ms` là thời gian tối đa Kafka client chờ response cho một request tới broker. Nếu response không tới trước timeout, client sẽ retry khi request có thể retry và còn thời gian cho phép; nếu không thể retry hoặc đã hết điều kiện retry, request sẽ thất bại.

Ví dụ cấu hình:

```properties
request.timeout.ms=30000
```

Với giá trị 30.000 ms, producer chờ tối đa khoảng 30 giây cho response của request đó. Đây không phải thời gian tối đa từ lúc gọi `send()` đến lúc record hoàn tất, vì record còn có thể chờ batch trước khi gửi và có thể cần nhiều lần request.

### 2.1. Điều gì có thể khiến request không nhận response?

- Broker xử lý chậm do CPU, disk I/O, request queue hoặc replication bị chậm.
- Network bị nghẽn, mất packet hoặc kết nối bị gián đoạn.
- Broker restart, leader thay đổi hoặc partition tạm thời không có leader.
- Broker đã xử lý request nhưng response bị mất trên đường về client.
- Producer kết nối tới broker không còn khả dụng hoặc đang chuyển đổi leader.

Khi timeout, producer không thể luôn biết broker chưa xử lý request. Có trường hợp broker đã append record nhưng acknowledgement không tới client. Vì vậy timeout của request không đồng nghĩa chắc chắn record chưa được ghi.

### 2.2. Quan hệ với `replica.lag.time.max.ms`

Tài liệu Kafka khuyến nghị `request.timeout.ms` lớn hơn `replica.lag.time.max.ms` của broker để giảm khả năng producer retry không cần thiết khi replication đang chậm. Nếu request timeout quá ngắn so với thời gian broker cần để xử lý và xác nhận request, client có thể retry trong khi request cũ đã được xử lý.

Hãy kiểm tra cấu hình broker và điều kiện network thực tế trước khi giảm request timeout. Không dùng giá trị cực nhỏ chỉ để làm lỗi xuất hiện nhanh trong production.

## 3. `delivery.timeout.ms`: deadline của một record

`delivery.timeout.ms` là giới hạn trên của thời gian producer báo thành công hoặc thất bại sau khi lời gọi `send()` trả về. Deadline này bao gồm:

- Thời gian record chờ trong accumulator/batch trước khi gửi.
- Thời gian chờ broker acknowledgement nếu cấu hình `acks` yêu cầu.
- Thời gian dành cho các lần retry khi gặp lỗi có thể retry.

Producer có thể báo lỗi sớm hơn deadline nếu gặp lỗi không thể retry, hết số lần retry được cấu hình hoặc batch chứa record đã chạm deadline hết hạn sớm hơn.

Ví dụ:

```properties
delivery.timeout.ms=120000
```

Producer có tối đa khoảng 120 giây kể từ khi `send()` trả về để hoàn tất record. Nếu record đã chờ 5 ms để gom batch, phần thời gian còn lại cho các request và retry sẽ ít hơn 120 giây. Nếu broker trả lỗi không thể retry ở giây thứ hai, producer không cần chờ đủ 120 giây mới báo lỗi.

### 3.1. Vì sao delivery timeout không phải timeout của một lần request?

Giả sử `request.timeout.ms=10.000` và `delivery.timeout.ms=45.000`. Một request có thể chờ response tối đa khoảng 10 giây. Nếu request thất bại theo cách có thể retry, producer có thể gửi lại request trong phần thời gian delivery còn lại. Producer báo kết quả cuối cùng khi:

- Có acknowledgement thành công.
- Gặp lỗi không thể retry.
- Retry bị giới hạn và không còn lần thử.
- Deadline giao record hết hạn.

Vì thế, một record có thể tồn tại qua nhiều request timeout trước khi delivery timeout kết thúc. Các lần retry thực tế còn phụ thuộc backoff, kết nối, leader metadata, trạng thái batch và loại lỗi.

## 4. Quan hệ giữa ba cấu hình timeout chính

Kafka yêu cầu:

\[
\texttt{delivery.timeout.ms} \geq
\texttt{request.timeout.ms} + \texttt{linger.ms}
\]

Delivery timeout nên đủ lớn để bao gồm ít nhất một khoảng chờ batch và một request timeout. Nếu đặt nhỏ hơn tổng này, producer có thể không có đủ thời gian cho một lần gửi bình thường; cấu hình có thể bị từ chối khi khởi tạo hoặc không đạt mục tiêu vận hành.

Ví dụ hợp lệ về quan hệ số học:

```properties
linger.ms=5
request.timeout.ms=30000
delivery.timeout.ms=120000
```

Với cấu hình này, delivery deadline lớn hơn `30.000 + 5` ms. Phần thời gian còn lại tạo dư địa cho retry và các khoảng chờ khác trong vòng đời gửi.

| Cấu hình | Phạm vi | Bắt đầu tính từ đâu? | Tác động khi hết hạn |
|---|---|---|---|
| `linger.ms` | Thời gian chờ thêm để gom batch | Khi batch chưa đủ điều kiện gửi | Batch được gửi khi đủ kích thước hoặc hết thời gian chờ |
| `request.timeout.ms` | Một request tới broker | Khi request đang chờ response | Request có thể retry hoặc thất bại |
| `delivery.timeout.ms` | Một record trong producer | Sau khi `send()` trả về | Producer hoàn tất future/callback với lỗi nếu record chưa được xác nhận thành công |

Lưu ý: `linger.ms` là khoảng chờ batching tối đa được cấu hình, không phải một khoản luôn cộng chính xác vào latency. Batch có thể được gửi sớm khi đầy hoặc khi điều kiện gửi khác được thỏa mãn.

## 5. Phân biệt với `max.block.ms` và timeout ở phía ứng dụng

Producer có các timeout khác nhau cho từng lớp. Không tăng một timeout để giải quyết lỗi thuộc lớp khác.

| Timeout | Phạm vi | Ý nghĩa |
|---|---|---|
| `max.block.ms` | Lời gọi API producer | Giới hạn thời gian `send()` có thể block khi chờ metadata hoặc cấp phát buffer; không phải thời gian chờ broker acknowledgement. Thời gian chạy serializer/partitioner do ứng dụng cung cấp không được tính vào giới hạn này |
| `request.timeout.ms` | Một request broker | Giới hạn thời gian client chờ response của request |
| `delivery.timeout.ms` | Một record | Giới hạn thời gian producer báo kết quả sau khi `send()` trả về |
| `Future.get(timeout)` | Luồng ứng dụng | Giới hạn thời gian thread gọi `get()` chờ future; không tự hủy record đang gửi |
| HTTP/request timeout | Caller hoặc API gateway | Giới hạn thời gian người gọi chờ response từ ứng dụng; không tự hủy Kafka produce request |
| `transaction.timeout.ms` | Một Kafka transaction | Giới hạn thời gian transaction được phép mở trước khi coordinator có thể chủ động abort theo cấu hình |

Ví dụ:

```java
Future<RecordMetadata> future = producer.send(record);
RecordMetadata metadata = future.get(5, TimeUnit.SECONDS);
```

Nếu `get(5, SECONDS)` ném `TimeoutException`, chỉ có nghĩa thread ứng dụng đã chờ 5 giây mà chưa nhận kết quả. Future/request Kafka có thể vẫn đang tiếp tục và sau đó hoàn tất. Không được coi thao tác này là lệnh hủy record hoặc kết luận chắc chắn broker chưa append record.

Tương tự, `max.block.ms` chủ yếu tác động trước khi `send()` trả về. `delivery.timeout.ms` bắt đầu tính sau khi `send()` trả về. Vì vậy thời gian toàn bộ lời gọi từ góc nhìn ứng dụng có thể gồm thời gian block trong `send()` cộng với thời gian giao record.

## 6. Retry và kết quả không xác định

Producer tự retry một số lỗi tạm thời. Số lần retry không phải cách tốt nhất để đặt tổng thời gian chờ; `delivery.timeout.ms` là deadline tổng thể phù hợp hơn. Kafka hiện đại mặc định `retries` ở giá trị rất lớn, còn delivery deadline giới hạn thời gian producer cố gắng giao record.

### 6.1. Request timeout và retry

Khi request không nhận response đúng hạn, client có thể retry nếu lỗi thuộc nhóm có thể retry và record còn thời gian giao. Nếu response thực ra đã bị mất sau khi broker append record, lần retry tạo ra nguy cơ duplicate khi producer không có cơ chế idempotence phù hợp.

### 6.2. Idempotent producer

Với `enable.idempotence=true`, Kafka dùng producer ID, epoch và sequence number để nhận diện retry của cùng một producer session, giúp tránh duplicate do retry ở protocol. Đây là cơ chế quan trọng khi producer gặp timeout hoặc lỗi mạng.

Idempotence không đồng nghĩa mọi lần ứng dụng gọi `send()` với cùng payload đều được xem là một record. Nếu ứng dụng nhận HTTP retry rồi gọi `send()` lần nữa như một thao tác mới, đó là lần gửi mới. Đối với event nghiệp vụ quan trọng, hãy duy trì `eventId` ổn định và thiết kế consumer idempotent.

### 6.3. Delivery timeout hết hạn

Khi deadline hết hạn, producer báo lỗi cho future/callback. Tuy nhiên, trong tình huống response bị mất hoặc timeout xảy ra sau khi broker append record, ứng dụng có thể không biết chắc record đã được ghi hay chưa. Không nên lập tức tạo event mới với ID khác để gửi lại.

Quy trình xử lý phù hợp:

1. Ghi log `eventId`, topic, key, `client.id`, loại exception và thời điểm gửi.
2. Phân biệt lỗi tạm thời, lỗi cấu hình và lỗi không thể retry.
3. Nếu retry ở tầng nghiệp vụ, giữ nguyên event ID hoặc idempotency key.
4. Dùng consumer deduplication/unique constraint để ngăn tác động nghiệp vụ lặp.
5. Theo dõi kết quả gửi và đối soát khi hệ thống không thể xác định record đã được append hay chưa.

## 7. Chọn timeout theo mục tiêu vận hành

Timeout cần dựa trên latency thực tế của cluster, yêu cầu API và chính sách retry. Không nên đặt tất cả timeout bằng nhau.

### 7.1. Ứng dụng ưu tiên latency thấp

Một API đồng bộ có thể chỉ chờ vài trăm mili giây hoặc vài giây. Tuy nhiên, deadline của Kafka không nhất thiết phải bằng HTTP timeout. Ứng dụng có thể trả trạng thái `accepted` sau khi lưu outbox, rồi publish bất đồng bộ ở background. Nếu ứng dụng cần đợi Kafka acknowledgement trước khi trả HTTP response, phải thiết kế ngân sách thời gian sao cho caller timeout không xảy ra trước mọi lần thử có ích.

### 7.2. Luồng ingestion ưu tiên khả năng phục hồi

Với ingestion chạy nền, có thể cho delivery deadline dài hơn để producer có cơ hội retry qua một đợt broker restart hoặc leader election. Hãy cân nhắc kích thước queue, lượng dữ liệu chờ, memory pressure và SLA của pipeline. Deadline quá dài có thể khiến ứng dụng giữ nhiều record pending lâu và làm chậm phát hiện lỗi.

### 7.3. Producer ghi dữ liệu quan trọng

Kết hợp timeout hợp lý với:

- `acks=all` và `min.insync.replicas` phù hợp với yêu cầu durability.
- `enable.idempotence=true` để xử lý retry protocol.
- Event ID ổn định và consumer idempotency.
- Monitoring cho request latency, retry, record error và buffer exhaustion.
- Outbox/transactional design khi phải phối hợp database với Kafka.

Timeout dài hơn không tự làm dữ liệu bền hơn. Nó chỉ cho producer thêm thời gian thử gửi và chờ acknowledgement.

## 8. Ví dụ cấu hình Java Kafka Producer

Ví dụ sau dùng `Properties` để cấu hình producer:

```java
import java.util.Properties;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092,localhost:9093,localhost:9094");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());

props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);
props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 60_000);
```

Quan hệ kiểm tra:

\[
120000 \geq 30000 + 5
\]

Producer có thể chờ tối đa 60 giây trong một số bước `send()` cần metadata/buffer trước khi API trả về. Sau khi `send()` trả về, delivery deadline tối đa là 120 giây. Mỗi Produce request có thời gian chờ response tối đa 30 giây.

Đây là cấu hình minh họa, không phải khuyến nghị cho mọi cluster. Giá trị phải được kiểm chứng với broker latency, replication lag, network và SLA thực tế.

## 9. Cấu hình Spring Boot / Spring Kafka

Trong Spring Boot, các producer property có thể khai báo trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092,localhost:9093,localhost:9094
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 5
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        max.block.ms: 60000
```

Khi dùng `KafkaTemplate`, cần phân biệt timeout của Kafka producer với timeout chờ của application code:

```java
public RecordMetadata publishAndWait(String key, String value) {
    try {
        SendResult<String, String> result = kafkaTemplate
                .send("orders", key, value)
                .get(10, TimeUnit.SECONDS);
        return result.getRecordMetadata();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Thread bị interrupt", e);
    } catch (ExecutionException e) {
        throw new IllegalStateException("Kafka publish thất bại", e.getCause());
    } catch (TimeoutException e) {
        // Caller ngừng chờ; Kafka send có thể vẫn đang được xử lý.
        throw new IllegalStateException("Caller hết thời gian chờ", e);
    }
}
```

`get(10, SECONDS)` là deadline của thread gọi phương thức. Nó không thay đổi `request.timeout.ms` hoặc `delivery.timeout.ms` của Kafka client. Nếu API web có timeout ngắn hơn, việc client HTTP ngắt kết nối cũng không tự hủy record đang gửi.

Với API bất đồng bộ, có thể trả `CompletableFuture` cho tầng gọi và áp dụng timeout ở đúng ranh giới API. Hãy ghi rõ timeout đó chỉ điều khiển response của ứng dụng; việc publish Kafka vẫn theo cấu hình producer.

## 10. Thực hành quan sát các timeout

Thực hành trên Kafka cluster local hoặc môi trường lab riêng. Không gây gián đoạn broker production để thử timeout.

### 10.1. Ghi nhận thời gian gửi bình thường

Tạo producer với cấu hình:

```properties
acks=all
enable.idempotence=true
linger.ms=5
request.timeout.ms=3000
delivery.timeout.ms=10000
max.block.ms=5000
```

Giá trị delivery timeout thỏa điều kiện `10000 >= 3000 + 5`. Gửi một nhóm record và đo thời gian từ lúc `send()` trả về đến callback/future hoàn tất. Trong môi trường khỏe mạnh, record thường được xác nhận nhanh hơn deadline.

### 10.2. Quan sát request timeout

Trong lab, tạo tình huống broker response bị chậm hoặc mất kết nối tới broker. Có thể dùng công cụ mô phỏng network như Toxiproxy nếu đã có sẵn trong môi trường thử nghiệm. Quan sát producer log và callback/future:

- Request có thể hết `request.timeout.ms`.
- Producer có thể retry nếu lỗi có thể retry và delivery deadline còn.
- Kết quả cuối cùng có thể thành công sau retry hoặc thất bại khi deadline hết.

Một lần ngắt kết nối đơn giản có thể tạo lỗi connection/disconnect trước khi request timeout đủ lâu; điều này vẫn là lỗi ở tầng kết nối và không nhất thiết chứng minh `request.timeout.ms` đã hết. Muốn kiểm tra đúng request timeout, cần mô phỏng broker không trả response trong khi kết nối vẫn tồn tại.

### 10.3. Quan sát delivery timeout

Đặt delivery timeout ngắn trong lab và làm cho broker không thể xác nhận record trong khoảng thời gian đó. Producer sẽ hoàn tất record với lỗi khi delivery deadline hết hoặc sớm hơn nếu gặp lỗi không retry được.

Ghi nhận:

| Quan sát | Giá trị cần ghi |
|---|---|
| Thời điểm gọi `send()` | Timestamp bắt đầu |
| Thời điểm `send()` trả về | Xác định mốc bắt đầu delivery deadline |
| Request timeout | Giá trị cấu hình và số lần request timeout |
| Delivery timeout | Giá trị cấu hình và thời gian callback báo lỗi |
| Số lần retry | Theo producer log/metrics |
| Kết quả record | Success, lỗi timeout hoặc lỗi không retry được |
| Khả năng record đã được append | Đối chiếu topic/partition/offset hoặc event ID nếu có thể |

Không kết luận record chắc chắn chưa tồn tại chỉ vì producer callback báo timeout. Hãy kiểm tra topic bằng consumer hoặc công cụ quản trị khi môi trường phục hồi.

### 10.4. Phân biệt timeout của caller

Giữ delivery timeout dài hơn, nhưng gọi `future.get(1, SECONDS)` trong ứng dụng. Nếu caller hết một giây, thread nhận `TimeoutException` trong khi Kafka producer có thể tiếp tục gửi. So sánh thời điểm caller timeout với thời điểm callback hoàn tất để thấy hai deadline độc lập.

## 11. Theo dõi và chẩn đoán

Khi producer gặp timeout, cần xem log và metrics theo từng lớp.

| Dấu hiệu | Khả năng | Hướng kiểm tra |
|---|---|---|
| `send()` block lâu trước khi trả về | Thiếu metadata hoặc producer buffer đầy | `max.block.ms`, metadata refresh, `buffer.memory`, broker throughput |
| Request timeout lặp lại | Broker/network phản hồi chậm hoặc leader/replication bất ổn | Request latency, network, broker request queue, ISR và leader election |
| Delivery timeout | Record không được xác nhận trong deadline tổng thể | `linger.ms`, request timeout, retry/backoff, broker errors và delivery deadline |
| Timeout ngay khi topic/broker lỗi cấu hình | Lỗi không retry được hoặc metadata không hợp lệ | Topic tồn tại, ACL, serializer, partition leader và broker logs |
| Producer retry tăng nhưng record cuối cùng thành công | Có lỗi tạm thời nhưng deadline còn đủ | Theo dõi retry rate và request latency để phát hiện cluster suy giảm |
| Callback báo lỗi nhưng record có trong topic | Response có thể bị mất sau khi broker append | Dùng event ID và đối soát; không tạo event mới tùy tiện |
| HTTP request timeout nhưng Kafka callback đến sau | Timeout của caller ngắn hơn thời gian gửi Kafka | Thiết kế API async/outbox hoặc ngân sách timeout phù hợp |

Producer metrics nên được theo dõi gồm request latency, record retry rate, record error rate, request error rate, buffer available bytes, buffer wait time và batch size. Tên metric cụ thể có thể khác theo phiên bản client.

## 12. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt `request.timeout.ms` bằng `delivery.timeout.ms` | Chỉ còn ít hoặc không có dư địa cho batching và retry | Delivery timeout phải đủ lớn so với request timeout và linger |
| Nghĩ request timeout là tổng thời gian gửi record | Hiểu sai nhiều lần retry và thời gian chờ batch | Dùng delivery timeout để giới hạn toàn bộ vòng đời gửi |
| Đặt delivery timeout quá ngắn | Producer báo lỗi trước khi cluster có thời gian phục hồi | Dựa trên latency, replication và SLA để chọn deadline |
| Tăng request timeout để xử lý buffer đầy | Không giải quyết việc `send()` chờ buffer/metadata | Kiểm tra `max.block.ms`, buffer memory và tốc độ drain |
| Tăng delivery timeout để sửa ACL/serializer lỗi | Lỗi không retry được vẫn thất bại ngay | Sửa nguyên nhân cấu hình hoặc quyền truy cập |
| Nghĩ `Future.get(timeout)` hủy request Kafka | Có thể gửi lại trong khi request cũ vẫn đang hoàn tất | Xem đây là timeout của caller; theo dõi future và dùng idempotency |
| Retry ở tầng nghiệp vụ với event ID mới | Có thể tạo duplicate event | Giữ event ID ổn định và deduplicate ở consumer |
| Đặt timeout rất thấp để phát hiện broker lỗi nhanh | Retry không cần thiết, tăng tải và có thể tạo duplicate nếu không idempotent | Đo latency và đặt request timeout lớn hơn thời gian broker cần cho xử lý/replication |

## 13. Checklist cấu hình timeout

- [ ] `request.timeout.ms` phù hợp với thời gian phản hồi broker và replication lag.
- [ ] `delivery.timeout.ms >= request.timeout.ms + linger.ms`.
- [ ] Delivery deadline cho phép số lần retry có ích nhưng không giữ record pending quá lâu.
- [ ] `max.block.ms` được cân nhắc riêng cho metadata và buffer allocation.
- [ ] Timeout của HTTP/API và `Future.get(timeout)` được xem là deadline của caller, không phải lệnh hủy Kafka send.
- [ ] Producer idempotence được bật khi cần bảo vệ retry ở protocol.
- [ ] Event ID ổn định và consumer idempotent để xử lý kết quả không xác định.
- [ ] Callback/future error được ghi nhận cùng topic, key, event ID và client ID.
- [ ] Có metrics cho request latency, retry, error, buffer wait và record delivery.
- [ ] Đã thử nghiệm broker/network failure trên môi trường lab trước khi áp dụng production.

## 14. Câu hỏi tự kiểm tra

1. `request.timeout.ms` bắt đầu có ý nghĩa ở giai đoạn nào của Produce request?
2. Vì sao một record có thể trải qua nhiều request timeout trước khi delivery timeout kết thúc?
3. `delivery.timeout.ms` tính từ thời điểm nào và bao gồm những khoảng chờ nào?
4. Vì sao Kafka yêu cầu delivery timeout lớn hơn hoặc bằng request timeout cộng linger?
5. `max.block.ms` khác `delivery.timeout.ms` như thế nào?
6. Nếu `Future.get(1, SECONDS)` timeout, Kafka có tự hủy record không?
7. Vì sao producer có thể báo timeout dù broker đã append record?
8. Idempotent producer bảo vệ loại retry nào? Vì sao vẫn cần event ID nghiệp vụ?
9. Khi request timeout liên tục, cần kiểm tra những chỉ số broker và network nào?
10. Vì sao tăng timeout không sửa được lỗi serializer hoặc ACL?

## Tài liệu tham khảo

- [Apache Kafka 4.4 — Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/): định nghĩa, phạm vi và giá trị mặc định của `request.timeout.ms`, `delivery.timeout.ms`, `linger.ms`, `max.block.ms` và `retries`.
- [Apache Kafka — Producer API](https://kafka.apache.org/documentation/#producerapi): `KafkaProducer.send`, `Future`, callback, flush và close.
- [Apache Kafka — Producer Metrics](https://kafka.apache.org/documentation/#producer_monitoring): metric để theo dõi request latency, retry, error và buffer.
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate`, kết quả gửi và `CompletableFuture`.

> `request.timeout.ms` kiểm soát thời gian chờ response của một request; `delivery.timeout.ms` kiểm soát deadline tổng thể để producer báo kết quả cho record. Timeout chỉ quyết định thời gian chờ và retry, không tự xác định record đã được append hay chưa.
