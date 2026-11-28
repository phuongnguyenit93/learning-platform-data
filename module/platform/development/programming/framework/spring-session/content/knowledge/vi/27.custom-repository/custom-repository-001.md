# Khi nào cần tự xây repository thay vì dùng triển khai sẵn có

Spring Session tách API session khỏi nơi lưu trữ. Ứng dụng tiếp tục làm việc với HttpSession trong Servlet hoặc WebSession trong WebFlux, còn SessionRepository hoặc ReactiveSessionRepository chịu trách nhiệm tạo, tìm, lưu và xóa dữ liệu phiên. Các triển khai có sẵn như Redis và JDBC đáp ứng phần lớn nhu cầu phổ biến, đồng thời đã xử lý nhiều chi tiết khó như định danh, timeout, serialization, index, cleanup và tích hợp với vòng đời request.

Tự xây repository chỉ hợp lý khi có yêu cầu kỹ thuật cụ thể mà repository có sẵn không đáp ứng được và các điểm mở rộng nhẹ hơn cũng không giải quyết được. Ví dụ có thể là một kho dữ liệu nội bộ bắt buộc, giao thức lưu trữ riêng, yêu cầu định dạng hoặc mã hóa đặc thù, hoặc một mô hình phân phối dữ liệu mà implementation hiện tại không hỗ trợ. Việc tự xây đồng nghĩa đội ngũ phải chịu trách nhiệm về toàn bộ hợp đồng lưu phiên, tính nhất quán, bảo mật, hết hạn, sự kiện, nâng cấp và vận hành.

Không nên tự viết repository chỉ vì muốn đổi tên cookie, đổi timeout, thêm một thuộc tính, chỉnh schema JDBC hoặc dùng một serializer khác. Những việc đó thường đã có cấu hình hoặc extension point. Cũng không nên dùng session repository để bảo vệ số dư, tồn kho hay bất biến nghiệp vụ; những dữ liệu đó cần nguồn chuẩn và transaction nghiệp vụ riêng.

## 1. Repository là ranh giới giữa API session và storage

Spring Session cung cấp hai hợp đồng chính:

| Hợp đồng | Dành cho | Kiểu xử lý |
|---|---|---|
| SessionRepository<S extends Session> | Ứng dụng Servlet | Đồng bộ |
| ReactiveSessionRepository<S extends Session> | Ứng dụng WebFlux | Reactive, dùng Mono |

Với Servlet, SessionRepository<S> có các thao tác cốt lõi:

- createSession(): tạo một session mới chưa được lưu.
- save(S session): lưu trạng thái session.
- findById(String id): tìm session theo định danh; trả null nếu không tồn tại hoặc không còn hợp lệ.
- deleteById(String id): xóa session theo định danh.

Với WebFlux, ReactiveSessionRepository<S> cung cấp các thao tác tương ứng qua Mono<S> và Mono<Void>. Không gọi block() để biến repository reactive thành đồng bộ trong request path.

Session mô tả dữ liệu mà repository cần lưu, gồm ID, thời điểm tạo, thời điểm truy cập gần nhất, khoảng không hoạt động tối đa, các thuộc tính và trạng thái hết hạn. Repository phải bảo đảm khi khôi phục session, các giá trị này phản ánh đúng trạng thái đã lưu.

Spring Session dùng repository ở phía dưới filter/manager. Với Servlet, SessionRepositoryFilter bọc HttpSession và điều phối việc đọc/lưu theo request lifecycle. Với WebFlux, WebSessionManager dùng reactive repository để tạo và khôi phục WebSession. Vì vậy, một repository custom phải đáp ứng đúng semantics mà lớp tích hợp phía trên mong đợi; chỉ lưu một map thuộc tính đơn giản là chưa đủ.

## 2. Bắt đầu bằng câu hỏi: có thật sự cần repository mới?

Trước khi thiết kế implementation, mô tả yêu cầu không được đáp ứng:

- Backend bắt buộc có phải là hệ thống nội bộ không được Spring Session hỗ trợ?
- Có cần ghi session vào một giao thức hoặc dịch vụ lưu trữ riêng?
- Có yêu cầu mã hóa, phân vùng, residency hoặc kiểm soát dữ liệu mà cấu hình hiện có không đáp ứng?
- Có cần semantics về TTL, truy vấn, transaction hoặc failover khác với các implementation có sẵn?
- Có cần chia sẻ session qua nhiều ứng dụng hoặc nhiều vùng địa lý theo một giao thức riêng?
- Có thể đáp ứng bằng serializer, namespace, schema, index resolver hoặc customizer không?
- Có thể bọc repository hiện có bằng adapter/decorator nhỏ không?

Hãy viết tiêu chí chấp nhận có thể kiểm thử. Ví dụ: “mọi session phải được lưu tại kho X, có TTL được gia hạn nguyên tử cùng lần ghi, và có thể khôi phục từ hai vùng theo chính sách Y” cụ thể hơn nhiều so với “cần repository linh hoạt hơn”.

Nếu chưa thể mô tả yêu cầu bằng hành vi đo được, chưa có cơ sở để duy trì một implementation riêng. Hãy đo bottleneck hoặc thử cấu hình hiện có trước.

## 3. Khi nào triển khai sẵn có là đủ?

Redis và JDBC giải quyết hai nhóm nhu cầu thường gặp:

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Session chia sẻ giữa nhiều instance, cần truy cập nhanh và đã vận hành Redis | Spring Session Redis |
| Muốn dùng database quan hệ, schema và backup hiện có | Spring Session JDBC |
| Chỉ cần session trong một tiến trình để phát triển/test | MapSessionRepository hoặc cấu hình test tương ứng |
| Cần tìm session theo principal với Redis | Repository Redis indexed phù hợp phiên bản |
| Cần đổi tên cookie hoặc thuộc tính cookie | CookieSerializer |
| Cần đổi session timeout | Cấu hình repository/Boot property |
| Cần thay namespace hoặc tên bảng | Cấu hình namespace/table name tương ứng |
| Cần đổi serialization | Cấu hình serializer phù hợp |
| Cần tùy biến repository được auto-configure | SessionRepositoryCustomizer hoặc extension point tương ứng |

Đừng chọn MapSessionRepository làm backend production nhiều instance nếu mỗi node có map riêng. Session sẽ không được chia sẻ giữa node và mất khi tiến trình khởi động lại. Nó hữu ích cho test, demo hoặc một ứng dụng đơn tiến trình có chủ đích.

## 4. Các lựa chọn nhẹ hơn tự xây repository

Trước khi viết implementation mới, xem xét các extension point sau:

1. **Cấu hình:** timeout, namespace, cookie, table name, cleanup cron và các thuộc tính đã được hỗ trợ.
2. **Serializer:** thay đổi cách mã hóa/giải mã thuộc tính mà không thay toàn bộ vòng đời repository.
3. **IndexResolver:** thay đổi cách xác định principal hoặc index bổ sung nếu repository indexed cho phép.
4. **Customizer:** tùy chỉnh bean/repository do Spring Boot hoặc Spring Session tạo.
5. **Adapter/decorator:** bọc repository hiện có để thêm metric, audit metadata hoặc quy tắc hẹp mà không viết lại storage engine.
6. **Repository có sẵn khác:** kiểm tra module Spring Session phù hợp với backend hoặc application type trước khi tự triển khai.

Ví dụ dùng customizer để điều chỉnh một repository JDBC đã được cấu hình:

~~~java
@Bean
SessionRepositoryCustomizer<JdbcIndexedSessionRepository> jdbcCustomizer() {
    return repository -> repository.setDefaultMaxInactiveInterval(
            Duration.ofMinutes(20));
}
~~~

Đây là ví dụ về cách tùy chỉnh repository có sẵn theo API của phiên bản đang dùng. Nếu chỉ cần đổi timeout mặc định, customizer nhỏ hơn và ít rủi ro hơn một repository mới.

Không dùng customizer để thay đổi những semantics ngoài hợp đồng nếu repository không hỗ trợ. Nếu yêu cầu mới đòi hỏi một mô hình lưu trữ hoàn toàn khác, hãy cân nhắc implementation custom sau khi đã đánh giá các lựa chọn trên.

## 5. Những trường hợp custom repository có thể hợp lý

### Backend không được hỗ trợ

Tổ chức có một nền tảng lưu trữ nội bộ bắt buộc, có API ổn định và khả năng vận hành phù hợp. Không có Spring Session repository tương thích. Khi đó, một adapter triển khai SessionRepository có thể cho phép ứng dụng tiếp tục dùng API HttpSession.

### Quy tắc ghi/đọc đặc thù

Kho yêu cầu một thao tác nguyên tử riêng để lưu payload và TTL, hoặc cần một giao thức transaction mà implementation có sẵn không thể cấu hình. Cần chứng minh semantics đó là yêu cầu thực tế, không phải giả định.

### Mô hình mã hóa hoặc phân vùng riêng

Dữ liệu session phải được mã hóa theo tenant/key version, phân vùng theo tổ chức hoặc lưu tại vùng dữ liệu được chỉ định. Trước khi viết repository, kiểm tra serializer, encryption converter, namespace và khả năng phân vùng ở lớp storage đã đủ chưa.

### Tích hợp hệ thống cũ

Ứng dụng phải đọc/ghi một session format đã tồn tại trong hệ thống cũ. Adapter có thể chuyển đổi format cũ sang Session của Spring Session. Phải có kế hoạch xử lý dữ liệu lỗi, version schema và migration.

### Nhu cầu reactive thực sự

Ứng dụng WebFlux cần backend có API non-blocking nhưng không có repository reactive phù hợp. Một implementation reactive có thể hợp lý; bọc lời gọi blocking bằng Mono.fromCallable() không biến backend thành non-blocking và không nên được xem là giải pháp hiệu năng tương đương.

## 6. Những lý do không đủ để tự xây

| Lý do thường được nêu | Hướng nên thử trước |
|---|---|
| Muốn đổi tên cookie | CookieSerializer hoặc HttpSessionIdResolver |
| Muốn timeout khác | Cấu hình max inactive interval |
| Muốn thêm thuộc tính session | setAttribute và serializer tương thích |
| Muốn đổi tên bảng JDBC | Cấu hình table name và schema |
| Muốn log mỗi lần lưu | Decorator, listener hoặc instrumentation |
| Muốn thêm metric | Micrometer/instrumentation quanh repository |
| Muốn tìm session theo người dùng | Repository indexed và principal index |
| Muốn dùng session làm distributed lock | Chọn cơ chế coordination/transaction phù hợp; repository session không phải lock |
| Muốn số dư/tồn kho luôn đúng | Database transaction, constraint, ledger hoặc atomic update |
| Muốn khắc phục session bị mất do cấu hình sai | Sửa namespace, topology, persistence hoặc failover |
| Muốn nhanh hơn nhưng chưa benchmark | Đo latency, payload, serialization, network và backend trước |

Tự xây repository làm tăng diện tích mã phải bảo trì. Một lỗi nhỏ trong expiration, serialization hoặc concurrent update có thể khiến người dùng bị đăng xuất, session bị hồi sinh hoặc dữ liệu nhạy cảm bị lộ.

## 7. Quyết định theo ma trận chi phí và rủi ro

Có thể đánh giá các lựa chọn theo bảng:

| Tiêu chí | Dùng repository có sẵn | Customizer/decorator | Repository custom |
|---|---|---|---|
| Thời gian triển khai | Thấp | Trung bình thấp | Cao |
| Trách nhiệm storage semantics | Chủ yếu do implementation cung cấp | Phần lớn giữ nguyên | Đội ngũ tự chịu |
| Tương thích nâng cấp | Theo dòng Spring Session | Cần kiểm tra extension point | Cần tự duy trì contract |
| TTL/expiration | Có sẵn theo backend | Giữ semantics, tùy biến hẹp | Phải tự thiết kế và kiểm thử |
| Serialization | Cấu hình có sẵn | Có thể thay serializer | Phải tự quản lý format/version |
| Concurrency | Theo implementation/backend | Không tự giải quyết conflict lớn | Phải định nghĩa rõ |
| Multi-instance | Được hỗ trợ nếu dùng shared store | Giữ cơ chế shared store | Phải tự bảo đảm |
| Quan sát/vận hành | Có tài liệu và metric nền tảng | Bổ sung metric riêng | Tự xây dashboard/runbook |
| Rủi ro dài hạn | Thấp hơn nếu dùng đúng | Trung bình | Cao hơn đáng kể |

Không chọn custom repository chỉ vì có một yêu cầu ở một hàng. Cần xem tổng thể: yêu cầu đó có bắt buộc không, extension point có đáp ứng không, và đội ngũ có khả năng vận hành implementation mới trong nhiều năm không.

## 8. Thiết kế hợp đồng repository trước khi viết code

Nếu quyết định tự xây, hãy viết rõ các hành vi sau trước khi chọn công nghệ:

- **Tạo:** session mới có ID đủ ngẫu nhiên, creation time và timeout mặc định.
- **Tìm:** trả session nếu tồn tại và chưa hết hạn; trả không có session nếu không tồn tại hoặc đã hết hạn.
- **Lưu:** lưu ID, creation time, last access time, max inactive interval và toàn bộ attributes theo hợp đồng.
- **Xóa:** xóa dữ liệu session và mọi index/metadata phụ liên quan.
- **Đổi ID:** bảo đảm ID cũ không còn khôi phục phiên sau khi đổi.
- **TTL:** đồng bộ expiration của backend với thời gian hiệu lực logic.
- **Đồng thời:** xác định cách xử lý nhiều request cùng đọc/sửa/lưu một session.
- **Serialization:** định nghĩa format, version, class compatibility và xử lý dữ liệu hỏng.
- **Sự kiện:** xác định có cần event tạo, xóa, hết hạn và cách phân phối chúng giữa các node.
- **Lỗi:** phân biệt session không tồn tại với backend unavailable hoặc serialization failure.
- **Bảo mật:** bảo vệ session ID, thuộc tính nhạy cảm, kết nối và backup.
- **Migration:** xác định cách chuyển dữ liệu và rollback khi nâng schema/format.

Hợp đồng phải nêu rõ tính nhất quán. Ví dụ, sau khi deleteById(id) hoàn tất thành công, một lần findById(id) tiếp theo trên bất kỳ instance nào có được phép trả session cũ không? Với định danh đã thu hồi, câu trả lời thường phải là không trong giới hạn consistency được cam kết.

## 9. Triển khai SessionRepository cho Servlet

Một repository đồng bộ có thể triển khai SessionRepository<MapSession>. MapSession là implementation session có sẵn, giúp tránh phải tự viết lại cấu trúc thuộc tính và metadata cơ bản.

Ví dụ dưới đây là skeleton cho một adapter lưu bản ghi vào một storage service do ứng dụng cung cấp:

~~~java
public final class CustomSessionRepository
        implements SessionRepository<MapSession> {

    private final SessionRecordStore store;

    public CustomSessionRepository(SessionRecordStore store) {
        this.store = store;
    }

    @Override
    public MapSession createSession() {
        MapSession session = new MapSession();
        session.setMaxInactiveInterval(Duration.ofMinutes(30));
        return session;
    }

    @Override
    public void save(MapSession session) {
        store.upsert(toRecord(session));
    }

    @Override
    public MapSession findById(String id) {
        return store.find(id)
                .map(this::restore)
                .filter(session -> !session.isExpired())
                .orElse(null);
    }

    @Override
    public void deleteById(String id) {
        store.delete(id);
    }

    private SessionRecord toRecord(MapSession session) {
        // Chuyển ID, timestamps, timeout và attributes sang storage format.
        throw new UnsupportedOperationException("Implement mapping");
    }

    private MapSession restore(SessionRecord record) {
        // Khôi phục MapSession và tất cả metadata/attributes đã lưu.
        throw new UnsupportedOperationException("Implement mapping");
    }
}
~~~

Đây là skeleton minh họa hợp đồng, không phải implementation có thể đưa thẳng vào production. SessionRecordStore, SessionRecord, toRecord và restore là kiểu/phương thức thuộc ứng dụng và cần được triển khai. Phần mapping phải giữ nguyên session ID, creation time, last access time, max inactive interval và tất cả attributes.

Khi findById phát hiện session hết hạn, implementation phải bảo đảm dữ liệu được xử lý theo chính sách expiration. Có thể xóa ngay hoặc để cleanup job dọn vật lý sau đó, nhưng không được trả một session đã hết hạn như phiên hợp lệ. Nếu store.find thất bại vì backend unavailable, phải ném lỗi phù hợp thay vì trả null; null có nghĩa là không tìm thấy session, không có nghĩa kho dữ liệu đang lỗi.

Đăng ký repository với Spring Session Servlet:

~~~java
@Configuration
@EnableSpringHttpSession
public class CustomHttpSessionConfiguration {

    @Bean
    SessionRepository<MapSession> sessionRepository(SessionRecordStore store) {
        return new CustomSessionRepository(store);
    }
}
~~~

EnableSpringHttpSession cấu hình tích hợp HttpSession dựa trên SessionRepository được cung cấp. Trong ứng dụng Spring Boot, cần kiểm tra auto-configuration để tránh tạo hai repository hoặc hai cơ chế quản lý session cùng lúc. Chỉ có một repository được gắn với filter cho ứng dụng.

## 10. ReactiveSessionRepository cho WebFlux

Nếu ứng dụng chạy WebFlux, repository phải triển khai ReactiveSessionRepository<S> và giữ toàn bộ I/O trong reactive pipeline:

~~~java
public interface ReactiveSessionRepository<S extends Session> {
    Mono<S> createSession();
    Mono<Void> save(S session);
    Mono<S> findById(String id);
    Mono<Void> deleteById(String id);
}
~~~

Các phương thức trên thể hiện hợp đồng reactive cốt lõi. Implementation phải dùng client non-blocking của backend hoặc một cơ chế thực sự phù hợp với tải và scheduler. Không gọi block() trong repository hoặc controller để chờ database đồng bộ.

WebFlux có thể bật tích hợp repository reactive qua EnableSpringWebSession và cung cấp bean ReactiveSessionRepository. Không dùng EnableSpringHttpSession trong WebFlux thuần và không đưa repository Servlet đồng bộ vào reactive request path.

Nếu backend chỉ có API blocking, hãy đánh giá một adapter chạy trên scheduler dành cho blocking I/O, giới hạn concurrency và pool. Cách này có thể là bước chuyển tiếp, nhưng không mang lại đặc tính non-blocking thật của Redis reactive hoặc một backend reactive native.

## 11. Có cần hỗ trợ tìm session theo principal không?

SessionRepository cơ bản tìm theo session ID. Nếu ứng dụng cần liệt kê hoặc thu hồi tất cả phiên của một người dùng, cần thêm khả năng index:

- Servlet: FindByIndexNameSessionRepository<S>.
- WebFlux: ReactiveFindByIndexNameSessionRepository<S>.

Các interface này hỗ trợ tìm theo index name/value, trong đó có principal name index. Nếu tự triển khai, cần định nghĩa cách populate index từ danh tính đã xác thực, cách cập nhật khi principal thay đổi, cách xóa index khi session bị xóa/hết hạn và cách phục hồi index nếu backend gặp lỗi.

Không tự lấy principal name từ request body hoặc một session attribute do client có thể sửa. Giá trị index phải xuất phát từ Authentication đã được xác thực hoặc nguồn danh tính tin cậy.

Nếu không cần tra cứu theo principal, đừng triển khai index chỉ vì “có thể sẽ cần”. Index thêm thao tác ghi, dung lượng và công việc cleanup. Chỉ hỗ trợ capability mà ứng dụng thực sự dùng.

## 12. TTL và expiration phải nhất quán

Timeout của Spring Session được biểu diễn bằng max inactive interval và thời điểm truy cập gần nhất. Backend thường có TTL vật lý, expiration timestamp hoặc cleanup job. Hai cơ chế phải tương thích:

1. Khi lưu session, tính expiration từ last access time và max inactive interval.
2. Ghi payload cùng TTL/expiry metadata theo thao tác nhất quán.
3. Khi đọc, kiểm tra session đã hết hạn trước khi trả về.
4. Khi gia hạn, cập nhật metadata và TTL sao cho không có cửa sổ mà session logic còn hợp lệ nhưng backend đã xóa, hoặc session logic đã hết hạn nhưng backend vẫn trả hợp lệ.
5. Khi xóa, dọn cả dữ liệu và index liên quan.

Không chỉ dựa vào TTL backend. Một số store xóa key bất đồng bộ hoặc phát expiration event trễ. Repository phải có kiểm tra expiration logic khi tìm session. Ngược lại, không chỉ kiểm tra timestamp mà để key tồn tại mãi; cần cleanup vật lý để tránh rò rỉ dung lượng.

## 13. Concurrency và lost update

Một request có thể đọc session ở thời điểm T1, request khác đọc cùng session ở T2, cả hai sửa attributes rồi lưu ở T3/T4. Nếu repository ghi toàn bộ snapshot, request lưu sau có thể ghi đè thay đổi của request trước.

Tự xây repository phải chọn một chiến lược:

- optimistic locking bằng version;
- compare-and-set hoặc conditional update;
- merge theo từng attribute với semantics rõ ràng;
- khóa theo session ID với timeout/lease và cơ chế phục hồi;
- chấp nhận last-write-wins cho các thuộc tính không quan trọng và tài liệu hóa giới hạn.

Không giả định việc dùng Redis hoặc database tự động giải quyết lost update. Một lệnh upsert cuối cùng vẫn có thể ghi đè snapshot cũ nếu không có version/condition. Cũng không dùng session làm nơi giữ số dư hoặc tồn kho cần atomicity; dữ liệu nghiệp vụ cần transaction và constraint riêng.

## 14. Serialization và tương thích khi triển khai phiên bản mới

Session attributes có thể chứa object của ứng dụng. Nếu custom repository serialize trực tiếp Java object, rolling deployment có thể tạo dữ liệu mà node phiên bản cũ không đọc được. Một thay đổi class name, field type hoặc serialVersionUID có thể làm khôi phục session thất bại.

Thiết kế format lưu trữ có version:

- dùng kiểu dữ liệu ổn định hoặc schema serialization rõ ràng;
- tránh lưu object phức tạp nếu chỉ cần ID tham chiếu;
- hỗ trợ đọc format hiện tại và format trước trong thời gian rolling deployment;
- định nghĩa cách migrate hoặc loại bỏ session cũ khi không tương thích;
- kiểm thử deserialize fixture được tạo từ phiên bản ứng dụng trước;
- không deserialize dữ liệu tùy ý từ nguồn không tin cậy.

Nếu chỉ cần thay serializer trong Redis repository, ưu tiên cấu hình serializer thay vì viết lại repository. Custom repository chỉ nên sở hữu serialization khi yêu cầu không thể đáp ứng ở extension point.

## 15. Sự kiện vòng đời và các thành phần phụ thuộc

Ứng dụng có thể phụ thuộc vào SessionCreatedEvent, SessionDeletedEvent hoặc SessionExpiredEvent để cập nhật metric, dọn dữ liệu phụ trợ hoặc đóng WebSocket. SessionRepository cơ bản không tự bảo đảm mọi backend custom sẽ phân phối event giống Redis/JDBC implementation.

Nếu ứng dụng cần event, hãy xác định:

- event nào được phát khi tạo, xóa chủ động hoặc hết hạn;
- event phát một lần hay có thể lặp;
- event được gửi trong process hay qua message bus tới mọi instance;
- event có thể đến trễ hoặc mất khi backend/network gián đoạn không;
- listener có idempotent và retry được không;
- cách đối chiếu event với trạng thái repository hiện tại.

Event không nên là nguồn duy nhất quyết định session có hợp lệ hay không. Request cần kiểm tra repository và expiration hiện tại. Event chủ yếu hỗ trợ dọn dẹp và thông báo cho các thành phần khác.

## 16. Phân biệt lỗi không tìm thấy và lỗi storage

Đây là ranh giới quan trọng:

| Kết quả | Ý nghĩa | Hành vi |
|---|---|---|
| Không có bản ghi | Session ID không tồn tại | Trả không có session theo hợp đồng |
| Session hết hạn | Session không còn hiệu lực | Không trả session; dọn theo chính sách |
| Backend timeout/unavailable | Không thể xác định trạng thái session | Phát lỗi hạ tầng; không giả thành session missing |
| Serialization failure | Có dữ liệu nhưng không thể khôi phục | Ghi nhận lỗi, áp dụng chính sách fail-closed và xử lý dữ liệu lỗi |
| Version/schema mismatch | Node không hiểu format đang lưu | Áp dụng compatibility/migration policy |

Nếu backend unavailable mà repository trả null, ứng dụng có thể tạo session mới hoặc coi người dùng là anonymous trong khi thực tế kho đang gặp sự cố. Điều đó che giấu lỗi và có thể dẫn đến hành vi bảo mật không nhất quán. Phân loại exception rõ ràng và để filter/error handling xử lý phù hợp.

## 17. Bảo mật của custom repository

Repository custom trở thành một phần của vùng tin cậy bảo mật:

- tạo ID đủ ngẫu nhiên, không đoán được;
- bảo vệ dữ liệu khi truyền và khi lưu;
- giới hạn quyền đọc/ghi/xóa theo nguyên tắc tối thiểu;
- mã hóa thuộc tính nhạy cảm nếu yêu cầu;
- không ghi session ID, cookie hoặc SecurityContext vào log;
- xác thực expiration trước khi trả session;
- bảo đảm ID cũ không còn dùng được sau delete/rotation;
- bảo vệ backup và công cụ quản trị;
- tránh deserialize payload tùy ý;
- kiểm thử tenant isolation nếu dữ liệu được phân vùng.

Nếu một người dùng có thể đoán ID của tenant khác hoặc truy cập namespace không đúng, repository có thể trở thành đường vượt quyền. Không dựa vào controller authorization để bù cho việc phân vùng storage sai.

## 18. Kiểm thử hợp đồng trước khi triển khai

Tạo contract test dùng chung cho mọi repository implementation. Bộ test tối thiểu:

| Nhóm | Kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| Create | Tạo session mới | ID duy nhất, metadata ban đầu hợp lệ |
| Save/find | Lưu rồi đọc lại theo ID | Attributes và metadata được giữ nguyên |
| Update | Sửa attribute và last access time | Lần đọc sau nhận đúng giá trị mới |
| Delete | Xóa session | findById sau đó không trả session |
| Expiration | Đọc session sau timeout | Không trả session đã hết hạn |
| TTL | Gia hạn session | Backend TTL/expiry khớp chính sách |
| ID rotation | Đổi ID | ID cũ không khôi phục session mới |
| Attributes | Lưu nhiều kiểu dữ liệu hỗ trợ | Serialize/deserialize đúng |
| Corrupt data | Đọc payload lỗi | Lỗi được phân loại, không trả dữ liệu giả |
| Concurrent writes | Hai request cập nhật cùng session | Conflict/merge theo semantics đã chọn |
| Index | Tìm theo principal nếu hỗ trợ | Index đúng và được dọn khi xóa |
| Events | Tạo/xóa/hết hạn | Event đúng semantics và listener idempotent |
| Multi-instance | Ghi ở A, đọc ở B | Cùng dữ liệu và trạng thái thu hồi |
| Backend outage | Ngắt kho dữ liệu | Phát lỗi hạ tầng, không giả thành missing |
| Rolling version | Node cũ/mới cùng đọc session | Format tương thích hoặc migration được kiểm soát |

Mock storage chỉ phù hợp cho unit test logic mapping. Để chứng minh TTL, consistency, transaction, failover và multi-instance, chạy integration test với backend thật hoặc môi trường test cùng loại với production.

## 19. Đo chi phí bảo trì trước khi chấp nhận

Một custom repository cần có chủ sở hữu lâu dài. Ước lượng các công việc:

- nâng cấp theo mỗi major/minor Spring Session và Spring Framework;
- kiểm tra thay đổi contract/API và compatibility;
- vận hành backend, connection pool, TTL và cleanup;
- migration schema/serialization;
- xử lý failover, backup/restore và disaster recovery;
- giám sát metric, log, alert và event delivery;
- kiểm thử tải, race condition và rolling deployment;
- hỗ trợ sự cố người dùng bị logout hoặc session không khôi phục.

Nếu không có đội ngũ sở hữu các nhiệm vụ này, custom repository có thể trở thành thành phần hạ tầng không ai hiểu rõ. Chi phí bảo trì nhiều năm thường lớn hơn thời gian viết vài phương thức CRUD ban đầu.

## 20. Quy trình ra quyết định

~~~mermaid
flowchart TD
    A[Yêu cầu session mới] --> B{Redis/JDBC hoặc store có sẵn đáp ứng?}
    B -->|Có| C[Dùng repository có sẵn]
    B -->|Chưa rõ| D[Benchmark và kiểm tra cấu hình]
    D --> B
    B -->|Không| E{Customizer, serializer, index resolver hoặc decorator đủ?}
    E -->|Có| F[Dùng extension point hẹp]
    E -->|Không| G{Có yêu cầu bắt buộc và owner vận hành?}
    G -->|Không| H[Điều chỉnh yêu cầu hoặc kiến trúc]
    G -->|Có| I[Thiết kế custom repository và contract test]
    I --> J[Kiểm thử tải, lỗi, concurrency và multi-instance]
    J --> K[Triển khai canary và runbook]
~~~

Trình tự khuyến nghị:

1. Ghi rõ yêu cầu không được đáp ứng và cách đo.
2. Kiểm tra cấu hình repository có sẵn.
3. Thử customizer, serializer, index resolver hoặc decorator.
4. Đánh giá backend, consistency, TTL, security và chi phí.
5. Xác định owner và kế hoạch nâng cấp/bảo trì.
6. Viết contract test trước khi hoàn thiện implementation.
7. Kiểm thử failure, concurrency, multi-instance và rolling deployment.
8. Triển khai canary, theo dõi metric và có rollback plan.
9. Tài liệu hóa semantics và giới hạn cho các nhóm sử dụng.

## 21. Checklist trước khi tự xây

- [ ] Có yêu cầu cụ thể mà Redis/JDBC hoặc repository có sẵn không đáp ứng.
- [ ] Đã thử các cấu hình và extension point nhẹ hơn.
- [ ] Đã xác định Servlet hay WebFlux và chọn đúng repository contract.
- [ ] Đã định nghĩa semantics create, find, save, delete, expiry và ID rotation.
- [ ] Đã quyết định cách xử lý concurrent update/lost update.
- [ ] Đã xác định serialization format và version compatibility.
- [ ] Đã xác định có cần principal index và session events hay không.
- [ ] Đã phân biệt session missing với backend unavailable.
- [ ] Đã có security model, TTL, backup và multi-tenant isolation.
- [ ] Có contract tests chạy trên backend thật.
- [ ] Có benchmark, failure test và multi-instance test.
- [ ] Có owner, dashboard, alert, runbook và kế hoạch nâng cấp.

Tự xây repository là quyết định sở hữu một phần hạ tầng session, không chỉ là thay một lớp truy cập dữ liệu. Hãy dùng implementation Redis/JDBC khi chúng đáp ứng yêu cầu; dùng customizer, serializer, index resolver hoặc decorator khi chỉ cần thay đổi hẹp. Chỉ triển khai repository riêng khi có yêu cầu bắt buộc, hợp đồng được định nghĩa rõ, và đội ngũ có thể kiểm thử cũng như vận hành đầy đủ expiration, concurrency, security, events và compatibility lâu dài.
