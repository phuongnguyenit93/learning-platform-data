# Không serialize entity domain trực tiếp ra API

Một entity trong domain hoặc ORM mô tả dữ liệu và trạng thái mà ứng dụng cần quản lý. Nó thường chứa nhiều thuộc tính nội bộ, quan hệ giữa các bảng, thông tin phục vụ persistence và quy tắc nghiệp vụ. API response lại là hợp đồng dữ liệu dành cho một nhóm client cụ thể. Hai mục đích này khác nhau, vì vậy không nên trả trực tiếp entity domain từ controller để framework tự serialize thành JSON.

Ví dụ, entity `User` có thể chứa `passwordHash`, `roles`, `mfaSecret`, `internalNote`, `deletedAt` và quan hệ tới `Organization`. Người dùng chỉ cần xem tên hiển thị và email. Nếu controller trả entity nguyên vẹn, một thay đổi nhỏ trong model hoặc cấu hình Jackson có thể vô tình làm lộ thuộc tính nội bộ, dữ liệu của object liên quan hoặc cấu trúc database.

Trong API Security, output filtering là việc quyết định rõ **ai được đọc thuộc tính nào của object nào trong ngữ cảnh nào**. Cách phổ biến là tạo response DTO hoặc projection riêng cho từng use case, ánh xạ tường minh từ domain model sau khi đã xác minh quyền. Request DTO cũng cần tách riêng để client chỉ gửi được những trường mà chức năng cho phép thay đổi.

## 1. Entity domain và API representation phục vụ hai mục đích khác nhau

Entity thường được thiết kế để biểu diễn trạng thái và quan hệ của domain, hỗ trợ persistence và thực thi nghiệp vụ. API representation được thiết kế để truyền dữ liệu vừa đủ cho một chức năng, với tên trường, cấu trúc và mức chi tiết ổn định.

| Domain entity | API DTO/representation |
|---|---|
| Phản ánh mô hình nghiệp vụ và persistence | Phản ánh hợp đồng mà client được phép sử dụng |
| Có thể chứa ID nội bộ, trạng thái kỹ thuật và dữ liệu nhạy cảm | Chỉ chứa trường cần thiết cho use case |
| Có quan hệ ORM, lazy proxy hoặc collection | Có cấu trúc phẳng hoặc lồng nhau có chủ đích |
| Có thể thay đổi theo refactor database/domain | Nên thay đổi có kiểm soát theo version API |
| Có thể được cập nhật bởi domain service | Là dữ liệu trao đổi; không nên được xem là nguồn trạng thái đáng tin cậy |

Ví dụ entity người dùng:

```java
@Entity
@Table(name = "users")
public class User {
    @Id
    private UUID id;
    private String email;
    private String displayName;
    private String passwordHash;
    private String mfaSecret;
    private boolean enabled;
    private boolean emailVerified;
    private String internalNote;

    @ManyToOne(fetch = FetchType.LAZY)
    private Organization organization;

    @ManyToMany(fetch = FetchType.LAZY)
    private Set<Role> roles;
}
```

Entity này có các trường cần cho xác thực, quản trị và persistence. Một trang hồ sơ công khai có thể chỉ cần `displayName` và ảnh đại diện. Trả toàn bộ entity sẽ tạo nguy cơ lộ `passwordHash`, `mfaSecret`, ghi chú nội bộ, role hoặc dữ liệu tổ chức.

## 2. Rủi ro khi serialize entity trực tiếp

### Lộ thuộc tính nhạy cảm hoặc nội bộ

Framework serializer thường duyệt các thuộc tính có thể truy cập theo cấu hình. Khi entity có thêm field mới, field đó có thể tự xuất hiện trong response dù người viết controller không chủ ý công khai nó. Những thuộc tính nguy hiểm thường gồm:

- Password hash, reset token, MFA secret, API key hoặc thông tin xác thực.
- Vai trò, quyền nội bộ, cờ quản trị hoặc trạng thái kiểm duyệt.
- Ghi chú nhân viên, lý do khóa tài khoản, risk score và dữ liệu điều tra.
- Số dư, giá vốn, chiết khấu nội bộ hoặc thông tin thanh toán không dành cho client đó.
- ID nội bộ, foreign key, tên bảng/cột hoặc thông tin hạ tầng không cần thiết.
- Dữ liệu cá nhân của object liên quan như địa chỉ, email hoặc số điện thoại.

Một response có thể không chứa password rõ nhưng vẫn làm lộ password hash hoặc secret dùng để xác thực. Không xem hash là dữ liệu công khai.

### Lộ dữ liệu qua quan hệ lồng nhau

Entity `Order` có thể tham chiếu `Customer`, `Payment`, `Address` và `Employee`. Khi serialize entity, serializer có thể đi theo quan hệ và đưa dữ liệu của các object liên quan vào response. Quyền xem đơn hàng không tự động cho phép xem mọi thuộc tính của khách hàng, thông tin thanh toán hoặc ghi chú nhân viên.

Quan hệ ORM cũng có thể tạo vòng tham chiếu, ví dụ `Order.customer.orders`. Điều này có thể gây lỗi đệ quy, response rất lớn hoặc vô tình phơi bày cả collection không liên quan. Các annotation xử lý vòng lặp chỉ thay đổi cách serialize; chúng không quyết định người gọi có quyền xem dữ liệu hay không.

### Phụ thuộc vào cấu trúc ORM và hiệu năng

Entity có thể chứa lazy proxy và collection. Serialize trực tiếp có thể kích hoạt truy vấn ngoài dự kiến, gây N+1 query, tải dữ liệu lớn hoặc lỗi `LazyInitializationException` khi persistence context đã đóng. Một response tưởng như đơn giản có thể khiến ORM tải cả graph object.

### Rò rỉ chi tiết triển khai và khóa chặt API vào database

Khi response phản ánh trực tiếp entity, đổi tên field, quan hệ hoặc kiểu dữ liệu trong domain có thể làm thay đổi API ngoài ý muốn. Client bị phụ thuộc vào cấu trúc persistence; việc refactor database trở thành thay đổi hợp đồng API.

### Tạo đường ghi dữ liệu ngoài ý muốn

Nếu cùng entity được dùng để nhận request body và trả response, client có thể gửi thêm trường như `role`, `ownerId`, `tenantId`, `enabled` hoặc `status`. Việc bind trực tiếp body vào entity có thể dẫn tới mass assignment/overposting. Tách response DTO và request DTO giúp kiểm soát hai hướng dữ liệu riêng biệt.

## 3. Dùng response DTO theo allowlist

Response DTO định nghĩa chính xác các trường được phép xuất hiện trong response. Hãy ưu tiên allowlist: khai báo trường cần trả thay vì lấy toàn bộ entity rồi cố gắng loại bỏ vài field nhạy cảm.

Ví dụ:

```java
public record UserProfileResponse(
    UUID id,
    String displayName,
    String email
) {}
```

Controller trả DTO:

```java
@GetMapping("/api/v1/profile")
public UserProfileResponse getProfile(@AuthenticationPrincipal Jwt jwt) {
    UUID userId = UUID.fromString(jwt.getSubject());
    return userService.getProfile(userId);
}
```

Service hoặc mapper ánh xạ các trường được phép:

```java
@Transactional(readOnly = true)
public UserProfileResponse getProfile(UUID userId) {
    User user = userRepository.findById(userId)
        .orElseThrow(() -> new EntityNotFoundException("User not found"));

    return new UserProfileResponse(
        user.getId(),
        user.getDisplayName(),
        user.getEmail()
    );
}
```

Trong ví dụ này, `passwordHash`, `mfaSecret`, `internalNote`, `roles` và quan hệ `organization` không nằm trong DTO nên không được serialize. Khi entity có thêm field, response không tự động mở rộng theo.

DTO không tự thực hiện authorization. Trước khi ánh xạ, service vẫn phải xác minh người gọi có quyền xem đúng user và từng thuộc tính. Với endpoint xem hồ sơ của người khác, cần policy riêng thay vì thay `userId` tùy ý từ path rồi trả cùng DTO.

## 4. Tạo DTO riêng cho từng use case

Không nên tạo một DTO khổng lồ có mọi field rồi dùng chung cho hồ sơ cá nhân, màn hình quản trị, danh sách tìm kiếm và báo cáo. Mỗi use case có nhu cầu dữ liệu và quyền khác nhau.

Ví dụ:

| Use case | Response DTO có thể dùng | Trường điển hình |
|---|---|---|
| Hồ sơ cá nhân | `UserProfileResponse` | ID, display name, email của chính user |
| Danh sách nhân viên | `UserListItemResponse` | ID, tên, trạng thái công việc được phép xem |
| Quản trị tài khoản | `UserAdminDetailResponse` | Trường quản trị cần thiết theo quyền admin |
| Hồ sơ công khai | `PublicUserResponse` | Tên hiển thị, ảnh, thông tin công khai |
| Báo cáo tổng hợp | `UserMetricsResponse` | Số liệu tổng hợp, không xuất field cá nhân không cần thiết |

Ví dụ DTO cho quản trị:

```java
public record UserAdminDetailResponse(
    UUID id,
    String email,
    String displayName,
    boolean enabled,
    boolean emailVerified,
    Instant createdAt
) {}
```

Ngay cả DTO quản trị cũng không nên chứa `passwordHash`, MFA secret hoặc token. Role, quyền và ghi chú nội bộ chỉ được thêm nếu use case thực sự cần, có policy field-level và audit phù hợp.

Đừng suy ra quyền chỉ từ tên DTO. `UserAdminDetailResponse` không tự bảo vệ endpoint; controller/service phải kiểm tra permission và object scope. DTO là ranh giới dữ liệu đầu ra, authorization là ranh giới quyết định ai được nhận dữ liệu đó.

## 5. Tách request DTO khỏi response DTO

Request DTO xác định các trường client được phép gửi cho một hành động. Response DTO xác định các trường server được phép trả về. Hai cấu trúc có thể khác nhau hoàn toàn.

Ví dụ request đổi tên hiển thị:

```java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName
) {}
```

```java
@PatchMapping("/api/v1/profile")
public UserProfileResponse updateProfile(
        @Valid @RequestBody UpdateProfileRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    UUID userId = UUID.fromString(jwt.getSubject());
    return userService.updateDisplayName(userId, request.displayName());
}
```

Client không thể gửi `role`, `enabled`, `tenantId`, `emailVerified` hoặc `passwordHash` qua DTO này. Nếu muốn đổi email hoặc mật khẩu, hãy tạo use case và request DTO riêng với xác minh bổ sung, thay vì mở rộng một endpoint cập nhật hồ sơ chung.

Không bind trực tiếp JSON vào JPA entity:

```java
// Không nên: client có thể gửi thêm thuộc tính mà entity cho phép bind.
@PutMapping("/api/v1/users/{id}")
public User update(@PathVariable UUID id, @RequestBody User user) {
    user.setId(id);
    return userRepository.save(user);
}
```

Ngay cả khi dùng DTO, service vẫn cần kiểm tra quyền ghi từng field và trạng thái nghiệp vụ. DTO chỉ giới hạn schema đầu vào; nó không chứng minh caller được phép sửa object.

## 6. Lọc thuộc tính theo principal và ngữ cảnh

Một object có thể được nhiều nhóm người xem với mức dữ liệu khác nhau. Ví dụ, người mua xem đơn hàng của mình, nhân viên hỗ trợ xem thông tin cần cho xử lý, còn nhân viên tài chính xem dữ liệu thanh toán theo phạm vi được cấp.

| Principal/ngữ cảnh | Có thể được xem | Cần ẩn hoặc giới hạn |
|---|---|---|
| Chủ đơn hàng | Mã đơn, mặt hàng, trạng thái, địa chỉ giao hàng của mình | Ghi chú nội bộ, thông tin nhân viên khác không liên quan |
| Nhân viên hỗ trợ | Mã đơn, trạng thái, thông tin liên hệ cần xử lý | Dữ liệu thanh toán đầy đủ, thông tin ngoài phạm vi hỗ trợ |
| Nhân viên tài chính | Tổng tiền, trạng thái thanh toán, chứng từ được cấp quyền | Dữ liệu cá nhân không phục vụ nghiệp vụ |
| Người dùng công khai | Tên hiển thị và dữ liệu công khai | Email riêng, địa chỉ, trạng thái nội bộ |

Có thể dùng DTO khác nhau hoặc mapper nhận context để quyết định field. Nếu mapper nhận context, phải bảo đảm context được tạo từ security principal đã xác minh, không lấy `role` hoặc `isAdmin` từ query/body.

Ví dụ khái niệm:

```java
public OrderResponse toResponse(Order order, Viewer viewer) {
    boolean maySeeContact = policy.canReadCustomerContact(viewer, order);

    return new OrderResponse(
        order.getId(),
        order.getStatus(),
        order.getTotal(),
        maySeeContact ? order.getCustomer().getEmail() : null
    );
}
```

Đây chỉ là minh họa cho field-level policy. Trong ứng dụng thật, hãy xác định rõ `null` có nghĩa là bị ẩn hay dữ liệu thực sự rỗng. Với một số API, nên dùng DTO riêng hoặc omit field theo schema có chủ đích để client không nhầm lẫn. Policy phải được kiểm thử theo principal, tenant và trạng thái object.

## 7. Tránh lộ dữ liệu qua object lồng nhau

DTO lồng nhau cũng cần được thiết kế theo allowlist. Ví dụ response đơn hàng:

```java
public record OrderResponse(
    UUID id,
    String status,
    BigDecimal total,
    CustomerSummaryResponse customer,
    List<OrderLineResponse> items
) {}

public record CustomerSummaryResponse(
    UUID id,
    String displayName
) {}

public record OrderLineResponse(
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}
```

Không đặt trực tiếp `Customer`, `Product`, `Payment` hoặc `Employee` entity vào DTO. Hãy tạo summary DTO chứa các field cần thiết. Nếu cần thông tin thanh toán, tạo `PaymentSummaryResponse` riêng với dữ liệu phù hợp cho principal và use case.

Khi response chứa danh sách con, kiểm tra quyền trên từng object liên quan. Ví dụ, một order có thể tham chiếu địa chỉ giao hàng đã bị xóa hoặc một sản phẩm thuộc catalog khác. Không dựa vào việc object cha đã được phép đọc để tự động trả toàn bộ graph.

## 8. Projection để chỉ truy vấn dữ liệu cần trả

DTO filtering ở tầng mapping giúp kiểm soát output, nhưng nếu repository tải cả entity graph với các secret field hoặc collection lớn thì vẫn tốn tài nguyên và tăng nguy cơ vô tình sử dụng sai. Với danh sách hoặc báo cáo, có thể dùng projection để chỉ truy vấn cột cần thiết.

Ví dụ interface projection của Spring Data:

```java
public interface UserListProjection {
    UUID getId();
    String getDisplayName();
    String getEmail();
}
```

```java
public interface UserRepository extends JpaRepository<User, UUID> {
    @Query("""
        select u.id as id,
               u.displayName as displayName,
               u.email as email
        from User u
        where u.organization.id = :organizationId
        """)
    Page<UserListProjection> findVisibleUsers(
        UUID organizationId, Pageable pageable);
}
```

Projection giúp chỉ lấy trường cần thiết và có thể giảm tải entity graph. Tuy nhiên, điều kiện `organizationId` phải được lấy từ phạm vi đã xác minh hoặc được kiểm tra bởi policy; không tin tenant ID do client tự chọn. Projection cũng không tự thay thế field-level authorization nếu các principal khác nhau có quyền khác nhau trên cùng dữ liệu.

Với dữ liệu phức tạp, có thể dùng constructor projection hoặc query trả DTO trực tiếp. Hãy giới hạn page size, sort field và số lượng bản ghi để tránh endpoint danh sách trở thành nguồn tiêu thụ tài nguyên không giới hạn.

## 9. Mapper rõ ràng và tránh ánh xạ tự động quá rộng

Mapper giúp tách domain model khỏi API contract. Với các response nhạy cảm, ánh xạ tường minh thường dễ review hơn việc tự động copy mọi field cùng tên.

Ví dụ mapper thủ công:

```java
public final class UserMapper {
    private UserMapper() {}

    public static UserProfileResponse toProfile(User user) {
        return new UserProfileResponse(
            user.getId(),
            user.getDisplayName(),
            user.getEmail()
        );
    }
}
```

Nếu dùng MapStruct hoặc thư viện tương tự, hãy khai báo rõ mapping và cấu hình phát hiện unmapped target/source phù hợp. Với DTO chứa dữ liệu nhạy cảm, không dùng chế độ tự động copy mọi thuộc tính rồi chỉ bỏ qua một vài field; khi entity thêm field, mapper cần khiến reviewer chú ý thay đổi.

Nên đặt mapper gần use case hoặc module API, không để entity tự cung cấp `toJson()` chứa toàn bộ dữ liệu. Việc tạo representation phải nằm trong lớp chịu trách nhiệm hợp đồng API và có thể nhận policy/context khi cần.

## 10. Không dựa vào `@JsonIgnore` như lớp bảo mật duy nhất

Jackson có các annotation như `@JsonIgnore`, `@JsonProperty`, `@JsonView`, `@JsonManagedReference` và `@JsonBackReference`. Chúng hữu ích cho serialization, nhưng không thay thế DTO và authorization.

Các giới hạn cần lưu ý:

- `@JsonIgnore` trên entity có thể bị thay đổi hoặc bỏ quên khi model được tái sử dụng ở endpoint khác.
- Hành vi đọc/ghi JSON có thể thay đổi theo `JsonProperty.Access`, mix-in hoặc cấu hình deserializer; không suy ra input allowlist chỉ từ một annotation output.
- `@JsonView` dễ tạo nhiều view và khó kiểm soát khi endpoint kết hợp nhiều object hoặc role.
- `@JsonManagedReference`/`@JsonBackReference` xử lý một số vòng tham chiếu, không xác định quyền đọc object liên quan.
- Mix-in hoặc custom serializer có thể làm hành vi output phụ thuộc cấu hình toàn cục, khó thấy tại controller.

Có thể dùng annotation để bổ sung hoặc phòng vệ, nhưng response contract vẫn nên được thể hiện bằng DTO riêng. Không đánh dấu `passwordHash` bằng `@JsonIgnore` rồi xem entity đã an toàn để trả ra mọi endpoint.

## 11. Kiểm soát polymorphic serialization và deserialization

Một số hệ thống dùng kiểu đa hình hoặc cấu hình Jackson polymorphic typing để serialize/deserialize nhiều subtype. Nếu client có thể điều khiển type metadata và ứng dụng cho phép khởi tạo kiểu không mong muốn, bề mặt tấn công có thể mở rộng đáng kể.

Không bật default typing rộng cho dữ liệu JSON không đáng tin cậy. Nếu cần polymorphism, dùng allowlist subtype rõ ràng, schema ổn định và DTO cụ thể. Không cho client chọn class Java tùy ý qua field như `@class`. Request DTO nên biểu diễn loại hành động bằng enum hoặc discriminator đã được kiểm tra, rồi service ánh xạ tới xử lý hợp lệ.

## 12. Không để serializer quyết định truy vấn dữ liệu

Serialize entity có thể kích hoạt lazy loading hoặc làm lộ dữ liệu qua quan hệ. Hãy xác định dữ liệu cần trả ngay trong query hoặc use case, dùng projection/fetch plan phù hợp và ánh xạ sang DTO trong phạm vi transaction có kiểm soát.

Một số nguyên tắc:

- Tránh trả collection entity không giới hạn; dùng pagination hoặc cursor.
- Tránh để serializer gọi getter có side effect hoặc getter kích hoạt truy vấn lớn.
- Tránh quan hệ hai chiều trong DTO; response graph phải có cấu trúc hữu hạn.
- Không dùng `EAGER` cho mọi quan hệ chỉ để tránh lỗi lazy loading; điều đó có thể tải quá nhiều dữ liệu.
- Theo dõi số query, kích thước response và latency của endpoint.
- Dùng projection cho danh sách/báo cáo và query chi tiết riêng cho use case cần dữ liệu sâu.

## 13. Output filtering và cache

Khi response khác nhau theo user, role, tenant hoặc quyền field-level, cache cần phân biệt đúng ngữ cảnh. Nếu cache dùng chung key cho hai principal nhưng response của người thứ nhất chứa nhiều field hơn, người thứ hai có thể nhận dữ liệu không được phép.

Hãy cân nhắc:

- Không cache response nhạy cảm dùng chung nếu chưa có key partition phù hợp.
- Dùng `Cache-Control: private` hoặc `no-store` cho dữ liệu cá nhân/nhạy cảm theo chính sách.
- Nếu cache theo tenant/user/permission context, đảm bảo key phản ánh mọi yếu tố làm thay đổi representation.
- Khi quyền bị thu hồi, có cơ chế invalidation hoặc TTL phù hợp để response cũ không tiếp tục được phục vụ.
- Kiểm tra cache ở CDN, reverse proxy, gateway và browser, không chỉ cache trong ứng dụng.

Không dùng `Vary: Authorization` như giải pháp tự động cho mọi cache. Cần hiểu hành vi cache của từng proxy/CDN và tránh lưu raw credential vào cache key hoặc log. Với response nhạy cảm, `no-store` thường đơn giản và an toàn hơn.

## 14. Lỗi và response metadata cũng có thể làm lộ thông tin

Output filtering không chỉ áp dụng cho response thành công. Error response có thể để lộ stack trace, câu SQL, tên class, đường dẫn file, dữ liệu đầu vào hoặc sự tồn tại của object.

Hãy dùng error DTO ổn định, ví dụ Problem Details, chỉ chứa mã lỗi công khai, thông báo phù hợp và request ID. Log nội bộ có thể giữ thông tin kỹ thuật cần điều tra nhưng phải được kiểm soát quyền truy cập và không ghi secret.

Các header như `ETag`, `Location`, `Link`, pagination metadata và số lượng bản ghi cũng có thể tiết lộ thông tin. Chỉ trả metadata cần thiết và không để count hoặc URL tham chiếu làm lộ object ngoài phạm vi tenant.

## 15. Ví dụ hoàn chỉnh: đọc đơn hàng theo quyền người dùng

Giả sử chủ đơn hàng được xem địa chỉ giao hàng, nhân viên hỗ trợ được xem trạng thái và tên khách hàng, còn nhân viên tài chính được xem tổng tiền và trạng thái thanh toán. Có thể tách DTO theo use case:

```java
public record CustomerOrderResponse(
    UUID id,
    String status,
    BigDecimal total,
    String shippingCity,
    List<OrderLineResponse> items
) {}

public record SupportOrderResponse(
    UUID id,
    String status,
    String customerDisplayName
) {}

public record FinanceOrderResponse(
    UUID id,
    BigDecimal total,
    String paymentStatus,
    String currency
) {}
```

Service xác minh object và role trước khi tạo representation:

```java
@Transactional(readOnly = true)
public Object getOrder(UUID orderId, Viewer viewer) {
    Order order = orderRepository.findVisibleOrder(orderId, viewer)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    if (viewer.isCustomer()) {
        return customerOrderMapper.toResponse(order);
    }

    if (viewer.hasAuthority("orders:support.read")) {
        return supportOrderMapper.toResponse(order);
    }

    if (viewer.hasAuthority("orders:finance.read")) {
        return financeOrderMapper.toResponse(order);
    }

    throw new AccessDeniedException("Not allowed to view this order");
}
```

Đây là ví dụ khái niệm; trong code thực tế nên dùng kiểu return thống nhất hoặc tách endpoint/handler theo hợp đồng API. `findVisibleOrder` phải ràng buộc tenant và quyền object trong truy vấn hoặc policy; `Viewer` phải được xây từ principal đã xác minh. Không dùng `isCustomer()` hoặc authority do client gửi.

Nếu API chỉ có một endpoint cho nhiều loại principal, OpenAPI/schema cần mô tả rõ các response variant và client phải xử lý đúng. Với API công khai ổn định, các endpoint riêng thường dễ hiểu và dễ kiểm thử hơn một response thay đổi tùy role.

## 16. Kiểm thử output filtering

Kiểm thử phải xác nhận trường được phép có mặt và trường bị cấm thực sự không xuất hiện trong JSON. Không chỉ kiểm tra status code hoặc DTO Java.

| Nhóm test | Ca kiểm thử |
|---|---|
| Sensitive fields | Response không chứa password hash, MFA secret, token, internal note hoặc secret khác |
| Role-based fields | User thường không thấy field quản trị; support không thấy dữ liệu tài chính ngoài phạm vi |
| Object scope | User A không nhận dữ liệu order/customer của B hoặc tenant khác |
| Nested object | DTO con không vô tình chứa entity hoặc collection nhạy cảm |
| Mass assignment | Request gửi thêm `role`, `ownerId`, `tenantId`, `enabled` không làm thay đổi dữ liệu |
| Serialization | Không có vòng lặp, lazy-loading ngoài ý muốn hoặc response graph quá lớn |
| Cache | Response của principal/tenant này không được phục vụ cho principal/tenant khác |
| Error output | Không có stack trace, SQL, class name hoặc dữ liệu nhạy cảm trong lỗi |
| Schema contract | Thay đổi entity không tự thêm field vào API response |
| Pagination | Count, sort và page chỉ phản ánh object caller được phép xem |

Ví dụ kiểm tra JSON bằng Spring MockMvc:

```java
mockMvc.perform(get("/api/v1/profile")
        .with(jwt().jwt(jwt -> jwt.subject(userId.toString()))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.displayName").exists())
    .andExpect(jsonPath("$.email").exists())
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.mfaSecret").doesNotExist())
    .andExpect(jsonPath("$.internalNote").doesNotExist());
```

Test cần tạo entity có giá trị sentinel ở các field nhạy cảm để phát hiện trường hợp serializer vô tình đưa chúng ra. Nên có test cho từng role, tenant và use case, đồng thời kiểm tra response body thực tế sau khi qua Jackson, filter, advice và gateway nếu có.

## 17. Quy trình review khi thêm field hoặc endpoint

Mỗi khi thêm field vào entity, thêm quan hệ ORM hoặc tạo endpoint mới, hãy rà soát:

1. Field có thuộc API contract không? Nếu có, use case nào cần nó?
2. Principal nào được đọc field và trong phạm vi object/tenant nào?
3. Field có nhạy cảm, nội bộ hoặc có thể hỗ trợ suy luận dữ liệu khác không?
4. DTO nào cần thay đổi? Có thể dùng projection hoặc summary DTO không?
5. Mapper có đang copy field tự động quá rộng không?
6. Response cache, log, error handler và OpenAPI schema có bị ảnh hưởng không?
7. Test có xác nhận field được phép và field bị cấm cho từng role không?

Không coi việc field mới không xuất hiện trên giao diện là bằng chứng nó không thể truy cập. Client có thể gọi API trực tiếp và đọc toàn bộ response JSON.

## 18. Checklist không serialize entity trực tiếp

- [ ] Controller không trả JPA/domain entity trực tiếp cho API client.
- [ ] Mỗi use case có request DTO và response DTO phù hợp.
- [ ] DTO dùng allowlist, chỉ chứa field cần thiết và được phép công khai.
- [ ] Quyền object, tenant và field được kiểm tra trước khi mapping/trả dữ liệu.
- [ ] Không bind request body trực tiếp vào entity; tránh mass assignment.
- [ ] DTO lồng nhau không chứa entity hoặc collection không giới hạn.
- [ ] Projection/query chỉ lấy dữ liệu cần thiết cho response.
- [ ] Mapper không copy tự động quá rộng; mapping nhạy cảm được review tường minh.
- [ ] Annotation Jackson không được xem là lớp authorization duy nhất.
- [ ] Polymorphic deserialization chỉ cho phép subtype được allowlist.
- [ ] Lazy loading, N+1 query, vòng tham chiếu và kích thước response được kiểm soát.
- [ ] Cache được phân vùng theo principal/tenant hoặc tắt cache cho dữ liệu nhạy cảm.
- [ ] Error response và metadata không làm lộ thông tin nội bộ.
- [ ] Test kiểm tra JSON thực tế, nested fields, role, tenant và mass assignment.
- [ ] Thay đổi entity không tự động làm thay đổi API contract.

## Kết luận

Domain entity được thiết kế để quản lý trạng thái và quan hệ của ứng dụng; API response được thiết kế để công bố đúng dữ liệu cho một use case và principal cụ thể. Serialize entity trực tiếp làm tăng nguy cơ lộ field nhạy cảm, lộ object lồng nhau, mass assignment, phụ thuộc ORM và thay đổi API ngoài ý muốn. Hãy dùng request/response DTO hoặc projection theo allowlist, ánh xạ tường minh sau khi kiểm tra quyền object và property, đồng thời kiểm thử JSON thực tế qua serializer. Cách làm này giúp API giữ hợp đồng ổn định và chỉ trả đúng dữ liệu mà caller được phép nhận.
