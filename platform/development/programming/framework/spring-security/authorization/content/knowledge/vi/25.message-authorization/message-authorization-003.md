# MessageMatcherDelegatingAuthorizationManager và thứ tự quy tắc trong Spring Security Messaging

## 1. Mục tiêu: một quy tắc đặt sai vị trí có thể mở sai kênh STOMP

Với Spring WebSocket/STOMP, ứng dụng có thể cho client gửi `SEND /app/chat` để gọi một `@MessageMapping`, và cho client `SUBSCRIBE /topic/public/news` để nhận sự kiện từ message broker. Nhưng client **không được tự gửi SEND vào `/topic/**` hoặc `/queue/**`** để giả mạo thông báo của server. Client cũng không được subscribe vào private topic chỉ vì có quyền đọc một public topic.

Spring Security 6.5 cung cấp `MessageMatcherDelegatingAuthorizationManager`, một `AuthorizationManager<Message<?>>` áp dụng các **cặp điều kiện khớp message → quyết định quyền**. Một đặc điểm quyết định là **thứ tự khai báo**: manager đánh giá các matcher theo thứ tự và chọn delegate của quy tắc khớp đầu tiên. Nó không tự tìm quy tắc có pattern cụ thể nhất, cũng không mặc định kiểm tra tất cả matcher rồi AND các quyền với nhau.

Bài thuộc nhóm **Phân quyền thông điệp** của Spring Security Authorization. Sau khi học, bạn sẽ:

1. Phân biệt STOMP `CONNECT`, `MESSAGE` (thường từ frame `SEND`), `SUBSCRIBE`, `UNSUBSCRIBE`, `DISCONNECT` và message có/không có destination.
2. Dùng đúng `MessageMatcherDelegatingAuthorizationManager.Builder`, `nullDestMatcher`, `simpDestMatchers`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers` và `anyMessage`.
3. Lý giải vì sao **quy tắc cụ thể phải đặt trước quy tắc bao quát** khi chúng có thể cùng khớp.
4. Phân tách quyền **gửi lên application** và quyền **đăng ký nhận từ broker**, chặn giả mạo `/topic/` và `/queue/`.
5. Đặt deny-by-default ở cuối và tránh bị “catch-all permit” nuốt hết các rule sau.
6. Tích hợp `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` vào Spring WebSocket Messaging.
7. Viết test Java 17+ với JUnit 5, dựng message thật bằng `SimpMessageHeaderAccessor`, quan sát `AuthorizationResult` và kiểm thử các trường hợp **cố tình sai thứ tự**.
8. Phân biệt message authorization với authentication WebSocket handshake, CSRF cho STOMP CONNECT, user destinations, quyền object/tenant và logic bảo vệ gửi đi.

**Phạm vi phiên bản:** Spring Security 6.5.x, Spring Framework 6.x, Java 17+. Project ở mục 8 là **unit test của manager thực** — không cần khởi động WebSocket server hay giả lập socket; các test handshake/CSRF/broker thực được đề xuất bổ sung riêng.

## 2. Mô hình inbound và những điểm tin cậy

```text
Browser / STOMP client
   |
   | HTTP handshake (HTTP security, cookie/token/Origin)
   v
WebSocket endpoint
   |
   | CONNECT / SEND / SUBSCRIBE / DISCONNECT frames
   v
clientInboundChannel
   |
   +--> SecurityContextChannelInterceptor / principal
   |
   +--> AuthorizationChannelInterceptor
          |
          v
     MessageMatcherDelegatingAuthorizationManager
          |
          +-- matcher #1 ? -> delegate authorization
          +-- matcher #2 ? -> delegate authorization
          +-- matcher #3 ? -> delegate authorization
          +-- ...
          +-- anyMessage() -> denyAll()
          |
          +-- ALLOW -> application handler or broker routing
          +-- DENY  -> message not forwarded to protected destination
```

Sơ đồ là rút gọn đường **inbound**. Spring Security WebSocket Message Authorization tập trung vào **clientInboundChannel**; đừng suy ra rằng mỗi message **outbound** được kiểm tra cùng một quy tắc. Outbound phải được bảo vệ qua subscription restrictions, broker/user-destination isolation, server-side publication logic và chính sách trên dữ liệu tạo ra.

### 2.1. Ví dụ 4 destination có ngữ nghĩa khác nhau

| Client action | Destination | Mục đích | Policy phù hợp |
| --- | --- | --- | --- |
| `SEND` (MESSAGE) | `/app/chat/send` | Gọi application handler | Authority `CHAT_SEND` |
| `SEND` (MESSAGE) | `/topic/public/news` | **Có thể giả mạo thông báo broker** | **DENY** |
| `SUBSCRIBE` | `/topic/public/news` | Nhận thông báo public trong app | Authority `TOPIC_READ` hoặc policy công khai có chủ đích |
| `SUBSCRIBE` | `/topic/public/admin/alerts` | Nhận thông báo quản trị | Authority `TOPIC_ADMIN` |
| `SUBSCRIBE` | `/topic/private/finance` | Nhận topic nhạy cảm | Authority `TOPIC_PRIVATE` + object/tenant policy nếu cần |
| `SUBSCRIBE` | `/user/queue/inbox` | Nhận queue cá nhân được broker resolve | Authenticated + quyền phù hợp |
| `SUBSCRIBE` | `/queue/inbox-user-x` | Cố truy cập broker destination thô | **DENY** |
| `SEND` (MESSAGE) | `/app/admin/execute` | Lệnh application quản trị | Authority `ADMIN_SEND` |

`/app`, `/topic`, `/queue` và `/user` là **quy ước cấu hình phổ biến** của Spring STOMP broker, không phải chuỗi được framework tự bảo vệ cho mọi ứng dụng. Kiểm tra chính xác prefix mà `MessageBrokerRegistry` của bạn đã khai báo.

## 3. Chữ ký và kiểu dữ liệu trong Spring Security 6.5

Class và interface chính:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.messaging.access.intercept
    .MessageMatcherDelegatingAuthorizationManager;
import org.springframework.messaging.Message;

// Kiểu trả về thực sự của Builder.build():
AuthorizationManager<Message<?>> manager =
    MessageMatcherDelegatingAuthorizationManager.builder()
        .anyMessage().denyAll()
        .build();
```

**Ghi chú:** trong code block trên, Java không cho phép xuống dòng bên trong một câu lệnh import theo cách trình bày minh họa. Import chuẩn, **được dùng trong project chạy được phía dưới**, phải viết trên cùng một dòng:

```java
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
```

Ví dụ phần sau dùng `AuthorizationManager.authorize(Supplier<Authentication>, Message<?>)`, trả về `AuthorizationResult` có `isGranted()`. `check(...)` còn xuất hiện ở Spring Security 6.5 nhưng đã **deprecated**, vì vậy không nên viết API mới dựa vào nó nếu có thể dùng `authorize(...)`.

### 3.1. Cách manager xử lý từng message

Về mặt logic:

```text
for each configured rule in declaration order:
    if rule.matcher.matches(message):
        return rule.authorizationManager.authorize(authentication, messageContext)
return null  // không có matcher nào khớp
```

Đây là **pseudocode**, không phải đoạn trích source thực. Điểm quan trọng là **first matching rule wins**. Nếu một rule khớp nhưng delegate trả DENY, manager **không tự chuyển sang rule kế tiếp** để tìm ALLOW. Nếu không match và không có catch-all, `AuthorizationResult` có thể là `null` (không quyết định), rất nguy hiểm nếu một integration layer diễn giải nhầm abstain. Bởi vậy nên có `anyMessage().denyAll()` ở cuối.

### 3.2. Các builder matchers cần nắm

| Builder | Khớp điều gì? | Khi dùng |
| --- | --- | --- |
| `nullDestMatcher()` | Message không có `simpDestination` (thường CONNECT, UNSUBSCRIBE, DISCONNECT, HEARTBEAT...) | Quy tắc cho control frames không có destination |
| `simpDestMatchers("/app/**")` | Destination pattern, **không giới hạn loại message** | Cẩn trọng; cả SEND/MESSAGE lẫn SUBSCRIBE có thể khớp |
| `simpMessageDestMatchers("/app/**")` | `SimpMessageType.MESSAGE` + destination | Phân quyền client SEND vào application |
| `simpSubscribeDestMatchers("/topic/**")` | `SimpMessageType.SUBSCRIBE` + destination | Phân quyền client đăng ký nhận |
| `simpTypeMatchers(MESSAGE, SUBSCRIBE)` | Loại message bất kể destination | Fallback cho dữ liệu có destination |
| `anyMessage()` | Mọi message | **Luật cuối cùng**, thường DENY |
| `matchers(customMatchers...)` | Matcher tự triển khai | Route có điều kiện phức tạp |
| `hasRole("USER")` | Authority `ROLE_USER` | Tên role không có prefix khi gọi |
| `hasAuthority("TOPIC_READ")` | Authority đúng `TOPIC_READ` | Quyền application chính xác |
| `authenticated()` | Principal đã xác thực theo trust resolver | Handshake/session/message control |
| `permitAll()` / `denyAll()` | Cho phép hoặc từ chối vô điều kiện | Chỉ mở những message **thực sự** được phép |

**Lưu ý:** `simpDestMatchers` không kiểm tra `SimpMessageType`; nếu dùng `simpDestMatchers("/topic/**").permitAll()` chỉ vì muốn cho phép SUBSCRIBE, bạn có thể vô tình cho phép client **MESSAGE/SEND đến broker prefix**.

## 4. Thứ tự quan trọng hơn độ cụ thể của pattern

Đây là lỗi trọng tâm của bài.

### 4.1. Cấu hình không an toàn: broad match ở trước

```java
// PHẢN VÍ DỤ — tuyệt đối không dùng làm cấu hình production.
return MessageMatcherDelegatingAuthorizationManager.builder()
    .simpDestMatchers("/topic/**").permitAll()
    .simpSubscribeDestMatchers("/topic/private/**")
        .hasAuthority("TOPIC_PRIVATE")
    .simpMessageDestMatchers("/topic/**").denyAll()
    .anyMessage().denyAll()
    .build();
```

Với `SUBSCRIBE /topic/private/finance`, rule đầu `/topic/**` đã khớp và trả ALLOW. `TOPIC_PRIVATE` **không bao giờ được kiểm tra**.

Với `MESSAGE /topic/public/news`, chính rule đầu cũng khớp và trả ALLOW. Rule deny message đến broker prefix ở bên dưới **không bao giờ được xét**. Một dòng `permitAll()` ở sai chỗ đã mở hai đường sai.

### 4.2. Cấu hình an toàn: type-specific, hẹp trước rộng, deny cuối

```java
MessageMatcherDelegatingAuthorizationManager.Builder m =
    MessageMatcherDelegatingAuthorizationManager.builder();

m.nullDestMatcher().authenticated();

m.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll();

m.simpSubscribeDestMatchers("/topic/private/**")
    .hasAuthority("TOPIC_PRIVATE");

m.simpSubscribeDestMatchers("/topic/public/admin/**")
    .hasAuthority("TOPIC_ADMIN");

m.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ");

m.simpSubscribeDestMatchers("/user/queue/**")
    .hasAuthority("USER_QUEUE");

m.simpMessageDestMatchers("/app/admin/**")
    .hasAuthority("ADMIN_SEND");

m.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("CHAT_SEND");

m.simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
    .denyAll();
m.anyMessage().denyAll();

return m.build();
```

Đây là **fragment trong factory method**, được cung cấp đầy đủ với imports và test ở mục 8. Cấu hình trên là minh họa policy cho một ứng dụng chat, không phải danh sách các prefix mặc định bắt buộc.

Đặt `/topic/public/admin/**` **trước** `/topic/public/**`: cả hai đều có thể khớp một SUBSCRIBE admin; rule đầu yêu cầu `TOPIC_ADMIN`, nên actor chỉ có `TOPIC_READ` bị chặn. Với `/topic/private/**` và `/topic/public/**`, patterns không overlap trong ví dụ; chúng vẫn được tách riêng để dễ audit.

### 4.3. Không cần “cộng dồn” deny với allow

Bạn có thể đọc cấu hình như bảng ưu tiên:

| Thứ tự | Matcher | Quyết định |
| ---: | --- | --- |
| 1 | Không destination | Authenticated |
| 2 | MESSAGE đến `/topic/**`, `/queue/**` | DenyAll |
| 3 | SUBSCRIBE `/topic/private/**` | TOPIC_PRIVATE |
| 4 | SUBSCRIBE `/topic/public/admin/**` | TOPIC_ADMIN |
| 5 | SUBSCRIBE `/topic/public/**` | TOPIC_READ |
| 6 | SUBSCRIBE `/user/queue/**` | USER_QUEUE |
| 7 | MESSAGE `/app/admin/**` | ADMIN_SEND |
| 8 | MESSAGE `/app/chat/**` | CHAT_SEND |
| 9 | MESSAGE hoặc SUBSCRIBE còn lại | DenyAll |
| 10 | Bất cứ loại message còn lại | DenyAll |

Một `MESSAGE /topic/public/news` dừng tại **hàng 2**. Một `SUBSCRIBE /topic/public/admin/alerts` bỏ qua hàng 2 vì không phải MESSAGE và dừng ở **hàng 4**. Một `SUBSCRIBE /app/chat/send` không khớp hàng 7 vì không phải MESSAGE; bị chặn ở **hàng 9**.

Cấu hình `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` phần nào trùng với `anyMessage().denyAll()`, nhưng hữu ích để thể hiện **mặc định từ chối MESSAGE/SUBSCRIBE không có rule rõ ràng**. Trong app thật có thể giữ cả hai cho tính rõ ràng hoặc chỉ dùng `anyMessage().denyAll()` nếu đã kiểm thử đủ.

### 4.4. `anyMessage().permitAll()` đặt đầu là lỗi nghiêm trọng

```java
// PHẢN VÍ DỤ: mọi matcher phía sau đều bị che.
MessageMatcherDelegatingAuthorizationManager.builder()
    .anyMessage().permitAll()
    .simpMessageDestMatchers("/topic/**").denyAll()
    .build();
```

Một catch-all permit đầu tiên khiến rule deny phía sau trở nên vô hiệu. **Đừng giả định builder tự reorder từ cụ thể tới tổng quát.** Các test minh họa cấu hình nguy hiểm nhằm tái hiện bug, không phải một đề xuất triển khai.

## 5. Phân biệt inbound SEND với outbound delivery

STOMP frame `SEND` của client thường trở thành một `SimpMessageType.MESSAGE` vào `clientInboundChannel`. Client thường được phép SEND đến `/app/**` do application destination prefix định tuyến vào `@MessageMapping`.

Mặt khác:

```text
Server -> convertAndSend("/topic/public/news", payload)
                |
                v
          Broker outbound delivery
                |
                v
Clients đã SUBSCRIBE "/topic/public/news"
```

Client muốn **nhận** từ topic phải SUBSCRIBE; client **không nên SEND trực tiếp** đến broker destination để tránh giả mạo thông báo hệ thống. Do đó:

```java
.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ")
```

Hai matcher **không mâu thuẫn**: một áp MESSAGE và một áp SUBSCRIBE.

### 5.1. User destinations

Spring STOMP hỗ trợ dạng `/user/queue/notifications`: khi client subscribe, `UserDestinationMessageHandler` có thể chuyển nó thành destination thuộc session/user của broker. Không có nghĩa nên mở `SUBSCRIBE /queue/**`: broker destination raw có thể cho phép subscribe vào queue mà user khác nhận.

Gợi ý policy:

```java
.simpSubscribeDestMatchers("/user/queue/**")
    .hasAuthority("USER_QUEUE")
.simpSubscribeDestMatchers("/queue/**").denyAll()
```

Rule deny `/queue/**` thứ hai là optional nếu đã có fallback deny và không có rule rộng khác cho phép; nó diễn đạt ý định bảo vệ rõ ràng. Trong hệ thống multi-tenant, identity/session mapping còn phải xử lý đúng username không duy nhất; không tự suy ra `/user` là đã an toàn cho mọi tenant, mọi broker relay hoặc custom `Principal.getName()`.

### 5.2. `@MessageMapping` không tự xác thực quyền object

Ví dụ:

```java
@MessageMapping("/rooms/{roomId}/post")
public void post(@DestinationVariable long roomId,
                 ChatPayload payload, Principal principal) {
    // Phải xác minh principal có quyền vào roomId/tenant.
}
```

Đây là **fragment**; `ChatPayload`, imports, broker config và service policy phải được định nghĩa. Gate `CHAT_SEND` chỉ cấp quyền chức năng gửi chat, không tự cho phép viết vào mọi phòng. Kiểm tra membership/owner/tenant, quota và trạng thái phòng tại service/repository.

## 6. Cấu hình Spring Security Messaging với `@EnableWebSocketSecurity`

Trong Spring Security 6.5, Java configuration thường khai báo một `AuthorizationManager<Message<?>>` bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
public class WebSocketAuthorizationConfiguration {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
            .simpSubscribeDestMatchers("/topic/private/**")
                .hasAuthority("TOPIC_PRIVATE")
            .simpSubscribeDestMatchers("/topic/public/admin/**")
                .hasAuthority("TOPIC_ADMIN")
            .simpSubscribeDestMatchers("/topic/public/**")
                .hasAuthority("TOPIC_READ")
            .simpSubscribeDestMatchers("/user/queue/**")
                .hasAuthority("USER_QUEUE")
            .simpMessageDestMatchers("/app/admin/**")
                .hasAuthority("ADMIN_SEND")
            .simpMessageDestMatchers("/app/chat/**")
                .hasAuthority("CHAT_SEND")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Đây là **class Java cấu hình có imports**, nhưng vẫn cần một ứng dụng Spring có Spring Messaging/WebSocket broker setup, HTTP authentication và WebSocket endpoint được đăng ký. Không coi cấu hình bean một mình là WebSocket server hoàn chỉnh.

**Chú ý phiên bản:** Java WebSocket message authorization đổi sang `AuthorizationManager` từ Spring Security 5.8. Những dự án cũ dùng `AbstractSecurityWebSocketMessageBrokerConfigurer`, `MessageSecurityMetadataSourceRegistry` hoặc SpEL messaging expressions nên được migration có test so sánh, không sao chép đồng thời hai cơ chế mà chưa rõ order/interceptor.

### 6.1. Handshake, STOMP CONNECT và CSRF

Spring Security WebSocket Messaging nhận principal từ **HTTP handshake** (thường là authentication của phiên HTTP). Với `@EnableWebSocketSecurity`, mặc định yêu cầu **CSRF token hợp lệ trong inbound STOMP CONNECT** nhằm tăng bảo vệ Same Origin; việc này **không được kiểm thử bằng các unit test manager** ở mục 8.

`nullDestMatcher().authenticated()` trong manager chỉ đánh giá authentication cho nhóm message không có destination. Nó **không tự thay thế CSRF CONNECT check**, Origin validation, session authentication, network/TLS hoặc policy trên HTTP handshake endpoint.

Một request/connection có thể bị từ chối **trước khi message authorization manager được gọi**. Khi debug, phân biệt:
- HTTP WebSocket handshake status `401/403`, Origin/CORS.
- STOMP CONNECT bị từ chối vì CSRF token thiếu/sai.
- `SEND` hoặc `SUBSCRIBE` bị từ chối bởi message authorization.
- Broker relay không cho subscribe/route, session đóng hoặc destination không tồn tại.

**Không tắt CSRF/Same Origin chỉ để làm test đơn giản.** Nếu phải hỗ trợ các client cross-origin hoặc SockJS, cần threat model cụ thể, Origin allowlist, token validation và kiểm thử tích hợp.

### 6.2. STOMP CONNECT headers không tự là identity

Một client có thể gửi native STOMP headers như `login`, `passcode`, `X-Tenant` hoặc `X-User`. Đừng tin chúng là danh tính đã xác thực trừ khi có một authentication interceptor đáng tin xác minh và xây dựng `Principal` hợp lệ. Nếu dùng JWT Bearer trong STOMP CONNECT, cần thực hiện authentication tại nơi thích hợp và bảo vệ key/session/expiry.

### 6.3. Không thay thế domain-level authorization

Một custom matcher có thể nhìn destination `/app/rooms/42/post`, nhưng kiểm tra room membership trên DB, owner, quyền theo tenant vẫn phải diễn ra ở service. Với topic nhạy cảm, **SUBSCRIBE** có thể cần custom `.access(AuthorizationManager<MessageAuthorizationContext<?>>)` xét biến route và principal đã xác thực, thay vì chỉ `hasAuthority("TOPIC_PRIVATE")` toàn cục.

Quy tắc thứ tự vẫn vậy: custom matcher cụ thể phải đứng **trước** một broad `simpSubscribeDestMatchers("/topic/**")` hoặc `anyMessage()`; nếu không, delegate custom sẽ không được gọi.

## 7. Thiết kế test: phải tái hiện lỗi ordering, không chỉ test allow bình thường

Bảng ca kiểm thử tối thiểu:

| Message | Actor authorities | Expected | Quy tắc đầu tiên cần khớp |
| --- | --- | --- | --- |
| CONNECT, null dest | Đã xác thực | ALLOW | `nullDestMatcher` |
| CONNECT, null dest | Anonymous | DENY | `nullDestMatcher` |
| SUBSCRIBE `/topic/public/news` | TOPIC_READ | ALLOW | Public subscribe |
| SUBSCRIBE `/topic/public/admin/alerts` | Chỉ TOPIC_READ | DENY | **Admin subscribe trước broad public** |
| SUBSCRIBE `/topic/public/admin/alerts` | TOPIC_ADMIN | ALLOW | Admin subscribe |
| SUBSCRIBE `/topic/private/finance` | Chỉ TOPIC_READ | DENY | Private subscribe |
| SUBSCRIBE `/topic/private/finance` | TOPIC_PRIVATE | ALLOW | Private subscribe |
| MESSAGE `/topic/public/news` | CHAT_SEND hoặc TOPIC_READ | DENY | Broker send deny |
| MESSAGE `/queue/internal` | ADMIN_SEND | DENY | Broker send deny |
| MESSAGE `/app/chat/send` | CHAT_SEND | ALLOW | App chat send |
| SUBSCRIBE `/app/chat/send` | CHAT_SEND | DENY | MESSAGE-only rule không khớp |
| MESSAGE `/app/admin/run` | ADMIN_SEND | ALLOW | Admin send |
| MESSAGE `/app/admin/run` | CHAT_SEND | DENY | Admin send |
| SUBSCRIBE `/user/queue/inbox` | USER_QUEUE | ALLOW | User queue subscribe |
| SUBSCRIBE `/queue/raw` | USER_QUEUE | DENY | Fallback |
| MESSAGE `/app/unmapped` | CHAT_SEND | DENY | Fallback |
| SUBSCRIBE `/topic/unmapped` | TOPIC_READ | DENY | Fallback |
| Cấu hình sai `simpDestMatchers("/topic/**").permitAll()` đầu | Không quyền | **ALLOW sai** | Broad permit nuốt rule riêng |
| Cấu hình sai `anyMessage().permitAll()` đầu | Không quyền | **ALLOW sai** | Catch-all permit nuốt deny |
| Cấu hình không có `anyMessage` | Unmatched message | `null`/abstain có thể xảy ra | Không có rule cuối |

**Không chỉ assert các case thành công.** Một cấu hình hở thường vẫn pass 100% positive test. Test **SEND broker prefix**, **narrow rule sau broad**, **SUBSCRIBE nơi chỉ SEND được phép**, và **catch-all** là những ca có giá trị nhất.

## 8. Project Java 17+ tự chạy test manager thực

Bộ test này tạo `MessageMatcherDelegatingAuthorizationManager` bằng Builder API 6.5, dựng `Message<byte[]>` với `SimpMessageHeaderAccessor.create(type)` rồi gọi `AuthorizationManager.authorize(...)`. Nó không mock quyết định bằng một custom Boolean policy. **Không cần khởi động WebSocket server**, vì ta đang unit-test logic matcher/order; để chứng minh wiring interceptor và STOMP CONNECT CSRF thật, cần integration tests riêng.

### 8.1. Cấu trúc và Gradle

```text
messaging-rule-order/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/MessageRuleOrderTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'messaging-rule-order'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-messaging'
    testImplementation 'org.springframework:spring-messaging'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-security-messaging` chứa `MessageMatcherDelegatingAuthorizationManager`; `spring-messaging` chứa `SimpMessageHeaderAccessor`, `Message` và `MessageBuilder`; `spring-boot-starter-test` cung cấp JUnit 5 và AssertJ. Vì source chỉ nằm dưới `src/test/java`, các dependency dùng `testImplementation`.

### 8.2. Mã Java test đầy đủ

Tạo `src/test/java/demo/MessageRuleOrderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.HEARTBEAT;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;

class MessageRuleOrderTest {

    private static Message<?> msg(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor headers =
            SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            headers.setDestination(destination);
        }

        return MessageBuilder.createMessage(
            new byte[0], headers.getMessageHeaders());
    }

    private static Authentication user(String... authorities) {
        return new UsernamePasswordAuthenticationToken(
            "alice", "test-only",
            AuthorityUtils.createAuthorityList(authorities));
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
            "test-key", "anonymousUser",
            AuthorityUtils.createAuthorityList(
                "ROLE_ANONYMOUS"));
    }

    private static AuthorizationManager<Message<?>> safePolicy() {
        MessageMatcherDelegatingAuthorizationManager.Builder m =
            MessageMatcherDelegatingAuthorizationManager.builder();

        m.nullDestMatcher().authenticated();

        // Client tuyệt đối không được giả mạo broker publications.
        m.simpMessageDestMatchers(
            "/topic/**", "/queue/**").denyAll();

        // SUBSCRIBE: hẹp trước rộng nếu cùng loại và overlap.
        m.simpSubscribeDestMatchers("/topic/private/**")
            .hasAuthority("TOPIC_PRIVATE");

        m.simpSubscribeDestMatchers("/topic/public/admin/**")
            .hasAuthority("TOPIC_ADMIN");

        m.simpSubscribeDestMatchers("/topic/public/**")
            .hasAuthority("TOPIC_READ");

        m.simpSubscribeDestMatchers("/user/queue/**")
            .hasAuthority("USER_QUEUE");

        // SEND/MESSAGE: chỉ vào application destinations đã khai.
        m.simpMessageDestMatchers("/app/admin/**")
            .hasAuthority("ADMIN_SEND");

        m.simpMessageDestMatchers("/app/chat/**")
            .hasAuthority("CHAT_SEND");

        // Mọi MESSAGE/SUBSCRIBE khác đều bị từ chối.
        m.simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll();
        m.anyMessage().denyAll();

        return m.build();
    }

    private static boolean allowed(
            AuthorizationManager<Message<?>> manager,
            Authentication authentication,
            SimpMessageType type, String destination) {

        AuthorizationResult decision =
            manager.authorize(
                () -> authentication, msg(type, destination));

        // Null là no-decision/abstain, KHÔNG được tự chuyển ALLOW.
        return decision != null && decision.isGranted();
    }

    @Test
    void authenticatedConnectIsAllowedByNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), CONNECT, null)).isTrue();
    }

    @Test
    void anonymousConnectIsDeniedByNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), anonymous(), CONNECT, null)).isFalse();
    }

    @Test
    void authenticatedHeartbeatMatchesNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), HEARTBEAT, null)).isTrue();
    }

    @Test
    void authenticatedDisconnectMatchesNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), DISCONNECT, null)).isTrue();
    }

    @Test
    void anonymousUnsubscribeIsDenied() {
        assertThat(allowed(
            safePolicy(), anonymous(), UNSUBSCRIBE, null)).isFalse();
    }

    @Test
    void privateSubscribeRequiresPrivateAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_PRIVATE"),
            SUBSCRIBE, "/topic/private/finance")).isTrue();
    }

    @Test
    void privateSubscribeIsDeniedWithOnlyPublicAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/private/finance")).isFalse();
    }

    @Test
    void privateSubscribeIsDeniedWithSendAuthority() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/topic/private/finance")).isFalse();
    }

    @Test
    void regularPublicSubscribeAllowsTopicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/news")).isTrue();
    }

    @Test
    void publicSubscribeWithoutTopicReadIsDenied() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/topic/public/news")).isFalse();
    }

    @Test
    void adminSubtopicRequiresSpecificAuthorityBeforeBroadRule() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isFalse();
    }

    @Test
    void adminSubtopicAllowsTopicAdminAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isTrue();
    }

    @Test
    void adminAuthorityDoesNotImplicitlyGrantPublicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            SUBSCRIBE, "/topic/public/news")).isFalse();
    }

    @Test
    void userQueueSubscriptionRequiresUserQueueAuthority() {
        assertThat(allowed(
            safePolicy(), user("USER_QUEUE"),
            SUBSCRIBE, "/user/queue/inbox")).isTrue();
    }

    @Test
    void userQueueSubscriptionWithoutAuthorityIsDenied() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/user/queue/inbox")).isFalse();
    }

    @Test
    void rawBrokerQueueCannotBeSubscribedTo() {
        assertThat(allowed(
            safePolicy(), user("USER_QUEUE"),
            SUBSCRIBE, "/queue/inbox-user-x")).isFalse();
    }

    @Test
    void topicSendIsDeniedEvenForChatSender() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/topic/public/news")).isFalse();
    }

    @Test
    void topicSendIsDeniedEvenForTopicAdmin() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            MESSAGE, "/topic/public/admin/alerts")).isFalse();
    }

    @Test
    void queueSendIsDeniedEvenForAdminSender() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            MESSAGE, "/queue/raw")).isFalse();
    }

    @Test
    void appChatSendRequiresChatAuthority() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/chat/send")).isTrue();
    }

    @Test
    void appChatSendIsNotGrantedByTopicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            MESSAGE, "/app/chat/send")).isFalse();
    }

    @Test
    void appAdminSendAllowsOnlyAdminAuthority() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            MESSAGE, "/app/admin/execute")).isTrue();
    }

    @Test
    void chatSenderCannotSendToAdminApplicationDestination() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/admin/execute")).isFalse();
    }

    @Test
    void cannotSubscribeToApplicationSendDestination() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/app/chat/send")).isFalse();
    }

    @Test
    void cannotSubscribeToApplicationAdminDestination() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            SUBSCRIBE, "/app/admin/execute")).isFalse();
    }

    @Test
    void unmatchedApplicationSendIsDeniedByFallback() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/unmapped/operation")).isFalse();
    }

    @Test
    void unmatchedTopicSubscriptionIsDeniedByFallback() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/unlisted/messages")).isFalse();
    }

    @Test
    void broadDestinationPermitBeforePrivateRuleIsAnUnsafeBypass() {
        // CHỈ minh họa lỗi ordering, KHÔNG dùng trong production.
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/topic/**").permitAll()
                .simpSubscribeDestMatchers("/topic/private/**")
                    .hasAuthority("TOPIC_PRIVATE")
                .simpMessageDestMatchers("/topic/**").denyAll()
                .anyMessage().denyAll()
                .build();

        // ALLOW này là KẾT QUẢ SAI VỀ BẢO MẬT.
        assertThat(allowed(
            insecure, user(),
            SUBSCRIBE, "/topic/private/finance")).isTrue();
    }

    @Test
    void broadDestinationPermitAlsoAllowsForgedTopicSend() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/topic/**").permitAll()
                .simpMessageDestMatchers("/topic/**").denyAll()
                .anyMessage().denyAll()
                .build();

        // Một quyền SUBSCRIBE rộng đã làm lộ cả SEND.
        assertThat(allowed(
            insecure, user(),
            MESSAGE, "/topic/public/news")).isTrue();
    }

    @Test
    void catchAllPermitBeforeDenyAlsoBypassesDeny() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .anyMessage().permitAll()
                .simpMessageDestMatchers("/topic/**").denyAll()
                .build();

        assertThat(allowed(
            insecure, user(), MESSAGE, "/topic/system")).isTrue();
    }

    @Test
    void broadSubscribeBeforeNarrowAdminRuleIsAnUnsafeBypass() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/public/**")
                    .hasAuthority("TOPIC_READ")
                .simpSubscribeDestMatchers("/topic/public/admin/**")
                    .hasAuthority("TOPIC_ADMIN")
                .anyMessage().denyAll()
                .build();

        // TOPIC_READ bị chấp nhận ở subtopic dành cho TOPIC_ADMIN.
        assertThat(allowed(
            insecure, user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isTrue();
    }

    @Test
    void simpDestMatchersIsNotRestrictedToSendOrSubscribe() {
        AuthorizationManager<Message<?>> typeAgnostic =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/app/**")
                    .hasAuthority("CHAT_SEND")
                .anyMessage().denyAll()
                .build();

        // Cùng pattern cấp quyền cả MESSAGE lẫn SUBSCRIBE.
        assertThat(allowed(
            typeAgnostic, user("CHAT_SEND"),
            MESSAGE, "/app/chat/send")).isTrue();

        assertThat(allowed(
            typeAgnostic, user("CHAT_SEND"),
            SUBSCRIBE, "/app/chat/send")).isTrue();
    }

    @Test
    void hasRoleAddsRolePrefixButHasAuthorityDoesNot() {
        AuthorizationManager<Message<?>> rolePolicy =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/moderators")
                    .hasRole("MODERATOR")
                .anyMessage().denyAll()
                .build();

        assertThat(allowed(
            rolePolicy, user("ROLE_MODERATOR"),
            SUBSCRIBE, "/topic/moderators")).isTrue();

        assertThat(allowed(
            rolePolicy, user("MODERATOR"),
            SUBSCRIBE, "/topic/moderators")).isFalse();
    }

    @Test
    void missingCatchAllReturnsNoDecisionForUnmatchedMessage() {
        AuthorizationManager<Message<?>> incomplete =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/public/**")
                    .hasAuthority("TOPIC_READ")
                .build();

        AuthorizationResult decision = incomplete.authorize(
            () -> user("TOPIC_READ"),
            msg(MESSAGE, "/app/unknown"));

        assertThat(decision).isNull();
    }
}
```

### 8.3. Tại sao ví dụ này kiểm tra đúng thứ tự?

Bộ test dựng **message thực** với `simpMessageType` và `simpDestination` trong headers, gọi trực tiếp implementation manager thực thay vì fake `boolean`. Phương thức `allowed(...)` nhận `AuthorizationResult` từ `authorize`; mọi kết quả `null` đều được coi là **không được chứng minh ALLOW**.

Các test cố ý dùng **insecure manager** trong phạm vi method test riêng để chứng minh *lỗ hổng có thể xảy ra*. Chúng không bao giờ được đăng ký làm bean bảo vệ application. Một test có kết quả ALLOW trên cấu hình sai là **bằng chứng bug**, không phải xác nhận policy an toàn.

Số lượng test: **33 JUnit 5 `@Test` methods** (theo source minh họa). Hãy chạy Gradle để xác minh compilation và hành vi trên dependency versions thực tế; **không coi các kỳ vọng bên dưới là log đã thực thi**.

### 8.4. Chạy test

```bash
gradle test --tests demo.MessageRuleOrderTest
```

Nếu project đã có Gradle Wrapper:

```bash
# Linux/macOS
./gradlew test --tests demo.MessageRuleOrderTest

# Windows PowerShell/cmd
gradlew.bat test --tests demo.MessageRuleOrderTest
```

**Kết quả kỳ vọng:** các test JUnit thành công và Gradle báo `BUILD SUCCESSFUL` nếu JDK 17+, Gradle và dependency download tương thích. Những test cấu hình sai được thiết kế để PASS khi **xác nhận manager thực sự cho phép nhầm**, nên không được lấy `BUILD SUCCESSFUL` làm bằng chứng cấu hình insecure là an toàn. Báo cáo HTML: `build/reports/tests/test/index.html`.

### 8.5. Đọc test theo 3 tầng

- **Tầng matcher:** message có đúng type và destination không? `simpDestMatchers` không hạn chế type, `simpSubscribeDestMatchers` và `simpMessageDestMatchers` có.
- **Tầng precedence:** matcher nào đứng đầu trong các matcher cùng khớp? Rule hẹp `/topic/public/admin/**` có đứng trước `/topic/public/**` không?
- **Tầng grant:** `hasAuthority`, `hasRole`, `authenticated`, `permitAll`, `denyAll` trả kết quả gì? Với fallback, mọi message chưa được phép rõ ràng phải DENY.

Bộ test **không** kiểm thử `@EnableWebSocketSecurity` wiring, session principal propagation, CSRF STOMP CONNECT, broker relay auth, SockJS, thực thi `@MessageMapping` hoặc outbound delivery. Cần integration test sử dụng STOMP/WebSocket test client để nghiệm thu các lớp đó.

## 9. Test tích hợp trước production

Ngoài unit tests manager, hãy chạy ứng dụng Spring Boot/WebSocket thật với authentication và broker được cấu hình.

### 9.1. Kiểm thử STOMP CONNECT

Tạo các trường hợp:

1. HTTP handshake không có authentication hợp lệ: từ chối ở HTTP layer theo policy.
2. Có HTTP authentication nhưng STOMP CONNECT thiếu CSRF: bị chặn nếu default `@EnableWebSocketSecurity` CSRF đang bật.
3. STOMP CONNECT có CSRF hợp lệ và authenticated principal: tạo session theo policy.
4. CONNECT có native `X-User` giả danh người khác: không thay thế server authenticated Principal.
5. Một client đã CONNECT không được tự thêm quyền `TOPIC_ADMIN` qua STOMP header.
6. SockJS/cross-origin client phải tuân theo Origin/CSRF/trust requirements được cấu hình, không mở bừa.

### 9.2. Kiểm thử SEND, SUBSCRIBE và broker

Sau CONNECT thành công:

- User có `CHAT_SEND` gửi `SEND /app/chat/send`: được định tuyến đến `@MessageMapping` phù hợp.
- User chỉ có `TOPIC_READ` gửi `SEND /app/chat/send`: bị chặn.
- User có `TOPIC_READ` subscribe `/topic/public/news`: nhận thông báo **do server phát**.
- User gửi `SEND /topic/public/news`: bị chặn ngay inbound; subscriber khác không nhận nội dung giả.
- User có `TOPIC_READ` subscribe `/topic/public/admin/alerts`: bị chặn do **precedence hẹp trước rộng**.
- User có `TOPIC_ADMIN` subscribe subtopic admin: được phép theo policy và broker setup.
- User cố subscribe trực tiếp `/queue/**` hoặc `/user/<other>/queue/**`: bị chặn theo matcher và user destination mapping.
- Unmatched destination và type bị `anyMessage().denyAll()` chặn.
- Khi quyền/membership thay đổi trong một session dài, phải có recheck/re-subscribe/revoke policy theo SLA; một SUBSCRIBE ALLOW trước đó không tự biến thành quyền vĩnh viễn.

### 9.3. Kiểm thử tenant và object-level permission

Nếu app có `/topic/tenants/{tenantId}/rooms/{roomId}`, cần kiểm tra actor membership của tenant đã xác thực và quyền trên room **ở thời điểm SUBSCRIBE**; backend publish phải lọc tenant và tránh gửi dữ liệu vào destination chia sẻ quá rộng. Hai tenant có thể cùng room ID=42; không cache decision theo ID 42 đơn lẻ.

Một JWT có `SCOPE_chat:read` là quyền chức năng nhưng **không chứng minh quyền xem mọi tenant/room**. Tách policy ở message manager (đường nào được subscribe/send) và domain service (dữ liệu nào được publish).

## 10. Troubleshooting: đúng matcher nhưng vẫn không đúng quyền

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| User không có `TOPIC_PRIVATE` vẫn subscribe private | Broad matcher `/topic/**` permitAll ở trước | Test rule order; narrow trước broad |
| User gửi SEND vào topic | Dùng `simpDestMatchers` thay cho `simpSubscribeDestMatchers` | Chặn `simpMessageDestMatchers("/topic/**")` |
| Một rule deny không bao giờ có hiệu lực | `anyMessage().permitAll()` hoặc broad allow đứng trước | Đọc từ trên xuống, test first-match |
| Người dùng có đúng authority vẫn bị deny | Một rule deny rộng đứng trước allow mong muốn | Kiểm tra type và order |
| Subscribe `/app/**` bất ngờ được phép | `simpDestMatchers("/app/**")` match cả SUBSCRIBE | Dùng `simpMessageDestMatchers` |
| `ROLE_USER` không khớp | Nhầm `hasRole` với `hasAuthority` prefix | `hasRole("USER")` tự thêm `ROLE_` |
| MESSAGE /topic được nhận dù fallback deny | Rule broad khác khớp trước fallback | Dựng test MESSAGE thật với cùng destination |
| Không có rule nào khớp nhưng ứng dụng xử lý kỳ lạ | Manager trả `null`/abstain | Luôn có `anyMessage().denyAll()` |
| CONNECT bị chặn mặc dù `nullDestMatcher().authenticated()` | CSRF STOMP CONNECT, handshake/Origin, principal không hợp lệ | Kiểm tra filter/interceptor thực tế |
| Có token nhưng Principal không xuất hiện trong message | Handshake auth và messaging context không khớp | Kiểm tra authentication bridge và interceptor order |
| SUBSCRIBE /user được phép nhưng nhận sai dữ liệu | Custom user destination resolution, user name collision hoặc publish sai tenant | Kiểm tra Principal, session ID, destination mapping |
| Broker relay nhận message sai | Broker/relay authorization khác với inbound app policy | Test trực tiếp end-to-end; broker ACL |
| Mọi SUBSCRIBE bị deny sau migration | Legacy SpEL rules không chuyển đúng thành AuthorizationManager | Test migration theo destination/type |
| Publish riêng vẫn xuất dữ liệu nhạy cảm | Chỉ có message gate, thiếu domain policy | Kiểm tra room membership, tenant, payload projection |
| Inconsistent giữa nhiều instance | Session stickiness, broker relay, cache hoặc rule deployment khác | Test đa node, policy versions, message path |
| 403 HTTP dù manager cho phép | Handshake/CSRF/CORS/authentication khác | Phân biệt các tầng security |

## 11. Checklist khi review rules theo thứ tự

- [ ] Có `AuthorizationManager<Message<?>>` bean và `@EnableWebSocketSecurity` theo Spring Security version đang dùng.
- [ ] Dùng đúng `MessageMatcherDelegatingAuthorizationManager.Builder`, các matchers type-specific và cú pháp `hasAuthority/hasRole`.
- [ ] Khi hai pattern overlap, **specific rule đứng trước broad rule**.
- [ ] Không có `anyMessage().permitAll()` hoặc `simpDestMatchers("/**").permitAll()` đầu danh sách.
- [ ] MESSAGE đến broker prefixes `/topic/**`, `/queue/**` bị deny.
- [ ] SUBSCRIBE đến private/admin topics có quyền riêng; không được hưởng nhầm authority public.
- [ ] SEND đến application được cấp `CHAT_SEND`/`ADMIN_SEND` theo đúng destination; SUBSCRIBE đến `/app/**` không được tự hưởng SEND grant.
- [ ] `nullDestMatcher()` và các control frames được cân nhắc cùng CSRF CONNECT/handshake security.
- [ ] Các destination không khớp và loại message không dự kiến có `anyMessage().denyAll()` cuối.
- [ ] `/user/queue/**` dùng per-user semantics an toàn; không mở broker destination raw `/queue/**`.
- [ ] Test cả **MESSAGE** và **SUBSCRIBE** cho cùng destination; không chỉ test destination string.
- [ ] Test broad-first insecure để phát hiện rule bị shadowed trước khi đưa vào production.
- [ ] Kiểm tra token/session/tenant context và quyền object ở service, không chỉ matcher.
- [ ] Test end-to-end STOMP handshake, CONNECT CSRF, SUBSCRIBE, SEND và delivery để xác minh wiring thật.
- [ ] Ghi audit/metrics denial nhưng không lộ raw token, room secrets hoặc payload nhạy cảm.

## 12. Bài tập thực hành

**Bài A — sửa một policy hở.** Cấu hình `simpDestMatchers("/topic/**").permitAll()` trước `simpSubscribeDestMatchers("/topic/private/**").hasAuthority("TOPIC_PRIVATE")`. Viết test chứng minh user thiếu quyền vẫn được subscribe, sau đó sửa bằng type-specific matchers.

**Bài B — admin topic lồng public topic.** Cho `/topic/public/admin/**` đòi `TOPIC_ADMIN`; `/topic/public/**` đòi `TOPIC_READ`. Thử đảo thứ tự và kiểm tra user chỉ TOPIC_READ có thể được phép nhầm khi rule rộng đứng trước.

**Bài C — broker impersonation.** Tạo STOMP client gửi `SEND /topic/system/notifications` và một client khác subscribe topic. Bảo đảm nội dung giả không đi đến subscriber khi `simpMessageDestMatchers("/topic/**").denyAll()` áp dụng.

**Bài D — user destinations.** Tạo hai Principal khác nhau nhưng cùng display name, đăng ký `/user/queue/inbox`; xác minh outbound routing tách session/identity và không nhận message của nhau.

**Bài E — scope và tenant.** Thêm `/topic/tenants/{tenantId}/rooms/{roomId}`; viết custom AuthorizationManager xét principal tenant membership, role trong room, object state. Giữ rule custom trước broad fallback.

**Bài F — CONNECT CSRF.** Dùng STOMP/WebSocket integration test với/không CSRF ở CONNECT. So sánh với unit test `nullDestMatcher().authenticated()` để hiểu hai lớp khác nhau.

**Bài G — no-decision.** Xóa `anyMessage().denyAll()` và thử message không khớp. Xem kết quả `null`/abstain rồi bổ sung fallback explicit deny.

**Bài H — role prefix.** Thử `hasRole("MODERATOR")`, `hasAuthority("MODERATOR")` và `hasAuthority("ROLE_MODERATOR")`, viết ba test độc lập.

## 13. Tổng kết

`MessageMatcherDelegatingAuthorizationManager` cho phép ánh xạ message matcher tới quyết định authorization trong Spring Messaging/STOMP. **Thứ tự là hợp đồng bảo mật**: rule khớp đầu tiên quyết định; framework không tự xếp “pattern cụ thể nhất” lên trước.

Cấu hình an toàn thường gồm:

```java
.nullDestMatcher().authenticated()
.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
.simpSubscribeDestMatchers("/topic/private/**")
    .hasAuthority("TOPIC_PRIVATE")
.simpSubscribeDestMatchers("/topic/public/admin/**")
    .hasAuthority("TOPIC_ADMIN")
.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ")
.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("CHAT_SEND")
.simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
.anyMessage().denyAll();
```

**Phân biệt** client `MESSAGE/SEND` với `SUBSCRIBE` và tránh dùng broad `simpDestMatchers` khi chỉ muốn một type. Chặn client publish trực tiếp vào broker prefix, hạn chế subscribe tới private/user destinations và đặt `anyMessage().denyAll()` cuối cùng. Bài test manager giúp bắt lỗi order, còn an toàn production đòi hỏi thêm handshake authentication, STOMP CONNECT CSRF, user-session routing, broker policy và object/tenant authorization.

## Tài liệu tham khảo

- Spring Security 6.5 — WebSocket Security và rule matcher trong Java config: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 API — `MessageMatcherDelegatingAuthorizationManager`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.html
- Spring Security 6.5 API — `MessageMatcherDelegatingAuthorizationManager.Builder`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security 6.5 API — `Builder.Constraint`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.Constraint.html
- Spring Security 6.5 API — `AuthorizationChannelInterceptor`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/AuthorizationChannelInterceptor.html
- Spring Framework — WebSocket/STOMP Messaging: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html
- Spring Framework — User destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- OWASP — WebSocket Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
