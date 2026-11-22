# Đọc kiểu dữ liệu và tránh chuyển đổi mặc định ngoài ý muốn

Jackson Tree Model biểu diễn JSON thành một cây các node. Mỗi node có loại dữ liệu cụ thể như object, array, string, number, boolean hoặc null. Khi đọc JSON thành `JsonNode`, ứng dụng có thể kiểm tra loại node trước khi lấy giá trị, thay vì yêu cầu Jackson tự chuyển đổi sang kiểu Java theo một quy tắc ngầm.

Điểm cần chú ý là nhiều phương thức tiện ích của `JsonNode`, chẳng hạn `asInt()`, `asLong()`, `asBoolean()` hoặc `asText()`, được thiết kế để thuận tiện và có thể thực hiện coercion (chuyển đổi linh hoạt) hoặc trả về giá trị mặc định khi node không phù hợp. Nếu dùng chúng mà không kiểm tra loại dữ liệu, một payload sai có thể biến thành `0`, `false`, chuỗi rỗng hoặc một giá trị khác có vẻ hợp lệ. Lỗi khi đó khó phát hiện và có thể đi sâu vào logic nghiệp vụ.

Để đọc dữ liệu an toàn, hãy phân biệt node không tồn tại, node JSON null và node có giá trị; kiểm tra loại node bằng `isTextual()`, `isIntegralNumber()`, `isBoolean()`…; kiểm tra miền số bằng `canConvertToInt()` hoặc `canConvertToLong()`; chỉ dùng giá trị mặc định khi hợp đồng cho phép rõ ràng.

## 1. Tree Model và JsonNode

Jackson Databind cung cấp Tree Model để biểu diễn tài liệu JSON dưới dạng cây. Lớp cơ sở là `JsonNode`; các node cụ thể biểu diễn object, array, string, number, boolean và null.

Ví dụ JSON:

```json
{
  "id": 23,
  "name": "Lan",
  "active": true,
  "score": 8.75,
  "tags": ["java", "jackson"],
  "address": {
    "city": "Ho Chi Minh City"
  },
  "note": null
}
```

Đọc JSON thành cây:

```java
ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(json);
```

`root` đại diện object ngoài cùng. Có thể lấy từng node:

```java
JsonNode idNode = root.get("id");
JsonNode nameNode = root.get("name");
JsonNode tagsNode = root.get("tags");
JsonNode addressNode = root.get("address");
JsonNode noteNode = root.get("note");
```

Tree Model hữu ích khi cấu trúc JSON động, chỉ cần đọc một số trường, hoặc cần kiểm tra payload trước khi ánh xạ sang DTO. Nhưng sự tiện lợi của các phương thức chuyển đổi không có nghĩa là mọi giá trị đều nên được ép kiểu tự động.

## 2. Phân biệt node thiếu, null và giá trị cụ thể

Ba trạng thái này khác nhau:

```json
{}
```

```json
{"note": null}
```

```json
{"note": "Hello"}
```

Với `get("note")`:

- Nếu khóa không tồn tại, `get()` trả về `null` Java.
- Nếu khóa có mặt và giá trị JSON là `null`, `get()` trả về một `NullNode`.
- Nếu khóa có giá trị, `get()` trả về node tương ứng.

Có thể kiểm tra:

```java
JsonNode note = root.get("note");

if (note == null) {
    // Thuộc tính không tồn tại.
} else if (note.isNull()) {
    // Thuộc tính có mặt với JSON null.
} else {
    // Thuộc tính có một giá trị khác null.
}
```

Phương thức `has()` và `hasNonNull()` cũng khác nhau:

| Phương thức | Khóa thiếu | Khóa có JSON null | Khóa có giá trị |
|---|---:|---:|---:|
| `has("note")` | `false` | `true` | `true` |
| `hasNonNull("note")` | `false` | `false` | `true` |

Nếu cần phân biệt “không gửi” với “gửi null”, dùng `has()` rồi kiểm tra `isNull()`. Nếu chỉ dùng `hasNonNull()`, hai trạng thái đầu sẽ bị gộp.

### 2.1. get() và path()

`get()` trả về `null` Java nếu property không tồn tại. `path()` trả về `MissingNode` thay vì null Java:

```java
JsonNode missing = root.path("notFound");

if (missing.isMissingNode()) {
    // Đường dẫn không tồn tại.
}
```

`path()` hữu ích khi truy cập lồng nhau mà không muốn kiểm tra null sau từng bước:

```java
String city = root.path("address").path("city").asText();
```

Tuy nhiên, gọi `asText()` ngay như trên có thể làm mất dấu hiệu đường dẫn bị thiếu hoặc sai kiểu. Nếu trường bắt buộc, hãy giữ node và kiểm tra trước:

```java
JsonNode cityNode = root.path("address").path("city");

if (!cityNode.isTextual()) {
    throw new IllegalArgumentException("address.city must be a string");
}

String city = cityNode.textValue();
```

## 3. Các loại node và cách nhận diện

Jackson cung cấp các phương thức kiểm tra loại node:

| JSON type | Phương thức kiểm tra | Ví dụ |
|---|---|---|
| Object | `isObject()` | `{"id": 23}` |
| Array | `isArray()` | `[1, 2, 3]` |
| String | `isTextual()` | `"Lan"` |
| Number | `isNumber()` | `23`, `8.75` |
| Số nguyên | `isIntegralNumber()` | `23` |
| Số dấu phẩy động | `isFloatingPointNumber()` | `8.75`, `1e3` |
| Boolean | `isBoolean()` | `true`, `false` |
| Null | `isNull()` | `null` |
| Missing | `isMissingNode()` | Đường dẫn không có trong cây |

Ví dụ kiểm tra trước khi đọc:

```java
JsonNode activeNode = root.get("active");

if (activeNode == null || !activeNode.isBoolean()) {
    throw new IllegalArgumentException("active must be provided as a boolean");
}

boolean active = activeNode.booleanValue();
```

`isNumber()` chỉ cho biết node là một số. Nếu yêu cầu là số nguyên, hãy dùng `isIntegralNumber()` thay vì `isNumber()`, vì `12.5` cũng là number nhưng không phải số nguyên.

## 4. Vì sao các phương thức asXxx() có thể nguy hiểm?

Các phương thức `asXxx()` giúp lấy giá trị thuận tiện từ node, nhưng có thể chuyển đổi từ dạng khác hoặc trả giá trị mặc định khi không thể chuyển đổi.

Ví dụ:

```java
int quantity = root.path("quantity").asInt();
boolean enabled = root.path("enabled").asBoolean();
String name = root.path("name").asText();
```

Nếu `quantity` không tồn tại hoặc node không thể chuyển thành số nguyên, `asInt()` không nhất thiết báo lỗi; nó có thể trả về `0`. Tương tự, `asBoolean()` có thể trả `false`, còn `asText()` có thể trả chuỗi rỗng đối với node thiếu hoặc node không phù hợp.

Khi `0`, `false` hoặc `""` là giá trị hợp lệ trong nghiệp vụ, việc dùng fallback ngầm sẽ làm payload lỗi trông giống payload hợp lệ.

Ví dụ JSON:

```json
{
  "quantity": "unknown",
  "enabled": "perhaps",
  "name": null
}
```

Nếu code đọc trực tiếp bằng `asInt()`, `asBoolean()` hoặc `asText()`, nó có thể không phát hiện được rằng dữ liệu không đúng kiểu mà hợp đồng yêu cầu.

Nguyên tắc: **kiểm tra node trước, sau đó dùng phương thức lấy giá trị phù hợp với loại node.**

## 5. Đọc String an toàn

Nếu hợp đồng yêu cầu một trường là chuỗi JSON, hãy xác nhận `isTextual()`:

```java
JsonNode nameNode = root.get("name");

if (nameNode == null || !nameNode.isTextual()) {
    throw new IllegalArgumentException("name must be a string");
}

String name = nameNode.textValue();
```

`textValue()` trả về giá trị chuỗi của `TextNode`; nếu node không phải textual, nó không thực hiện coercion như `asText()`.

Phân biệt các trường hợp:

| JSON | `isTextual()` | Ý nghĩa |
|---|---:|---|
| `"Lan"` | `true` | Chuỗi hợp lệ |
| `123` | `false` | Number, không phải string |
| `true` | `false` | Boolean, không phải string |
| `null` | `false` | Null |
| Khóa thiếu | Không có node hoặc `MissingNode` | Không cung cấp |

Nếu API chủ động cho phép số được gửi dưới dạng chuỗi, hãy quy định coercion rõ ràng ở hợp đồng và chuyển đổi có kiểm soát. Không tự chấp nhận mọi loại node chỉ vì `asText()` có thể tạo ra một chuỗi.

## 6. Đọc số nguyên và kiểm tra miền giá trị

Nếu trường yêu cầu `int`, cần kiểm tra cả loại số và phạm vi:

```java
JsonNode quantityNode = root.get("quantity");

if (quantityNode == null || !quantityNode.isIntegralNumber()) {
    throw new IllegalArgumentException("quantity must be an integer");
}

if (!quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("quantity is outside int range");
}

int quantity = quantityNode.intValue();
```

`isIntegralNumber()` ngăn trường hợp JSON `3.5` bị đọc như số nguyên. `canConvertToInt()` kiểm tra giá trị có thể chuyển sang miền `int` hay không. Sau đó mới gọi `intValue()`.

Với `long`:

```java
JsonNode idNode = root.get("id");

if (idNode == null || !idNode.isIntegralNumber()) {
    throw new IllegalArgumentException("id must be an integer");
}

if (!idNode.canConvertToLong()) {
    throw new IllegalArgumentException("id is outside long range");
}

long id = idNode.longValue();
```

Nếu số có thể vượt miền `long`, lấy `BigInteger`:

```java
if (idNode == null || !idNode.isIntegralNumber()) {
    throw new IllegalArgumentException("id must be an integer");
}

BigInteger id = idNode.bigIntegerValue();
```

`BigInteger` tránh tràn kiểu nguyên thủy, nhưng ứng dụng vẫn nên đặt giới hạn độ dài và miền nghiệp vụ để tránh dữ liệu quá lớn tiêu tốn tài nguyên.

## 7. Đọc số thập phân chính xác

Nếu trường cần số thập phân, hãy lấy `BigDecimal`:

```java
JsonNode priceNode = root.get("price");

if (priceNode == null || !priceNode.isNumber()) {
    throw new IllegalArgumentException("price must be a number");
}

BigDecimal price = priceNode.decimalValue();
```

Nếu yêu cầu chỉ chấp nhận token có phần thập phân, có thể kiểm tra `isFloatingPointNumber()`. Nhưng nếu API cho phép cả `10` và `10.0` cho cùng trường giá, `isNumber()` phù hợp hơn.

Để bảo toàn độ chính xác khi parse Tree Model, có thể cấu hình reader:

```java
ObjectReader exactReader = mapper.reader()
    .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

JsonNode root = exactReader.readTree(json);
BigDecimal price = root.path("price").decimalValue();
```

Nếu node đã được tạo dưới dạng `DoubleNode`, gọi `decimalValue()` sau đó không thể khôi phục chính xác token thập phân ban đầu. Muốn giữ số thập phân chính xác, phải cấu hình trước khi parse hoặc ánh xạ trực tiếp vào DTO có trường `BigDecimal`.

Với tiền tệ, ngoài kiểu số còn cần kiểm tra scale, đơn vị tiền tệ và quy tắc làm tròn. `BigDecimal` không tự quyết định nghiệp vụ đó.

## 8. Đọc Boolean mà không biến dữ liệu sai thành false

Nếu hợp đồng yêu cầu boolean:

```java
JsonNode activeNode = root.get("active");

if (activeNode == null || !activeNode.isBoolean()) {
    throw new IllegalArgumentException("active must be a boolean");
}

boolean active = activeNode.booleanValue();
```

Không nên dùng:

```java
boolean active = root.path("active").asBoolean();
```

trừ khi hợp đồng quy định thiếu hoặc không chuyển đổi được sẽ mặc định là `false`. Nếu client gửi `"yes"`, `0` hoặc bỏ hẳn khóa, `asBoolean()` có thể cho kết quả fallback thay vì báo lỗi.

Nếu trường là tùy chọn, xử lý riêng trạng thái thiếu:

```java
JsonNode activeNode = root.get("active");

if (activeNode == null) {
    // Không được cung cấp: dùng giá trị hiện tại hoặc default theo hợp đồng.
} else if (activeNode.isNull()) {
    // Có null: từ chối hoặc xử lý null theo hợp đồng.
} else if (activeNode.isBoolean()) {
    boolean active = activeNode.booleanValue();
} else {
    throw new IllegalArgumentException("active must be boolean or null");
}
```

## 9. Đọc Array và Object an toàn

Không nên giả định node luôn là array hoặc object:

```java
JsonNode tagsNode = root.get("tags");

if (tagsNode == null || !tagsNode.isArray()) {
    throw new IllegalArgumentException("tags must be an array");
}

for (JsonNode tagNode : tagsNode) {
    if (!tagNode.isTextual()) {
        throw new IllegalArgumentException("each tag must be a string");
    }
    String tag = tagNode.textValue();
    processTag(tag);
}
```

Nếu API cho phép array rỗng, vòng lặp không thực hiện lần nào và kết quả là danh sách rỗng. Array rỗng không phải là node thiếu hoặc null.

Với object lồng nhau:

```java
JsonNode addressNode = root.get("address");

if (addressNode == null || !addressNode.isObject()) {
    throw new IllegalArgumentException("address must be an object");
}

JsonNode cityNode = addressNode.get("city");
if (cityNode == null || !cityNode.isTextual()) {
    throw new IllegalArgumentException("address.city must be a string");
}
```

Kiểm tra từng cấp giúp lỗi chỉ rõ đường dẫn sai. Nếu cấu trúc ổn định và có nhiều trường, ánh xạ toàn bộ cây sang DTO bằng `treeToValue()` có thể gọn hơn sau khi xác nhận node gốc là object.

## 10. Không dùng giá trị mặc định một cách ngầm định

Một số overload của `asXxx()` cho phép truyền giá trị mặc định:

```java
int pageSize = root.path("pageSize").asInt(20);
String locale = root.path("locale").asText("vi-VN");
```

Điều này không sai nếu hợp đồng quy định rõ:

- `pageSize` thiếu hoặc không đọc được thì dùng 20.
- `locale` thiếu hoặc không đọc được thì dùng `vi-VN`.

Nhưng nó có thể gây lỗi nếu dữ liệu sai kiểu cần bị từ chối. Ví dụ `pageSize: "many"` bị thay bằng 20 khiến lỗi client bị che giấu.

Nên phân biệt hai mục đích:

- **Default theo hợp đồng:** thiếu trường được phép và có giá trị mặc định xác định. Có thể dùng `asInt(defaultValue)` sau khi vẫn kiểm tra những trường hợp không hợp lệ cần từ chối.
- **Validation:** trường bắt buộc hoặc phải đúng kiểu. Kiểm tra sự hiện diện, loại node và miền giá trị; nếu sai thì trả lỗi.

Ví dụ xử lý page size tùy chọn:

```java
int pageSize = 20;
JsonNode pageSizeNode = root.get("pageSize");

if (pageSizeNode != null) {
    if (!pageSizeNode.isIntegralNumber()
            || !pageSizeNode.canConvertToInt()) {
        throw new IllegalArgumentException("pageSize must be an integer");
    }

    pageSize = pageSizeNode.intValue();
}

if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("pageSize must be between 1 and 100");
}
```

Trong ví dụ, thiếu `pageSize` thì dùng 20; nhưng nếu có giá trị sai kiểu thì báo lỗi. Đây là cách tránh việc fallback che giấu payload không hợp lệ.

## 11. Tránh chuyển đổi chuỗi số ngoài ý muốn

JSON phân biệt number và string:

```json
{"quantity": 12}
```

khác với:

```json
{"quantity": "12"}
```

Nếu hợp đồng yêu cầu number, hãy kiểm tra `isNumber()` hoặc `isIntegralNumber()`. Không nên chấp nhận chuỗi chỉ vì `asInt()` có thể chuyển được một số dạng textual.

Nếu hệ thống cũ bắt buộc nhận số dạng chuỗi, hãy xử lý riêng:

```java
JsonNode quantityNode = root.get("quantity");

if (quantityNode == null) {
    throw new IllegalArgumentException("quantity is required");
}

int quantity;
if (quantityNode.isIntegralNumber() && quantityNode.canConvertToInt()) {
    quantity = quantityNode.intValue();
} else if (quantityNode.isTextual()) {
    try {
        quantity = Integer.parseInt(quantityNode.textValue());
    } catch (NumberFormatException exception) {
        throw new IllegalArgumentException("quantity must be an integer", exception);
    }
} else {
    throw new IllegalArgumentException("quantity must be an integer number or numeric string");
}
```

Code trên thể hiện rõ hai dạng đầu vào được phép. Nếu chuỗi có khoảng trắng, dấu cộng hoặc định dạng khác, hãy quyết định có trim hoặc cho phép hay không theo hợp đồng; đừng để coercion ngầm quyết định thay ứng dụng.

## 12. Chuyển JsonNode sang DTO sau khi kiểm tra

Tree Model không buộc ứng dụng phải tự đọc từng trường. Khi đã xác định cấu trúc node phù hợp, có thể dùng `treeToValue()`:

```java
if (!root.isObject()) {
    throw new IllegalArgumentException("request must be a JSON object");
}

JsonNode dataNode = root.get("data");
if (dataNode == null || !dataNode.isObject()) {
    throw new IllegalArgumentException("data must be an object");
}

StudentDto student = mapper.treeToValue(dataNode, StudentDto.class);
```

Nếu cấu trúc lồng nhau có kiểu generic, có thể dùng `readerFor(JavaType)` với `treeAsTokens()` hoặc `convertValue()` cùng kiểu đích phù hợp. Hãy tránh chuyển đổi sang `Object.class` rồi ép kiểu vì điều đó làm mất thông tin kiểu và đưa rủi ro `ClassCastException` về sau.

Ví dụ với kiểu collection:

```java
JavaType studentListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, StudentDto.class);

List<StudentDto> students = mapper.readerFor(studentListType)
    .readValue(root.path("students").traverse(mapper));
```

Trước khi ánh xạ, vẫn cần xác nhận `students` tồn tại và là array nếu hợp đồng yêu cầu. Cách đọc cụ thể có thể thay đổi tùy phiên bản Jackson; với code đơn giản, `convertValue()` cũng có thể được dùng khi đã có kiểu đích:

```java
List<StudentDto> students = mapper.convertValue(
    root.path("students"),
    new TypeReference<List<StudentDto>>() {}
);
```

`convertValue()` thực hiện chuyển đổi trong bộ nhớ; nó không thay thế validation cấu trúc. Hãy kiểm tra node đầu vào trước khi chuyển đổi để tránh một giá trị sai bị coercion ngoài ý muốn.

## 13. Ví dụ thực tế: đọc webhook có trường tùy chọn

Giả sử webhook có dạng:

```json
{
  "eventType": "profile.updated",
  "userId": 23,
  "payload": {
    "displayName": "Lan",
    "bio": null,
    "active": true
  }
}
```

Ứng dụng cần:

- `eventType` là chuỗi bắt buộc.
- `userId` là số nguyên dương trong miền `long`.
- `payload` là object.
- `displayName` nếu có phải là chuỗi.
- `bio` phân biệt thiếu, null và chuỗi.
- `active` nếu có phải là boolean.

Ví dụ xử lý:

```java
JsonNode root = mapper.readTree(json);

if (!root.isObject()) {
    throw new IllegalArgumentException("Webhook must be an object");
}

JsonNode eventTypeNode = root.get("eventType");
if (eventTypeNode == null || !eventTypeNode.isTextual()) {
    throw new IllegalArgumentException("eventType must be a string");
}
String eventType = eventTypeNode.textValue();

JsonNode userIdNode = root.get("userId");
if (userIdNode == null || !userIdNode.isIntegralNumber()
        || !userIdNode.canConvertToLong()) {
    throw new IllegalArgumentException("userId must be a long integer");
}
long userId = userIdNode.longValue();
if (userId <= 0) {
    throw new IllegalArgumentException("userId must be positive");
}

JsonNode payload = root.get("payload");
if (payload == null || !payload.isObject()) {
    throw new IllegalArgumentException("payload must be an object");
}

JsonNode displayNameNode = payload.get("displayName");
if (displayNameNode != null && !displayNameNode.isTextual()) {
    throw new IllegalArgumentException("displayName must be a string");
}

JsonNode bioNode = payload.get("bio");
boolean bioProvided = bioNode != null;
String bio = null;
if (bioProvided && !bioNode.isNull()) {
    if (!bioNode.isTextual()) {
        throw new IllegalArgumentException("bio must be a string or null");
    }
    bio = bioNode.textValue();
}

JsonNode activeNode = payload.get("active");
Boolean active = null;
if (activeNode != null) {
    if (!activeNode.isBoolean()) {
        throw new IllegalArgumentException("active must be a boolean");
    }
    active = activeNode.booleanValue();
}
```

Trong ví dụ, `bioProvided` phân biệt khóa thiếu với null tường minh. `active` dùng `Boolean` vì trường có thể chưa được cung cấp; không dùng `boolean` nếu cần giữ trạng thái đó.

Code ví dụ tập trung minh họa việc kiểm tra loại node. Trong ứng dụng thực tế, nên chuyển kết quả thành DTO/command có kiểu rõ ràng, gom validation vào thành phần phù hợp và tránh để một controller lớn chứa toàn bộ logic parse.

## 14. Kiểm thử việc đọc kiểu dữ liệu

Nên kiểm thử cả payload hợp lệ và payload sai kiểu. Ví dụ với JUnit 5:

```java
class JsonNodeTypeTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void distinguishesMissingFromExplicitNull() throws Exception {
        JsonNode missingRoot = mapper.readTree("{}");
        JsonNode nullRoot = mapper.readTree("{\"note\":null}");

        assertFalse(missingRoot.has("note"));
        assertTrue(nullRoot.has("note"));
        assertTrue(nullRoot.get("note").isNull());
    }

    @Test
    void rejectsDecimalWhenIntegerIsRequired() throws Exception {
        JsonNode root = mapper.readTree("{\"quantity\":3.5}");
        JsonNode quantity = root.get("quantity");

        assertFalse(quantity.isIntegralNumber());
    }

    @Test
    void checksIntegerRangeBeforeConversion() throws Exception {
        JsonNode root = mapper.readTree("{\"quantity\":2147483648}");
        JsonNode quantity = root.get("quantity");

        assertTrue(quantity.isIntegralNumber());
        assertFalse(quantity.canConvertToInt());
        assertTrue(quantity.canConvertToLong());
    }
}
```

Ngoài ra, nên kiểm tra:

- Trường bị thiếu.
- Trường có JSON null.
- Trường có kiểu đúng.
- Trường có kiểu sai nhưng có thể bị `asXxx()` chuyển đổi.
- Số vượt miền `int` hoặc `long`.
- Chuỗi rỗng so với null.
- Array/object rỗng so với node sai kiểu.
- Boolean `false` so với trường thiếu.
- Các đường dẫn lồng nhau không tồn tại.

Test cần chạy với `ObjectMapper` thực tế của ứng dụng, bao gồm module và feature đã cấu hình. Cấu hình coercion hoặc null có thể làm hành vi khác với mapper mặc định trong ví dụ.

## 15. Những lỗi thường gặp

### Gọi asInt() cho trường bắt buộc mà không kiểm tra

Giá trị sai kiểu hoặc thiếu có thể trở thành `0`, che giấu payload lỗi. Hãy kiểm tra `isIntegralNumber()` và `canConvertToInt()` trước.

### Dùng hasNonNull() khi cần phân biệt null

`hasNonNull()` trả false cho cả khóa thiếu và khóa null. Dùng `has()` rồi `isNull()` nếu hai trạng thái có ý nghĩa khác nhau.

### Dùng asText() cho mọi loại node

`asText()` có thể tạo biểu diễn chuỗi từ số hoặc boolean. Nếu hợp đồng yêu cầu JSON string, kiểm tra `isTextual()` và dùng `textValue()`.

### Dùng asBoolean() và coi false là mặc định an toàn

Boolean `false` là giá trị hợp lệ. Nếu node thiếu hoặc sai kiểu cũng cho ra false, ứng dụng không thể phân biệt client gửi false hay gửi payload lỗi. Kiểm tra `isBoolean()` trước.

### Chuyển số thập phân thành số nguyên

Không gọi `intValue()` cho node `3.9` nếu hợp đồng yêu cầu số nguyên. Kiểm tra `isIntegralNumber()` trước khi chuyển.

### Gọi decimalValue() sau khi đã parse thành DoubleNode

Chuyển đổi sau khi mất chính xác không thể khôi phục token gốc. Cấu hình `USE_BIG_DECIMAL_FOR_FLOATS` trước khi đọc hoặc ánh xạ trực tiếp vào `BigDecimal`.

### Dùng path() rồi lấy giá trị ngay

`path()` tránh null Java nhưng có thể trả `MissingNode`. Nếu trường bắt buộc, kiểm tra node trước khi sử dụng.

## 16. Quy trình đọc dữ liệu an toàn với Tree Model

Khi đọc một payload không hoàn toàn tin cậy hoặc có cấu trúc động, có thể áp dụng trình tự:

1. Parse JSON thành `JsonNode` bằng mapper đã cấu hình.
2. Kiểm tra node gốc có phải object/array đúng hợp đồng không.
3. Với từng trường, kiểm tra sự hiện diện bằng `get()` hoặc `has()`.
4. Phân biệt missing, null và giá trị cụ thể.
5. Kiểm tra loại node bằng `isTextual()`, `isIntegralNumber()`, `isBoolean()`…
6. Với số, kiểm tra range trước khi chuyển sang kiểu nguyên thủy.
7. Dùng `textValue()`, `intValue()`, `longValue()`, `decimalValue()` hoặc `booleanValue()` sau khi đã xác nhận loại.
8. Chỉ dùng fallback khi default được quy định trong hợp đồng; không dùng fallback để che dữ liệu sai.
9. Ánh xạ sang DTO/command có kiểu rõ ràng và thực hiện validation nghiệp vụ.
10. Trả lỗi có ngữ cảnh nếu payload không hợp lệ; tránh log dữ liệu nhạy cảm nguyên vẹn.

## 17. Bảng ghi nhớ các API JsonNode

| Mục đích | API nên dùng | Điều cần lưu ý |
|---|---|---|
| Kiểm tra object | `isObject()` | Không giả định root luôn là object |
| Kiểm tra array | `isArray()` | Array rỗng vẫn là array hợp lệ |
| Kiểm tra chuỗi | `isTextual()` + `textValue()` | Không dùng `asText()` thay cho kiểm tra kiểu |
| Kiểm tra số nguyên | `isIntegralNumber()` | `isNumber()` còn bao gồm số thập phân |
| Kiểm tra số bất kỳ | `isNumber()` | Cần kiểm tra thêm miền và độ chính xác |
| Kiểm tra miền int/long | `canConvertToInt()`, `canConvertToLong()` | Kiểm tra trước khi gọi `intValue()`/`longValue()` |
| Đọc số thập phân chính xác | `decimalValue()` | Cấu hình BigDecimal trước khi parse nếu cần giữ độ chính xác |
| Kiểm tra boolean | `isBoolean()` + `booleanValue()` | Không để node sai kiểu biến thành false |
| Phân biệt khóa thiếu/null | `has()`, `get()`, `isNull()` | `hasNonNull()` gộp thiếu và null |
| Truy cập đường dẫn an toàn | `path()` + `isMissingNode()` | Không bỏ qua việc kiểm tra node thiếu |
| Lấy loại node | `getNodeType()` hoặc các `isXxx()` | Dùng loại node để chọn phép chuyển đổi phù hợp |

Tree Model cho phép đọc JSON linh hoạt, nhưng các phương thức chuyển đổi tiện ích có thể che giấu kiểu dữ liệu sai bằng cách coercion hoặc trả giá trị mặc định. Khi hợp đồng yêu cầu một kiểu cụ thể, hãy xác nhận node trước rồi mới lấy giá trị. Đặc biệt, phân biệt node thiếu với JSON null, kiểm tra miền số và chỉ dùng fallback khi nó là một phần có chủ đích của hợp đồng. Cách làm này giúp dữ liệu không định kiểu vẫn được xử lý có kiểm soát trước khi đi vào DTO và logic nghiệp vụ.
