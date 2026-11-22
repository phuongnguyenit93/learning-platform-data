# Phân biệt chuyển giá trị trong bộ nhớ và đọc một tài liệu JSON

Jackson có hai nhóm thao tác dễ bị nhầm lẫn: **chuyển một giá trị Java đang có trong bộ nhớ sang kiểu Java khác** và **đọc một tài liệu JSON từ chuỗi, byte hoặc stream**. `ObjectMapper.convertValue(...)` phục vụ nhóm thứ nhất; `readValue(...)` phục vụ nhóm thứ hai.

Hai thao tác có thể tạo ra kết quả giống nhau trong ví dụ đơn giản, nhưng chúng bắt đầu từ hai loại đầu vào khác nhau và đi qua hai luồng xử lý khác nhau. Nếu đầu vào là một object Java, hãy dùng API chuyển đổi trong bộ nhớ. Nếu đầu vào là văn bản hoặc byte JSON, hãy parse tài liệu bằng `readValue(...)`. Đưa một chuỗi JSON vào `convertValue(...)` không có nghĩa Jackson sẽ parse chuỗi đó thành object.

## 1. Hai bài toán khác nhau

Giả sử ứng dụng có kiểu đích:

```java
public record UserDto(Long id, String name, boolean active) {
}
```

Ứng dụng có thể nhận dữ liệu theo hai cách:

**Trường hợp A — đã có object Java:**

```java
Map<String, Object> source = Map.of(
        "id", 101,
        "name", "An",
        "active", true
);

UserDto user = mapper.convertValue(source, UserDto.class);
```

Jackson chuyển giá trị `Map` đang nằm trong heap thành `UserDto`.

**Trường hợp B — đang có tài liệu JSON:**

```java
String json = """
        {
          "id": 101,
          "name": "An",
          "active": true
        }
        """;

UserDto user = mapper.readValue(json, UserDto.class);
```

Jackson parse nội dung JSON, tạo token rồi deserialize thành `UserDto`.

| Câu hỏi | API phù hợp |
|---|---|
| Tôi đã có `Map`, POJO, record hoặc object Java và muốn chuyển sang kiểu khác | `convertValue(...)` |
| Tôi có chuỗi JSON cần parse thành object | `readValue(String, ...)` |
| Tôi có byte JSON từ HTTP/file/message | `readValue(byte[], ...)` hoặc đọc từ stream |
| Tôi có `JsonNode` và muốn chuyển thành DTO | `treeToValue(...)` hoặc `convertValue(...)` |
| Tôi có POJO và muốn tạo cây JSON trong bộ nhớ | `valueToTree(...)` |

## 2. convertValue chuyển một giá trị đang ở trong bộ nhớ

`ObjectMapper.convertValue(fromValue, targetType)` nhận một object Java làm nguồn và một kiểu đích. Jackson dùng cơ chế serialize/deserializer nội bộ để chuyển dữ liệu qua biểu diễn token trong bộ nhớ, thường dựa trên `TokenBuffer`, rồi deserialize token đó thành kiểu đích.

Luồng khái quát:

```text
Object Java nguồn
       |
       v
Serializer của Jackson
       |
       v
TokenBuffer trong bộ nhớ
       |
       v
Deserializer của Jackson
       |
       v
Object Java đích
```

Không cần tạo một chuỗi JSON hoàn chỉnh rồi parse lại chuỗi đó. Vì vậy, `convertValue` hữu ích khi ứng dụng đã có dữ liệu Java và muốn tái sử dụng mapping rules của Jackson.

Ví dụ POJO sang DTO:

```java
public record CustomerEntityView(
        Long id,
        String fullName,
        String email
) {
}

public record CustomerResponse(
        Long id,
        String name,
        String email
) {
}

CustomerEntityView source = new CustomerEntityView(
        42L,
        "Nguyen An",
        "an@example.test"
);

CustomerResponse response = mapper.convertValue(
        source,
        CustomerResponse.class
);
```

Ví dụ này chỉ chuyển được nếu các property mà Jackson serialize từ nguồn có thể được bind vào kiểu đích. `convertValue` không phải một bộ sao chép property tổng quát như một số bean-mapping library. Nó vẫn tuân theo serializer, deserializer, annotation, module và feature của mapper.

## 3. readValue đọc một tài liệu JSON thực sự

`readValue(...)` nhận dữ liệu JSON từ nhiều dạng nguồn:

```java
UserDto fromText = mapper.readValue(json, UserDto.class);
UserDto fromBytes = mapper.readValue(jsonBytes, UserDto.class);
UserDto fromFile = mapper.readValue(jsonFile.toFile(), UserDto.class);
UserDto fromStream = mapper.readValue(inputStream, UserDto.class);
```

Jackson tạo parser cho nguồn đầu vào, đọc token JSON, kiểm tra cú pháp theo parser configuration và deserialize vào kiểu đích.

Luồng khái quát:

```text
String / byte[] / InputStream / Reader / File
                    |
                    v
               JsonParser
                    |
                    v
              JSON tokens
                    |
                    v
          Deserializer của Jackson
                    |
                    v
              Object Java
```

`readValue` là API phù hợp khi dữ liệu đến từ request body, file JSON, message broker, object storage hoặc một hệ thống khác. Nó kiểm tra dữ liệu như một tài liệu JSON thay vì xem đầu vào là một object Java đã tồn tại.

## 4. Một lỗi thường gặp: đưa chuỗi JSON vào convertValue

Đoạn code sau không parse object JSON:

```java
String json = "{\"id\":101,\"name\":\"An\",\"active\":true}";

UserDto user = mapper.convertValue(json, UserDto.class);
```

Nguồn của `convertValue` là một Java `String`. Jackson xử lý nó như một giá trị string, tương đương token JSON string:

```json
"{\"id\":101,\"name\":\"An\",\"active\":true}"
```

Đây không phải JSON object có ba field. Khi deserialize token string thành `UserDto`, Jackson thường báo lỗi ánh xạ vì kiểu đích là object.

Hãy dùng:

```java
UserDto user = mapper.readValue(json, UserDto.class);
```

Quy tắc cần nhớ: `convertValue` nhận giá trị Java; `readValue` nhận nội dung JSON. Nếu biến có kiểu `String`, hãy xác định nó là văn bản thông thường hay là một tài liệu JSON được mã hóa dưới dạng văn bản.

Ngược lại, nếu một property JSON thực sự chứa chuỗi văn bản có ký tự `{` và `}`, ví dụ:

```json
{
  "rawText": "{\"id\":101}"
}
```

thì `rawText` vẫn là string. Chỉ parse nội dung của nó thành một tài liệu JSON thứ hai nếu contract yêu cầu rõ điều đó.

## 5. Chuyển đổi Map sang POJO hoặc record

Một use case phổ biến là nhận dữ liệu đã được chuyển thành `Map<String, Object>` bởi tầng khác rồi ánh xạ sang DTO:

```java
Map<String, Object> payload = new HashMap<>();
payload.put("id", 101L);
payload.put("name", "An");
payload.put("active", true);

UserDto user = mapper.convertValue(payload, UserDto.class);
```

Các key trong map được xem như tên property. Value được chuyển qua deserializer của kiểu property tương ứng.

Việc chuyển đổi có thể chịu ảnh hưởng của:

- Tên property và annotation như `@JsonProperty`.
- Constructor/record creator mà Jackson sử dụng.
- `@JsonIgnoreProperties` và cấu hình unknown property.
- Scalar coercion, ví dụ chuyển một số kiểu number phù hợp.
- Custom deserializer hoặc module đã đăng ký.
- Null handling và inclusion không giống nhau giữa serialize/deserialization.

Nếu key trong map không khớp property đích, hành vi phụ thuộc cấu hình unknown property. Với mapper mặc định, `FAIL_ON_UNKNOWN_PROPERTIES` thường được bật cho POJO trong nhiều cấu hình Jackson thuần; framework có thể cấu hình khác. Hãy dùng đúng mapper production và không dựa vào một default không được xác nhận.

## 6. Chuyển POJO sang Map hoặc kiểu Java tổng quát

`convertValue` cũng có thể chuyển một object thành map:

```java
UserDto user = new UserDto(101L, "An", true);

Map<String, Object> map = mapper.convertValue(
        user,
        new TypeReference<Map<String, Object>>() { }
);
```

Map được tạo dựa trên property mà Jackson serialize. Vì vậy, annotation như `@JsonProperty`, `@JsonIgnore`, view, filter hoặc custom serializer có thể làm thay đổi các entry xuất hiện trong map.

Điều này có nghĩa `convertValue` không nhất thiết sao chép toàn bộ field nội bộ của object. Nó chuyển theo góc nhìn serialization của Jackson. Nếu một field bị `@JsonIgnore`, field đó thường không có trong token trung gian và sẽ không xuất hiện trong map kết quả.

## 7. Dùng TypeReference hoặc JavaType cho generic target

Khi kiểu đích có generic, không nên dùng raw class vì Java type erasure làm mất thông tin tham số.

Ví dụ chuyển map sang list DTO:

```java
List<Map<String, Object>> rows = loadRows();

List<UserDto> users = mapper.convertValue(
        rows,
        new TypeReference<List<UserDto>>() { }
);
```

Với `readValue`, cũng cần cung cấp generic type:

```java
List<UserDto> users = mapper.readValue(
        json,
        new TypeReference<List<UserDto>>() { }
);
```

Nếu kiểu được xác định tại runtime, tạo `JavaType`:

```java
JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, UserDto.class);

List<UserDto> converted = mapper.convertValue(rows, listType);
List<UserDto> parsed = mapper.readValue(json, listType);
```

Với wrapper generic:

```java
JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, UserDto.class);

ApiResponse<UserDto> response = mapper.readValue(json, responseType);
```

Thông tin generic đầy đủ giúp Jackson chọn đúng deserializer cho từng phần tử hoặc property lồng nhau.

## 8. Chuyển đổi JsonNode với treeToValue và convertValue

Nếu nguồn đã là `JsonNode`, có hai API thường dùng:

```java
JsonNode tree = mapper.readTree(json);

UserDto first = mapper.treeToValue(tree, UserDto.class);
UserDto second = mapper.convertValue(tree, UserDto.class);
```

`treeToValue(...)` diễn đạt rõ ý định: chuyển một JSON tree thành kiểu Java. `convertValue(...)` tổng quát hơn và cũng có thể nhận `JsonNode` làm nguồn.

Ở chiều ngược lại, `valueToTree(...)` chuyển object Java thành cây JSON trong bộ nhớ:

```java
UserDto user = new UserDto(101L, "An", true);
JsonNode tree = mapper.valueToTree(user);
```

Các API tree hữu ích khi cần kiểm tra hoặc sửa JSON trong bộ nhớ:

```java
ObjectNode tree = (ObjectNode) mapper.valueToTree(user);
tree.put("source", "admin-console");

UserDto converted = mapper.treeToValue(tree, UserDto.class);
```

Lưu ý `treeToValue` không đọc một chuỗi JSON. Nó nhận một `JsonNode` đã tồn tại. Nếu nguồn là chuỗi, parse bằng `readTree(...)` trước.

## 9. convertValue không phải cast hoặc copy object đơn giản

Không nên hiểu `convertValue` như một phép ép kiểu Java:

```java
UserDto dto = (UserDto) source; // Đây là cast, không phải mapping.
```

Cast chỉ hợp lệ nếu object runtime đã là `UserDto`. `convertValue` tạo object đích thông qua quy trình serialize/deserialize của Jackson.

Nó cũng không tương đương một deep clone tổng quát. Kết quả phụ thuộc cấu trúc JSON-like mà serializer tạo ra. Các đặc tính Java không được biểu diễn qua JSON token có thể không được giữ, ví dụ:

- Object identity hoặc quan hệ chia sẻ cùng một instance.
- Kiểu concrete nếu không có type metadata.
- Field bị ignore hoặc không có accessor serialize.
- State nội bộ không được serializer xuất ra.
- Một số kiểu tài nguyên, stream, proxy hoặc object có vòng tham chiếu.

Nếu object graph có vòng tham chiếu, Jackson có thể báo lỗi self-reference hoặc xử lý theo annotation/identity configuration. `convertValue` không tự động sao chép graph tùy ý mà không có quy tắc.

## 10. Custom serializer và deserializer ảnh hưởng convertValue

Vì `convertValue` dùng cơ chế serialization và deserialization của mapper, custom module có thể ảnh hưởng cả hai chiều.

Ví dụ custom serializer ghi `Money` thành string:

```java
public final class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator gen,
            SerializerProvider provider
    ) throws IOException {
        gen.writeString(value.currency() + " " + value.amount().toPlainString());
    }
}
```

Nếu convert một object chứa `Money` sang kiểu đích cũng có `Money`, token trung gian có thể là string. Deserializer của `Money` phải hiểu đúng string đó. Nếu deserializer mặc định mong đợi object `{currency, amount}`, conversion có thể thất bại.

Đây là một ví dụ cho thấy `convertValue` chịu ảnh hưởng của JSON contract nội bộ do serializer tạo ra. Nếu cần xác nhận chính xác cách dữ liệu sẽ đi qua wire, hãy serialize thành byte JSON rồi đọc lại bằng `readValue`, đồng thời test contract output độc lập.

## 11. convertValue không được bảo đảm giống hệt serialize rồi readValue

Javadoc của Jackson mô tả `convertValue` có mục tiêu chức năng gần với serialize rồi deserialize, nhưng conversion không được bảo đảm giống hệt việc tạo JSON text rồi parse lại. Một số serializer/deserializer có thể dựa vào chi tiết của parser hoặc định dạng token cụ thể; conversion qua `TokenBuffer` có thể khác so với đường đi qua JSON byte/text.

Ví dụ khái niệm:

```java
Target converted = mapper.convertValue(source, Target.class);

byte[] jsonBytes = mapper.writeValueAsBytes(source);
Target parsed = mapper.readValue(jsonBytes, Target.class);
```

Hai kết quả thường giống nhau với kiểu dữ liệu thông thường và cấu hình phù hợp. Nhưng nếu ứng dụng có custom serializer, custom deserializer, polymorphic type handling, raw output hoặc format phụ thuộc parser, hãy kiểm tra cả hai đường đi thay vì giả định chúng luôn tương đương.

Một số feature xử lý root wrapping/unwrapping hoặc định dạng đặc thù cũng có thể không có ngữ nghĩa giống nhau giữa convert và thao tác JSON text. Nếu contract phụ thuộc các feature này, hãy dùng `writeValue`/`readValue` trên đúng wire representation và test thực tế.

## 12. readValue kiểm tra cú pháp JSON; convertValue không parse tài liệu JSON

Với `readValue`, Jackson phải đọc token từ nguồn JSON. Dữ liệu sai cú pháp có thể gây `JsonParseException` hoặc lỗi `JsonProcessingException` tương ứng.

Ví dụ JSON không hợp lệ:

```java
String invalidJson = "{\"id\":101,\"name\":\"An\""; // thiếu }

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(invalidJson, UserDto.class)
);
```

`convertValue` không nhận chuỗi đó như tài liệu JSON. Nó xem đây là một string Java; do vậy, lỗi (nếu có) là lỗi chuyển một string value sang `UserDto`, không phải lỗi parser phát hiện dấu `}` bị thiếu.

Khi đọc JSON từ input có thể chứa nhiều root value hoặc trailing content, hãy cân nhắc `DeserializationFeature.FAIL_ON_TRAILING_TOKENS`:

```java
ObjectReader strictReader = mapper.readerFor(UserDto.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

UserDto user = strictReader.readValue(json);
```

Feature này giúp từ chối nội dung dư sau root value theo contract. Không nên giả định mọi lời gọi `readValue` đều tự động kiểm tra trailing tokens nếu feature chưa được bật.

## 13. Coercion và kiểu dữ liệu không khớp

Trong cả conversion và deserialization, Jackson có thể áp dụng scalar coercion theo cấu hình. Ví dụ một nguồn có số `101` và target là `String`, hoặc nguồn có string `"101"` và target là `Integer`, có thể được chuyển đổi tùy logical type, version và coercion config.

```java
Map<String, Object> source = Map.of("id", "101");

UserIdView converted = mapper.convertValue(source, UserIdView.class);
```

Đừng dựa vào coercion ngầm nếu contract yêu cầu kiểu chính xác. Với JSON wire format, hãy kiểm tra token type trong output và cấu hình `CoercionConfig` nếu cần từ chối một dạng input. Với conversion trong bộ nhớ, vẫn cần xác định nguồn Java đang cung cấp kiểu gì và mapper có được phép chuyển kiểu đó không.

Nếu conversion thất bại, `convertValue` thường ném `IllegalArgumentException` bao bọc nguyên nhân ánh xạ. `readValue` thường ném `JsonProcessingException` hoặc subclass. Khi xử lý lỗi, hãy log nguyên nhân phù hợp và không thay giá trị sai bằng mặc định một cách âm thầm.

## 14. Module, annotation và mapper configuration phải nhất quán

`convertValue`, `readValue`, `treeToValue` và `valueToTree` đều dựa trên cấu hình Jackson được dùng cho thao tác đó. Cấu hình có thể bao gồm:

- Module như JavaTimeModule hoặc module nghiệp vụ.
- Serializer/deserializer tùy chỉnh.
- Mix-in và annotation introspector.
- Property naming strategy.
- Visibility và inclusion.
- Coercion, null handling và unknown property behavior.
- Polymorphic type configuration.

Nếu conversion chạy bằng một mapper tự tạo khác với mapper của API, kết quả có thể khác. Trong ứng dụng framework, hãy dùng mapper bean đã được cấu hình hoặc factory trung tâm. Đừng tạo `new ObjectMapper()` tùy tiện cho mỗi conversion nếu ứng dụng cần module/feature thống nhất.

## 15. Chọn API theo loại nguồn dữ liệu

| Nguồn hiện có | Mục tiêu | API |
|---|---|---|
| POJO/record | Sang DTO hoặc kiểu Java khác | `convertValue` |
| `Map<String, Object>` | Sang POJO/record | `convertValue` |
| POJO/record | Sang `Map` hoặc `List` tổng quát | `convertValue` với `TypeReference`/`JavaType` |
| Chuỗi JSON | Sang POJO/record | `readValue(String, ...)` |
| Byte JSON | Sang POJO/record | `readValue(byte[], ...)` |
| File/InputStream/Reader | Sang POJO/record | `readValue(source, ...)` |
| JSON đã parse thành `JsonNode` | Sang POJO/record | `treeToValue` hoặc `convertValue` |
| POJO/record | Sang JSON tree | `valueToTree` |
| JSON tree | Sang JSON text | `writeValueAsString(tree)` hoặc `writeValueAsBytes(tree)` |

Nếu ứng dụng cần parse chuỗi JSON nằm bên trong một property string, đó là hai bước riêng: lấy string property, sau đó gọi `readValue` trên chính string đó. Chỉ thực hiện khi schema định nghĩa nested JSON text; nếu không, nên giữ nó như string.

## 16. Ví dụ tổng hợp: nhận JSON, chuyển DTO và chuẩn bị response

Giả sử một service nhận payload JSON từ đối tác, deserialize thành request DTO, chuyển sang command nội bộ rồi tạo response DTO:

```java
public record PartnerUserPayload(
        String externalId,
        String displayName,
        String enabled
) {
}

public record CreateUserCommand(
        String externalId,
        String name,
        boolean active
) {
}

public record UserResponse(
        Long id,
        String name,
        boolean active
) {
}
```

Đọc JSON từ đối tác:

```java
PartnerUserPayload payload = mapper.readValue(
        requestBody,
        PartnerUserPayload.class
);
```

Chuyển giá trị trong bộ nhớ sang command:

```java
CreateUserCommand command = new CreateUserCommand(
        payload.externalId(),
        payload.displayName(),
        Boolean.parseBoolean(payload.enabled())
);
```

Nếu hai kiểu có cùng property name và kiểu tương thích, có thể dùng `convertValue` để mapping, nhưng ví dụ trên có tên field và kiểu khác nhau nên cần logic chuyển đổi tường minh. Sau khi service tạo user, response có thể được serialize ra JSON:

```java
String responseJson = mapper.writeValueAsString(userResponse);
```

Luồng tổng thể:

```text
HTTP JSON body
     |
     v
readValue(...)
     |
     v
PartnerUserPayload
     |
     v
Domain mapping / validation
     |
     v
CreateUserCommand
     |
     v
Service xử lý nghiệp vụ
     |
     v
UserResponse
     |
     v
writeValueAsString / writeValueAsBytes
     |
     v
HTTP JSON response
```

Trong luồng này, chỉ những bước làm việc với JSON text/bytes mới cần parser hoặc generator. Mapping giữa các object Java có thể dùng code tường minh hoặc `convertValue` nếu hai cấu trúc thực sự tương thích.

## 17. Khi nào nên dùng mapping code tường minh thay cho convertValue?

`convertValue` tiện khi hai cấu trúc dữ liệu gần giống nhau và mapping theo property là đủ. Nhưng không phải lúc nào nó cũng là lựa chọn tốt nhất.

Nên cân nhắc mapping tường minh khi:

- Tên property khác nhau hoặc cần ghép nhiều field.
- Cần tính toán, chuẩn hóa hoặc validation nghiệp vụ.
- Cần bỏ qua field nhạy cảm hoặc field không được client điều khiển.
- Cần xử lý null/missing theo chính sách riêng.
- Entity ORM có lazy proxy hoặc association không nên bị serialize.
- Cần giữ type identity, object graph hoặc resource lifecycle không phù hợp với JSON-like conversion.
- Cần compile-time safety và mapping dễ review.

Ví dụ:

```java
UserResponse toResponse(User entity) {
    return new UserResponse(
            entity.getId(),
            entity.getDisplayName(),
            entity.isEnabled()
    );
}
```

Mapping tường minh cho thấy chính xác field nào được đưa ra API. `convertValue` có thể ngắn hơn, nhưng nó dựa trên metadata serialization và có thể vô tình đưa thêm property nếu model thay đổi.

## 18. Không dùng convertValue để thay thế validation

Việc chuyển đổi thành công chỉ chứng minh Jackson có thể tạo kiểu đích theo cấu hình. Nó không chứng minh dữ liệu hợp lệ theo nghiệp vụ.

Ví dụ chuỗi `"-3"` có thể chuyển thành `Integer` thành công, nhưng số lượng đơn hàng không được phép âm. Tương tự, một `Map` có thể chuyển thành DTO dù giá trị nằm ngoài giới hạn nghiệp vụ.

Sau `readValue` hoặc `convertValue`, vẫn cần validation:

```java
CreateOrderRequest request = mapper.readValue(json, CreateOrderRequest.class);
Set<ConstraintViolation<CreateOrderRequest>> violations = validator.validate(request);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

Với dữ liệu đã có trong bộ nhớ, validate sau `convertValue` theo cùng quy tắc. Nếu có thể, validate nguồn trước hoặc dùng constructor/factory domain để bảo đảm invariant ngay khi tạo object.

## 19. Hiệu năng và bộ nhớ

`convertValue` tránh việc tạo chuỗi JSON hoàn chỉnh và parse lại, nên thường giảm công việc so với `writeValueAsString` rồi `readValue`. Tuy nhiên, nó vẫn thực hiện serialize và deserialize qua token trung gian, có thể cấp phát object và buffer. Không nên xem đây là phép chuyển đổi miễn phí.

So sánh khái quát:

| Cách làm | Công việc chính | Khi phù hợp |
|---|---|---|
| `convertValue` | Serialize source thành token buffer rồi deserialize target | Chuyển đổi object trong bộ nhớ |
| `writeValueAsBytes` + `readValue` | Serialize thành byte JSON, sau đó parse và deserialize | Kiểm tra wire format hoặc cần byte JSON thực tế |
| Mapping thủ công | Đọc property và tạo target trực tiếp | Mapping nghiệp vụ rõ, hiệu năng/kiểm soát cao |
| MapStruct hoặc mapper chuyên dụng | Mapping code được tạo/định nghĩa rõ | Nhiều DTO mapping có cấu trúc ổn định |

Nếu cần chuyển đổi số lượng lớn object trong hot path, hãy benchmark với dữ liệu thật trước khi chọn. Nếu cần xác nhận contract liên hệ thống, ưu tiên kiểm tra byte JSON thực tế thay vì dùng hiệu năng của `convertValue` làm lý do bỏ qua wire serialization.

## 20. Test phân biệt convertValue và readValue

Một test nên xác nhận cả hai API với đúng loại đầu vào:

```java
@Test
void convertsInMemoryMapToDto() {
    Map<String, Object> source = Map.of(
            "id", 101,
            "name", "An",
            "active", true
    );

    UserDto user = mapper.convertValue(source, UserDto.class);

    assertEquals(101L, user.id());
    assertEquals("An", user.name());
    assertTrue(user.active());
}

@Test
void readsJsonDocumentIntoDto() throws Exception {
    String json = """
            {"id":101,"name":"An","active":true}
            """;

    UserDto user = mapper.readValue(json, UserDto.class);

    assertEquals(101L, user.id());
    assertEquals("An", user.name());
    assertTrue(user.active());
}

@Test
void convertValueDoesNotParseJsonText() {
    String jsonText = "{\"id\":101,\"name\":\"An\",\"active\":true}";

    assertThrows(
            IllegalArgumentException.class,
            () -> mapper.convertValue(jsonText, UserDto.class)
    );
}
```

Test cuối minh họa lỗi dùng sai API. Exception cụ thể có thể phụ thuộc kiểu đích và cấu hình; điểm quan trọng là chuỗi JSON được đưa vào như một Java string value, không phải document parser input.

## 21. Bảng quyết định nhanh

| Tình huống | Chọn | Tránh |
|---|---|---|
| Có Java object và muốn map sang DTO tương thích | `convertValue` | Serialize ra string chỉ để map lại nếu không cần wire bytes |
| Có JSON text từ request/file | `readValue` | `convertValue(jsonText, Target.class)` |
| Có `JsonNode` | `treeToValue` hoặc `convertValue` | Chuyển tree thành string rồi parse lại không cần thiết |
| Muốn object thành `JsonNode` | `valueToTree` | Ghi JSON string rồi parse lại chỉ để tạo tree |
| Cần kiểm tra JSON thực tế gửi qua network | `writeValueAsBytes` rồi test/readValue | Chỉ test bằng `convertValue` |
| Cần generic target | `TypeReference` hoặc `JavaType` | Raw `List.class`/`Map.class` |
| Mapping có quy tắc nghiệp vụ hoặc field khác nhau | Code mapping tường minh | Dựa vào property matching tự động mà không kiểm tra |
| Cần bảo toàn object identity hoặc byte gốc | Thiết kế cơ chế riêng phù hợp | Xem `convertValue` như deep clone hoặc byte-preserving conversion |

## 22. Ghi nhớ

`convertValue` chuyển một giá trị Java đang có trong bộ nhớ sang kiểu đích bằng cơ chế serialize/deserialize nội bộ của Jackson, thường qua token buffer và không tạo JSON text trung gian. `readValue` đọc một tài liệu JSON từ string, byte, file hoặc stream, parse token rồi deserialize thành kiểu Java.

Một chuỗi JSON đưa vào `convertValue` vẫn là Java `String`; nó không được parse như một object JSON. Dùng `readValue` cho JSON text/bytes, `convertValue` cho object/Map trong bộ nhớ, `treeToValue` cho `JsonNode` sang POJO và `valueToTree` cho POJO sang cây. Cung cấp `TypeReference`/`JavaType` cho generic target, dùng đúng mapper/module production và nhớ rằng conversion không được bảo đảm giống hệt serialize thành JSON rồi parse lại. Chuyển đổi thành công cũng không thay thế validation nghiệp vụ.
