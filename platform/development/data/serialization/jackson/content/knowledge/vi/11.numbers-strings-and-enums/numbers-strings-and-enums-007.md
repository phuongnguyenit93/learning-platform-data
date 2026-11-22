# Phân biệt chuỗi chứa JSON và đối tượng JSON thực sự

Một lỗi dễ gặp khi làm việc với Jackson là nhầm lẫn giữa **văn bản JSON được lưu trong một Java String** và **một giá trị JSON có kiểu object**. Hai dữ liệu có thể trông gần giống nhau khi in ra màn hình, nhưng cấu trúc và kiểu của chúng khác nhau.

Ví dụ, đây là một JSON object:

```json
{
  "id": 42,
  "name": "An"
}
```

Còn đây là một JSON string có nội dung là văn bản JSON:

```json
"{\"id\":42,\"name\":\"An\"}"
```

Trường hợp thứ hai là một chuỗi JSON. Các dấu ngoặc kép và dấu gạch chéo ngược là một phần của cú pháp biểu diễn string trong JSON. Khi Jackson đọc tài liệu thứ hai, nó nhận được một giá trị kiểu String, không tự động biến nội dung của chuỗi thành object.

Hiểu sự khác biệt này giúp thiết kế DTO đúng kiểu, tránh parse hai lần ngoài ý muốn và tránh tạo payload double-encoded khi serialize.

## 1. Hai cấu trúc JSON khác nhau

JSON định nghĩa nhiều kiểu giá trị. Trong đó:

- **Object** là tập hợp các cặp key/value, nằm trong dấu ngoặc nhọn `{ }`.
- **String** là chuỗi ký tự nằm trong dấu ngoặc kép.
- **Array** là danh sách giá trị nằm trong dấu ngoặc vuông `[ ]`.
- Number, boolean và null là các kiểu giá trị riêng.

So sánh hai payload:

**JSON object:**

```json
{
  "payload": {
    "id": 42,
    "name": "An"
  }
}
```

Giá trị của key `payload` là một object có hai thuộc tính `id` và `name`.

**JSON string chứa văn bản JSON:**

```json
{
  "payload": "{\"id\":42,\"name\":\"An\"}"
}
```

Giá trị của key `payload` là một string. Nội dung của string tình cờ trông giống một JSON object, nhưng parser của tài liệu bên ngoài chỉ xem nó là văn bản.

| Đặc điểm | Object lồng nhau | String chứa JSON |
|---|---|---|
| Kiểu JSON của `payload` | Object | String |
| Ký tự bắt đầu sau dấu hai chấm | `{` | `"` |
| Có key/value ở cấp JSON hiện tại? | Có | Không, chỉ có chuỗi ký tự |
| DTO Java phù hợp | Một class con hoặc `JsonNode` | `String` |
| Cần parse lần nữa để truy cập trường bên trong? | Không | Có, nếu muốn diễn giải nội dung chuỗi thành JSON |

## 2. JSON text và Java String không phải cùng một khái niệm

Một biến Java `String` chỉ lưu ký tự. Nó có thể chứa văn bản JSON, văn bản thường, XML, câu lệnh SQL hoặc bất kỳ chuỗi nào khác.

```java
String jsonText = """
    {
      "id": 42,
      "name": "An"
    }
    """;
```

Biến `jsonText` là một Java String. Nội dung của nó là một tài liệu JSON object. Khi truyền nó làm đối số đầu vào cho `readValue`, Jackson phân tích nội dung chuỗi như nguồn JSON.

```java
User user = mapper.readValue(jsonText, User.class);
```

Ở đây, tham số đầu tiên là nguồn JSON text; tham số thứ hai là kiểu Java đích.

Điều này khác với việc JSON document bản thân nó biểu diễn một string:

```java
String jsonStringValue = "\"hello\"";

String value = mapper.readValue(jsonStringValue, String.class);

System.out.println(value);
```

Kết quả là:

```text
hello
```

Tài liệu JSON `"hello"` có kiểu JSON là String, nên Jackson ánh xạ nó thành Java String.

Ngược lại, nếu tài liệu JSON là object nhưng kiểu đích là `String.class`:

```java
String value = mapper.readValue(
    """
    {"id":42,"name":"An"}
    """,
    String.class
);
```

Jackson không hiểu đây là yêu cầu "hãy stringify object". Kiểu token đầu vào là object, trong khi kiểu đích là String; thông thường thao tác sẽ thất bại với lỗi mapping kiểu không phù hợp.

Muốn lấy lại văn bản JSON của object, hãy giữ nguồn JSON text ban đầu hoặc dùng API serialize phù hợp. Không dùng `readValue(..., String.class)` để chuyển một JSON object thành chuỗi.

## 3. Đọc JSON object lồng nhau vào DTO

Khi hợp đồng API xác định `payload` là object, hãy khai báo một kiểu Java tương ứng.

```java
public class User {
    private long id;
    private String name;

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
}

public class ApiResponse {
    private User payload;

    public User getPayload() {
        return payload;
    }

    public void setPayload(User payload) {
        this.payload = payload;
    }
}
```

JSON:

```json
{
  "payload": {
    "id": 42,
    "name": "An"
  }
}
```

Đọc trực tiếp:

```java
ApiResponse response = mapper.readValue(json, ApiResponse.class);

long id = response.getPayload().getId();
String name = response.getPayload().getName();
```

Jackson phân tích object ngoài, nhận ra `payload` là một object JSON và ánh xạ object đó vào kiểu `User`. Không cần gọi `readValue` lần thứ hai.

Đây là cách nên dùng khi API kiểm soát được schema và dữ liệu lồng nhau có cấu trúc ổn định.

## 4. Đọc JSON string có nội dung là một JSON document

Nếu hợp đồng thực sự khai báo `payload` là string, DTO phải phản ánh đúng kiểu đó:

```java
public class StringPayloadResponse {
    private String payload;

    public String getPayload() {
        return payload;
    }

    public void setPayload(String payload) {
        this.payload = payload;
    }
}
```

JSON bên ngoài:

```json
{
  "payload": "{\"id\":42,\"name\":\"An\"}"
}
```

Đọc lớp ngoài trước:

```java
StringPayloadResponse response =
    mapper.readValue(outerJson, StringPayloadResponse.class);

String innerJsonText = response.getPayload();

System.out.println(innerJsonText);
```

Giá trị của `innerJsonText` là văn bản JSON không còn các escape cần thiết cho JSON string bên ngoài:

```json
{"id":42,"name":"An"}
```

Nếu ứng dụng cần diễn giải văn bản đó thành object, phải parse thêm một lần:

```java
User user = mapper.readValue(innerJsonText, User.class);
```

Luồng xử lý:

```text
Outer JSON document
        |
        v
Đọc key "payload"
        |
        v
Java String: "{\"id\":42,\"name\":\"An\"}"
        |
        v
mapper.readValue(innerJsonText, User.class)
        |
        v
Java User object
```

Đây là quá trình parse hai lớp có chủ đích:

1. Parse tài liệu JSON ngoài để lấy string.
2. Parse nội dung string như một tài liệu JSON mới.

Chỉ thực hiện bước thứ hai nếu hợp đồng dữ liệu nói rằng chuỗi đó chứa một JSON document.

## 5. Double encoding khi serialize

Double encoding thường xuất hiện khi một object được serialize thành JSON text, sau đó JSON text đó lại được gán vào một thuộc tính String của object khác.

Ví dụ:

```java
User user = new User();
user.setId(42L);
user.setName("An");

String innerJson = mapper.writeValueAsString(user);

StringPayloadResponse response = new StringPayloadResponse();
response.setPayload(innerJson);

String outerJson = mapper.writeValueAsString(response);
System.out.println(outerJson);
```

Kết quả có dạng:

```json
{
  "payload": "{\"id\":42,\"name\":\"An\"}"
}
```

Đây là JSON hợp lệ. Tuy nhiên, `payload` là string, không phải object. Jackson phải escape dấu ngoặc kép bên trong để giữ nguyên nội dung chuỗi theo cú pháp JSON.

Nếu API muốn gửi object lồng nhau, hãy dùng kiểu Java object:

```java
public class ObjectPayloadResponse {
    private User payload;

    public User getPayload() {
        return payload;
    }

    public void setPayload(User payload) {
        this.payload = payload;
    }
}
```

Serialize:

```java
ObjectPayloadResponse response = new ObjectPayloadResponse();
response.setPayload(user);

String outerJson = mapper.writeValueAsString(response);
```

Kết quả:

```json
{
  "payload": {
    "id": 42,
    "name": "An"
  }
}
```

Hai cách khác nhau ở kiểu của thuộc tính Java:

- `String payload`: Jackson serialize thành JSON string.
- `User payload`: Jackson serialize thành JSON object.

Không nên tự escape hoặc bỏ escape dấu ngoặc kép bằng cách replace chuỗi. Hãy chọn đúng kiểu dữ liệu và để Jackson xử lý cú pháp JSON.

## 6. Dùng JsonNode khi cấu trúc có thể thay đổi

Nếu ứng dụng chưa biết trước kiểu hoặc cấu trúc của `payload`, có thể dùng `JsonNode`.

```java
import com.fasterxml.jackson.databind.JsonNode;

JsonNode root = mapper.readTree(json);
JsonNode payload = root.path("payload");

if (payload.isObject()) {
    long id = payload.path("id").asLong();
    String name = payload.path("name").asText();
} else if (payload.isTextual()) {
    String innerJsonText = payload.textValue();
    JsonNode innerNode = mapper.readTree(innerJsonText);

    long id = innerNode.path("id").asLong();
    String name = innerNode.path("name").asText();
}
```

`isObject()` và `isTextual()` giúp phân biệt object với string ở cấp JSON hiện tại. Với cách này, ứng dụng có thể hỗ trợ dữ liệu đến từ nhiều nguồn có schema khác nhau, nhưng cần xác thực rõ từng nhánh.

Nếu schema được kiểm soát, DTO có kiểu cụ thể thường an toàn và dễ bảo trì hơn. Dùng `JsonNode` khi cần xử lý cấu trúc động hoặc khi phải kiểm tra token trước khi quyết định cách ánh xạ.

## 7. Các API Jackson cần phân biệt

Các API sau có tên gần nhau nhưng nhiệm vụ khác nhau:

| API | Đầu vào | Đầu ra | Công dụng |
|---|---|---|---|
| `readValue(jsonText, Type.class)` | JSON text | Java object | Parse JSON text và bind vào kiểu đích |
| `readTree(jsonText)` | JSON text | `JsonNode` | Parse thành cây JSON |
| `treeToValue(node, Type.class)` | `JsonNode` | Java object | Bind một cây JSON đã có vào kiểu Java |
| `valueToTree(value)` | Java object | `JsonNode` | Chuyển Java value thành cây JSON |
| `convertValue(value, Type.class)` | Java object hoặc tree/value tương thích | Java object | Chuyển đổi dữ liệu qua cơ chế databind |
| `writeValueAsString(value)` | Java object hoặc tree | Java String chứa JSON text | Serialize thành một JSON document dạng văn bản |

### 7.1. readValue dùng để parse văn bản JSON

```java
User user = mapper.readValue(innerJsonText, User.class);
```

Jackson phân tích nội dung của `innerJsonText` như JSON document.

### 7.2. readTree dùng để lấy cây JSON

```java
JsonNode node = mapper.readTree(innerJsonText);
```

Kết quả là một cây có node object, array, text, number, boolean hoặc null. Có thể truy cập key mà chưa cần khai báo DTO.

### 7.3. treeToValue dùng khi đã có JsonNode

```java
JsonNode node = mapper.readTree(innerJsonText);
User user = mapper.treeToValue(node, User.class);
```

Không cần serialize node thành String rồi parse lại. `treeToValue` chuyển trực tiếp cây JSON thành kiểu Java đích.

### 7.4. convertValue không phải cách parse JSON text

Ví dụ:

```java
Map<String, Object> values = Map.of(
    "id", 42,
    "name", "An"
);

User user = mapper.convertValue(values, User.class);
```

`convertValue` hữu ích khi đã có một Java object, map hoặc tree và muốn chuyển nó sang kiểu khác theo quy tắc Jackson databind.

Không nên viết:

```java
String innerJsonText = "{\"id\":42,\"name\":\"An\"}";

// Không dùng convertValue để parse nội dung JSON text.
User user = mapper.convertValue(innerJsonText, User.class);
```

Trong trường hợp này, `innerJsonText` là một Java String. `convertValue` coi nó là một giá trị String cần chuyển đổi, không coi nội dung chuỗi là nguồn JSON cần parse. Dùng `readValue(innerJsonText, User.class)` mới đúng mục đích.

### 7.5. valueToTree chuyển object thành cây

```java
User user = new User();
user.setId(42L);
user.setName("An");

JsonNode node = mapper.valueToTree(user);
```

Kết quả là một `JsonNode` object. Nếu cần chuyển node đó thành kiểu khác, dùng `treeToValue`.

## 8. Khi nào cần parse hai lần?

Parse hai lần chỉ hợp lý khi lớp ngoài thực sự định nghĩa một thuộc tính string có nội dung là JSON text.

Một số trường hợp có thể gặp:

- Hệ thống legacy đóng gói payload JSON thành string.
- Message broker hoặc hệ thống log lưu body dưới dạng một trường văn bản.
- Một API trả về trường `rawPayload` là chuỗi để bảo toàn nội dung gốc.
- Dữ liệu được lưu dưới dạng JSON string trong database rồi được đọc lại.

Ví dụ:

```json
{
  "eventType": "USER_CREATED",
  "rawPayload": "{\"id\":42,\"name\":\"An\"}"
}
```

DTO:

```java
public class EventEnvelope {
    private String eventType;
    private String rawPayload;

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    public String getRawPayload() {
        return rawPayload;
    }

    public void setRawPayload(String rawPayload) {
        this.rawPayload = rawPayload;
    }
}
```

Đọc event và payload:

```java
EventEnvelope event = mapper.readValue(json, EventEnvelope.class);

JsonNode payloadNode = mapper.readTree(event.getRawPayload());
long id = payloadNode.path("id").asLong();
```

Nếu các dịch vụ cùng kiểm soát schema, nên cân nhắc đổi `rawPayload` thành object lồng nhau hoặc dùng một envelope có trường typed. Khi đó bên nhận chỉ cần parse một lần và có thể kiểm tra schema ở cấp JSON.

## 9. Content-Type và ranh giới giữa các hệ thống

Ngoài nội dung JSON, header HTTP cũng góp phần mô tả cách diễn giải dữ liệu.

Một response có:

```http
Content-Type: application/json
```

thường có body là JSON document. Nếu body là:

```json
{"payload":{"id":42}}
```

thì `payload` là object.

Nếu body là:

```json
{"payload":"{\"id\":42}"}
```

thì body vẫn là JSON, nhưng thuộc tính `payload` có kiểu string.

Không nên suy luận rằng một trường là JSON object chỉ vì nội dung chuỗi của nó trông giống JSON. Kiểu thực tế được xác định bởi token trong document và schema/hợp đồng API.

Khi thiết kế API, cần thống nhất:

- Trường payload là object, array hay string.
- Nếu là string, nó chứa văn bản thường hay một JSON document.
- Bên gửi serialize bao nhiêu lần.
- Bên nhận cần parse bao nhiêu lần.
- Phiên bản schema và cách xử lý dữ liệu sai định dạng.

Nếu trường là JSON text được nhúng trong string, tài liệu API nên ghi rõ điều đó. Tên như `rawPayloadJson` hoặc `payloadText` có thể giúp người đọc hiểu mục đích hơn một tên chung chung như `payload`.

## 10. Lỗi thường gặp

### 10.1. Đọc JSON object vào String.class

Nguồn là JSON object nhưng kiểu đích là String:

```java
mapper.readValue("{\"id\":42}", String.class);
```

Thông thường sẽ phát sinh lỗi mapping vì token object không phải JSON string. Nếu cần giữ văn bản JSON, hãy giữ nguyên nguồn text hoặc dùng `writeValueAsString` với một object đã parse.

### 10.2. Đọc JSON string chứa object trực tiếp vào DTO

Nguồn là JSON string:

```json
"{\"id\":42}"
```

Nếu đọc trực tiếp thành `User.class`, Jackson nhận token string ở cấp ngoài, không phải object. Hãy đọc thành `String.class` trước rồi parse nội dung nếu hợp đồng yêu cầu.

### 10.3. Serialize inner JSON text thêm một lần

```java
String inner = mapper.writeValueAsString(user);
String outer = mapper.writeValueAsString(inner);
```

Kết quả là một JSON string chứa JSON text, không phải object JSON lồng nhau. Nếu muốn object, serialize trực tiếp `user` hoặc đặt `user` vào thuộc tính kiểu `User` của envelope.

### 10.4. Dùng convertValue để parse chuỗi

`convertValue` không đọc chuỗi như nguồn JSON. Dùng `readValue` hoặc `readTree` khi đầu vào là JSON text.

### 10.5. Tự replace escape bằng tay

Các ký tự escape như `\\\"`, `\\\\` và `\\n` thuộc cú pháp JSON string. Xóa chúng bằng replace có thể làm thay đổi dữ liệu hoặc tạo JSON không hợp lệ. Để Jackson parse và serialize đúng một lớp dữ liệu tại một thời điểm.

### 10.6. Không xác thực JSON bên trong

Parse thành công lớp ngoài chỉ chứng minh document ngoài hợp lệ. Nếu một trường string được parse tiếp, nội dung bên trong vẫn có thể sai cú pháp, thiếu trường hoặc sai kiểu. Hãy bắt và xử lý lỗi parse ở đúng tầng, đồng thời xác thực schema sau khi parse.

## 11. Xử lý lỗi và bảo vệ dữ liệu

Khi parse JSON text được nhúng trong một string, nên coi nó như một đầu vào độc lập:

```java
try {
    User user = mapper.readValue(innerJsonText, User.class);
    // Kiểm tra các điều kiện nghiệp vụ của user
} catch (JsonProcessingException ex) {
    // Ghi nhận lỗi định dạng với ngữ cảnh phù hợp
}
```

Trong thực tế, có thể cần phân biệt lỗi cú pháp JSON với lỗi ánh xạ kiểu và lỗi validation sau khi tạo object. Không nên nuốt exception rồi trả về object rỗng hoặc null nếu điều đó làm mất dấu dữ liệu sai.

Ngoài ra:

- Giới hạn kích thước của chuỗi JSON lồng nhau để tránh payload quá lớn.
- Kiểm tra độ sâu và cấu trúc dữ liệu theo nhu cầu ứng dụng.
- Không bật polymorphic default typing rộng rãi cho JSON không đáng tin cậy.
- Dùng DTO rõ ràng và xác thực các trường bắt buộc.
- Không ghi log toàn bộ raw payload nếu có dữ liệu nhạy cảm.

Parse hai lần không tự thân là một lỗ hổng, nhưng mỗi lần parse đều là một ranh giới dữ liệu cần được kiểm soát.

## 12. Chọn mô hình dữ liệu phù hợp

| Tình huống | Kiểu Java nên dùng | Cách Jackson xử lý |
|---|---|---|
| Payload là object có schema ổn định | DTO/class cụ thể | `readValue` trực tiếp vào DTO |
| Payload là object nhưng cấu trúc chưa biết | `JsonNode` | `readTree`, sau đó truy cập node |
| Payload thực sự là văn bản JSON | `String` | Đọc lớp ngoài thành String, parse lần nữa nếu cần |
| Payload cần giữ nguyên dạng văn bản | `String` | Không parse nội dung nếu không cần |
| Đã có JsonNode và muốn DTO | DTO/class cụ thể | `treeToValue` |
| Đã có Map/object Java và muốn DTO | DTO/class cụ thể | `convertValue` |
| Cần tạo JSON text từ object | `String` | `writeValueAsString` |

Khi thiết kế DTO, hãy để kiểu field thể hiện đúng cấu trúc JSON. Nếu key đại diện cho object, dùng một object Java hoặc `JsonNode`; nếu key đại diện cho string, dùng `String`. Không nên chọn String chỉ vì muốn "nhận được mọi dữ liệu" rồi parse thủ công ở nhiều nơi.

## 13. Ghi nhớ

- JSON object `{"id":42}` và JSON string `"{\"id\":42}"` là hai kiểu dữ liệu khác nhau.
- Java String chứa JSON text không có nghĩa JSON document bên ngoài cũng chứa một object.
- Dùng DTO lồng nhau khi key JSON là object; dùng String khi hợp đồng thực sự định nghĩa key đó là string.
- Nếu một string chứa JSON text, parse lớp ngoài để lấy String rồi mới gọi `readValue` hoặc `readTree` lần nữa.
- `readValue` parse JSON text; `readTree` tạo JsonNode; `treeToValue` chuyển node sang DTO; `convertValue` chuyển Java value/tree chứ không parse nội dung JSON của String.
- Double encoding tạo JSON hợp lệ nhưng có thể sai schema mong đợi; tránh serialize JSON text vào field String khi cần object lồng nhau.
- Không xóa escape bằng replace thủ công; để Jackson xử lý từng lớp JSON và xác thực dữ liệu sau mỗi lần parse.

