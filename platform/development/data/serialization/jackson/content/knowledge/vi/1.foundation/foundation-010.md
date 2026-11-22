# Các thuật ngữ cốt lõi và trình tự học Jackson

Bài học này đặt nền móng để đọc, viết và cấu hình JSON bằng Jackson trong Java. Mục tiêu là hiểu Jackson gồm những phần nào, mỗi API giải quyết loại bài toán nào, dữ liệu đi qua các bước nào và nên học theo thứ tự nào để không nhầm lẫn giữa cú pháp JSON, mô hình Java và cấu hình chuyển đổi.

Các ví dụ dùng API Jackson 2.x với package `com.fasterxml.jackson`. Hãy dùng phiên bản được dự án hoặc Spring Boot quản lý; không trộn các phiên bản Jackson khác nhau trong cùng một ứng dụng.

## 1. Jackson là gì?

**Jackson** là bộ thư viện xử lý dữ liệu cho Java. Trong ứng dụng web, phần được dùng thường xuyên nhất là khả năng chuyển đổi giữa JSON và đối tượng Java:

- **Serialization**: chuyển dữ liệu Java thành JSON, thường gọi là *serialize* hoặc *ghi JSON*.
- **Deserialization**: đọc JSON và tạo dữ liệu Java tương ứng, thường gọi là *deserialize* hoặc *đọc JSON*.
- **Data binding**: cơ chế ánh xạ cấu trúc JSON sang thuộc tính Java và ngược lại.

Ví dụ, một đối tượng Java:

```java
public record UserDto(long id, String displayName) {}
```

có thể được ghi thành JSON:

```json
{
  "id": 42,
  "displayName": "An"
}
```

Khi đọc JSON có cấu trúc tương ứng, Jackson tạo một `UserDto`. Jackson xử lý việc phân tích cú pháp, tìm thuộc tính, chuyển kiểu dữ liệu và gọi cách tạo đối tượng phù hợp. Nó không tự quyết định ý nghĩa nghiệp vụ của dữ liệu. Việc kiểm tra một email có hợp lệ, người dùng có quyền thực hiện thao tác hay đơn hàng có được phép chuyển trạng thái vẫn thuộc trách nhiệm của ứng dụng.

JSON là định dạng dữ liệu độc lập với Java. Jackson là một cách triển khai việc đọc và ghi định dạng đó trong hệ sinh thái Java.

## 2. Ba lớp thư viện chính

Jackson thường được hiểu qua ba lớp có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | API tiêu biểu |
| --- | --- | --- |
| **jackson-core** | Đọc và ghi JSON ở mức token, theo luồng dữ liệu | `JsonFactory`, `JsonParser`, `JsonGenerator` |
| **jackson-annotations** | Khai báo quy tắc ánh xạ ngay trên kiểu hoặc thuộc tính Java | `@JsonProperty`, `@JsonIgnore`, `@JsonCreator` |
| **jackson-databind** | Ánh xạ giữa JSON và đối tượng Java; cung cấp mô hình cây | `ObjectMapper`, `ObjectReader`, `ObjectWriter`, `JsonNode` |

Ba lớp này bổ trợ cho nhau:

- `jackson-core` biết cách phân tích hoặc phát ra cấu trúc JSON, chẳng hạn bắt đầu một object, đọc tên field hay đọc một giá trị string.
- `jackson-annotations` cung cấp metadata để mô tả tên JSON, thuộc tính cần bỏ qua, cách tạo object và những quy tắc khác.
- `jackson-databind` kết hợp parser/generator với metadata để tự động ánh xạ dữ liệu vào các kiểu Java.

Khi mới học, hãy bắt đầu với `ObjectMapper` của databind. Khi đã hiểu data binding, học tree model và streaming API để biết lúc nào cần kiểm soát dữ liệu ở mức thấp hơn.

Jackson còn có các **module** mở rộng hỗ trợ cho những kiểu dữ liệu hoặc quy ước cụ thể, ví dụ module cho ngày giờ Java, kiểu Optional hoặc các kiểu dữ liệu của thư viện khác. Module thường đăng ký serializer, deserializer hoặc những thành phần mở rộng tương ứng.

## 3. Từ vựng cần nắm

### 3.1. JSON object, array, property và value

- **JSON object** là cấu trúc nằm trong cặp dấu ngoặc nhọn `{}`, gồm các cặp tên và giá trị.
- **JSON array** là cấu trúc nằm trong cặp dấu ngoặc vuông `[]`, chứa một dãy giá trị có thứ tự.
- **Property/field trong JSON** là tên gắn với một giá trị trong object, ví dụ `"displayName"`.
- **Value** có thể là string, number, boolean, `null`, object hoặc array.
- **Nested object/array** là object hoặc array nằm bên trong một cấu trúc khác.

Ví dụ:

```json
{
  "id": 42,
  "active": true,
  "roles": ["READER", "EDITOR"],
  "address": {
    "city": "Da Nang",
    "postalCode": "550000"
  },
  "nickname": null
}
```

Một JSON object không bắt buộc phải tương ứng với một class duy nhất. Nó có thể được ánh xạ vào DTO, `Map`, `JsonNode` hoặc được đọc từng token.

### 3.2. POJO, DTO và Java property

- **POJO (Plain Old Java Object)** là cách gọi thông dụng cho một đối tượng Java thông thường, không phụ thuộc vào một framework đặc biệt.
- **DTO (Data Transfer Object)** là kiểu dữ liệu dùng để truyền dữ liệu qua một ranh giới, chẳng hạn request/response HTTP hoặc giữa các lớp ứng dụng.
- **Java property** là thuộc tính mà Jackson nhận diện trên kiểu Java. Tùy cấu hình và kiểu lớp, property có thể được nhận diện qua getter, setter, field, constructor parameter hoặc record component.
- **Constructor-based creation** là cách Jackson tạo object thông qua constructor hoặc factory method được nhận diện, thay vì tạo object rỗng rồi gán từng thuộc tính.

Không nên đồng nhất Java property với một field khai báo trong source code. Jackson có thể xem getter và field cùng tên là những thành phần của một property logic.

DTO thường là lựa chọn tốt cho dữ liệu API vì hình dạng JSON có thể thay đổi độc lập với mô hình nghiệp vụ bên trong. Không nên mặc định serialize toàn bộ domain entity chỉ vì Jackson có thể làm được.

### 3.3. Data binding và các mô hình xử lý JSON

Có ba cách làm việc phổ biến:

1. **POJO/data binding model**: ánh xạ JSON vào class, record, collection hoặc map. Dùng khi cấu trúc dữ liệu đã biết.
2. **Tree model**: biểu diễn JSON thành cây node có thể duyệt và sửa. Dùng khi cấu trúc thay đổi hoặc chỉ cần một vài nhánh.
3. **Streaming model**: xử lý lần lượt các token từ input stream hoặc ghi token ra output stream. Dùng khi cần kiểm soát chi tiết hoặc xử lý dữ liệu lớn.

Ba mô hình không loại trừ nhau. Một ứng dụng có thể đọc một phần dữ liệu bằng streaming, chuyển một object con sang tree model rồi bind object đó vào DTO.

### 3.4. ObjectMapper, ObjectReader và ObjectWriter

- **`ObjectMapper`** là điểm vào chính của databind. Nó cung cấp các thao tác đọc, ghi và cấu hình ánh xạ.
- **`ObjectReader`** đại diện cho một cách đọc đã được cấu hình, ví dụ đọc một kiểu cụ thể hoặc áp dụng một số tùy chọn.
- **`ObjectWriter`** đại diện cho một cách ghi đã được cấu hình, ví dụ ghi một kiểu hoặc bật pretty printing.
- **`JsonFactory`** tạo parser và generator cho API streaming.

Hãy cấu hình `ObjectMapper` trước khi dùng và tái sử dụng nó trong ứng dụng. `ObjectMapper` an toàn cho việc dùng đồng thời sau khi cấu hình hoàn tất, nhưng không nên thay đổi cấu hình của mapper trong lúc các luồng đang sử dụng nó. Khi cần biến thể cấu hình cho từng thao tác, ưu tiên tạo `ObjectReader` hoặc `ObjectWriter` từ mapper.

### 3.5. JsonNode và tree model

**`JsonNode`** là kiểu node cơ sở trong tree model. Các node thường gặp:

- `ObjectNode`: JSON object, có các thuộc tính theo tên.
- `ArrayNode`: JSON array, có các phần tử theo chỉ số.
- Các node giá trị: text, number, boolean, null.
- `MissingNode`: kết quả biểu thị đường dẫn không tìm thấy node trong một số thao tác truy cập.

Tree model hữu ích khi JSON có field tùy chọn, cấu trúc không ổn định hoặc chương trình chỉ cần đọc một phần tài liệu. Nó cũng cho phép sửa cây trước khi ghi JSON trở lại.

### 3.6. TypeReference và JavaType

Java dùng **type erasure** cho generic ở runtime. Vì vậy, chỉ truyền `List.class` không cho Jackson biết phần tử của danh sách là `UserDto` hay kiểu nào khác.

**`TypeReference<T>`** và **`JavaType`** giúp cung cấp thông tin kiểu đầy đủ cho những cấu trúc generic như:

- `List<UserDto>`
- `Map<String, UserDto>`
- `Map<String, List<UserDto>>`

Đây là khái niệm cần học trước khi đọc JSON thành collection hoặc cấu trúc lồng nhau có generic.

### 3.7. Serializer, deserializer và module

- **Serializer** chuyển một giá trị Java thành cấu trúc JSON.
- **Deserializer** chuyển token/cấu trúc JSON thành giá trị Java.
- **Custom serializer/deserializer** là phần triển khai do ứng dụng cung cấp khi quy tắc mặc định không đáp ứng được định dạng cần thiết.
- **Jackson module** đóng gói serializer, deserializer, annotation introspector hoặc các thành phần mở rộng để đăng ký với mapper.

Chỉ viết custom serializer/deserializer khi đã xác nhận mapping mặc định và annotation không giải quyết được yêu cầu. Logic chuyển đổi tùy biến làm tăng trách nhiệm phải kiểm thử và bảo trì.

### 3.8. Tên field, null, field thiếu và giá trị mặc định

Các trường hợp sau có ý nghĩa khác nhau:

```json
{}
```

```json
{ "nickname": null }
```

```json
{ "nickname": "" }
```

Trường hợp thứ nhất là property không xuất hiện; trường hợp thứ hai có property với giá trị null; trường hợp thứ ba có property với chuỗi rỗng. Ứng dụng cần quyết định cách xử lý từng trường hợp. Đặc biệt, kiểu primitive như `int` không thể chứa null, nên giá trị thiếu hoặc null có thể dẫn tới giá trị mặc định hoặc lỗi tùy cấu hình và ngữ cảnh.

**Naming strategy** quy định cách chuyển tên property Java sang tên JSON, ví dụ từ `displayName` sang `display_name`. **Inclusion rule** quy định property nào được ghi ra JSON, chẳng hạn có bỏ qua giá trị null hay không.

### 3.9. Polymorphic type và type metadata

**Polymorphic deserialization** là đọc JSON thành một trong nhiều kiểu con dựa trên thông tin phân biệt kiểu. JSON có thể chứa một field như `"type": "card"` để chỉ ra kiểu cần tạo.

Type metadata phải có quy ước rõ ràng và danh sách kiểu được cho phép. Không bật default typing một cách tùy tiện khi đọc JSON không đáng tin cậy, vì việc cho input bên ngoài quyết định kiểu Java cần khởi tạo có thể tạo ra rủi ro bảo mật.

## 4. Ánh xạ các kiểu Java thường gặp

### 4.1. Kiểu đơn giản và object lồng nhau

Các kiểu string, boolean, số và enum thường được ánh xạ trực tiếp. Object lồng nhau thường được ánh xạ thành một DTO khác.

```java
public record AddressDto(String city, String postalCode) {}

public record UserDto(
    long id,
    String displayName,
    boolean active,
    AddressDto address
) {}
```

Với JSON có object `address`, Jackson tiếp tục ánh xạ object con vào `AddressDto`. Kiểu Java và cấu trúc JSON phải tương thích; nếu JSON đưa một object vào vị trí cần số hoặc ngược lại, quá trình mapping có thể thất bại.

### 4.2. Collection và map

JSON array thường được ánh xạ thành `List<T>` hoặc collection phù hợp. JSON object có thể được ánh xạ thành `Map<K, V>` nếu tên property và kiểu value tương thích.

```java
List<UserDto> users = mapper.readValue(
    json,
    new TypeReference<List<UserDto>>() {}
);

Map<String, List<UserDto>> groups = mapper.readValue(
    json,
    new TypeReference<Map<String, List<UserDto>>>() {}
);
```

Khi dùng generic, hãy truyền đủ kiểu phần tử bằng `TypeReference` hoặc tạo `JavaType`. Nếu chỉ truyền `List.class`, thông tin kiểu phần tử đã bị mất.

### 4.3. Record và constructor

Java record phù hợp với DTO bất biến:

```java
public record CreateUserRequest(String username, String email) {}
```

Jackson có thể dùng record component và canonical constructor để tạo record. Với class thông thường có nhiều constructor hoặc quy tắc khởi tạo đặc biệt, có thể cần `@JsonCreator` và `@JsonProperty` để chỉ rõ constructor/factory method và tham số tương ứng.

Đừng giả định mọi class đều có thể được tạo bằng constructor rỗng. Hãy xác định rõ kiểu dữ liệu được thiết kế để mutable hay immutable và chọn cách mapping tương ứng.

### 4.4. Ngày giờ và kiểu dữ liệu mở rộng

Các kiểu trong `java.time` như `LocalDate`, `Instant` và `OffsetDateTime` thường cần module hỗ trợ Java Time của Jackson. Trong Jackson 2.x, module phổ biến là `jackson-datatype-jsr310` với `JavaTimeModule`.

Ví dụ cấu hình độc lập:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
```

Với API, nên thống nhất định dạng ngày giờ, múi giờ và độ chính xác. ISO-8601 là lựa chọn phổ biến, nhưng hợp đồng API phải quy định rõ kiểu thời gian nào được gửi và ý nghĩa của múi giờ. Đừng dùng `double` để biểu diễn tiền; dùng kiểu số thập phân phù hợp như `BigDecimal` khi cần giữ chính xác giá trị.

Trong Spring Boot, các module và `ObjectMapper` thường được cấu hình thông qua cơ chế auto-configuration. Hãy ưu tiên dùng bean được Spring quản lý để giữ cấu hình thống nhất. Với ứng dụng Java độc lập, khai báo dependency và đăng ký module cần thiết theo phiên bản Jackson của dự án.

## 5. Các API nên học đầu tiên

### 5.1. Khởi tạo mapper và đọc/ghi cơ bản

Trong ứng dụng độc lập, có thể bắt đầu với:

```java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(
    new UserDto(42L, "An", true, null)
);

UserDto user = mapper.readValue(json, UserDto.class);
```

Các phương thức cần nhận diện:

| Phương thức | Công dụng |
| --- | --- |
| `writeValueAsString(value)` | Serialize thành chuỗi JSON |
| `writeValue(output, value)` | Ghi JSON ra output target |
| `readValue(json, Type.class)` | Deserialize thành kiểu cụ thể |
| `readValue(input, TypeReference)` | Deserialize khi cần giữ generic type |
| `readTree(json)` | Đọc JSON thành tree model |
| `treeToValue(node, Type.class)` | Chuyển một node thành kiểu Java |
| `valueToTree(value)` | Chuyển giá trị Java thành tree model |

`ObjectMapper` mặc định có thể đủ cho ví dụ đầu tiên, nhưng ứng dụng thực tế thường cần module và cấu hình phù hợp. Hãy cấu hình xong trước khi chia sẻ mapper cho các luồng xử lý.

### 5.2. Đọc dữ liệu không biết trước cấu trúc

Dùng tree model khi chỉ cần truy cập một vài field:

```java
JsonNode root = mapper.readTree(json);

String city = root
    .path("address")
    .path("city")
    .asText(null);

boolean active = root.path("active").asBoolean(false);
```

`path` giúp truy cập an toàn hơn `get` khi node trung gian không tồn tại; kết quả có thể là `MissingNode`. Khi cần phân biệt rõ field không tồn tại và field có giá trị null, kiểm tra `isMissingNode()` và `isNull()` thay vì chỉ chuyển giá trị sang kiểu Java.

### 5.3. Khi nào dùng streaming API?

Data binding thường đọc cả cấu trúc cần ánh xạ vào bộ nhớ. Với tài liệu JSON rất lớn, xử lý từng bản ghi hoặc yêu cầu kiểm soát thứ tự token, streaming API có thể phù hợp hơn.

```java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();
        // Xử lý token hiện tại theo cấu trúc dữ liệu mong đợi.
    }
}
```

`JsonParser` đọc các token như `START_OBJECT`, `FIELD_NAME`, `VALUE_STRING` và `END_OBJECT`. `JsonGenerator` làm công việc ngược lại: phát token để ghi JSON. Streaming API yêu cầu tự quản lý trạng thái cấu trúc nhiều hơn, vì vậy không nên bắt đầu học bằng API này nếu mục tiêu trước mắt chỉ là đọc request thành DTO.

## 6. Annotation thường gặp

Annotation cho Jackson là metadata hướng dẫn cách ánh xạ. Chúng không thay thế việc thiết kế DTO và cũng không thay thế kiểm tra nghiệp vụ.

| Annotation | Ý nghĩa chính |
| --- | --- |
| `@JsonProperty("user_name")` | Chỉ định tên JSON cho property |
| `@JsonAlias({"name", "userName"})` | Chấp nhận các tên thay thế khi đọc JSON |
| `@JsonIgnore` | Bỏ qua property trong quá trình mapping theo quy tắc của annotation |
| `@JsonInclude(JsonInclude.Include.NON_NULL)` | Bỏ qua property null khi ghi JSON |
| `@JsonFormat` | Chỉ định định dạng hoặc cách biểu diễn trong ngữ cảnh được hỗ trợ |
| `@JsonCreator` | Chỉ định constructor hoặc factory method dùng để tạo object |
| `@JsonValue` | Dùng giá trị được chỉ định làm biểu diễn JSON của object |
| `@JsonTypeInfo` và `@JsonSubTypes` | Khai báo metadata và các subtype cho polymorphic mapping |

Ví dụ đổi tên property:

```java
public record UserResponse(
    long id,
    @JsonProperty("display_name") String displayName
) {}
```

`@JsonAlias` hữu ích khi API cần đọc dữ liệu cũ và mới trong giai đoạn chuyển đổi tên field. Alias chủ yếu hỗ trợ đọc; tên chuẩn khi ghi vẫn do cấu hình/property chính quyết định.

`@JsonInclude` kiểm soát dữ liệu được xuất ra, không tự xác định dữ liệu đầu vào có hợp lệ hay không. `@JsonIgnore` cũng cần được cân nhắc kỹ vì có thể làm mất dữ liệu ở cả chiều đọc hoặc ghi theo cách Jackson áp dụng annotation và cấu hình.

## 7. Cấu hình cần hiểu trước khi dùng trong ứng dụng

Không nên sao chép một bộ cấu hình lớn mà không biết từng tùy chọn ảnh hưởng đến hợp đồng JSON như thế nào. Hãy kiểm tra các nhóm sau:

- **Property naming**: dùng tên mặc định, snake_case hay quy ước khác.
- **Unknown properties**: JSON có field chưa được DTO khai báo thì bỏ qua hay báo lỗi. Tùy chọn liên quan là `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Hành vi mặc định có thể khác khi ứng dụng dùng cấu hình Spring Boot; hãy kiểm tra cấu hình thực tế.
- **Null và missing values**: xử lý property null, property vắng mặt và giá trị mặc định như thế nào.
- **Date/time**: module, định dạng, timezone và độ chính xác.
- **Enum**: ánh xạ theo tên, giá trị tùy chỉnh hay quy tắc khác; cần có hành vi rõ ràng với giá trị không nhận diện.
- **Visibility**: Jackson được phép nhìn thấy field, getter, setter hay constructor nào.
- **Inclusion**: property null hoặc giá trị mặc định có được ghi ra JSON hay không.
- **Coercion**: có cho phép chuyển đổi ngầm giữa các dạng dữ liệu hay không.

Mỗi tùy chọn có thể ảnh hưởng đến khả năng tương thích giữa các phiên bản client và server. Với API công khai, hãy xem quy tắc mapping là một phần của hợp đồng dữ liệu và kiểm thử bằng JSON mẫu thực tế.

## 8. Lỗi thường gặp và cách định vị

Các lỗi Jackson thường thuộc một trong ba nhóm:

1. **Lỗi cú pháp JSON**: dấu phẩy, dấu ngoặc, chuỗi hoặc escape không hợp lệ. Đây là lỗi parse trước khi mapping vào DTO.
2. **Lỗi không tương thích kiểu/cấu trúc**: JSON có object ở nơi cần số, array ở nơi cần object, hoặc giá trị không thể chuyển sang kiểu Java đích. Các lỗi này thường xuất hiện dưới dạng nhóm lỗi mapping như `MismatchedInputException`.
3. **Lỗi định nghĩa kiểu hoặc cấu hình**: Jackson không tìm được cách tạo object, không có serializer/deserializer phù hợp hoặc cấu hình annotation/module không nhất quán. Một ví dụ là `InvalidDefinitionException`.

Một số lỗi khác như property không được nhận diện có thể xuất hiện dưới dạng `UnrecognizedPropertyException` tùy cấu hình.

Khi xử lý lỗi, hãy xác định:

- JSON đầu vào có hợp lệ về cú pháp không?
- Đường dẫn property nào gây lỗi?
- Kiểu JSON thực tế là gì và kiểu Java đang mong đợi là gì?
- DTO có constructor, record component, getter/setter hoặc annotation phù hợp không?
- Module cần thiết đã được đăng ký chưa?
- Cấu hình của mapper độc lập có giống cấu hình mapper trong Spring Boot không?

Không nên bắt mọi lỗi rồi trả về một DTO rỗng. Cách đó che mất dữ liệu đầu vào không hợp lệ và có thể làm ứng dụng tiếp tục xử lý với trạng thái sai. Hãy chuyển lỗi parse/mapping thành phản hồi phù hợp ở ranh giới API, đồng thời giữ thông tin chẩn đoán cần thiết trong log mà không làm lộ dữ liệu nhạy cảm.

## 9. Trình tự học Jackson đề xuất

Học theo thứ tự dưới đây giúp mỗi phần dựa trên khái niệm đã có ở phần trước.

### Bước 1 — Ôn JSON và kiểu dữ liệu Java

Nắm object, array, string, number, boolean, null, object lồng nhau; đồng thời ôn class, record, enum, collection và generic trong Java.

**Kết quả cần đạt:** nhìn một JSON mẫu và phác thảo được DTO hoặc cấu trúc Java tương ứng.

### Bước 2 — Hiểu serialization và deserialization

Phân biệt hai chiều chuyển đổi. Tập chuyển một DTO đơn giản thành JSON và đọc JSON trở lại.

**Kết quả cần đạt:** dùng được `writeValueAsString` và `readValue` với một class hoặc record.

### Bước 3 — Nắm ba lớp core, annotations và databind

Hiểu vai trò của từng artifact, vì sao `ObjectMapper` dựa trên parser/generator và annotation cung cấp metadata.

**Kết quả cần đạt:** biết API mình đang dùng thuộc lớp nào và khi nào cần đọc tài liệu của lớp đó.

### Bước 4 — Mapping object lồng nhau, collection và generic

Thực hành DTO lồng nhau, `List<T>`, `Map<K,V>` và `TypeReference`. Chú ý type erasure.

**Kết quả cần đạt:** đọc được JSON có danh sách và cấu trúc lồng nhau mà vẫn giữ đúng kiểu phần tử.

### Bước 5 — Annotation và quy ước tên property

Học `@JsonProperty`, `@JsonAlias`, `@JsonIgnore`, `@JsonInclude` và `@JsonCreator`. Thử ánh xạ tên Java khác tên JSON.

**Kết quả cần đạt:** biểu diễn được hợp đồng JSON mà không phải đổi tên class/property chỉ để khớp với payload.

### Bước 6 — Cấu hình mapper và module

Tìm hiểu unknown properties, null, enum, ngày giờ, naming strategy và module. Nếu làm Spring Boot, kiểm tra bean `ObjectMapper` thực tế và cơ chế auto-configuration.

**Kết quả cần đạt:** giải thích được vì sao cùng một DTO có thể cho kết quả khác nhau khi dùng hai cấu hình mapper khác nhau.

### Bước 7 — Tree model

Dùng `readTree`, `JsonNode`, `ObjectNode` và `ArrayNode` để đọc hoặc thay đổi JSON có cấu trúc linh hoạt.

**Kết quả cần đạt:** lấy được field tùy chọn, phân biệt missing/null và chỉnh sửa một nhánh mà không cần tạo DTO cho toàn bộ payload.

### Bước 8 — Lỗi mapping, kiểm thử và hợp đồng dữ liệu

Thử JSON sai cú pháp, sai kiểu, thiếu field, field lạ, null, ngày giờ sai định dạng và enum không nhận diện. Kiểm tra cả chiều đọc lẫn chiều ghi.

**Kết quả cần đạt:** xác định được nhóm lỗi và viết test bảo vệ hình dạng JSON mà ứng dụng hỗ trợ.

### Bước 9 — Custom serializer/deserializer và polymorphism

Chỉ sau khi hiểu mapping mặc định mới học cách thay đổi biểu diễn của một kiểu, đăng ký module tùy biến và ánh xạ subtype.

**Kết quả cần đạt:** triển khai được quy tắc đặc biệt có phạm vi rõ ràng; hiểu rủi ro khi dữ liệu bên ngoài quyết định subtype.

### Bước 10 — Streaming API và tối ưu theo nhu cầu

Học parser, generator và token khi có yêu cầu về kích thước dữ liệu, bộ nhớ hoặc kiểm soát luồng.

**Kết quả cần đạt:** biết lựa chọn giữa data binding, tree model và streaming dựa trên hình dạng dữ liệu và yêu cầu xử lý.

## 10. Bài thực hành tổng hợp

Tạo một DTO request và response cho chức năng quản lý người dùng. JSON đầu vào có thông tin cơ bản, danh sách role và địa chỉ lồng nhau. Thực hiện lần lượt:

1. Serialize một record thành JSON.
2. Deserialize JSON thành record.
3. Deserialize một danh sách record bằng `TypeReference`.
4. Đổi tên một property bằng `@JsonProperty` và thử đọc tên cũ bằng `@JsonAlias`.
5. Đọc một field tùy chọn bằng `JsonNode`; phân biệt field bị thiếu với field null.
6. Thêm một trường ngày giờ và đăng ký `JavaTimeModule`.
7. Viết test cho JSON hợp lệ, sai kiểu, sai ngày giờ và field không được nhận diện.
8. Nếu payload có nhiều subtype, mô tả discriminator và chỉ cho phép những subtype đã định nghĩa.
9. Nếu dữ liệu rất lớn, giải thích phần nào có thể xử lý bằng streaming thay vì bind toàn bộ vào một object graph.

Bài thực hành hoàn thành khi có thể giải thích từng quyết định mapping, không chỉ khi chương trình chạy thành công với một JSON mẫu.

## 11. Các nguyên tắc nên giữ khi làm việc với Jackson

- Dùng DTO rõ ràng ở ranh giới API; giữ mô hình domain độc lập với hình dạng JSON khi hai mô hình có mục đích khác nhau.
- Tái sử dụng mapper đã cấu hình xong. Trong Spring Boot, ưu tiên inject bean được quản lý thay vì tự tạo nhiều mapper với cấu hình khác nhau.
- Đăng ký module cần thiết một cách nhất quán, đặc biệt với ngày giờ và kiểu dữ liệu mở rộng.
- Giữ nguyên thông tin generic khi deserialize collection bằng `TypeReference` hoặc `JavaType`.
- Quy định rõ cách xử lý unknown field, null, field thiếu, enum và ngày giờ.
- Kiểm thử JSON như một hợp đồng: tên field, kiểu dữ liệu, giá trị biên và khả năng tương thích.
- Chỉ thêm custom serializer/deserializer khi mapping tiêu chuẩn không đáp ứng được yêu cầu.
- Không bật default typing một cách tùy tiện cho dữ liệu không đáng tin cậy.
- Không nhầm mapping thành validation nghiệp vụ. Sau khi Jackson tạo DTO, ứng dụng vẫn phải kiểm tra dữ liệu và quyền thực hiện thao tác.

Jackson sẽ dễ học hơn khi luôn đặt câu hỏi: dữ liệu đang ở dạng JSON hay Java, cấu trúc đã biết đến đâu, và cần mức kiểm soát nào? Câu trả lời sẽ dẫn tới lựa chọn data binding, tree model hoặc streaming API phù hợp.

