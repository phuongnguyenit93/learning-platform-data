# Ánh xạ LDAP group, UserDetailsContextMapper và bảo vệ kết nối LDAP trong Spring Security Servlet

## 1. Bài toán: xác thực bằng LDAP, cấp quyền theo ứng dụng

Một ứng dụng Spring Boot chạy trên **Servlet stack** có người dùng được quản lý trong LDAP (Lightweight Directory Access Protocol). Nhân viên đăng nhập bằng username/password trong directory. Directory còn có các **group** như `PORTAL_READERS` và `PORTAL_OPERATORS`, trong khi Spring Security phải quyết định người dùng có quyền `ROLE_READER` hoặc `ROLE_OPERATOR` trong ứng dụng hay không.

Ba việc này liên quan nhưng khác nhau:

1. **LDAP authentication:** Xác minh thông tin đăng nhập qua LDAP, thường bằng **bind** với tài khoản người dùng. Nếu LDAP không chấp nhận thông tin đăng nhập, ứng dụng không tạo phiên đã xác thực.
2. **LDAP authority retrieval:** Tìm group mà người dùng thuộc về, từ một schema/group search base được cấu hình. Spring Security có thể biến tên group thành những `GrantedAuthority` ban đầu.
3. **Application authorization:** Chuyển **nhóm LDAP đã được quản trị tin cậy** thành vai trò ứng dụng được chấp thuận, kiểm tra trạng thái tài khoản/chính sách nội bộ và dùng `hasRole` hoặc `hasAuthority` để bảo vệ URL.

**`UserDetailsContextMapper`** là điểm mở rộng để chuyển đối tượng LDAP user + authorities vừa tìm được thành **`UserDetails`** (principal) phù hợp với hệ thống. Nó không phải là cơ chế tạo kết nối TLS, cũng không tự thực hiện tất cả việc tìm group.

Mặt khác, dù authentication/role mapping đúng, nếu ứng dụng truyền password hoặc thông tin directory nhạy cảm qua kết nối không bảo vệ, tài khoản vẫn gặp rủi ro. Vì thế **LDAPS hoặc StartTLS, xác minh chứng chỉ và quản lý secret** là một phần thiết yếu của bài toán.

Mục tiêu của bài: hiểu luồng LDAP bind và group lookup của Spring Security 6, viết một mapper kiểm soát group-to-role, tạo demo Java 17, dùng LDAP qua TLS và kiểm tra được các tình huống thành công/thất bại.

## 2. Cấu trúc directory: DN, OU, user và group

LDAP không phải bảng quan hệ SQL. Một entry có **Distinguished Name (DN)** xác định vị trí trong cây directory, chứa các attribute và object class theo schema.

Ví dụ directory minh họa:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice,ou=people,dc=example,dc=org
│   └── uid=bob,ou=people,dc=example,dc=org
├── ou=groups
│   ├── cn=PORTAL_READERS,ou=groups,dc=example,dc=org
│   └── cn=PORTAL_OPERATORS,ou=groups,dc=example,dc=org
└── ou=service
    └── cn=app-reader,ou=service,dc=example,dc=org
~~~

Ý nghĩa các từ quan trọng:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `DN` | Định danh đầy đủ của entry trong cây LDAP | `uid=alice,ou=people,dc=example,dc=org` |
| `RDN` | Thành phần tương đối tại một cấp của DN | `uid=alice` |
| `base DN` | Điểm gốc để thực hiện tìm kiếm tương đối | `dc=example,dc=org` |
| `OU` | Organizational Unit, cách tổ chức các entry | `ou=people`, `ou=groups` |
| `uid` | Thuộc tính có thể dùng để đăng nhập tùy schema | `alice` |
| `cn` | Common Name, thường là tên nhóm hoặc entry | `PORTAL_READERS` |
| `member` / `uniqueMember` | Thuộc tính lưu DN thành viên của group tùy objectClass/schema | `uid=alice,ou=people,dc=example,dc=org` |
| `memberOf` | Thuộc tính group membership do một số server như AD cung cấp | Không mặc định tồn tại ở mọi LDAP |
| `objectClass` | Xác định schema/attribute của entry | `inetOrgPerson`, `groupOfUniqueNames` |

Một nhóm thuộc kiểu `groupOfUniqueNames` có thể được mô tả bằng LDIF sau. Đây là **dữ liệu minh họa cần directory thật để nhập**, không phải dữ liệu được demo Java tự tạo:

~~~ldif
dn: cn=PORTAL_READERS,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: PORTAL_READERS
uniqueMember: uid=alice,ou=people,dc=example,dc=org

dn: cn=PORTAL_OPERATORS,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: PORTAL_OPERATORS
uniqueMember: uid=bob,ou=people,dc=example,dc=org
~~~

Với `groupOfNames`, thuộc tính membership thông dụng là `member`. Với **Active Directory**, user và group thường dùng schema, user lookup và group membership khác; không mặc định rằng `uid`, `ou=people` và `uniqueMember` tồn tại. Chỉ dùng đúng filter/base/attribute theo directory đang kết nối.

Một account phục vụ tra cứu (`cn=app-reader,...`) có thể có quyền **đọc group và thuộc tính cần thiết**, trong khi password người dùng chỉ được LDAP xác thực bằng bind. Phân quyền đọc LDAP cho service account ở mức tối thiểu; không cần cấp quyền sửa directory cho ứng dụng chỉ thực hiện login.

## 3. Luồng xác thực LDAP trong Spring Security Servlet

Spring Security LDAP có các thành phần tiêu biểu:

- **`LdapContextSource`** (Spring LDAP): Cấu hình server URL, base DN và thông tin kết nối/tra cứu.
- **`BindAuthenticator`**: Dùng DN của người dùng và password để thực hiện LDAP bind, qua đó yêu cầu LDAP server xác thực.
- **`DefaultLdapAuthoritiesPopulator`**: Tìm các LDAP group khớp user DN/username bằng filter, lấy role attribute và chuyển sang tập `GrantedAuthority`.
- **`UserDetailsContextMapper`**: Nhận `DirContextOperations`, username và authorities; xây `UserDetails` cho principal của ứng dụng.
- **`LdapAuthenticationProvider`**: Phối hợp authenticator, authorities populator và context mapper.
- **`SecurityFilterChain`**: Dùng provider cho form login; bước authorization sau đó dựa vào authorities của `Authentication`.

~~~text
Browser POST /login (username + password + CSRF token)
         |
         v
Spring Security UsernamePasswordAuthenticationFilter
         |
         v
LdapAuthenticationProvider
         |
         +-- BindAuthenticator
         |      |
         |      +--> Xác định user DN theo pattern/search
         |      +--> LDAP bind qua kết nối TLS
         |      +--> Password sai? Authentication fail
         |
         +-- DefaultLdapAuthoritiesPopulator
         |      |
         |      +--> Search group theo user DN / username
         |      +--> cn=PORTAL_READERS -> LDAP_PORTAL_READERS
         |
         +-- UserDetailsContextMapper
                |
                +--> LDAP_PORTAL_READERS -> ROLE_READER
                +--> LDAP_PORTAL_OPERATORS -> ROLE_OPERATOR
                +--> Chưa thuộc nhóm được duyệt? Từ chối hoặc không cấp role
                |
                v
         Authentication trong SecurityContext
                |
                v
         AuthorizationFilter
         /me -> ROLE_READER hoặc ROLE_OPERATOR
         /ops -> ROLE_OPERATOR
~~~

**Quan trọng:** Nhập password đúng có thể chứng minh user tồn tại và được LDAP xác thực, nhưng **không chứng minh user có quyền sử dụng ứng dụng**. Việc ánh xạ group đến `ROLE_*` là quyết định của ứng dụng. Một user không thuộc group được duyệt có thể bị từ chối login (như demo) hoặc được login nhưng chặn truy cập từng URL, tùy chính sách.

LDAP bind nên sử dụng **TLS trước khi truyền credential**. `ldap://` không có StartTLS chủ động là kết nối LDAP thông thường; không coi `ldap://` mặc định là đường truyền an toàn.

## 4. Group lookup: filter và cách tạo GrantedAuthority

Trong Spring Security, `DefaultLdapAuthoritiesPopulator` có thể được cấu hình để tìm group dưới một **group search base**. Ví dụ:

~~~java
// Mảnh cấu hình Java bên trong phương thức tạo provider:
DefaultLdapAuthoritiesPopulator groups =
        new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
groups.setGroupSearchFilter("(uniqueMember={0})");
groups.setGroupRoleAttribute("cn");
groups.setRolePrefix("LDAP_");
groups.setConvertToUpperCase(true);
~~~

Ý nghĩa:

- `"ou=groups"` là search base **tương đối với base DN** đã đặt trong `LdapContextSource`.
- `(uniqueMember={0})` dùng `{0}` làm **full user DN** để tìm các group có thành viên là user đó. Một số LDAP schema cần `(member={0})`, hoặc search dựa trên username qua `{1}`. Chọn filter sau khi xác minh schema và dữ liệu thực.
- `setGroupRoleAttribute("cn")` lấy tên nhóm từ `cn` của group entry.
- `setRolePrefix("LDAP_")` và `setConvertToUpperCase(true)` tạo tên quyền như `LDAP_PORTAL_READERS` từ `cn=PORTAL_READERS`. Prefix `LDAP_` giúp tách **nhóm đến từ directory** khỏi **role ứng dụng `ROLE_*`**.
- Mapping chỉ áp dụng khi truy vấn group tìm được entry và account tra cứu có đủ quyền đọc; đừng nhầm “authentication thành công nhưng không có authorities” với lỗi password.

`{0}` và `{1}` trong filter là placeholder do API search của Spring Security xử lý; tránh tự nối username nhập từ request vào LDAP filter hoặc DN mà không dùng cơ chế escape của thư viện. LDAP filter injection khác SQL injection nhưng cũng nguy hiểm khi tên/ngữ cảnh được ghép thủ công.

**Nhóm lồng nhau (nested groups)** thường không được truy vấn đệ quy chỉ bằng filter trực tiếp `uniqueMember={0}`. Active Directory có thể dùng các cơ chế truy vấn thành viên riêng, nhưng đó là giải pháp schema/vendor-specific; cần đặc tả rõ cách xử lý group lồng nhau, vòng lặp, deny và giới hạn độ sâu. Không giả định một user nằm trong nhóm cha thông qua nhóm con sẽ được tính vào kết quả mặc định.

### 4.1. Từ LDAP group sang role nội bộ

Một bảng ánh xạ tường minh là cách dễ kiểm soát nhất:

| LDAP authority đã tra được | Vai trò nội bộ | Được làm gì trong demo |
| --- | --- | --- |
| `LDAP_PORTAL_READERS` | `ROLE_READER` | Xem `/me` |
| `LDAP_PORTAL_OPERATORS` | `ROLE_OPERATOR` | Xem `/me` và `/ops` |
| `LDAP_OTHER_GROUP` | Không tự cấp role | Không tự có quyền trong ứng dụng |
| Không tìm thấy group hợp lệ | Không có role, demo từ chối login | Không cho truy cập |

Tên group nằm trong LDAP, nhưng quyền nhóm được cấp/phân công bởi quản trị viên directory. Một directory có thể bị sai cấu hình hoặc group bị quản trị ngoài phạm vi tin cậy; cần chọn group thuộc domain/OU đáng tin, quy định ai được chỉnh sửa membership và kiểm tra thay đổi quyền.

**Không dùng kiểu mapping** “mọi `cn` thành `ROLE_<CN>`” nếu group không do bộ phận được ủy quyền quản lý. Đặc biệt tránh suy luận `cn=admins` bên ngoài luôn tương đương `ROLE_ADMIN` của ứng dụng.

## 5. UserDetailsContextMapper làm gì?

Giao diện `org.springframework.security.ldap.userdetails.UserDetailsContextMapper` định nghĩa hai chiều:

~~~java
UserDetails mapUserFromContext(
    DirContextOperations ctx,
    String username,
    Collection<? extends GrantedAuthority> authorities
);

void mapUserToContext(
    UserDetails user,
    DirContextAdapter ctx
);
~~~

- **`mapUserFromContext`** là đường dùng trong quá trình nạp principal sau khi LDAP authentication/lookup hoàn tất. Nó nhận `ctx` để đọc thuộc tính user từ LDAP, username của phiên và tập LDAP authorities đã được authorities populator cấp.
- **`mapUserToContext`** phục vụ chiều ghi thông tin từ `UserDetails` về LDAP context trong các kịch bản thích hợp. Với ứng dụng **chỉ đăng nhập và không cập nhật LDAP**, không thực hiện LDAP write; có thể báo unsupported trong mapper chỉ đọc.
- Mapper có thể chuẩn hóa tên hiển thị, kiểm tra account status, gắn local user ID khi tích hợp database và chuyển group vào authorities. Nếu cần local ID bền vững hoặc trạng thái khóa nội bộ, hãy dùng repository/chính sách do ứng dụng sở hữu. Demo chỉ tập trung role.
- Mapper **không** thay LDAP bind, không kiểm chứng mật khẩu và không làm kết nối tự động có TLS. Nó cũng không thay SecurityFilterChain authorization.

Lưu ý `UserDetails.getPassword()` của demo không chứa password LDAP, và **không nên** lấy `userPassword` từ LDAP về để ứng dụng tự so sánh hay lưu lại. Authentication provider dùng LDAP bind để kiểm tra password; mapper chỉ xây principal đã xác thực.

## 6. Ví dụ Spring Boot 3.3.5 / Java 17 với LDAP bind và group mapping

Ví dụ sử dụng **directory LDAP thật** theo schema minh họa ở mục 2. Để chạy thành công cần một LDAP server LDAPS hợp lệ, hai user `alice`/`bob`, nhóm như LDIF, service account chỉ đọc, chứng chỉ được JVM tin cậy, và biến môi trường cho endpoint/credentials. Mã có thể biên dịch với Maven/JDK 17+ khi đủ dependency; bài không tự triển khai hay tạo account LDAP.

Cấu trúc:

~~~text
ldap-group-demo/
  pom.xml
  src/main/java/example/ldap/LdapGroupDemoApplication.java
  src/main/resources/application.yml
  src/test/java/example/ldap/ApprovedGroupMapperTests.java
~~~

### 6.1. Maven

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>ldap-group-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-ldap</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-security-ldap` cung cấp LDAP authentication provider, authorities populator và các cấu hình LDAP của Spring Security. `spring-boot-starter-security` cung cấp form login và Servlet security chain. `spring-boot-starter-test` có JUnit 5, AssertJ và Mockito để test mapper tách biệt với server.

### 6.2. Cấu hình qua biến môi trường

**src/main/resources/application.yml:**

~~~yaml
demo:
  ldap:
    url: ${LDAP_URL}
    base: ${LDAP_BASE}
    bind-dn: ${LDAP_BIND_DN}
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Ví dụ dùng `LDAP_URL=ldaps://ldap.example.org:636` và `LDAP_BASE=dc=example,dc=org`. DN của service account là `cn=app-reader,ou=service,dc=example,dc=org`. **Không** ghi mật khẩu thật trong Git, tài liệu hoặc response; truyền từ secret store / environment phù hợp.

### 6.3. Application và security configuration

**src/main/java/example/ldap/LdapGroupDemoApplication.java:**

~~~java
package example.ldap;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.ldap.authentication.BindAuthenticator;
import org.springframework.security.ldap.authentication.LdapAuthenticationProvider;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.ldap.userdetails.UserDetailsContextMapper;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LdapGroupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LdapGroupDemoApplication.class, args);
    }

    @Bean
    LdapContextSource contextSource(
            @Value("${demo.ldap.url}") String url,
            @Value("${demo.ldap.base}") String base,
            @Value("${demo.ldap.bind-dn}") String bindDn,
            @Value("${demo.ldap.bind-password}") String bindPassword)
            throws Exception {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);  // Dùng ldaps:// trong demo.
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(bindPassword);
        source.afterPropertiesSet();
        return source;
    }

    @Bean
    UserDetailsContextMapper ldapUserDetailsContextMapper() {
        return new ApprovedGroupMapper();
    }

    @Bean
    LdapAuthenticationProvider ldapAuthenticationProvider(
            LdapContextSource contextSource,
            UserDetailsContextMapper mapper) {

        BindAuthenticator authenticator =
                new BindAuthenticator(contextSource);

        // DN pattern tương đối với base dc=example,dc=org.
        authenticator.setUserDnPatterns(
                new String[] {"uid={0},ou=people"});

        DefaultLdapAuthoritiesPopulator groups =
                new DefaultLdapAuthoritiesPopulator(
                        contextSource, "ou=groups");

        // Phù hợp với schema groupOfUniqueNames của demo.
        groups.setGroupSearchFilter("(uniqueMember={0})");
        groups.setGroupRoleAttribute("cn");
        groups.setRolePrefix("LDAP_");
        groups.setConvertToUpperCase(true);

        LdapAuthenticationProvider provider =
                new LdapAuthenticationProvider(authenticator, groups);

        provider.setUserDetailsContextMapper(mapper);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LdapAuthenticationProvider ldapProvider) throws Exception {

        return http
                .authenticationProvider(ldapProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/ops").hasRole("OPERATOR")
                        .anyRequest().hasAnyRole("READER", "OPERATOR"))
                .formLogin(Customizer.withDefaults())
                .build();
    }

    static final class ApprovedGroupMapper
            implements UserDetailsContextMapper {

        @Override
        public UserDetails mapUserFromContext(
                DirContextOperations ctx,
                String username,
                Collection<? extends GrantedAuthority> authorities) {

            Set<String> ldapGroups = authorities.stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());

            List<GrantedAuthority> appRoles = new ArrayList<>();

            if (ldapGroups.contains("LDAP_PORTAL_READERS")) {
                appRoles.add(new SimpleGrantedAuthority("ROLE_READER"));
            }

            if (ldapGroups.contains("LDAP_PORTAL_OPERATORS")) {
                appRoles.add(new SimpleGrantedAuthority("ROLE_OPERATOR"));
            }

            if (appRoles.isEmpty()) {
                // Không đủ quyền dùng ứng dụng dù LDAP bind có thể đúng.
                throw new DisabledException("No approved application group");
            }

            // Không đưa LDAP password vào principal.
            return new User(
                    username, "",
                    true, true, true, true,
                    appRoles);
        }

        @Override
        public void mapUserToContext(
                UserDetails user, DirContextAdapter ctx) {
            throw new UnsupportedOperationException(
                    "This application does not write user data to LDAP");
        }
    }

    @RestController
    static class DemoController {

        @GetMapping("/")
        String home() {
            return "Sign in using the directory account";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                    "username", authentication.getName(),
                    "authorities", authentication.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList());
        }

        @GetMapping("/ops")
        String operations() {
            return "Operator access granted";
        }
    }
}
~~~

**Điều gì diễn ra sau khi nhập form login?**

1. Form login do Spring Security sinh gửi POST đến `/login`, kèm CSRF token của form như cấu hình mặc định.
2. Security chain dùng `LdapAuthenticationProvider`; `BindAuthenticator` tạo DN `uid=alice,ou=people,dc=example,dc=org` tương ứng base và thử bind qua LDAPS với password.
3. Sau bind thành công, `DefaultLdapAuthoritiesPopulator` tìm group có `uniqueMember` bằng DN user và trả các quyền LDAP_*.
4. `ApprovedGroupMapper` đối chiếu whitelist:
   - `LDAP_PORTAL_READERS` → `ROLE_READER`.
   - `LDAP_PORTAL_OPERATORS` → `ROLE_OPERATOR`.
   - Không có nhóm được duyệt → ném `DisabledException`, đăng nhập thất bại theo policy demo.
5. `SecurityFilterChain` tiếp tục dùng các role từ principal: người có `ROLE_READER` hoặc `ROLE_OPERATOR` đọc `/me`; chỉ `ROLE_OPERATOR` đọc `/ops`.

**Role không tự kế thừa trong Spring Security**: `ROLE_OPERATOR` không tự chứa `ROLE_READER`. Đó là lý do `/me` dùng `hasAnyRole("READER","OPERATOR")`; muốn quan hệ thứ bậc role phải cấu hình rõ ràng và kiểm tra tính nhất quán.

Mã trả `User` với password rỗng **chỉ là principal sau bind**; không xác thực mật khẩu bằng cách so sánh với chuỗi rỗng. Không sử dụng principal này cho một `DaoAuthenticationProvider` khác mà thiếu chính sách password. Trong production nên xử lý thêm trạng thái tài khoản từ database của ứng dụng và chọn thông điệp lỗi login không tiết lộ quá nhiều về user/group.

### 6.4. Cách chạy với directory thật

Trước hết xác nhận DN/group schema trên LDAP server và giấy chứng nhận máy chủ LDAPS đã được JVM tin cậy. Trong Bash/Git Bash, chuẩn bị environment:

~~~bash
export LDAP_URL='ldaps://ldap.example.org:636'
export LDAP_BASE='dc=example,dc=org'
export LDAP_BIND_DN='cn=app-reader,ou=service,dc=example,dc=org'
# Đọc LDAP_BIND_PASSWORD từ secret được cấp trong môi trường,
# không hard-code mật khẩu vào source hay lịch sử shell.

mvn spring-boot:run
~~~

Ứng dụng cần biến `LDAP_BIND_PASSWORD` được cấp bởi deployment/secret manager. Nếu thiếu giá trị, Spring không thể giải quyết placeholder từ YAML. URL và DN minh họa phải được đổi sang máy chủ/directory thật, và user pattern phải khớp schema. Nếu directory dùng `mail` hoặc `sAMAccountName` thay vì `uid`, cần điều chỉnh chiến lược tìm DN và cấu hình group search; không được tự suy luận username là DN.

Mở `http://localhost:8080/`, truy cập `http://localhost:8080/me` để được chuyển tới trang login, nhập tài khoản từ directory. Sau khi login thành công, request tới `/me` sẽ trả JSON tương tự:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

Đây là **hình dạng output minh họa** khi `alice` thuộc `PORTAL_READERS`; không phải kết quả cố định nếu LDAP directory khác. Đăng nhập `bob` thuộc `PORTAL_OPERATORS` có thể truy cập `/ops`, nhận chuỗi `Operator access granted`. Người không thuộc hai nhóm được duyệt không có principal hợp lệ theo policy của mapper demo.

Nếu dùng `curl` trực tiếp mà không có cookie/session và CSRF token cho POST login, kết quả không tương đương thao tác đăng nhập từ form browser; để thử LDAP bind có thể dùng công cụ LDAP client riêng đã được cấu hình TLS.

## 7. Test mapper mà không cần server LDAP thật

Vì mapper chỉ chuyển authorities thành role, có thể test độc lập với JUnit 5 và Mockito. Đây là **unit test**: nó không thay thế test bind TLS, group search LDAP hoặc login flow.

**src/test/java/example/ldap/ApprovedGroupMapperTests.java:**

~~~java
package example.ldap;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class ApprovedGroupMapperTests {

    private final LdapGroupDemoApplication.ApprovedGroupMapper mapper =
            new LdapGroupDemoApplication.ApprovedGroupMapper();

    private final DirContextOperations ctx =
            mock(DirContextOperations.class);

    @Test
    void readerGroupGetsOnlyReaderRole() {
        UserDetails user = mapper.mapUserFromContext(
                ctx, "alice",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_PORTAL_READERS")));

        assertThat(user.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_READER");
        assertThat(user.getUsername()).isEqualTo("alice");
    }

    @Test
    void operatorGroupGetsOperatorRole() {
        UserDetails user = mapper.mapUserFromContext(
                ctx, "bob",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_PORTAL_OPERATORS")));

        assertThat(user.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_OPERATOR");
    }

    @Test
    void unrelatedGroupIsNotAnApplicationRole() {
        assertThatThrownBy(() -> mapper.mapUserFromContext(
                ctx, "guest",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_UNRELATED"))))
                .isInstanceOf(DisabledException.class);
    }

    @Test
    void groupsAreMappedByWhitelistNotByArbitraryAdminName() {
        assertThatThrownBy(() -> mapper.mapUserFromContext(
                ctx, "someone",
                List.of(new SimpleGrantedAuthority(
                        "LDAP_ADMIN"))))
                .isInstanceOf(DisabledException.class);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test chứng minh hai group được phép chuyển thành local roles, group không thuộc whitelist không tạo quyền và tên `LDAP_ADMIN` không có đặc quyền chỉ vì trông giống nhóm quản trị. Với map thực tế phức tạp hơn, nên test case nhiều group, trùng group, group bị vô hiệu hóa, tenant mismatch và trạng thái tài khoản.

Để kiểm end-to-end, tạo directory thử nghiệm có fixture user/group, cấu hình chứng chỉ TLS tin cậy, thực hiện login qua browser/MockMvc với session + CSRF và kiểm status `/me`, `/ops`. Test group mapper thuần túy **không chứng minh** `DefaultLdapAuthoritiesPopulator` có tìm được group đúng từ directory.

## 8. Bảo vệ kết nối LDAP: LDAPS và StartTLS

Khi LDAP client làm bind, password hoặc credential có thể đi qua kết nối mạng. Trước khi gửi dữ liệu nhạy cảm, **thiết lập TLS và xác minh danh tính máy chủ**. Hai phương án phổ biến:

| Tiêu chí | LDAPS | LDAP + StartTLS |
| --- | --- | --- |
| URL thường gặp | `ldaps://ldap.example.org:636` | `ldap://ldap.example.org:389` |
| Thời điểm có TLS | TLS ngay khi kết nối | Kết nối LDAP rồi nâng cấp bằng StartTLS **trước bind** |
| Cấu hình client | LDAP URL hỗ trợ LDAPS và JSSE truststore | Client phải bật chiến lược StartTLS có xác thực chứng chỉ, xử lý lỗi nâng cấp |
| Rủi ro khi cấu hình sai | Trust-all, bỏ hostname validation, chứng chỉ hết hạn | Quên gọi StartTLS, cho phép gửi credential trước nâng cấp hoặc fallback plaintext |
| Nguyên tắc | Không dùng kết nối không xác thực server để mang password | Nếu StartTLS không thiết lập được, **fail closed**, không bind plaintext |

Demo Java sử dụng **LDAPS**. Không được chỉ đổi chuỗi URL từ `ldap://` sang `ldaps://` rồi mặc định rằng hệ thống đã an toàn nếu không kiểm tra chứng chỉ và trust chain thực tế.

### 8.1. Certificate và truststore ở JVM

Máy chủ LDAP cần chứng chỉ hợp lệ do CA tin cậy ký, đúng hostname (SAN), chưa hết hạn và có chain phù hợp. JVM dùng truststore tin cậy để kiểm tra chain. Ví dụ tham số JSSE (đường dẫn và secret do môi trường triển khai quản lý):

~~~text
-Djavax.net.ssl.trustStore=/opt/app/certs/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<truststore-secret>
~~~

Khi chạy Maven có thể cấp các property này cho **JVM ứng dụng** thông qua cấu hình runtime/deployment hoặc `JAVA_TOOL_OPTIONS` thích hợp; không vô tình chỉ truyền cho một JVM không thực hiện LDAP kết nối. Mật khẩu truststore là secret; tránh in lệnh có secret thật vào log pipeline hoặc lịch sử terminal. Nếu CA công khai được JDK tin cậy sẵn, không nhất thiết cần truststore riêng; nhiều LDAP doanh nghiệp dùng internal CA.

Đừng dùng một trust manager chấp nhận mọi chứng chỉ (`trustAll`), đừng tắt hostname verification, và đừng bỏ qua cảnh báo certificate path. Những cách này làm mất khả năng xác minh bạn đang nói chuyện với LDAP server dự kiến, tạo điều kiện cho man-in-the-middle.

**`server.ssl.*` của Spring Boot** cấu hình HTTPS **đầu vào** cho embedded web server, không tự cấu hình truststore của kết nối **đi ra LDAP**. Hai hướng TLS phải được xem xét độc lập.

### 8.2. Kiểm tra kết nối và bảo mật thực tế

Một công cụ LDAP client hỗ trợ LDAPS có thể xác nhận truy vấn group bằng service account chỉ đọc:

~~~bash
ldapsearch -H ldaps://ldap.example.org:636 \
  -D 'cn=app-reader,ou=service,dc=example,dc=org' -W \
  -b 'ou=groups,dc=example,dc=org' \
  '(uniqueMember=uid=alice,ou=people,dc=example,dc=org)' cn
~~~

`-W` yêu cầu nhập mật khẩu tương tác, tránh đưa password ngay trên dòng lệnh. Cần công cụ được cấu hình **CA và certificate/hostname verification** phù hợp; kết quả từ máy cài `ldapsearch` không tự chứng minh truststore JSSE trên máy chạy Java cũng đúng.

Kiểm chứng riêng: LDAP server xác thực chứng chỉ đúng hostname, app không kết nối khi certificate sai/hết hạn, app từ chối khi server chỉ cho plaintext, và password không xuất hiện trong HTTP response/log. Khi dùng StartTLS, phải kiểm tra nâng cấp thành công **trước bất kỳ bind có mật khẩu** và không fallback về plaintext.

### 8.3. Secret và quyền của service account

- Lưu `LDAP_BIND_PASSWORD` ở secret manager hoặc cơ chế cung cấp secret riêng của nền tảng; không commit vào `application.yml`, Docker image hoặc screenshot.
- Service account chỉ cần quyền **đọc user/group attributes phục vụ login**; không cấp quyền tạo/sửa/xóa account, đổi password hoặc đọc dữ liệu ngoài phạm vi.
- Thiết lập network policy cho phép ứng dụng kết nối đúng server/port, ghi nhận lỗi kết nối mà không in credential.
- Luân phiên secret/chứng chỉ, theo dõi thời hạn certificate, retry có giới hạn và health check theo mức độ cần thiết.
- Nếu LDAP là hệ thống xác thực tập trung, downtime cần chính sách fail closed, thông báo lỗi phù hợp và cơ chế quản trị khẩn cấp đã được phê duyệt.

## 9. Phân quyền theo LDAP group: lựa chọn thiết kế và ranh giới tin cậy

### 9.1. Không đồng nhất mọi group với role ứng dụng

Một directory có thể chứa hàng trăm nhóm không liên quan. Cho toàn bộ `cn` trở thành `ROLE_*` sẽ tạo quan hệ quyền ngầm nguy hiểm, nhất là khi chủ sở hữu nhóm không phải người quản lý ứng dụng. Chọn danh sách group được tin cậy và một bảng mapping có kiểm soát, nên theo domain/OU cụ thể.

Khi các group trong LDAP được quản lý bởi bộ phận IT còn role nghiệp vụ cần phê duyệt từ owner ứng dụng, bạn có thể dùng **LDAP group chỉ để xác định danh tính/điều kiện ban đầu**, rồi đối chiếu cơ sở dữ liệu role nội bộ. `UserDetailsContextMapper` có thể gọi một service tra cứu local account, nhưng phải xem xét thời gian phản hồi, availability, caching và lỗi.

### 9.2. Cập nhật group sau khi người dùng đã đăng nhập

LDAP authorities thường được nạp **tại thời điểm xác thực**. Với phiên HTTP session đã tồn tại, thay đổi membership ở directory không nhất thiết cập nhật ngay `Authentication` trong session. Nếu quyền bị thu hồi khẩn cấp, ứng dụng cần chính sách session timeout, reauthentication, session invalidation hoặc recheck quyền ở service phù hợp.

Không nói rằng chỉ cần xóa người dùng khỏi LDAP group là mọi phiên hiện tại mất quyền tức thì. Tùy mức rủi ro có thể cần quyền thời gian thực tại API nhạy cảm, cơ chế thu hồi phiên tập trung hoặc TTL ngắn.

### 9.3. Nested group và Active Directory

Mỗi directory có schema và cách xác định membership khác nhau. Active Directory thường dùng `sAMAccountName`, `userPrincipalName`, `memberOf` và có thể có nested groups. Spring Security có những integration riêng cho Active Directory; ví dụ dùng `uid` + `groupOfUniqueNames` ở trên không phải cấu hình AD mặc định.

Trước khi áp dụng, kiểm tra:

- User được định vị bằng DN pattern hay user search filter?
- Group là `groupOfNames` với `member`, `groupOfUniqueNames` với `uniqueMember`, hay schema khác?
- User/group có thể nằm sâu trong nhiều OU cần subtree search không?
- Group trực tiếp và nested group cần xử lý thế nào?
- `cn` có trùng tên giữa các OU hoặc tenants không?
- LDAP account disabled/locked có khiến bind thất bại không, và local account status được kiểm thêm ra sao?

Các quyết định này tác động trực tiếp đến tính đúng đắn của phân quyền; không có một group filter phù hợp cho mọi LDAP.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Đăng nhập luôn thất bại, log LDAP connection error | Server/port sai, TLS certificate không được tin, firewall, DN service account sai | Kiểm LDAPS handshake/truststore và quyền kết nối trước khi nghi ngờ password |
| User tồn tại nhưng bind báo invalid credentials | User DN pattern sai, password sai, account LDAP bị khóa, directory policy | Kiểm DN và schema; không log password hoặc chuyển plaintext |
| Login thành công nhưng không có nhóm | Group base sai, filter dùng `member` thay `uniqueMember`, service account không đọc được group, nested group | Kiểm LDAP search trực tiếp qua TLS với DN thật |
| Authority ban đầu là `ROLE_...` thay vì `LDAP_...` | Populator role prefix mặc định/cấu hình khác | Kiểm `setRolePrefix` và quy tắc uppercase, không nhầm mapping |
| Nhóm có tên gần giống nhưng role không được cấp | `cn` khác chữ hoa/underscore, code mapping không khớp | So khớp đúng authority sau populator, dùng mapping explicit |
| Người dùng không thuộc app group vẫn login được | Mapper đang trả principal có empty roles hoặc cấu hình fallback | Xác định chính sách deny khi không có group, test trường hợp này |
| Người dùng `ROLE_OPERATOR` không đọc được `/me` | `hasRole("READER")` không tự coi OPERATOR là READER | Dùng `hasAnyRole` hoặc role hierarchy được thiết kế rõ |
| Đã xóa group nhưng session cũ vẫn truy cập | Authorities nạp lúc login, session chưa refresh | Thiết lập chính sách revoke/relogin/reauthorize cho endpoint nhạy cảm |
| Truststore đúng ở laptop nhưng production lỗi | Java runtime dùng truststore khác, thiếu internal CA, hostname lệch | Kiểm cấu hình JVM thực tế và certificate chain/SAN |
| AD không tìm thấy `uid=alice` | AD không dùng schema demo | Dùng chiến lược user search/group lookup đúng AD |
| LDAP search chậm sau khi mở rộng directory | Base rộng, filter không indexed, nested traversal, kết nối timeout | Thu hẹp base, index phù hợp, timeout và đo latency |
| POST /login bị 403 từ trình duyệt | CSRF token của login form thiếu, session/cookie không khớp | Kiểm form login và CSRF, không vô hiệu hóa CSRF toàn bộ |

**Phân biệt status lỗi:** password sai thường tạo đăng nhập thất bại (redirect đến trang login báo lỗi khi dùng form login), còn đã xác thực nhưng thiếu role thường bị authorization từ chối 403. Trong demo, user thiếu nhóm có thể **bị từ chối ngay tại mapper**, nên không nhận được session đã xác thực; đây là lựa chọn policy có chủ ý.

**Quan sát an toàn:** trong môi trường phát triển, bật log mức cần thiết cho `org.springframework.security.ldap` và Spring LDAP để biết phase lỗi, nhưng không bật debug quá rộng khiến thông tin nhạy cảm bị ghi ra log. Ghi `group count`, mã lỗi, thời gian query và DN đã được redaction thích hợp; tuyệt đối không ghi password, giá trị secret hoặc nội dung directory nhạy cảm không cần thiết.

## 11. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** LDAP bind thành công có tự động cấp `ROLE_ADMIN` không?  
**Trả lời:** Không. Bind chứng minh credential được LDAP chấp nhận; quyền ứng dụng phải được ánh xạ theo nhóm/chính sách đã tin cậy.

**Câu 2.** `DefaultLdapAuthoritiesPopulator` trả `LDAP_PORTAL_READERS`. Thành phần nào trong demo đổi nó thành `ROLE_READER`?  
**Trả lời:** `ApprovedGroupMapper.mapUserFromContext`, một `UserDetailsContextMapper`.

**Câu 3.** Directory dùng `groupOfNames` với thuộc tính `member`, nhưng ứng dụng tìm `(uniqueMember={0})`. Vì sao user không nhận role?  
**Trả lời:** Filter không khớp schema thực tế; đổi sang `(member={0})` sau khi xác minh cấu trúc group.

**Câu 4.** User nằm trong nhóm `PORTAL_OPERATORS`, URL `/me` đòi `hasRole("READER")`. Có được truy cập mặc định không?  
**Trả lời:** Không. Spring Security không mặc định suy ra OPERATOR là READER. Demo dùng `hasAnyRole("READER","OPERATOR")`.

**Câu 5.** Thấy người dùng còn quyền sau khi bị xóa khỏi LDAP group. Có nhất thiết là lỗi group filter không?  
**Trả lời:** Không. Session có thể giữ authorities đã nạp ở lần login trước; cần chính sách cập nhật/revoke.

**Câu 6.** Thay `ldaps://` thành `ldap://` mà không bật StartTLS để sửa lỗi kết nối. Có an toàn không?  
**Trả lời:** Không. Việc truyền credential trên LDAP plaintext làm tăng nguy cơ lộ thông tin; phải sửa truststore/chứng chỉ/host đúng cách hoặc cấu hình StartTLS fail closed.

**Câu 7.** `server.ssl.enabled=true` trong Spring Boot có tự bảo vệ kết nối LDAP đi ra không?  
**Trả lời:** Không. Nó liên quan HTTPS server của ứng dụng; LDAP client cần LDAPS/StartTLS và truststore riêng thích hợp.

**Câu 8.** LDAP có group tên `ADMIN` nhưng owner ứng dụng chưa duyệt nhóm đó. Có nên chuyển thành `ROLE_ADMIN` vì tên giống nhau không?  
**Trả lời:** Không. Chỉ map group được whitelist và quản trị đúng trust boundary.

**Câu 9.** Unit test mapper pass có chứng minh kết nối LDAPS và bind hoạt động không?  
**Trả lời:** Không. Nó chỉ xác nhận logic group-to-role; cần integration test với LDAP thật/fixture có TLS và chính sách chứng chỉ.

## 12. Checklist triển khai và ghi nhớ

- **Xác minh schema**: base DN, user DN pattern/search, group OU, `member`/`uniqueMember`, `cn`, có nested groups/AD hay không.
- **Phân tách ba lớp**: `BindAuthenticator` kiểm tra password, `DefaultLdapAuthoritiesPopulator` tìm LDAP groups, `UserDetailsContextMapper` chuyển group đáng tin thành application principal/roles.
- **Giới hạn quyền**: map theo whitelist được quản trị; không tự tạo `ROLE_ADMIN` từ bất kỳ `cn` nào; kiểm account disabled, tenant, local permission và chính sách thu hồi phiên.
- **Bảo vệ kết nối**: LDAPS hoặc StartTLS **trước bind**, xác minh chain và hostname; cấu hình truststore của JVM gọi LDAP, không bật trust-all và không fallback plaintext.
- **Giữ bí mật**: service account chỉ đọc, password từ secret manager, không log credential/DN nhạy cảm; kiểm timeout/network/rotation và certificate expiry.
- **Kiểm thử đúng tầng**: unit test group mapper, integration test bind/group search và TLS, kiểm `/me`/`/ops` cùng session; test nhóm lạ, group nested, user disabled, session cũ và lỗi certificate.

**Ghi nhớ:** LDAP trả lời **ai đang đăng nhập và họ thuộc những nhóm nào theo directory**. `UserDetailsContextMapper` là điểm chuyển dữ liệu đó thành **UserDetails/roles do ứng dụng kiểm soát**. Toàn bộ quá trình trao đổi credential và group information với LDAP phải đi qua một kết nối đã được bảo vệ và xác minh danh tính server.
