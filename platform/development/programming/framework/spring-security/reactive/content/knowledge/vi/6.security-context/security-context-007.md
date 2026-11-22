# WebSessionServerSecurityContextRepository và NoOpServerSecurityContextRepository

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích hợp đồng `ServerSecurityContextRepository` trong Spring Security WebFlux và cách `load` / `save` tham gia vào vòng đời xác thực reactive.
- Phân biệt `WebSessionServerSecurityContextRepository` (lưu/khôi phục `SecurityContext` qua `WebSession`) với `NoOpServerSecurityContextRepository` (không lưu và không khôi phục).
- Hiểu vì sao `SecurityContext` trong **Reactor Context của request hiện tại** khác với `SecurityContext` được **lưu qua nhiều HTTP request**.
- Cấu hình đúng cả **nơi đọc context cho request đến** và **nơi lưu context sau authentication** trong `ServerHttpSecurity` / authentication filter.
- Chạy ví dụ Java 17+ để so sánh request có HTTP Basic, request kế tiếp chỉ có session cookie và request không mang bất kỳ credential nào.
- Chọn chiến lược phù hợp cho ứng dụng web dùng login session hoặc API xác thực độc lập bằng bearer token; nhận diện ảnh hưởng đối với CSRF, cookie, logout, hiệu năng, phân tán và bảo mật.

> **Phạm vi:** Spring Security **reactive** trên Spring WebFlux, dùng API `org.springframework.security.web.server.context.*`. Không trộn với `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository` hay `HttpSecurity` của stack **Servlet**.

## 1. Vì sao cần một SecurityContextRepository?

Sau khi xác thực credential, Spring Security có một `Authentication` (principal, authorities và thông tin liên quan), được đặt trong `SecurityContext`. Ở WebFlux, context này thường được truy cập theo **subscription** nhờ `ReactiveSecurityContextHolder`, không dựa vào một `ThreadLocal` cố định của request.

Nhưng một HTTP request kết thúc rồi. Request tiếp theo là một exchange và subscription **khác**. Nếu ứng dụng muốn nhớ rằng người dùng đã đăng nhập ở request trước, cần cơ chế **lưu và tải lại** context. `ServerSecurityContextRepository` cung cấp chiến lược thực hiện việc đó.

Có ba khái niệm nên tách riêng:

| Khái niệm | Vai trò | Phạm vi |
|---|---|---|
| `SecurityContext` | Chứa `Authentication` hiện tại. | Được sử dụng trong pipeline xử lý request. |
| Reactor `Context` / `ReactiveSecurityContextHolder` | Truyền security context theo reactive subscription, kể cả khi đổi thread. | **Một subscription** và các đoạn pipeline đúng phạm vi. |
| `ServerSecurityContextRepository` | Quyết định có lưu/khôi phục `SecurityContext` qua các HTTP exchange hay không. | **Giữa các request** khi có cơ chế lưu trữ phù hợp. |

Không đồng nhất ba điều này. Một request vẫn có thể được xác thực thành công và authorization cho phép **dù repository không lưu gì**. Ngược lại, một session tồn tại không bảo đảm có một `Authentication` hợp lệ bên trong nó.

Mô hình:

~~~text
Request #1                 Request #2
  |                           |
  v                           v
Authentication             Repository.load(exchange)
  |                           |
  v                           v
SecurityContext ----------> nếu đã được lưu: SecurityContext
  |                           |
  v                           v
Reactor Context #1         Reactor Context #2
  |                           |
  v                           v
Authorization + Handler    Authorization + Handler
  |
  +--> Repository.save(exchange, context) (khi authentication
        filter/luồng xử lý được cấu hình để lưu)
~~~

Với repository lưu session, mũi tên `save` ở request đầu và `load` ở request sau có thể nối hai request qua session ID. Với NoOp, chúng không nối hai request.

## 2. Hợp đồng ServerSecurityContextRepository

Interface Spring Security reactive:

~~~java
public interface ServerSecurityContextRepository {

    Mono<Void> save(ServerWebExchange exchange,
                    SecurityContext context);

    Mono<SecurityContext> load(ServerWebExchange exchange);
}
~~~

Đây là **chữ ký rút gọn để học** (chưa trình bày các annotation nullability); không phải toàn bộ source của framework. Hai method có ý nghĩa:

- `load(exchange)`: phát `SecurityContext` nếu có; trả **publisher rỗng** (`Mono.empty()`) khi không tìm thấy. Không trả `null` thay `Mono`.
- `save(exchange, context)`: trả `Mono<Void>` báo hoàn thành/lỗi thao tác lưu. Truyền `null` làm context có ý nghĩa xóa ở các implementation hỗ trợ, theo API tương ứng. Không tự suy luận rằng gọi method là dữ liệu đã được ghi nếu publisher chưa được subscribe.
- `exchange` chính là `ServerWebExchange` của HTTP request hiện tại, có thể cung cấp `WebSession` qua `getSession()`.

Điểm thực tế: `Mono<Void> save(...)` phải được **kết hợp vào luồng reactive**. Nếu tự viết authentication filter và bỏ qua publisher `save`, không thể kết luận context đã được persist. Tránh `block()` hoặc `subscribe()` thủ công trong WebFlux filter.

### 2.1. Ai gọi load, ai gọi save?

Trong chuỗi bảo mật WebFlux:

1. `ReactorContextWebFilter` sử dụng repository được cấu hình ở cấp `ServerHttpSecurity.securityContextRepository(...)` để tìm security context của request và đưa nó vào phạm vi Reactor Context khi phù hợp.
2. `AuthenticationWebFilter` hoặc cơ chế authentication tương ứng, khi xác thực thành công, có thể đặt `Authentication` vào context **của request hiện tại** và gọi repository lưu đã được cấu hình **cho bộ lọc xác thực đó**.
3. Authorization và downstream code dùng `ReactiveSecurityContextHolder.getContext()`, `ServerWebExchange.getPrincipal()` hoặc API reactive phù hợp để truy cập người dùng hiện hành.
4. Với request sau, việc có khôi phục danh tính từ request trước hay không phụ thuộc repository load **và** cookie/session hoặc credential mới có sẵn.

Quan trọng: **chọn nơi load và nơi save là hai việc có thể phải cấu hình riêng.** API cấp `ServerHttpSecurity` dùng repository cho `ReactorContextWebFilter`, nhưng không mặc nhiên thay tất cả repository dùng để lưu trên từng authentication filter.

## 3. WebSessionServerSecurityContextRepository: lưu context vào WebSession

Class: `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository`.

Đây là implementation lưu `SecurityContext` vào `WebSession` của Spring WebFlux và đọc lại từ session gắn với request sau. Nó phù hợp khi ứng dụng muốn **đăng nhập một lần, duy trì phiên** qua nhiều request.

### 3.1. Cơ chế

~~~text
Lần đăng nhập thành công
    Authentication thành công
      -> tạo SecurityContext chứa Authentication
      -> WebSessionServerSecurityContextRepository.save(exchange, context)
      -> WebSession lưu attribute security context
      -> response chuyển thông tin session ID cho client (thường qua cookie)

Request về sau
    client gửi session ID tương ứng
      -> WebFlux tìm WebSession hiện hành
      -> WebSessionServerSecurityContextRepository.load(exchange)
      -> lấy SecurityContext đã lưu
      -> ReactorContextWebFilter cung cấp cho reactive security pipeline
      -> authorization/handler có thể thấy người dùng đã đăng nhập
~~~

**Không phải mọi request tự tạo session.** Khi cần lưu context, implementation có thể truy cập `exchange.getSession()` để lấy WebSession tương ứng. Cookie/session lifecycle còn phụ thuộc cấu hình WebFlux, quản lý session, thời điểm commit response và hạ tầng session store.

Theo Javadoc của Spring Security, `WebSessionServerSecurityContextRepository` đổi session ID khi lưu security context nhằm phòng **session fixation**. Hành vi này không thay thế các biện pháp bảo vệ phiên khác.

### 3.2. Thuộc tính được lưu

`WebSessionServerSecurityContextRepository.DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME` là hằng số tên attribute mặc định. Có thể thay tên bằng `setSpringSecurityContextAttrName(...)` nếu thực sự cần tương thích với hệ thống khác.

Class cũng cung cấp `setCacheSecurityContext(boolean)` ở các phiên bản hỗ trợ: khi bật, giá trị do `load(exchange)` trả về có thể được cache bằng `Mono.cache()` để hạn chế nhiều lần tra cứu **trong phạm vi publisher được cache**. Không nhầm cache này với kho session toàn cụm hoặc cache bảo mật xuyên request.

### 3.3. Hệ quả vận hành

- Client thường giữ một session cookie (ví dụ `SESSION` theo cấu hình WebFlux). Cookie là mã định danh truy cập session, **không phải nội dung Authentication dạng JSON**.
- Server/session store phải giữ trạng thái và quản lý timeout/invalidation. Nhiều instance có thể cần Spring Session với backend chung (ví dụ Redis); nếu chỉ dùng kho session trong bộ nhớ của một instance, việc định tuyến request sang instance khác có thể làm mất phiên.
- Tổ chức CSRF là quan trọng cho ứng dụng trình duyệt dựa vào cookie tự động gửi. Lưu context vào session **không tự loại bỏ nguy cơ CSRF**; cấu hình `CsrfWebFilter`, token repository và cookie `Secure`/`HttpOnly`/`SameSite` theo threat model.
- Logout đúng phải loại bỏ/cập nhật context đã lưu và xử lý session phù hợp. Chỉ xóa một key trong Reactor Context của request hiện tại không đủ để chắc chắn người dùng sẽ không được khôi phục ở request sau.
- Session ID cần được bảo vệ qua HTTPS; tránh ghi nó vào URL, log hoặc tracing.

**Không có quy tắc “WebSessionRepository = tự động đăng nhập”.** Chỉ khi có một luồng authentication thực sự tạo context và **lưu thành công**, request sau mới có dữ liệu để khôi phục.

## 4. NoOpServerSecurityContextRepository: không lưu và không tải

Class: `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository`.

Implementation này chủ đích **không làm gì** đối với persistence:

~~~java
ServerSecurityContextRepository repository =
    NoOpServerSecurityContextRepository.getInstance();
~~~

Đây là đoạn Java ngắn dùng trong class cấu hình; `getInstance()` trả instance dùng chung.

Về mặt hành vi:

- `load(exchange)` không tìm hoặc tạo SecurityContext lưu trước đó; publisher không phát context từ repository.
- `save(exchange, context)` hoàn thành mà không persist authentication.
- Ở request đang xác thực, `AuthenticationWebFilter` vẫn có thể cung cấp context cho downstream; authorization vẫn có thể hoạt động bình thường. Nhưng request sau cần một cơ chế xác thực mới, ví dụ Bearer JWT có hiệu lực được gửi trong từng request.

Đây là lựa chọn phổ biến cho API **stateless về security-context persistence**. Ví dụ mỗi request mang `Authorization: Bearer <token>`, resource server kiểm tra token rồi tạo context cho request hiện tại, không lưu authentication vào WebSession.

### 4.1. Không đồng nghĩa với vô hiệu hóa mọi WebSession

Đặt `NoOpServerSecurityContextRepository` **không có nghĩa**:

- Server sẽ không bao giờ tạo WebSession cho mục đích khác (CSRF token repository, flash/session state của ứng dụng, request cache, v.v.).
- Request sẽ không thể có một `Authentication` trong Reactor Context hiện hành.
- Spring Security ngừng xác thực hoặc phân quyền.
- Token phía client tự động bị thu hồi khi logout.
- Cookie của ứng dụng sẽ biến mất hoặc mọi WebFilter khác ngừng chạy.

Nó chỉ định nghĩa **repository không persist/restore SecurityContext**. Thiết kế stateless đầy đủ còn cần kiểm soát các cơ chế khác có thể giữ session hoặc cookie và kiểm tra mô hình xác thực hiện hành.

### 4.2. Sử dụng với bearer token

Trong ứng dụng OAuth2 Resource Server JWT, thường request được xác thực bằng credential ký/mã hóa hoặc introspection theo **từng request**. Nếu dùng NoOp, request A với token hợp lệ được cho phép; request B thiếu token có thể nhận 401. Đây là hành vi mong muốn.

Tuy nhiên, lựa chọn NoOp không thay thế cấu hình:

- issuer/audience/JWK/signature/expiry/token validation;
- scope/authority mapping và authorization rules;
- HTTPS, logging redaction và chính sách token lifetime/revocation.

Không lưu Authentication vào session **không đồng nghĩa JWT tự an toàn**.

## 5. Bảng so sánh kỹ thuật

| Tiêu chí | WebSessionServerSecurityContextRepository | NoOpServerSecurityContextRepository |
|---|---|---|
| Mục đích | Duy trì SecurityContext qua HTTP request bằng WebSession | Không persist SecurityContext giữa HTTP request |
| `save(exchange, context)` | Lưu/xóa context trong WebSession theo hợp đồng implementation | Hoàn thành mà không lưu |
| `load(exchange)` | Tìm context trong WebSession; không có thì `Mono.empty()` | Không phát context đã lưu: `Mono.empty()` |
| Đối tượng cần duy trì | WebSession và session ID phía client; store ở server | Không cần session store cho chính SecurityContext |
| Request kế tiếp chỉ có session cookie | Có thể khôi phục Authentication đã lưu | Không khôi phục Authentication từ repo |
| Request mang credential hợp lệ mới | Vẫn có thể xác thực; có lưu hay không phụ thuộc authentication filter | Vẫn có thể xác thực trong request hiện tại |
| Mô hình thường gặp | Form login, ứng dụng web session-based | API bearer token hoặc Basic xác thực mỗi request |
| Chi phí/rủi ro | Session store, cookie, timeout, phân tán, fixation, CSRF | Kiểm tra credential mỗi request; quản lý vòng đời token ở nơi khác |
| Logout | Cần xóa context đã lưu/invalidate phiên theo cấu hình | Không có context trong repository để xóa; phải xử lý token/revocation riêng |
| Điểm dễ nhầm | Có repo lưu nhưng auth filter không gọi repo đó | Nghĩ không có `WebSession` nào trong toàn ứng dụng |

Đừng diễn giải “stateless” thành “không có security context”. Stateless chỉ nói về **không giữ Authentication qua request bằng repository**, còn trong một request vẫn có đầy đủ principal/authorities để phân quyền.

## 6. Cấu hình đúng: nơi load khác nơi save

### 6.1. Nơi đọc cho request đến

~~~java
http.securityContextRepository(repository);
~~~

Ở WebFlux, cách cấu hình này cung cấp repository cho `ReactorContextWebFilter` để tải context và tích hợp vào Reactor Context khi request đi qua security chain.

### 6.2. Nơi lưu sau authentication

Tùy loại authentication mà còn một cấu hình khác:

~~~java
http.httpBasic(basic ->
    basic.securityContextRepository(repository));

http.formLogin(form ->
    form.securityContextRepository(repository));
~~~

Hai method trên là các **đoạn minh họa độc lập**. Chỉ bật loại đăng nhập phù hợp. Chúng cấu hình repository để **authentication filter lưu Authentication khi thành công**.

Các giá trị mặc định đáng nhớ (theo API Spring Security reactive dòng 6.3 trở lên):

- Với **HTTP Basic**, `HttpBasicSpec.securityContextRepository(...)` mặc định dùng `NoOpServerSecurityContextRepository` để Basic không tự tạo phiên cho mỗi request.
- Với **form login**, `FormLoginSpec.securityContextRepository(...)` mặc định dùng `WebSessionServerSecurityContextRepository` để đăng nhập có thể giữ session.
- Các mặc định này **không buộc** phải là cùng instance repository đang dùng ở `ServerHttpSecurity.securityContextRepository(...)` cho việc load. Khi thay đổi chiến lược, hãy nối **cả hai phía** tương ứng và kiểm thử.

Đây là lý do một lỗi thường gặp là chỉ viết:

~~~java
// Chưa đủ để bảo đảm mọi authentication mechanism lưu theo repo này.
http.securityContextRepository(new WebSessionServerSecurityContextRepository());
~~~

Nếu dùng HTTP Basic mà vẫn giữ repository lưu của Basic là NoOp, việc xác thực Basic ở một request **không tự động sinh security context được persist trong WebSession**. Request sau thiếu Basic credential vẫn có thể bị 401. Chiều ngược lại, nếu cấu hình authentication filter lưu session nhưng ReactorContextWebFilter dùng NoOp để đọc, request sau vẫn không khôi phục được context từ session.

## 7. Ví dụ Java 17+ chạy độc lập: cùng một API với hai chiến lược

Ví dụ chạy với **Spring Boot 3.3.5**, **Java 17+**, Spring WebFlux, Spring Security 6.3.x do Spring Boot quản lý. Thử nghiệm chủ động cấu hình:

1. `ServerHttpSecurity.securityContextRepository(repo)` để **load** đúng repo.
2. `httpBasic(basic -> basic.securityContextRepository(repo))` để **save** đúng repo.
3. Một endpoint `GET /me` yêu cầu authenticated và trả về tên principal.
4. Chọn repository qua `--demo.repository=session` hoặc `--demo.repository=noop`.

**Vì sao cố ý dùng Basic?** Để nhìn rõ hiệu ứng persistence: trong chế độ session, request thứ hai chỉ gửi cookie, **không gửi lại Basic credential**, vẫn có thể được xác thực từ context đã lưu. Đây là cách thử cơ chế repository, **không phải khuyến nghị dùng HTTP Basic làm login có phiên trong production**. Nếu cần login web thực tế, hãy thiết kế form login/SSO và CSRF đúng chuẩn.

### 7.1. Cấu trúc dự án

~~~text
security-context-repository-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecurityContextRepositoryDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-repository-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

`src/main/java/example/SecurityContextRepositoryDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityContextRepositoryDemo {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextRepositoryDemo.class, args);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository(Environment env) {
        String mode = env.getProperty("demo.repository", "session");

        return switch (mode) {
            case "session" -> new WebSessionServerSecurityContextRepository();
            case "noop" -> NoOpServerSecurityContextRepository.getInstance();
            default -> throw new IllegalArgumentException(
                "Unsupported demo.repository: " + mode);
        };
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ServerSecurityContextRepository repository) {

        return http
            // Dùng repo này để load context qua ReactorContextWebFilter.
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            // HTTP Basic bình thường mặc định không save session;
            // demo cố ý dùng cùng repo cho thao tác save.
            .httpBasic(basic ->
                basic.securityContextRepository(repository))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // Chỉ GET /me; giữ nguyên cấu hình CSRF mặc định.
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Chỉ dùng cho demo trên localhost, không dùng production.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @RestController
    static class MeController {
        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }
    }
}
~~~

**Giải thích code:**

- Bean `securityContextRepository(...)` trả đúng một trong hai implementation.
- `@EnableWebFluxSecurity` bật web security reactive.
- Hai lời gọi `securityContextRepository` và `httpBasic(...securityContextRepository...)` là điểm chính của bài: **load và save cùng một repo**.
- `formLogin(...disable)` tránh một luồng đăng nhập form dùng repository mặc định khác, gây nhiễu kết quả.
- Controller chỉ nhìn `exchange.getPrincipal()` đã được Spring Security tích hợp, không tự đọc username từ header `Authorization`.
- Code dùng Java `switch` expression (hỗ trợ ở Java 17) và `Map.of(...)`; không yêu cầu Lombok.

### 7.2. Chạy chế độ WebSession

Cần JDK 17+ và Gradle/Gradle Wrapper tương thích. Trong thư mục dự án:

~~~bash
gradle bootRun --args="--demo.repository=session"
~~~

Nếu dự án có wrapper, dùng `./gradlew bootRun --args="--demo.repository=session"` trên Linux/macOS hoặc `gradlew.bat bootRun --args="--demo.repository=session"` trên Windows.

Ở terminal khác:

~~~bash
# Request A: gửi Basic đúng và lưu cookie nếu server cấp.
curl -i -c session-cookies.txt -u learner:demo-pass http://localhost:8080/me

# Request B: KHÔNG gửi -u; chỉ gửi cookie từ request A.
curl -i -b session-cookies.txt http://localhost:8080/me
~~~

Với ứng dụng demo chạy thành công và dùng session store mặc định, kết quả kỳ vọng:

- Request A: `200 OK`, body chứa `{"username":"learner"}`; response thường có `Set-Cookie: SESSION=...` hoặc cookie session tương ứng với cấu hình.
- Request B: `200 OK`, body chứa cùng username mặc dù lần này không có Basic header. Repository đã load lại `SecurityContext` qua WebSession theo cookie đã lưu.
- Nếu request B nhận `401`, kiểm tra cookie jar/cookie domain và port, `save` của Basic, `load` của ReactorContextWebFilter, session timeout và session store. Đừng kết luận repository sai chỉ từ status.

Body JSON trên chỉ có một field nên giá trị là cố định trong demo; HTTP header (cookie ID, thời gian, các security header) thì biến thiên. Output của `curl -i` là HTTP response, không phải stdout cố định của chương trình Java.

### 7.3. Chạy chế độ NoOp

Dừng app ở terminal đầu, khởi động lại cùng dự án nhưng đổi tham số:

~~~bash
gradle bootRun --args="--demo.repository=noop"
~~~

Ở terminal khác:

~~~bash
# Request A: credential Basic đúng, đăng nhập trong request này.
curl -i -c noop-cookies.txt -u learner:demo-pass http://localhost:8080/me

# Request B: không mang Basic, chỉ thử gửi cookie đã ghi.
curl -i -b noop-cookies.txt http://localhost:8080/me
~~~

Kết quả kỳ vọng:

- Request A: `200 OK` và body `{"username":"learner"}`. **NoOp không ngăn một request có Authentication hợp lệ.**
- Request B: `401 Unauthorized` do không có Basic credential mới, cũng không có SecurityContext được khôi phục từ repository. HTTP Basic entry point có thể thêm `WWW-Authenticate`.
- `NoOp` tự nó không phát `Set-Cookie` cho SecurityContext; nếu app hoặc thành phần khác có phát cookie, sự tồn tại cookie đó **không chứng minh SecurityContext được lưu**.

Thử tiếp:

~~~bash
# Mỗi request mang Basic đúng: trong chế độ NoOp vẫn trả 200.
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/me
~~~

Cả hai request có thể trả 200 vì **mỗi request xác thực lại**. Điều này minh họa: NoOp chỉ bỏ lưu/khôi phục security context giữa request, chứ không vô hiệu hóa authentication.

**An toàn khi thử:** Mật khẩu dùng `{noop}` (plain text) chỉ dành cho demo localhost; không dùng thật. HTTP Basic gửi credential ở mọi request cần TLS/HTTPS trong môi trường triển khai. Đừng giữ tài khoản hardcode hoặc công khai ứng dụng thử nghiệm ra Internet.

## 8. Luồng nội bộ: vì sao hai cài đặt tạo kết quả khác nhau?

### 8.1. WebSession + Basic save chủ động

~~~text
GET /me + Authorization: Basic ...
  -> AuthenticationWebFilter xác thực thành công
  -> Authentication tồn tại trong Reactor Context request #1
  -> repository.save(exchange #1, SecurityContext)
       WebSession chứa SecurityContext
       session ID cấp/trả cho client
  -> Controller: 200 {"username":"learner"}

GET /me + Cookie: SESSION=... (không Basic)
  -> ReactorContextWebFilter dùng repository.load(exchange #2)
       đọc SecurityContext từ WebSession đã lưu
  -> Authorization thấy Authentication
  -> Controller: 200 {"username":"learner"}
~~~

### 8.2. NoOp + Basic save không persist

~~~text
GET /me + Authorization: Basic ...
  -> AuthenticationWebFilter xác thực thành công
  -> Authentication tồn tại trong Reactor Context request #1
  -> repository.save(exchange #1, context) hoàn thành nhưng không lưu
  -> Controller: 200 {"username":"learner"}

GET /me (không Basic)
  -> repository.load(exchange #2) rỗng
  -> Không có Authentication đã khôi phục
  -> anyExchange().authenticated() từ chối
  -> HTTP Basic entry point: 401
~~~

Điểm kiểm chứng quan trọng là **request sau không mang credential**. Nếu gửi `-u learner:demo-pass` ở cả hai request, cả hai chiến lược có thể đều trả 200 và không phân biệt được repository có persist hay không.

## 9. Chọn repository theo mô hình xác thực

### 9.1. Ứng dụng web dùng form login và cookie session

Phần lớn ứng dụng tương tác qua trình duyệt muốn người dùng đăng nhập một lần, sau đó gửi cookie ở những request tiếp theo. `WebSessionServerSecurityContextRepository` thường phù hợp. Hãy cấu hình:

- Form login/SSO (đúng authentication manager và thành phần success/failure) để save vào WebSession;
- repository load của `ServerHttpSecurity` tương thích với nơi form login save;
- CSRF bảo vệ request thay đổi trạng thái khi trình duyệt tự động gửi cookie;
- cookie có `Secure` khi dùng HTTPS, `HttpOnly`/`SameSite` phù hợp, session timeout và invalidation;
- session store đủ tin cậy cho môi trường scale (Spring Session reactive với Redis hoặc hạ tầng tương ứng);
- logout và quy trình session expiry được test thực tế.

Ví dụ chỉ phần cấu hình (đặt trong bean `SecurityWebFilterChain` tương thích; **không** ghép đồng thời với `httpBasic` của demo):

~~~java
ServerSecurityContextRepository sessionRepo =
    new WebSessionServerSecurityContextRepository();

return http
    .securityContextRepository(sessionRepo)
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/login", "/public/**").permitAll()
        .anyExchange().authenticated())
    .formLogin(form ->
        form.securityContextRepository(sessionRepo))
    .build();
~~~

Đoạn trên chỉ là **mảnh cấu hình minh họa**, không chứa bean user details và giao diện đăng nhập. Spring Security có thể cấp trang login mặc định nếu ứng dụng chưa tạo trang riêng. Khi có login page tùy chỉnh, phải cấu hình URL/form field/success handler và CSRF token đúng để login hoạt động.

### 9.2. API bearer token stateless

API nhận bearer access token trong từng request thường không cần lưu SecurityContext vào WebSession:

~~~java
return http
    .securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance())
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()))
    .build();
~~~

Đây là **mảnh cấu hình tích hợp**, cần `spring-boot-starter-oauth2-resource-server`, issuer/JWK validation và cấu hình OAuth2 Resource Server phù hợp. Mỗi request mang bearer token hợp lệ sẽ được xác thực theo token; request thiếu token ở route protected nhận 401. Không tự gán Authentication cho token chưa kiểm chứng.

**Ranh giới stateless:** `NoOp` không tự vô hiệu hóa form login, request cache hoặc các nguồn session khác. Với API không dựa vào cookie tự động gửi, hãy đánh giá CSRF theo mô hình thực tế; đừng tắt CSRF chỉ vì gọi API là “REST”.

### 9.3. Nhiều SecurityWebFilterChain

Nếu ứng dụng có cả website session-based và API bearer-based, có thể cấu hình **hai SecurityWebFilterChain** với matcher/thứ tự riêng. Trong mỗi chuỗi:

- Web route → session repository + form login thích hợp.
- API route → NoOp + resource server token auth thích hợp.
- Có chuỗi dự phòng rõ ràng nếu cần bảo vệ tất cả URL; đừng để path nhạy cảm nằm ngoài mọi chain.
- Không giả định repository áp dụng toàn app nếu các chain có cấu hình khác nhau.

Đừng dùng một bean repository với trạng thái global mutable để đổi giữa session/NoOp theo request. Sự lựa chọn thuộc cấu hình chain/matcher có kiểm soát.

## 10. Logout, session fixation, phân tán và các rủi ro thực tế

### 10.1. Logout ở chế độ session

Khi người dùng logout, cơ chế logout phải xóa SecurityContext đã lưu và, tùy chính sách, invalidate WebSession; thao tác dọn Reactor Context hiện tại **không đủ** để bảo đảm request sau không được khôi phục từ cookie cũ. Hãy dùng logout handler của Spring Security và kiểm tra request kế tiếp với cookie cũ bị từ chối.

Javadoc của `WebSessionServerSecurityContextRepository` nêu hành vi đổi session ID khi lưu context để giảm session fixation. Thử nghiệm session fixation nên kiểm tra cookie/session ID trước và sau authentication, đồng thời bảo đảm người dùng khác không thể chiếm session ID bị lộ.

### 10.2. Logout ở chế độ NoOp

Repository NoOp không có SecurityContext để xóa. Với JWT hoặc bearer token, “logout” trên client thường là xóa credential khỏi nơi lưu; token cũ **vẫn có thể hợp lệ** đến khi hết hạn nếu không có cơ chế thu hồi. Nếu cần thu hồi tức thời, thiết kế revoke/denylist/introspection hoặc token rotation theo yêu cầu.

### 10.3. Load từ WebSession không phải authorization

`SecurityContextRepository.load` chỉ tìm SecurityContext; nó không trực tiếp quyết định user có quyền xem tài nguyên. Authorization vẫn dựa vào Authentication/authorities và các quy tắc (`authenticated()`, `hasRole`, reactive method security…). Session cũ, user disabled hoặc quyền mới thay đổi có thể đòi hỏi giải pháp làm mới/revoke context tùy mô hình bảo mật; đừng tưởng session luôn phản ánh dữ liệu quyền mới nhất.

### 10.4. Thiết kế nhiều instance

Một session nằm trong memory của server A thường không tự xuất hiện ở server B. Với load balancer và scale ngang, hoặc dùng sticky session có giới hạn, hoặc ưu tiên session store dùng chung phù hợp (ví dụ Spring Session WebFlux và Redis). Xem xét timeout, failover, serialization, quyền truy cập Redis và việc xóa/invalidate session trên toàn cụm.

NoOp giảm yêu cầu kho session cho Authentication, nhưng có thể tăng số lần validate token/tra cứu identity theo request. Đánh giá bottleneck thật, cache khóa/JWK/introspection an toàn và giới hạn rate.

### 10.5. Hiển thị/log trạng thái

Không log raw `SecurityContext`, bearer token, cookie `SESSION`, mật khẩu, hoặc credential Basic. Khi debug, ghi correlation ID và chỉ số vô hại: request có header Authorization hay không (không ghi giá trị), status, filter đã khớp, repository mode. Tránh trả thông tin chi tiết nguyên nhân authentication thất bại cho client ngoài mức HTTP chuẩn.

## 11. Lỗi thường gặp và cách sửa

**Lỗi 1 — Cấu hình chỉ nơi load mà quên nơi save.**

~~~java
http.securityContextRepository(sessionRepo);
// Basic authentication vẫn có thể mặc định save vào NoOp!
~~~

Sửa bằng cấu hình repository cho authentication mechanism cần persist, ví dụ `httpBasic(basic -> basic.securityContextRepository(sessionRepo))` trong demo. Tương tự, cấu hình form login với repository tương thích.

**Lỗi 2 — Cấu hình chỉ nơi save, request sau load bằng repo khác.**

Repository lưu ở WebSession, nhưng `ReactorContextWebFilter` đọc từ NoOp thì request sau không thấy Authentication. Sửa bằng cấu hình nhất quán ở cả hai vị trí.

**Lỗi 3 — Nghĩ NoOp đồng nghĩa mọi request bị anonymous.**

Credential hợp lệ trong một request vẫn tạo Authentication trong Reactor Context request đó. Hãy thử request A Basic đúng → 200, request B không Basic → 401.

**Lỗi 4 — Nghĩ WebSessionRepo tự xác thực header.**

Repository chỉ lưu/khôi phục `SecurityContext`, **không kiểm chứng username/password/JWT**. Authentication manager/filter làm nhiệm vụ xác thực; không tự dựng `SecurityContext` từ header client chưa xác minh.

**Lỗi 5 — Tự gọi `repository.save(...).subscribe()` rồi ngay lập tức trả response.**

Các thao tác có thể không hoàn tất trước khi response commit; lỗi không được điều phối đúng. Sửa bằng kết hợp publisher `save` vào chuỗi xử lý và trả `Mono<Void>` được framework subscribe.

**Lỗi 6 — Khởi tạo WebSessionRepository cho API JWT rồi nghĩ đó là bắt buộc.**

Bearer token đủ thông tin được gửi từng request thường không cần security context session. Không tạo trạng thái server và cookie không cần thiết nếu security requirements không đòi.

**Lỗi 7 — Tắt CSRF vô điều kiện để làm form login/session chạy được.**

Nếu trình duyệt tự động gửi cookie trên request thay đổi trạng thái, cần xem xét CSRF nghiêm túc. Hãy cấu hình CSRF token/route phù hợp; không lấy “WebFlux là reactive” làm lý do bỏ CSRF.

**Lỗi 8 — Chỉ kiểm tra cookie, không kiểm tra request sau có Authorization hay không.**

Nếu request sau vẫn gửi Basic/JWT, nó có thể trả 200 dù repo NoOp; đó không chứng minh persistence. Test request tiếp theo **chỉ có session cookie**, không credential.

**Lỗi 9 — Nhầm `HttpSessionSecurityContextRepository` Servlet với `WebSessionServerSecurityContextRepository` WebFlux.**

Dùng class đúng package và đúng stack. API servlet `SecurityContextRepository`/`HttpSecurity` không thay cho interface `ServerSecurityContextRepository` và `ServerHttpSecurity` reactive.

**Lỗi 10 — Nghĩ NoOp tự revoke JWT hoặc xóa cookie.**

NoOp không lưu Authentication; nó không quản lý thời hạn token ở client, cookie ngoài security context hay token đã ký còn hiệu lực. Cần cơ chế revoke/logout riêng.

**Lỗi 11 — Đánh đồng lưu SecurityContext với cache Reactor Context.**

`setCacheSecurityContext` và Reactor `Mono.cache()` nhằm tối ưu truy cập publisher, không phải hạ tầng lưu phiên lâu dài giữa request. Session store và timeout được quản lý riêng.

**Lỗi 12 — Dùng chung mutable Authentication cho nhiều user/request.**

Không đặt Authentication hoặc WebSession của một request vào field singleton. Kiểm soát scope qua framework, context theo subscriber và repository đúng exchange.

## 12. Checklist kiểm thử

Trước khi đưa cấu hình vào production, hãy kiểm chứng tối thiểu:

1. **Authentication hiện tại:** Với credential hợp lệ, route protected trả 200 và principal đúng, dù repository dùng NoOp.
2. **Persistence:** Với WebSession repo và cơ chế save đúng, request sau chỉ có session cookie (không Authorization) được khôi phục; với NoOp, request sau thiếu credential bị 401.
3. **Không credential:** Request đầu tiên đến route protected không có credential và session hợp lệ phải bị từ chối.
4. **Credential sai:** Request dùng Basic/password sai hoặc bearer token hết hạn phải bị từ chối, không làm rò token/password trong log.
5. **Cookie session:** Cookie được xử lý đúng `Secure`, `HttpOnly`, `SameSite`, Path và HTTPS theo môi trường.
6. **Logout:** Session-based logout làm request sau với cookie cũ thất bại; token-based logout tuân theo policy revoke/expiry.
7. **CSRF:** Các route thay đổi trạng thái được kiểm thử với/không có CSRF token khi ứng dụng sử dụng cookie auth.
8. **Nhiều instance:** Load context sau khi chuyển instance vẫn đúng nếu hệ thống yêu cầu phân tán; lỗi session store không tạo đường vượt authorization.
9. **Matcher/chain:** Mỗi route nằm trong `SecurityWebFilterChain` đúng; không có endpoint nhạy cảm ngoài tất cả chain.
10. **Theo dõi:** Correlation ID và log ghi đủ để debug mà không ghi credential/sessions.
11. **Timeout:** Session hết hạn thì request không credential không được phép; token hết hạn thì resource server từ chối.
12. **Thay đổi quyền:** Thiết kế cập nhật/invalidate context cũ khi role hoặc tài khoản bị thay đổi.

## 13. Tự đánh giá

**Câu 1.** Nếu dùng `NoOpServerSecurityContextRepository`, một request gửi JWT hợp lệ có được authenticated không?

**Đáp án:** Có, khi token được xác thực thành công bằng cấu hình resource server. Authentication tồn tại trong request hiện tại, nhưng NoOp không persist sang request sau.

**Câu 2.** Tại sao cấu hình `http.securityContextRepository(sessionRepo)` có thể chưa đủ để Basic authentication persist context?

**Đáp án:** Vì thuộc tính cấp `ServerHttpSecurity` dùng cho việc load qua `ReactorContextWebFilter`; repository được dùng để save sau authentication có cấu hình riêng tại `HttpBasicSpec.securityContextRepository`, mặc định NoOp.

**Câu 3.** Một ứng dụng dùng form login lưu session, sau đó trả 401 khi request tiếp theo có cookie. Hãy kiểm tra gì?

**Đáp án:** Xem cookie có được gửi đúng, WebSession còn hiệu lực và cùng store, authentication filter đã save đúng repo, ReactorContextWebFilter đang load cùng repo, request có khớp security chain, và rule authorization có chấp nhận principal đó hay không.

**Câu 4.** Tắt security-context persistence có tự tắt CSRF không?

**Đáp án:** Không. CSRF và security-context persistence là hai cơ chế khác nhau; đánh giá CSRF theo việc browser có thể tự gửi credential trên request thay đổi trạng thái.

**Câu 5.** Có phải cứ thấy cookie `SESSION` là người dùng đã đăng nhập?

**Đáp án:** Không. Session có thể rỗng, hết hạn, chỉ chứa dữ liệu CSRF hoặc dữ liệu ứng dụng; phải tải/kiểm chứng Authentication qua Spring Security.

**Câu 6.** Dùng WebSessionRepository có nghĩa authorization không còn cần thiết?

**Đáp án:** Không. Context được khôi phục chỉ cho biết Authentication đã lưu; authorization vẫn cần quyết định user có quyền với tài nguyên và hành động cụ thể hay không.

## Tài liệu chính thức

- Spring Security — `ServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security — `WebSessionServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — `NoOpServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html
- Spring Security — `ServerHttpSecurity` (repository của `ReactorContextWebFilter`): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `ServerHttpSecurity.HttpBasicSpec` (save repository mặc định NoOp): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security — `ServerHttpSecurity.FormLoginSpec` (save repository mặc định WebSession): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — CSRF in WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — WebSession API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
