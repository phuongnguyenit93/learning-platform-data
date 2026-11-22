# Response schema chỉ trả field được phép

Một API có thể xác thực người gọi đúng, kiểm tra quyền đọc đối tượng đúng nhưng vẫn làm lộ dữ liệu nếu response trả quá nhiều thuộc tính. Ví dụ, endpoint hồ sơ chỉ cần trả tên hiển thị và ảnh đại diện nhưng lại serialize toàn bộ entity `User`, bao gồm email riêng tư, số điện thoại, trạng thái xác minh, ghi chú nội bộ hoặc thông tin quản trị. Client có thể đọc các trường này ngay cả khi giao diện không hiển thị chúng.

**Output filtering** là quá trình giới hạn dữ liệu được đưa vào response theo hợp đồng API, quyền của người gọi và ngữ cảnh nghiệp vụ. Response schema cần mô tả rõ những field được phép xuất hiện; server phải tạo response theo allowlist và chỉ đưa dữ liệu cần thiết vào đó. Không nên xem việc ẩn field trên frontend hoặc việc client bỏ qua field không dùng là biện pháp bảo vệ.

Trong API Security, bảo vệ output là một phần của property-level authorization và data minimization. Quyền đọc một object không đồng nghĩa với quyền đọc mọi thuộc tính của object đó. Mỗi endpoint cần xác định field nào được trả, cho principal nào, trong tình huống nào và qua kênh nào.

## 1. Vì sao cần lọc response?

Nhiều framework có thể tự động chuyển object thành JSON hoặc XML. Nếu controller trả trực tiếp entity hoặc model nội bộ, serializer có thể đưa ra mọi thuộc tính công khai, kể cả những trường không được thiết kế cho consumer.

Ví dụ entity tài khoản có thể chứa:

```java
public class UserAccount {
    private UUID id;
    private String username;
    private String displayName;
    private String email;
    private String phone;
    private String passwordHash;
    private String mfaSecret;
    private String role;
    private UUID tenantId;
    private boolean verified;
    private String internalNote;
    private Instant createdAt;
}
```

Endpoint `GET /api/me` có thể chỉ cần `id`, `username` và `displayName`. Nếu trả entity trực tiếp, thay đổi nội bộ trong tương lai như thêm `mfaSecret` hoặc `internalNote` có thể vô tình mở rộng response. Đây là rủi ro overexposure, thường liên quan đến Broken Object Property Level Authorization (BOPLA).

Output filtering giúp:

- Giảm lượng dữ liệu cá nhân, bí mật và dữ liệu nội bộ được tiết lộ.
- Ngăn client suy ra thông tin qua các field không được phép đọc.
- Giữ response ổn định khi entity hoặc database thay đổi.
- Tạo hợp đồng rõ ràng cho consumer và công cụ sinh client.
- Giảm dữ liệu truyền qua mạng, cache, log, analytics và các hệ thống downstream.
- Hỗ trợ phân quyền field theo vai trò, tenant, quan hệ sở hữu và mục đích truy cập.

## 2. Phân loại field trước khi thiết kế response schema

Trước khi tạo response DTO, cần xác định mức độ nhạy cảm và đối tượng được phép đọc từng field. Một field có thể được phép với chủ tài khoản nhưng bị ẩn với người xem hồ sơ công khai; một field khác chỉ được phép với nhân viên hỗ trợ hoặc quản trị viên có quyền chuyên biệt.

| Nhóm dữ liệu | Ví dụ | Cách xử lý response |
| --- | --- | --- |
| Công khai | Tên hiển thị, ảnh đại diện công khai, mô tả sản phẩm | Trả theo schema công khai đã định nghĩa. |
| Cá nhân thông thường | Email, số điện thoại, địa chỉ | Chỉ trả khi consumer và principal có mục đích/quyền phù hợp; có thể che một phần. |
| Nhạy cảm | Số giấy tờ, dữ liệu tài chính, lịch sử giao dịch, vị trí chính xác | Giới hạn theo quyền cụ thể và nhu cầu nghiệp vụ; ghi audit khi cần. |
| Bí mật xác thực | Password hash, MFA secret, refresh token, API key | Không trả trong response API thông thường. |
| Nội bộ | Risk score, ghi chú nhân viên, policy decision, debug metadata | Chỉ dùng nội bộ hoặc endpoint vận hành riêng có quyền kiểm soát. |
| Quản trị | Role, permission, trạng thái khóa, tenant ownership | Chỉ trả qua chức năng quản trị và theo đúng phạm vi được cấp. |

Không nên chỉ dựa vào tên field để quyết định. Ví dụ `status` có thể là trạng thái đơn hàng được công khai, nhưng `accountStatus` có thể tiết lộ thông tin điều tra nội bộ. Cần xét ý nghĩa, đối tượng nhận và hậu quả nếu dữ liệu bị lộ.

### 2.1. Tách quyền đọc field khỏi quyền đọc object

Authorization ở cấp object trả lời người gọi có được xem bản ghi hay không. Property-level authorization trả lời người gọi được xem những thuộc tính nào của bản ghi.

Ví dụ:

| Principal | Object | Field được phép đọc |
| --- | --- | --- |
| Chủ tài khoản | Hồ sơ của chính mình | Tên, email, số điện thoại và các tùy chọn cá nhân cần cho ứng dụng. |
| Người xem công khai | Hồ sơ công khai | Tên hiển thị và ảnh đại diện công khai. |
| Nhân viên hỗ trợ | Hồ sơ trong phạm vi phụ trách | Thông tin liên hệ cần thiết; không mặc nhiên xem bí mật xác thực hoặc dữ liệu tài chính. |
| Quản trị viên tenant | Thành viên thuộc tenant | Field quản lý thành viên theo quyền được cấp; không xem dữ liệu ngoài tenant. |

Một principal có thể được phép đọc object nhưng chỉ được xem một phần field. Nếu endpoint trả mọi field rồi dựa vào UI để ẩn bớt, quyền đọc thực tế đã bị cấp quá rộng.

## 3. Dùng response DTO theo allowlist

Biện pháp nền tảng là không trả entity hoặc model persistence trực tiếp từ endpoint công khai. Hãy tạo response DTO riêng, chỉ khai báo các field cần thiết cho use case.

Ví dụ endpoint hồ sơ cá nhân:

```java
public record MyProfileResponse(
    UUID id,
    String username,
    String displayName,
    String email
) {}

@GetMapping("/me")
public MyProfileResponse getMyProfile(
        @AuthenticationPrincipal Jwt jwt) {
    UUID userId = UUID.fromString(jwt.getSubject());
    UserAccount user = userService.getById(userId);

    return new MyProfileResponse(
        user.getId(),
        user.getUsername(),
        user.getDisplayName(),
        user.getEmail()
    );
}
```

DTO này chỉ chứa field được endpoint công bố. Khi entity được bổ sung `passwordHash`, `mfaSecret`, `role` hoặc `internalNote`, những thuộc tính mới không tự xuất hiện trong JSON.

Ví dụ giả định JWT đã được resource server xác minh và `sub` ánh xạ đúng sang định danh user. Nếu hệ thống dùng claim khác hoặc principal riêng, hãy lấy user ID từ principal đã xác thực qua một mapper tin cậy. Không nhận `userId` tùy ý từ query/body để thay thế identity của endpoint `/me`.

### 3.1. Tách DTO theo use case

Không nên tạo một DTO lớn dùng chung cho hồ sơ cá nhân, hồ sơ công khai, màn hình hỗ trợ và màn hình quản trị. Các use case có mục đích khác nhau và được phép hiển thị các field khác nhau.

```java
public record PublicProfileResponse(
    String displayName,
    URI avatarUrl
) {}

public record MyProfileDetailsResponse(
    UUID id,
    String username,
    String displayName,
    String email,
    String phone
) {}

public record SupportProfileResponse(
    UUID id,
    String displayName,
    String maskedEmail,
    String maskedPhone,
    String accountStatus
) {}
```

Các DTO khác nhau làm rõ hợp đồng và giảm nguy cơ một endpoint vô tình trả field chỉ dành cho endpoint khác. Nếu response quản trị cần dữ liệu bổ sung, hãy đặt quyền riêng cho endpoint và DTO đó.

### 3.2. Mapping tường minh

Mapping thủ công có thể phù hợp với response nhạy cảm vì reviewer nhìn thấy rõ field nào được xuất ra. Nếu dùng MapStruct hoặc thư viện mapping, cần cấu hình allowlist, tránh tự động copy mọi field cùng tên từ entity.

```java
public PublicProfileResponse toPublicProfile(UserAccount user) {
    return new PublicProfileResponse(
        user.getDisplayName(),
        user.getPublicAvatarUrl()
    );
}
```

Không nên tạo một response từ entity rồi cố gắng xóa field nhạy cảm ở bước cuối. Cách denylist dễ bỏ sót khi entity có field mới; allowlist chỉ đưa các field đã được duyệt vào response.

## 4. Lọc field theo principal và ngữ cảnh

Một số endpoint có response thay đổi theo quyền. Có thể dùng mapper hoặc projection nhận principal và policy để quyết định field nào được đưa vào DTO.

Ví dụ màn hình hồ sơ nội bộ có thể trả email đã che cho nhân viên hỗ trợ, nhưng chỉ trả email đầy đủ cho chủ tài khoản hoặc nhân viên có quyền xem thông tin liên hệ:

```java
public record AccountView(
    UUID id,
    String displayName,
    String email,
    String accountStatus
) {}

public AccountView toAccountView(
        UserAccount account,
        ApiPrincipal actor) {

    boolean canReadEmail = accountPolicy.canReadEmail(actor, account);
    boolean canReadStatus = accountPolicy.canReadAccountStatus(actor, account);

    return new AccountView(
        account.getId(),
        account.getDisplayName(),
        canReadEmail ? account.getEmail() : null,
        canReadStatus ? account.getAccountStatus().name() : null
    );
}
```

Đây là ví dụ minh họa. Trong API thực tế, cần xác định rõ `null` có nghĩa là field bị ẩn hay giá trị thực sự không tồn tại. Nếu consumer cần phân biệt hai trường hợp, có thể dùng các response schema riêng, field optional hoặc một cấu trúc biểu diễn trạng thái rõ ràng. Không trả `null` một cách mơ hồ nếu điều đó làm lộ sự tồn tại của field hoặc gây hiểu nhầm.

### 4.1. Field có quyền đọc nhưng không được công bố trong mọi response

Một field có thể được phép đọc trong một use case nhưng không cần thiết trong use case khác. Ví dụ, nhân viên hỗ trợ được phép xem email để xử lý ticket, nhưng danh sách user dùng cho dashboard không cần trả email. Quyền đọc không buộc API phải trả field đó ở mọi response.

Data minimization nên là nguyên tắc mặc định: chỉ trả dữ liệu tối thiểu để consumer hoàn thành nhiệm vụ. Nếu consumer cần thêm field, hãy xác định use case và quyền tương ứng, sau đó mở rộng contract có chủ đích.

## 5. Truy vấn dữ liệu theo đúng projection

Lọc ở response DTO giúp tránh serialize thừa, nhưng đôi khi database vẫn tải toàn bộ entity và dữ liệu nhạy cảm vào memory. Với endpoint danh sách hoặc báo cáo lớn, nên chọn projection chỉ lấy các cột cần thiết.

Ví dụ với Spring Data JPA:

```java
public interface PublicUserProjection {
    UUID getId();
    String getDisplayName();
    String getAvatarUrl();
}

public interface UserRepository extends JpaRepository<UserAccount, UUID> {
    @Query("""
        select u.id as id,
               u.displayName as displayName,
               u.publicAvatarUrl as avatarUrl
        from UserAccount u
        where u.id = :id
        """)
    Optional<PublicUserProjection> findPublicViewById(@Param("id") UUID id);
}
```

Projection giảm dữ liệu được đọc từ database và giúp tách read model khỏi entity. Tuy nhiên, projection không tự thực hiện authorization: query vẫn phải giới hạn theo tenant, ownership hoặc policy cần thiết. Không dùng projection công khai nếu endpoint yêu cầu field khác hoặc quyền khác.

Với truy vấn danh sách, tránh N+1 query khi mapper đọc quan hệ lồng nhau. Có thể dùng projection, fetch join có kiểm soát hoặc batch loading. Cần bảo đảm tối ưu hiệu năng không khiến query tải thêm dữ liệu nhạy cảm ngoài nhu cầu.

## 6. Kiểm soát object lồng nhau, collection và phân trang

Response có thể chứa quan hệ lồng nhau như order/customer/items/payment, project/members/documents hoặc user/roles. Mỗi object con có thể có quyền đọc và field allowlist riêng.

Ví dụ response đơn hàng cho khách hàng có thể gồm:

```json
{
  "id": "order-123",
  "status": "PROCESSING",
  "items": [
    {
      "productName": "Keyboard",
      "quantity": 1
    }
  ],
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
```

Response này không cần trả `supplierCost`, `fraudScore`, `internalNote`, thông tin tài khoản nhân viên hoặc token thanh toán. Không serialize toàn bộ graph entity rồi trông chờ annotation tự loại bỏ mọi trường nhạy cảm.

### 6.1. Mỗi phần tử trong collection phải được lọc

Endpoint trả danh sách cần bảo đảm tất cả phần tử đều nằm trong phạm vi object authorization và được ánh xạ qua schema phù hợp. Không chỉ kiểm tra quyền trên collection cha rồi trả mọi bản ghi con.

Với bulk response hoặc export, áp dụng cùng policy như endpoint đọc từng object. Một báo cáo có thể chứa hàng nghìn bản ghi; cần kiểm tra quyền trên từng tenant/object và field, đồng thời giới hạn số lượng, kích thước và thời gian xử lý.

### 6.2. Pagination và metadata

Metadata phân trang cũng có thể tiết lộ thông tin. Ví dụ `totalElements` có thể cho biết số lượng tài khoản hoặc đơn hàng của tenant khác nếu count query không có cùng filter với query dữ liệu. `nextCursor` có thể chứa ID nội bộ hoặc thông tin truy vấn.

Count, cursor và page token phải được tạo từ cùng phạm vi authorization với dữ liệu. Cursor nên được ký hoặc mã hóa nếu chứa thông tin cần bảo vệ; server vẫn phải xác minh quyền khi client gửi cursor trở lại. Không xem cursor khó đoán là bằng chứng authorization.

## 7. Response schema trong OpenAPI

Response schema là hợp đồng công khai cho consumer. Nó cần liệt kê field được phép, kiểu dữ liệu, nullability, định dạng và ý nghĩa. Với JSON Schema/OpenAPI 3.1, có thể dùng `additionalProperties: false` để thể hiện object không cho phép field ngoài schema.

Ví dụ:

```yaml
openapi: 3.1.0
info:
  title: Profile API
  version: 1.0.0
paths:
  /api/me:
    get:
      summary: Get the current user's public profile fields
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Current user's profile view
          content:
            application/json:
              schema:
                type: object
                additionalProperties: false
                required: [id, username, displayName]
                properties:
                  id:
                    type: string
                    format: uuid
                  username:
                    type: string
                  displayName:
                    type: string
                  email:
                    type: string
                    format: email
                    description: Returned only when the caller is allowed to read it.
        '401':
          description: Missing or invalid access token
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

Schema trên minh họa response allowlist. Nếu `email` chỉ xuất hiện với một số principal, contract cần mô tả điều kiện đó rõ ràng hoặc tách response theo use case/role. OpenAPI mô tả hợp đồng nhưng không tự lọc response ở runtime; implementation phải tạo đúng schema.

### 7.1. Schema nghiêm ngặt và khả năng tương thích

`additionalProperties: false` giúp phát hiện field ngoài hợp đồng trong kiểm thử và validation. Tuy nhiên, cần đánh giá cách consumer xử lý schema khi API mở rộng. Với response nhạy cảm, việc kiểm soát chặt field thường hữu ích để tránh lộ dữ liệu ngoài dự kiến. Khi thêm field mới, phải xác định ai được đọc và liệu có cần version hoặc permission mới.

Không đưa field nội bộ vào OpenAPI công khai chỉ để consumer “không dùng đến”. Một field đã công bố có thể được consumer lưu lại hoặc sử dụng sau này; việc loại bỏ về sau có thể gây breaking change và vẫn không xóa được dữ liệu đã bị thu thập.

## 8. Các cách lọc không nên dùng làm lớp bảo vệ chính

### 8.1. Chỉ ẩn field ở frontend

Frontend có thể không hiển thị `internalNote`, nhưng nếu response chứa field đó thì người dùng vẫn có thể xem qua browser devtools, proxy hoặc script. Mọi quyết định về dữ liệu được phép đọc phải thực hiện ở server.

### 8.2. Trả entity rồi dùng annotation một cách tùy tiện

Các annotation như `@JsonIgnore`, `@JsonView` hoặc `@JsonProperty(access = READ_ONLY)` có thể hỗ trợ serialization, nhưng dễ bị cấu hình sai khi entity được dùng ở nhiều endpoint hoặc cả chiều input lẫn output. `@JsonIgnore` có thể ảnh hưởng cả deserialize; `READ_ONLY` không thay thế authorization theo principal.

Có thể dùng annotation như lớp phòng vệ bổ sung cho field tuyệt đối không được công bố, nhưng response DTO riêng vẫn nên là ranh giới chính giữa domain/persistence và API contract.

### 8.3. Xóa field sau khi serialize

Không nên serialize toàn bộ object rồi dùng regex, map mutation hoặc bộ lọc chuỗi để xóa tên field nhạy cảm. Cách này dễ lỗi với nested object, tên field trùng, kiểu dữ liệu và response format khác. Dữ liệu cũng đã có thể xuất hiện trong log hoặc bộ nhớ trung gian trước khi bị xóa.

### 8.4. Dùng denylist thay allowlist

Denylist kiểu “trả tất cả trừ password và secret” có nguy cơ bỏ sót field mới như `recoveryCode`, `riskScore`, `privateMetadata` hoặc `internalComment`. Allowlist chỉ xuất những field đã được xác định cho endpoint và principal.

## 9. Bảo vệ output ngoài response body

Output không chỉ là JSON body. HTTP status, headers, cookies, file download, redirect, cache và error message cũng có thể làm lộ thông tin.

### 9.1. Error response

Không trả stack trace, SQL query, đường dẫn file nội bộ, tên bảng, secret hoặc chi tiết cấu hình trong response lỗi. Dùng error schema ổn định gồm code, message an toàn và correlation ID.

```json
{
  "code": "RESOURCE_NOT_AVAILABLE",
  "message": "The requested resource is not available.",
  "correlationId": "corr-01JXYZ8K"
}
```

Thông tin chi tiết để debug nên được ghi vào log có kiểm soát, gắn correlation ID và không chứa credential hoặc payload nhạy cảm nguyên vẹn. Với tài nguyên cần che giấu sự tồn tại, có thể trả cùng một error shape cho trường hợp không tồn tại và trường hợp caller không được phép.

### 9.2. Headers và cookies

Không đưa token, secret hoặc dữ liệu cá nhân vào response header không cần thiết. Cookie phiên cần các thuộc tính phù hợp như `HttpOnly`, `Secure`, `SameSite` và phạm vi `Path`/`Domain` hẹp. Không phản chiếu header tùy ý do client gửi vào response.

Header `Server`, debug header hoặc header nội bộ có thể tiết lộ phiên bản và topology; chỉ công bố khi có lý do vận hành rõ ràng. CORS không phải output authorization: cho phép browser đọc response từ origin nào không quyết định người gọi có quyền đọc field nào.

### 9.3. Cache và dữ liệu theo người dùng

Response chứa dữ liệu cá nhân hoặc dữ liệu phụ thuộc principal/tenant cần chính sách cache phù hợp. Có thể dùng `Cache-Control: no-store` cho dữ liệu nhạy cảm. Nếu cho phép cache, cache key và phạm vi cache phải tách biệt theo identity/tenant và mọi lần đọc vẫn cần bảo đảm authorization.

Không dựa vào URL giống nhau để chia sẻ cache response giữa nhiều user nếu body phụ thuộc quyền. CDN hoặc reverse proxy cấu hình sai có thể trả response của Alice cho Bob dù backend đã kiểm tra quyền đúng.

### 9.4. File download và export

Endpoint tải file cần kiểm tra quyền trên object và nội dung file trước khi stream hoặc phát hành signed URL. Tên file, `Content-Disposition`, MIME type và metadata cũng cần được kiểm soát để không lộ path nội bộ hoặc dữ liệu nhạy cảm. Export phải áp dụng allowlist field tương tự response API và có giới hạn kích thước, số bản ghi cùng thời gian lưu file.

## 10. GraphQL và API có field selection

GraphQL cho phép client chọn field trong query, nhưng việc client chỉ yêu cầu field nào không thay thế authorization. Resolver cần kiểm tra quyền đọc field nhạy cảm và quyền trên từng object. Nếu resolver trả nguyên entity hoặc một object có nhiều thuộc tính, schema có thể vô tình làm lộ field khi được thêm vào query.

Với GraphQL:

- Áp dụng authorization trong resolver hoặc lớp policy/service dùng chung, không chỉ ẩn field trong UI.
- Kiểm tra quyền trên object và nested relation; không cho phép truy vấn node ID để vượt tenant boundary.
- Giới hạn query depth, complexity, alias và số phần tử để tránh resource exhaustion.
- DataLoader phải giữ đúng security context và không chia sẻ kết quả cache giữa principal/tenant không tương thích.
- Tránh lỗi GraphQL trả stack trace hoặc chi tiết resolver nội bộ cho client production.

Với REST có query parameter như `?fields=id,name,email`, chỉ hỗ trợ field selection nếu server có allowlist và kiểm tra quyền từng field. Không chuyển chuỗi field tùy ý thành reflection hoặc serialize toàn bộ entity theo tên thuộc tính do client chọn.

## 11. Kiểm thử response schema và rò rỉ field

Kiểm thử cần xác minh cả field được phép xuất hiện lẫn field bị cấm. Một test chỉ kiểm tra `displayName` có trong JSON không phát hiện được việc response đồng thời chứa `passwordHash`.

| Trường hợp | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Hồ sơ cá nhân | Response của chủ tài khoản | Chỉ có field trong schema cá nhân và theo quyền hiện tại. |
| Hồ sơ công khai | Response cho anonymous/public caller | Không có email, phone, tenant ID hoặc field nội bộ. |
| Nhân viên hỗ trợ | Response trong phạm vi phụ trách | Chỉ có field cần cho tác vụ hỗ trợ; dữ liệu nhạy cảm được che hoặc loại bỏ. |
| Cross-tenant | Caller truy cập object tenant khác | Không có body hoặc field tiết lộ dữ liệu ngoài phạm vi. |
| Nested object | Order/customer/payment/items | Mỗi object con chỉ có field được phép; không lộ entity graph. |
| Collection/count | Danh sách và pagination metadata | Dữ liệu, count và cursor cùng tuân thủ phạm vi authorization. |
| Error | Lỗi 4xx/5xx | Không có stack trace, SQL, path hoặc secret. |
| Cache | Hai principal gọi cùng URL | Không nhận response cache thuộc principal khác. |
| Export/download | Tải file hoặc báo cáo | Kiểm tra object/field authorization và không lộ metadata nội bộ. |
| Schema drift | Entity được thêm field mới | Field mới không tự xuất hiện trong response. |

### 11.1. Ví dụ test không lộ field nhạy cảm

```java
@Test
void publicProfileDoesNotExposePrivateFields() throws Exception {
    UUID userId = profileFixture.createUser();

    mockMvc.perform(get("/api/users/{id}/public-profile", userId))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists())
        .andExpect(jsonPath("$.avatarUrl").exists())
        .andExpect(jsonPath("$.email").doesNotExist())
        .andExpect(jsonPath("$.phone").doesNotExist())
        .andExpect(jsonPath("$.tenantId").doesNotExist())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(jsonPath("$.internalNote").doesNotExist());
}
```

Test minh họa kiểm tra cả field cần có và field không được xuất hiện. Với response có field tùy quyền, cần thêm test cho từng principal/role và từng trạng thái object. Có thể so sánh response với schema OpenAPI trong contract test, đồng thời kiểm tra field nhạy cảm bằng assertion denylist như một lớp regression bổ sung; thiết kế runtime vẫn nên dựa trên allowlist DTO.

## 12. Logging, observability và dữ liệu downstream

Response có thể bị sao chép vào access log, tracing, analytics, cache, event hoặc hệ thống hỗ trợ khách hàng. Lọc body ở controller nhưng middleware ghi toàn bộ response có thể vẫn làm lộ dữ liệu.

Các nguyên tắc vận hành:

- Không ghi toàn bộ response body mặc định; chỉ log metadata hoặc field đã được duyệt.
- Redact header `Authorization`, cookie và các trường bí mật trước khi tracing/logging.
- Kiểm soát quyền truy cập log, trace, analytics và bản export; audit việc truy cập dữ liệu nhạy cảm.
- Truyền data classification hoặc metadata cần thiết để downstream biết dữ liệu nào được phép lưu/chia sẻ.
- Dùng retention và deletion policy nhất quán cho bản sao dữ liệu, cache và export.
- Theo dõi response size, loại field được trả theo endpoint và lỗi schema để phát hiện response bất thường.

Không đưa raw email, user ID hoặc resource ID làm label metrics có cardinality cao. Dùng route template, status class và nhóm dữ liệu phù hợp; định danh chi tiết lưu trong event store có phân quyền nếu cần điều tra.

## 13. Checklist thiết kế response schema an toàn

- [ ] Endpoint có response DTO riêng và không serialize trực tiếp entity/persistence model.
- [ ] Mỗi field được phân loại theo độ nhạy cảm và mục đích sử dụng.
- [ ] Allowlist field được xác định theo principal, object, action và ngữ cảnh.
- [ ] Quyền đọc object và quyền đọc từng property được kiểm tra riêng.
- [ ] Mapping chỉ đưa field được duyệt vào response; field mới trong entity không tự xuất hiện.
- [ ] Nested object, collection, count, cursor và export tuân thủ cùng phạm vi authorization.
- [ ] OpenAPI/JSON Schema mô tả response rõ ràng và được kiểm tra trong CI.
- [ ] Error response, headers, cookies, cache và file download không làm lộ dữ liệu nội bộ.
- [ ] GraphQL resolver/field selection có authorization và query complexity limit phù hợp.
- [ ] Log, trace và analytics không ghi response hoặc credential nhạy cảm nguyên vẹn.
- [ ] Test xác minh field cần có và field cấm phải vắng mặt cho từng nhóm principal.
- [ ] Có regression test để entity/schema drift không vô tình mở rộng response.

Response schema an toàn phải thể hiện rõ dữ liệu nào được phép rời khỏi service cho từng use case. Dùng DTO allowlist, mapping tường minh, kiểm tra property-level authorization và kiểm thử field bị cấm giúp API chỉ trả dữ liệu cần thiết cho đúng principal, đồng thời hạn chế rò rỉ qua response body, lỗi, cache, log và các kênh xuất dữ liệu khác.
