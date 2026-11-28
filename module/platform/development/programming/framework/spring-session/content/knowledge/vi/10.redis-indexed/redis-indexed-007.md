# SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent

Spring Session có thể phát các sự kiện vòng đời khi một phiên được tạo, bị xóa hoặc hết hạn. Với Redis có chỉ mục, các sự kiện này giúp ứng dụng nhận biết thay đổi của session dù dữ liệu được lưu ngoài bộ nhớ của từng instance Spring. Chúng hữu ích cho việc ghi nhận hoạt động, cập nhật trạng thái phụ trợ và tích hợp các xử lý sau khi phiên kết thúc.

Ba sự kiện cần phân biệt là SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent. Chúng mô tả những thời điểm khác nhau trong vòng đời phiên. Sự kiện là thông báo rằng một thay đổi đã xảy ra; nó không thay thế thao tác tạo, xóa hoặc xác thực session. Khi vận hành nhiều instance, cần hiểu nguồn phát sự kiện, cấu hình Redis keyspace notifications và giới hạn độ tin cậy của thông báo.

## 1. Vai trò của sự kiện vòng đời session

Một session có thể được tạo bởi một request, được sử dụng bởi nhiều request sau đó, rồi kết thúc do người dùng đăng xuất, quản trị viên thu hồi hoặc hết thời gian không hoạt động. Với Spring Session Redis, dữ liệu phiên được lưu trong Redis và có thể được truy cập từ nhiều instance ứng dụng.

Nếu chỉ quan sát bộ nhớ của một instance, ứng dụng không thể biết đầy đủ mọi thay đổi của phiên trong repository dùng chung. Spring Session cung cấp các application event để mã nghiệp vụ có thể phản ứng với thay đổi vòng đời.

| Sự kiện | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| SessionCreatedEvent | Một session mới được tạo và lưu | Có một phiên mới bắt đầu |
| SessionDeletedEvent | Một session bị xóa hoặc vô hiệu hóa tường minh | Phiên kết thúc do thao tác xóa |
| SessionExpiredEvent | Một session hết hạn theo chính sách thời gian | Phiên kết thúc do timeout |

Sự kiện có thể mang theo đối tượng Session, cho phép listener lấy ID hoặc các thuộc tính cần thiết. Chỉ đọc dữ liệu thực sự cần cho tác vụ. Không ghi session ID, cookie, token hoặc toàn bộ thuộc tính phiên vào log vì những giá trị đó có thể cho phép truy cập phiên hoặc làm lộ thông tin người dùng.

## 2. SessionCreatedEvent

SessionCreatedEvent được phát khi repository tạo một session mới. Một số tình huống có thể dẫn đến việc tạo session:

- Controller gọi request.getSession() khi request chưa có session hợp lệ.
- Một thành phần bảo mật tạo session để lưu SecurityContext hoặc trạng thái xác thực.
- Một tính năng lưu trạng thái nhiều bước yêu cầu vùng dữ liệu phiên.
- Ứng dụng tạo session tường minh thông qua SessionRepository.

Không phải mọi request HTTP đều tạo session. Nếu controller dùng request.getSession(false) để kiểm tra phiên hiện có, request không có session sẽ không tự động tạo phiên mới.

Ứng dụng có thể lắng nghe sự kiện để ghi nhận số lượng phiên mới, khởi tạo dữ liệu phụ trợ hoặc cập nhật một chỉ số thống kê:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.Session;
import org.springframework.session.events.SessionCreatedEvent;

@Component
class SessionCreatedListener {

    @EventListener
    void onSessionCreated(SessionCreatedEvent event) {
        Session session = event.getSession();

        // Chỉ dùng thông tin không nhạy cảm cần cho tác vụ.
        String sessionId = session.getId();
        recordSessionCreationWithoutExposingId(sessionId);
    }

    private void recordSessionCreationWithoutExposingId(String sessionId) {
        // Ví dụ: tăng metric hoặc phát một mã tham chiếu đã được bảo vệ.
    }
}
~~~

Ví dụ minh họa việc nhận event. Trong ứng dụng thật, không đưa session ID thô vào log hoặc metric label. Metric label có giá trị thay đổi theo từng session sẽ tạo cardinality rất lớn; nên dùng bộ đếm tổng hợp thay vì gắn ID phiên vào nhãn metric.

SessionCreatedEvent không có nghĩa người dùng đã đăng nhập thành công. Session có thể được tạo bởi một request ẩn danh, một trang công khai hoặc một tính năng chưa xác thực. Nếu cần biết trạng thái xác thực, hãy kiểm tra trạng thái bảo mật theo cách phù hợp; không suy luận đăng nhập chỉ từ sự kiện tạo session.

## 3. SessionDeletedEvent

SessionDeletedEvent biểu thị một session bị xóa tường minh. Trường hợp thường gặp nhất là ứng dụng gọi HttpSession.invalidate(), người dùng đăng xuất hoặc một luồng quản trị chủ động thu hồi session.

Ví dụ:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LogoutController {

    @PostMapping("/logout")
    void logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
    }
}
~~~

Trong ứng dụng dùng Spring Security, nên để logout flow đã cấu hình thực hiện vô hiệu hóa session và xóa cookie phù hợp. Ví dụ trên chỉ minh họa thao tác Servlet cơ bản; nó không thay thế cấu hình logout, CSRF và các handler bảo mật của Spring Security.

Listener có thể dùng SessionDeletedEvent để cập nhật trạng thái phụ trợ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionDeletedEvent;

@Component
class SessionDeletedListener {

    @EventListener
    void onSessionDeleted(SessionDeletedEvent event) {
        // Thu hồi dữ liệu phụ trợ gắn với phiên nếu nghiệp vụ yêu cầu.
        // Không giả định event được giao đúng một lần trên toàn cụm.
    }
}
~~~

Xóa session ở repository và xóa cookie ở trình duyệt là hai việc khác nhau. Repository cần vô hiệu hóa phiên để ID cũ không còn truy cập được dữ liệu. Response đăng xuất cần xóa cookie với đúng tên, Path và Domain để trình duyệt ngừng gửi ID cũ. Chỉ xóa cookie phía client mà không xóa session phía server có thể để lại một session còn hiệu lực nếu ID bị lộ.

## 4. SessionExpiredEvent

SessionExpiredEvent biểu thị session hết hạn theo chính sách thời gian, thường là idle timeout. Với Spring Session Redis, thời hạn được áp dụng trong Redis; khi khóa liên quan đến thời hạn phiên hết hạn, Redis có thể phát keyspace notification để Spring Session nhận biết và phát sự kiện.

Ví dụ listener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionExpiredEvent;

@Component
class SessionExpiredListener {

    @EventListener
    void onSessionExpired(SessionExpiredEvent event) {
        // Cập nhật số liệu tổng hợp hoặc trạng thái phụ trợ.
        // Tránh coi thời điểm nhận event là thời điểm hết hạn chính xác.
    }
}
~~~

Hết hạn khác với xóa tường minh. Người dùng có thể không thực hiện thao tác đăng xuất; session vẫn kết thúc khi vượt quá thời gian không hoạt động hoặc TTL theo cấu hình. Khi nhận sự kiện hết hạn, ứng dụng có thể ghi nhận số phiên hết hạn, dọn dữ liệu phụ trợ hoặc yêu cầu người dùng xác thực lại ở request tiếp theo.

Redis không bảo đảm thông báo hết hạn được phát đúng vào mili giây TTL chạm 0. Việc phát sự kiện phụ thuộc cơ chế kiểm tra và xử lý expiration của Redis; thông báo có thể đến trễ. Vì vậy, không dùng SessionExpiredEvent làm đồng hồ chính xác để tính thời hạn nghiệp vụ hoặc thực hiện giao dịch cần đúng thời điểm.

## 5. Lắng nghe nhiều sự kiện trong cùng một thành phần

Có thể gom các listener vào một component nếu các tác vụ có cùng trách nhiệm:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;

@Component
class SessionLifecycleListener {

    @EventListener
    void created(SessionCreatedEvent event) {
        // Ghi nhận phiên mới.
    }

    @EventListener
    void deleted(SessionDeletedEvent event) {
        // Xử lý phiên bị xóa tường minh.
    }

    @EventListener
    void expired(SessionExpiredEvent event) {
        // Xử lý phiên hết hạn.
    }
}
~~~

Tách handler theo loại event giúp mã dễ đọc và tránh nhầm lẫn giữa logout và timeout. Nếu cả hai trường hợp đều cần dọn dữ liệu phụ trợ, có thể gọi một hàm dùng chung nhưng vẫn giữ thông tin nguyên nhân khác nhau để phục vụ audit và thống kê.

Khi cần nhận mọi sự kiện kết thúc phiên, có thể dùng kiểu sự kiện cha tương ứng trong phiên bản Spring Session đang dùng. Tuy nhiên, nếu nghiệp vụ cần phân biệt logout với timeout thì nên xử lý SessionDeletedEvent và SessionExpiredEvent riêng biệt. Kiểm tra API của phiên bản dependency trước khi dựa vào quan hệ kế thừa cụ thể.

## 6. Bật Redis keyspace notifications

Các sự kiện liên quan đến Redis expiration và deletion phụ thuộc vào Redis keyspace notifications. Redis không nhất thiết phát những thông báo này nếu cấu hình chưa bật đúng nhóm sự kiện.

Với Redis có thể cấu hình tham số:

~~~text
notify-keyspace-events Egx
~~~

Các ký tự trong cấu hình có ý nghĩa:

- E: phát key-event notification trên channel dạng __keyevent@<db>__:<event>.
- g: bao gồm các lệnh generic như DEL.
- x: bao gồm sự kiện key hết hạn (expired).

Có thể kiểm tra cấu hình hiện tại bằng redis-cli:

~~~bash
redis-cli CONFIG GET notify-keyspace-events
~~~

Trong môi trường thử nghiệm có quyền cấu hình, có thể bật bằng:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Egx
~~~

Không phải môi trường production nào cũng cho phép ứng dụng tự chạy CONFIG SET. Một số dịch vụ Redis được quản lý chặn lệnh CONFIG hoặc quản lý tham số qua console/parameter group. Trong trường hợp đó, quản trị viên cần bật keyspace notifications bằng cấu hình của nhà cung cấp. Chỉ cấu hình ứng dụng bỏ qua lệnh CONFIG không tự bật notification trên Redis.

Nếu môi trường dùng Redis Cluster hoặc dịch vụ Redis managed, hãy kiểm tra cách nhà cung cấp phát và phân phối keyspace notification, cũng như quyền subscribe của ứng dụng. Kiểm thử bằng chính topology production-like vì cấu hình trên một Redis đơn lẻ chưa chứng minh event hoạt động trong cụm.

### Khi Spring Session không được phép cấu hình Redis

Nếu ứng dụng không có quyền chạy CONFIG SET, có thể cung cấp ConfigureRedisAction.NO_OP để Spring Session không cố thay đổi cấu hình Redis khi khởi động:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.ConfigureRedisAction;

@Configuration
class RedisSessionConfiguration {

    @Bean
    ConfigureRedisAction configureRedisAction() {
        return ConfigureRedisAction.NO_OP;
    }
}
~~~

NO_OP chỉ tắt hành động cấu hình tự động từ ứng dụng. Nó không thay thế bước cấu hình notify-keyspace-events trên Redis. Nếu keyspace notifications chưa được bật ở server, các sự kiện dựa vào thông báo Redis có thể không được phát như mong đợi.

## 7. Cách RedisIndexedSessionRepository hỗ trợ sự kiện

RedisIndexedSessionRepository lưu session trong Redis và duy trì các chỉ mục để tìm phiên theo thông tin như principal name. Các chỉ mục này hữu ích khi ứng dụng cần tra cứu các phiên của một người dùng, chẳng hạn để giới hạn số phiên đăng nhập hoặc thu hồi các phiên liên quan.

Để theo dõi vòng đời, repository kết hợp thao tác lưu/xóa session với thông báo từ Redis. Khi một session mới được tạo, Spring Session có thể phát SessionCreatedEvent trong application context xử lý thao tác đó. Khi session bị xóa hoặc hết hạn, Redis keyspace notifications giúp repository nhận biết thay đổi và phát sự kiện tương ứng.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng tạo hoặc thay đổi session"] --> B["RedisIndexedSessionRepository"]
    B --> C["Redis: session hash và chỉ mục"]
    B --> D["SessionCreatedEvent"]
    C --> E["Redis keyspace notifications"]
    E --> F{"Loại thay đổi"}
    F -->|DEL / xóa| G["SessionDeletedEvent"]
    F -->|expired / hết hạn| H["SessionExpiredEvent"]
    D --> I["ApplicationEvent listener"]
    G --> I
    H --> I
    I --> J["Metric, audit hoặc dọn dữ liệu phụ trợ"]
~~~

Chi tiết key, TTL và cách phát sự kiện phụ thuộc phiên bản Spring Session. Không nên viết mã nghiệp vụ dựa trên tên khóa nội bộ của repository hoặc tự xóa key Redis bằng mẫu đoán. Dùng API SessionRepository và cấu hình được hỗ trợ để tránh làm hỏng index hoặc dữ liệu phụ trợ.

## 8. Sự kiện trong môi trường nhiều instance

Trong hệ thống nhiều instance, cần phân biệt application event trong một Spring ApplicationContext với Redis Pub/Sub notification. Event được publish trong một ApplicationContext không mặc nhiên trở thành event toàn cụm. Redis keyspace notification có thể được phân phối đến các subscriber đang lắng nghe, nhưng cách mỗi instance xử lý còn phụ thuộc topology và cấu hình listener.

Vì vậy:

- Không giả định mọi instance đều nhận SessionCreatedEvent nếu event được phát cục bộ tại instance thực hiện thao tác tạo.
- Với sự kiện dựa trên Redis keyspace notifications, nhiều instance cùng subscribe có thể cùng quan sát một thay đổi. Không thiết kế listener với giả định chỉ một node xử lý.
- Không giả định event được giao đúng một lần, đúng thứ tự hoặc không bị mất khi Redis, mạng hay ứng dụng gặp sự cố.
- Listener nên idempotent: nhận cùng thông báo nhiều lần vẫn không tạo tác dụng phụ sai.
- Nếu tác vụ cần xử lý đúng một lần trên toàn hệ thống, hãy dùng hàng đợi bền vững, khóa phân tán hoặc cơ chế điều phối riêng với chiến lược retry và chống trùng.

Ví dụ, cập nhật metric tổng số phiên có thể chấp nhận một số sai lệch nhỏ hoặc được đối soát định kỳ. Ngược lại, cấp quyền truy cập tài chính, phát hành hóa đơn hoặc gửi một thông báo quan trọng không nên dựa duy nhất vào một callback session event có thể lặp hoặc bị trễ.

## 9. Thiết kế listener an toàn và ổn định

Listener nên thực hiện công việc ngắn, có thể lặp lại và không làm chậm luồng xử lý sự kiện. Một số nguyên tắc:

1. Chỉ đọc các thuộc tính session cần thiết.
2. Không ghi session ID, cookie, access token hoặc SecurityContext vào log.
3. Không giả định event chứa mọi thuộc tính nếu session đã hết hạn hoặc dữ liệu đã bị dọn.
4. Kiểm tra null và trường hợp session không còn đọc được.
5. Dùng thao tác idempotent cho tác vụ dọn dữ liệu phụ trợ.
6. Đặt timeout và xử lý lỗi khi listener gọi dịch vụ bên ngoài.
7. Ghi metric cho số event theo loại, lỗi listener và độ trễ xử lý.
8. Không thực hiện tác vụ kéo dài trực tiếp trên thread nhận Redis notification.

Nếu listener cần gọi dịch vụ bên ngoài hoặc xử lý nặng, có thể chuyển công việc sang executor. Tuy nhiên, chạy bất đồng bộ trong bộ nhớ vẫn không tạo ra bảo đảm bền vững: tiến trình có thể dừng trước khi công việc hoàn tất. Với công việc quan trọng, hãy chuyển event sang hệ thống messaging bền vững và thiết kế retry, dead-letter và deduplication.

Ví dụ dùng executor cho tác vụ không cần bảo đảm bền vững:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionExpiredEvent;

@Component
class AsyncSessionExpiryListener {

    @Async
    @EventListener
    void onExpired(SessionExpiredEvent event) {
        // Chỉ chạy công việc phụ trợ có thể retry hoặc đối soát.
        updateNonCriticalAggregate();
    }

    private void updateNonCriticalAggregate() {
        // Cập nhật số liệu tổng hợp.
    }
}
~~~

Để @Async hoạt động, ứng dụng cần bật async processing và cấu hình executor phù hợp. Không chuyển mọi listener sang async theo mặc định: executor không giới hạn có thể làm cạn bộ nhớ, còn executor quá nhỏ có thể tạo backlog. Theo dõi hàng đợi và thời gian xử lý nếu bật bất đồng bộ.

## 10. Kết hợp sự kiện với HttpSessionListener

Một số ứng dụng cũ đã dùng Servlet HttpSessionListener để nhận callback tạo và hủy session. Spring Session cung cấp SessionEventHttpSessionListenerAdapter để chuyển các sự kiện Spring Session phù hợp thành lời gọi HttpSessionListener.

Ví dụ minh họa:

~~~java
import jakarta.servlet.http.HttpSessionEvent;
import jakarta.servlet.http.HttpSessionListener;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.SessionEventHttpSessionListenerAdapter;

class ApplicationHttpSessionListener implements HttpSessionListener {

    @Override
    public void sessionCreated(HttpSessionEvent event) {
        // Xử lý callback tạo session.
    }

    @Override
    public void sessionDestroyed(HttpSessionEvent event) {
        // Xử lý callback kết thúc session.
    }
}

@Configuration
class ServletSessionListenerConfiguration {

    @Bean
    SessionEventHttpSessionListenerAdapter sessionEventHttpSessionListenerAdapter() {
        return new SessionEventHttpSessionListenerAdapter(
            List.of(new ApplicationHttpSessionListener())
        );
    }
}
~~~

Adapter hữu ích khi cần giữ hợp đồng listener Servlet trong ứng dụng đã có sẵn. Với mã mới, lắng nghe SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent trực tiếp thường làm rõ nguyên nhân kết thúc phiên hơn. Kiểm tra phiên bản Spring Session đang dùng và cách đăng ký adapter trong môi trường Servlet thực tế trước khi triển khai.

## 11. Kiểm thử ba sự kiện

Một bộ kiểm thử cần xác nhận cả thao tác session và sự kiện tương ứng:

| Kịch bản | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Tạo phiên mới | Tạo session và lưu lần đầu | Nhận SessionCreatedEvent |
| Xóa tường minh | Gọi invalidate hoặc xóa qua repository | Nhận SessionDeletedEvent nếu cơ chế notification được cấu hình đúng |
| Hết hạn | Đặt timeout ngắn rồi chờ repository/Redis hết hạn | Nhận SessionExpiredEvent sau khi Redis phát notification |
| Redis notifications tắt | Tạo/xóa/hết hạn trong môi trường kiểm thử | Phát hiện các event phụ thuộc keyspace notification không đến |
| Nhiều instance | Tạo hoặc xóa phiên qua một instance, quan sát subscriber khác | Xác định rõ instance nào nhận từng loại event |
| Event lặp | Gửi lại cùng tác vụ xử lý trong kiểm thử | Listener không tạo tác dụng phụ trùng |

Với kiểm thử hết hạn, không dùng sleep ngắn rồi giả định sự kiện phải đến đúng thời điểm. Redis expiration có thể trễ; hãy dùng timeout đủ dài, chờ theo điều kiện có giới hạn và kiểm tra trạng thái repository cùng event. Trong kiểm thử tự động, dùng một listener ghi nhận event vào cấu trúc đồng bộ dành riêng cho test, rồi chờ đến khi điều kiện được thỏa mãn hoặc timeout.

Nên có kiểm thử tích hợp với Redis thật hoặc container test tương thích. Mock ApplicationEventPublisher chỉ xác nhận listener có thể được gọi; nó không kiểm chứng keyspace notifications, TTL, index hoặc luồng event thực tế của RedisIndexedSessionRepository.

## 12. Giám sát và xử lý sự cố

Khi sự kiện không xuất hiện, kiểm tra theo thứ tự:

1. Ứng dụng có thực sự tạo, xóa hoặc làm hết hạn session không?
2. Đang dùng RedisIndexedSessionRepository đúng như dự kiến hay repository khác?
3. Redis có bật notify-keyspace-events với nhóm event cần thiết không?
4. Ứng dụng có thể subscribe kênh keyevent và nhận message từ Redis không?
5. Có lỗi kết nối, quyền ACL, cấu hình database index hoặc Redis Cluster khiến listener không nhận notification không?
6. Listener có bị lỗi khi xử lý hoặc bị tắt bởi cấu hình component/async không?

Theo dõi:

- Số lượng SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent theo khoảng thời gian.
- Lỗi khi khởi tạo Redis message listener và lỗi reconnect.
- Độ trễ từ lúc TTL hết hạn đến lúc listener nhận event.
- Lỗi trong listener và số tác vụ retry.
- Sự khác biệt giữa số session trong repository và số liệu thống kê từ event.

Không dùng event count làm nguồn dữ liệu duy nhất để xác định chính xác số session đang hoạt động. Event có thể bị trễ, lặp hoặc không được nhận trong thời gian hệ thống gặp sự cố. Để có số liệu chính xác hơn, dùng truy vấn repository/index phù hợp và đối soát định kỳ, có tính đến chi phí truy vấn trên Redis.

## 13. Nguyên tắc sử dụng sự kiện

- Dùng SessionCreatedEvent để nhận biết phiên mới được tạo.
- Dùng SessionDeletedEvent cho phiên bị xóa hoặc vô hiệu hóa tường minh.
- Dùng SessionExpiredEvent cho phiên kết thúc do timeout.
- Bật Redis keyspace notifications khi cần nhận sự kiện xóa/hết hạn từ Redis.
- Trên dịch vụ Redis managed, cấu hình notification ở cấp dịch vụ nếu ứng dụng không được phép chạy CONFIG SET.
- Thiết kế listener idempotent và không giả định exactly-once.
- Không thực hiện giao dịch quan trọng chỉ dựa trên application event trong bộ nhớ.
- Không ghi session ID hoặc dữ liệu xác thực vào log.
- Kiểm thử trên đúng kiểu repository và topology Redis của môi trường triển khai.

Các sự kiện vòng đời giúp Spring Session kết nối thay đổi trạng thái phiên với xử lý nghiệp vụ và giám sát. SessionCreatedEvent cho biết phiên mới được tạo; SessionDeletedEvent thể hiện thao tác xóa tường minh; SessionExpiredEvent thể hiện phiên hết hạn. Khi dùng Redis có chỉ mục, cần cấu hình và giám sát keyspace notifications, đồng thời thiết kế listener chịu được độ trễ, lặp và gián đoạn để hệ thống nhiều instance vận hành ổn định.
