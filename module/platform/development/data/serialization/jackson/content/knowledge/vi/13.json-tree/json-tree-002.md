# Đọc tài liệu thành cây bằng readTree

Jackson cung cấp Tree Model để biểu diễn một JSON document dưới dạng cây node trong bộ nhớ. Thay vì ánh xạ toàn bộ JSON vào một class Java đã định nghĩa trước, ứng dụng có thể dùng method **readTree()** của ObjectMapper để đọc document thành một JsonNode, sau đó duyệt, kiểm tra hoặc thay đổi từng phần của cấu trúc.

Cách làm này hữu ích khi cấu trúc JSON chưa cố định, khi chỉ cần lấy một vài trường, khi cần xử lý dữ liệu lồng nhau theo điều kiện hoặc khi muốn biến đổi JSON trước khi chuyển nó thành DTO. Tree Model nằm giữa Data Binding và Streaming API: nó linh hoạt hơn POJO nhưng vẫn giữ toàn bộ cấu trúc document trong bộ nhớ.

## 1. Tree Model là gì?

JSON có các dạng cấu trúc như object, array, string, number, boolean và null. Tree Model biểu diễn từng giá trị đó thành một node. Các node liên kết với nhau thành cây:

~~~json
{
  "id": 101,
  "customer": {
    "name": "An",
    "active": true
  },
  "tags": ["java", "jackson"],
  "note": null
}
~~~

Có thể hình dung cây tương ứng:

~~~text
ObjectNode
├── id: IntNode(101)
├── customer: ObjectNode
│   ├── name: TextNode("An")
│   └── active: BooleanNode(true)
├── tags: ArrayNode
│   ├── TextNode("java")
│   └── TextNode("jackson")
└── note: NullNode
~~~

Mỗi node có kiểu cụ thể. Node object chứa các cặp tên và node con; node array chứa một dãy node; node value chứa giá trị scalar như string, number hoặc boolean.

Jackson sử dụng lớp trừu tượng **JsonNode** làm kiểu gốc cho các node trong cây. Các kiểu thường gặp:

| Kiểu node | Biểu diễn |
|---|---|
| ObjectNode | JSON object |
| ArrayNode | JSON array |
| TextNode | JSON string |
| IntNode, LongNode, DecimalNode và các node số khác | JSON number |
| BooleanNode | JSON true hoặc false |
| NullNode | JSON null |
| MissingNode | Kết quả biểu diễn một đường dẫn không tồn tại trong một số thao tác truy cập |

ObjectNode và ArrayNode là các node có cấu trúc có thể thay đổi. Các node giá trị như TextNode, BooleanNode và NullNode thường được xem là giá trị bất biến.

## 2. Đọc JSON thành cây bằng readTree()

### 2.1. Đọc từ String

Cách đơn giản nhất là truyền JSON string vào ObjectMapper:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ReadTreeExample {
    public static void main(String[] args) throws Exception {
        String json = """
                {
                  "id": 101,
                  "name": "An",
                  "active": true
                }
                """;

        ObjectMapper mapper = new ObjectMapper();

        JsonNode root = mapper.readTree(json);

        System.out.println(root);
        System.out.println(root.get("name").asText());
    }
}
~~~

readTree() phân tích JSON và trả về node gốc. Trong ví dụ, root là ObjectNode vì document ngoài cùng là JSON object.

Không cần tạo class Customer trước khi đọc. Ứng dụng có thể kiểm tra cấu trúc document rồi mới quyết định lấy dữ liệu hoặc chuyển đổi sang một kiểu Java cụ thể.

### 2.2. Đọc một JSON array ở node gốc

JSON document không bắt buộc phải bắt đầu bằng object. Nếu nội dung gốc là array:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
~~~

node gốc sẽ là ArrayNode:

~~~java
JsonNode root = mapper.readTree(json);

if (root.isArray()) {
    for (JsonNode item : root) {
        System.out.println(item.path("name").asText());
    }
}
~~~

Không nên giả định root luôn là ObjectNode. Hãy kiểm tra isObject(), isArray() hoặc node type trước khi truy cập theo cấu trúc mong đợi.

### 2.3. Đọc từ file

Có thể truyền File cho readTree():

~~~java
Path path = Path.of("data", "customer.json");

JsonNode root = mapper.readTree(path.toFile());
~~~

Hoặc tự mở Reader để chỉ định charset:

~~~java
try (Reader reader = Files.newBufferedReader(
        path,
        StandardCharsets.UTF_8
)) {
    JsonNode root = mapper.readTree(reader);
}
~~~

Reader làm việc với ký tự, vì vậy charset được chỉ định ở bước tạo Reader. Khi đọc từ byte stream, Jackson có thể nhận diện encoding theo định dạng đầu vào; với hệ thống trao đổi dữ liệu, UTF-8 là lựa chọn phổ biến và nên được thống nhất.

### 2.4. Đọc từ InputStream

Nếu JSON đến từ HTTP, file hoặc một nguồn byte khác, có thể truyền InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    JsonNode root = mapper.readTree(input);
}
~~~

Đọc từ stream giúp tránh phải tự tạo một String chứa toàn bộ nội dung trước khi parse. Tuy nhiên, Tree Model vẫn xây dựng toàn bộ cây node trong bộ nhớ. Nếu document rất lớn, nên cân nhắc Streaming API để xử lý tuần tự từng token.

### 2.5. Đọc từ byte array hoặc JsonParser

ObjectMapper cũng có overload nhận byte array hoặc JsonParser:

~~~java
byte[] bytes = Files.readAllBytes(path);
JsonNode rootFromBytes = mapper.readTree(bytes);
~~~

~~~java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    JsonNode rootFromParser = mapper.readTree(parser);
}
~~~

Dùng JsonParser trực tiếp hữu ích khi ứng dụng đã có parser hoặc đang phối hợp Tree Model với Streaming API. Khi dùng parser chung, cần chú ý vị trí token hiện tại và quyền sở hữu vòng đời parser.

## 3. Kiểm tra node gốc trước khi truy cập

### 3.1. Phân biệt object, array và scalar

Sau khi đọc, hãy kiểm tra kiểu node trước khi gọi các thao tác phụ thuộc cấu trúc:

~~~java
JsonNode root = mapper.readTree(json);

if (root == null) {
    throw new IllegalArgumentException("JSON document is empty");
}

if (root.isObject()) {
    System.out.println("Root is an object");
} else if (root.isArray()) {
    System.out.println("Root is an array");
} else if (root.isTextual()) {
    System.out.println("Root is a string");
} else if (root.isNumber()) {
    System.out.println("Root is a number");
} else if (root.isBoolean()) {
    System.out.println("Root is a boolean");
} else if (root.isNull()) {
    System.out.println("Root is JSON null");
}
~~~

Một JSON document hợp lệ có thể là scalar ở root, ví dụ:

~~~json
"hello"
~~~

~~~json
42
~~~

~~~json
true
~~~

~~~json
null
~~~

Vì vậy, nếu hợp đồng yêu cầu root phải là object, hãy kiểm tra isObject() và báo lỗi phù hợp thay vì ép mọi document thành object.

### 3.2. Phân biệt input rỗng và JSON null

Hai trường hợp sau không giống nhau:

- Input không có nội dung.
- Input chứa đúng token JSON null.

Với các API readTree của Jackson 2.x, input rỗng có thể khiến method trả về Java null vì không có root token để tạo node. Trong khi document chứa JSON null được biểu diễn bằng một NullNode.

~~~java
JsonNode emptyResult = mapper.readTree("");
JsonNode nullResult = mapper.readTree("null");

System.out.println(emptyResult == null); // true với input rỗng
System.out.println(nullResult.isNull()); // true với JSON null
~~~

Đây là lý do nên kiểm tra root có phải Java null trước khi gọi isNull() hoặc các method khác.

## 4. Truy cập property bằng get() và path()

Đây là hai cách truy cập node con thường gặp nhất.

### 4.1. get(): trả về null nếu không có khóa

~~~java
JsonNode root = mapper.readTree("""
        {
          "name": "An",
          "age": 25
        }
        """);

JsonNode nameNode = root.get("name");
JsonNode missingNode = root.get("nickname");
~~~

Nếu khóa không tồn tại, get() trả về Java null. Nếu khóa có mặt nhưng JSON value là null, get() trả về một NullNode.

Vì vậy, cần phân biệt:

~~~java
JsonNode node = root.get("nickname");

if (node == null) {
    System.out.println("Property is missing");
} else if (node.isNull()) {
    System.out.println("Property exists and is null");
} else {
    System.out.println("Property has a value");
}
~~~

Nếu gọi node.asText() ngay khi node là Java null, ứng dụng sẽ gặp NullPointerException.

### 4.2. path(): trả về MissingNode nếu không có khóa

path() thuận tiện khi muốn truy cập chuỗi property lồng nhau mà không phải kiểm tra Java null ở mỗi bước:

~~~java
String city = root.path("address")
        .path("city")
        .asText();
~~~

Nếu address hoặc city không tồn tại, path() trả về MissingNode thay vì Java null. Có thể kiểm tra:

~~~java
JsonNode cityNode = root.path("address").path("city");

if (cityNode.isMissingNode()) {
    System.out.println("City is missing");
} else if (cityNode.isNull()) {
    System.out.println("City is explicitly null");
} else {
    System.out.println(cityNode.asText());
}
~~~

path() giúp chuỗi truy cập an toàn hơn, nhưng không tự xác nhận cấu trúc đúng với hợp đồng. Nếu cần bắt buộc có field, ứng dụng vẫn phải kiểm tra trạng thái node.

### 4.3. has() và hasNonNull()

Hai method này kiểm tra sự hiện diện:

~~~java
boolean exists = root.has("nickname");
boolean hasValue = root.hasNonNull("nickname");
~~~

| Trạng thái property | has(name) | hasNonNull(name) |
|---|---:|---:|
| Không tồn tại | false | false |
| Có mặt, value null | true | false |
| Có mặt, value khác null | true | true |

has() trả lời câu hỏi khóa có tồn tại hay không. hasNonNull() trả lời câu hỏi khóa có tồn tại với giá trị khác null hay không.

Không nên dùng hasNonNull() nếu nghiệp vụ cần phân biệt missing và null, vì cả hai đều cho kết quả false.

## 5. Đọc giá trị theo kiểu dữ liệu

JsonNode cung cấp các method tiện ích để lấy string, number và boolean. Hãy kiểm tra node type nếu dữ liệu đầu vào cần tuân thủ kiểu nghiêm ngặt.

### 5.1. String

~~~java
JsonNode nameNode = root.path("name");

if (nameNode.isTextual()) {
    String name = nameNode.textValue();
}
~~~

asText() cũng có thể chuyển một số node scalar thành chuỗi. textValue() thể hiện rõ ý định lấy nội dung của TextNode và có thể trả về Java null nếu node không phải textual.

### 5.2. Số nguyên

~~~java
JsonNode ageNode = root.path("age");

if (ageNode.isIntegralNumber() && ageNode.canConvertToInt()) {
    int age = ageNode.intValue();
}
~~~

canConvertToInt() giúp kiểm tra giá trị số có nằm trong miền int hay không. Nếu không kiểm tra, việc lấy giá trị có thể gây mất thông tin do tràn hoặc chuyển đổi không phù hợp.

### 5.3. Số thập phân

~~~java
JsonNode priceNode = root.path("price");

if (priceNode.isNumber()) {
    BigDecimal price = priceNode.decimalValue();
}
~~~

Với dữ liệu cần độ chính xác thập phân như tiền tệ, decimalValue() giúp lấy BigDecimal thay vì chuyển qua double.

### 5.4. Boolean

~~~java
JsonNode activeNode = root.path("active");

if (activeNode.isBoolean()) {
    boolean active = activeNode.booleanValue();
}
~~~

Không nên gọi asBoolean() rồi mặc nhiên coi mọi kết quả là dữ liệu hợp lệ. Method chuyển đổi tiện ích có thể trả về giá trị mặc định khi node không phù hợp. Nếu JSON contract yêu cầu boolean, hãy kiểm tra isBoolean() trước.

### 5.5. Null và MissingNode

Các method như asText(), asInt() và asBoolean() có thể trả về giá trị mặc định đối với node null hoặc missing. Điều đó thuận tiện cho dữ liệu tùy chọn nhưng có thể làm mất khác biệt giữa thiếu dữ liệu và giá trị thực.

Ví dụ, asInt() có thể trả về 0 trong tình huống node không chuyển đổi được. Nếu 0 là giá trị hợp lệ, ứng dụng có thể nhầm dữ liệu sai với dữ liệu thực. Hãy kiểm tra node trước khi chuyển đổi hoặc dùng overload có giá trị fallback được chỉ định rõ khi nghiệp vụ cho phép.

## 6. Duyệt object và array

### 6.1. Duyệt các field của ObjectNode

Có thể dùng fields() để duyệt cặp tên và node con:

~~~java
JsonNode root = mapper.readTree(json);

Iterator<Map.Entry<String, JsonNode>> fields = root.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> field = fields.next();

    String fieldName = field.getKey();
    JsonNode value = field.getValue();

    System.out.println(fieldName + " = " + value);
}
~~~

fields() phù hợp khi chưa biết trước tên property hoặc cần xử lý tất cả field theo một quy tắc chung.

fieldNames() chỉ trả về tên khóa. Nếu cần cả tên và giá trị, fields() thuận tiện hơn.

### 6.2. Duyệt các phần tử array

JsonNode có thể được lặp trực tiếp nếu node là array:

~~~java
JsonNode items = root.path("items");

if (items.isArray()) {
    for (JsonNode item : items) {
        System.out.println(item.path("name").asText());
    }
}
~~~

Có thể dùng elements() khi muốn nhận Iterator<JsonNode>:

~~~java
Iterator<JsonNode> elements = items.elements();

while (elements.hasNext()) {
    JsonNode item = elements.next();
}
~~~

Không nên giả định mọi phần tử trong array đều có cùng cấu trúc nếu dữ liệu chưa được kiểm tra. Hãy xác định item có phải object và property mong đợi có đúng kiểu hay không.

### 6.3. Truy cập phần tử theo index

Với array:

~~~java
JsonNode firstItem = items.get(0);
JsonNode secondItem = items.path(1);
~~~

get(index) trả về Java null nếu index không tồn tại. path(index) trả về MissingNode nếu index không tồn tại.

Có thể kiểm tra kích thước trước khi truy cập:

~~~java
if (items.isArray() && items.size() > 0) {
    JsonNode first = items.get(0);
}
~~~

size() trả về số field đối với object hoặc số phần tử đối với array. Với scalar node, kích thước thường là 0.

## 7. Truy cập đường dẫn lồng nhau

### 7.1. Ghép path()

Với JSON:

~~~json
{
  "customer": {
    "profile": {
      "name": "An",
      "city": "Ho Chi Minh City"
    }
  }
}
~~~

Có thể đọc city:

~~~java
String city = root.path("customer")
        .path("profile")
        .path("city")
        .asText();
~~~

Cách này dễ đọc với đường dẫn ngắn. Nếu cần kiểm tra từng tầng, hãy giữ node trung gian và kiểm tra isObject() hoặc isMissingNode().

### 7.2. Dùng JSON Pointer với at()

Jackson hỗ trợ JSON Pointer để truy cập một node theo đường dẫn:

~~~java
JsonNode cityNode = root.at("/customer/profile/city");
~~~

Một số ví dụ:

| JSON Pointer | Ý nghĩa |
|---|---|
| /customer/name | Property name bên trong customer |
| /items/0 | Phần tử đầu tiên của array items |
| /items/1/price | price của phần tử thứ hai |
| /a~1b | Khóa có ký tự slash được escape |
| /a~0b | Khóa có ký tự tilde được escape |

Trong JSON Pointer, ký tự slash trong tên khóa được viết thành ~1, còn dấu ~ được viết thành ~0.

Nếu đường dẫn không tồn tại, at() trả về MissingNode. Có thể kiểm tra:

~~~java
JsonNode node = root.at("/customer/profile/city");

if (node.isMissingNode()) {
    throw new IllegalArgumentException("Required path is missing");
}
~~~

JSON Pointer hữu ích khi đường dẫn được truyền vào như một cấu hình hoặc khi cần truy cập sâu mà không viết nhiều lần path().

## 8. Thay đổi cây JSON

Tree Model không chỉ dùng để đọc. ObjectNode và ArrayNode còn cho phép tạo hoặc chỉnh sửa cấu trúc JSON.

### 8.1. Chuyển JsonNode thành ObjectNode

~~~java
JsonNode root = mapper.readTree(json);

if (!(root instanceof ObjectNode objectNode)) {
    throw new IllegalArgumentException("Expected a JSON object");
}

objectNode.put("active", true);
objectNode.put("displayName", "An Nguyen");
objectNode.putNull("deletedAt");
~~~

put() tạo hoặc thay thế scalar property. putNull() đặt giá trị JSON null.

Nếu root không phải ObjectNode, không thể dùng các thao tác chỉnh sửa object theo cách này. Hãy kiểm tra kiểu node trước.

### 8.2. Thêm node con bằng set()

~~~java
ObjectNode root = mapper.createObjectNode();

ObjectNode address = mapper.createObjectNode();
address.put("city", "Ho Chi Minh City");
address.put("country", "Vietnam");

root.set("address", address);
~~~

set() nhận JsonNode nên phù hợp khi giá trị đã là node object, array hoặc node scalar.

Có thể tạo cây từ đầu bằng createObjectNode() và createArrayNode() mà không cần đọc JSON trước.

### 8.3. Xóa property

~~~java
ObjectNode objectNode = (ObjectNode) root;
objectNode.remove("internalNote");
~~~

remove() xóa property khỏi object. Kết quả khác với đặt property thành null:

- remove("nickname"): khóa nickname không còn tồn tại.
- putNull("nickname"): khóa vẫn tồn tại với JSON null.

Khác biệt này quan trọng nếu JSON được dùng làm tài liệu cập nhật.

### 8.4. Làm việc với array

~~~java
ArrayNode tags = mapper.createArrayNode();

tags.add("java");
tags.add("jackson");
tags.add(2026);

ObjectNode root = mapper.createObjectNode();
root.set("tags", tags);
~~~

Có thể thêm node, chèn theo index hoặc xóa phần tử:

~~~java
tags.insert(1, "json");
tags.remove(0);
~~~

ArrayNode lưu thứ tự phần tử. Khác với object property, vị trí phần tử array thường có ý nghĩa.

### 8.5. Serialize cây trở lại JSON

Sau khi chỉnh sửa, có thể ghi cây thành JSON:

~~~java
String updatedJson = mapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(root);
~~~

Hoặc ghi ra file:

~~~java
mapper.writeValue(Path.of("updated.json").toFile(), root);
~~~

Jackson dùng serializer của Tree Model để ghi các node thành JSON. Không cần tự nối chuỗi hoặc tự escape giá trị.

## 9. Chuyển đổi giữa JsonNode và POJO

Tree Model có thể kết hợp với Data Binding. Ứng dụng đọc JSON thành cây, kiểm tra cấu trúc, sau đó chuyển node thành DTO.

### 9.1. treeToValue()

~~~java
JsonNode root = mapper.readTree(json);

Customer customer = mapper.treeToValue(root, Customer.class);
~~~

treeToValue() ánh xạ node thành kiểu Java đích. Cách này hữu ích khi cần kiểm tra hoặc biến đổi một vài node trước khi tạo DTO.

### 9.2. convertValue()

~~~java
Customer customer = mapper.convertValue(root, Customer.class);
~~~

convertValue() chuyển đổi giữa các kiểu thông qua cơ chế databinding. Nó hữu ích khi nguồn đã là một object Java hoặc JsonNode và không cần parse một JSON string mới.

### 9.3. valueToTree()

Chiều ngược lại, có thể chuyển POJO thành JsonNode:

~~~java
Customer customer = new Customer("CUS-001", "An", 25);

JsonNode node = mapper.valueToTree(customer);
~~~

Sau đó có thể đọc hoặc thay đổi node trước khi ghi JSON.

### 9.4. Khi nào nên dùng cách nào?

| API | Nguồn | Đích | Mục đích |
|---|---|---|---|
| readTree() | JSON string, file, stream hoặc parser | JsonNode | Parse document thành cây |
| treeToValue() | JsonNode | POJO/kiểu Java | Chuyển cây thành kiểu đích |
| convertValue() | Giá trị Java hoặc node | Kiểu Java khác | Chuyển đổi qua databinding |
| valueToTree() | POJO hoặc giá trị Java | JsonNode | Tạo cây từ object |

Nếu schema đã biết và chỉ cần một DTO, có thể gọi readValue() trực tiếp. Nếu cần kiểm tra hoặc biến đổi cấu trúc trước, readTree() rồi treeToValue() thường phù hợp hơn.

## 10. Xử lý lỗi khi dùng readTree()

### 10.1. JSON sai cú pháp

~~~java
try {
    JsonNode root = mapper.readTree("{\"name\": }");
} catch (JsonProcessingException e) {
    System.out.println("JSON syntax or parsing error");
}
~~~

JsonProcessingException là nhóm exception thường gặp khi Jackson không thể xử lý nội dung JSON. Thông tin exception thường có vị trí dòng/cột và đường dẫn khi lỗi xảy ra trong quá trình mapping.

### 10.2. Input rỗng

Input không có token JSON có thể khiến readTree() trả về Java null. Vì vậy, hãy kiểm tra trước khi truy cập node:

~~~java
JsonNode root = mapper.readTree(json);

if (root == null) {
    throw new IllegalArgumentException("JSON input is empty");
}
~~~

Document chứa literal null lại trả về NullNode. Không nên dùng một phép kiểm tra null duy nhất để đại diện cho cả hai trường hợp.

### 10.3. Sai root type

Nếu hợp đồng yêu cầu object nhưng client gửi array:

~~~java
JsonNode root = mapper.readTree(json);

if (root == null || !root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}
~~~

Đây là kiểm tra cấu trúc mà ứng dụng thực hiện sau khi parse. readTree() có thể đọc thành công một array; việc array có phù hợp với API hay không là quyết định của ứng dụng.

### 10.4. Kiểm tra field bắt buộc và kiểu dữ liệu

~~~java
JsonNode root = mapper.readTree(json);

JsonNode idNode = root.path("id");
JsonNode nameNode = root.path("name");

if (!idNode.isIntegralNumber() || !idNode.canConvertToLong()) {
    throw new IllegalArgumentException("id must be an integer");
}

if (!nameNode.isTextual() || nameNode.textValue().isBlank()) {
    throw new IllegalArgumentException("name must be a non-empty string");
}
~~~

Đoạn code kiểm tra cấu trúc và kiểu trước khi lấy dữ liệu. Với ứng dụng lớn, nên gom các quy tắc vào lớp validation hoặc chuyển sang DTO có constraint thay vì rải kiểm tra thủ công khắp nơi.

## 11. Tree Model, Data Binding và Streaming API

Jackson cung cấp ba cách làm việc với JSON ở các mức trừu tượng khác nhau:

| Cách làm | API tiêu biểu | Đặc điểm |
|---|---|---|
| Data Binding | ObjectMapper.readValue(), writeValue() | Chuyển trực tiếp giữa JSON và kiểu Java đã biết |
| Tree Model | readTree(), JsonNode, ObjectNode, ArrayNode | Giữ cấu trúc JSON trong cây node có thể duyệt/chỉnh sửa |
| Streaming API | JsonParser, JsonGenerator | Xử lý tuần tự từng token, kiểm soát bộ nhớ tốt hơn với dữ liệu lớn |

### 11.1. Chọn Data Binding khi schema đã biết

Nếu document luôn có cấu trúc Customer ổn định:

~~~java
Customer customer = mapper.readValue(json, Customer.class);
~~~

Cách này cho code có kiểu rõ ràng, dễ gọi getter và dễ kiểm tra bằng compiler.

### 11.2. Chọn Tree Model khi cần cấu trúc linh hoạt

Nếu một trường có thể thay đổi giữa các loại dữ liệu, hoặc chỉ cần đọc một vài property:

~~~java
JsonNode root = mapper.readTree(json);

String type = root.path("type").asText();

if ("customer".equals(type)) {
    Customer customer = mapper.treeToValue(root, Customer.class);
} else if ("supplier".equals(type)) {
    Supplier supplier = mapper.treeToValue(root, Supplier.class);
}
~~~

Tree Model cho phép kiểm tra discriminator trước khi chọn kiểu Java đích.

### 11.3. Chọn Streaming API khi dữ liệu lớn

Tree Model giữ toàn bộ cây trong bộ nhớ. Nếu file có hàng triệu phần tử, tạo một node cho từng giá trị có thể tiêu tốn nhiều RAM.

Streaming API cho phép đọc từng token, xử lý record rồi giải phóng tham chiếu trước khi tiếp tục. Ví dụ, nếu chỉ cần đọc từng object trong một array lớn, parser có thể duyệt lần lượt thay vì tạo cả ArrayNode.

Tree Model phù hợp khi cần truy cập ngẫu nhiên, nhiều lần hoặc biến đổi cấu trúc. Streaming phù hợp khi cần xử lý tuần tự và tối ưu bộ nhớ.

## 12. Một ví dụ tổng hợp

Giả sử hệ thống nhận JSON từ một dịch vụ khác. Schema có thể thêm field mới theo thời gian, nhưng ứng dụng chỉ cần customer id, name và các tag.

JSON đầu vào:

~~~json
{
  "eventType": "customer.created",
  "data": {
    "id": 101,
    "name": "An",
    "tags": ["java", "backend"],
    "metadata": {
      "source": "partner",
      "version": 2
    }
  }
}
~~~

Đọc cây và lấy các trường cần thiết:

~~~java
ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(json);

if (root == null || !root.isObject()) {
    throw new IllegalArgumentException("Expected event object");
}

String eventType = root.path("eventType").asText();

JsonNode data = root.path("data");
if (!data.isObject()) {
    throw new IllegalArgumentException("Event data must be an object");
}

JsonNode idNode = data.path("id");
JsonNode nameNode = data.path("name");

if (!idNode.isIntegralNumber() || !idNode.canConvertToLong()) {
    throw new IllegalArgumentException("Invalid customer id");
}

if (!nameNode.isTextual()) {
    throw new IllegalArgumentException("Invalid customer name");
}

long id = idNode.longValue();
String name = nameNode.textValue();

List<String> tags = new ArrayList<>();
JsonNode tagsNode = data.path("tags");

if (tagsNode.isArray()) {
    for (JsonNode tagNode : tagsNode) {
        if (!tagNode.isTextual()) {
            throw new IllegalArgumentException("Each tag must be a string");
        }
        tags.add(tagNode.textValue());
    }
}
~~~

Ứng dụng chỉ phụ thuộc vào eventType, data.id, data.name và data.tags. Các field metadata có thể được giữ trong cây hoặc bỏ qua tùy yêu cầu.

Nếu muốn chuyển riêng data thành DTO:

~~~java
Customer customer = mapper.treeToValue(data, Customer.class);
~~~

Sau khi kiểm tra hoặc bổ sung thông tin, có thể thay đổi cây:

~~~java
ObjectNode dataObject = (ObjectNode) data;
dataObject.put("processed", true);
dataObject.remove("metadata");
~~~

Và ghi lại:

~~~java
String output = mapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(root);
~~~

Ví dụ này cho thấy Tree Model hữu ích khi document có nhiều field nhưng ứng dụng chỉ cần xử lý một phần, hoặc khi cần sửa cấu trúc trước khi gửi tiếp.

## 13. Những lưu ý quan trọng

### 13.1. JsonNode không phải POJO

JsonNode biểu diễn cấu trúc JSON. Nó không có getter/setter nghiệp vụ như Customer. Muốn truy cập property, dùng get(), path(), fields(), elements() và các method kiểm tra kiểu node.

### 13.2. Kiểm tra kiểu trước khi chuyển đổi

Các method tiện ích như asText(), asInt() có thể tạo giá trị fallback. Nếu dữ liệu cần tuân thủ schema nghiêm ngặt, hãy kiểm tra isTextual(), isIntegralNumber(), isBoolean() hoặc isArray() trước.

### 13.3. ObjectNode và ArrayNode có thể thay đổi

Nếu sửa node, các tham chiếu khác đến cùng node có thể quan sát được thay đổi. Nếu cần tạo bản sao trước khi chỉnh sửa, có thể dùng deepCopy() trên node có cấu trúc:

~~~java
ObjectNode copy = ((ObjectNode) root).deepCopy();
~~~

### 13.4. readTree không tự validate nghiệp vụ

Đọc được một JsonNode chỉ chứng minh parser đã tạo được cây từ JSON. Ứng dụng vẫn phải kiểm tra field bắt buộc, kiểu dữ liệu, giới hạn giá trị và quy tắc nghiệp vụ.

### 13.5. Cân nhắc bộ nhớ và kích thước input

Tree Model lưu toàn bộ cấu trúc trong bộ nhớ, thường có overhead lớn hơn nội dung JSON dạng byte. Với dữ liệu không đáng tin cậy, cần giới hạn kích thước request, độ sâu lồng nhau và số phần tử phù hợp. Khi dữ liệu rất lớn, dùng Streaming API hoặc xử lý theo từng phần.

### 13.6. Xử lý tài nguyên và encoding

Khi tự mở File, InputStream hoặc Reader, hãy quản lý tài nguyên bằng try-with-resources. Với Reader/Writer, chỉ định charset rõ ràng, thường là UTF-8. Khi làm việc với parser đã được tạo sẵn, cần hiểu thành phần nào sở hữu và đóng parser/nguồn.

## 14. Trình tự thực hành

Khi dùng readTree() trong một ứng dụng:

1. Chọn nguồn JSON phù hợp: String, File, Reader, InputStream, byte array hoặc JsonParser.
2. Gọi readTree() để nhận JsonNode gốc.
3. Xử lý riêng input rỗng và document chứa JSON null.
4. Kiểm tra root type: object, array hay scalar.
5. Dùng get() nếu cần phân biệt khóa thiếu với khóa có null; dùng path() để truy cập an toàn qua đường dẫn.
6. Kiểm tra node type trước khi chuyển thành String, số hoặc boolean.
7. Duyệt fields() hoặc elements() khi cấu trúc không biết trước.
8. Dùng ObjectNode/ArrayNode để thêm, thay đổi hoặc xóa node khi cần biến đổi JSON.
9. Dùng treeToValue() hoặc convertValue() nếu cần chuyển cây sang DTO.
10. Chuyển sang Streaming API nếu document quá lớn để giữ toàn bộ cây trong bộ nhớ.

readTree() là điểm vào chính để làm việc với JSON theo mô hình cây. JsonNode giúp ứng dụng khám phá cấu trúc, phân biệt trạng thái property, truy cập dữ liệu lồng nhau và chỉnh sửa document. Khi schema ổn định, Data Binding vẫn là cách đơn giản để ánh xạ trực tiếp vào POJO; khi cấu trúc linh hoạt hoặc cần thao tác từng phần, Tree Model mang lại mức kiểm soát phù hợp.
