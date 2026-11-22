# Ẩn field nội bộ khỏi response serialization

Trong chương **Property authorization** của module `SECURITY_API_SECURITY`, bảo vệ dữ liệu ở mức thuộc tính không dừng ở việc kiểm tra người gọi có được truy cập một đối tượng hay không. API còn phải quyết định **những field nào của đối tượng được phép xuất hiện trong response**. Một user có thể được quyền xem hồ sơ nhân viên nhưng không được xem lương, ghi chú nội bộ, token khôi phục hoặc thông tin phục vụ vận hành. Nếu server serialize nguyên entity rồi trả về, các field này có thể bị lộ dù giao diện không hiển thị chúng.

Response serialization là ranh giới cuối cùng trước khi dữ liệu rời khỏi service. Thiết kế an toàn cần chọn dữ liệu được phép trả về theo từng use case và principal, sau đó chuyển thành response model chuyên biệt. Không dựa vào việc frontend ẩn field, không xem tên field khó đoán là biện pháp bảo vệ và không mặc định rằng entity persistence có thể dùng làm API response.

## 1. Vì sao phải kiểm soát field ở response?

Một đối tượng trong database thường chứa nhiều thông tin hơn những gì client cần. Ví dụ `UserEntity` có thể bao gồm:

| Field | Mục đích lưu trữ | Có nên trả cho client thông thường? |
|---|---|---|
| `id` | Định danh user | Có thể, nếu use case cần |
| `displayName` | Tên hiển thị | Thường có |
| `email` | Địa chỉ email | Tùy quyền và mục đích |
| `passwordHash` | Xác minh mật khẩu | Không bao giờ |
| `resetTokenHash` | Quy trình khôi phục tài khoản | Không bao giờ |
| `mfaSecret` | Bí mật xác thực đa yếu tố | Không bao giờ |
| `tenantId` | Phạm vi dữ liệu nội bộ | Chỉ khi contract và quyền yêu cầu |
| `roleAssignments` | Quan hệ vai trò | Chỉ trả representation được phép |
| `riskScore` | Tín hiệu chống gian lận | Chỉ luồng nội bộ được ủy quyền |
| `createdAt` | Thời điểm tạo | Tùy contract |
| `deletedAt` | Trạng thái xóa mềm | Thường không trả trực tiếp |

Ngay cả field không phải bí mật xác thực cũng có thể nhạy cảm. `tenantId`, cờ moderation, trạng thái điều tra, internal note, version, nguồn dữ liệu hoặc metadata vận hành có thể giúp người gọi suy ra cấu trúc hệ thống hay thông tin của người khác.

Một response thừa field có thể gây ra nhiều vấn đề:

- **Information disclosure:** lộ dữ liệu cá nhân, bí mật, thông tin tenant hoặc trạng thái nội bộ.
- **Property-level authorization failure:** user được xem đối tượng nhưng được xem cả thuộc tính họ không có quyền.
- **Tăng bề mặt tấn công:** client biết thêm ID, trạng thái, cấu hình hoặc quan hệ có thể dùng để dò endpoint khác.
- **Ràng buộc tương thích ngoài ý muốn:** khi entity thêm field mới, API vô tình công bố field đó mà không qua review contract.
- **Khó kiểm soát dữ liệu:** nhiều endpoint serialize cùng entity theo cách khác nhau, khiến chính sách không nhất quán.

Nguyên tắc cần áp dụng là **allowlist response**: mỗi use case chỉ đưa vào response những field đã được xác định rõ. Nếu một field không được công bố trong response contract, mặc định không serialize field đó.

## 2. Phân loại field trước khi thiết kế response

Trước khi viết DTO hoặc serializer, lập danh mục field và phân loại theo mục đích, độ nhạy cảm, chủ thể dữ liệu và vai trò được phép đọc.

| Nhóm field | Ví dụ | Cách xử lý khuyến nghị |
|---|---|---|
| Công khai | Tên sản phẩm, mô tả công khai | Trả theo contract |
| Cá nhân | Email, số điện thoại, địa chỉ | Chỉ trả khi có mục đích và quyền phù hợp; có thể mask |
| Bí mật xác thực | Password hash, API key, refresh token, MFA secret | Không serialize vào response API |
| Nội bộ nghiệp vụ | Internal note, risk score, moderation state | Chỉ trả cho vai trò và use case được cấp quyền |
| Kỹ thuật/vận hành | Stack trace, SQL, internal host, debug flag | Không trả trong response công khai |
| Metadata quản trị | Tenant ID, owner ID, audit actor, soft-delete marker | Chỉ công bố nếu contract và quyền yêu cầu |

Phân loại cần xét cả field lồng nhau, collection, map và object được tham chiếu. Một `OrderResponse` có thể không lộ `customer.passwordHash` ở cấp đầu nhưng vẫn vô tình serialize toàn bộ `customer` trong nested object.

Nên ghi rõ cho từng endpoint:

- Field nào được trả về cho mọi principal đủ quyền đọc đối tượng.
- Field nào cần quyền bổ sung hoặc vai trò cụ thể.
- Field nào phải mask, ví dụ chỉ hiển thị một phần số điện thoại.
- Field nào tuyệt đối không được đưa vào response.
- Field nào do server tính toán và không được lấy nguyên từ entity.
- Field nào chỉ được trả trong một luồng chuyên biệt, chẳng hạn màn hình quản trị hoặc xuất dữ liệu.

Đừng dùng một nhãn chung như “admin thấy tất cả”. Vai trò quản trị cũng cần phạm vi và mục đích cụ thể. Quyền đọc hồ sơ không tự động bao gồm quyền đọc thông tin xác thực, bí mật tích hợp hoặc dữ liệu điều tra.

## 3. Tách persistence entity khỏi response DTO

### 3.1. Không serialize trực tiếp entity

Ví dụ sau tạo ra rủi ro vì response phụ thuộc vào toàn bộ field của entity:

```java
@RestController
@RequestMapping("/v1/users")
class UserController {
    private final UserRepository users;

    @GetMapping("/{id}")
    UserEntity getUser(@PathVariable UUID id) {
        return users.findById(id).orElseThrow();
    }
}
```

Nếu entity có `passwordHash`, `mfaSecret`, `internalNote` hoặc field mới được thêm sau này, serializer có thể đưa chúng vào JSON. Một số annotation có thể ẩn field hiện tại, nhưng entity vẫn mang trách nhiệm lưu trữ, quan hệ ORM và hành vi API trong cùng một kiểu dữ liệu. Điều đó làm việc review và kiểm soát thay đổi khó hơn.

Hãy tạo response DTO riêng:

```java
public record UserSummaryResponse(
        UUID id,
        String displayName,
        String avatarUrl
) {}
```

Controller hoặc service chuyển entity sang DTO đã chọn:

```java
@GetMapping("/{id}")
UserSummaryResponse getUser(@PathVariable UUID id) {
    UserEntity user = users.findById(id).orElseThrow();
    return new UserSummaryResponse(
            user.getId(),
            user.getDisplayName(),
            user.getAvatarUrl()
    );
}
```

DTO là allowlist có thể review: chỉ ba field được khai báo mới được đưa ra response. Khi entity được bổ sung field, response không tự thay đổi.

### 3.2. Tạo DTO theo use case

Không nhất thiết một entity chỉ có một response DTO. Cùng một User có thể có representation khác nhau:

```java
public sealed interface ProfileResponse
        permits PublicProfileResponse, OwnProfileResponse, SupportProfileResponse {
}

public record PublicProfileResponse(
        UUID id,
        String displayName,
        String avatarUrl
) implements ProfileResponse {}

public record OwnProfileResponse(
        UUID id,
        String displayName,
        String email,
        String phone,
        String avatarUrl,
        Instant createdAt
) implements ProfileResponse {}

public record SupportProfileResponse(
        UUID id,
        String displayName,
        String emailMasked,
        String accountStatus
) implements ProfileResponse {}
```

`PublicProfileResponse` dùng cho hồ sơ công khai; `OwnProfileResponse` dùng khi user xem dữ liệu của chính mình; `SupportProfileResponse` dành cho use case hỗ trợ được cấp quyền và chỉ trả thông tin cần thiết. Không tạo một DTO khổng lồ với mọi field rồi trông chờ từng controller nhớ loại bỏ field nhạy cảm.

Tên DTO nên phản ánh use case hoặc audience, không chỉ tên bảng. Điều đó giúp reviewer hiểu vì sao field xuất hiện và endpoint nào được phép dùng representation đó.

### 3.3. Mapping tường minh

Mapping tường minh giúp nhìn thấy dữ liệu nào rời khỏi entity:

```java
public final class UserResponseMapper {
    private UserResponseMapper() {}

    public static PublicProfileResponse toPublicProfile(UserEntity user) {
        return new PublicProfileResponse(
                user.getId(),
                user.getDisplayName(),
                user.getAvatarUrl()
        );
    }

    public static OwnProfileResponse toOwnProfile(UserEntity user) {
        return new OwnProfileResponse(
                user.getId(),
                user.getDisplayName(),
                user.getEmail(),
                user.getPhone(),
                user.getAvatarUrl(),
                user.getCreatedAt()
        );
    }
}
```

Với mapping framework tự động, cấu hình phải mặc định bỏ qua field không khai báo hoặc chỉ map theo danh sách được cho phép. Tránh cấu hình “map tất cả field cùng tên” rồi dựa vào developer nhớ loại trừ field nhạy cảm. Nếu dùng MapStruct, có thể dùng `unmappedTargetPolicy = ERROR` và khai báo mapping rõ ràng; vẫn cần review các mapping có chủ ý và DTO đích.

## 4. Áp dụng property authorization trước serialization

DTO allowlist ngăn entity tự động lộ field, nhưng một số field chỉ được trả cho một số principal. Khi đó cần kiểm tra quyền trước khi tạo representation.

Ví dụ: người dùng được xem hồ sơ công khai; chủ hồ sơ được xem email đầy đủ; nhân viên hỗ trợ có grant cụ thể chỉ được xem email đã mask.

Trong ví dụ, `principal.tenantId()` phải là tenant context đã được server xác minh từ token/session và membership. Không lấy giá trị này trực tiếp từ query, path hoặc body rồi gắn vào principal.

```java
public UserProfileResponse getProfile(UUID targetUserId, CurrentPrincipal principal) {
    UserEntity target = users.findByIdAndTenantId(targetUserId, principal.tenantId())
            .orElseThrow(() -> new ResourceNotFoundException("User not found"));

    boolean isOwner = target.getId().equals(principal.id());
    boolean canViewSupportContact = policy.canViewMaskedContact(principal, target);

    String email = null;
    if (isOwner) {
        email = target.getEmail();
    } else if (canViewSupportContact) {
        email = maskEmail(target.getEmail());
    }

    return new UserProfileResponse(
            target.getId(),
            target.getDisplayName(),
            email
    );
}
```

Ví dụ này minh họa cách quyết định field; contract thực tế cần xác định rõ field không có quyền sẽ bị bỏ qua, trả `null` hay trả lỗi. Không để từng endpoint tự chọn semantics khác nhau.

### 4.1. Omit, null hay mask?

Ba cách biểu diễn có ý nghĩa khác nhau:

| Cách xử lý | Response | Khi phù hợp |
|---|---|---|
| Omit | Không có key `email` | Field không thuộc representation của principal hoặc không muốn tiết lộ sự tồn tại/quyền |
| Null | `"email": null` | Contract định nghĩa field có mặt nhưng giá trị không được cung cấp |
| Mask | `"email": "a***@example.test"` | Caller được phép nhận một phần thông tin để xác minh hoặc hỗ trợ |

Không dùng `null` một cách tùy tiện: client có thể hiểu null là dữ liệu thực sự chưa có. Không dùng mask như một thay thế cho authorization nếu ngay cả một phần dữ liệu cũng không được phép tiết lộ. Omit có thể làm schema phụ thuộc role; khi đó OpenAPI cần mô tả rõ representation hoặc dùng schema response riêng.

Với field nhạy cảm, default-deny là lựa chọn phù hợp: chỉ thêm field khi policy cho phép. Đừng mặc định trả field rồi cố gắng xóa khi phát hiện principal không đủ quyền.

### 4.2. Kiểm tra quyền trên field lồng nhau

Ví dụ response đơn hàng có customer và payment:

```json
{
  "id": "ord_123",
  "status": "PAID",
  "customer": {
    "displayName": "An Nguyen"
  },
  "payment": {
    "method": "CARD",
    "last4": "4242"
  }
}
```

Không trả nguyên `CustomerEntity` hoặc `PaymentEntity` vào các thuộc tính nested. Tạo DTO lồng nhau riêng và kiểm tra quyền theo từng nhóm field. Ví dụ người xem đơn có thể xem tên người nhận và phương thức thanh toán nhưng không được xem billing address, transaction reference nội bộ hay dữ liệu xác thực.

Collection cũng phải được lọc theo quyền. Nếu một response có danh sách comment, chỉ map những comment principal được xem; không lấy toàn bộ rồi ẩn trong frontend. Nếu số lượng comment bị lọc ảnh hưởng đến count hoặc pagination, contract cần định nghĩa count theo tập dữ liệu caller được phép nhìn thấy.

## 5. Kiểm soát các cơ chế Jackson và Spring

Java/Spring thường dùng Jackson để serialize JSON. Jackson có nhiều cơ chế ẩn hoặc chọn field, nhưng mỗi cơ chế có semantics riêng. Chúng nên hỗ trợ DTO design, không thay thế nó.

### 5.1. `@JsonIgnore`

Có thể đánh dấu field không được serialize:

```java
public class UserEntity {
    private UUID id;
    private String displayName;

    @JsonIgnore
    private String passwordHash;

    @JsonIgnore
    private String mfaSecret;
}
```

Đây là lớp phòng vệ hữu ích cho bí mật tuyệt đối không được xuất hiện trong JSON. Tuy nhiên, annotation trên entity không đảm bảo mọi serializer, mapper, log hoặc export khác đều tuân thủ. Ngoài ra, `@JsonIgnore` có thể ảnh hưởng cả deserialize tùy cấu hình và vị trí đặt annotation. Không dùng nó như cách duy nhất để tạo representation khác nhau theo role.

Với password hash, secret, token hash và private key, tốt nhất là không đưa chúng vào bất kỳ response DTO nào ngay từ đầu. Có thể giữ `@JsonIgnore` như lớp phòng vệ bổ sung nếu entity có nguy cơ bị serialize ngoài ý muốn.

### 5.2. `@JsonView`

`@JsonView` cho phép chọn nhóm thuộc tính:

```java
public class UserViews {
    public interface Public {}
    public interface Owner extends Public {}
}

public class UserResponse {
    @JsonView(UserViews.Public.class)
    public UUID id;

    @JsonView(UserViews.Public.class)
    public String displayName;

    @JsonView(UserViews.Owner.class)
    public String email;
}
```

Controller có thể chọn view cho endpoint:

```java
@GetMapping("/{id}/public")
@JsonView(UserViews.Public.class)
UserResponse publicProfile(@PathVariable UUID id) {
    return service.getProfile(id);
}
```

`@JsonView` là cơ chế chọn field ở tầng serializer, không phải authorization engine. View phải được chọn sau khi server đã xác minh principal và policy. Cấu hình mặc định của Jackson về field không gắn view cũng cần được hiểu rõ; trong một số cấu hình, field không có view có thể vẫn được serialize. Không đặt secret vào object rồi giả định view luôn che được nó.

Khi các vai trò và điều kiện field phức tạp, nhiều DTO rõ ràng thường dễ review hơn một tập view lồng nhau. Nếu sử dụng view, hãy có test xác minh chính xác field được xuất ở từng view.

### 5.3. `@JsonFilter` và custom serializer

Jackson filter hoặc custom serializer có thể hữu ích khi field được chọn động theo policy. Tuy nhiên, logic động phải có default-deny, được kiểm thử và không phụ thuộc header do client tự đặt. Tránh xây dựng một filter tổng quát cho phép client truyền danh sách field tùy ý như `?fields=passwordHash,tenantId`; nếu có field selection, server vẫn phải giao cắt danh sách yêu cầu với allowlist và quyền của principal.

Custom serializer cũng cần kiểm tra nested object, collection và kiểu con. Một serializer an toàn ở cấp object có thể vô tình gọi serializer mặc định của nested entity rồi lộ field.

### 5.4. `@Transient` không phải biện pháp bảo mật response

`@Transient` trong JPA thường có nghĩa là thuộc tính không được persistence provider lưu trữ. Nó không đồng nghĩa với việc Jackson sẽ bỏ qua thuộc tính đó. Tương tự, `transient` của Java, `@JsonIgnore` và annotation persistence có semantics khác nhau. Không suy luận hành vi serialization từ annotation dành cho database.

## 6. Cẩn trọng với các nguồn rò rỉ ngoài field trực tiếp

### 6.1. Getter và computed property

Jackson có thể serialize property thông qua getter. Một getter như `getInternalStatus()` hoặc `isPrivileged()` có thể làm lộ dữ liệu dù field backing không public. Kiểm tra cả getter, record component, annotation ở field/method và cấu hình visibility của `ObjectMapper`.

Computed property cũng cần được review. Ví dụ `getCanRefund()` có thể tiết lộ thông tin về chính sách hoặc trạng thái nội bộ nếu không dành cho client. Chỉ tạo computed field khi contract cần và quyền cho phép.

### 6.2. Map và dynamic attributes

Một field `Map<String, Object> metadata` hoặc `@JsonAnyGetter` có thể đưa key/value không được kiểm soát vào response. Không chuyển nguyên metadata nội bộ ra JSON. Hãy lọc theo allowlist key, kiểu dữ liệu, kích thước và policy; tốt hơn là chuyển thành DTO có cấu trúc nếu schema đã biết.

Nếu dữ liệu dynamic đến từ plugin hoặc đối tác, coi nó là dữ liệu không tin cậy. Giới hạn độ sâu, số key và kích thước; không cho metadata ghi đè field chuẩn như `id`, `tenantId` hoặc `permissions`.

### 6.3. Quan hệ ORM và lazy loading

Serialize entity có quan hệ JPA có thể kéo theo nested entity, lazy proxy, vòng tham chiếu hoặc truy vấn ngoài dự kiến. Dùng DTO projection hoặc fetch cụ thể cho use case giúp tránh việc serializer tự duyệt graph entity. Không bật serialize toàn bộ quan hệ chỉ để giải quyết lỗi lazy loading.

### 6.4. Polymorphism và subtype

Nếu response chứa base type có nhiều subtype, cần kiểm soát subtype nào được serialize và field riêng của subtype đó. Không cho dữ liệu đầu vào chọn tùy ý class hoặc type name nội bộ. Dùng danh sách subtype được phép và response DTO riêng cho các biến thể công khai.

### 6.5. Error response và header

Field nội bộ có thể rò qua error object, header hoặc metadata chứ không chỉ response body. Không trả stack trace, exception message nguyên bản, SQL, đường dẫn file, host nội bộ, access token hoặc cấu hình. Header như `Server`, debug header và diagnostic detail cần được kiểm soát theo chính sách triển khai.

## 7. Ví dụ đầy đủ: response hồ sơ theo quyền

Giả sử API có ba use case: xem hồ sơ công khai, xem hồ sơ của chính mình và hỗ trợ khách hàng. Entity có thể chứa dữ liệu rộng:

`principal.tenantId()` trong ví dụ là tenant đã xác minh ở security context; repository dùng tenant này để giới hạn đối tượng trước khi policy quyết định field nào được trả về.

```java
@Entity
public class UserEntity {
    @Id
    private UUID id;
    private String displayName;
    private String email;
    private String phone;
    private String avatarUrl;
    private String passwordHash;
    private String mfaSecret;
    private UUID tenantId;
    private String internalNote;
    private String accountStatus;
    private Instant createdAt;
    private Instant deletedAt;
}
```

Sử dụng ba response DTO đã định nghĩa ở mục 3.2 để giữ representation tách biệt theo audience.

Policy service quyết định representation nào được phép:

```java
@Service
public class UserProfileService {
    private final UserRepository users;
    private final UserAccessPolicy policy;

    public UserProfileService(UserRepository users, UserAccessPolicy policy) {
        this.users = users;
        this.policy = policy;
    }

    public ProfileResponse getProfile(UUID targetId, CurrentPrincipal principal) {
        UserEntity user = users.findByIdAndTenantId(targetId, principal.tenantId())
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));

        if (policy.isOwner(principal, user)) {
            return new OwnProfileResponse(
                    user.getId(),
                    user.getDisplayName(),
                    user.getEmail(),
                    user.getPhone(),
                    user.getAvatarUrl(),
                    user.getCreatedAt()
            );
        }

        if (policy.canViewSupportProfile(principal, user)) {
            return new SupportProfileResponse(
                    user.getId(),
                    user.getDisplayName(),
                    maskEmail(user.getEmail()),
                    user.getAccountStatus()
            );
        }

        if (policy.isPublicProfileVisibleTo(principal, user)) {
            return new PublicProfileResponse(
                    user.getId(),
                    user.getDisplayName(),
                    user.getAvatarUrl()
            );
        }

        throw new ResourceNotFoundException("User not found");
    }

    private String maskEmail(String email) {
        int at = email.indexOf('@');
        if (at <= 1) {
            return "***";
        }
        return email.charAt(0) + "***" + email.substring(at);
    }
}
```

Đây là ví dụ rút gọn để minh họa việc chọn DTO sau khi kiểm tra policy. Các response record cùng implement `ProfileResponse` để service trả về kiểu rõ ràng thay vì `Object`. Contract cần mô tả các biến thể JSON được phép. Với API public ổn định, tách endpoint hoặc schema response theo use case thường giúp client dễ tích hợp và code review dễ hơn. Ngoài ra, việc đọc entity phải được giới hạn theo tenant và object authorization; ví dụ tập trung vào field-level response nên lược bớt phần đó.

## 8. Field selection do client yêu cầu

Một số API hỗ trợ sparse fieldset, ví dụ:

```http
GET /v1/users/usr_123?fields=id,displayName,email
```

Tính năng này có thể giảm payload, nhưng không được biến thành cơ chế cấp quyền. Server phải xác định tập field được caller yêu cầu, tập field contract cho phép và tập field principal được phép đọc; response chỉ được chứa giao của các tập đó.

```text
requestedFields = {id, displayName, email}
contractFields  = {id, displayName, email, phone}
permittedFields = {id, displayName}

responseFields = requestedFields
                 INTERSECT contractFields
                 INTERSECT permittedFields
```

Nếu client yêu cầu field không được phép, contract cần quy định trả lỗi hay bỏ qua field. Với dữ liệu nhạy cảm, từ chối rõ ràng thường giúp phát hiện việc client đang dựa vào field trái phép; bỏ qua có thể phù hợp nếu API công bố semantics đó. Không bao giờ phản chiếu tên field tùy ý vào reflection hoặc truy cập getter theo chuỗi mà không có allowlist.

Field selection không nên cho phép lấy `passwordHash`, `internalNote`, `tenantId` hoặc bất kỳ field nào chỉ tồn tại trong entity. Allowlist phải được xây dựng từ response schema công khai, không từ danh sách property của entity.

## 9. Cache và representation theo quyền

Nếu response thay đổi theo principal, role, tenant hoặc policy, cache phải phản ánh các yếu tố đó. Cache chỉ theo URL có thể khiến response đầy đủ của owner được trả cho người xem công khai nếu cùng endpoint tạo representation khác nhau.

Các lựa chọn:

- Tách endpoint hoặc URL theo representation công khai và representation cá nhân.
- Dùng cache key bao gồm tenant, principal hoặc policy version khi response phụ thuộc các giá trị đó.
- Đặt `Cache-Control: private` hoặc `no-store` cho response chứa dữ liệu cá nhân/nhạy cảm theo yêu cầu.
- Tránh shared CDN cache cho response được cá nhân hóa nếu không có cấu hình cache key và variation an toàn.
- Vô hiệu hóa cache khi quyền, membership, share hoặc field policy thay đổi.

Header `Vary` chỉ có ích khi cache thực sự phân biệt đúng request header liên quan. Không xem `Vary: Authorization` là giải pháp chung cho mọi loại cache; cần xác minh behavior của CDN, reverse proxy và browser cache. Với dữ liệu xác thực hoặc bí mật có rủi ro cao, `no-store` thường là lựa chọn rõ ràng hơn.

## 10. Response schema và API contract

OpenAPI nên mô tả response DTO thực tế, không mô tả entity database. Nếu response thay đổi theo role, cân nhắc schema riêng cho từng use case hoặc `oneOf` với discriminator rõ ràng khi phù hợp.

Ví dụ:

```yaml
openapi: 3.1.0
paths:
  /v1/users/{id}/public-profile:
    get:
      operationId: getPublicProfile
      responses:
        '200':
          description: Public profile
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PublicProfileResponse'
        '404':
          description: Profile not found
components:
  schemas:
    PublicProfileResponse:
      type: object
      additionalProperties: false
      required: [id, displayName]
      properties:
        id:
          type: string
          format: uuid
        displayName:
          type: string
          maxLength: 120
        avatarUrl:
          type: string
          format: uri
```

`additionalProperties: false` giúp schema công bố không chấp nhận field response ngoài danh sách nếu validator/client áp dụng; nó không tự ngăn server serialize thêm field. Implementation và contract test phải xác minh response thực tế không chứa thuộc tính ngoài schema.

Khi thêm field mới, cần review phân loại dữ liệu, quyền đọc, cache behavior và tác động tương thích. Không tự động công bố mọi field mới của DTO chỉ vì serializer có thể xử lý nó.

## 11. Kiểm thử response serialization

Kiểm thử cần xác minh dữ liệu thực sự xuất hiện trên wire. Unit test mapper là hữu ích nhưng chưa đủ, vì Jackson config, getter, nested serializer, controller advice hoặc filter có thể làm response khác với DTO dự kiến.

### 11.1. Kiểm tra allowlist và denylist

Với mỗi response type, kiểm tra các key được phép và các field tuyệt đối không được xuất hiện:

```java
@Test
void publicProfileMustNotExposeInternalFields() throws Exception {
    UserEntity user = userWithSensitiveFields();
    PublicProfileResponse response = UserResponseMapper.toPublicProfile(user);

    String json = objectMapper.writeValueAsString(response);
    JsonNode body = objectMapper.readTree(json);

    Set<String> fieldNames = new HashSet<>();
    body.fieldNames().forEachRemaining(fieldNames::add);
    assertThat(fieldNames)
            .containsExactlyInAnyOrder("id", "displayName", "avatarUrl");

    assertThat(body.has("passwordHash")).isFalse();
    assertThat(body.has("mfaSecret")).isFalse();
    assertThat(body.has("internalNote")).isFalse();
    assertThat(body.has("tenantId")).isFalse();

    assertThat(json)
            .doesNotContain("passwordHash")
            .doesNotContain("mfaSecret")
            .doesNotContain("internalNote")
            .doesNotContain("tenantId");
}
```

Đoạn test minh họa dùng AssertJ và Jackson; import/helper được lược bớt. Trong dự án thực tế, nên assert cấu trúc JSON bằng JSONPath hoặc JsonNode thay vì chỉ tìm chuỗi, đồng thời kiểm tra các nested object và array đệ quy.

### 11.2. Kiểm thử theo principal và role

Tạo ma trận test cho cùng một đối tượng:

| Principal | Quyền | Field mong đợi |
|---|---|---|
| Người xem công khai | `profile:read-public` | `id`, `displayName`, `avatarUrl` |
| Chủ hồ sơ | `profile:read-own` | Thêm `email`, `phone`, `createdAt` |
| Nhân viên hỗ trợ có grant | `support:read-contact-masked` | Email đã mask và trạng thái được phép |
| Nhân viên không có grant | Chỉ có quyền hỗ trợ chung | Không có email và internal note |
| Principal ngoài tenant | Không có quyền đối tượng | Từ chối theo policy; không trả object |

Không chỉ kiểm tra role; cần kiểm tra tenant, ownership, membership, grant, trạng thái và thời hạn. Test phải xác minh field bị ẩn ngay cả khi client tự thêm query `fields=email` hoặc gửi header yêu cầu debug.

### 11.3. Kiểm tra nested object và đường response phụ

Kiểm tra:

- Nested DTO, collection, map và dynamic metadata.
- Getter/computed property, polymorphic subtype và custom serializer.
- Error response, validation errors, pagination metadata và export.
- Response qua cache, gateway, GraphQL resolver và background download.
- Log, trace và audit event có chứa request/response body hay không.
- JSON thực tế sau khi đi qua toàn bộ HTTP stack.

Test regression nên chứa giá trị bí mật giả lập dễ nhận biết, ví dụ `SECRET_TEST_VALUE_...`, rồi xác minh chúng không xuất hiện trong body, header hoặc log được thu thập. Không dùng secret production trong test.

### 11.4. Kiểm tra schema contract

Chạy contract test để so response với OpenAPI/JSON Schema. Kiểm tra field bắt buộc, kiểu dữ liệu, enum, giới hạn và `additionalProperties`. Schema test giúp phát hiện field ngoài contract, nhưng cần test authorization riêng để xác minh mỗi principal chỉ nhận representation được phép.

## 12. Logging, tracing và observability

Một lỗi phổ biến là response đã lọc field nhưng hệ thống log toàn bộ entity hoặc DTO trước khi serialize. Log, trace, error reporting và debugging endpoint đều có thể trở thành kênh rò dữ liệu.

Nguyên tắc:

- Không log password, password hash, access/refresh token, MFA secret, API key, private key hoặc reset token.
- Hạn chế log email, số điện thoại, địa chỉ và dữ liệu cá nhân; mask hoặc pseudonymize khi cần.
- Không log nguyên request/response body mặc định cho endpoint nhạy cảm.
- Ghi metadata phục vụ điều tra như trace ID, actor ID, tenant ID, operation, resource type và kết quả policy ở mức tối thiểu.
- Phân quyền truy cập log và đặt thời hạn lưu giữ phù hợp.
- Kiểm tra SDK APM/error tracker có tự động capture header, body, exception hoặc local variable hay không.

Nếu cần ghi nhận field nào đã bị redacted, có thể log tên nhóm field hoặc policy decision code thay vì giá trị field. Ví dụ `response_redaction=CONTACT_FIELDS` giúp điều tra mà không phải lưu email thực.

## 13. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Trả entity trực tiếp | Field mới có thể tự động lộ | Dùng DTO allowlist theo use case |
| Chỉ ẩn field ở frontend | Client có thể đọc JSON đầy đủ | Lọc ở server trước serialization |
| Một DTO chứa mọi field | Controller dễ trả thừa dữ liệu | Tạo response model riêng theo audience/use case |
| Dùng `@JsonIgnore` làm giải pháp duy nhất | Không xử lý được quyền động và serializer khác | Dùng DTO; giữ ignore như lớp bảo vệ bổ sung cho secret |
| Tin `@JsonView` tự kiểm tra quyền | View là lựa chọn serializer, không phải policy engine | Xác minh policy trước khi chọn representation |
| Cho client chọn field tùy ý | Có thể truy cập getter hoặc field nội bộ | Giao field yêu cầu với schema allowlist và policy |
| Serialize nested entity | Lộ dữ liệu qua quan hệ ORM | Dùng nested DTO/projection riêng |
| Trả map metadata nguyên trạng | Key/value nội bộ lọt vào response | Allowlist và giới hạn dynamic attributes |
| Cache không phân biệt representation | Response của owner có thể tới user khác | Cache key/headers theo phạm vi hoặc no-store |
| Log nguyên response | Dữ liệu đã ẩn ở API vẫn lộ trong log | Redaction và kiểm soát log pipeline |

## 14. Checklist review trước khi phát hành

- [ ] Mỗi endpoint có response DTO riêng phù hợp use case và audience.
- [ ] Entity persistence không được serialize trực tiếp trong API công khai.
- [ ] Field được phân loại: công khai, cá nhân, bí mật, nội bộ và vận hành.
- [ ] Password hash, token, MFA secret và key không xuất hiện trong response model.
- [ ] Field nhạy cảm có policy đọc rõ ràng theo principal và đối tượng.
- [ ] Nested object, collection, map và subtype cũng dùng allowlist.
- [ ] Semantics omit/null/mask được công bố nhất quán.
- [ ] Getter, computed property, `@JsonAnyGetter` và custom serializer đã được review.
- [ ] Jackson annotation không được xem là thay thế authorization.
- [ ] Field selection của client chỉ chọn trong schema công khai và quyền được phép.
- [ ] Cache không chia sẻ response theo quyền sai phạm vi.
- [ ] OpenAPI phản ánh response thực tế và không mô tả entity nội bộ.
- [ ] Contract test xác minh không có additional properties ngoài dự kiến.
- [ ] Integration test kiểm tra JSON thực tế với nhiều principal/role/tenant.
- [ ] Error response, log, trace và export không làm lộ field nhạy cảm.

## Kết luận

Ẩn field nội bộ khỏi response serialization là một phần của property-level authorization và data minimization. Hãy xác định representation theo use case, tạo DTO allowlist, kiểm tra quyền trước khi thêm field và kiểm thử JSON thực tế sau toàn bộ HTTP stack. Các annotation như `@JsonIgnore` hay `@JsonView` có thể hỗ trợ serializer, nhưng quyết định field nào được phép rời khỏi hệ thống phải thuộc về policy phía server. Khi response contract tách biệt khỏi entity và mỗi field có lý do công bố rõ ràng, nguy cơ lộ dữ liệu ngoài ý muốn sẽ giảm và API dễ review, kiểm thử, duy trì hơn.
