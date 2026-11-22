# Quyền trên kênh cá nhân, topic dùng chung và dữ liệu theo tenant trong Spring Security

## 1. Vì sao đăng nhập WebSocket chưa đủ để bảo vệ dữ liệu?

Một ứng dụng Spring Boot dùng **STOMP over WebSocket** cho thông báo thời gian thực. Người dùng Alice và Bob thuộc tenant `t1`; Carol thuộc tenant `t2`; Mallory có tài khoản nhưng chưa được cấp membership của tenant nào.

Ứng dụng có ba nhóm destination:

- **Kênh cá nhân:** `/user/queue/notifications` để nhận thông báo dành cho một user hoặc session.
- **Topic dùng chung:** `/topic/announcements` để mọi user đăng nhập được xem thông báo công khai trong ứng dụng.
- **Topic theo tenant:** `/topic/tenants/t1/events`, `/topic/tenants/t2/events` để phát các sự kiện chỉ thành viên tenant tương ứng được nhận.

Nếu hệ thống chỉ bảo vệ HTTP handshake `/ws` bằng `authenticated()`, Carol vẫn có thể thử `SUBSCRIBE /topic/tenants/t1/events` và lắng nghe dữ liệu t1. Nếu cho client `SEND /topic/announcements`, họ có thể giả mạo thông báo từ hệ thống mà không đi qua logic nghiệp vụ.

**Nguyên tắc:** cần kiểm tra quyền theo **Authentication + STOMP message type + destination + tenant + action**, không phải chỉ theo URL handshake hoặc prefix. Một client có quyền SUBSCRIBE một topic không tự được quyền SEND vào topic ấy.

### Kết quả học tập

Sau bài này, bạn có thể:
1. Phân biệt `/app`, `/topic`, `/queue`, `/user` với `/ws`.
2. Tách `SimpMessageType.SUBSCRIBE` và `SimpMessageType.MESSAGE`.
3. Sử dụng `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` của Spring Security 6.5.
4. Tách quyền subscribe cá nhân, subscribe broadcast, subscribe theo tenant và publish.
5. Dùng `MessageAuthorizationContext.getVariables()` nhận `{tenant}` rồi xác minh bằng membership server-side.
6. Chặn subscription tới broker queue trực tiếp và client SEND trực tiếp vào broker prefix.
7. Hiểu vì sao Spring Security chỉ bảo vệ `clientInboundChannel` và cần kiểm tra thêm ở server publisher.
8. Thiết kế revocation, multi-session, CSRF CONNECT, origin policy và kiểm thử thực tế.
9. Viết Java 17/Spring Boot 3.5.6 cùng unit/integration tests cho decision matrix.

## 2. STOMP routing và các ranh giới tin cậy

| Prefix | Ví dụ | Chức năng |
|---|---|---|
| `/ws` | `ws://localhost:8080/ws` | HTTP upgrade / WebSocket handshake, không phải địa chỉ STOMP |
| `/app` | `/app/tenants/t1/events` | Client SEND đến server handler `@MessageMapping` |
| `/topic` | `/topic/announcements` | Broker destination cho nhiều subscribers |
| `/topic/tenants/{tenant}` | `/topic/tenants/t1/events` | Topic logic theo tenant, phải có ACL |
| `/queue` | `/queue/notifications-user123` | Broker queue, client không nên truy cập tùy ý |
| `/user` | `/user/queue/notifications` | Logical user destination do Spring resolve theo session |

Luồng Spring Messaging:

```text
Browser → HTTP GET /ws Upgrade → authenticated WebSocket session
                           |
                  STOMP CONNECT + CSRF
                           |
                    clientInboundChannel
                           |
                    Message AuthorizationManager
                       |          |
                    DENY        ALLOW
                                  |
              +-------------------+-------------------+
              |                                       |
     SEND /app/**                           SUBSCRIBE /topic|/user
              |                                       |
      @MessageMapping                            Broker registry
              |
      Trusted business service
              |
     SimpMessagingTemplate
              |
       clientOutboundChannel → subscribed user/session
```

**Spring Security 6.5 chỉ đặt message authorization interceptor trên `clientInboundChannel`**. Nó không tự kiểm tra quyền trên từng message phát ra `clientOutboundChannel`. Vì vậy khi gửi dữ liệu tenant nhạy cảm, server phải xác minh **ai được phép đăng ký** và **đối tượng nào được phép tạo nội dung được gửi**. Khi membership thay đổi giữa một connection dài, cần chủ động revoke subscription hoặc hạn chế thời gian sống.

### 2.1. Authentication của WebSocket đến từ đâu?

Với STOMP over WebSocket trong Servlet stack, một WebSocket session thường kế thừa `Principal` từ HTTP handshake đã được Spring Security xác thực. Khi có session/cookie, server ánh xạ Authentication sang `simpUser` trong Spring Messaging.

Không tin:
- STOMP header `login=admin` hoặc `passcode=...` mặc định như bằng chứng Authentication.
- Trường JSON `sender`, `tenant`, `role` do client tự gửi.
- Phần `t1` của destination như bằng chứng user thuộc t1.
- Query parameter `?user=alice` hoặc `X-Tenant-Id` không được kiểm chứng.

Client chỉ lựa chọn **destination**. Quyền quyết định được lấy từ **trusted principal và canonical server-side membership**.

## 3. Kênh cá nhân /user/queue và nguy cơ nghe trộm queue

Client Alice subscribe:

```text
SUBSCRIBE
id:alice-notifications
destination:/user/queue/notifications
```

Spring `UserDestinationMessageHandler` biến logical user destination thành một broker destination dành riêng cho session (ví dụ `/queue/notifications-user123`). Server có thể gửi:

```java
template.convertAndSendToUser(
    "alice", "/queue/notifications", payload);
```

Điều này **không đồng nghĩa** Alice được phép tự SUBSCRIBE `/queue/notifications-user123` hoặc `/queue/**`. Một kẻ tấn công có thể thử đoán suffix session/queue để nghe dữ liệu của người khác nếu broker/direct subscription được mở quá rộng.

Rule đúng:

```java
messages.simpSubscribeDestMatchers(
    "/user/queue/notifications").authenticated();
```

Đồng thời, catch-all deny mọi `SUBSCRIBE /queue/**` chưa được cấp riêng.

### 3.1. @SendToUser và nhiều sessions

Với:

```java
@MessageMapping("/inbox/ping")
@SendToUser(
    destinations = "/queue/notifications",
    broadcast = false)
public String ping(Principal principal) {
    return "pong:" + principal.getName();
}
```

`broadcast=false` gửi reply cho **session phát yêu cầu**, hữu ích khi một user có nhiều tabs. `SimpMessagingTemplate.convertAndSendToUser(...)` nói chung có thể gửi tới **nhiều sessions của cùng user**. Khi user có thể hoạt động tại nhiều tenant trên nhiều sessions, phải kiểm soát data classification và tenant scope của từng notification; logical user destination không tự bảo vệ payload.

### 3.2. Kịch bản không nên cho phép

| Client action | Kết luận |
|---|---|
| Alice SUBSCRIBE `/user/queue/notifications` | Allow, authenticated |
| Alice SUBSCRIBE `/queue/notifications-user123` | Deny |
| Alice SUBSCRIBE `/user/bob/queue/notifications` | Deny |
| Alice SUBSCRIBE `/user/queue/admin-secrets` | Deny nếu không được khai báo |
| Anonymous SUBSCRIBE `/user/queue/notifications` | Deny |

## 4. Topic chung và quyền SEND/SUBSCRIBE

Một topic dùng chung như `/topic/announcements` thường cho phép người dùng đã đăng nhập **nghe thông báo do hệ thống gửi**, không cho client tự phát thông báo.

```text
SUBSCRIBE /topic/announcements → authenticated user: ALLOW
SEND      /topic/announcements → any client: DENY
```

**Cấu hình sai:**

```java
// PHẢN VÍ DỤ: vô tình mở quyền MESSAGE vào broker prefix.
messages.simpDestMatchers("/topic/**").authenticated();
```

Vì `simpDestMatchers` được dùng cho **MESSAGE** destination, rule trên có thể cho phép user gửi trực tiếp tới topic, tạo khả năng giả mạo nguồn thông báo. Cách đúng:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/announcements").authenticated()
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

Rule hẹp phải đặt trước catch-all deny. Không để hệ thống public data, report riêng hoặc hồ sơ cá nhân cùng đi vào `/topic/announcements` chỉ vì “mọi người đều đã đăng nhập”.

## 5. Topic theo tenant: ranh giới đa khách hàng

Alice và Bob thuộc t1, Carol thuộc t2. Một policy tối thiểu:

| User | SUBSCRIBE t1 | SUBSCRIBE t2 | SEND /app/tenants/t1/events |
|---|---|---|---|
| Alice, member t1, EVENT_PUBLISH | Allow | Deny | Allow |
| Bob, member t1, chỉ đọc | Allow | Deny | Deny |
| Carol, member t2, EVENT_PUBLISH | Deny | Allow | Deny |
| Mallory, không membership | Deny | Deny | Deny |
| Anonymous | Deny | Deny | Deny |

Client gửi:

```text
SUBSCRIBE
destination:/topic/tenants/t2/events
id:tenant-updates
```

`t2` là selector, không phải credential. Server bắt buộc kiểm tra:

```text
isAuthenticated(principal)
AND tenantExists(t2)
AND activeMembership(principal, t2)
AND allowedToSubscribe(principal, "events", t2)
```

Với publish:

```text
isAuthenticated(principal)
AND tenantExists(t2)
AND activeMembership(principal, t2)
AND hasAuthority(principal, "EVENT_PUBLISH")
AND allowedToCreateEvent(principal, resource)
```

**Không làm:**

```java
// PHẢN VÍ DỤ: client tự tuyên bố thuộc tenant.
boolean granted = payload.tenantId().equals(tenantFromPath);
```

Cả payload lẫn path do caller chọn. Phải đối chiếu với DB/membership/ACL do server sở hữu.

### 5.1. Topic tenant chưa đủ cho quyền từng bản ghi

Một member t1 không tự được quyền đọc **mọi hóa đơn, báo cáo lương, hồ sơ sức khỏe hoặc secret** của t1. Nếu một topic chứa event nhạy cảm theo từng record, nên phân quyền theo record ở publisher hoặc chỉ publish một event ID không nhạy cảm rồi để client lấy detail qua HTTP endpoint đã kiểm tra owner/share/tenant.

Thường cần phân biệt `canSubscribeToTenant(t1)` và `canRead(resource:123)`.

## 6. AuthorizationManager<Message<?>> ở Spring Security 6.5

Spring Security 6.5 hỗ trợ `@EnableWebSocketSecurity` với `MessageMatcherDelegatingAuthorizationManager`. Những matcher quan trọng:

| Matcher | Ý nghĩa |
|---|---|
| `simpSubscribeDestMatchers("/topic/...")` | Chỉ SUBSCRIBE tới destination cụ thể |
| `simpDestMatchers("/app/...")` | Chỉ MESSAGE/SEND tới destination cụ thể |
| `simpTypeMatchers(CONNECT,...)` | Kiểm soát các loại STOMP/SIMP frame |
| `nullDestMatcher()` | Nhận messages không có destination |
| `anyMessage().denyAll()` | Từ chối tất cả messages chưa có allow rule |
| `.access(customManager)` | Chính sách tùy chỉnh theo Authentication và `MessageAuthorizationContext<?>` |

Đặc biệt `MessageAuthorizationContext.getVariables()` trả biến đã được destination matcher trích từ pattern, ví dụ `"/topic/tenants/{tenant}/events"` có thể cung cấp `tenant=t1`. Phải kiểm tra value này với canonical membership.

Ví dụ:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/tenants/{tenant}/events")
    .access((auth, ctx) ->
        new AuthorizationDecision(
            acl.canSubscribe(
                auth.get(),
                ctx.getVariables().get("tenant"))));
```

Nếu tenant null/không hợp lệ hoặc auth không được phép, custom manager phải ra **explicit deny**. Không return null/abstain cho điều kiện bảo mật bắt buộc.

### 6.1. Catch-all deny và thứ tự matcher

Một cấu hình an toàn theo thứ tự:

1. CONNECT/DISCONNECT/UNSUBSCRIBE đã xác thực.
2. SUBSCRIBE private logical queue được công nhận.
3. SUBSCRIBE shared announcements.
4. SUBSCRIBE topic tenant sau membership.
5. SEND vào `/app/inbox/ping`.
6. SEND vào `/app/tenants/{tenant}/events` sau quyền publish.
7. `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()`.
8. `anyMessage().denyAll()`.

Không bao giờ dùng `.simpSubscribeDestMatchers("/queue/**").permitAll()` hoặc `.simpDestMatchers("/topic/**").authenticated()` như một lối tắt.

## 7. Dự án Java 17 / Spring Boot 3.5.6 đầy đủ

Ví dụ dùng **STOMP over WebSocket trên Servlet stack**, Java 17, Spring Boot **3.5.6** và Spring Security 6.5.x. Cấu hình gồm HTTP authentication, WebSocket broker prefixes, message authorization, membership service và publisher kiểm tra lại quyền nghiệp vụ.

### 7.1. Cây thư mục

```text
stomp-tenant-security/
  pom.xml
  src/main/java/com/example/messages/
    MessageSecurityApplication.java
    HttpSecurityConfig.java
    WebSocketConfig.java
    TenantPermissions.java
    MessageSecurityConfig.java
    EventPublisher.java
    EventsController.java
  src/test/java/com/example/messages/
    MessageAuthorizationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>stomp-tenant-security</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-messaging</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-websocket` cung cấp WebSocket/STOMP, còn `spring-security-messaging` cung cấp các message interceptors và authorization. Không trộn demo này với raw WebSocket handler không dùng STOMP hoặc với RSocket, vì chúng có cơ chế bảo vệ khác.

### 7.3. MessageSecurityApplication.java

```java
package com.example.messages;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            MessageSecurityApplication.class, args);
    }
}
```

### 7.4. HttpSecurityConfig.java — xác thực trước handshake

```java
package com.example.messages;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {
    @Bean
    SecurityFilterChain httpChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("ROLE_USER","EVENT_PUBLISH")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("ROLE_USER")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-pass"))
                .authorities("ROLE_USER","EVENT_PUBLISH")
                .build(),
            User.withUsername("mallory")
                .password(encoder.encode("mallory-pass"))
                .authorities("ROLE_USER")
                .build());
    }
}
```

Người dùng đăng nhập HTTP trước khi handshake. Browser WebSocket API không cho JavaScript tùy ý đặt `Authorization` header; với browser nên dùng cookie/session đúng SameSite/CSRF/origin hoặc một token handshake architecture đã kiểm chứng, không coi Basic là cách mặc định của browser.

### 7.5. WebSocketConfig.java — broker và user destination prefixes

```java
package com.example.messages;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry broker) {
        broker.enableSimpleBroker("/topic", "/queue");
        broker.setApplicationDestinationPrefixes("/app");
        broker.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry endpoints) {
        endpoints.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:8080");
    }
}
```

`setAllowedOrigins` là một allowlist cho local demo. Khi deploy, thay bằng origins frontend đã tin cậy; không đặt `*` cho WebSocket cookie/session. `/topic` và `/queue` là broker destinations; `/user` là prefix phân giải private destination, **không** nên dùng như broker prefix thông thường.

### 7.6. TenantPermissions.java — nguồn membership phía server

```java
package com.example.messages;

import java.util.Map;
import java.util.Set;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class TenantPermissions {

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice","bob"),
        "t2", Set.of("carol")
    );

    private boolean validUser(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !(auth instanceof AnonymousAuthenticationToken);
    }

    private boolean validTenant(String tenant) {
        return tenant != null
            && tenant.matches("[a-z][a-z0-9-]{0,20}")
            && members.containsKey(tenant);
    }

    public boolean canSubscribe(
            Authentication auth, String tenant) {
        return validUser(auth) && validTenant(tenant)
            && members.get(tenant).contains(auth.getName());
    }

    public boolean canPublish(
            Authentication auth, String tenant) {
        if (!canSubscribe(auth, tenant)) return false;
        for (GrantedAuthority a : auth.getAuthorities()) {
            if ("EVENT_PUBLISH".equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

Dữ liệu RAM chỉ dùng học tập. Production phải map principal ID theo nguồn identity tin cậy, xác minh membership active, roles có scope tenant và consistency với DB. `EVENT_PUBLISH` **không đủ** nếu user không thuộc tenant được chọn.

### 7.7. MessageSecurityConfig.java — nơi tách bốn loại quyền

```java
package com.example.messages;

import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            TenantPermissions permissions) {

        var rules =
            MessageMatcherDelegatingAuthorizationManager.builder();

        rules
            .simpTypeMatchers(CONNECT, DISCONNECT, UNSUBSCRIBE)
                .authenticated()

            .simpSubscribeDestMatchers(
                "/user/queue/notifications")
                .authenticated()

            .simpSubscribeDestMatchers(
                "/topic/announcements")
                .authenticated()

            .simpSubscribeDestMatchers(
                "/topic/tenants/{tenant}/events")
                .access((auth, ctx) ->
                    new AuthorizationDecision(
                        permissions.canSubscribe(
                            auth.get(),
                            ctx.getVariables().get("tenant"))))

            .simpDestMatchers("/app/inbox/ping")
                .authenticated()

            .simpDestMatchers(
                "/app/tenants/{tenant}/events")
                .access((auth, ctx) ->
                    new AuthorizationDecision(
                        permissions.canPublish(
                            auth.get(),
                            ctx.getVariables().get("tenant"))))

            .simpTypeMatchers(MESSAGE, SUBSCRIBE)
                .denyAll()

            .anyMessage().denyAll();

        return rules.build();
    }
}
```

**Điểm cần nhìn:**
- `@EnableWebSocketSecurity` tích hợp message authorization và mặc định CSRF trên CONNECT.
- `SimpMessageType.MESSAGE` cho `SEND /app/**`; `SUBSCRIBE` dùng matcher chuyên biệt.
- Tenant variable được trích từ `MessageAuthorizationContext.getVariables()`; membership kiểm tra ở `TenantPermissions`.
- Chỉ mở `/user/queue/notifications`; không mở direct broker queue.
- Chỉ mở SUBSCRIBE `/topic/announcements`; MESSAGE trực tiếp tới topic bị catch-all chặn.
- `anyMessage().denyAll()` đóng destinations và message types ngoài allowlist.
- `HEARTBEAT` và các message types khác chưa được mở tường minh ở ví dụ. Nếu transport thực cần chúng, cần test và bổ sung rule hẹp, không bật allow toàn phần.

### 7.8. EventPublisher.java — check lại quyền ở service

```java
package com.example.messages;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class EventPublisher {
    public record EventView(
        String tenant, String sender, String body) {}

    private final TenantPermissions permissions;
    private final SimpMessagingTemplate template;

    public EventPublisher(
            TenantPermissions permissions,
            SimpMessagingTemplate template) {
        this.permissions = permissions;
        this.template = template;
    }

    public void publish(
            Authentication auth, String tenant, String text) {

        if (!permissions.canPublish(auth, tenant)) {
            throw new AccessDeniedException(
                "Publish not permitted");
        }
        if (text == null || text.isBlank()
                || text.length() > 1000) {
            throw new IllegalArgumentException(
                "Message length must be 1..1000");
        }

        EventView event =
            new EventView(tenant, auth.getName(), text);

        template.convertAndSend(
            "/topic/tenants/" + tenant + "/events",
            event);
    }
}
```

Service check lần thứ hai vì một method có thể được gọi từ job/HTTP controller khác, không đi qua inbound STOMP security. Payload `sender` và `tenant` do server tạo từ Authentication/tenant đã xác minh; không dùng các trường privileged do client tự khai. Với tenant nhạy cảm, còn phải kiểm tra object-level permission trước outbound.

### 7.9. EventsController.java — SEND /app, reply qua /user

```java
package com.example.messages;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;

@Controller
public class EventsController {
    public record PublishEvent(String body) {}
    private final EventPublisher publisher;

    public EventsController(EventPublisher publisher) {
        this.publisher = publisher;
    }

    @MessageMapping("/tenants/{tenant}/events")
    public void publish(
            @DestinationVariable("tenant") String tenant,
            @Payload PublishEvent payload,
            Principal principal) {

        if (!(principal instanceof Authentication auth)) {
            throw new AccessDeniedException(
                "Missing trusted principal");
        }

        publisher.publish(auth, tenant, payload.body());
    }

    @MessageMapping("/inbox/ping")
    @SendToUser(
        destinations = "/queue/notifications",
        broadcast = false)
    public String ping(Principal principal) {
        return "pong:" + principal.getName();
    }
}
```

Đường STOMP đúng:
- Client Alice: `SEND /app/tenants/t1/events`.
- Server: kiểm tra quyền phát ở message layer và service, rồi `convertAndSend("/topic/tenants/t1/events", event)`.
- Bob đã subscribe t1 nhận event; Carol thuộc t2 không được subscribe t1.
- Client Alice: `SEND /app/inbox/ping`; reply qua `@SendToUser` tới session Alice và client subscribe `/user/queue/notifications`.
- Client **không** được SEND trực tiếp vào `/topic/**`, `/queue/**` hoặc giả destination `/user/bob/...`.

## 8. Kiểm thử message authorization với JUnit 5

Bộ test dùng `MessageBuilder` + `SimpMessageHeaderAccessor` tạo một `Message<byte[]>` có `simpMessageType` và `simpDestination`. Nó gọi `AuthorizationManager.authorize(...)` và kiểm tra `AuthorizationResult.isGranted()`.

**Đây là kiểm thử policy trong Spring application context, chưa phải WebSocket E2E**. CONNECT CSRF, origin handshake và thực tế UserDestinationMessageHandler chuyển queue cần bộ E2E riêng ở phần 9.

**`src/test/java/com/example/messages/MessageAuthorizationTest.java`**

```java
package com.example.messages;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest
class MessageAuthorizationTest {
    @Autowired AuthorizationManager<Message<?>> manager;
    @Autowired TenantPermissions permissions;

    private static Authentication user(
            String name, String... authorities) {
        List<GrantedAuthority> granted =
            Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .map(a -> (GrantedAuthority) a)
                .toList();

        return UsernamePasswordAuthenticationToken.authenticated(
            name, "N/A", granted);
    }

    private static Authentication alice() {
        return user("alice", "ROLE_USER", "EVENT_PUBLISH");
    }

    private static Authentication bob() {
        return user("bob", "ROLE_USER");
    }

    private static Authentication carol() {
        return user("carol", "ROLE_USER", "EVENT_PUBLISH");
    }

    private static Authentication mallory() {
        return user("mallory", "ROLE_USER");
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
            "key", "anonymous",
            List.of(new SimpleGrantedAuthority(
                "ROLE_ANONYMOUS")));
    }

    private static Message<byte[]> frame(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor h =
            SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            h.setDestination(destination);
        }
        h.setLeaveMutable(true);
        return MessageBuilder.createMessage(
            new byte[0], h.getMessageHeaders());
    }

    private void expect(
            Authentication auth,
            SimpMessageType type,
            String destination,
            boolean granted) {
        AuthorizationResult decision = manager.authorize(
            () -> auth, frame(type, destination));

        assertNotNull(decision,
            "Every frame needs explicit authorization");
        assertEquals(granted, decision.isGranted(),
            type + " " + destination);
    }

    @Test
    void authenticatedConnectCanPassManager() {
        expect(alice(), SimpMessageType.CONNECT, null, true);
    }

    @Test
    void anonymousConnectDenied() {
        expect(anonymous(), SimpMessageType.CONNECT, null, false);
    }

    @Test
    void disconnectAuthenticatedAllowed() {
        expect(alice(), SimpMessageType.DISCONNECT, null, true);
    }

    @Test
    void unsubscribeAuthenticatedAllowed() {
        expect(alice(), SimpMessageType.UNSUBSCRIBE, null, true);
    }

    @Test
    void personalQueueAllowedForAlice() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", true);
    }

    @Test
    void personalQueueAllowedForCarol() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", true);
    }

    @Test
    void anonymousPersonalQueueDenied() {
        expect(anonymous(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", false);
    }

    @Test
    void directBrokerQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/queue/notifications-user123", false);
    }

    @Test
    void otherUsersLogicalQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/bob/queue/notifications", false);
    }

    @Test
    void unlistedPrivateQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/queue/admin", false);
    }

    @Test
    void commonAnnouncementsSubscribeAllowed() {
        expect(bob(), SimpMessageType.SUBSCRIBE,
            "/topic/announcements", true);
    }

    @Test
    void sendingToCommonTopicDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/topic/announcements", false);
    }

    @Test
    void aliceCanSubscribeOwnTenant() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", true);
    }

    @Test
    void bobCanSubscribeOwnTenant() {
        expect(bob(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", true);
    }

    @Test
    void carolCannotSubscribeT1() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void carolCanSubscribeT2() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t2/events", true);
    }

    @Test
    void aliceCannotSubscribeT2() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t2/events", false);
    }

    @Test
    void loggedInNonMemberDenied() {
        expect(mallory(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void unknownTenantDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t9/events", false);
    }

    @Test
    void malformedTenantDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/_invalid/events", false);
    }

    @Test
    void aliceCanPublishToT1ViaApp() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", true);
    }

    @Test
    void bobCannotPublishWithoutAuthority() {
        expect(bob(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void carolCanPublishToT2ViaApp() {
        expect(carol(), SimpMessageType.MESSAGE,
            "/app/tenants/t2/events", true);
    }

    @Test
    void aliceCannotPublishToOtherTenant() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/tenants/t2/events", false);
    }

    @Test
    void carolCannotPublishToT1() {
        expect(carol(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void clientSendToTenantBrokerTopicDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void clientSendToBrokerQueueDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/queue/notifications", false);
    }

    @Test
    void privatePingViaAppAllowed() {
        expect(bob(), SimpMessageType.MESSAGE,
            "/app/inbox/ping", true);
    }

    @Test
    void unlistedApplicationMessageDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/admin/reset", false);
    }

    @Test
    void unlistedTopicDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/secret", false);
    }

    @Test
    void subscribeToApplicationRouteDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void messageWithoutDestinationDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            null, false);
    }

    @Test
    void subscribeWithoutDestinationDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            null, false);
    }

    @Test
    void unlistedMessageTypeDenied() {
        expect(alice(), SimpMessageType.OTHER,
            null, false);
    }

    @Test
    void publisherUsesVerifiedSenderAndTenant() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        publisher.publish(alice(), "t1", "hello");

        verify(template).convertAndSend(
            eq("/topic/tenants/t1/events"),
            eq(new EventPublisher.EventView(
                "t1", "alice", "hello")));
    }

    @Test
    void publisherDeniesCrossTenantBeforeSending() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(
            org.springframework.security.access.AccessDeniedException.class,
            () -> publisher.publish(alice(), "t2", "blocked"));
        verifyNoInteractions(template);
    }

    @Test
    void publisherDeniesReadOnlyMember() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(
            org.springframework.security.access.AccessDeniedException.class,
            () -> publisher.publish(bob(), "t1", "blocked"));
        verifyNoInteractions(template);
    }

    @Test
    void publisherRejectsEmptyBody() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(IllegalArgumentException.class,
            () -> publisher.publish(alice(), "t1", " "));
        verifyNoInteractions(template);
    }

    @Test
    void publisherRejectsOversizeBody() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(IllegalArgumentException.class,
            () -> publisher.publish(
                alice(), "t1", "X".repeat(1001)));
        verifyNoInteractions(template);
    }
}
```

### 8.1. Cách chạy

```bash
mvn test
```

**Kết quả mong đợi:** các tests cho SUBSCRIBE cá nhân, topic chung, tenant và SEND vào app, broker bypass, non-member, deny-by-default, publisher defense-in-depth đều pass. Đây là **bộ mã được soạn và kiểm tra nội dung, không phải log Maven đã thực thi**. Muốn khẳng định độ tương thích chính xác với dependency/build environment, cần chạy Maven trên project.

Các tests này gọi authorization bean trực tiếp. Chúng **không** mở WebSocket thật, không gửi STOMP CONNECT kèm CSRF và không kiểm thử broker delivery. Cần E2E để xác nhận interceptor đang được wiring trên network và không có đường bypass.

## 9. Ma trận kiểm thử STOMP end-to-end

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `WebSocketStompClient` hoặc STOMP browser client với login session/CSRF thật. Một kịch bản tốt cần ít nhất:

| Scenario | Hành động | Kết quả phải xác minh |
|---|---|---|
| CONNECT hợp lệ | Alice đã login, STOMP CSRF token hợp lệ | CONNECTED |
| CONNECT thiếu CSRF | Alice đã login nhưng không có token | Bị từ chối |
| Origin không tin cậy | Handshake từ origin lạ | Bị từ chối |
| Private subscribe | Alice SUBSCRIBE /user/queue/notifications | Alice nhận reply |
| Private isolation | Bob subscribe kênh riêng của mình | Không nhận reply của Alice |
| Direct queue | Alice SUBSCRIBE /queue/notifications-user123 | Không được đăng ký |
| Shared topic | Bob SUBSCRIBE /topic/announcements | Được nghe server announcement |
| Shared topic spoof | Alice SEND /topic/announcements | Không có message giả phát ra |
| T1 subscribe | Alice/Bob SUBSCRIBE /topic/tenants/t1/events | Accepted |
| Cross-tenant subscribe | Carol SUBSCRIBE /topic/tenants/t1/events | Rejected |
| T2 subscribe | Carol SUBSCRIBE /topic/tenants/t2/events | Accepted |
| T1 publish | Alice SEND /app/tenants/t1/events | Bob nhận t1 event |
| T1 read-only publish | Bob SEND /app/tenants/t1/events | Rejected |
| Cross-tenant publish | Alice SEND /app/tenants/t2/events | Rejected |
| Private session reply | Alice có hai tabs, ping từ tab A | Chỉ tab A nhận nếu broadcast=false |
| Membership revoked | Alice bị loại t1 khi socket còn mở | Subscription được revoke/disconnect trước event nhạy cảm kế tiếp |

**Không nhầm HTTP 403 với lỗi STOMP:** sau khi connection đã upgrade, lỗi authorization có thể tạo STOMP `ERROR`, đóng socket hoặc báo frame failure. Test xác nhận **không có subscription active, không nhận dữ liệu và không có unauthorized publish**, không chỉ đòi một HTTP status.

### 9.1. STOMP frames ví dụ

```text
SUBSCRIBE
id:alice-t1
destination:/topic/tenants/t1/events
```

Alice có quyền publish:

```text
SEND
destination:/app/tenants/t1/events
content-type:application/json

{"body":"Invoice created"}
```

Hai ví dụ trên minh họa nội dung frame mà client STOMP tạo. Trên wire, STOMP cần ký tự NULL kết thúc frame; thư viện STOMP client tự xử lý. Đích client **không phải** `/topic/tenants/t1/events` khi gửi lệnh publish; đó là đích do server publish sau khi kiểm tra quyền.

## 10. CONNECT CSRF và cross-site WebSocket hijacking

Trình duyệt không áp Same Origin Policy cho WebSocket giống fetch/XHR. Spring Security 6.5 yêu cầu CSRF token ở **STOMP CONNECT** khi dùng `@EnableWebSocketSecurity`; WebSocket endpoint cũng nên hạn chế allowed origins.

Client browser cần:
1. Đăng nhập với session/cookie hợp lệ.
2. Lấy CSRF token từ cùng origin qua endpoint/config được bảo vệ.
3. Khởi tạo WebSocket tới `/ws` cùng session.
4. Đưa CSRF token vào **STOMP CONNECT headers** theo tên header token của Spring.
5. Chỉ SUBSCRIBE sau khi nhận CONNECTED.

Nếu dùng SockJS, HTTP fallback transports có cơ chế riêng; đừng disable CSRF trên **toàn website** chỉ để SockJS hoạt động. Với JWT ở STOMP CONNECT, muốn dùng phải viết/kiểm thử một `ChannelInterceptor` xác minh token và đặt Authentication đúng thứ tự; Spring không mặc định tin `Authorization`/`login` header trong STOMP như một proof of identity.

## 11. Multi-tenant trong production

### 11.1. Subscription authorization được quyết định theo thời gian

Một subscription có thể sống nhiều giờ. Nếu user bị revoke membership hoặc role trong lúc kết nối, kiểm tra chỉ ở thời điểm SUBSCRIBE **không tự động chặn mọi outbound event về sau**. Thiết kế thêm:
- Force unsubscribe/disconnect khi revoke.
- Reconnect có hạn và re-auth theo TTL.
- Policy version và membership-cache invalidation.
- Per-recipient filtering với dữ liệu rất nhạy cảm.
- Audit principal, tenant, subscription ID và thời gian revoke.

### 11.2. Topic per tenant không thay object-level ACL

Một member t1 có thể đọc tenant-level activity nhưng không được xem report lương trong t1. Không gửi secrets, full PII hay dữ liệu record-level quá rộng vào broadcast topic tenant. Có thể gửi một ID/notification summary, rồi client lấy detail qua HTTP API có kiểm tra record-level permissions.

### 11.3. Multi-node và broker relay

Demo dùng `enableSimpleBroker("/topic","/queue")`. Production có thể dùng RabbitMQ/ActiveMQ relay. Khi đó:
- Bảo vệ network/broker TCP, không để client kết nối thẳng vào broker và bỏ qua Spring security.
- Phân quyền broker-side, rotate credentials và hạn chế wildcard permissions.
- Quản lý auto-delete queues, stale subscriptions, user destinations trên nhiều nodes.
- Xem `userDestinationBroadcast`/unresolved user destinations nếu nhiều Spring nodes.
- Kiểm thử duplicate delivery, message ordering, reconnect, rate limit và revoke.

### 11.4. Không tin raw path/string

Đừng kiểm tra tenant bằng `startsWith("/topic/tenants/t1")` vì có thể match `t10`. Dùng destination matcher có capture variables và validate tenant ID theo policy. Path encoding, separators, custom broker naming và proxy rewrites phải được kiểm thử khi sử dụng thực tế.

### 11.5. Chống flood và data exfiltration

Authorization không đủ chống việc một user được phép gửi hàng triệu messages:
- Rate limit theo principal/tenant/session.
- Giới hạn payload size, attachment/media restrictions.
- Timeout, backpressure, queue retention và delivery quotas.
- Logging/metrics không chứa raw secrets.
- Anomaly detection cho SUBSCRIBE thay đổi tenant liên tục hoặc SEND tới destinations lạ.

## 12. Sai lầm phổ biến

| Sai lầm | Rủi ro | Sửa |
|---|---|---|
| Chỉ xác thực `/ws` | Cross-tenant SUBSCRIBE | Message authorization |
| Mở `simpDestMatchers("/topic/**")` | Client có thể publish trực tiếp broker | SEND chỉ tới `/app/**` |
| Mở `/queue/**` cho SUBSCRIBE | Có thể nghe queue riêng của người khác | Chỉ logical `/user/queue/...` |
| Coi `/user/queue` là bằng chứng quyền trên record | Gửi quá nhiều dữ liệu cá nhân | Check payload/tenant/owner |
| Tin `tenantId` từ JSON | Client tự nâng scope | Canonical membership |
| Bỏ role publish | Read-only user có thể ghi | Tách canSubscribe/canPublish |
| Tin `sender` từ client | Impersonation | Trusted Principal |
| Dùng role ADMIN để bỏ qua tenant | Cross-tenant escalation | Admin binding có scope |
| Cho `SUBSCRIBE /topic/**` bất kể tenant | Tenant leak | Dynamic tenant matcher |
| Chỉ check ở STOMP inbound | Job/HTTP gọi publisher bypass | Service guard |
| Cho rằng outbound security tự kiểm tra mỗi tin | Stale subscription tiếp tục nhận | Revoke/recipient filtering |
| Tắt CSRF STOMP CONNECT | Cross-site WebSocket hijacking | STOMP CSRF token |
| Cho Origin `*` với cookie/session | Cross-origin access | Trusted origin allowlist |
| Coi STOMP `login` là authentication | Spoof identity | HTTP-authenticated Principal |
| Chỉ viết test handshake | Bỏ lỗ hổng message-level | Matrix frame/destination/user |
| Coi denied STOMP như HTTP 403 | Sai tầng protocol | ERROR/close/no delivery tests |
| Không quản lý broker TCP direct | Bypass Spring security | Firewall và broker ACL |

## 13. Checklist phát hành

- [ ] Bảo vệ HTTP WebSocket handshake bằng Spring Security.
- [ ] Bật `@EnableWebSocketSecurity` và message `AuthorizationManager`.
- [ ] Phân biệt `MESSAGE` và `SUBSCRIBE`.
- [ ] SUBSCRIBE kênh cá nhân chỉ được phép ở logical `/user/queue/**` đã định nghĩa.
- [ ] Không mở direct broker `/queue/**`.
- [ ] Topic dùng chung cho SUBSCRIBE, không cho client SEND trực tiếp.
- [ ] Topic tenant dùng destination variables và canonical membership.
- [ ] Quyền publish mạnh hơn quyền subscribe khi nghiệp vụ yêu cầu.
- [ ] Sender/tenant authoritative do server tạo, không lấy từ body.
- [ ] Business publisher có guard thứ hai.
- [ ] `anyMessage().denyAll()` ở cuối và test unlisted destinations.
- [ ] STOMP CONNECT được bảo vệ CSRF, origins giới hạn.
- [ ] WebSocket identity map từ HTTP session hoặc token interceptor đáng tin.
- [ ] Có chiến lược revoke membership giữa subscription dài.
- [ ] Không đưa record-secret vào tenant broadcast topic khi user không có object ACL.
- [ ] Có E2E test kiểm tra no-delivery và multi-session isolation.
- [ ] External broker network, queues và credentials được bảo vệ.
- [ ] Có audit, rate limits, payload size limits và observability.

## 14. Câu hỏi tự kiểm tra

**1.** Alice có quyền đọc topic t1, có được SEND trực tiếp tới `/topic/tenants/t1/events` không?

**Trả lời:** Không. Client phải SEND tới `/app/tenants/t1/events`, đi qua message authorization và business handler.

**2.** Tại sao không cho Alice đăng ký `/queue/notifications-user123`?

**Trả lời:** Đây là broker destination có thể thuộc session khác. Alice chỉ nên đăng ký logical `/user/queue/notifications`, để Spring giải quyết theo session.

**3.** Carol là authenticated user t2, có subscribe t1 được không?

**Trả lời:** Không. Cần xác nhận membership t1 từ server, không chỉ authenticated.

**4.** Spring Security tự recheck mọi message outbound sau khi user bị revoke không?

**Trả lời:** Không. Cơ chế message authorization chuẩn tập trung inbound; cần revoke subscription/reconnect hoặc filtering ở outbound publisher.

**5.** `@SendToUser(broadcast=false)` giải quyết điều gì?

**Trả lời:** Gửi reply cho session phát yêu cầu thay vì mọi sessions của cùng user; không tự cấp permission trên tài liệu.

**6.** Bảo vệ WebSocket CONNECT có cần CSRF không?

**Trả lời:** Trong mô hình Spring Security 6.5 với `@EnableWebSocketSecurity`, CONNECT yêu cầu CSRF token để giảm cross-site WebSocket hijacking; còn cần allowed origins.

## 15. Tài liệu chính thức

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, message matcher rules, SEND vs SUBSCRIBE, CSRF CONNECT, outbound limitations.
- [Spring Security 6.5 — MessageMatcherDelegatingAuthorizationManager.Builder API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpSubscribeDestMatchers`, `simpDestMatchers`, `anyMessage`.
- [Spring Security 6.5 — MessageAuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html): `getVariables()`.
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/AuthorizationManager.html): `authorize(...)`, `AuthorizationResult`.
- [Spring Framework 6.2 — User Destinations](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/user-destination.html): logical `/user`, `UserDestinationMessageHandler`, `@SendToUser(broadcast=false)`.
- [Spring Framework 6.2 — Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html): HTTP Principal và STOMP user header.
- [Spring Framework 6.2 — Authorization](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authorization.html): message interceptor và Spring Security.
- [Spring Framework 6.2 — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html): inbound/broker/outbound channel.

**Ghi nhớ:** `/user/queue/**` là logical private destination được Spring resolve theo user/session, không phải lý do mở broker `/queue/**`. `/topic/announcements` là topic dùng chung có quyền **SUBSCRIBE**, không có nghĩa client được **SEND** trực tiếp. `/topic/tenants/{tenant}/events` phải kiểm tra Authentication, membership và quyền theo tenant từ source of truth cho **mỗi SUBSCRIBE/SEND**. Spring Security 6.5 bảo vệ `clientInboundChannel`; phải kết hợp business publisher guard, object-level ACL và revoke subscription để tránh rò dữ liệu khi quyền thay đổi.