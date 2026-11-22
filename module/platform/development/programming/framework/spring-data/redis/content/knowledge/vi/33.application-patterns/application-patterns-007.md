# Quản lý phiên đăng nhập với Spring Session và ranh giới tích hợp

Trong ứng dụng web Java, **phiên đăng nhập (login session)** giúp server nhớ người dùng đã xác thực qua nhiều HTTP request. Nếu chỉ sử dụng phiên HTTP lưu trong bộ nhớ của một instance ứng dụng, việc tăng số replica, khởi động lại instance hoặc điều phối request qua load balancer có thể khiến người dùng mất trạng thái đăng nhập.

**Spring Session** giải quyết một phần quan trọng của bài toán này bằng cách thay nơi lưu phiên mặc định của servlet container bằng một `SessionRepository` dùng chung. Khi sử dụng **Spring Session Data Redis**, nhiều instance ứng dụng có thể đọc, cập nhật và vô hiệu hóa phiên qua Redis; browser chỉ giữ một session ID trong cookie.

Tuy nhiên, việc đặt session vào Redis không tự tạo hệ thống xác thực hoàn chỉnh. Cần phân biệt rõ:

- **Spring Security** quyết định danh tính, quyền truy cập, quy trình login/logout, chống session fixation và quản lý `SecurityContext`.
- **Spring Session** quản lý vòng đời và lưu trữ phiên HTTP phía server thông qua repository, TTL và session ID.
- **Redis** là nơi lưu dữ liệu phiên dùng chung, có những đặc điểm về timeout, replication, persistence, memory và failover.
- **Cookie trên browser** mang session ID, không nên chứa mật khẩu, thông tin quyền nhạy cảm hoặc toàn bộ nội dung phiên.
- **Database/identity provider** vẫn là nguồn sự thật về tài khoản, trạng thái khóa, mật khẩu, vai trò và các quyết định bảo mật cần kiểm tra lại.

Bài học triển khai một mẫu ứng dụng **Spring MVC (Servlet) + Spring Security + Spring Session Data Redis**, sau đó đi sâu vào ranh giới tích hợp với WebFlux, Redis Cluster, token, transaction, serialization và vận hành production.

## 1. Tại sao cần đưa phiên đăng nhập ra khỏi memory của ứng dụng?

Giả sử một hệ thống có ba instance chạy sau load balancer:

```text
                     Browser
                        |
                 Cookie: SESSION=abc
                        |
                  Load Balancer
                        |
              +---------+---------+
              |         |         |
              v         v         v
           App A      App B      App C
          Session A  Session B  Session C
          (local)    (local)    (local)
```

Nếu người dùng login qua App A nhưng request kế tiếp được gửi tới App B, App B có thể không biết session vừa tạo ở A. Một số hạ tầng giải quyết tạm bằng **sticky sessions**: giữ request của browser trên cùng instance. Cách này có hạn chế:

- Instance chết hoặc được deploy lại có thể làm mất session.
- Tăng/giảm replica và cân bằng tải phức tạp hơn.
- Dữ liệu session sống trong memory instance nên khó vô hiệu hóa trên nhiều replica.
- Không có kho chung để quản trị vòng đời session.

Đưa session vào Redis:

```text
                        Browser
                           |
                   Cookie: SESSION=abc
                           |
                     Load Balancer
                           |
                 +---------+---------+
                 |         |         |
                 v         v         v
               App A     App B     App C
                 |         |         |
                 +---------+---------+
                           |
                           v
                       Redis
                Session id = abc
                SecurityContext
                lastAccessedTime
                maxInactiveInterval
                attributes
```

Mỗi instance nhận cùng một session ID và truy vấn repository dùng chung. Khi các instance có **cùng cấu hình namespace, serializer, Spring Session/Security tương thích** và cùng cụm Redis phù hợp, người dùng có thể tiếp tục phiên dù request được chuyển sang instance khác.

**Redis ở đây là shared session store**, không phải một bản sao cookie gửi tới tất cả server. Browser vẫn chỉ lưu session identifier; ứng dụng đọc dữ liệu session phía Redis.

## 2. Spring Session thay thế cơ chế HttpSession mặc định thế nào?

Ở tầng Servlet, Spring Session có một filter tích hợp để đưa `HttpSession` của ứng dụng qua một `SessionRepository`.

```text
HTTP Request
     |
     v
SessionRepositoryFilter
     |
     +-- Đọc session ID từ cookie
     |
     +-- Tra SessionRepository trong Redis
     |
     +-- Bọc HttpServletRequest/Response
     |   với HttpSession được Spring Session quản lý
     |
     v
Spring Security Filter Chain
     |
     +-- Đọc/ghi SecurityContext nếu sử dụng session
     |
     v
Controller / Service
     |
     +-- request.getSession()
     +-- session.setAttribute(...)
     |
     v
SessionRepositoryFilter lưu thay đổi theo chế độ cấu hình
     |
     v
HTTP Response với cookie nếu cần
```

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `HttpSession` | API phiên HTTP quen thuộc của Servlet |
| `SessionRepository<S extends Session>` | Hợp đồng tạo, tìm, lưu và xóa session |
| `RedisSessionRepository` | Triển khai lưu session vào Redis không yêu cầu các tính năng index nâng cao |
| `RedisIndexedSessionRepository` | Triển khai có khả năng index/tra cứu phiên theo thuộc tính như principal trong những cấu hình phù hợp |
| `SessionRepositoryFilter` | Kết nối HttpSession với SessionRepository ở tầng filter |
| `HttpSessionIdResolver` | Quy định cách lấy/trả session ID, thường qua cookie |
| `CookieSerializer` | Điều chỉnh tên, path, domain và thuộc tính cookie |
| `SecurityContext` | Thông tin xác thực do Spring Security quản lý |
| Redis | Lưu dữ liệu session theo các cấu trúc, key và TTL của implementation |

Spring Session không thay thế `UserDetailsService`, OAuth2/OIDC provider hoặc `AuthenticationManager`. Nó lưu phiên do ứng dụng và security filter sử dụng, không tự kiểm tra mật khẩu hay cấp quyền.

### 2.1. Có session không có nghĩa người dùng đã đăng nhập

Một ứng dụng có thể tạo `HttpSession` trước khi người dùng đăng nhập, ví dụ để giữ CSRF token hoặc lựa chọn giao diện. Vì vậy:

```java
HttpSession session = request.getSession(false);
boolean hasSession = session != null;
```

chỉ trả lời **request có session hiện hành hay không**, không xác định người dùng đã authenticated hay chưa.

Để xác định đăng nhập, sử dụng cơ chế Spring Security như `Authentication` hoặc `SecurityContextHolder` trong ranh giới request thích hợp, và kiểm tra trạng thái xác thực theo chính sách của ứng dụng.

### 2.2. Spring Session và HttpSession theo mô hình nào?

Trong phần ví dụ chính của bài, ta dùng **Spring MVC / Servlet**. Nếu ứng dụng là **Spring WebFlux reactive**, API phiên là `WebSession` và repository/filter reactive tương ứng. Không trộn `HttpSession` Servlet với `WebSession` WebFlux như thể chúng là cùng một interface.

Điều này ảnh hưởng cách lấy principal, cách xử lý context, chỗ cấu hình security và cơ chế lưu Redis.

## 3. Dependency cho ứng dụng Spring Boot

Ví dụ ứng dụng Spring Boot chạy Spring MVC, Spring Security và Spring Session Redis với các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
```

Trong một số hệ sinh thái/phiên bản, tên starter hoặc dependency management có thể thay đổi. Điều quan trọng là thư viện Spring Session Redis, Spring Security, Spring Data Redis và driver được phiên bản Spring Boot đang dùng quản lý tương thích.

Thông thường, Spring Boot có thể tự cấu hình cơ chế Spring Session Redis khi dependency và Redis connection được thiết lập đúng. Không nên vừa bật auto-configuration vừa tự tạo nhiều repository/filter bean trùng nhau nếu chưa xác định rõ vai trò.

### Cấu hình cơ bản trong application.yml

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s

  session:
    store-type: redis
    redis:
      namespace: myapp:session

server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Ý nghĩa:

- `spring.data.redis.*`: kết nối tới Redis.
- `spring.session.store-type: redis`: chỉ định kho session Redis trong những phiên bản Spring Boot hỗ trợ property này.
- `spring.session.redis.namespace`: tách không gian key của session khỏi ứng dụng khác.
- `server.servlet.session.timeout`: thời gian không hoạt động tối đa của session trong cấu hình Servlet thông thường.
- `http-only: true`: giảm nguy cơ JavaScript trực tiếp đọc cookie.
- `secure: true`: chỉ gửi cookie qua HTTPS; khi chạy HTTP localhost đơn thuần cần môi trường thử nghiệm thích hợp.
- `same-site: lax`: một lớp giảm thiểu CSRF trong nhiều luồng browser nhưng không thay thế CSRF protection.

**Phân biệt môi trường:** Ví dụ `secure: true` dành cho request đi qua HTTPS. Nếu phát triển trên HTTP localhost, browser có thể không gửi cookie như mong đợi tùy điều kiện và chính sách browser. Trong production, dùng HTTPS từ browser tới điểm kết thúc TLS và kiểm soát trusted reverse proxy/forwarded headers chính xác.

### Kiểm tra version/property

Properties của Spring Boot và cách Spring Session tự cấu hình có thể khác theo phiên bản. Khi nâng cấp, cần kiểm tra **configuration metadata và reference guide của chính phiên bản đang chạy**; không chép một property từ ví dụ cũ rồi mặc định nó còn tác dụng.

Không nên kiểm tra thành công bằng việc “application khởi động được” duy nhất. Phải thử đăng nhập qua hai instance, đổi routing và kiểm tra session còn hợp lệ.

## 4. Mẫu ứng dụng: đăng nhập và giữ trạng thái qua Redis

Một mẫu ứng dụng nhỏ có thể gồm:

```text
src/main/java/com/example/sessiondemo/
    SessionDemoApplication.java
    SecurityConfiguration.java
    UserPreferencesController.java

src/main/resources/
    application.yml
```

Giả định ứng dụng đã có cơ chế định danh người dùng phù hợp, chẳng hạn một `UserDetailsService` hoặc authentication provider được cấu hình riêng. Các ví dụ bên dưới không hardcode username/password production.

### 4.1. Cấu hình Spring Security theo session

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .deleteCookies("SESSION"));

        return http.build();
    }
}
```

Ví dụ dựa trên mô hình Spring Security sử dụng session. Cần cấu hình một nguồn người dùng hoặc identity provider để login thực sự hoạt động, đồng thời quản lý CSRF token và trang/form login phù hợp.

Spring Security thường quản lý session fixation protection và lưu/khôi phục `SecurityContext` theo cấu hình security đang dùng. Không nên tự viết login controller chỉ bằng cách đặt:

```java
session.setAttribute("authenticated", true);
```

rồi coi đó là xác thực an toàn. Một session attribute tự đặt không thay thế quy trình xác minh danh tính và kiểm soát quyền của Spring Security.

### 4.2. Controller ghi và đọc một thuộc tính session

```java
import jakarta.servlet.http.HttpSession;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/me")
public class UserPreferencesController {

    @GetMapping("/session")
    public Map<String, Object> currentSession(
            HttpSession session,
            Authentication authentication) {

        String locale = (String) session.getAttribute("locale");

        return Map.of(
                "authenticatedUser", authentication.getName(),
                "preferredLocale", locale == null ? "vi-VN" : locale,
                "isNewSession", session.isNew());
    }

    @PostMapping("/locale/vi")
    public Map<String, String> setVietnameseLocale(HttpSession session) {
        session.setAttribute("locale", "vi-VN");
        return Map.of("locale", "vi-VN");
    }

    @PostMapping("/locale/en")
    public Map<String, String> setEnglishLocale(HttpSession session) {
        session.setAttribute("locale", "en-US");
        return Map.of("locale", "en-US");
    }
}
```

Các request có session ID hợp lệ sẽ tìm session qua Redis. Thuộc tính `locale` là ví dụ dữ liệu phụ có thể lưu trong session; thông tin `Authentication` được lấy từ Spring Security chứ không phải một giá trị do controller tin tưởng từ request header không được xác thực.

Với Spring Security và CSRF được bật theo mặc định phù hợp cho session-based browser login, các request `POST` cần CSRF token hợp lệ. Không vô hiệu hóa CSRF chỉ để ví dụ `curl -X POST` chạy được; trong bài thử nghiệm nên gửi token do ứng dụng phát và cookie cùng phiên.

### 4.3. Luồng request qua nhiều replica

```text
Request 1:
Browser -- POST /login --> App A
                         |
                         +-- Spring Security xác thực
                         +-- Spring Session lưu session vào Redis
                         +-- Response Set-Cookie: SESSION=<opaque-id>

Request 2:
Browser -- GET /me/session --> App B
           Cookie SESSION=<same-id>
                         |
                         +-- Spring Session đọc dữ liệu ở Redis
                         +-- Spring Security khôi phục Authentication
                         +-- Controller trả thông tin người dùng

Request 3:
Browser -- POST /me/locale/en --> App C
                         |
                         +-- Cập nhật session attribute
                         +-- Spring Session lưu thay đổi vào Redis
```

Nếu load balancer chuyển request từ A sang B hoặc C, session có thể tiếp tục vì dữ liệu được chia sẻ qua Redis. Điều kiện là các instance phải thống nhất về **namespace, serialization, phiên bản schema, cấu hình security, thời gian sống và cookie**.

Đặt cùng tên cookie nhưng trỏ mỗi replica đến một Redis khác nhau không tạo shared session store.

## 5. Cookie chứa gì và tại sao không nên coi cookie là session store?

Với mô hình server-side session của Spring Session, browser thường có cookie như:

```http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Session ID là một **bearer secret**: ai có giá trị session ID hợp lệ có thể có khả năng sử dụng phiên theo các điều kiện bảo vệ của hệ thống. Do đó:

- Luôn dùng HTTPS để tránh lộ cookie khi truyền.
- Đặt `Secure` và `HttpOnly` phù hợp.
- Đặt `SameSite` theo luồng đăng nhập và mức bảo vệ CSRF cần có.
- Chọn `Path` và `Domain` hẹp nhất cần thiết.
- Không đưa session ID vào URL, log, analytics event hoặc response body công khai.
- Không log nguyên header `Cookie` hay `Set-Cookie` chứa session secret.
- Bảo vệ trước session fixation và session hijacking bằng cơ chế security phù hợp.

Cookie thông thường **chỉ mang ID**, không phải toàn bộ `SecurityContext` hoặc object Java trong Redis. Điều này khác với mô hình lưu toàn bộ authentication claims vào một token tự chứa như JWT.

### 5.1. Cookie domain và chia sẻ giữa subdomain

Giả sử hai ứng dụng:

```text
app1.example.com
app2.example.com
```

Nếu đặt cookie domain quá rộng như `.example.com`, cookie có thể được gửi tới cả hai ứng dụng. Việc đó không tự khiến hai ứng dụng chia sẻ phiên hợp lệ: chúng còn cần cùng session namespace/repository và hợp đồng security, và việc dùng chung cookie mở rộng phạm vi rủi ro nếu một subdomain bị xâm nhập.

Trong nhiều hệ thống, nên để cookie **host-only** thay vì chia sẻ toàn domain, trừ khi có yêu cầu SSO/session sharing được thiết kế và đánh giá an toàn riêng.

### 5.2. Không tự thiết kế session ID

Đừng tạo session ID từ user ID, timestamp hoặc số tăng:

```text
sessionId = "user-1001-2026-11-13"     // dễ đoán, không phù hợp
```

Dùng cơ chế sinh ID của Spring Session/Servlet integration đã được thiết kế cho session identifier. Không dùng email, số điện thoại hoặc user ID làm session ID.

## 6. Vòng đời của một login session

Một phiên có thể đi qua các trạng thái:

```text
Chưa có session
       |
       v
Tạo session khi cần
       |
       v
Xác thực thành công (login)
       |
       +-- Spring Security áp dụng session fixation protection
       |
       v
Session hợp lệ, chứa trạng thái SecurityContext
       |
       +-- Nhiều request đọc/cập nhật session
       |
       +-- lastAccessedTime/TTL được quản lý
       |
       +-- Có thể đổi/rotate ID theo security policy
       |
       v
Một trong các sự kiện kết thúc:
       |
       +-- User logout
       +-- Session timeout
       +-- Administrator revoke
       +-- Repository/session bị xóa
       +-- Redis mất dữ liệu/session
       |
       v
Session không còn hợp lệ
       |
       v
Request kế tiếp phải xác thực lại
```

Cần phân biệt **session tồn tại**, **session chưa hết hạn** và **người dùng hiện còn được phép đăng nhập**. Một user có thể đã bị khóa trong database khi session trong Redis vẫn còn sống. Nếu nghiệp vụ yêu cầu khóa tài khoản có hiệu lực tức thì, hệ thống cần cơ chế revoke/revalidate thích hợp, không chỉ dựa vào TTL.

## 7. Session timeout và Redis TTL

`server.servlet.session.timeout: 30m` thường biểu thị **thời gian không hoạt động tối đa** (max inactive interval) của phiên HTTP Servlet, không nhất thiết là tuổi đời tuyệt đối 30 phút kể từ lúc login.

Ví dụ:

```text
10:00 user login
10:10 user request  -> session vẫn hoạt động
10:20 user request  -> session vẫn hoạt động
10:49 không có request đủ lâu -> session có thể đã hết hạn
```

Nếu ứng dụng cần cả **idle timeout** và **absolute maximum lifetime** (ví dụ buộc login lại sau 8 giờ bất kể hoạt động), phải thiết kế thêm chính sách tuổi phiên tuyệt đối. Chỉ dựa vào max inactive interval không thực hiện được yêu cầu đó.

### 7.1. TTL của Redis có thể khác một phép trừ thời gian đơn giản

Spring Session dùng các key, metadata và chiến lược lưu/hết hạn để triển khai session. Ở những phiên bản/configuration cụ thể, TTL vật lý của một số key nội bộ có thể được đặt dài hơn max inactive interval để hỗ trợ sự kiện hết hạn hoặc dọn dẹp.

Vì vậy, không suy luận:

```text
Redis TTL key = 1800 seconds
=> Chắc chắn user còn đúng 1800 giây truy cập.
```

Khả năng session còn hợp lệ phải được đánh giá qua `SessionRepository` và thuộc tính thời gian của phiên, không chỉ nhìn một Redis key vật lý. Key prefix, chỉ mục và dữ liệu nội bộ có thể khác theo repository implementation/phiên bản.

### 7.2. Không sửa TTL/session keys trực tiếp bằng StringRedisTemplate

Tránh viết một service phụ:

```java
redis.expire("spring:session:sessions:" + sessionId, Duration.ofHours(4));
```

rồi tin rằng đã thay đổi đúng chính sách phiên. Làm vậy bỏ qua những dữ liệu nội bộ/index và quy tắc expiry của Spring Session. Nếu cần thay timeout, sử dụng API session/repository và cấu hình được hỗ trợ, ví dụ:

```java
session.setMaxInactiveInterval(30 * 60);
```

và để Spring Session lưu lại theo cơ chế của implementation. Nếu cần thay đổi timeout mặc định của mọi phiên, cấu hình ở lớp ứng dụng thay vì “chỉnh Redis key bằng tay”.

## 8. Chế độ lưu session: flush mode và save mode

Spring Session Data Redis có những cơ chế điều khiển **khi nào thay đổi được ghi tới Redis** và **những thuộc tính nào được xem là cần lưu**.

Những khái niệm cần phân biệt:

- **Flush mode**: thời điểm ghi thay đổi vào Redis, ví dụ `ON_SAVE` hoặc `IMMEDIATE` theo những cấu hình được hỗ trợ.
- **Save mode**: phạm vi thuộc tính được ghi, ví dụ những attribute thực sự được cập nhật hay tập attribute rộng hơn tùy chế độ/implementation.

Các lựa chọn cụ thể phụ thuộc phiên bản Spring Session, nhưng ý nghĩa kiến trúc không đổi:

| Vấn đề | Khi lưu trễ đến cuối request | Khi lưu thay đổi sớm |
|---|---|---|
| Số lần ghi Redis | Thường ít hơn | Có thể nhiều hơn |
| Thời điểm request khác thấy giá trị mới | Có thể sau khi request hiện tại hoàn thành | Có thể thấy sớm hơn |
| Request lỗi giữa chừng | Có thể chưa flush một số thay đổi | Có thể đã có thay đổi được ghi |
| Concurrent updates | Có nguy cơ mất cập nhật tùy save mode | Vẫn có race nếu nhiều request sửa cùng thuộc tính |

Đừng tự suy luận `IMMEDIATE` biến mỗi `setAttribute` thành một transaction an toàn xuyên nhiều request. Nó chỉ ảnh hưởng thời điểm ghi, không làm xuất hiện một distributed lock cho cả phiên.

### 8.1. Mutable object là bẫy

Giả sử lưu một object mutable:

```java
CartState cart = (CartState) session.getAttribute("cart");
cart.addItem("sku-1");  // chỉ thay đổi object trong bộ nhớ
```

Tùy save mode, framework có thể không nhận ra attribute đã được cập nhật nếu không gọi lại `setAttribute`, và thay đổi có thể không được persist như kỳ vọng.

Rõ ràng hơn:

```java
CartState current = (CartState) session.getAttribute("cart");
CartState next = current.withAddedItem("sku-1");
session.setAttribute("cart", next);
```

Tuy nhiên, hai request đồng thời vẫn có thể đọc cùng bản cũ rồi ghi đè nhau. Với shopping cart có yêu cầu consistency cao, lưu cart vào một kho nghiệp vụ có version/atomic operations thường hợp lý hơn việc coi session như database giao dịch.

## 9. Tích hợp Spring Security: SecurityContext và thay đổi session ID

Spring Security có thể lưu `SecurityContext` qua security context repository dùng HTTP session trong mô hình session-based authentication. Spring Session làm tầng `HttpSession` bên dưới nên thông tin phù hợp có thể được lưu và khôi phục qua Redis.

Điều quan trọng:

1. **Spring Security xác thực** người dùng và tạo `Authentication`.
2. Security framework quản lý quá trình lưu/khôi phục `SecurityContext` theo filter chain đang bật.
3. Spring Session lưu dữ liệu phiên do HttpSession giữ vào Redis.
4. Browser nhận session ID để tham chiếu tới phiên trong những request tiếp theo.

Không đặt toàn bộ quyền của người dùng vào một object tùy biến rồi bỏ kiểm tra quyền trong Spring Security. Nếu quyền có thể thay đổi trong thời gian phiên còn sống, cần chính sách làm mới hoặc vô hiệu hóa authentication state.

### 9.1. Session fixation protection

Một cuộc tấn công session fixation tìm cách khiến nạn nhân login bằng một session ID đã được đối tượng tấn công biết trước. Spring Security hỗ trợ chiến lược thay đổi session ID sau khi xác thực thành công theo cấu hình phù hợp.

Không tự giữ nguyên ID phiên trước và sau login chỉ để “không mất cart”, nếu điều đó phá cơ chế chống fixation. Nếu ứng dụng cần chuyển dữ liệu phiên trước đăng nhập sang phiên đã xác thực, phải chọn chiến lược migration/copy phù hợp và không chuyển các thuộc tính không được tin cậy một cách mù quáng.

### 9.2. Logout và session invalidation

Cấu hình logout của Spring Security có thể invalid session hiện tại và xóa cookie theo yêu cầu. Điều này khác với chỉ trả:

```java
return ResponseEntity.ok("Logged out");
```

Nếu chỉ trả lời HTTP thành công mà không xóa `SecurityContext`, vô hiệu hóa session hoặc áp dụng chính sách tương ứng, browser có thể tiếp tục dùng phiên cũ.

Với ví dụ form login và CSRF bật, logout thường là một request `POST` có CSRF token hợp lệ; không mặc định mở logout bằng `GET` như một endpoint có side effect.

### 9.3. Cookie bị xóa chưa chắc session ở Redis đã bị revoke

`Set-Cookie` với thời hạn quá khứ khiến browser không gửi ID đó nữa. Nhưng nếu session server-side vẫn còn, một người đã giữ ID hợp lệ trước đó có thể có khả năng tiếp tục sử dụng trong một số tình huống.

**Logout an toàn cần xử lý session server-side theo policy**, không chỉ xóa cookie phía client.

Ngược lại, xóa session ở Redis mà không điều chỉnh cookie khiến browser còn gửi ID đã hết hiệu lực; server nên coi request đó là chưa có session authenticated và yêu cầu login lại.

## 10. Quản trị nhiều phiên đăng nhập của một người dùng

Một người dùng có thể đồng thời đăng nhập trên laptop, điện thoại và browser khác. Nghiệp vụ có thể cần:

- Hiển thị danh sách thiết bị/phiên.
- Revoke một phiên cụ thể.
- Logout tất cả các phiên.
- Giới hạn số phiên đăng nhập đồng thời.
- Xóa tất cả phiên khi đổi mật khẩu hoặc tài khoản bị khóa.

Các yêu cầu này **không tự được đáp ứng** chỉ vì session lưu trong Redis. Muốn tìm session theo principal, cần repository/chiến lược index phù hợp.

### 10.1. RedisSessionRepository so với RedisIndexedSessionRepository

Một repository cơ bản tập trung vào thao tác theo **session ID**. Repository indexed hỗ trợ tra cứu theo chỉ mục, chẳng hạn principal, với các đặc điểm và chi phí duy trì index riêng.

Trong Spring Session Data Redis, các cấu hình như `@EnableRedisIndexedHttpSession` hoặc lựa chọn repository type tương ứng có thể được dùng để bật indexing theo phiên bản. Nhưng không bật annotation này tùy tiện bên cạnh cấu hình Spring Boot tự tạo session repository mà không kiểm tra các bean/result thực tế.

Indexing có đánh đổi:

- Ghi/xóa session có thể tạo thêm metadata/index.
- Logout/revoke theo principal cần đọc đúng index.
- Xử lý expiration event và dọn index có giới hạn theo topology/notification.
- Cấu hình Redis Cluster có những giới hạn riêng liên quan tới việc thu nhận event/index theo node.
- Tính nhất quán của index sau failure cần được đo và đối soát khi yêu cầu bảo mật cao.

### 10.2. Ví dụ thu hồi các session đã biết theo principal

Nếu dự án đã cấu hình `FindByIndexNameSessionRepository` phù hợp, có thể lấy các session của principal và xóa những session không phải phiên hiện tại:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class AccountSessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public void revokeOtherSessions(
            String authenticatedPrincipalName,
            String currentSessionId) {

        sessions.findByPrincipalName(authenticatedPrincipalName)
                .values()
                .stream()
                .filter(session -> !session.getId().equals(currentSessionId))
                .forEach(session ->
                        sessions.deleteById(session.getId()));
    }
}
```

**Không nhận `authenticatedPrincipalName` trực tiếp từ body do người dùng nhập rồi cho xóa session tùy ý.** Principal phải xuất phát từ security context đã được xác thực và có authorization phù hợp. Tương tự, API quản trị session của người khác cần phân quyền riêng.

Đoạn code thể hiện thao tác repository, không chứng minh rằng toàn bộ index luôn phản ánh tức thời mọi trạng thái trong mọi Cluster/failover. Nếu yêu cầu thu hồi khẩn cấp, cần thiết kế thêm cơ chế kiểm tra tại request mới, chẳng hạn session version/revocation epoch.

### 10.3. Giới hạn số session đồng thời

Spring Security có các cơ chế concurrent session control trong một số cấu hình; nhưng khi dùng Spring Session, phải kiểm tra cách các thành phần `SessionRegistry`/repository tương thích với session store được chia sẻ.

Không coi việc bật một `maximumSessions(1)` ở một instance local là đủ để điều phối phiên trên toàn cụm khi registry đang nằm trong memory riêng từng instance.

Trong hệ thống lớn, còn có race: hai login diễn ra đồng thời trên hai node có thể cùng kiểm tra rồi tạo phiên. Nếu yêu cầu “chỉ một phiên” là bất biến bảo mật bắt buộc, cần cơ chế phối hợp ở nguồn được lựa chọn, không chỉ so sánh số lượng phiên qua hai lệnh không nguyên tử.

## 11. Sự kiện hết hạn và logout không phải event log nghiệp vụ

Spring Session có thể cung cấp session lifecycle events như tạo, xóa hoặc hết hạn phiên, tùy repository và cơ chế thông báo đang dùng. Điều này hữu ích để dọn dữ liệu phụ hoặc quan sát.

Nhưng cần hiểu giới hạn:

- Redis key expiration có thể được thông báo **không chính xác tại mili-giây TTL chạm 0**; việc dọn key chịu cơ chế expiration của Redis.
- Redis keyspace/keyevent notifications dựa trên Pub/Sub nên **không có hàng đợi bền** cho listener đang offline.
- Ở Redis Cluster, sự kiện của một node không mặc nhiên được phát và nhận như một event log toàn cụm.
- Một failure hoặc deploy có thể khiến listener không nhận một số expiration events.
- Không nên phụ thuộc vào event session destroyed để thực thi nghĩa vụ nghiệp vụ bắt buộc đúng một lần.

Ví dụ sai:

```text
User session hết hạn
        |
        v
SessionDestroyedEvent
        |
        v
Bắt buộc trừ tiền hoặc đóng sổ giao dịch
```

Nếu event bị mất, nghiệp vụ có thể không hoàn tất. Những side effect bắt buộc nên dựa vào nguồn giao dịch bền, scheduler có đối soát hoặc hàng đợi có ACK/retry, không coi session expiration event là tín hiệu duy nhất.

### 11.1. Keyspace notifications có thể bị hạn chế

Một số chế độ indexed session repository tận dụng khả năng Redis phát sự kiện xóa/hết hạn key hoặc duy trì cấu trúc hỗ trợ expiration. Trong môi trường Redis quản lý sẵn, quyền thay đổi `notify-keyspace-events` có thể bị hạn chế; trong Cluster, cách thu nhận event còn phụ thuộc từng node và cơ chế của Spring Session.

Cần đánh giá xem tính năng phụ thuộc expiration events có hoạt động **đúng với topology production** hay không. Không tự sửa cấu hình Redis production chỉ để làm một listener “có vẻ hoạt động” mà bỏ qua quyền quản trị và ảnh hưởng vận hành.

## 12. Redis Cluster và Sentinel khi lưu session

Một trong những lý do chọn Redis làm session store là nhiều instance có thể dùng chung. Nhưng khi Redis được triển khai thành Sentinel hoặc Cluster, cần hiểu các đặc tính phân tán.

### 12.1. Sentinel: failover không đồng nghĩa không mất session

```text
Spring instances
       |
       v
Lettuce/Sentinel discovery
       |
       v
Current Redis primary
       |
       v
Replica(s)
```

Redis replication có thể bất đồng bộ. Một session vừa được ghi trên primary trước khi failover có thể chưa hiện diện ở replica được nâng lên primary mới, tùy trạng thái replication/persistence tại thời điểm sự cố.

Hệ quả:

- Người dùng có thể phải login lại sau failover.
- Session vừa revoke có thể xuất hiện lại ở dữ liệu khôi phục không đúng như kỳ vọng nếu không có cơ chế kiểm soát bổ sung.
- Một request đang lưu session có thể timeout với kết quả **không xác định**.
- Lettuce reconnect không đảm bảo các session writes đã được thực thi chính xác một lần theo mọi kịch bản.

Với dữ liệu xác thực nhạy cảm, đánh giá khả năng **mất/reappear session và trạng thái revoke**. Có thể chọn Redis cho session, nhưng phải chốt yêu cầu availability và security khi failover.

### 12.2. Redis Cluster: các key không nhất thiết ở một slot

Spring Session có thể lưu session và metadata/index/expiration-related keys theo quy tắc implementation. Không mặc định mọi key của một session hoặc tất cả index đều nằm cùng hash slot chỉ vì có prefix chung.

```text
myapp:session:sessions:<id-1> -> slot A
myapp:session:sessions:<id-2> -> slot B
myapp:session:index:...      -> có thể slot khác
```

Tên key chỉ minh họa; implementation có thể dùng cách tổ chức khác theo phiên bản. Nếu repository có thao tác nhiều key cần atomicity hoặc Lua, giới hạn Redis Cluster về slot cần được xác minh.

Đặc biệt đối với **indexed repository** và session lifecycle notifications, phải kiểm tra tài liệu/hành vi của phiên bản Spring Session đang chạy với Redis Cluster. Không suy luận từ việc một thao tác `GET sessionId` thành công rằng tra cứu principal, dọn index và sự kiện expired cũng đã đúng trên mọi node.

### 12.3. Đọc từ replica có thể cho session stale

Nếu cấu hình Lettuce đọc từ replica để giảm tải, replication lag có thể khiến request nhận session state cũ:

```text
App A ghi logout/invalidate trên primary
                        |
                 Replication async
                        |
App B đọc từ replica chưa cập nhật
                        |
                 Có thể nhìn thấy state cũ
```

Đối với session xác thực, việc nhìn thấy một trạng thái revoke cũ có thể là rủi ro bảo mật. Vì vậy, **đường đọc session nên có chính sách consistency chủ động**; không tự bật replica reads cho session chỉ để tăng throughput mà chưa chứng minh được semantics khi logout, khóa tài khoản hoặc thay đổi quyền.

Với các quyết định truy cập nhạy cảm, ưu tiên kiểm tra trạng thái authoritative và cơ chế revoke đáng tin cậy.

## 13. Session Redis là kho dữ liệu có giới hạn tài nguyên

Khác với cách nghĩ “Redis nhanh nên cứ lưu object vào session”, mỗi session là một phần bộ nhớ Redis, và mỗi request có thể phát sinh ghi/đọc/tăng TTL.

Một session giữ nhiều object lớn có thể dẫn tới:

- Dung lượng Redis tăng mạnh theo số người dùng online.
- Serialize/deserialize chậm.
- Băng thông giữa app và Redis tăng.
- Nhiều byte phải được nhân bản tới replica.
- Thời gian GC Java tăng nếu session chứa object graph lớn.
- Khó triển khai nhiều phiên bản ứng dụng cùng đọc session.

Ví dụ không phù hợp:

```java
session.setAttribute("allOrders", orderRepository.findAllByUser(userId));
session.setAttribute("cartHistory", hugeObjectGraph);
session.setAttribute("fullUser", entityWithRelations);
```

Thay vì lưu hàng nghìn bản ghi hoặc entity JPA lazy-loading, có thể lưu:

```java
session.setAttribute("currentWorkspaceId", workspaceId);
session.setAttribute("preferredLocale", "vi-VN");
```

Dữ liệu nghiệp vụ chính được đọc từ database/cache chuyên dụng theo ID và kiểm tra quyền theo request.

### 13.1. Redis maxmemory-policy và session eviction

Nếu Redis gần giới hạn bộ nhớ và chính sách `maxmemory-policy` cho phép evict key, dữ liệu session có thể bị loại bỏ trước thời điểm inactivity timeout. Hệ quả thường là user đột ngột bị logout hoặc mất một số attribute.

Không chia chung một Redis được cấu hình **evict cache mạnh** cho session xác thực rồi kỳ vọng session sống đủ TTL. Cần đánh giá:

- Memory budget cho số session cực đại.
- Chính sách eviction phù hợp, thường không được tùy tiện xóa session còn sống.
- Alert khi memory cao, lệnh ghi bị từ chối hoặc Redis bị quá tải.
- Phương án khi Redis tạm không hoạt động.
- Backup/persistence/replication theo yêu cầu availability và security.

Một hệ thống có thể cố ý chấp nhận mất session khi Redis lỗi (buộc login lại) thay vì cố duy trì phiên bằng dữ liệu cũ không đáng tin. Quyết định này phải dựa trên threat model và SLO.

## 14. Serialization và nâng cấp ứng dụng

Session chứa nhiều thuộc tính Java. Spring Session Data Redis cần serializer để lưu chúng vào Redis. Mặc định serializer thực tế phụ thuộc phiên bản/configuration; một số cấu hình phổ biến sử dụng **Java native serialization** khi không tùy biến.

Rủi ro khi triển khai rolling deployment:

```text
App v1:
    session attribute class UserPreferencesV1

App v2:
    session attribute class UserPreferencesV2
    cấu trúc trường thay đổi

Cả hai đọc cùng Redis:
    có thể deserialize lỗi hoặc không hiểu dữ liệu cũ
```

Nếu không quản lý schema, người dùng có thể mất session sau khi deploy hoặc gặp lỗi truy cập do object không tương thích.

### 14.1. Những quy tắc hữu ích

- Chỉ lưu những thuộc tính thật sự cần cho phiên.
- Tránh nhét JPA entity, object graph lớn, socket/connection, bean hoặc dữ liệu không serializable vào session.
- Thiết kế DTO nhỏ, có thể version hóa, hoặc lưu primitive/ID.
- Không thay serializer giữa hai phiên bản mà không có chiến lược migration.
- Kiểm tra tương thích với `SecurityContext`/`Authentication` do Spring Security sử dụng.
- Không deserialize dữ liệu session từ nguồn Redis không đáng tin; đánh giá rủi ro của Java deserialization và khả năng truy cập Redis.
- Khi dùng JSON serializer, xác định rõ type metadata, allowlist/type mapping và cấu trúc bảo mật, không bật polymorphic deserialization rộng tùy tiện.

### 14.2. Spring Session serializer riêng

Trong Spring Session Data Redis, một bean serializer có tên quy ước như `springSessionDefaultRedisSerializer` có thể được sử dụng để tùy chỉnh serialization trong những cấu hình/phiên bản hỗ trợ.

Ví dụ định hướng:

```java
// Pseudocode cấu hình:
// @Bean("springSessionDefaultRedisSerializer")
// RedisSerializer<?> sessionSerializer() {
//     return serializerDuocCauHinhAnToanChoSpringSecurity();
// }
```

Không nên sao chép pseudocode trên như một cấu hình hoàn chỉnh: serializer phải tương thích với tất cả attribute, đặc biệt `SecurityContext` và những subtype xác thực. Nếu chọn JSON, cần module/mixin của Spring Security phù hợp với phiên bản library, xử lý schema migration và kiểm tra cả quá trình login, logout, rolling deploy.

**Đổi serializer khi đã có live sessions là một migration dữ liệu**, không chỉ đổi một bean. Có thể cần giai đoạn đọc hai định dạng, namespace mới hoặc chủ động buộc re-login có thông báo.

## 15. Session và dữ liệu nghiệp vụ: giới hạn tích hợp

Một session có thể giữ trạng thái tạm thời như locale, tab hiện tại, mã flow id, nhưng không nên trở thành nguồn sự thật cho:

- Số dư tài khoản hoặc lịch sử giao dịch.
- Tồn kho, giá đặt hàng cuối cùng.
- Vai trò/quyền truy cập cần có hiệu lực tức thời.
- Hóa đơn, dữ liệu audit hoặc các sự kiện không được phép mất.
- Khóa phân tán hoặc trạng thái workflow dài ngày.
- Token bí mật không cần thiết phải nằm trong session.

Lý do là session có thể:

1. Hết hạn theo inactivity timeout.
2. Bị revoke khi logout.
3. Bị Redis evict hoặc mất khi sự cố.
4. Bị ghi đè bởi request đồng thời.
5. Không được commit nguyên tử cùng database.
6. Được serialize theo phiên bản application và có thể không tương thích khi deploy.

**Cơ chế xác thực và dữ liệu kinh doanh có tuổi thọ, bảo đảm và người chịu trách nhiệm khác nhau.** Spring Session nên giữ dữ liệu tối thiểu cần cho trải nghiệm phiên, còn database/identity store giữ dữ liệu lâu dài có bất biến nghiệp vụ.

## 16. Concurrent requests có thể gây mất cập nhật session

Hai request từ cùng browser có thể đến cùng lúc:

```text
Request A                           Request B
    |                                   |
Đọc session version cũ           Đọc session version cũ
    |                                   |
locale = "vi"                     theme = "dark"
    |                                   |
Ghi session                        Ghi session
    |                                   |
    +----------> Redis <---------------+
```

Tùy repository, flush/save mode và cách các attribute được lưu, một cập nhật có thể ghi đè trạng thái hoặc khiến request sau quan sát dữ liệu chưa đồng bộ. Đặc biệt khi **cùng một attribute mutable** được hai request sửa, không nên kỳ vọng Spring Session tự cung cấp optimistic locking cho logic nghiệp vụ.

Với tính năng quan trọng như thêm/xóa item trong cart, nên dùng cấu trúc dữ liệu riêng và thiết kế atomic update, version control hoặc transaction theo nguồn sự thật. Không dựa vào việc session được chia sẻ trong Redis để chứng minh mọi thay đổi session đều không có race.

### 16.1. Không giữ long-running lock trên toàn HttpSession

Khóa toàn session từ đầu request đến cuối request có thể làm giảm concurrency và gây deadlock/chờ lâu nếu một request gọi API ngoài. Khi cần coordination, chỉ khóa/ràng buộc những thao tác cần nhất quán, giới hạn thời gian và thiết kế xử lý lỗi rõ ràng.

## 17. Ranh giới transaction giữa database và Redis session

Một request login hoặc cập nhật profile có thể thực hiện:

```text
1. Database transaction: cập nhật profile.
2. Session: ghi attribute hiển thị tên mới.
3. HTTP response: trả thành công.
```

Nếu database rollback nhưng session đã được lưu, session có thể hiển thị dữ liệu không phù hợp với nguồn. Nếu database commit nhưng ghi Redis lỗi, session có thể còn dữ liệu cũ hoặc người dùng cần login lại.

`@Transactional` của JPA/JDBC/R2DBC **không tự tạo giao dịch nguyên tử giữa database và Spring Session Redis**. Redis session và database là những tài nguyên riêng.

Các hướng thiết kế:

- Xem database là nguồn sự thật.
- Không để session attribute quyết định một thay đổi tài chính hoặc quyền truy cập quan trọng mà không kiểm tra nguồn.
- Khi profile đổi, có thể invalidate/refresh thông tin hiển thị ở session theo chính sách.
- Với thay đổi quyền, thiết kế revalidation hoặc session revocation theo mức độ khẩn cấp.
- Nếu cần sự kiện đáng tin cậy sau commit, dùng outbox hoặc cơ chế event bền; không dùng `HttpSession.setAttribute` làm event log.
- Với trạng thái giao dịch nhiều bước, lưu workflow state vào database phù hợp thay vì chỉ giữ trong session.

Một thay đổi session có thể thành công rồi request trả lỗi; client retry cũng có thể tạo các side effect khác. Chọn idempotency key/transaction boundary cho nghiệp vụ, không coi session repository là transaction coordinator.

## 18. Ranh giới tích hợp với JWT, OAuth2 và OpenID Connect

Spring Session thường phù hợp với **server-side session authentication**, nơi server giữ SecurityContext và browser mang session cookie. JWT/OAuth2/OIDC có những vai trò khác:

| Khái niệm | Vai trò |
|---|---|
| Spring Session | Lưu/vận hành phiên server-side qua Redis hoặc store khác |
| Spring Security | Xác thực, authorization, security filters, session management |
| Session cookie | Mang session identifier của phiên server |
| OAuth2 access token | Credential để truy cập resource server theo scope/quy tắc của hệ thống |
| Refresh token | Credential lấy access token mới theo quy tắc authorization server |
| ID token (OIDC) | Thể hiện thông tin xác thực người dùng từ identity provider theo chuẩn OIDC |
| JWT | Định dạng token tự chứa có thể được ký; không đồng nghĩa một phiên Redis |

### 18.1. JWT resource server không tự dùng Spring Session

Một API chỉ xác thực bearer access token trên mỗi request có thể hoạt động stateless, không cần `HttpSession`. Bật Spring Session Data Redis **không tự khiến mọi JWT được lưu trong Redis**, và xóa một Spring Session không đương nhiên revoke access token đã phát.

Nếu mục tiêu là revoke JWT/refresh token, phải dùng cơ chế token revocation, introspection, tuổi token ngắn, token version hoặc authoritative authorization server phù hợp.

### 18.2. OAuth2 login trên browser có thể vẫn dùng session

Một ứng dụng web thực hiện OAuth2/OIDC login có thể tạo session sau khi callback xác thực hoàn tất; Spring Security lưu SecurityContext vào phiên. Đây là một cách kết hợp bình thường: **OIDC làm đăng nhập, Spring Session lưu trạng thái đăng nhập của web application**.

Nhưng vẫn cần quản lý:

- State/nonce của OAuth2 flow theo cơ chế bảo mật thích hợp.
- Callback URL, cookie SameSite và HTTPS.
- Session fixation protection.
- Logout ở ứng dụng so với logout tại identity provider.
- Access/refresh token lifecycle nếu ứng dụng thực sự lưu hoặc dùng các token đó.
- Authorization khi user bị thu hồi quyền ở IdP trong lúc local session còn sống.

Logout local không tự đảm bảo global single logout ở mọi client/identity provider.

## 19. Ranh giới với WebFlux reactive session

Trong **Spring WebFlux**, không dùng Servlet `HttpSession`. Ứng dụng thường dùng `WebSession` và `WebSessionManager`; Spring Session có tích hợp Redis reactive qua repository và cấu hình phù hợp.

Sơ đồ:

```text
Spring MVC (Servlet)                 Spring WebFlux (Reactive)
--------------------                 -------------------------
HttpSession                          WebSession
SessionRepositoryFilter              WebSessionManager/integration
RedisSessionRepository                Reactive Redis session repository
Spring Security servlet filters      Spring Security WebFilterChain
Servlet SecurityContext handling     Reactive SecurityContext handling
```

Một controller WebFlux có thể nhận `WebSession`:

```java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

@RestController
public class ReactiveSessionController {

    @GetMapping("/session/locale")
    public Map<String, String> locale(WebSession session) {
        String locale = session.getAttribute("locale");
        return Map.of(
                "locale", locale == null ? "vi-VN" : locale);
    }
}
```

Ví dụ minh họa kiểu API WebFlux; ứng dụng cần cấu hình security và session store reactive phù hợp. Không đưa `RedisTemplate` blocking vào event loop để quản lý session của WebFlux. Cần dùng integration reactive được Spring Session hỗ trợ cho phiên bản framework của dự án.

### 19.1. Không trộn Servlet và WebFlux session giữa hai hệ thống tùy tiện

Một frontend gọi đồng thời:

```text
mvc.example.com    -> Servlet HttpSession
api.example.com    -> WebFlux WebSession
```

Dù cùng Redis và cùng tên cookie, không được mặc định hai hệ thống sử dụng cùng định dạng session, cùng repository, cùng SecurityContext serialization hoặc cùng quy tắc auth. Việc chia sẻ một session giữa các framework khác nhau là một bài toán tương thích/SSO cần thiết kế riêng, không tự hình thành chỉ vì chung Redis.

Thông thường, dễ kiểm soát hơn là dùng một identity provider/SSO và để mỗi ứng dụng quản lý session của chính nó.

## 20. Cấu trúc key Redis: không phụ thuộc implementation nội bộ

Khi dùng Spring Session Data Redis, có thể thấy các key mang prefix namespace và dữ liệu session/index/expiry. Trong một số cấu hình/phiên bản, tên key có thể tương tự:

```text
myapp:session:sessions:<session-id>
myapp:session:expirations:...
myapp:session:index:...
```

Đây chỉ là **ví dụ cách tổ chức có thể gặp**, không phải hợp đồng public API ổn định. Chi tiết key, kiểu Redis (hash/string/set), TTL và cơ chế indexing thay đổi tùy repository/phiên bản.

Không xây logic nghiệp vụ bằng cách:

- `GET` key nội bộ rồi deserialize thủ công ngoài Spring Session.
- Sửa trực tiếp trường `sessionAttr:SPRING_SECURITY_CONTEXT` mà không qua Spring Security.
- `DEL` tất cả key khớp pattern rồi coi là revoke đúng mọi index.
- Dùng `KEYS myapp:session:*` trên Redis production lớn.
- Tự gán TTL cho từng key nội bộ rồi kỳ vọng session lifecycle hoạt động đúng.

Hãy dùng `SessionRepository`, `HttpSession` hoặc API quản trị được hỗ trợ. Khi quan sát Redis ở CLI, thao tác read-only và xác định mục tiêu cụ thể.

## 21. Quan sát session ở production

Nếu session store là một dependency cho authentication, cần đo:

| Chỉ số | Ý nghĩa |
|---|---|
| Tỷ lệ login thành công/thất bại | Sức khỏe auth flow và identity provider |
| Tỷ lệ request có session hợp lệ | Khả năng duy trì đăng nhập |
| Session create/delete/expire | Tốc độ vòng đời và dấu hiệu thay đổi bất thường |
| Redis session read/write latency | Tác động đến mọi request cần session |
| Session lookup miss | Session hết hạn, bị revoke, mất dữ liệu hoặc lỗi namespace |
| Redis timeout/connection errors | Nguy cơ request authentication thất bại |
| Reconnect/failover count | Phát hiện hạ tầng không ổn định |
| Serializer errors | Không tương thích thuộc tính session giữa phiên bản |
| Memory usage và eviction rate | Session bị đẩy ra trước timeout do áp lực bộ nhớ |
| Session size distribution | Phát hiện session quá lớn |
| Index lookup/revocation failures | Tính đúng của chức năng “logout all devices” |
| Logout-to-revocation latency | Khoảng thời gian từ revoke đến khi request cũ bị từ chối |
| Replica lag | Rủi ro session stale khi đọc replica |

Các thống kê Redis:

```bash
redis-cli INFO stats
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO commandstats
```

Nếu muốn kiểm tra TTL của **một key đã xác định chính xác** trong môi trường phù hợp:

```bash
redis-cli TTL 'myapp:session:sessions:<session-id>'
```

Nhưng không log session ID thực hoặc dump toàn bộ session attribute ra hệ thống quan sát. Session ID là dữ liệu nhạy cảm; có thể dùng correlation ID khác để trace.

### 21.1. Health check và chính sách khi Redis không sẵn sàng

Nếu Redis mất kết nối, một ứng dụng dùng Spring Session Data Redis có thể không tra được phiên để xác thực request. Không tự động “cho qua” mọi request nếu lookup session lỗi: như vậy biến outage thành bypass auth.

Chọn một chính sách rõ:

- Với endpoint cần authentication, thường **fail closed** khi không xác nhận được session hợp lệ.
- Với endpoint công khai, có thể tiếp tục phục vụ mà không phụ thuộc session nếu security policy cho phép.
- Với các dịch vụ cần availability cao, triển khai Redis HA và timeout phù hợp, cân nhắc tác động phải login lại.
- Không tự phát hành một session ID “dự phòng” trong memory rồi coi nó có cùng bảo đảm với Redis shared store.

Lỗi session store phải được phát hiện và đo lường, không gộp mọi Redis timeout thành “session expired” để làm mất dấu sự cố.

## 22. Kiểm thử mẫu ứng dụng trên nhiều instance

Một bài kiểm thử thực tế cần chứng minh cả **chia sẻ session** lẫn **giới hạn tích hợp**.

### 22.1. Thử login qua instance A, đọc trên B

1. Khởi chạy App A và App B với cùng Redis namespace và serializer.
2. Thực hiện login hợp lệ qua App A.
3. Lưu cookie jar của client test an toàn.
4. Gửi request authenticated sang App B với cùng cookie.
5. Xác nhận Spring Security trên B nhận được authentication hợp lệ.
6. Thay đổi một attribute session trên B.
7. Đọc lại trên A và quan sát trạng thái thống nhất theo flush/save mode.

Không dựa vào sticky session của load balancer trong bài thử này; cần ép request thực sự đi tới instance khác nhau để kiểm tra shared store.

### 22.2. Thử logout/revoke

1. Login, xác nhận cookie và session hợp lệ.
2. Gọi logout bằng phương thức và CSRF token đúng.
3. Gửi lại request tới một instance khác với cookie cũ.
4. Xác nhận request không được chấp nhận là authenticated.
5. Nếu có chức năng logout tất cả thiết bị, thử với nhiều session ID khác nhau và theo dõi thời gian revoke.

Đừng chỉ kiểm tra browser xóa cookie; cần xác nhận **server-side session** không còn được chấp nhận.

### 22.3. Thử TTL và inactivity

1. Cấu hình timeout ngắn trong test.
2. Login, đợi quá thời gian inactivity.
3. Gửi request mới với cookie cũ.
4. Xác nhận hệ thống yêu cầu xác thực lại.
5. Thử một request trong khoảng hợp lệ và kiểm tra session được refresh theo chính sách.

Đừng suy ra kết quả chỉ từ `TTL` trên Redis key nội bộ; kiểm tra hành vi HTTP thực.

### 22.4. Thử rolling deploy và serializer

1. Đăng nhập bằng phiên bản App v1.
2. Đọc cùng session bằng App v2 trong thời gian hai phiên bản cùng chạy.
3. Đảm bảo `SecurityContext` và các attribute cần thiết deserialize được.
4. Thử rollback về App v1 nếu kế hoạch triển khai cho phép.
5. Đánh giá chiến lược migration hoặc buộc re-login khi schema không tương thích.

### 22.5. Thử failover và lỗi Redis

1. Cho Redis primary failover trong môi trường thử nghiệm.
2. Theo dõi request login và request đã authenticated.
3. Kiểm tra session state có bị mất/stale không.
4. Thử revoke ngay gần thời điểm failover và xác nhận ranh giới bảo mật.
5. Kiểm tra timeout và phản hồi lỗi không biến thành bypass auth.

### 22.6. Thử concurrency

Gửi hai request cập nhật cùng một session attribute đồng thời. Quan sát kết quả theo repository mode đã chọn. Nếu nghiệp vụ yêu cầu atomic update, chuyển dữ liệu đó sang nguồn có kiểm soát concurrency thay vì coi session store tự giải quyết.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ dùng session memory khi có nhiều replica | Người dùng mất login khi request sang node khác | Spring Session Redis/shared store |
| Coi Spring Session là authentication provider | Bỏ qua xác thực/quyền | Dùng Spring Security/IdP đúng vai trò |
| Coi mọi HttpSession là đã đăng nhập | Truy cập trái phép khi session chỉ chứa dữ liệu tạm | Kiểm tra SecurityContext/authorization |
| Lưu toàn bộ object graph vào session | Redis memory cao, serializer lỗi | Lưu ID/DTO nhỏ |
| Chia sẻ cookie toàn domain không cần thiết | Mở rộng phạm vi cookie hijack | Cookie scope tối thiểu |
| Cho session ID vào URL/log | Lộ credential phiên | Cookie an toàn, không log secret |
| Logout chỉ xóa cookie | Session server có thể còn hiệu lực | Revoke/invalidate phía server |
| Chỉ dựa vào TTL khi tài khoản bị khóa | Phiên cũ có thể còn quyền | Revalidate hoặc revoke theo policy |
| Đặt Redis cache eviction policy cho session | Session bị xóa trước TTL | Memory budget và policy session phù hợp |
| Tự sửa Spring Session key bằng RedisTemplate | Hỏng index/expiry/security state | Dùng repository/HttpSession |
| Đổi serializer mà không migration | Phiên cũ không đọc được | Version/compatibility plan |
| Dựa tuyệt đối vào Redis expiration events | Listener offline có thể mất sự kiện | Reconcile/nguồn bền cho nghĩa vụ bắt buộc |
| Coi Sentinel/Cluster là persistence tuyệt đối | Session có thể mất/stale khi failover | Đánh giá durability và failover |
| Đọc session từ replica lag | Revoke có thể không thấy tức thời | Consistency policy cho auth |
| Đặt cart/stock/tài chính vào session | Không có transaction/consistency đúng | Nguồn nghiệp vụ riêng |
| Tin `@Transactional` bao cả DB và session Redis | Hai tài nguyên vẫn có thể commit lệch | Outbox/reconcile/source of truth |
| Trộn Servlet HttpSession với WebFlux WebSession | Sai abstraction và security filter | Chọn tích hợp theo stack |
| Dùng session để revoke JWT | JWT còn hợp lệ độc lập | Token revocation/IdP policy |
| Dùng local session registry cho giới hạn toàn cụm | Các instance đếm phiên khác nhau | Indexed repository/registry phù hợp |
| Gộp Redis outage thành expired session | Khó điều tra và có thể xử lý sai | Phân loại lỗi, fail-closed khi cần |

## 24. Cây quyết định khi thiết kế phiên đăng nhập

```text
Ứng dụng có trạng thái đăng nhập phía server?
                      |
                +-----+-----+
                |           |
               Có          Không
                |           |
                v           v
         Cần HttpSession?   Bearer token/stateless?
                |           |
                v           v
         Có nhiều replica?  Chọn token/IdP
                |           lifecycle riêng
           +----+----+
           |         |
          Có        Không
           |         |
           v         v
     Dùng shared   Local session có thể
     session store phù hợp khi chấp nhận
           |        hạn chế
           v
    Spring Session Data Redis
           |
           v
     Spring MVC hay WebFlux?
        +--+-----------+
        |              |
      MVC            WebFlux
        |              |
        v              v
    HttpSession      WebSession
        |              |
        +------+-------+
               |
               v
        Spring Security quản lý
        authentication/authorization
               |
               v
        Cookie và session ID an toàn
               |
               v
        TTL, serializer, namespace,
        Cluster/Sentinel, memory policy
               |
               v
       Cần logout tất cả thiết bị?
               |
          +----+----+
          |         |
         Có        Không
          |         |
          v         |
      Indexed repository/
      revocation policy
          |         |
          +----+----+
               |
               v
       Test nhiều replica, logout,
       timeout, failover và deploy
```

## 25. Kết luận

**Spring Session Data Redis** giúp ứng dụng Spring quản lý `HttpSession` ngoài bộ nhớ của từng instance, hỗ trợ chia sẻ phiên khi scale ngang, cấu hình thời gian sống và thực hiện logout/revoke qua một repository tập trung. Đây là một **mẫu ứng dụng** hữu ích khi triển khai login dựa trên session cookie với Spring Security.

Nhưng ranh giới tích hợp phải được giữ rõ:

1. **Spring Security xác thực và phân quyền; Spring Session lưu session; Redis lưu dữ liệu phiên.** Không dùng Redis session như một hệ thống identity provider.
2. **Session cookie là bearer secret.** Cần HTTPS, HttpOnly, Secure, SameSite và phạm vi cookie phù hợp; không log session ID.
3. **Session có TTL và giới hạn nhất quán.** Không coi session là database nghiệp vụ, không giả định cập nhật attribute giữa hai request đồng thời luôn an toàn.
4. **Logout và thu hồi quyền phải có hiệu lực theo chính sách bảo mật.** Không chỉ xóa cookie, không dựa mù vào expiration event hoặc replica stale.
5. **Redis HA/Cluster không phải transaction và durability tuyệt đối.** Failover, eviction, index và serializer phải được thử trong hạ tầng thực.
6. **Servlet và WebFlux khác abstraction.** Chọn `HttpSession` hoặc `WebSession` và integration tương ứng; không trộn tùy tiện.
7. **OAuth2/JWT có vòng đời riêng.** Xóa Spring Session không tự revoke access token tự chứa.

Một triển khai đáng tin cậy không chỉ cho thấy “đăng nhập qua App A, đọc được trên App B”. Nó còn phải chứng minh **logout có hiệu lực, session không bị lộ, timeout đúng chính sách, dữ liệu sống qua rolling deployment phù hợp và lỗi Redis không phá ranh giới xác thực**.

