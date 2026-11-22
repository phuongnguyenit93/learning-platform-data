# Đọc cập nhật lên đối tượng có sẵn bằng readerForUpdating

Thông thường, khi gọi ObjectMapper.readValue(...), Jackson tạo một object mới từ JSON. Nhưng trong một số luồng xử lý, ứng dụng đã có một object và chỉ muốn áp dụng dữ liệu mới lên object đó. Jackson Databind cung cấp ObjectMapper.readerForUpdating(existingValue) để tạo một ObjectReader đọc JSON và cập nhật target có sẵn.

Ví dụ, một hồ sơ người dùng đang có tên, email, địa chỉ và danh sách quyền. Payload chỉ gửi tên mới. Với cơ chế update, các thuộc tính không xuất hiện trong JSON có thể giữ giá trị hiện tại, thay vì bị khởi tạo lại như khi deserialize một object mới.

Cần phân biệt ba tình huống:

- **Property bị thiếu**: JSON không nhắc đến property; giá trị hiện tại thường được giữ nguyên khi cập nhật bean.
- **Property có giá trị**: Jackson áp dụng giá trị mới lên target.
- **Property có null tường minh**: mặc định có thể ghi đè giá trị hiện tại thành null; chính sách null cần được cấu hình riêng nếu muốn bỏ qua hoặc từ chối.

Bài học này trình bày cách dùng readerForUpdating, hành vi với object lồng nhau và collection, @JsonMerge, cách xử lý null, giới hạn với kiểu bất biến và cách kiểm thử cập nhật an toàn.

## 1. Deserialize object mới và update object hiện có

Deserialize thông thường:

```java
UserProfile profile = mapper.readValue(json, UserProfile.class);
```

Jackson tạo một UserProfile mới từ nội dung JSON. Các property không xuất hiện trong JSON sẽ nhận giá trị do constructor, initializer hoặc cơ chế tạo object quy định.

Update object hiện có:

```java
UserProfile existing = loadProfile();

UserProfile updated = mapper
    .readerForUpdating(existing)
    .readValue(json);
```

Trong ví dụ này, Jackson dùng existing làm root target. Với một bean mutable thông thường, các property có trong JSON được áp dụng lên object đó; property bị thiếu thường giữ nguyên.

Sơ đồ tổng quát:

```text
Object hiện có
      │
      ▼
readerForUpdating(existing)
      │
      ▼
Đọc JSON
      │
      ├── property có trong JSON ──> áp dụng giá trị mới
      │
      ├── property bị thiếu ───────> giữ giá trị hiện tại
      │
      └── property là null ────────> theo null policy
      │
      ▼
Object sau cập nhật
```

Đây là cơ chế update ở tầng Jackson. Nó không tự định nghĩa nghiệp vụ PATCH, không lưu object xuống database và không bảo đảm transaction hoặc rollback nếu quá trình đọc thất bại.

## 2. Ví dụ cơ bản với một bean mutable

Giả sử model:

```java
public class UserProfile {

    private String displayName;
    private String email;
    private int age;
    private boolean active;

    public UserProfile() {
    }

    public UserProfile(
            String displayName,
            String email,
            int age,
            boolean active
    ) {
        this.displayName = displayName;
        this.email = email;
        this.age = age;
        this.active = active;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Tạo object ban đầu:

```java
UserProfile existing = new UserProfile(
    "Nguyen An",
    "an@example.com",
    28,
    true
);
```

Payload chỉ thay đổi tên:

```json
{
  "displayName": "An Nguyen"
}
```

Cập nhật:

```java
String patchJson = """
    {
      "displayName": "An Nguyen"
    }
    """;

UserProfile result = mapper
    .readerForUpdating(existing)
    .readValue(patchJson);
```

Với bean mutable, target được cập nhật tại chỗ. Các giá trị email, age và active vẫn giữ như trước vì JSON không cung cấp các property đó.

Có thể kiểm tra:

```java
assertSame(existing, result);
assertEquals("An Nguyen", existing.getDisplayName());
assertEquals("an@example.com", existing.getEmail());
assertEquals(28, existing.getAge());
assertTrue(existing.isActive());
```

Việc trả về target giúp có thể nối thao tác đọc vào biểu thức. Tuy nhiên, với kiểu đặc biệt như array hoặc deserializer không hỗ trợ update tại chỗ, kết quả có thể là một instance mới. Đừng giả định mọi kiểu Java đều có thể được sửa tại chỗ.

## 3. Tạo ObjectReader từ target hiện có

readerForUpdating nhận object cần cập nhật:

```java
ObjectReader updater = mapper.readerForUpdating(existing);
```

Sau đó có thể đọc từ nhiều loại nguồn:

```java
updater.readValue(jsonString);
updater.readValue(inputStream);
updater.readValue(reader);
updater.readValue(file);
```

Có thể cấu hình thêm feature cho reader:

```java
ObjectReader updater = mapper
    .readerForUpdating(existing)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

ObjectReader là đối tượng cấu hình bất biến theo cách sử dụng thông thường. Các method cấu hình tạo reader mới. Tuy nhiên, reader được tạo bằng readerForUpdating(existing) vẫn giữ tham chiếu tới target cụ thể. Không chia sẻ cùng reader/target mutable giữa các request hoặc thread nếu chúng có thể cập nhật đồng thời.

Mẫu phù hợp là tạo reader cho từng object cần cập nhật:

```java
UserProfile existing = repository.loadProfile(id);

mapper.readerForUpdating(existing)
    .readValue(requestBody);
```

Nếu cần tái sử dụng cấu hình chung, hãy giữ mapper hoặc reader không gắn target; tạo readerForUpdating mới khi đã có object đích.

## 4. Property bị thiếu khác với property null

Đây là điểm quan trọng nhất khi dùng update.

Giả sử object ban đầu:

```java
UserProfile existing = new UserProfile(
    "Nguyen An",
    "an@example.com",
    28,
    true
);
```

### 4.1. Property bị thiếu

Payload:

```json
{
  "displayName": "An Nguyen"
}
```

Không có email, age và active. Với bean update thông thường, Jackson không gọi setter cho những property bị thiếu. Giá trị hiện tại của chúng được giữ nguyên.

### 4.2. Property có null tường minh

Payload:

```json
{
  "displayName": "An Nguyen",
  "email": null
}
```

email có mặt trong JSON và giá trị là null. Mặc định, Jackson có thể gọi setter với null, làm email hiện tại bị xóa.

| JSON | Ý nghĩa khi update bean thông thường |
| --- | --- |
| Không có email | Giữ email hiện tại |
| "email": "new@example.com" | Gán email mới |
| "email": null | Gán null theo null policy mặc định |
| "email": "" | Gán chuỗi rỗng, trừ khi có coercion/validation khác |

Không nên coi missing và null là cùng một trạng thái. Nếu API cần phân biệt “không thay đổi” với “xóa giá trị”, hãy giữ semantics này rõ ràng trong hợp đồng.

### 4.3. Null cho primitive

Primitive Java như int và boolean không thể chứa null. Với JSON:

```json
{
  "age": null,
  "active": null
}
```

Hành vi phụ thuộc cấu hình deserialization. Nếu không muốn null bị chuyển thành giá trị mặc định như 0 hoặc false, bật:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
```

Nếu property cần trạng thái “chưa biết” hoặc “được xóa”, dùng wrapper như Integer hoặc Boolean thay vì primitive, rồi định nghĩa null policy phù hợp.

## 5. Bỏ qua null bằng @JsonSetter

Nếu hợp đồng yêu cầu null nghĩa là “không thay đổi giá trị hiện tại”, có thể cấu hình null handling cho property bằng @JsonSetter.

Ví dụ:

```java
public class UserProfile {

    private String displayName;
    private String email;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setEmail(String email) {
        this.email = email;
    }

    // Other getters/setters
}
```

Với Nulls.SKIP, Jackson bỏ qua việc gán khi input property là null. Giá trị email đang có được giữ nguyên.

Có thể áp dụng cho field hoặc setter theo vị trí annotation mà Jackson hỗ trợ:

```java
@JsonSetter(nulls = Nulls.SKIP)
private String phoneNumber;
```

Các chính sách thường gặp:

| Nulls | Ý nghĩa |
| --- | --- |
| Nulls.SET | Gán null cho property; đây là hành vi thông thường |
| Nulls.SKIP | Bỏ qua giá trị null, giữ giá trị hiện tại khi update |
| Nulls.FAIL | Báo lỗi nếu input là null |
| Nulls.AS_EMPTY | Dùng giá trị rỗng theo kiểu đích |
| Nulls.DEFAULT | Dùng chính sách mặc định của Jackson/property |

Đối với collection/map, contentNulls có thể kiểm soát null của từng phần tử hoặc value bên trong container, khác với null của chính property container.

Không nên dùng @JsonInclude(Include.NON_NULL) để giải quyết null khi đọc. JsonInclude chủ yếu kiểm soát cách serialize output; nó không thay thế null handling trong deserialization.

## 6. Update object lồng nhau và @JsonMerge

readerForUpdating(existing) cập nhật root object. Nhưng với một property lồng nhau, cần phân biệt việc thay cả property với việc merge vào object con đang tồn tại.

Model:

```java
public class Address {
    private String city;
    private String street;

    // Constructors, getters and setters
}

public class Customer {
    private String name;

    private Address address;

    // Getters and setters
}
```

Object hiện tại:

```java
Customer customer = new Customer();
customer.setName("An");

Address address = new Address();
address.setCity("Da Nang");
address.setStreet("Hai Chau");

customer.setAddress(address);
```

Payload chỉ có một phần địa chỉ:

```json
{
  "address": {
    "street": "Bach Dang"
  }
}
```

Nếu property address không được cấu hình merge, Jackson có thể thay giá trị property bằng một Address mới được deserialize từ payload. Khi đó city có thể trở thành null vì object Address mới không nhận được field city.

Để yêu cầu Jackson cập nhật object Address hiện có, dùng @JsonMerge:

```java
public class Customer {

    private String name;

    @JsonMerge
    private Address address;

    // Getters and setters
}
```

Khi update Customer:

```java
mapper.readerForUpdating(customer)
    .readValue("""
        {
          "address": {
            "street": "Bach Dang"
          }
        }
        """);
```

Jackson merge nội dung vào Address đang có theo khả năng update của deserializer cho kiểu đó. city được giữ nguyên, còn street nhận giá trị mới.

@JsonMerge cần đặt trên property cần merge; nó không phải một công tắc toàn cục khiến mọi object lồng nhau tự động merge.

### 6.1. Merge Map

Với Map property, @JsonMerge cho phép hợp nhất các entry mới vào Map hiện có thay vì thay toàn bộ Map.

```java
public class UserSettings {

    @JsonMerge
    private Map<String, String> preferences =
        new LinkedHashMap<>();

    // Getter and setter
}
```

Map ban đầu:

```java
preferences.put("theme", "dark");
preferences.put("language", "vi");
```

Payload:

```json
{
  "preferences": {
    "theme": "light",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

Sau merge, Map có thể chứa:

```text
theme     -> light
language  -> vi
timezone  -> Asia/Ho_Chi_Minh
```

Key theme được cập nhật; key language không xuất hiện trong payload nên vẫn còn; key timezone được thêm mới.

Nếu không có @JsonMerge, property Map có thể được thay bằng Map mới chỉ chứa các entry từ payload. Chọn semantics theo mục đích API.

### 6.2. Merge Collection

Với collection property được đánh dấu @JsonMerge, Jackson áp dụng update semantics của collection deserializer. Với các collection chuẩn, các phần tử từ input thường được thêm vào collection hiện tại:

```java
public class UserSettings {

    @JsonMerge
    private List<String> tags = new ArrayList<>();

    // Getter and setter
}
```

List ban đầu:

```java
tags.add("java");
tags.add("jackson");
```

Payload:

```json
{
  "tags": ["serialization"]
}
```

Kết quả có thể là:

```json
["java", "jackson", "serialization"]
```

Đây là append semantics, không phải thay thế toàn bộ list. Nếu API muốn thay list bằng đúng nội dung payload, không bật merge cho property đó.

Với Set, việc thêm phần tử chịu ảnh hưởng của equals/hashCode và quy tắc uniqueness của Set. Với collection tùy chỉnh, hành vi phụ thuộc deserializer và kiểu container cụ thể.

### 6.3. Array khác với List

Java array có kích thước cố định. Jackson không thể mở rộng một array hiện có để append phần tử theo cách của List. Với property array, hãy coi update là thay thế giá trị array bằng một array mới khi cần thay đổi nội dung/kích thước.

Nếu cần merge/append linh hoạt, dùng List hoặc collection phù hợp thay vì array.

### 6.4. Không áp dụng @JsonMerge một cách máy móc

Merge có thể tạo ra trạng thái tích lũy ngoài ý muốn. Ví dụ client gửi một List mới với ý nghĩa “đây là danh sách đầy đủ”, nhưng @JsonMerge lại append các phần tử vào list cũ. Kết quả sẽ có dữ liệu trùng hoặc dữ liệu đã bị loại ở phía client vẫn tồn tại.

Hãy xác định ý nghĩa của từng property:

- **Replace**: payload là giá trị đầy đủ mới.
- **Merge**: chỉ những phần được gửi mới được áp dụng; phần còn lại giữ nguyên.
- **Append**: dữ liệu mới được thêm vào collection.
- **Clear**: payload có cách biểu diễn rõ ràng để xóa giá trị hoặc collection.

@JsonMerge hỗ trợ update semantics ở cấp Jackson; nó không tự suy ra ý nghĩa nghiệp vụ mong muốn.

## 7. Update root Map và Collection

readerForUpdating cũng có thể được dùng với container làm root target.

### 7.1. Cập nhật Map gốc

```java
Map<String, Object> existing = new LinkedHashMap<>();
existing.put("theme", "dark");
existing.put("language", "vi");

Map<String, Object> result = mapper
    .readerForUpdating(existing)
    .readValue("""
        {
          "theme": "light",
          "timezone": "Asia/Ho_Chi_Minh"
        }
        """);
```

Với Map root có thể cập nhật, các entry mới được áp dụng lên Map hiện có; key trùng được cập nhật và key không có trong input thường vẫn tồn tại.

### 7.2. Cập nhật Collection gốc

```java
List<String> existing = new ArrayList<>(
    List.of("java", "jackson")
);

List<String> result = mapper
    .readerForUpdating(existing)
    .readValue("""
        ["serialization"]
        """);
```

Với collection deserializer chuẩn hỗ trợ update, các phần tử input được thêm vào collection hiện có. Kiểm tra hành vi cụ thể của kiểu collection và deserializer được đăng ký trong ứng dụng.

### 7.3. Đừng suy rộng từ root container sang property container

Cập nhật Map/List làm root target không hoàn toàn giống cập nhật một property Map/List bên trong bean. Với property, @JsonMerge quyết định việc merge hay replace. Với root target, chính container hiện có là đối tượng được cập nhật.

Khi API có nhiều cấu trúc lồng nhau, hãy viết test riêng cho root Map, Map property, root List và List property.

## 8. Update với kiểu bất biến, record và object không có setter

readerForUpdating phù hợp nhất với object có thể cập nhật: bean có setter, field có thể ghi hoặc container mutable.

Với kiểu bất biến như:

```java
public record UserProfile(
    String displayName,
    String email,
    int age
) {}
```

các component không thể được thay đổi sau khi record được tạo. Không thể kỳ vọng Jackson cập nhật trực tiếp từng component như bean mutable.

Với record hoặc immutable class, cân nhắc:

- Deserialize thành một DTO cập nhật riêng rồi tạo record mới.
- Dùng builder hoặc copy method.
- Tạo object mới bằng cách kết hợp giá trị hiện tại với field có mặt trong payload.
- Dùng JsonNode để biểu diễn presence/null rồi xây dựng object mới.

Ví dụ một cách thủ công:

```java
public record UserProfile(
    String displayName,
    String email,
    int age
) {
    public UserProfile withDisplayName(String value) {
        return new UserProfile(value, email, age);
    }
}
```

Nếu payload chỉ chứa displayName, ứng dụng cần biết field đó có mặt hay không trước khi gọi withDisplayName. Một DTO dùng wrapper nullable đơn giản chưa chắc phân biệt được missing và explicit null; có thể cần JsonNode, một presence wrapper hoặc lớp request có trạng thái field rõ ràng.

Không nên dùng reflection hoặc sửa field final để ép kiểu bất biến hoạt động như mutable bean.

## 9. Cập nhật property có custom deserializer

Khi property có custom deserializer, việc cập nhật object hiện có phụ thuộc deserializer đó có hỗ trợ update hay không.

JsonDeserializer có overload:

```java
deserialize(
    JsonParser parser,
    DeserializationContext context,
    T intoValue
)
```

Overload này cho phép custom deserializer nhận object đang có và cập nhật nó. Deserializer cũng có thể khai báo khả năng update thông qua supportsUpdate(...) trong các phiên bản Jackson hỗ trợ API này.

Ví dụ minh họa cho một kiểu mutable:

```java
public final class PreferencesDeserializer
        extends StdDeserializer<Preferences> {

    public PreferencesDeserializer() {
        super(Preferences.class);
    }

    @Override
    public Boolean supportsUpdate(DeserializationConfig config) {
        return Boolean.TRUE;
    }

    @Override
    public Preferences deserialize(
            JsonParser parser,
            DeserializationContext context,
            Preferences intoValue
    ) throws IOException {
        if (parser.currentToken() != JsonToken.START_OBJECT) {
            throw JsonMappingException.from(
                parser,
                "Preferences must be an object"
            );
        }

        while (parser.nextToken() != JsonToken.END_OBJECT) {
            String fieldName = parser.currentName();
            JsonToken token = parser.nextToken();

            switch (fieldName) {
                case "theme" -> {
                    if (token != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                            parser,
                            "theme must be a string"
                        );
                    }
                    intoValue.setTheme(parser.getText());
                }
                case "language" -> {
                    if (token != JsonToken.VALUE_STRING) {
                        throw JsonMappingException.from(
                            parser,
                            "language must be a string"
                        );
                    }
                    intoValue.setLanguage(parser.getText());
                }
                default -> parser.skipChildren();
            }
        }

        return intoValue;
    }
}
```

Đây là ví dụ minh họa cho custom type có thể sửa tại chỗ. Trong code thực tế, cần triển khai cả cách xử lý khi không có target hiện tại bằng overload hai tham số deserialize(parser, context), đồng thời bảo đảm cả hai đường đọc dùng cùng quy tắc validation.

Nếu custom deserializer không hỗ trợ update, Jackson có thể phải tạo giá trị mới hoặc không thể áp dụng semantics update mong muốn. Hãy kiểm tra API và hành vi của đúng phiên bản Jackson đang dùng.

## 10. readerForUpdating không phải JSON Merge Patch

readerForUpdating và JSON Merge Patch có thể trông giống nhau vì đều cập nhật một phần object, nhưng chúng không phải cùng một giao thức.

| Khía cạnh | readerForUpdating | JSON Merge Patch (RFC 7396) |
| --- | --- | --- |
| Phạm vi | API update của Jackson Databind | Quy tắc định dạng patch ở cấp JSON |
| Target | Object Java đã có | JSON document hiện tại |
| Missing property | Deserializer không cập nhật property đó trong nhiều bean update thông thường | Giữ nguyên property |
| Null | Theo null handling của Jackson/property | Có nghĩa xóa property trong object theo RFC |
| Array | Theo deserializer và merge config | Thay toàn bộ array bằng array được cung cấp |
| HTTP semantics | Không tự định nghĩa | Có media type và quy tắc giao thức riêng |

Nếu API tuyên bố hỗ trợ application/merge-patch+json, hãy thực hiện semantics của RFC 7396. Chỉ gọi readerForUpdating không đủ để tuyên bố đã triển khai JSON Merge Patch.

Tương tự, JSON Patch (RFC 6902) dùng các operation như add, remove, replace, move, copy và test; nó cũng không đồng nghĩa với readerForUpdating.

readerForUpdating là một công cụ bind/update object. Ứng dụng cần xác định rõ giao thức API ở tầng cao hơn.

## 11. Tạo luồng cập nhật một phần an toàn

Trong một API cập nhật hồ sơ, có thể thiết kế luồng:

```text
HTTP request body
      │
      ▼
Kiểm tra authentication / authorization
      │
      ▼
Tải object hiện tại
      │
      ▼
Áp dụng update semantics
      │
      ▼
Validate trạng thái sau cập nhật
      │
      ▼
Lưu trong transaction
      │
      ▼
Trả response
```

Ví dụ service:

```java
@Transactional
public UserProfile updateProfile(
        String userId,
        String requestBody
) throws IOException {
    UserProfile profile = repository.findById(userId)
        .orElseThrow(() -> new NotFoundException(userId));

    mapper.readerForUpdating(profile)
        .readValue(requestBody);

    validator.validate(profile);

    return repository.save(profile);
}
```

Đây là minh họa đơn giản. Với JPA managed entity, việc sửa field có thể đã được persistence context theo dõi. Với detached object, cần lưu lại theo quy tắc repository.

Không nên cho phép request body cập nhật trực tiếp các field nhạy cảm như id, role, ownerId, createdAt hoặc trạng thái nội bộ nếu client không có quyền. Dùng DTO update allowlist hoặc kiểm tra field trước khi áp dụng.

### 11.1. Validate sau update

Một payload riêng lẻ có thể không chứa đủ field để validation. Ví dụ displayName được cập nhật nhưng email lấy từ object cũ. Nhiều invariant chỉ có thể được kiểm tra trên trạng thái hoàn chỉnh sau khi merge.

Hãy phân biệt:

- Validation cú pháp/kiểu trong lúc deserialize.
- Validation field-level trên giá trị mới.
- Validation object-level trên trạng thái sau cập nhật.
- Authorization cho từng field hoặc operation.

Jackson không tự biết field nào người dùng được phép sửa. Authorization phải được thực hiện ở service/domain layer.

### 11.2. Cập nhật có thể thất bại giữa chừng

Update mutable object có thể thay đổi một số property trước khi gặp lỗi ở property sau. Không nên giả định Jackson rollback các thay đổi đã áp dụng nếu deserialize thất bại.

Nếu cần tính nguyên tử ở tầng ứng dụng, có thể:

1. Tạo bản sao của object hiện tại.
2. Áp dụng JSON lên bản sao.
3. Validate bản sao.
4. Chỉ thay thế/lưu object gốc khi tất cả bước thành công.

Hoặc deserialize vào một update DTO riêng rồi tạo trạng thái mới. Cách này đặc biệt hữu ích khi object đang được chia sẻ hoặc có nhiều invariant liên quan.

## 12. Unknown property và strictness khi update

Khi payload có field không tồn tại trong target, hành vi phụ thuộc DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES và annotation/custom deserializer.

Có thể bật strictness cho reader:

```java
ObjectReader updater = mapper
    .readerForUpdating(existing)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Điều này giúp phát hiện client gửi sai tên field hoặc cố cập nhật field không được mô hình hỗ trợ.

Nếu update DTO có các field riêng được phép sửa, dùng DTO đó thay vì expose toàn bộ entity. @JsonIgnoreProperties(ignoreUnknown = true) có thể bỏ qua field lạ, nhưng điều đó có thể che lỗi chính tả hoặc request chứa field không được phép.

Unknown property và forbidden property cũng không hoàn toàn giống nhau: một field có thể được biết trong model nhưng vẫn không được phép cập nhật bởi user hiện tại. Cần kiểm tra authorization riêng.

## 13. Cấu hình merge và null theo từng property

Một object có thể cần nhiều semantics khác nhau:

```java
public class AccountSettings {

    private String displayName;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phoneNumber;

    @JsonMerge
    private Address address;

    @JsonMerge
    private Map<String, String> preferences =
        new LinkedHashMap<>();

    private List<String> notificationChannels =
        new ArrayList<>();

    // Getters and setters
}
```

Trong ví dụ:

- displayName được gán khi payload có field.
- phoneNumber bỏ qua null tường minh.
- address merge vào object hiện có.
- preferences merge các entry.
- notificationChannels được thay thế khi property được gửi vì không bật merge.

Đây là một ví dụ về cách thiết kế semantics theo property. Không phải tất cả field đều nên dùng chung một quy tắc update.

Nếu cần xóa phoneNumber, Nulls.SKIP khiến null không còn là cách xóa. Có thể dùng một operation rõ ràng, một endpoint riêng, một wrapper biểu diễn trạng thái hoặc giao thức patch phù hợp.

## 14. Kiểm thử readerForUpdating

Nên kiểm thử trạng thái trước và sau update, đặc biệt là missing, null, nested object và collection.

### 14.1. Property bị thiếu giữ giá trị hiện tại

```java
@Test
void keepsPropertiesMissingFromUpdate() throws Exception {
    UserProfile existing = new UserProfile(
        "An",
        "an@example.com",
        28,
        true
    );

    mapper.readerForUpdating(existing)
        .readValue("""
            {"displayName": "An Nguyen"}
            """);

    assertEquals("An Nguyen", existing.getDisplayName());
    assertEquals("an@example.com", existing.getEmail());
    assertEquals(28, existing.getAge());
    assertTrue(existing.isActive());
}
```

### 14.2. Explicit null được xử lý theo policy

Với property mặc định:

```java
@Test
void explicitNullClearsNullableProperty() throws Exception {
    UserProfile existing = new UserProfile(
        "An",
        "an@example.com",
        28,
        true
    );

    mapper.readerForUpdating(existing)
        .readValue("""
            {"email": null}
            """);

    assertNull(existing.getEmail());
}
```

Nếu property có @JsonSetter(nulls = Nulls.SKIP), test tương ứng cần xác nhận giá trị cũ vẫn còn.

### 14.3. Nested POJO merge

Tạo Customer có Address đã tồn tại, đánh dấu property address bằng @JsonMerge, rồi gửi JSON chỉ có street. Kiểm tra city cũ vẫn được giữ và street được thay đổi.

### 14.4. Map merge và List append

Với property được đánh dấu @JsonMerge:

- Map giữ key không có trong input và cập nhật key trùng.
- List giữ phần tử cũ và thêm phần tử mới theo semantics collection.
- Không có @JsonMerge, property container được thay thế theo cách deserialize thông thường.

Kiểm thử cả trường hợp list có phần tử trùng để hiểu rõ semantics của kiểu collection đang dùng.

### 14.5. Test reader và target identity

```java
@Test
void updatesExistingMutableBeanInstance() throws Exception {
    UserProfile existing = new UserProfile(
        "An",
        "an@example.com",
        28,
        true
    );

    UserProfile returned = mapper
        .readerForUpdating(existing)
        .readValue("""
            {"displayName": "Binh"}
            """);

    assertSame(existing, returned);
}
```

Test này phù hợp với bean mutable thông thường. Không dùng nó làm giả định cho array, immutable value hoặc custom deserializer không hỗ trợ update tại chỗ.

### 14.6. Test lỗi giữa quá trình update

Gửi payload có một property hợp lệ trước một property sai kiểu. Quan sát object sau exception để xác định có thay đổi một phần hay không. Nếu yêu cầu atomicity, test phải chạy qua luồng cập nhật bản sao và xác nhận object gốc không thay đổi khi lỗi.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Property không có trong JSON bị mất giá trị | Đang deserialize object mới thay vì update target | Dùng readerForUpdating(existing) |
| Gửi null làm xóa giá trị hiện tại | Null tường minh khác với missing | Dùng @JsonSetter(nulls = Nulls.SKIP) nếu null nghĩa là bỏ qua |
| Nested object bị thay toàn bộ | Property chưa được cấu hình merge | Dùng @JsonMerge nếu muốn cập nhật object con hiện có |
| List bị append ngoài ý muốn | Bật @JsonMerge cho collection | Bỏ merge nếu payload phải thay toàn bộ list |
| Map cũ bị mất entry | Property Map bị thay vì merge | Dùng @JsonMerge nếu cần giữ key không có trong input |
| Record không được cập nhật tại chỗ | Record/immutable object không có property mutable | Tạo instance mới qua DTO/builder/copy method |
| Custom deserializer không merge như mong muốn | Chưa hỗ trợ overload update | Triển khai update-aware deserializer hoặc dùng DTO trung gian |
| Null vào primitive tạo giá trị mặc định | Primitive không chứa null | Bật FAIL_ON_NULL_FOR_PRIMITIVES hoặc dùng wrapper |
| Reader update dùng chung gây dữ liệu chéo | Nhiều luồng cập nhật cùng target mutable | Tạo reader theo target và đồng bộ/transaction phù hợp |
| Object đã đổi một phần sau lỗi | Update mutable không tự rollback | Cập nhật bản sao rồi validate và commit |
| Field lạ vẫn bị bỏ qua | Unknown-property policy đang lenient | Bật strictness hoặc dùng update DTO có allowlist |

## 16. Quy trình chọn update semantics

Khi xây dựng chức năng cập nhật một phần:

1. Xác định target là mutable bean, Map, Collection, array hay immutable object.
2. Chọn readerForUpdating(existing) khi muốn cập nhật root object có sẵn.
3. Quy định missing và explicit null có ý nghĩa gì cho từng property.
4. Dùng @JsonSetter(nulls = ...) để kiểm soát null khi cần.
5. Dùng @JsonMerge chỉ cho property lồng nhau thực sự cần merge.
6. Quyết định collection là replace hay append/merge.
7. Kiểm tra custom deserializer có hỗ trợ update không.
8. Giới hạn các field mà client được phép cập nhật.
9. Validate trạng thái hoàn chỉnh sau khi update.
10. Nếu cần atomicity, cập nhật bản sao rồi commit sau khi thành công.
11. Viết test cho missing, null, nested object, Map, List, immutable type và lỗi giữa chừng.
12. Xác nhận semantics API có phù hợp giao thức PATCH mà hệ thống công bố hay không.

Không nên thêm @JsonMerge vào mọi property chỉ để tránh mất dữ liệu. Mỗi property cần semantics rõ ràng để client và server hiểu cùng một cách.

## 17. Bài thực hành tổng hợp

Tạo model mutable:

```java
public class Profile {

    private String displayName;
    private String email;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phone;

    @JsonMerge
    private Address address;

    @JsonMerge
    private Map<String, String> preferences =
        new LinkedHashMap<>();

    private List<String> roles = new ArrayList<>();

    // Constructors, getters and setters
}
```

Khởi tạo profile có đủ dữ liệu, sau đó thực hiện:

1. Dùng readerForUpdating(profile) để chỉ đổi displayName.
2. Gửi JSON không có email và xác nhận email giữ nguyên.
3. Gửi email: null và xác nhận null được áp dụng theo policy mặc định.
4. Gửi phone: null và xác nhận Nulls.SKIP giữ phone cũ.
5. Cập nhật một field của Address và kiểm tra field còn lại được giữ nhờ @JsonMerge.
6. Thêm một preference mới và cập nhật key cũ.
7. Gửi một List roles mới và xác nhận property không merge được thay thế.
8. Thử bật @JsonMerge cho roles và quan sát append semantics.
9. Thử cập nhật record bất biến bằng readerForUpdating và so sánh với cách tạo record mới.
10. Gửi field không biết và kiểm tra FAIL_ON_UNKNOWN_PROPERTIES.
11. Gửi payload có lỗi sau một property hợp lệ để quan sát khả năng thay đổi một phần.
12. Tạo service cập nhật bản sao, validate rồi mới lưu.
13. Viết test cho từng trạng thái missing, value và null.

Bài thực hành hoàn thành khi có thể giải thích chính xác property nào được giữ, thay thế, merge, append hoặc xóa sau mỗi payload.

## 18. Nguyên tắc ghi nhớ

- readerForUpdating(existing) tạo reader dùng object có sẵn làm root target.
- Với mutable bean, property có trong JSON được áp dụng lên object; property bị thiếu thường giữ nguyên.
- Explicit null khác với missing và có thể xóa giá trị hiện tại.
- @JsonSetter(nulls = Nulls.SKIP) bỏ qua null cho property được cấu hình.
- @JsonMerge điều khiển merge cho property lồng nhau; không phải mọi property đều nên bật.
- Map merge giữ entry không có trong input và cập nhật entry tương ứng; collection merge thường thêm phần tử.
- Array có kích thước cố định nên không có append semantics giống List.
- Root Map/Collection update khác với container property bên trong bean.
- Record và immutable object nên được tạo instance mới bằng DTO, builder hoặc copy method.
- Custom deserializer cần hỗ trợ update nếu muốn sửa object con hiện có.
- readerForUpdating không tự triển khai JSON Merge Patch, JSON Patch, authorization, validation hay persistence.
- Mutable update có thể để lại thay đổi một phần nếu deserialize thất bại; dùng bản sao nếu cần atomicity.
- Tạo reader theo từng target mutable; không chia sẻ một target cho nhiều luồng cập nhật đồng thời.
- Kiểm thử missing, null, merge, replace, nested value và lỗi giữa chừng.

Khi dùng readerForUpdating, hãy xác định rõ target nào được cập nhật và semantics của từng property. Phân biệt missing với null, chỉ bật @JsonMerge ở nơi thực sự cần, rồi kiểm thử trạng thái sau update trước khi lưu hoặc trả object cho phần còn lại của ứng dụng.
