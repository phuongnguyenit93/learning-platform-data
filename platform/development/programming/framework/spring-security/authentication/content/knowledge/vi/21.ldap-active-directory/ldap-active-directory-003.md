# Xác thực bằng bind với bằng chứng của người dùng (LDAP và Active Directory)

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích LDAP `bind` dùng tên đăng nhập và mật khẩu của chính người dùng để xác thực như thế nào; phân biệt việc **tìm DN** với việc **kiểm tra mật khẩu**; chọn giữa `userDnPatterns` và `userSearchFilter` trong Spring Security; cấu hình một luồng đăng nhập bằng bind; và xử lý các rủi ro bảo mật, lỗi thường gặp khi làm việc với LDAP/Active Directory (AD).

## 1. Bind với thông tin đăng nhập của người dùng là gì?

LDAP (Lightweight Directory Access Protocol) cho phép ứng dụng tìm và truy cập các bản ghi trong dịch vụ thư mục. Một bản ghi người dùng có **Distinguished Name (DN)** duy nhất theo cấu trúc cây thư mục. Ví dụ:

```text
uid=lan,ou=people,dc=example,dc=org
└─ uid=lan       : bản ghi người dùng
   ou=people     : đơn vị chứa người dùng
   dc=example,dc=org : base DN của thư mục
```

Trong **simple bind với bằng chứng của người dùng**, ứng dụng gửi danh tính dùng để bind (thường là DN; với AD có thể là tên dạng `user@domain`) cùng **mật khẩu vừa nhận từ người dùng** đến LDAP server qua kết nối đã được bảo vệ bằng TLS. **Máy chủ LDAP**, theo dữ liệu và chính sách tài khoản của nó, quyết định thông tin đó có hợp lệ hay không. Ứng dụng chỉ dựa trên kết quả thành công/thất bại, không cần đọc `userPassword`, lấy hash mật khẩu hay tự so khớp mật khẩu trong Java.

Ở đây, “bằng chứng của người dùng” là **credentials** mà người dùng trình cho phiên đăng nhập, điển hình là username/password. Không nhầm với một token OAuth2, kết quả tìm thấy user, hay mật khẩu của tài khoản kỹ thuật. LDAP bind không tự tạo cơ chế MFA và không thay thế các cơ chế đăng nhập liên kết như OIDC/SAML.

Phân biệt ba đối tượng:

- **Tên đăng nhập**: ví dụ `lan`; là giá trị biểu mẫu người dùng nhập, chưa nhất thiết là DN.
- **DN**: ví dụ `uid=lan,ou=people,dc=example,dc=org`; định danh vị trí bản ghi trong LDAP.
- **User credentials**: username/password gửi từ phía đăng nhập, dùng trong lần bind của **chính tài khoản đó**. Một service account dùng để tìm kiếm thư mục, nếu có, không chứng minh mật khẩu của người dùng.

Ví dụ: LDAP có user `uid=lan,ou=people,dc=example,dc=org` với mật khẩu bí mật. Nếu bind bằng DN đó và đúng mật khẩu, server chấp nhận; nếu mật khẩu sai, server từ chối. Ứng dụng **không nhận lại mật khẩu đúng** từ LDAP.

## 2. Luồng xác thực từ ứng dụng đến LDAP

```text
Người dùng
   │ 1. Gửi username + password qua HTTPS
   ▼
Spring Security (AuthenticationManager / LDAP provider)
   │ 2. Xác định DN: DN pattern hoặc tìm user theo filter
   │ 3. Mở kết nối LDAP bảo mật rồi bind bằng DN + password của user
   ▼
LDAP/AD server
   │ 4. Kiểm tra mật khẩu + trạng thái/chính sách tài khoản
   ├── Từ chối ──> AuthenticationException ──> đăng nhập thất bại
   └── Chấp nhận
           │ 5. Có thể đọc thuộc tính và xác định nhóm/authorities
           ▼
Spring Security tạo Authentication thành công
           │ 6. SecurityContext chứa principal + authorities
           ▼
Ứng dụng áp dụng quy tắc ủy quyền cho request tiếp theo
```

**Điểm quyết định thành công** là bước bind bằng credentials của người dùng. Tìm được bản ghi LDAP ở bước 2 **chưa phải** xác thực. Ngược lại, bind thành công chỉ trả lời “người này đã được xác thực”; truy cập `/admin` hay một API cụ thể còn phụ thuộc **authorization** (roles/authorities và chính sách của ứng dụng).

Spring Security dùng `LdapAuthenticator` (thường là `BindAuthenticator`) cho cơ chế này. Nó không dùng `UserDetailsService` để đọc mật khẩu LDAP rồi so sánh. Sau xác thực, `LdapAuthoritiesPopulator` có thể lấy thông tin nhóm và chuyển thành authorities; bước này là riêng biệt.

### Kết quả điển hình

| Tình huống | Bind LDAP | Hệ quả trong ứng dụng |
|---|---|---|
| DN đúng, mật khẩu đúng, tài khoản được phép đăng nhập | Thành công | Có thể tạo `Authentication` đã xác thực; áp dụng quyền truy cập |
| Mật khẩu sai | Bị từ chối | Đăng nhập thất bại; không tạo phiên xác thực hợp lệ |
| Không tìm ra user hoặc DN sai | Không bind được đúng user | Đăng nhập thất bại |
| Tài khoản bị khóa/hết hạn/bị vô hiệu hóa | Theo chính sách của server, thường bị từ chối | Đăng nhập thất bại; không nên tiết lộ nguyên nhân chi tiết cho người lạ |
| LDAP server/TLS không sẵn sàng | Không thể xác thực đáng tin | **Fail closed**: từ chối đăng nhập, không chuyển sang bỏ qua kiểm tra |

## 3. Chuyển username thành danh tính dùng để bind

### 3.1. DN pattern: khi vị trí user dự đoán được

Giả sử mọi người dùng ở dưới `ou=people,dc=example,dc=org` và thuộc tính định danh là `uid`. Spring Security có thể dùng pattern:

```text
userDnPatterns = "uid={0},ou=people"
username       = "lan"
LDAP base DN   = "dc=example,dc=org"
DN cuối cùng   = "uid=lan,ou=people,dc=example,dc=org"
```

`{0}` là chỗ Spring Security thay username. Cách này nhanh, ít bước và không cần dò cây thư mục. Nó **không phù hợp** nếu người dùng nằm ở nhiều OU, nếu DN dùng `cn` khác username, hoặc người dùng có thể đổi vị trí trong AD.

### 3.2. Search-then-bind: khi DN không biết trước

Nếu người dùng nằm ở nhiều OU, ứng dụng cần **tìm bản ghi trước, bind sau**:

1. Tìm từ `userSearchBase` bằng `userSearchFilter`, chẳng hạn `(uid={0})`, trong base DN đã cấu hình.
2. Lấy DN của bản ghi duy nhất phù hợp.
3. Bind với **mật khẩu của người dùng**, bằng DN vừa tìm được.
4. Chỉ sau khi bind thành công mới công nhận đăng nhập.

Ví dụ: search base `ou=people` + filter `(uid=lan)`, xét dưới base DN `dc=example,dc=org`. Kết quả có thể là `uid=lan,ou=developers,ou=people,dc=example,dc=org`, sau đó ứng dụng dùng DN đó để bind.

Thao tác **search** có thể cần một danh tính đọc thư mục với quyền hạn tối thiểu (search account) nếu thư mục cấm anonymous search. Account này chỉ phục vụ tra cứu; nó không thay thế việc bind bằng credentials của người dùng. Nếu tìm thấy 0 hoặc nhiều bản ghi không thể phân biệt an toàn, không được chọn tùy tiện rồi công nhận đăng nhập.

### 3.3. Active Directory: định danh đăng nhập có thể là UPN

AD thường chấp nhận **User Principal Name (UPN)** như `lan@corp.example.org`, bên cạnh cấu trúc DN. Spring Security có `ActiveDirectoryLdapAuthenticationProvider` để xử lý mô hình AD phổ biến. Cần phân biệt tên domain/UPN với DN thật của user; **không mặc định** LDAP thuần và AD có cùng schema, quy tắc tìm kiếm nhóm hay mã lỗi.

| Cách | Phù hợp khi | Điều cần chú ý |
|---|---|---|
| DN pattern + user bind | Cấu trúc DN ổn định, cùng OU | DN pattern phải đúng schema |
| Search user rồi user bind | Nhiều OU, DN không suy ra được | Phạm vi search, filter, quyền đọc và kết quả duy nhất |
| AD provider + UPN bind | Active Directory của doanh nghiệp | Domain/UPN, TLS, chính sách account và mapping nhóm AD |

## 4. Cấu hình Spring Security bằng Java 17+ và Spring Boot 3.x

Ví dụ dưới đây là **cấu hình ứng dụng Spring Boot**, không phải một file Java có thể chạy độc lập bằng `javac`. Nó dùng **Spring Security 6.x** và một LDAP server đã tồn tại, với dữ liệu người dùng theo cấu trúc `uid=...,ou=people,dc=example,dc=org`. Thay package, URL, DN pattern theo hệ thống thực tế. Spring Boot quản lý version của các dependency tương ứng.

### 4.1. Dependency Gradle

Trong dự án đã có plugin Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation 'org.springframework.security:spring-security-ldap'
}
```

`spring-security-ldap` cung cấp LDAP authentication provider và factory. Starter LDAP cung cấp phần tích hợp Spring LDAP. Không cần `PasswordEncoder` của ứng dụng để tự kiểm tra mật khẩu trong **bind authentication**.

### 4.2. Kết nối đến LDAP qua TLS

`src/main/resources/application.yml`:

```yaml
app:
  ldap:
    provider-url: "${LDAP_PROVIDER_URL:ldaps://ldap.example.org:636/dc=example,dc=org}"
```

Ví dụ URL gồm `ldaps://host:636/` và **base DN** `dc=example,dc=org`. Với cấu trúc khác, phải thay phần base DN cho khớp directory. Giá trị môi trường `LDAP_PROVIDER_URL` nên do hạ tầng cung cấp; chứng thư của máy chủ LDAP phải được JVM tin cậy và hostname phải khớp chứng thư. Không tắt kiểm tra TLS để “sửa” lỗi kết nối.

### 4.3. Cấu hình bind bằng DN pattern

Tạo `src/main/java/com/example/security/LdapSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LdapSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContextSource(
            @Value("${app.ldap.provider-url}") String providerUrl) {
        return new DefaultSpringSecurityContextSource(providerUrl);
    }

    @Bean
    AuthenticationManager authenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager authenticationManager)
            throws Exception {
        http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Giải thích theo luồng thực thi:**

1. `ldapContextSource` định nghĩa server và base DN cho LDAP connection. Ở ví dụ này URL đã có base DN; đừng nối base DN lần thứ hai.
2. `LdapBindAuthenticationManagerFactory` tạo `AuthenticationManager` dùng bind. `setUserDnPatterns("uid={0},ou=people")` xác định DN tương đối dưới base DN.
3. `HttpSecurity.authenticationManager(...)` đưa manager đó vào luồng xử lý đăng nhập HTTP. `formLogin` cung cấp form đăng nhập mặc định và xử lý thành công/thất bại theo cơ chế Spring Security.
4. `anyRequest().authenticated()` yêu cầu có danh tính đã đăng nhập. Nó **không** tự đòi vai trò `ROLE_ADMIN`.
5. Bean `SecurityFilterChain` không biến những endpoint khác thành public; muốn giới hạn quyền chi tiết cần bổ sung authorization rules.

**Để chạy:** dùng một Spring Boot application có `@SpringBootApplication`, cấu hình LDAP server tương ứng, đặt biến môi trường nếu URL khác ví dụ và chạy `./gradlew bootRun` (hoặc `gradlew.bat bootRun` trên Windows). Truy cập một trang cần xác thực sẽ dẫn đến trang login; nhập tài khoản có thật trong directory để kiểm thử. Không thể bảo đảm đầu ra HTTP cố định khi chưa có server, dữ liệu LDAP và cấu hình ứng dụng thực tế.

### 4.4. Đổi sang tìm user rồi bind

Nếu DN user không theo một pattern cố định, **thay** method `authenticationManager` ở trên bằng:

```java
@Bean
AuthenticationManager authenticationManager(
        BaseLdapPathContextSource contextSource) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
```

Đây là **đoạn thay thế bên trong cùng class** (giữ imports ở ví dụ đầy đủ); không khai báo hai bean cùng tên. `setUserSearchBase` là DN tương đối so với root của `ContextSource`. Không nối trực tiếp username vào một chuỗi LDAP filter tự xây dựng; dùng tham số/filter escaping đúng ngữ cảnh để hạn chế LDAP injection. Nếu thư mục cần tài khoản đọc chuyên dụng để search, cấu hình credentials bảo mật và quyền tối thiểu cho context dùng tra cứu, vẫn phải xác thực user bằng bind riêng.

### 4.5. Khi directory là Active Directory

Ví dụ **độc lập về lựa chọn provider** (không dùng đồng thời với manager LDAP thường ở trên chỉ để mô tả cùng một flow):

```java
@Bean
ActiveDirectoryLdapAuthenticationProvider adAuthenticationProvider() {
    return new ActiveDirectoryLdapAuthenticationProvider(
        "corp.example.org",
        "ldaps://dc1.corp.example.org:636/");
}
```

Import class `org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider`. Đăng ký provider này vào `HttpSecurity`/`AuthenticationManager` của ứng dụng nếu chọn nhánh AD. UPN thường ở dạng `lan@corp.example.org`. Đừng sao chép DN pattern `uid=...` của OpenLDAP sang AD khi schema/OU thực tế khác; hãy xác minh search filter, domain và nhóm trên AD đang sử dụng. Ví dụ AD bên trên là một **bean minh họa**, không phải một ứng dụng Spring Boot hoàn chỉnh thứ hai.

## 5. Xác thực thành công rồi lấy quyền (authorization)

Một user có thể bind thành công nhưng không có `ROLE_ADMIN`. Để ánh xạ LDAP group thành Spring Security authorities, dùng `LdapAuthoritiesPopulator`; mẫu sau sử dụng nhóm dạng `groupOfNames` với thuộc tính `member` chứa DN của thành viên:

```java
@Bean
LdapAuthoritiesPopulator ldapAuthorities(
        BaseLdapPathContextSource contextSource) {
    var populator =
        new DefaultLdapAuthoritiesPopulator(contextSource, "ou=groups");
    populator.setGroupSearchFilter("(member={0})");
    populator.setGroupRoleAttribute("cn");
    return populator;
}

@Bean
AuthenticationManager authenticationManager(
        BaseLdapPathContextSource contextSource,
        LdapAuthoritiesPopulator authorities) {
    var factory = new LdapBindAuthenticationManagerFactory(contextSource);
    factory.setUserDnPatterns("uid={0},ou=people");
    factory.setLdapAuthoritiesPopulator(authorities);
    return factory.createAuthenticationManager();
}
```

Imports bổ sung: `org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator` và `org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator`. **Thay thế** bean `authenticationManager` của phần 4.3 nếu áp dụng đoạn này. Với group search base `ou=groups`, ứng dụng tìm nhóm dưới `ou=groups,dc=example,dc=org`. Thuộc tính `cn` được chọn làm tên role; quy tắc thêm prefix `ROLE_` và viết hoa cần kiểm tra theo cấu hình của `DefaultLdapAuthoritiesPopulator`, không mặc định mọi nhóm sẽ cho ra đúng role ứng dụng cần.

Nếu thư mục yêu cầu quyền đọc nhóm riêng, cần giải quyết quyền truy vấn an toàn; đừng bỏ qua kiểm tra authorization khi truy vấn nhóm thất bại. AD dùng `memberOf`, các kiểu group/nested group và quy tắc ánh xạ khác với ví dụ OpenLDAP này. Thiết kế quyền ứng dụng theo nguyên tắc tối thiểu, và kiểm tra đúng nguồn group được phê duyệt.

## 6. Kiểm thử và quan sát lỗi

Có thể kiểm tra khả năng bind độc lập trước bằng lệnh trên máy có công cụ OpenLDAP và tin cậy chứng thư LDAP:

```bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D 'uid=lan,ou=people,dc=example,dc=org' \
  -W
```

`-x` yêu cầu simple authentication; `-D` là bind DN, `-W` yêu cầu nhập mật khẩu tương tác (không đưa mật khẩu lên command line). Với credentials đúng, lệnh trả về định danh được server xác nhận; định dạng phản hồi tùy máy chủ. Không chạy lại lệnh với `-w <password>` trong shell history của môi trường thật.

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Username/password đúng | LDAP bind thành công; Spring Security xác thực request sau login |
| Password sai | LDAP từ chối; phiên chưa được xác thực |
| Password rỗng hoặc chỉ không có password | Từ chối trước khi chấp nhận bind; không coi anonymous/unauthenticated bind là thành công |
| User không tồn tại / DN pattern sai | Xác thực thất bại; cần phân biệt cấu hình sai với tài khoản không tồn tại qua log nội bộ |
| User ở OU khác | DN pattern có thể thất bại, search-then-bind có thể giải quyết nếu filter/base đúng |
| Tài khoản AD khóa/hết hạn | Kết quả phụ thuộc AD policy; luồng ứng dụng phải từ chối |
| Không đọc được nhóm | Xác thực danh tính có thể thành công nhưng không được tự nâng quyền |
| TLS certificate sai / server ngắt kết nối | Từ chối đăng nhập và cảnh báo vận hành, không fallback sang LDAP plaintext |
| User input chứa ký tự đặc biệt trong filter/DN | Không làm thay đổi cú pháp truy vấn ngoài ý định; kiểm thử trường hợp LDAP injection |

Khi gỡ lỗi, theo thứ tự: **kết nối TLS và DNS** → **base DN** → **DN pattern hoặc search base/filter** → **lỗi bind và trạng thái account** → **mapping groups/authorities** → **quy tắc HTTP access**. Ví dụ lỗi LDAP `invalidCredentials` có thể đến từ mật khẩu sai hoặc chính sách xác thực phía directory; không suy đoán tất cả lỗi là “mật khẩu sai”. Log tối thiểu mã lỗi, thời gian, loại thao tác và correlation ID; không ghi mật khẩu, cookie/session token, secret của service account, hay toàn bộ dữ liệu nhạy cảm của bản ghi LDAP.

## 7. Những yêu cầu bảo mật không thể bỏ qua

1. **Bảo vệ kênh truyền:** form người dùng tới ứng dụng qua HTTPS; ứng dụng tới directory dùng **LDAPS** hoặc **StartTLS được cấu hình và kiểm thử đúng**. Kiểm tra chứng thư CA và tên máy chủ. Không gửi simple-bind password qua `ldap://` không mã hóa trong môi trường thật.
2. **Từ chối password trống:** RFC 4513 có “unauthenticated bind”, nơi DN không rỗng + password rỗng có thể được server xử lý như truy cập anonymous. Tuyệt đối không coi việc server cho phép thao tác đó là bằng chứng user đã đăng nhập. Framework/phần thư viện phải được cập nhật bản vá; kiểm thử explicit. Spring LDAP có cảnh báo **CVE-2026-41720 (08/06/2026)** về trường hợp liên quan ở một số phiên bản thư viện.
3. **Không tự đọc hay lưu mật khẩu LDAP:** bind trả trạng thái xác thực; không lưu password plaintext vào DB/session/log và không gửi nó đến dịch vụ khác. Việc server nhận password qua TLS để kiểm tra là bản chất của simple bind.
4. **Chống LDAP injection:** username không được ghép tự do vào DN hoặc filter; phân biệt escaping của **DN** (RFC 4514) và **filter** (RFC 4515). Dùng cơ chế chèn tham số của framework và giới hạn giá trị đầu vào khi phù hợp.
5. **Least privilege:** tài khoản tìm kiếm kỹ thuật, nếu dùng, chỉ có quyền đọc các thuộc tính thực sự cần; bind tài khoản người dùng được kiểm soát theo LDAP policy. Không cấp quyền quản trị ứng dụng chỉ vì bind thành công.
6. **Chống dò mật khẩu:** thực hiện rate limit, backoff/lockout phù hợp với chính sách directory, giám sát số lần đăng nhập lỗi. Tránh tạo thêm khóa tài khoản hàng loạt ngoài ý muốn do retry quá mức.
7. **Fail closed và giới hạn thời gian:** cấu hình timeout/tài nguyên kết nối và kiểm tra khả năng phục hồi directory; khi LDAP không phản hồi, không dùng “authenticated=true” mặc định hoặc bỏ qua bước bind.
8. **Xử lý lỗi an toàn:** thông báo cho client kiểu “Thông tin đăng nhập không hợp lệ”, giữ chi tiết account disabled/locked/expired trong kênh vận hành hạn chế. Không lộ khả năng liệt kê username.
9. **Kiểm soát session:** bind chỉ là thời điểm xác minh credentials. Khi tài khoản bị thu hồi sau khi đã đăng nhập, session cũ không tự bị hủy ngay trừ khi ứng dụng có chính sách session/revalidation phù hợp.

## 8. Các nhầm lẫn thường gặp và cách sửa

- **“Tìm thấy user trong LDAP tức là đăng nhập thành công.”** Sai. Search chỉ trả về bản ghi; vẫn cần bind của user bằng password hợp lệ.
- **“Kết nối bằng service account là xác thực được tất cả user.”** Sai. Service account chỉ có danh tính của chính nó; nó không chứng minh password của người dùng.
- **“Spring Security phải lấy `userPassword` để so sánh.”** Sai với bind. LDAP server kiểm tra secret; ứng dụng không cần biết giá trị hash mật khẩu.
- **“Dùng `uid={0},ou=people` là chạy cho mọi AD.”** Sai. AD thường dùng UPN, `sAMAccountName`, DN hoặc OU khác; chọn strategy dựa trên schema thực.
- **“Đăng nhập thành công đồng nghĩa có quyền admin.”** Sai. Bind là authentication; role/group là authorization data phải map và đánh giá riêng.
- **“LDAP server trả success với password rỗng là đủ an toàn.”** Sai: phải từ chối unauthenticated bind và giữ thư viện đã vá.
- **“Có LDAPS là khỏi cần chống LDAP injection.”** Sai. TLS bảo vệ dữ liệu trên đường truyền, không làm sạch filter hay DN do ứng dụng xây dựng.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Vì sao search-then-bind không được coi là authenticated sau khi search trả về DN?  
**Đáp án:** Search xác định user entry; chỉ bind bằng bằng chứng do người dùng cung cấp mới kiểm tra được credential.

**Câu 2.** Khi user nằm ở nhiều OU, nên thay đổi cấu hình thế nào?  
**Đáp án:** Dùng `setUserSearchBase` và `setUserSearchFilter` để tìm đúng DN, rồi bind như cũ. Giới hạn search scope và bảo đảm filter an toàn.

**Câu 3.** Có thể dùng `hasRole("ADMIN")` chỉ vì LDAP bind thành công không?  
**Đáp án:** Không. Phải lấy và ánh xạ nhóm/authorities đúng chính sách, sau đó mới áp dụng authorization.

**Câu 4.** Vì sao password rỗng phải bị chặn ngay cả khi server trả “bind success”?  
**Đáp án:** LDAP có thể cho phép unauthenticated/anonymous bind; thành công kiểu đó không chứng minh danh tính hay mật khẩu của user.

## Tài liệu tham khảo

- [Spring Security — LDAP Authentication (6.5)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html): bind, search+bind, authorities, AD provider.
- [Spring Security — LDAP Authentication (7.0)](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passwords/ldap.html): đối chiếu khái niệm trên nhánh framework mới hơn.
- [OWASP — LDAP Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html): escaping, least privilege, chống unauthenticated bind.
- [Spring — CVE-2026-41720](https://spring.io/security/cve-2026-41720/): thông tin các phiên bản Spring LDAP bị ảnh hưởng và bản vá cho trường hợp empty-password bind.
