# Truy cập vị trí bằng JSON Pointer

Khi làm việc với JSON dưới dạng cây bằng Jackson, ta thường cần lấy một giá trị nằm sâu bên trong object hoặc array. Có thể gọi get() hoặc path() nhiều lần, nhưng với cấu trúc lồng nhau sâu, chuỗi lời gọi dài sẽ khó đọc và khó tái sử dụng.

**JSON Pointer** là một cú pháp chuẩn để mô tả đường dẫn đến một giá trị trong JSON document. Ví dụ, pointer /customer/address/city chỉ đến property city bên trong address của customer; pointer /orders/0/id chỉ đến id của phần tử đầu tiên trong array orders.

Jackson hỗ trợ JSON Pointer thông qua lớp JsonPointer và method JsonNode.at(). Hiểu cú pháp pointer, cách escape tên property và cách phân biệt node thiếu với JSON null giúp truy cập cây JSON chính xác hơn.

## 1. JSON Pointer là gì?

JSON Pointer được định nghĩa trong RFC 6901. Nó biểu diễn vị trí của một value trong JSON document bằng một chuỗi gồm các token được phân tách bởi dấu gạch chéo xuôi (/).

Ví dụ document:

~~~json
{
  "customer": {
    "id": "CUS-001",
    "name": "An",
    "address": {
      "city": "Ho Chi Minh City",
      "country": "Vietnam"
    }
  },
  "orders": [
    {
      "id": "ORD-100",
      "total": 250000
    },
    {
      "id": "ORD-101",
      "total": 180000
    }
  ]
}
~~~

Một số pointer tương ứng:

| JSON Pointer | Giá trị được truy cập |
|---|---|
| chuỗi rỗng | Toàn bộ JSON document ở root |
| /customer | Object customer |
| /customer/id | "CUS-001" |
| /customer/address/city | "Ho Chi Minh City" |
| /orders | Array orders |
| /orders/0 | Object order đầu tiên |
| /orders/0/id | "ORD-100" |
| /orders/1/total | 180000 |

Mỗi phần nằm giữa hai dấu / là một token. Jackson dùng token để đi từ node hiện tại sang property của object hoặc phần tử của array.

JSON Pointer chỉ xác định vị trí. Nó không tự thay đổi document và cũng không thực hiện truy vấn nâng cao như lọc phần tử theo điều kiện.

## 2. Cú pháp JSON Pointer

### 2.1. Pointer đến root

Pointer rỗng (empty string) đại diện cho toàn bộ JSON document:

~~~text
""
~~~

Ví dụ:

~~~java
JsonNode root = mapper.readTree(json);

JsonNode sameRoot = root.at("");
~~~

sameRoot chính là node root. Không nhầm pointer rỗng với chuỗi "/" nhé: "/" có nghĩa truy cập một property có tên rỗng ở root object.

### 2.2. Token được phân tách bằng dấu gạch chéo

Một pointer đến property lồng nhau:

~~~text
/customer/address/city
~~~

Có ba token:

1. customer
2. address
3. city

Jackson bắt đầu từ root, tìm property customer, đi vào object đó, tìm address rồi tìm city.

Pointer phải bắt đầu bằng dấu / nếu nó không phải pointer rỗng. Ví dụ /customer/id là hợp lệ; customer/id không phải biểu diễn JSON Pointer chuẩn.

### 2.3. Truy cập phần tử array

Khi node hiện tại là array, token tiếp theo được hiểu là chỉ số phần tử:

~~~json
{
  "languages": [
    "Java",
    "Kotlin",
    "Go"
  ]
}
~~~

Các pointer:

| Pointer | Kết quả |
|---|---|
| /languages/0 | "Java" |
| /languages/1 | "Kotlin" |
| /languages/2 | "Go" |

Chỉ số bắt đầu từ 0, giống index của array trong Java.

Token chỉ số array theo RFC 6901 có dạng số nguyên không âm ở dạng thập phân chuẩn:
- 0 là chỉ số hợp lệ.
- 1, 2, 10 là chỉ số hợp lệ.
- 01 không phải cách viết chỉ số chuẩn vì có số 0 ở đầu.
- -1 không phải chỉ số array hợp lệ.
- Chỉ số vượt quá phần tử cuối không trỏ đến một value tồn tại.

Một token có dạng số không phải lúc nào cũng là index. Nếu node hiện tại là JSON object và object có key "0", token 0 được hiểu là tên property. Cách diễn giải phụ thuộc kiểu node đang được duyệt.

### 2.4. Property có tên rỗng

Tên property rỗng là hợp lệ trong JSON:

~~~json
{
  "": "empty-name",
  "name": "An"
}
~~~

Pointer "/" trỏ đến property có tên rỗng:

~~~java
JsonNode value = root.at("/");
~~~

Trong khi pointer rỗng "" trỏ đến toàn bộ root. Đây là hai đường dẫn khác nhau.

## 3. Escape ký tự đặc biệt trong tên property

JSON Pointer dùng dấu / để phân tách token và dấu ~ để biểu diễn escape. Vì thế, khi tên property chứa hai ký tự này, không thể chèn trực tiếp vào pointer.

RFC 6901 quy định hai chuỗi escape:

| Ký tự trong tên property | Cách viết trong pointer |
|---|---|
| ~ | ~0 |
| / | ~1 |

Ví dụ object có các key đặc biệt:

~~~json
{
  "a/b": "slash-key",
  "a~b": "tilde-key",
  "path/name~type": "combined-key"
}
~~~

Các pointer tương ứng:

| Tên property | Pointer |
|---|---|
| a/b | /a~1b |
| a~b | /a~0b |
| path/name~type | /path~1name~0type |

### 3.1. Vì sao phải escape theo đúng thứ tự?

Khi tạo token từ tên property, hãy thay ~ thành ~0 trước, rồi thay / thành ~1:

~~~java
private static String escapePointerToken(String token) {
    return token
            .replace("~", "~0")
            .replace("/", "~1");
}
~~~

Nếu thay / trước, sau đó mới thay ~, ký tự ~ vừa tạo trong chuỗi ~1 cũng có thể bị escape lần nữa và tạo kết quả sai.

Khi giải mã, thứ tự ngược lại: thay ~1 thành / trước, rồi thay ~0 thành ~. Nhờ vậy, token ~01 được giải mã thành chuỗi ~1, không bị hiểu nhầm thành dấu /.

### 3.2. Tạo pointer từ tên property động

Không nên nối trực tiếp tên property từ dữ liệu đầu vào nếu tên đó có thể chứa / hoặc ~. Hãy escape token trước:

~~~java
private static String pointerForProperty(String propertyName) {
    return "/" + escapePointerToken(propertyName);
}
~~~

Sử dụng:

~~~java
String propertyName = "path/name~type";
String pointer = pointerForProperty(propertyName);

JsonNode value = root.at(pointer);
~~~

pointer được tạo là /path~1name~0type và trỏ đúng đến key path/name~type.

Với đường dẫn nhiều cấp, escape từng token riêng biệt rồi ghép bằng dấu /:

~~~java
String pointer = "/users/0/" + escapePointerToken(propertyName);
~~~

Không escape toàn bộ pointer một lần, vì như vậy dấu / phân tách token cũng bị biến đổi.

## 4. URI fragment representation

JSON Pointer có thể được biểu diễn dưới dạng URI fragment identifier bằng cách thêm dấu # ở đầu và percent-encode các ký tự theo quy tắc URI.

Ví dụ, pointer /customer/name có fragment representation:

~~~text
#/customer/name
~~~

Nếu tên property có ký tự cần percent-encode, fragment cần mã hóa phù hợp. Đây là lớp biểu diễn dành cho URI; nó không làm thay đổi quy tắc escape token ~0 và ~1 của JSON Pointer.

Khi dùng Jackson JsonNode.at() hoặc JsonPointer.compile(), hãy truyền biểu diễn JSON Pointer dạng thông thường, ví dụ /customer/name. Không truyền nguyên chuỗi fragment bắt đầu bằng # như thể nó là pointer path.

Nếu nhận pointer từ URL fragment, ứng dụng cần xử lý lớp URI fragment đúng cách trước khi biên dịch pointer: tách dấu # và percent-decode theo quy tắc URI, sau đó mới xử lý JSON Pointer. Không dùng cách decode form URL có quy tắc dấu + thành dấu cách cho URI fragment.

## 5. Truy cập JSON Pointer bằng Jackson

Jackson cung cấp lớp JsonPointer trong package com.fasterxml.jackson.core và hỗ trợ truy cập trực tiếp từ JsonNode.

### 5.1. Dùng JsonNode.at(String)

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "customer": {
            "id": "CUS-001",
            "address": {
              "city": "Ho Chi Minh City"
            }
          }
        }
        """;

JsonNode root = mapper.readTree(json);

JsonNode cityNode = root.at("/customer/address/city");

System.out.println(cityNode.asText());
~~~

Kết quả:

~~~text
Ho Chi Minh City
~~~

at(String) nhận chuỗi JSON Pointer, duyệt từ node hiện tại và trả về node ở vị trí được chỉ định. Nếu pointer trỏ đến object hoặc array, kết quả cũng là node tương ứng chứ không nhất thiết là scalar.

### 5.2. Dùng JsonPointer.compile()

Nếu cùng một pointer được dùng nhiều lần, có thể biên dịch trước thành đối tượng JsonPointer:

~~~java
JsonPointer cityPointer =
        JsonPointer.compile("/customer/address/city");

JsonNode first = root.at(cityPointer);
JsonNode second = anotherRoot.at(cityPointer);
~~~

JsonPointer biểu diễn đường dẫn đã được phân tích. Có thể tái sử dụng cùng pointer cho nhiều JSON tree có cấu trúc phù hợp.

Đây là cách hữu ích khi một ứng dụng có nhiều thao tác đọc lặp lại theo cùng đường dẫn, ví dụ đọc mã khách hàng hoặc trạng thái từ nhiều message.

### 5.3. Dùng nhiều pointer trên cùng một root

~~~java
JsonNode customerId = root.at("/customer/id");
JsonNode city = root.at("/customer/address/city");
JsonNode orderId = root.at("/orders/0/id");
~~~

Mỗi lời gọi trả về node tương ứng. Có thể chuyển node sang kiểu Java sau khi kiểm tra loại node:

~~~java
if (customerId.isTextual()) {
    String id = customerId.textValue();
}
~~~

Đối với số:

~~~java
JsonNode totalNode = root.at("/orders/0/total");

if (totalNode.isNumber()) {
    BigDecimal total = totalNode.decimalValue();
}
~~~

Không nên gọi asText(), asInt() rồi mặc nhiên cho rằng dữ liệu tồn tại và đúng kiểu. Hãy kiểm tra node phù hợp với yêu cầu trước khi chuyển đổi.

## 6. MissingNode khác NullNode

Đây là điểm quan trọng khi dùng at().

Nếu pointer không tìm thấy vị trí, JsonNode.at() trả về MissingNode, không trả về Java null. Nếu vị trí tồn tại và JSON ghi null, kết quả là NullNode.

Ví dụ:

~~~json
{
  "nickname": null
}
~~~

Hai truy vấn:

~~~java
JsonNode explicitNull = root.at("/nickname");
JsonNode missing = root.at("/email");

System.out.println(explicitNull.isNull());
System.out.println(missing.isMissingNode());
~~~

Kết quả:

~~~text
true
true
~~~

Có thể phân biệt:

| Trạng thái | Node trả về từ at() | Kiểm tra |
|---|---|---|
| Property không tồn tại | MissingNode | isMissingNode() |
| Property tồn tại với null | NullNode | isNull() |
| Property có string | TextNode | isTextual() |
| Property có số | NumericNode | isNumber() |
| Property có object | ObjectNode | isObject() |
| Property có array | ArrayNode | isArray() |

### 6.1. Kiểm tra an toàn trước khi lấy giá trị

~~~java
JsonNode nicknameNode = root.at("/nickname");

if (nicknameNode.isMissingNode()) {
    System.out.println("nickname was not provided");
} else if (nicknameNode.isNull()) {
    System.out.println("nickname was explicitly null");
} else if (nicknameNode.isTextual()) {
    System.out.println(nicknameNode.textValue());
} else {
    System.out.println("nickname has an unexpected JSON type");
}
~~~

Cách này đặc biệt quan trọng khi xử lý JSON từ API bên ngoài hoặc dữ liệu cập nhật từng phần. Nếu gộp MissingNode và NullNode thành một trạng thái, ứng dụng có thể vô tình xóa dữ liệu hoặc bỏ qua một yêu cầu xóa rõ ràng.

### 6.2. So sánh at(), get() và path()

Ba cách truy cập này có hành vi khác nhau:

| API | Cách truyền đường dẫn | Khi không tìm thấy |
|---|---|---|
| get(name) | Tên property hoặc index trực tiếp | Trả về Java null |
| path(name) | Tên property hoặc index trực tiếp | Trả về MissingNode |
| at(pointer) | JSON Pointer nhiều cấp | Trả về MissingNode |

Ví dụ:

~~~java
JsonNode customer = root.get("customer");
JsonNode cityByPath = root.path("customer").path("address").path("city");
JsonNode cityByPointer = root.at("/customer/address/city");
~~~

get() không hiểu chuỗi "/customer/address/city" là pointer. Nếu gọi root.get("/customer/address/city"), Jackson sẽ tìm một key có đúng tên đó ở root object.

path() tiện khi đi từng cấp và không muốn xử lý Java null sau mỗi lần gọi. at() tiện khi đã có một đường dẫn JSON Pointer hoàn chỉnh.

## 7. Truy cập array bằng pointer

Ví dụ JSON có danh sách đơn hàng:

~~~json
{
  "orders": [
    {"id": "ORD-100", "total": 250000},
    {"id": "ORD-101", "total": 180000},
    {"id": "ORD-102", "total": 320000}
  ]
}
~~~

Lấy phần tử đầu tiên:

~~~java
JsonNode firstOrder = root.at("/orders/0");
~~~

Lấy id của phần tử thứ hai:

~~~java
JsonNode secondOrderId = root.at("/orders/1/id");
~~~

Lấy total của phần tử thứ ba:

~~~java
JsonNode thirdTotal = root.at("/orders/2/total");
~~~

Nếu index vượt phạm vi array, kết quả là MissingNode:

~~~java
JsonNode missingOrder = root.at("/orders/10");

if (missingOrder.isMissingNode()) {
    System.out.println("Order index does not exist");
}
~~~

Không nên giả định index hợp lệ chỉ vì token là số. Dữ liệu array có thể ngắn hơn dự kiến, rỗng hoặc không tồn tại.

### 7.1. Token "-" không phải phần tử cuối đang tồn tại

Trong JSON Pointer, token "-" đại diện cho vị trí sau phần tử cuối của array, tức một vị trí không tồn tại. Quy tắc này được dùng trong ngữ cảnh thao tác add của JSON Patch (RFC 6902).

Vì vậy, không nên coi /orders/- là pointer để đọc phần tử cuối bằng JsonNode.at(). Nếu cần phần tử cuối, hãy kiểm tra node là array, lấy size rồi truy cập index size - 1 khi size lớn hơn 0.

~~~java
JsonNode orders = root.path("orders");

if (orders.isArray() && !orders.isEmpty()) {
    JsonNode lastOrder = orders.get(orders.size() - 1);
}
~~~

## 8. Tên property có dấu /, ~ hoặc ký tự Unicode

Tên khóa JSON có thể chứa nhiều ký tự, không chỉ chữ và số. JSON Pointer vẫn có thể truy cập chúng nếu token được escape đúng.

Ví dụ:

~~~json
{
  "customer/info": {
    "display~name": "An"
  },
  "thành_phố": "Đà Nẵng"
}
~~~

Pointer đến display~name:

~~~text
/customer~1info/display~0name
~~~

Pointer đến key có ký tự Unicode:

~~~text
/thành_phố
~~~

Jackson xử lý chuỗi Java Unicode bình thường. Với tên property chứa / và ~, cần escape theo quy tắc JSON Pointer; Unicode không có quy tắc escape token riêng ngoài cách biểu diễn chuỗi và URI fragment nếu dùng dạng fragment.

### 8.1. Hàm tạo pointer token an toàn

~~~java
public static String escapePointerToken(String token) {
    return token
            .replace("~", "~0")
            .replace("/", "~1");
}

public static String pointerOf(String... tokens) {
    StringBuilder pointer = new StringBuilder();

    for (String token : tokens) {
        pointer.append('/')
                .append(escapePointerToken(token));
    }

    return pointer.toString();
}
~~~

Sử dụng:

~~~java
String pointer = pointerOf(
        "customer/info",
        "display~name"
);

JsonNode value = root.at(pointer);
~~~

Kết quả pointer là /customer~1info/display~0name.

Hàm nhận từng token riêng biệt giúp tránh nhầm dấu / trong tên property với dấu / phân tách cấp của pointer.

## 9. JSON Pointer chỉ truy cập, không tự cập nhật cây JSON

JsonNode.at() là thao tác tìm kiếm. Nó không thay đổi node được trỏ tới.

Ví dụ:

~~~java
JsonNode city = root.at("/customer/address/city");
~~~

Lệnh trên chỉ lấy node city. Muốn cập nhật dữ liệu, cần thao tác trên ObjectNode hoặc ArrayNode sau khi xác định đúng node cha.

### 9.1. Cập nhật property của object

~~~java
JsonNode customerNode = root.path("customer");

if (!customerNode.isObject()) {
    throw new IllegalStateException("customer must be an object");
}

ObjectNode customerObject = (ObjectNode) customerNode;
JsonNode addressNode = customerObject.path("address");

if (!addressNode.isObject()) {
    throw new IllegalStateException("address must be an object");
}

ObjectNode addressObject = (ObjectNode) addressNode;
addressObject.put("city", "Da Nang");
~~~

Sau khi cập nhật, có thể ghi cây JSON thành chuỗi:

~~~java
String updatedJson = mapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(root);
~~~

Ở đây JSON Pointer giúp xác định đường dẫn cần làm việc; ObjectNode mới là API thực hiện thay đổi.

### 9.2. Cập nhật phần tử array

~~~java
JsonNode ordersNode = root.path("orders");

if (!ordersNode.isArray()) {
    throw new IllegalStateException("orders must be an array");
}

ArrayNode orders = (ArrayNode) ordersNode;

if (orders.size() > 1) {
    ObjectNode secondOrder = (ObjectNode) orders.get(1);
    secondOrder.put("total", 200000);
}
~~~

ArrayNode hỗ trợ các thao tác như add(), insert(), set() và remove(). Cần kiểm tra index và kiểu node trước khi cast hoặc cập nhật.

### 9.3. Nếu cần thao tác patch chuẩn

JSON Pointer thường được dùng làm giá trị path và from trong JSON Patch (RFC 6902). Nhưng JSON Pointer và JSON Patch là hai khái niệm khác nhau:

- JSON Pointer xác định vị trí.
- JSON Patch mô tả danh sách operation như add, remove, replace, move, copy và test.

Ví dụ một JSON Patch document:

~~~json
[
  {
    "op": "replace",
    "path": "/customer/address/city",
    "value": "Da Nang"
  },
  {
    "op": "remove",
    "path": "/orders/0"
  }
]
~~~

Các path trong operation là JSON Pointer. Bản thân Jackson Databind cung cấp JsonNode.at() để truy cập, nhưng không nên nhầm một lời gọi at() với việc thực thi đầy đủ JSON Patch. Nếu API công bố hỗ trợ application/json-patch+json, cần dùng implementation tương thích RFC 6902 hoặc tự thực thi đầy đủ semantics.

## 10. Kết hợp JSON Pointer với tree model

JSON Pointer đặc biệt hữu ích khi cấu trúc JSON động hoặc chưa có POJO tương ứng.

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree(json);

String[] pointers = {
        "/customer/id",
        "/customer/address/city",
        "/orders/0/id",
        "/orders/1/total"
};

for (String pointer : pointers) {
    JsonNode node = root.at(pointer);

    if (node.isMissingNode()) {
        System.out.println(pointer + " -> missing");
    } else if (node.isNull()) {
        System.out.println(pointer + " -> null");
    } else {
        System.out.println(pointer + " -> " + node);
    }
}
~~~

Cách làm này phù hợp với:
- Đọc một vài trường từ JSON có cấu trúc lồng nhau.
- Xử lý message có schema thay đổi theo loại sự kiện.
- Trích xuất dữ liệu để logging hoặc mapping sang model khác.
- Kiểm tra sự hiện diện của property trước khi cập nhật.
- Viết công cụ debug hoặc kiểm tra payload.

Nếu schema đã biết và ổn định, data binding vào POJO có thể rõ ràng và an toàn kiểu hơn. Tree model cùng JSON Pointer phù hợp khi cần truy cập linh hoạt theo đường dẫn.

## 11. Xử lý pointer không hợp lệ và dữ liệu đầu vào

### 11.1. Kiểm tra cú pháp trước khi dùng

Có thể biên dịch pointer rõ ràng:

~~~java
JsonPointer pointer = JsonPointer.compile("/customer/address/city");
JsonNode city = root.at(pointer);
~~~

Một pointer sai cú pháp, chẳng hạn escape token dùng dấu ~ không theo sau bởi 0 hoặc 1, có thể bị từ chối khi compile. Nếu pointer do người dùng gửi lên, hãy xử lý IllegalArgumentException và trả lỗi đầu vào phù hợp.

Ví dụ:

~~~java
try {
    JsonPointer pointer = JsonPointer.compile(userSuppliedPointer);
    JsonNode value = root.at(pointer);
} catch (IllegalArgumentException e) {
    throw new IllegalArgumentException("Invalid JSON Pointer", e);
}
~~~

Cần phân biệt:
- Pointer sai cú pháp: không biên dịch được.
- Pointer hợp lệ nhưng không khớp document: at() trả về MissingNode.
- Pointer trỏ đến JSON null: trả về NullNode.

Ba trường hợp này có ý nghĩa khác nhau và nên được xử lý riêng nếu ứng dụng cần thông báo chính xác.

### 11.2. Pointer không phải cơ chế phân quyền

Nếu API cho phép client gửi pointer tùy ý, pointer có thể trỏ đến bất kỳ property nào trong cây JSON được cung cấp. JSON Pointer chỉ là cú pháp truy cập; nó không kiểm tra quyền đọc hoặc sửa dữ liệu.

Với dữ liệu nhạy cảm, hãy giới hạn pointer theo allowlist hoặc kiểm tra quyền trên từng trường. Không cho phép client tự do chọn đường dẫn đến field nội bộ rồi coi đó là cơ chế an toàn.

### 11.3. Không nhầm JSON Pointer với JSONPath

JSON Pointer chỉ định một đường dẫn cụ thể bằng các token. Nó không hỗ trợ wildcard, điều kiện lọc, đệ quy hay chọn nhiều node.

Ví dụ:
- JSON Pointer /orders/0/id trỏ đến id của order đầu tiên.
- Một biểu thức JSONPath có thể chọn id của mọi order hoặc lọc order theo total.

Nếu yêu cầu là truy vấn nhiều phần tử theo điều kiện, JSONPath phù hợp hơn. Đừng cố dùng JSON Pointer cho truy vấn mà nó không được thiết kế để giải quyết.

## 12. Ví dụ tổng hợp

Ví dụ dưới đây đọc JSON, dùng nhiều pointer để truy cập dữ liệu, phân biệt missing với null, rồi cập nhật một property bằng ObjectNode.

~~~java
import com.fasterxml.jackson.core.JsonPointer;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public class JsonPointerDemo {

    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "customer": {
                    "id": "CUS-001",
                    "nickname": null,
                    "address": {
                      "city": "Ho Chi Minh City"
                    }
                  },
                  "orders": [
                    {"id": "ORD-100", "total": 250000},
                    {"id": "ORD-101", "total": 180000}
                  ]
                }
                """;

        ObjectMapper mapper = new ObjectMapper();
        JsonNode root = mapper.readTree(json);

        // Biên dịch pointer và truy cập node.
        JsonPointer cityPointer =
                JsonPointer.compile("/customer/address/city");

        JsonNode cityNode = root.at(cityPointer);
        System.out.println(cityNode.asText());

        // Phân biệt explicit null và missing.
        JsonNode nicknameNode = root.at("/customer/nickname");
        JsonNode emailNode = root.at("/customer/email");

        System.out.println(nicknameNode.isNull());
        System.out.println(emailNode.isMissingNode());

        // Truy cập phần tử array.
        JsonNode firstOrderId = root.at("/orders/0/id");
        System.out.println(firstOrderId.asText());

        // Cập nhật cây bằng ObjectNode.
        JsonNode customerNode = root.path("customer");
        if (!customerNode.isObject()) {
            throw new IllegalStateException("customer must be an object");
        }

        ObjectNode customer = (ObjectNode) customerNode;
        JsonNode addressNode = customer.path("address");

        if (!addressNode.isObject()) {
            throw new IllegalStateException("address must be an object");
        }

        ((ObjectNode) addressNode).put("city", "Da Nang");

        String updatedJson = mapper
                .writerWithDefaultPrettyPrinter()
                .writeValueAsString(root);

        System.out.println(updatedJson);
    }
}
~~~

Trong ví dụ:
1. JsonPointer.compile() phân tích đường dẫn thành đối tượng pointer.
2. root.at(pointer) lấy node theo đường dẫn.
3. isNull() nhận diện JSON null tường minh.
4. isMissingNode() nhận diện đường dẫn không tồn tại.
5. Pointer /orders/0/id truy cập phần tử array bằng index.
6. ObjectNode.put() thực hiện cập nhật dữ liệu.
7. ObjectMapper ghi cây JSON sau khi cập nhật.

## 13. Những điểm cần nhớ

- JSON Pointer là cú pháp chuẩn theo RFC 6901 để xác định một vị trí trong JSON document.
- Pointer rỗng "" trỏ đến root; pointer "/" trỏ đến property có tên rỗng.
- Mỗi token được phân tách bằng dấu /.
- Trong tên property, ~ được escape thành ~0 và / thành ~1.
- Token số chỉ là array index khi node hiện tại là array; trong object, nó có thể là tên key.
- Array index bắt đầu từ 0; token index có số 0 ở đầu như 01 không phải dạng chuẩn.
- JsonNode.at() nhận pointer và trả về MissingNode khi không tìm thấy đường dẫn.
- NullNode biểu diễn JSON null tường minh; MissingNode biểu diễn vị trí không tồn tại.
- get() và path() không nhận chuỗi JSON Pointer nhiều cấp; at() mới là API dành cho pointer.
- at() chỉ truy cập; cập nhật cần ObjectNode, ArrayNode hoặc cơ chế JSON Patch.
- JSON Pointer không phải JSONPath và cũng không phải JSON Patch.
- Pointer do người dùng cung cấp cần được kiểm tra cú pháp và giới hạn quyền truy cập theo yêu cầu ứng dụng.

Khi làm việc với tree model của Jackson, JSON Pointer giúp truy cập node lồng nhau bằng một đường dẫn ngắn gọn, có thể tái sử dụng và tuân theo chuẩn. Nắm vững cú pháp token, escape và khác biệt giữa MissingNode với NullNode sẽ giúp xử lý JSON động và các thao tác cập nhật chính xác hơn.
