# Không tin client bỏ qua field nhạy cảm

Một API có thể kiểm tra token hợp lệ, xác minh người dùng có quyền cập nhật hồ sơ và vẫn cho phép người đó tự nâng quyền quản trị, đổi chủ sở hữu bản ghi hoặc sửa số dư tài khoản. Lỗi thường xuất hiện khi server nhận JSON từ client rồi ánh xạ trực tiếp vào entity hoặc object nghiệp vụ có nhiều thuộc tính nội bộ. Client chỉ gửi vài trường trên giao diện, nhưng một request tự tạo có thể bổ sung những trường mà giao diện không cho chỉnh sửa.

Đây là nhóm lỗi phân quyền ở cấp thuộc tính (Broken Object Property Level Authorization – BOPLA), thường gặp dưới dạng mass assignment hoặc over-posting. Nguyên tắc cốt lõi là **server phải tự xác định thuộc tính nào được phép đọc hoặc ghi trong từng ngữ cảnh**. Việc client bỏ qua field trên form, ẩn nút, không gửi thuộc tính hoặc không hiển thị dữ liệu không tạo ra ranh giới bảo mật. Mọi request đều có thể được tạo lại bên ngoài giao diện.

## 1. Vì sao field nhạy cảm vẫn có thể bị thay đổi?

Giả sử màn hình cập nhật hồ sơ chỉ cho người dùng đổi tên hiển thị và số điện thoại. Frontend gửi:

```http
PATCH /api/v1/me/profile HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "displayName": "An Nguyen",
  "phoneNumber": "+84-900-123-456"
}
```

Nhưng entity `User` trong backend còn có nhiều thuộc tính khác:

```java
public class User {
    private UUID id;
    private String displayName;
    private String phoneNumber;
    private String email;
    private String passwordHash;
    private String role;
    private UUID tenantId;
    private boolean enabled;
    private boolean verified;
    private BigDecimal accountBalance;
    private Instant lockedAt;
}
```

Nếu controller nhận trực tiếp `User` làm request body, một client có thể gửi thêm các thuộc tính không xuất hiện trên giao diện:

```http
PATCH /api/v1/me/profile HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "displayName": "An Nguyen",
  "phoneNumber": "+84-900-123-456",
  "role": "ADMIN",
  "tenantId": "00000000-0000-0000-0000-000000000999",
  "enabled": true,
  "verified": true,
  "accountBalance": 999999999
}
```

Nếu cơ chế binding ánh xạ các field này vào entity và service lưu toàn bộ object, request có thể thay đổi quyền, phạm vi tenant, trạng thái xác minh hoặc số dư. Người dùng đã xác thực vẫn có thể khai thác lỗi này vì server kiểm tra danh tính nhưng không kiểm soát thuộc tính được phép ghi.

Không cần giao diện có input cho field nhạy cảm. Kẻ tấn công có thể dùng DevTools, curl, Postman, proxy hoặc script để gửi request tùy ý. Bảo mật phải được thực thi ở server.

## 2. Phân biệt quyền trên object và quyền trên property

Quyền truy cập object trả lời câu hỏi: người gọi có được truy cập tài nguyên cụ thể này không? Quyền trên property trả lời câu hỏi: người gọi được đọc hoặc thay đổi những thuộc tính nào của tài nguyên đó?

Ví dụ, chủ đơn hàng được xem đơn hàng của mình nhưng không được tự sửa `totalAmount`, `paymentStatus` hoặc `customerId`. Nhân viên hỗ trợ có thể xem trạng thái giao hàng và địa chỉ theo phạm vi công việc nhưng không được đọc thông tin thanh toán đầy đủ. Quản trị viên có thể đổi vai trò người dùng trong tenant mình quản lý nhưng không được chuyển tài khoản sang tenant khác nếu không có quyền cấp cao hơn.

Một quyết định property authorization thường phụ thuộc vào:

- Danh tính và loại chủ thể: người dùng, quản trị viên, nhân viên hỗ trợ hay service account.
- Object cụ thể: chủ sở hữu, tenant, tổ chức, trạng thái và quan hệ với người gọi.
- Hành động: đọc, tạo, cập nhật, xóa, xuất hoặc chuyển trạng thái.
- Thuộc tính: trường được đọc hoặc ghi, kể cả field lồng nhau.
- Ngữ cảnh nghiệp vụ: mục đích truy cập, trạng thái quy trình, thời điểm và điều kiện phê duyệt.

Không nên có một quy tắc duy nhất kiểu “được sửa object thì sửa mọi field”. Quyền đọc và quyền ghi cũng phải tách riêng. Một người có thể được xem số dư nhưng không được điều chỉnh; một người khác có thể được cập nhật thông tin liên hệ nhưng không được xem ghi chú nội bộ.

## 3. Nhận diện các field cần bảo vệ

Không phải chỉ field có tên `password` mới nhạy cảm. Hãy phân loại dữ liệu theo tác động nếu bị đọc hoặc sửa trái phép.

| Nhóm field | Ví dụ | Rủi ro khi bị ghi trái phép | Rủi ro khi bị đọc trái phép |
|---|---|---|---|
| Danh tính và quyền | `role`, `permissions`, `isAdmin`, `ownerId` | Nâng quyền, chiếm quyền object | Lộ cấu trúc quyền và thông tin quản trị |
| Phạm vi dữ liệu | `tenantId`, `organizationId`, `projectId` | Chuyển object sang tenant khác, vượt ranh giới dữ liệu | Lộ quan hệ giữa tenant và project |
| Trạng thái tài khoản | `enabled`, `verified`, `lockedAt`, `mfaEnabled` | Bỏ khóa, tự xác minh, vô hiệu hóa kiểm soát | Lộ trạng thái bảo mật và xác minh |
| Tài chính | `balance`, `creditLimit`, `price`, `discount`, `paymentStatus` | Gian lận số dư, giá, hạn mức hoặc thanh toán | Lộ dữ liệu tài chính |
| Kiểm soát nghiệp vụ | `status`, `approvedBy`, `approvedAt`, `riskScore` | Bỏ qua bước duyệt, tự phê duyệt | Lộ thông tin kiểm soát nội bộ |
| Bí mật và xác thực | `passwordHash`, `apiSecret`, `refreshToken`, `mfaSecret` | Thay đổi cơ chế xác thực | Lộ credential và bí mật |
| Nội bộ và vận hành | `internalNotes`, `fraudFlags`, `deletedAt`, `createdBy` | Làm sai audit hoặc quy trình xử lý | Lộ ghi chú và dữ liệu vận hành |

Danh sách này chỉ là điểm bắt đầu. Một field bình thường như `email`, `shippingAddress` hoặc `dateOfBirth` vẫn có thể là dữ liệu cá nhân cần hạn chế đọc. Một field không nhạy cảm ở một endpoint có thể nhạy cảm ở endpoint khác do khác mục đích hoặc đối tượng nhận.

## 4. Mass assignment và over-posting

Mass assignment xảy ra khi framework hoặc mã ứng dụng tự động gán nhiều field từ request vào object đích. Over-posting là việc client gửi thêm thuộc tính ngoài tập field mà endpoint dự kiến nhận. Hai khái niệm thường xuất hiện cùng nhau trong lỗi phân quyền property.

Một đoạn code rủi ro trong Spring MVC có thể trông như sau:

```java
@PatchMapping("/api/v1/me/profile")
public User updateProfile(@RequestBody User user) {
    return userRepository.save(user);
}
```

Đoạn code này có nhiều vấn đề:

- Request body được bind vào entity có cả field nghiệp vụ và field nội bộ.
- Không có allowlist thể hiện rõ field nào endpoint cho phép cập nhật.
- Có thể ghi đè giá trị do server quản lý như `role`, `tenantId` hoặc `verified`.
- Có thể lưu entity chưa được tải từ database, làm mất dữ liệu hoặc phá vỡ quan hệ.
- Trả trực tiếp entity có thể làm lộ field không nên xuất hiện trong response.

Chỉ kiểm tra người dùng đã đăng nhập hoặc có quyền `profile:update` không khắc phục được những vấn đề này. Quyền chức năng không tự động cấp quyền sửa mọi thuộc tính.

## 5. Dùng request DTO theo allowlist

Biện pháp cơ bản và dễ review nhất là tạo DTO riêng cho từng thao tác. DTO chỉ chứa những field endpoint được phép nhận. Server tải object từ nguồn dữ liệu đáng tin cậy, sau đó gọi các phương thức nghiệp vụ rõ ràng để cập nhật đúng thuộc tính.

Ví dụ request DTO:

```java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Pattern(regexp = "^[+0-9() .-]{7,20}$")
    String phoneNumber
) {}
```

Controller xác định người dùng từ security context, không nhận `userId` hoặc `role` từ body để quyết định danh tính:

```java
@PatchMapping("/api/v1/me/profile")
public ProfileResponse updateMyProfile(
        @Valid @RequestBody UpdateProfileRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    UUID userId = UUID.fromString(jwt.getSubject());
    return userService.updateProfile(userId, request);
}
```

Service chỉ cập nhật các field có trong hợp đồng thao tác:

```java
@Transactional
public ProfileResponse updateProfile(
        UUID userId,
        UpdateProfileRequest request) {

    User user = userRepository.findById(userId)
        .orElseThrow(() -> new EntityNotFoundException("User not found"));

    user.changeDisplayName(request.displayName());
    user.changePhoneNumber(request.phoneNumber());

    return new ProfileResponse(
        user.getId(),
        user.getDisplayName(),
        user.getPhoneNumber()
    );
}
```

Trong ví dụ này, `User` được tải từ database theo danh tính đã xác thực. Service gọi các hành vi cụ thể của domain object thay vì sao chép mọi field từ request. `role`, `tenantId`, `enabled`, `verified` và `accountBalance` không nằm trong DTO nên request cập nhật hồ sơ không có khả năng điều khiển chúng.

DTO phải được thiết kế theo use case, không nên tạo một `UpdateUserRequest` tổng quát có hàng chục field rồi tái sử dụng cho mọi endpoint. Endpoint cập nhật hồ sơ, đổi email, thay mật khẩu, đổi vai trò và điều chỉnh hạn mức có quy tắc quyền cùng validation khác nhau.

Với `PATCH`, cần quy định rõ sự khác nhau giữa field bị bỏ qua và field được gửi với giá trị `null`. Ví dụ, không gửi `phoneNumber` có thể nghĩa là giữ nguyên; gửi `"phoneNumber": null` có thể nghĩa là xóa số điện thoại hoặc bị từ chối. DTO Java thông thường có thể biểu diễn cả hai trường hợp thành `null`, nên nếu cần phân biệt, hãy dùng kiểu dữ liệu có trạng thái presence như `JsonNullable<T>` hoặc một request model phù hợp. Không để việc deserialize vô tình xóa dữ liệu hay thay đổi field ngoài ý muốn.

## 6. Field nhạy cảm cần luồng nghiệp vụ riêng

Một số thuộc tính có thể được cập nhật trong hệ thống, nhưng chỉ qua thao tác có quyền và điều kiện nghiệp vụ cụ thể. Không nên đơn giản xóa khả năng thay đổi field đó khỏi toàn bộ ứng dụng; hãy đưa nó vào một command riêng.

Ví dụ thay đổi vai trò:

```java
public record ChangeUserRoleRequest(
    @NotBlank
    @Pattern(regexp = "^(USER|SUPPORT|MANAGER)$")
    String role
) {}
```

```java
@PreAuthorize("hasAuthority('users:role:assign')")
@PutMapping("/api/v1/admin/users/{userId}/role")
public UserAdminResponse changeRole(
        @PathVariable UUID userId,
        @Valid @RequestBody ChangeUserRoleRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    UUID actorId = UUID.fromString(jwt.getSubject());
    return userAdminService.changeRole(actorId, userId, request.role());
}
```

Annotation kiểm tra quyền chức năng. `userAdminService.changeRole` vẫn phải kiểm tra người gọi có quyền trên **userId cụ thể** và role đích hay không: ví dụ quản trị viên tenant A không được thay vai trò tài khoản tenant B; quản trị viên hỗ trợ không được cấp role quản trị toàn hệ thống; không được xóa quyền của quản trị viên cuối cùng nếu quy tắc hệ thống cấm điều đó.

Các thao tác như đổi email, xác minh tài khoản, thay số dư, hoàn tiền, duyệt hồ sơ hoặc chuyển trạng thái thanh toán cũng nên có command riêng. Service có thể yêu cầu xác thực lại, phê duyệt hai người, bằng chứng từ nhà cung cấp hoặc kiểm tra chuyển trạng thái hợp lệ.

## 7. Kiểm soát field khi đọc response

BOPLA không chỉ là lỗi ghi field. API còn có thể trả quá nhiều dữ liệu vì controller serialize toàn bộ entity. Ví dụ:

```java
@GetMapping("/api/v1/users/{userId}")
public User getUser(@PathVariable UUID userId) {
    return userRepository.findById(userId).orElseThrow();
}
```

Nếu entity có `passwordHash`, `mfaSecret`, `internalNotes`, `riskScore` hoặc dữ liệu tenant, các field đó có thể vô tình xuất hiện trong JSON. Annotation ẩn field trên một lớp entity có thể giúp giảm lỗi serialize, nhưng không thay thế response contract và kiểm tra quyền theo ngữ cảnh.

Dùng response DTO chỉ chứa dữ liệu được phép trả:

```java
public record ProfileResponse(
    UUID id,
    String displayName,
    String phoneNumber
) {}

public record UserAdminResponse(
    UUID id,
    String displayName,
    String email,
    String role,
    boolean enabled
) {}
```

`ProfileResponse` và `UserAdminResponse` phục vụ hai mục đích khác nhau. Không trả `UserAdminResponse` cho mọi người chỉ vì endpoint có thể tái sử dụng mapper. Với từng response, hãy xác định rõ đối tượng nhận, mục đích và field cần thiết.

### Quyền đọc field có thể thay đổi theo ngữ cảnh

Một nhân viên hỗ trợ có thể xem email đã che một phần để xác minh tài khoản, nhưng không cần thấy toàn bộ số giấy tờ. Chủ tài khoản có thể xem thông tin cá nhân của mình; quản trị viên tenant có thể xem một số field quản lý trong phạm vi tenant; bộ phận chống gian lận có thể cần một số cờ rủi ro theo mục đích công việc.

Nếu response thay đổi theo vai trò hoặc quan hệ, hãy xây dựng policy rõ ràng và tạo projection/DTO tương ứng. Không chỉ dựa vào một DTO chung rồi xóa field bằng logic rải rác ở controller. Cần kiểm tra quyền đọc trước khi truy vấn hoặc trước khi đưa field vào response, tùy cách triển khai và yêu cầu bảo vệ dữ liệu.

## 8. Bảo vệ field lồng nhau và collection

Field nhạy cảm không chỉ nằm ở cấp đầu của JSON. Một request có thể chứa object lồng nhau hoặc danh sách:

```json
{
  "profile": {
    "displayName": "An Nguyen"
  },
  "organization": {
    "tenantId": "tenant-other",
    "billingPlan": "ENTERPRISE"
  },
  "members": [
    {
      "userId": "user-9",
      "role": "OWNER"
    }
  ]
}
```

Nếu endpoint chỉ cho phép đổi tên hiển thị, nó không được cập nhật `organization.tenantId`, `billingPlan` hoặc role của các thành viên. Không giả định rằng việc kiểm tra object cha đã đủ để cho phép mọi object con.

Với mỗi quan hệ lồng nhau, hãy kiểm tra:

- Object con có thuộc object cha mà người gọi được phép thao tác không?
- Người gọi có quyền trên object con theo tenant và quan hệ sở hữu không?
- Field cụ thể trong object con có được phép đọc hoặc ghi không?
- Có thể thay ID tham chiếu để liên kết object của tenant khác không?
- Số lượng phần tử và độ sâu lồng nhau có giới hạn không?

Đối với batch update, phải kiểm tra từng phần tử và từng thuộc tính. Nếu một batch chứa 100 object, không được kiểm tra quyền trên phần tử đầu rồi mặc định 99 phần tử còn lại hợp lệ. Cũng cần xác định hành vi nguyên tử: toàn bộ batch thất bại khi một phần tử không được phép, hay chỉ xử lý các phần tử hợp lệ. Hợp đồng phải rõ ràng để tránh client hiểu nhầm kết quả.

## 9. PATCH, PUT và cập nhật động

`PUT` thường thay thế biểu diễn của tài nguyên tại URI đích; `PATCH` áp dụng một tập thay đổi. Dù dùng method nào, server vẫn phải định nghĩa field được phép ghi. Không được coi `PATCH` là quyền sửa tùy ý mọi thuộc tính.

Một số API nhận map động:

```json
{
  "updates": {
    "displayName": "An Nguyen",
    "role": "ADMIN"
  }
}
```

Nếu service lặp qua map rồi dùng reflection hoặc property path để set field theo tên do client cung cấp, đây là bề mặt mass assignment. Hãy dùng allowlist tường minh:

```java
private static final Set<String> PROFILE_FIELDS = Set.of(
    "displayName",
    "phoneNumber"
);

public void updateProfileFields(
        User user,
        Map<String, Object> updates) {

    for (String field : updates.keySet()) {
        if (!PROFILE_FIELDS.contains(field)) {
            throw new IllegalArgumentException("Unsupported field: " + field);
        }
    }

    if (updates.containsKey("displayName")) {
        user.changeDisplayName((String) updates.get("displayName"));
    }
    if (updates.containsKey("phoneNumber")) {
        user.changePhoneNumber((String) updates.get("phoneNumber"));
    }
}
```

Đây là ví dụ minh họa; triển khai thực tế cần validate kiểu dữ liệu, null, độ dài, format và quyền của actor trước khi gọi domain method. Allowlist cần gắn với endpoint/use case, không phải một danh sách toàn cục cho mọi loại cập nhật.

Nếu hỗ trợ JSON Patch (`application/json-patch+json`) hoặc JSON Merge Patch (`application/merge-patch+json`), hãy kiểm tra từng operation và path. Ví dụ, client không được dùng `replace /role`, `copy /tenantId` hoặc `move /ownerId` nếu endpoint không cấp quyền cho các đường dẫn đó. Cần giới hạn độ sâu, số operation và kích thước patch; từ chối path không thuộc allowlist.

## 10. Xử lý field không được hỗ trợ trong request

Khi client gửi field ngoài DTO, server có thể từ chối request hoặc bỏ qua field tùy cấu hình parser. Cả hai cách đều có thể phù hợp nếu được lựa chọn có chủ đích:

- **Từ chối field lạ:** giúp phát hiện client gửi nhầm hoặc cố thử field nhạy cảm. Phản hồi nên nêu tên field không được hỗ trợ nếu việc tiết lộ tên không gây rủi ro.
- **Bỏ qua field lạ:** có thể hỗ trợ tương thích giữa các phiên bản client, nhưng cần đảm bảo field bị bỏ qua thực sự không ảnh hưởng tới entity hoặc side effect.

Không dựa vào cấu hình `ignoreUnknown = true` hay mặc định của Jackson làm biện pháp phân quyền. Dù field lạ bị bỏ qua, field được khai báo trong DTO vẫn cần kiểm soát quyền và validation. Nếu DTO vô tình chứa `role`, field đó vẫn có thể bị bind.

Với API nhạy cảm, từ chối field không được hỗ trợ thường giúp phát hiện sớm lỗi hợp đồng. Tuy nhiên, việc từ chối phải được triển khai nhất quán theo phiên bản API và có test. Không nên thay đổi cấu hình parser toàn hệ thống mà không đánh giá ảnh hưởng tới các endpoint khác.

## 11. Các biện pháp bổ trợ trong Spring/Jackson

DTO riêng và mapping tường minh nên là lớp bảo vệ chính. Một số cơ chế framework có thể bổ trợ:

### Giới hạn field cho form binding

Với dữ liệu form được bind qua `@ModelAttribute`, Spring `WebDataBinder` có thể giới hạn field được phép:

```java
@InitBinder("profileForm")
void configureProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "phoneNumber");
}
```

Điều này áp dụng cho data binding qua `WebDataBinder`; không được nhầm nó với cơ chế kiểm soát JSON body được deserialize bằng Jackson qua `@RequestBody`. Với JSON, hãy thiết kế DTO allowlist và kiểm soát mapper/service.

### Annotation Jackson

`@JsonProperty(access = JsonProperty.Access.READ_ONLY)` có thể biểu diễn field chỉ được xuất khi serialize và không nhận giá trị đầu vào theo cấu hình Jackson tương ứng. `@JsonIgnore` có thể ẩn field trong quá trình serialize/deserialize. Tuy nhiên, annotation có thể ảnh hưởng nhiều endpoint dùng chung model và không thể thay thế chính sách quyền theo object/ngữ cảnh.

Không nên dựa vào một annotation trên entity để giải quyết mọi trường hợp. Cùng một field có thể được phép đọc ở endpoint quản trị, bị che ở endpoint hồ sơ và hoàn toàn không được trả ở endpoint công khai. DTO theo use case giúp hợp đồng rõ hơn.

### Mapping tường minh

Nếu dùng MapStruct hoặc mapper tự viết, hãy chỉ định các field được map. Với mapper từ request DTO sang entity, có thể cấu hình ignore các field server quản lý để tránh mapping tự động khi DTO thay đổi. Tuy nhiên, mapper không quyết định actor có quyền sửa field đó hay không; service vẫn phải kiểm tra policy và điều kiện nghiệp vụ.

## 12. Field authorization nên nằm ở đâu?

Controller chịu trách nhiệm nhận request, xác thực đầu vào và điều phối. Service/domain layer có đủ ngữ cảnh để kiểm tra quyền trên object, field và trạng thái nghiệp vụ. Không nên rải các điều kiện quyền ở nhiều controller khiến một endpoint mới dễ bỏ sót.

Có thể mô hình hóa policy theo actor, object, action và property:

```java
public interface UserPropertyPolicy {
    boolean canRead(User actor, User target, String property);
    boolean canWrite(User actor, User target, String property);
}
```

Ví dụ một policy đơn giản:

```java
public boolean canWrite(User actor, User target, String property) {
    if (actor.getId().equals(target.getId())) {
        return Set.of("displayName", "phoneNumber")
            .contains(property);
    }

    return actor.hasAuthority("users:profile:manage")
        && actor.getTenantId().equals(target.getTenantId())
        && Set.of("displayName", "phoneNumber")
            .contains(property);
}
```

Đây chỉ là ví dụ minh họa. Trong hệ thống thật, policy cần xem xét field, action, tenant, quan hệ, trạng thái, purpose và quyền đặc biệt. Không dùng tên property do client gửi để tự động truy cập reflection mà không qua allowlist và policy.

Nếu quyền phức tạp, có thể dùng policy engine hoặc mô hình ABAC (Attribute-Based Access Control). Dù chọn cách nào, cần có một điểm thực thi nhất quán và test bao phủ các tổ hợp actor–object–action–property.

## 13. Ma trận quyền đọc và ghi thuộc tính

Ma trận giúp nhóm phát triển, nghiệp vụ và bảo mật thống nhất field nào được phép đọc hoặc ghi trong từng vai trò. Ví dụ:

| Thuộc tính | Người dùng sở hữu | Nhân viên hỗ trợ | Quản trị viên tenant | Hệ thống |
|---|---|---|---|---|
| `displayName` | Đọc/ghi | Đọc/ghi theo case | Đọc/ghi | Có thể cập nhật qua đồng bộ |
| `phoneNumber` | Đọc/ghi | Đọc có che/ghi theo xác minh | Đọc/ghi theo chính sách | Có thể đồng bộ |
| `email` | Đọc; đổi qua luồng xác minh | Đọc có che | Đọc/ghi theo quy trình | Xác minh trạng thái |
| `role` | Không | Không | Gán trong phạm vi tenant | Đồng bộ theo policy |
| `tenantId` | Không | Không | Không tùy ý chuyển tenant | Chỉ luồng provisioning được phép |
| `passwordHash` | Không | Không | Không | Chỉ authentication service quản lý |
| `verified` | Không tự ghi | Không tự ghi | Không tự ghi trực tiếp | Luồng xác minh cập nhật |
| `accountBalance` | Đọc theo chính sách | Đọc có giới hạn | Đọc theo quyền tài chính | Ledger/payment service điều chỉnh |

Ma trận trên chỉ là ví dụ; mỗi hệ thống cần định nghĩa chính sách theo dữ liệu và vai trò thực tế. “Đọc có che” cũng cần xác định rõ cách che và trường hợp được xem đầy đủ. Với dữ liệu tài chính, thay đổi số dư nên được biểu diễn bằng giao dịch ledger hoặc lệnh nghiệp vụ có audit, không phải gán trực tiếp một con số từ request.

## 14. Những nguồn cập nhật khác ngoài JSON body

Mass assignment có thể đến từ nhiều kênh đầu vào:

- Query parameter như `?role=ADMIN` hoặc `?tenantId=...`.
- Path parameter được dùng làm ID object hoặc khóa quan hệ.
- Header tùy chỉnh như `X-Role`, `X-Owner-Id` hoặc `X-Tenant-Id`.
- Multipart form, file import CSV/Excel hoặc dữ liệu đồng bộ từ đối tác.
- GraphQL mutation, JSON Patch, message queue và event do service khác phát.
- Batch job, admin console hoặc script vận hành.

Mọi đường ghi dữ liệu phải áp dụng cùng nguyên tắc allowlist, authorization và validation. Không phải request nào cũng đến từ trình duyệt; service-to-service hoặc file import cũng có thể gửi field ngoài hợp đồng. Với event nội bộ, cần xác minh producer, schema, quyền service và nguồn dữ liệu.

## 15. Bảo vệ tính toàn vẹn và tránh cập nhật cạnh tranh

Ngay cả khi field được phép ghi, server cần kiểm tra giá trị và trạng thái hiện tại. Ví dụ, người dùng có thể đổi địa chỉ giao hàng khi đơn hàng đang `PENDING_FULFILLMENT`, nhưng không thể sửa sau khi đơn đã bàn giao vận chuyển. Quyền ghi field cần kết hợp với state transition hợp lệ.

Với field tài chính, giá, chiết khấu, số lượng và hạn mức, server phải tự tính hoặc đối chiếu dữ liệu từ nguồn đáng tin cậy. Không tin `unitPrice`, `totalAmount`, `discountAmount` hoặc `balance` do client gửi. Nếu client gửi giá để hiển thị, server vẫn cần tính lại khi tạo giao dịch.

Với thao tác nhạy cảm, nên dùng transaction, optimistic locking hoặc cơ chế đồng bộ phù hợp để tránh race condition. Ví dụ, hai request đồng thời cùng đọc trạng thái `PENDING` rồi cùng chuyển sang `APPROVED` có thể tạo side effect kép nếu không có kiểm tra phiên bản hoặc ràng buộc trạng thái nguyên tử.

Không dùng việc ẩn field trong response làm biện pháp bảo vệ tính toàn vẹn. Một field không được trả về vẫn có thể bị client tự thêm vào request. Kiểm soát ghi và kiểm soát đọc phải độc lập.

## 16. Kiểm thử property-level authorization

Test cần thử gửi các field mà giao diện không hiển thị, cũng như xác nhận response không lộ thuộc tính nội bộ.

| Nhóm test | Tình huống |
|---|---|
| Over-posting | Thêm `role`, `tenantId`, `ownerId`, `verified`, `balance` vào request cập nhật hồ sơ |
| Allowlist | Gửi field lạ, field chỉ đọc hoặc field không có trong DTO; xác nhận bị từ chối hoặc bỏ qua theo hợp đồng |
| Object và property | Người dùng A cập nhật field hợp lệ trên object B; người dùng A thử field nhạy cảm trên object của mình |
| Read authorization | Response không chứa `passwordHash`, `mfaSecret`, `internalNotes` hoặc field ngoài quyền |
| Nested object | Thay ID object con, tenant ID, role thành viên hoặc field lồng nhau |
| Dynamic patch | Gửi JSON Patch `replace /role`, `copy /tenantId` hoặc đường dẫn ngoài allowlist |
| State transition | Thử đổi `paymentStatus`, `verified`, `approvedAt` hoặc field trạng thái trực tiếp |
| Batch/import | Một phần tử trái quyền trong danh sách; field nhạy cảm trong file nhập |
| Concurrent update | Hai request cùng thay đổi field hoặc trạng thái; xác nhận không có side effect kép |
| Response variations | So sánh response giữa owner, support, tenant admin và anonymous; xác nhận field được che/ẩn đúng policy |

Ví dụ test tích hợp với Spring MockMvc:

```java
@Test
void profileUpdateMustNotChangeRole() throws Exception {
    mockMvc.perform(patch("/api/v1/me/profile")
            .with(jwt().jwt(jwt -> jwt.subject(USER_ID.toString())))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "An Nguyen",
                  "role": "ADMIN"
                }
                """))
        .andExpect(status().isBadRequest());

    User saved = userRepository.findById(USER_ID).orElseThrow();
    assertThat(saved.getRole()).isEqualTo("USER");
}
```

Test trên giả định API cấu hình từ chối field không được hỗ trợ. Nếu hợp đồng chọn bỏ qua field lạ, hãy kiểm tra response phù hợp và quan trọng nhất là xác nhận `role` trong database không thay đổi. Không chỉ kiểm tra status code: request trả `400` nhưng đã cập nhật dữ liệu trước khi lỗi vẫn là lỗi nghiêm trọng.

Ngoài test từng endpoint, có thể dùng property-based test hoặc fuzzing để sinh các tên field, cấu trúc lồng nhau và tổ hợp role/object. Test phải dựa trên policy đã xác định, không chỉ lặp lại implementation hiện tại.

## 17. Lỗi thường gặp khi xử lý field nhạy cảm

| Cách làm sai | Rủi ro | Cách xử lý |
|---|---|---|
| Bind JSON trực tiếp vào entity | Client có thể set field nội bộ | Dùng request DTO allowlist |
| Ẩn field trong frontend | Request tùy chỉnh vẫn gửi được field | Kiểm tra ở server |
| Chỉ dùng `@JsonIgnore` | Không diễn tả policy theo actor/object/ngữ cảnh và có thể ảnh hưởng endpoint khác | Dùng request/response DTO theo use case |
| Dùng một DTO update cho mọi endpoint | Field được phép ở endpoint này bị mở ở endpoint khác | Tách command theo hành động |
| Chỉ kiểm tra role ở controller | Bỏ sót quyền trên object hoặc field | Kiểm tra policy trong service/domain |
| Cho phép map động mọi tên property | Có thể set field qua reflection hoặc property path | Allowlist field và kiểu dữ liệu |
| Tin `tenantId` hoặc `ownerId` từ request | Có thể chuyển quyền sở hữu hoặc vượt tenant | Lấy phạm vi từ danh tính và quan hệ server-side |
| Chỉ test status code | Có thể đã có side effect trước khi trả lỗi | Kiểm tra cả dữ liệu và side effect |
| Trả thẳng entity | Có thể lộ field nội bộ | Dùng response DTO/projection |

## 18. Checklist review một endpoint cập nhật hoặc đọc dữ liệu

- [ ] Endpoint có request DTO riêng với danh sách field được phép nhận.
- [ ] Không bind trực tiếp request vào entity hoặc object chứa field nội bộ.
- [ ] Danh tính, owner và tenant được lấy từ nguồn đáng tin cậy phía server.
- [ ] Quyền chức năng, quyền object và quyền property được kiểm tra riêng.
- [ ] Field nhạy cảm có luồng nghiệp vụ riêng và điều kiện trạng thái rõ ràng.
- [ ] Nested object, collection, batch và patch path đều có allowlist và kiểm tra quyền.
- [ ] Giá, số dư, trạng thái thanh toán, role và dữ liệu xác minh do server hoặc service có thẩm quyền quản lý.
- [ ] Response DTO chỉ chứa field được phép đọc trong ngữ cảnh hiện tại.
- [ ] Field lạ được xử lý nhất quán theo hợp đồng; không dựa vào cấu hình parser như biện pháp authorization.
- [ ] Có test over-posting, field nhạy cảm, truy cập chéo tenant, nested object và response leakage.
- [ ] Test xác nhận database và side effect không đổi khi request bị từ chối.
- [ ] Thao tác nhạy cảm có audit, kiểm soát đồng thời và khả năng điều tra.

## Kết luận

Client có thể bỏ qua mọi giới hạn của giao diện và gửi bất kỳ field nào mà endpoint nhận được. Nếu server bind request trực tiếp vào entity hoặc serialize toàn bộ object, field nhạy cảm có thể bị sửa hoặc bị lộ dù người gọi đã qua xác thực. Hãy thiết kế request/response DTO theo từng use case, dùng allowlist, kiểm tra quyền đọc và ghi ở cấp property, giữ các field quan trọng trong luồng nghiệp vụ riêng, và kiểm thử cả dữ liệu sau xử lý lẫn response. Một endpoint chỉ an toàn khi server quyết định rõ ai được làm gì với từng thuộc tính của object trong đúng ngữ cảnh.
