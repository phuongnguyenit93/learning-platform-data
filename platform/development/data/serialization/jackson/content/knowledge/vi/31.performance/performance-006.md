# Đọc hoặc ghi từng phần cho tập dữ liệu lớn

Khi một ứng dụng phải đọc hoặc ghi hàng trăm nghìn hay hàng triệu object JSON, cách gọi readValue() cho toàn bộ danh sách hoặc writeValueAsString() cho toàn bộ kết quả có thể tiêu tốn nhiều bộ nhớ. Jackson hỗ trợ xử lý theo luồng để parser và generator làm việc tuần tự với dữ liệu. Ứng dụng có thể lấy một object, kiểm tra, xử lý rồi chuyển sang object tiếp theo; khi ghi, nó có thể phát từng object ra output stream mà không cần tạo một chuỗi JSON khổng lồ.

Cần phân biệt hai khái niệm thường được gọi chung là “chia nhỏ dữ liệu”:

- **Streaming ở tầng định dạng:** Jackson đọc token hoặc object từ một nguồn liên tục, và ghi token/object ra một luồng liên tục.
- **Batching ở tầng ứng dụng:** ứng dụng gom một số object đã đọc thành một batch nhỏ để validate, lưu database hoặc gọi dịch vụ downstream.

Hai kỹ thuật có thể kết hợp. Streaming kiểm soát cách dữ liệu đi qua parser/generator; batching kiểm soát kích thước công việc và transaction của ứng dụng.

Bài học này tập trung vào Jackson Databind và Jackson Core: đọc mảng JSON lớn bằng MappingIterator hoặc JsonParser, xử lý từng phần, ghi mảng lớn bằng SequenceWriter, dùng NDJSON khi cần ranh giới record rõ ràng, quản lý lỗi và tài nguyên, đồng thời giữ bộ nhớ ở mức có thể dự đoán.

## 1. Vì sao không nên materialize toàn bộ tập dữ liệu?

Giả sử API trả về một mảng JSON có hàng triệu đơn hàng:

~~~json
[
  {"id":"ORD-1","amount":100.00},
  {"id":"ORD-2","amount":250.00},
  {"id":"ORD-3","amount":75.00}
]
~~~

Cách đọc thông thường:

~~~java
List<Order> orders = mapper.readValue(
    input,
    new TypeReference<List<Order>>() {}
);

for (Order order : orders) {
    process(order);
}
~~~

Cách này tiện cho tập dữ liệu nhỏ. Nhưng với file rất lớn, toàn bộ List<Order> và các object con được giữ trong heap cho đến khi xử lý xong. Bộ nhớ tăng theo số lượng object và kích thước dữ liệu.

Tương tự, khi ghi:

~~~java
String json = mapper.writeValueAsString(orders);
output.write(json);
~~~

Ứng dụng có thể đồng thời giữ danh sách object và một chuỗi JSON lớn. Với dữ liệu lớn, còn có thể phát sinh bản sao bộ nhớ trong quá trình mã hóa hoặc chuyển đổi sang byte.

Những hạn chế chính:

- Heap tăng theo tổng số record.
- Có thể gặp OutOfMemoryError khi dữ liệu vượt khả năng bộ nhớ.
- Thời gian chờ trước khi xử lý record đầu tiên dài.
- Khó kiểm soát áp lực lên database hoặc dịch vụ downstream.
- Một lỗi muộn có thể khiến toàn bộ thao tác thất bại sau khi đã tốn nhiều công sức.
- Việc tạo một chuỗi trung gian lớn làm tăng allocation và garbage collection.

Streaming cho phép bộ nhớ chủ yếu phụ thuộc vào parser/generator buffer, object đang xử lý và batch hiện tại thay vì toàn bộ tập dữ liệu.

## 2. Streaming khác với việc cắt chuỗi JSON thành nhiều đoạn

Không thể tùy tiện chia một JSON document thành các chuỗi byte hoặc chuỗi ký tự rồi gọi readValue() riêng cho từng đoạn.

Ví dụ, JSON object sau:

~~~json
{
  "id": "ORD-1001",
  "description": "A long description",
  "items": [
    {"sku":"A","quantity":2},
    {"sku":"B","quantity":1}
  ]
}
~~~

Nếu cắt giữa "descrip" và "tion" hoặc giữa một chuỗi escape, mỗi đoạn không còn là JSON hợp lệ. Parser cần duy trì trạng thái giữa các lần đọc để xử lý token đang dang dở.

Một InputStream vốn đã có thể trả dữ liệu thành các buffer nhỏ. Jackson parser tự quản lý buffer, token và trạng thái cú pháp khi đọc stream. Ứng dụng không cần tự chia byte theo kích thước cố định rồi parse từng mảnh độc lập.

**Chỉ chia theo ranh giới cấu trúc hoặc framing đã được định nghĩa.** Ví dụ:

- Các phần tử trực tiếp trong một JSON array.
- Mỗi JSON value trên một dòng theo NDJSON.
- Mỗi message trong một message broker.
- Các record trong một định dạng record-oriented như CSV.

Nếu cần chia một JSON document tùy ý thành các đoạn truyền qua mạng, hãy dùng parser có khả năng giữ trạng thái hoặc một protocol framing riêng; không coi mỗi đoạn byte là một JSON document.

## 3. Chọn cấu trúc dữ liệu phù hợp

Có ba hình thức phổ biến khi truyền nhiều object JSON.

### 3.1. Một JSON array

~~~json
[
  {"id":1,"name":"Lan"},
  {"id":2,"name":"Minh"},
  {"id":3,"name":"An"}
]
~~~

Ưu điểm:

- Là một JSON document chuẩn.
- Consumer có thể hiểu rõ đây là một collection.
- Có thể đọc tuần tự các phần tử bằng Jackson.
- Phù hợp với REST API và file JSON trao đổi dữ liệu.

Hạn chế: consumer phải xử lý phần tử bên trong array; nếu stream bị ngắt giữa chừng, toàn bộ document có thể chưa hoàn chỉnh.

### 3.2. Nhiều JSON root values nối tiếp

~~~text
{"id":1,"name":"Lan"}
{"id":2,"name":"Minh"}
{"id":3,"name":"An"}
~~~

Jackson có thể đọc một chuỗi nhiều root values bằng API đọc sequence. Tuy nhiên, nhiều JSON value nối tiếp không phải một JSON document đơn lẻ theo cú pháp JSON thông thường. Hai phía cần thống nhất framing và separator.

### 3.3. NDJSON / JSON Lines

~~~text
{"id":1,"name":"Lan"}
{"id":2,"name":"Minh"}
{"id":3,"name":"An"}
~~~

NDJSON quy định mỗi dòng chứa một JSON text hoàn chỉnh. Đây là một dạng framing hữu ích cho log, event stream và file lớn:

- Có thể xử lý từng dòng độc lập.
- Dễ append record.
- Một record lỗi có thể được xác định theo số dòng.
- Consumer có thể đọc tuần tự mà không phải chờ dấu đóng của một array rất lớn.

NDJSON là một quy ước truyền dữ liệu riêng; đừng nhầm nó với một JSON array được format nhiều dòng. Hãy công bố định dạng, encoding và chính sách dòng trống cho producer/consumer.

## 4. Chuẩn bị kiểu Java và ObjectMapper

Ví dụ dùng DTO đơn giản:

~~~java
import java.math.BigDecimal;

public class Order {
    private String id;
    private BigDecimal amount;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Tạo ObjectMapper và reader/writer một lần:

~~~java
ObjectMapper mapper = new ObjectMapper();

ObjectReader orderReader = mapper.readerFor(Order.class);
ObjectWriter orderWriter = mapper.writerFor(Order.class);
~~~

ObjectReader và ObjectWriter là đối tượng cấu hình bất biến, có thể tái sử dụng. Mapper nên được cấu hình hoàn chỉnh trước khi chia sẻ cho nhiều thread. Không bật/tắt feature hoặc đăng ký module trên một mapper đang được dùng đồng thời.

Nếu DTO cần Java Time, custom serializer hoặc module khác, hãy đăng ký chúng trên mapper dùng cho luồng đọc/ghi trước khi tạo reader/writer.

## 5. Đọc JSON array lớn bằng MappingIterator

MappingIterator<T> là API thuận tiện khi muốn đọc nhiều object cùng kiểu từ một nguồn. Với một JSON array, có thể dùng ObjectReader.readValues():

~~~java
ObjectReader reader = mapper.readerFor(Order.class);

try (MappingIterator<Order> orders = reader.readValues(input)) {
    while (orders.hasNextValue()) {
        Order order = orders.nextValue();
        process(order);
    }
}
~~~

Khi parser gặp array ở cấp root, iterator duyệt các phần tử bên trong. Mỗi lần gọi nextValue() ánh xạ một phần tử sang Order. Ứng dụng không cần tạo List<Order> chứa toàn bộ array.

Nếu đọc từ file:

~~~java
try (InputStream input = Files.newInputStream(path);
     MappingIterator<Order> orders = reader.readValues(input)) {

    while (orders.hasNextValue()) {
        process(orders.nextValue());
    }
}
~~~

MappingIterator có thể quản lý parser mà reader tạo ra. Đóng iterator là điều quan trọng để giải phóng parser và tài nguyên liên quan. Nếu nguồn stream do ứng dụng sở hữu, có thể đóng cả nguồn trong cùng try-with-resources; việc đóng lặp lại một stream chuẩn thường an toàn, nhưng ownership nên được xác định rõ trong abstraction của ứng dụng.

Không gọi readAll() nếu mục tiêu là xử lý streaming, vì phương thức đó đọc phần còn lại vào collection.

## 6. Đọc mảng JSON bằng JsonParser ở cấp token

Khi cần kiểm soát rõ cấu trúc document, có thể dùng Jackson Core trực tiếp. JsonParser đọc token lần lượt:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    JsonToken first = parser.nextToken();

    if (first != JsonToken.START_ARRAY) {
        throw new InvalidDataException("Expected a JSON array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (parser.currentToken() == null) {
            throw new InvalidDataException("Unexpected end of JSON array");
        }

        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw new InvalidDataException("Expected an order object");
        }

        Order order = mapper.readValue(parser, Order.class);
        process(order);
    }

    if (parser.nextToken() != null) {
        throw new InvalidDataException("Unexpected content after array");
    }
}
~~~

Cách này hữu ích khi:

- Cần xác nhận root phải là array.
- Cần kiểm tra token hoặc cấu trúc từng phần tử.
- Cần bỏ qua một nhánh không cần dùng bằng skipChildren().
- Cần đọc envelope lớn nhưng chỉ xử lý một phần.
- Cần ghi nhận tiến độ hoặc áp dụng logic riêng khi gặp token.

Khi mapper.readValue(parser, Order.class) được gọi tại START_OBJECT, Jackson đọc object hiện tại. Parser tiếp tục ở cuối object; vòng lặp gọi nextToken() để đi đến phần tử tiếp theo.

Đừng gọi readValue() cho toàn bộ root array trong khi cũng đang tự duyệt token. Chọn một chiến lược đọc rõ ràng để tránh tiêu thụ cùng token hai lần.

## 7. Đọc envelope lớn và chỉ xử lý một mảng con

Nhiều API không trả một array trực tiếp mà bọc dữ liệu trong metadata:

~~~json
{
  "exportId": "EXP-2026-001",
  "createdAt": "2026-11-12T08:00:00Z",
  "orders": [
    {"id":"ORD-1","amount":100.00},
    {"id":"ORD-2","amount":250.00}
  ],
  "summary": {
    "count": 2
  }
}
~~~

Nếu ánh xạ cả envelope thành một DTO có List<Order>, toàn bộ danh sách vẫn được materialize. Có thể duyệt token và chỉ bind từng phần tử của orders:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new InvalidDataException("Expected an object envelope");
    }

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("orders".equals(fieldName)
                && valueToken == JsonToken.START_ARRAY) {

            while (parser.nextToken() != JsonToken.END_ARRAY) {
                Order order = mapper.readValue(parser, Order.class);
                process(order);
            }

        } else {
            parser.skipChildren();
        }
    }
}
~~~

Đoạn code minh họa việc chỉ đọc mảng orders; trong ứng dụng thật, cần xử lý rõ các field metadata phải giữ lại, field trùng tên, field bắt buộc và trường hợp thiếu orders. skipChildren() bỏ qua toàn bộ object/array con hiện tại mà không tạo cây object cho chúng.

Nếu cần đọc metadata nằm sau orders, có thể lưu giá trị nhỏ cần thiết hoặc tiếp tục duyệt parser đến cuối envelope. Không giữ cả cây JSON nếu mục tiêu là tiết kiệm bộ nhớ.

## 8. Xử lý theo batch nhỏ

Streaming lấy từng object; batching gom một số object để xử lý cùng lúc. Ví dụ, database có thể hiệu quả hơn khi ghi 500 record trong một lần:

~~~java
private static final int BATCH_SIZE = 500;

List<Order> batch = new ArrayList<>(BATCH_SIZE);

try (MappingIterator<Order> orders = reader.readValues(input)) {
    while (orders.hasNextValue()) {
        Order order = orders.nextValue();
        validate(order);
        batch.add(order);

        if (batch.size() == BATCH_SIZE) {
            orderService.saveBatch(List.copyOf(batch));
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        orderService.saveBatch(List.copyOf(batch));
    }
}
~~~

Bộ nhớ ứng dụng lúc này gần với kích thước batch cộng parser buffer và object đang xử lý, thay vì tổng số record. Nếu saveBatch() giữ reference hoặc xử lý bất đồng bộ, truyền snapshot như List.copyOf(batch) để tránh việc batch.clear() làm thay đổi dữ liệu mà downstream đang dùng.

Kích thước batch cần được đo theo:

- Kích thước trung bình của một object.
- Giới hạn parameter hoặc packet của database.
- Thời gian transaction.
- Throughput của downstream service.
- Heap và garbage collection.
- Mức độ chịu lỗi và khả năng retry.

Không có một batch size đúng cho mọi ứng dụng. Hãy bắt đầu bằng giá trị vừa phải, đo latency, throughput và memory rồi điều chỉnh.

## 9. Tạo backpressure thay vì xếp hàng vô hạn

Một lỗi phổ biến là đọc rất nhanh rồi đẩy mọi record vào một queue hoặc danh sách future không giới hạn. Parser có streaming nhưng ứng dụng vẫn có thể hết bộ nhớ vì queue tăng mãi.

Ví dụ không an toàn:

~~~java
while (orders.hasNextValue()) {
    Order order = orders.nextValue();
    futures.add(CompletableFuture.runAsync(
        () -> process(order),
        executor
    ));
}
~~~

Nếu producer nhanh hơn consumer, số task chờ sẽ tăng theo tổng số record. Điều đó biến pipeline thành một dạng materialization gián tiếp.

Các cách kiểm soát:

- Xử lý đồng bộ từng record nếu throughput đủ.
- Dùng queue có capacity giới hạn.
- Khi queue đầy, chặn producer hoặc tạm dừng đọc.
- Chỉ cho phép một số lượng task in-flight cố định.
- Đợi một batch hoàn thành trước khi đọc batch tiếp theo.
- Dùng cơ chế backpressure của framework reactive nếu toàn pipeline hỗ trợ nó.

Một mô hình bounded queue:

~~~java
BlockingQueue<Order> queue = new ArrayBlockingQueue<>(1_000);
~~~

Khi queue đầy, put() chờ consumer lấy bớt phần tử. Nhờ đó tốc độ đọc bị giới hạn theo tốc độ xử lý. Cần có chính sách shutdown, cancellation và truyền lỗi giữa producer/consumer để tránh thread bị treo.

## 10. Đọc NDJSON từng dòng

Nếu format đầu vào là NDJSON, mỗi dòng chứa một JSON object độc lập. Có thể đọc từng dòng và bind từng object:

~~~java
try (BufferedReader lines = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8)) {

    String line;
    long lineNumber = 0;

    while ((line = lines.readLine()) != null) {
        lineNumber++;

        if (line.isBlank()) {
            continue; // Chỉ khi hợp đồng cho phép dòng trống.
        }

        Order order;
        try {
            order = mapper.readValue(line, Order.class);
        } catch (JsonProcessingException exception) {
            throw new InvalidNdjsonRecordException(
                lineNumber,
                exception
            );
        }

        process(order);
    }
}
~~~

Cách này chỉ đúng khi file thực sự tuân theo NDJSON. Không dùng readLine() để đọc một JSON array được format nhiều dòng, vì một dòng vật lý có thể chỉ là một phần của object.

NDJSON không cho phép JSON text của một record chứa newline vật lý chưa escape bên trong string. Newline trong nội dung string phải được biểu diễn bằng escape \\n, nhờ đó newline thực tế có thể dùng làm delimiter record.

Nếu file có thể chứa dòng rất dài, cần giới hạn độ dài record. readLine() có thể tạo một chuỗi lớn tương ứng với toàn bộ dòng; streaming theo record không ngăn một record riêng lẻ chiếm nhiều bộ nhớ.

## 11. Đọc nhiều root values bằng MappingIterator

Một số luồng dùng nhiều JSON root values nối tiếp thay vì array:

~~~text
{"id":"ORD-1","amount":100.00}
{"id":"ORD-2","amount":250.00}
{"id":"ORD-3","amount":75.00}
~~~

Có thể dùng readValues() để đọc sequence:

~~~java
try (MappingIterator<Order> orders = reader.readValues(input)) {
    while (orders.hasNextValue()) {
        process(orders.nextValue());
    }
}
~~~

Trong trường hợp này, mỗi root value là một JSON object riêng. Cần thống nhất với producer cách phân tách record và xử lý whitespace, lỗi giữa các record, cũng như việc một document có thể chứa nhiều root values.

Nếu định dạng là NDJSON, đọc theo dòng thường làm framing và báo lỗi dễ hiểu hơn. Nếu là JSON sequence theo protocol riêng, hãy dùng parser/reader phù hợp và tài liệu hóa chính xác format.

Không gửi nhiều root JSON values rồi gọi readValue() một lần như thể chúng là một JSON array. readValue() thông thường đọc một root value; readValues() được thiết kế cho sequence.

## 12. Ghi JSON array lớn bằng SequenceWriter

Khi ghi một collection lớn, có thể dùng SequenceWriter để phát từng object vào một JSON array:

~~~java
ObjectWriter writer = mapper.writerFor(Order.class);

try (SequenceWriter sequence = writer.writeValuesAsArray(output)) {
    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

writeValuesAsArray() tạo sequence writer với array wrapper. Jackson ghi dấu mở array, mỗi lần write() phát một phần tử, và khi đóng writer sẽ hoàn tất array.

Nếu dữ liệu đến từ database, không cần tải tất cả vào List:

~~~java
try (Writer output = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8);
     SequenceWriter sequence = mapper
        .writerFor(Order.class)
        .writeValuesAsArray(output);
     Stream<Order> source = repository.streamOrders()) {

    Iterator<Order> iterator = source.iterator();

    while (iterator.hasNext()) {
        sequence.write(iterator.next());
    }
}
~~~

Stream từ repository cần được tiêu thụ trong phạm vi transaction/session còn mở. Đừng trả stream ra khỏi transaction rồi mới bắt đầu ghi file nếu cursor phụ thuộc session.

SequenceWriter có thể được dùng cho các nguồn OutputStream, Writer hoặc JsonGenerator. Chọn overload phù hợp với encoding và quyền sở hữu stream của ứng dụng.

## 13. Ghi NDJSON hoặc root sequence

Nếu consumer yêu cầu mỗi JSON object trên một dòng, hãy cấu hình root value separator là newline:

~~~java
ObjectWriter ndjsonWriter = mapper.writerFor(Order.class)
    .withRootValueSeparator("\n");

try (SequenceWriter sequence = ndjsonWriter.writeValues(output)) {
    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

Đây là root sequence với separator newline. Hợp đồng NDJSON còn cần quy định encoding, xử lý dòng trống, record lỗi và newline cuối file. Hãy kiểm tra output thực tế bằng parser NDJSON ở phía consumer.

Dùng writeValuesAsArray() khi output phải là một JSON array; dùng writeValues() với separator phù hợp khi output là một sequence root values. Không nhầm hai định dạng vì chúng có framing khác nhau.

## 14. Ghi theo batch và flush

Có thể ghi một batch, flush output rồi tiếp tục lấy batch kế tiếp:

~~~java
try (SequenceWriter sequence = mapper
        .writerFor(Order.class)
        .writeValuesAsArray(output)) {

    while (true) {
        List<Order> batch = repository.fetchPage(page++, 500);
        if (batch.isEmpty()) {
            break;
        }

        for (Order order : batch) {
            sequence.write(order);
        }

        sequence.flush();
    }
}
~~~

Flush đẩy dữ liệu đang buffer của writer xuống stream bên dưới theo hợp đồng của các lớp liên quan. Nó không nhất thiết đồng nghĩa dữ liệu đã được ghi bền vững xuống disk hoặc đã được consumer nhận và xử lý.

Với file, flush() không thay thế việc đóng stream và kiểm tra lỗi đóng. Với HTTP response, flush có thể gửi bytes tới client; sau khi response đã bắt đầu, ứng dụng thường không thể đổi status code để báo lỗi như trước khi gửi body.

Flush quá thường xuyên có thể làm giảm throughput do tăng số lần ghi hệ thống. Hãy flush theo batch hoặc theo nhu cầu latency, không nhất thiết sau mỗi object.

## 15. Đọc và ghi theo chunk không có nghĩa transaction tự động an toàn

Streaming và batching là quyết định về dữ liệu đi qua bộ nhớ. Chúng không tự quyết định transaction của database hoặc tính atomic của file.

Ví dụ import 1 triệu record theo batch 500:

- Batch 1 có thể đã commit.
- Batch 2 có thể đã commit.
- Record 1.234 bị lỗi.
- Import dừng lại.

Lúc này database có thể chứa một phần dữ liệu. Cần chọn chính sách:

- Toàn bộ file phải thành công hoặc rollback.
- Cho phép commit từng batch và báo partial success.
- Ghi vào staging table rồi validate toàn bộ trước khi publish.
- Dùng job ID, checkpoint và idempotency để resume.
- Ghi error report và cho phép người dùng sửa rồi gửi lại.

Transaction kéo dài cho toàn file có thể giữ lock lâu, tăng undo log và gây áp lực database. Staging thường hữu ích khi cần xác nhận toàn bộ file trước khi thay đổi dữ liệu chính.

## 16. Lỗi parse giữa luồng và partial output

Khi đọc một array lớn, parser có thể thất bại giữa chừng do JSON sai cú pháp hoặc một object không map được. Các object trước đó có thể đã được xử lý.

Khi ghi, lỗi I/O có thể xảy ra sau khi một phần JSON đã được phát ra. Nếu output là file, file đích có thể chứa JSON không hoàn chỉnh. Nếu output là HTTP response, bytes đã gửi không thể thu hồi.

Các chiến lược:

### Với file export

1. Ghi vào file tạm, ví dụ export.json.part.
2. Đóng SequenceWriter và stream để hoàn tất JSON và phát hiện lỗi đóng.
3. Chỉ sau khi thành công mới rename/move sang tên chính thức.
4. Nếu lỗi, xóa file tạm theo chính sách dọn dẹp.
5. Dùng ATOMIC_MOVE khi filesystem hỗ trợ và fallback có chủ đích khi không hỗ trợ.

### Với HTTP response

- Validate và chuẩn bị metadata trước khi gửi body.
- Nếu cần tính atomic, có thể ghi vào file/object storage tạm rồi mới trả link.
- Nếu stream trực tiếp, chấp nhận rằng lỗi sau khi gửi một phần body có thể làm client nhận response bị cắt.
- Cung cấp checksum, content length nếu biết trước, hoặc protocol có trạng thái hoàn tất để client phát hiện output không đầy đủ.

### Với message/event

- Dùng message có ranh giới record và acknowledgement rõ ràng.
- Thiết kế consumer idempotent để retry không tạo side effect trùng.
- Không ack message trước khi dữ liệu tương ứng được xử lý thành công theo semantics của broker.

## 17. Bỏ qua nhánh không cần thiết bằng skipChildren

Khi đọc JSON lớn, có thể chỉ cần một số field. JsonParser.skipChildren() bỏ qua toàn bộ object hoặc array con mà không tạo cây JsonNode cho nhánh đó.

Ví dụ, chỉ cần orders và bỏ qua debugMetadata:

~~~java
while (parser.nextToken() != JsonToken.END_OBJECT) {
    String field = parser.currentName();
    JsonToken valueToken = parser.nextToken();

    if ("orders".equals(field)
            && valueToken == JsonToken.START_ARRAY) {
        readOrders(parser);
    } else {
        parser.skipChildren();
    }
}
~~~

Đối với scalar, skipChildren() không cần đi sâu; với object/array, parser tiêu thụ đến token đóng tương ứng. Sau khi skip, vòng lặp có thể tiếp tục tại field tiếp theo.

Không dùng readTree() cho một nhánh rất lớn nếu không cần truy cập ngẫu nhiên vào toàn bộ nhánh đó. JsonNode tạo object graph và có thể làm mất lợi ích streaming.

## 18. Chọn chunk size

Chunk size quá nhỏ làm tăng số lần gọi database, RPC hoặc commit. Chunk size quá lớn làm tăng heap, latency và thời gian retry.

Có thể bắt đầu với một kích thước nhỏ-vừa, ví dụ 100–1.000 record, rồi đo theo dữ liệu thực tế. Các yếu tố:

| Yếu tố | Tác động khi batch tăng |
|---|---|
| Heap | Tăng theo số object trong batch |
| Throughput DB | Có thể tăng nhờ ít round-trip |
| Transaction duration | Thường dài hơn |
| Latency record đầu tiên | Có thể tăng nếu phải đợi đủ batch |
| Chi phí retry | Có thể tăng nếu batch thất bại |
| Áp lực downstream | Tăng nếu consumer không xử lý kịp |
| Kích thước request/message | Có thể chạm giới hạn hệ thống |

Có thể dùng batch cuối nhỏ hơn batch chuẩn. Không cần đệm cho đủ batch size trước khi xử lý nếu latency quan trọng hoặc file kết thúc sớm.

Nếu kích thước record thay đổi rất lớn, số record không phải thước đo bộ nhớ hoàn hảo. Có thể cần giới hạn tổng số byte hoặc tổng kích thước ước lượng của batch.

## 19. Quản lý InputStream, JsonParser và OutputStream

Streaming kéo dài thời gian giữ tài nguyên. Hãy dùng try-with-resources để đóng đúng lúc:

~~~java
try (InputStream input = Files.newInputStream(path);
     JsonParser parser = mapper.getFactory().createParser(input)) {

    // Parse tuần tự.
}
~~~

Nếu dùng MappingIterator, đóng iterator khi hoàn tất:

~~~java
try (InputStream input = Files.newInputStream(path);
     MappingIterator<Order> iterator = reader.readValues(input)) {

    while (iterator.hasNextValue()) {
        process(iterator.nextValue());
    }
}
~~~

Khi ghi:

~~~java
try (OutputStream output = Files.newOutputStream(path);
     SequenceWriter sequence = mapper.writerFor(Order.class)
         .writeValuesAsArray(output)) {

    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

Cần hiểu ownership của tài nguyên: Jackson có thể đóng parser/generator hoặc target stream theo cấu hình auto-close. Đóng cả lớp wrapper và nguồn bên ngoài trong try-with-resources thường an toàn với stream chuẩn, nhưng abstraction tùy chỉnh cần quy định rõ ai sở hữu và đóng tài nguyên.

Không giữ parser hoặc generator mở qua nhiều request nếu chúng gắn với một stream cụ thể. Mapper/reader/writer có thể tái sử dụng; parser/generator thường thuộc về một lần xử lý.

## 20. Nén dữ liệu khi streaming

Có thể kết hợp Jackson với gzip để giảm dung lượng truyền hoặc lưu trữ:

~~~java
try (OutputStream file = Files.newOutputStream(path);
     GZIPOutputStream gzip = new GZIPOutputStream(file);
     SequenceWriter sequence = mapper.writerFor(Order.class)
         .writeValuesAsArray(gzip)) {

    for (Order order : source) {
        sequence.write(order);
    }
}
~~~

Khi đọc:

~~~java
try (InputStream file = Files.newInputStream(path);
     GZIPInputStream gzip = new GZIPInputStream(file);
     MappingIterator<Order> orders = reader.readValues(gzip)) {

    while (orders.hasNextValue()) {
        process(orders.nextValue());
    }
}
~~~

Compression giảm bytes truyền/lưu nhưng có chi phí CPU. Cần giới hạn cả kích thước sau giải nén để tránh compressed payload nhỏ nhưng giải nén thành dữ liệu khổng lồ. Đo throughput end-to-end thay vì chỉ so sánh kích thước file.

## 21. Async/non-blocking parsing khi input đến theo từng buffer

Trong phần lớn ứng dụng, InputStream hoặc Reader blocking là đủ. Jackson Core cũng có parser non-blocking cho trường hợp dữ liệu đến từng buffer qua network event loop.

Một non-blocking parser có thể trả token NOT_AVAILABLE khi chưa có đủ dữ liệu. Producer cấp thêm bytes qua feeder rồi tiếp tục parse. Luồng xử lý về khái niệm:

~~~text
Network buffer
     |
     v
ByteArrayFeeder.feedInput(...)
     |
     v
Non-blocking JsonParser
     |
     +--> token available --> consume token
     |
     +--> NOT_AVAILABLE --> wait for more bytes
     |
     v
endOfInput()
~~~

API cụ thể phụ thuộc phiên bản Jackson Core và loại feeder, ví dụ ByteArrayFeeder hoặc ByteBufferFeeder. Parser non-blocking không có nghĩa ứng dụng có thể bỏ qua trạng thái token dang dở; cần giữ trạng thái parser và chỉ feed vùng buffer hợp lệ.

Không nên chọn non-blocking parser chỉ vì file lớn. Streaming blocking với InputStream thường đơn giản hơn. Non-blocking hữu ích khi cần tích hợp trực tiếp với event loop hoặc network framework và phải tránh blocking thread.

## 22. Giới hạn kích thước và bảo vệ tài nguyên

Streaming giảm việc giữ toàn bộ document trong heap nhưng không tự bảo vệ ứng dụng khỏi payload quá lớn hoặc cấu trúc độc hại.

Cần cân nhắc:

- Giới hạn byte của request/file.
- Giới hạn độ sâu nesting.
- Giới hạn độ dài string/number.
- Giới hạn số phần tử array.
- Giới hạn thời gian xử lý.
- Giới hạn số job đồng thời.
- Giới hạn batch và queue.
- Giới hạn kích thước sau giải nén.
- Giới hạn số lỗi được ghi lại.

Các phiên bản Jackson Core mới có StreamReadConstraints để giới hạn một số đặc tính như nesting depth, string length và number length. API và default thay đổi theo phiên bản; hãy cấu hình dựa trên dependency thực tế và vẫn áp dụng giới hạn ở tầng HTTP/file upload.

Không log toàn bộ payload lớn khi parse lỗi. Ghi request ID, record index, parser location và một phần metadata đã được kiểm soát. Payload có thể chứa dữ liệu cá nhân hoặc bí mật.

## 23. Kiểm thử streaming

Test đọc nhiều object trong một array:

~~~java
@Test
void readsLargeArrayIncrementally() throws Exception {
    String json = """
        [
          {"id":"ORD-1","amount":100.00},
          {"id":"ORD-2","amount":250.00}
        ]
        """;

    ObjectReader reader = mapper.readerFor(Order.class);
    List<String> ids = new ArrayList<>();

    try (MappingIterator<Order> orders =
            reader.readValues(new StringReader(json))) {
        while (orders.hasNextValue()) {
            ids.add(orders.nextValue().getId());
        }
    }

    assertEquals(List.of("ORD-1", "ORD-2"), ids);
}
~~~

Test ghi nhiều object thành một array:

~~~java
@Test
void writesSequenceAsJsonArray() throws Exception {
    StringWriter output = new StringWriter();

    try (SequenceWriter sequence = mapper
            .writerFor(Order.class)
            .writeValuesAsArray(output)) {
        sequence.write(new Order("ORD-1", new BigDecimal("100.00")));
        sequence.write(new Order("ORD-2", new BigDecimal("250.00")));
    }

    JsonNode root = mapper.readTree(output.toString());

    assertTrue(root.isArray());
    assertEquals(2, root.size());
    assertEquals("ORD-1", root.get(0).get("id").asText());
}
~~~

Ngoài các test cơ bản, nên có test cho:

- Array rỗng.
- Root không phải array khi hợp đồng yêu cầu array.
- JSON bị cắt giữa một object.
- Một object không map được.
- Một field rất dài hoặc nesting quá sâu.
- Lỗi I/O giữa chừng.
- Batch cuối có ít record hơn batch size.
- Downstream chậm và queue đạt capacity.
- Writer lỗi trước khi hoàn tất array.
- File tạm không được công bố khi export thất bại.
- NDJSON có dòng trống hoặc một record sai.
- Gzip stream lỗi hoặc kích thước sau giải nén vượt giới hạn.

Để xác nhận bộ nhớ được giới hạn, có thể chạy integration/performance test với dataset lớn và đo heap/GC. Unit test nhỏ chỉ xác nhận hành vi API; nó không chứng minh throughput hoặc mức tiêu thụ bộ nhớ ở production.

## 24. Đo hiệu năng đúng cách

Khi so sánh cách đọc toàn bộ với streaming, cần đo:

- Thời gian hoàn tất.
- Thời gian tới record đầu tiên.
- Peak heap và allocation rate.
- Garbage collection pause.
- Throughput record/giây.
- Latency của batch và downstream.
- Kích thước input/output.
- Chi phí CPU nếu có compression.

Streaming thường giảm peak memory, nhưng không đảm bảo nhanh hơn trong mọi trường hợp. Nếu downstream chậm, throughput tổng thể vẫn bị giới hạn bởi downstream. Nếu xử lý từng record gọi database riêng lẻ, batching có thể đem lại cải thiện lớn hơn bản thân parser streaming.

Hãy benchmark với dữ liệu đại diện: kích thước field, số field, cấu trúc nested, tỷ lệ lỗi và tốc độ downstream gần với production. Tránh kết luận chỉ từ một file nhỏ nằm hoàn toàn trong cache.

## 25. Những lỗi thường gặp

### Đọc toàn bộ array vào List

Điều này giữ toàn bộ object trong heap. Dùng MappingIterator hoặc JsonParser để xử lý tuần tự.

### Cắt JSON theo số byte cố định

Đoạn cắt có thể nằm giữa token, string escape hoặc object. Để Jackson quản lý buffer và parser state.

### Dùng readAll() rồi gọi đó là streaming

readAll() materialize toàn bộ phần còn lại. Duyệt iterator trực tiếp.

### Dùng readLine() cho JSON array nhiều dòng

Một dòng vật lý không phải một JSON value. Chỉ dùng line framing khi input thực sự là NDJSON.

### Dùng queue hoặc future không giới hạn

Parser streaming nhưng task chờ vẫn tăng vô hạn. Dùng queue bounded và giới hạn số task in-flight.

### Ghi một chuỗi JSON lớn trước khi gửi

writeValueAsString() tạo bản sao dữ liệu lớn. Ghi trực tiếp bằng SequenceWriter hoặc JsonGenerator.

### Cho rằng batch là transaction

Batch chỉ là nhóm công việc. Cần xác định commit, rollback, partial success và idempotency riêng.

### Flush sau mỗi object

Có thể làm giảm throughput. Flush theo batch hoặc theo yêu cầu latency.

### Không xử lý output chưa hoàn chỉnh

Lỗi giữa chừng có thể để lại JSON array thiếu dấu đóng. Dùng file tạm hoặc protocol có trạng thái hoàn tất.

### Giữ tất cả lỗi trong bộ nhớ

Error list có thể trở thành nguồn tăng heap mới. Ghi error sink hoặc giới hạn số lỗi.

### Nghĩ streaming giới hạn kích thước từng object

Một record đơn lẻ vẫn có thể rất lớn. Cấu hình parser constraints và giới hạn input.

### Chọn non-blocking parser quá sớm

API phức tạp hơn và cần quản lý trạng thái buffer. Chỉ dùng khi kiến trúc network/event loop cần nó.

## 26. Quy trình thiết kế luồng đọc/ghi từng phần

1. Xác định định dạng framing: JSON array, root sequence, NDJSON hay message riêng.
2. Xác định dữ liệu có thể xử lý độc lập theo từng object hay không.
3. Chọn MappingIterator cho sequence đơn giản hoặc JsonParser khi cần kiểm soát token.
4. Không chia raw JSON thành các đoạn độc lập theo số byte.
5. Dùng ObjectReader tái sử dụng cho kiểu record.
6. Validate object ngay sau khi parse.
7. Gom batch có giới hạn nếu downstream cần xử lý nhiều record cùng lúc.
8. Tạo backpressure bằng xử lý đồng bộ, queue bounded hoặc giới hạn task in-flight.
9. Ghi output bằng SequenceWriter hoặc JsonGenerator thay vì tạo chuỗi toàn bộ.
10. Chọn array wrapper hoặc root separator theo hợp đồng consumer.
11. Xác định partial failure, retry, transaction và idempotency.
12. Đóng parser, iterator, writer và stream đúng ownership.
13. Dùng file tạm nếu cần công bố output chỉ khi hoàn tất.
14. Giới hạn file, field, nesting, batch, queue, concurrency và thời gian.
15. Đo heap, throughput, latency và GC bằng dữ liệu đại diện.

## 27. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Đọc JSON array nhiều object | ObjectReader.readValues(...) |
| Duyệt từng object | MappingIterator<T> |
| Kiểm soát token và cấu trúc root | JsonParser |
| Bỏ qua object/array con | JsonParser.skipChildren() |
| Không materialize toàn bộ array | Không gọi readAll() |
| Gom một số record để xử lý | Batch có kích thước giới hạn |
| Điều tiết producer/consumer | Queue bounded hoặc backpressure |
| Ghi một JSON array lớn | ObjectWriter.writeValuesAsArray(...) |
| Ghi root sequence | ObjectWriter.writeValues(...) với separator rõ ràng |
| Ghi dữ liệu từ database | Cursor/stream/page, không tải toàn bộ List |
| Ghi file chỉ khi hoàn tất | File tạm rồi move/rename |
| Gửi JSON theo record độc lập | NDJSON hoặc message framing |
| Nhận dữ liệu theo buffer bất đồng bộ | Non-blocking parser và feeder |
| Bảo vệ parser | Giới hạn byte, nesting, string, number và thời gian |
| Kiểm chứng hiệu năng | Benchmark heap, GC, throughput và latency |

## 28. Kết luận

Đọc hoặc ghi từng phần là cách tổ chức luồng dữ liệu để ứng dụng không phải giữ toàn bộ tập object hoặc toàn bộ chuỗi JSON trong bộ nhớ. Với Jackson, MappingIterator đọc tuần tự các giá trị, JsonParser cho phép điều khiển ở cấp token, còn SequenceWriter ghi nhiều object ra một JSON array hoặc root sequence. Batching ở tầng ứng dụng giúp giới hạn công việc mỗi lần xử lý; queue bounded và backpressure ngăn producer tạo hàng đợi vô hạn khi consumer chậm.

Hãy chọn framing phù hợp với consumer, để parser quản lý token thay vì tự cắt JSON theo byte, và xác định rõ cách xử lý lỗi giữa luồng, transaction, retry cùng output chưa hoàn chỉnh. Streaming giảm peak memory nhưng không thay thế giới hạn kích thước từng record, parser constraints, batch size và concurrency. Đo heap, throughput, latency và garbage collection trên dữ liệu đại diện để chọn cấu hình phù hợp với workload thực tế.
