# Đối tượng con, khóa Map và chỉ số collection ngoài dự kiến trong Spring Data Binding

## 1. Tình huống: một biểu mẫu hợp lệ có thể chứa tên field nguy hiểm

Một API Spring MVC nhận các field của biểu mẫu tạo vận đơn:

```http
POST /api/shipments/form
Content-Type: application/x-www-form-urlencoded

reference=SHP-001&
contact.email=mai@example.com&
addresses[0].city=Ha+Noi&
labels[color]=blue
```

Các tên field thể hiện cả ba kiểu property path:

- `contact.email`: thuộc tính `email` của **đối tượng con** `contact`.
- `addresses[0].city`: thuộc tính `city` của phần tử thứ 0 trong **List** `addresses`.
- `labels[color]`: giá trị ứng với khóa `color` trong **Map** `labels`.

Nếu model object còn có các trường không được phép sửa, client có thể tự thêm:

```text
approved=true
contact.admin=true
ownerId=someone-else
labels[role]=administrator
labels[internal_note]=change-approval
addresses[999999].city=Unexpected
addresses[2].city=Extra
```

**Không có gì buộc client chỉ gửi những input mà giao diện HTML hiển thị.** Một request tự tạo có thể gửi tên property lồng nhau, khóa Map không có trên form, hoặc chỉ số collection rất lớn. Nếu binding policy quá rộng, ứng dụng có thể gặp **mass assignment / over-posting**, làm thay đổi object graph ngoài ý định hoặc tốn tài nguyên khi tự phát triển List/nested objects.

**Bài học này tập trung vào an toàn dữ liệu của Spring MVC `WebDataBinder`:**
1. Bean property paths và cách Spring diễn giải nested object, List, Map.
2. Nguy cơ khi bind trực tiếp domain entity hoặc dùng wildcard quá rộng.
3. Allowlist chính xác qua `setAllowedFields(...)` và xác minh `getSuppressedFields()`.
4. `setAutoGrowNestedPaths`, `setAutoGrowCollectionLimit` và giới hạn chúng **không** bảo vệ được.
5. Jakarta Validation cho nested object/container và vì sao validation không thay binding policy.
6. Constructor binding / `setDeclarativeBinding(true)` và giới hạn của allowlist.
7. Sự khác biệt với `@RequestBody`/Jackson, bảo vệ server-owned fields.
8. Ví dụ **Java 17 + Spring Boot 3.5.6 + MockMvc** có test chặn key, index, nested field bất ngờ.

Ngữ cảnh module: **Spring Framework — validation/data-binding**, nhóm **An toàn dữ liệu**. Ví dụ chính dùng Spring MVC Servlet stack và `@ModelAttribute`; không đồng nhất mọi kết luận về argument resolvers với WebFlux hoặc JSON.

## 2. Tên field từ HTTP được diễn giải như thế nào?

Với DTO Java:

```java
public class ShipmentForm {
    private Contact contact;
    private List<Address> addresses = new ArrayList<>();
    private Map<String, String> labels = new LinkedHashMap<>();
    // getters/setters
}
```

Spring `WebDataBinder` có thể xử lý property paths thông qua bean property access, type conversion và nested path navigation.

| Request field | Ý nghĩa về dữ liệu | Nguy cơ cần xét |
| --- | --- | --- |
| `contact.email` | Gán `email` vào object `contact` | Có thể tạo object con nếu null |
| `contact.admin` | Gán property `admin` trong object con | Leo vào trạng thái không thuộc form |
| `addresses[0].city` | Gán `city` của phần tử List tại 0 | Auto-grow object/collection |
| `addresses[2].city` | Gán phần tử ngoài hai vị trí dự kiến | Vượt giới hạn nghiệp vụ của form |
| `addresses[999999].city` | Thử chỉ số cực lớn | Lỗi binding/chi phí bộ nhớ nếu policy thiếu |
| `labels[color]` | Map key `color` | Key hợp lệ theo nghiệp vụ |
| `labels[role]` | Map key `role` | Thêm metadata/role không được phép |
| `ownerId` | Setter trực tiếp field server-owned | Mass assignment |
| `approved` | Setter trạng thái phê duyệt | Vượt quyền nếu không kiểm soát |

### 2.1. Property path là giao diện do client điều khiển

Trong `@ModelAttribute` form/query binding, tên parameter do client gửi đóng vai trò **đường dẫn property**. Với một đối tượng bean mutable và setter public, Spring có thể gán giá trị ở nhiều tầng.

Mẫu sai lầm phổ biến:

```java
@PostMapping("/edit")
public String edit(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "ok";
}
```

Đây là **anti-pattern minh họa**, chưa có định nghĩa `AccountEntity` hay `repository`. Một JPA entity có thể chứa `id`, `role`, `enabled`, `owner` hoặc collection quan hệ; bind trực tiếp vào entity rồi save dễ cho phép client tác động lên field không được phê duyệt.

**Ưu tiên:** một request DTO/command object chỉ chứa dữ liệu có thể nhập, sau đó service tự tìm entity thật, kiểm tra quyền và map **từng thuộc tính được phép**.

### 2.2. Key Map không nhất thiết tương ứng tên property của bean

Đối với:

```java
private Map<String, String> labels = new LinkedHashMap<>();
```

`labels[color]` thường ghi entry với key `"color"`, còn `labels[role]` thử ghi một entry khác trong cùng Map. Việc Map có thể nhận key tùy ý không có nghĩa **mọi key đều thuộc hợp đồng API**.

Map có thể chứa cấu hình, thẻ phân loại, metadata hoặc các quyền đặc biệt. Nếu nghiệp vụ chỉ cho phép `color` và `tier`, cần ràng buộc key **trước hoặc trong binding**, không chỉ mong người dùng tự tuân thủ form.

### 2.3. List index là đầu vào có thể gây mở rộng object graph

Một path `addresses[1].city` có thể yêu cầu binder:
1. Truy cập bean `addresses`.
2. Bảo đảm List có phần tử tại index 1.
3. Tạo `Address` nếu binder được cấu hình auto-grow và type có thể khởi tạo.
4. Chuyển String rồi gán property `city`.

Vì thế chỉ số `999999` không chỉ là “giá trị sai về nghiệp vụ”; nếu cấu hình binding quá rộng và không giới hạn, nó có thể tạo áp lực tài nguyên hoặc exception trước khi Bean Validation chạy.

Các phiên bản Spring `DataBinder` có giới hạn auto-grow mặc định (thường 256 phần tử), nhưng **mặc định không thay thế chính sách field, request size và mức tài nguyên của ứng dụng**.

## 3. Nguyên tắc số một: DTO riêng, không bind thẳng entity

Thiết kế an toàn hơn:

```java
public record CreateShipmentCommand(
        String reference,
        String contactEmail,
        List<String> cities,
        Map<String, String> labels) {
}
```

Service nhận command sau khi validation và kiểm tra authorization:

```java
Shipment shipment = shipmentRepository.findById(id)
        .orElseThrow(...);

// Chỉ map trường client có quyền điều chỉnh.
shipment.changeReference(command.reference());
shipment.changeContactEmail(command.contactEmail());

// approved/ownerId/role lấy từ server và authorization.
```

Đây là **fragment minh họa** (giả định service, repository và domain methods tồn tại). Nguyên tắc là **không** dùng `BeanUtils.copyProperties(input, entity)` hoặc tự động map mọi field từ request một cách không kiểm soát.

Thứ tự an toàn:
1. Xác định input contract.
2. Chặn những property paths/key/index không được phép.
3. Chuyển kiểu dữ liệu.
4. Validate cấu trúc/nội dung.
5. Kiểm tra authorization và business invariants trong service.
6. Chỉ ghi các thuộc tính được phép vào model/domain.

Việc DTO có field `approved` trong project demo bên dưới là **cố ý để chứng minh rủi ro**. Ứng dụng thật nên **loại field server-owned khỏi input DTO hoàn toàn**, không chỉ chặn bằng binder.

## 4. `setAllowedFields`: positive allowlist cho property binding

Spring khuyến nghị khai báo rõ những fields được property-bind:

```java
@InitBinder("shipmentForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields(
            "reference",
            "contact.email",
            "addresses[0].city",
            "addresses[1].city",
            "labels[color]",
            "labels[tier]");
}
```

Ý nghĩa:
- `reference` hợp lệ.
- `contact.email` hợp lệ nhưng `contact.admin` không.
- Chỉ có `addresses[0].city` và `addresses[1].city` được phép qua setter/property binding.
- Chỉ có hai key `labels[color]` và `labels[tier]`; `labels[role]` không được phép.
- `approved` và `ownerId` không có trong danh sách nên bị chặn.

Đây là allowlist **trên tên đường dẫn property** khi binding, không phải danh sách những field mà provider Jakarta Validation sẽ kiểm tra.

### 4.1. Allowed fields hỗ trợ pattern, nhưng nên dùng càng hẹp càng tốt

Spring hỗ trợ simple wildcard matching cho allowed field patterns. Ví dụ:

```java
binder.setAllowedFields("addresses[*].city");
```

có thể cho phép nhiều index khác nhau; `*` là wildcard trong pattern. Nếu form chỉ có hai địa chỉ, pattern rộng này **không phù hợp** bằng kê khai hai index cụ thể.

Tương tự:

```java
binder.setAllowedFields("labels[*]");
```

có thể chấp nhận các Map key ngoài nghiệp vụ. Không dùng wildcard ở đoạn nhạy cảm chỉ vì nó ngắn hơn.

**Khuyến nghị:** các field path mang ý nghĩa đặc quyền, tiền, quyền, role, ID, owner, approval cần bị loại khỏi request DTO và được kiểm soát ở service. Allowlist là một lớp phòng vệ bổ sung.

### 4.2. So sánh `setAllowedFields` với `setDisallowedFields`

| API | Nguyên tắc | Rủi ro |
| --- | --- | --- |
| `setAllowedFields(...)` | Mặc định không cho property bind ngoài tập đã cho | Phải duy trì danh sách mỗi khi hợp đồng thay đổi |
| `setDisallowedFields(...)` | Mặc định cho property bind, trừ những tên đã cấm | Trường mới có thể được bind mà chưa ai nhớ blacklist |
| `setDeclarativeBinding(true)` | Ưu tiên constructor binding; setter binding chỉ khi allowedFields được cấu hình | Không chặn constructor arguments sai ý định |
| DTO immutable chỉ chứa input public | Giới hạn các field ngay trong cấu trúc dữ liệu | Cần mapping rõ vào domain entity |

Spring reference lưu ý `allowedFields` patterns **phân biệt chữ hoa/thường**, `disallowedFields` patterns được xử lý **không phân biệt hoa/thường**. Vì security, allowlist thường tốt hơn denylist.

### 4.3. Canonical property names và ký hiệu khóa có dấu nháy

Spring có bước chuẩn hóa một số dạng property path, ví dụ bracket-quoted map keys. Vì vậy:
- Việc một key trong URL xuất hiện dưới dạng `labels[color]` hay có dấu nháy không mặc nhiên tạo ra một namespace bảo mật khác.
- Không tự viết kiểm tra whitelist bằng chuỗi thô của URL rồi giả định nó tương đương cách `WebDataBinder` canonicalize field names.
- Hãy dùng chính sách của binder cho property binding, và test các biến thể input framework chấp nhận.

Tên field sau khi canonicalize có thể khác cách nó xuất hiện nguyên văn trong request; với test security, ưu tiên kiểm tra **giá trị thực sự được bind** và danh sách field bị suppress, thay vì khẳng định mọi biến thể cú pháp được xử lý giống nhau.

## 5. Phát hiện field bị chặn: `getSuppressedFields()`

Khi client gửi một tên field không nằm trong allowlist, Spring `DataBinder` có thể **suppress** field đó khỏi property binding và ghi tên vào `BindingResult`.

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("shipmentForm") ShipmentForm form,
        BindingResult errors) {

    String[] suppressed = errors.getSuppressedFields();

    if (suppressed.length > 0) {
        return ResponseEntity.badRequest().build();
    }

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
```

Đoạn này là fragment; class project đầy đủ nằm ở phần 12.

**Điểm then chốt:** `errors.hasErrors()` **không bắt buộc trả true chỉ vì có suppressed fields**. Suppression là thông tin về policy của binder, không luôn là `FieldError` do validator tạo ra. Do đó nếu muốn **từ chối** request có field ngoài hợp đồng, phải kiểm tra `getSuppressedFields()` **riêng**.

Phản hồi public có thể là:

```json
{"code":"UNEXPECTED_FIELD","suppressedCount":2}
```

Demo chỉ trả **số lượng** suppressed, không phản chiếu nguyên tên field do client tự chọn. Ở logging nội bộ, cũng nên hạn chế length/cardinality của những tên lạ và không ghi kèm raw PII.

### 5.1. Bị suppress khác với unknown field và constraint violation

| Loại | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| Suppressed vì không được phép | `labels[role]` ngoài allowlist | `BindingResult.getSuppressedFields()` |
| Unknown property | `unknownField` không tồn tại trên bean | Binder ignore/reject theo cấu hình; với allowlist hẹp cũng có thể bị suppress |
| Sai kiểu | `addresses[0].number=abc` với field Integer được cho phép | Type conversion/binding error |
| Sai Jakarta constraint | `addresses[0].city=""` | `@NotBlank` sau khi bind |
| List index vượt giới hạn | `addresses[999999].city` | Có thể bị suppress trước, hoặc lỗi property access/auto-grow tùy policy |
| Map key không hợp nghiệp vụ | `labels[role]` | Allowlist hoặc validation/key policy riêng |

Không dùng `@Valid` để “cấm các field dư” nếu chúng đã bị binder bỏ qua hoặc không thuộc DTO. Bean Validation kiểm tra **object sau binding**, không phải mọi raw tên field mà client đã gửi.

### 5.2. Thứ tự xử lý lỗi của endpoint

Trong project đầy đủ, controller kiểm tra:

```text
if suppressed fields not empty:
    HTTP 400, code UNEXPECTED_FIELD
else if BindingResult contains errors:
    HTTP 400, code INVALID_FORM
else:
    HTTP 200, mapped safe response
```

Đây là policy có chủ đích: khi có **field bị chặn**, request bị từ chối ngay cả khi các field hợp lệ khác có lỗi validation. Các ứng dụng khác có thể trả nhiều loại lỗi cùng lúc, nhưng phải xác định thứ tự và test rõ. Không bao giờ cho field bị chặn lọt vào domain write.

## 6. Hai cấu hình auto-grow: khác vai trò và giới hạn

### 6.1. `setAutoGrowNestedPaths(boolean)`

```java
binder.setAutoGrowNestedPaths(true);
```

Cho phép binder tự tạo object/collection trung gian ở một số property paths nếu có thể khởi tạo:

```text
contact == null
  + request contact.email="mai@example.com"
  => tạo Contact rồi gán email (khi phù hợp)
```

Nó giúp form đơn giản hơn vì không bắt buộc tự tạo mọi nested object trước binding. Tuy nhiên nó cũng có thể mở rộng object graph ngoài ý định nếu field names không được giới hạn.

Nếu tắt:

```java
binder.setAutoGrowNestedPaths(false);
```

binder không còn tự khởi tạo các property trung gian theo cùng cách. Nếu form cần `contact.email`, bạn có thể **khởi tạo sẵn** `contact = new Contact()` trong DTO, hoặc thiết kế constructor binding/DTO khác. Tắt auto-grow không phải biện pháp duy nhất để chặn mass assignment.

### 6.2. `setAutoGrowCollectionLimit(int)`

```java
binder.setAutoGrowCollectionLimit(4);
```

Dùng để giới hạn số phần tử tự mở rộng trong **array/List** khi binder gặp indexed property paths. Ví dụ giới hạn 4 giúp ngăn yêu cầu tự tạo đến index hàng nghìn, trong trường hợp data binder vẫn cho phép một pattern index rộng.

**Không hiểu sai:**
- Nó **không** có nghĩa mọi List luôn chứa tối đa 4 phần tử bất kể nguồn tạo; nó giới hạn cơ chế **auto-grow khi binding**.
- Nó **không** là giới hạn chung cho số lượng **Map entries** khi attacker gửi các map keys khác nhau.
- Nó **không** tự giới hạn kích thước HTTP body, số lượng request parameters, độ dài từng chuỗi hoặc chi phí của converter.
- Nó **không** bảo đảm một index vượt cap chỉ đơn giản được ghi vào `BindingResult`; tùy đường binder/config có thể có exception và cần handler/test.

Dùng đồng thời:
1. **Allowlist** cho đúng index được nghiệp vụ cho phép.
2. **Auto-grow collection limit** như một lớp chặn phụ.
3. **HTTP/request limits** trên server/container/proxy.
4. **Bean Validation** cho số phần tử sau binding.
5. **Business validation** cho số lượng/thứ tự liên quan đến user/tenant.

### 6.3. Ví dụ index lớn bị chặn trước khi auto-grow

Với allowlist:

```java
binder.setAllowedFields(
        "addresses[0].city",
        "addresses[1].city");
binder.setAutoGrowCollectionLimit(4);
```

request `addresses[999999].city=Rogue` không khớp allowlist và có thể bị **suppress** trước khi binder cố tự mở List. Trong ví dụ hoàn chỉnh, test xác nhận:
- `addresses[999999].city` có trong suppressed fields.
- List chỉ chứa các phần tử thực sự được cho phép và gửi.
- API trả `UNEXPECTED_FIELD`, không lưu dữ liệu ngoài hợp đồng.

Nếu dùng `addresses[*].city` thay cho hai index cụ thể, allowlist không còn chặn index tùy ý; lúc đó chỉ còn auto-grow limit và các lớp còn lại, khiến behavior khó kiểm soát hơn.

## 7. Map key: whitelist, giới hạn số phần tử và “metadata nguy hiểm”

### 7.1. Dùng key chính xác

Nếu hợp đồng chỉ có hai thẻ:

```text
labels[color]
labels[tier]
```

thì allowlist nên ghi đúng:

```java
binder.setAllowedFields(
        "labels[color]",
        "labels[tier]");
```

Request với `labels[role]`, `labels[isAdmin]`, `labels[tenantId]` hoặc `labels[discount]` không nên được bind chỉ vì property `labels` là một `Map<String,String>`.

Một Map mở rộng là **trường dữ liệu do caller kiểm soát**; nếu cho key tùy ý, phải có:
- Quy tắc key name được phép và phạm vi dành riêng cho server.
- Giới hạn số entry và độ dài key/value từ trước hoặc trong quá trình decode.
- Chính sách xử lý duplicate keys và canonicalization.
- Schema/validation riêng cho value type.
- Authorization khi key có ý nghĩa nghiệp vụ.

### 7.2. `@Size(max=2)` không thay cho key whitelist

```java
@Size(max = 2)
Map<String, String> labels;
```

Constraint này có thể kiểm tra số entry **sau khi object đã bind**, nhưng không quyết định **key nào** được phép và không bảo vệ chi phí tài nguyên đã phát sinh khi nhận một request cực lớn. Hai entries `role` và `tenantId` vẫn có thể thỏa `max=2`, dù đều sai hợp đồng.

Tương tự:

```java
Map<@NotBlank String, @NotBlank String> labels;
```

có thể kiểm tra key/value không rỗng qua container element constraints, nhưng **không** thay thế chính sách key allowlist như `color` hoặc `tier`.

### 7.3. Key Map và business semantics

Nếu hệ thống dùng Map làm “bag of fields”, đừng để logic backend tin rằng một key có tên `role`, `approved` hoặc `owner` do client gửi có quyền thay đổi property tương ứng trên entity. Khi cần metadata linh hoạt:
- Tách namespace **user-defined** khỏi namespace **server-owned**.
- Định nghĩa pattern key và giới hạn size.
- Ngăn các key reserved.
- Bất kỳ hành động thay đổi quyền hoặc nguồn tiền đều phải qua authorization riêng.

**Kiểm tra key hậu binding vẫn hữu ích nhưng không đủ:** nếu binder chấp nhận hàng nghìn key trước khi validation chạy, chi phí tài nguyên đã phát sinh. Ưu tiên chặn ở sớm nhất có thể.

## 8. Nested object: cascade validation khác quyền ghi field

### 8.1. `@Valid` đi sâu vào object, nhưng không chọn tên field được bind

```java
public class Contact {
    @NotBlank
    @Email
    private String email;

    private boolean admin;
    // getters/setters...
}

public class ShipmentForm {
    @NotNull
    @Valid
    private Contact contact;
}
```

`@NotNull` cấm `contact=null`; `@Valid` yêu cầu Jakarta Validation đi sâu để kiểm tra `Contact.email`. Nhưng nếu binder không có allowlist và client gửi `contact.admin=true`, Bean Validation **không mặc nhiên chặn** điều đó; boolean `admin` không bị ràng buộc nào cấm.

Bộ ba độc lập:
- **Bind:** field này có được nhận từ client?
- **Validate:** sau khi bind, dữ liệu có đạt constraint?
- **Authorize:** caller có quyền thực hiện thay đổi này?

Không xem một trong ba thay thế hai phần còn lại.

### 8.2. Collection element cascading

```java
@Size(min = 1, max = 2)
private List<@Valid Address> addresses = new ArrayList<>();
```

`@Size` kiểm tra **độ dài List sau binding**; `@Valid` trên từng phần tử yêu cầu validate `Address.city`. Với `Address.city @NotBlank`:
- Có phần tử tại index 0 nhưng city blank → constraint violation.
- Không có địa chỉ → `@Size(min=1)` thất bại.
- Phần tử null → `@Valid` cascade thường bỏ qua null; nếu muốn cấm null, dùng `List<@NotNull @Valid Address>`.

Nếu request có `addresses[2].city` nhưng form chỉ cho phép indexes 0 và 1, **allowlist** cần loại nó trước. `@Size(max=2)` không đủ để thiết lập index security.

### 8.3. Chống object-graph explosion

Khi nested paths như `orders[10].items[50].options[99].value` được mở, mức độ mở rộng có thể tăng nhanh. Tránh:
- DTO tự tham chiếu/cyclic có setters công khai dễ bị binder truy cập.
- Dùng các quan hệ JPA entity làm request property graph.
- Pattern `*` rộng qua nhiều levels.
- Danh sách lồng nhau không có giới hạn nghiệp vụ.

Không chỉ giới hạn **một collection** mà phải xét **tổng số phần tử, độ sâu path, số field, chi phí xử lý** của cả request.

## 9. Constructor binding và `setDeclarativeBinding(true)`

Spring Framework 6.1+ hỗ trợ:

```java
@InitBinder
void init(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Khi bật **declarative binding**, Spring ưu tiên constructor binding; property/setter binding không tự động xảy ra trừ khi `allowedFields` được cấu hình.

Điều này giúp DTO immutable/record có một input contract hẹp:

```java
public record ShipmentInput(
        String reference,
        String contactEmail,
        List<String> cities) {}
```

**Sắc thái quan trọng:** `setAllowedFields` là chính sách cho **property binding**; nó **không phải** một bộ lọc chung cho mọi constructor argument. Spring MVC cũng có thể hỗ trợ constructor binding từ indexed Map/List request values khi constructor khai báo loại đó. Đừng tạo constructor có parameter `admin`, `role` hoặc `ownerId` rồi nghĩ whitelist setter tự bảo vệ nó.

Để an toàn với constructor binding:
1. Tạo constructor/record chỉ nhận các thuộc tính public thực sự.
2. Với Map/List trong constructor, kiểm soát **key/index/size** và hậu kiểm tra object.
3. Không lấy domain entity constructor làm input contract.
4. Tách server-owned fields khỏi constructor request.
5. Test request bổ sung extra keys/index/nested paths.

Trong project chạy ở phần 12, ta dùng **mutable DTO + allowlist cụ thể** nhằm quan sát `getSuppressedFields()`, không bật declarative binding để tránh nhập nhằng giữa hai cơ chế.

## 10. JSON qua `@RequestBody`: đừng tin rằng binder allowlist chặn Jackson

Ví dụ:

```java
@PostMapping("/json")
public ResponseEntity<?> create(
        @Valid @RequestBody ShipmentForm body) {
    // ...
}
```

Khi `Content-Type: application/json`, Jackson/`HttpMessageConverter` đọc JSON và tạo object. `WebDataBinder#setAllowedFields` dành cho property binding của form **không kiểm soát Jackson deserialize fields** theo cách tương tự.

JSON:

```json
{
  "reference": "SHP-001",
  "approved": true,
  "contact": {
    "email": "mai@example.com",
    "admin": true
  },
  "labels": {
    "role": "administrator"
  }
}
```

có thể được Jackson deserialize vào mutable DTO có các setters tương ứng, kể cả khi `@InitBinder` đã whitelist chỉ `contact.email`/`labels[color]` cho form binding. **Đừng tạo endpoint JSON như trên với input DTO lộ field server-owned**.

Mẫu tốt hơn là một request record riêng:

```java
public record CreateShipmentJson(
        @NotBlank String reference,
        @NotBlank @Email String contactEmail,
        @Size(max = 2) Map<String, String> labels) {}
```

Sau decode, dùng kiểm tra schema/key policy và service authorization; các trường `approved`/`ownerId` chỉ được server xác định. Nếu yêu cầu từ chối unknown JSON properties, cấu hình Jackson/DTO **có chủ đích**, test cụ thể, không trông chờ binder form. Jackson có chính sách riêng về coercion, unknown properties, duplicate JSON keys và creators.

**Một chi tiết cần chính xác:** Spring MVC có thể vẫn tạo `WebDataBinder` cho bước **validation** sau khi Jackson tạo DTO. Vì thế không nói “`@InitBinder` tuyệt đối không chạy với `@RequestBody`”; điều đúng là **setter field allowlist của WebDataBinder không điều khiển cách Jackson giải mã JSON**.

## 11. Định nghĩa hợp đồng API an toàn cho field paths

Trước khi viết binder, biến một bảng quyền thành code:

| Loại | Tên hợp lệ | Quy tắc |
| --- | --- | --- |
| Field đơn | `reference` | Chuỗi không blank |
| Nested | `contact.email` | Email đúng định dạng, có mặt |
| List index | `addresses[0].city`, `addresses[1].city` | Tối đa hai địa chỉ; mỗi city không blank |
| Map entry | `labels[color]`, `labels[tier]` | Chỉ hai keys được nhận |
| Server-owned | `approved`, `ownerId`, `contact.admin` | Không được client thay đổi |
| Index ngoài | `addresses[2].city` và lớn hơn | Reject/suppress |
| Map key ngoài | `labels[role]`, `labels[tenant]` | Reject/suppress |

Điểm quan trọng: danh sách này liên quan tới **quyền nhập field**. Bean Validation được viết **thêm** để kiểm tra chất lượng của các giá trị được phép.

Nếu UI có thể thêm số địa chỉ không cố định (ví dụ 0 đến 10), bạn có thể thiết kế:
- API JSON riêng với một list DTO và size bound, phân tích body size từ sớm.
- Hoặc form endpoint có allowlist động được xây dựng **từ quyền/hợp đồng server đáng tin**, kết hợp index validation và autoGrowCollectionLimit.
- Không lấy một tham số của chính client (ví dụ `count=100000`) để mở rộng allowlist một cách mù quáng.

## 12. Dự án đầy đủ: Spring Boot 3.5.6 + Java 17

Dự án minh họa có hai lớp kiểm chứng:
- **MockMvc**: gửi form thật đi qua controller và xác minh server trả lỗi cho unexpected nested property, Map key, index.
- **Unit test `WebDataBinder`**: xác minh field nào bị suppress và object graph thực tế **không bị gán** các giá trị trái phép.

Trong production, nên bỏ hẳn các setters nhạy cảm ra khỏi request DTO; demo vẫn chứa chúng để test rõ lớp phòng vệ bổ sung.

### 12.1. Cấu trúc thư mục

```text
safe-binding-demo/
├── pom.xml
├── src/main/java/demo/safebinding/
│   ├── SafeBindingApplication.java
│   ├── ShipmentForm.java
│   └── ShipmentController.java
└── src/test/java/demo/safebinding/
    ├── ShipmentControllerTest.java
    └── ShipmentBinderTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>safe-binding-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` chạy Spring MVC Servlet và MockMvc. `spring-boot-starter-validation` cung cấp Bean Validation provider để `@Valid`, `@NotBlank`, `@Email`, `@Size` được thực thi. Không cần thêm WebFlux starter vào bài học này.

### 12.3. `SafeBindingApplication.java`

```java
package demo.safebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeBindingApplication.class, args);
    }
}
```

### 12.4. `ShipmentForm.java`

```java
package demo.safebinding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ShipmentForm {

    @NotBlank(message = "reference.required")
    private String reference;

    @NotNull(message = "contact.required")
    @Valid
    private Contact contact;

    @Size(min = 1, max = 2, message = "addresses.size")
    private List<@Valid Address> addresses = new ArrayList<>();

    @Size(max = 2, message = "labels.size")
    private Map<String, String> labels = new LinkedHashMap<>();

    // Chỉ tồn tại để chứng minh mass assignment risk trong demo.
    private boolean approved;
    private String ownerId;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }

    public List<Address> getAddresses() {
        return addresses;
    }

    public void setAddresses(List<Address> addresses) {
        this.addresses = addresses;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }

    public static class Contact {
        @NotBlank(message = "email.required")
        @Email(message = "email.invalid")
        private String email;

        // Cố ý public setter, nhưng policy không cho bind field này.
        private boolean admin;

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public boolean isAdmin() {
            return admin;
        }

        public void setAdmin(boolean admin) {
            this.admin = admin;
        }
    }

    public static class Address {
        @NotBlank(message = "city.required")
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
```

Đối tượng `Contact` mặc định là null; `WebDataBinder` có thể auto-grow khi nhận `contact.email`. List addresses và Map labels đã được khởi tạo trống, giúp binder chỉ cần thêm phần tử/entry đúng đường dẫn được cho phép.

### 12.5. `ShipmentController.java`

```java
package demo.safebinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {

    @InitBinder("shipmentForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "reference",
                "contact.email",
                "addresses[0].city",
                "addresses[1].city",
                "labels[color]",
                "labels[tier]");

        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(4);
    }

    public record ShipmentView(
            String reference,
            String email,
            List<String> cities,
            Map<String, String> labels) {
    }

    public record ApiResult(
            String code,
            int suppressedCount,
            List<String> fields,
            ShipmentView shipment) {
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<ApiResult> create(
            @Valid @ModelAttribute("shipmentForm") ShipmentForm form,
            BindingResult errors) {

        String[] suppressed = errors.getSuppressedFields();

        // Kiểm tra suppression riêng: hasErrors() có thể là false.
        if (suppressed.length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiResult(
                            "UNEXPECTED_FIELD",
                            suppressed.length,
                            List.of(),
                            null));
        }

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors()
                    .stream()
                    .map(e -> e.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiResult("INVALID_FORM", 0, fields, null));
        }

        // Chỉ xuất một "view" của những dữ liệu client được phép gửi.
        var cities = form.getAddresses().stream()
                .map(ShipmentForm.Address::getCity)
                .toList();

        var view = new ShipmentView(
                form.getReference(),
                form.getContact().getEmail(),
                cities,
                Map.copyOf(form.getLabels()));

        return ResponseEntity.ok(
                new ApiResult("ACCEPTED", 0, List.of(), view));
    }
}
```

**Những chi tiết cố ý trong code:**
- `@InitBinder("shipmentForm")` chỉ cấu hình binder có object name khớp `@ModelAttribute("shipmentForm")`.
- `setAllowedFields` cấm `approved`, `ownerId`, `contact.admin`, Map keys lạ và List indexes ngoài [0],[1].
- `setAutoGrowNestedPaths(true)` cho phép tạo `Contact` và `Address` hợp lệ trong quá trình binding; chính allowlist giúp không mở đường dẫn tùy tiện.
- `setAutoGrowCollectionLimit(4)` là lớp phụ bên cạnh allowlist, không thay cho giới hạn index cụ thể.
- `@Valid` kích hoạt Bean Validation; `BindingResult` đứng **ngay sau** DTO.
- `suppressed.length > 0` được kiểm tra **trước** `errors.hasErrors()`.
- Không trả raw suppressed field names ra response để tránh phản chiếu input chưa tin cậy.
- `ShipmentView` không chứa field quyền, owner hoặc trạng thái approved.
- Trong ví dụ, dữ liệu chỉ được trả về, **không được persist**. Production phải kiểm tra quyền server-side và map có chọn lọc sang entity.

Không cần import `Arrays` ở controller trong code trên; nếu IDE cảnh báo unused import, có thể xóa `import java.util.Arrays;` mà không ảnh hưởng chức năng.

### 12.6. `ShipmentControllerTest.java` — test HTTP bằng MockMvc

```java
package demo.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShipmentControllerTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form(
            String reference, String email, String city) {
        return post("/api/shipments/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("reference", reference)
                .param("contact.email", email)
                .param("addresses[0].city", city)
                .param("labels[color]", "blue");
    }

    @Test
    void validNestedListAndMapAreAccepted() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("ACCEPTED"))
                .andExpect(jsonPath("$.suppressedCount").value(0))
                .andExpect(jsonPath("$.shipment.reference")
                        .value("SHP-001"))
                .andExpect(jsonPath("$.shipment.email")
                        .value("mai@example.com"))
                .andExpect(jsonPath("$.shipment.cities[0]")
                        .value("Hue"))
                .andExpect(jsonPath("$.shipment.labels.color")
                        .value("blue"));
    }

    @Test
    void allowedSecondAddressIndexWorks() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[1].city", "Da Nang")
                        .param("labels[tier]", "regular"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shipment.cities[1]")
                        .value("Da Nang"))
                .andExpect(jsonPath("$.shipment.labels.tier")
                        .value("regular"));
    }

    @Test
    void rejectTopLevelApprovedField() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void rejectTopLevelOwnerId() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("ownerId", "other-user"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnexpectedNestedAdminProperty() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("contact.admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnexpectedMapKey() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("labels[role]", "administrator"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }

    @Test
    void rejectUnexpectedAddressIndexTwo() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[2].city", "Unknown"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectVeryLargeAddressIndex() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("addresses[999999].city", "Rogue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void rejectUnknownParameterInsteadOfIgnoringIt() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", "Hue")
                        .param("surprise", "unexpected"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void blankNestedEmailFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("contact.email"));
    }

    @Test
    void malformedEmailFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "not-email", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("contact.email"));
    }

    @Test
    void blankListElementCityFailsBeanValidation() throws Exception {
        mvc.perform(form("SHP-001", "mai@example.com", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("addresses[0].city"));
    }

    @Test
    void absentListFailsSizeMin() throws Exception {
        mvc.perform(post("/api/shipments/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("reference", "SHP-001")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("addresses"));
    }

    @Test
    void absentContactFailsNotNull() throws Exception {
        mvc.perform(post("/api/shipments/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("reference", "SHP-001")
                        .param("addresses[0].city", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("contact"));
    }

    @Test
    void blankReferenceFailsNotBlank() throws Exception {
        mvc.perform(form("   ", "mai@example.com", "Hue"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_FORM"))
                .andExpect(jsonPath("$.fields[0]").value("reference"));
    }

    @Test
    void unexpectedFieldHasPriorityOverOtherInvalidValues()
            throws Exception {
        mvc.perform(form("", "mai@example.com", "Hue")
                        .param("labels[role]", "admin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.suppressedCount").value(1));
    }
}
```

Bộ test trên gồm **16 trường hợp**: 2 thành công, 7 kiểm tra unexpected fields/index/key, 5 xác minh nested/list/form constraints, và các trường hợp hợp đồng/ưu tiên lỗi. Đếm theo từng method `@Test` là nguồn xác nhận chính; khi thêm/bớt test, cập nhật bảng nhóm thay vì dựa vào một tổng cố định không được kiểm tra.

**Điểm cốt lõi:** Nếu chỉ test `200` cho form hợp lệ, không hề chứng minh rằng `approved`, `contact.admin`, `labels[role]` hoặc `addresses[999999]` bị chặn. Những test negative là phần quan trọng nhất của bài học về an toàn dữ liệu.

### 12.7. `ShipmentBinderTest.java` — đọc chính xác field bị suppress

```java
package demo.safebinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShipmentBinderTest {

    @Test
    void unexpectedNestedMapAndListPathsAreSuppressed() {

        ShipmentForm target = new ShipmentForm();

        WebDataBinder binder =
                new WebDataBinder(target, "shipmentForm");

        // Dùng đúng cấu hình @InitBinder của controller.
        new ShipmentController().initBinder(binder);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("reference", "SHP-001");
        values.add("contact.email", "mai@example.com");
        values.add("addresses[0].city", "Hue");
        values.add("labels[color]", "blue");

        values.add("approved", "true");
        values.add("ownerId", "another-user");
        values.add("contact.admin", "true");
        values.add("labels[role]", "administrator");
        values.add("addresses[999999].city", "Rogue");

        binder.bind(values);

        Set<String> suppressed = new TreeSet<>(
                Arrays.asList(
                        binder.getBindingResult().getSuppressedFields()));

        assertEquals(
                Set.of(
                        "approved",
                        "ownerId",
                        "contact.admin",
                        "labels[role]",
                        "addresses[999999].city"),
                suppressed);

        // Chỉ các property paths hợp lệ mới thay đổi DTO.
        assertFalse(target.isApproved());
        assertNull(target.getOwnerId());
        assertFalse(target.getContact().isAdmin());
        assertEquals("mai@example.com",
                target.getContact().getEmail());

        assertEquals(1, target.getAddresses().size());
        assertEquals("Hue",
                target.getAddresses().get(0).getCity());

        assertEquals(1, target.getLabels().size());
        assertEquals("blue", target.getLabels().get("color"));
        assertFalse(target.getLabels().containsKey("role"));
    }

    @Test
    void allowedFieldsCanBindTwoAddressesAndTwoLabels() {

        ShipmentForm target = new ShipmentForm();

        WebDataBinder binder =
                new WebDataBinder(target, "shipmentForm");
        new ShipmentController().initBinder(binder);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("addresses[0].city", "Hue");
        values.add("addresses[1].city", "Da Nang");
        values.add("labels[color]", "blue");
        values.add("labels[tier]", "regular");

        binder.bind(values);

        assertTrue(binder.getBindingResult()
                .getSuppressedFields().length == 0);
        assertEquals(2, target.getAddresses().size());
        assertEquals("Da Nang",
                target.getAddresses().get(1).getCity());
        assertEquals(2, target.getLabels().size());
    }
}
```

Hai test `WebDataBinder` chạy **không cần Spring ApplicationContext**: chúng tạo binder thủ công và gọi method cấu hình như controller. Chúng chứng minh chính xác:
- Fields lạ được liệt kê trong `getSuppressedFields()`.
- Nested `contact.admin` vẫn false.
- `approved` và `ownerId` không nhận giá trị client gửi.
- Chỉ số cực lớn không khiến List phình lên khi đã bị allowlist loại bỏ.
- Map chỉ nhận key được phép.
- Hai List indexes/Map keys được cho phép vẫn hoạt động.

**Lưu ý về test:** `new WebDataBinder(...)` không tự có provider Jakarta Validation như MVC auto-configured binder. Hai test ở đây chỉ kiểm tra **binding/suppression**, không kiểm tra `@NotBlank`/`@Size`; phần Bean Validation đã được kiểm tra qua MockMvc trong class trước.

### 12.8. Chạy test và khởi động server

Tại thư mục `safe-binding-demo`:

```bash
mvn test
```

Kỳ vọng tất cả **18 tests** (16 MockMvc + 2 WebDataBinder) pass trong môi trường Java 17/Maven tải được dependencies. Đây là **kết quả dự kiến của mã mẫu**, không phải kết quả đã thực thi trong lúc soạn bài.

Khởi động server:

```bash
mvn spring-boot:run
```

Không cần database. Spring Boot web starter cung cấp server Servlet nhúng. Nhớ chọn `application/x-www-form-urlencoded` khi thử form; gửi JSON vào cùng endpoint sẽ không đi qua cách binding đang được minh họa.

## 13. Thử bằng curl

### 13.1. Form hợp lệ

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'labels[color]=blue'
```

Kỳ vọng HTTP **200** và body tương đương:

```json
{
  "code": "ACCEPTED",
  "suppressedCount": 0,
  "fields": [],
  "shipment": {
    "reference": "SHP-001",
    "email": "mai@example.com",
    "cities": ["Hue"],
    "labels": {"color": "blue"}
  }
}
```

### 13.2. Chèn key Map bất thường

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'labels[color]=blue' \
  --data-urlencode 'labels[role]=administrator'
```

Kỳ vọng HTTP **400**:

```json
{
  "code": "UNEXPECTED_FIELD",
  "suppressedCount": 1,
  "fields": [],
  "shipment": null
}
```

**Vì sao không là constraint error?** Key `role` đã bị binder suppress do không thuộc allowlist; nó không cần trở thành một Map entry trước khi bị từ chối.

### 13.3. Chỉ số List cực lớn

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'addresses[999999].city=Unexpected'
```

Kỳ vọng HTTP **400** với `UNEXPECTED_FIELD`. Với allowlist chính xác, index lớn bị chặn thay vì được dùng để tạo phần tử. `setAutoGrowCollectionLimit(4)` vẫn hữu ích như lớp phụ khi policy sau này thay đổi.

### 13.4. Nested field có quyền cao

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'addresses[0].city=Hue' \
  --data-urlencode 'contact.admin=true' \
  --data-urlencode 'approved=true'
```

Kỳ vọng HTTP **400**, `suppressedCount=2`. Không có code nào nhận trạng thái `approved` từ client. Một hệ thống thực cần ủy quyền ở service nếu có chức năng phê duyệt vận đơn.

### 13.5. Field hợp lệ nhưng không đạt constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/shipments/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'reference=SHP-001' \
  --data-urlencode 'contact.email=not-an-email' \
  --data-urlencode 'addresses[0].city=Hue'
```

Kỳ vọng HTTP **400**:

```json
{
  "code": "INVALID_FORM",
  "suppressedCount": 0,
  "fields": ["contact.email"],
  "shipment": null
}
```

Đây là **Bean Validation sau khi bind**. Nó khác `UNEXPECTED_FIELD`, xảy ra khi một tên field trái policy được gửi.

## 14. Field suppression, validation và authorization không thay thế nhau

| Lớp | Đầu vào được kiểm soát | Câu hỏi cần trả lời |
| --- | --- | --- |
| HTTP/server limits | Body/param count/size | Có thể xử lý request với chi phí hợp lý không? |
| Binder allowlist | Names/property paths | Client có được đặt field này không? |
| Auto-grow cap | Indexed list/array expansion | Một indexed field có thể tự mở rộng đến mức nào? |
| Jakarta Validation | Values, nested objects, container elements | Đối tượng sau binding có đạt ràng buộc dữ liệu không? |
| Service authorization | Caller, tenant, entity, operation | Người này có quyền sửa object/field này không? |
| Domain invariants | State transition, quantity, references | Thay đổi có hợp lệ về nghiệp vụ không? |
| Persistence mapping | Định nghĩa fields thực sự lưu | Có copy nhầm field server-owned không? |

Ví dụ:
- `labels[role]` bị allowlist chặn dù value không blank.
- `contact.email="bad-email"` được allowlist cho phép nhận nhưng `@Email` từ chối.
- `approved=true` bị allowlist chặn, nhưng server vẫn cần authorization khi có endpoint duyệt riêng.
- `addresses[1].city` hợp lệ theo allowlist nhưng có thể sai nghiệp vụ nếu user không được phép thêm địa chỉ; quyền đó thuộc service.
- `addresses[999999].city` không phải “chỉ là size constraint”; index path được xem xét khi binder xử lý.

## 15. Các lỗi và đường tấn công thiết kế thường gặp

### 15.1. Wildcard quá rộng

```java
binder.setAllowedFields("contact.*", "labels[*]", "addresses[*].*");
```

Đây là **anti-pattern** khi các object chứa privileged properties. Nó có thể mở đường cho `contact.admin`, Map key tùy ý và properties mới được thêm sau này.

Một wildcard hợp lệ về kỹ thuật không tự là hợp lệ về **quyền**. Nếu form thực sự có fields động, nên xác định keys/index nào được phép dựa trên schema server-side, và test giới hạn.

### 15.2. Blacklist thiếu trường mới

```java
binder.setDisallowedFields("admin", "role");
```

Điều này bỏ qua nhiều đường khác như `contact.admin`, `approved` hoặc Map entries. Trường mới xuất hiện sau refactor có thể được bind mặc dù không có trong UI. Positive allowlist đáng tin cậy hơn.

### 15.3. Tin rằng `@Valid` tự cấm extra fields

`@Valid` kiểm tra các constraints trên object mà Spring/Jackson đã tạo. Nó không biết mọi tên input ngoài schema ban đầu nếu chúng không được đưa vào object hoặc validator không thiết kế để xem raw request.

### 15.4. Dùng `@Size(max=2)` thay auto-grow limit

`@Size` được đánh giá **sau binding**; nếu binder đã mở rộng một List quá lớn trước đó, Bean Validation đến muộn. Kết hợp exact index whitelist, `setAutoGrowCollectionLimit` và request limits.

### 15.5. Cấm setter nhưng vẫn cho constructor nhận quyền

Nếu một record có `boolean approved` trong primary constructor, Spring constructor binding có thể lấy nó từ request. `setAllowedFields` chỉ kiểm soát property binding, không phải lá chắn chung cho constructor arguments.

### 15.6. Dùng trực tiếp JPA entity

Binder có thể đi sâu vào quan hệ/collections, trộn dữ liệu client và trạng thái trong entity, và bỏ qua authorization nếu code save quá sớm. Tạo DTO đầu vào riêng rồi map có chọn lọc.

### 15.7. JSON và form dùng chung DTO nhạy cảm

Một DTO được bảo vệ bằng `@InitBinder` cho form không đồng nghĩa an toàn khi dùng lại ở `@RequestBody` JSON. Jackson deserialize theo cơ chế khác. Tạo API-specific DTOs và test từng content type.

### 15.8. Bỏ qua suppressed fields vì `hasErrors()==false`

Nếu policy mong muốn reject extra input, phải đọc `BindingResult.getSuppressedFields()`. Không tự giả định suppression là `FieldError` hoặc một Bean Validation violation.

### 15.9. Tin rằng Map key không thể ảnh hưởng quyền

Một Map metadata có thể được service downstream diễn giải là quyền/discount/internal state. Chặn reserved keys trước khi chúng ảnh hưởng nghiệp vụ; không chỉ regex cho value.

### 15.10. Trả nguyên tên field do attacker nhập ra response

Tên field có thể rất dài hoặc chứa nội dung do client đặt. Nếu cần phản hồi chi tiết, giới hạn chiều dài, escape đúng encoding và phân biệt field paths hợp đồng với raw keys. Demo dùng mã lỗi và suppressed count thay vì echo toàn bộ input.

## 16. Checklist khi triển khai/bảo trì một form lồng nhau

1. Xác định rõ đâu là request DTO, đâu là entity có trạng thái server.
2. Có field `id`, `owner`, `admin`, `approved` hoặc `role` nào đang lộ qua public setter/constructor không?
3. Enumerate **mọi** nested property path mà UI thực sự dùng.
4. Enumerate **mọi** Map key công khai, tránh `map[*]` nếu key có ý nghĩa nghiệp vụ.
5. Enumerate **List indexes** được phép hoặc xây chính sách limits từ schema server.
6. Đăng ký `@InitBinder("attributeName")` đúng object name.
7. Dùng `setAllowedFields(...)` và không thay bằng blacklist chỉ vì ngắn.
8. Kiểm tra `setAutoGrowNestedPaths` và `setAutoGrowCollectionLimit` theo nghiệp vụ.
9. Kiểm soát HTTP body size, parameter count và độ sâu object graph.
10. Quyết định **reject hay silently ignore** suppressed fields; nếu reject thì xem `getSuppressedFields()` riêng.
11. Đặt `BindingResult` ngay sau `@Valid @ModelAttribute` để xử lý lỗi rõ ràng.
12. Dùng `@NotNull` trên nested object cần có mặt và `@Valid` để cascade.
13. Dùng `List<@Valid Item>` và `@Size` cho collection; không coi chúng là index whitelist.
14. Nếu dùng `Map<K,V>`, kiểm tra entry count/key policy/value type, không chỉ `@NotBlank`.
15. Xác minh constructor binding và `setDeclarativeBinding` không mở server-owned arguments.
16. Nếu có endpoint JSON, test riêng Jackson unknown fields và quyền gán property.
17. Trong service, kiểm tra quyền theo authenticated principal/tenant, không nhận ownerId từ form.
18. Chỉ map chính xác fields được phép, tránh generic property copy into entity.
19. Viết negative tests cho malicious nested property, Map key và huge List index.
20. Test cả dữ liệu hợp lệ bị Bean Validation từ chối, để thấy khác suppression.
21. Xác minh output không echo raw input hoặc tiết lộ thông tin nhạy cảm.
22. Kiểm thử lại khi DTO được mở rộng thêm property/setter; allowlist giúp fail closed nếu giữ chính sách hẹp.

## 17. Bài tập tự luyện

1. Đổi `setAllowedFields("labels[color]","labels[tier]")` thành `"labels[*]"` rồi gửi `labels[role]`. Quan sát vì sao Map key lạ không còn bị allowlist chặn.
2. Thêm setter `Contact.setRole` vào DTO và gửi `contact.role=admin`. Xác minh policy hiện tại vẫn suppress.
3. Đổi `addresses[1].city` trong allowlist thành wildcard và thử index lớn; so sánh kết quả với `setAutoGrowCollectionLimit(4)`.
4. Tắt `setAutoGrowNestedPaths` và gửi `contact.email` khi `contact=null`. Giải thích khác biệt với object con khởi tạo sẵn.
5. Bỏ `@Valid` trên `contact`, giữ `@NotNull`; gửi email sai và giải thích vì sao cascade có thể không chạy.
6. Bỏ `@NotNull` nhưng giữ `@Valid` trên `contact`, gửi request không có contact và quan sát kết quả.
7. Bỏ `@Size(max=2)` trên List; giữ index allowlist. Phân biệt giới hạn binding và giới hạn validation.
8. Chỉ kiểm tra `errors.hasErrors()` mà bỏ `getSuppressedFields()`; gửi `approved=true` và xác định endpoint có thể trả response gì.
9. Tạo immutable record chỉ nhận `reference`, `contactEmail`, `cities` và bật `setDeclarativeBinding(true)`; thiết kế thêm kiểm tra map keys nếu dùng Map trong constructor.
10. Viết test raw JSON chứa `approved=true` vào một DTO có setter tương ứng, rồi thay bằng JSON DTO chỉ có public input fields.
11. Thêm Map key `labels[tenantId]`, áp một policy reserved-keys trước khi persistence và test nó không thể ảnh hưởng tenant.
12. Xây service nhận authenticated principal, không chấp nhận `ownerId` client gửi và chỉ cho phép thay contact email khi có quyền.
13. Bổ sung giới hạn request size/parameter count ở server, test một request có rất nhiều Map key.
14. Tạo lỗi validation cho một `Address.city` rỗng và lỗi suppression cho `addresses[99].city` trong cùng request; xác minh policy chọn mã `UNEXPECTED_FIELD` trước.
15. Thử key có dấu nháy trong bracket như `labels['color']`; test cách Spring chuẩn hóa path trong phiên bản đang dùng, không tự suy đoán.
16. Thiết kế schema/ProblemDetail response cho unknown field, nhưng không phản chiếu unbounded raw path do client gửi.

**Kết luận:** Với form/query binding, các tên `contact.email`, `labels[key]` và `addresses[index].city` là một phần **bề mặt đầu vào** của ứng dụng. Hãy bảo vệ chúng bằng **request DTO chuyên biệt**, **positive allowed-fields theo đường dẫn cụ thể**, **kiểm tra suppressed fields**, **giới hạn auto-grow và request resources**, sau đó mới tới Jakarta Validation và authorization. Không dùng một cơ chế để thay thế tất cả các lớp còn lại.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — `@InitBinder` và Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — `@ModelAttribute` và bảo mật data binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — `DataBinder` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — `WebDataBinder` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 — `BindingResult` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — `PropertyAccessorUtils` canonical names](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/PropertyAccessorUtils.html)
- [Spring Framework 6.2 — MVC `@RequestBody` (Jackson)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Boot 3.5 — Testing web applications with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 — Container element validation and cascades](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)