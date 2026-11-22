# Chia sẻ phiên giữa các nút bằng Spring Session và Redis reactive

## Mục tiêu học tập

Trong ứng dụng **Spring Security - reactive**, một người dùng có thể đăng nhập qua instance A nhưng request kế tiếp lại được load balancer chuyển đến instance B. Nếu trạng thái đăng nhập chỉ nằm trong RAM của A, B sẽ không thấy `SecurityContext` và có thể yêu cầu đăng nhập lại. **Spring Session với Redis reactive** đưa trạng thái `WebSession` vào kho chia sẻ, để các nút WebFlux truy cập cùng một phiên qua session ID.

Sau bài học thuộc nhóm **Phiên và đăng xuất**, bạn sẽ:

1. Giải thích vì sao phải chia sẻ session khi scale ứng dụng Spring WebFlux theo chiều ngang.
2. Phân biệt `WebSession`, `ServerSecurityContextRepository`, `ReactiveSessionRepository`, `WebSessionManager`, Redis và cookie `SESSION`.
3. Thiết lập Spring Boot WebFlux dùng `spring-session-data-redis` và kết nối Redis **reactive**.
4. Chạy **hai instance ứng dụng** trên các cổng khác nhau, kiểm chứng cookie được giữ và dữ liệu phiên đi qua nút A → B → A.
5. Xác nhận `SecurityContext` của Spring Security form login được nạp ở nút B sau khi người dùng đăng nhập ở nút A.
6. Hiểu expiration/TTL, logout, rotation session ID, đồng thời ghi session, serialization, Redis outage và giới hạn consistency.
7. Kiểm thử tự động phần cơ bản bằng `WebTestClient`, rồi thực hiện bài kiểm thử xuyên nút bằng HTTP thực tế.
8. Thiết kế vận hành an toàn: namespace, cookie, Redis ACL/TLS, phiên bản triển khai, rate limit, observability và fail-closed.

Đây là hướng dẫn cho **WebFlux**. Spring Session ở thế giới Servlet cũng lưu session vào Redis, nhưng sử dụng `HttpSession`, `SessionRepositoryFilter` và các annotation `@EnableRedisHttpSession`; chúng **không phải** API của `WebSession` reactive.

## 1. Vấn đề: tại sao đăng nhập ở A rồi sang B lại mất phiên?

Giả sử một dịch vụ WebFlux có hai pod:

```text
                         Browser
                    Cookie: SESSION=S123
                              |
                              v
                       Load balancer
                         /         \
                        v           v
                  Node A           Node B
                  :8081            :8082
                     |                |
                  Memory A         Memory B
                  S123 có auth     Không có S123

Kết quả: user login ở A; request sau vào B không được khôi phục
         SecurityContext nếu mỗi node dùng session lưu cục bộ.
```

Trong mô hình chỉ lưu RAM, session có thể mất khi node restart/scale down và request chuyển nút thường nhận session khác. “Sticky sessions” tại load balancer có thể giảm trường hợp request chuyển nút, nhưng không tự bảo vệ khi node chết, không tạo kho phiên dùng chung và không giải quyết nhiều thay đổi triển khai.

Mô hình mong muốn:

```text
                            Browser
                     Cookie: SESSION=S123
                               |
                               v
                        Load balancer
                         /          \
                        v            v
                   Node A          Node B
                   WebFlux         WebFlux
                       \             /
                        \           /
                         v         v
                       Redis shared
                   session key for S123
                   + attributes
                   + SecurityContext

A lưu dữ liệu dưới session S123. B nhận cùng session ID và nạp
dữ liệu ấy từ Redis. Cả hai node có thể phục vụ request hợp lệ.
```

**Quan trọng:** Cookie chỉ mang một **định danh phiên** được server sử dụng để tìm session. Redis lưu dữ liệu phiên phía server, không phải gửi `SecurityContext` nguyên vẹn cho browser. Chia sẻ Redis không tự làm một request trở nên “đã xác thực”: Spring Security vẫn phải kiểm tra context và policy của chain được chọn.

## 2. Các lớp và vai trò

| Thành phần | Thuộc tầng nào? | Vai trò |
| --- | --- | --- |
| `ServerWebExchange` | Spring WebFlux | Chứa HTTP request/response, thuộc tính exchange và đường lấy `WebSession` |
| `WebSession` | Spring WebFlux | Tập thuộc tính session, ID, trạng thái started, lastAccessTime và maxIdleTime |
| `WebSessionManager` | Spring WebFlux | Quyết định cách lấy/tạo/lưu `WebSession` đối với một exchange |
| `ReactiveSessionRepository<? extends Session>` | Spring Session | Tạo, tìm, lưu, xóa `Session` bằng các publisher reactive |
| `ReactiveRedisSessionRepository` | Spring Session Data Redis | Cài đặt `ReactiveSessionRepository` bằng Redis reactive |
| `ReactiveRedisConnectionFactory` | Spring Data Redis | Kết nối Redis không chặn theo API reactive, thường qua Lettuce |
| `ServerSecurityContextRepository` | Spring Security reactive | Lưu/nạp `SecurityContext` theo `ServerWebExchange` |
| `WebSessionServerSecurityContextRepository` | Spring Security reactive | Lưu `SecurityContext` **làm một thuộc tính của WebSession** |
| `ReactiveSecurityContextHolder` | Spring Security/Reactor | Truyền security context trong Reactor Context của **một request** |
| Cookie `SESSION` | HTTP client | Cho biết session ID để các node tìm cùng phiên |

Hai chữ “repository” không có nghĩa cùng một nhiệm vụ:

- `ServerSecurityContextRepository` ở tầng **bảo mật** biết lưu/nạp `SecurityContext` của Spring Security.
- `ReactiveSessionRepository` ở tầng **session storage** biết lưu/nạp `Session` của Spring Session, gồm các attributes.
- `WebSessionServerSecurityContextRepository` sử dụng `WebSession`. Khi `WebSessionManager` được thay bằng phiên bản Redis-backed, context nằm trong `WebSession` cũng được đưa xuống Redis.
- `ReactiveSecurityContextHolder` không lưu session; nó cung cấp context cho publisher/subscriber đang chạy.

Vì vậy, chỉ gắn một bean `ReactiveRedisTemplate` vào ứng dụng **không tự chia sẻ session**. Cần cấu hình Spring Session để `WebSessionManager` được thay bằng loại dùng `ReactiveSessionRepository`.

## 3. Đường đi của session trong một HTTP request

### 3.1. Lần đầu truy cập

```text
GET /public/touch  (chưa có cookie SESSION)
        |
        v
WebSessionManager mở/tạo WebSession
        |
        v
Handler đặt session attribute demo.visits = 1
        |
        v
Spring Session ghi session vào Redis
        |
        v
Response Set-Cookie: SESSION=<session-id>
        |
        v
Browser giữ ID, không giữ dữ liệu demo.visits
```

Spring Session thường **chỉ cần lưu một session khi session đã được sử dụng/khởi tạo và có thay đổi tương ứng**; không suy ra mọi request vô danh sẽ tạo bản ghi Redis. Với ví dụ bên dưới, endpoint `/public/touch` chủ động `start()` và gắn attribute nên session có lý do để được ghi.

### 3.2. Request tiếp theo vào node khác

```text
GET /public/touch  Cookie: SESSION=S123
        |
        v
Node B -> Spring Session WebSessionManager
        |
        v
ReactiveSessionRepository.findById("S123")
        |
        v
Redis trả session attributes từ lần trước
        |
        v
Node B cập nhật demo.visits 1 -> 2
        |
        v
Response JSON: node-b, visits=2
        |
        v
Session được persist theo cấu hình save/flush
```

Thứ tự chính xác của việc ghi cuối request là trách nhiệm hạ tầng WebSession/Spring Session. Không tự gọi `ReactiveSessionRepository.save(...)` từ mọi controller chỉ để chắc chắn lưu; hãy để `WebSession` được quản lý bởi framework và dùng API `exchange.getSession()`.

### 3.3. Khi có Spring Security form login

```text
POST /login (credentials đúng + CSRF hợp lệ) tại Node A
        |
        v
ReactiveAuthenticationManager xác thực
        |
        v
SecurityContext chứa Authentication đã xác thực
        |
        v
WebSessionServerSecurityContextRepository.save(...)
        |
        v
WebSession attribute chứa SecurityContext
        |
        v
Spring Session Redis-backed WebSessionManager
        |
        v
Redis ghi dữ liệu session
        |
        v
Browser nhận cookie SESSION hiện hành
        |
        v
GET /me tới Node B với cùng cookie
        |
        v
Redis-backed WebSession được nạp
        |
        v
WebSessionServerSecurityContextRepository.load(...)
        |
        v
ReactiveSecurityContextHolder + authorization
        |
        v
Handler tại Node B thấy cùng principal
```

**Hai lần “load” khác nhau:** Spring Session **load WebSession** bằng ID; Spring Security **load SecurityContext từ WebSession**. Khi làm việc đúng, authentication có thể sống qua nhiều node mà ứng dụng không cần chia sẻ Java object trong RAM giữa process.

## 4. Cấu hình Spring Session Redis reactive bằng Spring Boot

Với Spring Boot WebFlux 3.3.x, khi Spring Session Redis nằm trên classpath và có kết nối Redis reactive, auto-configuration có thể tạo `ReactiveSessionRepository` cùng `WebSessionManager` thích hợp. **Không cần tự thêm `@EnableRedisWebSession` trong ví dụ Boot auto-config**, vì annotation thủ công có thể làm auto-configuration lùi lại và thay đổi cơ chế property binding. Với cấu hình Java thuần không dựa Boot, `@EnableRedisWebSession` là cách bật Redis-backed `WebSessionManager`.

### 4.1. Các dependency cần có

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.session:spring-session-data-redis'
}
```

Với Boot 3.3.13, dùng BOM để quản lý Spring Session, Spring Data Redis và Lettuce tương thích. Đừng dùng riêng `spring-boot-starter-data-redis` đồng bộ rồi cho rằng mọi API đã reactive; hãy kiểm tra đã có `ReactiveRedisConnectionFactory` và `ReactiveSessionRepository`.

Nếu dùng Boot version mới có starter riêng cho Spring Session Redis, dependency có thể được gom theo starter chính thức; nội dung và API nên căn theo phiên bản Boot đang triển khai. Ví dụ này cố định **Spring Boot 3.3.13** để có tọa độ dependency nhất quán.

### 4.2. Các properties phải thống nhất giữa node

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: spring:session:webflux-lab
      flush-mode: on_save
```

Ý nghĩa:

- `spring.data.redis.host/port`: cả node A và B phải cùng tới **một dịch vụ Redis chia sẻ** (hoặc cấu hình Redis HA/cluster được hỗ trợ).
- `spring.session.redis.namespace`: tiền tố Redis dành riêng cho **cùng một ứng dụng**. A và B phải dùng **cùng namespace** để nhìn thấy cùng session; các ứng dụng khác nên dùng namespace khác nhằm tránh đè/hỗn tạp dữ liệu.
- `spring.session.timeout`: thời gian không hoạt động tối đa theo chính sách; sau inactivity timeout, không nên tiếp tục chấp nhận authentication cũ. Lấy giá trị thực từ cấu hình/quan sát, không đoán TTL từ một dòng Redis.
- `spring.session.redis.flush-mode=on_save`: dữ liệu được ghi theo thời điểm save của repository/session pipeline, thay vì cố gắng ghi mỗi thay đổi ngay lập tức. Cần đo mức nhất quán và độ trễ khi có nhiều request đồng thời.

Mỗi node phải thống nhất cả **phiên bản schema dữ liệu session và serializer**. Cùng Redis nhưng deserialization không tương thích vẫn có thể gây lỗi load và mất phiên hiệu dụng.

### 4.3. Nếu cấu hình thủ công không dùng Boot auto

Có thể khai báo cấu hình:

```java
// Mảnh cấu hình Java thuần, KHÔNG thêm song song
// với Boot auto-config trong ví dụ chạy đầy đủ.
@Configuration
@EnableRedisWebSession
class RedisSessionConfig {
    // Cần một ReactiveRedisConnectionFactory phù hợp.
}
```

Import `org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession`. Annotation xuất `WebSessionManager` dùng Redis reactive. Nếu cần theo dõi session events/indexing trên phiên bản hỗ trợ, có `@EnableRedisIndexedWebSession` với các ràng buộc riêng; đừng dùng bản indexed chỉ để “chia sẻ session thông thường”.

**Không nhầm với `@EnableRedisHttpSession`:** annotation đó thuộc Servlet và không thay thế WebFlux `WebSession`.

## 5. Ví dụ đầy đủ chạy hai node với Java 17+

Ví dụ có hai phần chứng minh:

- **`/public/touch`:** không cần đăng nhập, nhưng ghi bộ đếm vào `WebSession`. Có thể dùng `curl` để chứng minh session data đi A → B → A.
- **`/me`:** yêu cầu form login; sau khi đăng nhập ở A, browser gửi cookie sang B và vẫn thấy người dùng đã xác thực.

Đây là demo phát triển cục bộ, không phải bản cấu hình production đầy đủ. Redis container không có mật khẩu chỉ được bind vào `127.0.0.1` để tránh phơi ra mạng.

### 5.1. Cấu trúc

```text
redis-webflux-session-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/ClusterSessionApplication.java
      resources/application.yml
    test/
      java/example/ClusterSessionApplicationTests.java
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'redis-webflux-session-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.session:spring-session-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Cấu hình application.yml

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: spring:session:webflux-lab
      flush-mode: on_save

app:
  node-id: node-local
```

Tham số dòng lệnh `--server.port` và `--app.node-id` sẽ ghi đè giá trị mặc định để tạo hai process. **Không cấu hình namespace khác nhau cho A và B** vì đây là dữ liệu session của cùng một ứng dụng.

### 5.3. Ứng dụng Spring WebFlux và Spring Security

Tạo `src/main/java/example/ClusterSessionApplication.java`:

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ClusterSessionApplication {

    @Value("${app.node-id:node-local}")
    private String nodeId;

    public static void main(String[] args) {
        SpringApplication.run(ClusterSessionApplication.class, args);
    }

    @GetMapping("/")
    public String index() {
        return "Visit /public/touch, then /me";
    }

    @GetMapping("/public/touch")
    public Mono<VisitResponse> touch(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.start();

            Long previous = session.getAttribute("demo.visits");
            long visits = previous == null ? 1L : previous + 1L;

            session.getAttributes().put("demo.visits", visits);
            return new VisitResponse(nodeId, visits);
        });
    }

    @GetMapping("/me")
    public Mono<UserResponse> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(username -> new UserResponse(nodeId, username));
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/login", "/public/**")
                        .permitAll()
                        .anyExchange().authenticated())
                .formLogin(withDefaults())
                .httpBasic(basic -> basic.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    public record VisitResponse(String node, long visits) { }
    public record UserResponse(String node, String username) { }
}
```

**Vì sao mã trên chứng minh đúng bài học?**

1. `nodeId` cho biết request do process A hay B xử lý, không lưu nodeId trong session.
2. `exchange.getSession()` là API chuẩn WebFlux; nó được Spring Session kết nối tới `ReactiveSessionRepository`/Redis bằng auto-configuration.
3. `session.start()` làm session bắt đầu, `session.getAttributes().put("demo.visits", visits)` tạo thay đổi để lưu. `Long` là kiểu có thể được serializer mặc định xử lý.
4. `VisitResponse` trả JSON có node và số lần truy cập, **không trả session ID, cookie hoặc nội dung SecurityContext**.
5. `/public/touch` không cần login nên dễ thử bằng `curl` và loại bỏ CSRF/form khỏi bài test dữ liệu session.
6. `/me` cần authentication và lấy username từ `ReactiveSecurityContextHolder`, không dùng ThreadLocal Servlet. Nếu session-backed context tồn tại, node B có thể thấy user đăng nhập ở A.
7. `formLogin(withDefaults())` bật trang đăng nhập mặc định `GET /login` và xử lý `POST /login`. Chúng thuộc cùng security chain; CSRF mặc định vẫn được bật.
8. `httpBasic(...disable())` tránh vô tình dùng Basic credentials cho mỗi request, vì điều đó **không chứng minh Redis đã lưu login**.
9. `{noop}learn` chỉ là mật khẩu demo. Production phải dùng BCrypt/Argon2/PBKDF2/scrypt phù hợp, password encoder mạnh và HTTPS.
10. Ứng dụng **không có `@EnableRedisWebSession`**: Boot tự cấu hình Redis-backed WebSession do đã có dependency và kết nối reactive.
11. Hai record response không được lưu trong session. Phần session demo chỉ chứa `Long`; khi form login, Spring Security lưu context dưới attribute của WebSession.

**Lưu ý đồng thời:** Bộ đếm trong session chỉ phục vụ bài test request **tuần tự**. Nếu hai request A/B chạy đồng thời, chúng có thể cùng đọc số cũ rồi cùng ghi số mới, dẫn đến lost update. Spring Session không biến thao tác `getAttribute + 1 + put` thành một lệnh Redis nguyên tử. Với counter nghiệp vụ thật, dùng Redis `INCR` hoặc cơ chế atomic/locking phù hợp, không lấy WebSession làm bộ đếm đồng thời đáng tin.

### 5.4. Khởi chạy Redis cho phòng lab

Ví dụ với Docker đã cài trên máy (chỉ chạy local):

```bash
docker run --name redis-session-lab \
  -p 127.0.0.1:6379:6379 \
  -d redis:7.4-alpine

docker exec redis-session-lab redis-cli PING
```

Phản hồi của lệnh thứ hai:

```text
PONG
```

Nếu Redis đã chạy tại `localhost:6379`, không cần tạo container mới. Nếu đang dùng Windows PowerShell và không thích ký tự tiếp dòng `\` của bash, nhập `docker run ...` trên một dòng. **Không mở port Redis thử nghiệm cho Internet**; môi trường thật phải có network policy, authentication/ACL, TLS và kiểm soát dữ liệu.

### 5.5. Chạy hai process cùng ứng dụng

Mở hai terminal trong thư mục dự án.

Terminal A:

```bash
./gradlew bootRun --args='--server.port=8081 --app.node-id=node-a'
```

Terminal B:

```bash
./gradlew bootRun --args='--server.port=8082 --app.node-id=node-b'
```

Trên Windows dùng `gradlew.bat bootRun --args="--server.port=8081 --app.node-id=node-a"` và câu lệnh tương ứng cho B. Nếu chưa có Gradle Wrapper, dùng `gradle bootRun` với `--args` tương tự và Gradle tương thích Spring Boot 3.3.13.

Hai process sẽ có **cùng cấu hình Redis và namespace**, chỉ khác `server.port` và `app.node-id`. Khi deploy dưới load balancer thật, thay cặp cổng bằng service/pod riêng.

### 5.6. Kiểm tra session data A → B → A bằng curl

Trong terminal mới, dùng **cùng cookie jar** cho cả ba request. Trên Linux/macOS hoặc Windows có bản curl chuẩn:

```bash
curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8081/public/touch

curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8082/public/touch

curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8081/public/touch
```

Trong PowerShell, nên gọi `curl.exe` thay vì alias `curl` của một số phiên bản PowerShell cũ; hoặc nhập mỗi lệnh trên một dòng.

Nếu cookie jar ban đầu chưa có file, `curl` vẫn có thể tạo nó qua tham số `-c`; nếu công cụ báo lỗi không đọc được `-b`, khởi tạo một file trống cục bộ. Sau **ba request tuần tự** thành công, JSON mong đợi có dạng:

```json
{"node":"node-a","visits":1}
{"node":"node-b","visits":2}
{"node":"node-a","visits":3}
```

Đây là **kết quả dự kiến** cho phiên mới chưa có bộ đếm, không phải log đo trực tiếp của máy bạn. Nếu tái sử dụng cookie jar cũ, giá trị bắt đầu có thể lớn hơn 1. Thứ tự trường JSON không bắt buộc cố định; hãy kiểm tra ý nghĩa từng trường.

**Điểm chứng minh:** Một session ID sinh ở A được B nhận và tiếp tục cập nhật. Sticky sessions không cần thiết cho chức năng này. Nếu B tạo `visits=1` thay vì 2, hãy kiểm tra cookie được gửi, hai instance có trỏ cùng Redis/namespace hay không, và thời hạn session.

### 5.7. Kiểm tra Spring Security authentication giữa hai nút

Thử bằng browser, **giữ cùng hostname `localhost`** để cookie có thể được chia sẻ giữa các cổng (cookie HTTP không phân biệt port):

1. Mở `http://localhost:8081/me` khi chưa login. Spring Security redirect tới `/login` của node A.
2. Trên trang form mặc định, nhập **`alice` / `learn`**, để browser tự gửi CSRF token và giữ session cookie.
3. Sau đăng nhập, truy cập lại `http://localhost:8081/me`. JSON dự kiến là `{"node":"node-a","username":"alice"}`.
4. Không xóa cookie, mở `http://localhost:8082/me` trong **cùng browser profile**. JSON dự kiến là `{"node":"node-b","username":"alice"}`.
5. Quay lại A, người dùng vẫn được nhận diện. Khởi động lại A (B vẫn chạy), thử request `/me` ở B để xác minh session không chỉ nằm trong RAM của A.
6. Mở cửa sổ private/incognito hoặc xóa cookie `SESSION` rồi vào B: cần đăng nhập lại vì không có session ID để lookup.

**Bằng chứng tốt nhất** là request `/me` sang B **không cung cấp lại username/password** mà vẫn có principal, đồng thời code chỉ dùng form login, không bật HTTP Basic. Đó là sự kết hợp giữa Spring Security `WebSessionServerSecurityContextRepository` và Spring Session Redis-backed WebSession.

**Chú ý session rotation:** Sau POST login, session ID có thể được đổi để chống session fixation. Khi test thủ công bằng HTTP client, phải giữ **cookie mới từ response login**, không lấy mã `SESSION` trước login rồi cố dùng lại.

## 6. Spring Security và Spring Session: hai tầng phối hợp

Một cách gọi thường gặp là “Spring Session lưu SecurityContext”. Điều này đúng ở mức kết quả nhưng cần hiểu cơ chế:

```text
Spring Security AuthenticationWebFilter
    |
    +-- Authentication success
    +-- WebSessionServerSecurityContextRepository.save(...)
           |
           v
      ServerWebExchange.getSession()
           |
           v
      Spring Session WebSessionManager
           |
           v
      ReactiveSessionRepository<Session>
           |
           v
      ReactiveRedisSessionRepository
           |
           v
          Redis
```

Ở request sau, đường nạp chạy ngược:

```text
Cookie SESSION
    -> WebSessionManager nạp session từ Redis
    -> WebSessionServerSecurityContextRepository.load(...)
    -> ReactorContextWebFilter / ReactiveSecurityContextHolder
    -> AuthorizationWebFilter
    -> Handler được phép
```

Có hai cấu hình có thể gây sai lệch:

**(a) Dùng `NoOpServerSecurityContextRepository` ở chain form login**: Spring Session có thể đang lưu các session attributes bình thường, nhưng SecurityContext không được lưu/khôi phục để dùng request kế tiếp. `/public/touch` A → B thành công còn `/me` B yêu cầu login lại. Vì thế test cả hai chiều, không chỉ kiểm tra bộ đếm.

**(b) Không bật Spring Session Redis-backed WebSession**: SecurityContext vẫn có thể tồn tại trong một `WebSession` do mỗi node quản lý cục bộ; node A hoạt động nhưng node B không khôi phục được. Kiểm tra Spring Boot auto-configuration, beans `WebSessionManager`/`ReactiveSessionRepository` và Redis connectivity.

Nếu dùng `ServerHttpSecurity.securityContextRepository(...)` để tùy biến đường load, cũng cần kiểm tra repository dùng để **save** ở từng authentication filter. Đừng cho rằng mọi filter tự đồng bộ cấu hình save chỉ từ một setter của `ServerHttpSecurity`.

## 7. TTL và vòng đời session trong Redis

Session có các thời điểm quan trọng:

- **creationTime**: session được tạo khi nào.
- **lastAccessedTime**: gần nhất khi nào session hoạt động theo chính sách.
- **maxInactiveInterval**: giới hạn không hoạt động.
- **TTL của Redis keys**: phần hạ tầng để session/metadata hết hạn và được dọn dẹp.

Ví dụ đặt `spring.session.timeout=30m` là chính sách inactivity 30 phút cho demo. Một request dùng session đúng cách có thể cập nhật last-accessed time, làm lần hết hạn dịch chuyển. Dữ liệu session không tồn tại vĩnh viễn; bạn phải kiểm tra token/login mới sau khi nó hết hạn.

**Không mặc định TTL của mọi key Redis luôn bằng chính xác 1.800 giây.** Spring Session có thể dùng thêm key expiration/metadata hoặc khoảng đệm phục vụ sự kiện hết hạn và cleanup. Tùy repository mặc định/indexed và phiên bản, key TTL, sự kiện Redis expired và kết quả `findById` không hoàn toàn là cùng một thứ. Hãy kiểm tra thời hạn theo API Session và behavior request, rồi dùng Redis TTL chỉ như bằng chứng phụ.

Để quan sát metadata trong lab (chỉ với Redis local):

```bash
redis-cli --scan --pattern 'spring:session:webflux-lab:*'
```

Sau khi biết **một key cụ thể** thuộc session demo, có thể dùng `redis-cli TTL "<key>"`. Đừng chạy `KEYS *` hoặc `FLUSHALL` trên Redis dùng chung: có thể gây nghẽn hoặc xóa session của ứng dụng khác. Không dump toàn bộ session attributes ra log, vì chúng có thể chứa thông tin xác thực.

### Khi node restart

Nếu node A chết, session vẫn nằm trong Redis cho đến khi hết hạn hoặc bị xóa. B có thể xử lý request tiếp theo với cookie hợp lệ. **Tuy nhiên Redis là một phụ thuộc sống còn**: nếu Redis mất dữ liệu, bị failover thiếu độ bền hoặc serializer lỗi, việc tiếp tục xác thực có thể thất bại.

### Khi Redis bị mất kết nối

Với Redis-backed session, không thể tự suy ra session đã được xác thực khi lookup thất bại. Spring Security cần **fail closed**: không tiếp tục cho vào endpoint bảo vệ chỉ vì lỗi Redis. Ứng dụng có thể phản hồi 5xx hoặc lỗi được handler cấu hình; cần metric, retry có giới hạn và cảnh báo thay vì chuyển `load` error thành một `SecurityContext` giả hợp lệ.

Redis cần HA/sentinel/cluster phù hợp nhu cầu, nhưng failover cũng có độ trễ và tùy cấu hình replication có thể mất vài write mới nhất. “Có Redis” **không đồng nghĩa** session tuyệt đối không mất trong mọi sự cố.

## 8. Logout và hủy phiên trên toàn bộ cụm

Một yêu cầu logout có thể đến node A, trong khi request kế tiếp tới node B. Để logout có hiệu lực xuyên nút, phải xóa hoặc vô hiệu hóa **trạng thái xác thực được chia sẻ**, không chỉ xóa biến trong RAM.

```text
Browser POST /logout với CSRF hợp lệ
      |
      v
Node A Security LogoutWebFilter
      |
      +-- xóa SecurityContext khỏi repository/session
      +-- tùy cấu hình có thể invalidate toàn bộ WebSession
      |
      v
Spring Session ghi xóa/thay đổi vào Redis
      |
      v
Browser gửi request mới tới Node B
      |
      v
B không còn khôi phục Authentication cũ
      |
      v
Redirect/challenge để đăng nhập lại
```

**Phân biệt hai mục tiêu:**

1. **Đăng xuất người dùng khỏi Spring Security:** loại bỏ SecurityContext đã lưu để các request sau không còn authenticated.
2. **Hủy hẳn WebSession:** xóa cả attribute nghiệp vụ như `demo.visits`, dữ liệu request cache và các thuộc tính khác.

Một logout handler chỉ xóa context **không nhất thiết xóa toàn bộ dữ liệu session**. Nếu yêu cầu nghiệp vụ là xóa sạch session, cấu hình invalidate WebSession qua `WebSessionServerLogoutHandler` hoặc cơ chế phù hợp phiên bản Spring Security, đồng thời kiểm thử request mới sau logout trên node khác.

Trong cấu hình CSRF mặc định, logout làm thay đổi trạng thái phiên nên thường cần **POST + CSRF token**, không biến GET thành thao tác logout chỉ vì dễ đặt một hyperlink.

**Không nhầm logout session với JWT revocation:** Nếu ứng dụng còn cấp Bearer token độc lập, việc xóa WebSession ở Redis không tự vô hiệu hóa mọi token đã phát hành. Cần thiết kế token lifetime/revocation tương ứng.

### Kiểm tra logout đúng cách

- Đăng nhập qua A, gọi `GET /me` ở B và xác nhận username.
- Thực hiện logout qua A bằng form hợp lệ, giữ cookie/session tương ứng.
- Gọi lại `GET /me` ở B: không còn quyền từ lần login trước.
- Nếu đã cấu hình invalidate hoàn toàn, gọi `/public/touch` với session cũ: không được tiếp tục dữ liệu session cũ; có thể xuất hiện phiên mới từ 1.
- Test lại khi một node restart để loại trừ hiện tượng cache cục bộ giữ context cũ.

## 9. Serialization giữa các phiên bản của ứng dụng

Redis lưu **dữ liệu session**, không phải một object Java sống có thể gửi giữa JVM mà không chuyển đổi. Session attributes và SecurityContext phải được **serialize/deserialize** tương thích.

Spring Session Redis mặc định sử dụng **Java serialization** cho các session attributes trong nhiều cấu hình Spring Session 3.x. Đây là một lựa chọn cần cân nhắc khi triển khai rolling update.

### Rủi ro phổ biến

| Tình huống | Hệ quả có thể gặp |
| --- | --- |
| Node A và B chạy hai version không tương thích của class lưu trong session | Deserialization exception ở node B |
| Lưu custom object không hỗ trợ serializer | Ghi session thất bại |
| Thay đổi `serialVersionUID` hoặc cấu trúc class khi rolling deploy | Session cũ khó được đọc |
| Session chứa nhiều dữ liệu/đối tượng lớn | Redis memory, network traffic và GC tăng |
| Cấu hình JSON serializer không hỗ trợ kiểu `SecurityContext`/`Authentication` | Login thành công có thể lỗi khi save/load |
| Cho dữ liệu Redis không tin cậy được deserialization tùy ý | Nguy cơ bảo mật nghiêm trọng |

**Nguyên tắc:** Không lưu entity ORM, request object, token raw hoặc object nghiệp vụ phức tạp vào session nếu có thể chỉ lưu **mã định danh nhỏ, ổn định và dữ liệu cần thiết**. Nếu cần serializer JSON, kiểm tra cách cấu hình bean `springSessionDefaultRedisSerializer` và các module Jackson hỗ trợ Spring Security theo **phiên bản tương ứng**; không chỉ thay thành JSON rồi giả định mọi Authentication class đều đọc được.

Tài liệu Spring Session có hướng dẫn serializer tùy biến và nhấn mạnh việc đăng ký Spring Security Jackson modules khi session có SecurityContext. Khi nâng cấp framework, kiểm thử **phiên cũ trên Redis được node mới đọc lại** trước khi rollout toàn bộ.

### Namespace và migration

Nếu thay `spring.session.redis.namespace`, node mới sẽ không nhìn thấy session thuộc namespace cũ. Với rolling deployment, cần kế hoạch cutover/migration hoặc chấp nhận người dùng phải login lại. Đừng triển khai A với namespace `webflux-lab-v1` và B với `webflux-lab-v2` rồi gọi hiện tượng “mất phiên” là bug của Redis.

## 10. Concurrent updates và consistency

Chia sẻ session không có nghĩa mọi thao tác trên attributes **atomic** khi hai request chạy đồng thời.

Giả sử A và B cùng đọc `visits=10`:

```text
A: load visits=10 ---------> update visits=11 ----> save
B:      load visits=10 ---> update visits=11 ----------> save

Giá trị cuối có thể là 11, không phải 12.
```

Spring Session tối ưu ghi những thuộc tính thay đổi, nhưng bài toán **read-modify-write** giữa process không tự thành một transaction phân tán.

Do đó:

- Dùng WebSession cho **state phiên người dùng**, như một số preference nhỏ, SecurityContext hoặc CSRF/session data phù hợp.
- Với counter, số dư, quota, inventory hoặc idempotency, hãy dùng Redis command atomic (`INCR`/Lua) hoặc storage có transaction/lock riêng.
- Hạn chế việc ghi cùng một attribute trong nhiều request đồng thời; không dựa vào load balancer stickiness như bảo đảm atomicity.
- Khi có nhiều browser tab/request đồng thời, thiết kế cách merge/xử lý xung đột hoặc tránh đưa trạng thái nghiệp vụ quan trọng vào session.

**Flush mode và save mode:** `FlushMode.ON_SAVE` (thay vì ghi tức thì) cùng `SaveMode.ON_SET_ATTRIBUTE` là lựa chọn thường gặp. Chúng có tác động đến thời điểm/khối lượng ghi nhưng **không bảo đảm serializable transaction** cho nhiều request. Cần benchmark và test race khi dùng session với concurrency lớn.

## 11. Kiểm thử tự động và kiểm chứng xuyên nút

### 11.1. Test WebTestClient trên một node

Bài test dưới đây chạy cùng ứng dụng, yêu cầu Redis lab đang hoạt động. Nó xác minh một cookie đã phát hành có thể dùng ở request kế tiếp. Chưa chứng minh hai JVM độc lập cùng đọc Redis: đó là mục đích của bài test A → B qua `curl` hoặc browser.

Tạo `src/test/java/example/ClusterSessionApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ClusterSessionApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void sessionAttributeSurvivesTwoRequests() {
        var first = client.get()
                .uri("/public/touch")
                .exchange()
                .expectStatus().isOk()
                .expectBody(ClusterSessionApplication.VisitResponse.class)
                .returnResult();

        assertNotNull(first.getResponseBody());
        assertEquals(1L, first.getResponseBody().visits());

        ResponseCookie sessionCookie =
                first.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get()
                .uri("/public/touch")
                .cookie("SESSION", sessionCookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody(ClusterSessionApplication.VisitResponse.class)
                .value(body -> assertEquals(2L, body.visits()));
    }

    @Test
    void protectedEndpointRequiresLogin() {
        client.get()
                .uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Chạy khi Redis đang chạy:

```bash
./gradlew test
```

Nếu `@SpringBootTest` không kết nối được Redis, test sẽ thất bại do dependency hạ tầng thực; cần khởi chạy Redis local hoặc dùng Testcontainers/Redis instance chuyên cho CI. **Không** thay bằng mock session nếu mục tiêu test là Redis persistence.

### 11.2. Test tích hợp hai node

Các điểm bắt buộc:

| Bước | Gửi tới | Kỳ vọng |
| --- | --- | --- |
| Request public đầu tiên, giữ cookie | Node A | `visits=1` |
| Request public tiếp theo với cùng cookie | Node B | `visits=2` |
| Request public kế tiếp với cùng cookie | Node A | `visits=3` |
| Form login thành công có CSRF và cookie | Node A | Tạo SecurityContext lưu vào session |
| `GET /me` có cookie sau login | Node B | 200, username `alice` |
| `GET /me` không cookie | Node B | Redirect tới form login |
| Restart node A khi giữ Redis | Node B | Session vẫn tiếp tục theo TTL |
| Logout qua node A, request mới ở node B | Node B | Không còn authentication cũ |
| Đợi hết thời hạn không hoạt động | Node A/B | Session cũ không tiếp tục được xác thực |
| Redis không truy cập được | Node A/B | Không bypass authorization; cảnh báo lỗi |

**Điều không đủ để chứng minh sharing:**

- Chỉ chạy một instance.
- Dùng `mockUser` trong unit test: mock có thể bỏ qua form login và repository.
- Gửi HTTP Basic credentials ở **mọi** request: node B xác thực lại bằng password, không chứng minh nạp session từ Redis.
- Luôn định tuyến tới A bằng sticky sessions.
- Chỉ thấy hai instance đều có kết nối Redis mà không kiểm tra cùng cookie/session.
- Chỉ kiểm tra Redis có key nhưng không kiểm tra `SecurityContext` được node B sử dụng.

### 11.3. Kiểm tra Redis key metadata

```bash
redis-cli --scan --pattern 'spring:session:webflux-lab:*'
```

Nếu có key session, xem TTL theo key cụ thể. Không xuất nội dung attributes/`Authentication` ra log, không commit cookie jar của test vào git, không lưu Redis dump thật trong artifact dùng chung. `SCAN` an toàn hơn `KEYS *` để quan sát trên kho lớn, nhưng vẫn cần giới hạn và kiểm soát môi trường.

## 12. Theo dõi vận hành và hiệu năng

Spring Session Redis giúp bỏ ràng buộc node-local session, nhưng mỗi request cần session có thể tạo lưu lượng Redis. Với nhiều nút, độ trễ Redis, connection pool, serialization và mạng sẽ ảnh hưởng đến login/API.

### 12.1. Chỉ số nên có

| Lớp | Metric và dấu hiệu |
| --- | --- |
| HTTP | Login success/failure, `/me` p50/p95/p99, redirect rate, 401/403/5xx |
| Redis client | Command latency, timeout, connection errors, reconnects, pool saturation |
| Session | Tỉ lệ tạo/nạp/hết hạn, save failures, cache hit, session size, TTL |
| Tài nguyên | Redis memory, evictions, CPU, network bandwidth, replication lag |
| Spring Security | Authentication failure, CSRF failure, authorization deny, logout errors |
| Triển khai | Số node, phiên bản node, namespace/serializer version, session behavior sau rolling deploy |

Không log cookie `SESSION`, raw session ID, mật khẩu, token hay toàn bộ `SecurityContext` trong log. Nếu cần đối chiếu request qua nhiều node, dùng correlation ID độc lập hoặc fingerprint session có kiểm soát, không lộ ID dùng để truy cập phiên.

### 12.2. Các rủi ro khi tải lớn

- **Redis round trip:** login hoặc session-intensive traffic có thể tăng chi phí mạng và latency.
- **Session size:** object lớn tốn serialize/memory, gây GC; giữ session gọn.
- **Nhiều requests cùng session:** có rủi ro ghi chồng; không dùng WebSession làm database phân tán cho nghiệp vụ.
- **Key expiration:** cần timeout hợp lý; keyspace events phục vụ indexed sessions có hạn chế và không thay cơ chế kiểm tra TTL.
- **Capacity:** Redis `maxmemory-policy` có thể evict session key trước timeout; lúc đó browser phải login lại.
- **Availability:** Redis HA và replication bất đồng bộ có thể có một khoảng mất ghi trong failover.
- **Security:** Redis chứa authentication state nhạy cảm; dùng network isolation, ACL, TLS, secret rotation, backup và giám sát truy cập.

Một Redis cluster shared **không thay cho kiểm soát session fixation, CSRF và mật khẩu**. Spring Security vẫn phải quản lý authentication/authorization; Spring Session chỉ thay hạ tầng lưu phiên.

## 13. Lỗi thường gặp và cách sửa

### 13.1. Login A thành công nhưng B vẫn redirect login

Kiểm tra theo thứ tự:

1. Client có gửi **cùng cookie `SESSION`** tới B không? Cookie scope có cùng host/path/domain/secure settings không?
2. A và B có cùng Redis endpoint và `spring.session.redis.namespace` không?
3. Dependency `spring-session-data-redis`, Redis reactive auto-configuration và `WebSessionManager` có thực sự được bật không?
4. Spring Security form login có lưu `SecurityContext` vào WebSession không? Có vô tình dùng `NoOpServerSecurityContextRepository` không?
5. B có đọc được serialized SecurityContext do A lưu không? Có lỗi class/version/serializer không?
6. Session có đã timeout, bị logout, bị xóa hoặc bị Redis evict không?

Nếu `/public/touch` A → B thành công nhưng `/me` không, khả năng lớn là **SecurityContext persistence/authentication filter**, không phải Redis cookie routing. Nếu cả `/public/touch` cũng reset, ưu tiên kiểm tra **session cookie, namespace và WebSessionManager**.

### 13.2. Redis có key nhưng user không authenticated

Session có thể chỉ chứa `demo.visits` hoặc CSRF token mà không có SecurityContext. Có key Redis **không đồng nghĩa** đã đăng nhập. Kiểm tra form POST credentials/CSRF thành công và repository save/load của SecurityContext.

### 13.3. Cấu hình annotation Servlet

`@EnableRedisHttpSession` hoặc `SessionRepositoryFilter` cho `HttpSession` không phù hợp khi ứng dụng dùng Spring WebFlux `WebSession`. Trong Boot WebFlux ví dụ này để auto-config; nếu viết Java config, dùng `@EnableRedisWebSession` và `ReactiveRedisConnectionFactory`.

### 13.4. Hai node dùng khác namespace

Node A lưu `spring:session:app-a:*` còn B tìm `spring:session:app-b:*`. Mỗi node hoạt động cục bộ nhưng không nhận cùng session. Dùng một namespace cho toàn bộ cùng ứng dụng; tách namespace **giữa các ứng dụng khác nhau**.

### 13.5. Dùng cùng Redis nhưng lưu custom object không serialize được

Gặp `SerializationException`, `ClassNotFoundException` hoặc invalid class khi rollout. Giữ attributes nhỏ, tương thích, có kế hoạch serialize JSON với module Security được kiểm chứng hoặc migration session, test hai phiên bản node.

### 13.6. TTL hết hạn bất ngờ

Xem timeout session, last accessed, cookie, Redis eviction và clock/config, không chỉ `TTL` của một key. Khác biệt giữa TTL key và phiên theo API có thể do cơ chế cleanup/expiration tracking.

### 13.7. Logout ở A nhưng B vẫn cho vào

Đảm bảo logout xóa SecurityContext trên repository chia sẻ, và B không giữ một bản cache Authentication vượt quá vòng đời phù hợp. Kiểm thử **request mới** tới B; nếu cần “logout tất cả thiết bị”, cần thêm chính sách tìm/xóa nhiều session hoặc token revocation chuyên biệt.

### 13.8. Redis outage nhưng ứng dụng vẫn cho qua

Không dùng `onErrorResume(...)` để tự dựng user authenticated khi session store lỗi. Đường bảo vệ phải từ chối hoặc trả lỗi hạ tầng có kiểm soát, không bypass authorization.

### 13.9. Tăng concurrency làm bộ đếm sai

Hai request cùng session đọc và tăng giá trị riêng có thể lost update. Redis-backed WebSession không bảo đảm increment atomic. Dùng Redis atomic operation cho counter nghiệp vụ.

### 13.10. Spring Session chạy blocking trên Netty event loop

Sử dụng `ReactiveRedisConnectionFactory`/Lettuce và API `Mono`; không gọi `block()` hay client Redis blocking trong WebFilter/handler. Nếu đã dùng starter data Redis reactive, vẫn cần tránh tự viết code I/O đồng bộ xen giữa luồng WebFlux.

### 13.11. Session cookie không được gửi khi chuyển từ localhost sang 127.0.0.1

Browser cookie theo host/path/domain/scheme policy; `localhost` và `127.0.0.1` khác hostname. Trong demo phải dùng **localhost cho cả A và B**. Cổng khác nhau không tự làm cookie khác hostname. Khi deploy thật cần hostname ổn định dưới reverse proxy và cấu hình forwarded headers/cookie đúng.

### 13.12. Chạy ứng dụng mới làm hỏng session cũ

Rolling deploy có thể phá deserialization nếu class nằm trong SecurityContext thay đổi. Xem trước chiến lược tương thích phiên hoặc chấp nhận cắt session theo policy; không coi Redis là nơi lưu object Java qua mọi bản nâng cấp mà không cần kiểm chứng.

## 14. Câu hỏi tự kiểm tra

**1. Tại sao hai instance cùng dùng Redis lại có thể nhận cùng trạng thái đăng nhập?**  
Vì client gửi cùng session ID; Spring Session Redis-backed WebSessionManager nạp phiên từ Redis, rồi Spring Security nạp SecurityContext đã lưu trong WebSession.

**2. `ReactiveSessionRepository` và `ServerSecurityContextRepository` có phải cùng một interface không?**  
Không. Repository Spring Session lưu/nạp session; repository Spring Security lưu/nạp context bảo mật. Chúng liên hệ thông qua `WebSession`.

**3. Có cần `@EnableRedisHttpSession` trong WebFlux không?**  
Không. Đó là API Servlet. Với Boot WebFlux và dependency phù hợp có thể dùng auto-config; nếu cấu hình thủ công reactive thì dùng `@EnableRedisWebSession`.

**4. Tại sao không đủ để chỉ gửi Basic auth tới cả A và B?**  
Vì mỗi request có thể được xác thực lại từ credentials, không chứng minh session được chia sẻ. Cần test **form login một lần** rồi GET request mới **không gửi lại mật khẩu** ở node khác.

**5. Mã `curl -c/-b` trong ví dụ chứng minh điều gì?**  
Cookie jar giữ `SESSION` giữa ba request tuần tự; bộ đếm tăng 1 → 2 → 3 khi luân chuyển qua hai instance. Điều này kiểm chứng shared WebSession attributes.

**6. Logout có mặc nhiên xóa mọi attributes khỏi Redis không?**  
Không nên giả định. Xóa SecurityContext và invalidate toàn bộ session là hai mục tiêu có thể khác nhau; cần cấu hình và test theo yêu cầu bảo mật.

**7. Spring Session có bảo đảm `visits++` nguyên tử giữa hai node không?**  
Không. Read-modify-write qua WebSession có thể lost update; dùng Redis `INCR` hoặc transaction phù hợp cho counter nghiệp vụ.

**8. Hai node dùng cùng Redis nhưng khác `namespace` có chia sẻ session không?**  
Không. Namespace khác khiến mỗi node nhìn key khác nhau.

**9. Redis mất kết nối thì API bảo vệ có được cho qua vì “không tải được session” không?**  
Không. Lỗi load không phải chứng cứ authentication hợp lệ; phải giữ fail-closed và xử lý lỗi vận hành.

**10. Vì sao serializer quan trọng khi dùng nhiều phiên bản của ứng dụng?**  
Vì node B phải deserialize những attributes mà node A đã serialize; thay đổi class hoặc định dạng có thể làm session không đọc được.

**11. Cookie `SESSION` chứa toàn bộ quyền của user không?**  
Không. Nó chủ yếu mang session ID. SecurityContext/attributes được lưu phía server trong Redis theo cấu hình.

**12. Nếu A bị restart, tại sao B vẫn thấy session?**  
Vì dữ liệu phiên được lưu ngoài RAM của A trong Redis; còn hiệu lực nếu chưa timeout, chưa bị xóa và Redis sẵn sàng.

**Ghi nhớ:** Với Spring Security WebFlux, **Spring Security quản lý ai đã đăng nhập**, còn **Spring Session Redis reactive lưu WebSession để request từ nhiều nút dùng cùng một phiên**. Để chứng minh đúng, hãy thử cùng cookie xuyên A/B, đăng nhập form trên A rồi kiểm tra principal ở B, logout rồi kiểm tra B không còn authenticated, và quan sát Redis/session expiration. Chia sẻ phiên không giải quyết tự động concurrency, serialization, Redis HA hoặc security policy.

## Tài liệu tham khảo

- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): thay `WebSessionManager` và tích hợp `ReactiveSessionRepository` vào WebFlux.
- [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html): auto-configuration Spring Session reactive, Redis và properties timeout.
- [Spring Session — API Documentation](https://docs.spring.io/spring-session/reference/api.html): `ReactiveSessionRepository`, `ReactiveRedisSessionRepository`, expiration và session storage.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespace, serializer, indexed repository và session cleanup.
- [Spring Session — Reactive Redis Indexed Configuration](https://docs.spring.io/spring-session/reference/configuration/reactive-redis-indexed.html): indexed sessions và hạn chế Redis keyspace event, dùng khi thực sự cần indexing.
- [Spring Session — EnableRedisWebSession API](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/data/redis/config/annotation/web/server/EnableRedisWebSession.html): cấu hình Java thủ công cho WebFlux.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): form login, `SecurityWebFilterChain` và authorization.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): contract load/save context theo exchange.
