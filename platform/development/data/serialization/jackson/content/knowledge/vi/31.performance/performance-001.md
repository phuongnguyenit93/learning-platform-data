# Đo thời gian đọc, ghi và chi phí cấp phát đối tượng

Khi tối ưu Jackson, chỉ đo thời gian gọi writeValueAsString() hoặc readValue() một lần thường không cho biết hệ thống thực sự nhanh hay chậm. Kết quả có thể bị ảnh hưởng bởi JIT chưa warm up, class loading, cache serializer chưa được tạo, garbage collection, kích thước payload, cách tạo input và việc benchmark vô tình đo cả I/O hoặc logging.

Một phép đo có ích phải trả lời rõ ba câu hỏi:

1. **Đọc (deserialization) mất bao lâu?** Từ JSON text/bytes/stream đến object Java.
2. **Ghi (serialization) mất bao lâu?** Từ object Java đến JSON text/bytes/stream.
3. **Mỗi thao tác cấp phát bao nhiêu bộ nhớ?** Bao nhiêu byte/object được tạo, tần suất GC ra sao và allocation đến từ thành phần nào?

Trong Java, JMH là công cụ phù hợp cho microbenchmark vì nó xử lý warmup, measurement iteration, fork và tối ưu hóa của JVM có kiểm soát. Khi cần hiểu allocation và GC, kết hợp JMH GC profiler với Java Flight Recorder (JFR) hoặc profiler phù hợp. Sau đó, kiểm tra lại bằng benchmark tích hợp hoặc load test trên luồng ứng dụng thật.

## 1. Xác định chính xác điều cần đo

Serialization và deserialization là hai hướng công việc khác nhau:

~~~text
Serialization:
Java object -> Jackson serializer -> JSON tokens -> String / byte[] / OutputStream

Deserialization:
String / byte[] / InputStream -> JSON parser -> Jackson deserializer -> Java object
~~~

Không nên gộp hai hướng thành một con số duy nhất. Một payload có thể serialize nhanh nhưng deserialize chậm do constructor, collection, polymorphic type resolution hoặc custom deserializer. Ngược lại, đọc có thể nhanh nhưng ghi tốn allocation do tạo String hoặc byte buffer lớn.

Cũng cần phân biệt phạm vi đo:

| Phạm vi | Bao gồm | Câu hỏi trả lời |
|---|---|---|
| Jackson core mapping | Parser/generator và mapping Java type | Bản thân Jackson xử lý payload nhanh đến đâu? |
| Chuyển sang String/byte[] | Mapping cộng tạo output representation | API hiện tại tốn bao nhiêu cho output trong memory? |
| Đọc từ stream/ghi ra stream | Mapping cộng parser/generator và buffer I/O | Cách ứng dụng đang dùng stream có chi phí nào? |
| End-to-end request | Mapping, validation, business logic, network, compression, framework | Người dùng hoặc service nhận latency/throughput ra sao? |

Một benchmark chỉ đo writeValueAsString() không đại diện cho thời gian gửi HTTP response. Một load test endpoint cũng không tách được riêng chi phí Jackson. Hãy đo từng lớp để tìm đúng nơi cần tối ưu.

## 2. Vì sao không nên dùng một vòng lặp System.nanoTime đơn giản?

Một benchmark tự viết thường trông như sau:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    mapper.writeValueAsString(value);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Cách này dễ viết nhưng kết quả thường không đáng tin vì:

- JVM có thể đang biên dịch code trong lúc vòng lặp chạy.
- Lần đầu tạo serializer/deserializer và cache có chi phí khác những lần tiếp theo.
- Kết quả có thể bị tối ưu bỏ nếu không được sử dụng đúng cách.
- GC có thể xảy ra giữa phép đo và làm một iteration dài bất thường.
- Một luồng benchmark có thể không phản ánh tải nhiều thread.
- Không có cơ chế chuẩn để tách warmup và measurement.
- Chỉ đo một lần nên không thể đánh giá độ biến thiên hoặc độ ổn định.

System.nanoTime() vẫn hữu ích để đo một khoảng thời gian trong ứng dụng hoặc benchmark nhỏ có kiểm soát. Nhưng để so sánh hiệu năng thư viện/Jackson, hãy dùng JMH thay vì tự viết vòng lặp đo thời gian.

## 3. JMH là gì?

JMH (Java Microbenchmark Harness) là framework benchmark dành cho JVM. JMH cung cấp:

- Warmup iterations để JVM tối ưu code trước khi lấy kết quả.
- Measurement iterations để thu thập số đo.
- Forks để chạy benchmark trong JVM process riêng, giảm ảnh hưởng trạng thái từ benchmark khác.
- Các chế độ throughput, average time, sample time và single-shot.
- State và setup để chuẩn bị dữ liệu ngoài vùng đo.
- Blackhole/return value để tránh dead-code elimination.
- Profiler tích hợp, trong đó có GC profiler.

JMH phù hợp để so sánh các cách gọi Jackson trong điều kiện được kiểm soát. Nó không thay thế load test cho API production, nhưng giúp xác định chi phí tương đối của từng thao tác một cách có hệ thống.

## 4. Tạo benchmark JMH cho Jackson

Một benchmark nên chuẩn bị ObjectMapper, DTO và JSON input trong @Setup, sau đó chỉ thực hiện thao tác cần đo trong method @Benchmark.

Ví dụ DTO:

~~~java
public record OrderItem(
        long productId,
        String productName,
        int quantity,
        BigDecimal unitPrice
) {}

public record OrderEvent(
        String orderId,
        Instant createdAt,
        String customerId,
        List<OrderItem> items,
        Map<String, String> attributes
) {}
~~~

State dùng chung cho các benchmark method:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.openjdk.jmh.annotations.*;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
public class JacksonBenchmarkState {
    ObjectMapper mapper;
    ObjectWriter writer;
    ObjectReader reader;

    OrderEvent event;
    String json;
    byte[] jsonBytes;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();

        writer = mapper.writerFor(OrderEvent.class);
        reader = mapper.readerFor(OrderEvent.class);

        event = new OrderEvent(
                "ORD-2026-001",
                Instant.parse("2026-11-12T10:30:00Z"),
                "CUS-100",
                List.of(
                        new OrderItem(
                                501L,
                                "Keyboard",
                                2,
                                new BigDecimal("49.90")
                        ),
                        new OrderItem(
                                502L,
                                "Mouse",
                                1,
                                new BigDecimal("19.50")
                        )
                ),
                Map.of(
                        "source", "web",
                        "campaign", "autumn"
                )
        );

        json = writer.writeValueAsString(event);
        jsonBytes = json.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Điểm quan trọng là mapper, writer, reader, object nguồn và JSON input được tạo trước measurement. Nếu tạo new ObjectMapper() hoặc dựng payload trong từng invocation, benchmark sẽ đo cả chi phí setup thay vì chỉ đo thao tác cần so sánh.

## 5. Đo thời gian serialization

Benchmark ghi JSON thành String:

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class JacksonWriteBenchmark {

    @Benchmark
    public String writeString(JacksonBenchmarkState state)
            throws JsonProcessingException {
        return state.writer.writeValueAsString(state.event);
    }
}
~~~

Method trả về String để JMH quan sát kết quả; không cần ghi ra console. Nếu benchmark chỉ gọi method rồi bỏ kết quả, JIT có thể loại bỏ hoặc biến đổi một phần công việc trong những trường hợp phù hợp.

Có thể đo output byte:

~~~java
@Benchmark
public byte[] writeBytes(JacksonBenchmarkState state)
        throws JsonProcessingException {
    return state.writer.writeValueAsBytes(state.event);
}
~~~

Hai phép đo trả lời hai câu hỏi khác nhau:

- writeValueAsString() tạo Java String.
- writeValueAsBytes() tạo byte representation theo encoding mà Jackson sử dụng cho writer.

Nếu ứng dụng thật gửi HTTP body dưới dạng bytes, benchmark bytes thường gần hơn. Nếu ứng dụng cần String để xử lý tiếp, benchmark String phù hợp hơn. Không so sánh hai số rồi kết luận một API luôn tốt hơn khi output representation và yêu cầu downstream khác nhau.

## 6. Đo thời gian deserialization

Dùng JSON được chuẩn bị sẵn trong setup:

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class JacksonReadBenchmark {

    @Benchmark
    public OrderEvent readString(JacksonBenchmarkState state)
            throws IOException {
        return state.reader.readValue(state.json);
    }

    @Benchmark
    public OrderEvent readBytes(JacksonBenchmarkState state)
            throws IOException {
        return state.reader.readValue(state.jsonBytes);
    }
}
~~~

Benchmark này tách việc đọc JSON khỏi việc tạo JSON input. Nếu tạo String/byte[] trong method benchmark, số đo sẽ bao gồm cả chi phí encode hoặc chuẩn bị dữ liệu.

Khi so sánh readValue(String, ...) và readValue(byte[], ...), hãy ghi rõ ứng dụng thực tế nhận dữ liệu dưới dạng nào. Byte input có thể tránh một số bước chuyển đổi String, nhưng kết quả còn phụ thuộc charset, parser, kích thước payload và cách dữ liệu đến từ network/file.

## 7. Đo thời gian bằng các chế độ JMH

@BenchmarkMode quyết định ý nghĩa số đo:

| Mode | Đơn vị/ý nghĩa | Khi phù hợp |
|---|---|---|
| Throughput | Số operation mỗi đơn vị thời gian | Muốn biết năng lực xử lý tối đa |
| AverageTime | Thời gian trung bình mỗi operation | So sánh chi phí một lần đọc/ghi |
| SampleTime | Lấy mẫu thời gian operation | Xem phân phối latency và tail trong benchmark |
| SingleShotTime | Đo một lần chạy mỗi iteration | Khảo sát cold path hoặc thao tác hiếm |

Ví dụ đo throughput:

~~~java
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class JacksonThroughputBenchmark {
    @Benchmark
    public OrderEvent read(JacksonBenchmarkState state)
            throws IOException {
        return state.reader.readValue(state.jsonBytes);
    }
}
~~~

Throughput và average time không phải hai cách ghi cùng một con số. Khi tải đơn luồng và workload ổn định, chúng có quan hệ gần nhau; dưới tải đa luồng hoặc có contention, không thể đơn giản lấy nghịch đảo một số đo để suy ra toàn bộ hành vi hệ thống.

## 8. Warmup, measurement và fork

JVM là runtime có JIT compiler, class loading, inline cache và nhiều cơ chế tối ưu động. Kết quả ở lần gọi đầu thường khác xa steady state.

Các annotation thường dùng:

~~~java
@Warmup(
        iterations = 5,
        time = 1,
        timeUnit = TimeUnit.SECONDS
)
@Measurement(
        iterations = 8,
        time = 1,
        timeUnit = TimeUnit.SECONDS
)
@Fork(3)
~~~

Ý nghĩa:

- Warmup chạy benchmark nhưng không dùng các iteration đó làm kết quả chính.
- Measurement thu thập số liệu sau warmup.
- Fork chạy benchmark trong nhiều JVM process riêng, giúp tránh phụ thuộc một trạng thái JVM duy nhất.

Các con số trên chỉ là điểm bắt đầu. Benchmark nặng có thể cần iteration dài hơn; benchmark rất ngắn có thể cần nhiều iteration để giảm nhiễu. Hãy xem độ ổn định và error/confidence interval trong output JMH.

Không nên chỉ chạy một fork rồi kết luận chênh lệch nhỏ là có ý nghĩa. Nếu hai cách đo chênh nhau ít hơn mức dao động giữa các fork, cần thêm dữ liệu hoặc workload thực tế hơn.

## 9. Đo allocation và GC bằng JMH profiler

Thời gian nhanh không đồng nghĩa chi phí bộ nhớ thấp. Một serializer có thể chạy nhanh hơn nhưng tạo nhiều object tạm, khiến GC hoạt động thường xuyên hơn khi traffic tăng.

Chạy benchmark với GC profiler:

~~~bash
java -jar target/benchmarks.jar JacksonWriteBenchmark -prof gc
~~~

Một số metric quan trọng:

| Metric | Ý nghĩa |
|---|---|
| gc.alloc.rate | Tốc độ cấp phát bộ nhớ, thường báo MB/giây |
| gc.alloc.rate.norm | Số byte cấp phát trung bình trên mỗi operation |
| gc.count | Số lần GC trong khoảng đo |
| gc.time | Tổng thời gian GC được profiler ghi nhận |
| gc.churn.* | Lượng allocation/churn theo các pool khi profiler cung cấp |

Trong nhiều trường hợp, gc.alloc.rate.norm là metric dễ so sánh nhất: nó trả lời một lần serialize/deserialize tạo khoảng bao nhiêu byte allocation.

Ví dụ output minh họa, không phải số đo của một ứng dụng cụ thể:

| Benchmark | Score | gc.alloc.rate.norm |
|---|---:|---:|
| writeString | 18.2 µs/op | 8.4 KB/op |
| writeBytes | 16.7 µs/op | 7.1 KB/op |
| readString | 21.5 µs/op | 5.8 KB/op |
| readBytes | 19.9 µs/op | 5.1 KB/op |

Không nên dùng bảng số liệu minh họa làm mục tiêu hiệu năng. Allocation phụ thuộc DTO, payload, JDK, Jackson version, module, cấu hình, kích thước string và cách benchmark.

## 10. Vì sao cần đo bytes/op thay vì chỉ nhìn heap sau benchmark?

Heap usage tại một thời điểm không cho biết mỗi operation đã cấp phát bao nhiêu. Nhiều object có thể được tạo rồi thu gom trước khi bạn chụp heap. Ngược lại, heap có thể lớn vì object còn được giữ reference, không phải vì allocation rate cao.

Cần phân biệt:

- **Allocation rate:** tốc độ tạo object/byte mới.
- **Live set:** object còn reachable sau GC.
- **Retained heap:** lượng memory còn bị giữ bởi một object graph.
- **GC pressure:** mức độ allocation khiến collector phải chạy thường xuyên.

Một benchmark có 10 KB/op và chạy 20.000 operation/giây có allocation khoảng 200 MB/giây trước khi tính các thành phần khác. Đây là phép nhân để hình dung áp lực allocation, không phải dự đoán trực tiếp thời gian GC.

Một object có thể được allocate nhiều nhưng sống rất ngắn. GC generation và collector có thể xử lý loại allocation đó khá hiệu quả, nhưng nếu allocation rate quá cao, CPU dành cho GC vẫn có thể đáng kể.

## 11. Đo riêng String, byte[] và stream

Một API có thể tạo các lớp representation khác nhau:

~~~text
Java object
   |
   +-- writeValueAsString -> String + buffer/temporary objects
   |
   +-- writeValueAsBytes  -> byte[] + buffer/temporary objects
   |
   +-- writeValue(OutputStream) -> stream writes + internal buffers
~~~

writeValueAsString() cần tạo String kết quả. writeValueAsBytes() cần tạo byte array. writeValue(OutputStream, value) ghi qua stream và có thể tránh giữ toàn bộ output dưới dạng một String/byte array do ứng dụng tạo, nhưng vẫn có buffer nội bộ và chi phí I/O.

Ví dụ stream benchmark:

~~~java
@State(Scope.Thread)
public class StreamWriteState {
    ObjectWriter writer;
    OrderEvent event;
    ByteArrayOutputStream output;

    @Setup(Level.Trial)
    public void setup() {
        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();
        writer = mapper.writerFor(OrderEvent.class);
        event = createRepresentativeEvent();
        output = new ByteArrayOutputStream(4096);
    }
}

@Benchmark
public int writeToStream(StreamWriteState state)
        throws IOException {
    state.output.reset();
    state.writer.writeValue(state.output, state.event);
    return state.output.size();
}
~~~

Ví dụ này tái sử dụng một ByteArrayOutputStream trong suốt trial và reset nội dung trước mỗi lần ghi. Nó đo đường đi với buffer được tái sử dụng. Nếu production tạo stream/buffer mới mỗi request, hãy benchmark riêng trường hợp tạo mới bên trong method để tính cả chi phí cấp phát đó.

Đối với stream từ network/file, đo cả I/O trong benchmark tích hợp. Không trộn số đo stream memory với số đo network chậm rồi quy toàn bộ khác biệt cho Jackson.

## 12. Đo chi phí tạo ObjectMapper và chi phí thao tác riêng biệt

ObjectMapper có chi phí khởi tạo và cấu hình. Mapper còn xây dựng/cache serializer và deserializer khi xử lý type lần đầu.

Hai câu hỏi cần được tách:

1. Ứng dụng khởi tạo mapper mất bao lâu và cấp phát bao nhiêu?
2. Một mapper đã cấu hình và warm up xử lý mỗi JSON mất bao lâu?

Benchmark steady-state nên tạo mapper một lần trong @Setup(Level.Trial), sau đó dùng lại. Nếu mục tiêu là đo startup/cold path, tạo benchmark riêng và dùng SingleShotTime hoặc một chương trình startup measurement được thiết kế riêng.

Không tạo new ObjectMapper() trong mỗi request chỉ để “đảm bảo mới nhất”. Jackson khuyến nghị tái sử dụng mapper đã cấu hình; mapper thread-safe khi cấu hình hoàn tất trước khi dùng. ObjectReader và ObjectWriter là các đối tượng cấu hình bất biến, thích hợp để tái sử dụng theo kiểu đích hoặc use case.

Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();

ObjectReader orderReader = mapper.readerFor(OrderEvent.class);
ObjectWriter orderWriter = mapper.writerFor(OrderEvent.class);
~~~

Cấu hình mapper một lần khi ứng dụng khởi động. Tránh đăng ký module hoặc thay đổi feature sau khi mapper đã bắt đầu xử lý request.

## 13. Cache serializer/deserializer ảnh hưởng phép đo

Jackson cache serializer và deserializer đã xây dựng cho các kiểu. Vì vậy, lần đầu xử lý một kiểu có thể bao gồm:

- Introspection class/property.
- Phân giải annotation và mix-in.
- Tạo serializer/deserializer.
- Tạo hoặc tra cứu serializer cho kiểu lồng nhau.
- Khởi tạo cache và các cấu trúc phụ trợ.

Steady-state benchmark thường warm up những đường đi này. Nếu muốn đo cold start, phải thiết kế một phép đo khác, thường dùng process mới cho từng sample hoặc đo startup ứng dụng.

Không xóa cache hoặc tạo mapper mới trong từng iteration steady-state nếu production dùng một mapper chia sẻ. Điều đó làm benchmark đo một workload khác.

## 14. Đo các cách đọc khác nhau: POJO, Map và JsonNode

Cùng một JSON có thể được đọc thành các cấu trúc khác nhau:

~~~java
OrderEvent event = mapper.readValue(json, OrderEvent.class);

Map<String, Object> map = mapper.readValue(
        json,
        new TypeReference<Map<String, Object>>() {}
);

JsonNode tree = mapper.readTree(json);
~~~

Các target này có chi phí allocation và mục đích khác nhau:

| Target | Allocation thường gặp | Khi phù hợp |
|---|---|---|
| POJO/record | DTO, collection, String và object domain | Ứng dụng biết schema và xử lý nghiệp vụ |
| Map<String, Object> | Map, entry, list và scalar wrapper | Dữ liệu linh hoạt, không có model cố định |
| JsonNode | Node cho object, array, scalar và cấu trúc tree | Cần inspect/transform JSON động |
| Streaming parser | Parser/token state và object do consumer tự tạo | Chỉ cần đọc một phần hoặc xử lý từng token |

Map và JsonNode thường cần cấu trúc trung gian tổng quát hơn DTO cụ thể. Nhưng không có quy tắc rằng chúng luôn chậm hơn trong mọi payload; serializer/deserializer custom và cấu trúc dữ liệu có thể làm thay đổi kết quả. Hãy benchmark đúng thao tác downstream: nếu sau khi đọc Map còn phải chuyển sang DTO, hãy đo cả chuỗi công việc đó.

## 15. Tree model có thể tạo nhiều object

readTree() xây dựng một cây node. Với JSON lồng sâu và nhiều field, cây có thể chứa nhiều object node và node scalar.

Ví dụ:

~~~json
{
  "order": {
    "items": [
      {"id": 1, "quantity": 2},
      {"id": 2, "quantity": 1}
    ]
  }
}
~~~

Tree model tiện cho việc truy cập động:

~~~java
JsonNode root = mapper.readTree(json);
int itemCount = root.path("order").path("items").size();
~~~

Nhưng nếu ứng dụng chỉ cần một DTO xác định, đọc trực tiếp vào POJO có thể tránh tạo một tree tổng quát rồi chuyển tiếp. Nếu chỉ cần một vài field trong payload lớn, streaming parser có thể tránh xây dựng toàn bộ tree.

Benchmark phải bao gồm phần xử lý mà ứng dụng thực sự cần. So sánh readTree() đơn thuần với readValue() rồi bỏ qua bước truy cập tree/convert DTO sẽ không phải so sánh công bằng nếu production luôn làm bước đó.

## 16. Streaming API khi cần giảm allocation

Jackson Streaming API cho phép đọc token trực tiếp bằng JsonParser và ghi token bằng JsonGenerator, không cần tạo toàn bộ object graph hoặc tree.

Ví dụ đọc một field:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "orderId".equals(parser.currentName())) {
            parser.nextToken();
            String orderId = parser.getValueAsString();
            processOrderId(orderId);
        }
    }
}
~~~

Streaming hữu ích khi:

- Chỉ cần một số field trong JSON lớn.
- Có thể xử lý từng phần tử array ngay khi đọc.
- Không cần giữ toàn bộ object graph trong memory.
- Cần kiểm soát chính xác token và luồng dữ liệu.

Đổi lại, code streaming cần tự quản lý state, nested structure, field order nếu logic phụ thuộc thứ tự, validation và error handling. Nó không tự động nhanh hơn trong mọi tình huống. Nếu vẫn phải tạo toàn bộ domain object, lợi ích allocation có thể nhỏ hơn phần phức tạp tăng thêm.

Hãy so sánh hai implementation có cùng semantics và cùng lượng công việc.

## 17. Đo payload nhỏ, vừa và lớn

Không nên chỉ benchmark một JSON mẫu. Kích thước và hình dạng payload ảnh hưởng parser, mapping và allocation.

Một bộ workload nên có ít nhất:

| Workload | Đặc điểm | Điều cần quan sát |
|---|---|---|
| Small | Vài scalar field | Overhead cố định trên mỗi operation |
| Medium | Nested DTO, vài collection | Chi phí mapping và allocation phổ biến |
| Large | Nhiều record/field, string lớn | Throughput, allocation rate, GC và memory |
| Deep | Object graph lồng nhiều tầng | Parser depth, object count, stack/CPU |
| Wide | Nhiều property cùng cấp | Introspection/cache và số field |
| Sparse/null-heavy | Nhiều null hoặc property thiếu | Inclusion/null handling |
| Polymorphic | Nhiều subtype/discriminator | Type resolution và subtype construction |

Dùng dữ liệu đại diện, không chỉ tạo JSON có hàng nghìn field giống nhau. Payload production thường có phân bố độ dài string, số phần tử, null và subtype khác nhau.

## 18. Kiểm soát dữ liệu benchmark

Một benchmark có thể bị lệch nếu payload không đại diện hoặc chỉ lặp một giá trị đơn giản.

Nên xác định:

- Kích thước JSON theo byte và theo ký tự.
- Số property, nested level và số phần tử collection.
- Độ dài string trung bình và tối đa.
- Số trường null/missing.
- Số kiểu concrete/subtype.
- Kiểu number, precision của BigDecimal và định dạng ngày giờ.
- Tỷ lệ payload hợp lệ/lỗi nếu ứng dụng cần xử lý lỗi.
- Tỷ lệ payload nhỏ/vừa/lớn theo traffic thực tế.

Nếu benchmark chỉ lặp cùng một JSON, cache CPU và dữ liệu có thể làm kết quả tốt hơn workload có nhiều payload khác nhau. Nếu production dùng payload thay đổi, nên có benchmark dataset nhiều mẫu. Chi phí chọn mẫu/index cũng cần được tính hoặc loại trừ có chủ đích và ghi rõ.

Không dùng dữ liệu nhạy cảm thật trong benchmark nếu không cần thiết. Tạo dữ liệu tổng hợp giữ đặc điểm kích thước và phân bố là đủ cho phần lớn phép đo.

## 19. Đo allocation theo từng kiểu target

Có thể dùng JMH cùng state JSON cố định để so sánh DTO, tree và map:

~~~java
@State(Scope.Thread)
public class ReadTargetBenchmark {
    ObjectMapper mapper;
    String json;
    byte[] bytes;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        mapper = new ObjectMapper();
        json = loadRepresentativeJson();
        bytes = json.getBytes(StandardCharsets.UTF_8);
    }

    @Benchmark
    public OrderEvent readPojo() throws IOException {
        return mapper.readValue(bytes, OrderEvent.class);
    }

    @Benchmark
    public JsonNode readTree() throws IOException {
        return mapper.readTree(bytes);
    }

    @Benchmark
    public Map<String, Object> readMap() throws IOException {
        return mapper.readValue(
                bytes,
                new TypeReference<Map<String, Object>>() {}
        );
    }
}
~~~

loadRepresentativeJson() ở đây là hàm chuẩn bị dữ liệu trong setup, không phải API của Jackson. Trong project thực tế, có thể đọc fixture một lần hoặc dựng payload trong @Setup.

Chạy:

~~~bash
java -jar target/benchmarks.jar ReadTargetBenchmark -prof gc
~~~

So sánh cả thời gian và bytes/op. Nếu tree/map nhanh hơn trong phép đo parser nhưng application phải convert tiếp sang DTO, hãy thêm benchmark cho toàn bộ pipeline.

## 20. JFR để tìm object nào đang được cấp phát

JMH GC profiler cho biết allocation tổng thể trên mỗi operation. Để tìm class cụ thể gây allocation, có thể dùng Java Flight Recorder.

Ví dụ chạy ứng dụng/benchmark với recording:

~~~bash
java -XX:StartFlightRecording=filename=jackson.jfr,settings=profile,dumponexit=true -jar target/benchmarks.jar
~~~

Sau khi chạy, mở file recording bằng JDK Mission Control hoặc công cụ JFR tương ứng. Tùy JDK/version và recording settings, có thể xem:

- Allocation in new TLAB.
- Allocation outside TLAB.
- Hot methods.
- CPU samples.
- Garbage collection events.
- Object allocation samples và stack trace.

Các class có thể xuất hiện trong profile tùy workload: byte[], char[], String, collection implementation, LinkedHashMap, ArrayList, Jackson node classes, DTO và buffer nội bộ. Đây chỉ là ví dụ các loại allocation có thể gặp; profile thực tế mới xác định hotspot.

JFR allocation sampling là sampling, không phải lúc nào cũng ghi từng object allocation. Hãy dùng nó để tìm hướng điều tra, rồi đối chiếu với gc.alloc.rate.norm và benchmark có kiểm soát.

## 21. Phân tích GC và heap

Nếu allocation rate cao, cần xem GC có thực sự ảnh hưởng latency/throughput hay không. Các câu hỏi cần trả lời:

- GC xảy ra bao nhiêu lần trong measurement?
- Có pause dài trùng với latency spike không?
- Young generation có churn rất cao không?
- Object có sống lâu và bị promote không?
- Có retained object do cache hoặc queue giữ reference không?
- Tăng throughput có làm allocation rate tăng quá nhanh không?

Không nên chỉ nhìn tổng heap hoặc một lần GC rồi kết luận. Benchmark ngắn có thể chưa tạo đủ áp lực để lộ vấn đề production. Với workload dài, hãy chạy đủ lâu và giữ JVM flags, heap size, GC và CPU tương đương môi trường mục tiêu.

Không gọi System.gc() giữa các iteration để “làm sạch” benchmark. Lệnh này làm thay đổi workload và có thể khiến số đo không còn đại diện.

## 22. Đo chi phí ObjectMapper, ObjectReader và ObjectWriter

Mapper reuse là một quyết định quan trọng đối với hiệu năng. So sánh hai tình huống riêng:

**Steady-state reuse:**

~~~java
@State(Scope.Benchmark)
public class ReusedMapperState {
    ObjectMapper mapper;
    ObjectReader reader;
    String json;

    @Setup(Level.Trial)
    public void setup() throws JsonProcessingException {
        mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();
        reader = mapper.readerFor(OrderEvent.class);
        json = mapper.writeValueAsString(createRepresentativeEvent());
    }
}

public class MapperReuseBenchmark {
    @Benchmark
    public OrderEvent read(ReusedMapperState state) throws IOException {
        return state.reader.readValue(state.json);
    }

    @Benchmark
    public OrderEvent readWithNewMapper(ReusedMapperState state)
            throws IOException {
        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();
        return mapper.readValue(state.json, OrderEvent.class);
    }
}
~~~

createRepresentativeEvent() là hàm dựng fixture của benchmark và chỉ được gọi trong setup; phần đọc đo ở method read(). Method readWithNewMapper cố ý tính cả chi phí tạo mapper để đối chiếu anti-pattern.
Benchmark tạo mapper mới có thể hữu ích để định lượng anti-pattern hoặc chi phí khởi tạo, nhưng không nên được dùng làm đại diện cho ứng dụng được thiết kế để chia sẻ mapper.

Trong ứng dụng bình thường, tạo mapper một lần, đăng ký module/feature trước khi dùng và tái sử dụng. Có thể tạo ObjectReader/ObjectWriter cho type hoặc cấu hình cụ thể rồi tái sử dụng chúng.

## 23. Các yếu tố cấu hình có thể thay đổi số đo

Để so sánh công bằng, giữ cấu hình nhất quán giữa các benchmark:

- Cùng Jackson version và JDK.
- Cùng module, mix-in và custom serializer/deserializer.
- Cùng property naming strategy.
- Cùng date/time format và timezone behavior.
- Cùng polymorphic type configuration.
- Cùng inclusion và null policy.
- Cùng pretty printing hoặc compact output.
- Cùng sorting/order requirement.
- Cùng target Java type và validation steps.

Pretty printing, property sorting, custom date formatter hoặc polymorphic resolution có thể làm thay đổi CPU và allocation. Nếu production bật các feature đó, benchmark phải bật tương ứng.

Không so sánh một mapper tối giản với mapper production có nhiều module rồi quy toàn bộ chênh lệch cho Jackson core.

## 24. Đo nhiều thread và throughput

JMH có thể chạy benchmark nhiều thread:

~~~java
@Threads(4)
@Benchmark
public OrderEvent read(JacksonBenchmarkState state)
        throws IOException {
    return state.reader.readValue(state.jsonBytes);
}
~~~

Hoặc chọn thread count bằng tham số chạy. Với mapper đã cấu hình và tái sử dụng, Jackson hỗ trợ concurrent read/write theo thiết kế thread-safe của mapper sau khi cấu hình hoàn tất.

Tuy nhiên, benchmark đa luồng còn chịu ảnh hưởng của:

- Số core vật lý/logic.
- CPU frequency scaling và thermal throttling.
- Memory bandwidth.
- GC concurrency.
- Shared state hoặc lock do benchmark tự thêm.
- Object source có bị nhiều thread cùng mutate hay không.

Dùng @State(Scope.Thread) khi mỗi thread cần input/output riêng. Dùng Scope.Benchmark chỉ khi state thật sự được chia sẻ an toàn và muốn mô phỏng mapper dùng chung. Không để nhiều thread cùng mutate một DTO đang serialize.

Đo throughput ở nhiều mức thread count giúp phát hiện điểm bão hòa. Throughput không tăng tuyến tính mãi theo số thread; nếu allocation hoặc memory bandwidth trở thành bottleneck, thêm thread có thể không giúp.

## 25. Đo latency và tail latency

Average time có thể che giấu các operation chậm bất thường. JMH SampleTime lấy mẫu thời gian và cung cấp phân vị theo output, hữu ích cho benchmark micro-level:

~~~java
@BenchmarkMode(Mode.SampleTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class JacksonLatencyBenchmark {
    @Benchmark
    public OrderEvent read(JacksonBenchmarkState state)
            throws IOException {
        return state.reader.readValue(state.jsonBytes);
    }
}
~~~

Khi cần p95/p99 của HTTP request, hãy dùng load test hoặc telemetry ở tầng ứng dụng. JMH đo method trong một harness; nó không tự mô phỏng queueing, network, connection pool, thread pool và backpressure của production.

Để so sánh tail latency có ý nghĩa, dùng cùng request mix, concurrency, warmup và thời lượng chạy. Theo dõi cả throughput, error rate, CPU, allocation và GC.

## 26. Đo parser/generator riêng với mapping

Nếu cần biết chi phí parser/generator so với object mapping, có thể tạo benchmark riêng cho streaming API.

Ví dụ đọc và duyệt token:

~~~java
@Benchmark
public int scanTokens(JacksonBenchmarkState state)
        throws IOException {
    int fields = 0;

    try (JsonParser parser = state.mapper.getFactory()
            .createParser(state.jsonBytes)) {
        while (parser.nextToken() != null) {
            if (parser.currentToken() == JsonToken.FIELD_NAME) {
                fields++;
            }
        }
    }

    return fields;
}
~~~

Benchmark này không tạo OrderEvent; nó đo parse/scan token. So sánh nó với readValue có thể cho biết phần chi phí thêm của databinding, nhưng hai method làm lượng công việc khác nhau. Đừng gọi chênh lệch đó là overhead thuần chính xác nếu parser scan và POJO mapping không thực hiện cùng logic.

Tương tự, có thể đo JsonGenerator ghi token thủ công so với bean serializer. Khi đó, cần bảo đảm cả hai tạo ra cùng JSON contract, bao gồm null, number format, escaping và field order nếu field order thuộc yêu cầu.

## 27. Đừng để I/O, log hoặc setup lấn át phép đo

Một số lỗi benchmark phổ biến:

- Ghi JSON ra file/network trong khi mục tiêu chỉ là mapping.
- In JSON ra console trong mỗi operation.
- Đọc fixture từ disk trong mỗi invocation dù production đã giữ payload trong memory.
- Tạo DTO và collection nguồn bên trong method serialize.
- Tạo ObjectMapper trong mỗi operation nhưng so sánh với mapper đã warm.
- Chuyển String sang byte[] trong một benchmark nhưng không tính bước đó ở benchmark kia.
- Chỉ benchmark payload rất nhỏ trong khi production gửi payload lớn.
- Dùng cùng một mutable object và sửa nó từ nhiều thread.
- Chạy benchmark cùng lúc với build, antivirus scan hoặc tác vụ CPU nặng.

Nếu cần đo I/O, hãy đo riêng hoặc thiết kế benchmark tích hợp có chủ đích. Ghi rõ setup nào nằm ngoài phép đo và setup nào được tính vào operation.

## 28. Đọc kết quả JMH đúng cách

JMH thường báo score, error/confidence interval và đơn vị. Ví dụ minh họa:

~~~text
Benchmark                 Mode  Cnt   Score   Error  Units
writeString               avgt   24  18.20 ± 0.60  us/op
readBytes                 avgt   24  19.90 ± 0.70  us/op
~~~

Đọc kết quả:

- Mode: loại phép đo, ví dụ avgt là average time.
- Cnt: số measurement sample/iteration được tổng hợp theo output.
- Score: kết quả trung bình theo đơn vị.
- Error: khoảng sai số được báo theo cách JMH tổng hợp.
- Units: đơn vị như us/op, ops/s.

Khi so sánh, hãy nhìn cả score lẫn error. Nếu hai benchmark có khoảng dao động chồng lấn đáng kể, chênh lệch nhỏ có thể không đủ cơ sở để chọn implementation khác.

Đừng chỉ lấy lần chạy nhanh nhất. Báo cáo kết quả cùng JDK, Jackson version, CPU, OS, GC, heap flags, payload size, thread count và command chạy.

## 29. Tính allocation rate từ bytes/op và throughput

Nếu benchmark cho biết:

- Allocation trung bình: 6 KB/op.
- Throughput: 15.000 op/s.

Allocation rate gần đúng:

~~~text
6 KB/op × 15.000 op/s = 90.000 KB/s ≈ 87,9 MiB/s
~~~

Đây là lượng memory được cấp phát theo thời gian, không phải heap live size. Nếu throughput tăng gấp đôi mà bytes/op không đổi, allocation rate cũng gần gấp đôi.

Công thức tổng quát:

~~~text
allocation_rate ≈ allocated_bytes_per_operation × operations_per_second
~~~

Dùng cùng đơn vị byte và giây khi tính. Kết quả giúp ước lượng áp lực allocation ở tải dự kiến, nhưng thời gian GC thực tế còn phụ thuộc collector, heap, object lifetime, CPU và phân bố tải.

## 30. So sánh streaming, tree và databinding công bằng

Một phép so sánh tốt phải thực hiện cùng mục tiêu nghiệp vụ. Ví dụ, nếu mục tiêu là lấy orderId và tổng số item:

- POJO: deserialize toàn bộ OrderEvent, sau đó đọc hai field.
- Tree: readTree, sau đó truy cập hai node.
- Streaming: scan token và lấy đúng field cần thiết.

Không so sánh chỉ riêng readTree() với readValue() nếu sau đó một bên phải duyệt tree còn bên kia không cần bước đó.

Nếu mục tiêu là xây dựng toàn bộ domain object, streaming implementation phải tạo ra object graph tương đương và thực hiện validation giống POJO path. Nếu không, kết quả chỉ phản ánh lượng công việc khác nhau.

## 31. Benchmark custom serializer/deserializer

Custom serializer có thể tăng hoặc giảm allocation tùy cách triển khai. Ví dụ serializer tạo chuỗi trung gian:

~~~java
gen.writeString(value.getCurrency() + " " + value.getAmount());
~~~

có thể tạo String mới. Một cách ghi trực tiếp token/field có thể tránh một số String trung gian:

~~~java
gen.writeStartObject();
gen.writeStringField("currency", value.getCurrency());
gen.writeNumberField("amount", value.getAmount());
gen.writeEndObject();
~~~

Đây chỉ là ví dụ về hai shape khác nhau, không phải output tương đương. Muốn so sánh hiệu năng, phải giữ JSON contract giống nhau và chỉ thay đổi cách thực hiện.

Với deserializer, đo riêng parse token, tạo object, parse number/date/string, validation, lookup enum/subtype và tạo collection/nested object. Không bỏ validation khỏi một implementation chỉ để nó có số đo nhanh hơn nếu production cần validation đó.

## 32. Kiểm tra kết quả bằng integration benchmark

Sau microbenchmark, cần xác nhận lợi ích trong luồng gần production:

1. Dùng đúng mapper bean và module của ứng dụng.
2. Dùng payload distribution gần traffic thực.
3. Đo request throughput, latency và error rate.
4. Theo dõi CPU, allocation, GC và memory.
5. Kiểm tra response bytes và semantics không đổi.
6. Chạy với concurrency và resource limit tương tự môi trường triển khai.

Một tối ưu giúp writeValueAsBytes() nhanh hơn 10% có thể không làm endpoint nhanh hơn nếu database/network chiếm phần lớn request time. Ngược lại, giảm 20% allocation/op có thể rất có giá trị khi endpoint được gọi hàng chục nghìn lần mỗi giây.

## 33. Các lỗi thường gặp khi đo hiệu năng

| Hiện tượng | Nguyên nhân | Cách cải thiện |
|---|---|---|
| Lần đầu chậm, lần sau nhanh | Class loading, JIT và cache chưa warm | Dùng warmup và fork của JMH |
| Kết quả dao động mạnh | Iteration ngắn, GC, CPU contention | Tăng thời lượng, chạy fork riêng, giảm tác vụ nền |
| Số đo quá nhanh bất thường | Kết quả không được tiêu thụ hoặc dead-code elimination | Trả kết quả hoặc dùng Blackhole |
| Benchmark ghi nhanh nhưng API vẫn chậm | Đo String memory, production dùng network/stream | Thêm benchmark tích hợp |
| Heap không tăng nhưng GC nhiều | Object tạm được tạo và thu gom nhanh | Đo bytes/op và allocation rate |
| Map/tree tốn nhiều memory | Tạo cấu trúc tổng quát và nhiều node/entry | So sánh DTO hoặc streaming theo nhu cầu |
| Mapper mới chậm hơn nhiều | Đang tính chi phí khởi tạo/cache | Tách startup benchmark và steady-state |
| Multi-thread không tăng throughput | CPU, memory bandwidth, GC hoặc shared state bão hòa | Đo nhiều thread count và profile |
| Hai implementation nhanh khác nhau nhưng output khác | Workload/semantics không tương đương | So sánh cùng contract và cùng validation |
| Kết quả không lặp lại | JDK/Jackson/config/flags khác nhau | Ghi môi trường và pin dependency |

## 34. Quy trình đo một thay đổi Jackson

Khi thay serializer, module, cấu hình hoặc kiểu target, hãy dùng quy trình:

1. Xác định câu hỏi: latency, throughput, allocation/op hay cold start.
2. Chọn phạm vi: mapping thuần, String/byte, stream hay end-to-end.
3. Chuẩn bị payload đại diện và fixture cố định.
4. Tạo JMH state; khởi tạo mapper, reader, writer và input ngoài measurement.
5. Tách read benchmark và write benchmark.
6. Chạy warmup, measurement và nhiều fork.
7. Chạy GC profiler để lấy bytes/op và GC metrics.
8. Nếu cần, dùng JFR để tìm class/method gây allocation hoặc CPU hotspot.
9. So sánh output semantics và validation của các implementation.
10. Chạy integration/load test trước khi quyết định tối ưu có lợi cho production.

Giữ kết quả benchmark trong repository hoặc CI artifact cùng metadata môi trường. Không đặt một ngưỡng tuyệt đối quá chặt trên mọi máy build nếu hardware và runtime không cố định; có thể dùng benchmark regression trend trên runner ổn định.

## 35. Ghi nhớ

Đo hiệu năng Jackson cần tách thời gian đọc, thời gian ghi và chi phí cấp phát. Dùng JMH để kiểm soát warmup, measurement, fork và dead-code elimination. Chuẩn bị mapper, DTO và JSON trong setup; benchmark riêng String, byte[] và stream theo đúng representation mà ứng dụng dùng.

Dùng -prof gc để xem allocation bytes/op, allocation rate và GC. Dùng JFR khi cần tìm class hoặc stack trace tạo object. So sánh POJO, Map, JsonNode và streaming chỉ khi chúng làm cùng lượng công việc. Tái sử dụng ObjectMapper đã cấu hình, đồng thời benchmark startup/cold path riêng nếu đó là mối quan tâm.

Microbenchmark giúp giải thích chi phí của Jackson; integration benchmark và load test mới cho biết lợi ích đó ảnh hưởng thế nào đến request thực. Luôn giữ payload, mapper configuration, JDK, Jackson version, thread count và môi trường chạy nhất quán khi so sánh.
