# Kiểm thử hết hạn, đăng xuất và mất kết nối kho trong ứng dụng WebSocket

Ứng dụng WebSocket thường xác thực người dùng qua HTTP handshake rồi duy trì kết nối trong thời gian dài. Trong khi đó, Spring Session quản lý vòng đời phiên HTTP theo timeout, logout và kho lưu trữ dùng chung như Redis hoặc JDBC. Vì vậy, một WebSocket có thể vẫn đang mở khi session đã hết hạn, người dùng đã đăng xuất hoặc kho session tạm thời không truy cập được.

Không thể coi kết nối WebSocket đang mở là bằng chứng rằng phiên đăng nhập vẫn hợp lệ. Cần kiểm thử cả vòng đời session lẫn vòng đời kết nối: session được tạo khi handshake, hoạt động WebSocket có làm mới idle timeout hay không, logout có đóng các socket gắn với session trên node khác hay không, và hệ thống phản ứng thế nào khi Redis/database mất kết nối.

Bài này hướng dẫn thiết kế và kiểm thử ba tình huống quan trọng: session hết hạn, logout và mất kết nối kho session. Nội dung bao gồm tích hợp Spring Session với WebSocket/STOMP, đồng bộ nhiều node, đóng kết nối, xử lý tài nguyên phụ trợ, kiểm thử bằng server và kho dữ liệu thật, cùng các giới hạn cần tính đến khi vận hành.

## 1. Hai vòng đời chạy song song

HTTP session và WebSocket connection có liên quan nhưng không phải cùng một đối tượng.

HTTP session có thể được tạo trong quá trình đăng nhập hoặc handshake. Session được lưu trong Spring Session repository và được định danh bằng cookie hoặc header. WebSocket connection được thiết lập qua HTTP handshake, sau đó chuyển sang giao thức WebSocket. Sau khi handshake hoàn tất, các frame tiếp theo không phải là request HTTP độc lập.

Sơ đồ khái niệm:

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant LB as Load balancer
    participant A as App node A
    participant B as App node B
    participant S as Shared session store
    participant W as WebSocket broker

    C->>LB: HTTP handshake + session cookie
    LB->>A: Upgrade request
    A->>S: Tìm session và xác thực
    S-->>A: Session + principal
    A->>W: Đăng ký WebSocket/STOMP session
    W-->>C: WebSocket connected
    Note over C,W: Kết nối tiếp tục sau handshake
    C->>W: STOMP message
    W->>A: Inbound message
    A->>S: Cập nhật/kiểm tra session theo cấu hình
    S-->>A: Kết quả repository
~~~

Hai vòng đời cần được quản lý:

| Thành phần | Bắt đầu | Kết thúc |
|---|---|---|
| HTTP session | Login hoặc request tạo session | Idle timeout, logout, thu hồi hoặc xóa bởi repository |
| WebSocket connection | HTTP Upgrade handshake thành công | Client disconnect, mạng lỗi, server close hoặc session bị thu hồi và listener đóng socket |
| STOMP session | Client gửi CONNECT và broker xác nhận | DISCONNECT, lỗi transport hoặc đóng WebSocket |
| Subscription | Client SUBSCRIBE tới destination | UNSUBSCRIBE, disconnect hoặc cleanup phía server |
| Tài nguyên theo kết nối | Tạo subscription, consumer hoặc room membership | Được giải phóng khi kết nối đóng |

Một HTTP session có thể gắn với nhiều WebSocket connection, ví dụ nhiều tab trình duyệt. Logout phải xử lý tất cả socket thuộc session đó nếu chính sách yêu cầu thu hồi hoàn toàn.

## 2. Liên kết WebSocket với Spring Session

Spring Session có tích hợp WebSocket để liên kết kết nối WebSocket với HttpSession đã dùng trong handshake. Với STOMP messaging, cấu hình tích hợp có thể thêm interceptor để cập nhật lastAccessedTime khi có message đến và listener để đóng WebSocket connection khi session bị hủy.

Với phiên bản Spring Session có hỗ trợ cấu hình qua AbstractSessionWebSocketMessageBrokerConfigurer, cấu trúc có thể như sau:

~~~java
@Configuration
@EnableWebSocketMessageBroker
@EnableRedisHttpSession
public class WebSocketConfiguration
        extends AbstractSessionWebSocketMessageBrokerConfigurer<Session> {

    @Override
    protected void configureStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("https://app.example.com");
    }

    @Override
    protected void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Ví dụ minh họa cấu hình STOMP với kho Redis. Tên annotation, loại repository và extension point cần đối chiếu phiên bản Spring Session/Spring Framework đang dùng. Nếu ứng dụng dùng broker relay hoặc WebSocketHandler thuần, cách đăng ký interceptor và registry có thể khác.

Tích hợp Spring Session WebSocket thường đảm nhiệm hai việc quan trọng:

- Liên kết WebSocket session với HTTP session đã được xác thực trong handshake.
- Cập nhật thời điểm truy cập session khi nhận message WebSocket, nếu interceptor tương ứng được bật.

Tùy cấu hình, thành phần WebSocket registry cũng có thể nhận sự kiện session bị xóa/hết hạn và đóng các kết nối đã đăng ký. Không giả định cơ chế này tự hoạt động trên mọi repository hoặc mọi topology; cần xác minh event được phát, được truyền tới các node và listener đã được đăng ký.

### Handshake chỉ xác thực tại một thời điểm

Spring Security thường xác thực HTTP handshake. Principal của request được gắn với WebSocket/STOMP session. Sau handshake, việc session bị xóa trong Redis không tự động làm cho mọi frame đang truyền bị kiểm tra lại như một request HTTP mới.

Vì vậy, ứng dụng phải có chính sách xử lý kết nối đang mở khi session bị thu hồi. Có thể dùng Spring Session WebSocket integration để đóng socket khi nhận sự kiện hủy session, kết hợp kiểm tra quyền trên inbound message và xác minh session cho thao tác nhạy cảm.

## 3. Idle timeout khi kết nối WebSocket đang mở

Một WebSocket có thể duy trì kết nối TCP trong thời gian dài mà không gửi message ứng dụng. Việc socket còn mở không nhất thiết làm mới lastAccessedTime của HTTP session.

Trong tích hợp Spring Session STOMP, SessionRepositoryMessageInterceptor có thể cập nhật thời điểm truy cập khi nhận inbound message. Khi đó:

- Một message hợp lệ từ client có thể được tính là hoạt động và làm mới idle timeout.
- Chỉ giữ TCP/WebSocket connection mở nhưng không gửi message có thể không làm mới session.
- Ping/pong ở tầng transport không nhất thiết đi qua interceptor xử lý STOMP message.
- Heartbeat của STOMP cần được kiểm tra với phiên bản và cấu hình cụ thể; không giả định mọi heartbeat đều cập nhật session giống message ứng dụng.

Hãy xác định chính sách mong muốn:

| Chính sách | Hành vi cần kiểm thử |
|---|---|
| Socket mở không giữ session sống | Session hết hạn nếu không có hoạt động được tính là activity |
| STOMP message làm mới idle timeout | Message đến cập nhật lastAccessedTime |
| Heartbeat không làm mới session | Kết nối có thể vẫn hoạt động ở transport nhưng session hết hạn |
| Mọi hoạt động được xác thực làm mới timeout | Cần xác định chính xác loại frame/message được tính |
| Absolute timeout | Session hết hạn sau tuổi tối đa dù WebSocket vẫn gửi message |

Không dùng heartbeat để kéo dài phiên đăng nhập vô thời hạn nếu chính sách bảo mật yêu cầu absolute timeout. Có thể lưu thời điểm xác thực hoặc thời điểm tạo session và kiểm tra riêng.

## 4. Hết hạn session phải ảnh hưởng tới WebSocket ra sao?

Khi session hết hạn, repository không còn coi session đó là hợp lệ. Tuy nhiên, socket đã được mở có thể vẫn còn ở node xử lý kết nối.

Một luồng xử lý mong muốn:

1. Session hết idle timeout hoặc bị xóa.
2. Repository phát sự kiện session hết hạn/xóa theo khả năng của implementation.
3. Listener nhận sự kiện trên node có kết nối WebSocket.
4. Registry tìm các WebSocket connection gắn với session ID.
5. Các socket liên quan được đóng bằng close status phù hợp.
6. Broker giải phóng subscription và tài nguyên theo kết nối.
7. Client nhận close event, xóa trạng thái kết nối và yêu cầu đăng nhập lại khi cần.

Spring Session WebSocket integration có thể dùng WebSocketRegistryListener để đóng các socket gắn với session đã bị hủy. Điều này phụ thuộc event source và event delivery. Nếu dùng repository không phát sự kiện phân tán hoặc listener không nhận được event, socket ở node khác có thể tiếp tục mở.

Không đặt timeout cleanup vật lý của Redis/JDBC làm tiêu chí duy nhất. Session có thể đã hết hạn logic trước khi key hoặc row bị xóa. Repository phải từ chối session hết hạn khi được tra cứu; cơ chế đóng socket cần nhận biết việc session hết hạn theo cách phù hợp với repository.

### Đóng socket bằng close status

Ứng dụng nên dùng close status có ý nghĩa:

| Tình huống | Mã đóng có thể dùng | Ý nghĩa |
|---|---:|---|
| Session hết hạn hoặc logout | 1008 | Policy violation; client cần xác thực lại |
| Lỗi nội bộ khi không thể tiếp tục an toàn | 1011 | Internal error |
| Server bảo trì hoặc khởi động lại | 1012 | Service restart |
| Tạm thời không thể phục vụ, yêu cầu thử lại | 1013 | Try again later |

Chọn mã và thông điệp phù hợp với client. Không đưa session ID, token hoặc chi tiết nội bộ vào close reason. Client không nên lặp reconnect vô hạn với cookie đã bị thu hồi.

## 5. Logout HTTP cần đóng các WebSocket liên quan

Logout thường được thực hiện qua HTTP endpoint. Spring Security có thể invalidate HttpSession, xóa SecurityContext và xóa cookie session. Khi session bị hủy, WebSocket integration có thể đóng các socket liên kết với session đó.

Ví dụ cấu hình logout:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

Ví dụ trên giả định cookie session có tên SESSION. Nếu dùng tên cookie khác hoặc cấu hình Domain/Path riêng, thao tác xóa cookie phải khớp với cookie đã phát. Với Spring Session, cần kiểm tra CookieSerializer để biết tên, Domain, Path, Secure, HttpOnly và SameSite thực tế.

Nếu CSRF đang bật, request logout POST cần cung cấp CSRF token hợp lệ. Không tắt CSRF chỉ để làm test logout đơn giản.

Xóa cookie chỉ tác động tới trình duyệt gửi response logout. Việc invalidate session trong repository mới là bước thu hồi server-side. Nếu chỉ xóa cookie mà không xóa session, bản sao cookie cũ vẫn có thể được replay.

### Logout từ một node, WebSocket ở node khác

Ví dụ:

~~~text
Browser A
  |
  +-- HTTP logout --> App node 1 --> Shared session store: delete session
  |
  +-- WebSocket ----> App node 2 --> WebSocket registry
                                  ^
                                  |
                         Session destroyed event
~~~

Node 1 có thể không giữ socket. Node 2 cần nhận được sự kiện hủy session để đóng kết nối. Nếu event không được truyền tới node 2, session trong kho đã bị xóa nhưng socket có thể vẫn mở.

Do đó, kiểm thử logout trên cùng một node là chưa đủ. Cần tạo WebSocket trên node B, thực hiện logout qua node A rồi xác nhận socket ở B bị đóng hoặc bị từ chối message tiếp theo theo chính sách.

## 6. Event propagation giữa các node

Các event như SessionDeletedEvent và SessionExpiredEvent có thể được phát khi session bị xóa hoặc hết hạn. Redis repository hỗ trợ event propagation qua cơ chế Redis notification/Pub/Sub tùy loại repository và cấu hình. JDBC repository có thể có hành vi event khác; không mặc định rằng mọi node sẽ nhận được event chỉ vì chúng cùng truy cập một database.

Cần phân biệt ba lớp:

- **Repository state:** dữ liệu session đã bị xóa hoặc hết hạn.
- **Application event:** một node trong ứng dụng nhận event từ repository.
- **Cross-node delivery:** các node khác cũng nhận event và thực hiện cleanup socket.

Event listener cục bộ chỉ chứng minh node đó nhận event. Nó không chứng minh node đang giữ WebSocket ở máy khác đã nhận được thông báo.

Nếu backend không cung cấp event phân tán phù hợp, có thể bổ sung cơ chế broadcast qua message broker, Redis Pub/Sub, database outbox hoặc một kênh điều phối riêng. Nếu dùng Pub/Sub, phải tính tới việc subscriber có thể mất kết nối và bỏ lỡ message. Với yêu cầu thu hồi bảo mật cao, event nên là tín hiệu đóng socket; mỗi thao tác nhạy cảm vẫn cần kiểm tra trạng thái session/token hoặc một revocation version có nguồn dữ liệu đáng tin cậy.

Không dùng event như một nguồn dữ liệu bền vững hoặc bảo đảm exactly-once. Listener cần idempotent vì một disconnect hoặc cleanup event có thể được xử lý nhiều lần.

## 7. Xử lý nhiều WebSocket trên cùng một HTTP session

Một người dùng có thể mở nhiều tab hoặc nhiều thiết bị. Các kết nối này có thể cùng dùng một session cookie:

~~~text
HTTP session S-100
   |
   +-- WebSocket connection W-A (tab 1)
   +-- WebSocket connection W-B (tab 2)
   +-- WebSocket connection W-C (laptop khác)
~~~

Khi session S-100 bị logout, chính sách thường yêu cầu đóng tất cả W-A, W-B và W-C. Không chỉ đóng socket vừa gửi request logout.

Kiểm thử cần tạo ít nhất hai kết nối dùng cùng session cookie, có thể trên hai node khác nhau. Sau khi logout:

- Tất cả kết nối gắn với session phải nhận close event.
- Các subscription STOMP phải được giải phóng.
- Không có kết nối nào tiếp tục nhận message riêng tư.
- Một session khác của cùng principal vẫn hoạt động nếu logout chỉ nhắm tới một session.
- Logout all devices phải thu hồi mọi session của principal và đóng mọi socket tương ứng.

Để logout all devices, ứng dụng cần tìm và xóa mọi session của principal bằng repository indexed hoặc cơ chế quản lý session phù hợp. Sau đó, cần bảo đảm sự kiện thu hồi tới mọi node giữ socket của các session đó.

## 8. Remember-me và cơ chế tự đăng nhập lại

Nếu ứng dụng bật remember-me, logout session nhưng vẫn giữ remember-me cookie có thể khiến request HTTP tiếp theo tự xác thực lại và tạo session mới. Đây có thể là hành vi đúng nếu logout chỉ kết thúc phiên hiện tại, nhưng thường không đúng với yêu cầu “đăng xuất hoàn toàn”.

Cần xác định rõ:

- Logout một session: xóa session hiện tại, giữ các session/remember-me credential khác theo chính sách.
- Logout mọi thiết bị: thu hồi tất cả session và remember-me token có thể thu hồi.
- Logout toàn bộ tài khoản: có thể cần đổi credential version, thu hồi refresh token hoặc vô hiệu hóa các remember-me token.

Với persistent remember-me token, token repository dùng chung cần xóa token tương ứng khi logout. Với remember-me cookie dựa trên chữ ký stateless, xóa cookie ở browser không thu hồi bản sao cookie bị đánh cắp; cần chính sách thu hồi như đổi signing key, đổi mật khẩu hoặc kiểm tra version/denylist.

Khi kiểm thử WebSocket, phải tách cookie session khỏi remember-me cookie. Nếu client tự kết nối lại bằng remember-me, test có thể hiểu nhầm rằng socket cũ vẫn hoạt động trong khi thực tế một session mới đã được tạo.

## 9. Khi kho session mất kết nối

Redis hoặc database có thể tạm thời không truy cập được trong khi WebSocket đang mở. Đây là tình huống khác với session hết hạn.

Khi kho dữ liệu mất kết nối:

- Handshake mới có thể không tải hoặc tạo được session.
- Logout có thể không xóa được session ở thời điểm đó.
- WebSocket message interceptor có thể không cập nhật được lastAccessTime.
- Event hết hạn/xóa có thể không được truyền tới node.
- Socket đã thiết lập có thể vẫn truyền frame nếu broker và transport còn hoạt động.
- Một node không thể khẳng định session còn hợp lệ chỉ vì socket vẫn mở.

Không biến lỗi repository thành “không tìm thấy session” bằng cách nuốt exception. Cũng không tự động cho phép message nhạy cảm vì kết nối đã được xác thực từ trước.

### Chính sách fail-closed cho thao tác nhạy cảm

Khi không thể xác minh trạng thái session, hệ thống nên từ chối hoặc tạm dừng thao tác nhạy cảm cho tới khi kiểm tra được. Ví dụ:

| Loại message | Hướng xử lý khi session store không khả dụng |
|---|---|
| Cập nhật số dư, đặt lệnh, thay đổi quyền | Từ chối nếu không thể xác minh phiên/quyền hiện tại |
| Truy cập dữ liệu cá nhân nhạy cảm | Fail closed hoặc đóng socket |
| Ping/heartbeat kỹ thuật | Có thể xử lý nếu không làm phát sinh hành động được bảo vệ |
| Message công khai không cần xác thực | Có thể tiếp tục theo chính sách endpoint |
| Subscription riêng tư mới | Không cho đăng ký nếu không xác minh được quyền |
| Gửi lại command sau khi kết nối phục hồi | Không tự replay nếu chưa có idempotency key và xác nhận kết quả |

Không phải mọi ứng dụng đều cần đóng toàn bộ WebSocket ngay khi Redis chập chờn. Có thể giữ kết nối transport trong một khoảng ngắn để chờ phục hồi, nhưng phải ngăn các thao tác cần xác thực mà chưa thể kiểm tra. Với ứng dụng có yêu cầu bảo mật cao, đóng socket là lựa chọn đơn giản và dễ chứng minh hơn.

### Phân biệt outage với session miss

Repository lookup có ba kết quả:

- Tìm thấy session hợp lệ.
- Không tìm thấy session hoặc session đã hết hạn.
- Lỗi kết nối/timeout/serialization.

Lỗi kho dữ liệu không phải bằng chứng rằng người dùng đã logout. Hãy ghi nhận trạng thái unavailable riêng, phát metric và trả lỗi phù hợp. Khi store phục hồi, phải tra cứu lại từ nguồn dữ liệu; không tin một bản session cache cũ vô thời hạn.

## 10. Kết nối WebSocket đã mở có thể tiếp tục sau logout không?

Có thể, nếu ứng dụng chỉ invalidate HTTP session mà không đóng socket và không kiểm tra session trên inbound message. Handshake đã xác thực một lần; principal có thể tiếp tục gắn với WebSocket connection.

Vì vậy, phải kiểm thử cả hai cơ chế:

1. Session destruction event đóng socket trên node giữ kết nối.
2. Inbound message authorization kiểm tra trạng thái hoặc quyền cần thiết trước khi thực hiện hành động.

Đối với message nhạy cảm, có thể kiểm tra session ID gắn với WebSocket session qua repository hoặc kiểm tra một revocation/version value. Việc kiểm tra phải non-blocking nếu ứng dụng dùng WebFlux; với STOMP Servlet, cần tránh làm nghẽn message channel bằng truy vấn chậm.

Không nên truy vấn repository cho mọi message nếu tải rất lớn mà không có thiết kế phù hợp. Có thể dùng lease ngắn hoặc cache revocation có thời hạn, nhưng cache phải có giới hạn thời gian và cơ chế invalidation rõ ràng. Một cache không nhận logout event sẽ kéo dài quyền truy cập sau khi session bị thu hồi.

## 11. Đóng socket và giải phóng tài nguyên liên quan

Đóng WebSocket transport là một phần của cleanup. Ứng dụng còn có thể phải giải phóng:

- STOMP subscriptions.
- Broker subscription và queue consumer.
- Room/channel membership.
- Event stream hoặc reactive subscription.
- Listener theo user/session.
- Tác vụ nền gắn với kết nối.
- Presence record và distributed lock có thời hạn.
- Tài nguyên tạm như upload hoặc workflow draft.

Không đóng các tài nguyên dùng chung của toàn ứng dụng khi một người dùng logout. Ví dụ, không đóng toàn bộ RedisConnectionFactory, DataSource hoặc message broker connection pool chỉ vì một WebSocket session bị hủy. Chỉ hủy subscription hoặc resource riêng của kết nối đó.

Cleanup nên idempotent: gọi hai lần không gây lỗi hoặc xóa tài nguyên của session khác. SessionDisconnectEvent có thể xuất hiện nhiều lần trong một số tình huống; listener phải chịu được disconnect trùng lặp.

Ví dụ listener STOMP ghi nhận disconnect:

~~~java
@Component
public class WebSocketLifecycleListener {

    private final ConnectionCleanupService cleanupService;

    public WebSocketLifecycleListener(ConnectionCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        cleanupService.releaseForWebSocket(event.getSessionId());
    }
}
~~~

Đoạn code minh họa listener. ConnectionCleanupService cần xử lý lặp lại an toàn, không ghi session ID thô vào log và không thực hiện tác vụ blocking trên message event thread. Nếu cleanup cần I/O, hãy đưa nó vào pipeline/scheduler phù hợp và ghi nhận lỗi để có thể thử lại.

## 12. Kiểm thử với hai node và kho session dùng chung

Kiểm thử trên một node không chứng minh logout hoặc expiration được truyền tới node khác. Hãy dựng ít nhất hai application instance có cùng:

- Redis/JDBC endpoint hoặc test database.
- Namespace và schema.
- Serializer và session timeout.
- Cấu hình cookie/resolver.
- Cơ chế event listener và WebSocket registry.

Một kịch bản kiểm thử:

~~~text
1. Khởi động node A và node B cùng dùng một session store.
2. Đăng nhập qua node A, nhận session cookie.
3. Mở WebSocket qua node B bằng cookie đó.
4. Xác nhận STOMP CONNECT được xác thực và subscribe thành công.
5. Logout qua node A.
6. Xác nhận session đã bị xóa ở repository.
7. Xác nhận WebSocket trên node B nhận close event.
8. Gửi lại cookie cũ tới HTTP endpoint và xác nhận không còn được xác thực.
9. Xác nhận subscriptions và tài nguyên của socket được giải phóng.
~~~

Khi dùng load balancer, cần điều khiển request để biết node nào nhận handshake và node nào xử lý logout. Có thể gọi trực tiếp từng node trong test hoặc dùng test routing header chỉ trong môi trường kiểm thử.

Nếu test chạy cùng một process nhưng có hai application context, hãy xác nhận registry và event bus thật sự tách theo node. Nếu dùng chung singleton WebSocket registry trong cùng context, test có thể vô tình bỏ qua vấn đề truyền event qua mạng.

## 13. Kiểm thử hết hạn session

Dùng timeout ngắn trong test, ví dụ 3–5 giây, và repository thật. Không dùng sleep dài cố định để giả định event sẽ tới đúng millisecond.

Các bước:

1. Đăng nhập và tạo session với idle timeout ngắn.
2. Mở WebSocket dùng session cookie.
3. Không gửi STOMP application message trong thời gian dài hơn timeout.
4. Xác nhận repository coi session đã hết hạn.
5. Chờ event/cleanup trong giới hạn hợp lý.
6. Xác nhận socket bị đóng theo cơ chế tích hợp.
7. Gửi request HTTP bằng cookie cũ và xác nhận không còn xác thực.
8. Mở một kết nối mới và xác nhận cần đăng nhập lại.

Tạo thêm trường hợp có message đều đặn trước timeout để kiểm tra message có cập nhật lastAccessedTime theo cấu hình. Kiểm tra heartbeat riêng; không suy luận heartbeat làm mới session chỉ vì TCP connection vẫn hoạt động.

Với Redis, expiration event và cleanup có thể trễ so với thời điểm TTL. Với JDBC, job cleanup có thể chạy theo lịch. Test nên xác nhận session không còn hợp lệ qua repository trước, sau đó kiểm tra socket được đóng trong SLA đã định.

## 14. Kiểm thử logout và nhiều kết nối

Một bộ test logout nên bao gồm:

| Ca kiểm thử | Thao tác | Kết quả cần xác nhận |
|---|---|---|
| Một socket, một session | Logout qua HTTP | Socket bị đóng |
| Nhiều socket cùng session | Mở hai tab rồi logout | Cả hai socket bị đóng |
| Socket ở node khác | Handshake ở B, logout ở A | B nhận event và đóng socket |
| Một trong nhiều session của user | Logout một session ID | Socket của session đó đóng; session khác vẫn hoạt động |
| Logout all devices | Xóa mọi session theo principal | Mọi socket tương ứng đóng |
| Remember-me bật | Logout hoàn toàn | Cookie/token remember-me được xử lý theo chính sách |
| Replay cookie cũ | Gửi lại cookie sau logout | Repository không tìm thấy session hợp lệ |
| Disconnect event trùng lặp | Gọi cleanup nhiều lần | Không lỗi và không xóa resource khác |
| Logout trong lúc message đang chạy | Gửi command đồng thời | Hành vi race được xác định và kiểm soát |

Nếu logout và một message nhạy cảm xảy ra đồng thời, message có thể đã được xác thực trước thời điểm session bị xóa. Invalidation không tự hủy công việc đang chạy. Với thao tác có hậu quả lớn, cần kiểm tra revocation ngay trước commit nghiệp vụ hoặc dùng version/lock phù hợp.

## 15. Kiểm thử mất kết nối Redis/JDBC

Không chỉ mô phỏng repository trả Mono.empty hoặc null. Hãy làm kho dữ liệu thực sự không truy cập được trong integration test để xác nhận lỗi mạng, timeout và phục hồi.

Một kịch bản:

1. Khởi động Redis test container hoặc database.
2. Đăng nhập, mở WebSocket và xác nhận message hoạt động.
3. Tạm dừng hoặc chặn kết nối tới session store.
4. Thử handshake mới: xác nhận request không được coi là anonymous thành công một cách âm thầm.
5. Gửi message nhạy cảm qua socket cũ: xác nhận hệ thống fail closed hoặc đóng socket theo chính sách.
6. Kiểm tra log/metric ghi nhận store unavailable, không ghi session miss.
7. Khôi phục store.
8. Kiểm tra session còn hạn được đọc lại hoặc session đã bị thu hồi vẫn bị từ chối.
9. Kết nối lại bằng cookie cũ và xác nhận hành vi phù hợp.
10. Kiểm tra không có command bị replay ngoài ý muốn.

Cần phân biệt hai trạng thái sau khi phục hồi:

- Session vẫn còn hợp lệ trong store: client có thể thực hiện handshake mới sau khi xác thực lại.
- Session đã hết hạn hoặc bị logout trong thời gian outage: không được khôi phục từ bản cache cũ.

Nếu event logout bị mất trong thời gian subscriber ngắt kết nối, socket có thể chưa được đóng ngay. Có thể dùng periodic revalidation hoặc revocation version để giảm cửa sổ rủi ro. Với yêu cầu thu hồi nghiêm ngặt, khi mất event channel nên đóng các socket đã xác thực hoặc hạn chế message cho tới khi kiểm tra được trạng thái.

## 16. WebSocket event và xử lý disconnect

Spring Messaging phát các event như:

- SessionConnectEvent khi nhận STOMP CONNECT.
- SessionConnectedEvent khi broker xác nhận kết nối.
- SessionSubscribeEvent khi client đăng ký destination.
- SessionUnsubscribeEvent khi client hủy subscription.
- SessionDisconnectEvent khi kết nối STOMP bị ngắt.

SessionDisconnectEvent có thể được phát nhiều lần trong một số đường đi đóng kết nối. Listener không được giả định event chỉ đến đúng một lần. Hãy dùng khóa định danh nội bộ của connection và thao tác cleanup idempotent.

Các event này mô tả vòng đời STOMP connection. Chúng khác với event Spring Session như session deleted/expired. Một event disconnect có thể xảy ra do mạng rớt trong khi HTTP session vẫn còn hợp lệ; ngược lại, session có thể bị logout trong khi WebSocket transport vẫn đang mở.

Đừng đồng nhất hai loại event. Cần có mapping giữa HTTP session ID và WebSocket session ID để biết connection nào cần đóng khi session bị thu hồi. Không đưa các ID này vào log công khai.

## 17. Bảo mật handshake và message

Handshake cần kiểm tra:

- Người dùng đã xác thực.
- Origin được allowlist rõ ràng.
- Cookie/session ID được gửi qua HTTPS.
- Session repository có thể xác minh session.
- Không nhận session ID qua query parameter.
- Không cho phép origin wildcard khi dùng cookie xác thực.

Sau handshake, cần bảo vệ từng STOMP destination:

- Chỉ cho phép SUBSCRIBE tới topic mà principal có quyền.
- Kiểm tra quyền trên SEND destination.
- Không tin user ID hoặc tenant ID do client gửi trong payload.
- Gắn principal từ handshake/security context.
- Khi logout/expiry, đóng socket và hủy subscription.
- Với thao tác nhạy cảm, kiểm tra trạng thái thu hồi theo chính sách.

Một WebSocket đã xác thực không nên trở thành đường vòng để bỏ qua authorization của HTTP API. Nếu một user bị thu hồi quyền hoặc chuyển tenant, socket cũ có thể vẫn giữ principal cũ; cần đóng socket hoặc revalidate quyền trước message.

## 18. Quan sát khi vận hành

Các metric nên theo dõi:

- Số WebSocket connection đang mở theo node.
- Số STOMP connect/disconnect và close reason theo nhóm.
- Số session expiry/delete event nhận được.
- Độ trễ từ logout tới socket close.
- Số socket còn mở sau khi session đã bị thu hồi.
- Số lỗi Redis/JDBC, timeout và reconnect.
- Số message bị từ chối vì không xác minh được session.
- Số subscription/resource được cleanup.
- Số lần client reconnect với session cũ.
- Tỷ lệ session lookup miss và repository unavailable được phân loại riêng.

Không dùng session ID, token, cookie hoặc principal name làm metric label. Log cần correlation ID và node ID; chỉ ghi loại sự kiện, kết quả và close status. Nếu cần điều tra một session cụ thể, dùng mã tham chiếu đã được bảo vệ và không thể đảo ngược thay vì ID thật.

Cảnh báo hữu ích gồm: độ trễ logout-to-close tăng, session store unavailable kéo dài, event listener mất kết nối, số socket không có session mapping tăng, và cleanup backlog vượt ngưỡng.

## 19. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Logout thành công nhưng socket vẫn gửi message | Socket không được liên kết với HTTP session hoặc event không tới node giữ socket | Kiểm tra handshake mapping, event propagation và registry |
| Socket đóng ở node logout nhưng không đóng ở node khác | Event chỉ được publish cục bộ hoặc subscriber node kia mất kết nối | Kiểm tra repository event support và pub/sub listener |
| Session hết hạn dù socket đang hoạt động | Message interceptor không chạy hoặc message không được tính là activity | Kiểm tra inbound interceptor và lastAccessTime |
| Socket mở vô hạn sau khi session hết hạn | Không có close listener/revalidation | Kiểm tra session destroyed event và timeout policy |
| Redis outage nhưng message riêng tư vẫn được xử lý | Authorization chỉ dựa vào principal snapshot từ handshake | Áp dụng fail-closed cho thao tác nhạy cảm |
| Client reconnect liên tục với cookie cũ | Không xử lý close status hoặc không yêu cầu login lại | Thiết kế reconnect backoff và trạng thái auth |
| Tài nguyên bị giải phóng hai lần | Listener không idempotent hoặc disconnect event trùng lặp | Dùng cleanup idempotent |
| Logout một tab làm mất tất cả thiết bị ngoài ý muốn | Thu hồi theo principal thay vì session ID | Phân biệt logout một session và logout all |
| Session store đã xóa nhưng socket vẫn tồn tại | Invalidation không tự hủy socket đang mở | Cấu hình registry và kiểm thử cross-node |
| Test pass nhưng production lỗi | Test dùng một node hoặc mock repository/event | Dùng topology hai node và kho dữ liệu thật |

## 20. Checklist kiểm thử trước khi phát hành

- Handshake dùng session cookie và xác thực đúng principal.
- WebSocket connection được liên kết với HTTP session.
- Đã xác định message nào cập nhật lastAccessTime.
- Đã xác định heartbeat có hay không làm mới idle timeout.
- Session hết hạn logic làm socket đóng trong SLA đã đặt.
- Logout HTTP invalidate session trong repository.
- Logout ở node A đóng socket trên node B.
- Tất cả socket của cùng session được đóng.
- Logout một session không vô tình xóa session khác của cùng principal.
- Logout all devices thu hồi tất cả session và socket tương ứng.
- Remember-me cookie/token được xử lý đúng theo ý nghĩa logout.
- Redis/JDBC outage không bị chuyển thành session miss.
- Handshake mới thất bại rõ khi không xác minh được session store.
- Message nhạy cảm fail closed khi không thể xác minh quyền.
- Store phục hồi không làm sống lại session đã hết hạn hoặc bị logout.
- Disconnect cleanup idempotent và giải phóng subscription/resource.
- Client không reconnect vô hạn bằng cookie cũ.
- Metric/log không chứa session ID, cookie hoặc token.
- Test chạy với ít nhất hai node và repository thật.

Kết thúc session HTTP không tự động đồng nghĩa mọi WebSocket connection đã đóng. Ứng dụng cần liên kết socket với session, nhận biết sự kiện hết hạn/xóa, truyền sự kiện tới node đang giữ kết nối và giải phóng subscription cùng tài nguyên phụ trợ. Khi kho session mất kết nối, socket vẫn có thể tồn tại ở tầng transport; vì vậy, thao tác nhạy cảm phải fail closed nếu không thể xác minh trạng thái phiên. Hãy kiểm thử các tình huống trên với hai node và kho dữ liệu thật để chứng minh logout, expiration và outage có hành vi nhất quán.

## Tài liệu tham khảo

- [Spring Session — WebSocket Integration](https://docs.spring.io/spring-session/reference/web-socket.html)
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Framework — WebSocket/STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework — WebSocket API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/package-summary.html)

