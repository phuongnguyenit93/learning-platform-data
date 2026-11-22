# Cân bằng tải, kho phiên chia sẻ và xử lý sự cố Redis trong Spring Security WebFlux

## 1. Mục tiêu và phạm vi

Bài này thuộc nhóm **Triển khai an toàn** của **Spring Security - reactive**. Sau bài học, bạn cần giải thích được vì sao đăng nhập theo session có thể “mất” khi request đi sang instance khác, cách Spring Session chia sẻ `WebSession` qua Redis, cách triển khai sau load balancer, biện pháp bảo mật cookie/CSRF và quy trình chẩn đoán khi Redis gặp sự cố.

Các ý chính:

- Trong ứng dụng **Spring WebFlux**, session phía server được truy cập qua **`WebSession`**, khác với `HttpSession` của Servlet. Spring Session tích hợp thông qua `WebSessionManager` và `ReactiveSessionRepository`; backend Redis thường dùng `ReactiveRedisSessionRepository`.
- Browser lưu cookie mang **session ID**, còn dữ liệu phiên/danh tính được xác thực nằm tại kho session phía server. Redis không tự biến cookie thành JWT; đây vẫn là **xác thực có trạng thái**.
- Khi nhiều instance cùng dùng **một kho Redis và cùng namespace, định dạng session, chính sách timeout**, bất kỳ instance nào cũng có thể lấy lại phiên bằng cùng session ID. Do đó sticky session thường không bắt buộc chỉ để duy trì đăng nhập.
- Không thể coi Redis là “cache có cũng được” nếu xác thực phụ thuộc vào đó: mất khả năng đọc/ghi session phải được xử lý an toàn, không tự đổi sang một danh tính mặc định hoặc bỏ qua bước kiểm tra bảo mật.

## 2. Đường đi của request trong cụm nhiều instance

```text
Browser
  | HTTPS, Cookie: SESSION=<opaque-session-id>
  v
Load balancer / reverse proxy (TLS termination, health/routing)
  | round robin / least connections
  +------------------+------------------+
  |                                     |
  v                                     v
Spring WebFlux instance A               Spring WebFlux instance B
SecurityWebFilterChain                  SecurityWebFilterChain
WebSessionManager                       WebSessionManager
  |                                     |
  +------------------+------------------+
                     |
                     v
                Redis shared store
             session ID -> WebSession
                         -> session attributes
                         -> SecurityContext (nếu dùng login theo session)
```

Một luồng truy cập khi đã đăng nhập bằng form login:

1. Người dùng gửi credentials qua HTTPS vào instance A. Spring Security xác thực, tạo/lưu `SecurityContext` thông qua `ServerSecurityContextRepository` dùng `WebSession` (điển hình là `WebSessionServerSecurityContextRepository`).
2. `WebSessionManager` được Spring Session cấu hình lưu session trong Redis. Phản hồi gửi cookie phiên có session ID ngẫu nhiên.
3. Request kế tiếp có thể vào instance B. B đọc ID từ cookie, lấy `WebSession` trong Redis, khôi phục `SecurityContext` và thực thi authorization; **B không cần truy cập bộ nhớ của A**.
4. Khi logout hoặc phiên hết hạn, dữ liệu tương ứng không còn hợp lệ; trình duyệt mang cookie cũ không tự được xác thực.

**Điều kiện quan trọng:** mọi replica dùng cùng backend/namespace/session serializer tương thích và cùng cơ chế xác thực. Session đã lưu trong memory của riêng một pod không tự được chia sẻ khi ta chỉ lắp Redis client vào ứng dụng; cần đúng tích hợp Spring Session.

**Phân biệt với Bearer JWT:** Resource Server thuần stateless kiểm tra Bearer token theo từng request thường không cần session kho Redis. Chỉ triển khai Redis session khi các luồng thực sự dùng `WebSession`, ví dụ form login, OAuth2 login authorization request, session-backed CSRF hoặc ứng dụng lưu trạng thái theo phiên. Không ép mọi API bearer token phải phụ thuộc Redis.

## 3. Tại sao chỉ bật sticky session chưa đủ?

**Sticky session/session affinity** cố gắng gửi các request của một client về cùng một instance, dựa trên cookie của load balancer, IP hoặc cách khác. Nó có thể giảm chuyển tuyến, nhưng:

- Khi pod được thay thế, scale-in, mất node hoặc deploy rolling, session nằm trong RAM của pod cũ vẫn mất.
- IP-based affinity dễ sai với NAT/proxy; người dùng có thể bị đổi IP. Cookie affinity của LB cũng không cứu được session khi node hỏng.
- Sticky session không thay thế replication và cơ chế lưu phiên đáng tin. Redis chung giúp instance khác tiếp quản khi pod lỗi hoặc bị drain.
- Kết nối WebSocket đang mở luôn gắn với một kết nối cụ thể; việc Redis chia sẻ `WebSession` **không** tự phân phối message, room subscription hoặc trạng thái kết nối WebSocket giữa các pod. Các thành phần đó cần kiến trúc riêng.
- Không nên dùng phiên để chứa dữ liệu nghiệp vụ lớn hoặc trạng thái giao dịch đang thay đổi; các cập nhật song song trên cùng một session có thể tranh chấp/ghi đè. Trạng thái nghiệp vụ phải nằm ở database hay hệ thống xử lý tương ứng.

Với ứng dụng session-backed thông thường, chọn load balancing cân bằng giữa các instance và Spring Session Redis chung, sau đó chứng minh có thể chuyển qua node B mà vẫn giữ trạng thái đã xác thực. Sticky session có thể tồn tại vì lý do vận hành khác, nhưng không được là điều kiện duy nhất để phiên sống sót.

## 4. Cấu hình mẫu Spring Boot 3.5 + WebFlux + Spring Session Redis

Ví dụ dùng **Java 17+, Spring Boot 3.5.16, Maven**, Redis cục bộ khi phát triển. Đây là ứng dụng WebFlux session-backed dùng form login để thử chuyển node. `demo` / `demo-pass` **chỉ dùng trong môi trường học tập**, tuyệt đối không dùng user/password này trong production.

Cấu trúc:

```text
reactive-session-demo/
├── pom.xml
└── src/main/
    ├── java/example/sessiondemo/
    │   ├── SessionDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── SessionCookieConfig.java
    │   └── WhoAmIController.java
    └── resources/application.yml
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>reactive-session-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Trong Spring Boot **3.x**, `spring-session-data-redis` kết hợp reactive Redis starter và auto-configuration là đường đi rõ ràng. Một số tài liệu Spring Boot **4.x** dùng artifact starter tên `spring-boot-starter-session-data-redis`; không sao chép artifact của Boot 4 vào project Boot 3 theo thói quen. `spring-session-data-redis` được Boot quản lý version theo BOM.

**`src/main/java/example/sessiondemo/SessionDemoApplication.java`**:

```java
package example.sessiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

**`src/main/java/example/sessiondemo/SecurityConfig.java`**:

```java
package example.sessiondemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health/**").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails demo = User.withUsername("demo")
            .password("{noop}demo-pass") // Chỉ dùng trong ví dụ local.
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(demo);
    }
}
```

Spring Security WebFlux mặc định bật CSRF cho các request cần bảo vệ; **không tắt CSRF chỉ để làm curl cho dễ**. Form login đã cấu hình dùng `WebSession` để ghi lại trạng thái xác thực, và cookie giúp trình duyệt mang session ID qua các request. Ở production, thay in-memory user bằng cơ chế định danh phù hợp (IdP/LDAP/user store) và password encoder an toàn.

**`src/main/java/example/sessiondemo/SessionCookieConfig.java`**:

```java
package example.sessiondemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class SessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver(
            @Value("${app.session.cookie-secure:true}") boolean secure) {
        CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(secure)
            .sameSite("Lax"));
        return resolver;
    }
}
```

`WebSessionIdResolver` là cơ chế tùy chỉnh cookie phù hợp **WebFlux**. `DefaultCookieSerializer` và `HttpSession` thường gặp trong tài liệu Servlet không phải cách cấu hình cookie chính của ví dụ này. `Secure=true` yêu cầu kết nối HTTPS trong production; để chạy thử HTTP localhost mới chủ động đặt biến `COOKIE_SECURE=false`. Không gửi cookie qua HTTP công khai. `SameSite=Lax` thường phù hợp login same-site; nếu một luồng hợp pháp thực sự cần `SameSite=None` thì phải dùng `Secure` và thiết kế CSRF/CORS tương ứng, không đổi tùy tiện.

**`src/main/java/example/sessiondemo/WhoAmIController.java`**:

```java
package example.sessiondemo;

import java.security.Principal;
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Mono<Map<String, String>> whoami(Mono<Principal> principal) {
        return principal.map(identity -> Map.of(
            "user", identity.getName(),
            "instance", System.getenv().getOrDefault(
                "INSTANCE_ID", "local")
        ));
    }
}
```

Response chỉ cho biết tên user và replica hiện tại. Không đưa session ID, secret hoặc nguyên văn `SecurityContext` vào response/log để “debug”.

**`src/main/resources/application.yml`**:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      connect-timeout: 2s
      timeout: 2s
  session:
    timeout: 30m
    redis:
      namespace: "spring:session:reactive-demo"

app:
  session:
    cookie-secure: ${COOKIE_SECURE:true}

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Spring Boot 3.5 tự cấu hình reactive Spring Session khi các module phù hợp hiện diện, nên mẫu này **không thêm `@EnableRedisWebSession`**. Nếu muốn tự cấu hình bằng annotation `@EnableRedisWebSession`, Spring Boot sẽ nhường quyền auto-configuration tương ứng; khi ấy phải hiểu thuộc tính trên annotation như `redisNamespace` và timeout để tránh nghĩ rằng mọi property của auto-config còn áp dụng y nguyên.

`spring.session.timeout` là timeout session khi dùng Spring Session. `spring.session.redis.namespace` tách dữ liệu giữa ứng dụng/môi trường và phải **giống nhau** trên mọi instance của cùng một ứng dụng. `spring.data.redis.*` là cấu hình kết nối tới Redis, không phải TTL cookie. Trong production, cấu hình Redis endpoint, chứng thư/TLS, tài khoản ACL và secret qua cơ chế quản lý cấu hình an toàn; không hard-code password trong YAML. Đặt timeout hợp lý để một sự cố Redis không giữ vô hạn các luồng đang chờ.

### Chạy demo hai instance

Trên máy local có Docker, có thể khởi động Redis thử nghiệm:

```bash
docker run --rm --name demo-redis -p 6379:6379 redis:7.4
```

Mở hai terminal khác nhau trong thư mục project (cú pháp dưới đây dành cho Bash):

```bash
# Terminal 1
SERVER_PORT=8081 INSTANCE_ID=node-a COOKIE_SECURE=false mvn spring-boot:run
```

```bash
# Terminal 2
SERVER_PORT=8082 INSTANCE_ID=node-b COOKIE_SECURE=false mvn spring-boot:run
```

Truy cập `http://localhost:8081/whoami` bằng trình duyệt; Spring Security sẽ chuyển sang trang đăng nhập. Đăng nhập user `demo`, password `demo-pass`, rồi mở `http://localhost:8082/whoami` trên **cùng trình duyệt**. Khi hai instance trỏ đến cùng Redis và cùng namespace, response kỳ vọng có cùng `"user": "demo"` nhưng `"instance"` đổi từ `"node-a"` sang `"node-b"`.

Lưu ý: cookie thường gắn với **hostname và path, không gắn với TCP port**, nên hai URL `localhost:8081` và `localhost:8082` có thể dùng chung cookie với thiết lập `path("/")`. Việc đăng nhập thực sự qua browser tự xử lý CSRF của form; một lệnh POST `/login` không kèm CSRF token hợp lệ có thể bị 403 và **không** phải lỗi Redis. Cần có Redis và Maven trong môi trường trước khi chạy. Không coi Docker command không có xác thực/TLS ở trên là cấu hình production.

## 5. Cấu hình load balancer và cookie để tránh “mất đăng nhập”

| Thành phần | Cần thống nhất/kiểm tra | Lỗi hay gặp |
| --- | --- | --- |
| Các app replica | Một ứng dụng, cùng namespace Redis, schema serialization tương thích, timezone/đồng hồ đồng bộ | Replica B đọc khóa khác namespace hoặc không deserialize được session do A viết |
| Load balancer | Gửi request đến các instance đang sẵn sàng; drain phiên kết nối khi deploy; truyền đúng host và scheme từ proxy tin cậy | Redirect login sai `http`/`https`, loop 302 |
| Cookie | `Secure` với HTTPS, `HttpOnly`, `SameSite` phù hợp, path/domain chính xác, tên ổn định | Browser không gửi cookie hoặc 2 ứng dụng ghi đè cùng tên cookie |
| Redis | HA nếu cần, DNS/service discovery đúng, ACL, TLS, latency và timeout hợp lý | `READONLY`, `NOAUTH`, timeout, mất keys do eviction |
| Spring Security | Bảo vệ endpoint, CSRF cho cookie-backed requests, session fixation protection, logout | Login hoạt động nhưng request thay đổi trạng thái 403; logout không vô hiệu phiên như mong đợi |
| Health checks | Liveness phản ánh tiến trình; readiness phản ánh khả năng phục vụ request cần Redis | Mất Redis gây restart hàng loạt hoặc LB vẫn đưa request vào instance lỗi |

**Header từ proxy:** ở deployment có TLS termination, app có thể nhìn thấy kết nối nội bộ HTTP. Cấu hình forwarded headers theo nền tảng, chẳng hạn `server.forward-headers-strategy=framework` trong Boot khi được triển khai sau **proxy tin cậy**. Chỉ tin `Forwarded`/`X-Forwarded-*` do load balancer của mình ghi và chặn/ghi đè giá trị client tự giả mạo. Nếu không, URL redirect, cookie Secure hoặc logic theo hostname có thể sai; thậm chí xuất hiện spoofing khi ứng dụng dùng forwarded headers vào quyết định bảo mật.

**Tên và domain cookie:** nên để host-only cookie khi ứng dụng chỉ cần một hostname. Đặt cookie domain quá rộng như `.example.com` làm tăng bề mặt chia sẻ cookie giữa subdomain. Nếu nhiều app chạy cùng domain/path, đặt cookie name/namespace rõ ràng và thiết kế phạm vi cookie để tránh client gửi một session ID không thuộc ứng dụng đang nhận.

**CSRF:** trong ứng dụng cookie-based, browser tự gửi cookie trên request liên quan. Bảo vệ CSRF phải tương thích với cả hai replica. Mặc định WebFlux Spring Security dùng `WebSessionServerCsrfTokenRepository` cho expected CSRF token; khi WebSession chia sẻ qua Redis, replica B có thể kiểm chứng CSRF token do phiên khởi tạo ở A. `SameSite` là lớp phòng vệ bổ sung, **không thay thế** chính sách CSRF cho luồng có nguy cơ.

**Session fixation:** sau khi đăng nhập, session ID cần được thay/rotate theo cơ chế bảo vệ Spring Security. `WebSessionServerSecurityContextRepository` đổi session ID khi lưu `SecurityContext` để giảm nguy cơ session fixation. Không tự giữ ID cố định, tái sử dụng ID do người dùng cung cấp hoặc tiết lộ ID qua URL.

## 6. Redis là hệ thống phụ thuộc quan trọng của xác thực theo session

### 6.1. Dữ liệu, tuổi thọ và bộ nhớ

Spring Session Redis lưu thông tin session dưới namespace riêng, ví dụ tiền tố `spring:session:reactive-demo`. Các key session thường có hậu tố session ID và Redis expiration liên quan. Session có **max inactive interval**, chứ không nhất thiết là thời điểm kết thúc tuyệt đối được gắn cứng từ lúc login. Hoạt động truy cập hợp lệ có thể cập nhật last-accessed time; cách tối ưu lệnh ghi phụ thuộc repository/version.

- Đặt thời gian chờ phù hợp mức rủi ro: 15–30 phút inactivity có thể hợp lý cho hệ thống cần xác thực; các hệ thống nhạy cảm cần cân nhắc thêm absolute session lifetime, reauthentication và kiểm soát đa thiết bị.
- Cookie expiration và server-side session expiration là **hai khái niệm khác nhau**. Cookie còn tồn tại không chứng minh session tương ứng còn trong Redis.
- Không coi TTL của một key cụ thể luôn bằng `spring.session.timeout` tại mọi thời điểm: Spring Session có thể dùng key phụ/expiration strategy khác nhau; cần hiểu phiên bản repository đang chạy.
- `maxmemory-policy` và eviction có thể làm mất phiên trước thời hạn. Chính sách không chủ động evict session, dự trù dung lượng và cảnh báo trước khi cạn bộ nhớ thường phù hợp hơn nếu phiên là nguồn xác thực; `noeviction` khiến lệnh ghi thất bại khi full memory, nên vẫn phải có cảnh báo và capacity planning.
- Mặc định serialization của Spring Session Redis có thể là Java Serialization. Rolling deployment đa phiên bản cần kiểm tra khả năng deserialize (class name, `serialVersionUID`, cấu trúc principal/authorities). Nếu chọn JSON serializer, phải cấu hình security type mapping/allowlist và tương thích `SecurityContext`, không bật polymorphic deserialization không giới hạn.

### 6.2. Redis HA, failover và các giới hạn

Redis đơn lẻ là single point of failure. Các môi trường cần availability cao thường dùng Redis managed HA, Sentinel hoặc Cluster phù hợp với driver/architecture. App phải trỏ vào endpoint hoặc topology chính xác; không hard-code địa chỉ của một master cũ khi hệ thống quản lý failover.

Replication Redis thường bất đồng bộ; sau failover có thể có một cửa sổ mất cập nhật mới nhất. Hệ quả có thể là một số session/logouts mới chưa được tái hiện hoàn toàn trên replica mới. Với các yêu cầu bảo mật cao, cần xác định rõ mô hình consistency/revocation bổ sung, không mặc định Redis replication cung cấp giao dịch xác thực đồng bộ tuyệt đối.

`RedisIndexedSessionRepository` và biến thể indexed reactive có tính năng chỉ mục/sự kiện thêm; không bật chỉ để “Redis có vẻ production hơn”. Nếu cần tìm phiên theo principal hoặc xử lý expired events, phải đọc kỹ giới hạn Pub/Sub, các node Redis Cluster và đặc điểm event expiration. Không dùng event expiration làm nguồn duy nhất cho nghiệp vụ bắt buộc chính xác từng giây.

### 6.3. Khi Redis lỗi, fail closed như thế nào?

Khi request cần session mà Redis không đọc/ghi được, đây là **lỗi phụ thuộc hạ tầng**. Không chuyển sang local `ConcurrentHashMap` hay tạo một `SecurityContext` tùy ý để request “vẫn 200”. Cũng không biến lỗi Redis thành `Mono.empty()` rồi coi như người dùng chắc chắn chưa đăng nhập: điều này che khuất sự cố, làm sai quan sát và có thể tạo đường đi bảo mật không lường trước.

Chiến lược vận hành:

1. Giới hạn timeout, kết nối và retry có kiểm soát. Retry ngắn với backoff/jitter cho lỗi transient và chú ý tổng thời gian request; retry không giới hạn sẽ nhân tải lên Redis đang quá tải.
2. Các endpoint cần xác thực session không được thực thi hành động có quyền khi chưa truy xuất/xác minh được session. Trả lỗi có kiểm soát (ví dụ HTTP **503** nếu app định nghĩa error mapping này) và `Retry-After` khi phù hợp; thực tế framework có thể trả **5xx** khác nếu chưa cấu hình. Không tuyên bố Spring tự mặc định 503.
3. Phân biệt lỗi Redis và `401/403`: 401/redirect login có thể do không có phiên hay đã hết hạn, 403 do không đủ quyền/CSRF; Redis timeout là tình trạng dependency và cần ghi nhận riêng.
4. Readiness phản ánh khả năng phục vụ nghiệp vụ phụ thuộc Redis; liveness không nhất thiết thất bại chỉ vì Redis đang ngắt ngắn hạn, tránh restart storm. Dùng health/readiness với chính sách rõ ràng, tránh để toàn bộ replica rời LB nếu điều đó làm sự cố lan rộng.
5. Chỉ phục hồi nhận lưu lượng khi kết nối, thao tác session và tuyến cân bằng tải đã ổn định. Có thể yêu cầu người dùng đăng nhập lại nếu phiên mất do failover/eviction; phải giải thích điều này thay vì giả định mọi phiên đều phục hồi.

## 7. Runbook xử lý sự cố Redis trong production

**Bước 1 — Xác định triệu chứng và phạm vi.** Phân biệt: người dùng đăng nhập thành công ở node A nhưng sang B bị chuyển về `/login`; đăng nhập loop liên tục; 5xx tăng; request treo; hoặc mất phiên đồng loạt sau failover. Ghi thời điểm, namespace, môi trường, node app/Redis, phiên bản deploy và tình trạng load balancer; không ghi thô cookie/session ID vào ticket/log.

**Bước 2 — Kiểm tra ứng dụng và tuyến mạng.** Xem health, connection/command timeout từ Lettuce, DNS/TLS/ACL, cấu hình Redis chung giữa replica, log serialize/deserialize và trạng thái thiết lập proxy cookie. Nếu một replica sai namespace, rollback/cập nhật cấu hình replica đó theo quy trình deployment; không xóa toàn Redis.

**Bước 3 — Kiểm tra Redis theo cách ít xâm lấn.** Dùng quyền đọc/quan sát thích hợp (lệnh minh họa cho Redis local, điều chỉnh TLS/ACL/port cho môi trường thật):

```bash
redis-cli -h localhost -p 6379 PING
redis-cli -h localhost -p 6379 INFO replication
redis-cli -h localhost -p 6379 INFO memory
redis-cli -h localhost -p 6379 INFO stats
redis-cli -h localhost -p 6379 INFO persistence
redis-cli -h localhost -p 6379 SLOWLOG GET 10
```

`PONG` chỉ chứng minh kết nối tới một Redis endpoint, **không đủ** để kết luận tất cả session read/write và auth flow lành mạnh. Quan sát `role`, replication lag, `used_memory`, `maxmemory`, `evicted_keys`, `expired_keys`, rejected connections, command latency, slowlog và CPU/network. `SLOWLOG` có thể chứa đối số lệnh nhạy cảm; kiểm soát quyền xem và không chép nguyên văn vào hệ thống log công khai.

Khi cần kiểm tra đúng một key thuộc môi trường thử nghiệm, dùng `SCAN` thay vì `KEYS *`:

```bash
redis-cli -h localhost -p 6379 \
  --scan --pattern 'spring:session:reactive-demo:sessions:*'
```

Với session ID đã được xác định an toàn qua công cụ nội bộ, kiểm tra TTL theo đúng namespace:

```bash
redis-cli -h localhost -p 6379 \
  TTL 'spring:session:reactive-demo:sessions:<session-id>'
```

`TTL = -2` có nghĩa key không tồn tại, `TTL = -1` là key không có expiration, còn giá trị không âm là số giây còn lại. Việc mất key có thể do hết hạn/eviction/logout/chuyển namespace, không tự kết luận “Redis đã đánh mất session” chỉ từ một kết quả. Hạn chế thao tác đọc các giá trị nhạy cảm trong session; session có thể chứa principal/metadata người dùng.

**Bước 4 — Khoanh vùng theo dấu hiệu:**

| Dấu hiệu | Nguyên nhân có khả năng | Hướng kiểm chứng và xử lý |
| --- | --- | --- |
| Chỉ sang replica B mới bị logout | B không dùng Redis Spring Session, sai namespace, sai cookie hoặc serializer | So cấu hình đã triển khai; thử cùng cookie qua A/B, xem lỗi đọc session |
| Login liên tục redirect về `/login` | Cookie không được browser lưu/gửi, `Secure` trên HTTP, domain/path/SameSite sai, proxy `X-Forwarded-Proto` sai | Xem Set-Cookie/request Cookie trên DevTools và redirect location, không dump cookie value |
| Đột ngột nhiều 401/redirect login nhưng Redis vẫn chạy | Key session hết TTL, eviction, thay đổi namespace/schema, logout, cookie mất | Kiểm tra `evicted_keys`, TTL, deployment và chính sách session |
| Nhiều 5xx và Lettuce timeout | Redis quá tải, mạng/TLS/DNS, connection không sẵn sàng, failover | Kiểm tra latency, connection errors, endpoint HA, timeout và backoff |
| `READONLY You can't write against a read only replica` | Kết nối ghi tới replica hoặc topology failover chưa cập nhật | Sửa endpoint/Sentinel/Cluster topology và quyền ghi; không buộc ghi vào replica |
| `NOAUTH`/`WRONGPASS`/`NOPERM` | ACL, tài khoản hoặc secret sai/quyền thiếu | Kiểm tra rotation secret, ACL, TLS và quyền lệnh cần thiết |
| `OOM command not allowed` | Redis chạm `maxmemory`, chính sách `noeviction` làm ghi thất bại | Mở rộng capacity, giảm session data/TTL phù hợp, cảnh báo; không xóa hàng loạt |
| `ClassNotFoundException`/deserialization | Version app cũ/mới không tương thích với object trong Redis | Thiết kế migration/serialization compatibility; rollout có kiểm soát |
| 403 ở POST sau login | CSRF token thiếu/sai, session không nhất quán, origin/cookie policy | Đối chiếu token form/header và session, không tắt CSRF để che lỗi |
| Tăng kết nối/CPU khi Redis chậm | Retry storm, pool/timeout sai, command quá nặng | Hạn chế retry, giảm thundering herd, scale/repair backend |

**Bước 5 — Phục hồi có kiểm soát.** Nếu Redis endpoint lỗi, chuyển sang node/endpoint HA đúng theo cơ chế vận hành. Nếu hết memory, mở rộng dung lượng và rà soát policy; nếu cấu hình mới làm sai namespace/serializer, rollback phiên bản/cấu hình tương thích. Với failover có mất dữ liệu session, chấp nhận yêu cầu đăng nhập lại khi cần và truyền thông cho người dùng. Không dùng `FLUSHALL`, `FLUSHDB`, `KEYS * | DEL`, hay sửa giá trị `sessionAttr:*` tùy tiện như cách xử lý mặc định.

**Bước 6 — Hậu kiểm.** Chạy lại các ca chuyển node, login/logout, expiry và hoạt động khi Redis tạm ngắt; đo tốc độ 401/403/5xx và lỗi Lettuce sau phục hồi. Phân loại nguyên nhân gốc: mạng, topology, capacity, serializer, ứng dụng, cookie hoặc CSRF. Ghi action items có owner và chỉ số cảnh báo.

## 8. Quan sát hệ thống, SLO và bảo mật Redis

Để phát hiện sớm lỗi, theo dõi tối thiểu:

- **App/Security:** tỷ lệ login thành công/thất bại; redirect loop; HTTP 401/403/5xx; p95/p99 latency endpoint phụ thuộc session; số lỗi tạo/đọc/lưu/xóa session; số lỗi serialize/deserialize theo version.
- **Client Redis:** connection failure, reconnect, command timeout, pool saturation (nếu dùng pooling), thời gian chờ lệnh GET/HSET/EXPIRE, retry count và queue depth.
- **Redis/HA:** memory, eviction, expired keys, connected clients, ops/sec, replication lag, failover, `READONLY`/ACL errors và sức khỏe endpoint quản lý.
- **Load balancer:** upstream 5xx, healthy backends, latency, số kết nối được drain, tỷ lệ chuyển tuyến A/B trong bài test.
- **Bảo mật:** TLS với Redis, ACL least privilege, không mở Redis trực tiếp ra Internet, secrets có rotation, tách namespace giữa production/staging và ứng dụng khác. Không ghi session ID, giá trị cookie, session payload hoặc password vào log/trace. Tùy chính sách, hash/pseudonymize session ID khi phải correlate request.

**Readiness** nên có kiểm tra đủ tin cậy rằng dịch vụ có thể xử lý request cần session. Actuator Redis health indicator có thể đóng góp vào health group; hãy kiểm tra cấu hình probes và thực tế deploy thay vì cho rằng nó tự có trong readiness group. **Liveness** là tín hiệu app có còn hoạt động để có thể tự phục hồi hay không; không gắn restart liveness vào mọi lỗi Redis transient.

## 9. Kiểm thử tích hợp trước khi triển khai

Một môi trường staging hữu ích có tối thiểu hai instance cùng một Redis thử nghiệm, cân bằng tải không cần session affinity và khả năng chủ động làm lỗi Redis. Các tiêu chí sau nên được xác nhận bằng browser thật hoặc integration tests dùng HTTP thật:

| Kịch bản | Cách thực hiện | Kỳ vọng |
| --- | --- | --- |
| Chuyển node sau login | Đăng nhập qua A; dùng cùng cookie để gọi `/whoami` ở B | B xác thực đúng user, không login lại |
| Restart pod | Login, thay thế A, gọi B | Session vẫn tồn tại khi Redis không mất dữ liệu |
| Load balancing liên tục | Gọi endpoint bảo vệ nhiều lần qua LB, quan sát instance ID | Không bị mất quyền khi request đổi replica |
| Logout | Logout qua A rồi thử cookie cũ ở B | Không còn được truy cập nội dung bảo vệ |
| Expiry | Dùng timeout ngắn chỉ trong test, để idle đủ lâu rồi gọi lại | Bị yêu cầu xác thực lại; không tự tạo quyền |
| Redis ngừng kết nối | Chặn kết nối/stop Redis thử nghiệm trong lúc có phiên | Request cần Redis không được thực thi thành công với quyền giả; ghi nhận lỗi phụ thuộc |
| Redis phục hồi | Khôi phục kết nối, kiểm tra health và request | Phục hồi có kiểm soát; session còn hay mất tùy persistence/HA |
| Chạy 2 version song song | Rolling upgrade có thay đổi class session | Không có lỗi deserialize/`ClassNotFoundException` |
| Cookie bị sửa/đánh cắp | Thay ID ngẫu nhiên hoặc mất cookie; thực hiện kiểm thử bảo mật hợp pháp | ID không hợp lệ không được nhận; cookie cần TLS, Secure, HttpOnly và CSRF |
| Concurrent requests | Hai request cùng cập nhật thuộc tính session | Hiểu rõ hành vi ghi cuối/conflict; không dùng session làm nguồn sự thật cho nghiệp vụ |
| Redis failover | Chuyển primary qua cơ chế HA thử nghiệm | Driver reconnect và request xử lý an toàn, có cảnh báo nếu session thất lạc |

Đối với WebFlux, có thể dùng `WebTestClient` để thử authorization/CSRF ở mức ứng dụng; **để chứng minh chia sẻ session giữa các replica thực**, cần hai application context/process (hoặc hai server instance) và **Redis thật trong test** như container tích hợp, bởi `WebTestClient` gắn vào một context hay `mockAuthentication()` không chứng minh replication. Spring Session không thay thế việc test đường đi cookie qua load balancer.

Một lỗi nguy hiểm là test login tại A rồi chỉ kiểm HTTP 200 ở A; nó bỏ sót việc B đang dùng session repository local. Một lỗi khác là dùng `mockUser()`/`mockAuthentication()` để giả đăng nhập tại B: bài test sẽ xanh dù Redis hoàn toàn không hoạt động, vì danh tính đã được tiêm sẵn.

## 10. Danh sách kiểm tra triển khai an toàn

1. Mọi instance chạy WebFlux đều dùng **Spring Session + reactive Redis** cùng namespace/serializer, và không vô tình dùng `HttpSession` filter kiểu Servlet.
2. Load balancer kiểm tra readiness, dùng TLS, truyền đúng forwarded headers qua proxy tin cậy, có draining khi rollout và không bắt buộc sticky chỉ để giữ phiên.
3. Cookie mang session ID có `HttpOnly`, `Secure` trong production, `SameSite`, domain và path đúng; test thật trên domain production-like. CSRF vẫn được bật cho form login/cookie auth.
4. Redis có capacity, TTL và eviction policy phù hợp, mạng nội bộ an toàn, TLS, ACL/secret rotation, HA và kế hoạch failover; xem xét giới hạn consistency khi replication.
5. Lưu dữ liệu phiên tối giản và tương thích khi nâng cấp; không lưu bí mật dài hạn, dữ liệu lớn hay trạng thái nghiệp vụ quan trọng trong session.
6. Lỗi Redis được nhận diện thành lỗi hạ tầng, có timeout và chiến lược fail-closed. Không fallback sang phiên in-memory hoặc bỏ kiểm tra auth.
7. Monitoring/alerts và runbook phân biệt lỗi cookie, CSRF, Redis, topology, serializer và deploy. Đã test đổi node, logout, expiry, Redis outage và recovery.

## Tài liệu chính thức để tra cứu

- Spring Boot 3.5 — Spring Session (reactive auto-configuration): https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html
- Spring Boot 3.5 — Common Application Properties (`spring.session.*`, `spring.data.redis.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session — `ReactiveSessionRepository`, `@EnableRedisWebSession`: https://docs.spring.io/spring-session/reference/api.html
- Spring Session — Redis configuration, serialization, namespace: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session — Common Configuration (`CookieWebSessionIdResolver`): https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
