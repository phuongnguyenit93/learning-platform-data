# Các ranh giới tin cậy và bề mặt tấn công của một ứng dụng reactive

> **Ngữ cảnh:** Spring Boot 3.3, Spring WebFlux, Spring Security 6, Java 17+. Bài học tập trung vào cách nhận diện nơi dữ liệu/quyền đi qua một ranh giới tin cậy và các điểm có thể bị tấn công trong ứng dụng reactive. Lập trình không chặn (non-blocking) giúp xử lý I/O hiệu quả; nó **không tự động** bảo đảm xác thực, phân quyền, bảo mật dữ liệu hay chống quá tải.

## 1. Ba khái niệm cần phân biệt

- **Tài sản cần bảo vệ (asset):** dữ liệu người dùng, đơn hàng, token, cookie phiên, thông tin định danh, cấu hình bí mật, API quản trị, hạ tầng và tài nguyên CPU/bộ nhớ/kết nối.
- **Ranh giới tin cậy (trust boundary):** điểm mà dữ liệu, danh tính hoặc quyền đi từ vùng có mức bảo đảm này sang vùng khác. Ví dụ: yêu cầu HTTP ngoài Internet vào API; claims trong JWT do bên thứ ba cấp đi vào quyết định cấp quyền; ID tài nguyên từ URL được dùng để truy vấn dữ liệu nội bộ.
- **Bề mặt tấn công (attack surface):** các điểm tiếp xúc mà tác nhân không đáng tin cậy có thể điều khiển hoặc tác động: URL, query, body, header, WebSocket, endpoint đăng nhập, file upload, callback, WebClient, hàng đợi, cấu hình công khai, logs và endpoint vận hành.

**Nguyên tắc:** nhận được một giá trị không có nghĩa là giá trị đó đáng tin; xác thực danh tính không đồng nghĩa với quyền truy cập mọi tài nguyên.

Sơ đồ luồng điển hình:

```text
Client (trình duyệt, mobile, service khác)       [không tin cậy]
       |
       | HTTPS: path, header, cookie/token, body
       v
CDN / Load balancer / Reverse proxy              [ranh giới 1]
       |
       | request + header forwarded đã kiểm soát
       v
Spring WebFlux: ServerWebExchange, WebFilter     [ranh giới 2]
       |
       v
Spring Security: SecurityWebFilterChain
       | xác thực -> SecurityContext -> kiểm tra quyền
       v
Handler -> Service (Mono/Flux)                    [ranh giới 3]
       |          |               |
       |          |               +--> WebClient / API ngoài [ranh giới 5]
       |          +--> DB, cache, object storage              [ranh giới 4]
       +--> broker, WebSocket, log, metrics                   [ranh giới 6]
```

Các ô trong sơ đồ biểu thị **vùng cần đánh giá mức tin cậy riêng**, không có nghĩa mọi kết nối giữa hai ô đều an toàn chỉ nhờ nằm trong mạng nội bộ.

## 2. Những ranh giới quan trọng

| Điểm đi qua | Dữ liệu thường gặp | Rủi ro cốt lõi | Kiểm soát cần có |
|---|---|---|---|
| Client → proxy/ingress | URL, Host, Origin, X-Forwarded-*, body, cookie | Giả header nguồn, HTTP không mã hóa, request bất thường | HTTPS, chính sách proxy tin cậy, giới hạn request, lọc header |
| Proxy → ứng dụng WebFlux | Scheme, địa chỉ IP, route, forwarded headers | Ứng dụng tin vào địa chỉ/host do client tự khai | Chỉ chấp nhận header do proxy tin cậy thiết lập; loại header giả từ Internet |
| Request → Spring Security | Session/cookie, Authorization bearer | Token sai issuer/audience, token hết hạn, xác thực thiếu | SecurityWebFilterChain, xác minh chữ ký/token, chính sách phiên |
| Principal → nghiệp vụ | Vai trò, scope, tenant, mã tài nguyên | Người đã đăng nhập đọc/sửa đối tượng của người khác (BOLA/IDOR) | Kiểm quyền **trên từng tài nguyên** và tenant ở phía server |
| Service → DB/cache | Truy vấn, khóa cache, dữ liệu đa tenant | Injection, thiếu tenant predicate, rò dữ liệu qua cache | Query có tham số, ràng buộc tenant, phân quyền dữ liệu |
| Service → WebClient/IdP/API khác | URL, credential, bearer token, JSON | SSRF, gửi nhầm token, tin vào phản hồi ngoài | Allowlist đích, kiểm TLS, chỉ chuyển credential theo chính sách |
| HTTP → WebSocket/broker/background job | Session lúc bắt tay, message, event | Tin message sau handshake, bỏ qua kiểm quyền người nhận | Xác thực kết nối, phân quyền từng hành động/message, xác minh event |
| Ứng dụng → log/metrics/Actuator | URL, lỗi, request metadata, secret | Lộ token/PII, lộ chức năng vận hành | Che dữ liệu nhạy cảm, hạn chế endpoint, phân quyền quan sát |

Một ranh giới có thể lặp lại nhiều lần: request đã vượt qua xác thực ở gateway vẫn phải qua phân quyền tại service đang thực sự sở hữu dữ liệu.

## 3. Điều gì đặc thù ở WebFlux và Reactor?

### 3.1 Chuỗi lọc bảo mật

WebFlux tiếp nhận request qua **ServerWebExchange**; các **WebFilter** xử lý request/response. Spring Security sử dụng **SecurityWebFilterChain** để cấu hình xác thực và quy tắc truy cập cho ứng dụng reactive. Chính sách đường dẫn là tuyến bảo vệ đầu tiên, còn nghiệp vụ vẫn phải kiểm quyền tài nguyên.

Quy tắc dễ mắc lỗi:

- `permitAll()` nghĩa là cho phép truy cập theo quy tắc đó; không được đặt nhầm lên `/admin/**`.
- `authenticated()` chỉ đòi hỏi danh tính hợp lệ, chưa chứng minh người gọi sở hữu `orderId` hay thuộc `tenantId` cần truy cập.
- Các điều kiện được xét theo cấu hình matcher; cần hiểu thứ tự và phạm vi của từng `pathMatchers(...)`.
- Endpoint không liệt kê nên có chính sách mặc định chặt chẽ (`denyAll()` cho phần chưa khai báo, hoặc yêu cầu xác thực theo thiết kế).
- WebSocket, Actuator, proxy routes, tài nguyên tĩnh và các HTTP method có thể cần chính sách riêng.

### 3.2 SecurityContext trong luồng reactive

Trong ứng dụng servlet truyền thống, mã thường trông cậy vào `ThreadLocal`. Với Reactor, một yêu cầu có thể thay đổi thread giữa các bước bất đồng bộ. Spring Security reactive gắn ngữ cảnh bảo mật vào **Reactor Context** của luồng đăng ký (subscription); khi cần đọc trong chuỗi reactive, sử dụng cơ chế như `ReactiveSecurityContextHolder.getContext()` hoặc principal do WebFlux cung cấp.

Hệ quả thực tế:

1. Không coi tên thread hay một `ThreadLocal` tự tạo là định danh người dùng.
2. Việc đổi scheduler thông qua operator Reactor **không mặc nhiên làm mất Context**; rủi ro thường xuất hiện khi tự `subscribe()` bên trong handler, tạo subscription tách biệt, chuyển sang callback/thư viện không truyền Context, hoặc chạy tác vụ ngoài chuỗi mà không chuyển rõ thông tin cần thiết.
3. Không tự mang nguyên đối tượng xác thực đến message queue/job lâu dài. Với tác vụ nền, truyền một tập thông tin đã được xác minh, có phạm vi tối thiểu, rồi áp dụng lại chính sách quyền tại phía nhận.
4. Không chặn event loop bằng `block()`, JDBC đồng bộ hoặc lời gọi I/O chặn. Việc chặn có thể làm cạn thread và khiến ứng dụng dễ bị từ chối dịch vụ. Nếu bắt buộc gọi API blocking, cô lập và giới hạn nó ở scheduler phù hợp; lý tưởng là dùng client reactive.

### 3.3 Backpressure không phải tường lửa

`Flux` và backpressure giúp các thành phần phối hợp tốc độ tiêu thụ dữ liệu; chúng **không tự giới hạn** số kết nối tấn công, dung lượng request, thời gian tồn tại của luồng, truy vấn đắt tiền hay số request đồng thời. Một endpoint dùng `Flux` vẫn có thể bị lạm dụng bằng upload lớn, stream không kết thúc, client đọc chậm hoặc hàng nghìn request xác thực sai.

Cần giới hạn kích thước body, thời gian, concurrency, số request theo danh tính/nguồn và tài nguyên của dịch vụ. Cấu hình codec như `maxInMemorySize` chỉ giải quyết giới hạn bộ đệm của các thao tác giải mã liên quan; nó không thay thế giới hạn tổng thể ở ingress và ứng dụng.

## 4. Các bề mặt tấn công theo luồng request

### 4.1 Biên Internet, TLS và forwarded headers

Client kiểm soát `Host`, URL, body và phần lớn HTTP headers. `X-Forwarded-For`, `X-Forwarded-Proto` hoặc `Forwarded` do client tự gửi **không phải chứng cứ đáng tin** về IP hay HTTPS. Chỉ proxy do mình quản lý mới được phép ghi đè/thiết lập các header này và chỉ ứng dụng phía sau proxy tin cậy mới nên sử dụng chúng để suy ra scheme, host hoặc địa chỉ thật.

Ví dụ lỗi: hệ thống giới hạn theo IP lấy trực tiếp `X-Forwarded-For` từ Internet; kẻ tấn công đổi header trong mỗi request để vượt giới hạn. Biện pháp: bỏ header client khai ở edge, tái tạo header chuẩn tại proxy, xác định dải mạng proxy tin cậy và áp dụng rate limit thực tế ở biên.

TLS cần được bảo vệ ở đoạn client–ingress và ingress–backend theo mô hình triển khai. Khi dùng cookie an toàn, cấu hình `Secure`/`HttpOnly`/`SameSite` phù hợp và xem xét HSTS tại điểm phục vụ HTTPS.

### 4.2 Xác thực: ai gửi request?

- **Session/cookie:** server liên kết session với người dùng; trình duyệt có thể tự gắn cookie vào request, vì thế cần phòng chống CSRF cho những thao tác thay đổi trạng thái.
- **Bearer access token:** client gửi `Authorization: Bearer ...`. Một resource server phải kiểm tra chữ ký hoặc thực hiện introspection phù hợp, thời hạn, issuer và audience dự kiến; không được giải mã payload JWT rồi tin ngay các claim.
- **OIDC/OAuth2:** Identity Provider (IdP) cấp danh tính/token; ứng dụng vẫn chịu trách nhiệm kiểm tra token dành **đúng resource server**. Token còn hạn nhưng dành cho API khác không đủ căn cứ cấp quyền.
- **Khóa API/service credential:** phải có phạm vi quyền, vòng đời, bảo vệ bí mật và giới hạn sử dụng; header do bên gọi tự đặt không thể tự biến thành danh tính được xác thực.

Trong cấu hình JWT resource server theo `issuer-uri`, Spring Security thường tự xác minh chữ ký, issuer và các mốc thời gian như `exp`/`nbf` theo cơ chế của nó. **Đừng mặc định audience luôn được kiểm tra đúng nhu cầu ứng dụng:** hãy cấu hình validator/audience được mong đợi và kiểm thử token dành cho API khác.

### 4.3 Phân quyền: người đó được làm gì?

Hai yêu cầu có thể đều mang token hợp lệ nhưng có quyền khác nhau:

```text
GET /api/orders/1001  Authorization: Bearer <token-user-A>
GET /api/orders/1002  Authorization: Bearer <token-user-A>
```

Giả sử đơn `1001` thuộc A, còn `1002` thuộc B. Kiểm tra `authenticated()` hoặc `hasRole("USER")` cho cả hai request vẫn chưa đủ. Service phải dùng danh tính/tenant đã xác minh để kiểm tra **quyền đọc chính đơn hàng đó**, chẳng hạn truy vấn ràng buộc cả `orderId` và `tenantId` từ principal đáng tin. Không lấy `tenantId` từ query/header do client tự khai làm nguồn sự thật.

Nếu không được xem một tài nguyên, API có thể trả `403 Forbidden` hoặc `404 Not Found` theo chính sách chống lộ tồn tại. Giữ cách xử lý nhất quán, kể cả dữ liệu cache, object storage và sự kiện bất đồng bộ.

### 4.4 CORS, CSRF và trình duyệt

**CORS** là cơ chế trình duyệt quyết định JavaScript từ origin khác có thể truy cập phản hồi hay gửi một số cross-origin request theo chính sách hay không. CORS **không thay thế** xác thực, phân quyền, rate limit; client không phải trình duyệt thường không tuân thủ CORS. Không tùy tiện cho phép mọi origin đi kèm credential.

**CSRF** là việc lợi dụng trình duyệt tự gửi credential (cookie hoặc một số hình thức xác thực được trình duyệt lưu) để kích hoạt hành động ngoài ý muốn. Với UI/session/cookie, giữ cơ chế CSRF của Spring Security và áp dụng đúng cho request ghi. Một API thực sự không dùng credential tự gắn và chỉ nhận bearer token do client chủ động đặt có thể có thiết kế CSRF khác, nhưng phải chứng minh giả định trước khi vô hiệu hóa.

**Origin**, **Referer** và **SameSite** có thể hỗ trợ chính sách browser; chúng không phải bằng chứng danh tính người dùng. Cần phân biệt `401 Unauthorized` (chưa xác thực hợp lệ) và `403 Forbidden` (đã xác thực nhưng không đủ quyền), dù cơ chế cụ thể có thể ảnh hưởng cách phản hồi.

### 4.5 Dữ liệu đầu vào và tài nguyên

Body, query, path, multipart, filename, URL ngoài, header và giá trị trong JSON đều là đầu vào không tin cậy. Kiểm tra kiểu, độ dài, miền giá trị, encoding và ràng buộc nghiệp vụ ở server. Không bind tùy tiện JSON vào entity có các trường `role`, `ownerId`, `price`, `tenantId` hoặc `isAdmin` để tránh mass assignment.

Với database, sử dụng truy vấn có tham số/ràng buộc truy cập để phòng injection và BOLA. Với file upload, giới hạn kích thước, loại nội dung được chấp nhận, quyền đọc/ghi và đường dẫn lưu. Với WebClient sử dụng URL đầu vào, chống **SSRF** bằng danh sách đích hợp lệ, chặn truy cập địa chỉ nội bộ/metadata endpoint ngoài chính sách và kiểm soát chuyển hướng.

## 5. Một ví dụ WebFlux có thể chạy và thử quyền

Ví dụ nhỏ sau dùng **HTTP Basic với tài khoản cố định chỉ để học trên localhost**; không phải mô hình đăng nhập production. Tất cả endpoint chỉ thực hiện GET, để cơ chế CSRF mặc định không bị vô hiệu hóa. Mục đích là phân biệt cho phép công khai, xác thực và phân quyền vai trò. Không dùng mật khẩu mẫu trên môi trường thật.

**Tạo dự án Gradle độc lập** với cấu trúc:

```text
boundary-demo/
  build.gradle
  src/main/java/demo/BoundaryDemo.java
```

**build.gradle**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/demo/BoundaryDemo.java**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BoundaryDemo {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/private").hasRole("USER")
                .pathMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        Mono<String> publicInfo() {
            return Mono.just("public");
        }

        @GetMapping("/private")
        Mono<String> privateInfo() {
            return Mono.just("private: authenticated USER");
        }

        @GetMapping("/admin")
        Mono<String> adminInfo() {
            return Mono.just("admin");
        }
    }
}
```

Chạy với **Gradle tương thích và JDK 17+**: `gradle bootRun`; nếu dự án đã có wrapper, dùng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Sau khi server khởi động trên cổng mặc định 8080, thử:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:demo-pass http://localhost:8080/private
curl -i -u alice:demo-pass http://localhost:8080/admin
```

| Thử nghiệm | Kết quả kỳ vọng |
|---|---|
| GET `/public` không credential | HTTP 200, body `public` |
| GET `/private` không credential | HTTP 401 (yêu cầu xác thực) |
| GET `/private` với `alice` | HTTP 200, body `private: authenticated USER` |
| GET `/admin` với `alice` | HTTP 403 (không có `ROLE_ADMIN`) |

Thông tin HTTP header/log khởi động có thể khác theo môi trường, nhưng mã trạng thái minh họa sự phân biệt **public → authentication → authorization**. `hasRole("USER")` tương ứng authority `ROLE_USER`; ví dụ cố ý **không** giả định vai trò ADMIN tự kế thừa USER.

**Giới hạn của ví dụ:** HTTP Basic gửi credential trên mỗi request; chỉ thử ở localhost hoặc qua TLS, không đưa credential vào source production. Ví dụ chưa minh họa object-level authorization, JWT validation, giới hạn request hay kết nối downstream. Với ứng dụng thực tế, phải bổ sung các kiểm soát theo mô hình đe dọa; chỉ thay Basic bằng JWT không tự giải quyết BOLA hoặc SSRF.

## 6. Mô phỏng một request cần bảo vệ đúng ranh giới

Xét `GET /api/orders/{orderId}` trong hệ thống đa tenant:

1. **Client → ingress:** nhận URL và token; ingress áp giới hạn kết nối/request, chuẩn hóa forwarded headers và dùng HTTPS.
2. **Ingress → WebFlux:** `ServerWebExchange` đi qua `SecurityWebFilterChain`; request không hợp lệ bị từ chối trước khi vào nghiệp vụ.
3. **Token → principal:** resource server xác minh token theo issuer/audience/chữ ký/thời hạn phù hợp, tạo principal/authorities. Claim về tenant chỉ đáng tin sau bước xác minh và kiểm tra phạm vi sử dụng.
4. **Principal → order:** handler/service chỉ lấy `orderId` từ URL như một **định danh cần kiểm tra**, không xem nó là giấy phép truy cập. Nghiệp vụ xác minh người gọi có quyền xem đơn, ví dụ truy vấn theo đồng thời `orderId` và tenant đã được chứng thực.
5. **Order → DB/cache:** mọi truy vấn và cache key phải giữ ranh giới tenant, không chia sẻ key chỉ theo `orderId` nếu ID không toàn cục/an toàn.
6. **Kết quả → client:** chỉ serialize các trường cho phép; không gửi entity chứa secret/PII thừa; log ID tương quan đã lọc thay vì raw bearer token.

Một phác thảo **logic, không phải chương trình độc lập**:

```text
authenticatedTenant = principal.verifiedTenant
order = repository.findByIdAndTenantId(orderId, authenticatedTenant)
if order is missing: return HTTP 404
if policy denies access to order: return HTTP 403
return an approved response DTO (not the raw persistence entity)
```

Điểm mấu chốt là **xác minh danh tính ở filter không thay cho kiểm tra quyền gắn với dữ liệu ở service/repository**. Quy tắc tương tự áp dụng với cập nhật, xóa, tải file và gửi event.

## 7. Các luồng ngoài HTTP cũng mang ranh giới tin cậy

**WebClient và hệ thống khác.** Khi API gọi sang service B, không mặc nhiên chuyển `Authorization` gốc sang mọi URL. Chỉ truyền token khi B là đối tượng nhận được phép, token có audience/scope phù hợp, và có chính sách ủy quyền rõ. Không dùng URL từ request để gọi tài nguyên mạng tùy ý. Xác thực TLS, giới hạn timeout, số kết nối và kích thước phản hồi.

**WebSocket hoặc stream dài.** Xác thực khi handshake giúp biết người mở kết nối nhưng không tự phân quyền mọi message, subscription hoặc topic. Kiểm tra quyền mỗi hành động nhạy cảm, xử lý token hết hiệu lực/chấm dứt quyền theo thiết kế, giới hạn kích thước và tốc độ message. Dữ liệu SSE/Flux đẩy xuống cũng phải lọc đúng người nhận; stream kéo dài không đồng nghĩa quyền tồn tại mãi mãi.

**Message broker / background job.** Producer có thể gửi message sai hoặc bị xâm nhập; consumer cần xác minh schema, nguồn và quyền thực thi. Không coi `userId`, `tenantId` hay `role` trong event tự khai là bằng chứng đủ để làm thao tác có đặc quyền. Bảo vệ bí mật của service account, retry và dead-letter queue khỏi lộ dữ liệu.

**Actuator, diagnostics và logs.** Các endpoint sức khỏe, metrics, config, env hoặc dump có thể tiết lộ cấu hình/chi tiết hệ thống nếu public sai. Chỉ phơi bày thứ cần thiết, tách mạng/phân quyền khi phù hợp, lọc token, cookie, password, PII và tránh lỗi phản hồi chứa stack trace nhạy cảm. Correlation ID do client cung cấp cũng phải được chuẩn hóa để tránh log injection.

## 8. Cách lập threat model đơn giản cho một endpoint

Với mỗi endpoint hoặc luồng message, lần lượt trả lời:

1. **Tài sản nào bị tác động?** Dữ liệu của ai, hành động gì, dịch vụ/tài nguyên nào có thể bị cạn?
2. **Nguồn đầu vào ở đâu?** Client, proxy, JWT/IdP, DB, cache, service ngoài, message broker? Phần nào do kẻ tấn công kiểm soát?
3. **Ranh giới nào được vượt qua?** Ở bước nào một input được biến thành danh tính, quyền, câu truy vấn, URL gọi ra hoặc dữ liệu trả về?
4. **Ai kiểm tra và bằng chứng là gì?** TLS, xác minh token, audience/scope, kiểm quyền object/tenant, validation, allowlist đích, giới hạn tài nguyên, audit.
5. **Bị lạm dụng thì sao?** 401/403/404, timeout/429/413, từ chối request, hạn chế thông tin lỗi, log/anomaly monitoring.
6. **Có thể thử âm tính không?** Token sai, tài nguyên của người khác, giả forwarded header, cross-origin request, body lớn, đường dẫn tới IP nội bộ, subscriber không có quyền.

Mẫu kiểm thử thực tế:

| Tình huống | Kỳ vọng |
|---|---|
| Không có credential / token hết hạn / chữ ký sai | Không vào dữ liệu bảo vệ; phản hồi từ chối phù hợp |
| JWT hợp lệ nhưng sai audience | Không được xem như token dành cho API này |
| USER A truy cập ID thuộc USER B | Bị từ chối dù USER A đã đăng nhập |
| USER A đổi `tenantId` trong query/header/body | Không vượt qua ràng buộc tenant phía server |
| Gửi `X-Forwarded-For` giả từ Internet | Không làm sai định danh nguồn hoặc chính sách giới hạn |
| Origin không được phép hoặc request giả mạo cookie | Chính sách CORS/CSRF áp dụng đúng theo kiểu client |
| Gửi body lớn, stream vô hạn hoặc request dồn dập | Có giới hạn kích thước/thời gian/tài nguyên, không chiếm hệ thống vô hạn |
| WebClient bị nhập URL nội bộ/cloud metadata | Bị chặn theo chính sách đích |
| Truy cập endpoint quản trị/metrics nhạy cảm | Chỉ người/hệ thống được cấp quyền mới dùng được |
| Ngắt kết nối giữa chừng, lỗi downstream | Giải phóng tài nguyên, không lộ dữ liệu, không sinh thao tác ngoài quyền |

## 9. Những nhầm lẫn cần tránh

- **“Reactive nên an toàn hơn.”** Reactive nói về mô hình thực thi; vẫn cần xác thực, phân quyền, giới hạn tài nguyên và kiểm tra dữ liệu.
- **“Gateway đã xác thực là đủ.”** Service sở hữu tài nguyên vẫn phải kiểm quyền theo nghiệp vụ và theo từng object/tenant.
- **“JWT có chữ ký hợp lệ là dùng ở đâu cũng được.”** Phải kiểm issuer, thời hạn, audience, loại token và quyền phù hợp.
- **“CORS chặn hacker gọi API.”** CORS chủ yếu do trình duyệt thực thi; không thay thế bảo mật phía server.
- **“Tắt CSRF là chuẩn cho mọi API reactive.”** Quyết định phụ thuộc loại credential và khả năng trình duyệt tự gửi chúng.
- **“Reactor Context = ThreadLocal.”** Context gắn với luồng reactive/subscription; phải chú ý khi tách subscription, tự tạo thread hoặc chuyển qua hệ thống không truyền context.
- **“Backpressure tự chống DDoS.”** Vẫn cần giới hạn ingress, request, body, connection, concurrency, timeout và tài nguyên.
- **“Nằm trong VPC là dữ liệu đáng tin.”** Service, queue và callback bên trong vẫn có thể bị cấu hình sai hoặc bị xâm nhập.

## 10. Ghi nhớ

Hãy vẽ đường đi của **request → xác thực → quyết định quyền → dữ liệu → dịch vụ ngoài → phản hồi**, đánh dấu mỗi lần dữ liệu/danh tính/quyền vượt sang vùng khác. Với Spring Security WebFlux, các lớp bảo vệ phải phối hợp: cấu hình `SecurityWebFilterChain` đúng, lấy ngữ cảnh bảo mật theo Reactor, kiểm quyền trên tài nguyên, kiểm soát đầu vào/đầu ra và bảo vệ mọi lời gọi downstream. Một request được xác thực chỉ là **đầu vào của quyết định ủy quyền**, không phải bảo chứng an toàn cho toàn bộ luồng.