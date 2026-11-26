# Cập nhật thông tin xác thực cho connection pool hoặc HTTP client

## 1. Vấn đề: Vault đã cấp credential mới nhưng ứng dụng vẫn dùng credential cũ

Trong chương **Xoay vòng trong ứng dụng** của module **SPRING_VAULT**, ứng dụng Java có thể dùng `VaultTemplate` lấy tài khoản database ngắn hạn, API key từ KV, chứng thư PKI hoặc token để gọi một dịch vụ khác. HashiCorp Vault giúp quản lý quyền truy cập, TTL và việc cấp lại secret, nhưng **ứng dụng vẫn phải cập nhật thành phần đang sử dụng credential**.

Ví dụ: lúc 10:00, Vault database secrets engine cấp tài khoản `v-db-001` cho ứng dụng với lease 30 phút. HikariCP đã dùng tài khoản này để mở 20 JDBC connections. Đến lúc cần xoay vòng, Vault cấp `v-db-002`; nếu ứng dụng chỉ thay biến cấu hình `username/password` mà không cập nhật pool, những kết nối hiện hữu vẫn được tạo bằng tài khoản cũ. Khi Vault thu hồi tài khoản `v-db-001`, request SQL có thể lỗi hoặc pool không tạo được kết nối mới.

Tình huống tương tự xảy ra với HTTP client: một `RestClient` mang `Authorization: Bearer ...` cố định, một API key cũ lưu trong interceptor, hoặc một client mTLS đã tạo `SSLContext` từ KeyStore trước khi chứng thư được thay. Việc Vault đã lưu giá trị mới **không đồng nghĩa** HTTP client đang gửi giá trị mới.

Sau bài học, bạn có thể:

- Phân biệt Vault **login token**, **dynamic secret lease**, KV static secret và chứng thư TLS được dùng bởi ứng dụng.
- Nhận sự kiện cấp mới/xoay vòng từ `SecretLeaseContainer` hoặc `ManagedSecret` và truyền credential đến consumer phù hợp.
- Lựa chọn cách thay credential cho JDBC pool: cập nhật credential cho kết nối mới hoặc dựng pool thế hệ mới và chuyển traffic.
- Cập nhật HTTP bearer token/API key theo **từng request**; nhận biết khi phải xây lại HTTP/TLS client.
- Thiết kế thứ tự cập nhật, xác minh, rút credential cũ, xử lý lỗi, metric và kiểm thử tích hợp mà không làm lộ secret.

> **Giả định trong bài:** Vault database secrets engine được mount tại `database/`, role là `payments-ro`; KV v2 của ứng dụng nằm tại `kv-app/`. Mọi hostname, username, secret path và token dưới đây chỉ phục vụ ví dụ. Không sử dụng credential thật trong mã nguồn hoặc log.

## 2. Chọn đúng vòng đời và thành phần phải cập nhật

| Loại thông tin xác thực | Ví dụ lấy từ Vault | Vòng đời | Consumer cần cập nhật |
|---|---|---|---|
| **Vault client token** | Đăng nhập bằng Kubernetes, AppRole, AWS, mTLS | TTL, renew, revoke và re-login | `VaultTemplate` / Vault HTTP client qua `SessionManager` |
| **Tài khoản database động** | `database/creds/payments-ro` trả `username/password/lease_id` | Lease, renew, revoke, rotation | JDBC `DataSource`, pool như HikariCP, transaction đang dùng connection cũ |
| **API key trong KV v2** | `kv-app/data/integrations/partner` | Giá trị theo version; **không tự có lease rotation event** | HTTP header/interceptor hoặc cấu hình SDK của dịch vụ ngoài |
| **Bearer token của dịch vụ ngoài** | Vault KV hoặc nguồn cấp OAuth riêng | `expires_at`, revoke, refresh theo issuer | HTTP client gọi dịch vụ ngoài |
| **Chứng thư mTLS của client** | Vault PKI hoặc KeyStore/Secret volume | Hạn chứng thư, cấp lại và thu hồi | `SSLContext`, `KeyManager`, TLS connection pool |
| **Truststore/CA của server** | Cấu hình trust cho endpoint Vault/partner | CA rotation, chain mới | `TrustManager`, SSLContext và kết nối TLS mới |

**Hai cặp khác nhau cần nhớ:**

1. `LifecycleAwareSessionManager` quản lý **Vault client token dùng để gọi Vault**. Khi đăng nhập lại, nó không tự cập nhật JDBC pool bằng database credential mới.
2. `SecretLeaseContainer` quản lý **secret/lease**. Nó có thể lấy lại database username/password, nhưng **không tự thay toàn bộ JDBC connections** đang mở trong ứng dụng.

Không nên tự gắn một `X-Vault-Token` tĩnh lên HTTP client dành cho `VaultTemplate` khi Spring Vault đã có `SessionManager`. Các ví dụ bearer token ở phần sau dùng cho **HTTP client gọi dịch vụ ngoài Vault**.

## 3. Mô hình cập nhật an toàn: nhận, chuẩn bị, chuyển, rút

Credential rotation là một quá trình chuyển thế hệ chứ không phải phép gán một chuỗi.

~~~mermaid
flowchart TD
    A[Vault cấp hoặc cập nhật credential B] --> B[Ứng dụng nhận event / đọc version mới]
    B --> C{Credential hợp lệ về cú pháp và scope?}
    C -- Không --> D[Giữ trạng thái lỗi, cảnh báo; không cài giá trị hỏng]
    C -- Có --> E[Chuẩn bị pool/client mới bằng B]
    E --> F{Kết nối kiểm tra thành công?}
    F -- Không --> G[Không chuyển traffic; retry có giới hạn]
    F -- Có --> H[Chuyển request mới sang B]
    H --> I[Cho request/transaction cũ hoàn thành theo deadline]
    I --> J[Đóng kết nối thế hệ A và thu hồi A theo policy]
    J --> K[Kiểm tra metrics, log không nhạy cảm, hoàn tất]
~~~

Trong đó **A** là credential đang chạy, **B** là credential mới. Các bước phải đáp ứng:

- **Tính hợp lệ:** username/password có mặt và có quyền dự kiến; API token có kiểu và thời hạn phù hợp; chứng thư có chain/private key hợp lệ.
- **Tính nhất quán:** `username` và `password` thuộc cùng một thế hệ, không để luồng đồng thời nhìn thấy `username-B` đi với `password-A`.
- **Chuyển mượt:** request mới lấy B, request/transaction cũ được phép hoàn thành nếu credential A còn được server chấp nhận trong giai đoạn chuyển.
- **Không rút quá sớm:** kiểm tra B thật sự hoạt động trước khi thu hồi A; đảm bảo thời gian overlap phù hợp với TTL và yêu cầu bảo mật.
- **Có giới hạn:** nếu B không hoạt động, hệ thống không giữ A vô hạn ngoài TTL/retention; dừng nhận công việc mới khi không còn credential hợp lệ.
- **Có quan sát:** ghi trạng thái và thế hệ bằng ID/fingerprint an toàn, không ghi secret value hoặc chuỗi token.

### Vì sao cần khoảng chồng lấp?

Hãy tưởng tượng transaction T1 dùng connection đã mở với tài khoản A, trong khi T2 mới được cấp kết nối bằng B. Nếu A bị revoke ngay trong lúc T1 chưa commit, hành vi của T1 phụ thuộc database và cách revoke user/session, có thể thất bại dù pool đã được cập nhật. Vì vậy, **an toàn vòng đời cần phối hợp thời điểm cấp B và thu hồi A**; `softEvictConnections()` không hứa kết thúc mọi transaction cũ ngay lập tức.

Với credential bị lộ, bảo mật có thể đòi **thu hồi ngay**, chấp nhận gián đoạn cho các request cũ. Với xoay vòng định kỳ, dùng overlap ngắn và drain theo deadline giúp giảm lỗi. Chính sách cụ thể phụ thuộc hệ thống và quyền truy cập.

## 4. Nhận credential mới từ Spring Vault

### 4.1. SecretLeaseContainer và các event

`SecretLeaseContainer` quản lý các secret có lease. Nó có hai chế độ đáng phân biệt:

| Chế độ | Hành vi | Phù hợp |
|---|---|---|
| `requestRenewableSecret(path)` | Nhận secret và ưu tiên gia hạn lease khi được phép | Secret cần giữ nguyên credential qua nhiều vòng renew |
| `requestRotatingSecret(path)` | Nhận secret, renew khi còn khả năng, **lấy secret mới khi lease cần rotation** | Database credential muốn thay thế sau vòng đời lease |

Các event hữu ích:

- `SecretLeaseCreatedEvent`: lần đầu nhận secret có dữ liệu; **`SecretLeaseRotatedEvent` kế thừa class này**, nên điều kiện `instanceof SecretLeaseCreatedEvent` cũng nhận được credential sau rotation.
- `AfterSecretLeaseRenewedEvent`: **gia hạn lease** thành công; thông thường không cần đổi username/password nếu dữ liệu secret không đổi.
- `SecretLeaseExpiredEvent`: lease bị xem là hết hạn; cần kiểm tra consumer đang dùng credential nào và có thể phải ngừng cấp connection mới.
- `SecretNotFoundEvent` / `SecretLeaseErrorEvent`: không nhận được dữ liệu hoặc có lỗi Vault/network; không coi đó là credential rỗng hợp lệ.

Vault **không push sự kiện trực tiếp** đến JVM. Container chủ động gọi Vault và lập lịch theo TTL. Event khi lease hết hạn có thể đến **sau thời điểm hết hạn thực tế**, nên không dựa vào riêng event để cho phép dùng credential đã quá hạn.

Ví dụ nối event vào một tầng điều phối pool riêng:

~~~java
import java.util.Map;

import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;

public final class DatabaseLeaseRegistration {

    // Lớp này là adapter; PoolRotationCoordinator do ứng dụng triển khai.
    public static void register(
            SecretLeaseContainer container,
            PoolRotationCoordinator coordinator) {

        RequestedSecret target =
                container.requestRotatingSecret("database/creds/payments-ro");

        // Đăng ký trước khi container.start() để không bỏ lỡ event đầu.
        container.addLeaseListener(new LeaseListenerAdapter() {
            @Override
            public void onLeaseEvent(SecretLeaseEvent event) {
                if (!target.equals(event.getSource())) {
                    return;
                }

                if (event instanceof SecretLeaseCreatedEvent created) {
                    Map<String, Object> values = created.getSecrets();
                    Object username = values.get("username");
                    Object password = values.get("password");

                    if (username instanceof String user
                            && password instanceof String pass
                            && !user.isBlank() && !pass.isBlank()) {
                        // Xếp công việc sang một worker riêng có giới hạn.
                        coordinator.enqueueRotation(user, pass);
                    } else {
                        coordinator.reportMissingFields();
                    }
                } else if (event instanceof SecretLeaseExpiredEvent) {
                    coordinator.reportLeaseExpired();
                }
            }

            @Override
            public void onLeaseError(
                    SecretLeaseEvent event, Exception exception) {
                if (target.equals(event.getSource())) {
                    coordinator.reportVaultError(
                            exception.getClass().getSimpleName());
                }
            }
        });
    }

    public interface PoolRotationCoordinator {
        void enqueueRotation(String username, String password);
        void reportMissingFields();
        void reportLeaseExpired();
        void reportVaultError(String errorType);
    }
}
~~~

Ví dụ trên chủ đích **không** tạo pool trong callback, vì callback có thể chạy trên thread khởi động hoặc worker xử lý lease của Spring Vault. `enqueueRotation` phải sử dụng hàng đợi **có giới hạn**, chạy tuần tự theo thế hệ và kiểm soát retry. Không ghi `Map` secrets, `password` hay `exception.getMessage()` ra log. Nếu sử dụng Java dưới 17, thay pattern matching của `instanceof` bằng cast thông thường.

Trong cấu hình Spring Vault Core tự quản, tạo `SecretLeaseContainer` với `VaultOperations` và `TaskScheduler`, đăng ký listener rồi gọi `afterPropertiesSet()`/`start()` theo lifecycle. Trong Spring Cloud Vault, ưu tiên tích hợp container/lease do framework quản lý; **không khởi tạo container thứ hai** để cùng renew một secret không cần thiết.

### 4.2. ManagedSecret (Spring Vault 4.1+)

Spring Vault 4.1 bổ sung `ManagedSecret` để khai báo callback nhận credential mới, không phải tự xử lý mọi event. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.lease.ManagedSecret;
import org.springframework.vault.core.lease.ManagedSecret.UsernamePassword;

@Configuration(proxyBeanMethods = false)
class DatabaseCredentialConfiguration {

    @Bean
    ManagedSecret paymentsDatabaseCredentials(
            DatabaseLeaseRegistration.PoolRotationCoordinator coordinator) {

        return ManagedSecret.rotating(
                "database/creds/payments-ro",
                secrets -> secrets.as(UsernamePassword::from)
                        .applyTo((username, password) ->
                                coordinator.enqueueRotation(
                                        username, password.toString())),
                error -> coordinator.reportVaultError(
                        error.getClass().getSimpleName()));
    }
}
~~~

`ManagedSecret` đăng ký qua `SecretRegistrar`/`SecretsRegistry`, thường được tích hợp theo cấu hình quản lý lease của Spring Vault. Một `@Bean ManagedSecret` **chỉ hoạt động khi thực sự được đăng ký với container**, đúng lifecycle; kiểm tra auto-configuration và version đang dùng. Callback được gọi khi nhận credential ban đầu và khi rotation; xử lý pool vẫn là trách nhiệm của ứng dụng.

> **Cảnh báo về thứ tự khởi động:** một số thành phần như Spring Data JPA, Flyway, Hibernate có thể cần DataSource ngay khi khởi tạo. Nếu credential chỉ xuất hiện sau `SecretLeaseContainer.start()`, phải thiết kế dependency ordering hoặc bootstrap phù hợp để chúng không mở connection trước khi có credential hợp lệ.

### 4.3. Static KV không phát lease rotation khi có version mới

Với KV v2, gọi:

~~~java
var kv = vaultTemplate.opsForVersionedKeyValue("kv-app");
var response = kv.get("integrations/partner");
~~~

sẽ đọc **giá trị hiện hành tại thời điểm request**. Việc người quản trị ghi KV version mới **không tự gửi thông báo** đến HTTP client đã giữ API key cũ. Nếu hệ thống cần cập nhật runtime, phải thiết kế một trong các cách: polling có giới hạn và so sánh version/metadata, webhook/notification tin cậy do hệ thống điều phối phát ra, thao tác refresh có kiểm soát, hoặc rollout Pod. Luôn xác minh nguồn cập nhật và tránh polling liên tục làm tăng tải Vault.

## 5. Connection pool: điều gì xảy ra khi đổi username/password?

JDBC pool lưu và tái sử dụng những **connection vật lý** đã được xác thực với database. Sau khi thay username/password, có ba trạng thái tồn tại đồng thời:

1. Connection **đang dùng** được mở với credential A; có thể có transaction chưa commit.
2. Connection **idle** cũng được mở bằng A, vẫn nằm trong pool.
3. Connection **mở mới** sẽ dùng credential B **chỉ nếu pool đã được cấu hình để sử dụng B**.

Vì vậy, thay biến trong Spring Environment hoặc thay `spring.datasource.password` không tự làm mới những connection vật lý đã được tạo. `@Value` trong bean hoặc thuộc tính DataSource được khởi tạo một lần cũng không tự phản ứng với mọi cập nhật của Vault.

### 5.1. Hai chiến lược phổ biến

| Chiến lược | Cách triển khai | Lợi ích | Hạn chế |
|---|---|---|---|
| **Cập nhật credential trên pool đang chạy** | Áp dụng username/password mới cho các connection tạo sau đó và `softEvictConnections()` | Ít đối tượng cần quản lý, có thể nhanh | Phụ thuộc HikariCP/driver mode; cập nhật hai field có thể thiếu tính nguyên tử; connection đang dùng vẫn mang A |
| **Tạo pool thế hệ B và chuyển reference/routing** | Tạo pool B, kiểm tra connection, chuyển luồng cấp connection mới, chờ/drain pool A | Phù hợp khi cần đổi cặp credential nguyên tử và cách ly thế hệ | Cần quản lý transaction, reference đếm số in-flight, deadline và đóng pool cũ |

Với dịch vụ cần uptime cao, **pool thế hệ mới** thường dễ kiểm soát hơn khi thay cả username lẫn password hoặc JDBC URL/TLS config. Dù chọn cách nào, cần kế hoạch cho connection đang hoạt động và thời điểm database vô hiệu hóa tài khoản cũ.

### 5.2. HikariCP: cập nhật cho connection mới và soft eviction

HikariCP cung cấp `HikariConfigMXBean` để điều chỉnh một số thuộc tính runtime và `HikariPoolMXBean.softEvictConnections()` để đánh dấu các connection cần rút khỏi pool.

Đoạn code dưới đây chỉ minh họa thao tác điều khiển trên **pool đã được xác minh hỗ trợ cập nhật username/password ở runtime**, với giai đoạn bảo trì hoặc cơ chế khóa việc mượn connection trong lúc đổi hai field:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariConfigMXBean;

public final class HikariInPlaceRotation {

    public static void changeCredentialsForNewConnections(
            HikariDataSource pool, String username, String password) {

        HikariConfigMXBean config = pool.getHikariConfigMXBean();
        config.setUsername(username);
        config.setPassword(password);

        // Idle connections bị evict; in-use connections được đánh dấu
        // để loại bỏ khi trả về pool, tùy trạng thái kết nối.
        pool.getHikariPoolMXBean().softEvictConnections();
    }
}
~~~

**Bốn giới hạn phải hiểu trước khi áp dụng:**

1. Theo contract HikariCP, việc thay `username/password` lúc đang chạy **chỉ áp dụng cho connection mở mới**; các connection đã đăng nhập bằng A không biến thành B.
2. Khả năng thay runtime này dành cho **cấu hình dựa trên `DataSource`**. Nếu pool đang dùng `jdbcUrl`/driver-class mode, không mặc định `setUsername()/setPassword()` sẽ cập nhật credential cho connection mới.
3. Gán `username` và `password` bằng hai lệnh riêng **không nguyên tử** khi nhiều thread cùng xin connection. Cần gate/suspend một cách có kiểm soát hoặc dùng thiết kế chuyển pool theo thế hệ. Không bật `suspendPool()` nếu chưa hiểu cấu hình `allowPoolSuspension` và rủi ro thread chờ vô hạn.
4. `softEvictConnections()` rút các connection idle, còn connection đang được mượn có thể tiếp tục đến lúc trả về pool. Nó **không bảo đảm không có request nào còn dùng A** tại thời điểm gọi.

HikariCP ở những phiên bản mới có thêm hỗ trợ cập nhật cặp credential qua một đối tượng chung; chỉ dùng khi **API thực sự có trong phiên bản được khóa của dự án** và driver mode hỗ trợ. Không thêm một lời gọi API từ phiên bản mới vào code Spring Boot đang dùng Hikari cũ mà chưa xác minh dependency.

### 5.3. Lựa chọn vững chắc: pool B, kiểm tra, chuyển, drain A

Mã sau minh họa **phần tạo và kiểm chứng pool mới**. Hai interface `PoolGenerationRouter` và `retireAfterDrain` là hợp đồng do **ứng dụng phải triển khai** để phân phối DataSource cho request/transaction, đếm số kết nối đang sử dụng và đóng pool cũ sau khi hoàn tất.

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.function.Supplier;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class PoolGenerationRotator {

    public interface PoolGenerationRouter {
        // Chuyển nguyên tử các lần mượn mới sang next.
        HikariDataSource promote(HikariDataSource next);

        // Chỉ đóng old sau khi không còn transaction/connection
        // nào thuộc thế hệ cũ, hoặc khi đã xử lý deadline theo policy.
        void retireAfterDrain(HikariDataSource old, Duration deadline);
    }

    private final Supplier<HikariConfig> newBaseConfig;
    private final PoolGenerationRouter router;

    public PoolGenerationRotator(
            Supplier<HikariConfig> newBaseConfig,
            PoolGenerationRouter router) {
        this.newBaseConfig = newBaseConfig;
        this.router = router;
    }

    public void rotate(String username, String password) throws SQLException {
        HikariConfig cfg = newBaseConfig.get(); // Tạo config MỚI cho mỗi lần
        cfg.setUsername(username);
        cfg.setPassword(password);

        HikariDataSource candidate = new HikariDataSource(cfg);
        try (Connection connection = candidate.getConnection()) {
            if (!connection.isValid(3)) {
                throw new SQLException("Candidate connection is invalid");
            }
        } catch (SQLException | RuntimeException ex) {
            candidate.close(); // Không thay pool nếu B chưa xác minh
            throw ex;
        }

        HikariDataSource previous = router.promote(candidate);
        if (previous != null) {
            router.retireAfterDrain(previous, Duration.ofSeconds(60));
        }
    }
}
~~~

**Mã không phải một DataSource router hoàn chỉnh:** ứng dụng phải triển khai `PoolGenerationRouter` có kiểm soát đồng thời. Chỉ đọc `getActiveConnections()==0` rồi đóng pool là **chưa đủ** nếu một thread đã lấy tham chiếu pool A nhưng chưa gọi `getConnection()`. Router cần cơ chế khóa hoặc reference counting cho cả lượt borrow đang diễn ra, transaction đang giữ connection và request đang dùng pool cũ.

Một giai đoạn retire có deadline phù hợp với thời gian transaction thực tế. Khi quá deadline, cần áp dụng chính sách rõ ràng: từ chối request mới, hủy transaction treo theo cách có kiểm soát hoặc báo sự cố. **Không đóng pool A ngay sau `promote()`** nếu còn công việc có thể sử dụng A.

Khi thay credential đồng thời với database migration hoặc policy user, kiểm tra B có đúng quyền truy vấn, transaction isolation/schema và TLS DB connection; `connection.isValid()` chỉ cho biết kết nối có thể dùng, **chưa chứng minh** role được phép thực hiện tất cả câu SQL của nghiệp vụ.

### 5.4. Thứ tự khi lease hết hạn và credential bị thu hồi

Một timeline minh họa:

| Thời điểm | Vault/database | Ứng dụng |
|---|---|---|
| T+0 | Cấp A, lease còn 30 phút | Tạo pool A, ứng dụng Ready |
| T+20 | Lease A còn hiệu lực | Theo dõi TTL, thực hiện renew nếu được phép |
| T+28 | Chuẩn bị chuyển nếu lease sắp hết hoặc yêu cầu rotate | Xin B, tạo pool B và kiểm tra kết nối |
| T+29 | A và B còn khả dụng nếu policy overlap cho phép | Request mới dùng B, transaction A được drain |
| T+30 | Lease A hết hạn hoặc Vault/database thu hồi A | Pool A phải được retire, quan sát lỗi connection cũ |
| T+31 | B tiếp tục hợp lệ | Ứng dụng chỉ cấp connection từ B |

Các mốc trong bảng chỉ mang tính khái niệm, **không phải lịch cố định của Spring Vault**. `requestRotatingSecret` có thể renew A rồi chỉ xin B sau khi lease hết hạn hoặc không còn renew được; việc tự thiết kế **overlap chủ động trước khi A hết hạn** cần cơ chế cấp B sớm tương ứng, không thể suy ra container luôn phát B trước khi A bị revoke.

Nếu role có TTL rất ngắn hoặc không hỗ trợ cấp đồng thời hai credential, ưu tiên thiết kế giảm thời gian transaction, tách worker hoặc chọn chính sách restart/switch phù hợp. Không mặc định người dùng database A tiếp tục còn hiệu lực sau khi Vault đã revoke lease.

## 6. HTTP client: bearer token hoặc API key thay đổi

Với HTTP client gọi một **dịch vụ ngoài Vault**, có hai vấn đề khác nhau:

- Nếu credentials chỉ nằm trong **header của từng request**, có thể giữ HTTP client và đọc credential mới **mỗi lần gửi**.
- Nếu credentials nằm trong **TLS handshake hoặc cấu hình connection factory** (client certificate, private key, truststore), phải tạo lại cấu hình TLS/client hoặc dùng cơ chế hot reload đã được kiểm chứng.

### 6.1. Đọc bearer token theo request bằng RestClient interceptor

Thay vì tạo một `RestClient` với `defaultHeader("Authorization", "Bearer " + tokenA)` cố định, dùng một holder có khả năng cập nhật nguyên tử:

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class PartnerTokenHolder {

    public record Credential(
            String bearerToken, Instant validUntil, long generation) {}

    private final AtomicReference<Credential> active =
            new AtomicReference<>();

    public void install(Credential candidate) {
        if (candidate == null || candidate.bearerToken() == null
                || candidate.bearerToken().isBlank()
                || candidate.validUntil() == null
                || !candidate.validUntil().isAfter(Instant.now())) {
            throw new IllegalArgumentException("Invalid credential");
        }

        active.updateAndGet(previous -> {
            if (previous != null
                    && candidate.generation() <= previous.generation()) {
                return previous; // Không cài lại event/version cũ
            }
            return candidate;
        });
    }

    public String tokenForRequest() {
        Credential snapshot = active.get();
        if (snapshot == null
                || !snapshot.validUntil().isAfter(
                        Instant.now().plusSeconds(15))) {
            throw new IllegalStateException(
                    "Partner credential unavailable or near expiry");
        }
        return snapshot.bearerToken();
    }
}
~~~

`generation` là số phiên bản **do nguồn cập nhật có thẩm quyền cung cấp hoặc ứng dụng quản lý theo thứ tự đã kiểm tra**. Không dùng timestamp máy cục bộ tùy tiện để quyết định credential nào mới hơn khi nhiều worker/POD chạy lệch đồng hồ. Thời gian `15s` chỉ là ngưỡng dự phòng minh họa; thiết kế thực tế phải dựa trên độ trễ, clock skew và policy của issuer. Đối với API key không có TTL, cần mô hình version/validity tương ứng thay vì giả định tự có `validUntil`.

Khai báo HTTP client cho partner:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerHttpClientConfiguration {

    @Bean
    PartnerTokenHolder partnerTokenHolder() {
        return new PartnerTokenHolder();
    }

    @Bean
    RestClient partnerRestClient(PartnerTokenHolder credentialHolder) {
        return RestClient.builder()
                .baseUrl("https://partner.example.invalid")
                .requestInterceptor((request, body, execution) -> {
                    // Đọc snapshot hiện hành cho CHÍNH request này.
                    request.getHeaders().setBearerAuth(
                            credentialHolder.tokenForRequest());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Khi `credentialHolder.install(...)` nhận token B, các HTTP request **bắt đầu sau đó** sẽ gắn bearer B mà không phải xây lại `RestClient`. Những request đã gửi trước đó có thể vẫn mang A vì HTTP header của chúng đã được tạo; phải phối hợp thời điểm revoke A và retry. Không dùng holder này để thay thế cách Spring Vault tự gắn `X-Vault-Token` cho `VaultTemplate`.

Nếu partner yêu cầu API key qua header tùy biến, có thể thay `setBearerAuth(...)` bằng `request.getHeaders().set("X-API-Key", credentialHolder.tokenForRequest())`, sau khi xác minh đúng contract của partner. Không đưa API key vào URL query string vì có thể bị ghi lại trong proxy/access log.

### 6.2. Vì sao retry HTTP 401 cần thận trọng?

Một request nhận HTTP `401 Unauthorized` có thể dùng bearer token A đã hết hạn. Tuy nhiên, ứng dụng cũng có thể bị từ chối do audience, scope, account disabled hoặc clock skew; retry bằng chính A thường vô ích.

Quy trình phù hợp:

1. Phân loại lỗi `401` do token hết hạn với lỗi `403` do thiếu quyền hoặc cấu hình; kiểm tra issuer, scope và môi trường.
2. Chỉ xin/đọc credential mới từ nguồn đã được xác thực; nếu cần refresh OAuth, dùng cơ chế refresh token của issuer thay vì gọi Vault login không liên quan.
3. Retry **tối đa một lần hoặc theo giới hạn**, sau khi holder đã cập nhật. Chỉ replay tự động các request an toàn/idempotent hoặc request có idempotency key và body có thể gửi lại an toàn.
4. Nếu credential mới vẫn bị từ chối, báo lỗi rõ ràng, áp dụng backoff/circuit breaker và cảnh báo; tránh vòng `401 → refresh → 401` vô hạn.

Một HTTP POST thanh toán hoặc thao tác ghi Transit/PKI có thể gây side effect; không replay tùy tiện khi client không biết server đã xử lý request cũ hay chưa.

## 7. HTTP client dùng mTLS: nạp lại SSLContext và connection pool

API key hoặc bearer token đi trong HTTP header, còn **chứng thư client mTLS** được sử dụng trong **TLS handshake**. Đây là lý do một interceptor cập nhật `Authorization` không giải quyết được certificate rotation.

Giả sử HTTP client của ứng dụng gọi một partner yêu cầu chứng thư client:

1. Lúc khởi động, JVM nạp KeyStore chứa client certificate A, private key A và truststore chứa CA của partner.
2. Apache HttpClient, JDK HttpClient, Reactor Netty hoặc HTTP client tương ứng tạo `SSLContext`/TLS engine/connection manager từ các dữ liệu đó.
3. Ứng dụng dùng connection pool, trong đó TLS sessions được tái sử dụng.
4. Sau khi Vault PKI cấp cert B, file KeyStore trên disk được thay bằng B. **HTTP client đã tồn tại có thể vẫn giữ SSLContext A và những TLS connections của A**.

Do đó, phương án đáng tin cậy nếu không có cơ chế hot-reload được kiểm chứng là:

- Cấp B và xác minh key pair, certificate chain, SAN/EKU và hạn sử dụng; đảm bảo partner **tin B**.
- Tạo **SSLContext mới** từ B cùng truststore phù hợp. Không tắt certificate verification hoặc hostname verification để “thử cho chạy được”.
- Xây **HTTP client/connection manager mới** dùng SSLContext B, gọi một endpoint kiểm tra không gây side effect.
- Chuyển tham chiếu các request **mới** sang client B theo cơ chế đồng bộ; cho request/HTTP stream của client A hoàn thành theo deadline.
- Đóng client/connection pool A sau khi drain, rồi mới rút cert A theo thời điểm được quản trị phê duyệt.

~~~mermaid
flowchart LR
    C[Vault PKI / certificate B] --> V[Validate cert + key + trust]
    V --> T[SSLContext B]
    T --> N[HTTP client B]
    N --> H{mTLS handshake + health check OK?}
    H -- Không --> X[Giữ trạng thái lỗi, điều tra; chưa switch]
    H -- Có --> S[Chuyển new requests sang B]
    S --> D[Drain HTTP client A]
    D --> R[Retire A và đóng pool]
~~~

**Thay truststore xác minh TLS server** cũng cần làm mới TLS client/SSLContext nếu runtime không hỗ trợ hot reload. Nếu chỉ đổi cert dùng cho một dịch vụ downstream, Vault client token do `SessionManager` quản lý không tự nhiên phải login lại. Ngược lại, nếu thay **chính cert dùng để đăng nhập Vault qua cert auth**, cần đảm bảo Spring Vault login mới sử dụng TLS client credential mới và xem xét ràng buộc khi renew token cũ.

### 7.1. Spring Vault CertificateContainer

Với chứng thư cấp từ Vault PKI, Spring Vault có `CertificateContainer` hỗ trợ quản lý chứng thư và việc phát hành lại khi đến hạn. Không phải mọi PKI response đều có renewable lease như database secret; **certificate rotation thường là re-issuance**. Ngay cả khi container cấp chứng thư mới, ứng dụng vẫn phải truyền nó tới `SSLContext`/HTTP client hoặc server TLS stack theo chiến lược reload riêng.

Một hệ thống sử dụng PKI có thể cần xử lý thêm OCSP/CRL, trust bundle, intermediate CA rotation, server name verification và thời gian chồng lấp. Không dùng trực tiếp `SecretLeaseContainer.requestRotatingSecret("pki/issue/...")` để suy luận rằng mọi chứng thư sẽ được tự gia hạn như database credential; hãy chọn API PKI/certificate lifecycle phù hợp.

## 8. Phối hợp Spring Cloud Vault, SessionManager và vòng đời consumer

Spring Cloud Vault có thể lấy database credential vào Spring Environment, ví dụ:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.example.internal:8200
      database:
        enabled: true
        backend: database
        role: payments-ro
        username-property: spring.datasource.username
        password-property: spring.datasource.password
      config:
        lifecycle:
          enabled: true
~~~

Đây là **ví dụ cấu hình nhận secret làm property**, đòi hỏi đúng starter/dependency, auth method và database role đã được tạo. Spring Cloud Vault tích hợp lease lifecycle, nhưng **binding credential vào `spring.datasource.*` lúc startup không đồng nghĩa DataSource/Hikari pool tự cập nhật username/password sau mỗi lease rotation**. Tài liệu Spring Cloud Vault cũng lưu ý giới hạn đối với việc lấy credential mới và cấu hình lại DataSource sau khi max lease time của database role đạt tới.

Nếu mục tiêu là **cập nhật pool ngay trong runtime**, ưu tiên thiết kế riêng được kiểm thử bằng `SecretLeaseContainer` hoặc `ManagedSecret`, một lớp điều phối thay pool và cơ chế readiness phù hợp. Việc lựa chọn giữa auto-config và cấu hình thủ công phải rõ ràng để không hai container cùng quản lý/revoke một lease.

### 8.1. Vault client token hết hạn có thể kéo theo lease

Vault database lease có quan hệ với **Vault client token đã xin secret**. Nếu session token bị revoke hoặc hết hạn tại giới hạn cuối, những lease phụ thuộc có thể bị thu hồi theo. Vì thế:

- `LifecycleAwareSessionManager` xử lý renew/re-login **Vault token**.
- `SecretLeaseContainer`/`SessionLeaseContainer` xử lý **lease secrets** và phối hợp khởi động lại việc quản lý secret khi session được cấp mới.
- `PoolGenerationRotator`/HTTP credential holder của ứng dụng xử lý **consumer đang dùng credential**.

`SessionLeaseContainer` cung cấp `getAuthenticationListener()` và `getAuthenticationErrorListener()` để liên kết với `SessionManager` trong các kiến trúc quản lý lease tương ứng. Không thể chỉ bắt một `AfterLoginEvent` rồi coi database credentials và mọi connection đã được cấp mới.

### 8.2. Khác biệt giữa database dynamic credentials và KV v2

| Hành động | Database secrets engine | KV v2 |
|---|---|---|
| Lấy dữ liệu | `database/creds/<role>` trả cặp username/password và lease | `kv-app/data/<path>` trả dữ liệu phiên bản |
| Tính thời hạn | Vault lease TTL, renewable/max TTL, revoke | KV value không tự có renewable lease kiểu database |
| Khi hết hạn | Credential có thể bị thu hồi ở database | Version cũ vẫn tồn tại trừ khi xóa/destroy theo KV policy |
| Cách nhận mới | Lease container renew/rotate hoặc app yêu cầu mới | Poll/check version hoặc nguồn notification có kiểm soát |
| Consumer | DataSource/JDBC pool | Header HTTP, cache/config, SDK của downstream |

Khi xoay một **static API key ở KV v2**, có thể đọc metadata/version và kiểm tra giá trị mới bằng `VaultTemplate.opsForVersionedKeyValue("kv-app").get("integrations/partner")`, rồi gọi `PartnerTokenHolder.install(...)` với thế hệ mới đã được xác minh. **KV v2 không tự push event cho ứng dụng chỉ vì có một write mới**. Nếu dùng các cơ chế refresh Spring Environment, phải xác minh bean/HTTP client có áp dụng giá trị mới và không chỉ cập nhật một property source.

## 9. Lỗi thường gặp khi chuyển credential

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Vault trả credential B nhưng JDBC vẫn báo `password authentication failed` | Pool mở connection mới bằng credential A hoặc dùng nhầm driver mode không hỗ trợ runtime update | Kiểm tra pool đang chạy, nguồn `DataSource`, generation và số connection; cân nhắc tạo pool B |
| Thay username/password nhưng vài request SQL lỗi ngẫu nhiên | Update hai field không nguyên tử; một số connection A bị revoke trong lúc transaction còn chạy | Chuyển theo pool generation, đồng bộ vùng transition và drain có deadline |
| Sau khi đổi mật khẩu, nhiều idle connections vẫn dùng A | Pool giữ connection vật lý đã đăng nhập | `softEvictConnections()` hoặc xây pool mới; kiểm tra tính hiệu lực của session DB cũ |
| Pool B health check thành công nhưng nghiệp vụ `permission denied` | B không có đủ quyền schema/table/transaction | Test câu SQL an toàn tương ứng role trước khi chuyển tất cả traffic |
| SecretLeaseCreatedEvent không chạy | Container chưa start, listener đăng ký muộn, RequestedSecret path sai hoặc không có quyền Vault | Kiểm tra container lifecycle, auth policy, registration và error events |
| Lease đã hết nhưng ứng dụng vẫn cấp connection A | Chỉ dựa vào callback chậm hoặc pool chưa chuyển | Theo dõi TTL/expiry tại consumer, giới hạn thời gian dùng A và fail closed khi không còn credential hợp lệ |
| HTTP trả 401 sau khi key đã xoay | Request gắn header cũ, credential holder chưa update hoặc token hết hạn | Kiểm tra nguồn dữ liệu và interceptor đọc per-request; retry có giới hạn khi an toàn |
| HTTP trả 403 dù token mới hợp lệ | Scope/audience/role của B không phù hợp | Kiểm tra quyền issuer/partner, tránh retry liên tục hoặc cấp thêm quyền tùy tiện |
| Client mTLS vẫn trình cert A | TLS context/connection pool chưa được xây lại | Tạo SSLContext/client B và switch theo generation; kiểm chứng chứng thư được partner nhận |
| TLS lỗi `PKIX path building failed` | Truststore không có CA mới của server | Cập nhật truststore, xây lại TLS client; không tắt TLS verification |
| Vault timeout trong lúc cần rotation | Không lấy được B, A gần hết TTL | Backoff/jitter, giữ trạng thái `degraded`, điều chỉnh readiness và deadline sử dụng A |
| Credential mới bị overwrite bởi event cũ | Nhiều worker/event bất đồng bộ cập nhật không theo generation | Serialize updates theo path, kiểm tra version/sequence và dùng atomic swap |
| Rotate thành công nhưng leak connection/client | Pool A hoặc HTTP connection manager không được retire | Theo dõi in-flight requests, timeout, close resource và metric số generation |

Không đồng nhất lỗi Vault login token `401/403` với lỗi database `SQLState 28P01` hoặc lỗi partner HTTP `401`: ba tầng có nguồn credential và hướng xử lý riêng. Logs nên ghi **operation phase** như `lease_fetch`, `pool_candidate_validate`, `pool_promote`, `http_send`, `tls_handshake` để rút ngắn thời gian chẩn đoán.

## 10. Giám sát và kiểm soát rủi ro

Một hệ thống rotation cần quan sát cả **sự kiện Vault** lẫn **hành vi consumer**:

| Tín hiệu | Ý nghĩa |
|---|---|
| `vault_lease_rotate_success_total` / `vault_lease_rotate_fail_total` | Có nhận được thế hệ credential mới không |
| `pool_candidate_validation_failure_total` | Credential B có dùng được để mở JDBC connection không |
| `pool_generation_active` / `pool_retiring_count` | Đang dùng bao nhiêu thế hệ pool, có pool A nào chưa drain |
| HikariCP active/idle/pending connections | Đánh giá áp lực borrow và khả năng phục vụ khi rotation |
| DB authentication failures theo loại SQLState | Phát hiện credential đã revoke, sai password hoặc quyền |
| HTTP 401/403, TLS handshake failures theo partner | Phát hiện header/token hoặc chứng thư không hợp lệ |
| Thời gian đến credential expiry / lease TTL còn lại | Xác định rủi ro hết hạn trước khi cập nhật |
| Số request/transaction còn dùng generation A | Cho biết khi nào có thể retire A |

Không ghi **password, bearer token, SecretID, private key, raw Vault lease response, header Authorization** hoặc URL có secret vào log/trace/metric label. Thay bằng những nhãn hữu hạn như `component=database|partner-http`, `phase=prepare|validate|promote|retire`, `result=ok|error`; generation có thể lưu trong log bảo vệ nhưng không dùng giá trị có độ phân biệt quá cao làm metric label.

### Readiness và xử lý lúc không có credential hợp lệ

Nếu ứng dụng chưa từng nhận credential hoặc tất cả credential đã hết hạn, không nên báo Ready cho endpoint bắt buộc database/partner hoạt động. Ngược lại, liveness không nên phụ thuộc trực tiếp vào Vault để tránh hàng loạt Pod restart trong một đợt outage. Một `SecretLeaseErrorEvent` đơn lẻ chưa chắc dịch vụ đã mất khả năng phục vụ nếu pool hiện hành vẫn dùng credential còn hạn.

Khi rotation thất bại, phân loại rõ:

- **Lỗi tạm thời:** Vault/network timeout; có thể retry có giới hạn và backoff, nhưng deadline không được vượt hạn sử dụng của A.
- **Lỗi cấu hình/phân quyền:** Vault `403` ở database credentials path, role sai, cert B sai issuer; cần sửa cấu hình, retry liên tục không có ích.
- **Lỗi consumer:** Hikari pool B không mở được connection, partner không tin cert/token B; cần rollback phần traffic đã chuyển nếu A vẫn còn hợp lệ hoặc chặn request cần thiết.
- **Credential bị thu hồi khẩn cấp:** ưu tiên không sử dụng lại A ngay cả khi có thể làm một số request thất bại; vận hành theo chính sách bảo mật.

## 11. Kế hoạch kiểm thử tích hợp

Không thể chứng minh rotation đã hoàn tất bằng cách chỉ mock `VaultTemplate.read(...)` hoặc assert rằng biến `password` thay đổi. Cần kiểm tra **kết nối mới thực sự dùng B** và connection A được retire.

### 11.1. Test cho database pool

Dùng Vault dev/Testcontainers + một database test (ví dụ PostgreSQL) có database secrets engine và role cấp credential ngắn hạn; mỗi test dùng namespace/role và dữ liệu giả:

1. **Cấp lần đầu:** Vault phát A, `SecretLeaseCreatedEvent` xuất hiện, điều phối tạo pool A và mở JDBC connection bằng A.
2. **Nhận credential B:** trigger rotation bằng thời điểm TTL/lease trong lab hoặc cơ chế rotate có kiểm soát; xác nhận event B được đọc và pool candidate B thử kết nối thành công.
3. **Chuyển traffic:** request mới mượn từ pool B; connection cũ A được drain/close sau khi transaction hoàn tất. Không assert chỉ bằng giá trị username trong config.
4. **Revoke A:** cho Vault revoke lease A; kiểm tra new borrows không còn sử dụng A, query bằng B vẫn chạy, và pool A cuối cùng đóng.
5. **Vault tạm mất kết nối:** mock failure lúc xin B; ứng dụng không cài credential null/rỗng; theo dõi readiness khi A gần hết hạn.
6. **B bị từ chối:** cấu hình role DB test khiến B không có quyền cần thiết hoặc validation fail; đảm bảo không promote pool B và ghi nhận alert.
7. **Concurrency:** tạo nhiều request/transaction đồng thời, xoay credential liên tiếp; xác minh không có cặp username/password chéo thế hệ, không leak connection và không mất request vượt ngoài chính sách.
8. **Khởi động lại Pod:** kiểm tra session token, lease và pool được tạo lại với credential của Pod mới; không serialize credential A của Pod cũ vào volume.

### 11.2. Test cho bearer token của HTTP client

Với `MockRestServiceServer` hoặc MockWebServer, tạo hai response giả:

- Cài token `fake-A` vào holder; request thứ nhất phải mang `Authorization: Bearer fake-A`.
- Cài token `fake-B` có generation lớn hơn; request thứ hai phải mang `Authorization: Bearer fake-B`.
- Thử cài lại generation cũ, đảm bảo request thứ ba vẫn dùng B.
- Khi `validUntil` đã qua hoặc quá gần ngưỡng an toàn, client không gửi token quá hạn.
- Nếu partner trả `401`, chỉ retry request an toàn theo giới hạn; `403` do scope không được quy thành “Vault phải đăng nhập lại”.

Đối với mTLS, MockRestServiceServer **không kiểm tra TLS handshake** vì HTTP được mock trong JVM. Dùng HTTPS test server có cấu hình yêu cầu client cert để xác nhận thực sự chuyển từ chứng thư A sang B, certificate chain và truststore được dùng đúng.

### 11.3. Các tiêu chí chấp nhận

| Điều kiện | Bằng chứng |
|---|---|
| Credential B được Vault cấp đúng quyền và còn hiệu lực | Lease response và/hoặc Vault audit redacted; không log secret |
| Consumer thực sự sử dụng B | JDBC connection mới/HTTP header mới/TLS certificate mới đã được xác minh |
| A không còn được dùng sau deadline | Pool A đóng, in-flight cũ kết thúc, không còn request mới dùng A |
| Sai credential B không gây traffic sai | Pool/client B bị từ chối trước khi promote |
| Không có cập nhật ngược thế hệ | Test concurrency, generation/sequence kiểm tra monotonic |
| Sự cố Vault không tạo vòng retry vô hạn | Test timeout, backoff, metric và trạng thái readiness |
| Không rò rỉ bí mật | Log/trace/CI artifacts không chứa token/password, private key hay raw response |

## 12. Checklist vận hành

- [ ] Phân loại rõ credential: Vault token, dynamic database credential, API key KV v2, bearer partner hay chứng thư mTLS.
- [ ] Xác định nguồn và thời hạn của B: lease event, KV version, token issuer hoặc PKI; không dùng callback giả định.
- [ ] Chuẩn bị consumer B **trước khi** bỏ A; validation bằng endpoint/query không gây side effect.
- [ ] Với JDBC pool, đảm bảo username/password B cùng thế hệ, connection mới không tiếp tục dùng A và transaction cũ được drain có deadline.
- [ ] Kiểm tra HikariCP mode/phiên bản trước khi dùng runtime setters; nếu không chắc, chọn chiến lược pool generation.
- [ ] Với HTTP bearer/API key, đọc credential hiện hành tại **thời điểm tạo request**; xử lý token expiry và retry an toàn.
- [ ] Với mTLS, nạp lại KeyStore/truststore, SSLContext và HTTP connection manager hoặc dùng hot reload đã được kiểm thử.
- [ ] Đặt cơ chế serialization/generation chống callback chậm cài đè credential mới bằng credential cũ.
- [ ] Không để Vault/lease callbacks chặn lâu, không thực hiện I/O nặng hoặc network retry vô hạn trong callback.
- [ ] Đảm bảo Vault client token và secret lease đều có vòng đời riêng; cấu hình re-login/lease restart khi phù hợp.
- [ ] Có metric lỗi, TTL, pool generation, in-flight và readiness; log loại sự kiện mà không log secret.
- [ ] Kiểm thử trên Vault/database/HTTPS server cô lập trước rollout; xác minh các tình huống TTL/revoke và outage.

## 13. Tổng kết

Trong **SPRING_VAULT**, xoay vòng credential chỉ hoàn tất khi **thành phần sử dụng credential thực sự được cập nhật**. `VaultTemplate`, `SecretLeaseContainer` và `ManagedSecret` giúp ứng dụng lấy secret/lease mới; JDBC pool hoặc HTTP client phải có một cơ chế riêng để chuyển sang thế hệ mới.

Với database, cập nhật thuộc tính pool thường chỉ ảnh hưởng connection mới; phương án xây pool B, xác minh, chuyển luồng cấp connection rồi drain A giúp kiểm soát đồng thời và transaction tốt hơn. Với HTTP bearer token, interceptor lấy token theo từng request có thể đủ; với client mTLS, cần làm mới TLS context và connection manager. Luôn phối hợp thời điểm revoke credential cũ, kiểm tra hậu điều kiện và bảo vệ secret khỏi log/metrics.

## Tài liệu tham khảo

- Spring Vault Reference — [Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html), gồm `SecretLeaseContainer`, `ManagedSecret`, `SessionLeaseContainer` và `CertificateContainer`.
- Spring Vault API — [`SecretLeaseContainer`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html).
- Spring Vault API — [`ManagedSecret`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/ManagedSecret.html) và [`ManagedSecret.UsernamePassword`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/ManagedSecret.UsernamePassword.html).
- Spring Vault API — [Lease events](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/package-summary.html).
- Spring Cloud Vault Reference — [Secret Backends / Database](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html).
- HikariCP — [`HikariConfigMXBean` API](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/HikariConfigMXBean.java) và [`HikariPoolMXBean` API](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/HikariPoolMXBean.java).
- Spring Framework Reference — [REST Clients (RestClient)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).
- HashiCorp Vault — [Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases) và [KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2).


