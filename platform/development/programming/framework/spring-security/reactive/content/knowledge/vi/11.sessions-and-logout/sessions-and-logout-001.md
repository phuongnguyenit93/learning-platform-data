# WebSession, cookie phiên và sự khác biệt với HttpSession

> **Ngữ cảnh:** Spring Boot 3.3.x, Spring Framework 6.1.x, Spring Security 6.x, Java 17+, ứng dụng HTTP dùng **Spring WebFlux**. Trọng tâm là vòng đời phiên, cookie chứa mã phiên, sự khác biệt với `jakarta.servlet.http.HttpSession` và cách Spring Security lưu/đọc `SecurityContext` khi dùng phiên. Các phiên bản trong ví dụ chỉ phục vụ học tập; triển khai thật phải chọn bản Spring Boot/Spring Framework đã được vá bảo mật và còn được hỗ trợ.

## 1. Session là gì, cookie phiên giữ thứ gì?

Một **server-side session** là tập dữ liệu trạng thái mà server liên kết với các request của cùng một client. Ví dụ: giỏ hàng tạm, bước đang thực hiện trong một wizard, hoặc security context sau khi đăng nhập bằng form. Thông thường trình duyệt giữ một **session ID** trong cookie và gửi lại ID đó cho server:

```text
Lần 1: Browser                         WebFlux server
       POST /lab/cart  ----------------------> 
                         tạo WebSession; lưu cart
       <----------------------  Set-Cookie: SESSION=<opaque-id>; ...
       browser lưu cookie

Lần 2: Browser
       GET /lab/state
       Cookie: SESSION=<opaque-id>  --------->
                         tìm WebSession theo ID
       <----------------------  JSON có cart đã lưu
```

- Cookie thường chứa **ID tham chiếu**, **không phải toàn bộ dữ liệu Java trong session**. Dữ liệu session nằm phía server hoặc kho lưu trữ được cấu hình.
- Session ID là **bí mật mang tính bearer**: người có ID hợp lệ có thể giả mạo phiên nếu hệ thống không có lớp bảo vệ khác. Không log, gắn vào URL, gửi cho bên thứ ba, hoặc đưa vào response JSON để debug.
- Cookie không đồng nghĩa với đăng nhập. Một khách **chưa xác thực** vẫn có thể có `WebSession` chứa giỏ hàng; người đã xác thực bằng Basic/JWT chưa chắc dùng cookie phiên.
- Thời gian tồn tại của cookie trên browser và thời gian hết hạn session phía server có thể **khác nhau**. Cookie còn mà session đã hết hạn không làm dữ liệu cũ sống lại.

Trong Spring WebFlux, kiểu Java dùng cho phiên là:

```java
import org.springframework.web.server.WebSession;
```

Còn trong Spring MVC/Servlet:

```java
import jakarta.servlet.http.HttpSession;
```

Hai API phục vụ cùng nhu cầu trạng thái giữa request, nhưng **không thể dùng thay thế trực tiếp** trong controller, filter hay repository của hai web stack.

## 2. WebSession hoạt động như thế nào?

`org.springframework.web.server.WebSession` là interface của Spring Framework cho session trong WebFlux. Nó là thành phần của **Spring WebFlux**, không riêng Spring Security. Các API chính:

| API | Ý nghĩa |
|---|---|
| `getId()` | Đọc ID hiện tại của session; không xuất ID này ra log hoặc JSON ngoài nhu cầu quản trị được bảo vệ |
| `getAttributes()` | `Map<String,Object>` chứa dữ liệu phiên |
| `getAttribute("key")` | Đọc thuộc tính theo tên, có thể trả `null` |
| `getRequiredAttribute("key")` | Đọc thuộc tính bắt buộc; ném lỗi nếu không có |
| `start()` | Đánh dấu bắt đầu phiên tường minh; `void` |
| `isStarted()` | Cho biết session được bắt đầu tường minh hoặc ngầm do thêm attribute |
| `save()` | Trả `Mono<Void>`, lưu session; framework thường tự gọi khi response sắp commit |
| `changeSessionId()` | Trả `Mono<Void>`, tạo ID mới và cập nhật nơi lưu |
| `invalidate()` | Trả `Mono<Void>`, vô hiệu hóa phiên và xóa trạng thái lưu |
| `getMaxIdleTime()` / `setMaxIdleTime(Duration)` | Đọc/đặt thời gian rỗi tối đa của session |
| `getCreationTime()` / `getLastAccessTime()` / `isExpired()` | Thông tin vòng đời và hết hạn |

### 2.1 Lấy session không nhất thiết bắt đầu session

Trên WebFlux, tham số controller `WebSession session` **không tự ép tạo phiên được lưu**. Khi gọi `ServerWebExchange.getSession()`, bạn nhận `Mono<WebSession>`; request chưa có session hợp lệ có thể được cấp một đối tượng WebSession **chưa started**.

```java
@GetMapping("/peek")
Mono<Boolean> peek(WebSession session) {
    return Mono.just(session.isStarted());
}
```

Đoạn method này là ví dụ rời, chưa có class/imports đầy đủ. Khi chỉ đọc `isStarted()` hoặc `getAttribute(...)`, không bắt buộc có `Set-Cookie` mới. Tuy nhiên **filter khác** (ví dụ authentication, CSRF hoặc ứng dụng) có thể đồng thời thay đổi session; không dùng quy tắc “GET chắc chắn không bao giờ có cookie” làm hợp đồng hệ thống.

Session bắt đầu khi:

1. Gọi `session.start()` tường minh.
2. Thêm thuộc tính vào `session.getAttributes()`, ví dụ `put("cart", ...)`; session được bắt đầu ngầm.

Sau đó `WebSessionManager`/`WebSessionStore` lo việc persist session trong vòng đời xử lý request. Thường **không cần tự gọi `save()` trong controller**, vì việc lưu diễn ra trước khi response được commit. Nếu đã bắt đầu ghi response quá sớm hoặc dùng flow tùy chỉnh không đúng vòng đời, phải xem lại API cụ thể thay vì chèn `block()`.

### 2.2 Các API bất đồng bộ thật sự cần được kết hợp vào pipeline

`changeSessionId()` và `invalidate()` trả `Mono<Void>`. Không viết:

```java
session.invalidate(); // Chỉ tạo Publisher, chưa bảo đảm được thực thi
return Mono.just("logged out");
```

Trong Reactor, publisher cần có subscription. Handler phải **trả về publisher có nối thao tác vào flow**:

```java
return session.invalidate()
    .thenReturn("session invalidated");
```

Đây là mảnh code trong method trả `Mono<String>`. Spring WebFlux sẽ subscribe publisher mà handler trả về. **Không tự `subscribe()` và không gọi `block()`** trong controller WebFlux để chờ vô hiệu hóa session.

### 2.3 Session và request có vòng đời khác nhau

- `ServerWebExchange.getAttributes()` chứa attributes của **một request/exchange**, không giữ qua request tiếp theo.
- `WebSession.getAttributes()` chứa attributes của **phiên**, tồn tại giữa nhiều request khi có session ID và store phù hợp.
- `ReactiveSecurityContextHolder` cung cấp `SecurityContext` cho **chuỗi Reactor hiện tại**. Việc lưu nó qua nhiều request là trách nhiệm `ServerSecurityContextRepository`, không phải cứ có Reactor Context là sẽ có session.
- `@SessionAttributes` trên controller WebFlux liên quan đến model attributes và `SessionStatus`; không giống thao tác trực tiếp với `WebSession.getAttributes()`. Xóa model attributes bằng `SessionStatus.setComplete()` **không mặc nhiên thay cho việc invalidate toàn bộ session**.

## 3. CookieWebSessionIdResolver và WebSessionManager

Các lớp liên quan trong Spring WebFlux:

```text
HTTP request
    |
    v
DefaultWebSessionManager
    |
    +--> WebSessionIdResolver
    |       +--> CookieWebSessionIdResolver
    |               đọc Cookie: SESSION=<id>
    |
    +--> WebSessionStore
    |       +--> InMemoryWebSessionStore (mặc định cơ bản)
    |       +--> store tích hợp Spring Session/Redis/... (nếu cấu hình)
    |
    v
WebSession
    |
    v
handler / WebFilter / Spring Security
    |
    v
lưu phiên khi response được commit
    |
    +--> Set-Cookie: SESSION=<id> khi cần
```

`CookieWebSessionIdResolver` mặc định sử dụng cookie tên **`SESSION`**. Đây là **mặc định của WebFlux**, không phải tiêu chuẩn bắt buộc; ứng dụng có thể đổi tên thông qua resolver hoặc Spring Boot configuration. Trong nhiều ứng dụng Servlet, cookie container thường tên **`JSESSIONID`**. Vì vậy, dùng `JSESSIONID` để suy đoán mọi ứng dụng WebFlux đang có phiên là sai.

`WebSessionIdResolver` chỉ chịu trách nhiệm đọc, ghi hoặc làm hết hạn **session ID phía client**. `WebSessionStore` chịu trách nhiệm lưu/tra cứu dữ liệu phía server. Thay cookie name không đồng nghĩa chuyển dữ liệu session sang Redis.

### 3.1 Mẫu HTTP: Set-Cookie và Cookie

Ví dụ headers minh họa (giá trị ID đã được thay bằng ký hiệu):

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-id>; Path=/; HttpOnly; SameSite=Lax

GET /lab/state HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
```

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò | Điều không làm được |
|---|---|---|
| `HttpOnly` | Hạn chế JavaScript truy cập cookie qua `document.cookie` | Không tự ngăn CSRF hay mọi kiểu XSS/đánh cắp phiên |
| `Secure` | Chỉ gửi cookie qua kết nối an toàn theo quy tắc browser | Không thay thế TLS termination và proxy configuration đúng |
| `SameSite=Lax/Strict/None` | Hạn chế một số kiểu gửi cookie trong ngữ cảnh cross-site | Không thay thế CSRF token/kiểm tra Origin cho mọi ứng dụng |
| `Path` | Giới hạn đường dẫn browser gửi cookie | Không tạo ranh giới bảo mật phía server giữa các endpoint |
| `Domain` | Giới hạn phạm vi domain/subdomain của cookie | Domain quá rộng có thể tăng nguy cơ lộ hoặc session fixation qua subdomain |
| `Max-Age` | Thời gian browser giữ cookie | Không bảo đảm session backend chưa hết hạn hoặc chưa bị thu hồi |

Nếu dùng `SameSite=None` theo trình duyệt hiện đại, thường cần `Secure`. Với triển khai HTTPS thật, bật `Secure`; khi đang chạy `http://localhost` cho bài thực hành, header sẽ khác. Không đưa cookie phiên vào localStorage như một bản sao chỉ để debug.

### 3.2 Tùy chỉnh cookie bằng Spring Boot 3.3

Với ứng dụng reactive dùng Spring Boot 3.3, các properties phổ biến:

**src/main/resources/application.yml**

```yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
```

`server.reactive.session.timeout` là thời gian rỗi của WebSession; các cài đặt cookie dùng namespace `server.reactive.session.cookie.*`. **Không dùng `server.servlet.session.*` để mong đổi cấu hình WebFlux.**

Trong production dùng HTTPS, cân nhắc thêm:

```yaml
server:
  reactive:
    session:
      cookie:
        secure: true
```

Đây là **cấu hình bổ sung**, không nhất thiết phù hợp với localhost HTTP. Nếu TLS kết thúc ở reverse proxy/load balancer, cần kiểm soát forwarding headers, scheme và nơi phát cookie để chắc chắn `Secure`/Domain/Path khớp domain thật.

### 3.3 Tùy chỉnh trực tiếp bằng WebSessionIdResolver

Khi cần điều khiển rõ cách tạo cookie (ví dụ tên khác), có thể cung cấp bean:

```java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(builder ->
        builder.path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));
    return resolver;
}
```

Đây là **đoạn cấu hình minh họa**, cần đặt vào lớp `@Configuration`, import `@Bean`, `WebSessionIdResolver` và `CookieWebSessionIdResolver`. Khi dùng bean này, tên cookie không còn là `SESSION` và `secure(true)` chỉ phù hợp khi client truy cập HTTPS. Đừng khai báo đồng thời cơ chế tùy chỉnh không hiểu thứ tự ưu tiên rồi mặc định mọi property Boot vẫn ghi đè bean của mình.

## 4. WebSession khác HttpSession ở đâu?

| Khía cạnh | WebFlux: `WebSession` | Servlet/MVC: `HttpSession` |
|---|---|---|
| Package | `org.springframework.web.server.WebSession` | `jakarta.servlet.http.HttpSession` |
| Môi trường | Reactor/WebFlux; có thể chạy trên Netty | Servlet API và container như Tomcat/Jetty |
| Lấy session từ request | `ServerWebExchange.getSession()` trả `Mono<WebSession>`; controller cũng có thể inject `WebSession` | `HttpServletRequest.getSession()` trả `HttpSession` đồng bộ |
| Khi truy cập session lần đầu | Việc lấy đối tượng chưa buộc start/persist; thêm attribute hoặc gọi `start()` mới bắt đầu | `getSession()` thường tạo nếu chưa có; `getSession(false)` không tạo |
| Thuộc tính | `getAttributes().put(...)`, `getAttribute(...)` | `setAttribute(...)`, `getAttribute(...)` |
| Lưu/thay ID/hủy | `save()`, `changeSessionId()`, `invalidate()` trả `Mono<Void>` (trừ `start`) | `invalidate()` trả `void`; đổi ID thường qua `HttpServletRequest.changeSessionId()` |
| Cookie mặc định thông thường | `SESSION` của `CookieWebSessionIdResolver` | `JSESSIONID` của nhiều Servlet container |
| Kho lưu | `WebSessionStore`; mặc định có `InMemoryWebSessionStore`, có thể tích hợp Spring Session | Session do Servlet container hoặc Spring Session/`SessionRepository` quản lý |
| Ngữ cảnh bảo mật | `ReactiveSecurityContextHolder` và `ServerSecurityContextRepository` | `SecurityContextHolder` và Servlet `SecurityContextRepository` |
| Transaction/thread | Không đồng nghĩa request gắn một thread suốt vòng đời | Code Servlet truyền thống hay dựa mô hình thread-per-request |

**Ví dụ Servlet truyền thống** (không dùng trong WebFlux):

```java
// Mảnh mã MVC/Servlet, không thuộc demo WebFlux:
@GetMapping("/cart")
String cart(HttpServletRequest request) {
    HttpSession session = request.getSession();
    session.setAttribute("cart", "book");
    return (String) session.getAttribute("cart");
}
```

**Ví dụ WebFlux tương ứng** (chỉ là method minh họa):

```java
@GetMapping("/cart")
Mono<String> cart(WebSession session) {
    session.getAttributes().put("cart", "book");
    return Mono.just(session.getAttribute("cart"));
}
```

Mã WebFlux có thể trông ngắn hơn nhưng không phải bởi việc đọc `Map` tự nó là non-blocking I/O: việc lấy session từ `ServerWebExchange` và lưu vào một repository reactive mới là phần có thể tương tác bất đồng bộ. **Không thay `HttpSession` bằng `WebSession` rồi gọi repository JDBC/JPA đồng bộ trên event-loop**; phải đặt ranh giới blocking phù hợp.

## 5. Demo Java 17+ đầy đủ: tạo, đọc, đổi ID và hủy WebSession

Ví dụ dưới đây là **phòng thực hành về cơ chế session**, không phải hệ thống quản lý phiên production. Ứng dụng dùng Spring Security nhưng cho phép truy cập các endpoint `/lab/**` mà không cần đăng nhập để thấy rằng **session != authenticated user**.

Trong mẫu này **giữ CSRF protection mặc định**. Vì vậy mọi `POST`/`DELETE` qua browser/client phải có CSRF token hợp lệ. Bài test dùng Spring Security Test để gửi token; lệnh curl không có token được dùng để kiểm tra phản hồi bị từ chối.

### 5.1 Cấu trúc và dependency

```text
websession-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/session/WebSessionApplication.java
  src/main/java/demo/session/SecurityConfiguration.java
  src/main/java/demo/session/SessionController.java
  src/test/java/demo/session/SessionFlowTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'websession-lab'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.session'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web`; mục tiêu là **reactive** web stack. `spring-security-test` giúp mô phỏng CSRF an toàn trong `WebTestClient`. Spring Boot 3.3.13 được chọn để thống nhất API trong ví dụ; không xem đây là phiên bản khuyến nghị triển khai production ở thời điểm hiện tại.

**src/main/resources/application.yml**

```yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
```

Ở localhost HTTP, ví dụ không ép cookie `secure: true` để dễ thử; **phải bật Secure trên HTTPS production**. Trong bản triển khai khác, tên cookie có thể không phải `SESSION`.

### 5.2 Spring Boot application

**src/main/java/demo/session/WebSessionApplication.java**

```java
package demo.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSessionApplication.class, args);
    }
}
```

### 5.3 SecurityWebFilterChain

**src/main/java/demo/session/SecurityConfiguration.java**

```java
package demo.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/lab/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Đọc cấu hình:

- `/lab/**` công khai để có thể thao tác session ẩn danh; đây là **ngoại lệ chỉ dành cho môi trường học tập**. Trong ứng dụng thật, không để khách tùy ý ghi trạng thái nhạy cảm.
- `.anyExchange().authenticated()` bảo vệ các route khác, ví dụ `/secure/me`.
- `httpBasic(...)` hỗ trợ API cần danh tính thật; Basic và cookie `SESSION` **là hai cơ chế khác nhau**, không thay thế nhau.
- `formLogin` tắt chỉ để curl nhận phản hồi Basic thay vì redirect trang đăng nhập.
- **Không gọi `csrf(csrf -> csrf.disable())`**: CSRF vẫn bảo vệ các HTTP method thay đổi trạng thái. Đừng nghĩ `permitAll()` tự loại bỏ yêu cầu CSRF.

### 5.4 Controller: dùng WebSession chứ không dùng HttpSession

**src/main/java/demo/session/SessionController.java**

```java
package demo.session;

import java.security.Principal;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    public record CartChange(String item) {}
    public record SessionState(boolean started, String cart) {}
    public record Ack(String status) {}

    private SessionState view(WebSession session) {
        String item = session.getAttribute("lab.cart");
        return new SessionState(session.isStarted(), item);
    }

    @GetMapping("/lab/state")
    public Mono<SessionState> state(WebSession session) {
        // Chỉ đọc: không tự tạo cart và không gọi start().
        return Mono.just(view(session));
    }

    @PostMapping("/lab/cart")
    public Mono<SessionState> addCart(
            WebSession session, @RequestBody CartChange change) {
        if (change.item() == null || change.item().isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "item must not be blank"));
        }

        // Ghi attribute -> WebSession được bắt đầu ngầm.
        session.getAttributes().put("lab.cart", change.item());
        return Mono.just(view(session));
    }

    @PostMapping("/lab/rotate")
    public Mono<SessionState> rotate(WebSession session) {
        if (!session.isStarted()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.CONFLICT, "no started session"));
        }

        // Bắt buộc đưa Mono<Void> vào chuỗi trả về.
        return session.changeSessionId()
            .then(Mono.fromSupplier(() -> view(session)));
    }

    @DeleteMapping("/lab/state")
    public Mono<Ack> invalidate(WebSession session) {
        return session.invalidate()
            .thenReturn(new Ack("invalidated"));
    }

    @GetMapping("/secure/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user: " + principal.getName());
    }
}
```

**Vì sao ví dụ không trả `session.getId()` trong JSON?** ID phiên là credential mang tính bearer, không phải thông tin trạng thái nên hiển thị cho mọi khách. Để kiểm thử ID được đổi, hãy so sánh giá trị cookie trong HTTP client/test có kiểm soát; không tạo endpoint xuất ID ra công khai.

**Vì sao `view(session)` chỉ đọc?** GET `/lab/state` được giữ không có side-effect nghiệp vụ. `POST /lab/cart` mới tạo/đổi cart; `POST /lab/rotate` đổi ID; `DELETE /lab/state` hủy phiên. Dù trong lab tất cả được `permitAll`, HTTP unsafe methods vẫn phải có CSRF token hợp lệ.

### 5.5 Chạy và quan sát HTTP

Ở thư mục dự án, dùng JDK 17+ và một Gradle tương thích với Spring Boot 3.3:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper tương thích, dùng `./gradlew bootRun`; Windows PowerShell/cmd có thể dùng `gradlew.bat bootRun`.

**Đọc session chưa tạo attribute**:

```bash
curl -i http://localhost:8080/lab/state
```

Kết quả chính kỳ vọng:

```json
{
  "started": false,
  "cart": null
}
```

Không dựa vào việc thiếu `Set-Cookie` trong mọi môi trường: các WebFilter khác có thể chạm vào session. Điều chắc chắn từ API là **bản thân lấy WebSession và đọc thuộc tính không bắt buộc start**.

**Thử thao tác POST mà không có CSRF token**:

```bash
curl -i -X POST http://localhost:8080/lab/cart \
  -H "Content-Type: application/json" \
  --data '{"item":"book"}'
```

Vì cấu hình đã giữ CSRF mặc định, request không có token hợp lệ được kỳ vọng **403 Forbidden** dù `/lab/**` có `permitAll()`. Đây là minh họa rằng **authorization không thay CSRF protection**. Để thực sự ghi cart, dùng test `WebTestClient` ở mục tiếp theo hoặc triển khai quy trình cấp/gửi token CSRF đúng chuẩn cho browser.

**Protected endpoint không có credential**:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/secure/me
```

Kỳ vọng **401 Unauthorized**, khác với `403` do thiếu CSRF khi POST. Nếu muốn kiểm tra Basic đã đăng nhập, dùng user/password phát triển mà Spring Boot cung cấp (nếu auto-configuration tạo user); không cho rằng cookie giỏ hàng tự cấp quyền vào `/secure/me`.

### 5.6 Kiểm thử tự động với WebTestClient

**src/test/java/demo/session/SessionFlowTest.java**

```java
package demo.session;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class SessionFlowTest {

    @Autowired
    WebTestClient client;

    @Test
    void readingDoesNotRequireStartingASession() {
        client.get().uri("/lab/state")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(false);
    }

    @Test
    void missingCsrfTokenIsRejected() {
        client.post().uri("/lab/cart")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new SessionController.CartChange("book"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void cartPersistsThroughCookieThenSessionIsInvalidated() {
        var stored = client.mutateWith(csrf())
            .post().uri("/lab/cart")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new SessionController.CartChange("book"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(SessionController.SessionState.class)
            .returnResult();

        ResponseCookie cookie =
            stored.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie);

        // Request thứ hai tự gửi cookie, không phụ thuộc client
        // có tự lưu cookie hay không.
        client.get().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(true)
            .jsonPath("$.cart").isEqualTo("book");

        client.mutateWith(csrf())
            .delete().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("invalidated");

        // ID cũ không còn truy cập được cart đã hủy.
        client.get().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(false);
    }

    @Test
    void cookieDoesNotCountAsAuthentication() {
        client.get().uri("/secure/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Ở file test trên, lệnh static import được xuống dòng giữa các token của tên package cho dễ đọc; đây là **cú pháp Java hợp lệ** (whitespace được cho phép giữa các token của qualified name). Nếu áp dụng quy ước format import một dòng, có thể viết như sau:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Dùng bản import một dòng sẽ dễ sao chép nhất. `client.mutateWith(csrf())` thuộc Spring Security Test, không phải cách browser ở production tự lấy token; client production phải có token CSRF thật do server cấp và gửi lại qua header/field đúng chính sách.

Chạy:

```bash
gradle test
```

Với cấu hình và dependency đúng, kỳ vọng **4 test method** chứng minh: đọc không ép start, POST thiếu CSRF bị từ chối, cart tồn tại giữa các request qua cookie rồi bị hủy, và route bảo vệ từ chối khách không credential. Đây là **kỳ vọng được rà soát từ code**, không phải báo cáo build thực tế. Việc dùng `WebTestClient` mock server khác với kiểm thử end-to-end qua trình duyệt/reverse proxy; môi trường thật vẫn cần test cookie flags, SameSite, TLS và logout.

### 5.7 Mở rộng: kiểm tra đổi session ID

Sau khi đã tạo session bằng `POST /lab/cart` có CSRF hợp lệ, gửi:

```http
POST /lab/rotate HTTP/1.1
Cookie: SESSION=<old-id>
X-CSRF-TOKEN: <valid-csrf-token>
```

`session.changeSessionId()` tạo ID mới trong store; `WebSessionManager`/resolver sẽ phản ánh ID tương ứng cho client theo vòng đời response. Dùng client test có quyền xem cookie để so sánh old/new ID; **không log ID thật** vào tài liệu hoặc telemetry. Nếu đang dùng CSRF token lưu trong session, cần giữ/cập nhật cookie và token theo luồng đúng trước request tiếp theo.

## 6. Spring Security dùng WebSession để làm gì?

`WebSession` là hạ tầng HTTP; Spring Security có tầng riêng để bảo quản `SecurityContext`:

- `ServerSecurityContextRepository` là giao diện reactive với `load(ServerWebExchange)` và `save(ServerWebExchange, SecurityContext)`.
- `WebSessionServerSecurityContextRepository` lưu `SecurityContext` trong `WebSession`, khi lưu context còn có cơ chế **đổi session ID** nhằm chống session fixation.
- `NoOpServerSecurityContextRepository` không persist security context qua request. Phù hợp với một số API thật sự stateless đã xác thực từng request bằng bearer token đúng chuẩn.
- `ReactiveSecurityContextHolder` đặt/truy cập security context trong **Reactor Context của một subscription**. Đó là cơ chế truyền danh tính trong request, không đồng nghĩa lưu thông tin người dùng sang HTTP request sau.

**Phải phân biệt hai nội dung có thể cùng nằm trong một WebSession:**

```text
WebSession (store phía server)
  ├── "lab.cart"             -> "book"                  (state ứng dụng)
  ├── Spring Security context -> Authentication/User... (nếu repo lưu)
  └── các attributes khác được hệ thống thêm

Cookie SESSION=<id>          -> chỉ định danh session trong store
Reactor Context              -> cung cấp SecurityContext cho pipeline đang chạy
```

Một session giỏ hàng có thể được tạo bởi khách chưa đăng nhập. Sự tồn tại của cookie **không bảo đảm** có `SecurityContext` hợp lệ trong session; chỉ các authentication mechanism và repository đã cấu hình mới quyết định liệu đăng nhập có được nhớ giữa request.

### 6.1 Form login, Basic và bearer token không vận hành y hệt nhau

| Kiểu xác thực | Cookie/phiên thường đóng vai trò gì? | Điều cần kiểm tra |
|---|---|---|
| Form login + browser | Có thể persist `SecurityContext` trong `WebSession` để các request sau không phải gửi lại password | Cấu hình repository, CSRF, session fixation, logout |
| HTTP Basic | Client thường gửi username/password ở mỗi request | Đừng nghĩ cookie cart tương đương credential; persistence tùy chain |
| Bearer JWT | Client gửi token; resource server kiểm chữ ký, issuer, audience, quyền theo policy | Không tự tạo login session; tránh phối hợp cookie không cần thiết |
| OAuth2 Login/OIDC | Có thể cần session cho quá trình login, state/nonce và lưu xác thực | Cấu hình authorized client, context và CSRF đúng mô hình |
| Guest/anonymous | Có thể có session state như cart nhưng không có danh tính đã xác minh | Kiểm tài nguyên public, không cấp quyền dựa vào cookie |

Không nên “chữa” lỗi 401 bằng cách tạo một `WebSession` mới. Session là nơi *lưu trạng thái*, không phải bộ xác thực credential.

### 6.2 Lưu security context bằng repository reactive

**Đoạn cấu hình minh họa (thay thế, không thêm song song với bean demo ở mục 5):**

```java
@Bean
SecurityWebFilterChain securityWithSession(ServerHttpSecurity http) {
    var repository = new WebSessionServerSecurityContextRepository();

    return http
        .securityContextRepository(repository)
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đoạn này cần `@Configuration`, imports `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, `WebSessionServerSecurityContextRepository` và `@Bean`; không phải Java độc lập. Nó đặt một repository lưu `SecurityContext` vào WebSession để phù hợp flow stateful. Cần có nguồn người dùng và thiết kế các route login/logout. Tự khai báo chain không tự tạo hệ thống account của production.

Đối với một **resource server stateless** đúng nghĩa, có thể dùng `NoOpServerSecurityContextRepository`; nhưng chỉ làm khi xác thực token thật sự xảy ra trên mỗi request và các thành phần khác không dựa vào server-side session. Không bật `NoOp` chỉ để giảm số lượng cookie rồi làm hỏng flow form/OAuth2 login.

## 7. Logout, invalidate và session fixation

### 7.1 Ba thao tác dễ nhầm

1. **Xóa/không persist SecurityContext:** đưa người dùng về trạng thái chưa đăng nhập trong tương lai, tùy authentication scheme và repository.
2. **`WebSession.invalidate()`:** vô hiệu hóa toàn bộ phiên ở store, gồm cả cart và attributes khác.
3. **Xóa cookie trên browser:** browser ngừng gửi ID cũ; **không tự bảo đảm đã hủy state phía server** nếu server chưa invalidate.

Một triển khai logout muốn kết thúc toàn bộ phiên của người dùng thường phải xét **cả security context lẫn WebSession**, đặc biệt khi ứng dụng có dữ liệu khác lưu chung trong session.

Spring Security reactive có `SecurityContextServerLogoutHandler` để loại bỏ security context và `WebSessionServerLogoutHandler` để invalidate WebSession. Có thể kết hợp:

```java
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

// Mảnh cấu hình trong SecurityWebFilterChain bean:
var logoutHandler = new DelegatingServerLogoutHandler(
    new SecurityContextServerLogoutHandler(),
    new WebSessionServerLogoutHandler());

http.logout(logout -> logout.logoutHandler(logoutHandler));
```

Đoạn này **chưa phải bean hoàn chỉnh**: còn cần authorization, login mechanism và `build()`. Trên một web app dùng CSRF, logout qua POST cần CSRF token hợp lệ theo cấu hình. Ngoài ra, logout cục bộ không tự thu hồi access token đã phát ra hoặc đăng xuất tại Identity Provider bên ngoài.

### 7.2 Chống session fixation

**Session fixation** xảy ra nếu kẻ tấn công khiến nạn nhân dùng một ID session do attacker biết, sau đó nạn nhân đăng nhập và ID vẫn không đổi. Khi đó ID đã biết có thể trở thành chìa khóa truy cập phiên đã xác thực.

- Sau khi login thành công và security context được lưu, `WebSessionServerSecurityContextRepository` có hành vi đổi ID phiên theo API của Spring Security để giảm nguy cơ này.
- `WebSession.changeSessionId()` là primitive của WebFlux để chủ động tạo ID mới. Nó **không tự thay user hoặc xóa attributes**.
- Không cho session ID trong URL/query string, không dùng Domain cookie quá rộng, không để subdomain không đáng tin ghi đè cookie.
- Cần nâng cấp bản Spring Framework đã được vá. Các phiên bản cũ có thể tồn tại lỗ hổng session fixation; đừng xem “đã gọi `changeSessionId()`” là lý do không cần cập nhật framework.

**Lưu ý thời điểm:** tài liệu và advisory bảo mật thay đổi theo phiên bản. Chẳng hạn advisory **CVE-2026-41839** của Spring Framework công bố ngày 08/06/2026 nêu một trường hợp session fixation/escalation trong WebFlux trên một số bản 6.1/6.2/7.0; trước production phải đối chiếu các version bị ảnh hưởng và phiên bản vá tại https://spring.io/security/cve-2026-41839/. Ví dụ Spring Boot 3.3.13 trong bài phục vụ học cú pháp, **không phải baseline bảo mật khuyến nghị cho năm 2026**.

## 8. Cookie security, CSRF và giới hạn phiên

### 8.1 CSRF vẫn quan trọng khi browser gửi cookie tự động

Nếu browser tự gửi `Cookie: SESSION=...` trên request POST, một trang ác ý có thể cố kích hoạt thay đổi trạng thái thay người dùng. `HttpOnly` và `Secure` **không giải quyết đầy đủ** kiểu tấn công này. Cần CSRF protection theo flow có cookie/session (hoặc kiến trúc xác thực khác không phụ thuộc credential tự động gửi).

Trong demo, `POST /lab/cart` không có CSRF token bị 403 dù `permitAll()`; việc này thể hiện policy có hai lớp. Với SPA, cần cơ chế cấp token CSRF phù hợp, gửi token qua header và quản lý rotation/renewal sau đăng nhập/logout.

Không vô hiệu hóa toàn bộ CSRF để “sửa 403” trong ứng dụng dùng session cookie cho xác thực. Nếu API thuần bearer token và không có cookie/session credential, việc đánh giá CSRF có thể khác, nhưng phải dựa trên mô hình threat thực tế.

### 8.2 Expiration phía browser và server

- `WebSession.maxIdleTime` là số thời gian session được phép không hoạt động trước khi hết hạn.
- Cookie `Max-Age` là thời gian browser lưu cookie. Cookie hết hạn có thể khiến client mất khả năng truy cập phiên dù dữ liệu chưa được dọn; cookie còn tồn tại không gia hạn session đã hết hạn phía server.
- `CookieWebSessionIdResolver` mặc định có thể dùng cookie theo phiên trình duyệt (không `Max-Age` cố định). Các ứng dụng có thể chọn persistent cookie nhưng phải xem xét rủi ro.
- Khi session server-side hết hạn hoặc bị invalidate, request có cookie cũ phải được coi như không có session hợp lệ; tuyệt đối không tái tạo quyền từ việc thấy cookie tên `SESSION`.

Đừng đồng nhất `maxIdleTime` với thời gian tuyệt đối kể từ lúc đăng nhập. Với yêu cầu bảo mật cao, có thể cần **absolute session lifetime** hoặc giới hạn reauthentication riêng, không chỉ idle timeout.

### 8.3 Các điều kiện ở reverse proxy và domain

- Cấu hình HTTPS và `Secure` nhất quán từ browser đến điểm TLS termination.
- Cẩn thận với `Domain=.example.com` trên hệ sinh thái có subdomain ít đáng tin; ưu tiên host-only cookie khi không có lý do chia phiên.
- Hạn chế cookie `Path` và tránh trùng tên giữa các ứng dụng trên cùng host. Đổi tên cookie không tự cô lập dữ liệu nếu Domain/Path và backend store cấu hình sai.
- Kiểm tra SameSite, CORS, CSRF, forwarding headers, cookie clearing trong các thử nghiệm trình duyệt thật.
- Không dump session cookie vào access log, error log, tracing span, ảnh chụp màn hình hoặc công cụ analytics.

## 9. In-memory WebSession và Spring Session phân tán

### 9.1 Mặc định dễ dùng nhưng không phù hợp mọi kiến trúc

`InMemoryWebSessionStore` lưu phiên trong bộ nhớ process. Điều này phù hợp demo hoặc ứng dụng đơn giản, nhưng nếu triển khai nhiều pod/node:

```text
Client có SESSION=id
      |
      +--> Pod A: có session id trong memory -> cart có dữ liệu
      |
      +--> Pod B: không có id trong memory -> không thấy cart
```

Load balancer có thể cấu hình sticky session nhưng đây không phải thay thế hoàn toàn cho kho phiên bền vững khi pod restart, scale hoặc failover. Cần đánh giá TTL, dung lượng, số phiên và xử lý hết hạn.

### 9.2 Spring Session thay persistence layer

**Spring Session** hỗ trợ tích hợp với `WebSession` bằng `WebSessionManager` và `ReactiveSessionRepository`, ví dụ store được hỗ trợ bởi Redis. Khi cấu hình đúng, nhiều instance có thể đọc cùng dữ liệu phiên và giảm phụ thuộc vào bộ nhớ của từng node.

Ví dụ **mảnh cấu hình định hướng**, không phải dự án chạy độc lập:

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

Dùng phiên bản dependency tương thích với Spring Boot và Spring Session mà dự án chọn; cần Redis server, cấu hình kết nối bảo mật, timeout, serialization, key namespace và chính sách vận hành. Với Spring Session reactive có thể dùng `@EnableRedisWebSession` để bật WebSession backing bằng Redis khi chủ động quản lý cấu hình. Tránh đặt annotation này cùng auto-configuration không hiểu cơ chế back off.

**Lưu ý quan trọng:** Spring Session JDBC truyền thống dành cho `HttpSession`/Servlet không làm JDBC repository tự trở thành **ReactiveSessionRepository** của WebFlux. Với reactive session, cần chọn integration hỗ trợ reactive store theo tài liệu tương ứng; không tự bọc một repository blocking rồi cho rằng đủ cho tải lớn.

### 9.3 Mặt trái của phân tán

- Store Redis/network có thể chậm hoặc không sẵn sàng, dẫn đến lỗi đọc/ghi phiên; cần timeout, retry có giới hạn và fail closed khi liên quan xác thực.
- Session attributes phải có chiến lược serialization/versioning, không tùy tiện đưa entity JPA, `HttpServletRequest`, đối tượng mang connection, secret hoặc dữ liệu quá lớn vào Redis.
- Xóa phiên/log out cần tác dụng ở mọi instance; kiểm tra sự nhất quán và behavior khi client đang có nhiều request đồng thời.
- Sử dụng monitoring cho active sessions, expired sessions, error rate, latency store, dung lượng dữ liệu; bảo vệ Redis bằng quyền mạng, auth, TLS và backup theo mô hình rủi ro.

## 10. Những lỗi thường gặp

| Hiểu sai/cấu hình lỗi | Hậu quả | Cách sửa |
|---|---|---|
| “Ứng dụng WebFlux phải dùng `HttpSession` vì có cookie” | Lẫn Servlet và reactive API | Dùng `WebSession` và `ServerWebExchange` |
| “Gọi `getSession()` luôn tạo cookie” | Tạo giả định sai về request không làm gì | Kiểm tra `isStarted`, cơ chế ghi attribute và filter khác |
| “`Mono.just(session.invalidate())` là đủ” | Publisher chưa được compose đúng và có thể không chạy | `return session.invalidate().thenReturn(...)` |
| “Cookie `SESSION` chứa cả user/cart” | Ngộ nhận dữ liệu nằm trên browser | Cookie chứa session ID; dữ liệu do store phía server quản lý |
| “`JSESSIONID` là cookie mặc định WebFlux” | Không tìm thấy session | Kiểm tra `CookieWebSessionIdResolver` và properties Boot |
| “Có cookie là đã login” | Gán quyền trái phép cho guest cart | Kiểm `Authentication` và policy của Security chain |
| “`permitAll` vô hiệu hóa CSRF” | POST/DELETE bị 403, hoặc tắt CSRF bừa | Thực hiện đúng CSRF token flow |
| “Có `HttpOnly` là chặn hết CSRF” | Vẫn có request cross-site dùng cookie | Dùng CSRF, SameSite và threat model phù hợp |
| “`secure=true` trên localhost HTTP vẫn hoạt động y hệt” | Cookie không được gửi theo dự kiến | Phân biệt môi trường HTTP test và HTTPS production |
| “Xóa cookie là đã logout hoàn toàn” | Session backend/token vẫn hợp lệ | Invalidate phía server; xóa SecurityContext; xử lý token/IdP khi cần |
| “`invalidate()` và `changeSessionId()` giống nhau” | Dữ liệu cần xóa còn nguyên | ID rotation giữ session; invalidate hủy session |
| “Cookie Max-Age bằng timeout server” | Session hết hạn bất ngờ hoặc cookie tồn tại lâu | Cấu hình cả browser retention và backend idle timeout |
| “In-memory store chạy nhiều pod sẽ tự đồng bộ” | Người dùng mất state khi đổi pod/restart | Dùng store phân tán hỗ trợ reactive |
| “`ThreadLocal SecurityContextHolder` dùng như MVC” | Mất/nhầm context khi đổi thread | Dùng Reactor Context hoặc tham số controller |
| “Lưu cả entity/credential vào session cho tiện” | Lộ dữ liệu, serialization lỗi và tăng memory | Lưu ID/giá trị tối thiểu, map DTO server-side |
| “Đã đổi ID session nên không cần patch framework” | Có thể bỏ sót lỗ hổng fixation/cookie handling | Theo dõi advisory và nâng cấp phiên bản |

## 11. Checklist cho thiết kế WebSession trong Spring Security reactive

1. Xác định ứng dụng dùng WebFlux hay Servlet trước khi chọn `WebSession` hoặc `HttpSession`.
2. Vẽ luồng request: nhận cookie ID → resolve session → load state → authorization → response lưu session.
3. Ghi rõ nơi nào bắt đầu session: `start()`, thêm attribute, CSRF/login filter hay logic ứng dụng.
4. Không gửi session ID qua URL, response DTO hoặc log; giới hạn quyền xem request headers.
5. Dùng `server.reactive.session.timeout` và cookie properties khi cấu hình Spring Boot reactive; kiểm test trên browser/proxy thật.
6. Phân biệt cart session (có thể guest) với SecurityContext (chỉ tồn tại khi xác thực và lưu đúng cách).
7. Giữ CSRF protection nếu browser tự gửi cookie credential; test POST không token bị từ chối và POST hợp lệ được xử lý.
8. Thiết kế logout: xóa context, invalidate WebSession, hết hạn cookie, revoke token/IdP nếu mô hình yêu cầu.
9. Đổi session ID tại thời điểm nâng quyền theo luồng được framework hỗ trợ; theo dõi bản vá bảo mật.
10. Trên nhiều node, dùng WebSession store phân tán phù hợp, test failover, race condition, serialization và TTL.
11. Tránh dùng `block()`, `subscribe()` thủ công trong request flow; compose các `Mono` từ `invalidate`/`changeSessionId`.
12. Có test cho khách, user thật, cookie cũ, session hết hạn, logout và access control theo tài nguyên/tenant.

## 12. Bài tập tự luyện

1. Chạy demo, gọi `GET /lab/state` trước khi thêm thuộc tính. Giải thích sự khác nhau giữa đối tượng WebSession và phiên đã bắt đầu.
2. Chạy bốn test WebTestClient, sau đó ghi cart bằng token CSRF hợp lệ và mang cookie sang request mới. Giải thích tại sao cùng cookie đọc lại được cart.
3. Đổi `server.reactive.session.cookie.name` từ `SESSION` sang `APPSESSION`; sửa client/test cho đúng rồi giải thích vì sao không đổi được tên tùy tiện ở chỉ một phía.
4. Sau khi có session, gọi `POST /lab/rotate`. Kiểm tra cookie ID mới và session attribute; vì sao ID mới không đồng nghĩa cart đã bị xóa?
5. Gọi `DELETE /lab/state` và thử lại ID cũ. Giải thích khác nhau giữa invalidate ở store và xóa cookie phía browser.
6. Thêm `Secure` trong môi trường HTTPS và thử SameSite=Lax/Strict/None dưới một kịch bản cross-site. Không nhầm hành vi browser với quyền của server.
7. So sánh một method MVC dùng `request.getSession(false)` với `ServerWebExchange.getSession()` và `WebSession.isStarted()`. Chúng có cùng quy tắc tạo phiên không?
8. Thiết kế form login cho WebFlux, mô tả `SecurityContext` được lưu/đọc nhờ `WebSessionServerSecurityContextRepository` và kiểm chứng logout có hủy session chưa.
9. Đề xuất cách chuyển một ứng dụng nhiều pod từ `InMemoryWebSessionStore` sang Spring Session Redis, kèm retry có giới hạn, TTL và serialization.
10. Giải thích tại sao một browser có cookie phiên không tự động được vào endpoint `/secure/me` khi application chỉ cấp cart state cho guest.

## Ghi nhớ

**`WebSession` là phiên server-side của Spring WebFlux; `HttpSession` là phiên theo Servlet API.** WebFlux truy cập WebSession qua API reactive và không bắt đầu phiên chỉ vì đọc đối tượng; thao tác thêm attribute hoặc `start()` mới bắt đầu phiên. Cookie **`SESSION`** thường chỉ giữ ID để tìm dữ liệu trong `WebSessionStore`, không phải bằng chứng xác thực. Trong Spring Security reactive, `WebSessionServerSecurityContextRepository` có thể lưu `SecurityContext` vào session, nhưng auth, authorization, CSRF, ID rotation, logout và session expiry vẫn là những trách nhiệm cần được thiết kế, cấu hình và kiểm thử riêng.

## Tài liệu chính thức

- Spring Framework 6.1 — `WebSession` API, `start`/`isStarted`/`changeSessionId`/`invalidate`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Framework 6.1 — `CookieWebSessionIdResolver` mặc định `SESSION` và các cookie initializer: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
- Spring Framework — WebFlux controller arguments (`WebSession`): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Boot 3.3 — Common application properties, `server.reactive.session.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Security 6.3 — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — Reactive logout và WebSessionServerLogoutHandler: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security — Reactive CSRF và WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Session — WebSession integration/Redis: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Framework security advisory về session fixation WebFlux: https://spring.io/security/cve-2026-41839/
