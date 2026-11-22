# Đánh giá kích thước, tốc độ và khả năng quan sát dữ liệu

## 1. Vì sao cần đánh giá định dạng nhị phân?

JSON là định dạng văn bản dễ đọc, dễ debug và được hỗ trợ rộng rãi. Tuy nhiên, trong hệ thống trao đổi dữ liệu với lưu lượng lớn, JSON có thể tạo payload tương đối dài vì phải mang tên field, dấu ngoặc, dấu phẩy và biểu diễn số dưới dạng văn bản.

Jackson hỗ trợ các định dạng nhị phân như Smile và CBOR. Chúng biểu diễn dữ liệu theo token hoặc kiểu nhị phân, nhờ đó có thể giảm số byte truyền đi và giảm chi phí parse/format trong một số workload.

Nhưng việc chuyển sang binary không tự động làm hệ thống nhanh hơn hoặc rẻ hơn. Kết quả phụ thuộc vào:

- Hình dạng dữ liệu: object có nhiều field, array lớn, string dài hay message nhỏ.
- Tần suất lặp lại tên field và giá trị string.
- Cách mapper cấu hình serializer/deserializer.
- Nén ở tầng HTTP, message broker hoặc storage.
- CPU, allocation, garbage collection và tốc độ mạng.
- Cách đội vận hành cần xem log, kiểm tra message và điều tra sự cố.

Đánh giá định dạng cần xem đồng thời ba khía cạnh: **kích thước**, **hiệu năng** và **khả năng quan sát**. Một định dạng tiết kiệm byte nhưng khó debug hoặc không tương thích với consumer hiện có có thể làm tổng chi phí vận hành tăng lên.

## 2. Những định dạng cần so sánh

Trong hệ sinh thái Jackson, hai định dạng nhị phân thường được cân nhắc là Smile và CBOR.

| Định dạng | Đặc điểm | Điểm cần cân nhắc |
|---|---|---|
| JSON | Văn bản, dễ đọc, phổ biến | Tên field và dấu cú pháp làm payload dài hơn; cần parse text |
| Smile | Định dạng nhị phân hướng token, được thiết kế cho dữ liệu kiểu JSON và hệ sinh thái Jackson | Tích hợp thuận tiện với Jackson; công cụ ngoài hệ sinh thái có thể ít phổ biến hơn |
| CBOR | Định dạng nhị phân được chuẩn hóa, biểu diễn map, array, scalar và byte string | Có hệ sinh thái ngoài Jackson; cần kiểm tra mức tương thích giữa các implementation |

Smile được thiết kế để mã hóa dữ liệu kiểu JSON hiệu quả. Nó có thể tận dụng các cơ chế như biểu diễn token nhị phân và tham chiếu tên/string trong phạm vi tài liệu để giảm lặp lại. Đây là lợi thế khi nhiều object có cùng tên field hoặc giá trị text được lặp lại.

CBOR (Concise Binary Object Representation) là một định dạng nhị phân độc lập với Jackson. Nó có kiểu biểu diễn cho integer, floating-point, byte string, text string, array, map, boolean và null; CBOR còn có các tính năng như tag để biểu diễn dữ liệu có ngữ nghĩa mở rộng. Khi dùng Jackson, cần nhớ rằng mapping cụ thể vẫn phụ thuộc cách Jackson Databind và CBOR module ánh xạ kiểu Java.

JSON có lợi thế lớn về khả năng đọc bằng mắt và khả năng tích hợp. Smile có thể phù hợp với các hệ thống Java/Jackson cần payload gọn và tích hợp cùng mapper. CBOR phù hợp khi cần một định dạng nhị phân có chuẩn độc lập và có consumer ở nhiều ngôn ngữ.

Không nên chọn chỉ dựa trên tên gọi “binary”. Hãy kiểm tra thư viện ở mọi phía giao tiếp, kiểu dữ liệu thực tế và công cụ vận hành.

## 3. Binary không đồng nghĩa với luôn nhỏ hơn

Định dạng nhị phân thường tránh phải viết số và cấu trúc dưới dạng text. Ví dụ, số nguyên có thể được mã hóa bằng một hoặc vài byte thay vì chuỗi ký tự. Tên field có thể được mã hóa hiệu quả hơn hoặc tái sử dụng trong một tài liệu.

Tuy nhiên, binary có overhead riêng:

- Header hoặc marker nhận diện định dạng.
- Metadata cho một số kiểu hoặc cấu trúc.
- Chi phí biểu diễn tên field nếu chúng không được rút gọn hoặc tái sử dụng.
- Một số payload nhỏ có thể không đủ lớn để bù overhead ban đầu.

Với một message rất nhỏ, JSON có thể ngắn hơn một định dạng binary cụ thể. Với nhiều object lặp lại cùng schema, binary có thể tiết kiệm đáng kể hơn. Kết quả phải được đo bằng dữ liệu đại diện.

Ví dụ JSON:

~~~json
{
  "eventId": "E-100",
  "eventType": "order-created",
  "quantity": 12,
  "active": true
}
~~~

Nếu payload chứa hàng nghìn event có cùng các tên eventId, eventType, quantity và active, chi phí lặp lại tên field trong JSON sẽ xuất hiện ở từng object. Smile hoặc CBOR có thể mã hóa cấu trúc hiệu quả hơn tùy cách triển khai và payload.

Nếu JSON được nén bằng gzip hoặc Brotli, tên field và dấu cú pháp lặp lại có thể nén rất tốt. Vì vậy, cần so sánh cả:

1. Kích thước payload trước nén.
2. Kích thước payload sau nén.
3. Chi phí CPU và latency để serialize, nén, truyền, giải nén và deserialize.

Chỉ so sánh số byte JSON thô với số byte binary thô có thể không phản ánh lưu lượng mạng thực tế.

## 4. Tốc độ phụ thuộc vào toàn bộ pipeline

Hiệu năng serialization không chỉ là thời gian gọi writeValueAsBytes(). Một request có thể trải qua:

~~~text
Java object
    |
    v
Serialize
    |
    v
Compress (optional)
    |
    v
Network / broker / storage
    |
    v
Decompress (optional)
    |
    v
Deserialize
    |
    v
Java object
~~~

Binary có thể giảm thời gian parse text hoặc giảm số byte cần truyền. Nhưng kết quả end-to-end còn phụ thuộc:

- CPU serialize và deserialize.
- Số object tạm được cấp phát.
- Chi phí nén/giải nén.
- Băng thông và latency mạng.
- Buffering, copy byte array và I/O.
- GC khi xử lý số lượng message lớn.
- Backpressure và mức độ song song.

Nếu hệ thống bị giới hạn bởi CPU, binary nhanh hơn ở bước parse có thể hữu ích. Nếu hệ thống bị giới hạn bởi mạng, giảm payload có thể đem lại lợi ích lớn hơn. Nếu dữ liệu đã được nén mạnh và mạng không phải bottleneck, khác biệt về kích thước có thể ít quan trọng.

Định dạng tốt nhất là định dạng cải thiện bottleneck đang tồn tại mà không tạo chi phí vận hành lớn hơn ở phần còn lại.

## 5. Kích thước cần đo ở những lớp nào?

Nên ghi rõ mỗi con số đo đại diện cho lớp dữ liệu nào:

| Chỉ số | Ý nghĩa |
|---|---|
| Serialized bytes | Số byte sau khi mapper serialize, trước compression |
| Compressed bytes | Số byte sau gzip, Brotli hoặc codec đang dùng |
| Framed bytes | Số byte sau khi thêm message header, length prefix hoặc envelope |
| Wire bytes | Số byte thực tế truyền trên giao thức, có thể gồm framing và protocol overhead |
| Stored bytes | Số byte lưu trong broker, file hoặc object storage sau các lớp mã hóa/nén |

Một hệ thống có thể dùng CBOR nhưng vẫn bọc payload trong JSON envelope hoặc Base64. Khi đó, kích thước thực tế có thể khác xa số byte CBOR ban đầu.

Base64 mã hóa binary thành text để đi qua một kênh chỉ chấp nhận text. Nó làm dữ liệu dài thêm khoảng một phần ba trước các overhead khác. Nếu transport đã hỗ trợ byte payload, không nên Base64 chỉ để giữ định dạng text nếu không có yêu cầu tương thích cụ thể.

Khi báo cáo kích thước, hãy nêu rõ có tính header, envelope, compression, encryption và Base64 hay không.

## 6. Tốc độ không chỉ là throughput

Một benchmark chỉ báo số message/giây có thể che giấu latency ở đuôi hoặc chi phí tài nguyên.

Nên đo:

- **Throughput:** số message hoặc byte xử lý trong một đơn vị thời gian.
- **Latency:** thời gian xử lý một message; xem p50, p95, p99.
- **CPU/op:** lượng CPU tiêu thụ cho mỗi lần serialize/deserialize.
- **Allocation/op:** số byte hoặc object được cấp phát mỗi operation.
- **GC:** tần suất và thời gian pause.
- **Peak memory:** bộ nhớ đỉnh khi xử lý batch hoặc message lớn.
- **Error rate:** tỷ lệ payload không thể đọc hoặc chuyển đổi sai.

Một định dạng có throughput cao hơn nhưng p99 latency xấu hơn có thể không phù hợp với API tương tác. Một định dạng có payload nhỏ hơn nhưng allocation lớn hơn có thể làm GC tăng khi lưu lượng cao.

Đặc biệt với message lớn, hãy đo peak memory và khả năng streaming. Một cách benchmark chỉ serialize toàn bộ object thành byte[] có thể không phản ánh pipeline streaming thực tế.

## 7. Cấu hình Jackson cho JSON, Smile và CBOR

Jackson dùng các factory khác nhau để chọn định dạng. Databind vẫn có thể làm việc với cùng DTO:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.smile.SmileFactory;
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;

ObjectMapper jsonMapper = new ObjectMapper();
ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
~~~

Dependency Maven tương ứng:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-smile</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-cbor</artifactId>
    </dependency>
</dependencies>
~~~

Nên dùng Jackson BOM hoặc dependency management của framework để căn chỉnh phiên bản Core, Databind và các dataformat module.

Ví dụ serialize cùng một object:

~~~java
byte[] json = jsonMapper.writeValueAsBytes(event);
byte[] smile = smileMapper.writeValueAsBytes(event);
byte[] cbor = cborMapper.writeValueAsBytes(event);

System.out.println("JSON bytes: " + json.length);
System.out.println("Smile bytes: " + smile.length);
System.out.println("CBOR bytes: " + cbor.length);
~~~

Đây là cách đo kích thước serialized payload trong bộ nhớ. Nó chưa đo compression, framing, network hoặc storage.

## 8. Dùng cùng một dữ liệu và cùng một hợp đồng

So sánh công bằng phải bảo đảm các mapper tạo ra cùng ý nghĩa dữ liệu:

~~~java
public class Event {
    private String eventId;
    private String eventType;
    private Instant occurredAt;
    private int quantity;
    private boolean active;
    private List<String> tags;

    // getters/setters
}
~~~

Nếu một mapper có JavaTimeModule còn mapper khác không có, kết quả có thể khác về khả năng đọc hoặc định dạng timestamp. Nếu một mapper bật inclusion khác, payload có thể nhỏ hơn chỉ vì bỏ null field.

Trước khi so sánh, thống nhất:

- Cùng DTO và cùng object graph.
- Cùng serializer/deserializer tùy chỉnh.
- Cùng null inclusion và default values.
- Cùng cách biểu diễn ngày giờ, decimal, enum và binary data.
- Cùng quy tắc property naming.
- Cùng mức validation và type metadata.

Đừng để một mapper phát timestamp dạng number, mapper khác phát chuỗi ISO-8601 rồi kết luận chênh lệch kích thước chỉ do định dạng.

## 9. Benchmark kích thước và round-trip cơ bản

Ví dụ đo kích thước và xác nhận deserialize:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

public class FormatSizeExample {
    static void measure(
            String name,
            ObjectMapper mapper,
            List<Event> events
    ) throws Exception {
        byte[] bytes = mapper.writeValueAsBytes(events);
        List<Event> restored = mapper.readValue(
                bytes,
                mapper.getTypeFactory()
                        .constructCollectionType(List.class, Event.class)
        );

        if (restored.size() != events.size()) {
            throw new IllegalStateException("Round-trip record count mismatch");
        }

        System.out.printf(
                "%s: %d bytes for %d events%n",
                name,
                bytes.length,
                events.size()
        );
    }
}
~~~

Đoạn mã trên chỉ kiểm tra kích thước và số lượng phần tử. Production benchmark cần xác nhận giá trị từng field hoặc so sánh domain object sau round-trip, vì hai payload có cùng số lượng record vẫn có thể mất dữ liệu.

Không nên đo thời gian bằng một vòng lặp đơn giản duy nhất rồi coi đó là benchmark đáng tin cậy. JVM cần warmup; JIT compilation, class loading và GC có thể làm kết quả đầu tiên khác xa trạng thái ổn định.

## 10. Dùng JMH để đo hiệu năng

JMH (Java Microbenchmark Harness) phù hợp để đo các thao tác nhỏ như serialize và deserialize. Một benchmark nên:

- Tạo mapper một lần trong setup, không tạo mapper trong mỗi operation.
- Chuẩn bị payload trước benchmark.
- Tách benchmark serialize và deserialize.
- Có warmup và nhiều measurement iteration.
- Dùng nhiều fork để giảm ảnh hưởng trạng thái JVM.
- Tránh dead-code elimination bằng cách trả về kết quả hoặc dùng Blackhole.
- Đo allocation nếu cần bằng profiler của JMH.

Ví dụ cấu trúc:

~~~java
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class SerializationBenchmark {
    private ObjectMapper mapper;
    private Event event;
    private byte[] payload;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        mapper = createMapper();
        event = createRepresentativeEvent();
        payload = mapper.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] serialize() throws Exception {
        return mapper.writeValueAsBytes(event);
    }

    @Benchmark
    public Event deserialize() throws Exception {
        return mapper.readValue(payload, Event.class);
    }

    @Benchmark
    public void roundTrip(Blackhole blackhole) throws Exception {
        byte[] bytes = mapper.writeValueAsBytes(event);
        Event restored = mapper.readValue(bytes, Event.class);
        blackhole.consume(restored);
    }
}
~~~

Đây là khung benchmark; createMapper và createRepresentativeEvent phải được cung cấp cho từng định dạng. Tốt hơn nên có một benchmark state hoặc class riêng cho JSON, Smile và CBOR, giữ các thiết lập khác giống nhau.

Đo thêm allocation:

~~~text
java -jar benchmarks.jar SerializationBenchmark -prof gc
~~~

Profiler GC của JMH có thể cung cấp thông tin allocation và GC liên quan. Khi diễn giải kết quả, ghi lại phiên bản JDK, Jackson, CPU, heap, GC, flags và cấu hình benchmark.

## 11. Thiết kế workload đại diện

Một payload duy nhất không đại diện cho toàn hệ thống. Nên tạo nhiều nhóm:

| Workload | Đặc điểm | Điều muốn tìm hiểu |
|---|---|---|
| Small command | Ít field, message nhỏ | Header/overhead có chiếm tỷ trọng lớn không? |
| Repeated records | Nhiều object cùng schema | Tên field lặp lại được mã hóa hiệu quả đến đâu? |
| Text-heavy | String dài, nội dung tự do | Text encoding và compression ảnh hưởng thế nào? |
| Numeric-heavy | Nhiều integer/decimal | Binary number encoding có lợi ích gì? |
| Nested objects | Nhiều cấp object/array | Parser và mapper xử lý nesting ra sao? |
| Large arrays | Hàng nghìn hoặc hàng triệu phần tử | Throughput, memory và streaming |
| Sparse records | Nhiều null/field thiếu | Inclusion và metadata ảnh hưởng kích thước thế nào? |
| Binary values | Byte array hoặc dữ liệu ảnh nhỏ | Native byte string và Base64 khác nhau ra sao? |

Payload nên lấy từ dữ liệu production đã được làm sạch hoặc được tạo theo phân bố thực tế. Nếu tự tạo dữ liệu, cần mô phỏng đúng độ dài string, tỷ lệ null, số field và mức lặp giá trị.

Không dùng dữ liệu thật chứa thông tin cá nhân hoặc bí mật trong benchmark chia sẻ. Dùng fixture đã ẩn danh hoặc dữ liệu tổng hợp.

## 12. So sánh khi có compression

JSON thường nén tốt vì tên field, dấu ngoặc và các chuỗi lặp lại có pattern. Smile/CBOR đã mã hóa cấu trúc nhị phân, nhưng vẫn có thể nén thêm tùy payload.

Một phép đo cơ bản:

~~~java
static byte[] gzip(byte[] input) throws IOException {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
        gzip.write(input);
    }
    return output.toByteArray();
}
~~~

Đo:

~~~java
byte[] raw = mapper.writeValueAsBytes(events);
byte[] compressed = gzip(raw);

System.out.printf(
        "raw=%d bytes, gzip=%d bytes%n",
        raw.length,
        compressed.length
);
~~~

Hãy chạy cùng thuật toán và mức nén cho từng định dạng. Cũng cần đo thời gian và CPU của compression/decompression; không chỉ so sánh compressed size.

Nếu transport đã tự nén, đừng nén lần hai mà không có lý do. Nén lặp có thể tiêu thụ CPU nhưng chỉ giảm rất ít kích thước.

Với payload nhỏ, gzip header có thể lớn hơn phần tiết kiệm. Một số hệ thống chỉ nén khi payload vượt ngưỡng kích thước.

## 13. Đo end-to-end thay vì chỉ mapper

Microbenchmark trả lời câu hỏi serializer nào nhanh hơn trong một JVM. Nó không trả lời trực tiếp hệ thống nào phục vụ request nhanh hơn.

Một benchmark end-to-end nên bao gồm:

1. Tạo hoặc lấy object từ nguồn.
2. Serialize.
3. Compression nếu production dùng.
4. Framing và network/broker nếu cần.
5. Decompression.
6. Deserialize.
7. Validation và xử lý downstream đại diện.

Nếu mục tiêu là giảm chi phí mạng, cần chạy qua môi trường có băng thông và latency tương tự production. Nếu mục tiêu là giảm CPU, cần đo CPU trên mỗi message ở mức concurrency dự kiến.

Ghi riêng thời gian từng giai đoạn để biết binary cải thiện ở đâu. Nếu serialize nhanh hơn nhưng downstream vẫn bị giới hạn bởi database, thay đổi định dạng có thể không làm tăng throughput toàn hệ thống.

## 14. Khả năng quan sát: JSON có lợi thế gì?

JSON có thể đọc trực tiếp bằng mắt và bằng hầu hết công cụ:

- Log viewer.
- Terminal.
- HTTP client.
- Message broker UI.
- Công cụ diff.
- Công cụ jq hoặc JSONPath.
- Dashboard và hệ thống tracing.

Khi có lỗi, kỹ sư có thể mở payload, tìm field và so sánh hai message mà không cần decoder chuyên dụng.

Binary payload thường hiển thị dưới dạng byte không đọc được hoặc ký tự lỗi. Nếu chỉ ghi raw bytes vào log, log có thể vô ích, phình lớn hoặc làm hỏng encoding. Nếu Base64 toàn bộ payload, log trở nên dài hơn và vẫn cần decode để hiểu.

Khả năng quan sát là một chi phí thật của binary. Trước khi chọn, cần xác định ai sẽ debug, họ dùng công cụ nào và có decoder sẵn hay không.

## 15. Thiết kế observability cho binary payload

Không cần ghi toàn bộ payload vào log để vận hành tốt. Có thể ghi metadata có cấu trúc:

~~~json
{
  "messageId": "M-100",
  "format": "cbor",
  "schemaVersion": 2,
  "payloadBytes": 1840,
  "compressedBytes": 920,
  "recordCount": 25,
  "serializationMs": 0.42,
  "correlationId": "C-123"
}
~~~

Các trường hữu ích:

- Message ID hoặc correlation ID.
- Định dạng payload: json, smile hoặc cbor.
- Schema version.
- Byte count trước và sau nén.
- Record count hoặc loại message.
- Thời gian serialize/deserialize.
- Kết quả xử lý và error code.
- Producer/consumer version.

Tránh ghi raw payload, token, password, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Nếu cần lưu payload phục vụ điều tra, dùng kho có quyền truy cập, encryption, retention và audit phù hợp.

Metrics nên tổng hợp theo format và loại message. Không đưa message ID duy nhất vào label metric có cardinality cao; để ID trong log hoặc trace.

## 16. Decoder và công cụ chẩn đoán

Khi dùng binary, đội vận hành cần một cách chuyển payload về dạng dễ đọc. Có thể xây dựng công cụ nội bộ:

~~~text
binary payload
      |
      v
Chọn format từ metadata
      |
      v
SmileFactory / CBORFactory
      |
      v
Đọc thành JsonNode
      |
      v
Pretty-print JSON
~~~

Ví dụ decode CBOR:

~~~java
ObjectMapper cborMapper = new ObjectMapper(new CBORFactory());
JsonNode tree = cborMapper.readTree(cborBytes);

ObjectMapper jsonMapper = new ObjectMapper();
String readable = jsonMapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(tree);
~~~

Đối với Smile:

~~~java
ObjectMapper smileMapper = new ObjectMapper(new SmileFactory());
JsonNode tree = smileMapper.readTree(smileBytes);

String readable = new ObjectMapper()
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(tree);
~~~

Decoder cần biết đúng định dạng và phiên bản/schema. Không nên thử parse một payload bằng mọi factory cho đến khi một parser tình cờ không ném lỗi; dữ liệu có thể bị diễn giải sai. Hãy lưu format identifier cùng message hoặc xác định format bằng content type đáng tin cậy.

Nếu dữ liệu dùng custom serializer, polymorphic type ID hoặc schema ngoài JSON data model, JsonNode có thể không thể hiện đầy đủ semantics. Decoder nên có phiên bản ứng dụng và module tương thích với producer.

## 17. Content type và framing khi trao đổi binary

Khi gửi qua HTTP, broker hoặc file, consumer cần biết payload dùng định dạng nào. Không nên đoán từ byte đầu tiên nếu protocol không quy định cách nhận diện.

Có thể dùng content type hoặc envelope metadata để phân biệt:

- application/json
- application/cbor
- Smile media type theo quy ước của hệ thống, thường gặp là application/x-jackson-smile

Hãy xác nhận media type được các bên thống nhất và tài liệu hóa. Với message broker, có thể dùng message header như contentType, schemaVersion và encoding.

Binary stream cũng cần framing để biết ranh giới message:

- Một HTTP request body thường cung cấp ranh giới message.
- Broker thường có ranh giới từng message.
- File có thể chứa một document hoặc nhiều document nối tiếp theo protocol.
- TCP stream không tự bảo đảm mỗi lần read tương ứng một message.

Nếu nhiều payload được nối vào cùng một stream, cần length prefix hoặc framing protocol rõ ràng. Không nên dựa vào một lần đọc socket để thu đủ toàn bộ message.

## 18. Khả năng tương thích và schema evolution

Smile và CBOR thường giữ mô hình dữ liệu kiểu JSON: object/map, array, string, number, boolean và null. Chúng không tự giải quyết mọi vấn đề schema evolution.

Nếu producer đổi tên property, đổi kiểu hoặc bỏ field, consumer vẫn chịu các quy tắc tương thích của Jackson:

- Unknown properties có thể bị bỏ qua hoặc gây lỗi tùy cấu hình.
- Field mới có thể cần default khi đọc payload cũ.
- Alias có thể giúp nhận tên cũ trong giai đoạn migration.
- Enum mới có thể làm consumer cũ thất bại.
- Polymorphic type ID phải được consumer nhận diện.

Binary không có nghĩa payload tự mang schema đầy đủ. Smile và CBOR có thể tự mô tả cấu trúc token, nhưng không tự biết rằng quantity phải lớn hơn 0 hoặc enum PAID mang ý nghĩa gì.

Nếu cần schema registry, numeric field ID, contract compatibility được quản lý tập trung hoặc code generation đa ngôn ngữ, cần đánh giá các định dạng schema-based như Avro hoặc Protocol Buffers riêng. Chúng có mô hình và tradeoff khác với Smile/CBOR; không nên coi chúng chỉ là một cấu hình khác của Jackson.

## 19. Bảo mật và giới hạn parser

Binary không làm dữ liệu đáng tin cậy hơn. Payload vẫn có thể chứa:

- Cấu trúc lồng nhau quá sâu.
- Array hoặc map rất lớn.
- String/byte string quá dài.
- Giá trị số ngoài miền ứng dụng.
- Type metadata không được phép.
- Nội dung gây tiêu thụ CPU hoặc memory quá mức.

Nên:

- Giới hạn kích thước request/message trước khi parse.
- Cấu hình StreamReadConstraints phù hợp với phiên bản Jackson.
- Giới hạn số record và độ sâu nghiệp vụ.
- Chỉ bật polymorphic typing với validator/allowlist phù hợp.
- Kiểm tra kiểu, miền giá trị và authorization sau deserialize.
- Không ghi payload nhạy cảm vào log.
- Cập nhật Jackson và dataformat module theo chính sách dependency của dự án.

Khi lưu payload binary, cần bảo vệ tính toàn vẹn và nguồn gốc message bằng cơ chế phù hợp của hệ thống, chẳng hạn TLS, message authentication hoặc chữ ký trên một representation được canonicalize rõ. Không ký byte stream theo cách mà hai serializer có thể tạo byte khác nhau cho cùng dữ liệu nếu giao thức chưa quy định canonical encoding.

## 20. Những yếu tố làm benchmark sai lệch

Một số lỗi thường gặp:

### Tạo ObjectMapper trong mỗi lần đo

Chi phí khởi tạo mapper và cache serializer bị trộn với chi phí serialize. Trong ứng dụng, mapper thường được tái sử dụng. Hãy tạo mapper trong setup.

### Chỉ đo một payload

Một object nhỏ không đại diện cho batch lớn hoặc dữ liệu nhiều string. Dùng nhiều workload.

### So sánh mapper có cấu hình khác nhau

Null inclusion, date format, custom serializer và module khác nhau có thể làm thay đổi kích thước hoặc tốc độ.

### Không warmup JVM

JIT compilation và class loading làm số đo ban đầu thiếu ổn định. Dùng JMH warmup và nhiều fork.

### Chỉ đo raw bytes

Production có thể nén, Base64, framing hoặc mã hóa. Đo thêm compressed/wire size.

### Bỏ qua allocation và GC

Throughput cao trong benchmark ngắn có thể đi kèm allocation lớn và GC pause khi chạy lâu.

### Đo serialize nhưng bỏ qua deserialize

Producer và consumer đều trả chi phí. Một format có serialize nhanh nhưng deserialize chậm có thể không phù hợp.

### Dùng dữ liệu quá sạch

Production có null, string dài, Unicode, field thiếu, array rỗng và giá trị biên. Fixture phải phản ánh các trường hợp đó.

### Không xác nhận round-trip

Payload nhỏ hoặc nhanh không có ích nếu dữ liệu thay đổi hoặc mất field.

## 21. Ví dụ bảng kết quả benchmark

Không nên điền số giả định vào báo cáo. Hãy đo và điền các giá trị từ môi trường mục tiêu:

| Định dạng | Raw bytes/message | Compressed bytes/message | Serialize µs | Deserialize µs | Allocation bytes/op | p99 end-to-end |
|---|---:|---:|---:|---:|---:|---:|
| JSON | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| Smile | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| CBOR | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Có thể bổ sung các cột:

- CPU utilization ở concurrency mục tiêu.
- GC pause và allocation rate.
- Error rate.
- Throughput messages/second.
- Peak heap với batch lớn.
- Thời gian điều tra payload trong một bài tập vận hành.

Ghi rõ dataset, số lần chạy, JDK, Jackson version, phần cứng, compression level và cấu hình mapper. Nếu không có thông tin này, người khác khó tái lập hoặc diễn giải kết quả.

## 22. Đưa binary vào production theo từng bước

Không nhất thiết phải chuyển toàn bộ hệ thống cùng lúc. Một lộ trình có kiểm soát:

1. Chọn một luồng message có workload đại diện.
2. Thêm hỗ trợ format ở producer và consumer.
3. Công bố content type/schema version rõ ràng.
4. Giữ JSON fallback nếu consumer hoặc công cụ vận hành chưa hỗ trợ binary.
5. Chạy shadow/canary để so sánh byte size, latency, CPU và lỗi.
6. Kiểm tra decoder, log metadata và quy trình hỗ trợ sự cố.
7. Chỉ tăng tỷ lệ traffic khi round-trip và contract tests đạt.
8. Theo dõi chi phí hạ tầng và khả năng debug sau khi rollout.
9. Có đường rollback về JSON hoặc phiên bản trước.

Nếu producer và consumer được nâng cấp độc lập, không đổi format mặc định khi còn consumer cũ chưa hiểu content type mới. Dùng content negotiation hoặc versioned topic/endpoint nếu cần chuyển đổi dần.

## 23. Khi nào nên chọn JSON, Smile hay CBOR?

| Điều kiện | Lựa chọn thường hợp lý |
|---|---|
| API công khai, client đa dạng, cần debug trực tiếp | JSON |
| Các dịch vụ Java dùng Jackson, lưu lượng lớn và muốn giảm payload | Đánh giá Smile |
| Cần định dạng nhị phân có chuẩn độc lập, consumer nhiều ngôn ngữ | Đánh giá CBOR |
| Payload đã gzip tốt và network không phải bottleneck | Giữ JSON có thể hợp lý |
| Message rất nhỏ | Đo overhead trước khi chọn binary |
| Công cụ vận hành không có decoder | JSON dễ quan sát hơn; cần xây decoder trước khi chuyển |
| Cần schema registry và field ID ổn định | Đánh giá Avro/Protobuf riêng |
| Dữ liệu cần được con người sửa trực tiếp | JSON hoặc YAML thường thuận tiện hơn |

Đây là hướng lựa chọn ban đầu, không phải kết luận thay cho benchmark. Cần đo trên workload và hạ tầng thật.

## 24. Checklist đánh giá trước khi quyết định

Trước khi chuyển định dạng, hãy xác nhận:

- [ ] Đã chọn các workload đại diện cho message nhỏ, lớn, lặp field, text-heavy và nested.
- [ ] Đã so sánh raw size và compressed size.
- [ ] Đã đo serialize, deserialize và round-trip.
- [ ] Đã đo throughput, p50/p95/p99 latency, allocation và GC.
- [ ] Mapper và module có phiên bản/cấu hình tương đương.
- [ ] Round-trip giữ nguyên giá trị nghiệp vụ.
- [ ] Content type và framing được tài liệu hóa.
- [ ] Consumer ở mọi ngôn ngữ có thư viện tương thích.
- [ ] Có decoder và quy trình điều tra binary payload.
- [ ] Log chỉ chứa metadata cần thiết, không làm lộ dữ liệu nhạy cảm.
- [ ] Có schema evolution policy và test fixture nhiều phiên bản.
- [ ] Có giới hạn kích thước, độ sâu và số lượng phần tử.
- [ ] Có canary, metric theo format và phương án rollback.

## 25. Kết luận

Smile và CBOR có thể giảm kích thước hoặc chi phí parse so với JSON trong một số workload, nhưng binary không mặc nhiên nhỏ hơn hoặc nhanh hơn sau khi tính compression, framing, CPU, allocation và network. Hãy đo raw bytes, compressed bytes, throughput, latency ở đuôi, CPU, memory và GC bằng cùng dữ liệu, cùng cấu hình và benchmark có warmup. JSON có ưu thế rõ rệt về khả năng quan sát; khi dùng binary, cần content type, decoder, log metadata và công cụ điều tra phù hợp. Smile thuận tiện trong hệ sinh thái Jackson; CBOR có chuẩn độc lập và phù hợp với hệ thống đa ngôn ngữ nếu các implementation tương thích. Cả hai vẫn cần schema evolution, validation và giới hạn parser. Chỉ chuyển format khi số đo end-to-end chứng minh lợi ích đủ lớn để bù chi phí tích hợp và vận hành.
