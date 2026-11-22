# JsonObject và Jackson mapping

Trong Spring Batch, dữ liệu JSON thường được đọc thành Java object để processor xử lý và được chuyển ngược thành JSON khi writer xuất kết quả. Jackson là thư viện phổ biến để phân tích cú pháp JSON, ánh xạ JSON sang POJO hoặc cây JSON, và serialize object thành JSON.

Khi làm việc với JSON, cần phân biệt ba lớp:

- **JSON object trong dữ liệu:** cấu trúc gồm các cặp key/value, ví dụ một object có orderId, amount và customer.
- **Object model trong Java:** POJO, DTO, record hoặc cây JSON như Jackson JsonNode và ObjectNode.
- **Jackson mapping:** quy tắc chuyển đổi giữa JSON và kiểu Java, được điều khiển bởi ObjectMapper, annotation, module và custom serializer/deserializer.

Trong Spring Batch, các abstraction JsonItemReader, JsonObjectReader, JsonFileItemWriter và JsonObjectMarshaller giúp đưa việc đọc/ghi JSON vào chunk processing. Jackson cung cấp implementation tương ứng để ánh xạ dữ liệu vào kiểu Java.

## 1. JSON object và các kiểu JsonObject trong Java

JSON có một số cấu trúc cơ bản:

~~~json
{
  "orderId": 1001,
  "customer": {
    "code": "C001",
    "name": "Nguyễn Văn An"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    },
    {
      "sku": "PEN-02",
      "quantity": 5
    }
  ],
  "paid": true
}
~~~

Đối tượng gốc có các property orderId, customer, items và paid. Trong đó customer là object lồng nhau, còn items là array các object.

Tên JsonObject có thể chỉ những kiểu khác nhau tùy thư viện:

| Kiểu | Thư viện | Đặc điểm |
| --- | --- | --- |
| JsonNode / ObjectNode | Jackson | Cây JSON tổng quát; ObjectNode biểu diễn JSON object có thể chỉnh sửa |
| JsonObject | Jakarta JSON Processing (JSON-P) | API JSON object theo chuẩn Jakarta |
| JsonObject | Gson | Kiểu JSON object của thư viện Gson |
| POJO/DTO | Java | Kiểu dữ liệu nghiệp vụ được Jackson ánh xạ từ JSON |

Trong Jackson, kiểu thường dùng để biểu diễn một JSON object là ObjectNode, còn kiểu cha tổng quát là JsonNode. Jackson không đặt tên tree node chính là JsonObject.

Spring Batch cũng có interface tên JsonObjectReader<T> và JsonObjectMarshaller<T>. Chữ JsonObject trong tên interface mô tả một đơn vị JSON được đọc hoặc marshal; không có nghĩa bắt buộc phải dùng Gson JsonObject hay Jakarta JsonObject.

## 2. Ba cách ánh xạ JSON với Jackson

Jackson hỗ trợ nhiều cách làm việc với JSON:

1. **Data binding:** ánh xạ JSON trực tiếp sang POJO/DTO.
2. **Tree model:** đọc JSON thành JsonNode hoặc ObjectNode, sau đó truy cập và chỉnh sửa từng node.
3. **Streaming API:** đọc hoặc ghi token tuần tự bằng JsonParser và JsonGenerator.

| Cách | API tiêu biểu | Khi phù hợp |
| --- | --- | --- |
| Data binding | readValue, writeValue, convertValue | Cấu trúc JSON đã biết và có DTO |
| Tree model | readTree, treeToValue, valueToTree | Cấu trúc thay đổi hoặc cần kiểm tra field động |
| Streaming | JsonParser, JsonGenerator | Payload rất lớn hoặc cần kiểm soát token và bộ nhớ |

Với batch nghiệp vụ, data binding sang DTO thường dễ đọc, dễ kiểm thử và ít lỗi hơn. Tree model phù hợp khi schema không cố định hoàn toàn hoặc cần giữ các field chưa biết. Streaming phù hợp khi cần xử lý JSON lớn mà không muốn tạo cây object đầy đủ trong bộ nhớ.

## 3. Tạo DTO để nhận JSON

Giả sử file đầu vào chứa đơn hàng:

~~~json
{
  "orderId": 1001,
  "customerCode": "C001",
  "totalAmount": 250000.50,
  "currency": "VND"
}
~~~

Có thể tạo DTO:

~~~java
public class OrderJson {

    private Long orderId;
    private String customerCode;
    private BigDecimal totalAmount;
    private String currency;

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Jackson có thể tạo object và gán property dựa trên tên field/property. Nên dùng BigDecimal cho tiền thay vì double để tránh sai số dấu phẩy động.

Khi thiết kế DTO cho batch:

- Dùng kiểu nullable như Long, Integer nếu cần phân biệt field bị thiếu với giá trị 0.
- Định nghĩa rõ field bắt buộc và field optional.
- Không dùng trực tiếp entity đang được quản lý bởi persistence context nếu DTO là ranh giới dữ liệu ngoài.
- Giữ DTO đầu vào tách biệt với model ghi database nếu cấu trúc JSON khác cấu trúc bảng.
- Xác định quy tắc cho field lạ, field null và kiểu dữ liệu không hợp lệ.

## 4. Dùng ObjectMapper trực tiếp

ObjectMapper là trung tâm của Jackson data binding. Có thể dùng readValue để chuyển JSON String thành DTO:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "orderId": 1001,
          "customerCode": "C001",
          "totalAmount": 250000.50,
          "currency": "VND"
        }
        """;

OrderJson order = mapper.readValue(json, OrderJson.class);
~~~

Chiều ngược lại dùng writeValueAsString:

~~~java
String output = mapper.writeValueAsString(order);
~~~

Các phương thức thường dùng:

| API | Chức năng |
| --- | --- |
| readValue(json, Type.class) | JSON sang kiểu Java |
| writeValueAsString(value) | Object sang JSON String |
| readTree(json) | JSON sang cây JsonNode |
| treeToValue(node, Type.class) | Node sang kiểu Java |
| valueToTree(value) | Object sang cây JSON |
| convertValue(source, Type.class) | Chuyển đổi giữa các kiểu Java/JSON-compatible |

Trong ứng dụng Spring, nên cấu hình và tái sử dụng ObjectMapper đã được quản lý thay vì tạo mapper mới cho từng item. ObjectMapper đã cấu hình có thể được dùng đồng thời cho các thao tác đọc/ghi thông thường sau khi cấu hình hoàn tất; tránh thay đổi cấu hình mapper trong lúc Job đang chạy.

## 5. Mapping tên property bằng annotation

Tên field trong JSON có thể khác tên property trong Java. Dùng JsonProperty để khai báo tên JSON:

~~~java
public class CustomerJson {

    @JsonProperty("customer_id")
    private Long customerId;

    @JsonProperty("display_name")
    private String displayName;

    // getters and setters
}
~~~

JSON:

~~~json
{
  "customer_id": 501,
  "display_name": "Nguyễn Văn An"
}
~~~

Jackson ánh xạ customer_id sang customerId và display_name sang displayName.

Nếu nguồn có thể gửi nhiều tên khác nhau cho cùng một property, dùng JsonAlias:

~~~java
public class CustomerJson {

    @JsonProperty("customerCode")
    @JsonAlias({"customer_code", "code"})
    private String customerCode;

    // getters and setters
}
~~~

JsonProperty xác định tên property chính khi serialize/deserialize. JsonAlias bổ sung tên thay thế khi đọc. Khi ghi JSON, Jackson vẫn dùng tên property chính.

## 6. Mapping object lồng nhau và array

DTO có thể phản ánh cấu trúc JSON nhiều tầng:

~~~java
public class OrderJson {

    private Long orderId;
    private CustomerJson customer;
    private List<OrderLineJson> items;

    // getters and setters
}

public class CustomerJson {

    private String code;
    private String name;

    // getters and setters
}

public class OrderLineJson {

    private String sku;
    private Integer quantity;

    // getters and setters
}
~~~

Jackson tự ánh xạ object lồng nhau và array nếu kiểu property được khai báo đúng. Không cần parse từng node thủ công cho cấu trúc đã biết.

Ví dụ:

~~~java
OrderJson order = mapper.readValue(json, OrderJson.class);

String customerName = order.getCustomer().getName();
Integer firstQuantity = order.getItems().get(0).getQuantity();
~~~

Nếu customer hoặc items có thể null, cần kiểm tra trước khi truy cập. JSON hợp lệ về cú pháp không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ.

## 7. Generic type và collection

Khi đọc một JSON array thành List<OrderJson>, không thể chỉ truyền List.class vì Java type erasure làm mất kiểu phần tử. Dùng TypeReference:

~~~java
List<OrderJson> orders = mapper.readValue(
        jsonArray,
        new TypeReference<List<OrderJson>>() {});
~~~

Hoặc dùng JavaType:

~~~java
JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, OrderJson.class);

List<OrderJson> orders = mapper.readValue(jsonArray, listType);
~~~

Trong Spring Batch, JsonItemReader<OrderJson> thường đọc từng object từ mảng JSON và trả từng item cho chunk. Vì vậy, không nhất thiết phải đọc toàn bộ array thành List trước khi xử lý.

## 8. Tree model với JsonNode và ObjectNode

Khi schema không cố định, có thể đọc thành JsonNode:

~~~java
JsonNode root = mapper.readTree(json);

long orderId = root.path("orderId").asLong();
String customerCode = root.path("customerCode").asText();
JsonNode items = root.path("items");
~~~

path() trả về MissingNode khi field không tồn tại, giúp tránh một số NullPointerException. Tuy nhiên, asLong() hoặc asText() có thể trả giá trị mặc định nếu node thiếu hoặc sai kiểu. Với field bắt buộc, nên kiểm tra isMissingNode(), isNull() và kiểu node trước khi lấy giá trị.

Ví dụ kiểm tra chặt:

~~~java
JsonNode idNode = root.get("orderId");
if (idNode == null || !idNode.canConvertToLong()) {
    throw new IllegalArgumentException(
            "orderId is missing or invalid");
}

long orderId = idNode.longValue();
~~~

### Chỉnh sửa JSON object

ObjectNode cho phép thêm, sửa hoặc xóa property:

~~~java
ObjectNode object = (ObjectNode) mapper.readTree(json);
object.put("source", "BATCH");
object.put("processed", true);
object.remove("temporaryField");

String updatedJson = mapper.writeValueAsString(object);
~~~

Ép kiểu sang ObjectNode chỉ an toàn nếu root thực sự là JSON object. Có thể kiểm tra root.isObject() trước khi cast.

### Chuyển giữa JsonNode và DTO

Khi cần kiểm tra hoặc biến đổi một số field rồi mới ánh xạ sang DTO:

~~~java
JsonNode root = mapper.readTree(json);
JsonNode customerNode = root.path("customer");

CustomerJson customer = mapper.treeToValue(
        customerNode,
        CustomerJson.class);
~~~

Chiều ngược lại:

~~~java
ObjectNode jsonObject = mapper.valueToTree(order);
jsonObject.put("sourceSystem", "ERP");
~~~

Tree model hữu ích khi schema thay đổi, nhưng nếu cấu trúc đã ổn định thì DTO thường dễ kiểm soát kiểu dữ liệu và validation hơn.

## 9. Cấu hình Jackson ObjectMapper

ObjectMapper có nhiều tính năng ảnh hưởng trực tiếp đến kết quả mapping. Nên cấu hình rõ ràng thay vì phụ thuộc mọi mặc định.

Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Ý nghĩa:

- JavaTimeModule hỗ trợ các kiểu ngày giờ trong java.time.
- Tắt WRITE_DATES_AS_TIMESTAMPS để ghi ngày giờ dưới dạng chuỗi theo cấu hình serializer thay vì timestamp số.
- Tắt FAIL_ON_UNKNOWN_PROPERTIES để bỏ qua field không có trong DTO khi đọc.

Đây là lựa chọn theo contract. Nếu field lạ có thể chỉ ra sai version hoặc sai schema, nên giữ chế độ fail và xử lý rõ ràng. Nếu đối tác thường thêm field tương thích ngược, có thể bỏ qua field lạ nhưng vẫn kiểm tra các field bắt buộc.

### Naming strategy

Nếu JSON dùng snake_case còn Java dùng camelCase, có thể cấu hình:

~~~java
mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE);
~~~

Khi đó customer_code có thể ánh xạ vào customerCode. Không cần thêm JsonProperty cho từng field nếu toàn bộ schema dùng cùng một quy tắc. Annotation vẫn hữu ích cho những tên ngoại lệ.

Không thay đổi naming strategy sau khi mapper đã được sử dụng. Cấu hình mapper một lần khi khởi tạo ứng dụng.

## 10. Ngày giờ và định dạng số

JSON không có kiểu date hoặc decimal riêng. Ngày giờ thường được biểu diễn bằng String hoặc number; số thập phân được biểu diễn bằng JSON number.

Ví dụ:

~~~json
{
  "createdAt": "2026-11-15T10:30:00Z",
  "amount": 123456.78
}
~~~

DTO:

~~~java
public class PaymentJson {

    private Instant createdAt;
    private BigDecimal amount;

    // getters and setters
}
~~~

Đăng ký JavaTimeModule để Jackson hỗ trợ kiểu Instant, LocalDate, LocalDateTime và các kiểu java.time tương ứng. Cần thống nhất timezone và format với hệ thống nguồn.

Không dùng double cho số tiền nếu cần độ chính xác thập phân. BigDecimal giữ giá trị decimal tốt hơn và cho phép định nghĩa rounding mode rõ ràng khi tính toán.

Nếu nguồn gửi amount dưới dạng String thay vì JSON number, hãy xác định format và dùng custom deserializer hoặc chuyển đổi có kiểm soát. Không âm thầm chấp nhận mọi kiểu dữ liệu vì có thể che giấu thay đổi schema.

## 11. Null, field thiếu và giá trị mặc định

Ba trường hợp sau khác nhau:

~~~json
{}
~~~

~~~json
{"customerCode": null}
~~~

~~~json
{"customerCode": ""}
~~~

Chúng lần lượt biểu thị field không xuất hiện, field có giá trị null và field là chuỗi rỗng.

Với kiểu Java primitive như long, field thiếu có thể giữ giá trị mặc định 0. Nếu cần phân biệt thiếu với 0, dùng wrapper Long.

Ví dụ kiểm tra:

~~~java
if (order.getOrderId() == null) {
    throw new InvalidOrderException("orderId is required");
}

if (order.getCustomerCode() == null
        || order.getCustomerCode().isBlank()) {
    throw new InvalidOrderException("customerCode is required");
}
~~~

Không dùng JsonInclude(NON_NULL) để giải quyết lỗi dữ liệu đầu vào. Annotation này chủ yếu điều khiển cách serialize property khi ghi JSON; validation đầu vào vẫn cần được thực hiện riêng.

## 12. Custom serializer và deserializer

Khi JSON có format đặc biệt, có thể viết custom deserializer:

~~~java
public class AmountDeserializer
        extends JsonDeserializer<BigDecimal> {

    @Override
    public BigDecimal deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();
        if (value == null || value.isBlank()) {
            return null;
        }

        return new BigDecimal(value.replace(",", ""));
    }
}
~~~

Đăng ký trên property:

~~~java
public class OrderJson {

    @JsonDeserialize(using = AmountDeserializer.class)
    private BigDecimal totalAmount;

    // getters and setters
}
~~~

Ví dụ minh họa nguồn gửi số tiền dưới dạng chuỗi có dấu phân tách hàng nghìn. Trong thực tế, phải biết locale và quy ước dấu thập phân. Chuỗi 1,234 có thể mang nghĩa khác nhau theo locale; không xóa dấu phẩy nếu contract chưa rõ.

Custom serializer có thể kiểm soát định dạng khi ghi:

~~~java
public class AmountSerializer
        extends JsonSerializer<BigDecimal> {

    @Override
    public void serialize(
            BigDecimal value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeNumber(value);
    }
}
~~~

Chỉ viết custom serializer/deserializer khi mapping mặc định không đáp ứng contract. Logic parse phức tạp cần có unit test cho dữ liệu hợp lệ, dữ liệu biên và dữ liệu lỗi.

## 13. Enum và giá trị không nhận diện

JSON thường biểu diễn enum bằng String:

~~~json
{
  "status": "APPROVED"
}
~~~

DTO:

~~~java
public enum OrderStatus {
    NEW,
    APPROVED,
    REJECTED
}
~~~

Jackson có thể ánh xạ String sang enum theo tên. Nếu nguồn gửi giá trị ngoài danh sách, mapping có thể thất bại tùy cấu hình.

Không nên tự động biến mọi giá trị lạ thành một enum mặc định nếu điều đó làm mất thông tin. Có thể:

- Reject record và ghi lỗi dữ liệu.
- Dùng String ở DTO biên rồi validate trong processor.
- Dùng enum có giá trị UNKNOWN nếu nghiệp vụ định nghĩa rõ.
- Viết custom deserializer để giữ nguyên giá trị gốc và phân loại lỗi.

Với batch import, ghi lại giá trị enum không hợp lệ và message ID/record key để có thể sửa và phát lại.

## 14. Đọc JSON bằng JsonItemReader

Spring Batch cung cấp JsonItemReader<T> để đọc JSON thành từng item. Với Jackson, dùng JacksonJsonObjectReader<T> để ánh xạ từng JSON object sang kiểu Java.

Ví dụ file đầu vào là một JSON array:

~~~json
[
  {
    "orderId": 1001,
    "customerCode": "C001",
    "totalAmount": 250000.50
  },
  {
    "orderId": 1002,
    "customerCode": "C002",
    "totalAmount": 180000.00
  }
]
~~~

Cấu hình reader:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderJson> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    JacksonJsonObjectReader<OrderJson> objectReader =
            new JacksonJsonObjectReader<>(OrderJson.class);

    return new JsonItemReaderBuilder<OrderJson>()
            .name("orderJsonReader")
            .resource(inputFile)
            .jsonObjectReader(objectReader)
            .saveState(true)
            .build();
}
~~~

Reader trả về từng OrderJson cho chunk Step. Ứng dụng không cần tự đọc toàn bộ file thành List trước khi xử lý.

JsonItemReader được thiết kế cho cấu trúc JSON mà JsonObjectReader hỗ trợ, thường là một JSON array chứa các object. Nếu nguồn dùng cấu trúc khác, ví dụ root object có property orders chứa array, cần kiểm tra API của phiên bản đang dùng hoặc viết reader phù hợp để đi đến đúng array.

### Cấu hình ObjectMapper tùy chỉnh

Nếu cần JavaTimeModule, naming strategy hoặc quy tắc unknown field riêng, có thể tạo JacksonJsonObjectReader với ObjectMapper đã cấu hình theo API của phiên bản Spring Batch đang dùng. Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

JacksonJsonObjectReader<OrderJson> objectReader =
        new JacksonJsonObjectReader<>(OrderJson.class);
objectReader.setMapper(mapper);
~~~

Tên constructor hoặc setter có thể khác giữa các phiên bản Spring Batch. Hãy đối chiếu API version của dự án; nguyên tắc là dùng cùng ObjectMapper đã cấu hình thay vì để reader tự tạo mapper mặc định khi cần mapping đặc biệt.

## 15. Đọc JSON theo từng dòng (NDJSON)

Không phải file JSON nào cũng là một array. Một số hệ thống dùng NDJSON (newline-delimited JSON), trong đó mỗi dòng là một JSON document độc lập:

~~~text
{"orderId":1001,"customerCode":"C001","totalAmount":250000.50}
{"orderId":1002,"customerCode":"C002","totalAmount":180000.00}
{"orderId":1003,"customerCode":"C003","totalAmount":99000.00}
~~~

NDJSON khác với một JSON array. Nếu JsonItemReader của phiên bản đang dùng yêu cầu root array, không thể đưa NDJSON vào mà chỉ đổi extension file.

Có thể dùng FlatFileItemReader<String> để đọc từng dòng, rồi parse bằng Jackson trong processor:

~~~java
@Bean
public ItemProcessor<String, OrderJson> ndjsonProcessor(
        ObjectMapper objectMapper) {

    return line -> objectMapper.readValue(line, OrderJson.class);
}
~~~

Hoặc viết custom ItemReader dùng Jackson streaming parser để đọc từng JSON document. Cách chọn phụ thuộc kích thước file, khả năng xử lý lỗi theo dòng và yêu cầu restart.

Không dùng readTree() trên toàn bộ NDJSON như thể đó là một JSON document duy nhất. Mỗi dòng phải được parse riêng hoặc dùng parser streaming theo format.

## 16. Ghi JSON bằng JsonFileItemWriter

Spring Batch cung cấp JsonFileItemWriter<T> để ghi item thành JSON. Với Jackson, dùng JacksonJsonObjectMarshaller<T>:

~~~java
@Bean
public JsonFileItemWriter<OrderJson> orderJsonWriter(
        Resource outputFile) {

    JacksonJsonObjectMarshaller<OrderJson> marshaller =
            new JacksonJsonObjectMarshaller<>();

    return new JsonFileItemWriterBuilder<OrderJson>()
            .name("orderJsonWriter")
            .resource(outputFile)
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
~~~

Writer chuyển từng OrderJson thành JSON object và quản lý cấu trúc file theo implementation của Spring Batch. Với writer này, cần kiểm tra format file kết quả mà hệ thống nhận yêu cầu, bao gồm root array, pretty print nếu có và cách xử lý khi không có item.

Nếu cần cấu hình ObjectMapper riêng cho marshaller, dùng constructor hoặc setter tương ứng của version Spring Batch đang sử dụng. Đảm bảo mapper của reader và writer thống nhất về naming strategy, date format, enum và custom serializer/deserializer khi hai chiều phải tương thích.

### Ghi JSON không đồng nghĩa ghi một object JSON duy nhất

JsonFileItemWriter ghi một chuỗi item theo định dạng mà writer quản lý. Nếu cần một JSON document có root object chứa metadata và một array lồng nhau, chẳng hạn:

~~~json
{
  "batchId": "BATCH-2026-11",
  "generatedAt": "2026-11-15T10:30:00Z",
  "orders": [
    {
      "orderId": 1001
    }
  ]
}
~~~

có thể cần writer tùy chỉnh hoặc bước đóng gói metadata riêng. Không giả định JsonFileItemWriter tự tạo mọi cấu trúc root object tùy ý.

## 17. Jackson mapping trong processor

Một pattern hữu ích là reader parse JSON thành DTO đầu vào, processor validate và chuyển thành model đích:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderJson, OrderEntity> {

    @Override
    public OrderEntity process(OrderJson input) {
        if (input.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.getTotalAmount() == null
                || input.getTotalAmount().signum() < 0) {
            throw new InvalidOrderException("totalAmount is invalid");
        }

        return new OrderEntity(
                input.getOrderId(),
                input.getCustomerCode(),
                input.getTotalAmount());
    }
}
~~~

Tách DTO đầu vào khỏi entity giúp ứng dụng không phụ thuộc trực tiếp vào schema bên ngoài. Nếu đối tác đổi tên field hoặc thêm metadata, chỉ mapping layer cần thay đổi.

Có thể dùng JsonNode nếu một số field động:

~~~java
public OrderEntity map(JsonNode node) {
    JsonNode sourceNode = node.path("source");
    String source = sourceNode.isTextual()
            ? sourceNode.textValue()
            : "UNKNOWN";

    OrderJson order = mapper.convertValue(node, OrderJson.class);
    return toEntity(order, source);
}
~~~

Không để default value làm mất dấu hiệu schema sai đối với field bắt buộc. Nếu thiếu source là lỗi nghiệp vụ, hãy reject thay vì tự gán UNKNOWN.

## 18. Validation sau khi mapping

Jackson chịu trách nhiệm parse và ánh xạ kiểu dữ liệu. Nó không tự xác nhận mọi quy tắc nghiệp vụ.

Ví dụ JSON có thể parse thành DTO nhưng vẫn không hợp lệ:

~~~json
{
  "orderId": -1,
  "customerCode": "",
  "totalAmount": -500
}
~~~

Sau mapping, có thể validate bằng Jakarta Bean Validation:

~~~java
public class OrderJson {

    @NotNull
    @Positive
    private Long orderId;

    @NotBlank
    private String customerCode;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal totalAmount;

    // getters and setters
}
~~~

Trong processor hoặc một validation service, gọi Validator để kiểm tra constraint và chuyển violation thành exception nghiệp vụ phù hợp. Nếu muốn Spring Batch skip record lỗi, cần phân loại exception rõ ràng và cấu hình skip policy tương ứng.

Phân biệt:

- JSON syntax error: tài liệu JSON không hợp lệ.
- Mapping error: JSON hợp lệ nhưng không chuyển được sang kiểu Java.
- Validation error: object đã tạo được nhưng vi phạm constraint.
- Business error: object hợp lệ về cấu trúc nhưng không thỏa quy tắc nghiệp vụ.

Phân loại đúng giúp retry, skip, reject và monitoring hoạt động chính xác.

## 19. Xử lý field không biết và version schema

Đối tác có thể thêm field mới theo thời gian. Có hai chiến lược:

**Strict mapping:** từ chối field không biết. Phù hợp khi schema phải khớp chính xác hoặc field mới có thể thay đổi ý nghĩa dữ liệu.

**Tolerant mapping:** bỏ qua field không biết. Phù hợp khi nguồn bảo đảm thêm field mới tương thích ngược và consumer chỉ quan tâm một phần schema.

Có thể thêm version vào JSON:

~~~json
{
  "schemaVersion": 2,
  "orderId": 1001,
  "customerCode": "C001"
}
~~~

Processor hoặc reader có thể kiểm tra schemaVersion và chọn DTO/mapper tương ứng. Không nên cố ánh xạ mọi version vào cùng DTO bằng nhiều giá trị mặc định nếu các version có thay đổi ngữ nghĩa.

Nếu cần giữ field lạ để ghi lại hoặc chuyển tiếp, tree model ObjectNode có thể hữu ích. Với DTO, có thể dùng JsonAnySetter/JsonAnyGetter để lưu các property bổ sung trong Map, nếu contract cho phép.

## 20. Polymorphic JSON và subtype

Một JSON array có thể chứa nhiều loại item:

~~~json
[
  {
    "type": "PAYMENT",
    "paymentId": "P-100",
    "amount": 250000
  },
  {
    "type": "REFUND",
    "refundId": "R-200",
    "amount": 50000
  }
]
~~~

Có thể mô hình hóa subtype bằng JsonTypeInfo và JsonSubTypes:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = PaymentEvent.class,
                name = "PAYMENT"),
        @JsonSubTypes.Type(
                value = RefundEvent.class,
                name = "REFUND")
})
public abstract class FinancialEvent {
}
~~~

Subtype:

~~~java
public class PaymentEvent extends FinancialEvent {
    private String paymentId;
    private BigDecimal amount;
    // getters and setters
}

public class RefundEvent extends FinancialEvent {
    private String refundId;
    private BigDecimal amount;
    // getters and setters
}
~~~

Chỉ cho phép các subtype được liệt kê rõ. Không bật Jackson default typing rộng cho JSON không tin cậy; metadata kiểu tùy ý có thể tạo rủi ro bảo mật khi deserialize. Với dữ liệu từ đối tác hoặc người dùng, dùng allowlist subtype và kiểm tra version/schema.

## 21. JSON lớn và giới hạn bộ nhớ

Nếu file JSON chứa hàng triệu object, không nên dùng ObjectMapper.readTree() cho toàn bộ file rồi giữ cả cây trong bộ nhớ. Cây JSON có thể lớn hơn đáng kể so với kích thước file.

Với một JSON array lớn, JsonItemReader giúp đọc từng object theo mô hình ItemReader và chuyển từng item vào chunk. Khi cần kiểm soát token sâu hơn, có thể dùng Jackson streaming API hoặc custom JsonObjectReader.

Các nguyên tắc:

- Không nạp toàn bộ file thành List nếu có thể đọc theo item.
- Giữ DTO chỉ chứa field cần xử lý.
- Chọn chunk size dựa trên memory và transaction duration.
- Giới hạn độ dài String và kích thước nested array theo contract.
- Tránh log nguyên payload lớn.
- Theo dõi heap và thời gian parse.

JSON lồng nhau quá sâu hoặc chứa array không giới hạn có thể tạo áp lực memory. Đặt giới hạn kích thước file/request ở tầng tiếp nhận và kiểm tra cấu trúc trước khi đưa vào Job.

## 22. Restart và checkpoint với JSON reader/writer

JsonItemReader và JsonFileItemWriter là các thành phần ItemStream có thể lưu state khi bật saveState. Đặt name ổn định và giữ resource/input ổn định giữa lần chạy đầu và restart.

Ví dụ:

~~~java
return new JsonItemReaderBuilder<OrderJson>()
        .name("orderJsonReader")
        .resource(inputFile)
        .jsonObjectReader(new JacksonJsonObjectReader<>(OrderJson.class))
        .saveState(true)
        .build();
~~~

Khi Job restart cùng JobInstance, reader dùng checkpoint đã lưu để tiếp tục vị trí đọc theo khả năng implementation. Writer cũng cần giữ đúng output resource và state để tiếp tục ghi.

Để restart an toàn:

- Giữ nguyên Job name và identifying JobParameters.
- Không thay file input hoặc nội dung file giữa lần chạy và restart.
- Giữ ổn định reader/writer name.
- Giữ nguyên ObjectMapper configuration và schema version.
- Không đổi thứ tự item trong input.
- Bảo đảm writer idempotent hoặc tiếp tục đúng output position.

Nếu input JSON được tạo lại hoặc thay đổi schema, hãy xác định đó là input version mới thay vì áp checkpoint cũ vào dữ liệu khác.

## 23. JSON parse error, skip và dead-letter

JSON lỗi cú pháp hoặc mapping error có thể khiến reader ném exception trước khi trả về item. Điều này khác với validation error phát sinh trong processor sau khi item đã được đọc thành công.

Với dữ liệu cần tiếp tục xử lý khi một record lỗi:

- Nếu mỗi record là một dòng NDJSON, có thể bắt lỗi parse theo dòng và đưa record lỗi vào reject flow.
- Nếu file là một JSON array duy nhất và lỗi cú pháp làm parser mất cấu trúc, không phải lúc nào cũng có thể an toàn bỏ qua một object để đọc object tiếp theo.
- Ghi lại vị trí, input file ID, record key nếu có và nguyên nhân lỗi.
- Chỉ skip exception đã phân loại rõ; không skip mọi IOException hoặc lỗi I/O hệ thống.
- Dùng dead-letter/reject output để giữ raw record khi có thể.

Với JSON array, lỗi cú pháp ở một vị trí có thể làm parser không biết điểm bắt đầu object tiếp theo. Nếu yêu cầu cô lập lỗi theo record, NDJSON hoặc một message per record thường dễ phục hồi hơn.

Không ghi toàn bộ payload nhạy cảm vào log hoặc DLQ không được bảo vệ. Lưu raw record ở nơi có kiểm soát truy cập và retention phù hợp.

## 24. Bảo mật khi deserialize JSON

JSON là dữ liệu đầu vào và phải được xem là không tin cậy. Các biện pháp cần có:

- Không bật default typing rộng hoặc cho phép class name tùy ý trong payload.
- Allowlist subtype nếu dùng polymorphic mapping.
- Giới hạn kích thước file, độ sâu lồng nhau và độ dài field.
- Validate field bắt buộc, enum, số lượng và range.
- Không deserialize trực tiếp vào entity có setter gây side effect.
- Không dùng payload để điều khiển class hoặc method được thực thi.
- Không log token, secret hoặc thông tin cá nhân không cần thiết.
- Cập nhật Jackson và Spring Batch lên phiên bản được hỗ trợ theo chính sách dự án.

Không dùng custom deserializer để thực thi biểu thức hoặc gọi class được chỉ định trong JSON. Deserializer nên chỉ chuyển đổi dữ liệu theo contract đã biết.

## 25. Kiểm thử Jackson mapping

Nên kiểm thử riêng DTO mapping trước khi chạy toàn bộ Job.

Ví dụ:

~~~java
@Test
void mapsNestedOrderJson() throws Exception {
    String json = """
            {
              "orderId": 1001,
              "customer": {
                "code": "C001",
                "name": "Nguyễn Văn An"
              },
              "items": [
                {"sku": "BOOK-01", "quantity": 2}
              ]
            }
            """;

    OrderJson order = objectMapper.readValue(json, OrderJson.class);

    assertEquals(1001L, order.getOrderId());
    assertEquals("Nguyễn Văn An", order.getCustomer().getName());
    assertEquals(2, order.getItems().get(0).getQuantity());
}
~~~

Các trường hợp nên kiểm tra:

- Property name chuẩn và alias.
- Nested object và array rỗng.
- Field thiếu, null và chuỗi rỗng.
- Sai kiểu dữ liệu, ví dụ String thay cho number.
- Decimal lớn và precision.
- Ngày giờ, timezone và format.
- Enum không nhận diện.
- Unknown field và schema version.
- Unicode tiếng Việt và ký tự đặc biệt.
- Custom serializer/deserializer.
- JSON root array, root object và NDJSON.

Sau đó kiểm thử tích hợp:

1. JsonItemReader đọc đúng số item.
2. Processor validate và map đúng.
3. JsonFileItemWriter tạo JSON hợp lệ.
4. Restart sau một số chunk commit không bỏ sót hoặc ghi trùng.
5. Parse error và validation error được phân loại đúng.
6. File output có thể được đọc lại bằng mapper của consumer.

## 26. Những lỗi thường gặp

### Nhầm JsonObject của các thư viện

Jackson dùng JsonNode/ObjectNode; Gson và Jakarta JSON-P có kiểu JsonObject riêng. Xác định đúng package và API đang sử dụng.

### Dùng DTO sai tên property

JSON dùng snake_case nhưng Java dùng camelCase. Dùng JsonProperty, JsonAlias hoặc naming strategy phù hợp.

### Đọc JSON array thành List bằng List.class

Type erasure làm mất kiểu phần tử. Dùng TypeReference hoặc JavaType; với batch, cân nhắc JsonItemReader đọc từng item.

### Đọc NDJSON bằng reader mong đợi JSON array

NDJSON là nhiều JSON document theo dòng. Dùng FlatFileItemReader kết hợp ObjectMapper hoặc custom streaming reader.

### Bỏ qua null và field thiếu

DTO có thể nhận null hoặc giá trị primitive mặc định. Validate field bắt buộc sau mapping.

### Tắt lỗi unknown field quá rộng

Schema thay đổi có thể bị che giấu. Chọn strict hoặc tolerant mapping theo contract và kiểm tra version.

### Dùng double cho tiền

Sai số dấu phẩy động có thể ảnh hưởng tính toán. Dùng BigDecimal.

### Tạo ObjectMapper mới cho từng item

Làm tăng chi phí và khiến cấu hình mapping không nhất quán. Tái sử dụng mapper đã cấu hình.

### Parse toàn bộ file JSON lớn vào JsonNode

Có thể tiêu tốn nhiều heap. Dùng JsonItemReader hoặc streaming.

### Bật default typing cho payload không tin cậy

Có thể mở rộng kiểu được deserialize ngoài dự kiến. Dùng subtype allowlist và cấu hình an toàn.

### Cho rằng JSON hợp lệ là dữ liệu nghiệp vụ hợp lệ

Mapping chỉ xác nhận cấu trúc/kiểu. Cần validation và business rule riêng.

### Thay ObjectMapper hoặc input file khi restart

Checkpoint có thể không còn khớp với nội dung hoặc cách mapping. Giữ ổn định input, schema và mapper configuration trong cùng JobInstance.

## 27. Quy trình thiết kế JSON mapping trong Spring Batch

Trước khi triển khai, hãy xác định:

1. JSON root là object, array hay NDJSON?
2. Một item JSON tương ứng với DTO nào?
3. Có nested object, array hoặc polymorphic subtype không?
4. JSON property name có khác tên Java không?
5. Field nào bắt buộc, nullable hoặc có default?
6. Số tiền, ngày giờ và timezone dùng format nào?
7. Unknown field và schema version được xử lý ra sao?
8. Dùng POJO data binding hay tree model JsonNode?
9. Có cần custom serializer/deserializer không?
10. JsonItemReader/JsonFileItemWriter có phù hợp với cấu trúc file không?
11. File có lớn đến mức cần streaming hoặc NDJSON không?
12. Reader/writer có saveState và restart được không?
13. Parse error, mapping error và validation error được phân loại thế nào?
14. Payload có được giới hạn kích thước và kiểm soát bảo mật không?
15. Output có thể được consumer parse lại theo cùng contract không?

Với schema ổn định, ưu tiên DTO và Jackson data binding. Dùng JsonNode/ObjectNode khi cần xử lý cấu trúc động. Dùng streaming khi kích thước hoặc yêu cầu kiểm soát token không phù hợp với việc tạo object tree. Trong Spring Batch, để reader trả từng item cho chunk và để writer quản lý output theo lifecycle của Step thay vì nạp hoặc ghi toàn bộ dữ liệu thủ công.

## Kết luận

JSON object là cấu trúc dữ liệu; Jackson cung cấp data binding sang POJO, tree model bằng JsonNode/ObjectNode và streaming API để xử lý token. Trong Spring Batch, JsonItemReader kết hợp JacksonJsonObjectReader có thể đọc từng object từ JSON array, còn JsonFileItemWriter kết hợp JacksonJsonObjectMarshaller ghi item thành JSON. Hãy định nghĩa DTO và property mapping rõ ràng, cấu hình ObjectMapper thống nhất cho tên field, ngày giờ, decimal và unknown field, rồi validate nghiệp vụ sau khi parse. Với schema động, dùng tree model; với NDJSON hoặc file rất lớn, chọn reader/streaming phù hợp. Giữ input, schema, mapper và checkpoint ổn định khi restart, đồng thời xem JSON là dữ liệu không tin cậy và kiểm thử cả mapping lẫn toàn bộ luồng đọc/ghi.
