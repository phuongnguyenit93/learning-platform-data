# Reject unknown field khi contract yêu cầu

Một API thường công bố rõ những trường client được phép gửi trong request. Nếu hợp đồng của endpoint chỉ nhận `displayName` và `phoneNumber`, request có thêm `role`, `isAdmin` hoặc một trường viết sai như `phoneNubmer` cần được xử lý theo chính sách schema của API. Khi contract yêu cầu object đóng (closed schema), server phải từ chối field không được khai báo thay vì âm thầm bỏ qua hoặc bind nó vào model rộng hơn.

Việc reject unknown field giúp phát hiện lỗi tích hợp sớm, giảm nguy cơ mass assignment và tránh việc các lớp trong hệ thống hiểu payload khác nhau. Tuy nhiên, không phải mọi API đều nên từ chối mọi thuộc tính mở rộng: webhook có metadata mở, API proxy hoặc hợp đồng được thiết kế để forward extension có thể cần giữ field chưa biết. Quyết định phải được thể hiện rõ trong contract, áp dụng nhất quán và được kiểm thử.

Trong API Security, validation dữ liệu đầu vào là một lớp bảo vệ ở ranh giới tin cậy. Nó bổ sung cho xác thực, phân quyền theo object/property và kiểm tra nghiệp vụ; nó không thay thế các lớp đó. Một field được schema chấp nhận vẫn có thể không được caller quyền thấp cập nhật.

Sau bài học, người đọc có thể:

- Phân biệt unknown field, field sai kiểu và field đã biết nhưng caller không được phép sửa.
- Quyết định khi nào contract cần đóng schema và từ chối field ngoài danh sách.
- Mô tả quy tắc unknown field trong JSON Schema/OpenAPI.
- Cấu hình Jackson/Spring để phát hiện field không được khai báo.
- Xử lý nested object, array, PATCH và các kênh đầu vào khác một cách nhất quán.
- Kiểm thử để chứng minh request sai contract không gây thay đổi dữ liệu hoặc side effect.

## 1. Unknown field là gì?

Unknown field là thuộc tính xuất hiện trong request nhưng không nằm trong schema mà endpoint chấp nhận. Ví dụ contract của `PATCH /api/me` chỉ định:

```json
{
  "displayName": "string",
  "phoneNumber": "string"
}
```

Request sau có một field không thuộc contract:

```json
{
  "displayName": "An Nguyen",
  "phoneNumber": "+84900000000",
  "isAdmin": true
}
```

Nếu API dùng closed schema, server trả lỗi validation cho `isAdmin` và không cập nhật hồ sơ. Nếu API dùng open schema, field bổ sung có thể được chấp nhận, bỏ qua hoặc lưu trong vùng extension tùy contract. Không nên để hành vi phụ thuộc tình cờ vào cấu hình serializer hoặc cách entity được khai báo.

### 1.1. Phân biệt ba trường hợp

| Trường hợp | Ví dụ | Câu hỏi cần xử lý |
|---|---|---|
| Unknown field | `phoneNubmer` không có trong schema | Endpoint có cho phép field mở rộng không? Nếu schema đóng thì từ chối |
| Known field nhưng sai kiểu/giá trị | `quantity: "many"` khi cần số nguyên | Kiểu và miền giá trị có hợp lệ không? |
| Field đã biết nhưng caller không được phép ghi | `role: "ADMIN"` trong model user | Caller có quyền cập nhật property này không? |

Một field có thể tồn tại trong domain model hoặc response model nhưng không thuộc request DTO của endpoint hiện tại. Ví dụ `role` là thuộc tính của user, nhưng `PATCH /api/me` chỉ nhận tên và số điện thoại. Từ góc nhìn request contract, `role` không được hỗ trợ ở endpoint đó và nên bị từ chối nếu schema đóng.

Nếu field được khai báo trong request schema nhưng một số role không được phép cập nhật, đây là property authorization. Server cần kiểm tra quyền trên field đó, không thể chỉ dựa vào việc field có nằm trong schema.

## 2. Vì sao nên reject unknown field khi contract yêu cầu?

### 2.1. Phát hiện lỗi tích hợp thay vì âm thầm bỏ qua

Giả sử client gửi `deliveryAdressId` do viết sai tên trường. Nếu server bỏ qua field không biết, request có thể trả thành công nhưng đơn hàng được tạo mà không có địa chỉ giao. Client nghĩ dữ liệu đã được lưu; hệ thống phía sau lại xử lý với giá trị mặc định hoặc trạng thái không mong muốn.

Từ chối field lạ làm lỗi lộ ra ngay tại ranh giới API, giúp developer sửa contract hoặc payload trước khi lỗi lan sang nghiệp vụ.

### 2.2. Giảm nguy cơ mass assignment và over-posting

Nếu request được bind trực tiếp vào entity có nhiều thuộc tính hơn DTO công khai, field do attacker tự thêm có thể lọt vào model:

```json
{
  "displayName": "An Nguyen",
  "role": "ADMIN",
  "tenantId": "TENANT-OTHER",
  "accountStatus": "ACTIVE"
}
```

Reject unknown field là một lớp phòng vệ hữu ích khi những field này không thuộc request contract. Nhưng biện pháp chính vẫn là dùng DTO riêng, allowlist field được phép ghi và kiểm tra property authorization. Nếu entity hoặc DTO quá rộng và field đặc quyền được khai báo hợp lệ, cấu hình reject unknown field không ngăn được mass assignment.

### 2.3. Tránh các lớp hiểu payload khác nhau

Trong hệ thống nhiều tầng, gateway, framework, service và message consumer có thể diễn giải cùng một JSON khác nhau. Một tầng bỏ qua field, tầng khác giữ field, tầng khác lại bind vào entity. Sự khác biệt này có thể tạo ra lỗi kiểm soát dữ liệu hoặc validation bypass.

Hợp đồng rõ ràng về unknown field giúp mọi tầng thống nhất: field nào được phép, field nào bị từ chối và lỗi được trả theo cấu trúc nào.

### 2.4. Không biến reject unknown thành quy tắc cứng cho mọi API

Có những contract cần mở rộng có chủ đích, ví dụ:

- Webhook provider gửi metadata bổ sung mà consumer cần lưu nguyên trạng.
- API proxy chuyển tiếp payload cho hệ thống đích mà không sở hữu toàn bộ schema.
- Object có vùng `extensions` được thiết kế để plugin hoặc tenant mở rộng.
- API nhận dữ liệu từ nhiều phiên bản client và contract cho phép field tùy chọn.

Trong những trường hợp này, hãy mô hình hóa vùng mở rộng rõ ràng, giới hạn kích thước/độ sâu và quy định field nào được forward hoặc lưu. Không mở toàn bộ object chỉ để hỗ trợ một vài extension.

## 3. Quyết định closed schema hay open schema

Trước khi triển khai, nhóm API cần xác định contract của từng endpoint.

| Loại request | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Cập nhật hồ sơ với DTO cố định | Closed schema | Chỉ có một danh sách field được hỗ trợ |
| Tạo đơn hàng | Closed schema | Field dư có thể ảnh hưởng giá, owner hoặc trạng thái |
| Thay đổi quyền/quản trị | Closed schema và allowlist nghiêm ngặt | Tác động bảo mật cao |
| Webhook có metadata mở theo provider | Schema lõi đóng, vùng metadata mở có giới hạn | Giữ extension cần thiết nhưng kiểm soát phần còn lại |
| Proxy/forward payload | Theo contract của hệ thống đích, giới hạn rõ vùng opaque | Gateway không nên tự diễn giải payload không thuộc trách nhiệm |
| JSON Patch | Cho phép đúng cấu trúc operation và path theo policy | Path/operation không hợp lệ phải bị từ chối |

Không nên chọn open schema chỉ vì muốn API “linh hoạt”. Mỗi field mở rộng làm tăng bề mặt cần parse, validate, lưu trữ, serialize, audit và phân quyền. Nếu cần extensibility, hãy tạo một property riêng như `metadata` hoặc `extensions` với quy tắc cụ thể thay vì chấp nhận mọi key ở cấp root.

## 4. Khai báo contract trong JSON Schema và OpenAPI

JSON Schema hỗ trợ `additionalProperties` để quy định object có được phép chứa field không khai báo hay không. Với `additionalProperties: false`, object chỉ được chứa các property đã được mô tả trong schema đó.

Ví dụ JSON Schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["displayName"],
  "properties": {
    "displayName": {
      "type": "string",
      "minLength": 1,
      "maxLength": 80
    },
    "phoneNumber": {
      "type": "string",
      "maxLength": 20
    }
  }
}
```

Với schema này, request chứa `isAdmin` sẽ không hợp lệ. `additionalProperties: false` cần được đặt ở đúng object scope; nếu object có nested object thì mỗi schema con cũng cần định nghĩa chính sách riêng.

### 4.1. Nested object và array

Ví dụ request có địa chỉ giao hàng:

```json
{
  "deliveryAddress": {
    "line1": "12 Nguyen Trai",
    "city": "Ho Chi Minh City",
    "isVerified": true
  }
}
```

Nếu schema root đóng nhưng `deliveryAddress` không có schema con đóng, field `isVerified` vẫn có thể được chấp nhận. Cần khai báo `additionalProperties: false` trong từng object lồng nhau:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["deliveryAddress"],
  "properties": {
    "deliveryAddress": {
      "type": "object",
      "additionalProperties": false,
      "required": ["line1", "city"],
      "properties": {
        "line1": { "type": "string", "maxLength": 160 },
        "city": { "type": "string", "maxLength": 80 }
      }
    }
  }
}
```

Với array, mỗi phần tử cũng cần schema:

```json
{
  "type": "array",
  "maxItems": 20,
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": ["productId", "quantity"],
    "properties": {
      "productId": { "type": "string" },
      "quantity": { "type": "integer", "minimum": 1, "maximum": 20 }
    }
  }
}
```

Không chỉ đóng object ngoài cùng. Unknown field trong nested object hoặc phần tử array cũng có thể mang dữ liệu đặc quyền.

### 4.2. Lưu ý khi dùng `$ref`, `allOf` và schema composition

Với JSON Schema, `additionalProperties` chỉ xét các property được khai báo trong cùng schema object theo quy tắc đánh giá của từ khóa. Khi kết hợp nhiều schema bằng `allOf` hoặc `$ref`, việc đặt `additionalProperties: false` ở một nhánh có thể khiến property được khai báo ở nhánh khác bị coi là không hợp lệ.

Với JSON Schema 2020-12, `unevaluatedProperties: false` có thể phù hợp hơn khi cần đóng object sau khi các nhánh schema đã được đánh giá. Cần kiểm tra validator thực tế và dialect đang sử dụng; không thay từ khóa một cách máy móc. Viết test cho schema đã resolve đầy đủ, không chỉ test từng fragment riêng.

### 4.3. OpenAPI

OpenAPI mô tả schema request/response để client sinh code và công cụ kiểm tra contract. Ví dụ OpenAPI 3.1 có thể dùng schema JSON Schema tương thích:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        additionalProperties: false
        required:
          - displayName
        properties:
          displayName:
            type: string
            minLength: 1
            maxLength: 80
          phoneNumber:
            type: string
            maxLength: 20
```

Với OpenAPI 3.0, `additionalProperties: false` cũng thường được dùng để biểu đạt object đóng, nhưng cần tuân theo subset/schema semantics của phiên bản. Contract phải được đồng bộ với runtime validation: tài liệu ghi closed schema nhưng server âm thầm bỏ qua field lạ là một dạng contract drift.

## 5. Cấu hình Jackson/Spring để từ chối unknown field

Với Spring Boot và Jackson, có thể bật `FAIL_ON_UNKNOWN_PROPERTIES` để quá trình deserialize thất bại khi JSON chứa property không có trong target DTO.

Ví dụ cấu hình trong `application.yml`:

```yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
```

Hoặc cấu hình `ObjectMapper` tương đương:

```java
@Bean
Jackson2ObjectMapperBuilderCustomizer strictUnknownFields() {
    return builder -> builder.featuresToEnable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
}
```

Tên property và cách áp dụng có thể phụ thuộc phiên bản Spring Boot/Jackson. Hãy xác minh `ObjectMapper` thực tế được dùng bởi HTTP message converter, đặc biệt khi ứng dụng có nhiều mapper hoặc cấu hình riêng cho một media type.

### 5.1. Dùng request DTO hẹp

```java
public record UpdateProfileRequest(
        @NotBlank @Size(max = 80) String displayName,
        @Pattern(regexp = "^[0-9+ -]{8,20}$") String phoneNumber) {
}
```

Controller:

```java
@PatchMapping("/me")
public ProfileResponse updateProfile(
        @Valid @RequestBody UpdateProfileRequest request,
        @AuthenticationPrincipal ApiPrincipal principal) {
    return profileService.updateAllowedFields(principal, request);
}
```

DTO này chỉ khai báo hai field. Nếu client gửi thêm `role`, Jackson có thể từ chối ngay ở bước deserialize trước khi controller được gọi. Service vẫn cần kiểm tra caller được phép sửa hồ sơ của mình và chỉ cập nhật các thuộc tính được DTO cho phép.

### 5.2. Tránh tắt strictness ở DTO nhạy cảm

Annotation sau yêu cầu Jackson bỏ qua unknown field:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public record UpdateProfileRequest(
        String displayName,
        String phoneNumber) {
}
```

Nếu contract yêu cầu reject unknown field, annotation này làm ngược chính sách. Tương tự, `@JsonAnySetter` có thể gom mọi field chưa biết vào một map; chỉ dùng khi contract có vùng extension được thiết kế rõ, có giới hạn và có validation riêng.

Không dùng entity làm `@RequestBody`. DTO riêng giúp field không được hỗ trợ không có đường bind trực tiếp vào persistence model, ngay cả khi một mapper hoặc cấu hình JSON bị thay đổi.

### 5.3. Cấu hình global hay theo endpoint?

Bật strict unknown-field toàn cục dễ tạo hành vi nhất quán nhưng có thể phá các endpoint vốn cần metadata mở hoặc webhook provider có extension. Nếu các contract khác nhau, có thể:

- Dùng mapper/reader riêng cho một boundary được xác định rõ.
- Dùng validator JSON Schema theo endpoint/media type.
- Đưa dữ liệu mở vào property `metadata` riêng và chỉ mở schema tại vị trí đó.
- Tách webhook adapter khỏi DTO nghiệp vụ nội bộ.

Tránh để controller tự parse JSON theo cách khác với HTTP converter của hệ thống. Một request không nên được kiểm tra ở gateway bằng closed schema nhưng lại được một đường internal khác deserialize theo open schema mà không có lý do.

## 6. Unknown field trong PATCH và JSON Patch

PATCH có nhiều định dạng và ngữ nghĩa khác nhau; cần xác định rõ contract.

### 6.1. JSON Merge Patch

Với `application/merge-patch+json`, client gửi các field muốn thay đổi. Field không xuất hiện thường có nghĩa là giữ nguyên; field có giá trị `null` thường mang nghĩa xóa property theo JSON Merge Patch (RFC 7396). Nếu schema endpoint đóng, field không khai báo vẫn phải bị từ chối.

Ví dụ contract chỉ cho đổi ghi chú:

```http
PATCH /api/orders/ORD-200
Content-Type: application/merge-patch+json

{
  "deliveryNote": "Giao tại lễ tân",
  "status": "COMPLETED"
}
```

Nếu `status` không thuộc schema patch, request phải thất bại và không thay đổi `deliveryNote` hoặc trạng thái. Không nên áp dụng phần hợp lệ trước rồi mới phát hiện field lạ và trả lỗi, trừ khi contract chủ động định nghĩa xử lý partial.

### 6.2. JSON Patch

Với `application/json-patch+json` (RFC 6902), request là danh sách operation như `add`, `remove`, `replace`, `move`, `copy`, `test`. Schema cần giới hạn cấu trúc operation; policy cần allowlist path và operation được phép.

Ví dụ user chỉ được thay `/deliveryNote`:

```json
[
  { "op": "replace", "path": "/deliveryNote", "value": "Giao tại lễ tân" },
  { "op": "replace", "path": "/role", "value": "ADMIN" }
]
```

`/role` có thể là path không được contract cho phép. Server phải từ chối toàn bộ patch theo hợp đồng và không để operation đầu tiên thay đổi dữ liệu trước khi operation thứ hai bị từ chối. Kiểm tra cả path escape, nested path, array index và operation `copy`/`move` vì chúng có thể đưa dữ liệu từ một property nhạy cảm sang property khác.

## 7. Các kênh đầu vào ngoài JSON body

Unknown field không chỉ xuất hiện trong JSON object. Tùy endpoint, cần quy định rõ hành vi với:

- **Query parameter:** `/orders?status=PAID&stauts=PAID`. Nhiều framework bỏ qua query parameter không được khai báo; nếu contract yêu cầu strict, cần allowlist tên tham số và kiểm tra trước khi truy vấn.
- **Form/multipart:** từ chối field form dư nếu endpoint có schema cố định; giới hạn số part, tên field, kích thước và loại tệp.
- **Header:** chỉ xử lý header được định nghĩa; không dùng custom header tùy ý làm nguồn quyền. Header tiêu chuẩn không liên quan có thể được proxy bỏ qua, nên contract cần xác định phần nào thuộc ứng dụng.
- **Path parameter:** route template thường giới hạn cấu trúc, nhưng vẫn cần kiểm tra kiểu, định dạng và phạm vi ID.
- **GraphQL:** schema validation từ chối field/argument không được khai báo trong operation; authorization vẫn phải được kiểm tra ở resolver cho object và property.
- **Webhook/event:** phân biệt field lõi bắt buộc với vùng metadata mở theo contract của provider; xác minh chữ ký và nguồn trước khi xử lý.

Không nên cố áp một quy tắc “từ chối mọi thứ lạ” cho toàn bộ HTTP headers, vì nhiều header được thêm bởi proxy, tracing hoặc hạ tầng. Hãy đóng schema ở những vùng dữ liệu mà API thực sự sở hữu và diễn giải.

## 8. Xử lý lỗi khi gặp unknown field

Khi request chứa field không được phép, API cần trả lỗi nhất quán, dễ sửa nhưng không tiết lộ dữ liệu nhạy cảm.

Ví dụ response:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/unknown-field",
  "title": "Invalid request body",
  "status": 400,
  "detail": "The request contains a field that is not supported.",
  "code": "UNKNOWN_FIELD",
  "errors": [
    {
      "path": "$.isAdmin",
      "code": "UNKNOWN_FIELD"
    }
  ]
}
```

`400 Bad Request` thường phù hợp khi body không đáp ứng cấu trúc contract. Một API có thể dùng `422 Unprocessable Content` cho validation nội dung nếu đó là quy ước nhất quán; điều quan trọng là tài liệu hóa và không dùng lẫn lộn khó đoán. Không trả lại giá trị field bị từ chối vì nó có thể chứa secret hoặc dữ liệu nhạy cảm.

Thông báo lỗi nên chỉ ra đường dẫn field hoặc vị trí cần sửa nếu an toàn. Không đưa stack trace, tên class Java, câu SQL, danh sách property nội bộ hoặc thông tin của object khác vào response. Log nội bộ có thể ghi chi tiết hơn nhưng cần kiểm soát quyền truy cập và loại bỏ token/secret.

## 9. Tương thích phiên bản và thay đổi contract

Reject unknown field làm contract chặt hơn, nhưng có hệ quả khi client và server được triển khai lệch phiên bản.

Ví dụ server phiên bản mới thêm field `preferredLanguage` vào request. Client mới gửi field này tới server cũ đang dùng closed schema sẽ nhận lỗi unknown field. Vì vậy, cần có chiến lược triển khai:

1. Xác định phiên bản contract và các client đang sử dụng.
2. Nếu thêm field mới, triển khai server có khả năng nhận field trước khi client mới bắt đầu gửi.
3. Chỉ bật client gửi field sau khi backend tương thích đã sẵn sàng.
4. Với API có nhiều phiên bản, giữ schema riêng cho từng version và kiểm thử contract tương ứng.
5. Nếu cần extension, thêm vùng mở có giới hạn thay vì mở toàn bộ request object.

Đối với response, client thường nên chịu được field mới nếu contract quy định forward compatibility. Đây là quyết định khác với việc server nhận request. Có thể thiết kế server strict với request nhưng response extensible cho client, miễn là tài liệu nói rõ. Không nhầm lẫn giữa client phải bỏ qua response field mới và server phải chấp nhận mọi request field mới.

Thay đổi một schema từ open sang closed có thể là breaking change nếu client trước đây gửi field mà server âm thầm bỏ qua. Cần kiểm tra log, telemetry hoặc contract test trước khi bật strict mode cho API đã tồn tại.

## 10. Kiểm thử reject unknown field

Test cần xác minh cả phản hồi lẫn trạng thái dữ liệu. Một response `400` không đủ nếu server đã thực hiện side effect trước khi validation thất bại.

| Tình huống | Payload | Kết quả mong đợi |
|---|---|---|
| Body hợp lệ | Chỉ có field được khai báo | Chấp nhận nếu các validation khác đạt |
| Field gõ sai | `phoneNubmer` | Từ chối closed schema |
| Field đặc quyền | `isAdmin`, `role` | Từ chối nếu không thuộc request contract |
| Field root dư | `debug: true` | Từ chối |
| Field nested dư | `address.isVerified` | Từ chối nếu schema con đóng |
| Field trong array | Một phần tử có `adminNote` | Từ chối theo schema phần tử |
| Kiểu sai | `quantity: "two"` | Từ chối type validation |
| Field bắt buộc thiếu | Thiếu `displayName` | Từ chối required validation |
| JSON Patch path cấm | `replace /role` | Từ chối toàn bộ patch |
| Query parameter lạ | `?stauts=PAID` | Từ chối nếu query contract strict |
| Field lặp key | Hai key `role` trong cùng object | Parser xử lý theo chính sách duplicate-key rõ ràng |
| Body quá lớn/quá sâu | Object lồng nhiều tầng hoặc payload lớn | Từ chối theo giới hạn parser/request |
| Extension hợp lệ | Field trong `metadata` được phép mở | Chấp nhận theo schema extension và giới hạn |

### 10.1. Integration test với Spring Boot

Ví dụ contract `PATCH /api/me` chỉ chấp nhận `displayName` và `phoneNumber`, và chọn hành vi từ chối toàn bộ request nếu có unknown field:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UnknownFieldValidationIT {

    @Autowired MockMvc mockMvc;
    @Autowired UserProfileRepository repository;

    @Test
    @WithMockUser(username = "user-1", authorities = "profile:update")
    void rejectsUnknownFieldWithoutChangingProfile() throws Exception {
        UserProfile before = repository.findById(TestUsers.USER_1)
                .orElseThrow();

        mockMvc.perform(patch("/api/me")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "Changed Name",
                      "isAdmin": true
                    }
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("UNKNOWN_FIELD"));

        UserProfile after = repository.findById(TestUsers.USER_1)
                .orElseThrow();
        assertThat(after.getDisplayName()).isEqualTo(before.getDisplayName());
        assertThat(after.isAdmin()).isEqualTo(before.isAdmin());
    }
}
```

Đây là ví dụ minh họa; fixture, principal và tên property cần khớp ứng dụng thực tế. Nếu controller dùng custom principal, test phải tạo đúng security context thay vì giả định `@WithMockUser` tự cung cấp tenant/user ID. Test cũng cần xác minh không phát event hoặc gọi dịch vụ ngoài trước khi request bị từ chối.

### 10.2. Kiểm thử schema độc lập và contract test

Nếu dùng JSON Schema/OpenAPI validator, viết test trực tiếp cho schema và test tích hợp qua HTTP. Test trực tiếp giúp xác minh `additionalProperties: false` ở root, nested object, array và composition. Test qua HTTP giúp phát hiện runtime converter không dùng schema hoặc Jackson config như mong đợi.

Contract test giữa client và server cần bao gồm payload từ các phiên bản client được hỗ trợ. Khi strictness thay đổi, chạy test tương thích trước khi rollout.

## 11. Giới hạn parser và các trường hợp biên

Reject unknown field không thay thế giới hạn parser. Một JSON không có field lạ vẫn có thể gây tiêu tốn tài nguyên qua body quá lớn, chuỗi quá dài, object lồng sâu hoặc array rất lớn. Cần thêm:

- Giới hạn kích thước request body và số phần tử array.
- Giới hạn độ sâu JSON, độ dài tên field và độ dài chuỗi.
- Giới hạn số lượng field và số nested object.
- Timeout đọc body và giới hạn upload.
- Kiểm tra duplicate key nếu parser/contract yêu cầu object key duy nhất; tránh các tầng xử lý khác nhau khi cùng key xuất hiện nhiều lần.
- Chuẩn hóa cách xử lý tên field/case/alias để không có hai tên cùng ánh xạ một property theo cách bất ngờ.

Ví dụ, `role`, `Role` và `ROLE` có thể được xử lý khác nhau tùy cấu hình case-insensitive hoặc alias của serializer. Không nên dựa vào việc parser mặc định phân biệt chữ hoa/thường nếu hệ thống bật chế độ khác. Test phải phản ánh chính xác cấu hình runtime.

## 12. Checklist trước khi phát hành

- [ ] Contract endpoint xác định rõ object nào đóng và vùng nào được phép mở rộng.
- [ ] Unknown field bị từ chối đúng theo chính sách, không phụ thuộc ngẫu nhiên vào serializer.
- [ ] DTO request hẹp, tách khỏi entity và response model.
- [ ] Field đặc quyền không xuất hiện trong request DTO thông thường; property authorization vẫn được kiểm tra cho field được khai báo.
- [ ] Root, nested object và từng array item có schema phù hợp.
- [ ] JSON Schema/OpenAPI và runtime validation đồng bộ.
- [ ] `$ref`, `allOf` hoặc composition đã được kiểm thử với đúng validator/dialect.
- [ ] PATCH/JSON Patch giới hạn operation và path; request bị từ chối không gây cập nhật một phần.
- [ ] Query, form, multipart, GraphQL và webhook có contract riêng cho unknown field.
- [ ] Error response nhất quán, không tiết lộ stack trace hoặc giá trị nhạy cảm.
- [ ] Có giới hạn kích thước, độ sâu và số lượng phần tử của payload.
- [ ] Có chiến lược tương thích phiên bản và rollout khi chuyển sang closed schema.
- [ ] Test xác minh response, database và side effect sau request sai contract.

## Kết luận

Reject unknown field là một quyết định của API contract. Khi endpoint dùng closed schema, server nên từ chối field không được khai báo ngay tại ranh giới đầu vào, trả lỗi nhất quán và bảo đảm không có thay đổi dữ liệu một phần. Kết hợp request DTO hẹp, JSON Schema/OpenAPI, cấu hình parser rõ ràng và test nested/PATCH/version compatibility giúp phát hiện lỗi tích hợp, giảm mass assignment và giữ các tầng trong hệ thống hiểu cùng một payload. Field được schema chấp nhận vẫn phải qua authorization và validation nghiệp vụ trước khi được sử dụng.
