# Xóa, thay thế và thêm thuộc tính mà không làm sai cấu trúc

Jackson Tree Model cho phép ứng dụng đọc JSON thành một cây `JsonNode`, sau đó truy cập và chỉnh sửa từng object, array hoặc giá trị trong cây. Khi cần xóa một field, thay giá trị hiện tại hoặc thêm thuộc tính mới, các thao tác chính thường được thực hiện trên `ObjectNode` và `ArrayNode`.

Điều quan trọng là giữ đúng cấu trúc JSON trong suốt quá trình chỉnh sửa. Một object property có thể chứa object, array, string, number, boolean hoặc `null`; việc thay một node bằng sai loại có thể làm thay đổi hợp đồng dữ liệu. Ngoài ra, **field bị xóa, field có giá trị JSON `null` và field không tồn tại là ba trạng thái khác nhau**.

Các ví dụ trong bài sử dụng Jackson 2.x với package `com.fasterxml.jackson`. Tree Model phù hợp khi cần thao tác linh hoạt trên JSON mà không muốn ánh xạ toàn bộ tài liệu vào một POJO cố định.

## 1. Đọc JSON thành cây và nhận diện loại node

`ObjectMapper.readTree()` đọc JSON thành một đối tượng `JsonNode`. Tùy cấu trúc gốc, node đó có thể là object, array hoặc một giá trị đơn.

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "id": 101,
          "name": "An",
          "active": true,
          "tags": ["java", "jackson"],
          "profile": {
            "city": "Ho Chi Minh City",
            "nickname": null
          }
        }
        """;

JsonNode parsed = mapper.readTree(json);
if (parsed == null || !parsed.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object at the root");
}

ObjectNode root = (ObjectNode) parsed;
```

`JsonNode` là kiểu cơ sở dùng để đọc và duyệt mọi node. Các node container có API chỉnh sửa riêng:

| Loại node | Kiểu cụ thể | Cấu trúc |
|---|---|---|
| Object | `ObjectNode` | Các cặp tên field và node value |
| Array | `ArrayNode` | Các node theo thứ tự và index |
| String | `TextNode` | Một giá trị chuỗi |
| Number | `NumericNode` | Một giá trị số |
| Boolean | `BooleanNode` | `true` hoặc `false` |
| Null | `NullNode` | Giá trị JSON `null` |
| Thiếu field/path | `MissingNode` khi dùng `path()` | Không phải một giá trị JSON có trong tài liệu |

`ObjectNode` và `ArrayNode` là các container có thể thay đổi. Các node giá trị như `TextNode`, `IntNode` hoặc `NullNode` được dùng như giá trị; muốn thay giá trị, ứng dụng thay node trong container cha.

### 1.1. Kiểm tra loại node trước khi ép kiểu

Không nên ép một `JsonNode` sang `ObjectNode` hoặc `ArrayNode` khi chưa xác nhận loại:

```java
JsonNode tagsNode = root.get("tags");

if (tagsNode == null || !tagsNode.isArray()) {
    throw new IllegalArgumentException("tags must be a JSON array");
}

ArrayNode tags = (ArrayNode) tagsNode;
```

Các phương thức như `isObject()`, `isArray()`, `isTextual()`, `isNumber()`, `isBoolean()` và `isNull()` giúp kiểm tra cấu trúc trước khi thực hiện thao tác cụ thể. Việc kiểm tra này đặc biệt quan trọng với JSON đến từ client hoặc hệ thống ngoài.

## 2. Thêm thuộc tính vào `ObjectNode`

Để thêm field có giá trị scalar, dùng các phương thức `put()` phù hợp với kiểu dữ liệu:

```java
root.put("displayName", "An Nguyen");
root.put("age", 28);
root.put("score", 9.5);
root.put("verified", true);
```

Jackson tạo node JSON tương ứng. Kết quả có dạng:

```json
{
  "displayName": "An Nguyen",
  "age": 28,
  "score": 9.5,
  "verified": true
}
```

Một số overload thường dùng:

| Phương thức | Loại JSON được tạo |
|---|---|
| `put(String, String)` | String |
| `put(String, int)` / `put(String, long)` | Number nguyên |
| `put(String, double)` / `put(String, float)` | Number thập phân |
| `put(String, boolean)` | Boolean |
| `putNull(String)` | Null |

### 2.1. Thêm object hoặc array lồng nhau

Khi muốn tạo một object con, dùng `putObject()`:

```java
ObjectNode metadata = root.putObject("metadata");
metadata.put("source", "import-job");
metadata.put("version", 2);
```

Khi muốn tạo array con, dùng `putArray()`:

```java
ArrayNode labels = root.putArray("labels");
labels.add("internal");
labels.add("reviewed");
```

JSON được tạo:

```json
{
  "metadata": {
    "source": "import-job",
    "version": 2
  },
  "labels": ["internal", "reviewed"]
}
```

Lưu ý: `putObject("metadata")` và `putArray("labels")` tạo container mới tại tên field đó. Nếu field đã tồn tại, giá trị hiện tại sẽ bị thay bằng container mới. Chỉ dùng các phương thức này khi chủ đích là tạo mới hoặc thay thế toàn bộ field; nếu muốn cập nhật object con hiện tại, hãy lấy node hiện có, kiểm tra loại rồi chỉnh sửa node đó.

### 2.2. Thêm một `JsonNode` có sẵn

Nếu giá trị đã là một node, dùng `set()`:

```java
ObjectNode preferences = mapper.createObjectNode();
preferences.put("theme", "dark");
preferences.put("notifications", true);

root.set("preferences", preferences);
```

`set()` phù hợp với object/array lồng nhau hoặc node đã được tạo bằng `mapper.createObjectNode()`, `mapper.createArrayNode()` hay `mapper.valueToTree(...)`.

Ví dụ chuyển một POJO thành node rồi gắn vào cây:

```java
UserSummary user = new UserSummary(7L, "An");
JsonNode userNode = mapper.valueToTree(user);
root.set("owner", userNode);
```

`valueToTree()` chuyển object Java thành cây JSON trong bộ nhớ. Cách này tránh việc tự nối chuỗi JSON và parse lại.

## 3. Phân biệt thêm mới và thay thế giá trị hiện có

Trong `ObjectNode`, tên field là duy nhất theo mô hình map. Gọi `put()` hoặc `set()` với tên đã tồn tại sẽ thay value cũ bằng value mới; không tạo thêm một field cùng tên theo ý nghĩa “append”.

```java
root.put("status", "draft");
root.put("status", "published");
```

Sau hai lệnh, `status` có giá trị `published`.

Có hai API thường gặp:

- `set(name, node)` gán node mới cho tên field và trả về `ObjectNode`, thuận tiện khi nối thao tác.
- `replace(name, node)` cũng gán node mới nhưng trả về node cũ, hoặc `null` nếu trước đó field chưa tồn tại.

Ví dụ cần giữ lại giá trị cũ:

```java
import com.fasterxml.jackson.databind.node.TextNode;

JsonNode previousStatus = root.replace("status", TextNode.valueOf("published"));

if (previousStatus == null) {
    System.out.println("status did not exist before the update");
} else {
    System.out.println("Previous value: " + previousStatus);
}
```

`replace()` có thể thêm field nếu tên đó chưa tồn tại vì thao tác bên dưới là cập nhật map. Nếu cần phân biệt rõ “chỉ thay field đã có” với “thêm nếu chưa có”, hãy kiểm tra `has()` trước khi gọi.

```java
if (!root.has("status")) {
    throw new IllegalArgumentException("status is required");
}

root.put("status", "published");
```

Không nên hiểu `set()` hoặc `replace()` là thao tác nối thêm field trùng tên. Nếu cần lưu nhiều giá trị cùng loại, cấu trúc phù hợp thường là JSON array.

## 4. Xóa thuộc tính bằng `remove()`

`ObjectNode.remove(name)` xóa field theo tên:

```java
JsonNode removed = root.remove("internalNote");
```

Giá trị trả về là node vừa bị xóa; nếu field không tồn tại, kết quả là `null`. Vì vậy, có thể dùng nó để ghi nhận hoặc kiểm tra việc xóa:

```java
JsonNode removed = root.remove("temporaryToken");
if (removed != null) {
    System.out.println("Temporary token was removed");
}
```

Xóa nhiều field bằng collection tên:

```java
import java.util.List;

root.remove(List.of("debugInfo", "internalNote", "legacyFlag"));
```

`remove()` không làm hỏng các field còn lại; nó chỉ bỏ entry tương ứng khỏi object. Nếu field không tồn tại, lệnh xóa không tạo ra field mới và thường không gây lỗi.

### 4.1. Xóa khác với gán `null`

Hai JSON sau có ý nghĩa khác nhau:

```json
{}
```

```json
{
  "nickname": null
}
```

Để xóa field:

```java
root.remove("nickname");
```

Để giữ field nhưng đặt giá trị JSON null:

```java
root.putNull("nickname");
```

Trong API, việc bỏ field có thể mang nghĩa “không cập nhật”, trong khi `null` có thể mang nghĩa “xóa giá trị hiện tại”. Cần theo đúng hợp đồng của endpoint hoặc message.

### 4.2. Xóa toàn bộ thuộc tính

`removeAll()` xóa mọi field của object:

```java
root.removeAll();
```

Sau lệnh này, object vẫn tồn tại nhưng trở thành `{}`. Đây là thao tác có phạm vi rộng; chỉ dùng khi thật sự muốn làm rỗng object. Nếu chỉ muốn bỏ một vài field, hãy dùng `remove(name)` hoặc `remove(names)` để tránh xóa nhầm dữ liệu.

## 5. Phân biệt field không tồn tại, field null và field có giá trị

Khi chỉnh sửa JSON, cần kiểm tra trạng thái trước khi quyết định xóa hoặc thay thế. `get()`, `path()`, `has()` và `hasNonNull()` có hành vi khác nhau:

| API | Field không tồn tại | Field có JSON `null` | Field có giá trị |
|---|---|---|---|
| `get(name)` | Trả `null` Java | Trả `NullNode` | Trả node tương ứng |
| `path(name)` | Trả `MissingNode` | Trả `NullNode` | Trả node tương ứng |
| `has(name)` | `false` | `true` | `true` |
| `hasNonNull(name)` | `false` | `false` | `true` |

Ví dụ:

```java
if (!root.has("nickname")) {
    System.out.println("Field is absent");
} else if (root.get("nickname").isNull()) {
    System.out.println("Field exists with JSON null");
} else {
    System.out.println("Field has a value");
}
```

Không dùng `get(name) == null` để kiểm tra cả hai trường hợp “không có” và “JSON null”; `get()` trả về một `NullNode` cho field có giá trị JSON null.

## 6. Thay thế một node bằng đúng loại JSON

Một field có thể là string, number, boolean, object, array hoặc null. Khi thay thế, hãy chọn node phản ánh đúng schema mong muốn.

```java
root.put("retryCount", 3);                  // number
root.put("enabled", false);                // boolean
root.put("description", "Imported record"); // string
root.putNull("deletedAt");                 // JSON null

ObjectNode audit = mapper.createObjectNode();
audit.put("actor", "system");
audit.put("reason", "data migration");
root.set("audit", audit);                   // object

ArrayNode history = mapper.createArrayNode();
history.add("created");
history.add("approved");
root.set("history", history);               // array
```

Nếu schema quy định `retryCount` là number, thay nó bằng chuỗi `"3"` có thể làm client khác không đọc được. JSON parser vẫn coi đó là JSON hợp lệ, nhưng hợp đồng kiểu dữ liệu đã bị thay đổi.

### 6.1. Tránh biến object/array thành chuỗi JSON

Một lỗi thường gặp là serialize node con thành chuỗi rồi gán chuỗi đó vào field:

```java
String profileJson = mapper.writeValueAsString(profileNode);
root.put("profile", profileJson); // Sai nếu profile phải là JSON object
```

Kết quả sẽ là một JSON string chứa ký tự JSON:

```json
{
  "profile": "{\"city\":\"Ho Chi Minh City\"}"
}
```

Nếu muốn giữ `profile` là object, gắn trực tiếp node:

```java
root.set("profile", profileNode);
```

Kết quả:

```json
{
  "profile": {
    "city": "Ho Chi Minh City"
  }
}
```

Đừng nhầm một chuỗi chứa văn bản JSON với một object JSON thật. Hai dạng này có cấu trúc khác nhau dù khi in ra có thể trông gần giống.

## 7. Cập nhật thuộc tính lồng nhau an toàn

Để sửa field ở sâu trong object, cần đi qua từng cấp và xác nhận node cha đúng là object. Ví dụ cập nhật `profile.city`:

```java
JsonNode profileNode = root.get("profile");
if (profileNode == null || !profileNode.isObject()) {
    throw new IllegalArgumentException("profile must be an object");
}

ObjectNode profile = (ObjectNode) profileNode;
profile.put("city", "Da Nang");
```

Nếu `profile` bị thiếu, có giá trị null hoặc là array/string, code sẽ dừng với lỗi rõ ràng thay vì ép kiểu sai hoặc vô tình thay toàn bộ node.

### 7.1. Cập nhật sâu hơn nhiều cấp

Giả sử cấu trúc là `customer.address.city`:

```java
JsonNode customerNode = root.get("customer");
if (customerNode == null || !customerNode.isObject()) {
    throw new IllegalArgumentException("customer must be an object");
}

JsonNode addressNode = customerNode.get("address");
if (addressNode == null || !addressNode.isObject()) {
    throw new IllegalArgumentException("customer.address must be an object");
}

ObjectNode address = (ObjectNode) addressNode;
address.put("city", "Da Nang");
```

Kiểm tra từng cấp giúp xác định chính xác nơi cấu trúc không như mong đợi. Đặc biệt, nếu `address` là array nhưng code giả định object, việc tự tạo object mới và thay thế có thể làm mất dữ liệu cũ.

### 7.2. Tạo object cha nếu field chưa tồn tại

Đôi khi hợp đồng cho phép tạo `customer` hoặc `address` nếu chưa có. Hãy quy định rõ cách xử lý khi node đang là null hoặc sai kiểu:

```java
JsonNode customerNode = root.get("customer");
ObjectNode customer;

if (customerNode == null || customerNode.isNull()) {
    customer = mapper.createObjectNode();
    root.set("customer", customer);
} else if (customerNode.isObject()) {
    customer = (ObjectNode) customerNode;
} else {
    throw new IllegalArgumentException("customer must be an object or null");
}

JsonNode addressNode = customer.get("address");
ObjectNode address;

if (addressNode == null || addressNode.isNull()) {
    address = mapper.createObjectNode();
    customer.set("address", address);
} else if (addressNode.isObject()) {
    address = (ObjectNode) addressNode;
} else {
    throw new IllegalArgumentException("customer.address must be an object or null");
}

address.put("city", "Da Nang");
```

Code chỉ tạo object mới khi field chưa tồn tại hoặc đang là null. Nếu field đang chứa kiểu khác, nó từ chối thay đổi. Đây là chính sách an toàn khi kiểu node hiện tại có thể mang dữ liệu mà ứng dụng không được phép ghi đè.

## 8. Sửa phần tử trong `ArrayNode`

Array dùng index thay vì tên field. Có thể thêm, chèn, thay thế hoặc xóa phần tử:

```java
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.TextNode;

ArrayNode tags = (ArrayNode) root.get("tags");

tags.add("tree-model");          // Thêm vào cuối
tags.insert(0, "java");          // Chèn vào index 0
tags.set(1, TextNode.valueOf("jackson")); // Thay phần tử tại index 1
tags.remove(2);                  // Xóa phần tử tại index 2
```

Các thao tác có ý nghĩa khác nhau:

| API | Hành vi |
|---|---|
| `add(value)` | Thêm phần tử vào cuối array |
| `insert(index, value)` | Chèn phần tử tại index; các phần tử phía sau dịch sang phải |
| `set(index, value)` | Thay phần tử hiện có tại index; độ dài array không đổi |
| `remove(index)` | Xóa phần tử tại index; các phần tử phía sau dịch sang trái |
| `removeAll()` | Xóa toàn bộ phần tử |

Trước khi gọi `set()` hoặc `remove(index)`, hãy xác nhận index hợp lệ. `ArrayNode` có `size()` để lấy số phần tử:

```java
int index = 2;
if (index < 0 || index >= tags.size()) {
    throw new IndexOutOfBoundsException("Invalid tag index: " + index);
}

tags.remove(index);
```

Xóa phần tử sẽ làm thay đổi index của những phần tử phía sau. Nếu đang duyệt array bằng index từ đầu đến cuối và xóa phần tử ngay trong vòng lặp, có thể bỏ qua phần tử kế tiếp do nó dịch sang vị trí hiện tại. Có thể duyệt ngược từ cuối về đầu hoặc xây dựng array mới chỉ chứa những phần tử cần giữ.

## 9. Xóa field lồng nhau và xóa phần tử trong array con

Ví dụ xóa `profile.nickname`:

```java
JsonNode profileNode = root.get("profile");
if (profileNode != null && profileNode.isObject()) {
    ((ObjectNode) profileNode).remove("nickname");
}
```

Nếu `items` là array các object và cần xóa field `debug` khỏi từng item:

```java
JsonNode itemsNode = root.get("items");
if (itemsNode == null || !itemsNode.isArray()) {
    throw new IllegalArgumentException("items must be an array");
}

ArrayNode items = (ArrayNode) itemsNode;
for (JsonNode item : items) {
    if (item.isObject()) {
        ((ObjectNode) item).remove("debug");
    }
}
```

Đoạn code trên bỏ qua phần tử không phải object. Nếu schema yêu cầu mọi phần tử đều là object, nên ném lỗi khi gặp phần tử sai kiểu thay vì âm thầm bỏ qua. Cách xử lý phụ thuộc vào việc JSON đầu vào có được xem là dữ liệu tin cậy hay không.

## 10. Làm việc với đường dẫn JSON và `JsonPointer`

`JsonNode.at()` hỗ trợ tìm node theo JSON Pointer, ví dụ `/customer/address/city`:

```java
JsonNode cityNode = root.at("/customer/address/city");

if (cityNode.isMissingNode()) {
    throw new IllegalArgumentException("customer.address.city is missing");
}

if (!cityNode.isTextual()) {
    throw new IllegalArgumentException("customer.address.city must be a string");
}
```

JSON Pointer rất tiện để đọc một vị trí sâu mà không cần viết nhiều lần `get()`. Tuy nhiên, `at()` trả về node được tìm thấy hoặc `MissingNode`; nó không cung cấp thao tác `set` trực tiếp tại đường dẫn. Muốn sửa, ứng dụng vẫn phải tìm parent node, xác nhận parent là `ObjectNode` hoặc `ArrayNode`, rồi thay child tại đó.

Ví dụ cập nhật field cuối của đường dẫn:

```java
JsonNode addressNode = root.at("/customer/address");
if (!addressNode.isObject()) {
    throw new IllegalArgumentException("customer.address must be an object");
}

((ObjectNode) addressNode).put("city", "Da Nang");
```

Nếu tên field có ký tự `/` hoặc `~`, JSON Pointer yêu cầu escape tương ứng (`~1` cho `/`, `~0` cho `~`). Dùng đường dẫn được tạo/escape đúng quy tắc thay vì nối chuỗi tùy tiện.

## 11. Giữ nguyên cây gốc bằng `deepCopy()`

Các thao tác trên `ObjectNode` và `ArrayNode` sửa trực tiếp cây đang được tham chiếu. Nếu cần giữ nguyên bản gốc để audit, so sánh hoặc thử biến đổi, hãy tạo bản sao sâu trước:

```java
ObjectNode original = (ObjectNode) mapper.readTree(json);
ObjectNode working = original.deepCopy();

working.remove("internalNote");
working.put("status", "published");
```

`deepCopy()` sao chép các node container lồng nhau để thay đổi trên `working` không làm thay đổi các object/array con trong `original`.

Nếu chỉ gán một biến khác trỏ tới cùng node:

```java
ObjectNode working = original;
working.remove("internalNote");
```

thì `working` và `original` cùng tham chiếu một object. Thay đổi qua biến này cũng nhìn thấy qua biến kia. Đây là nguyên nhân thường gặp khiến dữ liệu gốc bị sửa ngoài ý muốn.

## 12. Một quy trình cập nhật JSON hoàn chỉnh

Giả sử cần xử lý một profile theo các yêu cầu:

1. Bỏ field nội bộ `debugToken`.
2. Thay `status` thành `active`.
3. Cập nhật `profile.city` nếu `profile` là object.
4. Thêm `metadata.updatedBy`.
5. Giữ lại cây gốc để so sánh.

Code:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public class JsonTreeUpdateExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        String json = """
                {
                  "id": 101,
                  "status": "pending",
                  "debugToken": "internal-only",
                  "profile": {
                    "city": "Ho Chi Minh City",
                    "nickname": null
                  }
                }
                """;

        JsonNode parsed = mapper.readTree(json);
        if (parsed == null || !parsed.isObject()) {
            throw new IllegalArgumentException("Expected object JSON");
        }

        ObjectNode original = (ObjectNode) parsed;
        ObjectNode updated = original.deepCopy();

        updated.remove("debugToken");
        updated.put("status", "active");

        JsonNode profileNode = updated.get("profile");
        if (profileNode == null || !profileNode.isObject()) {
            throw new IllegalArgumentException("profile must be an object");
        }
        ((ObjectNode) profileNode).put("city", "Da Nang");

        ObjectNode metadata = updated.putObject("metadata");
        metadata.put("updatedBy", "system");

        String updatedJson = mapper.writerWithDefaultPrettyPrinter()
                .writeValueAsString(updated);

        System.out.println(updatedJson);
        System.out.println("Original still has debugToken: "
                + original.has("debugToken"));
    }
}
```

Kết quả được ghi ra là một JSON object hợp lệ. `debugToken` không còn trong bản cập nhật; `status` là string; `profile` vẫn là object; `metadata` là object con. Cây `original` vẫn giữ `debugToken` vì thao tác được thực hiện trên bản sao sâu.

## 13. Khi nào nên dùng `set()`, `put()`, `replace()` hay `remove()`?

| Nhu cầu | API phù hợp | Ghi chú |
|---|---|---|
| Thêm/thay scalar | `put(name, value)` | Chọn overload đúng kiểu |
| Đặt JSON null | `putNull(name)` | Giữ field với giá trị null |
| Thêm/thay object hoặc array node | `set(name, node)` | Không serialize node thành string |
| Thêm object con mới | `putObject(name)` | Thay nội dung cũ tại tên đó nếu đã tồn tại |
| Thêm array con mới | `putArray(name)` | Thay nội dung cũ tại tên đó nếu đã tồn tại |
| Thay node và lấy node cũ | `replace(name, node)` | Trả node trước đó hoặc null nếu chưa có |
| Xóa một field | `remove(name)` | Trả node đã xóa hoặc null |
| Xóa nhiều field | `remove(names)` | Truyền danh sách tên field |
| Xóa mọi field | `removeAll()` | Object còn lại là `{}` |
| Thêm/chèn phần tử array | `add(value)` / `insert(index, value)` | `insert` làm dịch index phía sau |
| Thay/xóa phần tử array | `set(index, value)` / `remove(index)` | Kiểm tra index trước khi thao tác |

## 14. Những lỗi dễ làm sai cấu trúc JSON

### 14.1. Thay object bằng chuỗi

Gán `writeValueAsString(child)` bằng `put()` làm node object biến thành JSON string. Dùng `set()` để giữ nguyên cấu trúc node.

### 14.2. Ghi đè container mà không kiểm tra

`putObject()` và `putArray()` tạo container mới tại field được chỉ định. Nếu field cũ chứa dữ liệu, dữ liệu đó bị thay thế. Khi cần cập nhật, hãy lấy node hiện có và kiểm tra `isObject()`/`isArray()` trước.

### 14.3. Nhầm field null với field thiếu

`remove()` xóa field; `putNull()` giữ field với JSON null. Hai thao tác có thể mang ý nghĩa nghiệp vụ khác nhau.

### 14.4. Ép kiểu node khi chưa xác nhận cấu trúc

Ép `JsonNode` sang `ObjectNode` hoặc `ArrayNode` khi input có thể là kiểu khác sẽ gây `ClassCastException`. Kiểm tra loại trước khi cast.

### 14.5. Xóa phần tử array trong vòng lặp tiến

Khi xóa phần tử, các index phía sau dịch trái. Duyệt tiến và xóa có thể khiến phần tử kế tiếp bị bỏ qua. Duyệt ngược hoặc tạo array mới nếu cần lọc nhiều phần tử.

### 14.6. Sửa cây gốc khi cần giữ dữ liệu ban đầu

Gán biến mới bằng `ObjectNode working = original` không tạo bản sao. Dùng `deepCopy()` nếu cần một cây độc lập.

### 14.7. Tạo JSON object có field trùng tên bằng cách nối chuỗi

Không tự ghép chuỗi JSON để thêm field. JSON có thể bị sai dấu phẩy, escape hoặc có key trùng lặp. Dùng Tree Model để thêm, thay và xóa node rồi để Jackson serialize.

## 15. Kiểm tra kết quả sau khi chỉnh sửa

Sau khi hoàn tất các thay đổi, có thể serialize cây thành JSON:

```java
String output = mapper.writeValueAsString(root);
```

Nếu cần dễ đọc:

```java
String output = mapper.writerWithDefaultPrettyPrinter()
        .writeValueAsString(root);
```

Có thể parse lại output để xác nhận đó là JSON hợp lệ và kiểm tra cấu trúc:

```java
JsonNode reparsed = mapper.readTree(output);

if (!reparsed.isObject()) {
    throw new IllegalStateException("Updated document is no longer an object");
}

if (reparsed.has("debugToken")) {
    throw new IllegalStateException("Internal field was not removed");
}

if (!reparsed.path("profile").path("city").isTextual()) {
    throw new IllegalStateException("profile.city must be a string");
}
```

Parse lại giúp kiểm tra cú pháp JSON và các điều kiện cấu trúc cần thiết. Với một hợp đồng phức tạp, nên ánh xạ cây sang DTO hoặc xác thực schema ở bước phù hợp; việc parse thành công không chứng minh mọi quy tắc nghiệp vụ đều đúng.

## 16. Ghi nhớ khi thao tác trên JSON Tree

`ObjectNode` là nơi thêm, thay thế và xóa thuộc tính của JSON object; `ArrayNode` là nơi chỉnh sửa các phần tử theo index. Dùng `put()` cho scalar, `putNull()` cho JSON null, `set()` cho node con và `remove()` để xóa field. Trước khi cập nhật node lồng nhau, kiểm tra loại node cha và chính sách khi field bị thiếu hoặc null. Dùng `deepCopy()` nếu cần giữ cây gốc không đổi.

Hãy để Jackson quản lý cấu trúc JSON thay vì tự ghép chuỗi. Khi giữ đúng loại node, phân biệt rõ missing/null và kiểm tra các cấp lồng nhau trước khi chỉnh sửa, ứng dụng có thể biến đổi JSON linh hoạt mà không vô tình làm hỏng hợp đồng dữ liệu.
