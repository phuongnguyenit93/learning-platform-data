# WebAuthn, passkey và điều kiện phiên bản/dependency của Spring Security

## 1. Bài toán, phạm vi và mục tiêu

Người dùng muốn đăng nhập ứng dụng Spring Boot bằng vân tay, nhận diện khuôn mặt, PIN hoặc khóa bảo mật thay vì nhập mật khẩu mỗi lần. Trong nhiều thiết bị, trải nghiệm này được gọi là **passkey**. Cơ chế web đằng sau là **Web Authentication API (WebAuthn)**: browser yêu cầu authenticator tạo hoặc sử dụng cặp khóa bất đối xứng; server xác minh bằng public key đã đăng ký, không cần nhận private key và không cần giữ một bí mật dùng chung cho đăng nhập.

Trong module **Spring Security - authentication**, bài học này tập trung vào **khả năng tích hợp có thật của Spring Security, điều kiện phiên bản và dependency tương ứng**, không chỉ định nghĩa passkey chung chung. Sau khi học, bạn cần:

1. Phân biệt WebAuthn, passkey, FIDO2, authenticator, Relying Party (RP), registration và authentication assertion.
2. Hiểu vì sao passkey ràng buộc với miền ứng dụng và giúp giảm nguy cơ phishing so với password.
3. Nắm chính xác sự khác biệt **Spring Security 6.4–6.5** và **Spring Security 7.x** về artifact.
4. Thiết lập `HttpSecurity.webAuthn(...)` với `rpId`, `allowedOrigins`, `rpName`; chọn đúng starter và phiên bản Java/Spring Boot.
5. Thực hiện luồng **đăng ký credential** rồi **đăng nhập**; hiểu các endpoint HTTP mặc định, CSRF, challenge, session và repository.
6. Biết lúc nào dữ liệu WebAuthn trong memory chỉ dùng được cho demo và cách chuyển sang JDBC/custom persistence.
7. Kiểm thử các lỗi thường gặp: không có HTTPS/secure context, RP ID sai, origin không khớp, thiếu dependency, mất challenge/session hoặc credentials sau restart.
8. Đánh giá chính sách chống chiếm đoạt tài khoản khi đăng ký/xóa passkey, khôi phục tài khoản, xác minh người dùng và duy trì phiên.

**Phạm vi kỹ thuật của ví dụ runnable:** ứng dụng **Servlet/Spring MVC** với Java 17, Spring Boot 3.5.x và Spring Security 6.5.x. Các API reactive/WebFlux, ứng dụng mobile native và tự xây dựng WebAuthn server từ đầu là phạm vi khác, không mặc nhiên sử dụng được cùng cấu hình Servlet.

## 2. WebAuthn và passkey không hoàn toàn đồng nghĩa

**WebAuthn** là API web + giao thức xác thực dùng public-key cryptography. **Passkey** là một loại trải nghiệm/credential dựa trên FIDO/WebAuthn, thường có thể được quản lý trên thiết bị hoặc đồng bộ qua hệ sinh thái của nền tảng và có khả năng khám phá (discoverable) để đăng nhập thuận tiện.

Các khái niệm chính:

| Thuật ngữ | Nghĩa | Hệ quả khi tích hợp |
| --- | --- | --- |
| **Relying Party (RP)** | Dịch vụ ứng dụng muốn xác thực người dùng | Spring Boot là RP server; phải công bố RP ID và kiểm tra origin |
| **RP ID** | Chuỗi tên miền xác định phạm vi dùng credential, ví dụ `app.example.com` hoặc `example.com` | Không có scheme/port; phải khớp host hoặc registrable-domain suffix hợp lệ |
| **Origin** | Scheme + host + port của trang web gọi WebAuthn, ví dụ `https://app.example.com` | Phải được server cho phép; không chỉ so tên host |
| **Authenticator** | Nền tảng hoặc khóa bảo mật sở hữu private key và ký challenge | Browser gọi thông qua `navigator.credentials`; server không được lấy private key |
| **Credential ID** | Định danh của public-key credential cụ thể | Dùng tra record public key, owner, trạng thái và metadata |
| **Public key** | Thành phần được lưu phía RP sau đăng ký | Dùng kiểm tra chữ ký trong những lần login sau |
| **Private key** | Thành phần nằm ở authenticator/passkey provider | Không được gửi về server trong WebAuthn |
| **Challenge** | Giá trị ngẫu nhiên mới, liên kết một ceremony cụ thể | Phải lưu và so khớp, kiểm tra thời hạn/chống replay |
| **Attestation** | Thông tin bổ sung về nguồn gốc/loại authenticator khi policy dùng | Không đồng nghĩa xác thực danh tính người dùng; nhiều ứng dụng dùng `none` |
| **Assertion** | Dữ liệu trình browser gửi khi credential ký thử thách xác thực | Server kiểm tra chữ ký, challenge, RP ID, origin và flags |
| **User presence (UP)** | Thiết bị có tương tác của user | Không đồng nghĩa user verification |
| **User verification (UV)** | Authenticator thực hiện biện pháp xác minh local như PIN/biometric | Server cần chính sách UV phù hợp rủi ro |

**Passkey không phải “đăng nhập bằng vân tay mà server lưu dấu vân tay”.** Vân tay/face/PIN chỉ mở khóa hoặc xác minh người dùng **trên thiết bị/provider**; server nhận kết quả mật mã, không nhận template sinh trắc học.

**Passkey không phải JWT, OAuth2 access token hoặc OIDC ID Token.** Sau khi WebAuthn thành công, Spring Security tạo `Authentication` trong ứng dụng và có thể lưu phiên; nếu sau đó cần phát JWT cho API, đó là một cơ chế thêm và phải được thiết kế riêng.

## 3. Tại sao WebAuthn giảm nguy cơ phishing?

Với mật khẩu, một trang giả dạng có thể hỏi user nhập lại cùng secret. Với WebAuthn, browser và authenticator đưa **RP ID** vào phạm vi credential. Credential của `app.example.com` không được tự do sử dụng trên `fake-login.attacker.example`. Ngoài ra, mỗi lần đăng nhập cần chữ ký cho **challenge mới** của RP, giúp ngăn phát lại một response cũ.

Ba lớp kiểm tra quan trọng:

1. **Ràng buộc domain/origin:** browser chỉ cho phép WebAuthn ở context hợp lệ, và server so `clientDataJSON.origin`/RP ID.
2. **Chứng minh sở hữu khóa:** server kiểm tra chữ ký bằng public key gắn credential ID đã đăng ký.
3. **Tính mới:** challenge phải là challenge server đã cấp cho ceremony hiện hành, chưa hết hạn/chưa bị dùng lại.

Tuy nhiên, “phishing-resistant” không có nghĩa ứng dụng **tự động an toàn tuyệt đối**. Nếu attacker chiếm phiên HTTP của người dùng, khai thác lỗ hổng XSS, dẫn người dùng thêm passkey vào tài khoản bằng luồng đăng ký bị chiếm đoạt hoặc chiếm phương thức recovery yếu, WebAuthn không tự giải quyết được. Bảo mật vẫn phụ thuộc server, session, CSRF, quyền đăng ký và vận hành tài khoản.

## 4. Điều kiện phiên bản và dependency: điểm dễ nhầm nhất

Spring Security hỗ trợ WebAuthn/passkeys bắt đầu từ **Spring Security 6.4**. Cách đóng gói thư viện thay đổi giữa hai thế hệ:

| Hệ Spring | WebAuthn nằm ở đâu? | Dependency cần chú ý |
| --- | --- | --- |
| **Spring Security trước 6.4** | Không có DSL WebAuthn tích hợp tương đương | Cần nâng cấp hoặc tích hợp thư viện khác có hỗ trợ Spring phiên bản đó; không gọi `http.webAuthn(...)` |
| **Spring Security 6.4–6.5** (Spring Boot 3.4–3.5) | Các lớp WebAuthn thuộc `spring-security-web` | Ngoài starter Security, phải có **`com.webauthn4j:webauthn4j-core`** theo tài liệu của nhánh tương ứng |
| **Spring Security 7.0–7.1** (Spring Boot 4.x) | Tách chức năng WebAuthn sang artifact **`spring-security-webauthn`** | Thêm **`org.springframework.security:spring-security-webauthn`** với version do Spring Boot/Security BOM quản lý |

**Không chuyển nguyên xi file `pom.xml` từ 6.5 sang 7.x.** Việc tách module ở 7.x có thể gây lỗi classpath/runtime dù API cấu hình nhìn gần giống nhau. Ngược lại, thêm `spring-security-webauthn` vào một project 6.5 là chọn sai hệ dependency.

### 4.1. Maven cho Spring Boot 3.5 / Spring Security 6.5

Tài liệu Spring Security **6.5.11** chỉ rõ:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
</dependency>
<dependency>
    <groupId>com.webauthn4j</groupId>
    <artifactId>webauthn4j-core</artifactId>
    <version>0.29.7.RELEASE</version>
</dependency>
```

Khi dùng `spring-boot-starter-security`, `spring-security-web` đã được starter kéo vào; **không cần khai báo trùng**. Nhưng `webauthn4j-core` phải có trên classpath đúng nhánh. Dùng `mvn dependency:tree` để xác nhận, thay vì đoán phiên bản từ một hướng dẫn khác.

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

**Điều kiện Java:** Spring Boot 3.x yêu cầu Java 17 trở lên; ví dụ dùng Java 17. Spring Security 6.x tương ứng Jakarta Servlet API, không dùng các import `javax.servlet.*` cũ trong code Servlet trên Boot 3.x.

### 4.2. Maven/Gradle cho Spring Security 7.x

Với Spring Security 7.0–7.1 và BOM tương thích:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-webauthn</artifactId>
</dependency>
```

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

Các dependency nền như Spring Security config/web vẫn cần theo cấu trúc ứng dụng. **Không ghi `0.29.7.RELEASE` làm version của artifact Spring Security 7.x**; đó là version thư viện WebAuthn4J được tài liệu Spring Security 6.5 sử dụng, không phải version `spring-security-webauthn`.

Kiểm tra bản thực tế bằng Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=com.webauthn4j
```

Khi nâng cấp Spring Boot major, hãy đọc version-specific docs thay vì dựa vào trang “latest” vì trang latest có thể nói về cấu trúc module đã thay đổi. Cũng phải kiểm tra dependency conflicts, các thư viện serialization, Spring Framework/Servlet version và cảnh báo bảo mật.

### 4.3. Thông tin về Spring Boot 3.5.16

Bài thực hành dùng một bản cố định **Spring Boot 3.5.16** có trên Maven Central. Spring công bố đây là **bản OSS cuối của 3.5.x** vào ngày **25/06/2026**; nếu triển khai sản phẩm mới, nên nâng lên nhánh còn được hỗ trợ như Boot 4.x theo lộ trình tương thích. Dùng Boot 3.5 trong bài chỉ để minh họa API Spring Security 6.5 với dependency WebAuthn4J rõ ràng, **không phải khuyến nghị tiếp tục chạy bản đã hết hỗ trợ**.

## 5. Relying Party ID, allowedOrigins và secure context

Đây là cấu hình sai dễ gây lỗi nhất dù project đã build thành công.

Với ứng dụng production:

```text
Public URL:      https://login.example.com
RP ID:           login.example.com
Allowed Origin:  https://login.example.com
```

- **RP ID** là domain string, không có `https://`, port hoặc path.
- **Origin** gồm scheme, hostname và port nếu khác mặc định; không có path.
- RP ID phải là host hiệu lực hoặc registrable-domain suffix hợp lệ của host theo quy tắc WebAuthn (ví dụ trong một số kiến trúc RP ID có thể là `example.com` cho subdomain được kiểm soát).
- Không được dùng một public suffix tùy ý như `com` làm RP ID.
- Passkey đăng ký cho RP ID này không dùng tự động cho một RP ID không liên quan.
- Nếu thay đổi miền đăng nhập sau này, cần kế hoạch migration/phát hành lại credential hoặc kiến trúc phù hợp, không chỉ sửa một biến config.

**HTTPS:** WebAuthn được phép trong **secure context**. HTTP thông thường ở domain public không đủ; đặc biệt, `http://localhost:<port>` được WebAuthn cho phép làm môi trường dev ngoại lệ. Vì vậy ví dụ local có thể dùng:

```text
Public URL:      http://localhost:8080
RP ID:           localhost
Allowed Origin:  http://localhost:8080
```

Đừng nhầm `http://127.0.0.1:8080`, `http://localhost:8080` và `https://localhost:8080`: origin khác nhau. Nếu RP/origin cấu hình cho localhost nhưng truy cập bằng IP, browser có thể từ chối yêu cầu; dùng đúng hostname. Trong production sau reverse proxy, public host/HTTPS phải nhất quán với RP và origin, không lấy giá trị từ host header tùy ý.

## 6. Hai ceremony: đăng ký và xác thực

Một passkey **phải được đăng ký trước** mới có thể dùng xác thực. Về logic, WebAuthn gồm hai ceremony khác nhau.

### 6.1. Registration: người dùng đang đăng nhập thêm credential mới

```text
User đang đăng nhập bằng phương thức bootstrap đáng tin cậy
         |
         | Mở /webauthn/register
         v
Browser / Spring Security registration page
         |
         | POST /webauthn/register/options + CSRF
         v
Spring: xác nhận user, tạo challenge/options
         |
         | publicKey.rp / user / challenge / algorithms / policy
         v
Browser: navigator.credentials.create({ publicKey: options })
         |
         | Authenticator tạo cặp khóa và xác minh local user
         | Private key nằm phía authenticator/passkey provider
         v
Browser gửi attestation/credential response
         |
         | POST /webauthn/register + CSRF
         v
Spring: kiểm tra challenge, origin, RP ID, dữ liệu attestation
         |
         | Lưu credential ID, public key, user handle, metadata
         v
Passkey được liên kết với tài khoản hiện tại
```

**Tại sao phải đăng nhập trước khi đăng ký?** Vì thao tác “thêm một phương thức đăng nhập mới” cho tài khoản là nhạy cảm. Nếu attacker có thể thêm passkey vào tài khoản người khác mà không có phiên/reauth hợp lệ, attacker tạo ra phương thức truy cập lâu dài. Registration nên ràng buộc với một **local user ID ổn định**, kiểm tra anti-CSRF và áp dụng xác thực lại (step-up) cho trường hợp rủi ro cao.

Các HTTP endpoint mặc định của Spring Security Servlet 6.5/7.x:

| Bước | Endpoint | HTTP method | Yêu cầu đặc biệt |
| --- | --- | --- | --- |
| Hiển thị trang quản lý passkey mẫu | `/webauthn/register` | GET | User đã đăng nhập |
| Tạo registration options | `/webauthn/register/options` | POST | User đã đăng nhập, CSRF token, lưu challenge |
| Lưu credential mới | `/webauthn/register` | POST | User đã đăng nhập, CSRF token, xác minh WebAuthn response |

Cùng một URL `/webauthn/register` có thể đáp ứng **GET trang UI** và **POST đăng ký thực tế**, đừng suy luận một method cho mọi hành động.

### 6.2. Authentication: dùng credential đã đăng ký để đăng nhập

```text
Anonymous Browser
     |
     | GET /login
     v
Trang login có lựa chọn passkey
     |
     | POST /webauthn/authenticate/options + CSRF
     v
Spring tạo challenge xác thực
     |
     | Browser navigator.credentials.get({ publicKey: options })
     v
Authenticator chọn credential phù hợp với RP ID
     | xác minh local user (PIN/biometric nếu policy yêu cầu)
     | ký challenge-related data bằng private key
     v
POST /login/webauthn + CSRF (assertion)
     |
     v
Spring tìm credential record theo credential ID
     | kiểm tra challenge, origin, RP ID hash
     | kiểm tra UP/UV theo policy, chữ ký và metadata
     v
Spring Security Authentication thành công
     |
     v
SecurityContext + session + authorization
```

Các endpoint mặc định:

| Bước | Endpoint | HTTP method |
| --- | --- | --- |
| Trang login mẫu | `/login` | GET |
| Tạo authentication options | `/webauthn/authenticate/options` | POST |
| Gửi assertion để đăng nhập | `/login/webauthn` | POST |

**Challenge mới mỗi lần:** server tạo challenge ngẫu nhiên và lưu trạng thái của ceremony, thường gắn với session. Client gọi `navigator.credentials.get(...)`; server phải so response với challenge của chính lần yêu cầu đang chờ. Một assertion cũ không được chấp nhận chỉ vì chữ ký hợp lệ dưới public key của user.

**User presence vs user verification:** thiết bị có tương tác (UP) chưa đảm bảo PIN/biometric (UV) đã được yêu cầu. App có yêu cầu strong authentication cần kiểm soát đúng userVerification policy và kết quả server-side; không kết luận “WebAuthn tức là luôn có biometric”.

### 6.3. Luồng browser WebAuthn và dữ liệu nhị phân

WebAuthn browser API dùng `ArrayBuffer`/`Uint8Array`, trong khi JSON API của Spring thường biểu diễn byte arrays bằng **base64url**. Cần chuyển đổi ở hai chiều.

Đây là **trích đoạn JS minh họa API WebAuthn**, không phải một web page hoàn chỉnh:

```javascript
// publicKey là options đã lấy từ /webauthn/authenticate/options.
// Helper này chuyển field binary ở dạng base64url về ArrayBuffer.
// Bản tích hợp phải chuyển cả allowCredentials[].id nếu có.
function fromBase64url(text) {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), char => char.charCodeAt(0)).buffer;
}

async function usePasskey(publicKey) {
  const options = {
    ...publicKey,
    challenge: fromBase64url(publicKey.challenge),
    allowCredentials: (publicKey.allowCredentials ?? []).map(item => ({
      ...item,
      id: fromBase64url(item.id)
    }))
  };
  return navigator.credentials.get({ publicKey: options });
}
```

Ở bước registration dùng `navigator.credentials.create({publicKey: ...})`, đồng thời giải mã `challenge`, `user.id` và `excludeCredentials[].id`. Sau khi API browser trả credential, client phải **encode lại** các giá trị binary trong `rawId`/`response.*` theo schema request mà Spring Security yêu cầu. Có thể tham khảo trang registration/login mặc định thay vì tự viết serialization chỉ từ vài dòng minh họa.

Đừng tự lấy `credential.id` rồi coi đó là bằng chứng đăng nhập: **ID chỉ để tra public key; chữ ký assertion mới là phần phải kiểm chứng**.

## 7. Ví dụ Spring Boot 3.5.16 + Spring Security 6.5 + WebAuthn4J

Ví dụ này là một dự án **Java 17+, Servlet/MVC** tối giản. Nó dùng trang login và registration **mặc định do Spring Security sinh ra**, tránh phải tự triển khai client JavaScript/WebAuthn serializer trước khi hiểu server flow.

Điều kiện để tương tác thực sự: trình duyệt hỗ trợ WebAuthn, máy có authenticator/passkey provider hoặc security key, browser truy cập đúng `http://localhost:8080`, và người dùng đồng ý tạo passkey. Bản demo dùng in-memory credential persistence: restart app có thể làm mất registration.

Cấu trúc:

```text
webauthn-passkey-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/passkey/PasskeyApplication.java
    └── test/
        └── java/demo/passkey/PasskeyApplicationTests.java
```

### 7.1. Tạo `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webauthn-passkey-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <!-- WebAuthn crypto integration cần cho Spring Security 6.5 -->
        <dependency>
            <groupId>com.webauthn4j</groupId>
            <artifactId>webauthn4j-core</artifactId>
            <version>0.29.7.RELEASE</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Cả `spring-security-web` và `spring-security-config` được `spring-boot-starter-security` mang vào project; không cần ghi version riêng cho các module đó. **Không thêm `spring-security-webauthn` 7.x vào `pom.xml` này.**

### 7.2. Tạo file Java đầy đủ

Tạo `src/main/java/demo/passkey/PasskeyApplication.java`:

```java
package demo.passkey;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PasskeyApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasskeyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwords) {
        UserDetails learner = User.withUsername("learner")
            .password(passwords.encode("local-demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().authenticated())
            // Dùng password login để bootstrap tài khoản trong demo;
            // không mặc định tắt cơ chế recovery ở production.
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .rpName("Local Passkeys Demo")
                .allowedOrigins("http://localhost:8080"))
            .build();
    }

    @GetMapping("/")
    Map<String, String> index() {
        return Map.of(
            "login", "/login",
            "registerPasskey", "/webauthn/register");
    }

    @GetMapping("/public")
    ResponseEntity<String> publicPage() {
        return ResponseEntity.ok("public");
    }

    @GetMapping("/private/me")
    Map<String, String> currentUser(Principal principal) {
        return Map.of("name", principal.getName());
    }
}
```

**Những lựa chọn có chủ đích:**

- `.webAuthn(...)` dùng DSL tích hợp của Spring Security 6.5, không viết một custom filter tự xác minh signature.
- `rpId("localhost")` và `allowedOrigins("http://localhost:8080")` đúng cho dev trên loopback. Nếu deploy tại `https://login.example.com`, hai giá trị phải đổi đồng bộ theo domain public.
- `.formLogin(...)` tạo đường bootstrap: login bằng user/password demo rồi vào trang `/webauthn/register` để thêm passkey. Sau khi đăng xuất, đăng nhập lại bằng passkey.
- `UserDetailsService` dùng in-memory username/password cho **demo**, password được hash bằng BCrypt. Không sử dụng password cố định trong ứng dụng thực.
- Credential repository mặc định cũng ở **bộ nhớ**. Nó khác với `InMemoryUserDetailsManager`: một nơi lưu account/login password, một nơi lưu public-key credentials. Cả hai không phù hợp làm user store cho production.
- Spring Security quản lý giao thức, challenge và tạo `Authentication`. Controller `/private/me` chỉ đọc `Principal` đã xác thực.
- Không tắt CSRF; các POST tạo challenge/credential vẫn cần CSRF token vì có thay đổi trạng thái hoặc kết nối ceremony với session.

**Không gọi ví dụ là “passwordless-only”**: người dùng vẫn bootstrap bằng password demo. Một sản phẩm muốn hoàn toàn không có password phải có luồng onboarding, invitation, account recovery và quản lý rủi ro riêng.

### 7.3. Chạy ứng dụng và thử trong browser

Chạy:

```bash
mvn spring-boot:run
```

Mở **đúng**:

```text
http://localhost:8080/
```

Thực hiện:

1. Mở `/private/me` khi chưa login: Spring chuyển tới `/login`.
2. Đăng nhập bằng `learner` / `local-demo-password` trên **máy local** để bootstrap.
3. Mở `http://localhost:8080/webauthn/register`.
4. Dùng giao diện đăng ký của Spring Security tạo passkey. Trình duyệt/hệ điều hành có thể yêu cầu PIN/biometric hoặc chọn security key.
5. Xác nhận giao diện báo đăng ký thành công.
6. Đăng xuất bằng giao diện Spring Security (theo cơ chế POST/CSRF hoặc trang logout chuẩn), quay về `/login`.
7. Chọn đăng nhập bằng passkey và chọn credential vừa tạo.
8. Kiểm tra `/private/me` trả tên người dùng là `learner` nếu authentication thành công.

JSON mẫu khi thành công:

```json
{"name":"learner"}
```

Đây là response ví dụ cho user test cố định, không phải dữ liệu mà WebAuthn API luôn trả trực tiếp. Nếu `mvn spring-boot:run` chạy nhưng browser từ chối `navigator.credentials.create`, hãy kiểm tra secure context/RP ID/origin và thiết bị trước khi sửa dependency.

**Quan trọng:** credential trên thiết bị có thể tồn tại ngay cả khi app restart, nhưng record public key trong memory của server bị xóa. Kết quả là browser vẫn “thấy passkey” song server không thể đối chiếu để login. Đó là lý do cần **persistent WebAuthn credential store** ở production.

## 8. Test ứng dụng bằng MockMvc và giới hạn của unit test

Có thể kiểm tra controller/authorization/login fallback bằng `MockMvc` mà không gọi thiết bị sinh trắc học hoặc browser WebAuthn. Tuy nhiên, **không thể kết luận WebAuthn crypto/challenge đã hoạt động chỉ nhờ `@WithMockUser`**.

Tạo `src/test/java/demo/passkey/PasskeyApplicationTests.java`:

```java
package demo.passkey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasskeyApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedPrincipalCanReadPrivateEndpoint()
            throws Exception {
        mvc.perform(get("/private/me").with(user("learner")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng **3 test pass** nếu project và dependencies đúng. Test này chứng minh SecurityFilterChain cơ bản chạy, trang protected cần authentication và controller nhận principal. Test dùng `user("learner")` **tiêm authentication thử nghiệm**, không đi qua authenticator.

**Muốn test WebAuthn end-to-end**, cần browser thật hoặc framework browser automation hỗ trợ virtual authenticator/FIDO2 (các API DevTools tương ứng) hoặc thiết bị kiểm thử; phải thực hiện thật hai ceremony registration và assertion, kiểm chứng 401 với challenge/credential sai, nhiều browser/session, mất credential sau restart, RP ID sai và cơ chế thu hồi. Không gán cho MockMvc mức bảo đảm mà nó chưa kiểm chứng.

## 9. Persistence: các repository và schema không được bỏ qua

Tài liệu Spring Security 6.5 mô tả hai abstraction lưu dữ liệu:

- `PublicKeyCredentialUserEntityRepository`: liên kết WebAuthn user entity / user handle với người dùng mà RP quản lý.
- `UserCredentialRepository`: lưu các credential record, public key/credential ID và metadata cần để kiểm tra assertion.

Mặc định là **in-memory**. Trong single-node demo, có thể đăng ký và đăng nhập trong cùng vòng đời process; **restart sẽ mất dữ liệu**, nhiều node không cùng kho credentials sẽ cho kết quả thất thường.

### 9.1. Dùng JDBC từ Spring Security 6.5

Spring cung cấp:

- `JdbcPublicKeyCredentialUserEntityRepository`.
- `JdbcUserCredentialRepository`.

Mẫu bean **trích đoạn để đưa vào một class `@Configuration`**, không phải chương trình độc lập:

```java
@Bean
JdbcPublicKeyCredentialUserEntityRepository webauthnUserEntities(
        JdbcOperations jdbc) {
    return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
}

@Bean
JdbcUserCredentialRepository webauthnCredentials(
        JdbcOperations jdbc) {
    return new JdbcUserCredentialRepository(jdbc);
}
```

Khi dùng mã trên, thêm `spring-boot-starter-jdbc`, cấu hình `DataSource`, và khởi tạo **schema mà chính phiên bản Spring Security đó yêu cầu**, không tự đoán tên cột. Ví dụ API `JdbcUserCredentialRepository` lưu ý schema resource:

```text
classpath:org/springframework/security/user-credentials-schema.sql
```

Xác minh resource schema của **phiên bản JAR đã chọn**; repository lưu user entity cũng có schema riêng. Hãy chạy migration Flyway/Liquibase có kiểm soát, áp dụng unique constraint theo credential ID/user handle và giới hạn truy cập DB. Đừng gán cho database bảng tên tự đặt rồi kỳ vọng JDBC repository tích hợp truy vấn được.

Nếu dữ liệu account đang nằm trong PostgreSQL/MySQL hoặc identity platform riêng, có thể tự triển khai hai interface repository nhưng phải bảo toàn hợp đồng tìm/ghi/xóa credential và tính nhất quán transaction.

### 9.2. Challenge/options cũng có state

Ngoài bảng credential, các registration options phải được bảo toàn giữa bước xin options và bước gửi credential. Spring Security có `PublicKeyCredentialCreationOptionsRepository`; mặc định implementation giữ options trong **HttpSession**. Khi cần, tùy biến repository qua `webAuthn(...).creationOptionsRepository(...)` hoặc bean phù hợp.

Trong môi trường nhiều instance, nếu mỗi node giữ session riêng mà không có sticky routing/shared session store, bước đăng ký/challenge có thể bị mất khi request tiếp theo sang node khác. Cần đánh giá session store, cookie, TTL và chống replay, không chỉ chuyển credential sang JDBC rồi cho rằng mọi bước đã stateless.

### 9.3. Thiết kế vòng đời credential

Một tài khoản có thể sở hữu nhiều passkey (điện thoại, laptop, hardware security key), và từng passkey có:

- Credential ID, public key, owner user handle, RP ID liên quan.
- Tên do user tự đặt như “Laptop của tôi”, loại/hints và thời điểm đăng ký/sử dụng cuối.
- Trạng thái revoked/deleted, metadata authenticator và sign counter nếu có.
- Các tín hiệu như backup eligibility/backup state nếu chính sách/audit cần.

Không cần và **không được** lưu biometric template hoặc private key của user. Nếu user xóa một passkey trong hệ điều hành nhưng record server còn đó, credential có thể không dùng được nữa; cần UI quản lý và quy trình remove phía ứng dụng. Ngược lại, xóa record server không nhất thiết xóa credential đã đồng bộ trên thiết bị, nhưng sẽ khiến server từ chối assertion từ credential đó.

## 10. Những điều kiện triển khai production cần kiểm chứng

### 10.1. HTTPS và cấu hình proxy

- Public origin phải dùng HTTPS với chứng chỉ hợp lệ, trừ ngoại lệ localhost khi phát triển.
- Khai báo RP ID và allowedOrigins theo **domain mà browser thực sự truy cập**, không theo hostname/container port nội bộ.
- Nếu có ingress/load balancer, đảm bảo browser nhận HTTPS/origin đúng; không tin tùy tiện `X-Forwarded-Host`/`X-Forwarded-Proto` từ client ngoài.
- Cấu hình forwarded headers chỉ từ proxy tin cậy; xác minh các URL redirect, cookie Secure/SameSite, và routing của đăng ký/authentication endpoint.
- Không tự thêm `*` vào origin allowlist để chữa lỗi CORS hoặc origin mismatch. **CORS không thay thế WebAuthn origin verification.**

### 10.2. CSRF, state và session

- Các request options là POST vì chúng tạo challenge/state để so trong bước sau. Tài liệu Spring Security yêu cầu CSRF token cho cả request options và gửi credential.
- Không tắt CSRF toàn cục chỉ để mẫu chạy được; tìm cách lấy token từ form/meta/cookie theo cấu hình bảo mật và gửi đúng header.
- Giữ session/challenge state giữa options request và response submission. Cookie khác domain, hết hạn hoặc nhiều node không chia sẻ session làm challenge “không tồn tại”.
- Chặn replay và xử lý thời hạn challenge; khi ceremony thất bại, tránh tái sử dụng challenge cũ như một credential hợp lệ.
- Sau successful authentication, Spring Security tạo context và xử lý session fixation/logout theo chain cấu hình. Passkey không thay session management.

### 10.3. Credential enrollment, recovery và account takeover

- Registration thường yêu cầu user **đã authenticated**; đối với account quan trọng, cân nhắc yêu cầu đăng nhập lại/step-up khi thêm passkey mới, xóa passkey cuối hoặc đổi recovery.
- Xác nhận rõ user handle/owner; không lấy arbitrary `username` từ request mà bỏ qua context người dùng hiện tại.
- Có recovery flow an toàn khi mất mọi thiết bị; nếu recovery dựa trên email quá yếu, attacker có thể bỏ qua bảo mật của passkey.
- Giới hạn lượng credential/account, chống abuse và audit mỗi lần thêm/xóa/đăng nhập thất bại; cảnh báo user về thay đổi credential.
- Nếu tổ chức yêu cầu authenticator phần cứng hoặc attestation, cần đánh giá policy riêng. `attestation: none` hỗ trợ privacy và broad compatibility nhưng **không chứng minh thiết bị thuộc một vendor/model cụ thể**.
- Thử user verification policy `preferred`/`required` theo mức rủi ro. Không xem mọi request WebAuthn đều chắc chắn đã xác minh sinh trắc học.
- Đối chiếu trạng thái user bị khóa/xóa trong local account store trước khi tiếp tục cấp quyền truy cập, kể cả credential có chữ ký đúng.

### 10.4. Đồng bộ passkey, privacy và signCount

Một số passkey có thể được đồng bộ giữa các thiết bị. Điều này tăng tính khả dụng nhưng cũng ảnh hưởng lựa chọn policy (backup state, attestation, device-bound requirements). Server phải đánh giá metadata và bản ghi credential theo thiết kế và tiêu chuẩn, không tự coi credential đồng bộ là “không an toàn” hoặc hardware key là “luôn an toàn”.

`signCount` có thể giúp nhận biết dấu hiệu clone ở một số authenticator, nhưng với credential đồng bộ counter không luôn tăng như mô hình cũ. Đánh giá bất thường cùng với backup flags, policy và risk signals; không tự đặt quy tắc “counter bằng 0 thì chắc chắn gian lận”.

### 10.5. Access control sau đăng nhập

WebAuthn xác thực **ai đang truy cập**, không tự tạo `ROLE_ADMIN` hoặc bảo đảm user có thể xem mọi dữ liệu. Spring Security `Authentication` nhận principal/authorities gắn local account; authorization vẫn cần kiểm tra endpoint, tenant và object ownership.

Nếu API cần access token, dùng giao thức OAuth2/OIDC hoặc một token issuer riêng có thiết kế rõ; login WebAuthn thành công trong web session không tự biến thành bearer access token cho các microservice.

## 11. Ma trận lỗi thực tế

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `http.webAuthn(...)` không compile | Spring Security quá cũ (trước 6.4), sai major hoặc thiếu config module | Xem dependency tree, BOM và version-specific docs |
| `ClassNotFoundException`/`NoClassDefFoundError` liên quan WebAuthn | 6.5 thiếu WebAuthn4J hoặc 7.x thiếu `spring-security-webauthn` | Đối chiếu artifact chính xác theo nhánh Spring Security |
| Browser báo `SecurityError`/RP ID invalid | RP ID không hợp lệ cho hostname hiện tại | Dùng đúng host, RP ID không scheme/port, không dùng domain không liên quan |
| Browser báo secure context không hợp lệ | Truy cập HTTP trên miền public | Bật HTTPS; dev có thể dùng `http://localhost:8080` |
| Browser báo `NotAllowedError` | User hủy, timeout, policy authenticator, không có credential phù hợp hoặc điều kiện browser khác | Kiểm tra UI, authenticator, timeout, RP ID và browser logs |
| User có passkey nhưng server từ chối sau restart | Default WebAuthn credential store là in-memory | Dùng JDBC/custom repository và migration schema |
| Registration bị 403 | CSRF token thiếu/sai; policy của authenticated user | Gửi CSRF token và xác minh session/authorization |
| Options request thành công, submit báo challenge invalid | Session/options không khớp, cookie không gửi lại, nhiều node không share state hoặc challenge timeout | Kiểm tra HttpSession, creation options repository, cookie và routing |
| Authentication trả 401 dù credential tồn tại | Chữ ký/credential ID/challenge/origin/RP hash/user policy không hợp lệ | Debug có lọc dữ liệu nhạy cảm; không tắt validation |
| Credential thuộc user khác lại được gắn vào account hiện tại | Enrollment flow lấy user ID từ input chưa được xác thực | Ràng buộc registration với user principal từ SecurityContext |
| Passkey login thành công nhưng trang admin trả 403 | Authentication hợp lệ nhưng thiếu authority | Kiểm tra user store và policy, không đổi cryptographic verification |
| Dev chạy localhost nhưng staging lỗi | Sai HTTPS public origin, proxy headers, RP ID hoặc cookie | So sánh URL browser với allowedOrigins/rpId |
| Có thể đăng nhập lại sau khi khóa account | Local account state chưa được kiểm tra trong login path | Nạp status/quyền từ nguồn chuẩn và kiểm tra trước cấp session |
| Test MockMvc xanh nhưng WebAuthn không hoạt động | MockMvc injected principal, không thực hiện browser/authenticator ceremony | Tạo browser integration test với virtual authenticator hoặc device thật |

**Thứ tự debug hợp lý:** Spring version/dependency → ứng dụng khởi động và filter chain → browser secure context → rpId/allowedOrigins → registration bootstrap/CSRF → options challenge/session → credential store → assertion validation → local user mapping/authorization.

Không log raw assertion, full `clientDataJSON`, user biometric (không được server nhận), cookie session hay credential payload không cần thiết. Log correlation ID, loại lỗi và metadata không nhạy cảm để hỗ trợ điều tra.

## 12. Checklist kiểm thử tích hợp và vận hành

Một luồng kiểm thử WebAuthn đầy đủ cần có cả **happy path** và **failure path**:

1. **Registration:** user đã đăng nhập có thể đăng ký; anonymous bị từ chối; thiếu CSRF bị chặn; sai challenge/origin bị từ chối.
2. **Authentication:** passkey đăng ký có thể login lại; credential ID lạ hoặc chữ ký sai bị 401; challenge cũ bị từ chối.
3. **Domain binding:** credential đăng ký ở RP ID dự kiến không dùng ở domain khác; origin sai bị chặn.
4. **State:** session/challenge được giữ qua hai request, cả khi ứng dụng chạy nhiều node.
5. **Persistence:** restart/redeploy không làm mất credential; xóa credential rồi đăng nhập lại phải thất bại.
6. **Local account:** account disabled/revoked không được quyền; role/tenant policy vẫn được thực thi.
7. **Recovery:** mất một hoặc tất cả passkey có quy trình khôi phục an toàn; người dùng được thông báo khi thêm/xóa passkey.
8. **Browser/device:** thử những browser, hệ điều hành, platform authenticators, synced passkeys và hardware keys nằm trong danh sách hỗ trợ thực tế.
9. **Security:** kiểm tra HTTPS, CSRF, cookie, session fixation/logout, XSS, CSP, origin, audit và rate limiting.
10. **Compatibility:** kiểm tra fresh Maven/Gradle build và deployment với đúng Spring Boot/Security versions, không chỉ chạy trên máy có cached JAR.

Test automation với browser thường dùng **virtual authenticator** để sinh credential/signature thực trong test; vẫn nên có ít nhất một vòng kiểm thử thủ công trên thiết bị đại diện vì UI/OS passkey provider thay đổi theo nền tảng.

## 13. Những hiểu lầm cần tránh

**“Passkey nghĩa là server nhận vân tay của user.”** Sai. Sinh trắc học hoặc PIN được kiểm tra tại thiết bị/provider; server kiểm chứng public-key assertion.

**“Spring Boot starter-security tự đủ cho mọi Spring version.”** Sai. 6.5 cần `webauthn4j-core` theo tài liệu; 7.x cần `spring-security-webauthn` riêng.

**“Chỉ cần thêm `.webAuthn(...)` là production-ready.”** Sai. Cần HTTPS, RP ID/origin, credential persistence, enrollment policy, session/CSRF, account recovery và monitoring.

**“Passkey không thể bị phishing nên không cần CSRF hoặc XSS protection.”** Sai. Phishing-resistant authentication không loại bỏ yêu cầu bảo vệ phiên, registration endpoint, tài khoản và ứng dụng.

**“User đang có passkey trên điện thoại thì backend sẽ biết nó mãi.”** Sai. Server cần credential record và public key bền vững; thiết bị giữ private key không đồng nghĩa server còn metadata sau restart.

**“Tắt formLogin sẽ tự động có onboarding passwordless.”** Sai. Cần thiết kế cách tạo user tin cậy, đăng ký passkey đầu tiên và khôi phục khi mất thiết bị.

**“MockMvc `user(...)` đã kiểm tra WebAuthn.”** Sai. Nó chỉ giả lập Spring Authentication; không gọi `navigator.credentials` và không xác minh chữ ký.

**“RP ID là URL đầy đủ.”** Sai. RP ID là miền, còn origin có scheme/host/port; server phải bảo vệ cả hai.

## 14. Câu hỏi tự kiểm tra

1. **WebAuthn lưu gì ở server?** Credential ID, public key, user handle và metadata/policy cần thiết, không phải private key hay fingerprint.
2. **Tại sao phải gọi `navigator.credentials.create` trước `navigator.credentials.get` đối với tài khoản mới?** Vì RP phải đăng ký credential để có public key đối chiếu assertion sau này.
3. **Phân biệt `rpId` và `allowedOrigins`?** RP ID xác định phạm vi domain credential; allowedOrigins là các web origin scheme/host/port mà RP chấp nhận.
4. **Điều kiện HTTPS có ngoại lệ nào cho dev?** `localhost` trên HTTP được coi là secure context ngoại lệ cho WebAuthn.
5. **Spring Security 6.5 phải thêm dependency nào?** `com.webauthn4j:webauthn4j-core` theo version-specific docs; `spring-security-web` thường có nhờ starter.
6. **Spring Security 7.1 phải thêm dependency nào?** `org.springframework.security:spring-security-webauthn` với BOM tương thích.
7. **Tại sao xin registration options qua POST và phải có CSRF?** Vì server tạo/chứa challenge/state gắn với session; nếu không bảo vệ, thao tác credential enrollment dễ bị lạm dụng.
8. **Vì sao login qua browser sau restart thất bại dù thiết bị vẫn có passkey?** Default credential store phía Spring trong memory đã mất; cần repository bền vững.
9. **Passkey login có tự cấp quyền admin không?** Không. Spring authorization vẫn dựa vào authorities và chính sách tài nguyên.
10. **Mất passkey duy nhất thì sao?** Cần quy trình recovery đã được thiết kế từ trước, không mặc nhiên quay về phương thức yếu có nguy cơ account takeover.
11. **Đăng nhập bằng passkey có luôn yêu cầu biometric không?** Không. Authenticator có thể dùng PIN hoặc phương thức local khác và policy UV có thể khác nhau.
12. **Chỉ test với `@WithMockUser` đủ chưa?** Chưa. Cần browser/authenticator integration tests để kiểm chứng challenge, signature và RP binding.

## 15. Tài liệu chính thức và tài liệu đối chiếu

- **Spring Security 6.5 – Passkeys:** https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- **Spring Security 7.1 – Passkeys:** https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html
- **Spring Security 6.5 – Getting Spring Security và BOM:** https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
- **Spring Security 6.5 – What's New, JDBC Persistence:** https://docs.spring.io/spring-security/reference/6.5/whats-new.html
- **Spring Security 7.1 – Modules:** https://docs.spring.io/spring-security/reference/modules.html
- **Spring Security 6.5 – WebAuthnConfigurer API:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html
- **WebAuthn Level 3 specification:** https://www.w3.org/TR/webauthn-3/
- **Spring Boot 3.5.16 release notice:** https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- **Spring Boot 3.4 Security/Passkeys example:** https://spring.io/blog/2024/11/24/bootiful-34-security/
