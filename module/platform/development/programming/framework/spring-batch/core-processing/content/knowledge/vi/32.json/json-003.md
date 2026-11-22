# JSON array lớn và streaming

Khi xử lý một file JSON chứa hàng trăm nghìn hoặc hàng triệu object, cách đọc toàn bộ tài liệu vào một `List` có thể làm bộ nhớ tăng theo kích thước file. Nếu file lớn hơn heap khả dụng, ứng dụng có thể gặp `OutOfMemoryError`, GC kéo dài hoặc giảm mạnh throughput.

Trong Spring Batch, cách phù hợp cho JSON array lớn là đọc từng object theo dạng streaming, đưa từng item vào chunk processing rồi ghi kết quả theo từng chunk. `JsonItemReader` kết hợp với `JacksonJsonObjectReader` hỗ trợ mô hình này: reader duyệt mảng JSON và tạo một Java object cho mỗi lần đọc, thay vì deserialize toàn bộ array thành một collection trong bộ nhớ.

Streaming không có nghĩa bộ nhớ luôn cố định tuyệt đối. Bộ nhớ còn phụ thuộc kích thước object lớn nhất, chunk size, buffer, processor, writer và các dữ liệu ứng dụng giữ lại. Vì vậy cần thiết kế cả định dạng JSON, reader, chunk size và checkpoint.

## 1. Vì sao JSON array lớn cần streaming?

Một file JSON array thông thường có dạng:

```json
[
  {"id":"C001","name":"Nguyen An","active":true},
  {"id":"C002","name":"Tran Binh","active":false},
  {"id":"C003","name":"Le Chi","active":true}
]
```

Mỗi phần tử trong mảng là một item độc lập. Nếu dùng cách đọc toàn bộ:

```java
List<Customer> customers = objectMapper.readValue(
        inputFile,
        new TypeReference<List<Customer>>() {});
```

Jackson phải tạo collection và giữ tất cả `Customer` trong bộ nhớ cùng lúc. Với một triệu item, bộ nhớ không chỉ chứa byte của file mà còn chứa object header, String, collection entry, field object và dữ liệu tạm trong quá trình parse.

Với streaming, parser đọc từng object:

```text
JSON array trên disk
       |
       v
Parser đọc object tiếp theo
       |
       v
Một Java item
       |
       v
Spring Batch gom tối đa chunk-size item
       |
       v
Processor / Writer
       |
       v
Commit chunk và giải phóng item đã xử lý
       |
       v
Đọc object tiếp theo
```

Thay vì giữ toàn bộ danh sách, ứng dụng giữ parser state, một item đang đọc, dữ liệu trong chunk và các buffer cần thiết. Điều này giúp xử lý file lớn với mức bộ nhớ có thể dự đoán và kiểm soát tốt hơn.

## 2. Phân biệt streaming và deserialize toàn bộ

Hai cách tiếp cận có hành vi bộ nhớ khác nhau:

| Cách đọc | Cách hoạt động | Đặc điểm bộ nhớ |
|---|---|---|
| Deserialize toàn bộ array | `ObjectMapper.readValue(... List<T>)` tạo danh sách chứa mọi object. | Tăng theo tổng số item và dữ liệu của cả file. |
| Streaming từng item | Parser đọc một object, trả object đó cho reader rồi tiếp tục. | Chủ yếu phụ thuộc object hiện tại, chunk, buffer và state. |
| Streaming thủ công | Dùng Jackson `JsonParser` hoặc StAX-like token processing để đọc token và tự quản lý item boundary. | Có thể kiểm soát chi tiết hơn, nhưng phải tự quản lý lifecycle, lỗi và checkpoint. |

Ví dụ không nên dùng với file rất lớn:

```java
List<Customer> allCustomers = objectMapper.readValue(
        resource.getInputStream(),
        new TypeReference<List<Customer>>() {});

for (Customer customer : allCustomers) {
    customerService.process(customer);
}
```

Đoạn code này có thể phù hợp với file nhỏ, nhưng không tận dụng chunk processing và checkpoint của Spring Batch. Nếu job thất bại giữa vòng lặp, ứng dụng cũng phải tự thiết kế cách tiếp tục và tránh xử lý lặp.

## 3. Cấu trúc JSON mà JsonItemReader hỗ trợ

`JsonItemReader<T>` của Spring Batch được thiết kế để đọc một resource JSON có root là array các object. Ví dụ:

```json
[
  {"customerId":"C001","name":"Nguyen An"},
  {"customerId":"C002","name":"Tran Binh"}
]
```

Mỗi object trong array trở thành một item kiểu `T`. Reader không cần tạo `List<T>` chứa cả array.

Định dạng này khác với một số kiểu JSON khác:

**Một object bao toàn bộ collection:**

```json
{
  "batchDate": "2026-11-15",
  "customers": [
    {"customerId":"C001"},
    {"customerId":"C002"}
  ]
}
```

Nếu reader được thiết kế để đọc array ở root, cấu trúc object bao ngoài này không khớp trực tiếp. Cần dùng reader tùy chỉnh, chuyển đổi nguồn hoặc thiết kế parser để đi đến `customers` array.

**JSON Lines / NDJSON:**

```text
{"customerId":"C001","name":"Nguyen An"}
{"customerId":"C002","name":"Tran Binh"}
{"customerId":"C003","name":"Le Chi"}
```

Mỗi dòng là một JSON document riêng, không có dấu ngoặc array bao ngoài. `JsonItemReader` dành cho JSON array không nên được giả định là reader NDJSON. Với JSON Lines, có thể dùng custom `ItemStreamReader` đọc từng dòng rồi deserialize từng dòng hoặc dùng một reader phù hợp định dạng.

## 4. Các thành phần JSON của Spring Batch

Spring Batch cung cấp abstraction để đọc và ghi JSON theo item:

| Thành phần | Trách nhiệm |
|---|---|
| `JsonItemReader<T>` | Đọc JSON array theo từng item. |
| `JsonObjectReader<T>` | Chuyển một JSON object thành Java object. |
| `JacksonJsonObjectReader<T>` | Implementation của `JsonObjectReader` dùng Jackson. |
| `GsonJsonObjectReader<T>` | Implementation dùng Gson. |
| `JsonFileItemWriter<T>` | Ghi các item thành JSON array. |
| `JsonObjectMarshaller<T>` | Chuyển một Java object thành JSON representation. |
| `JacksonJsonObjectMarshaller<T>` | Implementation marshaller dùng Jackson. |
| `GsonJsonObjectMarshaller<T>` | Implementation marshaller dùng Gson. |

Spring Batch quản lý việc gọi reader/writer theo chunk. Jackson hoặc Gson đảm nhiệm chuyển đổi một object tại một thời điểm.

## 5. Cấu hình JsonItemReader với Jackson

Giả sử mỗi item là một customer:

```java
public record Customer(
        String customerId,
        String name,
        String email,
        boolean active) {
}
```

Cấu hình reader:

```java
@Bean
@StepScope
JsonItemReader<Customer> customerJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<Customer>()
            .name("customerJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Customer.class))
            .saveState(true)
            .build();
}
```

Các phần chính:

- `name(...)` đặt tên ổn định cho reader; tên này được dùng trong metadata/checkpoint.
- `resource(...)` chỉ định file JSON đầu vào.
- `jsonObjectReader(...)` chọn cách deserialize từng object.
- `saveState(true)` cho phép reader lưu vị trí đọc vào `ExecutionContext` để hỗ trợ restart.
- `@StepScope` cho phép lấy input path từ JobParameters của lần chạy.

`JsonItemReader` sẽ đọc các phần tử trong root array và trả về một `Customer` cho mỗi lần gọi `read()`. Không cần gọi `ObjectMapper.readValue` với `List<Customer>`.

## 6. Tích hợp reader vào chunk-oriented step

Sau khi cấu hình reader, có thể dùng nó như bất kỳ `ItemReader` nào khác:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Customer> customerJsonReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerJsonReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Với chunk size 500, step đọc tối đa 500 item cho một chunk, xử lý chúng rồi gọi writer. Khi transaction commit, framework cập nhật checkpoint theo lifecycle của reader/step.

Chunk size là tham số cần đo đạc:

- Chunk quá nhỏ có thể tăng số lần commit và overhead metadata.
- Chunk quá lớn làm tăng lượng object cùng tồn tại trong heap và kéo dài transaction.
- Object có nested collection hoặc payload lớn cần chunk nhỏ hơn.
- Writer gọi database hoặc dịch vụ ngoài có thể có giới hạn batch riêng.

Không có một chunk size đúng cho mọi file. Hãy benchmark với kích thước item và hạ tầng gần với production.

## 7. Đọc một object có nested array

Một JSON item có thể chứa collection lồng bên trong:

```json
[
  {
    "orderId": "O-100",
    "customerId": "C001",
    "lines": [
      {"sku":"SKU-01","quantity":2},
      {"sku":"SKU-02","quantity":1}
    ]
  },
  {
    "orderId": "O-101",
    "customerId": "C002",
    "lines": [
      {"sku":"SKU-03","quantity":4}
    ]
  }
]
```

Model có thể là:

```java
public record OrderLine(String sku, int quantity) {
}

public record Order(
        String orderId,
        String customerId,
        List<OrderLine> lines) {
}
```

`JsonItemReader<Order>` đọc một order tại một thời điểm. Tuy nhiên, toàn bộ `lines` của order hiện tại vẫn được deserialize thành một `List<OrderLine>`.

Điều này có nghĩa streaming ở cấp item không tự chia nhỏ nested array. Nếu một order chứa hàng triệu line, một item có thể vẫn rất lớn. Khi đó cần cân nhắc:

- Thay đổi đơn vị item thành từng line nếu nghiệp vụ cho phép.
- Dùng custom streaming reader để đọc nested array theo từng phần tử.
- Chia input thành nhiều file/partition nhỏ hơn.
- Giới hạn số phần tử hoặc kích thước payload của mỗi object.
- Chỉ đọc các field cần thiết nếu có thể dùng parser streaming tùy chỉnh.

## 8. Streaming bằng Jackson JsonParser

Ở mức thấp hơn, Jackson cung cấp streaming API thông qua `JsonFactory` và `JsonParser`. Parser duyệt token lần lượt mà không cần tạo cây JSON (`JsonNode`) cho toàn bộ document.

Ví dụ khái niệm đọc root array:

```java
try (InputStream input = resource.getInputStream();
     JsonParser parser = jsonFactory.createParser(input)) {

    JsonToken first = parser.nextToken();
    if (first != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected a JSON array");
    }

    while (parser.nextToken() != JsonToken.END_ARRAY) {
        Customer customer = objectMapper.readValue(parser, Customer.class);
        process(customer);
    }
}
```

Đoạn code minh họa nguyên lý: parser đọc đến đầu mỗi object và Jackson bind object đó. `JsonItemReader` đã đóng gói phần quản lý đọc array và tích hợp với Spring Batch, vì vậy nên ưu tiên dùng reader có sẵn khi định dạng đầu vào phù hợp.

Custom parser phù hợp khi cấu trúc không phải root array đơn giản, cần xử lý token đặc biệt, muốn đọc một nested array lớn theo item nhỏ hơn hoặc cần kiểm soát chi tiết việc xử lý từng token.

Không nên dùng `ObjectMapper.readTree(input)` cho một JSON document cực lớn nếu mục tiêu là giới hạn bộ nhớ. `readTree` tạo cây node đại diện cho document; nó vẫn có thể giữ toàn bộ cấu trúc trong RAM.

## 9. Khi nào cần custom ItemStreamReader?

`JsonItemReader` phù hợp với root array các object. Có thể cần custom reader trong những trường hợp:

- JSON có object bao ngoài rồi mới đến array cần đọc.
- Input là NDJSON/JSON Lines.
- Cần tách nested array thành item độc lập.
- Cần bỏ qua metadata hoặc xử lý nhiều loại object theo discriminator.
- Cần kiểm soát chính xác checkpoint theo byte offset, token hoặc record key.
- Cần giới hạn kích thước từng object trước khi deserialize.

Một custom reader cần quản lý đúng lifecycle `ItemStream`:

| Method | Trách nhiệm |
|---|---|
| `open(ExecutionContext)` | Mở resource/parser và khôi phục checkpoint. |
| `read()` | Trả về item tiếp theo hoặc `null` khi hết dữ liệu. |
| `update(ExecutionContext)` | Lưu vị trí/trạng thái để restart. |
| `close()` | Đóng parser và resource. |

Nếu reader không implement `ItemStream` hoặc không lưu state, restart có thể đọc lại từ đầu hoặc không khôi phục được vị trí. Với reader tự viết, cần định nghĩa checkpoint sao cho chỉ xác nhận item đã commit mới được xem là đã xử lý.

## 10. Ví dụ NDJSON reader đơn giản

NDJSON có một JSON object trên mỗi dòng. Một cách đơn giản là đọc từng dòng bằng `BufferedReader` và deserialize dòng đó. Reader dưới đây minh họa việc lưu số dòng đã đọc; trong ứng dụng thực tế cần cân nhắc tính ổn định của file và chi phí skip đến checkpoint khi restart.

```java
public class CustomerNdjsonReader implements ItemStreamReader<Customer> {

    private static final String LINE_KEY = "customerNdjsonReader.line";

    private final Resource resource;
    private final ObjectMapper objectMapper;
    private BufferedReader reader;
    private long lineNumber;

    public CustomerNdjsonReader(Resource resource, ObjectMapper objectMapper) {
        this.resource = resource;
        this.objectMapper = objectMapper;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = new BufferedReader(new InputStreamReader(
                    resource.getInputStream(), StandardCharsets.UTF_8));
            lineNumber = context.getLong(LINE_KEY, 0L);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    break;
                }
            }
        } catch (IOException exception) {
            throw new ItemStreamException("Cannot open NDJSON resource", exception);
        }
    }

    @Override
    public Customer read() throws Exception {
        String line = reader.readLine();
        if (line == null) {
            return null;
        }
        lineNumber++;
        if (line.isBlank()) {
            return read();
        }
        return objectMapper.readValue(line, Customer.class);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_KEY, lineNumber);
    }

    @Override
    public void close() throws ItemStreamException {
        try {
            if (reader != null) {
                reader.close();
            }
        } catch (IOException exception) {
            throw new ItemStreamException("Cannot close NDJSON resource", exception);
        }
    }
}
```

Đây là ví dụ đơn giản để giải thích checkpoint theo dòng, không phải implementation tối ưu cho mọi file lớn. Khi restart, reader phải đọc bỏ qua các dòng đã checkpoint nên thời gian mở lại tăng theo vị trí trong file. Với file rất lớn, có thể cần byte offset, index hoặc chia file thành các phần độc lập. Nếu một dòng có thể cực lớn, `readLine()` vẫn tạo một String lớn trong bộ nhớ; cần giới hạn kích thước dòng hoặc dùng parser streaming trên byte stream.

Một reader production cũng cần xử lý dòng rỗng, dòng lỗi, BOM, encoding, giới hạn kích thước, checkpoint transaction và trường hợp file thay đổi giữa các lần chạy. Input phải bất biến trong suốt vòng đời của JobInstance.

## 11. JsonItemReader và checkpoint/restart

`JsonItemReader` hỗ trợ lưu trạng thái đọc qua `ExecutionContext` khi `saveState(true)`. Khi chunk commit, Spring Batch cập nhật trạng thái reader theo cơ chế `ItemStream`.

Ví dụ:

```text
JSON array: [item1, item2, item3, item4, item5, ...]

Chunk 1: item1-item500 -> commit -> checkpoint
Chunk 2: item501-item1000 -> commit -> checkpoint
Chunk 3: item1001-item1500 -> lỗi trước commit

Restart:
  khôi phục checkpoint đã commit
  đọc lại phần chưa commit
  tiếp tục các item tiếp theo
```

Khi thiết kế restart:

- Giữ tên reader ổn định.
- Giữ nguyên identifying JobParameters và input resource.
- Giữ `saveState(true)`.
- Không thay nội dung file trong khi JobInstance còn có thể restart.
- Writer cần idempotent hoặc transactionally consistent để không ghi trùng tác dụng phụ.

Nếu tắt `saveState`, reader không thể dựa vào checkpoint mặc định để tiếp tục đúng vị trí. Job có thể phải đọc lại từ đầu hoặc cần cơ chế tự quản lý khác.

## 12. Input JSON phải bất biến khi restart

Checkpoint thường mô tả vị trí/tiến độ trong resource, không phải snapshot nội dung của file. Nếu file bị thay đổi giữa lần chạy đầu và restart, cùng vị trí có thể trỏ tới object khác.

Ví dụ:

```text
Lần chạy đầu:
  item 1 = C001
  item 2 = C002
  item 3 = C003

Checkpoint sau item 2

File bị thay thế:
  item 1 = C100
  item 2 = C200
  item 3 = C300

Restart từ vị trí sau item 2 có thể tiếp tục trên một tập dữ liệu khác.
```

Nên lưu input file theo batch ID, checksum hoặc version bất biến. Nếu cần sửa dữ liệu, tạo một JobInstance/batch mới theo quy tắc nghiệp vụ thay vì âm thầm thay file dưới một JobInstance đã có checkpoint.

## 13. Streaming writer cho JSON output

Spring Batch cung cấp `JsonFileItemWriter<T>` để ghi item thành một JSON array. Có thể dùng `JacksonJsonObjectMarshaller` để serialize từng item.

Ví dụ:

```java
@Bean
@StepScope
JsonFileItemWriter<Customer> customerJsonWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new JsonFileItemWriterBuilder<Customer>()
            .name("customerJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
```

Writer tạo JSON array và ghi từng item theo chunk. Cách này tránh phải gom toàn bộ kết quả vào `List<Customer>` rồi serialize một lần.

Khi ghi file output lớn, cần chú ý:

- `saveState(true)` để hỗ trợ restart.
- Tên writer và resource ổn định trong cùng JobInstance.
- Chọn overwrite/append theo vòng đời output.
- Không để nhiều job/partition cùng ghi một file nếu không có cơ chế đồng bộ.
- Xác nhận output JSON hợp lệ sau khi job hoàn tất.

## 14. JSON writer và transaction boundary

Chunk writer thường phối hợp với transaction manager để quản lý commit và state. Tuy nhiên, file system không phải database transaction resource thông thường. Nếu process chết đúng lúc ghi/flush file, metadata và file vật lý có thể cần được đối soát.

Đối với output quan trọng, một pattern an toàn là:

1. Ghi JSON vào file tạm riêng cho JobInstance.
2. Hoàn tất step và kiểm tra JSON parse được, số item và checksum.
3. Publish bằng move/rename sang tên file chính thức.
4. Chỉ công bố file sau khi publish step hoàn tất.

Nếu publish đã thành công nhưng metadata commit thất bại, lần restart cần nhận biết file đã được publish để thao tác có tính idempotent. Không giả định transaction database sẽ tự rollback thao tác rename file.

## 15. Chọn chunk size cho JSON lớn

Chunk size tác động trực tiếp đến bộ nhớ, throughput và transaction duration.

Ví dụ cùng một file 2 triệu item:

| Chunk size | Số chunk xấp xỉ | Đặc điểm |
|---:|---:|---|
| 50 | 40.000 | Transaction ngắn, overhead commit nhiều. |
| 500 | 4.000 | Có thể là điểm bắt đầu để benchmark. |
| 5.000 | 400 | Ít commit hơn nhưng nhiều object cùng tồn tại và transaction dài hơn. |

Đây là số liệu minh họa theo phép chia, không phải khuyến nghị chunk size cố định. Hãy chọn dựa trên:

- Kích thước object trung bình và lớn nhất.
- Số lượng field và nested collection.
- Bộ nhớ heap được cấp cho batch worker.
- Chi phí processor và writer.
- Khả năng batch insert/update của database.
- Timeout và lock duration của transaction.
- Số worker/partition chạy đồng thời.

Nếu item chứa payload lớn, chunk size 500 có thể vẫn quá cao. Có thể bắt đầu thấp, đo heap/GC/throughput rồi tăng dần. Đừng tối ưu chỉ theo số item/giây nếu điều đó làm heap gần ngưỡng OOM.

## 16. Streaming không loại bỏ mọi vấn đề bộ nhớ

Streaming giới hạn số object được materialize cùng lúc, nhưng vẫn có thể gặp áp lực bộ nhớ trong các trường hợp:

- Một object đơn lẻ có nested array rất lớn.
- Processor giữ object trong cache hoặc collection dùng chung.
- Writer buffer toàn bộ output trước khi ghi.
- Ứng dụng lưu mọi item đã xử lý vào một `List` để thống kê.
- Chunk size quá lớn.
- Nhiều partition chạy song song, mỗi partition giữ chunk riêng.
- Jackson tạo cây `JsonNode` cho object quá lớn thay vì bind streaming vào model cần thiết.

Để giữ memory bounded:

- Chọn item boundary hợp lý.
- Không giữ tham chiếu tới item sau khi chunk đã được ghi.
- Dùng aggregate counter thay vì tích lũy toàn bộ item.
- Giới hạn kích thước field/nested collection theo hợp đồng dữ liệu.
- Chọn chunk size dựa trên kích thước byte thực tế, không chỉ số item.
- Giới hạn concurrency nếu mỗi worker cần nhiều heap.
- Theo dõi heap, allocation rate, GC pause và thời gian xử lý.

## 17. JSON Schema và validation theo item

JSON parser xác nhận cú pháp JSON và Jackson binding chuyển field sang Java type. Điều đó không đảm bảo dữ liệu thỏa schema hoặc quy tắc nghiệp vụ.

Ví dụ object có cú pháp hợp lệ:

```json
{"customerId":"","age":-5,"active":"yes"}
```

Object vẫn có thể parse một phần hoặc gây lỗi conversion tùy model, nhưng dữ liệu rỗng/âm có thể vi phạm nghiệp vụ.

Nên tách các tầng:

- JSON syntax: cấu trúc JSON hợp lệ.
- Object mapping: field có thể chuyển sang kiểu Java.
- Schema validation: field bắt buộc, kiểu, range và cấu trúc đúng JSON Schema.
- Business validation: quy tắc nghiệp vụ như customer tồn tại, age hợp lệ hoặc trạng thái được phép.

Có thể thực hiện validation theo item trong `ItemProcessor`. Nếu validation thất bại, ném exception nghiệp vụ cụ thể và quyết định skip hay fail theo policy.

Với file rất lớn, tránh parse toàn bộ document chỉ để validate trước bằng một thư viện tạo tree lớn. Có thể validate từng item khi streaming hoặc dùng validator hỗ trợ streaming nếu yêu cầu schema phức tạp.

## 18. Xử lý lỗi JSON và skip policy

Lỗi JSON có thể xảy ra ở cấp toàn document hoặc một object:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| JSON syntax toàn file | Thiếu dấu `]`, dấu ngoặc không cân bằng. | Step thất bại; file không phải một array hợp lệ. |
| Object không map được | Chuỗi không chuyển được sang số hoặc ngày. | Có thể skip item nếu parser khôi phục được ranh giới và nghiệp vụ cho phép. |
| Thiếu field nghiệp vụ | `customerId` rỗng. | Processor validate, reject/skip theo quy tắc. |
| File I/O | File mất giữa lúc đọc, quyền truy cập bị từ chối. | Step thất bại hoặc retry lỗi hạ tầng phù hợp. |
| Schema version không hỗ trợ | Field/structure khác version được triển khai. | Từ chối file hoặc route sang mapper version phù hợp. |

Không nên cấu hình skip cho mọi exception parse. Khi JSON array bị hỏng cấu trúc, parser có thể không biết vị trí bắt đầu của object tiếp theo. Cố bỏ qua exception có thể làm mất đồng bộ parser và bỏ qua phần còn lại.

Nếu cần tiếp tục sau một object sai, hãy xác nhận reader/parser có thể khôi phục đến ranh giới object kế tiếp. Có thể cần custom reader lưu raw fragment hoặc line để ghi rejected data.

## 19. Giới hạn kích thước và bảo vệ parser

Input JSON có thể đến từ hệ thống ngoài và không phải lúc nào cũng đáng tin cậy. Nên kiểm soát:

- Kích thước tối đa của file.
- Kích thước tối đa của một JSON object hoặc một dòng NDJSON.
- Độ sâu nesting tối đa.
- Độ dài tối đa của String/number token nếu thư viện hỗ trợ.
- Số phần tử trong nested collection.
- Các tính năng polymorphic deserialization.

Không bật Jackson default typing một cách rộng rãi cho dữ liệu JSON không tin cậy. Polymorphic type metadata có thể khiến Jackson khởi tạo kiểu ngoài dự kiến nếu cấu hình quá rộng. Nếu cần polymorphism, dùng allowlist type hoặc discriminator được kiểm soát.

Giới hạn parser cụ thể phụ thuộc phiên bản Jackson. Có thể cấu hình `StreamReadConstraints` ở các phiên bản hỗ trợ; hãy xác nhận API hiện có trong dependency thực tế. Ngoài giới hạn parser, cần kiểm tra kích thước file ở tầng nhận dữ liệu và giới hạn tài nguyên ở process/container.

## 20. JSON array có metadata và nhiều loại record

Một số nguồn dùng cấu trúc:

```json
{
  "version": "2",
  "generatedAt": "2026-11-15T10:00:00Z",
  "records": [
    {"type":"CUSTOMER","customerId":"C001"},
    {"type":"ORDER","orderId":"O001"}
  ]
}
```

Đây không phải root array đơn giản. Có thể xử lý theo các hướng:

- Dùng custom Jackson streaming reader tìm field `records` rồi đọc từng object.
- Tách bước kiểm tra metadata/header và bước đọc array bằng reader chuyên biệt.
- Chuẩn hóa nguồn thành root array hoặc NDJSON trước khi đưa vào batch.
- Dùng discriminator `type` để route từng object sang mapper phù hợp.

Không nên deserialize toàn bộ wrapper thành một object chứa `List<Object>` nếu `records` có hàng triệu phần tử. Điều đó đưa toàn bộ collection vào heap và làm mất lợi ích streaming.

Nếu có nhiều loại record, hãy định nghĩa cách phân loại rõ ràng. Có thể dùng một DTO envelope nhẹ để đọc discriminator rồi ánh xạ payload tương ứng, hoặc custom parser để chọn class theo `type`.

## 21. JSON array lớn và partitioning

Có thể partition batch khi dữ liệu được chia thành các nguồn hoặc phạm vi độc lập. Tuy nhiên, một JSON array duy nhất không dễ chia theo byte offset tùy ý vì dấu ngoặc, escape string và nested structure có thể cắt ngang token.

Các chiến lược phù hợp hơn:

- Chia file đầu vào thành nhiều JSON array hợp lệ trước khi chạy partition.
- Dùng NDJSON để mỗi dòng là một record có thể phân chia theo line range nếu giữ đúng byte offset/encoding.
- Partition theo key/range từ database thay vì chia file JSON tùy tiện.
- Dùng custom parser/index để xác định boundary object an toàn nếu thực sự cần phân vùng một file lớn.

Nếu mỗi partition xử lý một file riêng, mỗi worker có reader state và output riêng. Hãy giữ mapping giữa partition ID và resource ổn định qua restart. Không để nhiều worker cùng ghi vào một JSON output file nếu writer không được thiết kế cho concurrent access.

## 22. Kiểm thử streaming reader

Test nên xác nhận reader trả từng object theo đúng thứ tự và kết thúc bằng `null` khi hết array.

Ví dụ:

```java
@Test
void readsItemsOneAtATimeFromJsonArray() throws Exception {
    JsonItemReader<Customer> reader = new JsonItemReaderBuilder<Customer>()
            .name("customerReader")
            .resource(new ClassPathResource("customers.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Customer.class))
            .saveState(true)
            .build();

    reader.open(new ExecutionContext());
    try {
        Customer first = reader.read();
        Customer second = reader.read();
        Customer end = reader.read();

        assertThat(first.customerId()).isEqualTo("C001");
        assertThat(second.customerId()).isEqualTo("C002");
        assertThat(end).isNull();
    } finally {
        reader.close();
    }
}
```

Test nên có các fixture:

- Array rỗng.
- Một item và nhiều item.
- Object có nested object/array.
- Field thiếu, null hoặc sai kiểu.
- JSON syntax lỗi.
- File encoding không hợp lệ.
- File có kích thước lớn đủ để xác nhận reader không tạo collection toàn bộ trong ứng dụng.

Một unit test vài item chỉ xác nhận mapping và thứ tự. Để kiểm tra bộ nhớ, cần chạy benchmark/load test với dữ liệu đại diện và quan sát heap/GC.

## 23. Kiểm thử checkpoint và restart

Để xác nhận reader khôi phục đúng vị trí, cần integration test với JobRepository và transaction manager:

1. Khởi chạy job với input JSON bất biến và identifying parameters cố định.
2. Cho một số chunk commit thành công.
3. Làm step thất bại ở chunk sau.
4. Xác nhận checkpoint của reader đã được lưu.
5. Restart cùng JobInstance với cùng resource và reader name.
6. Xác nhận các item đã commit không bị xử lý lại ngoài semantics dự kiến.
7. Xác nhận item chưa commit được đọc lại.
8. Xác nhận writer không tạo dữ liệu trùng.

Không thay file JSON giữa lần chạy đầu và restart. Nếu thay file, checkpoint có thể không còn tương ứng với nội dung. Cũng không thay reader name hoặc tắt `saveState` giữa hai lần chạy.

## 24. Theo dõi hiệu năng và bộ nhớ

Với JSON array lớn, nên theo dõi ít nhất:

- Số item đã đọc, xử lý và ghi.
- Thời gian parse trung bình và percentile nếu có metric phù hợp.
- Throughput item/giây và byte/giây.
- Heap used, allocation rate và GC pause.
- Chunk duration và commit duration.
- Tỷ lệ lỗi mapping/validation và số item bị skip.
- Thời gian reader mở lại khi restart.
- Số partition/worker đồng thời.

Nếu heap tăng đều theo số item đã đọc dù reader streaming, hãy tìm nơi ứng dụng đang giữ reference. Các nguyên nhân thường gặp là cache không giới hạn, list dùng để tổng hợp, metric giữ tag theo từng ID hoặc processor tích lũy item.

Khi throughput thấp, kiểm tra cả parse, processor, writer và downstream. Jackson streaming không giúp nhiều nếu mỗi item phải gọi một API tuần tự chậm hoặc writer commit từng record riêng lẻ.

## 25. Những lỗi thường gặp khi xử lý JSON lớn

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `OutOfMemoryError` | Deserialize toàn bộ array thành `List`, hoặc giữ item trong collection. | Dùng `JsonItemReader`/parser streaming và bỏ reference sau khi xử lý. |
| Reader không đọc được JSON wrapper | Reader mong root array nhưng file có root object chứa array. | Dùng custom reader hoặc chuẩn hóa input. |
| NDJSON bị parse lỗi | Dùng reader cho JSON array với file mỗi dòng một document. | Dùng reader theo dòng hoặc custom `ItemStreamReader`. |
| Một item vẫn tiêu tốn nhiều heap | Nested array quá lớn trong một object. | Đổi item boundary, giới hạn payload hoặc đọc nested data streaming. |
| Restart đọc lại quá nhiều | `saveState` tắt hoặc checkpoint không được khôi phục. | Bật save state, giữ reader name và input ổn định. |
| Restart đọc sai record | File thay đổi sau khi checkpoint được lưu. | Dùng input bất biến theo batch ID/checksum. |
| JSON lỗi làm skip toàn bộ phần sau | Parser không thể khôi phục ranh giới object. | Dừng job hoặc dùng định dạng record boundary rõ như NDJSON. |
| Chunk lớn gây GC pause | Quá nhiều object cùng tồn tại trong một chunk. | Giảm chunk size và benchmark. |
| Output JSON không hợp lệ sau lỗi | File writer/metadata không đồng bộ hoặc output được consumer đọc khi chưa hoàn tất. | Dùng save state, staging, validation và publish step. |
| Nhiều worker ghi hỏng file | Concurrent writer cùng resource. | File riêng theo partition rồi merge. |
| JSON field sai kiểu | Jackson conversion không phù hợp dữ liệu nguồn. | Dùng DTO/serializer phù hợp, validate và phân loại lỗi. |
| Parser nhận type không mong muốn | Polymorphic typing quá rộng hoặc payload không tin cậy. | Dùng allowlist/discriminator và giới hạn parser. |

## 26. Quy trình triển khai JSON array lớn

Khi xây dựng job xử lý một JSON array lớn, có thể đi theo trình tự:

1. **Xác định định dạng:** root array, wrapper object hay NDJSON; xác định item boundary.
2. **Xác định kích thước:** số record, kích thước object trung bình/lớn nhất và nested collection.
3. **Tạo DTO:** mô tả field và kiểu dữ liệu; không đưa toàn bộ array vào một model collection.
4. **Chọn reader:** dùng `JsonItemReader` cho root array; custom reader cho wrapper, NDJSON hoặc nested streaming.
5. **Bật checkpoint:** đặt tên reader ổn định và `saveState(true)` nếu cần restart.
6. **Cấu hình chunk:** chọn giá trị ban đầu dựa trên heap và kích thước item, sau đó benchmark.
7. **Xử lý từng item:** validate/mapping trong processor, không tích lũy mọi item.
8. **Ghi output:** dùng writer streaming hoặc database batch writer; bảo vệ output bằng idempotency.
9. **Kiểm soát lỗi:** phân biệt lỗi syntax toàn file, lỗi object và lỗi nghiệp vụ; chỉ skip khi có thể khôi phục an toàn.
10. **Kiểm soát resource:** giới hạn file/object/depth, concurrency và parser features.
11. **Kiểm thử restart:** dùng JobRepository và input bất biến để xác nhận checkpoint.
12. **Đo vận hành:** theo dõi heap, GC, throughput, chunk time và số lỗi.

## 27. Những điểm cần ghi nhớ

- Không deserialize một JSON array rất lớn thành `List<T>` nếu mục tiêu là giữ bộ nhớ bounded.
- `JsonItemReader<T>` đọc root array theo từng object; `JacksonJsonObjectReader<T>` bind mỗi object thành Java type.
- `JsonItemReader` phù hợp với root array; wrapper object và NDJSON cần cách đọc khác hoặc custom reader.
- Streaming ở cấp item không chia nhỏ nested array bên trong một object.
- `JsonItemReaderBuilder` cần tên reader ổn định, resource, object reader và `saveState(true)` khi cần restart.
- Chunk size ảnh hưởng số object cùng tồn tại, transaction duration và throughput.
- Jackson `JsonParser` là streaming API cấp thấp; `readTree` hoặc deserialize thành collection có thể materialize toàn bộ cấu trúc.
- Custom reader cần implement lifecycle `open`, `read`, `update`, `close` và lưu checkpoint nhất quán.
- Input phải bất biến giữa lần chạy đầu và restart; giữ JobParameters, reader name và resource ổn định.
- `JsonFileItemWriter` cùng `JacksonJsonObjectMarshaller` có thể ghi item thành JSON array theo chunk.
- Streaming không tự bảo đảm memory thấp nếu processor/cache/writer giữ dữ liệu hoặc object đơn lẻ quá lớn.
- JSON syntax, object mapping, schema validation và business validation là các tầng khác nhau.
- Không skip mọi lỗi parser; lỗi cấu trúc toàn file thường cần làm step thất bại.
- Với partitioning, chia file ở ranh giới record hợp lệ hoặc dùng resource riêng; không chia byte tùy tiện trong JSON array.
- Theo dõi heap, allocation, GC, throughput, chunk duration và lỗi để xác nhận streaming thực sự có hiệu quả.

Streaming JSON array trong Spring Batch là sự kết hợp giữa parser đọc từng object, chunk processing và checkpoint. `JsonItemReader` giúp xử lý root array lớn mà không phải giữ cả danh sách trong heap. Để hệ thống ổn định, cần chọn đúng item boundary, giới hạn kích thước object, kiểm soát chunk/concurrency, giữ input bất biến khi restart và không để các thành phần phía sau tích lũy dữ liệu không giới hạn.
