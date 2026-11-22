# Chuyển cây sang đối tượng bằng treeToValue

Jackson Tree Model cho phép đọc JSON thành một cây JsonNode trước khi quyết định ánh xạ dữ liệu sang class Java nào. Sau khi đã kiểm tra cấu trúc, chọn một nhánh hoặc biến đổi node, ứng dụng có thể dùng ObjectMapper.treeToValue() để chuyển node đó thành POJO, record hoặc kiểu Java khác.

treeToValue() hữu ích khi chỉ một phần của JSON cần được chuyển thành DTO, khi payload có các nhánh động, hoặc khi ứng dụng muốn kiểm tra dữ liệu bằng tree API trước khi binding. Thay vì parse lại chuỗi JSON, Jackson đọc trực tiếp cấu trúc node đã có và áp dụng cơ chế databinding cho kiểu đích.

Điều quan trọng là phân biệt cây JSON với object Java. JsonNode giữ cấu trúc và kiểu token của dữ liệu đầu vào; treeToValue() tạo một object Java theo kiểu đích. Quá trình chuyển đổi vẫn chịu ảnh hưởng của annotation, module, creator, naming strategy và cấu hình deserialization của ObjectMapper.

## 1. treeToValue() làm gì?

Phương thức treeToValue() thuộc ObjectMapper. Nó nhận một TreeNode (thường là JsonNode) và một kiểu Java đích, sau đó chuyển nội dung node thành instance của kiểu đó.

Ví dụ, cây JSON:

~~~json
{
  "id": 101,
  "name": "Linh",
  "active": true
}
~~~

Có thể chuyển thành record:

~~~java
public record UserResponse(
    long id,
    String name,
    boolean active
) {}
~~~

Code:

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree(json);

UserResponse user =
    mapper.treeToValue(root, UserResponse.class);
~~~

Kết quả là một UserResponse có id 101, name "Linh" và active true.

treeToValue() không yêu cầu tạo chuỗi JSON trung gian rồi gọi readValue(). Nó dùng cây node làm nguồn cho quá trình databinding. Điều này giúp giữ một luồng xử lý: parse một lần, kiểm tra hoặc chỉnh sửa node, sau đó chuyển node cần thiết sang kiểu Java.

## 2. Quy trình parse tree rồi chuyển sang POJO

Một pipeline phổ biến gồm ba bước:

~~~text
JSON text / InputStream
        |
        v
ObjectMapper.readTree()
        |
        v
      JsonNode
        |
        +--> kiểm tra cấu trúc, presence, loại node
        |
        +--> chọn subtree cần xử lý
        |
        v
ObjectMapper.treeToValue()
        |
        v
      DTO / record
        |
        v
Validation và nghiệp vụ
~~~

Ví dụ đầy đủ:

~~~java
String json = """
    {
      "requestId": "REQ-100",
      "customer": {
        "id": 17,
        "name": "Linh"
      },
      "items": [
        {"sku": "BOOK-01", "quantity": 2},
        {"sku": "PEN-02", "quantity": 3}
      ]
    }
    """;

JsonNode root = mapper.readTree(json);

if (!root.isObject()) {
    throw new IllegalArgumentException("Request must be a JSON object");
}

JsonNode customerNode = root.path("customer");

if (!customerNode.isObject()) {
    throw new IllegalArgumentException("customer must be an object");
}

CustomerResponse customer =
    mapper.treeToValue(customerNode, CustomerResponse.class);
~~~

Ở đây, ứng dụng chỉ chuyển nhánh customer thành CustomerResponse. Các nhánh khác vẫn có thể được xử lý riêng hoặc giữ dưới dạng JsonNode.

Cách làm này hữu ích khi một request có phần header cố định, phần metadata động và nhiều payload con có schema khác nhau.

## 3. Chuyển một subtree thay vì toàn bộ root

Một ưu điểm quan trọng của tree model là có thể chọn node ở bất kỳ cấp nào.

Ví dụ:

~~~json
{
  "eventId": "EVT-500",
  "data": {
    "user": {
      "id": 17,
      "name": "Linh"
    },
    "source": "mobile"
  }
}
~~~

Nếu chỉ cần user:

~~~java
JsonNode userNode = root.path("data").path("user");

UserResponse user =
    mapper.treeToValue(userNode, UserResponse.class);
~~~

Không cần tạo DTO cho toàn bộ envelope nếu service chỉ quan tâm user.

Có thể dùng JsonPointer khi đường dẫn sâu:

~~~java
JsonNode userNode = root.at("/data/user");

if (userNode.isMissingNode()) {
    throw new IllegalArgumentException("data.user is required");
}

UserResponse user =
    mapper.treeToValue(userNode, UserResponse.class);
~~~

at() trả MissingNode nếu đường dẫn không tồn tại. Kiểm tra trước khi chuyển đổi để tránh biến một node thiếu thành kết quả không rõ ràng.

Nếu đường dẫn có tên field chứa dấu slash hoặc dấu ngã, phải escape theo quy tắc JSON Pointer: slash thành ~1, dấu ngã thành ~0.

## 4. Chuyển cây thành class Java thông thường

Ví dụ các class:

~~~java
public class CustomerResponse {
    private long id;
    private String name;

    public CustomerResponse() {
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
~~~

Sau đó:

~~~java
CustomerResponse customer =
    mapper.treeToValue(customerNode, CustomerResponse.class);
~~~

Jackson dùng cơ chế binding thông thường để tạo object và gán property. Tùy class, quá trình có thể dùng constructor không tham số và setter, field access, constructor creator hoặc record canonical constructor.

Nếu class không có constructor mà Jackson có thể sử dụng, hoặc không có creator/property mapping phù hợp, quá trình chuyển đổi sẽ thất bại với lỗi mapping.

treeToValue() không tự bỏ qua quy tắc tạo object của Databind. Hãy thiết kế constructor và property giống như khi gọi readValue() từ chuỗi JSON.

## 5. Chuyển sang Java record

Record là kiểu dữ liệu bất biến, có component và canonical constructor. Jackson phiên bản hỗ trợ record có thể ánh xạ JSON property vào record component.

~~~java
public record AddressResponse(
    String city,
    String country
) {}

public record CustomerResponse(
    long id,
    String name,
    AddressResponse address
) {}
~~~

JSON:

~~~json
{
  "id": 17,
  "name": "Linh",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "VN"
  }
}
~~~

Chuyển đổi:

~~~java
CustomerResponse customer =
    mapper.treeToValue(customerNode, CustomerResponse.class);
~~~

Jackson chuyển cả object address lồng nhau thành AddressResponse. Ứng dụng không cần tự lấy từng field rồi gọi constructor thủ công.

Với record có component bắt buộc, hãy quy định rõ cách xử lý property thiếu và explicit null. Các feature như FAIL_ON_MISSING_CREATOR_PROPERTIES hoặc FAIL_ON_NULL_CREATOR_PROPERTIES có thể giúp kiểm soát creator properties, nhưng nên cấu hình theo đúng hợp đồng và kiểm tra trên phiên bản Jackson của dự án.

## 6. Chuyển cây có collection hoặc Map

Khi kiểu đích là class cụ thể, dùng Class<T> rất đơn giản. Nhưng với collection generic, chỉ truyền List.class sẽ làm mất kiểu phần tử.

Ví dụ JSON:

~~~json
[
  {"id": 1, "name": "Linh"},
  {"id": 2, "name": "Minh"}
]
~~~

Muốn chuyển thành List<UserResponse>, cần cung cấp kiểu generic đầy đủ.

Dùng JavaType với ObjectReader:

~~~java
JavaType listType = mapper.getTypeFactory()
    .constructCollectionType(List.class, UserResponse.class);

List<UserResponse> users = mapper.readerFor(listType)
    .readValue(arrayNode.traverse(mapper));
~~~

Hoặc dùng TypeReference với parser từ node:

~~~java
List<UserResponse> users = mapper.readValue(
    arrayNode.traverse(mapper),
    new TypeReference<List<UserResponse>>() {}
);
~~~

Một số phiên bản Jackson cung cấp overload treeToValue() nhận JavaType hoặc TypeReference; nếu dùng overload này, hãy xác nhận nó có trong phiên bản jackson-databind của dự án. Cách readerFor(JavaType).readValue(node.traverse(mapper)) thể hiện rõ kiểu generic và có thể dùng khi cần cấu hình reader riêng.

Với Map:

~~~java
JavaType mapType = mapper.getTypeFactory()
    .constructMapType(
        Map.class,
        String.class,
        UserResponse.class
    );

Map<String, UserResponse> usersByCode =
    mapper.readerFor(mapType).readValue(mapNode.traverse(mapper));
~~~

JavaType mô tả cả kiểu key và value. Nếu chỉ dùng Map.class, Jackson thường không có đủ thông tin để tạo value theo UserResponse.

## 7. Chuyển một phần tử trong ArrayNode

ArrayNode giữ các phần tử theo thứ tự. Có thể chuyển từng node thành một DTO:

~~~java
JsonNode itemsNode = root.path("items");

if (!itemsNode.isArray()) {
    throw new IllegalArgumentException("items must be an array");
}

List<ItemResponse> items = new ArrayList<>();

for (JsonNode itemNode : itemsNode) {
    items.add(mapper.treeToValue(itemNode, ItemResponse.class));
}
~~~

Với từng phần tử, Jackson dùng ItemResponse để binding các field. Nếu một phần tử sai cấu trúc hoặc không thể ánh xạ, quá trình chuyển đổi ném lỗi.

Nếu cần biết phần tử nào lỗi, có thể thêm index vào thông báo:

~~~java
List<ItemResponse> items = new ArrayList<>();
int index = 0;

for (JsonNode itemNode : itemsNode) {
    try {
        items.add(mapper.treeToValue(itemNode, ItemResponse.class));
    } catch (JsonProcessingException exception) {
        throw new IllegalArgumentException(
            "Invalid item at index " + index,
            exception
        );
    }

    index++;
}
~~~

Với array rất lớn, việc tạo toàn bộ JsonNode rồi chuyển từng phần tử có thể tốn bộ nhớ. Nếu mục tiêu là xử lý tuần tự từng item, JsonParser/MappingIterator có thể phù hợp hơn.

## 8. Phân biệt NullNode, MissingNode và Java null trước khi chuyển

Tree model phân biệt property không tồn tại với property có giá trị JSON null.

Ví dụ:

~~~json
{
  "nickname": null
}
~~~

Với:

~~~java
JsonNode missing = root.get("unknown");
JsonNode explicitNull = root.get("nickname");
~~~

- missing là Java null vì get() không tìm thấy property.
- explicitNull là NullNode vì property tồn tại và có JSON null.

Nếu dùng path():

~~~java
JsonNode missing = root.path("unknown");
JsonNode explicitNull = root.path("nickname");
~~~

- missing là MissingNode.
- explicitNull là NullNode.

Hãy kiểm tra presence trước khi treeToValue():

~~~java
JsonNode addressNode = root.get("address");

if (addressNode == null) {
    // Property address không được gửi.
} else if (addressNode.isNull()) {
    // Property address có mặt nhưng giá trị là JSON null.
} else {
    AddressResponse address =
        mapper.treeToValue(addressNode, AddressResponse.class);
}
~~~

Đừng dùng MissingNode như thể nó là một object rỗng. MissingNode biểu diễn đường dẫn không tồn tại, không phải JSON object {}.

Với NullNode, kết quả phụ thuộc kiểu đích và quy tắc null của Databind. Đối với kiểu tham chiếu, JSON null thường ánh xạ thành Java null; đối với primitive, có thể áp dụng giá trị mặc định hoặc lỗi tùy cấu hình. Nếu null có ý nghĩa nghiệp vụ khác với thiếu field, hãy xử lý rõ ràng trước khi chuyển đổi.

## 9. Kiểm tra hình dạng node trước khi treeToValue()

treeToValue() thực hiện mapping; nó không thay thế việc xác nhận node có đúng hình dạng hợp đồng hay không.

Ví dụ API yêu cầu customer là object:

~~~java
JsonNode customerNode = root.path("customer");

if (customerNode.isMissingNode()) {
    throw new IllegalArgumentException("customer is required");
}

if (customerNode.isNull()) {
    throw new IllegalArgumentException("customer must not be null");
}

if (!customerNode.isObject()) {
    throw new IllegalArgumentException("customer must be an object");
}

CustomerResponse customer =
    mapper.treeToValue(customerNode, CustomerResponse.class);
~~~

Nếu node là string hoặc array, việc chuyển sang CustomerResponse có thể thất bại bằng lỗi mapping. Kiểm tra isObject() trước giúp thông báo lỗi cụ thể hơn.

Đối với scalar, có thể xác nhận kiểu trước:

~~~java
JsonNode quantityNode = root.path("quantity");

if (!quantityNode.isIntegralNumber()
        || !quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException("quantity must be an integer");
}

int quantity = quantityNode.intValue();
~~~

Nếu chỉ cần lấy một giá trị scalar, không nhất thiết phải gọi treeToValue(). Có thể dùng intValue(), textValue(), decimalValue() sau khi kiểm tra loại và phạm vi.

## 10. treeToValue() vẫn áp dụng annotation của kiểu đích

Vì treeToValue() sử dụng Databind, các annotation của class đích vẫn có tác dụng theo cấu hình mapper.

Ví dụ:

~~~java
public record UserResponse(
    @JsonProperty("user_id") long id,
    @JsonProperty("display_name") String name
) {}
~~~

Input node:

~~~json
{
  "user_id": 17,
  "display_name": "Linh"
}
~~~

Chuyển đổi:

~~~java
UserResponse user =
    mapper.treeToValue(node, UserResponse.class);
~~~

Jackson dùng tên wire được khai báo bằng @JsonProperty.

Tương tự, các annotation như @JsonAlias, @JsonFormat, @JsonIgnoreProperties, @JsonCreator và những metadata liên quan đến property có thể ảnh hưởng đến binding. Điều này có nghĩa treeToValue() không phải một phép copy field theo tên Java đơn giản; nó đi qua cơ chế mapping mà ObjectMapper đang cấu hình.

## 11. Module tùy biến cũng được áp dụng

Nếu ObjectMapper đã đăng ký custom deserializer trong SimpleModule, treeToValue() sử dụng mapper đó cũng có thể gọi deserializer tương ứng.

Ví dụ:

~~~java
SimpleModule module = new SimpleModule("money-module");
module.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();

JsonNode moneyNode = mapper.readTree("""
    {
      "amount": 1250.50,
      "currency": "VND"
    }
    """);

Money money = mapper.treeToValue(moneyNode, Money.class);
~~~

MoneyDeserializer được đăng ký trong module xử lý node thành Money. Vì vậy, nếu cùng một kiểu được chuyển từ JSON string, InputStream hoặc JsonNode, mapper đã cấu hình có thể duy trì cùng một quy tắc deserialize.

Nếu custom deserializer không được gọi, hãy kiểm tra xem treeToValue() có đang dùng đúng ObjectMapper hay không. Một mapper mới tạo bằng new ObjectMapper() không tự thừa hưởng module đã đăng ký trên mapper khác.

## 12. Cấu hình strict reader khi chuyển cây

Đôi khi chỉ một lần chuyển đổi cần chính sách chặt hơn mapper mặc định. Có thể tạo ObjectReader cho kiểu đích và cấu hình feature riêng:

~~~java
ObjectReader strictReader = mapper.readerFor(UserResponse.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .with(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);

UserResponse user =
    strictReader.readValue(node.traverse(mapper));
~~~

Cách này cho phép áp dụng cấu hình reader mà không cần thay đổi toàn bộ ObjectMapper.

Một số feature có ý nghĩa:

| Feature | Tác dụng |
|---|---|
| FAIL_ON_UNKNOWN_PROPERTIES | Từ chối property không ánh xạ được vào kiểu đích. |
| FAIL_ON_NULL_FOR_PRIMITIVES | Từ chối JSON null cho primitive. |
| FAIL_ON_MISSING_CREATOR_PROPERTIES | Từ chối creator property bị thiếu. |
| FAIL_ON_NULL_CREATOR_PROPERTIES | Từ chối creator property có explicit null. |
| FAIL_ON_TRAILING_TOKENS | Từ chối token dư sau root value khi đọc một document. |

Khi dùng ObjectReader với node.traverse(mapper), parser được tạo từ cây. FAIL_ON_TRAILING_TOKENS hữu ích khi nguồn parser có thể chứa thêm token sau root; với một JsonNode đã là một root tree riêng, thông thường không có sibling root thứ hai bên ngoài node đó.

Nếu cần strict policy chỉ cho một subtree, reader riêng có thể giúp tách chính sách khỏi các endpoint khác.

## 13. treeToValue() và convertValue() khác nhau thế nào?

Cả hai đều có thể chuyển dữ liệu sang kiểu đích, nhưng mục đích sử dụng khác nhau.

| API | Nguồn dữ liệu | Mục đích |
|---|---|---|
| treeToValue(node, Type.class) | TreeNode/JsonNode | Chuyển một node JSON đã có thành kiểu Java. |
| convertValue(source, Type.class) | Object Java, Map hoặc tree | Chuyển đổi tổng quát giữa các dạng dữ liệu mà Databind hỗ trợ. |
| readValue(json, Type.class) | Chuỗi, byte, stream hoặc parser | Parse JSON input rồi binding thành kiểu Java. |
| readTree(json) | JSON input | Parse thành cây JsonNode để kiểm tra/chỉnh sửa. |

Ví dụ treeToValue():

~~~java
UserResponse user = mapper.treeToValue(userNode, UserResponse.class);
~~~

Ví dụ convertValue():

~~~java
UserResponse user = mapper.convertValue(
    sourceMap,
    UserResponse.class
);
~~~

Ví dụ readValue():

~~~java
UserResponse user = mapper.readValue(json, UserResponse.class);
~~~

Nếu đã có JsonNode và muốn chuyển node đó thành DTO, treeToValue() diễn tả đúng ý định. Nếu nguồn là Map hoặc POJO khác, convertValue() phù hợp hơn. Nếu nguồn vẫn là JSON text hoặc InputStream, readValue() thường là đường trực tiếp.

convertValue() không phải một bản sao object Java thông thường; nó dùng cơ chế chuyển đổi Databind và có thể tạo ra hành vi tương tự serialize rồi deserialize trong bộ nhớ. Hãy dùng API theo loại nguồn và mục tiêu rõ ràng.

## 14. So sánh treeToValue() với readValue(node.traverse())

Có thể chuyển node bằng hai cách:

~~~java
UserResponse first =
    mapper.treeToValue(node, UserResponse.class);
~~~

Hoặc:

~~~java
UserResponse second = mapper.readValue(
    node.traverse(mapper),
    UserResponse.class
);
~~~

Cả hai đều dùng Databind để tạo kiểu đích. treeToValue() ngắn gọn hơn và thể hiện rằng nguồn là tree node. readValue() qua parser có ích khi muốn truyền thêm ObjectReader hoặc xử lý luồng parser theo một API chung.

Ví dụ reader có cấu hình riêng:

~~~java
ObjectReader reader = mapper.readerFor(UserResponse.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

UserResponse user = reader.readValue(node.traverse(mapper));
~~~

Không cần chuyển node thành chuỗi JSON trung gian:

~~~java
// Không cần làm như sau chỉ để gọi readValue:
String json = mapper.writeValueAsString(node);
UserResponse user = mapper.readValue(json, UserResponse.class);
~~~

Việc serialize node thành String rồi parse lại tạo thêm chi phí cấp phát và parse, trong khi node đã có sẵn.

## 15. Unknown property và dữ liệu động

Giả sử node có các field:

~~~json
{
  "id": 17,
  "name": "Linh",
  "metadata": {
    "source": "mobile"
  },
  "experimentalFlag": true
}
~~~

Kiểu đích chỉ có id và name:

~~~java
public record UserResponse(long id, String name) {}
~~~

Nếu mapper bỏ qua unknown property theo cấu hình mặc định, metadata và experimentalFlag không được giữ trong UserResponse. Nếu mapper bật FAIL_ON_UNKNOWN_PROPERTIES, quá trình chuyển đổi có thể thất bại.

Nếu cần giữ metadata, hãy đưa JsonNode vào DTO:

~~~java
public record UserResponse(
    long id,
    String name,
    JsonNode metadata
) {}
~~~

Hoặc chuyển riêng nhánh metadata:

~~~java
JsonNode metadataNode = node.path("metadata");

if (!metadataNode.isObject()) {
    throw new IllegalArgumentException("metadata must be an object");
}

MetadataResponse metadata =
    mapper.treeToValue(metadataNode, MetadataResponse.class);
~~~

Tree model cho phép giữ phần động dưới dạng JsonNode trong khi phần cố định được chuyển thành DTO. Đây là cách hữu ích khi tích hợp với nhiều producer có schema mở rộng khác nhau.

## 16. Chuyển đổi sau khi chỉnh sửa tree

Một lợi thế khác là có thể thay đổi node trước khi chuyển thành DTO.

~~~java
ObjectNode normalized = ((ObjectNode) root).deepCopy();

if (!normalized.has("displayName")
        && normalized.has("name")) {
    normalized.set("displayName", normalized.get("name").deepCopy());
}

normalized.remove("legacyField");

UserResponse user =
    mapper.treeToValue(normalized, UserResponse.class);
~~~

Ví dụ này tạo một bản sao để không sửa tree nguồn, đổi tên field legacy theo quy tắc tương thích rồi chuyển sang DTO.

Có thể dùng cách này trong adapter khi phải nhận nhiều phiên bản payload. Tuy nhiên, không nên âm thầm biến đổi dữ liệu mà không có quy tắc rõ. Nếu producer gửi cả name và displayName với giá trị khác nhau, ứng dụng cần xác định ưu tiên hoặc từ chối xung đột.

Nếu chỉ cần đổi tên một field, @JsonAlias hoặc custom deserializer có thể phù hợp hơn. Tree normalization hữu ích khi cần nhiều bước biến đổi trên một payload trước khi binding.

## 17. Lỗi thường gặp khi dùng treeToValue()

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Node không phải object | API mong DTO object nhưng input là array/scalar/null. | Kiểm tra isObject() trước khi chuyển. |
| Property thiếu | Tree không có field cần thiết. | Kiểm tra isMissingNode() hoặc has() trước. |
| Explicit null | Field có mặt nhưng là NullNode. | Xác định null có hợp lệ không trước khi chuyển. |
| Generic collection thành Map/List không đúng kiểu | Chỉ dùng List.class hoặc Map.class. | Dùng JavaType hoặc TypeReference. |
| Unknown property gây lỗi | Reader/mapper bật FAIL_ON_UNKNOWN_PROPERTIES. | Cập nhật DTO, giữ JsonNode cho field động hoặc điều chỉnh policy. |
| Custom deserializer không chạy | Dùng mapper chưa đăng ký module. | Chuyển bằng đúng ObjectMapper đã cấu hình. |
| Primitive nhận giá trị mặc định ngoài ý muốn | JSON null hoặc field thiếu được xử lý theo quy tắc primitive/creator. | Dùng wrapper, kiểm tra presence và bật feature strict phù hợp. |
| Dữ liệu bị mất sau khi chuyển | DTO không có property tương ứng và unknown fields bị bỏ qua. | Giữ subtree dưới dạng JsonNode hoặc mở rộng DTO. |
| Chuyển đổi thất bại do cấu trúc lồng nhau | Node con không phù hợp kiểu đích. | Kiểm tra node path và kiểu trước khi mapping. |

treeToValue() thường ném JsonProcessingException khi parse/binding không thành công. Hãy giữ nguyên nguyên nhân để log hoặc chuyển thành lỗi adapter có ngữ cảnh. Không nên bắt mọi lỗi rồi trả về DTO rỗng, vì như vậy dữ liệu sai có thể đi vào nghiệp vụ.

## 18. Kiểm tra kết quả sau khi chuyển và validation nghiệp vụ

Chuyển đổi thành công chỉ chứng minh Jackson tạo được kiểu Java theo quy tắc binding. Nó không đảm bảo dữ liệu thỏa mọi ràng buộc nghiệp vụ.

Ví dụ DTO:

~~~java
public record CreateUserRequest(
    String email,
    int age
) {}
~~~

JSON có thể deserialize thành công nhưng email rỗng hoặc age âm vẫn sai nghiệp vụ.

Có thể dùng Bean Validation sau khi chuyển:

~~~java
CreateUserRequest request =
    mapper.treeToValue(node, CreateUserRequest.class);

Set<ConstraintViolation<CreateUserRequest>> violations =
    validator.validate(request);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
~~~

Với DTO:

~~~java
public record CreateUserRequest(
    @NotBlank @Email String email,
    @Min(0) @Max(130) int age
) {}
~~~

Bean Validation kiểm tra miền giá trị sau khi Jackson hoàn thành binding. Nếu field bắt buộc phải xuất hiện, hãy kiểm tra presence trước khi treeToValue() hoặc dùng creator/feature phù hợp; @NotNull một mình không chứng minh property đã có mặt trong JSON nếu field có default hoặc primitive.

## 19. Kiểm thử treeToValue() bằng JUnit

Ví dụ test chuyển một subtree thành record:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonMappingException;
import org.junit.jupiter.api.Test;

class TreeToValueTest {

    record UserResponse(long id, String name) {}

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void convertsObjectNodeToRecord() throws Exception {
        JsonNode root = mapper.readTree("""
            {
              "data": {
                "id": 17,
                "name": "Linh"
              }
            }
            """);

        UserResponse user = mapper.treeToValue(
            root.path("data"),
            UserResponse.class
        );

        assertEquals(17L, user.id());
        assertEquals("Linh", user.name());
    }

    @Test
    void rejectsWrongRootShape() {
        JsonNode array = mapper.createArrayNode().add(1);

        assertThrows(
            JsonMappingException.class,
            () -> mapper.treeToValue(array, UserResponse.class)
        );
    }

    @Test
    void identifiesMissingSubtreeBeforeMapping() {
        JsonNode root = mapper.createObjectNode();

        JsonNode userNode = root.path("user");

        assertEquals(true, userNode.isMissingNode());
    }
}
~~~

Test thứ ba minh họa rằng ứng dụng nên nhận diện MissingNode trước khi chuyển đổi. Nếu muốn kiểm tra việc mapping thất bại, hãy truyền một node có hình dạng sai và xác nhận exception tương ứng trên phiên bản Jackson của dự án.

Với generic type, hãy có test riêng cho List<UserResponse> hoặc Map<String, UserResponse>. Với module tùy biến, tạo mapper từ cấu hình module production để chắc chắn treeToValue() dùng đúng deserializer.

## 20. Chọn API chuyển đổi phù hợp

| Tình huống | API nên dùng |
|---|---|
| Đã có JsonNode và cần DTO cụ thể | treeToValue(node, Target.class) |
| Đã có JsonNode và cần generic type | ObjectReader với JavaType và node.traverse(mapper), hoặc overload treeToValue hỗ trợ kiểu generic trong phiên bản đang dùng |
| Có JSON text hoặc InputStream và cần DTO ngay | readValue() |
| Có JSON text và cần kiểm tra/chỉnh sửa trước | readTree() rồi treeToValue() |
| Có Map hoặc POJO nguồn và muốn chuyển sang kiểu khác | convertValue() |
| Cần duyệt dữ liệu rất lớn theo token | JsonParser / Streaming API |
| Cần giữ phần JSON chưa có DTO | JsonNode trong DTO hoặc xử lý subtree riêng |

Không cần đưa mọi payload qua tree model. Nếu schema ổn định và không cần kiểm tra cấu trúc trước, readValue() trực tiếp thường đơn giản hơn. Tree model phát huy tác dụng khi cần chọn nhánh, giữ dữ liệu động, kiểm tra presence hoặc biến đổi JSON trước khi binding.

## Kết luận

treeToValue() chuyển một JsonNode/TreeNode thành kiểu Java bằng cơ chế Databind của ObjectMapper. Nó đặc biệt hữu ích sau khi đọc JSON thành cây, khi ứng dụng muốn kiểm tra cấu trúc, chọn một subtree hoặc chuẩn hóa dữ liệu trước khi tạo DTO.

Hãy xác nhận node tồn tại và có đúng hình dạng, phân biệt MissingNode với NullNode, dùng JavaType cho collection generic và chuyển bằng đúng mapper đã đăng ký module. treeToValue() vẫn áp dụng annotation, creator, deserializer và cấu hình Databind; nhưng chuyển đổi thành công không thay thế validation nghiệp vụ. Chọn treeToValue() khi nguồn đã là tree, readValue() khi nguồn là JSON text/stream, convertValue() khi cần chuyển đổi tổng quát giữa các kiểu Java.

