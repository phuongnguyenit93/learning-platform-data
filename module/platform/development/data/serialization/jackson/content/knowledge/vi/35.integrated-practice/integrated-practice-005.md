# Đọc dữ liệu mở rộng bằng cây JSON và giữ trường chưa nhận diện

Một hệ thống thường phải đọc JSON do nhiều phiên bản producer tạo ra. Producer mới có thể thêm field mà consumer hiện tại chưa biết. Nếu consumer từ chối mọi field lạ, việc thêm một thuộc tính tùy chọn cũng có thể làm hỏng tích hợp. Nếu consumer âm thầm bỏ qua field lạ, ứng dụng có thể đọc được message nhưng làm mất dữ liệu khi ghi lại hoặc chuyển tiếp message đó.

Jackson cung cấp hai cơ chế hữu ích cho tình huống này:

- **JSON Tree Model** với JsonNode, ObjectNode và ArrayNode để đọc, kiểm tra, thay đổi và chuyển đổi cấu trúc JSON linh hoạt.
- **Unknown-property handling** với JsonAnySetter, JsonAnyGetter hoặc chính sách bỏ qua field lạ để quyết định dữ liệu chưa nhận diện được xử lý thế nào.

Chọn đúng cơ chế phụ thuộc vào mục tiêu. Nếu cần inspect một vài field động, tree model thường rõ ràng. Nếu phần lớn payload có schema cố định nhưng cần giữ thêm field mới, có thể bind vào DTO và thu thập phần mở rộng bằng JsonAnySetter. Nếu chỉ cần chấp nhận payload có field lạ và không bao giờ ghi lại chúng, bỏ qua unknown properties có thể đủ.

Điều quan trọng là phân biệt **đọc được dữ liệu**, **giữ được dữ liệu chưa nhận diện** và **giữ nguyên văn bản JSON gốc**. Đây là ba yêu cầu khác nhau.

## 1. Vì sao field chưa nhận diện xuất hiện?

Giả sử consumer đang có DTO:

~~~java
public record CustomerEvent(
        String customerId,
        String eventType
) {}
~~~

Consumer nhận JSON:

~~~json
{
  "customerId": "CUS-100",
  "eventType": "CustomerUpdated",
  "preferredLanguage": "vi",
  "marketingConsent": true
}
~~~

preferredLanguage và marketingConsent chưa có trong DTO hiện tại. Chúng có thể xuất hiện vì:

- Producer được triển khai phiên bản mới trước consumer.
- Một hệ thống đối tác gửi thêm metadata.
- Event có extension fields tùy theo loại nghiệp vụ.
- API gateway hoặc middleware thêm thuộc tính.
- Payload được lưu lâu dài và schema thay đổi theo thời gian.
- Một message chứa thông tin chỉ một số consumer quan tâm.

Một consumer có thể chọn một trong ba chính sách:

| Chính sách | Kết quả | Khi phù hợp |
|---|---|---|
| Strict | Từ chối field lạ | Command/request cần schema nghiêm ngặt |
| Ignore | Bỏ qua field lạ | Consumer chỉ cần field đã biết và không phải round-trip |
| Preserve | Lưu field lạ để serialize/chuyển tiếp lại | Event consumer, proxy, integration hub, dữ liệu mở rộng |

Không có chính sách đúng cho mọi endpoint. Hãy quyết định theo contract và hậu quả nếu field mới bị bỏ mất.

## 2. Cây JSON của Jackson là gì?

Tree Model biểu diễn JSON thành một cây các node. Mỗi node đại diện cho một object, array hoặc giá trị scalar:

~~~text
ObjectNode
  |
  +-- "customerId"      -> TextNode
  |
  +-- "eventType"       -> TextNode
  |
  +-- "metadata"        -> ObjectNode
  |                         |
  |                         +-- "source" -> TextNode
  |                         +-- "priority" -> IntNode
  |
  +-- "tags"            -> ArrayNode
                            |
                            +-- TextNode
                            +-- TextNode
~~~

Các kiểu node thường gặp:

| Kiểu | Đại diện cho |
|---|---|
| ObjectNode | JSON object gồm các property |
| ArrayNode | JSON array gồm các phần tử |
| TextNode | JSON string |
| IntNode, LongNode, BigIntegerNode | JSON integer |
| DecimalNode, DoubleNode | JSON number có phần thập phân |
| BooleanNode | JSON true/false |
| NullNode | JSON null |
| MissingNode | Kết quả truy cập một property không tồn tại qua API như path() |

JsonNode là kiểu cơ sở để đọc và truy cập node. ObjectNode và ArrayNode là container có thể thay đổi cấu trúc. Các node scalar thường được dùng như giá trị bất biến.

## 3. Đọc JSON thành JsonNode

Dùng ObjectMapper.readTree() để parse JSON thành cây:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "customerId": "CUS-100",
          "eventType": "CustomerUpdated",
          "marketingConsent": true
        }
        """;

JsonNode root = mapper.readTree(json);
~~~

Truy cập field:

~~~java
String customerId = root.path("customerId").asText();
String eventType = root.path("eventType").asText();
boolean consent = root.path("marketingConsent").asBoolean();
~~~

path() trả về MissingNode khi property không tồn tại, vì vậy có thể gọi tiếp isMissingNode() mà không phải kiểm tra Java null trước.

Nếu biết chắc root phải là object, kiểm tra kiểu node:

~~~java
if (!root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}

ObjectNode object = (ObjectNode) root;
~~~

Không cast trực tiếp một JSON array hoặc scalar sang ObjectNode. Payload có root shape sai cần được xử lý như lỗi contract.

## 4. Khác nhau giữa get(), path(), has() và hasNonNull()

Các API truy cập property có semantics khác nhau:

~~~java
JsonNode root = mapper.readTree("""
        {
          "name": "An",
          "nickname": null
        }
        """);
~~~

| API | Property tồn tại có value | Property có explicit null | Property bị thiếu |
|---|---|---|---|
| get(name) | Trả node | Trả NullNode | Trả Java null |
| path(name) | Trả node | Trả NullNode | Trả MissingNode |
| has(name) | true | true | false |
| hasNonNull(name) | true | false | false |

Ví dụ:

~~~java
assertTrue(root.has("name"));
assertTrue(root.has("nickname"));
assertFalse(root.hasNonNull("nickname"));
assertFalse(root.has("age"));

assertTrue(root.path("age").isMissingNode());
assertTrue(root.path("nickname").isNull());
~~~

Khi cần phân biệt missing và explicit null, không dùng riêng asText() hoặc asInt() làm phép kiểm tra presence. Những phương thức chuyển đổi có thể trả giá trị mặc định và làm hai trạng thái trông giống nhau.

Ví dụ kiểm tra rõ:

~~~java
JsonNode nickname = root.get("nickname");

if (nickname == null) {
    // Property không xuất hiện.
} else if (nickname.isNull()) {
    // Property xuất hiện với JSON null.
} else {
    // Property có một giá trị cụ thể.
}
~~~

## 5. Đọc field động mà không cần DTO cho toàn bộ payload

Tree model phù hợp khi chỉ một số field cần được xử lý:

~~~java
JsonNode root = mapper.readTree(json);

String eventType = root.path("eventType").asText();
JsonNode metadata = root.path("metadata");

if (metadata.isObject()) {
    String source = metadata.path("source").asText("unknown");
    int priority = metadata.path("priority").asInt(0);
    process(eventType, source, priority);
}
~~~

Ưu điểm là consumer không cần định nghĩa DTO cho mọi property. Producer có thể thêm field mà phần logic không sử dụng vẫn tiếp tục đọc được.

Tuy nhiên, tree model không tự validation contract. Ứng dụng vẫn phải kiểm tra:

- Root có phải object không.
- Field bắt buộc có tồn tại không.
- Field có đúng kiểu node không.
- Number có nằm trong range không.
- Array có số phần tử cho phép không.
- Nested object có đủ cấu trúc cần thiết không.

asInt() có thể trả default khi node không chuyển đổi được theo overload đang dùng. Nếu cần báo lỗi chính xác, kiểm tra isIntegralNumber() hoặc canConvertToInt() trước khi lấy giá trị.

## 6. Kiểm tra kiểu node trước khi chuyển đổi

Không nên giả định field luôn có kiểu mong đợi:

~~~java
JsonNode quantityNode = root.get("quantity");

if (quantityNode == null || !quantityNode.isIntegralNumber()) {
    throw new IllegalArgumentException(
            "quantity must be an integer"
    );
}

if (!quantityNode.canConvertToInt()) {
    throw new IllegalArgumentException(
            "quantity is outside the supported integer range"
    );
}

int quantity = quantityNode.intValue();
~~~

Với string:

~~~java
JsonNode nameNode = root.get("name");

if (nameNode == null || !nameNode.isTextual()) {
    throw new IllegalArgumentException("name must be a string");
}

String name = nameNode.textValue();
~~~

Với boolean:

~~~java
JsonNode enabledNode = root.get("enabled");

if (enabledNode == null || !enabledNode.isBoolean()) {
    throw new IllegalArgumentException("enabled must be boolean");
}

boolean enabled = enabledNode.booleanValue();
~~~

Kiểm tra kiểu trước khi chuyển giúp phân biệt payload sai schema với giá trị mặc định. Đây là điểm quan trọng trong API nhận dữ liệu từ bên ngoài.

## 7. Duyệt object và array

Có thể duyệt các field chưa biết trước bằng fields():

~~~java
ObjectNode object = (ObjectNode) root;

Iterator<Map.Entry<String, JsonNode>> fields = object.fields();

while (fields.hasNext()) {
    Map.Entry<String, JsonNode> field = fields.next();

    String name = field.getKey();
    JsonNode value = field.getValue();

    processExtension(name, value);
}
~~~

Duyệt array bằng elements() hoặc vòng lặp:

~~~java
JsonNode tags = root.path("tags");

if (tags.isArray()) {
    for (JsonNode tag : tags) {
        if (tag.isTextual()) {
            processTag(tag.textValue());
        }
    }
}
~~~

Nếu một field có thể là array hoặc scalar theo dữ liệu thực tế, đừng âm thầm giả định. Hãy quy định contract hoặc hỗ trợ từng shape một cách tường minh.

## 8. Truy cập cấu trúc lồng nhau

Có thể đi qua nhiều cấp bằng path():

~~~java
String city = root
        .path("customer")
        .path("address")
        .path("city")
        .asText();
~~~

Cách này tránh NullPointerException khi một cấp bị thiếu. Nhưng nếu field bắt buộc, cần kiểm tra MissingNode và node type thay vì nhận chuỗi rỗng/default:

~~~java
JsonNode cityNode = root.path("customer")
        .path("address")
        .path("city");

if (!cityNode.isTextual()) {
    throw new IllegalArgumentException(
            "customer.address.city must be a string"
    );
}
~~~

Một path lồng sâu bị thiếu không tự động có nghĩa dữ liệu hợp lệ. path() giúp truy cập an toàn; validation vẫn là trách nhiệm của ứng dụng.

## 9. Chuyển một phần cây JSON thành DTO

Không nhất thiết phải xử lý toàn bộ payload bằng tree. Có thể đọc root tree, sau đó chuyển phần đã biết sang DTO bằng treeToValue():

~~~java
public record CustomerData(
        String customerId,
        String displayName
) {}

JsonNode root = mapper.readTree(json);
JsonNode customerNode = root.path("customer");

CustomerData customer = mapper.treeToValue(
        customerNode,
        CustomerData.class
);
~~~

Điều này hữu ích khi envelope chứa metadata động nhưng phần payload nghiệp vụ có schema ổn định:

~~~json
{
  "eventId": "EVT-900",
  "schemaVersion": 2,
  "metadata": {
    "source": "mobile",
    "traceId": "trace-123"
  },
  "customer": {
    "customerId": "CUS-100",
    "displayName": "Nguyen An"
  }
}
~~~

Có thể bind envelope hoặc từng phần độc lập. Hãy kiểm tra node trước khi chuyển; nếu customer bị thiếu hoặc không phải object, báo lỗi contract rõ ràng.

## 10. Chuyển DTO thành cây JSON bằng valueToTree()

Chiều ngược lại dùng valueToTree():

~~~java
CustomerData customer = new CustomerData(
        "CUS-100",
        "Nguyen An"
);

JsonNode tree = mapper.valueToTree(customer);
~~~

Có thể thêm metadata vào object tree:

~~~java
ObjectNode root = mapper.createObjectNode();

root.put("eventId", "EVT-900");
root.put("schemaVersion", 2);
root.set("customer", mapper.valueToTree(customer));
~~~

valueToTree() sử dụng cơ chế serializer của mapper để tạo node tree. Vì vậy, annotation, naming strategy và custom serializer có thể ảnh hưởng kết quả. Nó không phải phép chuyển Java object sang cấu trúc phản chiếu field một cách độc lập với cấu hình Jackson.

Nếu cần kiểm tra chính xác output JSON, test tree được tạo bằng mapper production hoặc kiểm tra chuỗi JSON ở cấp contract.

## 11. Khác nhau giữa readTree(), treeToValue(), valueToTree() và convertValue()

| API | Đầu vào | Đầu ra | Mục đích |
|---|---|---|---|
| readTree(json) | JSON text/bytes/stream | JsonNode | Parse JSON thành tree |
| treeToValue(node, Type.class) | JSON tree | Java object | Bind một tree vào kiểu đích |
| valueToTree(value) | Java object | JsonNode | Tạo tree qua serializer |
| convertValue(value, Type.class) | Java value hoặc tree | Java target type | Chuyển kiểu trong bộ máy databind |

readTree() thực sự parse tài liệu JSON. convertValue() không nên được dùng như cách parse một Java String chứa JSON; String đó là giá trị string cần chuyển đổi, không phải tài liệu JSON cần đọc.

Ví dụ đúng:

~~~java
JsonNode tree = mapper.readTree(json);
CustomerData customer = mapper.treeToValue(tree, CustomerData.class);
~~~

Ví dụ khác:

~~~java
CustomerData customer = mapper.convertValue(
        sourceMap,
        CustomerData.class
);
~~~

Hãy chọn API theo bản chất dữ liệu đầu vào. Nếu đầu vào là JSON document, parse bằng readTree() hoặc readValue().

## 12. Bỏ qua field chưa nhận diện bằng JsonIgnoreProperties

Nếu consumer chỉ cần field đã biết và chấp nhận mất phần mở rộng, có thể dùng:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerEvent(
        String customerId,
        String eventType
) {}
~~~

Với JSON:

~~~json
{
  "customerId": "CUS-100",
  "eventType": "CustomerUpdated",
  "futureFlag": true
}
~~~

Jackson có thể bind hai field đã biết và bỏ qua futureFlag.

Có thể cấu hình feature ở mapper:

~~~java
mapper.disable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
~~~

Annotation áp dụng theo class; feature trên mapper ảnh hưởng rộng hơn. Hãy cân nhắc phạm vi trước khi thay đổi.

**Bỏ qua không đồng nghĩa giữ lại.** Sau khi deserialize thành DTO không có property hoặc extension map, dữ liệu futureFlag đã mất. Nếu serialize DTO đó trở lại, field này không tự xuất hiện.

## 13. Thu thập field lạ bằng JsonAnySetter

Nếu cần giữ field chưa nhận diện, dùng JsonAnySetter để nhận tên property và node value:

~~~java
public class CustomerEvent {
    private String customerId;
    private String eventType;

    private final Map<String, JsonNode> extensions =
            new LinkedHashMap<>();

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    public Map<String, JsonNode> getExtensions() {
        return extensions;
    }
}
~~~

Khi Jackson gặp property không ánh xạ tới property đã biết, method addExtension() nhận tên và giá trị của nó.

JSON:

~~~json
{
  "customerId": "CUS-100",
  "eventType": "CustomerUpdated",
  "preferredLanguage": "vi",
  "marketingConsent": true,
  "futureMetadata": {
    "sourceVersion": 5,
    "labels": ["vip", "mobile"]
  }
}
~~~

Sau deserialize, map extensions có thể chứa:

- preferredLanguage là TextNode.
- marketingConsent là BooleanNode.
- futureMetadata là ObjectNode với cấu trúc lồng nhau.

Dùng JsonNode giúp giữ được cấu trúc và kiểu JSON của extension. Nếu dùng Map<String, Object>, Jackson sẽ tạo các kiểu Java tổng quát như Map, List, String, Boolean và Number; vẫn linh hoạt nhưng cần cẩn thận khi xử lý kiểu số và chuyển đổi tiếp.

## 14. Xuất lại extension bằng JsonAnyGetter

JsonAnySetter thu thập field; JsonAnyGetter đưa map trở lại thành các property JSON ở cấp object:

~~~java
@JsonAnyGetter
public Map<String, JsonNode> anyProperties() {
    return extensions;
}
~~~

Có thể bổ sung method này vào class ở phần trước. Khi serialize, các entry trong extensions được ghi như property cùng cấp với customerId và eventType.

Round-trip:

~~~java
CustomerEvent event = mapper.readValue(json, CustomerEvent.class);

String output = mapper.writeValueAsString(event);
JsonNode restoredTree = mapper.readTree(output);
~~~

Test field mở rộng:

~~~java
assertEquals("vi", restoredTree.path("preferredLanguage").asText());
assertTrue(restoredTree.path("marketingConsent").asBoolean());
assertEquals(
        5,
        restoredTree.path("futureMetadata")
                .path("sourceVersion")
                .asInt()
);
~~~

Đây là cách hữu ích cho event forward-compatible hoặc một service đóng vai trò trung gian.

## 15. JsonAnySetter và JsonAnyGetter không phải cơ chế giữ nguyên byte JSON

Khi parse rồi serialize lại, Jackson tái tạo JSON từ cấu trúc dữ liệu. Những thông tin lexical sau có thể thay đổi:

- Khoảng trắng và xuống dòng.
- Indentation/pretty printing.
- Thứ tự property object.
- Cách viết escape của string.
- Cách biểu diễn số, ví dụ 1.0 và 1.00.
- Dạng exponent của number.
- Dấu cách quanh dấu hai chấm và dấu phẩy.

Tree model giữ ý nghĩa dữ liệu theo cách Jackson parse, không giữ nguyên mọi ký tự của tài liệu gốc.

Nếu cần lưu nguyên văn payload để audit, ký số, đối chiếu chữ ký hoặc chuyển tiếp byte-for-byte, hãy lưu thêm raw request body/byte array theo chính sách phù hợp. Không dùng serialize lại một JsonNode như bằng chứng rằng chuỗi ban đầu được bảo toàn.

## 16. Unknown fields lồng nhau cần được xử lý ở đúng cấp

JsonAnySetter trên DTO ngoài chỉ nhận unknown properties trực tiếp của object đó. Nó không tự động thu thập field lạ bên trong mọi nested DTO.

Ví dụ:

~~~json
{
  "customerId": "CUS-100",
  "address": {
    "city": "Da Nang",
    "districtCode": "D-07"
  }
}
~~~

Nếu address được bind thành một class Address có schema cố định và không có any-setter, districtCode vẫn chịu chính sách unknown-property của Address.

Muốn giữ field lạ ở nested object, class nested cũng cần extension map/any-setter:

~~~java
public class Address {
    private String city;

    private final Map<String, JsonNode> extensions =
            new LinkedHashMap<>();

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> anyProperties() {
        return extensions;
    }
}
~~~

Hoặc giữ toàn bộ address dưới dạng JsonNode nếu consumer chưa cần bind nested structure thành DTO.

## 17. Dùng DTO cho phần ổn định, JsonNode cho phần mở rộng

Một pattern phổ biến là envelope có các field cốt lõi và payload mở rộng:

~~~java
public class IntegrationEvent {
    private String eventId;
    private String eventType;
    private int schemaVersion;
    private JsonNode data;

    // getters/setters
}
~~~

Ví dụ JSON:

~~~json
{
  "eventId": "EVT-900",
  "eventType": "CustomerUpdated",
  "schemaVersion": 3,
  "data": {
    "customerId": "CUS-100",
    "newFieldFromProducer": {
      "enabled": true,
      "labels": ["a", "b"]
    }
  }
}
~~~

Consumer có thể:

1. Bind eventId, eventType và schemaVersion thành kiểu rõ ràng.
2. Giữ data dưới dạng JsonNode.
3. Kiểm tra eventType/schemaVersion.
4. Chuyển các field đã biết thành DTO nếu cần.
5. Giữ lại field chưa biết để chuyển tiếp hoặc lưu trữ.

Cách này tránh phải tạo một DTO thay đổi liên tục cho mọi biến thể payload.

## 18. Kết hợp extension map với các field đã biết

Ví dụ hoàn chỉnh:

~~~java
public class CustomerEvent {
    private String eventId;
    private String customerId;
    private final Map<String, JsonNode> extensions =
            new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    @JsonAnySetter
    public void captureUnknown(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> unknownProperties() {
        return extensions;
    }
}
~~~

Với payload:

~~~json
{
  "eventId": "EVT-900",
  "customerId": "CUS-100",
  "newFeature": {
    "rollout": 25,
    "active": true
  }
}
~~~

Code xử lý extension:

~~~java
CustomerEvent event = mapper.readValue(json, CustomerEvent.class);

JsonNode newFeature = event.unknownProperties().get("newFeature");

if (newFeature != null && newFeature.isObject()) {
    int rollout = newFeature.path("rollout").asInt();
    boolean active = newFeature.path("active").asBoolean();

    if (active && rollout > 0) {
        enableCompatibleBehavior(rollout);
    }
}
~~~

Consumer chỉ diễn giải extension khi biết ý nghĩa của nó. Những extension khác vẫn được giữ lại để serialize hoặc chuyển tiếp.

## 19. Bảo vệ tên property đã biết và tránh xung đột

Extension map không nên được dùng để ghi đè field cốt lõi. Cần định nghĩa rõ namespace và kiểm tra tên.

Ví dụ không cho phép extension dùng các tên reserved:

~~~java
private static final Set<String> RESERVED =
        Set.of("eventId", "customerId", "eventType", "schemaVersion");

@JsonAnySetter
public void captureUnknown(String name, JsonNode value) {
    if (RESERVED.contains(name)) {
        throw new IllegalArgumentException(
                "Extension property uses a reserved name: " + name
        );
    }

    extensions.put(name, value);
}
~~~

Thông thường Jackson đã nhận diện known property trước khi gọi any-setter. Tuy nhiên, reserved-name check vẫn hữu ích khi extension map được tạo từ nguồn khác, được cập nhật thủ công hoặc được merge từ nhiều object.

Khi serialize, JsonAnyGetter xuất entry map thành property cùng cấp. Nếu map chứa tên trùng với property chuẩn, output có thể tạo JSON có duplicate key hoặc gây hành vi khó đoán ở consumer. Hãy bảo vệ invariant này trong model và test.

Nếu producer hỗ trợ extension có namespace, có thể đặt chúng dưới một property rõ ràng như extensions hoặc metadata thay vì đưa tất cả vào root. Cách đó giảm nguy cơ va chạm với field tương lai.

## 20. Chỉ giữ extension được cho phép

Giữ mọi field lạ là hữu ích cho forward compatibility nhưng có thể làm consumer lưu hoặc phát lại dữ liệu không mong muốn. Nếu payload đến từ nguồn không tin cậy, có thể dùng allowlist:

~~~java
private static final Set<String> ALLOWED_EXTENSIONS =
        Set.of("preferredLanguage", "marketingConsent", "futureMetadata");

@JsonAnySetter
public void captureUnknown(String name, JsonNode value) {
    if (!ALLOWED_EXTENSIONS.contains(name)) {
        throw new IllegalArgumentException(
                "Unsupported extension: " + name
        );
    }

    extensions.put(name, value);
}
~~~

Có hai chính sách khác nhau:

- **Preserve all:** giữ mọi unknown field, phù hợp proxy/event relay cần forward dữ liệu.
- **Allowlist:** chỉ giữ các extension đã được chấp thuận, phù hợp domain boundary cần kiểm soát.

Nếu muốn bỏ qua extension không được phép, hãy ghi nhận quyết định đó rõ ràng và không nhầm nó với preserve.

## 21. Giới hạn kích thước và độ sâu của dữ liệu mở rộng

Unknown field có thể chứa object hoặc array rất lớn. Việc giữ toàn bộ tree có thể làm tăng memory và tạo bề mặt tấn công.

Các giới hạn cần cân nhắc:

- Kích thước HTTP body tối đa.
- Số lượng property ở mỗi object.
- Số phần tử array.
- Độ sâu nesting.
- Độ dài string.
- Kích thước number và precision.
- Số lượng extension được giữ.
- Thời gian xử lý và số lượng message đồng thời.

Có thể kiểm tra kích thước extension sau parse:

~~~java
if (event.unknownProperties().size() > 50) {
    throw new IllegalArgumentException(
            "Too many extension properties"
    );
}
~~~

Với giới hạn parser-level, Jackson có StreamReadConstraints ở các version hỗ trợ. Cấu hình cụ thể phụ thuộc version Core; hãy kiểm tra API tương ứng của dependency đang dùng. Giới hạn HTTP body ở web server cũng cần được cấu hình riêng.

Không nên parse một payload không giới hạn chỉ vì field lạ được lưu dưới dạng JsonNode.

## 22. Xử lý null, missing và extension rỗng

Với any-setter, một property có mặt với JSON null vẫn là một property đã được gửi. Giá trị nhận được là NullNode, không phải Java null trong cách truy cập tree thông thường.

Ví dụ:

~~~json
{
  "futureFlag": null
}
~~~

Sau khi lưu:

~~~java
JsonNode futureFlag = event.unknownProperties().get("futureFlag");

assertNotNull(futureFlag);
assertTrue(futureFlag.isNull());
~~~

Nếu property không xuất hiện, map không có key:

~~~java
assertFalse(event.unknownProperties().containsKey("futureFlag"));
~~~

Không dùng Map.get() một mình để phân biệt missing với giá trị Java null nếu map cho phép null reference. Với JsonNode extension, nên giữ NullNode cho JSON null và không đưa Java null vào map.

Các trạng thái sau khác nhau:

| Payload | Map extension |
|---|---|
| Không có futureFlag | Không có key |
| futureFlag: null | Có key, value là NullNode |
| futureFlag: false | Có key, value là BooleanNode(false) |
| futureFlag: {} | Có key, value là ObjectNode rỗng |

## 23. Chỉnh sửa tree an toàn

ObjectNode và ArrayNode là container mutable. Có thể thêm, thay thế hoặc xóa property:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(json);

root.put("processed", true);
root.put("schemaVersion", 4);
root.remove("temporaryField");

ObjectNode metadata = root.withObject("metadata");
metadata.put("consumerVersion", "2.1");
~~~

Các helper như withObject() có thể phụ thuộc version Jackson; nếu project dùng version khác, có thể kiểm tra node trước rồi tạo/set ObjectNode tường minh.

Ví dụ không phụ thuộc helper:

~~~java
JsonNode existing = root.get("metadata");
ObjectNode metadata;

if (existing == null) {
    metadata = mapper.createObjectNode();
    root.set("metadata", metadata);
} else if (existing.isObject()) {
    metadata = (ObjectNode) existing;
} else {
    throw new IllegalArgumentException(
            "metadata must be a JSON object"
    );
}

metadata.put("consumerVersion", "2.1");
~~~

Nếu cần giữ nguyên cây ban đầu, tạo bản sao trước khi sửa:

~~~java
ObjectNode copy = root.deepCopy();
copy.put("processed", true);
~~~

deepCopy() quan trọng khi container lồng nhau vì copy nông có thể vẫn chia sẻ node con có thể thay đổi.

## 24. Merge extension từ nhiều nguồn

Khi kết hợp dữ liệu, cần quy định xung đột key. Ví dụ, tree incoming có thể được merge vào target:

~~~java
ObjectNode target = mapper.createObjectNode();
target.put("customerId", "CUS-100");

ObjectNode incoming = (ObjectNode) mapper.readTree("""
        {
          "source": "partner",
          "priority": 2
        }
        """);

incoming.fields().forEachRemaining(entry ->
        target.set(entry.getKey(), entry.getValue())
);
~~~

Trong ví dụ, field trùng tên trong incoming sẽ thay thế field cùng tên trong target nếu có. Đó là một chính sách overwrite, không phải quy tắc merge mặc định đúng cho mọi ứng dụng.

Có thể chọn:

- Existing wins: không ghi đè field đã có.
- Incoming wins: dữ liệu mới ghi đè.
- Reject collision: báo lỗi khi trùng.
- Recursive merge: merge object lồng nhau theo quy tắc được định nghĩa.
- Keep both: đưa extension vào namespace riêng.

Đừng dùng setAll() hoặc vòng lặp merge mà không xác định collision semantics. Với dữ liệu nghiệp vụ, overwrite im lặng có thể làm thay đổi ý nghĩa event.

## 25. Unknown property ở cấp top-level và nested object

Một DTO có any-setter ở root chỉ giữ field lạ trực tiếp ở root. Nếu JSON có cấu trúc:

~~~json
{
  "eventId": "EVT-900",
  "customer": {
    "customerId": "CUS-100",
    "newCustomerTier": "GOLD"
  }
}
~~~

và customer là DTO riêng, newCustomerTier cần được giữ bởi DTO customer hoặc được giữ dưới dạng JsonNode. Any-setter ở EventEnvelope không thể nhận field bên trong customer.

Một cách thiết kế là:

~~~java
public class EventEnvelope {
    private String eventId;
    private JsonNode customer;

    // getters/setters
}
~~~

Sau đó xử lý field đã biết từ customer tree hoặc chuyển node thành DTO có extension map. Chọn một điểm giữ dữ liệu rõ ràng thay vì mong đợi any-setter ở root bắt toàn bộ cây đệ quy.

## 26. Giữ trường chưa biết khi đổi schema version

Một envelope có version giúp chọn logic đọc:

~~~java
public record EventEnvelope(
        int schemaVersion,
        String eventType,
        JsonNode data
) {}
~~~

Ví dụ payload:

~~~json
{
  "schemaVersion": 1,
  "eventType": "CustomerUpdated",
  "data": {
    "customer_id": "CUS-100",
    "name": "Nguyen An",
    "legacy_region": "south"
  }
}
~~~

Consumer mới có thể:

1. Parse envelope.
2. Kiểm tra schemaVersion.
3. Chuyển các field đã biết từ data sang model hiện tại.
4. Giữ các field chưa nhận diện trong extension map.
5. Ghi ra schema mới hoặc forward payload theo chính sách.

Migration nên là bước rõ ràng:

~~~java
ObjectNode data = (ObjectNode) envelope.data().deepCopy();

if (envelope.schemaVersion() == 1) {
    JsonNode oldName = data.remove("name");

    if (oldName != null && !data.has("displayName")) {
        data.set("displayName", oldName);
    }
}

CurrentCustomer customer =
        mapper.treeToValue(data, CurrentCustomer.class);
~~~

Nếu CurrentCustomer cần giữ field lạ, nó phải có any-setter hoặc một property extension phù hợp. Nếu không, bước treeToValue có thể bỏ hoặc từ chối các field còn lại tùy cấu hình.

Không nên đổi schema version mà không định nghĩa cách giữ, chuyển hoặc loại bỏ field cũ.

## 27. JsonAlias khác với giữ unknown fields

JsonAlias cho phép một property đã biết nhận nhiều tên input:

~~~java
public class Customer {
    @JsonProperty("displayName")
    @JsonAlias({"name", "full_name"})
    private String displayName;

    // getter/setter
}
~~~

Jackson có thể đọc displayName, name hoặc full_name vào cùng một property. Khi serialize, tên chính là displayName.

Alias chỉ giải quyết các tên cũ đã biết trước. Nó không lưu mọi property lạ tùy ý. Nếu muốn giữ newFieldFromProducer, cần extension map hoặc tree model.

Có thể kết hợp alias với any-setter: tên alias được nhận diện như property đã biết, còn field khác đi vào extension map.

## 28. JsonIgnoreProperties khác với JsonAnySetter

| Cơ chế | Field lạ có làm lỗi không? | Field lạ có được giữ không? |
|---|---|---|
| Strict unknown handling | Có thể bị từ chối | Không |
| JsonIgnoreProperties(ignoreUnknown = true) | Không | Không, bị bỏ |
| FAIL_ON_UNKNOWN_PROPERTIES = false | Không | Không, bị bỏ |
| JsonAnySetter lưu vào map/tree | Không nếu setter xử lý thành công | Có |
| Đọc toàn bộ thành JsonNode | Không cần DTO để nhận field | Có, trong tree |

Nếu consumer chỉ cần một vài field và không bao giờ serialize lại payload, ignore unknown có thể đủ. Nếu consumer phải làm proxy, lưu event, audit hoặc forward đến hệ thống khác, preserve thường cần thiết.

## 29. Duplicate JSON property cần chính sách riêng

JSON object thông thường được kỳ vọng có tên property duy nhất, nhưng một số payload có thể chứa duplicate key:

~~~json
{
  "customerId": "CUS-100",
  "customerId": "CUS-200"
}
~~~

Nhiều parser mặc định sẽ giữ một giá trị theo hành vi xử lý duplicate của parser, thường là giá trị xuất hiện sau. Sau khi parse thành tree, thông tin về việc key từng xuất hiện nhiều lần có thể đã mất.

Nếu duplicate key là vấn đề an toàn hoặc tính đúng đắn, bật strict duplicate detection ở parser factory phù hợp với Jackson version:

~~~java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper strictMapper = JsonMapper.builder(factory)
        .build();
~~~

API builder cụ thể phụ thuộc Jackson Core version. Hãy dùng API của version project đang quản lý.

Không thể phát hiện duplicate key bằng cách kiểm tra ObjectNode sau khi parse nếu parser đã hợp nhất các key trùng. Việc phát hiện phải diễn ra trong lúc parse.

## 30. Tree model không giữ nguyên mọi đặc tính lexical của number

Một JSON number có thể viết theo nhiều dạng:

~~~json
{
  "amountA": 1.0,
  "amountB": 1.00,
  "amountC": 1e0
}
~~~

Các giá trị có thể mang ý nghĩa số học tương đương nhưng cách viết lexical khác nhau. Khi parse thành node và serialize lại, Jackson có thể ghi ra một representation khác.

Nếu scale của decimal có ý nghĩa nghiệp vụ, dùng BigDecimal và cấu hình/test precision phù hợp. Nếu phải giữ nguyên token number gốc để ký số hoặc audit byte-level, tree model không đủ; cần giữ raw payload hoặc token representation thích hợp.

Không so sánh số tiền bằng double nếu yêu cầu precision chính xác. Dùng BigDecimal cho decimal nghiệp vụ và test scale/rounding theo contract.

## 31. Kiểm soát polymorphic type và dữ liệu không tin cậy

Field lạ đôi khi chứa discriminator hoặc metadata liên quan subtype. Không nên bật default typing rộng chỉ để deserialize được một payload có type name chưa biết.

Với dữ liệu không tin cậy:

- Dùng subtype allowlist rõ ràng.
- Dùng logical type id thay vì class name tùy ý khi có thể.
- Từ chối type id không được hỗ trợ theo contract.
- Không nạp class theo tên do payload gửi lên.
- Giới hạn kích thước/depth của JSON.
- Validate extension trước khi dùng trong logic nhạy cảm.

Unknown field được giữ trong JsonNode không nên tự động được diễn giải thành class Java. Chỉ chuyển sang DTO/subtype đã được ứng dụng cho phép.

## 32. Ví dụ hoàn chỉnh: đọc DTO, giữ extension và ghi lại

Model:

~~~java
public class CustomerEvent {
    private String eventId;
    private String customerId;

    private final Map<String, JsonNode> extensions =
            new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtensions() {
        return extensions;
    }
}
~~~

Mapper và payload:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .build();

String input = """
        {
          "eventId": "EVT-900",
          "customerId": "CUS-100",
          "preferredLanguage": "vi",
          "futureMetadata": {
            "priority": 2,
            "labels": ["vip", "mobile"]
          }
        }
        """;

CustomerEvent event =
        mapper.readValue(input, CustomerEvent.class);

event.setEventId("EVT-900-processed");

String output = mapper.writeValueAsString(event);
JsonNode result = mapper.readTree(output);
~~~

Kiểm tra extension:

~~~java
assertEquals("vi", result.path("preferredLanguage").asText());
assertEquals(
        2,
        result.path("futureMetadata").path("priority").asInt()
);
assertEquals(
        "mobile",
        result.path("futureMetadata").path("labels").get(1).asText()
);
~~~

Consumer có thể cập nhật field đã biết trong khi vẫn giữ cấu trúc field chưa nhận diện. Output là JSON tương đương về dữ liệu, không nhất thiết giống nguyên văn input.

## 33. Test tree access cho missing, null và value

Một test nên khóa rõ ba trạng thái:

~~~java
class JsonTreePresenceTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void distinguishesMissingNullAndValue() throws Exception {
        JsonNode missing = mapper.readTree("{}");
        JsonNode explicitNull = mapper.readTree(
                "{\"futureField\":null}"
        );
        JsonNode value = mapper.readTree(
                "{\"futureField\":\"new\"}"
        );

        assertFalse(missing.has("futureField"));
        assertTrue(missing.path("futureField").isMissingNode());

        assertTrue(explicitNull.has("futureField"));
        assertTrue(explicitNull.path("futureField").isNull());

        assertTrue(value.has("futureField"));
        assertEquals(
                "new",
                value.path("futureField").textValue()
        );
    }
}
~~~

Test này hữu ích cho PATCH, extension map và schema migration. Không dùng asText() một mình để quyết định property có xuất hiện hay không.

## 34. Test JsonAnySetter giữ field lạ

Test model:

~~~java
@Test
void capturesAndReemitsUnknownFields() throws Exception {
    String json = """
            {
              "eventId": "EVT-900",
              "customerId": "CUS-100",
              "futureFlag": true,
              "futureMetadata": {
                "sourceVersion": 5,
                "labels": ["a", "b"]
              }
            }
            """;

    CustomerEvent event =
            mapper.readValue(json, CustomerEvent.class);

    assertEquals("EVT-900", event.getEventId());
    assertTrue(event.getExtensions().get("futureFlag").asBoolean());

    String output = mapper.writeValueAsString(event);
    JsonNode tree = mapper.readTree(output);

    assertTrue(tree.path("futureFlag").asBoolean());
    assertEquals(
            5,
            tree.path("futureMetadata").path("sourceVersion").asInt()
    );
    assertEquals(
            2,
            tree.path("futureMetadata").path("labels").size()
    );
}
~~~

Test này xác nhận cả bước thu thập lẫn serialize lại. Nếu chỉ assert DTO được tạo thành công, test chưa chứng minh field lạ được giữ.

## 35. Test ignore unknown để xác nhận dữ liệu bị loại có chủ đích

Nếu model dùng JsonIgnoreProperties(ignoreUnknown = true), test nên ghi rõ rằng unknown property không xuất hiện lại:

~~~java
@Test
void ignoresUnknownFieldsWhenConfiguredToDiscardThem() throws Exception {
    String json = """
            {
              "customerId": "CUS-100",
              "futureFlag": true
            }
            """;

    SimpleCustomer customer =
            mapper.readValue(json, SimpleCustomer.class);

    String output = mapper.writeValueAsString(customer);
    JsonNode tree = mapper.readTree(output);

    assertFalse(tree.has("futureFlag"));
}
~~~

Tên test thể hiện rõ chính sách discard. Nếu sau này yêu cầu chuyển tiếp dữ liệu, đổi model sang extension map và cập nhật contract test.

## 36. Test unknown field ở nested DTO

Ví dụ nested model cũng có extension map:

~~~java
@Test
void preservesUnknownFieldsInsideNestedObject() throws Exception {
    String json = """
            {
              "customerId": "CUS-100",
              "address": {
                "city": "Da Nang",
                "districtCode": "D-07"
              }
            }
            """;

    CustomerWithAddress customer =
            mapper.readValue(json, CustomerWithAddress.class);

    String output = mapper.writeValueAsString(customer);
    JsonNode tree = mapper.readTree(output);

    assertEquals(
            "D-07",
            tree.path("address").path("districtCode").asText()
    );
}
~~~

Nếu chỉ DTO root có any-setter, test này cần được thiết kế để chứng minh nested field không bị âm thầm mất. Mỗi cấp object có thể có schema và chính sách unknown riêng.

## 37. Test extension collision và allowlist

Nếu extension map có reserved key, test từ chối xung đột:

~~~java
@Test
void rejectsReservedExtensionName() {
    assertThrows(
            IllegalArgumentException.class,
            () -> mapper.readValue("""
                    {
                      "eventId": "EVT-900",
                      "customerId": "CUS-100",
                      "schemaVersion": 99
                    }
                    """, CustomerEvent.class)
    );
}
~~~

Ví dụ chỉ phù hợp nếu model có kiểm tra reserved key tương ứng. Nếu ứng dụng chủ ý coi schemaVersion là property đã biết, hãy dùng DTO có property đó và test collision ở API cập nhật extension map thay vì kỳ vọng any-setter nhận property đã biết.

Test allowlist nên bao gồm một extension được phép và một extension bị từ chối. Điều này giữ chính sách rõ ràng khi producer thêm field mới.

## 38. Test tree migration mà không làm thay đổi node nguồn

Ví dụ:

~~~java
@Test
void migratesLegacyFieldOnACopy() throws Exception {
    ObjectNode original = (ObjectNode) mapper.readTree("""
            {
              "name": "Nguyen An",
              "region": "south"
            }
            """);

    ObjectNode migrated = original.deepCopy();

    JsonNode legacyName = migrated.remove("name");
    if (legacyName != null && !migrated.has("displayName")) {
        migrated.set("displayName", legacyName);
    }

    assertTrue(original.has("name"));
    assertFalse(original.has("displayName"));

    assertFalse(migrated.has("name"));
    assertEquals("Nguyen An", migrated.path("displayName").asText());
}
~~~

deepCopy() giúp migration không sửa tree nguồn. Điều này quan trọng nếu cùng payload được dùng để log, so sánh hoặc xử lý ở nhánh khác.

## 39. So sánh JsonNode trong test

Có thể parse expected và actual thành tree rồi so sánh cấu trúc:

~~~java
JsonNode expected = mapper.readTree("""
        {
          "eventId": "EVT-900",
          "futureFlag": true
        }
        """);

JsonNode actual = mapper.readTree(output);

assertEquals(expected, actual);
~~~

Cách này tránh phụ thuộc whitespace và pretty-printing. JSON object không nên được coi là có thứ tự property mang ý nghĩa; array vẫn có thứ tự phần tử.

Nếu lexical representation có ý nghĩa, ví dụ cần kiểm tra chính xác chuỗi number hoặc chữ ký, so sánh raw bytes/string theo contract và giữ payload gốc. Tree equality kiểm tra cấu trúc/value đã parse, không kiểm tra mọi ký tự đầu vào.

## 40. Chọn Map<String, JsonNode> hay JsonNode cho phần mở rộng?

| Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|
| Map<String, JsonNode> qua any-setter | Tích hợp DTO rõ, field đã biết vẫn là property Java | Cần any-getter để serialize lại; nested unknown phải xử lý riêng |
| ObjectNode cho toàn bộ object | Giữ cấu trúc JSON linh hoạt và dễ thêm/xóa field | Business code phải tự validate và truy cập node |
| JsonNode cho một property payload | Tách envelope ổn định khỏi payload thay đổi | Cần logic riêng khi muốn map payload thành DTO |
| Map<String, Object> | Dễ dùng với Java collection/scalar | Kiểu number và nested structure tổng quát hơn, conversion cần cẩn thận |
| Ignore unknown | Đơn giản, ít lưu dữ liệu | Không thể round-trip field đã bỏ |

Nếu schema phần lớn ổn định, extension map thường là lựa chọn cân bằng. Nếu toàn bộ payload biến động theo event type, giữ JsonNode có thể tự nhiên hơn.

## 41. Khi nào nên giữ raw JSON thay vì tree?

Dùng tree khi cần hiểu hoặc sửa cấu trúc JSON. Giữ raw JSON khi cần bảo toàn chính xác tài liệu đầu vào.

Ví dụ các yêu cầu cần raw bytes/text:

- Xác minh chữ ký số trên đúng byte sequence.
- Lưu audit evidence nguyên văn.
- Chuyển tiếp message byte-for-byte.
- Giữ formatting hoặc lexical number representation.
- Điều tra payload lỗi mà không muốn parser chuẩn hóa nội dung.

Một kiến trúc có thể giữ cả hai:

~~~java
public record ReceivedMessage(
        byte[] rawBody,
        JsonNode parsedBody
) {}
~~~

Hãy quản lý vòng đời và quyền truy cập raw body cẩn thận nếu payload chứa dữ liệu nhạy cảm. Không log raw body tùy tiện.

## 42. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng ignoreUnknown rồi mong field được giữ | Field biến mất khi serialize lại | Dùng any-setter hoặc JsonNode |
| Any-setter chỉ có ở root | Field lạ trong nested DTO vẫn bị bỏ/từ chối | Thêm extension handling ở cấp nested hoặc giữ subtree |
| Dùng asText() để phân biệt missing/null | Trạng thái bị gộp | Kiểm tra has, isNull, isMissingNode |
| Serialize tree rồi yêu cầu raw text giống hệt | Whitespace/number/escape có thể thay đổi | Lưu raw body riêng |
| Extension map cho phép key reserved | Duplicate/collision với property chuẩn | Namespace, allowlist và kiểm tra collision |
| Giữ mọi field không giới hạn | Memory/DoS risk | Giới hạn body, depth, count và kích thước |
| Bật default typing để xử lý type lạ | Rủi ro tạo subtype ngoài allowlist | Dùng type ID và subtype allowlist |
| Dùng Map<String,Object> mà không test number | Kiểu scalar/conversion có thể khác kỳ vọng | Dùng JsonNode hoặc BigDecimal và test |
| Chỉ test deserialize thành công | Không biết field lạ có bị mất không | Test serialize lại và so sánh tree |
| Dùng một any-setter để nhận mọi cấp lồng nhau | Hiểu sai phạm vi annotation | Xử lý từng object node hoặc nested DTO |

## 43. Quy trình thiết kế consumer forward-compatible

Khi consumer cần tiếp nhận producer có thể phát triển độc lập:

1. Xác định các field cốt lõi và kiểu Java ổn định.
2. Quyết định unknown field bị từ chối, bỏ qua hay giữ lại.
3. Nếu giữ, chọn extension map Map<String, JsonNode> hoặc subtree JsonNode.
4. Xác định chính sách riêng cho unknown field lồng nhau.
5. Dùng JsonAnySetter để thu thập và JsonAnyGetter để xuất lại khi phù hợp.
6. Bảo vệ tên field reserved và quy định collision semantics.
7. Quy định null, missing và empty trong extension.
8. Giới hạn kích thước, số field và độ sâu payload.
9. Dùng schemaVersion/migration khi ý nghĩa field thay đổi.
10. Test cả parse, giữ extension, serialize lại và payload cũ/mới.
11. Giữ raw payload riêng nếu cần byte-for-byte preservation.
12. Không tự diễn giải type metadata không được tin cậy.

Forward compatibility không có nghĩa là chấp nhận mọi cấu trúc mà không kiểm soát. Consumer cần giữ những gì contract yêu cầu và từ chối hoặc cô lập dữ liệu không an toàn.

## 44. Ghi nhớ

JsonNode là nền tảng của Jackson Tree Model; ObjectNode và ArrayNode cho phép truy cập và thay đổi object/array linh hoạt. readTree() parse JSON thành cây, treeToValue() bind node thành DTO và valueToTree() tạo cây từ Java value. Dùng has(), hasNonNull(), get() và path() đúng semantics để phân biệt field thiếu, explicit null và value.

JsonIgnoreProperties(ignoreUnknown = true) hoặc FAIL_ON_UNKNOWN_PROPERTIES = false chỉ giúp bỏ qua field lạ; dữ liệu bị bỏ sẽ không tự xuất hiện lại. Nếu cần giữ field chưa nhận diện, dùng JsonAnySetter để thu thập và JsonAnyGetter để serialize lại, thường lưu dưới dạng Map<String, JsonNode>. Unknown field ở nested object phải được xử lý ở đúng cấp.

Tree round-trip giữ cấu trúc/value đã parse chứ không giữ nguyên mọi byte/lexical detail. Nếu cần raw preservation, lưu raw body riêng. Cuối cùng, bảo vệ extension key, giới hạn payload, kiểm soát duplicate property và polymorphic type, version hóa schema khi cần, và test cả việc giữ lẫn phát lại field chưa nhận diện.
