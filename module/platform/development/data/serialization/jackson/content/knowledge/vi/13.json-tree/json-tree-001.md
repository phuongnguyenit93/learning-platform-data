# Vai trò của JsonNode, ObjectNode và ArrayNode

Jackson Databind không chỉ ánh xạ JSON trực tiếp vào class Java. Khi cấu trúc đầu vào chưa biết trước, có nhiều trường động hoặc cần kiểm tra và chỉnh sửa JSON trước khi tạo DTO, ứng dụng có thể dùng **tree model** của Jackson.

Trong tree model, mỗi giá trị JSON được biểu diễn bằng một node. Kiểu nền tảng là JsonNode; ObjectNode biểu diễn JSON object, còn ArrayNode biểu diễn JSON array. Các node có thể chứa node con, tạo thành cây phản ánh cấu trúc lồng nhau của tài liệu JSON.

Tree model phù hợp khi ứng dụng cần duyệt, tìm, thêm, sửa, xóa hoặc chuyển đổi từng phần của JSON. Nó cũng hữu ích khi API nhận payload có cấu trúc không hoàn toàn cố định. Hiểu vai trò của ba kiểu node này giúp chọn đúng công cụ cho từng thao tác.

## 1. Tree model trong Jackson là gì?

Một JSON document có thể gồm object, array hoặc một giá trị đơn ở root. Ví dụ:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "CUS-17",
    "displayName": "Linh"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    },
    {
      "sku": "PEN-02",
      "quantity": 3
    }
  ],
  "paid": true
}
~~~

Jackson có thể biểu diễn nội dung này thành một cây:

~~~text
JsonNode (root)
  |
  +-- ObjectNode
       |
       +-- orderId: TextNode
       |
       +-- customer: ObjectNode
       |     |
       |     +-- id: TextNode
       |     +-- displayName: TextNode
       |
       +-- items: ArrayNode
       |     |
       |     +-- ObjectNode
       |     |     +-- sku: TextNode
       |     |     +-- quantity: IntNode
       |     |
       |     +-- ObjectNode
       |           +-- sku: TextNode
       |           +-- quantity: IntNode
       |
       +-- paid: BooleanNode
~~~

Mỗi node biểu diễn một giá trị JSON. Các node con được nối với node cha theo tên thuộc tính hoặc vị trí phần tử trong array.

Tree model có ba nhóm node thường gặp:

- **JsonNode** là kiểu cơ sở để làm việc với mọi giá trị JSON. Một biến JsonNode có thể đang tham chiếu đến object, array, string, number, boolean hoặc null.
- **ObjectNode** là node container đại diện cho JSON object, chứa các cặp tên thuộc tính và node giá trị.
- **ArrayNode** là node container đại diện cho JSON array, chứa các node theo thứ tự.

Ngoài ra còn có các node giá trị như TextNode, NumericNode, BooleanNode, NullNode và MissingNode. Thông thường, ứng dụng thao tác qua API của JsonNode và chỉ ép kiểu sang ObjectNode hoặc ArrayNode sau khi đã xác nhận đúng loại.

## 2. Đọc JSON thành JsonNode

Cách đơn giản nhất để tạo cây là dùng ObjectMapper.readTree:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "orderId": "ORD-100",
      "quantity": 2,
      "paid": true
    }
    """;

JsonNode root = mapper.readTree(json);
~~~

Biến root có kiểu JsonNode. Nếu JSON root là object, node thực tế thường là ObjectNode. Nếu root là array, node thực tế là ArrayNode. Root cũng có thể là string, number, boolean hoặc null theo cú pháp JSON.

Có thể đọc từ các nguồn khác nhau:

~~~java
JsonNode fromString = mapper.readTree(json);
JsonNode fromBytes = mapper.readTree(jsonBytes);
JsonNode fromStream = mapper.readTree(inputStream);
~~~

Tree model không yêu cầu root phải là object. Vì vậy, trước khi truy cập thuộc tính, nên kiểm tra hình dạng:

~~~java
if (root == null || !root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}

ObjectNode object = (ObjectNode) root;
~~~

Với dữ liệu từ hệ thống bên ngoài, không nên ép kiểu trực tiếp mà chưa kiểm tra. Nếu root thực tế là array hoặc scalar, ép sang ObjectNode sẽ gây ClassCastException.

Đọc tree đặc biệt hữu ích khi cấu trúc đầu vào chỉ được biết một phần. Ví dụ, API có một số trường cố định nhưng phần metadata do từng đối tác tự định nghĩa. Ứng dụng có thể đọc toàn bộ thành JsonNode, kiểm tra các trường quan trọng rồi chỉ chuyển phần đã biết sang DTO.

## 3. JsonNode cung cấp API chung để kiểm tra và truy cập

JsonNode có các phương thức kiểm tra loại node:

| Phương thức | Ý nghĩa |
|---|---|
| isObject() | Node đại diện cho JSON object. |
| isArray() | Node đại diện cho JSON array. |
| isTextual() | Node là chuỗi JSON. |
| isNumber() | Node là số JSON. |
| isIntegralNumber() | Node số có kiểu nguyên. |
| isFloatingPointNumber() | Node số có kiểu dấu phẩy động. |
| isBoolean() | Node là boolean. |
| isNull() | Node là JSON null. |
| isMissingNode() | Node đại diện cho đường dẫn hoặc thuộc tính không tồn tại. |

Ví dụ:

~~~java
JsonNode quantityNode = root.get("quantity");

if (quantityNode == null) {
    throw new IllegalArgumentException("Missing quantity");
}

if (!quantityNode.isIntegralNumber()) {
    throw new IllegalArgumentException("quantity must be an integer");
}

if (!quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("quantity is outside int range");
}

int quantity = quantityNode.intValue();
~~~

Kiểm tra loại và phạm vi trước khi chuyển đổi giúp tránh chấp nhận nhầm dữ liệu. Nếu chỉ gọi asInt(), Jackson có thể thực hiện coercion hoặc trả về giá trị mặc định cho node không phù hợp. Điều đó tiện cho đọc dữ liệu linh hoạt, nhưng không phù hợp để xác thực hợp đồng nghiêm ngặt.

Các phương thức chuyển đổi thường dùng:

- textValue() lấy nội dung chuỗi từ TextNode; nên kiểm tra isTextual() trước.
- intValue(), longValue(), bigIntegerValue() và decimalValue() lấy giá trị từ node số phù hợp.
- asText(), asInt(), asLong() và asBoolean() cung cấp cách chuyển đổi tiện lợi hơn, nhưng có thể áp dụng coercion hoặc giá trị fallback.
- asInt(defaultValue) cho phép chỉ định giá trị dự phòng nếu node không chuyển đổi được theo quy tắc của API.

Ví dụ đọc số thập phân:

~~~java
JsonNode priceNode = root.path("unitPrice");

if (!priceNode.isNumber()) {
    throw new IllegalArgumentException("unitPrice must be a number");
}

BigDecimal price = priceNode.decimalValue();
~~~

Nếu hợp đồng yêu cầu kiểu số nguyên, hãy dùng isIntegralNumber() và kiểm tra phạm vi thay vì chỉ kiểm tra isNumber(). Một giá trị 2.0 là number nhưng không phải token số nguyên.

## 4. Phân biệt get(), path(), has() và hasNonNull()

Khi truy cập một thuộc tính object, cần phân biệt property không tồn tại với property có giá trị JSON null.

Giả sử root là:

~~~json
{
  "nickname": null,
  "age": 18
}
~~~

Jackson cung cấp hai cách truy cập phổ biến:

~~~java
JsonNode missing = root.get("unknown");
JsonNode explicitNull = root.get("nickname");

JsonNode missingByPath = root.path("unknown");
JsonNode nullByPath = root.path("nickname");
~~~

Kết quả:

- get("unknown") trả về null của Java vì thuộc tính không tồn tại.
- get("nickname") trả về NullNode vì thuộc tính có mặt và giá trị JSON là null.
- path("unknown") trả về MissingNode thay vì null của Java.
- path("nickname") trả về NullNode.

Các phương thức kiểm tra:

| Phương thức | Property không tồn tại | Property có JSON null | Property có giá trị |
|---|---:|---:|---:|
| has(name) | false | true | true |
| hasNonNull(name) | false | false | true |
| get(name) == null | true | false | false |
| path(name).isMissingNode() | true | false | false |
| path(name).isNull() | false | true | false |

Ví dụ xử lý ba trạng thái:

~~~java
JsonNode nickname = root.path("nickname");

if (nickname.isMissingNode()) {
    // Client không gửi nickname.
} else if (nickname.isNull()) {
    // Client gửi nickname với giá trị null.
} else if (nickname.isTextual() && nickname.textValue().isEmpty()) {
    // Client gửi chuỗi rỗng.
} else {
    // Client gửi một giá trị khác.
}
~~~

Đây là cách quan trọng khi xử lý PATCH hoặc request cập nhật từng phần. Một DTO nullable thông thường có thể làm mất khác biệt giữa thuộc tính thiếu và explicit null, trong khi tree model vẫn giữ được thông tin đó.

Lưu ý: path() trả về node để tiếp tục truy cập an toàn qua các cấp. Nếu một node trung gian không tồn tại, kết quả tiếp theo vẫn là MissingNode thay vì phát sinh NullPointerException.

## 5. ObjectNode đại diện cho JSON object

ObjectNode là node container chứa các thuộc tính có tên. Có thể tạo ObjectNode bằng mapper:

~~~java
ObjectNode object = mapper.createObjectNode();
~~~

Hoặc lấy node object con từ một cây đã đọc:

~~~java
JsonNode customerNode = root.path("customer");

if (!customerNode.isObject()) {
    throw new IllegalArgumentException("customer must be an object");
}

ObjectNode customer = (ObjectNode) customerNode;
~~~

Các phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| put(name, value) | Thêm hoặc thay giá trị primitive/String. |
| putNull(name) | Gán thuộc tính bằng JSON null. |
| set(name, node) | Gắn một node con vào thuộc tính. |
| replace(name, node) | Thay node của thuộc tính và trả về node cũ. |
| putObject(name) | Tạo object con và gắn vào thuộc tính. |
| putArray(name) | Tạo array con và gắn vào thuộc tính. |
| get(name) | Lấy node theo tên thuộc tính. |
| remove(name) | Xóa một thuộc tính. |
| removeAll() | Xóa toàn bộ thuộc tính. |
| fields() | Duyệt các cặp tên và node giá trị. |
| fieldNames() | Duyệt tên thuộc tính. |

Ví dụ xây dựng object:

~~~java
ObjectNode order = mapper.createObjectNode();

order.put("orderId", "ORD-100");
order.put("quantity", 2);
order.put("paid", true);
order.putNull("note");

ObjectNode customer = order.putObject("customer");
customer.put("id", "CUS-17");
customer.put("displayName", "Linh");

String json = mapper.writeValueAsString(order);
~~~

put() phù hợp với giá trị Java đơn giản. set() dùng khi giá trị đã là JsonNode:

~~~java
ObjectNode metadata = mapper.createObjectNode();
metadata.put("source", "partner-api");
metadata.put("priority", 3);

order.set("metadata", metadata);
~~~

Nếu muốn thay đổi một thuộc tính, put() hoặc set() sẽ thay giá trị cũ cùng tên. Nếu muốn xóa, dùng remove():

~~~java
order.remove("note");
~~~

Không nên truyền Java null vào set() để biểu diễn JSON null. Dùng putNull() hoặc NullNode.instance để thể hiện rõ ý định.

## 6. ArrayNode đại diện cho JSON array

ArrayNode là node container giữ một danh sách node theo thứ tự. Tạo array mới:

~~~java
ArrayNode tags = mapper.createArrayNode();

tags.add("java");
tags.add("jackson");
tags.add("serialization");
tags.addNull();
~~~

Có thể gắn array vào ObjectNode:

~~~java
ObjectNode profile = mapper.createObjectNode();
profile.put("userId", "U-100");
profile.set("tags", tags);
~~~

Một số phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| add(value) | Thêm giá trị vào cuối array. |
| add(node) | Thêm node vào cuối array. |
| addNull() | Thêm phần tử JSON null. |
| addObject() | Tạo và thêm một object con. |
| addArray() | Tạo và thêm một array con. |
| insert(index, value) | Chèn phần tử tại vị trí chỉ định. |
| set(index, node) | Thay phần tử tại vị trí đã có. |
| get(index) | Lấy phần tử theo chỉ số. |
| remove(index) | Xóa phần tử tại vị trí. |
| removeAll() | Xóa mọi phần tử. |
| elements() | Duyệt các phần tử. |
| size() | Số phần tử hiện tại. |

Ví dụ tạo array object:

~~~java
ArrayNode items = mapper.createArrayNode();

ObjectNode first = items.addObject();
first.put("sku", "BOOK-01");
first.put("quantity", 2);

ObjectNode second = items.addObject();
second.put("sku", "PEN-02");
second.put("quantity", 3);

ObjectNode order = mapper.createObjectNode();
order.put("orderId", "ORD-100");
order.set("items", items);
~~~

Có thể thay hoặc xóa phần tử:

~~~java
items.set(0, mapper.createObjectNode().put("sku", "BOOK-NEW"));
items.remove(1);
~~~

Chỉ số array bắt đầu từ 0. Trước khi truy cập một index đến từ dữ liệu bên ngoài, hãy kiểm tra node là array và index nằm trong phạm vi.

Khác với ObjectNode, thứ tự phần tử ArrayNode là một phần của cấu trúc dữ liệu. Thay đổi thứ tự có thể làm thay đổi ý nghĩa JSON nếu hợp đồng quy định vị trí phần tử.

## 7. Duyệt thuộc tính và phần tử trong cây

Với ObjectNode, có thể duyệt tên và giá trị:

~~~java
Iterator<Map.Entry<String, JsonNode>> fields = object.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> entry = fields.next();

    String name = entry.getKey();
    JsonNode value = entry.getValue();

    System.out.println(name + " = " + value);
}
~~~

Nếu chỉ cần tên:

~~~java
Iterator<String> names = object.fieldNames();

while (names.hasNext()) {
    String name = names.next();
    System.out.println(name);
}
~~~

Với ArrayNode:

~~~java
for (JsonNode item : items) {
    String sku = item.path("sku").asText();
    int quantity = item.path("quantity").asInt();

    System.out.println(sku + ": " + quantity);
}
~~~

Nếu dữ liệu không đáng tin cậy, không nên dùng asText() hoặc asInt() mà không kiểm tra loại node. Ví dụ:

~~~java
for (JsonNode item : items) {
    JsonNode skuNode = item.path("sku");
    JsonNode quantityNode = item.path("quantity");

    if (!item.isObject()
            || !skuNode.isTextual()
            || !quantityNode.isIntegralNumber()
            || !quantityNode.canConvertToInt()) {
        throw new IllegalArgumentException("Invalid order item");
    }

    String sku = skuNode.textValue();
    int quantity = quantityNode.intValue();
}
~~~

Đoạn code trên minh họa kiểm tra cấu trúc trước khi sử dụng giá trị. Trong ứng dụng thực tế, nên tạo exception hoặc lỗi validation có thông tin field cụ thể để client dễ sửa request.

## 8. Truy cập sâu bằng JsonPointer

Khi cây có nhiều cấp lồng nhau, việc gọi path() liên tiếp có thể dài. Jackson hỗ trợ JSON Pointer để truy cập một node theo đường dẫn.

Ví dụ:

~~~json
{
  "customer": {
    "address": {
      "city": "Ho Chi Minh City"
    }
  },
  "items": [
    {
      "sku": "BOOK-01"
    }
  ]
}
~~~

Truy cập city:

~~~java
JsonNode city = root.at("/customer/address/city");
~~~

Truy cập SKU của phần tử đầu tiên:

~~~java
JsonNode sku = root.at("/items/0/sku");
~~~

JsonPointer bắt đầu bằng dấu slash. Mỗi segment đại diện cho một tên thuộc tính hoặc chỉ số array.

Ký tự đặc biệt trong tên thuộc tính cần escape:

- ~ được viết thành ~0.
- / được viết thành ~1.

Ví dụ, tên field a/b được truy cập bằng pointer /a~1b.

Có thể biên dịch pointer để tái sử dụng:

~~~java
JsonPointer cityPointer =
    JsonPointer.compile("/customer/address/city");

JsonNode city = root.at(cityPointer);
~~~

Nếu đường dẫn không tồn tại, at() trả về MissingNode. Hãy kiểm tra isMissingNode() trước khi sử dụng giá trị:

~~~java
JsonNode city = root.at("/customer/address/city");

if (city.isMissingNode() || city.isNull()) {
    throw new IllegalArgumentException("Customer city is required");
}
~~~

JsonPointer chỉ tìm node theo cấu trúc. Nó không xác nhận kiểu hoặc ý nghĩa nghiệp vụ của node đó.

## 9. Chuyển đổi giữa JsonNode và object Java

Tree model có thể kết hợp với databinding. Ứng dụng không cần chọn một cách làm duy nhất cho toàn bộ payload.

### Chuyển POJO thành cây bằng valueToTree

~~~java
public record Customer(String id, String displayName) {}

Customer customer = new Customer("CUS-17", "Linh");

JsonNode customerTree = mapper.valueToTree(customer);
~~~

valueToTree dùng cơ chế serialization của mapper để tạo biểu diễn tree tương ứng với object Java. Các module, annotation và serializer đã cấu hình có thể ảnh hưởng đến kết quả.

### Chuyển cây thành POJO bằng treeToValue

~~~java
Customer restored =
    mapper.treeToValue(customerTree, Customer.class);
~~~

treeToValue phù hợp khi đã có một JsonNode và muốn ánh xạ nó sang một kiểu Java xác định.

### Dùng convertValue cho chuyển đổi tổng quát

~~~java
Customer restored = mapper.convertValue(
    customerTree,
    Customer.class
);
~~~

convertValue hỗ trợ chuyển đổi giữa nhiều dạng object có thể ánh xạ qua Jackson, chẳng hạn POJO, Map và tree node. Khi mục đích cụ thể là chuyển tree thành DTO, treeToValue thường thể hiện ý định rõ hơn.

Với kiểu generic, cung cấp đầy đủ kiểu đích:

~~~java
List<Customer> customers = mapper.convertValue(
    root.path("customers"),
    new TypeReference<List<Customer>>() {}
);
~~~

Nếu chỉ dùng List.class, thông tin kiểu Customer của phần tử không được thể hiện đầy đủ.

Trước khi chuyển tree thành DTO, nên xác nhận node có đúng hình dạng và các trường cần thiết. Việc convert thành công không thay thế validation nghiệp vụ.

## 10. Ví dụ kết hợp: kiểm tra JSON động rồi tạo DTO

Giả sử hệ thống nhận đơn hàng có các trường cơ bản cố định, nhưng có thể có metadata tùy đối tác:

~~~json
{
  "orderId": "ORD-100",
  "quantity": 2,
  "metadata": {
    "source": "partner-a",
    "campaign": "winter"
  }
}
~~~

Có thể đọc cây trước, kiểm tra các trường quan trọng, rồi chuyển thành DTO:

~~~java
public record OrderRequest(
    String orderId,
    int quantity
) {}

JsonNode root = mapper.readTree(json);

if (!root.isObject()) {
    throw new IllegalArgumentException("Request must be a JSON object");
}

JsonNode orderIdNode = root.path("orderId");
JsonNode quantityNode = root.path("quantity");

if (!orderIdNode.isTextual()) {
    throw new IllegalArgumentException("orderId must be a string");
}

if (!quantityNode.isIntegralNumber()
        || !quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("quantity must be an integer");
}

OrderRequest request =
    mapper.treeToValue(root, OrderRequest.class);

JsonNode metadata = root.path("metadata");

if (metadata.isObject()) {
    String source = metadata.path("source").asText(null);
    // Xử lý metadata theo quy tắc của đối tác.
}
~~~

Ví dụ này dùng tree model để kiểm tra trường động và kiểu dữ liệu, còn DTO giữ các trường nghiệp vụ ổn định. Nếu ứng dụng cần từ chối thuộc tính lạ ngoài metadata, hãy kiểm tra danh sách field cho phép hoặc dùng cấu hình databinding phù hợp sau khi xác định rõ hợp đồng.

Một cách khác là lấy riêng subtree metadata và lưu nó dưới dạng JsonNode trong DTO:

~~~java
public record OrderEnvelope(
    String orderId,
    int quantity,
    JsonNode metadata
) {}
~~~

Cách này giữ metadata ở dạng cây, cho phép xử lý linh hoạt mà không cần tạo class Java cho mọi cấu trúc đối tác.

## 11. Sửa đổi cây JSON

ObjectNode và ArrayNode là container có thể thay đổi. Điều này làm tree model phù hợp cho việc biến đổi JSON trước khi gửi tiếp hoặc ghi file.

Ví dụ thêm trường:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(json);

root.put("processed", true);
root.put("processedAt", Instant.now().toString());
~~~

Thay trường:

~~~java
root.put("status", "confirmed");
~~~

Xóa trường:

~~~java
root.remove("internalNote");
~~~

Thêm phần tử vào array:

~~~java
JsonNode itemsNode = root.path("items");

if (itemsNode.isArray()) {
    ArrayNode items = (ArrayNode) itemsNode;
    items.addObject().put("sku", "EXTRA-01");
}
~~~

Tạo một cây mới từ dữ liệu hiện có:

~~~java
ObjectNode response = mapper.createObjectNode();
response.put("success", true);
response.set("data", root);
~~~

Sau khi thay đổi, serialize lại:

~~~java
String output = mapper.writerWithDefaultPrettyPrinter()
    .writeValueAsString(response);
~~~

Thao tác trên tree không thay đổi chuỗi JSON gốc đã đọc; nó thay đổi các node trong bộ nhớ. Chỉ khi serialize cây đã sửa, ứng dụng mới tạo ra JSON output mới.

## 12. Sao chép cây và tránh chia sẻ node mutable ngoài ý muốn

ObjectNode và ArrayNode là các container mutable. Nếu hai biến cùng tham chiếu đến một node container, thay đổi qua một biến cũng được nhìn thấy qua biến còn lại.

Ví dụ:

~~~java
ObjectNode original = mapper.createObjectNode();
original.put("status", "new");

ObjectNode alias = original;
alias.put("status", "changed");

// original cũng nhìn thấy status = changed.
~~~

Nếu cần một bản sao độc lập trước khi chỉnh sửa, dùng deepCopy():

~~~java
ObjectNode copy = original.deepCopy();

copy.put("status", "changed");
~~~

deepCopy tạo bản sao đệ quy cho các container con. Các node giá trị bất biến có thể được tái sử dụng an toàn.

Khi gắn một subtree vào nhiều cấu trúc, hãy cân nhắc việc hai nơi cùng tham chiếu đến một node mutable. Nếu một nơi sửa subtree, nơi kia có thể quan sát thay đổi. Dùng deepCopy khi cần hai nhánh dữ liệu độc lập.

ObjectMapper có thể được chia sẻ sau khi cấu hình hoàn tất, nhưng không nên mặc định coi mọi cây JsonNode là immutable. Nếu một cây được nhiều luồng sử dụng, hãy tránh sửa đổi đồng thời hoặc tạo bản sao riêng cho mỗi luồng.

## 13. Ghi JSON từ tree node

JsonNode có thể được ghi trực tiếp bằng ObjectMapper hoặc ObjectWriter:

~~~java
String compactJson = mapper.writeValueAsString(root);

String prettyJson = mapper.writerWithDefaultPrettyPrinter()
    .writeValueAsString(root);
~~~

Jackson ghi node theo loại thực tế:

- ObjectNode được ghi thành JSON object.
- ArrayNode được ghi thành JSON array.
- TextNode được ghi thành JSON string.
- NumericNode được ghi thành JSON number.
- BooleanNode được ghi thành true hoặc false.
- NullNode được ghi thành null.

Tree model giúp chỉnh sửa nội dung mà không cần tự nối chuỗi JSON. Không nên tạo JSON bằng cách ghép chuỗi thủ công vì dễ sai dấu ngoặc, dấu phẩy, escape ký tự và kiểu dữ liệu.

Thứ tự field của object có thể được giữ theo cấu trúc nội bộ và cấu hình, nhưng hợp đồng JSON không nên phụ thuộc vào thứ tự thuộc tính object. Array thì giữ thứ tự phần tử và thường cần được kiểm tra theo đúng thứ tự nếu thứ tự có ý nghĩa.

## 14. Khi nào dùng JsonNode, ObjectNode, ArrayNode và DTO?

Các kiểu này bổ sung cho nhau:

| Công cụ | Nên dùng khi |
|---|---|
| JsonNode | Cần tham chiếu hoặc xử lý chung cho mọi loại giá trị JSON. |
| ObjectNode | Cần tạo hoặc chỉnh sửa JSON object theo tên thuộc tính. |
| ArrayNode | Cần tạo hoặc chỉnh sửa JSON array theo vị trí phần tử. |
| DTO / record | Cấu trúc dữ liệu đã biết và cần kiểu Java rõ ràng, dễ validation, dễ dùng trong nghiệp vụ. |
| Streaming API | Tài liệu rất lớn hoặc cần xử lý tuần tự mà không giữ toàn bộ cây trong bộ nhớ. |

Tree model đặc biệt hữu ích trong các trường hợp:

- API nhận JSON có trường động hoặc metadata tùy đối tác.
- Cần kiểm tra sự tồn tại của field trước khi ánh xạ.
- Cần sửa, thêm hoặc xóa một phần JSON.
- Cần lọc một số thuộc tính rồi mới gửi tiếp.
- Cần đọc nhiều cấu trúc khác nhau bằng cùng một luồng xử lý.
- Cần giữ nguyên subtree chưa có DTO tương ứng.

Nếu schema ổn định, DTO thường dễ bảo trì hơn vì compiler biết kiểu field và validation có thể được gắn trực tiếp. Nếu file có hàng triệu phần tử, streaming thường tiết kiệm bộ nhớ hơn vì tree model phải giữ cấu trúc node trong bộ nhớ.

Có thể kết hợp các cách: streaming để đọc từng bản ghi lớn, tree model để xử lý phần dữ liệu linh hoạt của từng bản ghi, rồi chuyển các phần cố định thành DTO.

## 15. Những lỗi thường gặp khi làm việc với tree model

### Ép kiểu node khi chưa kiểm tra loại

Không nên:

~~~java
ObjectNode customer = (ObjectNode) root.get("customer");
~~~

Nếu customer bị thiếu, null hoặc không phải object, code có thể lỗi. Hãy kiểm tra isObject() trước khi ép kiểu.

### Nhầm MissingNode với NullNode

get() trả Java null khi thiếu property, còn JSON null được biểu diễn bằng NullNode. path() trả MissingNode khi thiếu. Hãy dùng đúng phép kiểm tra theo API đã chọn.

### Dùng asInt() để xác thực số nguyên

asInt() là API chuyển đổi tiện lợi, không phải validator. Nếu cần số nguyên đúng định dạng và đúng phạm vi, hãy kiểm tra isIntegralNumber() và canConvertToInt() trước khi gọi intValue().

### Coi ObjectNode và ArrayNode là immutable

Container node có thể bị sửa đổi. Nếu cần dữ liệu độc lập, dùng deepCopy() và tránh chia sẻ mutable subtree giữa các luồng.

### Dùng tree model cho mọi dữ liệu lớn

Tree model giữ toàn bộ cấu trúc đã parse trong bộ nhớ. Với dữ liệu lớn cần xử lý tuần tự, Streaming API thường phù hợp hơn.

### Tự ghép chuỗi để tạo JSON

Dùng ObjectNode và ArrayNode để xây dựng cấu trúc. Jackson sẽ xử lý escaping, kiểu dữ liệu, dấu phân cách và serialize đúng cú pháp.

## Kết luận

JsonNode là kiểu nền tảng để làm việc với mọi giá trị trong cây JSON. ObjectNode đại diện cho object và cho phép thao tác theo tên thuộc tính; ArrayNode đại diện cho array và cho phép thao tác theo vị trí phần tử. Cả hai là container node có thể lồng nhau và được tạo, đọc, sửa rồi serialize bằng ObjectMapper.

Hãy dùng tree model khi cấu trúc đầu vào linh hoạt hoặc cần thao tác từng phần; dùng DTO khi schema ổn định và cần kiểu Java rõ ràng; dùng streaming khi dữ liệu lớn cần xử lý tuần tự. Kết hợp kiểm tra loại node, phân biệt MissingNode với NullNode và dùng deepCopy khi cần bản sao độc lập để xử lý JSON an toàn, dễ kiểm soát.

