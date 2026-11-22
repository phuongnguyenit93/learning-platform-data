# Kiểm thử null, thiếu, rỗng và giá trị mặc định

Khi Jackson deserialize JSON thành Java object, một property có thể ở nhiều trạng thái khác nhau: không xuất hiện, xuất hiện với giá trị null, xuất hiện với chuỗi rỗng, collection rỗng, object rỗng hoặc một giá trị cụ thể. Các trạng thái này có thể tạo ra kết quả Java khác nhau, nhưng đôi khi lại hội tụ về cùng một giá trị sau binding. Nếu chỉ kiểm tra getter cuối cùng, test có thể bỏ sót lỗi trong contract của API.

Kiểm thử đúng cần xác định rõ ý nghĩa của từng trạng thái và quan sát cả giá trị lẫn cách Jackson tạo object. Ví dụ, property bị thiếu trong mutable bean thường không gọi setter và giữ giá trị khởi tạo; explicit null có thể gọi setter với null; chuỗi rỗng được gán thành chuỗi rỗng; array rỗng tạo collection không có phần tử. Với creator-based binding, missing và null có thể được xử lý theo feature hoặc logic constructor. Với PATCH, missing thường có nghĩa giữ giá trị hiện tại, còn null có thể có nghĩa xóa.

## 1. Phân biệt các trạng thái đầu vào

Với một property tên nickname, các JSON sau có ý nghĩa khác nhau:

`````````json
{}
`````````

Property nickname bị thiếu. Không có token cho property này.

`````````json
{"nickname": null}
`````````

Property xuất hiện và có explicit null.

`````````json
{"nickname": ""}
`````````

Property xuất hiện với chuỗi rỗng.

`````````json
{"nickname": "An"}
`````````

Property xuất hiện với một giá trị cụ thể.

Với collection và object, còn có những trường hợp riêng:

`````````json
{"tags": []}
`````````

Collection có mặt nhưng không có phần tử.

`````````json
{"tags": null}
`````````

Collection có mặt và có giá trị null.

`````````json
{"address": {}}
`````````

Object con có mặt nhưng không có property nào.

`````````json
{"address": null}
`````````

Object con có mặt và có giá trị null.

Không được gộp các trường hợp trên chỉ vì một số trường hợp cho ra Java null hoặc collection rỗng. Contract phải quy định rõ trạng thái nào được chấp nhận và chúng có ý nghĩa gì.

### 1.1. Bảng trạng thái cần kiểm thử

| JSON input | Ý nghĩa | Kết quả có thể mong đợi |
|---|---|---|
| Property không xuất hiện | Missing | Giữ initializer/default hoặc báo lỗi |
| Property là null | Explicit null | Gán null, bỏ qua, dùng empty hoặc báo lỗi theo policy |
| String là chuỗi rỗng | Empty string | Gán chuỗi rỗng hoặc báo lỗi validation |
| String là whitespace | Text có nội dung whitespace | Giữ nguyên, trim hoặc từ chối theo contract |
| Array là [] | Empty collection | Collection rỗng |
| Array là null | Null collection | Null, giữ giá trị cũ hoặc lỗi |
| Array có phần tử null | Null content | Giữ, bỏ qua, thay bằng empty hoặc lỗi |
| Object là {} | Empty object | Tạo object con với default của nó |
| Object là null | Null nested object | Null hoặc xử lý theo null policy |

## 2. Chuẩn bị ObjectMapper dùng trong test

Nên tạo mapper giống cấu hình production hoặc dùng factory method chung của ứng dụng. Không cấu hình một mapper khác biệt trong test rồi kết luận hành vi production cũng giống vậy.

Ví dụ cơ bản:

`````````java
private final ObjectMapper mapper = new ObjectMapper();
`````````

Nếu ứng dụng có module Java Time, custom serializer/deserializer hoặc naming strategy, test mapper cần đăng ký cùng những module cần thiết:

`````````java
ObjectMapper mapper = JsonMapper.builder()
    .findAndAddModules()
    .build();
`````````

Trong dự án Spring Boot, có thể inject ObjectMapper mà application context đang dùng vào test. Với test cần kiểm tra một feature riêng, tạo mapper riêng trong test đó để thể hiện rõ cấu hình đang được thử.

Không thay đổi cấu hình của mapper dùng chung sau khi nó đã được sử dụng. Tạo mapper hoàn chỉnh trước khi test chạy giúp tránh ảnh hưởng giữa các test.

## 3. Kiểm thử missing và explicit null trong mutable bean

Một bean có constructor mặc định và setter là trường hợp dễ quan sát nhất:

`````````java
public class ProfileRequest {
    private String nickname;
    private boolean nicknameSetterCalled;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nicknameSetterCalled = true;
        this.nickname = nickname;
    }

    public boolean isNicknameSetterCalled() {
        return nicknameSetterCalled;
    }
}
`````````

Test:

`````````java
class ProfileRequestTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void missingPropertyDoesNotCallSetter() throws Exception {
        ProfileRequest request =
            mapper.readValue("{}", ProfileRequest.class);

        assertNull(request.getNickname());
        assertFalse(request.isNicknameSetterCalled());
    }

    @Test
    void explicitNullCallsSetterWithNull() throws Exception {
        ProfileRequest request = mapper.readValue(
            "{\"nickname\":null}",
            ProfileRequest.class
        );

        assertNull(request.getNickname());
        assertTrue(request.isNicknameSetterCalled());
    }

    @Test
    void emptyStringCallsSetterWithEmptyValue() throws Exception {
        ProfileRequest request = mapper.readValue(
            "{\"nickname\":\"\"}",
            ProfileRequest.class
        );

        assertEquals("", request.getNickname());
        assertTrue(request.isNicknameSetterCalled());
    }
}
`````````

Ở đây, cờ nicknameSetterCalled chỉ dùng để quan sát hành vi binding trong test. Không đưa side effect thật như ghi database hoặc gửi message vào setter chỉ để kiểm tra setter có được gọi hay không.

Nếu field không có initializer, cả missing và explicit null đều có thể làm getter trả null. Cờ presence mới cho biết property có xuất hiện và setter có chạy hay không. Trong model production, chỉ thêm presence flag khi contract thực sự cần phân biệt trạng thái đó.

## 4. Kiểm thử giá trị khởi tạo và default

Với mutable bean, field initializer thường được giữ khi property bị thiếu:

`````````java
public class SearchRequest {
    private String query = "";
    private int page = 1;
    private boolean includeArchived = false;

    public String getQuery() { return query; }
    public void setQuery(String query) { this.query = query; }

    public int getPage() { return page; }
    public void setPage(int page) { this.page = page; }

    public boolean isIncludeArchived() { return includeArchived; }
    public void setIncludeArchived(boolean value) {
        this.includeArchived = value;
    }
}
`````````

Test missing giữ initializer:

`````````java
@Test
void missingPropertiesKeepFieldInitializers() throws Exception {
    SearchRequest request =
        mapper.readValue("{}", SearchRequest.class);

    assertEquals("", request.getQuery());
    assertEquals(1, request.getPage());
    assertFalse(request.isIncludeArchived());
}
`````````

Explicit null có thể ghi đè initializer tùy kiểu và null policy:

`````````java
@Test
void explicitNullCanReplaceReferenceDefault() throws Exception {
    ProfileWithDefault request = mapper.readValue(
        "{\"nickname\":null}",
        ProfileWithDefault.class
    );

    assertNull(request.getNickname());
}
`````````

Trong khi đó, nếu setter dùng Nulls.SKIP, explicit null sẽ bị bỏ qua và initializer vẫn được giữ. Vì vậy, test default cần bao gồm cả missing và explicit null; chỉ test JSON rỗng không đủ để xác nhận null policy.

### 4.1. Default của primitive

Java primitive không thể chứa null. Ví dụ:

`````````java
public class CounterRequest {
    private int count = 7;
    private boolean enabled = true;

    public int getCount() { return count; }
    public void setCount(int count) { this.count = count; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
`````````

Khi property bị thiếu, initializer có thể được giữ. Khi explicit null được bind vào primitive, hành vi mặc định của Jackson có thể chuyển về giá trị mặc định primitive như 0 hoặc false. Để tránh nhận dữ liệu null âm thầm, bật:

`````````java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
`````````

Test:

`````````java
@Test
void explicitNullForPrimitiveFailsWhenConfigured() {
    ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();

    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue(
            "{\"count\":null}",
            CounterRequest.class
        )
    );
}
`````````

Nếu contract cần phân biệt null với 0 hoặc false, dùng wrapper type Integer/Boolean thay vì primitive. Wrapper type có thể giữ null; primitive không thể.

### 4.2. Không nhầm default của Java với default trong contract

Giá trị 0, false và null có thể chỉ là giá trị mặc định của Java, không nhất thiết là default nghiệp vụ. Ví dụ page mặc định là 1, số lần retry mặc định là 3, còn account balance mặc định bằng 0 có thể cần được khởi tạo bởi domain factory.

Hãy viết test xác nhận default nghiệp vụ rõ ràng. Không dựa vào Java zero initialization để ngầm diễn tả quy tắc của API.

## 5. JsonSetter và các chính sách xử lý null

Jackson hỗ trợ null policy cho property qua JsonSetter:

`````````java
public class ProfileWithNullPolicies {
    private String preserve = "initial";
    private String reject = "initial";
    private String empty = "initial";

    @JsonSetter(value = "preserve", nulls = Nulls.SKIP)
    public void setPreserve(String value) {
        preserve = value;
    }

    @JsonSetter(value = "reject", nulls = Nulls.FAIL)
    public void setReject(String value) {
        reject = value;
    }

    @JsonSetter(value = "empty", nulls = Nulls.AS_EMPTY)
    public void setEmpty(String value) {
        empty = value;
    }

    public String getPreserve() { return preserve; }
    public String getReject() { return reject; }
    public String getEmpty() { return empty; }
}
`````````

Các policy:

| Policy | Hành vi khi JSON có explicit null |
|---|---|
| Nulls.SET | Gán null cho property |
| Nulls.SKIP | Bỏ qua việc gán, giữ giá trị hiện có |
| Nulls.FAIL | Ném lỗi mapping |
| Nulls.AS_EMPTY | Dùng empty value do deserializer của kiểu đích cung cấp |
| Nulls.DEFAULT | Dùng policy mặc định của Jackson |

Test từng policy:

`````````java
@Test
void nullSkipPreservesInitializer() throws Exception {
    ProfileWithNullPolicies value = mapper.readValue(
        "{\"preserve\":null}",
        ProfileWithNullPolicies.class
    );

    assertEquals("initial", value.getPreserve());
}

@Test
void nullFailRejectsExplicitNull() {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(
            "{\"reject\":null}",
            ProfileWithNullPolicies.class
        )
    );
}

@Test
void nullAsEmptyUsesStringDeserializerEmptyValue() throws Exception {
    ProfileWithNullPolicies value = mapper.readValue(
        "{\"empty\":null}",
        ProfileWithNullPolicies.class
    );

    assertEquals("", value.getEmpty());
}
`````````

Nulls.AS_EMPTY phụ thuộc empty value mà deserializer của kiểu đích cung cấp. Với String, empty value thường là chuỗi rỗng; với collection, thường là collection rỗng. Không giả định mọi kiểu custom đều có cùng empty value. Nếu cần behavior cụ thể, viết custom deserializer hoặc kiểm tra trong factory/domain constructor.

### 5.1. Nulls.SKIP không phân biệt missing với null

Với property preserve trong ví dụ trên:

- Missing: setter không được gọi, giá trị initializer giữ nguyên.
- Explicit null: policy SKIP bỏ qua setter, giá trị initializer cũng giữ nguyên.

Kết quả getter giống nhau. Nếu use case cần biết client có gửi property hay không, phải theo dõi presence riêng. Nulls.SKIP chỉ quyết định việc gán; nó không cung cấp một cờ cho biết null đã xuất hiện.

### 5.2. Nulls content cho collection

Null policy của property và policy của phần tử trong collection là hai điều khác nhau:

`````````java
public class TagRequest {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(
        value = "tags",
        nulls = Nulls.SET,
        contentNulls = Nulls.SKIP
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
`````````

Với cấu hình trên, property tags có thể nhận null, còn phần tử null bên trong list bị bỏ qua khi Jackson xử lý content null. Test:

`````````java
@Test
void contentNullSkipRemovesNullElements() throws Exception {
    TagRequest request = mapper.readValue(
        "{\"tags\":[\"java\",null,\"jackson\"]}",
        TagRequest.class
    );

    assertEquals(List.of("java", "jackson"), request.getTags());
}
`````````

Nếu muốn từ chối phần tử null:

`````````java
@JsonSetter(contentNulls = Nulls.FAIL)
public void setTags(List<String> tags) {
    this.tags = tags;
}
`````````

Test riêng array chứa null và xác nhận lỗi. Đừng chỉ test tags: null; đó là null của cả collection, không phải null content.

## 6. Kiểm thử empty string, whitespace và empty collection

Empty không phải null:

`````````java
@Test
void emptyStringIsPreserved() throws Exception {
    ProfileRequest request = mapper.readValue(
        "{\"nickname\":\"\"}",
        ProfileRequest.class
    );

    assertEquals("", request.getNickname());
}
`````````

Whitespace cũng không tự động là empty:

`````````java
@Test
void whitespaceStringIsPreservedByDefaultBinding() throws Exception {
    ProfileRequest request = mapper.readValue(
        "{\"nickname\":\"   \"}",
        ProfileRequest.class
    );

    assertEquals("   ", request.getNickname());
}
`````````

Nếu domain yêu cầu trim hoặc từ chối whitespace-only, test rule đó ở validation/domain layer thay vì giả định Jackson tự chuẩn hóa mọi String.

Empty collection:

`````````java
@Test
void emptyArrayCreatesEmptyCollection() throws Exception {
    TagRequest request = mapper.readValue(
        "{\"tags\":[]}",
        TagRequest.class
    );

    assertNotNull(request.getTags());
    assertTrue(request.getTags().isEmpty());
}
`````````

Empty object:

`````````java
@Test
void emptyNestedObjectCreatesObjectWithItsDefaults() throws Exception {
    CustomerRequest request = mapper.readValue(
        "{\"address\":{}}",
        CustomerRequest.class
    );

    assertNotNull(request.getAddress());
    assertEquals("unknown", request.getAddress().getCity());
}
`````````

Test empty object cần model con có default rõ ràng. Một object {} không có nghĩa nested object là null; Jackson vẫn có thể tạo instance và để các property con ở trạng thái default.

### 6.1. Phân biệt các dạng collection

| Input | Test nên xác nhận |
|---|---|
| Không có tags | Default/initializer có được giữ không? |
| tags: null | Null policy của cả property là gì? |
| tags: [] | Có tạo list rỗng không? |
| tags: [null] | Content null được giữ, bỏ hay từ chối? |
| tags: [""] | Empty string có hợp lệ không? |
| tags: [" "] | Whitespace có được giữ hay validation từ chối? |

Đối với Map, kiểm tra tương tự: property missing, null, map rỗng, entry có value null và key/value rỗng theo contract.

## 7. Kiểm thử creator-based binding

Với constructor hoặc factory dùng JsonCreator, Jackson thu thập property rồi gọi creator. Missing và explicit null có thể đi vào creator dưới dạng null nếu không bật feature từ chối.

Ví dụ:

`````````java
public final class PageRequest {
    private final String query;
    private final Integer page;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PageRequest(
            @JsonProperty(value = "query", required = true) String query,
            @JsonProperty("page") Integer page) {
        this.query = query;
        this.page = page == null ? 1 : page;
    }

    public String getQuery() { return query; }
    public Integer getPage() { return page; }
}
`````````

Trong ví dụ này, cả missing page và explicit null page đều được chuẩn hóa thành 1. Đó là quyết định của constructor; nếu cần phân biệt hai trạng thái, constructor với tham số Integer đơn thuần không đủ thông tin.

Test default:

`````````java
@Test
void creatorAppliesPageDefaultForMissingAndNull() throws Exception {
    PageRequest missing = mapper.readValue(
        "{\"query\":\"jackson\"}",
        PageRequest.class
    );
    PageRequest explicitNull = mapper.readValue(
        "{\"query\":\"jackson\",\"page\":null}",
        PageRequest.class
    );

    assertEquals(1, missing.getPage());
    assertEquals(1, explicitNull.getPage());
}
`````````

### 7.1. Từ chối creator property bị thiếu

Có thể bật:

`````````java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .build();
`````````

Feature này áp dụng cho creator properties và có thể từ chối cả parameter vốn được xem là optional. Nếu chỉ một property cần bắt buộc, có thể dùng required metadata/creator logic và test behavior trên Jackson version đang dùng. Không bật global feature mà chưa kiểm tra mọi creator DTO.

Test:

`````````java
@Test
void missingRequiredCreatorPropertyFails() {
    ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .build();

    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue("{}", RequiredCommand.class)
    );
}
`````````

### 7.2. Từ chối creator property null

Feature tương ứng:

`````````java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
`````````

Nó từ chối creator property được cấp explicit null. Nếu cần phân biệt missing và null, test riêng cả hai vì chúng có thể phát sinh hai exception path khác nhau.

### 7.3. JsonProperty.defaultValue không tự gán default trong mọi trường hợp

Thuộc tính defaultValue của JsonProperty chủ yếu là metadata cho introspection/schema hoặc framework tích hợp. Không nên giả định chỉ cần khai báo:

`````````java
@JsonProperty(defaultValue = "1")
private int page;
`````````

là Jackson Databind sẽ tự gán 1 khi property bị thiếu. Hãy đặt default trong field initializer, creator, builder hoặc custom deserializer và viết test cho behavior đó.

## 8. Kiểm thử presence bằng JsonNode

Nếu cần xác định property có xuất hiện trong JSON hay không, JsonNode cung cấp cách kiểm tra rõ:

`````````java
JsonNode root = mapper.readTree(json);

JsonNode nickname = root.get("nickname");
`````````

Các trường hợp:

| JSON | root.get("nickname") | has("nickname") | hasNonNull("nickname") |
|---|---|---:|---:|
| {} | Java null reference | false | false |
| {"nickname":null} | NullNode | true | false |
| {"nickname":""} | TextNode rỗng | true | true |
| {"nickname":"An"} | TextNode có nội dung | true | true |

Test:

`````````java
@Test
void treeModelDistinguishesMissingNullAndEmpty() throws Exception {
    JsonNode missing = mapper.readTree("{}");
    JsonNode explicitNull = mapper.readTree("{\"nickname\":null}");
    JsonNode empty = mapper.readTree("{\"nickname\":\"\"}");

    assertFalse(missing.has("nickname"));
    assertNull(missing.get("nickname"));

    assertTrue(explicitNull.has("nickname"));
    assertTrue(explicitNull.get("nickname").isNull());

    assertTrue(empty.has("nickname"));
    assertTrue(empty.get("nickname").isTextual());
    assertEquals("", empty.get("nickname").textValue());
}
`````````

hasNonNull trả false cho cả missing và explicit null, vì vậy không dùng riêng method đó nếu cần phân biệt hai trạng thái. path("nickname") trả MissingNode khi property không tồn tại, còn get trả Java null reference; đây là hai API khác nhau.

### 8.1. Kiểm tra empty object và empty array trong tree

`````````java
JsonNode objectNode = mapper.readTree("{\"address\":{}}");
JsonNode arrayNode = mapper.readTree("{\"tags\":[]}");

assertTrue(objectNode.get("address").isObject());
assertEquals(0, objectNode.get("address").size());

assertTrue(arrayNode.get("tags").isArray());
assertEquals(0, arrayNode.get("tags").size());
`````````

Empty object và empty array đều có size bằng 0 nhưng khác node type. Test cả isObject() và isArray() để không vô tình chấp nhận sai cấu trúc.

## 9. Kiểm thử update semantics với readerForUpdating

Khi cập nhật một object hiện có, missing thường có nghĩa giữ giá trị cũ; explicit null có thể ghi đè hoặc bị skip theo policy; empty string/list có thể thay thế giá trị cũ bằng empty.

Ví dụ:

`````````java
public class UserProfile {
    private String nickname = "initial";
    private List<String> tags = new ArrayList<>(List.of("java"));

    public String getNickname() { return nickname; }
    public void setNickname(String nickname) { this.nickname = nickname; }

    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }
}
`````````

Test missing:

`````````java
@Test
void updatingWithMissingPropertyKeepsExistingValue() throws Exception {
    UserProfile existing = new UserProfile();

    mapper.readerForUpdating(existing)
        .readValue("{ }");

    assertEquals("initial", existing.getNickname());
    assertEquals(List.of("java"), existing.getTags());
}
`````````

Test explicit null:

`````````java
@Test
void updatingWithExplicitNullSetsReferencePropertyToNull() throws Exception {
    UserProfile existing = new UserProfile();

    mapper.readerForUpdating(existing)
        .readValue("{\"nickname\":null}");

    assertNull(existing.getNickname());
}
`````````

Test empty:

`````````java
@Test
void updatingWithEmptyValuesReplacesWithEmptyValues() throws Exception {
    UserProfile existing = new UserProfile();

    mapper.readerForUpdating(existing)
        .readValue("{\"nickname\":\"\",\"tags\":[]}");

    assertEquals("", existing.getNickname());
    assertTrue(existing.getTags().isEmpty());
}
`````````

Các ví dụ trên minh họa update cho bean/setter đơn giản. Collection update behavior có thể phụ thuộc property type, setter/field access và merge configuration. readerForUpdating không phải một deep merge tổng quát. Nếu cần append, merge theo ID hoặc giữ phần tử cũ khi thiếu, viết logic update domain tường minh và test semantics riêng.

### 9.1. Nulls.SKIP khi update

Nếu setter có JsonSetter(nulls = Nulls.SKIP), explicit null có thể giữ giá trị cũ khi dùng readerForUpdating. Test phải tạo một instance đã có giá trị và xác nhận:

- Missing giữ giá trị.
- Explicit null cũng giữ giá trị vì SKIP.
- Empty string thay bằng chuỗi rỗng.

Ba input này có thể tạo cùng kết quả cho hai trường hợp đầu nhưng nguyên nhân khác nhau. Nếu cần audit xem client đã gửi field nào, phải lưu presence metadata.

## 10. Kiểm thử serialize và JsonInclude

JsonInclude kiểm soát property khi serialize. Nó không tự đặt default khi deserialize:

`````````java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class PublicProfile {
    private String nickname;
    private String city;

    // Getters and setters
}
`````````

Test:

`````````java
@Test
void nonNullOmitsNullPropertiesDuringSerialization() throws Exception {
    PublicProfile profile = new PublicProfile();
    profile.setNickname(null);
    profile.setCity("Da Nang");

    JsonNode json = mapper.readTree(mapper.writeValueAsBytes(profile));

    assertFalse(json.has("nickname"));
    assertEquals("Da Nang", json.get("city").asText());
}
`````````

Với NON_EMPTY, empty string và empty collection cũng có thể bị bỏ khỏi output theo kiểu property:

`````````java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class SearchResponse {
    private String message = "";
    private List<String> results = new ArrayList<>();

    // Getters and setters
}
`````````

Test cần xác nhận output không có message/results khi empty theo policy. Không kết luận rằng input thiếu hai field này sẽ được gán default bởi NON_EMPTY; inclusion chỉ điều khiển serialization.

### 10.1. Round-trip không nhất thiết giữ nguyên trạng thái ban đầu

Ví dụ:

1. Object có nickname null.
2. Serializer dùng NON_NULL nên bỏ property.
3. Deserialize JSON đó vào bean có initializer nickname = "Guest".
4. Kết quả có nickname "Guest", không còn là null.

Điều này không phải lỗi parser; serializer đã chủ động loại thông tin null khỏi representation. Nếu round-trip phải giữ null, không dùng inclusion policy loại null cho contract đó, hoặc dùng representation khác để biểu diễn trạng thái.

Test round-trip nên kiểm tra semantics cần giữ, không chỉ gọi serialize rồi deserialize và so sánh equals một cách máy móc.

## 11. Kiểm thử default cho nested object

Nested object có thể thiếu, null hoặc empty:

`````````java
public class AddressRequest {
    private String city = "unknown";

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public class CustomerRequest {
    private AddressRequest address = new AddressRequest();

    public AddressRequest getAddress() { return address; }
    public void setAddress(AddressRequest address) {
        this.address = address;
    }
}
`````````

Các input:

`````````json
{}
`````````

Giữ AddressRequest initializer đã tạo.

`````````json
{"address":null}
`````````

Explicit null có thể thay nested object bằng null theo policy mặc định.

`````````json
{"address":{}}
`````````

Jackson tạo AddressRequest mới; city có thể nhận initializer "unknown".

Test:

`````````java
@Test
void nestedMissingNullAndEmptyObjectAreDifferent() throws Exception {
    CustomerRequest missing =
        mapper.readValue("{}", CustomerRequest.class);
    CustomerRequest nil =
        mapper.readValue("{\"address\":null}", CustomerRequest.class);
    CustomerRequest empty =
        mapper.readValue("{\"address\":{}}", CustomerRequest.class);

    assertNotNull(missing.getAddress());
    assertEquals("unknown", missing.getAddress().getCity());

    assertNull(nil.getAddress());

    assertNotNull(empty.getAddress());
    assertEquals("unknown", empty.getAddress().getCity());
}
`````````

Missing giữ instance initializer; empty object tạo instance khác nhưng có cùng default field. Nếu identity của nested object quan trọng, test thêm assertNotSame hoặc assertSame theo contract.

## 12. Kiểm thử với JUnit 5 parameterized tests

Khi nhiều input có cùng dạng kiểm tra, parameterized test giúp gom các case mà vẫn thể hiện rõ từng trạng thái:

`````````java
@ParameterizedTest
@CsvSource({
    "'{\"nickname\":\"\"}', ''",
    "'{\"nickname\":\"An\"}', 'An'"
})
void readsStringValues(String json, String expected) throws Exception {
    ProfileRequest request = mapper.readValue(json, ProfileRequest.class);
    assertEquals(expected, request.getNickname());
}
`````````

Với case missing/null/empty có kết quả khác nhau, có thể dùng MethodSource để truyền cả JSON và expected behavior:

`````````java
static Stream<Arguments> nicknameCases() {
    return Stream.of(
        Arguments.of("{}", null, false),
        Arguments.of("{\"nickname\":null}", null, true),
        Arguments.of("{\"nickname\":\"\"}", "", true),
        Arguments.of("{\"nickname\":\"An\"}", "An", true)
    );
}

@ParameterizedTest
@MethodSource("nicknameCases")
void checksNicknameBinding(
        String json,
        String expectedValue,
        boolean expectedSetterCall) throws Exception {

    ProfileRequest request = mapper.readValue(json, ProfileRequest.class);

    assertEquals(expectedValue, request.getNickname());
    assertEquals(expectedSetterCall, request.isNicknameSetterCalled());
}
`````````

Parameterized tests phù hợp cho ma trận input, nhưng không nên nhồi nhiều semantics khác nhau vào một test khó đọc. Giữ tên method mô tả điều đang được xác nhận.

## 13. Kiểm thử lỗi mapping và validation

Jackson mapping error và Bean Validation error là hai loại lỗi khác nhau.

Ví dụ JSON có kiểu sai:

`````````json
{"page":"first"}
`````````

Nếu page là Integer và coercion không chấp nhận input đó, Jackson báo lỗi binding trước khi DTO được tạo đầy đủ.

Ngược lại:

`````````json
{"page":-1}
`````````

Có thể bind thành Integer thành công, sau đó Bean Validation hoặc domain validation mới từ chối giá trị âm.

Test mapping:

`````````java
assertThrows(JsonMappingException.class, () ->
    mapper.readValue("{\"page\":\"first\"}", SearchRequest.class)
);
`````````

Test Bean Validation:

`````````java
Set<ConstraintViolation<SearchRequest>> violations =
    validator.validate(request);

assertTrue(violations.stream()
    .anyMatch(v -> v.getPropertyPath().toString().equals("page")));
`````````

Không bắt mọi exception rồi chỉ assert rằng có lỗi. Nếu test cần kiểm tra mapping, assert loại exception Jackson phù hợp; nếu test validation, assert constraint/property cụ thể.

## 14. Kiểm thử unknown property và duplicate property

Unknown property:

`````````java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();

assertThrows(JsonMappingException.class, () ->
    strictMapper.readValue(
        "{\"nickname\":\"An\",\"unexpected\":true}",
        ProfileRequest.class
    )
);
`````````

Nếu DTO được đánh dấu ignore unknown, viết test xác nhận field lạ bị bỏ qua theo contract. Không để behavior phụ thuộc một cấu hình mapper không được kiểm soát.

Duplicate property:

`````````java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();
ObjectMapper duplicateStrictMapper = new ObjectMapper(factory);

assertThrows(JsonProcessingException.class, () ->
    duplicateStrictMapper.readValue(
        "{\"nickname\":\"An\",\"nickname\":null}",
        ProfileRequest.class
    )
);
`````````

Test này xác nhận parser từ chối property lặp trước khi giá trị thứ hai âm thầm ghi đè giá trị đầu. Nếu contract cho phép duplicate (thường không nên cho command API), phải định nghĩa chính sách rõ ràng.

## 15. Kiểm thử null cho array, map và phần tử lồng

Null có thể xuất hiện ở nhiều cấp:

`````````json
{
  "tags": null,
  "metadata": {},
  "attributes": {
    "nickname": null
  },
  "items": [
    null,
    {"name": "A"}
  ]
}
`````````

Test riêng:

- Property collection là null.
- Collection rỗng.
- Phần tử null trong collection.
- Map rỗng.
- Map entry có value null.
- Nested object null.
- Nested object rỗng.
- Nested property null.

Nếu chỉ test property null ở root, các lỗi content null hoặc nested null có thể không được phát hiện. Dùng contentNulls khi cần policy cho phần tử; dùng validation/domain constructor để kiểm tra collection rỗng hoặc quan hệ giữa các phần tử.

## 16. Test helper để giảm lặp

Một helper nhỏ có thể giúp test đọc JSON gọn hơn:

`````````java
private <T> T read(String json, Class<T> type) throws IOException {
    return mapper.readValue(json, type);
}
`````````

Hoặc helper kiểm tra lỗi:

`````````java
private void assertMappingFailure(String json, Class<?> type) {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(json, type)
    );
}
`````````

Không tạo helper quá tổng quát che giấu input và expected result. Với test về null/missing, chính chuỗi JSON là một phần quan trọng của contract; nên giữ nó nhìn thấy được trong test.

## 17. Các lỗi thường gặp khi viết test

| Triệu chứng | Nguyên nhân | Cách kiểm tra đúng |
|---|---|---|
| Test missing và null cùng pass nhưng contract sai | Chỉ assert getter cuối cùng | Theo dõi setter/presence hoặc kiểm tra JsonNode. |
| Default không được kiểm tra | Chỉ test JSON có đủ mọi field | Test {} và từng property bị thiếu. |
| Primitive null biến thành 0/false ngoài ý muốn | Không bật FAIL_ON_NULL_FOR_PRIMITIVES | Dùng wrapper hoặc bật feature và test explicit null. |
| JsonInclude bị hiểu là default input | Nhầm serialize policy với deserialize policy | Test serialization và deserialization độc lập. |
| Nulls.SKIP được xem như missing detection | SKIP chỉ bỏ qua gán null | Dùng presence flag nếu cần biết field đã gửi. |
| Empty string bị xem là null | Coercion/custom deserializer/validation chuẩn hóa | Test empty, whitespace và null riêng. |
| Array null và array có null item bị gộp | Chỉ test null ở property level | Test nulls và contentNulls riêng. |
| Empty object bị xem như null | Chỉ assert nested field thay vì nested instance | Assert object có mặt và default field. |
| Creator default không hoạt động như mong muốn | Dựa vào JsonProperty.defaultValue | Đặt default trong constructor/factory và test. |
| Update vô tình xóa field | Dùng null/missing không đúng semantics | Test readerForUpdating với cả missing, null và empty. |
| Round-trip làm mất null | NON_NULL hoặc NON_EMPTY loại property khi ghi | Kiểm tra JSON trung gian và inclusion policy. |
| Test phụ thuộc mapper khác production | Tạo mapper test với cấu hình không tương ứng | Dùng production mapper hoặc factory chung. |

## 18. Ma trận test tối thiểu cho một DTO

Với mỗi property, lập ma trận theo kiểu dữ liệu và contract:

| Kiểu property | Missing | Null | Empty | Giá trị hợp lệ | Giá trị sai |
|---|---|---|---|---|---|
| String | Default/required | SET/SKIP/FAIL | Chuỗi rỗng hoặc validation error | Text | Sai token type/length |
| Integer | Default/required | Null/FAIL | Không áp dụng | Trong range | String, decimal, overflow |
| Boolean | Default/required | Null/FAIL | Không áp dụng | true/false | Sai token type |
| List | Default/null | Null policy | [] | Có phần tử | Null content/quá nhiều phần tử |
| Map | Default/null | Null policy | {} | Entry hợp lệ | Value sai type/duplicate theo contract |
| Nested object | Default/null | Null policy | {} | Object hợp lệ | Sai structure |

Không cần mọi ô đều là một test độc lập nếu nhiều case có cùng semantics, nhưng phải có test chứng minh mỗi trạng thái quan trọng. Với DTO dùng cho PATCH, presence và null thường cần được kiểm tra kỹ hơn DTO chỉ dùng cho create request.

## 19. Checklist thiết kế test

1. Liệt kê từng property và các trạng thái missing, null, empty, value.
2. Xác định default đến từ field initializer, constructor, builder hay application layer.
3. Test missing trên mutable bean để xác nhận setter không được gọi và initializer được giữ.
4. Test explicit null theo Nulls.SET, SKIP, FAIL hoặc AS_EMPTY.
5. Test primitive null với FAIL_ON_NULL_FOR_PRIMITIVES hoặc chuyển sang wrapper type nếu cần giữ null.
6. Test empty string, whitespace, empty array, empty map và empty object riêng.
7. Test content null trong collection/map, không chỉ null của property.
8. Test creator missing/null features và constructor defaults.
9. Dùng JsonNode để kiểm tra presence khi getter cuối không giữ được khác biệt.
10. Test readerForUpdating nếu DTO được dùng cho PATCH/partial update.
11. Test serialization inclusion riêng với deserialization default.
12. Test round-trip nếu contract yêu cầu giữ semantics qua cả hai chiều.
13. Test mapping error và Bean Validation error như hai tầng riêng.
14. Dùng đúng ObjectMapper production hoặc cấu hình test tương ứng.

Kiểm thử null, thiếu, rỗng và default là kiểm thử hợp đồng dữ liệu. Missing cho biết producer không cung cấp property; null là một giá trị được gửi; empty là một giá trị có mặt nhưng không chứa phần tử hoặc nội dung; default là quyết định của model hoặc ứng dụng khi dữ liệu không cung cấp giá trị. Khi test từng trạng thái bằng input riêng, quan sát cả giá trị lẫn presence và dùng đúng mapper production, các lỗi cập nhật, mất dữ liệu và default ngoài ý muốn sẽ dễ được phát hiện trước khi đi vào service hoặc database.
