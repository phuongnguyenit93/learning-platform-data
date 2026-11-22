# Bảo vệ trường nhạy cảm qua JSON, projection và liên kết quan hệ trong Spring Data REST

## Mục tiêu

Spring Data REST có thể tự động xuất entity thành JSON/HAL resources. Điều này giúp tạo API nhanh, nhưng cũng khiến những thuộc tính trong domain model có khả năng trở thành một phần của hợp đồng HTTP nếu không được kiểm soát.

Bảo vệ dữ liệu cần được thực hiện ở nhiều lớp:

1. **Serialization:** quyết định field nào được phép xuất hiện trong JSON.
2. **Deserialization:** quyết định client được phép gửi và thay đổi field nào.
3. **Projection và excerpt:** kiểm soát các representation tùy chọn mà client có thể yêu cầu.
4. **Association links:** kiểm soát dữ liệu và thao tác qua URI quan hệ.
5. **Authorization:** quyết định ai được đọc, tạo, cập nhật hoặc xóa từng resource.

Không nên xem `@JsonIgnore`, projection hoặc việc ẩn một link là cơ chế phân quyền hoàn chỉnh. Một field có thể bị ẩn trong representation mặc định nhưng xuất hiện trở lại qua projection; một endpoint không có link trong HAL vẫn có thể được gọi trực tiếp nếu route còn được export và không có authorization phù hợp.

## 1. Nhận diện dữ liệu nhạy cảm trong domain model

Ví dụ entity User thường chứa dữ liệu cần bảo vệ:

~~~java
@Entity
public class User {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    private String displayName;

    @JsonIgnore
    private String passwordHash;

    @JsonIgnore
    private String resetToken;

    @JsonIgnore
    private String internalNote;

    @ElementCollection
    private Set<String> roles = new HashSet<>();

    // getters and setters
}
~~~

Các field cần được xem xét trước khi export:

- Password, password hash, API key, access token, refresh token và reset token.
- Secret dùng để tích hợp hệ thống, private key hoặc thông tin xác thực.
- Ghi chú nội bộ, cờ kiểm soát rủi ro, dữ liệu vận hành và audit metadata.
- Thông tin cá nhân như số điện thoại, email riêng, địa chỉ hoặc ngày sinh nếu API không cần công khai.
- Tenant ID, owner ID, role và permission nếu client không được phép tự thay đổi.
- Các field kỹ thuật như trạng thái moderation, trạng thái thanh toán hoặc cờ nội bộ.

Hãy lập allowlist các field cần xuất cho từng use case. Đừng mặc định rằng mọi field trong entity đều an toàn chỉ vì chúng không được hiển thị trên giao diện hiện tại.

## 2. Dùng @JsonIgnore để loại field khỏi JSON mặc định

Jackson `@JsonIgnore` ngăn thuộc tính được serialize trong representation thông thường:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

Spring Data REST tôn trọng `@JsonIgnore` trên field hoặc getter tương ứng khi tạo representation mặc định. Ví dụ response không có passwordHash:

~~~json
{
  "id": 12,
  "username": "lan",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/users/12"
    }
  }
}
~~~

Có thể dùng `@JsonIgnoreProperties` khi muốn bỏ qua nhiều thuộc tính ở cấp class:

~~~java
@JsonIgnoreProperties({
    "passwordHash",
    "resetToken",
    "internalNote"
})
@Entity
public class User {
    // ...
}
~~~

Tuy nhiên, `@JsonIgnore` chỉ là quy tắc mapping JSON. Nó không:

- Xác thực người gọi.
- Kiểm tra người dùng có quyền đọc entity hay không.
- Bảo vệ một custom controller dùng DTO hoặc ObjectMapper khác.
- Ngăn projection chủ động khai báo getter cho thuộc tính bị ẩn.
- Tự ngăn mass assignment hoặc thay đổi field thông qua mọi đường ghi.

Vì vậy, dùng annotation để giảm dữ liệu trong serialization mặc định, sau đó kiểm soát projection, input binding và authorization riêng.

## 3. Projection có thể làm lộ field đã bị @JsonIgnore

Đây là một rủi ro đặc biệt của Spring Data REST. Projection cho phép định nghĩa một representation bằng interface getter. Một projection có thể khai báo getter cho field mà entity đã đánh dấu `@JsonIgnore`.

Ví dụ entity:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

Projection không an toàn:

~~~java
@Projection(name = "userSecrets", types = User.class)
public interface UserSecretsProjection {

    String getUsername();

    String getPasswordHash();
}
~~~

Nếu projection được đăng ký và client gọi:

~~~http
GET /api/users/12?projection=userSecrets
Accept: application/hal+json
~~~

thì getter trong projection có thể đưa passwordHash trở lại response, bỏ qua ý định ẩn field bằng `@JsonIgnore`.

Spring Data REST không thể tự phân loại dữ liệu nào nhạy cảm theo nghiệp vụ. Trách nhiệm rà soát getter và nested projection thuộc về nhóm phát triển.

**Quy tắc:** không khai báo getter cho secret trong bất kỳ projection công khai nào, kể cả projection chỉ được dự định dùng nội bộ. Nếu một projection có thể được client chọn qua HTTP hoặc xuất hiện trong metadata ALPS, hãy xem nó là một phần của API công khai.

Projection an toàn nên chỉ khai báo field được phép đọc:

~~~java
@Projection(name = "userSummary", types = User.class)
public interface UserSummary {

    String getUsername();

    String getDisplayName();
}
~~~

Đặt interface projection trong cùng package hoặc sub-package của domain type để Spring Data REST phát hiện, hoặc đăng ký thủ công. Chỉ đăng ký những projection đã được kiểm tra.

## 4. Kiểm soát excerptProjection

Excerpt là projection được áp dụng tự động khi Spring Data REST nhúng item resources vào collection hoặc related resources.

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "users",
    excerptProjection = UserSummary.class
)
public interface UserRepository
        extends JpaRepository<User, Long> {
}
~~~

Khi gọi collection, mỗi User được nhúng theo projection UserSummary. Điều này giúp giới hạn payload mặc định của danh sách.

Nhưng excerpt không phải authorization:

- Nó không quyết định user nào được đọc collection.
- Nó không ngăn client đọc item resource trực tiếp.
- Nó không ngăn client yêu cầu một projection khác đã được export.
- Nó không bảo vệ association endpoint.
- Nó không bảo đảm field nhạy cảm không xuất hiện trong custom controller.

Excerpt cũng không tự động áp dụng cho item resource đơn. Client có thể yêu cầu projection cụ thể qua query parameter nếu projection đó được công bố.

Trước khi cấu hình excerpt, hãy rà soát cả projection được áp dụng tự động lẫn projection client có thể yêu cầu tường minh.

## 5. Nested projection và dữ liệu quan hệ

Projection có thể đưa object quan hệ vào response. Ví dụ User có Profile:

~~~java
@Projection(name = "userProfile", types = User.class)
public interface UserProfileView {

    String getUsername();

    ProfileSummary getProfile();
}

@Projection(name = "profileSummary", types = Profile.class)
public interface ProfileSummary {

    String getDisplayName();

    String getPublicBio();
}
~~~

Nested projection giúp chỉ đưa những field cần thiết của Profile vào response. Tuy nhiên, nếu Profile chứa địa chỉ riêng, ngày sinh, thông tin thanh toán hoặc dữ liệu nội bộ, đừng thêm getter cho các field đó chỉ vì tiện cho client.

Với excerpt có nested association, dữ liệu quan hệ có thể được nhúng trực tiếp trong collection response. Một field nhạy cảm có thể xuất hiện qua nhiều đường:

- Item resource của User.
- Projection User.
- Excerpt User.
- Nested projection Profile.
- Association resource của Profile.
- Repository Profile được export độc lập.

Cần kiểm tra tất cả các đường biểu diễn có thể truy cập, không chỉ một response mẫu.

## 6. JSON annotation cho quyền đọc và ghi

Jackson hỗ trợ `@JsonProperty(access = ...)` để điều khiển hướng serialization/deserialization của property.

~~~java
public class AccountRequest {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String accountNumber;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String newPassword;
}
~~~

Hai mode chính:

| Access mode | Response JSON | Request JSON |
| --- | --- | --- |
| READ_ONLY | Có thể serialize | Bỏ qua khi deserialize |
| WRITE_ONLY | Không serialize | Có thể deserialize |
| READ_WRITE | Serialize và deserialize | Serialize và deserialize |
| AUTO | Theo visibility mặc định | Theo visibility mặc định |

Ví dụ, client có thể gửi newPassword trong request nhưng server không trả lại field này trong response. Tuy nhiên, password nên được xử lý trong một command DTO và được hash bằng PasswordEncoder; không lưu password thô trực tiếp vào entity hoặc log.

Với Spring Data REST, cần kiểm thử annotation trên đúng ObjectMapper/exporter của ứng dụng. Projection và custom serializer có thể làm thay đổi representation. Đừng dùng access mode như một cơ chế phân quyền theo user.

Đối với field như role, ownerId, tenantId, balance hoặc trạng thái thanh toán, việc chỉ đánh dấu READ_ONLY vẫn chưa đủ nếu một endpoint khác có thể ghi field đó. Nên dùng DTO/command allowlist và service kiểm tra nghiệp vụ.

## 7. DTO và command model để kiểm soát input

Entity JPA thường chứa nhiều field hơn một client được phép thay đổi. Nếu Spring Data REST bind trực tiếp request JSON vào entity, việc expose một repository có thể làm lộ nhiều thuộc tính writable hơn dự kiến.

Ví dụ, client không nên tự gửi:

~~~json
{
  "username": "lan",
  "roles": ["ROLE_ADMIN"],
  "tenantId": 999,
  "enabled": true
}
~~~

nếu nghiệp vụ chỉ cho phép người dùng cập nhật displayName.

Với thao tác nhạy cảm, tạo DTO chỉ chứa field được phép:

~~~java
public record UpdateProfileRequest(
        @NotBlank String displayName,
        @Size(max = 300) String publicBio
) {}
~~~

Service xử lý allowlist:

~~~java
@Service
public class ProfileService {

    private final UserRepository users;

    public ProfileService(UserRepository users) {
        this.users = users;
    }

    @Transactional
    public void updateProfile(
            Long userId,
            UpdateProfileRequest request) {

        User user = users.findById(userId).orElseThrow();

        user.setDisplayName(request.displayName());
        user.setPublicBio(request.publicBio());
    }
}
~~~

Không copy toàn bộ request map vào entity bằng reflection hoặc BeanUtils khi request có thể chứa field mà client không được phép thay đổi. Hãy gán từng field theo allowlist.

Spring Data REST có thể tiếp tục dùng cho các repository/resource đơn giản. Với thao tác nhạy cảm cần DTO, authorization theo owner/tenant hoặc workflow nhiều bước, custom controller/service thường cho phép kiểm soát contract rõ hơn.

## 8. Bảo vệ repository bằng Spring Security method security

Ẩn field trong JSON không thay thế authorization. Một người dùng không có quyền vẫn có thể gọi trực tiếp endpoint nếu repository resource không được bảo vệ.

Spring Data REST hỗ trợ Spring Security method-level security. Bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Spring Boot Starter Security không tự bật method-level authorization. Cần bật `@EnableMethodSecurity` nếu sử dụng `@PreAuthorize` hoặc `@PostAuthorize`.

Ví dụ bảo vệ repository:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('orders:read')")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @PreAuthorize("hasAuthority('orders:read')")
    @Override
    Optional<Order> findById(Long id);

    @PreAuthorize("hasAuthority('orders:write')")
    @Override
    <S extends Order> S save(S entity);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteById(Long id);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void delete(Order entity);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteAll(Iterable<? extends Order> entities);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteAll();
}
~~~

Các authority ở ví dụ là tên quyền ứng dụng tự định nghĩa. Có thể dùng role như `hasRole('ADMIN')` nếu hệ thống tổ chức quyền theo role.

Spring Data REST lưu ý rằng annotation trên repository và annotation trên method **không tự kết hợp**. Method-level annotation ghi đè annotation ở cấp repository. Nếu cần một method vừa yêu cầu quyền đọc chung vừa yêu cầu quyền đặc biệt, hãy viết điều kiện kết hợp trong cùng biểu thức, ví dụ:

~~~java
@PreAuthorize(
    "hasAuthority('orders:read') and hasAuthority('orders:delete')"
)
@Override
void deleteById(Long id);
~~~

`CrudRepository` có nhiều biến thể delete. Nếu chỉ bảo vệ `deleteById` nhưng bỏ sót `delete(entity)`, `deleteAll(iterable)` hoặc `deleteAll()`, client có thể đi qua method còn lại. Hãy rà soát tất cả method HTTP mà repository export.

Cũng cần bảo vệ các query method tìm kiếm và method đọc dữ liệu nhạy cảm. Không chỉ kiểm soát POST/PUT/PATCH/DELETE.

## 9. Phân quyền theo từng đối tượng và tenant

Role-based access chỉ là bước đầu. Nhiều ứng dụng cần kiểm tra người dùng có quyền trên chính entity đó hay không.

Ví dụ service chỉ cho owner hoặc nhân viên có quyền hỗ trợ đọc Order:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "@orderAccess.canRead(#orderId, authentication)"
    )
    @Transactional(readOnly = true)
    public OrderView getOrder(Long orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        return new OrderView(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus());
    }
}
~~~

Bean policy:

~~~java
@Component("orderAccess")
public class OrderAccess {

    public boolean canRead(
            Long orderId,
            Authentication authentication) {
        // Kiểm tra owner, tenant, quyền hỗ trợ và trạng thái.
        return true; // Thay bằng policy thực tế.
    }
}
~~~

Giá trị `true` trong ví dụ chỉ là chỗ đặt logic minh họa; production phải thực hiện truy vấn và kiểm tra quyền thật. Không dùng username hoặc tenantId do client gửi làm bằng chứng quyền. Lấy danh tính từ Authentication và xác minh quan hệ sở hữu ở server.

Nếu dùng Spring Data REST exporter mặc định, hãy bảo vệ các repository method mà exporter gọi. Với policy theo từng object phức tạp, custom service/controller có thể dễ kiểm soát hơn vì method nhận rõ ID, principal và trả DTO.

Không dựa vào việc client không nhìn thấy link hoặc không biết ID. ID có thể bị đoán, lộ từ log, export, URL hoặc một resource khác. Mỗi request phải được authorization độc lập.

## 10. Liên kết quan hệ không phải cơ chế bảo vệ dữ liệu

Spring Data REST biểu diễn association bằng HAL link, ví dụ:

~~~json
{
  "username": "lan",
  "_links": {
    "self": {
      "href": "https://api.example.com/users/12"
    },
    "profile": {
      "href": "https://api.example.com/users/12/profile"
    }
  }
}
~~~

Link chỉ giúp client khám phá URI. Nó không chứng minh người gọi được phép đọc hoặc thay đổi resource đích.

Nếu profile chứa dữ liệu riêng tư:

- Bảo vệ endpoint item Profile.
- Bảo vệ association resource từ User sang Profile.
- Bảo vệ repository Profile nếu repository được export độc lập.
- Kiểm tra authorization cho GET, PUT, POST và DELETE association theo nghiệp vụ.
- Không đưa dữ liệu riêng tư vào excerpt/nested projection chỉ để giảm số request.

Một association link bị ẩn trong response không tự động chặn việc client gọi URI đã biết. Ngược lại, một link được hiển thị cũng không có nghĩa mọi user đều được quyền truy cập.

## 11. Ẩn repository, method hoặc association khỏi REST API

Có thể không export một repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Có thể không export một query method:

~~~java
@RestResource(exported = false)
Optional<User> findByPasswordResetToken(String token);
~~~

Có thể không export một association:

~~~java
@ManyToOne
@RestResource(exported = false)
private InternalProfile internalProfile;
~~~

Các cấu hình này hữu ích để giảm bề mặt API:

- `@RepositoryRestResource(exported = false)`: repository không được xuất thành REST resources.
- `@RestResource(exported = false)` trên method: method không được xuất.
- `@RestResource(exported = false)` trên association: association sub-resource/link không được xuất.

Nhưng việc không export không phải authorization. Service hoặc controller khác vẫn có thể truy cập dữ liệu; nếu route khác tồn tại, route đó cần security riêng. Nếu repository vẫn được dùng nội bộ, annotation này không thay thế kiểm soát quyền ở service layer.

## 12. Bảo vệ các thao tác ghi và chống mass assignment

Một response không lộ field nhạy cảm vẫn có thể nhận request thay đổi field đó. Ví dụ, nếu client gửi:

~~~http
PATCH /api/users/12
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "roles": ["ROLE_ADMIN"],
  "enabled": true
}
~~~

thì việc field không xuất hiện trong GET không tự đảm bảo Spring Data REST không bind request vào entity. Cần kiểm soát cả input.

Các biện pháp:

1. Không export repository trực tiếp nếu entity có nhiều field nhạy cảm và writable.
2. Dùng DTO/command endpoint với allowlist field được cập nhật.
3. Dùng `@JsonProperty(access = READ_ONLY)` hoặc cấu hình Jackson phù hợp cho thuộc tính không được client ghi, rồi kiểm thử.
4. Đặt authorization trên repository/service methods.
5. Kiểm tra owner, tenant, role và trạng thái nghiệp vụ ở server.
6. Không cho client tự thay đổi `@Version`, ID, audit fields hoặc quyền quản trị nếu nghiệp vụ không cho phép.
7. Dùng validation và database constraints như lớp bảo vệ bổ sung.

Đối với password, tạo endpoint đổi password riêng: xác minh password hiện tại hoặc token hợp lệ, kiểm tra policy, encode bằng `PasswordEncoder`, lưu hash và không bao giờ trả hash về client.

## 13. Bảo vệ query method và search resources

Spring Data REST có thể xuất query methods dưới `/search`. Những method này có thể làm lộ dữ liệu ngay cả khi item endpoint được bảo vệ không đầy đủ.

Ví dụ:

~~~java
@RestResource(path = "by-email", rel = "byEmail")
@PreAuthorize("hasAuthority('users:lookup')")
Optional<User> findByEmail(@Param("email") String email);
~~~

Hãy kiểm tra:

- Query method có trả field nhạy cảm qua representation mặc định hoặc projection không?
- Tham số tìm kiếm có thể bị dùng để dò email, số điện thoại hoặc mã định danh không?
- Người gọi có được phép tìm mọi tenant hay chỉ tenant của mình?
- Kết quả có cần giới hạn, rate limit hoặc audit không?
- Search endpoint có được bảo vệ tương tự item/collection endpoint không?

Nếu cần tra cứu tài khoản theo email hoặc reset token, custom endpoint/service có policy, rate limit và response tối giản thường phù hợp hơn việc export một query method tổng quát.

## 14. Cấu hình HTTP security cùng method security

Method security bảo vệ lời gọi method được đánh dấu. Spring Security cũng khuyến nghị có request-level rule bao phủ các route còn lại, vì method không có annotation không tự động được bảo vệ.

Ví dụ cấu hình khung:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ trên yêu cầu xác thực cho /api và từ chối route còn lại; production cần chọn cơ chế xác thực phù hợp như OAuth2 Resource Server/JWT, session hoặc HTTP Basic theo kiến trúc thực tế.

Request-level security giúp bảo vệ route tổng thể; method-level security thêm điều kiện theo repository, service, method parameter hoặc return value. Cả hai lớp cần được kiểm thử.

CORS không thay thế authorization. Việc một browser origin được phép gửi request không chứng minh người dùng có quyền truy cập dữ liệu.

## 15. Kiểm thử không lộ field nhạy cảm

Không chỉ kiểm tra HTTP status. Hãy xác nhận response body không chứa tên field, giá trị bí mật hoặc dữ liệu quan hệ riêng tư.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class UserExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(authorities = "users:read")
    void userResponseDoesNotExposePasswordHash() throws Exception {
        mockMvc.perform(get("/api/users/12")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").exists())
            .andExpect(jsonPath("$.passwordHash").doesNotExist())
            .andExpect(jsonPath("$.resetToken").doesNotExist());
    }
}
~~~

Kiểm thử projection được công bố:

~~~java
@Test
@WithMockUser(authorities = "users:read")
void publicProjectionDoesNotExposeSecrets() throws Exception {
    mockMvc.perform(get("/api/users/12")
            .param("projection", "userSummary")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.username").exists())
        .andExpect(jsonPath("$.passwordHash").doesNotExist());
}
~~~

Kiểm thử role bị từ chối:

~~~java
@Test
@WithMockUser(authorities = "users:read")
void userWithoutDeleteAuthorityCannotDelete() throws Exception {
    mockMvc.perform(delete("/api/users/12"))
        .andExpect(status().isForbidden());
}
~~~

Nếu không đăng nhập, status thường là 401 tùy authentication entry point; nếu đã đăng nhập nhưng thiếu quyền, thường là 403. Cấu hình thực tế có thể tùy biến response.

Cần có test cho:

- Representation mặc định của item và collection.
- Mọi projection và excerpt.
- Nested projection và association link.
- Search resource và query method.
- GET association trực tiếp bằng URI.
- PUT/PATCH/POST/DELETE association.
- Field bị cấm trong request body có bị thay đổi hay không.
- Người dùng khác tenant/owner không thể truy cập resource.
- Repository method và custom controller đều thực thi authorization.

## 16. Kiểm tra bề mặt dữ liệu trước khi phát hành

Một quy trình rà soát hữu ích:

1. Liệt kê entity/repository được export.
2. Phân loại field thành public, internal, confidential và secret.
3. Kiểm tra Jackson annotations trên field/getter.
4. Liệt kê mọi projection, excerpt và nested projection.
5. Kiểm tra association links và repository đích.
6. Kiểm tra query methods và search parameters.
7. Rà soát field writable, mass assignment và DTO.
8. Rà soát request-level và method-level authorization.
9. Kiểm thử với user thuộc nhiều role, owner và tenant khác nhau.
10. Kiểm tra response thực tế, log và metadata ALPS/JSON Schema để bảo đảm không công bố contract ngoài ý muốn.

ALPS metadata có thể liệt kê tên projection và descriptor field. Metadata không phải nội dung bí mật của entity, nhưng tên projection hoặc relation nội bộ cũng có thể tiết lộ cấu trúc API. Chỉ đăng ký projection và resource mà client được phép khám phá.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| passwordHash không xuất ở GET mặc định nhưng xuất hiện khi projection | Projection có getter cho field bị @JsonIgnore | Rà soát mọi projection và nested projection; xóa getter nhạy cảm |
| Ẩn association link nhưng client vẫn truy cập URI | Link không phải cơ chế authorization | Bảo vệ endpoint/resource đích và association method |
| User thường có thể sửa role | Request binder nhận field ngoài ý định UI | Dùng DTO allowlist, read-only binding và service policy |
| Chỉ DELETE by ID bị chặn nhưng deleteAll vẫn chạy | Chưa bảo vệ mọi method CRUD | Override và bảo vệ tất cả biến thể delete được export |
| Repository-level rule không áp dụng như mong đợi ở method | Method annotation ghi đè class/interface annotation | Viết biểu thức kết hợp trong method nếu cần cả hai điều kiện |
| Search endpoint làm lộ email hoặc token | Query method được export nhưng thiếu authorization | Bảo vệ method, giới hạn kết quả và dùng endpoint chuyên biệt |
| Excerpt lộ dữ liệu quan hệ riêng tư | Nested projection đưa association vào inline | Chỉ xuất field cần thiết và kiểm tra nested projection |
| Endpoint custom vẫn lộ field dù entity có @JsonIgnore | Controller dùng DTO/ObjectMapper/serializer khác | Kiểm tra representation riêng và viết test response |
| CORS cấu hình đúng nhưng người dùng vẫn truy cập được API | CORS không phải authorization | Dùng Spring Security request và method security |
| Có @PreAuthorize nhưng route khác vẫn public | Chỉ bảo vệ method đã đánh dấu | Thêm catch-all request rule và rà soát toàn bộ route |

## 18. Nguyên tắc thiết kế

- Thiết kế representation theo allowlist, không export toàn bộ entity rồi cố gắng ẩn dần từng field.
- Không để secret hoặc credential hash xuất hiện trong bất kỳ projection, excerpt hoặc nested projection nào.
- Dùng DTO/command model cho thao tác nhạy cảm và field có quyền ghi khác nhau theo user.
- Bảo vệ collection, item, search, association và custom controller bằng authorization phù hợp.
- Không coi việc ẩn link, đổi relation name hoặc dùng UUID khó đoán là bảo mật.
- Kiểm tra quyền theo owner/tenant ở server cho từng request.
- Bảo vệ tất cả method CRUD được exporter sử dụng, bao gồm các biến thể bulk delete.
- Dùng test để xác nhận dữ liệu không xuất hiện và request trái phép bị từ chối.
- Rà soát lại projection/association mỗi khi domain model có thêm field hoặc quan hệ mới.

## Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projection, excerpt, nested association và cảnh báo projection có thể đưa field `@JsonIgnore` trở lại response.
- [Spring Data REST 5.1.2 — Security](https://docs.spring.io/spring-data/rest/reference/security.html): bảo vệ repository bằng `@PreAuthorize`, `@Secured`, method-level security và lưu ý method annotation ghi đè repository-level annotation.
- [Spring Data REST 5.1.2 — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association và search resources cùng các HTTP method được export.
- [Spring Security 7.1 — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, authorization theo parameter/return object và test method security.
- [Spring Framework — Jackson JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html): Jackson serialization views trong Spring MVC; nếu dùng custom controller, kiểm soát response view riêng.
