# Đánh giá batching, nén payload và chi phí chuyển đổi JSON

## 1. Tại sao cần đo cả ba kỹ thuật cùng nhau?

Trong hệ thống **Spring AMQP + RabbitMQ**, producer dùng `RabbitTemplate` phát sự kiện tới exchange, broker định tuyến tới queue qua binding và `@RabbitListener` xử lý bất đồng bộ. Khi lưu lượng tăng, ta thường nghe ba đề xuất: **gộp nhiều message (batching)**, **nén body (compression)** hoặc **tối ưu JSON serialization**. Không có kỹ thuật nào mặc nhiên nhanh hơn trong mọi tình huống:

- Batching giảm số **AMQP publish/physical deliveries** và overhead trên một sự kiện, nhưng tạo thêm thời gian chờ ở producer và tăng phạm vi lỗi.
- Nén gzip giảm số byte truyền/lưu nếu dữ liệu đủ lớn, có tính lặp; nó lại tốn CPU và cấp phát bộ nhớ cho nén/giải nén.
- JSON dễ tích hợp đa ngôn ngữ và linh hoạt schema, nhưng encode/decode, object allocation và ánh xạ kiểu có chi phí; đổi converter có thể chỉ cải thiện một phần nhỏ tổng thời gian xử lý.

Mục tiêu đúng không phải là “batch lớn nhất” hay “nén mạnh nhất”, mà là **đạt thông lượng và độ trễ mục tiêu trong giới hạn CPU, RAM, mạng, độ tin cậy và chi phí vận hành**.

Ví dụ một service vận chuyển nhận sự kiện `shipment.requested`:

~~~text
Order Service
   |
   | Java DTO -> JSON byte[]
   |      -> (optional) batch
   |      -> (optional) gzip
   v
RabbitTemplate / BatchingRabbitTemplate
   |
   v
RabbitMQ exchange -- binding --> queue
                                  |
                                  v
                         (optional) gunzip
                                  |
                             de-batching
                                  |
                              JSON parse
                                  |
                             @RabbitListener
                                  |
                                  v
                        Database / business task
~~~

**Sau bài học**, bạn có thể:

1. Phân biệt **producer batching**, **consumer batching** và **batch ACK** trong Spring AMQP.
2. Giải thích thứ tự **JSON → batching → gzip** và **gunzip → de-batching → JSON**.
3. Cấu hình `BatchingRabbitTemplate`, `SimpleBatchingStrategy`, `GZipPostProcessor`, `GUnzipPostProcessor` và JSON converter phù hợp phiên bản.
4. Xây benchmark có đối chứng, warm-up, cỡ mẫu và số đo end-to-end đáng tin cậy.
5. Đọc kết quả throughput, p95/p99 latency, CPU, GC, heap, network và backlog; xác định điểm hòa vốn của nén.
6. Quyết định tối ưu mà vẫn giữ publisher confirms, retry, DLQ, idempotency và khả năng phục hồi.

> Các con số trong bài chỉ là **đầu vào minh họa để thiết kế thí nghiệm**, không phải benchmark thực đo. Không kết luận “batching tăng x lần” hoặc “gzip tiết kiệm y%” nếu chưa đo trên broker, payload và hạ tầng thật.

## 2. Ba kiểu batching rất dễ bị nhầm

### 2.1. Producer batching: nhiều sự kiện thành một delivery

`BatchingRabbitTemplate` là subclass của `RabbitTemplate`. Nó thu thập message theo `BatchingStrategy` rồi gửi khi đủ lô hoặc hết thời gian chờ. `SimpleBatchingStrategy` dùng các tham số:

| Tham số | Ý nghĩa | Tác động |
| --- | --- | --- |
| `batchSize` | Số message logic tối đa trước khi phát lô đầy. | Cao hơn thường giảm số publish vật lý khi tải cao nhưng có thể tăng chờ khi tải thấp. |
| `bufferLimit` | Giới hạn tổng số byte của lô; có thể phát lô chưa đủ `batchSize` khi thêm nữa sẽ vượt ngưỡng. | Tránh bộ đệm tăng quá lớn; **không phải giới hạn cứng cho một message đơn lẻ**. |
| `timeout` | Khoảng chờ để nhả partial batch khi không đủ message. | Chặn độ trễ chờ không giới hạn trong thiết kế bình thường; scheduler và lỗi hạ tầng vẫn có thể ảnh hưởng. |

`SimpleBatchingStrategy` hỗ trợ **một cặp exchange/routing key tại một thời điểm**. Không xem đây là cơ chế gom tùy ý các sự kiện đi tới nhiều routing key khác nhau; muốn đa tuyến, cần thiết kế chiến lược/producer riêng và kiểm thử.

Batch được đóng gói:

~~~text
Logical event #1 (JSON) -> [4-byte length][JSON bytes #1]
Logical event #2 (JSON) -> [4-byte length][JSON bytes #2]
Logical event #3 (JSON) -> [4-byte length][JSON bytes #3]

AMQP physical message body:
[len1][json1][len2][json2][len3][json3]
header: springBatchFormat = lengthHeader4
~~~

Lúc nhận, Spring container dùng header này để **de-batch**, thường gọi listener một lần cho mỗi event logic. Broker **không biết** ba event logic ở bên trong; RabbitMQ chỉ thấy **một physical delivery**.

**Chi phí/đánh đổi:**

- Ít publish vật lý hơn nhưng có thêm **4 byte length** trên mỗi fragment, header và chi phí ghép/tách.
- Lô chờ trong bộ nhớ producer; nếu tiến trình chết **trước khi flush/publish**, các sự kiện chưa gửi có thể mất nếu không có outbox.
- Nếu một fragment gây lỗi/reject, **toàn bộ physical batch** có thể bị reject/requeue/dead-letter, làm các event hợp lệ bị xử lý lại.
- Publisher confirm (nếu được bật) tương ứng thao tác publish **physical batch**, không phải confirm độc lập cho mỗi event logic.
- Metadata của physical message có thể được lấy từ **phần tử đầu trong batch**. Không dựa vào `messageId` hoặc header của từng fragment như một hợp đồng được giữ độc lập; đặt `eventId` vào payload logic hoặc envelope tương ứng.

### 2.2. Consumer batching: gom các physical deliveries để xử lý cùng lúc

`SimpleMessageListenerContainer` có `consumerBatchEnabled=true`, `batchSize` và `batchReceiveTimeout`/`receiveTimeout` để gom **những message broker đã gửi riêng lẻ** thành một batch ở consumer. Đây là cơ chế khác producer batching.

Ví dụ:

~~~text
Producer publish: msg A, msg B, msg C (3 AMQP deliveries)
Broker stores:     A | B | C
Consumer batch:    [A, B, C] -> one @RabbitListener(List<...>) call
~~~

Consumer batch không làm broker nhận ít publish hơn, nhưng có thể giảm số lần gọi method, số transaction/DB batch hoặc overhead xử lý downstream. Nếu consumer nhận một producer-created batch, nó có thể de-batch thành các event logic rồi đưa vào consumer batch; **số phần tử trong List có thể vượt `batchSize`**, vốn được hiểu theo số physical deliveries thu thập.

### 2.3. Batch ACK khác với batch listener

`SimpleMessageListenerContainer.setBatchSize(...)` còn ảnh hưởng cách gom ACK/transaction khi dùng `AcknowledgeMode.AUTO` và cấu hình container phù hợp. Đây là một chiều tối ưu khác, không tự biến `@RabbitListener(String payload)` thành `@RabbitListener(List<...>)` và không thay đổi số publish từ producer.

| Kỹ thuật | Giảm số publish vật lý? | Giảm lời gọi listener? | Phạm vi ACK/retry |
| --- | --- | --- | --- |
| Producer batching | **Có**, khi lô đủ nhiều event. | Không mặc định: container có thể tách rồi gọi từng event. | Có thể gắn với cả physical batch. |
| Consumer batching | Không. | Có, chuyển nhiều deliveries vào một lời gọi List. | Theo những delivery đã nhận, tùy container/ACK mode. |
| Batch ACK/container transaction | Không. | Không nhất thiết. | Dời thời điểm ACK/commit của một nhóm delivery; phải cân nhắc duplicate/redelivery. |

**Đừng so sánh benchmark “producer batch” với “consumer batch” mà gọi cả hai là cùng một phép tối ưu.**

## 3. Compression: gzip chạy ở vị trí nào?

Spring AMQP có `MessagePostProcessor`, trong đó:

- `GZipPostProcessor` nén body, thêm/sửa thông tin `contentEncoding` và metadata phù hợp.
- `GUnzipPostProcessor` giải nén body ở phía nhận.
- `RabbitTemplate.setBeforePublishPostProcessors(...)` chạy **ngay trước publish**.
- Listener container có `addAfterReceivePostProcessors(...)` hoặc setter tương ứng để xử lý **sau khi nhận**, trước khi giao cho listener.

**Điểm quan trọng:** khi sử dụng `BatchingRabbitTemplate`, `beforePublishPostProcessors` chạy **sau khi batch được ghép**. Bởi vậy:

~~~text
Producer batching + gzip (thứ tự phù hợp):
  DTO1 --> JSON1 --+
  DTO2 --> JSON2 --+--> [len1][JSON1][len2][JSON2] --> gzip --> publish
  DTO3 --> JSON3 --+

Consumer:
  RabbitMQ delivery --> gunzip --> de-batching --> JSON decode --> listener
~~~

Điều này khác với “nén từng JSON rồi mới ghép”. Với một lô có nhiều key JSON trùng nhau, **gzip trên cả batch có thể tận dụng tính lặp xuyên các event** tốt hơn nén riêng từng event. Đổi lại, phải cấp phát/giải nén cả physical batch và một lỗi nén có thể ảnh hưởng toàn lô.

**Không dùng `RabbitTemplate.setAfterReceivePostProcessors` để thay thế xử lý của `@RabbitListener` một cách tùy tiện:** setter trên template phục vụ những thao tác nhận **qua chính RabbitTemplate** (polling/receive). Với listener bất đồng bộ, gắn decompressor vào **listener container**.

### 3.1. Content encoding là một phần của giao thức giữa producer và consumer

Nếu producer nén nhưng consumer không giải nén, JSON converter sẽ nhận dữ liệu gzip binary và báo parse error. Nếu consumer cố giải nén **hai lần**, cũng lỗi. Tất cả producer/consumer trên queue phải đồng ý về:

- Compression algorithm: gzip hoặc không nén.
- `contentEncoding`, `contentType`, converter và thứ tự các post-processor.
- Các phiên bản Spring AMQP có khác nhau về delimiter trong `contentEncoding` khi có nhiều encoding.
- Giới hạn kích thước message **sau giải nén**, để chống oversized payload và decompression bomb.

Từ Spring AMQP 2.2.12, delimiter mặc định giữa các phần `contentEncoding` là `", "` thay vì `":"` ở các phiên bản 2.2.11 trở về trước. Nếu producer mới giao tiếp với consumer quá cũ, cần cấu hình delimiter tương thích hoặc nâng cấp consumer; không đo benchmark khi pipeline giải nén chưa thật sự đúng.

`GZipPostProcessor` mặc định có thể **tái sử dụng và sửa MessageProperties** nhằm giảm chi phí; nếu giữ reference original message để so sánh/correlate, cân nhắc tùy chọn `copyProperties=true` (có từ 2.1.5).

### 3.2. Khi nào gzip thường có ích?

| Payload | Khả năng giảm byte | Chi phí/rủi ro |
| --- | --- | --- |
| JSON ngắn 100–300 B | Thường ít lợi ích; header gzip/CPU có thể làm tổng kích thước lớn hơn. | Độ trễ và allocations tăng. |
| JSON vài KB, lặp tên trường/nội dung | Thường nén tương đối tốt. | Phải đo CPU và p99. |
| JSON hàng chục KB, text có cấu trúc lặp | Có thể giảm network đáng kể. | RAM/GC/decompress cost, queue/memory limit. |
| Byte đã nén (JPEG, PNG, ZIP, MP4) | Thường rất ít lợi ích. | Gần như chỉ thêm CPU và overhead. |
| Ciphertext sau mã hóa AEAD | Thường không nén hiệu quả. | Không tự nén sau encrypt; xem xét rò rỉ kích thước nếu nén trước encrypt. |
| Dữ liệu ngẫu nhiên/binary có entropy cao | Lợi ích thấp hoặc âm. | Bỏ qua gzip hoặc dùng threshold có đo đạc. |

**Không công bố một ngưỡng “gzip từ 1 KB là luôn tốt”.** Điểm hòa vốn thay đổi theo CPU, payload, băng thông, latency mạng, instance type và cả cách Java cấp phát bộ nhớ.

## 4. JSON conversion: đo đúng công việc của converter

Với Spring AMQP, `MessageConverter` biến Java object thành AMQP `Message` và ngược lại. Với JSON thường là:

~~~text
Producer Java object
   |
   v
Jackson serialize -> UTF-8 bytes
   |
   v
MessageProperties + JSON metadata
   |
   v
RabbitTemplate -> RabbitMQ

Consumer
   |
   v
bytes -> Jackson deserialize -> Java DTO
   |
   v
@RabbitListener(DTO)
~~~

Chi phí có thể gồm: duyệt object graph, codec UTF-8, allocation của byte array/string/collection, annotation/type mapping, cache metadata, kiểm tra schema và GC. Nếu consumer chỉ cần một vài trường trong payload lớn, tạo toàn bộ object graph có thể lãng phí.

### 4.1. Lưu ý phiên bản converter

| Dòng Spring AMQP | Converter JSON thường dùng | Lưu ý |
| --- | --- | --- |
| **3.2.x** | `Jackson2JsonMessageConverter` (Jackson 2). | Phổ biến với Spring Boot 3.x, cần tin cậy type mapping/inferred type đúng. |
| **4.x** | `JacksonJsonMessageConverter` (Jackson 3). | `Jackson2JsonMessageConverter` cũ bị deprecated trong 4.0 theo lộ trình migration. |

Không so sánh hai converter trên **hai bộ Spring Boot/JVM/broker khác nhau** rồi kết luận thay converter là nguyên nhân duy nhất. Chênh lệch library/runtime cũng tác động tới kết quả.

**An toàn:** không bật Java native deserialization từ dữ liệu không tin cậy để “tăng hiệu năng”. Với JSON, quản lý type headers, class mapping và danh sách type được phép; không nhận arbitrary class từ một header do người gửi có thể điều khiển.

### 4.2. Ba mốc nên đo độc lập

1. **Serialize cost:** `DTO -> byte[]` bằng Jackson trong cùng JVM, không truy cập RabbitMQ.
2. **Deserialize cost:** `byte[] -> DTO` với cấu hình thực của consumer.
3. **End-to-end message cost:** từ business event được tạo, qua publish, broker, listener, database đến hoàn tất nghiệp vụ.

Nếu JSON serialization chỉ chiếm 3% CPU tổng luồng và database mất 40 ms/message, tối ưu JSON 2 lần có thể hầu như không đổi throughput. Dùng **profiling** (JFR, async-profiler, Micrometer tracing) để xác định hotspot thật, không suy ra từ kích thước JSON.

## 5. Thiết kế thí nghiệm: đo biến nào, giữ cố định biến nào?

### 5.1. Định nghĩa mục tiêu trước khi benchmark

Một báo cáo hiệu năng có ích nên trả lời:

| Câu hỏi | Metric | Đơn vị |
| --- | --- | --- |
| Xử lý được bao nhiêu nghiệp vụ? | Logical events processed / giây | events/s |
| Broker phải nhận bao nhiêu publish? | Physical AMQP publishes / giây | publishes/s |
| Một event chờ lâu bao nhiêu? | End-to-end p50/p95/p99 | ms |
| Producer có bị nghẽn không? | Publisher confirm latency, pending confirms, batch waiting time | ms, số lượng |
| CPU chi vào đâu? | CPU utilization, process CPU, JFR stack samples | %, core-ms/event |
| Nén có giảm byte không? | Before/after gzip sizes, broker network I/O | bytes/event, bytes/s |
| Ứng dụng có tạo nhiều rác? | Allocation rate, heap usage, GC pauses | bytes/event, ms |
| Broker/consumer có theo kịp? | Queue ready/unacked, oldest message age, listener processing time | số lượng, s, ms |
| Lỗi có bị khuếch đại? | Requeue, DLQ, duplicates, retry attempts | count/rate |

**Throughput** phải dựa trên **logical business events hoàn tất**, không phải số `convertAndSend()` hay số physical deliveries. Một batch 50 event được broker nhận chỉ là **một physical publish** nhưng chứa **50 logical events**.

Với luồng có database, có ít nhất ba mốc độ trễ:

~~~text
T0 = business event được tạo trước JSON encode
T1 = physical publish được phát vào broker (có thể sau batch wait)
T2 = listener đã hoàn tất và ghi tác vụ nghiệp vụ
T3 = DB commit/ACK theo hợp đồng xử lý

Producer-side  = T1 - T0
Broker+consumer = T2 - T1
Business E2E   = T3 - T0
~~~

Trong ví dụ khác process/host, không lấy `System.nanoTime()` của producer trừ `System.nanoTime()` của consumer: hai process có gốc thời gian khác nhau. Dùng clock đồng bộ với sai số được báo cáo hoặc distributed tracing/benchmark controller đo thời gian từ một nguồn tin cậy; khi đo **bên trong một JVM**, `System.nanoTime()` thích hợp cho duration.

### 5.2. Ma trận 2 × 2 cho batching và gzip

Giữ cố định serializer JSON, broker, concurrency, payload và phương thức ACK:

| Kịch bản | Producer batching | Gzip | Mục đích |
| --- | --- | --- | --- |
| A — baseline | Không | Không | Chi phí gốc JSON + broker + consumer. |
| B — gzip | Không | Có | Tác động độc lập của nén từng message. |
| C — batch | Có | Không | Tác động độc lập của batching. |
| D — batch + gzip | Có | Có | Tác động tương tác giữa batching và nén toàn lô. |

Sau đó giữ một kịch bản ổn định (thường A hoặc C) để **đo riêng biến thể chuyển đổi JSON**: Spring converter Jackson, byte[] JSON đã pre-serialize, streaming parser, hoặc serializer khác khi contract cho phép.

**Không kết luận “JSON converter nhanh hơn” nếu đổi đồng thời payload schema, compression, queue type và concurrency.** Mỗi thí nghiệm phải thay đổi có chủ đích một biến hoặc dùng một ma trận factorial rõ ràng.

### 5.3. Bộ dữ liệu đại diện

Tạo payload có sự phân bố gần production, không chỉ dùng một chuỗi ngắn lặp:

| Nhóm | Dữ liệu minh họa | Điều kiểm tra |
| --- | --- | --- |
| Nhỏ | ~200 B, các trường id/status/timestamp. | Overhead gzip, batching wait và fixed costs. |
| Vừa | ~2 KB, JSON có các trường lặp, mô tả. | Điểm hòa vốn network–CPU. |
| Lớn | ~32 KB, danh sách chi tiết hàng hóa. | Băng thông, heap, GC và queue memory. |
| Khó nén | Dữ liệu ngẫu nhiên/đã nén biểu diễn trong body. | Trường hợp gzip kém hiệu quả. |
| Không đều | 90% nhỏ, 9% vừa, 1% lớn (ví dụ giả định). | Tail latency và bufferLimit do outliers. |

Những tỷ lệ ở bảng là **kịch bản giả định để học**, không phải phân bố thực tế. Trên hệ thống của bạn, lấy histogram kích thước từ metric production **không lưu dữ liệu nhạy cảm** rồi tổng hợp dataset test tương ứng.

Mỗi event có `eventId` độc lập, timestamp và checksum/expected result để test **không rơi hoặc trùng**. Khi producer batching, đừng đặt ID duy nhất ở AMQP header của physical message rồi kỳ vọng container giữ được nó cho từng fragment; ID nên có trong JSON của event logic.

### 5.4. Quy tắc benchmark công bằng

1. **Warm-up JVM** trước khi đo (JIT, class loading, connection creation, consumer startup, JSON metadata caches).
2. **Cùng phần cứng/broker/network** cho các biến thể. Ghi version Java, Spring Boot, Spring AMQP, RabbitMQ, queue type, CPU/RAM, TLS, topology và giới hạn container.
3. Chạy **nhiều lần**, thay đổi thứ tự kịch bản ngẫu nhiên hoặc xoay vòng để tránh kết quả lệch do nhiệt độ máy, autoscaling, GC và bộ đệm.
4. Dùng **thời gian đo đủ dài**, tách warm-up và cooldown; chờ queue drain trước mỗi lượt hoặc tạo queue độc lập.
5. So sánh cả **open-loop workload** (tốc độ gửi cố định) và **closed-loop workload** (gửi khi có kết quả) nếu mục tiêu là sức chịu tải lẫn độ trễ. Closed-loop có thể che latency khi hệ thống chậm.
6. Tắt hoặc ghi nhận các nguồn nhiễu: debugger, console logging per message, shared CI load, broker management overhead quá lớn, TCP changes, auto-scaling.
7. Đảm bảo **không drop dữ liệu**: tổng events gửi, events đã commit, duplicates và DLQ phải khớp theo eventId.
8. Dùng cùng persistence/ACK/confirm settings; không “tăng tốc” bằng cách tắt durability trong một kịch bản rồi so với baseline durable.

Nếu workload vượt khả năng xử lý, throughput nhất thời có thể cao do queue đang tích backlog. **Thử nghiệm chưa hoàn thành** cho đến khi đo được trạng thái queue drain và toàn bộ nghiệp vụ hoàn tất hoặc được phân loại lỗi.

## 6. Cấu hình Spring AMQP: bốn kịch bản so sánh

Ví dụ này sử dụng **Java 17**, **Spring Boot 3.x + Spring AMQP 3.2.x** (Jackson 2). Trên Spring AMQP 4.x, thay `Jackson2JsonMessageConverter` bằng `JacksonJsonMessageConverter` (Jackson 3) và kiểm tra dependency/starter phù hợp.

### 6.1. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để xuất Prometheus metric, thêm registry Prometheus tương thích và cấu hình bảo vệ actuator endpoint. Với Java Flight Recorder (JFR), có thể dùng JDK hỗ trợ mà không cần một dependency Spring đặc biệt.

### 6.2. Topology: bốn queue độc lập

Dùng **direct exchange** để mỗi kịch bản có **một queue riêng**, không để hai listener tranh nhau cùng một message:

~~~java
// PerformanceTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PerformanceTopology {
    public static final String EXCHANGE = "perf.events.x";
    public static final String PLAIN = "perf.plain.q";
    public static final String GZIP = "perf.gzip.q";
    public static final String BATCH = "perf.batch.q";
    public static final String BATCH_GZIP = "perf.batch.gzip.q";

    @Bean
    Declarables performanceDeclarables() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);

        Queue plain = QueueBuilder.durable(PLAIN).build();
        Queue gzip = QueueBuilder.durable(GZIP).build();
        Queue batch = QueueBuilder.durable(BATCH).build();
        Queue batchGzip = QueueBuilder.durable(BATCH_GZIP).build();

        Binding p = BindingBuilder.bind(plain).to(exchange).with("plain");
        Binding g = BindingBuilder.bind(gzip).to(exchange).with("gzip");
        Binding b = BindingBuilder.bind(batch).to(exchange).with("batch");
        Binding bg = BindingBuilder.bind(batchGzip)
                .to(exchange).with("batch.gzip");

        return new Declarables(exchange,
                plain, gzip, batch, batchGzip, p, g, b, bg);
    }
}
~~~

Trong production, quản lý topology và queue lifecycle theo chuẩn vận hành. Trong benchmark, mỗi queue phải có trạng thái ban đầu tương đương; nếu thử persistence, quorum/classic queue type phải giống nhau ở bốn kịch bản.

### 6.3. Kiểu sự kiện JSON

~~~java
// PerfEvent.java
public record PerfEvent(
        String eventId,
        String customerGroup,
        String description,
        long createdEpochMillis) {
}
~~~

`eventId` đóng vai trò event logic ID; `customerGroup` chỉ nên có giá trị thuộc một số nhóm không nhạy cảm, không đem toàn bộ customer ID vào metric tags. Timestamp không đủ để đo độ trễ chính xác giữa host lệch clock; ghi thêm trace nếu cần.

### 6.4. Cấu hình RabbitTemplate, batching và gzip

~~~java
// PerformanceProducerConfig.java
import org.springframework.amqp.rabbit.batch.SimpleBatchingStrategy;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.postprocessor.GZipPostProcessor;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class PerformanceProducerConfig {

    @Bean
    Jackson2JsonMessageConverter perfJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean("perfBatchScheduler")
    ThreadPoolTaskScheduler perfBatchScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("perf-batch-");
        // Spring khởi tạo và đóng scheduler theo vòng đời bean.
        return scheduler;
    }

    @Bean("perfPlainPublisher")
    RabbitTemplate plain(ConnectionFactory connectionFactory,
                         Jackson2JsonMessageConverter perfJsonConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(perfJsonConverter);
        return template;
    }

    @Bean("perfGzipPublisher")
    RabbitTemplate gzip(ConnectionFactory connectionFactory,
                        Jackson2JsonMessageConverter perfJsonConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(perfJsonConverter);
        template.setBeforePublishPostProcessors(new GZipPostProcessor());
        return template;
    }

    @Bean("perfBatchPublisher")
    BatchingRabbitTemplate batch(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter perfJsonConverter,
            ThreadPoolTaskScheduler perfBatchScheduler) {
        var strategy = new SimpleBatchingStrategy(
                20,          // tối đa 20 events/physical batch
                128 * 1024,  // 128 KiB bufferLimit
                50);         // timeout 50 ms

        var template = new BatchingRabbitTemplate(
                connectionFactory, strategy, perfBatchScheduler);
        template.setMessageConverter(perfJsonConverter);
        return template;
    }

    @Bean("perfBatchGzipPublisher")
    BatchingRabbitTemplate batchGzip(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter perfJsonConverter,
            ThreadPoolTaskScheduler perfBatchScheduler) {
        var strategy = new SimpleBatchingStrategy(20, 128 * 1024, 50);
        var template = new BatchingRabbitTemplate(
                connectionFactory, strategy, perfBatchScheduler);
        template.setMessageConverter(perfJsonConverter);

        // Quan trọng: chạy trên PHYSICAL batch sau khi ghép.
        template.setBeforePublishPostProcessors(new GZipPostProcessor());
        return template;
    }
}
~~~

`batchSize=20`, `bufferLimit=128 KiB` và `timeout=50 ms` là **giá trị khởi đầu thí nghiệm**, không phải khuyến nghị production. Thay đổi từng tham số, đo thêm p95/p99 và mức bộ nhớ producer.

**Lưu ý định tuyến:** mỗi `BatchingRabbitTemplate` ở trên gửi một cặp exchange/routing key duy nhất trong lúc benchmark. Để tránh tranh chấp, **không dùng chung một instance BatchingRabbitTemplate cho nhiều thread vừa đổi routing key liên tục** nếu chưa kiểm tra chiến lược gom và khả năng tuần tự.

**Lưu ý gửi chưa xong:** `BatchingRabbitTemplate.convertAndSend()` có thể trả về khi event mới được **thêm vào bộ đệm**, chưa phát qua broker. Cuối bài test phải gọi `flush()` cho các template batching, sau đó **chờ tất cả logical events được consumer xử lý** và đối chiếu kết quả.

### 6.5. Publisher chọn kịch bản

~~~java
// PerfPublisher.java
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class PerfPublisher {
    private final RabbitTemplate plain;
    private final RabbitTemplate gzip;
    private final BatchingRabbitTemplate batch;
    private final BatchingRabbitTemplate batchGzip;

    public PerfPublisher(
            @Qualifier("perfPlainPublisher") RabbitTemplate plain,
            @Qualifier("perfGzipPublisher") RabbitTemplate gzip,
            @Qualifier("perfBatchPublisher") BatchingRabbitTemplate batch,
            @Qualifier("perfBatchGzipPublisher")
            BatchingRabbitTemplate batchGzip) {
        this.plain = plain;
        this.gzip = gzip;
        this.batch = batch;
        this.batchGzip = batchGzip;
    }

    public void send(String scenario, PerfEvent event) {
        switch (scenario) {
            case "A" -> plain.convertAndSend(
                    PerformanceTopology.EXCHANGE, "plain", event);
            case "B" -> gzip.convertAndSend(
                    PerformanceTopology.EXCHANGE, "gzip", event);
            case "C" -> batch.convertAndSend(
                    PerformanceTopology.EXCHANGE, "batch", event);
            case "D" -> batchGzip.convertAndSend(
                    PerformanceTopology.EXCHANGE, "batch.gzip", event);
            default -> throw new IllegalArgumentException(
                    "Unknown scenario: " + scenario);
        }
    }

    public void flushBatches() {
        batch.flush();
        batchGzip.flush();
    }
}
~~~

Trong benchmark, ứng dụng nên chỉ gửi vào **một scenario tại một thời điểm** hoặc dùng tài nguyên tách biệt/ghi nhận load tổng để không tạo nhiễu. Nếu dùng `flushBatches()` giữa các mẫu đo, nó thay đổi kích thước lô và không còn đo hành vi scheduler bình thường; chỉ flush **khi kết thúc lượt test** hoặc trong kịch bản flush riêng.

### 6.6. Listener factory: giải nén trước de-batching và JSON decode

Các queue A/C nhận body không nén; B/D nhận body gzip. Ta dùng hai factory khác nhau để **không áp dụng gunzip cho message chưa nén**:

~~~java
// PerformanceConsumerConfig.java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.postprocessor.GUnzipPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PerformanceConsumerConfig {

    @Bean("perfPlainListenerFactory")
    SimpleRabbitListenerContainerFactory plainListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter perfJsonConverter) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(perfJsonConverter);
        factory.setConcurrentConsumers(2);
        // deBatchingEnabled mặc định true:
        // producer batch -> các PerfEvent được đưa tới listener riêng.
        return factory;
    }

    @Bean("perfGzipListenerFactory")
    SimpleRabbitListenerContainerFactory gzipListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter perfJsonConverter) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(perfJsonConverter);
        factory.setConcurrentConsumers(2);

        // GUnzip sau khi nhận physical delivery, trước xử lý listener.
        // Sử dụng API container customizer của Spring AMQP 3.x.
        factory.setContainerCustomizer(container ->
                container.addAfterReceivePostProcessors(
                        new GUnzipPostProcessor()));

        return factory;
    }
}
~~~

**Vì sao đặt decompressor trong container?** `@RabbitListener` nhận message từ **listener container**, không phải lời gọi `RabbitTemplate.receive()`. Nếu đặt `setAfterReceivePostProcessors` chỉ ở producer RabbitTemplate, consumer listener không được giải nén.

Spring AMQP hỗ trợ de-batching thông qua metadata `springBatchFormat=lengthHeader4`. Ở queue D, container xử lý physical delivery được **giải nén** rồi tách logical JSON fragments để converter biến thành `PerfEvent`. Đây là đường xử lý cần kiểm chứng bằng integration test thực, đặc biệt khi chuyển phiên bản Spring AMQP hoặc tùy chỉnh MessagePostProcessor.

### 6.7. Bốn listener đo cùng một loại sự kiện

~~~java
// PerformanceListeners.java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class PerformanceListeners {
    private final MeterRegistry metrics;

    public PerformanceListeners(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @RabbitListener(
        queues = PerformanceTopology.PLAIN,
        containerFactory = "perfPlainListenerFactory"
    )
    public void onPlain(PerfEvent event) {
        received("A");
    }

    @RabbitListener(
        queues = PerformanceTopology.GZIP,
        containerFactory = "perfGzipListenerFactory"
    )
    public void onGzip(PerfEvent event) {
        received("B");
    }

    @RabbitListener(
        queues = PerformanceTopology.BATCH,
        containerFactory = "perfPlainListenerFactory"
    )
    public void onBatch(PerfEvent event) {
        received("C");
    }

    @RabbitListener(
        queues = PerformanceTopology.BATCH_GZIP,
        containerFactory = "perfGzipListenerFactory"
    )
    public void onBatchGzip(PerfEvent event) {
        received("D");
    }

    private void received(String scenario) {
        Counter.builder("perf.logical.listener.invocations")
                .tag("scenario", scenario)
                .register(metrics)
                .increment();
    }
}
~~~

Trong ví dụ, các method không có database/HTTP để **đo overhead messaging**, chứ không đại diện cho xử lý đơn hàng thật. `perf.logical.listener.invocations` đếm **lượt gọi** method, **không phải số event đã commit**; retry có thể làm một event được đếm nhiều lần. Trong bài test reliability, cần ghi thêm **eventId** vào durable sink/inbox và assert tác dụng phụ nghiệp vụ. Không thêm eventId làm Micrometer tag vì cardinality cao.

Nếu một scenario không thực hiện cùng khối lượng công việc với scenario khác (ví dụ A ghi DB, D chỉ đếm counter), kết quả throughput không còn so sánh được.

### 6.8. Bật listener batch để đánh giá phần giảm method invocations

Phần A–D ở trên chỉ thay đổi **producer batching và gzip**, còn listener vẫn nhận **mỗi `PerfEvent` riêng**. Nếu muốn đánh giá thêm **consumer batching**, chạy một thí nghiệm **độc lập**:

~~~java
// Bên trong @Configuration, dùng một queue benchmark mới.
@Bean("perfConsumerBatchFactory")
SimpleRabbitListenerContainerFactory consumerBatchFactory(
        ConnectionFactory connectionFactory,
        Jackson2JsonMessageConverter converter) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);
    factory.setBatchListener(true);
    factory.setConsumerBatchEnabled(true);
    factory.setBatchSize(20);
    return factory;
}
~~~

~~~java
@RabbitListener(
    queues = "perf.consumer.batch.q",
    containerFactory = "perfConsumerBatchFactory"
)
public void onMany(java.util.List<PerfEvent> events) {
    // Ví dụ: database batch insert một lượt.
    // Nếu có event lỗi, cần thiết kế partial failure/idempotency rõ ràng.
}
~~~

**Điều kiện:** queue `perf.consumer.batch.q` cần được provision trong test trước khi chạy đoạn này; đây là ví dụ **mở rộng**, không thuộc bốn queue A–D. Với Spring AMQP 3.x, `consumerBatchEnabled=true` yêu cầu listener nhận List. Container sẽ điều chỉnh de-batching thích hợp; không ép `setDeBatchingEnabled(false)` trong cấu hình consumer batching vì producer batch cần được tách để tập hợp logical records.

**Phân biệt:** khi chỉ cần nhận một lô producer-created batch dưới dạng `List`, có thể đặt `batchListener=true` mà **không** bật `consumerBatchEnabled`. Khi bật `consumerBatchEnabled`, container còn gom **nhiều physical deliveries riêng lẻ**. Listener batch không nên dùng trực tiếp cho request–reply với một reply duy nhất thiếu quan hệ rõ ràng tới từng event.

## 7. Đo riêng chi phí JSON bằng JMH

Trong benchmark end-to-end, network và broker có thể che chi phí codec. Dùng **JMH** để đo riêng `DTO -> JSON bytes` và `JSON bytes -> DTO` trong JVM, trên payload có cấu trúc gần thực tế.

### 7.1. Tránh các lỗi microbenchmark cổ điển

- Đừng dùng một vòng `for` tự đo `System.nanoTime()` rồi báo nanoseconds/op: JIT có thể tối ưu code không sử dụng kết quả, GC và warm-up làm số liệu nhiễu.
- Không tạo `ObjectMapper` mới cho mỗi lần serialize nếu production dùng singleton; đó là đo initialization chứ không phải codec thông thường.
- Không chạy JMH cùng lúc với load test RabbitMQ trên một CPU host bị giới hạn, vì chúng cạnh tranh tài nguyên.
- Dùng **nhiều JVM forks**, warm-up và measurement iterations; đo **allocation rate** nếu muốn hiểu GC.
- Thử các DTO khác nhau: record nhỏ, object lồng nhau, danh sách dài, optional/null và payload có nhiều Unicode.

### 7.2. Ví dụ JMH

Khai báo dependency `jmh-core` và annotation processor `jmh-generator-annprocess` (đúng version với nhau) trong **module benchmark riêng**. Trong các build system, cấu hình annotation processing khác nhau; không coi một class JMH đưa vào `src/main/java` là tự động chạy cùng Spring Boot.

~~~java
// JsonCodecBenchmark.java - module JMH riêng, dùng Jackson 2.
import com.fasterxml.jackson.databind.ObjectMapper;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class JsonCodecBenchmark {
    private final ObjectMapper mapper = new ObjectMapper();
    private final PerfEvent event = new PerfEvent(
            "event-42", "enterprise",
            "A representative shipment description with repeated fields",
            1_700_000_000_000L);
    private byte[] encoded;

    @Setup(Level.Trial)
    public void prepare() throws Exception {
        encoded = mapper.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] serialize() throws Exception {
        // Return value được JMH tiêu thụ để tránh dead-code elimination.
        return mapper.writeValueAsBytes(event);
    }

    @Benchmark
    public PerfEvent deserialize() throws Exception {
        return mapper.readValue(encoded, PerfEvent.class);
    }
}
~~~

**Lưu ý:** JMH benchmark ở trên đo **Jackson ObjectMapper trực tiếp**, không tự bao gồm chi phí Spring `MessageConverter`, `MessageProperties`, header type mapping hay RabbitTemplate. Muốn đo converter, thêm một benchmark riêng gọi `toMessage(...)` và `fromMessage(...)` với properties/type inference hợp lệ. Không gọi kết quả ObjectMapper là “toàn bộ chi phí Spring converter”.

Đối với JSON parser streaming, hãy kiểm tra bạn có cần tạo **toàn bộ DTO** hay chỉ đọc một trường. Nếu thay bằng tree model hoặc parser thủ công, phải giữ cùng quy tắc validation và schema để benchmark công bằng.

### 7.3. Khi nào đổi converter sẽ có lợi?

Nếu profiling cho thấy JSON chiếm phần lớn CPU **của producer/consumer**, có thể cân nhắc:

1. Reuse `ObjectMapper` / `JacksonJsonMessageConverter` như singleton thread-safe sau khi cấu hình xong.
2. Tránh tạo JSON string trung gian rồi lại gọi `getBytes`; serialize trực tiếp thành UTF-8 bytes khi có thể.
3. Giảm payload không cần thiết; đo cả wire bytes lẫn CPU.
4. Dùng DTO/schema gọn, type mapping rõ ràng; hạn chế polymorphism gây ánh xạ kiểu phức tạp.
5. Tối ưu trường cần giải mã bằng streaming projection **nếu giữ đúng contract dữ liệu**.
6. Đánh giá format khác (Avro, Protobuf...) **chỉ khi tất cả producer/consumer cùng hỗ trợ**, có đo migration/versioning và chi phí vận hành.

Đừng tự động bật Afterburner/Blackbird hoặc tùy chọn Jackson đặc biệt chỉ dựa vào lời đồn; tương thích Java/Jackson/module accessibility thay đổi theo phiên bản. Hãy benchmark và kiểm thử đúng DTO thực tế.

## 8. Phân tích số đo: throughput, byte và latency

### 8.1. Đếm logical và physical

Đặt:

- `N` = số **logical events** đã hoàn thành.
- `P` = số **physical AMQP publishes**.
- `W` = số byte body đã gửi qua broker trong kỳ đo.
- `T` = thời gian đo hữu ích (không gồm warm-up, nhưng cần ghi rõ có tính thời gian drain hay không).

Các metric:

\[
\text{Logical throughput} = \frac{N}{T}
\]

\[
\text{Mean logical events per publish} = \frac{N}{P}
\]

\[
\text{AMQP body bytes per logical event} = \frac{W}{N}
\]

Với batching, `N/P` có thể tới gần `batchSize` khi tải cao, nhưng thấp hơn nếu `timeout` hoặc `bufferLimit` liên tục nhả partial batch. Khi bật retry, cần ghi riêng `publish attempts`, `successful physical batches` và `logical events hoàn tất` để không đánh đồng lượt thử với kết quả.

### 8.2. Compression ratio

Với cùng một physical message:

\[
\text{Compression ratio} = \frac{\text{uncompressed bytes}}
                                  {\text{compressed bytes}}
\]

\[
\text{Size reduction} =
1-\frac{\text{compressed bytes}}{\text{uncompressed bytes}}
\]

**Ví dụ minh họa về cấu trúc**, không phải kết quả thực đo: 20 JSON payload, mỗi cái 2 KiB, khi ghép dạng `lengthHeader4` tạo khoảng `20 × 2 KiB + 20 × 4 B` **trước gzip**, chưa tính AMQP frame và metadata. Gzip có thể giảm kích thước đáng kể nếu 20 JSON có nhiều khóa/giá trị lặp; nếu là dữ liệu ngẫu nhiên, kích thước sau gzip có thể lớn hơn.

Chú ý `W` chỉ là tổng **body byte** khi đo trước publish. **Network bytes thật** còn gồm AMQP frame headers, heartbeats, confirms, TLS overhead, reconnect và dữ liệu protocol. Không gọi `W` là “bytes on wire” chính xác nếu chưa đo ở tầng kết nối.

### 8.3. Độ trễ do chờ batch

Nếu arrival rate thấp, batch chờ đủ `batchSize` có thể kéo dài gần timeout. Ví dụ:

~~~text
batchSize = 20
timeout   = 50 ms

Message 1 đi vào buffer ---- chờ 50 ms (nếu không đủ batch)
Message 2, 3 ...           ---- chờ ít hơn
Batch cuối cùng            ---- phát khi timeout hoặc đủ điều kiện
~~~

Một message không có lỗi broker vẫn có thể chịu p99 cao hơn chỉ vì **đợi gom lô**. Với workload ổn định và đủ nhanh, batch có thể đầy trước deadline; với traffic có khoảng nghỉ, tail latency có thể bị chi phối bởi `timeout`.

**Đừng tối ưu chỉ theo average latency:** p99 có thể xấu đi rõ rệt dù throughput tăng. SLO nên được biểu diễn bằng “99% business event hoàn tất trong X ms” hoặc tiêu chí đúng với nghiệp vụ.

### 8.4. Điểm hòa vốn của gzip

Có thể đặt một mô hình gần đúng:

\[
T_{\text{saved by network}}\approx
\frac{S_{\text{plain}}-S_{\text{gzip}}}
     {B_{\text{effective}}}
\]

\[
T_{\text{extra CPU}}=
T_{\text{compress}}+T_{\text{decompress}}+
T_{\text{additional allocation/GC}}
\]

Nếu tiết kiệm mạng nhỏ hơn chi phí CPU trong một hệ CPU-bound, gzip có thể làm chậm. Nếu mạng hoặc broker I/O là nút thắt, giảm byte có thể cải thiện throughput dù CPU tăng. Trên pipeline bất đồng bộ, các thời gian **có thể chồng lấp**, nên công thức chỉ là mô hình tư duy — quyết định cuối cùng dựa vào phép đo end-to-end.

## 9. Biến cần quét khi tuning

### 9.1. BatchingStrategy

Đối với một workload có throughput đủ lớn, thử các giá trị theo dải, không chỉ một giá trị tốt nhất trong tài liệu:

| Biến | Dải thí nghiệm minh họa | Điều cần quan sát |
| --- | --- | --- |
| `batchSize` | 1, 5, 20, 50, 100 | Physical publishes/s, latency chờ, CPU broker, số fragment bị xử lý lại. |
| `bufferLimit` | 32 KiB, 128 KiB, 512 KiB | Kích thước lô thực, peak heap, GC, broker frame size. |
| `timeout` | 5, 20, 50, 100 ms | p95/p99 khi traffic thấp hoặc bursty. |
| Producer threads | 1, 2, 4, 8 | Contention trên template/strategy, số message đang buffer, tốc độ publish. |
| Listener consumers | 1, 2, 4, 8 | Khả năng drain queue, thứ tự xử lý, DB contention. |
| `prefetch` | 10, 50, 200 | Unacked, bộ nhớ client, fairness và tốc độ ACK. |

Các con số là **điểm quét minh họa**, không phải giá trị khuyến nghị mặc định. `prefetch` cao có thể tăng throughput nhưng làm một consumer ôm nhiều unacked messages và tăng duplicate replay sau crash. `batchSize` lớn có thể vượt giới hạn kích thước/policy của broker nếu `bufferLimit` không được thiết kế đúng.

**Đặc biệt:** `SimpleBatchingStrategy.bufferLimit` giới hạn byte của **batch chưa nén**, và Javadoc nêu rằng giới hạn này **không áp dụng cho một message đơn lẻ**. Nếu có một payload cực lớn, phải chặn ở producer bằng validation/size limit riêng — không trông chờ bufferLimit bảo vệ hoàn toàn.

### 9.2. Compression threshold

So sánh hai chính sách:

**Chính sách X:** gzip mọi physical message. Đơn giản nhưng có thể tốn CPU với message nhỏ.

**Chính sách Y:** chỉ gzip nếu physical body trước nén vượt một ngưỡng thử nghiệm (ví dụ 2 KiB, 4 KiB hoặc 8 KiB), có đo tỷ lệ tiết kiệm. Đây là tùy chỉnh ứng dụng, **không phải tự động mặc định của `GZipPostProcessor`**.

Ý tưởng minh họa một `MessagePostProcessor`:

~~~java
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessagePostProcessor;
import org.springframework.amqp.support.postprocessor.GZipPostProcessor;

public final class LargeMessageGzipPostProcessor
        implements MessagePostProcessor {
    private final int minimumBytes;
    private final GZipPostProcessor compressor = new GZipPostProcessor();

    public LargeMessageGzipPostProcessor(int minimumBytes) {
        this.minimumBytes = minimumBytes;
    }

    @Override
    public Message postProcessMessage(Message message) {
        if (message.getBody().length < minimumBytes) {
            return message; // Không thay contentEncoding.
        }
        return compressor.postProcessMessage(message);
    }
}
~~~

**Điểm cần tự hoàn thiện:** nếu cùng queue chứa cả message gzip và không gzip, phía consumer phải **nhận diện contentEncoding** rồi chỉ giải nén khi có gzip. Không cấu hình `GUnzipPostProcessor` vô điều kiện cho dữ liệu hỗn hợp mà chưa kiểm chứng hành vi của phiên bản. Trong kịch bản A–D, mỗi queue đã tách riêng chế độ nén nên tránh được nhánh này.

Đo số lượng message bị nén, tổng byte trước/sau và CPU. Một số message có thể lớn trước nén nhưng gần như không giảm byte. Nếu cần chính sách tinh vi hơn, đo tỷ lệ nén trên dữ liệu mẫu hoặc phân loại theo event type thay vì tự nén thử nhiều lần rồi bỏ.

### 9.3. JSON converter và kích thước DTO

Đo theo ba dạng:

1. **Typed DTO:** `@RabbitListener(PerfEvent)` với Spring JSON converter.
2. **Raw bytes + ObjectMapper:** `@RabbitListener(org.springframework.amqp.core.Message)` rồi `mapper.readValue(message.getBody(), PerfEvent.class)` trong method.
3. **Projection/streaming:** chỉ đọc các trường cần thiết, nhưng vẫn cần validation theo schema.

Nếu dùng raw message, chi phí chuyển đổi không biến mất: nó chỉ được chuyển khỏi Spring converter vào code ứng dụng. **Đừng báo “raw bytes nhanh hơn” khi thực tế không parse JSON hoặc bỏ qua validation**. Sử dụng cùng DTO, cùng data validation và cùng business sink cho phép so sánh.

Với nhiều event type, nên thiết kế type mapping được kiểm soát; không bật phân giải class tùy ý từ header chỉ để tiết kiệm vài dòng chuyển đổi.

## 10. Độ tin cậy: hiệu năng cao không được đổi bằng mất dữ liệu

### 10.1. Unsent batch trong RAM

Giả sử `batchSize=100` và producer mới nhận 40 sự kiện. Nếu tiến trình bị kill trước scheduler timeout/flush, các event chưa phát **có thể mất** vì batch nằm trong bộ nhớ. Một request HTTP trả 200 chỉ vì `convertAndSend()` trả về **không phải xác nhận message đã vào broker**.

Thiết kế an toàn cho nghiệp vụ quan trọng:

~~~text
DB transaction:
   update business row + insert outbox event(eventId)
                     |
                   COMMIT
                     |
             Outbox dispatcher
                     |
              JSON conversion
                     |
        BatchingRabbitTemplate (buffer RAM)
                     |
                  publish
                     |
              publisher confirm
                     |
             mark outbox success
~~~

Nếu dispatcher chết ở bất kỳ bước nào sau DB commit, sự kiện vẫn ở outbox. Sau restart, retry có thể publish trùng nếu kết quả confirm cũ chưa rõ. **Consumer cần idempotency** theo `eventId`. Batch không thay thế outbox.

### 10.2. Confirm ở mức physical batch

Một physical AMQP message chứa nhiều logical events. Publisher confirm của broker cho biết trạng thái **publish physical batch**:

~~~text
Batch physical publish #41
  - evt-301
  - evt-302
  - evt-303
          |
          v
  publisher confirm ACK / NACK / timeout
~~~

**Không** đánh dấu `evt-301`, `evt-302` và `evt-303` đã **xử lý nghiệp vụ** chỉ vì confirm ACK. Với outbox, cần biết chính xác mapping eventId → physical batch và trạng thái publisher confirm; sau khi confirm ACK, các event chỉ được ghi là **broker accepted/published** theo hợp đồng, vẫn cần phía consumer xử lý.

Với `BatchingRabbitTemplate`, hãy xác minh cụ thể semantics của correlation/publisher confirms theo **phiên bản Spring AMQP**: đừng cho rằng mỗi lần gọi `convertAndSend` ban đầu luôn sinh một callback confirm riêng ngay lúc gọi. Mức độ gom lô làm **đơn vị xác nhận vật lý** khác event logic.

### 10.3. Reject một fragment có thể tác động cả batch

Giả sử batch chứa 19 event hợp lệ và 1 payload sai schema. Sau de-batching, listener có thể xử lý nhiều fragment thành công rồi thất bại ở fragment cuối. **Broker chỉ quản lý physical delivery**, nên một NACK/reject cho batch có thể làm cả 20 event bị requeue hoặc dead-letter.

Khi retry batch:

- Các event đã ghi DB thành công có thể được giao lại.
- Nếu consumer không idempotent, tạo duplicate task/payment/email.
- Nếu chọn `defaultRequeueRejected=true`, một poison record có thể làm cả batch bị giao lại liên tục.
- Nếu chọn không requeue, **toàn physical batch** có thể vào DLQ, kể cả event hợp lệ.

**Chính sách phù hợp tùy nghiệp vụ:**

1. Dùng inbox unique `eventId`, business operation ID hoặc database constraint để xử lý trùng.
2. Phân loại transient vs permanent errors; retry có giới hạn và backoff.
3. Khi cần xử lý từng event độc lập, cân nhắc **không producer-batch** hoặc tách lô ra failure store/queue riêng bằng logic có kiểm soát.
4. Với batch listener, nếu muốn “partial success”, phải thiết kế cách ghi bền vững trạng thái từng event, không nghĩ ACK trong broker có thể xác nhận tùy ý từng fragment của một physical message.
5. Đo **duplicate amplification factor** sau lỗi: số lượt event logic được xử lý lại trên một lỗi physical batch.

### 10.4. Nén và DLQ

DLQ có thể chứa **physical message body đang ở dạng gzip** với metadata batch. Các công cụ redrive và replay phải biết giải nén/de-batch đúng thứ tự trước khi kiểm tra fragment lỗi.

Nếu script vận hành giải nén rồi gửi lại message nhưng **giữ nguyên contentEncoding=gzip**, consumer có thể thử giải nén lần nữa và lỗi. Nếu thay routing key, xem xét các header/rules tương ứng. Không sửa một phần body/header tùy tiện mà không kiểm thử với consumer thật.

Đặt giới hạn **kích thước sau giải nén** để không cho một payload nén nhỏ bung thành bộ nhớ khổng lồ. Mã hóa payload nhạy cảm và nén là hai vấn đề khác nhau; không nén dữ liệu sau khi đã mã hóa rồi mong gzip có tỷ lệ giảm cao.

## 11. Quan sát bottleneck và tránh metric đánh lừa

### 11.1. Metric ứng dụng

Ví dụ metric tùy chỉnh (tên tự định nghĩa, không phải metric RabbitMQ mặc định):

| Metric | Dimension nên có | Điều cần hiểu |
| --- | --- | --- |
| `perf.logical.events.sent` | scenario, event_type | Số event được yêu cầu gửi, chưa chắc broker accepted. |
| `perf.physical.batches.published` | scenario | Số physical publish thực sự được thực hiện (cần instrument đúng hook). |
| `perf.batch.fill_ratio` | scenario | Trung bình số fragment thực tế / batchSize. |
| `perf.batch.wait.duration` | scenario | Thời gian fragment nằm trong producer buffer. |
| `perf.gzip.input_bytes`, `output_bytes` | scenario | Tỷ lệ giảm body trước/sau gzip. |
| `perf.json.serialize.duration` | serializer, payload_size_group | CPU/latency encode JSON. |
| `perf.json.deserialize.duration` | serializer, payload_size_group | Chi phí decode/allocations. |
| `perf.logical.events.completed` | scenario | Số event đã hoàn tất công việc theo business contract. |
| `perf.e2e.latency` | scenario, payload_size_group | p50/p95/p99 từ event tạo đến hoàn thành. |
| `perf.duplicates.detected` | scenario | Số lần consumer gặp eventId đã xử lý. |

**Tuyệt đối không đặt `eventId`, `orderId`, raw payload hoặc customer ID có cardinality cao vào metric tags.** Các giá trị này thuộc log/tracing hoặc bảng đối soát có quyền truy cập thích hợp.

### 11.2. Metric RabbitMQ và host

Khi producer tăng tốc nhưng queue `messages_ready` liên tục tăng, **throughput đầu vào không đồng nghĩa throughput đầu cuối**. Theo dõi:

- RabbitMQ publish/deliver/ack rates, physical queue depth và số consumer.
- `messages_unacknowledged`, prefetch, độ trễ xử lý phía listener.
- RAM, disk usage, resource alarms, connection blocked/flow control.
- Network RX/TX, TCP retransmissions, TLS overhead nếu bật.
- CPU producer/consumer, GC pause, heap allocation, thread contention và DB wait.

Khi batching làm số physical message nhỏ đi, metric `deliver/get` của RabbitMQ có thể **giảm** trong khi số logical events/s **tăng**. Không dùng số deliveries/s một mình để kết luận hệ thống đang làm ít việc hơn.

### 11.3. Cách đọc một số dấu hiệu

| Dấu hiệu quan sát | Giả thuyết | Phép kiểm tra tiếp theo |
| --- | --- | --- |
| Batch tăng throughput nhưng p99 tăng mạnh | Chờ flush/timeout, contention buffer, batch quá lớn. | Đo batch wait theo event; giảm batchSize/timeout. |
| Gzip giảm network nhưng CPU producer ~100% | Compression CPU-bound. | So sánh payload threshold, giảm mức nén, scale CPU. |
| Gzip tiết kiệm byte rất ít | Payload nhỏ/entropy cao/đã nén. | Đo histogram theo loại message; tắt gzip cho nhóm đó. |
| Jackson parse chiếm CPU cao | DTO lớn, converter configuration, allocations. | JFR/JMH, giảm payload, xem inferred type/type mapping. |
| Queue depth tăng khi tăng batch size | Consumer bị bottleneck hoặc ACK/DB chậm. | Đo consumer service time, prefetch và unacked. |
| Thỉnh thoảng burst GC dài | Buffer batch, gzip byte arrays, DTO allocations. | Profiling allocation, heap, batch size, GC logs. |
| Producer “gửi xong” nhưng listener chưa đủ event | Lô chưa flush, timeout scheduler, broker/consumer lag. | Gọi flush cuối lượt, chờ drain và kiểm tra confirms. |
| Sau một lỗi, số event xử lý tăng đột biến | Requeue cả physical batch, duplicate processing. | Theo eventId, count retries và DLQ. |

Nếu môi trường không có metric phân tách JSON/gzip, **không được suy ra** mọi CPU tăng là do gzip. Dùng profiler hoặc đo đối chứng với cùng tải.

## 12. Quy trình benchmark thực hành từ đầu đến cuối

**Bối cảnh:** dịch vụ giao hàng nhận event `shipment.requested` thông qua RabbitMQ. SLA minh họa: 99% sự kiện được tiếp nhận và xử lý trong một deadline đã định; không mất và không xử lý nghiệp vụ trùng.

### Bước 1: Chuẩn hóa môi trường

Ghi thông tin thí nghiệm:

~~~text
JDK / JVM flags:
Spring Boot / Spring AMQP:
RabbitMQ / Erlang:
Queue type: classic / quorum, durable / transient:
Broker nodes / resources:
Producer CPU/RAM limits:
Consumer CPU/RAM limits:
Database: enabled / disabled:
Network RTT / bandwidth:
Publisher confirms: enabled / disabled:
TLS: enabled / disabled:
Consumer ACK mode / prefetch / concurrency:
Retry/DLX policies:
~~~

Với benchmark so sánh hiệu năng thật, nên giữ durable queues, persistent messages, ACK và confirms giống production nếu chúng là yêu cầu của hệ thống. Không tạo benchmark “đẹp” bằng cách vô hiệu hóa các cơ chế bảo đảm cần thiết mà không ghi chú.

### Bước 2: Kiểm thử chức năng trước đo tốc độ

Trước tiên gửi một vài event vào **từng scenario A/B/C/D**:

1. Kiểm tra exchange, binding và bốn queue đúng.
2. Xác nhận listener nhận **đúng eventId và nội dung**.
3. Với B/D, kiểm tra `GUnzipPostProcessor` thật sự giải nén và JSON converter decode thành `PerfEvent`.
4. Với C/D, gửi số event **ít hơn batchSize**, chờ timeout hoặc gọi `flush()` cuối test; bảo đảm không thiếu event.
5. Gửi một event gần giới hạn `bufferLimit` rồi nhiều event nhỏ; xác minh partial batch có thể được nhả.
6. Khi cố tình gửi một event lỗi, quan sát chính sách requeue/DLQ và xác minh event khác trong physical batch không tạo side effect trùng.

Không bắt đầu load test nếu basic functionality chưa PASS. Nếu queue D bị parse error do thứ tự nén/tách sai, throughput = 0 không phải một kết quả tuning hữu ích.

### Bước 3: Chạy A/B/C/D với cùng workload

Cho từng scenario:

~~~text
Phase 1: warm-up              30–60 s (chọn theo môi trường)
Phase 2: measurement          2–5 min hoặc đủ số mẫu
Phase 3: stop accepting work  ngừng tạo event mới
Phase 4: flush pending batch  chỉ dùng cho C/D cuối lượt
Phase 5: wait for drain       so sánh eventIds và trạng thái nghiệp vụ
Phase 6: cooldown/reset      queue và heap/CPU trở về trạng thái phù hợp
~~~

Khoảng thời gian chỉ là **lịch thử nghiệm minh họa**. Muốn tự tin hơn về tail latency và JVM GC, chạy lâu hơn theo SLO/điều kiện tải; warm-up đến khi số liệu ổn định.

Chạy ít nhất hai kiểu tải:

- **Low/bursty:** nhiều khoảng trống và burst ngắn; phát hiện latency batch timeout.
- **Sustained/high:** rate cố định gần công suất mục tiêu; phát hiện giới hạn CPU/network/broker.

Ở mỗi mức tải, phải giữ **cùng số logical events** và phân bố kích thước như nhau. Thực thi nhiều lần và báo phân tán giữa runs, không chỉ một con số cực đại.

### Bước 4: Đối soát kết quả

Một lần chạy chỉ được coi là hoàn thành hợp lệ khi:

\[
N_{\mathrm{logical\ sent}} =
N_{\mathrm{unique\ completed}} +
N_{\mathrm{terminal\ failed}} +
N_{\mathrm{pending\ at\ cutoff}}
\]

Trong đó cần định nghĩa rõ “terminal failed” (ví dụ có DLQ/failure record đã được đối soát) và “pending” (outbox hoặc queue/task đang chờ). **Không đếm retry invocation là logical event mới**. Khi chạy test thông lượng, mục tiêu thường là `pending=0` và `terminal failed=0` sau khi drain, trừ kịch bản lỗi chủ động.

**Thực hành:** một cơ sở dữ liệu test có unique constraint trên `eventId` hoặc bảng `received_event_ids` giúp biết event logic nào đã hoàn thành. Không dùng một `LongAdder` đơn lẻ để chứng minh “không có duplicate” vì nó không chứa danh sách ID.

### Bước 5: Lưu kết quả theo bảng, không bịa số

| Scenario | Logical events/s | p95 (ms) | p99 (ms) | CPU producer (%) | CPU consumer (%) | Body bytes/event | GC alloc/event | Retry/DLQ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A — plain | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| B — gzip | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| C — batch | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| D — batch+gzip | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |

Thêm bảng `batchSize / actualAvgBatchSize / batchWaitP99 / physicalPublishesPerSecond` cho C và D. Nếu chạy nhiều lần, trình bày median và khoảng phân tán (hoặc confidence interval phù hợp), không chọn run nhanh nhất rồi so với run chậm nhất của phương án khác.

### Bước 6: Quyết định theo tiêu chí rõ ràng

**Một ví dụ về thứ tự ưu tiên (không phải thông số chung):**

1. **Không mất dữ liệu và không side effect trùng:** outbox/inbox, ACK/retry/DLQ theo yêu cầu.
2. **p99 nằm dưới SLO** trên workload bursty và sustained.
3. **Throughput đáp ứng peak load** cùng headroom vận hành.
4. **CPU/RAM/network hợp lý** trong ngân sách.
5. **Dễ vận hành và phục hồi:** có metric, logs, runbook, backward compatibility.

Nếu C tăng throughput nhưng p99 vượt deadline nghiệp vụ, có thể giảm timeout/batchSize hoặc bỏ batching. Nếu D giảm network nhưng CPU producer tăng đến mức dễ mất khả năng xử lý burst, gzip có thể không phải lựa chọn đúng cho môi trường đó.

## 13. Các sai lầm khiến benchmark cho kết quả sai

| Sai lầm | Vì sao kết luận sai | Cách sửa |
| --- | --- | --- |
| Đo `convertAndSend()` trả về như “message delivered”. | Batch có thể vẫn nằm trong RAM. | Flush cuối lượt, chờ confirm/drain và đối soát eventId. |
| Lấy physical publishes/s so với logical events/s. | Hai đơn vị khác nhau, batching làm chúng tách xa. | Ghi cả hai và actual batch fill ratio. |
| Chỉ dùng một JSON payload lặp lại. | Gzip hưởng lợi quá mức từ tính lặp, cache/JIT có thể làm kết quả lạc quan. | Nhiều payload/entropy và phân bố thực tế. |
| Không warm-up JVM. | Class loading/JIT chi phối lần đo đầu. | Warm-up rồi mới đo ổn định. |
| Dùng `Thread.sleep` để đợi consumer xong. | Sleep ngắn mất kết quả, sleep dài làm test chậm. | Chờ counter/eventIds/DB trạng thái có timeout hữu hạn. |
| Dùng chung queue cho bốn scenario. | Consumer cạnh tranh, gzip và plain xung đột cấu hình. | Queue/consumer riêng hoặc reset/cấu hình chính xác. |
| Chỉ đo p50 và throughput. | p99 do batch wait/GC có thể vượt SLA. | Đo p95/p99/p99.9 khi đủ mẫu. |
| Đổi batchSize và concurrency cùng lúc không ghi nhận. | Không tách được nguyên nhân. | Ma trận biến, ghi đủ parameters. |
| Benchmark JSON bằng tạo ObjectMapper mỗi lần. | Đo init metadata thay vì use case thực. | Reuse mapper như production, dùng JMH. |
| Báo “0 lỗi” vì chỉ đếm listener invocation. | Một physical batch lỗi có thể làm replay nhiều event. | EventId, DLQ, retry count và DB assertions. |
| Không giới hạn payload sau giải nén. | Gzip bomb hoặc batch quá lớn làm cạn heap. | Đặt max size, input validation và memory budget. |
| Nén payload đã encrypt rồi kỳ vọng tiết kiệm. | Ciphertext thường không có entropy để gzip giảm. | Chỉ cân nhắc nén trước encrypt sau threat modeling. |
| Test trên broker production đang có traffic. | Nhiễu số liệu và rủi ro tác động nghiệp vụ. | Benchmark trên môi trường test gần production, không gây tải ngoài ý muốn. |

## 14. Bài thực hành và câu hỏi tự kiểm tra

**Bài thực hành 1 — Tìm điểm hòa vốn của gzip.** Tạo ba nhóm JSON gần 200 B, 2 KiB và 32 KiB, kèm nhóm JSON khó nén. Đo thời gian encode, gzip, gunzip, decode, bytes trước/sau, p99 end-to-end. Kết luận nhóm nào nên bật gzip theo số liệu thực tế của môi trường.

**Bài thực hành 2 — Tối ưu batch cho lưu lượng biến động.** Với cấu hình C, thử `batchSize` 5/20/50 và `timeout` 10/50/100 ms dưới hai kiểu traffic sustained/bursty. Ghi actualAvgBatchSize, batchWaitP99, throughput và duplicate amplification khi tạo một exception.

**Bài thực hành 3 — Đo JSON độc lập.** Dùng JMH đo serialize/deserialize một `PerfEvent` và một DTO có danh sách con; dùng JFR xem CPU/allocations khi chạy broker-backed test. Báo tỷ lệ CPU dành cho JSON so với tổng ứng dụng và liệu tối ưu codec có cải thiện p99 hay không.

**Bài thực hành 4 — Kiểm chứng độ tin cậy.** Thêm outbox/inbox; kill producer trước khi batch flush, kill consumer sau DB commit nhưng trước ACK và tạo một fragment sai schema. Chứng minh event không mất, không side effect trùng và DLQ/failed records được quản lý.

### Câu hỏi

**Câu 1.** Tại sao 100 lần gọi `BatchingRabbitTemplate.convertAndSend()` chưa chứng minh broker nhận 100 events?

**Đáp án:** Lời gọi có thể chỉ đưa event vào buffer RAM của producer. Phải chờ flush, publish/confirm và consumer xử lý; dùng eventId để đối soát.

**Câu 2.** Vì sao `setBeforePublishPostProcessors(new GZipPostProcessor())` có thể nén hiệu quả hơn khi đặt trên `BatchingRabbitTemplate`?

**Đáp án:** Processor chạy sau khi batch được ghép, giúp gzip khai thác các cấu trúc JSON lặp lại **xuyên nhiều logical events** trong cùng một physical message, đổi lại CPU/latency và phạm vi lỗi lớn hơn.

**Câu 3.** Bật `consumerBatchEnabled` có giảm số publish từ producer không?

**Đáp án:** Không. Nó chỉ gom các delivery đã tới container để gọi listener theo List. Producer batching mới giảm số physical publish.

**Câu 4.** Producer batching chứa 20 event, listener thất bại ở event cuối. ACK/NACK có thể chọn riêng 19 event đầu không?

**Đáp án:** Broker chỉ quản lý **physical delivery** của batch, không có ACK độc lập cho từng fragment. Cần idempotency/partial-failure handling trong DB hoặc thiết kế không batch nếu cần tách lỗi.

**Câu 5.** Một hệ thống dùng gzip giảm 40% body bytes nhưng throughput không tăng. Có mâu thuẫn không?

**Đáp án:** Không. Bottleneck có thể ở CPU nén/giải nén, JSON, database hoặc business logic chứ không phải bandwidth. Cần đo CPU, GC, broker network và p99 để xác định.

**Câu 6.** `Jackson2JsonMessageConverter` của Spring AMQP 3.x và `JacksonJsonMessageConverter` của Spring AMQP 4.x có nên đem so trực tiếp trên hai hệ triển khai khác nhau không?

**Đáp án:** Không. Phải giữ môi trường so sánh tương đương; khác biệt JVM, Spring Boot, Jackson, topology, payload và tài nguyên đều có thể tạo sai lệch.

**Câu 7.** Có thể dùng số message RabbitMQ deliver/s làm throughput nghiệp vụ khi producer batching không?

**Đáp án:** Không trực tiếp. Một physical delivery có thể chứa nhiều logical events. Phải đếm `logical events completed/s` độc lập.

**Câu 8.** Vì sao thời gian chờ batch có thể ảnh hưởng p99 nhiều hơn p50 khi traffic thấp?

**Đáp án:** Những event tới đầu một partial batch phải chờ đủ số hoặc timeout; các event tới sau đợi ít hơn. Latency phân bố không đều, đặc biệt với traffic bursty.

## 15. Checklist triển khai

- [ ] Đã xác nhận bottleneck thật là broker/network/CPU JSON/DB, không chỉ dựa vào trực giác.
- [ ] Thí nghiệm A/B/C/D giữ **cùng payload, SLA, ACK, confirms, queue type và concurrency**.
- [ ] Báo cả **logical events/s** và **physical publishes/s**.
- [ ] Đo p95/p99, GC, CPU, RAM, network, queue ready/unacked, retry/DLQ.
- [ ] `SimpleBatchingStrategy` có `batchSize`, `bufferLimit`, `timeout` đã được đo dưới traffic cao và thấp.
- [ ] Hiểu batch chỉ hỗ trợ một exchange/routing key trong SimpleBatchingStrategy.
- [ ] Có giới hạn payload đơn lẻ; không tưởng `bufferLimit` sẽ chặn mọi oversized event.
- [ ] Gzip chạy trên đúng physical message; listener giải nén trước de-batching/JSON.
- [ ] Content encoding và converter tương thích giữa producer/consumer và các phiên bản Spring AMQP.
- [ ] Nếu dùng gzip có điều kiện, receiver nhận diện đúng message nén/chưa nén.
- [ ] JSON converter phù hợp dòng Spring/Jackson, type mapping an toàn.
- [ ] Đã đo JSON bằng JMH/profiling, không dùng microbenchmark vòng lặp sai cách.
- [ ] Cuối benchmark flush pending batch, chờ queue drain và đối soát event IDs.
- [ ] Khi producer crash trước flush, có **transactional outbox** hoặc cơ chế bền vững tương đương nếu nghiệp vụ không được mất.
- [ ] Consumer có **idempotency**, retry giới hạn và DLQ vì physical batch có thể bị requeue nguyên lô.
- [ ] Kết quả benchmark có nhiều lần chạy, phân bố và điều kiện môi trường tái lập được.

## 16. Tổng kết

Trong **Spring AMQP**, tối ưu batching, gzip và JSON là **bài toán đánh đổi tài nguyên**:

- **Producer batching** bằng `BatchingRabbitTemplate`/`SimpleBatchingStrategy` có thể giảm số publish vật lý, nhưng tăng batch wait, dùng RAM và khuếch đại lỗi ở cấp physical delivery.
- **Gzip** giúp giảm số byte với payload lớn/có tính lặp, đặc biệt khi nén sau khi đã ghép batch; nó đồng thời tiêu thụ CPU, cấp phát bộ nhớ và đòi hỏi giải nén đúng thứ tự.
- **JSON conversion** có chi phí serialize/deserialize và allocations; chỉ nên tối ưu sau khi profiling chứng minh đó là bottleneck, không bỏ validation hoặc an toàn type mapping để chạy nhanh hơn.

Quyết định tối ưu phải dựa vào **benchmark có đối chứng, logical throughput, end-to-end p99, CPU/GC/network và trạng thái nghiệp vụ**. Quan trọng nhất, không đánh đổi **publisher confirms, ACK, retry/DLQ, transaction, outbox và idempotency** để nhận một biểu đồ throughput đẹp nhưng có nguy cơ mất hoặc xử lý trùng dữ liệu.

### Tài liệu tham khảo chính thức

- [Spring AMQP – Sending Messages: Batching](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): `BatchingRabbitTemplate`, `SimpleBatchingStrategy`, `lengthHeader4` và cảnh báo buffer RAM.
- [Spring AMQP – @RabbitListener with Batching](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/batch.html): `batchListener`, `consumerBatchEnabled`, List payloads và de-batching.
- [Spring AMQP – Batched Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/de-batching.html): xử lý producer batches, reject nguyên lô, consumer batching.
- [Spring AMQP – Modifying Messages: Compression and More](https://docs.spring.io/spring-amqp/reference/amqp/post-processing.html): `GZipPostProcessor`, `GUnzipPostProcessor`, content encoding và vị trí post-processor.
- [Spring AMQP – Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): `JacksonJsonMessageConverter` và khác biệt phiên bản Jackson.
- [Spring AMQP 3.2 – Sending Messages](https://docs.spring.io/spring-amqp/reference/3.2/amqp/sending-messages.html): API phù hợp ví dụ Spring 3.x.
- [Spring AMQP – SimpleBatchingStrategy Javadoc 3.2](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/batch/SimpleBatchingStrategy.html): ý nghĩa `bufferLimit`/`batchSize`/`timeout`.
- [OpenJDK JMH Project](https://github.com/openjdk/jmh): microbenchmark Java chuẩn với warm-up/fork/annotation processing.
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK và confirm khác nhau; tác động của redelivery.
- [RabbitMQ – Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms): backpressure và tình trạng broker khi thiếu tài nguyên.
