# Chuyển giữa POJO, Map và cây JSON bằng convertValue

Trong một ứng dụng Java, cùng một dữ liệu có thể cần xuất hiện dưới nhiều hình thức: một DTO có kiểu rõ ràng, một `Map<String, Object>` linh hoạt, hoặc một cây JSON để truy cập và chỉnh sửa theo tên field. Jackson Databind cung cấp `ObjectMapper.convertValue()` để chuyển đổi trực tiếp giữa những biểu diễn này trong bộ nhớ.

`convertValue()` hữu ích khi cần chuyển một POJO thành Map, biến Map thành DTO, chuyển DTO thành `JsonNode`, hoặc ánh xạ một cấu trúc JSON tree sang kiểu Java có generic. Phương thức sử dụng serialization/deserialization machinery của mapper với một biểu diễn token trung gian, không cần tạo chuỗi JSON rồi parse lại.

Tuy nhiên, đây vẫn là một phép chuyển đổi theo quy tắc data binding của Jackson. Kết quả phụ thuộc serializer, deserializer, annotation, module, naming strategy, kiểu đích và cấu hình mapper. `convertValue()` không phải phép ép kiểu Java, không phải validation nghiệp vụ và cũng không phải bản sao sâu tổng quát cho mọi object.

## 1. convertValue() làm gì?

`ObjectMapper.convertValue()` nhận một object nguồn và chuyển nó thành một kiểu đích được chỉ định. Các overload thường dùng:

```java
<T> T convertValue(Object fromValue, Class<T> toValueType)
<T> T convertValue(Object fromValue, TypeReference<T> toValueTypeRef)
<T> T convertValue(Object fromValue, JavaType toValueType)
```

Ví dụ chuyển `User` thành Map:

```java
Map<String, Object> values = mapper.convertValue(
    user,
    new TypeReference<Map<String, Object>>() {}
);
```

Hoặc chuyển Map thành POJO:

```java
User user = mapper.convertValue(values, User.class);
```

Về mặt khái niệm, Jackson serialize object nguồn thành token rồi deserialize các token đó theo kiểu đích. Jackson dùng cấu trúc trung gian trong bộ nhớ (thường là `TokenBuffer`) thay vì phải ghi toàn bộ JSON ra `String` rồi đọc lại. Vì vậy, phép chuyển đổi phù hợp với các thao tác in-memory.

### 1.1. convertValue() không phải phép cast

Ép kiểu Java chỉ thay đổi cách compiler nhìn một reference và không chuyển đổi cấu trúc object:

```java
Object source = user;
User sameReference = (User) source;
```

`convertValue()` thực hiện data binding. Ví dụ, một Map có key `id` và `name` có thể được ánh xạ thành một `User` mới:

```java
Map<String, Object> source = Map.of(
    "id", 25,
    "name", "An"
);

User user = mapper.convertValue(source, User.class);
```

Map không trở thành `User` bằng cast; Jackson đọc các entry và gán chúng theo cấu hình deserialization của `User`.

### 1.2. Không cần tạo JSON String trung gian

Không cần viết:

```java
String json = mapper.writeValueAsString(user);
Map<String, Object> values = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
```

Khi chỉ cần chuyển biểu diễn trong bộ nhớ, có thể viết:

```java
Map<String, Object> values = mapper.convertValue(
    user,
    new TypeReference<Map<String, Object>>() {}
);
```

Cách thứ hai tránh tạo và parse một chuỗi JSON tường minh. Nó vẫn đi qua serializer và deserializer của Jackson, nên các quy tắc data binding liên quan vẫn có hiệu lực.

## 2. Chuyển POJO thành Map

Một ứng dụng có thể cần biến DTO thành Map để tạo payload động, ghi audit metadata, truyền dữ liệu vào template hoặc làm việc với một API nội bộ nhận key/value.

Giả sử DTO:

```java
public class User {
    private long id;
    private String name;
    private String email;

    public User() {
    }

    public User(long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
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

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Chuyển sang Map:

```java
User user = new User(25L, "An", "an@example.com");

Map<String, Object> map = mapper.convertValue(
    user,
    new TypeReference<Map<String, Object>>() {}
);
```

Map kết quả có các entry tương ứng với property được Jackson serialize, ví dụ:

```java
{
    "id" -> 25,
    "name" -> "An",
    "email" -> "an@example.com"
}
```

Thứ tự entry phụ thuộc cấu hình serializer và kiểu Map đích. Nếu cần thứ tự ổn định, chỉ định kiểu đích cụ thể như `LinkedHashMap`:

```java
LinkedHashMap<String, Object> map = mapper.convertValue(
    user,
    new TypeReference<LinkedHashMap<String, Object>>() {}
);
```

Không nên dựa vào thứ tự Map nếu hợp đồng nghiệp vụ không yêu cầu. JSON object về mặt dữ liệu thường được xem là tập các cặp tên/giá trị, không phải danh sách có thứ tự.

### 2.1. Annotation serialize ảnh hưởng Map kết quả

Vì bước đầu của `convertValue()` sử dụng serializer của object nguồn, các annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonInclude` và naming strategy có thể ảnh hưởng key/value trong Map.

Ví dụ:

```java
public class Account {
    @JsonProperty("account_id")
    private long id;

    private String owner;

    @JsonIgnore
    private String internalSecret;
}
```

Khi chuyển `Account` thành `Map<String, Object>`, key có thể là `account_id`, `owner`; `internalSecret` bị bỏ do `@JsonIgnore`. Đây là Map theo representation mà Jackson serialize, không nhất thiết là bản sao mọi field Java.

### 2.2. POJO lồng nhau thành Map lồng nhau

Nếu DTO có object con:

```java
public class Order {
    private long id;
    private Customer customer;
    private List<OrderLine> lines;

    // Getter và setter
}
```

Chuyển sang kiểu Map tổng quát:

```java
Map<String, Object> orderMap = mapper.convertValue(
    order,
    new TypeReference<Map<String, Object>>() {}
);
```

Các object con và collection cũng được serialize theo serializer của chúng. Map kết quả có thể chứa Map lồng nhau, List và scalar:

```text
Map
 ├── "id"       -> Number
 ├── "customer" -> Map<String, Object>
 └── "lines"    -> List<Map<String, Object>>
```

Nếu muốn kiểu Map cụ thể ở mọi tầng, có thể dùng `JavaType` lồng nhau; nếu chỉ cần truy cập dữ liệu linh hoạt, `Map<String, Object>` thường đủ.

## 3. Chuyển Map thành POJO

Một nguồn dữ liệu như cache, cấu hình, message hoặc kết quả xử lý động có thể được biểu diễn bằng Map. `convertValue()` giúp ánh xạ Map sang DTO:

```java
Map<String, Object> source = new HashMap<>();
source.put("id", 25);
source.put("name", "An");
source.put("email", "an@example.com");

User user = mapper.convertValue(source, User.class);
```

Jackson dùng property metadata và cơ chế tạo object của `User` để gán giá trị. DTO có thể dùng constructor mặc định và setter, field visibility phù hợp, hoặc creator được đánh dấu bằng `@JsonCreator`/`@JsonProperty`.

### 3.1. Tên key phải khớp JSON property

Nếu DTO khai báo tên JSON khác tên Java:

```java
public class Account {
    @JsonProperty("account_id")
    private long id;
}
```

Map nguồn cần dùng key `account_id`:

```java
Map<String, Object> source = Map.of("account_id", 25);
Account account = mapper.convertValue(source, Account.class);
```

Nếu Map dùng key `id` nhưng DTO chỉ nhận `account_id`, Jackson có thể xem `id` là unknown property hoặc bỏ qua tùy cấu hình. Không nên giả định tên field Java luôn là key đầu vào.

### 3.2. Naming strategy cũng ảnh hưởng ánh xạ

Với mapper dùng snake case:

```java
ObjectMapper mapper = new ObjectMapper()
    .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Property Java `firstName` có thể được nhận từ key `first_name`. Map cần tuân theo naming strategy của mapper.

Điều này có thể hữu ích khi chuyển Map được tạo từ JSON snake_case sang POJO camelCase. Nhưng nếu Map được tạo bởi một nguồn khác với quy ước tên riêng, cần chuẩn hóa key hoặc dùng `@JsonProperty` phù hợp.

### 3.3. Unknown property và thiếu field

Nếu Map chứa key không có trong DTO, kết quả phụ thuộc cấu hình `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` và các cơ chế như `@JsonAnySetter`.

Nếu DTO có property không xuất hiện trong Map, Jackson áp dụng hành vi mặc định của quá trình tạo object: giá trị khởi tạo của field, giá trị primitive mặc định hoặc logic creator. `convertValue()` không tự suy ra giá trị nghiệp vụ cho field bị thiếu.

Ví dụ, nếu `age` không có trong Map, không nên mặc định rằng nó sẽ tự nhận một giá trị như 18. Nếu cần default nghiệp vụ, hãy đặt giá trị khởi tạo rõ ràng, dùng creator/default logic hoặc xử lý sau khi chuyển đổi.

## 4. Chuyển POJO và Map sang JsonNode

`JsonNode` là API tree model của Jackson. Nó biểu diễn JSON dưới dạng cây node có thể duyệt và truy cập theo field/index.

Có thể chuyển POJO thành `JsonNode` bằng `convertValue()`:

```java
JsonNode node = mapper.convertValue(user, JsonNode.class);
```

Hoặc dùng API chuyên biệt hơn:

```java
JsonNode node = mapper.valueToTree(user);
```

`valueToTree()` thể hiện rõ ý định chuyển một Java value thành JSON tree. Cả hai đều dựa trên serialization semantics của mapper; nếu mục tiêu là tree model, `valueToTree()` thường dễ đọc hơn.

Tương tự, Map có thể được chuyển thành tree:

```java
JsonNode node = mapper.valueToTree(orderMap);
```

Ví dụ truy cập node:

```java
long id = node.path("id").asLong();
String name = node.path("name").asText();
```

`path()` trả `MissingNode` khi không có field, giúp tránh `NullPointerException`. Tuy nhiên, `asText()` hoặc `asLong()` có thể trả giá trị mặc định khi node không có kiểu như mong đợi; nếu cần kiểm tra nghiêm ngặt, hãy dùng `has()`, `isTextual()`, `isNumber()` và kiểm tra node null/missing.

### 4.1. Sửa đổi JsonNode

Nếu cần thay đổi cấu trúc trước khi chuyển sang DTO, dùng node mutable như `ObjectNode` và `ArrayNode`:

```java
ObjectNode objectNode = (ObjectNode) mapper.valueToTree(user);
objectNode.put("source", "import");
objectNode.remove("email");

User updated = mapper.treeToValue(objectNode, User.class);
```

`treeToValue()` chuyển JSON tree sang kiểu Java. Nó phù hợp hơn `convertValue()` khi nguồn đã là `JsonNode`, vì tên phương thức diễn đạt trực tiếp tree-to-POJO.

Không cast một `JsonNode` bất kỳ thành `ObjectNode` nếu chưa xác nhận node là object:

```java
if (!node.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}
ObjectNode objectNode = (ObjectNode) node;
```

## 5. Chuyển JsonNode thành POJO hoặc Map

Khi nhận một JSON tree và muốn ánh xạ sang DTO:

```java
User user = mapper.treeToValue(node, User.class);
```

Hoặc:

```java
User user = mapper.convertValue(node, User.class);
```

`treeToValue()` thường là API dễ hiểu nhất cho trường hợp tree-to-value. `convertValue()` hữu ích khi code đã dùng một pipeline chuyển đổi thống nhất giữa nhiều loại object nguồn.

Chuyển tree sang Map:

```java
Map<String, Object> values = mapper.convertValue(
    node,
    new TypeReference<Map<String, Object>>() {}
);
```

Với root array, kiểu đích phải là collection hoặc array phù hợp:

```java
List<User> users = mapper.convertValue(
    node,
    new TypeReference<List<User>>() {}
);
```

Nếu root node là object nhưng kiểu đích là `List<User>`, Jackson không thể tự biến object thành list trừ khi có một coercion hoặc deserializer riêng cho phép. Kiểu cấu trúc root cần phù hợp với kiểu đích.

## 6. Dùng TypeReference cho generic type

Java xóa phần lớn thông tin generic ở runtime. Không thể viết `List<User>.class`; `List.class` chỉ biểu diễn raw collection và không nói phần tử là `User`.

Khi kiểu đích có generic, dùng `TypeReference<T>`:

```java
List<User> users = mapper.convertValue(
    source,
    new TypeReference<List<User>>() {}
);
```

Ví dụ chuyển POJO có danh sách thành Map với nested list:

```java
Map<String, List<User>> groupedUsers = mapper.convertValue(
    source,
    new TypeReference<Map<String, List<User>>>() {}
);
```

`TypeReference` giữ metadata generic thông qua anonymous subclass. Nó thuận tiện khi kiểu đã biết tĩnh tại nơi viết code.

### 6.1. Dùng JavaType khi kiểu được tạo lúc runtime

Nếu kiểu phần tử chỉ biết khi chạy, có thể dùng `TypeFactory`:

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userType = typeFactory.constructType(User.class);
JavaType userListType = typeFactory.constructCollectionType(
    List.class,
    userType
);

List<User> users = mapper.convertValue(source, userListType);
```

Với map lồng nhau:

```java
JavaType userListType = typeFactory.constructCollectionType(List.class, User.class);

JavaType groupedType = typeFactory.constructMapType(
    Map.class,
    String.class,
    userListType
);

Map<String, List<User>> grouped = mapper.convertValue(source, groupedType);
```

`JavaType` hữu ích khi generic type được ghép từ các class hoặc type descriptor khác nhau lúc runtime. Nên lấy `TypeFactory` từ chính mapper dùng để chuyển đổi.

### 6.2. Tránh raw List.class khi cần phần tử có kiểu

Đoạn sau không giữ được thông tin phần tử:

```java
List values = mapper.convertValue(source, List.class);
```

Object lồng bên trong có thể trở thành `Map` hoặc kiểu tổng quát thay vì `User`. Nếu cần `List<User>`, dùng `TypeReference<List<User>>` hoặc `JavaType`.

## 7. Chuyển đổi giữa các kiểu container

`convertValue()` có thể chuyển giữa những kiểu container tương thích khi serializer/deserializer của chúng hỗ trợ.

### 7.1. List POJO thành List Map

```java
List<Map<String, Object>> rows = mapper.convertValue(
    users,
    new TypeReference<List<Map<String, Object>>>() {}
);
```

Mỗi `User` được serialize thành object representation, rồi deserialize thành Map. Kết quả là một list Map có thể dùng cho xuất báo cáo hoặc xử lý dữ liệu động.

### 7.2. Map thành List DTO

Nếu nguồn Map chứa một key `users` với giá trị là list các map:

```java
Map<String, Object> payload = Map.of(
    "users", List.of(
        Map.of("id", 1, "name", "An"),
        Map.of("id", 2, "name", "Binh")
    )
);

ApiResponse<List<User>> response = mapper.convertValue(
    payload,
    new TypeReference<ApiResponse<List<User>>>() {}
);
```

Jackson xử lý wrapper `ApiResponse`, collection và từng `User` theo generic type đích.

### 7.3. Map key và kiểu key

JSON object dùng tên field dạng chuỗi. Nếu Map nguồn có key không phải String, serializer Map cần chuyển key thành JSON property name theo key serializer. Khi chuyển sang Map đích có key Java tùy chỉnh, cần key deserializer phù hợp.

Ví dụ:

```java
Map<String, Object> jsonLike = mapper.convertValue(
    sourceMap,
    new TypeReference<Map<String, Object>>() {}
);
```

Đây là kiểu đích tự nhiên cho biểu diễn object JSON. Nếu dùng `Map<Integer, User>` hoặc `Map<CustomKey, User>`, cần xác định cách Jackson chuyển tên key JSON thành kiểu key Java và đăng ký key deserializer khi cần.

## 8. ConvertValue, valueToTree và treeToValue khác nhau thế nào?

Ba API có thể giải quyết các tác vụ liên quan nhưng diễn đạt mục đích khác nhau:

| API | Nguồn | Đích | Khi nên dùng |
|---|---|---|---|
| `convertValue(source, Target.class)` | Java object hoặc cấu trúc có thể serialize | Kiểu Java bất kỳ được hỗ trợ | Chuyển đổi tổng quát giữa POJO, Map, collection và tree |
| `valueToTree(source)` | Java object | `JsonNode` | Muốn tạo cây JSON để truy cập/chỉnh sửa |
| `treeToValue(node, Target.class)` | `JsonNode` | Kiểu Java | Muốn ánh xạ tree đã có sang DTO |

Ví dụ pipeline tree:

```java
JsonNode tree = mapper.valueToTree(source);
ObjectNode object = (ObjectNode) tree;
object.put("status", "READY");
Target result = mapper.treeToValue(object, Target.class);
```

Ví dụ pipeline convert trực tiếp:

```java
Target result = mapper.convertValue(source, Target.class);
```

Nếu không cần sửa hoặc truy vấn tree, chuyển trực tiếp thường ngắn gọn hơn. Nếu cần thao tác từng node, tree model làm ý định rõ ràng.

## 9. ConvertValue không phải deep clone tổng quát

Một cách dùng đôi khi thấy là:

```java
User copy = mapper.convertValue(original, User.class);
```

Kết quả có thể là một object mới cùng kiểu, nhưng không nên xem đây là cơ chế clone sâu bảo đảm mọi field đều được sao chép.

Lý do:

- `@JsonIgnore`, `@JsonInclude` và visibility có thể làm một số property không đi qua representation.
- Custom serializer có thể biến object thành dạng không giữ đầy đủ thông tin ban đầu.
- Deserializer có thể chuẩn hóa hoặc bỏ qua field.
- Field transient, read-only, write-only hoặc không được Jackson nhận diện có thể không được sao chép.
- Object con có thể được chuyển đổi theo kiểu đích và không giữ identity/reference graph như bản gốc.
- Reference cycle có thể không được hỗ trợ nếu không có cấu hình xử lý phù hợp.

Nếu cần clone domain object với invariant, identity và quan hệ tham chiếu được kiểm soát, hãy dùng copy constructor, factory hoặc mapper chuyên biệt. Dùng `convertValue()` khi muốn chuyển representation theo hợp đồng JSON của Jackson.

## 10. Chuyển đổi không đồng nghĩa với merge hoặc update

`convertValue()` tạo giá trị theo kiểu đích từ source. Nó không tự cập nhật một object đang tồn tại theo kiểu merge field-by-field.

Ví dụ:

```java
User updated = mapper.convertValue(patchMap, User.class);
```

Đoạn trên tạo một `User` từ Map. Nó không giữ các property hiện có của một `User` khác nếu Map không chứa chúng.

Nếu cần đọc dữ liệu vào một object đã có, Jackson có API riêng như `readerForUpdating()`:

```java
User existing = loadUser();

ObjectReader updatingReader = mapper.readerForUpdating(existing);
updatingReader.readValue(jsonPatch);
```

Hoặc `ObjectMapper.updateValue()` cho một số trường hợp merge:

```java
User updated = mapper.updateValue(existing, overrides);
```

Các API update có semantics riêng, bao gồm cách xử lý property lồng nhau và collection. Không nên giả định chúng luôn deep merge. Nếu cần quy tắc patch như “field không có nghĩa là giữ nguyên, field null nghĩa là xóa”, hãy định nghĩa hợp đồng update rõ ràng và kiểm thử riêng.

## 11. Annotation và cấu hình mapper ảnh hưởng kết quả

`convertValue()` dùng serializer và deserializer của mapper. Vì vậy, các thiết lập sau có thể tác động:

- `@JsonProperty`, `@JsonAlias`, `@JsonIgnore` và visibility.
- `@JsonInclude` ở chiều serialize.
- `@JsonCreator`, `@JsonSetter` và null handling ở chiều deserialize.
- Naming strategy như snake case.
- Module cho Java Time, Optional, Kotlin hoặc kiểu đặc biệt khác.
- Custom serializer, deserializer, key serializer và key deserializer.
- Coercion config và các `DeserializationFeature`.
- Polymorphic type handling như `@JsonTypeInfo`.

Ví dụ, nếu POJO có `Instant` và mapper chưa đăng ký `JavaTimeModule`, việc chuyển sang Map hoặc tree có thể không có representation mong muốn. Hãy dùng mapper đã được cấu hình đầy đủ của ứng dụng.

### 11.1. Serializer và deserializer có thể không đối xứng

Một custom serializer có thể xuất `Money` thành chuỗi:

```json
"125.50 USD"
```

Trong khi deserializer lại chỉ nhận object:

```json
{
  "amount": 125.50,
  "currency": "USD"
}
```

Khi `convertValue()` đi qua representation do serializer tạo ra rồi dùng deserializer của kiểu đích, phép chuyển có thể thất bại hoặc cho kết quả khác mong muốn. Hãy bảo đảm representation đầu ra của source tương thích với kiểu đích và các serializer/deserializer đã cấu hình.

### 11.2. Naming strategy và key của Map

Khi chuyển POJO thành Map, tên key phản ánh JSON property name sau naming strategy/annotation. Khi chuyển Map trở lại POJO, Jackson dùng quy tắc nhận diện property tương ứng. Nếu Map được tạo từ một nguồn ngoài, không nên giả định key camelCase và snake_case có thể thay thế cho nhau.

## 12. Coercion, null và giá trị thiếu

`convertValue()` áp dụng cơ chế deserialize của kiểu đích, bao gồm coercion và null handling đã cấu hình. Ví dụ, Map có giá trị `"25"` cho property kiểu `Integer` có thể được chuyển thành số hoặc bị từ chối tùy coercion config.

Hãy phân biệt:

| Nguồn Map/JSON-like | Ý nghĩa khi chuyển |
|---|---|
| Không có key | Property không được cung cấp; giữ default/giá trị khởi tạo theo cách tạo object |
| Key có value `null` | Giá trị null được xử lý theo null handling và kiểu đích |
| Key có `""` | Chuỗi rỗng; coercion/deserializer quyết định có chấp nhận hay không |
| Key có `0` hoặc `false` | Giá trị cụ thể, không đồng nghĩa với thiếu |
| Key có collection rỗng | Collection rỗng nếu kiểu đích hỗ trợ |

Đối với kiểu primitive như `int` hoặc `boolean`, không thể lưu null. Nếu cần phân biệt null với zero/false, dùng wrapper `Integer`/`Boolean` trong DTO trung gian rồi validate hoặc chuyển sang domain type.

## 13. Xử lý lỗi khi convertValue()

Nếu source không thể serialize hoặc representation không thể deserialize thành kiểu đích, `convertValue()` thường ném `IllegalArgumentException` với nguyên nhân bên dưới là lỗi mapping/processing.

Ví dụ:

```java
try {
    User user = mapper.convertValue(source, User.class);
} catch (IllegalArgumentException e) {
    throw new InvalidImportDataException("Cannot convert input to User", e);
}
```

Không nên bắt exception rồi trả về object rỗng mà không ghi nhận lỗi. Cách đó có thể làm dữ liệu sai tiếp tục đi vào hệ thống.

Khi điều tra lỗi:

1. Kiểm tra source thực tế và kiểu runtime của nó.
2. Kiểm tra kiểu đích có generic metadata đầy đủ không.
3. Kiểm tra tên property, kiểu scalar và cấu trúc object/array.
4. Kiểm tra custom serializer/deserializer và module đã đăng ký.
5. Xem cause của `IllegalArgumentException` để biết property/path gây lỗi.
6. Tạo test nhỏ với cùng mapper để tái hiện.

## 14. Hạn chế cần biết

`convertValue()` tiện lợi nhưng không thay thế mọi thao tác serialize/deserialize:

- Không bảo đảm tương đương tuyệt đối với việc ghi JSON text rồi đọc lại. Đây là cơ chế chuyển đổi token trong bộ nhớ; một số tính năng ở cấp root, như root wrapping/unwrapping, không được hỗ trợ giống hệt pipeline JSON đầy đủ.
- Không phải API streaming cho nguồn lớn. Source object và biểu diễn token trung gian vẫn cần tài nguyên trong bộ nhớ.
- Không bảo toàn identity hoặc object graph như một phép clone sâu tổng quát.
- Không tự validate quy tắc nghiệp vụ ngoài những kiểm tra mà deserializer thực hiện.
- Không tự merge vào object hiện có; dùng API update hoặc logic patch riêng.
- Không khôi phục thông tin đã bị serializer bỏ qua hoặc biến đổi.

Nếu cần xác nhận output JSON chính xác trên wire, hãy dùng `writeValueAsString()`/`writeValue()` và kiểm thử JSON thực tế. Nếu cần kiểm soát từng token hoặc xử lý payload rất lớn, dùng `JsonParser`/`JsonGenerator` hoặc `ObjectReader`/`MappingIterator` phù hợp.

## 15. Ví dụ tổng hợp: Map đầu vào thành DTO, chỉnh tree rồi tạo response

Một luồng xử lý có thể nhận Map từ một thành phần nội bộ, chuyển sang DTO, thêm metadata vào JSON tree rồi tạo response cuối:

```java
Map<String, Object> input = new LinkedHashMap<>();
input.put("id", 25);
input.put("name", "An");
input.put("email", "an@example.com");

// 1. Map -> POJO
User user = mapper.convertValue(input, User.class);

// 2. POJO -> JSON tree
ObjectNode tree = mapper.valueToTree(user);

// 3. Chỉnh sửa cấu trúc JSON
tree.put("source", "internal-import");
tree.put("processed", true);

// 4. JSON tree -> response DTO
UserResponse response = mapper.treeToValue(tree, UserResponse.class);
```

Mỗi bước có mục đích riêng:

- `convertValue()` ánh xạ cấu trúc Map sang kiểu Java.
- `valueToTree()` tạo tree model để thao tác theo field.
- `ObjectNode` thêm hoặc xóa node.
- `treeToValue()` ánh xạ tree đã chỉnh sửa sang kiểu response.

Nếu không cần chỉnh sửa tree, có thể bỏ các bước tree và chuyển trực tiếp sang kiểu đích.

## 16. Ví dụ JUnit kiểm tra chuyển đổi

```java
class ConvertValueTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void convertsMapToUser() {
        Map<String, Object> source = Map.of(
            "id", 25,
            "name", "An",
            "email", "an@example.com"
        );

        User user = mapper.convertValue(source, User.class);

        assertEquals(25L, user.getId());
        assertEquals("An", user.getName());
        assertEquals("an@example.com", user.getEmail());
    }

    @Test
    void convertsUserToMap() {
        User user = new User(25L, "An", "an@example.com");

        Map<String, Object> result = mapper.convertValue(
            user,
            new TypeReference<Map<String, Object>>() {}
        );

        assertEquals(25, ((Number) result.get("id")).longValue());
        assertEquals("An", result.get("name"));
    }

    @Test
    void convertsPojoToTreeAndBack() throws Exception {
        User original = new User(25L, "An", "an@example.com");

        JsonNode tree = mapper.valueToTree(original);
        User restored = mapper.treeToValue(tree, User.class);

        assertEquals(original.getId(), restored.getId());
        assertEquals(original.getName(), restored.getName());
    }

    @Test
    void preservesGenericElementType() {
        List<Map<String, Object>> source = List.of(
            Map.of("id", 1, "name", "An"),
            Map.of("id", 2, "name", "Binh")
        );

        List<User> users = mapper.convertValue(
            source,
            new TypeReference<List<User>>() {}
        );

        assertEquals(2, users.size());
        assertEquals("Binh", users.get(1).getName());
    }
}
```

Test generic đặc biệt quan trọng: nếu thay `TypeReference<List<User>>` bằng `List.class`, compiler không thể bảo đảm phần tử trả về là `User`.

## 17. Quy trình lựa chọn API

| Nhu cầu | API nên cân nhắc |
|---|---|
| POJO -> Map hoặc Map -> POJO trong bộ nhớ | `convertValue()` |
| POJO -> `JsonNode` | `valueToTree()` |
| `JsonNode` -> POJO | `treeToValue()` |
| Chỉnh sửa JSON theo field/index | `ObjectNode` / `ArrayNode` |
| Serialize ra JSON text hoặc stream | `writeValueAsString()` / `writeValue()` |
| Đọc JSON text/stream thành object | `readValue()` |
| Đọc nhiều record lớn theo luồng | `ObjectReader.readValues()` / `MappingIterator` |
| Cập nhật object đang tồn tại | `readerForUpdating()` hoặc `updateValue()` với semantics được kiểm tra |

Khi dùng `convertValue()`, hãy làm theo các bước:

1. Xác định representation nguồn: POJO, Map, collection hay `JsonNode`.
2. Xác định kiểu đích chính xác, đặc biệt với generic type.
3. Dùng `Class`, `TypeReference` hoặc `JavaType` phù hợp.
4. Dùng mapper đã đăng ký module và cấu hình của ứng dụng.
5. Xác nhận tên property, null, empty, coercion và custom serializer/deserializer.
6. Kiểm tra lỗi mapping và không che giấu exception.
7. Nếu cần sửa tree, dùng `valueToTree()`/`treeToValue()` để ý định rõ ràng.
8. Nếu cần merge, clone sâu, validation hoặc streaming, chọn API/chính sách chuyên biệt thay vì kỳ vọng `convertValue()` xử lý tất cả.

## Kết luận

`ObjectMapper.convertValue()` chuyển một Java value sang kiểu đích bằng serialization/deserialization machinery của Jackson và một biểu diễn token trung gian trong bộ nhớ. Nó rất tiện để chuyển POJO, Map, collection và `JsonNode` mà không phải tạo JSON String trung gian. Dùng `TypeReference` hoặc `JavaType` khi kiểu đích có generic; dùng `valueToTree()` và `treeToValue()` khi thao tác rõ ràng với JSON tree. Hãy nhớ kết quả phụ thuộc cấu hình mapper, annotation và custom serializer/deserializer; `convertValue()` không phải cast, deep clone, validation, streaming hay merge tổng quát.
