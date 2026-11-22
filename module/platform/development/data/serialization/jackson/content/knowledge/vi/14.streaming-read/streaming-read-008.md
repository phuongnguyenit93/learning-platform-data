# Xử lý trường thiếu, trường thừa và thứ tự trường thay đổi

Khi đọc JSON theo luồng, dữ liệu đến dưới dạng chuỗi token theo đúng thứ tự byte trong tài liệu. Một object JSON có thể chứa property theo nhiều thứ tự khác nhau; producer có thể gửi thêm field mới mà consumer cũ chưa biết; một field mà ứng dụng mong đợi cũng có thể không xuất hiện. Nếu code đọc stream giả định thứ tự cố định hoặc dừng ngay khi gặp tên field lạ, hệ thống dễ hỏng khi schema phát triển.

Jackson cung cấp hai mức xử lý. Databinding dùng ObjectMapper để ánh xạ JSON vào POJO/record và có feature điều khiển field không biết hoặc creator property bị thiếu. Streaming API dùng JsonParser để đọc từng token; code ứng dụng tự quyết định field nào được nhận, field nào bị bỏ qua, field nào bắt buộc và thứ tự xử lý ra sao.

Điểm cốt lõi là JSON object không quy định ý nghĩa nghiệp vụ theo thứ tự property. Vì vậy, code streaming phải nhận diện property bằng tên, xử lý token value tương ứng và tiếp tục đến hết object. Với field thiếu hoặc field thừa, hãy chọn chính sách rõ ràng theo hợp đồng dữ liệu: chấp nhận, bỏ qua, lưu lại, đặt mặc định hay báo lỗi.

## 1. Ba tình huống cần phân biệt

Ví dụ một client gửi object:

```json
{
  "id": "u-17",
  "name": "An",
  "active": true
}
```

Server mong đợi id, name và active. Có ba tình huống độc lập:

| Tình huống | Ví dụ | Câu hỏi cần xử lý |
|---|---|---|
| Trường thiếu (missing) | Không có active | Dùng giá trị mặc định, xem là null hay từ chối? |
| Trường thừa/không biết (unknown/extra) | Có thêm nickname | Bỏ qua, giữ trong map mở rộng hay từ chối? |
| Thứ tự thay đổi | active xuất hiện trước id | Parser tìm field theo tên hay đang giả định thứ tự? |

Một payload có thể đồng thời chứa cả ba tình huống. Producer mới có thể thêm nickname, bỏ active vì nó trở thành optional, đồng thời sắp xếp property theo alphabet. Consumer cũ cần chính sách tương thích đã được xác định thay vì phụ thuộc thứ tự field.

### 1.1. Missing không giống null

Các JSON sau có trạng thái khác nhau:

```json
{}
```

```json
{ "name": null }
```

```json
{ "name": "" }
```

- Missing: property không xuất hiện trong object.
- Explicit null: property có mặt và token value là JSON null.
- Empty string: property có mặt và giá trị là chuỗi rỗng.

Với POJO mutable thông thường, nếu property bị thiếu, Jackson thường không gọi setter cho property đó; field giữ giá trị đã khởi tạo hoặc giá trị mặc định của Java. Nếu property xuất hiện với null, Jackson xử lý null theo kiểu đích và cấu hình null của property. Với String, mặc định thường gán null; với primitive, hành vi còn phụ thuộc feature và kiểu.

Nếu nghiệp vụ cần phân biệt cả ba trạng thái, không thể chỉ nhìn giá trị cuối cùng của field. Cần dùng cờ seen, wrapper/presence type, JsonNode.has(...) hoặc DTO chuyên biểu diễn trạng thái cập nhật.

## 2. Thứ tự property trong JSON object

JSON object là tập hợp các cặp name/value. Theo mô hình dữ liệu JSON, thứ tự các member không mang ý nghĩa nghiệp vụ. Hai payload dưới đây tương đương về nội dung:

```json
{
  "id": "u-17",
  "name": "An",
  "active": true
}
```

```json
{
  "active": true,
  "id": "u-17",
  "name": "An"
}
```

Jackson streaming parser vẫn phát token theo đúng thứ tự vật lý xuất hiện trong input. Điều đó có nghĩa code thủ công sẽ nhìn thấy thứ tự khác nhau, dù ý nghĩa object không đổi.

### 2.1. Databinding thông thường không phụ thuộc thứ tự property

Với POJO có setter hoặc field có thể được Jackson gán, databinding ánh xạ theo tên property:

```java
public class UserRequest {
    private String id;
    private String name;
    private boolean active;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
}

UserRequest first = mapper.readValue(jsonInOneOrder, UserRequest.class);
UserRequest second = mapper.readValue(jsonInAnotherOrder, UserRequest.class);
```

Hai object có cùng dữ liệu sau deserialize nếu hai JSON chứa cùng property/value và không có logic setter phụ thuộc thứ tự.

### 2.2. Khi nào thứ tự vẫn có thể ảnh hưởng?

Một số thiết kế có thể tạo ra phụ thuộc thứ tự ngoài ý muốn:

- Setter của property này đọc property khác đã được gán trước đó.
- Custom deserializer xử lý field theo trình tự và dùng giá trị chưa được đọc.
- Constructor/factory cần nhiều creator property và code tự viết giả định thứ tự token.
- Code streaming dừng sau khi đọc một field thay vì đọc hết object.
- Parser được dùng để đọc cấu trúc có thứ tự như array, nơi vị trí thực sự mang ý nghĩa.

Nếu cần logic phụ thuộc nhiều property, hãy thu thập giá trị rồi mới tạo object hoặc validate. Đừng để setter có side effect phụ thuộc property nào xuất hiện trước.

### 2.3. JsonPropertyOrder chỉ điều khiển chiều ghi

Annotation JsonPropertyOrder có thể quy định thứ tự property khi serialize:

```java
@JsonPropertyOrder({ "id", "name", "active" })
public class UserResponse {
    public String id;
    public String name;
    public boolean active;
}
```

Annotation này hữu ích cho output ổn định, snapshot test hoặc tài liệu dễ đọc. Nó không yêu cầu parser đầu vào phải nhận property theo thứ tự đó. Không dùng JsonPropertyOrder như cơ chế sửa lỗi đọc stream có thứ tự field thay đổi.

## 3. Trường thiếu khi dùng ObjectMapper

Khi deserialize vào POJO, cách xử lý field thiếu phụ thuộc kiểu đích và cách tạo object.

### 3.1. Field mutable giữ giá trị khởi tạo

```java
public class SearchRequest {
    private String query = "all";
    private List<String> tags = new ArrayList<>();
    private int page = 1;

    // getter/setter
}
```

Với JSON {}, nếu Jackson tạo object bằng constructor rồi không nhận property tương ứng, các giá trị khởi tạo có thể vẫn còn: query là "all", tags là collection rỗng và page là 1.

Nếu JSON có {"query": null}, giá trị query có thể được gán null theo chính sách null. Missing và null do đó có thể dẫn đến hai trạng thái khác nhau.

### 3.2. Primitive và wrapper

```java
public class CounterRequest {
    private int count;
    private Integer optionalCount;
}
```

Nếu cả hai property bị thiếu, giá trị Java mặc định lần lượt là 0 và null. Nếu JSON có explicit null cho count, Jackson mặc định có thể chuyển thành giá trị primitive mặc định; bật DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES nếu muốn từ chối.

Nếu nghiệp vụ phải phân biệt “client không gửi count” với “client gửi count = 0”, primitive không đủ để biểu diễn trạng thái presence. Dùng Integer, một kiểu wrapper có cờ presence, hoặc DTO patch riêng.

### 3.3. Creator property bị thiếu

Với constructor hoặc record, Jackson cần tạo object từ các tham số creator. Một tham số bị thiếu có thể nhận giá trị mặc định/null tùy kiểu và cấu hình. Có thể bật các feature:

```java
ObjectMapper strictMapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES);
```

- FAIL_ON_MISSING_CREATOR_PROPERTIES: báo lỗi khi creator property bắt buộc bị thiếu.
- FAIL_ON_NULL_CREATOR_PROPERTIES: báo lỗi khi creator property nhận null.

Hai feature này khác nhau. Một property có thể xuất hiện nhưng value là null; đó không phải missing. Nếu bật cả hai, cần chắc rằng mọi creator property của DTO đều thực sự bắt buộc.

JsonProperty(required = true) chủ yếu cung cấp metadata required cho creator property; không nên giả định annotation đó tự biến mọi field mutable có setter thành bắt buộc trong mọi đường databinding. Với POJO mutable, dùng validation hoặc logic kiểm tra sau deserialize.

### 3.4. Dùng JsonNode để phân biệt missing và null

Khi cần kiểm tra presence rõ ràng, có thể đọc JSON thành tree:

```java
JsonNode root = mapper.readTree(json);

boolean hasName = root.has("name");
boolean nameIsNonNull = root.hasNonNull("name");

if (!hasName) {
    // Property không xuất hiện.
} else if (!nameIsNonNull) {
    // Property xuất hiện với JSON null.
} else {
    // Property có giá trị khác null.
}
```

has("name") trả true cả khi property có explicit null. hasNonNull("name") chỉ trả true khi property tồn tại và không null. Với payload patch, hai kiểm tra này giúp quyết định giữ nguyên, xóa hoặc cập nhật giá trị.

## 4. Trường thừa/không biết khi dùng ObjectMapper

Một property được xem là unknown khi Jackson không tìm thấy property tương ứng trong kiểu đích và không có cơ chế xử lý khác như any-setter hoặc ignore rule.

Ví dụ client mới gửi:

```json
{
  "id": "u-17",
  "name": "An",
  "nickname": "annie"
}
```

Model server cũ không có nickname.

### 4.1. FAIL_ON_UNKNOWN_PROPERTIES

DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES điều khiển việc Jackson báo lỗi khi gặp property không được nhận diện sau khi đã thử các cơ chế xử lý khác. Feature này được bật theo mặc định trong Jackson databind thông thường, nhưng framework hoặc cấu hình ứng dụng có thể tắt nó.

Bật nghiêm ngặt:

```java
ObjectMapper strictMapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Khi gặp nickname, deserialize sẽ thất bại nếu không có property, any-setter hoặc ignore rule phù hợp.

Tắt để bỏ qua field mới:

```java
ObjectMapper tolerantMapper = new ObjectMapper()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Khi đó field không biết được bỏ qua. Đây là cách hỗ trợ forward compatibility cho consumer chỉ cần các field mà nó hiểu.

Không nên mặc định tắt strict mode ở mọi nơi. Với command hoặc request nhạy cảm, field lạ có thể chỉ ra client gửi sai tên property, sai version hoặc nhầm schema. Bỏ qua nó có thể làm request được xử lý thiếu dữ liệu mà không ai nhận ra.

### 4.2. JsonIgnoreProperties(ignoreUnknown = true)

Có thể đặt chính sách bỏ qua unknown field cho một DTO cụ thể:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class UserRequest {
    private String id;
    private String name;
    // getter/setter
}
```

Cách này giới hạn sự khoan dung cho kiểu đó, không cần thay đổi toàn mapper. Nó phù hợp với response DTO đọc từ producer có thể bổ sung field mà consumer không cần sử dụng.

Annotation ignoreUnknown không làm mất tác dụng của các lỗi parse khác. JSON sai cú pháp, kiểu value không chuyển được hoặc vi phạm creator constraint vẫn có thể gây lỗi.

### 4.3. JsonAnySetter để giữ field mở rộng

Nếu consumer cần giữ lại field chưa biết để chuyển tiếp hoặc lưu metadata, dùng any-setter:

```java
public class ExtensibleUser {
    private String id;
    private final Map<String, JsonNode> extra = new LinkedHashMap<>();

    @JsonAnySetter
    public void addExtra(String name, JsonNode value) {
        extra.put(name, value);
    }

    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
```

Ví dụ JSON:

```json
{
  "id": "u-17",
  "nickname": "annie",
  "preferences": {
    "theme": "dark"
  }
}
```

id được ánh xạ vào property đã biết; nickname và preferences được đưa vào map extra. Dùng JsonNode giúp giữ kiểu JSON tổng quát, bao gồm object, array, number, boolean và null.

JsonAnySetter phù hợp với extension point có chủ đích. Nếu dùng nó cho mọi DTO, lỗi chính tả như userNmae cũng có thể bị lưu như metadata thay vì phát hiện. Hãy xác định namespace hoặc prefix cho field mở rộng nếu hợp đồng cần phân biệt field chính với extension.

### 4.4. JsonAlias xử lý tên cũ, không phải field bất kỳ

Khi tên property đổi qua các version, JsonAlias có thể cho phép đọc nhiều tên đầu vào:

```java
public class AccountRequest {
    @JsonAlias({ "user_id", "legacyId" })
    private String id;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
}
```

Các tên user_id, legacyId và tên chính id đều có thể ánh xạ vào cùng property khi deserialize. Khi serialize, tên property chính vẫn được dùng; alias không tạo nhiều field output.

Nếu client gửi đồng thời nhiều alias của cùng một property, kết quả có thể phụ thuộc thứ tự token và cách property được gán. Không nên dùng alias như cơ chế merge nhiều giá trị. Hãy từ chối hoặc định nghĩa rõ quy tắc khi hai tên cùng xuất hiện mà value mâu thuẫn.

## 5. Xử lý unknown field ở tầng streaming

Với JsonParser, không có databinding tự động để quyết định field nào đã biết. Code phải đọc tên field và xử lý token tương ứng.

Một object thường có token theo dạng:

```text
START_OBJECT
  FIELD_NAME("id")
  VALUE_STRING("u-17")
  FIELD_NAME("newField")
  START_OBJECT
    FIELD_NAME("enabled")
    VALUE_TRUE
  END_OBJECT
  FIELD_NAME("name")
  VALUE_STRING("An")
END_OBJECT
```

Khi gặp field không biết, phải tiêu thụ toàn bộ value của field đó trước khi đọc field tiếp theo. Value có thể là scalar, object lồng hoặc array; chỉ gọi nextToken() một lần là không đủ nếu value là cấu trúc lồng.

### 5.1. Dùng skipChildren() để bỏ qua value lồng

JsonParser.skipChildren() bỏ qua toàn bộ object hoặc array hiện tại, đưa parser đến token kết thúc cấu trúc tương ứng. Với scalar, nó không cần bỏ qua thêm token.

Ví dụ unknown field là object:

```json
{
  "id": "u-17",
  "futureMetadata": {
    "flags": ["a", "b"],
    "details": { "level": 3 }
  },
  "name": "An"
}
```

Nếu parser chỉ gọi nextToken() để bỏ futureMetadata, nó sẽ đứng ở START_OBJECT; vòng lặp bên ngoài có thể nhầm flags hoặc details là field trực tiếp của user. skipChildren() bảo đảm parser bỏ toàn bộ value lồng và quay lại đúng ranh giới object cha.

### 5.2. Mẫu đọc object theo tên field

Ví dụ sau minh họa cách đọc thủ công một UserRequest với thứ tự property tùy ý. Field lạ được bỏ qua bằng skipChildren():

```java
public UserRequest readUser(JsonParser parser) throws IOException {
    if (parser.currentToken() != JsonToken.START_OBJECT) {
        throw new JsonParseException(parser, "Expected a JSON object");
    }

    String id = null;
    String name = null;
    Boolean active = null;
    boolean idSeen = false;

    JsonToken token;
    while ((token = parser.nextToken()) != JsonToken.END_OBJECT) {
        if (token == null) {
            throw new JsonParseException(parser, "Unexpected end of input");
        }
        if (token != JsonToken.FIELD_NAME) {
            throw new JsonParseException(parser, "Expected a field name");
        }

        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();
        if (valueToken == null) {
            throw new JsonParseException(parser, "Missing field value");
        }

        switch (fieldName) {
            case "id" -> {
                idSeen = true;
                if (valueToken == JsonToken.VALUE_NULL) {
                    id = null;
                } else if (valueToken == JsonToken.VALUE_STRING) {
                    id = parser.getText();
                } else {
                    throw new JsonParseException(parser, "id must be a string");
                }
            }
            case "name" -> {
                if (valueToken == JsonToken.VALUE_NULL) {
                    name = null;
                } else if (valueToken == JsonToken.VALUE_STRING) {
                    name = parser.getText();
                } else {
                    throw new JsonParseException(parser, "name must be a string");
                }
            }
            case "active" -> {
                if (valueToken == JsonToken.VALUE_NULL) {
                    active = null;
                } else if (valueToken == JsonToken.VALUE_TRUE) {
                    active = true;
                } else if (valueToken == JsonToken.VALUE_FALSE) {
                    active = false;
                } else {
                    throw new JsonParseException(parser, "active must be boolean");
                }
            }
            default -> parser.skipChildren();
        }
    }

    if (!idSeen || id == null) {
        throw new JsonParseException(parser, "Required field 'id' is missing or null");
    }

    UserRequest result = new UserRequest();
    result.setId(id);
    result.setName(name);
    if (active != null) {
        result.setActive(active);
    }
    return result;
}
```

Đây là ví dụ cho Java 17 trở lên vì dùng switch arrow. Với Java cũ hơn, thay bằng switch statement truyền thống. Ví dụ giả định parser đang đứng ở START_OBJECT; nếu được gọi từ custom deserializer, token hiện tại phải được kiểm tra theo đúng contract của deserializer.

Điểm quan trọng trong vòng lặp:

1. Đọc FIELD_NAME.
2. Lấy tên field bằng currentName().
3. Gọi nextToken() để đến value.
4. Xử lý theo tên và loại token.
5. Với field không biết, gọi skipChildren() để bỏ toàn bộ value nếu là object/array.
6. Tiếp tục cho đến END_OBJECT.

Không có nhánh nào yêu cầu id phải xuất hiện trước name hoặc active.

### 5.3. Giữ unknown field thay vì bỏ qua

Nếu muốn lưu field chưa biết, có thể đọc chúng thành JsonNode bằng codec:

```java
JsonNode extraValue = parser.getCodec().readTree(parser);
extraFields.put(fieldName, extraValue);
```

Khi gọi readTree(parser), parser tiêu thụ toàn bộ value hiện tại, kể cả object/array lồng. Đây là lựa chọn tiện lợi nếu cần giữ cấu trúc JSON tùy ý. Tuy nhiên, nó tạo tree cho value đó; với payload rất lớn, bỏ qua bằng skipChildren() hoặc xử lý streaming riêng sẽ tiết kiệm bộ nhớ hơn.

## 6. Trường thiếu trong code streaming

Trong code streaming thủ công, ứng dụng tự quyết định field nào bắt buộc. Cách đơn giản là giữ cờ seen cho từng field:

```java
boolean idSeen = false;
boolean nameSeen = false;

// Trong switch:
case "id" -> {
    idSeen = true;
    // Đọc giá trị id.
}
case "name" -> {
    nameSeen = true;
    // Đọc giá trị name.
}

// Sau END_OBJECT:
if (!idSeen) {
    throw new IllegalArgumentException("Missing id");
}
```

Cờ seen phân biệt:

- Không có field: seen == false.
- Có field với null: seen == true, value Java có thể null.
- Có field với giá trị: seen == true, value khác null.

Nếu chỉ kiểm tra id == null, hai trường hợp đầu sẽ bị gộp lại. Với PATCH, sự khác biệt này thường quyết định giữ nguyên hay xóa dữ liệu.

### 6.1. Giá trị mặc định và required field

Mỗi field cần một chính sách được ghi rõ:

| Field | Missing | Explicit null | Giá trị hợp lệ |
|---|---|---|---|
| id bắt buộc | Báo lỗi | Báo lỗi | Gán giá trị |
| description tùy chọn | Giữ default | Gán null hoặc bỏ qua theo hợp đồng | Gán giá trị |
| active có default true | Giữ true | Báo lỗi hoặc xử lý riêng | Gán true/false |
| tags collection | Giữ list rỗng | Null, empty hoặc skip theo hợp đồng | Gán collection |

Không nên dùng một default chung cho mọi kiểu. 0, false, null và empty collection có thể là dữ liệu hợp lệ khác nhau.

### 6.2. Creator và thứ tự field

Một custom parser có thể nhận field theo thứ tự bất kỳ bằng cách thu thập giá trị vào biến tạm rồi tạo object sau khi đọc xong:

```java
String id = null;
String name = null;
Integer priority = null;

// Đọc các field bất kỳ thứ tự, lưu vào biến tạm.
// Sau END_OBJECT, validate required/null/range.

return new Task(id, name, priority);
```

Đây là cách an toàn cho constructor bất biến cần nhiều property. Không tạo object ngay khi gặp field đầu tiên nếu constructor cần các field có thể xuất hiện sau đó.

## 7. Nested object và array trong streaming

Khi field đã biết chứa object lồng, có thể chuyển parser cho databinding:

```java
case "address" -> {
    if (valueToken == JsonToken.VALUE_NULL) {
        address = null;
    } else if (valueToken == JsonToken.START_OBJECT) {
        address = parser.readValueAs(Address.class);
    } else {
        throw new JsonParseException(parser, "address must be an object");
    }
}
```

Với array:

```java
case "roles" -> {
    if (valueToken == JsonToken.START_ARRAY) {
        roles = parser.readValueAs(
            mapper.getTypeFactory()
                .constructCollectionType(List.class, String.class)
        );
    } else if (valueToken == JsonToken.VALUE_NULL) {
        roles = null;
    } else {
        throw new JsonParseException(parser, "roles must be an array");
    }
}
```

readValueAs dùng codec đã gắn với parser để đọc value hiện tại thành kiểu đích. Khi xử lý xong, parser được đưa đến token sau cấu trúc vừa đọc, nhờ vậy vòng lặp object cha tiếp tục đúng ranh giới.

Nếu không có codec gắn với parser, có thể dùng ObjectMapper.readValue(parser, type) hoặc tự duyệt token. Trong custom deserializer, parser.getCodec() thường là mapper/codec của lần đọc hiện tại.

## 8. Duplicate field là tình huống riêng

JSON object có thể xuất hiện cùng một tên property nhiều lần trong input:

```json
{
  "role": "user",
  "role": "admin"
}
```

Duplicate field không giống unknown field hoặc field order. Nếu consumer không định nghĩa chính sách, các lần gán có thể khiến giá trị sau ghi đè giá trị trước trong một số đường mapping. Điều này có thể gây khác biệt giữa parser, proxy, validator và ứng dụng phía sau.

Có thể bật strict duplicate detection ở JsonFactory:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Với Jackson 2.x, API builder/feature có thể khác đôi chút theo phiên bản; JsonParser.Feature.STRICT_DUPLICATE_DETECTION là cách cấu hình tương ứng ở các API cũ. Hãy dùng API được hỗ trợ bởi dependency đang dùng và kiểm thử với phiên bản thực tế.

Nếu duplicate field không bị từ chối, hãy quy định rõ last-value-wins, first-value-wins hay merge semantics. Với dữ liệu bảo mật, quyền hạn hoặc chữ ký, từ chối duplicate thường là lựa chọn an toàn hơn.

## 9. Các chính sách tương thích schema

Không có một chính sách đúng cho mọi hệ thống. Consumer nên chọn mức nghiêm ngặt theo loại dữ liệu và vai trò của nó.

| Chính sách | Khi gặp field thừa | Khi thiếu field tùy chọn | Ưu điểm | Rủi ro |
|---|---|---|---|---|
| Strict | Báo lỗi | Chấp nhận theo default | Phát hiện schema drift sớm | Producer thêm field có thể làm consumer cũ lỗi. |
| Ignore unknown | Bỏ qua | Chấp nhận theo default | Hỗ trợ producer thêm field | Có thể che lỗi chính tả hoặc field bắt buộc bị đổi tên. |
| Capture unknown | Lưu vào extension map | Chấp nhận theo default | Giữ thông tin mới để forward/store | Tăng bộ nhớ và cần namespace rõ. |
| Version-specific DTO | Theo schema của version | Theo contract version | Hợp đồng rõ, dễ deprecate | Cần duy trì nhiều DTO/mapping. |

### 9.1. Producer thêm field

Nếu producer bổ sung field optional và consumer cũ không cần nó, ignore unknown hoặc capture unknown giúp consumer tiếp tục hoạt động. Nếu field mới làm thay đổi semantics của field cũ, bỏ qua field mới có thể không đủ để bảo đảm tương thích.

### 9.2. Producer bỏ field

Nếu consumer vẫn cần field đã bị bỏ, missing field phải được phát hiện bằng required check hoặc validation. Đừng tự gán giá trị mặc định có thể gây hành vi sai, ví dụ isAdmin = false khi field quyền hạn bị thiếu do lỗi producer.

### 9.3. Đổi tên field

Có thể dùng JsonAlias trong giai đoạn chuyển đổi để đọc cả tên cũ và tên mới. Output nên dùng tên chuẩn của version hiện tại. Sau khi client cũ được chuyển đổi, loại bỏ alias trong một thay đổi có kiểm soát.

### 9.4. Thay đổi kiểu field

Đổi count từ number sang string, hoặc object sang scalar, thường là breaking change. Không nên dựa vào coercion ngầm để hỗ trợ tất cả payload. Dùng field mới/version mới hoặc custom deserializer có quy tắc rõ và thời hạn kết thúc.

## 10. DeserializationProblemHandler cho chính sách dùng chung

Khi nhiều DTO cần xử lý unknown property theo một quy tắc chung, Jackson có DeserializationProblemHandler. Handler có thể được đăng ký với mapper để can thiệp khi gặp unknown property.

Ví dụ:

```java
public class UnknownFieldHandler extends DeserializationProblemHandler {
    @Override
    public boolean handleUnknownProperty(
            DeserializationContext context,
            JsonParser parser,
            JsonDeserializer<?> deserializer,
            Object beanOrClass,
            String propertyName) throws IOException {

        parser.skipChildren();
        // Có thể ghi metric tên field và loại DTO ở đây.
        return true;
    }
}
```

Đăng ký:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addHandler(new UnknownFieldHandler());
```

Handler trả true khi đã xử lý property. Nếu trả false, cơ chế xử lý tiếp theo có thể báo lỗi unknown property theo cấu hình. Handler dùng chung nên tránh ghi log toàn bộ value vì có thể chứa dữ liệu nhạy cảm hoặc payload lớn. Chỉ ghi metadata cần thiết như tên field, loại DTO và version.

Nếu chỉ một DTO cần ignore hoặc capture field, annotation JsonIgnoreProperties/JsonAnySetter thường dễ đọc hơn handler toàn mapper.

## 11. Đọc nhiều object liên tiếp theo luồng

Một số nguồn truyền nhiều JSON document hoặc record liên tiếp thay vì một array bao ngoài. Khi dùng streaming, mỗi record cần được xử lý độc lập và parser phải tiêu thụ hết object hiện tại.

Ví dụ đọc một JSON array lớn:

```java
try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new JsonParseException(parser, "Expected an array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        UserRequest user = parser.readValueAs(UserRequest.class);
        process(user);
    }
}
```

Databinding cho từng phần tử vẫn xử lý property theo tên và theo chính sách unknown/missing đã cấu hình. Nếu thay bằng parser thủ công, phải đọc hết từng object, bao gồm nested values, trước khi chuyển sang record tiếp theo.

Với nguồn JSON Lines (mỗi dòng một JSON document), cách đọc thường là tách theo dòng rồi tạo parser cho từng record hoặc dùng API đọc sequence phù hợp. Không được giả định newline trong mọi JSON string là ranh giới record nếu format nguồn không phải JSON Lines.

## 12. Kiểm thử missing, extra và order

Nên tách test theo từng hành vi để biết chính sách nào được áp dụng.

### 12.1. Test thứ tự property không ảnh hưởng kết quả

```java
@Test
void acceptsPropertiesInDifferentOrders() throws Exception {
    String first = """
        {"id":"u-17","name":"An","active":true}
        """;
    String second = """
        {"active":true,"name":"An","id":"u-17"}
        """;

    UserRequest a = mapper.readValue(first, UserRequest.class);
    UserRequest b = mapper.readValue(second, UserRequest.class);

    assertEquals(a.getId(), b.getId());
    assertEquals(a.getName(), b.getName());
    assertEquals(a.isActive(), b.isActive());
}
```

### 12.2. Test unknown property strict và lenient

```java
@Test
void strictMapperRejectsUnknownProperty() {
    ObjectMapper strict = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    assertThrows(UnrecognizedPropertyException.class, () ->
        strict.readValue(
            "{\"id\":\"u-17\",\"nickname\":\"annie\"}",
            UserRequest.class
        )
    );
}

@Test
void lenientMapperIgnoresUnknownProperty() throws Exception {
    ObjectMapper lenient = new ObjectMapper()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    UserRequest user = lenient.readValue(
        "{\"id\":\"u-17\",\"nickname\":\"annie\"}",
        UserRequest.class
    );

    assertEquals("u-17", user.getId());
}
```

Nếu DTO có JsonAnySetter hoặc JsonIgnoreProperties, hãy test riêng vì chúng có thể xử lý unknown field trước khi feature toàn mapper quyết định.

### 12.3. Test missing khác explicit null

```java
@Test
void distinguishesMissingAndExplicitNullWithTreeModel() throws Exception {
    JsonNode missing = mapper.readTree("{}");
    JsonNode explicitNull = mapper.readTree("{\"name\":null}");

    assertFalse(missing.has("name"));
    assertFalse(missing.hasNonNull("name"));

    assertTrue(explicitNull.has("name"));
    assertFalse(explicitNull.hasNonNull("name"));
}
```

### 12.4. Test unknown nested value được bỏ qua hoàn toàn

Với streaming parser thủ công, tạo unknown field chứa object và array lồng sâu rồi đặt field đã biết ở phía sau. Test phải xác nhận field phía sau vẫn được đọc đúng. Đây là cách phát hiện lỗi quên gọi skipChildren().

### 12.5. Test duplicate property

Nếu bật strict duplicate detection, xác nhận object có hai property cùng tên bị từ chối. Test cả duplicate ở object lồng nhau nếu hợp đồng yêu cầu phát hiện trên toàn bộ document.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Field bị gán nhầm khi producer đổi thứ tự | Code streaming đọc theo vị trí token | Dispatch theo currentName() và đọc hết object. |
| Unknown nested object làm parser lệch trạng thái | Chỉ gọi nextToken() một lần để bỏ field | Gọi skipChildren() hoặc đọc toàn bộ value bằng codec. |
| Consumer cũ lỗi khi producer thêm field | FAIL_ON_UNKNOWN_PROPERTIES đang bật | Chọn ignore/capture/versioning theo hợp đồng. |
| Sai dữ liệu khi field bị thiếu | Dùng primitive/default mà không validate presence | Dùng wrapper/cờ seen hoặc required creator feature. |
| Không phân biệt null và missing | Chỉ kiểm tra giá trị Java cuối cùng | Dùng seen, JsonNode.has/hasNonNull hoặc presence wrapper. |
| Field đổi tên khiến property thành null | Consumer không có alias hoặc version mapping | Dùng JsonAlias có thời hạn hoặc DTO version mới. |
| Unknown field typo bị âm thầm bỏ qua | Tắt unknown-property strict mode toàn cục | Giới hạn ignore ở DTO phù hợp hoặc giữ strict cho command. |
| Duplicate property tạo kết quả không rõ | Không có duplicate detection | Bật strict duplicate detection hoặc định nghĩa rõ semantics. |
| Setter cho kết quả khác theo order | Setter phụ thuộc trạng thái field khác | Thu thập rồi validate/map sau khi đọc xong object. |

## 14. Chọn chính sách theo loại consumer

| Consumer | Missing field | Extra field | Field order |
|---|---|---|---|
| Public API command | Validate required; default có chủ đích | Thường strict hoặc chỉ ignore ở extension point | Luôn theo tên property |
| Public API response client | Theo schema/version | Client nên bỏ qua field chưa biết nếu contract hỗ trợ forward compatibility | Không phụ thuộc order |
| Event consumer cần forward metadata | Presence-aware | Capture unknown field nếu cần chuyển tiếp | Không phụ thuộc order |
| Import file do người dùng cung cấp | Validate required và kiểu dữ liệu | Có thể báo lỗi để phát hiện file sai schema | Không phụ thuộc thứ tự object property |
| High-throughput streaming | Cờ presence tối thiểu, validation đúng mức | skipChildren() cho field không cần | Dispatch theo field name, tránh tạo tree không cần thiết |

Không nên áp dụng ignore unknown cho mọi consumer chỉ để giảm lỗi. Với dữ liệu đầu vào do người dùng hoặc command thay đổi trạng thái, báo lỗi sớm có thể tốt hơn việc chấp nhận payload sai. Với response/event do producer độc lập phát triển, bỏ qua field mới có thể là lựa chọn hợp lý nếu các field đã biết vẫn giữ nguyên semantics.

## 15. Nguyên tắc triển khai

1. Phân biệt missing, explicit null, empty value và default.
2. Không giả định property trong JSON object xuất hiện theo một thứ tự cố định.
3. Trong streaming code, đọc FIELD_NAME, lấy tên và dispatch value theo tên đó.
4. Khi bỏ unknown field có object/array lồng, dùng skipChildren() để tiêu thụ toàn bộ value.
5. Chỉ bỏ unknown field khi hợp đồng cho phép; cân nhắc strict mode cho command và input nhạy cảm.
6. Dùng JsonAnySetter khi cần giữ extension field; dùng JsonAlias cho tên cũ đã biết.
7. Với field bắt buộc, kiểm tra presence riêng; đừng suy ra missing chỉ từ giá trị null cuối cùng.
8. Dùng creator features cho constructor/record khi mọi creator property cần được kiểm soát.
9. Xem duplicate field là vấn đề riêng và bật strict duplicate detection nếu cần.
10. Tránh setter có side effect phụ thuộc thứ tự property.
11. Giữ DTO theo version khi schema hoặc semantics thay đổi không tương thích.
12. Test payload có field thiếu, field thừa, nested unknown value, thứ tự khác nhau và duplicate field.

Khi đọc JSON theo luồng, thứ tự token là thứ tự byte trong tài liệu; tên property mới là khóa để diễn giải object. Databinding của Jackson giúp xử lý phần lớn khác biệt thứ tự, còn code streaming thủ công phải tự duy trì nguyên tắc đó. Chính sách missing và unknown cần được chọn theo hợp đồng API, đồng thời được kiểm thử rõ ràng để schema có thể phát triển mà consumer vẫn xử lý dữ liệu đúng.
