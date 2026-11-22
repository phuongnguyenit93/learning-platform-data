# Tạo và sửa `ObjectNode`, `ArrayNode`

## 1. Vai trò của ObjectNode và ArrayNode trong Tree Model

Jackson Tree Model biểu diễn tài liệu JSON thành một cây các node trong bộ nhớ. `JsonNode` là kiểu cơ sở để đọc và duyệt cây. Khi cần tạo hoặc thay đổi cấu trúc, hai lớp quan trọng nhất là:

- **`ObjectNode`:** biểu diễn một JSON object, gồm các cặp tên thuộc tính và giá trị.
- **`ArrayNode`:** biểu diễn một JSON array, gồm các phần tử có thứ tự.

Ví dụ JSON:

```json
{
  "id": 101,
  "name": "Lan",
  "profile": {
    "city": "Da Nang"
  },
  "roles": ["admin", "editor"]
}
```

Trong cây này, node gốc và `profile` là `ObjectNode`; `roles` là `ArrayNode`; các giá trị như `101`, `"Lan"` và `"admin"` là các node giá trị.

`JsonNode` cung cấp API chung để đọc, kiểm tra kiểu và duyệt. `ObjectNode` và `ArrayNode` bổ sung các thao tác thay đổi cấu trúc như thêm, thay thế, chèn và xóa. Các node giá trị như `TextNode`, `IntNode`, `BooleanNode` và `NullNode` thường được xem là bất biến; khi muốn đổi giá trị của một property, chương trình cập nhật node chứa nó.

## 2. Tạo node bằng ObjectMapper

`ObjectMapper` cung cấp hai phương thức thuận tiện để tạo node chứa:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

ObjectMapper mapper = new ObjectMapper();

ObjectNode object = mapper.createObjectNode();
ArrayNode array = mapper.createArrayNode();
```

Hai node được tạo là rỗng:

- `object` ban đầu tương ứng với `{}`.
- `array` ban đầu tương ứng với `[]`.

Đây là các đối tượng có thể thay đổi. Ta có thể thêm property hoặc phần tử rồi ghi cây thành JSON bằng `ObjectMapper.writeValueAsString(...)`.

### Tạo object với các giá trị đơn

`ObjectNode.put(...)` có các overload cho những kiểu dữ liệu phổ biến:

```java
ObjectNode user = mapper.createObjectNode();

user.put("id", 101L);
user.put("name", "Lan");
user.put("active", true);
user.put("score", 9.5);
```

Jackson tạo node giá trị phù hợp với kiểu Java được truyền vào. Có thể ghi các kiểu số nguyên, số thực, boolean và chuỗi mà không cần tự tạo `IntNode`, `TextNode` hay `BooleanNode`.

### Tạo object lồng nhau

`putObject(fieldName)` tạo một `ObjectNode` con, gắn nó vào property được chỉ định và trả về node con để tiếp tục thao tác:

```java
ObjectNode user = mapper.createObjectNode();
user.put("id", 101L);
user.put("name", "Lan");

ObjectNode profile = user.putObject("profile");
profile.put("city", "Da Nang");
profile.put("country", "Vietnam");
```

Sau khi gọi `putObject("profile")`, `profile` đã là một phần của cây `user`. Không cần gọi thêm `set` để gắn lại node con.

### Tạo array lồng nhau

`putArray(fieldName)` tạo một `ArrayNode` rỗng ở property được chỉ định và trả về array để thêm phần tử:

```java
ArrayNode roles = user.putArray("roles");
roles.add("admin");
roles.add("editor");
```

Có thể kết hợp object và array nhiều cấp. Mỗi node con được tạo sẽ trở thành một phần của cây ngay khi dùng `putObject` hoặc `putArray`.

## 3. Thêm và thay thế property trong ObjectNode

`ObjectNode` lưu các property theo tên. Những thao tác thường dùng gồm:

| Phương thức | Tác dụng |
|---|---|
| `put(name, value)` | Thêm property hoặc thay giá trị hiện tại bằng node phù hợp với kiểu Java |
| `putNull(name)` | Thêm hoặc thay property bằng JSON `null` |
| `set(name, node)` | Gắn một `JsonNode` đã được tạo sẵn làm giá trị property |
| `putObject(name)` | Tạo object con và trả về `ObjectNode` con |
| `putArray(name)` | Tạo array con và trả về `ArrayNode` con |
| `remove(name)` | Xóa property theo tên |
| `removeAll()` | Xóa toàn bộ property của object |

### put thêm hoặc thay thế giá trị

Nếu property chưa tồn tại, `put` thêm property mới. Nếu property đã tồn tại, giá trị cũ được thay thế:

```java
ObjectNode user = mapper.createObjectNode();
user.put("name", "Lan");

user.put("name", "Lan Nguyen"); // Thay giá trị cũ
user.put("age", 28);             // Thêm property mới
```

Vì `put` vừa thêm vừa thay thế, chương trình không cần kiểm tra property đã tồn tại trước khi cập nhật nếu cả hai trường hợp đều có cùng ý nghĩa.

### putNull để ghi JSON null

Khi muốn property hiện diện với giá trị JSON null, dùng `putNull`:

```java
user.putNull("middleName");
```

Kết quả có property `middleName` với token JSON `null`. Điều này khác với việc không tạo property hoặc gọi `remove("middleName")`.

### set để gắn node đã có

Khi giá trị đã là một `JsonNode`, dùng `set`:

```java
ObjectNode address = mapper.createObjectNode();
address.put("city", "Da Nang");
address.put("postalCode", "550000");

user.set("address", address);
```

`set` hữu ích khi node được tạo từ một phần khác của chương trình hoặc được lấy từ một cây đã đọc. Nếu muốn dùng cùng một node làm nhiều nhánh độc lập, nên gắn một bản sao sâu bằng `deepCopy()` để những lần chỉnh sửa về sau không vô tình tác động đến phần dữ liệu dùng chung.

## 4. Xóa property trong ObjectNode

`remove(name)` xóa một property. Nếu property không tồn tại, object vẫn giữ nguyên:

```java
user.remove("temporaryToken");
```

Nếu cần xóa toàn bộ property và đưa object về `{}`, dùng `removeAll()`:

```java
user.removeAll();
```

Có thể kiểm tra trước khi xóa bằng `has(name)` hoặc lấy node bằng `get(name)`. Phương thức `remove` trả về node đã bị xóa nếu property tồn tại, hoặc Java null nếu không tìm thấy. Điều này hữu ích khi cần ghi nhận hoặc xử lý giá trị cũ:

```java
JsonNode oldValue = user.remove("status");
if (oldValue != null) {
    System.out.println("Removed status: " + oldValue);
}
```

Không nhầm xóa property với gán JSON null:

```java
user.putNull("middleName"); // Property vẫn tồn tại, giá trị là null
user.remove("middleName"); // Property không còn trong object
```

Hai kết quả này có ý nghĩa khác nhau đối với API, đặc biệt khi client dùng JSON để cập nhật một phần dữ liệu.

## 5. Thêm phần tử vào ArrayNode

Array có thứ tự và mỗi phần tử được truy cập bằng chỉ số bắt đầu từ 0. `ArrayNode.add(...)` thêm phần tử vào cuối mảng:

```java
ArrayNode roles = mapper.createArrayNode();
roles.add("reader");
roles.add("editor");
roles.add("publisher");
```

Các overload của `add` nhận kiểu Java phổ biến như string, boolean và number. Có thể thêm JSON null bằng `addNull()`:

```java
roles.addNull();
```

Nếu đã có một node, dùng `add(JsonNode)`:

```java
ObjectNode role = mapper.createObjectNode();
role.put("code", "reviewer");
role.put("enabled", true);

roles.add(role);
```

Để tạo object hoặc array trực tiếp bên trong array, dùng `addObject()` và `addArray()`:

```java
ArrayNode items = mapper.createArrayNode();

ObjectNode first = items.addObject();
first.put("sku", "BK-01");
first.put("quantity", 2);

ArrayNode tags = items.addArray();
tags.add("featured");
tags.add("sale");
```

Các node được tạo đã được thêm vào array khi phương thức trả về. Ta có thể điền nội dung ngay qua biến node con.

## 6. Chèn, thay thế và xóa phần tử trong ArrayNode

Ngoài thêm ở cuối, `ArrayNode` hỗ trợ thao tác theo index:

| Phương thức | Tác dụng |
|---|---|
| `add(value)` | Thêm phần tử ở cuối |
| `insert(index, value)` | Chèn phần tử tại vị trí index, đẩy các phần tử sau sang phải |
| `set(index, value)` | Thay thế phần tử đang có tại index |
| `remove(index)` | Xóa phần tử tại index, các phần tử sau dịch sang trái |
| `removeAll()` | Xóa toàn bộ phần tử |

Ví dụ:

```java
ArrayNode numbers = mapper.createArrayNode();
numbers.add(10);
numbers.add(30);

numbers.insert(1, 20); // [10, 20, 30]
numbers.set(2, 35);    // [10, 20, 35]
numbers.remove(0);    // [20, 35]
```

`insert` làm thay đổi vị trí các phần tử phía sau. `set` chỉ thay thế phần tử ở vị trí đã có, không chèn thêm. `remove(index)` làm giảm kích thước mảng một phần tử.

Trước khi dùng index lấy hoặc thay thế phần tử, nên kiểm tra `index >= 0 && index < array.size()`. Index ngoài phạm vi có thể dẫn đến `IndexOutOfBoundsException`. Với `insert`, cần tuân theo phạm vi chèn hợp lệ từ 0 đến kích thước hiện tại của mảng.

Có thể xóa phần tử dựa trên nội dung bằng cách duyệt và kiểm tra từng node. Khi xóa nhiều phần tử theo index, hãy nhớ rằng các phần tử sau sẽ dịch vị trí; thường nên duyệt từ cuối mảng về đầu để tránh bỏ sót phần tử.

## 7. Tạo cây JSON hoàn chỉnh

Ví dụ dưới đây kết hợp object, array, object lồng nhau và giá trị null:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

public class BuildJsonTree {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        ObjectNode root = mapper.createObjectNode();
        root.put("id", 101);
        root.put("name", "Lan");
        root.put("active", true);

        ObjectNode profile = root.putObject("profile");
        profile.put("city", "Da Nang");
        profile.put("country", "Vietnam");

        ArrayNode roles = root.putArray("roles");
        roles.add("admin");
        roles.add("editor");

        root.putNull("nickname");

        String json = mapper.writerWithDefaultPrettyPrinter()
                .writeValueAsString(root);
        System.out.println(json);
    }
}
```

JSON được tạo có cấu trúc tương đương:

```json
{
  "id" : 101,
  "name" : "Lan",
  "active" : true,
  "profile" : {
    "city" : "Da Nang",
    "country" : "Vietnam"
  },
  "roles" : [ "admin", "editor" ],
  "nickname" : null
}
```

`ObjectMapper` chịu trách nhiệm serialize cây node thành văn bản JSON hợp lệ, bao gồm dấu ngoặc, dấu phẩy, dấu nháy và escape chuỗi. Không cần nối chuỗi thủ công để tạo JSON.

## 8. Đọc JSON có sẵn rồi chỉnh sửa cây

Trong ứng dụng thực tế, cây thường được tạo từ JSON đầu vào. `readTree` trả về `JsonNode` vì root có thể là object, array hoặc một giá trị scalar. Chỉ ép kiểu sang `ObjectNode` sau khi kiểm tra `isObject()`:

```java
String input = """
        {
          "id": 101,
          "name": "Lan",
          "roles": ["reader"],
          "profile": {"city": "Da Nang"}
        }
        """;

JsonNode parsed = mapper.readTree(input);
if (parsed == null || !parsed.isObject()) {
    throw new IllegalArgumentException("Root JSON value must be an object");
}

ObjectNode root = (ObjectNode) parsed;
root.put("active", true);
root.put("name", "Lan Nguyen");
root.remove("temporary");

ArrayNode roles = (ArrayNode) root.path("roles");
roles.add("editor");

String updatedJson = mapper.writeValueAsString(root);
```

Đoạn mã giả định `roles` tồn tại và là array, vì vậy có thể ép kiểu sau khi kiểm tra dữ liệu thực tế. Với JSON không đáng tin cậy, nên kiểm tra node trước khi ép kiểu:

```java
JsonNode rolesNode = root.get("roles");
if (rolesNode == null || !rolesNode.isArray()) {
    throw new IllegalArgumentException("roles must be an array");
}

ArrayNode roles = (ArrayNode) rolesNode;
roles.add("editor");
```

Nếu property chưa có và muốn tạo array mới, dùng `putArray("roles")`. Nếu property đã có nhưng không phải array, hãy quyết định rõ có được phép thay thế giá trị cũ hay không; không nên âm thầm ghi đè dữ liệu sai kiểu nếu việc đó làm mất thông tin quan trọng.

## 9. Thay đổi node lồng nhau một cách an toàn

Khi truy cập object con, `get` trả về Java null nếu property không tồn tại. `path` trả về `MissingNode` trong trường hợp đó. Cả hai đều cần được phân biệt với `NullNode`, tức property có mặt nhưng chứa JSON null.

Ví dụ lấy hoặc tạo object `profile`:

```java
JsonNode profileNode = root.get("profile");
ObjectNode profile;

if (profileNode == null) {
    // Property chưa tồn tại: tạo object mới.
    profile = root.putObject("profile");
} else if (profileNode.isObject()) {
    // Đã là object: có thể chỉnh sửa trực tiếp.
    profile = (ObjectNode) profileNode;
} else {
    // Property có nhưng sai kiểu (có thể là null, string, array...).
    throw new IllegalArgumentException("profile must be an object");
}

profile.put("city", "Hue");
```

Ví dụ này chọn từ chối giá trị sai kiểu. Một API khác có thể cho phép thay thế một giá trị null bằng object mới, nhưng quyết định đó nên được thể hiện rõ trong logic.

Với array lồng nhau, áp dụng cùng nguyên tắc: kiểm tra `isArray()` trước khi ép kiểu sang `ArrayNode`, sau đó kiểm tra index trước khi truy cập hoặc thay thế phần tử.

## 10. Sao chép cây trước khi chỉnh sửa

`ObjectNode` và `ArrayNode` có thể thay đổi trực tiếp. Nếu cây gốc còn được dùng ở nơi khác, chỉnh sửa node gốc sẽ làm nơi giữ tham chiếu đến cùng node quan sát được thay đổi.

Khi cần giữ nguyên bản gốc, dùng `deepCopy()`:

```java
ObjectNode original = mapper.createObjectNode();
original.put("name", "Lan");
original.putObject("profile").put("city", "Da Nang");

ObjectNode edited = original.deepCopy();
edited.put("name", "Lan Nguyen");
((ObjectNode) edited.get("profile")).put("city", "Hue");

System.out.println(original.path("name").asText());
// Lan
System.out.println(original.path("profile").path("city").asText());
// Da Nang
```

`deepCopy()` sao chép cả các node con, vì vậy việc sửa object lồng nhau trong bản sao không làm thay đổi cây gốc. Với cây lớn, bản sao sâu cần thêm bộ nhớ; chỉ tạo bản sao khi thực sự cần hai phiên bản độc lập.

## 11. Duyệt ObjectNode và ArrayNode

Có thể duyệt tên property và node tương ứng bằng `fields()`:

```java
Iterator<Map.Entry<String, JsonNode>> fields = root.fields();
while (fields.hasNext()) {
    Map.Entry<String, JsonNode> entry = fields.next();
    System.out.println(entry.getKey() + " -> " + entry.getValue());
}
```

`fieldNames()` chỉ trả về tên property. Với array, có thể duyệt trực tiếp từng node:

```java
for (JsonNode role : roles) {
    if (role.isTextual()) {
        System.out.println(role.asText());
    }
}
```

Các node trong array có thể thuộc nhiều kiểu khác nhau. Nếu cấu trúc không cố định, hãy kiểm tra `isObject()`, `isArray()`, `isTextual()`, `isNumber()` hoặc `isNull()` trước khi xử lý.

Nếu cần sửa array trong khi duyệt, tránh thay đổi cấu trúc một cách tùy tiện trong vòng lặp đang dùng iterator. Có thể duyệt bằng index từ cuối về đầu khi xóa phần tử, hoặc thu thập các vị trí cần xóa trước rồi thực hiện thao tác sau.

## 12. Kết hợp ObjectNode và ArrayNode với data binding

Tree Model có thể kết hợp với POJO hoặc record. Khi một nhánh JSON có cấu trúc ổn định, có thể chuyển nhánh đó thành kiểu Java bằng `treeToValue`:

```java
JsonNode orderNode = root.path("order");
Order order = mapper.treeToValue(orderNode, Order.class);
```

Theo chiều ngược lại, có thể chuyển đối tượng Java thành cây bằng `valueToTree` rồi bổ sung các field linh hoạt:

```java
Order order = new Order("O-100", 250000);
ObjectNode response = mapper.valueToTree(order);
response.put("source", "mobile-app");
response.putArray("warnings").add("address-not-verified");
```

Cách kết hợp này hữu ích khi phần lớn dữ liệu có schema rõ ràng nhưng response cần một số metadata hoặc field động.

## 13. Ghi cây JSON ra chuỗi hoặc luồng

Sau khi tạo hoặc chỉnh sửa xong, dùng `ObjectMapper` để ghi cây:

```java
String compactJson = mapper.writeValueAsString(root);

String prettyJson = mapper.writerWithDefaultPrettyPrinter()
        .writeValueAsString(root);
```

Nếu cần ghi trực tiếp ra file hoặc `OutputStream`, có thể dùng `writeValue`:

```java
try (OutputStream output = Files.newOutputStream(Path.of("user.json"))) {
    mapper.writerWithDefaultPrettyPrinter().writeValue(output, root);
}
```

Khi tự mở stream, hãy đóng tài nguyên bằng `try-with-resources`. Nếu stream do framework hoặc thành phần khác quản lý, cần xác định rõ ai sở hữu và đóng stream trước khi chuyển nó cho Jackson.

## 14. Những lỗi thường gặp

### Ép kiểu khi chưa kiểm tra loại node

Không ép một `JsonNode` bất kỳ sang `ObjectNode` hoặc `ArrayNode`. JSON đầu vào có thể chứa scalar, null hoặc kiểu node khác. Hãy kiểm tra `isObject()` hoặc `isArray()` trước.

### Nhầm property bị thiếu với property null

`get(name) == null` thường có nghĩa property không tồn tại. Nếu property tồn tại với JSON null, `get(name)` trả về `NullNode`. Khi cập nhật, hãy quyết định rõ muốn giữ null hay xóa hẳn property.

### Dùng set để biểu diễn null mà không rõ ý định

Khi muốn ghi JSON null, `putNull(name)` thể hiện ý định rõ ràng. Khi muốn gắn một node có sẵn, dùng `set(name, node)`. Tránh truyền một tham chiếu Java null vào API khi mục tiêu là tạo token JSON null.

### Nhầm insert với set trong ArrayNode

`insert(index, value)` làm array tăng kích thước và đẩy phần tử phía sau. `set(index, value)` thay phần tử tại vị trí hiện có. Chọn sai phương thức có thể làm thay đổi thứ tự hoặc kích thước mảng.

### Sửa cây gốc ngoài ý muốn

Nếu nhiều thành phần đang giữ tham chiếu đến cùng một node, chỉnh sửa node đó sẽ ảnh hưởng đến tất cả nơi dùng chung tham chiếu. Dùng `deepCopy()` khi cần bản sao độc lập.

### Tự ghép chuỗi JSON

Không nối chuỗi thủ công để tạo JSON. Dữ liệu có dấu nháy, dấu gạch chéo ngược hoặc ký tự điều khiển cần escape đúng cách. Dùng `ObjectNode`, `ArrayNode`, `ObjectMapper` hoặc `JsonGenerator` để Jackson đảm nhiệm cú pháp.

## 15. Tổng kết API thường dùng

| Nhu cầu | ObjectNode | ArrayNode |
|---|---|---|
| Tạo node | `mapper.createObjectNode()` | `mapper.createArrayNode()` |
| Thêm giá trị đơn | `put(name, value)` | `add(value)` |
| Ghi null | `putNull(name)` | `addNull()` |
| Gắn node có sẵn | `set(name, node)` | `add(node)` |
| Tạo node con | `putObject(name)`, `putArray(name)` | `addObject()`, `addArray()` |
| Thay thế | `put` hoặc `set` theo tên | `set(index, value)` |
| Chèn | Không áp dụng theo index | `insert(index, value)` |
| Xóa | `remove(name)`, `removeAll()` | `remove(index)`, `removeAll()` |
| Sao chép sâu | `deepCopy()` | `deepCopy()` |

`ObjectNode` là công cụ để quản lý các property có tên; `ArrayNode` là công cụ để quản lý danh sách phần tử có thứ tự. Khi nắm rõ API tạo, thêm, thay thế, chèn và xóa, có thể xây dựng hoặc chỉnh sửa JSON phức tạp mà không phải tạo trước một hệ thống POJO cho toàn bộ cấu trúc.

## 16. Kết luận

`ObjectNode` và `ArrayNode` là hai kiểu node có thể thay đổi trong Jackson Tree Model. Dùng `ObjectMapper.createObjectNode()` và `createArrayNode()` để tạo cây mới; dùng `put`, `putNull`, `set`, `putObject` và `putArray` để xây dựng object; dùng `add`, `insert`, `set` và `remove` để thao tác với array. Khi chỉnh sửa JSON đã đọc, cần kiểm tra loại node và phân biệt property thiếu với giá trị null. Dùng `deepCopy()` nếu cần giữ nguyên bản gốc, rồi ghi kết quả bằng `ObjectMapper` để tạo JSON hợp lệ.
