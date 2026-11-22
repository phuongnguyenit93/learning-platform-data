# Biểu mẫu đăng nhập, đăng xuất và thao tác nghiệp vụ cần được xét tới

> **Ngữ cảnh:** Spring Security – fundamentals / **CSRF**. Bài tập trung vào **ứng dụng Spring MVC/Servlet có người dùng đăng nhập bằng trình duyệt**, dùng session cookie hoặc một credential mà browser có thể tự đính kèm. Ví dụ sử dụng **Java 17, Spring Boot 3.5.0, Spring Security 6.x, Thymeleaf, JUnit 5 và MockMvc**. Những API hoàn toàn không dùng browser/cookie và WebFlux được phân biệt riêng. Tất cả URL, account và số tiền trong ví dụ chỉ là môi trường học tập, không dùng cho giao dịch thực.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu được vì sao **login**, **logout** và **mọi thao tác thay đổi trạng thái nghiệp vụ** đều nằm trong phạm vi đánh giá CSRF.
2. Giải thích cách CSRF lợi dụng cookie/credentials được browser tự gửi, phân biệt **authentication**, **authorization** và **CSRF protection**.
3. Phân biệt HTTP method an toàn (`GET`, `HEAD`, `OPTIONS`, `TRACE`) với method không an toàn (`POST`, `PUT`, `PATCH`, `DELETE`), và hiểu vì sao **GET không được tạo side effect**.
4. Hiểu `CsrfFilter`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository`, `CsrfTokenRequestHandler`, request attribute `_csrf` và cơ chế token masking/BREACH protection của Spring Security.
5. Tạo biểu mẫu Thymeleaf cho login, logout và nghiệp vụ bằng token hợp lệ; hiểu sự khác nhau giữa auto-insert token và thêm hidden field thủ công.
6. Kiểm thử đầy đủ **token hợp lệ, thiếu, sai, cũ**; xác nhận thao tác nghiệp vụ **không diễn ra** khi bị từ chối.
7. Xử lý token sau login/logout, khi session hết hạn và trong SPA dùng cookie auth.
8. Không vô hiệu CSRF toàn bộ chỉ vì frontend sử dụng JSON hoặc test POST bị 403.
9. Biết khi nào API Bearer token thực sự có thể không cần CSRF, và khi nào `SameSite`/CORS/HTTPS **không** thay thế kiểm tra token.

## 2. CSRF là gì và điểm yếu nằm ở đâu?

**Cross-Site Request Forgery (CSRF)** là hành vi khiến trình duyệt của nạn nhân gửi một HTTP request không chủ đích đến một website mà trình duyệt đang có quan hệ xác thực. Đối tượng tấn công **không cần biết mật khẩu** và thường **không cần đọc được phản hồi**; chỉ cần nạn nhân bị dẫn đến gửi request có tác dụng.

Giả sử Alice đã đăng nhập vào `https://bank.example.test` và browser giữ session cookie. Khi Alice mở một trang khác do kẻ tấn công kiểm soát, trang này có thể cố gửi một form đến website ngân hàng. Nếu ứng dụng ngân hàng chỉ kiểm "có session cookie hợp lệ hay không", nó có thể hiểu request ấy là yêu cầu thật từ Alice.

Ví dụ **chỉ để nhận diện cơ chế** (không gửi đến hệ thống thật):

```html
<!-- Ví dụ rủi ro: form ngoài origin đích có thể kích hoạt request. -->
<form method="post" action="https://bank.example.test/transfer">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="100">
</form>
```

Browser có thể tự gắn cookie đích tùy `SameSite`, đặc điểm request, chính sách browser và cấu hình website. Ngay cả nếu JavaScript từ origin lạ **không đọc được response** do Same-Origin Policy, yêu cầu thay đổi trạng thái có thể đã đến server.

**CSRF khác XSS:** XSS chạy mã không tin cậy trong origin của ứng dụng, có thể đọc/điền CSRF token tùy cách triển khai. CSRF đến từ origin khác nhằm **lợi dụng quyền browser đang giữ**. Phải chống cả hai; token CSRF không sửa lỗi XSS.

**CSRF khác IDOR/BOLA:** CSRF hỏi "request có thật do người dùng chủ động tạo từ giao diện tin cậy không?"; authorization hỏi "người dùng có quyền chuyển tiền/đọc tài nguyên cụ thể này không?". Token CSRF đúng **không** tự biến một hành động trái quyền thành hợp lệ.

## 3. Vì sao phải xét đủ ba nhóm: đăng nhập, đăng xuất, nghiệp vụ?

| Luồng | Request thường gặp | Vì sao có trạng thái cần bảo vệ? | Khi thiếu CSRF |
| --- | --- | --- | --- |
| **Đăng nhập** | `POST /login` | Tạo authentication/session, có thể gắn browser nạn nhân vào một tài khoản khác | **Login CSRF**: nạn nhân bị đăng nhập vào tài khoản kẻ tấn công |
| **Đăng xuất** | `POST /logout` | Hủy security context và session, thay đổi trạng thái xác thực | **Logout CSRF**: kẻ khác ép nạn nhân bị đăng xuất |
| **Nghiệp vụ** | `POST /transfer`, `PUT /profile`, `PATCH /order`, `DELETE /item` | Thay đổi tài sản, hồ sơ, dữ liệu, quyền, trạng thái đơn | Dữ liệu có thể bị thay đổi bằng request được browser tự gửi |
| **Những route bị quên** | `GET /delete?id=...`, GET xác nhận, callback ghi dữ liệu | Dùng method "an toàn" để gây side effect | CSRF filter mặc định **không chặn** GET |
| **Tính năng đặc biệt** | Upload, webhook, endpoint JSON, async job trigger | Có thể tạo tác dụng khi credential tự gửi | Phải phân tích cơ chế xác thực và kênh gọi |

Nếu một API thay đổi trạng thái không bảo vệ CSRF nhưng có authentication/role nghiêm ngặt, **vẫn có thể bị CSRF**: request qua browser của người dùng thật mang theo session đã xác thực.

### 3.1. Login CSRF nguy hiểm thế nào?

Một kịch bản:

1. Kẻ tấn công tạo tài khoản `mallory` trên ứng dụng.
2. Hắn khiến trình duyệt Alice gửi form login với credentials của **mallory**.
3. Nếu login endpoint không bảo vệ CSRF, browser Alice có thể nhận session đã xác thực **dưới tài khoản mallory**.
4. Alice tưởng mình đang sử dụng tài khoản cá nhân, nhập ghi chú/hồ sơ/đơn hàng nhạy cảm.
5. Dữ liệu có thể được lưu vào tài khoản mà Mallory kiểm soát và sau đó đọc được.

Vì vậy **login vẫn phải có CSRF**, dù người dùng chưa đăng nhập. Token CSRF trước login được liên kết với một session hoặc kho token phù hợp; không phải yêu cầu "đã xác thực mới được lấy token".

### 3.2. Logout CSRF nguy hiểm thế nào?

Một trang độc hại có thể khiến browser gọi logout mà Alice không chủ động. Hậu quả thường gặp là bị gián đoạn thao tác, buộc đăng nhập lại, làm mất trạng thái hoặc tạo điều kiện cho các thủ thuật phishing khác. Logout là một thay đổi trạng thái bảo mật nên không nên thực hiện chỉ bằng GET.

Trong Spring Security Servlet với CSRF bật, **GET `/logout` thường hiển thị trang xác nhận**; request **POST `/logout` mang CSRF token hợp lệ** mới kích hoạt logout. Nếu cấu hình tắt CSRF, hành vi mặc định có thể khác và rủi ro phải được đánh giá lại.

### 3.3. Nghiệp vụ không chỉ là POST

Một số URL dễ bỏ sót:

- `POST /account/change-email`, `POST /payment/send`;
- `PUT /api/settings`, `PATCH /api/orders/{id}`, `DELETE /api/files/{id}`;
- `POST /admin/grant-role`, `POST /export/start`, `POST /notifications/subscribe`;
- `GET /account/delete?confirm=true` hoặc `GET /transfer?to=...` nếu code sai nguyên tắc REST.

**Quy tắc bắt buộc:** các HTTP method được coi là *safe* (`GET`, `HEAD`, `OPTIONS`, `TRACE`) phải **không tạo thay đổi trạng thái theo ý định nghiệp vụ**. Nếu code xử lý ghi dữ liệu qua GET, hãy sửa API thành một method unsafe có CSRF protection; đừng nghĩ bật CSRF mặc định sẽ tự bảo vệ GET.

## 4. Cơ chế Synchronizer Token Pattern

Đây là mô hình CSRF phổ biến với session authentication.

```mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security + MVC
    participant R as CSRF Token Repository
    participant App as Nghiệp vụ

    B->>S: GET /transfer (có session cookie nếu đã login)
    S->>R: Lấy/tạo CSRF token gắn với session
    R-->>S: CsrfToken
    S-->>B: HTML form chứa hidden _csrf token

    B->>S: POST /transfer + session cookie + _csrf token
    S->>R: Lấy expected CSRF token
    S->>S: So sánh token trong request với expected token
    alt token thiếu hoặc sai
        S-->>B: 403 Forbidden; không gọi nghiệp vụ
    else token đúng
        S->>S: Kiểm Authentication + Authorization
        S->>App: Thực hiện thao tác hợp lệ
        App-->>B: Kết quả
    end
```

Token cần xuất hiện ở phần request mà một website bên ngoài **không thể tự lấy hoặc tự khiến browser đính kèm thay cho nạn nhân**, chẳng hạn một hidden form parameter hoặc custom request header được JavaScript cùng origin chủ động gửi.

Cookie session là credential browser có thể gửi tự động; **chỉ cookie đó không phải tín hiệu chủ động từ người dùng**. Token CSRF được kết hợp với cơ chế xác thực/phân quyền để phân biệt request hợp lệ.

### 4.1. Token cần bí mật và khó đoán

Một token CSRF phải được sinh bằng cơ chế ngẫu nhiên mật mã thích hợp, liên kết với session/transaction theo thiết kế, kiểm tra tại server và không được lộ qua URL/log/referrer. Không hardcode giá trị token trong HTML build sẵn hoặc dùng một token giống nhau cho tất cả tài khoản.

**Lưu ý thực tế:** CSRF token không nhất thiết được rotate sau **mỗi** request trong cấu hình mặc định. Spring Security có các chiến lược tải/lưu token, xóa token lúc authentication success và logout; vòng đời thực tế phụ thuộc repository. Token có thể tồn tại qua nhiều form submissions trong cùng session.

### 4.2. `CsrfFilter` hoạt động trước business controller

Spring Security cung cấp `CsrfFilter` để kiểm tra request cần CSRF. Khi request bị từ chối, controller/service **không được chạy**. Vì vậy trong kiểm thử cần assert không có mutation ở tầng nghiệp vụ chứ không chỉ kiểm response `403`.

Không được nhầm hai lỗi:

- Thiếu CSRF trên POST: thường trả **403** từ `CsrfFilter`, ngay cả khi user không có quyền.
- Token hợp lệ nhưng user chưa login/không đủ role: request vượt qua CSRF nhưng bị authentication/authorization từ chối, có thể là redirect login/401/403 tùy cấu hình.

Nếu chỉ kiểm thấy `403`, bạn chưa biết đó là kết quả của CSRF hay policy quyền. Cần tách các ca test.

### 4.3. Method nào được yêu cầu token mặc định?

Trong Spring Security Servlet, **mặc định** CSRF filter bỏ qua các method an toàn (`GET`, `HEAD`, `OPTIONS`, `TRACE`), yêu cầu token cho những method khác.

| HTTP method | CSRF mặc định? | Ghi chú |
| --- | --- | --- |
| GET | Không | Phải read-only; không dùng cho xóa/duyệt/chuyển tiền |
| HEAD | Không | Không được tạo side effect |
| OPTIONS | Không | CORS preflight có logic riêng; không mở POST thật |
| TRACE | Không | Nên cân nhắc vô hiệu ở tầng server nếu không cần |
| POST | Có | Bao gồm login, logout, payment, update |
| PUT | Có | Cập nhật resource |
| PATCH | Có | Cập nhật từng phần |
| DELETE | Có | Xóa resource |

Nếu ứng dụng bật `HiddenHttpMethodFilter`, method override, gateway method rewriting hoặc có nhiều filter chain, cần kiểm tra **method được security nhìn thấy** và method MVC xử lý. Không suy đoán rằng cứ “giao diện là form HTML” thì tất cả hành động nghiệp vụ đều chỉ dùng POST.

## 5. Các class CSRF quan trọng trong Spring Security

### 5.1. `CsrfTokenRepository`

Spring Security mặc định lưu expected token trong `HttpSession` bằng `HttpSessionCsrfTokenRepository`. Thành phần có chức năng tạo, tải, lưu/xóa token.

```java
// Minh họa cấu hình tường minh trong HttpSecurity:
http.csrf(org.springframework.security.config.Customizer.withDefaults());
```

Dòng trên **không bắt buộc** nếu ứng dụng đang giữ cấu hình CSRF mặc định; mục tiêu là thấy nơi cấu hình.

Có thể dùng:

```java
// Phương án tùy chỉnh: cùng mô hình session-based CSRF.
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        new org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository()));
```

Đây là mã **minh họa DSL**, không ghép hai đoạn cùng một bean và không mặc định rằng đổi repository là bắt buộc.

### 5.2. `CsrfToken` và request attribute `_csrf`

Spring Security đưa CSRF token vào request attributes cho template engine/rendering, thường dưới tên `_csrf`, với API như:

```java
CsrfToken token = (CsrfToken) request.getAttribute("_csrf");
// token.getParameterName(), token.getHeaderName(), token.getToken()
```

Đoạn này cần `HttpServletRequest request` và import `org.springframework.security.web.csrf.CsrfToken` trong một method Java thực tế. Khi render template, có thể dùng `_csrf.parameterName` và `_csrf.token` để tạo hidden input.

### 5.3. `CsrfTokenRequestHandler` và BREACH masking

Các phiên bản Spring Security 6.x dùng cơ chế **deferred CSRF token** và một `CsrfTokenRequestHandler`; cấu hình mặc định phổ biến sử dụng `XorCsrfTokenRequestAttributeHandler` để che token khi được đưa vào response, giúp giảm nguy cơ **BREACH**.

Điểm cần phân biệt:

- Giá trị token render vào HTML có thể **khác nhau qua những response**, dù expected token bên dưới repository vẫn giống nhau.
- Handler biết cách xử lý giá trị masked token khi request gửi lại.
- Đừng viết test so sánh byte của hai hidden input rồi kết luận CSRF token đã bị rotate hoặc sai.
- Nếu frontend cần đọc **raw CSRF token từ cookie** để gửi bằng custom header, việc phối hợp `CookieCsrfTokenRepository` và request handler phải được cấu hình đúng; không tùy tiện bỏ BREACH protection chỉ để ví dụ JavaScript chạy.

### 5.4. Token được xóa sau authentication và logout

Spring Security dùng `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` để xóa token cũ ở các mốc liên quan. Sau login hoặc logout thành công, đặc biệt với SPA, client có thể cần **lấy CSRF token mới** trước request POST/PUT/PATCH/DELETE tiếp theo.

Điều này lý giải lỗi thường gặp: login API trả thành công nhưng ngay request POST tiếp theo bị 403 vì SPA giữ token cũ đã bị xóa. Cách xử lý là **refresh token từ nguồn tin cậy** sau khi chuyển trạng thái authentication, không tắt CSRF.

## 6. Tạo bài thực hành chạy được với Spring Boot

Ta tạo một ứng dụng Web MVC đơn giản, không sử dụng database hay giao dịch tài chính thật. Nó có:

- `GET /login`: trang đăng nhập custom Thymeleaf, được phép truy cập khi chưa login;
- `POST /login`: Spring Security form login filter tiếp nhận, yêu cầu CSRF;
- `GET /transfer`: trang form nghiệp vụ (chỉ user đã login);
- `POST /transfer`: nhận số lượng điểm giả lập, kiểm authenticated/role + CSRF, tăng **bộ đếm in-memory**;
- `POST /logout`: Spring Security `LogoutFilter` xử lý, yêu cầu CSRF;
- `GET /error`: endpoint lỗi của Boot khi cần.

Mục tiêu của demo là kiểm chứng **một giao dịch mô phỏng không được ghi nhận khi token thiếu hoặc sai**, không thiết kế một hệ thống chuyển tiền thật.

### 6.1. Cấu trúc project

```text
csrf-forms-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/csrf/
    │   │   ├── CsrfFormsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── TransferService.java
    │   │   └── PageController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── login.html
    │           └── transfer.html
    └── test/java/demo/csrf/
        └── CsrfFormsTest.java
```

Cần **JDK 17+** và Maven 3.9+, với parent Spring Boot `3.5.0` để các dependency đồng bộ. Khi triển khai thật, sử dụng bản vá còn được hỗ trợ và kiểm thử tương thích.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>csrf-forms-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 6.3. Main class

`src/main/java/demo/csrf/CsrfFormsApplication.java`:

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormsApplication.class, args);
    }
}
```

### 6.4. SecurityConfig: CSRF luôn được bật

`src/main/java/demo/csrf/SecurityConfig.java`:

```java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/login", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/transfer")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/transfer")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/transfer", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

Giải thích:

1. `GET /login` công khai để người chưa đăng nhập lấy form và CSRF token.
2. `formLogin(...loginPage("/login").permitAll())` để Spring Security xử lý `POST /login` và các URL liên quan đến xác thực, nhưng **không tắt CSRF**. `permitAll` cho phép vào login, không có nghĩa POST login bỏ CSRF.
3. `GET /transfer` yêu cầu xác thực, `POST /transfer` yêu cầu authority `ROLE_USER` và CSRF token.
4. `logout(...)` dùng cơ chế của `LogoutFilter`, không tự viết `@PostMapping("/logout")`. Với CSRF bật, POST logout mới thực hiện cleanup đúng.
5. `anyRequest().denyAll()` giúp đóng các route chưa được phê duyệt. Trong sản phẩm thật cần thêm rule theo nhu cầu cho static assets, endpoints khác, v.v.
6. `csrf(Customizer.withDefaults())` là cấu hình tường minh. Spring Security đã **bật CSRF theo mặc định** cho Servlet web app nếu không vô hiệu hóa.
7. Account `alice` và mật khẩu cố định chỉ dành cho local demo; production cần hệ thống danh tính, hashing và secret management thích hợp.

**Không dùng `csrf.disable()` trong ứng dụng form/session cookie** chỉ để POST nghiệp vụ chạy qua. Khi thiếu CSRF token, lỗi 403 là một dấu hiệu bảo vệ đang hoạt động, không phải lỗi cần "lách".

### 6.5. Service ghi nhận nghiệp vụ mô phỏng

`src/main/java/demo/csrf/TransferService.java`:

```java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class TransferService {

    private final AtomicInteger acceptedRequests = new AtomicInteger();

    public int accept(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        return acceptedRequests.incrementAndGet();
    }

    public int count() {
        return acceptedRequests.get();
    }

    // Chỉ dùng trong bài test.
    public void reset() {
        acceptedRequests.set(0);
    }
}
```

Service này **không chuyển tiền, không chứa dữ liệu khách hàng và không dùng database**. `AtomicInteger` làm bộ đếm quan sát được trong test. Trong hệ thống thật phải có authorization theo đối tượng, validation, transaction, idempotency, audit và chống replay phù hợp; CSRF token chỉ giải quyết một phần của an ninh request.

### 6.6. Controller hiển thị form và nhận nghiệp vụ

`src/main/java/demo/csrf/PageController.java`:

```java
package demo.csrf;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

@Controller
public class PageController {

    private final TransferService service;

    public PageController(TransferService service) {
        this.service = service;
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/transfer")
    public String transferForm() {
        return "transfer";
    }

    @PostMapping("/transfer")
    @ResponseBody
    public Map<String, Object> transfer(
            @RequestParam("amount") int amount,
            Authentication authentication) {

        if (amount <= 0 || amount > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid amount");
        }

        int recordNumber = service.accept(amount);
        return Map.of(
            "status", "accepted",
            "recordNumber", recordNumber,
            "recordedBy", authentication.getName(),
            "amount", amount
        );
    }
}
```

Với một POST hợp lệ, JSON trả về đại loại:

```json
{
  "status": "accepted",
  "recordNumber": 1,
  "recordedBy": "alice",
  "amount": 100
}
```

Đó là **kết quả kỳ vọng khi bộ đếm bắt đầu từ 0**, không phải kết quả được ghi nhận từ một lần chạy server trong bài đọc này. Nếu CSRF token thiếu hoặc sai, controller không nên được gọi và `acceptedRequests` không tăng.

### 6.7. Template đăng nhập

`src/main/resources/templates/login.html`:

```html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
<h1>Đăng nhập</h1>

<p th:if="${param.error}">Tên đăng nhập hoặc mật khẩu không đúng.</p>
<p th:if="${param.logout}">Bạn đã đăng xuất.</p>

<form th:action="@{/login}" method="post">
  <label>Tên đăng nhập
    <input type="text" name="username" autocomplete="username" required>
  </label>
  <label>Mật khẩu
    <input type="password" name="password"
           autocomplete="current-password" required>
  </label>
  <button type="submit">Đăng nhập</button>
</form>
</body>
</html>
```

Với Spring MVC + Thymeleaf có tích hợp `RequestDataValueProcessor`, khi dùng `th:action` cho form POST, Thymeleaf có thể **tự chèn hidden field CSRF** theo cơ chế Spring Security. Không cần thêm **một hidden `_csrf` thứ hai** vào cùng form khi auto-insertion đã hoạt động. Cần kiểm tra HTML render thật trong integration test/browser; không nhìn duy nhất mã template rồi suy ra request không có token.

**Nếu không dùng Thymeleaf hoặc template engine không tự chèn:** render token vào form một cách tường minh, ví dụ:

```html
<!-- Mẫu minh họa cho template không auto-insert CSRF. -->
<form action="/login" method="post">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <input name="username">
  <input name="password" type="password">
  <button type="submit">Đăng nhập</button>
</form>
```

`TOKEN_FROM_SERVER` **chỉ là placeholder mô tả**, không phải mã để deploy: phải lấy giá trị từ `CsrfToken` được framework gắn vào request, như `_csrf.token`, và lấy tên từ `_csrf.parameterName` nếu repository tùy chỉnh. Với context path khác root, tạo action URL bằng URL builder của framework, không hardcode đường dẫn không phù hợp.

### 6.8. Template thao tác nghiệp vụ và đăng xuất

`src/main/resources/templates/transfer.html`:

```html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Giao dịch mô phỏng</title>
</head>
<body>
<h1>Giao dịch điểm mô phỏng</h1>
<p>Ví dụ học tập: không có tiền thật được chuyển.</p>

<form th:action="@{/transfer}" method="post">
  <label>Số điểm
    <input type="number" name="amount" min="1" max="1000"
           value="100" required>
  </label>
  <button type="submit">Gửi thao tác</button>
</form>

<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất</button>
</form>
</body>
</html>
```

Cả **form nghiệp vụ** và **form logout** dùng POST với `th:action`. Trong cấu hình MVC/Thymeleaf chuẩn, cơ chế tự thêm hidden CSRF field áp dụng cho cả hai. Không đổi logout thành:

```html
<!-- KHÔNG nên dùng một GET link như hành động thay đổi trạng thái. -->
<a href="/logout">Đăng xuất ngay</a>
```

Với CSRF bật, `GET /logout` có thể chỉ hiển thị trang xác nhận; dùng POST có token mới biểu thị hành động logout. Một link dẫn đến **trang xác nhận** là khác với link GET trực tiếp thực hiện logout.

### 6.9. Properties cho demo

`src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
spring.thymeleaf.cache=false
```

Trên production dùng **HTTPS** và cookie **Secure**:

```properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`Secure`, `HttpOnly` và `SameSite` có tác dụng giảm rủi ro riêng; **không thay thế CSRF token** khi ứng dụng nhận browser credentials được gửi tự động. Demo local dùng HTTP để dễ thử, không áp dụng lựa chọn này cho production.

## 7. Bộ test kiểm tra chính xác ba nhóm form

Tạo `src/test/java/demo/csrf/CsrfFormsTest.java`:

```java
package demo.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormsTest {

    @Autowired MockMvc mvc;
    @Autowired TransferService service;

    @BeforeEach
    void reset() {
        service.reset();
    }

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(
                formLogin().user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void loginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-demo"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithValidCsrfCreatesAuthenticatedSession()
            throws Exception {
        MockHttpSession session = login();
        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void businessPostWithoutCsrfIsRejectedBeforeService()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .param("amount", "100"))
            .andExpect(status().isForbidden());

        assertThat(service.count()).isZero();
    }

    @Test
    void businessPostWithInvalidCsrfDoesNotMutate()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .with(csrf().useInvalidToken())
                .param("amount", "100"))
            .andExpect(status().isForbidden());

        assertThat(service.count()).isZero();
    }

    @Test
    void businessPostWithValidCsrfSucceeds() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .with(csrf())
                .param("amount", "100"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.recordedBy").value("alice"))
            .andExpect(jsonPath("$.recordNumber").value(1));

        assertThat(service.count()).isEqualTo(1);
    }

    @Test
    void businessPostWithCsrfButWithoutLoginCannotMutate()
            throws Exception {
        mvc.perform(post("/transfer")
                .with(csrf())
                .param("amount", "100"))
            .andExpect(status().is3xxRedirection());

        assertThat(service.count()).isZero();
    }

    @Test
    void getFormIsReadOnly() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());

        assertThat(service.count()).isZero();
    }

    @Test
    void logoutWithoutCsrfCannotEndSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void logoutWithCsrfInvalidatesCurrentSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertThat(session.isInvalid()).isTrue();

        // Session cũ đã invalid nên KHÔNG truyền lại nó vào MockMvc.
        mvc.perform(get("/transfer"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginFormRenders() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }
}
```

**Những điều bộ test chứng minh:**

- `POST /login` không token bị **403**, còn `formLogin()` của Spring Security Test tự gửi CSRF token hợp lệ và xác thực thành công.
- `POST /transfer` thiếu token hoặc token sai bị **403**. Quan trọng hơn, `service.count()` vẫn là **0**: thao tác không có side effect.
- Token hợp lệ **nhưng chưa authenticated** vẫn không được phép thực thi nghiệp vụ. Đây là minh chứng CSRF **không thay thế authentication**.
- Token hợp lệ, user hợp lệ và rule quyền hợp lệ mới được ghi nhận.
- `GET /transfer` không gây side effect.
- `POST /logout` thiếu token không hủy session; POST có token hủy session và chuyển đến login, không cần viết controller logout.
- Test dùng `MockHttpSession` thực do form login tạo, không chỉ dùng `@WithMockUser` để đặt một danh tính giả vào request mà bỏ qua vòng đời login/session.

Khi cần kiểm tra Thymeleaf tự chèn token, có thể mở HTML response từ `GET /login` và `GET /transfer`, kiểm tra các form POST có hidden parameter `_csrf` hoặc tên cấu hình tương đương. Test đầu-cuối bằng browser thật còn kiểm được Path/SameSite/cookie và token được gửi qua browser.

### 7.1. Chạy test và server

```bash
mvn test
mvn spring-boot:run
```

Khi chạy thành công, class trên có **10 phương thức `@Test`**, kết quả dự kiến tất cả pass với đúng cấu hình của ví dụ. Đây là **kỳ vọng sau phân tích mã**, không phải log Maven đã thực thi trong bài đọc này.

### 7.2. Trình tự thử thủ công

1. Mở `http://localhost:8080/login` trên browser; quan sát HTML form được render với hidden CSRF token.
2. Đăng nhập bằng `alice` / `alice-demo`; browser được đưa đến `/transfer`.
3. Điền số điểm `100`, submit form; response JSON `status=accepted` và bộ đếm tăng.
4. Tạo một request POST thủ công **trong môi trường local được phép** nhưng bỏ token; kỳ vọng 403, bộ đếm không tăng.
5. Mở `/transfer` lại, submit form logout; browser nhận redirect `/login?logout` và session hiện tại bị invalidate.
6. Thử truy cập `/transfer` khi chưa xác thực; phải được chuyển đến login.

**Đừng chỉ dùng `curl -X POST` không cookie/token rồi kết luận CSRF đang chặn user đã login.** Cần giữ cùng cookie jar, dùng CSRF token từ server, và so sánh response/side effect. Khi chạy với custom domain/reverse proxy, phải kiểm cả Path/Domain/SameSite/Secure để bảo đảm browser thật gửi token và cookie đúng.

## 8. Debug lỗi 403: CSRF hay authorization?

Một error `403 Forbidden` không nói rõ tại sao request bị từ chối. Hãy kiểm tra có hệ thống:

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| `POST /login` trả 403 dù đúng mật khẩu | Thiếu/sai CSRF token | GET trang login, xem hidden CSRF field, test `with(csrf())` |
| `POST /transfer` trả 403 khi user đã login | Token sai, thiếu hoặc role không đủ | Test riêng có/không CSRF và có/không role |
| POST thành công bằng Postman nhưng form browser lỗi | Postman có header/token khác, cookie path hoặc session khác | So sánh chính xác cookie jar, token và content type |
| Form mở lâu, submit sau 30 phút bị 403 | Session/expected token hết hạn | Tải lại form/token, thiết kế xử lý timeout |
| SPA đăng nhập xong POST tiếp bị 403 | Token cũ bị dọn sau authentication success | Lấy CSRF token mới sau login |
| Logout hợp lệ rồi POST ở SPA bị 403 | Token cũ bị xóa sau logout | Refresh CSRF token theo flow sau logout |
| GET thực hiện ghi dữ liệu dù CSRF bật | GET không bị CSRF filter mặc định chặn | Sửa HTTP contract: dùng POST/PATCH/DELETE |
| POST bị 403 khi có token hợp lệ | Security role/permission hoặc rule filter khác | Kiểm authority, CSRF strategy, method security |
| Tắt CSRF thì POST hoạt động | Token integration sai, **không có nghĩa nên tắt CSRF** | Sửa form/template/client, giữ bảo vệ |
| API POST dùng Bearer header vẫn bị CSRF | Một filter chain vẫn áp CSRF hoặc API dùng cookie | Phân tích kiến trúc; chỉnh matcher có phạm vi nếu thật sự an toàn |

Trong test, nên phân biệt:

- `csrf().useInvalidToken()`: gửi token giả để xác nhận bị từ chối;
- `csrf().asHeader()`: gửi token hợp lệ qua header thay vì form parameter, phù hợp AJAX;
- Không dùng `with(csrf())`: kiểm thử tình huống thiếu token;
- `with(user(...))` hoặc `@WithMockUser`: mock authentication, nhưng không thay thế test form login/session thật.

## 9. Login, logout và thay đổi CSRF token ở SPA

Ứng dụng SPA thường gọi JSON endpoint và gửi session cookie bằng `fetch`:

```javascript
// Đoạn minh họa; csrfToken phải lấy từ backend đáng tin cậy.
await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});
```

Điểm cần nhớ:

1. Browser có thể **tự gửi session cookie** theo credentials policy; việc body là JSON không loại bỏ CSRF một cách tuyệt đối.
2. CSRF token phải được lấy từ server, không tự tạo random string trên client rồi gửi với hy vọng server chấp nhận.
3. Spring Security có thể nhận token từ parameter `_csrf` hoặc header phù hợp (chẳng hạn `X-CSRF-TOKEN`/`X-XSRF-TOKEN` tùy cấu hình handler/repository).
4. Cần lấy token sau khi ứng dụng khởi tạo, **sau login thành công** và **sau logout thành công** khi token cũ đã bị xóa.
5. Tránh đưa token vào URL/query string vì có thể rò rỉ qua history, referrer, proxy hoặc log.
6. Nếu dùng CORS, cấu hình nguồn được phép rõ ràng; **CORS không phải CSRF protection**.

### 9.1. Endpoint `/csrf` khi frontend cần token

Spring Security hướng dẫn một cách tích hợp là cung cấp endpoint để client chủ động nhận token:

```java
// Phương thức minh họa: đặt trong @RestController của app thật.
@GetMapping("/csrf")
public org.springframework.security.web.csrf.CsrfToken csrf(
        org.springframework.security.web.csrf.CsrfToken csrfToken) {
    return csrfToken;
}
```

Đoạn này **không thuộc demo runnable ở mục 6**, chỉ là hướng triển khai cho SPA/mobile; cần thêm rule `permitAll` nếu frontend phải gọi trước login, kiểm soát CORS/cache và xử lý BREACH masking/cookie repository đúng. Sau login/logout, frontend gọi lại endpoint để lấy token mới.

Đừng cho rằng endpoint `/csrf` tự “cấp quyền truy cập API”: nó chỉ giúp client lấy CSRF token. Authorization của mọi POST/PUT/PATCH/DELETE vẫn bắt buộc dựa trên principal và chính sách nghiệp vụ.

### 9.2. `CookieCsrfTokenRepository` có dùng được không?

Nếu frontend JavaScript cần đọc token từ một cookie như `XSRF-TOKEN` và phản hồi vào header `X-XSRF-TOKEN`, Spring Security có `CookieCsrfTokenRepository`. Khi JavaScript phải đọc cookie CSRF, có thể cấu hình cookie CSRF **không HttpOnly** *cho riêng cookie đó*, trong khi **session/authentication cookie vẫn phải HttpOnly**.

Tuy nhiên:

- Cần xét đúng `CsrfTokenRequestHandler` vì BREACH masking/deferred tokens trong Spring Security 6.x có thể khiến cách đọc token từ cookie và cách so sánh request cần điều chỉnh.
- Cần kiểm soát phạm vi cookie, SameSite, Secure, Path/Domain và nguồn JavaScript tin cậy.
- Không coi việc token nằm trong cookie đồng nghĩa đã chống CSRF; client phải gửi lại token trong **header/parameter chủ động**, không chỉ dựa vào browser tự đính kèm cookie.
- Phải đánh giá rủi ro subdomain cookie injection và trường hợp attacker có thể tác động vào cookie; token pattern và browser restrictions cần được thiết kế đồng bộ.
- Trong ứng dụng không cần JavaScript đọc token, dùng session repository mặc định thường đơn giản hơn.

**Không dùng `withHttpOnlyFalse()` cho JSESSIONID** chỉ vì một ví dụ SPA cần đọc CSRF cookie. Đây là hai cookie có mục đích khác nhau.

## 10. Khi nào không cần CSRF, và khi nào bắt buộc đánh giá kỹ?

### 10.1. Session cookie và form login: nên giữ CSRF

Nếu website dùng `JSESSIONID` hoặc `SESSION` được browser gửi tự động, login/logout và nghiệp vụ dùng POST phải có CSRF protection. `SessionCreationPolicy.STATELESS` tự nó **không** chứng minh an toàn nếu ứng dụng vẫn dùng một cookie tự động gửi hoặc HTTP Basic trong browser.

### 10.2. API chỉ nhận Bearer token do client chủ động gắn

Một API dành riêng cho service-to-service hoặc client không dùng browser có thể không cần CSRF nếu:

- Không dùng session/credential mà browser tự gửi trong các request tấn công;
- Mỗi request yêu cầu Bearer token qua `Authorization` header do client hợp lệ chủ động đặt;
- Không có fallback cookie/HTTP Basic trên cùng route;
- Không cho một website lạ tự lấy access token hoặc chèn header đã được cho phép mà không có authorization hợp lệ.

Ngay cả khi bỏ CSRF trong trường hợp này, API vẫn phải kiểm token, scopes, audience, authorization theo object và rate limit thích hợp.

### 10.3. Đừng tắt CSRF toàn cục cho ứng dụng hỗn hợp

Cấu hình dưới đây dễ trở thành lỗ hổng:

```java
// VÍ DỤ KHÔNG AN TOÀN với app form login/cookie auth.
http.csrf(csrf -> csrf.disable());
```

Nếu hệ thống vừa có web forms dựa trên cookie vừa có API stateless Bearer, hãy phân tích theo **SecurityFilterChain**, **securityMatcher** và cơ chế credentials của từng vùng, rồi chỉ miễn CSRF ở endpoints thật sự không chịu rủi ro. Một request bị bỏ qua vì `csrf.ignoringRequestMatchers("/api/**")` có thể trở thành lỗ hổng nếu sau này một endpoint cookie-auth được thêm vào namespace ấy.

`permitAll()` **không** đồng nghĩa bỏ CSRF. Login page public về authorization nhưng POST login vẫn cần token. Similarly, CSRF token hợp lệ **không** tự cấp role để gọi endpoint admin.

## 11. SameSite, CORS, Origin và Fetch Metadata

### 11.1. SameSite là lớp phụ trợ

Cookie `SameSite=Lax` hoặc `SameSite=Strict` hạn chế nhiều kịch bản cross-site gửi cookie. Tuy nhiên:

- Browser có khác biệt và các ngoại lệ theo cơ chế điều hướng;
- SameSite dựa trên **site**, không đồng nghĩa với **origin**; các subdomain có thể cùng site nhưng khác origin;
- Bỏ SameSite không đúng khi tích hợp SSO/third-party có thể làm request thất bại, nhưng bật Lax không chứng minh mọi nghiệp vụ miễn nhiễm CSRF;
- `SameSite=None` cần `Secure` trong browser hiện đại; cookie phiên phải dùng HTTPS.

Vì vậy xem SameSite là **defense in depth**, không mặc định bỏ CSRF token cho session browser.

### 11.2. CORS không chặn mọi form submissions

CORS kiểm soát việc script cross-origin có thể truy cập response và các trường hợp preflight; một HTML form đơn giản thường có thể gửi request cross-origin mà không cần JavaScript đọc response. Do đó bật CORS hạn chế **không thay thế** token CSRF. Nếu SPA dùng header `X-CSRF-TOKEN`, preflight/CORS là lớp kiểm soát khác, vẫn cần kiểm token.

### 11.3. Origin/Referer/Fetch Metadata

Kiểm tra `Origin`, `Referer` hoặc `Sec-Fetch-Site` có thể giúp phát hiện request đáng ngờ và làm lớp bảo vệ bổ sung khi được triển khai đúng. Nhưng header không có trong mọi client/cách điều hướng, có proxy và browser policies khác nhau. Đừng tự viết một kiểm tra `Origin` mong manh rồi bỏ `CsrfFilter`, đặc biệt với form/session truyền thống.

### 11.4. HTTPS và XSS

HTTPS bảo vệ credential/token trên đường truyền, nhưng không phân biệt request do nạn nhân chủ động với request do website khác kích hoạt. XSS trong same origin có thể phá vỡ nhiều giả định về CSRF token; bảo vệ output encoding, CSP, dependency và template vẫn bắt buộc.

## 12. Multipart, file upload và method override

### 12.1. File upload

Một form upload là POST:

```html
<form action="/files" method="post" enctype="multipart/form-data">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <input type="file" name="file">
  <button type="submit">Tải lên</button>
</form>
```

Đây là **template minh họa**, không dùng placeholder tĩnh trong thực tế. Khi form/JS tải file, bảo đảm CSRF token được gửi cùng request. Có sự đánh đổi về thứ tự `MultipartFilter` và security filter: nếu xử lý multipart trước CSRF, hệ thống có thể tạo file tạm trước khi xác thực token. Với JavaScript, gửi CSRF token qua header thường giúp tránh một số phức tạp này. Vẫn cần giới hạn dung lượng, loại file, quyền upload và an toàn lưu trữ.

### 12.2. `HiddenHttpMethodFilter`

Nếu form HTML gửi POST có field `_method=DELETE` để mô phỏng DELETE, cần kiểm tra vị trí các filter để Spring Security thấy method hiệu lực phù hợp. Đừng giả định method override luôn được áp dụng hoặc luôn an toàn; khi thiết kế API mới, test cả routing và CSRF cho các method được hỗ trợ.

### 12.3. Các POST "trông như đọc" nhưng thực chất có side effect

Tạo report, kích hoạt batch, xác nhận email, cập nhật lựa chọn, đổi password, reset MFA, bấm nút mời thành viên, đăng ký webhook, đánh dấu “đã xem”, gửi thông báo… có thể thay đổi trạng thái dù response chỉ là 204 hoặc một download link. Cần đánh giá CSRF theo **tác dụng**, không theo tên method trong controller hay việc response là JSON.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Điều xảy ra | Sửa đúng |
| --- | --- | --- |
| Chỉ bảo vệ form chuyển tiền, bỏ qua `POST /login` | Login CSRF gắn nạn nhân vào tài khoản attacker | Giữ CSRF cho login POST |
| Dùng `GET /logout` để thực sự hủy session | Logout CSRF qua navigation/image/link | Dùng POST logout với token |
| Dùng `GET /delete` vì thao tác “nhanh” | CSRF mặc định không chặn GET | Đổi sang method unsafe và token |
| Login form thiếu hidden token do custom template | Đúng mật khẩu vẫn bị 403 | Tích hợp token bằng Thymeleaf/RequestDataValueProcessor |
| Thêm hai hidden field `_csrf` do framework auto-insert + thủ công | Request/đọc parameter có thể khó đoán | Chọn một cơ chế phát token phù hợp và kiểm HTML render |
| SPA giữ token cũ sau login/logout | POST tiếp theo bị 403 | Lấy CSRF token mới sau thay đổi authentication |
| Session timeout nhưng tab form mở lâu | Expected token không còn | Render lỗi rõ, refresh form và token; không tắt CSRF |
| Chỉ test status 403 | Không biết filter nào từ chối hoặc có side effect không | Assert service/DB không bị thay đổi |
| Dùng `@WithMockUser` cho mọi test login | Không test luồng thật `POST /login` | Dùng `formLogin()` để kiểm integration |
| Cho phép POST khi có token nhưng chưa login | Token CSRF bị hiểu thành authentication | Kiểm login, role, quyền đối tượng riêng |
| Tắt CSRF khi API trả JSON | Browser vẫn có thể tự gửi cookie auth | Đánh giá credentials; giữ CSRF nếu cookie-based |
| Nhầm CORS với CSRF | HTML form cross-origin vẫn có thể tạo request | Dùng CSRF token/other proven defenses |
| Nhầm `SameSite=Lax` là đủ | Có trường hợp cùng site khác origin hoặc policy khác | Defense-in-depth + CSRF token |
| Dùng token trong URL | Có thể lộ qua log/referrer/history | Gửi hidden form field hoặc header |
| Tắt toàn bộ `csrf` để test pass | Bỏ lớp kiểm soát nguy cơ thật | Dùng `csrf()` của Spring Security Test |
| Tự tạo CSRF token trên frontend | Server không thể xác minh token tùy ý | Lấy token qua request từ backend |
| Để session cookie không HttpOnly vì cần đọc CSRF | Dễ lộ credential khi có XSS | Tách session cookie và CSRF cookie/endpoint |
| Dùng random UUID làm “token” nhưng không liên kết session | Dễ tạo/làm sai tương quan và validation | Dùng CsrfTokenRepository chuẩn |
| Mở một matcher ignore diện rộng | Endpoint mới có cookie-auth bị bỏ bảo vệ | Thu hẹp exemption và viết regression test |
| Chỉ bảo vệ form nhưng API khác cùng nghiệp vụ không bảo vệ | Kẻ tấn công gọi alternate endpoint | Test tất cả entry points/action |
| Dùng HTTP trong production | Token và cookie có nguy cơ bị lộ | HTTPS, Secure cookie, redaction log |
| Nghĩ CSRF token ngăn XSS | XSS có thể dùng token cùng origin | Bảo vệ XSS/CSP/output encoding riêng |

## 14. Ma trận kiểm thử cho một ứng dụng thực

| Ca test | Kỳ vọng chính |
| --- | --- |
| Anonymous GET login page | 200, form có CSRF token hợp lệ |
| POST login thiếu token | 403, chưa tạo authentication |
| POST login token sai | 403, chưa đăng nhập |
| POST login token đúng + password đúng | Login thành công, có session/Authentication |
| POST login token đúng + password sai | Login thất bại, không tạo authentication hợp lệ |
| Anonymous POST nghiệp vụ + token đúng | Không thực thi, redirect login/401 tùy flow |
| Authenticated POST nghiệp vụ không token | 403, DB/service unchanged |
| Authenticated POST nghiệp vụ token sai | 403, DB/service unchanged |
| Authenticated POST nghiệp vụ token đúng + thiếu role | 403, DB/service unchanged |
| Authenticated POST nghiệp vụ token đúng + đủ role | Chỉ thực thi thao tác được phép |
| GET trang nghiệp vụ | Đọc/hiển thị, không thay đổi trạng thái |
| POST logout thiếu token | 403, session vẫn hợp lệ |
| POST logout token đúng | Logout thành công, session bị invalidate |
| Token CSRF dùng trước login rồi giữ sau login | Cần token mới theo flow của phiên bản |
| Session timeout rồi submit form cũ | Không thực thi; thông báo cần tải lại trang |
| POST qua AJAX gửi header hợp lệ | Thành công nếu đủ authentication/role |
| POST AJAX không header/không field | 403, không side effect |
| Multipart upload thiếu token | Không xử lý upload nghiệp vụ |
| CORS preflight OPTIONS | Hoạt động theo CORS policy, không cấp quyền POST |
| POST khác không có handler nhưng cookie auth | Không vô tình được permit bởi rule ignore rộng |
| Browser có cookie `SameSite=Lax` | Token vẫn cần trong chính sách session-based |
| API Bearer-only không dùng cookie | Có thể miễn CSRF khi đánh giá đúng threat model |
| Proxy/chuyển domain/path | Cookie, session và token hoạt động đúng scope |

Trong test automation, ưu tiên những bất biến bảo mật: **không có side effect nếu CSRF thiếu/sai**, **có side effect đúng khi CSRF + quyền hợp lệ**, **login và logout không thể bị ép bằng POST không token**, và **GET không gây mutation**.

## 15. Checklist dùng khi code review

- [ ] Xác định cơ chế authentication: session cookie, Basic trong browser, custom cookie, Bearer header hay nhiều loại kết hợp.
- [ ] Giữ CSRF bật cho mọi form browser unsafe, bao gồm **login** và **logout**.
- [ ] Dùng HTTP safe methods chỉ để đọc; không thực hiện thay đổi trạng thái bằng GET.
- [ ] Dùng token do Spring Security cấp, không hardcode hoặc frontend tự chế.
- [ ] Render hidden token trong form HTML; xác minh khi template engine tự chèn token.
- [ ] Với SPA, gửi token qua header có chủ ý và lấy token mới sau login/logout.
- [ ] Kiểm tra token repository/handler khi đổi sang `CookieCsrfTokenRepository`.
- [ ] Dùng logout POST có CSRF, không buộc GET thành hành động logout.
- [ ] Không bỏ authorization theo role/owner/tenant chỉ vì request có CSRF token đúng.
- [ ] Kiểm tra riêng lỗi thiếu token và lỗi thiếu quyền; ghi nhận reason trong logging nội bộ mà không lộ token.
- [ ] Không đưa token hoặc cookie vào URL, telemetry, bug report hoặc client-side log.
- [ ] Định nghĩa hành vi session timeout / form cũ; hiển thị hướng dẫn refresh thay vì tắt CSRF.
- [ ] Với multipart/HTTP method override, test đúng filter ordering và đường đi server thật.
- [ ] Không miễn CSRF bằng matcher rộng cho vùng API có cookie auth hoặc thay đổi theo thời gian.
- [ ] Test token đúng, sai, thiếu, hết hạn sau login/logout và **zero side effect** khi request bị từ chối.
- [ ] Áp HTTPS, Secure/HttpOnly/SameSite và phòng chống XSS, CORS/Origin policy phù hợp.
- [ ] Với endpoint public có tác dụng thay đổi trạng thái, vẫn phân tích CSRF/abuse mặc dù không cần login.

## 16. Câu hỏi tự kiểm tra

**1. Tại sao `POST /login` cũng cần CSRF khi người dùng chưa được xác thực?**  
Vì login CSRF có thể khiến browser của nạn nhân đăng nhập vào tài khoản attacker và lưu dữ liệu sau đó vào tài khoản ấy; token được cấp trong session trước đăng nhập.

**2. Tại sao `GET /logout` không nên trực tiếp logout?**  
Vì GET có thể được kích hoạt ngoài ý muốn bởi link hoặc nội dung từ website khác; logout thay đổi trạng thái và cần POST/token.

**3. Tại sao Spring Security thường chặn POST nhưng không chặn GET bằng CSRF token?**  
Vì safe methods được giả định không thay đổi trạng thái. Nếu GET thực hiện ghi dữ liệu, phải sửa thiết kế HTTP, không dựa vào CSRF filter mặc định.

**4. CSRF token đúng có đủ quyền chuyển tiền không?**  
Không. Nó chứng minh một điều kiện về nguồn/tính chủ động của request, không xác nhận Authentication, role hay quyền trên resource cụ thể.

**5. Vì sao POST sai token phải assert bộ đếm/DB không đổi?**  
Vì response 403 có thể xuất hiện từ nhiều filter, và test security phải chứng minh nghiệp vụ nhạy cảm không chạy khi request bị từ chối.

**6. Spring Security mặc định lưu CSRF token ở đâu trong Servlet app?**  
Thường trong HttpSession qua `HttpSessionCsrfTokenRepository`. Có thể cấu hình repository khác theo kiến trúc.

**7. Vì sao giá trị hidden CSRF token trên hai lần GET có thể khác nhau?**  
Do cơ chế XOR masking/BREACH protection; không nhất thiết expected token trong repository đã thay đổi.

**8. Vì sao SPA phải lấy token mới sau login/logout?**  
Vì các chiến lược authentication/logout có thể dọn token cũ, khiến token client đang giữ không còn phù hợp.

**9. Có được tắt CSRF chỉ vì request JSON không?**  
Không. Phải xét có credential được browser tự gửi không, các endpoint chấp nhận content type gì và nguy cơ cross-origin. JSON không tự bảo đảm an toàn.

**10. CORS và SameSite có thay CSRF token được không?**  
Không mặc nhiên. CORS tập trung vào khả năng script cross-origin truy cập response; SameSite là lớp hạn chế cookie có các điều kiện/ngoại lệ riêng.

**11. Nếu API stateless dùng Bearer token chỉ qua Authorization header, không có cookie, CSRF có thể không cần không?**  
Có thể, sau khi đánh giá threat model và bảo đảm browser không tự thêm credential/chấp nhận fallback khác; authentication/authorization vẫn phải nghiêm ngặt.

**12. Tại sao một `csrf().ignoringRequestMatchers("/api/**")` rộng nguy hiểm với ứng dụng kết hợp?**  
Vì endpoint API mới có thể dùng session cookie mà vô tình không còn CSRF protection; miễn trừ phải hẹp, có review và regression test.

## 17. Tài liệu tham khảo

- [Spring Security — Cross Site Request Forgery (CSRF), Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): cơ chế token, repository/handler, BREACH, form/SPA, login/logout, timeout và cấu hình.
- [Spring Security — CSRF Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()`, `useInvalidToken()`.
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` tự thêm token và thực hiện flow authentication.
- [Spring Security — Testing Logout](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html): logout request builder với CSRF.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, CSRF và dọn session/context.
- [Spring Security — CSRF: Security Features](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): method an toàn, đồng bộ token, SameSite và nguyên tắc browser.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, synchronizer token, signed double-submit cookie và defense-in-depth.
