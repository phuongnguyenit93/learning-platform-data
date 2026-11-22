# Kiểm soát bộ đệm và số lượng đối tượng sống đồng thời

## 1. Vì sao bộ đệm và object lifetime ảnh hưởng hiệu năng?

Khi Jackson đọc hoặc ghi JSON, Smile, CBOR hay một định dạng khác, nó phải quản lý nhiều loại dữ liệu tạm:

- Buffer byte hoặc ký tự để đọc từ nguồn và ghi ra đích.
- Buffer tích lũy nội dung string, tên field hoặc token.
- Object Java được tạo từ payload.
- Object trung gian trong quá trình chuyển đổi, validation hoặc mapping.
- Buffer của ứng dụng, chẳng hạn byte array, ByteArrayOutputStream và queue.

Hiệu năng không chỉ phụ thuộc vào tốc độ parser. Một pipeline có thể parse nhanh nhưng vẫn tốn nhiều heap vì giữ cả payload byte[], JsonNode tree và object graph cùng lúc. Ngược lại, một pipeline có thể giảm allocation bằng cách tái sử dụng mapper, dùng streaming và giới hạn số record đang xử lý đồng thời.

Hai khái niệm cần phân biệt:

- **Buffer recycling:** tái sử dụng các vùng nhớ tạm mà parser/generator dùng để đọc và ghi dữ liệu.
- **Object lifetime:** khoảng thời gian một object Java còn được tham chiếu và chưa thể được garbage collector thu hồi.

Jackson có cơ chế tái sử dụng một số buffer nội bộ. Cơ chế đó không tự giải quyết việc ứng dụng giữ quá nhiều object nghiệp vụ, queue không giới hạn hoặc byte array lớn. Muốn kiểm soát memory, cần thiết kế cả mapper, parser/generator, luồng xử lý và concurrency.

## 2. Những loại buffer Jackson thường sử dụng

Trong quá trình đọc và ghi, Jackson Core có thể dùng các buffer cho:

| Nhóm buffer | Vai trò |
|---|---|
| Input byte buffer | Đọc byte theo từng khối từ InputStream |
| Output byte buffer | Gom byte trước khi ghi ra OutputStream |
| Input character buffer | Hỗ trợ parser đọc từ Reader |
| Output character buffer | Hỗ trợ generator ghi ra Writer |
| Token/text buffer | Tích lũy nội dung string hoặc token có độ dài lớn |
| Name-copy buffer | Hỗ trợ lưu hoặc xử lý tên property |

Tên lớp và cách tổ chức buffer nội bộ có thể thay đổi theo phiên bản Jackson Core. Điểm quan trọng ở góc nhìn ứng dụng là parser/generator thường không cần tạo một buffer mới cho từng byte hoặc từng ký tự; một số buffer có thể được tái sử dụng thông qua cơ chế recycler của factory.

Buffer nội bộ giúp giảm số lần cấp phát và giảm áp lực garbage collection. Tuy nhiên, buffer vẫn chiếm bộ nhớ trong thời gian hoạt động hoặc khi được giữ lại để tái sử dụng.

## 3. Buffer recycling và vòng đời parser/generator

Jackson Core quản lý các vùng nhớ tạm thông qua context và cơ chế buffer recycler. Khi parser hoặc generator kết thúc, các buffer được quản lý có thể được trả về cơ chế tái sử dụng thay vì để ứng dụng tự quản lý từng mảng byte/ký tự.

Vì vậy, parser và generator cần được đóng đúng cách:

~~~java
try (JsonParser parser = factory.createParser(inputStream)) {
    // Đọc token và xử lý dữ liệu.
}

try (JsonGenerator generator = factory.createGenerator(outputStream)) {
    // Ghi token và dữ liệu.
}
~~~

Đóng parser/generator giúp giải phóng tài nguyên gắn với phiên làm việc và cho phép Jackson thực hiện quy trình release buffer. Tùy cấu hình, thao tác close cũng có thể đóng InputStream hoặc OutputStream bên dưới.

Không nên giữ parser hoặc generator trong field dùng chung, cache hoặc collection sau khi đã xử lý xong. Chúng đại diện cho một phiên đọc/ghi cụ thể, có trạng thái token, vị trí và buffer riêng.

Đóng parser không có nghĩa mọi byte của buffer lập tức biến mất khỏi heap. Buffer có thể được trả về pool để tái sử dụng; vòng đời tiếp theo phụ thuộc cơ chế recycler, phiên bản Jackson, cấu hình factory và garbage collector.

## 4. Tái sử dụng ObjectMapper và JsonFactory

ObjectMapper có cache serializer/deserializer và các cấu trúc cấu hình. Tạo mapper mới cho từng request làm mất lợi ích cache và có thể tạo thêm allocation không cần thiết.

Nên tạo mapper một lần sau khi hoàn tất cấu hình:

~~~java
public final class JsonSupport {
    public static final ObjectMapper MAPPER =
            JsonMapper.builder().build();

    private JsonSupport() {
    }
}
~~~

Hoặc quản lý mapper bằng dependency injection:

~~~java
@Configuration
public class JacksonConfiguration {
    @Bean
    ObjectMapper objectMapper() {
        return JsonMapper.builder()
                .build();
    }
}
~~~

ObjectMapper có thể được chia sẻ giữa nhiều thread nếu cấu hình đã hoàn tất trước khi bắt đầu sử dụng đồng thời. Không nên thay đổi feature, module hoặc mix-in trên mapper đang phục vụ request.

ObjectReader và ObjectWriter là các đối tượng cấu hình bất biến, có thể được tạo trước và tái sử dụng:

~~~java
private final ObjectReader eventReader =
        mapper.readerFor(Event.class);

private final ObjectWriter eventWriter =
        mapper.writerFor(Event.class);
~~~

JsonFactory cũng được thiết kế để tái sử dụng khi tạo parser/generator cho nhiều luồng. Parser và generator được tạo ra từ factory có trạng thái riêng và không nên dùng đồng thời từ nhiều thread.

## 5. Không nhầm buffer nội bộ với object pool của ứng dụng

Jackson tái sử dụng buffer nội bộ không có nghĩa ứng dụng nên tự pool mọi POJO.

Object pool cho domain object có thể tạo thêm vấn đề:

- Object được giữ sống lâu hơn cần thiết.
- Trạng thái cũ có thể bị sót nếu không reset mọi field.
- Nhiều thread tranh chấp pool.
- Việc reset object phức tạp hơn cấp phát object mới.
- Pool có thể giữ các object lớn sau một đợt tải đột biến.

JVM garbage collector được tối ưu cho nhiều object ngắn hạn. Với phần lớn DTO và object graph được Jackson tạo ra, hãy bắt đầu bằng cấp phát thông thường và để GC thu hồi khi không còn tham chiếu.

Chỉ xem xét object pooling khi profiling chứng minh allocation của một loại object cụ thể là bottleneck và lợi ích lớn hơn chi phí đồng bộ, reset và giữ bộ nhớ.

## 6. Số lượng object sống đồng thời mới là giới hạn quan trọng

Một object chỉ có thể được GC thu hồi khi không còn đường tham chiếu có thể truy cập từ GC roots. Nếu ứng dụng đưa mọi record vào một List rồi giữ List đến cuối batch, tất cả object trong danh sách vẫn sống dù đã xử lý xong.

Ví dụ tích lũy toàn bộ dữ liệu:

~~~java
List<Event> events = mapper.readValue(
        inputStream,
        new TypeReference<List<Event>>() {}
);

for (Event event : events) {
    process(event);
}
~~~

Đoạn mã này tạo cả danh sách và object graph cho toàn bộ payload. Với file lớn, heap cần đủ chỗ cho tất cả record cùng lúc.

Nếu xử lý từng record rồi bỏ tham chiếu:

~~~java
while (parser.nextToken() != JsonToken.END_ARRAY) {
    Event event = mapper.readValue(parser, Event.class);
    process(event);
    // Sau khi vòng lặp sang record kế tiếp và không còn tham chiếu,
    // event có thể trở thành đối tượng đủ điều kiện để GC thu hồi.
}
~~~

Ứng dụng không còn cần giữ mọi record trong một danh sách. GC vẫn quyết định thời điểm thu hồi; việc bỏ tham chiếu chỉ làm object đủ điều kiện được thu hồi.

Streaming không có nghĩa bộ nhớ bằng 0 hoặc parser không tạo object. Nó có nghĩa ứng dụng giới hạn lượng dữ liệu được giữ cùng lúc thay vì materialize toàn bộ tài liệu.

## 7. Streaming một JSON array bằng JsonParser

Đây là cách đọc một array lớn theo từng phần tử:

~~~java
JsonFactory factory = mapper.getFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected a JSON array");
    }

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_ARRAY) {
        if (token == null) {
            throw new IOException("Unexpected end of JSON input");
        }

        Event event = mapper.readValue(parser, Event.class);
        process(event);
    }
}
~~~

Khi parser đang ở START_OBJECT hoặc token bắt đầu một value, mapper đọc trọn value thành một Event. Sau đó vòng lặp chuyển đến token kế tiếp. Mỗi lần chỉ cần giữ object graph của record hiện tại cùng các tài nguyên của bước xử lý.

Nếu process(event) đưa event vào queue bất đồng bộ, object vẫn sống cho đến khi consumer xử lý xong. Vì vậy, streaming parser cần đi kèm queue có giới hạn và backpressure; nếu producer đọc nhanh hơn consumer không giới hạn, heap vẫn tăng.

Đối với một JSON array có cú pháp sai ở giữa, parser có thể không thể tiếp tục an toàn. Streaming giúp giảm memory nhưng không tự tạo khả năng phục hồi sau mọi lỗi cú pháp.

## 8. Streaming khi ghi JSON array

Không cần tạo một List chứa mọi object trước khi serialize. Có thể ghi từng object qua JsonGenerator:

~~~java
try (JsonGenerator generator =
        mapper.getFactory().createGenerator(outputStream)) {

    generator.writeStartArray();

    for (Event event : eventSource) {
        mapper.writeValue(generator, event);
    }

    generator.writeEndArray();
}
~~~

Output được phát dần theo từng record. Bộ nhớ cần thiết phụ thuộc object hiện tại, buffer ghi và phần dữ liệu mà nguồn/đích giữ lại.

Nếu eventSource là một collection khổng lồ đã được nạp vào heap từ trước, phần ghi streaming không xóa được memory của collection đó. Lợi ích đầy đủ xuất hiện khi nguồn dữ liệu cũng được đọc theo luồng hoặc theo page.

Nếu output cần tính toàn vẹn, hãy ghi vào file tạm hoặc một transaction/staging destination rồi chỉ công bố sau khi generator đóng thành công. Streaming không tự làm output đã ghi một phần trở thành một JSON document hợp lệ.

## 9. Tree Model và POJO có thể làm tăng memory peak

Tree Model hữu ích khi cần duyệt, sửa hoặc kiểm tra cấu trúc JSON động. Nhưng JsonNode tạo một object đại diện cho từng node và có thể giữ toàn bộ cây trong heap.

Ví dụ:

~~~java
JsonNode root = mapper.readTree(inputStream);
Event event = mapper.treeToValue(root, Event.class);
process(event);
~~~

Trong khoảng thời gian chuyển đổi, cả JsonNode tree và Event object graph đều có thể cùng tồn tại. Nếu root vẫn được giữ tham chiếu sau khi chuyển đổi, cả hai tiếp tục chiếm bộ nhớ.

Với payload có schema ổn định, đọc trực tiếp vào POJO thường tránh được cây trung gian:

~~~java
Event event = mapper.readValue(inputStream, Event.class);
~~~

Với payload rất lớn gồm nhiều record, hãy đọc từng record bằng Streaming API thay vì tạo một JsonNode cho toàn bộ tài liệu.

Tree Model vẫn phù hợp khi cần xử lý schema linh hoạt, sửa field chưa biết hoặc làm gateway. Khi dùng nó, cần giới hạn kích thước tài liệu và thời gian giữ root node.

## 10. Tránh tạo byte[] và String trung gian không cần thiết

Các API tiện lợi như writeValueAsBytes() và writeValueAsString() tạo một kết quả hoàn chỉnh trong bộ nhớ. Với payload lớn, điều này có thể làm tăng memory peak.

Ví dụ:

~~~java
byte[] bytes = mapper.writeValueAsBytes(largeObject);
outputStream.write(bytes);
~~~

Trong thời gian ghi, byte[] chứa toàn bộ payload vẫn phải sống. Nếu dùng ByteArrayOutputStream rồi gọi toByteArray(), thao tác sao chép còn có thể tạo thêm một mảng byte khác.

Nếu đích là stream, có thể ghi trực tiếp:

~~~java
mapper.writeValue(outputStream, largeObject);
~~~

Tương tự, tránh:

~~~java
String json = mapper.writeValueAsString(largeObject);
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
send(bytes);
~~~

Cách này giữ String và byte[] cùng tồn tại trong quá trình chuyển đổi. Nếu transport nhận OutputStream, hãy serialize trực tiếp vào stream. Nếu API bắt buộc byte[], hãy tính dung lượng payload tối đa và giới hạn kích thước đầu vào.

Ở chiều đọc, tránh đọc toàn bộ file thành byte[] hoặc String trước khi gọi mapper nếu nguồn có thể được truyền dưới dạng InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    Event event = mapper.readValue(input, Event.class);
}
~~~

Đọc trực tiếp từ InputStream giúp tránh một bản sao toàn bộ payload do ứng dụng tạo ra. Object graph đích vẫn được materialize nếu dùng readValue cho một object lớn.

## 11. Bộ đệm lớn và dữ liệu string/binary lớn

Một field string rất lớn có thể cần buffer tích lũy trước khi trở thành Java String. Một field byte[] lớn cũng cần một vùng nhớ tương ứng với toàn bộ dữ liệu sau khi deserialize.

Ví dụ:

~~~java
public class Attachment {
    private String description;
    private byte[] content;
}
~~~

Nếu content chứa file lớn được Base64 trong JSON, parser và Databind phải xử lý chuỗi encoded rồi tạo byte[] đích. Memory peak có thể bao gồm:

- Buffer đọc.
- Buffer tích lũy token/string.
- Nội dung Base64 dạng String hoặc buffer trung gian tùy đường binding.
- byte[] sau decode.
- Các bản sao do ứng dụng tạo trong bước tiếp theo.

Nếu file lớn, cân nhắc lưu file ở object storage và chỉ truyền metadata/URI trong JSON. Nếu giao thức yêu cầu Base64, xem xét API streaming decode ra OutputStream thay vì materialize toàn bộ byte[] khi phù hợp với parser và format đang dùng.

Đừng giữ nội dung attachment trong log, cache hoặc DTO lâu hơn cần thiết. Hãy đặt giới hạn kích thước cho cả field và toàn request.

## 12. Buffer recycling không thay thế giới hạn parser

Buffer recycler giảm allocation lặp lại nhưng không bảo vệ ứng dụng khỏi một payload quá lớn hoặc độc hại. Một chuỗi khổng lồ vẫn có thể buộc parser cấp phát vùng nhớ lớn; một array có hàng triệu phần tử vẫn tạo ra nhiều object.

Jackson Core cung cấp StreamReadConstraints trong các phiên bản hỗ trợ để giới hạn một số đặc điểm của input:

~~~java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNestingDepth(100)
                        .maxStringLength(1_000_000)
                        .maxNumberLength(1_000)
                        .build()
        )
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các giới hạn trên chỉ là ví dụ. Chọn giá trị theo schema và workload thực tế. API và default có thể thay đổi theo phiên bản Jackson Core; hãy xác nhận với phiên bản dependency mà dự án đang dùng.

Ngoài parser constraints, nên giới hạn:

- Tổng kích thước HTTP request hoặc message.
- Số record trong một batch.
- Kích thước tối đa của một record.
- Số phần tử trong collection theo nghiệp vụ.
- Độ sâu object graph mà ứng dụng chấp nhận.
- Thời gian parse và xử lý.

## 13. Số parser/generator đồng thời ảnh hưởng bộ nhớ

Mỗi parser/generator đang hoạt động có thể giữ context và buffer riêng. Nếu ứng dụng xử lý 100 message song song, memory cần thiết không giống trường hợp chỉ có một parser.

Một mô hình ước lượng:

~~~text
Peak heap
  ≈ số tác vụ đang chạy
      × (parser/generator buffers
         + object graph đang xử lý
         + transformation objects
         + output buffers)
    + queue backlog
    + shared caches
    + application state
~~~

Đây là mô hình tư duy, không phải công thức đo chính xác. Kích thước thực tế thay đổi theo payload, buffer capacity, object layout, JVM và recycler.

Nếu tăng thread pool từ 8 lên 64 mà mỗi tác vụ giữ một record lớn, heap có thể tăng mạnh dù code không thay đổi. Concurrency là một phần của ngân sách memory.

Hãy xác định giới hạn số tác vụ in-flight dựa trên memory budget, latency và tốc độ downstream. Không tăng concurrency chỉ để đạt số thread lớn hơn.

## 14. Dùng bounded queue và backpressure

Một pipeline bất đồng bộ thường có producer đọc JSON và consumer xử lý record:

~~~text
JSON source
    |
    v
Parser / producer
    |
    v
Bounded queue
    |
    v
Worker pool
    |
    v
Output
~~~

Nếu queue không giới hạn, producer có thể đọc nhanh hơn consumer và giữ hàng nghìn object trong heap.

Ví dụ:

~~~java
BlockingQueue<Event> queue = new ArrayBlockingQueue<>(500);
~~~

Khi queue đầy, producer phải chờ hoặc áp dụng chính sách backpressure. Queue có giới hạn làm cho tốc độ đọc tự điều chỉnh theo tốc độ xử lý.

Kích thước queue phải dựa trên memory của mỗi record, không chỉ số lượng. 500 record nhỏ có thể nhẹ; 500 record chứa nhiều byte[] lớn có thể vượt heap budget.

Nếu record có kích thước rất khác nhau, cân nhắc giới hạn theo tổng byte in-flight hoặc semaphore theo trọng lượng ước lượng, thay vì chỉ giới hạn số phần tử.

## 15. Xử lý theo batch mà không giữ toàn bộ dữ liệu

Một số thao tác database hoặc network hiệu quả hơn khi gom nhiều record thành batch. Có thể dùng batch nhỏ và giải phóng tham chiếu sau mỗi lần gửi:

~~~java
int batchSize = 200;
List<Event> batch = new ArrayList<>(batchSize);

while (hasNextRecord(parser)) {
    Event event = readNextEvent(parser);
    batch.add(event);

    if (batch.size() == batchSize) {
        persist(batch);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    persist(batch);
    batch.clear();
}
~~~

clear() loại bỏ các tham chiếu từ danh sách để các Event có thể trở thành đối tượng đủ điều kiện GC nếu không còn nơi nào khác giữ chúng. Nó không ép GC chạy ngay.

Batch size là một tradeoff:

- Batch quá nhỏ tăng overhead gọi database hoặc network.
- Batch quá lớn tăng memory peak và latency chờ đủ batch.
- Batch cần phù hợp với giới hạn transaction, retry và khả năng phục hồi.

Nếu persist() giữ lại danh sách hoặc copy record vào cache, clear() không làm object được thu hồi. Hãy kiểm tra các tham chiếu downstream.

## 16. Tránh giữ object ngoài ý muốn

Một object đã xử lý xong vẫn sống nếu còn được tham chiếu bởi:

- Static collection hoặc singleton cache.
- ThreadLocal.
- Queue hoặc executor task chưa chạy.
- Future/CompletableFuture chưa hoàn tất.
- Listener hoặc callback giữ closure.
- Log buffer hoặc tracing span giữ payload.
- Collection batch chưa clear.
- Exception hoặc diagnostic context giữ object lớn.

Ví dụ rủi ro:

~~~java
static final List<Event> DEBUG_EVENTS = new ArrayList<>();

void process(Event event) {
    DEBUG_EVENTS.add(event);
    handle(event);
}
~~~

Danh sách static giữ mọi Event được thêm vào. Dù parser đã đóng và vòng lặp kết thúc, các object vẫn sống.

Không nên lưu toàn bộ DTO vào log/debug history. Hãy lưu metadata nhỏ như ID, trạng thái, timestamp và error code. Nếu cần lưu payload để điều tra, dùng kho riêng có giới hạn và retention.

## 17. ThreadLocal và bộ đệm tái sử dụng

Một số cơ chế buffer recycling của Jackson Core qua các phiên bản có thể sử dụng ThreadLocal hoặc recycler pool để giữ buffer giữa các lần tạo parser/generator. Cấu hình và default cụ thể phụ thuộc phiên bản.

Điều này giảm chi phí cấp phát khi cùng thread liên tục xử lý message. Tuy nhiên, thread pool của ứng dụng thường giữ worker thread sống lâu; dữ liệu trong ThreadLocal cũng có thể tồn tại lâu theo vòng đời thread hoặc recycler.

Các điểm cần cân nhắc:

- Không tự thêm ThreadLocal byte[] hoặc char[] lớn nếu không có lý do đo được.
- Không giữ parser/generator trong ThreadLocal.
- Khi dùng executor dài hạn, theo dõi heap sau các đợt xử lý payload lớn.
- Nếu ứng dụng chạy trong container hoặc nhiều classloader, kiểm tra vòng đời thread và classloader khi redeploy.
- Đọc tài liệu đúng phiên bản Jackson Core trước khi thay đổi recycler pool hoặc buffer recycling feature.

Không nên tắt buffer recycling chỉ vì thấy buffer còn trong heap dump. Buffer có thể được giữ có chủ đích để tái sử dụng. Hãy phân biệt retained memory có giới hạn với memory tăng liên tục do leak.

## 18. Giới hạn số tác vụ đồng thời

Có thể dùng fixed thread pool để đặt giới hạn worker:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);
~~~

Nhưng fixed thread pool một mình chưa đủ nếu task queue nội bộ không giới hạn. Với lượng message lớn, queue của executor có thể giữ rất nhiều task và object.

Có thể dùng ThreadPoolExecutor với queue có giới hạn:

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        8,
        8,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

CallerRunsPolicy làm thread gửi task thực hiện task khi queue đầy, tạo backpressure đơn giản. Trong hệ thống thực tế, cần chọn rejection policy phù hợp với nguồn dữ liệu, timeout và yêu cầu không mất message.

Nếu parser đọc record rồi submit task, producer phải quản lý trường hợp submit bị từ chối và không bỏ mất record. Có thể chờ slot, ghi backlog hoặc dừng intake tùy hợp đồng.

## 19. Dùng JFR và profiler để tìm memory bottleneck

Không nên kết luận memory leak chỉ từ việc heap chưa giảm ngay sau một batch. GC có thể chưa chạy hoặc buffer recycler đang giữ vùng nhớ để tái sử dụng.

Các công cụ hữu ích:

- Java Flight Recorder (JFR): quan sát allocation, GC, thread, lock và event theo thời gian.
- Java Mission Control: phân tích recording JFR.
- Heap dump: xem object nào đang giữ tham chiếu đến memory lớn.
- Eclipse MAT: tìm dominator tree, retained size và đường tham chiếu.
- async-profiler: đo allocation và CPU profile.
- JMH: benchmark allocation/op và hiệu năng ở mức operation.

Khi điều tra:

1. Ghi baseline heap sau warmup.
2. Chạy workload đại diện với concurrency cố định.
3. Ghi heap sau khi pipeline đã drain queue.
4. So sánh allocation rate và retained heap.
5. Kiểm tra object nào giữ byte[], JsonNode, DTO hoặc buffer lớn.
6. Lặp lại nhiều batch để xem memory có tăng không giới hạn hay ổn định ở một mức.

Một buffer được recycler giữ lại có thể là retained memory có chủ đích. Một List static tăng mãi theo số message thường là leak logic. Heap dump và đường tham chiếu giúp phân biệt hai trường hợp.

## 20. Benchmark buffer và object lifetime

Một benchmark nên thay đổi từng yếu tố:

| Thử nghiệm | Cấu hình | Điều cần quan sát |
|---|---|---|
| Mapper lifecycle | Một mapper dùng chung so với mapper mới mỗi lần | Allocation, throughput, cache |
| Input mode | byte[]/String so với InputStream | Bản sao payload và memory peak |
| Materialization | readValue toàn List so với parser từng record | Retained heap |
| Tree vs POJO | readTree rồi treeToValue so với readValue trực tiếp | Object trung gian và peak heap |
| Concurrency | 1, 4, 8, 16, 32 tác vụ | Buffer và object in-flight |
| Queue | Không giới hạn so với bounded queue | Backlog và memory ổn định |
| Payload size | Nhỏ, trung bình, rất lớn | Buffer growth và constraints |
| Buffer recycling | Default so với cấu hình được tài liệu hóa | Allocation và retained memory |

Không thay đổi nhiều yếu tố cùng lúc. Nếu vừa đổi định dạng, mapper, thread pool và batch size, rất khó biết thay đổi nào tạo ra kết quả.

Với benchmark micro, dùng JMH và đo allocation. Với memory peak và queue backlog, chạy load test dài hơn trong môi trường gần production.

## 21. Đọc và ghi stream với tài nguyên được quản lý

Ví dụ đọc một file lớn theo record:

~~~java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        Event event = mapper.readValue(parser, Event.class);
        process(event);
    }
}
~~~

Ví dụ ghi kết quả ra stream:

~~~java
try (OutputStream output = Files.newOutputStream(target);
     JsonGenerator generator =
             mapper.getFactory().createGenerator(output)) {

    generator.writeStartArray();
    for (Event event : eventSource) {
        mapper.writeValue(generator, event);
    }
    generator.writeEndArray();
}
~~~

Try-with-resources giúp đóng tài nguyên kể cả khi xử lý ném exception. Nếu stream do caller quản lý và không được phép đóng tại đây, cần cấu hình ownership/auto-close hoặc dùng wrapper phù hợp. Hãy quy định rõ ai chịu trách nhiệm đóng InputStream và OutputStream.

Không nên nuốt exception trong finally hoặc bỏ qua lỗi close nếu việc flush/close là điều kiện để output hoàn chỉnh.

## 22. Cân nhắc khi dùng ObjectReader và MappingIterator

ObjectReader có thể đọc nhiều value qua MappingIterator:

~~~java
try (MappingIterator<Event> iterator =
        mapper.readerFor(Event.class).readValues(inputStream)) {

    while (iterator.hasNextValue()) {
        Event event = iterator.nextValue();
        process(event);
    }
}
~~~

MappingIterator giúp đọc tuần tự và đóng parser/tài nguyên theo vòng đời của iterator. Hãy đóng iterator bằng try-with-resources khi nó quản lý parser hoặc stream.

Không gọi readAll() nếu mục tiêu là giới hạn memory; phương thức đó thu thập các value vào một collection. Hãy xử lý từng value và chỉ giữ batch có giới hạn nếu downstream cần gom nhóm.

Với JSON array, hãy kiểm tra cách reader được cấu hình và vị trí parser theo đúng API/phiên bản Jackson đang dùng. Khi cần kiểm soát token boundary rõ ràng nhất, vòng lặp JsonParser trực tiếp là cách dễ quan sát.

## 23. Đặt ngân sách memory cho pipeline

Trước khi chọn concurrency, hãy ước lượng:

- Heap tối đa được cấp cho service.
- Số request hoặc record in-flight.
- Kích thước object graph trung bình và p99.
- Buffer parser/generator mỗi tác vụ.
- Kích thước queue và batch.
- Memory của cache, session và trạng thái nghiệp vụ.
- Overhead của thread stack, direct buffer và native memory.

Ví dụ, nếu một record sau deserialize chiếm khoảng 200 KB và pipeline cho phép 100 record cùng sống, riêng object graph đã có thể chiếm khoảng 20 MB, chưa tính buffer, transformation và queue overhead. Đây chỉ là phép ước lượng; cần đo bằng profiler vì kích thước object thực tế phụ thuộc JVM layout và dữ liệu.

Đừng dùng toàn bộ heap cho object graph. Cần headroom cho GC, burst traffic, payload lớn và các thành phần khác của ứng dụng.

## 24. Những lỗi thường gặp

### Tạo ObjectMapper trong mỗi request

Làm mất lợi ích cache và tạo thêm object cấu hình. Tạo mapper một lần sau khi cấu hình xong.

### Không đóng parser/generator

Buffer và resource có thể không được release đúng vòng đời. Dùng try-with-resources.

### Đọc toàn bộ file vào byte[] rồi mới parse

Tạo thêm một bản sao lớn trong heap. Dùng InputStream và Streaming API khi payload lớn.

### Dùng readTree cho tài liệu rất lớn

Toàn bộ tree được giữ trong heap. Dùng streaming hoặc đọc từng record nếu schema cho phép.

### Tạo String rồi chuyển sang byte[]

String và byte[] có thể cùng sống trong lúc chuyển đổi. Ghi trực tiếp vào OutputStream khi có thể.

### Queue hoặc executor không giới hạn

Producer có thể tạo object nhanh hơn consumer và giữ backlog không giới hạn. Dùng bounded queue và backpressure.

### Pool POJO quá sớm

Pool có thể làm tăng retained memory và tạo lỗi trạng thái cũ. Hãy profile trước.

### Nghĩ rằng close sẽ giải phóng ngay mọi buffer

Buffer có thể được trả về recycler để tái sử dụng. Quan sát retained heap và lifecycle trước khi kết luận leak.

### Tăng concurrency mà không tính memory

Mỗi tác vụ có parser/context và object graph riêng. Đặt giới hạn theo memory budget và payload size.

## 25. Quy trình tối ưu thực tế

Khi pipeline Jackson tiêu thụ memory hoặc GC quá cao:

1. Đo heap, allocation rate, GC pause và số object in-flight.
2. Xác nhận mapper/factory có được tái sử dụng không.
3. Kiểm tra parser/generator có được đóng đúng cách không.
4. Xác định có materialize toàn bộ payload bằng List hoặc JsonNode không.
5. Loại bỏ byte[]/String trung gian nếu có thể ghi/đọc trực tiếp từ stream.
6. Đặt giới hạn record size, string length, nesting và số phần tử.
7. Giới hạn queue, batch và concurrency.
8. Tìm các collection, cache, ThreadLocal hoặc task đang giữ object sau xử lý.
9. Dùng JFR/heap dump để phân biệt allocation cao với retained-memory leak.
10. Chỉ điều chỉnh recycler/buffer setting sau khi đo và đọc tài liệu đúng phiên bản Jackson Core.

Sau mỗi thay đổi, chạy lại cùng workload và so sánh memory peak, allocation, throughput, latency và GC. Không tối ưu chỉ dựa trên một con số heap sau khi chạy xong.

## 26. Kết luận

Jackson dùng buffer nội bộ và cơ chế recycler để giảm allocation lặp lại, nhưng ứng dụng vẫn phải đóng parser/generator, tái sử dụng ObjectMapper/JsonFactory và giới hạn số object còn sống. Đọc toàn bộ payload thành List hoặc JsonNode, chuyển qua byte[]/String trung gian, queue không giới hạn và concurrency quá cao đều có thể làm memory peak tăng mạnh. Streaming theo record, bounded queue, batch nhỏ, direct InputStream/OutputStream và việc giải phóng tham chiếu giúp giữ số object in-flight trong giới hạn. Buffer được tái sử dụng có thể vẫn nằm trong heap sau close; hãy dùng JFR và heap dump để phân biệt buffer retention có chủ đích với leak thật. Chỉ thay đổi recycler hoặc buffer configuration sau khi benchmark trên đúng phiên bản Jackson và workload production.
