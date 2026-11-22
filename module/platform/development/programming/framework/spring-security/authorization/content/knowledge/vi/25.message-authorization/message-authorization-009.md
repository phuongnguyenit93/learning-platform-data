# Origin, CSRF trong STOMP CONNECT và quan hệ với kiểm soát truy cập

> Phạm vi: Spring Security trên Servlet stack, Spring WebSocket Messaging với STOMP over WebSocket (có thể có SockJS). Trọng tâm là bảo vệ điểm kết nối và **phân quyền từng thông điệp đến từ client**. WebSocket thuần không dùng STOMP, RSocket và WebFlux có cơ chế tích hợp khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt kiểm tra `Origin` tại WebSocket handshake, kiểm tra CSRF trong STOMP `CONNECT` và kiểm soát quyền của `SEND`/`SUBSCRIBE`.
- Giải thích vì sao kẻ tấn công có thể lợi dụng trình duyệt đã đăng nhập để tạo WebSocket trái ý người dùng (Cross-Site WebSocket Hijacking, CSWSH).
- Cấu hình bảo vệ WebSocket với `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>`, đồng thời truyền CSRF token qua STOMP header.
- Xây dựng policy theo **loại thông điệp + destination + danh tính/quyền người dùng**, và kiểm thử các trường hợp bị từ chối.

## 2. Ba lớp kiểm soát khác nhau

| Giai đoạn | Dữ liệu quan trọng | Cơ chế kiểm tra | Câu hỏi được trả lời |
| --- | --- | --- | --- |
| HTTP handshake, ví dụ `GET /ws` với `Upgrade: websocket` | Cookie/HTTP credentials, `Origin`, URL | Xác thực HTTP, kiểm tra origin do Spring WebSocket cấu hình | Trình duyệt từ nguồn này có thể mở transport không? Có nhận diện được người dùng không? |
| STOMP `CONNECT` đi **bên trong** transport | STOMP headers, trong đó có CSRF token | Spring Security kiểm tra token cho `CONNECT`; message authorization có thể yêu cầu `authenticated()` | Phiên STOMP được thiết lập với yêu cầu hợp lệ không? |
| STOMP `SEND` (Simp `MESSAGE`), `SUBSCRIBE` và các frame tiếp theo | `simpUser`, loại message, `destination` | `AuthorizationManager<Message<?>>` trên `clientInboundChannel` và kiểm tra nghiệp vụ | Người này được gửi/đăng ký đến đích này không? |

**Không có lớp nào thay thế đầy đủ lớp khác.** Một handshake hợp lệ chưa cấp mọi quyền cho mọi message. CSRF token hợp lệ chứng minh khả năng truy cập token trong bối cảnh được bảo vệ, **không** chứng minh quyền đọc topic bí mật hoặc thực hiện thao tác quản trị. Một người đã xác thực vẫn cần được phân quyền cho từng hành vi.

Luồng điển hình:

~~~text
Trình duyệt đã đăng nhập
  │
  ├─ 1. HTTP GET /ws + Cookie + Origin
  │       ├─ HTTP authentication / session
  │       └─ WebSocket allowed-origin check
  │                ↓
  ├─ 2. STOMP CONNECT + CSRF token trong STOMP header
  │       ├─ Kiểm tra CSRF của Spring Security
  │       └─ Kiểm tra quyền CONNECT theo message policy
  │                ↓
  ├─ 3. STOMP SUBSCRIBE /topic/updates
  │       └─ Policy: ai được theo dõi topic?
  │                ↓
  └─ 4. STOMP SEND /app/chat.send
          ├─ Policy: ai được gửi đến destination?
          └─ Handler: kiểm tra quyền trên phòng chat/đối tượng cụ thể
~~~

## 3. Origin: chặn nguồn trình duyệt không được phép

`Origin` mô tả nguồn của trang tạo yêu cầu (scheme + host + port), chẳng hạn `https://app.example.com`. Khác với nhiều yêu cầu `fetch`/XHR, **trình duyệt không tự áp dụng Same-Origin Policy để cấm JavaScript mở kết nối WebSocket đến origin khác**. Nếu server không kiểm tra, một trang độc hại có thể mở WebSocket tới ứng dụng người dùng đang đăng nhập; khi trình duyệt tự gửi cookie phiên theo chính sách cookie hiện hành, server có thể hiểu kết nối mang danh tính nạn nhân.

Spring Framework WebSocket/SockJS mặc định giới hạn **same-origin**. Ví dụ:

~~~java
// WsTransportConfig.java - một phần của ứng dụng Spring Boot
package example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WsTransportConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws"); // Giữ mặc định same-origin.
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Đây là **endpoint của handshake** `/ws`; nó không phải destination STOMP `/app/chat.send` hay `/topic/updates`. Khi frontend chạy ở origin được tin cậy khác với backend, có thể khai báo danh sách chính xác, ví dụ `registry.addEndpoint("/ws").setAllowedOrigins("https://app.example.com")`. Duy trì danh sách tối thiểu, dùng HTTPS/WSS và kiểm soát cookie/CORS phù hợp. Đừng dùng `*` chỉ để hết lỗi kết nối.

Giới hạn của `Origin`:

- Browser chuẩn tự đặt `Origin`, nên đây là tín hiệu quan trọng để chặn trang web lạ. **Client không phải browser có thể giả mạo `Origin`**; do đó đây không phải chứng thực danh tính.
- Allowed origins không kiểm tra dữ liệu STOMP, vai trò, tenant hay quyền truy cập tài nguyên.
- CORS của REST API và allowed-origin của WebSocket là các cấu hình khác nhau; mở CORS không đồng nghĩa cấp quyền WebSocket. Với SockJS fallback qua HTTP, còn cần kiểm tra hành vi CORS/transport tương ứng.
- Cookie `SameSite` là lớp hỗ trợ nhưng không nên là cơ chế phòng thủ duy nhất; hành vi gửi cookie còn phụ thuộc bối cảnh, trình duyệt và cách triển khai.

**Tình huống tấn công:** nạn nhân đăng nhập `chat.example.com`, sau đó mở `evil.example.net`. Trang độc gọi `new WebSocket("wss://chat.example.com/ws")`. Server phải từ chối origin lạ; nếu vô tình cho phép origin đó, lớp CSRF ở `CONNECT` vẫn cần ngăn trang không có token hợp lệ thiết lập phiên STOMP.

## 4. CSRF trên STOMP CONNECT: mục đích và cách truyền

CSRF (Cross-Site Request Forgery) xuất hiện khi trình duyệt tự đính kèm credentials như cookie vào yêu cầu mà kẻ tấn công khởi tạo. Spring Security WebSocket Messaging mặc định yêu cầu **CSRF token hợp lệ trong STOMP `CONNECT`** khi dùng `@EnableWebSocketSecurity`. Đây là cơ chế thực thi phòng vệ same-origin sâu hơn ở lớp STOMP.

Phân biệt hai yêu cầu:

1. `GET /ws` là HTTP handshake; các quy tắc bảo mật HTTP được áp dụng. Kiểm tra `Origin` diễn ra ở tầng WebSocket. CSRF của HTTP thường bảo vệ các phương thức thay đổi trạng thái (như POST), vì vậy **đừng giả định kiểm tra HTTP CSRF tại handshake GET đã bảo vệ STOMP CONNECT**.
2. Sau khi nâng cấp transport, client gửi STOMP frame `CONNECT`. Token phải nằm trong **STOMP native header**, không phải chỉ trong HTTP handshake header. Client JavaScript browser hoặc SockJS thường không có khả năng tùy ý đặt HTTP header ở handshake/transport, nhưng có thể đặt `connectHeaders` của STOMP.

Ví dụ frame (tên header theo cấu hình token của server):

~~~text
CONNECT
accept-version:1.2
host:chat.example.com
X-CSRF-TOKEN:<token-hop-le>

^@
~~~

Trong wire format STOMP, một frame kết thúc bằng **byte NUL (0x00)**; ký hiệu `^@` ở trên chỉ minh họa. Không hard-code chuỗi `<token-hop-le>`.

Một cách cấp token cho giao diện cùng origin là controller sau. Endpoint chỉ nên truy cập qua phiên/context hợp lệ; trình duyệt phải không thể đọc phản hồi này từ origin độc hại:

~~~java
// CsrfEndpoint.java
package example.chat;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfEndpoint {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

Client sử dụng `@stomp/stompjs` (minh họa cho trang cùng origin):

~~~javascript
import { Client } from "@stomp/stompjs";

const response = await fetch("/csrf", { credentials: "same-origin" });
if (!response.ok) {
  throw new Error("Không lấy được CSRF token: " + response.status);
}
const csrf = await response.json();

const client = new Client({
  brokerURL:
    (location.protocol === "https:" ? "wss://" : "ws://") +
    location.host + "/ws",
  connectHeaders: { [csrf.headerName]: csrf.token },
  onConnect: () => {
    client.subscribe("/topic/updates", (message) => {
      console.log(message.body);
    });
  },
  onStompError: (frame) => {
    console.error("STOMP bị từ chối:", frame.headers.message);
  }
});

client.activate();
~~~

Các thuộc tính JSON `headerName` và `token` lấy từ `CsrfToken`; đừng tự đoán tên header, vì cấu hình có thể khác. Đối với giao diện tách origin, cần thiết kế việc lấy token, credential và CORS riêng với allowlist chính xác; không cho phép origin không đáng tin cậy đọc `/csrf` bằng credential của nạn nhân. **Không đưa CSRF token vào URL/query string hoặc log.** Token có thể thay đổi sau login/logout hoặc khi phiên hết hạn; client phải lấy lại khi thích hợp.

**Quan hệ với phân quyền:** Một `CONNECT` có CSRF token đúng vẫn có thể bị từ chối nếu policy yêu cầu người dùng đã đăng nhập. Ngược lại, rule `CONNECT.permitAll()` hay `authenticated()` của message authorization **không tự vô hiệu hóa bước kiểm tra CSRF** mà `@EnableWebSocketSecurity` cài đặt.

## 5. Phân quyền inbound MESSAGE và SUBSCRIBE sau CONNECT

Spring Security kiểm tra các message đi từ client qua `clientInboundChannel`. Không nên suy luận rằng nó tự lọc mọi message outbound trên `clientOutboundChannel`: thông thường cần kiểm soát **quyền SUBSCRIBE** để giới hạn nơi người dùng nhận dữ liệu, kết hợp phân quyền ở handler và phía phát sự kiện.

Bài toán mẫu:

| Frame từ client | Destination | Chính sách ví dụ | Lý do |
| --- | --- | --- | --- |
| `CONNECT` | Không có destination | Đã xác thực + CSRF hợp lệ | Gắn phiên STOMP với user hợp lệ |
| `SUBSCRIBE` | `/topic/updates` | Đã xác thực | Chỉ đọc thông báo chung nội bộ |
| `SUBSCRIBE` | `/user/queue/alerts` | Đã xác thực | Nhận hàng đợi dành cho user hiện tại |
| `SEND` (Simp `MESSAGE`) | `/app/chat.send` | Đã xác thực; handler kiểm tra quyền phòng chat | Gửi yêu cầu vào ứng dụng |
| `SEND` | `/topic/updates` | Từ chối | Client không được giả mạo thông báo do server/broker phát |
| `SUBSCRIBE` | `/queue/**` hoặc topic chưa duyệt | Từ chối | Không đọc trực tiếp queue hoặc topic ngoài chính sách |

Triển khai bằng Spring Security `AuthorizationManager` (phù hợp Spring Security 6.x/7.x). Mỗi class dưới đây ở file trùng tên; kết hợp với `WsTransportConfig` đã giới thiệu:

~~~java
// WsMessageAuthorizationConfig.java
package example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WsMessageAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .simpTypeMatchers(
                SimpMessageType.CONNECT,
                SimpMessageType.DISCONNECT,
                SimpMessageType.UNSUBSCRIBE
            ).authenticated()
            .simpSubscribeDestMatchers("/topic/updates").authenticated()
            .simpSubscribeDestMatchers("/user/queue/alerts").authenticated()
            .simpMessageDestMatchers("/app/chat.send").authenticated()
            .simpTypeMatchers(
                SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Giải thích chính xác:

- `simpTypeMatchers` chọn theo loại message; `simpMessageDestMatchers` chỉ khớp Simp `MESSAGE`, còn `simpSubscribeDestMatchers` chỉ khớp `SUBSCRIBE`. **Đừng dùng `simpDestMatchers` không giới hạn loại nếu chính sách gửi và đăng ký cần khác nhau.**
- Các rule được xét theo thứ tự; đặt ngoại lệ được cấp quyền **trước** `denyAll`. Dấu `/app` định tuyến message vào `@MessageMapping`, còn `/topic`/`/queue` là broker destinations trong ví dụ.
- `authenticated()` ở `CONNECT` dựa trên Principal được gắn vào WebSocket session từ HTTP authentication trong mô hình thông thường. Nếu cho phép anonymous kết nối để đọc dữ liệu công khai, hãy thiết kế lại rõ ràng cả policy lẫn CSRF.
- `/user/queue/alerts` là user destination phía client; server ánh xạ tới destination cụ thể cho phiên. Không mở quyền `SUBSCRIBE` trực tiếp lên `/queue/**`.
- `denyAll` cuối bảo đảm những message/destination chưa xét không được tự động cho phép. Nếu ứng dụng cần heartbeat, receipt hoặc kiểu frame khác, hãy bổ sung policy có chủ đích và kiểm thử.

Để luồng HTTP dùng session login, ứng dụng còn cần `SecurityFilterChain` phù hợp: xác thực trang/HTTP endpoint, bảo vệ `/csrf` và `/ws`, giữ HTTP CSRF cho các thao tác thay đổi trạng thái. Việc có message authorization bean **không tạo ra cơ chế đăng nhập HTTP**. Trong mô hình session/cookie thông thường, Spring WebSocket chuyển `Principal` từ request handshake sang các STOMP message; các STOMP header `login`/`passcode` không tự được Spring dùng để đăng nhập.

Các ví dụ Java ở trên yêu cầu project Spring Boot tương ứng (Java 17+, dependency Spring WebSocket Messaging, Spring Security web và `spring-security-messaging`); đây là các class cấu hình trong một ứng dụng, **không phải chương trình Java độc lập có thể chạy bằng `javac` không kèm dependency**. Đừng suy diễn stdout từ các cấu hình này; hiệu quả được kiểm tra bằng kết nối và các quyết định cho phép/từ chối.

### Vì sao handler còn phải kiểm tra quyền nghiệp vụ?

Rule cho `/app/chat.send` chỉ cho thấy người dùng đã đăng nhập và được gọi destination đó. Payload có thể chứa `roomId=42`; handler phải xác nhận user thực sự là thành viên của phòng 42, giới hạn tenant, loại thao tác và kiểm tra dữ liệu đầu vào. Không tin `senderId`, `role` hoặc `tenantId` do client gửi thay cho `Principal` được xác thực.

Ví dụ logic handler ở mức ý tưởng:

~~~text
SEND /app/chat.send  {roomId: 42, text: "Xin chào"}
  → xác thực user từ Principal của phiên
  → tra tư cách thành viên room 42 ở server
  → từ chối nếu không phải thành viên
  → lưu/gửi thông điệp nếu hợp lệ
~~~

Mẫu trên chỉ mô tả nghiệp vụ; không phải Java source độc lập. Với topic theo tài nguyên, như `/topic/rooms/42`, ngay cả quyền `SUBSCRIBE` cũng cần kiểm tra quyền trên room 42, thay vì chỉ dùng `authenticated()`.

## 6. SockJS: phân biệt HTTP CSRF với STOMP CSRF

SockJS có thể dùng fallback transport qua HTTP POST. Các POST này đi qua `CsrfFilter` của tầng HTTP, trong khi JavaScript SockJS không dễ gửi token qua HTTP header của từng fallback request. Nếu ứng dụng **thật sự bật** `withSockJS()` và cần fallback, tài liệu Spring Security hướng dẫn bỏ qua **HTTP CSRF cho đúng URL transport SockJS**, nhưng vẫn giữ kiểm tra CSRF trong STOMP `CONNECT`. Đây là hai lớp khác nhau.

Ví dụ tùy chọn cho một endpoint `/ws` dùng SockJS, trong cấu hình HTTP của ứng dụng:

~~~java
// Đoạn cấu hình bên trong SecurityFilterChain (tùy chọn khi có SockJS).
http.csrf(csrf -> csrf.ignoringRequestMatchers("/ws/**"));
~~~

- Đoạn trên **không cần áp dụng mặc định** cho WebSocket thuần khi chưa gặp nhu cầu SockJS fallback.
- Chỉ bỏ qua HTTP CSRF đối với transport path chính xác (ở đây `/ws/**`); không gọi `csrf.disable()` cho toàn website.
- STOMP `CONNECT` vẫn cần token trong STOMP header và vẫn được Spring Security kiểm tra. Nếu cùng endpoint còn phục vụ HTTP API có thể thay đổi trạng thái, hãy tách path và rà soát lại phạm vi bỏ qua.
- Một số fallback dùng iframe; nếu ứng dụng cần chúng, có thể phải đặt `X-Frame-Options: SAMEORIGIN` thay vì DENY, với phạm vi an toàn phù hợp. Không nới lỏng framing khi không cần.

Không nên tắt CSRF của WebSocket chỉ để kết nối thành công. Nếu lựa chọn kiến trúc thật sự không dùng cookie và xác thực bằng bearer token gửi chủ động ở STOMP `CONNECT`, phải đánh giá lại threat model, cách đặt Principal trước security interceptor và tính tương thích phiên bản. Khi sử dụng custom token interceptor, Spring Framework lưu ý cần đảm bảo interceptor xác thực chạy **trước** Spring Security message authorization. Đừng coi đoạn cấu hình cookie/session ở bài này là ví dụ hoàn chỉnh cho JWT.

## 7. Những trường hợp nên và không nên được phép

Giả sử người dùng Alice đã đăng nhập, origin hợp lệ, client lấy được CSRF token mới:

1. **Đúng origin + session hợp lệ + token đúng + `CONNECT`**: qua các lớp kiểm tra, tiếp tục đến quy tắc message.
2. **Origin lạ**: handshake bị từ chối dù browser có thể tự gửi cookie; không đợi đến lúc SUBSCRIBE mới chặn.
3. **Origin được phép nhưng `CONNECT` thiếu/sai token**: WebSocket transport có thể được thiết lập, nhưng phiên STOMP không vượt qua kiểm tra CSRF và không được quyền hoạt động.
4. **Token hợp lệ nhưng anonymous trong policy yêu cầu đăng nhập**: `CONNECT` bị từ chối bởi authorization.
5. **Alice SUBSCRIBE `/topic/updates`**: policy cho phép; server chỉ gửi dữ liệu phù hợp với quyền của nhóm nhận.
6. **Alice SEND `/topic/updates`**: `denyAll` chặn; thông báo do server phát phải đến từ đường tin cậy.
7. **Alice SUBSCRIBE `/topic/rooms/42`**: policy trên không mở destination này nên bị từ chối; nếu muốn mở phải thêm kiểm tra membership của room 42.
8. **Alice SEND `/app/chat.send` nhưng không có quyền room 42**: message-level rule có thể cho đi vào handler, **handler phải từ chối** thao tác nghiệp vụ.

Tùy handshake, STOMP client và phiên bản thư viện, lỗi có thể thể hiện bằng HTTP rejection, STOMP `ERROR`, đóng kết nối hoặc exception trong log. **Không giả định mã HTTP chính xác cho mọi trường hợp**; hãy kiểm chứng ở hệ thống chạy thực tế.

## 8. Checklist kiểm thử khi triển khai

| Kịch bản | Cách thử | Kết quả mong đợi |
| --- | --- | --- |
| Same-origin | Mở kết nối từ frontend đúng origin | Handshake được xem xét theo HTTP auth; `CONNECT` còn yêu cầu token |
| Cross-origin trái phép | Trang khác origin gọi WebSocket | Handshake bị từ chối theo allowlist |
| Thiếu CSRF | Client kết nối nhưng bỏ `connectHeaders` token | `CONNECT` không thành công |
| Token sai/hết hạn | Gửi token không khớp phiên | `CONNECT` không thành công |
| Anonymous | Không có session đã đăng nhập | Rule `CONNECT.authenticated()` từ chối |
| Topic hợp lệ | Authenticated client SUBSCRIBE `/topic/updates` | Được cho phép |
| Gửi vào broker | Authenticated client SEND `/topic/updates` | Bị từ chối |
| Subscribe ngoài policy | SUBSCRIBE `/queue/someone-else` | Bị từ chối |
| Vượt quyền nghiệp vụ | SEND phòng chat không thuộc về user | Handler từ chối dù message match |
| SockJS fallback (nếu bật) | Chạy fallback HTTP và gửi STOMP CONNECT token | HTTP transport hoạt động; CSRF của STOMP vẫn được áp dụng |

Tự kiểm tra cả trường hợp session logout/expire, reconnect sau đổi token, cấu hình frontend tách origin, và destination do client tự dựng. Với kiểm thử tự động, cần assert **cả handshake lẫn frame**; chỉ kiểm tra HTTP `GET /ws` là chưa đủ. Khi quan sát log, không in giá trị CSRF token, cookie hoặc bearer token.

## 9. Sai lầm thường gặp

- **Nhầm `Origin` với authentication:** header này có thể giả mạo ngoài browser và không trả lời câu hỏi “user là ai?”.
- **Nhầm CORS với bảo vệ WebSocket:** phải cấu hình allowed origins cho WebSocket/SockJS đúng chỗ.
- **Nhầm handshake thành được toàn quyền:** HTTP 101 hoặc `CONNECTED` không cấp quyền SEND/SUBSCRIBE đến mọi destination.
- **Chỉ kiểm tra CSRF ở HTTP:** Spring Security còn bảo vệ STOMP `CONNECT`; gửi token trong `connectHeaders`, không chỉ HTTP headers.
- **Bỏ toàn bộ CSRF để sửa SockJS:** chỉ xem xét ngoại lệ HTTP trên path transport cần thiết và giữ lớp CSRF của STOMP.
- **Cho phép client SEND thẳng đến broker prefix:** người dùng có thể giả mạo thông báo hệ thống nếu policy không chặn.
- **Mở `/queue/**` hoặc `/topic/**` tràn lan:** có thể lộ dữ liệu của người khác; ưu tiên allowlist SUBSCRIBE và kiểm tra quyền theo tài nguyên.
- **Tin identity/role trong payload:** lấy Principal từ security context và kiểm tra quyền thật ở server.
- **Dùng API cấu hình cũ:** `AbstractSecurityWebSocketMessageBrokerConfigurer` thuộc hướng cũ và đã bị loại bỏ trong Spring Security 7; ví dụ ở đây sử dụng `AuthorizationManager<Message<?>>`.

## 10. Ghi nhớ và tài liệu chính thức

Có thể nhớ ba câu hỏi theo đúng thứ tự: **(1) Origin của browser được phép mở transport? (2) STOMP CONNECT có token chống CSRF hợp lệ và user phù hợp? (3) User được thực hiện loại message/destination/tài nguyên này?** Mỗi bước kiểm soát một rủi ro khác nhau, kết hợp để ngăn CSWSH, giả mạo gửi message và đọc trái phép dữ liệu broker.

Tài liệu tham khảo từ dự án Spring (nên kiểm tra theo phiên bản dependency của ứng dụng):

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — WebSocket allowed origins: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — STOMP authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — STOMP token authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — STOMP authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
