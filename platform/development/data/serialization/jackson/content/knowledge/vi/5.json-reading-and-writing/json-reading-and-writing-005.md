# Xử lý đối tượng gốc, mảng gốc và giá trị vô hướng

Khi đọc hoặc ghi JSON bằng Jackson, điều đầu tiên cần xác định là **kiểu giá trị nằm ở cấp cao nhất của tài liệu JSON**. Giá trị gốc đó có thể là một object, một array hoặc một giá trị vô hướng như string, number, boolean hay null.

Kiểu dữ liệu Java đích phải phù hợp với hình dạng JSON ở cấp gốc. Một JSON object thường được ánh xạ vào DTO hoặc Map; một JSON array thường được ánh xạ vào array hoặc collection; một JSON scalar thường được ánh xạ vào kiểu Java đơn giản. Nếu chọn sai kiểu đích, Jackson có thể báo lỗi mapping dù JSON hoàn toàn hợp lệ về cú pháp.

Bài học này hướng dẫn cách nhận diện, đọc, ghi và kiểm tra ba dạng giá trị gốc bằng Jackson Databind, đồng thời giải thích khi nào nên dùng tree model hoặc streaming API.

## 1. Hiểu giá trị gốc của một tài liệu JSON

Một tài liệu JSON hoàn chỉnh biểu diễn một giá trị. Theo cú pháp JSON, giá trị ở cấp gốc có thể thuộc một trong các dạng:

| Dạng giá trị gốc | Ví dụ | Kiểu Java thường dùng |
| --- | --- | --- |
| Object | `{"id": 10, "name": "An"}` | DTO, record, `Map`, `ObjectNode` |
| Array | `[{"id": 10}, {"id": 11}]` | `List<T>`, `T[]`, `ArrayNode` |
| String | `"Jackson"` | `String` |
| Number | `42` hoặc `12.50` | `Integer`, `Long`, `BigInteger`, `BigDecimal` |
| Boolean | `true` hoặc `false` | `Boolean`, `boolean` |
| Null | `null` | Java `null` hoặc `NullNode` |

Không có yêu cầu rằng mọi tài liệu JSON phải bắt đầu bằng object. Một JSON array hoặc một scalar cũng là một JSON document hợp lệ.

Cần phân biệt **giá trị gốc** với property nằm bên trong object. Ví dụ:

```json
{
  "user": {
    "id": 10,
    "name": "An"
  },
  "roles": ["READER", "EDITOR"],
  "active": true
}
```

Giá trị gốc ở đây là một object. Property `user` chứa một object lồng nhau, `roles` chứa một array và `active` chứa một boolean. Khi đọc toàn bộ tài liệu thành DTO, kiểu đích phải mô tả object gốc; không thể dùng riêng `UserDto` để đọc toàn bộ JSON trên.

Hãy luôn tự hỏi: **token đầu tiên của tài liệu là gì và kiểu Java đích đang mong đợi cấu trúc nào?** Câu hỏi này giúp định vị phần lớn lỗi mapping giữa object, array và scalar.

## 2. Xử lý object gốc

Object gốc bắt đầu bằng dấu ngoặc nhọn `{` và chứa các cặp tên property cùng giá trị. Đây là dạng thường gặp trong request/response API vì mỗi trường có tên rõ ràng.

Ví dụ:

```json
{
  "id": 101,
  "name": "Mechanical Keyboard",
  "price": 1250000.00,
  "available": true
}
```

### 2.1. Đọc object vào DTO hoặc record

Nếu cấu trúc JSON đã biết, hãy khai báo kiểu Java tương ứng:

```java
public record ProductDto(
    long id,
    String name,
    BigDecimal price,
    boolean available
) {}
```

Dùng `ObjectMapper.readValue` để deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "id": 101,
      "name": "Mechanical Keyboard",
      "price": 1250000.00,
      "available": true
    }
    """;

ProductDto product = mapper.readValue(json, ProductDto.class);
```

Jackson đọc object gốc, tìm property tương ứng và truyền các giá trị vào canonical constructor của record. Với class DTO mutable, Jackson có thể dùng constructor, field hoặc setter tùy cách class và mapper được cấu hình.

Nếu JSON có property lồng nhau, khai báo DTO lồng nhau thay vì ép toàn bộ cấu trúc thành chuỗi:

```java
public record AddressDto(String city, String country) {}

public record CustomerDto(
    long id,
    String name,
    AddressDto address
) {}
```

JSON tương ứng:

```json
{
  "id": 7,
  "name": "Minh",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

Object gốc vẫn là một `CustomerDto`. `AddressDto` chỉ đại diện cho object nằm trong property `address`.

### 2.2. Ghi DTO thành object JSON

Chiều ngược lại dùng `writeValueAsString`:

```java
ProductDto product = new ProductDto(
    101L,
    "Mechanical Keyboard",
    new BigDecimal("1250000.00"),
    true
);

String json = mapper.writeValueAsString(product);
```

Kết quả có hình dạng object:

```json
{"id":101,"name":"Mechanical Keyboard","price":1250000.00,"available":true}
```

Jackson tự chọn tên property và serializer cho từng giá trị dựa trên kiểu Java, annotation và cấu hình mapper. Nếu cần đổi tên field, bỏ qua field hoặc kiểm soát field null, dùng annotation/cấu hình tương ứng; không cần tự nối chuỗi JSON.

### 2.3. Đọc object thành Map

Khi cấu trúc chưa có DTO hoặc chỉ cần xử lý dữ liệu dạng key-value, có thể đọc object thành `Map`:

```java
Map<String, Object> values = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
```

Các object lồng nhau có thể trở thành Map lồng nhau, array trở thành List và scalar trở thành kiểu Java đơn giản. Cách này linh hoạt nhưng giảm tính an toàn kiểu: chương trình phải kiểm tra kiểu và ép kiểu khi lấy từng giá trị.

Ví dụ:

```java
Object rawPrice = values.get("price");

if (rawPrice instanceof Number number) {
    BigDecimal price = new BigDecimal(number.toString());
}
```

Với hợp đồng dữ liệu ổn định, DTO hoặc record thường dễ đọc, dễ kiểm tra và an toàn hơn Map. Không nên dùng Map chỉ vì muốn tránh khai báo kiểu dữ liệu.

## 3. Xử lý array gốc

Array gốc bắt đầu bằng dấu ngoặc vuông `[`. Mỗi phần tử trong array có thể là object, array lồng nhau hoặc scalar. Các phần tử giữ thứ tự trong JSON.

Ví dụ:

```json
[
  {"id": 101, "name": "Keyboard"},
  {"id": 102, "name": "Mouse"},
  {"id": 103, "name": "Monitor"}
]
```

### 3.1. Đọc array thành Java array

Nếu muốn dùng mảng Java có kích thước cố định sau khi đọc, truyền kiểu array:

```java
ProductDto[] products = mapper.readValue(
    json,
    ProductDto[].class
);
```

Jackson tạo một mảng Java với mỗi phần tử được ánh xạ thành `ProductDto`. Có thể truy cập bằng chỉ số:

```java
ProductDto first = products[0];
int count = products.length;
```

Kiểu array hữu ích khi API hoặc thư viện yêu cầu mảng Java. Trong ứng dụng nghiệp vụ, collection như List thường thuận tiện hơn khi thêm, xóa hoặc truyền dữ liệu giữa các lớp.

### 3.2. Đọc array thành List có generic type

Cách thường dùng là `TypeReference`:

```java
List<ProductDto> products = mapper.readValue(
    json,
    new TypeReference<List<ProductDto>>() {}
);
```

Không nên viết:

```java
List<ProductDto> products = mapper.readValue(json, List.class);
```

`List.class` chỉ thể hiện kiểu raw List, không giữ thông tin generic `ProductDto`. Jackson không được cung cấp đầy đủ kiểu phần tử và có thể tạo các Map/giá trị untyped thay vì các DTO mong muốn.

Một cách khác là tạo `JavaType`:

```java
JavaType productListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, ProductDto.class);

List<ProductDto> products = mapper.readValue(json, productListType);
```

Dùng `TypeReference` thuận tiện cho một kiểu generic được khai báo ngay tại chỗ. Dùng `JavaType` hữu ích khi cần xây dựng kiểu động từ các class hoặc kiểu generic khác nhau.

### 3.3. Array rỗng và phần tử null

Array rỗng là một giá trị hợp lệ:

```json
[]
```

Đọc thành List sẽ cho collection rỗng; đọc thành array sẽ cho mảng có độ dài bằng 0. Nó khác với JSON root `null` và khác với input không có nội dung.

Array cũng có thể chứa phần tử null:

```json
[
  {"id": 101, "name": "Keyboard"},
  null,
  {"id": 103, "name": "Monitor"}
]
```

Nếu kiểu phần tử là DTO tham chiếu, phần tử tương ứng có thể là Java `null`. Vì vậy, khi duyệt collection, cần xác định hợp đồng có cho phép phần tử null hay không và kiểm tra trước khi truy cập thuộc tính.

### 3.4. Ghi array hoặc List thành JSON

Jackson ghi Java array và collection thành JSON array:

```java
List<ProductDto> products = List.of(
    new ProductDto(101L, "Keyboard", new BigDecimal("1250000.00"), true),
    new ProductDto(102L, "Mouse", new BigDecimal("350000.00"), true)
);

String json = mapper.writeValueAsString(products);
```

Kết quả có dạng:

```json
[
  {
    "id": 101,
    "name": "Keyboard",
    "price": 1250000.00,
    "available": true
  },
  {
    "id": 102,
    "name": "Mouse",
    "price": 350000.00,
    "available": true
  }
]
```

Nếu muốn định dạng dễ đọc, có thể tạo writer có bật pretty printing:

```java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
String formattedJson = prettyWriter.writeValueAsString(products);
```

Pretty printing chỉ thay đổi khoảng trắng và cách xuống dòng. Nó không thay đổi kiểu root hoặc ý nghĩa dữ liệu.

## 4. Xử lý giá trị vô hướng ở cấp gốc

Scalar là một giá trị đơn lẻ, không phải object hoặc array. JSON có bốn nhóm scalar chính: string, number, boolean và null.

### 4.1. String gốc

JSON string phải được đặt trong dấu ngoặc kép:

```json
"Jackson"
```

Đọc bằng kiểu `String`:

```java
String libraryName = mapper.readValue(
    "\"Jackson\"",
    String.class
);
```

Ghi một Java String bằng Jackson:

```java
String json = mapper.writeValueAsString("Jackson");
```

Giá trị JSON thu được là:

```json
"Jackson"
```

Điểm cần nhớ: `writeValueAsString("Jackson")` trả về một chuỗi Java chứa văn bản JSON có dấu ngoặc kép. Nó không trả về nội dung thô `Jackson`. Jackson chịu trách nhiệm escape ký tự đặc biệt và tạo JSON string hợp lệ.

Ví dụ, một Java String chứa dấu ngoặc kép hoặc ký tự xuống dòng sẽ được Jackson escape theo quy tắc JSON. Không tự ghép dấu ngoặc kép hoặc tự thay thế ký tự để tạo JSON vì rất dễ tạo dữ liệu sai cú pháp.

### 4.2. Number gốc

JSON number có thể là số nguyên hoặc số thập phân:

```json
42
```

```json
12.50
```

Chọn kiểu Java theo miền giá trị:

| JSON number | Kiểu Java thường dùng | Ghi chú |
| --- | --- | --- |
| Số nguyên nhỏ | `Integer` / `int` | Kiểm tra giới hạn 32-bit |
| Số nguyên lớn | `Long` / `long` | Kiểm tra giới hạn 64-bit |
| Số nguyên rất lớn | `BigInteger` | Không bị giới hạn ở 64-bit |
| Số thập phân cần chính xác | `BigDecimal` | Phù hợp với tiền và dữ liệu thập phân chính xác |
| Số gần đúng phục vụ tính toán khoa học | `Double` / `double` | Dùng biểu diễn dấu phẩy động nhị phân |

Ví dụ đọc một số nguyên:

```java
Integer quantity = mapper.readValue("42", Integer.class);
```

Ví dụ đọc số thập phân chính xác:

```java
BigDecimal amount = mapper.readValue("12.50", BigDecimal.class);
```

Khi làm việc với tiền hoặc giá trị cần giữ chính xác phần thập phân, nên dùng `BigDecimal`. Tránh đọc qua `double` rồi mới chuyển sang `BigDecimal`, vì sai số nhị phân có thể đã xuất hiện trước khi chuyển đổi.

Jackson có thể chuyển đổi số giữa các kiểu trong một số trường hợp, nhưng việc chuyển đổi có thể mất độ chính xác hoặc vượt miền biểu diễn. Hãy chọn kiểu đích rõ ràng và kiểm thử các giá trị biên, số âm, số rất lớn và số có nhiều chữ số thập phân.

### 4.3. Boolean gốc

Boolean JSON chỉ có hai giá trị:

```json
true
```

```json
false
```

Đọc:

```java
Boolean enabled = mapper.readValue("true", Boolean.class);
```

Ghi:

```java
String json = mapper.writeValueAsString(Boolean.TRUE);
```

Kết quả là literal JSON `true`, không có dấu ngoặc kép. Nếu ghi chuỗi Java `"true"` thì kết quả là JSON string `"true"`; hai giá trị này khác kiểu và không nên nhầm lẫn.

### 4.4. Null ở cấp gốc

JSON literal `null` biểu diễn sự vắng mặt của một giá trị:

```json
null
```

Khi đọc vào kiểu tham chiếu:

```java
ProductDto product = mapper.readValue("null", ProductDto.class);
Integer quantity = mapper.readValue("null", Integer.class);
```

Kết quả của các biến kiểu tham chiếu là Java `null`. Khi ghi Java null:

```java
String json = mapper.writeValueAsString(null);
```

Jackson ghi literal JSON `null`.

Cần phân biệt ba tình huống:

| Tình huống | Ý nghĩa |
| --- | --- |
| JSON root là `null` | Tài liệu có một giá trị JSON hợp lệ, giá trị đó là null |
| JSON object có property `"name": null` | Object tồn tại và property name có giá trị null |
| Input rỗng hoặc chỉ có khoảng trắng | Không có giá trị JSON để đọc; đây không phải literal null |

Khi đọc vào kiểu primitive như `int` hoặc `boolean`, Java không có biểu diễn null. Jackson có các feature điều khiển việc nhận null cho primitive; tùy cấu hình, giá trị có thể được xử lý như giá trị mặc định hoặc bị từ chối. Với dữ liệu đầu vào cần phân biệt rõ null, nên dùng wrapper như `Integer` hoặc `Boolean` và quy định hành vi trong hợp đồng.

## 5. Chọn kiểu đích phù hợp với root JSON

Jackson không tự biến mọi hình dạng JSON thành mọi kiểu Java. Kiểu đích phải phản ánh cấu trúc gốc.

| JSON root | Kiểu đích phù hợp | Ví dụ API |
| --- | --- | --- |
| Object | DTO/record | `readValue(json, ProductDto.class)` |
| Object | Map | `readValue(json, new TypeReference<Map<String, Object>>() {})` |
| Array | Java array | `readValue(json, ProductDto[].class)` |
| Array | List generic | `readValue(json, new TypeReference<List<ProductDto>>() {})` |
| String | String | `readValue(json, String.class)` |
| Number | Integer, Long, BigDecimal... | `readValue(json, BigDecimal.class)` |
| Boolean | Boolean | `readValue(json, Boolean.class)` |
| Bất kỳ root JSON nào | JsonNode | `readTree(json)` |

Ví dụ về mismatch:

```java
// JSON bắt đầu bằng '[' nhưng kiểu đích lại là một object.
ProductDto product = mapper.readValue(arrayJson, ProductDto.class);
```

Jackson thường báo lỗi dạng `MismatchedInputException` vì token gốc là `START_ARRAY` trong khi deserializer của `ProductDto` mong đợi object.

Tương tự, không thể đọc JSON string `"hello"` thành một DTO chỉ vì DTO có một property tên `value`. Nếu hợp đồng yêu cầu object, JSON phải có hình dạng `{"value":"hello"}` hoặc ứng dụng phải dùng một kiểu scalar phù hợp.

Không nên xử lý mismatch bằng cách tắt hàng loạt feature hoặc bắt exception rồi trả về object rỗng. Hãy xác nhận lại hình dạng JSON thực tế, kiểu đích và hợp đồng API.

## 6. Dùng JsonNode khi chưa biết root shape

Khi input có thể là object, array hoặc scalar và chương trình cần quyết định cách xử lý sau khi đọc, tree model là lựa chọn phù hợp.

```java
JsonNode root = mapper.readTree(json);

if (root == null) {
    throw new IllegalArgumentException("JSON input is empty");
}

if (root.isObject()) {
    // Xử lý object gốc.
} else if (root.isArray()) {
    // Xử lý array gốc.
} else if (root.isTextual()) {
    // Xử lý string gốc.
} else if (root.isNumber()) {
    // Xử lý number gốc.
} else if (root.isBoolean()) {
    // Xử lý boolean gốc.
} else if (root.isNull()) {
    // Xử lý JSON null.
}
```

`readTree` trả về cây node. Với JSON object, root thường là `ObjectNode`; với array là `ArrayNode`; với string, number, boolean và null là các node giá trị tương ứng.

Có thể kiểm tra kiểu node cụ thể bằng các method như:

- `isObject()`
- `isArray()`
- `isTextual()`
- `isNumber()`
- `isBoolean()`
- `isNull()`
- `isMissingNode()`

`MissingNode` khác `NullNode`. Một node missing biểu thị đường dẫn không tồn tại trong cây; NullNode biểu thị một giá trị null có mặt trong JSON.

### 6.1. Đọc property khi root là object

Sau khi xác nhận root là object, có thể lấy property:

```java
JsonNode idNode = root.path("id");

if (idNode.isMissingNode()) {
    throw new IllegalArgumentException("Missing id");
}

if (idNode.isNull()) {
    throw new IllegalArgumentException("id must not be null");
}

long id = idNode.asLong();
```

`path` an toàn hơn `get` khi property không tồn tại vì trả về MissingNode thay vì Java null. Tuy nhiên, các method chuyển kiểu như `asLong()` có thể dùng giá trị mặc định khi node không phù hợp. Nếu cần kiểm soát chặt, hãy kiểm tra `isIntegralNumber()` hoặc kiểu node trước khi chuyển.

### 6.2. Duyệt array root

Khi root là array:

```java
for (JsonNode item : root) {
    if (item == null || item.isNull()) {
        continue;
    }

    if (!item.isObject()) {
        throw new IllegalArgumentException(
            "Each array item must be an object"
        );
    }

    long id = item.path("id").asLong();
}
```

Tree model cho phép kiểm tra từng phần tử trước khi chuyển sang DTO. Nếu cấu trúc đã biết và ổn định, deserialize trực tiếp thành `List<ProductDto>` thường ngắn gọn hơn.

### 6.3. Chuyển node thành DTO

Sau khi xác nhận node có hình dạng object phù hợp:

```java
ProductDto product = mapper.treeToValue(root, ProductDto.class);
```

Có thể dùng `convertValue` khi chuyển đổi giữa các giá trị Java trong bộ nhớ:

```java
ProductDto product = mapper.convertValue(sourceMap, ProductDto.class);
```

`treeToValue` diễn đạt rõ việc chuyển từ JSON tree sang kiểu Java. `convertValue` dùng cơ chế databind để chuyển giữa các biểu diễn giá trị mà không cần tự ghi ra chuỗi JSON rồi đọc lại.

## 7. Làm việc với kiểu Object và dữ liệu không định kiểu

Có thể đọc JSON vào `Object.class`:

```java
Object value = mapper.readValue(json, Object.class);
```

Jackson dùng mapping untyped để tạo các giá trị Java tổng quát. Thông thường:

- JSON object trở thành Map.
- JSON array trở thành List.
- JSON string trở thành String.
- JSON boolean trở thành Boolean.
- JSON number trở thành kiểu số phù hợp với cấu hình và giá trị.
- JSON null trở thành Java null.

Cách này tiện khi dữ liệu thay đổi, nhưng chương trình không còn biết chắc kiểu cụ thể của từng phần tử. Cần dùng `instanceof` hoặc kiểm tra kiểu trước khi ép kiểu.

Nếu cần duyệt dữ liệu JSON động, `JsonNode` thường biểu đạt ý định rõ hơn `Object` vì node cung cấp sẵn các method kiểm tra object, array, number, string, boolean và null.

Nếu cấu trúc đã ổn định, DTO/record và kiểu generic cụ thể vẫn là lựa chọn ưu tiên để tận dụng compiler và IDE kiểm tra kiểu.

## 8. Root wrapping: object có tên bao bên ngoài

Một số hợp đồng JSON yêu cầu object gốc được bọc trong một property có tên cố định. Ví dụ:

```json
{
  "product": {
    "id": 101,
    "name": "Keyboard"
  }
}
```

Đây là một object gốc có property `product`, trong đó chứa object DTO. Nó khác với JSON object không bọc:

```json
{
  "id": 101,
  "name": "Keyboard"
}
```

Jackson có tính năng root wrapping thông qua `@JsonRootName`, `SerializationFeature.WRAP_ROOT_VALUE` và `DeserializationFeature.UNWRAP_ROOT_VALUE`.

Ví dụ:

```java
@JsonRootName("product")
public record ProductDto(long id, String name) {}

ObjectMapper mapper = new ObjectMapper()
    .enable(SerializationFeature.WRAP_ROOT_VALUE)
    .enable(DeserializationFeature.UNWRAP_ROOT_VALUE);
```

Khi serialize, Jackson bọc object theo tên root:

```json
{
  "product": {
    "id": 101,
    "name": "Keyboard"
  }
}
```

Khi deserialize với chế độ unwrap, Jackson mong đợi wrapper có tên phù hợp với root name. Nếu wrapper không có hoặc tên khác, thao tác có thể thất bại.

Không bật root wrapping chỉ để làm JSON trông có cấu trúc hơn. Hãy dùng khi hợp đồng bên ngoài thực sự yêu cầu wrapper đó. Với API mới, một DTO request/response có property rõ ràng thường dễ mở rộng hơn việc bật cấu hình root wrapping toàn cục.

## 9. Một tài liệu JSON và một chuỗi nhiều giá trị JSON

Một JSON document thông thường có đúng một giá trị gốc. Ví dụ sau là một tài liệu JSON hợp lệ:

```json
{"id": 1}
```

Còn nội dung sau là hai giá trị JSON nối tiếp nhau, không phải một object hay array duy nhất:

```text
{"id": 1}
{"id": 2}
```

Nếu muốn biểu diễn hai object trong một JSON document, hãy dùng array:

```json
[
  {"id": 1},
  {"id": 2}
]
```

Với một luồng dữ liệu có nhiều JSON value nối tiếp nhau, hãy dùng API đọc sequence/streaming phù hợp thay vì giả định một lần `readValue` sẽ đọc toàn bộ như một array.

Ví dụ dùng `MappingIterator`:

```java
ObjectReader reader = mapper.readerFor(ProductDto.class);

try (MappingIterator<ProductDto> products =
         reader.readValues(inputStream)) {

    while (products.hasNextValue()) {
        ProductDto product = products.nextValue();
        // Xử lý từng object.
    }
}
```

Cách này phù hợp với luồng nhiều JSON object độc lập. Với định dạng NDJSON/JSON Lines, mỗi dòng thường chứa một JSON document riêng. Hãy kiểm tra quy ước framing, encoding và xử lý dòng lỗi của nguồn dữ liệu.

Nếu hợp đồng yêu cầu đúng một root value, có thể bật:

```java
mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Feature này giúp từ chối nội dung còn token phía sau giá trị gốc đã đọc, tránh vô tình chấp nhận một chuỗi có nhiều root value trong ngữ cảnh chỉ mong đợi một document.

## 10. Chọn hình dạng JSON cho API

Việc chọn object, array hay scalar ở cấp gốc là quyết định của hợp đồng dữ liệu, không chỉ là chi tiết triển khai Jackson.

| Hình dạng | Khi phù hợp | Điểm cần cân nhắc |
| --- | --- | --- |
| Object | Request/response có nhiều trường hoặc có khả năng mở rộng | Dễ thêm metadata, version, trạng thái và các field tùy chọn |
| Array | Endpoint trả về danh sách phần tử thuần túy | Không có chỗ trực tiếp cho metadata phân trang nếu không đổi cấu trúc |
| Scalar | Endpoint chỉ trả một giá trị đơn giản, hợp đồng rất ổn định | Khó mở rộng thêm metadata mà vẫn giữ nguyên hình dạng |
| Object chứa array | Danh sách cần metadata như total, page, next cursor | Thêm một lớp DTO nhưng hợp đồng rõ ràng và mở rộng tốt |

Ví dụ response danh sách đơn giản:

```json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
```

Nếu cần thông tin phân trang, object bao ngoài thường phù hợp hơn:

```json
{
  "items": [
    {"id": 1, "name": "An"},
    {"id": 2, "name": "Binh"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 135
}
```

Lựa chọn hình dạng root ảnh hưởng trực tiếp đến client. Đổi từ array root sang object có property `items` là thay đổi hợp đồng, vì vậy cần versioning hoặc kế hoạch tương thích nếu API đã được sử dụng.

### 10.1. Lưu ý khi trả dữ liệu qua Spring MVC

Khi gọi Jackson trực tiếp, `writeValueAsString("ok")` tạo JSON string `"ok"`. Tuy nhiên, trong Spring MVC, method controller trả về Java `String` có thể được `StringHttpMessageConverter` xử lý và gửi dưới dạng văn bản thuần, tùy cấu hình converter và content negotiation.

Vì vậy, không nên suy ra rằng mọi giá trị trả về từ `@RestController` đều chắc chắn đi qua Jackson. Nếu API cần trả JSON scalar, hãy kiểm tra converter được chọn, Content-Type và body thực tế bằng integration test. Có thể trả một kiểu JSON node như `TextNode` để biểu diễn rõ JSON string, hoặc dùng DTO/object nếu hợp đồng cần mở rộng.

Với DTO và collection, Spring Boot thường dùng Jackson message converter khi cấu hình phù hợp. Dù vậy, test qua HTTP vẫn là cách xác nhận chính xác hình dạng response mà client nhận được.

## 11. Lỗi thường gặp khi đọc object, array và scalar

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mong đợi DTO nhưng nhận `START_ARRAY` | JSON root là array | Đổi kiểu đích thành array/List hoặc xác minh API gửi sai shape |
| Mong đợi List nhưng nhận `START_OBJECT` | JSON root là object | Dùng DTO/Map hoặc kiểm tra wrapper/contract |
| Mong đợi String nhưng JSON bắt đầu bằng `START_OBJECT` | Root là object, không phải JSON string | Dùng DTO/JsonNode hoặc sửa payload theo hợp đồng |
| Không đọc được List có phần tử DTO | Dùng raw `List.class` và mất generic type | Dùng `TypeReference<List<T>>` hoặc `JavaType` |
| JSON null cho ra Java null | Đây là mapping bình thường cho kiểu tham chiếu | Kiểm tra null trước khi truy cập thuộc tính |
| JSON array có phần tử null | Payload cho phép null ở từng phần tử | Xác định có chấp nhận phần tử null không |
| Số bị tràn hoặc mất độ chính xác | Kiểu Java đích không phù hợp | Dùng Long, BigInteger hoặc BigDecimal theo miền giá trị |
| Chuỗi chứa dấu ngoặc kép làm JSON lỗi | Tự ghép JSON string hoặc escape sai | Để Jackson serialize String |
| Có dữ liệu sau root nhưng vẫn được chấp nhận | Chưa kiểm tra trailing tokens | Cân nhắc FAIL_ON_TRAILING_TOKENS |
| Controller trả String nhưng body không có dấu ngoặc kép | Spring chọn converter văn bản | Kiểm tra converter và Content-Type qua integration test |

### 11.1. Phân biệt lỗi cú pháp và lỗi shape

Hai loại lỗi cần được xử lý khác nhau:

- **Lỗi cú pháp**: JSON thiếu dấu ngoặc, dấu phẩy hoặc escape không hợp lệ. Parser không thể tạo token hợp lệ.
- **Lỗi shape/type**: JSON hợp lệ nhưng root hoặc property không khớp với kiểu Java đích. Ví dụ JSON root là array nhưng code yêu cầu một DTO.

Khi gặp lỗi mapping, đọc thông tin về token thực tế và token mong đợi trong exception. Điều này thường cho biết ngay chương trình đang nhầm object, array hay scalar.

### 11.2. Không biến mọi root thành String để né mapping

Một cách xử lý sai thường gặp là đọc mọi payload vào String rồi tự cắt chuỗi hoặc parse thủ công. Cách này làm mất lợi ích của Jackson và dễ gây lỗi escape, Unicode, số thập phân hoặc dữ liệu lồng nhau.

Nếu cấu trúc đã biết, bind vào DTO/array/List/scalar tương ứng. Nếu cấu trúc chưa biết, đọc vào JsonNode rồi kiểm tra root shape. Nếu cần xử lý luồng lớn, dùng streaming API.

## 12. Kiểm thử từng dạng root

Một bộ test nên kiểm tra cả hình dạng root và giá trị biên. Ví dụ với DTO đơn giản:

```java
public record ProductDto(long id, String name) {}
```

### 12.1. Test object root

```java
@Test
void readsObjectRoot() throws Exception {
    String json = """
        {"id": 1, "name": "Keyboard"}
        """;

    ProductDto product = mapper.readValue(json, ProductDto.class);

    assertEquals(1L, product.id());
    assertEquals("Keyboard", product.name());
}
```

### 12.2. Test array root

```java
@Test
void readsArrayRoot() throws Exception {
    String json = """
        [
          {"id": 1, "name": "Keyboard"},
          {"id": 2, "name": "Mouse"}
        ]
        """;

    List<ProductDto> products = mapper.readValue(
        json,
        new TypeReference<List<ProductDto>>() {}
    );

    assertEquals(2, products.size());
    assertEquals("Mouse", products.get(1).name());
}
```

### 12.3. Test scalar root

```java
@Test
void readsScalarRoots() throws Exception {
    String text = mapper.readValue("\"Jackson\"", String.class);
    Integer number = mapper.readValue("42", Integer.class);
    Boolean flag = mapper.readValue("true", Boolean.class);

    assertEquals("Jackson", text);
    assertEquals(42, number);
    assertTrue(flag);
}
```

### 12.4. Test JSON null và input rỗng

```java
@Test
void readsJsonNullAsNullReference() throws Exception {
    ProductDto product = mapper.readValue("null", ProductDto.class);

    assertNull(product);
}
```

Với input rỗng, hãy xác định hành vi mong muốn của ứng dụng và kiểm thử riêng. Không nên gộp input rỗng với JSON literal null vì chúng có ý nghĩa khác nhau trong giao thức.

Ngoài các test riêng lẻ, nên có test round-trip cho từng shape: Java object → JSON object → DTO, Java List → JSON array → List, Java scalar → JSON scalar → kiểu Java tương ứng.

## 13. Bài thực hành tổng hợp

Xây dựng một chương trình đọc ba loại JSON document:

1. Object root mô tả một sản phẩm.
2. Array root mô tả danh sách sản phẩm.
3. Scalar root chứa mã trạng thái hoặc một giá trị số.

Thực hiện lần lượt:

- Tạo DTO/record cho object sản phẩm.
- Đọc object root bằng `readValue` và ghi lại bằng `writeValueAsString`.
- Đọc array root thành `ProductDto[]` và `List<ProductDto>`.
- Đọc string, number, boolean và null root vào kiểu Java tương ứng.
- Thử đọc một array root bằng kiểu DTO để quan sát lỗi shape.
- Dùng `readTree` để nhận diện root shape trước khi chọn cách xử lý.
- Thử array rỗng và array có phần tử null.
- Thử số thập phân với `BigDecimal`.
- Bật `FAIL_ON_TRAILING_TOKENS` và kiểm tra input có hai root value nối tiếp.
- Nếu làm API Spring Boot, kiểm tra body và Content-Type khi controller trả DTO, List và String.

Bài thực hành hoàn thành khi có thể nhìn vào JSON và chọn đúng kiểu Java đích, giải thích được vì sao mapping thành công hoặc thất bại, và kiểm soát được hợp đồng dữ liệu ở cấp root.

## 14. Nguyên tắc ghi nhớ

- Một JSON document có một giá trị gốc; giá trị đó có thể là object, array, string, number, boolean hoặc null.
- Object root thường ánh xạ vào DTO/record hoặc Map.
- Array root thường ánh xạ vào Java array hoặc collection có generic type rõ ràng.
- Scalar root ánh xạ vào kiểu Java đơn giản; String JSON vẫn phải có dấu ngoặc kép trong payload.
- JSON null là một giá trị hợp lệ và khác với input rỗng.
- Dùng TypeReference hoặc JavaType để giữ generic type của collection.
- Dùng JsonNode khi cần kiểm tra root shape động; dùng streaming khi cần xử lý sequence hoặc dữ liệu lớn.
- Root wrapping là tùy chọn theo hợp đồng, không phải cấu trúc mặc định của mọi object.
- Kiểm thử đúng kiểu root, null, array rỗng, phần tử null, số biên và trailing tokens.
- Với Spring MVC, kiểm tra message converter thực tế khi trả về scalar String.

Khi đọc và ghi JSON, hãy xác định root shape trước, chọn kiểu Java đích tương ứng, rồi kiểm thử bằng payload đại diện cho hợp đồng thực tế.
