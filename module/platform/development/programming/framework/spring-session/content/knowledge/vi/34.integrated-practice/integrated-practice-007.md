# Thay Redis bằng JDBC và kiểm chứng khác biệt về cleanup, sự kiện

Spring Session cho phép ứng dụng Servlet tiếp tục dùng HttpSession trong khi trạng thái phiên được lưu ở một kho dùng chung. Redis và JDBC đều có thể đáp ứng yêu cầu chia sẻ session giữa nhiều application instance, nhưng cách lưu trữ, hết hạn, dọn dữ liệu và phát sự kiện vòng đời khác nhau. Chuyển từ Redis sang JDBC vì vậy không chỉ là đổi một dependency hoặc một URL kết nối. Cần xác nhận schema, serialization, transaction, cleanup, event semantics, hiệu năng và cách xử lý các session đang tồn tại.

Bài thực hành này xây dựng một quy trình thay backend Redis bằng JDBC và kiểm chứng sự khác biệt có ý nghĩa trong vận hành. Trọng tâm là hiểu session hết hạn logic, thời điểm dữ liệu bị xóa vật lý, cách Redis dùng TTL/keyspace notifications, cách JDBC dùng EXPIRY_TIME và cleanup task, cùng những khác biệt về SessionExpiredEvent và SessionDeletedEvent. Kết quả cần là một ứng dụng dùng đúng một repository, một bộ kiểm thử chạy được với cả hai backend và một quyết định chuyển đổi rõ ràng đối với session cũ.

## 1. Mục tiêu và phạm vi

Sau bài thực hành, người học cần có khả năng:

- thay cấu hình Spring Session Redis bằng Spring Session JDBC trong ứng dụng Servlet;
- bảo đảm application nodes cùng dùng một database/schema và một session repository;
- tạo, lưu, khôi phục, gia hạn, invalidate và hết hạn session qua request thật;
- phân biệt expiration logic với cleanup vật lý;
- kiểm chứng lịch cleanup JDBC và TTL/expiration behavior của Redis;
- quan sát event tạo, xóa chủ động và hết hạn mà không giả định hai backend phát event giống nhau;
- đo tác động lên database, Redis, latency và dung lượng;
- quyết định giữ, migrate hay vô hiệu hóa session đang có khi chuyển backend.

Phạm vi giả định là Spring Boot Servlet application dùng Spring Session. Nếu ứng dụng dùng WebFlux, cần thay API/filter model bằng WebSession và ReactiveSessionRepository; không trộn cấu hình Servlet với reactive session manager.

## 2. Kiến trúc trước và sau khi thay backend

Trước khi thay, request đi qua SessionRepositoryFilter và repository Redis:

~~~mermaid
flowchart LR
    C[Browser / HTTP client] --> F[SessionRepositoryFilter]
    F --> A[Spring MVC application]
    F --> R[Spring Session Redis repository]
    R --> X[(Redis shared store)]
    A --> F
~~~

Sau khi thay, application flow vẫn giữ HttpSession và filter, nhưng repository dùng JDBC:

~~~mermaid
flowchart LR
    C[Browser / HTTP client] --> F[SessionRepositoryFilter]
    F --> A[Spring MVC application]
    F --> J[Spring Session JDBC repository]
    J --> D[(Relational database)]
    A --> F
~~~

Phần controller và service thông thường không cần biết session đang nằm trong Redis hay JDBC. Thay đổi chủ yếu nằm ở dependency, auto-configuration, connection factory/DataSource, schema và vận hành. Tuy nhiên, không nên suy ra rằng dữ liệu session đã lưu trong Redis tự động xuất hiện trong JDBC. Hai backend có format, key/schema và lifecycle riêng.

## 3. Kiểm kê cấu hình Redis hiện tại

Trước khi thay, ghi nhận cấu hình đang có:

- Spring Boot và Spring Session version;
- dependency Redis session;
- Redis host/cluster, database index, TLS/ACL và namespace;
- serializer dùng cho session attributes;
- flush mode/save mode;
- timeout mặc định và timeout tùy chỉnh theo session;
- cách cấu hình keyspace notifications;
- listener đang phụ thuộc vào SessionCreatedEvent, SessionDeletedEvent hoặc SessionExpiredEvent;
- metric, alert và dashboard đang lấy số liệu từ Redis;
- số lượng session, kích thước dữ liệu và lưu lượng đọc/ghi.

Tìm các nơi dùng Redis trực tiếp thay vì qua HttpSession. Nếu ứng dụng tự đọc key Spring Session hoặc phụ thuộc vào tên key nội bộ, các phần đó có thể hỏng khi đổi sang JDBC. Chỉ dùng API công khai của Spring Session ở tầng ứng dụng; không coi cấu trúc key Redis là hợp đồng nghiệp vụ.

Lập danh sách listener và side effect. Ví dụ, listener SessionExpiredEvent có thể đang đóng WebSocket, xóa dữ liệu phụ hoặc cập nhật metric. Nếu JDBC không phát event theo cùng cách hoặc phát vào thời điểm khác, hành vi này cần được thiết kế lại thay vì chỉ đổi backend.

## 4. Dependency cho JDBC

Ứng dụng cần module Spring Session JDBC và JDBC driver của database. Với Maven, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Version của Spring Session nên được quản lý bởi Spring Boot dependency management hoặc BOM tương ứng. Không ghép tùy tiện Spring Session version khác với Spring Framework/Boot version.

Nếu dự án đang dùng Redis session, gỡ module Redis session khỏi runtime path khi chuyển hẳn sang JDBC. Có thể vẫn giữ Redis cho cache hoặc messaging nếu ứng dụng còn dùng, nhưng không để hai cấu hình session repository cùng hoạt động. Nếu cả Redis và JDBC session dependencies cùng có trên classpath, chọn rõ backend qua property/auto-configuration của phiên bản Spring Boot đang dùng hoặc cấu hình repository tường minh.

Không nhầm spring-session-jdbc với chỉ riêng spring-boot-starter-jdbc. Starter JDBC cung cấp DataSource/JdbcTemplate; module spring-session-jdbc cung cấp repository session.

## 5. Cấu hình DataSource và Spring Session JDBC

Ví dụ cấu hình application:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/app
    username: app_session
    password: session_test_only
  session:
    store-type: jdbc
    timeout: 30m
    jdbc:
      initialize-schema: never
      cleanup-cron: "0 * * * * *"
~~~

Trong môi trường production, schema nên được quản lý bằng migration đã review. Vì vậy ví dụ đặt initialize-schema là never. Khi phát triển hoặc integration test với database tạm, có thể dùng always nếu phù hợp. Hãy kiểm tra property name và khả năng auto-configuration theo Spring Boot version của dự án.

Property store-type giúp chọn JDBC khi classpath có nhiều implementation. Nếu dùng cấu hình tường minh bằng @EnableJdbcHttpSession, kiểm tra rằng auto-configuration khác không tạo thêm một repository hoặc filter thứ hai. Ứng dụng chỉ nên có một cơ chế quản lý HttpSession.

Timeout mặc định có thể đặt ở cấu hình Spring Session. Session riêng có thể có max inactive interval khác nếu ứng dụng chủ động thay đổi. Không giả định mọi session luôn dùng cùng timeout nếu code có logic tùy chỉnh.

## 6. Schema JDBC và migration

Spring Session JDBC mặc định sử dụng hai bảng chính:

- SPRING_SESSION lưu ID, creation time, last access time, max inactive interval, EXPIRY_TIME và principal name/index data.
- SPRING_SESSION_ATTRIBUTES lưu các session attributes đã serialize.

Schema cụ thể phụ thuộc database. Spring Session cung cấp schema script theo nền tảng; nếu dùng Flyway/Liquibase, đưa schema tương ứng vào migration và kiểm soát phiên bản.

Các điểm cần kiểm tra:

- primary key và độ dài session ID;
- cột EXPIRY_TIME và đơn vị epoch milliseconds;
- index hỗ trợ truy vấn theo expiration;
- index principal nếu ứng dụng dùng tìm session theo principal;
- foreign key giữa session và attributes;
- cascade delete hoặc quy trình dọn attributes tương ứng;
- quyền SELECT, INSERT, UPDATE và DELETE của tài khoản runtime;
- quyền migration được tách khỏi tài khoản runtime nếu chính sách yêu cầu.

Không tự sửa tên cột hoặc kiểu dữ liệu để giống bảng nghiệp vụ. Nếu đổi table name hoặc schema, cấu hình repository tương ứng và cập nhật migration, query giám sát, cleanup và runbook.

## 7. Chọn đúng một repository

Với Spring Boot, có thể chọn store type JDBC bằng property được hỗ trợ ở phiên bản đang dùng. Một cách khác là cấu hình @EnableJdbcHttpSession và cung cấp DataSource. Tránh cùng lúc kích hoạt cấu hình Redis session và JDBC session.

Ví dụ cấu hình tường minh ở mức khái niệm:

~~~java
@Configuration
@EnableJdbcHttpSession
class JdbcSessionConfiguration {
}
~~~

Nếu ứng dụng có nhiều DataSource, phải xác định DataSource nào được Spring Session sử dụng. Dùng qualifier/primary hoặc cấu hình repository phù hợp để không vô tình lưu session vào database nghiệp vụ khác. Cần xem xét transaction manager mà JDBC repository dùng và không giả định session save luôn nằm trong cùng transaction với business service.

Sau khi khởi động, kiểm tra ApplicationContext chỉ có repository/filter mong muốn. Một cấu hình sai có thể khiến ứng dụng khởi động được nhưng request đọc session từ backend khác với backend mà bạn đang quan sát.

## 8. Redis và JDBC khác nhau thế nào khi lưu session?

| Khía cạnh | Redis repository | JDBC repository |
|---|---|---|
| Dữ liệu chính | Redis keys/hash và metadata phụ | SPRING_SESSION và SPRING_SESSION_ATTRIBUTES |
| Expiration | TTL và các key phục vụ expiration | EXPIRY_TIME trong bản ghi |
| Dọn vật lý | Redis expiration và xử lý key/index liên quan | Cleanup task xóa các hàng hết hạn |
| Truy vấn theo principal | Indexed repository và Redis index | Principal index trong schema JDBC |
| Serialization | Serializer cấu hình cho Redis session attributes | Cơ chế serialize attributes của JDBC repository |
| Transaction | Phụ thuộc Redis operations và cấu hình repository | Dựa vào JDBC/DataSource và transaction behavior của repository |
| Quan sát | Redis memory, keyspace, TTL, replication | Table/index size, query, lock, WAL/transaction log |
| Event hết hạn | Có thể dựa vào keyspace expiration notifications | Cleanup theo lịch; event semantics cần xác minh theo implementation/version |

Không chọn JDBC chỉ vì database có sẵn. Session tạo nhiều thao tác đọc/ghi ngắn; database nghiệp vụ có thể bị ảnh hưởng bởi connection pool, index, transaction log và cleanup. Ngược lại, Redis có thể phù hợp hơn về latency nhưng cần vận hành memory, persistence, replication và keyspace notifications.

## 9. Hết hạn logic của session

Spring Session dùng thời điểm truy cập gần nhất và max inactive interval để xác định session hết hạn. Nếu khoảng không hoạt động vượt giới hạn, session không còn hợp lệ dù dữ liệu vật lý chưa được xóa.

Repository phải kiểm tra expiration khi tìm session. Điều này đặc biệt quan trọng với JDBC: hàng trong SPRING_SESSION có thể còn tồn tại cho đến lần cleanup định kỳ tiếp theo, nhưng findById không được trả session đã hết hạn như phiên hợp lệ.

Ví dụ:

- Session được truy cập lúc 10:00.
- Max inactive interval là 30 phút.
- Session hết hạn logic sau mốc 10:30 nếu không được gia hạn.
- Cleanup job JDBC chạy mỗi phút có thể xóa hàng ở lần chạy sau đó.

Thời điểm xóa vật lý không phải thời điểm session bắt đầu mất hiệu lực. Test cần xác minh hai mốc riêng.

## 10. Cleanup trong Spring Session JDBC

JdbcIndexedSessionRepository cung cấp cleanup task để xóa session hết hạn khỏi database. Trong cấu hình phổ biến, lịch mặc định chạy mỗi phút; có thể điều chỉnh bằng cleanupCron ở annotation hoặc property Spring Boot tương ứng, ví dụ spring.session.jdbc.cleanup-cron.

Cleanup query dựa trên EXPIRY_TIME và xóa các session đã hết hạn. Với schema chuẩn, foreign key cascade giúp dọn attributes liên quan. Hãy xác minh schema thực tế có giữ quan hệ này; nếu schema tùy chỉnh bỏ cascade, cần kiểm tra và dọn dữ liệu phụ đúng thứ tự.

Ví dụ thay đổi lịch:

~~~yaml
spring:
  session:
    jdbc:
      cleanup-cron: "0 */2 * * * *"
~~~

Ví dụ này chạy cleanup theo chu kỳ hai phút. Chọn lịch dựa trên lượng session hết hạn, chi phí DELETE, lock, transaction log/WAL và yêu cầu dung lượng. Lịch dày làm backlog giảm nhanh hơn nhưng tăng tải database. Lịch thưa giảm số lần chạy nhưng bản ghi hết hạn tồn tại vật lý lâu hơn.

Trong cụm nhiều instance, không mặc định mỗi node đều phải chạy cleanup độc lập. Kiểm tra cơ chế scheduling và cấu hình repository của phiên bản đang dùng; nếu nhiều node cùng chạy, database vẫn phải chịu các lần DELETE cạnh tranh. Có thể tách cleanup thành một tác vụ vận hành riêng nếu cần kiểm soát rõ.

## 11. Expiration và cleanup trong Spring Session Redis

Redis repository thường dùng TTL để quản lý expiration. Redis có thể xóa key khi TTL hết hạn, nhưng thời điểm xóa vật lý có thể trễ so với thời điểm logic. Spring Session Redis có thể dùng expiration keys và keyspace notifications để phát hiện session hết hạn, phát event và dọn các cấu trúc phụ.

Redis keyspace notifications được cấu hình ở Redis server. Một số môi trường cho phép ứng dụng yêu cầu cấu hình notification; managed Redis có thể chặn lệnh CONFIG hoặc yêu cầu người vận hành cấu hình trước. Hãy kiểm tra chính sách của Redis deployment và Spring Session version.

Redis expiration event dùng cơ chế notification/pub-sub, không phải một hàng đợi bền vững bảo đảm giao đúng một lần. Subscriber ngắt kết nối có thể bỏ lỡ notification. Vì vậy, không nên xem một bộ đếm event Redis là sổ kiểm toán tuyệt đối cho mọi session đã hết hạn.

Redis và JDBC có thể đạt cùng kết quả logic: session hết hạn không được khôi phục. Nhưng cách dọn dữ liệu vật lý và thời điểm phát hiện expiration khác nhau. Đó là điều cần thể hiện trong test và dashboard.

## 12. Sự kiện tạo, xóa và hết hạn

Spring Session có các event vòng đời như SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent. Cách event được phát phụ thuộc repository implementation và backend.

Một số điểm cần phân biệt:

- Tạo session là một hành vi khác với lưu thành công bền vững.
- Logout/invalidate là xóa chủ động.
- Expiration là hết hạn theo timeout.
- Cleanup job xóa các bản ghi hết hạn là thao tác dọn vật lý.
- Redis keyspace notification có thể đến khi key hết hạn vật lý.

JDBC cleanup task không nên được hiểu như một event bus phát một event cho mỗi hàng đã xóa. Việc cleanup xóa hàng không tự động chứng minh ứng dụng đã nhận một SessionExpiredEvent cho từng session. Tương tự, không giả định event từ Redis và JDBC có cùng thời điểm, cùng độ tin cậy hoặc cùng phạm vi phân phối.

Nếu ứng dụng cần đóng WebSocket, thu hồi token phụ hoặc dọn dữ liệu nghiệp vụ khi session hết hạn, phải thiết kế cơ chế riêng có tính idempotent và bền vững. Không phụ thuộc duy nhất vào event expiration có thể bị mất hoặc đến trễ. Request cần kiểm tra trạng thái session hiện tại; event hỗ trợ cleanup và thông báo.

## 13. Listener để quan sát event

Ví dụ listener:

~~~java
@Component
class SessionEvents {

    @EventListener
    void onCreated(SessionCreatedEvent event) {
        // Tăng counter tạo session.
    }

    @EventListener
    void onDeleted(SessionDeletedEvent event) {
        // Ghi nhận thao tác xóa chủ động nếu event được phát.
    }

    @EventListener
    void onExpired(SessionExpiredEvent event) {
        // Ghi nhận expiration notification nếu backend hỗ trợ.
    }
}
~~~

Listener cần an toàn khi event lặp hoặc đến trễ. Không thực hiện công việc nặng đồng bộ trên thread phát event. Nếu phải gọi dịch vụ khác, đẩy một message có ID nghiệp vụ hoặc event ID vào cơ chế bền vững và để consumer xử lý idempotent.

Không log session ID, cookie hoặc toàn bộ attributes. Nếu cần trace một sự kiện trong test, dùng một session ID giả lập không nhạy cảm và chỉ trong môi trường kiểm thử.

## 14. Kế hoạch kiểm thử dùng chung cho hai backend

Tạo một bộ contract test có thể chạy hai lần:

- Profile Redis dùng Redis container.
- Profile JDBC dùng PostgreSQL container.

Các test nghiệp vụ giống nhau:

1. Tạo session qua request.
2. Lấy cookie session.
3. Gửi request tiếp theo và khôi phục attribute.
4. Cập nhật attribute và xác nhận lần đọc sau thấy giá trị mới.
5. Logout/invalidate.
6. Replay cookie cũ và xác nhận session không còn hợp lệ.
7. Kiểm tra timeout logic.
8. Kiểm tra session được chia sẻ giữa hai application context nếu triển khai nhiều instance.

Các test backend-specific:

- JDBC: schema, EXPIRY_TIME, cleanup cron, foreign key cascade, query plan và số hàng được cleanup.
- Redis: TTL, expiration key, namespace, keyspace notification, principal index và behavior khi subscriber mất kết nối.

Không ép hai backend phải có cùng chi tiết nội bộ. Contract chung là hành vi session mà ứng dụng yêu cầu; test backend-specific kiểm tra cách mỗi implementation đạt contract đó.

## 15. Dùng Testcontainers cho PostgreSQL

Ví dụ khai báo PostgreSQL container:

~~~java
@Testcontainers
@SpringBootTest
class JdbcSessionTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

}
~~~

Với Spring Boot hỗ trợ ServiceConnection, cần dependency spring-boot-testcontainers. Nếu không dùng được ServiceConnection, đăng ký spring.datasource.url, username và password bằng @DynamicPropertySource từ container. Không hard-code port 5432 của host.

Schema có thể được tạo bởi Spring Session trong test bằng initialize-schema=always hoặc bằng migration riêng. Chọn một cơ chế, không để hai cơ chế cạnh tranh.

## 16. Dùng Testcontainers cho Redis

Ví dụ Redis container:

~~~java
@Testcontainers
@SpringBootTest
class RedisSessionTests {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
        registry.add("spring.session.redis.namespace",
                () -> "test:spring-session");
    }
}
~~~

Property prefix tùy Spring Boot version; kiểm tra cấu hình thực tế. Nếu test event expiration, container phải bật keyspace notifications phù hợp. Có thể cấu hình command khi khởi động hoặc dùng file cấu hình test riêng. Đừng giả định Redis image mặc định đã bật mọi notification mà Spring Session cần.

## 17. Kiểm thử JDBC cleanup

Để kiểm tra cleanup:

1. Tạo session với max inactive interval ngắn.
2. Xác nhận hàng session xuất hiện trong SPRING_SESSION.
3. Đợi qua thời điểm EXPIRY_TIME bằng polling có deadline.
4. Gọi repository findById và xác nhận session không còn hợp lệ.
5. Chờ cleanup task chạy hoặc gọi cơ chế cleanup trong test theo API được hỗ trợ.
6. Xác nhận hàng session đã bị xóa.
7. Nếu schema dùng cascade, xác nhận attributes liên quan cũng đã được dọn.

Tránh chỉ dùng Thread.sleep() cố định. Dùng Awaitility hoặc polling assertion với deadline để chờ trạng thái. Test cần tách:

- expiry logic: repository từ chối session sau timeout;
- physical cleanup: hàng dữ liệu bị xóa khỏi database.

Nếu cleanup cron mặc định một phút, test không nên chờ quá lâu cho mỗi method. Trong profile test, có thể đặt lịch ngắn hơn, hoặc gọi phương thức cleanup công khai nếu phiên bản repository cho phép. Không phụ thuộc API nội bộ không ổn định mà không ghi rõ version.

## 18. Kiểm thử Redis expiration

Với Redis, test nên:

1. Tạo session có timeout ngắn.
2. Xác nhận key/session metadata tồn tại.
3. Kiểm tra TTL của key chính và expiration key theo cấu trúc repository/version.
4. Đợi TTL hết và quan sát trạng thái session qua repository.
5. Nếu test event, đăng ký listener trước khi hết hạn.
6. Xác nhận event nhận được trong giới hạn thời gian test.
7. Ngắt subscriber có chủ đích trong một test riêng để chứng minh notification có thể bị bỏ lỡ.
8. Kiểm tra index phụ được xử lý theo behavior của implementation.

Không dùng lệnh KEYS rộng hoặc FLUSHALL trong test suite dùng chung Redis. Namespace test riêng và cleanup theo namespace. Khi kiểm tra TTL nội bộ, pin phiên bản Spring Session vì key layout là chi tiết implementation.

## 19. Kiểm chứng khác biệt event

Viết một listener test thu thập loại event, không lưu session ID thật:

~~~java
class RecordingSessionEvents {

    private final BlockingQueue<String> events =
            new LinkedBlockingQueue<>();

    @EventListener
    void created(SessionCreatedEvent event) {
        events.add("created");
    }

    @EventListener
    void deleted(SessionDeletedEvent event) {
        events.add("deleted");
    }

    @EventListener
    void expired(SessionExpiredEvent event) {
        events.add("expired");
    }

    String awaitEvent(Duration timeout) throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Test explicit invalidate và timeout thành hai trường hợp riêng. Không dùng cùng một assertion cho Redis và JDBC kiểu “mỗi session hết hạn luôn phát đúng một SessionExpiredEvent”. Trước hết, xác minh event semantics của phiên bản repository cụ thể; sau đó viết assertion theo contract thực tế.

Nếu yêu cầu nghiệp vụ cần nhận biết mọi session hết hạn một cách bền vững, cân nhắc một expiration registry/outbox hoặc job reconciliation riêng. Không biến Spring Session event thành cơ chế duy nhất để kích hoạt nghiệp vụ không thể mất event.

## 20. So sánh kết quả cleanup

| Kiểm tra | Redis | JDBC |
|---|---|---|
| Thời điểm hết hạn logic | Theo session timeout | Theo EXPIRY_TIME và timeout |
| Xóa key/hàng vật lý | TTL/expiration behavior của Redis | Scheduled cleanup task |
| Có thể trễ so với logic expiry | Có | Có, theo lịch cleanup |
| Theo dõi backlog | Key/index theo namespace và metric backend | Hàng EXPIRY_TIME đã qua hạn |
| Sự kiện expiration | Thường liên quan keyspace notifications | Không suy ra từ cleanup SQL; xác minh event behavior theo version |
| Tác động tải | Redis CPU, memory, replication, notification | SQL DELETE, index, locks, WAL/transaction log |
| Kiểm thử chính | TTL, notification, index cleanup | EXPIRY_TIME, cleanup cron, cascade |

Đừng so sánh số key Redis với số hàng JDBC một cách trực tiếp. Redis có thể có nhiều key phụ cho một session; JDBC có hàng attributes riêng. So sánh số session logic hoặc kết quả qua repository API, không so sánh số entry vật lý nếu chưa chuẩn hóa.

## 21. Sự kiện xóa chủ động và logout

Logout thường gọi invalidate session, dẫn tới deleteById hoặc thao tác tương ứng. Đây khác expiration theo timeout. Test riêng:

- logout thành công: session ID cũ không khôi phục được;
- delete event: listener nhận sự kiện nếu implementation phát;
- cleanup: không nên cần chờ cleanup expiration để logout có hiệu lực;
- multi-instance: node khác cũng phải từ chối ID đã invalidate;
- backend outage: nếu delete không hoàn tất, không được coi cookie bị xóa ở browser là bằng chứng session đã thu hồi.

Redis và JDBC đều phải đáp ứng contract invalidate ở repository. Event cụ thể và cơ chế phân phối event cần được kiểm tra riêng.

## 22. Chuyển đổi session đang tồn tại

Khi đổi backend từ Redis sang JDBC, cookie có thể vẫn mang cùng session ID nhưng JDBC không có bản ghi tương ứng. Request tiếp theo vì vậy sẽ được coi là không có session và người dùng phải xác thực lại.

Không có cơ chế tự động mặc định chuyển toàn bộ session đang sống từ Redis sang JDBC chỉ bằng cách đổi property. Không copy Redis key trực tiếp thành hàng SQL; schema, metadata, index, expiry và serialized attributes khác nhau.

Các lựa chọn:

| Chiến lược | Khi phù hợp | Hạn chế |
|---|---|---|
| Invalidate toàn bộ session và yêu cầu login lại | Chuyển đổi đơn giản, chấp nhận đăng nhập lại | Gián đoạn người dùng và login burst |
| Chuyển theo batch bằng công cụ riêng | Cần giữ một phần session và có thể kiểm soát format | Phải hiểu serialization, metadata, expiry, principal index và consistency |
| Dual read/write tạm thời | Hệ thống rất lớn có yêu cầu chuyển đổi không gián đoạn | Phức tạp, dễ split-brain và phải có kế hoạch kết thúc |

Nếu migrate session bằng công cụ riêng, cần dừng hoặc đồng bộ ghi trong thời gian snapshot, ánh xạ mọi metadata, bỏ session đã hết hạn, không khôi phục session đã bị revoke, kiểm tra attributes, rồi mới chuyển traffic. Phải có rollback plan. Với đa số ứng dụng, thông báo đăng nhập lại và tạo session mới là phương án ít rủi ro hơn.

## 23. Triển khai chuyển backend an toàn

Một kế hoạch triển khai thực tế:

1. Đo baseline Redis: active session ước lượng, creation rate, latency, memory và lỗi.
2. Chuẩn bị JDBC schema/migration và quyền runtime.
3. Cấu hình một môi trường test/staging dùng JDBC.
4. Chạy contract tests và backend-specific cleanup/event tests.
5. Đo query latency, connection pool, table/index growth và cleanup cost.
6. Quyết định cách xử lý session cũ: invalidate, migrate có kiểm soát hoặc dual operation.
7. Triển khai cấu hình JDBC cho canary hoặc maintenance window.
8. Xác nhận login mới, session round-trip, logout, expiry và nhiều instance.
9. Theo dõi login failures, creation rate, database load và cleanup backlog.
10. Mở traffic toàn bộ và giữ Redis session data trong thời hạn rollback được phê duyệt, nếu chính sách cho phép.
11. Khi kết thúc rollback window, dọn dữ liệu Redis session cũ theo namespace được xác nhận.

Không để ứng dụng một phần dùng Redis và một phần dùng JDBC mà không có cơ chế routing/consistency rõ ràng. Nếu các node cùng phục vụ một cookie nhưng mỗi node dùng repository khác nhau, người dùng sẽ có hành vi đăng nhập/đăng xuất không ổn định theo node.

## 24. Đánh giá hiệu năng và chi phí vận hành

Redis thường có latency thấp cho thao tác key/value nhưng cần quản lý memory, eviction, replication, persistence và notification. JDBC tận dụng database quan hệ và backup/monitoring sẵn có, nhưng session workload có thể tăng số lượng transaction ngắn, index updates, row locks, WAL và cleanup DELETE.

Đo ít nhất:

- p50/p95/p99 latency của find/save/delete;
- số request repository mỗi giây;
- pool active/idle/wait và connection acquisition time;
- database CPU, IOPS, lock wait, deadlock và transaction log;
- số hàng SPRING_SESSION và SPRING_SESSION_ATTRIBUTES;
- expired backlog và số hàng cleanup mỗi lần;
- Redis memory, evictions, replication lag và expiration processing;
- lỗi serialization và timeout.

Không kết luận JDBC chậm hơn hoặc nhanh hơn Redis chỉ từ benchmark local. Payload, database topology, network, connection pool, index, transaction isolation và tải cạnh tranh đều ảnh hưởng.

## 25. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Login xong request tiếp theo mất session | Node dùng repository khác hoặc JDBC schema chưa đúng | Kiểm tra cookie, store type, DataSource và round-trip |
| Ứng dụng khởi động nhưng bảng session không có | Schema initialization/migration chưa chạy | Kiểm tra migration và quyền |
| Session hết hạn nhưng hàng vẫn còn | Cleanup task chưa tới lịch hoặc bị lỗi | Kiểm tra EXPIRY_TIME, cron và log cleanup |
| JDBC cleanup tăng tải DB | Lịch quá dày hoặc backlog lớn | Đo DELETE, index, batch và lịch |
| SessionExpiredEvent không tới listener | Backend/version không phát theo semantics mong đợi hoặc notification thiếu | Kiểm tra implementation, Redis notification và test event |
| Event bị đếm trùng | Nhiều node nhận cùng notification | Xác định event delivery scope và deduplicate |
| Redis key count khác JDBC row count | Key phụ, attributes và schema khác nhau | So sánh session logic qua repository |
| Restore JDBC làm session cũ sống lại | Backup trước logout/revoke | Invalidate phạm vi hoặc kiểm tra credential/session version |
| Session attributes không deserialize | Format/class không tương thích | Dùng migration hoặc yêu cầu login lại |
| Một node đọc được, node khác không | Config, schema, serializer hoặc namespace khác nhau | So sánh cấu hình mọi instance |

## 26. Checklist nghiệm thu thay Redis bằng JDBC

- [ ] Đã ghi nhận cấu hình Redis hiện tại và các listener phụ thuộc.
- [ ] Dependency Spring Session JDBC và JDBC driver đúng version.
- [ ] Redis session repository không còn được kích hoạt đồng thời.
- [ ] Mọi application node dùng cùng DataSource, schema và table configuration.
- [ ] Schema SPRING_SESSION và SPRING_SESSION_ATTRIBUTES đúng, có index/foreign key cần thiết.
- [ ] Migration và quyền runtime được kiểm tra.
- [ ] Tạo, lưu, khôi phục, cập nhật và invalidate session thành công.
- [ ] Session hết hạn logic không được khôi phục.
- [ ] Cleanup JDBC xóa hàng hết hạn theo lịch đã chọn.
- [ ] Attributes liên quan được dọn đúng.
- [ ] Event created/deleted/expired được kiểm chứng theo implementation/version.
- [ ] Không phụ thuộc event expiration như message bền vững nếu nghiệp vụ không chịu được mất event.
- [ ] Multi-instance round-trip và revoke test đạt.
- [ ] Đã quyết định session cũ sẽ bị invalidate hay migrate.
- [ ] Đã đo latency, pool, database load và cleanup backlog.
- [ ] Có canary, rollback và thông báo login lại nếu cần.

## 27. Kết luận thực hành

Thay Redis bằng JDBC là thay đổi repository và mô hình vận hành session, không phải một phép đổi URL. Contract ứng dụng cần giữ nguyên: session được tạo, khôi phục, cập nhật, hết hạn và invalidate an toàn. Nhưng cleanup vật lý, TTL, event delivery và chi phí backend có thể khác nhau đáng kể.

Redis dựa vào TTL và cơ chế expiration/keyspace notification để xử lý trạng thái hết hạn và event liên quan. JDBC lưu EXPIRY_TIME trong bảng session và dùng cleanup task để xóa dữ liệu hết hạn theo lịch. Một bản ghi JDBC có thể còn trong bảng sau khi đã hết hạn logic; một Redis notification có thể đến trễ hoặc bị bỏ lỡ khi subscriber ngắt kết nối. Vì vậy, hãy kiểm tra trạng thái session qua repository, đo cleanup riêng và không dùng event làm nguồn duy nhất cho nghiệp vụ quan trọng.

Khi chuyển backend, không giả định session cũ tự di chuyển. Nếu không có một quy trình migration được thiết kế, kiểm thử và đối soát đầy đủ, invalidate session cũ và yêu cầu người dùng đăng nhập lại thường là lựa chọn an toàn, dễ vận hành hơn. Sau cùng, chỉ nghiệm thu khi mọi instance dùng cùng JDBC repository, session round-trip và revoke đúng, expiration/cleanup được quan sát, và hệ thống có runbook cho dữ liệu session còn tồn tại trong Redis cũ.

## Tài liệu tham khảo

- Spring Session – JDBC configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session – Redis configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session – HttpSession integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Session – API and session events: https://docs.spring.io/spring-session/reference/
- Redis – Keyspace notifications: https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/
- Spring Boot – Externalized configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
