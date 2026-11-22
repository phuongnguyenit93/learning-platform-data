# Chuyển đối tượng thành cây bằng valueToTree

Trong một ứng dụng Java, dữ liệu thường bắt đầu dưới dạng POJO, record, Map hoặc collection. Có lúc ứng dụng cần chuyển dữ liệu đó sang dạng JSON để kiểm tra field, thêm metadata, loại bỏ một số thuộc tính hoặc kết hợp với một payload động. Nếu mục tiêu là thao tác với cấu trúc JSON trong bộ nhớ, không nhất thiết phải serialize thành chuỗi rồi parse lại.

Jackson cung cấp phương thức **ObjectMapper.valueToTree()** để chuyển một giá trị Java thành cây JsonNode. Phương thức này dùng cơ chế serialization của Jackson để tạo ra biểu diễn JSON tương ứng, sau đó trả về node gốc phù hợp như ObjectNode, ArrayNode, TextNode hoặc NullNode.

Ví dụ, một User Java có thể được chuyển thành ObjectNode; một List<User> thành ArrayNode; một String thành TextNode; một giá trị null thành NullNode. Sau đó, ứng dụng có thể dùng API Tree Model để đọc, thêm, sửa hoặc xóa property.

Điểm cần nhớ là valueToTree() chuyển **giá trị Java thành biểu diễn cây JSON**. Nếu đầu vào đã là một chuỗi chứa văn bản JSON, phương thức không parse nội dung chuỗi đó thành object; nó xem chuỗi như một giá trị Java String và tạo TextNode. Muốn parse văn bản JSON, hãy dùng readTree().

## 1. valueToTree() là gì?

valueToTree() là phương thức của ObjectMapper:

~~~java
<T extends JsonNode> T valueToTree(Object fromValue)
~~~

Nó nhận một giá trị Java và trả về một JsonNode thể hiện cách giá trị đó được serialize theo cấu hình Jackson hiện tại.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

User user = new User(10L, "An", true);

JsonNode tree = mapper.valueToTree(user);
~~~

Nếu User có các property id, name và active, cây kết quả có dạng:

~~~json
{
  "id": 10,
  "name": "An",
  "active": true
}
~~~

Có thể truy cập:

~~~java
long id = tree.path("id").asLong();
String name = tree.path("name").asText();
boolean active = tree.path("active").asBoolean();
~~~

Không cần tạo chuỗi JSON trung gian để thực hiện thao tác trên cây.

### 1.1. Hình dung quá trình chuyển đổi

~~~text
Java value
  |
  +-- POJO / record
  +-- Map
  +-- List / array
  +-- String / number / boolean
  +-- null
  |
  v
ObjectMapper.valueToTree(...)
  |
  v
JsonNode
  |
  +-- ObjectNode
  +-- ArrayNode
  +-- TextNode
  +-- NumericNode
  +-- BooleanNode
  +-- NullNode
  |
  v
Đọc / thêm / sửa / xóa / chuyển tiếp
~~~

Kiểu node phụ thuộc vào JSON representation mà serializer tạo ra. Không phải mọi giá trị Java đều trở thành ObjectNode.

### 1.2. Khi nào nên dùng?

valueToTree() hữu ích khi:

- Muốn kiểm tra hoặc thao tác cấu trúc JSON trong bộ nhớ.
- Cần thêm metadata vào một POJO trước khi gửi đi.
- Muốn kết hợp dữ liệu typed với một payload động.
- Cần chọn field hoặc thay đổi cấu trúc trước khi serialize cuối cùng.
- Cần chuyển một DTO thành JsonNode để truyền cho API hoặc module khác nhận tree.
- Muốn kiểm tra JSON representation trong test mà không cần serialize thành String rồi parse lại.

Nếu chỉ cần chuyển Java object sang JSON text, dùng writeValueAsString() hoặc writeValue(). Nếu cần đọc JSON text, dùng readTree() hoặc readValue().

## 2. Chuyển POJO thành ObjectNode

Ví dụ class:

~~~java
public class Customer {

    private Long id;
    private String name;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Chuyển thành cây:

~~~java
ObjectMapper mapper = new ObjectMapper();

Customer customer = new Customer(
    1001L,
    "An Nguyen",
    "an@example.com"
);

JsonNode tree = mapper.valueToTree(customer);
~~~

Có thể kiểm tra kiểu:

~~~java
if (!tree.isObject()) {
    throw new IllegalStateException("Expected an object tree");
}

ObjectNode object = (ObjectNode) tree;
~~~

Kết quả là ObjectNode vì serializer của Customer tạo JSON object.

JSON tương ứng:

~~~json
{
  "id": 1001,
  "name": "An Nguyen",
  "email": "an@example.com"
}
~~~

Nếu ứng dụng biết chắc kiểu root luôn là object, có thể nhận trực tiếp kiểu ObjectNode:

~~~java
ObjectNode object = mapper.valueToTree(customer);
~~~

Cách này dựa trên cam kết rằng representation của Customer là object. Nếu serializer tùy biến có thể trả scalar hoặc array, hãy nhận JsonNode và kiểm tra isObject() trước khi ép kiểu.

### 2.1. Không cần mọi field Java đều xuất hiện

Tree được tạo theo quy tắc serialization của Jackson. Một field có thể không xuất hiện nếu:

- Không được Jackson xem là property có thể serialize.
- Bị đánh dấu @JsonIgnore.
- Bị loại bởi @JsonInclude.
- Getter hoặc field không được nhận diện theo visibility configuration.
- Custom serializer không ghi property đó.
- Một quy tắc mix-in hoặc filter loại bỏ property.

Vì vậy, valueToTree() phản ánh **JSON output của mapper**, không phải bản sao toàn bộ bộ nhớ của object Java.

## 3. Chuyển Map và collection thành cây

Map có key phù hợp với JSON object thường trở thành ObjectNode:

~~~java
Map<String, Object> attributes = new LinkedHashMap<>();
attributes.put("source", "import");
attributes.put("attempt", 2);
attributes.put("enabled", true);

JsonNode tree = mapper.valueToTree(attributes);
~~~

Cây kết quả:

~~~json
{
  "source": "import",
  "attempt": 2,
  "enabled": true
}
~~~

List hoặc array thường trở thành ArrayNode:

~~~java
List<String> tags = List.of("java", "jackson", "json");

ArrayNode array = mapper.valueToTree(tags);
~~~

JSON:

~~~json
[
  "java",
  "jackson",
  "json"
]
~~~

Collection chứa POJO cũng được chuyển từng phần tử theo serializer tương ứng:

~~~java
List<Customer> customers = List.of(
    new Customer(1L, "An", "an@example.com"),
    new Customer(2L, "Binh", "binh@example.com")
);

ArrayNode customerTree = mapper.valueToTree(customers);
~~~

Mỗi phần tử của ArrayNode là một object node.

### 3.1. Kiểu root có thể là object hoặc array

Không nên ép mọi kết quả valueToTree() thành ObjectNode:

~~~java
JsonNode tree = mapper.valueToTree(List.of("A", "B"));

if (tree.isArray()) {
    ArrayNode array = (ArrayNode) tree;
}
~~~

Nếu input là collection, array hoặc custom serializer trả JSON array, root thường là ArrayNode.

Nếu input là scalar, root có thể là TextNode, NumericNode hoặc BooleanNode. Hãy làm việc với JsonNode khi chưa biết hình dạng root.

### 3.2. Map key và giá trị phức tạp

JSON object có tên property dạng chuỗi. Khi Map dùng kiểu key khác String, Jackson có thể dùng key serializer để chuyển key thành tên property. Kết quả phụ thuộc kiểu key và cấu hình serializer.

Không nên giả định Map<Integer, V> sẽ trở thành JSON array. Nó vẫn thường được biểu diễn như object với tên key dạng chuỗi.

Nếu key là object phức tạp hoặc có thể trùng sau khi chuyển thành chuỗi, cần thiết kế representation riêng, ví dụ List<Entry> hoặc DTO có field key/value.

## 4. Chuyển scalar thành JsonNode

valueToTree() không chỉ dành cho POJO.

~~~java
JsonNode textNode = mapper.valueToTree("Jackson");
JsonNode numberNode = mapper.valueToTree(42);
JsonNode decimalNode = mapper.valueToTree(new BigDecimal("12.50"));
JsonNode booleanNode = mapper.valueToTree(true);
~~~

Các node tương ứng:

| Java value | JsonNode thường nhận được | JSON representation |
|---|---|---|
| String | TextNode | "Jackson" |
| Integer | IntNode | 42 |
| Long | LongNode hoặc node số nguyên tương ứng | 42 |
| BigDecimal | DecimalNode hoặc node số thập phân tương ứng | 12.50 |
| Boolean | BooleanNode | true |
| List | ArrayNode | [...] |
| Map | ObjectNode | {...} |
| null | NullNode | null |

Kiểu node số cụ thể có thể phụ thuộc kiểu Java, JsonNodeFactory và cấu hình đọc/ghi số. Khi hợp đồng yêu cầu độ chính xác hoặc miền giá trị cụ thể, hãy kiểm tra node type và dùng decimalValue()/longValue() phù hợp.

### 4.1. Giá trị null trở thành NullNode

Một điểm quan trọng của valueToTree():

~~~java
JsonNode tree = mapper.valueToTree(null);

assertTrue(tree.isNull());
~~~

Kết quả là NullNode, không phải Java null.

Điều này thuận tiện khi API Tree Model cần một JsonNode đại diện cho JSON null. Tuy nhiên, nó khác với một số API chuyển đổi Java-to-Java có thể trả về tham chiếu Java null.

## 5. Phân biệt valueToTree() và readTree()

Hai phương thức có mục đích khác nhau.

### 5.1. valueToTree(): Java value thành JSON tree

~~~java
String name = "An";

JsonNode tree = mapper.valueToTree(name);
~~~

Kết quả là TextNode:

~~~json
"An"
~~~

Nếu String chứa văn bản JSON:

~~~java
String rawJson = "{\"id\":10,\"name\":\"An\"}";

JsonNode tree = mapper.valueToTree(rawJson);
~~~

Kết quả vẫn là một TextNode chứa toàn bộ chuỗi:

~~~json
"{\"id\":10,\"name\":\"An\"}"
~~~

Jackson không diễn giải nội dung String như JSON source.

### 5.2. readTree(): JSON text thành cây

Nếu muốn parse nội dung chuỗi JSON thành object tree:

~~~java
JsonNode tree = mapper.readTree(rawJson);
~~~

Kết quả:

~~~json
{
  "id": 10,
  "name": "An"
}
~~~

Bảng so sánh:

| Nhu cầu | API |
|---|---|
| POJO → JsonNode | valueToTree() |
| Map/List → JsonNode | valueToTree() |
| String Java → TextNode | valueToTree() |
| JSON text → JsonNode | readTree() |
| InputStream JSON → JsonNode | readTree() |
| JsonNode → POJO | treeToValue() hoặc convertValue() |
| POJO → JSON String | writeValueAsString() |

Không dùng valueToTree() để parse file JSON hoặc nội dung nhận từ HTTP. Hãy dùng readTree() khi đầu vào là JSON text/stream.

## 6. Phân biệt valueToTree() và convertValue()

Cả hai đều sử dụng cơ chế databind của Jackson để chuyển đổi giá trị, nhưng mục đích API khác nhau.

- valueToTree(source): chuyển Java value thành JsonNode.
- convertValue(source, TargetType.class): chuyển source thành một kiểu Java đích khác.
- treeToValue(tree, TargetType.class): chuyển JsonNode thành kiểu Java cụ thể.

Ví dụ:

~~~java
Customer customer = new Customer(1L, "An", "an@example.com");

JsonNode tree = mapper.valueToTree(customer);

CustomerView view = mapper.convertValue(
    customer,
    CustomerView.class
);
~~~

Nếu cần tree để kiểm tra hoặc sửa field, dùng valueToTree(). Nếu cần một DTO khác, dùng convertValue().

Ví dụ chuyển tree trở lại DTO:

~~~java
Customer restored = mapper.treeToValue(tree, Customer.class);
~~~

Không nên chuyển POJO sang JsonNode chỉ để chuyển ngay sang một DTO khác. Điều đó tạo thêm bước chuyển đổi không cần thiết. Dùng convertValue() trực tiếp nếu mục tiêu cuối là kiểu Java.

### 6.1. Bảng lựa chọn API

| Input | Output mong muốn | API |
|---|---|---|
| Java object | JsonNode | valueToTree() |
| JSON text | JsonNode | readTree() |
| JsonNode | Java class | treeToValue() |
| Java object | Java class khác | convertValue() |
| Java object | JSON String | writeValueAsString() |
| JSON String | Java class | readValue() |

### 6.2. Chú ý khi chuyển đổi qua tree

Tree representation là representation JSON. Nó có thể làm mất thông tin chỉ tồn tại trong kiểu Java hoặc trong object graph nhưng không được serialize.

Ví dụ:

- Kiểu Java cụ thể có thể được thay bằng một JSON scalar.
- Reference identity có thể được biểu diễn thành ID.
- Field bị @JsonIgnore sẽ không có trong tree.
- Kiểu date/time phụ thuộc module và format.
- Custom serializer có thể đổi một object thành string hoặc array.
- Các object không thể biểu diễn bằng JSON có thể cần serializer riêng.

Vì vậy, valueToTree() không phải thao tác clone object Java và không bảo toàn mọi chi tiết runtime.

## 7. Cấu hình ObjectMapper ảnh hưởng đến tree

valueToTree() dùng cơ chế serialization của mapper. Vì vậy, annotation, module và cấu hình output có thể ảnh hưởng trực tiếp đến cây tạo ra.

Ví dụ:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {

    private String name;
    private String nickname;

    // Getters and setters
}
~~~

Nếu nickname null, property có thể bị bỏ khỏi tree do NON_NULL.

~~~java
UserResponse user = new UserResponse();
user.setName("An");
user.setNickname(null);

JsonNode tree = mapper.valueToTree(user);
~~~

Tree có thể chỉ chứa:

~~~json
{
  "name": "An"
}
~~~

Property nickname không tồn tại trong tree. Đây là missing property, không phải NullNode.

Nếu cấu hình inclusion là ALWAYS, nickname có thể xuất hiện với JSON null:

~~~json
{
  "name": "An",
  "nickname": null
}
~~~

Khi đó:

~~~java
tree.has("nickname"); // true
tree.path("nickname").isNull(); // true
~~~

### 7.1. @JsonProperty và naming strategy

Tên property trong tree là tên JSON sau khi Jackson áp dụng annotation và naming strategy.

~~~java
public class User {
    @JsonProperty("display_name")
    private String displayName;
}
~~~

Tree sẽ dùng display_name nếu property đó được serialize.

Nếu mapper dùng SNAKE_CASE, các tên như createdAt có thể được ghi thành created_at. Hãy dùng tên JSON trong Tree Model, không giả định tên luôn giống field Java.

### 7.2. @JsonValue

Một value object có @JsonValue có thể trở thành scalar node:

~~~java
public final class ProductCode {

    private final String value;

    public ProductCode(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
~~~

~~~java
JsonNode codeTree = mapper.valueToTree(
    new ProductCode("SKU-100")
);
~~~

Kết quả là TextNode với nội dung SKU-100, không phải ObjectNode có field value.

### 7.3. @JsonUnwrapped

Nếu property con dùng @JsonUnwrapped, tree phản ánh dạng phẳng mà serializer tạo ra. Các property con xuất hiện ở cấp object cha, theo prefix/suffix nếu được khai báo.

Điều này có nghĩa Tree Model thể hiện JSON contract, không nhất thiết phản ánh cấu trúc object graph Java.

### 7.4. Custom serializer và module

Nếu mapper đăng ký custom serializer cho một kiểu, valueToTree() cũng sử dụng serializer đó. Ví dụ một kiểu Money có thể được ghi thành number, object hoặc string theo serializer đã cấu hình.

Các module như JavaTimeModule ảnh hưởng representation của LocalDate, Instant và các kiểu thời gian khác. Nếu mapper không đăng ký module phù hợp hoặc dùng format không đúng, cây kết quả có thể khác mong đợi hoặc quá trình chuyển đổi có thể thất bại.

Hãy tái sử dụng mapper đã được cấu hình đúng cho ứng dụng. Không tạo một ObjectMapper mới với default settings chỉ để gọi valueToTree() nếu ứng dụng đang dựa vào module, naming strategy hoặc custom serializers.

## 8. Chuyển đổi ngày giờ và kiểu đặc biệt

Ví dụ:

~~~java
public record AuditInfo(
    Instant createdAt,
    LocalDate businessDate
) {}
~~~

Chuyển thành tree:

~~~java
JsonNode tree = mapper.valueToTree(
    new AuditInfo(
        Instant.parse("2026-11-12T08:00:00Z"),
        LocalDate.of(2026, 11, 12)
    )
);
~~~

Representation phụ thuộc JavaTimeModule và cấu hình date/time của mapper. Có thể là string ISO-8601 hoặc dạng khác nếu cấu hình yêu cầu timestamp.

Ví dụ cấu hình string date/time:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Tree khi đó thường chứa TextNode cho các kiểu java.time được hỗ trợ.

Không nên giả định một mapper bất kỳ sẽ serialize mọi kiểu đặc biệt theo cùng cách. Hãy kiểm tra dependency module và cấu hình thực tế của ứng dụng.

## 9. Chuyển POJO thành tree rồi thêm metadata

Một tình huống thường gặp là cần bổ sung thông tin nguồn, version hoặc correlation ID vào payload trước khi gửi đi.

Ví dụ:

~~~java
OrderResponse response = orderService.getOrder(orderId);

ObjectNode payload = mapper.valueToTree(response);

payload.put("source", "order-service");
payload.put("schemaVersion", 2);
payload.put("correlationId", correlationId);
~~~

JSON kết quả có thêm metadata:

~~~json
{
  "orderId": "ORD-100",
  "status": "PAID",
  "source": "order-service",
  "schemaVersion": 2,
  "correlationId": "corr-123"
}
~~~

Cách này hữu ích khi DTO nghiệp vụ không cần biết metadata vận chuyển, nhưng envelope gửi đi cần thêm một số field.

### 9.1. Kiểm tra root trước khi sửa

Nếu serializer của response trả về object, ép kiểu sang ObjectNode là hợp lý. Nếu không chắc, hãy kiểm tra:

~~~java
JsonNode tree = mapper.valueToTree(response);

if (!tree.isObject()) {
    throw new IllegalStateException(
        "Order response must serialize as a JSON object"
    );
}

ObjectNode payload = (ObjectNode) tree;
payload.put("source", "order-service");
~~~

Không gọi put() trên một JsonNode bất kỳ. put() là API của ObjectNode.

### 9.2. Tránh ghi đè field đã có

Trước khi thêm metadata, xác định chính sách nếu property đã tồn tại:

~~~java
if (payload.has("schemaVersion")) {
    throw new IllegalStateException(
        "schemaVersion is already present in the response"
    );
}

payload.put("schemaVersion", 2);
~~~

Hoặc dùng set() nếu muốn thay thế có chủ đích:

~~~java
payload.set("metadata", mapper.valueToTree(metadata));
~~~

Đừng ghi đè field nghiệp vụ chỉ vì tên metadata trùng nhau. Có thể đặt metadata trong một object riêng:

~~~json
{
  "data": {
    "orderId": "ORD-100",
    "status": "PAID"
  },
  "meta": {
    "source": "order-service",
    "schemaVersion": 2
  }
}
~~~

Cấu trúc envelope giúp tránh collision và phân tách dữ liệu nghiệp vụ với thông tin vận chuyển.

## 10. Kết hợp nhiều nguồn thành một tree

valueToTree() có thể chuyển từng nguồn Java thành JsonNode rồi gắn chúng vào một object lớn.

~~~java
ObjectNode envelope = mapper.createObjectNode();

envelope.set("customer", mapper.valueToTree(customer));
envelope.set("order", mapper.valueToTree(order));
envelope.set("metadata", mapper.valueToTree(metadata));
~~~

JSON:

~~~json
{
  "customer": {
    "id": 10,
    "name": "An"
  },
  "order": {
    "id": "ORD-100",
    "total": 250000
  },
  "metadata": {
    "source": "checkout",
    "version": 1
  }
}
~~~

Cách này phù hợp khi các phần của payload được xây dựng từ nhiều service hoặc nhiều model.

Nếu các node đã tồn tại, không cần chuyển lại qua valueToTree(). Có thể gắn trực tiếp bằng set() nếu node có kiểu phù hợp.

### 10.1. set(), replace(), put() và deepCopy()

Các API thường dùng:

| API | Mục đích |
|---|---|
| put(name, value) | Thêm/thay property scalar |
| set(name, node) | Thêm/thay property bằng JsonNode |
| replace(name, node) | Thay property đã tồn tại |
| remove(name) | Xóa property |
| putObject(name) | Tạo ObjectNode con |
| putArray(name) | Tạo ArrayNode con |
| deepCopy() | Tạo bản sao sâu của tree |

Ví dụ:

~~~java
ObjectNode payload = mapper.valueToTree(order);

payload.put("source", "batch");
payload.set("customer", mapper.valueToTree(customer));
payload.remove("internalNote");
~~~

Nếu cần giữ tree gốc không đổi:

~~~java
ObjectNode copy = payload.deepCopy();
copy.put("source", "reporting");
~~~

ObjectNode và ArrayNode có thể thay đổi. Nếu nhiều thành phần dùng chung một tree, hãy xác định ownership hoặc tạo deepCopy() trước khi sửa để tránh side effect ngoài ý muốn.

## 11. Chuyển JsonNode thành POJO sau khi chỉnh sửa

Sau khi sửa tree, có thể bind lại thành DTO:

~~~java
ObjectNode tree = mapper.valueToTree(customer);

tree.put("name", "An Nguyen");

Customer restored = mapper.treeToValue(
    tree,
    Customer.class
);
~~~

Hoặc:

~~~java
Customer restored = mapper.convertValue(
    tree,
    Customer.class
);
~~~

treeToValue() thể hiện rõ nguồn là JsonNode. convertValue() tổng quát hơn và phù hợp khi cần chuyển nhiều loại nguồn Java.

Khi bind lại, Jackson vẫn áp dụng deserializer, constructor, annotation và validation/binding configuration tương ứng. Một tree có field sai kiểu hoặc thiếu field bắt buộc có thể gây lỗi mapping.

valueToTree() không tự xác nhận tree có thể được đọc lại thành kiểu ban đầu. Ví dụ custom serializer có thể biến một object thành scalar nhưng không có custom deserializer tương ứng.

## 12. valueToTree() có phải deep clone object không?

Không. valueToTree() tạo một JSON tree representation của giá trị, không phải bản sao Java giữ nguyên mọi trạng thái.

Ví dụ:

- Các method không được serialize sẽ không xuất hiện.
- Field transient hoặc bị ignore có thể bị bỏ.
- Proxy/lazy property có thể được xử lý theo serializer và trạng thái truy cập.
- Reference identity có thể được biểu diễn theo cơ chế JSON identity.
- Custom serializer có thể bỏ hoặc biến đổi thông tin.
- Kiểu Java đặc biệt có thể trở thành string/number/object khác.

Nếu mục tiêu là clone Java object, valueToTree() rồi treeToValue() chỉ phù hợp khi chấp nhận clone qua JSON contract. Nó có thể làm mất kiểu cụ thể, reference sharing hoặc thông tin không nằm trong JSON.

Nếu cần clone một JsonNode, dùng deepCopy() thường diễn đạt đúng ý định hơn:

~~~java
JsonNode copy = original.deepCopy();
~~~

Nếu cần copy domain object, cân nhắc copy constructor, mapper chuyên biệt hoặc thư viện mapping phù hợp với mô hình.

## 13. Object identity và vòng tham chiếu

Tree Model là cấu trúc JSON dạng cây, trong khi object graph Java có thể chứa vòng tham chiếu. valueToTree() sử dụng serialization của Jackson nên chịu ảnh hưởng bởi các cơ chế xử lý tham chiếu như @JsonIdentityInfo, @JsonManagedReference, @JsonBackReference và custom serializers.

Ví dụ, nếu User chứa List<Order> và Order tham chiếu ngược User, serializer thông thường có thể gặp vòng tham chiếu. Cần cấu hình quan hệ hoặc identity trước khi chuyển thành tree.

@JsonIdentityInfo có thể khiến object lần đầu được ghi đầy đủ và tham chiếu sau được biểu diễn bằng ID. Tree khi đó giữ JSON reference semantics theo cấu hình, không phải mọi liên kết Java đều trở thành object con độc lập.

Đừng dùng valueToTree() như một cách né tránh thiết kế vòng tham chiếu. Hãy xác định representation JSON của graph trước.

## 14. Polymorphism và type metadata

Nếu base type dùng @JsonTypeInfo, valueToTree() có thể đưa discriminator vào tree theo serializer configuration.

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CreatedEvent.class, name = "created"),
    @JsonSubTypes.Type(value = CancelledEvent.class, name = "cancelled")
})
public abstract class DomainEvent {}
~~~

Chuyển subtype:

~~~java
DomainEvent event = new CreatedEvent();

JsonNode tree = mapper.valueToTree(event);
~~~

Nếu serializer được gọi trong ngữ cảnh base type hoặc cấu hình polymorphic tương ứng, tree có thể chứa eventType. Kết quả cụ thể cần được kiểm tra bằng mapper và kiểu khai báo thực tế; serialize một runtime subtype trực tiếp không phải lúc nào cũng có cùng ngữ cảnh với serialize qua property khai báo base type.

Nếu type metadata là một phần hợp đồng, hãy test cả root value lẫn property có kiểu base class.

## 15. Missing, null và empty trong tree được tạo ra

Sau valueToTree(), có thể kiểm tra các trạng thái:

- Field không xuất hiện trong JSON output: get() trả Java null hoặc path() trả MissingNode.
- Field xuất hiện với null: NullNode.
- String rỗng: TextNode với nội dung rỗng.
- List rỗng: ArrayNode có size 0.
- Map/object rỗng: ObjectNode không có property.
- Số 0 và false: NumericNode và BooleanNode hợp lệ.

Ví dụ:

~~~java
public class Sample {
    public String name = "";
    public String nickname;
    public List<String> tags = new ArrayList<>();
    public boolean active;
}
~~~

Với inclusion mặc định, nickname có thể được serialize thành null. Nếu mapper dùng NON_NULL, nickname có thể bị bỏ qua. name là chuỗi rỗng, tags là array rỗng, active là false.

Kiểm tra:

~~~java
JsonNode tree = mapper.valueToTree(new Sample());

tree.path("name").isTextual();  // true
tree.path("name").textValue();  // ""

tree.path("tags").isArray();    // true
tree.path("tags").size();       // 0

tree.path("active").isBoolean(); // true
tree.path("active").booleanValue(); // false
~~~

Nếu nickname bị bỏ do inclusion, tree.path("nickname").isMissingNode() trả true. Nếu nickname được ghi thành null, isNull() trả true.

Đây là lý do không nên coi tree là bản sao field-by-field của Java object; tree phản ánh output policy.

## 16. Hiệu năng và bộ nhớ

Theo ý nghĩa API, valueToTree() tránh phải tạo một JSON String đầy đủ rồi parse lại String đó. Nó dùng biểu diễn token nội bộ của Jackson để chuyển đổi sang tree.

Tuy nhiên, phương thức vẫn phải tạo toàn bộ cây JsonNode trong bộ nhớ. Nếu input là một collection có hàng triệu phần tử, ArrayNode kết quả vẫn chứa toàn bộ cấu trúc.

So sánh:

| Cách | Bộ nhớ trung gian | Khi phù hợp |
|---|---|---|
| writeValueAsString() rồi readTree() | JSON String + tree | Khi cần cả JSON text |
| valueToTree() | Tree và buffer nội bộ trong quá trình chuyển | Khi cần tree, không cần String |
| JsonParser streaming | Token/buffer và phần dữ liệu đang xử lý | Khi dữ liệu rất lớn, không cần giữ toàn bộ tree |
| readTree(InputStream) | Toàn bộ tree | Khi cần truy cập ngẫu nhiên toàn document |

Nếu payload nhỏ hoặc vừa và cần chỉnh sửa linh hoạt, valueToTree() tiện lợi. Nếu dữ liệu rất lớn và chỉ cần xử lý từng record, dùng Streaming API để tránh giữ toàn bộ cây.

Không nên gọi valueToTree() lặp lại nhiều lần cho cùng một object nếu có thể tạo tree một lần rồi tái sử dụng trong phạm vi hợp lý.

## 17. Ngoại lệ và các trường hợp cần lưu ý

valueToTree() có thể thất bại nếu Jackson không thể serialize giá trị đầu vào thành representation JSON.

Các nguyên nhân thường gặp:

- Không có serializer cho kiểu dữ liệu.
- Custom serializer ném exception.
- Object graph có vòng tham chiếu không được xử lý.
- Getter ném exception khi được gọi.
- Lazy property cần persistence context đã đóng.
- Cấu hình serializer hoặc module không phù hợp.
- Giá trị không thể biểu diễn theo JSON contract.

Phương thức có thể ném IllegalArgumentException khi quá trình chuyển đổi không thành công; nguyên nhân gốc có thể nằm trong lỗi serialization được bọc bên trong. Khi xử lý, giữ cause để chẩn đoán thay vì chỉ log thông báo tổng quát.

Ví dụ:

~~~java
try {
    JsonNode tree = mapper.valueToTree(source);
    process(tree);
} catch (IllegalArgumentException ex) {
    throw new PayloadMappingException(
        "Could not convert source object to JSON tree",
        ex
    );
}
~~~

Không nên bắt lỗi rồi trả ObjectNode rỗng. Điều đó biến lỗi mapping thành payload có vẻ hợp lệ nhưng mất dữ liệu.

## 18. Bảo mật và dữ liệu nhạy cảm

valueToTree() dùng serialization configuration, vì vậy các field được Jackson cho phép xuất ra sẽ xuất hiện trong tree. Nếu tree được ghi log, lưu cache hoặc gửi sang hệ thống khác, dữ liệu nhạy cảm có thể bị lộ.

Ví dụ một User entity có passwordHash, accessToken hoặc internalNotes. Nếu các field này không bị ignore hoặc loại bằng DTO, chúng có thể xuất hiện trong tree.

Thực hành tốt:

- Chuyển DTO chỉ chứa field được phép công bố.
- Dùng @JsonIgnore hoặc view/filter khi có lý do và đã kiểm soát.
- Không log toàn bộ tree của request/response có dữ liệu nhạy cảm.
- Kiểm tra custom serializers và MixIn.
- Không coi valueToTree() là cơ chế masking hoặc authorization.
- Hạn chế dữ liệu trước khi chuyển thành tree nếu payload sẽ rời khỏi trust boundary.

Tree Model làm dữ liệu dễ quan sát và chỉnh sửa; điều đó cũng khiến việc vô tình ghi log hoặc chuyển tiếp field nhạy cảm dễ xảy ra hơn.

## 19. Kiểm thử valueToTree()

Nên kiểm tra cả node type, property name và value.

### 19.1. Test POJO thành ObjectNode

~~~java
@Test
void convertsPojoToObjectTree() {
    Customer customer = new Customer(
        10L,
        "An",
        "an@example.com"
    );

    JsonNode tree = mapper.valueToTree(customer);

    assertTrue(tree.isObject());
    assertEquals(10L, tree.path("id").asLong());
    assertEquals("An", tree.path("name").asText());
}
~~~

### 19.2. Test collection thành ArrayNode

~~~java
@Test
void convertsListToArrayTree() {
    List<String> values = List.of("A", "B");

    JsonNode tree = mapper.valueToTree(values);

    assertTrue(tree.isArray());
    assertEquals(2, tree.size());
    assertEquals("A", tree.get(0).asText());
}
~~~

### 19.3. Test String chứa JSON vẫn là TextNode

~~~java
@Test
void treatsJsonLookingStringAsTextValue() {
    String rawJson = "{\"id\":10}";

    JsonNode tree = mapper.valueToTree(rawJson);

    assertTrue(tree.isTextual());
    assertEquals(rawJson, tree.textValue());
}
~~~

### 19.4. Test readTree parse nội dung JSON

~~~java
@Test
void readTreeParsesJsonText() throws Exception {
    String rawJson = "{\"id\":10}";

    JsonNode tree = mapper.readTree(rawJson);

    assertTrue(tree.isObject());
    assertEquals(10, tree.path("id").asInt());
}
~~~

### 19.5. Test null thành NullNode

~~~java
@Test
void convertsNullToNullNode() {
    JsonNode tree = mapper.valueToTree(null);

    assertNotNull(tree);
    assertTrue(tree.isNull());
}
~~~

### 19.6. Test mapper configuration được áp dụng

Nếu DTO dùng @JsonProperty, @JsonInclude hoặc custom serializer, hãy assert tree có đúng tên và shape theo hợp đồng.

Ví dụ:

~~~java
@Test
void appliesJsonPropertyName() {
    User user = new User();
    user.setDisplayName("An");

    JsonNode tree = mapper.valueToTree(user);

    assertTrue(tree.has("display_name"));
    assertFalse(tree.has("displayName"));
}
~~~

Các test nên chạy với đúng ObjectMapper được ứng dụng cấu hình, không phải một mapper test tự tạo khác với production.

## 20. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng valueToTree() để parse JSON String | Nhầm Java String với JSON source | Dùng readTree() |
| Ép mọi kết quả thành ObjectNode | Input có thể là scalar hoặc array | Nhận JsonNode rồi kiểm tra isObject()/isArray() |
| Nghĩ tree chứa mọi field Java | Ignore, inclusion và serializer đã biến đổi output | Kiểm tra serialization configuration |
| Dùng valueToTree() để clone object | Tree không bảo toàn mọi runtime state/identity | Dùng copy strategy phù hợp |
| Chuyển object lớn thành tree rồi giữ lâu | Toàn bộ JsonNode tree nằm trong RAM | Dùng streaming nếu không cần toàn bộ tree |
| Dùng valueToTree() để đổi DTO này sang DTO khác | Tạo bước tree không cần thiết | Dùng convertValue() |
| Gọi readTree() cho object Java | Nhầm API nguồn vào | Dùng valueToTree() |
| Bỏ qua custom serializer/module | Tree output khác mong đợi | Tái sử dụng mapper đã cấu hình |
| Coi missing và null giống nhau | Inclusion có thể bỏ field hoặc ghi NullNode | Kiểm tra has(), isMissingNode(), isNull() |
| Ghi đè field metadata không kiểm soát | Tên field có thể đã tồn tại | Kiểm tra collision hoặc dùng envelope |
| Log toàn bộ tree | Có thể lộ dữ liệu nhạy cảm | Dùng DTO an toàn và log field chọn lọc |

## 21. Quy trình sử dụng valueToTree()

1. Xác định đầu vào là Java value hay JSON text.
2. Nếu là Java object, Map, collection hoặc scalar, dùng valueToTree().
3. Nếu là JSON String/InputStream cần parse, dùng readTree().
4. Tái sử dụng ObjectMapper đã đăng ký module và cấu hình cần thiết.
5. Nhận kết quả bằng JsonNode nếu chưa chắc root type.
6. Kiểm tra isObject(), isArray() hoặc node type trước khi thao tác.
7. Dùng ObjectNode/ArrayNode để thêm, sửa hoặc xóa property khi cần.
8. Kiểm tra collision trước khi gắn metadata.
9. Chuyển lại bằng treeToValue() hoặc convertValue() nếu cần DTO.
10. Không dùng tree conversion như deep clone hoặc schema validation.
11. Đặt giới hạn bộ nhớ và chọn streaming cho dữ liệu lớn.
12. Kiểm thử JSON representation thực tế và các annotation/configuration có ảnh hưởng.

## 22. Nguyên tắc nên giữ

- valueToTree() chuyển Java value thành JsonNode.
- POJO/Map thường tạo ObjectNode; List/array tạo ArrayNode; scalar tạo value node.
- Input null tạo NullNode, không phải Java null.
- String trông giống JSON vẫn là TextNode; dùng readTree() để parse nội dung JSON.
- Kết quả phản ánh serializer, annotation, module và mapper configuration.
- Không giả định tree chứa mọi field hoặc giữ nguyên object identity.
- Kiểm tra node type trước khi ép kiểu hoặc sửa tree.
- Dùng ObjectNode.set()/put()/remove() để chỉnh sửa có chủ đích.
- Dùng deepCopy() khi cần bản sao tree độc lập.
- Dùng convertValue() nếu mục tiêu là một Java type khác.
- Dùng Streaming API khi không cần giữ toàn bộ payload trong bộ nhớ.
- Không xem valueToTree() là validation, authorization hoặc masking.
- Kiểm thử output literal và các trường hợp null, empty, custom serializer.

valueToTree() là cầu nối thuận tiện giữa mô hình Java có kiểu và Jackson Tree Model. Nó cho phép chuyển POJO, Map, collection hoặc scalar thành JsonNode theo đúng serialization policy của ứng dụng, rồi tiếp tục thao tác trên cây mà không cần tạo JSON String trung gian. Khi phân biệt rõ valueToTree() với readTree() và convertValue(), kiểm tra kiểu root, hiểu tác động của mapper configuration và giới hạn bộ nhớ, ứng dụng có thể xử lý payload động rõ ràng và an toàn hơn.

