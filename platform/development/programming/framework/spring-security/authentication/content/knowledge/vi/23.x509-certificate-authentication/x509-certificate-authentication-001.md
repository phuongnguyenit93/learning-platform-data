# Xác thực bằng chứng thư phía client và quan hệ với mTLS trong Spring Security

## 1. Mục tiêu bài học

X.509 client certificate authentication dùng **chứng thư số X.509 của phía client** làm bằng chứng để một máy chủ nhận diện bên gọi. Khi giao thức TLS xác thực **cả máy chủ lẫn client**, kết nối đó được gọi là **mutual TLS (mTLS)**. Spring Security tiếp nhận chứng thư phía client đã được tầng TLS cung cấp để ánh xạ thành `Authentication` của ứng dụng, rồi áp dụng chính sách phân quyền.

Sau bài này, bạn cần nắm được:

1. Vì sao HTTPS thông thường chỉ kiểm tra chứng thư máy chủ, còn mTLS bổ sung việc máy chủ yêu cầu và xác minh chứng thư của client.
2. Vai trò của private key, public key, certificate chain, CA, truststore/keystore, SAN, Key Usage, Extended Key Usage, ngày hiệu lực và cơ chế thu hồi chứng thư.
3. Ranh giới giữa **TLS handshake**, **Spring Security X.509 authentication**, **user account mapping** và **authorization**. Một kết nối mTLS thành công không tự biến mọi yêu cầu thành người dùng có đủ quyền.
4. Cách bật yêu cầu client certificate trên web server, cấu hình `ServerHttpSecurity.x509(...)` cho WebFlux, ánh xạ principal và lấy danh tính từ `ReactiveSecurityContextHolder`.
5. Cách thử nghiệm với OpenSSL + `curl`, diễn giải tình huống thiếu cert, cert không được tin cậy, cert hợp lệ nhưng không có account, và cert đã được xác thực nhưng thiếu quyền.
6. Cách triển khai ở môi trường có reverse proxy/service mesh và tránh biến HTTP header tự khai báo thành danh tính đã xác thực.

Bối cảnh: **Spring Boot WebFlux (reactive) + Spring Security**, Java 17+. Các nguyên tắc về PKI/mTLS áp dụng cả cho ứng dụng Servlet, nhưng ví dụ chính dùng `SecurityWebFilterChain` của WebFlux, không dùng `HttpSecurity` hoặc `X509AuthenticationFilter` của Servlet.

## 2. X.509 client certificate chứa gì và chứng minh điều gì?

Chứng thư X.509 là một dữ liệu có chữ ký của CA hoặc đơn vị phát hành, liên kết **public key** với những thuộc tính nhận diện do bên phát hành xác nhận. Những trường thường gặp:

| Thành phần | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| Subject / Distinguished Name (DN) | Các thuộc tính như `CN`, `O`, `OU` | `CN` có thể được dùng để ánh xạ username trong ví dụ; không mặc nhiên là định danh bền vững hoặc duy nhất |
| Subject Alternative Name (SAN) | Danh tính bổ sung, như DNS name, URI, email | Thường thích hợp hơn `CN` cho danh tính workload nếu tổ chức có quy ước rõ |
| Issuer, certificate chain | Ai phát hành/chuỗi đến trust anchor | Phải được phía xác minh tin cậy; chữ ký hợp lệ đơn lẻ chưa đủ |
| Public key và signature algorithm | Khóa công khai và thuật toán xác minh chữ ký | Private key tương ứng không nằm trong certificate |
| `notBefore` / `notAfter` | Khoảng hiệu lực của chứng thư | Chứng thư hết hạn hoặc chưa đến ngày hiệu lực phải bị từ chối |
| Key Usage / Extended Key Usage | Mục đích được phép dùng khóa | Với chứng thư client TLS thường yêu cầu EKU `clientAuth` theo chính sách và cách triển khai |
| Serial Number / CRL Distribution Points / OCSP | Hỗ trợ quản lý và tra cứu trạng thái chứng thư | Thu hồi chứng thư phải có chiến lược kiểm tra thực tế; đừng mặc định mọi triển khai đều tự kiểm tra online |

**Certificate là dữ liệu công khai; private key là bí mật.** Client trình chứng thư cùng bằng chứng sở hữu private key trong TLS handshake (cơ chế phụ thuộc phiên bản/cipher suite). Chỉ copy file `.crt` mà không có private key tương ứng không đủ để vượt qua mTLS.

Ví dụ tên tệp trong môi trường thử nghiệm:

- `client-ca.crt`: chứng thư CA được server tin cậy để xác minh client.
- `alice.crt`: chứng thư do CA ký, chứa danh tính ví dụ `CN=alice`.
- `alice.key`: private key mà Alice giữ; không chia sẻ, không commit.
- `server.p12`: PKCS#12 chứa private key và chứng thư server để phục vụ HTTPS.
- `client-truststore.p12`: danh sách CA/cert được web server dùng để xác minh chứng thư client; **không** chứa private key của Alice.

Tên “client certificate” nói về **vai trò trên kết nối**. Một dịch vụ có thể là server ở kết nối A và trở thành client ở kết nối B; cần cấu hình trust và key material tương ứng cho từng chiều.

## 3. TLS một chiều, mTLS và xác thực ở tầng ứng dụng

### 3.1. HTTPS thông thường

Trong HTTPS phổ biến, server gửi certificate chain; client xác minh chain, tên miền và các điều kiện TLS liên quan. Kết quả là client tin rằng mình đang nói chuyện với server mong muốn và dữ liệu trên đường truyền được bảo vệ. Server **chưa vì thế biết danh tính client**. Ứng dụng có thể xác thực người dùng bằng session cookie, OAuth2/OIDC, HTTP Basic hoặc cách khác.

### 3.2. Mutual TLS (mTLS)

Ở mTLS, server còn gửi yêu cầu client xuất trình certificate. Nếu chính sách TLS yêu cầu bắt buộc, handshake chỉ được chấp nhận khi phía client trình được chuỗi chứng thư hợp lệ và chứng minh sở hữu khóa tương ứng.

```text
Client                                               Web server
  |                                                       |
  |  TLS ClientHello                                      |
  |------------------------------------------------------>|
  |                           Server certificate,         |
  |               CertificateRequest (nếu yêu cầu mTLS)  |
  |<------------------------------------------------------|
  |  Kiểm tra danh tính + trust chain của server           |
  |  Client certificate + chứng minh sở hữu private key    |
  |------------------------------------------------------>|
  |                      Xác minh client certificate       |
  |<============= TLS được thiết lập nếu hợp lệ ===========>|
  |            HTTP request đi trong TLS                   |
  |------------------------------------------------------>|
  |                     Spring Security ánh xạ certificate|
  |                     thành principal/account/authorities|
  |                     rồi kiểm tra quyền HTTP           |
  |<---------------- HTTP response ------------------------|
```

Sơ đồ đã lược bớt các thông điệp TLS 1.2/1.3. Phần quan trọng là TLS hoàn thành **trước khi** tầng HTTP/Spring Security xử lý request. Với chính sách yêu cầu chứng thư client, nếu handshake thất bại, ứng dụng không có cơ hội trả HTTP status thông thường.

### 3.3. Hai tầng nhận diện, nhiều bước quyết định

| Bước | Thành phần quyết định | Hỏi điều gì? | Nếu thất bại |
| --- | --- | --- | --- |
| 1. Xác thực server | Client TLS stack | Đúng server theo host/SAN và trust policy không? | Client dừng TLS |
| 2. Xác thực client | Server TLS stack / gateway | Chứng thư client có chuỗi tin cậy, còn hiệu lực, phù hợp policy và được chứng minh private key không? | Thường TLS handshake bị từ chối khi `client-auth: need` |
| 3. Trích danh tính | Spring Security X.509 converter + principal extractor | Từ cert đã được giao bởi TLS, xác định principal nào? | Không có principal phù hợp / lỗi xác thực ứng dụng |
| 4. Ánh xạ account | `ReactiveAuthenticationManager` / `ReactiveUserDetailsService` | Principal có account được phép đăng nhập, không bị vô hiệu hóa, có roles nào? | HTTP authentication failure nếu đã vào tầng HTTP |
| 5. Kiểm tra quyền | `authorizeExchange` và/hoặc method security | Principal có quyền gọi endpoint, truy cập tài nguyên này không? | Thường HTTP 403 khi đã xác thực nhưng thiếu quyền |

**Không đánh đồng “CA tin cậy” với “account được ủy quyền”.** CA có thể cấp certificate cho hàng trăm workload; chỉ những identity nằm trong chính sách ứng dụng mới được phép thực hiện tác vụ cụ thể.

Chứng thư có thể xác minh danh tính **máy/dịch vụ**, không nhất thiết là danh tính **con người** đang sử dụng máy đó. Ví dụ một gateway có certificate của chính gateway; sau mTLS từ gateway vào backend, backend chỉ chứng minh được peer là gateway, chưa chứng minh end user trong trình duyệt.

## 4. Spring Security X.509 authentication hoạt động ở đâu?

Trong WebFlux, lớp mạng như Reactor Netty thực hiện HTTPS/mTLS. Với request đã có thông tin TLS, Spring Framework có thể cung cấp `SslInfo` trên `ServerHttpRequest`, trong đó có `getPeerCertificates()`. Thành phần X.509 authentication của Spring Security đọc chứng thư từ nguồn này, trích principal và tạo token **pre-authenticated** để authentication manager ánh xạ thành user/authorities.

Đường đi khái quát:

```text
Server TLS (client cert chain đã được kiểm tra)
   |
   v
ServerHttpRequest.getSslInfo().getPeerCertificates()
   |
   v
Spring Security X.509 authentication converter
   |
   v
X509PrincipalExtractor: X509Certificate -> principal ("alice")
   |
   v
ReactivePreAuthenticatedAuthenticationManager
   |
   v
ReactiveUserDetailsService: "alice" -> account + authorities
   |
   v
Authentication trong reactive SecurityContext
   |
   v
authorizeExchange / method security / business handler
```

**Pre-authenticated** nghĩa là Spring Security tin vào kết quả xác minh credential ở thành phần hạ tầng đã được cấu hình đúng; nó không có nghĩa Spring bỏ qua toàn bộ account policy. Trong cấu hình tiêu chuẩn, `ReactivePreAuthenticatedAuthenticationManager` có thể tìm account và kiểm tra trạng thái như locked/disabled/expired. Một principal trích từ cert không mặc nhiên được cấp mọi role.

Ở **WebFlux**:

```java
// Trích đoạn trong một @Configuration có import thích hợp.
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .x509(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .build();
}
```

Đây là API cấu hình **reactive** đã được Spring Security hỗ trợ; `x509` không phải tính năng chỉ có Servlet. Cấu hình này **chưa đủ** để yêu cầu mTLS trên socket: web server hoặc TLS gateway vẫn phải cấu hình key/cert, CA tin cậy và chính sách client authentication.

Trong **Servlet** cách cấu hình khác, dùng `HttpSecurity.x509(...)` và xử lý trên Servlet filter chain. Không sao chép `HttpSecurity` vào ứng dụng WebFlux. Một Servlet `X509AuthenticationFilter` không phải `WebFilter` reactive.

## 5. Thiết lập HTTPS/mTLS ở Spring Boot WebFlux

Giả sử ứng dụng WebFlux trực tiếp nhận TLS trên cổng `8443` (không có reverse proxy terminate TLS). Trong dự án Spring Boot 3.x có dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Ứng dụng dùng Reactor Netty mặc định do starter WebFlux cung cấp. Tệp `src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:./certs/server.p12"
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: tls-server
    trust-store: "file:./certs/client-truststore.p12"
    trust-store-type: PKCS12
    trust-store-password: changeit
    client-auth: need
```

Ý nghĩa phải chính xác:

- **`key-store`**: private key + certificate của **server**. Nó cho phép server chứng minh danh tính với client.
- **`trust-store`**: CA được server tin cậy khi xác minh **client certificate**. Không lẫn với truststore mà client dùng để kiểm tra server.
- **`client-auth: need`**: client certificate là điều kiện bắt buộc cho TLS connection. Nếu không có cert hợp lệ, HTTP handler thường không được gọi.
- **`client-auth: want`**: server yêu cầu cert nhưng cho phép handshake tiếp tục khi client không đưa cert; ứng dụng vẫn cần quyết định endpoint nào đòi xác thực. `want` không đồng nghĩa với buộc mọi request dùng mTLS.
- **`client-auth: none`**: không yêu cầu client certificate. Bật `.x509()` trong Spring Security một mình không thay thế chính sách này.

`changeit` và private key không mã hóa trong phần lệnh phía dưới **chỉ phục vụ local lab**. Production nên đặt secrets qua secret manager/mount giới hạn quyền truy cập, áp dụng rotation và không đưa `.key`, `.p12`, password vào repository. Nếu có cấu hình SSL bundle (`server.ssl.bundle`), phải làm theo quy tắc bundle của phiên bản Spring Boot; không trộn bundle với nhóm `server.ssl.key-store`/`trust-store` rời.

Nếu cổng `8443` không nghe hoặc quá trình TLS chưa đúng, **hãy sửa cấu hình TLS trước khi gỡ lỗi `ServerHttpSecurity`**. Security filter không thể nhận chứng thư mà server không yêu cầu hoặc không chuyển tiếp.

## 6. Ví dụ Java hoàn chỉnh: certificate CN ánh xạ account

Đây là demo chạy trong **dự án Spring Boot 3.x/WebFlux Java 17+ đã cấu hình dependency nêu trên**. Principal được lấy từ `CN` trong certificate chỉ để minh họa; thực tế nên ưu tiên định danh SAN/URI ổn định do CA kiểm soát và map qua chính sách tổ chức.

Demo chủ động chỉ chấp nhận **đúng một CN không rỗng**, parse DN bằng `LdapName` thay cho regex ngây thơ. Điều này tránh nhầm lẫn do dấu phẩy escape trong DN; thiết kế hệ thống vẫn cần kiểm soát CA nào được phép cấp CN và cập nhật Spring Security lên bản đã vá. Mã dưới đây là **một file Java biên dịch được** khi dự án có dependency hợp lệ.

Đặt tại `src/main/java/example/mtls/MtlsApplication.java`:

```java
package example.mtls;

import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Map;
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.security.auth.x500.X500Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class MtlsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MtlsApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService clientAccounts() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}not-used-for-client-cert-auth")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            MapReactiveUserDetailsService clientAccounts) {

        var preAuth = new ReactivePreAuthenticatedAuthenticationManager(
                clientAccounts);

        return http
                .x509(x509 -> x509
                        .principalExtractor(MtlsApplication::singleSubjectCn)
                        .authenticationManager(preAuth))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/whoami").hasRole("USER")
                        .anyExchange().denyAll())
                .build();
    }

    // Demo: từ certificate đã được TLS xác minh, lấy đúng một CN.
    private static String singleSubjectCn(X509Certificate certificate) {
        try {
            String subject = certificate.getSubjectX500Principal()
                    .getName(X500Principal.RFC2253);
            List<String> commonNames = new LdapName(subject).getRdns()
                    .stream()
                    .filter(rdn -> "CN".equalsIgnoreCase(rdn.getType()))
                    .map(rdn -> String.valueOf(rdn.getValue()))
                    .toList();

            if (commonNames.size() != 1 || commonNames.get(0).isBlank()) {
                throw new BadCredentialsException(
                        "Certificate must have exactly one nonblank CN");
            }

            return commonNames.get(0);
        } catch (InvalidNameException ex) {
            throw new BadCredentialsException(
                    "Invalid certificate subject DN", ex);
        }
    }

    @RestController
    static class WhoAmIController {

        @GetMapping("/whoami")
        Mono<Map<String, String>> whoAmI() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(context -> context.getAuthentication())
                    .map(MtlsApplication.WhoAmIController::response);
        }

        private static Map<String, String> response(
                Authentication authentication) {
            return Map.of(
                    "user", authentication.getName(),
                    "authenticated", Boolean.toString(
                            authentication.isAuthenticated()));
        }
    }
}
```

Giải thích những điểm cốt lõi:

1. `server.ssl.*` thực hiện xác minh certificate ở **lớp TLS**. `.x509(...)` thực hiện trích principal và authentication **ở lớp Spring Security**. Hai cấu hình phối hợp, không thay thế nhau.
2. `ReactivePreAuthenticatedAuthenticationManager` dùng danh tính trích từ cert để tìm account qua `MapReactiveUserDetailsService`. Ở production, thay bằng reactive account lookup phù hợp, giới hạn nguồn CA, tài khoản disabled/expired và quyền được gán.
3. `.hasRole("USER")` nghĩa là ngoài việc authenticated còn phải có authority `ROLE_USER`. `anyExchange().denyAll()` làm demo mặc định từ chối những endpoint không khai báo.
4. Handler trả `Mono` và lấy danh tính qua `ReactiveSecurityContextHolder`. Không dùng `SecurityContextHolder` thread-local kiểu Servlet trong WebFlux; không gọi `block()` để lấy principal.
5. User có mật khẩu giả trong fixture do `UserDetails` yêu cầu trường password; **mTLS không kiểm tra mật khẩu đó**. Đừng bật thêm HTTP Basic hoặc form login không chủ đích chỉ để “dùng” trường password.
6. Hàm `singleSubjectCn` chỉ là cơ chế ánh xạ của lab. Không coi CN tùy ý là định danh an toàn khi CA được phép phát hành CN trùng nhau hoặc khi có nhiều miền tin cậy. Nếu có namespace workload identity dựa vào SAN URI, hãy kiểm tra SAN type, expected trust domain và quy tắc cấp phát cụ thể trước khi ánh xạ.

Về phiên bản: Spring Security mới có `SubjectX500PrincipalExtractor` để thay `SubjectDnX509PrincipalExtractor` dùng parse DN cũ. Ngày 09/06/2026, Spring công bố [CVE-2026-47838](https://spring.io/security/cve-2026-47838/) về nguy cơ trích sai CN trong chứng thư được tạo đặc biệt ở các bản cũ. Nâng cấp đến bản vá phù hợp là yêu cầu riêng; một đoạn code demo không thay thế việc cập nhật dependency. Kiểm tra các bản Spring Security được Spring công bố đã vá, ví dụ dòng 6.5 từ **6.5.11**; với dòng 6.3, 6.4 cũ hãy xem chính sách hỗ trợ/bản vá tương ứng. Không sao chép cấu hình cũ dùng `SubjectDnX509PrincipalExtractor` hoặc regex trên DN mà không đánh giá rủi ro.

## 7. Tạo certificate cho local lab bằng OpenSSL và keytool

Các lệnh phần này chạy trong **Bash/POSIX shell** tại thư mục gốc dự án (có `openssl`, `keytool` trong JDK và `curl`). Trên Windows có thể dùng Git Bash hoặc điều chỉnh shell tương ứng. Chỉ thử nghiệm ở máy local: khóa CA/key sinh ra ở đây **không dùng cho production**.

### 7.1. Tạo CA chỉ để ký chứng thư client

```bash
mkdir -p certs

openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
  -keyout certs/client-ca.key \
  -out certs/client-ca.crt \
  -subj "/CN=Demo Client CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
```

`client-ca.key` là khóa ký rất nhạy cảm. Khi server tin `client-ca.crt`, server có thể chấp nhận chứng thư client do CA này phát hành nếu đáp ứng thêm chính sách. Vì vậy **phạm vi tin cậy của CA** quan trọng ngang việc kiểm tra username.

### 7.2. Tạo chứng thư HTTPS của server có SAN `localhost`

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 7 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  -addext "extendedKeyUsage=serverAuth"

openssl pkcs12 -export \
  -inkey certs/server.key \
  -in certs/server.crt \
  -name tls-server \
  -out certs/server.p12 \
  -passout pass:changeit
```

Server certificate ở đây được tự ký để lab; vì thế `curl` sẽ được truyền `--cacert certs/server.crt`. Production cần chứng thư của server do CA phù hợp cấp và client phải kiểm tra tên host/SAN theo quy tắc TLS. **Không dùng `curl -k` để “sửa” lỗi trust.**

### 7.3. Tạo certificate client có `CN=alice`, EKU `clientAuth`

```bash
openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout certs/alice.key \
  -out certs/alice.csr \
  -subj "/CN=alice"

printf '%s\n' \
  'basicConstraints=CA:FALSE' \
  'keyUsage=critical,digitalSignature' \
  'extendedKeyUsage=clientAuth' \
  > certs/client.ext

openssl x509 -req \
  -in certs/alice.csr \
  -CA certs/client-ca.crt \
  -CAkey certs/client-ca.key \
  -CAcreateserial \
  -out certs/alice.crt \
  -days 7 -sha256 \
  -extfile certs/client.ext
```

`alice.crt` là certificate public; `alice.key` là private key. TLS xác minh chain đến `client-ca.crt`; Spring Security demo trích `CN=alice` rồi tìm user `alice` trong `MapReactiveUserDetailsService`. Nếu account không tồn tại, **cert hợp lệ ở TLS vẫn chưa đủ để được cho phép vào endpoint**.

### 7.4. Tạo truststore để server xác minh client CA

```bash
keytool -importcert -noprompt \
  -alias demo-client-ca \
  -file certs/client-ca.crt \
  -keystore certs/client-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
```

`client-truststore.p12` phải đúng với `server.ssl.trust-store` trong YAML. **Không** đưa `alice.key` vào truststore của server. `client-ca.key` cũng không thuộc truststore; CA private key chỉ phục vụ phát hành certificate ở môi trường được kiểm soát.

Kiểm tra certificate được ký như mong muốn:

```bash
openssl verify -CAfile certs/client-ca.crt certs/alice.crt
openssl x509 -in certs/alice.crt -noout -subject -issuer -dates
openssl x509 -in certs/alice.crt -noout -text
```

Lệnh `openssl verify` đầu tiên dự kiến trả `certs/alice.crt: OK`. Các lệnh còn lại giúp xem Subject, Issuer, thời gian và EKU trong cert. Kết quả có thể khác theo phiên bản OpenSSL; với production cần thêm quy trình PKI của tổ chức.

### 7.5. Chạy ứng dụng

Đảm bảo cấu trúc file:

```text
project-root/
  certs/
    server.p12
    server.crt
    client-truststore.p12
    alice.crt
    alice.key
    client-ca.crt
  src/main/java/example/mtls/MtlsApplication.java
  src/main/resources/application.yml
  build.gradle
```

Chạy từ project root với Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell hoặc Command Prompt dùng `gradlew.bat bootRun`. Ví dụ giả định project có Spring Boot Gradle plugin và cấu hình Java đúng phiên bản, và cổng `8443` chưa có tiến trình khác.

### 7.6. Gọi HTTPS với certificate client

```bash
curl --show-error --silent \
  --cacert certs/server.crt \
  --cert certs/alice.crt \
  --key certs/alice.key \
  https://localhost:8443/whoami
```

Kỳ vọng nhận JSON có các trường `"user":"alice"` và `"authenticated":"true"` (thứ tự thuộc tính JSON có thể thay đổi). Đường đi kiểm chứng là: **client trust server -> server trust client CA -> chứng minh private key -> CN alice -> account alice -> ROLE_USER -> response**.

## 8. Bốn tình huống kiểm tra và cách hiểu kết quả

### 8.1. Không gửi client certificate khi `client-auth: need`

```bash
curl -v \
  --cacert certs/server.crt \
  https://localhost:8443/whoami
```

Dự kiến TLS handshake hoặc phiên TLS bị ngắt do server yêu cầu client certificate. **Không cố chờ HTTP 401**: request có thể chưa vào WebFlux. Tên lỗi cụ thể như `certificate required`, `alert bad certificate`, `handshake failure` hoặc kết nối reset phụ thuộc TLS 1.2/1.3, implementation và thời điểm lỗi được phát hiện.

Nếu bạn muốn các đường dẫn công khai vẫn dùng HTTPS mà không cần client certificate, cần thiết kế listener/gateway riêng, hoặc `client-auth: want` cộng với chính sách HTTP phù hợp. TLS `need` trên cùng socket áp dụng cho toàn bộ handshake, không chỉ một path như `/admin`.

### 8.2. Certificate do CA không tin cậy phát hành

Dù certificate có `CN=alice`, nếu không thuộc trust chain mà server cho phép, TLS phải từ chối. Không thể vượt qua bước này chỉ bằng cách sửa Subject thành “alice”. Tương tự, chỉ có `alice.crt` nhưng không có private key tương ứng sẽ không đủ để xác minh sở hữu khóa.

### 8.3. Certificate hợp lệ ở TLS nhưng không có account tương ứng

Tạo thêm một client `CN=bob` được **cùng CA** ký:

```bash
openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout certs/bob.key -out certs/bob.csr \
  -subj "/CN=bob"

openssl x509 -req \
  -in certs/bob.csr \
  -CA certs/client-ca.crt \
  -CAkey certs/client-ca.key \
  -CAcreateserial \
  -out certs/bob.crt \
  -days 7 -sha256 \
  -extfile certs/client.ext

curl -i \
  --cacert certs/server.crt \
  --cert certs/bob.crt \
  --key certs/bob.key \
  https://localhost:8443/whoami
```

Bob có thể vượt **TLS** vì CA được trust, nhưng không có user `bob` trong `MapReactiveUserDetailsService` nên Spring Security từ chối xác thực. Response HTTP cụ thể phụ thuộc security entry point/error handling; điểm phân biệt là **không phải lỗi xác minh chứng thư ở TLS**.

### 8.4. Account tồn tại nhưng không có quyền

Nếu ánh xạ thêm một user hợp lệ có `ROLE_VIEWER`, mà endpoint yêu cầu `hasRole("USER")`, Spring Security phải từ chối authorization sau khi authentication đã thành công, thường bằng HTTP **403 Forbidden**. Vì vậy:

```text
TLS ACCEPTED ≠ SPRING AUTHENTICATED ≠ AUTHORIZED
```

Không kết luận mTLS “hỏng” chỉ từ status 403. Hãy xác định request bị chặn ở lớp nào.

| Thử nghiệm | TLS | Spring authentication | Authorization |
| --- | --- | --- | --- |
| Alice đúng cert/key, account enabled, ROLE_USER | Qua | Qua | Qua |
| Không có client cert, server `need` | Thất bại | Chưa chạy | Chưa chạy |
| Cert tự ký/CA không được trust | Thất bại | Chưa chạy | Chưa chạy |
| Bob cert hợp lệ, account không tồn tại | Qua | Bị từ chối | Chưa đạt |
| Account tồn tại nhưng không có ROLE_USER | Qua | Qua | Bị từ chối |
| Alice cert đã hết hạn | Bị từ chối theo TLS validation policy | Chưa chạy | Chưa chạy |

## 9. Principal mapping: CN, SAN, service identity và quyền

Spring Security cung cấp `X509PrincipalExtractor` để chuyển `X509Certificate` thành principal. Theo phiên bản, implementation mặc định có thể lấy CN; phiên bản mới cung cấp `SubjectX500PrincipalExtractor`. Tuy nhiên, **chọn trường nào và cách tổ chức CA cấp tên** mới quyết định danh tính có an toàn và ổn định hay không.

### 9.1. Vì sao CN chỉ nên dùng như lab hoặc chính sách đã kiểm soát?

Một `CN=payment-service` trong certificate là một **chuỗi định danh** do CA/phía phát hành đặt. Nếu nhiều CA được trust cùng có thể cấp chuỗi đó, hoặc một CA cấp trùng CN cho nhiều chủ thể, ánh xạ theo CN đơn thuần có thể dẫn đến quyền không mong muốn.

Đối với máy/dịch vụ, nên định nghĩa namespace nhận diện, ví dụ danh tính nằm trong **URI SAN** và trust domain đã được chỉ định. Quy trình mapping nên kiểm tra đúng loại SAN, URI schema, tenant/trust domain, CA phát hành, environment và trạng thái workload theo chính sách. Không lấy một SAN bất kỳ rồi cấp role mặc định.

### 9.2. Custom mapping cần tách khỏi kiểm tra certificate

Ở ví dụ, `singleSubjectCn` **không** tự xác minh chữ ký/chứng chỉ; nhiệm vụ đó thuộc TLS stack. Hàm chỉ trích một tên từ certificate mà tầng TLS đã xác minh. Nếu tự đọc header `X-Client-Cert` hoặc chuỗi Base64 do client gửi rồi parse thành `X509Certificate` mà chưa có trust boundary, bạn đã bỏ qua lớp TLS xác thực.

Khi thay `ReactivePreAuthenticatedAuthenticationManager` bằng custom `ReactiveAuthenticationManager`, vẫn phải:

- Xác minh account hoặc workload được phê duyệt, disabled/locked/expiry và policy thu hồi quyền.
- Gán authorities theo dữ liệu đáng tin cậy; không lấy trực tiếp “ROLE_ADMIN” từ `OU` hoặc field do bên phát hành thiếu kiểm soát.
- Từ chối khi principal không khớp, không dùng `Mono.just(authentication)` với `authenticated=true` cho mọi certificate.
- Duy trì fail-closed: parse lỗi, danh tính không duy nhất, định danh không thuộc tenant/trust domain phải bị từ chối.

### 9.3. Phân biệt user identity với workload identity

Ví dụ gateway có certificate `CN=edge-gateway` và gọi backend bằng mTLS. Backend xác thực **edge-gateway**, không tự biết người dùng “alice” đăng nhập trên trình duyệt ở hop trước. Nếu backend cần end-user authorization, phải nhận và xác minh cơ chế delegation/end-user token phù hợp, độc lập với xác thực workload của kết nối mTLS.

Trong kiến trúc microservices, mTLS thường xác thực **service-to-service**, còn OAuth2 access token/JWT mang danh tính/phạm vi ủy quyền của user hoặc client theo mô hình riêng. Hai cơ chế có thể dùng cùng nhau; mTLS có thể hỗ trợ xác thực/kênh bảo mật, nhưng không tự tạo scopes, roles hoặc thay thế kiểm tra quyền theo tài nguyên.

## 10. mTLS với WebClient: caller cũng phải trình chứng thư

Nếu một ứng dụng Spring WebFlux là **client** gọi API yêu cầu mTLS, chỉ cấu hình `server.ssl.*` của chính ứng dụng đó là chưa đủ. Outbound `WebClient` cần **key material phía client** (certificate + private key) và **trust material** để kiểm tra certificate của server đích.

Trích đoạn Java sau minh họa cấu hình một `WebClient` riêng bằng Reactor Netty; đặt trong class cấu hình đã import các kiểu cần thiết, và xử lý `SSLException` theo chính sách khởi tạo ứng dụng:

```java
import java.io.File;
import javax.net.ssl.SSLException;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

// Trích đoạn phương thức cấu hình, không phải cả ứng dụng độc lập.
WebClient mtlsWebClient() throws SSLException {
    SslContext context = SslContextBuilder.forClient()
            .keyManager(
                    new File("certs/alice.crt"),
                    new File("certs/alice.key"))
            .trustManager(new File("certs/server.crt"))
            .build();

    HttpClient httpClient = HttpClient.create()
            .secure(spec -> spec.sslContext(context));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .baseUrl("https://localhost:8443")
            .build();
}
```

`WebClient` tiếp tục được sử dụng theo mô hình reactive:

```java
Mono<String> response = mtlsWebClient()
        .get()
        .uri("/whoami")
        .retrieve()
        .bodyToMono(String.class);
```

Trích đoạn thứ hai thuộc một phương thức được phép ném/xử lý `SSLException`; code không gọi `block()` hay `subscribe()` thủ công. Cấu hình production nên dùng SSL bundles/secrets phù hợp và quản lý lifecycle/key rotation thay vì tạo context/client mới cho mỗi request. `trustManager` chỉ định trust anchor server; **không thay bằng trust-all**. Cũng cần kiểm tra tên host/SAN và giới hạn URL đích, vì client certificate không nên được gửi sang host không thuộc miền tin cậy đã định nghĩa.

## 11. Nếu TLS terminate ở reverse proxy, ingress hoặc service mesh?

Đây là tình huống dễ cấu hình sai nhất.

### Trường hợp A: mTLS kết thúc ngay tại WebFlux/Netty

```text
Caller -- mTLS (client cert) --> Reactor Netty --> Spring Security .x509()
```

Tầng Spring có thể thấy `SslInfo.getPeerCertificates()`. Đây là mô hình của demo.

### Trường hợp B: mTLS kết thúc ở ingress/proxy

```text
Caller -- mTLS --> trusted ingress -- HTTP/TLS khác --> WebFlux app
                     |
                     +-- đã xác thực cert của caller tại ingress
```

Backend nhận kết nối từ ingress. Nếu ingress không chuyển chứng thư hoặc kết quả xác thực qua một giao thức được bảo vệ, `getSslInfo().getPeerCertificates()` ở backend có thể rỗng hoặc chỉ thấy **certificate của ingress** trên hop sau. `.x509()` của backend **không tự tìm lại chứng thư ban đầu**.

Nếu cần truyền kết quả xác thực từ ingress, phải có mô hình trust được thiết kế và kiểm toán: ingress xóa mọi header nhận từ internet có tên trùng header identity, tạo assertion/metadata từ kết quả TLS đã kiểm tra, ký hoặc chuyển qua kênh xác thực giữa ingress và backend, backend chỉ chấp nhận từ peer tin cậy và thực hiện mapping/authorization thích hợp. Không bật cơ chế “đọc `X-Client-Cert`, `X-Forwarded-Client-Cert` hoặc `X-SSL-Client-Cert` rồi coi là user” khi client bên ngoài có thể tự đặt header.

Nếu service mesh cấp workload identity, mesh và ứng dụng phải thống nhất **ai là peer đã được chứng minh**, **hop nào dùng TLS**, identity được chuyển thế nào và cơ chế kiểm tra quyền dùng gì. Một liên kết TLS bảo mật tới gateway chỉ chứng minh peer của liên kết đó.

### Sơ đồ phân chia trách nhiệm

| Kiến trúc | Ai xác minh chứng thư của client gốc? | App nhìn thấy cert gốc không? | App cần gì? |
| --- | --- | --- | --- |
| TLS trực tiếp ở WebFlux | Netty TLS stack | Có nếu SSL info được cung cấp đúng | `.x509`, account mapping, authorization |
| Ingress terminate mTLS, backend HTTP | Ingress | Thường không | Assertion đã xác minh qua trust boundary, policy riêng |
| Ingress terminate và mTLS tiếp tới backend | Ingress ở hop ngoài; backend xác minh ingress ở hop trong | Backend có thể thấy cert của ingress, không phải của user gốc | Xác minh workload ingress và end-user identity riêng |
| Service mesh mTLS giữa workloads | Sidecar/mesh proxy | Tùy tích hợp, thường mesh giữ identity kênh | Workload policy + optional application authentication |

## 12. Kiểm thử và quan sát lỗi theo từng tầng

### 12.1. Test certificate ở mức TLS

Kiểm tra các biến thể: cert hợp lệ; không có cert; cert thuộc CA không trust; cert hết hạn/chưa hiệu lực; wrong EKU; private key không khớp; hostname server sai. Test bằng `curl`/OpenSSL thật qua cổng HTTPS để xác minh **TLS handshake**; unit test giả lập principal không thay thế bước này.

### 12.2. Test account mapping và authorization

Với chứng thư được TLS chấp nhận, tạo identity tồn tại/không tồn tại, account enabled/disabled, roles đúng/sai, CN/SAN bất thường và namespace trùng. Xác minh ứng dụng fail-closed khi account lookup/authorization thất bại. `@WithMockUser` hoặc reactive security test fixture có ích cho business authorization test nhưng **không chứng minh mTLS đã được cấu hình đúng**.

### 12.3. Test bất đồng bộ và ranh giới context

Trong controller/service reactive, lấy danh tính qua `ReactiveSecurityContextHolder` hoặc principal do Spring inject; không phụ thuộc `ThreadLocal`. Tránh gọi `block()` và `subscribe()` thủ công. Test concurrent requests từ hai certificate (ví dụ Alice và một user thứ hai), bảo đảm không lẫn principal. Nếu một request phát sinh outbound call, cấu hình client certificate và propagation của end-user identity **độc lập** theo từng kết nối.

### 12.4. Khoanh vùng lỗi

| Triệu chứng | Khả năng gần nhất | Bước kiểm tra |
| --- | --- | --- |
| `SSLHandshakeException`, `certificate_required`, alert TLS | Không có cert, cert/key mismatch, CA/truststore, hạn, EKU hoặc handshake policy | Kiểm tra `server.ssl.client-auth`, chain, thời gian, key và truststore |
| `curl` báo self-signed/untrusted server | Client không tin chứng thư server hoặc SAN không khớp | Dùng `--cacert` đúng và hostname đúng, không tắt verify |
| TLS qua, HTTP bị từ chối | Principal không ánh xạ account hoặc thiếu role | Kiểm tra username trích xuất, account status, `authorizeExchange` |
| `ReactiveSecurityContextHolder` không có user | Request chưa được xác thực, certificate không hiện trong `SslInfo` hoặc chain security không chạy như mong đợi | Kiểm tra đúng WebFlux filter chain và topology TLS |
| Local chạy, sau ingress lỗi | TLS đã terminate trước ứng dụng, hoặc backend chỉ thấy cert của proxy | Xác định peer từng hop và thiết kế trust propagation |
| Chứng thư bị thu hồi vẫn gọi được | Chưa cấu hình/kiểm chứng CRL/OCSP hoặc cache/connection vẫn sống | Rà soát chính sách thu hồi, TTL kết nối và rotation |

Đừng ghi toàn bộ private key, raw certificate chain hoặc bearer token vào log. Nên log tối thiểu theo chính sách: request correlation, kết quả xác thực/authorization, mã lỗi và định danh workload đã chuẩn hóa; cân nhắc privacy với Subject DN, SAN, serial number.

## 13. Checklist production

1. **PKI:** chỉ trust CA cần thiết; định nghĩa trust domain, quy trình phát hành, giới hạn SAN/EKU và bảo vệ khóa CA.
2. **Private key:** lưu an toàn trong secret store/HSM hoặc cơ chế tương đương; phân quyền file, quản lý lifecycle và rotation. Không dùng password/mật khẩu lab.
3. **TLS:** bật phiên bản/giao thức được hỗ trợ an toàn, hostname verification ở phía client, `client-auth: need` ở cổng thật sự yêu cầu mọi kết nối mTLS; phân biệt `want`/`need` rõ.
4. **Identity mapping:** ưu tiên định danh do tổ chức quản trị với tính duy nhất kiểm chứng được; từ chối ambiguity; không dùng regex DN tùy tiện, không dựa vào header tự khai báo.
5. **Spring Security:** dùng `ServerHttpSecurity.x509(...)` khi WebFlux nhận peer certificate, kiểm tra account status và cấp authorities tối thiểu; cập nhật bản vá Spring Security, đặc biệt mã trích subject X.509.
6. **Authorization:** phân quyền endpoint, method và dữ liệu; certificate CA-signed không có nghĩa là `ROLE_ADMIN`. Phân biệt client workload với end-user.
7. **Topology:** xác định chính xác nơi TLS terminate; nếu qua proxy/mesh, thiết kế và kiểm chứng rõ hop và identity assertion được tin cậy.
8. **Revocation/rotation:** có quy trình CRL/OCSP hoặc cơ chế thu hồi/short-lived cert phù hợp; quan sát thay thế cert, connection reuse, lỗi do expiry và thời gian đồng hồ.
9. **Kiểm thử:** có smoke test TLS thật, test sai CA, thiếu certificate, account không tồn tại, thiếu quyền, hai identities đồng thời và proxy boundary.
10. **Quan sát:** theo dõi TLS handshake failures, authentication failures, 403, certificate expiry và mức độ thành công của rotation nhưng không phát tán key hoặc credential trong log.

Một hệ thống mTLS đáng tin cần **hai quyết định độc lập**: tầng vận chuyển xác minh bên đang giữ khóa đúng; ứng dụng xác định identity đó được phép làm việc gì. Spring Security X.509 là cầu nối từ chứng thư do TLS cung cấp đến mô hình `Authentication` và authorization của ứng dụng.

## 14. Tài liệu chính thức và bảo mật

- [Spring Security — Reactive X.509 Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/x509.html): cấu hình `ServerHttpSecurity.x509`, principal extractor và reactive pre-authentication manager.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): DSL WebFlux.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` và policy.
- [Spring Boot 3.3 — Embedded Web Servers / SSL](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): keystore, SSL bundles và Reactor Netty.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.ssl.client-auth` và truststore.
- [Spring Security — CVE-2026-47838](https://spring.io/security/cve-2026-47838/): rủi ro trích CN của `SubjectDnX509PrincipalExtractor` và bản vá.
- [Spring Security — CVE-2026-22747](https://spring.io/security/cve-2026-22747/): rủi ro trích CN ở một số phiên bản `SubjectX500PrincipalExtractor`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc chứng thư và xác minh chain.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): bắt tay TLS và xác thực certificate.
