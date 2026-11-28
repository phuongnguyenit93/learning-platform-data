# Tích hợp xác thực và ánh xạ quyền từ nhóm

Trong **SPRING_DATA_LDAP**, chúng ta dùng Java, Spring Data LDAP repository và `LdapTemplate` để truy cập một LDAP directory gồm các entry có DN (*Distinguished Name*), `objectClass`, schema và thuộc tính phân cấp. Bên cạnh thao tác CRUD và tìm kiếm, một ứng dụng doanh nghiệp thường cần **cho người dùng đăng nhập bằng tài khoản LDAP** rồi xác định **người đó được sử dụng chức năng nào** dựa trên membership trong các nhóm của directory.

Đây là một bài **thực hành tích hợp**: dùng **Spring Security LDAP** để thực hiện xác thực và tải quyền; dùng **Spring Data LDAP/Spring LDAP** cho phần truy vấn dữ liệu nghiệp vụ. Hai tầng cùng nói chuyện với directory nhưng **không cùng nhiệm vụ**. Bài xây dựng một ứng dụng danh bạ nội bộ có hai quyền `PEOPLE_READ` và `PEOPLE_EDIT`, được ánh xạ từ hai nhóm `app_readers` và `app_editors`.

**Điều người học cần làm được:** cấu hình kết nối LDAPS, tạo dữ liệu LDIF mẫu, xác thực bằng LDAP Bind, tìm nhóm bằng giá trị `member` chứa **DN đầy đủ** của người dùng, chỉ cho phép các nhóm đã được phê duyệt cấp quyền ứng dụng, bảo vệ HTTP endpoint, kiểm thử các trường hợp đúng/sai và hiểu thời điểm quyền thay đổi có hiệu lực.

## 1. Bài toán và kết quả mong đợi

Giả sử tổ chức dùng LDAP với nhánh:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=binh
├── ou=groups
│   ├── cn=app_readers
│   └── cn=app_editors
└── ou=service
    └── cn=ldap-reader
```

Quy ước của ứng dụng:

| Tài khoản | Nhóm LDAP | Quyền ứng dụng | Kỳ vọng |
|---|---|---|---|
| `lan` | `app_readers` | `PEOPLE_READ` | Được xem hồ sơ, không được chỉnh sửa |
| `binh` | `app_editors` | `PEOPLE_READ`, `PEOPLE_EDIT` | Được xem và chỉnh sửa |
| Tài khoản hợp lệ nhưng không thuộc hai nhóm | Nhóm khác hoặc không có nhóm | Không có quyền nghiệp vụ | Đăng nhập có thể thành công nhưng bị từ chối khi vào API |
| Sai mật khẩu / DN không tồn tại | Không xác thực được | Không cấp quyền | Không tạo phiên đăng nhập hợp lệ |

Khi đó:

```text
                     LOGIN (uid + password)
                               |
                               v
                         Spring Security
                               |
                  Tìm DN người dùng qua LDAP
                               |
                               v
                     Bind bằng mật khẩu user
                       /                \
                     FAIL              SUCCESS
                      |                   |
                 Không đăng nhập      Tìm nhóm theo DN
                                          |
                                          v
                           cn=app_readers / app_editors
                                          |
                                          v
                           Allowlist ánh xạ authority
                                          |
                                          v
                             SecurityContext / Session
                                          |
                       +------------------+------------------+
                       |                                     |
              GET /api/people/...                     POST /api/people/...
              cần PEOPLE_READ                        cần PEOPLE_EDIT
                       |                                     |
                       +------------------+------------------+
                                          |
                                          v
                          Spring Data LDAP / LdapTemplate
                             (dịch vụ truy vấn dữ liệu)
```

**Đặc biệt:** membership trong LDAP không nhất thiết là authority của Spring Security. Nhóm có thể được tên là `app_editors`, nhưng Spring Security kiểm soát HTTP bằng `GrantedAuthority`. Ứng dụng cần **một quy tắc ánh xạ rõ ràng, có kiểm soát**, không gán quyền admin chỉ vì LDAP trả về một tên nhóm giống `admins`.

## 2. Phân biệt Authentication và Authorization

**Authentication (xác thực):** người dùng có đúng là `lan` và có credential hợp lệ theo LDAP server không?

**Authorization (phân quyền):** sau khi xác thực, `lan` có được mở API xem danh bạ, sửa hồ sơ hoặc quản lý nhóm không?

Trong Spring Security:

| Thành phần | Nhiệm vụ |
|---|---|
| `AuthenticationManager` | Nhận yêu cầu đăng nhập và điều phối xác thực |
| `LdapBindAuthenticationManagerFactory` | Cấu hình luồng LDAP Bind authentication |
| `BindAuthenticator` (do factory tạo) | Tìm DN người dùng rồi thực hiện Bind bằng password được cung cấp |
| `DefaultLdapAuthoritiesPopulator` | Tìm các entry nhóm chứa người dùng, đọc tên nhóm |
| `LdapAuthoritiesPopulator` tùy biến | Chỉ chuyển nhóm được tin cậy thành authority ứng dụng |
| `GrantedAuthority` | Quyền đã được gắn vào `Authentication` |
| `SecurityFilterChain` | Quy định endpoint nào yêu cầu authority nào |
| `LdapTemplate` hoặc `LdapRepository` | Đọc/ghi các entry LDAP cho chức năng nghiệp vụ; không tự động xác thực người dùng |

Spring Data LDAP repository cung cấp cách truy cập và ánh xạ dữ liệu. Nó **không tự tạo một cơ chế đăng nhập hay gán Spring Security roles** khi bạn chỉ khai báo `LdapRepository<PersonEntry>`. Tương tự, một phép `ldapTemplate.lookup(...)` chạy bằng service account đọc được user **không chứng minh user đã cung cấp đúng password**.

Spring Security LDAP sử dụng **LDAP Bind** thay vì yêu cầu tải thuộc tính `userPassword` về Java rồi tự so sánh. Trong Bind authentication, mật khẩu được LDAP server xác thực; ứng dụng phải truyền credential trên kênh TLS hợp lệ và tránh ghi thông tin đó vào log.

## 3. Thiết kế directory và dữ liệu LDIF thực hành

Ví dụ này dùng **OpenLDAP hoặc LDAP server test tương thích** với `inetOrgPerson` và `groupOfNames`. Bạn cần một naming context `dc=example,dc=org`. Thay tên host, bind account, password và schema cho môi trường thực.

### 3.1. Hai người dùng và hai nhóm

**`sample-people-groups.ldif` — dữ liệu cho directory thử nghiệm**

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: ou=service,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: service

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
userPassword: only-for-test-lan

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Tran
sn: Tran
mail: binh@example.org
userPassword: only-for-test-binh

dn: cn=app_readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app_readers
member: uid=lan,ou=people,dc=example,dc=org

dn: cn=app_editors,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: app_editors
member: uid=binh,ou=people,dc=example,dc=org
```

**Cảnh báo bảo mật:** hai giá trị `userPassword` là **mật khẩu giả chỉ dành cho directory test**, được ghi dạng rõ để người học quan sát cấu trúc LDIF. Không đưa ví dụ này lên directory production, không lưu mật khẩu thật trong Git và không cho rằng mọi server đều chấp nhận mật khẩu dạng rõ trong LDIF. Môi trường thực cần dùng cơ chế cấp phát/hash/lưu trữ password do directory và tổ chức quy định.

Entry `cn=ldap-reader,ou=service,dc=example,dc=org` không được định nghĩa trong LDIF trên vì cách tạo service account và cấp ACL phụ thuộc sản phẩm LDAP. **Hãy tạo riêng tài khoản tra cứu chỉ có quyền cần thiết**, rồi cung cấp DN/password của nó qua secret configuration.

### 3.2. Vì sao `member` chứa DN?

`groupOfNames` thường dùng thuộc tính `member` mang giá trị **DN của entry thành viên**:

```text
group DN:
  cn=app_readers,ou=groups,dc=example,dc=org

member:
  uid=lan,ou=people,dc=example,dc=org
```

Không được ghi nhầm:

```text
member: lan
```

vì `member` không phải thuộc tính chứa tên đăng nhập thông thường. Bộ ánh xạ quyền trong bài sẽ tìm:

```text
(&(objectClass=groupOfNames)
  (member=uid=lan,ou=people,dc=example,dc=org))
```

Đây là **hình thức filter để giải thích ý nghĩa**, không phải yêu cầu tự nối chuỗi trong Java. Spring Security thay tham số `{0}` bằng DN của người dùng đã xác thực và thực hiện escape cho filter theo cơ chế nội bộ.

Để kiểm tra mẫu bằng LDAP CLI trên môi trường test:

```bash
ldapsearch -LLL -H ldaps://ldap.example.org:636 \
  -D "cn=ldap-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" \
  "(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))" \
  dn cn
```

Lệnh chỉ có ý nghĩa khi endpoint LDAPS tin cậy, account tra cứu đã được tạo và có ACL đọc nhóm. Tùy directory, lọc theo `member` có thể yêu cầu index/matching rule và chịu giới hạn của server.

## 4. Chuẩn bị dependencies và cấu hình bí mật

Ứng dụng minh họa dùng Java 17+ và họ Spring Boot/Spring Security tương thích. Các nhóm dependency chính:

**`build.gradle` — minh họa với Spring Boot dependency management**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Version Spring Security, Spring LDAP và Spring Data LDAP phải do BOM/dependency management tương thích quản lý. Không chốt phiên bản tùy ý hoặc trộn artifact Spring Security 6 và 7 trong cùng ứng dụng.

**`application.yml` — dùng biến môi trường/secret store**

```yaml
app:
  ldap-security:
    url: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    lookup-dn: cn=ldap-reader,ou=service,dc=example,dc=org
    lookup-password: ${LDAP_LOOKUP_PASSWORD}
```

Ở đây **lookup account** chỉ dùng để tìm DN của user và tìm nhóm. Password của chính người dùng được gửi đến LDAP server trong bước **Bind thử bằng user identity**, không lưu thành cấu hình và không gắn vào `LdapTemplate` dùng chung.

Trước khi thử đăng nhập, phải xác nhận ứng dụng tin tưởng CA của LDAP server, kiểm tra hostname/SAN, sử dụng TLS an toàn và LDAP server không cho phép một fallback sang SIMPLE Bind trên kết nối rõ dữ liệu khi LDAPS lỗi. Nếu test dùng CA nội bộ, cấp truststore JVM có cấu hình rõ ràng; không dùng trust-all `TrustManager`.

## 5. Cấu hình ContextSource chuyên dùng cho xác thực

Spring Security LDAP có `DefaultSpringSecurityContextSource` — một triển khai `ContextSource` thích hợp với luồng tìm user và bind xác thực. Dùng constructor nhận **danh sách LDAP URLs** và **base DN**:

**`LdapSecurityConfiguration.java` — phần ContextSource**

```java
package com.example.ldap.security;

import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;

@Configuration
public class LdapSecurityConfiguration {

    @Bean("securityLdapContextSource")
    DefaultSpringSecurityContextSource securityLdapContextSource(
            @Value("${app.ldap-security.url}") String url,
            @Value("${app.ldap-security.base}") String base,
            @Value("${app.ldap-security.lookup-dn}") String lookupDn,
            @Value("${app.ldap-security.lookup-password}") String password) {

        DefaultSpringSecurityContextSource contextSource =
                new DefaultSpringSecurityContextSource(List.of(url), base);

        contextSource.setUserDn(lookupDn);
        contextSource.setPassword(password);
        contextSource.setPooled(false); // Cấu hình rõ vòng đời bind user.
        return contextSource;
    }
}
```

Đây là **phần đầu của class cấu hình**, sẽ được bổ sung các bean khác ở mục tiếp theo. Các URL trong `List.of(url)` **không chứa base DN** vì constructor đã nhận `base` riêng; đừng dùng `ldaps://host:636/dc=example,dc=org` ở đây rồi lại truyền thêm base một lần nữa.

`setPooled(false)` giúp minh họa tách bạch context tra cứu và context bind người dùng, thay vì trông chờ pooling của provider trong một luồng credential thay đổi. Spring Security có các xử lý riêng cho bind identity, nhưng không nên tự tạo một pool chung trộn credential của nhiều người dùng.

Trong production, nếu có nhiều LDAP servers, phải phân tích **đường đi failover, replication lag, trust chain** và khả năng các node trả cùng group membership trước khi truyền nhiều URL cho context source.

## 6. Tải quyền từ `groupOfNames` và ánh xạ vào authority ứng dụng

`DefaultLdapAuthoritiesPopulator` tìm các entry nhóm mà người dùng là thành viên. Với `groupOfNames`:

| Tham số / thuộc tính | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Group search base | `ou=groups` | Nhánh nhóm, tương đối với `dc=example,dc=org` |
| Group search filter | `(&(objectClass=groupOfNames)(member={0}))` | Nhóm có member bằng DN đầy đủ của người dùng |
| `{0}` | `uid=lan,ou=people,dc=example,dc=org` | DN người dùng được xác thực |
| `{1}` | `lan` | Tên đăng nhập, phù hợp schema dùng `memberUid` |
| Group role attribute | `cn` | Tên nhóm, ví dụ `app_readers` |
| Role prefix trung gian | `LDAP_` | Phân biệt nhóm LDAP với quyền ứng dụng |
| Case conversion | Uppercase | `app_readers` trở thành `LDAP_APP_READERS` |

Trong một ứng dụng nhỏ, có thể dùng `ROLE_` theo mặc định và `hasRole(...)`. Nhưng đó không phải lúc nào cũng an toàn: nhóm `cn=admins` ở directory không nên tự cấp quyền quản trị hệ thống chỉ vì trùng tên. Ví dụ này dùng **allowlist tường minh**:

```text
LDAP_APP_READERS -> PEOPLE_READ
LDAP_APP_EDITORS -> PEOPLE_READ + PEOPLE_EDIT
Mọi nhóm khác   -> không cấp authority ứng dụng
```

### 6.1. Bean LdapAuthoritiesPopulator

**Thêm vào class `LdapSecurityConfiguration` ở mục 5:**

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator;

@Bean
LdapAuthoritiesPopulator applicationAuthorities(
        @Qualifier("securityLdapContextSource")
        DefaultSpringSecurityContextSource source) {

    DefaultLdapAuthoritiesPopulator ldapGroups =
            new DefaultLdapAuthoritiesPopulator(source, "ou=groups");

    ldapGroups.setGroupSearchFilter(
            "(&(objectClass=groupOfNames)(member={0}))");
    ldapGroups.setGroupRoleAttribute("cn");
    ldapGroups.setRolePrefix("LDAP_");
    ldapGroups.setConvertToUpperCase(true);
    ldapGroups.setSearchSubtree(false);

    return (userData, username) -> {
        Set<GrantedAuthority> allowed = new HashSet<>();

        for (GrantedAuthority group :
                ldapGroups.getGrantedAuthorities(userData, username)) {

            switch (group.getAuthority()) {
                case "LDAP_APP_READERS" ->
                        allowed.add(new SimpleGrantedAuthority("PEOPLE_READ"));

                case "LDAP_APP_EDITORS" -> {
                    allowed.add(new SimpleGrantedAuthority("PEOPLE_READ"));
                    allowed.add(new SimpleGrantedAuthority("PEOPLE_EDIT"));
                }

                default -> {
                    // Nhóm không nằm trong allowlist: không cấp quyền.
                }
            }
        }
        return allowed;
    };
}
```

Đoạn này là **một method đặt bên trong class cấu hình**; các import bổ sung nằm ở đầu file Java thực tế. Không copy method cùng `import` vào giữa thân class.

Để hoạt động an toàn, cần bảo đảm:

1. Người dùng không có khả năng tự ý sửa membership của `app_readers`/`app_editors`.
2. `ou=groups` là nhánh **được tin cậy**; không mở rộng search base đến nhóm do người dùng tự tạo.
3. `cn` của nhóm được quản lý theo quy ước ổn định, không cho role trùng/đổi tên tùy tiện.
4. Các trường hợp filter trả về nhiều nhóm hợp lệ được kết hợp bằng tập `Set` để tránh trùng authority.
5. Một lỗi LDAP khi tìm nhóm không được tự chuyển thành quyền mặc định rộng hơn. Không `catch Exception` rồi cấp `PEOPLE_EDIT`.

**Lưu ý:** `searchSubtree(false)` chỉ xét nhóm ngay dưới `ou=groups`, phù hợp cấu trúc LDIF ở trên. Nếu nhóm nằm trong nhánh con, có thể cần subtree search, nhưng điều đó mở rộng phạm vi quyền; phải kiểm soát lại allowlist và ACL.

### 6.2. Tại sao tách `LDAP_` khỏi `PEOPLE_`?

Không nên gán thẳng mọi group CN thành Spring authority:

```text
LDAP group cn=app_readers  ---> LDAP_APP_READERS (metadata)
                                   |
                                   v
                             mapping allowlist
                                   |
                                   v
                                PEOPLE_READ
```

Như vậy, thay đổi tên nhóm hoặc di chuyển nhóm LDAP không tự tạo quyền ứng dụng mới nếu không có một quyết định mapping cụ thể. Hệ thống còn có thể thêm các quyền chi tiết như `PEOPLE_EXPORT`, `GROUP_MANAGE` hoặc `AUDIT_READ` mà không gắn trực tiếp chúng với tên group tùy ý.

**Giới hạn còn lại:** nếu ai đó có quyền tạo/đổi tên/move nhóm **trong chính `ou=groups` được tin cậy** và gắn `member`, họ có thể tác động đến authorization. Vì thế directory ACL và quy trình quản trị nhóm là một phần của ranh giới bảo mật, không chỉ đoạn `switch` ở Java.

## 7. Tích hợp LDAP Bind với AuthenticationManager

Spring Security 6.5+ cung cấp `LdapBindAuthenticationManagerFactory`. Nó dùng `ContextSource` để tìm người dùng và xác thực thông qua LDAP Bind, rồi gọi `LdapAuthoritiesPopulator` vừa cấu hình.

**Tiếp tục thêm vào `LdapSecurityConfiguration`:**

```java
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Bean("ldapAuthenticationManager")
AuthenticationManager ldapAuthenticationManager(
        @Qualifier("securityLdapContextSource")
        BaseLdapPathContextSource source,
        LdapAuthoritiesPopulator applicationAuthorities) {

    LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(source);

    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter(
            "(&(objectClass=inetOrgPerson)(uid={0}))");
    factory.setLdapAuthoritiesPopulator(applicationAuthorities);

    return factory.createAuthenticationManager();
}
```

Trong ví dụ:

- `factory.setUserSearchBase("ou=people")`: tìm account trong nhánh con, **tương đối với base DN** của context source.
- `(uid={0})`: điều kiện tìm theo **login name** mà người dùng nhập. Đây không phải DN; bộ tìm kiếm sẽ lấy DN của entry khớp.
- `BindAuthenticator` thực hiện Bind với **DN tìm được** và password mà người dùng vừa gửi; không đọc `userPassword` để so sánh tại Java.
- Sau xác thực thành công, `applicationAuthorities` tìm group membership và trả authority đã qua allowlist.
- Nếu có nhiều entry cùng `uid` ở vùng tìm kiếm, không được coi kết quả là một định danh duy nhất. Directory cần quy tắc uniqueness/tenant rõ ràng.

**Tuyệt đối không** thay `setUserSearchFilter(...)` bằng chuỗi nối từ HTTP input, ví dụ `"(uid=" + username + ")"`. Bộ lọc được cấu hình cố định với placeholder `{0}`, Spring Security sẽ xử lý giá trị tìm kiếm qua cơ chế của nó. Cũng không nhận một `userDn` hoàn chỉnh từ frontend rồi tự chọn container ngoài phạm vi cho phép.

### 7.1. Trường hợp có quy tắc DN cố định

Spring Security cũng cho phép:

```java
factory.setUserDnPatterns("uid={0},ou=people");
```

Nhưng chỉ dùng khi **mọi user** thật sự được đặt tên theo quy tắc đó và ranh giới container cố định. Trong directory có `cn=Lan Nguyen,ou=employees,...` hoặc nhiều OU, nên **user search** có thể phù hợp hơn vì ứng dụng cần tìm DN thực. Đừng đồng thời bật nhiều cách tìm user mà không hiểu thứ tự thử và phạm vi tìm kiếm.

## 8. Bảo vệ HTTP endpoint bằng authorities

Sau khi xác thực, Spring Security có một `Authentication` chứa danh tính và `GrantedAuthority`. Một `SecurityFilterChain` có thể dùng authority để bảo vệ thao tác xem/chỉnh sửa.

**Thêm vào `LdapSecurityConfiguration`:**

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        @Qualifier("ldapAuthenticationManager")
        AuthenticationManager ldapAuthenticationManager) throws Exception {

    http.authenticationManager(ldapAuthenticationManager);

    http.authorizeHttpRequests(authorization -> authorization
            .requestMatchers("/login", "/error").permitAll()
            .requestMatchers(HttpMethod.GET,
                    "/api/people", "/api/people/**")
                .hasAuthority("PEOPLE_READ")
            .requestMatchers(HttpMethod.POST,
                    "/api/people", "/api/people/**")
                .hasAuthority("PEOPLE_EDIT")
            .anyRequest().authenticated());

    // Demo sử dụng login form + session, giữ CSRF protection mặc định.
    http.formLogin(Customizer.withDefaults());

    return http.build();
}
```

Đoạn mã kiểm soát **GET** và **POST** trong vùng `/api/people`. Trong ứng dụng thực phải xác định thêm chính sách cho `PUT`, `PATCH`, `DELETE` và các API quản trị; `anyRequest().authenticated()` chỉ yêu cầu có tài khoản hợp lệ, **không** đồng nghĩa mọi endpoint còn lại đã được phân quyền chức năng chặt chẽ.

Ví dụ kỳ vọng:

| HTTP request | Lan: `PEOPLE_READ` | Binh: `PEOPLE_READ` + `PEOPLE_EDIT` |
|---|---|---|
| `GET /api/people/lan` | Cho phép | Cho phép |
| `POST /api/people/lan` | Từ chối vì thiếu `PEOPLE_EDIT` | Cho phép **nếu** CSRF token và điều kiện nghiệp vụ hợp lệ |
| `GET /api/unknown` | Có thể qua lớp authentication | Có thể qua lớp authentication; controller còn có thể trả 404 |

**Về CSRF:** ví dụ dùng form login và cookie session nên giữ CSRF protection. Một POST có quyền `PEOPLE_EDIT` nhưng thiếu CSRF token vẫn có thể nhận **403**. Đừng tắt CSRF chỉ để bài test POST dễ chạy; nếu xây stateless API dùng bearer token thì đó là thiết kế authentication khác cần cấu hình và đánh giá riêng.

**Về HTTP status:** với form login, unauthenticated browser request thường bị chuyển hướng đến trang đăng nhập; request đã authenticated nhưng thiếu quyền thường bị từ chối (thường 403). Không mặc định mọi request chưa đăng nhập đều trả 401 nếu application đang dùng form login.

## 9. Kết nối chức năng nghiệp vụ với Spring Data LDAP

Tầng bảo vệ HTTP và tầng truy cập LDAP có mục đích tách biệt:

```text
                 Spring Security
                       |
            Xác thực + ánh xạ quyền
                       |
                       v
               SecurityFilterChain
                       |
                   Controller
                       |
              Service nghiệp vụ
                       |
            LdapTemplate / Repository
                       |
                LDAP directory
```

Một phương thức nghiệp vụ có thể cần đọc thông tin người dùng sau khi đăng nhập. Dùng một bean `LdapTemplate` được cấu hình rõ, chạy bằng **service identity được cấp quyền tối thiểu**, không giả định nó tự sử dụng credential của người đang đăng nhập.

### 9.1. DTO chỉ đọc và lookup bằng DN an toàn

**`PersonCard.java`**

```java
package com.example.ldap.directory;

public record PersonCard(String uid, String fullName, String email) {}
```

**`PersonDirectoryReader.java`**

```java
package com.example.ldap.directory;

import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.NamingException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Repository;

@Repository
public class PersonDirectoryReader {

    private final LdapTemplate ldapTemplate;

    public PersonDirectoryReader(
            @Qualifier("directoryLdapTemplate") LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public PersonCard findByUid(String uid) {
        if (uid == null || uid.isBlank()) {
            throw new IllegalArgumentException("uid không được rỗng");
        }

        Name relativeDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();

        AttributesMapper<PersonCard> mapper = attrs ->
                new PersonCard(
                        required(attrs, "uid"),
                        required(attrs, "cn"),
                        optional(attrs, "mail"));

        return ldapTemplate.lookup(relativeDn, mapper);
    }

    private static String required(Attributes attrs, String key)
            throws NamingException {
        Attribute attribute = attrs.get(key);
        if (attribute == null || attribute.size() == 0) {
            throw new IllegalStateException("Thiếu thuộc tính: " + key);
        }
        return (String) attribute.get();
    }

    private static String optional(Attributes attrs, String key)
            throws NamingException {
        Attribute attribute = attrs.get(key);
        return attribute == null || attribute.size() == 0
                ? null : (String) attribute.get();
    }
}
```

Bean tương ứng, bổ sung vào `LdapSecurityConfiguration`:

```java
import org.springframework.ldap.core.LdapTemplate;

@Bean("directoryLdapTemplate")
LdapTemplate directoryLdapTemplate(
        @Qualifier("securityLdapContextSource")
        DefaultSpringSecurityContextSource source) {
    return new LdapTemplate(source);
}
```

Trong ví dụ nhỏ này, `directoryLdapTemplate` dùng **service lookup identity** đã cấu hình trong `DefaultSpringSecurityContextSource`. Nó không dùng Bind của người dùng cuối để đọc entry; Spring Security đã xác thực user **trước** khi controller chạy. Nếu ứng dụng có một service account riêng để truy cập dữ liệu, hãy tạo `ContextSource` và `LdapTemplate` riêng cùng qualifier, rồi gán ACL phù hợp.

**Lưu ý về DN:** ví dụ `findByUid` chỉ đúng nếu naming convention thật là `uid=<login>,ou=people`. Trong directory có DN khác quy tắc, cần tìm `uid` bằng `LdapQueryBuilder` với filter an toàn, không đoán DN bằng cách ghép chuỗi.

### 9.2. Gắn HTTP controller vào quyền

**`PersonController.java` — minh họa GET**

```java
package com.example.ldap.api;

import com.example.ldap.directory.PersonCard;
import com.example.ldap.directory.PersonDirectoryReader;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/people")
public class PersonController {

    private final PersonDirectoryReader directory;

    public PersonController(PersonDirectoryReader directory) {
        this.directory = directory;
    }

    @GetMapping("/{uid}")
    public PersonCard get(@PathVariable String uid) {
        return directory.findByUid(uid);
    }
}
```

Khi trình duyệt gửi request đã đăng nhập đến `GET /api/people/lan`, Spring Security sẽ kiểm tra `PEOPLE_READ` **trước khi** vào controller; controller mới truy vấn directory. Ví dụ không có method POST nên request POST có thể bị từ chối hoặc không có handler ngay cả nếu quyền ứng dụng đã được cấp — cần xây thêm nghiệp vụ ghi và validation riêng nếu muốn thử POST thật.

Nếu dùng `LdapRepository<PersonEntry>` của Spring Data LDAP thay cho `LdapTemplate`, cách bảo vệ HTTP **không thay đổi**. Chỉ cần bảo đảm repository dùng **đúng ContextSource/LdapTemplate** đã được cấu hình, tránh khi ứng dụng có nhiều bean service và security cùng truy cập các LDAP endpoint khác nhau.

## 10. Phân biệt quyền ứng dụng và ACL trên LDAP server

Ngay cả khi Spring Security cấp `PEOPLE_EDIT`, LDAP server có thể từ chối ghi vì bind identity của `LdapTemplate` không có quyền sửa `mail` hoặc DN đích. Đây **không phải lỗi mapping nhóm**, mà là **ACL ở tầng directory**.

```text
Lan đăng nhập -> PEOPLE_READ
                   |
                   v
            GET /api/people/lan -> Security cho phép
                   |
                   v
              LDAP service account
                   |
                   v
          LDAP ACL: được đọc uid/cn/mail

Binh đăng nhập -> PEOPLE_EDIT
                   |
                   v
            POST /api/people/lan -> Security cho phép
                   |
                   v
              LDAP service account
                   |
                   v
          LDAP ACL: chỉ đọc -> MODIFY BỊ TỪ CHỐI
```

Thiết kế production phải quyết định rõ **identity ghi LDAP**: tài khoản riêng có quyền sửa những thuộc tính và nhánh được phép, hoặc cơ chế delegation được server hỗ trợ. Không tự cấp quyền ghi admin cho lookup account chỉ vì cần demo POST.

| Lớp | Người chịu trách nhiệm | Nếu bị bỏ qua |
|---|---|---|
| HTTP authentication | Spring Security | Request chưa xác thực có thể vào API |
| App authorities | Spring Security mapping + authorization | Người có tài khoản nhưng không có quyền vẫn có thể gọi chức năng nhạy cảm |
| Business rules | Service nghiệp vụ | Có thể sửa sai entry/tenant dù có role hợp lệ |
| LDAP ACL/schema | LDAP server | Service account có thể vượt phạm vi cần thiết hoặc ghi dữ liệu sai |
| Audit, logging, monitoring | Ứng dụng và directory | Khó điều tra việc cấp quyền, thay đổi nhóm và lỗi xác thực |

Khi một API cho phép cập nhật entry, quyền `PEOPLE_EDIT` cũng **không đủ** nếu có giới hạn tenant, ownership, yêu cầu phê duyệt hoặc optimistic concurrency. Những điều kiện đó phải được kiểm tra thêm ở tầng service và, khi cần, bằng thao tác ghi có điều kiện tại LDAP server.

## 11. Nếu directory dùng `posixGroup.memberUid` thì sao?

Không phải mọi directory đều lưu thành viên nhóm bằng DN. Có hai mô hình tiêu biểu:

| ObjectClass nhóm | Thuộc tính thành viên | Kiểu giá trị |
|---|---|---|
| `groupOfNames` | `member` | DN đầy đủ của người dùng |
| `groupOfUniqueNames` | `uniqueMember` | Name and Optional UID, thường biểu diễn DN |
| `posixGroup` | `memberUid` | Tên đăng nhập, ví dụ `lan` |

Với `posixGroup`, filter của populator phải dùng **`{1}`** (login), không dùng `{0}` (DN):

```java
DefaultLdapAuthoritiesPopulator posixGroups =
        new DefaultLdapAuthoritiesPopulator(source, "ou=posixGroups");
posixGroups.setGroupSearchFilter(
        "(&(objectClass=posixGroup)(memberUid={1}))");
posixGroups.setGroupRoleAttribute("cn");
```

Trường hợp `posixGroup` còn có membership **primary group** thể hiện qua `gidNumber` của user; nhóm chính đó **không bắt buộc xuất hiện trong `memberUid`**. Vì vậy filter `(memberUid={1})` có thể không trả toàn bộ membership POSIX. Nếu quyền ứng dụng phụ thuộc primary group, cần giải quyết riêng `gidNumber` → group và uniqueness, không mặc định `DefaultLdapAuthoritiesPopulator` đã xử lý.

Không tự trộn `member` và `memberUid` trong cùng filter nếu schema/ACL thực tế chưa được xác nhận. Mỗi backend có thể cần populator hoặc custom strategy riêng.

## 12. Nhóm lồng nhau, memberOf và các giới hạn

Với membership trực tiếp:

```text
uid=lan  -->  cn=app_readers
```

`DefaultLdapAuthoritiesPopulator` tìm nhóm có `member` trùng DN của Lan. Nếu LDAP dùng **nhóm lồng nhau**:

```text
uid=lan
   |
   v
cn=team_a (member=uid=lan,...)
   |
   v
cn=app_editors (member=cn=team_a,...)
```

thì phép lọc `(member=uid=lan,...)` trên `app_editors` **không tự mở rộng quan hệ bắc cầu**. Spring Security còn có `NestedLdapAuthoritiesPopulator` trong một số phiên bản, hoặc directory cung cấp matching rule đặc thù; phải kiểm tra cách giải quyết vòng lặp, quyền và chi phí truy vấn trước khi sử dụng.

Với **Active Directory**, thuộc tính backlink `memberOf` hoặc matching rule `1.2.840.113556.1.4.1941` có thể hỗ trợ truy vấn kiểu lồng nhau trong một số điều kiện, nhưng đây là hành vi đặc thù AD, **không** phải tính năng chung của mọi LDAP server. Các thuộc tính/giới hạn như `tokenGroups` và range retrieval của `member` cũng cần xử lý theo docs của AD.

**Đừng phân quyền chỉ dựa vào việc một thuộc tính `memberOf` xuất hiện trong DTO** nếu chưa biết nó là thuộc tính được server duy trì, có đồng bộ và đầy đủ hay không. Một số OpenLDAP deployment cần plugin/overlay riêng để có backlink; một số quyền có thể đến từ primary group hoặc nested membership không thể đọc qua một filter đơn giản.

## 13. Cập nhật membership và hiệu lực của quyền

Một câu hỏi quan trọng: “Nếu admin xóa Lan khỏi `app_readers`, Lan lập tức mất quyền `PEOPLE_READ` chưa?”

Không nhất thiết. Quy trình thường là:

```text
09:00 Lan đăng nhập
      LDAP groups -> PEOPLE_READ
      Spring Security lưu Authentication vào session

09:15 Admin xóa member=uid=lan khỏi cn=app_readers

09:16 Lan dùng session cũ
      Authorities trong SecurityContext có thể vẫn chứa PEOPLE_READ

10:00 Lan đăng xuất/đăng nhập lại
      Tra cứu nhóm mới -> không còn PEOPLE_READ
```

Spring Security không mặc nhiên requery LDAP groups **trước mọi request** chỉ vì một group trong directory thay đổi. Với hệ thống nhạy cảm, thiết kế chính sách:

1. Thời hạn session và cơ chế reauthentication phù hợp.
2. Hủy hoặc làm mới session khi có sự kiện thu hồi quyền quan trọng.
3. Nếu cache authorities, đặt TTL và eviction rõ ràng; không vô tình kéo dài quyền đã bị thu hồi.
4. Xác định consistency giữa LDAP writable server và read replicas.
5. Audit ai thêm/xóa member, thời điểm thay đổi được chấp nhận và người dùng chịu ảnh hưởng.

**Không dùng mỗi `exists(member)` như một phép “khóa” quyền**; membership có thể đổi sau khi kiểm tra. Với thao tác đặc quyền cao, cân nhắc xác minh lại ở điểm thực thi bằng nguồn dữ liệu/quy trình nhất quán thích hợp, không chỉ dựa trên session lâu dài.

### 13.1. Thay đổi nhóm an toàn

Khi nghiệp vụ cần thêm một user vào `groupOfNames`, có thể dùng `LdapTemplate.modifyAttributes` với `ADD_ATTRIBUTE` để **thêm một giá trị** thay vì đọc và `REPLACE_ATTRIBUTE` toàn bộ danh sách:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;

void addMember(LdapTemplate ldapTemplate,
               Name relativeGroupDn, Name fullUserDn) {

    ModificationItem item = new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", fullUserDn.toString()));

    ldapTemplate.modifyAttributes(
            relativeGroupDn, new ModificationItem[] {item});
}
```

Ở đây, **group DN** truyền vào template là **tương đối với `ContextSource.base`**, còn **member DN** trong thuộc tính `groupOfNames.member` là **DN đầy đủ**. Hai loại DN không được đánh tráo.

Việc cập nhật membership cần service account có ACL phù hợp, kiểm tra user/group tồn tại và xử lý cạnh tranh. Không đưa chức năng thêm quyền vào cùng một endpoint cho người dùng chỉ có `PEOPLE_EDIT` nếu nghiệp vụ không cho phép họ quản lý quyền.

## 14. Kiểm thử xác thực và ánh xạ quyền

### 14.1. Integration test với LDAP test directory

Khi có server test chứa LDIF mẫu và người dùng có mật khẩu test, có thể gọi trực tiếp `AuthenticationManager` để xác minh cả hai bước **Bind + group mapping**.

**`LdapAuthenticationIT.java`**

```java
package com.example.ldap.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class LdapAuthenticationIT {

    @Autowired
    @Qualifier("ldapAuthenticationManager")
    AuthenticationManager authenticationManager;

    @Test
    void lanCanReadButCannotEdit() {
        Authentication result = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(
                        "lan", "only-for-test-lan"));

        assertTrue(result.isAuthenticated());
        assertTrue(hasAuthority(result, "PEOPLE_READ"));
        assertFalse(hasAuthority(result, "PEOPLE_EDIT"));
    }

    @Test
    void binhCanReadAndEdit() {
        Authentication result = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(
                        "binh", "only-for-test-binh"));

        assertTrue(result.isAuthenticated());
        assertTrue(hasAuthority(result, "PEOPLE_READ"));
        assertTrue(hasAuthority(result, "PEOPLE_EDIT"));
    }

    @Test
    void wrongPasswordCannotAuthenticate() {
        assertThrows(AuthenticationException.class, () ->
                authenticationManager.authenticate(
                        new UsernamePasswordAuthenticationToken(
                                "lan", "incorrect-password")));
    }

    private static boolean hasAuthority(
            Authentication authentication, String authority) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
```

**Điều kiện chạy:** test server phải hỗ trợ LDAPS với trust chain hợp lệ; fixtures được nạp đầy đủ; service lookup DN/password chính xác và chỉ có dữ liệu test; Spring có bean manager đúng như phần cấu hình. Đây là **integration test**, không phải test độc lập có thể chạy khi không có LDAP server.

Không cố chứng minh password đúng bằng cách gọi `ldapTemplate.lookup("userPassword")`. Nếu server trả hashed value, ứng dụng cũng không được phép suy luận cách xác thực theo logic riêng; Bind là cơ chế được server xác thực.

### 14.2. Ma trận kiểm thử quyền và ranh giới tin cậy

| Trường hợp | Kỳ vọng |
|---|---|
| `lan` + đúng password | Xác thực thành công, có `PEOPLE_READ` |
| `lan` + sai password | Xác thực thất bại, không có session hợp lệ |
| `binh` + đúng password | Có `PEOPLE_READ` và `PEOPLE_EDIT` |
| User hợp lệ không ở nhóm được allowlist | Xác thực có thể thành công nhưng không có quyền nghiệp vụ |
| Tồn tại group `cn=admins` ngoài allowlist | Không tự thành `PEOPLE_EDIT` hoặc quyền admin |
| Nhóm có `member` là DN khác dù cùng `uid` | Không nhầm là thành viên của group |
| Đổi nhóm từ `app_readers` sang `app_editors` | Sau reauthentication, authorities phản ánh group mới |
| User bị xóa khỏi group trong lúc session còn sống | Kiểm tra chính sách session/refresh/revocation đã thiết kế |
| LDAP group search thiếu quyền | Không cấp quyền cao hơn; log/metric phân loại sự cố |
| Server LDAP không kết nối được | Không fallback sang bypass authentication |
| Filter có login chứa `*`/`(`/`)` | Không cho LDAP filter injection/đăng nhập nhầm account |
| Group schema chuyển sang `posixGroup.memberUid` | Cần thay filter `{1}` và kiểm tra primary group |
| HTTP GET có authority READ | Cho phép vào handler khi đã authenticated |
| HTTP POST thiếu EDIT hoặc CSRF token | Bị từ chối bởi lớp thích hợp |
| LDAP ACL từ chối thao tác ghi | App authority không vượt được ACL phía directory |

### 14.3. Test HTTP không thay thế test LDAP

Với `spring-security-test`, test dùng `@WithMockUser(authorities = "PEOPLE_READ")` giúp kiểm tra `SecurityFilterChain` nhưng **bỏ qua LDAP Bind và group loading**. Ví dụ:

```java
@Test
@WithMockUser(authorities = "PEOPLE_READ")
void readAuthorityCanAccessGet() throws Exception {
    // Với MockMvc đã cấu hình controller và dữ liệu test:
    mockMvc.perform(get("/api/people/lan"))
            .andExpect(status().isOk());
}
```

Các import JUnit/MockMvc/`WithMockUser` và fixture cho controller được lược bớt vì đây là khung minh họa. Nếu controller gọi LDAP trực tiếp, test còn cần mock `PersonDirectoryReader` hoặc test directory. Bài test này chỉ chứng minh **quy tắc HTTP authorization**, không chứng minh `member={0}` đã trả đúng group.

Một bộ test hoàn chỉnh cần **cả hai tầng**: authentication manager integration test với directory thật và web authorization test với principal/authority giả lập. Đừng dùng một loại test để suy ra toàn bộ hệ thống an toàn.

## 15. Những lỗi dễ gặp khi tích hợp thực tế

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Sai password nhưng vẫn đọc được user qua `LdapTemplate` | Nhầm service lookup với xác thực | Dùng LDAP Bind qua `AuthenticationManager` |
| Đăng nhập thành công nhưng authority rỗng | Group search base/filter sai, thiếu quyền đọc hoặc user chưa thuộc group | Kiểm tra `member={0}`, ACL, container |
| `groupOfNames.member` dùng `lan` | Sai schema: cần DN, không phải login | Lưu đúng DN đầy đủ của user |
| `posixGroup.memberUid` không khớp | Dùng filter `member={0}` thay vì `memberUid={1}` | Chọn filter đúng kiểu membership |
| Tên nhóm `app_editors` không thành `PEOPLE_EDIT` | Prefix/case mapping hoặc allowlist sai | Xem `LDAP_APP_EDITORS` và đường mapping rõ ràng |
| User thuộc nhóm trong nested group nhưng thiếu quyền | Populator chỉ tìm direct membership | Dùng strategy nested group đặc thù và kiểm thử |
| Spring Security bảo vệ HTTP nhưng LDAP modify bị từ chối | Service account không có ACL sửa | Thiết kế write identity/ACL riêng |
| User bị rút khỏi nhóm nhưng vẫn có quyền | SecurityContext/session hoặc cache chưa được cập nhật | Reauthentication, session revocation, TTL phù hợp |
| Hai user cùng `uid` trong nhiều OU | User search không bảo đảm uniqueness | Cố định tenant/base và uniqueness |
| Lỗi `PKIX path building failed` | Java không tin server certificate | Sửa CA/truststore, không tắt TLS verify |
| Endpoint POST trả 403 cho editor | Có thể thiếu CSRF token dù đúng authority | Kiểm tra CSRF + role trước khi kết luận mapping sai |
| `@WithMockUser` test pass nhưng login thật lỗi | Test HTTP không thực hiện LDAP Bind | Chạy integration test AuthenticationManager |
| App cho phép group tự tạo cấp quyền admin | Không giới hạn group search và mapping | Dùng group OU đáng tin + allowlist + LDAP ACL |
| Repository dùng context sai/khác môi trường | Nhiều bean `ContextSource`/`LdapTemplate` thiếu qualifier | Cấu hình rõ bean/endpoint và kiểm thử |

Một lỗi đáng lưu ý khác là **bắt mọi ngoại lệ LDAP rồi trả “không có role”**. Trong một số bài toán, thiếu quyền đọc nhóm hoặc network lỗi có thể tạo trạng thái quyền rỗng; đó là *fail closed* về chức năng, nhưng ứng dụng vẫn nên báo **sự cố dịch vụ xác thực/phân quyền**, không gán là một tài khoản “không có nhóm” hợp lệ nếu cần điều tra vận hành.

## 16. Bảo mật và vận hành production

### 16.1. Checklist triển khai

1. **Kết nối qua TLS hợp lệ:** LDAPS hoặc StartTLS với certificate trust, hostname verification và timeout rõ ràng; không gửi password user trên cleartext.
2. **Lookup account quyền tối thiểu:** đủ đọc các thuộc tính cần tìm user và nhóm, không được sửa group quản trị.
3. **Tìm user có ranh giới:** `ou=people`/tenant xác định, filter tham số hóa, không tin DN do client gửi; cần uniqueness.
4. **Bind người dùng thực sự:** để LDAP server xác minh password; không truy vấn `userPassword` về Java.
5. **Lấy membership đúng schema:** `member`/`uniqueMember` dạng DN hoặc `memberUid` dạng login; kiểm tra nested/primary groups.
6. **Allowlist group → authority:** chỉ cho phép nhóm được tin cậy tạo quyền; tránh tự cấp `ROLE_ADMIN` từ tên bất kỳ.
7. **Phân quyền toàn bộ endpoint:** GET/POST/PUT/PATCH/DELETE, tenant/ownership, CSRF hoặc token policy phù hợp với cách login.
8. **ACL phía LDAP server:** không coi một `GrantedAuthority` của web là quyền sửa mọi DN/attribute trong directory.
9. **Quản lý hiệu lực quyền:** session, caching, revocation, replication lag và reauthentication khi membership thay đổi.
10. **Audit và theo dõi:** login success/failure, group-lookup failure, denied request, thay đổi membership; không log password, raw filter hay dữ liệu nhạy cảm.

### 16.2. Quan sát luồng login mà không lộ thông tin

Một trace có thể gồm:

```text
authentication.login
  ldap.user_search             [success / not_found / ambiguous]
  ldap.user_bind               [success / bad_credentials / connection_error]
  ldap.group_search            [success / denied / connection_error]
  app.authority_mapping        [groups_matched / authorities_granted]
  web.authorization           [allowed / denied]
```

Đây là tên span/sự kiện **minh họa**, không mặc định Spring Security hoặc Spring LDAP tự xuất đủ các span này. Khi thêm instrumentation, đừng đưa username, full DN, email, mật khẩu, session ID hay raw LDAP filter vào metric tag có cardinality cao hoặc log không kiểm soát.

**Định nghĩa lỗi rõ ràng:** một mật khẩu sai khác với LDAP server mất kết nối; user không thuộc group khác với group search bị ACL từ chối. Phân loại đúng giúp vận hành mà không lộ chi tiết nhạy cảm tới người đăng nhập.

## 17. Bài tập mở rộng

1. Thêm `uid=mai` vào `ou=people` nhưng không cho vào nhóm nào; xác minh **đăng nhập đúng nhưng GET bị từ chối**.
2. Thêm Lan vào `app_editors`; đăng xuất/đăng nhập lại và xác nhận Lan được cấp `PEOPLE_EDIT`. Sau đó xóa membership, thử với session cũ và giải thích lý do cần chính sách revocation.
3. Chuyển mô hình nhóm sang `posixGroup` với `memberUid=lan`; đổi filter thành `memberUid={1}` và xác minh kết quả. Nêu sự khác nhau khi quyền được xác định từ `gidNumber` của nhóm chính.
4. Thêm nhóm `cn=admins` trong `ou=groups` rồi đưa Lan vào. Chứng minh **allowlist hiện tại không cấp quyền admin**.
5. Giới hạn lookup account chỉ đọc `uid`/`cn` của `ou=people` và `cn`/`member` của `ou=groups`; xác nhận password check hoạt động và thử một thao tác sửa nhóm bị LDAP ACL từ chối.
6. Đo thời gian tìm user, Bind và tải nhóm trên test directory. So sánh số lượng nhóm, search scope và tác động của index đối với thời gian đăng nhập.
7. Thêm endpoint `DELETE /api/people/{uid}` nhưng **không cấp quyền mặc định**; xác định authority chuyên biệt, business rules, conditional write và ACL trước khi triển khai.

## 18. Câu hỏi tự đánh giá

1. Spring Data LDAP repository và Spring Security LDAP khác nhau ở bước nào của luồng đăng nhập?
2. Tại sao một lần `LdapTemplate.lookup("uid=lan,...")` thành công không chứng minh mật khẩu Lan đúng?
3. Với `groupOfNames`, thuộc tính nào chứa thành viên và có kiểu giá trị gì?
4. `{0}` và `{1}` trong `DefaultLdapAuthoritiesPopulator.setGroupSearchFilter(...)` khác nhau ra sao?
5. Vì sao nên dùng allowlist `LDAP_APP_EDITORS → PEOPLE_EDIT` thay vì biến mọi group name thành authority tương ứng?
6. Sau khi Bind thành công nhưng user không thuộc nhóm nào, ứng dụng nên đối xử với authentication và authorization như thế nào?
7. Tại sao `PEOPLE_EDIT` không tự cho phép `LdapTemplate.modifyAttributes` nếu LDAP service account thiếu ACL?
8. Khi người dùng bị xóa khỏi group, session Spring Security có tự đổi authority ngay không?
9. Vì sao `memberUid={1}` có thể bỏ sót primary group trong schema POSIX?
10. `@WithMockUser` giúp kiểm thử điều gì và không kiểm thử được điều gì?
11. Vì sao không được tắt CSRF tùy tiện khi dùng form login/session?
12. Làm sao kiểm tra người dùng không thể tự tạo group để nhận quyền admin?

**Ghi nhớ:** xây luồng **LDAP Bind để xác thực**, **tìm nhóm theo đúng schema**, **allowlist ánh xạ nhóm thành GrantedAuthority**, rồi **bảo vệ endpoint và dữ liệu** bằng Spring Security kết hợp ACL của LDAP server. Dùng `LdapTemplate`/Spring Data LDAP repository cho CRUD theo DN/schema, không lấy việc đọc được entry làm bằng chứng đăng nhập. Luôn phân biệt DN nhóm với login, kiểm soát nhóm lồng nhau và độ trễ thu hồi quyền, giữ kết nối TLS hợp lệ, kiểm thử cả Bind + HTTP authorization và không tự biến một tên nhóm tùy ý thành quyền đặc biệt.

### Tài liệu tham khảo

- Spring Security — [LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): Bind authentication, user search và group authorities.
- Spring Security API — [`LdapBindAuthenticationManagerFactory`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/LdapBindAuthenticationManagerFactory.html): tạo AuthenticationManager dùng LDAP Bind.
- Spring Security API — [`DefaultLdapAuthoritiesPopulator`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html): group search base, `{0}` DN, `{1}` username, role attribute/prefix.
- Spring Security API — [`DefaultSpringSecurityContextSource`](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/ldap/DefaultSpringSecurityContextSource.html): context source cho LDAP Security, URL/base DN và Bind authentication.
- Spring Security — [Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `SecurityFilterChain`, `hasAuthority`, request matchers.
- Spring LDAP — [Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): `LdapTemplate` và `ContextSource`.
- Spring Data LDAP — [Repositories](https://docs.spring.io/spring-data/ldap/reference/ldap/repositories.html): entity ODM, `LdapRepository` và cách truy cập LDAP.
- IETF [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): LDAP Bind, các cơ chế xác thực và bảo vệ thông tin xác thực.
- IETF [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515) và [RFC 4519 — LDAP Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): filter an toàn, `groupOfNames`/`member`.
- IETF [RFC 2307 — LDAP as a Network Information Service](https://www.rfc-editor.org/rfc/rfc2307): `posixGroup`, `memberUid`, `gidNumber` và nhóm POSIX.
