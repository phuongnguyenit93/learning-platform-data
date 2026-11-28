# Lắng nghe SessionDestroyedEvent và thu hồi tài nguyên bên ngoài

## Mục tiêu bài học

Một session có thể sở hữu hoặc liên kết với những tài nguyên nằm ngoài kho session: kết nối WebSocket, trạng thái hiện diện, subscription, dữ liệu tạm, khóa nghiệp vụ hoặc bản ghi theo dõi. Khi phiên bị xóa hay hết hạn trong Redis, các tài nguyên đó cũng cần được thu hồi để tránh rò rỉ và trạng thái mồ côi.

Spring Session cung cấp `SessionDestroyedEvent` để ứng dụng phản ứng khi một session kết thúc. Bài học này tập trung vào cách lắng nghe sự kiện, xác định tài nguyên cần dọn, xử lý trường hợp event đến trễ hoặc bị lặp và thiết kế cơ chế dự phòng khi thông báo hết hạn Redis không được nhận.

Sau bài học, bạn có thể:

- Giải thích `SessionDestroyedEvent` và mối quan hệ với các event xóa hoặc hết hạn.
- Đăng ký listener bằng `@EventListener` trong ứng dụng Spring.
- Liên kết tài nguyên bên ngoài với Session ID và thu hồi chúng theo cách idempotent.
- Phân biệt cleanup đồng bộ, bất đồng bộ và xử lý qua message broker.
- Hiểu vai trò của Redis keyspace notifications trong việc phát hiện session hết hạn.
- Thiết kế TTL dự phòng, tác vụ đối soát và kiểm thử cho hệ thống nhiều instance.
- Tránh dùng lifecycle event làm cơ chế duy nhất cho nghiệp vụ cần bảo đảm không mất dữ liệu.

## 1. Vì sao session kết thúc cần thu hồi tài nguyên bên ngoài?

Spring Session quản lý dữ liệu phiên trong repository như Redis. Nhưng một ứng dụng thực tế có thể tạo thêm tài nguyên trong các hệ thống khác trong suốt vòng đời của session.

Ví dụ, khi người dùng đăng nhập và mở trang theo dõi trực tiếp:

- Ứng dụng tạo một session trong Redis.
- Người dùng mở kết nối WebSocket.
- Một dịch vụ presence ghi nhận session đang trực tuyến.
- Một dịch vụ thông báo đăng ký subscription theo session.
- Một tiến trình tạo dữ liệu tạm hoặc khóa phục vụ thao tác đang diễn ra.

Khi người dùng đăng xuất, session bị invalidate. Khi người dùng rời đi mà không logout, session có thể hết hạn sau thời gian không hoạt động. Nếu các tài nguyên ngoài Redis không được dọn, chúng có thể tồn tại lâu hơn phiên gốc.

Hậu quả thường gặp:

- WebSocket connection vẫn mở dù phiên xác thực đã kết thúc.
- Người dùng vẫn xuất hiện trực tuyến trong hệ thống presence.
- Subscription tiếp tục nhận thông báo không cần thiết.
- Dữ liệu tạm, khóa hoặc bản ghi liên kết bị bỏ quên.
- Bộ đếm kết nối và metric phản ánh sai số người dùng đang hoạt động.

`SessionDestroyedEvent` giúp ứng dụng nhận biết session đã kết thúc và khởi động quy trình thu hồi những tài nguyên gắn với phiên đó.

Điều quan trọng là event chỉ là tín hiệu vòng đời. Nó không tự đóng socket, xóa subscription hay thu hồi tài nguyên trong hệ thống khác. Ứng dụng phải xây dựng listener và service thực hiện các thao tác đó.

## 2. SessionDestroyedEvent là gì?

Spring Session cung cấp các sự kiện vòng đời trong package `org.springframework.session.events`. Hai sự kiện kết thúc quan trọng là:

- `SessionDeletedEvent`: session bị xóa, thường do ứng dụng invalidate hoặc repository thực hiện thao tác xóa.
- `SessionExpiredEvent`: session được nhận diện là đã hết hạn theo chính sách thời gian.

Cả hai là các dạng cụ thể của `SessionDestroyedEvent`. Vì vậy, một listener nhận lớp cơ sở có thể xử lý chung các trường hợp session kết thúc.

| Event | Tình huống thường gặp | Ý nghĩa với cleanup |
|---|---|---|
| `SessionDeletedEvent` | Người dùng logout, quản trị viên xóa session | Thu hồi tài nguyên gắn với phiên bị xóa |
| `SessionExpiredEvent` | Session vượt quá thời gian không hoạt động hoặc TTL | Thu hồi tài nguyên gắn với phiên hết hạn |
| `SessionDestroyedEvent` | Lớp event cơ sở cho các trường hợp kết thúc | Điểm nhận chung cho cleanup |

Sự kiện tạo phiên `SessionCreatedEvent` không phải sự kiện kết thúc và không thay thế `SessionDestroyedEvent`.

### Event cung cấp thông tin gì?

Các event Spring Session thường cung cấp Session ID thông qua `getSessionId()` và có thể cung cấp thuộc tính session qua `getSessionAttributes()` theo API của phiên bản đang dùng.

Session ID là khóa tương quan thuận tiện để tìm tài nguyên phụ. Tuy nhiên, không nên ghi ID này vào log công khai vì nó có thể được dùng như thông tin bearer để tiếp tục phiên.

Chỉ đọc các thuộc tính cần thiết. Không serialize hoặc ghi toàn bộ session attributes vào log hay message nếu chúng có thể chứa thông tin xác thực, dữ liệu cá nhân hoặc object lớn.

### Phân biệt nguyên nhân kết thúc

Nếu chỉ cần dọn chung tài nguyên, listener nhận `SessionDestroyedEvent` thường là đủ. Nếu cần ghi nhận lý do kết thúc, có thể lắng nghe `SessionDeletedEvent` và `SessionExpiredEvent` riêng.

Cần tránh đăng ký cả listener cho lớp cơ sở và listener cho lớp con rồi thực hiện cùng một tác vụ hai lần. Event listener của Spring có thể khớp theo kiểu lớp cha; một event thuộc lớp con có thể kích hoạt cả hai handler.

Một cách tổ chức là dùng một service cleanup chung, còn listener cụ thể chỉ truyền vào Session ID và lý do. Nếu có nhiều handler, service cần idempotent để việc gọi lặp không gây tác động sai.

## 3. Luồng từ Redis expiration đến listener

Với repository Redis có hỗ trợ session event, Spring Session có thể nhận thông báo từ Redis keyspace notifications khi key liên quan đến session bị xóa hoặc hết hạn.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant A as Spring Application
    participant R as Redis Session Repository
    participant D as Redis
    participant L as Session Lifecycle Listener
    participant X as External Resource Service

    A->>R: Tạo hoặc cập nhật session
    R->>D: Lưu session và TTL
    Note over D: Session key hết hạn
    D-->>R: Keyspace expiration notification
    R->>L: Publish SessionExpiredEvent
    L->>X: Thu hồi tài nguyên theo Session ID
    X-->>L: Xác nhận hoặc kết quả xử lý
~~~

Với thao tác logout, repository có thể phát event xóa khi ứng dụng invalidate session. Với hết hạn tự động, Redis cần phát notification mà repository đang lắng nghe.

Không phải mọi repository Redis hoặc mọi cấu hình đều phát event giống nhau. Khả năng này thường gắn với repository hỗ trợ index/event như `RedisIndexedSessionRepository` và cấu hình listener tương ứng. Cần xác nhận repository thực tế của ứng dụng và phiên bản Spring Session.

### Redis keyspace notifications

Redis keyspace notifications là cơ chế publish/subscribe thông báo về các thay đổi trên key. Để nhận event expiration, Redis phải bật nhóm notification tương ứng.

Một cấu hình thường gặp trong tài liệu Spring Session là:

~~~text
notify-keyspace-events Egx
~~~

Các ký tự cấu hình biểu thị nhóm thông báo keyevent, lệnh generic và sự kiện expired. Cấu hình cụ thể cần đối chiếu tài liệu của phiên bản Spring Session/Redis đang dùng.

Có thể kiểm tra cấu hình trên Redis tự quản lý bằng:

~~~text
CONFIG GET notify-keyspace-events
~~~

Một số Redis managed service không cho phép ứng dụng chạy lệnh `CONFIG SET`. Khi đó, quản trị viên cần bật notification qua cấu hình dịch vụ hoặc control plane của nhà cung cấp. Không nên giả định ứng dụng có thể tự thay đổi cấu hình server.

Nếu keyspace notification không được bật hoặc listener không nhận được thông báo, dữ liệu session vẫn có thể hết hạn theo TTL, nhưng listener cleanup có thể không chạy. Đây là lý do cần có cơ chế dự phòng cho tài nguyên bên ngoài.

## 4. Đăng ký listener bằng @EventListener

Một component Spring có thể nhận `SessionDestroyedEvent` bằng `@EventListener`.

Ví dụ listener tối giản:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionDestroyedEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionDestroyedListener {

    private final SessionResourceCleanupService cleanupService;

    public SessionDestroyedListener(
            SessionResourceCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onSessionDestroyed(SessionDestroyedEvent event) {
        String sessionId = event.getSessionId();

        cleanupService.cleanupBySessionId(sessionId);
    }
}
~~~

Listener chỉ nhận event, lấy định danh và giao công việc cho service. Cách tổ chức này giúp tách phần tích hợp Spring Session khỏi quy tắc cleanup của ứng dụng.

Một service có thể quản lý các thao tác thu hồi:

~~~java
import org.springframework.stereotype.Service;

@Service
public class SessionResourceCleanupService {

    private final SessionResourceRepository resourceRepository;

    public SessionResourceCleanupService(
            SessionResourceRepository resourceRepository) {
        this.resourceRepository = resourceRepository;
    }

    public void cleanupBySessionId(String sessionId) {
        resourceRepository.deleteAllBySessionId(sessionId);
    }
}
~~~

`SessionResourceRepository` là abstraction do ứng dụng định nghĩa để xóa các bản ghi tài nguyên phụ theo Session ID. Nó có thể là repository JDBC, Redis key namespace riêng hoặc client gọi một dịch vụ quản lý tài nguyên.

Ví dụ trên chỉ minh họa cấu trúc. Trong hệ thống thật, cần triển khai repository phù hợp với loại tài nguyên và bảo đảm thao tác xóa có thể chạy nhiều lần.

### Lắng nghe riêng event hết hạn

Nếu ứng dụng chỉ muốn phản ứng với session hết hạn, có thể nhận `SessionExpiredEvent`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionExpiredListener {

    private final SessionResourceCleanupService cleanupService;

    public SessionExpiredListener(
            SessionResourceCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onSessionExpired(SessionExpiredEvent event) {
        cleanupService.cleanupBySessionId(event.getSessionId());
    }
}
~~~

Nếu đã có listener cho `SessionDestroyedEvent` thực hiện cùng cleanup, không nên thêm listener hết hạn này mà không thiết kế chống xử lý trùng. Hãy chọn một điểm nhận chung hoặc tách rõ tác vụ theo lý do kết thúc.

## 5. Liên kết tài nguyên ngoài với Session ID

Muốn thu hồi tài nguyên khi session kết thúc, ứng dụng cần biết tài nguyên nào thuộc về Session ID nào.

Một mô hình phổ biến là lưu mapping:

| Session ID | Loại tài nguyên | Định danh tài nguyên |
|---|---|---|
| session-A | WebSocket | connection-101 |
| session-A | Presence | user-presence-42 |
| session-A | Subscription | subscription-8 |
| session-B | WebSocket | connection-205 |

Khi nhận event cho session-A, cleanup service tìm các mapping theo ID đó rồi thu hồi tài nguyên tương ứng.

### Tạo mapping khi tài nguyên được mở

Ví dụ khi một kết nối WebSocket được xác thực bằng session, ứng dụng có thể ghi nhận liên kết giữa Session ID và connection ID:

~~~java
public void registerConnection(
        String sessionId,
        String connectionId) {
    resourceRepository.save(sessionId, "WEBSOCKET", connectionId);
}
~~~

Khi socket đóng bình thường, ứng dụng cũng nên xóa mapping ngay. Event session destroyed là đường thu hồi bổ sung khi client mất kết nối bất ngờ hoặc phiên hết hạn.

Không nên lưu object socket, thread, executor hay connection thật vào session attributes. Chỉ lưu định danh hoặc metadata nhỏ trong registry do ứng dụng quản lý.

### Phạm vi theo session hay theo user?

Một người dùng có thể đăng nhập từ nhiều thiết bị hoặc trình duyệt. Mỗi thiết bị có thể có session riêng. Nếu cleanup theo user ID, logout ở một thiết bị có thể vô tình đóng kết nối của các thiết bị còn lại.

Thông thường:

- Dùng Session ID để thu hồi tài nguyên thuộc đúng phiên.
- Dùng user ID để thống kê hoặc áp dụng chính sách toàn tài khoản.
- Chỉ cleanup theo user ID khi nghiệp vụ yêu cầu logout mọi phiên hoặc thu hồi mọi kết nối của người dùng.

Không nhầm một session với toàn bộ tài khoản người dùng.

## 6. Ví dụ: thu hồi WebSocket và trạng thái presence

Giả sử ứng dụng có một dịch vụ quản lý kết nối. Mỗi kết nối WebSocket được gắn với Session ID đã xác thực.

Khi session kết thúc, listener có thể yêu cầu dịch vụ đóng các kết nối được đăng ký cho ID đó:

~~~java
@Service
public class WebSocketCleanupService {

    private final SessionConnectionRegistry registry;

    public WebSocketCleanupService(SessionConnectionRegistry registry) {
        this.registry = registry;
    }

    public void closeConnectionsForSession(String sessionId) {
        var connectionIds = registry.findConnections(sessionId);

        for (String connectionId : connectionIds) {
            registry.closeIfOpen(connectionId);
        }

        registry.removeSessionMappings(sessionId);
    }
}
~~~

Trong môi trường một instance, registry có thể nằm trong bộ nhớ. Nhưng khi ứng dụng chạy nhiều instance, kết nối WebSocket có thể đang được giữ ở một instance khác.

Một listener chạy ở App A không thể đóng trực tiếp socket nằm trong bộ nhớ App B. Cần một cơ chế chia sẻ hoặc định tuyến:

1. Registry dùng chung lưu Session ID, connection ID và instance đang giữ socket.
2. Cleanup service phát lệnh đến instance sở hữu connection.
3. Instance đó đóng socket cục bộ và xác nhận trạng thái.
4. Mapping được xóa hoặc đánh dấu đã thu hồi.

Có thể dùng message broker, pub/sub, distributed registry hoặc một dịch vụ connection manager để chuyển lệnh đến đúng instance.

### Presence và subscription

Tài nguyên presence thường có thể biểu diễn bằng một mapping hoặc lease có TTL. Khi session hết hạn, listener xóa mapping; TTL là lớp bảo vệ bổ sung nếu event bị bỏ lỡ.

Subscription đến message broker cũng nên được quản lý theo định danh có thể thu hồi. Khi session kết thúc, cleanup service hủy subscription và xóa mapping. Nếu subscription nằm trong một dịch vụ bên ngoài, nên dùng API idempotent để lệnh hủy có thể gửi lại khi cần.

## 7. Cleanup phải idempotent

Trong hệ thống phân tán, không nên giả định một event chỉ được xử lý đúng một lần. Có thể xảy ra:

- Event được phát lại hoặc listener nhận trùng.
- Hai đường xử lý cùng yêu cầu cleanup, ví dụ logout và expiration.
- Service ngoài đã xóa tài nguyên nhưng response bị mất.
- Một instance xử lý xong nhưng không kịp ghi nhận kết quả.
- Tác vụ retry gửi lại lệnh xóa.

Idempotent nghĩa là gọi cùng thao tác nhiều lần vẫn đưa hệ thống về cùng trạng thái cuối.

Ví dụ, câu lệnh xóa mapping theo Session ID nên chấp nhận trường hợp không còn mapping. API đóng connection nên trả kết quả hợp lệ cả khi connection đã đóng. API hủy subscription nên chấp nhận subscription không tồn tại.

Một quy tắc thiết kế:

~~~java
public void cleanupBySessionId(String sessionId) {
    // DELETE ... WHERE session_id = ? là thao tác có thể lặp lại.
    resourceRepository.deleteAllBySessionId(sessionId);

    // Hủy subscription theo ID; không lỗi nếu subscription đã bị hủy.
    subscriptionService.cancelAllForSession(sessionId);
}
~~~

Nếu một thao tác không idempotent, cần khóa chống trùng hoặc lưu trạng thái xử lý theo event key. Không dựa vào biến boolean trong bộ nhớ của một instance vì instance khác không nhìn thấy biến đó.

### Tránh xóa nhầm tài nguyên của phiên mới

Nếu một Session ID được thay đổi sau đăng nhập hoặc nâng quyền, ứng dụng cần hiểu mapping tài nguyên được gắn với ID cũ hay ID mới. Không nên giả định thay đổi ID luôn tương đương logout hoặc session bị phá hủy.

Nếu resource mapping phải tồn tại qua thao tác đổi ID, cần cập nhật mapping trong luồng đổi ID hoặc dùng một correlation ID nội bộ ổn định trong suốt vòng đời logic. Cleanup của session cũ không được xóa nhầm tài nguyên đã được chuyển sang định danh mới.

## 8. Không thực hiện công việc chậm trực tiếp trong listener

Một listener có thể được gọi trong luồng xử lý event của Spring hoặc trong luồng nhận notification từ repository. Nếu listener thực hiện nhiều lời gọi mạng đồng bộ, thời gian xử lý event tăng và có thể làm chậm luồng nhận event.

Tác vụ cleanup nên được phân loại:

| Loại công việc | Cách xử lý phù hợp |
|---|---|
| Xóa một mapping nhỏ trong cùng database | Có thể xử lý trực tiếp nếu thao tác nhanh |
| Xóa nhiều bản ghi hoặc cache phụ | Giao cho service, giới hạn thời gian và có metric |
| Gọi API bên ngoài hoặc đóng socket ở instance khác | Phát lệnh đến worker hoặc message broker |
| Nghiệp vụ bắt buộc không mất thông báo | Dùng cơ chế message bền vững, retry và đối soát |
| Công việc có thể hoàn tất bằng TTL | Dùng TTL làm dự phòng, event chỉ giúp thu hồi sớm |

Có thể dùng `@Async` cho công việc không yêu cầu bảo đảm giao nhận bền vững, nhưng cần hiểu rằng executor trong bộ nhớ không phải message broker. Nếu ứng dụng dừng trước khi task chạy, task có thể mất.

Ví dụ chỉ minh họa việc chuyển tác vụ sang executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncSessionCleanupService {

    @Async
    public void cleanup(String sessionId) {
        // Thực hiện cleanup có giới hạn thời gian và idempotent.
    }
}
~~~

Để dùng `@Async`, ứng dụng cần bật async processing và cấu hình executor phù hợp. Với tác vụ quan trọng, nên phát command vào hàng đợi bền vững thay vì chỉ dùng async executor.

## 9. Redis expiration event không phải thông điệp bền vững

Redis keyspace notifications được phát qua publish/subscribe. Cơ chế này giúp ứng dụng nhận biết key đã hết hạn hoặc bị xóa, nhưng không phải một log sự kiện bền vững có thể phát lại toàn bộ khi consumer mất kết nối.

Nếu listener container hoặc ứng dụng không hoạt động tại thời điểm notification được phát, cleanup event có thể bị bỏ lỡ. Khi đó, session key vẫn có thể hết hạn, nhưng tài nguyên bên ngoài có thể còn tồn tại.

Do đó, hãy kết hợp event với các biện pháp dự phòng:

- Đặt TTL cho resource phụ nếu tài nguyên có thể tự hết hạn.
- Dùng lease có thời hạn thay cho trạng thái presence tồn tại vô hạn.
- Chạy reconciliation job để tìm mapping gắn với session không còn hợp lệ.
- Có API cleanup có thể retry và idempotent.
- Theo dõi số event nhận được, số cleanup thành công, lỗi và độ trễ.
- Nếu cần bảo đảm giao nhận, chuyển tác vụ sang message broker hoặc outbox có lưu trữ bền vững.

### TTL dự phòng cho tài nguyên phụ

Ví dụ, một mapping presence có thể có TTL ngắn và được gia hạn khi session còn hoạt động. Nếu listener không nhận event, mapping vẫn tự hết hạn.

~~~text
Session TTL:       30 phút
Presence lease:    35 phút
Cleanup event:     Xóa presence ngay khi session kết thúc
Reconciliation:    Tìm và dọn mapping quá hạn còn sót
~~~

Thời hạn minh họa cần được chọn theo yêu cầu sản phẩm. TTL resource không nên ngắn hơn mức ứng dụng cho phép người dùng hoạt động bình thường, nếu không trạng thái phụ có thể biến mất khi session vẫn còn hợp lệ.

## 10. Xử lý lỗi và retry

Cleanup có thể thất bại vì dịch vụ ngoài không khả dụng, timeout, lỗi mạng hoặc dữ liệu mapping không còn tồn tại.

Một chiến lược xử lý nên xác định:

1. Lỗi nào có thể retry, ví dụ timeout tạm thời hoặc HTTP 5xx.
2. Lỗi nào không cần retry, ví dụ tài nguyên đã được xóa.
3. Số lần retry và khoảng backoff.
4. Cách ghi nhận command đã xử lý.
5. Cách chuyển tác vụ thất bại kéo dài sang dead-letter queue hoặc danh sách cần đối soát.
6. Metric và cảnh báo cho cleanup bị tồn đọng.

Không retry vô hạn trong listener. Retry đồng bộ có thể giữ luồng xử lý lâu và làm tắc listener container. Với công việc bên ngoài, phát một command có khóa idempotency đến worker thường dễ kiểm soát hơn.

Một event cleanup có thể được biểu diễn thành command nhỏ:

~~~java
public record CleanupSessionResources(String sessionId) {
}
~~~

Command chỉ nên chứa dữ liệu cần thiết để tìm tài nguyên. Không gửi toàn bộ session attributes nếu worker không cần chúng.

Nếu dùng message broker, message có thể được giao nhiều lần. Consumer vẫn phải idempotent và chỉ đánh dấu hoàn tất sau khi tác vụ được xử lý theo chính sách của hệ thống.

## 11. Đăng ký event listener và cấu hình Redis cần kiểm tra

Để cleanup theo event hết hạn hoạt động, hãy xác minh toàn bộ đường đi:

- Ứng dụng đang dùng repository Redis có hỗ trợ phát event session cần thiết.
- Redis keyspace notifications cho expiration đã được bật.
- Listener container và connection đến Redis hoạt động.
- Spring application context đã đăng ký listener.
- Session timeout và TTL được cấu hình đúng.
- Listener dùng đúng event class và lấy Session ID đúng cách.
- Resource registry có mapping theo Session ID.
- Cleanup service có thể được gọi lặp lại và có timeout hợp lý.

Không nên chỉ nhìn thấy key Redis đã biến mất rồi kết luận listener đã chạy. Cần quan sát event và xác minh trạng thái tài nguyên ngoài thực tế.

## 12. Kiểm thử SessionDestroyedEvent và cleanup

Nên có unit test cho cleanup service và integration test cho event được phát từ repository.

### Unit test cho cleanup service

Kiểm tra các trường hợp:

- Có nhiều tài nguyên gắn với một Session ID.
- Không có tài nguyên nào.
- Tài nguyên đã bị xóa trước đó.
- Cùng lệnh cleanup được gọi nhiều lần.
- Một dịch vụ ngoài tạm thời lỗi.

Kết quả cần bảo đảm việc gọi lặp không làm phát sinh lỗi nghiệp vụ hoặc xóa nhầm tài nguyên của session khác.

### Integration test cho session bị xóa

1. Khởi động Spring context có Spring Session Redis.
2. Tạo session và ghi thuộc tính.
3. Đăng ký listener test để thu event.
4. Gọi invalidate hoặc endpoint logout.
5. Xác minh event xóa hoặc event destroyed được nhận theo repository.
6. Xác minh resource registry không còn tài nguyên gắn với Session ID đó.

### Integration test cho session hết hạn

1. Dùng Redis thật hoặc Testcontainers.
2. Cấu hình timeout ngắn trong test.
3. Bảo đảm Redis keyspace notifications được bật.
4. Tạo session và ghi resource mapping có TTL.
5. Chờ có giới hạn đến khi nhận event hết hạn.
6. Xác minh cleanup đã chạy và tài nguyên ngoài được thu hồi.
7. Nếu event không được phát theo repository đang dùng, xác minh hành vi hết hạn của session và ghi nhận giới hạn hỗ trợ.

Dùng polling có giới hạn hoặc cơ chế await thay vì một lần sleep cố định rồi giả định event đã đến. Thời điểm Redis phát notification có thể khác thời điểm TTL đạt đến.

### Integration test nhiều instance

Khởi động hai application instance dùng chung Redis. Tạo session ở App A, đăng ký tài nguyên ở App B hoặc một resource service dùng chung, sau đó làm session hết hạn. Xác minh event được xử lý và lệnh cleanup đến đúng instance hoặc dịch vụ đang sở hữu tài nguyên.

Test này đặc biệt quan trọng với WebSocket hoặc connection local, vì listener ở một instance không thể trực tiếp truy cập bộ nhớ của instance khác.

## 13. Những lỗi thường gặp

**Chỉ cleanup khi logout.**  
Session có thể hết hạn mà không đi qua endpoint logout. Hãy xử lý cả event hết hạn hoặc có cơ chế đối soát.

**Cho rằng mọi Redis repository đều phát cùng loại event.**  
Khả năng phát event phụ thuộc implementation và cấu hình. Xác minh repository đang dùng và kiểm thử tích hợp.

**Redis không phát expiration notification.**  
Kiểm tra cấu hình keyspace notifications và quyền quản trị Redis. Redis managed có thể yêu cầu bật qua control plane.

**Listener xóa tài nguyên của cả user.**  
Một người có thể có nhiều session. Thông thường cleanup nên giới hạn theo Session ID.

**Listener gọi API ngoài đồng bộ và bị treo.**  
Đặt timeout, giới hạn công việc trong listener và chuyển tác vụ dài sang worker hoặc message broker.

**Event bị bỏ lỡ nhưng tài nguyên tồn tại vô hạn.**  
Dùng TTL/lease dự phòng, reconciliation job và metric theo dõi tài nguyên mồ côi.

**Cleanup chạy nhiều lần gây lỗi.**  
Thiết kế thao tác idempotent, dùng idempotency key hoặc trạng thái xử lý dùng chung.

**Dùng SessionDestroyedEvent để thay thế audit logout.**  
Event hết hạn và event xóa có thể có nguyên nhân khác nhau; application event cũng không bảo đảm lưu bền vững. Audit quan trọng nên được ghi trong luồng nghiệp vụ hoặc cơ chế bền vững riêng.

## 14. Checklist thiết kế cleanup tài nguyên bên ngoài

Trước khi triển khai, hãy xác nhận:

- Tài nguyên nào được liên kết với session?
- Mapping được lưu ở đâu và có thể tra cứu bằng Session ID không?
- Tài nguyên có thể tự hết hạn bằng TTL hoặc lease không?
- Listener có nhận cả xóa chủ động và hết hạn không?
- Redis keyspace notifications đã được bật và kiểm thử chưa?
- Cleanup có idempotent không?
- Listener có thực hiện lời gọi mạng dài không?
- Tài nguyên có thể nằm trên instance khác không?
- Có message broker hoặc cơ chế retry cho tác vụ quan trọng không?
- Có reconciliation job để dọn tài nguyên mồ côi không?
- Có metric, log đã che Session ID và cảnh báo lỗi cleanup không?

## 15. Tự kiểm tra

1. `SessionDestroyedEvent` biểu diễn điều gì?
2. `SessionDeletedEvent` và `SessionExpiredEvent` khác nhau như thế nào?
3. Vì sao listener nhận lớp cơ sở có thể xử lý chung nhiều loại kết thúc session?
4. Redis keyspace notifications hỗ trợ phát hiện điều gì?
5. Vì sao expiration event không phải message bền vững?
6. Làm thế nào để liên kết WebSocket hoặc subscription với một session?
7. Vì sao cleanup nên idempotent?
8. Vì sao listener ở App A không thể tự đóng socket đang nằm trong bộ nhớ App B?
9. TTL dự phòng và reconciliation job giúp xử lý trường hợp nào?
10. Khi nào nên chuyển cleanup sang message broker?
11. Vì sao không nên ghi Session ID hoặc toàn bộ session attributes vào log?
12. Cần kiểm thử những gì để xác minh tài nguyên ngoài được thu hồi khi session hết hạn?

### Gợi ý trả lời

1. Đây là lớp event biểu diễn một session đã kết thúc.
2. Deleted thường do thao tác xóa hoặc invalidate; expired do session vượt thời hạn không hoạt động.
3. Hai event kết thúc cụ thể là các dạng của lớp cơ sở, nên listener có thể nhận chúng qua kiểu cha.
4. Chúng cho phép ứng dụng nhận notification khi key Redis bị xóa hoặc hết hạn, nếu cấu hình phù hợp.
5. Pub/sub không lưu event để phát lại đầy đủ khi consumer mất kết nối.
6. Lưu mapping từ Session ID đến connection ID hoặc resource ID trong registry có thể truy cập từ instance cần cleanup.
7. Vì event hoặc command có thể được xử lý lặp, retry hoặc đến từ nhiều đường xử lý.
8. Socket thuộc bộ nhớ và runtime của App B; App A cần gửi lệnh qua registry hoặc message broker đến đúng instance.
9. Chúng giúp thu hồi tài nguyên khi event bị bỏ lỡ hoặc cleanup chưa hoàn tất.
10. Khi cleanup gọi dịch vụ ngoài, cần retry hoặc không được phép mất tác vụ.
11. Session ID là bí mật dạng bearer; session attributes có thể chứa dữ liệu nhạy cảm.
12. Dùng Redis thật, bật notification, tạo session/resource mapping, chờ event, xác minh cleanup và kiểm thử retry/idempotency.

## Kết luận

`SessionDestroyedEvent` là điểm tích hợp để ứng dụng thu hồi tài nguyên gắn với một session sau khi phiên bị xóa hoặc hết hạn. Listener có thể nhận event bằng `@EventListener`, lấy Session ID và chuyển công việc cho service cleanup. Các tài nguyên như WebSocket, presence, subscription và dữ liệu tạm cần được liên kết rõ với Session ID để thu hồi đúng phạm vi.

Trong môi trường Redis, event hết hạn phụ thuộc repository có hỗ trợ event và cấu hình keyspace notifications. Vì notification pub/sub có thể bị bỏ lỡ, cleanup quan trọng cần idempotent, có TTL hoặc lease dự phòng, retry và reconciliation. Với tài nguyên nằm trên instance khác hoặc dịch vụ bên ngoài, hãy định tuyến lệnh qua registry hoặc message broker; không để listener đồng bộ thực hiện công việc mạng kéo dài. Event giúp thu hồi sớm, còn chính sách kiểm tra session hợp lệ và cơ chế lưu bền vững vẫn phải được thiết kế riêng.

