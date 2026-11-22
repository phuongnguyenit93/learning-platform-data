# Duyệt trường của đối tượng và phần tử của mảng

Khi JSON có cấu trúc thay đổi hoặc ứng dụng chỉ cần lấy một vài trường mà chưa muốn tạo DTO cho toàn bộ payload, Jackson cung cấp **Tree Model** với kiểu `JsonNode`. Sau khi đọc JSON thành cây node, chương trình có thể kiểm tra một node là object hay array, duyệt tên trường và giá trị của object, hoặc duyệt lần lượt các phần tử của array.

Hai thao tác cần nhớ là:

- Với **JSON object**, dùng `fields()` để duyệt từng cặp tên trường và node giá trị; dùng `fieldNames()` nếu chỉ cần tên trường.
- Với **JSON array**, dùng `elements()` để duyệt các node phần tử theo thứ tự.

Khi dữ liệu lồng nhau, hãy kiểm tra kiểu node trước khi duyệt tiếp. Điều này giúp code xử lý được object chứa array, array chứa object và các cấu trúc JSON nhiều tầng mà không phải giả định mọi node đều có cùng kiểu.

## 1. Đọc JSON thành JsonNode

`JsonNode` là kiểu node cơ sở trong Jackson Databind Tree Model. Một JSON object thường được biểu diễn bằng `ObjectNode`, array bằng `ArrayNode`, còn các giá trị đơn giản như string, number, boolean và null được biểu diễn bằng những node tương ứng.

Ví dụ payload:

```json
{
  "id": "ORD-1001",
  "customer": {
    "name": "An",
    "active": true
  },
  "items": [
    { "sku": "BK-01", "quantity": 2 },
    { "sku": "PN-02", "quantity": 5 }
  ]
}
```

Đọc JSON thành cây:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(json);
```

`readTree()` phân tích cấu trúc JSON và trả về node gốc. Với ví dụ trên, `root` là object node. Bạn có thể bắt đầu duyệt trường của object hoặc truy cập các node con.

## 2. Phân biệt object và array trước khi duyệt

Một `JsonNode` có thể đại diện cho nhiều loại JSON. Trước khi dùng thao tác phù hợp, hãy kiểm tra loại node:

```java
if (root.isObject()) {
    System.out.println("Đây là JSON object");
} else if (root.isArray()) {
    System.out.println("Đây là JSON array");
} else if (root.isNull()) {
    System.out.println("Đây là JSON null");
} else if (root.isValueNode()) {
    System.out.println("Đây là giá trị đơn");
}
```

Các kiểm tra thường dùng gồm:

| Phương thức | Kiểm tra |
| --- | --- |
| `isObject()` | Node là JSON object |
| `isArray()` | Node là JSON array |
| `isTextual()` | Node là string |
| `isNumber()` | Node là number |
| `isBoolean()` | Node là boolean |
| `isNull()` | Node là JSON null |
| `isMissingNode()` | Node đại diện cho giá trị không tìm thấy, thường do `path()` trả về |
| `isValueNode()` | Node là một giá trị đơn thay vì container |

Không nên gọi `fields()` trên một node bất kỳ mà chưa xác định node đó có phải object hay không. Tương tự, `elements()` chỉ có ý nghĩa khi node là array hoặc container phù hợp.

## 3. Duyệt từng trường của JSON object bằng fields()

`fields()` trả về `Iterator<Map.Entry<String, JsonNode>>`. Mỗi entry chứa:

- `getKey()`: tên trường trong JSON.
- `getValue()`: node biểu diễn giá trị của trường.

Ví dụ:

```java
import com.fasterxml.jackson.databind.JsonNode;

Iterator<Map.Entry<String, JsonNode>> fields = root.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> field = fields.next();

    String fieldName = field.getKey();
    JsonNode fieldValue = field.getValue();

    System.out.println(fieldName + " -> " + fieldValue);
}
```

Với object đơn giản:

```json
{
  "name": "An",
  "age": 28,
  "active": true
}
```

Vòng lặp lần lượt nhận được các cặp tên/value tương ứng với `name`, `age` và `active`. `fieldValue` vẫn là `JsonNode`, vì vậy bạn có thể kiểm tra kiểu trước khi lấy giá trị Java.

### 3.1. Lấy kiểu giá trị của từng field

```java
Iterator<Map.Entry<String, JsonNode>> fields = root.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> field = fields.next();
    String name = field.getKey();
    JsonNode value = field.getValue();

    if (value.isTextual()) {
        System.out.println(name + " là chuỗi: " + value.textValue());
    } else if (value.isNumber()) {
        System.out.println(name + " là số: " + value.numberValue());
    } else if (value.isBoolean()) {
        System.out.println(name + " là boolean: " + value.booleanValue());
    } else if (value.isNull()) {
        System.out.println(name + " là null");
    } else if (value.isObject()) {
        System.out.println(name + " là object lồng nhau");
    } else if (value.isArray()) {
        System.out.println(name + " là array");
    }
}
```

Cách kiểm tra theo kiểu giúp tránh gọi `asInt()` hoặc `asText()` một cách tùy tiện khi dữ liệu có thể mang kiểu khác.

## 4. Chỉ duyệt tên trường bằng fieldNames()

Nếu chỉ cần tên các thuộc tính mà không cần giá trị, dùng `fieldNames()`:

```java
Iterator<String> names = root.fieldNames();

while (names.hasNext()) {
    String name = names.next();
    System.out.println(name);
}
```

Với object:

```json
{
  "id": "ORD-1001",
  "status": "PAID",
  "total": 250.00
}
```

kết quả duyệt là các tên `id`, `status` và `total`. Dùng `fieldNames()` khi cần kiểm tra schema động, ghi nhận những trường đang có hoặc xác định xem một tên trường có xuất hiện trong object hay không.

Nếu cần cả tên và giá trị, `fields()` phù hợp hơn vì không phải tra cứu lại từng node bằng tên.

## 5. Duyệt các phần tử của JSON array bằng elements()

JSON array là một danh sách có thứ tự. `elements()` trả về `Iterator<JsonNode>` để đọc từng phần tử theo thứ tự trong mảng.

Ví dụ:

```json
[
  "Java",
  "Jackson",
  "Spring"
]
```

Code:

```java
JsonNode tags = root.get("tags");

if (tags != null && tags.isArray()) {
    Iterator<JsonNode> elements = tags.elements();

    while (elements.hasNext()) {
        JsonNode element = elements.next();
        System.out.println(element.asText());
    }
}
```

Với array object, mỗi phần tử vẫn là một `JsonNode`:

```json
[
  { "sku": "BK-01", "quantity": 2 },
  { "sku": "PN-02", "quantity": 5 }
]
```

Ta có thể duyệt array rồi lấy từng trường của object:

```java
JsonNode items = root.path("items");

if (items.isArray()) {
    for (JsonNode item : items) {
        String sku = item.path("sku").asText();
        int quantity = item.path("quantity").asInt();

        System.out.println(sku + ": " + quantity);
    }
}
```

`JsonNode` triển khai cơ chế iterable cho các phần tử của container, nên enhanced for loop là cách viết gọn. Nếu muốn dùng iterator tường minh, hãy dùng `items.elements()`.

## 6. Duyệt object lồng nhau và array lồng nhau

Payload thực tế thường kết hợp object và array. Hãy kiểm tra kiểu node ở mỗi tầng trước khi đi sâu.

Với JSON đơn hàng ở đầu bài:

```java
JsonNode customer = root.path("customer");
if (customer.isObject()) {
    Iterator<Map.Entry<String, JsonNode>> customerFields = customer.fields();
    while (customerFields.hasNext()) {
        Map.Entry<String, JsonNode> field = customerFields.next();
        System.out.println("customer." + field.getKey() + " = " + field.getValue());
    }
}

JsonNode items = root.path("items");
if (items.isArray()) {
    for (JsonNode item : items) {
        if (item.isObject()) {
            String sku = item.path("sku").asText();
            int quantity = item.path("quantity").asInt();
            System.out.println(sku + " x " + quantity);
        }
    }
}
```

Trong đoạn code này:

1. `root.path("customer")` lấy object customer.
2. `fields()` duyệt từng cặp tên/value bên trong customer.
3. `root.path("items")` lấy array items.
4. Vòng lặp đi qua từng phần tử của array.
5. `item.path(...)` lấy thuộc tính trong từng object item.

Không nên giả định mọi phần tử trong array đều là object nếu hợp đồng JSON không bảo đảm điều đó. Nếu dữ liệu có thể chứa kiểu hỗn hợp, hãy kiểm tra `isObject()`, `isArray()` hoặc `isValueNode()` trước khi xử lý.

## 7. get(), path() và xử lý trường không tồn tại

Khi lấy một trường theo tên, `JsonNode` có hai phương thức thường dùng:

- `get("name")` trả về node nếu trường tồn tại; trả `null` nếu không có trường đó.
- `path("name")` trả về node tương ứng nếu tồn tại; nếu thiếu, trả `MissingNode` thay vì Java null.

Ví dụ:

```java
JsonNode emailWithGet = root.get("email");
if (emailWithGet == null) {
    System.out.println("Không có trường email");
}

JsonNode emailWithPath = root.path("email");
if (emailWithPath.isMissingNode()) {
    System.out.println("Không có trường email");
}
```

`path()` thuận tiện khi truy cập nhiều tầng vì có thể nối tiếp mà không phải kiểm tra null ở từng bước:

```java
String city = root.path("customer")
        .path("address")
        .path("city")
        .asText("Unknown");
```

Nếu `customer`, `address` hoặc `city` không tồn tại, `path()` trả về `MissingNode` cho phần thiếu. Tuy nhiên, cần phân biệt trường bị thiếu với trường hiện diện có giá trị JSON null:

```json
{
  "email": null
}
```

Với JSON này, `get("email")` trả về `NullNode`, không phải Java null. `path("email").isNull()` trả true; `path("missing").isMissingNode()` trả true.

| Trạng thái | `get("x")` | `path("x")` |
| --- | --- | --- |
| Trường không tồn tại | Java `null` | `MissingNode` |
| Trường tồn tại với JSON null | `NullNode` | `NullNode` |
| Trường có giá trị | Node tương ứng | Node tương ứng |

Sự khác biệt này quan trọng khi API cần phân biệt “không gửi trường” với “gửi null”.

## 8. Lấy phần tử array theo index

Array có thứ tự, vì vậy có thể truy cập trực tiếp bằng index:

```java
JsonNode items = root.path("items");

if (items.isArray() && items.size() > 0) {
    JsonNode firstItem = items.get(0);
    System.out.println(firstItem.path("sku").asText());
}
```

Hoặc dùng `path(index)` nếu muốn tránh Java null khi index không tồn tại:

```java
JsonNode firstItem = items.path(0);
if (firstItem.isMissingNode()) {
    System.out.println("Array không có phần tử đầu tiên");
}
```

Index bắt đầu từ 0. `size()` trả số phần tử trong array hoặc số field của object. Với array lớn, duyệt bằng iterator/enhanced for loop thường tự nhiên hơn việc gọi `get(i)` nhiều lần nếu không cần index.

## 9. Duyệt đệ quy mọi node trong cây JSON

Khi cấu trúc JSON không biết trước độ sâu, có thể viết hàm đệ quy. Quy tắc cơ bản:

- Nếu node là object, duyệt `fields()` rồi gọi lại hàm với từng value.
- Nếu node là array, duyệt `elements()` rồi gọi lại hàm với từng phần tử.
- Nếu node là value node hoặc null, xử lý giá trị và dừng nhánh đó.

Ví dụ in toàn bộ đường dẫn và giá trị:

```java
import com.fasterxml.jackson.databind.JsonNode;

import java.util.Iterator;
import java.util.Map;

public class JsonTreePrinter {
    public static void printTree(JsonNode node, String path) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            System.out.println(path + " = null/missing");
            return;
        }

        if (node.isObject()) {
            Iterator<Map.Entry<String, JsonNode>> fields = node.fields();
            while (fields.hasNext()) {
                Map.Entry<String, JsonNode> field = fields.next();
                String childPath = path.isEmpty()
                        ? field.getKey()
                        : path + "." + field.getKey();
                printTree(field.getValue(), childPath);
            }
            return;
        }

        if (node.isArray()) {
            for (int i = 0; i < node.size(); i++) {
                printTree(node.get(i), path + "[" + i + "]");
            }
            return;
        }

        System.out.println(path + " = " + node.asText());
    }
}
```

Với JSON đơn hàng, kết quả có thể có các đường dẫn như:

```text
id = ORD-1001
customer.name = An
customer.active = true
items[0].sku = BK-01
items[0].quantity = 2
items[1].sku = PN-02
items[1].quantity = 5
```

Đệ quy giúp xử lý cấu trúc tùy ý. Tuy nhiên, nếu JSON có độ sâu rất lớn, đệ quy có thể làm tăng độ sâu call stack. Với dữ liệu không tin cậy, nên giới hạn độ sâu JSON và cân nhắc duyệt bằng stack tường minh.

## 10. Dùng forEach khi chỉ cần xử lý nhanh

`JsonNode` cung cấp `forEach` để duyệt các phần tử con của container. Với array:

```java
JsonNode tags = root.path("tags");
if (tags.isArray()) {
    tags.forEach(tag -> System.out.println(tag.asText()));
}
```

Với object, `fields()` vẫn thường phù hợp hơn nếu cần tên trường. `forEach` trên object duyệt các giá trị con mà không cung cấp trực tiếp tên field trong callback. Nếu cần tên và value, hãy dùng `fields()`.

## 11. Chuyển node thành kiểu Java khi đọc giá trị

Sau khi lấy node, có thể dùng các phương thức chuyển đổi:

| Phương thức | Kiểu kết quả |
| --- | --- |
| `textValue()` | String nếu node là textual; không cố chuyển mọi kiểu thành chuỗi |
| `asText()` | Dạng chuỗi của node; với container thường không phải JSON đầy đủ |
| `intValue()` / `asInt()` | Số nguyên |
| `longValue()` / `asLong()` | Số nguyên dài |
| `decimalValue()` | `BigDecimal` cho node số phù hợp |
| `booleanValue()` / `asBoolean()` | Boolean |
| `numberValue()` | Giá trị thuộc nhóm `Number` |

Các phương thức `asXxx()` có thể trả giá trị mặc định khi node không phù hợp hoặc không chuyển được, tùy overload. Nếu cần phát hiện dữ liệu sai kiểu, hãy kiểm tra `isTextual()`, `isNumber()`, `isBoolean()` trước khi gọi phương thức lấy giá trị.

Ví dụ kiểm tra số:

```java
JsonNode quantityNode = item.get("quantity");

if (quantityNode != null && quantityNode.isIntegralNumber()) {
    int quantity = quantityNode.intValue();
} else {
    throw new IllegalArgumentException("quantity phải là số nguyên");
}
```

Nếu số có thể vượt phạm vi `int`, hãy kiểm tra kiểu và giới hạn phù hợp, rồi dùng `longValue()`, `bigIntegerValue()` hoặc `decimalValue()` tùy hợp đồng.

## 12. Truy cập nhanh bằng JsonPointer

Khi đã biết đường dẫn đến một node, `JsonPointer` cho phép truy cập bằng biểu thức JSON Pointer:

```java
JsonNode city = root.at("/customer/address/city");
JsonNode firstSku = root.at("/items/0/sku");
```

`at()` trả về `MissingNode` nếu đường dẫn không tồn tại. JSON Pointer thuận tiện khi cần lấy một giá trị ở đường dẫn đã biết; nó không thay thế việc duyệt `fields()` hoặc `elements()` khi cần xử lý toàn bộ object/array.

Tên field có ký tự `/` hoặc `~` phải được escape theo quy tắc JSON Pointer (`~1` cho `/`, `~0` cho `~`). Vì vậy, nếu tự tạo pointer từ tên field động, hãy escape đúng quy tắc.

## 13. Thực hành: tổng hợp số lượng từ array object

Giả sử JSON:

```json
{
  "orderId": "ORD-1001",
  "items": [
    { "sku": "BK-01", "quantity": 2 },
    { "sku": "PN-02", "quantity": 5 },
    { "sku": "ER-03", "quantity": 1 }
  ]
}
```

Ta muốn duyệt từng item và tính tổng số lượng:

```java
JsonNode items = root.path("items");

if (!items.isArray()) {
    throw new IllegalArgumentException("items phải là JSON array");
}

int totalQuantity = 0;

for (JsonNode item : items) {
    if (!item.isObject()) {
        throw new IllegalArgumentException("Mỗi item phải là JSON object");
    }

    JsonNode quantityNode = item.get("quantity");
    if (quantityNode == null || !quantityNode.isIntegralNumber()) {
        throw new IllegalArgumentException("quantity phải là số nguyên");
    }

    totalQuantity = Math.addExact(totalQuantity, quantityNode.intValue());
}

System.out.println(totalQuantity); // 8
```

Ví dụ này thể hiện cách kết hợp kiểm tra container, duyệt array, truy cập field và xác nhận kiểu dữ liệu. `Math.addExact()` giúp phát hiện overflow của `int` thay vì âm thầm tràn số.

## 14. Những lỗi thường gặp khi duyệt cây JSON

### 14.1. Gọi fields() trên array

`fields()` dành cho object. Nếu node hiện tại là array, hãy dùng `elements()` hoặc enhanced for loop.

### 14.2. Gọi elements() nhưng quên kiểm tra node

Trường lấy từ JSON có thể không tồn tại, là null hoặc có kiểu khác với mong đợi. Hãy kiểm tra node trước khi duyệt.

### 14.3. Nhầm MissingNode với NullNode

Trường thiếu và trường có giá trị JSON null là hai trạng thái khác nhau. `path()` giúp tránh null reference nhưng trả `MissingNode` khi không tìm thấy; `isNull()` và `isMissingNode()` trả lời hai câu hỏi riêng.

### 14.4. Dùng asText() cho object hoặc array

`asText()` không phải cách serialize một node container thành JSON. Nếu cần JSON text của node, dùng `ObjectMapper.writeValueAsString(node)` hoặc `node.toString()` theo mục đích phù hợp.

### 14.5. Giả định thứ tự field của object có ý nghĩa nghiệp vụ

Array có thứ tự phần tử. JSON object về mặt dữ liệu là tập hợp các cặp tên/value; không nên dựa vào thứ tự field để quyết định nghiệp vụ. Hãy truy cập theo tên field.

### 14.6. Giữ toàn bộ cây cho payload quá lớn

Tree Model giữ cấu trúc node trong bộ nhớ. Nếu payload rất lớn và chỉ cần xử lý tuần tự, cân nhắc Jackson Streaming API (`JsonParser`) để đọc token mà không phải tạo toàn bộ cây.

## 15. Chọn Tree Model hay Streaming API?

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| JSON nhỏ hoặc vừa, cần truy cập nhiều lần vào các node | Tree Model với `JsonNode` |
| Cấu trúc chưa cố định, cần duyệt field và array linh hoạt | Tree Model |
| Chỉ lấy một số trường đã biết từ payload lớn | Streaming parser có thể tiết kiệm bộ nhớ |
| Xử lý hàng triệu phần tử tuần tự | Streaming API thường phù hợp hơn |
| Cần ánh xạ payload ổn định vào DTO | Object binding với `ObjectMapper` |

Tree Model tạo trải nghiệm thao tác gần với cấu trúc JSON: object là node có tên trường, array là dãy node có thứ tự. Streaming API xử lý từng token và phù hợp với luồng lớn. Hãy chọn dựa trên kích thước dữ liệu, cách truy cập và lượng bộ nhớ có thể sử dụng.

## 16. Ghi nhớ

- Dùng `readTree()` để đọc JSON thành `JsonNode`.
- Dùng `isObject()` và `isArray()` để xác định loại container trước khi duyệt.
- Dùng `fields()` để duyệt cặp tên trường và node giá trị của object.
- Dùng `fieldNames()` nếu chỉ cần tên trường.
- Dùng `elements()` hoặc enhanced for loop để duyệt phần tử array theo thứ tự.
- Dùng `get()` khi chấp nhận kiểm tra Java null; dùng `path()` khi muốn nhận `MissingNode` thay vì Java null.
- Phân biệt `MissingNode` với `NullNode`; trường thiếu khác với trường có JSON null.
- Với cấu trúc lồng nhau, kiểm tra kiểu node ở mỗi tầng hoặc viết hàm đệ quy.
- Nếu payload lớn và cần xử lý tuần tự, cân nhắc Streaming API thay vì giữ toàn bộ Tree Model.

Khi làm việc với JSON động, hãy coi mỗi node là một giá trị có kiểu và kiểm tra trước khi duyệt. Object cần duyệt theo tên trường bằng `fields()`, array cần duyệt theo thứ tự bằng `elements()`. Kết hợp hai thao tác này cùng `path()`, `isObject()` và `isArray()` sẽ giúp xử lý an toàn các cấu trúc JSON lồng nhau.
