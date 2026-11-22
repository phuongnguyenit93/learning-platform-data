# Kho phiên, kho token dùng một lần và điều kiện nhất quán khi chạy nhiều nút

## 1. Vì sao một ứng dụng đăng nhập chạy tốt trên một máy có thể lỗi trên hai máy?

Một website Spring Security với `formLogin()` có thể hoạt động hoàn hảo khi chỉ có một instance: người dùng gửi mật khẩu, server tạo `HttpSession`, lưu `SecurityContext`, browser nhận session cookie rồi truy cập trang bảo vệ. Nhưng khi triển khai **nhiều nút** phía sau load balancer, request kế tiếp có thể đến **nút khác**. Nếu hai nút chỉ giữ phiên trong bộ nhớ riêng, nút thứ hai không biết người dùng đã đăng nhập.

Tương tự, khi hệ thống sử dụng **one-time token (OTT)** để gửi magic link qua email hoặc token một lần cho xác thực lại, node A có thể phát token và lưu vào `ConcurrentHashMap` nội bộ; user nhấp link tới node B thì B không tìm thấy token. Nguy hiểm hơn, nếu dữ liệu token được nhân bản nhưng không có phép **consume nguyên tử**, hai request đồng thời ở hai node có thể cùng nghĩ token chưa được dùng, dẫn tới **replay**.

Bài thuộc nhóm **Vận hành** của module **Spring Security - authentication**, tập trung vào cách lựa chọn và vận hành **kho session**, **kho token dùng một lần** và **điều kiện nhất quán** khi có nhiều node/pod, failover, autoscaling, Redis/database và gateway. Nội dung dùng Java 17+, Spring Boot 3.x/Spring Security 6.x ở những ví dụ tích hợp; chi tiết OTT dùng Spring Security **6.4+**, vì các bản 6.x trước đó chưa có `oneTimeTokenLogin()`.

Sau bài, bạn cần có khả năng:

1. Phân biệt cookie/session ID, `SecurityContext` và nơi lưu state.
2. Giải thích vì sao sticky session không tự giải quyết restart, failover hoặc token replay.
3. Cấu hình Spring Session Redis để hai instance cùng nhìn thấy login session.
4. Sử dụng kho chung cho OTT; hiểu `generate(...)` và `consume(...)` phải phối hợp với TTL, uniqueness và tính nguyên tử.
5. Thiết kế điều kiện nhất quán cho login, logout, đổi session ID, MFA step-up, token consume và revoke.
6. Kiểm thử hai nút, cạnh tranh đồng thời, hết hạn, mất kết nối store, restart, rollback và triển khai rolling update.

**Hai quy tắc đầu tiên:** session phải được **đọc/ghi bằng kho chia sẻ nếu muốn tồn tại qua node**, còn token “dùng một lần” phải có **một điểm quyết định tiêu thụ duy nhất**; chỉ lưu cùng chỗ nhưng không có atomicity vẫn chưa đủ.

## 2. Session không giống cookie; OTT không giống access token

| Đối tượng | Vai trò | Trạng thái ở đâu? | Điều kiện quan trọng |
| --- | --- | --- | --- |
| Session cookie (thường `SESSION` với Spring Session) | Mang ID phiên để server tra cứu | Browser giữ ID, không phải toàn `Authentication` | HTTPS, Secure/HttpOnly/SameSite, scope cookie, rotation |
| `HttpSession` | Phiên server có attributes | Local servlet container hoặc shared session store | Load/save được từ node bất kỳ; TTL, invalidation |
| `SecurityContext` | Chứa `Authentication` đã xác thực | Trong HttpSession/repository hoặc request theo cấu hình | Đúng principal/authorities; save và restore |
| OTT / magic-link token | Chứng cứ có thể đổi thành authentication **một lần** | Phải có store dùng chung với policy consume/expiry | Dùng một lần, ngắn hạn, đủ entropy, chống replay |
| TOTP/HOTP code | Mã tính từ authenticator secret/counter | Secret/counter hoặc replay state có chính sách riêng | Hạn chế thử, kiểm lệch giờ, chống replay |
| OAuth2 access JWT | Bằng chứng bearer do AS phát | Thường client giữ token; RS stateless xác minh từng request | Chữ ký, issuer, audience, exp, scope, revocation model |
| Opaque access/refresh token | Giá trị tham chiếu hoặc refresh credential | AS hoặc token store | Introspection/rotation/revocation, bảo vệ replay |
| CSRF token | Bảo vệ browser state-changing request | Session/cookie/repository tùy thiết kế | Phù hợp phiên, thay đổi theo lifecycle, không là authentication |

**Không gom tất cả các đối tượng vào một Redis key hoặc một TTL.** Phiên có thể tồn tại 30 phút không hoạt động; magic-link OTT có thể chỉ tồn tại 5 phút; refresh token cần vòng đời và atomic rotation khác; JWT stateless không mặc nhiên cần ghi HttpSession.

## 3. Điều gì xảy ra với session khi load balancer phân phối hai node?

Kiến trúc chưa có shared session:

```text
                       Load Balancer
                     /               \
                Node A              Node B
             HttpSession A       HttpSession B
               [Alice]              [trống]
                  │                    │
POST /login ──────┘                    │
GET /account ─────────────────────────┘ → anonymous / 302 login
```

Hai JVM riêng không chia sẻ object heap. `JSESSIONID` hoặc `SESSION` chỉ là **khóa** để tìm session, không tự biến một object trong RAM của node A thành dữ liệu trên node B.

Kiến trúc có shared session:

```text
                    Load Balancer
                      /       \
                  Node A      Node B
                      \       /
                  Spring Session
                        |
                 Redis / DB cluster
                        |
              session-id → attributes
                        |
                 SecurityContext Alice
```

Request đăng nhập tại A tạo/ghi session vào backend. Request kế tiếp qua B đọc cùng session ID và khôi phục Authentication. **Cần kiểm thật sau commit/save**; shared store không cứu được custom login code quên `SecurityContextRepository.saveContext(...)`.

### 3.1. Sticky session là gì và giới hạn ra sao?

Session affinity (sticky session) cố gắng định tuyến cùng browser về một node. Nó giảm nhu cầu đọc store chia sẻ ở một số kiến trúc nhưng **không phải bảo đảm nhất quán**:

- Node được “dính” vào có thể chết, drain hoặc scale-down.
- Browser đổi mạng, proxy hoặc load balancer đổi cấu hình.
- Rolling deployment có thể chuyển request sang node có phiên khác.
- Một token dùng một lần có thể được phát trên node A và redeem trên node B qua các client/requests khác nhau; stickiness không phải mutex.
- Quản trị viên đăng xuất session từ một node không tự xóa session trên các nút khác nếu mỗi node giữ bản riêng.

Có thể sử dụng stickiness để tối ưu topology khi có chiến lược phục hồi, nhưng **không dùng nó thay** shared session khi yêu cầu đăng nhập còn hiệu lực qua failover.

## 4. Tính nhất quán phải được đặt theo từng nghiệp vụ

“Nhất quán” không có một nghĩa duy nhất cho mọi dữ liệu. Hãy xác định **bất biến an toàn** (security invariants):

| Thao tác | Bất biến cần bảo đảm |
| --- | --- |
| Login thành công | Sau khi client nhận phiên hợp lệ, request kế tiếp đọc được đúng authenticated principal/authorities theo contract |
| Login thất bại | Không có session được lưu với Authentication đã xác thực do request thất bại |
| Session fixation protection | ID phiên trước login không trở thành đường vào tài khoản mới |
| Logout/invalidate | Session bị hủy không được tiếp tục trao quyền chỉ vì node khác vẫn có bản cache cũ |
| Session idle timeout | Khi hết hạn, không cấp quyền; không dùng thời điểm dọn rác vật lý thay thời điểm hết hiệu lực |
| OTT consume | **Tối đa một** request giành được quyền sử dụng một token hợp lệ |
| OTT expiration | Token quá hạn không được dùng dù bản ghi chưa được cleanup |
| OTT principal binding | Token được phát cho subject/account nào thì chỉ tạo login/step-up cho subject đó |
| OTP/MFA step-up | Evidence phải gắn đúng principal, phiên/giao dịch và thời gian; không nâng nhầm user khác |
| Refresh-token rotation | Chỉ một kết quả hợp lệ cho một refresh token cũ theo chính sách, replay được phát hiện |
| Password/account revoked | Session/token cũ được xử lý theo chính sách thu hồi và cửa sổ rủi ro xác định |

Điểm quyết định:

- **Availability:** hệ thống còn phục vụ được request khi store lỗi hay không?
- **Safety:** có bao giờ chấp nhận token đã dùng, session đã bị vô hiệu hóa hoặc user chưa được xác thực không?
- **Latency:** bao nhiêu round trips và p99 của store nằm trên authentication path?
- **Durability:** khi Redis/DB mất điện hoặc failover, dữ liệu đã trả “thành công” có còn không?
- **Ordering/linearizability:** nếu hai request đồng thời tới hai node, có một thứ tự commit rõ để chỉ một token được consume không?

Trong bảo mật, **đừng đổi safety lấy availability bằng cách “cứ cho qua nếu Redis không phản hồi”**. Với session/tokens không xác minh được, thường cần fail closed; các quyết định degraded mode phải được phân tích rủi ro, có giới hạn và giám sát.

## 5. Spring Security lưu và khôi phục Authentication bằng cách nào?

Luồng Servlet điển hình:

```text
POST /login
  UsernamePasswordAuthenticationFilter
    └─ AuthenticationManager / Provider kiểm credentials
    └─ session fixation strategy
    └─ SecurityContext chứa Authentication đã xác thực
    └─ SecurityContextRepository.saveContext(...)

GET /profile + session cookie
  Spring Session filter thay HttpSession bằng implementation dùng Redis
    └─ SecurityContextHolderFilter
       └─ SecurityContextRepository đọc SecurityContext
    └─ AuthorizationFilter kiểm authenticated + authorities
    └─ Controller / service
```

Spring Security 6 dùng cơ chế **explicit save** trong những flow custom: `SecurityContextHolder.setContext(...)` trên một thread **không đủ** để request kế tiếp nhìn thấy login. Các filter đăng nhập chuẩn thường lưu context đúng cho bạn; custom login handler phải phối hợp cùng repository và session strategy.

### 5.1. Hai tầng khác nhau

- `SecurityContextRepository` biết cách load/save `SecurityContext` vào `HttpSession` hoặc nguồn khác.
- **Spring Session** thay thế `HttpSession` của servlet container bằng object được lưu vào Redis/DB thông qua `springSessionRepositoryFilter`.

Bạn có thể có Spring Session Redis nhưng vẫn mất login nếu handler không save context. Hoặc bạn có thể save SecurityContext đúng nhưng chỉ dùng local session, khiến node B không đọc được. **Phải đúng cả hai tầng.**

### 5.2. Không mở session cho API thuần Bearer để “sửa” vấn đề

Một chain `oauth2ResourceServer().jwt()` dùng `SessionCreationPolicy.STATELESS` thường tạo `JwtAuthenticationToken` từ token trong **mỗi request**, không cần đồng bộ server session. Đừng vô tình chuyển API stateless thành stateful chỉ vì có Redis cluster. Khi cần revoke JWT ngay lập tức hoặc step-up xuyên phiên, đó là bài toán token/revocation riêng với chi phí lookup tương ứng.

## 6. Cấu hình Spring Session Redis trên Spring Boot 3.x

Ví dụ sau nhắm tới **Java 17 + Spring Boot 3.5.x + Spring Security 6.5.x** (phối hợp với Spring Session phiên bản do Spring Boot BOM quản lý). Nếu ứng dụng đang dùng Boot 3.0–3.3, kiểm ma trận phiên bản và khả năng `oneTimeTokenLogin()` trước khi sao chép phần OTT; OTT framework có từ Spring Security **6.4**.

### 6.1. Dependencies Gradle

Trong `build.gradle` của một Spring Boot 3.x project đã cấu hình plugin Spring Boot và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'

    // Kho dùng chung cho OneTimeTokenService qua JDBC.
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dùng phiên bản tương thích trong BOM, **không** tùy ý pin `spring-session-data-redis` lệch với Boot/Security. Với web MVC/Servlet, Spring Session Redis tự cấu hình filter/session repository trong trường hợp Boot nhận diện dependency và Redis connection. Không cần thêm `@EnableRedisHttpSession` bừa bãi lên nhiều class khi Boot đã auto-configure.

Đối với production, cấu hình Redis AUTH/TLS, network ACL, connection pool/timeouts, Sentinel/Cluster theo topology, quyền DB và observability. Các dependencies không tự triển khai được Redis/PostgreSQL server.

### 6.2. application.yml

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      # Password, TLS, sentinel/cluster thiết lập qua secret/config môi trường.

  session:
    store-type: redis
    redis:
      namespace: "training:auth-session:v1"
      repository-type: default
      flush-mode: on_save

  datasource:
    url: ${JDBC_URL}
    username: ${JDBC_USER}
    password: ${JDBC_PASSWORD}

  jdbc:
    template:
      query-timeout: 3s
```

**Lưu ý cấu hình:** `server.servlet.session.timeout=30m` là **idle timeout của session**, không phải thời gian sống magic-link token. `spring.session.redis.namespace` tách key giữa các ứng dụng/môi trường, tránh vô tình chia sẻ session với app khác. `repository-type: default` dùng `RedisSessionRepository`; `indexed` có chức năng tìm session theo user/events và chi phí index/cleanup riêng. `flush-mode: on_save` ghi khi repository save; `immediate` giảm trì hoãn một số thay đổi nhưng tăng số lần ghi và không giải quyết mọi tranh chấp cập nhật.

Trên HTTPS production, cần đặt cookie `Secure=true` và chính sách `SameSite`/domain/path phù hợp kiến trúc. Với lab HTTP trên localhost, bật `Secure` có thể làm browser không gửi cookie như dự kiến; tách cấu hình dev và prod rõ ràng, không tắt Secure trong production.

**Cảnh báo:** không commit `JDBC_PASSWORD`, Redis password, session ID hoặc OTT raw token vào repo/log. Credential của các kho hạ tầng phải được lấy từ secret manager và luân phiên quản lý.

### 6.3. RedisSessionRepository hay RedisIndexedSessionRepository?

| Lựa chọn | Hữu ích khi | Giới hạn/cảnh báo |
| --- | --- | --- |
| `RedisSessionRepository` (mặc định của Boot trong cấu hình Redis thường gặp) | Cần tra session theo ID và chia sẻ giữa nodes | Không có các index/event capability như indexed implementation |
| `RedisIndexedSessionRepository` | Cần tìm toàn bộ sessions của principal, kiểm concurrent sessions, xử lý session created/deleted/expired events | Thêm cấu trúc index, cleanup và yêu cầu keyspace-event handling; Redis Cluster có caveat |
| Spring Session JDBC | Hạ tầng đã có RDBMS bền, cần dùng chung session qua DB | Latency/throughput/locking và schema khác Redis |
| Local servlet session | Một node, lab hoặc hệ thống có thiết kế state local rõ | Không đảm bảo failover/cross-node access |

Spring Session documentation lưu ý `RedisIndexedSessionRepository` với Redis Cluster có thể chỉ subscribe events từ một node ngẫu nhiên, làm index không được cleanup ở một số tình huống. **Không xem chỉ số “đã có index” là bằng chứng mọi logout/revocation luôn cập nhật tức thì trong mọi topology.** Nếu nghiệp vụ cần xóa toàn bộ phiên chủ động, kiểm cụ thể cơ chế, cluster setup, propagation và tests.

### 6.4. Mã minh họa form login + endpoint /me

**`SessionDemoApplication.java`** (package `com.example.multinode`):

```java
package com.example.multinode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

**`WebSecurityConfig.java`**:

```java
package com.example.multinode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("lab-user")
                        .password(encoder.encode("LAB-only-change-me"))
                        .roles("READER")
                        .build());
    }
}
```

**`SessionIdentityController.java`**:

```java
package com.example.multinode;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionIdentityController {

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication auth) {
        return Map.of(
                "username", auth.getName(),
                "authenticated", auth.isAuthenticated());
    }
}
```

Các file tạo một web app demo sau khi có Redis và cấu hình datasource phù hợp (DB phần OTT bên dưới có thể là cấu hình riêng nếu muốn chạy chỉ session). Mật khẩu tĩnh là **đồ dùng lab**, không được dùng trong production hoặc public deployment. `/me` chỉ trả tên và trạng thái thay vì dump SecurityContext hoặc session ID.

Nếu dùng Spring Session Redis đúng, chạy cùng ứng dụng trên **hai port/instances** với chung `spring.session.redis.namespace` và backend Redis, session phát ở node A phải được load ở node B. Đây là **kết quả cần kiểm bằng integration test**, không tự động suy ra chỉ từ việc app startup thành công.

## 7. Test hai nút: phải có request sau đăng nhập qua node khác

Một test một JVM bằng `MockMvc` giúp xác nhận form login và `SecurityContextRepository`, nhưng **không chứng minh shared store chạy đúng**. Bài toán multi-node đòi:

1. Node A và B cùng version hoặc version tương thích, cùng Redis namespace/credentials, cookie contract và user store.
2. Browser/client gửi form login tới **A**; lưu cookie session sau login.
3. Không gửi lại password, đưa request `GET /me` tới **B** với chính session cookie.
4. Xác nhận B trả **đúng principal**, không redirect login và không nhìn thấy user lạ.
5. Gửi GET tương tự tới A/B xen kẽ và so authorities/subject.
6. Kill A hoặc drain A; B vẫn phải đọc được session nếu backend còn và session chưa expired.
7. Logout qua B rồi yêu cầu đến A với **cookie cũ**: phải không còn authenticated.
8. Kiểm đúng khi session đã hết idle timeout, khi Redis restart/failover, khi key bị evict và khi rolling deploy class phiên thay đổi.

**Không hardcode cookie name.** Spring Session thường dùng cookie `SESSION`; Servlet session mặc định phổ biến là `JSESSIONID`. Kiểm response thực tế vì cookie serializer/custom config có thể đổi tên.

### 7.1. Kịch bản curl ở mức ý tưởng

Với GET login page tạo CSRF token và session cookie qua port node A:

```text
A: GET /login
   → lấy CSRF token và cookie
A: POST /login (username, password, CSRF, cookie)
   → lưu lại cookie sau session fixation protection
B: GET /me (chỉ cookie, không gửi password)
   → 200, đúng principal "lab-user"
A: GET /me (chỉ cookie)
   → 200, đúng principal "lab-user"
B: POST /logout (CSRF + cookie)
   → logout
A: GET /me (cookie cũ)
   → anonymous, không còn thông tin user
```

Đây là **kịch bản cần tự động hóa**, không phải các lệnh curl đã thực thi. Vì browser form login bật CSRF, không chỉ gửi POST username/password rồi tắt CSRF khi bị 403. Nếu có session ID rotation khi login, dùng cookie mới nhất.

Với HTTP thực, có thể dùng `curl -c cookies.txt -b cookies.txt` cho cookie jar và lấy token CSRF từ trang `GET /login`; kịch bản hoàn chỉnh tùy login template/CSRF repository của hệ thống.

### 7.2. Kiểm tra hai session khác user

Đăng nhập Alice trên A và Bob trên B trong **hai cookie jars khác nhau**. Sau đó gửi từng jar tới cả A/B. Cả bốn kết quả phải giữ đúng danh tính. Một controller giữ principal trong field singleton hoặc một cache key chỉ dùng `"currentUser"` có thể gây cross-user leak mà test một account không phát hiện.

## 8. Serialization, versioning và rolling deployment

Với Spring Session, `HttpSession` lưu được attributes từ ứng dụng, bao gồm object gắn với Spring Security. Khi ghi Redis, có các quyết định:

- **JDK serialization** là lựa chọn mặc định trong nhiều cấu hình Spring Session Redis; yêu cầu các class phù hợp serialization và có rủi ro bảo mật khi tin untrusted data.
- **JSON serialization** có thể giúp portability/debugging nhưng phải dùng serializer và Jackson mixins/module tương thích với Spring Security. Không bật default typing thiếu kiểm soát cho dữ liệu không tin cậy.
- Object trong `SecurityContext` có thể gồm custom principal, user details, granted authorities, session data. Khi triển khai version mới, đổi package/class/serialVersionUID hoặc cấu trúc object có thể khiến node B không deserialize được session do A tạo.
- Trong rolling deploy, hai phiên bản code có thể cùng đọc/ghi namespace; cần compatibility test, schema migration hoặc tách namespace/đóng phiên theo kế hoạch có truyền thông.
- Khi Redis mất/không deserialize được session, **không tạo authenticated principal giả** và không fallback sang user last-seen lưu trong static field.

**Khuyến nghị:** lưu tối thiểu các thuộc tính cần thiết; tránh nhét entity JPA/proxy lớn hoặc access/refresh token raw vào session. Chọn định dạng với danh sách type cho phép, có tests thực qua cả phiên bản cũ/mới. Nếu phải force logout khi rollout không tương thích, đó là quyết định UX/bảo mật cần thông báo chứ không nên âm thầm làm hệ thống trả nhầm identity.

## 9. Session TTL, sliding expiration và thứ tự cập nhật

Session idle timeout là khoảng **không hoạt động**, khác absolute maximum lifetime. Trong Spring Session, expiration thường dựa vào `lastAccessedTime + maxInactiveInterval`, nhưng các lần truy cập gần nhau ở A/B, Redis writes và event cleanup có thể xảy ra không đồng thời.

Ví dụ:

```text
Session idle timeout = 30 phút
09:00 Login A, lastAccessedTime=09:00
09:20 GET /me B, ghi lastAccessedTime mới
09:40 GET /me A, nếu dữ liệu được cập nhật đúng thì vẫn hợp lệ
10:11 Không hoạt động thêm 31 phút → phải bị coi là hết hạn
```

**Không cho phép session đã hết hạn chỉ vì key vật lý chưa được dọn.** Repository phải kiểm expiration theo contract; cleanup Redis có thể chạy muộn nhưng quyền truy cập không được dựa vào việc “chưa xóa key thì vẫn hợp lệ”.

### 9.1. Tranh chấp cập nhật

Nếu hai request cùng session chạy song song:

- A đọc `SecurityContext`/attributes trước logout.
- B thực hiện logout/invalidate hoặc thay đổi factor/role.
- A kết thúc muộn và save snapshot cũ.

Tùy repository/flush mode/attribute update, **stale write** có thể ghi đè hoặc khôi phục state đã bị thay đổi. Không giả định Redis Hash/session save mặc định có transaction version/CAS bảo vệ mọi trường hợp concurrency.

Những state cực kỳ nhạy cảm (MFA assurance, admin elevation, forced logout, session version) nên có **nguồn sự thật/version ở server**: ví dụ `userAuthVersion`/`sessionEpoch` hoặc revocation index được kiểm ở request quan trọng, cùng CAS/transaction khi update. Không đủ chỉ thay value trong một object session nếu các request khác có thể commit sau.

### 9.2. Invalidation và concurrent sessions

- Logout thực hiện invalidate/delete session theo cấu hình, nhưng request đang chạy có thể đã được authorize trước khi logout xảy ra. Phải xác định window chấp nhận được và xử lý nghiệp vụ nhạy cảm tại thời điểm commit.
- Force logout từ node khác cần xóa phiên trong shared repository hoặc đánh dấu revocation mà tất cả node kiểm.
- Quản lý số session/user đòi index/query phù hợp; `RedisIndexedSessionRepository` hỗ trợ `findByPrincipalName(...)` nhưng cần kiểm cleanup indexes và Redis topology.
- Session fixation protection thường đổi session ID khi login; cookie trước login không được giữ quyền của session đã nâng cấp.
- Password reset hoặc disable account có thể cần tăng `authVersion` và khiến phiên cũ không còn hợp lệ theo policy, chứ không chỉ thay password hash ở DB.

## 10. OTT: phát ở node A, xác thực ở node B

Spring Security **6.4+** hỗ trợ `oneTimeTokenLogin()` trên Servlet. Flow:

```text
POST /ott/generate ở Node A
  └─ OneTimeTokenService.generate(request)
     └─ tạo token có entropy cao, username và expiresAt
        └─ lưu vào KHO CHUNG (JDBC/Redis/...)
           └─ OneTimeTokenGenerationSuccessHandler gửi token qua kênh tin cậy

Người dùng mở magic link → Node B
  └─ submit token (mặc định POST /login/ott)
     └─ OneTimeTokenService.consume(authenticationToken)
        ├─ invalid, expired, used → null → không login
        └─ hợp lệ → trả OneTimeToken và đánh dấu đã dùng NGUYÊN TỬ
             └─ authentication flow tạo phiên web nếu cấu hình stateful
```

Spring Security có `OneTimeTokenService` với:

```java
// GIAO DIỆN API CẦN HIỂU (6.4+), minh họa chữ ký:
OneTimeToken generate(GenerateOneTimeTokenRequest request);

@Nullable
OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
```

Đây là chữ ký mang tính giải thích, **không phải file Java để biên dịch độc lập**. Interface thật nằm trong package `org.springframework.security.authentication.ott`. `consume` trả `null` khi token không hợp lệ. Không nhầm token này với TOTP/HOTP: OTT là token một lần thường gửi qua email/magic link, không cần shared authenticator secret ở phía client.

### 10.1. Vì sao InMemoryOneTimeTokenService không phù hợp multi-node?

Spring Security dùng `InMemoryOneTimeTokenService` làm default khi không có bean/service riêng. Nếu A và B là hai JVM, mỗi node có map riêng; token phát ở A có thể không được B nhận diện. Token có thể mất khi restart A.

Với production, framework tài liệu đề xuất `JdbcOneTimeTokenService` hoặc một implementation shared khác. Không đơn giản “đồng bộ maps mỗi vài giây”: replicate async có thể làm **hai node đều consume cùng token** trước khi nhận trạng thái đã dùng. Dùng shared store **và** thao tác consume có ngữ nghĩa nguyên tử.

### 10.2. Những bất biến của một token một lần

Một OTT hợp lệ cần:

1. CSPRNG, entropy đủ cao; không dùng username, timestamp hoặc ID tuần tự làm secret.
2. Bản ghi trong store gắn token với **đúng account/tenant/flow/purpose**.
3. Thời gian hết hạn được kiểm trong chính thao tác consume (TTL/database time), không chỉ dọn rác định kỳ.
4. Tối đa một consume thành công khi có concurrency.
5. Không cho token của password reset đổi thành token login hoặc ngược lại.
6. Không tin thông tin account/email đến từ client tại thời điểm redeem: subject phải lấy từ record đã được issuer/server tạo và validate.
7. Rate limit việc phát và thử token, chống enumeration, replay và mail bombing.
8. Khi consume thành công, không được dùng token lại dù HTTP response/login session save thất bại; phải có chính sách recovery/idempotency riêng.
9. Không ghi raw token vào URL logs, tracing, analytics, referrer, ticket; áp HTTPS, `Referrer-Policy`, tránh tải third-party content trước khi hoàn tất token exchange.

## 11. Tích hợp JdbcOneTimeTokenService với Spring Security 6.5

Trong một project **Spring Security 6.5** có Spring JDBC và datasource dùng chung giữa nodes, `JdbcOneTimeTokenService` nhận `JdbcOperations` (ví dụ `JdbcTemplate`) và implement `OneTimeTokenService`.

**`OneTimeTokenStoreConfig.java`**:

```java
package com.example.multinode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

@Configuration
public class OneTimeTokenStoreConfig {

    @Bean
    OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
        return new JdbcOneTimeTokenService(jdbc);
    }
}
```

Framework sẽ có thể nhận bean này cho DSL `oneTimeTokenLogin()` nếu được bật. Hoặc chỉ định trực tiếp service trong cấu hình nhiều `SecurityFilterChain`:

```java
// Snippet trong một HttpSecurity config (Security 6.5).
.oneTimeTokenLogin(ott -> ott
        .tokenService(oneTimeTokenService)
        .tokenGenerationSuccessHandler(safeTokenDeliveryHandler))
```

**Các điều kiện bắt buộc để chạy thật:**

- Cần **migration schema chính xác của phiên bản thư viện**; `JdbcOneTimeTokenService` yêu cầu bảng định nghĩa bởi resource: `classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql`. Copy/adapt migration theo PostgreSQL đang dùng và áp dụng trước khi bật feature. Không tự chế bảng với tên cột đoán mò rồi mong service dùng được.
- Mọi node dùng **cùng datasource/schema**, pool/timeouts và transaction semantics tương thích.
- Cần một implementation `OneTimeTokenGenerationSuccessHandler` gửi token qua email/SMS được bảo vệ. Spring Security **không tự biết địa chỉ nhận hoặc kênh gửi token an toàn**.
- Chức năng OTT phải sử dụng đúng `oneTimeTokenLogin()` trên chain mà các URL generate/submit thuộc phạm vi. Mặc định generate là `POST /ott/generate`, trang submit là `GET /login/ott` và xử lý đăng nhập là `POST /login/ott`; giữ CSRF khi dùng web session.
- **Kiểm chứng concurrency của chính JDBC implementation/version và database isolation** dưới tải. Không tuyên bố “có JDBC nghĩa là luôn exactly once” nếu chưa test. Khi tự viết service, cần conditional update/delete trong transaction hoặc ràng buộc tương đương.

### 11.1. Phân tách session Redis và OTT JDBC có được không?

**Có.** Session dùng Redis còn token dùng một lần dùng PostgreSQL là thiết kế hợp lệ:

| State | Store | Lý do |
| --- | --- | --- |
| HTTP session | Redis qua Spring Session | Lookup theo session ID nhanh, TTL, chia sẻ qua pods |
| OTT | PostgreSQL qua JdbcOneTimeTokenService | DB chung, có schema, transaction/constraints |
| Identity/password/account state | User DB hoặc IdP | Nguồn sự thật danh tính riêng |
| JWT verification keys | JWKS cache có kiểm soát | Resource Server xác minh token, không lẫn phiên |
| Audit events | Outbox/audit sink | Quy định độ bền riêng |

Không yêu cầu tất cả dữ liệu “auth” ở cùng một store; quan trọng là những bước liên quan có thể có **ranh giới transaction riêng** và cần thiết kế điều kiện nhất quán khi chuyển từ OTT đã consume sang session đã login.

## 12. Atomic consume: bài toán chính của token một lần

Anti-pattern điển hình:

```java
// PHẢN VÍ DỤ, không dùng trong multi-node:
Token token = repository.find(tokenValue);
if (token != null && !token.isExpired()) {
    repository.delete(tokenValue);
    return login(token.username());
}
```

Hai request trên A/B có thể cùng đọc trước khi một node xóa. Thứ tự race:

```text
A: SELECT token → found
B: SELECT token → found
A: DELETE token
B: DELETE token (0 rows hoặc vẫn không kiểm affectedRows)
A: login success
B: login success     ← VI PHẠM single-use
```

Một phép xóa đơn lẻ **có thể nguyên tử**, nhưng đoạn `read → check → delete → grant` chưa nguyên tử. Cần một thao tác mà **chỉ một caller** giành được token và trả về dữ liệu chủ thể hợp lệ; caller còn lại phải nhận invalid/used.

Với database có thể thiết kế conditional atomic delete/returning hoặc transaction kèm row lock và check affected rows (phụ thuộc engine). Với Redis có thể dùng Lua script atomic hoặc Redis command phù hợp. **Không khóa bằng synchronized trong JVM** để giải quyết cross-node: mỗi JVM có một lock khác nhau.

### 12.1. SQL PostgreSQL minh họa cho service TỰ VIẾT

Nếu ứng dụng tự thiết kế OTT store, một bảng tối giản có thể là:

```sql
CREATE TABLE single_use_login_token (
    token_digest BYTEA PRIMARY KEY,
    subject_id VARCHAR(150) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX single_use_login_token_expiry
    ON single_use_login_token (expires_at);
```

Phát sinh raw token bằng CSPRNG, chỉ lưu digest/HMAC; lưu `subject_id` nội bộ đã xác định từ account directory, `purpose` là enum whitelist. PostgreSQL cho phép xóa có điều kiện và trả metadata trong cùng một statement:

```sql
DELETE FROM single_use_login_token
WHERE token_digest = :digest
  AND purpose = 'LOGIN'
  AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_id;
```

Với unique primary key và PostgreSQL row-level locking, hai transactions cạnh tranh xóa cùng row không thể cùng nhận **một row đã xóa**. Một statement trả subject cho request thắng; request còn lại nhận **0 rows** và phải từ chối. Lưu ý chuẩn bị dữ liệu, isolation và việc client retry khi DB timeout vẫn cần xử lý.

Đây là **mô hình custom store**, không phải SQL schema hoặc câu query nội bộ của `JdbcOneTimeTokenService`. Không thay schema framework bằng bảng minh họa này rồi expect ORM/JDBC service tự nhận diện.

### 12.2. Redis Lua: lấy subject và xóa chỉ trong một thao tác

Khi token có entropy cao, server có thể lưu token **digest/HMAC** làm thành phần key, không dùng raw token làm key. Phát hành bằng `SET key subject NX PX ttlMillis` (sau khi validate subject/purpose/tenant và giới hạn request). Dùng Redis TTL để token hết hạn.

Script Redis minh họa atomic redeem:

```lua
-- KEYS[1]: key theo HMAC/sha256 token secret (không raw token)
local subject = redis.call("GET", KEYS[1])
if not subject then
    return false
end
redis.call("DEL", KEYS[1])
return subject
```

Nếu hai node cùng chạy script trên **cùng một key tại cùng Redis primary**, chỉ request đầu nhận được subject; request sau nhận null. Redis kiểm TTL khi truy cập key, nên key đã hết hạn không được trả về như token hợp lệ.

Nhưng đừng bỏ sót:

- Key nên phân vùng theo `purpose` và tenant để tránh token confusion.
- Một token có thể bị tiêu thụ bởi attacker nếu raw token đã bị lộ; do đó phải bảo vệ delivery và rate limit.
- Redis Cluster chỉ thực thi một Lua script trên keys thuộc slot cho phép. Ví dụ một key ở đây tránh cross-slot, nhưng nếu kiểm/thay đổi nhiều keys cần cùng slot hoặc một thiết kế transaction khác.
- Redis failover có thể mất **write đã acknowledged nhưng chưa được replicate/durable**, làm token vừa bị xóa xuất hiện lại trên replica sau promotion tùy topology/config. Nếu single-use tuyệt đối qua failover là yêu cầu cứng, phải thiết kế durability/consistency mạnh hơn hoặc dùng DB transaction/consensus phù hợp và test.
- Nếu script thành công nhưng network response bị mất, client không biết có tiêu thụ không; retry trả “used”. Phải định nghĩa UX khôi phục, **không mở một nhánh cho phép token đã dùng**.
- Không lưu raw token trong metric label, Redis MONITOR log, tracing hoặc audit output.

## 13. Java 17 runnable: một token chỉ có một người tiêu thụ thắng

Để thấy bất biến độc lập với framework, chương trình dưới đây mô phỏng **hai node tham chiếu một store chung trong cùng JVM**. `ConcurrentHashMap.remove(key, expectedValue)` là một phép so sánh/xóa nguyên tử trong mô phỏng. **Đây không phải mô phỏng mạng/Redis/DB thật.**

**`SingleUseTokenDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SingleUseTokenDemo {

    record Entry(String subject, long expiresAt) {}

    static final class SharedStore {
        private final ConcurrentHashMap<String, Entry> tokens =
                new ConcurrentHashMap<>();

        void issue(String value, String subject, long expiresAt) {
            tokens.putIfAbsent(value, new Entry(subject, expiresAt));
        }

        boolean consume(String value, String expectedSubject, long now) {
            Entry record = tokens.get(value);
            if (record == null
                    || now >= record.expiresAt()
                    || !record.subject().equals(expectedSubject)) {
                return false;
            }
            return tokens.remove(value, record);
        }
    }

    public static void main(String[] args) throws Exception {
        SharedStore shared = new SharedStore();
        shared.issue("lab-token-1", "alice", 10_000);

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                start.await();
                if (shared.consume("lab-token-1", "alice", 9_000)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread nodeA = new Thread(attempt, "node-A");
        Thread nodeB = new Thread(attempt, "node-B");
        nodeA.start();
        nodeB.start();
        start.countDown();
        nodeA.join();
        nodeB.join();

        System.out.println("accepted = " + accepted.get());

        shared.issue("lab-token-2", "bob", 10_000);
        System.out.println("expired = "
                + shared.consume("lab-token-2", "bob", 10_000));

        shared.issue("lab-token-3", "carol", 10_000);
        System.out.println("wrong-subject = "
                + shared.consume("lab-token-3", "alice", 9_000));
        System.out.println("correct-subject = "
                + shared.consume("lab-token-3", "carol", 9_000));
    }
}
```

Lệnh:

```bash
javac SingleUseTokenDemo.java
java SingleUseTokenDemo
```

Stdout chính xác:

```text
accepted = 1
expired = false
wrong-subject = false
correct-subject = true
```

Dù thứ tự hai threads không cố định, **có đúng một** lần `remove(value, expectedValue)` thành công, nên `accepted=1` là kết quả xác định. Token ở đúng thời điểm `expiresAt` bị coi là quá hạn vì điều kiện `now >= expiresAt`. Thử với subject sai không làm tiêu thụ token trong mô hình minh họa; hệ thống thật vẫn phải giới hạn số lần đoán và chọn semantics phù hợp chống enumeration.

**Không đưa `lab-token-1` vào production.** Demo dùng chuỗi dễ đoán để có stdout cố định; token thực cần CSPRNG và lưu dạng digest/HMAC có chính sách riêng.

## 14. Phát token, giao token và xác thực trên nút khác

Token store chỉ là **một phần** của flow. Quá trình phát/gửi và redeem cũng phải đúng:

1. Request phát magic link đi qua `POST /ott/generate`; giới hạn theo account, IP/source, số recipient, tenant và ngân sách email/SMS.
2. Service xác định account/verified recipient từ **trusted directory**, không nhận địa chỉ email đích tùy ý từ query param.
3. Token có entropy đủ, scope/purpose đúng, TTL ngắn; ghi store thành công trước khi gửi link cho user.
4. `OneTimeTokenGenerationSuccessHandler` gửi qua mail/SMS provider đáng tin cậy hoặc outbox đáng tin cậy, có chống gửi trùng/rate limit.
5. User mở link tại node bất kỳ. Trình duyệt thường tải trang submit, sau đó gửi token bằng request login đúng filter/CSRF contract.
6. `OneTimeTokenService.consume(...)` kiểm token và tiêu thụ duy nhất; authentication flow xác minh user vẫn còn active rồi tạo session.
7. Session được save vào **shared session store** trước khi browser cần dùng trong request tiếp theo.
8. Request kế tiếp tại node khác đọc session, thấy đúng principal và authorities.

### 14.1. Phát xong nhưng gửi email lỗi thì sao?

Nếu token đã được lưu nhưng mail provider lỗi, bản ghi vẫn tồn tại cho đến TTL. Không gửi token raw vào error body/log. Có thể retry gửi bằng outbox riêng nhưng phải tránh tạo nhiều token vô hạn cho một account hoặc gửi link đã hết hạn. Tùy policy, revoke token không phát được và cho user yêu cầu lại.

### 14.2. Đã consume token nhưng tạo session thất bại thì sao?

Đây là **ranh giới consistency quan trọng giữa hai store**:

```text
DB/Redis OTT: consume thành công (token đã mất)
             ↓
Session Redis: save context thất bại
             ↓
Client: login lỗi, retry token → token đã dùng
```

Không nên “trả token về trạng thái chưa dùng” tự động: điều đó mở nguy cơ replay trong race/failover. Thiết kế UX an toàn là báo yêu cầu lại magic link (với rate limit), hoặc dùng một flow handoff/idempotency được thẩm định có expiry/subject binding. Nếu business đòi exactly-once end-to-end, cần phân tích transaction giữa token store và session store; một DB transaction không tự bao gồm cả Redis session commit.

### 14.3. Token sống sót qua response network timeout?

Nếu OTT đã bị consume nhưng response `302` hoặc session cookie mất trên mạng, client có thể thấy request thất bại mặc dù backend đã cấp session. Retry raw token vẫn bị từ chối; đây có thể là hệ quả đúng để chống replay. Ghi event ID/correlation và hướng người dùng thử vào trang protected, sau đó xin link mới nếu chưa có session. Không tạo “nút retry” cho phép dùng lại token mà không có một cơ chế idempotency đã phân tích an toàn.

## 15. Races giữa session, quyền và dữ liệu người dùng

Ngoài OTT, nhiều thao tác an ninh có thể đồng thời xảy ra ở các node:

| Race | Hậu quả tiềm ẩn | Biện pháp |
| --- | --- | --- |
| A logout, B request đang dùng session cũ | Có thể thực hiện tác vụ nhạy cảm sau thời điểm logout | Check revocation/role ở bước commit nhạy cảm, token epoch/version |
| A đổi password, B tiếp tục session cũ | Phiên trước vẫn có quyền nếu không bị revoke | Session invalidation/all-sessions revoke theo policy |
| A cập nhật MFA assurance, B save snapshot cũ | Mất factor mới hoặc khôi phục factor cũ | CAS/versioned state; step-up store tập trung |
| A và B đồng thời rotate session ID | Cookie ID/repository mapping có thể không đồng bộ | Test session fixation strategy và concurrent logins |
| A phát OTT mới, B consume OTT cũ | Token trước vẫn có thể còn nếu không revoke | Per-account nonce/generation version nếu “chỉ link mới nhất” |
| A refresh token và B refresh cùng token | Replay/double issue nếu không atomic rotate | Conditional compare-and-swap + token family |
| A đọc roles trước thay đổi quyền, B xóa role | A trả dữ liệu theo quyết định cũ | Định nghĩa consistency window, kiểm quyền tại thao tác nhạy cảm |
| A/B cập nhật `lastAccessedTime` của cùng session | Có thể ghi TTL/lần truy cập không nhất quán | Store policy/time, quan sát session expiration |

**Vấn đề không chỉ là storage location.** Chia sẻ Redis giữa A/B giải quyết *visibility* nhưng không tự bảo đảm *atomicity cho mọi trường* hoặc *transaction xuyên nhiều stores*. Cần lựa chọn bất biến và primitive phù hợp theo từng quyết định bảo mật.

## 16. Điều kiện nhất quán khi Redis/DB failover

### 16.1. Read-after-write

Sau khi login được trả thành công, node B phải đọc được session đúng từ primary/shared store. Nếu dùng replica read với replication delay, B có thể thấy session cũ/chưa có. Cấu hình read/write routing nhất quán theo session contract; không mặc định đưa auth state vào eventual-consistency cache/replica.

### 16.2. Atomicity

Một thao tác token consume phải **được quyết định ở một nơi**. Với Redis Lua một key, nó atomic trên primary tại thời điểm thực thi. Với PostgreSQL, conditional DELETE/UPDATE trong transaction có thể chọn đúng một winner. Nếu multi-primary có conflict resolution eventual, hai node có thể đồng thời nhận hai winners nếu không có coordination; không phù hợp cho strict single-use.

### 16.3. Durability và acknowledgment

Redis replication thông thường có thể asynchronous; write acknowledged ở primary chưa đồng nghĩa đã durable trên node mới sau failover. `WAIT`/`WAITAOF` và cấu hình AOF/replication có thể giảm cửa sổ mất dữ liệu nhưng không tự biến Redis thành giao thức consensus cho mọi failure model. Với token có yêu cầu chống replay tuyệt đối, cân nhắc store có giao dịch bền/consistency phù hợp và kiểm thử kịch bản promotion.

### 16.4. Clock consistency

- Session expiration, OTT TTL và TOTP window phải định nghĩa nguồn thời gian.
- Tránh dùng giờ tùy ý từ client. Đối với Redis TTL, store kiểm thời gian tồn tại theo cơ chế của nó; với SQL dùng DB time trong consume condition khi phù hợp.
- Đồng bộ NTP cho nodes, DB, IdP, metrics; ghi mốc UTC và phân biệt event time với processing time.
- Một số library có `Clock` injectable (như `JdbcOneTimeTokenService#setClock`), hữu ích cho deterministic test; không để các node lệch giờ lớn.
- Không cấp quyền chỉ vì scheduled cleanup chưa kịp xóa token hết hạn.

### 16.5. Partition và timeout

Khi store không truy cập được, ứng dụng phải quyết định **fail closed hay degraded mode có bảo vệ**. Với session chưa xác minh và token một lần, hợp lý là **không xác thực thành công khi không có câu trả lời đáng tin**. Trả HTTP 503/401 tùy nguyên nhân, tránh nói sai “mật khẩu sai” khi Redis gặp sự cố.

Không thêm một cache local cho OTT để “giảm lỗi Redis” nếu cache có thể cho token đã consume được sử dụng lại sau partition.

## 17. Redis eviction, memory và TTL không đồng nghĩa an toàn tuyệt đối

Redis có cơ chế maxmemory/eviction. Nếu policy cho phép evict key session/OTT trước khi hết hạn, người dùng có thể bị logout bất ngờ hoặc magic link không còn dùng được. Đây thường là rủi ro availability/UX; nhưng nếu Redis bị promote replica cũ, dữ liệu đã xóa có thể xuất hiện trở lại, tạo rủi ro safety khác.

Theo dõi:

- `used_memory`, `maxmemory`, `evicted_keys`, expired keys, memory fragmentation.
- Throughput `GET/SET/DEL` của session và OTT, latency p95/p99.
- TTL thực tế của session và OTP, số phiên active, số token pending theo purpose.
- Redis connection pool, timeout, retries, rejected calls, replication lag và failover time.
- Key cardinality: attacker tạo nhiều username/token requests có thể tăng state đến OOM.
- Serializer failures và session deserialization errors qua rolling deployments.
- Auth success/401/403, login redirects, OTT invalid/used/expired, duplicate redemption attempts.

**Đừng đặt Redis `maxmemory-policy` và TTL theo cảm tính.** Chọn riêng namespace/instance/DB phù hợp, capacity planning, quota ở ingress và hạn chế token issue. Với session có yêu cầu không evict trước hạn, cần vận hành storage theo SLO tương ứng.

## 18. Kiểm thử multi-node và concurrency: không thể thiếu

### 18.1. Ma trận bắt buộc

| Tình huống | Kỳ vọng |
| --- | --- |
| Login tại A, GET /me tại B dùng cùng session cookie | Đúng user/authorities; không login lại |
| Login A rồi kill A, GET /me tại B | Phiên vẫn hợp lệ nếu shared store sống và chưa expired |
| A và B login hai user khác nhau, xen kẽ GET | Không rò identity/cross-session |
| Logout B rồi truy cập A với session cũ | Không còn authenticated |
| Session đã hết idle timeout | Request protected không tiếp tục có quyền |
| A phát OTT, B redeem | B nhận được token hợp lệ và tạo session |
| A/B đồng thời redeem cùng OTT | **Tối đa một** request thành công |
| Consume OTT xong rồi retry cùng link | Bị từ chối như used/invalid |
| Token quá hạn nhưng row/Redis key còn tồn tại | Bị từ chối |
| OTT account A bị dùng để đăng nhập B | Không được nhầm subject |
| Login user đã disabled hoặc password revoked | Chặn theo account policy |
| Session ID rotation khi login | Old session ID không biến thành phiên có quyền |
| Redis failover khi write/delete session | Không tạo phantom session/không chấp nhận session đã revoke |
| Token store DB timeout khi consume | Không mặc định cho qua |
| Hai app version chạy cùng lúc | Deserialize session/OTT record tương thích hoặc fail safely |
| Một node có clock lệch nhiều | Expiry/TTL policy không bị bỏ qua |
| Một số email sends bị retry | Không tạo token reuse hoặc spam không hạn chế |
| Token consume được nhưng session save fail | UX xin token mới, không hồi sinh token cũ |
| Redis/DB pool cạn | Không trở thành authentication bypass |
| Redis Cluster/index events sai lệch | Không coi index cleanup event là bằng chứng revoke tuyệt đối |

### 18.2. Tách loại test

**Unit test** kiểm token algorithm, CAS/conditional delete, đúng expiry boundary và policy subject. Demo Java ở mục 13 giúp thấy bất biến trong JVM nhưng **không chứng minh** implementation Redis/JDBC.

**MockMvc** có thể kiểm form login thật, `SecurityContextRepository` và POST→GET bằng cùng `MockHttpSession`. Nó chỉ chạy trong một Spring context hoặc setup được thiết kế riêng.

**Integration test đa nút** dùng hai process/app containers, chung Redis/PostgreSQL; đẩy request cưỡng bức qua A/B thay vì để LB sticky. Test song song dùng barrier/latch, kiểm chỉ một lượt redeem thành công và trạng thái DB sau test.

**Chaos/failover test** mô phỏng dừng node, Redis failover, DB replica lag, network partition, pod restart, autoscale, Redis eviction, rollout nhiều phiên bản. Báo cáo phải nêu safety invariants có giữ được không, không chỉ tỉ lệ HTTP 200.

### 18.3. Test atomic consumption có thể sai như thế nào?

Nếu test concurrency chỉ gửi hai request nối tiếp, cả hai sẽ không thành công ngay cả với implementation `find → delete` không nguyên tử (request thứ hai thấy token mất), tạo **false confidence**. Cần hàng trăm/hàng nghìn lượt thử đồng thời, khởi động cùng barrier, qua **hai nút thật** và đo số thành công mỗi token.

Nếu có retry ở load balancer khi 502/timeout, phải đảm bảo retry POST redeem không đưa một request đã thành công chạy lại dưới credential cũ. Log correlation/event ID để phân biệt network retry với người dùng nhấp lại link, nhưng không ghi raw token.

## 19. Bảo mật cookie, token và dữ liệu tại store

### 19.1. Cookie và session

- Bắt buộc HTTPS và cookie `Secure` trong production.
- Sử dụng `HttpOnly`, `SameSite` và `Path/Domain` phù hợp kiến trúc login/SSO.
- Không dùng một cookie domain rộng để các subdomain không tin cậy cùng nhận session.
- Có CSRF protection cho web state-changing requests dựa vào cookie/session.
- Session fixation protection khi login; không log cookie/session ID, không gửi ID trong URL.
- Logout/timeout/role change phải xử lý invalidation và mọi client/session theo chính sách rõ.
- Session store cần encryption in transit, ACL, hạn chế administrative commands, backup/restore policy.

### 19.2. OTT/magic links

- Token có entropy cao, thời hạn ngắn, một lần dùng, subject/purpose binding.
- Raw token không nên bị lưu trong analytics, third-party link preview, access logs, tracing hoặc browser referrer. Áp `Referrer-Policy: no-referrer` cho trang chấp nhận link và tránh third-party scripts trước khi token được xử lý.
- Nếu email security scanner tự click magic link, chỉ click GET **không nên tiêu thụ token ngay** nếu flow được thiết kế GET trang submit rồi POST consume có CSRF phù hợp. Đừng bật side effect xác thực trên GET từ external scanner.
- Không bao giờ tự redirect magic link tới URL do query parameter không được kiểm chứng; tránh open redirect.
- Rate limit issue/verify và trả thông báo chung để tránh username enumeration.
- Nếu store giữ raw token, cần xem xét thay bằng hash/HMAC theo threat model, mã hóa và quyền DB; không coi JDBC/Redis mặc nhiên đã loại bỏ mọi dữ liệu nhạy cảm.

### 19.3. Redis/DB bảo mật

Kẻ có quyền đọc session Redis có thể tiếp cận SecurityContext hoặc session attributes; người có quyền sửa có thể giả mạo state. **Redis không phải kho dữ liệu vô hại** chỉ vì nằm trong private subnet. Dùng mTLS/TLS nếu hỗ trợ, IAM/ACL, network segmentation, no public exposure, least privilege, secrets rotation và audit truy cập. Backup/restore phải giữ nguyên nghĩa expiry/revocation; restore snapshot cũ có thể **hồi sinh trạng thái đã thu hồi** nếu không có biện pháp đối chiếu authVersion/ledger.

## 20. Các lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng local `HttpSession` khi có nhiều pods | Người dùng bị logout khi đổi node | Spring Session shared store hoặc thiết kế khác rõ |
| Chỉ bật LB sticky session | Không xử lý node chết/rolling deploy | Shared store + integration test failover |
| Có Redis nhưng quên save `SecurityContext` trong custom login | Request sau anonymous | `SecurityContextRepository.saveContext(...)` |
| Dùng `InMemoryOneTimeTokenService` trên mỗi node | A phát, B không consume được | JDBC/Redis shared OneTimeTokenService |
| Đọc token rồi xóa không nguyên tử | Hai node cùng login từ một token | Conditional delete/transaction/Lua |
| Không check TTL khi consume | Token hết hạn vẫn có thể dùng trước cleanup | Check expiry trong quyết định consume |
| Dùng `synchronized` để khóa OTT | Chỉ khóa một JVM | Primitive atomic của shared store |
| Tin Redis replication async = exactly once bền vững | Failover có thể hồi sinh state | Đánh giá durability/replay, test promotion |
| Đặt session TTL bằng OTT TTL | User logout nhanh hoặc link sống quá lâu | Phân biệt lifecycle theo object |
| Dùng JWT stateless như session stateful | Bỏ qua signature/audience hoặc tạo state thừa | JWT decoder và authorization đúng |
| Dùng replica stale cho auth state | GET sau login có thể không thấy phiên | Read-after-write consistency theo contract |
| Giữ toàn bộ principal/entity serialized trong session | Lỗi rolling deploy, lộ dữ liệu | Snapshot tối thiểu, serializer có kiểm soát |
| Không kiểm session fixation | Session ID cũ được nâng quyền | Session ID rotation và cookie security |
| Không kiểm principal khi OTP redeem | Account confusion / phishing | Bind subject/tenant/purpose với token |
| Không có rate limit phát OTT | Mail bombing và tăng key store | Quota account/source/global |
| Token consume xong nhưng session save fail thì hồi sinh token | Tạo replay cửa sau | Safe recovery/new token, idempotency design |
| Lưu token/cookie raw trong logs | Credential replay | Redact tại nguồn, audit bằng ID đã hash |
| Cache authorization revocation local quá lâu | Node A đã revoke, B vẫn dùng quyền cũ | Epoch/version checks, TTL bounded, critical recheck |
| Dùng cleanup events làm nguồn sự thật expired | Events có thể trễ/mất | Quyết định dựa vào repository expiry |
| Không test đa nút thật | Không phát hiện race và cross-node bugs | Integration 2+ nodes, chaos, concurrency |
| Redis outage → `permitAll()` | Authentication bypass | Fail closed với UX/error contract rõ |

## 21. Checklist triển khai và vận hành

Trước khi rollout, trả lời được:

- [ ] Đã phân loại session, OTT, CSRF, refresh token, JWT và xác định store nào sở hữu chúng?
- [ ] Mọi node dùng cùng session namespace/store, đúng cookie contract và SecurityContextRepository?
- [ ] Có bằng chứng GET /me trên node B đọc đúng identity sau login tại A không?
- [ ] Test logout tại B xóa quyền truy cập từ A và những request cũ?
- [ ] OTT có CSPRNG, TTL, subject/purpose binding, rate limit, store chung?
- [ ] Có **atomic consume** dưới 2+ node với requests đồng thời thật không?
- [ ] Hết hạn được check khi consume, không phụ thuộc scheduled cleanup?
- [ ] DB schema OTT đúng phiên bản Spring Security 6.4+ và được migration quản lý?
- [ ] Đã kiểm CSRF của OTT POST, verified recipient delivery và tránh token bị scanner tiêu thụ bởi GET?
- [ ] Redis/session serialization compatible với hai app versions trong rolling deploy?
- [ ] Redis eviction, failover, replication lag và memory capacity có giới hạn/cảnh báo?
- [ ] Có định nghĩa fail-closed behavior khi không đọc được auth state hoặc token store?
- [ ] Có xét quyền revocation, MFA step-up, refresh rotation với concurrency/versioned state?
- [ ] Có metrics p95/p99 session reads, token consumption, invalid/used/expired, login failure và retry?
- [ ] Không log session ID, OTT raw token, passwords, refresh/access token và payload nhạy cảm?
- [ ] Có test hai cookie jars/hai users, kill node, restore snapshot và failover?
- [ ] Có tài liệu rõ ràng mức bảo đảm consistency/durability, không chỉ “sử dụng Redis” như tuyên bố chung?

## 22. Bài tập tự thực hành

1. Dùng project Spring Boot 3.x form login ở mục 6, chạy 2 instances A/B chung Redis. Đăng nhập ở A và truy cập `/me` tại B. Sau đó kill A và gửi request tiếp vào B.
2. Thử thay Redis bằng local HttpSession. Vì sao test một node pass nhưng test qua B fail? Có phải sticky session sửa được mọi failure mode không?
3. Bật `oneTimeTokenLogin()` trong Spring Security 6.5, đăng ký `JdbcOneTimeTokenService` với bảng schema framework và handler gửi mail an toàn. Phát ở A, redeem ở B.
4. Viết integration test đồng thời 10–100 requests cùng sử dụng một OTT. Giữ invariant **số thành công tối đa bằng 1**; test qua cả hai nodes và khi có retry.
5. Thay custom token store `read → delete` bằng PostgreSQL conditional DELETE RETURNING hoặc Redis Lua atomic. Giải thích sự khác biệt khi hai requests đọc cùng row.
6. Tạo fault injection: consume token thành công nhưng save session Redis timeout. Đề xuất UX khôi phục không cho token cũ dùng lại; test số lần consume vẫn là một.
7. Thử Redis restart/failover sau khi xóa OTT. So sánh tình huống write acknowledged nhưng replica chưa theo kịp, và lựa chọn store khi yêu cầu chống replay nghiêm ngặt.
8. Thử rolling deploy hai app versions có custom UserDetails class khác cấu trúc. Lập migration/serializer compatibility test để tránh mất identity hoặc deserialize lỗi.
9. Thiết kế revoke-all-sessions khi password change, với `authVersion` gắn user và mỗi phiên. Cần xác minh version tại những bước nào?
10. Phân biệt OTT login, TOTP MFA, refresh token rotation và JWT stateless ở góc nhìn shared state, TTL và replay.

## 23. Tổng kết và nguồn đọc chính thức

- Với website dùng form/session trên nhiều node, **share HttpSession và SecurityContext qua store chung**; Spring Session Redis là một lựa chọn tiêu biểu.
- **Sticky session chỉ là routing optimization**; không thay visibility/failover. Spring Security 6 custom login còn cần explicit save context.
- OTT trên Spring Security **6.4+** sử dụng `OneTimeTokenService`; default in-memory không phải kho multi-node. Dùng JDBC/shared service phù hợp, có schema, expiry và atomic consumption.
- **Shared store khác atomicity; atomicity khác durability.** Redis Lua/conditional SQL giúp xử lý race; replica failover và network timeout vẫn đòi thiết kế consistency rõ.
- Mỗi object có **lifecycle và yêu cầu riêng**: session idle TTL, one-use OTT short expiry, JWT stateless, refresh rotation, MFA assurance, logout/revocation.
- Chỉ công bố authentication thành công khi có đủ bằng chứng. Không fallback `permitAll()` nếu Redis/DB lỗi; kiểm nạn nhân/subject và chống replay.
- Bảo vệ cookie/token, quan sát latency/backlog/eviction và **kiểm thử hai nút thật** với concurrency, expiry, rolling deploy và failover.

**Tài liệu chính thức để đối chiếu theo phiên bản:**

- [Spring Session 3.5 — Spring Boot + Redis](https://docs.spring.io/spring-session/reference/3.5/guides/boot-redis.html)
- [Spring Session 3.5 — Redis configuration và repository types](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session 3.5 — Spring Session cùng Spring Security](https://docs.spring.io/spring-session/reference/3.5/guides/java-security.html)
- [Spring Security 6.5 — Session Management và explicit SecurityContext save](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 — OneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security 6.5 — JdbcOneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)