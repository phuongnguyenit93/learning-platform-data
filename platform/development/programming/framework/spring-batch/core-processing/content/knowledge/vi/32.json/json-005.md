# Root array và item separator

Trong Spring Batch, `JsonItemReader<T>` đọc các item từ một tài liệu JSON có cấu trúc mảng ở cấp root. Mỗi phần tử của mảng là một JSON object được chuyển thành một object Java thông qua `JsonObjectReader`, chẳng hạn `JacksonJsonObjectReader`.

Điểm cần hiểu rõ là dấu phẩy giữa các phần tử không phải delimiter tùy chỉnh như trong CSV. Đó là dấu phân cách do cú pháp JSON quy định. JSON parser hiểu cấu trúc object, array, string và escape sequence nên dấu phẩy nằm bên trong string hoặc cấu trúc lồng nhau không làm tách nhầm item.

Vì vậy, `JsonItemReader` phù hợp với tài liệu dạng `[ { ... }, { ... } ]`. Nó không coi mỗi dòng là một item và cũng không tự đọc JSON Lines, nhiều JSON object nối tiếp hoặc một mảng nằm bên trong property của root object.

## 1. Root array là gì?

JSON có thể biểu diễn một object đơn lẻ, một array, một string, number, boolean hoặc null ở cấp root. `JsonItemReader` được thiết kế để đọc danh sách item từ một root array.

Ví dụ file `trades.json`:

```json
[
  {
    "tradeId": "T1001",
    "symbol": "ACME",
    "quantity": 10,
    "price": 125.50
  },
  {
    "tradeId": "T1002",
    "symbol": "NOVA",
    "quantity": 5,
    "price": 82.25
  },
  {
    "tradeId": "T1003",
    "symbol": "ACME",
    "quantity": 7,
    "price": 126.00
  }
]
```

Root của tài liệu là dấu ngoặc vuông `[` và `]`. Mỗi object bên trong mảng là một item. Reader trả về từng `Trade` khi Spring Batch gọi `read()`; khi đã đọc hết phần tử cuối cùng, lần gọi tiếp theo trả về `null`.

```text
trades.json
    |
    v
Root array [ ... ]
    |
    +--> object thứ nhất -> Trade T1001
    |
    +--> object thứ hai -> Trade T1002
    |
    +--> object thứ ba  -> Trade T1003
    |
    v
EOF -> read() trả về null
```

Mỗi object trong mảng cần có cấu trúc tương thích với kiểu Java mà `JsonObjectReader` được cấu hình để tạo. Nếu các object có field khác nhau, cần xác định rõ mapping, field optional và validation.

## 2. Item separator là dấu phẩy theo cú pháp JSON

Trong JSON array, các value ở cùng cấp được phân cách bằng dấu phẩy. Với `JsonItemReader`, dấu phẩy đó là một phần của cú pháp JSON và được parser xử lý.

```json
[
  { "tradeId": "T1001", "quantity": 10 },
  { "tradeId": "T1002", "quantity": 5 },
  { "tradeId": "T1003", "quantity": 7 }
]
```

Không có thuộc tính kiểu `delimiter(',')` để tùy chỉnh dấu phân cách item cho `JsonItemReader`. Muốn dùng một ký tự phân cách khác, dữ liệu đó không còn là JSON array chuẩn và cần một định dạng hoặc reader khác.

JSON cho phép khoảng trắng, tab và xuống dòng quanh các token. Vì thế các cách viết sau có cùng ý nghĩa:

```json
[{"tradeId":"T1"},{"tradeId":"T2"}]
```

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" }
]
```

Xuống dòng chỉ giúp con người đọc dễ hơn. Nó không phải item separator; dấu phẩy mới phân cách hai value trong array.

## 3. Dấu phẩy bên trong object không tách item

Một object JSON có thể có nhiều property, mỗi property được phân cách bằng dấu phẩy. Parser phân biệt dấu phẩy giữa property với dấu phẩy giữa các object nhờ cấu trúc ngoặc nhọn và ngoặc vuông.

```json
[
  {
    "tradeId": "T1001",
    "customer": {
      "id": "C01",
      "name": "An Nguyen"
    },
    "tags": ["priority", "online"],
    "quantity": 10
  },
  {
    "tradeId": "T1002",
    "customer": {
      "id": "C02",
      "name": "Binh Tran"
    },
    "tags": ["retail"],
    "quantity": 5
  }
]
```

Object thứ nhất có các dấu phẩy giữa `tradeId`, `customer`, `tags` và `quantity`; object lồng `customer` cũng có dấu phẩy riêng; array `tags` có dấu phẩy riêng. Không dấu phẩy nào trong các cấu trúc đó kết thúc item ở root array.

Reader dựa vào parser JSON để nhận diện cấu trúc, không dùng phép tách chuỗi theo dấu phẩy.

## 4. Dấu phẩy trong string không phải separator

Giá trị string có thể chứa dấu phẩy. JSON parser giữ dấu phẩy đó như một phần nội dung của string.

```json
[
  {
    "tradeId": "T1001",
    "customerName": "Nguyen, An",
    "note": "Bought shares, then transferred them"
  },
  {
    "tradeId": "T1002",
    "customerName": "Tran, Binh",
    "note": "Reviewed, approved"
  }
]
```

Không cần quote field theo quy tắc CSV. JSON string luôn được đặt trong dấu nháy kép và ký tự đặc biệt phải được escape theo JSON grammar. Parser biết dấu phẩy nằm trong string nhờ trạng thái đọc string.

Ví dụ một dấu nháy kép trong string phải được escape:

```json
{ "note": "Customer said: \"please review\"" }
```

Nếu tự viết code để tách item bằng `String.split(",")`, dữ liệu có string chứa dấu phẩy hoặc object/array lồng nhau sẽ bị chia sai. Hãy để JSON parser xử lý token và cấu trúc.

## 5. Không có trailing comma trong JSON chuẩn

JSON array cần dấu phẩy giữa hai phần tử, nhưng không đặt dấu phẩy sau phần tử cuối cùng.

Đúng:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" }
]
```

Sai:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" },
]
```

Trailing comma có thể được chấp nhận bởi một số parser ở chế độ mở rộng, nhưng không thuộc JSON chuẩn. Không dựa vào cấu hình permissive vì file có thể không đọc được ở môi trường khác hoặc parser khác.

Cũng sai nếu thiếu separator:

```json
[
  { "tradeId": "T1" }
  { "tradeId": "T2" }
]
```

Nếu hai object liền nhau mà không có dấu phẩy, tài liệu không hợp lệ. Reader sẽ báo lỗi parse thay vì tự đoán ranh giới item.

## 6. Root array rỗng

Một root array rỗng là JSON hợp lệ:

```json
[]
```

Trong trường hợp này, reader không trả về item nào và `read()` trả `null` ngay khi xác định hết mảng. Step có thể hoàn tất với read count bằng 0 nếu nghiệp vụ chấp nhận input rỗng.

Cần phân biệt root array rỗng với resource rỗng hoặc file chỉ có whitespace. `[]` là một document JSON hợp lệ có zero item; file không chứa document JSON có thể là input sai định dạng. Hãy định nghĩa rõ job có chấp nhận file rỗng hay không và kiểm tra bằng validation phù hợp.

## 7. Root phải là array, không phải object chứa array

Định dạng sau là một JSON object có property `trades` chứa array:

```json
{
  "batchId": "B20261115",
  "trades": [
    { "tradeId": "T1", "quantity": 10 },
    { "tradeId": "T2", "quantity": 5 }
  ]
}
```

Đây không phải root array. `JsonItemReader` tiêu chuẩn mong đợi array ở cấp root, nên không tự động đi vào property `trades` để phát từng object.

Nếu nguồn có envelope object như trên, có một số lựa chọn:

- Dùng custom `ItemReader` với Jackson streaming parser để mở root object, tìm property `trades` rồi đọc từng phần tử.
- Dùng bước tiền xử lý để chuyển envelope thành root array trong một resource bất biến.
- Nếu cấu trúc envelope nhỏ và giới hạn kích thước rõ ràng, đọc document bằng một thành phần riêng rồi tạo reader cho danh sách; tránh nạp toàn bộ dữ liệu lớn vào memory.

Không bỏ wrapper bằng thao tác cắt chuỗi đơn giản. Cần dùng parser để bảo toàn escaping, nested object, Unicode và cấu trúc hợp lệ.

## 8. Cấu hình JsonItemReader trong Spring Batch 5

`JsonItemReader<T>` dùng abstraction `JsonObjectReader<T>` để đọc từng object. Có thể dùng `JacksonJsonObjectReader` khi ứng dụng dùng Jackson.

```java
@Bean
@StepScope
JsonItemReader<Trade> tradeJsonReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new JsonItemReaderBuilder<Trade>()
        .name("tradeJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(new JacksonJsonObjectReader<>(Trade.class))
        .strict(true)
        .saveState(true)
        .build();
}
```

Những phần quan trọng:

- `name`: tên reader ổn định, dùng để lưu/khôi phục state.
- `resource`: file JSON có root array.
- `jsonObjectReader`: parser/mapping implementation để chuyển từng object thành `Trade`.
- `strict(true)`: yêu cầu resource tồn tại theo chính sách strict của reader.
- `saveState(true)`: lưu tiến độ đọc vào `ExecutionContext` để hỗ trợ restart.
- `@StepScope`: cho phép resolve input file theo JobParameters khi step bắt đầu.

Đảm bảo dependency Jackson tương thích với phiên bản Spring Batch và Spring Boot của ứng dụng. Nếu dự án dùng Gson, có thể dùng implementation `GsonJsonObjectReader` tương ứng thay cho Jackson.

## 9. Khai báo chunk step sử dụng JsonItemReader

Reader có thể được nối với processor và writer như các reader khác:

```java
@Bean
Step importTradesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Trade> tradeJsonReader,
        ItemProcessor<Trade, Trade> tradeProcessor,
        ItemWriter<Trade> tradeWriter) {

    return new StepBuilder("importTrades", jobRepository)
        .<Trade, Trade>chunk(100, transactionManager)
        .reader(tradeJsonReader)
        .processor(tradeProcessor)
        .writer(tradeWriter)
        .build();
}
```

Chunk size 100 nghĩa là step xử lý tối đa 100 item trong một chunk transaction theo cấu hình. Reader trả từng object; processor có thể validate/transform; writer ghi chunk đã xử lý.

Không cần đưa dấu phẩy vào processor hoặc writer để tách item. Separator đã được xử lý ở tầng JSON parser trước khi object được trả ra.

## 10. Cấu hình ánh xạ object

Jackson reader ánh xạ từng JSON object vào class hoặc record Java. Ví dụ:

```java
public record Trade(
        String tradeId,
        String symbol,
        int quantity,
        BigDecimal price) {
}
```

JSON object:

```json
{
  "tradeId": "T1001",
  "symbol": "ACME",
  "quantity": 10,
  "price": 125.50
}
```

Property JSON cần tương thích với mapping Java. Nếu tên field khác nhau, có thể dùng annotation Jackson như `@JsonProperty`; nếu định dạng ngày/số đặc thù, cấu hình serializer/deserializer hoặc module Jackson phù hợp.

Việc deserialize thành công không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ. Ví dụ `quantity` có thể là số âm hoặc `price` null; hãy kiểm tra các quy tắc này trong processor hoặc validator.

## 11. Kiểu dữ liệu và giá trị null

JSON phân biệt string, number, boolean, null, object và array. Không nên giả định mọi giá trị đều là chuỗi.

| JSON value | Kiểu Java thường dùng |
|---|---|
| `"T1001"` | `String` |
| `10` | `int`, `long` hoặc wrapper tương ứng |
| `125.50` | `BigDecimal` cho giá trị thập phân cần chính xác |
| `true` | `boolean` hoặc `Boolean` |
| `null` | `null` với reference type |
| `{ ... }` | Nested class/record |
| `[ ... ]` | `List<T>` hoặc collection phù hợp |

Với tiền tệ hoặc số thập phân cần chính xác, dùng `BigDecimal` thay vì `double`. Với field có thể thiếu hoặc null, dùng wrapper/nullable type và xác định rõ default trong processor.

JSON number không mang metadata về scale nghiệp vụ. Nếu `125.50` và `125.5` phải được phân biệt về định dạng đầu vào, cần lưu raw representation hoặc validation riêng; deserialize thành `BigDecimal` có thể chuẩn hóa cách biểu diễn số.

## 12. Nested arrays và nested objects

Một item root có thể chứa cấu trúc lồng nhau:

```json
[
  {
    "tradeId": "T1",
    "customer": {
      "customerId": "C1",
      "name": "An Nguyen"
    },
    "allocations": [
      { "account": "A1", "quantity": 4 },
      { "account": "A2", "quantity": 6 }
    ]
  }
]
```

Toàn bộ object bên trong root array vẫn là một item. Array `allocations` không tạo thêm item cho `JsonItemReader`; nó được ánh xạ thành collection bên trong object `Trade`.

Đây là khác biệt giữa root item separator và dấu phẩy ở các cấp lồng nhau. Chỉ các value trực tiếp trong root array mới là item riêng.

## 13. JSON Lines không giống root array

JSON Lines (NDJSON) thường lưu một JSON object trên mỗi dòng, không có dấu ngoặc vuông root array và không có dấu phẩy giữa các dòng:

```text
{"tradeId":"T1","quantity":10}
{"tradeId":"T2","quantity":5}
{"tradeId":"T3","quantity":7}
```

Đây không phải JSON document dạng root array. Newline là ranh giới record theo quy ước JSON Lines, còn trong JSON chuẩn newline chỉ là whitespace và không tự phân cách hai root value.

`JsonItemReader` được thiết kế cho root array; không dùng nó với file JSON Lines bằng cách kỳ vọng newline sẽ trở thành item separator.

Đối với JSON Lines, có thể dùng `FlatFileItemReader` để đọc từng dòng rồi dùng Jackson `ObjectMapper` parse từng dòng:

```java
@Bean
@StepScope
FlatFileItemReader<Trade> tradeJsonLinesReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        ObjectMapper objectMapper) {

    return new FlatFileItemReaderBuilder<Trade>()
        .name("tradeJsonLinesReader")
        .resource(new FileSystemResource(inputFile))
        .lineMapper((line, lineNumber) ->
            objectMapper.readValue(line, Trade.class))
        .strict(true)
        .saveState(true)
        .build();
}
```

Ví dụ này giả định mỗi dòng chứa đúng một JSON object hoàn chỉnh. Nếu line rỗng, comment hoặc record nhiều dòng xuất hiện, hãy xác định chính sách xử lý riêng. Với JSON Lines, không thêm dấu phẩy giữa các dòng.

## 14. Nhiều JSON object nối tiếp không có root array

File như sau không phải một JSON document chuẩn:

```text
{"tradeId":"T1"}
{"tradeId":"T2"}
```

Đây có thể là NDJSON nếu mỗi dòng độc lập, nhưng không phải JSON array. Nếu các object chỉ nối tiếp nhau mà không có quy ước record rõ ràng, reader không thể dựa vào JSON grammar để biết ranh giới item.

Không tự thêm hoặc xóa ký tự `[` `]` và dấu phẩy bằng string manipulation nếu nội dung có thể chứa nested structures hoặc escaped characters. Hãy dùng parser hoặc chuyển đổi nguồn theo quy trình có kiểm soát.

## 15. Một root object đơn lẻ

JSON sau là một root object:

```json
{
  "tradeId": "T1001",
  "symbol": "ACME",
  "quantity": 10
}
```

Nếu job chỉ cần đọc đúng một object, có thể dùng một tasklet hoặc custom reader đọc một document và trả về object một lần. Nếu muốn dùng `JsonItemReader`, hãy biểu diễn input thành root array chứa một object:

```json
[
  {
    "tradeId": "T1001",
    "symbol": "ACME",
    "quantity": 10
  }
]
```

Cách biểu diễn root array giữ cùng một reader contract cho cả file có một item và file có nhiều item.

## 16. Strict resource handling và file rỗng

Resource không tồn tại, file có zero bytes và file chứa `[]` là ba trường hợp khác nhau.

| Input | Ý nghĩa | Hành vi cần xác định |
|---|---|---|
| File không tồn tại | Sai đường dẫn hoặc file chưa đến | Thường fail nếu input bắt buộc |
| File zero bytes | Không có JSON document | Thường là input malformed hoặc thiếu dữ liệu |
| File chỉ có whitespace | Không có JSON value | Cần coi là input không hợp lệ nếu schema yêu cầu root array |
| `[]` | JSON root array hợp lệ nhưng không có item | Reader kết thúc với zero item |

Không dùng `strict(false)` để biến một file bắt buộc bị thiếu thành job thành công với zero item. Hãy xác thực resource và chính sách input rỗng trước khi xử lý.

## 17. Lỗi cú pháp và lỗi mapping

Có thể phân biệt hai nhóm lỗi:

- **Lỗi cấu trúc JSON:** thiếu dấu phẩy, thiếu dấu ngoặc, trailing comma, string không đóng hoặc token không hợp lệ.
- **Lỗi mapping/kiểu dữ liệu:** JSON hợp lệ nhưng field không chuyển được sang kiểu Java hoặc không khớp class.

Ví dụ lỗi cấu trúc:

```json
[
  { "tradeId": "T1" },
  { "tradeId": "T2" },
]
```

Ví dụ JSON hợp lệ nhưng có thể không map được nếu `quantity` là số nguyên trong class:

```json
[
  { "tradeId": "T1", "quantity": "many" }
]
```

Không nên skip mọi parse exception một cách rộng rãi. Một lỗi ở giữa array có thể làm parser không thể xác định vị trí tiếp tục; lỗi cấu trúc toàn document thường cần fail file. Lỗi mapping thuộc riêng một object có thể được xử lý khác nếu parser có thể tiếp tục an toàn và nghiệp vụ cho phép.

## 18. Checkpoint và restart của JsonItemReader

`JsonItemReader` hỗ trợ `ItemStream` và lưu tiến độ đọc vào `ExecutionContext` khi `saveState` được bật. Khi chunk commit, reader state được cập nhật để restart tiếp tục từ item tiếp theo sau checkpoint.

```java
return new JsonItemReaderBuilder<Trade>()
    .name("tradeJsonReader")
    .resource(new FileSystemResource(inputFile))
    .jsonObjectReader(new JacksonJsonObjectReader<>(Trade.class))
    .saveState(true)
    .build();
```

Để restart chính xác:

- Giữ tên reader ổn định giữa lần chạy và restart.
- Giữ cùng identifying `JobParameters` để restart cùng JobInstance.
- Giữ nguyên nội dung và thứ tự các object trong file.
- Dùng JobRepository bền vững để lưu ExecutionContext.
- Bảo đảm writer và side effect an toàn khi item chưa commit được đọc lại.

Checkpoint của reader là tiến độ item, không phải byte offset tùy ý trong file. Reader có thể cần mở lại resource và đi qua các item đã checkpoint để khôi phục vị trí. Với file lớn, thời gian restart có thể phụ thuộc số item cần bỏ qua.

## 19. Không thay file JSON giữa lần chạy và restart

Giả sử lần chạy đầu đọc 1.000 item và checkpoint đã commit 600 item. Nếu file bị thay bằng một file mới có thứ tự object khác, reader có thể bỏ qua 600 object đầu của file mới rồi tiếp tục từ object không liên quan đến lần chạy ban đầu.

Các biện pháp:

- Đưa file vào vùng lưu trữ bất biến theo batch ID hoặc source ID.
- Lưu checksum hoặc version file trước khi launch.
- Đưa source ID/version/checksum vào identifying JobParameters nếu chúng xác định dữ liệu nghiệp vụ.
- Không ghi đè resource khi JobInstance còn có thể restart.
- Giữ manifest ổn định nếu job đọc nhiều file.

Không chỉ dựa vào tên file nếu nhà cung cấp có thể tái sử dụng cùng tên cho nội dung khác.

## 20. Nhiều file JSON

Nếu có nhiều file JSON root array, có thể dùng `MultiResourceItemReader` với `JsonItemReader` làm delegate. Danh sách resource cần có thứ tự ổn định để restart khôi phục đúng file và item.

```java
@Bean
@StepScope
MultiResourceItemReader<Trade> allTradeFilesReader(
        @Value("#{jobParameters['input.directory']}") String directory,
        JsonItemReader<Trade> tradeJsonReader) throws IOException {

    Resource[] resources = new PathMatchingResourcePatternResolver()
        .getResources("file:" + directory + "/*.json");
    Arrays.sort(resources, Comparator.comparing(Resource::getFilename));

    return new MultiResourceItemReaderBuilder<Trade>()
        .name("allTradeFilesReader")
        .resources(resources)
        .delegate(tradeJsonReader)
        .saveState(true)
        .build();
}
```

Đây là cấu hình khái quát; cần bảo đảm delegate reader có scope và lifecycle phù hợp với wrapper trong phiên bản đang dùng. Danh sách file phải bất biến hoặc được snapshot trong manifest. Thêm một file đứng trước các file cũ có thể làm thay đổi index resource được lưu trong checkpoint.

## 21. JSON root array và item separator trong XML namespace

JSON không có namespace theo cách XML sử dụng namespace URI/prefix. Tên property như `tradeId` được ánh xạ theo quy tắc của JSON mapper. Nếu API nguồn dùng các property có tên khác nhau, có thể dùng annotation hoặc cấu hình mapper thay vì cố xử lý bằng delimiter.

Ví dụ:

```java
public record Trade(
        @JsonProperty("trade_id") String tradeId,
        @JsonProperty("qty") int quantity) {
}
```

JSON:

```json
[
  { "trade_id": "T1", "qty": 10 },
  { "trade_id": "T2", "qty": 5 }
]
```

Separator giữa hai object vẫn là dấu phẩy của root array; `@JsonProperty` chỉ điều khiển ánh xạ tên property.

## 22. Giữ item separator đúng khi tạo file đầu vào

Nếu một hệ thống upstream tạo JSON file cho Spring Batch, file cần được serialize bằng JSON generator hoặc thư viện JSON thay vì nối object string thủ công.

Không nên tạo file bằng:

```java
writer.write("[" + object1 + "," + object2 + "]");
```

Cách nối chuỗi dễ tạo JSON không hợp lệ khi object có quote, newline, ký tự Unicode hoặc dấu phẩy. Nên dùng `ObjectMapper` hoặc JSON generator:

```java
ObjectMapper objectMapper = new ObjectMapper();
objectMapper.writeValue(outputFile, trades);
```

Thư viện JSON tự xử lý escaping và dấu phẩy giữa array elements. Với output rất lớn, cân nhắc streaming generator để không cần giữ toàn bộ collection trong memory.

## 23. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng root object thay vì root array | `JsonItemReader` không đọc theo item contract mong đợi | Bọc item trong root array hoặc dùng custom reader cho envelope |
| Mong newline phân cách item | Nhiều object không tạo thành JSON array hợp lệ | Dùng root array hoặc reader riêng cho JSON Lines |
| Tự `split(',')` để tách object | Dấu phẩy trong string/nested object làm hỏng record | Dùng JSON parser |
| Thiếu dấu phẩy giữa hai item | JSON malformed | Serialize bằng JSON library |
| Có trailing comma sau item cuối | Không phải JSON chuẩn | Bỏ separator cuối |
| Dùng `JsonItemReader` cho NDJSON | Reader mong đợi root array | Dùng `FlatFileItemReader` với JSON mapper cho từng dòng |
| Nhầm nested array là item riêng | Collection con bị tách sai logic | Map toàn bộ root object thành một item |
| File rỗng bị coi là `[]` | Che giấu nguồn không hợp lệ | Phân biệt file zero-byte và root array rỗng |
| Thay file trước khi restart | Checkpoint item count trỏ sang dữ liệu khác | Giữ input immutable và lưu source version |
| Skip lỗi JSON cấu trúc toàn file | Parser không thể tiếp tục đúng vị trí | Fail input và xử lý nguồn/schema |

## 24. Kiểm thử root array và item separator

Integration test nên xác nhận parser xử lý đúng cấu trúc array và mỗi item được trả đúng một lần.

Các trường hợp cần kiểm tra:

1. Root array có một object: reader trả một item rồi EOF.
2. Root array có nhiều object: mỗi object trở thành một item theo đúng thứ tự.
3. Root array rỗng `[]`: reader trả EOF và read count bằng zero.
4. Whitespace và xuống dòng giữa item: kết quả không thay đổi.
5. String chứa dấu phẩy: giá trị string không bị tách.
6. Nested object và array có dấu phẩy: toàn bộ root object vẫn là một item.
7. Dấu phẩy thiếu hoặc trailing comma: parser báo lỗi JSON.
8. Root object chứa property array: xác nhận reader tiêu chuẩn không tự chọn nested array.
9. JSON Lines: xác nhận dùng reader phù hợp, không dùng `JsonItemReader` root-array.
10. Field thiếu/null/sai kiểu: mapping và validation phản ánh đúng policy.
11. Restart sau một chunk commit: reader tiếp tục từ item sau checkpoint.
12. File thay đổi giữa hai lần chạy: kiểm tra source version/checksum bảo vệ restart.

Test nên kiểm tra cả số item, thứ tự item, nội dung object, `ExecutionContext`, trạng thái step và dữ liệu writer. Chỉ kiểm tra job hoàn thành chưa đủ để chứng minh item separator được xử lý đúng.

## 25. Quy trình xác định định dạng JSON trước khi cấu hình reader

Trước khi chọn reader, hãy kiểm tra:

1. Root JSON là array hay object?
2. Mỗi item là object trực tiếp trong root array hay nằm trong property con?
3. Separator giữa item có phải dấu phẩy JSON chuẩn không?
4. Nguồn có thực sự là JSON Lines hay nhiều document nối tiếp?
5. Có nested object/array hoặc string chứa dấu phẩy không?
6. Các object có cùng schema và kiểu dữ liệu không?
7. File có thể rỗng hay root array rỗng có được phép?
8. Job có cần restart và input có bất biến không?
9. File có nhiều resource và cần manifest/thứ tự ổn định không?
10. Có cần skip record lỗi hay lỗi cấu trúc phải làm fail toàn file?

Chọn reader dựa trên định dạng thực tế của nguồn. Không ép JSON Lines thành root array chỉ bằng cách thêm dấu ngoặc nếu không kiểm soát được escaping và tính toàn vẹn document.

## Kết luận

`JsonItemReader<T>` của Spring Batch đọc item từ một JSON root array. Mỗi object trực tiếp trong array là một item; dấu phẩy giữa các object là item separator theo JSON grammar và được parser xử lý. Dấu phẩy trong string, nested object hoặc nested array không tách item. JSON chuẩn không cho phép trailing comma và whitespace/newline không thay thế dấu phẩy giữa các array elements.

Hãy dùng `JsonObjectReader` phù hợp như `JacksonJsonObjectReader`, khai báo resource và reader name ổn định, bật `saveState` khi cần restart và giữ nguyên input cùng identifying JobParameters. Nếu nguồn là JSON Lines, root object có envelope hoặc nhiều document nối tiếp, chọn `FlatFileItemReader`/custom reader phù hợp thay vì giả định `JsonItemReader` có thể tự tìm item separator theo dòng.
