# Test excessive data exposure và mass assignment

Một API có thể xác thực người dùng đúng nhưng vẫn làm lộ dữ liệu hoặc cho phép thay đổi thuộc tính ngoài quyền được cấp. Ví dụ, endpoint hồ sơ trả về cả `passwordHash`, `mfaSecret`, `internalRiskScore` dù giao diện chỉ cần tên và email; hoặc endpoint cập nhật hồ sơ nhận thêm `role`, `tenantId`, `isAdmin` rồi bind thẳng request vào entity. Cả hai lỗi đều xuất phát từ việc kiểm soát quyền ở mức endpoint hoặc object nhưng bỏ qua quyền trên từng property.

**Excessive data exposure** xảy ra khi response chứa thuộc tính nhiều hơn mức caller được phép hoặc cần nhận. **Mass assignment** xảy ra khi server tự động bind các field do client gửi vào model/entity mà không giới hạn field được phép thay đổi. Hai vấn đề này thuộc nhóm Broken Object Property Level Authorization (BOPLA) trong OWASP API Security Top 10 2023: quyền truy cập object không tự động đồng nghĩa quyền đọc hoặc ghi mọi thuộc tính của object.

Trong API Security, cần thiết kế riêng contract đọc và contract ghi, áp dụng property-level authorization theo actor, object, tenant và nghiệp vụ, sau đó kiểm thử cả nội dung response lẫn side effect. Không nên dựa vào việc frontend ẩn field hoặc không gửi field nhạy cảm; attacker có thể gọi API trực tiếp bằng request tự tạo.

## 1. Phân biệt object authorization và property authorization

Authorization có nhiều lớp. Một user có thể được phép truy cập một object nhưng chỉ được xem hoặc sửa một phần thuộc tính của object đó.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Function-level authorization | Caller có được gọi chức năng này không? | Chỉ support agent mới được mở chức năng quản lý tài khoản. |
| Object-level authorization (BOLA) | Caller có được truy cập object cụ thể không? | User chỉ được xem đơn hàng thuộc tenant của mình. |
| Property-level read authorization | Caller có được đọc field cụ thể không? | User xem hồ sơ của mình nhưng không xem `internalRiskScore`. |
| Property-level write authorization | Caller có được thay đổi field cụ thể không? | User sửa `displayName` nhưng không được tự đặt `role=ADMIN`. |

Ví dụ `GET /api/users/{id}` có thể kiểm tra user hiện tại được xem hồ sơ đó. Nhưng điều đó chưa trả lời user có được xem `personalEmail`, `salary`, `mfaEnabled`, `riskScore` hay `supportNotes` hay không. Tương tự, `PATCH /api/users/{id}` có thể kiểm tra user được cập nhật hồ sơ của mình, nhưng vẫn phải giới hạn field được cập nhật.

### 1.1. Hai hướng lỗi cần kiểm thử riêng

**Excessive data exposure (read):** server serialize object/entity quá rộng hoặc truy vấn tất cả field rồi trả nguyên object. Client nhận được dữ liệu nhạy cảm dù giao diện không hiển thị.

**Mass assignment (write):** server bind request vào entity hoặc object domain có nhiều setter. Client gửi thêm field ngoài contract như `role`, `ownerId`, `tenantId`, `creditLimit`, `emailVerified` hoặc `status`; nếu binder cập nhật được field đó, caller có thể nâng quyền hoặc thay đổi trạng thái.

Hai hướng có thể xuất hiện cùng lúc: endpoint cho phép user tự đổi `role`, rồi endpoint hồ sơ trả `role` và thông tin nội bộ cho mọi caller. Cần có test cho cả đọc và ghi, không chỉ test status code.

## 2. Excessive data exposure: dữ liệu trả về vượt quá quyền

Lỗi thường xảy ra khi controller trả trực tiếp JPA entity, ORM model hoặc object nội bộ. Serializer tự chuyển các field có thể truy cập thành JSON, kể cả field không thuộc API contract.

Ví dụ không an toàn:

```java
@GetMapping("/api/users/{id}")
public User getUser(@PathVariable UUID id) {
    return userRepository.findById(id).orElseThrow();
}
```

Nếu `User` có các field như `passwordHash`, `mfaSecret`, `role`, `tenantId`, `internalNotes` hoặc quan hệ `billingAccount`, response có thể làm lộ chúng tùy cấu hình serialization. `@JsonIgnore` trên một số field có thể giảm lộ dữ liệu nhưng không thay thế response contract riêng và dễ bị bỏ sót khi entity thay đổi.

### 2.1. Xác định dữ liệu theo mức nhạy cảm

Trước khi thiết kế response, lập danh mục field và xác định ai được đọc chúng:

| Field ví dụ | Phân loại | Quyền đọc gợi ý |
| --- | --- | --- |
| `id`, `displayName`, `avatarUrl` | Thông tin hồ sơ cơ bản | User sở hữu object; một phần có thể public theo privacy setting. |
| `email`, `phoneNumber` | PII/contact | Owner và role nghiệp vụ được phê duyệt; có thể mask theo use case. |
| `passwordHash`, `resetToken`, `mfaSecret` | Credential/security secret | Không trả qua API thông thường; chỉ dùng nội bộ cho chức năng xác thực. |
| `role`, `permissions`, `tenantId` | Security/tenancy metadata | Chỉ role quản trị hoặc service được phép; không để user tự đọc tenant khác. |
| `internalRiskScore`, `fraudFlags` | Dữ liệu kiểm soát nội bộ | Risk/fraud service hoặc role được ủy quyền. |
| `supportNotes`, `moderationReason` | Ghi chú nội bộ | Nhân viên có nhiệm vụ và phạm vi phù hợp. |
| `createdAt`, `updatedAt` | Metadata vận hành | Có thể trả nếu contract cần; không mặc định public. |

Phân loại phải dựa trên nghiệp vụ và luật bảo vệ dữ liệu áp dụng. Không phải mọi field nhạy cảm đều cần che hoàn toàn; một số có thể trả dạng mask hoặc chỉ cho role cụ thể. Quyết định cần được thể hiện trong contract và test.

### 2.2. Response DTO theo allowlist

Tạo response DTO riêng chỉ chứa field được phép trả. Không dùng entity làm response model và không dựa vào frontend để bỏ qua field thừa.

```java
public record UserProfileResponse(
    UUID id,
    String displayName,
    String email,
    Instant createdAt
) {}

@GetMapping("/api/users/{id}")
public UserProfileResponse getProfile(@PathVariable UUID id) {
    return userService.getProfileFor(currentActor(), id);
}
```

Trong service, `getProfileFor` cần kiểm tra object-level permission và property policy trước khi tạo DTO; ví dụ chỉ đưa email vào response nếu actor được đọc email của user đó. Response DTO hoạt động như allowlist: field mới được thêm vào entity sẽ không tự xuất hiện trong JSON. Nếu một role được phép xem thêm dữ liệu, có thể dùng DTO riêng như `AdminUserResponse` thay vì trả một DTO lớn rồi cố ẩn field ở controller.

```java
public record AdminUserResponse(
    UUID id,
    String displayName,
    String email,
    String role,
    String tenantId,
    Instant createdAt
) {}
```

Việc chọn DTO phải nằm sau authorization rõ ràng. Không để caller tự gửi `?view=admin` hoặc `?includeInternal=true` rồi được nhận field quản trị nếu chưa được kiểm tra quyền.

### 2.3. Property policy cho response động

Một số field phụ thuộc vào object, tenant hoặc quan hệ giữa actor và resource. Khi đó, service/policy layer quyết định field nào được đọc. Không đặt logic này rải rác trong serializer hoặc template.

Ví dụ khái niệm:

```java
public UserProfileResponse toProfile(User user, Actor actor) {
    authorization.requireCanReadUser(actor, user);

    String email = propertyPolicy.canReadEmail(actor, user)
        ? user.getEmail()
        : null;

    return new UserProfileResponse(
        user.getId(),
        user.getDisplayName(),
        email,
        user.getCreatedAt()
    );
}
```

Nếu dùng `null` để biểu diễn field không được phép xem, cần bảo đảm contract phân biệt được “không có giá trị” với “không được phép đọc”. Có thể dùng DTO khác nhau hoặc response schema theo role để tránh nhập nhằng. `@JsonInclude(NON_NULL)` có thể bỏ field null khỏi JSON nhưng không nên dùng như cơ chế authorization chính.

### 2.4. Projection để giảm dữ liệu được tải

DTO allowlist kiểm soát dữ liệu trả ra; database projection có thể giảm cả dữ liệu được truy vấn vào memory. Với màn hình hồ sơ cơ bản, chỉ select các cột cần thiết thay vì load toàn bộ entity có credential hoặc quan hệ lớn.

```java
public interface UserProfileView {
    UUID getId();
    String getDisplayName();
    String getEmail();
    Instant getCreatedAt();
}

public interface UserRepository extends Repository<User, UUID> {
    Optional<UserProfileView> findProfileByIdAndTenantId(
        UUID id, UUID tenantId);
}
```

Projection không thay thế authorization. Query vẫn cần lọc tenant/object theo actor và policy. Không lấy `tenantId` từ request nếu nó phải được xác định từ security context hoặc quan hệ đã được kiểm tra.

## 3. Mass assignment: request ghi vượt contract

Mass assignment thường xuất hiện khi server bind JSON trực tiếp vào entity/domain object:

```java
@PatchMapping("/api/users/{id}")
public User update(
        @PathVariable UUID id,
        @RequestBody User user) {
    User current = userRepository.findById(id).orElseThrow();
    BeanUtils.copyProperties(user, current);
    return userRepository.save(current);
}
```

Client có thể gửi:

```json
{
  "displayName": "Lan Nguyen",
  "role": "ADMIN",
  "tenantId": "another-tenant",
  "emailVerified": true,
  "creditLimit": 1000000000,
  "accountStatus": "ACTIVE"
}
```

Nếu entity có setter tương ứng và code copy field không có allowlist, server có thể cập nhật thuộc tính mà caller không được phép kiểm soát. Việc frontend không hiển thị input cho các field này không bảo vệ API.

### 3.1. Request DTO chỉ nhận field được phép

Thiết kế command/request DTO theo use case cụ thể:

```java
public record UpdateOwnProfileRequest(
    @NotBlank @Size(max = 80) String displayName,
    @Email @Size(max = 254) String contactEmail
) {}
```

Service chỉ áp dụng các field đã được xác định:

```java
@Transactional
public UserProfileResponse updateOwnProfile(
        Actor actor,
        UUID userId,
        @Valid UpdateOwnProfileRequest request) {

    User user = userRepository.findByIdAndTenantId(
        userId, actor.tenantId()).orElseThrow(NotFoundException::new);

    authorization.requireCanUpdateOwnProfile(actor, user);

    user.changeDisplayName(request.displayName());
    user.changeContactEmail(request.contactEmail());

    return mapper.toProfile(user, actor);
}
```

`role`, `tenantId`, `emailVerified`, `creditLimit` và `accountStatus` không có trong request DTO nên không thể bị bind qua endpoint cập nhật hồ sơ này. Tenant được lấy từ actor đã xác thực và object được truy vấn trong phạm vi tenant.

### 3.2. Field quản trị phải đi qua use case riêng

Nếu có chức năng đổi role, hãy tạo endpoint/command riêng với quyền mạnh hơn, validation và audit:

```java
public record ChangeUserRoleRequest(@NotNull UserRole role) {}

@PreAuthorize("hasAuthority('users:role:manage')")
@PostMapping("/api/admin/users/{id}/role")
public AdminUserResponse changeRole(
        @PathVariable UUID id,
        @Valid @RequestBody ChangeUserRoleRequest request) {
    return userAdminService.changeRole(currentActor(), id, request.role());
}
```

Ví dụ giả định method security đã được bật bằng `@EnableMethodSecurity` và authority được map từ identity đã xác thực. Service quản trị vẫn cần kiểm tra tenant, phạm vi quản lý, separation of duties và quy tắc không cho admin tự nâng quyền nếu nghiệp vụ cấm. Endpoint riêng không tự động an toàn nếu thiếu object-level authorization.

### 3.3. Không copy toàn bộ property tự động

Tránh các mẫu:

- `BeanUtils.copyProperties(request, entity)` mà không có allowlist rõ.
- Model mapper tự map mọi field cùng tên giữa request và entity.
- `entity.setProperties(requestMap)` với map tùy ý.
- `Map<String, Object>` hoặc `JsonNode` được áp dụng trực tiếp vào domain object.
- Generic patch handler cập nhật bất kỳ property path nào.

Nếu dùng mapper, khai báo mapping tường minh và kiểm thử field nhạy cảm không thể thay đổi. Mapper chỉ là công cụ chuyển đổi; nó không quyết định quyền.

## 4. Field-level authorization khi đọc và ghi

Property authorization phải kết hợp identity, role/scope, object ownership, tenant và trạng thái nghiệp vụ.

Ví dụ policy:

| Actor | Object | Field | Quyền |
| --- | --- | --- | --- |
| User thường | Hồ sơ của mình | `displayName`, `contactEmail` | Read/write theo contract. |
| User thường | Hồ sơ của mình | `role`, `tenantId`, `emailVerified` | Không được ghi; một số field có thể không được đọc. |
| Manager | Hồ sơ nhân viên thuộc phạm vi quản lý | `displayName`, `department` | Read/write theo policy. |
| HR role | Nhân viên thuộc phạm vi HR | `salary`, `employmentStatus` | Read/write theo nhiệm vụ và audit. |
| Security admin | User trong phạm vi quản trị | `role`, `mfaEnabled` | Read hoặc thay đổi qua workflow được phê duyệt. |
| Service integration | Object thuộc client/tenant được cấp | Field được định nghĩa trong event/API contract | Chỉ quyền tối thiểu theo scope. |

Không suy luận quyền field chỉ từ role chung. Ví dụ `MANAGER` không có nghĩa được xem mọi salary; cần kiểm tra quan hệ quản lý và phạm vi tổ chức. Không tin `ownerId`, `tenantId` hoặc role do client gửi; dùng identity đã xác minh và dữ liệu quan hệ từ server.

### 4.1. Đọc field: lọc trước khi serialize

Chọn response model sau khi policy được đánh giá. Không serialize entity đầy đủ rồi dùng regex hoặc filter JSON ở gateway để xóa field nhạy cảm. Cách lọc sau dễ bỏ sót nested object, alias, collection, error path hoặc phiên bản schema mới.

Với API có nhiều role, có thể dùng:

- DTO riêng cho từng use case/role.
- Projection riêng cho query có dữ liệu nhạy cảm.
- Mapper có policy rõ ràng và test theo actor/object.
- Field mask được server kiểm tra quyền, nếu API có contract chọn field.

Nếu hỗ trợ `fields=name,email,role`, server phải kiểm tra quyền cho từng field được yêu cầu. Không cho phép field mask trở thành đường vòng để đọc property nội bộ.

### 4.2. Ghi field: validate và authorize từng thay đổi

Request DTO giới hạn tập field, nhưng một số field hợp lệ vẫn có thể cần policy theo object. Ví dụ `department` chỉ được manager thay đổi trong đơn vị của mình; `contactEmail` chỉ được owner cập nhật; `status` chỉ được thay đổi qua state transition.

Quy trình nên là:

1. Xác thực caller và kiểm tra quyền gọi chức năng.
2. Load object trong phạm vi tenant/owner đã xác minh.
3. Kiểm tra object-level authorization.
4. Xác định tập field client yêu cầu thay đổi.
5. Kiểm tra field-level write authorization cho từng field.
6. Validate kiểu, độ dài, format, range và business invariant.
7. Áp dụng command/domain method, không set property tùy ý.
8. Lưu thay đổi và audit actor, field category, decision và kết quả.

Nếu một request chứa cả field được phép và field bị cấm, nên từ chối toàn bộ request theo contract rõ ràng để tránh partial update khó dự đoán. Chỉ chấp nhận partial success khi API có semantics tường minh và client hiểu được kết quả từng field.

## 5. Nested object, collection và mass assignment gián tiếp

Không chỉ field ở cấp đầu tiên mới nguy hiểm. JSON có thể chứa object lồng nhau, array hoặc map:

```json
{
  "displayName": "Lan",
  "preferences": {
    "theme": "dark",
    "billing": {
      "ownerId": "other-user",
      "paymentLimit": 999999
    }
  },
  "members": [
    {"userId": "u-2", "role": "OWNER"}
  ]
}
```

Nếu endpoint chỉ nhằm cập nhật theme nhưng nhận cả `preferences` object hoặc generic map, attacker có thể thử sửa field sâu hơn. Cần DTO nested riêng và allowlist từng cấp.

Ví dụ:

```java
public record UpdatePreferencesRequest(
    @NotNull @Valid DisplayPreferences display
) {}

public record DisplayPreferences(
    @NotNull Theme theme
) {}
```

Chỉ `theme` thuộc contract; các field billing/member không được bind vào request này. Với collection, kiểm tra quyền trên từng phần tử và quan hệ object; không tin ID con chỉ vì nó nằm trong object cha caller có thể truy cập.

### 5.1. JSON Patch và JSON Merge Patch

`PATCH` có thể dùng JSON Patch (`application/json-patch+json`) hoặc JSON Merge Patch (`application/merge-patch+json`). Các format này cho phép biểu diễn thay đổi linh hoạt nhưng cũng làm tăng nguy cơ mass assignment nếu server áp dụng path bất kỳ vào entity.

Nếu dùng JSON Patch:

- Allowlist operation (`add`, `replace`, `remove`, `test`) theo contract.
- Allowlist JSON Pointer path; từ chối `/role`, `/tenantId`, `/permissions`, `/ownerId` nếu caller không có quyền.
- Kiểm tra path sau khi decode/normalize đúng chuẩn, tránh bypass bằng escape hoặc path alias.
- Kiểm tra quyền trên từng field và nested object trước khi áp dụng patch.
- Không áp dụng patch trực tiếp lên JPA entity rồi mới kiểm tra.
- Xác minh atomicity: nếu một operation bị cấm, không để operation trước đó đã commit một phần.

Nếu dùng Merge Patch, định nghĩa rõ khác biệt giữa field bị bỏ qua, field `null` và field được xóa. Không để `null` vô tình xóa field hoặc reset giá trị nhạy cảm ngoài ý muốn.

### 5.2. Polymorphic deserialization và type metadata

Không bật cơ chế polymorphic/default typing rộng cho JSON không tin cậy nếu không có allowlist type chặt chẽ. DTO API nên có kiểu cụ thể và schema được xác định. Type metadata do client gửi không được quyết định class nội bộ cần instantiate.

## 6. Các bề mặt API dễ bị bỏ sót

Kiểm tra property-level authorization không chỉ trên endpoint detail:

- List/search: field nhạy cảm có bị trả trong từng item hoặc filter/sort không?
- Bulk read/export: export có lấy nhiều field hơn endpoint detail không?
- Bulk update/import: một record có thể thay đổi field quản trị hoặc object thuộc tenant khác không?
- Nested resource: response của order có lộ thông tin customer/payment không cần thiết không?
- GraphQL: resolver có trả field nhạy cảm hoặc cho mutation sửa field không được phép không?
- WebSocket/event stream: event có phát quá nhiều property đến subscriber không?
- Webhook: payload gửi cho partner có chứa field nội bộ hoặc PII ngoài hợp đồng không?
- Error response: exception/validation error có phản chiếu field nội bộ, token hoặc dữ liệu đã submit không?
- Cache: response khác nhau theo role/tenant có bị cache và trả nhầm cho caller khác không?
- File/report: PDF, CSV, spreadsheet hoặc generated document có field vượt quyền dù JSON endpoint đã lọc không?

Một response DTO an toàn ở endpoint detail không chứng minh export hoặc GraphQL resolver an toàn. Tạo inventory theo route, operation và data object để bao phủ mọi cách đọc/ghi.

## 7. Thiết kế test cho excessive data exposure

Test response cần kiểm tra field nhạy cảm không xuất hiện, không chỉ kiểm tra field mong muốn có mặt. Nếu response có nested object/array, phải kiểm tra cả các phần tử lồng nhau.

### 7.1. Test theo role và quan hệ object

Tạo fixture với dữ liệu nhạy cảm có marker rõ ràng:

- `passwordHash = TEST_HASH_SHOULD_NEVER_LEAK`
- `mfaSecret = TEST_MFA_SECRET_SHOULD_NEVER_LEAK`
- `internalRiskScore = 9876`
- `supportNotes = INTERNAL_ONLY_MARKER`

Gọi endpoint bằng các actor khác nhau: owner, user cùng tenant, user tenant khác, manager, support agent và security admin. Với mỗi actor, xác định field nào được phép xuất hiện. Không chỉ test owner và admin.

### 7.2. Ví dụ Spring MockMvc kiểm tra response allowlist

```java
@Test
void profileResponseDoesNotExposeInternalProperties() throws Exception {
    mockMvc.perform(get("/api/users/{id}", userId)
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("users:profile:read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(userId.toString()))
        .andExpect(jsonPath("$.displayName").value("Lan"))
        .andExpect(jsonPath("$.passwordHash").doesNotHaveJsonPath())
        .andExpect(jsonPath("$.mfaSecret").doesNotHaveJsonPath())
        .andExpect(jsonPath("$.internalRiskScore").doesNotHaveJsonPath())
        .andExpect(jsonPath("$.supportNotes").doesNotHaveJsonPath());
}
```

Test phải chạy với dữ liệu fixture thực sự có các field nhạy cảm; nếu fixture không có field, assertion có thể pass giả. Nên xác nhận dữ liệu trong repository trước request hoặc dùng integration fixture rõ ràng. `doesNotHaveJsonPath()` kiểm tra property không hiện diện trong JSON; không chỉ kiểm tra giá trị là `null` hoặc chuỗi rỗng.

### 7.3. Test nested response và export

Với `GET /api/orders`, kiểm tra mỗi item không chứa `customer.passwordHash`, `payment.providerToken` hoặc `internalFraudFlags`. Lặp lại cùng policy cho CSV/PDF export, list, search và GraphQL. Nếu export có schema khác, tài liệu hóa field riêng và test độc lập.

## 8. Thiết kế test cho mass assignment

Test mass assignment phải gửi các field nhạy cảm do attacker tự thêm, sau đó xác minh dữ liệu trong database không đổi. Response `400` hoặc `403` là hữu ích nhưng chưa đủ nếu một phần side effect đã xảy ra.

### 8.1. Test thêm field ngoài contract

Ví dụ request độc hại:

```json
{
  "displayName": "Lan Updated",
  "role": "ADMIN",
  "tenantId": "tenant-victim",
  "emailVerified": true,
  "creditLimit": 999999
}
```

Kết quả mong đợi phụ thuộc contract:

- Nếu API strict reject unknown fields: trả lỗi validation/contract, không có field nào được cập nhật.
- Nếu API bỏ qua unknown fields: chỉ `displayName` được cập nhật; field nhạy cảm giữ nguyên và có thể ghi security event về input bất thường.
- Nếu field được phép cập nhật nhưng caller không có quyền theo object: trả `403` hoặc response policy thống nhất, không có side effect.

Với endpoint nhạy cảm, reject unknown fields thường giúp phát hiện client cố gửi field ngoài contract. Dù chọn reject hay ignore, tuyệt đối không bind field lạ vào entity.

### 8.2. Ví dụ test kiểm tra database không bị thay đổi

```java
@Test
void profileUpdateCannotChangeRoleOrTenant() throws Exception {
    User before = userRepository.findById(userId).orElseThrow();
    assertThat(before.getRole()).isEqualTo(UserRole.USER);
    assertThat(before.getTenantId()).isEqualTo(tenantA);

    mockMvc.perform(patch("/api/users/{id}", userId)
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("users:profile:write")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "Lan Updated",
                  "role": "ADMIN",
                  "tenantId": "tenant-victim",
                  "emailVerified": true
                }
                """))
        .andExpect(status().is2xxSuccessful());

    User after = userRepository.findById(userId).orElseThrow();
    assertThat(after.getDisplayName()).isEqualTo("Lan Updated");
    assertThat(after.getRole()).isEqualTo(UserRole.USER);
    assertThat(after.getTenantId()).isEqualTo(tenantA);
    assertThat(after.isEmailVerified()).isFalse();
}
```

Ví dụ giả định contract bỏ qua field không biết và chỉ nhận field có trong `UpdateOwnProfileRequest`. Nếu cấu hình strict unknown-property thì thay assertion status bằng `400` và vẫn kiểm tra toàn bộ state không đổi. Test phải dùng database/repository thật hoặc test slice phù hợp để xác minh persistence, không chỉ mock mapper.

### 8.3. Test field hợp lệ nhưng không đủ quyền

Một field có trong DTO vẫn có thể bị giới hạn theo role hoặc object. Ví dụ manager được đổi `department` cho nhân viên thuộc nhóm của mình nhưng không được đổi cho nhân viên nhóm khác. Test phải bao gồm:

- Field hợp lệ + actor có quyền + object đúng phạm vi: thành công.
- Field hợp lệ + actor không có quyền: từ chối và state không đổi.
- Field hợp lệ + object thuộc tenant khác: từ chối hoặc không tiết lộ sự tồn tại theo contract.
- Nhiều field, trong đó một field bị cấm: không có partial update ngoài ý muốn.
- Field do server quản lý: luôn lấy từ server-side context/domain logic.

## 9. Test matrix tổng hợp

| Nhóm | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Read allowlist | User đọc hồ sơ của mình | Chỉ field trong profile contract xuất hiện. |
| Read privilege | User thường đọc hồ sơ người khác | Object policy được áp dụng; field riêng tư không lộ. |
| Read tenant | User tenant A đọc object tenant B | Không truy cập object hoặc dữ liệu theo policy. |
| Sensitive field | Response có password hash, MFA secret, internal note | Field không xuất hiện trong response. |
| Nested data | Order chứa payment/customer/internal object | Chỉ nested field được phép xuất hiện. |
| List/search | Collection trả nhiều object | Cùng property policy áp dụng cho từng item. |
| Export | CSV/PDF/bulk export | Không có field vượt quyền so với export contract. |
| Mass assignment | Gửi `role`, `tenantId`, `isAdmin` ngoài DTO | Reject hoặc ignore theo contract; DB field không đổi. |
| Nested mass assignment | Gửi field cấm trong nested object/array | Không thể cập nhật nested property ngoài allowlist. |
| JSON Patch | Replace `/role` hoặc `/ownerId` | Bị từ chối; không có partial mutation. |
| Field-level write | Field có trong DTO nhưng actor không đủ quyền | Từ chối và state không đổi. |
| Server-managed field | Gửi `createdAt`, `ownerId`, `verifiedAt` | Server bỏ qua hoặc reject; giá trị lấy từ domain logic. |
| Unknown property | Gửi field không có trong schema | Hành vi reject/ignore đúng contract, không mass assign. |
| Polymorphic JSON | Gửi type metadata ngoài allowlist | Không instantiate class nội bộ tùy ý. |
| Cache isolation | Hai role nhận representation khác nhau | Cache không trả response của role/tenant này cho role/tenant khác. |
| Error response | Validation/exception có chứa submitted secret | Không phản chiếu secret hoặc field nội bộ. |
| Audit | Field nhạy cảm bị sửa hoặc request bị từ chối | Ghi actor, action, resource, field category và decision; không log giá trị secret. |

## 10. Kiểm thử contract và schema

OpenAPI/JSON Schema nên mô tả request/response model riêng. Nếu dùng một schema entity cho cả read và write, client dễ hiểu nhầm field nào được phép cập nhật và response có thể phơi bày field nội bộ.

Các điểm cần kiểm tra:

- Request schema chỉ liệt kê property được phép nhận cho operation đó.
- Response schema chỉ liệt kê field được phép trả; không tham chiếu entity schema nội bộ.
- Required/optional/null semantics được định nghĩa rõ.
- Enum, string length, numeric range và array size có giới hạn.
- Unknown property policy nhất quán theo version/endpoint.
- Field read-only/write-only được mô tả đúng nhưng vẫn được enforce ở server.
- Nested schema cũng có allowlist và giới hạn depth/size.
- Breaking change không vô tình thêm field nhạy cảm vào response hoặc mở rộng writable properties.

`readOnly`/`writeOnly` trong OpenAPI là metadata cho tooling và client generation; không thay thế kiểm tra quyền ở server. Một field được đánh dấu read-only vẫn phải bị từ chối hoặc bỏ qua nếu client gửi nó trong request.

### 10.1. Consumer-driven contract tests

Consumer-driven contract test có thể xác nhận consumer chỉ phụ thuộc field đã công bố, nhưng không chứng minh server không trả thêm dữ liệu nhạy cảm. Bổ sung security assertions kiểm tra response không chứa field nội bộ và request không thể sửa server-managed property.

Khi thêm field mới vào entity hoặc DTO, review cần hỏi:

- Field này có xuất hiện trong response nào không?
- Role/tenant nào được đọc?
- Có được phép ghi qua API không? Operation nào?
- Có cần audit hoặc masking không?
- Có ảnh hưởng cache, export, webhook hoặc event payload không?

## 11. Cache, serialization và các kênh phụ

Ngay cả khi controller trả đúng DTO, cache hoặc serializer có thể làm lộ dữ liệu nếu representation phụ thuộc actor nhưng cache key không phản ánh khác biệt đó.

- Response chứa PII hoặc dữ liệu riêng tư thường cần `Cache-Control: private` hoặc `no-store` tùy nghiệp vụ.
- Nếu cache dùng chung giữa caller, phải partition theo mọi dimension ảnh hưởng đến authorization/representation; không dựa vào `Vary: Authorization` một cách máy móc nếu cache layer không bảo đảm semantics.
- Không cache response admin rồi trả cho user thường cùng URL.
- Serialization của nested entity cần được kiểm tra, tránh vòng quan hệ hoặc lazy-loaded field ngoài dự kiến.
- Error handler, debug endpoint, GraphQL introspection và API documentation cũng là bề mặt dữ liệu.
- Log/trace không nên ghi toàn bộ response body; field đã được lọc khỏi client vẫn có thể bị lộ trong telemetry.

## 12. Audit và giám sát

Không nên ghi giá trị secret hoặc toàn bộ nội dung field nhạy cảm khi audit. Ghi nhận quyết định và loại field đủ để điều tra:

- Actor/client reference đã xác minh.
- Action và resource reference.
- Field category hoặc property name theo allowlist, nếu không tiết lộ dữ liệu nhạy cảm.
- Kết quả `ALLOW`/`DENY`, reason code và timestamp.
- Request/correlation ID và kết quả persistence.

Các tín hiệu cần theo dõi:

- Request gửi nhiều field ngoài contract hoặc server-managed property.
- Tần suất `403`/`400` tăng trên endpoint update/admin.
- Client liên tục thử `role`, `tenantId`, `isAdmin`, `ownerId` hoặc field nhạy cảm.
- Response size tăng bất thường hoặc field mới xuất hiện sau deploy.
- Export/list endpoint trả dữ liệu nhạy cảm với số lượng lớn.
- Property denial tăng ở một tenant/consumer sau khi thay đổi policy.

Metric label nên dùng route template, method, outcome và reason code hữu hạn; không dùng user ID, resource ID, raw property value hoặc payload. Audit chi tiết cần access control và retention phù hợp.

## 13. Quy trình đánh giá một endpoint

Với mỗi endpoint đọc/ghi, thực hiện các bước:

1. Xác định actor, client, tenant và business purpose.
2. Xác định object/resource được truy cập và kiểm tra BOLA.
3. Liệt kê toàn bộ property có thể được đọc hoặc ghi, kể cả nested/derived field.
4. Phân loại property theo độ nhạy và owner nghiệp vụ.
5. Định nghĩa allowlist response và request riêng cho operation.
6. Xác định field-level policy theo actor-object-state.
7. Kiểm tra serialization, cache, export, GraphQL/webhook và telemetry.
8. Tạo positive/negative test với field hợp lệ, field cấm và object ngoài phạm vi.
9. Xác minh database state và side effect sau request bị từ chối.
10. Lưu kết quả, evidence, owner và remediation trong security assessment.

Ví dụ endpoint `PATCH /api/users/{id}` có thể có contract như sau:

| Thành phần | Quyết định |
| --- | --- |
| Actor | User đã đăng nhập. |
| Object | Hồ sơ user thuộc tenant từ security context. |
| Allowed request fields | `displayName`, `contactEmail`. |
| Forbidden/server-managed fields | `id`, `tenantId`, `role`, `permissions`, `emailVerified`, `createdAt`. |
| Allowed response fields | `id`, `displayName`, `contactEmail`, `createdAt`. |
| Object policy | Actor chỉ cập nhật hồ sơ của mình. |
| Property policy | Chỉ hai field trong request DTO được thay đổi. |
| Negative tests | Tenant khác, role injection, nested field, unknown property, JSON Patch path cấm. |
| Evidence | MockMvc response, database before/after, audit decision và API schema. |

## 14. Các lỗi triển khai thường gặp

- **Trả thẳng entity:** entity thay đổi thì response có thể tự lộ field mới.
- **Dùng cùng DTO cho request và response:** field nội bộ hoặc server-managed dễ bị bind nhầm.
- **Tin frontend ẩn field:** attacker có thể gửi request tùy ý.
- **Chỉ kiểm tra object-level permission:** caller được xem object nhưng không được xem mọi field.
- **Dùng `@JsonIgnore` như authorization:** không diễn đạt được quyền theo actor/object và có thể ảnh hưởng cả serialization/deserialization.
- **Copy property tự động:** mapper có thể cập nhật field ngoài contract.
- **Chỉ test status code:** request trả `403` nhưng một side effect đã xảy ra trước đó.
- **Chỉ test field vắng mặt khi fixture không có dữ liệu:** test pass giả.
- **Không kiểm tra list/export/nested:** field nhạy cảm vẫn rò ở operation khác.
- **Cho JSON Patch path tùy ý:** attacker cập nhật field không có trong DTO thông thường.
- **Dùng cache chung cho representation khác nhau:** user thường nhận response đã tạo cho admin.
- **Log raw request/response:** secret và PII vẫn bị lộ dù API response đã lọc.

## 15. Checklist test excessive data exposure và mass assignment

- [ ] Có inventory object và property nhạy cảm theo nghiệp vụ.
- [ ] Phân biệt function, object, property read và property write authorization.
- [ ] Controller không trả trực tiếp JPA entity hoặc model nội bộ.
- [ ] Response DTO/projection chỉ chứa field được phép; field mới không tự xuất hiện.
- [ ] Request DTO riêng cho từng command/use case; không bind entity trực tiếp.
- [ ] Field server-managed như role, tenant, owner, verification và timestamps không thể bị client gán.
- [ ] Nested object, collection, map và JSON Patch có allowlist riêng.
- [ ] Field-level policy xét actor, object, tenant và trạng thái nghiệp vụ.
- [ ] Unknown property policy được định nghĩa và test; reject/ignore đều không được mass assign.
- [ ] Test response xác minh key nhạy cảm không xuất hiện ở detail, list, search, export và nested resource.
- [ ] Fixture test có giá trị nhạy cảm thật để tránh assertion pass giả.
- [ ] Test malicious write xác minh cả database state và side effect không đổi.
- [ ] Test mixed allowed/forbidden field không tạo partial update ngoài ý muốn.
- [ ] OpenAPI request/response schema tách biệt và không dùng entity schema.
- [ ] Cache, GraphQL, webhook, file export, error response và telemetry tuân cùng property policy.
- [ ] Audit quyết định field-level mà không ghi raw secret/PII.

Excessive data exposure và mass assignment đều là lỗi phân quyền ở mức thuộc tính. Response phải chỉ trả field caller được phép đọc; request chỉ nhận field caller được phép thay đổi. DTO/projection allowlist, property policy ở service/domain và test xác minh dữ liệu thực tế trước/sau request giúp biến contract thành kiểm soát có thể kiểm chứng. Khi đánh giá đầy đủ nested object, list/export, cache và các kênh phụ, API giảm nguy cơ lộ dữ liệu cũng như nâng quyền qua field ngoài dự kiến.
