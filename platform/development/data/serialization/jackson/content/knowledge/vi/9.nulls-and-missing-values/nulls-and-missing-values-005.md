# Xử lý null trong phần tử của mảng, collection và Map

Trong JSON, `null` có thể xuất hiện ở nhiều tầng: thay cho cả một property, ở một phần tử của array, collection hoặc ở value của một key trong object. Những vị trí này có ý nghĩa khác nhau. Khi dùng Jackson, cần phân biệt **container null** với **content null**, đồng thời phân biệt giá trị null với property hoặc key không xuất hiện.

Ba payload sau không tương đương:

```json
{}
```

```json
{ "tags": null }
```

```json
{ "tags": ["java", null, "jackson"] }
```

Trường hợp đầu không có property `tags`. Trường hợp thứ hai có property nhưng cả collection là null. Trường hợp thứ ba có collection với ba phần tử, trong đó phần tử thứ hai là null. Cách xử lý các trạng thái này ảnh hưởng đến dữ liệu sau deserialize, validation và JSON được serialize trở lại.

## 1. Container null và content null

Container là cấu trúc chứa nhiều giá trị như array, `List`, `Set` hoặc `Map`. Có hai tầng null:

- **Container null:** bản thân array, collection hoặc map là null.
- **Content null:** container tồn tại nhưng một hoặc nhiều phần tử/giá trị bên trong là null.

| JSON | Ý nghĩa | Trạng thái Java thường gặp |
|---|---|---|
| Không có property `items` | Property bị thiếu | Field giữ giá trị khởi tạo hoặc mặc định. |
| `"items": null` | Cả container null | `items == null` theo mặc định. |
| `"items": []` | Container rỗng | Collection/array tồn tại, không có phần tử. |
| `"items": [null]` | Một content null | Một phần tử null nếu kiểu đích cho phép. |
| `"items": ["A", null]` | Giá trị hợp lệ xen kẽ null | Container có hai phần tử, phần tử thứ hai null. |

Với Map, phải phân biệt null ở value và null ở key:

```json
{
  "attributes": {
    "color": "blue",
    "comment": null
  }
}
```

Ở đây `comment` là key chuỗi có value null. JSON object dùng tên property dạng chuỗi; `"null"` là key gồm bốn ký tự, không phải Java null key.

## 2. Hành vi mặc định với array và collection

Jackson thường giữ null trong array hoặc collection nếu kiểu phần tử là kiểu tham chiếu và không có cấu hình loại bỏ null.

```java
public class BatchRequest {
    private String[] codes;
    private List<String> labels;

    public String[] getCodes() { return codes; }
    public void setCodes(String[] codes) { this.codes = codes; }
    public List<String> getLabels() { return labels; }
    public void setLabels(List<String> labels) { this.labels = labels; }
}
```

Đọc JSON:

```java
String json = """
    {
      "codes": ["A1", null, "A3"],
      "labels": ["primary", null, "archived"]
    }
    """;

BatchRequest request = mapper.readValue(json, BatchRequest.class);

System.out.println(request.getCodes().length);  // 3
System.out.println(request.getCodes()[1]);      // null
System.out.println(request.getLabels().size()); // 3
System.out.println(request.getLabels().get(1)); // null
```

Với kiểu phần tử tham chiếu như `String`, `User`, `Integer` hoặc DTO, null có thể được giữ trực tiếp. Collection không tự loại bỏ null chỉ vì phần tử không chứa dữ liệu.

### 2.1. Vị trí phần tử có thể mang ý nghĩa

JSON array có thứ tự và vị trí. Nếu giữ null, phần tử ở index 1 vẫn là null và phần tử thứ ba vẫn ở index 2. `List` cũng giữ thứ tự và có thể chứa null tùy implementation.

```java
List<String> names = Arrays.asList("An", null, "Bình");
String[] values = {"A", null, "C"};
```

Nếu cấu hình bỏ qua null, collection có thể ngắn hơn và index của các phần tử phía sau thay đổi. Với danh sách tọa độ, cột dữ liệu hoặc slot theo thứ tự, không nên bỏ null nếu vị trí mang ý nghĩa nghiệp vụ.

### 2.2. Container null khác container rỗng

```json
{ "labels": null }
```

```json
{ "labels": [] }
```

Payload đầu thường làm property thành null; payload thứ hai tạo collection rỗng. API có thể dùng khác biệt này để biểu diễn “không cung cấp danh sách”, “xóa danh sách” hoặc “cung cấp danh sách nhưng không có phần tử”.

Nếu field được khởi tạo:

```java
public class SearchRequest {
    private List<String> tags = new ArrayList<>();
}
```

Khi property bị thiếu và Jackson không gọi setter, giá trị khởi tạo có thể vẫn là list rỗng. Khi JSON có `"tags": null`, hành vi mặc định thường gán null. Có thể thay đổi bằng `@JsonSetter(nulls = ...)`.

## 3. Mảng primitive và mảng wrapper

Java array có thể chứa primitive hoặc kiểu tham chiếu. Primitive không thể lưu null; wrapper có thể:

| Kiểu Java | Có thể chứa null? | JSON `[1, null, 3]` |
|---|---|---|
| `int[]` | Không | Null có thể được coercion thành giá trị mặc định nếu chưa bật kiểm tra nghiêm ngặt. |
| `Integer[]` | Có | Giữ null ở vị trí thứ hai. |
| `boolean[]` | Không | Null có thể thành `false` nếu được coercion. |
| `Boolean[]` | Có | Giữ null ở vị trí tương ứng. |
| `long[]` | Không | Null có thể thành `0L` nếu được coercion. |
| `Long[]` | Có | Giữ null ở vị trí tương ứng. |

Ví dụ:

```java
public class NumberBatch {
    private int[] primitiveValues;
    private Integer[] wrapperValues;

    public int[] getPrimitiveValues() { return primitiveValues; }
    public void setPrimitiveValues(int[] values) { primitiveValues = values; }
    public Integer[] getWrapperValues() { return wrapperValues; }
    public void setWrapperValues(Integer[] values) { wrapperValues = values; }
}
```

```json
{
  "primitiveValues": [1, null, 3],
  "wrapperValues": [1, null, 3]
}
```

Với cấu hình Jackson mặc định phổ biến, null cho primitive có thể được chuyển thành giá trị mặc định vì `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` mặc định tắt. Điều này làm mất khác biệt giữa null và số 0/false.

Nếu cần từ chối null cho primitive:

```java
ObjectMapper mapper = new ObjectMapper()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);

ObjectReader strictReader = mapper.readerFor(NumberBatch.class)
    .with(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Khi feature bật, null ở vị trí cần gán vào primitive gây lỗi mapping thay vì âm thầm trở thành giá trị mặc định. Nếu null là trạng thái hợp lệ, hãy dùng wrapper như `Integer[]`, `Boolean[]` hoặc `List<Integer>`.

## 4. Null trong Map: value và key

Map Java thường được ánh xạ thành JSON object. Tên property trở thành key; giá trị property được deserialize thành value theo kiểu generic.

```java
public class Settings {
    private Map<String, String> attributes;

    public Map<String, String> getAttributes() { return attributes; }
    public void setAttributes(Map<String, String> attributes) {
        this.attributes = attributes;
    }
}
```

```json
{
  "attributes": {
    "theme": "dark",
    "description": null
  }
}
```

Kết quả:

```java
Settings settings = mapper.readValue(json, Settings.class);

settings.getAttributes().containsKey("description"); // true
settings.getAttributes().get("description");         // null
settings.getAttributes().get("missing");             // null
```

Chỉ gọi `get` không đủ để phân biệt key có tồn tại với value null. Dùng `containsKey` khi cần biết khác biệt.

### 4.1. Value null khác key không tồn tại

```json
{ "description": null }
```

```json
{}
```

Với `Map<String, String>`, object đầu tạo entry có key `description` và value null; object sau không tạo entry. Khác biệt này hữu ích cho patch document và đồng bộ dữ liệu: key bị thiếu có thể có nghĩa “không thay đổi”, còn key có null có thể có nghĩa “xóa giá trị”.

### 4.2. JSON object không có null key

JSON object không có cú pháp key null:

```json
{
  "null": "literal key",
  "": "empty key"
}
```

Key đầu tiên là chuỗi `"null"`; key thứ hai là chuỗi rỗng. Cả hai đều khác Java `null`.

Khi serialize `Map` có null key, Jackson thường không thể biểu diễn key đó bằng JSON object với cấu hình mặc định và báo lỗi vì null key không có tên property hợp lệ. Nếu nghiệp vụ cần key có thể null, biểu diễn map dưới dạng array các cặp key/value:

```json
[
  { "key": null, "value": "unknown" },
  { "key": "region", "value": "south" }
]
```

Mô hình Java tương ứng có thể là `List<EntryDto>` với `key` và `value` là kiểu tham chiếu. Không dùng chuỗi `"null"` làm thay thế nếu cần phân biệt null với literal key `"null"`.

### 4.3. Map value là object hoặc collection

```json
{
  "users": {
    "u1": { "name": "An" },
    "u2": null,
    "u3": { "name": "Bình" }
  }
}
```

Với `Map<String, User>`, entry `u2` có value null. Với map chứa collection:

```json
{
  "groups": {
    "admins": ["u1", null, "u3"],
    "guests": null
  }
}
```

Map value `guests` là null (container con null), còn list `admins` có một content null. Cấu hình phải được đặt tại đúng property/container cần điều khiển.

## 5. JsonSetter: null của property và null của content

`@JsonSetter` điều khiển null khi deserialize. Hai thuộc tính cần phân biệt:

- `nulls`: xử lý null của chính property/container.
- `contentNulls`: xử lý null bên trong container, chẳng hạn phần tử collection/array hoặc value của Map.

Các lựa chọn `Nulls`:

| Giá trị | Ý nghĩa |
|---|---|
| `Nulls.SET` | Gán null vào property/content nếu kiểu đích cho phép. |
| `Nulls.SKIP` | Bỏ qua null; với property không cập nhật property, với content bỏ phần tử/entry tương ứng. |
| `Nulls.FAIL` | Ném lỗi mapping khi gặp null. |
| `Nulls.AS_EMPTY` | Dùng empty value do deserializer của kiểu đích định nghĩa. |
| `Nulls.DEFAULT` | Dùng chính sách mặc định của Jackson. |

`contentNulls` có từ Jackson 2.9. Với phiên bản cũ hơn, kiểm tra API sẵn có và cân nhắc custom deserializer.

### 5.1. Cho phép null container nhưng từ chối null phần tử

```java
public class TagRequest {
    @JsonSetter(nulls = Nulls.SET, contentNulls = Nulls.FAIL)
    private List<String> tags;

    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }
}
```

| JSON | Kết quả |
|---|---|
| `{}` | Property bị thiếu; giữ trạng thái khởi tạo/default. |
| `{"tags": null}` | `tags` được gán null. |
| `{"tags": []}` | Collection rỗng. |
| `{"tags": ["a", "b"]}` | Deserialize thành công. |
| `{"tags": ["a", null]}` | Lỗi do `contentNulls = Nulls.FAIL`. |

API có thể cho phép bỏ toàn bộ danh sách nhưng không cho phép phần tử không có giá trị.

### 5.2. Bỏ qua phần tử null trong List

```java
public class SearchRequest {
    @JsonSetter(contentNulls = Nulls.SKIP)
    private List<String> tags = new ArrayList<>();

    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }
}
```

Với JSON:

```json
{ "tags": ["java", null, "jackson", null] }
```

Các giá trị null bị bỏ qua khi tạo collection, nên kết quả chỉ còn `java` và `jackson`. Số lượng phần tử và index thay đổi. Chỉ dùng cách này khi null có nghĩa “không có item” và vị trí không mang ý nghĩa.

### 5.3. Bỏ qua null value trong Map

```java
public class MetadataRequest {
    @JsonSetter(contentNulls = Nulls.SKIP)
    private Map<String, String> metadata = new LinkedHashMap<>();

    public Map<String, String> getMetadata() { return metadata; }
    public void setMetadata(Map<String, String> metadata) {
        this.metadata = metadata;
    }
}
```

Với JSON:

```json
{
  "metadata": {
    "source": "web",
    "comment": null,
    "region": "south"
  }
}
```

`contentNulls = Nulls.SKIP` bỏ entry `comment`. Kết quả Map không chứa key đó. Nếu cần phân biệt “key được gửi với null” với “key không được gửi”, không dùng chính sách skip.

### 5.4. Bỏ qua cả property null và content null

```java
public class PatchRequest {
    @JsonSetter(
        nulls = Nulls.SKIP,
        contentNulls = Nulls.SKIP
    )
    private List<String> labels = new ArrayList<>();
}
```

- Nếu JSON không có `labels`, field giữ collection được khởi tạo.
- Nếu JSON có `"labels": null`, property bị bỏ qua nên collection hiện tại không bị đặt thành null.
- Nếu JSON có `"labels": ["a", null, "b"]`, phần tử null bị bỏ qua.

Đây là cấu hình có ích cho một số patch/update DTO, nhưng cần mô tả rõ vì client gửi null sẽ không xóa dữ liệu như nhiều người có thể kỳ vọng.

### 5.5. Chuyển null thành giá trị rỗng bằng AS_EMPTY

`Nulls.AS_EMPTY` yêu cầu Jackson dùng empty value do deserializer của kiểu tương ứng cung cấp.

```java
public class DisplayRequest {
    @JsonSetter(nulls = Nulls.AS_EMPTY)
    private List<String> labels;

    @JsonSetter(contentNulls = Nulls.AS_EMPTY)
    private List<String> aliases;
}
```

Với `labels`, null của cả property được chuyển thành empty value của deserializer collection. Với `aliases`, null ở từng phần tử được chuyển thành empty value của deserializer phần tử; với `String`, empty value thường là chuỗi rỗng.

Không nên giả định `AS_EMPTY` luôn tạo cùng kết quả cho mọi kiểu. Giá trị rỗng phụ thuộc deserializer; custom deserializer có thể định nghĩa empty value riêng. Nếu nghiệp vụ yêu cầu chính xác `new ArrayList<>()`, `0`, `""` hoặc object sentinel cụ thể, hãy kiểm tra bằng test cho kiểu đó.

### 5.6. Nulls.DEFAULT

`Nulls.DEFAULT` để Jackson dùng chính sách null mặc định ở cấp property/content:

```java
@JsonSetter(
    nulls = Nulls.DEFAULT,
    contentNulls = Nulls.FAIL
)
private List<String> tags;
```

Trong ví dụ, null của cả list theo cấu hình mặc định, còn null của phần tử bị từ chối. Mặc định của primitive, wrapper và container không giống nhau.

## 6. Áp dụng chính sách null cho mảng

`contentNulls` cũng dùng được cho property array:

```java
public class CodeRequest {
    @JsonSetter(contentNulls = Nulls.FAIL)
    private String[] codes;

    public String[] getCodes() { return codes; }
    public void setCodes(String[] codes) { this.codes = codes; }
}
```

Nếu một phần tử JSON là null, Jackson báo lỗi thay vì tạo array có null. Với `Nulls.SKIP`, phần tử null bị loại khỏi nội dung được tạo; array kết quả có thể ngắn hơn array đầu vào. Nếu vị trí có ý nghĩa, `FAIL` thường rõ ràng hơn `SKIP`.

Với array primitive, cần xem xét đồng thời `contentNulls` và `FAIL_ON_NULL_FOR_PRIMITIVES`. `int[]` không thể chứa null; nếu cần từ chối null, bật feature primitive strict hoặc dùng chính sách content null phù hợp và kiểm thử với phiên bản Jackson đang dùng. Nếu cần giữ null như một trạng thái, dùng `Integer[]`.

## 7. Cấu hình null của Map

Ví dụ Map có hai chính sách:

```java
public class ConfigRequest {
    // Map được phép null; null value bên trong bị từ chối.
    @JsonSetter(nulls = Nulls.SET, contentNulls = Nulls.FAIL)
    private Map<String, String> requiredValues;

    // Map null trở thành empty Map; null value bên trong bị bỏ qua.
    @JsonSetter(nulls = Nulls.AS_EMPTY, contentNulls = Nulls.SKIP)
    private Map<String, String> optionalValues;
}
```

`nulls` xử lý toàn bộ Map; `contentNulls` xử lý từng value. Nó không áp dụng cho key vì JSON object property name được đọc qua key deserializer và không có token value null ở vị trí key.

Nếu key có kiểu Java không phải `String`, Jackson dùng key deserializer để chuyển tên property thành kiểu key. Ví dụ `Map<Integer, String>` có thể nhận property name `"10"` và chuyển thành integer 10. Giá trị null của entry vẫn do content null policy kiểm soát.

## 8. Null, property thiếu và giá trị khởi tạo

Đối với collection property, có ít nhất bốn trạng thái:

| Trạng thái đầu vào | Ý nghĩa có thể có trong API |
|---|---|
| Property bị thiếu | Client không đề cập; với PATCH có thể hiểu là giữ nguyên. |
| Property có giá trị null | Client chủ động xóa hoặc đặt property thành null. |
| Property là collection rỗng | Client cung cấp tập hợp không có phần tử. |
| Property có phần tử null | Một phần tử cụ thể không có giá trị. |

Ví dụ DTO khởi tạo collection:

```java
public class UpdateProfileRequest {
    private List<String> interests = new ArrayList<>();

    public List<String> getInterests() { return interests; }
    public void setInterests(List<String> interests) {
        this.interests = interests;
    }
}
```

Với cấu hình mặc định:

- JSON `{}` thường để nguyên list rỗng được khởi tạo.
- JSON `{"interests": null}` thường gọi setter với null.
- JSON `{"interests": []}` gán list rỗng từ input.
- JSON `{"interests": [null]}` gán list có một phần tử null.

Nếu dùng `Nulls.SKIP` ở property, null tường minh không cập nhật property; nếu dùng `Nulls.AS_EMPTY`, null tường minh trở thành empty value. Chọn chính sách dựa trên ngữ nghĩa API, đặc biệt với PATCH hoặc đồng bộ dữ liệu.

### 8.1. Constructor-based DTO và creator properties

Với immutable DTO được tạo qua constructor hoặc record, Jackson phải quyết định giá trị cho tham số khi property bị thiếu hoặc null. Hành vi phụ thuộc creator, kiểu tham số, annotation và các `DeserializationFeature` liên quan.

```java
public record TeamRequest(
    String name,
    List<String> members
) {}
```

JSON có `"members": null` khác với JSON không có `members`, nhưng cả hai có thể dẫn tới giá trị null trong record nếu không có cấu hình bổ sung. Nếu cần bắt buộc creator property phải xuất hiện hoặc không được null, xem xét `FAIL_ON_MISSING_CREATOR_PROPERTIES` và `FAIL_ON_NULL_CREATOR_PROPERTIES` phù hợp với hợp đồng và phiên bản Jackson.

Không nên bật các feature này toàn cục nếu một số endpoint hợp lệ với property thiếu/null. Có thể tạo `ObjectReader` riêng hoặc dùng validation phù hợp với từng DTO.

## 9. Null khi serialize: bỏ property hay bỏ content?

`@JsonSetter` điều khiển đầu vào; `@JsonInclude` điều khiển những gì được ghi ra JSON.

- `value`: điều kiện đưa chính property vào JSON.
- `content`: điều kiện đưa giá trị bên trong Map, Collection hoặc array vào JSON.

Ví dụ:

```java
public class Response {
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private List<String> labels;

    @JsonInclude(content = JsonInclude.Include.NON_NULL)
    private Map<String, String> metadata;
}
```

Với `labels`, nếu cả list là null thì property bị bỏ qua; chỉ đặt `value` không đồng nghĩa mọi phần tử null bên trong list đều bị loại. Với `metadata`, `content = NON_NULL` yêu cầu bỏ entry có value null khi serialize.

Có thể kết hợp cả hai:

```java
@JsonInclude(
    value = JsonInclude.Include.NON_NULL,
    content = JsonInclude.Include.NON_NULL
)
private List<String> tags;
```

Khi đó property null bị bỏ qua và null content được lọc theo content inclusion. Với array/collection, việc loại null có thể làm thay đổi số lượng hoặc vị trí phần tử trong JSON; chỉ sử dụng khi hợp đồng cho phép. Kiểm thử output của đúng loại container và phiên bản Jackson đang dùng.

### 9.1. Inclusion ở cấp class hoặc mapper

```java
@JsonInclude(
    value = JsonInclude.Include.NON_NULL,
    content = JsonInclude.Include.NON_NULL
)
public class ApiResponse {
    private List<String> tags;
    private Map<String, String> metadata;
}
```

Hoặc cấu hình inclusion chung cho property:

```java
ObjectMapper mapper = new ObjectMapper()
    .setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

`setSerializationInclusion` là cấu hình inclusion chung cho property. Nếu cần chính sách riêng cho content, dùng `@JsonInclude(content = ...)` hoặc cấu hình override phù hợp. Đừng giả định bỏ property null sẽ tự loại mọi null bên trong collection/map.

### 9.2. Map value null và Map key null khi serialize

```java
Map<String, String> values = new LinkedHashMap<>();
values.put("a", "one");
values.put("b", null);
```

Với cấu hình mặc định, Jackson có thể serialize thành:

```json
{
  "a": "one",
  "b": null
}
```

Nếu content inclusion là `NON_NULL`, entry `b` có thể được bỏ qua:

```json
{
  "a": "one"
}
```

Null key là trường hợp khác. JSON object cần tên property dạng chuỗi; serializer key mặc định của Jackson thường từ chối null key. Nếu cần biểu diễn null key, chuyển Map thành array các object `{ "key": ..., "value": ... }` hoặc định nghĩa key serializer có chủ đích và chấp nhận output dùng một chuỗi đại diện chứ không phải key null thực sự.

## 10. Custom deserializer cho content

Nếu phần tử có kiểu tùy chỉnh và cần quy tắc mapping riêng, có thể dùng `@JsonDeserialize(contentUsing = ...)`:

```java
public class MeasurementRequest {
    @JsonDeserialize(contentUsing = MeasurementDeserializer.class)
    private List<Measurement> measurements;
}
```

Custom deserializer xử lý cách chuyển đổi giá trị không-null thành `Measurement`. Chính sách null của container/content vẫn cần được xác định riêng, ví dụ bằng `@JsonSetter(contentNulls = Nulls.FAIL)`. Nếu custom deserializer cần giá trị null hoặc empty đặc biệt, có thể override các phương thức như `getNullValue(...)` hoặc `getEmptyValue(...)` tùy API phiên bản Jackson.

Không nên giả định Jackson luôn gọi `deserialize()` cho token JSON null. Jackson có cơ chế null provider riêng; null thường được xử lý theo đường riêng thay vì logic deserialize giá trị thông thường.

## 11. Validation phần tử null

Jackson tập trung vào parsing và mapping. Nó không tự động áp dụng mọi quy tắc nghiệp vụ cho từng phần tử collection hoặc map.

Nếu ứng dụng dùng Jakarta Bean Validation, có thể mô tả ràng buộc ở container và type argument:

```java
public class RegistrationRequest {
    @NotNull
    private List<@NotNull String> emails;

    private Map<@NotNull String, @NotNull UserRequest> users;
}
```

- `@NotNull` trên `emails` yêu cầu collection không null.
- `@NotNull` trên `String` yêu cầu mỗi phần tử email không null.
- Với Map, có thể ràng buộc key/value bằng type-use annotation tùy provider và cấu hình validation.

Để ràng buộc được thực thi, ứng dụng phải gọi Bean Validation hoặc dùng framework tự động validate request. Chỉ khai báo annotation không khiến `ObjectMapper` tự chạy validation.

Nếu muốn từ chối null ngay khi deserialize, `contentNulls = Nulls.FAIL` phát hiện lỗi ở biên JSON. Nếu muốn gom nhiều lỗi nghiệp vụ và trả response validation thống nhất, có thể giữ null rồi chạy validator sau mapping.

## 12. Generic type và null content

Khi đọc collection hoặc Map trực tiếp từ JSON, phải giữ thông tin kiểu phần tử/value. Nếu chỉ truyền raw type, Jackson có thể tạo kiểu tổng quát như `Map` hoặc `List` với giá trị object thay vì kiểu DTO mong muốn.

```java
List<User> users = mapper.readValue(
    jsonArray,
    new TypeReference<List<User>>() {}
);

Map<String, User> userMap = mapper.readValue(
    jsonObject,
    new TypeReference<Map<String, User>>() {}
);
```

Null vẫn được xử lý theo vị trí content:

```json
[
  { "id": 1, "name": "An" },
  null,
  { "id": 3, "name": "Bình" }
]
```

Với `List<User>`, phần tử thứ hai có thể là null. Nếu cần từ chối, đặt content null policy tại property hoặc reader/type configuration phù hợp. `TypeReference` chỉ giữ kiểu generic; nó không tự áp dụng validation hoặc loại null.

## 13. Chọn phạm vi cấu hình

| Phạm vi | Cách cấu hình | Khi phù hợp |
|---|---|---|
| Một property | `@JsonSetter(nulls = ..., contentNulls = ...)` | Một field có semantics riêng. |
| Một DTO/endpoint | `ObjectReader` với feature hoặc mix-in phù hợp | Một điểm đọc có chính sách riêng. |
| Một kiểu Java trên mapper | Config override theo type | Nhiều property cùng kiểu cần mặc định thống nhất. |
| Toàn ứng dụng | Feature/configuration của `ObjectMapper` | Chính sách áp dụng đồng nhất cho mọi luồng. |

`FAIL_ON_NULL_FOR_PRIMITIVES` là feature ở cấp mapper/reader. `@JsonSetter(contentNulls = Nulls.FAIL)` là chính sách gắn với một property. Tránh bật chế độ nghiêm ngặt toàn cục nếu các API có hợp đồng khác nhau.

Khi dùng `ObjectMapper` dùng chung, hoàn tất cấu hình trước khi phục vụ request. Với khác biệt theo endpoint, tạo `ObjectReader` riêng thay vì thay đổi mapper giữa các request.

## 14. Những tình huống dễ nhầm

### 14.1. NON_NULL không phải SKIP

`@JsonInclude(content = NON_NULL)` ảnh hưởng chiều serialize: null content không được ghi ra JSON theo inclusion policy. `@JsonSetter(contentNulls = SKIP)` ảnh hưởng chiều deserialize: null content trong JSON không được đưa vào object Java.

### 14.2. Null không giống chuỗi rỗng

```json
{ "items": [null, ""] }
```

Phần tử đầu là JSON null; phần tử thứ hai là string có độ dài bằng 0. Nếu dùng `Nulls.AS_EMPTY` cho content kiểu String, null có thể trở thành chuỗi rỗng theo empty value của String deserializer. Nếu giữ `Nulls.SET`, hai trạng thái vẫn khác nhau.

### 14.3. Null không giống số 0 hoặc false

Với primitive, null có thể bị coercion về giá trị mặc định nếu không bật `FAIL_ON_NULL_FOR_PRIMITIVES`. Dùng wrapper khi cần giữ null, hoặc bật strict feature để phát hiện payload vi phạm hợp đồng.

### 14.4. Map.get(key) == null không chứng minh key bị thiếu

Value có thể null trong khi key vẫn tồn tại. Dùng `containsKey` để phân biệt, đặc biệt khi Map đại diện cho patch hoặc cấu hình kế thừa.

### 14.5. Bỏ null khỏi array có thể làm thay đổi vị trí

Nếu dùng `contentNulls = SKIP` hoặc content inclusion để loại null, array có thể ngắn lại. Nếu vị trí phần tử tương ứng với ID, tọa độ hoặc cột dữ liệu, nên từ chối null hoặc dùng object có tên field thay vì âm thầm bỏ phần tử.

## 15. Ví dụ tổng hợp cho List, array và Map

```java
public class ImportRequest {
    // List có thể null; nếu list tồn tại thì không cho phần tử null.
    @JsonSetter(nulls = Nulls.SET, contentNulls = Nulls.FAIL)
    private List<String> names;

    // Bỏ qua phần tử null; vị trí và số lượng có thể thay đổi.
    @JsonSetter(contentNulls = Nulls.SKIP)
    private Integer[] scores;

    // Bỏ entry có value null.
    @JsonSetter(contentNulls = Nulls.SKIP)
    private Map<String, String> metadata;

    public List<String> getNames() { return names; }
    public void setNames(List<String> names) { this.names = names; }
    public Integer[] getScores() { return scores; }
    public void setScores(Integer[] scores) { this.scores = scores; }
    public Map<String, String> getMetadata() { return metadata; }
    public void setMetadata(Map<String, String> metadata) {
        this.metadata = metadata;
    }
}
```

Input:

```json
{
  "names": ["An", null, "Bình"],
  "scores": [10, null, 30],
  "metadata": {
    "source": "csv",
    "comment": null,
    "region": "south"
  }
}
```

Kết quả theo chính sách:

- `names` gây lỗi vì null content bị từ chối.
- Nếu sửa `names` thành `["An", "Bình"]`, list được tạo với hai phần tử.
- `scores` chỉ còn hai giá trị `10` và `30` vì null bị bỏ qua.
- `metadata` không chứa entry `comment` vì value null bị bỏ qua.

Để kiểm tra từng chính sách, tách test theo property thay vì chỉ dùng một payload có nhiều lỗi cùng lúc. Như vậy, khi một trường hợp thất bại, có thể xác định rõ chính sách nào tạo ra kết quả.

## 16. Hướng dẫn lựa chọn chính sách

| Yêu cầu nghiệp vụ | Chính sách gợi ý |
|---|---|
| Null phần tử là dữ liệu hợp lệ và cần giữ vị trí | Dùng kiểu tham chiếu và mặc định `SET`. |
| Không cho phép phần tử null | `contentNulls = Nulls.FAIL`. |
| Null có nghĩa phần tử không tồn tại | `contentNulls = Nulls.SKIP`, nếu thay đổi index/size được chấp nhận. |
| Null phần tử phải thay bằng giá trị rỗng | `contentNulls = Nulls.AS_EMPTY`; kiểm tra empty value của deserializer. |
| Null toàn bộ collection cần giữ là null | `nulls = Nulls.SET`. |
| Null toàn bộ collection cần thành collection rỗng | `nulls = Nulls.AS_EMPTY`. |
| Null property không được làm thay đổi giá trị đã có | `nulls = Nulls.SKIP`. |
| Null của primitive phải bị từ chối | `FAIL_ON_NULL_FOR_PRIMITIVES` hoặc chính sách property/content phù hợp. |
| Map entry có value null cần được giữ | Không skip content; dùng `containsKey` để phân biệt key thiếu. |
| Map entry có value null cần bỏ khi serialize | `@JsonInclude(content = Include.NON_NULL)`. |
| Nghiệp vụ cần key Map có thể null | Biểu diễn bằng array các object key/value. |

Khi thiết kế API, mô tả riêng semantics của property bị thiếu, property null, container rỗng và phần tử null. Sau đó chọn kiểu Java và cấu hình Jackson tương ứng. Không nên dùng một chính sách null chung cho mọi container nếu ý nghĩa nghiệp vụ khác nhau.

## 17. Những điểm cần ghi nhớ

- Null của cả array/collection/Map khác null của phần tử hoặc Map value.
- Property bị thiếu khác property có mặt với null; collection rỗng khác collection có một phần tử null.
- Kiểu tham chiếu như `String`, `Integer`, DTO và `List<T>` có thể giữ null content; primitive không thể.
- `FAIL_ON_NULL_FOR_PRIMITIVES` giúp từ chối null khi ánh xạ vào primitive thay vì dùng giá trị mặc định.
- Trong Map JSON, property name là key dạng chuỗi; `"null"` không phải Java null key.
- `@JsonSetter(nulls = ...)` điều khiển null của property; `contentNulls = ...` điều khiển null bên trong container.
- `Nulls.SET`, `SKIP`, `FAIL`, `AS_EMPTY` và `DEFAULT` có semantics khác nhau; `AS_EMPTY` phụ thuộc deserializer.
- `contentNulls = SKIP` có thể làm thay đổi size/index của array/collection hoặc loại bỏ entry trong Map.
- `@JsonInclude(value = ..., content = ...)` điều khiển chiều serialize, không thay thế chính sách deserialize.
- Dùng `containsKey` để phân biệt Map key bị thiếu với key hiện diện có value null.
- Jackson mapping không thay thế Bean Validation; validation phần tử cần được thực thi rõ ràng.
- Cấu hình null nên đặt ở phạm vi property, reader hoặc mapper phù hợp với hợp đồng dữ liệu.

Khi xử lý null trong container, hãy xác định rõ null nằm ở tầng nào và ý nghĩa của nó trong hợp đồng JSON. Một cấu hình đúng sẽ giữ lại thông tin cần thiết, từ chối dữ liệu không hợp lệ hoặc bỏ qua giá trị theo quy tắc đã định nghĩa. Việc phân biệt container null, content null và property bị thiếu giúp ứng dụng tránh mất dữ liệu âm thầm và làm cho hành vi deserialize/serialize nhất quán hơn.
