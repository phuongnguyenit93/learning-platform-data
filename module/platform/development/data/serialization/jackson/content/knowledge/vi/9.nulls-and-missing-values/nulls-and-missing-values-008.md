# Kiểm tra ý nghĩa của giá trị mặc định theo kiểu và cấu hình

Khi Jackson đọc JSON, một thuộc tính có thể không xuất hiện, xuất hiện với giá trị null, hoặc xuất hiện với một giá trị rỗng như chuỗi rỗng, mảng rỗng hay object rỗng. Những trường hợp này có ý nghĩa khác nhau và có thể tạo ra kết quả Java khác nhau tùy kiểu thuộc tính, cách khởi tạo object và cấu hình Jackson.

Ví dụ, một request không gửi field retryCount có thể có nghĩa là dùng giá trị mặc định 3. Nếu request gửi retryCount bằng null, hợp đồng có thể yêu cầu từ chối, đặt về 0 hoặc giữ nguyên giá trị mặc định. Nếu request gửi retryCount bằng chuỗi rỗng, ứng dụng cần quyết định có chuyển đổi, coi như null hay báo lỗi.

Vì vậy, không nên chỉ nhìn giá trị Java sau khi deserialize rồi đoán input ban đầu. Hãy xác định rõ ba trạng thái **missing, null và empty**, sau đó quy định hành vi theo kiểu dữ liệu và cấu hình Jackson.

## 1. Phân biệt missing, null và empty

Ba trường hợp thường gặp:

| Trạng thái JSON | Ví dụ | Ý nghĩa |
|---|---|---|
| Missing | Không có field trong object | Người gửi không cung cấp thuộc tính |
| Explicit null | "name": null | Người gửi có cung cấp field nhưng giá trị rỗng theo JSON null |
| Empty value | "name": "", "items": [], "metadata": {} | Field có mặt với giá trị rỗng của kiểu tương ứng |

Ví dụ:

~~~json
{
  "id": 10,
  "nickname": null,
  "tags": [],
  "metadata": {}
}
~~~

Trong payload trên:

- id có giá trị.
- nickname có mặt nhưng giá trị là null.
- tags có mặt và là mảng rỗng.
- metadata có mặt và là object rỗng.
- Nếu field locale không xuất hiện, locale là missing.

Jackson có thể xử lý các trạng thái này khác nhau. Kết quả phụ thuộc vào cách object được tạo, kiểu field, annotation và feature đang bật.

### 1.1. Missing không đồng nghĩa với null

Khi một field không xuất hiện trong JSON, Jackson thường không gán giá trị cho property đó trong quá trình setter/field-based deserialization. Nếu Java field đã được khởi tạo sẵn, giá trị khởi tạo có thể được giữ lại.

Ngược lại, khi field xuất hiện với null, Jackson nhận được một giá trị đầu vào và có thể gọi setter hoặc gán null vào property. Giá trị khởi tạo trước đó có thể bị ghi đè.

Ví dụ:

~~~java
public class UserPreferences {

    private String locale = "vi";

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
~~~

Với JSON không có locale:

~~~json
{}
~~~

Nếu Jackson tạo object bằng constructor không tham số rồi bind property, locale vẫn là "vi" vì setter không được gọi.

Với JSON:

~~~json
{
  "locale": null
}
~~~

Setter có thể được gọi với null, làm locale trở thành null. Đây là lý do missing và explicit null phải được kiểm thử riêng.

### 1.2. Empty value cũng có nhiều dạng

Không có một giá trị empty duy nhất cho mọi kiểu:

- String rỗng: "".
- Collection rỗng: [].
- Map rỗng: {}.
- Mảng rỗng: [].
- Chuỗi chỉ chứa khoảng trắng: "   " — không đồng nghĩa với chuỗi rỗng.
- Số 0 và boolean false là giá trị hợp lệ, không phải JSON null.
- JSON object {} có mặt nhưng không chứa property.

Jackson có các quy tắc coercion để chuyển một số dạng input sang kiểu đích. Không nên mặc định rằng chuỗi rỗng sẽ luôn trở thành null hoặc giá trị mặc định của kiểu.

## 2. Giá trị mặc định theo kiểu Java

Trước khi xem cấu hình Jackson, cần hiểu giá trị mặc định của Java.

### 2.1. Primitive type

Field primitive chưa được gán giá trị sẽ nhận giá trị mặc định của Java:

| Kiểu primitive | Giá trị mặc định |
|---|---|
| byte | 0 |
| short | 0 |
| int | 0 |
| long | 0L |
| float | 0.0f |
| double | 0.0d |
| boolean | false |
| char | ký tự null, mã Unicode U+0000 |

Ví dụ:

~~~java
public class RetryPolicy {

    private int maxRetries;
    private boolean enabled;

    public int getMaxRetries() {
        return maxRetries;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

Nếu Jackson tạo object bằng constructor không tham số và JSON không có hai field trên, chúng giữ giá trị mặc định của Java: maxRetries là 0 và enabled là false.

Nhưng giá trị mặc định của Java không nhất thiết là giá trị mặc định nghiệp vụ. Ví dụ retry mặc định có thể là 3 lần, trong khi 0 có nghĩa là tắt retry. Hãy khai báo default nghiệp vụ một cách tường minh.

### 2.2. Reference type

Field thuộc kiểu tham chiếu chưa được gán sẽ nhận null:

~~~java
public class UserProfile {

    private Integer age;
    private String displayName;
    private List<String> roles;
}
~~~

Nếu object được tạo bằng constructor không tham số và JSON không có các field trên, giá trị ban đầu của chúng là null.

Các kiểu wrapper như Integer, Long, Boolean khác primitive:

| Primitive | Wrapper | Khả năng biểu diễn null |
|---|---|---|
| int | Integer | Integer có thể null |
| long | Long | Long có thể null |
| boolean | Boolean | Boolean có thể null |
| double | Double | Double có thể null |

Nếu cần phân biệt "chưa được cung cấp" với giá trị 0 hoặc false, wrapper thường phù hợp hơn primitive. Tuy nhiên, wrapper chỉ giữ được null; sau khi deserialize, nó vẫn có thể không phân biệt được field bị thiếu với field được gửi rõ ràng là null nếu cả hai cùng dẫn đến null.

### 2.3. Giá trị khởi tạo của field

Java cho phép khai báo giá trị khởi tạo:

~~~java
public class SearchOptions {

    private int page = 0;
    private int size = 20;
    private boolean includeArchived = false;
    private String language = "vi";
    private List<String> tags = new ArrayList<>();
}
~~~

Với constructor không tham số và setter/field-based binding:

- Field bị thiếu thường giữ giá trị khởi tạo.
- Field có mặt với null có thể ghi đè giá trị khởi tạo, tùy kiểu và cấu hình.
- Field có giá trị được gán theo input.

Ví dụ:

| JSON | page | size | language |
|---|---:|---:|---|
| {} | 0 | 20 | vi |
| {"size": 50} | 0 | 50 | vi |
| {"size": null} | 0 | 0 hoặc lỗi theo kiểu/cấu hình | vi |
| {"language": null} | 0 | 20 | null |
| {"language": ""} | 0 | 20 | chuỗi rỗng nếu không có coercion khác |

Đối với primitive int, JSON null mặc định thường được chuyển thành giá trị mặc định 0 nếu FAIL_ON_NULL_FOR_PRIMITIVES không bật. Với Integer, null có thể được gán trực tiếp.

## 3. Ảnh hưởng của cách tạo object

Cùng một JSON có thể tạo kết quả khác nhau nếu Jackson sử dụng constructor không tham số, constructor có tham số hoặc builder.

### 3.1. Constructor không tham số và setter

~~~java
public class UserSettings {

    private String language = "vi";
    private int pageSize = 20;

    public UserSettings() {
    }

    public String getLanguage() {
        return language;
    }

    public void setLanguage(String language) {
        this.language = language;
    }

    public int getPageSize() {
        return pageSize;
    }

    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Khi JSON không có language hoặc pageSize, giá trị khởi tạo được giữ lại vì Jackson không cần gọi setter cho property bị thiếu.

Nếu JSON gửi language: null, setter được gọi với null và giá trị "vi" bị thay thế. Nếu pageSize là primitive int và JSON gửi null, hành vi phụ thuộc FAIL_ON_NULL_FOR_PRIMITIVES.

Đây là cách đơn giản để cung cấp default cho field bị thiếu, nhưng cần quyết định riêng cho explicit null.

### 3.2. Property-based creator

Với constructor có tham số được đánh dấu @JsonCreator, Jackson phải thu thập giá trị các creator property rồi gọi constructor.

~~~java
public class UserSettings {

    private final String language;
    private final int pageSize;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public UserSettings(
        @JsonProperty("language") String language,
        @JsonProperty("pageSize") int pageSize
    ) {
        this.language = language;
        this.pageSize = pageSize;
    }
}
~~~

Nếu field bị thiếu, Jackson phải cung cấp một giá trị cho tham số creator. Tham số reference có thể nhận null; tham số primitive có thể nhận giá trị mặc định nếu không có feature strict tương ứng. Giá trị khởi tạo field không tự động thay thế giá trị tham số constructor.

Nếu muốn default nghiệp vụ:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public UserSettings(
    @JsonProperty("language") String language,
    @JsonProperty("pageSize") Integer pageSize
) {
    this.language = language == null ? "vi" : language;
    this.pageSize = pageSize == null ? 20 : pageSize;
}
~~~

Cách trên gộp missing và explicit null thành cùng một chính sách: cả hai đều dùng default. Nếu hợp đồng cần phân biệt hai trạng thái, phải giữ thông tin presence riêng, chẳng hạn đọc JsonNode hoặc dùng một kiểu wrapper biểu diễn trạng thái.

### 3.3. Builder

Builder thường giữ default trong field của builder:

~~~java
@JsonDeserialize(builder = SearchOptions.Builder.class)
public class SearchOptions {

    private final int page;
    private final int size;
    private final String language;

    private SearchOptions(Builder builder) {
        this.page = builder.page;
        this.size = builder.size;
        this.language = builder.language;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private int page = 0;
        private int size = 20;
        private String language = "vi";

        public Builder page(int page) {
            this.page = page;
            return this;
        }

        public Builder size(int size) {
            this.size = size;
            return this;
        }

        public Builder language(String language) {
            this.language = language;
            return this;
        }

        public SearchOptions build() {
            return new SearchOptions(this);
        }
    }
}
~~~

Nếu property bị thiếu, method builder tương ứng không được gọi và default của builder được giữ lại. Nếu property có mặt với null, method có thể được gọi với null và ghi đè default. Có thể điều khiển explicit null bằng @JsonSetter trên phương thức builder.

Builder cần được thiết kế cùng chính sách missing/null; không nên nghĩ rằng chỉ vì có default trong builder thì mọi trường hợp null đều giữ default.

## 4. FAIL_ON_NULL_FOR_PRIMITIVES

Jackson 2.x có DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES. Feature này điều khiển việc xử lý JSON null khi target là kiểu primitive.

Mặc định feature này tắt. Vì vậy, JSON null có thể được chuyển thành giá trị mặc định của primitive, ví dụ int thành 0 và boolean thành false.

Ví dụ:

~~~java
public record PaymentRequest(int amount, boolean confirmed) {}
~~~

JSON:

~~~json
{
  "amount": null,
  "confirmed": null
}
~~~

Với cấu hình mặc định, Jackson có thể chuyển null thành 0 và false. Nếu đây là dữ liệu bắt buộc, kết quả này có thể che giấu lỗi từ client.

Bật feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Khi đó, explicit null cho primitive sẽ gây lỗi mapping thay vì âm thầm trở thành 0 hoặc false.

Cần phân biệt:

- Field bị thiếu trong POJO dùng constructor không tham số có thể giữ giá trị field initializer hoặc Java default vì không có assignment.
- Field explicit null cho primitive chịu ảnh hưởng của FAIL_ON_NULL_FOR_PRIMITIVES.
- Creator parameter bị thiếu còn liên quan đến FAIL_ON_MISSING_CREATOR_PROPERTIES.

Không nên bật feature rồi giả định nó cũng bắt được mọi field bị thiếu. Hai trạng thái cần test riêng.

## 5. FAIL_ON_MISSING_CREATOR_PROPERTIES và FAIL_ON_NULL_CREATOR_PROPERTIES

Khi dùng constructor/factory property-based, Jackson có hai feature quan trọng để kiểm soát creator parameter.

| Feature | Ý nghĩa |
|---|---|
| FAIL_ON_MISSING_CREATOR_PROPERTIES | Báo lỗi khi creator property bị thiếu |
| FAIL_ON_NULL_CREATOR_PROPERTIES | Báo lỗi khi creator property có giá trị null |

Ví dụ:

~~~java
public record CreateUserRequest(
    String username,
    String email
) {
    @JsonCreator
    public CreateUserRequest(
        @JsonProperty("username") String username,
        @JsonProperty("email") String email
    ) {
        this.username = username;
        this.email = email;
    }
}
~~~

Có thể cấu hình:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
~~~

Với cấu hình này:

- JSON thiếu username hoặc email sẽ bị từ chối.
- JSON có username: null hoặc email: null cũng bị từ chối.

Đây là chính sách strict cho creator property. Nó phù hợp với request tạo dữ liệu mà các field bắt buộc phải có giá trị.

Tuy nhiên, bật feature ở mapper dùng chung có thể ảnh hưởng các creator khác. Nếu một API có field tùy chọn, hãy dùng mapper/reader phù hợp hoặc thiết kế DTO và creator thể hiện rõ optionality.

### 5.1. @JsonProperty(required = true)

Có thể đánh dấu creator property bắt buộc:

~~~java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public CreateUserRequest(
    @JsonProperty(value = "username", required = true) String username,
    @JsonProperty(value = "email", required = true) String email
) {
    this.username = username;
    this.email = email;
}
~~~

Thuộc tính required chủ yếu có ý nghĩa trong metadata và quá trình xử lý property-based creator. Không nên xem nó là cơ chế thay thế cho toàn bộ validation. Hãy kiểm tra hành vi với phiên bản Jackson và cấu hình thực tế, đồng thời vẫn kiểm tra giá trị rỗng, format và quy tắc nghiệp vụ.

## 6. @JsonSetter và Nulls: xử lý explicit null theo từng property

@JsonSetter cho phép định nghĩa cách Jackson xử lý null cho một property. Thuộc tính nulls nhận các giá trị của enum Nulls.

| Nulls | Hành vi |
|---|---|
| SET | Gán null theo mặc định |
| SKIP | Bỏ qua assignment khi input là null |
| FAIL | Ném lỗi khi input là null |
| AS_EMPTY | Dùng giá trị empty do deserializer cung cấp |
| DEFAULT | Dùng chính sách mặc định của Jackson/context |

### 6.1. SKIP: giữ giá trị khởi tạo khi JSON gửi null

~~~java
public class UserPreferences {

    private String language = "vi";

    @JsonSetter(value = "language", nulls = Nulls.SKIP)
    public void setLanguage(String language) {
        this.language = language;
    }

    public String getLanguage() {
        return language;
    }
}
~~~

Với JSON:

~~~json
{
  "language": null
}
~~~

Setter bị bỏ qua, vì vậy giá trị khởi tạo "vi" được giữ lại.

SKIP hữu ích khi null có nghĩa là "không cập nhật thuộc tính". Tuy nhiên, với API tạo mới, ý nghĩa này có thể khác với hợp đồng mong muốn. Hãy chỉ dùng khi semantics được định nghĩa rõ.

### 6.2. FAIL: từ chối null

~~~java
public class CreateUserRequest {

    private String email;

    @JsonSetter(value = "email", nulls = Nulls.FAIL)
    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Nếu JSON có email: null, Jackson báo lỗi thay vì gán null. Nếu email bị thiếu hoàn toàn, setter không được gọi; điều đó không tự động có nghĩa missing cũng bị từ chối. Muốn bắt missing, cần validation sau binding hoặc cơ chế required phù hợp.

### 6.3. AS_EMPTY: chuyển null thành giá trị empty

~~~java
public class SearchRequest {

    private List<String> tags;

    @JsonSetter(value = "tags", nulls = Nulls.AS_EMPTY)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Khi tags nhận null, Jackson yêu cầu deserializer của kiểu đích cung cấp empty value. Với collection, kết quả thường là collection rỗng.

AS_EMPTY không đồng nghĩa với default nghiệp vụ tùy ý. Nó dùng định nghĩa empty value của deserializer. Nếu cần mặc định cụ thể như pageSize = 20 hoặc language = "vi", hãy đặt default trong constructor, builder hoặc setter.

### 6.4. DEFAULT và chính sách toàn cục

Nulls.DEFAULT cho phép Jackson dùng cách xử lý mặc định được cấu hình ở cấp cao hơn hoặc theo hành vi mặc định của deserializer.

Có thể cấu hình default setter null policy ở cấp ObjectMapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .defaultSetterInfo(JsonSetter.Value.forValueNulls(Nulls.SKIP))
    .build();
~~~

Cấu hình này ảnh hưởng rộng đến property binding. Một field cần explicit null có ý nghĩa riêng có thể bị thay đổi hành vi nếu không có annotation override phù hợp.

Vì vậy, hãy ưu tiên policy toàn cục chỉ khi ứng dụng thực sự có quy ước chung. Các ngoại lệ nên được ghi rõ ở DTO/property và có test.

## 7. Null trong phần tử collection và value của Map

Null của chính property khác null nằm bên trong collection hoặc Map.

Ví dụ:

~~~json
{
  "tags": ["java", null, "jackson"],
  "attributes": {
    "color": "blue",
    "note": null
  }
}
~~~

tags không null; nó là một List có một phần tử null. attributes không null; nó là Map có một value null.

@JsonSetter hỗ trợ contentNulls để điều khiển null bên trong container:

~~~java
public class CatalogItem {

    private List<String> tags = new ArrayList<>();

    @JsonSetter(
        value = "tags",
        nulls = Nulls.AS_EMPTY,
        contentNulls = Nulls.SKIP
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Trong ví dụ:

- Nếu toàn bộ tags là null, AS_EMPTY yêu cầu giá trị empty của List.
- Nếu một phần tử bên trong tags là null, contentNulls = SKIP bỏ qua phần tử null khi deserializing.

Có thể dùng contentNulls = FAIL nếu mọi phần tử bắt buộc phải có giá trị:

~~~java
@JsonSetter(
    value = "tags",
    nulls = Nulls.AS_EMPTY,
    contentNulls = Nulls.FAIL
)
public void setTags(List<String> tags) {
    this.tags = tags;
}
~~~

Đối với Map, contentNulls điều khiển value của Map. Nếu cần kiểm soát key, hãy xem xét key deserializer; key không phải cùng khái niệm với content value.

## 8. Giá trị mặc định cho constructor và factory method

Khi Jackson dùng property-based creator, field initializer của object không tự động giải quyết mọi trường hợp missing/null vì giá trị được truyền trực tiếp vào tham số constructor.

Có thể đặt default trong creator:

~~~java
public record SearchRequest(String keyword, Integer pageSize) {

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public SearchRequest(
        @JsonProperty("keyword") String keyword,
        @JsonProperty("pageSize") Integer pageSize
    ) {
        this.keyword = keyword;
        this.pageSize = pageSize == null ? 20 : pageSize;
    }
}
~~~

Ví dụ này coi missing và null của pageSize là cùng một trạng thái default 20. Nếu cần phân biệt, phải đọc presence riêng.

Với factory method, nguyên tắc tương tự:

~~~java
public static SearchRequest fromJson(
    String keyword,
    Integer pageSize
) {
    int effectivePageSize = pageSize == null ? 20 : pageSize;
    return new SearchRequest(keyword, effectivePageSize);
}
~~~

Hãy giữ logic default đơn giản và có tính xác định. Không gọi database hoặc dịch vụ ngoài trong constructor/factory chỉ để tìm giá trị mặc định; những việc đó thuộc tầng nghiệp vụ.

## 9. Optional có giải quyết được missing và null không?

Optional<T> biểu diễn một giá trị có thể không tồn tại, nhưng không phải lúc nào cũng giữ được cả ba trạng thái:

- Field không có trong JSON.
- Field có mặt với null.
- Field có mặt với giá trị cụ thể.

Khi dùng Jackson 2, Jdk8Module hỗ trợ Optional. Tuy nhiên, cách xử lý property bị thiếu còn phụ thuộc đường binding: setter/field, creator hoặc builder. Trong một số trường hợp, missing không gọi setter nên field initializer vẫn được giữ; trong creator, tham số missing được xử lý như giá trị không có để chuyển cho creator. Vì vậy, không nên giả định Optional tự động bảo toàn sự khác biệt giữa missing và explicit null.

Nếu API PATCH cần semantics:

| Input | Ý nghĩa cập nhật |
|---|---|
| Field bị thiếu | Giữ giá trị hiện tại |
| Field có null | Xóa giá trị hiện tại |
| Field có value | Gán giá trị mới |

thì Optional<T> đơn thuần thường không đủ để thể hiện ba trạng thái. Có thể dùng JsonNode để kiểm tra has(field) và isNull(), hoặc dùng một kiểu presence wrapper chuyên biệt.

Ví dụ với JsonNode:

~~~java
JsonNode patch = mapper.readTree(json);

if (!patch.has("displayName")) {
    // Không cập nhật displayName.
} else if (patch.get("displayName").isNull()) {
    // Xóa displayName theo semantics PATCH.
} else {
    String value = patch.get("displayName").asText();
    // Cập nhật displayName.
}
~~~

Đây là cách thể hiện rõ sự khác nhau giữa missing, null và value. Với API lớn, có thể đóng gói logic này thành một kiểu dữ liệu PatchField<T> hoặc dùng thư viện presence wrapper đã được dự án chấp nhận.

## 10. Chuỗi rỗng và coercion

Chuỗi rỗng không phải JSON null:

~~~json
{
  "age": "",
  "name": ""
}
~~~

Khi target là String, chuỗi rỗng thường được giữ là "". Khi target là số hoặc kiểu khác, Jackson có thể áp dụng coercion tùy logical type và cấu hình.

Jackson 2.12+ có CoercionConfig để kiểm soát các dạng input như EmptyString, EmptyArray và EmptyObject.

Ví dụ từ chối chuỗi rỗng khi target là kiểu số nguyên:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

Có thể chọn hành vi khác như AsNull, AsEmpty hoặc TryConvert tùy logical type và hợp đồng. Không nên dùng một chính sách coercion rộng cho mọi kiểu dữ liệu mà không test.

Phân biệt:

- Empty string: chuỗi có độ dài 0.
- Whitespace string: chuỗi có dấu cách/tab, cần chuẩn hóa riêng nếu hợp đồng yêu cầu.
- Null: giá trị JSON null.
- Missing: không có property.
- Empty collection/object: container có mặt nhưng không có phần tử/property.

## 11. @JsonProperty(defaultValue) không tự động đặt default cho databind

@JsonProperty có thuộc tính defaultValue để mô tả giá trị mặc định trong metadata. Tuy nhiên, Jackson Databind không tự dùng giá trị này để gán default cho property khi deserialize theo cách mà nhiều người dễ tưởng tượng.

Ví dụ:

~~~java
public class SearchRequest {

    @JsonProperty(value = "pageSize", defaultValue = "20")
    private Integer pageSize;
}
~~~

Không nên kỳ vọng JSON thiếu pageSize sẽ tự động nhận 20 chỉ nhờ defaultValue. Hãy đặt giá trị mặc định bằng field initializer, constructor, builder hoặc logic mapping phù hợp.

DefaultValue có thể hữu ích cho công cụ introspection hoặc sinh schema/documentation, nhưng không thay thế logic default thực thi.

Tương tự, @JsonInclude(Include.NON_NULL) chủ yếu điều khiển serialization: field null có được đưa vào JSON output hay không. Nó không quy định cách Jackson xử lý field null khi đọc JSON.

## 12. Thiết kế chính sách theo từng loại DTO

Có thể chia DTO theo mục đích:

~~~text
API request DTO
  -> yêu cầu input, validation, missing/null rõ ràng

API response DTO
  -> chỉ chứa field được phép công bố, format ổn định

Partner DTO
  -> phản ánh chính xác hợp đồng đối tác

Persistence document
  -> phục vụ lưu/khôi phục dữ liệu nội bộ

Patch DTO / presence model
  -> giữ được khác biệt giữa missing, null và value
~~~

Không nên tái sử dụng một DTO cho mọi ranh giới nếu semantics khác nhau. Ví dụ, field null trong request tạo mới có thể bị từ chối; field null trong PATCH có thể có nghĩa xóa dữ liệu; field null trong response có thể bị bỏ khỏi JSON. Ba trường hợp này không nên bị ép vào một cấu hình duy nhất.

## 13. Kiểm thử default theo kiểu và cấu hình

Nên viết test theo ma trận input thay vì chỉ test một payload thông thường.

Ví dụ class:

~~~java
public class RetrySettings {

    private int maxRetries = 3;
    private Integer delaySeconds = 5;
    private String strategy = "fixed";

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }

    public Integer getDelaySeconds() {
        return delaySeconds;
    }

    public void setDelaySeconds(Integer delaySeconds) {
        this.delaySeconds = delaySeconds;
    }

    public String getStrategy() {
        return strategy;
    }

    public void setStrategy(String strategy) {
        this.strategy = strategy;
    }
}
~~~

Test missing:

~~~java
RetrySettings settings = mapper.readValue("{}", RetrySettings.class);

assertEquals(3, settings.getMaxRetries());
assertEquals(5, settings.getDelaySeconds());
assertEquals("fixed", settings.getStrategy());
~~~

Test explicit null:

~~~java
RetrySettings settings = mapper.readValue(
    """
    {
      "maxRetries": null,
      "delaySeconds": null,
      "strategy": null
    }
    """,
    RetrySettings.class
);
~~~

Kết quả cần được xác định theo cấu hình:

- maxRetries là primitive int: mặc định null có thể thành 0; strict primitive mode sẽ báo lỗi.
- delaySeconds là Integer: null được gán trực tiếp nếu không có null policy khác.
- strategy là String: null được gán trực tiếp nếu không có null policy khác.

Nếu strategy có @JsonSetter(nulls = Nulls.SKIP), explicit null sẽ giữ "fixed". Nếu nulls = Nulls.FAIL, deserialize sẽ thất bại. Test nên chứng minh đúng hành vi đã chọn.

Ma trận kiểm thử nên có ít nhất:

| Kiểu | Missing | Explicit null | Empty |
|---|---|---|---|
| int | Field initializer/0 hoặc creator policy | 0 hoặc lỗi theo feature | Coercion theo cấu hình |
| Integer | Field initializer/null hoặc creator policy | null hoặc lỗi theo null policy | Coercion theo cấu hình |
| String | Field initializer/null | null, skip, fail hoặc empty theo policy | "" hoặc coercion |
| List<T> | Field initializer/null hoặc creator policy | null, empty hoặc fail | [] là collection rỗng |
| Map<K,V> | Field initializer/null hoặc creator policy | null, empty hoặc fail | {} là map rỗng |
| Optional<T> | Phụ thuộc đường binding/module | Thường thành empty theo module, cần test | Không đồng nghĩa với missing |
| Creator parameter | Feature missing creator | Feature null creator | Coercion theo kiểu đích |

## 14. Quy trình quyết định giá trị mặc định

~~~text
Nhận JSON
   |
   v
Property có xuất hiện?
   |
   +-- Không --> Missing policy
   |
   +-- Có
        |
        v
   Giá trị là null?
        |
        +-- Có --> Null policy
        |
        +-- Không
             |
             v
        Giá trị empty?
             |
             +-- Có --> Empty/coercion policy
             |
             +-- Không --> Parse và validate value
~~~

Sau khi xác định trạng thái input, hãy xét cách tạo object:

- Constructor không tham số: missing thường không gọi setter, nên field initializer có thể giữ nguyên.
- Property-based creator: missing/null được xử lý thành tham số đầu vào theo feature và kiểu tham số.
- Builder: missing có thể giữ builder default; explicit null có thể gọi setter builder với null.
- Record: canonical constructor nhận các component; default cần được xử lý trong constructor/creator nếu hợp đồng yêu cầu.

## 15. Nguyên tắc thiết kế nên giữ

1. Không coi missing, null và empty là một trạng thái.
2. Chọn primitive khi null không có ý nghĩa; chọn wrapper khi cần biểu diễn null.
3. Đặt default nghiệp vụ tường minh, không dựa vào 0/false mặc định của Java nếu chúng có ý nghĩa khác.
4. Dùng @JsonSetter(nulls = ...) cho explicit null ở property phù hợp.
5. Dùng contentNulls để kiểm soát null bên trong List/Map.
6. Dùng FAIL_ON_NULL_FOR_PRIMITIVES khi null cho primitive phải bị từ chối.
7. Dùng FAIL_ON_MISSING_CREATOR_PROPERTIES và FAIL_ON_NULL_CREATOR_PROPERTIES cho creator strict khi hợp đồng yêu cầu.
8. Không kỳ vọng @JsonProperty(defaultValue) tự gán default khi deserialize.
9. Không dùng @JsonInclude để điều khiển input null; annotation này chủ yếu tác động output.
10. Nếu PATCH cần phân biệt missing/null/value, dùng presence model hoặc JsonNode.
11. Viết test riêng cho field missing, null, empty và giá trị sai kiểu.
12. Giữ chính sách theo DTO/hợp đồng, tránh một mapper permissive cho toàn bộ ứng dụng.

Khi hiểu ý nghĩa của giá trị mặc định theo kiểu và cấu hình, ứng dụng sẽ tránh được lỗi âm thầm như null biến thành 0, field thiếu bị hiểu nhầm là null, hoặc dữ liệu PATCH không thể xóa đúng cách. Hợp đồng JSON nên quyết định semantics trước; Jackson chỉ thực thi những semantics đó qua creator, annotation và cấu hình mapper.

