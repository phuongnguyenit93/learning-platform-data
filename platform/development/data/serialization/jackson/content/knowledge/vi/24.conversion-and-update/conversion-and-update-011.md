# Kiểm thử ảnh hưởng của annotation và cấu hình lên phép chuyển đổi

Trong Jackson, kết quả chuyển đổi Java object thành JSON hoặc JSON thành Java object không chỉ phụ thuộc dữ liệu đầu vào. Nó còn phụ thuộc annotation trên class/property, serializer và deserializer đã đăng ký, naming strategy, mapper feature, coercion rule, mix-in, view và cấu hình riêng của từng lần đọc/ghi.

Vì vậy, khi thay đổi một annotation hoặc một cấu hình `ObjectMapper`, cần kiểm tra **JSON contract thực tế** ở cả hai chiều. Một thay đổi có thể làm đổi tên field khi serialize nhưng lại thay đổi cách nhận input theo hướng khác; một feature có thể áp dụng toàn mapper trong khi annotation chỉ tác động một property; một `ObjectWriter` hoặc `ObjectReader` có thể dùng cấu hình riêng mà không làm thay đổi mapper gốc.

Bài này tập trung vào cách thiết kế kiểm thử để nhìn thấy tác động của annotation và cấu hình lên phép chuyển đổi, cách cô lập từng thay đổi và cách tránh những test chỉ kiểm tra chuỗi JSON mong manh. Các ví dụ dùng Jackson 2.x, JUnit 5 và package `com.fasterxml.jackson`.

## 1. Kiểm thử phép chuyển đổi là kiểm thử hợp đồng dữ liệu

Một phép chuyển đổi có thể được kiểm tra ở nhiều mức:

1. **Cấu trúc JSON:** field nào có mặt, tên field là gì, node có đúng kiểu string/number/boolean/object/array/null không.
2. **Giá trị JSON:** giá trị được ghi ra có đúng quy tắc định dạng, alias, masking hoặc inclusion không.
3. **Đối tượng sau deserialize:** property Java có nhận đúng giá trị và đúng kiểu không.
4. **Chiều chuyển đổi:** annotation hoặc feature ảnh hưởng serialize, deserialize hay cả hai.
5. **Phạm vi cấu hình:** thay đổi tác động toàn mapper, một class, một property, một view hay chỉ một lần ghi/đọc.
6. **Tính tương thích:** payload cũ, alias cũ, field lạ hoặc giá trị biên có còn được xử lý theo hợp đồng không.

Ví dụ, nếu `password` được đánh dấu `WRITE_ONLY`, test chỉ serialize một object và xác nhận password không xuất hiện là chưa đủ. Cần test thêm rằng JSON request vẫn có thể gán password vào object nếu đó là mục đích của property.

Tương tự, nếu `@JsonProperty("display_name")` đổi tên property, cần kiểm tra cả output có `display_name` và input có thể đọc đúng tên đó. Nếu API còn hỗ trợ tên cũ, cần test riêng `@JsonAlias`.

## 2. Tách rõ serialize và deserialize trong test

Jackson có hai hướng chuyển đổi chính:

```text
Java object  -- serialize -->  JSON
Java object  <-- deserialize -- JSON
```

Một số annotation ảnh hưởng cả hai chiều, một số chỉ ảnh hưởng một chiều:

| Annotation/cấu hình | Serialize Java → JSON | Deserialize JSON → Java |
|---|---|---|
| `@JsonProperty("name")` | Đổi tên property output | Nhận property theo tên JSON đã khai báo |
| `@JsonAlias` | Không đổi tên output | Chấp nhận thêm tên input thay thế |
| `@JsonIgnore` | Bỏ property | Thông thường bỏ qua property |
| `@JsonProperty(access = WRITE_ONLY)` | Không ghi property | Cho phép nhận property từ JSON |
| `@JsonProperty(access = READ_ONLY)` | Có thể ghi property | Bỏ qua giá trị client gửi vào |
| `@JsonInclude` | Quyết định property/value nào được ghi | Không phải quy tắc nhận input |
| `@JsonFormat` | Có thể định dạng output | Có thể quy định cách parse input |
| `PropertyNamingStrategies` | Áp dụng tên property mặc định | Áp dụng tên property khi đọc |
| `FAIL_ON_UNKNOWN_PROPERTIES` | Không tác động output | Điều khiển việc từ chối property lạ |
| `WRITE_ENUMS_USING_TO_STRING` | Điều khiển biểu diễn enum | Không tự quyết định cách đọc nếu không cấu hình tương ứng |

Không nên gom tất cả vào một test round-trip duy nhất. Nếu round-trip thất bại, khó biết lỗi nằm ở serialize hay deserialize. Hãy có test riêng cho từng chiều và thêm round-trip khi hai chiều được kỳ vọng tương thích.

## 3. Tạo mapper kiểm thử có cấu hình tường minh

Một test nên tạo mapper với đúng module và feature cần kiểm tra. Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Không nên dựa vào cấu hình ngầm của môi trường test nếu production dùng mapper được framework cấu hình khác. Với Spring hoặc framework tương tự, hãy kiểm thử mapper bean thực tế hoặc HTTP message converter thực tế ở một lớp integration test.

### 3.1. Cấu hình trước khi mapper được sử dụng

`ObjectMapper` được thiết kế để tái sử dụng sau khi cấu hình hoàn tất. Không nên thay đổi feature hoặc đăng ký module liên tục trên mapper đang phục vụ nhiều request.

Trong test, mỗi trường hợp cần cấu hình khác nhau có thể tạo mapper mới hoặc dùng `mapper.copy()`:

```java
ObjectMapper baseMapper = new ObjectMapper();

ObjectMapper strictMapper = baseMapper.copy();
ObjectMapper tolerantMapper = baseMapper.copy()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Hai mapper có cấu hình độc lập. Cách này giúp so sánh tác động của một feature mà không làm test khác bị ảnh hưởng bởi trạng thái dùng chung.

### 3.2. Dùng `ObjectReader` và `ObjectWriter` cho cấu hình theo lần gọi

Nếu chỉ một lần đọc hoặc ghi cần cấu hình riêng, ưu tiên `ObjectReader` và `ObjectWriter`:

```java
ObjectReader reader = mapper.readerFor(UserRequest.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter writer = mapper.writer()
        .with(SerializationFeature.INDENT_OUTPUT);
```

`ObjectReader` và `ObjectWriter` là đối tượng cấu hình bất biến, phù hợp để dùng cho các biến thể đọc/ghi mà không phải sửa mapper dùng chung. Test nên gọi đúng reader/writer sẽ được sử dụng trong ứng dụng.

## 4. Kiểm tra cấu trúc JSON bằng `JsonNode`

Khi kiểm tra serialize, không phải lúc nào cũng nên so sánh toàn bộ JSON string. Thứ tự property của object thường không phải hợp đồng nghiệp vụ, và khoảng trắng có thể thay đổi theo pretty printer.

Thay vì:

```java
assertEquals("{\"id\":1,\"name\":\"An\"}", json);
```

có thể parse output rồi kiểm tra cấu trúc:

```java
JsonNode node = mapper.readTree(json);

assertEquals(1, node.path("id").asInt());
assertEquals("An", node.path("name").asText());
assertTrue(node.path("active").isBoolean());
assertFalse(node.has("password"));
```

Kiểu node cần được kiểm tra riêng khi kiểu dữ liệu là một phần của contract. Ví dụ JSON number `123` khác JSON string `"123"`; `asText()` có thể chuyển đổi cả hai thành chuỗi và che giấu lỗi kiểu. Hãy dùng `isNumber()`, `isTextual()`, `isBoolean()`, `isArray()`, `isObject()` khi cần.

So sánh nguyên chuỗi vẫn phù hợp khi định dạng chính xác là hợp đồng, ví dụ output chữ ký, canonical JSON, chuỗi date format cụ thể hoặc JSON Lines. Khi đó, hãy kiểm tra rõ vì sao thứ tự/khoảng trắng là quan trọng.

## 5. Kiểm thử `@JsonProperty` và naming strategy

Giả sử class có property `displayName`, nhưng API cần JSON field `display_name`:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class UserProfile {
    private Long id;
    private String displayName;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @JsonProperty("display_name")
    public String getDisplayName() {
        return displayName;
    }

    @JsonProperty("display_name")
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Test serialize:

```java
@Test
void writesExplicitJsonPropertyName() throws Exception {
    UserProfile profile = new UserProfile();
    profile.setId(10L);
    profile.setDisplayName("An Nguyen");

    JsonNode json = mapper.readTree(mapper.writeValueAsString(profile));

    assertEquals("An Nguyen", json.path("display_name").asText());
    assertFalse(json.has("displayName"));
}
```

Test deserialize:

```java
@Test
void readsExplicitJsonPropertyName() throws Exception {
    String input = """
            {"id":10,"display_name":"An Nguyen"}
            """;

    UserProfile profile = mapper.readValue(input, UserProfile.class);

    assertEquals(10L, profile.getId());
    assertEquals("An Nguyen", profile.getDisplayName());
}
```

### 5.1. Kiểm tra ảnh hưởng của naming strategy toàn cục

Jackson có thể áp dụng naming strategy cho property theo cấu hình mapper:

```java
ObjectMapper snakeCaseMapper = new ObjectMapper()
        .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Một class không có `@JsonProperty` có thể được chuyển từ `firstName` thành `first_name`. Test nên kiểm tra đúng mapper và đúng class:

```java
@Test
void appliesGlobalSnakeCaseNamingStrategy() throws Exception {
    PlainUser user = new PlainUser("An", "Nguyen");

    JsonNode json = snakeCaseMapper.readTree(
            snakeCaseMapper.writeValueAsString(user));

    assertTrue(json.has("first_name"));
    assertTrue(json.has("last_name"));
}
```

Tên tường minh qua `@JsonProperty` thường được dùng như tên property được chỉ định, thay vì bị đổi tiếp bởi naming strategy. Nếu class kết hợp annotation tường minh và naming strategy, hãy test output của đúng Jackson version và cấu hình đang dùng; không suy luận tên JSON chỉ từ tên Java.

## 6. Kiểm thử `@JsonAlias` và khả năng tương thích input cũ

`@JsonAlias` cho phép deserialize nhận thêm các tên cũ hoặc tên thay thế, trong khi serialize vẫn dùng tên property chính:

```java
public class PartnerUser {
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "name"})
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Test alias:

```java
@ParameterizedTest
@ValueSource(strings = {"display_name", "displayName", "name"})
void acceptsCurrentAndLegacyNames(String propertyName) throws Exception {
    String json = "{\"" + propertyName + "\":\"An\"}";

    PartnerUser user = mapper.readValue(json, PartnerUser.class);

    assertEquals("An", user.getDisplayName());
}
```

Test output canonical:

```java
@Test
void writesOnlyCanonicalPropertyName() throws Exception {
    PartnerUser user = new PartnerUser();
    user.setDisplayName("An");

    JsonNode json = mapper.readTree(mapper.writeValueAsString(user));

    assertTrue(json.has("display_name"));
    assertFalse(json.has("displayName"));
    assertFalse(json.has("name"));
}
```

Đây là mẫu hữu ích khi API đổi tên field nhưng cần tiếp tục nhận payload cũ trong giai đoạn chuyển đổi. Test nên ghi rõ alias nào được hỗ trợ và thời điểm dự kiến loại bỏ alias.

## 7. Kiểm thử `@JsonIgnore` và access direction

Annotation có thể tạo ra sự khác nhau rõ rệt giữa input và output.

```java
public class CredentialsRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    @JsonIgnore
    private String internalNote;

    // getters và setters
}
```

Test deserialize password:

```java
@Test
void readsWriteOnlyPassword() throws Exception {
    CredentialsRequest request = mapper.readValue(
            "{\"username\":\"an\",\"password\":\"secret\"}",
            CredentialsRequest.class);

    assertEquals("secret", request.getPassword());
}
```

Test serialize:

```java
@Test
void doesNotWriteWriteOnlyOrIgnoredProperties() throws Exception {
    CredentialsRequest request = new CredentialsRequest();
    request.setUsername("an");
    request.setPassword("secret");
    request.setInternalNote("private");

    JsonNode json = mapper.readTree(mapper.writeValueAsString(request));

    assertEquals("an", json.path("username").asText());
    assertFalse(json.has("password"));
    assertFalse(json.has("internalNote"));
}
```

Không dùng round-trip để kết luận `password` được giữ nguyên: serialize đã chủ động loại password, nên deserialize output trở lại sẽ không khôi phục giá trị đó. Hãy test từng chiều theo đúng mục đích của annotation.

## 8. Kiểm thử `@JsonInclude` và khác biệt null/empty

`@JsonInclude` quyết định property nào được đưa vào JSON output dựa trên trạng thái value. Ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProfileResponse {
    private String displayName;
    private String phone;
    private List<String> tags;

    // getters và setters
}
```

Test null:

```java
@Test
void omitsNullProperties() throws Exception {
    ProfileResponse response = new ProfileResponse();
    response.setDisplayName("An");
    response.setPhone(null);
    response.setTags(List.of());

    JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

    assertTrue(json.has("displayName"));
    assertFalse(json.has("phone"));
    assertTrue(json.has("tags"));
    assertTrue(json.path("tags").isArray());
    assertEquals(0, json.path("tags").size());
}
```

`NON_NULL` chỉ bỏ null; list rỗng vẫn được ghi. Nếu dùng `NON_EMPTY`, list rỗng và một số giá trị rỗng khác có thể bị bỏ theo quy tắc inclusion. Test nên bao gồm null, empty string, empty collection và giá trị bình thường để đảm bảo contract không thay đổi ngoài ý muốn.

`@JsonInclude` là quy tắc output. Đừng viết test deserialize mong `NON_NULL` tự từ chối hoặc bỏ qua một input null; cần annotation hoặc deserialization configuration khác nếu input cũng có chính sách riêng.

## 9. Kiểm thử `@JsonFormat` và module ngày giờ

Một property ngày có thể dùng định dạng riêng:

```java
public class ReportRequest {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "dd/MM/uuuu")
    private LocalDate reportDate;

    public LocalDate getReportDate() {
        return reportDate;
    }

    public void setReportDate(LocalDate reportDate) {
        this.reportDate = reportDate;
    }
}
```

Mapper cần đăng ký Java Time module:

```java
ObjectMapper dateMapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Test cả hai chiều:

```java
@Test
void formatsAndParsesDateUsingPropertyPattern() throws Exception {
    ReportRequest request = new ReportRequest();
    request.setReportDate(LocalDate.of(2026, 11, 12));

    JsonNode output = dateMapper.readTree(
            dateMapper.writeValueAsString(request));
    assertEquals("12/11/2026", output.path("reportDate").asText());

    ReportRequest restored = dateMapper.readValue(
            "{\"reportDate\":\"12/11/2026\"}",
            ReportRequest.class);
    assertEquals(LocalDate.of(2026, 11, 12), restored.getReportDate());
}
```

Test input sai format:

```java
@Test
void rejectsDateOutsideDeclaredPattern() {
    assertThrows(JsonProcessingException.class,
            () -> dateMapper.readValue(
                    "{\"reportDate\":\"2026-11-12\"}",
                    ReportRequest.class));
}
```

Một annotation format trên property có thể ghi đè định dạng mặc định của module cho property đó. Hãy test cả property có annotation và property không có annotation nếu cùng kiểu ngày xuất hiện ở nhiều nơi.

## 10. Kiểm thử enum annotation và mapper feature

Ví dụ enum có `toString()` khác `name()`:

```java
public enum OrderStatus {
    NEW("new"),
    IN_PROGRESS("in_progress");

    private final String wireName;

    OrderStatus(String wireName) {
        this.wireName = wireName;
    }

    @Override
    public String toString() {
        return wireName;
    }
}
```

Mapper có thể bật feature để serialize enum bằng `toString()`:

```java
ObjectMapper enumMapper = new ObjectMapper()
        .enable(SerializationFeature.WRITE_ENUMS_USING_TO_STRING)
        .enable(DeserializationFeature.READ_ENUMS_USING_TO_STRING);
```

Test:

```java
@Test
void usesToStringWhenConfiguredForEnumValues() throws Exception {
    String json = enumMapper.writeValueAsString(OrderStatus.IN_PROGRESS);
    assertEquals("\"in_progress\"", json);

    OrderStatus restored = enumMapper.readValue(json, OrderStatus.class);
    assertEquals(OrderStatus.IN_PROGRESS, restored);
}
```

Nếu chỉ bật `WRITE_ENUMS_USING_TO_STRING`, test deserialize cần phản ánh cấu hình đọc thực tế; không mặc định rằng serializer và deserializer tự đổi cùng lúc. Cũng không nên thay đổi `toString()` vì mục đích debug nếu mapper đang dùng `toString()` làm wire representation.

## 11. Kiểm thử feature xử lý property không biết

Một mapper strict có thể từ chối property không được khai báo:

```java
ObjectMapper strictMapper = new ObjectMapper();
ObjectMapper tolerantMapper = new ObjectMapper()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Test strict:

```java
@Test
void strictMapperRejectsUnknownProperty() {
    String json = "{\"name\":\"An\",\"legacyFlag\":true}";

    assertThrows(UnrecognizedPropertyException.class,
            () -> strictMapper.readValue(json, SimpleUser.class));
}
```

Test tolerant:

```java
@Test
void tolerantMapperIgnoresUnknownProperty() throws Exception {
    String json = "{\"name\":\"An\",\"legacyFlag\":true}";

    SimpleUser user = tolerantMapper.readValue(json, SimpleUser.class);

    assertEquals("An", user.getName());
}
```

Nếu dùng `@JsonIgnoreProperties(ignoreUnknown = true)` trên class, test nên xác nhận policy của class đó độc lập với mapper strict. Annotation có thể làm class chấp nhận property lạ ngay cả khi mapper mặc định strict.

Không nên tắt `FAIL_ON_UNKNOWN_PROPERTIES` toàn cục chỉ để một endpoint tương thích payload cũ nếu các endpoint khác cần validation nghiêm ngặt. Có thể dùng `ObjectReader` riêng hoặc DTO riêng cho endpoint đó.

## 12. Kiểm thử coercion và kiểu dữ liệu đầu vào

Jackson có thể chuyển đổi một số scalar sang kiểu khác tùy feature/coercion configuration. Ví dụ, một số cấu hình cho phép đọc chuỗi số thành integer hoặc scalar đơn thành collection.

Khi contract yêu cầu `quantity` phải là JSON number, đừng chỉ kiểm tra giá trị Java sau deserialize. Nếu mapper cho phép coercion, JSON string `"3"` có thể được chấp nhận và trở thành integer `3`.

Test contract strict nên xác nhận input sai kiểu bị từ chối:

```java
@Test
void rejectsStringWhenJsonNumberIsRequired() {
    String json = "{\"quantity\":\"3\"}";

    assertThrows(JsonProcessingException.class,
            () -> strictQuantityMapper.readValue(json, QuantityRequest.class));
}
```

Nếu dùng Jackson 2.12 trở lên, `CoercionConfig` có thể cấu hình hành vi theo logical type hoặc raw class. Vì API coercion và default có thể thay đổi theo version, hãy cấu hình cụ thể theo version đang dùng và viết test cho từng input quan trọng thay vì dựa vào default.

Các input biên nên kiểm tra:

- Number thay cho string và string thay cho number.
- `null` vào primitive hoặc wrapper type.
- Boolean dạng chuỗi `"true"` so với JSON boolean `true`.
- Scalar đơn vào property collection.
- Array một phần tử vào scalar khi feature đó được bật.
- Chuỗi rỗng và chuỗi chỉ có whitespace.

## 13. Kiểm thử annotation ở property so với cấu hình toàn mapper

Một điểm quan trọng là annotation thường có phạm vi hẹp hơn cấu hình mapper. Ví dụ naming strategy áp dụng cho nhiều property, trong khi `@JsonProperty` chỉ định tên cụ thể cho một property.

Có thể kiểm tra hai lớp tác động bằng một test:

```java
ObjectMapper mapper = new ObjectMapper()
        .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

@Test
void explicitPropertyNameAndGlobalNamingStrategyAreBothAppliedAsExpected()
        throws Exception {
    NamingExample value = new NamingExample();
    value.setFirstName("An");
    value.setExternalCode("X-1");

    JsonNode json = mapper.readTree(mapper.writeValueAsString(value));

    assertTrue(json.has("first_name"));
    assertTrue(json.has("partnerCode"));
    assertFalse(json.has("external_code"));
}
```

Model:

```java
public class NamingExample {
    private String firstName;
    private String externalCode;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    @JsonProperty("partnerCode")
    public String getExternalCode() {
        return externalCode;
    }

    @JsonProperty("partnerCode")
    public void setExternalCode(String externalCode) {
        this.externalCode = externalCode;
    }
}
```

Test này ghi lại hành vi mong đợi khi kết hợp cấu hình toàn cục với tên property tường minh. Nếu thay Jackson version hoặc naming strategy, test sẽ phát hiện thay đổi contract.

## 14. Kiểm thử `@JsonView` và filter theo từng writer

Nếu một class có nhiều mức output, test từng view riêng:

```java
public class Views {
    public interface Public {}
    public interface Internal extends Public {}
}

public class AccountViewModel {
    @JsonView(Views.Public.class)
    private String displayName;

    @JsonView(Views.Internal.class)
    private String email;
}
```

```java
String publicJson = mapper.writerWithView(Views.Public.class)
        .writeValueAsString(account);
String internalJson = mapper.writerWithView(Views.Internal.class)
        .writeValueAsString(account);
```

Test public output không có email; test internal output có email. Nếu mapper bật `MapperFeature.DEFAULT_VIEW_INCLUSION`, property không gắn `@JsonView` có thể vẫn xuất hiện trong view. Hãy chọn rõ feature này và viết test phản ánh đúng cấu hình.

Với property filter, tạo các `ObjectWriter` tương ứng với allowlist khác nhau rồi test từng output. Đừng chỉ test filter provider được tạo; test JSON thực tế để bảo đảm target class đã được gắn `@JsonFilter` và writer sử dụng đúng provider.

## 15. Kiểm thử custom serializer/deserializer đã đăng ký qua module

Khi một module thay đổi cách chuyển đổi của kiểu, cần test rằng module đã được đăng ký trên mapper đang dùng và serializer/deserializer thực sự được gọi.

Ví dụ module:

```java
SimpleModule module = new SimpleModule("money-module");
module.addSerializer(Money.class, new MoneySerializer());
module.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = new ObjectMapper().registerModule(module);
```

Test serialize và deserialize:

```java
@Test
void usesRegisteredMoneySerializer() throws Exception {
    String json = mapper.writeValueAsString(new Money("VND", new BigDecimal("1000")));
    assertEquals("\"VND 1000\"", json);
}

@Test
void usesRegisteredMoneyDeserializer() throws Exception {
    Money money = mapper.readValue("\"VND 1000\"", Money.class);
    assertEquals("VND", money.currency());
    assertEquals(new BigDecimal("1000"), money.amount());
}
```

Ngoài test hành vi, có thể dùng spy/fake trong unit test nếu cần xác nhận serializer được gọi, nhưng phần lớn trường hợp assert JSON và object kết quả là bằng chứng tốt hơn vì chúng kiểm tra contract quan sát được.

## 16. Round-trip test: dùng đúng lúc

Round-trip là serialize một object, rồi deserialize JSON kết quả trở lại:

```java
String json = mapper.writeValueAsString(original);
UserProfile restored = mapper.readValue(json, UserProfile.class);
```

Có thể so sánh các property cần giữ:

```java
assertEquals(original.getId(), restored.getId());
assertEquals(original.getDisplayName(), restored.getDisplayName());
```

Round-trip hữu ích khi contract yêu cầu dữ liệu được bảo toàn qua hai chiều. Tuy nhiên, nó không phù hợp với mọi model:

- `WRITE_ONLY` cố ý loại property khỏi output.
- `READ_ONLY` cố ý bỏ qua input.
- `@JsonIgnore` loại property khỏi quá trình binding.
- `@JsonInclude` có thể bỏ null/empty khỏi output.
- Serializer có thể chuẩn hóa giá trị, ví dụ đổi timezone hoặc làm tròn số.
- `@JsonAlias` chấp nhận nhiều input name nhưng chỉ có một output name canonical.

Trong những trường hợp đó, hãy kiểm tra từng chiều theo chính sách thay vì so sánh toàn bộ object trước và sau.

## 17. Kiểm tra JSON contract bằng helper tái sử dụng

Với nhiều test, có thể tạo helper parse JSON và so sánh node:

```java
private JsonNode toTree(ObjectMapper mapper, Object value) throws Exception {
    return mapper.readTree(mapper.writeValueAsString(value));
}
```

Hoặc so sánh JSON expected với actual theo cấu trúc:

```java
JsonNode expected = mapper.readTree("""
        {
          "id": 10,
          "display_name": "An"
        }
        """);

JsonNode actual = mapper.readTree(mapper.writeValueAsString(profile));

assertEquals(expected, actual);
```

`JsonNode.equals()` so sánh cấu trúc và giá trị node; thứ tự property trong object không cần được dùng làm tiêu chí. Với số, cần thống nhất kiểu số và cách biểu diễn nếu contract quan tâm đến precision hoặc scale.

Không nên tạo helper quá tổng quát che giấu cấu hình mapper. Tên test nên cho biết mapper nào, feature nào và contract nào đang được xác nhận.

## 18. Dùng parameterized test cho nhiều cấu hình hoặc input

JUnit 5 parameterized test giúp kiểm tra cùng một quy tắc với nhiều input:

```java
@ParameterizedTest
@CsvSource({
        "2026-11-12, 2026-11-12",
        "2024-02-29, 2024-02-29"
})
void readsSupportedIsoDates(String input, String expected) throws Exception {
    LocalDate actual = dateMapper.readValue(
            "\"" + input + "\"",
            LocalDate.class);

    assertEquals(LocalDate.parse(expected), actual);
}
```

Có thể tạo test matrix cho:

- Alias field cũ và tên field mới.
- Enum ID hợp lệ và không hợp lệ.
- Ngày hợp lệ, ngày không tồn tại và pattern sai.
- Null, empty và non-empty.
- Unknown property với mapper strict và tolerant.
- Scalar/array với feature bật và tắt.

Mỗi test case nên nêu rõ cấu hình được áp dụng. Nếu chỉ thay đổi một feature giữa hai mapper, giữ các cấu hình còn lại giống nhau để kết quả có thể quy về đúng nguyên nhân.

## 19. Kiểm thử khác biệt giữa mapper mặc định và mapper production

Một lỗi phổ biến là test tạo mapper mới:

```java
ObjectMapper mapper = new ObjectMapper();
```

trong khi production dùng mapper đã được cấu hình bởi framework với module, mix-in, naming strategy hoặc feature khác. Test có thể pass nhưng endpoint thực tế serialize khác.

Nên có hai lớp kiểm thử:

1. **Unit test:** tạo mapper nhỏ, cấu hình tường minh để kiểm tra annotation hoặc một feature độc lập.
2. **Integration test:** lấy mapper bean thực tế hoặc gọi HTTP endpoint/message converter để xác nhận cấu hình production.

Ví dụ Spring test có thể inject `ObjectMapper` bean:

```java
@SpringBootTest
class JacksonConfigurationIntegrationTest {
    @Autowired
    ObjectMapper objectMapper;

    @Test
    void applicationMapperUsesExpectedNamingStrategy() throws Exception {
        JsonNode json = objectMapper.readTree(
                objectMapper.writeValueAsString(new PlainUser("An", "Nguyen")));

        assertTrue(json.has("first_name"));
    }
}
```

Nếu ứng dụng có nhiều mapper bean, inject đúng bean bằng qualifier. Nếu cần xác nhận HTTP serialization, gọi endpoint qua test client để đi qua converter thực tế.

## 20. Kiểm thử thứ tự ưu tiên và tương tác cấu hình

Annotation và cấu hình mapper có thể cùng tác động một property. Không nên chỉ test từng thứ riêng lẻ nếu production dùng chúng đồng thời.

Các tổ hợp nên cân nhắc:

| Cấu hình kết hợp | Điều cần xác nhận |
|---|---|
| `@JsonProperty` + naming strategy | Tên JSON cuối cùng của property |
| `@JsonFormat` + date module | Pattern property có được áp dụng cho cả đọc và ghi không |
| `@JsonInclude` + global inclusion | Null/empty property có xuất hiện không |
| `@JsonIgnore` + getter/setter visibility | Property có thực sự bị bỏ ở cả hai chiều không |
| `@JsonView` + `DEFAULT_VIEW_INCLUSION` | Property không gắn view có xuất hiện không |
| `@JsonAlias` + unknown property policy | Alias được nhận, tên lạ khác vẫn bị xử lý theo policy nào |
| Mix-in + annotation target | Annotation cuối cùng được Jackson nhận diện là gì |
| Module serializer + property `using` | Serializer nào được dùng tại vị trí đó |

Không có một bảng ưu tiên duy nhất áp dụng cho mọi annotation. Jackson hợp nhất metadata theo loại annotation, member, property, type introspection và version. Vì vậy, khi hai nguồn cấu hình tương tác, test JSON thực tế là cách xác nhận đáng tin cậy nhất.

## 21. Kiểm thử cấu hình theo từng lần đọc/ghi

`ObjectReader` và `ObjectWriter` giúp kiểm tra policy riêng mà không thay đổi mapper:

```java
ObjectReader strictReader = mapper.readerFor(SimpleUser.class);
ObjectReader tolerantReader = mapper.readerFor(SimpleUser.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter compactWriter = mapper.writer();
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
```

Test có thể so sánh:

```java
@Test
void readerSpecificFeatureDoesNotChangeOtherReader() throws Exception {
    String json = "{\"name\":\"An\",\"legacy\":true}";

    assertThrows(JsonProcessingException.class,
            () -> strictReader.readValue(json));

    SimpleUser user = tolerantReader.readValue(json);
    assertEquals("An", user.getName());
}
```

Đây là cách tốt để bảo đảm một endpoint cần tolerant input không làm thay đổi hành vi của các endpoint strict khác.

## 22. Kiểm thử regression khi thay đổi annotation

Khi thay annotation, hãy xác định JSON contract trước và sau thay đổi. Ví dụ đổi:

```java
@JsonProperty("fullName")
```

thành:

```java
@JsonProperty("display_name")
@JsonAlias("fullName")
```

Các test regression nên xác nhận:

- Output mới chỉ ghi `display_name`.
- Input mới với `display_name` vẫn đọc được.
- Input cũ với `fullName` vẫn đọc được trong giai đoạn tương thích.
- Input với tên không được hỗ trợ vẫn bị từ chối hoặc xử lý theo unknown-property policy.
- Các property khác không đổi tên ngoài ý muốn.

Một thay đổi annotation nhỏ có thể ảnh hưởng nhiều endpoint nếu class được dùng chung. Trước khi sửa, cần xác định mọi ranh giới serialize/deserialize sử dụng class đó; sau khi sửa, test các contract quan trọng ở từng ranh giới.

## 23. Kiểm thử lỗi và thông báo lỗi

Không chỉ kiểm tra rằng deserialize thất bại. Với API, nên xác nhận lỗi được chuyển thành response có cấu trúc và không làm lộ payload nhạy cảm.

Ví dụ test input sai kiểu:

```java
@Test
void rejectsInvalidQuantity() {
    String json = "{\"quantity\":\"many\"}";

    JsonProcessingException error = assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(json, QuantityRequest.class));

    assertTrue(error.getMessage().contains("quantity"));
}
```

Ở tầng controller/service, có thể test exception handler trả mã lỗi phù hợp và message không chứa password/token hoặc toàn bộ input. Không nên phụ thuộc chính xác toàn bộ chuỗi exception nội bộ của Jackson nếu version upgrade có thể đổi wording; hãy kiểm tra loại lỗi hoặc path/field quan trọng.

## 24. Một bộ test mẫu tổng hợp

Một test class có thể gom các ví dụ cơ bản sau:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class JacksonConversionContractTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void writesCanonicalFieldName() throws Exception {
        UserProfile profile = new UserProfile();
        profile.setDisplayName("An");

        JsonNode json = mapper.readTree(mapper.writeValueAsString(profile));

        assertTrue(json.has("display_name"));
        assertFalse(json.has("displayName"));
    }

    @Test
    void readsCanonicalFieldName() throws Exception {
        UserProfile profile = mapper.readValue(
                "{\"display_name\":\"An\"}",
                UserProfile.class);

        assertEquals("An", profile.getDisplayName());
    }

    @Test
    void ignoresWriteOnlySecretOnOutput() throws Exception {
        CredentialsRequest request = new CredentialsRequest();
        request.setUsername("an");
        request.setPassword("secret");

        JsonNode json = mapper.readTree(mapper.writeValueAsString(request));

        assertFalse(json.has("password"));
    }

    @Test
    void keepsJsonNumberAsNumber() throws Exception {
        QuantityResponse response = new QuantityResponse(3);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

        assertTrue(json.path("quantity").isNumber());
        assertEquals(3, json.path("quantity").intValue());
    }
}
```

Các model trong ví dụ cần được khai báo theo annotation tương ứng ở những phần trước. Trong dự án thật, nên tách test class theo contract hoặc module để dễ xác định mapper và model đang được kiểm tra.

## 25. Những lỗi thường gặp khi kiểm thử

| Triệu chứng | Nguyên nhân có thể | Cách cải thiện |
|---|---|---|
| Test so sánh JSON string thất bại dù dữ liệu đúng | Thứ tự property hoặc khoảng trắng thay đổi | Parse thành `JsonNode` và so sánh cấu trúc |
| Test round-trip không phát hiện field bị mất | Hai chiều cùng bỏ field hoặc test không kiểm tra field đó | Test serialize và deserialize độc lập |
| Password bị mất sau round-trip | `WRITE_ONLY` cố ý không ghi password ra JSON | Kiểm tra input và output theo hai test riêng |
| Test pass nhưng production sai | Dùng mapper tự tạo khác mapper framework | Test mapper bean hoặc HTTP converter thực tế |
| Thay đổi global feature làm test khác lỗi | Mapper dùng chung bị thay đổi cấu hình | Tạo mapper riêng hoặc dùng reader/writer riêng |
| `asText()` làm test bỏ qua sai kiểu JSON | Number và string đều có thể được đọc thành text | Kiểm tra `isNumber()`/`isTextual()` trước |
| Alias cũ vô tình trở thành tên output | Nhầm `@JsonAlias` với `@JsonProperty` | Test tên output canonical và các tên input riêng |
| Test chỉ kiểm tra happy path | Không có input null, empty, unknown hoặc sai kiểu | Tạo test matrix cho dữ liệu biên |
| Annotation và feature xung đột không được phát hiện | Chỉ test từng cấu hình riêng | Test tổ hợp giống production |
| Test phụ thuộc message exception chính xác | Wording thay đổi theo version Jackson | Kiểm tra exception type và path quan trọng |

## 26. Quy trình xây dựng test matrix

Khi một model có nhiều annotation và mapper feature, lập bảng kiểm thử trước khi viết test:

| Nhóm | Câu hỏi kiểm tra | Bằng chứng nên assert |
|---|---|---|
| Tên property | JSON dùng tên nào? | `has()` với tên đúng và `has()` với tên không mong muốn |
| Hướng truy cập | Field nhận input, xuất output hay cả hai? | Giá trị Java sau read và field có/không có sau write |
| Inclusion | Null/empty có bị bỏ không? | `has()`, `isNull()`, `size()` |
| Format | Ngày/số/enum được biểu diễn ra sao? | Chuỗi output và object sau parse |
| Unknown input | Field lạ bị từ chối hay bỏ qua? | Exception hoặc object kết quả |
| Coercion | Input sai kiểu có được chuyển đổi không? | Exception hoặc node/value kiểu cụ thể |
| Scope | Cấu hình tác động mapper/property/writer nào? | So sánh hai mapper hoặc hai reader/writer |
| Tương thích | Alias hoặc payload cũ còn hoạt động không? | Parameterized test cho từng biến thể |
| Regression | Property khác có bị ảnh hưởng không? | Assert các field quan trọng của toàn JSON contract |

Mỗi test nên thay đổi một yếu tố chính. Khi cần test tương tác, hãy ghi rõ các annotation và feature đang được kết hợp để người bảo trì hiểu nguyên nhân của output.

## 27. Ghi nhớ

Annotation và cấu hình Jackson có thể tác động khác nhau lên serialize và deserialize, ở phạm vi property, class, mapper hoặc từng lần đọc/ghi. Hãy test JSON output và object sau deserialize độc lập; dùng `JsonNode` để kiểm tra tên, kiểu và sự hiện diện của field; dùng `ObjectReader`/`ObjectWriter` hoặc mapper riêng để cô lập cấu hình; và chỉ dùng round-trip khi contract thực sự yêu cầu dữ liệu được bảo toàn.

Một bộ kiểm thử tốt không chỉ xác nhận trường hợp thành công mà còn ghi lại hành vi với alias, null/empty, field lạ, sai kiểu, format, secret và cấu hình kết hợp. Khi kiểm thử trên mapper thực tế của ứng dụng và kiểm tra đúng hợp đồng quan sát được, thay đổi annotation hoặc feature sẽ ít có nguy cơ làm hỏng dữ liệu của client và hệ thống tích hợp.
