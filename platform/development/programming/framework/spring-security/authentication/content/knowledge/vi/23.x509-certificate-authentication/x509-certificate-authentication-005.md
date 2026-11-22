# Ánh xạ danh tính chứng thư X.509 sang tài khoản và GrantedAuthority trong Spring Security

## 1. Bài toán: chứng thư hợp lệ chưa đủ để biết người dùng được làm gì

Trong mô hình **mutual TLS (mTLS)**, client trình một chứng thư số X.509 cho server. TLS server kiểm tra chứng thư theo chính sách tin cậy, thời hạn, mục đích sử dụng và các điều kiện PKI tương ứng. Sau đó Spring Security có thể lấy danh tính đã được xác thực ở lớp TLS để tìm **tài khoản ứng dụng** và nạp tập **`GrantedAuthority`**.

Cần phân biệt ba câu hỏi:

1. **Chứng thư có được chấp nhận không?** Đây trước tiên là trách nhiệm TLS/container, với trust store và quy tắc kiểm tra chứng thư.
2. **Chứng thư đại diện cho tài khoản nào?** Đây là phép *ánh xạ danh tính chứng thư* (certificate identity mapping): chọn một định danh từ chứng thư và đối chiếu với registry/directory của ứng dụng.
3. **Tài khoản được phép làm gì?** Đây là phép *cấp quyền* (authority mapping): nạp role/permission hiện hành của tài khoản thành các đối tượng `GrantedAuthority`.

Ví dụ: client dùng chứng thư do CA doanh nghiệp cấp, có SAN URI `spiffe://company.example/service/report-reader`. Sau khi xác thực mTLS, ứng dụng ánh xạ URI đó sang tài khoản `svc-report-reader` và nạp quyền `REPORT_READ`. Chứng thư **không tự mặc nhiên cấp** `ROLE_ADMIN` hoặc `REPORT_READ` chỉ vì Subject có một tên trông hợp lệ.

### Sơ đồ luồng xử lý

```text
Client HTTPS + client certificate X.509
                |
                v
[TLS server / reverse proxy / servlet container]
  Xác thực trust chain, hạn dùng, chính sách CA / EKU,
  đối chiếu tên và revocation theo cấu hình triển khai
                |
                v
X509AuthenticationFilter  (Spring Security Servlet)
  -> lấy chứng thư client đã được container xác nhận
  -> X509PrincipalExtractor: chọn identity key
                |
                v
PreAuthenticatedAuthenticationToken
                |
                v
PreAuthenticatedAuthenticationProvider
  -> UserDetailsService / AuthenticationUserDetailsService
  -> identity key => ứng dụng/directory tìm account
  -> account enabled? roles/permissions?
                |
                v
UserDetails + Collection<GrantedAuthority>
                |
                v
Authentication đã xác thực -> SecurityContext
                |
                v
Authorization: hasAuthority / hasRole / @PreAuthorize
```

**Trust boundary:** Spring Security X.509 ở đây là cơ chế **pre-authentication**. Nó tin rằng tầng TLS có trách nhiệm xác minh chứng thư trước khi tạo danh tính đầu vào. Chỉ lấy một chuỗi DN hoặc HTTP header rồi coi là client đã xác thực sẽ phá vỡ giả định này.

## 2. Những trường trên chứng thư có thể dùng làm identity key

X.509 hỗ trợ nhiều nguồn danh tính. Không có một trường nào phù hợp cho mọi tổ chức; chọn theo chính sách CA và vòng đời tài khoản.

| Nguồn | Ý nghĩa | Ưu điểm / hạn chế |
| --- | --- | --- |
| **Subject DN** (`X500Principal`) | Chuỗi tên phân biệt, ví dụ `CN=svc-report,OU=Services,O=Example` | Có thể lấy CN nhanh; không bảo đảm duy nhất hoặc bất biến; phân tích đúng chuẩn DN |
| **Subject Alternative Name (SAN) DNS/email/URI** | Định danh thay thế, ví dụ `URI:spiffe://company.example/service/report-reader` | Phù hợp service identity nếu CA kiểm soát namespace; không tin tùy tiện mọi SAN |
| **Issuer DN + serial number** | Cặp xác định chứng thư trong phạm vi issuer | Phù hợp allowlist chứng thư cụ thể; đổi chứng thư thường tạo serial mới |
| **SHA-256 certificate fingerprint** | Hash của toàn bộ DER certificate | Pin chính xác một chứng thư; phải cập nhật khi renew/reissue |
| **Tên tài khoản nội bộ** | `accountId`/`userId` do ứng dụng quản lý | Là định danh nghiệp vụ bền vững; cần registry ánh xạ chứng thư sang account |

**Điểm quan trọng:**

- `CN` chỉ là một thuộc tính của Subject. Hai chứng thư khác nhau có thể cùng CN; việc một CA cấp trùng CN không tự tạo tài khoản duy nhất.
- `subject.getName(X500Principal.RFC2253)` cho biểu diễn DN tương đối nhất quán; **không dùng `split(",")` hoặc regex ngây thơ để parse DN** vì dấu phẩy/ký tự đặc biệt có thể được escape. Khi cần xem một RDN, dùng `javax.naming.ldap.LdapName` và kiểm tra đúng thứ tự/kiểu dữ liệu.
- SAN URI (ví dụ SPIFFE ID) hoặc SAN email dùng được **chỉ khi CA/tổ chức kiểm soát chính sách cấp phát giá trị đó**, có quy tắc chuẩn hóa và không chồng lấn tenant/namespace.
- Issuer + serial cần ràng buộc tới **trust domain/CA đã được chấp nhận**. Một chuỗi Issuer DN tự nó không phải bằng chứng mật mã; TLS phải kiểm tra chữ ký và đường dẫn chứng thư.
- Chứng thư chỉ làm bằng chứng mTLS trong giai đoạn còn hợp lệ. Dùng nó làm khóa tài khoản không được bỏ qua trạng thái khóa tài khoản, revocation, thu hồi quyền và quản trị vòng đời.

Ví dụ hai chứng thư cùng CN nhưng thuộc hai issuer:

```text
Certificate A:
  Subject = CN=report-bot,O=Example
  Issuer  = CN=Internal Client CA,O=Example
  Serial  = 2A

Certificate B:
  Subject = CN=report-bot,O=Example
  Issuer  = CN=External Partner CA,O=Partner
  Serial  = 19

CN giống nhau; cặp issuer + serial khác nhau.
Registry không được xem A và B là cùng một account
chỉ vì đều chứa CN=report-bot.
```

## 3. Các lớp Spring Security tham gia ánh xạ

Trong ứng dụng **Servlet / Spring MVC** với Spring Security 6.x:

| Lớp / interface | Vai trò |
| --- | --- |
| `X509AuthenticationFilter` | Đọc certificate chain từ servlet request, lấy principal, tạo token pre-auth |
| `X509PrincipalExtractor` | Hàm `Object extractPrincipal(X509Certificate cert)`, quyết định identity key từ chứng thư |
| `PreAuthenticatedAuthenticationToken` | Mang principal và pre-auth credentials cho quá trình xác thực nội bộ |
| `PreAuthenticatedAuthenticationProvider` | Dùng user-details service để nạp account/authorities |
| `UserDetailsService` | `loadUserByUsername(String)`: tìm tài khoản từ identity key đã chọn |
| `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` | Biến thể nhận cả pre-auth token nếu ứng dụng cần thêm chi tiết ngoài username |
| `UserDetails` | Đại diện account ứng dụng với `getUsername()`, các cờ trạng thái và authorities |
| `GrantedAuthority` / `SimpleGrantedAuthority` | Một quyền đơn, thường là tên role hoặc permission |
| `SecurityContext` | Giữ `Authentication` cho xử lý request hiện tại |

Cơ chế Spring Security `http.x509(...)` tạo filter/provider cần thiết. Với thông lệ X.509, tầng servlet cung cấp chứng thư qua request attribute `jakarta.servlet.request.X509Certificate`. Đây là dữ liệu container cung cấp **sau khi TLS đã xác thực client certificate**; Java code không nên tự nhận một header HTTP thiếu kiểm soát làm nguồn tin cậy tương đương.

### Phân biệt principal và GrantedAuthority

Ví dụ sau xác thực:

```text
Authentication.getName()            -> "svc-report"
Authentication.getPrincipal()       -> UserDetails(account nội bộ)
Authentication.getAuthorities()     -> [REPORT_READ, ROLE_SERVICE]
Certificate SAN URI                 -> "spiffe://company.example/service/report"
```

Định danh chứng thư có thể khác tên tài khoản ứng dụng. Một người có thể có nhiều chứng thư hợp lệ đang xoay vòng, nhưng cùng trỏ tới một account; ngược lại, không được ánh xạ hàng loạt chứng thư chưa được phép vào một account quyền cao.

Quy tắc cú pháp quyền:

- `hasAuthority("REPORT_READ")` tìm **chính xác** authority `REPORT_READ`.
- `hasRole("ADMIN")` theo cấu hình prefix mặc định kiểm tra `ROLE_ADMIN`.
- `ROLE_ADMIN` là một authority thông thường, không phải trạng thái đặc biệt tự đọc từ subject.
- Không biến từng chuỗi SAN/CN tùy ý thành `ROLE_<giá trị>` hoặc quyền admin. Phải có allowlist/quy tắc quy đổi và nguồn quyền độc lập, có quản trị.

## 4. Thiết kế bảng liên kết chứng thư -> tài khoản

Một hệ thống thực tế thường có ít nhất hai tập dữ liệu:

**Bảng liên kết chứng thư:**

| identity_key | account_id | trạng thái |
| --- | --- | --- |
| `issuer=CN=Example Client CA,O=Lab;serial=2a` | `svc-report` | active |
| `issuer=CN=Example Client CA,O=Lab;serial=31` | `svc-report` | active (chứng thư đang được thay thế) |
| `spiffe://company.example/service/billing` | `svc-billing` | active |

**Bảng tài khoản và quyền:**

| account_id | enabled | permissions |
| --- | --- | --- |
| `svc-report` | true | `REPORT_READ`, `ROLE_SERVICE` |
| `svc-billing` | true | `INVOICE_CREATE`, `ROLE_SERVICE` |
| `svc-retired` | false | không cấp quyền tại thời điểm xác thực |

Quy trình tại service mapping:

1. Đọc identity key đã qua xác thực TLS và được extractor tạo.
2. Đòi hỏi có **duy nhất một** liên kết active trong trust domain tương ứng; không chấp nhận kết quả mơ hồ.
3. Lấy account hiện hành và kiểm tra enabled/locked/expired theo chính sách.
4. Nạp role/permission của account từ nguồn tin cậy, chuyển thành `GrantedAuthority`.
5. Trả `UserDetails`. Nếu không thấy liên kết, tài khoản bị khóa hoặc thiếu dữ liệu bắt buộc, **từ chối xác thực** (fail closed).
6. Ứng dụng kiểm tra tiếp từng endpoint qua `authorizeHttpRequests`, `hasAuthority` và/hoặc method security.

**Không nhét trực tiếp quyền của một chứng thư bất kỳ vào account** trừ khi certificate profile có ràng buộc quyền đáng tin, được CA ký, policy quy đổi rõ và được kiểm toán. Trong đa số ứng dụng, quyền nằm ở database/IAM/directory nội bộ; certificate chỉ giúp xác định ai đang kết nối.

## 5. Ví dụ Java 17 chạy được: ánh xạ identity key sang account và GrantedAuthority

Ví dụ độc lập sau **không tạo kết nối TLS và không giả vờ xác thực chứng thư**. Nó kiểm thử phần nghiệp vụ nằm **sau** khi TLS xác thực: khóa chứng thư -> tài khoản -> authorities, bao gồm trường hợp không nhận ra chứng thư. Có thể dùng để hiểu mapping trước khi tích hợp Spring Boot.

Dự án có `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
}

application {
    mainClass = 'demo.CertificateAccountMappingDemo'
}
```

Tạo `src/main/java/demo/CertificateAccountMappingDemo.java`:

```java
package demo;

import java.math.BigInteger;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import javax.security.auth.x500.X500Principal;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class CertificateAccountMappingDemo {

    // Một khóa đăng ký chứng thư, không phải đối tượng Authentication.
    public record CertificateKey(String issuerDn, String serialHex) {

        public static CertificateKey from(X509Certificate certificate) {
            String issuer = certificate.getIssuerX500Principal()
                    .getName(X500Principal.RFC2253);
            String serial = certificate.getSerialNumber()
                    .toString(16).toLowerCase(Locale.ROOT);
            return new CertificateKey(issuer, serial);
        }

        public static CertificateKey of(String issuerDn, BigInteger serial) {
            return new CertificateKey(
                    new X500Principal(issuerDn).getName(X500Principal.RFC2253),
                    serial.toString(16).toLowerCase(Locale.ROOT));
        }
    }

    public record LocalAccount(
            String accountId,
            boolean enabled,
            Set<String> permissionNames) {}

    public record BoundIdentity(
            String accountId,
            List<GrantedAuthority> authorities) {}

    public static BoundIdentity resolve(
            CertificateKey certificate,
            Map<CertificateKey, LocalAccount> bindings) {

        // Registry phải được quản lý bởi nguồn có thẩm quyền,
        // không lấy role trực tiếp từ CN/SAN do client tự khai.
        LocalAccount account = bindings.get(certificate);
        if (account == null || !account.enabled()) {
            throw new SecurityException("Unknown or disabled account");
        }

        List<GrantedAuthority> grants = account.permissionNames().stream()
                .sorted()
                .<GrantedAuthority>map(SimpleGrantedAuthority::new)
                .toList();

        return new BoundIdentity(account.accountId(), grants);
    }

    public static void main(String[] args) {
        CertificateKey known = CertificateKey.of(
                "CN=Example Client CA,O=Lab", new BigInteger("42"));

        Map<CertificateKey, LocalAccount> bindings = Map.of(
                known,
                new LocalAccount("svc-report", true,
                        Set.of("REPORT_READ", "ROLE_SERVICE")));

        BoundIdentity principal = resolve(known, bindings);
        System.out.println("principal=" + principal.accountId());
        System.out.println("authorities=" + principal.authorities().stream()
                .map(GrantedAuthority::getAuthority).toList());
        System.out.println("canReadReports=" + principal.authorities().stream()
                .anyMatch(a -> a.getAuthority().equals("REPORT_READ")));

        try {
            CertificateKey unknown = CertificateKey.of(
                    "CN=Example Client CA,O=Lab", new BigInteger("43"));
            resolve(unknown, bindings);
        } catch (SecurityException rejected) {
            System.out.println("unknown=rejected");
        }
    }
}
```

Chạy bằng Gradle đã cài: `gradle run`. Nếu dự án có Wrapper thì dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). **Stdout của Java program** đúng như sau; Gradle có thể in thêm log bên ngoài stdout:

```text
principal=svc-report
authorities=[REPORT_READ, ROLE_SERVICE]
canReadReports=true
unknown=rejected
```

**Giải thích code:**

- `CertificateKey.from(X509Certificate)` có thể dùng với **đối tượng certificate đã được TLS/container xác thực** ở ứng dụng thật; ở `main`, `CertificateKey.of(...)` chỉ dựng khóa mẫu để chạy logic mapping, **không chứng minh một certificate hợp lệ**.
- `issuerDn + serialHex` là ví dụ liên kết **cụ thể một chứng thư**. Khi phát hành lại chứng thư mới, serial có thể đổi; cần thêm liên kết mới đã được duyệt trước khi loại liên kết cũ.
- Không tìm thấy key hoặc account bị disable: ném `SecurityException`. Tầng tích hợp Spring sẽ chuyển trạng thái này thành lỗi xác thực thích hợp; không cấp role mặc định để tiếp tục.
- Danh sách quyền được sắp xếp để stdout và kiểm thử có thứ tự xác định. `SimpleGrantedAuthority` giữ **tên quyền chính xác** mà ứng dụng cấp.
- Hàm `resolve` chạy trên một registry đáng tin và **không tự xác minh trust chain, signature, revocation**. Các phần đó thuộc cấu hình PKI/TLS và kiểm thử integration.

### Tình huống kiểm thử bổ sung cho mapping

Kiểm thử unit cần có cả bốn trường hợp:

| Input | Account registry | Kỳ vọng |
| --- | --- | --- |
| Issuer + serial trùng liên kết active | enabled, có `REPORT_READ` | Trả đúng account + `REPORT_READ` |
| Issuer trùng nhưng serial khác | không có liên kết | Từ chối |
| Cert key hợp lệ nhưng account disabled | disabled | Từ chối |
| Một account có nhiều cert key đã được đăng ký | 2 key active cùng trỏ một account | Cả hai về cùng account, quyền đến từ account |

Ngoài ra, thử `null`/trống, thay đổi quyền, và trường hợp registry bị lỗi để xác định hệ thống phải fail closed hay dùng cơ chế cache có kiểm soát.

## 6. Tích hợp với Spring Boot 3.x / Spring Security 6.x (Servlet)

Spring Security hỗ trợ cấu hình `HttpSecurity.x509`. Ở bản 6.x, có thể đặt một `X509PrincipalExtractor` trả identity key và một `UserDetailsService` ánh xạ key đó sang tài khoản nội bộ. Ví dụ sau minh họa hệ thống chỉ có một client được duyệt. Nó dùng `issuer + serial` tương tự ví dụ Java độc lập.

**Dependencies** của ứng dụng Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**Cấu hình Spring Security** (file `src/main/java/demo/CertificateSecurityConfig.java`):

```java
package demo;

import javax.security.auth.x500.X500Principal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CertificateSecurityConfig {

    @Bean
    UserDetailsService certificateAccounts() {
        // Ví dụ đúng một chứng thư đã duyệt. Với hệ thống thật,
        // lấy registry/roles từ database hoặc IAM quản lý tập trung.
        return certificateKey -> {
            if (!"CN=Example Client CA,O=Lab#2a".equals(certificateKey)) {
                throw new UsernameNotFoundException(
                        "No account bound to certificate");
            }
            return User.withUsername("svc-report")
                    .password("{noop}not-used-by-preauthentication")
                    .authorities("REPORT_READ", "ROLE_SERVICE")
                    .build();
        };
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http, UserDetailsService certificateAccounts)
            throws Exception {

        return http
                .authorizeHttpRequests(access -> access
                        .requestMatchers("/api/reports/**")
                            .hasAuthority("REPORT_READ")
                        .anyRequest().authenticated())
                .x509(x509 -> x509
                        .x509PrincipalExtractor(cert ->
                                cert.getIssuerX500Principal()
                                        .getName(X500Principal.RFC2253)
                                + "#" + cert.getSerialNumber().toString(16))
                        .userDetailsService(certificateAccounts))
                .build();
    }
}
```

**Chỗ cần phân biệt khi đọc đoạn code:**

1. `x509PrincipalExtractor` chỉ tạo key `CN=Example Client CA,O=Lab#2a`. Nó **không tự chọn role** và không tự validate chữ ký.
2. `certificateAccounts()` chọn đúng account/authorities được phép theo registry ví dụ. Chứng thư không có trong registry => ném `UsernameNotFoundException` => không xác thực thành công.
3. `UserDetails` trả username ứng dụng `svc-report`; từ đó `Authentication.getName()` thường là `svc-report` thay vì chuỗi Issuer/serial.
4. `password("{noop}not-used-by-preauthentication")` ở đây là chuỗi placeholder vì builder `User` yêu cầu trường password; pre-auth X.509 **không kiểm tra mật khẩu này**. Đừng biến nó thành credential thật hoặc lưu mật khẩu client trong mapper.
5. `.hasAuthority("REPORT_READ")` chỉ cho phép đọc reports khi account thực có authority đó. Chứng thư hợp lệ nhưng thiếu quyền vẫn bị từ chối ở bước authorization.
6. Mẫu code dùng API Spring Security **6.x**. Trong các phiên bản hiện đại, ưu tiên extractor rõ ràng thay vì phụ thuộc regex bắt CN; API và deprecation có thể thay đổi khi nâng lên Spring Security 7.x.

Đây là file cấu hình có thể biên dịch khi ứng dụng Boot có dependencies tương ứng; nó **không phải chương trình Java độc lập có `main`**. Ứng dụng phải có `@SpringBootApplication`, endpoint/controller và cấu hình TLS thực thì mới nhận được chứng thư từ trình duyệt/client.

### Cấu hình mTLS ở lớp server

Tầng TLS cần có certificate/keystore của **server**, trust store chứa CA/chứng thư **client được phép**, và chế độ yêu cầu client certificate:

```yaml
# application.yml (đường dẫn tài nguyên và tên biến tùy triển khai)
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
    key-store-password: "${SERVER_KEYSTORE_PASSWORD}"
    trust-store: classpath:client-trust.p12
    trust-store-type: PKCS12
    trust-store-password: "${CLIENT_TRUSTSTORE_PASSWORD}"
    client-auth: need
```

- `server.p12` phải chứa private key/chứng thư server; `client-trust.p12` chứa trust anchor hoặc certificate client tin cậy theo thiết kế.
- `client-auth: need` bắt buộc client gửi chứng thư được TLS chấp nhận. Với `want`, client có thể không gửi cert; behavior/authorization phải được xác định rõ, không mặc nhiên cho qua.
- File trên chỉ là cấu hình mẫu: **phải tạo/cấp phát keystore, truststore và cấu hình biến môi trường** trước khi chạy thật. Không commit key, mật khẩu hay chứng thư private của production.
- Nếu TLS terminate ở ingress/gateway, Spring Boot backend không tự có certificate trong servlet request attribute như trường hợp terminate trực tiếp. Cần thiết kế integration được bảo vệ giữa proxy và backend; xem mục 9.

### Lấy người dùng trong controller

Trong ứng dụng Spring MVC đã cấu hình như trên:

```java
// Đoạn handler cần đặt trong class @RestController với mapping phù hợp.
@GetMapping("/api/reports/me")
public Map<String, Object> me(Authentication authentication) {
    return Map.of(
            "account", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority).toList());
}
```

Cần import `java.util.Map`, `org.springframework.security.core.Authentication`, `org.springframework.security.core.GrantedAuthority` và `org.springframework.web.bind.annotation.GetMapping`. Endpoint trả account/authorities đã được Spring Security thiết lập, không đọc raw DN từ request và tự suy quyền. Tránh đưa certificate fingerprint, issuer/serial hoặc dữ liệu nhạy cảm vào response công khai trừ khi thật sự cần.

## 7. Trường hợp dùng SAN URI, email hoặc CN thay cho Issuer + serial

### 7.1. SAN URI cho service identity

Một service có thể được cấp chứng thư với SAN URI, chẳng hạn:

```text
subjectAltName:
  URI:spiffe://company.example/service/report-reader
```

Một `X509PrincipalExtractor` tùy chỉnh có thể trích URI dạng này rồi trả chuỗi chính xác làm key. Trình tự đúng:

1. Chỉ chấp nhận SAN URI đúng type 6 của X.509.
2. Chỉ chấp nhận trust domain/prefix cụ thể, đúng format, đúng số lượng identity kỳ vọng.
3. Không dùng `contains("report")` hoặc lấy phần suffix bất kỳ để suy ra role.
4. Tra registry `SAN URI -> accountId`, rồi lấy quyền từ hệ thống quản lý tài khoản.
5. Ràng buộc CA được tin cậy phải có chính sách chỉ cấp các SAN URI mà nó được phép cấp. Nếu bất kỳ CA nào trong trust store được phép cấp `spiffe://company.example/...` thì namespace có thể bị mạo danh trong phạm vi CA đó.

Một đoạn extractor **minh họa logic** (cần xử lý `CertificateParsingException` và cấu hình provider phù hợp trong dự án thật):

```java
// Hàm minh họa (không phải một class độc lập).
String extractExpectedServiceUri(X509Certificate certificate)
        throws CertificateParsingException {

    var sans = certificate.getSubjectAlternativeNames();
    if (sans == null) {
        throw new IllegalArgumentException("Missing SAN");
    }
    var uris = sans.stream()
            .filter(entry -> entry.size() >= 2)
            .filter(entry -> Integer.valueOf(6).equals(entry.get(0)))
            .map(entry -> entry.get(1))
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .filter(uri -> uri.startsWith("spiffe://company.example/service/"))
            .distinct()
            .toList();

    if (uris.size() != 1) {
        throw new IllegalArgumentException("Expected exactly one service URI");
    }
    return uris.get(0);
}
```

Để dùng làm `X509PrincipalExtractor` lambda, bắt `CertificateParsingException` và chuyển thành một lỗi xác thực thích hợp; không chọn đại phần tử đầu tiên khi có nhiều SAN URI. Đoạn này mới kiểm tra cú pháp/prefix ở ứng dụng, chưa thay thế TLS trust, CA policy hay kiểm tra identity provisioning.

### 7.2. CN chỉ dành cho mô hình được kiểm soát chặt

API Spring Security 6.x có cấu hình tiện dụng:

```java
.x509(x509 -> x509
        .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
        .userDetailsService(certificateAccounts))
```

Ở đó group regex lấy CN làm key đưa vào `UserDetailsService`. Cách này có ích để hiểu cơ chế và cho môi trường chỉ tin cậy tập chứng thư nhỏ đã kiểm soát, nhưng **CN không phải khóa toàn cục duy nhất**. Với DN chứa giá trị được escape, nhiều RDN hoặc CA cấp trùng CN, regex dễ không biểu diễn chính sách danh tính mong muốn. Khi dùng certificate identity nghiêm túc, hãy cân nhắc SAN URI, canonical ID hoặc issuer+serial/fingerprint cùng policy CA.

### 7.3. Email SAN cần liên kết tài khoản

Email có thể đổi hoặc tái cấp cho người khác, đặc biệt trong hệ thống doanh nghiệp. Nếu cần email SAN để chọn account thì phải xem email là **identity được CA xác minh và được quản lý vòng đời**; không lấy email bằng cách parse chuỗi Subject DN ngẫu nhiên, cũng không suy quyền từ domain `@example.org`.

## 8. UserDetailsService và nguồn quyền

`UserDetailsService` trong ví dụ nhận key đã trích xuất, sau đó thực hiện ánh xạ. Cần nghĩ theo hai bước:

```text
certificate identity (input) --> binding --> canonical account id
canonical account id --> account policy / IAM groups --> GrantedAuthority
```

Trong hệ thống thực tế:

- Cho phép một account nhiều certificate bindings khi rotation có kiểm soát.
- Giữ trạng thái tài khoản, quyền và liên kết certificate ở nguồn quản trị có thể audit.
- Ánh xạ external group/claim sang application authority qua **allowlist**; role nên chỉ được xuất hiện nếu có policy rõ.
- Nếu directory/DB unavailable, không âm thầm cấp `ROLE_USER` hoặc giữ quyền admin từ một cache vô hạn.
- Quyền có thể thay đổi khi certificate vẫn còn hạn. Cần xác định tần suất nạp lại quyền, cache TTL, session/security context và cơ chế thu hồi.
- `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` là điểm mở rộng khác khi mapping cần context của pre-auth token. Không nhầm với `UserDetailsService` chỉ nhận username; hãy dùng API thật tương ứng với loại dữ liệu cần xử lý.
- Không dùng `DaoAuthenticationProvider` để so password trong luồng mTLS này: quyền được nạp theo danh tính đã xác thực ở TLS, không có username/password login của người dùng.

**Nếu muốn nạp quyền từ AD/LDAP:** X.509 cho biết chứng thư thuộc account nào; directory service có thể cung cấp thuộc tính hoặc nhóm. Cần một bước mapping nhóm -> `GrantedAuthority` có kiểm soát. `memberOf` không đương nhiên là `ROLE_ADMIN`, nhóm lồng nhau có quy tắc riêng, và quyền nên phản ánh trạng thái mới nhất của account.

## 9. Reverse proxy / ingress: ranh giới tin cậy dễ bị bỏ sót

Hai mô hình triển khai có ý nghĩa khác nhau:

**(A) TLS mTLS terminate trực tiếp tại Spring Boot/Tomcat.** Container xác minh chứng thư và đặt chuỗi `X509Certificate[]` lên servlet request; Spring Security `X509AuthenticationFilter` sử dụng nguồn này.

**(B) TLS mTLS terminate tại gateway/ingress.** Backend thấy request HTTP hoặc TLS *mới* từ gateway, không trực tiếp thấy certificate của client ban đầu. Nếu gateway chuyển danh tính qua HTTP headers, ứng dụng phải:

1. Chặn truy cập trực tiếp backend từ client không được ủy quyền.
2. Bắt gateway loại bỏ các header danh tính do client gửi trước khi chèn thông tin đã xác thực.
3. Bảo vệ gateway -> backend (ví dụ mTLS nội bộ và network policy), nhận dạng gateway tin cậy.
4. Xác định chính xác dữ liệu được chuyển là *verified certificate identity* hay chỉ raw header do client khai.
5. Dùng thành phần xác thực ở backend phù hợp với mô hình gateway; **đừng giả định Spring Security `x509()` tự đọc header forwarded certificate**.

Ví dụ nguy hiểm là backend tin header `X-Client-Cert-Subject: CN=admin` mà bất kỳ client internet nào cũng có thể tự gửi đến backend. Nếu không có chặn route, xóa header và bảo vệ đường truyền, đó là lỗ hổng giả mạo danh tính.

## 10. Các lỗi phổ biến và cách khắc phục

**Lỗi 1 — Bật `http.x509()` nhưng mọi request không có principal.** Kiểm tra server có thật yêu cầu client certificate không, TLS có terminate tại backend không, chain có được container chấp nhận không và request có `jakarta.servlet.request.X509Certificate` tương ứng không. Spring Security không tạo chứng thư cho client.

**Lỗi 2 — Có certificate hợp lệ nhưng bị từ chối sau TLS.** Đây có thể là lỗi **mapping account**: extractor sinh key khác format registry; account không tồn tại/disabled; thiếu authorities; hoặc endpoint yêu cầu authority khác. Phân biệt handshake error với HTTP 401/403 bằng log đã làm sạch thông tin nhạy cảm.

**Lỗi 3 — Cùng CN nhưng hệ thống cho người dùng lạ đăng nhập account cũ.** CN trùng hoặc CA ngoài cùng truststore có thể cấp tên giống nhau. Chọn identity key không mơ hồ; giới hạn CA/namespace và ràng buộc certificate tới account qua registry.

**Lỗi 4 — Coi `X509PrincipalExtractor` như kiểm tra chữ ký/CA.** Extractor chỉ trả identity từ `X509Certificate`; TLS/container phải chứng minh chain, key usage, thời hạn và các điều kiện PKI khác. Đừng coi đối tượng cert tạo trong unit test là bằng chứng xác thực.

**Lỗi 5 — Cert có SAN `ADMIN` thì cấp `ROLE_ADMIN`.** Thông tin subject/SAN không nên trực tiếp trở thành role. Quyền phải đến từ chính sách đã duyệt, account hiện hành, hoặc certificate profile có cơ chế kiểm soát thực sự chặt chẽ.

**Lỗi 6 — Đổi certificate rồi mất quyền dù account vẫn tồn tại.** Issuer+serial hoặc fingerprint thay đổi khi renew. Hỗ trợ quy trình đăng ký certificate mới, overlap ngắn, thu hồi liên kết cũ và audit sự kiện rotation. Không tự nới policy sang “mọi cert cùng CN” để chữa cháy.

**Lỗi 7 — Tài khoản bị khóa nhưng certificate còn hạn vẫn dùng được.** Kiểm tra enabled/locked/expired ở mỗi lần cần refresh principal, đánh giá cache/session và xử lý thu hồi/khóa phù hợp. Certificate lifetime và account lifetime là hai vòng đời khác nhau.

**Lỗi 8 — Tưởng mTLS tự bảo đảm revocation.** Kiểm tra CRL/OCSP thường phụ thuộc cấu hình TLS/PKI và thực thi cụ thể. Nếu yêu cầu thu hồi nghiêm ngặt, phải kiểm thử chính sách revocation thực tế; không kết luận rằng mọi Java server tự kiểm tra OCSP.

**Lỗi 9 — Nhầm 401/403 với handshake TLS.** Nếu client không có cert khi `client-auth: need`, kết nối có thể thất bại **trước HTTP** nên không có response 401/403. Nếu TLS thành công nhưng account/authority bị từ chối, mới là trường hợp bảo mật ứng dụng.

**Lỗi 10 — Quyền không khớp `hasRole`.** `hasRole("REPORT")` thường kiểm tra `ROLE_REPORT`, còn `hasAuthority("REPORT_READ")` kiểm tra đúng `REPORT_READ`. Dùng một quy ước nhất quán và test quyền thực tế.

**Lỗi 11 — Phân tích DN bằng chuỗi `split(",")`.** DN có thể có escape, nhiều RDN, các trường không cố định thứ tự. Dùng `X500Principal`/`LdapName` hoặc thiết kế key issuer+serial/SAN theo chuẩn thay vì parser tự chế dễ sai.

**Lỗi 12 — Dùng WebFlux nhưng sao chép code Servlet.** `HttpSecurity` và `X509AuthenticationFilter` trong ví dụ là **Servlet/MVC**. Với Reactive WebFlux, thành phần filter và cấu hình bảo mật khác; đừng cắm filter Servlet vào `ServerHttpSecurity`.

## 11. Kiểm thử end-to-end phải chứng minh điều gì?

Unit test mapper chứng minh logic mapping; **integration test mTLS** mới xác nhận trust boundary và behavior khi certificate đến từ mạng.

| Thử nghiệm | Kỳ vọng và bằng chứng |
| --- | --- |
| Client không gửi cert khi server `client-auth: need` | TLS handshake thất bại hoặc kết nối bị từ chối trước HTTP |
| Client gửi cert tự ký không được truststore chấp nhận | TLS bị từ chối; không chạy tới mapping ứng dụng |
| Client gửi cert được trust nhưng key chưa được liên kết | Mapping thất bại; không có Authentication được cấp quyền |
| Client cert đã liên kết nhưng account disabled | Từ chối ở bước account lookup |
| Cert và account hợp lệ, có `REPORT_READ` | Endpoint `/api/reports/**` thành công khi controller xử lý |
| Cert và account hợp lệ, chỉ có `INVOICE_CREATE` | Endpoint reports bị 403 do không đủ quyền |
| Một account đổi sang cert mới đã đăng ký | Cùng canonical account, quyền đúng, cert cũ được vô hiệu hóa theo lịch |
| Thay đổi/thu hồi quyền trong IAM | Kiểm tra request mới và cache/session không giữ sai quyền quá thời gian cho phép |
| Gateway gửi giả header client identity | Backend không chấp nhận dữ liệu không đến từ kênh gateway tin cậy |

Khi kiểm thử với `curl`, cần **file client certificate, private key, CA đáng tin và HTTPS server đã cấu hình**. Một lệnh dạng sau chỉ là ví dụ khi đã có đủ certificate hợp lệ:

```bash
curl --cert client.crt --key client.key \
  --cacert server-ca.crt \
  https://localhost:8443/api/reports/me
```

Các file .crt/.key là ví dụ, không có sẵn từ đoạn Java. Cần cấp phát client cert đúng issuer/serial liên kết trong registry và server cert có SAN cho tên truy cập. Không dùng `-k` để bỏ xác minh server TLS như một cách “sửa lỗi” ở production.

### Bộ câu hỏi review trước khi đưa lên môi trường thật

1. Trust store và chính sách CA có chỉ chấp nhận đúng client identities dự định không?
2. Identity key dựa trên SAN/issuer+serial/fingerprint có thật sự phân biệt tenant, CA và quy trình rotation không?
3. Certificate binding thuộc hệ thống quản trị nào, có audit và thu hồi được không?
4. Tài khoản đã disable có bị từ chối ngay cả khi cert vẫn còn hạn không?
5. Quyền có nguồn tin cậy nào; có trường hợp nào subject/SAN tự tạo quyền cao bất thường không?
6. TLS direct và gateway terminate đã được test theo đúng đường triển khai chưa?
7. Việc log issuer/serial/fingerprint có mức độ dữ liệu tối thiểu và kiểm soát truy cập phù hợp không?
8. Test có phân biệt TLS handshake failure, authentication failure và authorization denial không?

## 12. Tài liệu gốc để tra cứu

- Spring Security — X.509 client certificate authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html
- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html
- Spring Security API — `X509Configurer`: https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html
- Spring Security API — `X509AuthenticationFilter`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/x509/X509AuthenticationFilter.html
- Spring Security API — `X509PrincipalExtractor`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/x509/X509PrincipalExtractor.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Boot — SSL configuration: https://docs.spring.io/spring-boot/reference/features/ssl.html

**Điều cần nhớ:** một chứng thư có thể chứng minh client sở hữu private key tương ứng trong phiên TLS và được CA hợp lệ cấp, nhưng **account ứng dụng và GrantedAuthority vẫn là kết quả của phép ánh xạ có kiểm soát**. Hãy kiểm soát cả ba ranh giới: chứng thư được tin cậy, liên kết tới account hợp lệ, và quyền hiện hành do ứng dụng cấp.
