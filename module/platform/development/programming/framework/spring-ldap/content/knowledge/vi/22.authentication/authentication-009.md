# Tích hợp Spring LDAP với Spring Security LDAP

Ứng dụng Spring thường phải thực hiện hai việc liên quan đến LDAP: **làm việc với dữ liệu thư mục** (tìm DN, đọc thuộc tính, thao tác entry) và **xác thực người dùng để bảo vệ các HTTP endpoint**. Hai thư viện giải quyết những phần việc khác nhau:

- **Spring LDAP** cung cấp `ContextSource`, `LdapTemplate`, `LdapClient` và các API truy vấn hoặc thao tác LDAP.
- **Spring Security LDAP** tích hợp xác thực LDAP vào chuỗi xử lý bảo mật của **Spring Security**, để kết quả LDAP bind có thể trở thành `Authentication` và đi qua cơ chế quản lý quyền truy cập.

Ví dụ, Lan đăng nhập vào cổng nội bộ bằng `uid=lan` và mật khẩu LDAP. Backend cần tìm DN của Lan, để LDAP xác minh mật khẩu, sau đó nạp quyền `ROLE_REPORT_READERS` nếu Lan thuộc nhóm được phép xem báo cáo. Cuối cùng, khi Lan gọi `GET /reports/monthly`, Spring Security phải kiểm tra danh tính và quyền của Lan. Việc gọi `LdapTemplate.authenticate(...)` trả về `true` riêng lẻ chưa tự thực hiện hết chuỗi này.

Bài học thuộc chương **Authentication** của module **SPRING_LDAP**. Nội dung trình bày kiến trúc tích hợp, cấu hình thực tế với Spring Boot, cách dùng `LdapBindAuthenticationManagerFactory`, nạp quyền từ nhóm LDAP, xử lý lỗi, TLS và chiến lược kiểm thử. Ví dụ Java sử dụng cách cấu hình `SecurityFilterChain` và factory được Spring Security hỗ trợ trong các phiên bản hiện đại; hãy đối chiếu chữ ký API với phiên bản được dùng trong dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt trách nhiệm của **Spring LDAP** và **Spring Security LDAP** trong cùng ứng dụng.
2. Giải thích luồng **service bind → tìm DN → user bind → nạp authorities → bảo vệ HTTP request**.
3. Cấu hình `ContextSource`/`LdapTemplate` bằng thuộc tính `spring.ldap` trong Spring Boot.
4. Tạo `AuthenticationManager` dựa trên `LdapBindAuthenticationManagerFactory` và dùng nó với `SecurityFilterChain`.
5. Ánh xạ LDAP group membership thành Spring Security `GrantedAuthority` hoặc role.
6. Nhận biết khi nào dùng bind, khi nào cân nhắc password comparison, và vì sao không nên tự xử lý mật khẩu khi không cần.
7. Kiểm thử đúng cả **LDAP authentication** và **authorization**, đồng thời tránh cấu hình TLS/ACL hoặc session thiếu an toàn.

## 2. Kiến trúc: hai thư viện phối hợp thế nào?

Spring LDAP là tầng **LDAP access**; Spring Security LDAP cung cấp các thành phần **authentication provider** dùng những kết nối và thông tin thư mục đó.

| Thành phần | Thuộc thư viện | Trách nhiệm chính |
|---|---|---|
| `ContextSource`, `LdapContextSource` | Spring LDAP | Tạo ngữ cảnh và kết nối LDAP, thiết lập URL/base/credential |
| `LdapTemplate` | Spring LDAP | Search, bind authentication đơn giản, CRUD, compare và thao tác entry |
| `LdapClient` | Spring LDAP | API fluent cho các thao tác LDAP trong phiên bản hỗ trợ |
| `LdapAuthenticator` | Spring Security LDAP | Hợp đồng kiểm tra thông tin xác thực LDAP và lấy dữ liệu người dùng |
| `BindAuthenticator` | Spring Security LDAP | Xác thực bằng cách bind dưới danh tính người dùng |
| `PasswordComparisonAuthenticator` | Spring Security LDAP | Xác thực theo cơ chế so sánh mật khẩu phù hợp với server/schema |
| `LdapAuthenticationProvider` | Spring Security LDAP | Phối hợp authenticator với bộ nạp authorities |
| `DefaultLdapAuthoritiesPopulator` | Spring Security LDAP | Tra LDAP groups và chuyển thành `GrantedAuthority` |
| `AuthenticationManager` | Spring Security | Tiếp nhận yêu cầu xác thực, trả kết quả/ngoại lệ xác thực |
| `SecurityFilterChain` | Spring Security | Xác thực request và kiểm tra quyền đối với endpoint |

**Ranh giới quan trọng:** `LdapTemplate.authenticate(...)` có thể trả về `boolean`, nhưng nó không tự đặt một `Authentication` vào `SecurityContext` của web request. Để sử dụng login và policy của Spring Security nhất quán, hãy cấu hình authentication provider/manager cho Spring Security hoặc viết một integration tương đương được kiểm thử đầy đủ.

### 2.1. Luồng tổng thể

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant F as Spring Security FilterChain
    participant P as LDAP Authentication Provider
    participant L as LDAP Server
    U->>F: Gửi credentials qua HTTPS
    F->>P: Yêu cầu xác thực
    P->>L: Search DN bằng service bind (nếu cần)
    L-->>P: DN của user
    P->>L: Bind bằng DN và mật khẩu user
    alt Bind thất bại
        L-->>P: Từ chối xác thực
        P-->>F: AuthenticationException
        F-->>U: Phản hồi đăng nhập thất bại
    else Bind hợp lệ
        L-->>P: Bind thành công
        P->>L: Tìm nhóm/thuộc tính cần cho quyền
        L-->>P: Dữ liệu membership
        P-->>F: Authentication + authorities
        F->>F: Kiểm tra quyền với endpoint
        F-->>U: Cho phép hoặc từ chối truy cập
    end
~~~

Trong luồng này, bước tìm DN có thể được bỏ qua nếu toàn bộ DN được suy ra đáng tin cậy từ username (ví dụ tất cả user đều nằm dưới cùng OU và dùng `uid` làm RDN). Nếu user nằm ở nhiều OU hoặc DN có thể thay đổi, nên dùng **search filter** để tìm entry rồi bind.

## 3. Chuẩn bị directory, dependencies và cấu hình

### 3.1. Ví dụ schema LDAP

Giả định directory thử nghiệm dùng cấu trúc:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=groups
│   └── cn=report_readers
└── ou=system
    └── cn=svc-ldap-reader
~~~

Một entry người dùng:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
cn: Lan Tran
sn: Tran
mail: lan@example.org
~~~

Một nhóm `groupOfNames`:

~~~ldif
dn: cn=report_readers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: report_readers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Lan thuộc nhóm `report_readers`; Minh không thuộc nhóm này. Tài khoản dịch vụ có quyền tìm user ở `ou=people` và tìm nhóm ở `ou=groups`, nhưng không có quyền đọc mật khẩu hay sửa entry.

> Tên `uid`, `groupOfNames`, `member` và cấu trúc OU chỉ là **schema minh họa**. Trong Active Directory, ứng dụng có thể cần `userPrincipalName`, `sAMAccountName`, nhóm lồng nhau và cách tìm membership khác. Đừng sao chép filter/schema mà chưa đối chiếu directory thật.

### 3.2. Dependencies

Với ứng dụng Spring Boot dùng Maven, khai báo các dependency phù hợp với phiên bản Spring Boot/Spring Security của dự án:

~~~xml
<dependencies>
    <!-- LdapContextSource, LdapTemplate, LDAP data access -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>

    <!-- AuthenticationManager, SecurityFilterChain và HTTP security -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <!-- LDAP authentication provider và LDAP authorities populator -->
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-ldap</artifactId>
    </dependency>
</dependencies>
~~~

Spring LDAP có thể được đưa vào dự án bằng `spring-ldap-core`; starter trên thuận tiện cho Spring Boot vì kết hợp các dependency và auto-configuration phù hợp. Không ghép các phiên bản Spring Security LDAP khác dòng với Spring Boot mà chưa kiểm tra tương thích dependency.

### 3.3. Cấu hình `application.yml`

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_SERVICE_DN}
    password: ${LDAP_SERVICE_PASSWORD}
~~~

Trong đó:

- `spring.ldap.urls` trỏ tới LDAP endpoint; ở ví dụ là **LDAPS**.
- `spring.ldap.base` đặt gốc context chung cho search và group lookup.
- `spring.ldap.username` và `spring.ldap.password` là **credential tài khoản dịch vụ**, không phải tài khoản mà người dùng điền vào form.
- Với Spring Boot có LDAP auto-configuration, một `LdapContextSource` và `LdapTemplate` có thể được khởi tạo từ cấu hình này. `LdapBindAuthenticationManagerFactory` sử dụng context source được inject.

Ví dụ, biến môi trường `LDAP_SERVICE_DN` chứa `cn=svc-ldap-reader,ou=system,dc=example,dc=org`, còn `LDAP_SERVICE_PASSWORD` được cấp qua secret manager.

**Bảo mật:** Chỉ dùng kết nối đã mã hóa và kiểm tra chứng chỉ. Nếu directory yêu cầu StartTLS, cần cấu hình `DirContextAuthenticationStrategy` phù hợp thay cho việc giả định URL `ldap://` đã an toàn. Mật khẩu tài khoản dịch vụ phải được cấp quyền và thay đổi định kỳ theo chính sách tổ chức.

## 4. Cấu hình Spring Security LDAP bằng bind authentication

Đối với đăng nhập bằng LDAP, cơ chế phổ biến là **bind authentication**. Spring Security cung cấp `LdapBindAuthenticationManagerFactory` để tạo một `AuthenticationManager` dựa trên LDAP context source.

### 4.1. Tìm người dùng bằng filter rồi bind

Với schema ở trên, ứng dụng cần tìm người dùng dưới `ou=people` bằng `uid`. Đồng thời, người dùng thuộc nhóm `cn=report_readers,ou=groups` sẽ được ánh xạ thành authority `ROLE_REPORT_READERS`.

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

@Configuration
public class LdapAuthenticationConfig {

    @Bean
    public AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        // Search trong ou=people (tương đối với spring.ldap.base).
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");

        DefaultLdapAuthoritiesPopulator groups =
                new DefaultLdapAuthoritiesPopulator(
                        contextSource, "ou=groups");

        // groupOfNames sử dụng member chứa DN đầy đủ của người dùng.
        groups.setGroupSearchFilter("(member={0})");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("ROLE_");
        groups.setConvertToUpperCase(true);

        factory.setLdapAuthoritiesPopulator(groups);

        // Chỉ đưa những role được ứng dụng phê duyệt vào SecurityContext.
        Set<String> allowed = Set.of("ROLE_REPORT_READERS", "ROLE_STAFF");
        factory.setAuthoritiesMapper(authorities -> authorities.stream()
                .filter(a -> allowed.contains(a.getAuthority()))
                .toList());

        return factory.createAuthenticationManager();
    }
}
~~~

**Cách hoạt động:**

1. `BaseLdapPathContextSource` đại diện kết nối LDAP đã cấu hình. Tài khoản dịch vụ phải có ACL cho search user và group.
2. `setUserSearchBase("ou=people")` giới hạn việc tra cứu user dưới `ou=people,dc=example,dc=org`.
3. `setUserSearchFilter("(uid={0})")` định nghĩa filter mẫu; `{0}` là **placeholder cho username** do thành phần tìm kiếm của Spring Security LDAP thay thế. Không tự nối giá trị người dùng vào filter.
4. `BindAuthenticator` dùng DN tìm được và credential do người dùng gửi để thử **user bind**. Nếu LDAP từ chối, authentication thất bại.
5. `DefaultLdapAuthoritiesPopulator` tìm nhóm dưới `ou=groups`, dùng `(member={0})` với `{0}` là DN của người dùng; lấy `cn` để tạo tên role.
6. Với nhóm `cn=report_readers`, tùy chọn role prefix `ROLE_` và uppercase sẽ tạo `ROLE_REPORT_READERS`.
7. `setAuthoritiesMapper(...)` giữ lại đúng các role đã được ứng dụng cho phép. Điều này giúp tránh tự trao quyền khi directory có các nhóm khác được thêm vào.
8. `createAuthenticationManager()` cung cấp một manager mà các cơ chế HTTP authentication của Spring Security có thể sử dụng.

**Hai loại placeholder `{0}` khác mục đích:** trong user search filter nó đại diện **username**, còn trong group search filter của `DefaultLdapAuthoritiesPopulator` nó đại diện **DN đầy đủ của user**. Với group filter, `{1}` có thể đại diện username nếu implementation hỗ trợ; nên chọn đúng dạng dữ liệu theo schema.

#### Lưu ý khi directory có dữ liệu phức tạp

- Tên đăng nhập phải xác định **duy nhất** một entry trong phạm vi search; không chọn kết quả đầu tiên khi có nhiều entry khớp.
- Một số directory cho phép nhiều OU, nhiều domain hoặc alias. Cần thiết kế filter và ranh giới danh tính rõ ràng.
- Nhóm lồng nhau không phải lúc nào được trả về bởi phép tìm `member` trực tiếp; nếu cần nested membership, phải thiết kế cách giải quyết theo server cụ thể.
- Tài khoản dịch vụ có quyền search không có nghĩa nó được đọc `userPassword`; xác thực bằng bind không yêu cầu đọc hash mật khẩu.
- `setAuthoritiesMapper(...)` trong ví dụ chỉ cho phép role đã được liệt kê, nhưng quyền nghiệp vụ trên tài nguyên vẫn cần được kiểm tra ở tầng ứng dụng.

### 4.2. Biến thể: bind trực tiếp khi DN cố định

Nếu mỗi user chắc chắn có DN theo `uid=<username>,ou=people,dc=example,dc=org`, có thể dùng:

~~~java
LdapBindAuthenticationManagerFactory factory =
        new LdapBindAuthenticationManagerFactory(contextSource);

factory.setUserDnPatterns("uid={0},ou=people");

AuthenticationManager authenticationManager =
        factory.createAuthenticationManager();
~~~

**Chọn một chiến lược tìm user phù hợp** trong cấu hình thực tế: bind theo DN pattern cho cấu trúc cố định, hoặc search filter khi user có thể nằm ở nhiều OU. Với DN pattern, phải để framework thực hiện xử lý ký tự đặc biệt phù hợp và giới hạn username theo chính sách. Tránh ghép DN từ request theo cách nối chuỗi tự phát.

## 5. Kết nối `AuthenticationManager` vào `SecurityFilterChain`

Khi đã có `AuthenticationManager` xác thực qua LDAP, Spring Security cần biết cách sử dụng manager này cho HTTP request và những endpoint nào yêu cầu quyền.

Ví dụ dùng **HTTP Basic qua HTTPS** cho môi trường minh họa/API nội bộ. Với giao diện đăng nhập bằng form hoặc OAuth2, cấu hình HTTP authentication có thể khác.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {

        http.authenticationManager(ldapAuthenticationManager);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/public/**").permitAll()
                .requestMatchers("/reports/**").hasRole("REPORT_READERS")
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ trên thực hiện hai nhóm công việc:

- **Authentication:** HTTP Basic lấy username và password từ request, chuyển sang `AuthenticationManager` dùng LDAP bind; nếu thất bại, request không được xem là đã xác thực.
- **Authorization:** `/reports/**` yêu cầu role `REPORT_READERS`. `hasRole("REPORT_READERS")` tương ứng với authority `ROLE_REPORT_READERS`; `/health` và `/public/**` được cho phép theo chính sách ví dụ.

HTTP Basic **không mã hóa riêng credential** nên phải sử dụng HTTPS từ client đến backend. Với form login dựa trên cookie/session, cần quản lý CSRF, session fixation và logout phù hợp. Với API dùng JWT, phải có thành phần phát hành và xác minh token được thiết kế riêng; Spring Security LDAP **không tự sinh JWT** chỉ vì bind thành công.

Nếu ứng dụng có nhiều `AuthenticationManager` bean hoặc nhiều filter chain, cần chỉ rõ manager đúng cho chain tương ứng bằng qualifier và cấu hình nhất quán; ví dụ giả định chỉ có một manager LDAP dành cho các endpoint nêu trên.

## 6. Nạp nhóm LDAP thành Spring Security authorities

**LDAP group** là cấu trúc của directory; **GrantedAuthority** là dữ liệu Spring Security dùng để xét quyền. Cần một bước ánh xạ có chủ đích giữa hai khái niệm.

### 6.1. Ví dụ từ nhóm thành role

| Group entry trong LDAP | Membership | Authority phía Spring Security | Quyền áp dụng |
|---|---|---|---|
| `cn=report_readers,ou=groups,...` | `member=<DN của Lan>` | `ROLE_REPORT_READERS` | Được kiểm tra tại `/reports/**` |
| `cn=staff,ou=groups,...` | `member=<DN của user>` | `ROLE_STAFF` | Quyền nhân viên do ứng dụng định nghĩa |
| Nhóm không thuộc danh sách cho phép | Tùy entry | Không tạo authority tương ứng | Không tự nâng quyền |

`DefaultLdapAuthoritiesPopulator` mặc định tìm membership theo filter phù hợp cấu hình của nó; ví dụ đã đổi thành `(member={0})` để phù hợp `groupOfNames`. Với `groupOfUniqueNames`, attribute có thể là `uniqueMember`. Với Active Directory, việc xử lý nested group/định danh domain có thể cần một chiến lược riêng.

**Không mặc định tin toàn bộ tên nhóm** dưới một OU là role ứng dụng. Cần biết nhóm nào được quản trị bởi ai, có thể bị người dùng sửa membership hay không, và nhóm nào được ánh xạ vào quyền nhạy cảm.

### 6.2. Bảo vệ nghiệp vụ sâu hơn role

`hasRole("REPORT_READERS")` kiểm tra một quyền chung. Trong ứng dụng thực tế, người dùng có role đọc báo cáo có thể vẫn chỉ được xem báo cáo thuộc phòng ban của mình hoặc dữ liệu không bị hạn chế. Những điều kiện theo tài nguyên phải được kiểm tra tại service/domain.

Ví dụ với method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('REPORT_READERS')")
    public String readOverview() {
        return "Bao cao tong hop";
    }
}
~~~

Để annotation có hiệu lực, cần bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Việc sử dụng `@PreAuthorize` và `SecurityFilterChain` bổ trợ cho nhau: chain kiểm soát điểm vào HTTP, trong khi method security giúp bảo vệ các đường gọi đi vào phương thức nghiệp vụ. Không được dựa chỉ vào ẩn nút trên frontend để bảo vệ chức năng nhạy cảm.

## 7. Khi nào vẫn dùng trực tiếp `LdapTemplate` hoặc `LdapClient`?

Không phải mọi thao tác LDAP đều cần đi qua authentication provider. Ứng dụng vẫn có thể dùng `LdapTemplate`, `LdapClient` hoặc ODM cho:

- Tìm user theo `uid` hoặc email để hiển thị thông tin danh bạ.
- Đọc thuộc tính được cấp phép sau khi người dùng đã được Spring Security xác thực.
- Đọc/sửa entry theo nghiệp vụ quản trị được ủy quyền.
- Tìm nhóm hoặc trạng thái tài khoản khi thư viện và cơ chế authorization của ứng dụng cần thông tin bổ sung.

Ví dụ một dịch vụ tra cứu LDAP:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryLookupService {

    private final LdapTemplate ldapTemplate;

    public DirectoryLookupService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNames(String username) {
        if (username == null || username.isBlank()) {
            return List.of();
        }

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .attributes("cn")
                .where("uid").is(username);

        return ldapTemplate.search(query,
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString());
    }
}
~~~

`LdapTemplate.search(...)` sử dụng context source đã cấu hình; quyền search là quyền của **danh tính thực sự đang bind trên connection**, thường là service account. Dữ liệu được trả về cho người gọi API vẫn phải được kiểm tra quyền ở tầng ứng dụng.

Nếu chỉ cần boolean xác thực bằng LDAP trong một job nội bộ, Spring LDAP có `ldapTemplate.authenticate(query, password)`. Tuy nhiên, với HTTP login cần quản lý principal, authorities, exception và session, dùng Spring Security LDAP làm tầng tích hợp sẽ dễ nhất quán hơn. Nếu tự viết custom `AuthenticationProvider`, không được chỉ trả `true` hay tự đặt `SecurityContext` ở controller mà bỏ qua chính sách bảo mật của framework.

## 8. Bind authentication so với password comparison

Spring Security LDAP hỗ trợ cả hai cách tiếp cận, nhưng ý nghĩa và ràng buộc khác nhau:

| Khía cạnh | Bind authentication | Password comparison |
|---|---|---|
| Cơ chế | Thử bind bằng danh tính user và mật khẩu | So khớp password attribute bằng LDAP Compare hoặc so sánh giá trị đọc được, tùy triển khai |
| Thành phần | `BindAuthenticator` / `LdapBindAuthenticationManagerFactory` | `PasswordComparisonAuthenticator` / factory so sánh mật khẩu |
| Cần đọc password hash không? | Không | Có thể cần nếu so sánh tại ứng dụng; LDAP Compare phụ thuộc server/ACL |
| Chính sách server | User bind đi qua cơ chế xác thực được server áp dụng | Không bảo đảm tương đương user bind trên mọi server |
| Mức độ phù hợp | Cách thường dùng cho ứng dụng LDAP thông thường | Chỉ cân nhắc khi có lý do rõ ràng, schema và hỗ trợ tương ứng |

Các directory có thể lưu mật khẩu dưới dạng hash với salt hoặc không cho đọc thuộc tính mật khẩu. Một phép LDAP Compare không mặc nhiên thực hiện đúng toàn bộ quy trình xác thực và chính sách khóa tài khoản. **Đừng chuyển sang password comparison chỉ để tránh lỗi quyền đọc password**; lỗi đó thường là dấu hiệu thư mục đang bảo vệ credential đúng cách.

## 9. Những vấn đề vận hành và bảo mật thường gặp

### 9.1. Service account, user bind và quyền tối thiểu

Để tìm DN và nhóm, backend thường dùng tài khoản dịch vụ như `cn=svc-ldap-reader,ou=system,dc=example,dc=org`. Tài khoản này nên:

- Có quyền search/read chỉ trên OU và thuộc tính cần cho login và group lookup.
- Không có quyền đọc `userPassword`, sửa ACL, xóa entry hay quản trị toàn thư mục.
- Có credential được quản lý trong secret manager, xoay định kỳ và phân tách giữa môi trường.
- Được giám sát khi lỗi bind hoặc thực hiện truy vấn bất thường.

User bind dùng **mật khẩu người dùng cuối** để LDAP xác thực. Không thay mật khẩu service account trong cấu hình bằng mật khẩu người dùng. Không tái sử dụng ngữ cảnh đã bind bằng user như context mặc định cho mọi request; nếu bật pooling, kiểm soát kỹ danh tính và vòng đời connection.

### 9.2. Bảo vệ TLS ở cả hai chặng

~~~text
Trình duyệt --HTTPS--> Backend Spring --LDAPS/StartTLS--> LDAP Server
~~~

Chứng chỉ LDAP server phải được xác minh theo truststore/SSL bundle phù hợp. Không tắt hostname verification hoặc hạ cấp sang kết nối `ldap://` không mã hóa khi TLS lỗi. HTTP Basic và form login đều cần bảo vệ credential ở chặng client → backend bằng HTTPS.

### 9.3. Một số lỗi cần phân biệt

| Tình huống | Kết quả cần hiểu | Hướng xử lý |
|---|---|---|
| Service bind sai password | Backend chưa thể search | Kiểm tra service DN/secret; báo lỗi dịch vụ |
| User không tồn tại trong vùng search | Không xác định được danh tính | Trả thất bại xác thực trung tính; rà soát base/scope khi cần |
| Username khớp nhiều DN | Danh tính mơ hồ | Từ chối an toàn và điều chỉnh chính sách uniqueness |
| User bind sai mật khẩu | LDAP không chấp nhận credential | Không cấp `Authentication` hợp lệ; tránh log password |
| Mật khẩu rỗng | Có thể gặp anonymous/unauthenticated bind ở một số server | Từ chối trước khi gửi bind |
| Search group thiếu ACL | Authorities có thể thiếu hoặc lookup lỗi | Không cấp role chưa xác minh; giám sát lỗi quyền |
| Group CN không khớp mapping | Role được tạo không giống role endpoint cần | Kiểm tra `ROLE_`, chữ hoa/thường, policy map nhóm |
| LDAP timeout hoặc TLS lỗi | Hạ tầng hoặc cấu hình chưa ổn | Xử lý theo nhánh lỗi dịch vụ; không coi là sai password |
| User đã xóa khỏi nhóm nhưng session còn role | Dữ liệu phân quyền bị cũ | Thiết kế TTL, refresh hoặc cơ chế thu hồi |
| User đã xác thực nhưng thiếu role | Authentication thành công, authorization thất bại | Trả `403` theo cơ chế bảo mật; không tăng quyền vì login đúng |

Phản hồi công khai nên tránh tiết lộ tài khoản có tồn tại hay không. Log kỹ thuật nên phân biệt lỗi LDAP service, lỗi user bind và lỗi tra quyền bằng correlation ID mà không ghi credential/secret hoặc toàn bộ entry nhạy cảm.

### 9.4. Một số bẫy tích hợp

1. **Chỉ gọi `ldapTemplate.authenticate(...)` trong controller rồi lưu cờ `loggedIn=true`.** Cách này không tích hợp đầy đủ với `AuthenticationManager`, `SecurityContext`, session và authorities.
2. **Dùng service bind thành công làm bằng chứng user đăng nhập.** Service bind chỉ chứng minh backend được server chấp nhận.
3. **Tự xây filter bằng chuỗi người dùng.** Hãy dùng API query builder của Spring LDAP hoặc placeholder của thành phần Spring Security LDAP; không đưa điều kiện filter tùy ý từ client.
4. **Quên cấu hình group filter.** `groupOfNames` thường dùng `member` trong khi một cơ chế tìm nhóm mặc định có thể kỳ vọng `uniqueMember`; phải đối chiếu schema.
5. **Nhầm `hasRole` với `hasAuthority`.** `hasRole("REPORT_READERS")` kiểm tra authority `ROLE_REPORT_READERS` theo role prefix mặc định, trong khi `hasAuthority("ROLE_REPORT_READERS")` dùng đúng chuỗi authority.
6. **Trộn bản phát hành Spring LDAP/Spring Security.** Dùng dependency management thống nhất và kiểm tra API theo phiên bản ứng dụng.
7. **Cấp role dựa trên tên nhóm không đáng tin.** Role nhạy cảm nên đi qua mapping có kiểm soát; không cấp quyền theo mọi `cn` được tìm thấy.
8. **Chỉ phân quyền lúc login.** Quyền trên tài nguyên cụ thể và những thay đổi membership sau login phải được xét trong chính sách authorization.

## 10. Kiểm thử tích hợp

Có thể chia kiểm thử thành ba lớp:

| Lớp kiểm thử | Mục đích | Cách thực hiện |
|---|---|---|
| LDAP connectivity và bind | Kiểm tra TLS, service bind, user bind | Directory thử nghiệm/embedded LDAP hoặc container LDAP |
| LDAP group mapping | Kiểm tra filter, quyền tìm nhóm, role prefix | Dataset LDIF có user, group, membership rõ ràng |
| Spring Security authorization | Kiểm tra HTTP và method security | `spring-security-test` với request/principal mô phỏng hoặc integration test |

### 10.1. Dữ liệu thử nghiệm

Tạo ít nhất hai người dùng:

- `uid=lan`: mật khẩu đúng, thuộc `cn=report_readers`.
- `uid=minh`: mật khẩu đúng, không thuộc nhóm đó.

Tài khoản dịch vụ có quyền tìm cả hai user và tra nhóm nhưng không có quyền đọc mật khẩu. Đảm bảo máy chủ thử nghiệm cho phép simple bind trên kết nối có TLS; nếu dùng embedded server, cấu hình riêng endpoint và trust material phù hợp.

### 10.2. Ma trận tình huống

| Trường hợp | Authentication | Kết quả endpoint `/reports/**` |
|---|---|---|
| Không gửi credential | Chưa có phiên xác thực | Bị từ chối, thường `401` với HTTP Basic |
| Lan + mật khẩu sai | Thất bại | Không truy cập |
| Lan + mật khẩu đúng và thuộc `report_readers` | Thành công, có `ROLE_REPORT_READERS` | Được phép theo policy |
| Minh + mật khẩu đúng nhưng không thuộc nhóm | Thành công, không có role báo cáo | Bị từ chối, thường `403` |
| Username không tồn tại | Không tìm được DN hợp lệ | Không truy cập; phản hồi không tiết lộ account tồn tại |
| Username chứa `*` hoặc dấu ngoặc | Không làm biến đổi filter ngoài ý muốn | Không truy cập ngoài danh tính cụ thể đã xác thực |
| Mật khẩu rỗng | Bị từ chối | Không truy cập |
| Service account bị thu hồi quyền search | Không thể tra cứu danh tính/nhóm phù hợp | Không cấp quyền; ghi nhận lỗi hạ tầng/quyền |
| Hai user cùng username trong vùng search | Định danh mơ hồ | Không chọn một DN bất kỳ để cấp role |
| Certificate LDAPS không hợp lệ | Không kết nối được an toàn | Không hạ cấp; trả lỗi dịch vụ thích hợp |
| Vai trò của Lan bị thu hồi sau khi login | Phụ thuộc cơ chế session/token | Quyền phải được làm mới/thu hồi theo chính sách |

### 10.3. Những assertion quan trọng

- **Credential không bị log** trong application log, exception handler hoặc tracing.
- Request hợp lệ tạo được `Authentication` có principal phù hợp và authorities đúng mapping.
- Kết quả xác thực thất bại **không** tạo một principal được coi là đã đăng nhập.
- Role mapping **không** trao role quản trị từ một nhóm không được cho phép.
- Một người đã đăng nhập nhưng thiếu role vẫn bị từ chối chức năng bảo vệ.
- Lỗi kết nối LDAP và lỗi tra nhóm được phân biệt với mật khẩu người dùng sai trong log kỹ thuật.
- Không có quyền truy cập tài nguyên của người khác chỉ vì service account LDAP có quyền đọc rộng hơn user.

**Lưu ý về phạm vi:** Test `@WithMockUser(roles = "REPORT_READERS")` giúp kiểm tra authorization của HTTP/method security, **không chứng minh LDAP bind và group lookup hoạt động**. Cần thêm integration test có LDAP server thử nghiệm và dữ liệu thực cho phần xác thực/tra nhóm.

## 11. Bài tập tự kiểm tra

1. Vì sao `LdapTemplate.authenticate(...)` trả `true` chưa đủ để coi một request Spring Security đã đăng nhập hợp lệ?
2. Khi nào bạn chọn `setUserDnPatterns(...)`, khi nào chọn `setUserSearchFilter(...)`?
3. Filter `(member={0})` trong `DefaultLdapAuthoritiesPopulator` sử dụng giá trị nào thay `{0}`?
4. Nếu nhóm LDAP có `cn=report_readers`, tổ hợp `ROLE_` và `setConvertToUpperCase(true)` tạo authority nào?
5. Vì sao `hasRole("REPORT_READERS")` và `hasAuthority("ROLE_REPORT_READERS")` tương đương trong cấu hình role prefix mặc định?
6. Điều gì xảy ra nếu user bind thành công nhưng tài khoản dịch vụ không thể search nhóm?
7. Nếu một trang admin chỉ được ẩn ở frontend, liệu Spring Security đã bảo vệ API tương ứng chưa?
8. Vì sao test với `@WithMockUser` chưa đủ để chứng minh toàn bộ tích hợp Spring Security LDAP hoạt động?

**Gợi ý trả lời:** (1) Cần `Authentication`/`SecurityContext` và cơ chế phiên/request của Spring Security. (2) DN pattern khi DN ổn định; search filter khi phải tìm DN. (3) DN người dùng đã tìm. (4) `ROLE_REPORT_READERS`. (5) `hasRole` bổ sung role prefix mặc định; `hasAuthority` kiểm tra chuỗi đầy đủ. (6) Không được cấp role chưa xác minh; phân loại lỗi và từ chối quyền. (7) Chưa; phải kiểm tra ở backend. (8) `@WithMockUser` bỏ qua LDAP bind và lookup thực.

## 12. Tài liệu tham khảo

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): bind authentication, user DN pattern, search filter và password comparison.
- [Spring Security — `DefaultLdapAuthoritiesPopulator` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html): group search base/filter, role prefix, thuộc tính role.
- [Spring Boot — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap): auto-configuration `LdapContextSource`/`LdapTemplate`, properties và TLS.

## Kết luận

**Spring LDAP** phụ trách thao tác với thư mục thông qua `ContextSource`, `LdapTemplate` và các API LDAP khác; **Spring Security LDAP** đưa việc xác thực bằng LDAP vào `AuthenticationManager` và luồng Spring Security. Mô hình triển khai thường dùng là **service bind để tìm DN → user bind để xác thực → nạp nhóm thành authority → kiểm tra quyền tại HTTP/service**. Cấu hình an toàn phải dùng TLS có xác minh chứng chỉ, quyền tìm kiếm tối thiểu, định danh duy nhất, group mapping đáng tin cậy và kiểm thử tách biệt authentication với authorization.
