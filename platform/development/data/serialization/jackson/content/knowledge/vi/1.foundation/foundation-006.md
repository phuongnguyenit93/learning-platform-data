# Luồng xử lý từ byte đầu vào đến đối tượng Java và ngược lại

Trong một ứng dụng Java, dữ liệu thường đi qua ranh giới giữa các hệ thống dưới dạng byte: HTTP request, message trong queue, file JSON, dữ liệu đọc từ socket hoặc nội dung lưu trên đĩa. Mã Java của ứng dụng lại làm việc với object, collection, kiểu số, enum và các kiểu miền nghiệp vụ. Jackson đảm nhiệm việc chuyển đổi giữa hai thế giới đó.

Với JSON, chiều đọc thường được gọi là **deserialization**: byte đầu vào được giải mã thành ký tự, phân tích thành cấu trúc JSON, rồi ánh xạ thành object Java. Chiều ghi là **serialization**: Jackson đọc trạng thái object Java, chuyển nó thành cấu trúc JSON, mã hóa thành byte và gửi tới đích. Hiểu rõ từng chặng giúp xác định lỗi nằm ở encoding, cú pháp JSON, cấu hình mapping, constructor, serializer hay nơi ghi dữ liệu.

## 1. Bức tranh tổng thể

Jackson không đơn thuần gọi một hàm để “biến JSON thành object”. Quá trình có nhiều lớp, mỗi lớp giải quyết một vấn đề riêng.

```text
ĐỌC (deserialization)

InputStream / byte[] / Reader / String
        |
        v
Đọc byte và giải mã ký tự (thường là UTF-8)
        |
        v
JsonFactory tạo JsonParser
        |
        v
Parser nhận diện token JSON
        |
        v
ObjectMapper / ObjectReader chọn kiểu Java đích
        |
        v
Deserializer đọc token và tạo object
        |
        v
Object Java dùng trong ứng dụng


GHI (serialization)

Object Java
        |
        v
ObjectMapper / ObjectWriter chọn serializer
        |
        v
Serializer duyệt thuộc tính và giá trị
        |
        v
JsonGenerator phát token JSON
        |
        v
Mã hóa ký tự thành byte (thường là UTF-8)
        |
        v
OutputStream / byte[] / Writer / String
```

Ở mức khái niệm, có thể chia pipeline thành bốn phần:

1. **Nguồn và đích dữ liệu:** nơi byte hoặc ký tự được đọc vào và ghi ra.
2. **Xử lý cú pháp JSON:** nhận diện object, array, field name, string, number, boolean và null.
3. **Ánh xạ kiểu:** quyết định JSON tương ứng với kiểu Java nào, tạo object và gán giá trị.
4. **Cấu hình và mở rộng:** quy tắc đặt tên, ngày giờ, enum, kiểu tùy chỉnh, xử lý giá trị thiếu và các module bổ sung.

Các lớp này có thể được sử dụng riêng. Ví dụ, ứng dụng có thể dùng `JsonParser` để đọc từng token mà không tạo toàn bộ object, hoặc dùng `JsonGenerator` để phát JSON mà không cần tạo cây object trung gian.

## 2. Các thành phần chính của Jackson

Jackson được chia thành các module có vai trò khác nhau. Trong ứng dụng thông thường, dependency `jackson-databind` thường kéo theo `jackson-core` và `jackson-annotations`.

| Thành phần | Vai trò |
|---|---|
| `jackson-core` | Đọc và ghi JSON ở mức token thông qua `JsonParser`, `JsonGenerator`, `JsonFactory`. |
| `jackson-annotations` | Cung cấp annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonCreator`, `@JsonFormat`. |
| `jackson-databind` | Ánh xạ giữa JSON và Java object; cung cấp `ObjectMapper`, `ObjectReader`, `ObjectWriter`, tree model. |
| Các module mở rộng | Hỗ trợ kiểu dữ liệu hoặc nền tảng cụ thể, ví dụ Java Time, parameter names, Kotlin. |

### 2.1. `JsonFactory`

`JsonFactory` là điểm tạo parser và generator. Nó thuộc lớp xử lý JSON cấp thấp và thường được quản lý bên trong `ObjectMapper`. Khi cần streaming trực tiếp, có thể dùng factory để tạo parser từ `InputStream` hoặc generator cho `OutputStream`.

### 2.2. `JsonParser` và `JsonGenerator`

`JsonParser` đọc nội dung JSON tuần tự và cung cấp các token. Ví dụ, với JSON:

```json
{
  "id": 42,
  "name": "An",
  "active": true
}
```

Parser lần lượt nhận được các token tương tự `START_OBJECT`, `FIELD_NAME`, `VALUE_NUMBER_INT`, `FIELD_NAME`, `VALUE_STRING`, `FIELD_NAME`, `VALUE_TRUE` và `END_OBJECT`.

`JsonGenerator` làm chiều ngược lại: chương trình yêu cầu ghi bắt đầu object, tên field, giá trị và kết thúc object. Generator đảm bảo dấu ngoặc, dấu phẩy, dấu nháy và escaping được phát đúng cú pháp.

### 2.3. `ObjectMapper`

`ObjectMapper` là facade cấp cao được dùng phổ biến nhất. Nó phối hợp parser/generator với cơ chế databinding để đọc hoặc ghi object.

```java
ObjectMapper mapper = new ObjectMapper();

User user = mapper.readValue(json, User.class);
String output = mapper.writeValueAsString(user);
```

Khi gọi `readValue`, mapper xác định kiểu đích, tìm deserializer phù hợp và yêu cầu deserializer đọc dữ liệu từ parser. Khi gọi `writeValueAsString`, mapper xác định serializer cho kiểu object, rồi serializer ghi dữ liệu thông qua generator.

Trong ứng dụng thực tế, nên cấu hình mapper một lần khi khởi tạo ứng dụng và tái sử dụng. Sau khi đã bắt đầu sử dụng, tránh thay đổi cấu hình mapper dùng chung trong lúc nhiều luồng đang xử lý. Nếu cần quy tắc đọc khác nhau cho từng điểm gọi, tạo `ObjectReader`; nếu cần quy tắc ghi khác nhau, tạo `ObjectWriter`.

## 3. Chiều đọc: từ byte đầu vào đến object Java

Giả sử dịch vụ nhận JSON đại diện cho người dùng:

```json
{
  "id": 42,
  "name": "An",
  "active": true
}
```

Kiểu Java đích:

```java
public class User {
    private long id;
    private String name;
    private boolean active;

    public User() {
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

Đọc dữ liệu:

```java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(Path.of("user.json"))) {
    User user = mapper.readValue(input, User.class);
    System.out.println(user.getName());
}
```

### 3.1. Nhận nguồn dữ liệu

Jackson có thể nhận dữ liệu từ nhiều dạng đầu vào:

```java
User fromString = mapper.readValue(jsonString, User.class);
User fromBytes = mapper.readValue(jsonBytes, User.class);
User fromStream = mapper.readValue(inputStream, User.class);
User fromReader = mapper.readValue(reader, User.class);
User fromFile = mapper.readValue(jsonFile, User.class);
```

Khi đầu vào là `InputStream` hoặc `byte[]`, Jackson phải xác định cách giải mã byte thành ký tự. JSON trao đổi giữa các hệ thống hiện nay nên được mã hóa UTF-8. Nếu tầng gọi đã có `Reader`, dữ liệu đã ở dạng ký tự và việc giải mã byte đã do tầng đó thực hiện.

Không nên tùy tiện chuyển byte sang `String` bằng charset mặc định của máy:

```java
// Tránh phụ thuộc charset mặc định của hệ điều hành
String json = new String(bytes);

// Chỉ rõ charset khi tự giải mã byte
String jsonUtf8 = new String(bytes, StandardCharsets.UTF_8);
```

Trong nhiều trường hợp, truyền trực tiếp `InputStream` hoặc `byte[]` cho Jackson giúp tránh một lần tạo chuỗi trung gian. Nếu tự chuyển đổi, phải thống nhất charset với bên gửi.

### 3.2. Phân tích cú pháp thành token

Sau khi có nguồn dữ liệu, `JsonFactory` tạo `JsonParser`. Parser đọc cấu trúc JSON và xác định token. Ở giai đoạn này, Jackson kiểm tra cú pháp như dấu ngoặc, dấu phẩy, dấu hai chấm, chuỗi được đóng đúng và các literal hợp lệ.

Ví dụ JSON sai cú pháp:

```json
{
  "id": 42,
  "name": "An",
}
```

Dấu phẩy sau field cuối làm tài liệu không hợp lệ theo cú pháp JSON chuẩn. Lỗi này xảy ra ở tầng parsing; Jackson chưa thể hoàn tất việc tạo `User`.

### 3.3. Chọn kiểu Java đích

Lời gọi `readValue(input, User.class)` cung cấp kiểu đích rõ ràng. Với collection hoặc kiểu generic, cần giữ thông tin kiểu bằng `TypeReference` hoặc `JavaType` vì generic type bị xóa ở runtime.

```java
List<User> users = mapper.readValue(
    jsonArray,
    new TypeReference<List<User>>() {}
);

Map<String, User> usersByName = mapper.readValue(
    jsonObject,
    new TypeReference<Map<String, User>>() {}
);
```

Nếu chỉ truyền `List.class`, Jackson biết đích là một `List` nhưng không biết phần tử cần là `User`; kết quả thường là các map hoặc kiểu giá trị tổng quát thay vì `User`.

### 3.4. Tạo object và gán thuộc tính

Databinding tìm cách tạo instance của kiểu đích rồi đọc từng field JSON để gán vào thuộc tính tương ứng. Cách tạo instance phụ thuộc vào cấu trúc lớp và metadata Jackson nhận diện được, chẳng hạn:

- Constructor không tham số kết hợp setter hoặc field có thể truy cập.
- Constructor hoặc factory method được đánh dấu bằng `@JsonCreator`.
- Tham số constructor được liên kết với tên thuộc tính bằng annotation hoặc metadata phù hợp.
- Cơ chế hỗ trợ record và các kiểu Java hiện đại trong phiên bản Jackson tương ứng.

Ví dụ dùng constructor tường minh:

```java
public class User {
    private final long id;
    private final String name;

    @JsonCreator
    public User(
        @JsonProperty("id") long id,
        @JsonProperty("name") String name
    ) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

`@JsonProperty` xác định tên thuộc tính JSON tương ứng với tham số constructor. Cách này phù hợp với object bất biến vì các trường được thiết lập ngay khi tạo instance.

### 3.5. Chuyển đổi giá trị theo kiểu

Jackson chuyển token JSON thành kiểu Java phù hợp: số thành kiểu số, string thành `String`, `true`/`false` thành boolean, array thành collection hoặc array Java, object thành object hoặc map. Với enum, ngày giờ và kiểu miền nghiệp vụ, Jackson có thể cần cấu hình hoặc module bổ sung.

Ví dụ ánh xạ tên JSON khác tên thuộc tính Java:

```java
public class User {
    @JsonProperty("user_id")
    private long id;

    @JsonProperty("display_name")
    private String name;
}
```

Jackson sẽ tìm `user_id` và `display_name` trong JSON để gán cho các thuộc tính tương ứng.

## 4. Chiều ghi: từ object Java thành byte đầu ra

Với cùng object `User`, có thể tạo JSON bằng:

```java
String json = mapper.writeValueAsString(user);
byte[] bytes = mapper.writeValueAsBytes(user);

try (OutputStream output = Files.newOutputStream(Path.of("user.json"))) {
    mapper.writeValue(output, user);
}
```

Quá trình ghi diễn ra theo các bước sau.

### 4.1. Xác định serializer

`ObjectMapper` xem kiểu runtime của object và tìm serializer phù hợp. Serializer có thể là serializer mặc định cho kiểu Java, serializer do module đăng ký hoặc serializer tùy chỉnh của ứng dụng.

### 4.2. Phát hiện thuộc tính cần ghi

Jackson xác định các thuộc tính có thể serialize dựa trên getter, field, annotation và cấu hình visibility. Các annotation có thể điều chỉnh hành vi:

```java
public class User {
    private long id;

    @JsonProperty("display_name")
    private String name;

    @JsonIgnore
    private String internalToken;
}
```

Ở ví dụ này, thuộc tính `name` được ghi dưới tên `display_name`, còn `internalToken` bị bỏ qua trong quá trình databinding theo cấu hình annotation mặc định.

### 4.3. Ghi token JSON

Serializer không cần tự ghép chuỗi JSON. Nó yêu cầu `JsonGenerator` phát các token tương ứng: bắt đầu object, tên field, giá trị và kết thúc object. Generator chịu trách nhiệm cú pháp và escaping ký tự đặc biệt.

Ví dụ chuỗi chứa dấu nháy kép:

```java
user.setName("An \"A\"");
String json = mapper.writeValueAsString(user);
```

Jackson sẽ escape dấu nháy để chuỗi đầu ra vẫn là JSON hợp lệ. Không nên tự nối chuỗi bằng toán tử `+` để tạo JSON vì dễ sai escaping, kiểu dữ liệu và dấu phân cách.

### 4.4. Mã hóa và ghi dữ liệu

Khi ghi ra `OutputStream` hoặc lấy `byte[]`, Jackson phát byte theo encoding JSON phù hợp, thông thường là UTF-8. Khi ghi ra `Writer`, tầng writer đã quyết định cách mã hóa ký tự thành byte nếu writer được nối với một stream.

Phân biệt hai trường hợp:

- `writeValueAsString`: kết quả là chuỗi Java, chưa phải byte trên mạng hoặc đĩa.
- `writeValue(OutputStream, value)` hoặc `writeValueAsBytes`: kết quả đi qua dạng byte, phù hợp khi gửi hoặc lưu dữ liệu nhị phân.

Nếu giao thức yêu cầu UTF-8, hãy đảm bảo header và cách ghi byte của ứng dụng cũng thống nhất UTF-8.

## 5. Ba cách làm việc với dữ liệu JSON

Jackson hỗ trợ ba cách tiếp cận thường gặp. Chọn cách phù hợp với kích thước dữ liệu, cấu trúc và nhu cầu xử lý.

| Cách tiếp cận | API tiêu biểu | Đặc điểm | Khi phù hợp |
|---|---|---|---|
| Databinding | `ObjectMapper`, `ObjectReader`, `ObjectWriter` | Chuyển trực tiếp giữa JSON và kiểu Java đã biết. | API request/response, cấu hình, message có schema rõ. |
| Tree model | `JsonNode`, `ObjectNode`, `ArrayNode` | Đọc thành cây JSON có thể duyệt và chỉnh sửa trước khi chuyển kiểu. | Cấu trúc linh hoạt, field tùy chọn, cần kiểm tra hoặc biến đổi JSON. |
| Streaming | `JsonParser`, `JsonGenerator` | Xử lý từng token, không cần giữ toàn bộ tài liệu trong bộ nhớ. | File lớn, luồng liên tục, xử lý từng bản ghi hoặc cần kiểm soát chi tiết. |

### 5.1. Databinding

Đây là cách ngắn gọn nhất khi biết kiểu dữ liệu:

```java
Order order = mapper.readValue(json, Order.class);
String output = mapper.writeValueAsString(order);
```

Ưu điểm là code dễ đọc, kiểu dữ liệu rõ và thuận tiện tích hợp với các lớp nghiệp vụ. Nhược điểm là cấu trúc JSON cần tương thích với kiểu Java và việc tạo toàn bộ object có thể tiêu thụ bộ nhớ đáng kể với tài liệu lớn.

### 5.2. Tree model

Tree model biểu diễn JSON thành các node. Có thể đọc một phần tử mà chưa cần định nghĩa lớp Java tương ứng:

```java
JsonNode root = mapper.readTree(json);

long id = root.path("id").asLong();
String name = root.path("name").asText();

JsonNode address = root.path("address");
if (!address.isMissingNode() && !address.isNull()) {
    String city = address.path("city").asText();
}
```

`get("field")` có thể trả về `null` khi field không tồn tại. `path("field")` trả về `MissingNode`, thuận tiện khi duyệt chuỗi node mà không phải kiểm tra null ở mỗi bước. Cần phân biệt field bị thiếu với field hiện diện nhưng có giá trị JSON `null` nếu nghiệp vụ quan tâm đến khác biệt này.

Có thể sửa cây JSON:

```java
ObjectNode object = (ObjectNode) mapper.readTree(json);
object.put("source", "imported");
object.remove("internalToken");

String transformed = mapper.writeValueAsString(object);
```

Tree model linh hoạt hơn databinding nhưng vẫn giữ toàn bộ cây trong bộ nhớ. Với tài liệu rất lớn, streaming thường phù hợp hơn.

### 5.3. Streaming

Streaming đọc và xử lý token tuần tự. Ví dụ đọc một mảng lớn gồm nhiều object và chỉ xử lý từng object một:

```java
JsonFactory factory = new JsonFactory();

try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected a JSON array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        User user = mapper.readValue(parser, User.class);
        process(user);
    }
}
```

Ví dụ trên minh họa cách tiếp cận: parser tiến qua từng phần tử của array và databinding tạo một `User` tại một thời điểm. Khi triển khai thực tế, cần xác định rõ cách xử lý token kết thúc, token sai định dạng và dữ liệu còn lại sau array.

Streaming giúp giới hạn bộ nhớ vì ứng dụng không cần giữ cả tài liệu hoặc danh sách object. Đổi lại, code phải quản lý trạng thái parser và cấu trúc token cẩn thận hơn.

## 6. Cấu hình mapping thường gặp

Không phải JSON nào cũng khớp hoàn toàn với tên thuộc tính và kiểu Java. Jackson cung cấp annotation, module và feature để mô tả quy tắc chuyển đổi.

### 6.1. Tên thuộc tính và thuộc tính bị bỏ qua

```java
public class Customer {
    @JsonProperty("customer_id")
    private long id;

    @JsonAlias({"full_name", "customer_name"})
    private String name;

    @JsonIgnore
    private String passwordHash;
}
```

- `@JsonProperty` đặt tên JSON chính thức cho thuộc tính.
- `@JsonAlias` khai báo các tên thay thế có thể nhận khi deserialize; khi serialize, tên chính thức vẫn được sử dụng.
- `@JsonIgnore` loại thuộc tính khỏi quá trình mapping theo hành vi annotation.

### 6.2. Giá trị không có trong JSON và giá trị null

Hai tình huống sau khác nhau:

```json
{}
```

```json
{"name": null}
```

Trong trường hợp đầu, field không xuất hiện. Trong trường hợp thứ hai, field xuất hiện với giá trị null. Với thuộc tính object, giá trị sau khi deserialize có thể là `null` trong cả hai trường hợp nếu không có cấu hình hoặc cơ chế theo dõi sự hiện diện riêng. Với kiểu primitive như `int` hoặc `boolean`, Java không thể chứa null nên giá trị mặc định hoặc cấu hình xử lý null có thể ảnh hưởng kết quả.

Nếu cần phân biệt “không gửi field” với “yêu cầu xóa giá trị”, DTO cần thể hiện được trạng thái hiện diện, ví dụ dùng wrapper, setter tùy chỉnh, tree model hoặc kiểu dữ liệu biểu diễn patch phù hợp. Không nên giả định rằng một thuộc tính Java đơn giản luôn giữ được sự khác biệt đó.

### 6.3. Field không được biết trước

Khi JSON chứa field không có trong lớp Java, Jackson mặc định thường có thể báo lỗi `UnrecognizedPropertyException`, tùy cấu hình. Có thể bỏ qua field lạ khi hợp đồng API cho phép:

```java
ObjectMapper mapper = new ObjectMapper()
    .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
```

Quyết định này có tác động đến khả năng phát hiện sai tên field. Nếu tắt kiểm tra toàn cục, lỗi chính tả trong JSON có thể bị bỏ qua âm thầm. Với API nội bộ có schema chặt, giữ kiểm tra thường giúp phát hiện lỗi sớm; với tích hợp cần tương thích tiến về phía trước, bỏ qua field mới có thể hữu ích.

### 6.4. Ngày giờ và Java Time

Các kiểu trong `java.time` thường được hỗ trợ thông qua module `jackson-datatype-jsr310`:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule());
```

Có thể cấu hình biểu diễn ngày giờ dạng chuỗi ISO thay vì timestamp dạng số:

```java
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Hình thức JSON cụ thể cần thống nhất với hợp đồng API. Với thời điểm tuyệt đối, nên xác định rõ múi giờ hoặc dùng kiểu như `Instant`/`OffsetDateTime` phù hợp với ngữ nghĩa dữ liệu. Không nên dựa vào múi giờ mặc định của máy chủ.

### 6.5. Enum

Mặc định, enum thường được serialize theo tên hằng, ví dụ `"PENDING"`. Nếu API cần biểu diễn khác, có thể dùng `@JsonValue`, `@JsonCreator` hoặc serializer/deserializer tùy chỉnh. Hãy quyết định rõ cách xử lý giá trị enum mới mà phiên bản ứng dụng chưa biết.

## 7. Serializer và deserializer tùy chỉnh

Khi quy tắc mapping vượt quá khả năng annotation hoặc cấu hình chung, có thể viết serializer/deserializer riêng.

Ví dụ một kiểu tiền có biểu diễn JSON là chuỗi số thập phân:

```java
public class MoneySerializer extends JsonSerializer<BigDecimal> {
    @Override
    public void serialize(
        BigDecimal value,
        JsonGenerator generator,
        SerializerProvider serializers
    ) throws IOException {
        generator.writeString(value.toPlainString());
    }
}
```

Deserializer tương ứng:

```java
public class MoneyDeserializer extends JsonDeserializer<BigDecimal> {
    @Override
    public BigDecimal deserialize(
        JsonParser parser,
        DeserializationContext context
    ) throws IOException {
        String value = parser.getValueAsString();
        try {
            return new BigDecimal(value);
        } catch (NumberFormatException ex) {
            return (BigDecimal) context.handleWeirdStringValue(
                BigDecimal.class,
                value,
                "Expected a decimal amount"
            );
        }
    }
}
```

Đăng ký trực tiếp trên thuộc tính:

```java
public class Invoice {
    @JsonSerialize(using = MoneySerializer.class)
    @JsonDeserialize(using = MoneyDeserializer.class)
    private BigDecimal total;
}
```

Hoặc đăng ký qua `SimpleModule` khi quy tắc áp dụng cho kiểu dữ liệu ở nhiều nơi:

```java
SimpleModule module = new SimpleModule();
module.addSerializer(BigDecimal.class, new MoneySerializer());
module.addDeserializer(BigDecimal.class, new MoneyDeserializer());

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Ví dụ này minh họa cơ chế mở rộng. Trong ứng dụng tài chính, cần đặc tả rõ scale, rounding mode, dấu âm, giới hạn độ lớn và việc JSON dùng number hay string. Không nên để một serializer toàn cục vô tình thay đổi cách biểu diễn `BigDecimal` ở những API có hợp đồng khác nhau.

## 8. Kiểu generic, collection và object lồng nhau

JSON thường có object lồng nhau và array. Jackson có thể ánh xạ chúng sang model Java tương ứng:

```java
public class Order {
    private String orderId;
    private Customer customer;
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private int quantity;
}
```

Với kiểu generic lồng nhau, dùng `TypeReference`:

```java
List<Map<String, List<OrderLine>>> result = mapper.readValue(
    json,
    new TypeReference<List<Map<String, List<OrderLine>>>>() {}
);
```

`TypeReference` giữ thông tin generic thông qua kiểu anonymous subclass. Một cách khác là tạo `JavaType` bằng `TypeFactory`, hữu ích khi kiểu cần xây dựng động trong runtime.

## 9. Lỗi thường gặp và cách xác định tầng gây lỗi

Một lỗi đọc JSON có thể xuất phát từ nhiều tầng. Hãy xem loại exception, vị trí byte/line/column và kiểu đích để khoanh vùng.

| Dấu hiệu | Tầng có khả năng liên quan | Hướng kiểm tra |
|---|---|---|
| `JsonParseException` | Cú pháp hoặc encoding đầu vào | Kiểm tra byte gốc, charset, dấu ngoặc, dấu phẩy, chuỗi và vị trí lỗi. |
| `UnrecognizedPropertyException` | Databinding | Field JSON không có trong kiểu Java; kiểm tra tên field và chính sách field lạ. |
| `MismatchedInputException` | Chuyển đổi kiểu | Giá trị JSON không phù hợp kiểu đích, ví dụ object thay cho number. |
| `InvalidDefinitionException` | Định nghĩa kiểu Java/cấu hình | Jackson không biết cách tạo hoặc serialize kiểu; kiểm tra constructor, creator, getter, module. |
| `JsonMappingException` | Mapping nói chung | Đọc path tham chiếu đến thuộc tính lồng nhau để tìm vị trí mapping thất bại. |
| Lỗi ký tự bị hỏng | Charset ở đầu vào/đầu ra | Xác nhận encoding của bên gửi, header và cách chuyển byte thành string. |

Ví dụ bắt lỗi ở biên xử lý:

```java
try {
    User user = mapper.readValue(inputStream, User.class);
    handle(user);
} catch (JsonProcessingException ex) {
    // Ghi log loại lỗi và thông tin vị trí phù hợp.
    // Không ghi toàn bộ payload nếu payload có dữ liệu nhạy cảm.
    throw new InvalidRequestException("Invalid JSON payload", ex);
} catch (IOException ex) {
    throw new RequestReadException("Unable to read request body", ex);
}
```

`JsonProcessingException` là nhóm lỗi xử lý nội dung JSON; `IOException` còn có thể phản ánh lỗi đọc stream hoặc lỗi I/O. Cách phân loại exception cụ thể phụ thuộc phiên bản Jackson và chữ ký API đang dùng.

## 10. Hiệu năng và quản lý tài nguyên

Một vài lựa chọn thiết kế ảnh hưởng trực tiếp đến chi phí xử lý:

- **Tái sử dụng mapper:** tạo và cấu hình `ObjectMapper` khi khởi tạo ứng dụng, sau đó dùng chung khi cấu hình đã ổn định.
- **Dùng reader/writer theo tác vụ:** `ObjectReader` và `ObjectWriter` là lựa chọn phù hợp để áp dụng cấu hình theo lần đọc/ghi mà không phải thay đổi mapper dùng chung.
- **Tránh chuỗi trung gian khi không cần:** truyền stream trực tiếp hoặc dùng API byte khi đích cuối cùng là I/O dạng byte.
- **Chọn streaming cho tài liệu lớn:** databinding và tree model thường cần giữ object hoặc cây trong bộ nhớ; streaming xử lý token tuần tự.
- **Đóng tài nguyên đúng nơi sở hữu:** đóng stream do ứng dụng mở bằng try-with-resources. Với stream được framework truyền vào, tuân theo hợp đồng sở hữu tài nguyên của framework; không tự đóng nếu framework còn cần sử dụng.
- **Đo trước khi tối ưu:** kích thước payload, số object, độ sâu lồng nhau và chi phí custom serializer đều có thể ảnh hưởng hiệu năng.

Không nên bật các feature permissive hoặc tối ưu cấu hình một cách tùy tiện. Mỗi lựa chọn cần dựa trên hợp đồng dữ liệu và cách ứng dụng tiêu thụ kết quả.

## 11. An toàn khi deserialize dữ liệu không đáng tin cậy

JSON từ client, đối tác hoặc message broker cần được xem là dữ liệu đầu vào không đáng tin cậy. Một số nguyên tắc quan trọng:

1. **Giới hạn kích thước payload và độ sâu lồng nhau.** Tài liệu quá lớn hoặc lồng quá sâu có thể tiêu tốn nhiều bộ nhớ và CPU. Dùng giới hạn ở tầng HTTP/message broker và các giới hạn parser phù hợp với phiên bản Jackson.
2. **Không bật polymorphic default typing một cách tùy tiện.** Việc cho phép dữ liệu đầu vào quyết định kiểu Java cần được thiết kế với allowlist và `PolymorphicTypeValidator` phù hợp. Tránh deserialize kiểu tùy ý từ nguồn không tin cậy.
3. **Dùng DTO đầu vào có phạm vi rõ.** Không nhất thiết deserialize request trực tiếp vào entity nội bộ có nhiều thuộc tính nhạy cảm hoặc quyền thay đổi rộng.
4. **Kiểm tra dữ liệu sau mapping.** Jackson xác nhận cú pháp và chuyển kiểu; nó không thay thế validation nghiệp vụ như giới hạn số lượng, quyền sở hữu, trạng thái hợp lệ hoặc quy tắc tiền tệ.
5. **Không log payload nhạy cảm.** Token, mật khẩu, thông tin cá nhân và dữ liệu thanh toán có thể xuất hiện trong JSON. Log exception và metadata cần thiết, đồng thời che hoặc loại bỏ nội dung nhạy cảm.

## 12. Ví dụ hoàn chỉnh hai chiều

Ví dụ sau ghép các bước thường gặp: cấu hình mapper, deserialize JSON thành object, thay đổi dữ liệu và serialize trở lại.

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

public class JacksonRoundTrip {
    public static class User {
        private long id;

        @JsonProperty("display_name")
        private String name;

        private boolean active;

        public User() {
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

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper()
            .enable(SerializationFeature.INDENT_OUTPUT);

        String incomingJson = """
            {
              "id": 42,
              "display_name": "An",
              "active": true
            }
            """;

        // JSON text -> parser -> deserializer -> User
        User user = mapper.readValue(incomingJson, User.class);

        // Xử lý object trong logic ứng dụng
        user.setName(user.getName() + " Nguyen");

        // User -> serializer -> generator -> JSON text
        String outgoingJson = mapper.writeValueAsString(user);

        System.out.println(outgoingJson);
    }
}
```

Đầu ra có dạng:

```json
{
  "id" : 42,
  "active" : true,
  "display_name" : "An Nguyen"
}
```

Thứ tự thuộc tính và khoảng trắng có thể khác tùy cấu hình và phiên bản. Về mặt dữ liệu, JSON đầu ra giữ các giá trị đã ánh xạ, còn tên field `name` được xuất thành `display_name` nhờ annotation.

## 13. Cách chọn API theo tình huống

| Tình huống | Lựa chọn khởi đầu |
|---|---|
| Đọc request JSON thành DTO đã biết | `ObjectMapper.readValue` hoặc `ObjectReader` |
| Ghi DTO thành JSON response | `ObjectMapper.writeValue` hoặc `ObjectWriter` |
| Đọc danh sách có generic type | `TypeReference<List<T>>` hoặc `JavaType` |
| Kiểm tra field động, chưa có model cố định | `readTree` và `JsonNode` |
| Chỉnh sửa một vài field trong JSON | Tree model với `ObjectNode`/`ArrayNode` |
| Xử lý file rất lớn theo từng phần tử | `JsonParser` streaming kết hợp databinding từng phần |
| Ghi JSON lớn theo từng bản ghi | `JsonGenerator` streaming |
| Kiểu dữ liệu có quy tắc riêng | Annotation, module hoặc serializer/deserializer tùy chỉnh |

Khi thiết kế một luồng tích hợp, hãy xác định trước hợp đồng JSON: encoding, tên field, kiểu dữ liệu, quy tắc null, field lạ, định dạng ngày giờ và chính sách tương thích phiên bản. Sau đó mới chọn model Java và cấu hình Jackson. Làm rõ hợp đồng từ đầu giúp tránh việc sửa lỗi mapping bằng các cấu hình quá rộng, che mất dữ liệu sai hoặc tạo ra JSON đầu ra không nhất quán.

## 14. Những điểm cần ghi nhớ

- Byte đầu vào phải được giải mã đúng charset trước khi parser có thể hiểu nội dung JSON.
- Parser xử lý cú pháp JSON và tạo token; databinding chuyển token thành kiểu Java.
- `ObjectMapper` điều phối quá trình đọc/ghi; serializer và deserializer thực hiện mapping cho từng kiểu.
- Khi ghi, generator tạo cú pháp JSON và tầng output mã hóa ký tự thành byte.
- Databinding thuận tiện với model đã biết, tree model linh hoạt với cấu trúc động, streaming phù hợp với dữ liệu lớn.
- Generic type cần được giữ bằng `TypeReference` hoặc `JavaType`.
- Annotation, module và custom serializer/deserializer cho phép điều chỉnh quy tắc mapping.
- Deserialize thành công không đồng nghĩa dữ liệu đã hợp lệ về nghiệp vụ; ứng dụng vẫn phải validation và áp dụng giới hạn an toàn.
