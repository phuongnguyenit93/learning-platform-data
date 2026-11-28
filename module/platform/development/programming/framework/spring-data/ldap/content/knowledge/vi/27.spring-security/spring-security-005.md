# Tra cứu nhóm và ánh xạ sang GrantedAuthority

Trong **Spring Data LDAP**, ứng dụng Java có thể dùng `LdapRepository` hoặc `LdapTemplate` để đọc entry trong cây thư mục LDAP. Khi kết hợp với **Spring Security**, một nhu cầu rất phổ biến là: sau khi người dùng đăng nhập thành công bằng LDAP, ứng dụng phải biết họ thuộc **nhóm nào** để quyết định được phép gọi API, xem trang quản trị hoặc thao tác dữ liệu nào.

Quá trình này có hai nhiệm vụ độc lập nhưng liên quan chặt chẽ:

1. **Authentication:** xác minh danh tính người dùng, thường qua LDAP bind.
2. **Authorization:** tìm các nhóm/quyền của danh tính đó rồi chuyển chúng thành các đối tượng `GrantedAuthority` mà Spring Security có thể kiểm tra.

Spring Security LDAP cung cấp **`LdapAuthoritiesPopulator`** và triển khai phổ biến **`DefaultLdapAuthoritiesPopulator`** cho công việc tra cứu nhóm. Bài này tập trung vào cách đọc membership theo schema, tạo authority theo quy tắc có kiểm soát và kết nối kết quả với `hasRole(...)`/`hasAuthority(...)`.

Sau bài học, bạn có thể:

- Phân biệt group entry, DN thành viên, thuộc tính `member`/`uniqueMember`/`memberUid` và `GrantedAuthority`.
- Cấu hình `DefaultLdapAuthoritiesPopulator` với `groupSearchBase`, `groupSearchFilter`, `groupRoleAttribute` và `rolePrefix`.
- Hiểu các placeholder **`{0}` là full DN** và **`{1}` là username** trong filter tra cứu nhóm.
- Ánh xạ tên nhóm thành `ROLE_DEVELOPERS` hoặc `ROLE_ADMINS` và dùng đúng API phân quyền.
- Phân biệt nhóm trực tiếp, nhóm lồng nhau, đặc điểm Active Directory và nhóm POSIX.
- Kiểm thử kết quả role, kiểm soát lỗi/ACL, tránh tự cấp quyền cao và quản lý quyền khi membership thay đổi.

## 1. Mô hình LDAP nhóm và quyền trong Spring Security

Giả sử LDAP server phục vụ naming context `dc=example,dc=org`:

```text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=groups
    ├── cn=developers
    └── cn=admins
```

Với schema `groupOfNames`, mỗi nhóm được biểu diễn thành **một entry riêng**. Entry nhóm có thuộc tính `member` chứa **DN đầy đủ** của các thành viên:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Tran Van Minh
sn: Tran

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org

dn: cn=admins,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: admins
member: uid=minh,ou=people,dc=example,dc=org
```

LDIF này minh họa **dữ liệu người dùng và nhóm**; không chứa mật khẩu. Để thử bind authentication, cần thiết lập credential test hợp lệ bằng cơ chế của LDAP server. Không đưa mật khẩu thật hoặc userPassword không được bảo vệ vào tài liệu hay repository mã nguồn.

### Từ nhóm LDAP đến quyền trong ứng dụng

```text
User đăng nhập: lan
        │
        ▼
LDAP authentication xác định
full DN = uid=lan,ou=people,dc=example,dc=org
        │
        ▼
Tìm trong ou=groups:
(&(objectClass=groupOfNames)
  (member=uid=lan,ou=people,dc=example,dc=org))
        │
        ▼
Nhóm khớp: cn=developers
        │ groupRoleAttribute = cn
        │ rolePrefix = ROLE_
        │ convertToUpperCase = true
        ▼
SimpleGrantedAuthority("ROLE_DEVELOPERS")
        │
        ▼
Authentication.getAuthorities()
        │
        ▼
hasRole("DEVELOPERS") -> cho phép
hasRole("ADMINS")     -> từ chối
```

LDAP **không tự định nghĩa `ROLE_DEVELOPERS` là quyền của Spring Security**. Đây là cách ứng dụng chọn để diễn giải tên nhóm thành authority. Directory chịu trách nhiệm dữ liệu membership; ứng dụng chịu trách nhiệm **quy tắc chuyển đổi và chính sách cho phép truy cập**.

## 2. Phân biệt authentication, group lookup và authority

| Tầng | Dữ liệu đầu vào | Kết quả | Thành phần |
| --- | --- | --- | --- |
| Authentication | Username, password | Người dùng đã được xác thực, DN/attributes | `LdapAuthenticator`, `BindAuthenticator` |
| Group lookup | Full DN, username | Những entry nhóm có membership phù hợp | `LdapAuthoritiesPopulator` |
| Authority mapping | Tên nhóm, thuộc tính vai trò | `GrantedAuthority`, ví dụ `ROLE_DEVELOPERS` | `DefaultLdapAuthoritiesPopulator` |
| Authority post-processing | Tập `GrantedAuthority` có sẵn | Tập authority sau chuẩn hóa/lọc thêm | `GrantedAuthoritiesMapper` |
| Authorization | `Authentication.getAuthorities()` | Cho phép/từ chối request hay method | `hasRole`, `hasAuthority`, AuthorizationManager |

**`GrantedAuthority`** là interface của Spring Security, thường hiện thực bằng `SimpleGrantedAuthority`. Nó có `getAuthority()` trả về một chuỗi như `ROLE_DEVELOPERS`, `directory:read` hoặc `document:approve`.

**`ROLE_` là quy ước**, không phải một LDAP object class hoặc thuộc tính mặc định. Spring Security sử dụng prefix này khi gọi `hasRole` (trừ khi ứng dụng có cấu hình prefix khác). Vì vậy, cần thống nhất tên quyền được tạo và tên quyền mà chính sách kiểm tra.

### 2.1. Đăng nhập thành công không đồng nghĩa được cấp mọi quyền

Một user có thể bind thành công, nhưng **không nằm trong bất kỳ nhóm được phép nào**. Khi đó `Authentication` vẫn có thể xác thực danh tính, còn một endpoint yêu cầu `hasRole("ADMINS")` phải từ chối.

Không dùng một role “mặc định” có quyền cao chỉ để tránh tình trạng tài khoản không có nhóm. Nguyên tắc là **deny by default** cho tài nguyên nhạy cảm.

### 2.2. Spring Data LDAP repository có thay thế authorities populator không?

Không. Repository giúp đọc/ghi LDAP entity như `Person` hoặc `Group`; nó **không tự biến kết quả truy vấn nhóm thành authorities của Spring Security**. Có thể tự xây `LdapAuthoritiesPopulator` bằng repository/template nếu schema khác chuẩn, nhưng cần nối logic đó vào **authentication provider** và xác định cách kiểm tra quyền.

## 3. Schema nhóm quyết định filter cần viết

LDAP server có nhiều cách biểu diễn group membership. Không có **một filter duy nhất** áp dụng được cho mọi directory.

| Kiểu nhóm | Attribute thành viên | Giá trị lưu trong nhóm | Filter điển hình |
| --- | --- | --- | --- |
| `groupOfNames` | `member` | Full DN người dùng hoặc nhóm | `(&(objectClass=groupOfNames)(member={0}))` |
| `groupOfUniqueNames` | `uniqueMember` | DN, có thể kèm thành phần unique identifier theo schema | `(&(objectClass=groupOfUniqueNames)(uniqueMember={0}))` |
| `posixGroup` | `memberUid` | **Username** (không phải full DN) | `(&(objectClass=posixGroup)(memberUid={1}))` |
| Active Directory `group` | `member` | DN của user/group | `(&(objectClass=group)(member={0}))`, tùy triển khai |
| AD/user `memberOf` | Thuộc tính trên user do server duy trì | DN nhóm | Có thể dùng cơ chế riêng; không phổ quát |

### 3.1. `groupOfNames`: member là DN

Với Lan, group `developers` có:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
```

Filter `(member={0})` phải thay `{0}` bằng **full DN** `uid=lan,ou=people,dc=example,dc=org`, không phải chỉ `lan` hoặc `uid=lan`. Server dùng **matching rule của attribute DN** theo schema, không phải phép so sánh String thông thường trong Java.

Schema `groupOfNames` yêu cầu ít nhất một giá trị `member`; không tự tạo một nhóm rỗng bằng cách bỏ hết members nếu directory thực thi schema chuẩn. Muốn hỗ trợ nhóm không có thành viên, phải dùng mô hình/schema được server cho phép.

### 3.2. `groupOfUniqueNames`: uniqueMember có quy tắc riêng

`groupOfUniqueNames` dùng `uniqueMember` thay `member`. Nhiều mô hình thực tế chỉ lưu full DN, nhưng syntax cho phép biểu diễn DN kèm unique identifier tùy cấu hình. Cần kiểm tra schema và dữ liệu thật, không đơn giản đổi tên filter rồi mặc định giống hoàn toàn `member`.

### 3.3. `posixGroup`: memberUid là username

Ví dụ:

```ldif
dn: cn=linux-operators,ou=groups,dc=example,dc=org
objectClass: posixGroup
cn: linux-operators
gidNumber: 2050
memberUid: lan
```

Ở đây filter phù hợp là `(memberUid={1})`, bởi giá trị `memberUid` là `lan`, không phải DN của Lan. Đối với POSIX group, cần kiểm tra quy tắc `gidNumber`/primary group: membership được biểu diễn bằng thuộc tính chính trên user có thể **không được liệt kê trong `memberUid`**. Nếu ứng dụng coi primary group là quyền, phải bổ sung logic kiểm tra riêng, không suy ra tất cả từ một filter.

### 3.4. Đặc thù Active Directory

Microsoft Active Directory có các thuộc tính như `member` và `memberOf`, cũng như cơ chế đặc thù để tính group membership và nested groups. `memberOf` có thể không bao quát **primary group**; một số nhóm có thể được lồng nhiều cấp và việc tính quyền phụ thuộc loại/scope nhóm.

Không lấy một ví dụ OpenLDAP rồi mặc định `memberOf` được duy trì và đọc được trên mọi directory. Với AD, chọn cách truy vấn phù hợp với **domain, schema, global catalog, quyền đọc, nhóm lồng nhau và chính sách của tổ chức**.

## 4. Cấu hình `DefaultLdapAuthoritiesPopulator`

Đối với `groupOfNames` ở ví dụ, Spring Security có sẵn class:

```java
org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator
```

Hợp đồng `LdapAuthoritiesPopulator`:

```java
Collection<? extends GrantedAuthority> getGrantedAuthorities(
        DirContextOperations userData,
        String username);
```

Spring Security gọi interface này **sau khi người dùng đã được xác thực** và có thông tin entry. Populator tìm nhóm bằng DN và/hoặc username rồi biến các tên role thành authorities.

### 4.1. Các thuộc tính quan trọng

| Cấu hình | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `groupSearchBase` | `ou=groups` | DN gốc để tìm nhóm, **tương đối với base của ContextSource** |
| `groupSearchFilter` | `(&(objectClass=groupOfNames)(member={0}))` | Chọn những nhóm có DN người dùng trong `member` |
| `groupRoleAttribute` | `cn` | Tên attribute của group entry được chuyển thành role |
| `rolePrefix` | `ROLE_` | Prefix thêm vào role name |
| `convertToUpperCase` | `true` | Chuẩn hóa `developers` thành `DEVELOPERS` |
| `searchSubtree` | `false` | Tìm group entry **con trực tiếp** dưới `ou=groups` |
| `defaultRole` | Không khai báo | Nếu có, thêm một role mặc định cho mọi user; tránh dùng quyền cao |

Với `groupSearchBase = "ou=groups"`, base của `ContextSource` là `dc=example,dc=org`, search bắt đầu dưới `ou=groups,dc=example,dc=org`. Mặc định `searchSubtree=false`; nếu các nhóm nằm dưới `ou=engineering,ou=groups`, cần cân nhắc bật `true`.

### 4.2. Hai placeholder trong filter

**`{0}` = full DN** người dùng được xác thực.

**`{1}` = username** do ứng dụng dùng trong quá trình đăng nhập.

Ví dụ:

```text
username = lan
full DN  = uid=lan,ou=people,dc=example,dc=org

groupOfNames:
(&(objectClass=groupOfNames)(member={0}))

posixGroup:
(&(objectClass=posixGroup)(memberUid={1}))
```

Không viết `(member={1})` cho entry chứa DN nếu `{1}` chỉ là `lan`; kết quả tra cứu nhóm sẽ sai hoặc rỗng. Cũng không nối chuỗi filter từ input của user: Spring Security dùng filter parameter substitution của thư viện; khi xây filter riêng bằng `LdapTemplate`, phải dùng builder/escaping theo RFC 4515.

### 4.3. Java Config cho Spring Security LDAP

Ví dụ dưới đây giả định project dùng Spring Security hiện đại (dòng 6.x/7.x có API tương ứng), cấu hình `BaseLdapPathContextSource` của Spring Boot hoặc bean tùy chỉnh đã tồn tại, và base DN là `dc=example,dc=org`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator;

@Configuration(proxyBeanMethods = false)
public class LdapAuthorityConfiguration {

    @Bean
    LdapAuthoritiesPopulator ldapAuthorities(
            BaseLdapPathContextSource contextSource) {

        DefaultLdapAuthoritiesPopulator populator =
                new DefaultLdapAuthoritiesPopulator(
                        contextSource, "ou=groups");
        populator.setGroupSearchFilter(
                "(&(objectClass=groupOfNames)(member={0}))");
        populator.setGroupRoleAttribute("cn");
        populator.setRolePrefix("ROLE_");
        populator.setConvertToUpperCase(true);
        populator.setSearchSubtree(false);
        return populator;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource,
            LdapAuthoritiesPopulator authorities) {

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        // Chỉ phù hợp nếu người dùng ở trực tiếp dưới ou=people.
        factory.setUserDnPatterns("uid={0},ou=people");
        factory.setLdapAuthoritiesPopulator(authorities);
        return factory.createAuthenticationManager();
    }
}
```

Ý nghĩa luồng:

1. Spring Security nhận `username/password`.
2. `LdapBindAuthenticationManagerFactory` cấu hình cơ chế xác thực bằng LDAP bind với DN theo pattern (trong cấu hình ví dụ).
3. Sau khi xác thực thành công, `DefaultLdapAuthoritiesPopulator` tìm group entry phù hợp trong `ou=groups`.
4. Tên `cn` của mỗi nhóm khớp được thêm prefix và chuẩn hóa chữ hoa.
5. `Authentication.getAuthorities()` chứa các `GrantedAuthority` được tạo ra.

**Không được suy ra** rằng `ContextSource` của Spring Data LDAP repository tự động thiết lập Spring Security LDAP authentication: hai framework dùng chung Spring LDAP nhưng có **vai trò và cách cấu hình khác nhau**. Xác minh bean `AuthenticationManager` thực sự được ứng dụng sử dụng.

### 4.4. Cấu hình kết nối ở Spring Boot

Một cấu hình tham khảo cho directory có base ở `dc=example,dc=org`:

```yaml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: uid=directory-reader,ou=services,dc=example,dc=org
    password: ${LDAP_READER_PASSWORD}
```

`LDAP_READER_PASSWORD` là biến môi trường/secret ngoài source code. Tài khoản đọc cần quyền tìm user/group và các thuộc tính cần thiết; tài khoản xác thực của người dùng được bind riêng theo luồng Spring Security. **LDAPS hoặc StartTLS phải xác minh chứng chỉ và hostname**, không tắt TLS verification để “chạy được ví dụ”.

Cần thêm dependency `spring-security-ldap` bên cạnh Spring LDAP/Data LDAP và cấu hình security web phù hợp phiên bản. Ví dụ có thể thay đổi khi nâng phiên bản Spring Boot/Spring Security; kiểm tra chính xác API và dependency management của dự án.

## 5. Ánh xạ authority sang quy tắc phân quyền HTTP

Sau khi ánh xạ `cn=developers` thành `ROLE_DEVELOPERS`, ta có thể cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {

        http.authenticationManager(ldapAuthenticationManager);
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMINS")
                .requestMatchers("/dev/**").hasRole("DEVELOPERS")
                .anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là ví dụ **form login** để minh họa authorization, không tự động phù hợp với API stateless. Với REST API dùng session hoặc HTTP Basic/bearer token, chính sách xác thực, CSRF và session cần thiết kế riêng; không vô hiệu hóa CSRF tùy tiện.

### 5.1. `hasRole` so với `hasAuthority`

| Authority trong Authentication | Kiểm tra | Kết quả |
| --- | --- | --- |
| `ROLE_DEVELOPERS` | `hasRole("DEVELOPERS")` | Cho phép |
| `ROLE_DEVELOPERS` | `hasAuthority("ROLE_DEVELOPERS")` | Cho phép |
| `ROLE_DEVELOPERS` | `hasAuthority("DEVELOPERS")` | Không khớp |
| `ROLE_ADMINS` | `hasRole("ADMINS")` | Cho phép |
| `ROLE_DEVELOPERS` | `hasRole("ADMINS")` | Không khớp |

Theo quy ước mặc định, `hasRole("ADMINS")` kiểm tra `ROLE_ADMINS`. Không truyền `ROLE_ADMINS` vào `hasRole(...)` nếu đang dùng cấu hình mặc định, vì phương thức nhận tên **role chưa có prefix**. Nếu dùng `hasAuthority("ROLE_ADMINS")`, truyền đầy đủ chuỗi authority.

Một số hệ thống định nghĩa `GrantedAuthorityDefaults` để đổi role prefix. Khi đó phải xem toàn bộ cấu hình và policy; **không trộn hai quy ước** trong cùng ứng dụng mà không có kế hoạch tương thích.

### 5.2. Authority không phải là tên group nguyên văn trong policy

`cn=admins` ở LDAP không đồng nghĩa mọi ứng dụng phải cấp quyền quản trị chỉ vì chuỗi chứa chữ `admins`. Việc ánh xạ group name sang authority là một **ranh giới tin cậy**: chỉ những group nằm trong cây và chính sách đã phê duyệt mới được dùng để cấp quyền.

Nếu directory cho phép người dùng bình thường **tự tạo hoặc đổi tên group** dưới search base, ứng dụng có thể vô tình cấp quyền cao dựa trên `cn` do người dùng kiểm soát. Cần bảo vệ ACL tại `ou=groups`, xác định nhóm được quản trị bởi ai và cân nhắc mapping theo **allowlist định danh group** thay vì tin bất kỳ tên nào.

## 6. GrantedAuthoritiesMapper: chuẩn hóa sau khi tải nhóm

`LdapAuthoritiesPopulator` **tra cứu và tạo** authorities từ LDAP; `GrantedAuthoritiesMapper` **chuyển đổi tập authority đã được tạo** trước khi gắn vào `Authentication`.

Spring Security có `SimpleAuthorityMapper` để chuyển chữ hoa/thường, thêm prefix, và loại trùng sau chuẩn hóa:

```java
import org.springframework.security.core.authority.mapping.SimpleAuthorityMapper;

SimpleAuthorityMapper mapper = new SimpleAuthorityMapper();
mapper.setConvertToUpperCase(true);
mapper.setPrefix("ROLE_");

// Có thể gắn mapper vào authentication factory:
factory.setAuthoritiesMapper(mapper);
```

Đoạn code ở trên minh họa **bên trong phương thức cấu hình factory**, nơi biến `factory` đã được khai báo. Khi áp dụng, chọn **một tầng chuẩn hóa chính**: nếu `DefaultLdapAuthoritiesPopulator` đã thêm `ROLE_` và chuyển hoa, việc lặp lại trong `SimpleAuthorityMapper` thường không cần thiết. Dùng post-processing chủ yếu khi có nhiều nguồn authority hoặc cần quy tắc bổ sung.

### 6.1. Ánh xạ bằng allowlist thay vì tin toàn bộ tên nhóm

Đối với ứng dụng có ít role chính thức, có thể chỉ chấp nhận một danh sách authority cho phép:

```java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;

GrantedAuthoritiesMapper allowedRoles = source -> {
    Set<String> allowed = Set.of("ROLE_DEVELOPERS", "ROLE_ADMINS");

    return source.stream()
            .map(GrantedAuthority::getAuthority)
            .filter(allowed::contains)
            .map(name -> (GrantedAuthority) new SimpleGrantedAuthority(name))
            .collect(Collectors.toSet());
};

factory.setAuthoritiesMapper(allowedRoles);
```

Khi có thêm role hợp lệ, cấu hình allowlist phải được cập nhật có kiểm soát. Ví dụ này chặn các authority không nằm trong danh sách; **nó không chứng minh** group `admins` là đáng tin nếu một user không được phép có thể tự sửa membership của group đó. Phải kết hợp **ACL phía LDAP** với chính sách ánh xạ phía ứng dụng.

Nếu cần map tên nhóm tổ chức như `cn=backend-team` thành một quyền nghiệp vụ riêng như `project:read`, nên có một bảng mapping **tường minh** thay vì ghép prefix theo mọi tên nhóm. Điều này giúp tránh việc thay đổi tên group vô tình làm thay đổi quyền.

### 6.2. Dùng `setDefaultRole` rất thận trọng

`DefaultLdapAuthoritiesPopulator` có `setDefaultRole(...)` để gán role cho tất cả user mà nó xử lý. Đây không phải cách chữa lỗi search group: nếu filter/base sai, thêm `ROLE_ADMINS` mặc định là **lỗi phân quyền nghiêm trọng**.

Chỉ dùng default role nếu sản phẩm thật sự quy định mọi user **đã xác thực** được phép thực hiện một tập thao tác tối thiểu, và role đó không có đặc quyền cao. Ưu tiên kiểm tra `authenticated()` khi chỉ muốn yêu cầu người dùng đăng nhập.

## 7. Nhóm trực tiếp và nhóm lồng nhau

Giả sử:

```text
uid=lan
   │ member của
   ▼
cn=developers
   │ member của
   ▼
cn=engineering
   │ member của
   ▼
cn=all-staff
```

Với `groupOfNames`, entry `engineering` có thể chứa:

```ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: groupOfNames
cn: engineering
member: cn=developers,ou=groups,dc=example,dc=org
```

Khi filter tìm **nhóm chứa DN người dùng trực tiếp**:

```ldap
(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))
```

nó sẽ khớp `developers`, nhưng **không tự khớp `engineering`** nếu `engineering` chỉ chứa DN của group `developers`. Search scope `SUBTREE` của LDAP chỉ mở rộng **vùng tìm entry trong cây**, **không** có nghĩa tự đi theo chuỗi membership lồng nhau.

### 7.1. Khi cần quyền từ nested groups

Spring Security LDAP có **`NestedLdapAuthoritiesPopulator`** có khả năng tìm các nhóm tĩnh được lồng nhau theo cách đệ quy. Khi chọn cơ chế này cần kiểm tra:

- Schema có biểu diễn **group là member của group** không?
- Directory có giới hạn độ sâu, vòng lặp hoặc dữ liệu membership hỏng không?
- Hệ thống có nhóm lớn/nhiều cấp làm truy vấn phát sinh nhiều lần không?
- Có policy chỉ chấp nhận một số loại nhóm hoặc nhánh nhất định không?
- Có kiểm thử đúng việc cấp quyền gián tiếp và trường hợp không được cấp không?

Một số sản phẩm LDAP, đặc biệt AD, có extension riêng cho tìm membership đệ quy. Đây là **tính năng vendor**, không phải filter LDAP chuẩn dùng chung mọi server. Không tự thay `DefaultLdapAuthoritiesPopulator` bằng một tìm kiếm đệ quy chưa được kiểm soát vì có thể tạo quyền rộng hơn mong muốn.

### 7.2. Tránh vòng lặp

Nếu group A chứa group B, group B lại chứa group A, truy vấn đệ quy tùy chỉnh phải có:

- Tập DN đã thăm (visited set).
- Giới hạn độ sâu và số entry tối đa.
- Kiểm soát timeout.
- Phương án khi gặp referral/partial result.
- Kết quả **không cấp thêm role tùy ý** khi không thể xác nhận membership.

Khi dùng implementation có sẵn, vẫn phải xác minh hành vi trên directory thật; đừng coi recursion là bằng chứng đủ để cấp quyền.

## 8. Kiểm chứng filter trước khi cấu hình phân quyền

Trong môi trường thử nghiệm, có thể đối chiếu group search bằng `ldapsearch`:

```bash
ldapsearch -x \
  -H "ldaps://directory.example.org:636" \
  -D "uid=directory-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s one \
  "(&(objectClass=groupOfNames)(member=uid=lan,ou=people,dc=example,dc=org))" \
  dn cn member
```

Lệnh này là ví dụ cho **directory test có quyền đọc phù hợp**. `-W` hỏi mật khẩu tương tác thay vì đặt password trực tiếp trong command line. Với môi trường dùng SASL/LDAPS hoặc chính sách bảo mật khác, chọn phương thức bind hợp lệ.

Kết quả mong đợi: entry `cn=developers,ou=groups,...`. Nếu không có kết quả, cần kiểm tra:

1. Entry nhóm có tồn tại ở đúng OU không?
2. `objectClass` của group có phải `groupOfNames` không?
3. `member` có chứa **DN đầy đủ** người dùng đúng tên hiện tại không?
4. Principal đọc có quyền nhìn thấy `member` và `cn` không?
5. Search scope `ONELEVEL` có bỏ sót nhóm trong OU con không?
6. Query có trỏ đúng directory/naming context không?

Đừng tự thêm một role vào code để “bù” cho truy vấn group sai: phải sửa cấu hình hoặc dữ liệu ở đúng tầng.

### 8.1. Truy vấn chẩn đoán bằng `LdapTemplate`

Nếu cần kiểm tra kết quả nhóm riêng (không phải thay luôn cấu hình Spring Security), có thể dùng:

```java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

public List<String> groupNamesForDn(
        LdapTemplate ldapTemplate, String fullUserDn) {
    LdapQuery query = LdapQueryBuilder.query()
            .base("ou=groups")
            .searchScope(SearchScope.ONELEVEL)
            .attributes("cn")
            .where("objectClass").is("groupOfNames")
            .and("member").is(fullUserDn);

    return ldapTemplate.search(query,
            (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get());
}
```

`.is(fullUserDn)` xây equality filter và escape các ký tự cần thiết theo cú pháp filter. **DN có quy tắc escape riêng khi tạo**, khác escaping trong filter; ở đây full DN được dùng như **giá trị thuộc tính `member`**.

Mẫu code minh họa đường chẩn đoán; trong ứng dụng thật, cần kiểm tra `cn` thiếu/đa trị, giới hạn kết quả và tránh công khai membership qua API không có authorization.

## 9. Hiệu năng của tra cứu nhóm và ảnh hưởng tới đăng nhập

Vì group lookup có thể thực hiện mỗi lần người dùng xác thực, filter kém chọn lọc hoặc search base rộng có thể làm tăng đáng kể thời gian đăng nhập.

| Vấn đề | Cách xem xét |
| --- | --- |
| Quét toàn bộ directory để tìm nhóm | Dùng `groupSearchBase` hẹp, ví dụ `ou=groups` |
| Search scope `SUBTREE` trên cây nhóm lớn | Chỉ bật nếu group thực sự ở OU con |
| Filter không phù hợp schema | Chọn `member`, `uniqueMember` hoặc `memberUid` chính xác |
| Tra cứu `member={0}` chậm | Xem xét equality index của attribute `member` ở server (tùy backend) |
| Nested group nhiều cấp | Đo số truy vấn, chiều sâu, kích thước tập group và các vòng lặp |
| Group search trả nhiều attributes | Chỉ yêu cầu những thuộc tính cần ánh xạ, nếu API/cấu hình cho phép |
| Kết nối LDAP thường xuyên bị mở mới | Xem xét pool/context hợp lệ nhưng không dùng chung trạng thái bind người dùng |

**Pool không khắc phục filter sai**; index không giải quyết việc gán nhầm role. Hãy đo cả tính **đúng** của tập authority và độ trễ p50/p95/p99 trên directory test có dữ liệu gần thực tế.

### 9.1. Tránh pooling context của người dùng khác nhau

Spring LDAP và Spring Security có thể sử dụng service account để tìm nhóm, trong khi **bind authentication** dùng credential của từng người dùng. Nếu một pool context thông thường được gắn vào `AuthenticationSource` thay đổi principal theo request, có nguy cơ tái sử dụng context với danh tính không phù hợp. Không tùy tiện pool context xác thực động; dùng cấu hình được Spring Security hỗ trợ và tách đường đọc nhóm bằng service account ổn định khi cần.

## 10. An toàn: đừng để tên nhóm trở thành lỗ hổng cấp quyền

### 10.1. Kiểm soát ACL và nguồn sự thật

Nếu người dùng có thể tạo group `cn=admins` hoặc tự thêm DN của mình vào `member` dưới một OU mà ứng dụng search, việc ánh xạ thẳng `cn=admins` thành `ROLE_ADMINS` sẽ cấp quyền ngoài ý muốn.

Giảm thiểu rủi ro:

- **Chặn user tự sửa** các group cấp quyền ở LDAP; chỉ cấp quyền cho quy trình quản trị được phê duyệt.
- **Giới hạn groupSearchBase** vào nhánh chứa các nhóm đáng tin cậy.
- Xác minh **objectClass** và attribute role trước khi ánh xạ.
- Có thể dùng mapping **allowlist** từ group DN cụ thể sang permission ứng dụng thay vì coi mọi tên nhóm là role.
- Không tin một giá trị `memberOf` do client gửi lên hoặc thuộc tính do người dùng tự sửa.
- Không cấp `ROLE_ADMINS` mặc định và không tự hợp thức hóa một group search thất bại bằng role đặc quyền.

### 10.2. Fail closed khi directory không sẵn sàng

Đừng đánh đồng:

| Tình huống | Cách hiểu |
| --- | --- |
| Authenticated, group search trả danh sách rỗng | Có thể không có group khớp, hoặc query/ACL sai; không đủ quyền cho endpoint yêu cầu role |
| Group search ném lỗi kết nối/timeout | Không thể xác minh quyền; không nên cấp quyền đặc quyền dựa trên dữ liệu thiếu |
| User bind thất bại | Authentication thất bại, không đến bước cấp quyền |
| Group membership thay đổi sau khi login | Authority trong session/token có thể chưa được cập nhật |

Cấu hình ứng dụng cần xử lý lỗi truy vấn theo hướng **không cấp thêm quyền khi không thể xác minh**. Có thể chặn đăng nhập hoặc chặn endpoint phụ thuộc role, tùy chính sách. Đừng tự bỏ qua exception tra cứu nhóm rồi giữ các quyền nguy hiểm từ lần đăng nhập trước.

### 10.3. Bảo vệ filter và dữ liệu trong log

Đừng ghi password, raw LDAP filter chứa định danh cá nhân, danh sách membership nhạy cảm hoặc toàn bộ DN vào log/tracing tags khi không có chính sách cho phép. Ghi loại thao tác, nhóm lỗi, thời gian xử lý và correlation ID được quản lý thay thế. Dùng LDAPS/StartTLS với xác thực máy chủ và phân quyền tối thiểu cho tài khoản đọc nhóm.

## 11. Thay đổi nhóm có hiệu lực khi nào?

Khi Spring Security xác thực người dùng và nạp authorities, danh sách đó thường được giữ trong đối tượng `Authentication`. Trong ứng dụng stateful, nó có thể nằm trong **session/SecurityContext**. Với token như JWT, role được nhúng trong token có thể tồn tại tới khi token hết hạn hoặc bị thu hồi theo thiết kế.

Ví dụ:

```text
09:00: Lan login, thuộc group developers
       → Authentication authorities = [ROLE_DEVELOPERS]

09:10: Admin xóa Lan khỏi member của developers ở LDAP

09:11: Lan vẫn giữ session hoặc token cũ
       → Chưa chắc quyền đã mất ngay nếu không reload/revoke
```

Do đó cần xác định chính sách **freshness**:

- Tải lại authorities mỗi lần login, mỗi request hay theo TTL/cache?
- Khi thu hồi quyền, có cơ chế vô hiệu session/token hay sự kiện đồng bộ không?
- Cache membership tồn tại bao lâu, ai có thể invalidate?
- Khi directory replication bị trễ, các instance ứng dụng có thể nhìn thấy role khác nhau không?

**Không mặc định “xóa membership ở LDAP là mọi request ngay lập tức mất quyền”**. Đây là quyết định kiến trúc xác thực, session/token và thời gian đồng bộ.

### 11.1. Khi user DN đổi do Modify DN

Nếu người dùng chuyển từ `ou=people` sang `ou=staff` và group chứa DN cũ:

```text
member: uid=lan,ou=people,dc=example,dc=org
```

thì filter `(member={0})` với **DN mới** có thể không còn tìm thấy group. Một số directory có plugin tự cập nhật DN tham chiếu, nhưng không được giả định là mặc định. Kiểm tra rename/move, group membership và nơi repository/authenticator tìm user; cấu hình `userDnPatterns("uid={0},ou=people")` cũng cần thay đổi nếu user đã rời OU đó.

## 12. Kiểm thử từ nhóm LDAP đến quyền Spring Security

### 12.1. Bộ dữ liệu test

Chuẩn bị một directory test hoặc LDAP server nhúng với:

| User | DN | Membership | Kết quả dự kiến |
| --- | --- | --- | --- |
| Lan | `uid=lan,ou=people,...` | `developers` | `ROLE_DEVELOPERS` |
| Minh | `uid=minh,ou=people,...` | `admins` | `ROLE_ADMINS` |
| Mai | `uid=mai,ou=people,...` | Không thuộc nhóm được search | Không có role từ group lookup |

Với schema `groupOfNames`, dùng nhóm chứa ít nhất một member hợp lệ. Thiết lập password test qua cơ chế của directory nhúng hoặc bootstrap an toàn; không sử dụng tài khoản thật.

### 12.2. Unit test cho ánh xạ quyền

Có thể kiểm thử hậu xử lý authority độc lập với LDAP server:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.SimpleAuthorityMapper;

SimpleAuthorityMapper mapper = new SimpleAuthorityMapper();
mapper.setPrefix("ROLE_");
mapper.setConvertToUpperCase(true);

Set<String> result = mapper.mapAuthorities(List.of(
        new SimpleGrantedAuthority("developers"),
        new SimpleGrantedAuthority("admins")))
        .stream()
        .map(authority -> authority.getAuthority())
        .collect(Collectors.toSet());

if (!result.equals(Set.of("ROLE_DEVELOPERS", "ROLE_ADMINS"))) {
    throw new AssertionError("Unexpected authorities: " + result);
}
```

Đây là unit test **cách chuẩn hóa chuỗi authority**, không chứng minh group search đúng. Phải có **integration test** để kiểm chứng LDAP `member`/`cn` và authentication flow.

### 12.3. Integration test cho AuthenticationManager

Giả sử có bean `AuthenticationManager` đã cấu hình và test credentials được cấp từ nguồn an toàn:

```java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

Authentication authenticated = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "lan", testPassword));

Set<String> authorities = authenticated.getAuthorities().stream()
        .map(a -> a.getAuthority())
        .collect(Collectors.toSet());

if (!authenticated.isAuthenticated()
        || !authorities.contains("ROLE_DEVELOPERS")
        || authorities.contains("ROLE_ADMINS")) {
    throw new AssertionError("LDAP authority mapping is incorrect");
}
```

Kỳ vọng Lan đăng nhập đúng sẽ có `ROLE_DEVELOPERS`, **không có `ROLE_ADMINS`**. Test này cần LDAP server test, user bind thành công và quyền đọc group cho populator.

### 12.4. Test endpoint và trường hợp âm tính

Với rule:

```java
.requestMatchers("/dev/**").hasRole("DEVELOPERS")
.requestMatchers("/admin/**").hasRole("ADMINS")
```

Hãy kiểm tra:

1. Lan đăng nhập đúng → truy cập `/dev/reports` được phép; `/admin/users` bị từ chối.
2. Minh đăng nhập đúng → `/admin/users` được phép theo rule ví dụ.
3. Mai đăng nhập đúng nhưng không có group phù hợp → hai endpoint trên bị từ chối.
4. Password sai → authentication thất bại, **không có bước cấp role thành công**.
5. Sửa `groupSearchFilter` sang attribute sai → Lan mất quyền; test phát hiện lỗi cấu hình.
6. Đặt groups dưới OU con → `searchSubtree=false` bỏ sót; `true` chỉ dùng khi chính sách cho phép quét subtree.
7. Group name viết khác chữ hoa/thường → kiểm tra `convertToUpperCase` và policy.
8. Ngắt LDAP server khi đọc group → xác minh hệ thống **không tự cấp quyền đặc quyền**.
9. Xóa membership sau khi login → kiểm tra chính sách làm mới session/token.
10. Đổi DN của user nhưng không cập nhật `member` → kiểm tra membership và khả năng login/search.
11. Dùng principal đọc group thiếu quyền ACL → test không coi “không đọc thấy” là “không tồn tại” một cách thiếu chẩn đoán.
12. Thử nested group → kiểm tra role trực tiếp và gián tiếp theo chiến lược đã chọn.

Không nên chỉ mock Spring Security bằng `@WithMockUser(roles = "ADMINS")` rồi kết luận LDAP group mapping đúng: mock đó **bỏ qua LDAP**, chỉ xác minh lớp kiểm tra authorization. Cần cả integration test với directory thực/nhúng.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login thành công nhưng không có role | Group search sai base/scope/filter hoặc ACL che giấu | Kiểm tra `groupSearchBase`, `member`, returned attributes |
| Nhóm dùng `memberUid` nhưng filter `member={0}` | Dùng schema POSIX với filter DN | Đổi sang `memberUid={1}` khi phù hợp |
| Nhóm `groupOfUniqueNames` không được tìm thấy | Dùng `member` thay `uniqueMember` | Kiểm tra objectClass và filter |
| `hasRole("DEVELOPERS")` luôn từ chối | Authority thực là `DEVELOPERS`, `ROLE_DEVELOPER` hoặc khác case | In/kiểm tra tên authority trong test được kiểm soát |
| Bị thêm prefix sai | Chạy nhiều mapper với quy tắc không nhất quán | Đồng bộ prefix/uppercase một tầng |
| User ở OU con không được xác thực | `userDnPatterns` chỉ áp dụng OU trực tiếp | Dùng user search theo cấu trúc thực tế |
| Group ở OU con không được xét | `searchSubtree=false` | Cân nhắc subtree search nếu được phép |
| Nested group không mang lại quyền | Populator mặc định chỉ tìm member trực tiếp | Dùng cơ chế nested group được hỗ trợ và kiểm thử |
| AD primary group bị bỏ sót | Phụ thuộc `memberOf`/`member` thông thường | Xác minh mô hình AD và xử lý primary group |
| Group search rất chậm | Search base rộng, filter/index không phù hợp | Đo server query, thu hẹp vùng và kiểm tra index |
| User tự có quyền ADMIN sau khi tạo group | Tên group dưới nhánh search do user sửa được | Sửa ACL/group trust policy và allowlist |
| Thu hồi membership nhưng session vẫn có quyền | Authority được cache lúc login hoặc trong JWT | Thiết kế refresh/revoke/TTL |
| Đổi DN làm mất group | `member` còn trỏ DN cũ | Kiểm tra Modify DN và chính sách cập nhật tham chiếu |
| Directory lỗi nhưng app vẫn cấp role | Có fallback/default role quá mạnh | Fail closed, theo dõi lỗi group lookup |

## 14. Câu hỏi tự luyện

**Câu 1.** User Lan có DN `uid=lan,ou=people,dc=example,dc=org`, group `developers` dùng `member` lưu DN. Filter nào nên dùng và `{0}` được thay bằng gì?

*Đáp án gợi ý:* `(member={0})` hoặc filter kết hợp `objectClass=groupOfNames`; `{0}` là **full DN**, không phải username.

**Câu 2.** Group POSIX dùng `memberUid: lan`. Nên dùng placeholder nào?

*Đáp án gợi ý:* `{1}` đại diện username, nên filter là `(memberUid={1})` nếu phù hợp schema/group policy.

**Câu 3.** Directory trả group `cn=developers`. Với `rolePrefix=ROLE_` và `convertToUpperCase=true`, authority mặc định sẽ là gì?

*Đáp án gợi ý:* `ROLE_DEVELOPERS`. `hasRole("DEVELOPERS")` sẽ khớp theo prefix mặc định.

**Câu 4.** User có `ROLE_DEVELOPERS` nhưng không có `ROLE_ADMINS`. `hasAuthority("ROLE_ADMINS")` có cho phép không?

*Đáp án gợi ý:* Không. Xác thực danh tính không có nghĩa sở hữu mọi quyền.

**Câu 5.** `cn=engineering` chứa group `cn=developers`, còn Lan chỉ nằm trong developers. Vì sao filter `member={0}` không trả engineering?

*Đáp án gợi ý:* Filter tìm membership **trực tiếp**; engineering chứa DN nhóm chứ không chứa DN người dùng. Cần nested group strategy nếu yêu cầu.

**Câu 6.** Tại sao đổi `searchSubtree=false` sang `true` không đồng nghĩa hỗ trợ nested groups?

*Đáp án gợi ý:* Subtree chỉ mở rộng **vị trí tìm group entry trong DIT**, không tự đi đệ quy theo thuộc tính membership.

**Câu 7.** Nếu user có thể tự sửa `member` của group `admins`, rủi ro là gì?

*Đáp án gợi ý:* User có thể tự thêm DN vào group được ánh xạ thành `ROLE_ADMINS`. Cần ACL, allowlist và quy trình cấp quyền được kiểm soát.

**Câu 8.** Admin xóa Lan khỏi developers nhưng Lan đang có session/JWT cũ. Quyền có bị thu hồi tức thì không?

*Đáp án gợi ý:* Không bảo đảm. Cần quy tắc refresh authorities, hết hạn/revoke session/token và xử lý đồng bộ từ LDAP.

## 15. Ghi nhớ

- **Authentication** xác minh người dùng; **LdapAuthoritiesPopulator** tìm nhóm/quyền **sau khi xác thực**; **GrantedAuthority** là dữ liệu mà Spring Security dùng để quyết định truy cập.
- Với `groupOfNames`, `member` chứa **DN** và filter dùng **`{0}`**. Với `posixGroup.memberUid`, giá trị thường là **username** và có thể dùng **`{1}`**.
- `DefaultLdapAuthoritiesPopulator` điều chỉnh được group base/filter, role attribute, prefix, cách chuẩn hóa chữ hoa và search scope. Kiểm tra kết quả thực tế của `Authentication.getAuthorities()`.
- `hasRole("DEVELOPERS")` kiểm tra `ROLE_DEVELOPERS` theo quy ước mặc định; `hasAuthority("ROLE_DEVELOPERS")` kiểm tra chính xác toàn bộ chuỗi.
- **Subtree search không phải nested group traversal**. Nhóm lồng nhau cần chiến lược rõ ràng và kiểm thử bảo mật.
- **ACL của directory + group allowlist + fail closed** là nền tảng chống tự cấp quyền. Không dùng fallback đặc quyền khi group lookup thất bại.
- Khi đổi membership hoặc DN, **authority trong session/token có thể đã cũ**; cần chính sách làm mới và thu hồi quyền phù hợp.

**Tài liệu tham khảo:**

- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): bind authentication, `LdapAuthoritiesPopulator` và cấu hình `LdapBindAuthenticationManagerFactory`.
- [Spring Security API — DefaultLdapAuthoritiesPopulator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/DefaultLdapAuthoritiesPopulator.html): `groupSearchBase`, filter `{0}`/`{1}`, role attribute/prefix và search scope.
- [Spring Security API — NestedLdapAuthoritiesPopulator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/userdetails/NestedLdapAuthoritiesPopulator.html): nhóm tĩnh lồng nhau.
- [Spring Security API — AbstractLdapAuthenticationManagerFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/ldap/AbstractLdapAuthenticationManagerFactory.html): cấu hình authority populator và mapper.
- [Spring Security API — SimpleAuthorityMapper](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/SimpleAuthorityMapper.html): chuẩn hóa authority và prefix.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`, `hasAuthority` và quy tắc URL.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và ánh xạ entry LDAP.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511), [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512), [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
