# X509AuthenticationFilter và cấu hình x509

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring Security chạy trên **Servlet/Spring MVC**, `X509AuthenticationFilter` cho phép nhận diện người dùng hoặc thiết bị từ **chứng thư X.509 của client đã được tầng TLS kiểm tra**. Đây là mô hình *pre-authentication*: việc kiểm tra chứng thư và chứng minh quyền sở hữu private key xảy ra tại TLS connector hoặc hệ thống proxy đáng tin cậy; Spring Security nhận danh tính sau đó, ánh xạ thành user trong ứng dụng và quyết định quyền truy cập.

Sau bài học, bạn có thể:

- Phân biệt chứng thư của **server** với chứng thư của **client** và hiểu mTLS.
- Trình bày vai trò của `X509AuthenticationFilter`, `X509PrincipalExtractor`, `PreAuthenticatedAuthenticationToken`, `PreAuthenticatedAuthenticationProvider`, `UserDetailsService`, `SecurityContext`.
- Dùng `HttpSecurity.x509(...)` tạo filter tự động và cấu hình mTLS ở **Spring Boot 3.x**.
- Trích xuất username từ Subject DN/CN, chọn custom extractor khi danh tính nằm ở SAN, và gán authorities từ dữ liệu tin cậy.
- Dùng `MockMvc` và `curl` để kiểm thử hai tầng độc lập: mapping tại Spring Security và handshake tại máy chủ TLS.
- Nhận diện thay đổi cấu hình quan trọng khi chuyển từ Spring Security 5.x sang 6.x/7.x và các lỗi an toàn ở reverse proxy.

**Phạm vi chính:** Spring Security 6.x, Spring Boot 3.x, Java 17+, ứng dụng Servlet với Tomcat nhúng. Có ghi chú riêng cho 5.x và 7.x. WebFlux có API reactive X.509 khác; không dùng `X509AuthenticationFilter` của Servlet làm filter trực tiếp trong `SecurityWebFilterChain`.

## 2. Chứng thư X.509, TLS một chiều và mTLS

Chứng thư X.509 là dữ liệu được ký bởi CA, gắn một public key với danh tính và các thuộc tính như Subject, Subject Alternative Name (SAN), issuer, thời hạn, Key Usage và Extended Key Usage. Bên nắm private key tương ứng có thể chứng minh quyền sở hữu key trong giao thức TLS.

- **TLS một chiều:** client kiểm tra chứng thư server. HTTPS thông thường dùng cơ chế này; người dùng có thể tiếp tục đăng nhập bằng password/token.
- **mTLS (mutual TLS):** server còn yêu cầu và xác minh chứng thư của client. Chứng thư client phải thỏa trust policy, còn hợp lệ và đáp ứng mục đích sử dụng.
- **X.509 authentication của Spring Security:** sau khi tầng TLS chấp nhận chứng thư client, Spring Security trích danh tính rồi tra thông tin người dùng và quyền trong ứng dụng.

```text
Client có client.crt + client.key
           |
           | (1) TLS handshake, kiểm tra chứng thư server
           | (2) Server yêu cầu chứng thư client, kiểm tra chain/CA/key usage
           v
Embedded Tomcat / TLS terminator đáng tin cậy
           |
           | (3) Cung cấp certificate chain đã xác minh cho servlet request
           v
Spring Security FilterChainProxy
           |
           v
X509AuthenticationFilter
           |
           | (4) X509PrincipalExtractor -> application username
           v
PreAuthenticatedAuthenticationToken
           |
           v
PreAuthenticatedAuthenticationProvider
           |
           | (5) UserDetailsService / AuthenticationUserDetailsService
           |     -> tài khoản được phép? enabled? authorities?
           v
Authentication đã xác thực -> SecurityContext
           |
           v
AuthorizationFilter -> endpoint/controller
```

**Ranh giới tin cậy:** `X509AuthenticationFilter` **không thay cho** việc xác minh chữ ký chứng thư, CA, thời hạn, hostname, revocation hay TLS handshake ở phía server. Chỉ trích `CN` từ một chuỗi text không đủ chứng minh một client đáng tin. Máy chủ TLS phải thực thi chính sách chứng thư trước khi request tới application.

## 3. Vai trò và cơ chế của X509AuthenticationFilter

Lớp `org.springframework.security.web.authentication.preauth.x509.X509AuthenticationFilter` kế thừa `AbstractPreAuthenticatedProcessingFilter`. Nó đọc chứng thư client từ request Servlet được container cung cấp (thường dưới thuộc tính `jakarta.servlet.request.X509Certificate` trên Servlet/Jakarta hiện đại), rồi dùng `X509PrincipalExtractor` để tìm principal.

Luồng điển hình:

1. Servlet container đã hoàn tất phần xác minh chứng thư ở TLS.
2. `X509AuthenticationFilter` tìm certificate chain trong request. Nếu có, filter lấy thông tin cần thiết để tạo authentication request.
3. `X509PrincipalExtractor` lấy username từ leaf certificate. Với cấu hình thông thường, giá trị này được lấy từ **Common Name (CN)** của Subject DN.
4. `AuthenticationManager` dùng `PreAuthenticatedAuthenticationProvider` để nạp `UserDetails`/authorities ứng với username.
5. Khi thành công, `Authentication` được đặt trong `SecurityContext` cho phần xử lý tiếp theo; endpoint vẫn chịu sự kiểm tra authorization.
6. Nếu chứng thư không có, không trích được principal hoặc user không tồn tại/không được phép, không hình thành kết quả đăng nhập X.509 hợp lệ. Status trả về còn tùy TLS connector, entry point và các cơ chế đăng nhập khác.

Tương quan các đối tượng:

| Thành phần | Trách nhiệm | Không đảm nhận |
| --- | --- | --- |
| TLS connector (Tomcat/Jetty/proxy) | Yêu cầu và xác minh chứng thư client | Quyền nghiệp vụ như `ROLE_DEVICE` |
| `X509AuthenticationFilter` | Đọc chứng thư đã chuyển vào request, gọi cơ chế pre-authentication | Xây dựng trust chain/kiểm tra OCSP cho TLS |
| `X509PrincipalExtractor` | Chọn ứng dụng nhận diện nào từ chứng thư | Chứng minh user đó có quyền admin |
| `PreAuthenticatedAuthenticationProvider` | Xử lý pre-authentication token và nạp user data | Xác minh lại mật khẩu người dùng |
| `UserDetailsService` | Tìm user, trạng thái tài khoản và authorities | Kiểm tra client có private key |
| `SecurityFilterChain` | Lắp filter, entry point và policy | Tự bật mTLS tại cổng HTTPS nếu chưa cấu hình server |

Trong Spring Security 6, `http.x509(...)` tự cài `X509AuthenticationFilter` và provider liên quan. **Thông thường không tự tạo filter rồi `addFilterBefore`**: dễ đăng ký trùng filter hoặc sai vị trí. Chỉ thay filter bằng `x509AuthenticationFilter(...)` khi có lý do cụ thể và đã hiểu cấu hình manager/extractor của filter tùy biến.

## 4. Chuẩn bị Spring Boot 3.x + Spring Security 6.x

Giả sử hệ thống cần xác thực chứng thư client có Subject DN như sau:

```text
CN=client-alice,OU=Machines,O=Example
```

Directory/tài khoản ứng dụng cho `client-alice` được gán quyền `ROLE_DEVICE`. Chứng thư server dành cho `localhost`, chứng thư client đã được CA tin cậy ký. Mục tiêu demo:

```text
GET https://localhost:8443/whoami
  + chứng thư client đã được chấp nhận
  + CN=client-alice
  + user tồn tại và có ROLE_DEVICE
=> 200 OK, body: client-alice
```

Các giá trị trên là ví dụ. **Không thể kết nối thật** nếu chưa có server keystore, truststore và client certificate/key tương ứng.

### 4.1. Dependencies

Trong `build.gradle` của ứng dụng Spring Boot 3.x đã cấu hình plugin Spring Boot và Java 17+, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-web` và `spring-security-config` nằm trong starter security; không cần thêm LDAP, OAuth2 hay WebFlux chỉ để chạy `X509AuthenticationFilter`. Giữ đồng bộ phiên bản nhờ Spring Boot dependency management/BOM; không trộn Spring Security major khác nhau.

### 4.2. Cấu hình HTTPS và yêu cầu chứng thư client

`src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true

    # Server identity: private key và chứng thư HTTPS của server.
    key-store: ${SERVER_KEYSTORE_PATH}
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-store-type: PKCS12

    # Client trust: CA được phép cấp chứng thư client.
    trust-store: ${CLIENT_TRUSTSTORE_PATH}
    trust-store-password: ${CLIENT_TRUSTSTORE_PASSWORD}
    trust-store-type: PKCS12

    # need = không có chứng thư client hợp lệ thì TLS handshake không qua.
    client-auth: need
```

Giá trị môi trường minh họa:

```text
SERVER_KEYSTORE_PATH=file:/secure/server.p12
SERVER_KEYSTORE_PASSWORD=<secret-from-secret-manager>
CLIENT_TRUSTSTORE_PATH=file:/secure/client-truststore.p12
CLIENT_TRUSTSTORE_PASSWORD=<secret-from-secret-manager>
```

Không lưu private key, mật khẩu hay bản production truststore trong Git. Server keystore chứa private key và certificate chain dùng cho HTTPS. Client truststore chứa các trust anchor/CA mà server chấp nhận đối với client. Hai nơi này khác trách nhiệm; đừng chỉ nạp chứng thư server vào truststore rồi nghĩ đã cho phép mọi client.

- `client-auth: need`: TLS yêu cầu chứng thư client. Request thiếu chứng thư thường bị chặn **trước** khi Spring Security có thể trả HTTP.
- `client-auth: want`: server hỏi nhưng có thể cho client thiếu chứng thư hoàn tất handshake; sau đó chỉ endpoint/cơ chế cho phép anonymous hoặc xác thực khác mới hoạt động. Với endpoint chỉ dùng X.509 và `.authenticated()`, client thiếu cert vẫn không được vào.
- `client-auth: none`: server không yêu cầu chứng thư; cấu hình `.x509(...)` riêng lẻ không khiến trình duyệt/client tự gửi chứng thư.

Đối với client certificate: xem CA được tin, Extended Key Usage `clientAuth`, Key Usage, hạn hiệu lực, trạng thái thu hồi (nếu hạ tầng áp dụng) và chính sách chấp nhận danh tính. Đối với server certificate: SAN phải chứa hostname client kết nối, ví dụ `DNS:localhost` khi demo local.

**Lưu ý:** cấu hình `server.ssl.*` áp dụng cho TLS endpoint do Spring Boot quản lý; nếu TLS kết thúc ở reverse proxy/load balancer, bạn phải cấu hình yêu cầu/xác minh client cert tại proxy và có cơ chế chuyển danh tính đã xác minh an toàn (xem mục 10).

### 4.3. Cấu hình Spring Security x509 (ứng dụng Servlet)

File `src/main/java/example/x509/X509SecurityConfig.java`:

```java
package example.x509;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class X509SecurityConfig {

    @Bean
    UserDetailsService certificateUsers() {
        UserDetails alice = User.withUsername("client-alice")
            // Chỉ là trường bắt buộc của UserDetails; X.509 không dùng password này.
            // Không bật HTTP Basic/form login cho demo này.
            .password("{noop}!x509-only-not-a-login-password!")
            .authorities("ROLE_DEVICE")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService certificateUsers) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/whoami").hasAuthority("ROLE_DEVICE")
                .anyRequest().denyAll()
            )
            .x509(x509 -> x509.userDetailsService(certificateUsers));

        return http.build();
    }
}
```

Ở đây:

- `.x509(...)` đăng ký filter X.509 trong chain; `userDetailsService(certificateUsers)` dùng service đã định nghĩa để tìm principal vừa trích từ chứng thư.
- `UserDetailsService` demo chỉ chứa **một** user. Việc biết `CN=client-alice` không khiến Spring Security tự động tạo tài khoản cho mọi chứng thư hợp lệ khác.
- `.hasAuthority("ROLE_DEVICE")` yêu cầu đúng authority. User có chứng thư tin cậy nhưng không được gán quyền phù hợp vẫn bị từ chối truy cập.
- Đoạn password trong `UserDetails` không tham gia X.509 pre-authentication. Không dùng dạng này làm mật khẩu thật; khi bổ sung Basic/form login phải thiết kế password storage/encoder riêng, không để thông tin placeholder thành đường đăng nhập.
- `anyRequest().denyAll()` là chính sách demo giới hạn phạm vi, không phải một cấu hình bắt buộc của X.509.

`src/main/java/example/x509/WhoAmIController.java`:

```java
package example.x509;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public String whoAmI(Principal principal) {
        return principal.getName();
    }
}
```

`src/main/java/example/x509/X509DemoApplication.java`:

```java
package example.x509;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class X509DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(X509DemoApplication.class, args);
    }
}
```

Đây là các file Java độc lập theo đúng đường dẫn/package; khi đặt cùng ứng dụng Spring Boot với TLS assets và dependencies thích hợp, chúng tạo luồng authentication qua X.509. Không có fixture chứng thư trong đoạn code: muốn thử thật phải cung cấp certificate chain và private key đã được cấp.

Chạy bằng Gradle wrapper của project:

```bash
./gradlew bootRun
```

Trong môi trường Windows PowerShell, sử dụng `.\gradlew.bat bootRun` khi dự án có Gradle wrapper.

### 4.4. Gửi request bằng client certificate

Giả sử có `client-alice.crt`, `client-alice.key` và file CA để client xác minh server, thử:

```bash
curl --verbose \
  --cacert server-ca.crt \
  --cert client-alice.crt \
  --key client-alice.key \
  https://localhost:8443/whoami
```

Khi hostname, CA server, chứng thư client, private key và mapping user/authority đều hợp lệ, body dự kiến:

```text
client-alice
```

Đây là **HTTP response body dự kiến**, không phải stdout cố định của ứng dụng Java khi chưa có PKI test. Trong production tránh đưa private key hoặc mật khẩu vào command line, shell history, image hoặc CI log. Không dùng `curl -k`/`--insecure` để bỏ qua xác thực server khi kiểm tra một triển khai an toàn.

## 5. Trích xuất principal từ chứng thư: CN, DN và SAN

Mọi client certificate đều có Subject DN, có thể gồm `CN`, `OU`, `O`, `C`; chứng thư hiện đại còn có SAN như `rfc822Name` (email), `dNSName` và `uniformResourceIdentifier`. Ứng dụng phải chọn một định danh ổn định theo PKI policy, tránh giả định mọi chứng thư đều có CN duy nhất.

Cấu hình X.509 phổ biến dùng username từ CN:

```text
Subject DN = CN=client-alice, OU=Machines, O=Example
Username   = client-alice
```

`X509Configurer` có hai cách tùy biến:

- `subjectPrincipalRegex(String)` đặt biểu thức chính quy trực tiếp, được dùng trong nhiều ví dụ Spring Security 5.x/6.x nhưng **deprecated ở API 7.x**.
- `x509PrincipalExtractor(X509PrincipalExtractor)` nhận một extractor tùy biến, phù hợp hơn khi muốn kiểm soát cách lấy danh tính hoặc cần tương thích tốt với 7.x.

Ví dụ dùng `SubjectDnX509PrincipalExtractor` trong **Spring Security 6.x**, thay bean `securityFilterChain` tương ứng:

```java
import org.springframework.security.web.authentication.preauth.x509
    .SubjectDnX509PrincipalExtractor;

// Viết trong method SecurityFilterChain, trước lời gọi http.x509(...):
SubjectDnX509PrincipalExtractor extractor =
    new SubjectDnX509PrincipalExtractor();

extractor.setSubjectDnRegex("CN=(.*?)(?:,|$)");

http.x509(x509 -> x509
    .x509PrincipalExtractor(extractor)
    .userDetailsService(certificateUsers)
);
```

**Chú ý import Java:** ở một file Java thật, `import` **phải nằm trên một dòng**; ký pháp import đúng là:

```java
import org.springframework.security.web.authentication.preauth.x509.SubjectDnX509PrincipalExtractor;
```

Đoạn trên minh họa các dòng cấu hình **bổ sung vào method** `SecurityFilterChain`, không phải một chương trình độc lập. Biểu thức `(.*?)` phải trích phần giá trị CN; `(?:,|$)` dùng làm ranh giới mẫu trong DN thông thường. Class extractor yêu cầu regex có **một capturing group** để xác định username.

Có thể thử logic regex bằng Java 17 thuần JDK. File `SubjectRegexDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SubjectRegexDemo {
    public static void main(String[] args) {
        String subject = "CN=client-alice,OU=Machines,O=Example";
        Pattern pattern = Pattern.compile(
            "CN=(.*?)(?:,|$)",
            Pattern.CASE_INSENSITIVE
        );
        Matcher matcher = pattern.matcher(subject);
        System.out.println(matcher.find() ? matcher.group(1) : "NO_CN");
    }
}
```

Lệnh chạy:

```bash
javac SubjectRegexDemo.java
java SubjectRegexDemo
```

**stdout chính xác:**

```text
client-alice
```

Đây chỉ là demo **trích chuỗi**. Nó không đọc private key, không xác minh chữ ký chứng thư và không tạo một `Authentication` đã được tin cậy.

### Khi nào không nên dựa vào CN?

- Nhiều người dùng có chung CN; CA không bảo đảm tính duy nhất; đổi tên nhân sự làm thay đổi CN.
- Chủ thể có dấu phẩy/ký tự escape và thứ tự RDN phức tạp; regex tự viết trên chuỗi DN dễ sai.
- Identity policy xác định account qua SAN URI/email, số seri issuer hoặc định danh có chuẩn hóa riêng.
- Cần kiểm soát issuer/key usage/đời chứng thư hoặc mapping group từ hệ thống cấp chứng thư.

Khi đó, tạo một `X509PrincipalExtractor` phù hợp với mô hình identity của tổ chức và đưa nó qua `.x509PrincipalExtractor(...)`. Dữ liệu SAN có thể đọc bằng `X509Certificate.getSubjectAlternativeNames()`; API trả về tập các entry có type và value, cần xử lý trường hợp thiếu SAN và `CertificateParsingException`. Đừng tự lấy chữ ký/issuer bằng cách parse chuỗi không có kiểm chứng. Chứng thư đã tin cậy **vẫn phải được ánh xạ** tới một account được phép dùng ứng dụng.

## 6. Ánh xạ application user và authorities

X.509 pre-authentication có hai bước khác nhau:

1. **Identity**: extractor trả về `client-alice` từ certificate.
2. **Application account**: `UserDetailsService` xác nhận `client-alice` là tài khoản hợp lệ, cho biết enabled/locked/expired và authorities.

Factory/configurer thường tạo `PreAuthenticatedAuthenticationProvider`. Provider dùng `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`; `.userDetailsService(...)` là đường tắt bọc một `UserDetailsService` theo username.

Nếu cần lấy thêm dữ liệu từ token, có thể dùng `authenticationUserDetailsService(...)` (đoạn nằm trong một bean `SecurityFilterChain`):

```java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

// Ví dụ function mapping trong môi trường có danh sách account thật:
AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken> mapping =
    token -> {
        String name = token.getName();
        if (!"client-alice".equals(name)) {
            throw new UsernameNotFoundException("Client identity not registered");
        }
        return User.withUsername(name)
            .password("{noop}!not-used-by-x509!")
            .authorities("ROLE_DEVICE")
            .build();
    };

http.x509(x509 -> x509.authenticationUserDetailsService(mapping));
```

Đây là **đoạn minh họa bên trong một method có biến `http`**; file thật phải đưa các `import` lên đầu file và bảo đảm không đăng ký lặp `.x509(...)`. Trong ứng dụng production, thay điều kiện một username bằng tra cứu account/allowlist và policy do server quản lý. **Không** sinh `ROLE_ADMIN` trực tiếp từ CN hoặc gán quyền cho bất kỳ chứng thư nào do một CA ký nếu không có chính sách phân quyền cụ thể.

Các trạng thái failure phải được tách:

| Tình huống | Xử lý điển hình |
| --- | --- |
| Chứng thư không vượt qua kiểm tra TLS | TLS connector từ chối trước servlet |
| TLS chấp nhận nhưng không trích được principal | X.509 authentication không thể thành công |
| Principal được trích nhưng không có account | `UserDetailsService`/provider từ chối |
| User hợp lệ nhưng thiếu `ROLE_DEVICE` | Authorization từ chối, thường HTTP 403 |
| User có role nhưng bị vô hiệu hóa | Account status check dẫn tới authentication failure |
| User hợp lệ và có role yêu cầu | Được vào endpoint nếu các điều kiện an ninh khác đều đạt |

Vì vậy, **“TLS handshake OK” không đồng nghĩa “HTTP 200”**.

## 7. Tại sao không nên khởi tạo X509AuthenticationFilter thủ công?

Đường chuẩn:

```java
http.x509(x509 -> x509.userDetailsService(certificateUsers));
```

sẽ sắp xếp filter vào `SecurityFilterChain` và xây dựng các thành phần pre-authentication liên quan. Nếu tự:

```java
X509AuthenticationFilter filter = new X509AuthenticationFilter();
```

thì chỉ có một object filter chưa chắc có `AuthenticationManager`, principal extractor, failure behavior và thứ tự lọc đúng. Đặc biệt, nếu đăng ký `@Bean Filter` rồi cũng `addFilter...` vào Spring Security, embedded Servlet container và `FilterChainProxy` có thể chạy hai lần trong những cách cấu hình nhất định.

Chỉ custom filter khi có yêu cầu khó giải quyết bằng `x509PrincipalExtractor(...)`, `authenticationUserDetailsService(...)` hoặc `authenticationDetailsSource(...)`. `X509Configurer.x509AuthenticationFilter(...)` cho phép thay toàn bộ filter, nhưng phải kiểm tra lifecycle và các thuộc tính pre-authentication của subclass. Không sửa trực tiếp `SecurityContextHolder` để giả lập login thay cho pipeline.

`AbstractPreAuthenticatedProcessingFilter` có các thiết lập như kiểm tra principal thay đổi và cách tiếp tục chain khi authentication thất bại; thay đổi chúng phải được thiết kế cùng cơ chế session và những phương thức authentication còn lại. Với nhiều `SecurityFilterChain`, matcher/thứ tự quyết định request đi vào chain nào; `.x509(...)` trên chain A không bảo đảm chain B có xử lý X.509.

## 8. Phiên bản Spring Security: 5.x → 6.x → 7.x

| Chủ đề | Security 5.x | Security 6.x | Security 7.x |
| --- | --- | --- | --- |
| Servlet namespace | `javax.servlet.*` | `jakarta.servlet.*` | `jakarta.servlet.*` |
| Java baseline | Phụ thuộc phiên bản 5.x đang dùng | Java 17+ | Theo baseline và hướng dẫn migration của dòng 7.x |
| Cấu hình cũ qua adapter | `WebSecurityConfigurerAdapter` tồn tại trong các bản cũ, deprecated ở 5.7 | Adapter đã bị loại bỏ | Dùng bean `SecurityFilterChain` |
| HTTP Security X.509 | `.x509()`/configurer từng được dùng | Ưu tiên `.x509(Customizer.withDefaults())` hoặc `.x509(x -> ...)` | Ưu tiên lambda/Customizer DSL |
| Tùy chỉnh username | `subjectPrincipalRegex(...)`, extractor | `subjectPrincipalRegex(...)`, hoặc `x509PrincipalExtractor(...)` | `subjectPrincipalRegex(...)` được đánh dấu deprecated trong Javadoc hiện hành; ưu tiên `x509PrincipalExtractor(...)` |
| Nơi xác minh client certificate | TLS/container/proxy | TLS/container/proxy | TLS/container/proxy |

**Mẫu 6.x/7.x dễ bảo trì:**

```java
http
    .x509(x509 -> x509.userDetailsService(certificateUsers))
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
```

Để dùng cấu hình mặc định khi có `UserDetailsService` thích hợp:

```java
import static org.springframework.security.config.Customizer.withDefaults;

// Trong method cấu hình HttpSecurity:
http.x509(withDefaults());
```

Lưu ý vài tài liệu X.509 cũ chỉ trình bày XML namespace (`<x509/>`) và `WebSecurityConfigurerAdapter`: chúng mô tả phiên bản API khác, không phải cấu hình khuyến nghị cho Boot 3.x.

**Các chi tiết theo từng minor/major cần kiểm tra:** cơ chế xác thực đa yếu tố, marker authority cho phương thức xác thực (ví dụ `FACTOR_X509` trong tài liệu Spring Security 7.x) và API custom principal. Không dựa vào marker mới của 7.x như một điều kiện mặc định trên mọi ứng dụng 6.x. Kiểm tra phiên bản runtime bằng dependency tree; nâng cấp đồng bộ Spring Security/Boot và chạy lại test mTLS.

## 9. Kiểm thử hai tầng: MockMvc và TLS thật

### 9.1. Kiểm thử mapping/filter bằng MockMvc

Thêm dependency `spring-security-test`. Tạo chứng thư test có CN=`client-alice` tại `src/test/resources/certs/client-alice.crt` (PEM/DER được tool test chấp nhận), rồi viết `src/test/java/example/x509/X509SecurityTest.java`:

```java
package example.x509;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.x509;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class X509SecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void recognizedCertificateGetsMappedToApplicationUser() throws Exception {
        mvc.perform(get("/whoami")
                .with(x509("classpath:certs/client-alice.crt")))
            .andExpect(status().isOk())
            .andExpect(content().string("client-alice"));
    }

    @Test
    void requestWithoutCertificateCannotAccessProtectedEndpoint()
            throws Exception {
        mvc.perform(get("/whoami"))
            .andExpect(status().isForbidden());
    }
}
```

Để biên dịch Java thật, `import static` đầu tiên phải viết **trên cùng một dòng**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.x509;
```

`MockMvc` giả lập việc Servlet request đã có certificate chain; nó hữu ích để kiểm tra extractor, lookup user, authorities và rule `hasAuthority`. **MockMvc không thực hiện TLS handshake**, không chứng minh server có bật `client-auth: need`, CA chính xác, không kiểm tra truststore/CRL. Nếu test X.509 bằng certificate fixture nhưng không có SSL assets cấu hình cho Boot, vẫn cần cho test context các SSL properties hợp lệ hoặc dùng test profile tắt SSL do MockMvc không mở socket.

Lưu ý status trong test thiếu cert (`403`) là kết quả policy và entry point X.509 của cấu hình demo **khi request đã tới Spring Security**; khi chạy TLS thật với `client-auth: need`, request không có client cert thường không tới HTTP layer.

### 9.2. Kiểm thử mTLS qua cổng HTTPS thật

Với server đang chạy và certificate files hợp lệ:

```bash
# Thành công: cert/key/CA đủ tin cậy và principal được ánh xạ.
curl -i --cacert server-ca.crt \
  --cert client-alice.crt --key client-alice.key \
  https://localhost:8443/whoami

# Không có client certificate: TLS handshake thường thất bại khi client-auth=need.
curl -v --cacert server-ca.crt https://localhost:8443/whoami
```

Thử thêm các trường hợp:
- Chứng thư client ký bởi CA không được truststore chấp nhận.
- Chứng thư hết hạn, chưa đến thời điểm hiệu lực, sai EKU `clientAuth` hoặc bị thu hồi (tùy policy).
- Cert/key không khớp nhau.
- Cert hợp lệ nhưng CN không có user trong `UserDetailsService`.
- Cert hợp lệ, user tồn tại nhưng không có quyền `ROLE_DEVICE`.
- CA server sai hoặc hostname server không khớp SAN khi client kiểm tra HTTPS.
- Multi-chain, certificate chain thiếu intermediate hoặc proxy không chuyển attribute an toàn.

Kết quả quan trọng không chỉ là HTTP status: **phải ghi rõ lỗi thuộc TLS handshake, authentication mapping hay authorization**. Không cần in private key, credential, nguyên certificate chain hoặc thông tin nhạy cảm vào log.

## 10. Reverse proxy và TLS termination: ranh giới bảo mật

Trong triển khai qua ingress/nginx/load balancer:

```text
Client --mTLS--> Trusted TLS Terminator --(protected internal channel)--> Spring Boot
```

Nếu proxy terminate TLS, app có thể **không** nhận được `jakarta.servlet.request.X509Certificate` như khi Tomcat trực tiếp xử lý TLS. Hệ thống cần một cơ chế được kiểm soát để truyền identity đã xác minh, ví dụ tích hợp container/server với thông tin chứng thư được proxy chuyển trong một kênh tin cậy. Không giả định `.x509(...)` tự đọc header do proxy thêm.

**Không tin header do client tự gửi**, ví dụ `X-SSL-Client-Cert` hoặc `X-Forwarded-Client-Cert`, vì client có thể tự giả mạo nếu proxy không loại bỏ header đầu vào. Nếu kiến trúc chấp nhận danh tính từ proxy, phải đồng thời bảo đảm:
1. Đường network tới ứng dụng chỉ cho phép proxy tin cậy (firewall/service mesh/ACL), không có đường bypass.
2. Proxy thực sự xác minh chứng thư, policy/CA/CRL nếu cần, và **xóa** các header identity nhận từ bên ngoài.
3. Giá trị chứng thư hoặc identity được chuyển qua giao thức/middleware được kiểm chứng; ứng dụng biết chắc nguồn tin cậy, không chỉ parse một chuỗi header.
4. Có chính sách rotation/revocation, audit và kiểm thử client giả mạo header.

Mối quan hệ: **mTLS tin cậy ở biên** có thể xác thực một client; **authorization tại Spring Security** vẫn cần kiểm tra account, quyền, trạng thái và ngữ cảnh của request.

## 11. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân phổ biến | Kiểm tra |
| --- | --- | --- |
| Có `.x509(...)` nhưng request thiếu client certificate vẫn kết nối HTTPS | `server.ssl.client-auth` chưa bật hoặc TLS terminate ở proxy | Xem cấu hình Tomcat/ingress; dùng `curl -v` kiểm tra TLS |
| `curl` báo SSL handshake failure, bad certificate | Truststore CA client sai, cert/key không khớp, chứng thư hết hạn hoặc sai EKU | Kiểm tra chain, issuer, SAN/EKU, key, client trust anchor |
| Có chứng thư hợp lệ nhưng không có principal trong app | Container không chuyển attribute, extractor không đọc được CN/SAN | Xem Servlet API attribute từ trusted TLS connector, kiểm tra extractor |
| Principal đúng nhưng không đăng nhập | Không có user hoặc trạng thái user disabled/locked | `UserDetailsService`, account mapping, logs bảo mật |
| Đăng nhập được nhưng HTTP 403 | Thiếu `ROLE_DEVICE` hoặc rule authorization khác từ chối | Kiểm tra `Authentication.getAuthorities()` và endpoint matcher |
| Config bắt chước Spring Security 5.x không biên dịch trên 6.x | `WebSecurityConfigurerAdapter`, `javax.servlet.*` còn trong code | Dùng `@Bean SecurityFilterChain`, `jakarta.servlet.*` |
| Method `subjectPrincipalRegex` hiện deprecation warning | Bản Security 7.x khuyến nghị extractor riêng | Dùng `x509PrincipalExtractor(...)` với chiến lược rõ ràng |
| Spring Boot không khởi động HTTPS | Sai keystore/truststore path, password, type hoặc alias | Kiểm tra resource URL/permissions/store type; không in secret |
| Cert chạy trực tiếp vào Tomcat nhưng hỏng qua proxy | TLS termination và mất chain/request attribute | Kiểm tra trusted proxy integration và network bypass |
| MockMvc test pass nhưng kết nối thật fail | Unit test chỉ mô phỏng request certificate, không thực hiện TLS | Chạy thêm integration test HTTPS/mTLS thật |
| Bất kỳ cert từ CA nội bộ đều được vào app | Ánh xạ user/role quá rộng hoặc thiếu allowlist | Kiểm tra identity uniqueness, account policy và nhóm quyền |
| Test pass nhưng cert sau đổi mới không truy cập được | CN/SAN/issuer thay đổi, mapping gắn cứng vào subject | Thiết kế identity ổn định, quản lý rotation/revocation |

Trong cấu hình chỉ có X.509 pre-authentication, `Http403ForbiddenEntryPoint` thường được thiết lập khi không có cơ chế authentication entry point khác. Nếu app đồng thời bật form, Basic hoặc nhiều chain, status/redirect khi xác thực thất bại có thể khác; không khẳng định mọi trường hợp đều trả 401 hay 403.

## 12. Những quyết định cần đưa ra trong sản phẩm thật

1. **Điểm xác minh mTLS ở đâu?** Tomcat trực tiếp hay load balancer? Ai chịu trách nhiệm trust anchors, revocation và chuyển identity?
2. **Danh tính nào là duy nhất?** CN không luôn duy nhất. SAN URI/email, issuer+serial hoặc ID do PKI quản lý có thể phù hợp hơn theo quy tắc của tổ chức.
3. **Danh tính ánh xạ tới ai?** Thiết bị, dịch vụ, hay người dùng thực? Service account và human account có lifecycle/đặc quyền khác nhau.
4. **Quyền đến từ đâu?** Database/allowlist/identity provider đã được kiểm chứng; không tự cho quyền theo CN/OU.
5. **Chứng thư bị thu hồi/rotate thì sao?** Xác định CA trust, CRL/OCSP, cert lifetime, cách xóa account và session, cơ chế triển khai thay thế cert.
6. **Có cần hỗ trợ login khác không?** Nếu `client-auth=need` trên toàn cổng thì người dùng không có client cert không thể tới trang form. Muốn kết hợp cơ chế khác phải thiết kế TLS connector/host/path và policy phù hợp.
7. **Mức quan sát phù hợp?** Ghi kết quả handshake và authentication ở mức đủ điều tra, nhưng tránh lộ private key, số định danh không cần thiết, và dữ liệu cá nhân từ certificate.

Khi hai lớp được cấu hình đúng, mTLS xác minh **client có chứng thư đáp ứng trust policy**; `X509AuthenticationFilter` đưa identity từ chứng thư vào cơ chế xác thực của Spring Security; `UserDetailsService` và authorization rules quyết định user đó **được phép làm gì**.

## 13. Tài liệu chính thức

- Spring Security 6.5, X.509 Authentication (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html
- Spring Security 7.0, X.509 Authentication: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/x509.html
- API `X509Configurer` (7.x): https://docs.spring.io/spring-security/site/docs/7.0.x/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html
- API `AbstractPreAuthenticatedProcessingFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Boot, SSL: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot, Application SSL Properties: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security Test, MockMvc Request Post Processors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html
