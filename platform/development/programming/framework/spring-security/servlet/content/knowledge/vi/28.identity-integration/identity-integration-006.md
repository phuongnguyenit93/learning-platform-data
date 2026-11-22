# X.509: chứng thư phía client và ánh xạ subject sang tài khoản

**Phạm vi:** Tích hợp danh tính trong ứng dụng **Spring Security Servlet/Spring MVC**, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học giải thích chứng thư X.509 của **client** được kiểm tra ở đâu, Spring Security trích xuất **subject** như thế nào, cách biến danh tính đó thành tài khoản cùng quyền truy cập, và các điểm cần lưu ý khi có reverse proxy. Ví dụ chạy với embedded Tomcat và HTTPS trực tiếp; Spring WebFlux có API bảo mật reactive riêng.

## 1. X.509 client authentication giải quyết việc gì?

Thông thường HTTPS chỉ yêu cầu **server** trình chứng thư để trình duyệt/client xác minh nó đang nói chuyện với server hợp lệ. Trong **mutual TLS (mTLS)**, server còn yêu cầu **client** trình chứng thư riêng. Client chứng minh đang giữ **private key** tương ứng với public key trong chứng thư, còn server kiểm tra chuỗi tin cậy, thời hạn, quy tắc sử dụng chứng thư và các ràng buộc TLS áp dụng.

Ví dụ một hệ thống quản trị cho phép máy của nhân viên đã được cấp chứng thư truy cập:

1. Ứng dụng nhận kết nối TLS.
2. Server yêu cầu chứng thư client và xác minh nó theo **trust store** hoặc CA được tin cậy.
3. Khi TLS hợp lệ, servlet container có thể cung cấp chuỗi chứng thư đã xác minh cho request.
4. Spring Security dùng `X509AuthenticationFilter` để lấy chứng thư, trích xuất principal từ subject và xác thực principal với hệ thống tài khoản.
5. Ứng dụng chỉ cho phép truy cập nếu **tài khoản hợp lệ và đủ quyền**.

Như vậy có hai câu hỏi riêng: **“Chứng thư này có đáng tin về mặt TLS không?”** và **“Danh tính gắn với chứng thư được phép làm gì trong ứng dụng?”**. mTLS giải quyết tầng đầu, còn Spring Security kết nối danh tính với tài khoản/authorities cho tầng tiếp theo.

### 1.1 Phân biệt server certificate và client certificate

| Đối tượng | Nơi nắm private key | Ai kiểm tra | Mục tiêu |
| --- | --- | --- | --- |
| Chứng thư **server** | Server TLS / load balancer | Trình duyệt, curl, service client | Xác minh server; bảo vệ kênh HTTPS. |
| Chứng thư **client** | Browser certificate store, thiết bị hoặc service caller | Server TLS / proxy nhận kết nối | Xác minh danh tính thiết bị/client theo PKI. |
| Tài khoản ứng dụng | Directory/DB/`UserDetailsService` | Spring Security | Liên kết danh tính đã xác minh với trạng thái tài khoản và quyền. |

Một chứng thư client hợp lệ **không tự động** đồng nghĩa với `ROLE_ADMIN`, `ROLE_USER` hay quyền xem dữ liệu của người khác. Ngược lại, tên tài khoản có tồn tại trong database cũng không đủ khi client không thể chứng minh quyền sở hữu private key hợp lệ.

### 1.2 Nội dung quan trọng của chứng thư X.509

Chứng thư thường có những thuộc tính như:

- **Subject distinguished name (DN):** định danh chủ thể, ví dụ `CN=alice,OU=Engineering,O=Example,C=VN`.
- **Issuer DN:** đơn vị/cơ quan cấp chứng thư.
- **Serial number:** số sê-ri chứng thư do issuer cấp; thường cần kết hợp issuer để nhận diện bản cấp cụ thể.
- **Public key:** dùng trong quá trình kiểm tra bằng chứng sở hữu private key.
- **Validity:** `Not Before` và `Not After`, khoảng hiệu lực chứng thư.
- **Subject Alternative Name (SAN):** có thể chứa email, URI, DNS, IP hoặc định danh khác, tùy hồ sơ PKI.
- **Key Usage / Extended Key Usage (EKU):** ràng buộc mục đích sử dụng; chứng thư client thường được cấp cho `clientAuth`.
- **Chữ ký/chuỗi tin cậy:** chứng thư được nối với root/intermediate CA hoặc trust anchor mà server tin cậy theo chính sách.

**Chỉ đọc chuỗi subject không có nghĩa chứng thư đã được kiểm tra.** Điều kiện quan trọng là subject phải đến từ **chứng thư mà thành phần TLS đáng tin cậy đã xác minh**, chứ không phải một chuỗi header HTTP do caller tự gửi.

## 2. Luồng từ TLS đến SecurityContext trong ứng dụng Servlet

```text
Client (browser, curl, service)
        │  HTTPS + chứng thư client
        ▼
TLS endpoint (embedded Tomcat / ingress)
        │  Xác minh chain, trust, validity, purpose
        │  và bằng chứng sở hữu private key
        ▼
Servlet request có chứng thư đã xác minh
        │  thuộc tính chuẩn "jakarta.servlet.request.X509Certificate"
        ▼
Spring Security Filter Chain
        │
        └── X509AuthenticationFilter
                 │ trích xuất subject/principal
                 │ (ví dụ CN=alice -> "alice")
                 ▼
            Pre-authentication provider
                 │ tải UserDetails / tài khoản
                 ▼
            Authentication trong SecurityContext
                 │ principal = alice
                 │ authorities = ROLE_READER
                 ▼
            Authorization (requestMatchers, @PreAuthorize, ...)
                 │
                 ▼
            Controller / Service
```

### 2.1 mTLS là phần việc của TLS endpoint

Khi dùng **embedded Tomcat**, các thuộc tính `server.ssl.*` của Spring Boot điều khiển TLS connector. Khi bật `server.ssl.client-auth: need`, Tomcat yêu cầu chứng thư client tại TLS handshake. Trong trường hợp chứng thư bị từ chối hoặc không có chứng thư bắt buộc, kết nối có thể thất bại **trước khi HTTP request đi vào Spring Security**. Vì thế, đây thường là lỗi TLS/handshake, **không nhất thiết là HTTP 401/403**.

Khi bắt tay TLS thành công, servlet container thường cung cấp một mảng `java.security.cert.X509Certificate[]` qua request attribute `jakarta.servlet.request.X509Certificate`. Spring Security đọc thông tin này bằng cơ chế pre-authentication, thay vì yêu cầu client gửi mật khẩu trong body.

### 2.2 Spring Security sử dụng subject để nhận diện tài khoản

`X509AuthenticationFilter` là bộ lọc xử lý authentication dựa trên chứng thư client. Nó trích xuất một principal từ certificate subject; mặc định phổ biến dùng **Common Name (CN)**. Với subject:

```text
CN=alice,OU=Engineering,O=Example,C=VN
```

biểu thức:

```regex
CN=(.*?)(?:,|$)
```

lấy `alice` làm tên principal trong trường hợp DN đơn giản này.

Sau đó một `UserDetailsService` có thể tải tài khoản `alice`, kiểm tra tài khoản còn được phép truy cập hay không, rồi cung cấp authorities như `ROLE_READER`. Các authority này được dùng bởi `authorizeHttpRequests` hoặc method security.

**Chú ý:** regex trên dành cho **minh họa**; chuỗi DN có thể có escaping, thứ tự RDN khác nhau, dấu phẩy nằm trong giá trị, chữ hoa/thường và quy tắc chuẩn hóa. Hơn nữa, **CN có thể trùng** giữa người dùng hoặc giữa CA khác nhau. Trong hệ thống production, không nên dựa vào CN đơn lẻ nếu PKI không bảo đảm duy nhất và quản trị vòng đời định danh.

### 2.3 Client-auth “need” và “want”

| Cấu hình TLS | Hành vi chính | Hệ quả với Spring Security |
| --- | --- | --- |
| `server.ssl.client-auth: need` | Yêu cầu client cung cấp chứng thư được tin cậy. | Không có cert hợp lệ thường thất bại tại TLS; endpoint `permitAll` cũng không vượt được yêu cầu TLS. |
| `server.ssl.client-auth: want` | Yêu cầu nhưng có thể chấp nhận kết nối không có cert. | Nếu không có cert, X.509 authentication không có danh tính từ chứng thư; endpoint bảo vệ vẫn cần cơ chế xác thực khác. |
| `server.ssl.client-auth: none` | Không yêu cầu chứng thư client. | Không có cơ sở cho luồng X.509 trên connector này. |

Không dùng `want` như cách “bỏ qua” xác thực trên endpoint nhạy cảm. Nó chỉ thay đổi yêu cầu ở **TLS**, còn ứng dụng vẫn phải có chính sách authorization. Nếu muốn endpoint công khai không cần cert và endpoint quản trị bắt buộc cert trên cùng hostname, cần thiết kế connector/ingress/filter chains có ranh giới rõ ràng, vì `client-auth: need` áp dụng **tại TLS connector**, không chỉ cho một URL.

## 3. Ví dụ hoàn chỉnh: Spring Boot 3 + Spring Security 6 + mTLS

Mục tiêu: chạy HTTPS ở `https://localhost:8443`, chỉ chứng thư client tin cậy mới bắt tay TLS thành công, subject `CN=alice` được ánh xạ thành tài khoản `alice` với quyền `ROLE_READER`. Endpoint `GET /whoami` trả thông tin tài khoản/authorities, **không trả private key hoặc chứng thư gốc**.

Tạo project bằng Spring Initializr, chọn **Gradle, Java 17+, Spring Boot 3.x, Spring Web, Spring Security**. Giữ lại Gradle wrapper (`gradlew` / `gradlew.bat`) do Initializr tạo. Nếu tự khai báo dependency cho một project Spring Boot 3.x đã được cấu hình, cần hai starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Các file Java tiếp theo đặt trong package `com.example.x509demo`. Đây là một **ứng dụng Spring Boot**, vì vậy phải chạy bằng Maven/Gradle có Spring trên classpath; không phải chương trình chỉ dùng `javac` độc lập.

### 3.1 Cấu hình HTTPS và truststore của client

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./server.p12
    key-store-type: PKCS12
    key-store-password: ${TLS_SERVER_STORE_PASSWORD}
    trust-store: file:./trusted-clients.p12
    trust-store-type: PKCS12
    trust-store-password: ${TLS_CLIENT_TRUSTSTORE_PASSWORD}
    client-auth: need
```

Ý nghĩa:

- `server.p12` chứa **private key và chứng thư server**, dùng để thiết lập HTTPS.
- `trusted-clients.p12` chứa các **trust anchor/chứng thư client được tin cậy** trong bài thực hành. Khi triển khai thật, thường quản lý root/intermediate CA và chính sách phát hành phù hợp thay vì import thủ công từng chứng thư người dùng.
- `client-auth: need` bắt buộc client cung cấp chứng thư ở kết nối TLS.
- Hai password đọc từ biến môi trường để không đưa giá trị bí mật vào YAML. Không dùng mật khẩu demo cho khóa production.
- `file:./...` được giải quyết tương đối với **working directory khi chạy tiến trình**; trong ví dụ các file `.p12` nằm ở thư mục gốc project.

**Đường tin cậy khác nhau:** client (browser/curl) phải tin **chứng thư server**, còn server phải tin **chứng thư client**. Thêm client cert vào truststore của server không khiến browser tự tin server, và ngược lại.

### 3.2 Cấu hình SecurityFilterChain ánh xạ CN

**`src/main/java/com/example/x509demo/SecurityConfig.java`**

```java
package com.example.x509demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        // Tài khoản demo; password KHÔNG được dùng cho X.509 pre-auth.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-for-x509")
                .roles("READER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").hasRole("READER")
                .anyRequest().authenticated()
            )
            .x509(x509 -> x509
                .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                .userDetailsService(users)
            );

        return http.build();
    }
}
```

Các phần cần hiểu:

1. `.x509(...)` bật đường xác thực chứng thư client trong **Servlet Security Filter Chain**.
2. `subjectPrincipalRegex(...)` quy định cách trích principal từ subject DN. Ví dụ `CN=alice` trở thành chuỗi `alice`.
3. `userDetailsService(users)` tải tài khoản cùng authorities ứng với principal. Nó **không kiểm tra chuỗi TLS**; TLS container phải hoàn tất bước đó trước.
4. `hasRole("READER")` kiểm tra authority `ROLE_READER`. Certificate được tin cậy **chưa đủ** nếu tài khoản bị xóa/khóa hoặc thiếu quyền.
5. Mật khẩu `{noop}not-used-for-x509` chỉ giúp tạo `UserDetails` cho bài demo; xác thực X.509 dùng certificate/private key, không gửi password này. Trong production, lấy tài khoản và quyền từ hệ thống danh tính đáng tin, áp dụng chính sách vô hiệu hóa tài khoản và quản lý vòng đời.

**Quan trọng:** Khi muốn kiểm tra người dùng vẫn hợp lệ sau mỗi lần cấp chứng thư hoặc thay đổi quyền, phải xem rõ cơ chế caching/session và cách thu hồi phiên; đừng cho rằng certificate sẽ được xác minh lại trên mỗi HTTP request (có thể có TLS session resumption, connection reuse, cache ứng dụng).

### 3.3 Controller hiển thị tài khoản đã xác thực

**`src/main/java/com/example/x509demo/WhoAmIController.java`**

```java
package com.example.x509demo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Map<String, Object> whoami(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList()
        );
    }
}
```

`authentication.getName()` trả tên tài khoản mà Spring Security đã xác thực, **không nhất thiết là toàn bộ subject DN**. Cách trả authorities giúp quan sát mapping, nhưng endpoint thật không nên tiết lộ cấu trúc quyền nhạy cảm hơn mức cần thiết.

**`src/main/java/com/example/x509demo/X509DemoApplication.java`**

```java
package com.example.x509demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class X509DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(X509DemoApplication.class, args);
    }
}
```

Đặt chính xác tên file trùng public class. Các method `stream().toList()` dùng cú pháp/API Java 16+, nên **Java 17** đáp ứng. Ứng dụng không cần controller tự đọc chứng thư để login: filter Spring Security chịu trách nhiệm.

## 4. Tạo cặp chứng thư demo bằng keytool

Các lệnh sau **chỉ dùng để học và thử trên máy cá nhân**. Chúng tạo **self-signed server certificate** và một **self-signed client certificate** rồi tin cậy cụ thể chứng thư client đó. Production nên có PKI/CA đã quản trị, chứng thư đúng EKU, cấp phát/thu hồi/rotation có quy trình và bảo vệ private key bằng storage thích hợp.

Chạy các lệnh trong **thư mục gốc project** (nơi chứa `build.gradle` và `application.yml` tham chiếu `file:./...`). Công cụ `keytool` đi cùng JDK.

### 4.1 Tạo khóa/chứng thư server cho localhost

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost,OU=Learning,O=Example,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "EKU=serverAuth"

keytool -exportcert \
  -alias localhost -keystore server.p12 \
  -storepass changeit -rfc -file server.crt
```

File `server.p12` chứa private key của server: **không gửi file đó cho client**. File `server.crt` là chứng thư công khai dùng cho `curl --cacert` trong môi trường dev. Server certificate self-signed không được browser tin mặc định; browser cần trust anchor đúng (chỉ thêm vào kho tin cậy của máy test, không biến certificate demo thành trust anchor dùng chung).

### 4.2 Tạo chứng thư client CN=alice

```bash
keytool -genkeypair \
  -alias alice \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore alice.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=alice,OU=Learning,O=Example,C=VN" \
  -ext "EKU=clientAuth"

keytool -exportcert \
  -alias alice -keystore alice.p12 \
  -storepass changeit -rfc -file alice.crt
```

`alice.p12` chứa **private key** của client và chứng thư; **alice.crt** chỉ chứa chứng thư công khai. Không chép `alice.p12` vào repository, frontend JavaScript, Docker image công khai hay hệ thống log.

### 4.3 Cấp quyền tin cậy cho client ở server

```bash
keytool -importcert \
  -alias alice \
  -file alice.crt \
  -keystore trusted-clients.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
```

Trong demo này, `trusted-clients.p12` chứa chứng thư client `alice` làm trust anchor. Khi dùng PKI thật, server thường tin CA được kiểm soát, còn cơ chế kiểm tra tài khoản quyết định từng user nào được phép truy cập. **Trust client certificate** và **map account** là hai cấu hình khác nhau.

Xác minh file local nếu cần:

```bash
keytool -list -v \
  -keystore alice.p12 -storetype PKCS12 -storepass changeit
```

Kiểm tra `Owner: CN=alice,...`, issuer, validity và EKU phù hợp. Đầu ra thực tế có fingerprints/metadata riêng theo chứng thư vừa tạo; bài học không giả định một fingerprint cố định.

### 4.4 Khởi chạy ứng dụng

Đặt hai biến môi trường đã tham chiếu trong YAML. Trên macOS/Linux:

```bash
TLS_SERVER_STORE_PASSWORD=changeit \
TLS_CLIENT_TRUSTSTORE_PASSWORD=changeit \
./gradlew bootRun
```

Trên **Windows PowerShell**, đặt biến trước rồi chạy wrapper:

```powershell
$env:TLS_SERVER_STORE_PASSWORD = "changeit"
$env:TLS_CLIENT_TRUSTSTORE_PASSWORD = "changeit"
.\gradlew.bat bootRun
```

Mật khẩu `changeit` chỉ để lệnh demo có thể tái hiện trong môi trường cục bộ; không dùng cho production. Nếu thiếu `server.p12`, `trusted-clients.p12` hoặc sai password, Tomcat có thể không khởi động HTTPS; đây là lỗi cấu hình TLS, chưa liên quan tới việc Spring Security tìm user.

## 5. Kiểm tra end-to-end bằng curl và trình duyệt

### 5.1 Có chứng thư alice hợp lệ

Với phiên bản curl sử dụng TLS backend hỗ trợ PKCS#12 (ví dụ bản dùng OpenSSL), chạy:

```bash
curl -i \
  --cacert server.crt \
  --cert-type P12 \
  --cert alice.p12:changeit \
  https://localhost:8443/whoami
```

`--cacert server.crt` xác minh chứng thư **server**. `--cert-type P12 --cert alice.p12:changeit` nạp chứng thư và private key **client**. Không dùng `-k`/`--insecure` để “sửa” lỗi trust trong bài học; lệnh nên kiểm tra đầy đủ HTTPS.

Khi cả mTLS và mapping account thành công, response chứa HTTP **200 OK** và JSON tương đương:

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
```

Thứ tự khóa JSON có thể khác, vì `Map.of(...)` không bảo đảm thứ tự. Đây là **kết quả dự kiến theo cấu hình ví dụ**, không phải một transcript đã chạy trong mọi môi trường. Nếu curl của Windows dùng TLS backend khác (như Schannel), cú pháp nhập certificate/store có thể khác; hãy xem `curl -V` và tài liệu backend của bản curl đó.

### 5.2 Không gửi client certificate

```bash
curl -i --cacert server.crt https://localhost:8443/whoami
```

Với `client-auth: need`, kết nối không có client certificate hợp lệ thường bị **từ chối tại TLS handshake**, trước khi Spring Security xử lý HTTP. Tùy TLS version/curl, output có thể là TLS alert hoặc lỗi connection; **đừng khẳng định bắt buộc phải có status 401**.

### 5.3 Có chứng thư nhưng không được cấp quyền tài khoản

Có thể thử thêm một chứng thư client `CN=bob` được server trust **trong môi trường test**, nhưng **không thêm user `bob`** vào `UserDetailsService`. Khi đó mTLS có thể thành công, nhưng bước map principal sang account sẽ không thành công. Kết quả HTTP tùy authentication entry point, có thể là 401/403 hoặc hành vi xác thực khác của cấu hình. Đây là **lỗi application identity mapping**, khác với lỗi PKI của một chứng thư không tin cậy.

Ngay cả khi `bob` tồn tại nhưng không có `ROLE_READER`, `/whoami` phải bị từ chối bởi rule `hasRole("READER")`. Điều này chứng minh **certificate valid ≠ authorized**.

### 5.4 Trình duyệt desktop

Khi dùng Chrome/Edge/Firefox:

1. Browser phải tin **server certificate/CA** tương ứng; chứng thư self-signed trong demo cần trust local đúng cách.
2. Import chứng thư client `alice.p12` vào **cửa hàng chứng thư cá nhân được browser/OS dùng**, với private key bảo vệ. Browser có thể hỏi chọn chứng thư khi server yêu cầu.
3. Mở `https://localhost:8443/whoami`. Nếu chọn alice và handshake hợp lệ, ứng dụng sẽ map account như curl.
4. Khi lỗi, xem phần Certificate/TLS trong DevTools và logs của Tomcat/Spring (đã che thông tin nhạy cảm). Một số browser cache lựa chọn client certificate và có thể tái sử dụng TLS session, nên thao tác đổi cert đôi khi cần đóng session/browser context hoặc test bằng curl độc lập.

**Chứng thư client không phải một header do JavaScript tùy ý gán.** Private key phải được dùng trong TLS handshake thông qua browser/OS hoặc TLS library. Các API Fetch không có tùy chọn `clientCertificate: "alice"` chung để tự tạo mTLS từ string.

## 6. Subject DN mapping: ưu điểm, giới hạn và thiết kế production

### 6.1 Vì sao CN phù hợp cho demo nhưng chưa đủ cho production?

Giả sử hai chứng thư đều được CA tin cậy cấp, một cái của `CN=alice,OU=Sales` và một cái của `CN=alice,OU=Contractor`. Nếu cấu hình chỉ lấy `CN=alice`, cả hai có thể bị map về **cùng tài khoản alice**, dù chính sách nghiệp vụ muốn phân biệt. Ngay cả khi issuer khác nhau nhưng cả hai đều nằm trong tập trust, CN vẫn có thể trùng.

Ngoài ra, DN có thể có RDN được escape hoặc chuẩn hóa khác với regex đơn giản; việc đổi tên user/đơn vị cũng làm thay đổi subject. Không nên gắn đặc quyền cao vào CN chưa có chính sách duy nhất và xác minh tin cậy.

**Chiến lược production phổ biến:**

- **Quản lý CA:** chỉ tin những CA được quyền cấp chứng thư client cho nhóm ứng dụng; kiểm tra certificate profile, EKU, key usage và lịch thu hồi. Không chấp nhận bất kỳ CA công cộng nào chỉ vì có chứng thư đúng cú pháp.
- **Định danh rõ ràng:** chọn certificate identity ổn định do PKI quản lý, chẳng hạn SAN URI/otherName theo quy ước doanh nghiệp hoặc thông tin issuer+serial. Xác định cách rotation/renewal chuyển sang chứng thư mới mà vẫn map đúng account.
- **Ánh xạ ở backend:** tra directory/DB đáng tin cậy để gắn certificate identity với account ID, active/disabled state, tenant, roles; không tự động cấp quyền khi chỉ đọc được một CN.
- **Không trả authority từ client:** `ROLE_ADMIN` hay `tenantId` phải đến từ policy/account store đã kiểm soát, không phải text do caller tự nhập.
- **Theo dõi và thu hồi:** quản lý hết hạn, thu hồi/mất private key, thay thế cert, thay đổi vai trò, vô hiệu hóa tài khoản; yêu cầu session invalidation/reauth khi phù hợp.
- **Đối chiếu mức tin cậy:** issuer DN riêng lẻ cũng chưa phải bằng chứng đủ để kết luận “đúng CA”; phụ thuộc vào trust validation từ TLS và profile/anchor cụ thể.

Nếu ứng dụng cần mapping mạnh hơn CN regex, có thể tùy biến **X.509 principal extraction / pre-authenticated user-details resolution** của Spring Security để xây principal từ thông tin certificate đã được TLS xác minh, rồi tìm account. Nên dùng parser DN/SAN đúng chuẩn thay vì cắt chuỗi regex tùy ý. Giữ đường kiểm tra TLS đáng tin cậy khi thay cơ chế trích xuất.

### 6.2 Phân biệt account identity và bản cấp certificate

Số sê-ri + issuer giúp tham chiếu **một bản cấp** chứng thư cụ thể, thuận tiện cho audit và thu hồi, nhưng khi renew sẽ có serial mới. SAN identity ổn định (theo profile PKI) có thể thuận tiện hơn để gắn account lâu dài, nhưng phải do CA kiểm soát và được ứng dụng kiểm tra đúng semantics. Một mapping production nên xác định:

1. **User/Service ID** nào là định danh bất biến của hệ thống?
2. Những chứng thư nào được phép đại diện cho ID đó?
3. Khi renew/revoke/đổi CA hoặc khóa tài khoản, mapping nào bị thay đổi/thu hồi?
4. Cách ứng dụng kiểm tra quyền hiện tại sau khi xác thực certificate là gì?

Certificate mang identity, còn **authorization policy** là quyết định riêng dựa trên account/resource.

## 7. Reverse proxy, load balancer và ranh giới tin cậy

Ví dụ trên giả định **TLS handshake xảy ra trực tiếp ở embedded Tomcat**. Trong production, thường có ingress, WAF hoặc load balancer terminate TLS:

```text
Client -- mTLS --> Ingress/LB -- HTTP/HTTPS --> Spring Boot
                        │                    │
                  Verify cert          Servlet có thể KHÔNG
                  ở ingress            thấy X509Certificate[]
```

Khi TLS kết thúc tại proxy, servlet container phía sau thường **không nhận trực tiếp chứng thư client** như khi bắt tay mTLS tại Tomcat. Vì vậy, bật `http.x509()` trong backend **không đủ** nếu request không có certificate attribute đã được thành phần đáng tin cậy cung cấp.

Có hai hướng kiến trúc chính:

- **TLS passthrough:** proxy chuyển tiếp TLS mà không terminate; Tomcat thực hiện mTLS và có chứng thư client thật. Cần hạ tầng hỗ trợ và định tuyến thích hợp.
- **TLS termination và trusted identity forwarding:** ingress thực hiện xác minh client cert, sau đó truyền thông tin danh tính/chứng thư qua **kênh backend được bảo vệ và xác thực** cho ứng dụng; backend phải xác minh nguồn truyền và ánh xạ thông tin đó bằng cơ chế tích hợp rõ ràng, thay vì mặc định tin mọi request header.

**Lỗi bảo mật nghiêm trọng:** cho phép caller từ Internet gửi `X-Client-Cert: CN=admin` rồi backend coi chuỗi này là danh tính đã được xác thực. Header HTTP có thể bị **giả mạo** nếu truy cập trực tiếp backend hoặc proxy không xóa header do client gửi.

Để tránh giả mạo:

1. Ingress phải **xác minh chứng thư client** theo CA/policy được phép và chỉ công bố identity sau bước xác minh.
2. Proxy **xóa/ghi đè** mọi header identity nhạy cảm do client gửi; không chỉ “thêm một header” lên trước header do caller tạo.
3. Backend chỉ cho phép traffic từ proxy tin cậy, lý tưởng qua mTLS hoặc kênh mạng được bảo vệ; không công khai đường bypass đến Spring Boot.
4. Kiểm tra rõ định dạng/encoding của certificate DN/header; không parse tùy tiện từ chuỗi không đáng tin.
5. Đặt một **authentication adapter** đúng trust model để chuyển verified identity thành `Authentication`, áp dụng mapping account và authorization như bình thường.
6. Giám sát logging và audit theo certificate identity đã xác minh; không ghi private key, access tokens hay toàn bộ dữ liệu cá nhân không cần thiết.

**Đừng coi `X-Forwarded-Proto`, `Forwarded` hay mọi header “client-cert” là bằng chứng X.509 authentication.** Chúng có thể phục vụ routing/URL generation, nhưng không tự chứng minh client sở hữu private key.

## 8. Kết hợp X.509 với session, CSRF và các hình thức login khác

### 8.1 mTLS authentication không thay thế authorization

Spring Security có thể gắn `Authentication` sau khi map principal. Authorization vẫn dùng request matchers/method security và kiểm tra dữ liệu ở service. Ví dụ `hasRole("READER")` chỉ cho biết user có role; nếu API đọc hóa đơn theo ID, backend vẫn phải kiểm tra user có quyền với **hóa đơn đó** hay không.

### 8.2 mTLS không tự giải quyết CSRF

Khi trình duyệt tự gửi cookie **hoặc tự chọn/ghi nhớ client certificate** trên kết nối TLS, client authentication là một dạng **ambient credential** trong ngữ cảnh browser. Một website khác có thể kích hoạt những request từ trình duyệt nạn nhân trong một số điều kiện; vì vậy **không tắt CSRF chỉ vì app dùng X.509**.

Trong cấu hình ví dụ, Spring Security vẫn có bảo vệ CSRF mặc định cho những phương thức thay đổi trạng thái. `GET /whoami` không cần token CSRF. Nếu bạn làm API machine-to-machine chỉ nhận client certificate và **không dùng browser/cookie credential**, yêu cầu CSRF có thể khác; phải đánh giá riêng rồi mới chọn security matcher/cơ chế phù hợp, thay vì `csrf.disable()` toàn bộ ứng dụng.

### 8.3 Session và chứng thư có vòng đời khác nhau

Certificate có thời hạn, có thể bị revoke, và TLS connection có thể tái sử dụng. Trong khi đó, `SecurityContext`/session có thể tiếp tục giữ trạng thái authentication tùy cách ứng dụng cấu hình. Khi cần hiệu lực thu hồi ngay, phải thiết kế chiến lược **session timeout, re-authentication, kiểm tra trạng thái account, TLS revocation** và các sự kiện revoke/rotate, không giả định certificate được kiểm tra lại ở mỗi HTTP request.

### 8.4 Nhiều cơ chế xác thực trong một ứng dụng

Một ứng dụng có thể phục vụ nhân viên qua X.509 và người dùng ngoài qua OIDC, hoặc service qua mTLS và browser qua form login. Cần xác định **endpoint, connector, SecurityFilterChain và authentication entry point** cho mỗi loại. `client-auth: need` ở một connector sẽ chặn client không có chứng thư trước Spring, bất kể controller public hay `permitAll`. Nếu cùng hostname phải hỗ trợ cả browser công khai và mTLS, thường cần một thiết kế ingress/connector/domain phân tách thích hợp.

**X.509 và OIDC không đồng nhất:** X.509 client certificate có thể đại diện cho thiết bị/service hoặc danh tính người dùng theo PKI; OIDC cung cấp ID token và identity claims từ OpenID Provider. Một chứng thư hợp lệ không tự cấp scopes OAuth2 hoặc OIDC roles, và một OIDC login không mặc nhiên cung cấp client certificate cho mTLS.

## 9. Chẩn đoán lỗi theo từng lớp

| Dấu hiệu | Lớp cần kiểm tra | Nguyên nhân và cách xử lý |
| --- | --- | --- |
| Server không khởi động HTTPS | Cấu hình TLS | Sai đường dẫn/mật khẩu `server.p12` hoặc truststore, keystore không có private key, cert không phù hợp. Kiểm tra startup log an toàn. |
| Client nhận TLS handshake error trước khi thấy HTTP status | TLS client auth | Không có cert, client cert không được trust, hết hạn, sai EKU hoặc chain không hợp lệ. Kiểm tra cert selection và server truststore. |
| curl báo certificate verify failed | Xác minh server | Client chưa tin `server.crt` hoặc SAN hostname không khớp. Dùng đúng CA/certificate trust và hostname; đừng dùng `-k`. |
| mTLS thành công nhưng request 401/403 | Spring authentication/authorization | CN extract sai, không tìm thấy account, account disabled hoặc thiếu authority. Kiểm tra user mapping và rule. |
| CN regex đọc sai tên | DN parsing | Subject có escaped comma, cấu trúc phức tạp hoặc RDN khác dự kiến. Dùng principal extractor/PKI identity parser phù hợp. |
| Cert của người A map nhầm tài khoản người B | Identity binding | Chỉ so CN nhưng CN không duy nhất. Rà issuer, SAN/serial và mapping database/PKI. |
| Spring không thấy chứng thư khi dùng ingress | TLS termination | Cert đã được proxy kiểm tra, không truyền đến Servlet container. Thiết kế trusted identity bridge hoặc TLS passthrough. |
| Chỉ thêm `X-Client-Cert` thì đăng nhập được | Trust boundary bị phá | Header có thể bị giả mạo. Chặn bypass, xóa header ngoài, xác minh tại proxy và bảo vệ hop backend. |
| GET chạy nhưng POST bị 403 | CSRF hoặc quyền | Với browser/ambient credentials, cần CSRF token đúng; không gộp mọi 403 thành lỗi mTLS. |
| Cert hết hạn/revoke nhưng phiên còn truy cập | Vòng đời phiên/TLS | Cache/session/connection reuse hoặc revocation không được áp dụng. Thiết kế session invalidation, revocation và reauth. |

### 9.1 Lớp logging cần quan sát

- **TLS/connector logs:** nguyên nhân handshake, trust chain, certificate selection, hostname/server certificate, lỗi revocation/validity.
- **Spring Security logs:** filter chain áp dụng, principal sau extractor, kết quả tải user và quyết định authorization. Bật log chi tiết **chỉ trong môi trường debug có kiểm soát**, sau đó tắt.
- **Application audit:** account ID, issuer/serial hoặc định danh chứng thư đã chuẩn hóa, action, resource, outcome, request correlation. Hạn chế ghi subject đầy đủ nếu có thông tin cá nhân không cần thiết.
- **Reverse proxy logs:** xác nhận client-auth thực sự được thực thi ở ingress và backend không thể bị gọi bypass.

Khi debug, phân biệt **TLS đã tạo được HTTP request chưa?** Nếu chưa, không sửa `UserDetailsService`. Nếu HTTP request đến Spring nhưng principal null/sai, kiểm tra attribute/certificate extractor/identity bridge. Nếu principal đúng nhưng 403, kiểm tra quyền và CSRF.

## 10. Quy trình chọn thiết kế X.509 trong ứng dụng thật

| Câu hỏi | Quyết định nên ghi rõ |
| --- | --- |
| Ai cấp chứng thư client? | CA nội bộ, PKI doanh nghiệp hoặc nguồn tin cậy được phép. |
| Chứng thư nhận diện ai? | Con người, máy, workload, hoặc thiết bị; có thể cần account/service identity khác nhau. |
| TLS kết thúc ở đâu? | Tomcat trực tiếp hay ingress/LB; ai thực hiện PKIX/trust/revocation? |
| Principal được lấy từ đâu? | CN demo hay SAN/issuer+serial/identity profile đã quản trị. |
| Ánh xạ principal sang tài khoản thế nào? | UserDetailsService hoặc custom pre-auth mapping có trạng thái active/roles/tenant. |
| Thu hồi/rotation hoạt động ra sao? | CA revocation, thay cert, invalidation phiên, cập nhật mapping và audit. |
| Có browser không? | Nếu browser dùng ambient credentials, kiểm tra CSRF, session và cert selection. |
| Có nguồn danh tính khác không? | Phân tách filter chain/connector/OIDC/API theo đúng boundary. |

**Ghi nhớ:** Trong Spring Security Servlet, X.509 authentication là **pre-authentication**: **TLS endpoint** kiểm tra chứng thư client và bằng chứng sở hữu private key; **Spring Security** trích xuất principal từ chứng thư đã xác minh, tra tài khoản/authorities và áp dụng authorization. Regex lấy `CN` đủ để học cơ chế, nhưng production cần quản trị **trust, unique identity mapping, revocation, rotation, session và reverse-proxy trust boundary**.
