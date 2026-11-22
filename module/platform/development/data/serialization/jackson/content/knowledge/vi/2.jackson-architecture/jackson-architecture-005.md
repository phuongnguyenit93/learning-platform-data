# Vai trò của `JsonNode` trong mô hình cây của Jackson

## 1. Mô hình cây trong Jackson là gì?

JSON có cấu trúc phân cấp: một đối tượng có thể chứa các thuộc tính, mỗi thuộc tính có thể là giá trị đơn, một đối tượng khác hoặc một mảng. Jackson cung cấp **Tree Model** để biểu diễn cấu trúc đó thành một cây đối tượng Java ở trong bộ nhớ.

Trong Tree Model, mỗi phần tử của cây được biểu diễn bằng một đối tượng thuộc kiểu `JsonNode` hoặc một lớp con của nó. Vì vậy, `JsonNode` là kiểu nền tảng để đọc, duyệt, kiểm tra và thao tác với dữ liệu JSON khi chương trình chưa biết trước toàn bộ cấu trúc dữ liệu hoặc không muốn ánh xạ ngay sang một lớp Java cụ thể.

Ví dụ, JSON sau có một đối tượng gốc, một đối tượng lồng nhau và một mảng:

```json
{
  "id": 101,
  "name": "Lan",
  "active": true,
  "profile": {
    "city": "Da Nang"
  },
  "roles": ["admin", "editor"],
  "nickname": null
}
```

Có thể hình dung cây tương ứng như sau:

```text
JsonNode (đối tượng gốc)
├── "id"        -> nút số: 101
├── "name"      -> nút chuỗi: "Lan"
├── "active"    -> nút boolean: true
├── "profile"   -> ObjectNode
│   └── "city"  -> nút chuỗi: "Da Nang"
├── "roles"     -> ArrayNode
│   ├── phần tử 0 -> nút chuỗi: "admin"
│   └── phần tử 1 -> nút chuỗi: "editor"
└── "nickname"  -> NullNode
```

Các nhánh thể hiện quan hệ chứa nhau; các nút lá giữ những giá trị như chuỗi, số, boolean hoặc `null`. Một mảng cũng là một nút trong cây và các phần tử của nó là những nút con.

## 2. `JsonNode` nằm ở đâu trong kiến trúc Jackson?

Jackson thường được sử dụng qua các thành phần thuộc hai lớp chức năng chính:

- **Jackson Core** cung cấp API xử lý JSON ở mức luồng. `JsonFactory` tạo `JsonParser` để đọc token JSON và `JsonGenerator` để ghi token JSON.
- **Jackson Databind** cung cấp `ObjectMapper`, cơ chế ánh xạ dữ liệu và Tree Model. `JsonNode` thuộc Tree Model của module `jackson-databind`.

Khi gọi `ObjectMapper.readTree(...)`, Jackson đọc nội dung JSON và dựng các node tương ứng. Khi ghi một cây bằng `ObjectMapper.writeValue(...)` hoặc `writeValueAsString(...)`, Jackson duyệt cây và phát sinh nội dung JSON.

```text
Văn bản JSON
    |
    v
JsonFactory / JsonParser          (Jackson Core)
    |
    v
ObjectMapper                      (Jackson Databind)
    |
    v
JsonNode gốc
    |
    +-- ObjectNode
    +-- ArrayNode
    +-- các nút giá trị

JsonNode tree -- ObjectMapper / JsonGenerator --> Văn bản JSON
```

`ObjectMapper` là điểm vào thuận tiện cho ứng dụng. `JsonNode` là kiểu dữ liệu mà ứng dụng nhận được khi chọn cách đọc JSON thành cây. Hai thành phần có vai trò khác nhau: `ObjectMapper` điều phối việc chuyển đổi, còn các node lưu cấu trúc và giá trị đã được chuyển đổi.

## 3. `JsonNode` là kiểu trừu tượng chung của các nút

`JsonNode` là lớp trừu tượng làm giao diện thống nhất cho các loại phần tử JSON. Nhờ đó, một biến có kiểu `JsonNode` có thể tham chiếu đến nút gốc, nút đối tượng, nút mảng hoặc nút giá trị. Chương trình có thể duyệt cây mà không cần biết trước lớp cụ thể của mọi nút.

Những lớp thường gặp gồm:

| Lớp hoặc nhóm nút | Biểu diễn | Ví dụ JSON |
|---|---|---|
| `ObjectNode` | Một đối tượng gồm các cặp tên thuộc tính và giá trị | `{"name":"Lan"}` |
| `ArrayNode` | Một mảng có thứ tự các phần tử | `["admin","editor"]` |
| `TextNode` | Một giá trị chuỗi | `"Lan"` |
| Các lớp số như `IntNode`, `LongNode`, `DecimalNode` | Giá trị số với kiểu biểu diễn phù hợp | `101`, `12.5` |
| `BooleanNode` | Giá trị đúng hoặc sai | `true` |
| `NullNode` | Giá trị JSON `null` | `null` |

`ObjectNode` và `ArrayNode` là các nút chứa, có thể có nút con. Những nút như `TextNode`, `BooleanNode`, `NullNode` và các nút số là nút giá trị. Cách phân loại này giúp chương trình biết một nút có thể tiếp tục được duyệt như một cấu trúc hay chỉ chứa một giá trị.

Jackson còn có `MissingNode`, một nút đặc biệt dùng để biểu diễn trường hợp đường dẫn được truy cập không tồn tại. `MissingNode` không tương đương với `NullNode`: `NullNode` biểu diễn một giá trị `null` có mặt trong JSON, còn `MissingNode` biểu diễn việc không tìm thấy nút tại đường dẫn yêu cầu.

## 4. Đọc JSON thành cây và nhận `JsonNode` gốc

Để dùng Tree Model, dự án cần có module `jackson-databind` trên classpath. Sau đó, tạo `ObjectMapper` và gọi `readTree`:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ReadJsonTree {
    public static void main(String[] args) throws Exception {
        String json = "{\"id\":101,\"name\":\"Lan\","
                + "\"profile\":{\"city\":\"Da Nang\"},"
                + "\"roles\":[\"admin\",\"editor\"]}";

        ObjectMapper mapper = new ObjectMapper();
        JsonNode root = mapper.readTree(json);

        System.out.println(root.isObject());
        System.out.println(root.path("name").asText());
        System.out.println(root.path("profile").path("city").asText());
    }
}
```

`readTree` trả về `JsonNode` vì kiểu của nút gốc phụ thuộc vào JSON đầu vào. Nếu đầu vào là một đối tượng, nút gốc thực tế là `ObjectNode`; nếu đầu vào là một mảng, nút gốc là `ArrayNode`. Khai báo biến theo kiểu `JsonNode` giúp mã xử lý được cả hai trường hợp và kiểm tra kiểu nút trước khi thao tác cụ thể.

Các phương thức đọc thường dùng:

- `get("field")` lấy nút con theo tên thuộc tính. Nếu thuộc tính không tồn tại, phương thức trả về `null` của Java.
- `path("field")` cũng truy cập thuộc tính nhưng trả về `MissingNode` nếu không tìm thấy. Vì vậy có thể nối nhiều lần gọi `path` để đi sâu vào cấu trúc mà không phải kiểm tra `null` sau từng bước.
- `get(index)` hoặc `path(index)` truy cập phần tử mảng theo chỉ số bắt đầu từ `0`.
- `at("/profile/city")` tìm nút theo JSON Pointer. Kết quả cũng là `MissingNode` nếu đường dẫn không khớp.

Ví dụ truy cập một đối tượng lồng nhau và phần tử đầu tiên của mảng:

```java
String city = root.path("profile").path("city").asText();
String firstRole = root.path("roles").path(0).asText();

JsonNode cityNode = root.at("/profile/city");
```

Với JSON Pointer, dấu `/` phân tách các đoạn đường dẫn. Nếu tên thuộc tính có ký tự `~` hoặc `/`, cần mã hóa chúng lần lượt thành `~0` và `~1` theo quy tắc JSON Pointer.

## 5. Kiểm tra loại nút trước khi lấy giá trị

Vì `JsonNode` có thể đại diện cho nhiều loại dữ liệu, không nên giả định một thuộc tính luôn có kiểu mong đợi. Các phương thức kiểm tra loại phổ biến gồm:

| Phương thức | Ý nghĩa |
|---|---|
| `isObject()` | Nút là đối tượng JSON |
| `isArray()` | Nút là mảng JSON |
| `isTextual()` | Nút là chuỗi |
| `isNumber()` | Nút là số |
| `isIntegralNumber()` / `isFloatingPointNumber()` | Nút là số nguyên / số dấu phẩy động |
| `isBoolean()` | Nút là boolean |
| `isNull()` | Nút biểu diễn JSON `null` |
| `isMissingNode()` | Nút là dấu hiệu đường dẫn không tồn tại |

Ví dụ, chỉ đọc `age` như một số nguyên khi nút thực sự là số nguyên và nằm trong phạm vi `int`:

```java
JsonNode ageNode = root.path("age");

if (ageNode.isIntegralNumber() && ageNode.canConvertToInt()) {
    int age = ageNode.intValue();
    System.out.println(age);
} else {
    System.out.println("age không phải số nguyên hợp lệ");
}
```

Các phương thức như `asText()`, `asInt()` và `asBoolean()` hỗ trợ chuyển giá trị sang kiểu Java tương ứng. Một số phương thức `as...` có thể trả về giá trị mặc định khi nút bị thiếu hoặc không chuyển đổi được. Khi cần phân biệt dữ liệu hợp lệ với dữ liệu sai kiểu, hãy kiểm tra loại nút trước, hoặc dùng các phương thức nhận giá trị mặc định như `asInt(0)` một cách có chủ đích.

### Phân biệt thuộc tính không có, thuộc tính `null` và thuộc tính có giá trị

Ba trạng thái này thường cần được xử lý khác nhau:

```java
boolean containsNickname = root.has("nickname");
boolean nicknameHasValue = root.hasNonNull("nickname");

JsonNode absentByGet = root.get("phone");
JsonNode absentByPath = root.path("phone");
```

- `has("nickname")` trả về `true` nếu thuộc tính tồn tại, kể cả khi giá trị của nó là `null`.
- `hasNonNull("nickname")` chỉ trả về `true` khi thuộc tính tồn tại và giá trị không phải JSON `null`.
- `get("phone")` trả về `null` Java khi không có thuộc tính `phone`.
- `path("phone").isMissingNode()` trả về `true` khi không có thuộc tính đó.

Phân biệt các trạng thái này đặc biệt hữu ích khi xử lý API: thuộc tính bị lược bỏ có thể mang ý nghĩa “không gửi thông tin”, trong khi thuộc tính có giá trị `null` có thể mang ý nghĩa “chủ động xóa” hoặc “không có giá trị”. Ý nghĩa cụ thể phụ thuộc vào hợp đồng của API.

## 6. Duyệt các nút con trong cây

Với một `ObjectNode`, `fields()` cung cấp các cặp tên thuộc tính và nút giá trị. Với một `ArrayNode`, `elements()` cung cấp các nút phần tử. `fieldNames()` chỉ trả về tên thuộc tính.

```java
JsonNode profile = root.path("profile");
if (profile.isObject()) {
    var fields = profile.fields();
    while (fields.hasNext()) {
        var entry = fields.next();
        System.out.println(entry.getKey() + " = " + entry.getValue());
    }
}

JsonNode roles = root.path("roles");
if (roles.isArray()) {
    for (JsonNode role : roles) {
        System.out.println(role.asText());
    }
}
```

Điểm quan trọng là mỗi nút con vẫn có kiểu `JsonNode`. Vì vậy, trong một vòng lặp duyệt mảng, phần tử có thể là chuỗi, số, đối tượng hoặc một mảng khác. Nếu cấu trúc không cố định, hãy kiểm tra loại từng phần tử trước khi xử lý.

## 7. Chỉnh sửa cây bằng `ObjectNode` và `ArrayNode`

`JsonNode` cung cấp cách truy cập thống nhất, còn những thao tác chỉnh sửa cấu trúc được thực hiện thông qua các lớp nút chứa cụ thể:

- `ObjectNode` dùng `put(...)` để thêm hoặc thay thế giá trị đơn, `set(...)` để gán một `JsonNode`, và `remove(...)` để xóa thuộc tính.
- `ArrayNode` dùng `add(...)` để thêm phần tử vào cuối mảng, cùng các phương thức chèn, thay thế hoặc xóa phần tử khi cần.
- `deepCopy()` tạo bản sao sâu của cây con để có thể chỉnh sửa bản sao mà vẫn giữ cây ban đầu.

Ví dụ sau thêm một thuộc tính, cập nhật đối tượng lồng nhau và bổ sung một phần tử vào mảng:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

ObjectNode edited = ((ObjectNode) root).deepCopy();

edited.put("verified", true);

JsonNode profileNode = edited.get("profile");
if (profileNode != null && profileNode.isObject()) {
    ((ObjectNode) profileNode).put("country", "Vietnam");
}

JsonNode rolesNode = edited.get("roles");
if (rolesNode != null && rolesNode.isArray()) {
    ((ArrayNode) rolesNode).add("reviewer");
}

edited.remove("nickname");
```

Đoạn mã giả định nút gốc là đối tượng, vì vậy có ép kiểu sang `ObjectNode`. Trong chương trình xử lý JSON không cố định, cần kiểm tra `root.isObject()` trước khi ép kiểu. Tương tự, chỉ ép kiểu một nút con sang `ObjectNode` hoặc `ArrayNode` sau khi xác nhận loại nút phù hợp.

Các nút giá trị như `TextNode` hoặc `IntNode` thường được xem là giá trị bất biến. Khi cần thay đổi một giá trị trong đối tượng, hãy cập nhật nút chứa bằng `put` hoặc `set` thay vì cố sửa trực tiếp nút giá trị.

## 8. Chuyển đổi giữa `JsonNode` và đối tượng Java

Tree Model không loại bỏ khả năng ánh xạ dữ liệu sang POJO. Nó cho phép chương trình chọn thời điểm thực hiện việc ánh xạ:

```java
// Chuyển một cây JSON sang lớp Java đã biết cấu trúc.
User user = mapper.treeToValue(root, User.class);

// Chuyển một đối tượng Java thành cây JSON.
JsonNode userTree = mapper.valueToTree(user);

// Ghi cây đã chỉnh sửa thành chuỗi JSON dễ đọc.
String output = mapper.writerWithDefaultPrettyPrinter()
        .writeValueAsString(edited);
```

`treeToValue(...)` hữu ích khi đã đọc JSON thành cây, kiểm tra hoặc chỉnh sửa một số trường, rồi mới chuyển phần dữ liệu cần thiết sang lớp Java. `valueToTree(...)` làm chiều ngược lại: chuyển một đối tượng Java thành cây để có thể duyệt hoặc thao tác theo API của `JsonNode`.

Jackson cũng có `convertValue(...)` để chuyển đổi giữa các kiểu dữ liệu có thể ánh xạ. Nên chọn phương thức thể hiện rõ ý định của thao tác: `readTree` để đọc thành cây, `treeToValue` để chuyển cây thành POJO, và `valueToTree` để chuyển đối tượng thành cây.

## 9. Khi nào nên dùng Tree Model?

`JsonNode` phù hợp khi cấu trúc JSON thay đổi theo nguồn dữ liệu, khi chương trình chỉ cần một vài trường, hoặc khi cần sửa một phần JSON trước khi ghi lại. Ví dụ, một dịch vụ nhận nhiều phiên bản phản hồi từ API có thể kiểm tra trường `status`, sau đó chỉ đọc nhánh `payload` nếu nhánh đó tồn tại.

Có thể so sánh ba cách làm phổ biến của Jackson như sau:

| Cách xử lý | Đặc điểm | Nên cân nhắc khi |
|---|---|---|
| Streaming API (`JsonParser` / `JsonGenerator`) | Xử lý token tuần tự, không cần giữ toàn bộ tài liệu trong bộ nhớ | Dữ liệu rất lớn hoặc cần kiểm soát luồng xử lý chi tiết |
| Tree Model (`JsonNode`) | Dựng toàn bộ cấu trúc thành cây có thể duyệt và chỉnh sửa | Cấu trúc linh hoạt, cần kiểm tra nhiều nhánh hoặc sửa JSON |
| Data Binding (POJO) | Ánh xạ JSON trực tiếp vào lớp Java có kiểu rõ ràng | Cấu trúc dữ liệu ổn định và mô hình miền đã được định nghĩa |

Tree Model có một số giới hạn cần tính đến:

1. Jackson phải giữ các nút của tài liệu trong bộ nhớ. Với tài liệu rất lớn, việc dựng toàn bộ cây có thể tốn nhiều bộ nhớ hơn xử lý streaming.
2. `JsonNode` linh hoạt nhưng ít bảo đảm kiểu ở thời điểm biên dịch hơn POJO. Chương trình phải kiểm tra loại nút và sự hiện diện của trường khi đọc dữ liệu không đáng tin cậy.
3. Cây biểu diễn cấu trúc và giá trị JSON, không phải bản sao nguyên văn của tài liệu đầu vào. Khoảng trắng và cách định dạng ban đầu không được giữ lại như một phần của cây; khi ghi lại, Jackson tạo JSON theo cấu hình ghi hiện tại.
4. Việc đọc được một cây không đồng nghĩa dữ liệu đã hợp lệ theo quy tắc nghiệp vụ. Các điều kiện như trường bắt buộc, giới hạn giá trị và quan hệ giữa các trường vẫn cần được kiểm tra riêng.

## 10. Các nguyên tắc sử dụng `JsonNode` hiệu quả

- Giữ biến ở kiểu `JsonNode` khi cấu trúc có thể thay đổi; chỉ ép kiểu sang `ObjectNode` hoặc `ArrayNode` sau khi kiểm tra `isObject()` hoặc `isArray()`.
- Dùng `path(...)` khi muốn truy cập chuỗi đường dẫn an toàn trước trường hợp thiếu nút; dùng `get(...)` khi cần phân biệt rõ `null` Java do không có thuộc tính.
- Phân biệt `NullNode` và `MissingNode` để không làm mất ý nghĩa của dữ liệu đầu vào.
- Kiểm tra loại nút trước khi gọi các phương thức lấy giá trị nếu dữ liệu có thể sai kiểu.
- Dùng `deepCopy()` trước khi chỉnh sửa nếu cần giữ lại cây ban đầu.
- Chọn POJO cho cấu trúc ổn định và Streaming API cho tài liệu lớn; dùng Tree Model khi sự linh hoạt của cấu trúc cây đem lại lợi ích rõ ràng.

## 11. Kết luận

`JsonNode` là kiểu trừu tượng trung tâm của Tree Model trong Jackson. Nó cho phép ứng dụng biểu diễn JSON thành cây đối tượng Java, truy cập các nhánh và phần tử, kiểm tra loại dữ liệu, phân biệt giá trị `null` với nút không tồn tại, cũng như phối hợp với `ObjectNode` và `ArrayNode` để chỉnh sửa cấu trúc. Thông qua `ObjectMapper`, cây có thể được tạo từ JSON, chuyển đổi sang POJO hoặc ghi trở lại thành JSON. Nhờ vậy, Tree Model là lựa chọn phù hợp khi ứng dụng cần xử lý JSON linh hoạt mà chưa thể hoặc chưa cần ánh xạ toàn bộ dữ liệu vào một lớp Java cố định.
