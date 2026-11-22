# LDAP/Active Directory: Password comparison và điều kiện sử dụng phù hợp

## 1. Mục tiêu

Trong Spring Security, **password comparison** là chiến lược xác thực tài khoản LDAP bằng cách đối chiếu mật khẩu người dùng nhập với dữ liệu mật khẩu trong directory. Chiến lược này chỉ phù hợp khi **cách lưu mật khẩu, quyền truy cập thuộc tính, cơ chế kiểm tra và chính sách bảo mật của directory** đều cho phép.

Sau bài này, bạn cần phân biệt được:
- `bind authentication`: directory xác thực bằng cách thử bind bằng danh tính và mật khẩu của chính người dùng;
- **LDAP Compare**: ứng dụng yêu cầu directory đối chiếu một giá trị với thuộc tính mật khẩu mà không đọc giá trị đang lưu;
- **local password comparison**: ứng dụng có quyền đọc giá trị mật khẩu đã lưu (thường là hash), rồi gọi `PasswordEncoder.matches(rawPassword, storedHash)`.

**Quy tắc chọn nhanh:** Với Active Directory (AD DS) và phần lớn LDAP doanh nghiệp, ưu tiên **bind**. Chỉ triển khai password comparison khi đã chứng minh directory hỗ trợ đúng chế độ và không làm sai lệch các chính sách tài khoản.

## 2. Bối cảnh: password comparison hoạt động ở đâu?

Giả sử có cây LDAP:

~~~text
dc=example,dc=org
└── ou=people
    └── uid=alice
        ├── uid: alice
        ├── cn: Alice Nguyen
        └── userPassword: <giá trị mật khẩu hoặc hash do directory quản lý>
~~~

- **DN (Distinguished Name)** xác định một entry: `uid=alice,ou=people,dc=example,dc=org`.
- `uid` thường dùng để tìm người dùng ở LDAP thông thường; Active Directory có thể dùng `sAMAccountName` hoặc `userPrincipalName`.
- `userPassword` là tên thuộc tính mặc định của password comparison trong Spring Security LDAP; directory thực tế có thể đặt tên khác.
- `Authentication` trả lời **người dùng là ai, có xác thực hợp lệ không**; `GrantedAuthority`/nhóm giải quyết **họ được làm gì**. Kiểm tra mật khẩu thành công không tự động trao quyền quản trị.

Spring Security cung cấp `BindAuthenticator` và `PasswordComparisonAuthenticator` cho LDAP, thông qua `LdapAuthenticationProvider` hoặc các factory cấu hình `AuthenticationManager`. Cơ chế LDAP bind thông thường không sử dụng `UserDetailsService`/`DaoAuthenticationProvider` để đọc hash rồi so khớp như tài khoản nằm trong database ứng dụng.

## 3. Ba cách kiểm tra mật khẩu

### 3.1. Bind: directory xác thực trực tiếp

~~~text
Client gửi username + password
    ↓
Spring Security tìm DN (hoặc suy ra DN từ pattern)
    ↓
Kết nối TLS tới directory, bind bằng DN/UPN + mật khẩu người dùng
    ↓
Directory áp dụng logic đăng nhập của nó → thành công/thất bại
    ↓
Spring Security nạp thuộc tính và nhóm cần thiết
~~~

Ứng dụng **không cần đọc thuộc tính mật khẩu**, không cần biết mật khẩu được hash theo thuật toán nào. Đây thường là lựa chọn tốt nhất khi directory quản lý khóa tài khoản, thời hạn mật khẩu, policy và các điều kiện đăng nhập. Đối với AD, nên dùng `ActiveDirectoryLdapAuthenticationProvider` hoặc chiến lược bind phù hợp với UPN/domain.

### 3.2. LDAP Compare: đối chiếu ở directory

~~~text
Client gửi username + password
    ↓
Ứng dụng bind bằng service account có quyền tìm/compare
    ↓
Tìm user DN
    ↓
LDAP Compare(userDN, passwordAttribute, candidateValue)
    ↓
Directory trả kết quả compare true/false (hoặc LDAP error)
~~~

**Không cần đọc giá trị mật khẩu đang lưu**, nhưng **candidate** vẫn được truyền tới directory; vì vậy kết nối phải được bảo vệ bằng TLS. LDAP Compare là phép so sánh một thuộc tính theo ngữ nghĩa directory, **không phải cam kết rằng directory đã thực hiện toàn bộ quy trình đăng nhập**. Việc account bị khóa, hết hạn hoặc bị vô hiệu hóa có được kiểm tra hay không phụ thuộc directory/cấu hình: phải kiểm thử, không suy đoán.

Nếu ứng dụng phải tự mã hóa mật khẩu nhập trước khi so sánh với giá trị hash qua LDAP Compare, hash có **salt ngẫu nhiên** (SSHA, bcrypt, Argon2...) không thể tái tạo thành cùng chuỗi hash chỉ từ mật khẩu nhập. Với những trường hợp này, không coi LDAP Compare bằng hash mã hóa sẵn là phương án mặc định.

### 3.3. Local compare: đọc hash và xác minh trong ứng dụng

~~~text
Client gửi username + password
    ↓
Ứng dụng dùng service account tìm user DN
    ↓
Đọc thuộc tính password/hash được directory cho phép đọc
    ↓
PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Trả kết quả; kiểm tra riêng các trạng thái tài khoản cần thiết
~~~

Đây là cách có thể xử lý hash có salt, chẳng hạn bcrypt, vì `matches` dùng salt và tham số chứa trong **stored hash**. Tuy nhiên ứng dụng/service account phải có quyền đọc dữ liệu mật khẩu, hash phải có định dạng tương thích với encoder, và hệ thống phải giải quyết đầy đủ các kiểm tra policy mà bind có thể thực hiện hộ. **Hash đã đọc vẫn là dữ liệu nhạy cảm**; không ghi log, cache bừa bãi hoặc trả cho client.

Cần phân biệt: cấu hình `new BCryptPasswordEncoder()` chỉ có ý nghĩa nếu directory đang lưu **bcrypt hash đọc được và đúng định dạng**. Không thể dùng bcrypt để “giải mã” mật khẩu AD.

## 4. Bảng chọn chiến lược

| Tiêu chí | Bind (thường ưu tiên) | LDAP Compare tại server | Local compare trong ứng dụng |
|---|---|---|---|
| Ứng dụng cần đọc mật khẩu/hash? | Không | Không | Có, phải được cấp quyền |
| Cần biết thuật toán hash của directory? | Không | Phụ thuộc cơ chế/giá trị compare | Có, cần `PasswordEncoder` tương thích |
| Hash có salt ngẫu nhiên | Directory tự xử lý | Thường không phù hợp với so sánh hash client tạo ra | Có thể, nếu đọc được hash hợp lệ |
| Chính sách khóa/hết hạn tài khoản | Thường theo quy trình xác thực directory | Phải kiểm chứng riêng | Phải thực thi/kiểm chứng riêng |
| Active Directory DS | **Nên dùng** | Không chọn mặc định | Thường không khả thi/không phù hợp |
| Rủi ro điển hình | TLS, DN/search config, quyền bind | Quyền compare, thuật toán, policy bị bỏ sót | Lộ hash, lệch policy, sai hash format |
| Khi cân nhắc dùng | AD/LDAP doanh nghiệp, mật khẩu không đọc được | Directory cho phép compare, candidate phù hợp, policy được xác thực | Directory tùy biến cho đọc hash, có yêu cầu cụ thể và kiểm soát chặt |

**Không đồng nhất “không đọc password” với “an toàn tuyệt đối”**: LDAP Compare và bind đều cần TLS, giới hạn quyền, kiểm soát brute force và chính sách xử lý lỗi.

## 5. Điều kiện để password comparison là lựa chọn phù hợp

Chỉ chọn **LDAP Compare** khi đồng thời đáp ứng:

1. Directory hỗ trợ phép compare trên đúng thuộc tính mật khẩu; account/service principal có quyền compare, tìm DN và đọc những thuộc tính cần thiết.
2. Giá trị candidate do Spring Security tạo ra tương thích với cách directory lưu/đối chiếu mật khẩu. Không giả định `userPassword` luôn là plaintext hoặc luôn có một loại hash.
3. Không cần đọc hash để so khớp thuật toán có salt ngẫu nhiên; hoặc đã có một cơ chế compare **được directory xác nhận hỗ trợ** riêng.
4. Đã thử nghiệm hành vi đối với tài khoản bị khóa, bị vô hiệu hóa, hết hạn mật khẩu, buộc đổi mật khẩu và lỗi kết nối.
5. Có kết nối `ldaps://` hoặc StartTLS với **kiểm tra chứng chỉ đúng**, quyền service account tối thiểu, giới hạn tần suất đăng nhập và giám sát.
6. Đã xác nhận cách tìm người dùng, mapping nhóm và phạm vi search chính xác, không cho phép nhiều entry trùng username gây nhập nhằng.

Chỉ chọn **local compare** khi còn chứng minh thêm rằng: (a) hash có thể đọc hợp lệ bằng quyền tối thiểu; (b) encoder dùng được với đúng format, prefix và salt; (c) yêu cầu tuân thủ cho phép ứng dụng xử lý hash; (d) cách kiểm tra account status, lockout, password expiry và chính sách liên quan không bị bỏ qua. Trường hợp thiếu bất kỳ điều kiện thiết yếu nào, **dùng bind**.

Các trường hợp nên tránh password comparison: tích hợp AD DS thông thường; directory không cho đọc/compare thuộc tính; mật khẩu được bảo vệ bằng thuật toán/format không tương thích; yêu cầu chính sách account phải do domain controller thực thi khi đăng nhập; hệ thống đang dùng `NoOpPasswordEncoder` cho plaintext trong môi trường thật; hoặc service account phải được cấp quyền quá rộng mới thực hiện được.

## 6. Ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+

Ví dụ sau dùng **LDAP tùy biến**, với điều kiện rõ ràng: entry trong `ou=people` có thuộc tính `userPassword` chứa **bcrypt hash ở định dạng mà `BCryptPasswordEncoder` đọc được**, service account được phép đọc thuộc tính đó, và chính sách tài khoản đã được xử lý/kiểm tra riêng. Đây là cấu hình cho một ứng dụng Spring Boot có sẵn; **không thể đăng nhập thực tế nếu chưa có LDAP server, dữ liệu người dùng, chứng chỉ tin cậy và thông tin kết nối**.

### 6.1. Dependencies

Trong `pom.xml` của dự án Spring Boot đã khai báo parent/BOM tương ứng:

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

### 6.2. Cấu hình đường dẫn và secret

Tệp `src/main/resources/application.properties`:

~~~properties
# Base DN được đặt trong URL; ou=people phía dưới là relative search base.
app.ldap.url=ldaps://ldap.example.org:636/dc=example,dc=org
app.ldap.manager-dn=${LDAP_MANAGER_DN}
app.ldap.manager-password=${LDAP_MANAGER_PASSWORD}
~~~

- Cấp `LDAP_MANAGER_DN` và `LDAP_MANAGER_PASSWORD` từ secrets manager/environment, không commit secret vào Git.
- Máy JVM phải tin cậy CA cấp chứng chỉ cho LDAP server. Không tắt kiểm tra hostname/chứng chỉ để “sửa” lỗi TLS.
- `uid`, `ou=people` và `userPassword` là **ví dụ**; đổi theo schema directory thực tế.

### 6.3. AuthenticationManager sử dụng password comparison

Tệp `src/main/java/com/example/security/LdapCompareConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapPasswordComparisonAuthenticationManagerFactory;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;

@Configuration
public class LdapCompareConfiguration {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.manager-dn}") String managerDn,
            @Value("${app.ldap.manager-password}") String managerPassword) {

        DefaultSpringSecurityContextSource source =
                new DefaultSpringSecurityContextSource(url);
        source.setUserDn(managerDn);
        source.setPassword(managerPassword);
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        var factory = new LdapPasswordComparisonAuthenticationManagerFactory(
                contextSource, new BCryptPasswordEncoder());
        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");
        factory.setPasswordAttribute("userPassword");
        return factory.createAuthenticationManager();
    }
}
~~~

**Giải thích từng phần:**

1. `DefaultSpringSecurityContextSource` thiết lập LDAP server và base DN; service account phục vụ tìm entry và, nếu cần, đọc thuộc tính password.
2. `setUserSearchBase("ou=people")` giới hạn khu vực tìm tài khoản; `setUserSearchFilter("(uid={0})")` dùng username làm biến trong filter, tránh tự ghép chuỗi LDAP filter từ input.
3. `setPasswordAttribute("userPassword")` chỉ rõ thuộc tính chứa dữ liệu mật khẩu; mặc định của factory cũng là `userPassword`.
4. `new BCryptPasswordEncoder()` phù hợp **chỉ khi** giá trị lưu tương thích với bcrypt. Với password comparison dựa trên hash đọc được, ứng dụng dùng logic đối chiếu tương ứng; không suy ra rằng LDAP server đang dùng bcrypt chỉ từ tên attribute.
5. Factory trả về `AuthenticationManager` tích hợp LDAP cho luồng username/password. **Việc xác thực account thành công không chứng minh đã kiểm tra hết các trạng thái tài khoản**.

Nếu dự án đã có `SecurityFilterChain`, cấu hình form login hoặc HTTP Basic phù hợp với ứng dụng; ví dụ tối thiểu:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests ->
                        requests.anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Các lớp được đặt trong package con của package chứa `@SpringBootApplication` để Spring quét được. Ví dụ đăng nhập qua giao diện mặc định không có stdout cố định; kết quả phụ thuộc account và directory thực tế. **Không đưa `AuthenticationManager` so sánh LDAP và một provider AD khác vào cùng ví dụ mà chưa thiết kế rõ thứ tự và phạm vi các provider.**

### 6.4. Vì sao dùng bcrypt không có nghĩa là LDAP Compare từ xa?

Ví dụ Java chạy trong dự án có `spring-security-crypto` (đã có qua starter-security), file `PasswordEncoderCheck.java`:

~~~java
package com.example.security;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

public final class PasswordEncoderCheck {
    public static void main(String[] args) {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
        String storedHash = encoder.encode("demo-password");

        System.out.println(encoder.matches("demo-password", storedHash));
        System.out.println(encoder.matches("wrong-password", storedHash));
    }
}
~~~

Output khi chạy `main` bằng IDE hoặc classpath của dự án:

~~~text
true
false
~~~

`encode` tạo salt ngẫu nhiên nên chuỗi hash khác nhau giữa các lần chạy; `matches` vẫn đúng vì đối chiếu với **hash đã lưu**. Đây là **local comparison**, không phải phép LDAP Compare remote. Trong hệ thống thực, không hardcode mật khẩu vào source hoặc log ra hash.

### 6.5. Khi nào cần cấu hình LDAP Compare đơn giản?

Spring Security còn mô tả cách tạo factory bằng `NoOpPasswordEncoder.getInstance()` để minh họa phép so sánh với directory có giá trị phù hợp:

~~~java
var factory = new LdapPasswordComparisonAuthenticationManagerFactory(
        contextSource, NoOpPasswordEncoder.getInstance());
factory.setUserDnPatterns("uid={0},ou=people");
AuthenticationManager manager = factory.createAuthenticationManager();
~~~

Đoạn mã **chỉ minh họa API**, sử dụng trong môi trường học tập có server phù hợp. `NoOpPasswordEncoder` không hash mật khẩu; không dùng nó để thiết kế nơi lưu mật khẩu mới hoặc thay thế chính sách bảo vệ mật khẩu production. Muốn chạy đoạn này cần import `AuthenticationManager`, `LdapPasswordComparisonAuthenticationManagerFactory`, `NoOpPasswordEncoder` và có sẵn `contextSource`; không phải chương trình Java độc lập.

## 7. Khi chuyển sang bind hoặc Active Directory

### LDAP thông thường: đổi sang bind

Nếu không được quyền đọc hash, hoặc cần để chính directory kiểm tra mật khẩu, thay bean `AuthenticationManager` phía trên bằng **một trong các cấu hình bind**:

~~~java
@Bean
AuthenticationManager ldapAuthenticationManager(
        BaseLdapPathContextSource contextSource) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
~~~

Thêm import `org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory`. Ví dụ dùng chung bean `ldapContextSource` đã cấu hình. Bind có thể xác thực account ngay cả khi không cho ứng dụng đọc `userPassword`.

### Active Directory DS: dùng provider chuyên biệt

~~~java
@Bean
ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
            "corp.example.org",
            "ldaps://dc1.corp.example.org:636/");
}
~~~

Import `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. Đây là **đoạn thay thế cho lựa chọn LDAP compare**, cần tích hợp vào security config đúng ngữ cảnh. AD thường nhận `user@domain`/UPN và quản lý mật khẩu theo cách riêng. Theo tài liệu Microsoft, `unicodePwd` **không thể đọc qua LDAP search**, nên cách “đọc hash từ AD rồi gọi `PasswordEncoder.matches`” không phải đường tích hợp hợp lệ. AD provider dựa trên thao tác xác thực với domain controller; cấu hình TLS, tên domain, chứng chỉ và quyền truy cập vẫn phải đúng.

## 8. Security checklist trước khi đưa vào production

- **Transport:** LDAPS/StartTLS, validate trust chain và hostname; không truyền mật khẩu trên `ldap://` không được bảo vệ. Kiểm tra kết nối tới từng domain controller/LDAP replica.
- **Least privilege:** service account chỉ có quyền tìm/compare hoặc đọc thuộc tính thực sự cần thiết; tuyệt đối không cấp quyền sửa mật khẩu cho ứng dụng chỉ để xác thực.
- **Password storage:** directory quản lý hash, salt, rotation và cơ chế truy cập; không bật plaintext chỉ để làm LDAP Compare chạy được.
- **Account policy:** xác nhận khóa tài khoản, trạng thái `disabled`, mật khẩu hết hạn, `must change password`, hạn chế giờ/thiết bị nếu có; với local compare rất dễ bỏ sót. Không tự xem compare true là “được đăng nhập” khi policy yêu cầu thêm.
- **Input & errors:** dùng search filter có placeholder/escaping thích hợp; ngăn LDAP filter injection; không trả khác biệt chi tiết giữa sai username và sai password cho client.
- **Throttling & logging:** giới hạn retry, quan sát lỗi kết nối/latency; không ghi log raw password, hash, `Authorization` header hay LDAP bind credentials.
- **Tách xác thực và phân quyền:** sau khi xác thực, ánh xạ LDAP groups/AD groups sang `GrantedAuthority` theo rule đã duyệt, không suy role từ tên tài khoản.
- **Bảo trì:** timeout, connection pooling phù hợp với cơ chế bind, HA/failover và chính sách khi directory lỗi; không “cho qua” xác thực vì timeout.

## 9. Test matrix cần xác nhận với LDAP/AD thật

| Tình huống | Kỳ vọng |
|---|---|
| User tồn tại, mật khẩu đúng, account hợp lệ | Xác thực thành công; roles đúng theo groups |
| Mật khẩu sai | Từ chối; không lộ mật khẩu hay chi tiết account |
| Username không tồn tại / filter không match | Từ chối; không lấy nhầm entry |
| User ở ngoài search base, hoặc có nhiều entry match | Xử lý xác định; không chọn nhầm người |
| Service account không được đọc/compare password | Thất bại rõ ràng ở server/log an toàn; không fallback thiếu kiểm soát |
| Stored hash không tương thích encoder hoặc có prefix khác | Xác thực thất bại; sửa cơ chế/format, không thay bằng NoOp |
| Account bị disable, locked, password expired | Hành vi đúng policy đã thống nhất; test riêng cho từng chiến lược |
| LDAP server/CA/DNS không sẵn sàng | Fail closed, có timeout và giám sát; không bỏ qua xác thực |
| Sai mật khẩu liên tiếp | Rate limit và lockout hoạt động theo yêu cầu thực tế |
| AD account dùng UPN/domain | Bind với provider AD thành công nếu credential và policy hợp lệ |

**Kỹ thuật test:** chuẩn bị một directory thử nghiệm với các tài khoản và trạng thái nêu trên; kiểm tra `AuthenticationManager.authenticate(...)` hoặc đăng nhập qua endpoint; xác nhận cả kết quả HTTP, `Authentication`, `GrantedAuthority`, log an toàn và audit phía directory. Không dùng output hash ngẫu nhiên làm giá trị cố định trong assertion.

## 10. Lỗi phổ biến và cách chẩn đoán

1. **`BadCredentialsException` dù password đúng:** kiểm tra base DN, `userSearchBase`, `userSearchFilter`, thuộc tính `uid`/`sAMAccountName`, prefix/hash format và chiến lược đang dùng. Với LDAP Compare, kiểm tra directory có thật sự hỗ trợ compare attribute.
2. **Thiếu quyền đọc attribute:** remote compare có thể dùng quyền khác local compare; cấp đúng quyền tối thiểu hoặc chuyển sang bind, không mở rộng quyền admin tùy tiện.
3. **Stored `{SSHA}` nhưng dùng bcrypt hoặc NoOp:** không tương thích. Hash có salt ngẫu nhiên cần bộ so sánh đọc được stored hash và hiểu format; đừng so sánh chuỗi hash do encode lại.
4. **AD không có `userPassword` để đọc:** đây là giới hạn thiết kế/permission, không phải bug Spring Security; dùng AD bind.
5. **LDAP qua TLS báo handshake failure:** kiểm tra CA, SAN/hostname, chain, phiên bản TLS, cấu hình truststore thay vì tắt xác minh chứng chỉ.
6. **Password đúng nhưng account disabled/locked vẫn đi qua:** password comparison không mặc nhiên thay thế login policy; bổ sung kiểm soát chính thức hoặc đổi sang bind.
7. **Đăng nhập đúng nhưng nhận 403:** xác thực có thể thành công nhưng phân quyền/group mapping sai; kiểm tra `LdapAuthoritiesPopulator` và rule `authorizeHttpRequests`.

## 11. Ghi nhớ

- **Password comparison ≠ bind:** compare đối chiếu một thuộc tính; bind yêu cầu directory đăng nhập bằng credential người dùng.
- **Server-side compare ≠ local hash verification:** bên nào đọc stored hash, bên nào thực hiện so khớp và thuật toán/hash format tạo ra các điều kiện bảo mật khác nhau.
- **AD thường dùng bind:** không tìm cách đọc `unicodePwd` hoặc tái tạo mật khẩu AD bằng `PasswordEncoder`.
- **Ưu tiên chính sách danh tính của directory:** chỉ chọn compare khi đã xác nhận cơ chế, quyền, thuật toán, bảo vệ kết nối và trạng thái account bằng kiểm thử.

## Tài liệu tham khảo

- [Spring Security 6.5 — LDAP Authentication: Bind, Password Comparison, Active Directory](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security API — LdapPasswordComparisonAuthenticationManagerFactory](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/ldap/LdapPasswordComparisonAuthenticationManagerFactory.html)
- [Spring Security — Password Storage / BCryptPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Microsoft Learn — Change Windows Active Directory and LDS user password through LDAP](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/change-windows-active-directory-user-password)
