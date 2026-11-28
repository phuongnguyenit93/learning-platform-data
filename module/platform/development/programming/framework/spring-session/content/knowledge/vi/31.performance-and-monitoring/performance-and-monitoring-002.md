# Số phiên hoạt động, số phiên tạo mới và tốc độ hết hạn

Khi vận hành Spring Session trên nhiều instance, số lượng session và tốc độ thay đổi của chúng là những tín hiệu quan trọng để đánh giá tải, dung lượng Redis/JDBC, hiệu quả timeout và trải nghiệm đăng nhập. Tuy nhiên, ba số liệu thường bị nhầm lẫn: số session còn hiệu lực, số session được tạo trong một khoảng thời gian và số session hết hạn trong khoảng thời gian đó. Chúng đo những khía cạnh khác nhau và cần được thu thập bằng cách phù hợp.

Một session còn bản ghi trong Redis hoặc bảng JDBC chưa chắc còn hiệu lực. Session có thể đã vượt quá max inactive interval nhưng bản ghi vật lý vẫn chờ cleanup. Ngược lại, một người dùng có thể có nhiều session trên nhiều browser hoặc thiết bị. Vì vậy, số session hoạt động không đồng nghĩa số người dùng đang online.

Spring Session cung cấp repository và các sự kiện vòng đời để tích hợp với hệ thống giám sát. Để có số liệu đáng tin cậy, cần kết hợp bộ đếm sự kiện, phép đo định kỳ từ kho dữ liệu, metric thao tác repository và hiểu biết về cách từng backend xử lý TTL/cleanup. Không nên dùng một bộ đếm cục bộ trên một node làm số liệu toàn cụm.

## 1. Định nghĩa rõ từng chỉ số

Trước khi tạo dashboard, hãy thống nhất cách định nghĩa:

| Chỉ số | Ý nghĩa | Loại metric |
|---|---|---|
| Active sessions | Số session chưa hết hạn tại thời điểm đo | Gauge |
| Sessions created | Số session mới được tạo trong một khoảng thời gian | Counter |
| Creation rate | Tốc độ tạo session, ví dụ session/giây hoặc session/phút | Rate từ counter |
| Sessions expired | Số session chuyển sang trạng thái hết hạn trong khoảng thời gian | Counter |
| Expiration rate | Tốc độ hết hạn session | Rate từ counter |
| Sessions deleted | Số session bị xóa chủ động, ví dụ logout hoặc revoke | Counter |
| Expired record backlog | Số bản ghi đã hết hạn nhưng còn tồn tại vật lý trong storage | Gauge |
| Unique active principals | Số principal khác nhau có ít nhất một session còn hiệu lực | Gauge hoặc phép đo định kỳ |

Các chỉ số này không thay thế nhau. Active sessions cho biết quy mô trạng thái hiện tại; creation/expiration rate cho biết tốc độ biến động; expired backlog cho biết công việc dọn dữ liệu còn tồn đọng.

## 2. Session hoạt động không phải là người dùng online

Một session được xem là còn hiệu lực tại thời điểm t nếu repository vẫn có thể khôi phục nó và thời điểm hết hạn chưa đến. Trong mô hình timeout không hoạt động, thời điểm hết hạn thường được tính từ lần truy cập gần nhất cộng với max inactive interval.

Ví dụ:

- Một người dùng đăng nhập trên laptop và điện thoại: có thể tạo hai session.
- Một browser có nhiều tab: thường các tab chia sẻ cùng cookie/session, không nhất thiết tạo nhiều session.
- Người dùng đóng browser mà không logout: session có thể còn hiệu lực cho đến khi timeout.
- Người dùng logout: session bị invalidate/xóa, dù trước đó vẫn chưa hết timeout.
- Session hết hạn logic nhưng bản ghi JDBC chưa được cleanup: bản ghi còn trong bảng nhưng không còn là session hợp lệ.

Vì vậy, dashboard nên đặt tên chính xác là Active sessions thay vì Online users. Nếu sản phẩm cần số người dùng online, phải định nghĩa riêng “online”, chẳng hạn principal có hoạt động trong N phút gần nhất và có ít nhất một session còn hiệu lực. Đó là một phép đo nghiệp vụ, không phải thuộc tính tự động của Spring Session.

## 3. Hết hạn logic và xóa vật lý

Spring Session phân biệt thời điểm một session không còn được chấp nhận với thời điểm dữ liệu của nó được thu hồi khỏi storage:

1. Session có last access time và max inactive interval.
2. Khi khoảng không hoạt động vượt giới hạn, session hết hạn logic.
3. Khi request tìm session theo ID, repository phải kiểm tra expiration và không trả session đã hết hạn.
4. Dữ liệu vật lý có thể được xóa ngay trong luồng truy cập, bởi TTL backend hoặc bởi cleanup job định kỳ, tùy implementation.

Với JDBC, bảng SPRING_SESSION có cột EXPIRY_TIME. Bản ghi đã hết hạn có thể còn tồn tại cho đến khi cleanup job chạy. Với Redis, key TTL và các cấu trúc index/expiration phụ thuộc implementation; keyspace notification cũng có thể đến sau thời điểm logic hết hạn.

Do đó:

- Active sessions phải dựa trên trạng thái còn hiệu lực, không chỉ đếm mọi bản ghi hoặc mọi key.
- Expired record backlog đo dữ liệu đã hết hạn nhưng chưa được dọn.
- Expiration rate đo số phiên hết hạn theo thời gian, không phải số hàng đã bị xóa trong một lần cleanup.

## 4. Quan hệ giữa tạo mới, hết hạn và xóa

Quy mô active sessions thay đổi theo nhiều luồng:

- session mới được tạo và lưu;
- session hết hạn theo timeout;
- người dùng logout chủ động;
- quản trị viên thu hồi session;
- session bị xóa bởi chính sách bảo mật hoặc thao tác vận hành;
- dữ liệu bị mất do sự cố hoặc thao tác storage.

Một mô hình cân bằng gần đúng:

~~~text
Active(t2) = Active(t1)
          + Created(t1..t2)
          - Expired(t1..t2)
          - Deleted(t1..t2)
          - OtherRevoked(t1..t2)
~~~

Đây là mô hình giải thích, không phải đẳng thức luôn đúng giữa các metric thô. Có thể có event bị mất, event trùng, session được tạo nhưng chưa được lưu thành công, hoặc phép đo active được chụp trong lúc có request đang thay đổi dữ liệu. Dùng phép đo định kỳ từ repository/backend để đối chiếu và phát hiện drift.

Không cộng Sessions created vào active sessions rồi giữ mãi. Session có thể hết hạn hoặc bị xóa; active sessions là gauge hiện tại, còn created/expired/deleted là counter tích lũy.

## 5. Sự kiện vòng đời của Spring Session

Spring Session có các event vòng đời như:

- SessionCreatedEvent: session được tạo.
- SessionDeletedEvent: session bị xóa chủ động.
- SessionExpiredEvent: session hết hạn.

Các event được phát theo hành vi và implementation repository cụ thể. Redis và JDBC có cách phát hiện/xử lý expiration khác nhau; cần xác minh phiên bản Spring Session và backend đang dùng trước khi coi một event là nguồn thống kê đầy đủ.

Có thể lắng nghe event trong ứng dụng Spring:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;

@Component
class SessionLifecycleListener {

    @EventListener
    void onCreated(SessionCreatedEvent event) {
        // Ghi nhận một tín hiệu tạo session.
    }

    @EventListener
    void onDeleted(SessionDeletedEvent event) {
        // Ghi nhận một tín hiệu xóa chủ động.
    }

    @EventListener
    void onExpired(SessionExpiredEvent event) {
        // Ghi nhận một tín hiệu hết hạn.
    }
}
~~~

Listener chỉ nên cập nhật metric hoặc đẩy một sự kiện gọn sang hệ thống giám sát. Không log session ID, cookie, principal nhạy cảm hoặc toàn bộ session attributes. Nếu cần phân loại theo loại ứng dụng, dùng tag có cardinality thấp như backend=redis/jdbc hoặc application=web.

Không giả định event là một message bền vững được giao đúng một lần. Event có thể phụ thuộc keyspace notification, pub/sub hoặc cơ chế nội bộ của repository. Một node có thể bỏ lỡ event khi đang ngừng hoạt động; nhiều node có thể cùng nhận một thông báo backend tùy cơ chế phân phối. Bộ đếm event vì vậy cần được đối chiếu bằng phép đo storage và không nên là nguồn duy nhất cho số liệu kiểm toán.

## 6. Đếm số session hoạt động bằng phép đo định kỳ

Một cách chắc chắn là lấy snapshot định kỳ từ storage bằng truy vấn hoặc API phù hợp. Không chạy phép đếm toàn bộ ở mỗi request hoặc mỗi lần Prometheus scrape; việc đó có thể tạo tải đáng kể lên Redis/JDBC.

Mẫu triển khai:

1. Một scheduled task chạy theo chu kỳ, ví dụ mỗi 30 hoặc 60 giây.
2. Task đếm session còn hiệu lực theo backend.
3. Lưu kết quả vào AtomicLong hoặc một gauge state.
4. Prometheus/Micrometer đọc gauge đã lấy mẫu, không tự quét storage.
5. Ghi thời điểm snapshot cuối để phát hiện dữ liệu đã cũ.

Đối với cụm nhiều instance, chọn một tiến trình reconciliation duy nhất hoặc dùng cơ chế điều phối/leader election. Nếu mọi node đều quét toàn bộ kho chung và cùng publish cùng một số tổng, dashboard có thể cộng lặp các gauge. Nếu mỗi node chỉ đo phần dữ liệu riêng, cần tag và tổng hợp đúng phạm vi.

## 7. Đếm active sessions trong Spring Session JDBC

Schema JDBC mặc định có cột EXPIRY_TIME lưu mốc hết hạn dưới dạng epoch milliseconds. Tại thời điểm đo, session còn hiệu lực theo mốc này khi EXPIRY_TIME lớn hơn thời gian hiện tại.

Truy vấn đếm session chưa hết hạn:

~~~sql
SELECT COUNT(*)
FROM SPRING_SESSION
WHERE EXPIRY_TIME > ?;
~~~

Truyền tham số là epoch milliseconds tại thời điểm snapshot. Nếu schema được đặt trong schema/database khác hoặc đổi table name, cập nhật tên bảng tương ứng. Không dùng câu lệnh này trên một bảng có cấu trúc khác mà không xác minh đơn vị và ý nghĩa cột.

Ví dụ dùng JdbcTemplate:

~~~java
long countActiveSessions(JdbcTemplate jdbc, Clock clock) {
    Long count = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM SPRING_SESSION
            WHERE EXPIRY_TIME > ?
            """,
            Long.class,
            clock.millis());
    return count == null ? 0L : count;
}
~~~

Clock được tiêm giúp test điều khiển thời gian và tránh rải System.currentTimeMillis() trong code. Trong production, đồng hồ của các application node cần được đồng bộ. Truy vấn đếm là snapshot tại một thời điểm; session có thể được tạo, gia hạn hoặc xóa ngay sau đó.

Schema mặc định tạo index trên EXPIRY_TIME để hỗ trợ truy vấn expiration/cleanup. Với bảng lớn, kiểm tra execution plan và thống kê optimizer. Dù có index, COUNT(*) vẫn phải xử lý các entry phù hợp; không chạy quá thường xuyên nếu số lượng session rất lớn.

## 8. Đếm expired record backlog trong JDBC

Số bản ghi đã hết hạn nhưng còn nằm trong bảng:

~~~sql
SELECT COUNT(*)
FROM SPRING_SESSION
WHERE EXPIRY_TIME <= ?;
~~~

Đây là backlog vật lý, không phải số session còn hoạt động. Nếu cleanup job chạy đều, backlog thường tăng giữa các lần chạy và giảm sau cleanup. Nếu backlog tăng liên tục, kiểm tra cleanup schedule, lỗi SQL, quyền DELETE, index và tải database.

Bảng SPRING_SESSION_ATTRIBUTES có dữ liệu liên quan đến session. Với schema chuẩn, foreign key cascade giúp xóa attributes khi hàng session bị xóa. Nếu schema tùy chỉnh bỏ cascade, phải đo và dọn dữ liệu mồ côi riêng. Không cộng số hàng attributes vào số session.

Truy vấn backlog cũng cần chạy theo chu kỳ hợp lý. Với hệ thống lớn, có thể lấy snapshot chậm hơn active gauge, hoặc theo dõi số hàng xóa mỗi lần cleanup và dung lượng bảng/index thay vì liên tục đếm toàn bộ.

## 9. Đếm active sessions và unique principals

Một người dùng có thể có nhiều session. Nếu cần số principal có ít nhất một session chưa hết hạn, JDBC có thể dùng principal index nếu schema và repository thực sự populate PRINCIPAL_NAME:

~~~sql
SELECT COUNT(DISTINCT PRINCIPAL_NAME)
FROM SPRING_SESSION
WHERE EXPIRY_TIME > ?
  AND PRINCIPAL_NAME IS NOT NULL;
~~~

Truy vấn này đo principal khác nhau, không phải session. Nó chỉ đáng tin khi principal name được lưu nhất quán cho các session liên quan. Nếu ứng dụng không dùng indexed repository hoặc không ghi principal index, kết quả có thể thấp hơn thực tế.

Đối với Redis indexed repository, việc tra cứu theo principal phụ thuộc index được populate và cấu hình repository. Không quét index theo từng principal ở mỗi request. Nếu sản phẩm cần số người online, xác định cửa sổ hoạt động và định nghĩa danh tính trước khi xây metric.

Không dùng principal ID làm tag metric vì số lượng giá trị rất lớn và có thể là dữ liệu cá nhân. Nếu cần phân tích theo tenant, chỉ dùng tenant class/segment có cardinality được kiểm soát và chính sách dữ liệu phù hợp.

## 10. Đếm session trong Redis

Redis repository có thể lưu nhiều loại key phục vụ session, expiration, principal index và metadata. Vì vậy, DBSIZE của Redis database không phải số session; nó đếm mọi key trong logical database.

Không dùng lệnh KEYS với pattern rộng trên production để đếm session. KEYS có thể chặn Redis trong lúc duyệt lượng key lớn. SCAN là lựa chọn ít gây chặn hơn cho một phép kiểm kê định kỳ, nhưng vẫn tiêu tốn tài nguyên và không tạo snapshot nhất quán tuyệt đối khi key thay đổi liên tục.

Nếu cần scan để đối chiếu:

- giới hạn pattern vào namespace session của ứng dụng;
- chỉ đếm key session chính theo cấu trúc của đúng repository/version;
- không đếm key expiration/index như thể chúng là session độc lập;
- dùng cursor và batch size phù hợp;
- chạy ở tần suất thấp và đo thời gian scan;
- chấp nhận kết quả gần đúng trong lúc key thay đổi;
- không dùng scan như phép đo mỗi lần scrape.

Không hard-code cấu trúc key nội bộ nếu có API/metric chính thức hoặc một adapter được quản lý. Cấu trúc key có thể thay đổi theo phiên bản Spring Session. Nếu buộc phải dựa vào key pattern, pin phiên bản, viết integration test xác nhận pattern và kiểm tra lại khi nâng cấp.

## 11. Redis TTL và expiration notifications

Redis có thể tự xóa key khi TTL hết hạn. Thời điểm key được xóa vật lý không nhất thiết trùng chính xác với thời điểm timeout logic được tính. Redis xử lý expiration bằng các cơ chế chủ động và thụ động; notification có thể được phát khi key thực sự hết hạn.

Spring Session Redis có thể sử dụng keyspace notifications để nhận biết session key hết hạn và phát event/cleanup index liên quan. Cấu hình Redis phải bật đúng loại notification theo tài liệu của phiên bản đang dùng. Một cấu hình thường gặp cho keyevent expiration và generic event là:

~~~text
notify-keyspace-events Egx
~~~

Ý nghĩa các flag và yêu cầu chính xác cần được kiểm tra theo Spring Session/Redis version. Không áp dụng cấu hình này mù quáng lên Redis dùng chung; thay đổi notify-keyspace-events có thể ảnh hưởng các ứng dụng khác.

Redis keyspace notification dùng cơ chế pub/sub, không phải hàng đợi bền vững. Subscriber đang ngắt kết nối có thể bỏ lỡ thông báo. Vì vậy:

- Event expiration hữu ích để cập nhật metric và dọn index.
- Không coi event là bằng chứng duy nhất rằng mọi session đã hết hạn đều được ghi nhận.
- Đối chiếu với phép đo key/repository định kỳ.
- Kiểm thử notification trong Redis container có cấu hình tương ứng.
- Quan sát subscriber và tình trạng kết nối tới Redis.

## 12. Tốc độ tạo session

Creation rate thường được đo bằng số session mới trong một cửa sổ thời gian:

- session tạo mới mỗi giây;
- session tạo mới mỗi phút;
- session tạo mới theo application hoặc backend;
- tỷ lệ tạo session so với request hoặc lượt đăng nhập, nếu có định nghĩa rõ.

Spring Session có SessionCreatedEvent. Có thể tăng Micrometer Counter khi nhận event:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionCreatedEvent;
import org.springframework.stereotype.Component;

@Component
class SessionCreationMetrics {

    private final Counter created;

    SessionCreationMetrics(MeterRegistry registry) {
        this.created = Counter.builder("app.session.created")
                .description("Number of session creation events")
                .register(registry);
    }

    @EventListener
    void onCreated(SessionCreatedEvent event) {
        created.increment();
    }
}
~~~

Đây là bộ đếm sự kiện trong một application process. Nếu backend/event mechanism phát cùng một event tới nhiều node, tổng các counter cục bộ có thể đếm lặp. Hãy xác minh event delivery semantics và chọn một nơi tổng hợp có kiểm soát.

Ngoài ra, event tạo session không nhất thiết đồng nghĩa với một phiên đã được lưu bền vững thành công trong mọi implementation. Nếu cần đo persisted sessions, instrument thao tác save thành công hoặc đối chiếu bằng snapshot storage. Đặt tên metric theo điều thực sự được đếm, ví dụ session creation events thay vì successful persisted sessions nếu chưa chứng minh được quan hệ đó.

## 13. Tốc độ hết hạn và tốc độ xóa

Expiration rate là số session hết hạn trong một khoảng thời gian. Delete rate là số session bị xóa khỏi repository, có thể bao gồm logout, revoke, cleanup hoặc thao tác khác tùy implementation. Hai chỉ số này không nhất thiết bằng nhau.

Có thể dùng SessionExpiredEvent để tăng counter expiration và SessionDeletedEvent để tăng counter deletion. Nhưng phải hiểu semantics backend:

- JDBC cleanup job có thể xóa nhiều bản ghi hết hạn theo một câu lệnh; không nên mặc định mỗi hàng bị xóa đều tạo một application event.
- Redis expiration notification có thể phát event khi key hết hạn vật lý, không đúng ngay mili giây logic timeout.
- Event có thể bị mất khi subscriber không hoạt động.
- Các node có thể nhận cùng thông báo backend; không cộng mù quáng counter của mọi node.

Nếu cần đo chính xác số hàng cleanup, instrument job hoặc ghi nhận số hàng mà câu lệnh cleanup xóa được. Nếu cần đo session hết hạn logic, dùng event/repository logic và reconciliation. Ghi rõ định nghĩa metric để dashboard không trộn hai ý nghĩa.

## 14. Dùng Micrometer cho counter và gauge

Micrometer cung cấp Counter cho số lần sự kiện xảy ra và Gauge cho giá trị hiện tại. Ví dụ tạo metric active sessions bằng một AtomicLong được cập nhật bởi scheduled reconciliation:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class ActiveSessionGauge {

    private final AtomicLong active = new AtomicLong();

    ActiveSessionGauge(MeterRegistry registry) {
        Gauge.builder("app.session.active", active, AtomicLong::get)
                .description("Last reconciled number of active sessions")
                .register(registry);
    }

    @Scheduled(fixedDelay = 60000)
    void reconcile() {
        // Đếm từ repository/backend theo chiến lược đã chọn.
        // Chỉ cập nhật active sau khi phép đo thành công.
    }
}
~~~

Bật scheduling bằng @EnableScheduling trong cấu hình phù hợp. Trong ví dụ, phần truy vấn được tách khỏi metric để có thể chọn JDBC, Redis hoặc một dịch vụ reconciliation riêng.

Không đặt active về 0 khi backend query thất bại. Giá trị 0 sẽ gây hiểu nhầm rằng toàn bộ người dùng đã logout. Giữ snapshot cuối cùng và phát metric riêng cho thời điểm snapshot, trạng thái đo hoặc lỗi reconciliation. Dashboard nên hiển thị tuổi của snapshot để người vận hành biết số liệu đã cũ.

## 15. Tên metric và Prometheus

Nên dùng tên metric ổn định và định nghĩa rõ:

| Metric logic | Loại | Ví dụ ý nghĩa |
|---|---|---|
| app.session.active | Gauge | Số session còn hiệu lực tại snapshot gần nhất |
| app.session.created | Counter | Tổng event tạo session đã quan sát |
| app.session.expired | Counter | Tổng event hết hạn đã quan sát |
| app.session.deleted | Counter | Tổng event xóa đã quan sát |
| app.session.expired.backlog | Gauge | Số bản ghi hết hạn còn trong storage |
| app.session.reconcile.duration | Timer | Thời gian lấy snapshot |
| app.session.reconcile.errors | Counter | Số lần snapshot thất bại |

Prometheus thường chuyển metric name/tag theo quy tắc exporter. Với counter, dùng rate hoặc increase trong cửa sổ thời gian thay vì đọc giá trị tích lũy:

~~~promql
sum(rate(app_session_created_total[5m]))
~~~

Tốc độ hết hạn:

~~~promql
sum(rate(app_session_expired_total[5m]))
~~~

Gauge active sessions:

~~~promql
sum(app_session_active)
~~~

Các biểu thức này chỉ đúng khi metric đã được chuẩn hóa để mỗi session/event chỉ được tính một lần trong phạm vi tổng hợp. Nếu mọi node đều publish cùng một snapshot toàn cụm, không dùng sum; chọn một nguồn authoritative hoặc dùng max/leader metric theo kiến trúc.

## 16. Cardinality và quyền riêng tư

Không thêm các giá trị sau làm metric tag:

- session ID;
- cookie value;
- username/email;
- principal ID;
- IP đầy đủ nếu tạo số lượng series lớn hoặc có rủi ro riêng tư;
- URL có ID tài nguyên hoặc query string.

Các tag này tạo cardinality cao, làm tăng bộ nhớ/time series và có thể làm lộ thông tin cá nhân hoặc bearer credential. Chỉ dùng tag có tập giá trị giới hạn như backend, application, environment, region hoặc kết quả operation.

Nếu cần phân tích theo tenant, dùng nhóm tenant đã được kiểm soát hoặc hệ thống analytics riêng có chính sách dữ liệu phù hợp; không mặc định đưa tenant ID của hàng triệu khách hàng vào metric.

## 17. Đo theo từng instance và toàn cụm

Có hai phạm vi metric:

**Per-instance**

- số request/session operation do node xử lý;
- số event node đó quan sát;
- trạng thái kết nối Redis/JDBC của node;
- lỗi và latency cục bộ.

**Cluster-wide**

- tổng session active trong shared store;
- tổng session tạo mới/hết hạn theo event duy nhất;
- expired backlog toàn kho;
- tổng dung lượng và tải backend.

Không cộng các gauge toàn cụm được lặp trên từng node. Không giả định counter event là duy nhất nếu backend phát pub/sub tới tất cả node. Đặt tên và tag rõ phạm vi, ví dụ scope=instance hoặc scope=cluster.

Với active sessions toàn cụm, có thể chạy một reconciler leader, một scheduled job riêng hoặc một metric exporter chuyên dụng. Nếu dùng leader election, theo dõi leader và xử lý chuyển quyền; snapshot phải có timestamp để phát hiện khi không còn node nào cập nhật.

## 18. Diễn giải creation/expiration rate

Một số tình huống:

| Quan sát | Diễn giải có thể | Điều cần kiểm tra |
|---|---|---|
| Created tăng đột biến | Login burst, session regeneration, bot hoặc client tạo session ở endpoint công khai | Tỷ lệ login, request anonymous, session cookie và traffic bất thường |
| Active tăng nhanh, expiration thấp | Lượng người dùng tăng hoặc timeout dài | Backlog, max inactive interval, session creation path |
| Created ổn định, active giảm mạnh | Logout/revoke tăng, timeout giảm hoặc backend mất dữ liệu | Delete events, expiration, Redis/JDBC errors |
| Expired rate tăng cao theo giờ | Traffic trước đó tạo nhiều session có timeout tương tự | Login peak, timeout distribution và job cleanup |
| Expired backlog tăng liên tục | Cleanup không chạy hoặc xóa không theo kịp | JDBC cleanup logs, Redis TTL, quyền và index |
| Created cao nhưng active không tăng | Session ngắn hạn, bot, session bị xóa ngay hoặc event bị đếm lặp | Endpoint tạo session, logout/delete, event semantics |
| Active gauge đứng yên lâu | Reconciliation task lỗi hoặc metric exporter không cập nhật | Snapshot timestamp, scheduler và backend connectivity |
| Mỗi node báo cùng một active total | Gauge cluster bị lặp theo instance | Cách publish/tổng hợp metric |

Không kết luận người dùng tăng/giảm chỉ từ một metric. Đối chiếu login success, request rate, authentication failure, backend latency và event/delete counts.

## 19. Dung lượng và kích thước session

Số session chỉ là một phần chi phí storage. Hai hệ thống có cùng 100.000 session nhưng dung lượng khác nhau nếu số attributes và kích thước payload khác nhau.

Theo dõi thêm:

- kích thước Redis memory/keyspace;
- kích thước bảng SPRING_SESSION và SPRING_SESSION_ATTRIBUTES;
- số attributes trung bình và phân vị payload nếu có thể đo an toàn;
- tốc độ ghi/đọc session;
- Redis evictions, memory fragmentation và replication lag;
- JDBC index size, transaction log/WAL, lock wait và thời gian cleanup.

Không ghi toàn bộ session payload vào metric hoặc log để tính kích thước. Có thể đo kích thước serialize trước khi lưu trong một decorator nếu overhead được chấp nhận, hoặc dùng thống kê backend theo cách phù hợp.

## 20. Tần suất lấy snapshot

Snapshot càng thường xuyên thì gauge càng mới nhưng chi phí truy vấn càng lớn. Chọn chu kỳ theo quy mô và nhu cầu vận hành:

| Chu kỳ ví dụ | Dùng khi | Lưu ý |
|---|---|---|
| 10–15 giây | Quy mô vừa, cần phát hiện thay đổi nhanh | Chỉ dùng nếu query rẻ và backend chịu được |
| 30–60 giây | Dashboard vận hành thông thường | Thường là điểm bắt đầu hợp lý |
| 5 phút | Kho rất lớn hoặc metric ít nhạy thời gian | Phải hiển thị snapshot age và alert khi quá cũ |

Không chạy COUNT(*) toàn bảng mỗi giây chỉ vì Prometheus scrape mỗi 15 giây. Scrape metric nên đọc giá trị gauge đã lấy mẫu; scheduler reconciliation có chu kỳ riêng.

## 21. Đồng hồ và tính nhất quán thời gian

Spring Session dựa vào thời điểm truy cập và max inactive interval. Nếu application nodes có clock skew, chúng có thể tính thời điểm hết hạn khác nhau. Khi query JDBC bằng epoch milliseconds, dùng một Clock được đồng bộ và thống nhất đơn vị.

Redis TTL được backend quản lý, nhưng logic repository vẫn phải được hiểu theo thời điểm hết hạn. Không dùng múi giờ hiển thị hoặc local time string để so sánh với epoch milliseconds.

Trong test, có thể inject Clock cố định hoặc điều khiển thời gian để kiểm tra timeout. Với integration test Redis/JDBC thật, cần kiểm tra cả logic expiration và thời điểm backend dọn dữ liệu vì hai việc không nhất thiết xảy ra đồng thời.

## 22. Kiểm thử các chỉ số

| Ca kiểm thử | Thao tác | Kết quả cần xác nhận |
|---|---|---|
| Tạo session | Tạo một session mới và lưu | Created counter tăng đúng theo semantics |
| Khôi phục session | Gửi request tiếp theo với cookie | Active count không tăng thêm session mới |
| Nhiều thiết bị | Tạo hai session cho cùng principal | Active sessions tăng hai; unique principal tăng một |
| Logout | Invalidate một session | Deleted metric tăng theo event/operation được định nghĩa; active giảm sau reconciliation |
| Expiration logic | Đợi quá max inactive interval | Repository không trả session hết hạn |
| JDBC cleanup | Chạy cleanup sau expiration | Expired backlog giảm; không coi cleanup count là expiry rate |
| Redis TTL | Đợi key hết hạn và quan sát notification | Event hoạt động theo cấu hình; đối chiếu bằng snapshot |
| Event subscriber offline | Ngắt listener rồi tạo expiration | Phát hiện event có thể mất; reconciliation vẫn tìm đúng trạng thái |
| Multi-instance | Tạo ở A, đọc ở B, logout ở B | Gauge toàn cụm không bị cộng lặp |
| Backend outage | Làm Redis/JDBC unavailable | Snapshot lỗi được ghi nhận; gauge không bị đặt về 0 giả |
| Namespace isolation | Chạy hai suite cùng backend | Mỗi suite chỉ đếm dữ liệu thuộc namespace của mình |
| Clock skew | Dùng clock test khác nhau | Xác định tác động đến expiration và snapshot |

Test counter phải phân biệt số event được phát với số session thực sự đã lưu. Test gauge phải xác minh phép đo storage, không chỉ kiểm tra AtomicLong được cập nhật. Với Redis, bật keyspace notifications trong container nếu test event expiration; với JDBC, kiểm tra EXPIRY_TIME và cleanup job theo schema thật.

## 23. Cảnh báo vận hành

Một số cảnh báo hữu ích:

- Active sessions vượt ngưỡng dung lượng đã kiểm thử.
- Creation rate tăng đột biến so với baseline.
- Expiration rate hoặc delete rate thay đổi bất thường.
- Expired backlog vượt ngưỡng hoặc tiếp tục tăng qua nhiều chu kỳ.
- Snapshot active sessions quá cũ.
- Reconciliation task lỗi liên tiếp.
- Redis memory/eviction hoặc JDBC table/index growth vượt dự báo.
- Event subscriber mất kết nối hoặc Redis notification không được cấu hình.

Ngưỡng cần dựa trên baseline, giờ cao điểm và giới hạn backend. Một đợt login đầu giờ làm việc có thể khiến creation rate tăng bình thường; alert cần kết hợp tỷ lệ lỗi, active count và tài nguyên storage.

## 24. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Đếm mọi hàng JDBC | Tính cả bản ghi đã hết hạn | Lọc EXPIRY_TIME theo thời điểm đo |
| Dùng Redis DBSIZE | Tính cả key index, expiration và ứng dụng khác | Dùng metric/repository-specific count hoặc scan namespace có kiểm soát |
| Dùng KEYS để đếm production | Có thể chặn Redis | Dùng SCAN định kỳ hoặc instrumentation |
| Coi active sessions là online users | Đếm nhiều session cho cùng người | Định nghĩa unique principal/online riêng |
| Chỉ dựa vào expiration events | Bỏ lỡ event khi subscriber ngắt | Reconcile với backend |
| Cộng event của mọi node | Đếm trùng thông báo pub/sub | Xác định phạm vi và deduplicate/centralize |
| Đặt gauge về 0 khi query lỗi | Dashboard báo toàn bộ session biến mất | Giữ snapshot cuối và metric lỗi/độ cũ |
| Đếm mỗi request là một session mới | Phóng đại creation rate | Đếm sự kiện tạo session thực tế |
| Coi cleanup rows là expiration rate | Trộn thời điểm hết hạn với thời điểm xóa vật lý | Tách hai metric |
| Dùng session ID làm metric tag | Cardinality cao và lộ credential | Dùng tag có tập giá trị thấp |

## 25. Quy trình xây dashboard

1. Thống nhất định nghĩa active, created, expired, deleted và backlog.
2. Chọn nguồn đo cho mỗi chỉ số: repository event, storage snapshot, cleanup result hoặc backend metric.
3. Xác định phạm vi per-instance hay cluster-wide.
4. Triển khai counter cho lifecycle events và gauge cho snapshot.
5. Với JDBC, đo theo EXPIRY_TIME và kiểm tra index/query plan.
6. Với Redis, tránh DBSIZE/KEYS; hiểu key namespace, TTL và notification.
7. Thêm timestamp/age cho mỗi lần reconciliation.
8. Đối chiếu cân bằng created-expired-deleted với active snapshot để phát hiện drift.
9. Kiểm thử nhiều node, subscriber outage, backend outage và cleanup.
10. Đặt alert theo baseline và capacity đã đo.

Một dashboard cơ bản nên có:

- Active sessions hiện tại và thời điểm snapshot.
- Session creation rate theo 1 phút/5 phút.
- Session expiration rate theo 1 phút/5 phút.
- Session deletion/logout rate.
- Expired record backlog.
- Repository operation latency/error rate.
- Redis memory hoặc JDBC table/index size.

## 26. Nguyên tắc triển khai

- Định nghĩa active session theo expiration logic, không theo số bản ghi vật lý đơn thuần.
- Phân biệt session, principal và người dùng online.
- Dùng gauge cho active count, counter cho lifecycle events và rate cho tốc độ.
- Kết hợp event với reconciliation từ storage vì event có thể mất, trùng hoặc đến trễ.
- Với JDBC, dùng EXPIRY_TIME và tính theo epoch milliseconds.
- Với Redis, không dùng DBSIZE hoặc KEYS làm phép đếm session production.
- Đo expired backlog riêng với expiration rate và cleanup delete count.
- Đo toàn cụm ở một nguồn có thẩm quyền hoặc tổng hợp đúng phạm vi.
- Không chạy truy vấn đếm nặng ở mỗi request hoặc mỗi lần scrape.
- Không dùng session ID, cookie hoặc principal ID làm metric tag.
- Khi snapshot thất bại, giữ giá trị cuối cùng và báo độ cũ/lỗi đo.
- Kiểm thử session create, access, logout, expiration, multi-node và backend outage.

Số phiên hoạt động cho biết quy mô trạng thái hiện tại; số phiên tạo mới và tốc độ hết hạn cho biết hệ thống đang thay đổi nhanh đến đâu. Để các số liệu này có ý nghĩa, cần tách expiration logic khỏi cleanup vật lý, tách session khỏi unique user, và kết hợp event với snapshot storage. Spring Session cung cấp các điểm tích hợp vòng đời, còn Micrometer/Prometheus giúp ghi nhận và tổng hợp. Một phép đo định kỳ được cô lập và đối chiếu sẽ giúp dashboard phản ánh đúng tình trạng toàn cụm mà không tạo thêm tải không cần thiết lên Redis hoặc JDBC.

## Tài liệu tham khảo

- Spring Session – Core API and session events: https://docs.spring.io/spring-session/reference/
- Spring Session – JDBC configuration and expired session cleanup: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session – Redis configuration and expiration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Micrometer – Counters, gauges and meters: https://docs.micrometer.io/micrometer/reference/concepts/meters.html
- Prometheus – Querying basics: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Redis – Keyspace notifications: https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/
