# Truy cập thuộc tính bằng get và path

Jackson Tree Model biểu diễn JSON thành một cây node. Khi đã có JsonNode gốc, ứng dụng có thể truy cập object property, array element và các node lồng nhau mà không cần tạo DTO cho toàn bộ payload.

Hai phương thức được dùng thường xuyên nhất là **get()** và **path()**. Cả hai đều cho phép truy cập một thuộc tính hoặc phần tử, nhưng khác nhau ở cách biểu diễn trường hợp không tồn tại:

- get() trả về Java null nếu property hoặc index không tồn tại.
- path() trả về MissingNode nếu property hoặc index không tồn tại.
- Nếu JSON có field với giá trị null, cả hai đều trả về một NullNode, không phải Java null.

Khác biệt này quyết định cách viết code an toàn. get() phù hợp khi muốn tự kiểm tra null hoặc cần phân biệt node không có; path() thuận tiện cho truy cập lồng nhau vì MissingNode cho phép tiếp tục gọi path() mà không gây NullPointerException.

## 1. Tree Model và JsonNode

Jackson có thể đọc JSON thành cây node bằng ObjectMapper.readTree():

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree("""
    {
      "id": 1001,
      "name": "An",
      "active": true,
      "address": {
        "city": "Ho Chi Minh City",
        "district": "District 1"
      },
      "tags": ["java", "jackson"]
    }
    """);
~~~

Cấu trúc cây có thể hình dung:

~~~text
root (ObjectNode)
├── id       -> IntNode(1001)
├── name     -> TextNode("An")
├── active   -> BooleanNode(true)
├── address  -> ObjectNode
│   ├── city     -> TextNode("Ho Chi Minh City")
│   └── district -> TextNode("District 1")
└── tags     -> ArrayNode
    ├── [0]  -> TextNode("java")
    └── [1]  -> TextNode("jackson")
~~~

JsonNode là kiểu cơ sở để làm việc với nhiều dạng node. Các implementation thường gặp:

| Loại node | Ý nghĩa |
|---|---|
| ObjectNode | JSON object, chứa các property |
| ArrayNode | JSON array, chứa các phần tử theo index |
| TextNode | JSON string |
| IntNode, LongNode, BigIntegerNode | Các dạng số nguyên |
| DoubleNode, DecimalNode | Các dạng số có phần thập phân |
| BooleanNode | JSON true/false |
| NullNode | JSON null |
| MissingNode | Node đại diện cho giá trị không tìm thấy trong một số thao tác truy cập |

Tree Model hữu ích khi cấu trúc JSON thay đổi, chỉ cần đọc một vài field, hoặc phải quyết định kiểu DTO sau khi xem một thuộc tính như eventType.

## 2. Dùng get() để truy cập property

Với JSON object, gọi get() bằng tên field:

~~~java
JsonNode idNode = root.get("id");
JsonNode nameNode = root.get("name");
~~~

Nếu field tồn tại, get() trả về node tương ứng. Nếu field không tồn tại, kết quả là Java null.

Ví dụ:

~~~java
JsonNode cityNode = root.get("city");

if (cityNode == null) {
    System.out.println("Property city does not exist");
}
~~~

Điểm cần nhớ: Java null ở đây có nghĩa là không tìm thấy property. Nó khác với một property có mặt trong JSON nhưng mang giá trị null.

### 2.1. get() với field có giá trị JSON null

JSON:

~~~json
{
  "nickname": null
}
~~~

Code:

~~~java
JsonNode nicknameNode = root.get("nickname");
JsonNode missingNode = root.get("email");

System.out.println(nicknameNode == null); // false
System.out.println(nicknameNode.isNull()); // true

System.out.println(missingNode == null);   // true
~~~

Kết quả:

| Input | Kết quả của get() | Kiểm tra |
|---|---|---|
| Field có value | Node tương ứng | node != null |
| Field có explicit null | NullNode | node != null và node.isNull() |
| Field không tồn tại | Java null | node == null |

Vì vậy, nếu cần phân biệt missing với explicit null, get() cung cấp hai trạng thái riêng: Java null và NullNode.

### 2.2. get() không an toàn khi chain trực tiếp

Ví dụ:

~~~java
String city = root.get("address").get("city").asText();
~~~

Nếu address không tồn tại, root.get("address") trả về Java null. Gọi tiếp get("city") sẽ gây NullPointerException.

Nếu address tồn tại nhưng là JSON null, kết quả là NullNode. Gọi tiếp get("city") trên NullNode không có cùng ý nghĩa với một object thông thường; kết quả không tìm thấy sẽ dẫn đến vấn đề nếu code tiếp tục giả định có text node.

Có thể viết kiểm tra từng bước:

~~~java
JsonNode addressNode = root.get("address");

if (addressNode != null && addressNode.isObject()) {
    JsonNode cityNode = addressNode.get("city");

    if (cityNode != null && cityNode.isTextual()) {
        String city = cityNode.textValue();
    }
}
~~~

Cách này tường minh nhưng dài khi phải truy cập nhiều cấp. path() thường thuận tiện hơn cho trường hợp truy cập lồng nhau.

## 3. Dùng path() để truy cập an toàn

path() cũng nhận tên property, nhưng nếu field không tồn tại, nó trả về MissingNode thay vì Java null.

~~~java
JsonNode cityNode = root.path("address").path("city");
~~~

Nếu address hoặc city không tồn tại, kết quả cuối cùng vẫn là MissingNode. Không có NullPointerException do một cấp trung gian bị thiếu.

Ví dụ:

~~~java
JsonNode missing = root.path("unknown");

System.out.println(missing.isMissingNode()); // true
System.out.println(missing.isNull());        // false
~~~

Nếu field có mặt và explicit null:

~~~java
JsonNode nickname = root.path("nickname");

System.out.println(nickname.isMissingNode()); // false
System.out.println(nickname.isNull());        // true
~~~

### 3.1. Chain nhiều cấp

Giả sử JSON:

~~~json
{
  "customer": {
    "profile": {
      "displayName": "Minh"
    }
  }
}
~~~

Có thể truy cập:

~~~java
String displayName = root
    .path("customer")
    .path("profile")
    .path("displayName")
    .asText(null);
~~~

Nếu customer, profile hoặc displayName bị thiếu, path() trả MissingNode và asText(null) trả fallback null.

Cách viết này phù hợp khi field không bắt buộc. Nếu field bắt buộc, cần kiểm tra trạng thái MissingNode/NullNode và báo lỗi rõ ràng thay vì để fallback che giấu dữ liệu không hợp lệ.

### 3.2. path() không chứng minh node có đúng kiểu

path() chỉ giúp truy cập an toàn khi property không tồn tại. Nó không bảo đảm node là object, string, number hay array.

Ví dụ:

~~~json
{
  "address": "unknown"
}
~~~

Lệnh:

~~~java
JsonNode city = root.path("address").path("city");
~~~

Không gây lỗi truy cập, nhưng address là TextNode chứ không phải ObjectNode. Kết quả không thể được coi là city hợp lệ.

Hãy kiểm tra kiểu node trước khi dùng dữ liệu:

~~~java
JsonNode address = root.path("address");

if (!address.isObject()) {
    throw new IllegalArgumentException("address must be a JSON object");
}

JsonNode city = address.path("city");

if (!city.isTextual()) {
    throw new IllegalArgumentException("address.city must be a string");
}

String cityName = city.textValue();
~~~

An toàn khi truy cập và hợp lệ theo schema là hai vấn đề riêng.

## 4. So sánh get() và path()

| Tiêu chí | get(field/index) | path(field/index) |
|---|---|---|
| Field tồn tại | Trả node tương ứng | Trả node tương ứng |
| Field explicit null | Trả NullNode | Trả NullNode |
| Field missing | Trả Java null | Trả MissingNode |
| Chain nhiều cấp | Có thể gây NullPointerException | Có thể chain an toàn |
| Phân biệt missing và null | Có, qua Java null và NullNode | Có, qua MissingNode và NullNode |
| Kiểm tra field bắt buộc | Phải kiểm tra null | Phải kiểm tra isMissingNode/isNull |
| Truy cập index ngoài phạm vi | Trả Java null | Trả MissingNode |

Ví dụ cùng một field:

~~~java
JsonNode usingGet = root.get("nickname");
JsonNode usingPath = root.path("nickname");

if (usingGet == null) {
    // Field không tồn tại.
} else if (usingGet.isNull()) {
    // Field có mặt nhưng là JSON null.
}

if (usingPath.isMissingNode()) {
    // Field không tồn tại.
} else if (usingPath.isNull()) {
    // Field có mặt nhưng là JSON null.
}
~~~

Nên chọn theo mục đích:

- Dùng get() khi muốn Java null thể hiện missing và sẽ kiểm tra rõ ràng.
- Dùng path() khi cần chain nhiều cấp hoặc muốn tránh null check ở từng bước.
- Dùng has()/hasNonNull() khi câu hỏi chính là property có xuất hiện hay có giá trị khác null.
- Dùng isMissingNode()/isNull() để phân biệt trạng thái node.

## 5. has() và hasNonNull()

JsonNode cung cấp hai phương thức thường đi cùng get() và path():

- has(fieldName): trả true nếu property tồn tại, kể cả khi giá trị là JSON null.
- hasNonNull(fieldName): trả true nếu property tồn tại và giá trị không phải JSON null.

Ví dụ:

~~~json
{
  "name": "An",
  "nickname": null
}
~~~

~~~java
root.has("name");          // true
root.hasNonNull("name");   // true

root.has("nickname");      // true
root.hasNonNull("nickname"); // false

root.has("email");         // false
root.hasNonNull("email");  // false
~~~

Bảng kết quả:

| Trạng thái | has() | hasNonNull() |
|---|---:|---:|
| Field có giá trị | true | true |
| Field explicit null | true | false |
| Field missing | false | false |

Đây là cách ngắn gọn để kiểm tra presence khi xử lý payload động.

Tuy nhiên, hasNonNull() không phân biệt explicit null với missing. Nếu cần phân biệt hai trạng thái đó, hãy kết hợp has() với get()/path().

## 6. Truy cập phần tử array bằng index

Với JSON array, get(int) và path(int) dùng index bắt đầu từ 0.

JSON:

~~~json
{
  "items": [
    {"code": "A01", "quantity": 2},
    {"code": "B02", "quantity": 5}
  ]
}
~~~

Truy cập phần tử đầu tiên:

~~~java
JsonNode firstItem = root.path("items").get(0);
String code = firstItem.path("code").asText();
~~~

Có thể dùng path(index) để tránh Java null khi index không tồn tại:

~~~java
JsonNode thirdItem = root.path("items").path(2);

if (thirdItem.isMissingNode()) {
    // Không có phần tử ở index 2.
}
~~~

### 6.1. Kiểm tra array trước khi duyệt

Không nên giả định property luôn là ArrayNode. Hãy kiểm tra:

~~~java
JsonNode items = root.path("items");

if (!items.isArray()) {
    throw new IllegalArgumentException("items must be an array");
}

for (JsonNode item : items) {
    String code = item.path("code").asText(null);
    int quantity = item.path("quantity").asInt(-1);

    if (code == null || quantity < 0) {
        throw new IllegalArgumentException("Invalid item");
    }
}
~~~

Vòng lặp trên thể hiện cách duyệt node. Với dữ liệu nghiệp vụ, nên kiểm tra cả kiểu node và miền giá trị thay vì chỉ dựa vào fallback của asText/asInt.

### 6.2. Index âm và ngoài phạm vi

Index hợp lệ của array nằm từ 0 đến size() - 1.

- get(-1) hoặc get(index ngoài phạm vi) trả Java null.
- path(index ngoài phạm vi) trả MissingNode.
- size() trả số phần tử của array; với các node không phải container, kết quả thường là 0.

Không nên dùng index từ dữ liệu client mà không kiểm tra giới hạn. Với array lớn, cần cân nhắc giới hạn số phần tử và dung lượng payload.

## 7. Kiểm tra kiểu node trước khi đọc value

JsonNode cung cấp các phương thức kiểm tra kiểu:

| Phương thức | Kiểm tra |
|---|---|
| isObject() | JSON object |
| isArray() | JSON array |
| isTextual() | JSON string |
| isNumber() | JSON number |
| isIntegralNumber() | Số nguyên |
| isFloatingPointNumber() | Số có phần thập phân |
| isBoolean() | JSON boolean |
| isNull() | JSON null |
| isMissingNode() | Node không tìm thấy |
| isBinary() | Node biểu diễn binary theo Jackson |
| isValueNode() | Node scalar/value |

Ví dụ:

~~~java
JsonNode quantity = root.path("quantity");

if (quantity.isIntegralNumber() && quantity.canConvertToInt()) {
    int value = quantity.intValue();
} else {
    throw new IllegalArgumentException(
        "quantity must be an integer in int range"
    );
}
~~~

isIntegralNumber() xác nhận node là số nguyên. canConvertToInt() xác nhận giá trị nằm trong phạm vi int. Chỉ gọi intValue() mà không kiểm tra có thể làm mất thông tin hoặc nhận giá trị ngoài phạm vi mong muốn.

Với số thập phân:

~~~java
JsonNode price = root.path("price");

if (price.isNumber()) {
    BigDecimal amount = price.decimalValue();
}
~~~

Nếu hợp đồng yêu cầu BigDecimal chính xác, nên đọc trực tiếp vào DTO có field BigDecimal hoặc cấu hình mapper phù hợp. Khi đọc qua tree, cần chú ý cách JsonNode biểu diễn số phụ thuộc JsonFactory và cấu hình đọc số.

## 8. asText(), textValue() và các phương thức chuyển giá trị

Sau khi truy cập node, có thể lấy giá trị bằng các phương thức như asText(), textValue(), asInt(), intValue(), asBoolean(), booleanValue().

Các phương thức này không có semantics giống nhau.

### 8.1. asText() và textValue()

~~~java
JsonNode name = root.path("name");

String text1 = name.asText();
String text2 = name.textValue();
~~~

- asText() trả biểu diễn dạng chuỗi của node; một số node có thể cung cấp text từ giá trị scalar.
- textValue() chỉ trả nội dung nếu node là TextNode; với node khác, kết quả có thể là null.

Nếu field bắt buộc phải là JSON string, hãy kiểm tra isTextual() trước rồi dùng textValue(). Không dùng asText() để âm thầm chấp nhận number hoặc boolean khi hợp đồng yêu cầu string.

Ví dụ:

~~~java
JsonNode nameNode = root.path("name");

if (!nameNode.isTextual()) {
    throw new IllegalArgumentException("name must be a string");
}

String name = nameNode.textValue();
~~~

### 8.2. asInt() và intValue()

asInt() có thể chuyển một số dạng scalar sang int; với node không phù hợp, nó có thể trả fallback mặc định hoặc fallback do caller cung cấp.

~~~java
int quantity = root.path("quantity").asInt(-1);
~~~

Nếu quantity thiếu, null hoặc không chuyển được theo quy tắc của node, fallback -1 có thể được trả về.

intValue() phù hợp khi node đã được xác nhận là numeric. Nó không phải phương thức validation.

~~~java
JsonNode quantityNode = root.path("quantity");

if (!quantityNode.isIntegralNumber()
        || !quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("Invalid quantity");
}

int quantity = quantityNode.intValue();
~~~

### 8.3. asBoolean() và booleanValue()

~~~java
JsonNode activeNode = root.path("active");

if (!activeNode.isBoolean()) {
    throw new IllegalArgumentException("active must be boolean");
}

boolean active = activeNode.booleanValue();
~~~

Nếu dùng asBoolean() trực tiếp, chuỗi hoặc số có thể được diễn giải theo quy tắc chuyển đổi của node. Khi hợp đồng yêu cầu JSON true/false, kiểm tra isBoolean() trước.

## 9. Dùng default value khi gọi path và asX

Một số overload cho phép cung cấp fallback:

~~~java
String name = root.path("name").asText("Anonymous");
int page = root.path("page").asInt(0);
boolean active = root.path("active").asBoolean(false);
~~~

Điều này tiện khi field thực sự optional và fallback đã được quy định.

Nhưng fallback có thể làm mất thông tin về trạng thái input:

- Field missing.
- Field explicit null.
- Field sai kiểu.
- Field có giá trị nhưng không chuyển được.

Ví dụ asInt(0) có thể khiến code coi quantity missing như quantity 0. Nếu 0 có ý nghĩa nghiệp vụ, hai trường hợp này bị nhập làm một.

Khi cần báo lỗi khác nhau, hãy kiểm tra node trước:

~~~java
JsonNode pageNode = root.path("page");

if (pageNode.isMissingNode()) {
    // Field không được gửi.
} else if (pageNode.isNull()) {
    // Field được gửi với null.
} else if (!pageNode.isIntegralNumber()) {
    // Field có kiểu sai.
} else {
    int page = pageNode.intValue();
}
~~~

## 10. Truy cập bằng JsonPointer: at()

Khi cần truy cập một vị trí sâu trong cây JSON theo đường dẫn, JsonNode có phương thức at() nhận JSON Pointer.

Ví dụ:

~~~java
JsonNode city = root.at("/customer/address/city");
~~~

JSON Pointer theo RFC 6901 dùng dấu / để phân tách các segment. Array index cũng có thể được biểu diễn trong path:

~~~java
JsonNode firstProductCode = root.at("/items/0/code");
~~~

Nếu đường dẫn không tồn tại, at() trả MissingNode. Có thể kiểm tra:

~~~java
JsonNode node = root.at("/customer/address/postalCode");

if (node.isMissingNode()) {
    // Đường dẫn không tồn tại.
}
~~~

Một số ký tự trong tên property cần escape theo JSON Pointer:

- Dấu ~ được biểu diễn thành ~0.
- Dấu / được biểu diễn thành ~1.

Ví dụ property có tên a/b được truy cập bằng segment a~1b.

JsonPointer phù hợp khi đường dẫn được cấu hình hoặc truyền từ bên ngoài. Nếu chỉ truy cập một vài field cố định trong code, path() thường dễ đọc hơn.

Không nhầm JSON Pointer với JSONPath. JSON Pointer mô tả một đường dẫn cụ thể đến một node; nó không có cú pháp truy vấn/filter/wildcard như các biểu thức JSONPath.

## 11. Duyệt object và kiểm tra field động

Khi tên field không biết trước, có thể duyệt các field của ObjectNode:

~~~java
JsonNode metadata = root.path("metadata");

if (metadata.isObject()) {
    Iterator<Map.Entry<String, JsonNode>> fields =
        metadata.fields();

    while (fields.hasNext()) {
        Map.Entry<String, JsonNode> entry = fields.next();

        String fieldName = entry.getKey();
        JsonNode fieldValue = entry.getValue();

        System.out.println(fieldName + " = " + fieldValue);
    }
}
~~~

Một số phương thức hữu ích:

- fieldNames(): duyệt tên các property.
- fields(): duyệt cặp tên và JsonNode.
- elements(): duyệt các value con của object hoặc array.
- size(): số property của object hoặc số phần tử của array.
- has()/hasNonNull(): kiểm tra sự tồn tại và null.
- get()/path(): truy cập một phần tử cụ thể.

Nếu object chứa dữ liệu không tin cậy, không nên in toàn bộ value ra log. Hãy chọn field cần thiết và loại bỏ thông tin nhạy cảm.

## 12. Sửa đổi cây JSON sau khi truy cập

ObjectNode và ArrayNode là các node có thể thay đổi. Sau khi lấy được node phù hợp, có thể cập nhật, thêm hoặc xóa property.

Ví dụ:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(json);

root.put("status", "PROCESSED");
root.putNull("processedAt");
root.remove("internalNote");

ArrayNode tags = (ArrayNode) root.path("tags");

if (tags != null) {
    tags.add("jackson");
}
~~~

Cần kiểm tra node thực sự là ObjectNode hoặc ArrayNode trước khi ép kiểu. path() có thể trả MissingNode hoặc NullNode; ép kiểu trực tiếp sang ObjectNode có thể gây ClassCastException.

Một cách an toàn hơn:

~~~java
JsonNode tagsNode = root.path("tags");

if (tagsNode.isArray()) {
    ((ArrayNode) tagsNode).add("jackson");
} else {
    root.putArray("tags").add("jackson");
}
~~~

Nếu cây JSON được chia sẻ giữa nhiều luồng, không sửa đổi nó đồng thời mà không có cơ chế đồng bộ phù hợp. Tree Model mutable nên cần xác định ownership giống như các object Java khác.

## 13. Khi nào nên chuyển JsonNode thành DTO?

JsonNode phù hợp cho truy cập động, nhưng không nên thay DTO ở mọi nơi.

Dùng JsonNode khi:

- Payload có nhiều biến thể và cần xác định loại trước khi binding.
- Chỉ cần một vài field.
- Cần phân biệt missing, null và value.
- Cần giữ lại phần JSON chưa biết.
- Đang viết adapter cho hệ thống ngoài.

Chuyển thành DTO khi:

- Cấu trúc đã ổn định.
- Có validation và quy tắc kiểu rõ ràng.
- Nghiệp vụ cần gọi nhiều method trên dữ liệu.
- Muốn compiler hỗ trợ kiểm tra kiểu.
- Muốn test hợp đồng và refactor an toàn hơn.

Ví dụ:

~~~java
JsonNode root = mapper.readTree(json);
String eventType = root.path("eventType").asText(null);

if ("ORDER_CREATED".equals(eventType)) {
    OrderCreatedEvent event =
        mapper.treeToValue(root.path("data"), OrderCreatedEvent.class);

    orderHandler.handle(event);
}
~~~

Ở đây JsonNode được dùng để phân nhánh theo eventType, sau đó phần data được chuyển sang DTO cụ thể. Đây là cách kết hợp linh hoạt và type-safe.

## 14. Kiểm thử get() và path() với các trạng thái khác nhau

Nên viết test thể hiện rõ missing, explicit null và value.

~~~java
@Test
void distinguishesMissingNullAndPresentValue() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "nickname": null,
          "name": "An"
        }
        """);

    assertNull(root.get("email"));
    assertTrue(root.path("email").isMissingNode());

    assertNotNull(root.get("nickname"));
    assertTrue(root.get("nickname").isNull());
    assertTrue(root.has("nickname"));
    assertFalse(root.hasNonNull("nickname"));

    assertEquals("An", root.path("name").textValue());
}
~~~

Test nested access:

~~~java
@Test
void pathCanTraverseMissingIntermediateNodes() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "customer": {}
        }
        """);

    JsonNode city = root.path("customer")
        .path("address")
        .path("city");

    assertTrue(city.isMissingNode());
}
~~~

Test array index:

~~~java
@Test
void distinguishesOutOfRangeArrayIndex() throws Exception {
    JsonNode root = mapper.readTree("""
        {
          "items": ["A", "B"]
        }
        """);

    JsonNode items = root.path("items");

    assertNull(items.get(2));
    assertTrue(items.path(2).isMissingNode());
    assertEquals("A", items.path(0).textValue());
}
~~~

Ngoài các test trên, nên test node sai kiểu, field null ở cấp trung gian, empty object, empty array và các giá trị scalar không đúng hợp đồng.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| NullPointerException khi chain get() | Field trung gian không tồn tại nên get() trả Java null | Kiểm tra từng cấp hoặc dùng path() |
| Không phân biệt được missing và null | Dùng asText/asInt fallback ngay | Kiểm tra isMissingNode(), isNull() trước |
| Field sai kiểu nhưng vẫn nhận giá trị | Dùng asX() mà không kiểm tra node type | Dùng isTextual/isIntegralNumber/isBoolean |
| Ép kiểu ClassCastException | Giả định node là ObjectNode/ArrayNode | Kiểm tra isObject()/isArray() trước |
| Array index không tồn tại | Dùng get(index) rồi gọi tiếp | Kiểm tra null hoặc dùng path(index) |
| asInt() trả 0 khiến lỗi bị che | Fallback mặc định trùng giá trị nghiệp vụ | Dùng fallback sentinel hoặc kiểm tra node |
| Dùng at() như JSONPath | Nhầm JSON Pointer với query language | Dùng JsonPointer cho đường dẫn cụ thể |
| Sửa node dùng chung gây race | Tree Model mutable bị chia sẻ | Tạo tree riêng hoặc kiểm soát đồng bộ |

## 16. Quy trình truy cập thuộc tính an toàn

~~~text
Đọc JSON bằng readTree()
          |
          v
Xác định node gốc có đúng kiểu?
          |
          v
Truy cập bằng get() hoặc path()
          |
          v
Phân biệt MissingNode / NullNode / Value
          |
          v
Kiểm tra kiểu node
          |
          v
Chuyển giá trị bằng textValue/intValue/...
          |
          v
Validate theo hợp đồng và nghiệp vụ
          |
          v
Chuyển sang DTO hoặc xử lý tiếp
~~~

Đối với field optional, có thể dùng path() và fallback sau khi đã quyết định semantics. Đối với field bắt buộc, hãy báo lỗi cụ thể khi missing, null hoặc sai kiểu. Với cấu trúc lồng sâu, path() hoặc at() giúp tránh null dereference, nhưng vẫn cần kiểm tra schema.

## 17. Kết luận

get() và path() đều là công cụ truy cập cây JSON, nhưng khác nhau ở trạng thái property không tồn tại. get() trả Java null; path() trả MissingNode. Explicit JSON null là NullNode ở cả hai cách. Sự phân biệt này rất quan trọng khi xử lý dữ liệu thiếu, null và sai kiểu.

Hãy dùng get() khi cần kiểm soát trực tiếp Java null, path() cho truy cập lồng nhau an toàn, has()/hasNonNull() cho kiểm tra presence, và at() khi có JSON Pointer. Trước khi lấy giá trị, kiểm tra kiểu node để tránh chuyển đổi ngầm hoặc ép kiểu sai. Khi schema ổn định, chuyển JsonNode sang DTO để tận dụng type safety và validation.

Một quy trình truy cập rõ ràng giúp xử lý payload động an toàn hơn, tránh NullPointerException và không vô tình biến dữ liệu thiếu hoặc sai kiểu thành giá trị mặc định có vẻ hợp lệ.

