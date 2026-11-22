# Phân biệt Map có kiểu và đối tượng không định kiểu

Khi đọc JSON bằng Jackson, ứng dụng có thể chọn một mô hình Java có kiểu cụ thể, chẳng hạn Map<String, Customer>, hoặc yêu cầu Jackson đọc dữ liệu vào kiểu tổng quát Object. Hai cách này đều có thể biểu diễn một JSON object, nhưng chúng khác nhau về lượng thông tin kiểu mà Jackson có thể sử dụng.

**Map có kiểu** mô tả rõ kiểu của key và value, giúp Jackson chuyển đổi từng giá trị theo một kiểu Java xác định. **Đối tượng không định kiểu** thường dùng Object, Map<String, Object> hoặc Map.class; Jackson phải suy ra cấu trúc Java từ hình dạng JSON và thường tạo Map, List cùng các kiểu scalar như String, Boolean và kiểu số.

Phân biệt hai cách giúp chọn đúng mô hình khi đọc dữ liệu API, xử lý JSON linh hoạt, chuyển đổi dữ liệu và tránh lỗi ép kiểu lúc chạy.

## 1. JSON object và các cách biểu diễn trong Java

JSON object là tập hợp các cặp tên thuộc tính và giá trị:

~~~json
{
  "user-01": {
    "id": 1,
    "name": "Mai"
  },
  "user-02": {
    "id": 2,
    "name": "An"
  }
}
~~~

Nếu mỗi giá trị luôn là một User, có thể mô hình hóa bằng Map<String, User>. Nếu chưa biết kiểu của từng giá trị, có thể đọc vào Map<String, Object>.

~~~java
Map<String, User> usersByCode;
Map<String, Object> data;
~~~

Hai khai báo này đều có key kiểu String, nhưng kiểu value khác nhau:

| Kiểu Java | Ý nghĩa |
|---|---|
| Map<String, User> | Mỗi value phải được ánh xạ thành User |
| Map<String, List<User>> | Mỗi value phải là danh sách User |
| Map<String, Integer> | Mỗi value phải là số nguyên Integer |
| Map<String, Object> | Mỗi value có thể là một kiểu dữ liệu khác nhau |
| Map hoặc Map.class | Map raw, không khai báo kiểu key/value ở mức generic |
| Object | Jackson tự chọn biểu diễn Java dựa trên loại giá trị JSON |

Trong Java, generic type giúp compiler kiểm tra cách sử dụng dữ liệu. Khi truyền kiểu đích cho Jackson, generic type còn cho biết cần tạo đối tượng nào cho từng value.

## 2. Đọc Map có kiểu bằng TypeReference

Giả sử JSON là một object trong đó mỗi key là mã người dùng và mỗi value là một object có cấu trúc User:

~~~json
{
  "U01": {
    "id": 1,
    "name": "Mai"
  },
  "U02": {
    "id": 2,
    "name": "An"
  }
}
~~~

Mô hình:

~~~java
public class User {
    private Long id;
    private String name;

    public User() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
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

Đọc thành Map có kiểu:

~~~java
ObjectMapper mapper = new ObjectMapper();

Map<String, User> usersByCode = mapper.readValue(
    json,
    new TypeReference<Map<String, User>>() {}
);

User user = usersByCode.get("U01");
System.out.println(user.getName());
~~~

TypeReference giữ thông tin generic Map<String, User> thông qua anonymous subclass. Jackson biết key là String và mỗi value là User, vì vậy nó tạo User cho từng object con. Ứng dụng có thể gọi getName() trực tiếp mà không phải ép kiểu từ Object.

Nếu khai báo biến đích là Map<String, User> nhưng truyền Map.class cho readValue, thông tin User đã bị mất ở ranh giới Jackson. Kiểu của biến Java ở bên trái phép gán không được dùng để suy ra generic type cho phương thức đọc.

~~~java
// Không đủ thông tin kiểu phần tử:
Map<String, User> users = mapper.readValue(json, Map.class);
~~~

Đoạn mã trên có thể tạo cảnh báo unchecked assignment. Các value thường được đọc theo quy tắc untyped và trở thành Map lồng nhau thay vì User. Dùng TypeReference hoặc JavaType khi cần giữ generic type.

## 3. Đọc đối tượng không định kiểu bằng Object

Khi kiểu dữ liệu chưa biết trước, có thể yêu cầu Jackson đọc vào Object:

~~~java
Object value = mapper.readValue(json, Object.class);
~~~

Jackson dùng hình dạng của JSON để chọn kiểu Java tổng quát. Với cấu hình mặc định thường gặp của Jackson Databind, ánh xạ untyped có dạng:

| Giá trị JSON | Kiểu Java thường được tạo |
|---|---|
| Object {...} | Map, thường là LinkedHashMap<String, Object> |
| Array [...] | List, thường là ArrayList<Object> |
| String | String |
| Boolean | Boolean |
| Số nguyên | Integer, Long hoặc BigInteger tùy độ lớn và cấu hình |
| Số thập phân | Thường là Double; có thể dùng BigDecimal theo cấu hình |
| null | null |

Ví dụ:

~~~java
String json = """
    {
      "name": "Mai",
      "age": 25,
      "active": true,
      "tags": ["java", "json"],
      "address": {
        "city": "Ho Chi Minh City"
      }
    }
    """;

Object value = mapper.readValue(json, Object.class);
~~~

Đối tượng value thường là một LinkedHashMap. Bên trong có thể có:

- name: String.
- age: Integer nếu giá trị nằm trong phạm vi phù hợp.
- active: Boolean.
- tags: ArrayList chứa String.
- address: LinkedHashMap lồng nhau.

Jackson không tự tạo lớp Address hoặc một DTO nghiệp vụ khác vì kiểu đích chỉ là Object. Nó không có đủ thông tin để biết object con đó đại diện cho lớp Java nào.

### Duyệt dữ liệu untyped

Có thể kiểm tra kiểu trước khi sử dụng giá trị:

~~~java
Object value = mapper.readValue(json, Object.class);

if (value instanceof Map<?, ?> root) {
    Object nameValue = root.get("name");
    if (nameValue instanceof String name) {
        System.out.println(name);
    }

    Object tagsValue = root.get("tags");
    if (tagsValue instanceof List<?> tags) {
        for (Object tag : tags) {
            System.out.println(tag);
        }
    }
}
~~~

Pattern matching với instanceof giúp kiểm tra kiểu trước khi ép kiểu. Cách này phù hợp khi cấu trúc JSON thay đổi hoặc một số trường có thể mang nhiều dạng giá trị.

## 4. Map<String, Object> không phải Map có value type cụ thể

Khai báo Map<String, Object> có vẻ đã có generic type, nhưng chỉ kiểu key được xác định cụ thể. Object có nghĩa value có thể là bất kỳ kiểu Java nào mà Jackson tạo ra theo quy tắc untyped.

~~~java
Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
~~~

Kết quả có thể là:

~~~text
Map<String, Object>
  ├── "name"    -> String
  ├── "age"     -> Integer
  ├── "active"  -> Boolean
  ├── "tags"    -> List<Object>
  └── "address" -> Map<String, Object>
~~~

Đây là một cấu trúc có key được định kiểu nhưng value vẫn không định kiểu. Nó khác với Map<String, User>, nơi tất cả value được chuyển thành User.

Ví dụ truy cập object con:

~~~java
Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

Object addressValue = data.get("address");
if (addressValue instanceof Map<?, ?> address) {
    Object cityValue = address.get("city");
    if (cityValue instanceof String city) {
        System.out.println(city);
    }
}
~~~

Không nên viết phép ép kiểu trực tiếp nếu không chắc hình dạng dữ liệu:

~~~java
Map<String, Object> address =
    (Map<String, Object>) data.get("address");
~~~

Phép ép kiểu trên có thể ném ClassCastException nếu address là null, một chuỗi hoặc một giá trị khác. Với dữ liệu không tin cậy hoặc cấu trúc không cố định, nên kiểm tra instanceof ở từng cấp.

## 5. So sánh Map có kiểu, Map untyped và Object

Ba kiểu đích dưới đây thể hiện mức độ thông tin khác nhau:

~~~java
Map<String, User> typedUsers;
Map<String, Object> dynamicData;
Object arbitraryValue;
~~~

| Tiêu chí | Map<String, User> | Map<String, Object> | Object |
|---|---|---|---|
| Kiểu key | String | String | Không áp dụng nếu root không phải Map |
| Kiểu value | User | Bất kỳ kiểu untyped | Bất kỳ kiểu untyped |
| JSON object ở root | Map key String, value User | Map key String, value động | Thường thành LinkedHashMap |
| JSON array ở root | Không khớp kiểu đích thông thường | Không khớp Map | Thường thành ArrayList |
| Truy cập thuộc tính User | Gọi trực tiếp method User | Cần kiểm tra/ép kiểu | Cần kiểm tra/ép kiểu |
| Phù hợp | Cấu trúc value ổn định | Object có trường linh hoạt | Chưa biết loại root hoặc dữ liệu động |

Nếu biết JSON luôn là object có các giá trị User, hãy dùng Map có kiểu. Nếu mỗi key có thể trỏ đến chuỗi, số, mảng, object hoặc null, Map<String, Object> linh hoạt hơn. Nếu root cũng có thể thay đổi giữa object, array và scalar, Object thể hiện rõ nhất tính không xác định đó.

## 6. Raw Map và generic type bị mất

Java có thể khai báo Map raw:

~~~java
Map data = mapper.readValue(json, Map.class);
~~~

Raw Map không cung cấp kiểu key và value cho compiler hoặc Jackson. Với JSON object, Jackson thường tạo Map chứa key String và value untyped. Khi lấy giá trị, kết quả có kiểu Object:

~~~java
Object customer = data.get("customer");
~~~

So với:

~~~java
Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
~~~

Khai báo thứ hai vẫn cho phép value linh hoạt, nhưng compiler biết key là String và giúp hạn chế các thao tác sai kiểu trên key. Vì vậy, nên tránh raw Map trong mã ứng dụng trừ khi phải tương tác với API cũ hoặc một thư viện không hỗ trợ generic.

Đối với danh sách cũng có vấn đề tương tự:

~~~java
List values = mapper.readValue(jsonArray, List.class);
~~~

Jackson không biết phần tử cần là User, nên các object trong danh sách thường trở thành Map. Muốn có List<User>, dùng new TypeReference<List<User>>() {} hoặc JavaType tương ứng.

## 7. Đọc Map lồng nhau có kiểu cụ thể

Một Map có thể chứa value là collection hoặc một Map khác. Ví dụ JSON nhóm người dùng theo phòng ban:

~~~json
{
  "engineering": [
    {"id": 1, "name": "Mai"},
    {"id": 2, "name": "An"}
  ],
  "sales": [
    {"id": 3, "name": "Binh"}
  ]
}
~~~

Kiểu Java tương ứng:

~~~java
Map<String, List<User>> usersByDepartment = mapper.readValue(
    json,
    new TypeReference<Map<String, List<User>>>() {}
);
~~~

Jackson xử lý từng cấp:

1. Root là JSON object, tương ứng Map.
2. Tên phòng ban trở thành key String.
3. Mỗi value là JSON array, tương ứng List<User>.
4. Mỗi phần tử của array là JSON object, được ánh xạ thành User.

Có thể truy cập dữ liệu mà không cần ép kiểu:

~~~java
List<User> engineers = usersByDepartment.get("engineering");
User firstEngineer = engineers.get(0);
System.out.println(firstEngineer.getName());
~~~

Với cấu trúc sâu hơn, TypeReference có thể mô tả nhiều cấp:

~~~java
Map<String, Map<String, List<User>>> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Map<String, List<User>>>>() {}
);
~~~

Kiểu càng sâu thì DTO hoặc lớp wrapper có thể giúp mã dễ hiểu hơn. Map lồng nhau phù hợp khi tên key là dữ liệu động; nếu các nhánh có ý nghĩa cố định, DTO thường thể hiện hợp đồng rõ hơn.

## 8. Dùng JavaType khi generic type được tạo lúc chạy

TypeReference thuận tiện khi kiểu đích được biết tại thời điểm biên dịch. Nếu kiểu value được truyền vào như tham số, có thể tạo JavaType bằng TypeFactory:

~~~java
JavaType mapType = mapper.getTypeFactory()
    .constructMapType(Map.class, String.class, User.class);

Map<String, User> users = mapper.readValue(json, mapType);
~~~

Với Map có value là List<User>:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory
    .constructCollectionType(List.class, User.class);

JavaType usersByCodeType = typeFactory
    .constructMapType(
        Map.class,
        String.class,
        userListType
    );

Map<String, List<User>> usersByCode =
    mapper.readValue(json, usersByCodeType);
~~~

Có thể đóng gói thành hàm tiện ích:

~~~java
public <T> Map<String, T> readMap(
        String json,
        Class<T> valueType) throws JsonProcessingException {

    JavaType mapType = mapper.getTypeFactory()
        .constructMapType(Map.class, String.class, valueType);

    return mapper.readValue(json, mapType);
}
~~~

Hàm này đọc được Map<String, User>, Map<String, Product> hoặc kiểu value khác. Nếu value cũng là generic type phức tạp, hãy tạo JavaType của value trước rồi dùng overload nhận JavaType cho key và value.

## 9. Map có key không phải String

Theo cú pháp JSON, tên thuộc tính của object luôn là chuỗi. Tuy nhiên, Jackson có thể chuyển chuỗi key đó sang kiểu key Java khi kiểu đích yêu cầu.

Ví dụ JSON:

~~~json
{
  "101": {"name": "Keyboard"},
  "205": {"name": "Mouse"}
}
~~~

Có thể đọc thành Map có key Integer:

~~~java
Map<Integer, Product> products = mapper.readValue(
    json,
    new TypeReference<Map<Integer, Product>>() {}
);
~~~

Jackson sử dụng key deserializer phù hợp để chuyển tên thuộc tính "101" thành Integer 101. Việc chuyển đổi thành công phụ thuộc kiểu key và key deserializer đã đăng ký. Nếu key không thể chuyển thành kiểu đích, thao tác đọc có thể thất bại.

Một số kiểu key thường được hỗ trợ có thể gồm String, số, enum và các kiểu có key deserializer tương ứng. Với key là kiểu nghiệp vụ riêng, có thể đăng ký KeyDeserializer để chuyển tên JSON thành đối tượng key:

~~~java
public class RegionCode {
    private final String value;

    public RegionCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Key deserializer tùy chỉnh:

~~~java
public class RegionCodeKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(
            String key,
            DeserializationContext context) {
        return new RegionCode(key);
    }
}
~~~

Đăng ký key deserializer bằng module:

~~~java
SimpleModule module = new SimpleModule();
module.addKeyDeserializer(
    RegionCode.class,
    new RegionCodeKeyDeserializer()
);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
~~~

Khi ghi Map có key không phải String, Jackson cũng cần key serializer tương ứng để chuyển key Java thành tên thuộc tính JSON. JSON object không thể giữ một object phức tạp làm key theo nghĩa Java Map. Nếu key là cấu trúc phức tạp, nên biểu diễn dữ liệu dưới dạng array các object có trường key và value:

~~~json
[
  {
    "key": {"country": "VN", "region": "HCM"},
    "value": 120
  }
]
~~~

## 10. Đọc kiểu không định kiểu với độ chính xác số

Khi giá trị được đọc vào Object, Jackson phải chọn một kiểu số Java mà không có khai báo cụ thể từ người dùng. Mặc định, số nguyên thường được chọn thành Integer hoặc Long nếu nằm trong phạm vi; số nguyên quá lớn có thể thành BigInteger. Số có phần thập phân thường thành Double.

Nếu ứng dụng cần giữ độ chính xác thập phân, có thể bật USE_BIG_DECIMAL_FOR_FLOATS:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .build();
~~~

Nếu cần biểu diễn số nguyên không giới hạn bằng BigInteger hoặc muốn dùng Long cho số nguyên untyped, có thể xem các feature USE_BIG_INTEGER_FOR_INTS và USE_LONG_FOR_INTS theo phiên bản Jackson đang dùng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .build();
~~~

Các feature này chủ yếu tác động đến số được đọc vào kiểu không định kiểu như Object hoặc Number. Nếu đích đã là BigDecimal, Long hoặc Integer trong Map có kiểu, Jackson sẽ chuyển đổi theo kiểu đích đó và các quy tắc coercion liên quan.

Không nên dùng Double cho dữ liệu tiền tệ cần độ chính xác thập phân tuyệt đối. Với Map có kiểu, khai báo value là BigDecimal; với Map untyped, bật feature phù hợp hoặc chuyển đổi có kiểm soát sau khi đọc.

## 11. Object trong DTO và Map có value là Object

Một DTO có thể chứa thuộc tính kiểu Object:

~~~java
public class Event {
    private String type;
    private Object payload;

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Object getPayload() {
        return payload;
    }

    public void setPayload(Object payload) {
        this.payload = payload;
    }
}
~~~

Nếu JSON là:

~~~json
{
  "type": "user-created",
  "payload": {
    "id": 12,
    "name": "Mai"
  }
}
~~~

Khi đọc thành Event, payload thường là một Map untyped. Jackson không tự biết payload phải là User chỉ dựa vào giá trị type ở một trường khác. Nếu muốn payload là kiểu cụ thể, có một số cách:

- Dùng lớp generic như Event<User> và truyền TypeReference đầy đủ.
- Dùng các subtype đã khai báo với metadata đa hình rõ ràng.
- Đọc payload thành JsonNode rồi chuyển sang kiểu phù hợp dựa trên trường type.
- Viết custom deserializer nếu quy tắc chọn kiểu có nhiều điều kiện.

Ví dụ dùng generic wrapper:

~~~java
public class Event<T> {
    private String type;
    private T payload;

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public T getPayload() {
        return payload;
    }

    public void setPayload(T payload) {
        this.payload = payload;
    }
}
~~~

~~~java
Event<User> event = mapper.readValue(
    json,
    new TypeReference<Event<User>>() {}
);
~~~

Trong trường hợp này, Jackson biết payload có kiểu User từ kiểu generic được cung cấp cho root.

## 12. Khi nào nên dùng JsonNode thay cho Object?

Nếu dữ liệu chưa có schema cố định và ứng dụng cần kiểm tra cấu trúc trước khi quyết định kiểu Java, JsonNode thường phù hợp hơn Object hoặc Map<String, Object>.

~~~java
JsonNode root = mapper.readTree(json);

JsonNode payload = root.path("payload");
if (payload.isObject()) {
    JsonNode idNode = payload.path("id");
    if (idNode.canConvertToLong()) {
        long id = idNode.longValue();
        System.out.println(id);
    }
}
~~~

JsonNode giữ cấu trúc tree với các node riêng cho object, array, string, number, boolean và null. Ứng dụng có thể kiểm tra isObject(), isArray(), isTextual(), isNumber() hoặc isNull() mà không phải ép kiểu Java từ Object.

Sau khi xác định được kiểu dữ liệu, có thể chuyển node thành DTO:

~~~java
User user = mapper.treeToValue(payload, User.class);
~~~

Hoặc chuyển sang một kiểu generic bằng convertValue:

~~~java
Map<String, User> users = mapper.convertValue(
    root.get("users"),
    new TypeReference<Map<String, User>>() {}
);
~~~

JsonNode hữu ích khi cần đọc một phần JSON hoặc cấu trúc thay đổi theo loại sự kiện. Nếu cấu trúc đã biết và ổn định, binding trực tiếp vào DTO hoặc Map có kiểu thường đơn giản hơn.

## 13. Chuyển đổi từ Map untyped sang Map có kiểu

Có thể ứng dụng nhận dữ liệu qua một tầng tổng quát trước, sau đó chuyển phần cần thiết sang kiểu cụ thể. Jackson hỗ trợ convertValue để chuyển đổi giữa các object Java theo cơ chế databinding:

~~~java
Map<String, Object> raw = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

Map<String, User> users = mapper.convertValue(
    raw,
    new TypeReference<Map<String, User>>() {}
);
~~~

convertValue hữu ích khi nguồn dữ liệu đã là object Java hoặc Map và muốn ánh xạ sang kiểu đích. Nó không yêu cầu serialize thành chuỗi JSON rồi parse lại bằng hai lời gọi riêng. Tuy nhiên, việc chuyển đổi vẫn có thể thất bại nếu cấu trúc hoặc giá trị không tương thích với kiểu đích.

Có thể chuyển riêng một value:

~~~java
Object rawUser = raw.get("user");
User user = mapper.convertValue(rawUser, User.class);
~~~

Nếu rawUser là Map lồng nhau, Jackson có thể ánh xạ Map đó sang User dựa trên tên và kiểu thuộc tính. Cần xử lý trường hợp rawUser null hoặc không phải cấu trúc mong đợi trước khi chuyển đổi.

## 14. Ghi Map có kiểu và Map không định kiểu thành JSON

Khi ghi, cả Map có kiểu và Map untyped đều được tuần tự hóa thành JSON object. Jackson duyệt các entry và ghi key cùng value theo serializer tương ứng.

Map có kiểu:

~~~java
Map<String, User> users = new LinkedHashMap<>();
users.put("U01", new User(1L, "Mai"));

String json = mapper.writeValueAsString(users);
~~~

Map untyped:

~~~java
Map<String, Object> data = new LinkedHashMap<>();
data.put("name", "Mai");
data.put("age", 25);
data.put("tags", List.of("java", "json"));
data.put("address", Map.of("city", "Ho Chi Minh City"));

String json = mapper.writeValueAsString(data);
~~~

JSON đầu ra đều là object. Khác biệt nằm ở mô hình và thông tin kiểu phía Java. Với Map untyped, mỗi value có thể là scalar, List, Map con hoặc DTO; Jackson ghi theo kiểu thực tế của value. Khi đọc lại vào Object hoặc Map<String, Object>, các object và array lại trở thành Map và List tổng quát.

Nếu value là DTO nhưng Map khai báo Map<String, Object>, Jackson vẫn có thể ghi các thuộc tính của DTO theo serializer runtime. Tuy nhiên, khi đọc lại vào Map<String, Object>, Jackson không tự khôi phục DTO ban đầu nếu không có thông tin kiểu rõ ràng.

## 15. Map có value là interface hoặc lớp abstract

Map có generic type chưa chắc đã đủ để tạo value nếu kiểu value là interface hoặc abstract class:

~~~java
Map<String, Payment> payments;
~~~

Nếu Payment là interface hoặc abstract class, Jackson cần biết subtype cụ thể cho từng value. Có thể khai báo polymorphic type metadata với danh sách subtype được cho phép:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
    // Các thuộc tính chung
}
~~~

JSON:

~~~json
{
  "online": {
    "kind": "card",
    "amount": 120.0,
    "cardLast4": "1234"
  },
  "counter": {
    "kind": "cash",
    "amount": 50.0,
    "currency": "VND"
  }
}
~~~

Đọc:

~~~java
Map<String, Payment> payments = mapper.readValue(
    json,
    new TypeReference<Map<String, Payment>>() {}
);
~~~

Discriminator kind giúp Jackson chọn CardPayment hoặc CashPayment cho từng value. Nên khai báo subtype tường minh và kiểm soát các loại được phép. Tránh bật default typing rộng để đọc tên lớp tùy ý từ JSON không tin cậy.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Value đọc từ Map là LinkedHashMap thay vì DTO | Dùng Map.class hoặc Map<String, Object> | Dùng TypeReference<Map<String, User>> |
| Ép kiểu value gây ClassCastException | Giá trị thực tế không phải kiểu được ép | Kiểm tra instanceof hoặc đọc bằng kiểu đích rõ ràng |
| Map lồng nhau không có generic type | Khai báo raw Map hoặc Object | Khai báo TypeReference/JavaType đầy đủ |
| JSON array nhưng kiểu đích là Map | Root JSON không khớp kiểu đích | Dùng List, array hoặc Object/JsonNode |
| JSON object nhưng kiểu đích là List | Root JSON không khớp kiểu đích | Dùng DTO hoặc Map tương ứng |
| Key số không chuyển được | Key JSON không hợp lệ với kiểu key Java | Kiểm tra dữ liệu hoặc dùng KeyDeserializer |
| Value interface không tạo được | Jackson không biết subtype cụ thể | Khai báo subtype và type metadata |
| Số thập phân mất độ chính xác | Đọc vào Object thành Double | Dùng BigDecimal hoặc USE_BIG_DECIMAL_FOR_FLOATS |
| Map untyped đọc lại không còn DTO ban đầu | JSON không chứa thông tin kiểu cụ thể | Dùng DTO/generic type hoặc discriminator có kiểm soát |

Một nguyên tắc hữu ích là không dựa vào kiểu biến ở bên trái để kỳ vọng Jackson tự suy luận generic type. Kiểu cần tạo phải được truyền trực tiếp vào readValue, readerFor hoặc convertValue.

## 17. Chọn mô hình dữ liệu phù hợp

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Key động, mọi value cùng một DTO | Map<String, User> |
| Key động, value là danh sách DTO | Map<String, List<User>> |
| Key động, mỗi value có thể khác loại | Map<String, Object> |
| Root có thể là object, array hoặc scalar | Object hoặc JsonNode |
| Cần kiểm tra cấu trúc trước khi chọn DTO | JsonNode |
| Hợp đồng dữ liệu cố định, có ý nghĩa nghiệp vụ | DTO hoặc generic wrapper |
| Dữ liệu lớn cần đọc tuần tự | ObjectReader và MappingIterator |
| Key Java có kiểu đặc biệt | Key serializer/deserializer |

Map có kiểu phù hợp khi cấu trúc key/value tương đối ổn định nhưng tên key được quyết định bởi dữ liệu, ví dụ mã người dùng, mã sản phẩm hoặc tên nhóm. DTO phù hợp khi các thuộc tính có tên cố định và cần biểu diễn hợp đồng rõ ràng. Map untyped phù hợp khi cấu trúc thay đổi hoặc cần xử lý dữ liệu linh hoạt; JsonNode phù hợp khi cần kiểm tra cây JSON trước khi quyết định kiểu.

## 18. Ví dụ tổng hợp: đọc dữ liệu có cả Map typed và untyped

Giả sử API trả về một object chứa danh sách người dùng theo mã và metadata linh hoạt:

~~~json
{
  "users": {
    "U01": {
      "id": 1,
      "name": "Mai"
    },
    "U02": {
      "id": 2,
      "name": "An"
    }
  },
  "metadata": {
    "source": "partner-api",
    "page": 1,
    "labels": ["active", "verified"]
  }
}
~~~

Có thể dùng DTO wrapper để định kiểu phần users và giữ metadata linh hoạt:

~~~java
public class UserDirectory {
    private Map<String, User> users;
    private Map<String, Object> metadata;

    public Map<String, User> getUsers() {
        return users;
    }

    public void setUsers(Map<String, User> users) {
        this.users = users;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }
}
~~~

Đọc dữ liệu:

~~~java
UserDirectory directory = mapper.readValue(
    json,
    UserDirectory.class
);

User firstUser = directory.getUsers().get("U01");
System.out.println(firstUser.getName());

Object source = directory.getMetadata().get("source");
if (source instanceof String sourceName) {
    System.out.println(sourceName);
}
~~~

Jackson tạo các value của users thành User vì kiểu thuộc tính đã được khai báo. Các value trong metadata được đọc theo quy tắc untyped: source thành String, page thành kiểu số phù hợp và labels thành List.

Khi ghi lại:

~~~java
String output = mapper
    .writerWithDefaultPrettyPrinter()
    .writeValueAsString(directory);
~~~

Jackson ghi users theo cấu trúc User và ghi metadata theo kiểu thực tế của từng value. Cách kết hợp này hữu ích khi một phần hợp đồng ổn định và một phần metadata cần linh hoạt.

Khi lựa chọn kiểu đích cho Jackson, hãy xác định phần nào của JSON đã có schema rõ ràng và phần nào còn động. Cung cấp kiểu cụ thể cho dữ liệu ổn định; chỉ dùng Object hoặc Map<String, Object> ở những vị trí thật sự cần linh hoạt. Cách làm này giữ được khả năng mở rộng mà vẫn tận dụng kiểm tra kiểu và tính rõ ràng của Java.
