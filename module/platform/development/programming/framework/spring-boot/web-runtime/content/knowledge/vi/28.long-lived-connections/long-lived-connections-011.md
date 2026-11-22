# Giới hạn phiên xác thực hoặc token khi kết nối tồn tại lâu

## 1. Đặt vấn đề: kết nối còn mở không chứng minh quyền còn hợp lệ

Trong hệ thống **Spring Boot - web-runtime**, kết nối **WebSocket**, **STOMP over WebSocket**, **Server-Sent Events (SSE)** và HTTP streaming có thể tồn tại lâu hơn một HTTP request thông thường. Người dùng có thể được xác thực lúc mở kết nối, nhưng sau đó access token hết hạn, logout, bị khóa tài khoản hoặc bị thu hồi quyền.

**Không được mặc định framework sẽ tự kết thúc mọi kết nối dài đúng lúc token hết hạn.** Xác thực thường diễn ra ở HTTP handshake/SSE GET hoặc STOMP CONNECT. Những message WebSocket hoặc SSE events phát sinh sau đó không tự trở thành các HTTP requests mới đi lại toàn bộ Spring Security filters.

Bốn trạng thái cần tách biệt:
- **HTTP session:** dữ liệu phiên do Servlet container/Spring Session giữ, có session ID, idle timeout, invalidate.
- **Access token:** JWT hoặc opaque token có exp/TTL, scope, issuer/audience, chính sách xác minh và revocation.
- **Transport connection:** TCP/WebSocket/SSE stream còn hoạt động theo network lifecycle.
- **Authorization:** khả năng được truy cập topic, tenant, record, xem/sửa dữ liệu tại từng thời điểm.

Ngoài ra, hệ thống có thể đặt **connection lease**: thời hạn tuyệt đối từ lúc xác thực đến lúc phải reconnect/re-auth, độc lập với ping/pong và timeout của TCP.

Mục tiêu bài học là biết khi nào xác thực được thực hiện, khi nào cần kiểm tra lại token/quyền, xử lý logout/revocation giữa kết nối, bảo vệ SSE/WebSocket trên nhiều node và thực hành một **Spring Boot 3.3.13 + Java 17 SSE lab** có token hết hạn ngay trong stream.

## 2. Những loại thời hạn không thay thế cho nhau

| Loại | Điều bị giới hạn | Có tự đóng mọi WebSocket/SSE đã mở không? |
| --- | --- | --- |
| JWT exp / opaque token TTL | Khoảng thời gian verifier chấp nhận credential | **Không mặc định**, tùy middleware và application policy |
| HttpSession maxInactiveInterval | Session idle theo container/repository | **Tùy tích hợp** WebSocket/Spring Session |
| Cookie Max-Age/Expires | Browser giữ/gửi cookie | Không báo cho socket cũ tự đóng |
| WebSocket idle timeout | Transport không hoạt động theo network policy | Có thể đóng dù token còn hạn |
| SSE async timeout | Vòng đời một response đang mở | Không phải kiểm tra access token |
| Heartbeat / ping-pong | Kết nối còn sống không | Không chứng minh user còn được phép |
| Max connection age | Tuổi kết nối theo application policy | Có thể buộc reconnect dù traffic đều |
| Revocation event | Token/user/session bị thu hồi | Cần tới đúng instance và được thực thi |
| Authorization cache TTL | Thời gian cache quyết định quyền | Không thay token expiry |

**Ví dụ 1:** JWT có exp lúc 10:15, WebSocket đã mở lúc 10:00 và chưa được đóng lúc 10:45. Nếu ứng dụng chỉ xác minh JWT ở handshake rồi dùng Principal đã lưu, việc hết hạn của JWT không đương nhiên làm socket tự đóng.

**Ví dụ 2:** một kết nối WebSocket gửi heartbeat mỗi vài giây để tránh proxy idle timeout. Điều đó không phải hành động login lại hoặc gia hạn access token.

**Ví dụ 3:** browser mất cookie nhưng WebSocket cũ còn mở. HTTP request tiếp theo có thể không được xác thực, còn socket cũ vẫn cần cơ chế riêng để đánh giá quyền/đóng.

## 3. WebSocket bắt đầu bằng HTTP handshake

Với **Spring WebSocket trên Servlet**, việc thiết lập WebSocket bắt đầu bằng một HTTP Upgrade request:

~~~http
GET /ws HTTP/1.1
Host: example.test
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: ...
Cookie: JSESSIONID=...
~~~

Mẫu chỉ mô tả cấu trúc, header thực tế còn có Origin và nhiều trường khác.

~~~text
HTTP request /ws
      |
      v
Spring Security HTTP filters
      |
      v
Authentication + Principal
      |
      v
HTTP 101 Switching Protocols
      |
      v
WebSocketSession gắn với Principal
      |
      +---- SEND messages
      +---- SUBSCRIBE destinations
      +---- receive server events
      +---- heartbeat
      |
      +---- Recheck token exp/role?
              Phụ thuộc ứng dụng và tích hợp
~~~

Spring Framework có thể chuyển **Principal từ HttpServletRequest** vào WebSocketSession. Nhưng khi HTTP Upgrade hoàn tất, từng WebSocket frame **không tự được xử lý như HTTP request mới**. Không thể đổi response 101 đã gửi thành HTTP 401 khi token hết hạn.

### 3.1. Trình duyệt không tùy ý thêm Authorization header vào WebSocket handshake

Native browser **WebSocket constructor** cho phép truyền URL và subprotocols nhưng không hỗ trợ tùy ý đặt HTTP Authorization header như fetch. Các mô hình hay dùng:
1. **Cookie/session authentication:** cookie được browser gửi trong handshake; HTTP security xác thực và gắn Principal.
2. **STOMP CONNECT authentication:** STOMP client đưa token vào CONNECT frame; **ChannelInterceptor** do ứng dụng cấu hình phải verify token và thiết lập identity.
3. **Connection ticket ngắn hạn một lần:** endpoint HTTPS được bảo vệ cấp ticket riêng, WebSocket handshake xác minh ticket có TTL ngắn và chống replay.

Không đưa **access token hoặc refresh token dài hạn vào URL query**, vì URL có thể lộ trong proxy logs, monitoring, analytics hoặc debugging. Không giả định thêm STOMP header Authorization là Spring Security tự hiểu nếu chưa cài authentication interceptor.

### 3.2. STOMP CONNECT khác HTTP handshake

STOMP là giao thức nhắn tin trên WebSocket/SockJS. **CONNECT, SUBSCRIBE và SEND** là các frame có ý nghĩa khác nhau:
- CONNECT mở logic messaging session.
- SUBSCRIBE đăng ký destination để nhận dữ liệu.
- SEND gửi message tới destination.
- Heartbeat duy trì liveness.

Nếu authentication diễn ra bằng token của CONNECT, ứng dụng cần bảo vệ HTTP endpoint phù hợp, xác minh token trong inbound channel, gắn Principal đúng cách, rồi **vẫn phải kiểm tra expiry/authorization trong thời gian connection sống**. CONNECT authenticated không đồng nghĩa SUBSCRIBE mọi topic đều được phép.

## 4. Spring Session WebSocket integration làm thay đổi vòng đời HttpSession

Hai phát biểu tuyệt đối đều sai: **“HttpSession hết hạn chắc chắn đóng mọi WebSocket”** và **“WebSocket không thể bị đóng khi HttpSession hết hạn”**.

Nếu không có tích hợp, HTTP session bị invalidate không nhất thiết tự đóng một socket do ứng dụng tự tạo hoặc quản lý. Nhưng **Spring Session WebSocket integration** cung cấp các thành phần phối hợp:
- **SessionRepositoryMessageInterceptor:** cập nhật last-accessed time của Spring Session khi inbound WebSocket messages được xử lý.
- **WebSocketRegistryListener:** theo dõi ánh xạ session ID với các WebSocket connections.
- **SessionDestroyedEvent/SessionExpiredEvent** và các thành phần liên quan: cho phép đóng các sockets tương ứng khi HTTP session bị hủy/hết hạn, nếu event infrastructure và integration hoạt động đúng.

Vì vậy user trò chuyện liên tục có thể làm **HttpSession không bị coi idle**. Nhưng **JWT exp độc lập với HttpSession idle**: message activity không thay đổi timestamp exp của JWT.

### 4.1. Cần giới hạn tuyệt đối, không chỉ idle timeout

Nếu quy định “đăng nhập tối đa tám giờ trước khi phải xác thực lại”, chỉ cấu hình **maxInactiveInterval=20 phút** không đủ: người dùng hoạt động đều có thể giữ session active lâu hơn. Hãy áp **absolute auth age** hoặc **max connection lease**, dù heartbeat/session activity vẫn diễn ra.

### 4.2. Logout trên nhiều replica

User logout tại node A, nhưng WebSocket của user đang gắn với node B. Map sockets local tại A không tự đóng connection trên B. Cần session repository có events phù hợp, pub/sub hoặc revocation bus, connection registry gắn session/token/user ID và cleanup khi close. Sticky routing không thay việc propagate revocation toàn cụm.

## 5. Access token expiry và authorization phải được kiểm lại

**JWT được ký hợp lệ lúc connect không có nghĩa luôn hợp lệ sau đó.** User có thể bị disabled hoặc role bị thu hồi trước exp; JWT cũng có thể hết hạn trong khi WebSocket hoặc SSE tiếp tục chạy.

| Sự kiện | Cần hành động gì? |
| --- | --- |
| Token tới exp | Ngừng dữ liệu nhạy cảm, đóng hoặc re-auth/reconnect |
| Token revoke trước exp | Propagate revocation, cắt affected streams |
| User bị khóa | Từ chối SEND/SUBSCRIBE, dừng private events |
| Role/tenant membership đổi | Reauthorize và bỏ subscriptions không còn quyền |
| User logout | Invalidate session/token và đóng connections theo policy |
| Transport vẫn ping/pong | Chỉ cho thấy liveness, không xác nhận quyền |
| Client reconnect bằng token cũ | Xác minh lại; trả 401/403 hoặc từ chối handshake |
| Refresh access token mới | Kiểm issuer, audience, exp, scope, owner, rồi reauthorize |

Một connection registry có thể ghi những thuộc tính tối thiểu:

~~~text
connectionId       = định danh tương quan, không phải bearer secret
userId             = danh tính đã xác minh
tenantId           = tenant đã được cho quyền
tokenId            = jti hoặc opaque ID tham chiếu
authenticatedAt    = thời điểm xác thực
tokenExpiresAt     = expiry của access credential
maxConnectionUntil = thời hạn tuyệt đối của connection
effectiveExpiry    = min(tokenExpiresAt, maxConnectionUntil)
policyVersion      = phiên bản phân quyền/revocation
~~~

**Không lưu raw bearer token vào logs**, và đừng tin snapshot role được chụp ở connect mãi mãi. Cần hiểu clock skew của validator và đồng bộ thời gian bằng NTP.

## 6. Ba chiến lược giới hạn quyền trên kết nối dài

### 6.1. Đóng tại deadline

Khi connect hợp lệ, app tính **effectiveExpiry** = mốc sớm nhất của token exp và max connection age. Đến deadline, dừng gửi dữ liệu, đóng WebSocket hoặc hoàn tất SSE, yêu cầu client refresh credential qua HTTPS rồi reconnect. Ưu điểm là chính sách dễ giải thích; nhược điểm là phải làm lại subscriptions và resume cursor.

### 6.2. Revalidate trước mỗi message/event nhạy cảm

Trước SEND, SUBSCRIBE hoặc outbound private event:
1. Kiểm token/session chưa revoke, chưa hết hạn.
2. Kiểm user chưa disabled.
3. Kiểm role/scope và quyền sở hữu record/tenant hiện tại.
4. Chỉ sau khi đạt mọi điều kiện mới nhận/gửi dữ liệu.

Ưu điểm là giảm cửa sổ rủi ro. Nhược điểm là chi phí lookup và race nếu quyền đổi giữa lúc check với send; phải kiểm sát điểm publish và xử lý frames đang queue.

### 6.3. Kiểm tra định kỳ kết hợp revocation event

Một số hệ thống kiểm mỗi N giây và có event bus khi user logout/role change. N giây chỉ là **chu kỳ kiểm**, không bảo đảm thu hồi tức thì khi network, scheduler hoặc queue chậm. Đo metric **revokedAt → lastSensitiveEventDeliveredAt** để biết độ trễ thực tế và điều chỉnh security SLA.

Không dùng cùng một chu kỳ kiểm cho tất cả dữ liệu: bản tin công khai và báo cáo tài chính riêng tư có nhu cầu khác nhau.

## 7. SSE: một HTTP response chứa nhiều events

Spring MVC có **SseEmitter** để giữ response mở và gửi nhiều SSE events. Xác thực HTTP thường diễn ra lúc bắt đầu **GET /events**, không tự được thực hiện lại cho từng emitter.send().

~~~text
GET /api/events + Bearer token
          |
          v
HTTP auth ở request đầu
          |
          v
HTTP 200 text/event-stream
          |
          +---- event 1
          +---- event 2
          +---- token expires
          +---- app rechecks expiry
          +---- stop sensitive events
          +---- complete stream
          |
          v
New GET after refresh/authentication
~~~

**Không thể đổi HTTP 200 thành HTTP 401 sau khi đã phát headers và bắt đầu streaming.** Thay vào đó, ngừng phát, có thể gửi event **auth-expired** tối thiểu không nhạy cảm, hoàn tất stream; HTTP request mới được kiểm tra token và có thể trả 401.

### 7.1. Native browser EventSource và Bearer header

Native EventSource API không có tùy chọn đặt arbitrary Authorization: Bearer header như fetch. Với browser:
- Cookie/session authentication có thể dùng, nhưng phải xử lý SameSite, HTTPS, CORS credentials và policy dữ liệu.
- Nếu yêu cầu bearer header, dùng **fetch streaming** hoặc SSE client hỗ trợ thêm headers.
- Không đặt token dài hạn vào query URL chỉ để dùng native EventSource.

Lab phần 10 dùng **curl + Bearer header**, không phải native EventSource client.

### 7.2. Auto-reconnect không được biến thành retry loop

EventSource có thể tự nối lại khi stream kết thúc. Nếu token đã hết hạn, client phải:
1. Gọi **EventSource.close()** để ngừng retry stream cũ.
2. Refresh credential qua HTTPS hoặc yêu cầu login lại.
3. Mở stream mới với credential được xác minh.
4. Resume bằng event cursor được kiểm quyền, nếu nghiệp vụ có replay.

**Last-Event-ID không phải credential**: user không được xem lịch sử của tenant khác chỉ vì biết ID.

## 8. WebSocket/STOMP: bảo vệ SUBSCRIBE và SEND, không chỉ CONNECT

Một authenticated user có thể vẫn **không được** subscribe vào topic đơn hàng của người khác. Kiểm tra ở nhiều điểm:
- Handshake/CONNECT: xác thực danh tính.
- SUBSCRIBE: xác minh user/tenant được phép nhận destination.
- SEND: xác minh quyền thực hiện action.
- Publish/fan-out: không broadcast dữ liệu nhạy cảm tới subscribers không hợp lệ.
- Role change: loại subscription hoặc đóng connection khi quyền bị thu hồi.
- Replay: kiểm lại quyền của từng event lịch sử.

Spring Security có **@EnableWebSocketSecurity** và **AuthorizationManager<Message<?>>** cho Spring Messaging/STOMP, nhưng **các rule authorization không tự bảo đảm JwtDecoder chạy lại mỗi giây**. Nếu token có thể hết hạn sau CONNECT, app cần policy/ChannelInterceptor hoặc connection lease.

Ví dụ fragment không độc lập:

~~~java
@Configuration
@EnableWebSocketSecurity
class StompSecurityRules {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
            .simpDestMatchers("/app/**").authenticated()
            .simpSubscribeDestMatchers("/user/queue/**").authenticated()
            .anyMessage().denyAll();
        return messages.build();
    }
}
~~~

Fragment cần Spring Security Messaging, WebSocket/STOMP broker config và imports tương ứng. Cần thêm **object-level authorization** cho từng tenant/user ngay ở service/broker, vì authenticated/role không đương nhiên cấp quyền trên mọi resource.

### 8.1. Same Origin và CSRF

Browser không áp Same Origin Policy cho WebSocket tương đương fetch/XHR. Với cookie-based authentication, phải kiểm allowed origins và CSRF defense. Tài liệu Spring Security STOMP message security yêu cầu **CSRF token cho CONNECT** theo cấu hình mặc định, nhằm hạn chế cross-site WebSocket requests. Origin check là lớp bổ sung, không phải authentication: non-browser clients có thể giả Origin.

### 8.2. Close codes

RFC 6455:
- **1000**: normal closure.
- **1008**: policy violation, có thể dùng khi user không còn đáp ứng auth policy.
- **1011**: server gặp unexpected condition.
- **1006**: reserved để biểu diễn abnormal closure không nhận Close frame; **không được gửi 1006** trong Close frame.

Các mã custom như 4401 là quy ước ứng dụng, không phải mã được mọi WebSocket client hiểu. Sau handshake, không cố trả HTTP 401 trên WebSocket frames.

## 9. Refresh/reconnect và giới hạn phiên tối đa

Quy trình đề xuất:

~~~text
HTTP login/token issue qua HTTPS
        |
        v
Open SSE/WebSocket với identity hợp lệ
        |
        v
Server: connection lease + authorization
        |
        +---- message/event: check quyền hiện tại
        +---- timer: check token expiry/connection age
        +---- revocation event: close affected connection
        |
        v
Stop outbound sensitive events / close stream
        |
        v
Client renews access credential securely
        |
        v
Reconnect + re-authenticate + resubscribe
        |
        v
Replay events only after checking owner/tenant
~~~

**Refresh token không nên gửi qua STOMP broadcast, SSE data hoặc URL query.** Nếu re-auth trên cùng WebSocket, cả hai phía phải thiết kế protocol thật: verify token mới, xóa quyền cũ, reauthorize tất cả subscriptions, cấm user B thừa hưởng subscription của A và tránh race. Cách **close → refresh → reconnect** thường dễ kiểm soát hơn.

Proxy có thể ngắt connection dù token hợp lệ; cần backoff/jitter khi reconnect để tránh thundering herd. Không dùng ping/pong như thủ thuật gia hạn JWT exp.

## 10. Lab Spring Boot MVC SSE: token tự hết hạn và có thể revoke

Lab sau chạy **Spring Boot 3.3.13 + Java 17 + Spring MVC + Spring Security**, với **opaque token ngắn hạn**:
- POST được bảo vệ bằng HTTP Basic cấp token ngẫu nhiên với TTL 12 giây.
- GET SSE nhận Bearer token, kiểm tra khi mở stream.
- Trước **mỗi tick**, app kiểm tra token một lần nữa.
- Khi hết hạn/revoke, stream **ngừng tick** rồi complete.
- Token sai ở một **GET mới** trả 401.
- Unit test dùng Clock giả để kiểm tra expiry đúng mốc mà không sleep.

**Lab chỉ chạy trên localhost HTTP.** Basic credentials demo nằm trong code; token registry in-memory; bearer authentication trong GET được minh họa ở Controller chứ không dùng OAuth2 Resource Server. Không sao chép security policy này vào production. Ứng dụng thật phải dùng HTTPS, token verification tại security boundary, store có TTL, rate limits, multi-node revocation và resource ownership policy.

### 10.1. Cấu trúc thư mục

~~~text
long-auth-sse/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/longauth/LongAuthSseApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/longauth/TokenRegistryTest.java
~~~

### 10.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>long-auth-sse</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 15m
spring:
  mvc:
    async:
      request-timeout: 60s
~~~

HttpSession timeout 15 phút **không** thay TTL token 12 giây. Demo HTTP Basic được cấu hình stateless; opaque token có kho riêng.

### 10.3. Java source hoàn chỉnh

**src/main/java/com/example/longauth/LongAuthSseApplication.java**:

~~~java
package com.example.longauth;

import java.io.IOException;
import java.security.Principal;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class LongAuthSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongAuthSseApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.POST, "/api/dev-token", "/api/revoke"
                ).authenticated()
                // Lab: Bearer được kiểm tra thủ công trong GET controller.
                .requestMatchers(HttpMethod.GET, "/api/events").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            // Chỉ lab curl. Không copy bỏ qua CSRF sang browser app.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/dev-token", "/api/revoke"
            ))
            .build();
    }
}

record TokenGrant(String accessToken, long expiresInSeconds) {}

@Service
class TokenRegistry {
    static final long TTL_SECONDS = 12;

    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Lease> tokens = new ConcurrentHashMap<>();

    record Lease(String username, Instant expiresAt) {}

    TokenRegistry(Clock clock) {
        this.clock = clock;
    }

    TokenGrant issue(String username) {
        byte[] raw = new byte[32];
        random.nextBytes(raw);
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);
        tokens.put(token, new Lease(
                username, clock.instant().plusSeconds(TTL_SECONDS)
        ));
        return new TokenGrant(token, TTL_SECONDS);
    }

    Optional<Lease> lookup(String token) {
        if (token == null || token.isBlank()) {
            return Optional.empty();
        }
        Lease lease = tokens.get(token);
        if (lease == null) {
            return Optional.empty();
        }
        if (!clock.instant().isBefore(lease.expiresAt())) {
            tokens.remove(token, lease);
            return Optional.empty();
        }
        return Optional.of(lease);
    }

    boolean revoke(String token, String username) {
        Lease lease = tokens.get(token);
        return lease != null
                && lease.username().equals(username)
                && tokens.remove(token, lease);
    }
}

@RestController
class StreamController {
    private final TokenRegistry tokens;
    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(2);

    StreamController(TokenRegistry tokens) {
        this.tokens = tokens;
    }

    @PostMapping("/api/dev-token")
    TokenGrant issue(Principal principal) {
        return tokens.issue(principal.getName());
    }

    @PostMapping("/api/revoke")
    ResponseEntity<Void> revoke(
            Principal principal,
            @RequestHeader("X-Demo-Token") String token
    ) {
        return tokens.revoke(token, principal.getName())
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    @GetMapping(path = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> events(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION,
                           required = false) String authorization
    ) {
        String token = bearerToken(authorization);
        if (tokens.lookup(token).isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .header(HttpHeaders.WWW_AUTHENTICATE, "Bearer")
                    .build();
        }

        SseEmitter emitter = new SseEmitter(60_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<ScheduledFuture<?>> task = new AtomicReference<>();

        Runnable cancel = () -> {
            ScheduledFuture<?> f = task.get();
            if (f != null) {
                f.cancel(false);
            }
        };
        emitter.onCompletion(cancel);
        emitter.onTimeout(cancel);
        emitter.onError(error -> cancel.run());

        ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(() -> {
            // Revalidate TRƯỚC mỗi lần phát dữ liệu.
            if (tokens.lookup(token).isEmpty()) {
                try {
                    emitter.send(SseEmitter.event()
                            .name("auth-expired")
                            .data("renew-and-reconnect"));
                } catch (IOException | IllegalStateException ex) {
                    cancel.run();
                    return;
                }
                cancel.run();
                emitter.complete();
                return;
            }

            int n = counter.incrementAndGet();
            try {
                emitter.send(SseEmitter.event()
                        .id(Integer.toString(n))
                        .name("tick")
                        .data("count=" + n));
            } catch (IOException | IllegalStateException ex) {
                // MVC/container xử lý I/O error trong async response.
                cancel.run();
            }
        }, 1, 1, TimeUnit.SECONDS);

        task.set(future);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noStore())
                .body(emitter);
    }

    private static String bearerToken(String authorization) {
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            return null;
        }
        String value = authorization.substring("Bearer ".length());
        return value.isBlank() ? null : value;
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }
}
~~~

### 10.4. Phân tích code

1. **TokenRegistry** sinh opaque token 32 byte bằng SecureRandom, lưu username và expiresAt trong ConcurrentHashMap. Token được Base64URL encode, không phải JWT.
2. **TTL_SECONDS = 12** là expiry tính từ **lúc cấp token**, không phải từ tick SSE đầu tiên.
3. **lookup** kiểm token tồn tại và còn trước expiresAt; expired record bị xóa khi được lookup.
4. **revoke** chỉ cho username sở hữu token thu hồi nó; endpoint POST phải có Basic authentication.
5. **GET /api/events** cố ý được permitAll tại Spring Security filter, vì Controller kiểm Bearer trực tiếp trong lab để minh họa revalidation. Trong production, nên dùng Resource Server hoặc authentication filter chuẩn tại HTTP boundary.
6. **SseEmitter(60_000L)** có async timeout 60 giây, nhưng token chỉ có 12 giây. Nếu token hết hạn hoặc revoke, server ngừng tick rồi hoàn tất stream.
7. **onCompletion/onTimeout/onError** hủy scheduled task. Khi send gặp IOException do client disconnect, không gọi completeWithError sau IOException; Spring MVC/Servlet async listener xử lý lỗi I/O.
8. **@PreDestroy** dừng scheduler lúc shutdown.

**Giới hạn của lab:** token được cấp nhưng chưa bao giờ lookup có thể chiếm RAM đến khi được dọn; chưa có shared store/eviction/rate limiting, chưa hỗ trợ nhiều replica, TLS hoặc per-tenant sensitive data. Với nhiều SSE clients, Servlet response writes có thể blocking và hai scheduler threads không đủ. Production cần connection limits, bounded queues, event bus và monitoring.

**Race cần nhớ:** nếu token revoke giữa lookup và send, có thể lọt một tick. Kiểm mỗi giây không có nghĩa revoke tức thì; policy nhạy cảm phải đặt check gần publish hơn và xử lý queued events.

### 10.5. Unit test bằng đồng hồ giả, không phải sleep

**src/test/java/com/example/longauth/TokenRegistryTest.java**:

~~~java
package com.example.longauth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class TokenRegistryTest {
    static final class AdjustableClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        @Override
        public Instant instant() {
            return now;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        void advanceSeconds(long seconds) {
            now = now.plusSeconds(seconds);
        }
    }

    @Test
    void expiryAndRevocation() {
        AdjustableClock clock = new AdjustableClock();
        TokenRegistry registry = new TokenRegistry(clock);

        TokenGrant first = registry.issue("alice");
        assertTrue(registry.lookup(first.accessToken()).isPresent());

        assertFalse(registry.revoke(first.accessToken(), "bob"));
        assertTrue(registry.lookup(first.accessToken()).isPresent());

        assertTrue(registry.revoke(first.accessToken(), "alice"));
        assertTrue(registry.lookup(first.accessToken()).isEmpty());

        TokenGrant second = registry.issue("alice");
        assertTrue(registry.lookup(second.accessToken()).isPresent());

        clock.advanceSeconds(12);
        assertTrue(registry.lookup(second.accessToken()).isEmpty());
    }
}
~~~

Test dùng Clock giả để xác minh đúng **ranh giới expiry** và revoke theo username, không Thread.sleep. Nó chưa thay thế integration test cho SSE/network lifecycle.

### 10.6. Build, chạy và quan sát

Cần Java 17+, Maven và port 8080 trống, tại thư mục long-auth-sse:

~~~bash
mvn test
mvn package
java -jar target/long-auth-sse-1.0.0.jar
~~~

**Token sai:**

~~~bash
curl -i -N -H "Authorization: Bearer invalid" http://localhost:8080/api/events
~~~

Kỳ vọng **HTTP 401 Unauthorized**; chưa có stream hợp lệ.

**Linux/macOS Bash với curl và Python 3**:

~~~bash
TOKEN=$(curl -fsS -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
curl -i -N -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/events
~~~

**Windows PowerShell (mỗi lệnh trên một dòng, dùng curl.exe):**

~~~powershell
$grant = curl.exe -s -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | ConvertFrom-Json
curl.exe -i -N -H "Authorization: Bearer $($grant.accessToken)" http://localhost:8080/api/events
~~~

Token thật là chuỗi ngẫu nhiên nên không có stdout token cố định. SSE events có thể xuất hiện tương tự:

~~~text
id:1
event:tick
data:count=1

id:2
event:tick
data:count=2

event:auth-expired
data:renew-and-reconnect
~~~

Đây là **mẫu cấu trúc**, không phải stdout byte-for-byte: số tick phụ thuộc thời gian từ lúc issue đến lúc stream mở, scheduler và buffering. Token hết hạn **12 giây sau POST issue**, không phải sau 12 tick.

**Thử revoke trong khi SSE đang mở (Bash):**

~~~bash
TOKEN=$(curl -fsS -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
curl -sN -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/events &
STREAM_PID=$!
sleep 2
curl -i -u demo:demo-pass -X POST -H "X-Demo-Token: $TOKEN" http://localhost:8080/api/revoke
wait "$STREAM_PID"
~~~

POST revoke thành công trả **HTTP 204 No Content**; lần kiểm token tiếp theo khiến stream dừng tick. Đây không phải bảo đảm latency bằng 0.

**Lưu ý:** Basic credentials và Bearer token có thể lộ trong command history/process list. Chỉ chạy bằng thông tin giả tại localhost, không dùng production credential hoặc chia sẻ token ra bên ngoài.

## 11. Từ lab sang Spring Security production

Một API dùng OAuth2 Resource Server nên xác thực Bearer bằng Spring Security tại **HTTP request đầu**:

~~~java
// Fragment; cần starter OAuth2 Resource Server và issuer/JWK config.
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/events").authenticated()
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Đây là **fragment minh họa**, không thể chép trực tiếp vào lab opaque-token mà không đổi authentication. Sau khi JWT được xác minh ở HTTP GET, stream vẫn cần **expiry/revocation handling** trong quá trình phát events.

### 11.1. Đừng tin SecurityContextHolder chạy ở mọi thread

Spring MVC/Security dùng ThreadLocal trong nhiều ngữ cảnh. SSE scheduled callback có thể chạy trên thread khác; **SecurityContextHolder** trong callback không nhất thiết là Principal của request ban đầu. Lưu identity đã được xác minh một cách an toàn trong connection lease, sau đó tra authorization service hoặc tích hợp context propagation đúng framework. Không tự copy raw bearer vào global ThreadLocal.

### 11.2. Quyền trên từng subscription và event

Nếu user còn token nhưng mất membership tenant, phải dừng phát dữ liệu tenant đó. App nên:
- Kiểm tenant/owner tại SUBSCRIBE và khi publish dữ liệu nhạy cảm.
- Thu hồi subscriptions khi policy version đổi.
- Không coi Last-Event-ID là authentication.
- Kiểm quyền khi replay các sự kiện bị bỏ lỡ.
- Không broadcast private event vào public broker destination.

## 12. Vận hành và bảo vệ hạ tầng

**Connection registry:** đăng ký khi mở, dọn khi timeout/error/close, giới hạn số connections trên user/tenant/IP; tránh giữ SseEmitter/WebSocketSession trong map vô hạn.

**SSE/WS network:** proxy/ingress có idle timeout, header limits, WebSocket Upgrade forwarding và connection lifetime riêng. Dùng heartbeat cho liveness nhưng không nhầm là auth refresh.

**Reconnection:** giới hạn số lần và backoff có jitter để tránh hàng nghìn clients reconnect cùng lúc sau deploy hoặc auth outage.

**Resource quota:** kiểm số active connections, thread pool, queued frames, slow-consumer buffers, scheduler tasks, memory; Servlet writes có thể blocking.

**Token security:** không gửi refresh token trong URL/message, không log JWT/JSESSIONID, dùng HTTPS/WSS, xác minh signature/issuer/audience/exp, không dùng trust-all TLS.

**Multi-node:** truyền logout/revoke/role change đến các node đang giữ connection, dùng shared session/revocation store có TTL và test node failure.

**Observability:** đo token-expiry closes, denied subscriptions, revoke-to-last-event latency, reconnect rate và async exceptions dưới dạng thống kê; không đưa credential vào metric labels.

## 13. Bảng sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| JWT hết hạn nhưng socket vẫn nhận dữ liệu | Chỉ kiểm ở handshake | Lease, revalidate, đóng socket |
| Logout HTTP nhưng WebSocket vẫn mở | Không nối session destroy tới connections | Spring Session integration hoặc revocation bus |
| STOMP heartbeat làm HTTP session kéo dài | SessionRepositoryMessageInterceptor cập nhật hoạt động | Absolute max age và re-auth |
| User mất quyền nhưng topic vẫn gửi | Subscription không được cập nhật | Per-message/per-resource authorization |
| Native WebSocket không gửi custom Bearer header | Browser API hạn chế | Cookie+Origin+CSRF hoặc STOMP CONNECT auth |
| Native EventSource không gửi Bearer header | Không hỗ trợ arbitrary headers | Cookie auth hoặc fetch streaming |
| SSE đã 200 không đổi được 401 | Headers đã phát | Complete stream; 401 ở GET kế tiếp |
| EventSource retry vô hạn với token expired | Client không close() và refresh | Auth state machine, backoff |
| WebSocket code 1006 | Mất kết nối bất thường không nhận close frame | Kiểm proxy/network; không gửi frame 1006 |
| WebSocket code 1008 | Policy violation | Xem token/role/owner policy |
| Revoke node A, stream node B vẫn gửi | Local state không đồng bộ | Shared store/pubsub + lease |
| Nhiều SSE clients làm cạn threads | Servlet writes hoặc scheduler yếu | Caps, executor, slow-consumer policy |
| Last-Event-ID đọc sai tenant | Replay không reauthorize | Check owner/tenant trên từng event |
| Token expiry khác nhau giữa các node | NTP/clock skew/caching | Đồng bộ đồng hồ và policy |
| Refresh thành user B vẫn thấy dữ liệu A | Giữ subscriptions cũ | Disconnect, reauthenticate, resubscribe |

## 14. Bài tập tự đánh giá

**1.** JWT có exp 15 phút, WebSocket mở trước đó vẫn sống 2 giờ. Có chắc framework tự ngắt?  
**Đáp án:** Không. Cần xác minh tích hợp và thực thi expiry trong connection lifecycle.

**2.** STOMP heartbeat chứng minh user còn ROLE_ADMIN không?  
**Đáp án:** Không, chỉ đo liveness.

**3.** Spring Session WebSocket integration có thể làm gì?  
**Đáp án:** Gia hạn last accessed của HTTP session nhờ inbound messages và đóng sockets theo session destroyed events nếu tích hợp/repository event hoạt động đúng.

**4.** User hoạt động đều có thể vượt HttpSession idle timeout không?  
**Đáp án:** Có. Muốn giới hạn tuyệt đối phải có max session/connection age.

**5.** SSE đã trả HTTP 200, token hết hạn. Có đổi status của stream hiện tại thành 401 không?  
**Đáp án:** Không. Dừng data, close stream, xác thực ở request mới.

**6.** Native EventSource hoặc WebSocket API có tự đặt custom Authorization header như fetch không?  
**Đáp án:** Không. Chọn mô hình cookie/session đúng hoặc client/protocol có xử lý token.

**7.** Authenticated user có thể tự SUBSCRIBE topic của tenant khác không?  
**Đáp án:** Không nếu không có quyền, phải check owner/tenant.

**8.** Đóng WebSocket vì policy violation dùng status nào? Có gửi 1006 được không?  
**Đáp án:** 1008 phù hợp; 1006 là reserved và không được gửi trong Close frame.

**9.** Logout trên node A nhưng socket ở B, phải làm gì?  
**Đáp án:** Propagate revocation/session destroy qua shared store/event bus hoặc dùng lease ngắn và kiểm tra.

**10.** Last-Event-ID có thay token được không?  
**Đáp án:** Không. Nó chỉ là cursor và replay phải kiểm quyền.

**11.** Kiểm token mỗi giây bảo đảm revoke tức thì không?  
**Đáp án:** Không, vẫn có scheduler delay, propagation và race check-send.

**12.** Token có exp nhưng connection đã authenticate thì cần làm gì nữa?  
**Đáp án:** Có connection lease, revalidation và dừng private events khi không hợp lệ.

## 15. Checklist review

- [ ] Tách token expiry, HTTP session idle, connection lifetime và authorization.
- [ ] Biết chính xác nơi authenticate: handshake/SSE GET/STOMP CONNECT.
- [ ] Không giả định JWT exp tự đóng socket.
- [ ] Có connection lease hoặc revalidation phù hợp dữ liệu.
- [ ] Recheck SEND, SUBSCRIBE, publish, tenant/owner và replay.
- [ ] Có logout/revocation propagation đa node.
- [ ] Có chính sách max connection age độc lập heartbeat.
- [ ] Cookie auth WebSocket có Origin và CSRF đúng.
- [ ] Không đặt access/refresh token dài hạn vào query/logs.
- [ ] SSE/client refresh và reconnect có close/backoff.
- [ ] Dọn scheduled tasks, connection registry, broker subscriptions.
- [ ] Đo revoke-to-last-event latency và kiểm thử expiry giữa stream.

## 16. Kết luận

**Kết nối mạng còn sống không đồng nghĩa quyền vẫn còn hiệu lực.** Spring Security có thể xác thực HTTP handshake hoặc SSE GET; Spring Session có thể phối hợp vòng đời WebSocket và HTTP session. Nhưng **token exp, logout, revocation, role/tenant thay đổi** cần chính sách riêng trong quãng thời gian sau khi connection đã được mở.

Thiết kế tốt là: **xác thực tại connect → ghi identity/lease đã xác minh → tái kiểm expiry và quyền tại các điểm cần thiết → ngừng dữ liệu/đóng khi policy thất bại → refresh và reconnect an toàn**. Heartbeat giữ kết nối, không giữ quyền.

## Tài liệu tham khảo chính thức

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — STOMP Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — Token-based STOMP Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — STOMP Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Session — WebSocket Integration: https://docs.spring.io/spring-session/reference/web-socket.html
- Spring Framework — MVC Async/SseEmitter: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- RFC 6455 — WebSocket Close Status Codes: https://www.rfc-editor.org/rfc/rfc6455#section-7.4
- MDN — Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
