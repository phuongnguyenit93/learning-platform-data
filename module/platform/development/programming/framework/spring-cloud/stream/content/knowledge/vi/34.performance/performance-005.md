# Đánh giá compression, kích thước payload và chi phí serialization

Hiệu năng của một pipeline Spring Cloud Stream không chỉ phụ thuộc tốc độ broker hoặc số consumer. Mỗi message còn phải được chuyển từ object Java thành byte, có thể được nén, truyền qua mạng, lưu trữ, đọc lại, giải nén và deserialize. Những bước này tiêu thụ CPU, bộ nhớ, băng thông và thời gian xử lý.

Compression có thể giảm byte truyền và dung lượng lưu trữ nhưng làm tăng CPU. Serialization format gọn có thể giảm payload nhưng cần schema, generated code hoặc bước tra cứu schema. Một payload lớn có thể làm tăng latency, heap allocation, GC pressure và nguy cơ vượt giới hạn message của broker. Không có một codec hay định dạng phù hợp cho mọi workload; cần đo trên dữ liệu đại diện và ở cả cấp client lẫn broker.

## 1. Đường đi của một message

Một message trong ứng dụng xử lý sự kiện thường trải qua các bước:

~~~mermaid
flowchart LR
    A["Object nghiệp vụ"] --> B["Serialize"]
    B --> C["Byte payload"]
    C --> D["Compress"]
    D --> E["Publish qua binder"]
    E --> F["Broker / network / storage"]
    F --> G["Consume"]
    G --> H["Decompress"]
    H --> I["Deserialize"]
    I --> J["Function / Consumer"]
~~~

Thứ tự cụ thể có thể khác theo binder và serializer. Ví dụ Kafka nén record batch ở producer; RabbitMQ thường giữ body như byte opaque và ứng dụng phải chủ động nén nếu muốn; Pulsar producer có tùy chọn compression riêng. Dù triển khai theo cách nào, cần xác định chính xác thành phần nào nén và thành phần nào giải nén để tránh nén hai lần hoặc deserialize nhầm dữ liệu.

Các chi phí chính:

| Thành phần | Chi phí có thể phát sinh |
|---|---|
| Serialization | CPU encode, cấp phát byte array, reflection hoặc generated-code work |
| Compression | CPU nén, buffer tạm, độ trễ theo kích thước payload |
| Network | Băng thông, packet, TLS overhead và thời gian truyền |
| Broker storage | Dung lượng log/queue, disk I/O, replication |
| Decompression | CPU và bộ nhớ để khôi phục payload |
| Deserialization | CPU decode, tạo object graph, validation và GC |

Nếu message nhỏ, serialization và scheduling có thể tốn nhiều thời gian hơn truyền dữ liệu. Nếu message lớn hoặc có nhiều chuỗi lặp, compression có thể giảm đáng kể network và storage. Phải đo để biết workload đang bị giới hạn bởi CPU, mạng, broker hay application code.

## 2. Kích thước payload ảnh hưởng đến đâu?

Kích thước payload là số byte của dữ liệu message tại một ranh giới cụ thể. Cần phân biệt ít nhất:

- Kích thước object trong heap: không tương đương kích thước wire.
- Kích thước sau serialization: số byte trước compression.
- Kích thước sau compression: số byte được gửi hoặc lưu theo codec.
- Kích thước protocol record/frame/batch: có thể bao gồm key, headers, metadata và framing.

Ví dụ một OrderEvent có 15 trường Java không có nghĩa message sẽ chiếm 15 lần một đơn vị byte. String được mã hóa thành byte theo charset, field name của JSON lặp lại, timestamp/number có biểu diễn văn bản, schema ID hoặc header có thể bổ sung byte. Binary format thường biểu diễn kiểu dữ liệu trực tiếp và có thể bỏ field name lặp lại.

Payload lớn ảnh hưởng tới:

1. Băng thông giữa ứng dụng và broker.
2. Disk và replication traffic của broker.
3. Thời gian serialize, compress, decompress và deserialize.
4. Kích thước batch và số record có thể gom trong một request.
5. Heap allocation, buffer và garbage collection.
6. Khả năng vượt giới hạn producer, broker, consumer hoặc subscription.
7. Thời gian retry: message lớn được gửi lại nhiều lần có thể nhân chi phí.

Không nên chỉ theo dõi số message mỗi giây. Một pipeline xử lý 5.000 message/s với payload 1 KB có tải byte rất khác pipeline xử lý 5.000 message/s với payload 200 KB.

### 2.1. Đo kích thước tại nhiều ranh giới

Với mỗi loại event, hãy ghi nhận:

| Đại lượng | Cách đo | Mục đích |
|---|---|---|
| Serialized bytes | Độ dài byte array sau serializer | Đánh giá format và schema |
| Compressed bytes | Độ dài byte array sau codec ứng dụng | Tính compression ratio |
| Broker record/message size | Metrics hoặc công cụ của broker | Đánh giá kích thước thực tế broker nhận |
| End-to-end payload size | Theo contract của ứng dụng | So sánh giữa các service |

Compression ratio có thể tính:

\[
R = \frac{\text{compressed bytes}}{\text{serialized bytes}}
\]

Ví dụ payload 100 KB sau compression còn 25 KB thì R = 0,25, tức giảm khoảng 75% số byte ở ranh giới đã đo. Hãy luôn ghi rõ mẫu số và điểm đo; không so sánh compressed body của một broker với tổng request size của broker khác.

## 3. Serialization format: JSON và binary

Serialization biến object thành dạng có thể truyền qua broker. Chọn format ảnh hưởng đến kích thước, CPU, khả năng đọc, schema evolution và sự phụ thuộc giữa producer/consumer.

| Format | Ưu điểm | Đánh đổi |
|---|---|---|
| JSON | Dễ đọc, dễ debug, hỗ trợ rộng, schema linh hoạt | Field name lặp lại, số và timestamp dạng text, parse/allocate có thể tốn CPU |
| Avro | Binary gọn, schema rõ, hỗ trợ schema evolution theo compatibility rules | Cần schema và thường cần schema registry hoặc schema được phân phối |
| Protocol Buffers | Binary gọn, generated code nhanh, field tag hiệu quả | Cần quản lý .proto và quy tắc tương thích khi đổi schema |
| CBOR | Binary representation cho mô hình dữ liệu kiểu JSON | Hệ sinh thái và schema governance phụ thuộc nền tảng |

Không kết luận binary luôn nhanh hơn JSON trong mọi trường hợp. Payload nhỏ có thể bị chi phối bởi overhead gọi serializer, tạo object hoặc chuyển đổi message. JSON với cấu hình Jackson phù hợp có thể đủ nhanh và dễ vận hành. Binary thường có lợi khi throughput lớn, payload lặp nhiều hoặc cần giảm byte rõ rệt.

### 3.1. Ví dụ JSON serialization

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderEvent(
    String eventId,
    String orderId,
    String customerId,
    BigDecimal amount,
    Instant occurredAt,
    String status
) {}
~~~

Với Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();

byte[] bytes = mapper.writeValueAsBytes(event);
OrderEvent decoded = mapper.readValue(bytes, OrderEvent.class);
~~~

Trong ứng dụng thật, cấu hình ObjectMapper nên được quản lý dùng chung, có module cần thiết cho Java time và được kiểm tra bằng test tương thích. Không tạo ObjectMapper mới cho từng message vì khởi tạo mapper và module có chi phí không cần thiết.

### 3.2. Schema và schema evolution

Khi producer và consumer được triển khai độc lập, schema là contract giữa chúng. Hãy xác định:

- Field nào bắt buộc, field nào có thể vắng mặt?
- Có default value không?
- Thay đổi field type có tương thích không?
- Consumer cũ có đọc được message do producer mới tạo không?
- Schema ID/version được truyền ở đâu?
- Schema registry có cache và chính sách availability ra sao?

Avro, Protobuf và JSON Schema có các quy tắc compatibility khác nhau. Kiểm tra chính sách BACKWARD, FORWARD hoặc FULL theo công cụ quản lý schema đang dùng; không chỉ dựa vào việc code compile thành công.

Schema registry thường được cache trong client. Không mặc định mỗi message đều gọi registry qua mạng, nhưng cold start, cache miss, registry outage hoặc schema registration mới có thể thêm latency và failure mode. Đo riêng thời gian encode/decode và thời gian tương tác registry nếu có.

## 4. Chi phí CPU và bộ nhớ của serialization

Một serializer có thể tạo nhiều object tạm: String, byte array, buffer, wrapper, map và metadata. Deserializer có thể tạo object graph lớn hơn payload byte ban đầu. Điều này ảnh hưởng garbage collector, đặc biệt khi message đến với tốc độ cao.

Các nguyên nhân phổ biến:

- Serialize object nhiều lần cho log, publish và audit.
- Chuyển object sang JSON String rồi lại encode String thành UTF-8 byte.
- Tạo ObjectMapper hoặc serializer mới cho từng message.
- Dùng reflection hoặc schema lookup không có cache phù hợp.
- Deserialize toàn bộ payload lớn trong khi chỉ cần một vài field.
- Tạo nhiều bản sao byte array khi nén, giải nén hoặc chuyển converter.
- Giữ payload trong queue nội bộ quá lâu, làm tăng heap retention.

Nên đo allocation rate và GC cùng với CPU. Một cách tối ưu có thể giảm CPU nhưng tăng buffer retention hoặc tăng peak memory; throughput tăng trong benchmark ngắn nhưng latency p99 xấu đi khi chạy lâu.

### 4.1. Tránh serialize nhiều lần

Không nên làm:

~~~java
String jsonForLog = mapper.writeValueAsString(event);
byte[] payload = mapper.writeValueAsBytes(event);
publisher.send(payload);
~~~

Đoạn trên encode cùng object hai lần. Nếu cần log, ghi các field định danh có chọn lọc hoặc log byte count; tránh log toàn bộ payload nếu không cần.

~~~java
byte[] payload = mapper.writeValueAsBytes(event);
logger.debug("Publishing eventId={}, payloadBytes={}",
    event.eventId(), payload.length);
publisher.send(payload);
~~~

Nếu cần compression ở tầng ứng dụng, nén chính byte array vừa tạo thay vì serialize lại object. Đảm bảo byte array không bị sửa sau khi được chuyển cho publisher bất đồng bộ.

## 5. Compression hoạt động như thế nào?

Compression tìm cấu trúc lặp hoặc mẫu có thể biểu diễn bằng ít byte hơn. JSON thường có nhiều field name lặp lại, chuỗi trạng thái và tên thuộc tính giống nhau nên có thể nén tốt. Payload đã nén, mã hóa hoặc chứa dữ liệu ngẫu nhiên thường khó nén thêm.

Các codec thường gặp:

| Codec | Đặc điểm tổng quát | Khi cân nhắc |
|---|---|---|
| gzip/DEFLATE | Tỷ lệ nén thường tốt, phổ biến, CPU có thể cao hơn codec ưu tiên tốc độ | Băng thông hạn chế hoặc payload văn bản lớn |
| Snappy | Ưu tiên tốc độ, tỷ lệ nén vừa phải | Throughput cao, cần chi phí CPU thấp |
| LZ4 | Giải nén nhanh, thường phù hợp pipeline tốc độ cao | Latency và CPU quan trọng |
| Zstandard (Zstd) | Có nhiều mức nén, cân bằng ratio và tốc độ | Muốn điều chỉnh theo tải và năng lực CPU |
| ZLIB | Codec phổ biến, có mức nén điều chỉnh | Tương thích và nhu cầu nén tổng quát |

Đây là đặc điểm tương đối; hiệu năng thực tế phụ thuộc phiên bản thư viện, level, kích thước batch, dữ liệu và CPU. Hãy benchmark thay vì chọn codec theo một bảng xếp hạng chung.

### 5.1. Compression ratio và throughput

Giả sử một batch có 1 MB dữ liệu JSON:

| Kết quả giả định | Kích thước sau nén | Ratio | Byte tiết kiệm |
|---|---:|---:|---:|
| Codec A | 300 KB | 0,30 | 70% |
| Codec B | 420 KB | 0,42 | 58% |
| Không nén | 1.000 KB | 1,00 | 0% |

Nếu Codec A tiêu thụ nhiều CPU hơn đáng kể, nó có thể làm giảm số message xử lý mỗi giây khi producer đã bị giới hạn CPU. Codec B có ratio kém hơn nhưng có thể đạt throughput cao hơn và latency thấp hơn.

Đánh giá đồng thời:

- Compression ratio.
- CPU time cho encode/compress và decompress.
- Throughput theo message/s và byte/s.
- Producer latency và consumer processing latency.
- Network throughput.
- Broker disk usage và replication traffic.
- Allocation rate, heap và GC pause.

## 6. Kafka: compression theo record batch

Kafka producer nén record batch trước khi gửi tới broker. Vì compression hoạt động trên batch, nhiều record cùng partition thường cho cơ hội tìm mẫu lặp tốt hơn so với nén từng record nhỏ độc lập.

Các codec producer phổ biến gồm:

- none
- gzip
- snappy
- lz4
- zstd

Producer property compression.type chọn codec. Consumer Kafka giải nén batch khi đọc; ứng dụng không cần tự gọi GZIPInputStream nếu đang dùng Kafka serializer/deserializer thông thường.

Ví dụ cấu hình riêng cho output binding trong Spring Cloud Stream Kafka binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                compression.type: zstd
                linger.ms: 10
                batch.size: 65536
~~~

Trong ví dụ:

- compression.type chọn codec cho producer binding.
- linger.ms cho producer thêm thời gian gom record vào batch trước khi gửi.
- batch.size đặt mục tiêu kích thước batch theo partition.

Đây là cấu hình minh họa theo Kafka binder property model; hãy xác minh prefix và tên property với phiên bản Spring Cloud Stream Kafka binder của dự án. Nếu dùng nhiều output binding, có thể cấu hình riêng từng binding để tránh áp dụng codec không cần thiết cho mọi luồng.

### 6.1. Batch size và linger

Batch lớn hơn có thể cải thiện compression ratio và giảm số request, nhưng có thể làm tăng thời gian chờ record để batch đầy. Linger tăng giúp gom batch trong tải vừa hoặc thấp; đổi lại thêm latency trước khi gửi.

Không tăng batch.size tối đa ngay lập tức. Hãy quan sát:

- Batch-size-avg và records-per-request-avg.
- Request rate và producer request latency.
- Buffer pool wait time.
- Throughput theo partition.
- p95/p99 publish latency.

Nếu mỗi partition chỉ nhận một record rất thưa, tăng batch.size có thể không tạo ra batch lớn hơn. Nếu số partition tăng, mỗi partition nhận ít record hơn trong cùng thời gian và hiệu quả gom batch có thể giảm.

### 6.2. Compression ở broker và consumer

Kafka broker có thể lưu batch theo codec producer hoặc áp dụng chính sách compression broker tùy cấu hình. Consumer client xử lý giải nén theo định dạng record batch. Đừng nén payload JSON bằng gzip ở application layer rồi lại bật Kafka batch compression mà chưa đo; hai lớp nén thường tạo thêm CPU trong khi lớp thứ hai ít giảm được byte.

Kích thước request, record batch và fetch có các giới hạn khác nhau. Các thuộc tính như producer max.request.size, broker message.max.bytes hoặc topic max.message.bytes, consumer max.partition.fetch.bytes và fetch.max.bytes cần được xem cùng nhau. Compression không phải cách đáng tin cậy để né giới hạn message; một batch sau nén hoặc record quá lớn vẫn có thể bị từ chối hoặc không fetch được như mong đợi.

## 7. RabbitMQ: phân biệt compression của body với AMQP transport

AMQP không tự động biến mọi body thành payload nén chỉ vì client bật TLS hoặc dùng Rabbit binder. RabbitMQ thường xử lý body như byte sequence và không tự giải nén nội dung ứng dụng. Nếu cần compression, producer và consumer phải thống nhất codec và metadata.

Một contract ứng dụng có thể là:

- Body chứa byte đã nén.
- Content type mô tả dữ liệu sau giải nén, ví dụ application/json.
- Content encoding hoặc header tương đương ghi gzip/zstd.
- Consumer đọc encoding, giải nén rồi deserialize.

Ví dụ hàm nén GZIP thuần Java:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

public final class PayloadCompression {

    private PayloadCompression() {
    }

    public static byte[] gzip(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }
        return output.toByteArray();
    }
}
~~~

Consumer cần giải nén tương ứng:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPInputStream;

public static byte[] gunzip(byte[] input) throws IOException {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    try (GZIPInputStream gzip =
            new GZIPInputStream(new ByteArrayInputStream(input))) {
        gzip.transferTo(output);
    }
    return output.toByteArray();
}
~~~

Đây là codec utility, chưa phải cấu hình hoàn chỉnh của Rabbit binder. Khi tích hợp, hãy dùng byte-array serializer/converter hoặc message converter phù hợp, ghi content-encoding theo AMQP message properties/header contract và bảo đảm consumer giải nén trước khi JSON/Avro/Protobuf deserializer chạy. Không để converter mặc định cố parse các byte gzip như JSON văn bản.

Nén ở tầng ứng dụng làm payload body nhỏ hơn nhưng RabbitMQ vẫn phải xử lý message, header, queue index, routing và lưu trữ. Cần kiểm tra giới hạn message của broker và client ở phiên bản đang chạy. Frame max là giới hạn frame của giao thức, không nên dùng nó thay cho giới hạn tổng message.

## 8. Pulsar: producer compression

Apache Pulsar hỗ trợ compression ở producer. Client có thể nén message hoặc batch trước khi gửi tới broker; consumer tương ứng giải nén khi nhận. Các lựa chọn thường gặp trong Java client gồm LZ4, ZLIB, ZSTD, SNAPPY và NONE, tùy phiên bản client.

Ví dụ dùng Pulsar Java client:

~~~java
import org.apache.pulsar.client.api.CompressionType;
import org.apache.pulsar.client.api.Producer;

// client là PulsarClient đã được khởi tạo và cấu hình service URL.
Producer<byte[]> producer = client.newProducer()
    .topic("persistent://public/default/orders")
    .compressionType(CompressionType.ZSTD)
    .create();
~~~

Trong ứng dụng Spring Cloud Stream, cấu hình có thể được chuyển qua Pulsar binder hoặc client properties tùy phiên bản binder. Đối chiếu tài liệu binder tương ứng thay vì giả định tên property Kafka như compression.type dùng được cho Pulsar.

Compression có thể giảm network và storage nhưng tiêu thụ CPU ở producer/consumer. Hãy đo payload thực tế, batching, backlog và latency. Với message đã nén ở tầng ứng dụng, không bật thêm producer compression nếu chưa có benchmark chứng minh lợi ích.

## 9. Khi nào nên nén ở broker client, khi nào ở ứng dụng?

| Cách làm | Điểm nén/giải nén | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Kafka producer compression | Kafka producer nén record batch; consumer giải nén | Tích hợp native, batch compression, application giữ object bình thường | Chỉ áp dụng cho Kafka client; cần chỉnh producer config |
| Pulsar producer compression | Pulsar producer/client | Tích hợp native với client và batching | Cần cấu hình đúng binder/client; phụ thuộc codec support |
| Rabbit/application compression | Application hoặc converter trước khi publish | Dùng được khi cần kiểm soát body hoặc chia sẻ contract giữa hệ thống | Phải quản lý content encoding, compatibility và giải nén |
| Compression trước broker chung | Producer ứng dụng nén byte | Có thể dùng cùng payload trên nhiều broker | Consumer phải biết codec; broker không thể tự hiểu nội dung |

Ưu tiên compression native của broker client khi nó đáp ứng yêu cầu và cho phép consumer xử lý tự động. Dùng application-level compression khi cần một payload contract nén độc lập với broker hoặc cần nén trước một tầng trung gian. Tránh nén hai lần cùng một nội dung.

## 10. Payload lớn và giới hạn của broker

Mỗi broker và client có giới hạn kích thước khác nhau. Những giới hạn này có thể áp dụng cho message, record batch, request, frame, fetch hoặc buffer; chúng không nhất thiết dùng cùng một cách tính.

| Hệ thống | Nhóm giới hạn cần kiểm tra | Điều cần chú ý |
|---|---|---|
| Kafka | Producer request, broker/topic record batch, consumer fetch | Giới hạn producer, broker và consumer phải tương thích |
| RabbitMQ | Broker maximum message size, protocol frame, client memory/buffer | Frame size không đồng nghĩa total message size |
| Pulsar | Broker maximum message size, producer/batch và consumer receive | Kiểm tra cấu hình broker, namespace và client version |

Nếu message quá lớn, các lựa chọn thường là:

1. Giảm field không cần thiết hoặc bỏ dữ liệu lặp.
2. Dùng schema binary nếu phù hợp.
3. Nén payload nếu dữ liệu có thể nén.
4. Chia nhỏ message theo một contract có sequence ID, chunk count và idempotency.
5. Lưu blob lớn trong object storage rồi gửi event chứa URI, checksum, content type và metadata.

Với payload nhiều MB hoặc hàng trăm MB, mô hình claim-check thường phù hợp hơn đưa toàn bộ blob qua broker. Broker nên vận chuyển sự kiện và tham chiếu; object storage chịu trách nhiệm lưu nội dung lớn. Cần bảo đảm quyền truy cập, thời hạn lưu, checksum, retry và cleanup của object.

Chunking làm tăng độ phức tạp: consumer phải ghép đủ chunk, xử lý chunk thiếu/trùng/thứ tự sai, timeout và cleanup trạng thái. Chỉ chọn khi có yêu cầu thực sự và thiết kế recovery rõ ràng.

## 11. Compression và TLS giải quyết hai vấn đề khác nhau

Compression giảm số byte của payload có thể nén. TLS mã hóa dữ liệu trên đường truyền và xác minh peer. TLS không phải compression và compression không phải encryption.

Khi dùng TLS:

- TLS record framing và handshake có overhead riêng.
- Compression của application payload có thể diễn ra trước TLS encryption.
- Không nên trông đợi TLS nén nội dung; TLS compression đã bị loại bỏ trong các cấu hình hiện đại vì rủi ro bảo mật.
- Nén dữ liệu bí mật cùng dữ liệu do attacker kiểm soát trong cùng một context có thể tạo side-channel; cân nhắc threat model nếu payload chứa secret.

Thứ tự phổ biến là serialize, compress nếu cần, sau đó TLS mã hóa byte truyền đi. Ở đầu nhận, TLS giải mã transport trước, rồi application/broker client giải nén và deserialize theo contract.

## 12. Ví dụ đo serialize và compression

Đo đơn giản trong unit test có thể giúp so sánh kích thước, nhưng không dùng System.nanoTime trong một vòng lặp ngắn làm kết luận benchmark cuối cùng. JVM warm-up, JIT, GC và CPU scheduling có thể làm kết quả sai lệch.

Ví dụ thu thập kích thước:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class PayloadSizer {

    public static void main(String[] args) throws IOException {
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        OrderEvent event = new OrderEvent(
            "evt-1001",
            "order-1001",
            "customer-42",
            new java.math.BigDecimal("125.50"),
            java.time.Instant.parse("2026-03-10T10:15:00Z"),
            "ACCEPTED"
        );

        byte[] json = mapper.writeValueAsBytes(event);
        byte[] gzip = gzip(json);

        double ratio = (double) gzip.length / json.length;
        double savedPercent = (1.0 - ratio) * 100.0;

        System.out.printf("serialized=%d bytes%n", json.length);
        System.out.printf("gzip=%d bytes%n", gzip.length);
        System.out.printf("ratio=%.3f%n", ratio);
        System.out.printf("saved=%.1f%%%n", savedPercent);
    }

    static byte[] gzip(byte[] input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(input);
        }
        return output.toByteArray();
    }
}
~~~

Đo trên một event chỉ minh họa phép tính. Hãy chạy trên tập dữ liệu có phân phối kích thước và nội dung gần production, gồm payload nhỏ, trung bình, lớn, dữ liệu lặp nhiều và dữ liệu khó nén.

## 13. Benchmark đúng cách

Một benchmark hữu ích cần trả lời câu hỏi cụ thể: codec nào giảm network đủ nhiều mà không làm CPU hoặc p99 latency vượt ngân sách?

### 13.1. Benchmark micro

Dùng JMH để đo riêng:

- Serialize object thành JSON/Avro/Protobuf.
- Deserialize byte array về object.
- Compress và decompress byte array.
- Allocation bytes/op và GC.

JMH xử lý warm-up, fork và đo lường tốt hơn vòng lặp thủ công. Giữ payload giống nhau giữa các phép đo và không đưa broker/network vào microbenchmark.

### 13.2. Benchmark end-to-end

Chạy ứng dụng với broker thật hoặc môi trường tương đương production. So sánh:

| Trục thử nghiệm | Giá trị gợi ý |
|---|---|
| Payload | 1 KB, 10 KB, 100 KB, 1 MB hoặc theo phân phối thật |
| Format | JSON, Avro, Protobuf nếu ứng dụng hỗ trợ |
| Codec | none, gzip, snappy, lz4, zstd theo binder |
| Producer batching | batch mặc định và một vài cấu hình linger/batch có kiểm soát |
| Concurrency | Một producer, nhiều producer, số consumer dự kiến |
| Broker | Cùng cấu hình replication, partition, storage và network |
| Thời gian | Đủ lâu để quan sát warm-up, steady state và GC |

Giữ nguyên số partition, replication factor, consumer concurrency, message rate và phần cứng khi so sánh codec. Nếu thay nhiều biến cùng lúc, không thể biết cải thiện đến từ đâu.

### 13.3. Chỉ số cần ghi

- Throughput message/s và MB/s.
- Producer send latency p50/p95/p99.
- Consumer end-to-end latency p50/p95/p99.
- CPU usage và CPU time theo process.
- Allocation rate, heap occupancy và GC pause.
- Network bytes in/out.
- Broker disk throughput và dung lượng log/queue.
- Compression ratio theo payload type và batch.
- Retry, timeout, record/message too large và error rate.

Không chỉ lấy trung bình. Một codec có throughput trung bình tốt nhưng p99 latency xấu có thể không phù hợp cho hệ thống cần phản hồi nhanh.

## 14. Compression level và kích thước batch

Một số codec có level điều chỉnh. Level cao thường tiêu thụ nhiều CPU hơn để tìm cách nén tốt hơn; lợi ích thêm có thể nhỏ dần. Không dùng level cao nhất mặc định.

Với Kafka, hiệu quả batch phụ thuộc số record trên mỗi partition và thời gian gom batch. Với Pulsar, batching và compression cũng tương tác; kiểm tra client version và producer configuration. Với RabbitMQ, application-level compression thường nén từng payload hoặc một đơn vị do ứng dụng định nghĩa, nên overhead của từng message có thể đáng kể với payload nhỏ.

Nguyên tắc thực hành:

1. Bắt đầu với cấu hình mặc định và đo baseline.
2. Thử codec ưu tiên tốc độ và codec ưu tiên ratio.
3. Chỉ tăng compression level nếu byte tiết kiệm thêm có giá trị rõ.
4. Điều chỉnh batching sau khi quan sát batch thực tế.
5. Kiểm tra latency và memory khi tải thấp, không chỉ khi tải cao.
6. Đánh giá consumer CPU vì giải nén cũng có chi phí.

## 15. Spring Cloud Stream content type và native encoding

Spring Cloud Stream có cơ chế message conversion dựa trên content type. Binder có thể chuyển payload object sang byte theo converter hoặc serializer native của middleware. Các thuộc tính useNativeEncoding và useNativeDecoding điều khiển việc dùng native encoding/decoding ở một số binder.

Khi dùng Avro/Protobuf hoặc payload byte đã nén:

- Xác định ai chịu trách nhiệm serialize và deserialize.
- Đặt content type phù hợp với contract của message.
- Nếu dùng native encoding, cấu hình serializer/deserializer ở binder/client.
- Nếu dùng application converter, bảo đảm converter xử lý đúng thứ tự compression và serialization.
- Không để một phía coi byte gzip là JSON text.
- Kiểm thử tương thích giữa producer và consumer ở các phiên bản triển khai khác nhau.

Tên property và hành vi native encoding phụ thuộc binder. Kafka, Rabbit và Pulsar không có cùng cấu hình serializer. Hãy kiểm tra tài liệu của binder cụ thể và không sao chép một property prefix từ Kafka sang Rabbit/Pulsar.

## 16. Compression, schema và versioning

Compression không thay thế schema governance. Một payload nén vẫn cần biết:

- Format sau giải nén là JSON, Avro hay Protobuf?
- Schema version hoặc schema ID nằm trong header, envelope hay payload?
- Codec là gzip, zstd hay loại nào?
- Consumer cũ có hỗ trợ codec đó không?
- Nếu codec không nhận diện được thì message được retry, quarantine hay DLQ?

Nếu dùng application-level compression, content-encoding phải là một phần của contract. Không tự suy luận codec từ byte đầu tiên hoặc thử lần lượt nhiều codec trong production; điều đó tạo hành vi mơ hồ và có thể tốn CPU.

Với rolling deployment, triển khai consumer hỗ trợ codec mới trước khi producer bắt đầu phát codec đó. Khi cần đổi codec, có thể dùng header/version rõ ràng hoặc tách topic/destination trong giai đoạn chuyển đổi. Giữ khả năng đọc dữ liệu cũ trong thời gian retention và retry.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CPU producer tăng sau khi bật compression | Codec/level quá nặng hoặc batch nhỏ | Đo CPU và ratio; thử codec nhanh hơn hoặc batch tốt hơn |
| CPU consumer tăng | Decompression hoặc deserialization nặng | Đo từng bước; giảm payload, đổi codec/format hoặc tăng capacity |
| Ratio gần 1,0 | Payload đã nén, mã hóa hoặc khó nén | Tắt compression cho binding đó nếu không có lợi ích |
| Publish latency tăng khi tải thấp | linger/batch làm record chờ gom | Giảm linger hoặc cấu hình riêng theo workload |
| Message bị broker từ chối vì quá lớn | Producer/broker/topic limit không tương thích | Đối chiếu từng giới hạn; giảm payload hoặc dùng object storage |
| Consumer không parse được payload | Codec/header hoặc serializer contract không khớp | Kiểm tra content type, content encoding và thứ tự decode |
| Payload nén lớn hơn payload gốc | Message quá nhỏ hoặc overhead codec | Không nén payload dưới ngưỡng có lợi |
| Heap/GC tăng mạnh | Nhiều byte array/object tạm hoặc payload được giữ lâu | Giảm copy, stream xử lý khi phù hợp, giới hạn buffer và backlog |
| Schema registry gây spike latency | Cache miss, registry cold start hoặc timeout | Kiểm tra cache, schema lifecycle và registry availability |
| Một consumer version không đọc được message mới | Codec hoặc schema mới chưa được hỗ trợ | Triển khai consumer tương thích trước producer |

## 18. Quy trình ra quyết định

1. Thu thập phân phối payload thực tế theo event type, không chỉ lấy một ví dụ.
2. Đo serialized bytes và số byte trên broker/network.
3. Đo CPU, allocation và latency của serializer/deserializer hiện tại.
4. Thử format khác nếu serialization chiếm tỷ trọng đáng kể.
5. Thử codec native của binder nếu hỗ trợ.
6. Với Rabbit hoặc contract dùng chung, đánh giá application-level compression và metadata.
7. Điều chỉnh batching chỉ sau khi có số liệu batch thực tế.
8. Kiểm tra các giới hạn producer, broker, consumer và broker storage.
9. Chạy end-to-end benchmark dưới tải tương đương production.
10. Chọn cấu hình theo SLO latency, throughput, CPU và chi phí lưu trữ.
11. Triển khai tương thích ngược và theo dõi error, retry, DLQ sau rollout.

## 19. Checklist trước khi tối ưu

- [ ] Đã xác định payload size trước và sau serialization.
- [ ] Đã đo compressed bytes và compression ratio theo từng event type.
- [ ] Đã biết bước serialize, compress, decompress hay deserialize đang tốn CPU nhất.
- [ ] Đã kiểm tra allocation rate, heap và GC.
- [ ] Đã so sánh codec trên dữ liệu đại diện.
- [ ] Đã kiểm tra batch size và linger với Kafka/Pulsar nếu dùng.
- [ ] Đã xác định compression nằm ở broker client hay application layer.
- [ ] Không nén hai lần cùng một payload nếu không có lợi ích đo được.
- [ ] Producer và consumer thống nhất content type, content encoding và schema version.
- [ ] Đã kiểm tra message/request/fetch limits ở cả producer, broker và consumer.
- [ ] Đã có phương án object storage hoặc chunking cho payload rất lớn.
- [ ] Đã chạy benchmark end-to-end và xem p95/p99, CPU, network, disk, GC.
- [ ] Đã kiểm thử consumer cũ khi producer đổi format hoặc codec.
- [ ] Đã có dashboard theo dõi payload size, error và latency sau triển khai.

## Tài liệu tham khảo chính thức

- [Apache Kafka Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs): compression.type, batch.size, linger.ms và max.request.size.
- [Apache Kafka Broker Configurations](https://kafka.apache.org/documentation/#brokerconfigs): message.max.bytes và cấu hình broker liên quan.
- [Apache Kafka Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs): fetch.max.bytes và max.partition.fetch.bytes.
- [Spring Cloud Stream Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html): producer/consumer binding và Kafka-specific properties.
- [RabbitMQ Publishers](https://www.rabbitmq.com/docs/publishers): publish, message body và publisher confirms.
- [RabbitMQ Limits](https://www.rabbitmq.com/docs/limits): giới hạn message và tài nguyên broker.
- [Apache Pulsar Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): producer, consumer, batching và message handling.
- [Apache Pulsar Client Configuration](https://pulsar.apache.org/api/client/): producer compression và client options.
- [Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/): phương pháp benchmark Java có warm-up và fork.
