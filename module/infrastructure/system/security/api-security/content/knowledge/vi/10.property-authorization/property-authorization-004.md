# Chặn mass assignment và field overposting

Mass assignment là lỗi bảo mật xảy ra khi API tự động gán dữ liệu từ request vào object hoặc entity nội bộ mà không giới hạn rõ những thuộc tính client được phép thay đổi. Field overposting là cách khai thác thường gặp: client gửi thêm các trường mà giao diện hoặc tài liệu API không yêu cầu, với hy vọng server vẫn bind và lưu chúng. Nếu các trường đó điều khiển quyền, chủ sở hữu, tenant, giá tiền hoặc trạng thái nghiệp vụ, người gọi có thể thay đổi dữ liệu vượt quá quyền được cấp.

Ví dụ, chức năng cập nhật hồ sơ chỉ cho phép người dùng đổi tên hiển thị và số điện thoại. Client gửi thêm `role: "ADMIN"`, `tenantId: "tenant-b"` hoặc `isVerified: true`. Nếu controller bind toàn bộ JSON vào entity rồi lưu, các trường ngoài ý định của endpoint có thể bị thay đổi. Người dùng đã đăng nhập nhưng vẫn có thể tự nâng quyền hoặc sửa dữ liệu thuộc người khác.

Trong API Security, mỗi endpoint phải xác định rõ thuộc tính nào được nhận, thuộc tính nào được đọc và thuộc tính nào chỉ server được phép thay đổi. Kiểm soát này là một phần của property-level authorization, đồng thời giúp ngăn mass assignment, field overposting và các lỗi cập nhật dữ liệu ngoài phạm vi.

## 1. Mass assignment và field overposting là gì?

Mass assignment thường xuất hiện khi framework hoặc thư viện tự động ánh xạ nhiều trường của request vào một object. Cách làm này tiện lợi, nhưng nguy hiểm nếu object đích có nhiều thuộc tính hơn hợp đồng API.

Một entity tài khoản có thể chứa:

```java
public class Account {
    private UUID id;
    private UUID tenantId;
    private UUID ownerId;
    private String displayName;
    private String phone;
    private String email;
    private String role;
    private boolean enabled;
    private boolean verified;
    private BigDecimal creditLimit;
    private Instant createdAt;
    private Instant updatedAt;
}
```

Trong khi đó, endpoint `PUT /api/me/profile` chỉ nên cho phép người dùng đổi `displayName` và `phone`. Nếu server nhận trực tiếp `Account` làm request body, client có thể thử gửi thêm các trường khác.

```json
{
  "displayName": "Alice",
  "phone": "+84-900-000-000",
  "role": "ADMIN",
  "tenantId": "tenant-b",
  "verified": true,
  "creditLimit": 1000000000
}
```

Nếu các trường được bind và persist mà không có kiểm soát, request có thể thay đổi dữ liệu mà người dùng không được phép sửa.

**Field overposting** mô tả việc client gửi thêm hoặc ghi đè các trường không nằm trong tập dữ liệu mà thao tác dự kiến chấp nhận. Nó có thể khai thác mass assignment, nhưng cũng có thể xảy ra ở API tự viết khi controller chủ động đọc các trường tùy ý từ JSON.

## 2. Phân biệt với BOLA và BFLA

Các lỗi phân quyền thường kết hợp với nhau, nhưng tập trung vào những ranh giới khác nhau:

| Lỗi | Ranh giới bị vi phạm | Ví dụ |
| --- | --- | --- |
| BOLA (Broken Object Level Authorization) | Quyền trên đối tượng | Alice đổi `accountId` để sửa tài khoản của Bob. |
| BFLA (Broken Function Level Authorization) | Quyền sử dụng chức năng | Người dùng thường gọi được endpoint quản trị để khóa tài khoản. |
| BOPLA (Broken Object Property Level Authorization) | Quyền đọc hoặc ghi thuộc tính | Alice sửa `role`, `verified` hoặc `creditLimit` qua endpoint cập nhật hồ sơ. |
| Mass assignment / overposting | Cách dữ liệu request được ánh xạ vào object | Server bind toàn bộ JSON vào entity và lưu cả field ngoài hợp đồng. |

Một endpoint có thể mắc đồng thời nhiều lỗi. Ví dụ, nếu Alice có thể chọn `accountId` của Bob và gửi `role: "ADMIN"`, hệ thống vừa thiếu kiểm tra object-level vừa thiếu kiểm soát property-level.

## 3. Phân loại thuộc tính trước khi thiết kế request

Trước khi viết DTO hoặc controller, hãy lập danh sách thuộc tính và xác định ai được đọc, ai được ghi, trong điều kiện nào. Không nên phân loại chỉ theo tên trường; cần xét ý nghĩa nghiệp vụ và mức độ ảnh hưởng nếu trường bị thay đổi.

| Nhóm thuộc tính | Ví dụ | Quy tắc tiếp nhận |
| --- | --- | --- |
| Người dùng được tự sửa | `displayName`, `phone`, `preferredLanguage` | Chỉ nhận ở endpoint và vai trò phù hợp; vẫn phải validate. |
| Người dùng được đề xuất nhưng server quyết định | `shippingAddress`, `requestedPlan`, `notificationPreference` | Kiểm tra điều kiện nghiệp vụ và quyền trước khi áp dụng. |
| Server quản lý | `id`, `ownerId`, `tenantId`, `createdAt`, `updatedAt` | Không nhận từ request thông thường; server tự gán hoặc cập nhật. |
| Nhạy cảm về quyền | `role`, `permissions`, `isAdmin`, `verified`, `enabled` | Chỉ thay đổi qua chức năng quản trị riêng, có authorization và audit. |
| Tài chính hoặc trạng thái | `price`, `balance`, `creditLimit`, `paymentStatus`, `orderStatus` | Không cho client tự quyết định; dùng command nghiệp vụ chuyên biệt. |
| Bí mật hoặc nội bộ | `passwordHash`, `apiKeyHash`, `resetToken`, `internalNotes` | Không nhận hoặc trả qua DTO công khai; xử lý bằng luồng riêng. |

Một field có thể được phép ghi bởi một nhóm người dùng nhưng không được phép bởi nhóm khác. Ví dụ, nhân viên hỗ trợ có thể cập nhật số điện thoại liên hệ sau khi xác minh danh tính; quản trị viên tenant có thể thay đổi hạn mức tín dụng trong phạm vi tenant; người dùng cuối không được làm hai việc này nếu không có quyền tương ứng.

Vì vậy, danh sách field được phép ghi phải gắn với endpoint, action, principal và resource cụ thể. Không nên tạo một quy tắc chung kiểu “mọi field trừ password đều được cập nhật”.

## 4. Nguyên nhân kỹ thuật thường gặp

### 4.1. Bind request trực tiếp vào entity

Một controller nhận entity làm `@RequestBody` khiến toàn bộ thuộc tính mà Jackson có thể deserialize trở thành ứng viên được client điều khiển.

```java
@PutMapping("/accounts/{id}")
public Account update(
        @PathVariable UUID id,
        @RequestBody Account input) {
    Account account = accountRepository.findById(id)
        .orElseThrow(AccountNotFoundException::new);
    BeanUtils.copyProperties(input, account);
    return accountRepository.save(account);
}
```

Đoạn code có hai vấn đề: request được bind vào entity chứa nhiều field nhạy cảm, và `copyProperties` sao chép hàng loạt thuộc tính mà không thể hiện rõ hợp đồng cập nhật. Nếu không có kiểm tra khác, client có thể thử thay `ownerId`, `tenantId`, `role`, `enabled` hoặc `creditLimit`.

### 4.2. Dùng mapper tự động không có allowlist

MapStruct, ModelMapper, BeanUtils hoặc mapper tự viết đều có thể tạo rủi ro nếu ánh xạ mọi field cùng tên từ request sang entity. Việc dùng thư viện mapping không tự tạo ra property authorization. Cần cấu hình rõ field được phép, hoặc viết mapping tường minh cho thao tác nhạy cảm.

### 4.3. Dùng chung một DTO cho nhiều thao tác

DTO tạo mới, cập nhật hồ sơ, quản trị tài khoản và phản hồi chi tiết thường có tập field khác nhau. Nếu tái sử dụng một DTO lớn, một endpoint có thể vô tình chấp nhận các field chỉ dành cho endpoint khác. Mỗi use case nên có input model riêng với allowlist cụ thể.

### 4.4. Tin vào giao diện hoặc tài liệu API

Ẩn field trên giao diện, không hiển thị trong form hoặc ghi chú “không gửi trường role” trong tài liệu không ngăn client tự tạo request. Server phải từ chối hoặc bỏ qua field không được phép theo chính sách đã công bố và phải bảo đảm field đó không thể làm thay đổi trạng thái nội bộ.

## 5. Thiết kế input DTO theo allowlist

Biện pháp nền tảng là tạo request DTO chỉ chứa các thuộc tính mà endpoint được phép nhận. Sau đó ánh xạ tường minh từ DTO sang domain object.

```java
public record UpdateMyProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotBlank
    @Pattern(regexp = "^[0-9+() .-]{7,25}$")
    String phone
) {}

public record ProfileView(
    UUID id,
    String displayName,
    String phone
) {}
```

Controller lấy identity từ principal đã xác thực và không nhận `ownerId` hoặc `tenantId` từ body:

```java
@PutMapping("/me/profile")
@PreAuthorize("isAuthenticated()")
public ProfileView updateMyProfile(
        @AuthenticationPrincipal Jwt jwt,
        @Valid @RequestBody UpdateMyProfileRequest request) {
    UUID userId = UUID.fromString(jwt.getSubject());
    return profileService.updateMyProfile(userId, request);
}
```

Service tải đúng profile theo identity rồi chỉ cập nhật các field có trong use case:

```java
@Transactional
public ProfileView updateMyProfile(
        UUID userId,
        UpdateMyProfileRequest request) {

    Profile profile = profileRepository.findByUserId(userId)
        .orElseThrow(ProfileNotFoundException::new);

    profile.changeDisplayName(request.displayName());
    profile.changePhone(request.phone());

    return profileMapper.toView(profile);
}
```

Ví dụ này minh họa allowlist theo endpoint: request không có `role`, `tenantId`, `verified` hoặc `creditLimit`, và service không sao chép các field đó. Trong ứng dụng thực tế, cần bảo đảm `Jwt.getSubject()` đã được xác minh theo issuer/audience và ánh xạ đúng kiểu định danh user của hệ thống. Nếu principal dùng claim khác, hãy dùng một mapper tin cậy để tạo user context.

### 5.1. Từ chối hay bỏ qua field lạ?

Khi client gửi field ngoài DTO, ứng dụng có thể:

- **Từ chối request:** phù hợp khi muốn phát hiện sớm overposting hoặc contract sai. Trả lỗi validation rõ ràng nhưng không tiết lộ chi tiết nội bộ.
- **Bỏ qua field lạ:** có thể hữu ích cho một số API cần khả năng tương thích khi schema mở rộng, nhưng chỉ an toàn nếu field bị bỏ qua hoàn toàn và không ảnh hưởng tới entity, log hoặc side effect.

Hành vi phụ thuộc cấu hình Jackson và framework. Không nên giả định mọi ứng dụng Spring Boot đều tự động từ chối unknown properties. Có thể cấu hình `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES` cho API hoặc DTO phù hợp, sau khi đánh giá tác động tương thích. Với field nhạy cảm như `role`, `ownerId`, `tenantId` hoặc `price`, cần có kiểm thử chứng minh việc gửi field đó không làm thay đổi dữ liệu; từ chối rõ ràng thường giúp phát hiện lỗi tích hợp tốt hơn.

### 5.2. Mapping tường minh và mapper tự động

Đối với thao tác nhạy cảm, mapping tường minh làm rõ field nào được cập nhật:

```java
profile.setDisplayName(request.displayName());
profile.setPhone(request.phone());
```

Nếu dùng MapStruct, có thể đặt policy mặc định bỏ qua field và chỉ khai báo các mapping được phép, hoặc dùng DTO đích riêng cho use case. Cần review generated mapping và kiểm thử các field server-managed. Không dựa vào convention cùng tên field để quyết định quyền ghi.

## 6. Property-level authorization cho field có điều kiện

DTO theo endpoint xử lý tốt các field có quyền tĩnh. Một số field lại phụ thuộc role, tenant, ownership, trạng thái hoặc bước phê duyệt. Khi đó, cần kiểm tra quyền ở service/domain trước khi áp dụng thay đổi.

Ví dụ, chỉ nhân viên có quyền `accounts:credit-limit:write` mới được đổi hạn mức, và họ chỉ được thao tác trong tenant được phân công:

```java
public record ChangeCreditLimitRequest(
    @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2)
    BigDecimal creditLimit
) {}

@Transactional
public AccountView changeCreditLimit(
        UUID accountId,
        ChangeCreditLimitRequest request,
        ApiPrincipal actor) {

    Account account = accountRepository
        .findByIdAndTenantId(accountId, actor.tenantId())
        .orElseThrow(AccountNotFoundException::new);

    if (!accountPolicy.canChangeCreditLimit(actor, account)) {
        throw new AccessDeniedException("Not allowed");
    }

    account.changeCreditLimit(request.creditLimit());
    auditService.recordCreditLimitChange(actor, account);
    return accountMapper.toView(account);
}
```

Endpoint cũng cần kiểm tra quyền chức năng, ví dụ scope `accounts:manage-credit-limit`. Kiểm tra trong service bảo đảm quyền trên object và ngữ cảnh được xác minh ngay trước khi thay đổi. Domain method nên bảo vệ invariant như hạn mức không âm, không vượt chính sách rủi ro và không thay đổi khi tài khoản đang bị khóa.

### 6.1. Tách quyền đọc và quyền ghi

Một người có thể được xem một thuộc tính nhưng không được sửa nó, hoặc được sửa nhưng không được xem giá trị hiện tại. Ví dụ:

| Field | Quyền đọc | Quyền ghi |
| --- | --- | --- |
| `displayName` | Chủ tài khoản và người được chia sẻ hồ sơ | Chủ tài khoản |
| `phone` | Chủ tài khoản và nhân viên hỗ trợ được cấp quyền | Chủ tài khoản; hỗ trợ chỉ qua quy trình xác minh |
| `role` | Quản trị viên có quyền quản lý thành viên | Chỉ quản trị viên được cấp quyền, qua endpoint riêng |
| `creditLimit` | Nhân viên tài chính trong phạm vi phụ trách | Nhân viên được cấp quyền phê duyệt hạn mức |
| `passwordHash` | Không trả qua API | Không nhận trực tiếp; chỉ cập nhật qua quy trình đổi mật khẩu |

Không nên suy ra quyền ghi từ quyền đọc hoặc ngược lại. Policy cần xác định action cụ thể, field cụ thể và object cụ thể.

## 7. Cẩn trọng với PATCH, nested object và collection

### 7.1. PATCH và ý nghĩa của field bị bỏ qua

Với `PATCH`, một field không xuất hiện thường có nghĩa là giữ nguyên giá trị; field xuất hiện với `null` có thể mang nghĩa xóa giá trị hoặc không hợp lệ. DTO Java thông thường có thể khó phân biệt field bị bỏ qua với field được gửi rõ ràng là `null`, nhất là khi cả hai đều trở thành `null` sau deserialize.

Hãy định nghĩa semantics trong contract. Có thể dùng wrapper thể hiện ba trạng thái (không xuất hiện, có giá trị, null), JSON Merge Patch hoặc một command model chuyên biệt. Dù chọn cách nào, chỉ field trong allowlist mới được áp dụng. Không merge request JSON tùy ý vào entity.

Ví dụ với JSON Merge Patch:

```http
PATCH /api/me/profile
Content-Type: application/merge-patch+json

{
  "displayName": "Alice Nguyen",
  "phone": null,
  "role": "ADMIN"
}
```

Nếu contract chỉ cho phép `displayName` và `phone`, server phải từ chối hoặc bỏ qua `role` theo chính sách unknown field đã công bố. `phone: null` chỉ được phép xóa số điện thoại nếu nghiệp vụ cho phép; không được diễn giải mơ hồ.

### 7.2. Nested object

DTO có thể chứa object lồng nhau như địa chỉ, phương thức thanh toán hoặc thông tin doanh nghiệp. Không nên nhận entity lồng nhau trực tiếp vì nó có thể chứa field quản trị và quan hệ ID do client kiểm soát.

```java
public record ChangeShippingAddressRequest(
    @NotNull @Valid AddressInput address
) {}

public record AddressInput(
    @NotBlank @Size(max = 120) String line1,
    @NotBlank @Size(max = 80) String city,
    @NotBlank @Size(max = 20) String postalCode
) {}
```

Nếu địa chỉ tham chiếu `countryId`, `regionId` hoặc một address book entry, server phải xác minh các ID đó hợp lệ và thuộc phạm vi người gọi. Không chỉ kiểm tra object cha rồi tin mọi ID lồng nhau.

### 7.3. Collection và danh sách ID

Với request cập nhật nhiều phần tử, cần xác định field nào được sửa, số lượng tối đa, phần tử nào được phép thay đổi và cách xử lý lỗi từng phần. Mỗi object ID trong danh sách phải được kiểm tra quyền; mỗi field trong từng object cũng phải qua allowlist và policy. Không dùng một DTO rộng để cập nhật hàng loạt entity.

## 8. Bảo vệ response khỏi lộ field nhạy cảm

Mass assignment chủ yếu là rủi ro ghi dữ liệu, nhưng property-level authorization cũng kiểm soát quyền đọc. Trả trực tiếp entity có thể làm lộ `internalNotes`, `creditLimit`, `riskScore`, `passwordHash`, token hoặc field chỉ dành cho nhân viên.

Hãy dùng response DTO hoặc projection riêng:

```java
public record MyProfileView(
    UUID id,
    String displayName,
    String phone
) {}
```

Nếu response khác nhau theo vai trò, có thể dùng mapper/policy rõ ràng để tạo view phù hợp. Không nên serialize entity rồi cố gắng xóa một vài field nhạy cảm sau đó. `@JsonIgnore` hoặc `@JsonProperty(access = READ_ONLY)` có thể là lớp hỗ trợ, nhưng không thay thế input DTO, response DTO và authorization ở service.

Với endpoint quản trị, response có thể cần thêm field nhưng chỉ trả cho principal được cấp quyền. Cần kiểm thử cả trường hợp quyền thấp gọi cùng endpoint hoặc truy cập cùng resource qua route khác.

## 9. Validation và bảo vệ tính toàn vẹn dữ liệu

Validation kiểm tra dữ liệu có đúng cấu trúc và điều kiện nghiệp vụ hay không; authorization kiểm tra người gọi có quyền thay đổi field đó hay không. Hai kiểm soát này bổ sung cho nhau.

- Kiểm tra kiểu, độ dài, format, miền giá trị, số lượng phần tử và trường bắt buộc ở ranh giới API.
- Kiểm tra quy tắc nghiệp vụ trong domain, ví dụ hạn mức không vượt ngưỡng, trạng thái cho phép cập nhật hoặc số điện thoại đã được xác minh.
- Dùng decimal cho tiền tệ và kiểm soát scale/rounding; không để client tự tính giá, thuế hoặc số dư có thẩm quyền.
- Với enum như `status`, không nhận giá trị tùy ý từ client. Dùng command chuyển trạng thái và kiểm tra transition được phép.
- Dùng transaction và kiểm soát concurrency khi quyết định quyền phụ thuộc vào dữ liệu có thể thay đổi đồng thời.
- Ràng buộc database như foreign key, unique constraint và tenant-aware constraint có thể bảo vệ tính toàn vẹn, nhưng không thay authorization.

Nếu quyền thay đổi field phụ thuộc trạng thái hiện tại, hãy tải trạng thái mới nhất và kiểm tra ngay trước khi ghi. Tránh kiểm tra ở controller rồi thực hiện update muộn sau khi object hoặc membership đã thay đổi.

## 10. Kiểm thử mass assignment và property authorization

Test không chỉ xác nhận field hợp lệ được lưu. Cần chủ động gửi field ngoài hợp đồng và kiểm tra trạng thái persisted, response cùng side effect.

| Trường hợp | Request hoặc điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Field hợp lệ | Người dùng cập nhật `displayName` | Field được cập nhật và response đúng schema. |
| Overposting role | Gửi thêm `role: "ADMIN"` | Request bị từ chối hoặc field bị bỏ qua hoàn toàn; role không đổi. |
| Overposting tenant | Gửi `tenantId` khác | Không chuyển tenant, không đọc hoặc ghi dữ liệu tenant khác. |
| Field server-managed | Gửi `ownerId`, `createdAt`, `verified` | Không thay đổi giá trị do server quản lý. |
| Field tài chính | Gửi `creditLimit`, `balance` hoặc `price` qua endpoint hồ sơ | Không thay đổi dữ liệu tài chính. |
| Field đọc được nhưng không ghi được | Principal xem được `role` nhưng không có quyền cập nhật | Request cập nhật field bị từ chối. |
| Nested object | Gửi ID địa chỉ hoặc tài khoản thuộc người khác | Từ chối quan hệ không hợp lệ; không thay đổi object liên quan. |
| PATCH null/omitted | Bỏ qua field hoặc gửi `null` | Hành vi đúng contract; không xóa dữ liệu ngoài ý muốn. |
| Collection/bulk | Một số ID thuộc phạm vi, một số ID ngoài phạm vi | Xử lý đúng quy tắc nguyên tử/từng phần; không cập nhật object trái phép. |
| Response | Đọc profile bằng user thường và admin | Mỗi vai trò chỉ nhận field được phép. |

### 10.1. Ví dụ kiểm thử không thay đổi field nhạy cảm

```java
@Test
void profileUpdateMustIgnoreOrRejectOverpostedRole() throws Exception {
    UUID aliceId = profileFixture.createUserWithRole("CUSTOMER");

    mockMvc.perform(put("/api/me/profile")
            .with(jwt().jwt(jwt -> jwt.subject(aliceId.toString())))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Alice",
                  "phone": "+84-900-000-000",
                  "role": "ADMIN"
                }
                """))
        .andExpect(result -> {
            int status = result.getResponse().getStatus();
            assertThat(status).isIn(400, 200);
        });

    assertThat(profileRepository.findRoleByUserId(aliceId))
        .isEqualTo("CUSTOMER");
}
```

Test minh họa chấp nhận hai contract có chủ đích: reject unknown field với `400`, hoặc bỏ qua field lạ và trả `200`. Dù chọn cách nào, assertion quan trọng là role vẫn là `CUSTOMER`. Trong suite thực tế, nên tách thành test riêng theo đúng hành vi API đã công bố, đồng thời xác minh audit và response không chứa field nhạy cảm.

## 11. Logging, audit và giám sát

Thay đổi field nhạy cảm nên có audit trail đủ để điều tra: principal, tenant, resource, action, field hoặc nhóm field thay đổi, kết quả authorization, thời điểm, correlation ID và phiên bản policy. Với field nhạy cảm, có thể ghi giá trị trước/sau ở dạng đã che hoặc ghi hash/metadata phù hợp; không ghi password, token, secret hay toàn bộ payload cá nhân vào log thông thường.

Theo dõi các dấu hiệu như:

- Request thường xuyên gửi thêm `role`, `tenantId`, `ownerId`, `price`, `balance` hoặc trạng thái quản trị.
- Nhiều lần validation/authorization thất bại trên cùng endpoint.
- Một principal cố cập nhật field nhạy cảm ngoài chức năng thông thường.
- Tỷ lệ lỗi `400`/`403` tăng bất thường sau khi client hoặc schema thay đổi.
- Giá trị quyền, trạng thái hoặc tài chính thay đổi mà không có actor hay audit event hợp lệ.

Khi phát hiện overposting thành công, cần xác định field và object bị thay đổi, actor, phạm vi tenant và side effect liên quan. Khôi phục dữ liệu theo quy trình, thu hồi quyền hoặc credential nếu cần, sửa allowlist/mapping, kiểm tra response và thêm regression test.

## 12. Checklist trước khi đưa endpoint vào sử dụng

- [ ] Request DTO chỉ chứa field mà use case thực sự cho phép nhận.
- [ ] Entity không được bind trực tiếp từ request công khai.
- [ ] Mapper không sao chép hàng loạt field nhạy cảm; mapping được review và kiểm thử.
- [ ] `id`, `ownerId`, `tenantId`, role, permission, trạng thái và field tài chính do server quản lý hoặc qua endpoint chuyên biệt.
- [ ] Quyền đọc và quyền ghi từng field được xác định riêng theo principal, resource và context.
- [ ] Nested object, collection và mọi ID tham chiếu đều được xác minh.
- [ ] PATCH phân biệt rõ field bị bỏ qua và field được gửi `null`.
- [ ] Validation cấu trúc và quy tắc nghiệp vụ được thực hiện phía server.
- [ ] Response DTO chỉ công bố field được phép cho principal hiện tại.
- [ ] Test gửi field overposting và xác minh dữ liệu persisted không đổi ngoài allowlist.
- [ ] Audit và monitoring ghi nhận thay đổi nhạy cảm mà không làm lộ bí mật.

Chặn mass assignment cần bắt đầu từ hợp đồng input rõ ràng, ánh xạ field có chủ đích và kiểm tra property authorization trong ngữ cảnh nghiệp vụ. Mỗi endpoint chỉ nên thay đổi những thuộc tính mà chủ thể hiện tại được phép sửa trên đối tượng cụ thể; các field còn lại phải do server quản lý hoặc đi qua một luồng quản trị riêng có kiểm soát.
