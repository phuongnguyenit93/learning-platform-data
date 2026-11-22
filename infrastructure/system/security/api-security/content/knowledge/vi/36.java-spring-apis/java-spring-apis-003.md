# DTO thay vì expose entity trực tiếp

Trong ứng dụng Java/Spring, JPA entity mô tả dữ liệu được lưu trong database và thường mang theo quan hệ, trạng thái persistence, khóa nội bộ cùng các thuộc tính phục vụ nghiệp vụ. HTTP API lại cần một hợp đồng dữ liệu ổn định, chỉ công bố những trường caller được phép gửi hoặc nhìn thấy. Trả entity trực tiếp từ controller hoặc bind request body vào entity khiến hai mô hình này bị gắn chặt với nhau và có thể tạo ra lỗ hổng bảo mật.

DTO (Data Transfer Object) là kiểu dữ liệu được thiết kế cho một ranh giới trao đổi cụ thể. Request DTO định nghĩa client được gửi những gì; response DTO định nghĩa API được trả những gì. Entity vẫn được dùng trong domain/persistence layer. Service kiểm tra quyền và quy tắc nghiệp vụ, sau đó map giữa DTO và entity theo allowlist thuộc tính.

Thiết kế này giảm nguy cơ mass assignment, lộ dữ liệu nội bộ, cập nhật nhầm trường nhạy cảm, vòng lặp serialization và thay đổi API ngoài ý muốn khi schema database thay đổi. DTO không tự tạo ra authorization; mọi thao tác vẫn phải xác thực caller, kiểm tra quyền trên chức năng/object/tenant và xác minh dữ liệu đầu vào.

## 1. Entity và DTO phục vụ hai mục đích khác nhau

JPA entity thường phản ánh mô hình lưu trữ và quan hệ:

~~~java
@Entity
@Table(name = "users")
public class UserEntity {
    @Id
    private UUID id;

    private String email;
    private String displayName;
    private String passwordHash;
    private boolean enabled;
    private String role;
    private UUID tenantId;
    private Instant createdAt;
    private Instant updatedAt;

    @OneToMany(mappedBy = "user")
    private List<OrderEntity> orders;
}
~~~

Nếu trả entity này trực tiếp, API có thể vô tình đưa password hash, role, tenant ID, timestamp nội bộ hoặc quan hệ orders vào JSON. Nếu dùng entity làm request body, client có thể thử gửi những field mà endpoint không dự định cho phép thay đổi.

DTO có thể chỉ chứa phần dữ liệu phù hợp với use case:

~~~java
public record UserResponse(
    UUID id,
    String displayName
) {}

public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName
) {}
~~~

Entity mô tả dữ liệu và hành vi trong domain/persistence. DTO mô tả hợp đồng ở ranh giới API. Một entity có thể được dùng bởi nhiều endpoint nhưng mỗi endpoint có request/response DTO khác nhau.

## 2. Vì sao expose entity trực tiếp nguy hiểm?

Các rủi ro chính:

| Rủi ro | Cách xảy ra | Hậu quả |
|---|---|---|
| Mass assignment | Request bind trực tiếp vào entity có field nhạy cảm | Caller tự đổi role, owner, tenant hoặc trạng thái |
| Excessive data exposure | Serialize entity chứa field không dành cho client | Lộ password hash, internal note, PII hoặc metadata |
| Broken object property authorization | Không kiểm soát quyền đọc/sửa từng thuộc tính | User sửa trường không được phép hoặc đọc dữ liệu ngoài scope |
| Persistence coupling | Schema entity đổi làm JSON contract đổi | API compatibility bị phá vỡ ngoài ý muốn |
| Lazy loading/N+1 | Serializer truy cập quan hệ JPA | Query ngoài dự kiến, tải dữ liệu lớn, lỗi session |
| Circular reference | Entity có quan hệ hai chiều | JSON đệ quy, response lỗi hoặc quá lớn |
| Over-posting | Client gửi thêm field mà controller không dự kiến | Trạng thái nghiệp vụ bị thay đổi |
| Tenant leakage | Quan hệ entity kéo theo object của tenant khác | Lộ dữ liệu cross-tenant |

Ví dụ endpoint chỉ định cho phép đổi display name nhưng nhận UserEntity. Attacker thêm role, enabled hoặc tenantId vào JSON. Nếu binder ghi các field đó vào entity và service lưu nguyên object, caller có thể nâng quyền hoặc chuyển tài nguyên sang tenant khác.

DTO giúp giới hạn tập field có thể gửi/nhận ngay tại API contract. Service vẫn phải kiểm tra authorization và mapping; DTO không thay thế các bước đó.

## 3. Request DTO là allowlist đầu vào

Request DTO nên mô tả chính xác các field mà endpoint chấp nhận. Không dùng entity làm DTO rồi cố loại trừ từng field nhạy cảm bằng annotation.

Ví dụ cập nhật profile:

~~~java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    @Size(max = 254)
    String contactEmail
) {}
~~~

Controller:

~~~java
@PutMapping("/api/v1/me/profile")
public UserResponse updateProfile(
        @Valid @RequestBody UpdateProfileRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    UUID userId = UUID.fromString(jwt.getSubject());
    return userService.updateOwnProfile(userId, request);
}
~~~

Client không thể cập nhật passwordHash, role, enabled, tenantId hoặc createdAt thông qua DTO này vì các field đó không nằm trong contract. Nếu client gửi thêm field ngoài dự kiến, hãy chọn policy rõ ràng: từ chối unknown property hoặc bỏ qua theo compatibility contract; không bao giờ bind field không khai báo vào entity.

Với các API nhạy cảm, từ chối unknown fields giúp phát hiện over-posting và lỗi client sớm. Nếu cần hỗ trợ forward compatibility, quy định rõ field nào được phép mở rộng và không để unknown property tác động tới domain object.

## 4. Response DTO là allowlist đầu ra

Response DTO định nghĩa chính xác dữ liệu API được công bố:

~~~java
public record UserResponse(
    UUID id,
    String displayName,
    String avatarUrl
) {}
~~~

Không trả entity rồi dựa vào việc ẩn field ở frontend. Dữ liệu đã có trong response vẫn có thể được xem bằng browser developer tools, proxy hoặc client khác.

Response DTO nên:

- Chỉ có field cần thiết cho use case.
- Không chứa password hash, token, secret, internal flag hoặc dữ liệu tenant khác.
- Chỉ đưa PII vào response khi endpoint và caller có quyền xem.
- Không expose quan hệ persistence nguyên bản.
- Có kiểu dữ liệu và tên field ổn định theo API contract.
- Không tự động serialize object graph lớn.

Nếu có nhiều audience, ví dụ người dùng cuối, quản trị viên tenant và support operator, hãy tạo response DTO hoặc projection riêng cho từng use case. Không dùng một UserResponse đầy đủ cho mọi endpoint rồi hy vọng từng controller nhớ ẩn field.

## 5. Tách DTO theo use case, không tạo một DTO dùng cho mọi thao tác

Một entity User có thể được dùng ở nhiều chức năng:

| Use case | DTO phù hợp | Field điển hình |
|---|---|---|
| Xem profile | UserProfileResponse | id, displayName, avatarUrl |
| Cập nhật profile | UpdateProfileRequest | displayName, contactEmail |
| Tạo user | CreateUserRequest | email, displayName, invitation data |
| Quản trị user | AdminUserResponse | field quản trị được phép xem |
| Thay đổi trạng thái | ChangeUserStatusRequest | action hoặc target status được allowlist |
| Đặt lại mật khẩu | ResetPasswordRequest | reset token và password mới theo flow riêng |

Tránh một UserDto có hàng chục field nullable, được tái sử dụng cho create, update, admin, profile và search. DTO đa mục đích thường làm rõ ranh giới quyền khó hơn và dễ tạo ra field chỉ hợp lệ trong một số endpoint.

Tên DTO nên thể hiện use case và chiều dữ liệu, ví dụ CreateOrderRequest, UpdateOrderAddressRequest, OrderSummaryResponse hoặc OrderDetailResponse.

## 6. Chống mass assignment bằng mapping tường minh

Không làm như sau:

~~~java
@PutMapping("/api/v1/users/{id}")
public UserEntity update(
        @PathVariable UUID id,
        @RequestBody UserEntity request) {
    UserEntity entity = userRepository.findById(id).orElseThrow();
    BeanUtils.copyProperties(request, entity);
    return userRepository.save(entity);
}
~~~

Đoạn code trên bind toàn bộ field entity và copy hàng loạt thuộc tính. Nếu entity có role, enabled, tenantId hoặc ownerId, caller có thể thử thay đổi các field này.

Hãy map từng field được phép:

~~~java
@Transactional
public UserResponse updateOwnProfile(
        UUID authenticatedUserId,
        UpdateProfileRequest request) {

    UserEntity user = userRepository.findById(authenticatedUserId)
        .orElseThrow(UserNotFoundException::new);

    user.setDisplayName(request.displayName());
    user.setContactEmail(request.contactEmail());

    return userMapper.toProfileResponse(user);
}
~~~

User ID được lấy từ principal đã xác thực, không lấy từ request body. Nếu endpoint quản trị cho phép cập nhật user khác, service phải kiểm tra quyền trên user mục tiêu trước khi map.

Không dùng BeanUtils.copyProperties hoặc mapper cấu hình tự động giữa request và entity cho object nhạy cảm nếu không có allowlist rõ ràng. Với MapStruct, chỉ định mapping field cần thiết và cân nhắc cấu hình unmapped target/source để build phát hiện thay đổi model.

## 7. Không tin ID, tenant và owner do client gửi

DTO có thể chứa object ID hoặc tenant selector để client chọn tài nguyên, nhưng giá trị đó chỉ là đầu vào cần xác minh.

Ví dụ request không an toàn:

~~~json
{
  "displayName": "Alex",
  "role": "ADMIN",
  "tenantId": "tenant-b",
  "ownerId": "user-999",
  "enabled": true
}
~~~

Các field role, tenantId, ownerId và enabled thường do server/policy quản lý. Nếu nghiệp vụ cần admin đổi một trong các giá trị đó, tạo endpoint/use case riêng, kiểm tra permission cụ thể và ghi audit.

Với resource thuộc tenant, truy vấn theo cả object ID và tenant đã xác minh:

~~~java
OrderEntity order = orderRepository
    .findByIdAndTenantId(orderId, tenantContext.id())
    .orElseThrow(ResourceNotFoundException::new);
~~~

Sau đó kiểm tra object-level permission và action. Biết UUID không chứng minh caller có quyền. Không lấy tenant context từ DTO hoặc một header tự khai báo rồi dùng trực tiếp làm điều kiện repository.

## 8. Validation trên request DTO

Bean Validation giúp kiểm tra cấu trúc và giới hạn đầu vào tại ranh giới API:

~~~java
public record CreateOrderRequest(
    @NotBlank
    @Size(max = 80)
    String reference,

    @NotNull
    @Positive
    Integer quantity,

    @NotNull
    UUID productId
) {}
~~~

Kích hoạt validation bằng @Valid:

~~~java
@PostMapping("/api/v1/orders")
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(orderService.create(request));
}
~~~

Validation ở DTO nên kiểm tra kiểu, required, format, range, length và cấu trúc. Quy tắc cần database hoặc domain state như sản phẩm có bán, số lượng còn tồn, tenant membership và quyền mua phải được kiểm tra ở service/domain layer.

Giới hạn cả kích thước body, số phần tử collection, độ sâu object lồng nhau và số lỗi trả về. Annotation @Size trên một field không giới hạn tổng payload hoặc chi phí xử lý.

## 9. Validation liên trường và quy tắc nghiệp vụ

Một request có thể hợp lệ từng field nhưng không hợp lệ khi kết hợp. Ví dụ ngày bắt đầu phải trước ngày kết thúc, hoặc một loại thanh toán yêu cầu thêm thông tin.

Có thể dùng class-level constraint:

~~~java
@ValidDateRange
public record CreateReportRequest(
    @NotNull LocalDate from,
    @NotNull LocalDate to,
    @NotBlank String format
) {}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, CreateReportRequest> {

    @Override
    public boolean isValid(
            CreateReportRequest value,
            ConstraintValidatorContext context) {
        if (value == null || value.from() == null || value.to() == null) {
            return true; // @NotNull xử lý riêng.
        }
        return !value.from().isAfter(value.to());
    }
}
~~~

Đây là ví dụ rút gọn; cần khai báo annotation ValidDateRange và thông báo lỗi phù hợp. Không nhồi mọi business rule vào validator DTO. Những điều kiện phụ thuộc trạng thái hiện tại, quyền, database hoặc transaction phải được kiểm tra ở service/domain layer và có thể cần kiểm tra lại khi commit.

## 10. DTO lồng nhau và collection

DTO lồng nhau cần cascade validation:

~~~java
public record CreateShipmentRequest(
    @NotNull
    @Valid
    AddressRequest destination,

    @NotEmpty
    @Size(max = 20)
    List<@NotNull @Valid ShipmentItemRequest> items
) {}

public record AddressRequest(
    @NotBlank @Size(max = 120) String line1,
    @NotBlank @Size(max = 80) String city,
    @NotBlank @Size(max = 2) String countryCode
) {}

public record ShipmentItemRequest(
    @NotNull UUID productId,
    @NotNull @Positive Integer quantity
) {}
~~~

@Valid kích hoạt validation cho object con; constraint trên collection giới hạn số phần tử. Tuy vậy, mỗi productId vẫn phải được resolve trong tenant context và kiểm tra caller được phép đặt hàng. Không để nested DTO chứa entity object hoặc tự động cascade persistence từ request.

Với collection lớn, giới hạn page size và batch size. Cần cân nhắc duplicate ID, tổng quantity, tổng giá trị và chi phí truy vấn.

## 11. Response DTO và phân loại dữ liệu

Trước khi tạo response DTO, phân loại field:

| Nhóm field | Ví dụ | Cách xử lý |
|---|---|---|
| Public | Display name công khai, trạng thái public | Có thể trả theo contract |
| Personal | Email, phone, địa chỉ | Chỉ trả khi use case và caller được phép |
| Internal | Internal note, moderation flag, risk score | Chỉ cho role/service có quyền cụ thể |
| Secret | Password hash, API key, reset token, private key | Không trả trong API thông thường |
| Authorization metadata | Role, permission, tenant membership | Chỉ trả nếu use case cần và có policy |
| Persistence metadata | Version, internal ID, audit column | Chỉ expose khi contract có chủ đích |

Không mặc định rằng field không phải secret thì có thể trả cho mọi caller. PII và metadata authorization cũng có thể nhạy cảm.

Với response theo role, ưu tiên DTO/use case rõ ràng hoặc projection có kiểm soát. Nếu cần conditional field, policy phải được kiểm tra phía server; không gửi đầy đủ rồi dùng JavaScript ẩn field.

## 12. Mapping thủ công và MapStruct

### Mapping thủ công

Mapping thủ công rõ ràng và dễ review:

~~~java
public UserResponse toProfileResponse(UserEntity entity) {
    return new UserResponse(
        entity.getId(),
        entity.getDisplayName(),
        entity.getAvatarUrl()
    );
}
~~~

Ưu điểm là dễ thấy field nào được công bố và không tự động kéo quan hệ. Nhược điểm là có thể lặp lại khi số DTO lớn.

### MapStruct

MapStruct sinh code mapping lúc compile:

~~~java
@Mapper(componentModel = "spring")
public interface UserMapper {

    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "id", source = "id")
    @Mapping(target = "displayName", source = "displayName")
    @Mapping(target = "avatarUrl", source = "avatarUrl")
    UserResponse toProfileResponse(UserEntity entity);
}
~~~

Với request-to-entity update, chỉ map các field được phép và dùng @MappingTarget khi phù hợp:

~~~java
@Mapper(componentModel = "spring")
public interface ProfileMapper {

    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "displayName", source = "displayName")
    @Mapping(target = "contactEmail", source = "contactEmail")
    void updateProfile(
        UpdateProfileRequest request,
        @MappingTarget UserEntity entity
    );
}
~~~

Ngay cả khi dùng MapStruct, không map field quyền/tenant/owner từ request nếu endpoint không cho phép. Review generated mapping khi entity hoặc DTO thay đổi. Mapping là chuyển đổi dữ liệu, không phải authorization.

## 13. Không serialize JPA entity trực tiếp bằng Jackson

Jackson có thể truy cập getter và serialize các thuộc tính của entity. Quan hệ hai chiều như User có orders và Order có user có thể tạo vòng lặp hoặc response lớn. Lazy relation có thể kích hoạt truy vấn khi serializer đọc getter.

Các annotation như @JsonIgnore, @JsonManagedReference hoặc @JsonBackReference có thể xử lý một số vấn đề serialization, nhưng không thay thế DTO. Một field bị @JsonIgnore ở một endpoint có thể lại cần ở endpoint khác; việc ẩn field dựa vào entity annotation dễ làm contract phụ thuộc ngữ cảnh.

Không dùng @JsonView như cơ chế authorization duy nhất. JsonView có thể giúp định dạng response nhưng quyền xem field vẫn phải được kiểm tra phía server và cần test cho từng role/use case.

DTO giúp Jackson serialize một object graph nhỏ, rõ ràng, không phụ thuộc lazy relation. Hãy tránh đặt JPA entity làm field bên trong DTO vì điều đó lại kéo rủi ro serialization trở lại.

## 14. Kiểm soát lazy loading, N+1 và response size

Nếu controller trả entity, serializer có thể gọi getter trên collection/relationship. Hậu quả:

- Nhiều query phát sinh ngoài ý muốn.
- Response thay đổi theo fetch strategy.
- LazyInitializationException khi persistence context đã đóng.
- Tải toàn bộ collection dù endpoint chỉ cần vài field.
- Dữ liệu quan hệ của tenant khác bị lộ nếu query không scope đúng.

DTO projection giúp lấy đúng cột cần thiết:

~~~java
public record OrderSummaryProjection(
    UUID id,
    String reference,
    OrderStatus status,
    Instant createdAt
) {}

@Query("""
    select new com.example.api.OrderSummaryProjection(
        o.id, o.reference, o.status, o.createdAt
    )
    from OrderEntity o
    where o.tenantId = :tenantId
    order by o.createdAt desc
    """)
Page<OrderSummaryProjection> findSummaries(
    UUID tenantId, Pageable pageable);
~~~

Projection giảm lượng dữ liệu đọc và serialize. Vẫn phải kiểm tra authorization trước khi gọi query và giới hạn page size. Không lấy tenantId từ request tùy ý mà phải dùng tenant context đã xác minh.

## 15. DTO cho POST, PUT và PATCH

Các HTTP method có semantics khác nhau, nên request DTO cũng cần phản ánh mục đích:

| Method | Ý nghĩa thường dùng | DTO |
|---|---|---|
| POST | Tạo resource hoặc thực hiện command | CreateOrderRequest |
| PUT | Thay thế representation theo contract | ReplaceOrderRequest |
| PATCH | Cập nhật một phần field được cho phép | PatchOrderRequest hoặc JSON Patch policy |
| GET | Trả representation | OrderResponse |
| DELETE | Xóa/đóng resource | Thường không cần body; có thể có command riêng nếu contract yêu cầu |

Không dùng một DTO có toàn bộ field nullable cho cả POST/PUT/PATCH mà không định nghĩa rõ ý nghĩa null và absent.

Với PATCH, cần phân biệt:

- Field không xuất hiện: giữ nguyên giá trị.
- Field xuất hiện với null: xóa giá trị nếu contract cho phép.
- Field xuất hiện với giá trị: cập nhật sau validation.

Có thể dùng wrapper/presence type hoặc JSON Merge Patch theo RFC 7396 với policy rõ ràng. JSON Patch theo RFC 6902 cần allowlist path và kiểm tra quyền cho từng path/operation; không cho caller sửa bất kỳ property nào của entity.

## 16. Không dùng DTO để cho phép cập nhật trạng thái tùy ý

Một request như:

~~~json
{
  "status": "APPROVED",
  "approvedBy": "user-999",
  "approvedAt": "2026-11-18T10:00:00Z"
}
~~~

có thể là over-posting nếu client được phép sửa các field này trực tiếp. Trạng thái thường thay đổi qua command nghiệp vụ:

~~~java
public record ApproveOrderRequest(
    @Size(max = 500)
    String note
) {}

@PostMapping("/api/v1/orders/{orderId}/approve")
public OrderResponse approve(
        @PathVariable UUID orderId,
        @Valid @RequestBody ApproveOrderRequest request,
        @AuthenticationPrincipal Jwt jwt) {

    return orderService.approve(
        orderId,
        UUID.fromString(jwt.getSubject()),
        request
    );
}
~~~

Service kiểm tra quyền approve, trạng thái hiện tại, quy tắc phân tách nhiệm vụ và các điều kiện nghiệp vụ. Actor, approvedAt và status được xác định ở server. DTO command mô tả ý định của caller, không cho caller tự khai báo kết quả.

## 17. DTO không thay thế authentication và authorization

Một request DTO hợp lệ chỉ chứng minh dữ liệu có cấu trúc phù hợp. Nó không chứng minh caller có quyền thực hiện hành động.

Mỗi endpoint vẫn cần:

1. Xác thực principal bằng session/token/certificate phù hợp.
2. Kiểm tra quyền gọi chức năng.
3. Resolve tenant context từ nguồn đáng tin cậy.
4. Tải resource trong scope phù hợp.
5. Kiểm tra object-level permission và quyền trên từng property nhạy cảm.
6. Validate trạng thái và business rule.
7. Map đúng allowlist field.
8. Ghi audit cho thao tác nhạy cảm.

Ví dụ, UpdateProfileRequest chỉ chứa displayName và contactEmail, nhưng server vẫn phải xác định user nào được cập nhật. Endpoint admin update user khác cần permission khác với endpoint tự cập nhật profile.

## 18. Tách response DTO theo quyền và tránh property-level leakage

Một user có thể được xem theo nhiều ngữ cảnh. Ví dụ:

~~~java
public record PublicUserResponse(
    UUID id,
    String displayName,
    String avatarUrl
) {}

public record OwnProfileResponse(
    UUID id,
    String displayName,
    String email,
    String phone
) {}

public record AdminUserResponse(
    UUID id,
    String displayName,
    String email,
    boolean enabled,
    Instant createdAt
) {}
~~~

Controller/service chọn DTO dựa trên use case và authorization đã kiểm tra. Không trả AdminUserResponse cho mọi request rồi dựa vào client để ẩn email hoặc enabled.

Nếu quyền xem email phụ thuộc tenant role, kiểm tra policy trước khi map field. Với field nhạy cảm, có thể dùng mapper method riêng yêu cầu một authorization decision đã được xác minh, thay vì mapper tự suy luận role từ dữ liệu entity.

## 19. DTO cho file upload và dữ liệu lớn

Không phải request nào cũng nên bind vào một object JSON. File upload cần giới hạn riêng:

- Metadata DTO chỉ chứa field được phép như document type và description.
- File bytes được xử lý bằng MultipartFile/stream, có giới hạn size và content validation.
- File owner/tenant lấy từ principal/context, không tin metadata client.
- File name được chuẩn hóa; không dùng path client gửi để ghi trực tiếp lên filesystem.
- Kiểm tra quyền upload vào resource và quota.
- Response trả document ID, trạng thái scan và metadata an toàn; không trả storage credential hoặc internal path.

Với batch request, giới hạn số item và validate từng item. Không để DTO chứa một collection không giới hạn dẫn tới tiêu thụ bộ nhớ hoặc thời gian xử lý quá lớn.

## 20. DTO, OpenAPI và API versioning

Request/response DTO là phần cốt lõi của API schema. Hãy công bố contract trong OpenAPI:

- Schema riêng cho từng operation.
- Required, nullable, enum, format, min/max length và collection limit.
- Response schema không chứa entity field nội bộ.
- Ví dụ request/response dùng dữ liệu giả.
- Error response và validation error format.
- Deprecated field/version và migration guidance.

Không tự động expose JPA entity schema vào OpenAPI. Nếu entity đổi do migration database, API không nhất thiết phải đổi. Khi cần thay đổi contract, version hoặc mở rộng DTO có chủ đích và kiểm tra backward compatibility.

Tránh dùng cùng một DTO Java cho nhiều version API nếu semantics khác nhau. Có thể map nhiều version request DTO vào cùng application command/domain model, hoặc map một domain result ra các response DTO theo version.

## 21. Ví dụ luồng hoàn chỉnh trong Spring Boot

Một cấu trúc đơn giản:

~~~text
controller/
  UserController.java
dto/
  UpdateProfileRequest.java
  UserProfileResponse.java
service/
  UserService.java
mapper/
  UserMapper.java
repository/
  UserRepository.java
entity/
  UserEntity.java
~~~

Repository:

~~~java
public interface UserRepository extends JpaRepository<UserEntity, UUID> {
    Optional<UserEntity> findByIdAndTenantId(UUID id, UUID tenantId);
}
~~~

Service:

~~~java
@Service
public class UserService {
    private final UserRepository repository;
    private final UserMapper mapper;
    private final TenantContextProvider tenantContext;
    private final UserAuthorization authorization;

    public UserService(
            UserRepository repository,
            UserMapper mapper,
            TenantContextProvider tenantContext,
            UserAuthorization authorization) {
        this.repository = repository;
        this.mapper = mapper;
        this.tenantContext = tenantContext;
        this.authorization = authorization;
    }

    @Transactional
    public UserProfileResponse update(
            UUID targetUserId,
            UUID actorId,
            UpdateProfileRequest request) {

        UUID tenantId = tenantContext.requireTenantId();
        UserEntity user = repository
            .findByIdAndTenantId(targetUserId, tenantId)
            .orElseThrow(UserNotFoundException::new);

        authorization.requireCanUpdateProfile(actorId, user);
        user.setDisplayName(request.displayName());
        user.setContactEmail(request.contactEmail());

        return mapper.toProfileResponse(user);
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/v1/users")
public class UserController {
    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }

    @PutMapping("/{userId}/profile")
    public UserProfileResponse update(
            @PathVariable UUID userId,
            @Valid @RequestBody UpdateProfileRequest request,
            @AuthenticationPrincipal Jwt jwt) {

        UUID actorId = UUID.fromString(jwt.getSubject());
        return service.update(userId, actorId, request);
    }
}
~~~

Đây là ví dụ minh họa; cần thêm import, exception handler và cấu hình security phù hợp. TenantContextProvider phải lấy context từ quá trình xác thực/membership đã hoàn tất. Authorization service phải kiểm tra actor với user mục tiêu. Nếu chỉ cho phép tự cập nhật profile, có thể bỏ targetUserId khỏi route và dùng subject từ token.

## 22. Kiểm thử DTO và API contract

Test không chỉ xác nhận request hợp lệ chạy được. Cần chứng minh caller không thể gửi hoặc đọc field ngoài contract.

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Input allowlist | Gửi displayName hợp lệ | Chỉ field được phép thay đổi |
| Mass assignment | Gửi thêm role, enabled, tenantId, ownerId | Bị từ chối hoặc bỏ qua theo contract; không field nhạy cảm nào thay đổi |
| Output allowlist | GET profile | Không có passwordHash, role nội bộ, secret hoặc entity relation ngoài ý muốn |
| Unknown property | Gửi field không khai báo | Hành vi đúng với unknown-field policy |
| Validation | Null, blank, quá dài, sai format | Trả validation error ổn định |
| Nested validation | Item con sai hoặc collection quá lớn | Request bị từ chối trước xử lý nghiệp vụ |
| Object authorization | User đổi object ID sang user khác | Bị từ chối theo policy |
| Tenant isolation | Gửi tenant selector khác | Không truy cập dữ liệu tenant khác |
| Property authorization | Caller không được xem email/internal field | Response không chứa field đó |
| PATCH semantics | Field absent, null và value | Mỗi trường hợp đúng contract |
| State transition | Gửi status APPROVED trực tiếp | Không thể thay trạng thái ngoài command được phép |
| Serialization | Entity có quan hệ hai chiều/lazy | Response DTO không gây recursion hoặc query ngoài ý muốn |
| Pagination/size | Page size hoặc batch vượt giới hạn | Bị giới hạn hoặc từ chối |
| OpenAPI | Schema request/response | Không expose entity/internal field |
| Regression | Thêm field mới vào entity | API response/request không tự động thay đổi |

Ví dụ test mass assignment:

~~~java
mockMvc.perform(put("/api/v1/users/{id}/profile", userId)
        .with(jwt().jwt(jwt -> jwt.subject(actorId.toString())))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "displayName": "Alex",
              "role": "ADMIN",
              "tenantId": "00000000-0000-0000-0000-000000000099",
              "enabled": true
            }
            """))
    .andExpect(status().isBadRequest());

assertThat(userRepository.findById(userId).orElseThrow().getRole())
    .isEqualTo("CUSTOMER");
~~~

Test trên giả định Jackson được cấu hình từ chối unknown property. Nếu contract chọn bỏ qua field lạ, assertion phải chứng minh các field nhạy cảm không thay đổi. Điều quan trọng là không có mass assignment và response không lộ entity.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Controller trả JPA entity | Expose field/relationship và persistence details | Response DTO |
| Request body là entity | Client có thể over-post field | Request DTO allowlist |
| Copy toàn bộ property bằng BeanUtils | Dễ ghi field không được phép | Mapping tường minh |
| Một DTO cho mọi endpoint | Field nullable và quyền khó phân biệt | DTO theo use case |
| DTO chứa entity con | Serialization/persistence coupling quay lại | Nested DTO riêng |
| Chỉ dùng @JsonIgnore | Không giải quyết input binding và authorization | DTO riêng cho input/output |
| Chỉ dựa vào @JsonView | View không tự chứng minh quyền caller | Policy + response DTO |
| Tin tenantId trong DTO | Cross-tenant access | Resolve tenant server-side |
| DTO validation thay business validation | Trạng thái/permission có thể thay đổi | Service/domain checks |
| Trả toàn bộ object rồi ẩn ở frontend | Dữ liệu đã bị lộ qua response | Server-side response allowlist |
| PATCH map mọi field nullable | Không phân biệt absent/null và có thể overwrite | Patch contract rõ ràng |
| Serialize entity collection | N+1, recursion, response lớn | Projection/pagination |

## 24. Checklist thiết kế DTO an toàn

- [ ] Mỗi endpoint có request/response contract phù hợp use case.
- [ ] Không bind request trực tiếp vào JPA entity.
- [ ] Không trả entity hoặc entity graph trực tiếp từ controller.
- [ ] Request DTO chỉ chứa field caller được phép gửi.
- [ ] Response DTO chỉ chứa field caller được phép xem.
- [ ] Role, tenant, owner, status và audit field do server/policy quản lý.
- [ ] Mapping từ DTO sang entity là allowlist tường minh.
- [ ] Validation bao gồm type, required, format, range, length và nested collection.
- [ ] Business rule và authorization được kiểm tra ở service/domain layer.
- [ ] Object được truy vấn theo tenant scope đã xác minh.
- [ ] Quyền đọc/sửa property nhạy cảm được kiểm tra độc lập.
- [ ] PATCH phân biệt absent, null và value.
- [ ] Không dùng Jackson annotation làm cơ chế authorization duy nhất.
- [ ] Response không gây lazy loading, N+1, recursion hoặc tải dữ liệu không giới hạn.
- [ ] OpenAPI mô tả DTO, không expose schema entity.
- [ ] Test mass assignment, output leakage, object/tenant authorization và contract regression.

## Kết luận

DTO tạo ranh giới rõ giữa mô hình lưu trữ và hợp đồng HTTP. Request DTO giới hạn những gì client có thể gửi; response DTO giới hạn những gì API công bố; mapping tường minh ngăn field nhạy cảm bị ghi hoặc trả ngoài ý muốn. Hãy thiết kế DTO theo từng use case, validate đầu vào, kiểm tra authorization ở chức năng/object/property và resolve tenant từ nguồn đã xác minh. Entity vẫn thuộc domain/persistence layer; không để Jackson hoặc data binder biến cấu trúc database thành API contract. Khi DTO, service policy, mapping và contract test được thiết kế cùng nhau, Spring API dễ bảo trì hơn và giảm đáng kể nguy cơ mass assignment, excessive data exposure cùng lỗi tenant isolation.
