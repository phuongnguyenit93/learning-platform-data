# Kiểm thử xác thực, phân quyền và TLS

## 1. Ba câu hỏi bảo mật cần kiểm thử riêng

Khi một ứng dụng Spring Data LDAP kết nối directory, việc truy vấn thành công chưa chứng minh ứng dụng đã bảo vệ đúng danh tính và dữ liệu. Cần trả lời ba câu hỏi độc lập:

1. **Xác thực (authentication):** LDAP server có xác minh đúng danh tính và credential được gửi không?
2. **Phân quyền (authorization):** Sau khi xác thực, danh tính đó được phép tìm, đọc, so sánh, thêm, sửa hoặc xóa entry/attribute nào?
3. **Bảo mật đường truyền (transport security):** Kết nối có mã hóa, xác minh đúng máy chủ và dùng chứng thư phù hợp không?

Ba lớp này không thay thế nhau:

```text
Client
  |
  | 1. TLS handshake: kiểm tra certificate và hostname
  v
LDAP server
  |
  | 2. Bind: kiểm tra DN + credential
  v
Authenticated identity
  |
  | 3. ACL: kiểm tra quyền trên entry/attribute
  v
Search / Read / Compare / Add / Modify / Delete
```

Ví dụ, user `linh` có thể Bind thành công nhưng chỉ được đọc hồ sơ của mình. Một service account có thể Bind thành công và được đọc `ou=people`, nhưng không được sửa `userPassword`. Một TLS handshake có thể thành công nhưng Bind vẫn thất bại do mật khẩu sai.

Trong module **SPRING_DATA_LDAP**, Spring Data LDAP cung cấp repository và ánh xạ entry; Spring LDAP cung cấp `ContextSource`, `LdapTemplate` và API Bind; Spring Security LDAP có thể dùng Bind authentication và tải authorities từ group. Bài này tập trung vào cách kiểm thử các ranh giới bảo mật đó bằng fixture LDAP cô lập và integration test.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểm thử Bind với kiểm thử quyền đọc/ghi.
2. Tạo fixture gồm user, group và service account cho từng quyền.
3. Kiểm thử credential đúng, sai, user không tồn tại và mật khẩu rỗng.
4. Kiểm thử `LdapTemplate.authenticate` và Spring Security `AuthenticationManager`.
5. Kiểm tra role/authority được ánh xạ từ group membership.
6. Kiểm thử ACL bằng nhiều bind identity độc lập.
7. Phân biệt quyền trên entry với quyền trên từng attribute.
8. Kiểm thử LDAPS và StartTLS, trust chain, hostname, certificate expiry và client certificate.
9. Viết test phân biệt lỗi TLS, lỗi Bind, lỗi ACL và lỗi cấu hình.
10. Chọn đúng loại LDAP server cho embedded test và vendor-specific contract test.

## 2. Authentication khác Authorization như thế nào?

| Khái niệm | Câu hỏi | Ví dụ | Cách kiểm thử |
| --- | --- | --- | --- |
| Authentication | Bạn là ai? | DN `uid=linh,ou=people,...` cùng mật khẩu hợp lệ. | Bind bằng đúng/sai credential. |
| Authorization | Bạn được phép làm gì? | `linh` được đọc entry của mình nhưng không sửa group. | Thử Search/Read/Modify/Delete bằng từng identity. |
| Transport security | Kết nối có an toàn và đúng server không? | TLS certificate có CA tin cậy và SAN khớp hostname. | Handshake thành công/thất bại theo truststore và hostname. |
| Application authority | Ứng dụng gán quyền nghiệp vụ nào? | LDAP group `readers` ánh xạ thành `ROLE_READERS`. | Kiểm thử authorities và HTTP/method access. |

Bind thành công không có nghĩa caller được đọc mọi entry. Ngược lại, một search trả kết quả không chứng minh ứng dụng đã xác thực user theo cách dự kiến: directory có thể cho anonymous read.

Một số LDAP server có thể chấp nhận unauthenticated simple Bind khi DN không rỗng nhưng password rỗng, rồi chuyển session sang anonymous authorization state. Vì vậy, không dùng mật khẩu rỗng để đại diện cho Bind hợp lệ và không coi Bind success là đủ nếu chưa xác nhận password khác rỗng. RFC 4513 yêu cầu client nhận diện tình huống này khi kết quả Bind được dùng cho quyết định xác thực.

## 3. Chọn đúng test environment

Không có một loại LDAP test server nào mô phỏng mọi hành vi bảo mật của mọi directory.

| Môi trường | Dùng để kiểm tra | Không nên mặc định dùng để kết luận |
| --- | --- | --- |
| Embedded UnboundID | Bind cơ bản, user search, group lookup, mapping, repository, LDAPS cơ bản nếu cấu hình certificate. | ACL phức tạp của OpenLDAP/AD, password policy, replication, Kerberos, mọi hành vi vendor. |
| OpenLDAP container | Bind, ACL theo `olcAccess`, quyền entry/attribute, TLS, StartTLS, schema/overlay cụ thể. | Hành vi riêng của Active Directory. |
| Active Directory test domain | UPN/domain bind, group membership, nested groups, linked attributes, channel binding và policy của AD. | Hành vi của OpenLDAP. |
| LDAP staging gần production | Contract test với schema, ACL, TLS, referral, identity thực tế. | Chạy test phá hủy dữ liệu hoặc dùng credential production không được phép. |

Spring Boot hỗ trợ embedded UnboundID từ dependency `com.unboundid:unboundid-ldapsdk`; có thể nạp LDIF và bật LDAPS bằng SSL bundle. Spring LDAP cũng có `spring-ldap-test` với embedded server, nhưng cần kiểm tra tương thích phiên bản server được hỗ trợ.

**Quy tắc:** embedded server dùng để test luồng ứng dụng nhanh; ACL và TLS phụ thuộc vendor phải được xác minh trên đúng loại server, cấu hình và phiên bản triển khai.

## 4. Chuẩn bị fixture test

Tạo naming context `dc=example,dc=org` với:

- Hai user: `linh` và `an`.
- Hai group: `readers` và `writers`.
- Hai service account: `svc-reader` và `svc-writer`.

Ví dụ `src/test/resources/ldap-security.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
userPassword: test-linh-password

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org
userPassword: test-an-password

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: cn=readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: readers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org

dn: cn=writers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: writers
member: uid=an,ou=people,dc=example,dc=org

dn: ou=service,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: service

dn: cn=svc-reader,ou=service,dc=example,dc=org
objectClass: top
objectClass: organizationalRole
objectClass: simpleSecurityObject
cn: svc-reader
userPassword: test-reader-password

dn: cn=svc-writer,ou=service,dc=example,dc=org
objectClass: top
objectClass: organizationalRole
objectClass: simpleSecurityObject
cn: svc-writer
userPassword: test-writer-password
```

Mật khẩu trong LDIF chỉ là credential dùng riêng cho test. Với server có password policy hoặc yêu cầu hash cụ thể, nạp mật khẩu bằng cơ chế quản trị của test server thay vì giả định mọi implementation chấp nhận cùng định dạng `userPassword`.

### 4.1. Dependency cho embedded LDAP

Ví dụ Gradle với Spring Boot dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    implementation("org.springframework.security:spring-security-ldap")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testRuntimeOnly("com.unboundid:unboundid-ldapsdk")
}
```

Chỉ thêm `spring-security-ldap` nếu ứng dụng kiểm thử Spring Security LDAP. Dùng version được BOM của Spring Boot quản lý, tránh tự ghim một version UnboundID hoặc Spring Security không tương thích.

### 4.2. Cấu hình test profile

Ví dụ `src/test/resources/application-test.yml`:

```yaml
spring:
  ldap:
    base: dc=example,dc=org
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap-security.ldif
```

Spring Boot khởi động embedded LDAP trên port ngẫu nhiên nếu không cấu hình port cố định. Khi dùng embedded server, client lấy port, scheme, credential và SSL bundle từ cấu hình `spring.ldap.embedded.*`; các thuộc tính kết nối production như `spring.ldap.urls` hoặc `spring.ldap.username` có thể bị bỏ qua theo quy tắc embedded auto-configuration.

## 5. Kiểm thử Bind bằng Spring LDAP

`LdapTemplate.authenticate(LdapQuery, password)` thực hiện Search để tìm entry cần xác thực, sau đó dùng DN của entry và password để Bind. Query phải xác định duy nhất một entry. Các overload cũ nhận `base` và raw filter vẫn tồn tại; ưu tiên `LdapQuery` để khai báo truy vấn theo cấu trúc.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

@SpringBootTest
class LdapBindAuthenticationIT {

    @Autowired
    private LdapTemplate ldapTemplate;

    private LdapQuery userQuery(String uid) {
        return query()
            .base("ou=people")
            .where("uid").is(uid);
    }

    @Test
    void acceptsCorrectPassword() {
        assertThatCode(() ->
            ldapTemplate.authenticate(
                userQuery("linh"),
                "test-linh-password"
            )
        ).doesNotThrowAnyException();
    }

    @Test
    void rejectsWrongPassword() {
        assertThatThrownBy(() ->
            ldapTemplate.authenticate(
                userQuery("linh"),
                "wrong-password"
            )
        ).isInstanceOf(org.springframework.ldap.AuthenticationException.class);
    }
}
```

Hãy chạy test trên server fixture có hỗ trợ simple Bind. Query dùng base tương đối với base DN của `ContextSource`. API mới trả về `void`: Bind thành công thì method hoàn tất; Bind thất bại thì exception được ném ra.

Nếu service đang dùng `LdapClient`, API fluent tương ứng là:

```java
ldapClient.authenticate()
    .query(userQuery("linh"))
    .password("test-linh-password")
    .execute();
```

Kết quả cũng được thể hiện bằng việc hoàn tất bình thường hoặc ném exception. Khi cần thao tác tiếp trên authenticated context, dùng overload `execute(AuthenticatedLdapEntryContextMapper)`.

### 5.1. Kiểm tra user không tồn tại và filter không duy nhất

Thêm test cho:

- UID không tồn tại.
- UID trùng trong search scope (nếu schema/test server cho phép fixture lỗi).
- Search base sai hoặc caller không có quyền tìm user.

Không gom tất cả các lỗi thành “sai mật khẩu”. User không tồn tại, filter trả nhiều entry và ACL chặn Search là những lỗi khác nhau. Trong ứng dụng, có thể chủ động chuẩn hóa thông báo ra bên ngoài để tránh lộ thông tin tài khoản, nhưng test nội bộ vẫn cần nhận diện nguyên nhân đúng.

### 5.2. Không chấp nhận password rỗng

Không viết test kỳ vọng:

```java
ldapTemplate.authenticate(userQuery("linh"), "");
```

thành công. Một số LDAP server có unauthenticated simple Bind semantics; password rỗng có thể đưa session vào anonymous state. Test phải xác minh ứng dụng từ chối credential rỗng trước khi gửi Bind, và không dùng anonymous read để chứng minh authentication thành công.

### 5.3. Kiểm tra operation trên authenticated context

Một số server hoặc authentication mechanism yêu cầu thực hiện thao tác tiếp theo trên context vừa Bind để xác nhận hành vi thực tế. Spring LDAP có overload `authenticate(LdapQuery, password, AuthenticatedLdapEntryContextMapper<T>)` để chạy mapper trên authenticated context. Dùng API này khi ứng dụng cần đọc entry/attribute dưới quyền của chính user.

Không tự viết một hàm Bind riêng rồi quên đóng context. Nếu dùng trực tiếp `ContextSource.getContext(userDn, password)`, phải đóng context trong `finally`/try-with-resources tương ứng.

## 6. Kiểm thử Spring Security LDAP

Khi cần tích hợp với HTTP authentication, authorities, method security hoặc user context, nên kiểm thử `AuthenticationManager`/`LdapAuthenticationProvider` thay vì chỉ test một lệnh Bind đơn lẻ.

Spring Security LDAP sử dụng `LdapAuthenticator`; với Bind authentication, server nhận credential và tự xác minh mật khẩu. Ứng dụng không cần đọc `userPassword` về để so sánh ở Java.

### 6.1. Cấu hình Bind Authentication

Ví dụ cấu hình `AuthenticationManager` với user DN pattern:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.ldap.authentication.LdapBindAuthenticationManagerFactory;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@Configuration
class LdapAuthenticationConfiguration {

    @Bean
    AuthenticationManager authenticationManager(
            BaseLdapPathContextSource contextSource) {

        LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(contextSource);

        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }
}
```

Nếu user không nằm tại một DN pattern cố định, cấu hình `setUserSearchBase("ou=people")` và `setUserSearchFilter("(uid={0})")` để tìm DN trước khi Bind.

### 6.2. Test đúng mật khẩu, sai mật khẩu và user lạ

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;

@SpringBootTest
class SpringSecurityLdapAuthenticationIT {

    @Autowired
    private AuthenticationManager authenticationManager;

    @Test
    void authenticatesKnownUser() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "linh",
            "test-linh-password"
        );

        var result = authenticationManager.authenticate(request);

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getName()).isEqualTo("linh");
    }

    @Test
    void rejectsWrongPassword() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "linh",
            "wrong-password"
        );

        assertThatThrownBy(() ->
            authenticationManager.authenticate(request)
        ).isInstanceOf(AuthenticationException.class);
    }

    @Test
    void rejectsUnknownUser() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "unknown-user",
            "any-password"
        );

        assertThatThrownBy(() ->
            authenticationManager.authenticate(request)
        ).isInstanceOf(AuthenticationException.class);
    }

    @Test
    void rejectsEmptyPassword() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "linh",
            ""
        );

        assertThatThrownBy(() ->
            authenticationManager.authenticate(request)
        ).isInstanceOf(AuthenticationException.class);
    }
}
```

Spring Security LDAP từ chối password rỗng trong Bind authentication. Đây là test quan trọng để tránh nhầm unauthenticated Bind với authenticated user.

### 6.3. Kiểm thử group membership và authorities

Ví dụ `DefaultLdapAuthoritiesPopulator` tìm group có attribute `member` bằng DN user:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator;
import org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

@Bean
LdapAuthoritiesPopulator authorities(
        BaseLdapPathContextSource contextSource) {

    DefaultLdapAuthoritiesPopulator populator =
        new DefaultLdapAuthoritiesPopulator(
            contextSource,
            "ou=groups"
        );

    populator.setGroupSearchFilter("member={0}");
    populator.setGroupRoleAttribute("cn");
    populator.setRolePrefix("ROLE_");
    return populator;
}
```

Gắn populator vào factory:

```java
@Bean
AuthenticationManager authenticationManager(
        BaseLdapPathContextSource contextSource,
        LdapAuthoritiesPopulator authorities) {

    LdapBindAuthenticationManagerFactory factory =
        new LdapBindAuthenticationManagerFactory(contextSource);

    factory.setUserDnPatterns("uid={0},ou=people");
    factory.setLdapAuthoritiesPopulator(authorities);
    return factory.createAuthenticationManager();
}
```

Với fixture ở trên:

- `linh` là member của group `readers`.
- `an` là member của group `writers`.
- Group role attribute là `cn`.
- Role prefix là `ROLE_`.

Test:

```java
@Test
void mapsGroupMembershipToExpectedAuthority() {
    var result = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "linh",
            "test-linh-password"
        )
    );

    assertThat(result.getAuthorities())
        .extracting("authority")
        .contains("ROLE_READERS")
        .doesNotContain("ROLE_WRITERS");
}
```

Kiểm thử cả trường hợp user không thuộc group nào, user thuộc nhiều group, group search base sai và group attribute bị ACL ẩn. Không chỉ assert Bind thành công; phải xác minh authorities đúng với membership trong directory.

Trong cấu hình production, group search có thể chạy bằng manager/service identity của ContextSource thay vì user vừa Bind. Identity đó phải có quyền search group và read attribute membership cần thiết. Nếu test group mapping thất bại sau khi Bind thành công, kiểm tra quyền đọc group của ContextSource dùng bởi authorities populator.

### 6.4. Test HTTP authorization khác với test LDAP authentication

`@WithMockUser` hoặc request post-processor `user(...)` tạo Authentication giả cho test Spring Security web. Chúng hữu ích để kiểm tra endpoint yêu cầu role, nhưng **không** gọi LDAP và không kiểm tra Bind.

Chia test thành hai lớp:

- Integration test với `AuthenticationManager` thật để xác minh Bind và group mapping.
- Web/security test để xác minh `ROLE_READERS` được phép gọi endpoint đọc, còn user không có role bị từ chối.

Nếu muốn kiểm tra toàn bộ chuỗi HTTP login → LDAP Bind → authority mapping → endpoint authorization, dùng `@SpringBootTest`/MockMvc với security configuration và LDAP test server thật, không thay Authentication bằng mock.

## 7. Kiểm thử ACL trên LDAP server

ACL (Access Control List) được LDAP server thực thi. Spring Data LDAP không tự cấp quyền chỉ vì repository method đã chạy được. Để kiểm thử ACL, cần tạo các bind identity khác nhau và thực hiện operation thật bằng từng identity.

Ví dụ ma trận:

| Identity | Search people | Read mail | Read userPassword | Modify people | Modify groups |
| --- | --- | --- | --- | --- | --- |
| Anonymous | Không | Không | Không | Không | Không |
| `svc-reader` | Có | Có | Không | Không | Không |
| `svc-writer` | Có | Có | Không | Có | Không |
| `linh` | Theo policy | Theo policy | Chỉ auth/self | Chỉ entry của mình nếu policy cho phép | Không |
| Directory administrator | Có | Có | Theo policy quản trị | Có | Có |

Quyền cụ thể phải phản ánh policy của hệ thống. Ví dụ này chỉ là policy mẫu để tạo test case rõ ràng.

### 7.1. OpenLDAP ACL là đặc thù vendor

OpenLDAP dùng ACL trong `slapd.conf` hoặc `olcAccess` của dynamic configuration. Ví dụ `slapd.conf` minh họa:

```text
access to attrs=userPassword
    by self =xw
    by anonymous auth
    by * none

access to dn.subtree="ou=people,dc=example,dc=org"
    by self read
    by dn.exact="cn=svc-reader,ou=service,dc=example,dc=org" read
    by dn.exact="cn=svc-writer,ou=service,dc=example,dc=org" write
    by * none

access to dn.subtree="ou=groups,dc=example,dc=org"
    by dn.exact="cn=svc-reader,ou=service,dc=example,dc=org" read
    by dn.exact="cn=svc-writer,ou=service,dc=example,dc=org" read
    by * none

access to *
    by * none
```

Đây là cú pháp OpenLDAP, không phải cú pháp ACL chung cho mọi LDAP server. `by self =w` cấp đúng write privilege cho chủ thể self trên `userPassword`, không cấp read privilege cho password value. Trong policy minh họa, reader được đọc people và groups; writer được sửa people nhưng chỉ đọc groups. ACL được đánh giá theo thứ tự; entry/attribute phù hợp với rule nào thì kết quả phụ thuộc rule đó và các access level được cấp.

**Không dùng `rootdn` để test deny.** OpenLDAP root DN luôn có toàn quyền và bỏ qua ACL; nếu test bằng root DN, các assertion “reader không được ghi” hoặc “anonymous không được đọc” sẽ không có giá trị.

### 7.2. Quyền entry và quyền attribute

Một search có thể:

- Bị từ chối vì không có quyền `search` trên search base.
- Trả entry nhưng bỏ một attribute mà caller không có quyền `read`.
- Trả `insufficientAccessRights` hoặc lỗi khác tùy operation/server.

Vì vậy, test không nên chỉ kiểm tra số lượng entry. Cần assert từng attribute quan trọng:

```java
import javax.naming.directory.Attributes;

@Test
void readerCanReadMailButCannotReadPasswordAttribute() {
    Attributes attributes = readerTemplate.lookup(
        "uid=linh,ou=people",
        new String[] {"mail", "userPassword"},
        attrs -> attrs
    );

    assertThat(attributes.get("mail")).isNotNull();
    assertThat(attributes.get("userPassword")).isNull();
}
```

Kết quả cụ thể phụ thuộc ACL và API lookup. Nếu server từ chối toàn bộ lookup thay vì ẩn attribute, test phải assert exception tương ứng. Không giả định mọi server xử lý attribute bị ẩn giống nhau.

### 7.3. Tạo ContextSource riêng cho từng identity

Không dùng một `LdapTemplate` với administrator credentials để giả lập reader. Tạo ContextSource với bind DN và password của từng principal:

```java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

LdapTemplate templateFor(
        String ldapUrl,
        String baseDn,
        String bindDn,
        String password) throws Exception {

    LdapContextSource source = new LdapContextSource();
    source.setUrl(ldapUrl);
    source.setBase(baseDn);
    source.setUserDn(bindDn);
    source.setPassword(password);
    source.afterPropertiesSet();

    return new LdapTemplate(source);
}
```

Dùng helper trong test:

```java
LdapTemplate readerTemplate = templateFor(
    ldapUrl,
    "dc=example,dc=org",
    "cn=svc-reader,ou=service,dc=example,dc=org",
    readerPassword
);

LdapTemplate writerTemplate = templateFor(
    ldapUrl,
    "dc=example,dc=org",
    "cn=svc-writer,ou=service,dc=example,dc=org",
    writerPassword
);
```

Trong thực tế, khởi tạo một ContextSource cho mỗi identity trong test fixture hoặc test configuration, rồi đóng/destroy theo lifecycle. Không tạo ContextSource mới cho mỗi assertion nếu không cần.

### 7.4. Test quyền đọc và ghi

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import javax.naming.directory.BasicAttribute;
import javax.naming.directory.ModificationItem;
import javax.naming.directory.DirContext;
import org.springframework.dao.DataAccessException;

@Test
void readerCanSearchButCannotModifyEntry() {
    assertThat(readerTemplate.search(
        "ou=people",
        "(uid=linh)",
        (org.springframework.ldap.core.AttributesMapper<String>)
            attrs -> (String) attrs.get("uid").get()
    )).containsExactly("linh");

    ModificationItem changeMail = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "changed@example.org")
    );

    assertThatThrownBy(() ->
        readerTemplate.modifyAttributes(
            "uid=linh,ou=people",
            new ModificationItem[] {changeMail}
        )
    ).isInstanceOf(DataAccessException.class);

    writerTemplate.modifyAttributes(
        "uid=linh,ou=people",
        new ModificationItem[] {changeMail}
    );

    assertThat(writerTemplate.lookup(
        "uid=linh,ou=people",
        new String[] {"mail"},
        attrs -> (String) attrs.get("mail").get()
    )).isEqualTo("changed@example.org");

    ModificationItem removeMember = new ModificationItem(
        DirContext.REMOVE_ATTRIBUTE,
        new BasicAttribute(
            "member",
            "uid=an,ou=people,dc=example,dc=org"
        )
    );

    assertThatThrownBy(() ->
        writerTemplate.modifyAttributes(
            "cn=readers,ou=groups",
            new ModificationItem[] {removeMember}
        )
    ).isInstanceOf(DataAccessException.class);
}
```

Test tương ứng với `svc-writer` cần xác minh writer được phép sửa đúng entry/attribute cần thiết. Cũng cần xác minh writer không được sửa group hoặc `userPassword` nếu policy cấm.

### 7.5. Kiểm thử quyền password

Một policy thường gặp:

- User có quyền đổi password của chính mình.
- Anonymous chỉ có quyền `auth` trên `userPassword` để server kiểm tra Bind.
- Service reader không được đọc password attribute.
- Service account không có quyền sửa password của user khác.

Không assert password bằng cách đọc giá trị `userPassword`. Hãy kiểm tra bằng hành vi Bind đúng/sai và thao tác Modify password được phép/từ chối. Password có thể được hash, multi-valued hoặc do password policy overlay quản lý.

## 8. Kiểm thử LDAPS và StartTLS

LDAPS và StartTLS đều dùng TLS nhưng thiết lập TLS ở thời điểm khác nhau:

| Cách kết nối | URL | Thời điểm TLS |
| --- | --- | --- |
| LDAP không TLS | `ldap://host:389` | Không có TLS. |
| LDAPS | `ldaps://host:636` | TLS ngay khi mở socket. |
| StartTLS | `ldap://host:389` | Kết nối LDAP trước, sau đó gửi StartTLS extended operation để nâng cấp cùng connection lên TLS. |

Không cấu hình `ldaps://` rồi lại gửi StartTLS trên cùng session. Cũng không coi việc mở được TCP port 389 là chứng minh TLS đã được bật.

RFC 4513 khuyến nghị client thực hiện StartTLS trước Bind khi cần cả hai, để Bind request/response được bảo vệ. Client phải xác minh danh tính server dựa trên certificate; automated client nên đóng connection nếu identity check thất bại.

### 8.1. Cấu hình LDAPS trong Spring Boot

Với Spring Boot, cấu hình SSL bundle cho client và URL `ldaps://`:

```yaml
spring:
  ldap:
    urls: ldaps://ldap-test.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_TEST_BIND_PASSWORD}
    ssl:
      bundle: ldap-client
```

Bundle `ldap-client` phải có trust material tin cậy CA phát hành certificate của LDAP server. Nếu certificate là self-signed, chỉ import certificate test vào truststore của test profile; không tắt xác minh certificate để làm test pass.

Nếu không cần custom trust/key material, Spring Boot có thể dùng platform default trust material qua `spring.ldap.ssl.enabled=true`. Với test deterministic, nên cấu hình truststore rõ ràng.

### 8.2. Bật LDAPS cho embedded UnboundID

Spring Boot embedded LDAP có thể bật SSL bằng SSL bundle riêng cho embedded server:

```yaml
spring:
  ldap:
    embedded:
      base-dn: dc=example,dc=org
      ldif: classpath:ldap-security.ldif
      ssl:
        bundle: ldap-test
```

Bundle `ldap-test` phải chứa:

- Key store với certificate và private key mà embedded LDAP server trình ra.
- Trust store để client tin cậy certificate đó.

Certificate phải có SAN khớp hostname client dùng để kết nối, ví dụ `DNS:localhost` nếu test kết nối `ldaps://localhost`. Boot embedded server có thể tự cấu hình client dùng cùng bundle; nếu cần kiểm thử trust material độc lập giữa client và server, dùng `LdapConnectionDetails`/ContextSource riêng hoặc một LDAP test server bên ngoài.

Ví dụ cấu hình JKS/PKCS12 SSL bundle trong `application-test.yml` (đường dẫn và password là giá trị test):

```yaml
spring:
  ssl:
    bundle:
      jks:
        ldap-test:
          key:
            alias: ldap-test
          keystore:
            location: classpath:ldap-test.p12
            password: ${LDAP_TEST_KEYSTORE_PASSWORD}
            type: PKCS12
          truststore:
            location: classpath:ldap-test-trust.p12
            password: ${LDAP_TEST_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

Nếu server và client dùng hai bundle khác nhau, cấu hình bundle cho từng bên và đảm bảo truststore của client tin cậy CA/certificate server. Private key chỉ nằm trong key store phía server hoặc client tương ứng; không chia sẻ private key của server để thay cho trust configuration.

### 8.3. Tạo certificate test có SAN

Ví dụ tạo certificate test self-signed cho `localhost` bằng `keytool`:

```bash
keytool -genkeypair \
  -alias ldap-test \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore ldap-test.p12 \
  -storepass changeit \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert \
  -rfc \
  -alias ldap-test \
  -keystore ldap-test.p12 \
  -storepass changeit \
  -file ldap-test.crt

keytool -importcert \
  -alias ldap-test-ca \
  -file ldap-test.crt \
  -storetype PKCS12 \
  -keystore ldap-test-trust.p12 \
  -storepass changeit \
  -noprompt
```

`changeit` chỉ là password ví dụ cho test. Dùng password từ environment/CI secret và không dùng certificate/private key test làm credential production.

### 8.4. Cấu hình StartTLS trong Spring LDAP

StartTLS dùng `ldap://` rồi nâng cấp TLS qua `DirContextAuthenticationStrategy`. Spring LDAP có:

- `DefaultTlsDirContextAuthenticationStrategy`: StartTLS, sau đó SIMPLE Bind bằng DN/password.
- `ExternalTlsDirContextAuthenticationStrategy`: StartTLS và SASL EXTERNAL, dùng client certificate theo cấu hình.

Ví dụ dùng SSL socket factory từ Spring Boot SSL bundle:

```java
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;

@Configuration
class LdapStartTlsConfiguration {

    @Bean
    DefaultTlsDirContextAuthenticationStrategy startTlsStrategy(
            SslBundles sslBundles) {

        var strategy = new DefaultTlsDirContextAuthenticationStrategy();
        strategy.setSslSocketFactory(
            sslBundles.getBundle("ldap-client")
                .createSslContext()
                .getSocketFactory()
        );
        return strategy;
    }
}
```

ContextSource của ứng dụng phải dùng URL `ldap://...` và nhận bean `DirContextAuthenticationStrategy` này. Ví dụ phần URL/Bind config:

```yaml
spring:
  ldap:
    urls: ldap://ldap-test.example.org:389
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_TEST_BIND_PASSWORD}
```

Không gắn SSL bundle bằng `spring.ldap.ssl.bundle` cho StartTLS: thuộc tính đó dành cho LDAPS. Nếu tự định nghĩa ContextSource, phải cấu hình strategy trên ContextSource đó.

### 8.5. TLS strategy và connection pooling

Spring LDAP hỗ trợ `DefaultTlsDirContextAuthenticationStrategy` và `ExternalTlsDirContextAuthenticationStrategy`. `DefaultTls...` dùng SIMPLE authentication trên TLS session; `ExternalTls...` dùng SASL EXTERNAL.

Với TLS strategy:

- Tắt native Java LDAP pooling; Spring LDAP cảnh báo native pooling không hoạt động đúng với TLS authentication strategies.
- Nếu cần pooling, dùng `PoolingContextSource` của Spring LDAP.
- Chỉ bật graceful TLS shutdown khi server cần; hành vi shutdown khác nhau theo implementation.
- Giữ hostname verification mặc định. Chỉ cấu hình verifier riêng khi có yêu cầu kỹ thuật rõ ràng và vẫn xác minh đúng server identity.

## 9. Ma trận kiểm thử TLS

| Kịch bản | Kết quả mong đợi | Lỗi cần phân biệt |
| --- | --- | --- |
| Certificate do CA tin cậy ký, SAN đúng hostname | TLS handshake thành công | Không có lỗi trust/hostname. |
| Certificate do CA không tin cậy ký | Handshake thất bại | PKIX path/trust failure. |
| Certificate hết hạn | Handshake thất bại | Certificate validity failure. |
| SAN không khớp hostname | Handshake thất bại | Hostname verification failure. |
| Certificate thiếu SAN phù hợp | Handshake thất bại theo policy client | Server identity không được xác minh. |
| TLS protocol/cipher không giao nhau | Handshake thất bại | Protocol/cipher negotiation failure. |
| StartTLS bị server từ chối | Không thực hiện Bind credential trên kết nối plaintext | StartTLS extended operation failure. |
| Server yêu cầu client certificate, client không gửi | TLS handshake thất bại hoặc server từ chối theo policy | Client certificate failure. |
| Client certificate hợp lệ, SASL EXTERNAL được cấu hình | TLS và Bind EXTERNAL thành công | Xác minh certificate mapping/authorization identity. |
| Certificate đúng nhưng password Bind sai | TLS thành công, Bind thất bại | Authentication failure, không phải TLS failure. |

### 9.1. Test trusted certificate

Với embedded LDAPS hoặc test server có certificate được truststore tin cậy:

```java
@Test
void connectsOverLdapsWithTrustedCertificate() {
    assertThat(ldapTemplate.search(
        "ou=people",
        "(uid=linh)",
        (org.springframework.ldap.core.AttributesMapper<String>)
            attrs -> (String) attrs.get("uid").get()
    )).containsExactly("linh");
}
```

Test này chứng minh client đã kết nối, TLS handshake và LDAP Search thành công. Để chắc chắn test đang đi qua LDAPS, hãy kiểm tra URL/cấu hình test profile và server listener; một search thành công trên `ldap://` không chứng minh TLS.

### 9.2. Test untrusted certificate

Khởi tạo một ContextSource riêng với truststore không chứa CA test, rồi thực hiện một Search:

```java
@Test
void rejectsCertificateFromUntrustedAuthority() {
    LdapTemplate untrustedTemplate =
        ldapTemplateUsingTrustStore("empty-truststore.p12");

    assertThatThrownBy(() ->
        untrustedTemplate.search(
            "ou=people",
            "(uid=linh)",
            (org.springframework.ldap.core.AttributesMapper<String>)
                attrs -> (String) attrs.get("uid").get()
        )
    ).isInstanceOf(org.springframework.ldap.CommunicationException.class);
}
```

`ldapTemplateUsingTrustStore` là helper test dựng `LdapContextSource` với SSL socket factory/truststore riêng. Exception Spring LDAP có thể bọc `SSLHandshakeException`/`CertPathValidatorException`; khi chẩn đoán, kiểm tra cả cause chain thay vì chỉ assert một thông báo chuỗi.

### 9.3. Test hostname mismatch

Tạo certificate có SAN `DNS:ldap-test.internal`, sau đó kết nối tới hostname `localhost`. Client phải từ chối certificate dù CA đã được trust. Nếu test chỉ trust certificate mà không kiểm tra hostname, nó chưa kiểm tra server identity đầy đủ.

Không cấu hình `HostnameVerifier` luôn trả `true`, không dùng trust-all `TrustManager` và không tắt hostname verification trong test profile.

### 9.4. Test StartTLS bắt buộc

Với server test được cấu hình yêu cầu TLS:

1. Kết nối tới `ldap://host:389`.
2. Thực hiện StartTLS thành công.
3. Bind bằng credential đúng và kiểm tra Search.
4. Thử một client không cấu hình StartTLS; server phải từ chối simple Bind/operation nhạy cảm theo policy.
5. Thử certificate không tin cậy hoặc hostname mismatch; handshake phải thất bại trước Bind.

Nếu server vẫn cho phép simple Bind plaintext, test có thể phát hiện policy server chưa ép TLS. Không chỉ kiểm tra rằng ứng dụng có bean StartTLS; hãy xác minh request thực sự được nâng cấp trước Bind.

## 10. Kiểm thử mTLS và SASL EXTERNAL

Với mutual TLS, server yêu cầu client certificate trong TLS handshake. Sau handshake, client có thể dùng SASL EXTERNAL để server ánh xạ certificate sang authorization identity.

Spring LDAP có `ExternalTlsDirContextAuthenticationStrategy`. Kiểm thử cần ít nhất:

- Certificate client do CA được server tin cậy ký.
- Certificate client hết hạn/không được trust.
- Client không gửi certificate khi server yêu cầu.
- Certificate hợp lệ nhưng không được phép ánh xạ sang identity mong muốn.
- SASL EXTERNAL bind thành công và trả về authorization identity đúng.

Không đồng nhất client certificate hợp lệ với quyền LDAP. Server vẫn cần authorization policy cho identity được ánh xạ từ certificate.

## 11. Kiểm thử quyền nghiệp vụ trong Spring Security

Sau khi LDAP authorities được tải, ứng dụng thường bảo vệ endpoint hoặc method bằng role:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.stereotype.Service;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

@Service
class DirectoryAdminService {

    @PreAuthorize("hasRole('DIRECTORY_ADMIN')")
    public void rebuildDirectoryIndex() {
        // Thao tác quản trị.
    }
}
```

Test hai luồng:

1. User được LDAP group mapping thành `ROLE_DIRECTORY_ADMIN`, gọi method thành công.
2. User không thuộc group đó, xác thực LDAP có thể thành công nhưng gọi method bị từ chối.

Không assert user không thuộc group là “authentication failed”. User có thể đã được xác thực chính xác nhưng không có authority cần thiết.

Ví dụ unit/web security test cho policy method:

```java
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DirectoryAdminServiceSecurityTests {

    @Autowired
    private DirectoryAdminService directoryAdminService;

    @Test
    @WithMockUser(roles = "DIRECTORY_ADMIN")
    void adminCanRebuildIndex() {
        assertThatCode(directoryAdminService::rebuildDirectoryIndex)
            .doesNotThrowAnyException();
    }

    @Test
    @WithMockUser(roles = "READERS")
    void readerCannotRebuildIndex() {
        assertThatThrownBy(directoryAdminService::rebuildDirectoryIndex)
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

Đây là test authorization ở tầng Spring Security; nó cố ý dùng Authentication giả. Giữ integration test LDAP ở mục 6 để kiểm tra Bind và authorities thực tế.

## 12. Chẩn đoán lỗi theo lớp

| Triệu chứng | Lớp có thể lỗi | Kiểm tra |
| --- | --- | --- |
| `SSLHandshakeException` | TLS trust/protocol | CA chain, expiry, SAN, hostname, protocol và cipher. |
| `CommunicationException` trước Bind | TLS/network | Host/port, certificate, listener, firewall. |
| `AuthenticationException` hoặc `invalidCredentials` | Bind | Full DN, password, empty password, account state. |
| Bind thành công nhưng Search bị từ chối | ACL | Quyền `search` trên base và `read` trên entry/attribute. |
| Search trả entry nhưng thiếu attribute | ACL/projection | Quyền read attribute và returning attributes. |
| Modify bị `insufficientAccessRights` | ACL | Quyền write trên entry/attribute và parent children. |
| User login thành công nhưng thiếu role | Group mapping | Group base/filter, attribute `member`/`uniqueMember`, role attribute/prefix. |
| `ROLE_...` không khớp endpoint | Application authorization | Role prefix, method/HTTP policy, authorities thực tế. |
| Anonymous request vẫn đọc được dữ liệu | Anonymous ACL | Server default policy, anonymous read và bind identity thực tế. |
| Test deny luôn pass/fail sai | Test identity | Có đang dùng rootdn/admin bind hoặc ContextSource dùng chung credential không? |

Khi test ACL, hãy log danh tính bind đã chuẩn hóa và operation đang thử; không log password, `userPassword`, access token hoặc private key. Nếu cần log LDAP result code, không trả chi tiết nhạy cảm này cho end user.

## 13. Test trên OpenLDAP container

Để kiểm thử ACL và StartTLS gần thực tế, chạy OpenLDAP container với:

- Image version cố định.
- Suffix `dc=example,dc=org`.
- LDIF fixture.
- ACL config riêng cho test.
- Certificate test có SAN.
- Health check chờ Bind/Search thành công.

Ví dụ policy ACL OpenLDAP ở mục 7.1 nên được nạp vào đúng test server. Dùng `ldapwhoami`, `ldapsearch`, `ldapmodify` với các bind DN khác nhau để xác minh server trước khi test Spring:

```bash
# Xác minh reader bind và identity.
ldapwhoami -x -H "ldaps://localhost:636" \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W

# Reader được search people.
ldapsearch -LLL -x -H "ldaps://localhost:636" \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" "(uid=linh)" uid mail

# Writer không được sửa group nếu ACL không cấp quyền.
ldapmodify -x -H "ldaps://localhost:636" \
  -D "cn=svc-writer,ou=service,dc=example,dc=org" -W <<'LDIF'
dn: cn=readers,ou=groups,dc=example,dc=org
changetype: modify
replace: description
description: forbidden change
LDIF
```

Lệnh cuối phải thất bại theo policy nếu writer không có quyền sửa group. Trong automation, kiểm tra exit code và result code thay vì chỉ tìm từ “error” trong output.

Không dùng tài khoản `rootdn` trong các lệnh deny. Root DN của OpenLDAP luôn có toàn quyền và bỏ qua ACL.

## 14. Ma trận kiểm thử bảo mật

| Nhóm | Test case | Assertion |
| --- | --- | --- |
| Bind | User/password hợp lệ | Authentication thành công. |
| Bind | Password sai | Authentication thất bại. |
| Bind | User không tồn tại | Authentication thất bại, không cấp anonymous session như user đó. |
| Bind | Password rỗng | Ứng dụng từ chối. |
| Bind | Search filter không duy nhất | Cấu hình/test phát hiện user lookup ambiguity. |
| Group mapping | User thuộc readers | Có `ROLE_READERS`. |
| Group mapping | User không thuộc writers | Không có `ROLE_WRITERS`. |
| Group mapping | User thuộc nhiều group | Authorities đúng toàn bộ membership. |
| HTTP/method | User có role phù hợp | Endpoint/method cho phép. |
| HTTP/method | User thiếu role | Bị từ chối dù Bind thành công. |
| ACL | Anonymous search | Bị từ chối theo policy. |
| ACL | Reader search people | Thành công. |
| ACL | Reader modify people | Bị từ chối. |
| ACL | Reader đọc userPassword | Không được đọc. |
| ACL | Writer sửa attribute được cấp | Thành công. |
| ACL | Writer sửa group không được cấp | Bị từ chối. |
| LDAPS | Trusted CA + SAN đúng | Handshake thành công. |
| LDAPS | CA không trust | Handshake thất bại. |
| LDAPS | Hostname mismatch | Handshake thất bại. |
| LDAPS | Certificate expired | Handshake thất bại. |
| StartTLS | StartTLS trước Bind | TLS và Bind thành công. |
| StartTLS | Bind plaintext khi server yêu cầu TLS | Server từ chối. |
| mTLS | Client certificate hợp lệ | TLS/mTLS và EXTERNAL theo policy thành công. |
| mTLS | Certificate thiếu/không hợp lệ | Handshake hoặc EXTERNAL Bind thất bại. |

## 15. Chạy test trong CI an toàn và ổn định

- Dùng LDAP server/container cô lập cho mỗi test job.
- Pin image version và fixture LDIF; không phụ thuộc directory dùng chung.
- Dùng user, group và service account riêng cho test.
- Không dùng `rootdn` cho test quyền bị từ chối.
- Dùng certificate test có SAN; tạo truststore riêng cho test.
- Đưa password/keystore password qua CI secret hoặc environment variable.
- Không commit private key production hoặc credential thật.
- Tách embedded test nhanh khỏi OpenLDAP/AD contract test.
- Chạy test ACL trên đúng vendor/version có policy triển khai.
- Đảm bảo test dọn container/context và không để bind session hoặc connection pool rò rỉ.
- Không retry vô hạn khi TLS/Bind/ACL fail; fail sớm để giữ nguyên bằng chứng.
- Không tắt hostname verification hoặc trust validation để làm pipeline xanh.

### 15.1. Test âm cần được xác nhận đúng lớp

Một test “request thất bại” chưa đủ. Ví dụ certificate không tin cậy phải thất bại ở TLS handshake, chứ không phải kết nối được rồi Bind sai. Tương tự, reader sửa entry phải thất bại ở ACL, không phải do password reader sai.

Với test âm, xác minh:

1. Kết nối tới đúng host/port.
2. Bind identity đúng.
3. Operation đã tới đúng tầng cần kiểm tra.
4. Kết quả thất bại là do policy mong muốn.
5. Không có fallback vô tình sang anonymous/admin connection.

## 16. Checklist trước khi merge

- [ ] Test phân biệt authentication, authorization và transport security.
- [ ] Fixture có user, group và service identity riêng.
- [ ] Có test credential đúng, sai, user lạ và password rỗng.
- [ ] Không dùng empty password để chứng minh Bind thành công.
- [ ] Có test Spring Security `AuthenticationManager` thật.
- [ ] Có test group-to-authority mapping.
- [ ] Web/method authorization test được tách khỏi LDAP Bind test.
- [ ] ACL test dùng nhiều ContextSource/bind DN khác nhau.
- [ ] Không dùng rootdn/administrator trong test deny.
- [ ] Có test quyền entry và quyền attribute.
- [ ] Có test reader/writer và password attribute.
- [ ] LDAPS test xác minh CA trust và hostname SAN.
- [ ] Có test untrusted/expired/mismatched certificate.
- [ ] StartTLS được thực hiện trước Bind và server từ chối plaintext theo policy.
- [ ] mTLS/SASL EXTERNAL được kiểm thử nếu triển khai.
- [ ] Không tắt hostname verification hoặc dùng trust-all manager.
- [ ] TLS strategy không dùng native LDAP pooling.
- [ ] Vendor-specific ACL test chạy trên đúng LDAP server.
- [ ] Password, private key và cookie/credential không xuất hiện trong log.
- [ ] Test cleanup context, connection và container.

## 17. Bài tập thực hành

1. Tạo LDIF có `linh`, `an`, group `readers`, group `writers` và hai service account.
2. Viết test `LdapTemplate.authenticate` cho password đúng/sai và user không tồn tại.
3. Viết test chứng minh password rỗng bị từ chối.
4. Cấu hình `LdapBindAuthenticationManagerFactory` và xác minh authorities của `linh`.
5. Tạo endpoint yêu cầu `ROLE_READERS`; test user readers được phép và user writers bị từ chối.
6. Cấu hình OpenLDAP ACL để reader chỉ đọc people, writer sửa một số attribute nhưng không sửa group.
7. Dùng hai ContextSource với bind DN riêng và kiểm thử quyền.
8. Thử đọc `userPassword` bằng reader; xác minh attribute không lộ ra.
9. Tạo certificate test SAN `localhost`, bật LDAPS và xác minh handshake.
10. Thay truststore bằng truststore không chứa CA; xác minh lỗi TLS.
11. Kết nối bằng hostname không khớp SAN; xác minh client từ chối.
12. Bật StartTLS và xác minh Bind chỉ diễn ra sau TLS negotiation.
13. Nếu hệ thống dùng mTLS, kiểm tra client certificate và SASL EXTERNAL.
14. Ghi lại một lỗi mỗi lớp: TLS, Bind, ACL và Spring Security authority; phân loại chính xác từng lỗi.

## 18. Tài liệu tham khảo

- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): Simple Bind, unauthenticated Bind, StartTLS, server identity check và SASL EXTERNAL.
- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): embedded LDAP server, UnboundID, ApacheDS và LDIF fixture.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, authentication strategy, StartTLS, LDAPS và pooling.
- [Spring LDAP — User Authentication](https://docs.spring.io/spring-ldap/reference/user-authentication.html): `LdapClient` authenticate, authenticated context mapper và các API cũ đã deprecated.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `authenticate` bằng Bind.
- [Spring LDAP API — LdapClient](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapClient.html): fluent authentication và search API.
- [Spring LDAP API — DefaultTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/DefaultTlsDirContextAuthenticationStrategy.html): StartTLS và SIMPLE Bind.
- [Spring LDAP API — AbstractTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractTlsDirContextAuthenticationStrategy.html): hostname verifier, SSL socket factory, shutdown và pooling.
- [Spring Boot — Working with LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): `spring.ldap.ssl.bundle`, embedded LDAPS và SSL bundle.
- [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/ldap.html): Bind authentication, AuthenticationManager và authorities populator.
- [OpenLDAP 2.6 Administrator's Guide — Access Control](https://www.openldap.org/doc/admin26/access-control.html): ACL selectors, access levels, ordering và rootdn behavior.
- [Oracle Java SE — SSL/TLS](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE trust/key material và TLS.
