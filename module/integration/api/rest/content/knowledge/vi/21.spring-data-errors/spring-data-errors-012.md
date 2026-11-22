# Kiểm soát trường Jackson được đọc, ghi và tránh mass assignment

## 1. Bài toán và mục tiêu

Trong module **INTEGRATION_API_REST**, một endpoint có resource, URI, HTTP method, status và JSON schema hợp lệ vẫn có thể gây sự cố nếu server **cho client thay đổi những thuộc tính mà client không có quyền kiểm soát**. Với Java/Spring MVC, Jackson biến request JSON thành Java object và biến Java object thành response JSON. Khi kết hợp tính năng binding thuận tiện với JPA entity nhiều field, hệ thống dễ mắc **mass assignment** (còn gọi là *over-posting*).

Tình huống xuyên suốt: hệ thống SaaS có member với các thuộc tính **id, tenantId, displayName, bio, role, active, creditLimit, passwordHash, revision**. Người dùng chỉ được sửa **displayName** và **bio** tại endpoint cập nhật hồ sơ. Kẻ tấn công thử thêm **role: "ADMIN"** hoặc **tenantId** trong JSON, mong server lưu cả những field ngoài phạm vi được phép.

Sau bài học, bạn có thể:

- Phân biệt Jackson **đọc JSON/deserialization** với **ghi JSON/serialization**.
- Hiểu **@JsonProperty(access)**, **@JsonIgnore**, **@JsonIgnoreProperties**, **@JsonView** và giới hạn bảo mật của chúng.
- Dùng request/response DTO theo **allowlist**, không bind trực tiếp entity.
- Tách validation khỏi **quyền theo object, tenant và field**.
- Chặn over-posting ở object lồng nhau, association, collection và PATCH.
- Ánh xạ lỗi HTTP đúng, viết OpenAPI 3.1 và kiểm thử điều thật sự lưu vào DB.

**Bất biến:** request có thể đến từ người dùng hợp lệ nhưng mọi field trong request vẫn là **dữ liệu không tin cậy**. Một tên thuộc tính hợp lệ về JSON không cấp quyền được cập nhật thuộc tính đó.

## 2. Jackson đọc và ghi theo chiều nào?

**Read** theo Jackson là *deserialize JSON vào Java object*, không phải HTTP GET hay SELECT DB. **Write** là *serialize Java object ra JSON*, không phải HTTP POST/PUT hay UPDATE DB.

~~~mermaid
flowchart LR
    C[JSON request từ client] --> J[Jackson deserialize/read]
    J --> DTO[Request DTO]
    DTO --> V[Validate + authorize]
    V --> S[Domain service]
    S --> DB[(Database)]
    DB --> R[Response DTO]
    R --> O[Jackson serialize/write]
    O --> C
~~~

| Công đoạn | Vai trò | Không tự thực hiện |
| --- | --- | --- |
| **Jackson deserialize** | Ánh xạ JSON → request DTO | Xác minh tenant, field-level permission |
| **Bean Validation** | @NotBlank, @Size, cấu trúc cơ bản | Kiểm tra người gọi có quyền |
| **Service authorization** | Kiểm tra principal, tenant, target và operation | Tự bảo đảm DB atomicity nếu bỏ transaction |
| **Persistence** | Ghi các field hợp lệ vào DB trong transaction | Kiểm soát contract JSON nếu bind entity trực tiếp |
| **Jackson serialize** | Response DTO → JSON | Bảo đảm dữ liệu bí mật đã được chọn lọc trước đó |

Annotation Jackson điều khiển hướng binding của một **logical property** trong ngữ cảnh ObjectMapper. Chúng không thay quyền nghiệp vụ, DB constraint, transaction hoặc kiểm soát output theo phân quyền.

## 3. Mass assignment: từ JSON hợp lệ đến thay đổi trái quyền

Ví dụ entity nội bộ:

~~~java
@Entity
public class MemberEntity {
    @Id
    private UUID id;

    private UUID tenantId;
    private String displayName;
    private String bio;
    private String role;
    private boolean active;
    private BigDecimal creditLimit;
    private String passwordHash;

    @Version
    private long revision;

    // Constructor, getters, setters...
}
~~~

**Anti-pattern, chỉ để nhận diện lỗi:**

~~~java
@PutMapping("/api/v1/members/{id}/profile")
public MemberEntity unsafeUpdate(
        @PathVariable UUID id,
        @RequestBody MemberEntity body) {

    body.setId(id);
    return memberRepository.save(body);
}
~~~

Client có thể gửi:

~~~http
PUT /api/v1/members/11111111-1111-4111-8111-111111111111/profile HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "displayName": "An",
  "bio": "Giới thiệu mới",
  "role": "ADMIN",
  "active": true,
  "creditLimit": 999999999,
  "tenantId": "22222222-2222-4222-8222-222222222222"
}
~~~

Tùy entity, accessor, constructor, ObjectMapper và JPA save/merge, những thuộc tính **ngoài ý định** có thể được deserialize rồi persist. Ngay cả khi implementation hiện tại tình cờ không ghi được một field, việc bind entity vẫn dễ trở nên nguy hiểm khi thêm property hoặc cấu hình mới.

Phân biệt hai lỗi:

- **Mass assignment:** caller chỉnh sửa **trường không được phép** như role, active, creditLimit.
- **BOLA/IDOR:** caller chỉnh sửa **đối tượng không được phép** bằng cách đổi member ID hoặc tenant ID.

**Chặn role trong JSON không thay kiểm tra quyền trên ID đích. Kiểm tra ID đích không thay kiểm soát từng field được phép sửa.**

## 4. Thiết kế hai DTO theo hợp đồng, không theo entity

### 4.1. Request DTO chỉ chứa các field người dùng được sửa

~~~java
public record UpdateMemberProfileRequest(
        @NotBlank @Size(max = 120) String displayName,
        @Size(max = 500) String bio
) {}
~~~

Một request hợp lệ:

~~~http
PUT /api/v1/members/11111111-1111-4111-8111-111111111111/profile HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "displayName": "An Nguyễn",
  "bio": "Lập trình viên Java"
}
~~~

Không có **role, tenantId, active, creditLimit, passwordHash** trong request DTO. Khi entity thêm field mới, contract input **không tự mở rộng**.

### 4.2. Response DTO chỉ công bố dữ liệu được phép thấy

~~~java
public record MemberProfileResponse(
        UUID id,
        String displayName,
        String bio,
        Instant updatedAt
) {}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "displayName": "An Nguyễn",
  "bio": "Lập trình viên Java",
  "updatedAt": "2026-11-18T10:00:00Z"
}
~~~

**Không trả entity trực tiếp** để Jackson quyết định mọi field nào được lộ. Response DTO là hợp đồng public; JPA entity chứa nhiều thứ chỉ dành cho persistence/domain.

| Cách làm | Đánh giá |
| --- | --- |
| **Request DTO allowlist** | Dễ kiểm tra input, field-level validation rõ |
| **Response DTO allowlist** | Giảm rủi ro vô tình xuất lộ dữ liệu mới |
| **Entity cho request/response** | Ít code lúc đầu, nhưng over-posting, lazy proxies, output leak |
| **Một DTO dùng mọi operation** | Dễ nhầm required, null và quyền giữa create/update/response |

Với endpoint chỉ cập nhật hai field, **hai setter tường minh** thường minh bạch và dễ audit hơn generic mapper sao chép hàng chục trường.

## 5. @JsonProperty(access): READ_ONLY, WRITE_ONLY và READ_WRITE

Jackson cung cấp các chế độ truy cập:

| Chế độ | JSON request → Java | Java → JSON response |
| --- | --- | --- |
| **AUTO** | Theo accessor/visibility | Theo accessor/visibility |
| **READ_ONLY** | Không deserialize field này | Serialize field này |
| **WRITE_ONLY** | Deserialize field này | Không serialize field này |
| **READ_WRITE** | Deserialize | Serialize |

Ví dụ **minh họa hướng**, không khuyến nghị dùng một DTO đa mục đích cho toàn bộ nghiệp vụ:

~~~java
public record AccessDirectionExample(
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        UUID id,

        @JsonProperty(access = JsonProperty.Access.READ_WRITE)
        String displayName,

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String temporarySecret
) {}
~~~

- **id** có thể xuất hiện trong output nhưng Jackson không nhận giá trị field này từ request.
- **temporarySecret** có thể nhận từ request nhưng không xuất trong output của ObjectMapper.
- **displayName** đi được cả hai chiều.

**Quan trọng:** READ_ONLY có thể làm client gửi id nhưng Jackson **bỏ qua** thay vì trả lỗi. Nếu API muốn trả **400 cho field không được phép**, cần strict binding/validation và test hành vi; annotation READ_ONLY tự nó chưa phải chính sách từ chối.

WRITE_ONLY đối với password/secret **không** thay cho hash, storage encryption, permission và việc không log raw request. Nếu response DTO không có secret thì còn an toàn hơn.

### 5.1. @JsonIgnore và @JsonIgnoreProperties

~~~java
public class InternalExample {
    @JsonIgnore
    private String internalNote;

    // Accessors...
}
~~~

**@JsonIgnore** thường ẩn một logical property ở cả hai chiều. Với phối hợp field/getter/setter/creator, annotation trên một phần accessor có thể tạo tình huống tinh tế; hãy test bằng ObjectMapper thực tế.

~~~java
@JsonIgnoreProperties(
        value = {"internalState"},
        allowGetters = true)
public class ReadOnlyExample {
    private String internalState;

    // Accessors...
}
~~~

**allowGetters = true** cho phép xuất getter của property bị ignore, cho hiệu ứng hướng **read-only theo Jackson**; **allowSetters = true** cho phép input setter dù property bị ignore khi serialize. Các annotation này có thể hữu dụng nhưng khó review hơn hai DTO riêng khi quyền input/output khác nhiều.

**@JsonIgnoreProperties(ignoreUnknown = true)** cho phép bỏ qua property không được nhận diện. Nó hỗ trợ tolerance với một số client/nguồn JSON, nhưng cũng làm payload **role** lạ biến mất âm thầm. Với request nhạy cảm, thường nên từ chối unknown fields, không dùng ignoreUnknown làm biện pháp bảo mật.

### 5.2. Những annotation dễ bị hiểu sai

- **@JsonInclude(NON_NULL)** thay cách ghi field null ra JSON, **không** chặn input.
- **@JsonView** giúp chia view khi serialize/deserialize; cấu hình view/default inclusion sai có thể làm rò field. Không nên dùng làm ranh giới phân quyền chính.
- **@JsonAlias** mở rộng các tên JSON được nhận khi deserialize; có thể tăng bề mặt đầu vào.
- **@JsonAnySetter** nhận property lạ vào map; nếu dùng cần giới hạn key, value, số lượng và quyền.
- **@JsonProperty(access=READ_ONLY)** chỉ tác động JSON binding, không ngăn service/persistence tự cập nhật entity từ nguồn khác.

## 6. Spring MVC: @RequestBody khác @ModelAttribute

| Đầu vào | Cơ chế Spring | Cần giới hạn bằng |
| --- | --- | --- |
| **@RequestBody** JSON | HttpMessageConverter/Jackson | DTO, ObjectMapper, validation, service authorization |
| **@ModelAttribute** form/query | WebDataBinder/BeanWrapper | Allowed fields, DTO, validation, authorization |
| **@PathVariable/@RequestParam** | ConversionService | Type checking và quyền trên target |
| Multipart part JSON | Converter của part | DTO/schema riêng, quota và authorization |

**WebDataBinder#setAllowedFields** chủ yếu kiểm soát binding qua DataBinder (chẳng hạn @ModelAttribute). **@InitBinder allowedFields không phải bộ lọc JSON được Jackson deserialize qua @RequestBody.** Không coi việc thêm @InitBinder vào controller là đã khóa tất cả input fields của JSON.

### 6.1. Unknown field và ignored field phải được phân biệt

Spring Boot có thể cấu hình Jackson bỏ qua unknown properties mặc định. Nếu contract công bố object đóng, cần thực thi policy rõ ràng.

Ví dụ cấu hình toàn ứng dụng:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Hoặc customizer:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer strictJson() {
    return builder -> builder.featuresToEnable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
}
~~~

**Đây là cấu hình minh họa**, cần test và đánh giá tương thích khi bật toàn bộ ứng dụng. Property **được cố ý ignore** có thể chịu **FAIL_ON_IGNORED_PROPERTIES** và cơ chế annotation khác, không phải lúc nào cũng bị bắt bởi FAIL_ON_UNKNOWN_PROPERTIES. Viết test riêng cho trường **id, role, tenantId** để chứng minh API từ chối hay bỏ qua theo contract, không đoán.

### 6.2. Jackson coercion và kiểu JSON

Một số cấu hình cho phép chuyển string thành số/boolean, đọc enum từ tên alias hoặc xử lý empty string đặc biệt. Đối với field liên quan quyền/tài chính, cần test payload sai kiểu, null, array/object bất ngờ, và cấu hình coercion theo phiên bản thư viện. **@NotNull không đủ chứng minh JSON ban đầu thuộc đúng type**.

## 7. Controller, domain service và mapping tường minh

~~~java
@RestController
@RequestMapping("/api/v1/members")
public class MemberProfileController {
    private final MemberProfileService profiles;

    public MemberProfileController(MemberProfileService profiles) {
        this.profiles = profiles;
    }

    @PutMapping(
        path = "/{id}/profile",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<MemberProfileResponse> replaceProfile(
            @PathVariable UUID id,
            @Valid @RequestBody UpdateMemberProfileRequest body,
            Authentication authentication) {

        MemberProfileResponse updated =
            profiles.replaceAuthorized(id, body, authentication);
        return ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .body(updated);
    }
}
~~~

Service phải lấy tenant từ **principal đã được xác minh**, không từ input body:

~~~java
@Service
public class MemberProfileService {
    private final MemberRepository members;
    private final AccessPolicy access;

    public MemberProfileService(
            MemberRepository members, AccessPolicy access) {
        this.members = members;
        this.access = access;
    }

    @Transactional
    public MemberProfileResponse replaceAuthorized(
            UUID id,
            UpdateMemberProfileRequest body,
            Authentication principal) {

        UUID tenantId = access.requireTenant(principal);
        MemberEntity member = members
            .findByIdAndTenantId(id, tenantId)
            .orElseThrow(MemberNotVisibleException::new);

        access.requireCanEditProfile(principal, member);

        // Allowlist rõ: chỉ cập nhật hai field này.
        member.setDisplayName(body.displayName());
        member.setBio(body.bio());

        return new MemberProfileResponse(
            member.getId(), member.getDisplayName(),
            member.getBio(), member.getUpdatedAt());
    }
}
~~~

**Các class MemberRepository/AccessPolicy/MemberNotVisibleException cần được định nghĩa ở ứng dụng thật; code là skeleton, không phải project compile độc lập.** Nếu **updatedAt** chỉ đổi nhờ DB trigger khi flush, phải refresh hoặc chọn thời điểm ứng dụng quản lý để không trả timestamp cũ. Spring transaction thường commit trước khi controller nhận kết quả từ service proxy; mọi lỗi commit cần được xử lý thích hợp.

### 7.1. Vì sao generic mapper dễ gây lỗi?

~~~java
// Không dùng kiểu sao chép rộng từ untrusted input vào entity:
BeanUtils.copyProperties(request, memberEntity);
~~~

Nếu developer thêm field mới trùng tên vào DTO/entity, câu copy có thể tự ghi trường trước đây bị cấm. **MapStruct** hỗ trợ mapping có kiểm soát nhưng phải review annotation, generated code và chính sách target properties. Với hai field hồ sơ, setter tường minh là lựa chọn dễ kiểm chứng.

### 7.2. Endpoint quản trị phải riêng

Nếu admin được phép thay role, dùng endpoint như **PATCH /api/v1/admin/members/{id}/role**, DTO chỉ có field role và service kiểm tra scope/role/tenant tương ứng. Prefix **/admin** không tự cấp quyền; không tin cờ **isAdmin** do client gửi. Ghi audit ai đổi vai trò nào, ở tenant nào, và cân nhắc optimistic concurrency/idempotency theo quy tắc nghiệp vụ.

## 8. Mass assignment qua nested object và association

Một request top-level có DTO đúng vẫn có thể nguy hiểm nếu field con bind thẳng entity hoặc chấp nhận ID của người khác:

~~~json
{
  "displayName": "An",
  "addresses": [{
    "id": "another-user-address-id",
    "ownerId": "victim-user-id",
    "isPrimary": true
  }]
}
~~~

**Không bao giờ attach/save nguyên graph entity từ JSON.** Nếu client chọn addressId, service phải kiểm tra **addressId + parent member ID + tenantId**; một UUID hợp lệ không chứng minh quyền sử dụng association. Mỗi object con cần DTO allowlist, ràng buộc field-level authorization, maxItems/độ sâu/body size. Với JPA, đặc biệt cẩn trọng cascade MERGE/ALL trên entity graph được tạo từ dữ liệu không tin cậy.

Những flag như ownerId, tenantId, isPrimary, priceCalculated phải do service xác định hoặc qua **operation riêng** có quyền tương ứng. Kiểm quyền một lần cho object cha chưa đủ nếu nested reference trỏ sang tenant khác.

## 9. PUT/PATCH: missing, null và giá trị cụ thể

Ba body sau không có cùng ý nghĩa:

~~~json
{}
~~~

~~~json
{"bio":null}
~~~

~~~json
{"bio":"Đã cập nhật"}
~~~

Một **String bio** trong DTO thường không phân biệt được **field vắng mặt** và **explicit null** sau Jackson binding.

- Với **PUT**, hợp đồng phải quy định nếu bio vắng mặt thì được xóa, giữ hay bị từ chối. Service ví dụ ở mục 7 chọn **gán null** khi bio không được gửi.
- Với **application/merge-patch+json (RFC 7396)**, **vắng mặt** nghĩa là giữ nguyên; **null** nghĩa là **loại bỏ member** của JSON object đích.
- Với **application/json-patch+json (RFC 6902)**, request gồm các operation; **remove** xóa field, **replace** có thể ghi null nếu schema cho phép.

~~~http
PATCH /api/v1/members/11111111-1111-4111-8111-111111111111/profile HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/merge-patch+json
If-Match: "member-profile-r12"

{"bio":null}
~~~

Không merge JSON Patch/Merge Patch trực tiếp vào **MemberEntity**, vì client có thể gửi role hoặc đường dẫn tới nested object nhạy cảm. Có thể nhận **JsonNode** để giữ được dấu hiệu field có mặt và kiểm allowlist:

~~~java
private static final Set<String> PATCHABLE =
    Set.of("displayName", "bio");

void checkPatchFields(JsonNode patch) {
    if (!patch.isObject()) {
        throw new InvalidPatchException("Object required");
    }
    Iterator<String> names = patch.fieldNames();
    while (names.hasNext()) {
        if (!PATCHABLE.contains(names.next())) {
            throw new InvalidPatchException("Field not patchable");
        }
    }
}
~~~

Đây **chỉ là bước kiểm tên**. Sau đó phải validate type/null/độ dài, quyền từng field và tính nguyên tử. JSON Patch cần allowlist cả **operation, path, from và value**; kiểm JSON Pointer lồng nhau. Khi dùng If-Match chống lost update, DB cần **@Version hoặc UPDATE WHERE revision=?**, không chỉ check ETag rồi ghi vô điều kiện.

## 10. Validation không thay authorization

**@Valid @RequestBody** kích hoạt Bean Validation với cấu hình phù hợp, nhưng annotation trên DTO chỉ kiểm dữ liệu, không cấp quyền.

- **@NotBlank** chặn null, empty, string toàn khoảng trắng.
- **@Size(max=500)** cho phép null nhưng giới hạn độ dài string khi có giá trị.
- **@Email** kiểm hình thức email, không xác minh caller sở hữu email.
- **@Positive/@Min** kiểm số, không xác nhận quyền sửa hạn mức tiền.
- **@NotNull** kiểm Java value sau binding, không luôn chứng minh JSON gốc đúng kiểu khi có Jackson coercion.
- **record immutable** vẫn deserialize field có trong constructor; nếu đưa role vào record request, immutable không giúp chặn role.

Một payload hợp schema vẫn có thể bị **403/404** khi target thuộc tenant khác, **409** khi state cấm update hoặc **412** khi If-Match không khớp. Không gộp các lỗi đó thành 400.

## 11. Lỗi HTTP và Problem Details

| Điều kiện | HTTP status |
| --- | --- |
| JSON sai cú pháp, sai kiểu, field lạ bị cấm | **400 Bad Request** |
| displayName không đạt validation | **400** hoặc 422 theo contract |
| Không có credential hợp lệ | **401 Unauthorized** |
| Không đủ quyền theo user/tenant | **403** hoặc 404 theo privacy policy |
| Member không tồn tại trong scope | **404 Not Found** |
| Trạng thái nghiệp vụ ngăn chỉnh sửa | **409 Conflict** |
| If-Match không thỏa | **412 Precondition Failed** |
| Thiếu If-Match khi bắt buộc | **428 Precondition Required** |
| DB timeout/sự cố hệ thống | **5xx** phù hợp, không giả dạng 400/412 |

Lỗi có cấu trúc theo **RFC 9457**:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/forbidden-field",
  "title": "Invalid request field",
  "status": 400,
  "code": "FIELD_NOT_ALLOWED",
  "violations": [
    {"field": "role", "message": "Trường nằm ngoài hợp đồng profile"}
  ]
}
~~~

Không echo raw value của password, token, rejected secret hay payload cá nhân trong lỗi. Với lỗi Bean Validation, Spring hỗ trợ **ProblemDetail**:

~~~java
@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalidInput(
            MethodArgumentNotValidException ex) {
        ProblemDetail pd =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        pd.setTitle("Request validation failed");
        pd.setProperty("code", "VALIDATION_FAILED");
        return ResponseEntity.badRequest().body(pd);
    }
}
~~~

Ứng dụng thật cần thêm mapping cho **HttpMessageNotReadableException**, unknown/ignored field, domain errors và security filter. **@RestControllerAdvice không tự xử lý mọi 401/403 ở Spring Security filter hoặc gateway**. Cần cùng error policy trên mọi tầng.

## 12. OpenAPI 3.1: tách request và response schema

~~~yaml
openapi: 3.1.0
info:
  title: Member Profile API
  version: 1.0.0
paths:
  /api/v1/members/{id}/profile:
    parameters:
      - in: path
        name: id
        required: true
        schema: { type: string, format: uuid }
    get:
      operationId: getProfile
      security: [{ bearerAuth: [] }]
      responses:
        '200':
          description: Hồ sơ được phép đọc
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProfileResponse'
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '404': { description: Không tìm thấy }
    put:
      operationId: replaceProfile
      security: [{ bearerAuth: [] }]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateProfileRequest'
      responses:
        '200':
          description: Đã cập nhật
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProfileResponse'
        '400':
          description: JSON sai hoặc field ngoài hợp đồng
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '404': { description: Không tìm thấy }
        '409': { description: Xung đột nghiệp vụ }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer, bearerFormat: JWT }
  schemas:
    UpdateProfileRequest:
      type: object
      required: [displayName]
      additionalProperties: false
      properties:
        displayName: { type: string, minLength: 1, maxLength: 120 }
        bio: { type: [string, 'null'], maxLength: 500 }
    ProfileResponse:
      type: object
      required: [id, displayName, updatedAt]
      additionalProperties: false
      properties:
        id: { type: string, format: uuid, readOnly: true }
        displayName: { type: string }
        bio: { type: [string, 'null'] }
        updatedAt: { type: string, format: date-time, readOnly: true }
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
        detail: { type: string }
        violations:
          type: array
          items:
            type: object
            required: [field, message]
            properties:
              field: { type: string }
              message: { type: string }
~~~

**OpenAPI readOnly/writeOnly là metadata hợp đồng, không tự cấu hình Jackson hay authorization.** **additionalProperties: false** cũng không tự khiến Spring từ chối field lạ nếu runtime đang ignore unknown properties.

**Chú ý:** OpenAPI **minLength: 1** không cấm string chỉ có khoảng trắng, còn Java **@NotBlank** cấm. Nếu cần hợp đồng khớp tuyệt đối, thêm ràng buộc phù hợp hoặc schema validation đã được test; đừng coi chúng tương đương.

## 13. Ma trận kiểm thử chống mass assignment

| ID | Test | Kỳ vọng |
| --- | --- | --- |
| M01 | PUT displayName/bio hợp lệ | 200, chỉ hai field được sửa |
| M02 | Gửi role=ADMIN | 400 và DB role giữ nguyên |
| M03 | Gửi tenantId giả | 400, tenantId không đổi |
| M04 | Gửi active/creditLimit | 400, protected fields giữ nguyên |
| M05 | Gửi passwordHash hoặc id trong body | Không bind, không log secret |
| M06 | JSON sai cú pháp, sai kiểu hoặc unknown key | 400 theo strict contract |
| M07 | displayName null/blank/quá 120 ký tự | 400 |
| M08 | bio null hoặc không gửi | Đúng semantics PUT đã công bố |
| M09 | Tenant A sửa member B | 403/404, DB không đổi |
| M10 | User edit profile nhưng không được edit role | Không leo thang quyền |
| M11 | Nested address/ownerId trái tenant | Từ chối, kiểm từng association |
| M12 | PATCH /role hoặc Merge Patch role | Từ chối theo allowlist |
| M13 | @JsonProperty READ_ONLY/WRITE_ONLY | Binding/serialization đúng cấu hình |
| M14 | Response không lộ tenantId, role, passwordHash | Đúng DTO allowlist |
| M15 | Entity thêm field mới | Không tự mở input/output |
| M16 | Error/log/trace | Không lộ token, plaintext secret |

### 13.1. Test MockMvc và database fixture

~~~java
@Test
void rejectsRoleAndDoesNotAlterStoredRole() throws Exception {
    UUID id = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");

    mvc.perform(put("/api/v1/members/{id}/profile", id)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "An",
                  "bio": "Java",
                  "role": "ADMIN"
                }
                """))
        .andExpect(status().isBadRequest());

    assertThat(memberRepository.findById(id).orElseThrow()
            .getRole()).isEqualTo("MEMBER");
}
~~~

Cần DB fixture role MEMBER và token đủ quyền. Test chỉ mock service trả 400 **không chứng minh mass assignment không ghi DB**. Với unit test Jackson, serialize AccessDirectionExample và assert **temporarySecret không xuất**; deserialize id READ_ONLY để xác minh ignore/reject theo ObjectMapper thật.

## 14. Tiến hóa schema và quan sát

Bổ sung field **timezone** cần cập nhật **request DTO, validator, mapper, OpenAPI và tests** cùng lúc. Admin cần sửa active/role thì thêm **operation và policy riêng**, không mở rộng profile request chung cho mọi user.

- Chuyển từ ignore unknown sang strict 400 có thể làm client cũ gửi extension field gặp lỗi.
- Thêm required field có thể breaking; thêm optional field vẫn cần xác minh default.
- **@JsonAlias/@JsonProperty** có thể mở rộng tên JSON được nhận, ảnh hưởng compatibility và input surface.
- Đổi **@JsonInclude** có thể khiến response từ null thành missing, tác động SDK.
- Thêm property vào JPA entity không được làm thay đổi public JSON contract.

Audit **actor, tenant, resource, action, outcome, request ID** nhưng không log plaintext token, password hay dữ liệu nhạy cảm không cần thiết. Metrics theo route template/error code thay vì user ID/raw JSON nhằm giảm cardinality và rò PII.

## 15. Bài thực hành: SaaS Workspace Member

Entity có **id, tenantId, displayName, timezone, role, isSuspended, billingLimit, passwordHash, revision**. User chỉ được đổi displayName/timezone; workspace admin có operation riêng thay role.

**Yêu cầu (100 điểm):** (1) **Contract – 25:** request/response DTO tách biệt và OpenAPI 3.1 có additionalProperties false. (2) **Spring – 30:** controller @Valid @RequestBody, service lấy tenant từ principal, mapper chỉ thay hai field; giải thích READ_ONLY/WRITE_ONLY. (3) **Security – 25:** chặn role=OWNER, billingLimit, tenantId giả, ownerId nested; thiết kế admin role endpoint có audit. (4) **Tests – 20:** tối thiểu tám test về over-posting, cross-tenant, null/blank, unknown, PATCH path và response không lộ secret.

**Hướng giải:** request DTO chỉ displayName/timezone, response DTO chỉ thông tin công khai. Service load member bằng id + tenantId, kiểm quyền rồi chỉ set hai field. Strict unknown-field policy khiến role/tenantId lạ bị 400; nếu cố tình ignore thay vì reject, vẫn phải chứng minh DB không đổi. Endpoint admin có DTO và policy riêng.

## 16. Checklist và tài liệu

- [ ] Phân biệt **Jackson read/deserialization** và **write/serialization**.
- [ ] Hiểu READ_ONLY, WRITE_ONLY, @JsonIgnore, @JsonIgnoreProperties, @JsonView.
- [ ] Jackson annotation không tự cấp quyền field/domain.
- [ ] Request/response DTO là allowlist theo operation.
- [ ] Không bind JPA entity hay dùng generic BeanUtils.copyProperties từ request.
- [ ] Kiểm principal/tenant/target/field trước khi thay đổi.
- [ ] Association/nested data có ownership validation.
- [ ] PUT/PATCH xử lý missing, null, value theo media type.
- [ ] Unknown/ignored field policy được test bằng ObjectMapper thật.
- [ ] Validation và Problem Details khớp OpenAPI.
- [ ] WRITE_ONLY không thay hashing; không log secret.
- [ ] Integration tests chứng minh protected fields **không thay đổi ở DB**.

**Ghi nhớ:** **mass assignment là lỗ hổng quyền cập nhật dữ liệu**, không chỉ là lỗi parser. Annotation Jackson hỗ trợ điều khiển chiều đọc/ghi, nhưng phòng vệ bền vững là **DTO allowlist, service authorization, mapper tường minh, transaction và kiểm thử đầu-cuối**.

### Nguồn chuẩn

- **Jackson Databind:** JsonProperty.Access, JsonIgnore, JsonIgnoreProperties, JsonView, DeserializationFeature.
- **Spring Framework / Boot:** @RequestBody, HttpMessageConverter, DataBinder, @RestControllerAdvice, Spring Security.
- **Jakarta Bean Validation:** @Valid, @NotBlank, @Size.
- **OpenAPI 3.1 / JSON Schema 2020-12:** readOnly, writeOnly, additionalProperties.
- **RFC 9110, RFC 9457:** HTTP semantics, Problem Details.
- **RFC 7396, RFC 6902:** JSON Merge Patch và JSON Patch.
