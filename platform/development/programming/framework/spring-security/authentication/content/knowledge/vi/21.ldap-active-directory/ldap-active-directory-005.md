# LdapBindAuthenticationManagerFactory và cấu hình theo phiên bản

## 1. Mục tiêu bài học

`LdapBindAuthenticationManagerFactory` là factory của Spring Security dùng để tạo `AuthenticationManager` thực hiện **LDAP bind authentication**: nhận tên đăng nhập và mật khẩu, xác định LDAP Distinguished Name (DN) của tài khoản, rồi yêu cầu máy chủ LDAP xác thực bằng thao tác bind.

Sau bài này, bạn có thể:
- Chọn cách xác định DN bằng `userDnPatterns` hoặc tìm người dùng bằng `userSearchBase` + `userSearchFilter`.
- Cấu hình `BaseLdapPathContextSource`, tạo `AuthenticationManager` từ factory và gắn nó vào `SecurityFilterChain` của ứng dụng **Servlet**.
- Hiểu sự khác nhau giữa Spring Security 5.7/5.8, 6.x và 7.x; tránh áp dụng nguyên xi cấu hình cũ đã bị loại bỏ.
- Phân biệt **xác thực bằng LDAP bind** với **nạp quyền (authorities)** từ LDAP và trường hợp Active Directory (AD).
- Chẩn đoán lỗi DN, base DN, search filter, tài khoản service, TLS/LDAPS và thiếu quyền LDAP.

Bài viết dùng Java 17+ và cấu hình Spring Security theo kiểu bean, phù hợp nhất với ứng dụng Spring Boot 3.x/Spring Security 6.x; những điểm khác ở phiên bản 5.7+ và 7.x được nêu riêng.

## 2. LDAP bind là gì và factory nằm ở đâu?

Trong LDAP, mỗi entry có một DN duy nhất, chẳng hạn:

```text
dc=example,dc=org
└── ou=people
    └── uid=linh
        DN đầy đủ: uid=linh,ou=people,dc=example,dc=org
```

Giả sử người dùng nhập `linh` và mật khẩu. Ứng dụng không cần đọc thuộc tính mật khẩu trong directory để so sánh. Thay vào đó, nó nhờ LDAP server xác thực bằng bind với DN và mật khẩu đó.

Luồng điển hình:

```text
HTTP Basic / form login
        |
        v
Spring Security authentication filter
        |
        v
AuthenticationManager
        |
        v
LdapAuthenticationProvider + BindAuthenticator
        |
        +--> Xác định DN: từ pattern HOẶC tìm kiếm LDAP
        |
        +--> LDAP bind bằng mật khẩu vừa nhập
        |       |- Thành công -> lấy thông tin user, authorities
        |       `- Thất bại  -> authentication exception
        |
        v
Authentication đã xác thực -> SecurityContext
        |
        v
Authorization: authenticated(), hasRole(...), ...
```

`LdapBindAuthenticationManagerFactory` nằm trong package `org.springframework.security.config.ldap`. Nó **tạo ra** `AuthenticationManager`; bản thân factory không phải bean lưu phiên đăng nhập, không phải bộ lọc HTTP và không thay thế `SecurityFilterChain`.

Các thành phần:
- `BaseLdapPathContextSource`: biết máy chủ LDAP, base DN và cấu hình kết nối. Thường dùng `DefaultSpringSecurityContextSource`.
- `LdapBindAuthenticationManagerFactory`: cấu hình cách tìm/bind người dùng và tạo manager.
- `AuthenticationManager`: nhận `Authentication`, trả về đối tượng đã xác thực hoặc ném `AuthenticationException`.
- `LdapAuthoritiesPopulator`: tùy chọn tra cứu nhóm/quyền sau khi bind thành công; **xác thực đúng mật khẩu không tự động có quyền `ROLE_ADMIN`**.

> LDAP bind khác password comparison. Với bind, máy chủ LDAP kiểm tra mật khẩu; ứng dụng không cần lấy `userPassword`, không dùng `UserDetailsService`/`PasswordEncoder` để so mật khẩu LDAP như kiểu `DaoAuthenticationProvider`. Khi thực sự cần password comparison, Spring Security có factory khác là `LdapPasswordComparisonAuthenticationManagerFactory`.

## 3. Ma trận phiên bản: API nào dùng được?

| Nền tảng | Tình trạng | Hướng cấu hình |
| --- | --- | --- |
| Spring Security đến **5.6** | Chưa có `LdapBindAuthenticationManagerFactory` | Dùng API/cách cấu hình LDAP được hỗ trợ bởi đúng phiên bản cũ, hoặc nâng cấp trước khi áp dụng ví dụ dưới đây |
| Spring Security **5.7–5.8** | Factory được giới thiệu từ **5.7** | Có thể tạo `AuthenticationManager` bằng factory; chuyển dần từ `WebSecurityConfigurerAdapter` sang bean `SecurityFilterChain` |
| Spring Security **6.x** (Spring Boot 3.x) | Factory vẫn hỗ trợ; nền Jakarta, Java 17+ | Ưu tiên `@Bean AuthenticationManager`, `@Bean SecurityFilterChain` và lambda DSL |
| Spring Security **7.x** (thường đi với Spring Boot 4.x) | Factory vẫn có trong Javadoc 7.x | Tiếp tục dùng bean/factory; kiểm tra thay đổi API trong migration guide, không dựa vào các overload DSL đã bị loại bỏ |

Điểm chuyển đổi dễ nhầm:
1. `WebSecurityConfigurerAdapter` **deprecated trong 5.7** và **bị loại khỏi 6.0**. Code `extends WebSecurityConfigurerAdapter`/`configure(AuthenticationManagerBuilder)` trong tutorial cũ không biên dịch với Spring Security 6+.
2. `LdapBindAuthenticationManagerFactory` có từ **5.7**; không thể chỉ copy import vào project Security 5.6 rồi mong IDE tự sửa.
3. Khi nâng cấp, không pin riêng `spring-security-ldap` lên major khác các module Spring Security còn lại. Nếu dùng Spring Boot, để dependency management/BOM chọn các phiên bản cùng hệ.
4. Kể từ quá trình chuyển sang 7.x, **embedded ApacheDS cũ không còn là đường thử nghiệm nên chọn**; Spring Security khuyến nghị UnboundID. Điều này thuộc cấu hình máy chủ LDAP thử nghiệm, không phải việc factory bị xóa.
5. Kiểu cấu hình Servlet trong bài sử dụng `HttpSecurity` và `SecurityFilterChain`. Với ứng dụng WebFlux, đường xác thực dùng các thành phần reactive khác; không lấy ví dụ Servlet này gắn trực tiếp vào `SecurityWebFilterChain`.

Đừng suy đoán phiên bản Spring Security từ tên lớp khác hoặc tutorial: kiểm tra `./gradlew dependencies --configuration runtimeClasspath`, dependency tree Maven, hoặc BOM của phiên bản Spring Boot thực tế.

## 4. API cốt lõi của factory

Một factory nhận một `BaseLdapPathContextSource` và dùng các method kế thừa từ `AbstractLdapAuthenticationManagerFactory`:

| Phương thức | Khi nào dùng |
| --- | --- |
| `new LdapBindAuthenticationManagerFactory(contextSource)` | Bắt đầu cấu hình bind authentication |
| `setUserDnPatterns("uid={0},ou=people")` | Tạo DN theo mẫu khi vị trí user cố định |
| `setUserSearchBase("ou=people")` | Giới hạn nhánh tìm người dùng; tương đối so với base DN của context source |
| `setUserSearchFilter("(uid={0})")` | Tìm user theo thuộc tính LDAP khi DN không thể suy ra trực tiếp |
| `setLdapAuthoritiesPopulator(...)` | Tùy chỉnh cách lấy quyền từ nhóm LDAP/AD hoặc nguồn khác |
| `setAuthoritiesMapper(...)` | Chuyển đổi tập `GrantedAuthority` sau khi lấy |
| `setUserDetailsContextMapper(...)` | Điều chỉnh cách dữ liệu LDAP được chuyển thành principal/user details |
| `createAuthenticationManager()` | Tạo manager sau khi đã cấu hình các thành phần cần thiết |

`{0}` trong **DN pattern** và **user search filter** được thay bằng tên đăng nhập. Ví dụ `linh` cùng `uid={0},ou=people` sẽ tạo DN tương đối `uid=linh,ou=people`; kết hợp với base `dc=example,dc=org` thành DN đầy đủ. Với search, `(uid={0})` thành điều kiện tương ứng với tên đăng nhập tại vị trí tìm kiếm đã thiết lập. Dùng một trong hai chiến lược theo cấu trúc directory, không trộn thiếu chủ đích.

Lưu ý: method trả về `AuthenticationManager`, không trả về `AuthenticationProvider` hay `SecurityFilterChain`. Việc publish manager làm bean vẫn cần được nối đúng với cơ chế authentication mà ứng dụng dùng.

## 5. Ví dụ hoàn chỉnh trên Spring Boot 3.x + Spring Security 6.x

Ví dụ sau dùng một LDAP directory **đã tồn tại** có user tại `uid=<username>,ou=people,dc=example,dc=org`. Các domain/host là địa chỉ minh họa; phải thay bằng directory thật trong môi trường chạy. Ví dụ tập trung vào Spring Security LDAP, không tự khởi tạo LDAP server.

### 5.1. Dependencies

Trong một ứng dụng Spring Boot 3.x đã có plugin Gradle và dependency management tương thích, thêm vào `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
```

`spring-security-ldap` chứa API factory/authenticator; Spring LDAP cung cấp `ContextSource` và LDAP integration. Giữ phiên bản dependency theo Spring Boot BOM đang dùng.

### 5.2. Cấu hình URL LDAP

`src/main/resources/application.yml`:

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636/dc=example,dc=org}
```

URL của `DefaultSpringSecurityContextSource(String)` có thể gồm **base DN** ở phần path sau host/port. Ở ví dụ này, `dc=example,dc=org` chính là gốc của các DN tương đối bên dưới. Không ghép lặp base DN trong `userDnPatterns`.

Trong production, ưu tiên **LDAPS** hoặc StartTLS với kiểm tra chứng thư TLS; cấu hình truststore/CA phù hợp. `ldap://` không mã hóa kết nối chỉ thích hợp khi có bảo vệ tương đương và được chính sách cho phép.

### 5.3. Tạo ContextSource, AuthenticationManager và SecurityFilterChain

`src/main/java/example/ldap/LdapSecurityConfig.java`:

```java
package example.ldap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class LdapSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.url}") String ldapUrl) {
        return new DefaultSpringSecurityContextSource(ldapUrl);
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        // DN tương đối với base DN trong app.ldap.url.
        factory.setUserDnPatterns("uid={0},ou=people");

        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager) throws Exception {

        http
            .authenticationManager(ldapAuthenticationManager)
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/me").authenticated()
                .anyRequest().permitAll())
            .httpBasic(withDefaults());

        return http.build();
    }
}
```

Mấu chốt là `.authenticationManager(ldapAuthenticationManager)`: HTTP filter chain được khai báo **dùng chính manager LDAP** do factory tạo. Tránh ngộ nhận rằng chỉ tạo ra một bean `AuthenticationManager` thì mọi filter/chain tùy biến trong mọi cấu hình đều tự chọn nó.

`httpBasic(withDefaults())` tạo một điểm vào đơn giản để kiểm tra tên đăng nhập/mật khẩu. Nếu dùng form login, có thể thay bằng `formLogin(withDefaults())` trong chain thích hợp. **HTTP Basic chỉ được dùng qua HTTPS khi có mạng không đáng tin cậy**.

### 5.4. Entry point và endpoint để quan sát principal

`src/main/java/example/ldap/LdapDemoApplication.java`:

```java
package example.ldap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LdapDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LdapDemoApplication.class, args);
    }
}
```

`src/main/java/example/ldap/WhoAmIController.java`:

```java
package example.ldap;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
```

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Với một LDAP server đang chạy và người dùng `linh` tồn tại đúng DN/mật khẩu, thử từ máy local:

```bash
curl -i --user linh http://localhost:8080/me
```

`curl` có thể hỏi mật khẩu theo cách tương tác. **Kết quả phụ thuộc LDAP thật**: đúng thông tin sẽ được HTTP 200 và body là tên principal; sai mật khẩu thường cho HTTP 401; LDAP không kết nối được sẽ thất bại ở đường xác thực và cần đọc log phía server. Đây không phải chương trình console có stdout cố định. Trên môi trường thực, phải đưa ứng dụng ra HTTPS, không truyền credential qua HTTP thường.

Vì chưa có LDAP instance, certificate và credential thực tế trong bài viết, **không thể khẳng định demo sẽ bind thành công khi chạy nguyên trạng với `ldap.example.org`**. Mã Java là cấu trúc có thể biên dịch trong project Spring Boot phù hợp; việc test bind cần directory thật hoặc server embedded được dựng riêng.

## 6. Chọn `userDnPatterns` hay tìm kiếm bằng filter

### Cách A — DN cố định: `setUserDnPatterns`

```java
LdapBindAuthenticationManagerFactory factory =
    new LdapBindAuthenticationManagerFactory(contextSource);
factory.setUserDnPatterns("uid={0},ou=people");
AuthenticationManager manager = factory.createAuthenticationManager();
```

Phù hợp khi mọi tài khoản nằm cùng OU và DN luôn có dạng `uid=<login>,ou=people,...`. Ưu điểm là không cần search để biết DN, cấu hình gọn. Nhưng nếu user ở nhiều OU, bị đổi DN hoặc tên hiển thị khác thuộc tính định danh, pattern không còn đúng.

### Cách B — DN thay đổi: `setUserSearchBase` + `setUserSearchFilter`

Thay nội dung method tạo manager ở ví dụ trên bằng:

```java
LdapBindAuthenticationManagerFactory factory =
    new LdapBindAuthenticationManagerFactory(contextSource);
factory.setUserSearchBase("ou=people");
factory.setUserSearchFilter("(uid={0})");
return factory.createAuthenticationManager();
```

Tại đây Spring Security tìm entry thỏa `(uid=linh)` dưới `ou=people,dc=example,dc=org`, lấy DN trả về rồi bind bằng mật khẩu người dùng. Không chỉ định search base thì tìm từ base DN của `ContextSource`; không nên mở rộng phạm vi vô cớ nếu directory lớn.

**Quyền tìm kiếm:** một số LDAP directory cấm anonymous search. Khi đó cấu hình bind account có quyền đọc tối thiểu cho `ContextSource`. Ví dụ method bean độc lập dưới đây thay bean `ldapContextSource` trong cấu hình trước:

```java
@Bean
BaseLdapPathContextSource ldapContextSource(
        @Value("${app.ldap.url}") String ldapUrl,
        @Value("${app.ldap.search-dn}") String searchDn,
        @Value("${app.ldap.search-password}") String searchPassword) {

    DefaultSpringSecurityContextSource source =
        new DefaultSpringSecurityContextSource(ldapUrl);

    source.setUserDn(searchDn);
    source.setPassword(searchPassword);
    return source;
}
```

Cấu hình tương ứng trong `application.yml`:

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.org:636/dc=example,dc=org}
    search-dn: ${LDAP_SEARCH_DN}
    search-password: ${LDAP_SEARCH_PASSWORD}
```

`LDAP_SEARCH_DN` là DN của tài khoản service/search và `LDAP_SEARCH_PASSWORD` là secret cấp qua môi trường/secret manager. Tài khoản này được dùng cho các thao tác search cần quyền; **xác thực mật khẩu của người dùng vẫn phải là bind theo DN của user**. Không hard-code mật khẩu service vào Git. Tùy directory, DN cho `setUserDn` phải tuân theo yêu cầu định danh bind của server.

Không nhầm LDAP search filter với URL route filter hay SQL. Dùng placeholder `{0}` do Spring LDAP xử lý trong mẫu cấu hình; tránh tự ghép input vào filter bằng nối chuỗi và tuyệt đối tránh thiết kế filter cho phép người dùng tự quyết định phạm vi tìm kiếm.

### Quy tắc quyết định

| Cấu trúc directory | Nên dùng | Ví dụ |
| --- | --- | --- |
| Tất cả user có DN cố định | `userDnPatterns` | `uid={0},ou=people` |
| User phân bố nhiều nhánh hoặc DN thay đổi | `userSearchBase` + `userSearchFilter` | base `ou=employees`, filter `(uid={0})` |
| LDAP search cần quyền | Search filter + bind account ít quyền | `setUserDn`, `setPassword` trong `ContextSource` |
| Active Directory theo `sAMAccountName` | Search filter tương ứng hoặc AD provider chuyên dụng | `(sAMAccountName={0})` |
| Domain AD dùng UPN và lỗi trạng thái account đặc thù | Cân nhắc `ActiveDirectoryLdapAuthenticationProvider` | Ví dụ xem mục 8 |

Nếu directory thực tế có nhiều base DN, hãy rà soát phạm vi search, referral, quyền và uniqueness. Một `uid` không duy nhất trong phạm vi tìm kiếm có thể dẫn đến chọn sai hoặc tìm thấy nhiều entry, không được âm thầm bỏ qua.

## 7. Xác thực thành công không đồng nghĩa có đủ authority

`LdapBindAuthenticationManagerFactory` tạo authentication manager dùng LDAP bind, nhưng policy như `hasRole("READER")` còn phụ thuộc cách nạp `GrantedAuthority`.

Ví dụ directory có group:

```ldif
dn: cn=reader,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: reader
member: uid=linh,ou=people,dc=example,dc=org
```

Với schema như trên, cấu hình `DefaultLdapAuthoritiesPopulator` cho group search (đây là đoạn thay thế/tăng cường **bên trong** method `ldapAuthenticationManager`, sau khi đã tạo factory và trước `createAuthenticationManager()`):

```java
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;

DefaultLdapAuthoritiesPopulator roles =
    new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
roles.setGroupSearchFilter("(member={0})");
roles.setGroupRoleAttribute("cn");
roles.setRolePrefix("ROLE_");
factory.setLdapAuthoritiesPopulator(roles);
```

Với group `cn=reader`, việc map tên group (thường được viết hoa theo mặc định) có thể tạo authority `ROLE_READER`. `{0}` ở **group search filter** là DN đầy đủ của user; điều này khác với `{0}` ở **user search filter**, nơi nó là tên đăng nhập. Cần xác minh chính xác schema `member`/`uniqueMember`, location của group, group nesting và quyền search. Nếu không có group search phù hợp, đăng nhập vẫn có thể thành công nhưng `hasRole("READER")` trả 403.

Không tự gán `ROLE_ADMIN` mặc định chỉ vì bind thành công. Nên định nghĩa rõ quyền ứng dụng nào ánh xạ với nhóm LDAP nào, kiểm thử tài khoản ít quyền và các trường hợp group bị xóa.

## 8. Trường hợp Microsoft Active Directory

AD nói LDAP nhưng naming convention, cách đăng nhập, group và thông báo trạng thái tài khoản có nét riêng. Một số thuộc tính thường gặp là:

- `sAMAccountName`: tên đăng nhập kiểu Windows, ví dụ `linh`.
- `userPrincipalName`: thường ở dạng `linh@corp.example.org`.
- `distinguishedName`: DN đầy đủ của entry; OU có thể thay đổi khi chuyển nhân sự/phòng ban.
- `memberOf`: liên kết thành viên group trực tiếp; group lồng nhau và primary group cần chính sách xử lý riêng.

Nếu chỉ dùng factory LDAP chung, có thể dùng:

```java
factory.setUserSearchBase("ou=Staff");
factory.setUserSearchFilter("(sAMAccountName={0})");
```

Đây chỉ là **ví dụ**, không phải filter đúng cho mọi forest/domain; `ou=Staff` phải thực sự nằm dưới base DN của cấu hình. Trường hợp xác thực bằng UPN hoặc yêu cầu thông báo trạng thái tài khoản AD cụ thể, xem `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. Provider chuyên dụng này có logic tìm người dùng/nhóm và tùy chọn diễn giải sub-error code của AD; không giả định factory bind chung tự cung cấp đầy đủ những semantics đó.

Cần xác định sớm liệu yêu cầu là xác thực LDAP vào AD hay **SSO bằng Kerberos/SAML/OIDC**. `LdapBindAuthenticationManagerFactory` xử lý username/password và LDAP bind; nó **không tự bật Single Sign-On** chỉ vì máy chủ LDAP là Active Directory.

## 9. Quy trình kiểm thử theo phiên bản

Kiểm thử nên gồm cả cấu hình bean và xác thực thật với directory cô lập. Checklist:

1. Xác minh class `LdapBindAuthenticationManagerFactory` có trong `org.springframework.security.config.ldap` của `spring-security-ldap` đang dùng (từ 5.7 trở đi).
2. Kiểm tra có đúng một cấu hình manager mà filter chain mong đợi; xác nhận `.authenticationManager(...)` được gọi cho chain cần thử.
3. Dùng một user test tồn tại đúng DN và mật khẩu, một user không tồn tại, một user đúng tên nhưng sai mật khẩu.
4. Thử với LDAP server tắt hoặc sai hostname/port để phân biệt lỗi kết nối với lỗi credential.
5. Thử search account thiếu quyền đọc OU; verify lỗi ở bước user search thay vì nhầm thành sai mật khẩu.
6. Nếu dùng authorities, test cùng một user trước/sau khi thêm group và kiểm tra policy `hasRole`.
7. Thử chứng thư TLS không tin cậy, hostname mismatch và xác minh kết nối bị từ chối an toàn; không tắt certificate validation để test đi tiếp.
8. Khi nâng cấp Spring Security, biên dịch lại bean config, chạy các integration test xác thực và kiểm tra build logs/deprecation.

Có thể dùng UnboundID embedded LDAP trong test riêng với dữ liệu LDIF có DN và nhóm cụ thể. Spring Security cung cấp `EmbeddedLdapServerContextSourceFactoryBean`, ví dụ method minh họa trong test configuration:

```java
@Bean
EmbeddedLdapServerContextSourceFactoryBean embeddedLdap() {
    EmbeddedLdapServerContextSourceFactoryBean source =
        EmbeddedLdapServerContextSourceFactoryBean.fromEmbeddedLdapServer();
    source.setPort(0); // Port động để tránh đụng service khác.
    return source;
}
```

Cần import `org.springframework.security.config.ldap.EmbeddedLdapServerContextSourceFactoryBean`, khai báo UnboundID SDK ở test/runtime scope và LDIF thích hợp trong classpath. Đây là **một nhánh cấu hình thử nghiệm thay thế ContextSource production**, không đặt cả hai vào cùng ứng dụng rồi vô tình tạo nhiều bean trùng loại. Trong quá trình nâng cấp lên 7.x, ưu tiên UnboundID vì hỗ trợ ApacheDS embedded cũ đã bị loại bỏ.

Để debug, tạm tăng mức log có chọn lọc cho quá trình Spring Security/LDAP trong môi trường test, nhưng không ghi password, raw Basic header, secret của search account hay nội dung nhạy cảm từ entry LDAP vào logs. Hệ thống thực tế cần timeout, connection pooling phù hợp và giám sát tỷ lệ bind/search thất bại.

## 10. Lỗi cấu hình thường gặp

| Dấu hiệu | Khả năng cao | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` hoặc IDE không tìm thấy factory | Thiếu `spring-security-ldap` hoặc phiên bản trước 5.7 | Xem dependency tree và BOM; thêm đúng module |
| Code từ tutorial dùng `WebSecurityConfigurerAdapter` không build | Spring Security 6+ đã bỏ adapter | Đổi sang `@Bean SecurityFilterChain` và bean manager/factory |
| User có mật khẩu đúng nhưng bị `BadCredentialsException` | DN pattern sai, username format khác, mật khẩu sai hoặc account bị policy LDAP từ chối | Đối chiếu DN thực và log LDAP server, thử directory test |
| Search luôn không tìm thấy user | `userSearchBase` sai, filter dùng nhầm `uid`/`sAMAccountName`, thiếu quyền search | Kiểm tra base DN, OU, ACL và uniqueness |
| Lỗi DN bị lặp `dc=...` | Ghép full DN vào pattern trong khi context source đã có base DN | Chỉ dùng DN tương đối trong pattern/search base |
| Đăng nhập được nhưng truy cập endpoint cần role bị 403 | Chưa có/cấu hình sai `LdapAuthoritiesPopulator` hoặc mapping group | Kiểm tra `Authentication.getAuthorities()`, schema group và policy |
| LDAP server unreachable, SSL handshake error | Sai URL, port, DNS, firewall, truststore hoặc certificate | Xác minh LDAPS/StartTLS/CA, không bỏ xác minh TLS |
| Form/basic login không dùng LDAP manager mong muốn | Chưa nối manager vào đúng `SecurityFilterChain`, hoặc nhiều chain/provide khác nhau | Kiểm tra `.authenticationManager(...)`, security matcher và bean graph |
| AD bind có account status/sub-error cần diễn giải | Factory chung không phản ánh hết semantics AD | Đánh giá `ActiveDirectoryLdapAuthenticationProvider` |
| Test chỉ pass local nhưng fail môi trường thật | LDIF, schema, OU, ACL hoặc TLS khác production | Thử nghiệm với dữ liệu/LDAP staging gần production, không dùng dữ liệu nhạy cảm |

**Phân loại lỗi:** `BadCredentialsException` là lỗi xác thực người dùng ở mức Spring Security; `CommunicationException`/TLS/connection errors là vấn đề giao tiếp với directory; 403 là vấn đề authorization có thể xảy ra **sau** authentication. Không chuyển tất cả lỗi thành “sai mật khẩu” trong log vận hành, nhưng thông báo công khai cho client không được tiết lộ khả năng tồn tại của account hoặc trạng thái nội bộ quá chi tiết.

## 11. Nguyên tắc thiết kế và vận hành

- **Không đặt mật khẩu trong Git:** dùng môi trường, secret manager; phân quyền nhỏ nhất cho search account.
- **Mã hóa trên đường truyền:** HTTPS cho người dùng gửi password, LDAPS/StartTLS cho ứng dụng kết nối LDAP, kiểm tra CA và hostname.
- **Giữ cấu hình theo phiên bản:** nếu dùng Spring Security 6/7, viết bean + lambda DSL, kiểm tra thay đổi qua mỗi major; tránh copy code đã deprecated.
- **Tách xác thực với phân quyền:** bind đúng chỉ chứng minh mật khẩu hợp lệ; authorities phải được lấy và map đúng schema và policy.
- **Giới hạn phạm vi tìm kiếm:** base DN/OU càng cụ thể càng dễ kiểm soát; xử lý kết quả nhiều entry là lỗi cấu hình/dữ liệu cần sửa.
- **Không để người dùng kiểm soát trực tiếp DN/filter:** dùng API placeholder và validate login name; kiểm thử cả LDAP special characters.
- **Kiểm thử failure path:** sai credential, account không tồn tại, LDAP downtime, ACL, chứng thư TLS, thay group.
- **Nhiều security filter chain:** chỉ chain được cấu hình dùng LDAP manager mới chắc chắn chuyển credential cho manager ấy; rà soát thứ tự và request matcher khi ứng dụng dùng nhiều chain.

## 12. Tóm tắt quyết định

Nếu dự án đang ở **Spring Security 5.7+**, có LDAP server và cần đăng nhập bằng username/password, bắt đầu từ `BaseLdapPathContextSource` → `LdapBindAuthenticationManagerFactory` → `createAuthenticationManager()` → nối vào `SecurityFilterChain`. Chọn **DN pattern** khi biết chắc cấu trúc DN; chọn **search filter** khi cần tìm DN; bổ sung `LdapAuthoritiesPopulator` nếu policy dựa trên nhóm. Với **Active Directory**, xác minh riêng thuộc tính định danh, cách bind và mapping nhóm trước khi quyết định factory chung hay provider AD chuyên dụng.

### Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Security 6.5, LDAP Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html
- Spring Security 7.0, LDAP Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/ldap.html
- Javadoc `LdapBindAuthenticationManagerFactory` (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/LdapBindAuthenticationManagerFactory.html
- Javadoc `AbstractLdapAuthenticationManagerFactory` (6.5): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html
- Javadoc `DefaultLdapAuthoritiesPopulator`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html
- Javadoc `ActiveDirectoryLdapAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Migration 6.5 → 7.0, LDAP: https://docs.spring.io/spring-security/reference/6.5/migration-7/ldap.html
