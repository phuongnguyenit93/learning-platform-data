# Xử lý kết nối đang hoạt động khi thông tin cũ bị thu hồi

## 1. Bài toán xoay vòng credential trong ứng dụng

Trong module **SPRING_VAULT**, ứng dụng Java thường dùng `VaultTemplate` để đăng nhập HashiCorp Vault bằng danh tính workload, lấy **dynamic database credentials** và kết nối đến PostgreSQL, MySQL hoặc một dịch vụ khác. Vault có thể cấp username/password tạm thời kèm `lease_id` và TTL; ứng dụng cần sử dụng chúng, gia hạn hoặc thay thế khi lease sắp hết hạn.

Vấn đề xuất hiện khi **credential cũ bị thu hồi trong lúc ứng dụng vẫn có kết nối đang hoạt động**. Một connection pool có thể chứa hàng chục kết nối TCP đã được xác thực bằng username/password cũ. Nếu chỉ thay password trong một biến Java khi Vault cấp credential mới, các kết nối có sẵn không tự đăng nhập lại, giao dịch đang chạy có thể lỗi, và một số kết nối mới vẫn cố sử dụng credential cũ.

Ví dụ: dịch vụ Orders có HikariCP. Vault cấp tài khoản `v_orders_a` với lease `L1` và TTL 20 phút, sau đó cần đổi sang `v_orders_b` với lease `L2`. Cùng lúc:

- Request A đang thực hiện một giao dịch dùng connection của `v_orders_a`.
- Request B chuẩn bị lấy connection mới từ pool.
- Background job vừa nhận tín hiệu rotation từ Spring Vault.
- Vault hoặc DBA có thể revoke `v_orders_a` trước khi A hoàn thành.

Mục tiêu là **chuyển request mới sang credential mới, drain giao dịch cũ và xử lý revoke sớm**. Zero downtime cần phối hợp TTL, backend, pool và retry.

### Kết quả cần đạt

Sau bài học, bạn có thể phân biệt lease của Vault với trạng thái kết nối, xây dựng quy trình chuyển pool hai thế hệ, xử lý kết nối đang dùng và lỗi khi credential bị revoke, thiết kế cách dùng `SecretLeaseContainer` với `RequestedSecret.rotating(...)`, và kiểm thử khả năng phục hồi của ứng dụng Java.

## 2. Credential, lease, connection và transaction là bốn đối tượng khác nhau

| Đối tượng | Được quản lý bởi | Khi xoay vòng hoặc thu hồi |
| --- | --- | --- |
| **Vault login token** | Auth method, `LifecycleAwareSessionManager` | Có thể renew/re-login để tiếp tục gọi Vault API. Token mới không tự tạo database user mới. |
| **Dynamic secret lease** | Vault database secrets engine, `SecretLeaseContainer` | Có TTL, `lease_id`, trạng thái renewable; revoke có thể khiến DB user bị xóa hoặc mất quyền. |
| **JDBC connection** | Driver, database, HikariCP hoặc pool khác | Giữ session với DB đã xác thực trước đó. Thay password ở cấu hình không thay session hiện tại. |
| **Transaction / business request** | Ứng dụng, Spring transaction manager | Có thể đang giữ connection trong suốt transaction. Khi backend hủy session, transaction có thể rollback hoặc gặp lỗi giữa chừng. |

Login token còn hạn không chứng minh database credential còn hợp lệ: `VaultTemplate` có thể dùng token mới, còn connection đang mở vẫn mang danh tính DB cũ.

**Revoke phụ thuộc database và câu lệnh thu hồi.** Backend có thể chỉ chặn login mới hoặc làm hỏng session đang chạy. PostgreSQL có ràng buộc khi drop role còn session/đối tượng phụ thuộc. Phải kiểm thử đúng backend và cấu hình Vault; không suy đoán mọi TCP connection sẽ sống hoặc bị cắt ngay.

### Trường hợp khác với dynamic database credentials

- **KV v2 static secret:** có version và metadata; cập nhật giá trị trong Vault không tạo sự kiện thay connection pool tự động cho mọi ứng dụng. Nếu có password tĩnh do hệ thống khác đổi, cần cơ chế refresh riêng.
- **Transit encryption:** xoay khóa mã hóa Transit không đòi thay JDBC connection; ciphertext có thể gắn key version và chính sách decrypt riêng.
- **PKI certificate:** thay chứng thư trong keystore không tự đổi những TLS session đang mở; TLS client/server có cách nạp lại key material và đóng kết nối riêng.
- **Vault token / lease:** hết TTL login token có thể ảnh hưởng đến lease con tùy cấu trúc token; không được coi token renew hoặc re-login là một lần rotate credential của database.

## 3. Điều gì xảy ra khi credential cũ bị thu hồi?

Giả sử pool P1 dùng `user_a`, pool P2 dùng `user_b`. Có bốn loại connection cần xem xét:

| Trạng thái ở thời điểm revoke | Hệ quả có thể xảy ra | Ứng dụng cần làm |
| --- | --- | --- |
| **Idle** trong P1 | Kết nối vẫn mở nhưng có thể đã mất quyền, hoặc bị backend cắt. | Không cấp phát mới từ P1; đóng/evict kết nối cũ. |
| **Borrowed** từ P1, chưa bắt đầu SQL | SQL đầu tiên có thể thất bại do session bị hủy hoặc quyền bị thu hồi. | Phát hiện lỗi, rollback và chỉ retry khi an toàn. |
| **Transaction đang chạy** qua P1 | Một câu lệnh có thể lỗi giữa giao dịch; trạng thái commit cần được xác minh. | Đánh dấu transaction failed, rollback nếu có thể; không tự chuyển sang P2 giữa transaction. |
| **New checkout** sau khi đã publish P2 | Nếu router còn trỏ P1, request có thể dùng credential cũ. | Chuyển tuyến nguyên tử; mọi checkout mới phải chọn P2. |

Không cố “thay username/password” của một `Connection` đã mở. JDBC `Connection` thường gắn với session/authentication do server thiết lập lúc connect. Ngay cả khi pool hỗ trợ thay thuộc tính credential ở runtime, các kết nối cũ vẫn có vòng đời riêng; cách dễ kiểm soát là **xây dựng pool mới và chuyển luồng sử dụng**.

### Ba mục tiêu kiểm chứng được

1. **Không có checkout mới từ pool cũ** sau khi hệ thống công bố pool mới.
2. **Các operation đã bắt đầu được gắn với đúng một thế hệ pool**, tránh chuyển connection ở giữa transaction.
3. **Pool cũ được đóng** sau khi hết operation đang dùng hoặc sau một hạn drain có chính sách rõ ràng; mọi lỗi do revoke được báo và phân loại.

Khả năng không gián đoạn phụ thuộc việc Vault/DB có cho phép **hai credential cùng tồn tại** trong lúc chuyển tiếp.

## 4. Chiến lược chuyển tiếp: prepare, switch, drain, retire

Một quy trình an toàn hơn việc sửa password trực tiếp:

~~~mermaid
sequenceDiagram
    participant V as Vault / Database backend
    participant R as Rotation coordinator
    participant P2 as Pool P2 (credential mới)
    participant Route as Request router
    participant P1 as Pool P1 (credential cũ)
    participant Req as Request đang chạy
    R->>V: Yêu cầu credential C2 + lease L2
    V-->>R: C2 / L2
    R->>P2: Khởi tạo pool và thử query
    P2-->>R: Health-check PASS
    R->>Route: Publish P2 nguyên tử
    Route->>P2: Checkout mới
    Req->>P1: Kết thúc SQL/transaction nếu còn hợp lệ
    R->>P1: Ngừng checkout mới; chờ drain
    P1-->>R: Số operation in-flight = 0
    R->>P1: Close pool cũ
    R->>V: Revoke L1 nếu policy và quyền cho phép
~~~

Thứ tự ở sơ đồ áp dụng khi **ta kiểm soát được thời điểm revoke L1**. Với lease đã hết hạn hoặc Vault tự revoke trước khi P2 sẵn sàng, không thể hoàn thành một giao dịch đã bị backend hủy bằng cách chuyển pool. Khi đó, ứng dụng cần phục hồi ở lớp nghiệp vụ.

### Pha 1 — Prepare

Đọc hoặc nhận credential C2, tạo **một HikariDataSource mới** với `username`/`password` C2, SSL/driver/options đúng như P1. Thử kết nối thật và câu query tối thiểu, có timeout và giới hạn connection. Không coi “Vault trả credential” là bằng chứng database đã sẵn sàng chấp nhận C2; có thể có độ trễ tạo user hoặc propagation.

Nếu prepare thất bại, **không publish P2**. Giữ P1 nếu còn hợp lệ, retry có giới hạn; nếu L1 đã bị revoke, báo degraded/unready.

### Pha 2 — Switch

Sau khi P2 đạt health-check, publish pointer **nguyên tử**: operation mới chọn P2, operation đã mượn P1 giữ P1 đến cuối. Tránh thay singleton `DataSource` tùy tiện giữa giao dịch Spring `@Transactional`.

### Pha 3 — Drain

Đánh dấu P1 **retiring**, không cho borrow mới, đếm operation còn dùng P1 và đóng khi in-flight bằng 0. Đặt drain deadline cho job treo/connection leak, ngắn hơn thời gian còn lại của lease cũ.

Đóng P1 khi còn operation có thể gây rollback; phải có timeout, idempotency và xử lý thất bại.

### Pha 4 — Retire

Đóng P1, xác minh số connection/active sessions trở về 0; nếu chịu trách nhiệm revoke lease L1, thực hiện theo quyền và quy trình đã thiết kế. Với `SecretLeaseContainer`, kiểm tra **ai quản lý renew/revoke** để tránh thao tác revoke trùng hoặc revoke trước khi drain. Không cấp quyền `sudo` hay `sys/*` cho app chỉ vì nó cần đọc database credential.

Khi không kiểm soát được revoke, bắt đầu rotation **sớm trước TTL**, tính cả prepare, health-check, transaction dài nhất và trễ mạng.

## 5. Spring Vault hỗ trợ nhận thông tin rotation thế nào?

Với **database secrets engine**, Vault trả một dynamic secret kèm `lease_id`, `lease_duration` và `renewable`. Trong Spring Vault, `SecretLeaseContainer` theo dõi một `RequestedSecret`, renew lease khi còn được phép hoặc yêu cầu secret mới theo chính sách.

| Chế độ | Cách đăng ký | Ý nghĩa với ứng dụng |
| --- | --- | --- |
| `RENEW` | `RequestedSecret.renewable("database/creds/orders-ro")` | Cố gia hạn lease; không tự cung cấp bộ credential mới khi đến giới hạn như rotation. |
| `ROTATE` | `RequestedSecret.rotating("database/creds/orders-ro")` | Theo dõi lease và lấy secret mới khi tới điểm rotation theo điều kiện backend/container. |

Các sự kiện thường gặp:

| Event | Dùng để làm gì? |
| --- | --- |
| `SecretLeaseCreatedEvent` | Nhận secret lần đầu, lấy username/password và chuẩn bị pool ban đầu. |
| `SecretLeaseRotatedEvent` | Nhận credential thay thế và khởi động quá trình build/switch/drain. |
| `AfterSecretLeaseRenewedEvent` | Theo dõi gia hạn lease; không cần đổi pool chỉ vì TTL tăng. |
| `SecretLeaseExpiredEvent` | Đánh dấu credential có thể không còn hợp lệ; kiểm tra readiness và chuyển sang fallback. |
| `SecretLeaseErrorEvent` hoặc `LeaseErrorListener` | Xác định lỗi đọc/renew/revoke, ghi metric và áp dụng phục hồi có giới hạn. |

Tùy phiên bản, `SecretLeaseRotatedEvent` là một dạng `SecretLeaseCreatedEvent`. Với listener có nhiều nhánh, **xử lý rotated trước created**, hoặc dùng một nhánh chung nhận cả hai và giữ trạng thái generation đúng. `getSecrets()` chứa credential nhạy cảm: không log raw event.

### Điểm giới hạn rất quan trọng

Khi container đã đến thời điểm rotate, **đừng mặc nhiên cho rằng credential cũ còn hiệu lực đủ lâu để drain**. Lease có thể đã đạt max TTL hoặc đã bị revoke bởi backend. Nếu yêu cầu “không gián đoạn”, coordinator phải chủ động lấy bộ credential **trước** khi bộ cũ đến hạn, và kiểm soát thời điểm thu hồi nếu hệ thống hỗ trợ. `SecretLeaseContainer` cung cấp tín hiệu và lifecycle, nhưng chính ứng dụng phải thực hiện thay datasource/pool và xử lý các connection đang dùng.

## 6. Mẫu Java: quản lý hai thế hệ pool an toàn với operation in-flight

Ví dụ dưới đây dùng **Java 17, HikariCP và Spring JDBC**. `RotatingJdbcPools` giữ pointer tới một pool hiện hành. Mỗi operation mượn một `Handle`; handle gắn với pool cụ thể đến khi đóng, kể cả khi một thread khác cài credential mới. Thao tác đổi pointer và cập nhật bộ đếm được bảo vệ bằng cùng một monitor để tránh race giữa borrow và retire.

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.function.Function;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class RotatingJdbcPools implements AutoCloseable {
    private final Object mutex = new Object();
    private final String jdbcUrl;
    private Generation current;
    private boolean stopped;

    public RotatingJdbcPools(String jdbcUrl) {
        this.jdbcUrl = jdbcUrl;
    }

    public void install(String username, String password) throws SQLException {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(8);
        config.setConnectionTimeout(5000);
        HikariDataSource candidate = new HikariDataSource(config);

        // Validate bằng chính credential mới trước khi public.
        try (Connection connection = candidate.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("SELECT 1");
        } catch (SQLException | RuntimeException failure) {
            candidate.close();
            throw failure;
        }

        Generation old;
        boolean closeOld = false;
        synchronized (mutex) {
            if (stopped) {
                candidate.close();
                throw new IllegalStateException("Pool manager already stopped");
            }
            old = current;
            current = new Generation(candidate);
            if (old != null) {
                old.retiring = true;
                if (old.inFlight == 0) {
                    old.closed = true;
                    closeOld = true;
                }
            }
        }
        if (closeOld) old.pool.close();
    }

    public Handle acquire() {
        synchronized (mutex) {
            if (stopped || current == null) {
                throw new IllegalStateException("No active DB credential");
            }
            current.inFlight++;
            return new Handle(current);
        }
    }

    public final class Handle implements AutoCloseable {
        private final Generation generation;
        private boolean released;

        private Handle(Generation generation) {
            this.generation = generation;
        }

        // Transaction luôn dùng một generation từ đầu tới cuối.
        public <T> T inTransaction(Function<JdbcTemplate, T> operation) {
            if (released) throw new IllegalStateException("Handle closed");
            var transactionManager =
                new DataSourceTransactionManager(generation.pool);
            var transaction = new TransactionTemplate(transactionManager);
            return transaction.execute(
                status -> operation.apply(new JdbcTemplate(generation.pool)));
        }

        @Override
        public void close() {
            boolean closePool = false;
            synchronized (mutex) {
                if (released) return;
                released = true;
                generation.inFlight--;
                if (generation.retiring && generation.inFlight == 0
                        && !generation.closed) {
                    generation.closed = true;
                    closePool = true;
                }
            }
            if (closePool) generation.pool.close();
        }
    }

    private static final class Generation {
        final HikariDataSource pool;
        int inFlight;
        boolean retiring;
        boolean closed;
        Generation(HikariDataSource pool) { this.pool = pool; }
    }

    @Override
    public void close() {
        Generation old;
        boolean closeOld = false;
        synchronized (mutex) {
            if (stopped) return;
            stopped = true;
            old = current;
            current = null;
            if (old != null) {
                old.retiring = true;
                if (old.inFlight == 0 && !old.closed) {
                    old.closed = true;
                    closeOld = true;
                }
            }
        }
        if (closeOld) old.pool.close();
    }
}
~~~

Sử dụng trong một operation:

~~~java
try (RotatingJdbcPools.Handle handle = pools.acquire()) {
    return handle.inTransaction(jdbc -> jdbc.queryForObject(
        "SELECT status FROM orders WHERE order_id = ?",
        String.class, orderId));
}
~~~

**Điều kiện sử dụng mã mẫu:**

1. Operation/transaction phải hoàn tất **trước khi đóng handle**; không trả `Connection`, `ResultSet` hay lazy stream đang dùng pool ra ngoài scope.
2. Nếu một giao dịch gồm nhiều repository calls, toàn bộ giao dịch phải dùng **cùng handle và transaction manager**. Mẫu tạo `TransactionTemplate` trong handle nhằm làm rõ phạm vi; production có thể lưu sẵn các wrapper và phối hợp Spring transaction management hiệu quả hơn.
3. Khi nhiều event rotation đến, hãy **tuần tự hóa quá trình install**. Mã mẫu chỉ bảo vệ việc publish pointer, chưa điều phối các lần kiểm tra P2 song song. Nếu P3 đã được publish rồi một task P2 hoàn thành muộn, pool có thể bị hạ phiên bản nếu không có coordinator.
4. Manager này đóng pool cũ khi mọi handle được trả, **chưa thực thi deadline drain hoặc xử lý handle bị rò rỉ**. Production cần timeout, metric in-flight, cảnh báo và chính sách cưỡng bức kết thúc/quarantine khi vượt hạn.
5. Một handle đã mượn không ngăn database thu hồi quyền của username cũ; operation vẫn có thể lỗi giữa chừng. Phải xử lý rollback/retry ở tầng nghiệp vụ.

Dùng `try-with-resources`, theo dõi borrowed handles; không giữ handle trong singleton hay queue vô hạn.

## 7. Nối `SecretLeaseContainer` vào rotation coordinator

Ví dụ wiring khái niệm dưới đây tạo `RequestedSecret` và lắng nghe secret mới. `rotationExecutor` nên là **executor đơn luồng có queue giới hạn**, bảo đảm sự kiện credential đi qua một hàng đợi có thứ tự; đặt metric queue depth và xử lý trường hợp backlog. Bean `RotatingJdbcPools` được cấu hình riêng với JDBC URL.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;

@Configuration
public class OrdersRotationConfiguration {
    @Bean
    SecretLeaseContainer ordersLeaseContainer(
            VaultOperations vault,
            RotatingJdbcPools pools,
            Executor rotationExecutor) {

        var container = new SecretLeaseContainer(vault);
        RequestedSecret requested =
            RequestedSecret.rotating("database/creds/orders-ro");

        container.addLeaseListener(new LeaseListenerAdapter() {
            @Override
            public void onLeaseEvent(SecretLeaseEvent event) {
                if (!requested.equals(event.getSource())) return;

                // RotatedEvent cũng có thể là CreatedEvent.
                if (event instanceof SecretLeaseCreatedEvent created) {
                    Map<String, Object> values =
                        new HashMap<>(created.getSecrets());
                    rotationExecutor.execute(() -> {
                        try {
                            String user = (String) values.get("username");
                            String pass = (String) values.get("password");
                            pools.install(user, pass);
                            // Báo READY chỉ sau khi install thành công.
                        } catch (Exception failure) {
                            // Báo unhealthy và retry theo chính sách.
                            // Tuyệt đối không log values hoặc password.
                        } finally {
                            values.clear();
                        }
                    });
                } else if (event instanceof SecretLeaseExpiredEvent) {
                    // Kiểm tra trạng thái pool/readiness;
                    // không coi kết nối cũ vẫn hợp lệ.
                }
            }
        });

        container.addRequestedSecret(requested);
        return container; // Spring quản lý start/stop/destroy.
    }
}
~~~

Đây là khung tích hợp để chỉ ra **thứ tự các tác vụ**. Production cần thay khối xử lý lỗi bằng telemetry/alert thực, xác nhận `username/password` và `lease_id` tương ứng, bỏ qua sự kiện cũ, đặt queue timeout và xử lý executor bị từ chối task. Sao chép map vào một task bất đồng bộ vẫn giữ bí mật trong heap cho tới khi hoàn tất; bảo vệ heap/log, giới hạn queue và không cho phép dump trái phép.

**Quan trọng:** việc nghe `SecretLeaseCreatedEvent` và cài P2 chỉ đủ khi secret mới thực sự đến **trước** thời điểm revoke gây mất khả năng làm việc của P1. Nếu `SecretLeaseContainer` phát sự kiện sau expiry, phần chuyển pool vẫn cần khả năng xử lý gián đoạn. Muốn điều phối overlap chủ động, cần thiết kế một **credential rotation orchestrator** có quyền lấy lease mới trước hạn và trì hoãn revoke cũ phù hợp backend, thay vì chỉ dựa vào một event đã xảy ra.

Không register lại cùng `RequestedSecret` mỗi khi workload login lại. `LifecycleAwareSessionManager` xử lý token; `SecretLeaseContainer` xử lý lease; rotation của database là bước ứng dụng áp dụng secret vào consumer.

## 8. Xử lý transaction và retry khi pool cũ bị vô hiệu hóa

Ngay cả khi P2 đã được publish, transaction đang dùng P1 có thể bị revoke giữa chừng. Đây là sự cố **tại tầng nghiệp vụ**, vì DB có thể trả lỗi ngay trước hoặc sau thao tác ghi.

### Không retry mù mọi yêu cầu

| Loại operation | Khi connection cũ thất bại | Chính sách gợi ý |
| --- | --- | --- |
| `SELECT` không có side effect | Thường có thể thử lại sau khi lấy connection từ P2. | Retry có giới hạn, backoff, timeout và quan sát lỗi. |
| Ghi dữ liệu có transaction rõ ràng, rollback chắc chắn | Có thể thử lại **toàn bộ transaction** nếu idempotent. | Dùng idempotency key hoặc điều kiện version/CAS. |
| Gửi thanh toán, email, sự kiện ra ngoài | Có thể đã tạo side effect dù DB báo lỗi. | Không retry tự động nếu chưa có cơ chế chống trùng; dùng outbox/dedupe. |
| COMMIT timeout, trạng thái không chắc chắn | Có thể đã commit nhưng client không thấy kết quả. | Tra cứu theo business key/transaction ID trước khi quyết định retry. |
| Lỗi xác thực khi checkout P1 | Có thể do credential đã revoke. | Chuyển sang P2 nếu đã sẵn sàng; đo lỗi và chặn cấp lại P1. |

Không coi mọi `SQLException` hoặc HTTP `403` là lỗi credential hết hạn: phân biệt SQLState, vendor error code, DNS, network partition, deadlock, connection timeout và Vault ACL. Ví dụ SQLState `28xxx` thường liên quan lỗi ủy quyền/xác thực, nhưng mã chính xác và hành vi phụ thuộc driver/backend.

### Transaction phải giữ nguyên một generation

Sơ đồ đúng:

~~~text
Request / Business transaction
     |
     +--> acquire Handle(P1) --------> SELECT / UPDATE / COMMIT
                                      |
                                      +--> close Handle(P1)

                     ROTATE P1 -> P2

Request bắt đầu sau publish --> acquire Handle(P2) -> ...
~~~

Không đổi connection ở giữa transaction hoặc bỏ qua quy tắc nhất quán để tiếp tục một giao dịch P1 bằng câu lệnh P2. Khi P1 gặp lỗi sau revoke, transaction thường cần rollback, rồi quyết định retry một **operation mới** từ đầu nếu nghiệp vụ cho phép.

## 9. Drain deadline, readiness và rollback có kiểm soát

### Deadline hữu hạn

Operation bị treo có thể giữ P1 vô hạn. Theo dõi `in_flight_per_generation`, `retiring_age_seconds`, `old_pool_active_connections` và **max drain duration**. Khi vượt hạn, chọn ngắt operation hoặc đưa instance ra khỏi traffic theo SLO.

Nếu L1 hết hạn sau 30 giây nhưng transaction kéo dài 5 phút, phải tăng overlap, rút ngắn transaction hoặc chấp nhận rollback.

### Startup và shutdown

**Khởi động:** readiness chỉ PASS sau khi nhận credential, build pool và test DB thành công.

**Shutdown:** ngừng nhận traffic, drain tới deadline, đóng pool rồi revoke lease nếu có quyền; không revoke credential còn được replica khác dùng chung.

**Rotation lỗi:** giữ P1 nếu hợp lệ, retry trước expiry; nếu đã revoke thì báo unready. Tránh event P2 tới muộn ghi đè generation P3 mới hơn.

### Nhiều replica

Mỗi replica nên có session manager, lease và pool riêng nếu khả thi. Nếu chia sẻ credential, xác định chủ sở hữu lease và quyền revoke để tránh gián đoạn cả cụm.

## 10. Kiểm thử tích hợp cần chứng minh điều gì?

Kiểm thử với Vault và database thật trong lab có cấu hình tạo/revoke user. Mock `VaultTemplate` không kiểm chứng được tác động lên DB session.

| ID | Tình huống | Kết quả cần xác nhận |
| --- | --- | --- |
| ROT-01 | P1 active; cấp C2/L2; build P2 PASS | Chỉ sau health-check mới publish P2; checkout mới dùng C2. |
| ROT-02 | Request A đã acquire P1 trong lúc publish P2 | A giữ P1 đến khi kết thúc; không đổi transaction manager/connection giữa chừng. |
| ROT-03 | P1 còn hai handle, một handle đóng | P1 chưa bị đóng; đóng khi handle cuối cùng trả về. |
| ROT-04 | P2 không connect được (sai credential/TLS) | P2 bị dọn; P1 vẫn hiện hành nếu còn hợp lệ; có lỗi rotation rõ ràng. |
| ROT-05 | Credential C1 bị revoke trước khi A commit | A nhận lỗi thực tế; rollback/retry có kiểm soát, không báo thành công giả. |
| ROT-06 | Event P3 đến sau P2 nhưng P2 hoàn thành muộn | P3 vẫn là pool hiện hành; generation không lùi. |
| ROT-08 | Token Vault re-login nhưng lease cũ chưa rotate | Không tự đăng ký thêm secret, không tự đổi pool nếu credential không đổi. |
| ROT-09 | L1 revoke, Pod shutdown | Xác minh trạng thái session theo backend và drain trước khi đóng pool. |

Một phép test concurrency hữu ích dùng **`CountDownLatch`**:

1. Thread A acquire P1, vào transaction và chờ latch giữa hai câu lệnh SQL.
2. Thread B nhận credential C2, build/health-check P2 rồi publish pointer.
3. Thread C acquire và truy vấn, xác nhận connection thuộc generation P2.
4. Thread A được thả latch, commit hoặc gặp lỗi revoke theo điều kiện test; sau khi đóng handle cuối cùng, P1 phải được retire.
5. Kiểm tra sự kiện và metric không chứa username/password, token, `lease_id` nhạy cảm hoặc kết quả secret thô.

Các test trên phải xác minh **hành vi database thật** và phân biệt lỗi Vault authentication/ACL, lỗi kết nối DB, lỗi transaction. Với test revoke, không dựa vào “request thất bại” chung chung: cần xem đúng SQLState/response và log đã được lọc bí mật.

## 11. Giám sát và vận hành an toàn

Theo dõi ba nhóm tín hiệu:

- **Vault:** số lease cấp/renew/revoke, thời gian tới expiry, lỗi `sys/leases/...` và auth.
- **Connection pool:** active/idle/pending, generation retiring, thời gian drain và health-check fail.
- **Nghiệp vụ:** latency, rollback, lỗi sau revoke, retry và commit không rõ trạng thái.

Không log giá trị từ `SecretLeaseCreatedEvent.getSecrets()`, Vault token, database password hoặc thông tin authentication header. Có thể log path đã được phân loại, generation ID nội bộ, loại lỗi, request ID và lease metadata không nhạy cảm theo chính sách của tổ chức.

Mẫu cảnh báo đáng ưu tiên: credential cũ sắp hết hạn nhưng P2 chưa sẵn sàng; pool retiring quá thời hạn; số transaction lỗi tăng sau rotation; P1 còn checkout mới sau publish; replica nhận `403` từ Vault hoặc mất quyền với database. Với mỗi cảnh báo, cần thông tin generation và mốc thời gian để điều tra.

### Checklist trước khi triển khai

- [ ] Có kế hoạch cấp credential mới **trước thời hạn revoke** với overlap đủ cho build, switch, drain.
- [ ] Pool P2 được kết nối thử thật và kiểm tra quyền trước khi công bố.
- [ ] Checkout mới chỉ dùng generation hiện hành; transaction đang chạy giữ một generation cố định.
- [ ] Pool cũ không nhận checkout mới, được đóng sau khi drain hoặc khi hết deadline theo chính sách.
- [ ] Lỗi revoke giữa transaction được rollback/phân loại; retry chỉ khi có idempotency.
- [ ] `SecretLeaseContainer` và session manager được quản lý đúng lifecycle, không đăng ký trùng khi re-login.
- [ ] Mỗi replica có ownership lease rõ ràng; không revoke credential đang dùng chung.
- [ ] Có metric, audit, readiness và thử nghiệm end-to-end với Vault + DB thực.

### Câu hỏi tự đánh giá

1. Tại sao cập nhật password trên HikariCP không bảo đảm các connection đã mở dùng danh tính mới?
2. Sau khi Vault revoke credential cũ, một transaction đang chạy có luôn được phép commit không? Cần kiểm chứng điều gì trên database?
3. Vì sao phải build và thử P2 trước khi chuyển pointer từ P1?
4. Tại sao `SecretLeaseRotatedEvent` không đủ để khẳng định đã có zero downtime?
5. Nếu transaction bị lỗi ngay khi COMMIT, có thể retry toàn bộ thao tác mà không xem trạng thái thực tế không?
6. `LifecycleAwareSessionManager` đăng nhập lại có khiến `SecretLeaseContainer` bắt buộc tạo credential mới không?
7. Khi nào `RequestedSecret.rotating(...)` phù hợp hơn `RequestedSecret.renewable(...)`?
8. Một pool retiring còn một handle bị rò rỉ: cần chuẩn bị chính sách gì để không giữ credential quá hạn vô hạn?

## Tài liệu tham khảo chính thức

- [Spring Vault — Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault API — SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault API — RequestedSecret](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/domain/RequestedSecret.html)
- [HashiCorp Vault — Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Lease, renew và revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HikariCP — Configuration và pool lifecycle](https://github.com/brettwooldridge/HikariCP)

**Ghi nhớ:** Xoay vòng credential hoàn chỉnh phải kết nối hai vòng đời: **Vault cấp/thu hồi secret có lease** và **ứng dụng chuyển các operation từ pool cũ sang pool mới**. Với kết nối đang hoạt động, hãy giữ transaction nhất quán, drain trong giới hạn TTL, chuẩn bị retry có kiểm soát và chấp nhận rằng một credential đã bị backend thu hồi không thể được “cứu” chỉ bằng việc thay password trong Java.
