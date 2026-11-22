# Giữ cấu hình và kiểu dữ liệu đại diện khi đo hiệu năng

Đo hiệu năng serialization chỉ có ý nghĩa khi benchmark mô phỏng đúng công việc ứng dụng thực sự làm. Nếu benchmark dùng một DTO quá đơn giản, một payload rất nhỏ hoặc một mapper được tạo mới trong mỗi lần gọi, kết quả có thể dẫn đến quyết định sai về Jackson, định dạng JSON/Smile/CBOR hoặc cách cấu hình mapper.

Một phép đo đáng tin cậy cần giữ ổn định hai thứ: **cấu hình serialization** và **kiểu dữ liệu đại diện**. Cấu hình gồm mapper, module, annotation, naming strategy, serializer/deserializer, feature và cách tạo parser/generator. Kiểu dữ liệu đại diện gồm DTO, object lồng nhau, collection, map, kiểu số/ngày giờ, binary value và phân bố kích thước dữ liệu giống production.

Bài học này trình bày cách xây dựng benchmark có thể lặp lại, dùng JMH để đo, chuẩn bị fixture trước vùng đo, so sánh các mapper trên cùng workload, tách chi phí parse/bind/encode/transport, và đọc kết quả cùng allocation/GC thay vì chỉ nhìn một con số ops/second.

## 1. Benchmark phải trả lời một câu hỏi cụ thể

Trước khi viết benchmark, hãy xác định quyết định kỹ thuật cần hỗ trợ. Ví dụ:

- JSON hay Smile/CBOR phù hợp hơn cho event message?
- Đọc bằng byte array có nhanh hơn đọc bằng String trong luồng hiện tại không?
- Một custom serializer có tạo overhead đáng kể không?
- Dùng record hay mutable bean có ảnh hưởng tới mapping không?
- Tái sử dụng ObjectReader/ObjectWriter có thay đổi chi phí không?
- Payload có nested collection lớn gây allocation ở đâu?
- Nâng phiên bản Jackson có làm throughput hoặc allocation thay đổi không?

Mỗi câu hỏi cần một workload tương ứng. Nếu muốn so sánh format, phải dùng cùng dữ liệu logic và cùng cách xử lý đầu vào/đầu ra. Nếu muốn so sánh kiểu DTO, phải giữ format, mapper feature và payload distribution như nhau.

Không nên gom mọi thay đổi vào một benchmark duy nhất rồi kết luận nguyên nhân. Ví dụ đổi JSON sang CBOR, đổi DTO mutable sang record, bật custom serializer và thay luôn kích thước payload sẽ khiến kết quả không cho biết yếu tố nào tạo ra chênh lệch.

Một benchmark tốt thay đổi một biến có chủ đích, giữ các biến còn lại cố định và ghi rõ điều kiện đo.

## 2. Hai yếu tố phải đại diện: cấu hình và kiểu dữ liệu

### 2.1. Cấu hình serialization

Cấu hình thực tế có thể gồm:

- Jackson Core, Databind, Annotations và module version.
- ObjectMapper và JsonFactory cụ thể.
- JavaTimeModule hoặc module datatype khác.
- Naming strategy và visibility.
- SerializationFeature, DeserializationFeature và MapperFeature.
- Null handling, inclusion và coercion.
- Custom serializer/deserializer và key serializer.
- Polymorphic typing, subtype resolver và type metadata.
- StreamReadConstraints/StreamWriteConstraints nếu ứng dụng dùng.
- ObjectReader/ObjectWriter hoặc cách gọi mapper trong production.
- Đường dữ liệu: String, byte array, InputStream, OutputStream hay parser/generator trực tiếp.

Nếu production dùng Spring Boot auto-configured mapper có nhiều module và mix-in, benchmark bằng một ObjectMapper mới hoàn toàn có thể không phản ánh chi phí thực tế. Ngược lại, nếu benchmark thêm nhiều module mà production không dùng, kết quả cũng không còn đại diện.

### 2.2. Kiểu dữ liệu và phân bố payload

Một DTO thực tế thường không chỉ có vài field String. Nó có thể gồm:

- Object lồng nhau nhiều cấp.
- List/Set có số lượng phần tử khác nhau.
- Map có nhiều key/value.
- BigDecimal, BigInteger và số nguyên lớn.
- Instant, LocalDate, OffsetDateTime.
- Enum và polymorphic subtype.
- byte[] hoặc nội dung binary.
- Field null, field thiếu, field có default.
- String ngắn, string dài, string lặp lại hoặc có cardinality cao.
- Custom value object như Money, EmailAddress hoặc CustomerId.

Kiểu dữ liệu đại diện không có nghĩa là phải sao chép nguyên dữ liệu production nhạy cảm. Có thể dùng fixture đã ẩn danh hoặc dữ liệu tổng hợp có phân bố giống thật.

## 3. Tránh benchmark DTO quá đơn giản

Một ví dụ quá nhỏ:

```java
public record Person(String name, int age) {}
```

và payload:

```json
{
  "name": "An",
  "age": 28
}
```

có thể hữu ích để xác nhận benchmark hoạt động, nhưng không đủ để kết luận về hệ thống có event lớn, nested object, list và custom type.

Ví dụ một model gần với message nghiệp vụ hơn:

```java
public record OrderEvent(
    String eventId,
    Instant occurredAt,
    CustomerSnapshot customer,
    List<LineItem> items,
    Map<String, String> attributes,
    BigDecimal total,
    byte[] attachment
) {}

public record CustomerSnapshot(
    String customerId,
    String displayName,
    String email,
    CustomerTier tier
) {}

public record LineItem(
    String sku,
    int quantity,
    BigDecimal unitPrice,
    List<String> labels
) {}

public enum CustomerTier {
    STANDARD,
    PREMIUM,
    ENTERPRISE
}
```

Model này tạo ra nhiều loại công việc cho Databind: constructor/record binding, nested object, collection, map, enum, decimal, Java Time và binary data.

Không cần mọi benchmark đều dùng một model lớn. Nên có nhiều profile: payload nhỏ thường gặp, payload trung bình đại diện và payload lớn ở gần giới hạn thực tế.

## 4. Giữ cấu hình mapper cố định trong toàn bộ phép đo

ObjectMapper được thiết kế để tái sử dụng sau khi cấu hình hoàn tất. Jackson có thể cache serializer/deserializer và metadata của kiểu. Tạo mapper mới trong mỗi lần benchmark làm phép đo bao gồm chi phí khởi tạo và bỏ qua lợi ích cache mà production thường có.

Ví dụ không phù hợp để đo chi phí đọc/ghi thường xuyên:

```java
@Benchmark
public byte[] serializeBad() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.writeValueAsBytes(event);
}
```

Benchmark trên đo cả việc tạo mapper, khởi tạo factory, cấu hình mặc định và serialize. Nó trả lời câu hỏi về cold setup, không phải chi phí serialization steady-state.

Mẫu phù hợp hơn:

```java
@State(Scope.Thread)
public class MapperState {

    private ObjectMapper mapper;
    private OrderEvent event;

    @Setup(Level.Trial)
    public void setup() {
        mapper = createProductionLikeMapper();
        event = createRepresentativeEvent();
    }

    @Benchmark
    public byte[] serialize() throws Exception {
        return mapper.writeValueAsBytes(event);
    }
}
```

Mapper được tạo một lần trong setup của trial. Benchmark method chỉ thực hiện công việc cần đo.

Nếu muốn đo chi phí khởi tạo mapper, hãy tạo benchmark riêng với tên và mục tiêu rõ ràng. Không trộn startup benchmark với throughput benchmark.

## 5. Cấu hình phải giống production

Ví dụ mapper có Java Time module, naming strategy và feature:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Nếu production dùng custom serializer cho Money hoặc @JsonTypeInfo cho event subtype, benchmark cũng cần dùng chúng. Nếu production có mix-in, visibility override hoặc null policy, cần giữ lại.

Không nên thêm module chỉ vì benchmark muốn “thử Jackson đầy đủ”. Mỗi module có thể thay đổi serializer được chọn, startup metadata hoặc cách xử lý kiểu. Cấu hình cần được ghi nhận như một phần của kết quả.

Khi so sánh hai phiên bản Jackson:

1. Giữ cùng DTO và fixture.
2. Giữ cùng feature và module tương đương.
3. Giữ cùng JDK, JVM options và hardware.
4. Chỉ thay phiên bản thư viện được kiểm tra.
5. Xác nhận output/semantic correctness trước khi so sánh tốc độ.

Nếu version mới thay đổi behavior hoặc API, ghi lại khác biệt đó. Không ép cấu hình cũ vào version mới theo cách khiến hai mapper không còn tương đương.

## 6. Giữ cách giải quyết kiểu dữ liệu giống nhau

Khi benchmark một DTO, hãy dùng đúng target type trong cả setup và timed method.

Ví dụ đọc generic list:

```java
List<OrderEvent> events = mapper.readValue(
    jsonBytes,
    new TypeReference<List<OrderEvent>>() {}
);
```

Nếu production dùng JavaType, benchmark cũng nên tạo type tương ứng và quyết định rõ việc tạo JavaType có nằm trong vùng đo hay không.

Có thể tạo trước:

```java
JavaType eventListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, OrderEvent.class);
```

rồi dùng lại:

```java
List<OrderEvent> events =
    mapper.readValue(jsonBytes, eventListType);
```

Hai cách có thể có chi phí khác nhau nếu type construction diễn ra trong mỗi lần gọi. Không benchmark một cách tạo type trước rồi so với cách tạo type trong timed method mà không ghi rõ đó là hai workload khác nhau.

Tương tự, nếu production dùng ObjectReader đã tạo trước:

```java
ObjectReader eventReader = mapper.readerFor(OrderEvent.class);
```

thì benchmark nên đo reader đó. Nếu production gọi mapper.readValue(bytes, OrderEvent.class), hãy đo đúng đường đó. Chọn API theo workload thực tế, không theo giả định rằng một API luôn nhanh hơn.

## 7. Chuẩn bị dữ liệu ngoài vùng đo

Việc tạo fixture thường tốn thời gian và allocation. Nếu mục tiêu là đo deserialize, không nên tạo JSON ngay trong benchmark method rồi mới parse; nếu mục tiêu là serialize, không nên xây object graph trong vùng đo.

Chuẩn bị trước trong @Setup(Level.Trial):

```java
@Setup(Level.Trial)
public void setup() throws Exception {
    mapper = createProductionLikeMapper();
    event = createRepresentativeEvent();

    jsonBytes = mapper.writeValueAsBytes(event);
}
```

Sau đó benchmark đọc:

```java
@Benchmark
public OrderEvent readJson() throws Exception {
    return mapper.readValue(jsonBytes, OrderEvent.class);
}
```

Benchmark ghi:

```java
@Benchmark
public byte[] writeJson() throws Exception {
    return mapper.writeValueAsBytes(event);
}
```

Hai benchmark có vùng đo khác nhau:

- Read benchmark gồm tạo parser, đọc token, bind object và allocation của object graph.
- Write benchmark gồm serializer, generator, buffer và tạo output bytes.
- Cả hai không bao gồm việc tạo dữ liệu mẫu trong setup.

Nếu production phải tải dữ liệu từ file, đọc từ socket hoặc giải nén trước khi parse, có thể tạo benchmark end-to-end riêng để đo toàn bộ pipeline. Hãy đặt tên rõ để không nhầm kết quả parser-only với transport-plus-parser.

## 8. Dùng JMH thay cho vòng lặp nanoTime tự viết

JMH (Java Microbenchmark Harness) xử lý nhiều vấn đề của microbenchmark JVM:

- Warmup để JIT biên dịch code nóng.
- Nhiều measurement iteration.
- Fork JVM để giảm ảnh hưởng trạng thái từ lần chạy trước.
- Điều phối benchmark method và tránh một số dạng dead-code elimination.
- Cung cấp mode đo throughput, average time và sample time.
- Hỗ trợ profiler cho allocation và GC.

Một vòng lặp tự viết:

```java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    mapper.writeValueAsBytes(event);
}

long elapsed = System.nanoTime() - start;
```

có thể sai lệch do JIT, GC, dead-code elimination, warmup, CPU frequency, background process và cách chọn số vòng lặp. Dùng System.nanoTime() phù hợp cho timing đơn giản trong ứng dụng, nhưng không phải nền tảng tốt cho kết luận microbenchmark JVM.

JMH không loại bỏ mọi sai số. Nó cung cấp phương pháp có kiểm soát hơn; người viết vẫn phải chọn workload, state, mode và môi trường đúng.

## 9. Cấu hình benchmark JMH cơ bản

Ví dụ class benchmark:

```java
import org.openjdk.jmh.annotations.*;

import java.util.concurrent.TimeUnit;

@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
@State(Scope.Thread)
public class JacksonFormatBenchmark {

    // Mapper, fixture và benchmark methods
}
```

Ý nghĩa:

| Annotation | Mục đích |
| --- | --- |
| @BenchmarkMode(Mode.Throughput) | Đo số operation hoàn thành trong một đơn vị thời gian |
| @OutputTimeUnit(TimeUnit.SECONDS) | Hiển thị throughput theo giây |
| @Warmup | Cho JVM và JIT ổn định trước khi lấy kết quả |
| @Measurement | Số iteration được dùng để đo |
| @Fork(3) | Chạy nhiều JVM fork độc lập |
| @State(Scope.Thread) | Mỗi benchmark thread có state riêng |

Các giá trị warmup/measurement/fork là điểm bắt đầu, không phải hằng số cho mọi dự án. Benchmark lâu hơn có thể cần nhiều iteration; thao tác rất ngắn có thể cần thời gian đo đủ dài.

Không chạy benchmark trong IDE khi đang debug hoặc có nhiều workload khác chiếm CPU. Nên chạy trên máy ít tải, ghi lại JDK/JVM options và giữ điều kiện giữa các lần so sánh.

## 10. Ví dụ benchmark JSON, Smile và CBOR trên cùng dữ liệu

Để so sánh format, chuẩn bị ba mapper và ba payload từ cùng một object. Ví dụ skeleton:

```java
@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class FormatBenchmark {

    private ObjectMapper jsonMapper;
    private ObjectMapper smileMapper;
    private ObjectMapper cborMapper;

    private OrderEvent event;

    private byte[] jsonBytes;
    private byte[] smileBytes;
    private byte[] cborBytes;

    @Setup(Level.Trial)
    public void setup() throws Exception {
        jsonMapper = createJsonMapper();
        smileMapper = createSmileMapper();
        cborMapper = createCborMapper();

        event = createRepresentativeEvent();

        jsonBytes = jsonMapper.writeValueAsBytes(event);
        smileBytes = smileMapper.writeValueAsBytes(event);
        cborBytes = cborMapper.writeValueAsBytes(event);

        verifyEquivalentPayloads();
    }

    @Benchmark
    public OrderEvent readJson() throws Exception {
        return jsonMapper.readValue(jsonBytes, OrderEvent.class);
    }

    @Benchmark
    public OrderEvent readSmile() throws Exception {
        return smileMapper.readValue(smileBytes, OrderEvent.class);
    }

    @Benchmark
    public OrderEvent readCbor() throws Exception {
        return cborMapper.readValue(cborBytes, OrderEvent.class);
    }

    @Benchmark
    public byte[] writeJson() throws Exception {
        return jsonMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] writeSmile() throws Exception {
        return smileMapper.writeValueAsBytes(event);
    }

    @Benchmark
    public byte[] writeCbor() throws Exception {
        return cborMapper.writeValueAsBytes(event);
    }
}
```

Điểm quan trọng:

- Cùng một object logic được dùng cho ba format.
- Fixture đọc được tạo trước khi measurement bắt đầu.
- Mapper được tạo và cấu hình trong setup.
- Read và write là benchmark method riêng.
- Kết quả trả về được JMH tiêu thụ để tránh code bị loại bỏ.
- verifyEquivalentPayloads() chạy ngoài vùng đo để xác nhận các format tạo ra dữ liệu nghiệp vụ tương đương.

Đây là skeleton để tổ chức benchmark; các helper tạo mapper, fixture và so sánh cần được viết theo model thực tế của ứng dụng.

## 11. Không để benchmark vô tình đo việc tạo mapper

Nếu muốn đo startup, hãy tạo benchmark riêng:

```java
@State(Scope.Thread)
public class MapperStartupBenchmark {

    @Benchmark
    public ObjectMapper createMapper() {
        return createProductionLikeMapper();
    }
}
```

Benchmark này trả lời câu hỏi về chi phí tạo mapper. Nó không thay thế benchmark serialize/deserialize steady-state.

Trong production, mapper thường được tạo một lần khi khởi động và tái sử dụng. Nếu mỗi request tạo mapper mới, đó có thể là vấn đề thiết kế hoặc dependency injection. Không lấy kết quả startup benchmark để tuyên bố Jackson serialize chậm.

## 12. Giữ payload distribution đại diện

Một payload duy nhất không đủ để đại diện cho workload có nhiều kích thước. Nên chia profile dựa trên dữ liệu thực tế, ví dụ:

| Profile | Đặc điểm minh họa | Mục tiêu |
| --- | --- | --- |
| SMALL | Vài field, list ngắn, ít nested object | Request thường gặp |
| MEDIUM | Nhiều nested object, list/map vừa phải | Workload điển hình |
| LARGE | Collection lớn, string/binary dài, nested graph sâu hơn | Payload lớn nhưng hợp lệ |

Có thể dùng @Param:

```java
@Param({"SMALL", "MEDIUM", "LARGE"})
public String profile;
```

Trong setup, tạo fixture tương ứng. Cần ghi lại chính xác số item, độ dài string, kích thước byte array và số tầng nesting để kết quả có thể tái tạo.

Nếu production có phân bố như 80% small, 18% medium và 2% large, có thể báo cáo từng profile riêng và thêm một workload hỗn hợp có trọng số gần thực tế. Không lấy trung bình số học đơn giản của throughput các profile nếu tần suất thực tế khác nhau.

### 12.1. Dữ liệu tổng hợp cần giữ phân bố, không chỉ giữ tổng kích thước

Hai payload có cùng số byte có thể tạo chi phí rất khác:

- Một string lớn khác với hàng nghìn string ngắn.
- Một list lớn khác với nhiều object lồng nhau.
- Tên field lặp lại nhiều khác với tên field có cardinality cao.
- Binary payload khác với text Base64.
- Một object có nhiều null khác với object có đủ field.
- Một map nhỏ có key phức tạp khác với map string key thông thường.

Nếu dữ liệu tổng hợp chỉ giữ tổng kích thước mà bỏ qua cấu trúc, benchmark có thể không đại diện.

## 13. Những kiểu dữ liệu cần có trong workload

Hãy chọn kiểu dựa trên ứng dụng, nhưng các nhóm sau thường đáng cân nhắc:

| Nhóm | Ví dụ | Chi phí cần quan sát |
| --- | --- | --- |
| Scalar | String, int, boolean | Token parse, conversion |
| Decimal | BigDecimal, BigInteger | Parse số, precision, allocation |
| Date/time | Instant, LocalDate, OffsetDateTime | Module lookup, parse/format |
| Enum | Enum code, custom creator | String matching và lookup |
| Nested bean | Customer, Address | Object creation, property binding |
| Collection | List, Set | Số item, container allocation |
| Map | Map<String, Value> | Key parsing và map insertion |
| Binary | byte[] | Binary token hoặc Base64 conversion |
| Polymorphic | Base type + subtype | Type id lookup và subtype creation |
| Custom value object | Money, Identifier | Custom serializer/deserializer |

Không phải benchmark nào cũng cần tất cả. Chỉ đưa các kiểu có mặt trong workload mục tiêu và ghi rõ phần nào được bỏ qua.

## 14. Giữ null, missing và default giống production

Null handling có thể ảnh hưởng cả thời gian lẫn ngữ nghĩa. Một payload mà mọi field đều có giá trị sẽ không đại diện cho hệ thống có nhiều optional property.

Cần xác định tỷ lệ:

- Property luôn có mặt.
- Property bị thiếu.
- Property có giá trị null.
- Property có giá trị default như false, 0 hoặc empty string.
- Collection rỗng so với collection null.

Với benchmark read, tạo fixture có phân bố tương ứng. Với benchmark write, tạo object graph có tỷ lệ null tương ứng.

Không thay payload null bằng empty string chỉ để benchmark dễ hơn. Điều đó có thể thay đổi serializer path và làm thay đổi kích thước output.

Nếu muốn đo riêng một trường hợp null-heavy, đặt tên benchmark rõ ràng thay vì gộp nó vào workload trung bình.

## 15. Custom serializer/deserializer phải được giữ lại nếu production dùng

Ví dụ production có:

```java
@JsonSerialize(using = MoneySerializer.class)
@JsonDeserialize(using = MoneyDeserializer.class)
private Money total;
```

thì benchmark bỏ annotation/module này đang đo một workload khác.

Custom serializer có thể thêm:

- Kiểm tra null.
- Chuyển đổi scale hoặc currency.
- Ghi nested object.
- Tạo string tạm.
- Parse nhiều field.
- Tra cứu context hoặc property annotation.

Nếu custom code là một phần của đường dữ liệu thực tế, phải giữ nguyên trong benchmark. Nếu mục tiêu là đo overhead của custom serializer, tạo cặp benchmark đối chứng:

1. Mapper dùng serializer mặc định hoặc DTO tương đương.
2. Mapper dùng custom serializer.
3. Cùng fixture và cùng contract.
4. Xác nhận output tương đương trước khi so sánh.

Không dùng custom serializer chỉ ở một phía khi đang tuyên bố so sánh JSON với CBOR/Smile tổng thể.

## 16. Polymorphism và generic type resolution

Một số hệ thống nhận nhiều subtype qua base type:

```java
public sealed interface DomainEvent
    permits CustomerCreated, CustomerUpdated {
}

public record CustomerCreated(String customerId)
    implements DomainEvent {}

public record CustomerUpdated(String customerId, String name)
    implements DomainEvent {}
```

Nếu production dùng @JsonTypeInfo, subtype resolver hoặc default typing có kiểm soát, benchmark cần giữ cấu hình đó. Type id lookup và construction có thể ảnh hưởng đáng kể.

Với generic type, phải giữ đúng JavaType hoặc TypeReference. Đọc raw List.class rồi cast sau không tương đương với deserialize trực tiếp List<OrderEvent>; nó có thể tạo Map/List lồng nhau thay vì object mong muốn.

Nếu ứng dụng có nhiều subtype, dùng distribution subtype giống production. Benchmark chỉ một subtype sẽ không đo chi phí lookup và phân bố thực tế.

## 17. Phân biệt byte[], String và InputStream

Đường input/output có thể thay đổi kết quả đáng kể:

| Đường đọc | Công việc được tính trong benchmark |
| --- | --- |
| readValue(String, Type) | Parser tạo từ String/character source và databind |
| readValue(byte[], Type) | Parser từ bytes và databind |
| readValue(InputStream, Type) | Đọc stream, parser và databind |
| Parser token trực tiếp | Parse token, không nhất thiết tạo object graph |
| readTree(...) | Parse thành tree node thay vì DTO |

Với JSON, đọc từ String có thể bỏ qua một phần byte-to-character decoding nếu upstream đã có String. Nhưng production có thể nhận request body dưới dạng bytes/stream; benchmark cần theo đúng đường đó.

Tương tự, writeValueAsString và writeValueAsBytes có chi phí output khác nhau. Binary format nên dùng bytes hoặc stream. Không so sánh JSON String output với Smile byte output rồi quy mọi chênh lệch cho serializer.

Nếu muốn đo encoding UTF-8, có thể benchmark riêng bước chuyển String thành bytes. Nếu muốn đo toàn bộ HTTP path, đo từ request bytes đến response bytes trong integration/load test riêng.

## 18. Tách parse-only, databind và end-to-end

Một benchmark read bằng ObjectMapper.readValue gồm parser và Databind. Nếu cần tìm bottleneck, có thể tách:

1. **Token parsing**: tạo JsonParser và đi qua token.
2. **Tree binding**: đọc thành JsonNode.
3. **POJO binding**: đọc thành DTO.
4. **Custom mapping**: chạy serializer/deserializer đặc thù.
5. **Transport path**: nhận bytes, giải nén, parse, validate và xử lý.

Tương tự với write:

1. Tạo token bằng generator trực tiếp.
2. Serialize POJO bằng Databind.
3. Serialize ra byte buffer.
4. Ghi ra stream/file.
5. Nén hoặc đóng gói message.

Không dùng parse-only để kết luận toàn bộ API nhanh hơn. Parse-only có thể loại bỏ chi phí object creation, validation hoặc transport vốn chiếm phần lớn thời gian production.

## 19. Không để dữ liệu bị tối ưu hóa hoặc benchmark thành no-op

Benchmark cần thực sự sử dụng kết quả.

Ví dụ không tốt:

```java
@Benchmark
public void readButIgnore() throws Exception {
    mapper.readValue(jsonBytes, OrderEvent.class);
}
```

JMH có cơ chế hỗ trợ benchmark method, nhưng tốt hơn là trả về kết quả hoặc dùng Blackhole khi cần tiêu thụ nhiều kết quả:

```java
@Benchmark
public OrderEvent read() throws Exception {
    return mapper.readValue(jsonBytes, OrderEvent.class);
}
```

Với một benchmark có nhiều kết quả:

```java
@Benchmark
public void readMany(Blackhole blackhole) throws Exception {
    for (byte[] payload : payloads) {
        blackhole.consume(
            mapper.readValue(payload, OrderEvent.class)
        );
    }
}
```

Không tự thêm vòng lặp lớn bên trong benchmark nếu không có lý do. JMH đã lặp benchmark method; batch benchmark chỉ phù hợp khi workload production thực sự xử lý batch và overhead invocation cần được phản ánh.

## 20. Warmup, measurement và fork

JVM dùng JIT compiler, profile và runtime optimization. Những lần chạy đầu thường chưa đại diện steady-state.

- Warmup cho JVM thực hiện class loading, profiling và compilation.
- Measurement thu thập dữ liệu sau warmup.
- Fork chạy benchmark trong JVM riêng để giảm ảnh hưởng trạng thái.
- Nhiều iteration giúp quan sát độ dao động.

Một benchmark chạy một lần trong vài mili giây thường không đủ cơ sở để kết luận.

Nếu ứng dụng quan tâm startup latency hoặc cold path, hãy đo riêng bằng benchmark phù hợp, có thể là single-shot hoặc integration startup measurement. Đừng cố dùng một bộ warmup steady-state để trả lời câu hỏi cold start.

## 21. Đo allocation và GC, không chỉ throughput

Serialization thường tạo nhiều object tạm: parser, token buffer, String, collection, DTO và output byte array. Hai cấu hình có throughput gần nhau vẫn có thể tạo allocation rất khác.

Chạy JMH với GC profiler:

```bash
java -jar target/benchmarks.jar FormatBenchmark -prof gc
```

Các chỉ số thường quan tâm:

- gc.alloc.rate: tốc độ allocation.
- gc.alloc.rate.norm: byte allocation trung bình trên mỗi operation.
- gc.count: số lần GC trong khoảng đo.
- gc.time: tổng thời gian GC.

Nếu một format giảm thời gian serialize một ít nhưng tạo allocation nhiều hơn đáng kể, dưới tải concurrent có thể làm tăng GC pressure và tail latency.

JMH GC profiler giúp quan sát allocation/GC trong benchmark. Nó không thay thế profiling ứng dụng production, nơi heap size, concurrency, request mix và pause behavior có thể khác.

## 22. Đo throughput, latency và kích thước riêng

Các metric trả lời câu hỏi khác nhau:

| Metric | Ý nghĩa |
| --- | --- |
| Throughput | Số operation hoàn thành mỗi giây |
| Average time | Thời gian trung bình cho một operation |
| Sample time | Phân bố thời gian sample, có thể xem percentile |
| Allocation/op | Lượng bộ nhớ cấp phát trung bình mỗi operation |
| Output bytes | Kích thước payload được serialize |
| CPU utilization | Mức CPU dùng trong workload |
| End-to-end latency | Thời gian từ đầu đến cuối trong hệ thống thực |

Không suy ra payload nhỏ hơn từ throughput cao hơn. Hãy đo output size riêng:

```java
int jsonSize = jsonBytes.length;
int smileSize = smileBytes.length;
int cborSize = cborBytes.length;
```

Khi báo cáo, nêu rõ output size của cùng một fixture. Nếu có compression, báo kích thước trước và sau nén riêng; đừng gộp binary serialization và compression thành một kết luận không phân biệt.

## 23. Benchmark streaming phải mô phỏng đúng sink

Nếu production ghi vào HTTP response hoặc file, writeValueAsBytes có thể không đại diện hoàn toàn vì nó tạo byte array trong bộ nhớ.

Có thể đo stream path:

```java
@State(Scope.Thread)
public class StreamWriteState {

    private ObjectMapper mapper;
    private OrderEvent event;
    private ByteArrayOutputStream output;

    @Setup(Level.Trial)
    public void setup() {
        mapper = createProductionLikeMapper();
        event = createRepresentativeEvent();
        output = new ByteArrayOutputStream();
    }

    @Benchmark
    public int writeToBuffer() throws Exception {
        output.reset();
        mapper.writeValue(output, event);
        return output.size();
    }
}
```

Cách này tái sử dụng buffer nên không đo cùng allocation pattern với writeValueAsBytes. Điều đó không sai nếu production cũng tái sử dụng buffer, nhưng phải ghi rõ. Nếu production tạo buffer mới mỗi request, benchmark cũng cần mô phỏng điều đó.

Không dùng network thật trong microbenchmark cơ bản vì độ trễ mạng, socket buffer và server scheduling sẽ che chi phí serializer. Hãy dùng JMH cho phần encode/decode, rồi dùng load/integration test để đo network end-to-end.

## 24. Compression cần benchmark riêng hoặc pipeline riêng

Smile/CBOR và gzip/zstd giải quyết những lớp khác nhau. Nếu muốn so sánh:

- JSON không nén.
- JSON + gzip.
- Smile không nén.
- CBOR không nén.
- Smile + gzip.
- CBOR + gzip.

hãy đo cả encode/decode time và byte size. Compression có thể giảm payload nhưng tăng CPU và allocation. Dữ liệu đã compact có thể không giảm nhiều sau nén.

Tạo benchmark riêng cho compression-only nếu cần tìm chi phí thuật toán. Sau đó đo pipeline end-to-end gồm serialize, compress, decompress và deserialize. Giữ cùng mức compression, dictionary, buffer size và dữ liệu đầu vào giữa các lần so sánh.

Không so sánh JSON + gzip với CBOR không nén rồi kết luận format nào nhanh hơn mà không nói rõ trade-off.

## 25. Cẩn thận với việc chọn một payload lặp đi lặp lại

Dùng cùng một payload trong mọi invocation giúp phép đo ổn định, nhưng có thể tạo workload quá nóng:

- Cùng tên field lặp lại.
- Cùng string value lặp lại.
- Cùng subtype.
- Cùng độ dài list.
- Cùng nhánh null/nonnull.

Production có thể có nhiều giá trị khác nhau. Một bộ payload cố định gồm nhiều fixture đại diện thường tốt hơn một chuỗi duy nhất.

Có thể chuẩn bị mảng payload trong setup và luân phiên qua chúng. Nếu dùng cursor, bảo đảm phép chọn payload không trở thành phần chi phí chi phối và dùng cùng chiến lược cho mọi benchmark. Ví dụ mảng có số phần tử là lũy thừa hai để chọn bằng bit mask:

```java
private int cursor;

private byte[] nextPayload() {
    byte[] payload = payloads[cursor & (payloads.length - 1)];
    cursor++;
    return payload;
}
```

Cách này phù hợp khi payloads.length là lũy thừa hai. Nếu không, dùng phép modulo hoặc cách chọn khác và ghi nhận overhead. Không thay đổi phân bố payload giữa các format.

## 26. Tách hot type và dynamic type lookup

Trong ứng dụng thông thường, mapper có thể đọc lặp lại một tập kiểu đã biết. Serializer/deserializer metadata được cache, nên steady-state có thể rất nhanh.

Một workload khác có thể chọn kiểu động theo message type:

```java
JavaType targetType = typeRegistry.resolve(eventType);
Object value = mapper.readValue(bytes, targetType);
```

Nếu type registry lookup hoặc JavaType construction diễn ra mỗi message, chi phí đó nên được đo trong benchmark dynamic-dispatch riêng.

Nên phân biệt:

- **Hot known type**: target class/reader đã biết.
- **Generic known type**: target JavaType được tạo trước.
- **Dynamic type**: mỗi message tra registry hoặc tạo target type.
- **Polymorphic binding**: parser đọc type id rồi chọn subtype.

Đừng đưa type lookup vào benchmark format nếu câu hỏi chỉ là JSON so với CBOR. Ngược lại, nếu production thực sự có dynamic dispatch, đừng bỏ nó khỏi benchmark end-to-end.

## 27. Kiểm tra correctness ngoài vùng đo

Benchmark nhanh nhưng deserialize sai dữ liệu thì không có giá trị. Trước measurement, xác nhận từng mapper tạo và đọc dữ liệu đúng.

Có thể kiểm tra các field quan trọng:

```java
private void verifyEquivalentPayloads() throws Exception {
    OrderEvent fromJson =
        jsonMapper.readValue(jsonBytes, OrderEvent.class);

    OrderEvent fromSmile =
        smileMapper.readValue(smileBytes, OrderEvent.class);

    OrderEvent fromCbor =
        cborMapper.readValue(cborBytes, OrderEvent.class);

    assertEquivalent(event, fromJson);
    assertEquivalent(event, fromSmile);
    assertEquivalent(event, fromCbor);
}
```

Helper nên so sánh đúng semantics:

- BigDecimal bằng compareTo nếu scale không thuộc hợp đồng.
- byte[] bằng Arrays.equals hoặc assertArrayEquals.
- Instant/LocalDateTime theo timezone/precision đã quy định.
- List giữ thứ tự nếu thứ tự có ý nghĩa.
- Map so sánh key/value theo contract.
- Enum so sánh external code hoặc giá trị domain.

Không đặt assertion nặng trong benchmark method vì nó làm thay đổi công việc được đo. Correctness setup và benchmark measurement là hai phần riêng.

## 28. Dùng cùng điều kiện chạy

Khi so sánh hai phiên bản hoặc hai format, giữ các điều kiện sau càng giống nhau càng tốt:

- Cùng JDK vendor và version.
- Cùng JVM options, heap size và GC.
- Cùng CPU, memory và power profile.
- Cùng OS và kiến trúc.
- Cùng số benchmark thread.
- Cùng warmup, measurement và fork.
- Cùng dataset và thứ tự chạy hợp lý.
- Không chạy tác vụ CPU nặng khác cùng lúc.
- Cùng dependency graph ngoài phần đang so sánh.
- Cùng cấu hình mapper về mặt semantics.

Nếu chạy trên CI runner dùng chung, ghi nhận biến động môi trường. Không so sánh số liệu từ laptop nhàn rỗi với CI runner đang chạy nhiều job rồi kết luận phiên bản thư viện chậm hơn.

## 29. Đọc kết quả có ý nghĩa thống kê

Kết quả JMH thường hiển thị score và error margin. Không nên chỉ nhìn số lớn hơn vài phần trăm rồi kết luận có cải thiện.

Cần xem:

- Error margin có chồng lấn không?
- Các fork có ổn định không?
- Kết quả có biến động lớn giữa iteration không?
- Allocation/op có thay đổi không?
- Có thay đổi output size hoặc semantics không?
- Chênh lệch có đủ lớn để ảnh hưởng workload production không?

Nếu chênh lệch nhỏ hơn mức nhiễu của môi trường, kết luận phù hợp là chưa có bằng chứng rõ ràng. Có thể tăng thời gian đo, giảm background load, thêm fork hoặc lặp lại trên máy ổn định hơn.

Đừng làm tròn quá sớm hoặc báo cáo chỉ một số đẹp. Giữ raw JMH result để người khác có thể xem lại.

## 30. Lưu cấu hình và kết quả benchmark

Một báo cáo benchmark cần đủ thông tin để tái lập:

| Nhóm | Thông tin cần lưu |
| --- | --- |
| Code | Commit hash, benchmark source version |
| Runtime | JDK, JVM flags, GC, heap |
| Dependencies | Jackson Core/Databind/module version, JMH version |
| Mapper | Factory, module, feature, naming, custom serializer |
| Data | DTO schema, fixture/profile, số item, payload size |
| Execution | Warmup, measurement, fork, thread, mode |
| Results | Score, error, allocation/op, GC, output bytes |
| Environment | CPU, RAM, OS, load condition |
| Correctness | Test/fixture version và kết quả semantic check |

Có thể lưu output JSON của JMH:

```bash
java -jar target/benchmarks.jar FormatBenchmark -rf json -rff results.json
```

Khi chạy lại, dùng tên file khác hoặc lưu theo commit/version để không ghi đè kết quả cũ. Báo cáo nên ghi cả command thực tế và profile được chạy.

## 31. Những sai lầm thường gặp

| Sai lầm | Vì sao kết quả sai lệch | Cách sửa |
| --- | --- | --- |
| Tạo ObjectMapper trong mỗi operation | Đo startup cùng serialization | Tạo mapper trong setup; benchmark startup riêng |
| Dùng DTO chỉ có hai field | Không đại diện workload thực | Dùng nested DTO và payload profile |
| Dùng cùng một payload cực nhỏ | Không phản ánh distribution | Có small/medium/large và nhiều shape |
| Không đăng ký module production | Serializer path khác | Giữ module/config như production |
| Bỏ custom serializer | Bỏ qua logic thực tế | Dùng cùng custom mapping hoặc đo riêng overhead |
| So sánh String với binary bytes | Đường I/O khác nhau | So sánh cùng loại input/output path |
| Tạo fixture trong timed method | Đo cả fixture generation | Chuẩn bị fixture ở setup |
| Không consume kết quả | Có thể bị tối ưu hoặc không đại diện | Trả kết quả hoặc dùng Blackhole |
| Không warmup/fork | JIT và trạng thái JVM làm nhiễu | Dùng JMH với cấu hình phù hợp |
| Chỉ nhìn throughput | Bỏ qua allocation và GC | Dùng profiler và đo size riêng |
| Đặt assertion trong benchmark | Đo thêm chi phí kiểm tra | Verify correctness ngoài vùng đo |
| Chạy benchmark cùng tải nền | CPU và GC bị tranh chấp | Chạy trong môi trường ổn định |
| Chỉ benchmark một subtype | Bỏ qua polymorphic distribution | Dùng tỷ lệ subtype đại diện |
| Chỉ benchmark round-trip | Không biết read/write riêng tốn bao nhiêu | Tách benchmark read và write |
| Gộp compression với serialization | Không xác định được chi phí từng lớp | Đo từng bước và pipeline riêng |
| So sánh bytes giữa format | Encoding khác nhau là bình thường | So sánh semantic values và size |

## 32. Quy trình benchmark thực tế

Khi chuẩn bị một phép đo Jackson:

1. Viết câu hỏi benchmark và quyết định kỹ thuật cần hỗ trợ.
2. Chụp lại cấu hình mapper, module và phiên bản dependency production.
3. Chọn DTO đại diện cùng các kiểu dữ liệu thực sự xuất hiện.
4. Chuẩn bị fixture đã ẩn danh hoặc dữ liệu tổng hợp giữ phân bố thực tế.
5. Tạo mapper và fixture trong JMH setup, ngoài vùng đo.
6. Xác nhận correctness và semantic equivalence trước measurement.
7. Tách read, write, parse-only, streaming và compression nếu cần.
8. Dùng JMH warmup, measurement và fork.
9. Đo throughput/latency, allocation/GC và output size.
10. Chạy small/medium/large hoặc workload mix có trọng số thực tế.
11. Giữ JDK, JVM, hardware, thread và dependency ổn định.
12. Lưu command, cấu hình, raw result và commit hash.
13. Lặp lại khi chênh lệch nhỏ hoặc kết quả biến động.
14. Xác nhận bằng load/integration test trước khi đưa ra quyết định production.

## 33. Bài thực hành tổng hợp

Tạo một benchmark module nhỏ với JMH và model:

```java
public record PaymentEvent(
    String eventId,
    Instant occurredAt,
    BigDecimal amount,
    CustomerSnapshot customer,
    List<LineItem> items,
    Map<String, String> attributes,
    byte[] attachment
) {}
```

Thực hiện:

1. Tạo JSON mapper với JavaTimeModule và cấu hình giống production.
2. Nếu ứng dụng dùng Smile hoặc CBOR, tạo mapper tương ứng với cùng module và feature.
3. Tạo payload profile SMALL, MEDIUM và LARGE bằng seed cố định.
4. Đảm bảo profile có nested objects, collection, map, decimal, enum, timestamp và binary data phù hợp.
5. Tạo fixture bytes/string trong @Setup(Level.Trial).
6. Tạo benchmark read riêng cho JSON, Smile và CBOR.
7. Tạo benchmark write riêng cho từng format.
8. Tạo benchmark InputStream nếu production đọc từ stream.
9. Tạo benchmark riêng cho startup mapper nếu cần đo cold initialization.
10. Verify dữ liệu sau deserialize bằng helper ngoài vùng đo.
11. Chạy JMH với nhiều warmup, measurement và fork.
12. Chạy GC profiler để đo allocation/op.
13. Ghi output size của từng format.
14. Chạy thêm một workload có custom serializer nếu production dùng.
15. Chạy thêm polymorphic subtype distribution nếu production có type id.
16. Lưu JMH JSON result, dependency version, JDK và commit hash.
17. So sánh kết quả qua nhiều lần chạy và nêu error margin.
18. Xác nhận kết luận bằng integration/load test khi thay đổi có ảnh hưởng hệ thống.

Bài thực hành hoàn thành khi người khác có thể chạy lại benchmark với cùng cấu hình và fixture, hiểu rõ mỗi con số đo phần nào của pipeline, và xác nhận dữ liệu của các mapper vẫn giữ đúng semantics.

## 34. Nguyên tắc ghi nhớ

- Benchmark phải trả lời một câu hỏi cụ thể và thay đổi từng yếu tố có chủ đích.
- Giữ cấu hình mapper, module, feature và serializer giống production.
- Giữ DTO và phân bố dữ liệu đại diện: nested object, collection, map, decimal, date/time, enum, null và binary.
- Tạo ObjectMapper một lần trong setup cho steady-state benchmark; đo startup riêng.
- Chuẩn bị fixture ngoài timed method.
- Dùng đúng target Java type, generic type và đường String/bytes/stream của production.
- Dùng JMH để có warmup, measurement và fork; tránh vòng lặp nanoTime tự viết làm cơ sở kết luận.
- Tách read, write, parse, bind, stream và compression để biết chi phí thuộc lớp nào.
- Dùng return value hoặc Blackhole để kết quả thực sự được tiêu thụ.
- Kiểm tra correctness ngoài vùng đo; không đặt assertion nặng trong benchmark method.
- Đo allocation/GC và output size bên cạnh throughput/latency.
- Dùng nhiều profile và subtype distribution, không chỉ một payload lặp lại.
- Giữ JDK, JVM, hardware và dependency ổn định khi so sánh.
- Lưu raw results, cấu hình, fixture version và commit hash.
- Chỉ kết luận khi chênh lệch lớn hơn nhiễu đo và workload đại diện; xác nhận bằng integration/load test khi cần.

Một con số benchmark chỉ hữu ích khi biết chính xác nó được tạo ra từ mapper nào, kiểu dữ liệu nào và đường xử lý nào. Hãy giữ cấu hình cùng workload đại diện, tách từng phần cần đo và lưu đủ thông tin để tái lập; như vậy kết quả mới có thể hỗ trợ quyết định hiệu năng thay vì chỉ tạo ra một bảng số liệu khó áp dụng vào production.
