# Cấu hình hành vi setter đối với null bằng JsonSetter

Khi Jackson đọc JSON thành một Java object, một property có thể không xuất hiện trong input, có thể xuất hiện với giá trị `null`, hoặc có một giá trị cụ thể. Ba trường hợp này không đồng nghĩa với nhau. Đặc biệt, trong mô hình JavaBean, Jackson thường gọi setter khi property có mặt; nếu JSON chứa `null`, setter có thể nhận null và ghi đè giá trị đã được khởi tạo trong constructor hoặc field initializer.

Annotation `@JsonSetter` cho phép điều khiển cách Jackson xử lý giá trị null khi deserialize. Hai thuộc tính quan trọng nhất là:

- `nulls`: chính sách cho giá trị null của chính property.
- `contentNulls`: chính sách cho phần tử null bên trong container như array, collection hoặc map.

Bằng cách chọn đúng chính sách, ứng dụng có thể từ chối null, bỏ qua setter, chuyển null thành giá trị rỗng hoặc dùng chính sách mặc định. Điều này đặc biệt quan trọng với API nhận request, dữ liệu cập nhật từng phần và các DTO có giá trị khởi tạo.

## 1. Phân biệt property bị thiếu và property có giá trị null

Xét DTO:

```java
public class Profile {
    private String nickname = "guest";

    public Profile() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Có ba input cần phân biệt:

**Trường hợp A — property bị thiếu:**

```json
{}
```

Jackson không đọc thấy property `nickname`, vì vậy setter không được gọi. Giá trị `guest` từ field initializer được giữ lại.

**Trường hợp B — property có mặt với null:**

```json
{
  "nickname": null
}
```

Với chính sách null mặc định thông thường, Jackson gọi `setNickname(null)`. Giá trị `guest` bị thay bằng null.

**Trường hợp C — property có giá trị:**

```json
{
  "nickname": "an"
}
```

Jackson gọi `setNickname("an")`; giá trị sau deserialize là `an`.

| Input | Setter có được gọi? | Kết quả với DTO trên |
|---|---|---|
| Không có key `nickname` | Không | `guest` |
| `"nickname": null` | Có, theo mặc định | `null` |
| `"nickname": "an"` | Có | `an` |

`@JsonSetter` điều khiển trường hợp property hiện diện nhưng có giá trị null. Nó không biến một property bị thiếu thành null và không tự tạo giá trị cho key không có trong JSON.

## 2. @JsonSetter và hai thuộc tính nulls/contentNulls

Trong Jackson 2.x, `@JsonSetter` thuộc package:

```java
com.fasterxml.jackson.annotation.JsonSetter
```

Các chính sách null qua `nulls` và `contentNulls` được hỗ trợ từ Jackson 2.9.

Có thể đặt annotation trên setter:

```java
public class Profile {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Hoặc đặt trên field khi class dùng field-based binding:

```java
public class Profile {
    @JsonSetter(nulls = Nulls.SKIP)
    private String nickname = "guest";
}
```

Với JavaBean, đặt trên setter thường làm rõ ý định xử lý input. Nếu một logical property có cả field, getter và setter, nên tránh đặt các chính sách mâu thuẫn trên nhiều accessor; hãy khai báo annotation tại vị trí đại diện rõ ràng cho quy tắc deserialize.

### 2.1. nulls: null của chính property

`nulls` điều khiển điều gì xảy ra khi giá trị JSON của property là `null`:

```java
@JsonSetter(nulls = Nulls.SKIP)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
```

Ở đây, Jackson bỏ qua việc gán khi input có `"nickname": null`. Setter không được gọi cho giá trị null đó.

### 2.2. contentNulls: null bên trong container

`contentNulls` áp dụng cho các phần tử null bên trong array, collection hoặc value của map. Nó không điều khiển null của chính container.

```java
public class Preferences {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Với input:

```json
{
  "tags": ["java", null, "jackson"]
}
```

Jackson bỏ qua phần tử null trong danh sách và setter nhận list chứa `java` và `jackson`.

Hai chính sách có thể kết hợp:

```java
@JsonSetter(
        nulls = Nulls.SKIP,
        contentNulls = Nulls.FAIL
)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Kết quả:

- Nếu `tags` là null, setter bị bỏ qua.
- Nếu `tags` là một array nhưng có phần tử null, deserialize thất bại.

Đây là hai cấp kiểm soát khác nhau. Nếu chỉ khai báo `nulls = Nulls.SKIP`, các phần tử null bên trong list vẫn theo chính sách `contentNulls` mặc định.

## 3. Các lựa chọn của enum Nulls

Jackson cung cấp enum `Nulls` để mô tả chính sách null:

| Giá trị | Hành vi |
|---|---|
| `Nulls.SET` | Gán null như một giá trị bình thường; thường gọi setter với null |
| `Nulls.SKIP` | Bỏ qua việc gán property/phần tử null |
| `Nulls.FAIL` | Từ chối null và phát sinh lỗi mapping |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng do deserializer của kiểu đích cung cấp |
| `Nulls.DEFAULT` | Dùng chính sách mặc định đã cấu hình ở phạm vi cao hơn; nếu không có cấu hình khác thì hành vi mặc định thường là SET |

### 3.1. Nulls.SET — gán null

`SET` là lựa chọn mặc định thông dụng:

```java
public class UserInput {
    private String displayName = "Anonymous";

    @JsonSetter(nulls = Nulls.SET)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Với JSON:

```json
{
  "displayName": null
}
```

setter được gọi với null, vì vậy giá trị `Anonymous` bị ghi đè.

Có thể không ghi thuộc tính `nulls` vì `Nulls.DEFAULT` là mặc định của annotation, và chính sách mặc định cuối cùng thường tương đương `SET` nếu mapper không cấu hình khác.

### 3.2. Nulls.SKIP — bỏ qua khi input là null

`SKIP` yêu cầu Jackson không gán giá trị null cho property:

```java
public class UserInput {
    private String displayName = "Anonymous";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Khi đọc:

```json
{
  "displayName": null
}
```

Jackson không gọi setter cho property này. Giá trị `Anonymous` được giữ lại.

`SKIP` hữu ích khi null có nghĩa là “không cập nhật giá trị hiện tại”. Tuy nhiên, đây là một quyết định về hợp đồng API: nếu client cần xóa giá trị bằng cách gửi null, `SKIP` sẽ làm mất khả năng phân biệt ý định xóa với ý định giữ nguyên.

### 3.3. Nulls.FAIL — từ chối null

Nếu property bắt buộc không được null, có thể từ chối ngay ở bước deserialize:

```java
public class CreateUserRequest {
    private String username;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setUsername(String username) {
        this.username = username;
    }
}
```

Input:

```json
{
  "username": null
}
```

sẽ gây lỗi mapping thay vì gọi setter với null. Jackson 2.x thường biểu diễn lỗi này bằng `InvalidNullException` (một loại `MismatchedInputException`), kèm đường dẫn property để xác định vị trí.

Lưu ý rằng `FAIL` chỉ xử lý trường hợp key có mặt và giá trị null. Nếu key `username` hoàn toàn không có trong JSON, `@JsonSetter(nulls = Nulls.FAIL)` không tự động xem đó là lỗi. Để bắt buộc property phải xuất hiện, cần cơ chế required-property hoặc validation phù hợp với mô hình dữ liệu.

### 3.4. Nulls.AS_EMPTY — chuyển null thành giá trị rỗng

`AS_EMPTY` yêu cầu Jackson dùng empty value do deserializer của kiểu đích cung cấp:

```java
public class SearchRequest {
    private String keyword = "default";

    @JsonSetter(nulls = Nulls.AS_EMPTY)
    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public String getKeyword() {
        return keyword;
    }
}
```

Với String deserializer, empty value thường là chuỗi rỗng `""`. Vì vậy, JSON:

```json
{
  "keyword": null
}
```

có thể làm setter nhận `""`, thay vì null hoặc giữ `default`.

Với collection, empty value thường là collection rỗng; với kiểu khác, giá trị rỗng phụ thuộc implementation của deserializer. Không nên giả định mọi kiểu đều chuyển thành cùng một giá trị. Nếu ứng dụng cần giá trị thay thế cụ thể, hãy dùng setter logic, custom deserializer hoặc một default value rõ ràng.

### 3.5. Nulls.DEFAULT — dùng chính sách mặc định

`DEFAULT` không phải là “giữ giá trị Java mặc định” và cũng không phải “bỏ qua null”. Nó yêu cầu Jackson tra cứu null policy được cấu hình ở phạm vi khác.

Ví dụ:

```java
@JsonSetter(nulls = Nulls.DEFAULT)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
```

Nếu mapper có global default là `SKIP`, property này dùng chính sách `SKIP`. Nếu không có cấu hình thay thế, hành vi thường quay về `SET`.

Vì vậy, `DEFAULT` hữu ích khi class muốn tuân theo chính sách chung của ứng dụng thay vì khóa cứng một hành vi tại property.

## 4. Điều khiển null cho phần tử collection và map

`contentNulls` có cùng các lựa chọn `Nulls`, nhưng áp dụng cho từng phần tử của container.

### 4.1. Bỏ qua phần tử null trong List

```java
public class BatchRequest {
    private List<String> labels;

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setLabels(List<String> labels) {
        this.labels = labels;
    }

    public List<String> getLabels() {
        return labels;
    }
}
```

Input:

```json
{
  "labels": ["new", null, "priority", null]
}
```

Kết quả list có hai phần tử:

```text
["new", "priority"]
```

Lưu ý: đây là bỏ qua các phần tử null trong container. Nếu toàn bộ property `labels` là null, chính sách `nulls` của property mới quyết định setter được gọi hay không.

### 4.2. Từ chối phần tử null

```java
@JsonSetter(contentNulls = Nulls.FAIL)
public void setLabels(List<String> labels) {
    this.labels = labels;
}
```

Với input có phần tử null, Jackson từ chối payload. Điều này phù hợp khi mọi phần tử trong collection đều phải có giá trị.

### 4.3. Chuyển phần tử null thành empty value

```java
@JsonSetter(contentNulls = Nulls.AS_EMPTY)
public void setLabels(List<String> labels) {
    this.labels = labels;
}
```

Với `List<String>`, phần tử null có thể trở thành chuỗi rỗng vì empty value của String deserializer là `""`. Kết quả minh họa:

```text
["new", "", "priority"]
```

Với phần tử có kiểu phức tạp, empty value có thể khác và phụ thuộc deserializer. Cần kiểm tra đúng kiểu phần tử của container.

### 4.4. Map: contentNulls áp dụng cho value

JSON object được ánh xạ thành map. Với `Map<String, String>`, các value null chịu tác động của `contentNulls`:

```java
public class UserMetadata {
    private Map<String, String> attributes;

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }
}
```

Input:

```json
{
  "attributes": {
    "region": "apac",
    "nickname": null,
    "team": "platform"
  }
}
```

Khi áp dụng `SKIP`, entry `nickname` bị bỏ qua; các entry còn lại được giữ.

`contentNulls` điều khiển value bên trong map, không điều khiển tên key JSON. Key vẫn phải được chuyển đổi theo key deserializer tương ứng.

## 5. Kết hợp nulls và contentNulls

Một property container có thể cần chính sách riêng cho cả container và các phần tử:

```java
public class ImportRequest {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(
            nulls = Nulls.SKIP,
            contentNulls = Nulls.FAIL
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
```

Hành vi:

| JSON input | Kết quả |
|---|---|
| Không có key `tags` | Setter không được gọi; giữ list khởi tạo |
| `"tags": null` | Setter bị bỏ qua; giữ list khởi tạo |
| `"tags": []` | Setter nhận list rỗng |
| `"tags": ["a", "b"]` | Setter nhận list hai phần tử |
| `"tags": ["a", null]` | Deserialize thất bại vì phần tử null bị từ chối |

Ví dụ này minh họa rõ hai cấp chính sách. `nulls` chỉ kiểm tra giá trị của property; `contentNulls` chỉ kiểm tra nội dung container.

## 6. Áp dụng chính sách null ở phạm vi mapper

Không phải lúc nào cũng cần lặp lại `@JsonSetter` trên từng property. Jackson 2.x cho phép đặt default setter null policy ở cấp mapper hoặc cấu hình override theo kiểu.

### 6.1. Default setter info cho toàn mapper

Ví dụ áp dụng `SKIP` cho giá trị null và `FAIL` cho phần tử null trong container:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.setDefaultSetterInfo(
        JsonSetter.Value.construct(Nulls.SKIP, Nulls.FAIL)
);
```

Cấu hình này cung cấp default cho các property không có chính sách riêng. Khi annotation trên property chỉ định `Nulls.DEFAULT` hoặc không khai báo thuộc tính null policy, Jackson có thể dùng giá trị default tương ứng.

Đây là lựa chọn có ảnh hưởng rộng. Trước khi bật, cần xác định null có cùng ý nghĩa trên mọi DTO hay không. Ví dụ, một endpoint dùng null để xóa trường nhưng endpoint khác dùng null để giữ nguyên; một global `SKIP` có thể làm sai hợp đồng của endpoint đầu tiên.

### 6.2. Override theo kiểu dữ liệu

Jackson 2.x còn hỗ trợ config override theo kiểu Java:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.configOverride(String.class)
        .setSetterInfo(JsonSetter.Value.forValueNulls(Nulls.FAIL));
```

Cấu hình trên đặt chính sách mặc định cho property có kiểu `String` khi deserialize. Nó hữu ích khi muốn mọi chuỗi trong một nhóm model tuân thủ một quy tắc nhất quán, nhưng cũng cần xem xét phạm vi ảnh hưởng: một `String` có thể là trường bắt buộc ở DTO này nhưng lại tùy chọn ở DTO khác.

Ưu tiên annotation property-level khi hợp đồng khác nhau theo từng trường; chỉ dùng global hoặc type override khi đó thực sự là quy tắc chung.

### 6.3. Độ ưu tiên giữa annotation và cấu hình mặc định

Có thể hiểu theo nguyên tắc:

1. Chính sách tường minh trên property mô tả hành vi riêng của property.
2. Nếu property dùng `Nulls.DEFAULT` hoặc không chỉ định chính sách, Jackson tra cứu cấu hình override theo kiểu/default mapper.
3. Nếu không có cấu hình thay thế, Jackson dùng hành vi mặc định của databind, thường là gán null.

Khi có nhiều lớp cấu hình, hãy kiểm thử trên mapper thực tế thay vì chỉ nhìn một annotation riêng lẻ.

## 7. Null policy với primitive và wrapper

Primitive không thể lưu null, trong khi wrapper có thể:

```java
public class RetryConfig {
    private int maxAttempts = 3;
    private Integer delaySeconds = 10;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    @JsonSetter(nulls = Nulls.FAIL)
    public void setDelaySeconds(Integer delaySeconds) {
        this.delaySeconds = delaySeconds;
    }
}
```

- Với `maxAttempts`, `SKIP` khiến setter không được gọi khi input null, do đó giá trị 3 được giữ.
- Với `delaySeconds`, `FAIL` từ chối null thay vì gán null vào wrapper.

Nếu không có null policy cụ thể, hành vi null đối với primitive còn phụ thuộc `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`. Khi feature này tắt (mặc định trong nhiều cấu hình Jackson 2.x), null cho primitive thường trở thành giá trị mặc định như 0 hoặc false. Khi bật, Jackson từ chối null cho primitive.

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

Đừng dùng primitive nếu API cần phân biệt rõ ba trạng thái: không gửi property, gửi null và gửi giá trị mặc định như 0. Wrapper type hoặc mô hình cập nhật riêng sẽ thể hiện ý nghĩa này tốt hơn.

## 8. Dùng JsonSetter trong API cập nhật từng phần

Một trường hợp quan trọng là cập nhật object hiện có. Ví dụ, một API PATCH muốn giữ giá trị cũ khi client gửi null:

```java
public class UserProfile {
    private String displayName;
    private String phone;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setPhone(String phone) {
        this.phone = phone;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getPhone() {
        return phone;
    }
}
```

Có thể đọc JSON để cập nhật instance hiện có bằng `readerForUpdating(...)`:

```java
UserProfile existing = loadProfile();

ObjectReader updater = mapper.readerForUpdating(existing);

UserProfile updated = updater.readValue("""
        {
          "displayName": "An",
          "phone": null
        }
        """);
```

Với `SKIP`, `displayName` được cập nhật thành `An`, còn `phone` giữ giá trị hiện tại.

Tuy nhiên, đây là một quy ước API cụ thể. Trong nhiều hợp đồng PATCH, client cần ba trạng thái:

- Không có key: không thay đổi.
- Có key và null: xóa giá trị.
- Có key và giá trị: thay bằng giá trị mới.

Nếu đặt `Nulls.SKIP`, hai trạng thái đầu tiên bị nhập làm một. Khi cần hỗ trợ thao tác xóa, hãy dùng `SET` hoặc một mô hình patch biểu diễn rõ presence/null, rồi xử lý nghiệp vụ tại service. Không nên để annotation vô tình quyết định ngữ nghĩa cập nhật của toàn bộ API.

## 9. Những giới hạn và điểm cần lưu ý

### 9.1. JsonSetter không thay thế validation

`Nulls.FAIL` chỉ từ chối null. Nó không xác nhận chuỗi có đúng định dạng, số có nằm trong khoảng hợp lệ hay object có thỏa invariant nghiệp vụ không. Ví dụ `"age": -10` không null nhưng vẫn không hợp lệ nếu domain không cho phép tuổi âm.

Dùng Bean Validation như `@NotNull`, `@NotBlank`, `@Min` và validation ở tầng nghiệp vụ cho các quy tắc tương ứng. Cần nhớ rằng validation thường chạy sau khi Jackson tạo object; `@JsonSetter(nulls = Nulls.FAIL)` giúp từ chối null ngay trong quá trình binding.

### 9.2. JsonSetter áp dụng cho property binding, không phải mọi null trong mọi ngữ cảnh

`nulls` điều khiển null của property. `contentNulls` điều khiển null bên trong container. Null ở root JSON, null cho constructor creator parameter hoặc null được xử lý bởi custom deserializer có thể đi theo đường xử lý riêng. Không nên giả định annotation setter sẽ bao phủ mọi ngữ cảnh null trong tài liệu.

### 9.3. Null trong collection khác null của collection

Với:

```json
{
  "tags": null
}
```

đó là null của property `tags`, do `nulls` điều khiển.

Với:

```json
{
  "tags": ["java", null]
}
```

đó là null của phần tử trong list, do `contentNulls` điều khiển.

Hai cấu hình có thể khác nhau: ví dụ property null được skip nhưng phần tử null bị fail.

### 9.4. Default và cấu hình phụ thuộc phiên bản

Các ví dụ API cấu hình mapper trong bài hướng theo Jackson 2.x. Jackson 3 thay đổi package và chuyển mapper/factory sang mô hình bất biến, do đó cần cấu hình qua builder API tương ứng. Annotation null policy vẫn là khái niệm quan trọng, nhưng khi nâng major version cần xác nhận artifact annotation/databind và API builder trong phiên bản đang dùng.

Không trộn class `com.fasterxml.jackson.databind` của Jackson 2 với `tools.jackson.databind` của Jackson 3 trong cùng đoạn code.

## 10. Ví dụ kiểm thử các chính sách null

Một test đơn giản có thể xác nhận `SKIP` giữ giá trị khởi tạo:

```java
class Preferences {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }
}
```

JUnit:

```java
@Test
void shouldKeepInitialValueWhenJsonPropertyIsNull() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Preferences preferences = mapper.readValue(
            """
            {"nickname": null}
            """,
            Preferences.class
    );

    assertEquals("guest", preferences.getNickname());
}
```

Test cho `FAIL`:

```java
class RequiredInput {
    private String code;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setCode(String code) {
        this.code = code;
    }
}

@Test
void shouldRejectExplicitNull() {
    ObjectMapper mapper = new ObjectMapper();

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                    """
                    {"code": null}
                    """,
                    RequiredInput.class
            )
    );
}
```

Khi viết test, nên kiểm tra riêng:

- Key không xuất hiện.
- Key xuất hiện với null.
- Key xuất hiện với giá trị hợp lệ.
- Container có giá trị null.
- Container có phần tử null.
- Input sai kiểu hoặc vi phạm validation.

Test nên xác nhận kết quả cuối cùng và exception contract mà ứng dụng cần, không phụ thuộc vào việc Jackson gọi một implementation method nội bộ cụ thể.

## 11. Cách lựa chọn chính sách

| Yêu cầu của property | Chính sách gợi ý |
|---|---|
| Null là giá trị hợp lệ và phải xóa giá trị hiện tại | `Nulls.SET` |
| Null có nghĩa giữ giá trị hiện tại | `Nulls.SKIP` |
| Null là input không hợp lệ | `Nulls.FAIL` |
| Null cần chuyển thành giá trị rỗng theo kiểu đích | `Nulls.AS_EMPTY` |
| Property tuân theo cấu hình chung của ứng dụng | `Nulls.DEFAULT` |
| Bỏ phần tử null trong collection/map | `contentNulls = Nulls.SKIP` |
| Từ chối phần tử null trong collection/map | `contentNulls = Nulls.FAIL` |

Không có một chính sách null đúng cho mọi property. Hãy chọn theo ý nghĩa nghiệp vụ và hợp đồng API. Với request tạo mới, `FAIL` có thể phù hợp cho trường bắt buộc; với cập nhật từng phần, `SKIP` có thể giữ dữ liệu cũ; với trường nullable thông thường, `SET` thường là hành vi mong muốn.

## 12. Kết luận

`@JsonSetter` cho phép kiểm soát chính xác cách Jackson xử lý null trong quá trình deserialize. `nulls` điều khiển giá trị null của property, còn `contentNulls` điều khiển null bên trong collection, array hoặc map. Các lựa chọn `SET`, `SKIP`, `FAIL`, `AS_EMPTY` và `DEFAULT` giúp biểu diễn những chính sách khác nhau thay vì để hành vi null phụ thuộc hoàn toàn vào mặc định.

Cần phân biệt key bị thiếu với key có giá trị null, đồng thời cân nhắc primitive, collection, cập nhật từng phần và cấu hình ở phạm vi mapper. Khi hợp đồng API quan trọng, hãy viết test riêng cho từng trạng thái null để bảo đảm Jackson thực hiện đúng ý nghĩa mà ứng dụng mong muốn.

## Tài liệu tham khảo

- [Jackson Annotations — JsonSetter](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonSetter.html)
- [Jackson Annotations — Nulls enum](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/Nulls.html)
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)

# Cấu hình hành vi setter đối với null bằng JsonSetter

Khi Jackson đọc JSON thành một Java object, một property có thể không xuất hiện trong input, có thể xuất hiện với giá trị `null`, hoặc có một giá trị cụ thể. Ba trường hợp này không đồng nghĩa với nhau. Đặc biệt, trong mô hình JavaBean, Jackson thường gọi setter khi property có mặt; nếu JSON chứa `null`, setter có thể nhận null và ghi đè giá trị đã được khởi tạo trong constructor hoặc field initializer.

Annotation `@JsonSetter` cho phép điều khiển cách Jackson xử lý giá trị null khi deserialize. Hai thuộc tính quan trọng nhất là:

- `nulls`: chính sách cho giá trị null của chính property.
- `contentNulls`: chính sách cho phần tử null bên trong container như array, collection hoặc map.

Bằng cách chọn đúng chính sách, ứng dụng có thể từ chối null, bỏ qua setter, chuyển null thành giá trị rỗng hoặc dùng chính sách mặc định. Điều này đặc biệt quan trọng với API nhận request, dữ liệu cập nhật từng phần và các DTO có giá trị khởi tạo.

## 1. Phân biệt property bị thiếu và property có giá trị null

Xét DTO:

```java
public class Profile {
    private String nickname = "guest";

    public Profile() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Có ba input cần phân biệt:

**Trường hợp A — property bị thiếu:**

```json
{}
```

Jackson không đọc thấy property `nickname`, vì vậy setter không được gọi. Giá trị `guest` từ field initializer được giữ lại.

**Trường hợp B — property có mặt với null:**

```json
{
  "nickname": null
}
```

Với chính sách null mặc định thông thường, Jackson gọi `setNickname(null)`. Giá trị `guest` bị thay bằng null.

**Trường hợp C — property có giá trị:**

```json
{
  "nickname": "an"
}
```

Jackson gọi `setNickname("an")`; giá trị sau deserialize là `an`.

| Input | Setter có được gọi? | Kết quả với DTO trên |
|---|---|---|
| Không có key `nickname` | Không | `guest` |
| `"nickname": null` | Có, theo mặc định | `null` |
| `"nickname": "an"` | Có | `an` |

`@JsonSetter` điều khiển trường hợp property hiện diện nhưng có giá trị null. Nó không biến một property bị thiếu thành null và không tự tạo giá trị cho key không có trong JSON.

## 2. @JsonSetter và hai thuộc tính nulls/contentNulls

Trong Jackson 2.x, `@JsonSetter` thuộc package:

```java
com.fasterxml.jackson.annotation.JsonSetter
```

Các chính sách null qua `nulls` và `contentNulls` được hỗ trợ từ Jackson 2.9.

Có thể đặt annotation trên setter:

```java
public class Profile {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Hoặc đặt trên field khi class dùng field-based binding:

```java
public class Profile {
    @JsonSetter(nulls = Nulls.SKIP)
    private String nickname = "guest";
}
```

Với JavaBean, đặt trên setter thường làm rõ ý định xử lý input. Nếu một logical property có cả field, getter và setter, nên tránh đặt các chính sách mâu thuẫn trên nhiều accessor; hãy khai báo annotation tại vị trí đại diện rõ ràng cho quy tắc deserialize.

### 2.1. nulls: null của chính property

`nulls` điều khiển điều gì xảy ra khi giá trị JSON của property là `null`:

```java
@JsonSetter(nulls = Nulls.SKIP)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
```

Ở đây, Jackson bỏ qua việc gán khi input có `"nickname": null`. Setter không được gọi cho giá trị null đó.

### 2.2. contentNulls: null bên trong container

`contentNulls` áp dụng cho các phần tử null bên trong array, collection hoặc value của map. Nó không điều khiển null của chính container.

```java
public class Preferences {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
```

Với input:

```json
{
  "tags": ["java", null, "jackson"]
}
```

Jackson bỏ qua phần tử null trong danh sách và setter nhận list chứa `java` và `jackson`.

Hai chính sách có thể kết hợp:

```java
@JsonSetter(
        nulls = Nulls.SKIP,
        contentNulls = Nulls.FAIL
)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Kết quả:

- Nếu `tags` là null, setter bị bỏ qua.
- Nếu `tags` là một array nhưng có phần tử null, deserialize thất bại.

Đây là hai cấp kiểm soát khác nhau. Nếu chỉ khai báo `nulls = Nulls.SKIP`, các phần tử null bên trong list vẫn theo chính sách `contentNulls` mặc định.

## 3. Các lựa chọn của enum Nulls

Jackson cung cấp enum `Nulls` để mô tả chính sách null:

| Giá trị | Hành vi |
|---|---|
| `Nulls.SET` | Gán null như một giá trị bình thường; thường gọi setter với null |
| `Nulls.SKIP` | Bỏ qua việc gán property/phần tử null |
| `Nulls.FAIL` | Từ chối null và phát sinh lỗi mapping |
| `Nulls.AS_EMPTY` | Dùng giá trị rỗng do deserializer của kiểu đích cung cấp |
| `Nulls.DEFAULT` | Dùng chính sách mặc định đã cấu hình ở phạm vi cao hơn; nếu không có cấu hình khác thì hành vi mặc định thường là SET |

### 3.1. Nulls.SET — gán null

`SET` là lựa chọn mặc định thông dụng:

```java
public class UserInput {
    private String displayName = "Anonymous";

    @JsonSetter(nulls = Nulls.SET)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Với JSON:

```json
{
  "displayName": null
}
```

setter được gọi với null, vì vậy giá trị `Anonymous` bị ghi đè.

Có thể không ghi thuộc tính `nulls` vì `Nulls.DEFAULT` là mặc định của annotation, và chính sách mặc định cuối cùng thường tương đương `SET` nếu mapper không cấu hình khác.

### 3.2. Nulls.SKIP — bỏ qua khi input là null

`SKIP` yêu cầu Jackson không gán giá trị null cho property:

```java
public class UserInput {
    private String displayName = "Anonymous";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Khi đọc:

```json
{
  "displayName": null
}
```

Jackson không gọi setter cho property này. Giá trị `Anonymous` được giữ lại.

`SKIP` hữu ích khi null có nghĩa là “không cập nhật giá trị hiện tại”. Tuy nhiên, đây là một quyết định về hợp đồng API: nếu client cần xóa giá trị bằng cách gửi null, `SKIP` sẽ làm mất khả năng phân biệt ý định xóa với ý định giữ nguyên.

### 3.3. Nulls.FAIL — từ chối null

Nếu property bắt buộc không được null, có thể từ chối ngay ở bước deserialize:

```java
public class CreateUserRequest {
    private String username;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setUsername(String username) {
        this.username = username;
    }
}
```

Input:

```json
{
  "username": null
}
```

sẽ gây lỗi mapping thay vì gọi setter với null. Jackson 2.x thường biểu diễn lỗi này bằng `InvalidNullException` (một loại `MismatchedInputException`), kèm đường dẫn property để xác định vị trí.

Lưu ý rằng `FAIL` chỉ xử lý trường hợp key có mặt và giá trị null. Nếu key `username` hoàn toàn không có trong JSON, `@JsonSetter(nulls = Nulls.FAIL)` không tự động xem đó là lỗi. Để bắt buộc property phải xuất hiện, cần cơ chế required-property hoặc validation phù hợp với mô hình dữ liệu.

### 3.4. Nulls.AS_EMPTY — chuyển null thành giá trị rỗng

`AS_EMPTY` yêu cầu Jackson dùng empty value do deserializer của kiểu đích cung cấp:

```java
public class SearchRequest {
    private String keyword = "default";

    @JsonSetter(nulls = Nulls.AS_EMPTY)
    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public String getKeyword() {
        return keyword;
    }
}
```

Với String deserializer, empty value thường là chuỗi rỗng `""`. Vì vậy, JSON:

```json
{
  "keyword": null
}
```

có thể làm setter nhận `""`, thay vì null hoặc giữ `default`.

Với collection, empty value thường là collection rỗng; với kiểu khác, giá trị rỗng phụ thuộc implementation của deserializer. Không nên giả định mọi kiểu đều chuyển thành cùng một giá trị. Nếu ứng dụng cần giá trị thay thế cụ thể, hãy dùng setter logic, custom deserializer hoặc một default value rõ ràng.

### 3.5. Nulls.DEFAULT — dùng chính sách mặc định

`DEFAULT` không phải là “giữ giá trị Java mặc định” và cũng không phải “bỏ qua null”. Nó yêu cầu Jackson tra cứu null policy được cấu hình ở phạm vi khác.

Ví dụ:

```java
@JsonSetter(nulls = Nulls.DEFAULT)
public void setNickname(String nickname) {
    this.nickname = nickname;
}
```

Nếu mapper có global default là `SKIP`, property này dùng chính sách `SKIP`. Nếu không có cấu hình thay thế, hành vi thường quay về `SET`.

Vì vậy, `DEFAULT` hữu ích khi class muốn tuân theo chính sách chung của ứng dụng thay vì khóa cứng một hành vi tại property.

## 4. Điều khiển null cho phần tử collection và map

`contentNulls` có cùng các lựa chọn `Nulls`, nhưng áp dụng cho từng phần tử của container.

### 4.1. Bỏ qua phần tử null trong List

```java
public class BatchRequest {
    private List<String> labels;

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setLabels(List<String> labels) {
        this.labels = labels;
    }

    public List<String> getLabels() {
        return labels;
    }
}
```

Input:

```json
{
  "labels": ["new", null, "priority", null]
}
```

Kết quả list có hai phần tử:

```text
["new", "priority"]
```

Lưu ý: đây là bỏ qua các phần tử null trong container. Nếu toàn bộ property `labels` là null, chính sách `nulls` của property mới quyết định setter được gọi hay không.

### 4.2. Từ chối phần tử null

```java
@JsonSetter(contentNulls = Nulls.FAIL)
public void setLabels(List<String> labels) {
    this.labels = labels;
}
```

Với input có phần tử null, Jackson từ chối payload. Điều này phù hợp khi mọi phần tử trong collection đều phải có giá trị.

### 4.3. Chuyển phần tử null thành empty value

```java
@JsonSetter(contentNulls = Nulls.AS_EMPTY)
public void setLabels(List<String> labels) {
    this.labels = labels;
}
```

Với `List<String>`, phần tử null có thể trở thành chuỗi rỗng vì empty value của String deserializer là `""`. Kết quả minh họa:

```text
["new", "", "priority"]
```

Với phần tử có kiểu phức tạp, empty value có thể khác và phụ thuộc deserializer. Cần kiểm tra đúng kiểu phần tử của container.

### 4.4. Map: contentNulls áp dụng cho value

JSON object được ánh xạ thành map. Với `Map<String, String>`, các value null chịu tác động của `contentNulls`:

```java
public class UserMetadata {
    private Map<String, String> attributes;

    @JsonSetter(contentNulls = Nulls.SKIP)
    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }
}
```

Input:

```json
{
  "attributes": {
    "region": "apac",
    "nickname": null,
    "team": "platform"
  }
}
```

Khi áp dụng `SKIP`, entry `nickname` bị bỏ qua; các entry còn lại được giữ.

`contentNulls` điều khiển value bên trong map, không điều khiển tên key JSON. Key vẫn phải được chuyển đổi theo key deserializer tương ứng.

## 5. Kết hợp nulls và contentNulls

Một property container có thể cần chính sách riêng cho cả container và các phần tử:

```java
public class ImportRequest {
    private List<String> tags = new ArrayList<>();

    @JsonSetter(
            nulls = Nulls.SKIP,
            contentNulls = Nulls.FAIL
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public List<String> getTags() {
        return tags;
    }
}
```

Hành vi:

| JSON input | Kết quả |
|---|---|
| Không có key `tags` | Setter không được gọi; giữ list khởi tạo |
| `"tags": null` | Setter bị bỏ qua; giữ list khởi tạo |
| `"tags": []` | Setter nhận list rỗng |
| `"tags": ["a", "b"]` | Setter nhận list hai phần tử |
| `"tags": ["a", null]` | Deserialize thất bại vì phần tử null bị từ chối |

Ví dụ này minh họa rõ hai cấp chính sách. `nulls` chỉ kiểm tra giá trị của property; `contentNulls` chỉ kiểm tra nội dung container.

## 6. Áp dụng chính sách null ở phạm vi mapper

Không phải lúc nào cũng cần lặp lại `@JsonSetter` trên từng property. Jackson 2.x cho phép đặt default setter null policy ở cấp mapper hoặc cấu hình override theo kiểu.

### 6.1. Default setter info cho toàn mapper

Ví dụ áp dụng `SKIP` cho giá trị null và `FAIL` cho phần tử null trong container:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.setDefaultSetterInfo(
        JsonSetter.Value.construct(Nulls.SKIP, Nulls.FAIL)
);
```

Cấu hình này cung cấp default cho các property không có chính sách riêng. Khi annotation trên property chỉ định `Nulls.DEFAULT` hoặc không khai báo thuộc tính null policy, Jackson có thể dùng giá trị default tương ứng.

Đây là lựa chọn có ảnh hưởng rộng. Trước khi bật, cần xác định null có cùng ý nghĩa trên mọi DTO hay không. Ví dụ, một endpoint dùng null để xóa trường nhưng endpoint khác dùng null để giữ nguyên; một global `SKIP` có thể làm sai hợp đồng của endpoint đầu tiên.

### 6.2. Override theo kiểu dữ liệu

Jackson 2.x còn hỗ trợ config override theo kiểu Java:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.configOverride(String.class)
        .setSetterInfo(JsonSetter.Value.forValueNulls(Nulls.FAIL));
```

Cấu hình trên đặt chính sách mặc định cho property có kiểu `String` khi deserialize. Nó hữu ích khi muốn mọi chuỗi trong một nhóm model tuân thủ một quy tắc nhất quán, nhưng cũng cần xem xét phạm vi ảnh hưởng: một `String` có thể là trường bắt buộc ở DTO này nhưng lại tùy chọn ở DTO khác.

Ưu tiên annotation property-level khi hợp đồng khác nhau theo từng trường; chỉ dùng global hoặc type override khi đó thực sự là quy tắc chung.

### 6.3. Độ ưu tiên giữa annotation và cấu hình mặc định

Có thể hiểu theo nguyên tắc:

1. Chính sách tường minh trên property mô tả hành vi riêng của property.
2. Nếu property dùng `Nulls.DEFAULT` hoặc không chỉ định chính sách, Jackson tra cứu cấu hình override theo kiểu/default mapper.
3. Nếu không có cấu hình thay thế, Jackson dùng hành vi mặc định của databind, thường là gán null.

Khi có nhiều lớp cấu hình, hãy kiểm thử trên mapper thực tế thay vì chỉ nhìn một annotation riêng lẻ.

## 7. Null policy với primitive và wrapper

Primitive không thể lưu null, trong khi wrapper có thể:

```java
public class RetryConfig {
    private int maxAttempts = 3;
    private Integer delaySeconds = 10;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    @JsonSetter(nulls = Nulls.FAIL)
    public void setDelaySeconds(Integer delaySeconds) {
        this.delaySeconds = delaySeconds;
    }
}
```

- Với `maxAttempts`, `SKIP` khiến setter không được gọi khi input null, do đó giá trị 3 được giữ.
- Với `delaySeconds`, `FAIL` từ chối null thay vì gán null vào wrapper.

Nếu không có null policy cụ thể, hành vi null đối với primitive còn phụ thuộc `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES`. Khi feature này tắt (mặc định trong nhiều cấu hình Jackson 2.x), null cho primitive thường trở thành giá trị mặc định như 0 hoặc false. Khi bật, Jackson từ chối null cho primitive.

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
```

Đừng dùng primitive nếu API cần phân biệt rõ ba trạng thái: không gửi property, gửi null và gửi giá trị mặc định như 0. Wrapper type hoặc mô hình cập nhật riêng sẽ thể hiện ý nghĩa này tốt hơn.

## 8. Dùng JsonSetter trong API cập nhật từng phần

Một trường hợp quan trọng là cập nhật object hiện có. Ví dụ, một API PATCH muốn giữ giá trị cũ khi client gửi null:

```java
public class UserProfile {
    private String displayName;
    private String phone;

    @JsonSetter(nulls = Nulls.SKIP)
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    @JsonSetter(nulls = Nulls.SKIP)
    public void setPhone(String phone) {
        this.phone = phone;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getPhone() {
        return phone;
    }
}
```

Có thể đọc JSON để cập nhật instance hiện có bằng `readerForUpdating(...)`:

```java
UserProfile existing = loadProfile();

ObjectReader updater = mapper.readerForUpdating(existing);

UserProfile updated = updater.readValue("""
        {
          "displayName": "An",
          "phone": null
        }
        """);
```

Với `SKIP`, `displayName` được cập nhật thành `An`, còn `phone` giữ giá trị hiện tại.

Tuy nhiên, đây là một quy ước API cụ thể. Trong nhiều hợp đồng PATCH, client cần ba trạng thái:

- Không có key: không thay đổi.
- Có key và null: xóa giá trị.
- Có key và giá trị: thay bằng giá trị mới.

Nếu đặt `Nulls.SKIP`, hai trạng thái đầu tiên bị nhập làm một. Khi cần hỗ trợ thao tác xóa, hãy dùng `SET` hoặc một mô hình patch biểu diễn rõ presence/null, rồi xử lý nghiệp vụ tại service. Không nên để annotation vô tình quyết định ngữ nghĩa cập nhật của toàn bộ API.

## 9. Những giới hạn và điểm cần lưu ý

### 9.1. JsonSetter không thay thế validation

`Nulls.FAIL` chỉ từ chối null. Nó không xác nhận chuỗi có đúng định dạng, số có nằm trong khoảng hợp lệ hay object có thỏa invariant nghiệp vụ không. Ví dụ `"age": -10` không null nhưng vẫn không hợp lệ nếu domain không cho phép tuổi âm.

Dùng Bean Validation như `@NotNull`, `@NotBlank`, `@Min` và validation ở tầng nghiệp vụ cho các quy tắc tương ứng. Cần nhớ rằng validation thường chạy sau khi Jackson tạo object; `@JsonSetter(nulls = Nulls.FAIL)` giúp từ chối null ngay trong quá trình binding.

### 9.2. JsonSetter áp dụng cho property binding, không phải mọi null trong mọi ngữ cảnh

`nulls` điều khiển null của property. `contentNulls` điều khiển null bên trong container. Null ở root JSON, null cho constructor creator parameter hoặc null được xử lý bởi custom deserializer có thể đi theo đường xử lý riêng. Không nên giả định annotation setter sẽ bao phủ mọi ngữ cảnh null trong tài liệu.

### 9.3. Null trong collection khác null của collection

Với:

```json
{
  "tags": null
}
```

đó là null của property `tags`, do `nulls` điều khiển.

Với:

```json
{
  "tags": ["java", null]
}
```

đó là null của phần tử trong list, do `contentNulls` điều khiển.

Hai cấu hình có thể khác nhau: ví dụ property null được skip nhưng phần tử null bị fail.

### 9.4. Default và cấu hình phụ thuộc phiên bản

Các ví dụ API cấu hình mapper trong bài hướng theo Jackson 2.x. Jackson 3 thay đổi package và chuyển mapper/factory sang mô hình bất biến, do đó cần cấu hình qua builder API tương ứng. Annotation null policy vẫn là khái niệm quan trọng, nhưng khi nâng major version cần xác nhận artifact annotation/databind và API builder trong phiên bản đang dùng.

Không trộn class `com.fasterxml.jackson.databind` của Jackson 2 với `tools.jackson.databind` của Jackson 3 trong cùng đoạn code.

## 10. Ví dụ kiểm thử các chính sách null

Một test đơn giản có thể xác nhận `SKIP` giữ giá trị khởi tạo:

```java
class Preferences {
    private String nickname = "guest";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }
}
```

JUnit:

```java
@Test
void shouldKeepInitialValueWhenJsonPropertyIsNull() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Preferences preferences = mapper.readValue(
            """
            {"nickname": null}
            """,
            Preferences.class
    );

    assertEquals("guest", preferences.getNickname());
}
```

Test cho `FAIL`:

```java
class RequiredInput {
    private String code;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setCode(String code) {
        this.code = code;
    }
}

@Test
void shouldRejectExplicitNull() {
    ObjectMapper mapper = new ObjectMapper();

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                    """
                    {"code": null}
                    """,
                    RequiredInput.class
            )
    );
}
```

Khi viết test, nên kiểm tra riêng:

- Key không xuất hiện.
- Key xuất hiện với null.
- Key xuất hiện với giá trị hợp lệ.
- Container có giá trị null.
- Container có phần tử null.
- Input sai kiểu hoặc vi phạm validation.

Test nên xác nhận kết quả cuối cùng và exception contract mà ứng dụng cần, không phụ thuộc vào việc Jackson gọi một implementation method nội bộ cụ thể.

## 11. Cách lựa chọn chính sách

| Yêu cầu của property | Chính sách gợi ý |
|---|---|
| Null là giá trị hợp lệ và phải xóa giá trị hiện tại | `Nulls.SET` |
| Null có nghĩa giữ giá trị hiện tại | `Nulls.SKIP` |
| Null là input không hợp lệ | `Nulls.FAIL` |
| Null cần chuyển thành giá trị rỗng theo kiểu đích | `Nulls.AS_EMPTY` |
| Property tuân theo cấu hình chung của ứng dụng | `Nulls.DEFAULT` |
| Bỏ phần tử null trong collection/map | `contentNulls = Nulls.SKIP` |
| Từ chối phần tử null trong collection/map | `contentNulls = Nulls.FAIL` |

Không có một chính sách null đúng cho mọi property. Hãy chọn theo ý nghĩa nghiệp vụ và hợp đồng API. Với request tạo mới, `FAIL` có thể phù hợp cho trường bắt buộc; với cập nhật từng phần, `SKIP` có thể giữ dữ liệu cũ; với trường nullable thông thường, `SET` thường là hành vi mong muốn.

## 12. Kết luận

`@JsonSetter` cho phép kiểm soát chính xác cách Jackson xử lý null trong quá trình deserialize. `nulls` điều khiển giá trị null của property, còn `contentNulls` điều khiển null bên trong collection, array hoặc map. Các lựa chọn `SET`, `SKIP`, `FAIL`, `AS_EMPTY` và `DEFAULT` giúp biểu diễn những chính sách khác nhau thay vì để hành vi null phụ thuộc hoàn toàn vào mặc định.

Cần phân biệt key bị thiếu với key có giá trị null, đồng thời cân nhắc primitive, collection, cập nhật từng phần và cấu hình ở phạm vi mapper. Khi hợp đồng API quan trọng, hãy viết test riêng cho từng trạng thái null để bảo đảm Jackson thực hiện đúng ý nghĩa mà ứng dụng mong muốn.

## Tài liệu tham khảo

- [Jackson Annotations — JsonSetter](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonSetter.html)
- [Jackson Annotations — Nulls enum](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/Nulls.html)
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/ObjectMapper.html)
- [Jackson Databind — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features)

