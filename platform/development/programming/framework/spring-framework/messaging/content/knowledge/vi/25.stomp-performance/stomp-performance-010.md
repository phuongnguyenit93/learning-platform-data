# WebSocket scope và vòng đời dữ liệu theo phiên

## 1. WebSocket scope là gì?

Trong ứng dụng Spring WebSocket/STOMP, một người dùng có thể mở nhiều kết nối đồng thời: nhiều tab trình duyệt, nhiều cửa sổ hoặc nhiều thiết bị. Mỗi WebSocket session có thể cần một ít dữ liệu riêng, chẳng hạn ngữ cảnh thao tác tạm thời, lựa chọn giao diện, tiến trình của một tác vụ gắn với kết nối hoặc tài nguyên ngắn hạn cần giải phóng khi session kết thúc.

Nếu đặt dữ liệu này trong singleton service, mọi WebSocket session có thể cùng truy cập một instance và vô tình chia sẻ dữ liệu. Nếu đặt trong HTTP session, phạm vi dữ liệu lại là toàn bộ HTTP session, có thể được nhiều WebSocket session dùng chung.

Spring cung cấp **WebSocket scope** để quản lý bean theo vòng đời của một WebSocket session. Mỗi session có một instance riêng cho mỗi bean thuộc scope này. Spring tạo instance khi bean được truy cập lần đầu trong session, lưu nó trong session attributes và trả lại cùng instance ở các lần truy cập tiếp theo. Khi WebSocket session kết thúc, Spring gọi lifecycle callback của bean, bao gồm **@PreDestroy**.

WebSocket scope phù hợp với trạng thái ngắn hạn theo kết nối. Dữ liệu nghiệp vụ cần tồn tại sau khi người dùng đóng trình duyệt hoặc reconnect vẫn phải được lưu trong database hoặc kho lưu trữ phù hợp.

## 2. Phân biệt WebSocket scope với các scope khác

| Scope | Phạm vi tồn tại | Ví dụ sử dụng |
|---|---|---|
| **singleton** | Một instance cho bean definition trong Spring container. | Service stateless dùng chung cho toàn ứng dụng. |
| **prototype** | Instance mới mỗi lần container tạo bean. | Đối tượng ngắn hạn do ứng dụng chủ động tạo. |
| **request** | Một HTTP request. | Dữ liệu chỉ dùng trong một request. |
| **session** | Một HTTP session. | Dữ liệu theo phiên đăng nhập HTTP. |
| **websocket** | Một WebSocket session. | Workspace hoặc context riêng cho một kết nối STOMP. |

WebSocket scope không đồng nghĩa với HTTP session scope:

- Một HTTP session có thể mở nhiều WebSocket session.
- Mỗi WebSocket session có WebSocket-scoped bean riêng.
- Hai tab của cùng người dùng thường có hai WebSocket session riêng, vì vậy không dùng chung instance WebSocket-scoped.
- Khi WebSocket reconnect tạo session mới, bean của session cũ không tự chuyển sang session mới, kể cả cookie HTTP session vẫn còn hiệu lực.

~~~mermaid
flowchart TD
    U["Một người dùng / HTTP session"] --> W1["WebSocket session A"]
    U --> W2["WebSocket session B"]
    W1 --> A["WebSocket-scoped bean A"]
    W2 --> B["WebSocket-scoped bean B"]
    A -. "Không chia sẻ instance" .- B
~~~

Hãy chọn scope theo vòng đời thật của dữ liệu. Dùng singleton cho logic dùng chung và thread-safe; dùng WebSocket scope cho context ngắn hạn của một kết nối; dùng HTTP session scope khi dữ liệu cần chia sẻ theo phiên đăng nhập HTTP.

## 3. Dữ liệu session attributes

Mỗi WebSocket session có một map attributes. Spring gắn map này vào header của inbound client message. Controller có thể truy cập qua **SimpMessageHeaderAccessor.getSessionAttributes()**:

~~~java
import java.time.Instant;
import java.util.Map;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class SessionMetadataController {

    @MessageMapping("/session/touch")
    public void touch(SimpMessageHeaderAccessor headers) {
        Map<String, Object> attributes = headers.getSessionAttributes();

        if (attributes != null) {
            attributes.put("lastActionAt", Instant.now());
            attributes.put("lastAction", "touch");
        }
    }
}
~~~

Trong ví dụ, **lastActionAt** và **lastAction** thuộc session hiện tại. Một WebSocket session khác có map attributes riêng.

Có thể lấy session id bằng **headers.getSessionId()** để ghi log hoặc liên kết với dữ liệu theo phiên. Không nên dùng session id làm danh tính người dùng hoặc bằng chứng phân quyền; hãy dùng **Principal** đã được xác thực.

Session attributes phù hợp cho metadata nhỏ, tạm thời. Không nên lưu toàn bộ lịch sử message, file lớn, dữ liệu nhạy cảm hoặc object có vòng đời dài trong map này. Các giá trị được giữ trong bộ nhớ của ứng dụng cho tới khi session kết thúc.

## 4. Khai báo bean trong WebSocket scope

Dùng **@Scope(scopeName = "websocket")** để khai báo bean theo session. Nếu bean được inject vào controller singleton, cần bật scoped proxy vì controller tồn tại lâu hơn từng WebSocket session:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SessionWorkspace {

    private final Map<String, String> selections = new ConcurrentHashMap<>();
    private final AtomicLong actionCount = new AtomicLong();

    @PostConstruct
    public void initialize() {
        // Chạy khi instance của session được tạo lần đầu.
    }

    public void remember(String key, String value) {
        selections.put(key, value);
        actionCount.incrementAndGet();
    }

    public Map<String, String> getSelections() {
        return Map.copyOf(selections);
    }

    public long getActionCount() {
        return actionCount.get();
    }

    @PreDestroy
    public void destroy() {
        // Giải phóng tài nguyên ngắn hạn của session nếu có.
        selections.clear();
    }
}
~~~

**@PostConstruct** được gọi sau khi Spring tạo bean và inject dependencies. Bean thường được khởi tạo lười: callback này chạy khi session truy cập bean lần đầu, không nhất thiết ngay khi WebSocket handshake hoàn tất.

**@PreDestroy** được gọi khi scope của WebSocket session bị hủy. Đây là nơi phù hợp để đóng resource do bean sở hữu hoặc xóa dữ liệu tạm. Không đặt công việc blocking kéo dài trong callback này vì cleanup session không nên làm nghẽn luồng xử lý message.

Ví dụ dùng **jakarta.annotation.PostConstruct** và **jakarta.annotation.PreDestroy** phù hợp với Spring Framework 6 trở lên. Với phiên bản Spring cũ dùng hệ sinh thái Java EE, package annotation có thể khác.

## 5. Inject WebSocket-scoped bean vào singleton controller

Controller thường là singleton, nhưng vẫn có thể inject WebSocket-scoped bean qua proxy:

~~~java
import java.util.Map;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class WorkspaceController {

    private final SessionWorkspace workspace;

    public WorkspaceController(SessionWorkspace workspace) {
        this.workspace = workspace;
    }

    @MessageMapping("/workspace/select")
    public void select(Map<String, String> command,
                       SimpMessageHeaderAccessor headers) {

        String key = command.get("key");
        String value = command.get("value");

        if (key == null || value == null) {
            throw new IllegalArgumentException("key and value are required");
        }

        workspace.remember(key, value);

        String sessionId = headers.getSessionId();
        // Có thể dùng sessionId cho logging hoặc tracing.
    }
}
~~~

Khi method được gọi trong ngữ cảnh xử lý message của một WebSocket session, proxy tìm đúng target bean thuộc session đó. Nếu session A gọi method, proxy trả về workspace A; session B gọi method thì proxy trả về workspace B.

Scoped proxy giải quyết khác biệt vòng đời giữa singleton controller và bean theo session. Nếu bỏ proxy, Spring có thể không inject được bean vì không có WebSocket session cụ thể tại thời điểm khởi tạo controller.

Với **ScopedProxyMode.TARGET_CLASS**, class được proxy không nên là final, và method cần được proxy không nên là final. Nếu muốn dùng interface proxy, có thể chọn **ScopedProxyMode.INTERFACES** và inject qua interface tương ứng.

## 6. Vòng đời của WebSocket-scoped bean

Vòng đời cơ bản:

1. WebSocket handshake tạo một WebSocket session.
2. Client gửi STOMP CONNECT và Spring thiết lập ngữ cảnh message.
3. Khi controller hoặc inbound channel interceptor lần đầu gọi WebSocket-scoped bean, Spring tạo target instance.
4. Spring lưu instance trong session attributes.
5. Các message tiếp theo thuộc session đó truy cập cùng instance.
6. Khi WebSocket session kết thúc và scope được hủy, Spring chạy destruction callbacks, bao gồm **@PreDestroy**.

~~~mermaid
flowchart TD
    A["WebSocket session được tạo"] --> B["Message đầu tiên truy cập bean"]
    B --> C["Spring tạo target instance"]
    C --> D["Lưu target trong session attributes"]
    D --> E["Các message tiếp theo dùng cùng instance"]
    E --> F{"Session còn hoạt động?"}
    F -->|Có| E
    F -->|Không| G["Hủy WebSocket scope"]
    G --> H["@PreDestroy và cleanup"]
~~~

Một bean không được truy cập trong session có thể chưa từng được khởi tạo. Khi đó không có target instance để gọi **@PreDestroy**. Nếu cần theo dõi tất cả session ngay từ lúc CONNECT, dùng session lifecycle events hoặc registry riêng thay vì giả định mọi WebSocket-scoped bean đều đã được tạo.

WebSocket scope gắn với WebSocket session, không gắn với một STOMP subscription riêng. Hủy một subscription không đồng nghĩa hủy WebSocket scope; session có thể còn nhiều subscription khác.

## 7. Theo dõi session lifecycle bằng Spring events

Spring phát các application context events để ứng dụng theo dõi vòng đời STOMP session:

- **SessionConnectEvent**: Spring nhận STOMP CONNECT từ client.
- **SessionConnectedEvent**: broker đã trả CONNECTED và session STOMP được thiết lập.
- **SessionSubscribeEvent**: client gửi SUBSCRIBE.
- **SessionUnsubscribeEvent**: client gửi UNSUBSCRIBE.
- **SessionDisconnectEvent**: session STOMP ngắt kết nối.

Ví dụ listener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = event.getSessionId();
        // Ghi nhận session đã được broker chấp nhận.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Cleanup phải an toàn nếu event được phát nhiều lần.
    }
}
~~~

**SessionConnectEvent** cho biết client đã gửi CONNECT, nhưng chưa chắc broker đã chấp nhận. Nếu cần đánh dấu session đã kết nối STOMP, **SessionConnectedEvent** là mốc phù hợp hơn.

**SessionDisconnectEvent** có thể được phát nhiều lần cho cùng một session trong một số đường đóng kết nối. Vì vậy, thao tác cleanup phải idempotent: gọi nhiều lần vẫn cho cùng kết quả, không trừ presence nhiều lần, không giải phóng tài nguyên đã giải phóng và không xóa dữ liệu của session khác.

Không xem disconnect của một WebSocket session là người dùng đã đăng xuất hoàn toàn. Một user có thể có nhiều tab hoặc thiết bị. Chỉ đánh dấu user offline khi không còn session hợp lệ nào theo chính sách presence của ứng dụng.

## 8. WebSocket scope và concurrency

**clientInboundChannel** có thể xử lý message bằng executor thread pool. Nếu nhiều message của cùng session được xử lý đồng thời, chúng có thể truy cập cùng WebSocket-scoped bean từ nhiều thread.

Vì vậy, WebSocket scope không tự động làm cho các field bên trong bean thread-safe. Trong ví dụ trên, **ConcurrentHashMap** và **AtomicLong** được dùng để hỗ trợ cập nhật đồng thời. Với cấu trúc dữ liệu phức tạp hơn, cần khóa, immutable state hoặc cơ chế đồng bộ phù hợp.

Có thể yêu cầu Spring bảo toàn thứ tự nhận message trong cùng một session bằng:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
~~~

Tùy chọn này giúp message inbound của cùng session được chuyển tới channel theo thứ tự nhận. Tuy nhiên, nó không thay thế thread safety nếu bean còn được truy cập từ thread khác, scheduler hoặc asynchronous task.

Nếu bean được dùng trong tác vụ bất đồng bộ sau khi handler kết thúc, không nên giả định WebSocket scope context tự động được truyền sang executor khác. Proxy cần ngữ cảnh session đang hoạt động để tìm target. Hãy truyền rõ session id hoặc dữ liệu immutable cần thiết tới background service, rồi xử lý qua một API có phạm vi và quyền rõ ràng. Không giữ scoped proxy để gọi tùy ý từ scheduler hoặc thread không có session context.

## 9. Vòng đời tài nguyên và tránh memory leak

Một WebSocket session có thể tồn tại nhiều giờ hoặc nhiều ngày. Một bean trong WebSocket scope vì vậy cũng có thể giữ bộ nhớ trong thời gian dài.

Nên:

- Chỉ lưu dữ liệu nhỏ, cần thiết riêng cho session.
- Giới hạn số phần tử và kích thước collection.
- Xóa listener, callback hoặc reference tới object lớn trong **@PreDestroy**.
- Đóng resource mà bean thực sự sở hữu, ví dụ subscription nội bộ hoặc file handle ngắn hạn.
- Tránh tạo thread, database connection pool hoặc broker connection riêng cho mỗi session.
- Không lưu cache toàn bộ dữ liệu nghiệp vụ trong bean session; dùng cache hoặc persistence service có giới hạn và chính sách eviction riêng.

Ví dụ nếu mỗi session giữ 100 KB dữ liệu và có 20.000 session đồng thời, chỉ riêng phần state đó đã cần khoảng 2 GB bộ nhớ chưa tính overhead object, map, proxy và framework. Vì vậy cần ước lượng theo số session cực đại và đo heap thực tế.

Không nên lưu reference của WebSocket-scoped bean vào singleton collection hoặc static map. Khi session kết thúc, reference bên ngoài có thể giữ bean sống lâu hơn scope và làm memory leak. Nếu cần registry session, chỉ lưu metadata tối thiểu như session id, user id và timestamp; xóa entry một cách idempotent khi disconnect hoặc timeout.

**@PreDestroy** là lifecycle callback của scope trong tiến trình đang chạy; nó không phải bảo đảm lưu trữ bền vững. Nếu JVM bị kill hoặc máy chủ mất điện, callback có thể không chạy. Không dựa vào callback này để thực hiện thao tác duy nhất bảo vệ dữ liệu nghiệp vụ.

## 10. Khôi phục dữ liệu sau reconnect

Reconnect thường tạo WebSocket session mới, vì vậy WebSocket-scoped bean mới được tạo khi truy cập. Dữ liệu trong bean session cũ không tự chuyển sang session mới.

Nếu cần giữ lựa chọn tạm thời qua reconnect, có thể chọn một trong các cách:

| Loại dữ liệu | Nơi lưu phù hợp |
|---|---|
| Dữ liệu tạm thời chỉ cần trong một kết nối | WebSocket-scoped bean hoặc session attributes. |
| Lựa chọn cần giữ qua reconnect nhưng không cần bền vững lâu dài | Client store hoặc server-side cache có TTL, gắn với user/session logic. |
| Dữ liệu phải tồn tại sau logout, restart hoặc đổi thiết bị | Database hoặc persistence layer. |
| Trạng thái nhiều client cùng cập nhật | Backend authoritative store, có version hoặc sequence. |
| Message/event cần replay | Event log hoặc message store có cursor. |

Không dùng WebSocket session id làm khóa duy nhất cho dữ liệu cần sống qua reconnect vì session id mới có thể khác session cũ. Dùng user id đã xác thực hoặc một conversation/workspace id được server cấp và kiểm tra quyền. Không tin một id do client tự gửi nếu nó dùng để truy cập dữ liệu của người khác.

Một luồng khôi phục thường gồm:

1. Client reconnect và nhận CONNECTED.
2. Client đăng ký lại các subscription.
3. Client gửi yêu cầu đồng bộ chứa cursor/version cuối cùng đã xử lý.
4. Server trả snapshot hoặc event replay.
5. Client áp dụng dữ liệu theo version và bỏ qua event trùng.
6. Client chuyển trạng thái sang ready sau khi đồng bộ xong.

## 11. WebSocket scope không thay thế session authentication

WebSocket scope xác định vòng đời object, không xác định người dùng có quyền làm gì. Một bean riêng cho từng session không tự bảo đảm session đó thuộc user hợp lệ hoặc chỉ truy cập dữ liệu của user đó.

Trong controller và service:

- Dùng **Principal** do Spring Security xác thực để lấy danh tính người dùng.
- Kiểm tra quyền trên từng destination và thao tác nghiệp vụ.
- Không dùng session id như access token.
- Không tin user id, tenant id hoặc role nằm trong payload/session attributes nếu chúng do client kiểm soát.
- Không chia sẻ mutable session state giữa các user qua singleton service.

Nếu một session bị mất quyền hoặc người dùng logout, ứng dụng cần đóng hoặc từ chối các thao tác tiếp theo theo chính sách bảo mật. WebSocket scope sẽ được hủy khi session kết thúc; nó không tự thực hiện quy trình logout hoặc revoke token.

## 12. Kiểm thử vòng đời và tài nguyên

Các kiểm thử quan trọng:

| Tình huống | Điều cần xác nhận |
|---|---|
| Hai WebSocket session cùng user | Mỗi session có WebSocket-scoped bean riêng. |
| Hai message trong cùng session | Cùng truy cập một instance cho tới khi session kết thúc. |
| Bean chưa được truy cập | Không giả định **@PostConstruct** đã chạy. |
| Session disconnect | **@PreDestroy** được gọi khi scope bị hủy. |
| Disconnect event lặp | Cleanup không giải phóng hoặc cập nhật presence hai lần. |
| Reconnect cùng HTTP session | Session mới không dùng lại bean của WebSocket session cũ. |
| Nhiều message đồng thời | State bean không bị race condition. |
| Async task sau handler | Không truy cập scoped proxy khi thiếu session context. |
| Session tồn tại lâu | Memory theo session được giới hạn và quan sát được. |
| JVM shutdown bất thường | Dữ liệu nghiệp vụ vẫn an toàn dù cleanup callback không chạy. |

Có thể dùng integration test với WebSocket STOMP client để mở hai session, gửi message vào từng session và xác nhận state không bị chia sẻ. Kiểm tra callback lifecycle bằng bean test có counter hoặc recorder riêng. Khi test disconnect, chờ session thực sự được đóng và scope cleanup hoàn tất thay vì giả định event xảy ra đồng bộ ngay tại lệnh close.

## 13. Lỗi thường gặp

- **Dùng singleton để lưu dữ liệu riêng từng WebSocket session:** các session có thể ghi đè hoặc đọc dữ liệu của nhau. Dùng WebSocket scope hoặc session attributes.
- **Dùng @SessionScope nhưng muốn dữ liệu riêng từng tab:** HTTP session có thể được nhiều WebSocket session dùng chung. Dùng websocket scope cho mỗi kết nối.
- **Inject scoped bean vào singleton mà không dùng proxy:** Spring không xác định được session target khi tạo controller. Bật ScopedProxyMode.TARGET_CLASS hoặc proxy interface.
- **Cho rằng bean được tạo ngay khi CONNECT:** WebSocket-scoped bean thường được khởi tạo lười ở lần truy cập đầu tiên.
- **Cho rằng @PreDestroy chạy ngay khi mạng mất:** scope cleanup phụ thuộc việc server nhận diện session kết thúc; timeout hoặc lỗi đột ngột có thể làm cleanup trễ.
- **Cho rằng mỗi session chỉ có một thread:** inbound executor có thể xử lý song song; dùng cấu trúc thread-safe hoặc bảo toàn thứ tự khi phù hợp.
- **Dùng scoped proxy từ background thread:** thread đó có thể không có WebSocket scope context. Truyền dữ liệu cần thiết một cách tường minh.
- **Lưu dữ liệu bền vững trong bean session:** reconnect hoặc restart có thể làm mất dữ liệu. Dùng persistence.
- **Giữ reference tới bean session trong singleton/static map:** object có thể không được thu hồi sau disconnect. Dọn registry và reference đúng cách.

## 14. Ghi nhớ

WebSocket scope tạo một bean instance cho mỗi WebSocket session, thường khởi tạo ở lần truy cập đầu tiên và hủy khi session kết thúc. Dùng **@Scope("websocket", proxyMode = TARGET_CLASS)** khi inject vào singleton controller; dùng **SimpMessageHeaderAccessor.getSessionAttributes()** cho metadata nhỏ theo session. Dữ liệu trong scope không tự tồn tại qua reconnect và không thay thế HTTP session, authentication hoặc persistence. Vì inbound message có thể xử lý đồng thời, state trong bean cần thread-safe; vì session có thể sống lâu, dữ liệu cần nhỏ và cleanup phải idempotent. Thiết kế đúng vòng đời giúp tách dữ liệu giữa các tab, giảm memory leak và giữ hiệu năng khi có nhiều kết nối đồng thời.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebSocket Scope](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html)