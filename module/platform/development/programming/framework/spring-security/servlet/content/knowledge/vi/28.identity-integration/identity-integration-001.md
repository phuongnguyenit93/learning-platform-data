# Lựa chọn tích hợp LDAP, chứng thư, hệ thống đăng nhập tập trung hoặc container

> **Bối cảnh:** Ứng dụng Java 17+ dùng **Spring Security trên Servlet stack**. Khi cần tích hợp danh tính doanh nghiệp, việc chọn LDAP, chứng thư X.509, đăng nhập tập trung (SSO) hay cơ chế xác thực do Servlet container quản lý không chỉ là chọn một API: mỗi phương án đặt ranh giới tin cậy, vòng đời phiên, mô hình phân quyền và trách nhiệm vận hành ở một nơi khác nhau.

## 1. Bắt đầu từ câu hỏi kiến trúc, không bắt đầu từ một filter

Có bốn khái niệm cần tách rõ:

- **Nguồn danh tính (identity store):** nơi quản lý người dùng, nhóm, trạng thái tài khoản và thuộc tính. LDAP/Active Directory thường đóng vai trò này.
- **Cơ chế xác thực (authentication):** cách kiểm chứng bằng chứng danh tính, chẳng hạn bind LDAP bằng mật khẩu, kiểm tra chứng thư client đã được TLS xác thực, hoặc kiểm tra phản hồi của Identity Provider (IdP).
- **Liên kết đăng nhập (federation / single sign-on):** ứng dụng tin vào quy trình xác thực của một IdP để người dùng không phải nhập mật khẩu tại từng ứng dụng. OIDC/SAML 2.0 là hai lựa chọn phổ biến.
- **Phân quyền (authorization):** ứng dụng quyết định principal nào được thực hiện hành động nào. Các nhóm LDAP, claim OIDC, thuộc tính SAML, thông tin chứng thư hoặc container role là **đầu vào**; chúng không thay thế chính sách quyền của ứng dụng.

Ví dụ một công ty vẫn lưu nhân viên trong Active Directory nhưng xây dựng SSO bằng IdP đọc AD. Ứng dụng Servlet lúc đó **không cần bind LDAP trực tiếp**; nó có thể dùng OIDC để đăng nhập, rồi ánh xạ danh tính/nhóm sang `GrantedAuthority`. LDAP và SSO vì vậy **không nhất thiết là hai lựa chọn loại trừ nhau**.

Trước khi chọn, hãy trả lời những câu hỏi sau:

1. Người dùng là **nhân viên trình duyệt**, **đối tác**, **thiết bị**, **dịch vụ tự động**, hay ứng dụng chạy trên **application server** đã xác thực sẵn?
2. Có IdP doanh nghiệp hỗ trợ **OIDC** hoặc **SAML 2.0** không? Có yêu cầu MFA, passkey, quản lý phiên tập trung, chính sách conditional access hay đăng xuất một lần không?
3. Ứng dụng có bắt buộc nhận mật khẩu trực tiếp hay có thể chuyển người dùng đến IdP?
4. Dữ liệu quyền nằm ở đâu, ai cập nhật, bao lâu cần thu hồi quyền và có cần đồng bộ nhóm từ directory?
5. TLS được kết thúc tại ứng dụng hay reverse proxy/load balancer? Có tin cậy đường truyền từ proxy đến Servlet container không?
6. Đây là ứng dụng Servlet render giao diện, API nhận bearer token, hay service-to-service? Chọn đúng cơ chế của Spring Security cho từng loại.
7. Khi IdP, LDAP hoặc hệ thống xác thực ngừng hoạt động, ứng dụng phải **fail closed** ra sao, có cần cho phép phiên đang tồn tại duy trì bao lâu và ai kiểm soát việc thu hồi?

Không trả lời các câu hỏi này mà chỉ bật `formLogin()`, `x509()` hoặc `jee()` thường dẫn đến cấu hình có vẻ chạy được nhưng ranh giới tin cậy chưa rõ.

## 2. Bảng so sánh bốn hướng tích hợp

| Tiêu chí | LDAP / Active Directory trực tiếp | Chứng thư X.509 (client certificate) | SSO qua IdP (OIDC / SAML 2.0) | Servlet container / pre-auth |
|---|---|---|---|---|
| Bằng chứng danh tính | Thường là username/password được kiểm tra bằng LDAP bind | Chứng thư client + chứng minh sở hữu private key trong TLS handshake | Assertion/token do IdP cấp sau quá trình đăng nhập | Principal đã được container/application server xác thực |
| Ai xử lý đăng nhập? | Ứng dụng nhận credential và tương tác directory | TLS endpoint xác minh certificate; ứng dụng ánh xạ principal | IdP xử lý login, MFA; ứng dụng kiểm tra kết quả hợp lệ | Container và realm/security domain quản lý |
| Phù hợp nhất | Ứng dụng nội bộ cần tương thích LDAP/AD nhưng chưa có IdP; tác vụ xác thực theo directory | Thiết bị, môi trường mTLS, một số ứng dụng có PKI/doanh nghiệp yêu cầu xác thực certificate | Trình duyệt doanh nghiệp, đa ứng dụng, MFA, quản lý đăng nhập tập trung | Ứng dụng Java EE/Jakarta EE legacy, môi trường container có realm đã quản lý |
| Vận hành phụ thuộc | Directory, kết nối LDAP(S), account/group schema | PKI/CA, cấp phát–gia hạn–thu hồi cert, TLS termination | IdP, metadata/discovery, signing keys, redirect URI, client registration | Container realm, role mapping, deployment và vùng tin cậy application server |
| Quyền ứng dụng | Nhóm LDAP cần ánh xạ sang authorities | Chứng thư xác định identity; quyền tra từ registry/directory | Claim/attribute cần xác minh issuer, audience và ánh xạ quyền | Container roles cần ánh xạ đúng sang Spring authorities |
| Rủi ro nổi bật | Ứng dụng xử lý password, LDAP injection/misconfiguration, TLS, lockout, stale group membership | Trust chain, cert hết hạn/thu hồi, mapping sai subject/SAN, proxy spoof | Token validation, account linking, redirect/state/nonce, session/logout, claim overtrust | Tin nhầm header từ client, container bypass, mapping lệch giữa ứng dụng và server |
| Có SSO mặc nhiên? | Không | Không theo mô hình federation thông thường | Có, tùy khả năng và chính sách IdP | Có thể có trong cùng miền container/realm, không mặc định liên thông toàn doanh nghiệp |

**Quy tắc chọn nhanh:**

- **Nhân viên dùng web, có IdP tốt:** ưu tiên **OIDC** cho ứng dụng mới (SAML 2.0 khi hệ sinh thái doanh nghiệp yêu cầu).
- **Directory là nguồn sự thật nhưng chưa có dịch vụ SSO:** có thể dùng LDAP bind trực tiếp với kết nối được bảo vệ; cân nhắc đưa IdP phía trước directory khi có điều kiện.
- **Thiết bị/khách hàng dùng mTLS hoặc yêu cầu xác minh certificate:** dùng X.509, đồng thời có cơ chế ánh xạ cert sang tài khoản/quyền; không coi mọi cert do CA phát hành là quản trị viên.
- **Ứng dụng vốn chạy trong server có container-managed security đáng tin:** cân nhắc tích hợp `jee()` để dùng principal/role sẵn có, nhưng chỉ khi container thực sự xác thực và ứng dụng không thể bị truy cập qua đường bypass.
- **API nhận access token:** thường dùng `oauth2ResourceServer()` để **xác thực bearer access token**, không dùng `oauth2Login()` thay cho bảo mật API. Đây là nhánh sử dụng khác, dù có chung IdP.

## 3. LDAP: xác thực trực tiếp với directory

### 3.1. Cơ chế và các vai trò

**LDAP (Lightweight Directory Access Protocol)** là giao thức truy vấn/cập nhật directory; bản thân LDAP không phải protocol SSO trình duyệt. Trong mô hình username/password quen thuộc:

```text
Browser → form login của ứng dụng Servlet
           ↓
Spring Security AuthenticationManager
           ↓
LDAP authenticator → LDAP directory
           ↓                     ↓
     user DN được tìm      bind bằng credential
           ↓
     xác thực thành công
           ↓
     lấy nhóm/thuộc tính, ánh xạ authorities
           ↓
     SecurityContext và HTTP session ứng dụng
```

Hai cách thường gặp:

- **Bind authentication:** ứng dụng tìm DN của user, rồi bind tới directory bằng password user để kiểm chứng; đây là lựa chọn phổ biến với LDAP/AD.
- **Password comparison:** một số directory/kiến trúc cho phép so sánh thuộc tính mật khẩu theo quy trình riêng, nhưng không nên giả định có thể đọc mật khẩu hoặc tự hash client-side. Chọn theo capability và chính sách thực tế của directory.

Ứng dụng có thể cần **tài khoản service với quyền tối thiểu** để tìm DN/đọc nhóm. Không dùng tài khoản quản trị directory cho các truy vấn thông thường. DN pattern, cấu trúc OU và schema nhóm không giống nhau giữa OpenLDAP và Active Directory; `uid`, `sAMAccountName`, `userPrincipalName` và `memberOf` không thể thay thế vô điều kiện.

**Bảo vệ đường truyền:** dùng `ldaps://` với TLS được xác thực hoặc LDAP StartTLS cấu hình đúng; không truyền mật khẩu qua LDAP plaintext. Kiểm tra trust store, tên máy chủ, timeout, referral và chính sách firewall. TLS mã hóa không có nghĩa xác thực người dùng hay phân quyền ứng dụng đã đúng.

### 3.2. Cấu hình minh họa với Spring Security 6

Với Spring Security Servlet, module `spring-security-ldap` cung cấp các thành phần như `LdapBindAuthenticationManagerFactory`. Sau đây là **mẫu cấu hình thành phần** cho hệ thống đã có directory; không thể chạy độc lập nếu thiếu Spring Boot app, dependency LDAP, host/base DN và cấu trúc directory tương ứng:

```java
// Các import cần thiết:
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
class LdapAuthConfiguration {
    @Bean
    BaseLdapPathContextSource ldapContextSource() throws Exception {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(System.getenv("LDAP_URL")); // ldaps://directory...
        source.setBase(System.getenv("LDAP_BASE_DN"));
        source.afterPropertiesSet();
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }
}
```

Ý nghĩa:

- `LDAP_URL`/`LDAP_BASE_DN` đến từ cấu hình bảo mật của môi trường và cần có giá trị hợp lệ khi chạy. `uid={0},ou=people` chỉ là **cấu trúc directory minh họa**, phải được thay bằng mô hình DN/search thật của tổ chức.
- Khi directory không cho phép suy ra user DN từ username, cần cấu hình **user search** thay vì DN pattern; nếu directory đòi service bind để tìm user, cấu hình credential theo secret manager.
- `AuthenticationManager` được tạo để tích hợp vào `HttpSecurity` của chuỗi xử lý login tương ứng. Chỉ tạo bean này không chứng minh mọi chain/form login đã sử dụng đúng manager; cần cấu hình và test wiring rõ ràng.
- Thực tế phải cấu hình **nhóm → `GrantedAuthority`**, phân quyền theo nguyên tắc ít quyền và xử lý user bị khóa/xóa; đừng tự tạo `ROLE_ADMIN` chỉ vì LDAP bind thành công.

Điểm kiểm thử quan trọng là một user thuộc nhóm ứng dụng hợp lệ nhận đúng quyền, user đã bị loại khỏi nhóm không giữ quyền quá lâu sau refresh/session re-auth, và directory không truy cập được thì không fallback thành anonymous-but-authorized.

### 3.3. Khi nào nên chọn hoặc tránh LDAP trực tiếp?

Chọn khi cần tích hợp với hạ tầng LDAP hiện có, ít ứng dụng, môi trường nội bộ kiểm soát tốt, hoặc không thể dùng SSO. Tránh chọn chỉ vì “user nằm trong AD” nếu doanh nghiệp đã cung cấp OIDC/SAML: đọc AD bằng LDAP không tự cung cấp MFA, account federation, quy trình single logout hoặc các chính sách đăng nhập tập trung.

Khi chuyển từ LDAP login sang SSO, nên giữ một **internal user ID** riêng, liên kết tài khoản trên cơ sở định danh ổn định có thể kiểm chứng; không ghép tài khoản chỉ từ email nếu email có thể đổi hoặc tái sử dụng.

## 4. X.509: nhận dạng qua chứng thư client và mTLS

### 4.1. Điểm kết thúc TLS quyết định ranh giới tin cậy

Đăng nhập bằng chứng thư X.509 thường dựa trên **mutual TLS (mTLS)**:

```text
Client có certificate + private key
                 |
          TLS handshake
                 |
TLS endpoint xác thực chain, thời hạn, mục đích, chính sách thu hồi
                 |
Servlet container nhận authenticated certificate / principal
                 |
Spring Security X.509 pre-auth nhận identity đã kiểm chứng
                 |
Ánh xạ identity → user/authorities của ứng dụng
                 |
Kiểm tra authorization trên endpoint
```

Khác với form login, ứng dụng không nhận mật khẩu mỗi lần đăng nhập; nhưng phải trả lời được **certificate nào được tin**, **issuer nào được chấp nhận**, **certificate hết hạn/thu hồi xử lý ra sao** và **chủ thể certificate tương ứng account nào**.

Có hai kiến trúc phổ biến:

1. **TLS kết thúc ở Servlet container:** container kiểm tra client certificate và truyền thông tin được xác thực cho các tầng phía trên. Spring Security có thể dùng `x509()` để ánh xạ principal.
2. **TLS kết thúc ở gateway/reverse proxy:** gateway kiểm tra certificate, rồi truyền kết quả đã xác thực cho upstream qua kênh tin cậy. Khi đó Spring Security **không được tin thẳng** bất kỳ header như `X-Client-Cert` do client tự đặt. Gateway phải xóa/ghi đè header đến từ client, xác thực nội bộ tới backend và định nghĩa rõ cách ứng dụng kiểm tra thông tin forwarded/pre-auth.

**Mấu chốt:** Việc một chuỗi header chứa subject DN hoặc PEM không chứng minh certificate được xác thực. Trust decision nằm ở TLS termination hoặc lớp kết nối đáng tin cậy.

### 4.2. Spring Security Servlet hỗ trợ X.509 như thế nào?

Một dạng cấu hình trong `SecurityFilterChain` đã có hạ tầng mTLS:

```java
// Đoạn cấu hình trong HttpSecurity, không phải class độc lập.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/secure/**").authenticated()
        .anyRequest().denyAll())
    .x509(x509 -> x509
        .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
        .userDetailsService(userDetailsService));
```

Ở đây `userDetailsService` phải do ứng dụng cung cấp và ánh xạ identity xác thực từ certificate sang account cùng roles phù hợp. Regex CN là **ví dụ đơn giản để học cách xử lý**; ứng dụng mới nên ưu tiên định danh rõ ràng, duy nhất và phù hợp chính sách PKI (thường ở Subject Alternative Name), tránh dựa mù quáng vào CN có thể trùng hoặc bị diễn giải sai.

Lớp `x509()` của Spring Security **không thay việc xác thực trust chain tại TLS endpoint**. Không coi một certificate hợp lệ với bất kỳ CA nào trong trust store là đủ để dùng mọi quyền.

### 4.3. Checklist PKI khi chọn chứng thư

- CA phát hành có đáng tin và chỉ phát chứng thư cho đúng nhóm đối tượng? Có tách CA cho người dùng, máy và dịch vụ không?
- Certificate có EKU/key usage phù hợp với **client authentication** không? Có kiểm tra chain và hostname/service policy khi cần?
- Private key được lưu trong phần cứng/keystore an toàn không? Có quy trình mất thiết bị, khóa tài khoản, gia hạn và luân chuyển certificate không?
- Có quy trình **revocation** bằng CRL/OCSP hoặc phương án bù trừ có chính sách rõ ràng không? Kiểm tra thời điểm xác thực và tình trạng mất kết nối tới nguồn revocation.
- Mỗi certificate map sang **một identity duy nhất**? Nếu một user đổi certificate, tài khoản và quyền có được giữ chính xác?
- Nếu proxy kết thúc TLS, client có thể gọi thẳng upstream bằng certificate header giả không? Proxy có xóa/ghi đè header đầu vào và bảo vệ kênh tới backend không?

Chứng thư đặc biệt hợp với **service/thiết bị** và môi trường assurance cao, nhưng triển khai cho tất cả browser người dùng có thể tạo chi phí cấp phát, hỗ trợ thiết bị và trải nghiệm lớn. Đừng nhầm **mTLS xác thực client** với **OIDC/SAML phiên đăng nhập người dùng**: hai cơ chế có thể bổ trợ nhau.

## 5. SSO: OIDC và SAML 2.0 cho ứng dụng doanh nghiệp

### 5.1. SSO giải bài toán gì?

Trong kiến trúc SSO, ứng dụng Servlet đóng vai trò **Relying Party / client** và ủy thác màn hình đăng nhập cho **Identity Provider**. IdP có thể tích hợp AD/LDAP ở phía sau, thực thi MFA, passkey, chính sách thiết bị và quản lý đăng nhập tập trung.

Với **OpenID Connect (OIDC)** trên OAuth 2.0 Authorization Code flow, luồng browser thường là:

```text
Browser → GET /me của ứng dụng
                 |
     Chưa có phiên ở ứng dụng
                 |
Spring Security redirect → IdP /authorize (state, nonce,...)
                 |
      Người dùng xác thực tại IdP
                 |
IdP redirect browser về URI đã đăng ký với authorization code
                 |
Spring Security trao đổi code, kiểm tra token/ID token
                 |
      Tạo Authentication và HTTP session tại ứng dụng
                 |
       Browser truy cập tài nguyên đã được phép
```

OIDC xác thực danh tính dựa trên **ID token** và metadata của issuer. Một `access token` được cấp cho API không tự nó là ID token và không nên được dùng làm bằng chứng login OIDC nếu chưa đúng luồng kiểm chứng. **OAuth 2.0 đơn lẻ là framework ủy quyền, không phải giao thức đăng nhập hoàn chỉnh**; OIDC bổ sung lớp xác thực danh tính.

**SAML 2.0** cũng phổ biến trong hệ thống doanh nghiệp lâu năm, đặc biệt khi đối tác/IdP chỉ hỗ trợ SAML, cần truyền SAML assertions, metadata, ACS URL và chữ ký XML. Nó có mô hình trust khác OIDC; không thay việc kiểm tra audience, recipient, thời gian, signature và chống replay bằng việc tin vào một trường email.

### 5.2. Ví dụ chạy với Spring Boot 3.x + IdP OIDC thật

Ví dụ này là một ứng dụng **hoàn chỉnh về mã Java và khai báo dependency**, có thể build bằng Java 17/Gradle; để đăng nhập thành công cần **IdP OIDC thật** có issuer URI, đăng ký client, redirect URI và secret hợp lệ. Không có IdP thì không thể kỳ vọng login chạy; đó là phụ thuộc hạ tầng, không phải thiếu đoạn code.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

**`src/main/java/demo/identity/IdentityApplication.java`**

```java
package demo.identity;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @GetMapping("/")
    public String home() {
        return "Identity integration demo";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "subject", user.getIdToken().getSubject(),
            "issuer", user.getIdToken().getIssuer().toString()
        );
    }
}
```

**`src/main/java/demo/identity/SecurityConfig.java`**

```java
package demo.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Trong môi trường chạy, đặt `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` và `OIDC_ISSUER_URI` qua cơ chế secret/configuration thích hợp. `OIDC_ISSUER_URI` phải là issuer của IdP, thường có HTTPS và endpoint discovery. Tại IdP, đăng ký redirect URI của client tương ứng với URL thực tế ứng dụng; khi chạy local ở port 8080, mẫu URI là `http://localhost:8080/login/oauth2/code/corp` (chỉ dành cho local; production cần HTTPS).

Với dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Mở `http://localhost:8080/` để thấy text public. Truy cập `http://localhost:8080/me` sẽ chuyển hướng đăng nhập OIDC khi chưa có session. Sau khi đăng nhập hợp lệ, response JSON có dạng:

```json
{
  "subject": "id-on-dinh-do-idp-cap",
  "issuer": "https://idp.example.test"
}
```

Giá trị thực phụ thuộc IdP. Trong ứng dụng sản xuất, không nhất thiết cần trả issuer/subject ra client như ví dụ; ví dụ chỉ minh họa **định danh ổn định để liên kết tài khoản**. Không log ID token, access token, refresh token, client secret hay session cookie.

### 5.3. Quy tắc an toàn của SSO

- **OIDC:** dùng thư viện giao thức của Spring Security để kiểm tra chữ ký, `iss`, `aud`, thời hạn, `state`/`nonce` và các điều kiện của luồng; không tự parse JWT rồi tin claim. Chỉ chấp nhận issuer đã cấu hình; quản lý signing key/JWKS rotation và hành vi fail closed khi metadata không an toàn.
- **Authorization Code + PKCE:** chọn dòng chảy phù hợp với loại client và cấu hình IdP; không tự thay bằng implicit flow để “đăng nhập nhanh”.
- **Account linking:** nhận dạng user bằng tổ hợp `issuer + subject` (OIDC) hoặc định danh ổn định được bảo đảm theo hợp đồng SAML. Email/name có thể đổi; không dùng email trùng để gộp tài khoản không kiểm chứng.
- **Groups/roles:** claim từ IdP phải có semantics, nguồn cấp và chính sách rõ. Claim `scope` hay `email_verified` không tự động là `ROLE_ADMIN`. Đặt allowlist quy tắc ánh xạ quyền và từ chối quyền cao khi claim thiếu/không hợp lệ.
- **SAML:** kiểm tra issuer, audience, signature, destination/recipient, điều kiện thời gian, `InResponseTo`/chống replay theo profile sử dụng; cập nhật metadata/certificate rotation. Không tạo Authentication từ XML đã decode nhưng chưa được xác minh.
- **Phiên và logout:** `oauth2Login()` thường dùng session của ứng dụng Servlet sau callback; logout khỏi session ứng dụng không tự bảo đảm đã logout khỏi mọi ứng dụng/IdP. Quy hoạch session idle timeout, CSRF, cookie `Secure`/`HttpOnly`/`SameSite` và RP-initiated logout/Single Logout nếu cần.
- **API:** nếu API chỉ nhận access token, cấu hình **resource server** xác minh JWT hoặc opaque token theo hợp đồng riêng. Đừng giả định OIDC browser session tồn tại ở API service.

## 6. Container-managed authentication và pre-authentication

### 6.1. Khi container đã xác thực người dùng

Một application server có thể quản lý realm, login và role của người dùng bằng cấu hình triển khai (ví dụ Java EE/Jakarta EE, realm tích hợp LDAP/Kerberos hoặc bảo mật của nền tảng). Servlet API khi đó có các khái niệm:

- `HttpServletRequest.getUserPrincipal()`: principal do **container** cung cấp.
- `HttpServletRequest.isUserInRole("ADMIN")`: thông tin role mà container xác nhận theo mô hình của nó.
- Cấu hình bảo mật triển khai: `web.xml`/security constraints, realm/role mapping hoặc đặc tính application server tùy môi trường.

Spring Security hỗ trợ **JEE pre-authentication** qua cấu hình trong `HttpSecurity`. Ví dụ một đoạn chain đã có container principal và role mapping đúng:

```java
// Minh họa bên trong cấu hình HttpSecurity; yêu cầu container realm thực.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .jee(jee -> jee.mappableRoles("USER", "ADMIN"));
```

Đoạn trên **không phải ứng dụng Java hoàn chỉnh**; chỉ thêm `jee()` không khiến container tự xác thực request. Container phải đưa principal đáng tin vào `HttpServletRequest` và khai báo đúng vai trò. Các role mappable phải được kiểm thử để Spring Security nhìn thấy authorities phù hợp, kể cả khác biệt `ADMIN` so với `ROLE_ADMIN` ở tầng ứng dụng.

### 6.2. Ranh giới tin cậy của pre-auth

Chỉ dùng pre-auth khi chắc chắn:

1. **Tầng upstream** thực sự đã xác thực, và **không có đường gọi trực tiếp** tới backend bỏ qua tầng xác thực.
2. Bất kỳ header forwarded identity nào, nếu được dùng, đều được **xóa/ghi đè** ở proxy tin cậy; client bên ngoài không thể tự đặt `X-User` rồi lấy quyền.
3. Có hợp đồng ánh xạ identity/roles và vòng đời tài khoản. Principal không tồn tại, đã bị thu hồi hoặc không có role phải bị xử lý theo **fail closed**.
4. Đường lỗi, async dispatch, nhiều `SecurityFilterChain` và các URL quản trị không có nhánh `permitAll` vô tình đi vòng qua pre-auth.
5. Test phân biệt role container với authority trong Spring Security, tránh “đã authenticate” nhưng mọi role không được mapping hoặc mặc định trở thành quản trị.

Nếu ứng dụng triển khai trên Spring Boot embedded Tomcat mà **không cấu hình container realm**, pre-auth container thường không có ý nghĩa. Trong ứng dụng mới, OIDC trực tiếp có thể vận hành rõ ràng hơn so với phụ thuộc vào bảo mật của server cũ.

## 7. Quyền truy cập: phần chung của cả bốn phương án

**Xác thực thành công không đồng nghĩa được phép thao tác.** Dù identity đến từ LDAP, certificate, OIDC/SAML hay container, backend vẫn cần kiểm tra authorization dựa trên tài nguyên và nghiệp vụ.

Ví dụ thiết kế ánh xạ:

| Nguồn | Identity đáng tin | Dữ liệu nhóm/quyền ban đầu | Quy tắc ứng dụng |
|---|---|---|---|
| LDAP | DN/entry ID của user được bind xác thực | Nhóm directory qua query được kiểm soát | Chỉ nhóm được allowlist mới thành `ROLE_REPORT_READER` |
| X.509 | Cert principal/SAN đã qua TLS verification | Thường không có quyền nghiệp vụ ngay trong cert | Lookup account nội bộ, kiểm tra active + role |
| OIDC | `iss + sub` của ID token đã xác minh | Claim groups/entitlement nếu IdP cấp đáng tin | Mapper kiểm tra issuer, scope của claim và chính sách role |
| SAML 2.0 | NameID/subject ổn định theo thỏa thuận IdP | Signed attributes với audience/conditions hợp lệ | Mapper theo hợp đồng SAML riêng |
| Container | Trusted principal và container roles | Realm/role mapping | Chỉ role được cho phép mới thành authorities |

**Thực hành tốt:**

- Có **internal user/account ID** ổn định, phân biệt nguồn và namespace. Hai username `minh` từ hai directory/issuer không được coi là cùng một người nếu chưa có liên kết đáng tin.
- Dùng **least privilege** và deny by default, đặc biệt với role quản trị. Role nằm trong group hoặc token cần được giải thích có cấu trúc: không suy diễn bằng `startsWith("admin")` hay tên nhóm trông giống nhau.
- Quy định **độ trễ thu hồi quyền**. Claim trong ID token hoặc quyền trong session có thể cũ hơn directory. Nếu quyền nhạy cảm, cân nhắc session ngắn, re-auth, tra policy tập trung hoặc cơ chế invalidation.
- Lưu audit log về `issuer/provider`, stable subject, request ID, quyết định phân quyền và thời điểm; không ghi password, raw bearer token, client certificate private key hay secret.
- Với hệ thống nhiều nguồn, tránh một filter “thử tất cả cho đến khi thành công” không có chính sách. Tách các nhóm URL/chain theo giao thức và rõ thứ tự, đặc biệt browser session và machine-to-machine APIs.

## 8. Chọn hướng tích hợp theo kịch bản

### Kịch bản A — Portal nhân viên, nhiều ứng dụng, có MFA

**Ưu tiên OIDC SSO** nếu IdP hỗ trợ chuẩn và doanh nghiệp đã dùng nó. Ứng dụng có `oauth2Login()`, mapping claim/quyền được kiểm soát, session/CSRF, và kế hoạch refresh/logout. Nếu IdP chỉ có SAML 2.0 hoặc policy bắt buộc dùng SAML, sử dụng `saml2Login()` với metadata/signature validation phù hợp. Directory vẫn có thể là nguồn danh tính phía sau IdP, không cần backend nhận password LDAP trực tiếp.

### Kịch bản B — Ứng dụng nội bộ đơn lẻ có LDAP/AD, chưa có IdP

Có thể dùng **LDAP bind** qua TLS và mapping group rõ ràng, kèm rate limiting, lockout policy, audit, session/CSRF. Nếu về sau nhiều ứng dụng cần MFA và SSO, nên cân nhắc dịch chuyển việc xác thực sang IdP. Tránh tự xây “SSO” bằng cách chia sẻ mật khẩu hoặc cookie giữa các app.

### Kịch bản C — Thiết bị/ứng dụng B2B giao tiếp qua mTLS

Dùng **X.509 client certificate** khi tổ chức có PKI và vận hành vòng đời cert. Chọn identity ổn định từ SAN hoặc định danh đã chuẩn hóa, ánh xạ tài khoản/quyền máy hoặc tổ chức và phân quyền mỗi API. Nếu client còn cần quyền của người dùng cuối, mTLS ở transport không tự cho biết **người dùng cuối là ai**; có thể cần token/SSO bổ sung.

### Kịch bản D — Ứng dụng chạy trong application server với realm bắt buộc

Dùng **container pre-auth/`jee()`** nếu container là ranh giới bảo mật được vận hành và kiểm thử. Mọi request phải qua container bảo vệ; role mapping và thất bại của container phải được xử lý; không tin header từ client. Nếu chuyển sang embedded server hoặc microservice, đánh giá lại kiến trúc thay vì sao chép `jee()` một cách máy móc.

### Kịch bản E — SPA hoặc mobile gọi API sử dụng access token

Không dùng `oauth2Login()` của web-app như bộ giải mã mọi bearer token. API Spring Security có thể dùng:

```java
// Đoạn cấu hình cho API Spring Security Servlet.
// Chỉ hợp lệ khi có cấu hình resource-server và issuer/audience thích hợp.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(org.springframework.security.config.Customizer.withDefaults()));
```

Đây là **resource server**: mục tiêu là xác minh access token gửi tới API. Cần dependency `spring-boot-starter-oauth2-resource-server` và cấu hình issuer/JWK source, validate audience theo security contract. Nó **không phải** phương án login trực tiếp trong bốn lựa chọn, nhưng rất thường bị nhầm khi tích hợp với IdP chung.

## 9. Có thể phối hợp nhiều nguồn danh tính không?

Có, nhưng phối hợp cần **cấu trúc ranh giới rõ ràng**, không phải chỉ bật nhiều bộ filter trên một chain rồi hy vọng chúng hoạt động.

Ví dụ một ứng dụng Servlet có:

- `/portal/**`: web session + OIDC SSO cho nhân viên.
- `/api/**`: resource server chấp nhận bearer token do đúng issuer cấp và có audience dành cho API.
- `/device/**`: mTLS cho thiết bị đã đăng ký, kiểm tra quyền theo certificate identity.
- `/legacy/**`: xử lý container pre-auth trong một môi trường ứng dụng đặc thù.

Có thể thiết kế nhiều `SecurityFilterChain` với `securityMatcher(...)` và `@Order` cụ thể, nhưng phải xác minh chain nào bắt từng URL, fallback không vô tình `permitAll`, và không có đường bypass qua prefix/forward/rewrite. Không chấp nhận mTLS certificate cho tài khoản nhân viên chỉ vì subject CN trùng email, cũng không gán quyền admin cho OIDC user bởi một claim không được kiểm chứng.

Một ứng dụng còn có thể dùng LDAP như **nguồn dữ liệu groups** sau khi đăng nhập bằng OIDC. Khi đó việc tra directory phải có quyền đọc tối thiểu, cache có TTL thích hợp và phải xem xét tình huống directory đang lỗi nhưng claim token vẫn còn hiệu lực.

## 10. Kiểm thử, failure mode và câu hỏi nghiệm thu

### 10.1. Ma trận kiểm thử theo cơ chế

| Phương án | Ca xác thực bình thường | Ca lỗi phải xử lý an toàn | Ca phân quyền |
|---|---|---|---|
| LDAP | User đúng mật khẩu bind thành công qua TLS | Sai password, disabled account, DN không tồn tại, directory timeout, TLS cert sai | User ngoài group admin không có quyền admin; group bị thu hồi không giữ quyền quá hạn |
| X.509 | Certificate hợp lệ và được CA tin cậy, mapping chính xác | Cert hết hạn/thu hồi/không tin, thiếu cert, SAN không map, gateway header giả | Certificate hợp lệ nhưng account không có quyền phải nhận 403 |
| OIDC | Auth code hợp lệ, ID token issuer/audience đúng, session tạo thành công | `state`/`nonce` sai, redirect URI không hợp lệ, token hết hạn, issuer lạ, signature/JWKS sai, IdP offline | Claim thiếu nhóm hoặc user bị vô hiệu hóa không nhận quyền cao |
| SAML 2.0 | Signed assertion đúng audience, recipient và time conditions | Signature invalid, replay, thời hạn sai, issuer không tin, metadata rotation lỗi | Không tin role attribute từ assertion chưa xác minh |
| Container | Container xác thực principal + role đúng | Không có principal, realm lỗi, direct-to-backend bypass, spoof header | Container role không được map hoặc không thuộc role yêu cầu → deny |

**Không kết luận an toàn chỉ vì request trả 200/302/403.** Cần xác minh principal thực tế, provider đã xử lý, `Authentication`/`GrantedAuthority` và tài nguyên nào được thực thi. Ví dụ OIDC có thể 302 ra IdP khi chưa đăng nhập — đó là luồng login bình thường, không phải ứng dụng “trả dữ liệu bảo mật”. 

### 10.2. Kiểm thử session và vòng đời tài khoản

1. Tạo user thử với quyền thấp và quyền cao; kiểm tra response/authority trước và sau khi đổi group/role.
2. Revoke quyền ở nguồn, quan sát **thời gian cho đến khi session/token hết hiệu lực**; so với yêu cầu bảo mật.
3. Với LDAP, gây lỗi directory/TLS/timeout trên staging; app không được fallback tự cấp quyền.
4. Với OIDC/SAML, kiểm tra cert/signing-key rotation, lệch đồng hồ, logout, session fixation, CSRF, cookie và login redirect loop.
5. Với mTLS, kiểm tra chứng thư hết hạn, trust-store rotation, identity mapping, bypass qua proxy, revocation policy.
6. Với container, kiểm tra security constraints cho **mọi URL/dispatch**, mapping role và trường hợp truy cập thẳng vào embedded container nếu có.
7. Trong audit, chỉ lưu thông tin cần thiết để điều tra (issuer + subject/account ID, source, request ID, outcome), không lưu credential/token/secret.

### 10.3. Câu hỏi kiểm tra kiến thức

**Hỏi:** “Công ty đã có Active Directory, vậy bắt buộc chọn LDAP login?”

**Đáp:** Không. AD có thể là nguồn danh tính cho IdP; ứng dụng có thể chọn OIDC/SAML SSO để nhận MFA và chính sách tập trung. Chọn theo người dùng, UX, bảo mật và vận hành.

**Hỏi:** “Mọi certificate ký bởi CA nội bộ đều có quyền admin?”

**Đáp:** Không. TLS xác thực certificate, còn quyền phải được map từ identity sang account/role theo policy riêng.

**Hỏi:** “Client gửi `X-User: alice` qua gateway thì Spring Security có thể xem như đã login?”

**Đáp:** Không, trừ khi có cơ chế pre-auth hoàn chỉnh qua proxy đáng tin cậy, proxy xóa/ghi đè header client, bảo vệ backend và kiểm tra mapping. Header tự khai từ client không phải bằng chứng xác thực.

**Hỏi:** “Đã bật `oauth2Login()` thì API nhận bearer token cũng tự an toàn?”

**Đáp:** Không. `oauth2Login()` quản lý đăng nhập browser và session; API resource server cần xác thực access token, issuer/audience và scopes/authorities thích hợp.

## 11. Checklist ra quyết định trước khi triển khai

- [ ] Xác định đúng loại client: browser người dùng, máy/thiết bị, service-to-service hay container-managed.
- [ ] Vẽ ranh giới tin cậy của proxy, TLS termination, IdP, directory, container và Spring Security.
- [ ] Chọn nguồn danh tính và giao thức xác thực phù hợp; không nhầm LDAP directory với SSO.
- [ ] Xác định identity key ổn định, quy trình account linking và mapping role/authority.
- [ ] Có chính sách cấp phát, rotation, thu hồi secret/certificate/signing key và tài khoản.
- [ ] Đã định nghĩa fallback/timeout/HA/fail-closed khi nguồn danh tính không sẵn sàng.
- [ ] Đã kiểm thử người dùng thiếu quyền, tài khoản bị vô hiệu hóa, nhóm/role bị thu hồi.
- [ ] Đã kiểm thử phiên, logout, cookie/CSRF, revocation và giới hạn thời gian tồn tại token.
- [ ] Đã kiểm thử reverse proxy không thể truyền principal/header tự giả vào backend.
- [ ] Có audit log tối thiểu, không lộ password/token/private key.
- [ ] Với nhiều chain, URL nào dùng provider nào được tài liệu hóa và kiểm thử; fallback deny by default.

**Kết luận:** **LDAP** phù hợp khi ứng dụng cần kiểm chứng credential với directory; **X.509/mTLS** phù hợp khi danh tính gắn với certificate và hạ tầng PKI; **OIDC/SAML SSO** phù hợp khi IdP doanh nghiệp quản lý đăng nhập, MFA và federation; **container pre-auth** phù hợp khi application server là ranh giới xác thực đáng tin. Dù chọn cách nào, Spring Security Servlet vẫn phải ánh xạ identity sang authorities đúng, bảo vệ ranh giới tin cậy và thực thi authorization riêng cho từng tài nguyên.