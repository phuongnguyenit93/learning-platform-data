# Ánh xạ danh tính ngoài sang tài khoản nội bộ khi nghiệp vụ cần

Trong một hệ thống dùng **Spring Security OAuth 2.0 / OIDC Resource Server**, Access Token giúp API biết request đã được một **Authorization Server** tin cậy xác thực và cấp các quyền nào. Tuy nhiên, người dùng hoặc ứng dụng có danh tính ở bên ngoài **không nhất thiết trùng với một tài khoản nghiệp vụ** trong cơ sở dữ liệu nội bộ.

Ví dụ, nhà cung cấp danh tính phát hành Access Token cho người dùng có `sub: "00u7x9..."`, nhưng hệ thống quản lý đơn hàng lưu người dùng bằng khóa `app_user.id = 2f8a...`, còn những bảng `orders`, `approval` và `membership` tham chiếu tới **ID nội bộ** này. Resource Server cần một cơ chế **ánh xạ danh tính ngoài sang tài khoản nội bộ (external identity → local account mapping)** khi nghiệp vụ cần kiểm tra quyền sở hữu đơn hàng, tenant, trạng thái tài khoản hoặc lịch sử hoạt động.

Điểm cốt lõi: **xác thực JWT**, **liên kết danh tính với tài khoản** và **phân quyền nghiệp vụ** là ba việc khác nhau. Không nên tự động dùng email, tên người dùng hoặc giá trị trong header do client gửi để gộp tài khoản. Ngược lại, không phải API nào cũng cần tạo tài khoản nội bộ: nếu chỉ kiểm tra scope để phục vụ dữ liệu không gắn người dùng, ánh xạ có thể là không cần thiết.

Bài học sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC và JWT Bearer Access Token** làm ví dụ chính. Các giá trị issuer, subject, tenant và ID chỉ là dữ liệu minh họa.

## 1. Ba lớp danh tính trong một Resource Server

### 1.1. Danh tính được khai báo trong Access Token

Ví dụ JWT Claims Set:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "external-user-7812",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42",
  "email": "employee@example.test"
}
~~~

Nếu JWT được ký hợp lệ bởi issuer tin cậy, có audience dành cho API và đáp ứng những ràng buộc thời hạn/profile, các claims này có thể cung cấp **bối cảnh đã được xác thực**. Tuy nhiên:

- `sub` định danh subject của token **trong ngữ cảnh issuer**, không phải khóa chính của bảng người dùng nội bộ.
- `email` thường là thuộc tính liên lạc, có thể thay đổi, bị thu hồi hoặc được tái sử dụng; không tự động là khóa liên kết tài khoản.
- `tenant_id` có thể là claim riêng theo hợp đồng; API phải định nghĩa rõ kiểu dữ liệu, nguồn phát hành và cách kiểm tra quyền tenant.
- `scope` cho biết phạm vi quyền OAuth 2.0; không mặc nhiên đồng nghĩa quyền sở hữu một đơn hàng hoặc quyền hoạt động của tài khoản nội bộ.
- Một token được ký bởi đúng issuer vẫn cần **audience** phù hợp. Không nhận OIDC ID Token dành cho client thay Access Token dành cho API.

### 1.2. Principal do Spring Security tạo

Với JWT Resource Server, Spring Security thường tạo **`JwtAuthenticationToken`** sau khi `JwtDecoder` xác minh JWT. Principal thường là đối tượng `Jwt`, còn các scope có thể được chuyển thành `GrantedAuthority` như `SCOPE_orders.read`.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalExampleController {

    @GetMapping("/api/debug/principal-example")
    String principalExample(@AuthenticationPrincipal Jwt jwt) {
        // Chỉ minh họa cách đọc subject từ JWT đã xác thực.
        return jwt.getSubject();
    }
}
~~~

Đoạn trên là ví dụ cách lấy principal, **không phải endpoint nên bật trong production để trả định danh ra ngoài một cách tùy ý**. Đọc được `jwt.getSubject()` không có nghĩa API đã tìm thấy một `AppUser` trong cơ sở dữ liệu.

Trong cấu hình phổ biến, `Authentication.getName()` được lấy từ `sub` hoặc một claim được cấu hình làm tên principal. **Đổi claim làm principal name** không tự biến giá trị đó thành ID nội bộ và không chứng minh việc liên kết đã được phê duyệt.

### 1.3. Tài khoản nội bộ của hệ thống

Một tài khoản nghiệp vụ có thể lưu:

~~~text
app_user
--------
id                UUID (khóa chính nội bộ)
display_name      tên hiển thị
status            ACTIVE / SUSPENDED / CLOSED
created_at        thời điểm tạo tài khoản
...
~~~

Các bảng như `orders.owner_user_id`, `approvals.approver_user_id` và `user_tenant_membership.user_id` nên tham chiếu **ID nội bộ ổn định** nếu đó là thiết kế miền nghiệp vụ. Nếu tổ chức đổi IdP hoặc người dùng liên kết thêm danh tính mới, các quan hệ dữ liệu nghiệp vụ không nhất thiết phải bị thay khóa.

### 1.4. Tóm tắt mối quan hệ

| Lớp | Ví dụ | Nguồn sự thật | Trách nhiệm |
| --- | --- | --- | --- |
| **JWT claims** | `iss`, `sub`, `aud`, `scope` | Authorization Server được tin cậy | Thông tin về token và principal ngoài. |
| **Spring Security Authentication** | `JwtAuthenticationToken` | Token validation + converter | Request đã xác thực là ai, có authorities nào. |
| **Liên kết danh tính** | `(issuer, subject) → local_user_id` | Cơ sở dữ liệu/quy trình liên kết nội bộ | Biết principal ngoài tương ứng tài khoản nào. |
| **Tài khoản nội bộ** | `AppUser.id`, trạng thái tài khoản | Domain user service | Danh tính nghiệp vụ ổn định và vòng đời tài khoản. |
| **Phân quyền tài nguyên** | Chủ sở hữu đơn hàng, tenant membership | Domain services/policy | Có được xem/sửa dữ liệu cụ thể hay không. |

## 2. Khi nào nên ánh xạ, khi nào không cần?

**Nên ánh xạ sang tài khoản nội bộ** khi API có khái niệm user nội bộ độc lập với IdP:

- Đơn hàng, hồ sơ, lịch sử phê duyệt hoặc dữ liệu cần gắn với một khóa `user_id` ổn định.
- Tài khoản có trạng thái **ACTIVE / SUSPENDED / CLOSED** riêng với trạng thái của token.
- Quyền thuộc domain như vai trò trong công ty, thành viên tenant hoặc quyền sở hữu bản ghi được quản lý nội bộ.
- Nhiều nhà cung cấp danh tính có thể liên kết đến cùng một tài khoản nghiệp vụ.
- Cần chuyển IdP, hợp nhất tenant hoặc lưu lịch sử nghiệp vụ mà không đổi mọi khóa tham chiếu.
- Hệ thống cần quản lý quy trình đăng ký, mời tham gia, xác minh đủ điều kiện hoặc phê duyệt tài khoản.

**Có thể không cần ánh xạ** khi API chỉ là một Resource Server kỹ thuật, ví dụ endpoint trả dữ liệu không gắn người dùng cụ thể và chỉ cần kiểm tra `SCOPE_metrics.read` hoặc `SCOPE_catalog.read`. Khi không có quan hệ nghiệp vụ với account nội bộ, tạo bản ghi user cho mọi Access Token sẽ tăng độ phức tạp không cần thiết.

| Tình huống | Có cần local account? | Thiết kế hợp lý |
| --- | --- | --- |
| API công khai dữ liệu sau khi xác minh một scope ứng dụng | Thường không | Dùng `JwtAuthenticationToken` và scope policy. |
| User xem đơn hàng thuộc mình | Có, nếu đơn hàng lưu `owner_user_id` nội bộ | Resolve external identity → local user; kiểm tra owner. |
| Nhiều hệ thống con chia sẻ quyền dùng cùng IdP | Tùy | Chỉ tạo local user nơi cần dữ liệu/trạng thái nội bộ. |
| Service-to-service không có người dùng tương tác | Thường không nên tạo người dùng cá nhân | Quản lý service principal/client identity riêng. |
| Một người đăng nhập bằng hai IdP | Có, nếu nghiệp vụ muốn cùng tài khoản | Liên kết nhiều external identities với một local user theo quy trình an toàn. |
| Nội bộ khóa/suspend tài khoản dù token vẫn còn hạn | Có | Kiểm tra local account status trên request/action nhạy cảm. |

Nguyên tắc thiết kế là **giữ ánh xạ ở nơi có nhu cầu nghiệp vụ thật**; đừng biến việc đăng nhập ở IdP thành hành động tự động tạo/chỉnh sửa mọi tài khoản nội bộ nếu sản phẩm không yêu cầu.

## 3. Khóa liên kết cơ bản: `(iss, sub)`, không phải chỉ `sub`

Theo JWT/OIDC, subject `sub` cần được diễn giải trong **phạm vi issuer `iss`**. Hai issuer khác nhau có thể cùng dùng chuỗi `sub: "1234"` cho hai người hoàn toàn khác nhau.

~~~text
Issuer A: https://idp-a.example.test
  sub = "1234" -> Người dùng A

Issuer B: https://idp-b.example.test
  sub = "1234" -> Người dùng B
~~~

Nếu cơ sở dữ liệu chỉ có:

~~~sql
SELECT user_id FROM external_identity WHERE subject = '1234';
~~~

thì có thể ánh xạ nhầm, thậm chí gộp quyền giữa các tài khoản. Cách đúng là sử dụng **cặp (issuer, subject)**:

~~~sql
SELECT user_id
FROM external_identity
WHERE issuer = 'https://idp-a.example.test'
  AND subject = '1234';
~~~

Không lấy issuer hoặc subject từ HTTP header như `X-User-Id` hoặc query parameter do client gửi. Phải lấy từ **Access Token đã được Resource Server xác thực đúng chữ ký, issuer, audience và thời hạn**.

### 3.1. Vì sao email không phải khóa liên kết mặc định?

Email có thể:

1. Đổi khi nhân viên thay họ, phòng ban hoặc tên miền doanh nghiệp.
2. Được tái sử dụng sau khi tài khoản cũ bị xóa/thu hồi.
3. Chưa được nhà phát hành xác minh, hoặc `email_verified` không hiện diện.
4. Trùng hoặc không duy nhất trong một số hệ thống danh tính.
5. Có cách chuẩn hóa khác nhau giữa các bên (chữ hoa/thường, alias, domain).
6. Xuất hiện trong Access Token vì tiện hiển thị nhưng **không phải định danh principal ổn định theo hợp đồng**.

Ví dụ nguy hiểm:

~~~java
// KHÔNG LÀM: đừng tự động đăng nhập vào local account
// chỉ bằng email claim.
String email = jwt.getClaimAsString("email");
AppUser user = users.findByEmail(email).orElseThrow();
~~~

Ngay cả khi issuer báo `email_verified: true`, **điều đó không chứng minh người dùng được quyền chiếm tài khoản nội bộ có cùng email**. Email đã xác minh có thể là một tín hiệu cho quy trình mời/liên kết riêng, không phải thay thế việc chứng minh quyền sở hữu tài khoản nội bộ và nguồn danh tính ngoài.

### 3.2. `sub` không phải mã nhân viên, username hay client ID trong mọi trường hợp

- `sub` có thể là một identifier vô nghĩa đối với người đọc, không nên parse để lấy thông tin nghiệp vụ.
- OIDC có thể dùng **pairwise subject identifiers**; cùng một người đăng nhập qua các client có thể nhận `sub` khác nhau theo **sector identifier**. Không tự gộp hai subject chỉ vì email giống nhau.
- Khi thay đổi issuer/realm hoặc chiến lược phát hành subject, key liên kết có thể thay; việc di chuyển phải qua quy trình migration/linking đã kiểm soát.
- Với client credentials hoặc mô hình máy-với-máy, `sub` có thể đại diện **client/application** chứ không phải con người, tùy token profile. Không tự tạo một `AppUser` cá nhân từ mọi token có `sub`.

Nếu cần định danh service, dùng mô hình `ServiceAccount` hoặc `ClientPrincipal` riêng theo token contract. Không giả định `client_id`, `azp` và `sub` luôn hoán đổi cho nhau.

## 4. Sơ đồ ánh xạ danh tính ngoài sang domain account

Giả sử ứng dụng quản lý đơn hàng dùng bảng `app_user` và `external_identity`:

~~~text
Browser / OAuth2 Client
        |
        | Authorization: Bearer <JWT Access Token>
        v
Spring Security Resource Server
        |
        +-- Xác minh chữ ký + iss + aud + exp
        |
        v
JwtAuthenticationToken
        |
        | issuer = https://identity.example.test/realms/company
        | subject = external-user-7812
        v
ExternalIdentityResolver
        |
        | SELECT user_id WHERE issuer=? AND subject=?
        v
external_identity
  (iss, sub) ------------------------> app_user.id
                                       |
                                       +-- status ACTIVE?
                                       +-- membership/tenant?
                                       +-- policy với dữ liệu?
                                       v
                                  Domain service
                                       |
                                       v
                               Đơn hàng được phép
~~~

Tách rõ ba tầng:

- **Authentication:** Spring Security xác minh Bearer Access Token và tạo principal.
- **Account resolution:** ứng dụng tra cứu liên kết đã được thiết lập giữa principal ngoài và tài khoản nội bộ.
- **Authorization:** nghiệp vụ xét trạng thái local account, quyền tenant và quyền trên tài nguyên.

Không cho phép **account resolution** thay thế authentication: nếu chỉ decode JWT để lấy `sub` rồi truy vấn database, một token bị sửa vẫn có thể đưa ra `sub` của người khác.

## 5. Thiết kế cơ sở dữ liệu cho liên kết

### 5.1. Hai bảng tách biệt

Một thiết kế quan hệ đơn giản (ví dụ PostgreSQL):

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identity(user_id);
~~~

**Một external identity chỉ được ánh xạ tới tối đa một local account** nhờ `UNIQUE (issuer, subject)`. Một tài khoản nội bộ có thể có **nhiều external identities** nếu sản phẩm cho phép đăng nhập bằng nhiều IdP hoặc liên kết danh tính phụ.

Trong môi trường nhiều tenant có tenant boundary tách biệt, cần xác định tenant thuộc về **issuer**, subject hay domain account. Không thêm `tenant_id` vào unique key chỉ để làm cho các cặp trùng nhau “hết lỗi” nếu điều đó vô tình cho cùng một external identity chiếm nhiều tài khoản không được phép. Bất kỳ khóa liên kết mở rộng nào cũng phải theo **identity contract** và ranh giới cấp quyền thực sự.

### 5.2. Khóa nội bộ phải giữ ổn định

Ví dụ người dùng đổi từ IdP A sang IdP B:

~~~text
Trước migration:
  (iss=A, sub=old-123) -> user_id=550e8400-...

Sau migration:
  (iss=A, sub=old-123) -> user_id=550e8400-...  [tạm còn]
  (iss=B, sub=new-789) -> user_id=550e8400-...  [liên kết mới]
~~~

Các bảng đơn hàng vẫn tham chiếu cùng **user_id nội bộ**, không cần thay mọi khóa ngoại. Khi bỏ liên kết A, cần kiểm tra phiên đăng nhập, token còn hạn, audit trail và yêu cầu bảo mật liên quan. Không tự xóa/hợp nhất tài khoản chỉ vì một external identity biến mất khỏi IdP.

### 5.3. Những trường bổ sung hữu ích

Trong hệ thống thực tế, có thể cần `provider_type`, `link_method`, `linked_by`, `last_seen_at`, `revoked_at`, `created_at`, `identity_status` hoặc bản ghi audit. Cần phân biệt:

- **Identity link active:** cơ chế ánh xạ hiện hành cho principal ngoài.
- **Local user active:** tài khoản nghiệp vụ đang được phép hoạt động.
- **Membership/permission active:** user vẫn có quyền truy cập một tenant hoặc tài nguyên cụ thể.

Đừng dùng một cờ `active` duy nhất để suy ra cả ba trạng thái nếu domain có vòng đời khác nhau.

### 5.4. Không log/công bố cặp liên kết thiếu kiểm soát

`iss` và `sub` có thể là định danh cá nhân hoặc cho phép liên kết dữ liệu giữa hệ thống. Cần hạn chế truy cập bảng mapping, audit những thay đổi liên kết, tránh đưa nguyên subject/email vào log/metrics/ticket không cần thiết, và bảo vệ thông tin này theo chính sách dữ liệu cá nhân.

## 6. Spring Security: lấy principal ngoài đã được xác thực

### 6.1. Cấu hình JWT Resource Server

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/company
          audiences:
            - orders-api
~~~

Nếu Spring Boot version đang dùng hỗ trợ thuộc tính `audiences`, API chỉ nhận JWT có audience `orders-api`. Với phiên bản khác, cấu hình audience validator riêng bằng `JwtDecoder`. Cần đảm bảo JWT signature, thời hạn và issuer đều được kiểm tra theo profile áp dụng.

Không đọc `iss` trong JWT chưa xác thực rồi tự động tải metadata/khóa từ bất kỳ URL nào. Nếu có nhiều issuer, dùng allowlist và decoder/validator theo từng nguồn được phê duyệt.

SecurityFilterChain của API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong ví dụ, `GET /api/me` chỉ được truy cập khi JWT đã xác thực và có `SCOPE_profile.read`; những URL khác chưa định nghĩa đều bị từ chối. Đây là cấu hình minh họa cho một API thuần Bearer header, không dùng session cookie. **Không tắt CSRF một cách máy móc cho ứng dụng web dùng OIDC Login và cookie/session**.

### 6.2. Điều không nên làm với principal name

Spring Security có thể dùng `sub` làm `Authentication.getName()`, hoặc cho phép cấu hình principal claim khác bằng `JwtAuthenticationConverter`. Tuy nhiên:

~~~text
Authentication.getName() = "external-user-7812"
~~~

không đồng nghĩa:

~~~text
app_user.id = "external-user-7812"
~~~

**Thay cách chọn principal name chỉ thay nhãn được framework nhìn thấy, không tạo liên kết an toàn tới local account.** Nếu domain dùng UUID nội bộ, phải có bước resolve rõ ràng.

Tương tự, `JwtGrantedAuthoritiesConverter` có thể ánh xạ `scope` sang authority, nhưng nó **không tự kiểm tra local account bị SUSPENDED**, membership tenant hoặc quyền sở hữu từng bản ghi.

## 7. Triển khai tra cứu danh tính ngoài bằng Spring Data JPA

Đây là một mô hình tham khảo: **không tự động tạo local user khi chỉ có Bearer JWT**. Hệ thống giả định bảng liên kết đã được tạo qua quy trình đăng ký/invite/provisioning hoặc linking được phê duyệt.

### 7.1. Entity và repository

Các lớp có thể được đặt trong những tệp Java riêng dưới cùng package của ứng dụng.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "external_identity",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_external_issuer_subject",
        columnNames = {"issuer", "subject"}))
public class ExternalIdentity {

    @Id
    private UUID id;

    @Column(nullable = false, length = 512)
    private String issuer;

    @Column(nullable = false, length = 512)
    private String subject;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    protected ExternalIdentity() {}

    public UUID getUserId() {
        return userId;
    }
}
~~~

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ExternalIdentityRepository
        extends JpaRepository<ExternalIdentity, UUID> {

    Optional<ExternalIdentity> findByIssuerAndSubject(
        String issuer, String subject);
}
~~~

Entity user nội bộ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

enum UserStatus {
    ACTIVE, SUSPENDED, CLOSED
}

@Entity
@Table(name = "app_user")
public class AppUser {

    @Id
    private UUID id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserStatus status;

    protected AppUser() {}

    public UUID getId() { return id; }
    public String getDisplayName() { return displayName; }
    public UserStatus getStatus() { return status; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository
        extends JpaRepository<AppUser, UUID> {
}
~~~

Những entity trên chỉ nêu các trường cần thiết cho ví dụ ánh xạ. Khi triển khai, cần thống nhất migration/schema thực tế, lifecycle, cách tạo ID và các trường audit. Ví dụ dùng `jakarta.persistence` theo Spring Boot 3.x và yêu cầu dependency Spring Data JPA/database driver trong dự án nếu ứng dụng chạy thật.

### 7.2. Service chỉ đọc để resolve tài khoản

~~~java
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record CurrentAccount(UUID userId, String displayName) {}

@Service
public class CurrentAccountService {

    private final ExternalIdentityRepository identities;
    private final AppUserRepository users;

    public CurrentAccountService(
            ExternalIdentityRepository identities,
            AppUserRepository users) {
        this.identities = identities;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public CurrentAccount resolve(Jwt jwt) {

        // Jwt chỉ được truyền vào từ principal đã được
        // Spring Security xác thực, không decode thủ công.
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Account unavailable");
        }

        ExternalIdentity linked = identities
            .findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() ->
                new AccessDeniedException("Account unavailable"));

        AppUser user = users.findById(linked.getUserId())
            .orElseThrow(() ->
                new AccessDeniedException("Account unavailable"));

        if (user.getStatus() != UserStatus.ACTIVE) {
            throw new AccessDeniedException("Account unavailable");
        }

        return new CurrentAccount(
            user.getId(), user.getDisplayName());
    }
}
~~~

Mã minh họa cố ý **không tự tạo tài khoản** khi không tìm thấy liên kết. Nó cũng không trả về thông tin người khác khi user bị khóa. `AccessDeniedException` thường dẫn đến **403 Forbidden** khi request đã xác thực, tùy security exception handling và vị trí phát sinh lỗi.

Ở hệ thống có account mapping đã được xác lập, **không có liên kết** hoặc **account bị vô hiệu hóa** nên được xử lý như “principal đã xác thực nhưng **không được phép dùng tài khoản nội bộ này**”, thay vì âm thầm tạo bản ghi mới.

### 7.3. Controller lấy tài khoản nội bộ

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentAccountController {

    private final CurrentAccountService currentAccountService;

    CurrentAccountController(
            CurrentAccountService currentAccountService) {
        this.currentAccountService = currentAccountService;
    }

    @GetMapping("/api/me")
    CurrentAccount me(@AuthenticationPrincipal Jwt jwt) {
        return currentAccountService.resolve(jwt);
    }
}
~~~

Luồng thực tế:

~~~text
GET /api/me
Authorization: Bearer <valid-access-token>
       |
       v
JWT được xác minh, scope profile.read hợp lệ
       |
       v
Jwt: iss + sub đã xác thực
       |
       v
external_identity: tìm user_id
       |
       v
app_user: kiểm tra ACTIVE
       |
       v
200 {"userId": "...", "displayName": "..."}
~~~

**Response chỉ trả dữ liệu được phép công bố.** Không cần trả toàn bộ JWT claims, email riêng tư, identity links, internal roles hoặc dữ liệu liên quan IdP khác nếu endpoint không có nhu cầu.

### 7.4. Thời điểm nên resolve

Trong các API cần tài khoản nội bộ, có thể resolve trong:

- **Application service** nhận `Jwt` hoặc một cấu trúc external principal đã chuẩn hóa, như ví dụ trên.
- **CurrentUser/CurrentAccount resolver** cho các endpoint thật sự cần `AppUser`.
- **Custom Authentication converter/provider** nếu toàn bộ API luôn cần local account, nhưng phải thiết kế cẩn thận về DB I/O, lỗi dependency, cách cache và việc giữ authorities/claims đã được xác thực.

Thông thường, bắt đầu bằng **service rõ ràng sau authentication** giúp phân biệt JWT verification và domain lookup. Không nhét việc tạo/sửa tài khoản vào `JwtDecoder`; decoder nên tập trung vào tính hợp lệ của token. Không thực hiện ghi database mỗi lần nhận Bearer token chỉ để “đồng bộ hồ sơ”, trừ khi đó là quy trình có kiểm soát đã được thiết kế.

## 8. Mapping không phải account linking: ai có quyền tạo liên kết?

Đọc bảng liên kết đã được phê duyệt là một chuyện; **tạo hoặc thay đổi liên kết** là hành động bảo mật nhạy cảm hơn nhiều. Nếu hệ thống tự gán `(iss, sub)` vào tài khoản dựa trên email trùng, kẻ tấn công có thể tìm cách chiếm tài khoản.

### 8.1. Những mô hình provisioning/linking phổ biến

| Mô hình | Cách hoạt động | Rủi ro cần quản lý |
| --- | --- | --- |
| **Pre-provisioning** | Admin/hệ thống nguồn tạo local user và link theo thông tin đáng tin cậy trước lần đăng nhập đầu. | Sai mapping ban đầu, quy trình đổi người, quyền admin và audit. |
| **SCIM provisioning** | Identity lifecycle được đồng bộ qua SCIM hoặc tích hợp tương đương. | Giao kèo định danh, trạng thái vô hiệu hóa, idempotency, reconcile và quyền connector. |
| **Invite/claim account** | Người dùng có lời mời/phiên liên kết hợp lệ, chứng minh quyền sở hữu trước khi gắn external identity. | Token lời mời bị đoán/sử dụng lại, sai tenant, hết hạn, double linking. |
| **User-initiated account linking** | User đăng nhập vào local account hiện tại, sau đó chủ động xác thực với IdP mới và xác nhận liên kết. | CSRF, login CSRF, session fixation, token/code replay, thiếu xác minh cả hai phía. |
| **Just-in-time (JIT) provisioning** | Tạo local account khi principal hợp lệ lần đầu nếu chính sách cho phép. | Tạo tài khoản trái phép, role/tenant không rõ, racing requests, orphan accounts. |

**Không có mô hình mặc định đúng cho mọi hệ thống.** Nếu nghiệp vụ yêu cầu duyệt nhân viên trước khi sử dụng dữ liệu, pre-provisioning hoặc invite có kiểm soát phù hợp hơn JIT tự do. Nếu API chỉ cần scope, không nên auto-create AppUser chỉ vì mỗi JWT có `sub`.

### 8.2. Liên kết tài khoản phải chứng minh quyền ở cả hai phía

Một quy trình user-initiated linking an toàn ở mức khái niệm:

1. Người dùng đang có một **phiên local account** đã xác thực và được phép sửa phương thức đăng nhập.
2. Hệ thống yêu cầu **reauthentication** phù hợp nếu đây là thao tác nhạy cảm.
3. Người dùng chủ động bắt đầu luồng OIDC/Authorization Code với IdP cần liên kết.
4. OAuth/OIDC Client xác minh `state`, PKCE (khi áp dụng), `nonce` theo yêu cầu OIDC, issuer, audience và kết quả đăng nhập.
5. Hệ thống xác định **`(iss, sub)` đã được xác thực** của identity mới.
6. Trong transaction, kiểm tra identity đó chưa liên kết với tài khoản khác, quyền thao tác liên kết của user hiện tại, tenant và điều kiện chính sách.
7. Lưu liên kết, ghi audit sự kiện và thông báo khi cần; giữ cơ chế hủy/khôi phục an toàn.

**Resource Server không tự là OIDC Login Client.** Nếu endpoint liên kết danh tính cần điều hướng người dùng qua OIDC, thành phần OAuth 2.0 Client/Relying Party phải xử lý protocol đúng; không nhận một ID Token do browser tùy ý post lên rồi coi là đã hoàn thành account linking.

Không lấy `email` từ OIDC/JWT mới rồi tìm local user có cùng email để tự liên kết. Nếu hệ thống có chính sách linking qua email, phải có quy trình xác minh bổ sung, chống chiếm đoạt và đánh giá rủi ro riêng; **email matching không đủ làm bằng chứng duy nhất**.

### 8.3. Cập nhật liên kết phải atomic

Hai request đầu tiên có thể tới đồng thời:

~~~text
Request A: chưa thấy external identity -> tạo liên kết
Request B: chưa thấy external identity -> tạo liên kết
~~~

Nếu chỉ kiểm tra “chưa tồn tại” ở code rồi insert, cả hai có thể tạo liên kết hoặc đưa một subject về hai account khác nhau.

Hãy kết hợp:

- **Database UNIQUE (issuer, subject)** làm rào chắn cuối.
- **Transaction** cho quy trình tạo liên kết/tạo user.
- Xử lý **unique constraint conflict** theo chính sách idempotent: nếu cùng user, có thể xem là đã liên kết; nếu khác user, **từ chối và điều tra**, không tự gộp.
- Audit người/tiến trình đã tạo liên kết và nguồn chứng minh quyền sở hữu.
- Kiểm tra tenant boundary và tình trạng liên kết ở thời điểm commit nếu thay đổi nhạy cảm.

Không thực hiện “nếu conflict thì update user_id sang người hiện tại”: hành vi đó có thể biến một request thành thao tác **chiếm quyền liên kết**.

## 9. JIT provisioning: chỉ áp dụng khi hợp đồng cho phép

Một số sản phẩm cho phép người dùng trong tổ chức được cấp local account ngay lần đầu gọi API hoặc đăng nhập. Khi đó **JIT provisioning** có thể thích hợp, nhưng phải là **chính sách tạo account** riêng, không phải một dòng `orElseGet(userRepository::save)` vô điều kiện.

### 9.1. Điều kiện điển hình trước khi tạo user

- JWT đã được **xác minh chữ ký, issuer, audience, thời hạn** và token profile.
- Chủ thể phải thực sự là **end user** theo hợp đồng (không phải service principal).
- Issuer nằm trong allowlist của tổ chức và được phép đăng ký tài khoản.
- Tenant/organization membership được xác minh qua **nguồn đáng tin**; không nhận `tenant_id` tự khai từ HTTP header.
- Nếu cần lời mời, phải có **invitation hợp lệ, chưa sử dụng và đúng email/tenant/đối tượng** theo cơ chế chứng minh quyền.
- Vai trò ban đầu theo **least privilege**; không suy ra `ADMIN` chỉ từ tên miền email hoặc claim tùy ý.
- Thao tác tạo liên kết có transaction, unique constraint và audit.
- Quy trình phải có cách thu hồi/suspend account và reconcile với lifecycle của IdP.

Nếu bất kỳ điều kiện bắt buộc nào không được đáp ứng, **không tạo tài khoản**. Có thể trả response yêu cầu hoàn tất onboarding hoặc từ chối truy cập theo chính sách.

### 9.2. Ví dụ rủi ro khi auto-create theo email

~~~java
// KHÔNG LÀM:
String email = jwt.getClaimAsString("email");
AppUser user = users.findByEmail(email)
    .orElseGet(() -> users.save(
        new AppUser(/* email và quyền từ JWT */)));
~~~

Đoạn trên vừa dùng email làm khóa liên kết, vừa tạo account ngoài quy trình, lại có thể đồng nhất hóa quyền từ token với quyền nội bộ. Ngay cả khi JWT đã được issuer đáng tin ký, **cấp tài khoản nội bộ** vẫn cần một quyết định nghiệp vụ riêng.

## 10. Phân quyền: token hợp lệ vẫn có thể bị account nội bộ từ chối

Giả sử user có Access Token còn hiệu lực với:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "external-user-7812",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Tại thời điểm gọi API, bảng `app_user` lại có:

~~~text
id:      2f8a8fbd-....
status:  SUSPENDED
~~~

JWT vẫn có thể hợp lệ về chữ ký, issuer, audience và thời hạn, **nhưng hệ thống phải từ chối thao tác yêu cầu tài khoản đang ACTIVE**. Trạng thái nội bộ là ràng buộc độc lập, không được bỏ qua chỉ vì token còn hạn.

### 10.1. Scope và role JWT không thay quyền dữ liệu

Một token có `SCOPE_orders.read` không chứng minh user được xem mọi đơn hàng của mọi tenant. Quy trình đúng:

~~~text
JWT hợp lệ, scope orders.read
             |
             v
Resolve local user_id
             |
             v
Kiểm tra status ACTIVE
             |
             v
Kiểm tra tenant membership
             |
             v
Kiểm tra owner_user_id của đơn hàng / policy cụ thể
             |
          Cho phép hoặc từ chối
~~~

Trong các ứng dụng có multi-tenancy, token `tenant_id` và membership nội bộ có thể phải khớp. Nếu subject có thể thuộc nhiều tenant, hãy thiết kế tenant selection và authorization rõ; không chỉ tin path `/tenants/{tenantId}` hoặc `X-Tenant-Id` mà client tự chọn.

### 10.2. Ví dụ kiểm tra quyền trên đơn hàng

Giả sử domain service đã resolve `CurrentAccount` và có entity `Order` với `ownerUserId`:

~~~java
import org.springframework.security.access.AccessDeniedException;

public final class OrderAccessPolicy {

    public void requireOwner(
            CurrentAccount account,
            Order order) {

        if (!order.getOwnerUserId().equals(account.userId())) {
            throw new AccessDeniedException(
                "Order access is not permitted");
        }
    }
}
~~~

Ở đây `Order` là domain entity minh họa phải được định nghĩa trong dự án; chính sách có thể phức tạp hơn khi có role nhân viên hỗ trợ, tenant admin hoặc delegated access. Điểm chính là **so sánh với local user đã resolve**, không dùng `sub` làm `owner_user_id` nếu database không được thiết kế theo subject ngoài.

Nên áp quyền gần lớp service/data-access để giảm nguy cơ **BOLA/IDOR** (user đoán ID đơn hàng người khác rồi gọi cùng endpoint).

## 11. Chuẩn hóa principal nội bộ: nên làm ở đâu?

Có hai kiểu triển khai thường gặp.

### 11.1. Giữ Jwt principal và resolve khi cần

Theo ví dụ mục 7, controller nhận `@AuthenticationPrincipal Jwt`, service lấy `iss/sub` rồi tra cứu `AppUser`.

Ưu điểm:

- Tách **xác thực Bearer token** khỏi việc dùng dữ liệu nghiệp vụ.
- Không bắt endpoint không dùng account phải truy vấn database.
- Thấy rõ chỗ nào cần kiểm tra trạng thái tài khoản, tenant và quyền dữ liệu.
- Dễ mock service khi test authorization.

Nhược điểm:

- Nhiều endpoint cần user có thể lặp lại việc gọi resolver nếu không có lớp ứng dụng chung.
- Cần thống nhất cách xử lý lỗi và cache để không tra cứu không cần thiết trong cùng một request.

Có thể tạo `CurrentAccountContext` request-scoped hoặc một facade để reuse kết quả **trong một request**. Không nên lưu đối tượng tài khoản mutable trong một cache toàn cục mà không xét tính nhất quán trạng thái.

### 11.2. Tạo principal/domain authentication tùy biến

Một số ứng dụng muốn `Authentication` chứa cả `Jwt` và `localUserId`, hoặc tạo `CurrentUserPrincipal`. Điều này có thể hợp lý khi mọi endpoint thực sự cần account nội bộ.

Tuy nhiên phải xử lý:

- Không thay thế JWT validation bằng tra cứu database.
- Không bỏ các authorities đã được kiểm tra hoặc tự cấp role từ dữ liệu sai kiểu.
- Lỗi account bị suspend/no link phải được xử lý **fail-closed**.
- DB I/O trong đường authentication phải có timeout, quan sát lỗi và chính sách cache.
- Nếu local account bị khóa, cache không được tiếp tục cho phép đến hết hạn token một cách vô điều kiện.
- Không sửa `Authentication.getName()` thành ID nội bộ rồi giả định mọi thành phần sử dụng subject ngoài vẫn có thể đọc như trước.

Đổi `JwtAuthenticationConverter.setPrincipalClaimName(...)` chỉ thay **claim dùng làm tên principal**, không tự thực hiện tra cứu account/link. Nếu cần domain principal, thiết kế converter/provider riêng và kiểm thử đầy đủ.

**Cách tiếp cận thực tiễn:** trước tiên dùng **service resolve sau authentication**. Chỉ chuyển vào authentication pipeline khi có lý do nhất quán về kiến trúc và đã tính đến chi phí truy vấn, lỗi, security context.

## 12. Token và vòng đời tài khoản không đồng bộ tức thời

Bearer JWT thường có thời gian sống độc lập với cơ sở dữ liệu local. Vì thế:

~~~text
10:00 — IdP phát hành JWT còn hạn đến 10:15.
10:03 — Local admin chuyển app_user thành SUSPENDED.
10:04 — Client vẫn gửi JWT cũ, chữ ký/exp đều đúng.
10:04 — API kiểm tra local account status và từ chối.
~~~

Nếu API chỉ xác minh JWT mà **không kiểm tra local user**, trạng thái đình chỉ nội bộ có thể không được phản ánh trong authorization. Đó là lý do account resolution có giá trị khi domain quản lý trạng thái riêng.

### 12.1. Cache ánh xạ như thế nào?

Có thể cache `(iss,sub) → userId` để giảm truy vấn, nhưng phải có kế hoạch cho:

- **Unlink/relink**: identity bị thu hồi hoặc được liên kết sang tài khoản khác qua quy trình có kiểm soát.
- **SUSPENDED/CLOSED**: trạng thái account có thể thay đổi trước khi JWT hết hạn.
- **Tenant membership**: quyền trên tenant/bản ghi có thể bị thu hồi.
- **TTL và invalidation**: cache không được khiến quyền bị vô hiệu hóa vẫn tiếp tục được chấp nhận ngoài mức chấp nhận rủi ro đã xác định.
- **Multi-node consistency**: các node không được giữ hai mapping xung đột trong thời gian dài.

Một giải pháp có thể cache identity link ổn định với TTL ngắn, nhưng tra trạng thái nhạy cảm từ nguồn hiện thời hoặc cơ chế invalidation chủ động. Không có một TTL chuẩn cho mọi hệ thống; lựa chọn phụ thuộc yêu cầu thu hồi quyền và mức rủi ro.

### 12.2. JWT Access Token và refresh token không phải nguồn đồng bộ account

Resource Server thường nhận **Access Token**; nó không tự động đổi refresh token để cập nhật hồ sơ user. Quản lý session/login và refresh token thuộc OAuth 2.0 Client và Authorization Server theo flow liên quan.

Nếu tổ chức cần cập nhật nhân viên ra/vào hệ thống, có thể dùng **SCIM provisioning**, sự kiện lifecycle, quy trình quản trị hoặc đồng bộ nguồn nhân sự, thay vì kỳ vọng mọi request Access Token có đủ dữ liệu hiện thời.

## 13. Trường hợp đặc biệt: machine-to-machine và delegated access

### 13.1. Token cấp cho client thay vì con người

Trong OAuth 2.0 **client credentials**, token đại diện ứng dụng/service được cấp quyền, không nhất thiết có người dùng đứng sau. Dù token có `sub`, nó có thể mang ý nghĩa theo profile của Authorization Server, không phải `AppUser` cá nhân.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "nightly-batch-client",
  "client_id": "nightly-batch-client",
  "aud": ["reports-api"],
  "scope": "reports.generate"
}
~~~

Với token kiểu này, hệ thống có thể:

- Xây `ServiceAccount` hoặc `ClientPrincipal` riêng dựa trên claim **đã được xác minh và profile đã thỏa thuận**.
- Áp policy theo client và resource; ghi audit job/service tương ứng.
- Từ chối endpoint yêu cầu **end-user local account** nếu token chỉ biểu diễn service principal.

Không tạo `AppUser` cho một batch client rồi cấp quyền như nhân viên chỉ vì `sub` hiện diện.

### 13.2. On-behalf-of, delegation và actor

Trong một số hệ thống, token có thể mang thông tin **actor** hoặc người được ủy quyền, ví dụ theo RFC 8693 token exchange. Lúc đó phải phân biệt:

- **subject** mà quyền được thực thi thay mặt;
- **client/actor** thực hiện request;
- **internal account** nào được dùng cho nghiệp vụ;
- **permission** của hành động được ủy quyền.

Không tùy tiện lấy một claim như `act`, `client_id` hoặc `azp` và thay `sub` mà không có hợp đồng token cụ thể. Audit nên thể hiện người được đại diện và actor khi nghiệp vụ cần, tránh để một delegated token bị hiểu thành đăng nhập trực tiếp của chủ tài khoản.

## 14. Account linking, unlinking và migration là nghiệp vụ nhạy cảm

### 14.1. Unlink tài khoản

Khi user muốn gỡ một identity ngoài:

- Yêu cầu user còn quyền quản lý local account.
- Kiểm tra xem đây có phải **phương thức đăng nhập cuối cùng** không để tránh khóa người dùng khỏi tài khoản nếu không có cơ chế khôi phục.
- Không cho bên ngoài tự unlink identity của người khác.
- Thu hồi/đánh dấu không còn hiệu lực liên kết trong database; cân nhắc token cũ vẫn còn hạn và cache.
- Ghi audit ai, lúc nào, từ phiên nào đã gỡ.
- Nếu identity đang bị tranh chấp/điều tra, không tự xóa dấu vết bảo mật.

### 14.2. Chuyển IdP hoặc thay issuer

Khi realm/issuer thay đổi, `iss` cũ và `iss` mới là hai định danh khác nhau; không thể chỉ đổi cấu hình verifier rồi kỳ vọng bảng mapping tự hoạt động.

Quy trình migration thường gồm:

1. Lập danh sách **external identities cũ** và chủ sở hữu local account.
2. Thiết lập ánh xạ qua nguồn danh tính đáng tin, với quy trình xác minh khi cần.
3. Tạo các liên kết mới trong transaction, kiểm tra uniqueness và xung đột.
4. Thử trên môi trường hạn chế, xác nhận user truy cập đúng dữ liệu của mình.
5. Quản lý thời điểm thay đổi issuer/khóa/token và chuyển tiếp các liên kết.
6. Thu hồi liên kết cũ khi phù hợp, giữ audit trail.

Đừng “migration” bằng cách gộp toàn bộ tài khoản có email giống nhau. Nếu hai external identities không có chứng cứ hợp lệ là cùng một chủ thể được phép liên kết, phải dừng và xác minh qua quy trình riêng.

### 14.3. Khi một danh tính ngoài đang trỏ sang user khác

Nếu `(iss,sub)` đang liên kết tới `user-A`, request mới muốn gắn nó sang `user-B`, đây là tình huống **security conflict**, không phải một thao tác update bình thường.

Nên từ chối chuyển tự động, yêu cầu xác minh/điều tra và audit. Trong database, unique constraint bảo đảm không thể insert hai hàng trùng cặp; nhưng **quy tắc ứng dụng** vẫn phải cấm việc tùy tiện sửa `user_id` của hàng hiện hữu.

## 15. Kiểm thử ánh xạ và phân quyền nội bộ

Kiểm thử cần chia theo từng ranh giới:

| Tầng | Công cụ | Điều chứng minh |
| --- | --- | --- |
| **JWT authentication** | JwtDecoder với JWT ký thật hoặc integration test Bearer HTTP | Chữ ký, issuer, audience và exp hợp lệ; token giả bị bác. |
| **ExternalIdentityResolver** | Unit test với mocked repositories | `(iss,sub)` tìm đúng local user; missing/conflict/disabled bị từ chối. |
| **Database constraints** | Repository/DB integration test | Unique `(issuer,subject)`, transaction linking và FK hoạt động. |
| **Endpoint authorization** | MockMvc + `jwt()` + service mocks | Scope, route và cách controller sử dụng principal đã xác thực. |
| **Resource authorization** | Service/integration test với orders/tenant data | Không đọc được tài nguyên của user hoặc tenant khác. |
| **Account linking flow** | OIDC Client/integration tests | Có bằng chứng quyền ở cả hai phía, state/nonce/PKCE/CSRF và xử lý conflict. |

### 15.1. Ma trận ca kiểm thử cốt lõi

| Tình huống | Kết quả mong đợi |
| --- | --- |
| JWT hợp lệ, cặp `(iss,sub)` có liên kết, local account ACTIVE | Resolve đúng `userId`; request tiếp tục xét quyền. |
| JWT hợp lệ nhưng `sub` không có liên kết | Không tự tạo/gán user; từ chối theo chính sách. |
| JWT hợp lệ từ issuer B có `sub` giống issuer A | Không dùng nhầm mapping issuer A. |
| JWT không có `sub` dù profile API yêu cầu | Bị bác ở token validation hoặc không được resolve, không cấp quyền. |
| JWT giả mạo `sub` của người khác, chữ ký sai | Bị bác trước khi lookup local account. |
| JWT đúng issuer nhưng audience dành cho API khác | Bị bác trước khi lookup local account. |
| Local account SUSPENDED nhưng JWT còn hạn | Từ chối truy cập cần ACTIVE. |
| Local account ACTIVE, token có scope nhưng order thuộc user khác | Từ chối truy cập tài nguyên. |
| Một `(iss,sub)` được link đồng thời tới hai user | Unique constraint bảo vệ; conflict không chuyển owner tự động. |
| Link identity mới qua email trùng mà chưa xác minh quyền | Không tự gộp tài khoản. |
| Client credentials token gọi endpoint dành cho end user | Không map thành user cá nhân; từ chối nếu không có user context hợp lệ. |
| Cache chứa mapping đã bị unlink hoặc status đã suspend | Invalidation/TTL/policy bảo đảm không còn cấp quyền ngoài dự kiến. |

### 15.2. Test service không cần JWT thật

Với `CurrentAccountService`, unit test có thể tạo một `Jwt` **giả lập đã xác thực** để tập trung vào logic tra cứu:

~~~java
import java.time.Instant;
import java.util.Map;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtFixtures {

    static Jwt userJwt(String issuer, String subject) {
        Instant now = Instant.now();

        return new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", issuer,
                "sub", subject,
                "aud", "orders-api"));
    }
}
~~~

Sau đó tạo mocked `ExternalIdentityRepository` và `AppUserRepository`, xác minh rằng service:

- Gọi `findByIssuerAndSubject` với **cả issuer và subject**.
- Không gọi tìm tài khoản theo email.
- Không tìm được mapping thì ném `AccessDeniedException`.
- User `SUSPENDED` thì từ chối dù mapping có tồn tại.
- User `ACTIVE` thì trả đúng `CurrentAccount.userId`.

Fixture trên dùng token và claims giả, **không kiểm tra chữ ký thật**; nó chỉ là dữ liệu đầu vào của service. Với JWT được decode thực, object `Jwt` và các claim getter có thể được chuẩn hóa bởi Spring Security; unit test phải phù hợp với API phiên bản đang dùng.

### 15.3. Test MockMvc `jwt()` không xác minh chữ ký

Ví dụ:

~~~java
mockMvc.perform(get("/api/me")
        .with(jwt()
            .jwt(j -> j.claim("iss",
                    "https://identity.example.test/realms/company")
                .claim("sub", "external-user-7812"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read"))))
    .andExpect(status().isOk());
~~~

Đây là minh họa **authorization với principal giả lập** và giả định service resolve tìm thấy local account phù hợp. `spring-security-test` tạo Authentication trực tiếp; **JwtDecoder không xác minh JWS thật** trong request này. Muốn chứng minh token sai issuer/audience/chữ ký bị bác, dùng integration test gửi **JWT được ký bằng khóa test** qua Bearer filter và decoder thực.

### 15.4. Kiểm thử transaction/linking

Tại tầng database nên thử:

~~~text
T1: link (issuer-A, sub-123) -> user-A  [SUCCESS]
T2: link (issuer-A, sub-123) -> user-B  [CONFLICT]
T3: link (issuer-B, sub-123) -> user-B  [TÙY POLICY, CÓ THỂ HỢP LỆ]
~~~

Nếu link T2 thất bại do unique constraint, service phải báo conflict an toàn, không update bản ghi T1. Đặc biệt cần thử concurrent requests (race) và hành vi idempotent nếu cùng user tạo liên kết lặp.

## 16. Các lỗi thiết kế dễ dẫn tới chiếm quyền

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Tra user chỉ bằng `sub`. | Hai issuer có thể trùng subject. | Khóa theo `(iss,sub)` và kiểm tra issuer JWT. |
| Tra user bằng email claim. | Email có thể đổi, tái sử dụng hoặc chưa xác minh. | Có linking/provisioning xác thực rõ, không auto-gộp bằng email. |
| Dùng `X-User-Id`/tenant header làm user đã xác thực. | Client tự chọn danh tính/quyền. | Lấy claims từ Authentication đã xác minh; đối chiếu domain policy. |
| Chỉ Base64url-decode JWT rồi tìm local user. | Chữ ký/issuer/audience có thể bị giả mạo. | Resource Server xác minh token trước. |
| Mặc định tạo AppUser khi mapping thiếu. | Có thể cấp account ngoài quy trình. | Chỉ JIT khi chính sách định nghĩa, có điều kiện và audit. |
| Tự đổi link sang user mới khi trùng unique key. | Chiếm liên kết đang thuộc user khác. | Từ chối conflict, xác minh và xử lý theo quy trình. |
| Đồng nhất `Authentication.getName()` với UUID nội bộ. | Principal ngoài không phải domain user ID. | Có resolver mapping tường minh. |
| Chỉ kiểm tra JWT còn hạn, bỏ qua local status. | User đã bị khóa vẫn truy cập bằng token cũ. | Kiểm tra trạng thái local và quyền hiện thời theo policy. |
| Giữ mapping/cache vô hạn. | Unlink/suspend không được phản ánh. | TTL/invalidation và nhất quán phân quyền. |
| Dùng `client_id` làm user trong mọi token. | Service token bị hiểu là user token. | Phân biệt human principal, client principal và delegation. |
| Link chỉ vì `email_verified=true`. | Không chứng minh quyền chiếm local account. | Chứng minh quyền ở cả hai phía bằng flow bảo mật. |
| Log JWT/email/subject trên mọi request. | Rò rỉ credential và định danh cá nhân. | Log loại lỗi, request ID, audit có giới hạn truy cập. |

## 17. Cách đọc đúng các lỗi 401, 403 và trạng thái onboarding

### 17.1. Token invalid: 401

Khi JWT không có hoặc không hợp lệ về chữ ký, issuer, audience, thời hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Đây là lỗi **authentication**, thông thường phải được xử lý bởi Spring Security ở filter chain. Không cho request vào account resolution khi credential chưa được xác thực.

### 17.2. Token valid nhưng local account không được phép: thường 403

Nếu JWT hợp lệ nhưng user chưa liên kết, account `SUSPENDED` hoặc thiếu quyền domain, API có thể:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"account_unavailable","message":"Không thể sử dụng tài khoản cho thao tác này."}
~~~

Đây là ví dụ chính sách; với sản phẩm có onboarding hợp lệ, một endpoint riêng có thể trả trạng thái hướng dẫn hoàn tất đăng ký theo hợp đồng HTTP của API. **Không** mặc định biến token hợp lệ thành 401 chỉ vì thiếu local row, và cũng không trả thông tin quá chi tiết giúp người khác liệt kê account đang tồn tại/đã bị khóa.

Khi xử lý lỗi `AccessDeniedException` được ném từ controller/service, hành vi HTTP phụ thuộc method security, filter/exception handling và cấu hình ứng dụng; cần có integration test bảo đảm trả status mong đợi. Đừng giả định mọi exception trong controller sẽ được cùng một handler xử lý giống lỗi phát sinh ngay trong Bearer filter.

### 17.3. Tránh lộ identity mapping trong lỗi

Không trả:

~~~json
{
  "error": "External sub external-user-7812 belongs to user 2f8a..."
}
~~~

Thay bằng thông báo trung tính cho client và audit nội bộ có quyền truy cập hạn chế. Bảo vệ `Authorization` header, JWT và dữ liệu nhận dạng theo nguyên tắc tối thiểu cần thiết.

## 18. Quy trình triển khai theo từng bước

1. **Xác định nhu cầu nghiệp vụ.** Nếu API không cần local account, chỉ dùng claims/authorities phù hợp; nếu có dữ liệu gắn user, xác định domain user ID.
2. **Thống nhất identity contract.** Xác minh JWT Access Token, issuer đáng tin, audience API, chủ thể `sub` và loại principal con người hay service.
3. **Thiết kế mapping riêng.** Dùng `external_identity(issuer, subject, user_id)` với uniqueness và FK; local `app_user.id` độc lập với IdP.
4. **Định nghĩa quyền tạo/sửa liên kết.** Pre-provisioning, SCIM, invite, linking hoặc JIT theo policy; không link tự động chỉ bằng email.
5. **Triển khai account resolver sau authentication.** Lấy `iss/sub` từ `Jwt` đã xác thực, lookup mapping, kiểm tra user status và trả context nghiệp vụ tối thiểu.
6. **Áp authorization theo tài nguyên.** Kết hợp scope của token với trạng thái local, tenant membership, ownership và policy cụ thể.
7. **Xây quy trình lifecycle.** Suspend, unlink, đổi IdP, rotation/migration mapping, audit và invalidation cache khi quyền thay đổi.
8. **Kiểm thử các trường hợp thất bại.** Sai issuer nhưng trùng sub, mapping thiếu, tài khoản bị khóa, scope thiếu, sai owner/tenant, race linking và service token gọi endpoint user.
9. **Bảo vệ dữ liệu và quan sát.** Không log Bearer token; hạn chế truy cập identity links; chuẩn hóa phản hồi 401/403 và kiểm soát audit.

**Ghi nhớ:** **Spring Security Resource Server** chứng minh một Access Token hợp lệ và cung cấp principal ngoài. **Ứng dụng nghiệp vụ** mới quyết định principal đó có tương ứng với tài khoản nội bộ nào, còn active không và có quyền trên tài nguyên hay không. Khi cần ánh xạ, dùng danh tính đã được xác thực **`(iss, sub)`**, liên kết được tạo bằng **quy trình có kiểm soát**, và giữ **local user ID** độc lập với nhà cung cấp danh tính.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html).
- [Spring Security — OAuth 2.0 Login / OpenID Connect Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OpenID Connect Core 1.0 — Subject Identifier](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes).
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
