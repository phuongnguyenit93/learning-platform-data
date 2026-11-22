# Ba cách xử lý: ánh xạ đối tượng, cây dữ liệu và luồng token

Jackson cung cấp ba cách làm việc với JSON ở ba mức trừu tượng khác nhau: **ánh xạ đối tượng (data binding)**, **mô hình cây (tree model)** và **xử lý luồng token (streaming)**. Cả ba đều có thể đọc và ghi JSON, nhưng chúng khác nhau ở cách biểu diễn dữ liệu trong Java, lượng dữ liệu cần giữ trong bộ nhớ và mức độ kiểm soát mà chương trình có được.

Ví dụ, với JSON sau:

```json
{
  "id": 25,
  "name": "An",
  "active": true,
  "roles": ["reader", "editor"]
}
```

Ta có thể ánh xạ trực tiếp JSON thành một đối tượng `User`, duyệt các nút như `id` và `roles` trong một cây `JsonNode`, hoặc đọc lần lượt từng token như `START_OBJECT`, `FIELD_NAME`, `VALUE_NUMBER_INT` và `END_OBJECT`. Việc chọn cách nào phụ thuộc chủ yếu vào mức độ ổn định của cấu trúc JSON và quy mô dữ liệu cần xử lý.

## 1. Ánh xạ đối tượng (Data Binding)

Data binding chuyển dữ liệu JSON thành các đối tượng Java và chuyển đối tượng Java thành JSON. Đây là cách tiếp cận thuận tiện nhất khi cấu trúc dữ liệu đã biết và tương ứng rõ ràng với các lớp trong ứng dụng.

Trong Jackson Databind, `ObjectMapper` là lớp thường dùng để thực hiện hai chiều chuyển đổi:

- **Serialize:** đối tượng Java → chuỗi hoặc luồng JSON.
- **Deserialize:** JSON → đối tượng Java.

### 1.1. Đọc và ghi một đối tượng

Giả sử ứng dụng có lớp `User`:

```java
public class User {
    private long id;
    private String name;
    private boolean active;

    public User() {
    }

    public User(long id, String name, boolean active) {
        this.id = id;
        this.name = name;
        this.active = active;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Có thể đọc JSON và ghi đối tượng như sau:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "id": 25,
      "name": "An",
      "active": true
    }
    """;

// Deserialize: JSON thành đối tượng Java
User user = mapper.readValue(json, User.class);

// Truy cập dữ liệu bằng API của lớp Java
System.out.println(user.getName());

// Serialize: đối tượng Java thành JSON
String output = mapper.writeValueAsString(user);
System.out.println(output);
```

Jackson đối chiếu các thuộc tính JSON với thuộc tính mà nó có thể truy cập trên lớp Java. Cách ánh xạ cụ thể phụ thuộc vào constructor, getter, setter, field, annotation và cấu hình của mapper. Vì vậy, lớp Java cần cung cấp một cách tạo và gán giá trị phù hợp với cấu trúc dữ liệu đầu vào.

### 1.2. Điều chỉnh tên và quy tắc ánh xạ

Tên thuộc tính JSON có thể khác tên field Java. Annotation giúp khai báo rõ quy tắc ánh xạ:

```java
public class Account {
    @JsonProperty("account_id")
    private long id;

    @JsonProperty("display_name")
    private String displayName;

    @JsonIgnore
    private String internalNote;

    // Constructor, getter và setter phù hợp
}
```

Trong ví dụ này, JSON dùng `account_id` và `display_name`, trong khi mã Java dùng `id` và `displayName`. `@JsonIgnore` loại thuộc tính `internalNote` khỏi quá trình ánh xạ theo quy tắc của annotation.

Một số annotation thường gặp:

| Annotation | Mục đích |
|---|---|
| `@JsonProperty` | Khai báo tên thuộc tính JSON hoặc chỉ định thuộc tính cần ánh xạ. |
| `@JsonIgnore` | Bỏ qua thuộc tính trong quá trình serialize hoặc deserialize. |
| `@JsonInclude` | Quy định khi nào thuộc tính được đưa vào JSON, chẳng hạn bỏ giá trị `null`. |
| `@JsonCreator` | Đánh dấu constructor hoặc factory method dùng để tạo đối tượng khi deserialize. |
| `@JsonIgnoreProperties` | Bỏ qua một số thuộc tính được chỉ định; có thể dùng `ignoreUnknown = true` để bỏ qua thuộc tính JSON không được mô hình Java khai báo. |

Ví dụ, nếu API có thể bổ sung field mà ứng dụng hiện tại chưa sử dụng, lớp DTO có thể khai báo:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class User {
    private long id;
    private String name;

    // Constructor, getter và setter
}
```

Khi đó, các field JSON không có thuộc tính tương ứng sẽ được bỏ qua đối với lớp này. Nếu không bật cơ chế bỏ qua, hành vi với thuộc tính không nhận diện còn phụ thuộc cấu hình Jackson; cấu hình mặc định thường báo lỗi khi gặp thuộc tính không biết trong quá trình deserialize.

### 1.3. Deserialize collection và kiểu generic

Với kiểu cụ thể như `User.class`, ta có thể truyền trực tiếp `Class<T>`. Nhưng Java xóa thông tin generic ở runtime, nên `List<User>.class` không phải một class literal hợp lệ. Jackson cung cấp `TypeReference` để giữ mô tả kiểu generic:

```java
String json = """
    [
      {"id": 1, "name": "An", "active": true},
      {"id": 2, "name": "Binh", "active": false}
    ]
    """;

List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
```

Với kiểu generic được xác định lúc chạy, có thể tạo `JavaType` thông qua `TypeFactory`:

```java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, userListType);
```

### 1.4. Khi nào nên dùng data binding?

Data binding phù hợp khi:

- Cấu trúc JSON đã được mô tả bằng DTO, model hoặc record trong ứng dụng.
- Phần lớn field cần được sử dụng như thuộc tính Java có kiểu rõ ràng.
- Muốn tận dụng compiler, IDE, kiểu dữ liệu và các API nghiệp vụ của Java.
- Muốn giảm mã xử lý thủ công cho từng field JSON.

Đổi lại, cấu trúc Java cần theo kịp hợp đồng dữ liệu. Khi JSON thay đổi thường xuyên hoặc có nhiều field không thể dự đoán trước, việc ánh xạ toàn bộ vào một lớp cố định có thể kém linh hoạt.

## 2. Mô hình cây (Tree Model)

Tree model biểu diễn JSON thành một cây các node. Mỗi object JSON trở thành một object node, mỗi array trở thành một array node, còn string, number, boolean và null trở thành các node giá trị tương ứng.

Kiểu nền tảng để đọc cây là `JsonNode`. Với node object có thể dùng `ObjectNode`; với node array có thể dùng `ArrayNode`. Ta không cần tạo một lớp Java riêng cho toàn bộ cấu trúc JSON trước khi đọc dữ liệu.

### 2.1. Đọc JSON thành cây

`ObjectMapper.readTree()` đọc JSON và trả về node gốc:

```java
String json = """
    {
      "id": 25,
      "profile": {
        "name": "An",
        "city": "Da Nang"
      },
      "roles": ["reader", "editor"]
    }
    """;

JsonNode root = mapper.readTree(json);

long id = root.path("id").asLong();
String name = root.path("profile")
                  .path("name")
                  .asText();
String firstRole = root.path("roles")
                      .path(0)
                      .asText();
```

`path()` cho phép đi sâu qua object hoặc array. Nếu đường dẫn không tồn tại, nó trả về một `MissingNode` thay vì `null`, nhờ đó có thể tiếp tục gọi `path()` trên kết quả mà không phải kiểm tra null ở từng cấp.

`get()` có hành vi khác: nếu field hoặc index không tồn tại, nó trả về `null`. Vì vậy, khi dùng `get()`, cần kiểm tra kết quả trước khi gọi phương thức trên node:

```java
JsonNode profile = root.get("profile");
if (profile != null && profile.hasNonNull("name")) {
    String name = profile.get("name").asText();
}
```

Nên phân biệt ba tình huống:

- Field không tồn tại: `get()` trả về `null`; `path()` trả về `MissingNode`.
- Field tồn tại với JSON `null`: node là `NullNode`.
- Field tồn tại với giá trị cụ thể: node có kiểu tương ứng, chẳng hạn text, number, object hoặc array.

Các phương thức như `isMissingNode()`, `isNull()`, `isTextual()`, `isNumber()`, `isObject()` và `isArray()` giúp kiểm tra kiểu node trước khi chuyển đổi giá trị.

### 2.2. Duyệt object và array

Có thể duyệt các field của một object bằng `fields()` và các phần tử của array bằng cách lặp qua node:

```java
JsonNode profile = root.path("profile");
if (profile.isObject()) {
    Iterator<Map.Entry<String, JsonNode>> fields = profile.fields();
    while (fields.hasNext()) {
        Map.Entry<String, JsonNode> field = fields.next();
        System.out.println(field.getKey() + " = " + field.getValue());
    }
}

JsonNode roles = root.path("roles");
if (roles.isArray()) {
    for (JsonNode role : roles) {
        System.out.println(role.asText());
    }
}
```

Cách duyệt này hữu ích khi tên field chỉ được biết lúc chạy, hoặc khi cần xử lý một tập thuộc tính có thể thay đổi theo từng bản ghi.

### 2.3. Tạo và thay đổi cây JSON

`ObjectMapper` có thể tạo node mà không cần đọc JSON đầu vào:

```java
ObjectNode userNode = mapper.createObjectNode();
userNode.put("id", 25);
userNode.put("name", "An");
userNode.put("active", true);

ArrayNode roles = userNode.putArray("roles");
roles.add("reader");
roles.add("editor");

String json = mapper.writeValueAsString(userNode);
```

`ObjectNode` hỗ trợ thêm, thay thế hoặc xóa field bằng các phương thức như `put()`, `set()`, `replace()` và `remove()`. `ArrayNode` hỗ trợ thêm phần tử bằng `add()` và các biến thể tương ứng.

Ví dụ, cập nhật tên trong cây đã đọc:

```java
JsonNode node = mapper.readTree(json);
if (node.isObject()) {
    ObjectNode object = (ObjectNode) node;
    object.put("name", "An Nguyen");
    object.remove("temporaryField");
}

String updatedJson = mapper.writeValueAsString(node);
```

`JsonNode` là kiểu API chung để đọc và duyệt. Khi cần thay đổi cấu trúc, hãy xác nhận node là object hoặc array rồi chuyển sang `ObjectNode` hoặc `ArrayNode` tương ứng.

### 2.4. Chuyển đổi giữa cây và đối tượng Java

Tree model có thể kết hợp với data binding. Khi đã tìm được một nhánh có cấu trúc phù hợp với DTO, có thể chuyển nhánh đó thành đối tượng:

```java
JsonNode userNode = root.path("user");
User user = mapper.treeToValue(userNode, User.class);
```

Theo chiều ngược lại, có thể chuyển một đối tượng Java thành cây:

```java
User user = new User(25, "An", true);
JsonNode userNode = mapper.valueToTree(user);
```

`treeToValue()` và `valueToTree()` hữu ích khi ứng dụng cần kết hợp phần dữ liệu có schema rõ ràng với phần JSON linh hoạt. Chúng cũng tránh việc phải tự nối chuỗi JSON để ghép dữ liệu.

### 2.5. Khi nào nên dùng tree model?

Tree model phù hợp khi:

- Cấu trúc JSON chỉ biết một phần hoặc thay đổi theo loại thông điệp.
- Chỉ cần đọc một số field hoặc một nhánh trong tài liệu.
- Cần giữ lại field chưa biết để chuyển tiếp hoặc cập nhật JSON.
- Cần thêm, sửa, xóa field trước khi serialize lại.
- Muốn đọc dữ liệu linh hoạt rồi mới quyết định DTO đích.

Đổi lại, cây giữ biểu diễn node của tài liệu trong bộ nhớ. Với JSON rất lớn, việc tạo toàn bộ cây có thể tốn nhiều bộ nhớ hơn cách đọc tuần tự. Các thao tác lấy giá trị cũng thường cần kiểm tra kiểu node và chuyển đổi tường minh hơn so với truy cập thuộc tính Java.

## 3. Xử lý luồng token (Streaming API)

Streaming API là mức xử lý thấp và trực tiếp nhất trong ba cách. Thay vì tạo cả đối tượng Java hoặc cây node, Jackson đọc JSON thành một chuỗi token theo thứ tự xuất hiện. Khi ghi, chương trình phát các token để tạo ra JSON.

API này thuộc Jackson Core. Hai lớp quan trọng là:

- `JsonParser`: đọc JSON và cung cấp token hiện tại.
- `JsonGenerator`: ghi token để tạo JSON.

### 3.1. Hiểu chuỗi token

Với JSON:

```json
{
  "id": 25,
  "name": "An",
  "roles": ["reader", "editor"]
}
```

Parser lần lượt gặp các token có ý nghĩa như sau:

| Thành phần JSON | Token tiêu biểu |
|---|---|
| Bắt đầu object `{` | `START_OBJECT` |
| Tên field `id` | `FIELD_NAME` |
| Giá trị số `25` | `VALUE_NUMBER_INT` |
| Giá trị chuỗi `"An"` | `VALUE_STRING` |
| Bắt đầu array `[` | `START_ARRAY` |
| Kết thúc array `]` | `END_ARRAY` |
| Kết thúc object `}` | `END_OBJECT` |

Parser duy trì vị trí hiện tại trong tài liệu. Mỗi lần gọi `nextToken()`, parser tiến đến token tiếp theo và trả về loại token đó. Chương trình quyết định field nào cần đọc, field nào cần bỏ qua và khi nào kết thúc xử lý.

### 3.2. Đọc JSON bằng JsonParser

Ví dụ sau đọc một object, lấy hai field `id` và `name`, đồng thời bỏ qua các field còn lại:

```java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IllegalArgumentException("Expected a JSON object");
    }

    Long id = null;
    String name = null;

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("id".equals(fieldName)
                && valueToken != null
                && valueToken.isNumeric()) {
            id = parser.getLongValue();
        } else if ("name".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            name = parser.getText();
        } else {
            // Bỏ qua cả giá trị lồng nhau nếu field là object hoặc array.
            parser.skipChildren();
        }
    }

    System.out.println("id=" + id + ", name=" + name);
}
```

Điểm cần chú ý là parser đang đứng ở đâu:

1. `nextToken()` đầu tiên đưa parser đến token mở object.
2. Trong vòng lặp, lần gọi `nextToken()` đầu tiên đưa parser đến tên field.
3. `currentName()` lấy tên field hiện tại.
4. Lần gọi `nextToken()` tiếp theo đưa parser đến token biểu diễn giá trị của field đó.
5. Nếu giá trị là object hoặc array không cần xử lý, `skipChildren()` bỏ qua toàn bộ nội dung lồng nhau.

`skipChildren()` đặc biệt hữu ích khi JSON có nhiều field phức tạp nhưng chương trình chỉ cần một vài field. Với token scalar, phương thức này không phải duyệt một cấu trúc con.

Ví dụ trên tìm field ở cấp object gốc. Nếu JSON có nhiều object lồng nhau và cùng tên field, cần theo dõi cấp lồng nhau hoặc cấu trúc cha để tránh xử lý nhầm field cùng tên ở một nhánh khác.

### 3.3. Ghi JSON bằng JsonGenerator

`JsonGenerator` phát các token theo đúng thứ tự. Jackson chịu trách nhiệm xử lý dấu ngoặc, dấu phẩy, dấu nháy và escape ký tự cho giá trị chuỗi:

```java
StringWriter output = new StringWriter();

try (JsonGenerator generator = mapper.getFactory().createGenerator(output)) {
    generator.writeStartObject();
    generator.writeNumberField("id", 25);
    generator.writeStringField("name", "An");
    generator.writeBooleanField("active", true);

    generator.writeArrayFieldStart("roles");
    generator.writeString("reader");
    generator.writeString("editor");
    generator.writeEndArray();

    generator.writeEndObject();
}

String json = output.toString();
System.out.println(json);
```

Một số phương thức thường dùng:

| Phương thức | Tác dụng |
|---|---|
| `writeStartObject()` / `writeEndObject()` | Bắt đầu / kết thúc JSON object. |
| `writeStartArray()` / `writeEndArray()` | Bắt đầu / kết thúc JSON array. |
| `writeFieldName()` | Ghi tên field tiếp theo trong object. |
| `writeString()` / `writeNumber()` / `writeBoolean()` | Ghi giá trị scalar. |
| `writeNull()` | Ghi giá trị JSON `null`. |
| `writeObject()` | Ghi một giá trị Java qua cơ chế codec được cấu hình cho generator. |

Generator giúp tạo JSON tuần tự mà không phải dựng một cây `JsonNode` hoặc một object graph hoàn chỉnh trước. Việc ghép chuỗi JSON bằng tay dễ tạo lỗi dấu phẩy, escape và ký tự đặc biệt; generator xử lý các quy tắc cú pháp này.

### 3.4. Xử lý dữ liệu lớn theo từng phần

Lợi thế rõ nhất của streaming xuất hiện khi đọc từ `InputStream` hoặc `Reader`, thay vì nạp toàn bộ nội dung vào một `String` trước. Parser có thể xử lý từng phần của nguồn dữ liệu và chương trình chỉ giữ những giá trị cần thiết tại thời điểm hiện tại.

Ví dụ, một file JSON chứa array gồm nhiều user có thể được đọc từng object:

```java
try (InputStream input = Files.newInputStream(Path.of("users.json"));
     JsonParser parser = mapper.getFactory().createParser(input)) {

    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IllegalArgumentException("Expected a JSON array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        User user = mapper.readValue(parser, User.class);
        System.out.println(user.getName());
    }
}
```

Đoạn mã kết hợp streaming với data binding: parser điều hướng qua từng phần tử của array, còn `ObjectMapper` ánh xạ từng object hiện tại thành một `User`. Chương trình có thể xử lý xong một user rồi giải phóng tham chiếu trước khi chuyển sang phần tử tiếp theo.

Lưu ý: nếu tạo parser từ một chuỗi `String` lớn, chuỗi đó vẫn đã nằm trong bộ nhớ. Muốn tận dụng việc đọc tuần tự từ nguồn dữ liệu lớn, hãy tạo parser trực tiếp từ `InputStream`, `Reader` hoặc nguồn phù hợp khác.

### 3.5. Khi nào nên dùng streaming?

Streaming phù hợp khi:

- File hoặc thông điệp JSON rất lớn, đặc biệt là array có nhiều phần tử.
- Chỉ cần trích xuất một số field và có thể bỏ qua phần còn lại.
- Cần ghi kết quả tuần tự ra file, network stream hoặc writer.
- Muốn kiểm soát thứ tự đọc, ghi và xử lý từng token.
- Bộ nhớ cần được giữ ổn định khi kích thước dữ liệu tăng.

Đổi lại, mã streaming thường dài và dễ sai hơn vì chương trình phải quản lý vị trí parser, token hiện tại, cấp lồng nhau và ranh giới giữa các object. Đây là mức API phù hợp khi lợi ích về khả năng kiểm soát hoặc bộ nhớ đủ lớn để bù cho độ phức tạp đó.

## 4. So sánh ba cách xử lý

| Tiêu chí | Data binding | Tree model | Streaming |
|---|---|---|---|
| Biểu diễn trong Java | DTO, model, record hoặc collection | Các node `JsonNode` | Token hiện tại và trạng thái parser/generator |
| Cấu trúc JSON | Phù hợp với schema đã biết | Linh hoạt, có thể chưa biết đầy đủ | Không cần dựng toàn bộ cấu trúc |
| Cách truy cập | Qua thuộc tính Java | Qua tên field, index và node | Đọc tuần tự từng token |
| Thay đổi dữ liệu | Thay đổi object Java | Thêm, sửa, xóa node | Phát token mới hoặc xử lý khi đọc |
| Bộ nhớ | Thường giữ object graph được ánh xạ | Giữ cây node của tài liệu | Có thể xử lý tăng dần, giữ ít dữ liệu hơn |
| Độ phức tạp mã | Thường thấp với schema ổn định | Trung bình | Thường cao hơn vì phải quản lý token |
| Trường hợp tiêu biểu | DTO cho request/response API | JSON linh hoạt, sửa một vài field | File lớn, array dài, xử lý chọn lọc |

Không có cách nào luôn tốt nhất cho mọi trường hợp. Data binding tối ưu sự thuận tiện khi làm việc với model Java. Tree model cân bằng giữa sự linh hoạt và khả năng thao tác có cấu trúc. Streaming cho quyền kiểm soát trực tiếp và khả năng xử lý tăng dần.

## 5. Kết hợp các cách xử lý

Ba cách xử lý không loại trừ lẫn nhau. Một luồng công việc có thể dùng mỗi cách ở phần mà nó phù hợp nhất.

### 5.1. Streaming để chia nhỏ, data binding để ánh xạ từng phần tử

Khi một file chứa hàng triệu object, có thể dùng `JsonParser` để đi qua array và dùng `ObjectMapper.readValue()` để chuyển từng object thành DTO. Cách này giữ phần xử lý nghiệp vụ ở dạng Java có kiểu, trong khi parser kiểm soát việc đọc theo từng phần.

### 5.2. Tree model để kiểm tra cấu trúc, data binding để tạo DTO

Một thông điệp có thể chứa metadata linh hoạt cùng một phần payload có schema ổn định. Chương trình có thể đọc thông điệp thành `JsonNode`, kiểm tra loại sự kiện hoặc phiên bản trong metadata, sau đó chuyển riêng payload thành lớp Java tương ứng:

```java
JsonNode message = mapper.readTree(json);
String eventType = message.path("type").asText();
JsonNode payload = message.path("payload");

if ("user-created".equals(eventType)) {
    User user = mapper.treeToValue(payload, User.class);
    // Xử lý user
}
```

### 5.3. Data binding để tạo dữ liệu, tree model để bổ sung field

Nếu phần lớn dữ liệu thuộc một DTO nhưng cần thêm một vài field động trước khi trả về, có thể chuyển DTO thành cây, cập nhật node rồi serialize:

```java
User user = new User(25, "An", true);
ObjectNode response = mapper.valueToTree(user);
response.put("source", "import");

String json = mapper.writeValueAsString(response);
```

Các cách kết hợp này giúp giữ phần code nghiệp vụ dễ đọc mà vẫn xử lý được những trường hợp JSON linh hoạt hoặc có kích thước lớn.

## 6. Chọn cách tiếp cận cho từng tình huống

Có thể dùng các câu hỏi sau để quyết định:

1. **Đã có lớp Java đại diện cho dữ liệu chưa?** Nếu có và phần lớn cấu trúc đã ổn định, bắt đầu với data binding.
2. **Cần thao tác với field không cố định hoặc chỉ biết một phần cấu trúc?** Dùng tree model để truy cập và thay đổi node linh hoạt.
3. **Dữ liệu lớn đến mức không nên giữ toàn bộ object graph hoặc cây trong bộ nhớ?** Dùng streaming và xử lý theo từng phần.
4. **Cần cả xử lý tuần tự lẫn DTO có kiểu?** Kết hợp streaming với data binding cho từng object.
5. **Cần kiểm tra metadata linh hoạt rồi ánh xạ payload?** Kết hợp tree model với data binding.

Một quy tắc thực tế là chọn API có mức trừu tượng cao nhất vẫn đáp ứng được yêu cầu. Nếu DTO giải quyết được bài toán, data binding thường dễ duy trì hơn. Khi cần sự linh hoạt về cấu trúc, chuyển sang tree model. Khi quy mô hoặc yêu cầu kiểm soát luồng dữ liệu đòi hỏi, dùng streaming cho phần tương ứng.

## 7. Một số điểm cần lưu ý khi sử dụng

### Cấu hình ObjectMapper trước khi dùng chung

`ObjectMapper` được thiết kế để tái sử dụng và an toàn khi nhiều thread cùng sử dụng sau khi cấu hình hoàn tất. Hãy đăng ký module và thiết lập các feature cần thiết trước khi chia sẻ mapper cho nhiều luồng. Tránh thay đổi cấu hình trong khi ứng dụng đang serialize hoặc deserialize.

Nếu cần cấu hình riêng cho từng loại thao tác, `ObjectReader` và `ObjectWriter` là các đối tượng đọc/ghi có cấu hình chuyên biệt và có thể tái sử dụng.

### Phân biệt field thiếu và field có giá trị null

Trong tree model, field không tồn tại và field có JSON `null` là hai trường hợp khác nhau. Trong data binding, cách xử lý field thiếu hoặc null còn liên quan đến kiểu Java, constructor, setter và cấu hình. Với dữ liệu đầu vào quan trọng, hãy xác định rõ ứng dụng cần phân biệt hai trường hợp này hay không.

### Xử lý lỗi theo nguồn dữ liệu

Các thao tác đọc/ghi có thể phát sinh lỗi do JSON sai cú pháp, kiểu giá trị không phù hợp, field bắt buộc không hợp lệ hoặc lỗi I/O. Hãy xử lý exception tại ranh giới phù hợp của ứng dụng và cung cấp đủ ngữ cảnh để xác định nguồn dữ liệu gây lỗi. Không nên âm thầm chuyển mọi lỗi deserialize thành một đối tượng mặc định nếu điều đó có thể làm sai dữ liệu nghiệp vụ.

### Quản lý tài nguyên

Khi chương trình tự tạo `JsonParser`, `JsonGenerator`, `InputStream`, `Reader` hoặc `Writer`, hãy đóng tài nguyên đúng cách, thường bằng `try-with-resources`. Với stream do thành phần khác quản lý, cần hiểu rõ quyền sở hữu tài nguyên và cấu hình đóng stream trước khi chuyển nó cho Jackson.

### Không tự ghép JSON bằng chuỗi

Không nên tạo JSON bằng cách nối chuỗi thủ công từ dữ liệu người dùng. Các ký tự như dấu nháy kép, dấu gạch chéo ngược và ký tự điều khiển cần được escape đúng quy tắc. Hãy để `ObjectMapper`, `ObjectNode` hoặc `JsonGenerator` đảm nhiệm việc serialize.

## Kết luận

Data binding phù hợp với dữ liệu có model Java rõ ràng; tree model phù hợp với cấu trúc JSON linh hoạt cần được duyệt hoặc chỉnh sửa; streaming phù hợp với xử lý tuần tự, chọn lọc và dữ liệu lớn. Khi hiểu sự khác nhau về mức trừu tượng, biểu diễn và bộ nhớ, ta có thể chọn đúng API của Jackson hoặc kết hợp chúng để vừa giữ code dễ bảo trì vừa đáp ứng yêu cầu xử lý dữ liệu.
