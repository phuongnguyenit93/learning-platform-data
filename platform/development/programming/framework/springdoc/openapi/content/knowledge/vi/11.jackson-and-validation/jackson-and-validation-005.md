# Khả năng nhận `null` trong Java khác với thuộc tính thiếu trong JSON

Trong request JSON, một thuộc tính không xuất hiện và một thuộc tính xuất hiện với giá trị `null` là hai trạng thái khác nhau. Ví dụ, `{"name":"An"}` không giống `{"name":"An","nickname":null}`. Tuy nhiên, sau khi Jackson chuyển JSON thành một đối tượng Java, hai trạng thái này có thể cùng trở thành giá trị `null` trong một field wrapper hoặc cùng giữ giá trị mặc định trong một field primitive. Nếu không chủ động phân biệt, ứng dụng có thể cập nhật dữ liệu sai, áp dụng validation không đúng hoặc công bố hợp đồng OpenAPI gây hiểu nhầm.

Với `springdoc-openapi`, cần mô tả riêng việc thuộc tính có bắt buộc xuất hiện hay không và liệu giá trị `null` có được chấp nhận hay không. Hai khái niệm này tương ứng với `required` và `nullable` trong OpenAPI 3.0, hoặc kiểu union có `null` trong OpenAPI 3.1. Jackson quyết định cách deserialize JSON; Bean Validation kiểm tra trạng thái đối tượng sau binding; OpenAPI mô tả hợp đồng cho client. Ba lớp này phải được thiết kế nhất quán.

## 1. Thuộc tính thiếu và thuộc tính có giá trị `null`

Xét hai request:

```json
{
  "name": "Nguyen Van A"
}
```

```json
{
  "name": "Nguyen Van A",
  "nickname": null
}
```

Ở request thứ nhất, thuộc tính `nickname` không có trong object JSON. Ở request thứ hai, thuộc tính có mặt và giá trị của nó là `null`.

Sự khác nhau này thường mang ý nghĩa nghiệp vụ:

- **Thiếu thuộc tính:** client không gửi thông tin cho trường đó. Server có thể giữ nguyên giá trị hiện tại, dùng giá trị mặc định hoặc áp dụng quy tắc riêng.
- **Thuộc tính bằng `null`:** client gửi tín hiệu rõ ràng rằng giá trị là null. Với API cập nhật, điều này có thể có nghĩa là xóa giá trị hiện tại hoặc đặt trường về trạng thái rỗng.
- **Thuộc tính có giá trị cụ thể:** client gửi giá trị mới để tạo hoặc cập nhật.

Ví dụ với API cập nhật hồ sơ:

| JSON gửi lên | Ý nghĩa có thể được API quy định |
|---|---|
| Không có `phoneNumber` | Giữ số điện thoại hiện tại |
| `"phoneNumber": null` | Xóa số điện thoại đã lưu |
| `"phoneNumber": "0900000000"` | Đổi sang số mới |

Đây là quy ước API cần được thiết kế và công bố. JSON và Jackson không tự quyết định rằng `null` luôn có nghĩa là xóa hoặc thuộc tính thiếu luôn có nghĩa là giữ nguyên.

## 2. JSON phân biệt sự hiện diện với giá trị

Một object JSON là tập hợp các cặp tên và giá trị. Với một tên thuộc tính, có thể xảy ra ít nhất ba trạng thái:

1. Thuộc tính không xuất hiện.
2. Thuộc tính xuất hiện với giá trị `null`.
3. Thuộc tính xuất hiện với một giá trị khác `null`.

Ví dụ:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": "An"}
```

JSON không có từ khóa `undefined` để biểu diễn một thuộc tính thiếu. Trong JavaScript, thuộc tính có giá trị `undefined` khi serialize bằng `JSON.stringify` thường bị loại khỏi object; thuộc tính có giá trị `null` vẫn được giữ trong JSON. Khi đọc request ở server, chỉ hai dạng JSON cuối cùng là dữ liệu được truyền trên đường dây: không có key và có key với null.

## 3. Điều gì xảy ra khi Jackson deserialize vào Java?

Jackson ánh xạ JSON vào field, setter, constructor hoặc creator parameter. Kết quả phụ thuộc kiểu Java, cách tạo đối tượng và cấu hình mapper.

### Field wrapper và thuộc tính thiếu

Với wrapper như `Integer`, `Boolean` hoặc `String`, giá trị ban đầu thường là `null` nếu không có initializer. Khi thuộc tính không xuất hiện, Jackson không cần gán giá trị cho property đó; field giữ trạng thái ban đầu của đối tượng. Nếu trạng thái ban đầu là null, kết quả sau binding cũng là null.

```java
public class UserRequest {
    private String name;
    private Integer age;
    private Boolean active;

    // getters và setters
}
```

Với request `{}` trong ví dụ trên, `age` và `active` thường là `null`. Với request `{"age":null}`, Jackson cũng đặt `age` thành `null` theo hành vi mặc định cho wrapper.

### Field primitive và thuộc tính thiếu

Primitive Java không thể chứa null:

| Primitive | Giá trị mặc định của field nếu không được gán |
|---|---:|
| `boolean` | `false` |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | `\u0000` |

Ví dụ:

```java
public class SettingsRequest {
    private boolean enabled;
    private int retryCount;

    // getters và setters
}
```

Nếu request không chứa `enabled` và `retryCount`, các field primitive vẫn có giá trị mặc định `false` và `0`. Ứng dụng không thể biết từ các giá trị này rằng client đã gửi `false`/`0` hay đã bỏ qua thuộc tính.

Với thuộc tính JSON hiện diện và có `null`, Jackson thường không thể gán null vào primitive. Kết quả cụ thể có thể là dùng giá trị mặc định, bỏ qua hoặc ném lỗi tùy cấu hình coercion và xử lý null của Jackson. Không nên dựa vào hành vi mặc định này để xác định quy tắc nghiệp vụ; hãy dùng wrapper hoặc cấu hình rõ ràng nếu null cần được phát hiện.

## 4. Field initializer, constructor và record làm thay đổi kết quả

Khi một thuộc tính không xuất hiện, Jackson không nhất thiết ghi đè giá trị đã được khởi tạo trong đối tượng. Ví dụ:

```java
public class SearchRequest {
    private int page = 1;
    private int size = 20;
    private String sort = "createdAt,desc";

    // getters và setters
}
```

Nếu Jackson tạo đối tượng bằng constructor không tham số rồi chỉ gán các property có trong JSON, thuộc tính bị thiếu có thể giữ initializer (`page = 1`, `size = 20`). Nếu request gửi `{"page":null}`, kết quả phụ thuộc kiểu đích và cấu hình xử lý null; với primitive, Jackson có thể từ chối hoặc áp dụng cấu hình coercion.

Với constructor/creator parameter, record hoặc immutable DTO, việc thiếu thuộc tính có thể được xử lý khác với bean có setter. Jackson phải tạo giá trị cho constructor parameter; giá trị mặc định, `@JsonProperty(required = true)`, cấu hình creator và phiên bản Jackson có thể ảnh hưởng kết quả.

Ví dụ record:

```java
public record CreateUserRequest(
        String name,
        Integer age
) {}
```

Record không có field mutable để Jackson bỏ qua setter. Jackson gọi canonical constructor với các giá trị đã giải mã. Nếu `age` không xuất hiện, giá trị được truyền vào phụ thuộc cách Jackson xử lý creator property thiếu; nếu cần bắt buộc, hãy mô tả rõ bằng validation/metadata và kiểm tra bằng phiên bản thư viện thực tế.

Không nên suy ra quy tắc required chỉ từ việc field Java là primitive, wrapper, có initializer hay nằm trong record. Hãy xác định hành vi của DTO được dùng và kiểm thử deserialization.

## 5. Bảng so sánh trạng thái JSON và Java

Bảng dưới đây mô tả trường hợp bean mutable đơn giản có constructor không tham số, không có initializer và Jackson mặc định cho kiểu tương ứng:

| Kiểu Java | JSON thiếu thuộc tính | JSON có thuộc tính `null` | JSON có giá trị |
|---|---|---|---|
| `String` | `null` | `null` | Chuỗi được gán |
| `Integer` | `null` | `null` | Số nguyên được gán |
| `Boolean` | `null` | `null` | Boolean được gán |
| `int` | `0` | Tùy cấu hình; có thể lỗi hoặc dùng mặc định | Số nguyên được gán |
| `boolean` | `false` | Tùy cấu hình; có thể lỗi hoặc dùng mặc định | Boolean được gán |
| `List<String>` | `null` | `null` theo mặc định | Danh sách được gán |
| `Map<String, Object>` | `null` | `null` theo mặc định | Map được gán |

Đây không phải bảng bảo đảm cho mọi DTO. Initializer, constructor, creator property, `@JsonSetter`, custom deserializer và cấu hình `ObjectMapper` có thể thay đổi kết quả.

Điểm cốt lõi: nếu thiếu và null cùng trở thành một giá trị Java, ứng dụng đã mất thông tin về việc client có gửi key hay không. Khi nghiệp vụ cần phân biệt, phải giữ lại thông tin presence hoặc dùng một kiểu biểu diễn có trạng thái rõ ràng.

## 6. `required` và `nullable` trong OpenAPI

OpenAPI mô tả hai câu hỏi độc lập:

- Thuộc tính có bắt buộc phải xuất hiện trong object hay không?
- Nếu xuất hiện, thuộc tính có được phép mang giá trị null hay không?

### OpenAPI 3.0

Trong OpenAPI 3.0, danh sách `required` nằm ở cấp object; `nullable: true` được dùng để cho phép null cho schema có khai báo `type`.

```yaml
type: object
required:
  - name
properties:
  name:
    type: string
    nullable: false
  nickname:
    type: string
    nullable: true
  description:
    type: string
```

Diễn giải:

- `name` phải xuất hiện và không được null.
- `nickname` có thể bị thiếu; nếu xuất hiện thì có thể là null.
- `description` có thể bị thiếu; schema không đánh dấu cho phép null.

Vì vậy, `required: true` không có nghĩa là non-null trong mọi trường hợp, và `nullable: true` không có nghĩa là thuộc tính bắt buộc xuất hiện.

### OpenAPI 3.1

OpenAPI 3.1 sử dụng mô hình JSON Schema hiện đại hơn. Một schema cho phép chuỗi hoặc null có thể dùng union type:

```yaml
type: object
required:
  - name
properties:
  name:
    type: string
  nickname:
    type:
      - string
      - 'null'
```

Ở đây, `nickname` vẫn có thể bị thiếu vì không nằm trong `required`; nếu xuất hiện, giá trị có thể là chuỗi hoặc null. Không trộn `nullable: true` theo cách OpenAPI 3.0 với cú pháp union type 3.1 khi công cụ và phiên bản đặc tả chưa hỗ trợ tương ứng.

## 7. Bean Validation không tự phân biệt thiếu với null

Bean Validation kiểm tra giá trị của đối tượng sau khi binding. Với một thuộc tính wrapper, nếu JSON thiếu và nếu JSON gửi null đều khiến field trở thành null, constraint như `@NotNull` sẽ nhìn thấy cùng một trạng thái.

```java
public class CreateUserRequest {
    @NotNull
    private Integer age;

    // getters và setters
}
```

`@NotNull` yêu cầu giá trị Java không null sau binding. Nó không cho biết nguyên nhân null là do client bỏ qua thuộc tính hay chủ động gửi `"age": null`.

Các constraint phổ biến cũng có phạm vi riêng:

| Constraint | Kiểm tra |
|---|---|
| `@NotNull` | Giá trị Java không null |
| `@NotBlank` | Chuỗi không null, không rỗng và có ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi/collection/map không null và không rỗng |
| `@Positive` | Số lớn hơn 0; null thường được xem là hợp lệ bởi constraint này |
| `@Size` | Kích thước trong khoảng quy định; null thường được xem là hợp lệ |

Nếu yêu cầu là “key phải xuất hiện trong JSON”, `@NotNull` chỉ đủ khi cả trạng thái thiếu lẫn null đều bị từ chối. Nếu cần phân biệt “không được gửi” với “gửi null để xóa”, validation trên field cuối cùng không đủ; cần giữ thông tin presence trước khi chuyển thành DTO thông thường.

## 8. Kiểm soát null bằng Jackson `@JsonSetter`

Jackson có annotation `@JsonSetter` với thuộc tính `nulls` để quy định cách xử lý khi thuộc tính xuất hiện với giá trị null. Các chế độ thường dùng:

| Chế độ | Hành vi với JSON null |
|---|---|
| `Nulls.SET` | Gán null vào property theo cách thông thường |
| `Nulls.SKIP` | Bỏ qua giá trị null, không gọi setter/không cập nhật property |
| `Nulls.FAIL` | Ném lỗi khi gặp null |
| `Nulls.AS_EMPTY` | Chuyển null thành giá trị rỗng theo kiểu đích nếu kiểu hỗ trợ |
| `Nulls.DEFAULT` | Dùng hành vi mặc định/cấu hình của Jackson |

Ví dụ bỏ qua null:

```java
public class UpdateProfileRequest {
    private String displayName;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phoneNumber;

    // getters và setters
}
```

Với cấu hình tương ứng, khi request có `"phoneNumber": null`, Jackson bỏ qua thao tác gán và giữ giá trị hiện tại của field/đối tượng. Điều này có thể hữu ích cho API cập nhật một phần, nhưng cần hiểu rằng null không còn được dùng để xóa giá trị.

Ví dụ từ chối null:

```java
public class CreateUserRequest {
    @JsonSetter(nulls = Nulls.FAIL)
    private String name;

    // getters và setters
}
```

Khi JSON có `"name": null`, Jackson ném lỗi binding. Thuộc tính bị thiếu vẫn là một tình huống khác; nếu cần bắt buộc key phải xuất hiện, cần kết hợp creator requirement, validation hoặc kiểm tra presence.

`Nulls.AS_EMPTY` có ý nghĩa phụ thuộc kiểu đích và serializer/deserializer. Ví dụ với collection, null có thể trở thành collection rỗng; với một số kiểu khác, “empty value” có thể là giá trị mặc định riêng. Hãy kiểm tra hành vi cụ thể thay vì giả định tất cả đều thành chuỗi rỗng.

## 9. Dùng wrapper, initializer và validation theo mục đích

### Wrapper khi cần phát hiện null

Nếu cần biết client không cung cấp giá trị hay cung cấp một giá trị số, dùng `Integer` thay vì `int` để tránh trạng thái mặc định `0` làm mất thông tin.

```java
public class UpdateSettingsRequest {
    private Boolean enabled;
    private Integer retryCount;

    // getters và setters
}
```

Nhưng wrapper chỉ giúp biểu diễn null; nó không tự phân biệt key thiếu và key có null. Với bean không initializer, cả hai thường thành null.

### Initializer cho giá trị mặc định

```java
public class SearchRequest {
    private Integer page = 0;
    private Integer size = 20;

    // getters và setters
}
```

Khi thuộc tính bị thiếu và Jackson tạo bean thông thường, initializer có thể được giữ lại. Nếu client gửi null, hành vi có thể khác. Nếu API muốn dùng giá trị mặc định khi thiếu nhưng từ chối null tường minh, cần cấu hình null handling hoặc validation phù hợp.

### Validation cho giá trị sau binding

```java
public class CreateOrderRequest {
    @NotNull
    @Positive
    private Integer quantity;

    // getters và setters
}
```

`@NotNull` bảo đảm `quantity` không null sau binding; `@Positive` bảo đảm số dương. Nếu thuộc tính thiếu hoặc null đều dẫn đến null, cả hai trường hợp bị `@NotNull` từ chối. Đây thường là điều phù hợp với request tạo mới.

## 10. PATCH và nhu cầu biểu diễn ba trạng thái

API PATCH thường cần phân biệt ba trạng thái:

1. Không gửi thuộc tính: giữ nguyên giá trị hiện tại.
2. Gửi thuộc tính với null: xóa hoặc đặt giá trị về null.
3. Gửi thuộc tính với giá trị: cập nhật sang giá trị mới.

Một DTO Java thông thường với wrapper nullable thường không giữ được khác biệt giữa trường hợp 1 và 2 sau deserialize. Ví dụ:

```java
public class UpdateUserRequest {
    private String displayName;
    private String phoneNumber;

    // getters và setters
}
```

Sau khi bind, `phoneNumber == null` có thể có nghĩa là client không gửi key hoặc gửi key với null. Nếu tầng service phải phân biệt, có thể chọn một trong các cách sau:

- Dùng JSON Merge Patch (`application/merge-patch+json`) và triển khai semantics của nó một cách nhất quán; trong JSON Merge Patch, null thường biểu thị xóa thành viên.
- Nhận request dưới dạng `JsonNode` hoặc `ObjectNode`, kiểm tra `has("phoneNumber")` và `isNull()` trước khi ánh xạ sang model nghiệp vụ.
- Dùng wrapper kiểu `JsonNullable<T>` (ví dụ thư viện OpenAPITools) để biểu diễn trạng thái undefined, present-null và present-value, nếu hệ sinh thái dự án hỗ trợ.
- Viết custom deserializer hoặc kiểu patch field riêng để giữ lại presence.

Ví dụ kiểm tra bằng `JsonNode`:

```java
@PatchMapping("/{id}")
UserResponse update(
        @PathVariable UUID id,
        @RequestBody JsonNode body) {

    if (!body.has("phoneNumber")) {
        // Không cập nhật số điện thoại.
    } else if (body.get("phoneNumber").isNull()) {
        // Xóa số điện thoại.
    } else {
        String phone = body.get("phoneNumber").asText();
        // Cập nhật số điện thoại.
    }

    return userService.updateFromPatch(id, body);
}
```

Đoạn mã minh họa việc phân biệt presence; trong ứng dụng thực tế cần kiểm tra kiểu node, xử lý giá trị sai định dạng và tránh truy cập null ngoài dự kiến. Nếu dùng JSON Merge Patch, cần công bố đúng media type và semantics trong OpenAPI.

## 11. Mô tả `required` và nullable bằng springdoc-openapi

Springdoc tạo schema từ DTO, Jackson metadata và Bean Validation. Các annotation thường gặp gồm:

- `@NotNull`, `@NotBlank`, `@NotEmpty` để biểu đạt constraint không null/rỗng.
- `@Schema(nullable = true)` trong các phiên bản annotation/OpenAPI tương thích để mô tả khả năng null theo OpenAPI 3.0.
- `@Schema(requiredMode = Schema.RequiredMode.REQUIRED)` hoặc `NOT_REQUIRED` để điều chỉnh yêu cầu xuất hiện của thuộc tính khi cần.
- `@JsonSetter(nulls = ...)` để điều khiển runtime Jackson; đây không phải annotation thay thế `required` trong OpenAPI.

Ví dụ:

```java
public class ProfileRequest {

    @Schema(
        description = "Tên hiển thị, bắt buộc và không null",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    private String displayName;

    @Schema(
        description = "Tên gọi thân mật; có thể là null",
        nullable = true,
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    private String nickname;

    // getters và setters
}
```

Đây là ví dụ metadata; schema thực tế còn phụ thuộc phiên bản OpenAPI, springdoc, Swagger Annotations và cách tích hợp Bean Validation. Với OpenAPI 3.1, cần xác minh cách phiên bản thư viện biểu diễn null theo JSON Schema 3.1 thay vì mặc định rằng `nullable: true` luôn xuất ra đúng cú pháp mong muốn.

### `@JsonProperty(required = true)` không phải giải pháp tổng quát cho mọi bean

Jackson có thuộc tính `required` trên `@JsonProperty`, nhưng ý nghĩa kiểm tra bắt buộc chủ yếu gắn với creator property trong các trường hợp hỗ trợ. Đặt annotation lên field/setter của mutable bean không phải cách đáng tin cậy để thay thế Bean Validation hoặc kiểm tra presence trong mọi tình huống.

Để mô tả hợp đồng OpenAPI, dùng metadata schema phù hợp. Để kiểm tra request khi chạy, dùng validation, creator configuration, `@JsonSetter` hoặc logic kiểm tra presence tương ứng.

## 12. Ví dụ so sánh ba trạng thái khi cập nhật

Giả sử hồ sơ hiện tại có `nickname = "An"`. API muốn giữ nguyên khi thiếu key, xóa khi null và thay đổi khi có chuỗi.

| Request body | Trạng thái sau binding bằng DTO wrapper thông thường | Ý nghĩa PATCH mong muốn |
|---|---|---|
| `{}` | `nickname == null` | Giữ nguyên `"An"` |
| `{"nickname": null}` | `nickname == null` | Xóa, đặt null |
| `{"nickname": "Bình"}` | `nickname == "Bình"` | Đổi thành `"Bình"` |

Hai dòng đầu cho cùng giá trị Java nếu dùng bean wrapper đơn giản. Vì thế service không thể quyết định chính xác nếu chỉ kiểm tra `request.getNickname() == null`.

Nếu dùng `JsonNode`, có thể xác định trạng thái:

```java
if (!body.has("nickname")) {
    // Giữ nguyên
} else if (body.get("nickname").isNull()) {
    // Xóa giá trị
} else {
    // Cập nhật bằng giá trị được gửi
}
```

Đối với API PUT thay thế toàn bộ tài nguyên, quy tắc thường khác PATCH: các field cần thiết của representation mới phải được gửi đầy đủ; field không gửi có thể bị xem là thiếu dữ liệu hoặc nhận giá trị mặc định theo hợp đồng. Hãy mô tả rõ semantics của từng method thay vì dùng chung một DTO với quy tắc không xác định.

## 13. Kiểm tra sự nhất quán giữa Jackson, Validation và OpenAPI

Khi thiết kế một thuộc tính, nên kiểm tra riêng bốn lớp:

| Lớp | Câu hỏi cần trả lời |
|---|---|
| JSON contract | Key có bắt buộc xuất hiện không? Có cho phép null không? |
| Jackson | Khi key thiếu hoặc null, field/constructor nhận giá trị gì? Có lỗi hay bị bỏ qua không? |
| Bean Validation | Constraint kiểm tra trạng thái nào sau binding? Có phân biệt presence không? |
| OpenAPI | `required`, nullable/type union, default và ví dụ có mô tả đúng quy tắc không? |

Quy trình kiểm tra:

1. Viết các JSON mẫu: key thiếu, key null, key có giá trị hợp lệ và key sai kiểu.
2. Deserialize bằng đúng `ObjectMapper` đang được Spring Boot sử dụng.
3. Ghi nhận giá trị Java sau binding, kể cả field initializer và constructor default.
4. Chạy Bean Validation và xác nhận constraint nào thất bại.
5. Kiểm tra status code cùng error response thực tế của endpoint.
6. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và kiểm tra `required`, `nullable` hoặc union type tương ứng.
7. Thử Swagger UI/client generator nếu chúng được dùng để bảo đảm công cụ hiểu đúng hợp đồng.

Nên có integration test cho các trạng thái thiếu/null/value khi endpoint có semantics khác nhau giữa chúng, đặc biệt với PATCH và các trường có giá trị mặc định.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không phân biệt được thiếu và null | Cả hai cùng trở thành null trong wrapper field | Giữ presence bằng `JsonNode`, `JsonNullable` hoặc custom deserializer |
| Giá trị thiếu thành `0` hoặc `false` | Dùng primitive Java | Dùng wrapper nếu cần phát hiện null hoặc trạng thái chưa cung cấp |
| Gửi null nhưng field vẫn giữ giá trị cũ | Dùng `@JsonSetter(nulls = SKIP)` hoặc custom handling | Xác định semantics và chọn `SET`, `SKIP`, `FAIL` phù hợp |
| Gửi null gây lỗi deserialize | Primitive hoặc `Nulls.FAIL`/coercion config | Dùng wrapper hoặc mô tả rõ quy tắc từ chối null |
| `@NotNull` không phân biệt key thiếu với key null | Validation chỉ nhìn giá trị sau binding | Kiểm tra presence trước binding hoặc dùng kiểu giữ trạng thái |
| OpenAPI đánh dấu required nhưng client gửi null vẫn được | Required chỉ kiểm tra sự hiện diện, schema vẫn nullable hoặc runtime không kiểm tra | Điều chỉnh nullable và validation tương ứng |
| OpenAPI không đánh dấu nullable dù Java dùng wrapper | Wrapper không tự xác định toàn bộ hợp đồng nullable | Bổ sung `@Schema` và kiểm tra phiên bản OpenAPI |
| Giá trị mặc định không được áp dụng | Constructor/initializer và creator binding khác dự kiến | Kiểm thử với JSON thiếu và cấu hình Jackson thực tế |
| PATCH vô tình xóa dữ liệu | DTO không giữ sự khác nhau giữa missing và null | Dùng patch representation có presence rõ ràng |

## 15. Nguyên tắc thiết kế

- Xem thuộc tính thiếu, null và có giá trị là ba trạng thái riêng trong hợp đồng khi nghiệp vụ cần phân biệt.
- Dùng primitive khi giá trị mặc định là hợp lệ và không cần biết client có gửi field hay không.
- Dùng wrapper khi cần biểu diễn null, nhưng nhớ rằng wrapper đơn thuần không giữ presence.
- Dùng `@NotNull` để kiểm tra giá trị sau binding; không coi nó là bộ kiểm tra sự hiện diện của key JSON.
- Dùng `@JsonSetter(nulls = ...)` để quy định cách xử lý explicit null, không nhầm với hành vi khi thuộc tính thiếu.
- Dùng `required` để mô tả sự hiện diện và nullable/type union để mô tả khả năng nhận null trong OpenAPI.
- Kiểm tra cách Jackson xử lý bean, creator, record, initializer và primitive bằng đúng cấu hình runtime.
- Với PATCH, dùng representation có thể phân biệt missing, null và value nếu semantics cần ba trạng thái.
- Tách DTO request/response hoặc DTO create/update khi yêu cầu field và validation khác nhau.
- Kiểm tra schema được springdoc sinh cùng request thực tế và kết quả validation.

## Kết luận

JSON phân biệt thuộc tính không xuất hiện với thuộc tính xuất hiện có giá trị null, nhưng quá trình Jackson deserialize vào một field Java có thể làm mất khác biệt đó. Primitive còn có giá trị mặc định như `0` hoặc `false`; wrapper thường nhận null cho cả trường hợp thiếu và explicit null nếu không có initializer hay cấu hình khác. Bean Validation kiểm tra giá trị sau binding, còn OpenAPI dùng `required` và nullable để mô tả hai khía cạnh độc lập. Với API cập nhật một phần, hãy giữ thông tin presence khi cần phân biệt giữ nguyên, xóa và cập nhật; đồng thời kiểm tra metadata springdoc, hành vi Jackson và validation để hợp đồng khớp với runtime.
