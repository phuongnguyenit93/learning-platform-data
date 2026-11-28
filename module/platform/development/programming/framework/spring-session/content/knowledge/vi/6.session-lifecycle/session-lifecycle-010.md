# Sự kiện tạo, xóa, hết hạn và phá hủy phiên

## Mục tiêu bài học

Session có vòng đời từ lúc được tạo, được sử dụng, được gia hạn cho đến khi bị xóa hoặc hết hạn. Trong ứng dụng Spring Session, các sự kiện vòng đời giúp những thành phần khác phản ứng khi phiên được tạo hoặc kết thúc, ví dụ ghi nhận số phiên đang hoạt động, thu hồi dữ liệu phụ, giải phóng tài nguyên hoặc cập nhật trạng thái vận hành.

Sau bài học, bạn có thể:

- Phân biệt tạo session, xóa session chủ động, hết hạn session và sự kiện phá hủy phiên.
- Nhận biết các lớp sự kiện Spring Session như `SessionCreatedEvent`, `SessionDeletedEvent`, `SessionExpiredEvent` và `SessionDestroyedEvent`.
- Viết listener bằng @EventListener hoặc cơ chế listener tương ứng.
- Hiểu cách sự kiện Spring Session được chuyển thành callback Servlet `HttpSessionListener`.
- Nhận biết ảnh hưởng của repository, Redis keyspace notifications và tác vụ dọn dẹp JDBC đến việc phát sự kiện.
- Thiết kế listener idempotent, an toàn khi chạy nhiều instance và không phụ thuộc vào thời điểm hết hạn tuyệt đối.
- Kiểm thử các luồng tạo, invalidate, expire và xử lý sự kiện trong môi trường tích hợp.

## 1. Vì sao cần sự kiện vòng đời session?

Một session không chỉ là một tập thuộc tính được lưu trong Redis hoặc JDBC. Nó còn có thể gắn với trạng thái đăng nhập, thông tin giỏ hàng tạm, dữ liệu quy trình nhiều bước và một số tài nguyên phụ trợ.

Khi session được tạo, ứng dụng có thể cần ghi nhận thời điểm bắt đầu hoặc khởi tạo dữ liệu mặc định. Khi session kết thúc, ứng dụng có thể cần xóa trạng thái tạm, thu hồi một liên kết hoặc cập nhật số liệu vận hành.

Nếu mọi controller đều phải tự gọi các hàm phụ mỗi khi tạo hoặc xóa session, logic vòng đời sẽ bị phân tán. Có những session hết hạn do timeout hoặc bị xóa bởi tác vụ quản trị mà không đi qua endpoint đăng xuất của ứng dụng. Một cơ chế sự kiện giúp tập trung phản ứng vào các listener.

Ví dụ, một ứng dụng quản lý phiên có thể cần:

- Ghi nhận một session mới được tạo để đo số phiên mới theo thời gian.
- Cập nhật một trạng thái phụ khi người dùng đăng xuất.
- Thu hồi dữ liệu tạm liên quan khi session hết hạn.
- Phát hiện session kết thúc để giải phóng tài nguyên được quản lý riêng.
- Gửi tín hiệu cho hệ thống quan sát để theo dõi vòng đời phiên.

Sự kiện vòng đời cung cấp thông tin về việc session đã được tạo hoặc kết thúc. Nó không thay thế xác thực, phân quyền, transaction nghiệp vụ hay cơ chế lưu trữ bền vững.

## 2. Phân biệt các mốc trong vòng đời

Một vòng đời session thường có các mốc sau:

1. **Tạo**: ứng dụng hoặc framework yêu cầu tạo một session mới.
2. **Sử dụng**: request tiếp theo gửi định danh phiên, repository khôi phục session và ứng dụng đọc hoặc cập nhật thuộc tính.
3. **Gia hạn**: hoạt động của request có thể cập nhật thời điểm truy cập và thời gian hết hạn theo cấu hình.
4. **Xóa chủ động**: ứng dụng invalidate session, quản trị viên xóa session hoặc repository nhận lệnh xóa.
5. **Hết hạn**: session không còn được xem là hợp lệ sau thời gian không hoạt động được cấu hình.
6. **Phá hủy**: trạng thái phiên được kết thúc; Spring Session biểu diễn các nguyên nhân kết thúc bằng những loại sự kiện cụ thể.

Cần phân biệt hai nguyên nhân thường gặp:

| Nguyên nhân | Ý nghĩa |
|---|---|
| Xóa (deleted) | Có thao tác xóa session, thường do ứng dụng gọi invalidate hoặc repository xóa theo ID |
| Hết hạn (expired) | Session vượt quá thời hạn không hoạt động hoặc TTL và được repository nhận diện là hết hạn |

Cả hai đều là kết thúc session, nhưng nguyên nhân khác nhau. Ứng dụng có thể cần phân biệt chúng để thống kê hoặc áp dụng quy tắc phụ. Ví dụ, người dùng chủ động đăng xuất là một hành động khác với việc phiên tự hết hạn do không hoạt động.

Không nên đồng nhất việc trình duyệt đóng cửa sổ với sự kiện session bị xóa. Trình duyệt có thể ngừng gửi cookie, nhưng dữ liệu ở Redis hoặc JDBC vẫn có thể tồn tại cho đến khi timeout hoặc tác vụ dọn dẹp xử lý.

## 3. Các sự kiện Spring Session

Spring Session cung cấp các event class trong package `org.springframework.session.events`. Những sự kiện quan trọng gồm:

| Sự kiện | Ý nghĩa |
|---|---|
| `SessionCreatedEvent` | Một session mới được tạo |
| `SessionDeletedEvent` | Một session bị xóa chủ động hoặc bị repository xóa |
| `SessionExpiredEvent` | Một session được nhận diện là đã hết hạn |
| `SessionDestroyedEvent` | Lớp sự kiện cơ sở biểu diễn một session đã kết thúc |

`SessionDeletedEvent` và `SessionExpiredEvent` là những dạng sự kiện phá hủy session. Vì vậy, một listener nhận `SessionDestroyedEvent` có thể xử lý chung cả hai loại. Nếu cần phân biệt nguyên nhân, hãy lắng nghe từng lớp cụ thể.

### SessionCreatedEvent

`SessionCreatedEvent` được phát khi một session mới được tạo và được repository xử lý theo cơ chế của implementation đang dùng. Listener có thể dùng sự kiện này để ghi nhận việc tạo phiên hoặc khởi tạo trạng thái phụ.

Thông tin quan trọng nhất thường là Session ID. Không nên ghi toàn bộ ID vào log công khai vì nó có thể được dùng như một bí mật dạng bearer để tiếp tục phiên.

### SessionDeletedEvent

`SessionDeletedEvent` biểu diễn việc session bị xóa. Trường hợp thường gặp là ứng dụng gọi:

~~~java
HttpSession session = request.getSession(false);

if (session != null) {
    session.invalidate();
}
~~~

Khi thao tác xóa được repository xử lý, Spring Session có thể phát sự kiện xóa tương ứng. Listener có thể nhận biết phiên đã bị kết thúc do thao tác xóa.

### SessionExpiredEvent

`SessionExpiredEvent` biểu diễn việc session hết hạn. Nguyên nhân thường là vượt quá thời gian không hoạt động được cấu hình hoặc TTL của repository.

Thời điểm listener nhận event không nhất thiết trùng chính xác với mili giây timeout vừa đạt đến. Repository có thể phát hiện hết hạn khi truy cập, khi Redis gửi thông báo keyspace, hoặc khi tác vụ dọn dẹp chạy. Cách phát hiện phụ thuộc loại repository.

### SessionDestroyedEvent

`SessionDestroyedEvent` là lớp cơ sở cho các sự kiện kết thúc session như deleted và expired. Sự kiện này cung cấp định danh phiên và thông tin thuộc tính session được implementation hỗ trợ.

Một listener xử lý lớp cơ sở có thể tập trung phần dọn dẹp chung. Nếu đồng thời đăng ký listener cho lớp cơ sở và từng lớp con, cùng một event có thể kích hoạt nhiều handler. Hãy thiết kế rõ phần xử lý chung và phần xử lý riêng để tránh gửi thông báo hoặc xóa dữ liệu hai lần.

## 4. Lắng nghe sự kiện bằng @EventListener

Spring application event cho phép component đăng ký phương thức xử lý mà không cần controller gọi trực tiếp listener.

Ví dụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.session.events.SessionDestroyedEvent;

@Component
public class SessionLifecycleListener {

    @EventListener
    public void onSessionCreated(SessionCreatedEvent event) {
        String sessionId = event.getSessionId();

        // Ghi nhận sự kiện tạo phiên bằng ID đã được bảo vệ.
        recordSessionCreated(sessionId);
    }

    @EventListener
    public void onSessionDestroyed(SessionDestroyedEvent event) {
        String sessionId = event.getSessionId();

        // Dọn trạng thái phụ gắn với phiên đã kết thúc.
        cleanupSessionState(sessionId, event.getSessionAttributes());
    }

    private void recordSessionCreated(String sessionId) {
        // Thay bằng dịch vụ thống kê hoặc audit phù hợp.
    }

    private void cleanupSessionState(
            String sessionId,
            java.util.Map<String, Object> attributes) {
        // Thay bằng thao tác dọn dẹp idempotent.
    }
}
~~~

Ví dụ trên minh họa cách tổ chức listener. Trong ứng dụng thật, không log trực tiếp Session ID. Nếu cần tương quan sự kiện, có thể dùng mã tham chiếu đã băm hoặc một correlation ID riêng không cho phép chiếm quyền phiên.

`SessionDestroyedEvent` cung cấp thông tin thuộc tính phiên theo API của Spring Session. Hãy chỉ đọc những thuộc tính cần cho công việc dọn dẹp và tránh serialize hoặc log toàn bộ map thuộc tính, vì nó có thể chứa dữ liệu nhạy cảm.

### Tách handler theo nguyên nhân kết thúc

Nếu ứng dụng cần phân biệt logout với timeout, có thể đăng ký handler riêng:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionEndReasonListener {

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        // Xử lý session bị xóa.
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        // Xử lý session hết hạn.
    }
}
~~~

Trong ví dụ này, không đăng ký thêm một handler `SessionDestroyedEvent` thực hiện cùng tác vụ phụ cho cả hai loại nếu không có cơ chế chống trùng. Nếu cần xử lý chung, hãy tạo một phương thức nội bộ dùng chung và gọi nó có chủ đích từ các handler cụ thể.

## 5. Sự kiện Spring Session và HttpSessionListener

Servlet API định nghĩa `HttpSessionListener` với hai callback:

- `sessionCreated(HttpSessionEvent event)` khi một HTTP session được tạo.
- `sessionDestroyed(HttpSessionEvent event)` khi một HTTP session bị hủy.

Đây là giao diện listener quen thuộc trong ứng dụng Servlet truyền thống. Khi dùng Spring Session, session được quản lý qua repository bên ngoài Servlet container. Do đó, không nên giả định mọi callback của container sẽ tự động phản ánh đầy đủ vòng đời session trong Redis hoặc JDBC.

Spring Session cung cấp `SessionEventHttpSessionListenerAdapter` để chuyển đổi sự kiện Spring Session thành callback Servlet `HttpSessionListener`. Adapter này cho phép tái sử dụng listener Servlet hiện có trong ứng dụng tích hợp Spring Session.

Luồng khái quát:

~~~text
Redis / JDBC Session Repository
              |
              v
     Spring Session Event
              |
              v
SessionEventHttpSessionListenerAdapter
              |
              v
       HttpSessionListener
       /                \
sessionCreated()    sessionDestroyed()
~~~

Khi sử dụng adapter, cần đăng ký adapter và các listener Servlet theo cách mà phiên bản Spring Session đang dùng yêu cầu. Adapter chuyển sự kiện Spring Session sang mô hình Servlet; nó không làm cho mọi repository tự động phát mọi loại event.

### Nên dùng listener nào?

| Nhu cầu | Lựa chọn |
|---|---|
| Xử lý riêng event Spring Session như expired và deleted | `@EventListener` với event class tương ứng |
| Tái sử dụng code đang triển khai `HttpSessionListener` | `SessionEventHttpSessionListenerAdapter` |
| Chỉ cần logic trong một endpoint logout | Gọi service logout/dọn dẹp trong luồng logout, đồng thời vẫn xử lý các trường hợp session kết thúc ngoài endpoint |
| Cần audit bền vững, không được mất sự kiện | Dùng cơ chế audit hoặc message/outbox bền vững phù hợp; không chỉ dựa vào application event trong bộ nhớ |

## 6. Repository ảnh hưởng đến khả năng phát sự kiện

Sự kiện được phát như thế nào phụ thuộc implementation của `SessionRepository` và cấu hình lưu trữ. Không nên giả định mọi repository có cùng khả năng phát event hoặc cùng thời điểm phát.

### Redis

Các repository Redis có thể sử dụng Redis keyspace notifications để nhận biết key session bị xóa hoặc hết hạn. Với implementation dựa trên index, Spring Session có thể theo dõi các sự kiện keyspace để phát event tương ứng.

Redis cần được cấu hình cho phép những nhóm notification mà implementation sử dụng. Cấu hình thường gặp trong tài liệu Spring Session cho các event xóa/hết hạn là:

~~~text
notify-keyspace-events Egx
~~~

Trong đó, các ký tự cấu hình biểu thị nhóm notification cho keyevent, generic command và expired event. Cấu hình cụ thể cần đối chiếu với phiên bản Spring Session và Redis repository đang dùng.

Một số dịch vụ Redis được quản lý không cho ứng dụng chạy lệnh CONFIG. Trong trường hợp đó, không thể trông chờ ứng dụng tự thay đổi cấu hình Redis. Quản trị viên cần bật notification ở cấu hình dịch vụ; ứng dụng có thể dùng cấu hình không tự động thay đổi server khi được hướng dẫn bởi tài liệu của phiên bản đang sử dụng.

Redis keyspace notifications được truyền qua cơ chế publish/subscribe. Đây không phải hàng đợi lưu trữ bền vững để phát lại mọi event sau khi consumer mất kết nối. Nếu listener ngừng hoạt động đúng lúc event được phát, ứng dụng có thể không nhận được thông báo đó. Vì vậy, không dùng event này làm nguồn duy nhất cho nghiệp vụ đòi hỏi audit không mất dữ liệu.

### JDBC

Repository JDBC lưu session trong bảng quan hệ. Việc hết hạn thường liên quan đến thời gian hết hạn được lưu và cơ chế dọn dẹp các bản ghi quá hạn. Event có thể được phát khi implementation nhận biết session đã hết hạn hoặc bị xóa, nhưng khả năng và thời điểm phụ thuộc repository và phiên bản.

Không nên suy luận rằng một row vừa vượt thời hạn là listener sẽ được gọi ngay. Có thể cần tác vụ cleanup chạy định kỳ hoặc một request truy cập khiến repository nhận ra phiên đã hết hạn.

Khi chọn JDBC, hãy kiểm tra tài liệu API của đúng phiên bản và viết integration test để xác nhận các event cần thiết thực sự được phát trong đường đi của ứng dụng.

### Repository tùy chỉnh

Nếu tự triển khai `SessionRepository` hoặc wrapper repository, trách nhiệm phát event cần được xác định rõ. Một repository chỉ lưu và trả session nhưng không phát lifecycle event sẽ không tự tạo ra đầy đủ sự kiện cho listener.

Khi viết repository tùy chỉnh, cần bảo đảm event phản ánh đúng thao tác đã được lưu thành công, tránh phát event trước khi transaction xóa session được commit nếu listener có thể thực hiện tác vụ phụ dựa trên trạng thái đã xóa.

## 7. Sự kiện hết hạn không nhất thiết đến đúng thời điểm timeout

Timeout của session thường biểu diễn khoảng thời gian không hoạt động tối đa. Khi thời hạn đã qua, session không còn hợp lệ theo chính sách. Nhưng việc listener nhận được sự kiện phụ thuộc cách repository phát hiện sự hết hạn.

Ví dụ:

- Redis có thể phát expired notification khi key hết hạn được xử lý bởi server.
- JDBC có thể cần một tác vụ cleanup xóa bản ghi đã quá hạn.
- Một repository có thể phát hiện session hết hạn khi request tiếp theo cố tải ID cũ.
- Một số repository hoặc cấu hình không cung cấp đầy đủ lifecycle event.

Vì vậy, không dùng thời điểm nhận event để đo chính xác thời điểm người dùng ngừng hoạt động. Nếu cần số liệu idle time chính xác, hãy lưu timestamp hoạt động hoặc dùng telemetry riêng.

Cũng không nên dựa vào event hết hạn để thực hiện thao tác có deadline cứng như thu hồi quyền truy cập ngay đúng giây. Việc kiểm tra session hợp lệ phải dựa trên repository và chính sách timeout tại thời điểm request được xử lý.

## 8. Listener phải idempotent và an toàn khi nhiều instance

Trong môi trường nhiều instance, event có thể được quan sát ở nhiều nơi tùy repository, cơ chế pub/sub và cấu hình. Một thao tác xử lý event cũng có thể được thử lại bởi hệ thống bên ngoài hoặc được kích hoạt trùng khi có nhiều đường xử lý.

**Idempotent** nghĩa là thực hiện cùng một thao tác nhiều lần vẫn tạo ra kết quả cuối tương đương một lần. Listener nên được thiết kế theo nguyên tắc này.

Ví dụ, thao tác xóa bản ghi phụ theo session ID nên có thể gọi nhiều lần mà không gây lỗi nghiệp vụ. Nếu gửi email hoặc phát thông báo, cần có khóa chống trùng hoặc cơ chế ghi nhận đã xử lý.

Một số nguyên tắc:

- Không giả định listener chỉ chạy đúng một lần trong toàn hệ thống.
- Không dùng bộ đếm trong bộ nhớ của một instance làm số liệu session toàn cụm.
- Không giữ lock cục bộ để bảo vệ tác vụ được nhiều instance xử lý.
- Nếu cần chống xử lý trùng, dùng khóa hoặc bảng idempotency dùng chung.
- Không thực hiện công việc mạng dài hoặc thao tác chặn trong listener nếu nó có thể làm chậm luồng phát event.
- Nếu chuyển listener sang xử lý bất đồng bộ, truyền dữ liệu event cần thiết một cách an toàn và không phụ thuộc object session đã hết vòng đời.

Sự kiện kết thúc phiên không nên là nơi duy nhất cập nhật dữ liệu nghiệp vụ quan trọng. Ví dụ, khi người dùng logout, luồng logout nên thu hồi trạng thái xác thực theo cơ chế chính. Listener có thể thực hiện thêm tác vụ phụ như thống kê, xóa cache hoặc phát telemetry.

## 9. Không dùng lifecycle event thay cho audit bền vững

Spring application event hữu ích để tách các thành phần trong cùng ứng dụng. Tuy nhiên, event listener trong tiến trình không mặc nhiên có bảo đảm giao nhận bền vững.

Nếu ứng dụng dừng đột ngột, listener lỗi hoặc Redis notification bị mất, một số tác vụ phụ có thể không chạy. Đối với tác vụ có yêu cầu kiểm toán, tài chính hoặc tuân thủ, cần dùng cơ chế lưu bền vững.

Một số lựa chọn:

- Ghi audit event trong cùng transaction với thao tác nghiệp vụ khi có thể.
- Dùng transactional outbox để lưu sự kiện cần phát cùng transaction dữ liệu.
- Dùng message broker có cơ chế lưu trữ, acknowledgement và retry phù hợp.
- Tạo tác vụ đối soát định kỳ để phát hiện dữ liệu phụ chưa được dọn.
- Ghi nhận trạng thái xử lý event bằng idempotency key.

Ví dụ, khi logout, ứng dụng có thể invalidate session và ghi nhận audit trong luồng nghiệp vụ. Listener `SessionDeletedEvent` có thể xóa cache phụ; nếu cache chưa được xóa do listener lỗi, một tác vụ reconciliation có thể dọn theo TTL hoặc đối chiếu dữ liệu.

## 10. Kiểm thử sự kiện tạo, xóa và hết hạn

Kiểm thử nên tách từng nguyên nhân kết thúc và dùng repository thật khi xác minh hành vi phụ thuộc repository.

### Kiểm thử tạo session

1. Khởi động application context có Spring Session.
2. Gửi request khiến ứng dụng gọi `getSession()`.
3. Chờ hoặc thu thập `SessionCreatedEvent`.
4. Xác minh event chứa định danh session mới.
5. Xác minh response trả cookie hoặc header theo resolver đã cấu hình.

Không nên chỉ gọi `new MockHttpSession()` rồi kết luận Spring Session repository đã phát event. Mock Servlet session không đại diện cho toàn bộ luồng repository.

### Kiểm thử xóa chủ động

1. Tạo session và lưu một thuộc tính.
2. Gửi request logout hoặc gọi invalidate trong test.
3. Xác minh repository không còn trả session theo ID cũ.
4. Xác minh `SessionDeletedEvent` hoặc event tương ứng được phát theo implementation.
5. Xác minh listener dọn dữ liệu phụ chỉ thực hiện kết quả mong muốn một lần.

### Kiểm thử hết hạn

Để kiểm thử timeout, không nên chỉ dùng `Thread.sleep` dài và kỳ vọng event luôn xuất hiện đúng mili giây. Thay vào đó:

- Cấu hình timeout ngắn trong test.
- Dùng repository thật hoặc integration test tương ứng.
- Chờ có giới hạn với polling/assertion thay vì sleep cố định dài.
- Xác minh session không còn tải được sau thời hạn.
- Xác minh event hết hạn nếu repository hỗ trợ và cấu hình notification/cleanup đúng.
- Đảm bảo test cô lập namespace hoặc bảng dữ liệu để không ảnh hưởng test khác.

### Kiểm thử listener idempotent

Phát cùng một loại event hoặc gọi tác vụ cleanup nhiều lần trong test và xác minh trạng thái cuối vẫn đúng. Nếu listener phát message, kiểm tra khóa chống trùng và trạng thái retry.

## 11. Ví dụ tổ chức service xử lý vòng đời

Không nên đặt toàn bộ logic nghiệp vụ trực tiếp trong listener. Listener nên chuyển event đến một service chuyên trách:

~~~java
import org.springframework.stereotype.Service;

@Service
public class SessionCleanupService {

    public void cleanup(String sessionId) {
        // Ví dụ:
        // - Xóa cache phụ gắn với phiên.
        // - Gỡ liên kết tạm.
        // - Đánh dấu trạng thái phụ đã kết thúc.
        //
        // Thao tác phải idempotent.
    }
}
~~~

Listener có thể gọi service:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionDestroyedEvent;
import org.springframework.stereotype.Component;

@Component
public class SessionCleanupListener {

    private final SessionCleanupService cleanupService;

    public SessionCleanupListener(SessionCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onSessionDestroyed(SessionDestroyedEvent event) {
        cleanupService.cleanup(event.getSessionId());
    }
}
~~~

Trong production, service cần xử lý trường hợp dữ liệu phụ đã bị xóa, repository phụ tạm thời không khả dụng hoặc event được nhận nhiều lần. Nếu lỗi phải được retry, cần đưa tác vụ vào cơ chế retry/message bền vững phù hợp thay vì chỉ ném exception và hy vọng event được phát lại.

## 12. Những lỗi thường gặp

**Chỉ lắng nghe `SessionDeletedEvent` và bỏ qua timeout.**  
Session hết hạn có nguyên nhân khác với xóa chủ động. Nếu cần xử lý mọi trường hợp kết thúc, hãy xử lý cả `SessionExpiredEvent` hoặc lớp cơ sở `SessionDestroyedEvent`.

**Cho rằng `SessionDestroyedEvent` là một event riêng chỉ phát khi container shutdown.**  
Đây là lớp cơ sở trong hệ thống event của Spring Session cho các sự kiện kết thúc như deleted và expired. Nó không đồng nghĩa với việc JVM hoặc ứng dụng bị shutdown.

**Cho rằng đóng trình duyệt sẽ phát event destroyed ngay.**  
Trình duyệt đóng không gửi một tín hiệu logout đáng tin cậy. Session thường kết thúc theo timeout hoặc thao tác invalidate/xóa phía server.

**Redis không phát event hết hạn.**  
Kiểm tra keyspace notifications, quyền cấu hình Redis, loại repository và listener container. Với dịch vụ Redis managed, notification có thể cần được bật ở cấu hình server.

**Listener xử lý hai lần cùng một session.**  
Kiểm tra có listener cho cả `SessionDestroyedEvent` và lớp con hay không, đồng thời xem xét nhiều instance hoặc cơ chế retry. Thiết kế idempotent và chống trùng.

**Listener làm request chậm.**  
Tách công việc nặng khỏi callback, dùng executor hoặc message broker phù hợp và theo dõi lỗi xử lý bất đồng bộ.

**Dùng event để thu hồi quyền đúng thời điểm tuyệt đối.**  
Event hết hạn có thể đến trễ tùy repository. Kiểm tra session hợp lệ tại thời điểm request thay vì dựa vào thời điểm listener nhận thông báo.

**Ghi toàn bộ session attributes vào log.**  
Thuộc tính có thể chứa thông tin cá nhân hoặc bí mật. Chỉ ghi metadata tối thiểu và che dữ liệu nhạy cảm.

## 13. Tự kiểm tra

1. `SessionCreatedEvent` biểu diễn điều gì?
2. `SessionDeletedEvent` khác `SessionExpiredEvent` ở nguyên nhân nào?
3. Vì sao `SessionDestroyedEvent` có thể dùng để xử lý chung các trường hợp kết thúc phiên?
4. `HttpSessionListener` khác listener của Spring Session ở điểm nào?
5. `SessionEventHttpSessionListenerAdapter` có vai trò gì?
6. Vì sao event hết hạn không nhất thiết được nhận đúng mili giây session timeout vừa đạt?
7. Redis keyspace notifications hỗ trợ việc phát hiện điều gì?
8. Vì sao không nên dùng Redis pub/sub lifecycle event làm nguồn audit duy nhất?
9. Listener idempotent giúp xử lý vấn đề gì khi có nhiều instance?
10. Cần kiểm thử những gì để xác nhận repository thực sự phát event hết hạn?

### Gợi ý trả lời

1. Nó biểu diễn một session mới được tạo.
2. Deleted phản ánh thao tác xóa; expired phản ánh session đã hết hạn theo chính sách thời gian.
3. Đây là lớp sự kiện cơ sở cho các event kết thúc như deleted và expired.
4. `HttpSessionListener` là callback của Servlet API; Spring Session listener nhận các event được phát bởi cơ chế quản lý session của Spring Session.
5. Adapter chuyển event Spring Session thành callback `HttpSessionListener` để tái sử dụng listener Servlet hiện có.
6. Repository có thể phát hiện hết hạn khi có notification, request truy cập hoặc tác vụ cleanup chạy.
7. Chúng giúp repository nhận biết các key session bị xóa hoặc hết hạn theo cấu hình.
8. Pub/sub không phải kho message bền vững để phát lại mọi event sau khi consumer mất kết nối.
9. Nó giúp cùng một tác vụ được gọi lặp lại mà không tạo tác động nghiệp vụ trùng lặp.
10. Cần dùng repository thật, cấu hình timeout/notification/cleanup phù hợp, xác minh session không tải được và event hết hạn được nhận.

## Kết luận

Spring Session biểu diễn vòng đời phiên bằng các sự kiện như `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent`. Hai sự kiện kết thúc là các dạng của `SessionDestroyedEvent`, cho phép ứng dụng xử lý chung hoặc phân biệt nguyên nhân. Trong ứng dụng Servlet, `SessionEventHttpSessionListenerAdapter` giúp chuyển các event Spring Session thành callback `HttpSessionListener`.

Khả năng phát event và thời điểm nhận phụ thuộc repository, cấu hình Redis keyspace notifications hoặc cơ chế cleanup JDBC. Listener nên ngắn gọn, idempotent, bảo vệ Session ID và không ghi dữ liệu nhạy cảm. Với nghiệp vụ cần audit bền vững hoặc bảo đảm không mất thông báo, hãy dùng transaction, outbox hoặc message broker phù hợp thay vì chỉ dựa vào application event.

