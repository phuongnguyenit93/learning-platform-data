# JsonItemReader

Trong Spring Batch, `JsonItemReader<T>` là một `ItemReader` dùng để đọc dữ liệu JSON theo từng item. Reader xử lý một JSON array chứa các object, chuyển từng object thành Java object thông qua `JsonObjectReader<T>`, rồi trả từng item cho chunk-oriented Step.

Ví dụ, một file `orders.json` có thể chứa hàng trăm nghìn đơn hàng trong một mảng JSON. `JsonItemReader<Order>` đọc từng object `Order` để processor kiểm tra và writer lưu vào database. Cách đọc theo item giúp xử lý file lớn theo chunk, thay vì ứng dụng phải tự nạp và xử lý toàn bộ danh sách trong một lần.

`JsonItemReader` tách phần điều khiển đọc item khỏi thư viện JSON cụ thể. Có thể dùng `JacksonJsonObjectReader` hoặc `GsonJsonObjectReader`, hoặc triển khai `JsonObjectReader` riêng nếu ứng dụng cần một thư viện hay quy tắc parse khác.

## 1. Cấu trúc JSON mà JsonItemReader đọc

`JsonItemReader` được thiết kế cho tài liệu có một JSON array ở cấp cao nhất, trong đó mỗi phần tử là một JSON object đại diện cho một item.

Ví dụ file `orders.json`:

```json
[
  {
    "orderId": 1001,
    "customerName": "Lan",
    "amount": 125.50
  },
  {
    "orderId": 1002,
    "customerName": "Minh",
    "amount": 89.00
  },
  {
    "orderId": 1003,
    "customerName": "An",
    "amount": 240.75
  }
]
```

Mỗi object bên trong array là một item. Các lần gọi `read()` lần lượt trả về `Order` cho ID 1001, 1002 và 1003. Khi đã đọc hết array, reader trả `null` để báo hết dữ liệu.

Sơ đồ luồng:

```text
orders.json
    |
    v
JsonItemReader<Order>
    |
    v
JsonObjectReader<Order>
    |
    +--> JSON object thứ nhất --> Order 1001
    |
    +--> JSON object thứ hai  --> Order 1002
    |
    +--> JSON object thứ ba   --> Order 1003
    |
    +--> Hết array             --> null
```

Một JSON object đơn ở cấp cao nhất, ví dụ `{ "orders": [...] }`, hoặc JSON Lines/NDJSON (mỗi dòng là một object độc lập) không có cùng cấu trúc array mà reader này mong đợi. Với những định dạng đó, cần chuẩn hóa nguồn thành array, viết reader tùy chỉnh hoặc dùng reader phù hợp với định dạng dòng.

## 2. JsonObjectReader làm nhiệm vụ gì?

`JsonItemReader` quản lý việc đọc các item trong JSON array. Việc chuyển một JSON object thành Java object được giao cho `JsonObjectReader<T>`.

Các implementation thường dùng:

| Implementation | Thư viện | Khi nào dùng? |
|---|---|---|
| `JacksonJsonObjectReader<T>` | Jackson | Ứng dụng đã dùng Jackson hoặc cần tùy chỉnh `ObjectMapper` |
| `GsonJsonObjectReader<T>` | Gson | Ứng dụng dùng Gson để ánh xạ JSON |
| Custom `JsonObjectReader<T>` | Thư viện hoặc parser riêng | Cần quy tắc parse đặc biệt hoặc tích hợp thư viện khác |

`JsonObjectReader` chịu trách nhiệm mở nguồn JSON, đọc object tiếp theo và đóng tài nguyên khi reader kết thúc. `JsonItemReader` gọi các thao tác đó trong lifecycle của `ItemStreamReader`.

Việc tách hai thành phần giúp cùng một cấu hình batch có thể đổi thư viện JSON mà không phải viết lại chunk Step. Tuy nhiên, cách chuyển kiểu, xử lý field lạ, ngày giờ và null vẫn phụ thuộc implementation được chọn.

## 3. Cấu hình JsonItemReader cơ bản với Jackson

Ví dụ dùng `JacksonJsonObjectReader`:

```java
@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new ClassPathResource("data/orders.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

Các cấu hình chính:

- `name("orderJsonReader")`: tên reader ổn định, được dùng khi lưu state trong `ExecutionContext`.
- `resource(...)`: nguồn JSON cần đọc, ở đây là file trong classpath.
- `jsonObjectReader(...)`: thành phần chuyển mỗi JSON object thành `Order`.
- `strict(true)`: yêu cầu resource tồn tại khi mở reader theo hành vi strict của reader.
- `saveState(true)`: bật lưu checkpoint để hỗ trợ restart.

Builder và các class JSON reader thuộc Spring Batch infrastructure. Cần có dependency Spring Batch phù hợp và thư viện JSON mà implementation sử dụng, chẳng hạn Jackson hoặc Gson. API có thể khác giữa các phiên bản Spring Batch; hãy dùng builder và constructor tương ứng với dependency của dự án.

## 4. Model Java nhận dữ liệu JSON

Jackson hoặc Gson cần biết cách ánh xạ JSON object vào kiểu Java đích. Với một JavaBean đơn giản, model có thể như sau:

```java
public class Order {

    private Long orderId;
    private String customerName;
    private BigDecimal amount;

    public Order() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

JSON field `orderId` được ánh xạ vào property `orderId`, `customerName` vào `customerName`, và `amount` vào `BigDecimal amount` theo quy tắc của JSON library.

Với dữ liệu tiền tệ, `BigDecimal` thường phù hợp hơn `double` vì giữ độ chính xác thập phân. Không nên dùng floating-point nếu các phép tính cần chính xác số tiền.

## 5. Tích hợp JsonItemReader vào chunk Step

Sau khi cấu hình reader, đăng ký nó vào Step như một `ItemReader` bình thường:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Order> orderJsonReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderJsonReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Với `chunk(100, transactionManager)`, Step xử lý tối đa 100 item trong một chunk theo transaction. Reader tiếp tục đọc object tiếp theo trong JSON array qua các chunk cho đến EOF.

Chunk size không phải số object mà parser nạp từ toàn bộ file. `JsonItemReader` đọc tuần tự từng object, còn Spring Batch giữ các item của chunk đang xử lý cho đến khi transaction hoàn tất. Chọn chunk size dựa trên kích thước object, thời gian transaction, heap và hiệu năng writer.

## 6. Đọc file JSON từ JobParameters

Trong môi trường batch thực tế, file đầu vào thường thay đổi theo từng lần chạy. Có thể dùng `@StepScope` để inject đường dẫn từ JobParameters:

```java
@Bean
@StepScope
public JsonItemReader<Order> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` cho phép đọc JobParameters khi StepExecution hiện tại đã tồn tại. Mỗi lần chạy có thể dùng file khác nhau mà không phải giữ đường dẫn thay đổi trong một singleton reader.

Nếu `inputFile` là bắt buộc, hãy validate trước khi mở reader. Nếu có default, cân nhắc materialize giá trị đó vào JobParameters khi khởi chạy để restart luôn dùng đúng file ban đầu. Không nên để một default động thay đổi theo ngày hoặc deployment trong khi JobInstance cũ còn cần restart.

## 7. Đọc resource từ classpath hoặc filesystem

`JsonItemReader` nhận `Resource`, vì vậy có thể đọc JSON đóng gói cùng ứng dụng hoặc file bên ngoài.

Classpath resource:

```java
.resource(new ClassPathResource("data/orders.json"))
```

Filesystem resource:

```java
.resource(new FileSystemResource("/var/batch/inbound/orders.json"))
```

Classpath phù hợp với fixture, dữ liệu mẫu hoặc file mặc định bất biến được đóng gói trong artifact. Filesystem phù hợp với file được upstream chuyển đến theo lịch hoặc thay đổi theo từng JobExecution.

Không giả định mọi classpath resource đều có thể chuyển thành `File`; khi resource nằm bên trong executable JAR, nó có thể chỉ đọc được qua stream. `Resource` abstraction giúp reader xử lý nguồn mà không cần code ứng dụng tự gọi `getFile()`.

Với filesystem path lấy từ JobParameters, cần kiểm tra path được phép đọc, quyền truy cập và tính ổn định của file. Không nên cho phép một tham số tùy ý trỏ đến mọi vị trí trên máy chủ nếu Job chỉ cần một thư mục inbound.

## 8. Tùy chỉnh Jackson ObjectMapper

`JacksonJsonObjectReader` sử dụng Jackson để ánh xạ object JSON. Khi dữ liệu có kiểu ngày giờ, naming convention khác hoặc quy tắc field đặc biệt, có thể cấu hình `ObjectMapper` rồi truyền cho reader.

Ví dụ đăng ký module Java Time:

```java
@Bean
public JsonObjectReader<Trade> tradeJsonObjectReader() {
    ObjectMapper objectMapper = new ObjectMapper();
    objectMapper.registerModule(new JavaTimeModule());

    return new JacksonJsonObjectReader<>(objectMapper, Trade.class);
}
```

Model có thể chứa `LocalDate`:

```java
public class Trade {

    private String symbol;
    private LocalDate tradeDate;
    private BigDecimal price;

    public Trade() {
    }

    // getters và setters
}
```

JSON:

```json
{
  "symbol": "ACME",
  "tradeDate": "2026-11-15",
  "price": 125.75
}
```

`JavaTimeModule` giúp Jackson xử lý các kiểu ngày giờ Java khi format dữ liệu tương ứng. Nếu nguồn dùng format khác ISO, cấu hình formatter/annotation phù hợp và kiểm thử dữ liệu thực tế.

Constructor nhận `ObjectMapper` và thứ tự tham số cần đối chiếu với phiên bản Spring Batch đang dùng. Nếu API phiên bản khác, hãy cấu hình `JacksonJsonObjectReader` theo constructor hoặc factory method được cung cấp bởi dependency đó.

## 9. Dùng GsonJsonObjectReader

Nếu ứng dụng dùng Gson, có thể thay Jackson reader bằng `GsonJsonObjectReader`:

```java
@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new ClassPathResource("data/orders.json"))
            .jsonObjectReader(new GsonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

Phần cấu hình `JsonItemReader` vẫn giữ nguyên: resource, tên reader và state. Thay đổi nằm ở implementation dùng để chuyển JSON object thành `Order`.

Chọn một JSON library phù hợp với hệ thống hiện tại. Không nên đưa cả Jackson và Gson vào chỉ để dùng hai cách mapping cho cùng một file nếu không có nhu cầu rõ ràng. Cần kiểm tra cách library xử lý null, field không biết, enum, ngày giờ, số lớn và constructor của model.

## 10. Field name khác với Java property

JSON có thể dùng snake_case trong khi Java model dùng camelCase:

```json
{
  "order_id": 1001,
  "customer_name": "Lan",
  "total_amount": 125.50
}
```

Model:

```java
public class Order {
    private Long orderId;
    private String customerName;
    private BigDecimal totalAmount;

    // getters và setters
}
```

Với Jackson, có thể dùng `@JsonProperty`:

```java
public class Order {

    @JsonProperty("order_id")
    private Long orderId;

    @JsonProperty("customer_name")
    private String customerName;

    @JsonProperty("total_amount")
    private BigDecimal totalAmount;
}
```

Hoặc cấu hình naming strategy cho `ObjectMapper` nếu toàn bộ file tuân theo cùng một quy ước. Dùng annotation khi mapping cần rõ ràng theo từng field; dùng naming strategy khi quy tắc thống nhất và được áp dụng có chủ đích.

## 11. Nested object và array trong mỗi item

Một phần tử của JSON array có thể chứa object hoặc array lồng nhau. `JsonItemReader` vẫn coi toàn bộ object ngoài cùng là một item; JSON library ánh xạ các phần con vào model.

Ví dụ:

```json
[
  {
    "orderId": 1001,
    "customer": {
      "customerId": 501,
      "name": "Lan"
    },
    "lines": [
      { "sku": "A-10", "quantity": 2 },
      { "sku": "B-20", "quantity": 1 }
    ]
  }
]
```

Model có thể biểu diễn cấu trúc lồng nhau:

```java
public class Order {
    private Long orderId;
    private Customer customer;
    private List<OrderLine> lines;

    // getters và setters
}

public class Customer {
    private Long customerId;
    private String name;

    // getters và setters
}

public class OrderLine {
    private String sku;
    private int quantity;

    // getters và setters
}
```

Một lần `read()` trả về một `Order` hoàn chỉnh cùng `Customer` và danh sách `OrderLine`. Reader không trả từng line thành một item riêng trừ khi thiết kế nguồn hoặc custom reader yêu cầu điều đó.

## 12. JSON null, field thiếu và field không biết

JSON có thể có field bị thiếu, field có giá trị `null`, hoặc field mới mà model chưa biết.

```json
[
  { "orderId": 1001, "amount": 125.50 },
  { "orderId": 1002, "customerName": null, "amount": 89.00 },
  { "orderId": 1003, "customerName": "An", "amount": 240.75, "newField": "extra" }
]
```

Các trường hợp cần quyết định:

- Field bị thiếu: giữ giá trị mặc định của Java property hoặc áp dụng quy tắc mapping đã cấu hình.
- Field có `null`: property có thể nhận `null` nếu kiểu cho phép; primitive như `int` không thể chứa null.
- Field không biết: hành vi phụ thuộc cấu hình JSON library; Jackson mặc định thường từ chối unknown property trong nhiều cấu hình, còn Gson có hành vi khác.
- Field bắt buộc: nên validate rõ sau khi mapping hoặc dùng cơ chế validation phù hợp.

Không nên để một giá trị mặc định trong model vô tình che giấu việc upstream bỏ mất field bắt buộc. Hãy xác định contract JSON và kiểm tra dữ liệu sau khi parse.

## 13. Kiểu số và độ chính xác

JSON biểu diễn số dưới dạng number, nhưng model Java có thể chọn `Integer`, `Long`, `BigDecimal` hoặc kiểu khác. Với ID lớn, cần dùng kiểu đủ rộng. Với tiền tệ hoặc số thập phân cần chính xác, ưu tiên `BigDecimal`.

Ví dụ:

```json
{
  "orderId": 922337203685,
  "quantity": 3,
  "unitPrice": 19.99
}
```

Model:

```java
public class OrderLine {
    private Long orderId;
    private Integer quantity;
    private BigDecimal unitPrice;
}
```

Không nên parse tiền tệ thành `double` rồi chuyển sang `BigDecimal` sau đó vì sai số nhị phân có thể đã xuất hiện. Cấu hình và test JSON library để xác nhận số thập phân được ánh xạ đúng kiểu đích.

## 14. Checkpoint và restart

`JsonItemReader` là một reader có state và hỗ trợ lưu tiến độ đọc vào Step `ExecutionContext`. Bật `saveState(true)` và đặt tên reader ổn định:

```java
return new JsonItemReaderBuilder<Order>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
        .saveState(true)
        .build();
```

Khi Job restart cùng JobInstance:

1. Spring Batch tạo StepExecution mới cho lần chạy lại.
2. Reader mở lại resource và khởi tạo parser JSON mới.
3. Reader đọc item count đã lưu trong ExecutionContext.
4. Reader khôi phục vị trí logic đến item tiếp theo cần xử lý.
5. Step tiếp tục đọc các object còn lại.

Reader không giữ parser hoặc stream cũ qua process restart. Nó mở lại file và tái tạo vị trí đọc dựa trên checkpoint. Với reader dựa trên item count, việc khôi phục có thể cần đọc qua các item trước đó để đến vị trí đã lưu; restart một file rất lớn có thể tốn thời gian hơn so với đọc tiếp một cursor còn mở.

Để restart đúng:

- Giữ nguyên identifying JobParameters để tiếp tục cùng JobInstance.
- Dùng cùng file đầu vào và cùng nội dung JSON.
- Giữ tên reader ổn định.
- Bật `saveState` nếu cần checkpoint.
- Không thay đổi thứ tự hoặc chèn/xóa object trước vị trí checkpoint.
- Lưu checksum, version hoặc manifest nếu cần xác nhận file vẫn là bản ban đầu.

Checkpoint theo số item chỉ an toàn khi nguồn dữ liệu không thay đổi theo cách làm dịch chuyển thứ tự item.

## 15. Resource thay đổi giữa lần chạy và restart

Giả sử file JSON có 10.000 object và Step đã commit 5.000 item trước khi thất bại. Nếu upstream ghi đè file trước khi restart, item count 5.000 có thể trỏ đến một object khác so với lần chạy đầu.

Để tránh đọc sai dữ liệu:

- Copy file đến thư mục staging bất biến trước khi khởi chạy Job.
- Dùng tên file hoặc batch ID duy nhất cho từng lần nhập.
- Lưu checksum hoặc metadata phiên bản của file.
- Archive file sau khi Job hoàn tất.
- Không tái sử dụng cùng identifying JobParameters cho nội dung file khác.
- Khi nội dung file thay đổi, quyết định đó là JobInstance mới hay một lần restart của công việc cũ.

Nếu file là classpath resource được đóng gói trong JAR, artifact version cũng là một phần của tính ổn định. Deploy artifact mới có thể làm nội dung classpath resource thay đổi trong khi Job cũ còn cần restart.

## 16. Strict mode và kiểm tra resource

`strict(true)` yêu cầu reader kiểm tra resource có tồn tại khi mở. Nó giúp phát hiện sớm file bị thiếu hoặc đường dẫn sai.

Strict mode không xác thực toàn bộ JSON. Một resource tồn tại vẫn có thể chứa JSON malformed, sai cấu trúc root hoặc object không ánh xạ được vào target class.

Nên phân biệt:

| Kiểm tra | Mục tiêu |
|---|---|
| Resource strictness | File có tồn tại và mở được hay không |
| JSON syntax | Nội dung có phải JSON hợp lệ hay không |
| Root structure | Tài liệu có phải array object đúng cấu trúc reader mong đợi hay không |
| Object mapping | Field có chuyển được sang kiểu Java hay không |
| Business validation | Object có hợp lệ theo quy tắc nghiệp vụ hay không |

Các bước này có thể thất bại vì nguyên nhân khác nhau và cần thông báo lỗi phù hợp.

## 17. Xử lý lỗi parse và mapping

Một số lỗi thường gặp:

| Giai đoạn | Ví dụ | Cách xử lý |
|---|---|---|
| Mở resource | File không tồn tại, không có quyền đọc | Kiểm tra path và quyền; fail sớm nếu file bắt buộc |
| Parse JSON | Thiếu dấu phẩy, dấu ngoặc không khớp, token sai | Sửa file nguồn; thường nên fail vì parser có thể không phục hồi an toàn |
| Cấu trúc root | Root là object thay vì array | Chuẩn hóa input hoặc dùng reader khác |
| Mapping | Chuỗi không chuyển được thành số/ngày | Kiểm tra field và conversion configuration |
| Schema drift | Field bắt buộc bị thiếu hoặc field mới xuất hiện | Cập nhật contract/mapping và validation |
| Business validation | Số lượng âm, mã nghiệp vụ không tồn tại | Xử lý trong processor/validator |

Không nên skip mọi exception JSON một cách rộng rãi. Khi syntax của tài liệu bị lỗi, parser streaming có thể không xác định được ranh giới object tiếp theo để tiếp tục an toàn. Một lỗi mapping ở một object có thể có khả năng xử lý khác tùy JSON library; hãy kiểm tra exception thực tế và khả năng parser tiếp tục trước khi áp dụng skip.

Một thiết kế thường dễ kiểm soát là để JSON parser ánh xạ object đúng cấu trúc, sau đó dùng `ItemProcessor` kiểm tra quy tắc nghiệp vụ và ném exception riêng như `InvalidOrderException` nếu item được phép skip.

## 18. Kết hợp retry và skip

`JsonItemReader` có thể tham gia fault-tolerant Step như các reader khác. Tuy nhiên, retry và skip cần áp dụng theo nguyên nhân:

- Lỗi I/O tạm thời khi truy cập nguồn có thể retry nếu reader có thể mở lại nguồn an toàn.
- Một object JSON parse/mapping lỗi chỉ nên skip khi parser vẫn có thể tiếp tục và nghiệp vụ cho phép bỏ item.
- JSON syntax lỗi ở giữa tài liệu thường nên làm Step thất bại.
- Lỗi validation nghiệp vụ có thể được skip theo chính sách nếu item không ảnh hưởng tính toàn vẹn của toàn batch.

Ví dụ skip lỗi nghiệp vụ ở processor:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JsonItemReader<Order> orderJsonReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderJsonReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(20)
            .build();
}
```

Đây là ví dụ cho exception nghiệp vụ do processor ném ra, không phải khuyến nghị skip mọi exception do Jackson/Gson phát sinh.

## 19. Streaming và bộ nhớ

`JsonItemReader` đọc từng object trong array, phù hợp với file lớn hơn cách deserialize toàn bộ JSON array thành `List<Order>` trước khi xử lý. Tuy vậy, bộ nhớ vẫn phụ thuộc:

- Kích thước mỗi JSON object.
- Số lượng object được giữ trong chunk.
- Độ sâu và số lượng nested object/array.
- Buffer nội bộ của parser.
- State/caching trong processor và writer.
- Số Step hoặc Job chạy đồng thời.

Để kiểm soát bộ nhớ:

- Giữ chunk size phù hợp với kích thước object.
- Không tích lũy toàn bộ item vào một collection trong processor/writer.
- Chỉ map các field cần thiết nếu model có thể được thiết kế gọn hơn.
- Đo heap và GC bằng file có kích thước gần production.
- Tránh một JSON object duy nhất chứa một mảng con khổng lồ nếu mỗi phần tử con mới là đơn vị cần xử lý.

Nếu cấu trúc nguồn là một object lớn chứa array `items`, built-in `JsonItemReader` không tự động biến array lồng đó thành root array của item. Có thể chuẩn hóa file hoặc viết custom reader để duyệt mảng con theo streaming.

## 20. JsonItemReader và JSON Lines/NDJSON

JSON array:

```json
[
  {"orderId": 1001, "amount": 10.5},
  {"orderId": 1002, "amount": 20.0}
]
```

JSON Lines/NDJSON:

```text
{"orderId": 1001, "amount": 10.5}
{"orderId": 1002, "amount": 20.0}
```

Hai định dạng có cấu trúc khác nhau. `JsonItemReader` được thiết kế để đọc object trong JSON array. NDJSON có một object độc lập trên mỗi dòng và không có dấu `[`/`]` bao quanh; không nên đưa trực tiếp vào reader rồi kỳ vọng nó hoạt động như JSON array.

Với NDJSON, có thể dùng `FlatFileItemReader` để đọc từng dòng rồi map mỗi dòng bằng Jackson/Gson, hoặc viết một `ItemReader` riêng. Cách đó cho phép checkpoint theo dòng và xử lý từng record theo định dạng thực tế.

## 21. Custom JsonObjectReader

Nếu cần thư viện JSON khác hoặc quy tắc mapping riêng, có thể triển khai `JsonObjectReader<T>` và truyền vào `JsonItemReaderBuilder`.

Về mặt trách nhiệm, custom reader cần:

- Mở `Resource` và chuẩn bị parser.
- Đọc object tiếp theo trong JSON array.
- Chuyển object thành kiểu `T`.
- Trả `null` khi hết item theo contract mà `JsonItemReader` mong đợi.
- Đóng parser và stream khi `close()` được gọi.
- Giải phóng tài nguyên ngay cả khi parse hoặc mapping phát sinh exception.

Ví dụ cấu trúc minh họa:

```java
public class CustomTradeJsonObjectReader implements JsonObjectReader<Trade> {

    @Override
    public void open(Resource resource) throws Exception {
        // Mở resource và khởi tạo parser streaming.
    }

    @Override
    public Trade read() throws Exception {
        // Đọc object tiếp theo và map thành Trade; trả null ở EOF.
        return null;
    }

    @Override
    public void close() throws Exception {
        // Đóng parser và stream.
    }
}
```

Đây là skeleton mô tả trách nhiệm, không phải implementation hoàn chỉnh. Cần tuân theo interface chính xác của phiên bản Spring Batch đang dùng và xử lý trạng thái bắt đầu/kết thúc array, nested structure, exception và resource lifecycle.

Nếu chỉ cần đổi cách map object sang Java class, hãy ưu tiên một implementation `JsonObjectReader` có sẵn và cấu hình Jackson/Gson trước khi tự viết parser.

## 22. Giới hạn số item và cấu hình reader

Các phiên bản Spring Batch cung cấp những thuộc tính item-counting reader như giới hạn item tối đa hoặc vị trí item ban đầu thông qua builder/reader API. Những tùy chọn này hữu ích cho test hoặc chạy một phạm vi dữ liệu đã được xác định.

Ví dụ cấu hình cơ bản vẫn nên tập trung vào các thuộc tính cốt lõi:

```java
return new JsonItemReaderBuilder<Order>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
        .saveState(true)
        .strict(true)
        .build();
```

Nếu dùng `maxItemCount` hoặc `currentItemCount`, hãy xác định rõ ý nghĩa của chúng trong phiên bản cụ thể và tương tác với checkpoint/restart. Không dùng current item count để bỏ qua dữ liệu nghiệp vụ một cách tùy tiện; phạm vi xử lý nên được biểu diễn bằng JobParameters hoặc query/manifest rõ ràng.

## 23. Bảo mật khi đọc JSON không tin cậy

JSON không có cơ chế external entity như XML, nhưng vẫn cần kiểm soát dữ liệu không tin cậy. Một số rủi ro gồm:

- JSON object có kích thước quá lớn hoặc nesting quá sâu gây tiêu thụ CPU/heap.
- Chuỗi đầu vào chứa dữ liệu độc hại được chuyển tiếp sang SQL, log hoặc hệ thống khác.
- Cấu hình polymorphic deserialization quá rộng có thể tạo nguy cơ khởi tạo kiểu không mong muốn.
- File path lấy từ JobParameters có thể trỏ đến tài nguyên ngoài thư mục được phép.
- Dữ liệu nhạy cảm bị ghi toàn bộ vào log khi parse lỗi.

Với Jackson, không bật default typing rộng cho JSON bên ngoài nếu không có yêu cầu và thiết kế bảo mật rõ ràng. Cân nhắc giới hạn kích thước input, độ sâu parser và kích thước string/number theo khả năng của phiên bản Jackson. Validate dữ liệu trước khi dùng trong SQL hoặc gọi service.

Không ghi toàn bộ raw JSON vào exception log nếu file chứa thông tin cá nhân, token hoặc dữ liệu tài chính. Ghi ID record, tên file, vị trí item và mã lỗi đủ để điều tra.

## 24. Những lỗi thường gặp khi dùng JsonItemReader

### Root JSON không phải array

Reader mong đợi array object ở cấp cao nhất. Nếu nguồn là object wrapper hoặc NDJSON, hãy chuẩn hóa hoặc dùng reader khác.

### Thiếu JsonObjectReader

Reader cần implementation để map từng object. Cấu hình `JacksonJsonObjectReader`, `GsonJsonObjectReader` hoặc custom reader phù hợp.

### Model không khớp JSON

Field name, kiểu dữ liệu, constructor hoặc annotation không phù hợp có thể làm mapping thất bại. Kiểm tra model và JSON library.

### Ngày giờ hoặc số thập phân không parse đúng

Định dạng nguồn khác với cấu hình mapper. Đăng ký module/formatter phù hợp và dùng `BigDecimal` cho giá trị cần độ chính xác.

### Bật skip cho mọi lỗi parse

Parser có thể không phục hồi được sau JSON malformed. Chỉ skip lỗi item-level khi có thể tiếp tục an toàn và nghiệp vụ cho phép.

### Restart trên file đã thay đổi

Checkpoint item count có thể trỏ sang record khác. Giữ file bất biến hoặc kiểm tra checksum/version.

### Đổi tên reader giữa các lần chạy

Tên reader được dùng để tạo key state. Đổi tên có thể làm reader không tìm thấy checkpoint cũ.

### Tắt saveState nhưng kỳ vọng restart

Nếu không lưu state, reader không thể khôi phục tiến độ theo cơ chế checkpoint thông thường. Bật `saveState` khi cần restart.

## 25. Kiểm thử JsonItemReader

Nên kiểm thử reader độc lập và trong Job integration test:

1. JSON array có một object.
2. JSON array có nhiều object và reader trả đúng thứ tự.
3. JSON array rỗng và reader trả `null` ngay khi hết dữ liệu.
4. Root JSON là object wrapper hoặc NDJSON để xác nhận định dạng không được hỗ trợ trực tiếp.
5. Field thiếu, null, field lạ và kiểu dữ liệu sai.
6. Nested object và nested array được ánh xạ đúng.
7. Ngày giờ, enum và số thập phân được chuyển đổi đúng.
8. Resource không tồn tại khi strict bật.
9. JSON malformed ở đầu, giữa và cuối file.
10. Job restart sau một số chunk đã commit với cùng JobInstance và file không đổi.
11. File thay đổi giữa lần chạy và restart để xác nhận checksum/version được kiểm tra nếu cần.
12. File lớn để đo heap, GC và throughput.

Khi test trực tiếp `ItemStreamReader`, cần gọi lifecycle `open(ExecutionContext)`, `read()`, `update(ExecutionContext)` và `close()` theo contract. Trong integration test Job, Spring Batch quản lý lifecycle của reader.

Test restart cần dùng JobRepository giữ metadata giữa các lần chạy. Nếu repository hoặc ExecutionContext bị tạo mới, test không chứng minh được khả năng khôi phục checkpoint.

## 26. Quy tắc thiết kế JsonItemReader

Hãy dùng `JsonItemReader` khi nguồn là một JSON array chứa các object có cấu trúc rõ ràng và mỗi object là một item batch. Cấu hình `JsonObjectReader` phù hợp với JSON library của ứng dụng, định nghĩa model Java và quy tắc mapping cho field, nested object, ngày giờ và số thập phân. Đưa reader vào chunk Step để xử lý từng item.

Với file theo từng lần chạy, dùng `@StepScope` để inject JobParameters và giữ nguyên file qua restart. Đặt tên reader ổn định, bật `saveState` khi cần checkpoint và không thay đổi nội dung/thứ tự array trong lúc Job còn có thể restart. Phân biệt lỗi cú pháp JSON với lỗi validation nghiệp vụ; chỉ skip item khi parser tiếp tục an toàn và nghiệp vụ chấp nhận.

Nếu nguồn là NDJSON hoặc object wrapper chứa array lồng, hãy chọn reader phù hợp hoặc viết custom reader thay vì giả định mọi JSON đều có cùng cấu trúc. Kết hợp đúng resource, mapping, chunk, checkpoint và validation sẽ giúp `JsonItemReader` xử lý JSON theo từng item một cách có kiểm soát và có thể restart.
