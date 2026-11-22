# Nhầm `ROLE_` với `SCOPE_` và ánh xạ quyền rộng hơn dữ liệu nguồn

## 1. Lỗ hổng cần nhận diện

Trong Spring Security, hệ thống có thể **xác thực JWT đúng** nhưng **cấp quyền sai** nếu chuyển các claim của token thành `GrantedAuthority` không đúng ý nghĩa. Sai lầm thường gặp là lấy OAuth 2.0 scope như `documents.read` hoặc `ADMIN` rồi tạo authority dạng `ROLE_...`, hoặc lấy một role tổng quát như `USER` làm bằng chứng rằng người gọi có quyền đọc, sửa, xóa tất cả tài liệu.

Ví dụ: authorization server phát hành access token hợp lệ với `scope: "ADMIN"` theo một quy ước OAuth riêng (tên scope không chứng minh người mang token là quản trị viên ứng dụng). Resource server cấu hình `JwtGrantedAuthoritiesConverter#setAuthorityPrefix("ROLE_")`. Sau chuyển đổi, token mang `ROLE_ADMIN`; một endpoint bảo vệ bằng `hasRole("ADMIN")` có thể được truy cập. **Quyền quản trị xuất hiện từ phép đổi tiền tố, trong khi nguồn token chỉ cấp một scope.**

Tình huống khác phổ biến hơn: token có `scope: "documents.read"`, nhưng code ứng dụng tự cộng `ROLE_EDITOR` cho mọi người dùng đăng nhập. Endpoint `DELETE` chỉ kiểm `hasRole("EDITOR")`, nên access token chỉ dành cho đọc được phép xóa. Cả hai lỗi đều là **privilege escalation do authority mapping hoặc authorization policy**, không nhất thiết là lỗi chữ ký JWT.

**Mục tiêu học:** phân biệt role, scope, authority; theo dõi luồng claim → converter → authority → policy; nhận diện phép ánh xạ tạo quyền rộng hơn nguồn; cấu hình và kiểm thử để quyền cuối cùng phản ánh đúng chính sách đã xác minh.

## 2. Phân biệt ba khái niệm, tránh nhầm tên với quyền

| Khái niệm | Nguồn/ngữ nghĩa điển hình | Ví dụ | Ý nghĩa trong Spring Security |
| --- | --- | --- | --- |
| OAuth 2.0 **scope** | Phạm vi quyền được cấp cho access token của một client, theo hợp đồng với authorization server và resource server | `documents.read`, `documents.write` | Với JWT resource server mặc định, thường thành `SCOPE_documents.read`, `SCOPE_documents.write` |
| Ứng dụng **role** | Vai trò do hệ thống đích hoặc nguồn được ủy thác đáng tin cậy định nghĩa | `READER`, `EDITOR`, `ADMIN` | Thường biểu diễn bằng `ROLE_READER`, `ROLE_EDITOR`, `ROLE_ADMIN`; JWT không tự động tạo các role này nếu chưa cấu hình |
| Spring Security **GrantedAuthority** | Chuỗi đại diện cho một quyền mà policy có thể kiểm tra | `SCOPE_documents.read`, `ROLE_EDITOR`, `invoice:approve` | `hasAuthority("...")` so khớp authority; tiền tố chỉ có nghĩa khi converter/policy thống nhất quy ước |

**Tiền tố không phải bằng chứng quyền:** `ROLE_` và `SCOPE_` đều là phần của chuỗi `GrantedAuthority`; Spring Security không tự bảo đảm rằng `ROLE_ADMIN` thật sự đến từ một role quản trị tin cậy. Nơi tạo authority quyết định độ tin cậy của nó.

Trong cấu hình mặc định phổ biến:

- `hasAuthority("SCOPE_documents.read")` yêu cầu **đúng chuỗi** đó.
- `hasAuthority("ROLE_ADMIN")` yêu cầu **đúng chuỗi** đó.
- `hasRole("ADMIN")` là cú pháp rút gọn tìm `ROLE_ADMIN` khi dùng tiền tố role mặc định `ROLE_`. Nó **không đọc claim `roles` hay `scope` trực tiếp**.
- `hasRole("SCOPE_documents.read")` không phải cách kiểm scope; với tiền tố mặc định nó sẽ tìm `ROLE_SCOPE_documents.read`.
- `hasRole("ROLE_ADMIN")` không phải cách dùng chuẩn ở nơi API đã tự thêm tiền tố. Hãy truyền tên role `ADMIN`, hoặc dùng `hasAuthority("ROLE_ADMIN")`.
- Một ứng dụng có thể đổi tiền tố role mặc định; vì vậy khi review hãy xác minh **cấu hình thật**, nhưng đừng thay tiền tố để che lỗi phân loại quyền.

Ví dụ JWT được dùng trong các mục dưới là **payload minh họa**; không tự coi JSON này là token được ký hợp lệ:

~~~json
{
  "iss": "https://login.example.org",
  "aud": ["documents-api"],
  "sub": "alice",
  "scope": "documents.read",
  "app_roles": ["READER"],
  "tenant_id": "A"
}
~~~

Nếu converter được cấu hình theo đúng hợp đồng: `scope` tạo `SCOPE_documents.read`; `app_roles` (nếu đây là claim role do issuer đáng tin cậy kiểm soát) tạo `ROLE_READER`. `tenant_id` chỉ là dữ kiện để policy phạm vi dữ liệu kiểm chứng, không tự cấp quyền trên mọi tài liệu thuộc A.

## 3. Luồng thực thi: bug xuất hiện tại đâu?

~~~text
Authorization Server (đã xác định scopes/claims)
      |
      v
Access token (scope, scp, app_roles, aud, sub, ...)
      |
      v
JwtDecoder: xác minh chữ ký, thời hạn, issuer và validators cần thiết
      |
      v
JwtAuthenticationConverter / JwtGrantedAuthoritiesConverter
      |           (điểm có thể nâng scope thành role sai)
      v
Authentication.getAuthorities(): tập chuỗi GrantedAuthority
      |
      v
authorizeHttpRequests / @PreAuthorize / AuthorizationManager
      |
      v
Kiểm tra tài nguyên cụ thể: tenant, owner, membership, ACL
      |
      v
ALLOW hoặc DENY
~~~

Spring Security OAuth 2.0 resource server JWT mặc định đọc scope từ claim phổ biến như `scope` hoặc `scp` và thêm tiền tố `SCOPE_`. Chẳng hạn `scope: "documents.read documents.write"` thường trở thành hai authority `SCOPE_documents.read` và `SCOPE_documents.write`. Không mặc định biến chúng thành `ROLE_...`. Khi cấu hình `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName(...)` hoặc `setAuthorityPrefix(...)`, bạn đang chủ động thay quy tắc này.

**Hai quyết định khác nhau** cần được bảo vệ:

1. *Authority mapping*: nguồn dữ liệu/token có thực sự cho phép sinh từng authority không?
2. *Authorization*: endpoint hoặc thao tác nghiệp vụ có đòi đúng các authority **và** đúng quyền trên đối tượng dữ liệu không?

Sai ở bước 1 làm nhiều endpoint tin nhầm người dùng. Sai ở bước 2 có thể cho phép dùng authority hợp lệ nhưng quá rộng, ví dụ chỉ cần `ROLE_USER` để xóa mọi hóa đơn.

## 4. Bảng đối chiếu các trường hợp dễ nhầm

Giả định tiền tố role mặc định là `ROLE_` và resource server dùng converter scope mặc định trừ khi ghi rõ.

| Token/authority đầu vào | Authority có thể xuất hiện | Kiểm tra policy | Kết quả và lý do |
| --- | --- | --- | --- |
| `scope: "documents.read"` | `SCOPE_documents.read` | `hasAuthority("SCOPE_documents.read")` | Đúng: cho phép theo scope |
| `scope: "documents.read"` | `SCOPE_documents.read` | `hasRole("READER")` | Sai: không có `ROLE_READER` |
| `scope: "ADMIN"` | `SCOPE_ADMIN` | `hasRole("ADMIN")` | Sai theo converter mặc định: không có `ROLE_ADMIN` |
| `scope: "ADMIN"` + **converter sai dùng `ROLE_`** | `ROLE_ADMIN` | `hasRole("ADMIN")` | **Lỗ hổng** nếu scope ADMIN không có ngữ nghĩa role admin |
| Claim role đáng tin `app_roles:["EDITOR"]` + converter role riêng | `ROLE_EDITOR` | `hasRole("EDITOR")` | Đúng khi nguồn, audience và ý nghĩa role đã được xác minh |
| Chỉ có `ROLE_USER` từ app login | `ROLE_USER` | `hasAuthority("SCOPE_documents.delete")` | Sai: một role không tự cấp scope xóa |
| `SCOPE_documents.delete` nhưng tài liệu thuộc tenant B | `SCOPE_documents.delete` | Scope check qua; object-policy từ chối | Đúng: scope không đủ để vượt ranh giới tenant |

Chú ý: OAuth scope là chuỗi do **hợp đồng giữa issuer và resource server** định nghĩa. Một từ trùng tên role, ví dụ `ADMIN`, không mặc nhiên có cùng nghĩa. Ngược lại, một claim tên `roles` cũng chưa chắc là quyền quản trị cục bộ: có thể là realm role, role của client khác, nhóm tự gán hoặc metadata không dành cho API này.

## 5. Những cách ánh xạ quyền rộng hơn nguồn và hậu quả

### 5.1. Đổi toàn bộ OAuth scopes thành `ROLE_...`

Mảnh cấu hình **có thể chạy nhưng nguy hiểm khi nguồn là OAuth scopes**:

~~~java
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
scopes.setAuthorityPrefix("ROLE_"); // Sai ngữ nghĩa: scope -> role!

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(scopes);
~~~

API cho phép đặt tiền tố tùy ý, nhưng ở đây việc chuyển `scope=ADMIN` sang `ROLE_ADMIN` vô tình đáp ứng `hasRole("ADMIN")`. Khả năng cấu hình được không đồng nghĩa với ánh xạ an toàn. **Không đổi prefix vì thấy route đang dùng `hasRole` mà bị từ chối**; phải sửa route về kiểm scope hoặc tách nguồn roles chính danh.

### 5.2. Tạo role ngầm từ một scope hoặc chỉ vì đã đăng nhập

Ví dụ anti-pattern:

~~~java
// Minh họa lỗi: mọi access token hợp lệ đều nhận vai trò ghi.
if (authentication.isAuthenticated()) {
    authorities.add(new SimpleGrantedAuthority("ROLE_EDITOR"));
}
~~~

Nếu `ROLE_EDITOR` cho phép ghi/xóa, token chỉ được phát scope đọc cũng có quyền ghi/xóa. Tương tự, ánh xạ `documents.read` → `ROLE_EDITOR`, hoặc `SCOPE_*` → `ROLE_ADMIN` là mở rộng quyền không có căn cứ. `authenticated()` chỉ xác định trạng thái đăng nhập, không thay thế quyền thao tác.

### 5.3. Trộn role/scope thành một namespace rồi dùng điều kiện OR

~~~java
// Minh họa lỗi: role chung USER đủ để xóa, dù thiếu scope xóa.
@PreAuthorize("hasAuthority('SCOPE_documents.delete') or hasRole('USER')")
public void deleteDocument(long id) { /* ... */ }
~~~

`or` làm một trong hai điều kiện đủ để vào method; `hasAnyAuthority(...)` cũng là kiểm “ít nhất một”. Nếu đặc tả yêu cầu **cả scope xóa và quyền dữ liệu cụ thể**, phải dùng điều kiện AND và policy đối tượng. Một role tổng quát không thay được scope chuyên biệt.

### 5.4. Tin một claim role từ sai nguồn hoặc sai audience

Một access token cấp cho service X có thể mang vai trò `ADMIN` của **X**, không phải của documents API. Nếu service Y đọc mọi claim `roles`/`groups` rồi tạo `ROLE_ADMIN` nội bộ, người dùng có thể được nâng quyền tại Y. Cần giới hạn issuer hợp lệ, audience đích, loại token, nguồn claim, tên/namespace và ý nghĩa role theo hợp đồng. Không lấy role từ HTTP header, query, local storage, hoặc JWT chưa xác minh chữ ký.

Ngay cả JWT đã ký vẫn có thể chứa dữ liệu mà issuer lấy từ profile người dùng tự sửa hoặc từ client đăng ký. Ký số xác minh tính toàn vẹn và nguồn phát hành; **không chứng minh claim đó đủ tin cậy để làm quyền quản trị ứng dụng**.

### 5.5. Mở rộng bằng hierarchy hoặc phép gộp không kiểm soát

Role hierarchy như `ROLE_ADMIN > ROLE_EDITOR > ROLE_READER` có thể hợp lệ. Tuy nhiên một converter vô tình tạo `ROLE_ADMIN` từ scope sẽ khiến lỗi lan sang mọi quyền kế thừa. Gộp authorities từ nhiều nguồn bằng `DelegatingJwtGrantedAuthoritiesConverter` hoặc mapper tùy biến chỉ nên thực hiện sau khi đã kiểm trust boundary và contract của **từng nguồn**; phép union không tự chứng minh rằng quyền được gộp là đúng.

Các phép chuẩn hóa `toUpperCase()`, loại prefix, wildcard như `SCOPE_documents.*`, split claim sai delimiter hoặc gom toàn bộ role vào `ADMIN` cũng cần kiểm thử. Nếu chính sách không công bố wildcard thì chuỗi `documents.*` phải được đối xử như một giá trị bình thường, không tự cấp tất cả thao tác.

### 5.6. Endpoint bị bảo vệ quá rộng dù converter đúng

~~~java
// Ví dụ policy không đủ: mọi user đăng nhập đều có thể gọi endpoint ghi.
.requestMatchers(HttpMethod.DELETE, "/api/documents/**").authenticated()
~~~

Chính sách này không yêu cầu scope xóa. Một request chỉ có token đọc vẫn đi qua đường HTTP nếu không có chốt kiểm khác. Tương tự, `anyRequest().authenticated()` hoặc `permitAll()` trên route nhạy cảm, pattern matcher sai thứ tự và method chưa có `@PreAuthorize` đều có thể bỏ lọt thao tác.

### 5.7. Có scope đúng nhưng thiếu kiểm tra phạm vi dữ liệu

`SCOPE_documents.read` cho phép **thử thực hiện** thao tác đọc theo hợp đồng, không chứng minh quyền đọc mọi `documentId` hoặc tenant. Nếu `GET /api/documents/B-202` chỉ kiểm scope rồi `findById("B-202")`, actor thuộc tenant A có thể đọc dữ liệu B. Policy cần kiểm `tenant`, ownership/ACL, trạng thái tài nguyên và quyền hiện hành tại tầng service/query.

## 6. Minh họa đường tấn công từ token đến endpoint

Giả định ứng dụng có hai endpoint: `GET /api/documents/{id}` đòi `documents.read`; `DELETE /api/documents/{id}` đòi `documents.delete` và policy sở hữu.

**Hợp đồng mong đợi:** token của Alice chỉ có `scope: "documents.read"`, không có `documents.delete`. Kể cả Alice thuộc tenant A, cô ấy không thể xóa tài liệu A-101 và càng không thể xóa B-202.

**Luồng lỗi 1 — tự thêm vai trò:**

1. Alice nhận access token chỉ có `documents.read`.
2. Converter nội bộ luôn thêm `ROLE_EDITOR` cho principal đã xác thực.
3. Delete endpoint dùng `hasRole("EDITOR")`, bỏ qua yêu cầu `documents.delete`.
4. Request xóa A-101 được chấp nhận dù token gốc không có quyền xóa. Nếu endpoint đồng thời thiếu object-policy, B-202 cũng có nguy cơ bị xóa.

**Luồng lỗi 2 — nhầm tiền tố:**

1. Issuer phát một OAuth scope tên `ADMIN` để kiểm một tác vụ riêng.
2. Converter dùng `setAuthorityPrefix("ROLE_")` cho mọi scope.
3. Runtime thấy `ROLE_ADMIN` và `hasRole("ADMIN")` trả true.
4. Bất kỳ route nào cho phép quản trị qua authority đó có thể bị mở rộng.

**Luồng đúng:** JWT được validate đúng issuer/audience; scope thành `SCOPE_documents.read`; role chỉ lấy từ nguồn role tin cậy; delete yêu cầu `SCOPE_documents.delete` và kiểm quyền trên document ID. Alice nhận `403` (hoặc mã từ chối thống nhất trong hợp đồng) khi thiếu scope xóa; request không có side effect. Với một ID ngoài phạm vi, nhiều API dùng `404` để tránh lộ sự tồn tại, miễn được áp dụng nhất quán.

## 7. Cấu hình Spring Security: tách rõ nguồn scopes và roles

Ví dụ sau áp dụng cho **Servlet + JWT resource server** trong Spring Security 6.x/7.x, với Java 17+; cần các dependency Spring Security web, OAuth2 resource server/Jose và cấu hình `JwtDecoder`/issuer hợp lệ trong ứng dụng. Đây là **đoạn cấu hình tích hợp Spring**, không phải chương trình Java chạy độc lập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();
        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        // Chỉ bật nếu issuer/audience và app_roles là nguồn role tin cậy.
        JwtGrantedAuthoritiesConverter appRoles =
            new JwtGrantedAuthoritiesConverter();
        appRoles.setAuthoritiesClaimName("app_roles");
        appRoles.setAuthorityPrefix("ROLE_");

        var authorities =
            new DelegatingJwtGrantedAuthoritiesConverter(scopes, appRoles);

        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, JwtAuthenticationConverter jwtConverter)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.read")
            .requestMatchers(HttpMethod.POST,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.write")
            .requestMatchers(HttpMethod.DELETE,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.delete")
            .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
        );
        return http.build();
    }
}
~~~

Giải thích từng quyết định:

1. `scopes.setAuthoritiesClaimName("scope")` định danh đúng claim nguồn. Nếu issuer dùng `scp` dạng collection, phải điều chỉnh theo hợp đồng và kiểm thử chính xác cấu trúc; không mặc định gộp tùy tiện cả hai.
2. `scopes.setAuthorityPrefix("SCOPE_")` giữ ranh giới scope.
3. `appRoles` chỉ nên chạy khi `app_roles` thực sự do issuer tin cậy phát cho **documents API** và role này có nghĩa trong ứng dụng. Nếu không có nguồn role đáng tin, **bỏ hoàn toàn converter role** và chỉ dùng scope + policy nghiệp vụ.
4. `DelegatingJwtGrantedAuthoritiesConverter` gộp authorities từ hai converter; việc gộp **không bổ sung cơ chế xác thực nguồn**. Phải validate token trước khi dùng converter.
5. `jwt.jwtAuthenticationConverter(jwtConverter)` nối converter vào resource server; viết `@Bean` mà quên nối vào đúng filter chain có thể khiến runtime vẫn chạy converter khác.
6. HTTP rule yêu cầu scope đúng với HTTP method. Hệ thống thực tế phải xét cả các endpoint PATCH/PUT, export, batch, async và API khác, không dựa vào `anyRequest().authenticated()` làm default rộng. `denyAll()` trong ví dụ là default thận trọng cho đường chưa khai báo.
7. Route rule vẫn là kiểm soát coarse-grained. Trước khi đọc/ghi một tài liệu, service phải kiểm object-level policy, ví dụ `canRead(actor, document)` hoặc truy vấn repository ràng buộc tenant, owner và quyền. Method security đặt trong bean Spring được gọi qua proxy khi dùng `@PreAuthorize`.

Ví dụ kiểm **scope và dữ liệu** ở method security (mảnh mã minh họa, yêu cầu bean policy thực trong ứng dụng):

~~~java
@Service
class DocumentService {
    private final DocumentPolicy policy;
    private final DocumentRepository repository;

    DocumentService(DocumentPolicy policy, DocumentRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.delete')")
    @Transactional
    public void delete(long documentId, Authentication actor) {
        // Policy phải dùng principal/tenant đã xác minh, không tin tenantId do client gửi.
        policy.requireCanDelete(actor, documentId);
        repository.deleteById(documentId);
    }
}
~~~

Bổ sung import `@Service`, `@Transactional`, `@PreAuthorize`, `Authentication` và hai collaborator theo project. `DocumentPolicy#requireCanDelete` phải từ chối khi actor không có quyền trên record. Để tránh race/TOCTOU giữa kiểm và xóa, với dữ liệu nhạy cảm hãy cân nhắc truy vấn DELETE/UPDATE có predicate scope trong transaction, row locking hoặc RLS và kiểm số dòng thực sự tác động. Nếu business contract còn yêu cầu role, ví dụ role quản lý thuộc **đúng tenant**, thêm điều kiện đã được phê duyệt; không tự cho `ROLE_ADMIN` bỏ qua scope/object policy.

### Đặt nguồn sự thật và giới hạn tin cậy

- Token issuer phải được tin cậy; validate chữ ký, `iss`, `exp`, `nbf`. Validate `aud` **cho API hiện tại** theo threat model; chỉ `issuer-uri` không có nghĩa tự động kiểm đúng audience ứng dụng mong đợi trong mọi cấu hình.
- `scp`/`scope` là OAuth authorization; `app_roles` là role ứng dụng nếu có hợp đồng. Bất kỳ claim nào có thể do end user/client kiểm soát gián tiếp phải được xem xét trước khi cấp authority nhạy cảm.
- Không phân quyền theo giá trị chỉ decode từ token chưa xác minh, không lấy role từ `X-Role`/`X-Tenant` do client gửi và không nhận danh sách authorities từ request body.
- Không thêm quyền khi claim rỗng, sai kiểu, sai audience, có ký tự bất thường hoặc thiếu role. Hành vi đúng là từ chối hoặc không phát sinh authority nhạy cảm (**fail closed**).
- Quyền ở token có thể lỗi thời khi role/membership đã bị thu hồi. Với thao tác quan trọng, cân nhắc token ngắn hạn, revocation/introspection hoặc kiểm trạng thái policy hiện tại tại server.

## 8. Ví dụ Java 17+ độc lập: một phép đổi prefix tạo ra `ROLE_ADMIN`

Chương trình sau mô phỏng phần mapping của chính ứng dụng để quan sát hậu quả **mà không cần Spring Boot**. Đây là bài tập về ngữ nghĩa authority: `safe` chỉ đưa các scope được công nhận vào namespace `SCOPE_` và role `READER` vào namespace `ROLE_`; `unsafe` biến mọi scope thành role. Whitelist minh họa tùy thuộc hợp đồng của từng hệ thống; code này không xác minh JWT, issuer hay quyền dữ liệu thực.

Lưu thành `AuthorityMappingDemo.java`, chạy:

~~~bash
javac AuthorityMappingDemo.java
java AuthorityMappingDemo
~~~

Toàn bộ mã nguồn:

~~~java
import java.util.*;

public class AuthorityMappingDemo {
    record Claims(List<String> scopes, List<String> appRoles) {}

    static Set<String> safe(Claims c) {
        Set<String> out = new LinkedHashSet<>();
        Set<String> permittedScopes = Set.of("documents.read", "documents.write");
        for (String scope : c.scopes()) {
            if (permittedScopes.contains(scope)) out.add("SCOPE_" + scope);
        }
        for (String role : c.appRoles()) {
            if (role.equals("READER")) out.add("ROLE_" + role);
        }
        return out;
    }

    static Set<String> unsafe(Claims c) {
        Set<String> out = new LinkedHashSet<>();
        for (String scope : c.scopes()) out.add("ROLE_" + scope);
        return out;
    }

    public static void main(String[] args) {
        Claims reader = new Claims(List.of("documents.read"), List.of("READER"));
        System.out.println("safe = " + safe(reader));
        System.out.println("can-read = " + safe(reader).contains("SCOPE_documents.read"));
        System.out.println("can-write = " + safe(reader).contains("SCOPE_documents.write"));

        Claims unusual = new Claims(List.of("ADMIN"), List.of());
        System.out.println("unsafe = " + unsafe(unusual));
        System.out.println("unsafe-admin = " + unsafe(unusual).contains("ROLE_ADMIN"));
        System.out.println("safe-admin = " + safe(unusual).contains("ROLE_ADMIN"));
    }
}
~~~

Stdout:

~~~text
safe = [SCOPE_documents.read, ROLE_READER]
can-read = true
can-write = false
unsafe = [ROLE_ADMIN]
unsafe-admin = true
safe-admin = false
~~~

Giải thích: cùng một scope `ADMIN`, `unsafe` tự tạo `ROLE_ADMIN`; `safe` không tạo role admin vì nguồn `appRoles` không cấp nó. Tập `safe` vẫn chỉ mô phỏng bước mapping; ở production, cả scope và role phải được phát hành bởi nguồn có thẩm quyền phù hợp và được kiểm tại resource/method cụ thể.

## 9. Kiểm thử để bắt đúng lỗi thay vì chỉ kiểm HTTP status

Tạo bộ token/fixture có ít nhất: user Alice ở tenant A; admin hợp lệ của A; user Bob ở tenant B; token chỉ có scope đọc; token có scope ghi; token có scope tên giống role (`ADMIN`) nhưng không có app role; token có app role không có scope xóa; token sai issuer/audience; token không có scope/roles; token với claim sai cấu trúc.

### Ma trận test

| Token/actor | Kết quả authority dự kiến | GET documents | DELETE documents | Kết quả trên document B |
| --- | --- | --- | --- | --- |
| Alice: `documents.read`, `READER`, thuộc A | `SCOPE_documents.read`, `ROLE_READER` | Được đọc đối tượng A theo policy | Từ chối (thiếu scope delete) | Từ chối theo object policy |
| Alice: `documents.delete`, không có app role, thuộc A | Chỉ `SCOPE_documents.delete` | Từ chối nếu thiếu scope read | Chỉ cho phép nếu policy dữ liệu cho phép | Từ chối khi tài liệu thuộc B |
| Token có OAuth scope `ADMIN`, không có role | `SCOPE_ADMIN` (nếu scope hợp lệ với hợp đồng) | Không tự có scope read | Không tự có scope delete hay admin role | Từ chối |
| Admin thật: `documents.delete` + role hợp lệ theo chính sách | `SCOPE_documents.delete` + `ROLE_ADMIN` nếu nguồn trusted | Theo scope read | Theo policy, trong phạm vi được cấp | Không vượt tenant trừ quyền đặc biệt được định nghĩa rõ |
| Token sai issuer/audience hoặc không hợp lệ | Không tạo `Authentication` đáng tin | `401` thông thường | `401` thông thường | Không truy cập dữ liệu |
| Token thiếu claim cần thiết | Không tạo authority quyền thao tác | Từ chối thao tác cần scope | Từ chối thao tác cần scope | Không truy cập dữ liệu |

Status code cụ thể còn phụ thuộc hợp đồng API: access token thiếu/không hợp lệ thường `401`; đã xác thực nhưng thiếu authority thường `403`; resource ngoài phạm vi có thể `404` để tránh lộ tồn tại. Test phải đối chiếu chính sách đã công bố và xác nhận **không có thay đổi dữ liệu** khi bị từ chối.

### Kiểm thử converter trực tiếp

Trong ứng dụng có bean `JwtAuthenticationConverter` ở mục 7, ví dụ JUnit 5 + AssertJ dưới đây kiểm ánh xạ bằng một `Jwt` *dựng trong bộ test*, không cần JWT ký thật. Đây là **test snippet**, dùng dependency `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose` và các import theo project.

~~~java
@Test
void readScopeMustNotBecomeAdminRole() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("scope", "documents.read")
        .claim("app_roles", List.of("READER"))
        .build();

    JwtAuthenticationConverter converter = jwtAuthenticationConverter();
    var auth = converter.convert(jwt);

    assertThat(auth.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains("SCOPE_documents.read", "ROLE_READER")
        .doesNotContain("ROLE_ADMIN", "SCOPE_documents.delete");
}
~~~

Test tiếp với `scope: "ADMIN"` và **không có** `app_roles`: assert `ROLE_ADMIN` không xuất hiện. Kiểm cả `scp` dạng danh sách, missing claim, empty string, duplicate, delimiter có khoảng trắng, ký tự lạ, role ngoài whitelist và case-sensitive match theo hợp đồng IdP. Nếu converter custom tạo bất cứ authority nguy hiểm nào mà claim nguồn không cấp, test phải thất bại.

### Test HTTP + policy, không dựa hoàn toàn vào mock authority

`spring-security-test` hỗ trợ `MockMvc` với `jwt()`, ví dụ:

~~~java
mvc.perform(delete("/api/documents/{id}", 101L)
        .with(jwt().jwt(j -> j
            .subject("alice")
            .claim("scope", "documents.read"))
            .authorities(new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isForbidden());
~~~

Đoạn trên là **mảnh mã test tích hợp**: cần `MockMvc`, fixture, static import và route thực. Với ứng dụng bật CSRF cho state-changing request, cung cấp CSRF token hợp lệ để tránh test đi qua tầng CSRF thay vì kiểm scope. Khi gửi `jwt().authorities(...)`, bạn **chủ động cấp authorities trong bộ test**; điều này chỉ kiểm behavior sau khi authorities đã có, **không chứng minh converter JWT runtime thực tế đúng**. Cần unit test converter riêng và integration test với bearer token thật/decoder phù hợp để xác minh wire-up, issuer, audience và chữ ký.

Test đầy đủ nên có:

1. **Converter contract:** đúng danh sách authorities cho token chỉ đọc, chỉ ghi, role chính danh, role/scope tên trùng nhau, claim rỗng và claim không mong đợi. Dùng exact expected/forbidden authority, không chỉ kiểm số lượng.
2. **Request authorization:** `GET`, `POST`, `PATCH`, `DELETE` và các endpoint export/bulk yêu cầu scope riêng; token chỉ đọc không được ghi hoặc xóa. Chỉ có `ROLE_USER` không đủ để đi qua `hasAuthority("SCOPE_documents.delete")`.
3. **Object authorization:** cùng token đúng scope nhưng truy cập document tenant B phải bị từ chối. Kiểm cả repository rows, soft-delete, version, event/outbox sau denial.
4. **Token trust:** signed token sai issuer, sai audience, hết hạn, signature invalid, role claim sai nguồn bị loại. Test mã lỗi và không sinh context có quyền.
5. **Method security và proxy:** method nhạy cảm được gọi qua bean Spring để `@PreAuthorize` thực sự chạy. Gọi nội bộ qua `this.method()` có thể bỏ qua AOP interception; dùng service boundary phù hợp.
6. **Regression khi đổi cấu hình:** chạy lại matrix khi chỉnh `JwtGrantedAuthoritiesConverter`, `GrantedAuthoritiesMapper`, role hierarchy, custom authentication provider, IdP claim mapping và default role prefix.
7. **Kiểm dấu hiệu mở rộng quyền:** với token chỉ đọc, bất kỳ `ROLE_ADMIN`, `ROLE_EDITOR`, `SCOPE_documents.write` hoặc `SCOPE_documents.delete` nào ngoài hợp đồng đều phải làm test thất bại, kể cả endpoint hiện chưa sử dụng chúng.

Một **negative test** bị từ chối đơn lẻ chưa đủ: endpoint luôn trả `403` cũng qua test. Luôn có **positive control** cùng endpoint bằng token có permission và object scope đúng để chứng minh policy thực sự hoạt động.

## 10. Cách audit, sửa và ngăn tái diễn trong dự án hiện hữu

Bắt đầu từ hợp đồng quyền thực tế rồi theo dấu đến code; không sửa mù quáng một prefix để “cho test qua”:

1. **Liệt kê thao tác và quyền:** tạo matrix `endpoint/method → required scope → required app role (nếu có) → object/data policy`. Phân biệt rõ các permission đọc, sửa, xóa, xuất, quản trị.
2. **Ghi nhận nguồn claim:** issuer, audience, token type, `scope`/`scp`, claim role và bên có quyền cấp từng giá trị. Với Keycloak, Auth0 hoặc IdP khác, tên claim/namespace có thể khác nhau; không giả định `realm_access.roles`, `resource_access` hoặc `groups` đồng nghĩa quyền của API hiện tại.
3. **Truy nguồn tạo authority:** kiểm `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `setAuthorityPrefix`, `setAuthoritiesClaimName`, `GrantedAuthoritiesMapper`, custom filter, `UserDetailsService`, role hierarchy và code tự thêm `SimpleGrantedAuthority`. Tìm mọi phép mở rộng không được hợp đồng cho phép.
4. **Sửa phép ánh xạ:** giữ OAuth scope trong namespace scope; chỉ map app roles từ nguồn được phê duyệt và giới hạn tên/capability. Khi nguồn role không đáng tin, loại bỏ mapping đó; cần quyền nội bộ thì tra cứu policy tại server bằng principal đã xác thực.
5. **Sửa policy gọi tài nguyên:** route yêu cầu đúng scope theo HTTP method; service/DB kiểm owner, tenant, membership, ACL, quyền cập nhật. Không thay object check bằng `hasRole("ADMIN")` chung chung nếu không có chính sách cross-tenant rõ ràng.
6. **Thêm regression test:** chứng minh trước–sau cho token chỉ đọc, token có scope tên giống role, token app role sai nguồn, tenant B, job nền, export. Assert không có side effect và log/audit không rò token thô.
7. **Triển khai có quan sát:** rà soát các client đang phụ thuộc hành vi sai; cập nhật token contract/issuer nếu cần; đo request denied bất thường bằng metric an toàn. Không bật fallback cấp quyền để tránh lỗi 403 hàng loạt.

Với API vận hành thực tế, cần thống nhất owner của `ROLE_*` và `SCOPE_*`; việc đặt tên authority phải được code review như chính sách bảo mật. Một role hierarchy hoặc converter thay đổi là thay đổi quyền toàn hệ thống, có thể ảnh hưởng nhiều endpoint cùng lúc.

## 11. Những khẳng định sai thường gặp

| Nhận định sai | Điều đúng cần nhớ |
| --- | --- |
| “JWT có chữ ký hợp lệ nên claim `roles` có thể dùng làm admin.” | JWT hợp lệ về kỹ thuật chưa chứng minh claim đó đủ thẩm quyền cho role admin của API; phải xác minh nguồn, audience và ngữ nghĩa. |
| “`hasRole("ADMIN")` đọc JWT role trực tiếp.” | Nó kiểm `GrantedAuthority` tương ứng; converter hoặc authentication source phải tạo authority đó. |
| “Đổi `SCOPE_` sang `ROLE_` chỉ là sửa tên.” | Đổi tên có thể làm route `hasRole` chấp nhận một token trước đây bị từ chối. |
| “Scope `documents.write` cho phép sửa bất kỳ document.” | Vẫn cần policy trên document, tenant, owner và trạng thái. |
| “`hasAnyAuthority(...)` yêu cầu mọi quyền liệt kê.” | Nó dùng OR; cần AND thì dùng policy/SpEL phù hợp. |
| “Có `ROLE_USER` tức là có quyền ghi.” | Chỉ đúng nếu business contract chủ động cấp quyền ghi cho role đó. Không tự suy rộng. |
| “Kiểm `jwt()` trong MockMvc là đã kiểm token thật.” | Mock test có thể bỏ qua đường xác minh token/converter runtime; cần kiểm riêng trust path. |
| “Cứ có claim không hợp lệ thì gán quyền mặc định.” | Quyền nhạy cảm phải fail closed; không tự thêm role hoặc scope. |
| “Một test GET thành công đủ chứng minh không lộ dữ liệu.” | Cần test cả ID ngoài tenant, query/search, export, cache và state sau write denial. |

## 12. Checklist nghiệm thu bài học

- [ ] Phân biệt đúng `scope`, `role` và `GrantedAuthority`; giải thích được `hasRole` so với `hasAuthority`.
- [ ] Token chỉ có `scope: "ADMIN"` **không** tự có `ROLE_ADMIN` trong chính sách mong đợi.
- [ ] Không có converter tự động biến mọi `SCOPE_*` thành `ROLE_*` hoặc gán role mạnh hơn nguồn đã cấp.
- [ ] Claim role có issuer, audience, owner và contract rõ; không dùng role của hệ thống khác hoặc claim client kiểm soát.
- [ ] Mỗi endpoint yêu cầu scope chức năng phù hợp; không lấy `authenticated()`, `ROLE_USER` hoặc điều kiện OR làm đường tắt cho ghi/xóa.
- [ ] Policy còn kiểm quyền trên từng tài nguyên, tenant, owner và ACL; thiếu scope hoặc dữ liệu policy thì từ chối.
- [ ] Test converter khẳng định **không xuất hiện** các authorities ngoài nguồn; test request/method/database chứng minh không có quyền vượt phạm vi.
- [ ] Test bao phủ JWT thật và mock đúng tầng; biết rõ `jwt()` không thay thế kiểm chữ ký, issuer/audience và custom converter runtime.
- [ ] Khi đổi mapping/role hierarchy, có regression test và review ảnh hưởng lên mọi route sử dụng authority liên quan.

**Kết luận:** `ROLE_` và `SCOPE_` là quy ước tên ở tầng `GrantedAuthority`. Chính sách an toàn yêu cầu mỗi authority có nguồn được xác minh, ý nghĩa nghiệp vụ rõ ràng và không rộng hơn quyền được cấp; endpoint còn phải kiểm phạm vi tài nguyên cụ thể. Chỉ một phép ánh xạ từ scope sang role cũng có thể nâng quyền trên nhiều API.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): scope-to-authority mặc định, `JwtAuthenticationConverter`, custom claim/prefix và ghép converter.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `hasRole` và quy tắc request.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, expression và kiểm soát mức method.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, chỉnh claim và authorities trong MockMvc.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authority, role hierarchy và các thành phần authorization.
