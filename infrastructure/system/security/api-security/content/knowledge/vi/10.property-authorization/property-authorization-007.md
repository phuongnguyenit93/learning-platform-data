# Test low-privilege user với admin-only property

Một người dùng có thể chỉ được phép sửa tên hiển thị và số điện thoại của chính mình, nhưng API lại nhận thêm trường `role`, `isAdmin` hoặc `accountStatus` từ request rồi ghi thẳng vào database. Khi đó, người dùng quyền thấp có thể tự nâng quyền hoặc thay đổi dữ liệu quản trị dù endpoint đã yêu cầu đăng nhập. Một lỗi khác xảy ra khi API không cho ghi các trường này nhưng vẫn trả chúng trong response, khiến người dùng đọc được thông tin chỉ dành cho quản trị viên.

Kiểm thử **low-privilege user với admin-only property** nhằm xác minh rằng người dùng có quyền hạn chế không thể đọc hoặc thay đổi thuộc tính dành riêng cho quản trị viên. Đây là một phần của **Broken Object Property Level Authorization (BOPLA)**, trước đây thường được thảo luận qua các lỗi excessive data exposure và mass assignment. Bài kiểm thử cần xác minh cả request lẫn trạng thái dữ liệu sau xử lý; chỉ kiểm tra HTTP status code là chưa đủ.

Trong phạm vi API Security, quyền phải được áp dụng theo endpoint, object và từng property. Xác thực thành công hoặc có quyền cập nhật hồ sơ không đồng nghĩa người dùng được cập nhật mọi thuộc tính của hồ sơ đó.

Sau bài học, người đọc có thể:

- Phân biệt quyền trên object với quyền đọc/ghi từng property.
- Xác định các thuộc tính chỉ quản trị viên hoặc service đặc quyền mới được truy cập.
- Thiết kế test âm tính cho người dùng quyền thấp khi đọc, ghi hoặc gửi hàng loạt admin-only property.
- Phát hiện mass assignment, over-posting và excessive data exposure.
- Xác minh dữ liệu nhạy cảm không bị thay đổi, trả về hoặc phát sinh side effect sau request bị từ chối.
- Xây dựng integration test với Spring Boot để kiểm tra hợp đồng property authorization.

## 1. Property authorization là gì?

Property authorization là việc quyết định một chủ thể có được phép đọc hoặc thay đổi một thuộc tính cụ thể của object hay không. Một API có thể cho phép người dùng truy cập hồ sơ của chính họ, nhưng giới hạn các trường được đọc và ghi.

Ví dụ object `UserProfile` có các thuộc tính:

| Property | Người dùng thông thường | Quản trị viên | Nguồn cập nhật đáng tin cậy |
|---|---|---|---|
| `displayName` | Đọc và sửa hồ sơ của mình | Đọc/sửa theo phạm vi quản trị | Người dùng hoặc admin theo policy |
| `phoneNumber` | Đọc và sửa hồ sơ của mình | Đọc/sửa theo phạm vi quản trị | Người dùng hoặc admin theo policy |
| `role` | Không được đọc hoặc sửa | Được đọc/sửa khi có quyền quản trị phù hợp | Quy trình quản trị |
| `accountStatus` | Có thể chỉ đọc trạng thái công khai; không được sửa | Được thay đổi theo quyền quản trị | Quy trình quản trị/tác vụ hệ thống |
| `mfaEnabled` | Chỉ được xem trạng thái phù hợp với chính sách; không được tự bật/tắt bằng profile update | Được quản lý theo quy trình xác minh riêng | Quy trình MFA |
| `tenantId` | Không được tự đọc hoặc sửa nếu không cần cho chức năng | Có thể đọc theo phạm vi được cấp; thay đổi qua quy trình đặc biệt | Hệ thống quản lý tenant |
| `createdAt`, `updatedAt` | Có thể được trả về nếu cần; không được sửa | Thường vẫn do hệ thống quản lý | Máy chủ |
| `passwordHash`, `resetToken` | Không được đọc hoặc ghi trực tiếp | Không nên trả trực tiếp cho admin | Dịch vụ xác thực |

Quyền đọc và quyền ghi là hai quyết định riêng. Ví dụ, người dùng có thể xem trạng thái tài khoản của mình nhưng không được tự đặt `accountStatus` thành `ACTIVE`; quản trị viên có thể đọc `role` nhưng chỉ một nhóm admin cụ thể mới được sửa role. Một số thuộc tính nhạy cảm như `passwordHash` không nên được trả về ngay cả trong giao diện quản trị.

## 2. Nhận diện admin-only property và rủi ro

Admin-only property là thuộc tính mà policy giới hạn cho quản trị viên hoặc một service có thẩm quyền cụ thể. Không nên xác định danh sách này chỉ từ tên trường. Hãy xem tác động của thuộc tính và nguồn dữ liệu có thẩm quyền.

Các nhóm thường gặp:

- **Quyền và danh tính:** `role`, `roles`, `permissions`, `isAdmin`, `ownerId`, `tenantId`.
- **Trạng thái tài khoản:** `accountStatus`, `locked`, `enabled`, `verified`, `suspendedAt`.
- **Tài chính và hạn mức:** `creditLimit`, `balance`, `discountRate`, `approvedAmount`.
- **Kiểm soát nghiệp vụ:** `approvalStatus`, `approvedBy`, `riskLevel`, `fraudFlags`.
- **Dữ liệu xác thực và nội bộ:** `passwordHash`, `mfaSecret`, `resetToken`, `internalNotes`.
- **Audit và metadata hệ thống:** `createdBy`, `updatedBy`, `createdAt`, `version`.

Hai nhóm lỗi thường xuất hiện:

### 2.1. Mass assignment / over-posting

Client gửi các trường vượt quá phạm vi được phép và ứng dụng bind toàn bộ JSON vào entity hoặc object persistence. Ví dụ, endpoint được thiết kế để đổi tên hiển thị nhưng lại nhận `role`:

```http
PATCH /api/me HTTP/1.1
Content-Type: application/json
Authorization: Bearer <token-user-thuong>

{
  "displayName": "Nguyen An",
  "role": "ADMIN",
  "isAdmin": true
}
```

Nếu server deserialize trực tiếp vào entity rồi lưu, hai trường đặc quyền có thể bị cập nhật ngoài ý muốn. Việc frontend không hiển thị các trường này không ngăn được người dùng tự tạo request.

### 2.2. Excessive data exposure

API trả toàn bộ entity trong response dù client chỉ cần một vài trường:

```json
{
  "id": "U-17",
  "displayName": "Nguyen An",
  "phoneNumber": "0900000000",
  "role": "ADMIN",
  "internalRiskScore": 87,
  "tenantId": "TENANT-SECRET"
}
```

Ẩn trường trên giao diện không làm dữ liệu biến mất khỏi response. Người gọi có thể xem JSON trong network inspector hoặc gọi API trực tiếp. Response phải được tạo từ projection/DTO phù hợp với quyền đọc của caller.

## 3. Xác định chính sách trước khi viết test

Một test chỉ rõ ràng khi biết chính xác ai được làm gì với property nào. Hãy định nghĩa policy theo các thành phần:

- **Subject:** user thường, support, admin, tenant admin hoặc service principal.
- **Action:** đọc (`read`), tạo (`create`), cập nhật (`update`), xóa (`delete`) hoặc thực hiện chuyển trạng thái.
- **Object:** hồ sơ của chính user, hồ sơ người khác, tài khoản hoặc tài nguyên nghiệp vụ.
- **Property:** trường cụ thể đang được đọc hoặc ghi.
- **Context:** tenant, quan hệ sở hữu, trạng thái object, bước xác minh hoặc điều kiện phê duyệt.

Ví dụ policy:

```text
User thường:
  ALLOW read  displayName, phoneNumber của hồ sơ mình
  ALLOW write displayName, phoneNumber của hồ sơ mình
  DENY  read  role, isAdmin, internalRiskScore
  DENY  write role, isAdmin, accountStatus, tenantId

Admin có quyền user:manage:
  ALLOW read  role, accountStatus trong tenant/phạm vi được giao
  ALLOW write role, accountStatus theo quy trình quản trị
  DENY  read  passwordHash, mfaSecret, resetToken
```

Đây chỉ là policy minh họa; hệ thống cần định nghĩa theo nghiệp vụ thực tế. Không nên cấp quyền đọc hoặc ghi tất cả thuộc tính chỉ vì caller có role `ADMIN`. Một số trường vẫn phải được bảo vệ khỏi mọi API response hoặc yêu cầu quy trình chuyên biệt.

Đặc biệt, hãy kiểm tra riêng ba lớp:

1. Caller có quyền trên object hay không?
2. Caller có quyền dùng endpoint/action hay không?
3. Caller có quyền đọc hoặc ghi từng property trong payload/response hay không?

Ví dụ user thường được phép sửa hồ sơ của mình, nên object-level authorization có thể PASS, action `profile:update` có thể PASS, nhưng property `role` vẫn phải bị từ chối.

## 4. Thiết kế bộ dữ liệu test có thể chứng minh kết quả

Tạo fixture tách biệt để test không phụ thuộc dữ liệu thật:

| Tài khoản test | Quyền | Object test | Giá trị ban đầu |
|---|---|---|---|
| `user-low` | `profile:read`, `profile:update` | Hồ sơ của user-low | `role=CUSTOMER`, `accountStatus=ACTIVE` |
| `user-other` | `profile:read`, `profile:update` | Hồ sơ user-other | `role=CUSTOMER` |
| `admin-test` | `user:read`, `user:manage` | Hồ sơ trong phạm vi được giao | `role=ADMIN` hoặc role quản trị test |

Lưu lại giá trị ban đầu của các property cần bảo vệ để so sánh sau request. Không chỉ kiểm tra response; phải đọc lại trạng thái qua repository hoặc API kiểm thử có quyền phù hợp để xác minh database không bị thay đổi.

Nên chuẩn bị các object có cùng tenant và khác tenant nếu ứng dụng multi-tenant. Điều này giúp phân biệt lỗi property authorization với lỗi object authorization. Test low-privilege phải có quyền cập nhật một số trường thông thường để chứng minh request bị từ chối vì trường đặc quyền, thay vì chỉ vì user không được phép gọi endpoint.

Không dùng tài khoản quản trị production, dữ liệu khách hàng thật hoặc secret thật trong test. Dùng fixture có thể tái tạo, reset được và chạy độc lập giữa các test.

## 5. Ma trận test low-privilege với admin-only property

Với user quyền thấp, kiểm tra tối thiểu các trường hợp sau:

| Nhóm | Thao tác kiểm thử | Kết quả mong đợi |
|---|---|---|
| Đọc hồ sơ | GET hồ sơ của mình | Có trường được phép; không có `role`, `isAdmin` hoặc trường nội bộ bị cấm |
| Đọc object khác | GET hồ sơ người khác | Bị từ chối theo object policy; không lộ property |
| Gửi property đặc quyền | PATCH thêm `role=ADMIN` | Bị từ chối hoặc field bị loại theo hợp đồng; role không đổi |
| Gửi cờ quản trị | POST/PATCH thêm `isAdmin=true` | Không thể nâng quyền; dữ liệu lưu không đổi |
| Sửa trạng thái | Gửi `accountStatus=ACTIVE` hoặc `locked=false` | Bị từ chối nếu user không có quyền quản trị |
| Sửa tenant/owner | Gửi `tenantId` hoặc `ownerId` khác | Bị từ chối; object không chuyển tenant/owner |
| Gửi nhiều trường | Gửi cả trường hợp lệ và admin-only | Không có trường đặc quyền nào được áp dụng; hành vi request theo hợp đồng rõ ràng |
| Gửi nested property | `{"security":{"isAdmin":true}}` | Không vượt qua allowlist ở object lồng nhau |
| Gửi trong mảng/batch | Cập nhật nhiều user, có trường đặc quyền | Kiểm tra từng object và từng property; không có cập nhật trái phép |
| Dùng PUT thay PATCH | Gửi representation có `role` | Không thay đổi property bị cấm |
| Dùng endpoint khác | Import, bulk update, GraphQL mutation | Chính sách property được áp dụng nhất quán |
| Đọc danh sách/export | List, search, CSV hoặc báo cáo | Không trả admin-only property |

Đối với mỗi trường hợp, xác minh:

- HTTP status và cấu trúc lỗi phù hợp hợp đồng.
- Property bị cấm không thay đổi trong database.
- Response không echo lại giá trị đặc quyền như thể cập nhật thành công.
- Không phát sinh side effect như cấp quyền, gửi thông báo quản trị hoặc tạo audit event thành công giả.
- Log/audit ghi nhận lần từ chối nếu đây là thao tác nhạy cảm, nhưng không lưu token hoặc payload bí mật.

## 6. Chọn hành vi API khi client gửi property không được phép

API nên có một hợp đồng nhất quán cho trường hợp client gửi field ngoài phạm vi. Có hai cách phổ biến:

**Từ chối request:** trả `400 Bad Request` hoặc `422 Unprocessable Content` nếu field không thuộc schema được phép; có thể trả `403 Forbidden` nếu policy xác định caller không có quyền cập nhật property đó. Đây thường là lựa chọn rõ ràng cho field đặc quyền vì client biết request không được chấp nhận.

**Bỏ qua field bị cấm:** API chỉ áp dụng field được phép và bỏ qua field khác. Nếu chọn cách này, phải bảo đảm field bị cấm không được lưu, không được phản chiếu trong response và hành vi được ghi rõ trong tài liệu API. Cách này có thể khiến client tưởng rằng cập nhật thành công, vì vậy cần cân nhắc kỹ.

Không có một status code duy nhất phù hợp với mọi hợp đồng. Điều quan trọng là test khóa chặt hành vi đã chọn. Ví dụ, nếu API quy định từ chối field `role`, test phải yêu cầu đúng status đã thống nhất và xác minh `role` không đổi. Nếu API quy định bỏ qua field, test phải xác minh các trường hợp lệ vẫn được cập nhật nhưng `role` không đổi.

Với lỗi phân quyền trên toàn bộ object, `403` hoặc `404` có thể được dùng theo chính sách che giấu tài nguyên. Với lỗi property, tránh trả thông tin nội bộ như danh sách toàn bộ field quản trị nếu điều đó có thể tiết lộ thiết kế nhạy cảm; thông báo chung như `Property is not allowed` thường đủ cho client.

## 7. Phòng mass assignment bằng DTO và allowlist

Không nhận request bằng entity persistence:

```java
// Không nên: client có thể gửi thêm các field mà entity có.
@PatchMapping("/me")
public UserProfile update(@RequestBody UserProfile profile) {
    return repository.save(profile);
}
```

Thay vào đó, định nghĩa DTO riêng cho các trường user được phép cập nhật:

```java
public record UpdateMyProfileRequest(
        @NotBlank @Size(max = 80) String displayName,
        @Pattern(regexp = "^[0-9+ -]{8,20}$") String phoneNumber) {
}
```

Service chỉ gán những field có trong DTO:

```java
@Transactional
public UserProfileResponse updateMyProfile(
        UpdateMyProfileRequest request,
        ApiPrincipal actor) {

    UserProfile profile = repository
            .findByIdAndTenantId(actor.userId(), actor.tenantId())
            .orElseThrow(ProfileNotFoundException::new);

    profile.changeDisplayName(request.displayName());
    profile.changePhoneNumber(request.phoneNumber());

    return UserProfileResponse.from(profile);
}
```

DTO không chứa `role`, `isAdmin`, `tenantId`, `accountStatus` hoặc `createdAt`, do đó endpoint thông thường không có đường bind trực tiếp các field này. `actor.userId()` và `actor.tenantId()` phải đến từ principal đáng tin cậy, không lấy từ request body.

Đối với endpoint quản trị, dùng request DTO riêng và kiểm tra quyền rõ ràng:

```java
public record AdminUpdateUserRequest(
        @NotNull UserRole role,
        @NotNull AccountStatus accountStatus) {
}

@PatchMapping("/admin/users/{id}")
@PreAuthorize("hasAuthority('user:manage')")
public UserAdminResponse updateUserAsAdmin(
        @PathVariable UUID id,
        @Valid @RequestBody AdminUpdateUserRequest request) {
    return adminUserService.updateManagedFields(id, request);
}
```

Ví dụ này vẫn cần kiểm tra admin có quyền trên đúng user/tenant và có được thay đổi từng property trong ngữ cảnh hiện tại. Quyền `user:manage` không nên tự động cho phép mọi hành động trên mọi tenant.

## 8. Kiểm soát property trong response

Tạo response DTO theo mục đích sử dụng. Ví dụ:

```java
public record MyProfileResponse(
        UUID id,
        String displayName,
        String phoneNumber,
        AccountStatusView accountStatus) {
}

public record AdminUserResponse(
        UUID id,
        String displayName,
        String phoneNumber,
        UserRole role,
        AccountStatus accountStatus) {
}
```

`MyProfileResponse` chỉ chứa các trường mà user có thể đọc. `AdminUserResponse` dành cho endpoint quản trị sau khi kiểm tra quyền. Không nên trả entity trực tiếp hoặc dùng một DTO khổng lồ rồi hy vọng frontend tự ẩn field.

Test GET cần kiểm tra cả trường phải có và trường không được có:

```java
mockMvc.perform(get("/api/me"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").exists())
    .andExpect(jsonPath("$.role").doesNotExist())
    .andExpect(jsonPath("$.isAdmin").doesNotExist())
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
```

Kiểm tra response ở nhiều đường truy cập: detail, list, search, export, nested resource, GraphQL, cache và thông báo lỗi. Một endpoint detail an toàn không bảo đảm endpoint list hoặc export cũng an toàn.

## 9. Viết integration test với Spring Boot

Ví dụ dưới đây giả định API có hợp đồng: user thường được cập nhật `displayName`, nhưng nếu gửi `role` thì request bị từ chối bằng `400 Bad Request`. Repository cho phép đọc lại hồ sơ để xác minh trạng thái lưu.

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProfilePropertyAuthorizationIT {

    @Autowired MockMvc mockMvc;
    @Autowired UserProfileRepository repository;

    @Test
    @WithMockUser(username = "user-low", authorities = {
            "profile:read", "profile:update"
    })
    void lowPrivilegeUserCannotSetAdminOnlyRole() throws Exception {
        UUID userId = TestUsers.LOW_PRIVILEGE_ID;

        mockMvc.perform(patch("/api/me")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "displayName": "An Nguyen",
                      "role": "ADMIN"
                    }
                    """))
            .andExpect(status().isBadRequest());

        UserProfile saved = repository.findById(userId).orElseThrow();
        assertThat(saved.getRole()).isEqualTo(UserRole.CUSTOMER);
        assertThat(saved.getDisplayName()).isEqualTo("Original Name");
    }
}
```

Test này chứng minh user có quyền sửa hồ sơ vẫn không thể thay role. Ví dụ đang chọn hợp đồng từ chối toàn request, vì vậy cả `role` và `displayName` đều phải giữ nguyên. Nếu API được thiết kế để bỏ qua field cấm, tên có thể được cập nhật nhưng role phải giữ nguyên; khi đó hãy viết test riêng cho status và hành vi bỏ qua field. Không trộn hai hợp đồng trong cùng một test.

Đoạn test giả định fixture `user-low` đã được tạo với ID cố định và controller có thể ánh xạ username trong test security context sang hồ sơ đó. Nếu ứng dụng dùng `@AuthenticationPrincipal ApiPrincipal`, `@WithMockUser` mặc định không tạo đúng kiểu principal này; hãy dùng custom `@WithSecurityContext` hoặc test security context factory để dựng principal gồm user ID, tenant và authorities như request production.

Ví dụ kiểm tra response không lộ property:

```java
@Test
@WithMockUser(username = "user-low", authorities = "profile:read")
void lowPrivilegeUserDoesNotReceiveAdminOnlyProperties() throws Exception {
    mockMvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists())
        .andExpect(jsonPath("$.role").doesNotExist())
        .andExpect(jsonPath("$.isAdmin").doesNotExist())
        .andExpect(jsonPath("$.internalRiskScore").doesNotExist());
}
```

Ví dụ kiểm tra quyền quản trị hoạt động đúng:

```java
@Test
@WithMockUser(username = "admin-test", authorities = "user:manage")
void adminWithManagePermissionCanUpdateRoleInAllowedScope() throws Exception {
    mockMvc.perform(patch("/api/admin/users/{id}", TestUsers.TARGET_ID)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "role": "SUPPORT", "accountStatus": "ACTIVE" }
                """))
        .andExpect(status().isOk());

    UserProfile saved = repository.findById(TestUsers.TARGET_ID).orElseThrow();
    assertThat(saved.getRole()).isEqualTo(UserRole.SUPPORT);
}
```

Test admin chỉ chứng minh quyền được cấp có hiệu lực trong phạm vi fixture; cần có test admin khác tenant hoặc không có quyền `user:manage` bị từ chối. Không dùng test dương tính này thay cho test âm tính của user quyền thấp.

## 10. Những biến thể test dễ bị bỏ sót

Một bộ test tốt không chỉ thử payload đơn giản `{"role":"ADMIN"}`. Hãy xem xét các đường dữ liệu mà framework và ứng dụng có thể xử lý khác nhau:

| Biến thể | Ví dụ | Điều cần xác minh |
|---|---|---|
| PUT thay PATCH | Gửi toàn bộ profile kèm `role` | Không ghi field đặc quyền |
| POST tạo object | Gửi `ownerId`, `tenantId`, `createdBy` | Máy chủ tự xác định field hệ thống |
| Nested object | `{"security":{"isAdmin":true}}` | Không lọt qua DTO lồng nhau |
| Mảng | `{"users":[{"id":"...","role":"ADMIN"}]}` | Mỗi phần tử đều được kiểm soát |
| Batch import | CSV có cột `role` | Import không ghi field cấm |
| JSON Patch | `replace /role` | Path bị cấm phải bị từ chối |
| JSON Merge Patch | `{"role":"ADMIN"}` | Field cấm không được áp dụng |
| GraphQL mutation | `updateUser(role: ADMIN)` | Resolver kiểm tra quyền property |
| Query/filter | Lọc theo `internalRiskScore` | Không cho suy luận dữ liệu cấm qua filter/sort |
| Export/report | CSV có cột `tenantId` hoặc `riskScore` | Chỉ xuất field caller được đọc |
| Trường null/default | `{"role":null}` hoặc bỏ field | Không vô tình reset field đặc quyền |
| Field trùng tên | JSON chứa hai key `role` | Parser và validator xử lý nhất quán; không dựa vào hành vi không xác định |

Với JSON Patch, phải allowlist cả operation lẫn path. Không chỉ kiểm tra key ở cấp cao nhất; các path như `/security/isAdmin`, `/permissions/0` hoặc `/members/0/role` cũng cần policy. Với filter/sort, việc không trả field trong response vẫn chưa đủ nếu người dùng có thể suy luận giá trị qua thứ tự hoặc kết quả truy vấn.

## 11. Kiểm tra trạng thái và side effect sau khi từ chối

Một request có thể trả `403` nhưng đã ghi dữ liệu trước khi kiểm tra quyền. Vì vậy, test phải kiểm tra state sau request:

1. Đọc và lưu snapshot các property nhạy cảm trước request.
2. Gửi request bằng principal quyền thấp với field đặc quyền.
3. Xác minh status và response đúng hợp đồng.
4. Đọc lại object bằng repository hoặc test fixture có quyền phù hợp.
5. So sánh property nhạy cảm với snapshot ban đầu.
6. Kiểm tra audit/event/queue nếu thao tác có thể kích hoạt side effect.

Ví dụ, nếu user gửi `accountStatus=ACTIVE` để mở khóa tài khoản, test cần xác minh không có event `AccountUnlocked`, không gửi thông báo mở khóa và trạng thái vẫn giữ nguyên. Nếu API ghi audit từ chối, audit event phải phân biệt rõ `DENY` với cập nhật thành công.

Đối với giao dịch có nhiều bước, kiểm tra rollback hoặc tính nguyên tử. Một field bị từ chối không được để các field khác hoặc các bảng liên quan thay đổi một phần trái với hợp đồng.

## 12. Status code và thông báo lỗi

Chọn status code theo loại lỗi và hợp đồng API:

- `400 Bad Request`: payload không đúng schema hoặc chứa field ngoài danh sách được endpoint chấp nhận.
- `403 Forbidden`: caller đã xác thực nhưng policy không cho phép đọc/ghi property.
- `404 Not Found`: dùng khi chính sách cần che giấu object không thuộc phạm vi caller.
- `409 Conflict`: thay đổi không phù hợp với trạng thái hiện tại hoặc xung đột nghiệp vụ.
- `422 Unprocessable Content`: nội dung hợp lệ về cú pháp nhưng vi phạm quy tắc xử lý đã công bố.

Không trả lỗi tiết lộ toàn bộ danh sách admin-only property, cấu trúc nội bộ hoặc tên trường bí mật nếu không cần thiết. Có thể trả mã lỗi ổn định như `PROPERTY_NOT_ALLOWED` với thông báo chung. Log nội bộ có thể ghi chi tiết hơn nhưng cần giới hạn quyền truy cập và tránh lưu secret hoặc toàn bộ dữ liệu cá nhân.

## 13. Checklist trước khi phát hành

- [ ] Đã xác định property nhạy cảm và nguồn dữ liệu có thẩm quyền cho từng trường.
- [ ] Đã tách quyền đọc và quyền ghi property.
- [ ] User quyền thấp có quyền thao tác object thông thường để test cô lập property authorization.
- [ ] Request DTO/allowlist không bind trực tiếp admin-only property vào entity.
- [ ] DTO lồng nhau, mảng, batch, import và patch document cũng có allowlist.
- [ ] Response DTO không trả property caller không được đọc.
- [ ] Có test user quyền thấp gửi `role`, `isAdmin`, `accountStatus`, `tenantId` và field đặc quyền tương tự.
- [ ] Có test user quyền thấp đọc detail, list, search, export và các endpoint thay thế.
- [ ] Có test admin hợp lệ và admin ngoài phạm vi bị từ chối.
- [ ] Sau request bị từ chối, database, event, queue và side effect không bị thay đổi ngoài hợp đồng.
- [ ] Status code và lỗi nhất quán, không tiết lộ dữ liệu nhạy cảm.
- [ ] Có audit/log phù hợp và không ghi token hoặc secret.
- [ ] Test chạy với fixture riêng, không dùng tài khoản hoặc dữ liệu production.

## Kết luận

Kiểm thử low-privilege user với admin-only property phải chứng minh hai điều: người dùng quyền thấp không thể đọc thuộc tính đặc quyền và không thể làm thay đổi thuộc tính đó qua bất kỳ request path nào. Hãy kiểm tra cả request/response, trạng thái database và side effect; dùng DTO/allowlist cho dữ liệu ghi, projection cho dữ liệu đọc và policy riêng cho thao tác quản trị. Quyền trên object hoặc endpoint không tự động cấp quyền trên mọi property của object.
