# Thông tin xác thực, bằng chứng danh tính và ranh giới tin cậy

Trong Spring Security, một yêu cầu mang tên người dùng, mật khẩu, cookie hoặc token **chưa tự động trở thành yêu cầu đáng tin cậy**. Hệ thống phải xác định dữ liệu đó đến từ đâu, nó chứng minh được điều gì, ai có quyền xác nhận nó, nó còn hiệu lực hay không và quyết định truy cập nào được phép dựa trên kết quả. Đây là nền tảng của authentication (xác thực) và cũng là điểm bắt đầu để hiểu các ranh giới tin cậy trong ứng dụng web.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **danh tính**, **định danh**, **thông tin xác thực**, **bằng chứng**, **xác thực** và **phân quyền**.
2. Giải thích mật khẩu, passkey, OTP, cookie phiên, API key và JWT thật sự chứng minh điều gì; nhận biết điều chúng **không** chứng minh.
3. Xác định các ranh giới tin cậy giữa trình duyệt, reverse proxy, ứng dụng Spring Security, kho danh tính và nhà cung cấp danh tính (IdP).
4. Đọc được đường đi từ bằng chứng do client gửi đến `Authentication` đã được kiểm tra và `SecurityContext`.
5. Đề xuất các bước kiểm chứng bằng chứng, chống giả mạo/replay và các thử nghiệm dương tính, âm tính cho từng ranh giới.

## 2. Sáu khái niệm phải tách riêng

| Khái niệm | Ý nghĩa | Ví dụ và giới hạn |
| --- | --- | --- |
| **Danh tính (identity)** | Thực thể mà hệ thống muốn nói tới: con người, dịch vụ, thiết bị hoặc một tài khoản ứng dụng. | Tài khoản nhân viên số `u-123`; có tài khoản chưa đồng nghĩa danh tính pháp lý đã được kiểm chứng. |
| **Định danh (identifier)** | Giá trị dùng để tìm hoặc tham chiếu một danh tính trong một phạm vi xác định. | Username, email, account ID, hoặc cặp `(issuer, sub)` của OIDC. Email có thể thay đổi hoặc tái cấp; không mặc nhiên là khóa toàn cục. |
| **Thông tin xác thực (credential/authenticator)** | Bí mật, khóa hoặc phương tiện mà chủ thể dùng để chứng minh quyền kiểm soát. | Mật khẩu, khóa riêng của passkey, chứng chỉ client, khóa API. Thông tin đăng nhập tự khai là đầu vào chưa được xác minh. |
| **Bằng chứng (evidence/assertion)** | Dữ liệu và kết quả kiểm chứng hỗ trợ một khẳng định về chủ thể. | Mật khẩu khớp hash, chữ ký challenge hợp lệ, JWT có chữ ký hợp lệ và đúng audience. Mức tin cậy phụ thuộc quy trình tạo và kiểm chứng. |
| **Authentication — xác thực** | Quá trình hệ thống kiểm tra bằng chứng theo chính sách rồi gắn một principal đã xác thực cho ngữ cảnh xử lý. | Sau đăng nhập đúng, ứng dụng biết request được trình bày bởi bên kiểm soát authenticator của tài khoản; chưa chắc biết người đang ngồi trước máy là ai ngoài đời. |
| **Authorization — phân quyền** | Quyết định principal đã được nhận diện có được thực hiện hành động cụ thể trên tài nguyên cụ thể hay không. | `ROLE_USER` có thể đọc hồ sơ của chính mình; không vì đã đăng nhập mà được đọc hồ sơ tài khoản khác. |

**Identity proofing** (kiểm chứng danh tính khi đăng ký, ví dụ đối chiếu giấy tờ) khác **authentication** (kiểm tra lại quyền kiểm soát authenticator khi đăng nhập). Xác minh email thường chỉ chứng minh có quyền nhận thư tại hộp thư đó ở thời điểm kiểm tra; nó không tự chứng minh tên, nghề nghiệp hay tư cách pháp lý. Trong mô hình NIST, mức bảo đảm của identity proofing, authentication và federation được đánh giá theo các khía cạnh riêng. Đừng viết một cờ `verified=true` chung để suy ra tất cả.

Tương tự, `Authentication.getName()` là tên principal mà cơ chế xác thực đã chấp nhận; nó không phải bằng chứng độc lập. Một request gửi `{"userId":"admin"}` không được phép tự quyết định principal là `admin`.

## 3. Bằng chứng danh tính thực sự chứng minh điều gì?

Một hệ thống đáng tin không chỉ hỏi “có token/mật khẩu không?” mà hỏi “**bằng chứng này được ràng buộc với chủ thể, mục đích, hệ thống nhận và thời điểm nào?**”.

| Phương tiện | Điều có thể được chứng minh sau khi kiểm chứng đúng | Điều không được tự suy ra | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| Mật khẩu | Client biết bí mật liên kết với tài khoản. | Người nhập chắc chắn là chủ tài khoản ngoài đời; mật khẩu chưa bị lộ. | Credential stuffing, phishing, brute force; hash mật khẩu an toàn, TLS, giới hạn thử và MFA phù hợp. |
| OTP qua ứng dụng/TOTP | Client có quyền lấy mã từ phương tiện đang giữ secret TOTP tại thời điểm đó. | Chống phishing hoàn toàn hoặc thiết bị chắc chắn không bị chiếm quyền. | Chặn phát lại trong cửa sổ hợp lệ; mã nhập tay có thể bị kẻ tấn công chuyển tiếp. |
| SMS/email OTP | Client nhận được mã qua kênh được đăng ký. | Kênh đó an toàn tương đương passkey hoặc chứng minh danh tính pháp lý. | Chuyển SIM, chiếm hộp thư, phishing, chậm trễ và replay. |
| WebAuthn/passkey | Authenticator dùng khóa riêng trả lời challenge cho relying party hợp lệ; server kiểm chữ ký, challenge và origin/RP ID theo giao thức. | Mọi passkey đều cùng mức ràng buộc thiết bị hoặc người dùng; chủ tài khoản không thể bị lừa trong tình huống khác. | Quản lý đăng ký/thu hồi khóa, khôi phục tài khoản; dùng kiểm tra giao thức chuẩn. |
| Chứng chỉ client/mTLS | Bên kết nối sở hữu khóa riêng tương ứng chứng chỉ đã được chấp nhận theo chính sách. | Chứng chỉ của service tự động đồng nghĩa người dùng cuối được phép làm mọi việc. | Chính sách CA, tên chủ thể, vòng đời và thu hồi chứng chỉ. |
| API key hoặc bearer token | Bên gửi nắm được giá trị bí mật/token mà server chấp nhận. | Người gửi là chủ thể gốc tại thời điểm phát hành; token chưa từng bị đánh cắp. | Scope, hạn sử dụng, luân chuyển, thu hồi, quản lý secret, hạn chế replay. |
| Cookie session | Trình duyệt gửi định danh phiên mà server công nhận, hoặc dữ liệu phiên hợp lệ theo thiết kế. | Mật khẩu đang được nhập lại ở mỗi request; cookie không thể bị dùng lại nếu bị đánh cắp. | Session hijacking, session fixation, CSRF, timeout, logout và thuộc tính cookie. |
| ID token/assertion của IdP | Nhà phát hành được tin cậy đã ký một phát biểu về phiên xác thực/chủ thể cho bên nhận cụ thể, nếu kiểm đúng giao thức. | Token nào mang trường `sub` cũng là access token hợp lệ cho API của bạn. | Kiểm issuer, audience, signature, nonce/state theo luồng, thời gian và ánh xạ tài khoản. |

**Bearer** nghĩa là “ai cầm giá trị có thể dùng” trong phạm vi quyền token: chữ ký hợp lệ của JWT chứng minh tính toàn vẹn và nguồn ký, **không** ngăn người lấy cắp JWT sử dụng lại. Cơ chế proof-of-possession như mTLS hoặc DPoP có thêm kiểm tra quyền sở hữu khóa; không thể suy ra đặc tính đó từ JWT bearer thông thường.

**Phân biệt authentication với xác thực thuộc tính:** Một IdP có thể xác thực principal `sub=abc`; ứng dụng muốn cho thao tác “chuyển tiền” vẫn phải kiểm quyền, trạng thái tài khoản, tenant, giới hạn số tiền và có thể yêu cầu xác thực mạnh hơn gần thời điểm giao dịch.

## 4. Ranh giới tin cậy: nơi một khẳng định phải được kiểm lại

Một ranh giới tin cậy (trust boundary) là điểm dữ liệu đi từ vùng mà bên nhận **không có lý do mặc định để tin** sang thành phần sẽ đưa ra quyết định bảo mật. Dữ liệu vượt ranh giới phải được xác thực và chuẩn hóa tại đúng thành phần có thẩm quyền.

```text
[Người dùng / trình duyệt / mobile app]
          |
          | (A) HTTP request: cookie, Authorization, body, header
          v
[Internet] --> [Gateway / reverse proxy / load balancer]
                          |
                          | (B) request chuyển tiếp; header có thể bị giả mạo
                          v
                 [Spring Boot + Spring Security]
                    |      |        |
                    |      |        +--> [Policy / dữ liệu tài nguyên]
                    |      +--> (C) [Kho user + password hash]
                    +---------> (D) [IdP / JWKS / OAuth2-OIDC]
```

- **A — client → hạ tầng nhận request:** Mọi tham số, cookie, header, JSON body, client-side role, hidden field và địa chỉ IP báo cáo từ client đều là đầu vào chưa tin cậy. Dùng HTTPS/TLS và bảo vệ kênh, nhưng TLS chỉ bảo vệ truyền tải; nó không biến một `userId` do client tự điền thành danh tính đáng tin.
- **B — proxy → ứng dụng:** Chỉ chấp nhận các header nhận dạng do **proxy xác thực đã kiểm soát** chèn vào khi mạng nội bộ, tuyến truy cập và cấu hình loại bỏ header trùng/giả đều được kiểm soát. Không lấy `X-User-Id`, `X-Role`, `X-Forwarded-User` từ Internet rồi tạo `Authentication`. Proxy cũng phải tránh bị client giả mạo các header `Forwarded`/`X-Forwarded-*` ảnh hưởng đến host, scheme hoặc redirect.
- **C — ứng dụng → user store:** Username do client nhập chỉ là khóa tra cứu. Kho user trả về hash mật khẩu, trạng thái active/locked, quyền theo nguồn có thẩm quyền; đối chiếu bằng `PasswordEncoder.matches(raw, encoded)`. Không coi username tồn tại là đã xác thực, không lưu/so sánh mật khẩu dạng rõ.
- **D — ứng dụng → IdP/token issuer:** Ứng dụng chọn **issuer được cấu hình tin cậy**, lấy khóa xác thực qua kênh và metadata đúng chính sách, kiểm signature và claims áp dụng. Một URL JWKS hoặc giá trị `iss` do request tự chỉ định không được dùng làm quyết định tin cậy.
- **Ứng dụng → tài nguyên nghiệp vụ:** Sau khi có principal, vẫn kiểm **quyền cho hành động và object cụ thể**. `accountId` nằm trong URL/body thường là dữ liệu do client chọn, không tự trở thành account được phép truy cập.

Câu hỏi thực hành cho từng ranh giới: **Ai tạo giá trị này? Bên nào có quyền ký/xác minh? Kiểm được tính toàn vẹn, thời hạn và đúng đối tượng nhận không? Dữ liệu nào vẫn cần đối chiếu với nguồn đáng tin?**

### Chuỗi tin cậy không được đảo ngược

Sai: “Header `X-User: alice` được gửi tới API → gọi `SecurityContextHolder` và đặt principal `alice` → coi là đăng nhập.” Tại đây ứng dụng đã đưa dữ liệu client tự khai thành ngữ cảnh tin cậy mà không có bước kiểm chứng.

Đúng: “Client gửi credential/token → cơ chế xác thực phù hợp kiểm chứng → ánh xạ subject với tài khoản/tenant theo chính sách → tạo `Authentication` có trạng thái và authorities phù hợp → authorization kiểm hành động và tài nguyên”. Chỉ các thành phần được tin cậy mới được nâng bằng chứng chưa kiểm thành kết luận xác thực.

## 5. Vòng đời của bằng chứng: đăng nhập khác mỗi request tiếp theo

### 5.1 Username/password và session phía server

1. Client gửi username/password qua kết nối HTTPS tới endpoint đăng nhập có bảo vệ chống lạm dụng.
2. Server tìm user theo định danh chuẩn hóa, kiểm trạng thái tài khoản và kiểm mật khẩu đã hash bằng password encoder thích hợp; nếu chính sách yêu cầu, kiểm thêm MFA.
3. Khi thành công, hệ thống tạo một principal đã xác thực và **thiết lập phiên** theo cơ chế Spring Security đã cấu hình. Phiên cần định danh khó đoán, có vòng đời rõ ràng, thay đổi session ID khi đăng nhập để giảm nguy cơ session fixation.
4. Trình duyệt nhận cookie phiên với các thuộc tính bảo vệ, ví dụ `Secure`, `HttpOnly`, `SameSite` phù hợp; phía server giữ trạng thái phiên và ràng buộc principal theo chính sách.
5. Request sau gửi cookie; server **kiểm lại tính hợp lệ của phiên** và khôi phục ngữ cảnh người dùng, sau đó phân quyền request. Không mặc nhiên kiểm lại mật khẩu ở từng request.
6. Logout, hết hạn hoặc thu hồi phiên phải khiến **server từ chối** định danh phiên cũ. Chỉ xóa cookie ở trình duyệt chưa đủ nếu bản sao cookie đã bị lấy cắp.

Cookie session là một loại bearer credential. `HttpOnly` ngăn JavaScript đọc trực tiếp cookie, không thay thế phòng chống XSS; `SameSite` giảm một số luồng CSRF, không thay thế biện pháp CSRF thích hợp; `Secure` cần HTTPS. Với API dùng browser cookie tự gửi, phải đánh giá CSRF kể cả khi các endpoint chỉ chấp nhận JSON.

### 5.2 Bearer access token cho API

1. Client lấy access token từ authorization server theo flow thích hợp.
2. API chỉ chấp nhận token qua kênh quy định, thường là `Authorization: Bearer <token>` trên HTTPS; **không** tin dữ liệu token chỉ vì đọc được Base64 hoặc thấy JSON parse hợp lệ.
3. Với JWT tự chứa, resource server kiểm chữ ký theo thuật toán/khóa được cho phép, `iss`, `aud`, `exp`, `nbf` và các ràng buộc liên quan (`scope`/`scp`, token type, tenant, chính sách thu hồi nếu có). Với opaque token, dùng cơ chế introspection tin cậy theo thiết kế.
4. Chỉ sau khi hợp lệ, server ánh xạ claims thành principal và authorities; kiểm **quyền truy cập tài nguyên** trên từng request.
5. Hết hạn token không đồng nghĩa mọi token đã phát có thể thu hồi tức thì; cân nhắc hạn dùng ngắn, chính sách thu hồi/introspection, rotation và kiểm trạng thái tài khoản cho các trường hợp rủi ro.

JWT là một định dạng; **JWT không tự đồng nghĩa OAuth2/OIDC, và không phải mọi JWT đều dùng để gọi API**. OIDC **ID token** hướng tới client/relying party để mô tả kết quả đăng nhập; OAuth2 **access token** được cấp để trình bày với resource server. API cần kiểm token có audience dành cho **chính API**, không nhận nhầm ID token hoặc access token cấp cho API khác.

### 5.3 Vì sao xác thực thành công lúc T0 chưa đủ cho mọi thời điểm

Phiên có thể bị đánh cắp, quyền có thể bị thu hồi, mật khẩu có thể bị đổi, thiết bị có thể bị mất, giao dịch có thể có rủi ro mới. Thiết kế cần thời hạn, thu hồi, chính sách reauthentication/step-up cho hành động nhạy cảm và kiểm phân quyền liên tục. Authentication assurance phụ thuộc loại bằng chứng và thời điểm xác thực, không phải một cờ bất biến.

## 6. Spring Security biến bằng chứng thành SecurityContext thế nào?

Trong ứng dụng **Servlet/MVC**, luồng khái niệm là:

```text
HTTP request
  -> SecurityFilterChain
  -> filter phù hợp cơ chế (HTTP Basic, form login, bearer token, ...)
  -> Authentication token đầu vào (có thể chưa authenticated)
  -> AuthenticationManager / AuthenticationProvider hoặc decoder liên quan
  -> xác minh credential, token và chính sách
  -> Authentication đã xác thực: principal + authorities + details
  -> SecurityContextHolder chứa SecurityContext cho lượt xử lý hiện tại
  -> AuthorizationFilter / method security quyết định quyền
  -> controller/service
```

Một số cơ chế có thể dùng filter và thành phần kiểm chứng riêng, vì vậy sơ đồ là **mô hình tư duy**, không phải lời khẳng định mọi request đều đi qua cùng một `AuthenticationProvider`. Các thành phần cần biết:

- `SecurityFilterChain` xác định bộ lọc bảo mật áp dụng cho request; thứ tự chain và request matcher ảnh hưởng cơ chế được thực thi.
- `Authentication` vừa có thể là yêu cầu xác thực ban đầu (principal + credentials chưa kiểm), vừa là kết quả đã xác thực. `getPrincipal()` biểu diễn chủ thể, `getCredentials()` có thể được xóa sau xác thực; `getAuthorities()` chứa quyền cao cấp đã được gán.
- `AuthenticationManager` (thường là `ProviderManager`) điều phối các `AuthenticationProvider` phù hợp như xác thực username/password. Provider kiểm chứng trước khi trả kết quả thành công.
- `SecurityContextHolder` cung cấp `SecurityContext` trong ngữ cảnh xử lý; mặc định Servlet dùng `ThreadLocal`. Bộ lọc bảo mật chịu trách nhiệm dọn ngữ cảnh phù hợp. Đừng tự giả định ThreadLocal được truyền sang thread bất đồng bộ hoặc request kế tiếp.
- `SecurityContextRepository` có thể giúp nạp/lưu context qua các request theo cấu hình; **đã xác thực trong request hiện tại** không tự có nghĩa **đã lưu phiên** cho request sau.
- `GrantedAuthority` thường đại diện roles hoặc scopes đã ánh xạ. `ROLE_ADMIN` không thể đến trực tiếp từ một tham số `role=ADMIN` do client truyền.
- Cơ chế **anonymous authentication** có thể đặt một `AnonymousAuthenticationToken` trong context cho request không đăng nhập. Vì thế chỉ kiểm `authentication != null` hoặc thậm chí `authentication.isAuthenticated()` tại mã nghiệp vụ **không phải cách đáng tin để kết luận có người dùng thật đã đăng nhập**; dùng cấu hình `authenticated()`, `AuthenticationTrustResolver` hoặc kiểm chính sách Spring Security phù hợp.

**Authentication khác Authorization:** Một principal có thể đăng nhập thành công nhưng vẫn nhận HTTP `403 Forbidden` khi thiếu quyền. Với HTTP Basic, request không có credential hợp lệ đến resource yêu cầu đăng nhập thường nhận `401 Unauthorized` kèm challenge; một `403` khác cũng có thể phát sinh vì CSRF hoặc chính sách bảo mật khác, nên phải đọc cả nguyên nhân thay vì đoán từ mã trạng thái.

## 7. Ví dụ chạy được: một ranh giới xác thực bằng Spring Security

Ví dụ dưới đây là ứng dụng **Spring Boot Servlet** dùng Java 17+, Spring Boot 3.x và Spring Security 6.x với các dependency `spring-boot-starter-web`, `spring-boot-starter-security`. Mục tiêu: request công khai không cần credential; `/api/me` chỉ chấp nhận principal đã xác thực bằng HTTP Basic. File đơn `src/main/java/demo/AuthDemoApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-change-me"))
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "subject", authentication.getName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority).toList());
    }
}
```

Chạy qua lệnh của dự án Spring Boot đã khai báo hai starter tương ứng, ví dụ `./gradlew bootRun`; trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Nếu tạo một dự án Maven tương đương, lệnh là `./mvnw spring-boot:run`. Đây là ví dụ **Spring Boot có dependencies**, không phải chương trình chỉ chạy bằng `javac` chuẩn của JDK.

Thử từ terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u learner:wrong http://localhost:8080/api/me
curl -sS -u learner:demo-change-me http://localhost:8080/api/me
```

Kết quả có thể kiểm chứng:

| Request | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | URL được cấu hình `permitAll()`. |
| `GET /api/me` không có credential | HTTP 401 | Chưa có principal hợp lệ cho endpoint yêu cầu đăng nhập. |
| `GET /api/me` với `learner:wrong` | HTTP 401 | Password không khớp hash của tài khoản. |
| `GET /api/me` với `learner:demo-change-me` | HTTP 200; JSON có `subject` = `learner`, `authenticated` = `true` và `authorities` chứa `ROLE_LEARNER` | Server xác thực bằng chứng và gán authority từ user store; thứ tự các khóa JSON không phải hợp đồng cố định. |

**Diễn giải:** Client có thể tự thêm header `X-User: admin`, nhưng code không đọc header đó để tạo principal. `authentication.getName()` đến từ kết quả kiểm chứng của Spring Security. `User.withUsername(...).roles("LEARNER")` gán `ROLE_LEARNER` tại nguồn cấu hình server, khác với role do client tự khai.

Ví dụ dùng mật khẩu cố định và in-memory user **chỉ để học tại máy local**. HTTP Basic truyền credential được mã hóa Base64, **không phải mã hóa bảo mật**; triển khai thực tế luôn yêu cầu HTTPS, quản lý secret, lưu hash trong kho an toàn và phòng chống brute force. Bảo vệ CSRF mặc định vẫn cần được xem xét cho request thay đổi trạng thái có cookie/session; không thêm `csrf.disable()` chỉ để “cho qua” lỗi.

### 7.1 Đọc kết quả mà không mở lỗ hổng tin cậy

Code sau là **minh họa logic**, không phải class Java chạy độc lập:

```java
// Trong service đã được bảo vệ bởi Spring Security:
String caller = authentication.getName(); // principal do server xác thực
String requestedAccount = request.accountId(); // dữ liệu client chọn

// Phải kiểm quyền của caller với requestedAccount trước khi đọc.
authorizationService.checkCanRead(caller, requestedAccount);
return accountService.findById(requestedAccount);
```

Lỗi điển hình là thay `checkCanRead(...)` bằng `if (authentication.isAuthenticated())` rồi trả bất kỳ `accountId` nào; đó là broken object-level authorization (IDOR/BOLA). Authentication đúng vẫn không cứu được phân quyền sai.

## 8. Bốn tình huống đối chiếu trước và sau

### Tình huống A: “Tôi đã đặt username trong header”

- **Sai:** API lấy `X-User-Id` do client truyền, gọi `new UsernamePasswordAuthenticationToken(user, null, authorities)` với authorities được tự đặt rồi gắn vào context.
- **Đúng:** API kiểm bearer token bằng resource server, hoặc tin header chỉ khi một authentication gateway đã được bảo vệ và proxy **loại bỏ mọi bản sao do client gửi**, kênh và quyền truy cập giữa gateway–app đều được kiểm soát. Trường hợp đơn giản, tốt nhất để Spring Security kiểm credential trực tiếp.

### Tình huống B: “JWT decode ra sub nên đã xác thực”

- **Sai:** Chạy Base64-decode payload, lấy `sub` và `scope` rồi cấp quyền mà không kiểm chữ ký.
- **Đúng:** Resource server dùng một issuer/khóa **được cấu hình trước**, kiểm chữ ký, thuật toán, thời gian, `aud` là API này, các ràng buộc tenant/subject, sau đó mới ánh xạ scope thành authorities. Nếu `aud` thuộc service khác, trả 401 dù chữ ký đúng.

### Tình huống C: “Đã đăng nhập thì được xem đơn hàng”

- **Sai:** Endpoint `GET /orders/{id}` chỉ kiểm `authenticated()` rồi trả bất kỳ đơn có id đó.
- **Đúng:** Sau authentication, service đối chiếu `order.ownerId` hoặc quyền của nhân viên và tenant của principal với đối tượng đơn hàng. Trả lỗi theo chính sách khi thiếu quyền, không để thông tin đơn của tenant khác rò rỉ.

### Tình huống D: “Cookie phiên chứng minh người dùng vừa nhập mật khẩu”

- **Sai:** Dùng sự hiện diện cookie để coi giao dịch có bảo đảm cao và bỏ kiểm tra lại.
- **Đúng:** Server kiểm trạng thái phiên, giới hạn thời gian và rủi ro; thao tác nhạy cảm có thể yêu cầu reauthentication/step-up bằng yếu tố mạnh hơn. Logout phải làm phiên cũ hết hiệu lực ở server.

## 9. Kiểm tra và thiết kế an toàn tại mỗi ranh giới

### 9.1 Trước khi chấp nhận bằng chứng

- **Nguồn và mục đích:** Xác định credential/token dành cho ứng dụng, API, môi trường và tenant nào. Không cho client tự lựa chọn issuer hoặc điểm lấy khóa tin cậy.
- **Tính toàn vẹn và chứng minh sở hữu:** Xác minh chữ ký/secret/challenge bằng thư viện và cấu hình đúng; không tự viết thuật toán JWT, hashing hoặc WebAuthn.
- **Thời hạn và chống replay:** Kiểm `exp`, `nbf`, nonce/challenge, session TTL và khả năng thu hồi tương ứng với giao thức; không dùng một mã OTP nhiều lần.
- **Ràng buộc tài khoản:** Ánh xạ kết quả xác thực với subject ổn định, trạng thái tài khoản và tenant đúng. Với federation, dùng cặp `(issuer, subject)` hoặc quy tắc ánh xạ được quản lý; không tự gộp hai danh tính chỉ vì email giống nhau.
- **Lưu trữ credential:** Mật khẩu cần password hash được thiết kế cho password (ví dụ bcrypt, Argon2id, PBKDF2 được cấu hình phù hợp), không dùng SHA-256 trần hay mã hóa có thể giải mã để lưu password. Token/secret đặt trong secret manager hoặc kho bảo vệ tương xứng; không log raw credential.
- **Truyền tải và phiên:** Luôn HTTPS trong production; cookie phiên `Secure`, `HttpOnly`, `SameSite` theo kiến trúc; chống CSRF nơi có xác thực tự động bằng cookie, chống XSS, session fixation và đánh cắp phiên.
- **Giới hạn đặc quyền:** Quyền ít nhất cần thiết; phân quyền theo action và object ở phía server; không lấy role từ client-side UI.
- **Tín hiệu kiểm toán:** Ghi thời gian, cơ chế, issuer, principal ID và kết quả xác thực/phân quyền với dữ liệu tối thiểu; tránh log password, OTP, cookie, Authorization header hay token đầy đủ.

### 9.2 Ma trận kiểm thử tối thiểu

| Phép thử | Kết quả an toàn cần đạt |
| --- | --- |
| Không gửi credential vào endpoint yêu cầu đăng nhập | Bị từ chối trước khi xử lý nghiệp vụ nhạy cảm. |
| Credential sai, hết hạn, thu hồi hoặc bị sửa một byte | Không sinh principal đã xác thực. |
| JWT hợp lệ về chữ ký nhưng sai `iss` hoặc `aud` | Bị từ chối; không cấp scope/role. |
| Client gửi `X-User-Id: admin` hoặc sửa `role` trong body | Không đổi principal hay authorities được server tin cậy. |
| User A đã đăng nhập truy cập `/accounts/B` | Bị phân quyền từ chối nếu A không có quyền trên B. |
| Cookie phiên cũ sau logout/hết hạn; dùng lại OTP | Không được chấp nhận theo chính sách phiên/chống replay. |
| Request thay đổi trạng thái phát sinh từ website khác khi dùng session cookie | Được CSRF policy và thiết kế SameSite/origin phù hợp ngăn chặn. |
| Access token cấp cho API B được gửi tới API A | API A từ chối nếu audience không phải A. |
| Tài khoản bị khóa, quyền/tenant bị thay đổi | Các điểm kiểm soát phản ánh trạng thái mới theo thiết kế thu hồi và freshness đã xác định. |

### 9.3 Lỗi tư duy thường gặp

1. **“Xác thực = xác minh danh tính ngoài đời”:** Thực chất có thể chỉ xác minh quyền kiểm soát một authenticator; identity proofing là quy trình khác.
2. **“Có tên user trong request = principal đáng tin”:** Chỉ nguồn đã được kiểm chứng và chính sách ánh xạ mới tạo ra danh tính tin cậy.
3. **“JWT có chữ ký = được vào mọi API”:** Phải kiểm issuer, audience, thời hạn, scope, mục đích sử dụng và đối tượng dữ liệu.
4. **“Đã login = mọi hành động được phép”:** Authentication chỉ xác định chủ thể; authorization cần quyết định riêng trên mỗi resource.
5. **“HttpOnly/SameSite/TLS giải quyết hết”:** Mỗi cơ chế giảm một nhóm rủi ro; CSRF, XSS, replay, phishing và quyền nghiệp vụ vẫn cần kiểm soát riêng.
6. **“`isAuthenticated()` lúc nào cũng nghĩa là người dùng thật đã đăng nhập”:** Hãy tính tới anonymous token và dùng cơ chế authorization chuẩn thay vì kiểm tra boolean thủ công.
7. **“Chữ ký JWT đảm bảo token không bị lấy cắp”:** Bearer token bị lộ vẫn có thể bị sử dụng lại trước khi hết hạn hoặc bị thu hồi.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Trình duyệt gửi `{"accountId":"42","user":"admin"}`. API có thể lấy `user` để quyết định người gọi là admin không?

**Đáp án:** Không. Các trường JSON do client tự khai. Principal phải đến từ cơ chế authentication đã kiểm chứng; quyền trên `accountId=42` vẫn cần được xét riêng.

**Câu 2.** JWT có chữ ký đúng và chưa hết hạn, nhưng `aud` trỏ đến service thanh toán khác. API quản lý học viên được nhận không?

**Đáp án:** Không. Token không được cấp cho API đang nhận; cần kiểm audience cùng issuer và các ràng buộc khác.

**Câu 3.** API đã biết `authentication.getName() = "alice"`. Alice có mặc nhiên được xem đơn hàng của Bob?

**Đáp án:** Không. Authentication trả lời “ai”; authorization phải trả lời “Alice có được đọc đơn này không?” theo owner, tenant và role/policy.

**Câu 4.** Tại sao việc lưu `SecurityContext` vào phiên không chứng minh rằng client đang nhập lại mật khẩu ở mọi request?

**Đáp án:** Phiên tái sử dụng kết quả xác thực trước đó thông qua cookie/session ID; việc chấp nhận request tiếp theo dựa vào phiên còn hợp lệ, không phải một lần kiểm mật khẩu mới.

## 11. Tài liệu chuẩn để đọc tiếp

- Spring Security — [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, principal và authorities.
- Spring Security — [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm issuer, audience, thời gian và chữ ký cho API.
- Spring Security — [Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder` và `DelegatingPasswordEncoder`.
- OWASP — [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): vòng đời phiên, cookie và các rủi ro session.
- NIST — [SP 800-63 Digital Identity Guidelines](https://pages.nist.gov/800-63-4/): phân biệt identity proofing, authentication và federation; đặc tính chống phishing của authenticator.

**Nguyên tắc ghi nhớ:** Mọi request bắt đầu bằng dữ liệu ngoài ranh giới tin cậy. Chỉ một chuỗi kiểm chứng có nguồn và mục đích rõ ràng mới đủ nâng nó thành `Authentication` đáng tin; sau đó vẫn phải phân quyền hành động trên từng tài nguyên.