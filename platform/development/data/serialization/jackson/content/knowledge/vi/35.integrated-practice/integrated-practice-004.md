# Thiết kế cập nhật có phân biệt thuộc tính thiếu và null

Khi nhận một request cập nhật, ứng dụng thường cần biết client muốn làm gì với từng thuộc tính. Có ba trạng thái cơ bản:

1. Thuộc tính **không xuất hiện** trong JSON: client không yêu cầu thay đổi thuộc tính đó.
2. Thuộc tính xuất hiện với giá trị **`null`**: client chủ động gửi null; tùy hợp đồng, điều này có thể có nghĩa là xóa giá trị hiện tại hoặc từ chối cập nhật.
3. Thuộc tính xuất hiện với **giá trị cụ thể**: client yêu cầu thay thế giá trị hiện tại.

Ba trạng thái này không tương đương. Nếu DTO chỉ có một field Java thông thường, Jackson có thể để field đó là `null` khi property bị thiếu hoặc khi JSON gửi explicit `null`. Khi service không phân biệt được hai trường hợp, thao tác PATCH dễ vô tình xóa dữ liệu, bỏ qua yêu cầu xóa hoặc ghi đè giá trị bằng default không mong muốn.

Để thiết kế cập nhật chính xác, cần chọn rõ semantics của API, giữ được trạng thái presence trong DTO hoặc `JsonNode`, chuyển request thành một command thể hiện thao tác cụ thể rồi áp dụng vào domain/persistence. Jackson cung cấp nhiều cách biểu diễn presence; không có một annotation đơn lẻ tự định nghĩa đầy đủ semantics của PATCH.

Bài học dùng Jackson 2.x, Java 17, Spring Boot 3 và JUnit 5 trong ví dụ. Các API và thư viện bổ trợ có thể khác theo version của dự án.

## 1. Vì sao `null` và thiếu field phải được phân biệt?

Giả sử database đang lưu hồ sơ:

```json
{
  "id": 17,
  "displayName": "An Nguyen",
  "phone": "0900000001",
  "bio": "Backend developer"
}
```

Client gửi request cập nhật chỉ tên hiển thị:

```json
{
  "displayName": "An N."
}
```

`phone` và `bio` không xuất hiện. Thông thường, điều đó có nghĩa là giữ nguyên hai giá trị đang lưu.

Nếu client muốn xóa số điện thoại, request có thể là:

```json
{
  "phone": null
}
```

Ở đây `phone` xuất hiện và có giá trị null. Nếu hợp đồng cho phép xóa số điện thoại bằng null, service phải xóa giá trị cũ.

Nếu client gửi:

```json
{
  "phone": ""
}
```

đây là một trạng thái thứ tư: chuỗi rỗng. API phải quyết định chuỗi rỗng có được phép, có được trim thành null hay có nghĩa là một giá trị khác. Không nên tự động gộp absent, null và empty string.

| JSON request | Ý nghĩa thường gặp trong PATCH |
|---|---|
| Không có `phone` | Giữ nguyên số điện thoại hiện tại |
| `"phone": null` | Xóa số điện thoại, hoặc từ chối nếu field không nullable |
| `"phone": ""` | Đặt chuỗi rỗng nếu hợp đồng cho phép; có thể bị validation từ chối |
| `"phone": "0900000002"` | Thay bằng giá trị mới |

Đây là semantics do API định nghĩa. Một giao thức như JSON Merge Patch có quy tắc riêng cho null; một endpoint PATCH tùy biến có thể quy định khác. Hãy công bố quy tắc trước khi chọn cách binding.

## 2. Điều gì xảy ra với DTO Java thông thường?

DTO đơn giản:

```java
public class UpdateProfileRequest {
    private String displayName;
    private String phone;

    // getters và setters
}
```

Với JSON:

```json
{}
```

Jackson tạo object mà `displayName` và `phone` đều có thể là Java `null`.

Với JSON:

```json
{"phone": null}
```

`phone` cũng có thể là Java `null`. Nếu service chỉ kiểm tra:

```java
if (request.getPhone() == null) {
    // Không biết field bị thiếu hay client gửi null.
}
```

thì thông tin presence đã bị mất.

### 2.1. Primitive còn có vấn đề khác

Không dùng primitive để biểu diễn field PATCH có thể bị thiếu:

```java
public class UpdateSettingsRequest {
    private boolean notificationsEnabled;
    private int pageSize;
}
```

Khi field bị thiếu, primitive giữ giá trị mặc định `false` hoặc `0`. Service không biết client có chủ động yêu cầu tắt notification hoặc đặt page size bằng 0 hay không.

Đổi sang wrapper:

```java
public class UpdateSettingsRequest {
    private Boolean notificationsEnabled;
    private Integer pageSize;
}
```

Wrapper giúp phân biệt một số trường hợp thiếu/null với giá trị mặc định, nhưng vẫn chưa phân biệt được field thiếu và explicit null nếu cả hai cùng thành Java `null`. Muốn giữ đủ ba trạng thái, cần một biểu diễn presence riêng.

## 3. Chọn semantics của endpoint trước khi viết DTO

PATCH là một phương thức HTTP cho phép áp dụng một phần thay đổi lên resource, nhưng HTTP không bắt buộc mọi endpoint PATCH phải dùng cùng một định dạng patch document. Hai chuẩn phổ biến là JSON Merge Patch và JSON Patch; ngoài ra, ứng dụng có thể định nghĩa một request DTO partial-update riêng.

| Kiểu API | Cách biểu diễn thay đổi | Ý nghĩa null |
|---|---|---|
| DTO PATCH tùy biến | Field xuất hiện nghĩa là cập nhật | Do API tự quy định; có thể xóa hoặc từ chối |
| JSON Merge Patch | Object chỉ chứa member cần thay đổi | `null` yêu cầu xóa member khỏi target |
| JSON Patch | Mảng thao tác `add`, `remove`, `replace`, `test`, ... | Xóa được biểu diễn bằng operation `remove`; null là value nếu operation cho phép |

Đừng đặt `@PatchMapping` rồi mặc định cho rằng mọi null đều có nghĩa xóa. Hãy ghi rõ media type và semantics của endpoint.

## 4. Cách 1: dùng `JsonNode` để kiểm tra field presence

Khi request có cấu trúc linh hoạt hoặc cần phân biệt absent/null chính xác, `JsonNode` là cách trực tiếp. Jackson tree model giữ được sự khác nhau giữa:

- Field không tồn tại: `get(field)` trả Java `null`; `path(field)` trả `MissingNode`.
- Field tồn tại với JSON null: node là `NullNode`.
- Field tồn tại với value: node có kiểu string/number/boolean/object/array tương ứng.

Ví dụ:

```java
JsonNode body = mapper.readTree(json);

if (!body.has("phone")) {
    // Field không được gửi: giữ nguyên.
} else {
    JsonNode phoneNode = body.get("phone");
    if (phoneNode.isNull()) {
        // Field được gửi explicit null: xóa hoặc từ chối theo contract.
    } else if (phoneNode.isTextual()) {
        // Field được gửi với string value.
        String phone = phoneNode.textValue();
    } else {
        throw new InvalidPatchException("phone must be a string or null");
    }
}
```

`has("phone")` trả true khi field tồn tại kể cả khi value là JSON null. `hasNonNull("phone")` chỉ trả true nếu field tồn tại và không phải null. Do đó, không dùng `hasNonNull()` để kiểm tra presence nếu cần nhận diện explicit null.

### 4.1. Phân biệt `get()`, `path()`, `has()` và `hasNonNull()`

| API | Field thiếu | Field explicit null | Field có value |
|---|---|---|---|
| `get("x")` | Java `null` | `NullNode` | Node tương ứng |
| `path("x")` | `MissingNode` | `NullNode` | Node tương ứng |
| `has("x")` | `false` | `true` | `true` |
| `hasNonNull("x")` | `false` | `false` | `true` |

Ví dụ dùng `path()`:

```java
JsonNode value = body.path("phone");

if (value.isMissingNode()) {
    // Absent.
} else if (value.isNull()) {
    // Explicit JSON null.
} else {
    // Present value.
}
```

`path()` hữu ích vì không trả Java null khi field thiếu. Tuy nhiên, phải kiểm tra `isMissingNode()` trước khi gọi các accessor có thể trả default như `asText()` hoặc `asInt()`; nếu không, field thiếu có thể bị biến thành chuỗi rỗng hoặc số 0 mà không có lỗi.

### 4.2. Kiểm tra root và loại node

Một PATCH object thường yêu cầu root JSON là object:

```java
if (body == null || !body.isObject()) {
    throw new InvalidPatchException("Patch document must be a JSON object");
}
```

Sau đó, kiểm tra field allowlist và node type:

```java
Set<String> allowedFields = Set.of("displayName", "phone", "bio");

body.fieldNames().forEachRemaining(field -> {
    if (!allowedFields.contains(field)) {
        throw new InvalidPatchException("Unknown field: " + field);
    }
});
```

Không bind trực tiếp `JsonNode` tùy ý vào entity database. Tree model chỉ giữ cấu trúc JSON; nó không tự đảm bảo field được phép cập nhật, kiểu dữ liệu đúng hoặc caller có quyền thay đổi resource.

## 5. Chuyển `JsonNode` thành một patch command rõ nghĩa

Không nên để domain service nhận một `JsonNode` tùy ý và tự dò field. Tầng adapter có thể chuyển tree thành command thể hiện thao tác.

Ví dụ biểu diễn thao tác cho string:

```java
public sealed interface FieldChange<T>
        permits FieldChange.Unchanged, FieldChange.Clear, FieldChange.SetValue {

    record Unchanged<T>() implements FieldChange<T> {}
    record Clear<T>() implements FieldChange<T> {}
    record SetValue<T>(T value) implements FieldChange<T> {}

    static <T> FieldChange<T> unchanged() {
        return new Unchanged<>();
    }

    static <T> FieldChange<T> clear() {
        return new Clear<>();
    }

    static <T> FieldChange<T> set(T value) {
        return new SetValue<>(value);
    }
}
```

Command:

```java
public record UpdateProfileCommand(
        FieldChange<String> displayName,
        FieldChange<String> phone,
        FieldChange<String> bio) {
}
```

Mapper từ tree sang command:

```java
private FieldChange<String> readStringChange(JsonNode body, String field) {
    if (!body.has(field)) {
        return FieldChange.unchanged();
    }

    JsonNode node = body.get(field);
    if (node.isNull()) {
        return FieldChange.clear();
    }
    if (!node.isTextual()) {
        throw new InvalidPatchException(field + " must be a string or null");
    }

    return FieldChange.set(node.textValue());
}
```

Tạo command:

```java
UpdateProfileCommand command = new UpdateProfileCommand(
        readStringChange(body, "displayName"),
        readStringChange(body, "phone"),
        readStringChange(body, "bio"));
```

Domain service không cần biết JSON có field hay không. Nó nhận một trong ba thao tác: giữ nguyên, xóa hoặc đặt giá trị.

### 5.1. Áp dụng command vào aggregate

```java
public void apply(UpdateProfileCommand command) {
    applyDisplayName(command.displayName());
    applyPhone(command.phone());
    applyBio(command.bio());
}

private void applyDisplayName(FieldChange<String> change) {
    if (change instanceof FieldChange.Clear<?>) {
        throw new DomainValidationException("displayName cannot be cleared");
    }
    if (change instanceof FieldChange.SetValue<?> value) {
        rename((String) value.value());
    }
}

private void applyPhone(FieldChange<String> change) {
    if (change instanceof FieldChange.Clear<?>) {
        clearPhone();
    } else if (change instanceof FieldChange.SetValue<?> value) {
        setPhone((String) value.value());
    }
}

private void applyBio(FieldChange<String> change) {
    if (change instanceof FieldChange.Clear<?>) {
        clearBio();
    } else if (change instanceof FieldChange.SetValue<?> value) {
        setBio((String) value.value());
    }
}
```

Các `instanceof` pattern trong ví dụ hoạt động với Java 17 trở lên. Mục tiêu là domain xử lý thao tác rõ ràng và có thể từ chối clear cho field bắt buộc.

## 6. Cách 2: DTO setter có cờ đánh dấu presence

Với một DTO có cấu trúc cố định và class mutable, có thể giữ thêm cờ `provided`. Jackson không gọi setter cho property bị thiếu; khi property xuất hiện với null, setter được gọi theo null policy thông thường. Vì vậy setter có thể ghi nhận presence.

```java
public class UpdateProfileRequest {
    private boolean displayNameProvided;
    private String displayName;

    private boolean phoneProvided;
    private String phone;

    @JsonSetter(value = "displayName", nulls = Nulls.SET)
    public void setDisplayName(String displayName) {
        this.displayNameProvided = true;
        this.displayName = displayName;
    }

    @JsonSetter(value = "phone", nulls = Nulls.SET)
    public void setPhone(String phone) {
        this.phoneProvided = true;
        this.phone = phone;
    }

    public boolean isDisplayNameProvided() {
        return displayNameProvided;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isPhoneProvided() {
        return phoneProvided;
    }

    public String getPhone() {
        return phone;
    }
}
```

Khi đọc:

```java
UpdateProfileRequest request = mapper.readValue(json, UpdateProfileRequest.class);

if (!request.isPhoneProvided()) {
    // Không cập nhật phone.
} else if (request.getPhone() == null) {
    // Explicit null: xóa hoặc từ chối.
} else {
    // Set giá trị mới.
}
```

`Nulls.SET` thể hiện rằng explicit JSON null được chuyển thành Java null và setter được gọi. Nếu dùng `Nulls.SKIP`, Jackson có thể bỏ qua setter khi gặp null; cờ `provided` sẽ không được bật và explicit null bị gộp với absent. Chỉ dùng `SKIP` khi hợp đồng cố ý coi null như không gửi.

### 6.1. Ưu điểm và giới hạn của cờ presence

Ưu điểm:

- Không cần parse JSON hai lần.
- DTO giữ kiểu Java rõ ràng.
- Dễ tích hợp với controller `@RequestBody` và Bean Validation.
- Có thể phân biệt absent/null/value cho từng field.

Giới hạn:

- Cần một cờ cho mỗi field có semantics PATCH.
- Cần setter được Jackson gọi; field access trực tiếp hoặc creator-based binding có thể thay đổi hành vi.
- Cần cẩn thận với Lombok hoặc code generation để không tạo setter bỏ qua cờ.
- Cờ presence phải được khởi tạo mặc định `false` cho mỗi request object mới.
- Nếu DTO được tái sử dụng hoặc mutate sau binding, trạng thái cờ có thể trở nên khó hiểu.

Đây là cách phù hợp với DTO nhỏ, cố định. Với nhiều field hoặc API patch tổng quát, `JsonNode` hoặc wrapper tri-state có thể dễ quản lý hơn.

### 6.2. Vì sao record không tự giữ được presence?

Record có constructor canonical nhận tất cả component. Khi Jackson bind record, field bị thiếu và explicit null có thể cùng trở thành null nếu không có một component riêng thể hiện presence. Không có setter để đặt cờ như DTO mutable ở trên.

Nếu muốn dùng record cho PATCH, hãy dùng `JsonNullable<T>`, wrapper tri-state có deserializer phù hợp hoặc nhận `JsonNode` rồi chuyển sang record command. Không thêm boolean `provided` rồi giả định constructor tự biết field nào đã xuất hiện nếu không có cơ chế binding cụ thể để cung cấp thông tin đó.

## 7. Cách 3: dùng `JsonNullable<T>`

Thư viện `jackson-databind-nullable` của OpenAPI cung cấp `JsonNullable<T>` để biểu diễn một giá trị có thể chưa được gửi hoặc được gửi với null/value.

Dependency Maven (chọn version phù hợp với Jackson/Spring của dự án):

```xml
<dependency>
    <groupId>org.openapitools</groupId>
    <artifactId>jackson-databind-nullable</artifactId>
    <version>${jackson-databind-nullable.version}</version>
</dependency>
```

Đăng ký module:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JsonNullableModule());
```

DTO dạng bean đặt default là undefined để field bị thiếu giữ trạng thái chưa gửi:

```java
public class UpdateProfileRequest {
    private JsonNullable<String> displayName = JsonNullable.undefined();
    private JsonNullable<String> phone = JsonNullable.undefined();

    public JsonNullable<String> getDisplayName() {
        return displayName;
    }

    public void setDisplayName(JsonNullable<String> displayName) {
        this.displayName = displayName;
    }

    public JsonNullable<String> getPhone() {
        return phone;
    }

    public void setPhone(JsonNullable<String> phone) {
        this.phone = phone;
    }
}
```

Semantics:

| JSON | `JsonNullable<T>` |
|---|---|
| Field bị thiếu | `undefined()` / `isPresent() == false` |
| Field explicit null | Present với giá trị null |
| Field có value | Present với value |

Ví dụ xử lý:

```java
if (!request.getPhone().isPresent()) {
    // Không cập nhật.
} else if (request.getPhone().get() == null) {
    // Explicit null: xóa hoặc từ chối.
} else {
    // Giá trị mới.
    profile.setPhone(request.getPhone().get());
}
```

`JsonNullable` không giống `java.util.Optional`. `Optional.empty()` thường gộp absent và null; `JsonNullable` được thiết kế để giữ thêm trạng thái undefined. Hãy đăng ký `JsonNullableModule` và kiểm thử cả ba input trong đúng Jackson version. Với record, kiểm tra constructor/default semantics của thư viện đang dùng; nếu cần chắc chắn, dùng class có field khởi tạo `undefined()` hoặc một custom creator đã được test.

### 7.1. Không quên khởi tạo `undefined()`

Nếu field wrapper được khởi tạo thành Java `null`, một số đường binding có thể không giữ được trạng thái undefined như mong muốn. Dùng default `JsonNullable.undefined()` theo hướng dẫn thư viện.

Ví dụ:

```java
private JsonNullable<String> phone = JsonNullable.undefined();
```

Test phải chứng minh:

- `{}` cho wrapper undefined.
- `{"phone":null}` cho wrapper present-null.
- `{"phone":"0900000002"}` cho wrapper present-value.

Không chỉ test `isPresent()` với hai trường hợp; cần kiểm tra cả value null.

## 8. Cách 4: tự định nghĩa wrapper tri-state

Nếu không muốn thêm thư viện, có thể tạo kiểu dữ liệu nội bộ như `PatchField<T>`:

```java
public sealed interface PatchField<T>
        permits PatchField.Absent, PatchField.NullValue, PatchField.Value {

    record Absent<T>() implements PatchField<T> {}
    record NullValue<T>() implements PatchField<T> {}
    record Value<T>(T value) implements PatchField<T> {}
}
```

Tuy nhiên, để Jackson tự bind generic wrapper này, cần thiết kế deserializer/creator và null handling cẩn thận. Explicit JSON null thường đi qua null value provider thay vì `deserialize()`; custom deserializer cần override `getNullValue()` hoặc property null policy để tạo `NullValue`. Field bị thiếu thì Jackson không gọi setter/creator component theo cách tự động tạo `Absent` trừ khi DTO khởi tạo default hoặc creator có cơ chế presence.

Vì vậy, wrapper tự viết không tự giải quyết vấn đề. Nó chỉ có ích khi đã có binding adapter được kiểm thử. Với phần lớn ứng dụng, `JsonNode`, setter presence hoặc `JsonNullable<T>` là các lựa chọn đơn giản hơn.

## 9. `@JsonSetter` và null handling

Jackson cho phép điều khiển cách xử lý explicit null ở property bằng `@JsonSetter` và `Nulls`:

| `Nulls` | Hành vi tổng quát với explicit null |
|---|---|
| `SET` | Gán null thông qua setter/field/creator property theo binding path |
| `SKIP` | Bỏ qua giá trị null; thường không cập nhật property |
| `FAIL` | Báo lỗi khi input có null |
| `AS_EMPTY` | Dùng empty value do deserializer/type cung cấp |
| `DEFAULT` | Dùng null policy mặc định của mapper/property |

Ví dụ từ chối null:

```java
@JsonSetter(value = "displayName", nulls = Nulls.FAIL)
public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
```

Ví dụ bỏ qua explicit null:

```java
@JsonSetter(value = "phone", nulls = Nulls.SKIP)
public void setPhone(String phone) {
    this.phone = phone;
}
```

Lưu ý: `SKIP` có nghĩa là null không được áp dụng vào property; nó không tự cung cấp một cờ để service biết client đã gửi null. Nếu cần phân biệt absent và explicit null, không dùng `SKIP` trên property đó trừ khi null được định nghĩa giống absent.

`Nulls.AS_EMPTY` cũng làm thay đổi semantics: null có thể biến thành empty string, empty collection hoặc empty value của deserializer. Chỉ dùng khi contract yêu cầu chính xác hành vi đó; không dùng để tránh xử lý null ở service.

## 10. Phân biệt missing, null và empty trong các kiểu dữ liệu

Không chỉ string mới có vấn đề presence:

| Kiểu field | Absent | Explicit null | Empty/value đặc biệt |
|---|---|---|---|
| `String` | Không đổi | Xóa hoặc từ chối | `""` là chuỗi rỗng |
| `Integer` | Không đổi | Xóa hoặc từ chối | `0` là số 0 hợp lệ nếu contract cho phép |
| `Boolean` | Không đổi | Xóa hoặc từ chối | `false` là giá trị cụ thể |
| `List<T>` | Không đổi | Xóa list hoặc từ chối | `[]` là thay list thành rỗng |
| `Map<K,V>` | Không đổi | Xóa map hoặc từ chối | `{}` là map rỗng |
| Nested object | Không đổi | Xóa object hoặc từ chối | `{}` có thể là object patch rỗng |
| Date/time | Không đổi | Xóa hoặc từ chối | Một ngày cụ thể là value |

Đặc biệt, `false`, `0`, `[]` và `{}` không phải null. Không dùng điều kiện kiểu `if (value)` hoặc `if (list.isEmpty())` để quyết định field có được gửi hay không. Presence phải được lưu riêng.

## 11. Cập nhật nested object: thay thế hay merge?

Giả sử profile có địa chỉ:

```json
{
  "address": {
    "street": "1 Main Street",
    "city": "Hanoi",
    "postalCode": "100000"
  }
}
```

Client gửi:

```json
{
  "address": {
    "city": "Da Nang"
  }
}
```

Cần xác định semantics:

- **Replace:** thay toàn bộ address bằng object mới; `street` và `postalCode` bị bỏ hoặc thành null.
- **Merge:** chỉ cập nhật `city`, giữ `street` và `postalCode`.

Đây là quyết định của API. DTO thông thường deserialize `address` thành object mới không tự biết cần merge vào address hiện tại.

Với patch semantics, có thể dùng nested command:

```java
public record AddressPatch(
        FieldChange<String> street,
        FieldChange<String> city,
        FieldChange<String> postalCode) {
}

public record ProfilePatch(
        FieldChange<AddressPatch> address) {
}
```

Nếu `address` absent, giữ nguyên. Nếu null, xóa toàn bộ địa chỉ theo contract. Nếu object, merge từng field theo semantics riêng. Cách này rõ ràng nhưng cần code mapping và validation cho nested tree.

## 12. Collection trong PATCH: replace, append hay chỉnh từng phần tử?

Với collection, JSON:

```json
{"roles": []}
```

có thể có nghĩa là xóa toàn bộ role. Nhưng nếu field `roles` bị thiếu thì có nghĩa giữ nguyên. Nếu `roles` explicit null, API có thể từ chối hoặc xóa collection tùy contract.

Không mặc định rằng list trong PATCH sẽ được append. Phần lớn DTO binding thay collection bằng list được gửi lên. Nếu cần thêm/xóa phần tử riêng lẻ, thiết kế operation rõ ràng:

```json
{
  "addRoles": ["editor"],
  "removeRoles": ["viewer"]
}
```

Hoặc dùng JSON Patch path operation. Tránh suy diễn thao tác từ list rỗng hay null nếu contract không nói rõ.

## 13. JSON Merge Patch (RFC 7396)

JSON Merge Patch là một định dạng chuẩn cho partial update. Media type:

```http
Content-Type: application/merge-patch+json
```

Quy tắc cơ bản:

- Member không xuất hiện trong patch: giữ nguyên member trong target.
- Member xuất hiện với giá trị khác null: thêm hoặc thay giá trị.
- Member xuất hiện với null: xóa member khỏi target.
- Nếu value là object, merge đệ quy vào object tương ứng.
- Array được thay thế như một giá trị, không merge từng phần tử.

Target:

```json
{
  "name": "An",
  "phone": "0900000001",
  "address": {
    "city": "Hanoi",
    "street": "Main"
  },
  "roles": ["user", "editor"]
}
```

Merge patch:

```json
{
  "phone": null,
  "address": {
    "city": "Da Nang"
  },
  "roles": []
}
```

Kết quả theo RFC 7396:

```json
{
  "name": "An",
  "address": {
    "city": "Da Nang",
    "street": "Main"
  },
  "roles": []
}
```

`phone` bị xóa; `address.city` được thay nhưng `address.street` giữ nguyên; `roles` được thay bằng array rỗng.

### 13.1. Áp dụng Merge Patch bằng tree model

Có thể triển khai thuật toán merge trên `ObjectNode`:

```java
public ObjectNode applyMergePatch(ObjectNode target, ObjectNode patch) {
    ObjectNode result = target.deepCopy();

    patch.fields().forEachRemaining(entry -> {
        String field = entry.getKey();
        JsonNode patchValue = entry.getValue();

        if (patchValue.isNull()) {
            result.remove(field);
        } else if (patchValue.isObject()) {
            JsonNode current = result.get(field);
            ObjectNode currentObject = current != null && current.isObject()
                    ? (ObjectNode) current
                    : mapper.createObjectNode();

            result.set(field, applyMergePatch(
                    currentObject, (ObjectNode) patchValue));
        } else {
            result.set(field, patchValue.deepCopy());
        }
    });

    return result;
}
```

Đây là minh họa cho object target và object patch. Triển khai đầy đủ RFC cần xử lý trường hợp patch root không phải object: theo RFC 7396, patch không phải object thay thế toàn bộ target. Cũng cần xử lý target ban đầu không phải object, giới hạn depth/size và validate kết quả sau merge.

Sau khi merge, bind vào DTO/update model đã được allowlist:

```java
ObjectNode merged = applyMergePatch(currentTree, patchTree);
Profile replacement = mapper.treeToValue(merged, Profile.class);
```

Không bind kết quả trực tiếp vào entity nhạy cảm mà không kiểm tra field allowlist và authorization. Nếu target tree được tạo từ entity, chỉ serialize những field client được phép patch.

### 13.2. Merge Patch có một giới hạn về null

Trong JSON Merge Patch, null được dành cho thao tác xóa member. Do đó, nó không thể biểu diễn rõ yêu cầu “đặt member tồn tại thành JSON null” như một giá trị thông thường. Nếu domain cần lưu null như một giá trị có ý nghĩa khác với xóa, hãy chọn JSON Patch hoặc một DTO PATCH tùy biến có tri-state rõ ràng.

### 13.3. Không nhầm `@JsonMerge` với JSON Merge Patch

`@JsonMerge` là annotation của Jackson điều khiển cách Databind merge nội dung input vào giá trị property hiện có trong một số kiểu object/collection/map. Nó không tự triển khai toàn bộ RFC 7396:

- Không tự định nghĩa HTTP media type.
- Không tự cung cấp semantics cho mọi trường absent/null.
- Không tự xử lý root patch và member removal theo toàn bộ RFC.
- Hành vi merge có thể khác theo loại property và null handling.

Nếu API công bố `application/merge-patch+json`, hãy triển khai hoặc dùng thư viện có hành vi phù hợp RFC 7396 và test các case chuẩn. Không chỉ thêm `@JsonMerge` rồi tuyên bố endpoint là JSON Merge Patch.

## 14. JSON Patch (RFC 6902)

JSON Patch mô tả thay đổi dưới dạng danh sách operation. Media type:

```http
Content-Type: application/json-patch+json
```

Ví dụ:

```json
[
  {"op": "replace", "path": "/displayName", "value": "An N."},
  {"op": "remove", "path": "/phone"},
  {"op": "add", "path": "/roles/-", "value": "editor"}
]
```

Operation `remove` biểu diễn xóa field; không cần dùng null để mang ý nghĩa xóa. `replace` đặt value; `add` thêm value; `test` kiểm tra điều kiện; `move` và `copy` thao tác path.

JSON Patch hữu ích khi cần cập nhật chính xác một phần tử collection hoặc một path sâu. Đổi lại, API phải kiểm soát path được phép, operation hợp lệ, index, quyền trên từng field và thứ tự operation.

Không áp dụng một JSON Patch tùy ý lên entity hoặc object graph nhạy cảm. Một path như `/admin` hoặc `/ownerId` không được phép chỉ vì thư viện patch có thể cập nhật nó. Hãy dùng DTO/tree allowlist hoặc kiểm tra path trước khi apply.

## 15. Dùng `readerForUpdating()` có giải quyết absent/null không?

Jackson có API cập nhật một object đã tồn tại:

```java
mapper.readerForUpdating(existingProfile).readValue(json);
```

Với một bean mutable, property không xuất hiện thường không bị gán nên giá trị hiện tại có thể được giữ. Property xuất hiện với null có thể được gán null theo null policy. Cách này có thể hữu ích cho một số trường hợp update đơn giản.

Nhưng `readerForUpdating()` không tự định nghĩa đầy đủ contract PATCH:

- Không tự kiểm tra caller được phép cập nhật field nào.
- Không tự phân biệt mọi semantics absent/null/empty theo domain.
- Không tự đảm bảo nested object được merge như API mong muốn.
- Không tự cung cấp operation remove/add/test cho collection.
- Không tự áp dụng Bean Validation hoặc business invariants sau khi cập nhật.
- Có thể mutate object trước khi phát hiện lỗi ở field sau, tùy đường binding; không nên coi đó là transaction.

Nếu dùng API này, hãy test riêng object hiện tại trước/sau, null policy, nested merge, collection và failure behavior. Với aggregate cần invariant hoặc authorization, thường tốt hơn là parse thành patch command rồi áp dụng qua domain method.

## 16. Không dùng `@JsonMerge` như một cơ chế PATCH tổng quát

Ví dụ:

```java
public class Profile {
    @JsonMerge
    private Address address;
}
```

Annotation có thể yêu cầu Jackson merge input vào object `address` hiện có thay vì thay thế hoàn toàn property. Nó hữu ích trong một số cấu hình update/merge, nhưng không giải quyết mọi trạng thái:

- Field absent thường không có input để merge.
- Explicit null phụ thuộc null handling.
- Collection có semantics riêng.
- Xóa nested member không tự tương đương RFC 7396 trong mọi trường hợp.
- Business authorization và validation vẫn cần thực hiện riêng.

Hãy đọc tài liệu `@JsonMerge` của Jackson version đang dùng và viết test trên từng property type. Nếu contract là JSON Merge Patch, triển khai semantics RFC; nếu contract là merge bean nội bộ, ghi rõ cách null/collection được xử lý.

## 17. Áp dụng patch vào persistence một cách có kiểm soát

Sau khi chuyển request thành command, service có thể chỉ cập nhật field được gửi:

```java
@Transactional
public Profile updateProfile(UserId userId, UpdateProfileCommand command) {
    Profile profile = repository.findByUserId(userId)
            .orElseThrow(ProfileNotFoundException::new);

    profile.apply(command);

    return repository.save(profile);
}
```

Với JPA dirty checking, chỉ property thay đổi mới có thể được ghi theo cấu hình/entity mapping; tuy nhiên, không nên dựa vào SQL update behavior để quyết định semantics absent/null. Semantics phải được xử lý ở command/domain layer trước khi persistence.

### 17.1. Dynamic SQL update

Nếu dùng SQL/JDBC, tránh câu update luôn gán mọi cột từ DTO:

```sql
UPDATE profile
SET display_name = ?, phone = ?, bio = ?
WHERE id = ?
```

Nếu field absent bị chuyển thành null, câu lệnh này có thể xóa dữ liệu ngoài ý muốn. Có thể:

- Tạo câu SQL chỉ cập nhật cột được gửi.
- Dùng câu lệnh có cờ presence riêng cho từng field.
- Load entity, áp dụng command rồi lưu.

Ví dụ SQL có cờ:

```sql
UPDATE profile
SET phone = CASE WHEN :phoneProvided THEN :phone ELSE phone END,
    bio   = CASE WHEN :bioProvided   THEN :bio   ELSE bio   END
WHERE id = :id
```

Ở đây `phoneProvided = true` và `phone = NULL` có nghĩa là set null; `phoneProvided = false` có nghĩa giữ nguyên. Cách này thể hiện đúng tri-state nhưng cần binding boolean và null type chính xác theo JDBC/database.

Không dùng biểu thức `COALESCE(:phone, phone)` nếu explicit null phải xóa giá trị, vì COALESCE sẽ coi null như “giữ giá trị cũ” và làm mất thao tác clear.

### 17.2. Tránh cập nhật toàn bộ entity bằng dữ liệu không tin cậy

Không deserialize PATCH trực tiếp vào JPA entity rồi `save()` mà không kiểm soát field. Client có thể gửi `ownerId`, `role`, `status`, `createdAt` hoặc version field. DTO allowlist và domain method giúp tránh mass assignment.

## 18. Validation khi chỉ một số field xuất hiện

Validation cho create và update thường khác nhau. Với create, `displayName` có thể bắt buộc. Với PATCH, field không xuất hiện là hợp lệ vì không yêu cầu thay đổi; nhưng nếu field xuất hiện với chuỗi rỗng, có thể bị từ chối.

Không đặt `@NotNull` một cách máy móc trên mọi field của PATCH DTO, vì field absent có thể được xem là null sau binding và khiến request hợp lệ bị từ chối.

Có thể validate theo thao tác:

```java
if (request.isDisplayNameProvided()) {
    if (request.getDisplayName() == null || request.getDisplayName().isBlank()) {
        throw new RequestValidationException("displayName cannot be cleared or blank");
    }
}

if (request.isPhoneProvided() && request.getPhone() != null) {
    if (!PHONE_PATTERN.matcher(request.getPhone()).matches()) {
        throw new RequestValidationException("phone has invalid format");
    }
}
```

Validation chạy trên value được gửi, còn domain validation chạy sau khi áp dụng patch lên aggregate. Ví dụ, một field có thể hợp lệ riêng lẻ nhưng tổ hợp sau cập nhật không hợp lệ.

## 19. Validation sau khi merge vào trạng thái hiện tại

Một PATCH chỉ gửi `startDate` có thể làm ngày bắt đầu vượt quá `endDate` hiện tại. Validate riêng field mới chưa đủ.

Quy trình:

1. Load aggregate hiện tại.
2. Xác thực caller có quyền cập nhật aggregate.
3. Kiểm tra field allowlist và kiểu dữ liệu.
4. Áp dụng các thao tác patch vào aggregate/command.
5. Validate invariant trên trạng thái sau cập nhật.
6. Lưu trong transaction.

Ví dụ:

```java
booking.apply(patch);
booking.validateDateRange();
repository.save(booking);
```

Nếu validation thất bại, transaction phải rollback hoặc aggregate chưa được persist. Với object mutable được quản lý bởi persistence context, cần chú ý transaction rollback và trạng thái in-memory sau exception.

## 20. Nested validation và field bị xóa

Khi patch nested object, cần xác định validation dựa trên:

- Field được gửi và giá trị riêng lẻ.
- Object sau khi merge với trạng thái hiện tại.
- Invariant giữa parent và child.

Ví dụ client chỉ gửi `address.city`, service giữ `street` và `postalCode` hiện tại rồi validate địa chỉ hoàn chỉnh. Nếu client gửi `address: null` để xóa địa chỉ, domain có thể từ chối nếu profile yêu cầu địa chỉ bắt buộc.

Đừng validate một nested DTO partial như thể nó là object hoàn chỉnh. Một `AddressPatch` có thể hợp lệ dù `street` absent; sau khi áp dụng vào `Address` đầy đủ mới kiểm tra `street` có bắt buộc không.

## 21. Cập nhật nhiều field và tính atomic

Một patch document có thể thay đổi nhiều field. Nếu cập nhật một field thành công rồi field tiếp theo thất bại, resource không nên bị lưu ở trạng thái nửa chừng.

Thiết kế:

- Parse và kiểm tra toàn bộ cấu trúc trước khi mutate entity.
- Chuyển thành command bất biến.
- Kiểm tra authorization cho mọi field/operation cần thiết.
- Áp dụng thay đổi trong transaction.
- Validate invariant cuối cùng.
- Commit một lần.

Nếu custom patch handler mutate target trực tiếp trong lúc parse, lỗi ở field cuối có thể để lại object đã thay đổi một phần trong memory. Hãy parse patch thành command/tree trước rồi áp dụng sau khi binding thành công.

## 22. Concurrency: PATCH có thể ghi đè cập nhật của người khác

Giả sử hai client cùng đọc profile version 5:

- Client A cập nhật `phone`.
- Client B cập nhật `bio`.

Nếu mỗi client gửi toàn bộ object cũ và server thay thế resource, request đến sau có thể ghi đè thay đổi của request trước. PATCH giảm lượng field gửi lên nhưng không tự giải quyết lost update.

Có thể dùng optimistic locking với `@Version` trong JPA:

```java
@Entity
public class ProfileEntity {
    @Id
    private Long id;

    @Version
    private long version;

    // fields...
}
```

Hoặc dùng HTTP conditional request với ETag/`If-Match`. Server chỉ áp dụng patch nếu resource vẫn ở version mà client đã đọc; nếu không, trả `412 Precondition Failed` theo contract.

Không xem patch document là một thao tác atomic nếu service thực hiện nhiều update không có transaction/locking phù hợp.

## 23. Bảo vệ field allowlist và quyền cập nhật

Presence tracking không phải authorization. Client có thể gửi field tồn tại trong DTO nhưng không được phép thay đổi ở trạng thái hiện tại.

Ví dụ:

```json
{
  "displayName": "An",
  "role": "ADMIN",
  "ownerId": 999
}
```

Nếu DTO không có `role` hoặc `ownerId` và mapper bật strict unknown-property handling, request bị từ chối. Nếu contract cho phép unknown field bị bỏ qua, cần đảm bảo các field nhạy cảm không được bind qua một map mở.

Ngay cả field được phép patch cũng có thể cần authorization riêng. Ví dụ user được sửa `displayName` nhưng không được sửa `emailVerified`. Kiểm tra quyền trong application/domain service dựa trên actor đã xác thực, không dựa vào một field role do request gửi.

## 24. Spring MVC endpoint cho DTO PATCH tùy biến

Ví dụ controller nhận DTO có setter presence:

```java
@RestController
@RequestMapping("/profiles")
public class ProfileController {
    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @PatchMapping(path = "/me", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ProfileResponse patch(
            @Valid @RequestBody UpdateProfileRequest request,
            Principal principal) {
        return profileService.patch(principal.getName(), request);
    }
}
```

Ở đây endpoint định nghĩa PATCH tùy biến dùng `application/json`. Nếu muốn tuân theo JSON Merge Patch hoặc JSON Patch, hãy dùng media type tương ứng và implementation đúng chuẩn thay vì dùng DTO tùy biến nhưng công bố media type chuẩn.

`@Valid` không tự hiểu absent/null semantics. Các constraint cần được viết sao cho chỉ validate field được gửi, hoặc service/validator tùy chỉnh kiểm tra presence flag trước khi validate.

## 25. Spring MVC endpoint nhận JSON Merge Patch bằng `JsonNode`

```java
@PatchMapping(
        path = "/{id}",
        consumes = "application/merge-patch+json")
public ProfileResponse mergePatch(
        @PathVariable long id,
        @RequestBody JsonNode patch,
        Principal principal) {
    return profileService.applyMergePatch(id, principal.getName(), patch);
}
```

Service nên:

1. Load resource hiện tại.
2. Chuyển phần representation được phép patch thành tree.
3. Apply RFC 7396 semantics.
4. Kiểm tra field allowlist và authorization.
5. Bind kết quả vào update model/DTO.
6. Validate invariant và persist transactionally.

Không expose trực tiếp mọi property của entity trong tree. Có thể tạo `ProfilePatchDocument` hoặc tree representation chỉ chứa public fields.

## 26. Kiểm thử ba trạng thái với Jackson

Đây là bộ test tối thiểu cần có cho mỗi field partial-update:

| Input | Expected presence | Expected value/operation |
|---|---|---|
| `{}` | Absent | Unchanged |
| `{"phone":null}` | Present | Clear hoặc reject theo contract |
| `{"phone":"0900000002"}` | Present | Set value |
| `{"phone":""}` | Present | Empty string hoặc validation error |
| `{"phone":false}` | Present | Mapping/type error |
| `{"phone":[]}` | Present | Mapping/type error |

Không chỉ test một happy path có value. Lỗi PATCH thường xuất hiện ở explicit null, false/zero/empty và nested object.

## 27. Unit test cho DTO setter presence

```java
class UpdateProfileRequestTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void missingPhoneIsNotProvided() throws Exception {
        UpdateProfileRequest request = mapper.readValue("{}", UpdateProfileRequest.class);

        assertFalse(request.isPhoneProvided());
        assertNull(request.getPhone());
    }

    @Test
    void explicitNullPhoneIsProvidedAndNull() throws Exception {
        UpdateProfileRequest request = mapper.readValue(
                "{\"phone\":null}", UpdateProfileRequest.class);

        assertTrue(request.isPhoneProvided());
        assertNull(request.getPhone());
    }

    @Test
    void phoneValueIsProvided() throws Exception {
        UpdateProfileRequest request = mapper.readValue(
                "{\"phone\":\"0900000002\"}", UpdateProfileRequest.class);

        assertTrue(request.isPhoneProvided());
        assertEquals("0900000002", request.getPhone());
    }
}
```

Ba test này chứng minh cờ presence phân biệt được absent với explicit null. Nếu thay `Nulls.SET` bằng `Nulls.SKIP`, test explicit null sẽ thất bại theo đúng semantics khác.

## 28. Unit test cho `JsonNode`

```java
class PatchNodePresenceTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void distinguishesMissingAndExplicitNull() throws Exception {
        JsonNode missing = mapper.readTree("{}");
        JsonNode explicitNull = mapper.readTree("{\"phone\":null}");

        assertFalse(missing.has("phone"));
        assertTrue(explicitNull.has("phone"));
        assertFalse(explicitNull.hasNonNull("phone"));
        assertTrue(explicitNull.get("phone").isNull());
    }
}
```

Test thêm `false`, `0`, `[]` và `{}` để bảo đảm code không nhầm các value falsy/empty với absent.

## 29. Unit test cho `JsonNullable`

Khi dùng `JsonNullableModule`, test cả ba trạng thái:

```java
@Test
void preservesUndefinedNullAndValue() throws Exception {
    ObjectMapper mapper = new ObjectMapper()
            .registerModule(new JsonNullableModule());

    UpdateProfileRequest absent = mapper.readValue("{}", UpdateProfileRequest.class);
    UpdateProfileRequest explicitNull = mapper.readValue(
            "{\"phone\":null}", UpdateProfileRequest.class);
    UpdateProfileRequest value = mapper.readValue(
            "{\"phone\":\"0900000002\"}", UpdateProfileRequest.class);

    assertFalse(absent.getPhone().isPresent());
    assertTrue(explicitNull.getPhone().isPresent());
    assertNull(explicitNull.getPhone().get());
    assertTrue(value.getPhone().isPresent());
    assertEquals("0900000002", value.getPhone().get());
}
```

DTO bean trong ví dụ khởi tạo `JsonNullable.undefined()` và cho Jackson bind qua setter. Hãy xác nhận module version đang dùng giữ đúng semantics trên constructor mặc định/setter path bằng ba test này; không để field wrapper mặc định là Java null.

## 30. Test service: absent giữ nguyên, null xóa, value thay thế

```java
@Test
void appliesPatchAccordingToPresence() {
    Profile profile = new Profile("An", "0900000001", "Backend developer");

    UpdateProfileCommand command = new UpdateProfileCommand(
            FieldChange.unchanged(),
            FieldChange.clear(),
            FieldChange.set("Platform engineer"));

    profile.apply(command);

    assertEquals("An", profile.getDisplayName());
    assertNull(profile.getPhone());
    assertEquals("Platform engineer", profile.getBio());
}
```

Test domain không cần Jackson. Nó xác nhận command được áp dụng đúng và tách biệt transport mapping với domain behavior.

## 31. Integration test qua HTTP

Unit test mapper không chứng minh Spring controller, converter và validation hoạt động đúng. Dùng `MockMvc`/`WebTestClient` kiểm tra:

- PATCH không gửi field giữ nguyên giá trị hiện tại.
- PATCH gửi null xóa field nullable.
- PATCH gửi null vào field bắt buộc trả lỗi validation.
- PATCH gửi empty string theo policy.
- Sai token type trả 400.
- Unknown field bị từ chối hoặc bỏ qua đúng contract.
- Request media type không phù hợp trả 415.
- Caller không có quyền cập nhật field bị từ chối.
- Concurrent update xử lý ETag/version đúng.

Ví dụ:

```java
mockMvc.perform(patch("/profiles/me")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"phone\":null}"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.phone").doesNotExist());
```

Assertion response phụ thuộc output contract. Nếu API trả property với null thay vì bỏ property, dùng assertion `isEmptyOrNullString()` hoặc parse JSON tree để kiểm tra chính xác semantics.

## 32. Test JSON Merge Patch theo RFC 7396

Test các trường hợp:

1. Patch object rỗng không thay đổi target.
2. Field absent giữ nguyên.
3. Field null bị xóa.
4. Object nested merge đệ quy.
5. Array thay thế toàn bộ.
6. Value scalar thay thế target.
7. Patch root không phải object thay thế target theo RFC.
8. Target field không tồn tại được thêm khi patch có value.
9. Unknown/protected path bị từ chối ở lớp policy ứng dụng.

Ví dụ test nested:

```java
@Test
void mergePatchKeepsUnmentionedNestedMembers() throws Exception {
    ObjectNode target = (ObjectNode) mapper.readTree("""
            {"address":{"city":"Hanoi","street":"Main"}}
            """);
    ObjectNode patch = (ObjectNode) mapper.readTree("""
            {"address":{"city":"Da Nang"}}
            """);

    ObjectNode result = applyMergePatch(target, patch);

    assertEquals("Da Nang", result.path("address").path("city").asText());
    assertEquals("Main", result.path("address").path("street").asText());
}
```

Nếu dùng thư viện merge patch thay vì tự viết, hãy chạy bộ test tương đương và kiểm tra edge cases của implementation.

## 33. Test JSON Patch operation và path allowlist

Với JSON Patch, kiểm tra:

- `replace` path tồn tại và value đúng kiểu.
- `remove` chỉ được áp dụng cho field có thể xóa.
- `add` không thêm field quản trị.
- `move`/`copy` không vượt phạm vi resource được phép.
- `test` được đánh giá đúng.
- Path escape/pointer token được decode đúng.
- Operation count và document size có giới hạn.
- Operation thất bại không để resource ở trạng thái cập nhật một phần.

Đặc biệt, path là dữ liệu do client gửi. Dùng allowlist hoặc policy theo actor/resource; không cho phép cập nhật mọi JSON Pointer chỉ vì patch library có thể thực thi.

## 34. Tránh dùng `@JsonInclude` để giải quyết input presence

`@JsonInclude` điều khiển property có được ghi ra JSON khi serialize hay không. Ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
private String phone;
```

Điều này có thể khiến output bỏ field phone khi Java value là null. Nó không tạo ra trạng thái absent/null khi deserialize.

Nếu response cần thể hiện rõ field đã bị xóa hoặc không được phép xem, thiết kế response DTO/representation riêng. Không dùng output inclusion policy để suy ra request presence.

## 35. Tránh gộp absent và null qua default/coercion

Một số cấu hình có thể làm explicit null bị bỏ qua, đổi thành empty hoặc gán default. Ví dụ:

- `Nulls.SKIP` bỏ qua setter khi input null.
- `Nulls.AS_EMPTY` dùng empty value.
- Primitive có thể giữ `0`/`false` khi field thiếu.
- Custom setter có thể tự thay null thành default.
- `@JsonSetter(defaultValue = "...")` hoặc custom creator có thể thêm default semantics.

Những lựa chọn này có thể phù hợp với một số DTO, nhưng phải được xem là một phần của hợp đồng. Nếu PATCH cần ba trạng thái, đừng để cấu hình gộp chúng trước khi application layer có thể phân biệt.

## 36. Lỗi thường gặp khi thiết kế PATCH

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng DTO field nullable thông thường | Absent và explicit null cùng thành Java null | Presence flag, JsonNode hoặc JsonNullable |
| Dùng primitive cho field tùy chọn | Absent thành `0`/`false` | Dùng wrapper và giữ presence riêng |
| Dùng `hasNonNull()` để kiểm tra field có gửi | Explicit null bị xem như absent | Dùng `has()` hoặc `isMissingNode()` |
| Dùng `Nulls.SKIP` nhưng mong nhận biết null | Setter không chạy, presence flag không được bật | Dùng `Nulls.SET` hoặc policy phù hợp |
| Coi empty string/list là absent | Mất yêu cầu xóa/thay rỗng | Kiểm tra presence độc lập với value |
| Deserialize thẳng vào entity | Mass assignment và ghi đè field nhạy cảm | DTO allowlist và command |
| Gọi `readerForUpdating()` và coi đó là RFC PATCH | Thiếu semantics remove/nested/authorization | Định nghĩa protocol và test đầy đủ |
| Dùng `@JsonMerge` như JSON Merge Patch | Hành vi null/array/root không khớp RFC | Implement/dùng RFC 7396 đúng chuẩn |
| Validate partial DTO như create DTO | Field absent bị từ chối hoặc invariant bị bỏ sót | Validate field được gửi và state sau merge |
| Cập nhật entity trong lúc parse | Lỗi giữa chừng để lại state một phần | Parse command trước, apply transaction sau |
| Dùng `COALESCE` để giữ cột cũ | Không thể biểu diễn explicit null để xóa | Presence flag trong SQL hoặc update động |
| Không có optimistic locking | Lost update khi nhiều client PATCH đồng thời | Version/ETag/If-Match |
| Không kiểm tra path JSON Patch | Có thể sửa field ngoài quyền | Path allowlist và authorization |

## 37. Quy trình triển khai một endpoint PATCH

1. Chọn semantics: DTO tùy biến, JSON Merge Patch hay JSON Patch.
2. Chọn media type đúng với semantics đã công bố.
3. Liệt kê field được phép cập nhật và field không được phép.
4. Định nghĩa ý nghĩa của absent, null, empty, zero, false và empty collection.
5. Chọn cách giữ presence: `JsonNode`, setter flag, `JsonNullable` hoặc wrapper đã có binding.
6. Parse và kiểm tra kiểu/field allowlist trước khi thay đổi entity.
7. Chuyển thành command bất biến mô tả unchanged/clear/set hoặc operation tương đương.
8. Xác thực actor và quyền trên từng resource/field cần thiết.
9. Áp dụng patch trong transaction, không mutate khi còn đang parse.
10. Validate field và invariant trên trạng thái sau cập nhật.
11. Persist với optimistic locking/ETag nếu cần.
12. Trả response theo output contract độc lập với input null policy.
13. Test absent/null/value/empty, nested, collection, error, authorization và concurrency.

## 38. Checklist kiểm thử

- [ ] `{}` không làm thay đổi field nào.
- [ ] Explicit null được phân biệt với absent.
- [ ] Value mới được áp dụng đúng.
- [ ] Empty string/list/object có semantics được xác định.
- [ ] `false` và `0` không bị coi là absent.
- [ ] Sai JSON token type bị từ chối.
- [ ] Unknown/protected field được xử lý theo allowlist.
- [ ] Nested object có semantics replace hoặc merge rõ ràng.
- [ ] Collection có semantics replace/append/remove rõ ràng.
- [ ] Field bắt buộc không bị xóa trái phép.
- [ ] Validation chạy trên state sau patch.
- [ ] Lỗi giữa chừng không lưu state một phần.
- [ ] `readerForUpdating()`/`@JsonMerge` nếu dùng đã được test theo từng type.
- [ ] JSON Merge Patch tuân theo RFC 7396 nếu endpoint công bố media type đó.
- [ ] JSON Patch kiểm soát operation và path.
- [ ] Authorization và mass assignment được kiểm tra.
- [ ] Concurrency được bảo vệ bằng version/ETag khi cần.
- [ ] Response serialization không làm mất semantics cần trả về.

## 39. Ghi nhớ

Một request cập nhật cần giữ được khác biệt giữa thuộc tính không được gửi, thuộc tính được gửi với null và thuộc tính được gửi với value. DTO nullable thông thường thường không giữ đủ ba trạng thái; primitive còn có thể biến field thiếu thành `0` hoặc `false`. Có thể dùng `JsonNode` với `has()`/`isMissingNode()`/`isNull()`, DTO setter có cờ presence và `@JsonSetter(nulls = Nulls.SET)`, hoặc `JsonNullable<T>` đã đăng ký module.

Sau binding, hãy chuyển dữ liệu thành patch command rõ nghĩa rồi áp dụng qua domain service trong transaction. Phân biệt DTO PATCH tùy biến với JSON Merge Patch và JSON Patch; `@JsonMerge` hay `readerForUpdating()` không tự triển khai toàn bộ semantics của các chuẩn đó. Kiểm tra field allowlist, authorization, nested/collection behavior, invariant sau cập nhật và optimistic locking. Khi presence, null policy và thao tác cập nhật được định nghĩa tường minh, API tránh được việc xóa hoặc ghi đè dữ liệu ngoài ý muốn.
