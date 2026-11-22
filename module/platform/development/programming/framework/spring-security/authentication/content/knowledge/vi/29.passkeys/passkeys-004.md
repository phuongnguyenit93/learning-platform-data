# Relying Party ID, allowed origins và yêu cầu HTTPS trong Passkey/WebAuthn

## 1. Bài toán: vì sao một passkey có thể hoạt động ở domain này nhưng thất bại ở domain khác?

Ứng dụng Spring Security hỗ trợ **passkey** để người dùng đăng nhập bằng WebAuthn/FIDO2. Khi đăng ký, authenticator tạo cặp khóa; server lưu public key và credential metadata. Khi xác thực, authenticator ký dữ liệu của challenge và server xác minh chữ ký. Không có password chung được gửi qua mạng như trong đăng nhập truyền thống.

Giả sử website mở tại `https://login.example.com`, còn backend chạy sau reverse proxy ở `http://passkey-service:8080`. Một cấu hình passkey an toàn phải trả lời ba câu hỏi:

1. **Relying Party ID (RP ID) là gì?** Chẳng hạn `example.com` hoặc `login.example.com`. RP ID xác định phạm vi miền của credential.
2. **Allowed origins là gì?** Chẳng hạn chỉ `https://login.example.com`; đây là các origin cụ thể được server cho phép thực hiện WebAuthn ceremony.
3. **Trang web có secure context không?** Trong production phải phục vụ trang bằng HTTPS với chứng chỉ hợp lệ; HTTP `localhost` có ngoại lệ cho phát triển cục bộ.

Nếu RP ID không hợp lệ, browser có thể từ chối ngay bằng `SecurityError`. Nếu browser cho tạo assertion nhưng `origin` không được server tin cậy, backend phải từ chối. Nếu TLS/forwarded host cấu hình sai, đăng ký và xác thực có thể bị lỗi dù mã Java xử lý chữ ký là đúng.

**Mục tiêu học tập:** phân biệt RP ID, origin và URL; thiết kế nhiều subdomain/port; cấu hình `HttpSecurity.webAuthn()` của Spring Security 6.5; hiểu `rpIdHash` và `clientDataJSON.origin`; kiểm thử localhost/HTTPS; giải quyết sai host do reverse proxy và migration domain mà không bỏ kiểm tra bảo mật.

## 2. Bốn chủ thể trong WebAuthn

| Chủ thể | Vai trò | Thông tin liên quan |
| --- | --- | --- |
| **End user** | Yêu cầu đăng ký/đăng nhập; tương tác biometric/PIN khi authenticator cần | Người dùng không cần biết private key |
| **Browser/WebAuthn client** | Chạy `navigator.credentials.create/get`, kiểm tra origin và giới hạn RP ID | Origin trang đang hoạt động, challenge, RP ID request |
| **Authenticator/passkey provider** | Sinh/lưu/sử dụng credential và ký dữ liệu | Private key, `authenticatorData`, `rpIdHash`, UP/UV flags |
| **Relying Party server** | Cấp challenge, lưu public key, xác minh response, cấp phiên sau xác thực thành công | RP ID và allowed origins cấu hình, public key, credential ID/account binding |

WebAuthn server có thể chạy ở nhiều instance hoặc sau proxy; **RP ID không phải tên host của JVM/container**. Browser nhìn thấy địa chỉ public; điều đó mới quyết định origin gọi API.

Sơ đồ:

~~~text
User / Browser tại https://login.example.com
    |
    | GET/POST WebAuthn options và response qua HTTPS
    v
Reverse proxy / TLS termination
    |
    | HTTP nội bộ chỉ khi trust boundary cho phép
    v
Spring Security WebAuthn RP
    |
    +-- RP ID: example.com
    +-- allowed origins: https://login.example.com
    +-- credential public keys, challenge/session, user mapping
~~~

## 3. RP ID là một domain string, không phải nguyên URL

**RP ID** là miền mà credential được gắn với theo quy tắc WebAuthn. Nó **không chứa** scheme `https://`, port, đường dẫn, query, fragment hay wildcard.

~~~text
Đúng:   example.com
Đúng:   login.example.com
Lab:    localhost

Sai:    https://example.com
Sai:    login.example.com:443
Sai:    https://login.example.com/login
Sai:    *.example.com
Sai:    com
Sai:    co.uk
~~~

Theo quy tắc WebAuthn thông thường, RP ID phải **bằng effective domain của origin đang gọi**, hoặc là một **registrable domain suffix** của effective domain đó. Không được lấy public suffix như `com` hay `co.uk`. Để phân biệt public suffix và registrable domain trong thực tế cần dữ liệu/chính sách tương ứng, không tự kết luận bằng cách đếm số dấu chấm.

### 3.1. Ví dụ chính xác với subdomain

Browser đang ở `https://login.example.com:8443`:

| RP ID | Hợp lệ trong quy tắc thông thường? | Lý do |
| --- | --- | --- |
| `login.example.com` | Có | Bằng host của origin |
| `example.com` | Có | Hậu tố miền có thể đăng ký |
| `m.login.example.com` | Không | Là **subdomain sâu hơn**, không phải suffix |
| `app.example.com` | Không | Sibling hostname, không phải suffix của `login.example.com` |
| `evil-example.com` | Không | Chỉ trông giống chuỗi; không cùng domain |
| `com` | Không | Public suffix |
| `https://example.com` | Không | Sai định dạng RP ID |

Nếu chọn `rpId=example.com`, cả `login.example.com` và `app.example.com` có khả năng yêu cầu credential cho RP ID đó, nhưng điều này **không tự động** có nghĩa server nên tin cả hai origin. Origin allowlist phía server là bước kiểm tra độc lập.

**Không so miền bằng `host.endsWith("example.com")` tùy tiện**: `evil-example.com` có thể khớp chuỗi suffix đơn giản trong một số cách xử lý sai. Việc triển khai RP ID phải dựa vào thư viện WebAuthn/browser chuẩn và domain policy đã phê duyệt.

### 3.2. Đừng vô tình mở phạm vi cho tenant/preview host

Nếu tổ chức sở hữu `example.com` nhưng các subdomain như `preview.example.com`, `customer-123.example.com` hoặc `blog.example.com` do nhiều đội/khách hàng vận hành, chọn RP ID cấp cha có tác động an ninh. Một script độc hại trên subdomain không được tin cậy có thể cố khởi phát WebAuthn ceremony cho RP ID cấp cha nếu browser eligibility cho phép. **Server phải chặn origin ngoài allowlist**, đồng thời cần quản lý XSS/supply-chain cho các origin được phép.

Nếu chỉ một hostname dùng passkeys, RP ID hẹp như `login.example.com` có thể dễ kiểm soát hơn. Nếu cần dùng chung credential cho nhiều subdomain, chọn `example.com` có chủ đích và giới hạn allowlist.

## 4. Origin là bộ ba scheme + host + port

**Origin** nhận diện xuất xứ của trang đang gọi WebAuthn. Các origin sau khác nhau:

~~~text
https://login.example.com
https://login.example.com:8443
https://app.example.com
http://login.example.com
~~~

Không có `/login` hay `/settings/security` trong origin. Khi dùng port mặc định, browser thường biểu diễn `https://login.example.com:443` thành `https://login.example.com`. Cấu hình allowed origins nên dùng dạng origin chuẩn, không ghép chuỗi từ một URL path.

Ví dụ server muốn chỉ cho phép:

~~~text
RP ID: example.com
Allowed origins:
  https://login.example.com
  https://app.example.com
~~~

Server phải từ chối:

~~~text
https://evil.example.com
https://preview.example.com
http://login.example.com
https://login.example.com:8443    # trừ khi phê duyệt riêng port 8443
~~~

Port là chi tiết quan trọng: **RP ID không có port, nhưng origin có**. Nếu thay đổi cổng truy cập frontend từ 443 sang 8443, có thể cần cập nhật allowed origin dù RP ID không thay đổi.

### 4.1. Allowed origins ≠ CORS ≠ cookie domain

- **WebAuthn allowed origins:** server chỉ chấp nhận `origin` trong dữ liệu WebAuthn client cho những site đã phê duyệt.
- **CORS:** quy tắc browser cho phép JavaScript ở origin A đọc/gửi một số HTTP requests tới B, không xác minh assertion WebAuthn.
- **Cookie Domain/SameSite:** cơ chế phân phối cookie/giảm CSRF risk, không xác định RP ID và không chứng minh chữ ký.
- **HTTP Origin header:** header hữu ích cho một số bảo vệ request nhưng không thay thế xác minh `clientDataJSON.origin` trong WebAuthn.

Không giải quyết sai origin bằng `Access-Control-Allow-Origin: *` hoặc wildcard allowed origins. Không cho phép client truyền một giá trị origin bất kỳ rồi server tự thêm giá trị ấy vào allowlist.

## 5. Cơ chế mật mã liên kết credential với RP ID và origin

Trong `authenticatorData`, trường `rpIdHash` dài **32 byte** được tính như sau:

~~~text
rpIdHash = SHA-256(UTF-8(RP ID))
~~~

Với RP ID `example.com`, server mong đợi hash của đúng chuỗi `example.com`; không phải hash `https://example.com` hay `https://login.example.com` trừ khi RP ID đã được chọn là `login.example.com`.

Với authentication, authenticator ký dữ liệu liên quan `authenticatorData` và hash của `clientDataJSON`. `clientDataJSON` chứa các trường như `type`, `challenge`, `origin` và có thể có thông tin cross-origin. Server phải đồng thời kiểm tra:

1. **Type:** `webauthn.get` cho đăng nhập; `webauthn.create` cho đăng ký.
2. **Challenge:** khớp challenge ngẫu nhiên do server cấp cho đúng giao dịch và chỉ dùng một lần.
3. **Origin:** chính xác thuộc tập allowed origins của RP.
4. **RP ID hash:** `rpIdHash` khớp RP ID server cấu hình.
5. **Chữ ký:** hợp lệ với public key của credential đã đăng ký; không phải chuỗi do client tự khai.
6. **Flags:** UP (user presence), UV (user verification) theo chính sách yêu cầu.
7. **Credential/user mapping:** credential ID và user handle gắn với đúng tài khoản, không tự liên kết sang người khác.
8. **Lifecycle/replay:** challenge expiration, state, sign counter (khi có ý nghĩa) và các ràng buộc khác theo chuẩn.

**Hai khóa kiểm tra khác nhau:** RP ID xác định **phạm vi credential**, origin xác định **website đang gọi ceremony**. Một assertion có RP ID hash đúng nhưng origin phát sinh từ một preview host không nằm allowlist **phải bị từ chối**.

Không tự giải mã Base64URL rồi đọc một trường `origin` đúng để kết luận đăng nhập hợp lệ. Phải dùng thư viện WebAuthn server được duy trì vì còn chữ ký, parser, binding và countermeasures chống giả mạo.

## 6. HTTPS và secure context

WebAuthn là một API của **secure context**. Trong triển khai web thông thường:

| Địa chỉ browser | Đánh giá |
| --- | --- |
| `https://login.example.com`, chứng chỉ hợp lệ | Phù hợp production |
| `http://login.example.com` | Không phù hợp: thiếu secure context |
| `http://localhost:8080` | Ngoại lệ phổ biến để phát triển WebAuthn local |
| `https://localhost:8443` | Secure context nếu TLS/cert được browser tin |
| `http://192.168.1.20:8080` | Không coi là tương đương `localhost` một cách mặc định |
| `http://app.internal` | Không dùng cho deployment browser WebAuthn thật |

Một số trình duyệt coi địa chỉ loopback, `.localhost` hoặc các scheme được xác thực là *potentially trustworthy*. Tuy nhiên **secure context nói chung** không đồng nghĩa **RP ID WebAuthn hợp lệ trong mọi trình duyệt**. Để học có thể tái lập, dùng `http://localhost:<port>` và RP ID `localhost`. Production phải có HTTPS và domain được kiểm soát.

### 6.1. Kiểm tra từ DevTools

Mở chính trang gọi passkey, chạy:

~~~javascript
console.log(window.location.origin);
console.log(window.isSecureContext);
console.log(typeof PublicKeyCredential !== "undefined");
~~~

Ví dụ trong browser hỗ trợ tại `http://localhost:8080`:

~~~text
http://localhost:8080
true
true
~~~

Đây là kết quả kỳ vọng cho browser hỗ trợ, không bảo đảm trên mọi thiết bị/chính sách quản trị. `isSecureContext=true` chưa chứng minh rằng RP ID/allowed origins/signature đều đúng.

**HTTPS trong production:** công khai endpoint bằng TLS, dùng chứng chỉ đúng hostname, chặn downgrade sang HTTP, xem xét HSTS, bảo vệ cookie/session bằng `Secure`/`HttpOnly`/`SameSite` và chống XSS. Passkey giúp chống phishing theo origin/RP constraints nhưng không thay thế các lớp này.

## 7. Ma trận RP ID và allowed origin

| Trang gọi WebAuthn | RP ID | Allowed origin | Kết quả |
| --- | --- | --- | --- |
| `https://login.example.com` | `login.example.com` | `https://login.example.com` | Hợp lệ |
| `https://login.example.com` | `example.com` | `https://login.example.com` | Hợp lệ |
| `https://app.example.com` | `example.com` | `https://app.example.com` | Hợp lệ nếu server phê duyệt |
| `https://login.example.com:8443` | `example.com` | `https://login.example.com:8443` | Hợp lệ nếu cổng này được duyệt |
| `https://login.example.com:8443` | `example.com` | Chỉ `https://login.example.com` | Server từ chối |
| `http://login.example.com` | `example.com` | `http://login.example.com` | Không phù hợp HTTPS requirement |
| `http://localhost:8080` | `localhost` | `http://localhost:8080` | Hợp lệ cho lab local |
| `http://localhost:8081` | `localhost` | Chỉ `http://localhost:8080` | Khác origin; server từ chối |
| `https://login.other.net` | `example.com` | `https://login.other.net` | Browser thường từ chối theo suffix rule |
| `https://login.example.com` | `com` | `https://login.example.com` | RP ID không hợp lệ vì public suffix |

Khi origin được phép là HTTPS trên cổng mặc định, đừng thêm `:443` tùy tiện nếu browser trả origin chuẩn hóa không có cổng. Khi chuyển từ HTTP local sang HTTPS staging, phải cập nhật allowed origins đúng scheme/hostname.

## 8. Ví dụ Spring Security 6.5 và Spring Boot 3.5.x

Spring Security 6.5.x có DSL Servlet `HttpSecurity.webAuthn(...)` với `rpId(...)` và `allowedOrigins(...)`. Để giữ code đồng bộ, ví dụ dùng **Spring Boot 3.5.7** (Java 17+, Spring Security 6.5 line). Không lấy project Spring Boot 3.3.x/Spring Security 6.3.x rồi kỳ vọng `webAuthn()` xuất hiện tự động.

### 8.1. File cấu trúc project

~~~text
passkey-local-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/passkey/
    │   ├── PasskeyApplication.java
    │   └── SecurityConfig.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'passkey-local-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tài liệu Spring Security 6.5 yêu cầu `webauthn4j-core`; Spring Security 7 có mô hình dependency khác (ví dụ artifact `spring-security-webauthn`), cần đối chiếu đúng version trước khi dùng.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

`src/main/java/demo/passkey/PasskeyApplication.java`:

~~~java
package demo.passkey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }
}
~~~

`src/main/java/demo/passkey/SecurityConfig.java`:

~~~java
package demo.passkey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .webAuthn(webAuthn -> webAuthn
                        .rpName("Local Passkey Lab")
                        .rpId("localhost")
                        .allowedOrigins("http://localhost:8080"))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("demo-only-password"))
                        .roles("USER")
                        .build());
    }
}
~~~

Đây là cấu hình cho **lab local**:
- `rpId("localhost")` là chuỗi domain, không chứa port.
- `allowedOrigins("http://localhost:8080")` chứa scheme và port chính xác.
- `formLogin()` cung cấp một cách tạo phiên bằng password thử nghiệm trước khi đăng ký passkey.
- WebAuthn registration/login do Spring Security cung cấp; xác minh assertion phải do thư viện thực hiện, không phải một controller tự làm.
- User/credential repositories mặc định có thể là **in-memory**, không phù hợp để lưu passkey cho production.

Chạy tại thư mục project với Gradle hoặc wrapper tương ứng:

~~~bash
gradle bootRun
# Nếu project có wrapper: ./gradlew bootRun
~~~

Mở đúng `http://localhost:8080`, đăng nhập bằng `demo` / `demo-only-password`, rồi mở trang đăng ký tại `/webauthn/register` trong một browser có WebAuthn support. Đừng tự đổi sang `http://127.0.0.1:8080` vì hostname/origin sẽ khác. Dữ liệu in-memory không bảo đảm còn sau khi restart.

Theo tài liệu Spring Security, các endpoint cốt lõi gồm `POST /webauthn/register/options`, `POST /webauthn/register`, `POST /webauthn/authenticate/options` và `POST /login/webauthn`. Các POST có state/challenge và phải xử lý CSRF theo thiết kế, không nên disable CSRF bừa bãi.

### 8.2. Production: một RP ID và hai origin tin cậy

Đây là đoạn cấu hình **minh họa bên trong một SecurityFilterChain Spring Security 6.5**, không phải một chương trình Java độc lập:

~~~java
http.webAuthn(webAuthn -> webAuthn
        .rpName("Example Identity")
        .rpId("example.com")
        .allowedOrigins(
                "https://login.example.com",
                "https://app.example.com"));
~~~

Chỉ thêm origin thực sự được sở hữu, kiểm soát và cho phép chạy ceremony. Nếu website chỉ đăng nhập tại `login.example.com`, **chỉ** cho phép `https://login.example.com`. Không tự thêm `https://preview.example.com`, `http://login.example.com` hoặc `https://*.example.com`.

Nếu trình duyệt đang ở `https://app.example.com` nhưng RP ID được cấu hình là `login.example.com`, allowed origin phía server **không thể** ép browser cho phép RP ID sai quy tắc suffix.

### 8.3. Persistence và quản lý phiên

Theo Spring Security 6.5, WebAuthn persistence dùng `PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository`. Bản demo mặc định in-memory; production cần persistent credential store (chẳng hạn JDBC repositories do Spring Security hỗ trợ) và có chính sách backup/revocation. Khi triển khai nhiều node cần bảo đảm challenge, session, CSRF, cache và user mapping hoạt động nhất quán.

Một passkey được liên kết với tài khoản bằng credential ID/public key/user handle. Không tự tạo tài khoản nội bộ mới chỉ vì browser trả một username trùng email; cần quy tắc account linking và authorization riêng.

## 9. Registration và authentication kiểm tra những gì?

### 9.1. Registration (tạo credential)

Server tạo `PublicKeyCredentialCreationOptions` gồm `rp.id`, user handle, challenge, thuật toán và policy:

~~~json
{
  "rp": { "name": "Example Identity", "id": "example.com" },
  "user": {
    "id": "BASE64URL_USER_HANDLE",
    "name": "demo@example.com",
    "displayName": "Demo User"
  },
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "pubKeyCredParams": [{ "type": "public-key", "alg": -7 }],
  "attestation": "none"
}
~~~

Các chuỗi `BASE64URL_*` ở đây là **ký hiệu minh họa**, không phải giá trị WebAuthn hợp lệ để gửi thử. Spring Security sinh challenge, chọn thuật toán và giữ trạng thái thích hợp. Browser chuyển các trường binary sang đúng dạng `ArrayBuffer` rồi gọi `navigator.credentials.create({ publicKey: ... })`.

Browser kiểm tra RP ID. Authenticator tạo credential scoped tới RP ID. Server xác minh registration response/challenge/origin/rpIdHash và các policy khác **trước** khi lưu public key.

### 9.2. Authentication (sử dụng credential)

Server gửi `PublicKeyCredentialRequestOptions` với `rpId` và challenge:

~~~json
{
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "rpId": "example.com",
  "timeout": 120000,
  "userVerification": "preferred",
  "allowCredentials": []
}
~~~

Browser gọi `navigator.credentials.get({ publicKey: ... })`. Nếu thiết bị có credential thuộc đúng RP ID và user cho phép, server nhận assertion. Trong `clientDataJSON` đã giải mã có thể thấy:

~~~json
{
  "type": "webauthn.get",
  "challenge": "BASE64URL_FRESH_CHALLENGE",
  "origin": "https://login.example.com",
  "crossOrigin": false
}
~~~

Các trường này **không tự xác thực** khi chỉ parse JSON. Server còn phải xác minh cryptographic signature, challenge, rpIdHash, flags, userHandle và key tương ứng. Nếu cần embedded/cross-origin contexts, đánh giá `crossOrigin`/`topOrigin` và permission policy theo chuẩn.

### 9.3. Sai lầm giữa browser check và server check

Ví dụ `https://preview.example.com` với RP ID `example.com`: browser có thể chấp nhận suffix rule. Nhưng khi server chỉ cho `https://login.example.com`, **assertion từ preview phải bị từ chối**.

Ngược lại, trang `https://login.other.net` không thể mặc định dùng RP ID `example.com` chỉ bằng cách thêm origin vào allowlist server. Cần giải pháp domain architecture hoặc Related Origin Requests được client hỗ trợ, không có shortcut từ phía backend.

## 10. Java 17 chạy độc lập: phân biệt RP ID và allowlist origin

Mẫu dưới đây kiểm tra **chính sách allowlist trên dữ liệu mô phỏng**. Nó **không** phải trình xác minh WebAuthn; không kiểm tra Public Suffix List, chữ ký/challenge hoặc provenance của dữ liệu. Mục đích là thấy cùng RP ID không tự cho phép mọi subdomain.

Tạo file `PasskeyOriginPolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public final class PasskeyOriginPolicyDemo {
    private static final String RP_ID = "example.com";
    private static final Set<String> ALLOWED_ORIGINS = Set.of(
            "https://login.example.com",
            "https://app.example.com");

    record Scenario(String name, String origin, String rpId) {}

    static boolean accepts(Scenario scenario) {
        return RP_ID.equals(scenario.rpId())
                && ALLOWED_ORIGINS.contains(scenario.origin());
    }

    public static void main(String[] args) {
        List<Scenario> cases = List.of(
                new Scenario("Login", "https://login.example.com",
                        "example.com"),
                new Scenario("App", "https://app.example.com",
                        "example.com"),
                new Scenario("Preview", "https://preview.example.com",
                        "example.com"),
                new Scenario("HTTP", "http://login.example.com",
                        "example.com"),
                new Scenario("Other port", "https://login.example.com:8443",
                        "example.com"),
                new Scenario("Different RP", "https://login.example.com",
                        "login.example.com"));

        for (Scenario scenario : cases) {
            System.out.println(scenario.name() + ": "
                    + (accepts(scenario) ? "ALLOW" : "DENY"));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PasskeyOriginPolicyDemo.java
java PasskeyOriginPolicyDemo
~~~

Stdout **chính xác**:

~~~text
Login: ALLOW
App: ALLOW
Preview: DENY
HTTP: DENY
Other port: DENY
Different RP: DENY
~~~

**Quan trọng:** chương trình này chỉ mô phỏng các chuỗi **đã biết**. Đừng dùng `accepts(Scenario)` trên dữ liệu tự khai từ network để cấp phiên đăng nhập; server production phải dùng thư viện WebAuthn và dữ liệu `clientDataJSON` đã xác minh cùng RP ID cố định do server cấu hình. Việc xác nhận origin không thay thế signature verification.

## 11. Reverse proxy và địa chỉ public

Topology:

~~~text
Browser: https://login.example.com
    |
    | HTTPS
    v
Gateway/TLS terminator
    |
    | http://passkey-app:8080 (upstream nội bộ)
    v
Spring Security
~~~

Cấu hình WebAuthn phải dựa trên **public browser context**:

~~~text
rpId = example.com
allowedOrigins = [https://login.example.com]
~~~

Không đặt `rpId=passkey-app` hoặc `allowedOrigins=http://passkey-app:8080` khi user không mở trang ở hostname đó.

Nếu backend sinh redirect sai scheme/host (ví dụ redirect ra `http://...`):
- Rà soát TLS termination và Spring Boot forwarded-header handling.
- Chỉ tin `Forwarded`/`X-Forwarded-*` từ gateway đã xác thực/được kiểm soát, không tin do user gửi.
- Cấu hình public base URL và allowlist từ deployment configuration, không suy từ header request chưa tin cậy.
- Kiểm tra HTTPS từ client tới edge và khả năng bảo vệ chặng edge→service.

Một host poisoning attack có thể thay `Host` hoặc `X-Forwarded-Host` nếu proxy không sanitize. Không vì lỗi này mà tự thêm host vừa nhận vào WebAuthn allowed origins.

## 12. Nhiều origin cùng miền và khác miền

### 12.1. Cùng registrable domain

`https://login.example.com` và `https://app.example.com` có thể cùng sử dụng RP ID `example.com`, nhưng là hai origin khác nhau. Nếu cần cả hai làm ceremony, phải phê duyệt và kiểm soát security posture của từng site. CSP, bảo vệ XSS, dependency scripts, session và account recovery đều ảnh hưởng đến độ an toàn.

Nếu credential được tạo theo `rpId=login.example.com`, không thể tự giả định trang `app.example.com` sẽ dùng được. Để cho phép hai subdomain, RP ID chung phải được chọn đúng từ đầu hoặc có thiết kế login tập trung.

### 12.2. Related Origin Requests (ROR) cho domain khác nhau

WebAuthn Level 3 (W3C Recommendation năm 2026) hỗ trợ **Related Origin Requests** trên các WebAuthn clients triển khai tính năng. RP có thể đưa danh sách origin liên quan trong JSON được phục vụ **qua HTTPS** ở:

~~~text
https://example.com/.well-known/webauthn
~~~

Ví dụ:

~~~json
{
  "origins": [
    "https://example.co.uk",
    "https://example.net"
  ]
}
~~~

Điểm cần nhớ:
1. File phải nằm trên domain của **RP ID** và do RP kiểm soát; dùng `Content-Type: application/json`.
2. Browser hỗ trợ có thể kiểm tra file này khi một origin không thỏa quy tắc suffix mặc định; browser không hỗ trợ có thể vẫn từ chối bằng `SecurityError`.
3. Server vẫn phải kiểm tra `clientDataJSON.origin` theo chính sách của mình, dùng RP ID được mong đợi, không tin mọi domain trong Internet.
4. Đây không phải CORS, không phải wildcard và không chứng minh quyền sở hữu một domain chỉ bằng việc ghi tên nó vào JSON.
5. Phải cân nhắc rủi ro brand confusion/phishing, domain lifecycle và khả năng tương thích của browser/OS.

Nếu kiến trúc có nhiều domain nhưng không cần browser ở mọi domain trực tiếp gọi WebAuthn, một **login origin tập trung** và sau đó sử dụng phiên/SSO phù hợp đôi khi đơn giản hơn.

## 13. Đổi RP ID sau khi phát hành

Passkeys được tạo với phạm vi RP ID đã chọn. Đổi `rpId("login.example.com")` thành `rpId("example.com")` hoặc ngược lại **không chỉ là sửa một cấu hình URL**; authenticator/server cần làm việc với RP ID được credential ràng buộc. Người dùng có thể cần đăng ký lại passkey.

Quy trình migration:
1. Kiểm kê RP ID hiện hành, credential counts, các origin đang đăng nhập và domain có quyền kiểm soát.
2. Chọn RP ID dài hạn có chính sách tenant/subdomain rõ.
3. Chuẩn bị flow đăng ký passkey mới trong phiên đã xác thực hoặc phương thức account recovery được bảo vệ.
4. Nếu cần vận hành song song, tách các RP deployments và kiểm soát rõ credential store/issuer/domain, **không bỏ rpIdHash/origin verification**.
5. Lập kế hoạch thông báo user, revoke credentials cũ, backup metadata và xử lý sự cố.
6. Kiểm thử staging với credential test trước khi rollout.

Thay đổi **allowed origins** trong cùng RP ID có thể không buộc đăng ký lại credential, nhưng chỉ hợp lệ khi browser cho phép domain tương ứng và backend đã cho phép origin đó. Thay đổi **RP ID** tác động đến phạm vi mật mã.

## 14. Test matrix cho browser và Spring Security

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Local `http://localhost:8080`, RP ID `localhost`, origin allowed | Ceremony có thể chạy trên browser hỗ trợ |
| Production `https://login.example.com`, RP ID `example.com` | Hợp lệ nếu server allow origin và response cryptographically valid |
| RP ID ghi thành `https://example.com` | Browser/server reject vì sai format |
| RP ID là `com` | Reject vì public suffix |
| `http://login.example.com` trên Internet | Không phải secure context WebAuthn |
| `https://preview.example.com` dùng RP ID `example.com` nhưng không allow origin | **Server reject** |
| `https://login.example.com:8443` không được allow riêng | **Server reject** do port khác |
| Challenge bị đổi/hết hạn/dùng lại | Reject |
| `rpIdHash` khác RP ID đã chọn | Reject |
| Signature không khớp public key | Reject |
| User handle/credential chưa liên kết tài khoản | Không tự đăng nhập tài khoản khác |
| `crossOrigin=true` từ iframe chưa phê duyệt | Reject theo policy |
| HTTP `localhost` chuyển sang `127.0.0.1` | Không mặc định coi hai origin/RP ID giống nhau |
| Proxy sinh địa chỉ `http://internal-service` | Sửa trusted forwarding/base URL, không nới allowed origins |
| Đổi origin production sang domain khác | Thiết kế ROR/login origin hoặc migration, không bypass |

**Cấp kiểm thử:**
- **Unit:** policy/origin allowlist và cấu hình.
- **Integration:** WebAuthn handler/repository/challenge/session và các response test ký đúng/sai.
- **Browser E2E:** registration/authentication thật với virtual authenticator hoặc thiết bị thử nghiệm trên HTTPS/localhost, nhiều browser và OS được hỗ trợ.

`MockMvc` gọi endpoint trả `200` không tự chứng minh passkey verification đúng nếu test không tạo một WebAuthn assertion có chữ ký hợp lệ. Kiểm thử phải bao gồm âm tính và kiểm tra principal đúng.

### Chẩn đoán lỗi

| Lỗi/triệu chứng | Cần xem |
| --- | --- |
| Browser báo `SecurityError` trước khi gọi server | Domain suffix, RP ID syntax, HTTPS/secure context, browser support |
| `window.isSecureContext=false` | Scheme/host/TLS |
| Server báo origin mismatch | `clientDataJSON.origin` so với allowlist scheme/host/port |
| `rpIdHash` mismatch | RP ID khác giữa registration/authentication hoặc migration |
| Mất passkey sau restart demo | In-memory credential repository |
| Registration nhận 403 | Session/CSRF/authorization của endpoint |
| Một subdomain không login được | RP ID scope và allowlist, không phải CORS mặc định |
| Chỉ có backend URL HTTP nội bộ | Xem public origin qua proxy |
| Cross-domain ROR không chạy | Browser support, `/.well-known/webauthn`, RP ID/allowed origin |

Không log raw assertion, key material hoặc challenge nhạy cảm để debug. Dùng request/correlation ID, loại lỗi và cấu hình đã redacted.

## 15. Sai lầm cần tránh

1. “RP ID là URL.” **Sai:** chỉ là domain, không có scheme/port/path.
2. “RP ID bằng domain cha thì mọi subdomain đều được server tin.” **Sai:** server cần origin allowlist riêng.
3. “Port không cần quan tâm.” **Sai:** origin có port dù RP ID không.
4. “Có HTTPS thì không cần kiểm tra origin.” **Sai:** HTTPS bảo vệ kênh, không thay thế policy.
5. “CORS allowlist chính là WebAuthn allowed origins.” **Sai:** hai kiểm soát có nhiệm vụ khác.
6. “Browser đã check RP ID nên backend khỏi check rpIdHash.” **Sai:** backend phải xác minh.
7. “Tự parse JSON thấy `origin` đúng là đã login.” **Sai:** cần challenge/signature/flags.
8. “`http://staging.internal` giống `http://localhost`.” **Sai:** không có ngoại lệ WebAuthn rộng như vậy.
9. “Thêm domain bất kỳ vào `allowedOrigins` là browser sử dụng chung credential.” **Sai:** browser kiểm tra suffix hoặc cơ chế ROR.
10. “Có thể đổi RP ID tùy tiện không ảnh hưởng passkey.” **Sai:** scope credential thay đổi.
11. “`login.example.com` và `app.example.com` là cùng origin.” **Sai:** khác hostname.
12. “Truy cập `127.0.0.1` giống y `localhost`.” **Sai:** hostname/origin khác, browser policies cần được xác minh.
13. “Có passkey thì bỏ CSRF/XSS controls.” **Sai:** registration, session và account recovery vẫn cần bảo vệ.
14. “Tin `X-Forwarded-Host` từ mọi request để sửa lỗi.” **Sai:** có nguy cơ host poisoning.
15. “Default in-memory credentials đủ cho production.” **Sai:** cần persistence và lifecycle rõ.

## 16. Câu hỏi tự luyện

**Câu 1.** Trang `https://login.example.com` có thể dùng RP ID `example.com`?  
**Có**, theo quy tắc suffix khi miền hợp lệ; server vẫn phải allow origin riêng.

**Câu 2.** RP ID `example.com:443` có hợp lệ?  
**Không**, port thuộc origin, không thuộc RP ID.

**Câu 3.** Cùng RP ID `example.com` nhưng origin `https://preview.example.com` chưa được phê duyệt, có nên nhận assertion?  
**Không**, server từ chối dù browser có thể chấp nhận RP ID.

**Câu 4.** Có thể bật passkeys trên `http://login.example.com` vì đây là mạng nội bộ?  
**Không**, phải triển khai secure context với HTTPS; chỉ `localhost` và một số trường hợp đặc biệt có ngoại lệ phù hợp.

**Câu 5.** Nếu backend chạy `http://app:8080` nhưng browser truy cập `https://login.example.com`, allowed origin nên là gì?  
**`https://login.example.com`**, không phải hostname nội bộ.

**Câu 6.** Đổi allowed origin khác đổi RP ID thế nào?  
Allowed origin điều chỉnh **nơi server tin**; RP ID là phạm vi **credential cryptographic**, có thể cần migration/đăng ký lại.

**Câu 7.** Thêm `https://example.net` vào allowed origins có đủ để browser ở đó dùng RP ID `example.com`?  
**Không**. Cần kiến trúc khác hoặc Related Origin Requests với browser hỗ trợ và server validation.

### Checklist trước go-live

- [ ] RP ID là domain hợp lệ, ổn định, không scheme/port/path và không là public suffix.
- [ ] Allowed origins có scheme/host/port chính xác, không wildcard.
- [ ] Web app production qua HTTPS và chứng chỉ đúng; HTTP localhost chỉ là lab.
- [ ] Proxy tin đúng forwarded headers, không dùng Host header chưa tin để tự sinh allowlist.
- [ ] WebAuthn thư viện xác minh challenge, origin, rpIdHash, chữ ký, flags và user mapping.
- [ ] Session/CSRF/account recovery và persistence được kiểm thử.
- [ ] Không nới production allowlist cho preview hoặc subdomain kém tin cậy.
- [ ] Có kế hoạch multi-origin, ROR compatibility và migration RP ID.
- [ ] Test browser E2E và các lỗi âm tính, không chỉ unit test config.
- [ ] Không dùng thông tin clientData chưa xác thực như một bằng chứng đăng nhập.

## 17. Tài liệu tham khảo

- [W3C — Web Authentication Level 3 Recommendation, 25/08/2026](https://www.w3.org/TR/2026/REC-webauthn-3-20260825/): RP ID/domain suffix, secure context, `rpIdHash`, origin verification và Related Origin Requests.
- [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): `webAuthn(...)`, dependencies, registration/authentication endpoints và credential persistence.
- [Spring Security 6.5 — WebAuthnConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html): cấu hình `rpId`, `allowedOrigins`.
- [MDN — Secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts): local trustworthy origins và `isSecureContext`.
- [web.dev — Related Origin Requests](https://web.dev/articles/webauthn-related-origin-requests): file `/.well-known/webauthn` và browser compatibility.
- [Spring Boot 3.5 Gradle plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/): Java/Gradle project cho ví dụ.

**Kết luận:** **RP ID** quy định credential thuộc miền nào, **allowed origins** quy định website nào server cho phép thực hiện WebAuthn và **HTTPS** cung cấp secure context cho browser production. Cả ba phải đúng; không yếu tố nào cho phép bỏ qua việc xác minh cryptographic assertion.