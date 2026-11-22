# Tách DTO nhận vào và DTO trả ra theo hợp đồng API

Trong ứng dụng Spring dùng Jackson, một endpoint thường nhận JSON từ client, chuyển JSON thành Java object, gọi service xử lý nghiệp vụ rồi trả JSON response. Một lỗi thiết kế phổ biến là dùng cùng một class cho cả request, response và entity lưu trong database. Cách này ban đầu có vẻ tiện vì giảm số class và code mapping, nhưng khiến hợp đồng API bị gắn chặt với cấu trúc nội bộ: thêm field database có thể vô tình làm lộ dữ liệu, thay đổi validation đầu vào có thể ảnh hưởng response, và client có thể gửi những property mà server không muốn cho phép cập nhật.

Giải pháp là tách các mô hình theo vai trò:

- **Request DTO** mô tả dữ liệu client được phép gửi vào một use case cụ thể.
- **Response DTO** mô tả dữ liệu server cam kết trả về cho client.
- **Domain model/entity** mô tả trạng thái và hành vi bên trong ứng dụng hoặc persistence model.

Jackson đảm nhiệm việc bind request JSON vào request DTO và serialize response DTO thành JSON. Spring điều phối vòng đời HTTP, validation và exception handling. Service/domain layer quyết định nghiệp vụ. Việc mapping giữa các mô hình làm rõ ranh giới và giúp mỗi hợp đồng thay đổi độc lập.

## 1. Vì sao không dùng một class cho mọi chiều?

Giả sử hệ thống có entity người dùng:

```java
@Entity
public class User {
    @Id
    @GeneratedValue
    private Long id;

    private String username;
    private String email;
    private String passwordHash;
    private boolean admin;
    private Instant createdAt;
    private Instant lastLoginAt;

    // Getter và setter
}
```

Nếu controller nhận trực tiếp `User`:

```java
@PostMapping("/users")
public User create(@RequestBody User user) {
    return userRepository.save(user);
}
```

client có thể gửi các field như `id`, `admin`, `passwordHash` hoặc `createdAt`. Nếu Jackson bind được các property này và code lưu object trực tiếp, ứng dụng có thể cho phép client điều khiển những giá trị chỉ server mới được quyền đặt. Đây là rủi ro mass assignment/over-posting.

Nếu serialize entity trực tiếp, Jackson có thể đưa `passwordHash`, thông tin đăng nhập hoặc field nội bộ vào response. Với JPA, entity còn có thể chứa lazy proxy, quan hệ hai chiều gây vòng tham chiếu, collection lớn hoặc dữ liệu không thuộc API contract.

Tách DTO giúp controller chỉ nhận và trả các field được định nghĩa cho use case:

```java
public record CreateUserRequest(
    String username,
    String email,
    String password
) {}

public record UserResponse(
    Long id,
    String username,
    String email,
    Instant createdAt
) {}
```

Entity vẫn giữ `passwordHash` và `admin`, nhưng chúng không xuất hiện trong request/response DTO.

## 2. Ba mô hình có ba trách nhiệm khác nhau

| Mô hình | Ai tạo/cung cấp? | Mục đích | Có nên phụ thuộc Jackson? |
|---|---|---|---|
| Request DTO | Client gửi, Jackson bind | Diễn đạt input của endpoint/use case | Có thể có annotation Jackson và validation |
| Response DTO | Application tạo, Jackson serialize | Công bố dữ liệu cho client | Có thể có annotation Jackson để kiểm soát output |
| Domain model/entity | Service/domain/repository | Biểu diễn trạng thái, invariant và persistence | Nên độc lập với chi tiết HTTP/JSON khi có thể |

Không nhất thiết mỗi use case phải có một class riêng cho mọi loại dữ liệu. Nhưng request và response chỉ nên dùng chung khi hợp đồng, validation, lifecycle và ý nghĩa của chúng thực sự giống nhau. Đừng tái sử dụng class chỉ vì tên field hiện tại trùng nhau.

Ví dụ một user có thể có các DTO khác nhau:

- `CreateUserRequest`: username, email, password.
- `UpdateUserProfileRequest`: displayName, phoneNumber.
- `ChangePasswordRequest`: currentPassword, newPassword.
- `UserResponse`: id, username, displayName, createdAt.
- `AdminUserResponse`: thêm role/status cho client quản trị có quyền.

Mỗi use case có input và output khác nhau. Điều đó thể hiện quyền và ý nghĩa nghiệp vụ ngay trong kiểu Java.

## 3. Request DTO chỉ chứa field được phép nhận

Một request DTO nên mô tả chính xác input của endpoint. Ví dụ:

```java
public record CreateUserRequest(
    @NotBlank
    @Size(min = 3, max = 40)
    String username,

    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 12, max = 128)
    String password
) {}
```

Client không có property `id`, `admin`, `passwordHash` hay `createdAt` trong hợp đồng request. Jackson chỉ bind vào các component mà DTO công bố.

Nếu dùng class truyền thống thay vì record:

```java
public class CreateUserRequest {
    @NotBlank
    @Size(min = 3, max = 40)
    private String username;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @NotBlank
    @Size(min = 12, max = 128)
    private String password;

    public CreateUserRequest() {
    }

    // Getter và setter
}
```

Jackson có thể bind record trên các version hỗ trợ record constructor và có thể bind Java bean qua constructor mặc định/setter hoặc creator. Hãy dùng cấu hình và version Jackson tương thích với baseline Java của dự án.

### 3.1. Không dùng request DTO làm entity

Request DTO thường có dữ liệu dạng raw từ client, ví dụ password plaintext hoặc mã quốc gia dạng string. Entity có thể cần `passwordHash`, enum domain, quan hệ object và metadata do server quản lý.

Mapping service chuyển từ request sang domain:

```java
public User createUser(CreateUserRequest request) {
    User user = new User();
    user.setUsername(request.username());
    user.setEmail(request.email());
    user.setPasswordHash(passwordEncoder.encode(request.password()));
    user.setAdmin(false);
    user.setCreatedAt(clock.instant());
    return userRepository.save(user);
}
```

Server tự quyết định `admin`, hash password và timestamp. Client không được điều khiển các field đó qua JSON request.

## 4. Response DTO chỉ chứa field được phép công bố

Response DTO mô tả output của API. Ví dụ:

```java
public record UserResponse(
    Long id,
    String username,
    String email,
    Instant createdAt
) {}
```

Mapping từ entity:

```java
private UserResponse toResponse(User user) {
    return new UserResponse(
        user.getId(),
        user.getUsername(),
        user.getEmail(),
        user.getCreatedAt()
    );
}
```

Response không có password hash, flag nội bộ, token reset hoặc quan hệ persistence. Dù entity có thêm field trong tương lai, JSON response không tự thay đổi nếu DTO không được cập nhật.

### 4.1. Dùng response khác nhau theo quyền hoặc use case

Một endpoint profile công khai có thể trả:

```java
public record PublicUserResponse(
    Long id,
    String username,
    String displayName
) {}
```

Một endpoint quản trị có thể trả:

```java
public record AdminUserResponse(
    Long id,
    String username,
    String email,
    boolean enabled,
    Set<String> roles,
    Instant createdAt
) {}
```

Không nên dùng một `UserResponse` rất lớn rồi tùy từng endpoint ẩn/hiện field bằng nhiều điều kiện. Các DTO chuyên biệt làm rõ contract và giúp kiểm soát dữ liệu theo quyền dễ hơn.

## 5. Jackson trong Spring request/response lifecycle

Trong Spring MVC, `@RequestBody` yêu cầu một `HttpMessageConverter` đọc body. Với JSON, converter thường dùng Jackson `ObjectMapper` để deserialize request DTO.

Response object được trả từ controller sẽ được serialize qua converter tương ứng.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping
    public ResponseEntity<UserResponse> create(
            @Valid @RequestBody CreateUserRequest request) {

        User user = userService.createUser(request);
        UserResponse response = toResponse(user);

        return ResponseEntity
            .created(URI.create("/api/users/" + response.id()))
            .body(response);
    }
}
```

Luồng xử lý:

```text
HTTP JSON request
      |
      v
Jackson HttpMessageConverter
      |
      v
CreateUserRequest
      |
      v
Bean Validation (@Valid)
      |
      v
Controller / Service
      |
      v
Domain entity + repository
      |
      v
UserResponse mapping
      |
      v
Jackson HttpMessageConverter
      |
      v
HTTP JSON response
```

Jackson chịu trách nhiệm serialization/deserialization; Spring kết nối mapper với HTTP và kích hoạt validation; service/domain chịu trách nhiệm nghiệp vụ.

### 5.1. Không để controller trả entity trực tiếp

Ngay cả khi entity hiện tại serialize thành JSON mong muốn, việc đó tạo coupling giữa persistence model và public API. Thêm lazy relation, đổi field name hoặc thêm metadata có thể thay đổi output ngoài ý muốn.

Hãy map entity thành response DTO trước khi trả. Nếu cần projection hiệu quả từ database, có thể truy vấn thẳng projection/DTO thay vì tải toàn bộ entity rồi map.

## 6. Bean Validation đặt ở request boundary

Request DTO là nơi phù hợp để kiểm tra input có hình thức hợp lệ:

```java
public record RegisterRequest(
    @NotBlank
    @Size(min = 3, max = 40)
    String username,

    @NotBlank
    @Email
    String email,

    @NotBlank
    @Size(min = 12)
    String password
) {}
```

Controller dùng `@Valid`:

```java
@PostMapping("/register")
public UserResponse register(@Valid @RequestBody RegisterRequest request) {
    return userService.register(request);
}
```

Nếu constraint không đạt, Spring MVC thường ném `MethodArgumentNotValidException` (tùy phiên bản và cách khai báo method validation). Có thể xử lý bằng `@RestControllerAdvice` để trả lỗi nhất quán.

Không nên dùng response DTO để validate request chỉ vì field trùng nhau. Response có thể chứa field read-only do server tạo, còn request có các constraint riêng như password bắt buộc hoặc xác nhận password.

### 6.1. Validation hình thức và validation nghiệp vụ

Bean Validation phù hợp với các điều kiện như:

- Không null, không blank.
- Độ dài, pattern và định dạng.
- Số dương hoặc nằm trong range.
- Nested object và collection hợp lệ.
- Quan hệ giữa nhiều field.

Các kiểm tra như username đã tồn tại, user có quyền thay đổi role, tài khoản đang hoạt động hay số dư đủ thường cần repository hoặc trạng thái runtime. Chúng nên được xử lý ở service/domain layer, không chỉ dựa vào annotation trên DTO.

## 7. Không dùng @JsonIgnore để che lỗi thiết kế DTO

Jackson có annotation như `@JsonIgnore`, `@JsonProperty(access = READ_ONLY)` hoặc `WRITE_ONLY` để điều khiển property khi serialize/deserialze. Chúng hữu ích cho các trường hợp cần thiết, nhưng không thay thế việc tách request và response model.

Ví dụ:

```java
public class UserPayload {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;
}
```

`WRITE_ONLY` có thể cho phép đọc password từ input nhưng không serialize nó ra output. Tuy nhiên, nếu cùng class còn có `admin`, `id` hoặc field khác có semantics khác nhau theo use case, một DTO duy nhất sẽ ngày càng khó quản lý.

Một request `CreateUserRequest` có password và một response `UserResponse` không có password thường rõ ràng hơn một class có nhiều annotation access mode.

### 7.1. @JsonIgnoreProperties(ignoreUnknown = true) không phải allowlist input

Annotation này bỏ qua property lạ khi deserialize. Nó không tự bảo đảm client chỉ gửi field hợp lệ. Nếu endpoint cần phát hiện payload gửi thêm field, giữ unknown-property failure hoặc dùng schema/validation phù hợp.

Đối với security-sensitive input, tránh cấu hình lenient toàn cục khiến field gõ sai hoặc field không được phép bị bỏ qua âm thầm.

## 8. Tránh mass assignment và over-posting

Mass assignment xảy ra khi dữ liệu client được bind trực tiếp vào object có nhiều field nhạy cảm hơn contract endpoint.

Ví dụ nguy hiểm:

```java
@PatchMapping("/{id}")
public User update(@PathVariable Long id, @RequestBody User user) {
    user.setId(id);
    return userRepository.save(user);
}
```

Client có thể gửi:

```json
{
  "username": "alice",
  "admin": true,
  "enabled": true,
  "passwordHash": "attacker-value"
}
```

Tùy cách bind và merge, các field nội bộ có thể bị thay đổi ngoài ý muốn.

Tách request:

```java
public record UpdateUserProfileRequest(
    @NotBlank String displayName,
    @Size(max = 30) String phoneNumber
) {}
```

Service chỉ cập nhật field được phép:

```java
public User updateProfile(Long id, UpdateUserProfileRequest request) {
    User user = userRepository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));

    user.setDisplayName(request.displayName());
    user.setPhoneNumber(request.phoneNumber());

    return userRepository.save(user);
}
```

Không dùng reflection copier hoặc mapper tự động một cách mù quáng để copy mọi property từ request sang entity. Mapping nên là allowlist: chỉ những field use case cho phép mới được gán.

## 9. Tách DTO theo use case thay vì CRUD entity chung

Một entity `Product` có thể phục vụ nhiều endpoint nhưng mỗi endpoint có input khác nhau:

```java
public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @PositiveOrZero BigDecimal price
) {}

public record UpdateProductDetailsRequest(
    @NotBlank String name,
    @Size(max = 2000) String description
) {}

public record ChangeProductPriceRequest(
    @NotNull @PositiveOrZero BigDecimal newPrice,
    @NotBlank String reason
) {}
```

Response có thể khác:

```java
public record ProductSummaryResponse(
    Long id,
    String sku,
    String name,
    BigDecimal price
) {}

public record ProductDetailsResponse(
    Long id,
    String sku,
    String name,
    String description,
    BigDecimal price,
    boolean available,
    Instant updatedAt
) {}
```

Các DTO này không trùng hoàn toàn với entity và cũng không cần trùng nhau. Chúng mô tả đúng use case và response contract.

## 10. Mapping thủ công giữa DTO và domain

Mapping thủ công thường là lựa chọn tốt khi số field ít hoặc nghiệp vụ cần kiểm soát từng phép gán:

```java
private Product toNewProduct(CreateProductRequest request) {
    Product product = new Product();
    product.setSku(request.sku());
    product.setName(request.name());
    product.setPrice(request.price());
    product.setAvailable(false);
    return product;
}

private ProductSummaryResponse toSummary(Product product) {
    return new ProductSummaryResponse(
        product.getId(),
        product.getSku(),
        product.getName(),
        product.getPrice()
    );
}
```

Ưu điểm:

- Nhìn thấy rõ field nào được phép copy.
- Dễ thêm logic chuyển đổi, default và normalization.
- Không cần framework mapping bổ sung.
- Compiler giúp phát hiện constructor argument thay đổi với record.

Nhược điểm là code mapping có thể lặp lại khi DTO lớn và nhiều endpoint.

### 10.1. Mapping không nên chứa nghiệp vụ phức tạp trong controller

Controller nên điều phối HTTP, còn mapping có thể nằm trong assembler/mapper component hoặc service tùy quy mô. Không biến controller thành nơi chứa mọi quy tắc chuyển đổi và cập nhật domain.

Ví dụ component:

```java
@Component
public class UserApiMapper {
    public UserResponse toResponse(User user) {
        return new UserResponse(
            user.getId(),
            user.getUsername(),
            user.getEmail(),
            user.getCreatedAt()
        );
    }
}
```

Mapper component chỉ chuyển representation; kiểm tra quyền và invariant vẫn thuộc service/domain.

## 11. Dùng MapStruct hoặc mapping framework khi cần

Khi có nhiều DTO và mapping lớn, MapStruct có thể sinh code mapping lúc compile:

```java
@Mapper(componentModel = "spring")
public interface UserApiMapper {
    UserResponse toResponse(User user);
}
```

MapStruct giúp giảm code lặp và phát hiện một số mapping không hoàn chỉnh ở compile time. Tuy nhiên, không nên dùng cấu hình tự động copy mọi field từ request vào entity nhạy cảm.

Với create/update request, có thể khai báo mapping tường minh:

```java
@Mapper(componentModel = "spring")
public interface UserCommandMapper {
    @Mapping(target = "id", ignore = true)
    @Mapping(target = "admin", ignore = true)
    @Mapping(target = "passwordHash", ignore = true)
    @Mapping(target = "createdAt", ignore = true)
    User toEntity(CreateUserRequest request);
}
```

Sau mapping, service vẫn phải hash password, đặt metadata server-side và kiểm tra quyền. Nếu MapStruct không thể biểu diễn một quy tắc nghiệp vụ, viết logic rõ trong service thay vì ép framework làm thay.

## 12. DTO và Jackson naming/format annotations

DTO là API boundary nên có thể dùng annotation Jackson để ổn định tên property JSON:

```java
public record CreateUserRequest(
    @JsonProperty("display_name")
    @NotBlank
    String displayName,

    @JsonProperty("email_address")
    @NotBlank
    @Email
    String email
) {}
```

JSON:

```json
{
  "display_name": "An",
  "email_address": "an@example.com"
}
```

`@JsonProperty` giúp tên wire format không phụ thuộc tên Java property. Có thể dùng naming strategy toàn mapper như snake case, nhưng cần bảo đảm mọi endpoint theo cùng contract. Nếu API có tên field đặc biệt, annotation rõ ràng có thể dễ đọc hơn.

### 12.1. @JsonAlias cho tên cũ khi deserialize

Khi API cần hỗ trợ tên cũ trong giai đoạn migration:

```java
public record SearchRequest(
    @JsonAlias("q")
    String query
) {}
```

`@JsonAlias` chấp nhận alias khi deserialize. Khi serialize, tên property chính vẫn được sử dụng theo metadata của Jackson. Đây là công cụ chuyển đổi compatibility; không nên giữ alias vô thời hạn nếu contract đã có versioning rõ.

### 12.2. @JsonProperty.Access

Jackson có thể đặt access mode:

```java
public class TokenResponse {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String tokenId;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String secret;
}
```

`READ_ONLY`/`WRITE_ONLY` có ý nghĩa theo hướng đọc/ghi của Jackson. Hãy cẩn thận vì “read” trong API annotation có thể gây nhầm với góc nhìn của server; hiểu đúng là deserialize input hay serialize output theo định nghĩa Jackson. Với request/response tách riêng, thường ít cần dựa vào access mode để phân biệt hai contract.

## 13. Date/time và kiểu dữ liệu trong DTO

Request/response nên định nghĩa format thời gian rõ ràng. Ví dụ:

```java
public record CreateEventRequest(
    @NotNull
    Instant startsAt
) {}
```

Với Jackson Java Time module, `Instant` thường được serialize/deserialize theo cấu hình của `JavaTimeModule` và các feature liên quan. API nên thống nhất ISO-8601 UTC hoặc một representation đã được công bố.

Nếu dùng `LocalDate`, `LocalDateTime`, `OffsetDateTime` hoặc `Instant`, cần phân biệt ý nghĩa:

- `LocalDate`: ngày lịch không có timezone.
- `LocalDateTime`: ngày/giờ địa phương không chứa offset.
- `OffsetDateTime`: ngày/giờ có offset.
- `Instant`: thời điểm tuyệt đối trên timeline UTC.

Không dùng `LocalDateTime` cho timestamp toàn cầu nếu không có quy tắc timezone. Request DTO nên chọn kiểu phản ánh contract, không chỉ kiểu tiện cho entity.

## 14. PATCH và sự khác nhau giữa absent, null, empty

Tách request DTO đặc biệt quan trọng với PATCH. Trong một update request, ba trạng thái có thể khác nhau:

- Field **absent**: client không yêu cầu thay đổi field.
- Field có giá trị **null**: client yêu cầu xóa/clear giá trị nếu contract cho phép.
- Field có giá trị **empty**: client đặt chuỗi rỗng hoặc collection rỗng.

DTO Java thông thường:

```java
public record UpdateProfileRequest(String displayName) {}
```

có thể không phân biệt được absent với JSON `null`: cả hai có thể tạo `displayName == null`. Nếu API cần phân biệt, cần representation có presence information.

Một cách là dùng wrapper kiểu `JsonNullable<T>` (thư viện bên ngoài) hoặc một class field wrapper tự định nghĩa. Ý tưởng:

```java
public record PatchField<T>(boolean present, T value) {}
```

Deserializer/DTO binder cần ghi nhận key có xuất hiện hay không. Khi đó:

| JSON | Trạng thái mong muốn |
|---|---|
| `{}` | `present=false` |
| `{"displayName":null}` | `present=true`, `value=null` |
| `{"displayName":""}` | `present=true`, `value=""` |
| `{"displayName":"An"}` | `present=true`, `value="An"` |

Không nên tự triển khai presence wrapper nếu project đã có chuẩn JSON Merge Patch/JSON Patch hoặc thư viện wrapper tương thích. Quan trọng là contract phải xác định rõ semantics và test từng trường hợp.

### 14.1. JSON Merge Patch và JSON Patch

JSON Merge Patch (RFC 7396) dùng object patch, trong đó null thường mang nghĩa xóa member; JSON Patch (RFC 6902) mô tả thao tác như add, remove, replace theo path. Hai chuẩn có semantics khác nhau.

Nếu endpoint dùng `application/merge-patch+json` hoặc `application/json-patch+json`, hãy dùng parser/representation phù hợp với media type và test null/absent theo chuẩn. Không giả định một DTO PATCH thông thường tự có semantics của các chuẩn này.

## 15. Collection và nested DTO

Request/response có thể chứa object lồng nhau và collection:

```java
public record AddressRequest(
    @NotBlank String street,
    @NotBlank String city,
    @NotBlank String countryCode
) {}

public record CreateCustomerRequest(
    @NotBlank String name,
    @NotNull @Valid AddressRequest address,
    @NotEmpty List<@NotBlank String> tags
) {}
```

`@Valid` kích hoạt cascade validation vào address. Container element constraints kiểm tra từng tag. Jackson bind nested JSON thành nested DTO tương ứng.

Response có thể dùng một kiểu lồng nhau khác:

```java
public record AddressResponse(
    String street,
    String city,
    String countryName
) {}

public record CustomerResponse(
    Long id,
    String name,
    AddressResponse address,
    List<String> tags
) {}
```

Request có `countryCode`, response có thể trả `countryName`. Không cần dùng chung `AddressDto` nếu chiều vào và ra có ý nghĩa khác nhau.

## 16. Response projection và hiệu năng truy vấn

Tách response DTO không bắt buộc phải tải toàn bộ entity. Với danh sách lớn hoặc query read-heavy, có thể dùng projection:

```java
public interface UserSummaryProjection {
    Long getId();
    String getUsername();
    String getEmail();
}
```

Repository có thể trả projection, rồi mapping thành response DTO. Hoặc JPQL constructor projection:

```java
@Query("""
    select new com.example.api.UserResponse(
        u.id, u.username, u.email, u.createdAt
    )
    from User u
    where u.id = :id
    """)
Optional<UserResponse> findResponseById(Long id);
```

Ví dụ query phụ thuộc constructor/type của response DTO và persistence provider. Giữ DTO ở package API/application phù hợp; tránh để persistence layer phụ thuộc public web contract nếu kiến trúc yêu cầu tách lớp chặt.

Projection giúp chỉ đọc field cần thiết, tránh lazy loading và giảm allocation. Tuy nhiên, tối ưu query cần dựa trên đo đạc; DTO separation trước hết là quyết định về contract và an toàn dữ liệu.

## 17. Không serialize JPA entity trực tiếp

Serialize entity có thể gây ra một số vấn đề:

- **LazyInitializationException:** Jackson truy cập lazy relation sau khi persistence context đã đóng.
- **N+1 queries:** serialize collection relation có thể kích hoạt nhiều query.
- **Infinite recursion:** quan hệ hai chiều `User -> Orders -> User` tạo vòng tham chiếu.
- **Data exposure:** field nội bộ hoặc relation nhạy cảm bị xuất ra JSON.
- **Contract instability:** đổi entity mapping làm thay đổi API response.

Có thể thấy `@JsonManagedReference`, `@JsonBackReference`, `@JsonIdentityInfo` hoặc `@JsonIgnore` được dùng để xử lý một số vấn đề khi serialize entity. Nhưng các annotation đó không giải quyết coupling và field exposure tổng thể.

Tạo response DTO trong transaction/service hoặc dùng projection là cách kiểm soát output tốt hơn. Chỉ lấy dữ liệu cần thiết và không để Jackson đi duyệt toàn bộ object graph persistence.

## 18. Tổ chức package cho request/response DTO

Một cách tổ chức đơn giản:

```text
com.example.users
  api
    UserController.java
    request
      CreateUserRequest.java
      UpdateUserProfileRequest.java
      ChangePasswordRequest.java
    response
      UserResponse.java
      AdminUserResponse.java
      UserSummaryResponse.java
    mapper
      UserApiMapper.java
  application
    UserService.java
    command
      CreateUserCommand.java
  domain
    User.java
    UserRepository.java
```

Với ứng dụng nhỏ, có thể không cần nhiều package con. Điều quan trọng là người đọc nhận ra class nào thuộc HTTP contract, class nào thuộc domain/persistence.

Nếu domain layer không nên phụ thuộc API module, request DTO có thể được chuyển thành application command:

```java
public record CreateUserCommand(
    String username,
    String email,
    String rawPassword
) {}
```

Controller chuyển request DTO thành command; application service xử lý command và trả domain result; API mapper tạo response DTO. Đây là một bước tách lớp sâu hơn, hữu ích khi use case phức tạp hoặc có nhiều transport (HTTP, message, CLI).

## 19. Versioning và evolution của API DTO

Request/response DTO là public contract nên thay đổi cần được xem xét tương thích.

### 19.1. Thêm field response

Thêm field optional vào response thường tương thích với client bỏ qua unknown properties, nhưng không phải client nào cũng làm vậy. Một số client/generated model có thể strict. Kiểm tra consumer thực tế trước khi phát hành.

### 19.2. Thêm field request

Thêm request field bắt buộc có thể phá client cũ. Field mới thường nên optional/default trong giai đoạn chuyển tiếp hoặc được version hóa.

### 19.3. Đổi tên field

Có thể chấp nhận alias cũ bằng `@JsonAlias` trong giai đoạn migration, nhưng response cần một tên canonical. Không serialize đồng thời cả tên cũ và mới trừ khi contract yêu cầu rõ.

### 19.4. Xóa hoặc đổi semantics

Xóa field, đổi unit, thay enum token hoặc đổi null semantics có thể phá client dù JSON vẫn parse được. Versioning cần xét semantics, không chỉ tên property.

### 19.5. Version endpoint hoặc media type

Tùy hệ thống, có thể version qua URL (`/v1/users`), header, media type hoặc schema registry. Chọn một chính sách nhất quán, có thời gian deprecation và contract test cho consumer cũ.

## 20. Chuẩn hóa lỗi request và response lỗi riêng

Request DTO validation có thể thất bại trước khi service chạy. Response lỗi nên có contract riêng, ví dụ:

```java
public record ApiErrorResponse(
    String code,
    String message,
    List<FieldErrorResponse> errors
) {}

public record FieldErrorResponse(
    String field,
    String code,
    String message
) {}
```

Exception handler:

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleValidation(
            MethodArgumentNotValidException exception) {

        List<FieldErrorResponse> errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldErrorResponse(
                error.getField(),
                error.getCode(),
                error.getDefaultMessage()
            ))
            .toList();

        return ResponseEntity.badRequest().body(
            new ApiErrorResponse(
                "VALIDATION_FAILED",
                "Request validation failed",
                errors
            )
        );
    }
}
```

Đây là ví dụ cho Spring MVC; exception có thể khác khi dùng method validation, Spring version khác hoặc custom converter. Không trả rejected value nhạy cảm như password/token trong lỗi. Nên có error code ổn định để client xử lý và message có thể localize.

## 21. Kiểm thử request/response contract

Tách DTO giúp test contract rõ ràng. Nên có các lớp test:

### 21.1. Jackson serialization/deserialization test

Kiểm tra JSON field names và format:

```java
class UserApiJsonTest {
    private final ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();

    @Test
    void bindsCreateRequest() throws Exception {
        String json = """
            {
              "username": "alice",
              "email": "alice@example.com",
              "password": "a-strong-password"
            }
            """;

        CreateUserRequest request = mapper.readValue(
            json,
            CreateUserRequest.class
        );

        assertEquals("alice", request.username());
        assertEquals("alice@example.com", request.email());
    }

    @Test
    void responseDoesNotExposeInternalFields() throws Exception {
        UserResponse response = new UserResponse(
            10L,
            "alice",
            "alice@example.com",
            Instant.parse("2026-01-01T00:00:00Z")
        );

        String json = mapper.writeValueAsString(response);

        assertTrue(json.contains("\"username\""));
        assertFalse(json.contains("passwordHash"));
        assertFalse(json.contains("admin"));
    }
}
```

Test response DTO trực tiếp để xác nhận contract output. Với security-sensitive field, có thể test cả controller response để bảo đảm entity không bị trả nhầm.

### 21.2. Bean Validation test

```java
class CreateUserRequestValidationTest {
    private final Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();

    @Test
    void rejectsBlankUsername() {
        CreateUserRequest request = new CreateUserRequest(
            " ",
            "alice@example.com",
            "a-strong-password"
        );

        Set<ConstraintViolation<CreateUserRequest>> violations =
            validator.validate(request);

        assertTrue(violations.stream()
            .anyMatch(v -> v.getPropertyPath().toString().equals("username")));
    }
}
```

Trong test thực tế, đóng `ValidatorFactory` khi phù hợp với lifecycle test hoặc dùng validator được Spring inject. Không tạo factory mới cho từng request production.

### 21.3. Spring MVC integration test

`MockMvc` có thể kiểm tra JSON request được bind, validation được gọi và response đúng contract:

```java
@WebMvcTest(UserController.class)
class UserControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    UserService userService;

    @Test
    void rejectsInvalidRequest() throws Exception {
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": " ",
                      "email": "bad-email",
                      "password": "short"
                    }
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

Tùy Spring Boot version, `@MockBean` có thể được thay thế bằng API mock bean mới hơn. Ví dụ chỉ minh họa cách test endpoint; hãy dùng annotation tương ứng baseline dự án.

### 21.4. Test field không được phép

Nếu contract yêu cầu reject unknown property, test request chứa field `admin` hoặc `passwordHash` và xác nhận server từ chối. Nếu mapper được cấu hình ignore unknown, hãy bảo đảm DTO không bind các field nhạy cảm và service không copy chúng từ một Map tùy ý.

## 22. Những lỗi thường gặp

**Dùng entity JPA làm request body.** Client có thể điều khiển field nội bộ, quan hệ hoặc trạng thái mà use case không cho phép. Tạo request DTO theo use case.

**Trả entity trực tiếp từ controller.** Có nguy cơ lộ field, lazy loading, N+1 query và vòng tham chiếu. Map sang response DTO.

**Dùng một DTO cho create, update và response.** Các chiều có required/default/read-only field khác nhau. Tách model theo contract.

**Chỉ dựa vào `@JsonIgnore` để bảo vệ field.** Annotation có thể bị thay đổi hoặc cấu hình khác làm thay đổi behavior; DTO riêng tạo allowlist rõ ràng hơn.

**Copy tất cả property request sang entity bằng reflection mapper.** Đây là đường mass assignment. Mapping input nên là allowlist và phải có kiểm soát quyền.

**Đặt validation chỉ ở service sau khi đã ghi dữ liệu.** Request DTO nên được validate ở boundary trước khi use case chạy; invariant domain vẫn cần được bảo vệ trong domain/service.

**Để response DTO chứa object entity lồng nhau.** Việc đó lại kéo persistence model vào API. Tạo nested response DTO/projection.

**Không phân biệt absent với null trong PATCH.** DTO thông thường có thể làm mất presence. Chọn JSON Patch/Merge Patch hoặc wrapper có presence information.

**Đổi tên property mà không version/migrate client.** Dùng alias tạm thời, contract tests và kế hoạch deprecation.

**Dùng một response khổng lồ cho mọi quyền.** Tách response theo audience/use case để tránh field nhạy cảm xuất hiện ngoài ý muốn.

**Chỉ test mapper, không test HTTP endpoint.** Spring converter, validation và exception handler là một phần của API contract. Có integration test cho controller.

## 23. Quy trình thiết kế DTO cho một endpoint

1. Xác định use case và dữ liệu client được phép gửi.
2. Tạo request DTO chỉ chứa các field input cần thiết.
3. Đặt Bean Validation constraint cho null, blank, length, format và range.
4. Xác định semantics của absent, null, empty và default; đặc biệt với PATCH.
5. Để Jackson bind JSON vào request DTO qua Spring `@RequestBody`.
6. Dùng `@Valid` để kiểm tra request trước khi gọi service.
7. Chuyển request DTO thành command/domain input bằng mapping allowlist.
8. Để service/domain kiểm tra quyền, invariant và trạng thái runtime.
9. Tạo response DTO chỉ chứa field được phép công bố.
10. Serialize response DTO qua Jackson; tránh trả entity trực tiếp.
11. Version hóa tên field, enum, date/time và null semantics như một API contract.
12. Test Jackson binding, response JSON, validation, unknown fields và controller HTTP behavior.

## Kết luận

Tách DTO nhận vào và DTO trả ra giúp API contract độc lập với domain entity và persistence model. Request DTO là allowlist dữ liệu client được phép gửi, nơi đặt validation cho input; service chuyển request thành command/domain state và tự quyết định các field do server quản lý. Response DTO chỉ công bố dữ liệu mà endpoint cam kết trả về, tránh lộ password hash, flag nội bộ, lazy relation hoặc chi tiết database. Jackson bind request và serialize response qua Spring message converter; mapping thủ công hoặc MapStruct nối DTO với domain. Với PATCH, cần giữ presence information nếu absent, null và empty có ý nghĩa khác nhau. Kiểm thử cả mapper lẫn controller để bảo đảm JSON thực tế đúng contract, an toàn và có thể tiến hóa độc lập.
