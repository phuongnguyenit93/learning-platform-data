# Bảo vệ gửi, nhận thông điệp trên kênh STOMP cá nhân trong Spring Security

Ứng dụng nhắn tin, thông báo theo tài khoản và bảng công việc thường dùng **WebSocket + STOMP** để đẩy dữ liệu thời gian thực. Một luồng “chỉ gửi cho người dùng X” chỉ an toàn khi hệ thống kiểm soát được **ai tạo thông điệp, ai được gửi tới người nhận, ai được đăng ký nhận, và session nào thực sự được nhận dữ liệu**. Đổi tên destination thành `/user/queue/inbox` chưa tự động thay thế cho authentication, authorization hay kiểm tra quyền nghiệp vụ.

Bài thực hành này dùng **Spring Boot 3.5.x, Java 17+, Spring Security 6.x, Spring Messaging và Servlet WebSocket/STOMP**. Phần cấu hình, source Java và JUnit được trình bày theo dạng dự án Maven; các đoạn client JavaScript được ghi rõ khi cần thư viện `@stomp/stompjs`. Các nguyên tắc security cũng hữu ích khi nâng lên Spring Security 7, nhưng cần kiểm API cụ thể của phiên bản áp dụng.

## 1. Mục tiêu bảo mật và mô hình đe dọa

Giả sử Alice và Bob có quyền trò chuyện với nhau. Carol là người dùng có tài khoản nhưng **không thuộc cuộc trò chuyện**. Hệ thống muốn:

1. Alice gửi tin cho Bob bằng lệnh STOMP `SEND` tới một application destination do server xử lý.
2. Server lấy người gửi từ **`Principal` đã xác thực**, xác minh quyền trò chuyện và dữ liệu đầu vào, rồi chuyển tin đến **user destination của Bob**.
3. Bob đăng ký nhận qua `SUBSCRIBE /user/queue/inbox`; Alice không thể đọc inbox của Bob bằng cách tự thay chuỗi destination.
4. Carol không thể gửi tin tới Bob chỉ bằng cách sửa `to` trong JSON, dù Carol đã đăng nhập.
5. Client không thể tự phát thông điệp “thay server” vào `/queue/**` hay `/topic/**` hoặc đăng ký trực tiếp một physical broker queue có thể chứa dữ liệu người khác.
6. Origin, CSRF khi STOMP `CONNECT`, HTTP handshake, logout và vòng đời session được kiểm tra theo cơ chế dùng thực tế.

Phải kiểm **chiều gửi** và **chiều nhận** riêng biệt:

| Hướng | STOMP frame | Destination ví dụ | Quyết định cần có |
| --- | --- | --- | --- |
| Client → ứng dụng | `SEND` | `/app/chat/send` | Đã xác thực, có quyền sử dụng chức năng, có quyền gửi tới recipient |
| Client → broker | `SUBSCRIBE` | `/user/queue/inbox` | Đã xác thực; chỉ subscription dạng user-relative được cho phép |
| Client → broker trực tiếp | `SEND` | `/queue/inbox`, `/topic/system` | Từ chối để tránh giả danh server |
| Client → physical queue | `SUBSCRIBE` | `/queue/inbox-userXYZ` | Từ chối để tránh đọc queue/session người khác |
| Server → Bob | Thông điệp nội bộ | `convertAndSendToUser("bob", "/queue/inbox", ...)` | Server chọn người nhận sau kiểm tra nghiệp vụ |
| Server → socket Bob | Outbound `MESSAGE` | Destination phiên riêng do Spring xử lý | Dữ liệu chỉ đến những session đã được map và subscribe đúng |

**Điều quan trọng:** Spring Security bảo vệ chủ yếu **`clientInboundChannel`** (khung tin từ client vào). Nó không tự chạy lại authorization cho từng outbound message trên `clientOutboundChannel`. Vì thế, việc **kiểm tra SUBSCRIBE đầu vào**, bảo vệ code server phát tin và cấu hình broker đúng có ý nghĩa quyết định.

## 2. Hiểu ba loại destination và tên người dùng

Dùng ba namespace tách biệt:

- `/app/**`: **application destination**; client gửi `SEND` vào đây, Spring chuyển tới controller có `@MessageMapping`.
- `/user/**`: **user destination prefix**; client dùng `/user/queue/inbox` để SUBSCRIBE; Spring ánh xạ tới destination gắn với session. Đây không phải nơi client tự chọn user bằng đường dẫn.
- `/queue/**` hoặc `/topic/**`: **broker destination**; broker xử lý những subscription/notification đã được server ánh xạ hoặc công khai có chủ đích. Không mặc định cấp quyền SEND/SUBSCRIBE trực tiếp cho mọi client.

Với cấu hình:

~~~java
registry.enableSimpleBroker("/queue");
registry.setApplicationDestinationPrefixes("/app");
registry.setUserDestinationPrefix("/user");
~~~

luồng đúng là:

~~~text
Alice đã đăng nhập:
  SEND /app/chat/send
  {"to":"bob","body":"Chào Bob"}

Spring @MessageMapping("/chat/send"):
  Principal.getName() == "alice"
  ChatPolicy.canSend("alice", "bob") == true
  convertAndSendToUser("bob", "/queue/inbox", event)

Bob đã đăng nhập:
  SUBSCRIBE /user/queue/inbox
  Spring ánh xạ vào queue gắn với session của Bob
  → Bob nhận MESSAGE có from="alice"
~~~

`UserDestinationMessageHandler` chuyển `/user/queue/inbox` thành destination **riêng theo session** (tên physical cụ thể do framework tạo, không phải API cho client tự đoán). Việc server gọi `convertAndSendToUser("bob", "/queue/inbox", ...)` thường gửi tới **các session đang kết nối của Bob** và đăng ký destination đó. Nếu muốn trả lời duy nhất session vừa gửi một command, dùng `@SendToUser(value="/queue/receipts", broadcast=false)` tại handler thích hợp.

Không được coi đoạn `bob` trong chuỗi `/user/bob/queue/inbox` do client gửi là bằng chứng client chính là Bob. Trong ví dụ, client **chỉ được SUBSCRIBE chính xác `/user/queue/inbox`**. Những pattern dài hơn hoặc physical broker destination đều bị từ chối. Tên người nhận do server sử dụng ở API `convertAndSendToUser`, dựa vào Principal/khóa người dùng được xác minh.

**Principal identity:** `Principal#getName()` là danh tính trên kết nối, được Spring lấy từ quá trình xác thực HTTP handshake trong cấu hình session thông thường. Nếu hệ thống đa tenant, bảo đảm tên Principal **duy nhất trong phạm vi hệ thống** (ví dụ ánh xạ từ user ID bất biến có tenant namespace); nếu hai tenant cùng có username `bob` mà cùng dùng `convertAndSendToUser("bob", ...)`, chỉ dựa vào username có thể gây giao tin sai người. Đó là trách nhiệm thiết kế identity, không phải đảm bảo tự động của prefix `/user`.

## 3. Ba lớp bảo vệ phải hoạt động cùng nhau

### 3.1. Authentication ở HTTP handshake

Trước khi STOMP chạy, trình duyệt mở WebSocket bằng HTTP Upgrade request. Với form login/session, Spring Security xác thực request HTTP và chuyển `Principal` sang phiên WebSocket. Browser cùng origin thường gửi cookie session trong handshake theo quy tắc cookie của trình duyệt. Nếu handshake chưa xác thực nhưng cấu hình cho mở socket, STOMP có thể không có Principal hợp lệ.

**Không tin header `login`, `passcode` hoặc `sender` do STOMP client tự khai để xác định identity.** Spring WebSocket mặc định không biến các header STOMP đó thành authentication của HTTP session. Nếu triển khai API stateless JWT, cần cơ chế xác thực token ở handshake hoặc interceptor `CONNECT` được thiết kế đúng, gọi AuthenticationManager/JwtDecoder và liên kết Authentication vào session; không chỉ đọc một header rồi coi chuỗi username là người dùng thật.

### 3.2. Authorization cho từng STOMP frame đầu vào

Sau handshake, client có thể liên tục gửi `SEND` và `SUBSCRIBE` trên cùng kết nối. Không thể giả định “đã qua handshake” đồng nghĩa được làm mọi việc.

Với `@EnableWebSocketSecurity` và bean `AuthorizationManager<Message<?>>`, cấu hình nên cho phép **rất ít destination** và từ chối mặc định:

- `SEND /app/chat/send`: user có role cần thiết.
- `SUBSCRIBE /user/queue/inbox`: user có role cần thiết.
- `SEND /queue/**` và `SEND /topic/**`: từ chối.
- `SUBSCRIBE /queue/**` trực tiếp và `SUBSCRIBE /user/{other}/...`: từ chối.
- Mọi destination khác: từ chối cho đến khi được xét duyệt.

`simpMessageDestMatchers` chỉ xét các message có `SimpMessageType.MESSAGE` (thường tương ứng client STOMP `SEND`). `simpSubscribeDestMatchers` chỉ xét `SUBSCRIBE`. Còn `simpDestMatchers` không phân biệt loại, rất dễ mở rộng quá mức nếu dùng không đúng mục đích. Spring áp dụng **matcher khớp đầu tiên**, nên quy tắc cụ thể phải đứng trước `simpTypeMatchers(...).denyAll()` và `anyMessage().denyAll()`.

### 3.3. Business authorization trước khi phát tin

Ngay cả user được phép `SEND /app/chat/send` **chưa chắc được phép gửi cho mọi người nhận**. `to`, `conversationId`, `owner` hoặc `from` trong payload đều do client điều khiển.

Trong dịch vụ thật, policy nên kiểm:

- Sender là thành viên hoặc có grant hợp lệ trong cuộc trò chuyện.
- Recipient là thành viên hợp lệ, cùng tenant và chưa bị chặn theo chính sách sản phẩm.
- Đối tượng được gửi không bị xóa/thu hồi quyền và hành động được thực thi trong phạm vi tenant thực.
- Nếu thao tác gửi có lưu database, kiểm quyền và ghi dữ liệu với mức nhất quán/transaction phù hợp.

**Không lấy `from` từ JSON**. Server điền `from` từ `Principal`; nếu cần audit, lưu định danh server-side. Không gửi cả entity nội bộ có dữ liệu nhạy cảm vào payload đầu ra; tạo DTO chứa đúng trường người nhận được phép xem.

## 4. Dự án Maven tích hợp cấu hình STOMP cá nhân

Cấu trúc dự án:

~~~text
secure-stomp-inbox/
├── pom.xml
└── src/
    ├── main/java/com/example/stomp/
    │   ├── StompApplication.java
    │   ├── HttpSecurityConfig.java
    │   ├── WebSocketConfig.java
    │   ├── InboundSecurityConfig.java
    │   ├── ChatPolicy.java
    │   ├── ChatController.java
    │   └── CsrfController.java
    └── test/java/com/example/stomp/
        └── InboundSecurityTest.java
~~~

Ví dụ sử dụng ba user demo `alice`, `bob`, `carol`. Trong `ChatPolicy`, chỉ cặp Alice ↔ Bob có quyền nhắn tin; Carol đã xác thực nhưng không được gửi tới Bob. Đây là fixture học tập, không phải hệ thống quản lý quan hệ bạn bè/nhóm sản xuất.

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>secure-stomp-inbox</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot parent quản lý phiên bản tương thích của WebSocket, Spring Messaging và Spring Security. Trong dự án này không cần thêm version cho từng `spring-security-*`. Với Boot 3/Spring Framework 6 cần JDK 17+.

### 4.2. `StompApplication.java`

~~~java
package com.example.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompApplication.class, args);
    }
}
~~~

Đặt các class trong package `com.example.stomp` giúp `@SpringBootApplication` tự quét cấu hình, controller và service.

### 4.3. `HttpSecurityConfig.java` — đăng nhập trước handshake

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain httpChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .requestMatchers("/ws", "/csrf").authenticated()
                    .anyRequest().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER").build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("carol123"))
                .roles("USER").build();
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }
}
~~~

Mẫu dùng **form login + HTTP session** vì browser có thể đưa cookie session từ phiên login vào WebSocket handshake. Đây là tài khoản demo cục bộ; không hardcode credential trong production. HTTP chain yêu cầu authentication cho `/ws` và `/csrf`. Cần dùng HTTPS/WSS khi triển khai thật.

Đoạn code không disable CSRF toàn ứng dụng. Người dùng đã login lấy token từ endpoint `GET /csrf` rồi đặt nó vào **STOMP CONNECT headers** như mục 5. HTTP CSRF và STOMP CSRF là hai nơi kiểm tra có thời điểm khác nhau.

### 4.4. `WebSocketConfig.java` — phân tách broker/app/user prefixes

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry endpoints) {
        // Mặc định chỉ cho origin phù hợp, không dùng allowedOriginPatterns("*").
        endpoints.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`enableSimpleBroker("/queue")` tạo broker in-memory, phù hợp minh họa một instance, **không phải hàng đợi bền vững hay hệ thống liên node**. Đừng đặt broker prefix `/app`, vì client `SEND /app/...` phải được xử lý bởi server controller. Không mở origin bằng wildcard khi sử dụng cookie/session; nếu frontend chạy trên origin khác, cấu hình danh sách origin cụ thể và xem xét cookie/CORS/CSRF theo mô hình thật.

### 4.5. `InboundSecurityConfig.java` — chính sách SEND và SUBSCRIBE

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketSecurity
public class InboundSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT/DISCONNECT/UNSUBSCRIBE không có destination.
            .nullDestMatcher().authenticated()
            // Chỉ SEND vào application endpoint đã xét duyệt.
            .simpMessageDestMatchers("/app/chat/send").hasRole("USER")
            // Chỉ cho subscribe user-relative inbox của chính session.
            .simpSubscribeDestMatchers("/user/queue/inbox").hasRole("USER")
            // Những SEND/SUBSCRIBE khác đều bị chặn, kể cả /queue/**.
            .simpTypeMatchers(
                    SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                .denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

**Ý nghĩa:** một frame `SUBSCRIBE /user/queue/inbox` hợp lệ chỉ khi authentication có `ROLE_USER`. Frame `SUBSCRIBE /queue/inbox`, `SUBSCRIBE /user/bob/queue/inbox`, `SEND /queue/inbox`, `SEND /user/queue/inbox` hoặc `SEND /topic/system` không khớp hai allow-rule nên bị `denyAll`. Việc chặn `MESSAGE` (SEND) ngoài application destination là cách tránh client giả danh server để đẩy tin vào broker.

`nullDestMatcher().authenticated()` bao phủ các message không có destination, ví dụ `CONNECT` và `DISCONNECT`; với `@EnableWebSocketSecurity`, Spring Security còn kiểm CSRF cho `CONNECT`. Đây là hai yêu cầu **khác nhau**: authentication hợp lệ không làm CSRF token trở nên không cần thiết khi sử dụng bảo vệ này.

Chú ý `simpMessageDestMatchers` và `simpSubscribeDestMatchers` không dùng thay cho business policy. Mọi tài khoản role USER đều có quyền **gọi handler** và **đăng ký inbox riêng**; quyền gửi tới một recipient cụ thể sẽ được kiểm ở controller/service sau đó.

### 4.6. `ChatPolicy.java` — quyền gửi đến đúng đối tượng

~~~java
package com.example.stomp;

import org.springframework.stereotype.Service;

@Service
public class ChatPolicy {

    public boolean canSend(String sender, String recipient) {
        // Fixture học tập: chỉ Alice và Bob được nhắn cho nhau.
        // Production: truy vấn membership/tenant/block/ACL từ nguồn tin cậy.
        return ("alice".equals(sender) && "bob".equals(recipient))
                || ("bob".equals(sender) && "alice".equals(recipient));
    }
}
~~~

Trong ứng dụng thật, chính sách phải dựa vào quan hệ conversation và tenant trong database, có kiểm tra owner, trạng thái khóa/block và quyền mới nhất. Không dùng allowlist hardcoded ở production; mục tiêu của fixture là chứng minh **Carol có ROLE_USER vẫn không thể gửi tin cho Bob** chỉ nhờ sửa JSON.

### 4.7. `ChatController.java` — lấy sender từ Principal

~~~java
package com.example.stomp;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record SendRequest(String to, String body) {}
    public record InboxMessage(String from, String body) {}

    private final ChatPolicy policy;
    private final SimpMessagingTemplate template;

    public ChatController(ChatPolicy policy, SimpMessagingTemplate template) {
        this.policy = policy;
        this.template = template;
    }

    @MessageMapping("/chat/send")
    public void send(SendRequest command, Principal principal) {
        if (principal == null) {
            throw new AccessDeniedException("Authentication required");
        }
        if (command == null || command.to() == null
                || command.body() == null
                || command.body().isBlank()
                || command.body().length() > 500) {
            throw new IllegalArgumentException("Invalid chat request");
        }

        String sender = principal.getName();
        if (!policy.canSend(sender, command.to())) {
            throw new AccessDeniedException("Recipient not allowed");
        }

        // Server quyết định from và đích /user/{recipient}/...
        template.convertAndSendToUser(
                command.to(), "/queue/inbox",
                new InboxMessage(sender, command.body()));
    }
}
~~~

Khi client gửi `SEND /app/chat/send`, application prefix `/app` được loại bỏ trước khi Spring tìm `@MessageMapping("/chat/send")`. Khi Bob subscribe `/user/queue/inbox`, Spring chuyển message vào destination gắn với session Bob. Người gửi **không** được tự khai `from` đáng tin: `InboxMessage.from` lấy từ Principal.

Kiểm tra `body.isBlank()` và độ dài chỉ là validation cơ bản. Ở production, còn cần giới hạn kích thước frame, rate limit, chống spam, xử lý nội dung khi render HTML, audit và lưu trữ/thông báo khi người nhận offline. Đừng đưa user-provided body trực tiếp vào `innerHTML` ở frontend; hiển thị như văn bản hoặc qua sanitizer đã kiểm định.

Nếu nghiệp vụ gửi tới một **hội thoại nhiều thành viên**, server nên dùng `conversationId` để tra thành viên và phân phối đến tập user được phép nhận, thay vì cho client tự chỉ định bất kỳ username nào. Với thao tác ghi database, kiểm lại quyền bên trong transaction phù hợp nếu có nguy cơ thay đổi membership giữa check và write.

### 4.8. `CsrfController.java` — cung cấp CSRF token cho STOMP CONNECT

~~~java
package com.example.stomp;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        // Chỉ người đã đăng nhập truy cập do HTTP chain bảo vệ /csrf.
        return csrfToken;
    }
}
~~~

Trong kịch bản session/cookie cùng origin, client gọi `GET /csrf` sau khi login. Endpoint chỉ trả token cho session đã được xác thực; không ghi token ra log. Nếu session/cookie thay đổi, frontend cần lấy token tương ứng với session mới. Không dùng endpoint CSRF public với cấu hình cookie/origin không an toàn.

## 5. Client JavaScript: SUBSCRIBE inbox và SEND tới ứng dụng

Đây là **fragment frontend** sử dụng gói `@stomp/stompjs` (cần cài bằng package manager và bundle vào trang chạy **cùng origin** với ứng dụng). Trước khi chạy, mở trang login Spring, đăng nhập bằng một tài khoản demo, sau đó thực thi code trong app frontend đã được bundle. Khi dùng HTTPS, browser sẽ dùng WSS.

~~~javascript
import { Client } from "@stomp/stompjs";

async function openPersonalInbox() {
    const response = await fetch("/csrf", {
        credentials: "same-origin"
    });
    if (!response.ok) {
        throw new Error("Login before connecting STOMP");
    }
    const csrf = await response.json();

    const secure = window.location.protocol === "https:";
    const scheme = secure ? "wss://" : "ws://";

    const client = new Client({
        brokerURL: scheme + window.location.host + "/ws",
        connectHeaders: {
            [csrf.headerName]: csrf.token
        },
        reconnectDelay: 5000,
        onConnect: () => {
            // Mỗi user đăng ký CÙNG một đường dẫn user-relative.
            client.subscribe("/user/queue/inbox", frame => {
                const event = JSON.parse(frame.body);
                // Render event.from và event.body như text, tránh innerHTML.
                console.log("From", event.from, ":", event.body);
            });
        },
        onStompError: frame => {
            console.error("STOMP broker error:", frame.headers["message"]);
        }
    });

    client.activate();
    return client;
}

function sendToBob(client) {
    // Gọi khi kết nối đã CONNECTED; phía server xác nhận recipient.
    client.publish({
        destination: "/app/chat/send",
        body: JSON.stringify({
            to: "bob",
            body: "Chào Bob"
        })
    });
}
~~~

Tài khoản Bob cần mở **một session đăng nhập riêng** và subscribe cùng `/user/queue/inbox` để nhận. Alice gọi `sendToBob(client)` sau sự kiện `onConnect`. Trong ứng dụng thật, tránh phát tin trong lúc `client.connected` là false, có cơ chế xác nhận gửi, xử lý reconnect và gửi lại an toàn để không tạo message trùng.

**Không gửi STOMP header giả dạng `user` hay `login` để server “tin” sender.** Chính sách dùng Principal từ HTTP/session. Với OAuth2/JWT trên WebSocket, phải có cơ chế xác thực riêng được triển khai và test; `connectHeaders.Authorization` không tự được Spring Security xác thực nếu không có interceptor/token processor phù hợp.

### Các frame STOMP nên hình dung

~~~text
# Người dùng đã xác thực kết nối, gửi CSRF header hợp lệ.
CONNECT
accept-version:1.2
host:localhost
X-CSRF-TOKEN:<token-cua-session>

# Bob hoặc Alice đăng ký inbox của CHÍNH MÌNH.
SUBSCRIBE
id:inbox-1
destination:/user/queue/inbox

# Alice gửi request, không gửi trực tiếp vào broker queue.
SEND
destination:/app/chat/send
content-type:application/json

{"to":"bob","body":"Chào Bob"}
~~~

Các dòng này chỉ minh họa **cấu trúc frame**, chưa hiển thị byte kết thúc frame STOMP (`NUL`) và chưa thay thế client library. Tên CSRF header lấy từ response `/csrf`, không mặc định hardcode `X-CSRF-TOKEN` trong mọi cấu hình.

## 6. Kiểm thử chính sách inbound bằng JUnit 5

Unit/integration context test dưới đây kiểm trực tiếp `AuthorizationManager<Message<?>>` của chính cấu hình trên, không cần mở socket thật. Nó chứng minh **loại frame + destination + role** được chấp nhận hoặc từ chối đúng. Để chứng minh giao tin thực qua WebSocket, cần thêm test/harness hai session ở mục 7.

Tạo file `src/test/java/com/example/stomp/InboundSecurityTest.java`:

~~~java
package com.example.stomp;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class InboundSecurityTest {

    @Autowired AuthorizationManager<Message<?>> manager;
    @Autowired ChatPolicy policy;

    private Authentication user(String name) {
        return new TestingAuthenticationToken(
                name, "unused", "ROLE_USER");
    }

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "demo-key", "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private boolean granted(SimpMessageType type,
                            String destination,
                            Authentication authentication) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            accessor.setDestination(destination);
        }
        Message<byte[]> message = MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
        AuthorizationDecision decision =
                manager.check(() -> authentication, message);
        return decision != null && decision.isGranted();
    }

    @Test
    void authenticatedUserCanSendToApplicationHandler() {
        assertTrue(granted(SimpMessageType.MESSAGE,
                "/app/chat/send", user("alice")));
    }

    @Test
    void clientCannotSendDirectlyToBrokerQueue() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/queue/inbox", user("alice")));
    }

    @Test
    void clientCannotSendToFakeSystemTopic() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/topic/system", user("alice")));
    }

    @Test
    void userCanSubscribeToOwnRelativeInbox() {
        assertTrue(granted(SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox", user("bob")));
    }

    @Test
    void userCannotSubscribeDirectlyToBrokerQueue() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/queue/inbox", user("alice")));
    }

    @Test
    void userCannotPutOtherUsernameInSubscribeDestination() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/user/bob/queue/inbox", user("alice")));
    }

    @Test
    void otherSubscriptionsAreDeniedByDefault() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/topic/private", user("bob")));
    }

    @Test
    void anonymousCannotSubscribeToPrivateInbox() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox", anonymous()));
    }

    @Test
    void anonymousCannotSendToApplicationHandler() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/app/chat/send", anonymous()));
    }

    @Test
    void connectRequiresAuthenticationInMessagePolicy() {
        assertTrue(granted(SimpMessageType.CONNECT,
                null, user("alice")));
        assertFalse(granted(SimpMessageType.CONNECT,
                null, anonymous()));
    }

    @Test
    void aliceAndBobCanChatButCarolIsDeniedByBusinessPolicy() {
        assertTrue(policy.canSend("alice", "bob"));
        assertTrue(policy.canSend("bob", "alice"));
        assertFalse(policy.canSend("carol", "bob"));
        assertFalse(policy.canSend("alice", "carol"));
    }
}
~~~

Chạy dự án từ thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** 11 test JUnit 5 thành công nếu dependency và runtime phù hợp. Cụ thể, test kiểm các decision của `AuthorizationManager` và bean `ChatPolicy`; **không** tự xác minh HTTP login, token CSRF STOMP `CONNECT`, handshake, broker delivery, trạng thái ngắt kết nối hay phân phối qua nhiều instance.

Các test được viết theo Spring Security 6.x, dùng `AuthorizationManager.check(...)`, trả `AuthorizationDecision`. Nếu nâng lên API khác, cần rà soát những deprecation tương ứng mà không bỏ nội dung kiểm thử. `TestingAuthenticationToken` là fixture cho policy test; nó **không phải bằng chứng** Spring đã xác thực thành công WebSocket handshake của người dùng thật.

### Một test quan trọng thường bị thiếu

Nếu chỉ assert `SUBSCRIBE /user/queue/inbox` được cấp quyền, bạn mới chứng minh **request đăng ký dạng tương đối** được phép. Chưa chứng minh Bob thực sự nhận còn Alice/Carol không nhận message dành cho Bob. Cần một bài test có hai session authenticated khác nhau, cùng đăng ký `/user/queue/inbox`, sau đó server gửi message và kiểm **tập session nhận**. Đây là nơi dễ phát hiện lỗi dùng sai Principal name, broker prefix hoặc cấu hình user destination.

## 7. Kịch bản kiểm thử tích hợp hai tài khoản

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Tạo hai phiên trình duyệt tách cookie/session (ví dụ cửa sổ thường + private browsing hoặc hai profile khác nhau):

1. **Bob** đăng nhập ở `http://localhost:8080/login` bằng tài khoản demo `bob / bob123`. Trang cùng origin gọi `GET /csrf`, mở `ws://localhost:8080/ws`, gửi STOMP `CONNECT` với token, rồi `SUBSCRIBE /user/queue/inbox`.
2. **Alice** đăng nhập ở phiên khác bằng `alice / alice123`, kết nối STOMP theo cách tương tự, subscribe inbox cá nhân, rồi gửi `SEND /app/chat/send` có body `{"to":"bob","body":"hello"}`.
3. Quan sát Bob nhận message `{"from":"alice","body":"hello"}`. Alice **không tự nhận** tin đó trừ khi server có logic gửi bản sao cho sender; example này không làm vậy.
4. Thử Alice `SUBSCRIBE /queue/inbox` hoặc `/user/bob/queue/inbox`. Kỳ vọng subscription bị chặn. Ứng dụng có thể gửi `ERROR` và/hoặc đóng socket, tùy cách xử lý exception; **không** khẳng định một HTTP 403 cụ thể vì request đã vào STOMP.
5. **Carol** đăng nhập với `carol / carol123` rồi thử `SEND /app/chat/send` tới Bob. Destination được phép đối với ROLE_USER, nhưng `ChatPolicy` phải từ chối giao tin. Bob **không** được nhận message từ Carol.
6. Thử `SEND /topic/system` hoặc `SEND /queue/inbox` từ Alice; frame phải bị từ chối trước khi được broker phát ra.
7. Mở thêm session thứ hai của Bob và subscribe; theo mặc định, `convertAndSendToUser("bob",...)` có thể gửi tới **các session Bob đang subscribe**. Kiểm lại cả hai session nhận; khi Bob logout hoặc session hết hạn, kiểm chính sách cắt kết nối và quyền còn hiệu lực.
8. Gửi STOMP `CONNECT` thiếu hoặc sai CSRF token; kết nối phải bị từ chối theo cấu hình `@EnableWebSocketSecurity`, dù HTTP session đã đăng nhập.
9. Dùng một origin không nằm trong allowlist để thử handshake; xác nhận bị chặn theo cấu hình origin. Test này cần môi trường thực vì test unit ở mục 6 không mô phỏng trình duyệt/WebSocket network.

Để kiểm chứng **không rò tin**, không chỉ xác nhận Bob nhận được: xác nhận Alice và Carol không nhận sự kiện có `from="alice"` gửi tới Bob qua subscription khác. Nếu có durable inbox/database, kiểm thêm rằng Carol không thể đọc lịch sử hội thoại của Alice/Bob từ REST API hoặc chức năng replay.

### Ma trận mong đợi

| Actor | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Alice đã login | `SEND /app/chat/send` tới Bob | Cho phép về channel; business policy cho phép |
| Bob đã login | `SUBSCRIBE /user/queue/inbox` | Cho phép; nhận tin đúng session |
| Carol đã login | `SUBSCRIBE /user/queue/inbox` | Cho phép **inbox của Carol**, không phải của Bob |
| Alice đã login | `SUBSCRIBE /user/bob/queue/inbox` | Từ chối |
| Alice đã login | `SUBSCRIBE /queue/inbox` | Từ chối |
| Alice đã login | `SEND /queue/inbox` | Từ chối |
| Alice đã login | `SEND /topic/system` | Từ chối |
| Carol đã login | `SEND /app/chat/send` tới Bob | Channel cho phép; business policy từ chối |
| Anonymous | `SEND /app/chat/send` | Từ chối |
| Anonymous | `SUBSCRIBE /user/queue/inbox` | Từ chối |
| Alice có session nhưng sai CSRF | STOMP `CONNECT` | Từ chối |
| Bob có hai session | Server gửi tới user Bob | Các session Bob có đăng ký được nhận theo cấu hình mặc định |

Nếu bài test chỉ kiểm HTTP status từ handshake, bạn chưa chứng minh quyền `SEND`/`SUBSCRIBE` của từng STOMP frame. Hai tầng có mục đích khác nhau và nên được kiểm riêng.

## 8. Vì sao `@SendToUser` và `convertAndSendToUser` không đủ nếu cấu hình sai?

### `@SendToUser`: trả lời user gắn với message vào

Một controller có thể trả kết quả cho người gửi:

~~~java
// Fragment: đặt trong @Controller có @MessageMapping phù hợp.
@MessageMapping("/profile/ping")
@SendToUser(value = "/queue/replies", broadcast = false)
public Reply ping(Principal principal) {
    return new Reply(principal.getName(), "pong");
}
~~~

Fragment này cần khai báo `Reply`, imports và cho phép `SEND /app/profile/ping`, `SUBSCRIBE /user/queue/replies` trong policy. `broadcast=false` hướng câu trả lời tới **session đang gọi** thay vì tất cả session cùng user. Nó phù hợp cho receipt/error riêng, nhưng không thay thế kiểm tra payload và quyền thực thi ở handler.

### `convertAndSendToUser`: chủ động gửi tới user được chỉ định

~~~java
// Fragment trong Spring service có SimpMessagingTemplate.
template.convertAndSendToUser(
        verifiedRecipientId,
        "/queue/inbox",
        new InboxMessage(authenticatedSenderId, sanitizedText));
~~~

Cần bảo đảm `verifiedRecipientId` trùng cách Spring đặt `Principal#getName()` của session được kết nối, và recipient thực sự được phép nhận thông điệp. Nếu nhận `verifiedRecipientId` trực tiếp từ body client mà **không qua policy**, code này chỉ chuyển sai lầm authorization sang server-side.

**Nhận riêng không đồng nghĩa ẩn tuyệt đối:** Destination riêng chỉ ngăn user khác subscribe nhầm trong mô hình Spring đã cấu hình đúng. Nếu bạn cho phép `SUBSCRIBE /queue/**`, đặt broker relay mở ra Internet không có ACL, hoặc gửi cùng payload chứa bí mật lên `/topic/**`, user destination không cứu được dữ liệu đã phát sai.

## 9. CSRF, Origin, session và JWT

### 9.1. Vì sao handshake và STOMP CONNECT khác nhau?

Browser không áp dụng chính sách same-origin cho WebSocket theo cách giống fetch/XHR, nên ứng dụng phải giới hạn allowed origins và có lớp chống cross-site WebSocket hijacking khi dùng cookie. `@EnableWebSocketSecurity` trong mô hình Servlet mặc định yêu cầu **CSRF token trên frame STOMP `CONNECT`**.

Nhớ hai mốc:

- HTTP GET/Upgrade tới `/ws`: HTTP filter chain xử lý authentication và các chính sách handshake.
- STOMP `CONNECT` sau khi socket mở: Spring Security Messaging kiểm authentication và CSRF token trên STOMP headers trước khi cho giao tiếp.

Một request GET thành công với 101 Switching Protocols **không chứng minh** STOMP CONNECT đã được chấp nhận. Nếu client dùng SockJS fallback có POST/iframe, cần xử lý HTTP CSRF exception **cục bộ cho endpoint SockJS phù hợp** và vẫn duy trì CSRF trên STOMP CONNECT; không tắt CSRF toàn ứng dụng chỉ để sửa lỗi fallback. Mẫu này dùng WebSocket thuần nên không thêm SockJS và không cần vô hiệu hóa HTTP CSRF cho endpoint.

### 9.2. Session/logout và kết nối còn mở

HTTP session authentication được chụp tại handshake. Khi user bị khóa tài khoản hoặc thu hồi quyền, **không nên giả định** WebSocket đang mở sẽ tự ngắt hoặc mọi `AuthorizationManager` sẽ tự tải lại authority từ database. Cần chính sách: đóng session WebSocket tương ứng, refresh Authentication/kiểm quyền động trong handler, và kiểm revocation trong mọi thao tác nhạy cảm.

Với session stateful, quy trình “logout tất cả thiết bị” có thể cần vô hiệu hóa HTTP session **và** cắt các WebSocket session đang hoạt động ở nhiều node; test cả case socket kết nối trước thời điểm revoke.

### 9.3. JWT/OAuth2 Resource Server

Nếu frontend dùng access token thay cho cookie/session, cần xác định chính xác **điểm xác thực** token khi mở socket hoặc ở STOMP CONNECT. Với token trong STOMP headers, một `ChannelInterceptor` tùy chỉnh có thể giải mã, kiểm issuer/audience/expiry và set authenticated user vào headers theo API Spring Messaging thích hợp. Cần đăng ký interceptor **đúng thứ tự** trước authorization interceptor, kiểm lỗi token, bảo đảm không trust `login`/`user` tùy ý và kiểm reauthentication/revocation khi token hết hạn.

Spring Security không tự áp dụng JWT bearer authentication chỉ vì client gửi `Authorization` trong STOMP `CONNECT` headers. Đừng làm mẫu token bằng cách parse username chưa xác minh chữ ký. Với bearer token độc lập, CSRF/cross-origin và credential transport có threat model khác; đừng sao chép cấu hình session vào API stateless mà không kiểm chứng.

## 10. Broker relay, nhiều instance và tính riêng tư

Mẫu ở mục 4 dùng simple broker in-memory. Khi chạy nhiều application instances sau load balancer, các vấn đề mới xuất hiện:

- Bob có socket ở instance B, nhưng Alice gửi vào instance A. Simple broker cục bộ của A có thể **không biết** session Bob ở B và tin không đến nơi.
- Khi dùng **STOMP broker relay** (RabbitMQ/ActiveMQ), phải bảo vệ credential/ACL giữa ứng dụng và broker; không cho client bên ngoài đăng nhập trực tiếp broker rồi subscribe mọi queue.
- Spring có cơ chế `userDestinationBroadcast` để broadcast user destination chưa giải quyết nhằm hỗ trợ tìm session ở node khác, tùy cách triển khai. Cũng cần xem `userRegistryBroadcast`/registry phù hợp cho multi-node khi có yêu cầu.
- Physical queue per user/session phải có vòng đời/cleanup phù hợp; broker khác nhau có cơ chế auto-delete khác nhau.
- Ngắt kết nối/reconnect có thể tạo session mới hoặc mất notification chưa delivery. User destination không cung cấp mặc định **lưu trữ offline, exactly-once delivery hoặc thứ tự toàn cục**.

Nếu thông điệp nhạy cảm, lưu bản ghi đã được phân quyền trong database/queue bền vững theo chính sách và dùng STOMP chỉ làm tín hiệu realtime; khi user tải lịch sử, **authorization vẫn phải kiểm tra** người nhận/tenant/conversation. Đừng coi việc biết một destination string là đủ chứng minh có quyền truy cập dữ liệu đó.

## 11. Lỗi phổ biến và phương pháp phát hiện

**Lỗi 1: Cho client `SUBSCRIBE /queue/**`.** Điều này có thể cho user tham gia broker destination chứa dữ liệu người khác. Chỉ cho phép user-relative `/user/queue/inbox` hoặc các topic đã xét quyền, từ chối subscription trực tiếp tới physical queue.

**Lỗi 2: Cho client `SEND /topic/**` hoặc `SEND /queue/**`.** Người dùng có thể giả mạo thông báo hệ thống, thậm chí tự gửi dữ liệu vào inbox của người khác. Chỉ cho `SEND` tới `/app/**` đã cho phép và dùng controller/service để phát về broker.

**Lỗi 3: So khớp `simpDestMatchers("/user/**").permitAll()` quá rộng.** Quy tắc này có thể cho phép cả loại frame MESSAGE lẫn SUBSCRIBE trên nhiều path. Dùng `simpSubscribeDestMatchers` và `simpMessageDestMatchers` để chỉ định rõ frame type.

**Lỗi 4: Nhận `from`/`owner` từ JSON.** Client có thể tự nhận là Bob. Dùng authenticated `Principal`, và kiểm recipient/conversation membership từ nguồn server-side.

**Lỗi 5: Nghĩ rằng WebSocket handshake authentication là đủ.** Một socket đã login vẫn có thể thử destination khác hoặc thay recipient trong payload. Kiểm từng inbound message và chính sách nghiệp vụ.

**Lỗi 6: Nhầm 101/HTTP 403 với kết quả STOMP.** Handshake thành công không có nghĩa CONNECT/SUBSCRIBE hợp lệ. Việc từ chối frame ở messaging layer không nhất thiết tạo HTTP 403, có thể là STOMP ERROR/close. Test hai lớp riêng.

**Lỗi 7: Tắt CSRF toàn bộ vì CONNECT không qua.** Với cookie session, cross-site socket hijacking là mối nguy thực. Lấy CSRF token của session gửi trong STOMP CONNECT; kiểm allowed origins. Nếu dùng SockJS, chỉ mở ngoại lệ phù hợp cho HTTP fallback theo tài liệu.

**Lỗi 8: Không kiểm role và tenant thực của recipient.** `hasRole("USER")` cho phép gọi handler, nhưng không chứng minh Alice được nhắn với người bất kỳ. Thêm check conversation membership, blocklist, tenant, và các quyền theo tài nguyên.

**Lỗi 9: Assume user destination gửi tới đúng một tab.** Theo mặc định một user có thể có nhiều session, đều có thể nhận khi subscribe. Dùng `@SendToUser(broadcast=false)` khi mục tiêu là response cho session hiện tại; thiết kế quy tắc multi-device riêng cho hệ thống thực.

**Lỗi 10: Phụ thuộc một instance/local broker.** Khi người nhận kết nối node khác, message có thể mất. Thử giao tiếp cross-node, broker relay, user registry và thời gian reconnect.

**Lỗi 11: Không làm sạch queue/session sau logout.** Session cũ, stale subscriptions và backend broker có thể giữ resource hoặc thông điệp. Đặt lifecycle và retention phù hợp.

**Lỗi 12: Rò thông tin qua log và payload.** Không log CSRF token, raw JWT, session ID, private payload. Từ chối với thông báo đủ dùng nhưng không tiết lộ recipient có tồn tại hay không nếu đây là thông tin nhạy cảm.

## 12. Checklist nghiệm thu

- [ ] HTTP WebSocket handshake yêu cầu authentication; origin list phù hợp, HTTPS/WSS ở production.
- [ ] STOMP CONNECT xác minh CSRF token khi dùng mô hình session theo `@EnableWebSocketSecurity`.
- [ ] Client SEND chỉ được vào application destination đã xét duyệt; mọi gửi trực tiếp tới broker đều bị chặn.
- [ ] Client SUBSCRIBE chỉ được vào user-relative destination cá nhân hoặc các topic đã xác định quyền.
- [ ] `/user/queue/inbox` được Spring ánh xạ theo session; client không tự chọn username của người khác trong path.
- [ ] Sender lấy từ authenticated Principal, không lấy từ header/payload do client cung cấp.
- [ ] Recipient/tenant/conversation được kiểm bởi business policy trước khi gửi.
- [ ] Không gửi payload nhạy cảm ra topic công khai hoặc physical queue client tự subscribe.
- [ ] Test cả anonymous, user đủ/thiếu quyền và frame type sai, destination gần giống, giả mạo sender.
- [ ] Test Alice → Bob thành công; Carol → Bob bị từ chối, Bob nhận và Alice/Carol không được nhận nhầm.
- [ ] Test CSRF CONNECT đúng/sai, origin sai, expired session và disconnect/reconnect.
- [ ] Khi nhiều instance, test sender/recipient ở node khác nhau, user destination resolution và broker ACL.
- [ ] Có chiến lược thu hồi quyền khi WebSocket còn sống, kiểm soát backlog/offline và audit.

## 13. Tài liệu chính thức

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — STOMP User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — STOMP Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — STOMP WebSocket Configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Security — `MessageMatcherDelegatingAuthorizationManager.Builder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security — WebSocket and SockJS CSRF: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html#websocket-same-origin

**Kết quả cần đạt:** Alice có thể gửi một command được server kiểm tra đến Bob; Bob subscribe user-relative inbox của chính mình và nhận đúng message. Các đường giả mạo người gửi, subscribe physical queue, SEND vào broker, gửi tới recipient không đủ quyền, kết nối chưa đăng nhập hoặc thiếu CSRF đều bị từ chối theo lớp bảo vệ tương ứng. Không kết luận thành công chỉ vì WebSocket mở hoặc chỉ vì một thông điệp đã được nhận.
