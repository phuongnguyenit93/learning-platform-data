# simpDestMatchers, simpSubscribeDestMatchers và simpTypeMatchers trong Spring Security Messaging

> **Module:** Spring Security – authorization → **Phân quyền thông điệp**. Bài học giải thích chính xác cách Spring Security 6.x phân quyền các message STOMP/WebSocket đi vào ứng dụng: `simpDestMatchers` khớp **destination**, `simpSubscribeDestMatchers` khớp **SUBSCRIBE + destination**, `simpTypeMatchers` khớp **SimpMessageType**. Trọng tâm là thứ tự matchers, chặn giả mạo thông điệp vào broker destination (`/topic/**`, `/queue/**`), hạn chế SUBSCRIBE, bảo vệ user destination và kiểm thử rule bằng `AuthorizationManager<Message<?>>`. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x và JUnit 5.

## 1. Vì sao HTTP authorization chưa đủ cho WebSocket/STOMP?

Trong REST, server thường kiểm quyền với một HTTP request:

~~~text
GET  /api/chat/messages
POST /api/chat/send
~~~

Nhưng với WebSocket/STOMP, HTTP request ban đầu chủ yếu mở kết nối. Sau khi nâng cấp kết nối, một client có thể gửi **nhiều frame** khác nhau qua cùng socket:

~~~text
CONNECT
SUBSCRIBE destination:/topic/public-updates
SEND      destination:/app/chat.send
SEND      destination:/topic/system/announcements
SUBSCRIBE destination:/queue/private-all
DISCONNECT
~~~

Nếu chỉ kiểm người dùng có được mở WebSocket hay không, bạn **chưa** bảo vệ các thao tác cụ thể trên kênh ấy.

Hai loại rủi ro:

1. **Giả mạo người phát thông điệp:** Client tự `SEND` đến `/topic/system/announcements`, thay vì server mới được publish thông báo hệ thống.
2. **Đọc lén theo subscription:** Client tự `SUBSCRIBE` đến một topic/queue khác hoặc một queue tổng hợp nhạy cảm.

Vì vậy Spring Security hỗ trợ authorization trên **inbound messages** bằng `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>`.

### 1.1. Phân biệt frame STOMP và SimpMessageType

| STOMP frame từ client | SimpMessageType thông dụng | Destination? | Ý nghĩa |
| --- | --- | --- | --- |
| `CONNECT` | `CONNECT` | Thường không | Mở phiên STOMP |
| `SEND` | `MESSAGE` | Có | Yêu cầu gửi thông điệp |
| `SUBSCRIBE` | `SUBSCRIBE` | Có | Đăng ký nhận một luồng thông điệp |
| `UNSUBSCRIBE` | `UNSUBSCRIBE` | Thường không | Hủy một subscription ID |
| `DISCONNECT` | `DISCONNECT` | Thường không | Kết thúc phiên |
| Heartbeat/frames nội bộ | `HEARTBEAT`/loại khác | Thường không | Điều phối kết nối |

**Cẩn thận tên gọi:** Client dùng STOMP command `SEND`, nhưng Spring Messaging thường biểu diễn inbound command đó bằng `SimpMessageType.MESSAGE`. Do đó `simpTypeMatchers(MESSAGE)` dùng để bắt các yêu cầu gửi message từ client, **không** phải chỉ là frame `MESSAGE` server gửi tới client.

Trong Spring MVC annotated messaging, application prefix như `/app` thường dẫn tới `@MessageMapping` handlers; broker prefix như `/topic`/`/queue` được broker phục vụ.

## 2. Ba matcher trong đề bài: khác nhau ở điều kiện nào?

| Matcher | Kiểm tra | Ví dụ khớp | Ví dụ **không** khớp |
| --- | --- | --- | --- |
| `simpDestMatchers("/app/**")` | Destination khớp pattern, **không phụ thuộc SimpMessageType** | MESSAGE hoặc SUBSCRIBE có destination `/app/chat.send` | CONNECT không có destination |
| `simpSubscribeDestMatchers("/topic/**")` | Type = SUBSCRIBE **và** destination khớp | SUBSCRIBE `/topic/news` | MESSAGE `/topic/news` |
| `simpTypeMatchers(SUBSCRIBE)` | Type = SUBSCRIBE, **bất kể destination** | Mọi SUBSCRIBE kể cả path lạ | MESSAGE, CONNECT |
| `simpMessageDestMatchers("/app/**")` | Type = MESSAGE **và** destination khớp | Client SEND đến `/app/chat.send` | SUBSCRIBE vào `/app/chat.send` |
| `nullDestMatcher()` | Không có destination | CONNECT, UNSUBSCRIBE, DISCONNECT thường gặp | MESSAGE có destination hợp lệ |
| `anyMessage()` | Tất cả messages chưa được rule trước bắt | Catch-all | Không có ngoại lệ |

`simpMessageDestMatchers` là biến thể quan trọng dù đề bài nhắc ba matcher kia: nó thường an toàn hơn `simpDestMatchers` khi mục tiêu là cấp quyền **chỉ để gửi** vào application endpoint.

### 2.1. `simpDestMatchers` không mặc định nghĩa là SEND

~~~java
messages.simpDestMatchers("/app/admin/**")
        .hasRole("ADMIN");
~~~

Rule này yêu cầu ROLE_ADMIN cho message có destination tương ứng, nhưng **không giới hạn loại message**. Nếu không có rule riêng đứng trước, một SUBSCRIBE vào `/app/admin/any` cũng có thể được cấp quyền cho admin.

Điều này không đồng nghĩa broker sẽ trả dữ liệu cho subscription đó; còn tùy routing/broker. Tuy nhiên cấu hình quyền nên chính xác theo intent, đừng rely vào việc handler tình cờ không có route.

### 2.2. `simpSubscribeDestMatchers` giải quyết quyền đọc một topic

~~~java
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .hasRole("MEMBER");
~~~

Nó áp dụng cho **SUBSCRIBE** tại topic rooms một segment. Nó **không** cấp quyền để client SEND trực tiếp vào broker topic đó.

Nhưng lưu ý: `ROLE_MEMBER` chung chưa kiểm user được vào **room nào**; khi rooms có dữ liệu riêng, cần policy room membership theo ID đích.

### 2.3. `simpTypeMatchers` hữu ích để từ chối các frame chưa được khai báo

~~~java
messages.simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE)
    .denyAll();
~~~

Đặt sau các rule được phép để **từ chối toàn bộ SEND/SUBSCRIBE chưa match**. Một `MESSAGE` có destination `/topic/admin/alerts` nhưng không có rule cho phép sẽ bị chặn.

`simpTypeMatchers` không phân tích đường dẫn. Nếu đặt rule `simpTypeMatchers(MESSAGE).authenticated()` quá sớm, user chỉ cần đăng nhập có thể SEND vào mọi destination; đây là một anti-pattern.

## 3. Thứ tự rule: first matching rule wins

`MessageMatcherDelegatingAuthorizationManager` chọn matcher phù hợp theo **thứ tự khai báo**. Rule rộng đứng trước có thể che rule hẹp phía sau.

**Sai nguy hiểm:**

~~~java
messages
    .simpTypeMatchers(SimpMessageType.MESSAGE).authenticated()
    .simpMessageDestMatchers("/topic/system/**").denyAll()
    .anyMessage().denyAll();
~~~

Client đã đăng nhập gửi `MESSAGE /topic/system/alerts` sẽ trúng `MESSAGE.authenticated()` trước và không đến deny rule. Đó có thể là đường **spoof message**.

**Đúng:**

~~~java
messages
    .simpMessageDestMatchers("/app/chat.send").hasRole("MEMBER")
    .simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
    .anyMessage().denyAll();
~~~

Khi client SEND tới `/app/chat.send`, role MEMBER được kiểm; khi client SEND tới broker path `/topic/system/**`, nó chỉ trúng deny-by-default.

### 3.1. Một lỗi ordering khác: destination matcher quá rộng

~~~java
// KHÔNG KHUYẾN NGHỊ
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .anyMessage().denyAll();
~~~

`simpDestMatchers("/topic/**")` bắt **MESSAGE và SUBSCRIBE**, nên user authenticated có thể SUBSCRIBE admin topic mà không cần ROLE_ADMIN. Đổi thành:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .simpSubscribeDestMatchers("/topic/public-updates").authenticated()
    .simpTypeMatchers(
            SimpMessageType.MESSAGE,
            SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
~~~

Không cần mở quyền `/topic/**` cho MESSAGE từ client. Server-side `SimpMessagingTemplate` có thể publish nội bộ qua broker; chúng ta bảo vệ **inbound client messages**, không áp dụng logic tương tự cho mọi server outbound.

### 3.2. Khi nào `simpDestMatchers` thực sự có ích?

- Khi **cùng một quyền** được yêu cầu cho mọi message type có một destination pattern nhất định.
- Khi kết hợp một rule **SUBSCRIBE deny hẹp đứng trước** và một rule destination rộng hơn ở sau, có kiểm thử để đảm bảo nhánh không mong muốn bị chặn.
- Khi migration từ cấu hình cũ đã dùng destination-only và team hiểu rõ tác động với MESSAGE/SUBSCRIBE.

Nếu chỉ muốn SEND, ưu tiên `simpMessageDestMatchers`. Nếu chỉ muốn nghe, ưu tiên `simpSubscribeDestMatchers`.

## 4. Prefix và đường đi thực tế của STOMP message

Ví dụ WebSocket message broker:

~~~java
@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setUserDestinationPrefix("/user");
}
~~~

| Prefix | Bên xử lý dự kiến | Nguyên tắc |
| --- | --- | --- |
| `/app/**` | Spring `@MessageMapping` handler | Cho SEND có mục đích và quyền cụ thể |
| `/topic/**` | Broker broadcast | Chỉ cho client SUBSCRIBE những topic được phép, thường **deny client SEND** |
| `/queue/**` | Broker queue destination | Chỉ cấp SUBSCRIBE đúng queue được phép; không mở `/queue/**` |
| `/user/**` | Logical user destination | Có thể được Spring dịch thành destination riêng cho user/session |

Đây là conventions ứng dụng cấu hình, không phải quy tắc STOMP bắt buộc. Spring có thể dùng prefix khác. Matcher phải khớp **destination mà Spring thực nhận**, không chỉ URL UI hiển thị.

### 4.1. Không bao giờ để client tự giả làm “system producer”

Sai:

~~~text
Client Alice:
  SEND destination:/topic/system/announcements
  body="Admin has approved your transfer"
~~~

Nếu broker nhận và phân phối, Alice đã giả mạo thông báo hệ thống.

Đúng:

~~~text
Client Alice:
  SEND destination:/app/chat.send
       |
       v
@MessageMapping("chat.send") + authorization + validation
       |
       v
Server sends through SimpMessagingTemplate
       |
       v
/topic/public-updates
       |
       v
Clients authorized to SUBSCRIBE that topic receive data
~~~

Input từ client phải được validate: nội dung, kích thước, room membership, identity nguồn, rate limit và business rules. Không tin một trường `sender` trong payload; dùng `Principal` đã xác thực từ session.

### 4.2. Không mở `SUBSCRIBE /queue/**` tùy ý

Nếu một user destination như `/user/queue/inbox` được framework biến đổi thành một queue physical có session suffix, việc cho client subscribe trực tiếp `/queue/**` có thể tạo đường đi vào dữ liệu của user khác. Spring docs nhấn mạnh cần giới hạn subscriptions và chỉ cho **logical user destination** hợp lệ, thay vì cho broker queue wildcard.

Ví dụ:

~~~java
messages
    .simpSubscribeDestMatchers("/user/queue/inbox").authenticated()
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll();
~~~

Sự mapping `/user/queue/inbox` → physical broker destination do framework quản lý, không do client tự khai `/queue/user-<id>`.

### 4.3. Tenant/room ID trong destination không tự chứng minh quyền

Nếu destination là `/topic/rooms/42`, một user có `ROLE_MEMBER` **chưa chắc** được phép đọc room 42. Cần:
1. Kiểm Authentication hiện hành.
2. Trích room ID từ destination đã được parse chuẩn.
3. Kiểm membership của principal đối với room đó trong dữ liệu đáng tin.
4. Từ chối khi resource không tồn tại, đã khóa hoặc thuộc tenant khác.
5. Đánh giá khi SUBSCRIBE và cân nhắc revocation/lifecycle của một subscription dài.

Không tin room ID hoặc tenant ID trong client headers như bằng chứng membership.

## 5. Kiến trúc kiểm soát WebSocket inbound

~~~text
HTTP GET /ws (WebSocket handshake)
  |
  +-- Servlet Spring Security: xác thực HTTP session/cookie/Basic
  +-- WebSocket origin policy ở endpoint
  |
  v
STOMP CONNECT (yêu cầu CSRF token mặc định với @EnableWebSocketSecurity)
  |
  v
clientInboundChannel
  |
  +-- SecurityContext được lấy từ user/session
  +-- CSRF / same-origin defense
  +-- AuthorizationChannelInterceptor
  |       |
  |       v
  |    AuthorizationManager<Message<?>>
  |       |
  |       +-- nullDestMatcher
  |       +-- simpSubscribeDestMatchers
  |       +-- simpDestMatchers / simpMessageDestMatchers
  |       +-- simpTypeMatchers
  |       +-- anyMessage
  |
  +-- DENY: không chuyển inbound frame thành business/broker action
  |
  +-- ALLOW: @MessageMapping hoặc broker routing
                    |
                    v
             clientOutboundChannel
                    |
                    v
               subscribed clients
~~~

**Ranh giới đặc biệt quan trọng:** Spring Security WebSocket message authorization chủ yếu bảo vệ **`clientInboundChannel`**, không rà soát lại từng message trên `clientOutboundChannel`. Một message server phát có thể tới nhiều subscriber; vì vậy cần kiểm quyền khi SUBSCRIBE, không chỉ khi SEND.

Ngoài ra, một authorization rule có thể cho phép client **đăng ký** nhưng broker/application vẫn có thể từ chối do destination không tồn tại hoặc giao thức sai. Ngược lại, message được broker routing không tự chứng minh rằng policy room/tenant đã được kiểm đúng.

## 6. Mô hình quyền cho ứng dụng chat và notification

Chọn các loại client: anonymous chưa xác thực, MEMBER đã đăng nhập, ADMIN đã đăng nhập với ROLE_ADMIN.

| Message type | Destination | MEMBER | ADMIN | Tại sao |
| --- | --- | --- | --- | --- |
| CONNECT | null | Allow (còn cần CSRF) | Allow (còn cần CSRF) | Kết nối của user đã xác thực |
| SUBSCRIBE | `/topic/public-updates` | Allow | Allow | Topic cho mọi user đăng nhập |
| SUBSCRIBE | `/topic/rooms/42` | Allow* | Allow* | Demo kiểm MEMBER; production phải kiểm room membership |
| SUBSCRIBE | `/topic/admin/alerts` | Deny | Allow | Kênh quản trị |
| SUBSCRIBE | `/user/queue/inbox` | Allow | Allow | Logical personal queue |
| SUBSCRIBE | `/user/queue/errors` | Allow | Allow | Kênh lỗi của session |
| SUBSCRIBE | `/queue/private-all` | Deny | Deny | Không mở broker queue trực tiếp |
| SUBSCRIBE | `/app/admin/publish` | Deny | Deny | Không cho nghe command destination |
| MESSAGE (SEND) | `/app/chat.send` | Allow | Allow | Gửi qua application handler |
| MESSAGE (SEND) | `/app/admin/publish` | Deny | Allow | Publish announcement |
| MESSAGE (SEND) | `/topic/public-updates` | Deny | Deny | Không tự publish broker topic |
| MESSAGE (SEND) | `/topic/admin/alerts` | Deny | Deny | Không giả server notification |
| MESSAGE (SEND) | `/app/unknown` | Deny | Deny | Chưa có rule |
| MESSAGE (SEND) | `/queue/private-all` | Deny | Deny | Không gửi thẳng broker queue |

*Demo role-only là **đơn giản hóa có chủ đích**; room có dữ liệu riêng phải áp dụng ownership/membership riêng.

Cấu hình ở phần sau đưa `SUBSCRIBE /app/**` thành DENY **trước** rule `simpDestMatchers("/app/admin/**")`. Đây là ví dụ rõ ràng về cách một matcher destination-only phải được đặt vào đúng thứ tự để không vô ý cho phép message type khác.

## 7. Dự án Spring Boot 3.x / Spring Security 6.x / Java 17+

Dự án demo:
- Dùng Spring MVC + STOMP WebSocket message broker.
- Có một HTTP security filter chain cho handshake.
- Bật Spring Security message authorization với `@EnableWebSocketSecurity`.
- Có hai controllers xử lý `SEND` từ client và server publish bằng `SimpMessagingTemplate`.
- Tạo JUnit tests trên **chính AuthorizationManager bean**, với inbound messages giả lập đúng type/destination để test policy mà không mở socket.
- Không tắt WebSocket CONNECT CSRF: end-to-end STOMP client phải cung cấp token hợp lệ.

Các tests dưới đây là **policy-level integration tests**: khởi động Spring Context và dùng bean thực, không kiểm full socket/CSRF handshake. Vì không yêu cầu kết nối mạng, tests có thể chạy ổn định ngay trong CI. Production nên bổ sung end-to-end WebSocket STOMP tests để xác minh HTTP authentication, Origin, CONNECT CSRF, routing và broker behavior.

### 7.1. `settings.gradle`

~~~groovy
rootProject.name = 'stomp-message-authorization-lab'
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.stompauth'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Vì sao cần `spring-security-messaging`?** Authorization message matcher/manager nằm trong module này, không phải `spring-security-web` thông thường. `spring-boot-starter-websocket` kéo các thành phần Spring WebSocket/STOMP. Không dùng `ServerHttpSecurity`/`SecurityWebFilterChain` của WebFlux để cấu hình bài **Servlet WebSocket MessageBroker** này.

### 7.3. `src/main/java/demo/stompauth/StompAuthApplication.java`

~~~java
package demo.stompauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompAuthApplication.class, args);
    }
}
~~~

### 7.4. `src/main/java/demo/stompauth/BrokerConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class BrokerConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        // Cùng origin mặc định. Không mở setAllowedOriginPatterns("*").
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`/ws` là HTTP handshake endpoint, không phải STOMP destination pattern. `/app` đi đến `@MessageMapping`; `/topic` và `/queue` dành cho broker; `/user` là prefix cho user destination conversion. Việc cấu hình broker không tự đặt chính sách authorization cho từng frame; cần Message Security bên dưới.

Để tránh mở dữ liệu riêng tư, không cấu hình broker với một wildcard subscription toàn cục và không xem prefix là bằng chứng tenant/room membership.

### 7.5. `src/main/java/demo/stompauth/MessageSecurityConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT/DISCONNECT/UNSUBSCRIBE thường không có destination.
            .nullDestMatcher().authenticated()

            // Ngoại lệ: kênh thông báo lỗi của user/session.
            .simpSubscribeDestMatchers("/user/queue/errors").permitAll()

            // Những subscription được cấp quyền.
            .simpSubscribeDestMatchers("/user/queue/inbox")
                .hasRole("MEMBER")
            .simpSubscribeDestMatchers("/topic/public-updates")
                .authenticated()
            .simpSubscribeDestMatchers("/topic/rooms/*")
                .hasRole("MEMBER")
            .simpSubscribeDestMatchers("/topic/admin/**")
                .hasRole("ADMIN")

            // Chặn SUBSCRIBE tới application command destinations.
            // PHẢI đứng trước simpDestMatchers("/app/admin/**").
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Destination-only: khớp mọi type có destination này.
            // SUBSCRIBE /app/** ở trên đã bị chặn; các command
            // MESSAGE /app/admin/** cần ROLE_ADMIN.
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")

            // Chỉ cấp quyền MESSAGE (STOMP SEND) cho chat command.
            .simpMessageDestMatchers("/app/chat.send")
                .hasRole("MEMBER")

            // Tất cả MESSAGE/SUBSCRIBE khác: từ chối.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE).denyAll()

            // Bất kỳ loại message nào còn sót: từ chối.
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

**Phân tích thứ tự, từng dòng:**

1. `nullDestMatcher().authenticated()` cho phép các message không có destination **khi user authenticated**. Spring docs dùng cách này cho các frame điều khiển như CONNECT, UNSUBSCRIBE, DISCONNECT; yêu cầu CSRF ở CONNECT là **một lớp kiểm tra khác**, không bị `authenticated()` thay thế.
2. `simpSubscribeDestMatchers("/user/queue/errors").permitAll()` cho phép SUBSCRIBE kênh lỗi về mặt *authorization*. Nó **không** biến HTTP handshake hoặc CONNECT thành anonymous nếu nơi khác vẫn yêu cầu auth/CSRF.
3. `/user/queue/inbox` yêu cầu MEMBER, không mở `/queue/**` vật lý.
4. `/topic/public-updates` yêu cầu người dùng đã xác thực.
5. `/topic/rooms/*` yêu cầu MEMBER; sản phẩm thật phải kiểm membership từng room.
6. `/topic/admin/**` yêu cầu ADMIN khi SUBSCRIBE.
7. `simpSubscribeDestMatchers("/app/**").denyAll()` chặn việc SUBSCRIBE tới command namespace.
8. `simpDestMatchers("/app/admin/**").hasRole("ADMIN")` biểu diễn destination-only matcher. Vì rule số 7 đã phủ mọi SUBSCRIBE `/app/**`, ADMIN không vô tình được nghe command path trong policy này.
9. `simpMessageDestMatchers("/app/chat.send").hasRole("MEMBER")` là rule **chỉ cho SEND**, tránh cấp quyền SUBSCRIBE vào cùng path.
10. `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` chặn tất cả send/subscribe không có rule cụ thể.
11. `anyMessage().denyAll()` chặn mọi loại còn lại ngoài các nhánh đã xét.

**Ràng buộc:** Mỗi rule dùng `hasRole("MEMBER")` tương ứng Spring authority `ROLE_MEMBER`, và `hasRole("ADMIN")` tương ứng `ROLE_ADMIN`. Không thêm prefix `ROLE_` trong tham số `hasRole`.

**Ngoại lệ về thiếu destination:** `nullDestMatcher` dựa trên việc không có destination, nên cũng có thể match một message `MESSAGE`/`SUBSCRIBE` được tạo nhân tạo nhưng thiếu destination. Với giao thức STOMP hợp lệ, SEND/SUBSCRIBE cần destination. Do đó việc chặn frame malformed phải được thực thi ở protocol/broker validation và nên được test end-to-end; không đánh đồng `nullDestMatcher` với một allowlist nghiêm ngặt theo command. Nếu cần chặn những loại malformed ngay ở AuthorizationManager, hãy viết custom matcher xét đồng thời type và destination null trước rule này.

### 7.6. `src/main/java/demo/stompauth/HttpSecurityConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/ws", "/csrf")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Không disable CSRF mặc định!
                .build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails member = User.withUsername("member")
                .password(encoder.encode("member-pass"))
                .roles("MEMBER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN", "MEMBER")
                .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}
~~~

HTTP layer yêu cầu authenticated cho `/ws`. **Không được đánh đồng:** HTTP `requestMatchers("/ws")` chỉ xét handshake, còn `simpSubscribeDestMatchers(...)` xét STOMP messages sau đó. Trong browser, `WebSocket` API không cho script tự đặt bất kỳ Authorization header nào ở handshake; triển khai thực thường dùng session/cookie được xác thực qua HTTP hoặc token flow đã thiết kế và kiểm chứng. HTTP Basic ở đây chỉ để minh họa server-side authentication; không phải lời hứa rằng mọi browser STOMP client đều có thể gửi Basic header tùy ý.

### 7.7. `src/main/java/demo/stompauth/CsrfController.java`

~~~java
package demo.stompauth;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

Với client dựa trên session/cookie, ứng dụng có thể cung cấp CSRF token từ một endpoint được bảo vệ rồi gửi trong **STOMP CONNECT headers**. Token phải gắn với CSRF repository và session/client identity tương ứng, không được hardcode hay thay bằng bất kỳ chuỗi ngẫu nhiên nào ở phía client. Nếu dùng SockJS, cần kiểm soát CSRF HTTP transport và STOMP CONNECT separately; không mở quyền CSRF toàn ứng dụng.

### 7.8. `src/main/java/demo/stompauth/MessagingController.java`

~~~java
package demo.stompauth;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class MessagingController {

    public record ChatInput(String text) {}

    private final SimpMessagingTemplate outbound;

    public MessagingController(SimpMessagingTemplate outbound) {
        this.outbound = outbound;
    }

    @MessageMapping("/chat.send")
    public void chat(ChatInput input, Principal principal) {
        if (input == null
                || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 500) {
            throw new IllegalArgumentException("Invalid text");
        }

        // Sender lấy từ Principal tin cậy, không lấy từ payload.
        String body = principal.getName() + ": " + input.text();
        outbound.convertAndSend("/topic/public-updates", body);
    }

    @MessageMapping("/admin/publish")
    public void announcement(ChatInput input, Principal principal) {
        if (input == null
                || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 300) {
            throw new IllegalArgumentException("Invalid announcement");
        }

        outbound.convertAndSend(
                "/topic/admin/alerts",
                "Admin " + principal.getName() + ": " + input.text());
    }
}
~~~

`/app/chat.send` vào `@MessageMapping("/chat.send")`; client MEMBER được phép SEND qua manager. Server publish tới `/topic/public-updates` bằng `SimpMessagingTemplate`; client chỉ nhận nếu được SUBSCRIBE. Tương tự, `/app/admin/publish` là lệnh ADMIN và server mới publish `/topic/admin/alerts`.

Controller này **không thực hiện** validation HTML/Markdown rendering ở client; UI nhận text phải escape để ngăn XSS, có rate limit, payload schema và audit theo nhu cầu. Không tạo một room id nhạy cảm trong payload rồi nghĩ `hasRole("MEMBER")` đủ để gửi cho mọi room.

## 8. Kiểm thử trực tiếp AuthorizationManager bằng JUnit 5

Thay vì tạo kết nối WebSocket mạng thật, tạo Spring `Message<?>` với:
- `SimpMessageType`;
- destination;
- một `Authentication` do test tạo.

Sau đó gọi `AuthorizationManager<Message<?>>.authorize(...)` để lấy `AuthorizationResult.isGranted()`. Đây là **integration test của policy bean**, không phải end-to-end STOMP test của kết nối. Nó kiểm chính xác thứ tự, type/destination và role logic trong `MessageSecurityConfiguration`.

### 8.1. `src/test/java/demo/stompauth/MessageAuthorizationPolicyTest.java`

~~~java
package demo.stompauth;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = StompAuthApplication.class)
class MessageAuthorizationPolicyTest {

    @Autowired
    AuthorizationManager<Message<?>> manager;

    private Authentication member() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "member",
                "test-only",
                List.of(new SimpleGrantedAuthority("ROLE_MEMBER")));
    }

    private Authentication admin() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "admin",
                "test-only",
                List.of(
                        new SimpleGrantedAuthority("ROLE_ADMIN"),
                        new SimpleGrantedAuthority("ROLE_MEMBER")));
    }

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "test-key",
                "anonymous",
                List.of(
                        new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private Message<?> inbound(
            SimpMessageType type,
            String destination) {

        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            accessor.setDestination(destination);
        }

        accessor.setLeaveMutable(true);

        return MessageBuilder.createMessage(
                new byte[0],
                accessor.getMessageHeaders());
    }

    private boolean granted(
            Authentication actor,
            SimpMessageType type,
            String destination) {

        AuthorizationResult result = manager.authorize(
                () -> actor,
                inbound(type, destination));

        // Catch-all trong policy phải luôn trả decision, không null.
        assertNotNull(result, "Policy returned no decision");
        return result.isGranted();
    }

    @Test
    void memberMaySendChatCommand() {
        assertTrue(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/app/chat.send"));
    }

    @Test
    void anonymousMayNotSendChatCommand() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.MESSAGE,
                "/app/chat.send"));
    }

    @Test
    void memberCannotSendAdminCommand() {
        assertFalse(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/app/admin/publish"));
    }

    @Test
    void adminMaySendAdminCommand() {
        assertTrue(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/app/admin/publish"));
    }

    @Test
    void memberMaySubscribePublicUpdates() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/public-updates"));
    }

    @Test
    void anonymousMayNotSubscribePublicUpdates() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.SUBSCRIBE,
                "/topic/public-updates"));
    }

    @Test
    void memberMaySubscribeRoomTopicUnderDemoRolePolicy() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/rooms/42"));
    }

    @Test
    void memberCannotSubscribeAdminTopic() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/admin/alerts"));
    }

    @Test
    void adminMaySubscribeAdminTopic() {
        assertTrue(granted(
                admin(),
                SimpMessageType.SUBSCRIBE,
                "/topic/admin/alerts"));
    }

    @Test
    void memberMaySubscribeOwnLogicalInbox() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox"));
    }

    @Test
    void errorsQueueIsAllowedAtRuleLevel() {
        assertTrue(granted(
                anonymous(),
                SimpMessageType.SUBSCRIBE,
                "/user/queue/errors"));
    }

    @Test
    void directBrokerQueueSubscriptionIsDenied() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/queue/private-all"));
    }

    @Test
    void clientCannotPublishToTopic() {
        assertFalse(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/topic/public-updates"));
    }

    @Test
    void evenAdminCannotPublishDirectlyToBroker() {
        assertFalse(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/topic/admin/alerts"));
    }

    @Test
    void adminCannotSubscribeApplicationCommand() {
        assertFalse(granted(
                admin(),
                SimpMessageType.SUBSCRIBE,
                "/app/admin/publish"));
    }

    @Test
    void memberCannotSubscribeChatCommand() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/app/chat.send"));
    }

    @Test
    void unknownApplicationMessageIsDenied() {
        assertFalse(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void authenticatedConnectPassesRuleButStillNeedsCsrf() {
        assertTrue(granted(
                member(),
                SimpMessageType.CONNECT,
                null));
    }

    @Test
    void anonymousConnectIsRejectedByAuthorizationRule() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.CONNECT,
                null));
    }

    @Test
    void authenticatedDisconnectPassesNullDestinationRule() {
        assertTrue(granted(
                member(),
                SimpMessageType.DISCONNECT,
                null));
    }
}
~~~

### 8.2. Vì sao test dùng `SimpMessageHeaderAccessor`?

Spring Security matchers đọc **Simp headers** để phân biệt `SimpMessageType` và destination, không chỉ nhìn body. Một test tạo `GenericMessage<>("some text")` với headers trống rồi mong nó là STOMP SEND sẽ không đúng. `SimpMessageHeaderAccessor.create(type)` và `setDestination` giúp tạo thông điệp có headers mà matchers thực sự dựa vào.

### 8.3. Vì sao test dùng `AuthorizationResult`?

Trong Spring Security 6.5, API hiện đại có:

~~~java
AuthorizationResult result = manager.authorize(
        () -> authentication,
        message);

boolean allowed = result != null && result.isGranted();
~~~

`result == null` có thể nghĩa là manager không đưa ra quyết định. Bài mẫu dùng `anyMessage().denyAll()` nên kỳ vọng có decision rõ ràng cho mọi message được test. Với các hệ thống custom, **không** coi null/no decision là allow theo mặc định.

Spring Security 6.5 còn có `check(...)` nhưng method này đã deprecated theo hướng `authorize(...)`; nếu dùng version cũ thì đối chiếu API chính xác trước khi copy test.

### 8.4. Ma trận kiểm thử và những gì chưa được test

| Nhóm test | Chứng minh | Không chứng minh |
| --- | --- | --- |
| MEMBER MESSAGE `/app/chat.send` allow | Rule `simpMessageDestMatchers` khớp đúng | Payload hợp lệ hoặc handler business chạy |
| MEMBER MESSAGE broker path deny | `simpTypeMatchers(MESSAGE).denyAll()` catch đúng | Broker relay thực sự chặn theo đường mạng |
| ADMIN SUBSCRIBE `/app/admin/publish` deny | Rule SUBSCRIBE deny đứng trước destination matcher | Transport protocol tự reject mọi malformed frame |
| MEMBER SUBSCRIBE `/topic/admin/alerts` deny | ADMIN-only subscription | Topic tồn tại và broker gửi dữ liệu |
| No-destination CONNECT | `nullDestMatcher` quyết định role | **CSRF CONNECT** hoặc Origin verification |
| SUBSCRIBE `/user/queue/inbox` allow | Logical user path phù hợp | Không có lỗi user-destination routing ở runtime |

Điểm giới hạn rất quan trọng: JUnit gọi manager trực tiếp **không** kiểm WebSocket HTTP handshake, STOMP parser, CONNECT CSRF, user destination translation, authenticated Principal trong session hay broker actual delivery. Một hệ thống production cần bổ sung end-to-end tests ở những boundaries ấy.

### 8.5. Lệnh chạy

Với Gradle wrapper của dự án:

~~~bash
./gradlew test --tests demo.stompauth.MessageAuthorizationPolicyTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.stompauth.MessageAuthorizationPolicyTest
gradlew.bat bootRun
~~~

Test dùng Spring Context và JUnit assertions; không có `System.out.println` trong code nên không có stdout nghiệp vụ cố định. Kết quả mong đợi là toàn bộ tests thành công; cần thực thi thật với Java 17/Boot 3.x/Security 6.x được chọn để xác nhận.

## 9. STOMP CONNECT, CSRF và Same Origin

Một request WebSocket gồm hai boundary khác nhau:

~~~text
HTTP GET /ws
  -> handshake authentication và origin policy

STOMP CONNECT frame
  -> authentication/session association
  -> CSRF trong STOMP headers (mặc định @EnableWebSocketSecurity)
  -> nullDestMatcher rule

STOMP SUBSCRIBE/SEND frames
  -> Spring Security message authorization manager
~~~

Các WebSocket browser connections không bị áp dụng Same Origin Policy giống một request XHR thông thường. Một site độc hại có thể thử mở WebSocket tới backend đã đăng nhập bằng cookie, vì vậy cần kiểm Origin/allowed origins và CSRF trên STOMP CONNECT.

Tài liệu Spring Security 6.5 mô tả rằng `@EnableWebSocketSecurity` mặc định yêu cầu **CSRF token trong STOMP CONNECT headers**. `nullDestMatcher().authenticated()` **không thay thế** CSRF verification và không tự bảo đảm Same Origin.

### 9.1. Tại sao không gắn CSRF vào mọi SEND?

Spring Security dùng STOMP CONNECT CSRF để bảo vệ quá trình thiết lập kết nối/session khỏi Cross-Site WebSocket Hijacking. HTTP CSRF filter áp dụng cho HTTP request; STOMP frames cần cơ chế bảo vệ riêng. Không giả định HTTP filter sẽ kiểm từng STOMP SEND.

### 9.2. Lấy CSRF token và gửi trong CONNECT

Một kịch bản browser/session:

~~~text
1. Browser login qua HTTPS -> authenticated session.
2. GET /csrf (giữ đúng cookies và origin).
3. JavaScript lấy token và header name từ response.
4. Browser mở WebSocket /ws.
5. STOMP CONNECT dùng headers:
       X-CSRF-TOKEN: <session-token>
6. Server kiểm token và session tương ứng trước khi nhận CONNECT.
7. Sau đó mới SUBSCRIBE/SEND với message authorization.
~~~

**`<session-token>` là placeholder minh họa, không phải token dùng thật.** Tên header/tên token có thể khác tùy `CsrfTokenRepository`; lấy từ response thực. Không lưu secret trong hardcoded JS hoặc ghi raw token vào logs. Nếu dùng SockJS, transport HTTP và CONNECT header có đặc điểm riêng; không tắt CSRF toàn bộ API chỉ để “fix lỗi connect”.

### 9.3. CORS và WebSocket origins

CORS là cơ chế browser cho HTTP fetch; WebSocket có Origin handling riêng. Spring WebSocket endpoint dùng allowed origins; đừng cho mọi origin bằng `setAllowedOriginPatterns("*")` nếu không có mô hình auth/CSRF được kiểm chứng. Phân biệt:
- Trusted browser origin có thể kết nối?
- User/session có được xác thực?
- STOMP CONNECT có CSRF hợp lệ?
- SUBSCRIBE/SEND có quyền với destination không?

Bốn điều này đều có thể cần kiểm riêng. Không dùng `permitAll("/ws/**")` hoặc disable CSRF để che một cấu hình STOMP client sai.

## 10. Custom policy theo room hoặc tenant

Ví dụ role-only:

~~~java
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .hasRole("MEMBER");
~~~

**Chưa đủ** khi mỗi room có người tham gia riêng. Hai người cùng ROLE_MEMBER có thể thuộc hai rooms khác nhau.

Mô hình đúng:

~~~text
SUBSCRIBE /topic/rooms/42
  |
  +-- authenticated principal = alice
  +-- server parses roomId=42
  +-- trusted repository: room 42 belongs to tenant acme
  +-- membership repository: alice active in room 42?
  +-- policy: room status allows subscription?
  |
  +-- allow/deny
~~~

Spring Security có thể dùng:

~~~java
// MINH HỌA: manager cần được triển khai bởi ứng dụng
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .access(roomMembershipAuthorizationManager);
~~~

Đây là **đoạn tích hợp**, `roomMembershipAuthorizationManager` chưa có implementation trong project demo. Nó cần là `AuthorizationManager<MessageAuthorizationContext<?>>`, phải xử lý principal, destination pattern, database truth và error handling. Nếu policy backend không truy cập được, **không** trả allow. Không lấy `roomId` hoặc `tenantId` trong STOMP headers làm chứng cứ membership.

### 10.1. Vòng đời subscription và revocation

Một SUBSCRIBE được allow vào 10:00. Đến 10:05 admin revoke room membership. Broker có thể đã ghi nhận subscription và còn gửi messages tiếp theo vì Spring Security không tái-authorize mỗi outbound message.

Với dữ liệu nhạy cảm, thiết kế:
- Cơ chế chủ động unsubscribe/close session khi role/membership bị revoke.
- Event invalidation và policy revision để các nodes cập nhật nhanh.
- Kiểm quyền lại theo thời hạn/điều kiện khi phù hợp.
- Broker-level authorization hoặc topic isolation theo tenant nếu sử dụng external broker.
- Test trạng thái sau revoke, không chỉ thời điểm SUBSCRIBE ban đầu.

**Không nói “security ở inbound nên chắc chắn mọi outbound đều an toàn”.** Kiểm subscription là một chốt quan trọng, nhưng dữ liệu thay đổi quyền giữa phiên có thể cần chính sách bổ sung.

### 10.2. User destinations và spoofed identity

Server có thể gửi cá nhân:

~~~java
// MINH HỌA trong service có template và recipient ID đã xác minh.
messagingTemplate.convertAndSendToUser(
        trustedRecipientName,
        "/queue/inbox",
        eventPayload);
~~~

`trustedRecipientName` phải lấy từ domain/user directory đáng tin; `eventPayload` phải được xây từ business data có quyền. Client subscribe logical `/user/queue/inbox`; không cho client chỉ định physical destination của người khác. Không lấy `fromUser` trong payload để quyết định Principal phát message.

### 10.3. Multi-tenancy

Đừng trộn tenants vào một `/topic/rooms/{id}` nếu ID không globally unique hoặc data broadcasting không tách tenant. Dùng scope kiểu:

~~~text
tenant_id + room_id + subject_id + permission
~~~

Kiểm quyền trước subscription, và khi server publish đảm bảo destination được xây bằng tenant/resource mà domain service xác thực. Không nối chuỗi raw do user gửi rồi tự publish tới broker topic nhạy cảm.

## 11. Matcher builder và các lựa chọn mở rộng

Ngoài ba matcher trọng tâm:

| API | Khi nào dùng |
| --- | --- |
| `simpDestMatchers` | Match destination không giới hạn type |
| `simpMessageDestMatchers` | Match MESSAGE (STOMP SEND) + destination |
| `simpSubscribeDestMatchers` | Match SUBSCRIBE + destination |
| `simpTypeMatchers` | Match enum `SimpMessageType` |
| `nullDestMatcher` | Match thiếu destination, thường là control frames |
| `anyMessage` | Catch-all cho message chưa được match |
| `matchers(customMessageMatcher)` | Chèn matcher chuyên biệt nếu cần type + headers + tenant |
| `access(customAuthorizationManager)` | Custom decision với object/domain policy |

Trong Spring Security 6.5, các destination patterns mặc định có thể dùng `AntPathMatcher`, và versions/cấu hình mới có thể hỗ trợ builder dựa trên `PathPatternMessageMatcher`. Dấu `*`, `**`, dấu slash, URL encoding và path variables cần được test với version thực tế. Không áp dụng suy đoán của HTTP matcher như `requestMatchers("/**")` sang STOMP mà chưa test.

### 11.1. Lỗi chồng lấn pattern

~~~java
messages
    .simpSubscribeDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN");
~~~

Ở cấu hình trên, rule thứ hai không còn bảo vệ đúng vì matcher rộng đến trước.

Thứ tự đúng:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .simpSubscribeDestMatchers("/topic/public/**").authenticated()
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll();
~~~

Bản production tốt hơn là **không mở wildcard rộng** trừ khi mọi topic trong namespace ấy thực sự có cùng security policy.

### 11.2. No decision không được tự biến thành allow

Nếu custom AuthorizationManager không tìm được rule, có thể trả null/abstain tùy contract. Application nên có catch-all deny và test mọi loại/đường destination. Không viết code tự xử lý `null decision => true`.

### 11.3. Vì sao check chỉ role không đủ?

`hasRole("ADMIN")` chứng minh authority đã được cấp ở authentication context, không chứng minh client được gửi announcement nhân danh mọi tenant. Những operation như transfer money, create order, join room, publish audit log phải kiểm business policy trong handler/service, kể cả khi inbound message đã được cho phép theo URL/role.

## 12. Test end-to-end cần bổ sung trước production

Policy-level tests ở mục 8 là bước đầu. Test mạng thực có thể dùng Spring STOMP client hoặc test framework tương ứng:

~~~text
1. HTTP login -> authenticated Principal/session.
2. GET /csrf -> token đúng session.
3. WebSocket handshake /ws với đúng cookie/origin.
4. STOMP CONNECT với CSRF header đúng.
5. SUBSCRIBE /topic/public-updates với member -> được đăng ký.
6. SEND /app/chat.send -> server xử lý và publish tới topic.
7. SUBSCRIBE /topic/admin/alerts với member -> bị chặn.
8. SUBSCRIBE /topic/admin/alerts với admin -> được đăng ký.
9. SEND /topic/admin/alerts từ client -> bị chặn.
10. SEND /app/admin/publish từ admin -> server mới phát notification.
11. CONNECT thiếu/sai CSRF -> bị từ chối.
12. Handshake từ origin không tin -> bị từ chối.
13. Revoke membership giữa kết nối -> policy/connection xử lý theo contract.
~~~

Các lỗi STOMP authorization thường dẫn đến ERROR frame hoặc connection termination, **không nhất thiết là HTTP 403**, vì handshake HTTP đã kết thúc. Test phải kiểm hành vi STOMP frame, không suy từ HTTP status của `/ws`.

### 12.1. Phân biệt ba lớp test

| Lớp | Xác minh | Công cụ |
| --- | --- | --- |
| Unit/policy | Matcher type/destination, first-match rule, role decision | `AuthorizationManager.authorize` với Simp headers |
| Framework integration | Security bean wiring, inbound interceptors, authentication context | `@SpringBootTest` / messaging test setup |
| End-to-end socket | Handshake, CONNECT CSRF, Origin, broker routing, actual frames | WebSocket STOMP test client |

Không để toàn bộ bảo mật dựa vào việc một rule test với `GenericMessage` không có Simp headers. Và không coi policy unit test là bằng chứng browser CSRF đã được bảo vệ.

## 13. Những sai lầm phổ biến

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Client gửi được vào `/topic/system/**` | `simpDestMatchers("/topic/**").authenticated()` quá rộng | Chỉ allow SEND vào `/app/**` hợp lệ, deny MESSAGE khác |
| User subscribe topic ADMIN | Rule `/topic/**` đứng trước `/topic/admin/**` | Specific-before-general |
| SUBSCRIBE `/app/admin/**` được phép | `simpDestMatchers` match mọi type | Thêm subscribe deny trước hoặc dùng message-only matcher |
| MESSAGE `/topic/public-updates` lọt qua | `simpTypeMatchers(MESSAGE).authenticated()` quá sớm | Dùng denyAll fallback |
| Không nhận được data trên `/user/queue/inbox` | Nhầm logical user prefix với physical broker queue | Dùng user destination routing đúng |
| User nghe được queue người khác | Subscribe trực tiếp `/queue/**` | Không mở broker queue wildcard |
| CONNECT bị lỗi dù HTTP Basic đúng | Chưa có STOMP CONNECT CSRF | Lấy CSRF token đúng session và gửi trong headers |
| GET /ws 101 nhưng SUBSCRIBE bị deny | HTTP handshake và message authorization khác nhau | Debug inbound matcher/authority |
| Policy test luôn null decision | Thiếu Simp headers/type/destination | Tạo message bằng SimpMessageHeaderAccessor |
| Admin có quyền SEND nhưng vẫn bị chặn | Matcher deny đứng trước allow | Sắp xếp allow cụ thể trước catch-all |
| Người dùng chưa login SUBSCRIBE errors | Rule permitAll nhưng CONNECT/handshake còn chặn | Hiểu từng lớp và CSRF |
| Room MEMBER đọc room lạ | Role-only, không check membership | Custom manager + trusted domain DB |
| Broker relay cho phép khác policy Spring | Security chỉ trên inbound Spring app, đường broker khác | Broker ACL/network isolation |
| User đã revoke vẫn nhận dữ liệu | Existing subscription không re-check outbound | Close/unsubscribe/revoke handling |
| Kẻ tấn công spoof sender trong payload | Tin trường `fromUser` | Lấy Principal từ session |
| WebSocket từ evil origin được nhận | Origins wildcard/CSRF disabled | Allowed Origin + STOMP CSRF |
| Test nhầm SEND là `SimpMessageType.SEND` | Enum Spring dùng MESSAGE | Dùng `SimpMessageType.MESSAGE` |
| HTTP `requestMatchers` không chặn STOMP SEND | Chỉ áp dụng ở handshake HTTP | Dùng Message Security inbound |
| Dùng WebFlux config cho servlet STOMP | Sai stack | Dùng `@EnableWebSocketMessageBroker` và MessageSecurity |
| Chỉ check inbound SEND, không check SUBSCRIBE | Subscriber có thể nhận dữ liệu nhạy cảm | Cấp quyền subscribe riêng |
| Catch custom policy exception rồi allow | Fail-open khi DB/PDP lỗi | Deny/close, log reason code |
| Log raw STOMP payload/auth token | Lộ dữ liệu nhạy cảm | Redaction, giới hạn debug |
| Subscriber nhận nhiều tenant events | Server publish vào topic chung | Tenant isolation, resource-aware routing |

## 14. Checklist bảo mật trước triển khai

1. Có phân biệt HTTP handshake endpoint với STOMP destinations chưa?
2. `@EnableWebSocketMessageBroker` và `@EnableWebSocketSecurity` được cấu hình đúng chưa?
3. Có bean `AuthorizationManager<Message<?>>` với builder đúng version?
4. `simpDestMatchers` được dùng có chủ ý với nhiều message types?
5. Nếu chỉ SEND, đã cân nhắc `simpMessageDestMatchers`?
6. Nếu chỉ nghe, đã dùng `simpSubscribeDestMatchers`?
7. `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` ở cuối các allow rules?
8. `anyMessage().denyAll()` có chặn mọi message còn lại?
9. Những rule specific đặt trước wildcard/general?
10. Không có client SEND trực tiếp tới `/topic/**`, `/queue/**`?
11. Không cho SUBSCRIBE tự do vào `/queue/**` physical destinations?
12. Logical `/user/**` queue chỉ cho principal phù hợp?
13. Tenant/room membership được kiểm bằng dữ liệu domain đáng tin?
14. Role labels khớp convention `ROLE_` của Spring Security?
15. `Principal` lấy từ authenticated session, không từ payload?
16. STOMP CONNECT có CSRF token đúng và Origin restrictions?
17. HTTP handshake/auth và STOMP CONNECT được test riêng?
18. Policy tests có dùng `SimpMessageHeaderAccessor` với type/destination đúng?
19. Test cả SEND và SUBSCRIBE tới cùng destination để phát hiện matcher không type-specific?
20. Test unauthenticated, MEMBER, ADMIN và đường chưa khai báo?
21. Khi sử dụng external broker, đã bảo vệ broker khỏi direct client bypass?
22. Khi revoke quyền, existing subscriptions/long-lived sockets có được xử lý?
23. Outbound data được route theo tenant/user đúng, không broadcast nhầm?
24. Logs đã redact token và payload nhạy cảm chưa?
25. Rate limit/kích thước message, abuse và spam có cơ chế kiểm soát?
26. Có regression tests khi nâng Spring Boot/Spring Security/STOMP broker không?

## 15. Bài tập thực hành

**Bài 1 – Khác biệt matcher.** Tạo một MESSAGE và một SUBSCRIBE cùng destination `/app/chat.send`. Chứng minh `simpDestMatchers` có thể match cả hai, còn `simpMessageDestMatchers` chỉ match MESSAGE.

**Bài 2 – Specific-before-general.** Đặt `simpSubscribeDestMatchers("/topic/**").authenticated()` trước `/topic/admin/**`. Viết test MEMBER SUBSCRIBE admin topic và quan sát sai policy; sửa thứ tự.

**Bài 3 – Broker spoofing.** Tạo MESSAGE `/topic/system/announcements` với ROLE_ADMIN. Policy an toàn vẫn deny. Giải thích vì sao chỉ server-side producer được publish.

**Bài 4 – User queue.** So sánh SUBSCRIBE `/user/queue/inbox` với `/queue/private-all`, giải thích logical user destination conversion và nguy cơ physical broker wildcard.

**Bài 5 – Type fallback.** Xóa `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` nhưng giữ `anyMessage().denyAll()`; test behavior không đổi, giải thích vì sao rule type fallback vẫn hữu ích để diễn đạt policy rõ.

**Bài 6 – CSRF CONNECT.** Chạy STOMP browser client với/không có CSRF header phù hợp. Phân biệt việc CONNECT bị deny do token sai với SUBSCRIBE bị deny do role.

**Bài 7 – Room membership.** Thay `hasRole("MEMBER")` ở `/topic/rooms/*` bằng custom manager đọc room membership từ repository tin cậy. Test user ở room A không đọc room B.

**Bài 8 – Token change.** Revoke ROLE_ADMIN khi socket còn mở. Thiết kế đóng session/force unsubscribe hoặc policy revalidation và kiểm broker không tiếp tục phát thông tin riêng.

**Bài 9 – Đường gửi command.** Thêm `/app/chat.delete` được phép với ROLE_MODERATOR, không mở `/app/**` cho mọi authenticated user. Test MESSAGE lạ deny.

**Bài 10 – E2E.** Tạo hai STOMP connections authenticated, một MEMBER và một ADMIN, kiểm SUBSCRIBE và SEND qua broker thật với origin/CSRF hợp lệ. Đối chiếu event nhận được với policy unit tests.

**Bài 11 – Null destination.** Tạo CONNECT/DISCONNECT và một MESSAGE không có destination. Giải thích vì sao `nullDestMatcher` khác `simpTypeMatchers`, và tại sao malformed SEND phải được protocol layer reject hoặc custom guard chặn.

**Bài 12 – Different broker.** Thay simple broker bằng broker relay; xác minh không thể bypass Spring inbound authorization bằng cách kết nối trực tiếp broker từ mạng không được tin. Đánh giá ACL ở broker ngoài.

**Tiêu chí hoàn thành:** diễn giải chính xác ba API `simpDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`; phân biệt MESSAGE/SUBSCRIBE/CONNECT; sắp xếp first-match hợp lý; tránh SEND vào broker prefixes, giới hạn SUBSCRIBE theo principal/tenant/room; và kiểm thử policy bằng manager thực với Simp headers, rồi kiểm thử full STOMP origin/CSRF end-to-end.

## 16. Tài liệu tham khảo chính thức

- Spring Security 6.5 – **WebSocket Security** (message authorization, first-match rules, CSRF CONNECT, inbound/outbound, user destinations): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 – **MessageMatcherDelegatingAuthorizationManager.Builder API**, `simpDestMatchers`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security 6.5 – **AuthorizationManager API**, `authorize` và `AuthorizationResult`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Framework – **STOMP Overview**, frame commands, broker/app prefixes: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework – **STOMP Message Flow**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework – **User Destinations**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework – **Enable STOMP**, simple broker and endpoint setup: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework – **WebSocket Allowed Origins**: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
