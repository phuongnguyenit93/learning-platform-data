# Lựa chọn cây dữ liệu khi cấu trúc đầu vào chưa cố định

Không phải mọi JSON đều có cấu trúc cố định để ánh xạ trực tiếp vào một DTO. Có API trả về các field khác nhau theo loại sự kiện, message broker chứa metadata do producer tự mở rộng, webhook có payload thay đổi theo phiên bản hoặc một phần dữ liệu chỉ được xác định sau khi đọc discriminator. Trong những trường hợp này, việc tạo một class Java cho mọi biến thể có thể làm mô hình trở nên cồng kềnh và dễ vỡ.

Jackson cung cấp **tree model** với lớp nền `JsonNode`. Thay vì yêu cầu một kiểu Java cố định ngay từ đầu, ứng dụng đọc JSON thành một cây node, kiểm tra cấu trúc thực tế rồi quyết định cách xử lý từng nhánh. Tree model cho phép duyệt, kiểm tra, thêm, sửa và xóa node; khi một nhánh đã có cấu trúc rõ ràng, có thể chuyển riêng nhánh đó thành DTO.

Lựa chọn tree model phù hợp khi cấu trúc JSON thay đổi hoặc chỉ biết một phần. Tuy nhiên, cây vẫn được giữ trong bộ nhớ và không tự xác thực quy tắc nghiệp vụ. Cần chọn giữa DTO, `Map<String, Object>`, `JsonNode` và streaming theo mức độ cố định của schema, kích thước payload và kiểu xử lý cần thực hiện.

## 1. Khi nào cấu trúc JSON chưa cố định?

Một payload có thể chưa cố định theo nhiều cách:

- **Field tùy chọn:** các phiên bản producer khác nhau gửi những tập thuộc tính khác nhau.
- **Field mở rộng:** một object có phần lõi ổn định và một nhóm key do từng khách hàng hoặc plugin tự định nghĩa.
- **Kiểu node thay đổi:** một field có thể là object ở một trường hợp, array hoặc scalar ở trường hợp khác.
- **Schema phụ thuộc loại sự kiện:** key `type` quyết định cấu trúc của phần `data`.
- **Payload từ bên ngoài:** webhook hoặc message từ đối tác có thể bổ sung field mới mà ứng dụng chưa biết.
- **Chỉ cần một phần dữ liệu:** ứng dụng chỉ quan tâm vài field, không cần model hóa toàn bộ JSON.

Ví dụ hai message cùng có các field chung nhưng phần `data` khác nhau:

```json
{
  "eventType": "user.created",
  "eventId": "evt-100",
  "data": {
    "userId": 42,
    "displayName": "An"
  }
}
```

```json
{
  "eventType": "invoice.paid",
  "eventId": "evt-101",
  "data": {
    "invoiceId": "INV-900",
    "amount": 125000.50,
    "currency": "VND",
    "payment": {
      "method": "bank_transfer",
      "reference": "TX-88"
    }
  }
}
```

Nếu chỉ có một class `Event` với field `data` kiểu `Object`, phần dữ liệu bên trong thường trở thành map và các kiểu lồng nhau không được thể hiện rõ. Nếu tạo một DTO riêng cho từng event type, cần biết loại sự kiện trước khi deserialize. Tree model cho phép đọc envelope chung trước, sau đó chọn cách xử lý nhánh `data`.

## 2. Các lựa chọn biểu diễn JSON trong Jackson

Jackson có nhiều cách để làm việc với JSON động. Không có một lựa chọn phù hợp cho mọi trường hợp.

| Cách biểu diễn | Kiểu/API | Điểm mạnh | Giới hạn chính |
|---|---|---|---|
| DTO/POJO | Class Java, `ObjectMapper` | Kiểu tĩnh, dễ kiểm tra, validation và refactor | Cần schema tương đối ổn định |
| Map | `Map<String, Object>` | Dễ truy cập key động, gần với cấu trúc object JSON | Kiểu lồng nhau yếu, cần ép kiểu và kiểm tra thủ công |
| Tree model | `JsonNode`, `ObjectNode`, `ArrayNode` | Giữ cấu trúc JSON, phân biệt object/array/scalar/null, dễ duyệt và sửa | Giữ toàn bộ cây trong bộ nhớ, thao tác runtime |
| Streaming | `JsonParser`, `JsonGenerator` | Xử lý tuần tự, ít bộ nhớ, phù hợp dữ liệu lớn | Code điều khiển token phức tạp hơn |

### 2.1. Dùng DTO khi schema đã rõ

Nếu API có hợp đồng ổn định, DTO thường là lựa chọn tốt nhất:

```java
public class UserCreatedData {
    private long userId;
    private String displayName;

    // Getter/setter
}

UserCreatedData data =
        mapper.readValue(json, UserCreatedData.class);
```

Kiểu tĩnh giúp compiler hỗ trợ, IDE điều hướng tốt và Bean Validation có thể kiểm tra field. DTO cũng là nơi phù hợp để thể hiện quy tắc bắt buộc, naming và chuyển đổi kiểu.

### 2.2. Dùng Map khi cấu trúc là object key/value đơn giản

Nếu payload chỉ là object phẳng với các key động, có thể đọc thành map:

```java
Map<String, Object> attributes = mapper.readValue(
        json,
        new TypeReference<Map<String, Object>>() {}
);
```

Cách này thuận tiện cho metadata đơn giản. Nhưng với object lồng nhau, code phải liên tục kiểm tra `instanceof Map`, `List`, `Number` và ép kiểu. Một key có thể mang kiểu khác giữa các message, khiến lỗi xuất hiện ở runtime.

### 2.3. Dùng JsonNode khi cần khảo sát cấu trúc thực tế

Tree model giữ node theo đúng hình dạng JSON. Có thể kiểm tra một field là object, array, text, number, boolean hay null trước khi quyết định bước tiếp theo:

```java
JsonNode root = mapper.readTree(json);

JsonNode data = root.path("data");
if (data.isObject()) {
    // Xử lý object
} else if (data.isArray()) {
    // Xử lý array
} else if (data.isValueNode()) {
    // Xử lý scalar hoặc null
}
```

Cách này phù hợp khi ứng dụng cần thích nghi với nhiều biến thể nhưng vẫn muốn giữ cấu trúc lồng nhau rõ ràng.

## 3. JsonNode và các loại node

`JsonNode` là lớp trừu tượng đại diện cho một node trong cây JSON. Jackson cung cấp các lớp con tương ứng với những dạng giá trị JSON.

| Dạng JSON | Loại node tiêu biểu | Ví dụ |
|---|---|---|
| Object | `ObjectNode` | `{"id":1,"name":"An"}` |
| Array | `ArrayNode` | `[1,2,3]` |
| String | `TextNode` | `"An"` |
| Integer | `IntNode`, `LongNode`, `BigIntegerNode` | `42` |
| Decimal | `DoubleNode`, `DecimalNode` | `12.50` |
| Boolean | `BooleanNode` | `true` |
| JSON null | `NullNode` | `null` |
| Field không tồn tại khi truy cập bằng `path` | `MissingNode` | Không có node tương ứng |

Các kiểu node số cụ thể phụ thuộc giá trị token, node factory và cấu hình Jackson. Nếu độ chính xác số là yêu cầu quan trọng, không nên chỉ dựa vào tên kiểu `JsonNode`; hãy kiểm tra cách parser tạo node và đọc số bằng API chính xác phù hợp.

### 3.1. Đọc JSON thành cây

Cách đơn giản nhất:

```java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree(json);
```

`readTree` có thể đọc từ `String`, `byte[]`, `InputStream`, `Reader` và các nguồn mà mapper hỗ trợ. Kết quả là node gốc của cây.

Với JSON object, root thường là `ObjectNode`; với JSON array, root là `ArrayNode`; với JSON scalar, root có thể là một value node.

Đừng giả định root luôn là object. Nếu API có thể trả về array hoặc scalar, hãy kiểm tra trước khi gọi các thao tác dành riêng cho object:

```java
if (root == null || root.isNull()) {
    throw new IllegalArgumentException("JSON root không có giá trị");
}

if (!root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}
```

### 3.2. Phân biệt object, array và scalar

Một số phương thức kiểm tra hình dạng node:

```java
root.isObject();
root.isArray();
root.isTextual();
root.isNumber();
root.isBoolean();
root.isNull();
root.isValueNode();
root.isContainerNode();
```

- `isContainerNode()` trả về true cho object và array.
- `isValueNode()` nhận diện các node giá trị như string, number, boolean và null.
- `isNumber()` cho biết node thuộc nhóm số; cần kiểm tra thêm kiểu số nếu muốn xử lý integer và decimal khác nhau.

Ví dụ:

```java
if (root.isObject()) {
    JsonNode type = root.get("eventType");
    // Đọc envelope object
} else if (root.isArray()) {
    // Duyệt từng phần tử
} else {
    // Xử lý root scalar theo hợp đồng
}
```

## 4. Truy cập field và khác biệt giữa missing với null

Một điểm quan trọng của tree model là phân biệt key không tồn tại với key tồn tại nhưng mang JSON null.

Xét hai JSON:

```json
{
  "name": "An"
}
```

```json
{
  "name": "An",
  "phone": null
}
```

Trong JSON đầu tiên, field `phone` bị thiếu. Trong JSON thứ hai, field `phone` có mặt và giá trị của nó là null. Hai trạng thái có thể mang ý nghĩa nghiệp vụ khác nhau, đặc biệt trong API cập nhật từng phần.

### 4.1. get() và path()

`get(String)` trả về Java `null` nếu field không tồn tại. Nếu field tồn tại với JSON null, nó trả về `NullNode`.

```java
JsonNode phone = root.get("phone");

if (phone == null) {
    // Field không tồn tại
} else if (phone.isNull()) {
    // Field có mặt và mang JSON null
} else {
    // Có giá trị
}
```

`path(String)` không trả Java null khi field không tồn tại; nó trả `MissingNode`:

```java
JsonNode phone = root.path("phone");

if (phone.isMissingNode()) {
    // Field không tồn tại
} else if (phone.isNull()) {
    // Field có mặt và mang JSON null
} else {
    // Có giá trị
}
```

`path()` hữu ích khi duyệt đường dẫn nhiều tầng vì có thể gọi tiếp `path()` trên node thiếu mà không phát sinh NullPointerException:

```java
String city = root
        .path("customer")
        .path("address")
        .path("city")
        .asText("");
```

Tuy nhiên, nếu cần phân biệt thiếu với null, đừng chỉ lấy giá trị bằng `asText("")`; hãy kiểm tra node trước.

### 4.2. has(), hasNonNull() và isMissingNode()

Các phương thức thường dùng:

```java
root.has("phone");
root.hasNonNull("phone");
root.path("phone").isMissingNode();
root.path("phone").isNull();
```

| JSON | `has("phone")` | `hasNonNull("phone")` | `path("phone").isMissingNode()` | `path("phone").isNull()` |
|---|---:|---:|---:|---:|
| `{}` | false | false | true | false |
| `{"phone":null}` | true | false | false | true |
| `{"phone":"123"}` | true | true | false | false |

Dùng `has()` khi chỉ cần biết key có xuất hiện hay không. Dùng `hasNonNull()` khi cần biết key có giá trị khác null. Dùng `isMissingNode()` để kiểm tra kết quả truy cập bằng `path()`.

### 4.3. Giá trị mặc định của asText/asInt/asLong

Các phương thức như `asText()`, `asInt()`, `asLong()` có thể trả về giá trị mặc định khi node không chuyển đổi được. Ví dụ:

```java
int quantity = root.path("quantity").asInt(0);
```

Code trên tiện khi hợp đồng cho phép thiếu hoặc sai kiểu được xem là 0. Nhưng nếu `quantity` là trường bắt buộc, cách này có thể che giấu lỗi dữ liệu. Nên kiểm tra rõ:

```java
JsonNode quantityNode = root.get("quantity");

if (quantityNode == null || !quantityNode.isIntegralNumber()
        || !quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException(
            "quantity phải là số nguyên trong miền int"
    );
}

int quantity = quantityNode.intValue();
```

Đối với số nguyên lớn, dùng `bigIntegerValue()`; với số thập phân chính xác, dùng `decimalValue()` sau khi bảo đảm node được tạo và lưu theo độ chính xác mong muốn.

## 5. Duyệt object và array

### 5.1. Duyệt các field của object

Có thể duyệt từng cặp tên field và node:

```java
Iterator<Map.Entry<String, JsonNode>> fields = root.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> entry = fields.next();

    String fieldName = entry.getKey();
    JsonNode value = entry.getValue();

    System.out.println(fieldName + " -> " + value);
}
```

Hoặc dùng vòng lặp enhanced for:

```java
for (Map.Entry<String, JsonNode> entry : root.properties()) {
    // API properties() có trên các phiên bản Jackson mới hơn;
    // fields() tương thích rộng hơn trong Jackson 2.x.
}
```

Trong code cần tương thích nhiều phiên bản Jackson 2.x, `fields()` là lựa chọn quen thuộc. Chỉ gọi `fields()` khi node là object; nếu node là array hoặc scalar, cần kiểm tra hình dạng trước.

### 5.2. Duyệt phần tử array

```java
JsonNode items = root.path("items");

if (items.isArray()) {
    for (JsonNode item : items) {
        System.out.println(item.path("id").asText());
    }
}
```

Có thể truy cập theo index:

```java
JsonNode first = items.get(0);
```

Nếu index không tồn tại, `get(index)` trả Java null. Dùng `path(index)` nếu muốn nhận `MissingNode` để kiểm tra theo cùng một cách.

### 5.3. Duyệt đệ quy cây JSON

Khi cấu trúc lồng nhau chưa biết trước, có thể viết hàm đệ quy để thăm từng node:

```java
void visit(JsonNode node, String path) {
    if (node.isObject()) {
        Iterator<Map.Entry<String, JsonNode>> fields = node.fields();

        while (fields.hasNext()) {
            Map.Entry<String, JsonNode> field = fields.next();
            visit(field.getValue(), path + "/" + field.getKey());
        }
    } else if (node.isArray()) {
        for (int i = 0; i < node.size(); i++) {
            visit(node.get(i), path + "/" + i);
        }
    } else {
        System.out.println(path + " = " + node);
    }
}
```

Đây là nền tảng cho các công cụ log cấu trúc, lọc field, kiểm tra dữ liệu tổng quát hoặc chuyển đổi payload. Với dữ liệu không tin cậy, cần giới hạn độ sâu lồng nhau và kích thước node để tránh đệ quy quá sâu hoặc tốn tài nguyên.

## 6. Truy cập theo JSON Pointer

Khi cần lấy một nhánh sâu, có thể dùng JSON Pointer với phương thức `at()`:

```java
JsonNode city = root.at("/customer/address/city");
JsonNode firstItem = root.at("/items/0");
```

JSON Pointer bắt đầu bằng dấu `/` và phân tách từng token bằng dấu `/`. Các ký tự đặc biệt trong tên key được escape theo quy tắc JSON Pointer: `~1` đại diện cho `/`, `~0` đại diện cho `~`.

Ví dụ key có dấu slash:

```json
{
  "metadata": {
    "source/name": "partner-a"
  }
}
```

Pointer tương ứng:

```java
JsonNode source = root.at("/metadata/source~1name");
```

Nếu đường dẫn không tồn tại, `at()` trả `MissingNode`, không phải Java null. Có thể kiểm tra:

```java
JsonNode value = root.at("/customer/address/city");

if (value.isMissingNode()) {
    // Đường dẫn không tồn tại
}
```

JSON Pointer hữu ích khi đường dẫn được cấu hình từ bên ngoài hoặc cần đọc một nhánh sâu mà không viết nhiều chuỗi `path()`.

## 7. Xử lý envelope chung và payload động

Một pattern phổ biến là envelope có các field chung và payload phụ thuộc event type.

```json
{
  "eventType": "user.created",
  "eventId": "evt-100",
  "occurredAt": "2025-01-01T00:00:00Z",
  "data": {
    "userId": 42,
    "displayName": "An"
  }
}
```

Có thể đọc toàn bộ cây, lấy metadata chung, rồi chuyển riêng `data` thành DTO tương ứng:

```java
JsonNode root = mapper.readTree(json);

String eventType = root.path("eventType").asText(null);
String eventId = root.path("eventId").asText(null);
JsonNode dataNode = root.path("data");

if (eventType == null || dataNode.isMissingNode() || dataNode.isNull()) {
    throw new IllegalArgumentException("Event thiếu eventType hoặc data");
}

switch (eventType) {
    case "user.created" -> {
        UserCreatedData data =
                mapper.treeToValue(dataNode, UserCreatedData.class);
        handleUserCreated(eventId, data);
    }
    case "invoice.paid" -> {
        InvoicePaidData data =
                mapper.treeToValue(dataNode, InvoicePaidData.class);
        handleInvoicePaid(eventId, data);
    }
    default -> handleUnknownEvent(eventType, eventId, dataNode);
}
```

Lợi ích của cách làm này:

- Envelope được xử lý một lần.
- Mỗi loại payload chỉ cần DTO khi schema đã biết.
- Event type mới có thể được lưu trữ, chuyển tiếp hoặc bỏ qua theo chính sách mà không phải sửa toàn bộ model.
- Ứng dụng có thể kiểm tra discriminator trước khi chọn kiểu đích.

Không nên chuyển payload thành class dựa trên tên class tùy ý do JSON cung cấp. Hãy dùng allowlist rõ ràng như switch hoặc registry có kiểm soát để tránh cho dữ liệu ngoài quyết định kiểu Java cần khởi tạo.

## 8. Kết hợp phần cố định với phần động

Không phải toàn bộ payload đều phải dùng tree model. Một lựa chọn cân bằng là dùng DTO cho phần ổn định và `JsonNode` hoặc `Map` cho phần mở rộng.

### 8.1. DTO có phần mở rộng JsonNode

```java
public class PartnerMessage {
    private String partnerId;
    private String messageType;
    private JsonNode attributes;

    // Getter/setter
}
```

Jackson ánh xạ hai field đầu thành kiểu tĩnh, còn `attributes` giữ nguyên cây JSON động.

Cách này phù hợp khi envelope ổn định nhưng schema phần mở rộng do từng đối tác định nghĩa.

### 8.2. Dùng @JsonAnySetter để thu thập field chưa biết

Nếu các field mở rộng nằm cùng cấp với field cố định, có thể dùng `@JsonAnySetter`:

```java
public class PartnerMessage {
    private String partnerId;
    private final Map<String, JsonNode> extra = new LinkedHashMap<>();

    public String getPartnerId() {
        return partnerId;
    }

    public void setPartnerId(String partnerId) {
        this.partnerId = partnerId;
    }

    @JsonAnySetter
    public void addExtra(String name, JsonNode value) {
        extra.put(name, value);
    }

    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
```

Các property đã biết được gán vào field tương ứng; property còn lại được chuyển vào map `extra`. Dùng `JsonNode` làm value giúp giữ cấu trúc lồng nhau tốt hơn `Object` nếu ứng dụng cần tiếp tục duyệt hoặc chuyển đổi node.

### 8.3. Giữ lại field lạ khi cần round-trip

Nếu ứng dụng đọc message, sửa một vài field đã biết rồi ghi lại, tree model giúp giữ những field chưa biết mà DTO thuần có thể bỏ qua:

```java
ObjectNode root = (ObjectNode) mapper.readTree(json);

root.put("processed", true);
root.put("processedAt", Instant.now().toString());

String output = mapper.writeValueAsString(root);
```

Vì cây gốc vẫn chứa các field khác, chúng được giữ khi serialize lại, trừ những field ứng dụng chủ động xóa hoặc thay đổi.

Nếu dùng DTO, có thể lưu field lạ qua `@JsonAnySetter` và phát lại qua `@JsonAnyGetter`, hoặc giữ một node mở rộng riêng.

## 9. Chuyển một nhánh JsonNode thành POJO

Tree model không buộc ứng dụng ở lại dạng node mãi mãi. Khi đã nhận diện được cấu trúc, có thể chuyển một nhánh sang DTO.

### 9.1. treeToValue()

```java
JsonNode customerNode = root.path("customer");

Customer customer = mapper.treeToValue(
        customerNode,
        Customer.class
);
```

`treeToValue()` diễn giải node thành kiểu đích và ném lỗi mapping nếu cấu trúc không tương thích.

### 9.2. convertValue()

`convertValue()` chuyển đổi giữa object và kiểu khác thông qua cơ chế databinding nội bộ:

```java
Customer customer = mapper.convertValue(
        root.path("customer"),
        Customer.class
);
```

Có thể dùng nó để chuyển map thành DTO, DTO thành map hoặc node thành kiểu đích. Nó tiện cho chuyển đổi trong bộ nhớ, nhưng không nên xem như một vòng serialize JSON ra chuỗi rồi parse lại. Các khác biệt về custom serializer/deserializer hoặc kiểu đặc biệt có thể ảnh hưởng kết quả.

### 9.3. valueToTree()

Chiều ngược lại, chuyển một object Java thành cây JSON:

```java
Customer customer = loadCustomer();

JsonNode customerTree = mapper.valueToTree(customer);
```

Sau đó có thể kiểm tra hoặc ghép vào một object khác:

```java
ObjectNode envelope = mapper.createObjectNode();
envelope.put("eventType", "customer.snapshot");
envelope.set("data", customerTree);
```

### 9.4. Kiểm tra trước khi chuyển đổi

Không nên gọi `treeToValue()` trên node thiếu hoặc null nếu hợp đồng yêu cầu object:

```java
JsonNode data = root.path("data");

if (data.isMissingNode() || data.isNull() || !data.isObject()) {
    throw new IllegalArgumentException("data phải là JSON object");
}

UserCreatedData eventData =
        mapper.treeToValue(data, UserCreatedData.class);
```

Kiểm tra hình dạng node trước giúp thông báo lỗi ở đúng ranh giới dữ liệu, thay vì để lỗi chuyển đổi sâu hơn trở nên khó hiểu.

## 10. Tạo và chỉnh sửa cây JSON

Jackson cho phép tạo node mà không cần parse chuỗi JSON.

### 10.1. Tạo ObjectNode và ArrayNode

```java
ObjectNode root = mapper.createObjectNode();

root.put("eventType", "user.created");
root.put("eventId", "evt-200");
root.put("active", true);
root.putNull("optionalNote");

ArrayNode roles = root.putArray("roles");
roles.add("reader");
roles.add("admin");
```

Các phương thức `put()` tạo scalar property; `putNull()` ghi JSON null; `putArray()` tạo array và trả về node để thêm phần tử.

### 10.2. Thêm node lồng nhau

```java
ObjectNode customer = root.putObject("customer");
customer.put("id", 42);
customer.put("name", "An");

ObjectNode address = customer.putObject("address");
address.put("city", "Ho Chi Minh City");
address.put("country", "VN");
```

Kết quả là object lồng nhau. Không cần tự ghép dấu ngoặc hay escape chuỗi.

### 10.3. Sửa, thay thế và xóa field

```java
ObjectNode object = (ObjectNode) mapper.readTree(json);

object.put("status", "processed");
object.put("attempt", 2);
object.remove("temporaryToken");
```

Để thay một node bằng node khác:

```java
object.set("metadata", mapper.createObjectNode()
        .put("source", "batch-import"));
```

`set()` nhận node; `put()` phù hợp với các giá trị scalar như string, boolean và number.

### 10.4. Sao chép node trước khi sửa

Một node có thể được gắn vào cây khác. Nếu cần chỉnh sửa bản sao mà không ảnh hưởng cây nguồn, dùng `deepCopy()`:

```java
ObjectNode original = (ObjectNode) mapper.readTree(json);
ObjectNode copy = original.deepCopy();

copy.put("status", "reviewed");
```

Nếu chỉ gán cùng một node vào hai cấu trúc, cả hai biến có thể cùng tham chiếu đến một object node. Hãy dùng deep copy khi cần hai cây độc lập.

## 11. Xử lý kiểu dữ liệu và giá trị không mong đợi

Cấu trúc động đồng nghĩa với việc ứng dụng phải kiểm tra kiểu node trước khi đọc.

### 11.1. Không ép kiểu chỉ dựa vào tên field

Ví dụ API thường gửi `quantity` là number, nhưng một producer lỗi gửi string:

```json
{
  "quantity": "ten"
}
```

Không nên mặc định gọi `asInt()` và chấp nhận 0 nếu không chuyển đổi được. Hãy kiểm tra:

```java
JsonNode quantity = root.path("quantity");

if (!quantity.isIntegralNumber() || !quantity.canConvertToInt()) {
    throw new IllegalArgumentException("quantity phải là số nguyên hợp lệ");
}

int value = quantity.intValue();
```

Nếu chấp nhận cả integer JSON và chuỗi số, hãy định nghĩa rõ quy tắc chuyển đổi và báo lỗi khi chuỗi không hợp lệ.

### 11.2. Bảo toàn số nguyên lớn

Với node số nguyên:

```java
JsonNode idNode = root.path("id");

if (!idNode.isIntegralNumber()) {
    throw new IllegalArgumentException("id phải là số nguyên");
}

BigInteger id = idNode.bigIntegerValue();
```

Nếu cần bảo đảm giá trị nằm trong miền long, kiểm tra trước khi gọi `longValueExact()` trên BigInteger:

```java
long idAsLong = id.longValueExact();
```

Nếu node được tạo thành kiểu số dấu phẩy động, không thể khôi phục những chữ số đã mất do làm tròn. Khi cần số nguyên lớn chính xác, hãy đọc trực tiếp vào `BigInteger` hoặc bảo đảm tree model tạo integer node chính xác.

### 11.3. Số thập phân và BigDecimal

Với field tiền hoặc số thập phân cần chính xác:

```java
JsonNode amountNode = root.path("amount");

if (!amountNode.isNumber()) {
    throw new IllegalArgumentException("amount phải là number");
}

BigDecimal amount = amountNode.decimalValue();
```

Cần nhớ `decimalValue()` chuyển node hiện tại sang BigDecimal; nếu node trước đó đã được lưu dưới dạng double, sai số double có thể đã xuất hiện. Nếu cần bảo toàn chính xác token decimal, hãy cấu hình cách tạo node phù hợp với phiên bản Jackson hoặc deserialize trực tiếp property thành `BigDecimal`.

### 11.4. Không đồng nhất null, empty và missing

Ba giá trị sau khác nhau:

- Field không tồn tại: `MissingNode` khi dùng `path()`.
- Field tồn tại với JSON null: `NullNode`.
- Field tồn tại với chuỗi rỗng: `TextNode("")`.

Một API PATCH có thể quy định missing là không thay đổi, null là xóa và empty string là đặt giá trị rỗng. Cần giữ nguyên sự khác biệt này trong logic xử lý.

## 12. JsonNode và JSON Pointer trong kiểm tra schema linh hoạt

Khi cấu trúc không cố định, có thể định nghĩa các đường dẫn quan tâm thay vì viết một DTO khổng lồ.

Ví dụ một cấu hình mapping:

```java
List<String> requiredPaths = List.of(
        "/eventId",
        "/data/customer/id"
);

for (String pointer : requiredPaths) {
    JsonNode value = root.at(pointer);

    if (value.isMissingNode() || value.isNull()) {
        throw new IllegalArgumentException(
                "Thiếu dữ liệu bắt buộc tại " + pointer
        );
    }
}
```

Sau đó kiểm tra kiểu từng node:

```java
JsonNode eventId = root.at("/eventId");
if (!eventId.isTextual() || eventId.textValue().isBlank()) {
    throw new IllegalArgumentException("eventId phải là chuỗi không rỗng");
}
```

Cách này có thể hữu ích khi xây dựng một bộ kiểm tra payload tổng quát. Tuy nhiên, nó không thay thế JSON Schema validator nếu cần kiểm tra schema phức tạp như union type, pattern, giới hạn số, cấu trúc array hoặc tham chiếu schema. Tree model chỉ cung cấp cấu trúc để ứng dụng kiểm tra.

## 13. Lựa chọn tree model hay streaming cho payload lớn

Tree model cần tạo node cho toàn bộ JSON. Với payload nhỏ và trung bình, sự tiện lợi thường đáng giá. Với file hàng trăm MB hoặc stream chứa hàng triệu record, giữ toàn bộ cây có thể tốn nhiều heap.

Ví dụ tree model:

```java
JsonNode root = mapper.readTree(inputStream);
// Toàn bộ cây được giữ trong bộ nhớ
process(root);
```

Nếu chỉ cần xử lý từng phần tử trong mảng, streaming có thể phù hợp hơn:

```java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        JsonNode item = mapper.readTree(parser);
        process(item);
    }
}
```

Ví dụ này đọc một object tại một thời điểm thành tree node rồi xử lý và giải phóng tham chiếu trước khi đọc phần tử tiếp theo. Như vậy, ứng dụng chỉ giữ một phần tử tree thay vì toàn bộ array. Nếu cấu trúc từng phần tử đã ổn định, có thể bind trực tiếp:

```java
try (JsonParser parser = mapper.getFactory().createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        EventRecord record = mapper.readValue(parser, EventRecord.class);
        process(record);
    }
}
```

| Tiêu chí | Tree model toàn bộ | Streaming từng phần |
|---|---|---|
| Schema | Có thể thay đổi mạnh | Có thể thay đổi, nhưng phải xử lý token thủ công hoặc tạo tree nhỏ |
| Bộ nhớ | Tỷ lệ với toàn bộ cây | Có thể giới hạn theo phần đang xử lý |
| Duyệt ngược/tra cứu nhiều lần | Thuận tiện | Khó hơn vì stream tiến về phía trước |
| Chỉnh sửa cấu trúc | Dễ | Cần ghi token tương ứng |
| Code | Thường ngắn và trực quan | Nhiều trạng thái parser/generator hơn |
| Phù hợp | Payload vừa phải, cần khảo sát/chỉnh sửa | File lớn, luồng liên tục, xử lý tuần tự |

Một lựa chọn trung gian là streaming envelope và chỉ tạo tree cho nhánh payload cần xử lý. Điều này cân bằng giữa khả năng linh hoạt và bộ nhớ.

## 14. An toàn khi xử lý JSON động

Payload linh hoạt không đồng nghĩa với payload được phép tùy ý. Một số nguyên tắc quan trọng:

- **Giới hạn kích thước đầu vào:** không đọc tree vô hạn từ nguồn bên ngoài.
- **Giới hạn độ sâu và kích thước token:** cấu hình parser constraints theo phiên bản Jackson.
- **Không tạo class tùy ý từ dữ liệu:** dùng discriminator và registry subtype allowlist.
- **Kiểm tra node type trước khi ép kiểu:** tránh giá trị mặc định che giấu dữ liệu sai.
- **Xác thực field quan trọng:** tree model không tự bảo đảm field bắt buộc hoặc miền giá trị.
- **Không log toàn bộ payload nhạy cảm:** tree có thể chứa token, thông tin cá nhân hoặc dữ liệu thanh toán.
- **Giữ quy tắc tương thích rõ ràng:** quyết định field lạ được giữ, bỏ qua, lưu lại hay từ chối.

Nếu dùng tree model để chuyển tiếp payload không hiểu hết, cần cẩn thận khi ghi lại: ứng dụng có thể vô tình phát lại field nội bộ hoặc thông tin nhạy cảm. Hãy lọc field theo allowlist nếu payload được chuyển sang một trust boundary khác.

## 15. Ví dụ tổng hợp: webhook có schema thay đổi

Giả sử một webhook gửi envelope chung, còn `payload` thay đổi theo loại sự kiện và có thể chứa field mở rộng:

```json
{
  "id": "wh-300",
  "type": "order.shipped",
  "payload": {
    "orderId": "ORD-900",
    "carrier": "VNPost",
    "tracking": {
      "code": "TRK-123",
      "url": "https://example.test/track/TRK-123"
    },
    "partnerData": {
      "warehouse": "HCM-1",
      "route": ["HCM", "BD"]
    }
  }
}
```

Có thể đọc envelope và chuyển phần payload đã biết thành DTO:

```java
public class OrderShippedData {
    private String orderId;
    private String carrier;
    private Tracking tracking;

    // Getter/setter
}

public class Tracking {
    private String code;
    private String url;

    // Getter/setter
}
```

Xử lý:

```java
JsonNode root = mapper.readTree(webhookBody);

String id = requireText(root, "id");
String type = requireText(root, "type");
JsonNode payload = root.path("payload");

if (!payload.isObject()) {
    throw new IllegalArgumentException("payload phải là object");
}

switch (type) {
    case "order.shipped" -> {
        OrderShippedData data =
                mapper.treeToValue(payload, OrderShippedData.class);

        JsonNode partnerData = payload.path("partnerData");
        storePartnerMetadata(id, partnerData);

        handleShipped(data);
    }
    default -> storeUnknownWebhook(id, type, payload);
}
```

Hàm đọc field bắt buộc:

```java
private static String requireText(JsonNode object, String field) {
    JsonNode node = object.path(field);

    if (!node.isTextual() || node.textValue().isBlank()) {
        throw new IllegalArgumentException(
                field + " phải là chuỗi không rỗng"
        );
    }

    return node.textValue();
}
```

Ở đây:

- Envelope được kiểm tra bằng tree model.
- Phần `payload` của event đã biết được chuyển thành DTO.
- Phần `partnerData` chưa có schema được giữ dưới dạng JsonNode.
- Event type chưa hỗ trợ có thể được lưu lại hoặc xử lý theo chính sách unknown event.

Cách kết hợp này giữ phần nghiệp vụ quan trọng ở kiểu tĩnh, còn dữ liệu mở rộng ở dạng cây.

## 16. Cách quyết định trong thực tế

Khi nhận một JSON chưa biết cấu trúc đầy đủ, có thể đi theo trình tự:

1. **Kiểm tra root shape:** object, array hay scalar?
2. **Tìm phần ổn định:** envelope, discriminator, ID, timestamp hoặc field bắt buộc.
3. **Xác định nhánh động:** field mở rộng, object tùy biến hoặc payload phụ thuộc loại sự kiện.
4. **Chọn biểu diễn:** DTO cho phần ổn định, JsonNode cho nhánh cần khảo sát; Map chỉ phù hợp với object key/value đơn giản.
5. **Phân biệt missing và null:** xác định ý nghĩa của key vắng mặt, key null và giá trị rỗng.
6. **Kiểm tra kiểu trước khi đọc:** không để `asInt()` hoặc `asText()` che giấu token sai.
7. **Chuyển nhánh đã biết thành DTO:** dùng `treeToValue()` khi schema đã được nhận diện.
8. **Giữ hoặc loại field lạ có chủ đích:** đặc biệt khi chuyển tiếp payload sang hệ thống khác.
9. **Cân nhắc bộ nhớ:** nếu tài liệu lớn, streaming toàn bộ hoặc streaming kết hợp tree theo từng phần.
10. **Validate và kiểm thử biến thể:** kiểm tra payload cũ, mới, thiếu field, null, sai kiểu và event chưa hỗ trợ.

## 17. Kết luận

Tree model của Jackson phù hợp khi cấu trúc JSON chưa cố định hoặc chỉ một phần payload được biết trước. `JsonNode` giữ hình dạng object, array và scalar để ứng dụng kiểm tra trước khi xử lý; `ObjectNode` và `ArrayNode` cho phép tạo và sửa dữ liệu; `treeToValue()` chuyển một nhánh đã biết thành DTO.

Hãy dùng DTO cho hợp đồng ổn định, Map cho object key/value đơn giản, tree model cho cấu trúc động cần khảo sát hoặc biến đổi, và streaming cho payload lớn cần xử lý tuần tự. Luôn phân biệt field thiếu với field null, kiểm tra kiểu node trước khi chuyển đổi và validate dữ liệu theo nghiệp vụ. Cách kết hợp phần cố định với phần động thường giúp code vừa có kiểu rõ ràng, vừa thích nghi được với schema thay đổi.

## Tài liệu tham khảo

- [Jackson Databind — Tree Model](https://github.com/FasterXML/jackson-databind)
- [Jackson Databind — JsonNode API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonNode.html)
- [Jackson Databind — ObjectNode API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/node/ObjectNode.html)
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)

