# Chi phí serializer, payload và cấp phát đối tượng Java

Trong Kafka, hiệu năng của producer và consumer không chỉ phụ thuộc broker, số partition hay network. Mỗi record còn phải đi qua một chuỗi thao tác ở ứng dụng: tạo object nghiệp vụ, serialize thành byte, đưa vào producer buffer, truyền qua network, deserialize thành object mới rồi chuyển đổi và xử lý. Với payload lớn hoặc lưu lượng cao, CPU dành cho serializer, kích thước byte truyền đi, số object được cấp phát và áp lực garbage collection có thể trở thành nút thắt trước khi broker đạt giới hạn.

Bài này phân tích chi phí của serializer, thiết kế payload và object allocation trong Java. Ta sẽ so sánh JSON với các định dạng nhị phân, viết Jackson Serializer/Deserializer có thể tái sử dụng cấu hình, tránh cấp phát object không cần thiết, đo bằng JMH và benchmark qua Kafka thật. Mục tiêu là tối ưu dựa trên số đo: throughput, latency, bytes/record, CPU và allocation rate.

## 1. Đường đi của một record và các điểm phát sinh chi phí

Một record từ producer đến consumer thường đi qua các bước:

~~~mermaid
flowchart LR
    A[Domain object] --> B[Mapping / DTO]
    B --> C[Serializer]
    C --> D[byte[] key/value]
    D --> E[Producer accumulator]
    E --> F[Batch compression]
    F --> G[Network / broker log]
    G --> H[Consumer fetch]
    H --> I[Deserializer]
    I --> J[Java object graph]
    J --> K[Business processing]
~~~

Chi phí có thể xuất hiện ở mỗi bước:

| Bước | Chi phí chính | Dấu hiệu khi quá tốn kém |
|---|---|---|
| Tạo domain object/DTO | Object header, field, collection, String | Allocation rate cao |
| Mapping | Copy field, boxing/unboxing, conversion | CPU tăng, nhiều object trung gian |
| Serialize | Reflection, encoding, format conversion | Producer send latency tăng |
| Tạo byte[] | Cấp phát mảng và copy bytes | GC thường xuyên, heap pressure |
| Compression | CPU để nén/giải nén | CPU tăng nhưng network giảm |
| Network/disk | Số byte truyền và ghi | Throughput bị giới hạn bởi bandwidth hoặc I/O |
| Deserialize | Tạo object graph, parse, validation | Consumer poll tốn CPU |
| Business mapping | Copy DTO sang entity/map | Allocation lặp lại trên mỗi record |

Producer Java serialize key/value trong đường gọi send() trước khi record được thêm vào accumulator. Việc gửi lên broker là bất đồng bộ sau đó, nhưng serialization vẫn tiêu tốn CPU trên thread gọi send(). Vì vậy, serializer chậm có thể làm producer application thread bị nghẽn dù network và broker còn dư năng lực.

Consumer deserialize record trong quá trình poll/fetch. Một consumer nhận nhiều record mỗi lần poll có thể tạo ra lượng lớn object trong thời gian ngắn. Nếu object graph lớn và tồn tại lâu hơn một vài batch, garbage collector phải làm việc nhiều hơn.

## 2. Mô hình chi phí: CPU, bytes và allocation

Để phân tích, có thể tách tổng chi phí xử lý một record thành:

\[
T_{record} \approx T_{map} + T_{serialize} + T_{queue} + T_{network}
+ T_{deserialize} + T_{business}
\]

Đây là mô hình tư duy, không phải công thức latency cộng tuyến tính chính xác: các giai đoạn producer/network/consumer có thể chồng lấp và batch nhiều record cùng lúc.

Ba đại lượng cần đo:

| Đại lượng | Câu hỏi |
|---|---|
| CPU time/record | Serializer/deserializer tiêu tốn bao nhiêu CPU cho mỗi record? |
| Serialized bytes/record | Payload sau serialization lớn bao nhiêu byte? |
| Allocated bytes/record | Mỗi record tạo ra bao nhiêu byte object/mảng tạm? |

Ví dụ một ứng dụng phát 50.000 record/giây, mỗi record tạo thêm 4 KB object trung gian. Lượng allocation phát sinh là khoảng 200 MB/giây, chưa tính object gốc, byte[] đầu ra và các thành phần Kafka. Heap có thể vẫn đủ lớn nhưng GC phải thu gom liên tục.

Không tối ưu chỉ theo số object. Một object nhỏ, sống ngắn thường rẻ hơn một cấu trúc phức tạp được giữ lâu. Hãy đo allocated bytes/operation, GC pause, CPU và latency dưới tải thực tế.

## 3. Chọn định dạng payload

Serializer quyết định cách chuyển object Java thành byte[] và ảnh hưởng đến kích thước, CPU, khả năng tương thích schema và khả năng debug.

| Định dạng | Ưu điểm | Chi phí/đánh đổi | Phù hợp |
|---|---|---|---|
| JSON | Dễ đọc, dễ tích hợp, phổ biến | Field name lặp, text encoding, parse số/chuỗi, thường tạo object graph lớn | API/event đơn giản, cần interoperability |
| Avro | Binary compact, schema rõ, hỗ trợ schema evolution | Cần quản lý schema và serializer/deserializer tương thích | Event contract ổn định, nhiều consumer |
| Protocol Buffers | Binary compact, code generation, schema typed | Cần quản lý .proto và compatibility | Service-to-service, throughput cao |
| CBOR/MessagePack | Binary representation của dữ liệu kiểu JSON | Hệ sinh thái và schema governance tùy tổ chức | Muốn cấu trúc linh hoạt nhưng giảm text overhead |
| Custom binary | Có thể tối ưu rất sát workload | Tốn công versioning, compatibility, debug và bảo trì | Workload đặc thù, có benchmark chứng minh |

Không có định dạng luôn nhanh nhất. JSON với payload nhỏ, schema gọn và Jackson cấu hình tốt có thể đáp ứng tải cao. Avro hoặc Protobuf có thể giảm bytes và parse cost, nhưng phải tính cả schema registry, code generation, schema evolution và chi phí vận hành.

Khi so sánh, dùng cùng một tập dữ liệu và cùng semantics. Đo cả serialize/deserialize CPU, bytes trước và sau compression, p95/p99 end-to-end latency và allocation rate.

## 4. Thiết kế payload nhỏ, ổn định và dễ serialize

Payload càng lớn thì càng tốn memory, network, disk và thường tăng thời gian serialize/deserialize. Một event không nên là bản sao nguyên vẹn của database entity.

Payload dư thừa:

~~~json
{
  "eventId": "evt-9001",
  "eventName": "OrderPlacedEvent",
  "createdAt": "2026-11-20T10:15:30.123456Z",
  "order": {
    "id": "ord-9001",
    "status": "PLACED",
    "statusDescription": "The order has been placed successfully",
    "customer": {
      "id": "cus-10",
      "displayName": "Customer 10",
      "email": "customer@example.test"
    },
    "items": [
      {
        "productId": "p-1",
        "quantity": 2,
        "unitPrice": 100000,
        "currency": "VND",
        "productDescription": "Long product description repeated in every event"
      }
    ]
  }
}
~~~

Payload tập trung vào dữ liệu cần cho consumer:

~~~json
{
  "eventId": "evt-9001",
  "eventType": "OrderPlaced",
  "occurredAt": 1795169730123,
  "orderId": "ord-9001",
  "customerRef": "cus-10",
  "items": [
    {"productId": "p-1", "quantity": 2, "unitPriceMinor": 100000}
  ],
  "currency": "VND"
}
~~~

Một số nguyên tắc:

- Không lặp lại mô tả sản phẩm, tên enum dạng câu dài hoặc dữ liệu profile nếu consumer có thể tra cứu bằng ID.
- Không serialize field null nếu schema và consumer cho phép bỏ qua.
- Không gửi cùng một thông tin ở payload, key và headers nhiều lần.
- Dùng timestamp số hoặc định dạng thời gian thống nhất nếu phù hợp hợp đồng; đừng chuyển đổi qua nhiều String trung gian.
- Với tiền, chọn kiểu dữ liệu biểu diễn chính xác. Số nguyên theo minor unit phù hợp khi currency và quy tắc làm tròn được xác định; BigDecimal phù hợp khi cần scale/precision linh hoạt.
- Tránh dùng Map<String,Object> cho event có schema cố định nếu DTO typed giải quyết được.
- Đặt giới hạn kích thước payload và kiểm tra ở producer trước khi gửi.

Không rút gọn tên field đến mức làm schema khó hiểu hoặc khó nâng cấp. Tiết kiệm vài byte không đáng đổi lấy contract mơ hồ.

## 5. Payload nhị phân và Base64

Nếu dữ liệu gốc là binary, hãy cân nhắc gửi trực tiếp bytes thay vì chuyển thành Base64 bên trong JSON.

Base64 biến mỗi 3 byte đầu vào thành 4 ký tự, nên kích thước tăng khoảng một phần ba, chưa tính JSON quotes và field name. Ví dụ ảnh 3 MB có thể thành khoảng 4 MB trước compression.

| Cách gửi | Ưu điểm | Đánh đổi |
|---|---|---|
| Base64 trong JSON | Dễ tích hợp với JSON API | Tăng payload, encode/decode thêm, tạo String lớn |
| byte[] làm value | Không cần Base64 | Consumer phải biết content type/schema |
| Object storage + event chứa reference | Kafka record nhỏ, phù hợp file lớn | Thêm dependency vào object storage và lifecycle của object |

Với file lớn, thường nên lưu file ở object storage và phát event chứa object key, checksum, content type và size. Consumer tải file bằng credential riêng. Không mặc định đẩy file lớn qua Kafka chỉ vì Kafka hỗ trợ byte[].

## 6. Jackson ObjectMapper: tạo một lần, cấu hình trước khi dùng

Một lỗi phổ biến là tạo ObjectMapper cho từng record:

~~~java
public byte[] serialize(OrderEvent event) throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.writeValueAsBytes(event);
}
~~~

ObjectMapper có cấu hình, serializer cache và metadata reflection. Tạo mới cho từng record làm tăng CPU và allocation không cần thiết.

Tạo ObjectMapper một lần khi khởi tạo ứng dụng, đăng ký module/cấu hình xong rồi tái sử dụng. ObjectMapper thread-safe sau khi hoàn tất cấu hình; ObjectWriter và ObjectReader cũng immutable/thread-safe và phù hợp để dùng lại.

~~~java
public final class OrderJsonCodec {
    private final ObjectMapper mapper;
    private final ObjectWriter writer;
    private final ObjectReader reader;

    public OrderJsonCodec() {
        this.mapper = new ObjectMapper();
        // Đăng ký module và cấu hình trước khi tạo writer/reader.
        this.writer = mapper.writerFor(OrderEvent.class);
        this.reader = mapper.readerFor(OrderEvent.class);
    }

    public byte[] serialize(OrderEvent event) throws JsonProcessingException {
        return writer.writeValueAsBytes(event);
    }

    public OrderEvent deserialize(byte[] bytes) throws IOException {
        return reader.readValue(bytes);
    }
}
~~~

Nếu ứng dụng dùng Java Time, đăng ký JavaTimeModule và thống nhất format trước khi tạo ObjectWriter/Reader. Không thay đổi ObjectMapper sau khi nhiều thread đã bắt đầu sử dụng.

## 7. Viết Kafka Serializer dùng lại Jackson writer

Kafka Serializer có contract trả về byte[]. Ví dụ sau tạo ObjectWriter một lần trong constructor và dùng lại cho mỗi record:

~~~java
package com.example.orders.kafka;

import com.example.orders.OrderEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Serializer;

public final class OrderEventSerializer implements Serializer<OrderEvent> {
    private final ObjectWriter writer;

    public OrderEventSerializer() {
        ObjectMapper mapper = new ObjectMapper();
        this.writer = mapper.writerFor(OrderEvent.class);
    }

    @Override
    public byte[] serialize(String topic, OrderEvent data) {
        if (data == null) {
            return null;
        }
        try {
            return writer.writeValueAsBytes(data);
        } catch (JsonProcessingException exception) {
            throw new SerializationException(
                    "Cannot serialize OrderEvent for topic " + topic,
                    exception);
        }
    }
}
~~~

ObjectWriter có thể được chia sẻ giữa nhiều thread. Không thêm mutable buffer dùng chung vào serializer nếu chưa thiết kế đồng bộ và ownership rõ ràng.

Kafka producer có thể gọi serializer từ nhiều thread ứng dụng vì KafkaProducer hỗ trợ concurrent send. Serializer tùy chỉnh phải an toàn khi được gọi đồng thời; tránh lưu trạng thái record hiện tại trong field instance.

## 8. Viết Deserializer và giảm object trung gian

Deserializer cũng nên tái sử dụng ObjectReader:

~~~java
package com.example.orders.kafka;

import com.example.orders.OrderEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import org.apache.kafka.common.errors.SerializationException;
import org.apache.kafka.common.serialization.Deserializer;

import java.io.IOException;

public final class OrderEventDeserializer
        implements Deserializer<OrderEvent> {

    private final ObjectReader reader;

    public OrderEventDeserializer() {
        ObjectMapper mapper = new ObjectMapper();
        this.reader = mapper.readerFor(OrderEvent.class);
    }

    @Override
    public OrderEvent deserialize(String topic, byte[] data) {
        if (data == null) {
            return null;
        }
        try {
            return reader.readValue(data);
        } catch (IOException exception) {
            throw new SerializationException(
                    "Cannot deserialize OrderEvent from topic " + topic,
                    exception);
        }
    }
}
~~~

Deserializer phải xử lý null value đúng semantics Kafka: null có thể biểu diễn tombstone trong compacted topic. Đừng tự biến null thành object rỗng nếu ứng dụng cần phân biệt tombstone với event có payload rỗng.

Tránh parse JSON thành JsonNode hoặc Map rồi mới map sang DTO nếu consumer luôn cần cùng một kiểu event. Parse trực tiếp vào DTO giúp giảm một tầng object graph và bước mapping. Với payload linh hoạt thực sự, JsonNode có thể hợp lý; hãy đo trước khi thay đổi.

## 9. Object allocation trong Java

Mỗi record có thể tạo ra nhiều object:

- Event DTO và nested DTO.
- String cho field text.
- List/Map và node cho collection.
- Wrapper object do boxing như Integer, Long, Boolean.
- byte[] từ serializer.
- ByteArrayOutputStream hoặc buffer tạm.
- Object tạo trong mapper/converter.
- Exception và stack trace khi xử lý lỗi.

Một payload JSON lồng nhiều tầng có thể tạo hàng chục hoặc hàng trăm object tùy số field và collection. Khi xử lý 100.000 record/giây, một khác biệt nhỏ trên mỗi record có thể nhân lên thành hàng triệu allocation mỗi giây.

Ví dụ mapping tốn object:

~~~java
Map<String, Object> values = objectMapper.convertValue(
        event, new TypeReference<Map<String, Object>>() {});
OrderCommand command = objectMapper.convertValue(values, OrderCommand.class);
~~~

Nếu chỉ cần chuyển event sang command, map trực tiếp:

~~~java
OrderCommand command = new OrderCommand(
        event.orderId(),
        event.customerRef(),
        event.amountMinor(),
        event.currency());
~~~

Không cần loại bỏ mọi object. DTO typed giúp contract rõ và thường rẻ hơn nhiều lớp Map/JsonNode. Tối ưu chỉ những đường nóng có profile chứng minh.

## 10. Primitive, wrapper và collection

Primitive như long, int, boolean tránh một wrapper object trong nhiều trường hợp. Tuy nhiên, primitive không thể biểu diễn null. Nếu null mang ý nghĩa nghiệp vụ, dùng wrapper hoặc Optional theo đúng contract.

| Kiểu | Đặc điểm |
|---|---|
| long | Không boxing khi dùng trong field/biến primitive; không biểu diễn null |
| Long | Có thể null; có thể phát sinh boxing/unboxing |
| BigDecimal | Chính xác cho số thập phân; object immutable, phép toán tạo kết quả mới |
| String | Immutable; substring/concat/encoding có thể tạo thêm dữ liệu hoặc object |
| List<T> | Tạo collection và backing array; cần capacity phù hợp |
| Map<String,Object> | Linh hoạt nhưng thường tạo nhiều entry, node, wrapper và object giá trị |

Với amount, nếu domain dùng một đơn vị minor cố định cho từng currency, long có thể giảm object và serialize gọn. Không dùng double cho tiền vì sai số floating point; nếu cần scale linh hoạt hoặc phép tính decimal chính xác, BigDecimal là lựa chọn phù hợp.

Tránh tạo collection tạm chỉ để chuyển đổi một vài field. Nếu phải tạo list mới, cấp capacity gần với kích thước dự kiến để giảm resize/copy; đừng giữ collection dùng chung có thể bị sửa bởi thread khác.

## 11. Không tái sử dụng byte[] đầu ra một cách tùy tiện

Kafka Serializer trả về byte[]. Trong KafkaProducer, serialize key/value và append record vào accumulator diễn ra trong đường gọi send(); việc truyền batch qua network mới bất đồng bộ. Tuy vậy, producer có thể được gọi đồng thời từ nhiều thread, nên một mutable buffer dùng chung trong serializer có thể bị một lần serialize ghi đè trong khi lần gửi khác vẫn đang dùng nó. Ví dụ sau không an toàn:

~~~java
private final byte[] reusable = new byte[4096];

byte[] serialize(Event event) {
    writeInto(reusable, event);
    return reusable;
}
~~~

Nếu hai lời gọi serialize/send chồng lấp, lần serialize tiếp theo có thể ghi đè mảng trong lúc lần gửi trước đang tính partition hoặc append record. Kết quả có thể là payload bị trộn hoặc sai nội dung.

Quy tắc:

- Không trả về cùng một mutable byte[] cho các lời gọi serialize/send có thể chồng lấp.
- Không sửa mảng trong khi producer đang tính partition hoặc append record vào accumulator.
- Nếu dùng buffer pool, phải có ownership/lifecycle rõ ràng và chỉ tái sử dụng sau khi lời gọi serialize/send đã hoàn tất việc append; Kafka Serializer API không cung cấp callback riêng để trả từng byte[] về pool.
- Ưu tiên giảm object trung gian và tái sử dụng writer/parser trước khi tự triển khai buffer pool.

Với standard Kafka Serializer contract, một byte[] kết quả cho mỗi key/value serialization là chi phí thường phải có. Mục tiêu thực tế là giảm copy và object tạm trước khi tạo mảng đầu ra. Tránh khẳng định rằng mạng đã gửi xong khi send() trả về: send() trả Future sau khi append, còn delivery/acknowledgement hoàn tất sau đó.

## 12. String encoding và chi phí chuyển đổi

Kafka lưu byte, không lưu String. StringSerializer chuyển String thành byte[] theo UTF-8. Nếu dữ liệu đã là binary hoặc đã được encode ở tầng trước, chuyển thành String rồi serialize lại sẽ tạo thêm bản sao.

Ví dụ chuỗi chuyển đổi không cần thiết:

~~~java
String json = objectMapper.writeValueAsString(event);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
~~~

Có thể ghi trực tiếp thành byte[]:

~~~java
byte[] bytes = objectWriter.writeValueAsBytes(event);
~~~

Cách thứ hai tránh tạo String JSON trung gian. Tuy vậy, nó vẫn cấp phát byte[] đầu ra và các object nội bộ của serializer; cần benchmark thay vì giả định allocation bằng không.

## 13. Compression và kích thước record batch

Kafka nén record batch ở producer khi cấu hình compression.type. Các lựa chọn phổ biến gồm gzip, snappy, lz4, zstd và none (tùy client/broker version và thư viện được đóng gói).

| Thuật toán | Xu hướng | Đánh đổi |
|---|---|---|
| none | Không tốn CPU nén | Network/disk dùng nhiều bytes hơn |
| gzip | Tỷ lệ nén thường tốt | CPU nén/giải nén có thể cao |
| snappy | Ưu tiên tốc độ | Tỷ lệ nén thường thấp hơn gzip |
| lz4 | Tốc độ cao, phù hợp throughput | Tỷ lệ nén phụ thuộc payload |
| zstd | Có thể cân bằng tốc độ và tỷ lệ nén tốt | Cần benchmark theo level và workload |

Compression hoạt động trên batch, nên hiệu quả phụ thuộc kích thước batch và tính lặp của dữ liệu. JSON có field name lặp lại thường nén tốt; payload đã nén (JPEG, ZIP, gzip) có thể gần như không giảm thêm nhưng vẫn tốn CPU.

Ví dụ:

~~~properties
compression.type=lz4
batch.size=65536
linger.ms=5
~~~

batch.size là mục tiêu kích thước batch theo partition; linger.ms cho producer một khoảng thời gian ngắn để gom record trước khi gửi. Batch lớn hơn có thể tăng hiệu quả compression và records/request nhưng làm tăng latency chờ và memory. Chọn bằng benchmark và SLA, không sao chép nguyên giá trị ví dụ.

## 14. Payload lớn và giới hạn message

Payload lớn ảnh hưởng nhiều lớp:

- Serializer cần nhiều CPU và byte[] lớn.
- Producer accumulator cần nhiều memory.
- Request/batch lớn có thể giảm số request nhưng tăng latency và memory pressure.
- Broker phải nhận, replicate và ghi nhiều bytes.
- Consumer fetch nhiều bytes và deserialize lâu hơn.
- Retry/DLT có thể sao chép payload lớn thêm nhiều lần.

Các cấu hình kích thước cần được xem đồng bộ:

| Cấu hình | Phạm vi |
|---|---|
| max.request.size | Giới hạn request producer có thể gửi |
| message.max.bytes | Giới hạn record batch broker chấp nhận ở cấp broker |
| max.message.bytes | Giới hạn record batch theo topic, có thể override broker |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch cho một partition ở consumer |
| fetch.max.bytes | Giới hạn dữ liệu fetch tổng thể cho một request |

Tên và quan hệ chi tiết cần đối chiếu đúng phiên bản Kafka đang chạy. Không tăng các giới hạn chỉ để làm một record lớn gửi được; việc tăng đồng loạt có thể làm broker và consumer chịu áp lực memory lớn. Với file lớn, cân nhắc object storage và event reference.

## 15. Producer batching không thay thế tối ưu serializer

Producer batching giảm overhead request/network bằng cách gom nhiều record cùng partition. Nó không làm cho serializer rẻ hơn: mỗi record vẫn phải serialize thành byte[] trước khi được đưa vào batch.

Ví dụ cấu hình:

~~~java
Properties properties = new Properties();
properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        OrderEventSerializer.class.getName());
properties.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
properties.put(ProducerConfig.BATCH_SIZE_CONFIG, 64 * 1024);
properties.put(ProducerConfig.LINGER_MS_CONFIG, 5);
properties.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 64L * 1024 * 1024);
~~~

Nếu serializer dùng 70% CPU, tăng batch size không giải quyết nút thắt CPU đó. Ngược lại, nếu serializer nhanh nhưng records/request thấp và network overhead cao, batching có thể giúp nhiều hơn. Đo từng phần để chọn đúng hướng.

## 16. Consumer: giảm deserialize và mapping không cần thiết

Consumer thường cần parse payload thành DTO rồi gọi business logic. Các cách giảm chi phí:

1. Chỉ subscribe topic cần thiết và dùng DTO đúng schema.
2. Tránh deserialize thành Map rồi chuyển qua nhiều lớp DTO.
3. Không gọi toString() hoặc serialize lại payload chỉ để log.
4. Tránh copy byte[]/String nếu chỉ đọc dữ liệu.
5. Giữ business logic xử lý trực tiếp field cần thiết; chỉ map sang entity khi cần ghi database.
6. Dùng batch listener khi nghiệp vụ có thể xử lý theo batch và đo hiệu quả thực tế.
7. Giới hạn số record mỗi poll để tránh tạo object graph quá lớn cùng lúc.

Không giữ ConsumerRecord hoặc payload object trong queue nội bộ vô hạn. Nếu cần đẩy sang executor khác, phải giới hạn queue và xác định ownership, backpressure, retry semantics và thứ tự xử lý.

## 17. Benchmark serializer bằng JMH

Microbenchmark giúp so sánh chi phí serialize trong JVM mà không bị network/broker chi phối. Dùng cùng một event đại diện, cùng cấu hình Jackson và cùng JVM flags.

Dependency JMH cho Maven:

~~~xml
<dependency>
    <groupId>org.openjdk.jmh</groupId>
    <artifactId>jmh-core</artifactId>
    <version>1.37</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.openjdk.jmh</groupId>
    <artifactId>jmh-generator-annprocess</artifactId>
    <version>1.37</version>
    <scope>test</scope>
</dependency>
~~~

Ví dụ benchmark Jackson:

~~~java
package com.example.benchmark;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import org.openjdk.jmh.annotations.*;

import java.util.concurrent.TimeUnit;

record OrderEvent(
        String eventId,
        String orderId,
        String customerRef,
        long amountMinor,
        String currency) {
}

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
@State(Scope.Thread)
public class OrderSerializerBenchmark {
    private ObjectWriter writer;
    private ObjectReader reader;
    private OrderEvent event;
    private byte[] payload;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        writer = mapper.writerFor(OrderEvent.class);
        reader = mapper.readerFor(OrderEvent.class);
        event = new OrderEvent(
                "evt-10001",
                "ord-10001",
                "cus-100",
                125000L,
                "VND");
        payload = writer.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] jacksonSerialize() throws Exception {
        return writer.writeValueAsBytes(event);
    }

    @Benchmark
    public OrderEvent jacksonDeserialize() throws Exception {
        return reader.readValue(payload);
    }

    @Benchmark
    public byte[] jacksonSerializeWithMapperPerCall() throws Exception {
        return new ObjectMapper().writeValueAsBytes(event);
    }
}
~~~

Chạy JMH với GC profiler:

~~~bash
java -jar target/benchmarks.jar OrderSerializerBenchmark -prof gc
~~~

Lệnh trên giả định project đã đóng gói JMH benchmark jar bằng JMH Maven archetype hoặc build plugin phù hợp; chỉ thêm hai dependency chưa tự tạo executable benchmark jar.

Các kết quả nên xem:

- thrpt: số operation/giây.
- gc.alloc.rate.norm: byte được cấp phát cho mỗi operation.
- gc.alloc.rate: allocation rate theo thời gian.
- gc.count và gc.time: số lần và thời gian GC.

Benchmark jacksonSerializeWithMapperPerCall là baseline cố ý kém hiệu quả để thấy chi phí tạo mapper; không dùng pattern đó trong ứng dụng. Để so sánh JSON, Avro và Protobuf, tạo các benchmark method riêng nhưng dùng cùng logical event và dữ liệu. Đo cả serializer lẫn deserializer; một format serialize nhanh nhưng deserialize chậm có thể không phù hợp với workload có nhiều consumer.

JMH chỉ đo phần JVM code trong điều kiện benchmark. Nó không phản ánh đầy đủ batching, compression, network, broker replication, consumer lag hay end-to-end latency.

## 18. Benchmark end-to-end qua Kafka

Sau microbenchmark, chạy integration benchmark với broker thật hoặc môi trường staging tương đương production.

Giữ cố định:

- Số broker, partition, replication factor và ISR.
- Số producer/consumer instance và thread.
- Payload dataset, kích thước và phân bố field.
- Compression type, batch.size và linger.ms.
- Ack mode, idempotence và consumer isolation level.
- JVM version, heap, GC và CPU quota.

Thay đổi từng biến một: format, payload shape, compression hoặc serializer implementation. Chạy đủ thời gian warm-up và đo ổn định; lặp lại nhiều lần để tránh kết luận từ một lần chạy.

Các metric hữu ích:

| Nhóm | Metric/đại lượng |
|---|---|
| Producer | record-size-avg, record-size-max, compression-rate-avg |
| Producer batching | records-per-request-avg, batch-size-avg, record-queue-time-avg |
| Producer buffer | buffer-available-bytes, bufferpool-wait-time |
| Producer request | request-latency-avg, request-size-avg, record send rate |
| Consumer | bytes-consumed-rate, records-consumed-rate, fetch-latency-avg |
| Runtime | CPU utilization, heap usage, allocation rate, GC pause |
| Application | serialize/deserialize duration, p50/p95/p99 latency, errors |

Metric name có thể thay đổi theo Kafka client version và reporter. Dùng JMX/metrics documentation đúng version, và bổ sung timer/histogram ở tầng ứng dụng nếu cần tách riêng serializer.

Khi cần tìm allocation site trong ứng dụng đang chạy, có thể dùng Java Flight Recorder:

~~~bash
java -XX:StartFlightRecording=filename=kafka-producer.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Mở file JFR bằng JDK Mission Control, xem Allocation in New TLAB/Outside TLAB, CPU samples và GC pauses. JFR có overhead; dùng profile phù hợp và tránh bật cấu hình nặng liên tục trên production nếu chưa đánh giá.

## 19. Đọc kết quả và chọn tối ưu

| Quan sát | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Producer CPU cao, network thấp | Serializer/mapping tốn CPU | JFR/async-profiler, JMH, bỏ object trung gian |
| Bytes/record cao | Payload dư thừa hoặc text encoding | Rút gọn schema, bỏ Base64, thử binary format |
| Compression ratio tốt nhưng CPU tăng mạnh | Compression level/algorithm quá đắt | So sánh lz4/zstd/snappy và none |
| Allocation rate cao, GC pause tăng | Object graph, byte[] và mapping tạm | Reuse ObjectWriter/Reader, DTO typed, giảm copy |
| Producer buffer wait tăng | Producer gửi nhanh hơn broker/network hoặc batch giữ quá lâu | Kiểm tra broker throughput, linger, buffer memory và backpressure |
| Records/request thấp | Batch chưa đủ đầy hoặc phân tán nhiều partition | Xem linger, batch size và partition distribution |
| Consumer CPU cao | Deserialize/mapping/business logic | Profile từng giai đoạn, giảm parse/copy |
| p99 cao nhưng average tốt | Payload lớn, GC pause hoặc record outlier | Xem histogram theo payload size, GC và slow record |

Không đổi đồng thời serializer, compression, batch size và partition count. Khi nhiều biến thay đổi, rất khó biết cải thiện đến từ đâu và dễ tạo cấu hình tốt trong lab nhưng xấu khi tải thay đổi.

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả |
|---|---|
| Tạo ObjectMapper cho từng record | Tốn CPU, object và cache warm-up |
| Convert DTO → Map → DTO | Tạo nhiều object graph và copy |
| JSON chứa file Base64 lớn | Payload tăng khoảng 33% trước compression |
| Dùng double cho tiền | Sai số biểu diễn thập phân |
| Dùng một mutable byte[] chung cho các lần serialize đồng thời | Một lần serialize có thể ghi đè dữ liệu của lần khác |
| Chọn Avro/Protobuf chỉ vì nghe nói nhanh | Có thể tăng complexity mà không cải thiện workload |
| Bật gzip cho mọi payload | CPU có thể trở thành nút thắt |
| Tăng max.request.size để gửi file lớn | Tăng memory pressure và thời gian xử lý |
| Đo chỉ serializer, kết luận end-to-end | Bỏ qua compression, network, broker và consumer |
| Benchmark bằng một payload nhỏ duy nhất | Không đại diện dữ liệu thực tế và outlier |

## 21. Lab: đo serializer và allocation

### Bước 1: chuẩn bị dataset

Tạo ít nhất ba nhóm event: nhỏ (vài trăm byte), trung bình (1–4 KB) và lớn (từ vài chục KB). Dùng phân bố field giống production, gồm chuỗi ASCII, Unicode, collection và trường optional.

### Bước 2: tạo baseline JSON

Dùng Jackson ObjectMapper/ObjectWriter tái sử dụng. Đo serialize và deserialize bằng JMH, ghi throughput, bytes/op và allocation/op. Thêm benchmark đối chứng tạo ObjectMapper cho từng operation để thấy chi phí cấu hình/cấp phát.

### Bước 3: thử format khác

Serialize cùng event bằng Avro hoặc Protobuf. Đo bytes trước compression và CPU serialize/deserialize. Xác định rõ schema version và compatibility policy.

### Bước 4: thử payload design

So sánh payload đầy đủ với payload tối giản; so sánh nested DTO với Map<String,Object>; so sánh binary bytes với Base64 JSON. Ghi kích thước và allocation.

### Bước 5: thử compression

Chạy none, lz4, zstd và gzip với cùng dataset, batch size và linger. Đo compression ratio, producer CPU, network bytes và p95/p99 latency.

### Bước 6: benchmark end-to-end

Gửi dữ liệu vào topic có cấu hình partition/replication tương đương môi trường mục tiêu. Chạy consumer deserialize và xử lý cùng một logic. Theo dõi producer metrics, consumer rate/lag, JVM allocation và GC.

### Bước 7: ghi kết luận

Tạo bảng kết quả:

| Phương án | Bytes/record | Serialize ops/s | Deserialize ops/s | Alloc bytes/op | p99 end-to-end |
|---|---:|---:|---:|---:|---:|
| JSON baseline | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| JSON payload tối giản | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Avro/Protobuf | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| JSON + compression | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Không điền số giả định vào báo cáo. Ghi lại JVM, Kafka version, serializer version, phần cứng, dataset và cấu hình để người khác có thể lặp lại phép đo.

## 22. Checklist trước khi đưa serializer vào production

- Event schema chỉ chứa dữ liệu consumer cần.
- Serializer/deserializer dùng cấu hình immutable được khởi tạo một lần.
- Serializer thread-safe nếu được nhiều producer thread gọi đồng thời.
- Không dùng chung mutable byte[] cho các lời gọi serialize có thể chồng lấp.
- Không có DTO → Map → DTO conversion không cần thiết.
- Binary payload không bị Base64 hóa nếu không có lý do interoperability.
- Compression được benchmark với payload thực tế.
- batch.size, linger.ms và compression.type được đo cùng nhau.
- Giới hạn message/request/fetch phù hợp với kích thước record và memory.
- Có kiểm tra schema compatibility và versioning.
- Có metric serialize/deserialize duration, bytes/record và allocation rate.
- Benchmark có payload nhỏ, trung bình, lớn và outlier.
- JMH và end-to-end benchmark được dùng cho đúng mục đích.
- p95/p99 latency, CPU, GC và throughput đều đạt SLA.

## 23. Ghi nhớ

| Khái niệm | Cần nhớ |
|---|---|
| Serializer | Chuyển object thành byte[]; CPU của nó nằm trên đường gọi producer send |
| Deserializer | Tạo object graph từ byte[]; ảnh hưởng CPU và allocation của consumer |
| Payload size | Tác động memory, network, disk, replication và latency |
| JSON | Dễ đọc, nhưng field text và parse có overhead |
| Avro/Protobuf | Binary typed, cần schema/version governance |
| ObjectMapper/ObjectWriter | Khởi tạo/cấu hình một lần rồi tái sử dụng |
| Object allocation | Tích lũy thành allocation rate và áp lực GC |
| byte[] output | Tránh dùng chung mutable array giữa các lời gọi serialize đồng thời |
| Compression | Nén theo batch; đánh đổi CPU với network/disk |
| JMH | Đo code serializer/deserializer trong JVM |
| End-to-end benchmark | Đo producer, broker, network, consumer và latency |

Tối ưu serializer và payload bắt đầu từ việc hiểu mỗi record tạo ra bao nhiêu byte, bao nhiêu object và tiêu tốn bao nhiêu CPU. Hãy giảm dữ liệu dư thừa, tái sử dụng writer/reader, tránh mapping trung gian và chọn format/compression bằng benchmark. Giữ ownership của byte[] rõ ràng để tối ưu allocation không làm hỏng record bất đồng bộ.

## 24. Tài liệu tham khảo

- Apache Kafka – [Producer Configs](https://kafka.apache.org/42/configuration/producer-configs/)
- Apache Kafka – [Consumer Configs](https://kafka.apache.org/42/configuration/consumer-configs/)
- Apache Kafka – [Kafka Producer API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- Apache Kafka – [Serializer API](https://kafka.apache.org/42/javadoc/org/apache/kafka/common/serialization/Serializer.html)
- Apache Kafka – [Metrics](https://kafka.apache.org/42/operations/monitoring/)
- Jackson – [ObjectMapper Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- OpenJDK – [JMH](https://github.com/openjdk/jmh)
