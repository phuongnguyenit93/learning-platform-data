# Kiểu chứa dữ liệu tự do và chính sách thuộc tính không khai báo

Không phải object JSON nào cũng có danh sách thuộc tính cố định. Một API có thể nhận metadata do hệ thống tích hợp gửi đến, các trường mở rộng theo từng loại sự kiện hoặc cấu hình có tên khóa do người dùng lựa chọn. Với những trường hợp này, schema cần mô tả được object có các thuộc tính động mà không phải khai báo trước từng tên.

OpenAPI sử dụng `additionalProperties` trong Schema Object để định nghĩa chính sách cho các thuộc tính không được liệt kê trong `properties`. Thuộc tính này có thể cho phép mọi giá trị, giới hạn giá trị theo một schema hoặc cấm thuộc tính chưa khai báo. Trong ứng dụng Spring Boot, các kiểu như `Map<String, T>`, `Map<String, Object>` và `JsonNode`, cùng annotation Jackson và `@Schema`, giúp triển khai cũng như mô tả dữ liệu động.

## 1. Object có cấu trúc cố định và object có dữ liệu tự do

Một object có cấu trúc cố định thường khai báo trước tên và kiểu của từng thuộc tính:

```yaml
type: object
required:
  - id
  - name
properties:
  id:
    type: string
    format: uuid
  name:
    type: string
  active:
    type: boolean
```

Object trên có ba thuộc tính đã biết. Client và server có thể dựa vào schema để hiểu `id`, `name` và `active`.

Trong một số API, object còn cần nhận các khóa chưa biết trước. Ví dụ, webhook có thể mang các metadata khác nhau tùy nhà cung cấp; sự kiện có thể có các thuộc tính mở rộng theo loại sự kiện; cấu hình có thể cho phép người quản trị tự đặt tên khóa.

```json
{
  "eventId": "evt-1001",
  "eventType": "order.updated",
  "metadata": {
    "source": "partner-a",
    "region": "ap-southeast-1",
    "retryCount": 2,
    "verified": true
  }
}
```

Các thuộc tính trong `metadata` có tên thay đổi và có thể mang nhiều kiểu JSON. Nếu chỉ khai báo `source`, `region`, `retryCount` và `verified` thành `properties`, schema sẽ không phản ánh mục đích mở rộng của trường này. `additionalProperties` cho phép mô tả phần dữ liệu động.

## 2. `additionalProperties` hoạt động như thế nào?

Trong một Schema Object dạng object, `properties` mô tả các khóa đã biết; `additionalProperties` quy định cách xử lý các khóa còn lại. Giá trị của nó có thể là Boolean hoặc một Schema Object.

| Cách khai báo | Ý nghĩa |
|---|---|
| Không khai báo `additionalProperties` | Theo mặc định, các thuộc tính chưa được liệt kê vẫn được cho phép |
| `additionalProperties: true` | Cho phép thuộc tính chưa khai báo mà không đặt ràng buộc schema cụ thể lên giá trị |
| `additionalProperties: false` | Không cho phép thuộc tính chưa khai báo |
| `additionalProperties: { ...schema... }` | Cho phép thuộc tính chưa khai báo, nhưng giá trị của từng thuộc tính phải phù hợp schema chỉ định |

Ví dụ cho phép khóa động với giá trị chuỗi:

```yaml
type: object
properties:
  name:
    type: string
additionalProperties:
  type: string
```

Object có thể có `name` và bất kỳ thuộc tính bổ sung nào, nhưng giá trị của mỗi thuộc tính bổ sung phải là chuỗi.

Ví dụ cấm khóa ngoài danh sách:

```yaml
type: object
properties:
  name:
    type: string
  age:
    type: integer
additionalProperties: false
```

Với schema này, `name` và `age` được cho phép; khóa như `role` hoặc `internalFlag` không thuộc hợp đồng.

`additionalProperties` chỉ áp dụng cho các thuộc tính ở cùng cấp object với nó. Nó không tự động quyết định chính sách cho object con. Nếu `metadata` là một object lồng trong `Event`, chính sách thuộc tính động của `metadata` phải được khai báo trong schema của `metadata`.

## 3. Cho phép giá trị bất kỳ hay giới hạn kiểu của giá trị?

Một object tự do có thể cần chấp nhận mọi giá trị JSON hoặc chỉ cho phép một kiểu giá trị. Hai trường hợp cần schema khác nhau.

### Giá trị bất kỳ

```yaml
type: object
additionalProperties: true
```

Hoặc có thể dùng schema rỗng cho giá trị bổ sung:

```yaml
type: object
additionalProperties: {}
```

Hai cách trên biểu đạt rằng khóa động không bị ràng buộc bởi một schema giá trị cụ thể. Giá trị có thể là chuỗi, số, boolean, object, array hoặc null tùy phiên bản OpenAPI/JSON Schema và các ràng buộc khác áp dụng.

### Giá trị chỉ là chuỗi

```yaml
type: object
additionalProperties:
  type: string
```

Ví dụ JSON hợp lệ:

```json
{
  "labels": {
    "source": "partner-a",
    "region": "ap-southeast-1"
  }
}
```

Giá trị số hoặc boolean sẽ không phù hợp schema này.

### Giá trị là số

```yaml
type: object
additionalProperties:
  type: number
```

Phù hợp với bản đồ giá trị đo lường hoặc bảng giá có khóa động:

```json
{
  "prices": {
    "standard": 120000,
    "express": 250000
  }
}
```

### Giá trị là object có cấu trúc cố định

Nếu mỗi khóa động ánh xạ đến một object cùng hình dạng, có thể chỉ định schema cho giá trị:

```yaml
type: object
additionalProperties:
  type: object
  required:
    - enabled
  properties:
    enabled:
      type: boolean
    description:
      type: string
```

Mỗi khóa động được phép chứa object có `enabled` và `description` theo schema này. Cách làm phù hợp với bản đồ cấu hình theo tên module, trong đó mỗi mục có cùng cấu trúc.

## 4. Ánh xạ `Map` trong Java sang `additionalProperties`

Map là kiểu Java tự nhiên cho object có tên khóa động. Tên khóa được biểu diễn thành tên thuộc tính JSON; kiểu generic của value cung cấp thông tin để springdoc mô tả `additionalProperties`.

| Kiểu Java | Schema OpenAPI thường gặp |
|---|---|
| `Map<String, String>` | Object với `additionalProperties` có `type: string` |
| `Map<String, Integer>` | Object với `additionalProperties` có `type: integer` |
| `Map<String, BigDecimal>` | Object với `additionalProperties` có `type: number` |
| `Map<String, UserMetadata>` | Object với `additionalProperties` tham chiếu schema `UserMetadata` |
| `Map<String, Object>` | Object với giá trị tự do, thường không có schema ràng buộc cụ thể |
| `Map<String, JsonNode>` | Object với giá trị JSON động; cần kiểm tra schema được sinh và cách serialize |

Ví dụ DTO:

```java
public class EventRequest {
    private String eventType;
    private Map<String, String> labels;
    private Map<String, Object> metadata;

    // getters và setters
}
```

Trong đó, `labels` phù hợp với `additionalProperties` kiểu string; `metadata` cho phép value linh hoạt hơn. Schema minh họa:

```yaml
EventRequest:
  type: object
  properties:
    eventType:
      type: string
    labels:
      type: object
      additionalProperties:
        type: string
    metadata:
      type: object
      additionalProperties: true
```

Nên khai báo kiểu generic cụ thể nếu biết trước kiểu value. `Map<String, Object>` linh hoạt nhưng làm giảm khả năng kiểm tra kiểu ở compile time và khiến client khó biết mỗi khóa có thể chứa dữ liệu gì. Dùng `Map<String, String>` hoặc `Map<String, MetadataValue>` khi nghiệp vụ có thể xác định cấu trúc rõ ràng.

## 5. Dùng `@Schema` để mô tả thuộc tính bổ sung

Springdoc thường suy ra schema từ kiểu Java và generic. Annotation `@Schema` có thể được dùng để bổ sung mô tả hoặc quy định chính sách thuộc tính động khi suy luận mặc định chưa thể hiện đúng ý định.

Ví dụ Map chỉ chứa chuỗi:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;

public class PartnerEvent {

    @Schema(
        description = "Các nhãn mở rộng, mỗi khóa có giá trị chuỗi",
        type = "object",
        additionalPropertiesSchema = @Schema(implementation = String.class)
    )
    private Map<String, String> labels;

    // getters và setters
}
```

Với object cho phép giá trị tùy ý, có thể biểu đạt chính sách mở bằng `additionalProperties` theo phiên bản Swagger Annotations đang dùng:

```java
@Schema(
    description = "Metadata mở rộng với tên khóa động",
    type = "object",
    additionalProperties = Schema.AdditionalPropertiesValue.TRUE
)
private Map<String, Object> metadata;
```

Nếu cần đóng schema để không chấp nhận thuộc tính chưa khai báo, có thể sử dụng:

```java
@Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
public class StrictUserRequest {
    private String name;
    private String email;

    // getters và setters
}
```

Tên thuộc tính annotation và các giá trị enum có thể phụ thuộc phiên bản `swagger-annotations` được springdoc quản lý. Khi nâng cấp thư viện, hãy kiểm tra API annotation trong phiên bản thực tế và xác minh YAML được sinh. Không tự ghi đè phiên bản Swagger Annotations chỉ để dùng một thuộc tính mới nếu điều đó làm lệch dependency management của Spring Boot/springdoc.

## 6. Dữ liệu tự do bằng `JsonNode` hoặc `Object`

Khi giá trị động có thể là nhiều kiểu JSON khác nhau, Java `Object` hoặc Jackson `JsonNode` là hai lựa chọn thường gặp.

### `Map<String, Object>`

`Map<String, Object>` phù hợp khi phần dữ liệu có dạng object với khóa chuỗi, còn value có thể là chuỗi, số, boolean, list hoặc map con.

```java
public class IntegrationPayload {
    private Map<String, Object> attributes;

    // getters và setters
}
```

Ưu điểm là dễ dùng với các kiểu Java thông thường. Nhược điểm là value có thể trở thành `String`, `Integer`, `Double`, `Boolean`, `List`, `Map` hoặc kiểu khác tùy quá trình deserialize. Mã xử lý phải kiểm tra kiểu trước khi ép kiểu và không giả định mọi giá trị đều có cùng cấu trúc.

### `JsonNode`

Jackson `JsonNode` biểu diễn cây JSON. Nó có thể đại diện object, array, string, number, boolean hoặc null. Nếu trường API cần là object tự do, có thể kiểm tra node là object trước khi xử lý.

```java
public class WebhookRequest {
    private String eventType;
    private JsonNode payload;

    // getters và setters
}
```

`JsonNode` hữu ích khi cần giữ cấu trúc JSON lồng nhau mà chưa muốn ánh xạ sang POJO cố định. Nó cũng cung cấp API truy cập an toàn hơn so với ép kiểu nhiều tầng từ `Object`. Tuy nhiên, schema OpenAPI có thể cần được bổ sung để thể hiện rõ trường nào là object tự do, array hoặc bất kỳ JSON value nào.

Không nên dùng `Object` hoặc `JsonNode` chỉ để tránh thiết kế DTO. Nếu cấu trúc dữ liệu đã ổn định, POJO có kiểu cụ thể cho phép validation, tài liệu và client code tốt hơn.

## 7. Thu nhận thuộc tính không khai báo bằng Jackson

Jackson cung cấp `@JsonAnySetter` và `@JsonAnyGetter` để xử lý các thuộc tính JSON không có property cố định tương ứng trong lớp Java.

- `@JsonAnySetter` nhận các thuộc tính chưa được ánh xạ vào property đã khai báo khi deserialize JSON.
- `@JsonAnyGetter` xuất các cặp key/value từ Map thành các thuộc tính cùng cấp trong JSON khi serialize.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class EventPayload {
    private String eventType;
    private final Map<String, Object> extensions = new LinkedHashMap<>();

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> getExtensions() {
        return extensions;
    }
}
```

Với JSON đầu vào:

```json
{
  "eventType": "order.updated",
  "source": "partner-a",
  "retryCount": 2
}
```

Jackson có thể gán `eventType` vào thuộc tính đã khai báo và đưa `source`, `retryCount` vào Map `extensions`. Khi serialize, `@JsonAnyGetter` đưa các entry trong Map ra thành các thuộc tính cùng cấp:

```json
{
  "eventType": "order.updated",
  "source": "partner-a",
  "retryCount": 2
}
```

Điều này khác với một field thông thường như `Map<String, Object> metadata`, vốn thường được serialize thành object con `metadata: { ... }`. `@JsonAnyGetter` làm phẳng Map ra cùng cấp với các thuộc tính khác.

Khi dùng `@JsonAnySetter`/`@JsonAnyGetter`, hãy kiểm tra springdoc có sinh `additionalProperties` theo ý muốn hay không. Tùy phiên bản Jackson, Swagger Core và springdoc, việc suy luận từ annotation Jackson có thể không đủ để mô tả toàn bộ chính sách. Có thể bổ sung `@Schema` trên lớp hoặc dùng customizer để điều chỉnh schema.

## 8. Phân biệt `additionalProperties` với `@JsonIgnoreProperties`

Hai cơ chế này giải quyết hai vấn đề khác nhau:

| Cơ chế | Phạm vi | Kết quả |
|---|---|---|
| OpenAPI `additionalProperties: false` | Hợp đồng schema | Khai báo rằng thuộc tính không nằm trong `properties` không được phép |
| OpenAPI `additionalProperties: true` | Hợp đồng schema | Cho phép thuộc tính không khai báo |
| OpenAPI `additionalProperties: {schema}` | Hợp đồng schema | Cho phép thuộc tính động nhưng ràng buộc kiểu value |
| Jackson `@JsonIgnoreProperties(ignoreUnknown = true)` | Deserialize JSON | Bỏ qua thuộc tính không nhận diện; không lưu chúng vào Map |
| Jackson `@JsonAnySetter` | Deserialize JSON | Thu nhận thuộc tính không nhận diện vào nơi xử lý do ứng dụng chỉ định |

Ví dụ:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class UserRequest {
    private String name;

    // getters và setters
}
```

Nếu request có thêm `"admin": true`, Jackson có thể bỏ qua thuộc tính đó thay vì lưu lại. Điều này không tương đương với việc API hỗ trợ một trường metadata động. Tài liệu OpenAPI cũng không tự động trở thành `additionalProperties: true` chỉ vì lớp có `ignoreUnknown = true`.

Ngược lại, schema khai báo `additionalProperties: false` không tự cấu hình Jackson từ chối request có field lạ. Jackson có thể bỏ qua hoặc từ chối tùy cấu hình `FAIL_ON_UNKNOWN_PROPERTIES`, annotation và cách ứng dụng deserialize. Nếu muốn server thực thi đúng chính sách schema, phải cấu hình runtime hoặc validator tương ứng.

## 9. Chọn chính sách cho thuộc tính không khai báo

Có ba chính sách phổ biến. Việc chọn chính sách ảnh hưởng đến khả năng mở rộng, kiểm soát dữ liệu và tính tương thích của API.

| Chính sách | Schema | Phù hợp khi | Rủi ro cần kiểm soát |
|---|---|---|---|
| Mở hoàn toàn | `additionalProperties: true` | Payload thực sự cần chấp nhận mọi khóa và giá trị JSON | Khó validation, khó sinh client có kiểu mạnh, dễ nhận dữ liệu ngoài dự kiến |
| Mở có kiểu | `additionalProperties: { ... }` | Tên khóa thay đổi nhưng kiểu value có quy tắc rõ | Value sai kiểu cần được xử lý nhất quán ở runtime |
| Đóng | `additionalProperties: false` | Contract cần tập thuộc tính chính xác, kiểm soát chặt request/response | Thêm field mới có thể làm client hoặc request cũ không tương thích nếu kiểm tra quá nghiêm |

Ví dụ cho cấu hình mở có kiểu:

```yaml
type: object
properties:
  configVersion:
    type: string
required:
  - configVersion
additionalProperties:
  type: string
```

Object có `configVersion` và các khóa khác với value dạng chuỗi. Chính sách này hữu ích khi khóa động là tên thuộc tính cấu hình nhưng kiểu giá trị vẫn thống nhất.

Nếu chỉ một phần dữ liệu cần mở rộng, nên tạo một trường rõ ràng như `extensions` hoặc `metadata` thay vì mở toàn bộ object cấp cao:

```yaml
type: object
properties:
  id:
    type: string
    format: uuid
  status:
    type: string
  extensions:
    type: object
    additionalProperties: true
additionalProperties: false
```

Thiết kế này giữ `id` và `status` trong tập field được kiểm soát, trong khi vùng `extensions` cho phép dữ liệu động. Đây thường là lựa chọn cân bằng giữa khả năng mở rộng và tính rõ ràng của hợp đồng.

## 10. Ảnh hưởng của OpenAPI 3.0 và 3.1

`additionalProperties` tồn tại trong cả OpenAPI 3.0 và 3.1, nhưng cách mô hình hóa Schema Object có nền tảng khác nhau:

- OpenAPI 3.0 sử dụng một tập con và biến thể của JSON Schema. Schema hỗ trợ `additionalProperties` dưới dạng Boolean hoặc Schema Object.
- OpenAPI 3.1 đồng bộ chặt hơn với JSON Schema 2020-12 và hỗ trợ nhiều từ khóa JSON Schema hơn.

Các ví dụ cơ bản `true`, `false` và schema value dùng cho `additionalProperties` đều có thể xuất hiện trong cả hai phiên bản. Tuy nhiên, nếu schema sử dụng các từ khóa JSON Schema nâng cao khác, cần xác nhận phiên bản OpenAPI và công cụ validator/client có hỗ trợ hay không.

Không nên mặc định rằng mọi công cụ xử lý OpenAPI 3.0 đều hiểu đầy đủ schema 3.1. Hãy kiểm tra trường `openapi` ở đầu tài liệu được springdoc sinh, phiên bản thư viện và khả năng hỗ trợ của Swagger UI, code generator, mock server cùng validator trong pipeline.

## 11. Tùy biến schema khi springdoc suy luận chưa đúng

Nếu springdoc suy ra schema không đúng ý định, có thể điều chỉnh bằng annotation `@Schema` hoặc các customizer.

Ví dụ, một Map chứa value dạng `MetadataEntry`:

```java
public class MetadataEntry {
    private String value;
    private String source;

    // getters và setters
}

public class EventRequest {
    @Schema(
        description = "Metadata có khóa động; mỗi giá trị dùng cấu trúc MetadataEntry",
        type = "object",
        additionalPropertiesSchema = @Schema(implementation = MetadataEntry.class)
    )
    private Map<String, MetadataEntry> metadata;

    // getters và setters
}
```

Nếu annotation không đủ, có thể dùng `OpenApiCustomizer` để cập nhật schema trong tài liệu. Ví dụ khung:

```java
@Bean
OpenApiCustomizer dynamicMetadataSchemaCustomizer() {
    return openApi -> {
        // Tìm schema EventRequest và điều chỉnh additionalProperties.
        // Chỉ thay đổi schema có tên/điều kiện đã xác định rõ.
    };
}
```

Customizer thay đổi mô hình OpenAPI được công bố; nó không thay đổi kiểu Java, Jackson hoặc cách Spring bind dữ liệu. Nếu tài liệu cho phép chuỗi nhưng ứng dụng chỉ nhận số, hợp đồng và runtime vẫn mâu thuẫn. Hãy kiểm tra cả hai sau khi tùy biến.

## 12. Kiểm tra chính sách thuộc tính động

Sau khi tạo schema có `additionalProperties`, nên kiểm tra tài liệu và hành vi ứng dụng:

1. Tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
2. Tìm schema của DTO và xác định object nào có `properties` cùng `additionalProperties`.
3. Xác nhận chính sách là mở, mở có kiểu hay đóng.
4. Gửi JSON có đủ thuộc tính đã khai báo.
5. Gửi thêm một thuộc tính chưa khai báo để xác nhận hành vi runtime.
6. Với schema có kiểu value, thử value đúng kiểu và sai kiểu.
7. Với `@JsonAnySetter`, xác nhận field lạ được lưu vào đúng Map; với `@JsonAnyGetter`, xác nhận JSON output có đúng hình dạng.
8. Chạy OpenAPI validator và kiểm tra các công cụ client có thể xử lý schema động.

Ví dụ kiểm tra schema mở có value chuỗi:

```json
{
  "labels": {
    "source": "partner-a",
    "region": "ap-southeast-1"
  }
}
```

Một value số trong cùng Map:

```json
{
  "labels": {
    "retryCount": 3
  }
}
```

không phù hợp với schema `additionalProperties: { type: string }`. Tuy nhiên, ứng dụng chỉ thực sự từ chối request nếu validation hoặc quá trình xử lý runtime có kiểm tra kiểu đó.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Map không có `additionalProperties` như mong đợi | Generic type bị mất, kiểu raw Map hoặc model converter không suy ra được | Khai báo generic cụ thể và kiểm tra schema sinh ra |
| `Map<String, String>` lại cho phép value tùy ý trong tài liệu | Metadata bị override hoặc annotation không đúng | Bổ sung schema value bằng `@Schema` và kiểm tra YAML |
| Field lạ bị bỏ qua dù muốn lưu lại | Chỉ dùng `@JsonIgnoreProperties(ignoreUnknown = true)` | Dùng `@JsonAnySetter` hoặc Map property rõ ràng |
| Field lạ xuất ra thành object con ngoài ý muốn | Dùng Map property thay vì `@JsonAnyGetter` hoặc ngược lại | Chọn cấu trúc JSON lồng hay thuộc tính cùng cấp rõ ràng |
| Schema cho phép field lạ nhưng server từ chối | Runtime Jackson/validator đóng chặt hơn hợp đồng | Đồng bộ cấu hình xử lý unknown property và schema |
| Schema cấm field lạ nhưng server vẫn nhận | `additionalProperties: false` chỉ là metadata tài liệu | Bật kiểm tra runtime phù hợp nếu API yêu cầu từ chối |
| Client generator tạo kiểu `Object` quá rộng | `additionalProperties: true` không có schema value | Dùng schema value cụ thể nếu nghiệp vụ cho phép |
| Swagger UI không hiển thị từng khóa động | Tên khóa không biết trước và schema dùng additional properties | Mô tả quy tắc, ví dụ và value schema; thử request thủ công |

## 14. Nguyên tắc thiết kế

- Dùng `Map<String, T>` khi tên khóa thay đổi nhưng kiểu value có thể xác định.
- Chỉ dùng `Map<String, Object>` hoặc `JsonNode` khi thực sự cần nhận cấu trúc JSON linh hoạt.
- Dùng `additionalProperties: true` cho vùng dữ liệu mở không có ràng buộc value; dùng schema cụ thể khi có thể giới hạn kiểu.
- Dùng `additionalProperties: false` cho object cần tập thuộc tính cố định và kiểm soát chặt.
- Đặt dữ liệu mở trong trường `metadata` hoặc `extensions` nếu chỉ một phần object cần mở rộng.
- Dùng `@JsonAnySetter` để thu nhận field chưa biết và `@JsonAnyGetter` để xuất Map thành thuộc tính cùng cấp.
- Phân biệt việc bỏ qua field lạ bằng `@JsonIgnoreProperties` với việc lưu field lạ bằng `@JsonAnySetter`.
- Không xem `additionalProperties` là bộ kiểm tra runtime; cần validator hoặc logic xử lý tương ứng.
- Cân nhắc tương thích OpenAPI 3.0/3.1 và công cụ tiêu thụ tài liệu.
- Kiểm tra schema được sinh, JSON serialize/deserialize và hành vi client sau mỗi thay đổi.

## Kết luận

`additionalProperties` mô tả chính sách cho các thuộc tính object không được liệt kê trong `properties`: cho phép mọi giá trị, cho phép với schema value cụ thể hoặc cấm hoàn toàn. Trong Spring Boot, Map và JsonNode biểu diễn dữ liệu động; Jackson `@JsonAnySetter`/`@JsonAnyGetter` điều khiển việc thu nhận và xuất các thuộc tính không khai báo; springdoc cùng `@Schema` mô tả chính sách đó trong hợp đồng OpenAPI. Hãy chọn mức độ mở phù hợp với nghiệp vụ, giữ hợp đồng đồng bộ với hành vi runtime và giới hạn vùng dữ liệu tự do để API vẫn có thể kiểm soát, kiểm thử và sử dụng ổn định.
