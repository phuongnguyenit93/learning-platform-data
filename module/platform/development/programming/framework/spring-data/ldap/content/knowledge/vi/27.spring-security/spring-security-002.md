# Cấu hình luồng xác thực LDAP trong ứng dụng Spring Security

> **Chương:** Spring Security  
> **Module:** `SPRING_DATA_LDAP` — truy cập dịch vụ thư mục LDAP qua Spring Data LDAP, ánh xạ entry phân cấp thành đối tượng Java và thao tác bằng repository hoặc `LdapTemplate`.

Nhiều ứng dụng Java lưu thông tin người dùng, nhóm và bộ phận trong một dịch vụ thư mục LDAP. **Spring Data LDAP** giúp ứng dụng tìm kiếm, đọc và cập nhật những entry này; **Spring Security LDAP** giúp ứng dụng kiểm tra thông tin đăng nhập bằng directory và chuyển kết quả thành danh tính, quyền truy cập trong ứng dụng Spring.

Giả sử ứng dụng quản trị nhân sự cho người dùng đăng nhập bằng `uid` và mật khẩu directory. Khi người dùng gửi biểu mẫu đăng nhập, Spring Security cần tìm đúng entry, xác minh mật khẩu theo cơ chế LDAP, xác định các nhóm được cấp quyền, rồi cho phép hoặc từ chối truy cập endpoint. Bài học này hướng dẫn cấu hình **LDAP bind authentication** cho ứng dụng Spring Boot dùng `SecurityFilterChain` và giải thích các lựa chọn thay thế, giới hạn bảo mật và cách kiểm thử.

## 1. Mục tiêu và những khái niệm phải phân biệt

Sau bài này, người học có thể:

1. Mô tả đường đi của `username/password` qua Spring Security tới LDAP server.
2. Cấu hình `ContextSource`, tìm DN người dùng và xác thực bằng LDAP bind.
3. Ánh xạ nhóm LDAP thành `GrantedAuthority` để áp dụng `hasRole(...)`.
4. Phân biệt dịch vụ đăng nhập của Spring Security với repository/`LdapTemplate` của Spring Data LDAP.
5. Bảo vệ mật khẩu và đường truyền, giới hạn quyền bind, xử lý lỗi đăng nhập và kiểm thử tích hợp.

Bốn thuật ngữ quan trọng:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Authentication** | Xác định người dùng là ai bằng credential | Kiểm tra `lan` và mật khẩu qua LDAP bind |
| **Authorization** | Xác định danh tính đã xác thực được làm gì | Chỉ nhóm `app_admin` truy cập `/admin/**` |
| **LDAP bind** | Thao tác thiết lập danh tính xác thực đối với directory | Bind bằng DN của Lan và mật khẩu người dùng gửi |
| **LDAP search** | Tìm entry theo base DN, scope và filter | Tìm `(uid=lan)` dưới `ou=people` |

**Đăng nhập thành công không đồng nghĩa có quyền quản trị.** Người dùng có thể được directory chấp nhận mật khẩu nhưng không nằm trong nhóm tương ứng, nên truy cập `/admin/**` vẫn phải bị chặn.

## 2. Bức tranh tổng thể: HTTP request đến kết quả LDAP

Với cấu hình form login truyền thống, luồng chính như sau:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant F as Spring Security FilterChain
    participant A as AuthenticationManager / LDAP provider
    participant D as LDAP directory

    U->>B: Nhập username và password
    B->>F: POST /login (HTTPS + CSRF token)
    F->>A: UsernamePasswordAuthenticationToken
    A->>D: Tìm entry người dùng theo DN pattern hoặc search
    D-->>A: DN người dùng
    A->>D: Bind bằng DN người dùng và password
    alt Bind thành công
        D-->>A: Xác thực hợp lệ
        A->>D: Tìm nhóm/role nếu được cấu hình
        D-->>A: Các nhóm được cấp quyền
        A-->>F: Authentication đã xác thực và authorities
        F-->>B: Session/cookie và chuyển hướng sau login
        B->>F: Truy cập /admin
        F-->>B: Cho phép hoặc 403 theo authorities
    else Bind thất bại
        D-->>A: Lỗi xác thực LDAP
        A-->>F: AuthenticationException
        F-->>B: Thông báo đăng nhập thất bại
    end
~~~

Các vai trò trong chuỗi này:

- `SecurityFilterChain` nhận và bảo vệ yêu cầu HTTP, bao gồm form login, CSRF, session và kiểm soát endpoint.
- `AuthenticationManager` điều phối cơ chế xác thực; ở đây được cấu hình bằng `LdapBindAuthenticationManagerFactory`.
- LDAP authenticator tìm DN của người dùng rồi yêu cầu directory xác minh credential bằng **bind**.
- `LdapAuthoritiesPopulator` có thể tìm nhóm LDAP và chuyển chúng thành quyền cho Spring Security.
- `SecurityContext` chứa `Authentication` đã xác thực để các bước phân quyền sử dụng trong phạm vi phiên/yêu cầu thích hợp.

Trong bind authentication, Spring Security **không cần đọc giá trị `userPassword` hoặc hash mật khẩu từ LDAP** để so sánh. LDAP server là bên xác nhận thông tin đăng nhập. Tuy vậy, ứng dụng vẫn nhận mật khẩu từ biểu mẫu HTTP để chuyển cho cơ chế bind; đường truyền HTTPS, bảo vệ bộ nhớ và chính sách log vẫn rất quan trọng.

## 3. Chuẩn bị mô hình LDAP minh họa

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=binh
├── ou=groups
│   ├── cn=app_admin
│   └── cn=app_user
└── ou=system
    └── uid=svc-reader
~~~

Trong đó:

- Người dùng đăng nhập với `uid=lan`.
- Entry của Lan nằm tại `uid=lan,ou=people,dc=example,dc=org`.
- Các nhóm ứng dụng có `objectClass=groupOfNames` và thuộc tính `member` chứa DN của thành viên.
- `uid=svc-reader,ou=system,...` là **service account** được cấp quyền tìm kiếm user/nhóm; tài khoản này không phải người dùng đang đăng nhập.

Ví dụ LDIF dành cho directory **kiểm thử độc lập** (giả định `dc=example,dc=org` đã tồn tại):

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
userPassword: local-test-only

dn: cn=app_admin,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app_admin
member: uid=lan,ou=people,dc=example,dc=org
~~~

Mật khẩu `local-test-only` chỉ là dữ liệu giả trong ví dụ test. Không lưu mật khẩu production dạng rõ trong LDIF, repository, log hoặc file cấu hình. Directory sản xuất có thể dùng cơ chế lưu mật khẩu, chính sách tài khoản, `objectClass` và mô hình nhóm khác.

**Vai trò của schema:** `inetOrgPerson` kế thừa các thuộc tính bắt buộc `cn`/`sn` từ `person`; `groupOfNames` thường yêu cầu ít nhất một `member`. Entry thiếu thuộc tính MUST hoặc có attribute không được phép có thể bị directory server từ chối trước khi ứng dụng thử đăng nhập.

## 4. Dependencies cho ứng dụng Spring Boot

Cần có Spring Security cho bảo vệ HTTP, Spring Security LDAP cho xác thực LDAP và Spring LDAP/Spring Data LDAP để thao tác với entry bằng `LdapTemplate` hoặc repository.

Ví dụ khai báo Maven, dùng dependency management của Spring Boot để quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-ldap</artifactId>
    </dependency>
</dependencies>
~~~

Hai tầng có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `spring-boot-starter-security` | Filter chain, xử lý đăng nhập, phân quyền và bảo vệ web |
| `spring-security-ldap` | LDAP authenticator/provider, factory và đọc vai trò từ directory |
| `spring-boot-starter-data-ldap` | Cấu hình LDAP, Spring LDAP và Spring Data LDAP repository |
| `LdapRepository`/`LdapTemplate` | Truy vấn/CRUD entry theo nghiệp vụ, không mặc nhiên thực hiện login |

Ví dụ Java sau đây theo kiểu bean-based configuration với `SecurityFilterChain` và `LdapBindAuthenticationManagerFactory`, phù hợp nhóm phiên bản Spring Security hiện đại có các API này. Cần đối chiếu phiên bản Spring Boot/Spring Security/Spring LDAP đang triển khai, đặc biệt khi áp dụng sang dự án cũ.

## 5. Cấu hình kết nối LDAP qua ContextSource

Ví dụ file `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: ${LDAP_BASE_DN}
    username: ${LDAP_SERVICE_DN}
    password: ${LDAP_SERVICE_PASSWORD}
~~~

Biến môi trường minh họa:

~~~text
LDAP_URL=ldaps://directory.example.org:636
LDAP_BASE_DN=dc=example,dc=org
LDAP_SERVICE_DN=uid=svc-reader,ou=system,dc=example,dc=org
LDAP_SERVICE_PASSWORD=<giá-trị-từ-secret-manager>
~~~

`spring.ldap.urls` chọn endpoint LDAP; `spring.ldap.base` xác định gốc DN cho ngữ cảnh thao tác Spring LDAP. Tài khoản ở `spring.ldap.username`/`password` được dùng cho các thao tác đọc/tìm kiếm có yêu cầu credential của ứng dụng; đây **không phải** mật khẩu của từng người dùng đăng nhập.

Khi `base=dc=example,dc=org`, một search base `ou=people` trong cấu hình xác thực tương ứng với:

~~~text
ou=people,dc=example,dc=org
~~~

Không lặp lại `dc=example,dc=org` vào base tương đối chỉ vì DN tuyệt đối có chứa hậu tố này. Tương tự, group search base `ou=groups` tương ứng với `ou=groups,dc=example,dc=org`.

### Ranh giới trách nhiệm của service account

Service account cần đủ quyền đọc các thuộc tính và entry dùng để **tìm DN người dùng và nhóm**. Nó không cần quyền quản trị directory hoặc đọc thuộc tính `userPassword`. Sau khi tìm đúng entry, **bind authentication** sử dụng credential của chính người dùng để kiểm chứng.

Việc cấp quyền cụ thể phụ thuộc ACL của LDAP server. Trong hệ thống có nhiều tenant/OU, nên giới hạn tìm kiếm trong những nhánh cần thiết và kiểm tra quyền truy cập ở cả tầng ứng dụng lẫn directory.

### LDAPS và StartTLS

- `ldaps://` mở kết nối TLS ngay từ đầu, thường ở cổng `636`.
- StartTLS bắt đầu từ kết nối LDAP rồi nâng cấp sang TLS trước khi gửi credential; cần cấu hình và kiểm thử cơ chế nâng cấp, không tự phát sinh chỉ vì URL dùng `ldap://`.
- Trong production, phải kiểm tra chứng chỉ, CA/truststore và tên máy chủ; không bỏ xác minh TLS để bỏ qua lỗi cấu hình.

Vì thao tác bind chuyển mật khẩu người dùng tới directory, bảo vệ kết nối giữa **trình duyệt ↔ ứng dụng** và **ứng dụng ↔ LDAP server** là hai yêu cầu độc lập.

## 6. Cấu hình cơ bản: SecurityFilterChain và LDAP bind

Ví dụ một cấu hình Java hoàn chỉnh cho ứng dụng web dùng form login. Giả định Spring Boot đã tạo một `BaseLdapPathContextSource` phù hợp từ `spring.ldap.*` và service account có quyền đọc `ou=people`/`ou=groups`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class LdapSecurityConfig {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        DefaultLdapAuthoritiesPopulator groups =
                new DefaultLdapAuthoritiesPopulator(
                        contextSource, "ou=groups");

        groups.setGroupSearchFilter(
                "(&(objectClass=groupOfNames)(member={0}))");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter(
                "(&(objectClass=inetOrgPerson)(uid={0}))");
        factory.setLdapAuthoritiesPopulator(groups);

        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {

        http
            .authenticationManager(ldapAuthenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("APP_ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Điểm cốt lõi:

1. `LdapBindAuthenticationManagerFactory` tạo `AuthenticationManager` sử dụng LDAP bind.
2. `setUserSearchBase("ou=people")` chỉ định nhánh tìm entry đăng nhập, tương đối với base DN của `ContextSource`.
3. `setUserSearchFilter(...uid={0}...)` dùng username người dùng nhập để tìm DN phù hợp; placeholder `{0}` được Spring Security xử lý trong LDAP search.
4. `DefaultLdapAuthoritiesPopulator` tìm group có `member` bằng DN người dùng và lấy `cn` làm tên role.
5. `http.authenticationManager(...)` gắn manager LDAP với filter chain đang bảo vệ HTTP request.
6. `formLogin(...)` bật luồng đăng nhập bằng biểu mẫu; `authorizeHttpRequests(...)` quyết định endpoint được phép truy cập.

Với entry nhóm `cn=app_admin`, cách ánh xạ ở trên tạo authority `ROLE_APP_ADMIN`. Do đó `hasRole("APP_ADMIN")` sẽ khớp nếu Lan thuộc nhóm. Không viết `hasRole("ROLE_APP_ADMIN")` với cấu hình role prefix chuẩn: `hasRole` tự xét tiền tố `ROLE_` theo quy ước Spring Security.

**Lưu ý thực tế:** lớp cấu hình trên là ví dụ cho một cơ chế đăng nhập của ứng dụng. Nếu dự án đang có nhiều `SecurityFilterChain`, OAuth2/OIDC hoặc nhiều `AuthenticationProvider`, cần xác định chain/manager nào xử lý endpoint nào. Không mặc nhiên trộn các provider mà chưa kiểm thử thứ tự và ngữ nghĩa xác thực.

## 7. Xác định DN người dùng: DN pattern hay LDAP search?

Để thử bind bằng mật khẩu của user, Spring Security cần biết **DN người dùng**. Có hai cách phổ biến.

### Cách A: DN pattern khi cấu trúc thư mục cố định

Nếu tất cả người dùng đều nằm trực tiếp dưới `ou=people` và dùng `uid` làm RDN:

~~~java
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {

    LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(contextSource);

    factory.setUserDnPatterns("uid={0},ou=people");
    return factory.createAuthenticationManager();
}
~~~

Nếu username là `lan`, DN tương ứng là:

~~~text
uid=lan,ou=people,dc=example,dc=org
~~~

Lợi ích: đơn giản và không cần bước tìm entry theo `uid` nếu DN xác định được trực tiếp. Hạn chế: không phù hợp nếu người dùng nằm rải trong nhiều OU hoặc RDN không nhất quán. Ví dụ ở mục này trình bày **phương án thay thế** cho cấu hình ở mục 6, không phải bean thứ hai phải đăng ký song song.

### Cách B: Tìm user bằng base và filter

Nếu người dùng có thể nằm tại `uid=lan,ou=engineering,ou=people,...` hoặc tên DN khác với username, dùng bước search:

~~~java
LdapBindAuthenticationManagerFactory factory =
        new LdapBindAuthenticationManagerFactory(contextSource);

factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter(
        "(&(objectClass=inetOrgPerson)(uid={0}))");
~~~

Cách này phù hợp với cây có nhiều nhánh con, nhưng cần lưu ý:

- Search base phải bao phủ entry được phép xác thực và tránh quét các nhánh không liên quan.
- Search filter phải khớp schema/thuộc tính thực tế, chẳng hạn `uid`, `sAMAccountName` hoặc thuộc tính khác theo server.
- Nếu có nhiều entry trùng `uid` ở các nhánh khác nhau, ứng dụng phải định nghĩa chính sách nhận diện người dùng; không mặc nhiên xem `uid` là duy nhất toàn directory.
- Service account phải có quyền thực hiện tìm kiếm; nếu DN được tìm đúng nhưng bind thất bại thì nguyên nhân có thể nằm ở mật khẩu, trạng thái tài khoản hoặc chính sách server.

**Không tự nối chuỗi filter từ username:** tránh kiểu `"(uid=" + username + ")"`. Dùng API tìm kiếm và placeholder của Spring Security để framework xử lý dữ liệu theo cú pháp filter. Chọn DN base từ cấu hình đã kiểm soát; tránh cho người dùng truyền nguyên DN để định hướng tìm kiếm sang một tenant khác.

## 8. Lấy nhóm LDAP làm authority của Spring Security

LDAP có thể lưu nhóm dưới các lớp khác nhau, ví dụ `groupOfNames`, `groupOfUniqueNames` hoặc mô hình Active Directory. Thuộc tính thành viên cũng khác nhau:

| Loại nhóm | Thuộc tính thường dùng | Ý nghĩa |
|---|---|---|
| `groupOfNames` | `member` | Danh sách DN của thành viên |
| `groupOfUniqueNames` | `uniqueMember` | Danh sách thành viên theo cú pháp tương ứng |
| Active Directory | Thường sử dụng `member`/`memberOf` hoặc nhóm lồng nhau | Cần kiểm tra cách triển khai và phạm vi truy vấn |

Ví dụ config nhóm ở mục 6:

~~~java
DefaultLdapAuthoritiesPopulator groups =
        new DefaultLdapAuthoritiesPopulator(
                contextSource, "ou=groups");

groups.setGroupSearchFilter(
        "(&(objectClass=groupOfNames)(member={0}))");
groups.setGroupRoleAttribute("cn");
groups.setRolePrefix("ROLE_");
groups.setConvertToUpperCase(true);
~~~

`{0}` trong group filter biểu diễn **DN đầy đủ của user**, khác với `{0}` trong user search filter biểu diễn **username**. Đây là khác biệt quan trọng khi tự thiết kế filter.

Giả sử directory có entry:

~~~ldif
dn: cn=app_admin,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app_admin
member: uid=lan,ou=people,dc=example,dc=org
~~~

Khi Lan đăng nhập, populator tìm nhóm chứa DN này và chuyển `cn=app_admin` thành `ROLE_APP_ADMIN` (theo cấu hình prefix và chuyển chữ hoa). Một request tới `/admin/report` được phép nếu người dùng có authority tương ứng.

### Những giới hạn cần biết

- **Base tìm nhóm khác base tìm người dùng.** User search ở `ou=people`; group search ở `ou=groups`.
- Theo cấu hình thường gặp, group search chỉ duyệt **một cấp** dưới group base; cần bật `groups.setSearchSubtree(true)` nếu nhóm có OU con và muốn tìm xuyên cấp.
- **Role không tự xuất hiện từ objectClass của user.** Ứng dụng phải cấu hình cơ chế tải/mapping authority.
- **Nhóm lồng nhau** không mặc nhiên được duyệt đầy đủ bởi `DefaultLdapAuthoritiesPopulator`; cần thiết kế cơ chế đọc group membership phù hợp với server nếu yêu cầu quyền kế thừa.
- Khi nhóm hoặc quyền thay đổi trong LDAP, **phiên đăng nhập đang hoạt động không nhất thiết cập nhật ngay**. Cần xác định cơ chế làm mới session, reauthentication hoặc thu hồi phiên cho nghiệp vụ nhạy cảm.
- Không nên ánh xạ mọi nhóm trong tổ chức thành role của ứng dụng một cách vô điều kiện. Có thể giới hạn vào nhánh/nhóm ứng dụng hoặc dùng mapping tường minh đã được review.

## 9. Chuyện gì xảy ra với HTTP sau khi bind thành công?

Trong cấu hình `formLogin(Customizer.withDefaults())`, Spring Security cung cấp giao diện đăng nhập mặc định và endpoint xử lý đăng nhập của filter chain. Luồng thường gặp:

~~~text
GET /admin/dashboard
      |
      | Chưa xác thực
      v
Redirect đến GET /login
      |
      | Nhập username + password + CSRF token
      v
POST /login
      |
      +-- LDAP bind hợp lệ --> xác lập Authentication/session
      |                      --> chuyển tới URL đã yêu cầu
      |
      +-- LDAP bind lỗi ----> xử lý thất bại đăng nhập
~~~

Một `Authentication` thành công thường chứa principal và danh sách `GrantedAuthority`. Spring Security dùng nó ở bước authorization. Ứng dụng có thể lấy principal theo API SecurityContext hoặc tham số controller:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    public String currentUsername(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Endpoint này chỉ minh họa cách lấy danh tính **đã xác thực**. Không dùng `authentication.getName()` như một DN chắc chắn: giá trị có thể là username hiển thị hoặc dạng tên khác tùy `UserDetailsContextMapper`. Nếu nghiệp vụ cần DN chính xác, cần mapping/truy xuất có kiểm soát.

### Authentication khác authorization

Với `.anyRequest().authenticated()`, một người dùng bind thành công có thể truy cập endpoint chỉ yêu cầu đăng nhập. Với `.requestMatchers("/admin/**").hasRole("APP_ADMIN")`, người dùng còn cần authority `ROLE_APP_ADMIN`.

- **Chưa đăng nhập:** form login thường chuyển hướng đến trang đăng nhập.
- **Sai mật khẩu:** xác thực thất bại; trả về luồng đăng nhập lỗi, không tạo phiên xác thực thành công.
- **Đã đăng nhập nhưng thiếu quyền:** truy cập tài nguyên được bảo vệ thường bị từ chối với HTTP `403`.

Khi dùng API HTTP Basic hoặc cơ chế API khác, mã phản hồi cho client có thể khác. Không nhầm lỗi xác thực (credential) với lỗi phân quyền (authority).

## 10. Spring Data LDAP và Security LDAP dùng chung directory nhưng khác mục đích

Một ứng dụng có thể vừa đăng nhập qua Spring Security LDAP, vừa có repository quản lý hồ sơ:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

Với một entity được ánh xạ bằng `@Entry`, `@Id`, `@Attribute`, repository có thể tìm và sửa các thuộc tính như `cn`, `sn`, `mail`. Nhưng cần phân biệt:

| Hoạt động | Thành phần thực hiện | Credential thường sử dụng |
|---|---|---|
| Tìm entry để đăng nhập | LDAP authenticator/user search | ContextSource/service account có quyền tìm |
| Xác minh mật khẩu người dùng | LDAP bind authenticator | DN + mật khẩu vừa nhập của chính user |
| Đọc group/role | Authorities populator | ContextSource với quyền đọc group |
| Tìm hoặc CRUD entity LDAP | `LdapRepository` / `LdapTemplate` | Bind credential của ContextSource cho thao tác nghiệp vụ |
| Kiểm tra URL/endpoint | Spring Security authorization | `Authentication` và authorities của phiên |

**Ranh giới rất quan trọng:** gọi `personRepository.save(...)` **không mặc nhiên chạy dưới quyền LDAP của người dùng vừa đăng nhập**. Repository thường dùng context và tài khoản đã được cấu hình cho ứng dụng. Ứng dụng phải tự kiểm tra quyền nghiệp vụ của caller và directory server phải thực thi ACL phù hợp đối với tài khoản dùng để ghi.

Ví dụ: Lan có `ROLE_APP_USER` được phép xem hồ sơ của chính mình, nhưng không vì thế mà được phép gọi một endpoint admin đang dùng `LdapTemplate` để xóa entry của người khác. **Xác thực LDAP và phân quyền thao tác CRUD là hai lớp riêng biệt.**

## 11. Password comparison là phương án khác với bind

Spring Security hỗ trợ xác thực LDAP bằng **password comparison**, nhưng đây không phải cấu hình đang chọn trong ví dụ chính.

| Tiêu chí | Bind authentication | Password comparison |
|---|---|---|
| Cách xác minh | Thử bind bằng user DN và credential | So sánh password bằng LDAP compare hoặc giá trị đọc được theo cấu hình |
| Có cần ứng dụng đọc hash? | Không | Có thể có tùy chiến lược so sánh |
| Phụ thuộc | Quy tắc bind và chính sách LDAP server | Syntax, thuật toán lưu password, quyền đọc/compare |
| Phù hợp mặc định | Nhiều hệ thống LDAP hỗ trợ đăng nhập bằng bind | Chỉ khi schema, cách lưu mật khẩu và mô hình quyền phù hợp |

Trong Spring Security, API dành cho phương án này là `LdapPasswordComparisonAuthenticationManagerFactory`. Không sao chép ví dụ dùng `NoOpPasswordEncoder` vào production; lựa chọn thuật toán và cách so sánh phải phù hợp chính sách password của directory và mức bảo mật yêu cầu.

Đối với hệ thống đã có dịch vụ xác thực LDAP chuẩn, **bind authentication** thường là lựa chọn mở đầu hợp lý vì để directory server thực hiện kiểm chứng mật khẩu và áp dụng chính sách account của nó.

### Trường hợp Active Directory

Active Directory có thể sử dụng username dạng `user@corp.example`, `sAMAccountName`, schema group và chính sách bind riêng. Không áp dụng máy móc `uid={0},ou=people` hoặc filter `(uid={0})` của ví dụ OpenLDAP. Cần nghiên cứu naming context, thuộc tính đăng nhập và phương án như `ActiveDirectoryLdapAuthenticationProvider` nếu phù hợp hệ thống thực tế.

## 12. Bảo mật end-to-end cho luồng đăng nhập

Vì ứng dụng xử lý credential, cấu hình luồng xác thực LDAP phải bảo vệ cả HTTP lẫn LDAP:

1. **HTTPS giữa trình duyệt và ứng dụng.** Nếu không, username/password trong biểu mẫu có thể bị lộ trước khi tới Spring Security.
2. **LDAPS hoặc StartTLS giữa ứng dụng và directory.** Xác minh chứng chỉ và hostname, không chấp nhận tự động hạ cấp xuống kết nối không mã hóa.
3. **Service account đặc quyền tối thiểu.** Chỉ cấp đọc/tìm những OU và thuộc tính cần cho xác thực và roles; không dùng tài khoản quản trị directory khi không cần.
4. **Secret injection và rotation.** Đặt bind password trong secret manager/nền tảng triển khai, tránh hardcode trong mã nguồn và build artifact.
5. **Không log mật khẩu hay token.** Kể cả khi xác thực thất bại, chỉ ghi dữ liệu chẩn đoán tối thiểu, đã giới hạn thông tin cá nhân.
6. **Giữ CSRF protection khi dùng form login với session/cookie.** `formLogin` sử dụng các bảo vệ mặc định của Spring Security; không tắt CSRF để “sửa” lỗi POST /login trước khi hiểu nguyên nhân.
7. **Giới hạn thử đăng nhập.** Áp dụng rate limiting, giám sát thất bại và chính sách khóa tài khoản phù hợp; tránh tạo khả năng khai thác brute force hoặc gây khóa tài khoản hàng loạt.
8. **Quản lý session.** Thiết lập chính sách cookie, timeout, logout, thu hồi phiên khi cần và xem xét thay đổi quyền trong directory.
9. **Giới hạn tìm kiếm DN và group.** Không cho người dùng chọn search base tùy ý để thoát phạm vi OU/tenant đã được phân quyền.
10. **Kiểm tra lỗi theo chính sách.** Phản hồi đăng nhập không nên tiết lộ rõ “username tồn tại nhưng sai mật khẩu” cho người dùng bên ngoài.

### Đừng nhầm escaping filter với escaping DN

- Filter kiểu `(uid={0})` cần xử lý ký tự theo **cú pháp LDAP filter**.
- DN kiểu `uid=lan,ou=people,...` cần xử lý giá trị RDN theo **cú pháp DN**.
- Khi ứng dụng có chức năng xây dựng DN cho `LdapTemplate`, dùng `LdapNameBuilder` hoặc API thích hợp; không ghép chuỗi giá trị tùy ý.
- Escaping làm đầu vào hợp lệ về cú pháp, **không tự chứng minh caller được phép tìm hoặc sửa entry**. Cần authorization độc lập.

## 13. Xử lý lỗi: không tìm thấy user, mật khẩu sai, không đủ quyền

Các hiện tượng hay gặp:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Login luôn thất bại | `userSearchBase` sai, `uid` không khớp hoặc DN pattern không đúng | Xem DN hiệu lực, schema và dữ liệu test |
| User tồn tại nhưng không tìm thấy | Service account thiếu quyền search/read | Test search với chính service account |
| Chỉ một số user login được | User ở OU khác hoặc chính sách account khác | Kiểm tra nhánh thực tế, account lock/expiry |
| Password đúng nhưng bind lỗi | Credential sai, tài khoản bị khóa, server yêu cầu TLS hoặc chính sách bind | Kiểm tra chẩn đoán LDAP server, trạng thái account |
| Login thành công nhưng `/admin/**` trả 403 | Thiếu `ROLE_APP_ADMIN` hoặc group mapping sai | Kiểm tra member DN, group base/filter, role prefix |
| Không thấy nhóm dù user là thành viên | Group ở OU con, `member` vs `uniqueMember`, ACL hoặc nhóm lồng nhau | Kiểm tra schema, scope và quyền đọc |
| Ứng dụng start được nhưng đăng nhập timeout | LDAP server không tới được hoặc kết nối lười | DNS, firewall, port, timeout, log |
| Kết nối LDAPS lỗi | Chứng chỉ không tin cậy hoặc hostname mismatch | CA/truststore, hostname, thời hạn chứng chỉ |
| POST /login báo 403 trước khi xác thực | Thiếu CSRF token hoặc cấu hình filter chain | Kiểm tra form, CSRF và matcher |
| Form login liên tục redirect | Session/cookie không giữ được hoặc URL login bị bảo vệ sai | Kiểm tra cookie, reverse proxy, allow rule |

Phân loại lỗi giúp tránh một cách sửa sai phổ biến: **tắt CSRF, bỏ xác minh TLS hoặc mở quyền bind quá rộng** chỉ để đăng nhập thành công.

Ngoại lệ và mã HTTP còn phụ thuộc cơ chế form login, Basic, cấu hình `AuthenticationEntryPoint`/handler, JNDI và LDAP server. Nên log dữ liệu chẩn đoán phù hợp mà không làm lộ credential hoặc xác nhận sự tồn tại của tài khoản tới client.

## 14. Kiểm thử tích hợp với LDAP directory riêng

Unit test chỉ dùng mock `AuthenticationManager` không đủ chứng minh LDAP bind, user search và group mapping đang hoạt động. Nên dùng directory phục vụ test hoặc container LDAP với schema, OU, tài khoản và dữ liệu fixture như mục 3.

### Kịch bản kiểm thử thiết yếu

| Kịch bản | Đầu vào | Kết quả mong đợi |
|---|---|---|
| User hợp lệ | `lan` + mật khẩu đúng | `Authentication.isAuthenticated() == true` |
| Mật khẩu sai | `lan` + mật khẩu không đúng | Authentication thất bại |
| Không có user | Username không tồn tại | Authentication thất bại, không rò rỉ thông tin phân biệt |
| User có group admin | DN của user nằm trong `member` của `app_admin` | Có `ROLE_APP_ADMIN` |
| User thường | Bind thành công nhưng không thuộc admin | Truy cập URL thường được phép, admin trả 403 |
| Sai search base | Entry user nằm ngoài `ou=people` | Không tìm thấy user trong phạm vi đã cấu hình |
| Sai group base | Group đặt ngoài `ou=groups` | Không có role ứng dụng tương ứng |
| ACL hạn chế | Service account không đọc được nhóm | Phát hiện thiếu quyền mà không mở toàn bộ directory |
| TLS sai chứng chỉ | Test endpoint dùng cert không tin cậy | Kết nối thất bại, không tắt xác minh |
| Server down | LDAP test server tạm ngừng | Login thất bại có kiểm soát, không treo vô hạn |

### Test trực tiếp AuthenticationManager

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class LdapLoginIntegrationTest {

    @Autowired
    AuthenticationManager ldapAuthenticationManager;

    @Test
    void authenticatesUserAndLoadsAdminRole() {
        Authentication result = ldapAuthenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "local-test-only"));

        assertTrue(result.isAuthenticated());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a ->
                        a.getAuthority().equals("ROLE_APP_ADMIN")));
    }
}
~~~

Ví dụ giả định test profile đã kết nối **directory riêng** với fixture hợp lệ. Nó kiểm tra từ manager tới LDAP và group mapping, nhưng chưa kiểm tra đường đi của POST `/login`, CSRF/session hoặc mapping HTTP.

Để kiểm tra lớp HTTP, có thể dùng `MockMvc` với `spring-security-test` hoặc một integration test HTTP đầy đủ:

- `POST /login` có CSRF token và credential đúng → có phiên xác thực.
- Credential sai → xử lý thất bại đăng nhập, không tạo session xác thực hợp lệ.
- Session có `ROLE_APP_ADMIN` → được vào `/admin/**`.
- Session chỉ có quyền thường → `403` tại `/admin/**`.
- Thiếu CSRF token trong form request bảo vệ → bị từ chối theo cấu hình.

**Phân biệt mock và test tích hợp:** `@WithMockUser` giúp kiểm tra authorization rule nhưng **bỏ qua bind LDAP thật**. Để bảo đảm cấu hình xác thực chính xác, cần ít nhất một bài test đi qua LDAP server test và một bài kiểm tra HTTP/authorization.

## 15. Kiểm tra vận hành và giới hạn của môi trường production

Khi đưa luồng xác thực LDAP vào production, cần kiểm tra cả khả năng sẵn sàng lẫn cách phục hồi:

~~~mermaid
flowchart TD
    A["Triển khai ứng dụng"] --> B["Kiểm tra profile, secret, LDAP URL và base DN"]
    B --> C["Kiểm tra TLS/certificate và quyền service account"]
    C --> D["Kiểm tra tìm user, bind bằng test account và đọc group"]
    D --> E{"Đạt tiêu chí?"}
    E -->|Không| F["Chặn release / điều tra cấu hình"]
    E -->|Có| G["Cho phép phục vụ traffic"]
    G --> H["Theo dõi latency, failed bind, timeout, lockout"]
~~~

Gợi ý vận hành:

- Tách `dev`, `test` và `prod` bằng profile và secret riêng; không dùng production directory cho ca test ghi dữ liệu hay thử password liên tục.
- Có giới hạn thời gian kết nối/đọc thích hợp ở tầng JNDI/provider, mạng và reverse proxy; tránh để login treo khi LDAP không phản hồi.
- Theo dõi tỉ lệ đăng nhập lỗi và độ trễ nhưng không log password, raw form data hoặc toàn bộ entry LDAP.
- Thiết lập quy trình xoay vòng mật khẩu service account, chứng chỉ TLS và cách khởi động lại connection pool khi cần.
- Khi directory gặp sự cố, tránh triển khai cơ chế “login dự phòng” chấp nhận credential không được kiểm chứng. Quyết định availability phải giữ nguyên yêu cầu xác thực.
- Thiết kế phân quyền cho nhóm/role khi quyền thay đổi trong directory: cần hiểu thời điểm authority được tải và cách làm mới/thu hồi các session hiện hành.
- Giới hạn quyền CRUD của `LdapRepository`/`LdapTemplate` riêng với việc user đã đăng nhập; ghi thao tác nhạy cảm có audit thích hợp.

## 16. Bài tập thực hành

**Bối cảnh:** một ứng dụng Spring Boot có trang `/me` cho mọi nhân viên và `/admin/report` cho nhóm quản trị. Directory chứa `ou=people` và `ou=groups` dưới `dc=example,dc=org`.

Thực hiện lần lượt:

1. Tạo directory test có hai người dùng `lan`, `binh`; chỉ thêm DN của Lan vào nhóm `cn=app_admin`.
2. Cấu hình `spring.ldap.urls`, `spring.ldap.base` và service credential bằng biến môi trường của test.
3. Tạo `AuthenticationManager` với `LdapBindAuthenticationManagerFactory`, search base `ou=people` và filter `(uid={0})`.
4. Cấu hình `DefaultLdapAuthoritiesPopulator` đọc `groupOfNames` dưới `ou=groups`, ánh xạ `cn` thành role.
5. Tạo `SecurityFilterChain` yêu cầu authenticated cho `/me` và `hasRole("APP_ADMIN")` cho `/admin/**`.
6. Kiểm thử Lan đăng nhập đúng mật khẩu, vào được cả hai endpoint. Với Binh, `/me` hoạt động nhưng `/admin/report` bị từ chối.
7. Kiểm thử password sai, username không tồn tại, service account không đủ quyền search, group filter sai.
8. Bật LDAPS hoặc StartTLS trong môi trường test hỗ trợ và xác nhận kết nối thất bại khi chứng chỉ không được tin cậy.
9. Sử dụng một `LdapRepository` đọc thuộc tính hồ sơ của Lan, rồi giải thích vì sao credential repository không phải mật khẩu mà Lan vừa nhập.

**Tiêu chí hoàn thành:** người dùng được xác thực bằng LDAP bind thật; quyền được ánh xạ từ nhóm phù hợp; endpoint thực thi phân quyền; không có mật khẩu production trong mã nguồn; các tình huống lỗi và sự khác biệt giữa authentication với CRUD LDAP được kiểm chứng.

## 17. Tổng kết và tài liệu tham khảo

Luồng xác thực LDAP với Spring Security gồm: **nhận credential → tìm DN người dùng → LDAP bind → đọc nhóm/quyền → tạo Authentication → phân quyền request**. `SecurityFilterChain` bảo vệ HTTP; `LdapBindAuthenticationManagerFactory` cấu hình manager xác thực qua directory; `DefaultLdapAuthoritiesPopulator` ánh xạ group LDAP thành Spring Security authorities.

Trong cùng ứng dụng, Spring Data LDAP vẫn đảm nhận việc ánh xạ entry, truy vấn và CRUD bằng `LdapRepository` hoặc `LdapTemplate`. Các thao tác này phải có bảo vệ quyền nghiệp vụ và ACL riêng. Một cấu hình an toàn còn cần HTTPS, LDAPS/StartTLS, secret management, đúng search base, giới hạn quyền bind và integration test với directory độc lập.

Tài liệu tra cứu chính thức:

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): dependency, ContextSource, bind authentication và password comparison.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `SecurityFilterChain`, `HttpSecurity` và authorization.
- [Spring Security — DefaultLdapAuthoritiesPopulator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html): group base/filter, role prefix và ánh xạ quyền.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): cấu hình `ContextSource`, query và DN.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): entity mapping và repository.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): thao tác Bind và Search.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): các cơ chế xác thực và yêu cầu bảo mật LDAP.
