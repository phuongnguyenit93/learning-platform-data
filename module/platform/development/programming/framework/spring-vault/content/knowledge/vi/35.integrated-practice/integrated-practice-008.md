# Sử dụng thông tin cơ sở dữ liệu động qua nhiều lần xoay vòng

## 1. Mục tiêu và bối cảnh thực hành

Trong module **Spring Vault**, ứng dụng Java giao tiếp với HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, xác thực bằng danh tính workload và chỉ thực hiện thao tác được **Vault ACL policy** cấp phép. Bên cạnh KV secrets, Transit encryption và PKI, Vault **Database secrets engine** có thể tạo username/password cho PostgreSQL, MySQL và những hệ quản trị được plugin hỗ trợ. Mỗi bộ thông tin truy cập động có **lease**, thời hạn sử dụng và cơ chế thu hồi.

Đề bài **Thực hành tổng hợp** này không dừng ở việc lấy một username/password để kết nối. Ta phải duy trì một ứng dụng Spring Boot trong **nhiều vòng xoay vòng credentials**: ban đầu dùng bộ A, chuyển sang B rồi C, bảo đảm tác vụ đang chạy không bị ngắt bất ngờ và những bộ đã hết hạn được dọn đúng trách nhiệm.

Tình huống xuyên suốt: dịch vụ `orders-api` truy vấn bảng đơn hàng trong PostgreSQL bằng Vault dynamic role `orders-ro`. Vault mount tại `database/`; workload dùng Vault policy chỉ được `read database/creds/orders-ro`. Ví dụ dùng `jdbc:postgresql://postgres:5432/orders` và môi trường lab riêng, **không dùng credentials của production**.

Sau bài học, bạn có thể:

1. Phân biệt **renew lease** (kéo dài cùng tài khoản) và **rotate/issue** (nhận tài khoản mới), cũng như tác động tới connection pool.
2. Cấu hình database secrets engine, dynamic role và policy tối thiểu để thực hành nhiều thế hệ credentials.
3. Dùng `VaultOperations` nhận credentials và `SecretLeaseContainer` quản lý renewal/rotation; đọc sự kiện đúng thời điểm.
4. Thiết kế thay pool kết nối theo thế hệ `A → B → C` với bước kiểm tra trước khi kích hoạt, drain pool cũ và rollback an toàn.
5. Kiểm thử lease hết hạn, token phiên hết hạn, Vault không sẵn sàng, rollback, cleanup, quan sát metric và tác động lên hiệu năng.

> **Phạm vi:** Đây là bài lab Spring Vault + PostgreSQL trên hạ tầng thử nghiệm. Lệnh operator chỉ chạy bằng danh tính quản trị được ủy quyền; ứng dụng không được tự tạo/sửa database role. Những con số TTL ngắn nhằm nhìn thấy nhiều vòng quay trong lab, không phải cấu hình sản xuất.

## 2. Hiểu chính xác dữ liệu động và ba loại vòng đời

Dynamic database credentials được Vault tạo từ một **role** và **connection** đã cấu hình. Khi gọi endpoint `database/creds/orders-ro`, Vault có thể tạo **database user mới** và trả username, password, `lease_id`, `lease_duration`, `renewable`. Đây là endpoint HTTP `GET` có **hiệu ứng cấp phát**; mỗi lần đọc lại có thể tạo một tài khoản và lease khác.

| Hành động | Thay username/password? | Thay lease? | Ứng dụng cần làm |
|---|---|---|---|
| **Đọc lần đầu** `GET database/creds/orders-ro` | Có, nhận bộ A | Có, lease A | Tạo pool A, kiểm tra kết nối |
| **Gia hạn** lease A | Thông thường **không**, vẫn A | Cùng lease A được kéo dài nếu còn đủ điều kiện | Giữ pool A; cập nhật metadata hạn dùng |
| **Cấp mới/xoay** bằng yêu cầu mới | Có, nhận bộ B | Có, lease B | Tạo pool B; kiểm tra; chuyển traffic; đóng pool A |
| **Gia hạn** lease B | Vẫn B | Kéo dài B khi được phép | Không tạo pool mới chỉ vì renew thành công |
| **Xoay tiếp** | Có, nhận bộ C | Có, lease C | Tạo pool C và lặp quy trình chuyển thế hệ |
| **Thu hồi** lease A/B/C | Không tạo bộ mới | Vô hiệu hóa tài nguyên thuộc lease | Chỉ revoke sau khi không còn consumer hợp lệ |

### Timeline ba thế hệ

| Mốc tương đối | Vault lease | Pool đang nhận truy vấn mới | Tình trạng pool cũ |
|---|---|---|---|
| T0: khởi động | A được cấp | A | Chưa có |
| T1: renew A thành công | A kéo dài | A | Không thay đổi pool |
| T2: chủ động xin B khi A còn hạn | A và B có thể cùng tồn tại | A, chuẩn bị B | Pool A tiếp tục phục vụ |
| T3: kết nối B thử thành công | A + B | **B** | Drain những truy vấn A đang chạy |
| T4: A không còn consumer | A có thể revoke theo chính sách | B | A được đóng/revoke đúng phạm vi |
| T5: renew B hoặc hết trần TTL | B, rồi có thể cấp C | B, chuẩn bị C | Không đổi pool khi chỉ renew |
| T6: chuyển thành công sang C | C | **C** | B drain và được dọn sau đó |

```mermaid
sequenceDiagram
    participant App as orders-api
    participant Vault as Vault Database Engine
    participant PG as PostgreSQL
    App->>Vault: GET database/creds/orders-ro
    Vault->>PG: Tạo user A
    Vault-->>App: A + lease-A
    App->>PG: Pool A / SELECT thử
    Note over App: Dùng pool A
    App->>Vault: Renew lease-A
    Vault-->>App: A còn hiệu lực lâu hơn
    App->>Vault: Issue B trước khi A hết hạn
    Vault->>PG: Tạo user B
    Vault-->>App: B + lease-B
    App->>PG: Kiểm tra pool B
    Note over App: Chuyển truy vấn mới sang B, drain A
    App->>Vault: Issue C ở vòng sau
    Vault->>PG: Tạo user C
    Vault-->>App: C + lease-C
    Note over App: Chuyển sang C, dọn B
```

**Đừng nhầm khái niệm:** Database **dynamic role** phát hành user mới theo yêu cầu; **static role** quản lý một username cố định và xoay password của tài khoản đó. Bài này dùng **dynamic role**, nên ba thế hệ A/B/C thông thường có ba tên tài khoản khác nhau. Cũng không nhầm với Vault **root credential rotation** dùng để thay mật khẩu quản trị của connection đã cấu hình.

### Tại sao connection pool phải tham gia rotation?

Một connection JDBC đã mở đã được PostgreSQL xác thực từ lúc tạo kết nối. Thay giá trị `spring.datasource.password` hoặc gọi `dataSource.setPassword(...)` **không bảo đảm** các connection hiện có được xác thực lại hay một HikariCP đang chạy tự tái tạo toàn bộ pool đúng lúc. Sau khi credential cũ bị revoke/expire, những connection mới lấy bằng thông tin cũ sẽ thất bại; các phiên cũ còn hoạt động thế nào phụ thuộc database/plugin và cách revoke được thực thi.

Vì vậy, **cập nhật secret trong Spring Environment không đồng nghĩa cập nhật pool đang sử dụng**. Đối với bài lab cần quan sát nhiều vòng, ta dùng mô hình **pool theo thế hệ** (mỗi bộ credential tạo một `HikariDataSource` riêng), chuẩn bị kết nối mới trước khi chuyển traffic và đóng pool cũ sau khi không còn truy vấn.

## 3. Chuẩn bị PostgreSQL và Vault (phía operator)

### Điều kiện lab

- Vault dev/test có Database secrets engine và plugin `postgresql-database-plugin`.
- PostgreSQL test có database `orders`, bảng `public.orders` và một tài khoản **quản trị hạn chế** chuyên dành cho Vault được quyền tạo/thu hồi user động và cấp `SELECT` phù hợp. Với PostgreSQL thực, DBA cần xác định role membership/ownership/quyền tạo role phù hợp.
- Ứng dụng Java có Spring Boot, Spring Vault Core hoặc Spring Cloud Vault, PostgreSQL JDBC và HikariCP.
- Vault có thể kết nối PostgreSQL qua host `postgres:5432` trong cùng mạng lab. Đường dẫn `jdbc:postgresql://postgres:5432/orders` phía ứng dụng cũng phải trỏ tới địa chỉ có thể truy cập từ **chính nơi Java chạy**; khi chạy Java trên máy host, địa chỉ này có thể khác.

Ví dụ lệnh **operator** trên Vault lab, không dành cho token runtime:

```bash
# Bật engine một lần (bỏ qua nếu mount database đã tồn tại).
vault secrets enable database

# Tạo cấu hình connection, dùng riêng tài khoản operator của DB lab.
# Chỉ ở mạng Docker cô lập mới cân nhắc sslmode=disable.
vault write database/config/orders-pg \
  plugin_name="postgresql-database-plugin" \
  allowed_roles="orders-ro" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/orders?sslmode=disable" \
  username="$VAULT_DB_ADMIN_USER" \
  password="$VAULT_DB_ADMIN_PASSWORD"

# Role tạo một user read-only mỗi lần được gọi.
vault write database/roles/orders-ro \
  db_name="orders-pg" \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT CONNECT ON DATABASE orders TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="2m" \
  max_ttl="6m"
```

SQL tạo role trên là **ví dụ lab**, cần được DBA duyệt trước khi áp dụng. Nếu schema thay đổi hoặc hệ thống dùng nhiều schema, `GRANT SELECT ON ALL TABLES` không tự bao gồm các bảng mới tạo sau này; cần giải pháp phân quyền tương ứng. Lệnh cấu hình đưa mật khẩu vào đối số CLI (sau mở rộng shell), có thể xuất hiện ở process list/history trên một số hệ thống; môi trường sản xuất cần cơ chế nhập cấu hình bí mật an toàn và quy trình IaC đã bảo vệ.

Nếu muốn thử hồi phục khi hết hạn, phải có quyền thu hồi/renew và cấu hình database plugin hỗ trợ; **không** nên bổ sung SQL `DROP ROLE` tùy tiện nếu user đang giữ quyền hoặc có dependency khiến revocation thất bại. Kiểm tra hành vi mặc định của plugin với PostgreSQL lab và quy định của DBA.

### Policy của workload, không phải operator

Workload chỉ cần phát hành dynamic credentials:

```hcl
path "database/creds/orders-ro" {
  capabilities = ["read"]
}
```

Nếu chính ứng dụng thực hiện gia hạn một lease đã biết, cần kiểm tra quyền theo token lease owner, ví dụ capability `update` trên `sys/leases/renew`, tùy cấu hình token/ownership và policy. Nếu cần revoke chủ động, chỉ cấp đường dẫn revoke chính xác cho bộ phận quản lý vòng đời được giao quyền. Không cấp `database/config/*`, `database/roles/*` hay `auth/token/create/*` cho workload `orders-api`.

Một số hoạt động renew/revoke được Vault cho phép với lease gắn chính token và cơ chế token đã cấp; cách phân quyền chi tiết cần kiểm tra theo version/policy lab. **Không suy ra** rằng quyền `read database/creds/orders-ro` tự cho phép mọi dạng quản trị lease.

### Kiểm tra phát hành bằng Vault CLI

Chỉ chạy bằng token **thử nghiệm** được cấp đúng policy, ví dụ:

```bash
vault read database/creds/orders-ro
```

Phản hồi thường có dữ liệu tương tự (đã thay bằng placeholder):

```text
lease_id          database/creds/orders-ro/<id-A>
lease_duration    2m
lease_renewable   true
username          <generated-db-user-A>
password          <REDACTED>
```

**Cảnh báo:** Mỗi lần chạy `vault read database/creds/orders-ro` có thể cấp **một user khác**. Không dùng lệnh này như health check liên tục và không đính kèm output thật vào bài làm hoặc log CI. Dữ liệu nhạy cảm phải được che; việc kiểm tra có thể dựa trên cấu trúc response, `lease_id` và một phép kết nối SQL thử có kiểm soát.

## 4. Java: phát hành một thế hệ credentials qua VaultOperations

Phần thực hành dùng **constructor injection** để lớp tích hợp nhận `VaultOperations`. Không tạo `VaultTemplate` hoặc token Vault bên trong controller. Vault token lấy từ workload auth đã được cấu hình ở tầng hạ tầng: Kubernetes Auth, AppRole hoặc phương thức tương ứng.

### Giá trị trả về và metadata lease

Định nghĩa object nội bộ giữ bộ credentials **cùng metadata**:

```java
import java.time.Instant;

public record DbCredentialGeneration(
    String username,
    String password,
    String leaseId,
    long leaseDurationSeconds,
    boolean renewable,
    Instant observedAt
) {
    @Override
    public String toString() {
        // Không làm lộ password hay username qua log mặc định.
        return "DbCredentialGeneration[REDACTED]";
    }
}
```

`observedAt` là mốc **client đã nhận** kết quả, không phải `expireAt` có thẩm quyền của Vault. Có thể ước lượng `observedAt + leaseDuration` để lên kế hoạch cấp trước hạn; phải trừ safety window do độ trễ mạng, sai lệch đồng hồ và thời gian chuẩn bị pool.

Ví dụ adapter Java 17+:

```java
import java.time.Clock;
import java.util.Map;

import org.springframework.stereotype.Repository;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Repository
public final class VaultDatabaseCredentialIssuer {

    private static final String PATH = "database/creds/orders-ro";
    private final VaultOperations vault;
    private final Clock clock;

    public VaultDatabaseCredentialIssuer(
            VaultOperations vault, Clock clock) {
        this.vault = vault;
        this.clock = clock;
    }

    public DbCredentialGeneration issueOnce() {
        // GET này cấp credentials MỚI, không phải đọc lại KV tĩnh.
        VaultResponse response = vault.read(PATH);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                "Missing dynamic database credentials");
        }

        Map<String, Object> data = response.getData();
        Object u = data.get("username");
        Object p = data.get("password");
        String leaseId = response.getLeaseId();
        long ttl = response.getLeaseDuration();

        if (!(u instanceof String user) || user.isBlank()
                || !(p instanceof String password) || password.isBlank()
                || leaseId == null || leaseId.isBlank()
                || ttl <= 0) {
            throw new IllegalStateException(
                "Incomplete Vault lease/credential response");
        }

        return new DbCredentialGeneration(
            user, password, leaseId, ttl,
            response.isRenewable(), clock.instant());
    }
}
```

Các điểm then chốt:

1. `vault.read("database/creds/orders-ro")` có thể **tạo user mới** ở mỗi lần gọi. Method `issueOnce()` cố ý **không có `@Retryable`** và không gọi lại khi gặp lỗi thiếu response.
2. `VaultResponse.getLeaseId()`, `getLeaseDuration()` và `isRenewable()` là metadata đi kèm dynamic secret. Không lấy `lease_duration` từ nội dung KV v2.
3. Password chỉ được bàn giao cho thành phần mở kết nối. **Không** trả record này từ REST API, đưa vào message queue, log, tracing hoặc exception.
4. Phản hồi lỗi sau khi gửi request có thể xảy ra **sau khi Vault đã tạo user**. Không được mặc định kết luận “không có tài nguyên” rồi retry, vì có thể xuất hiện user/lease mồ côi. Hệ thống cần lưu trạng thái `UNKNOWN` và đối soát.
5. `Clock` chỉ hỗ trợ quyết định thời điểm ở Java. Gia hạn và hết hạn **thực tế** được Vault/database quyết định.

Spring Boot có thể cấp bean thời gian:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

### Sự khác biệt giữa nhận secret và dùng secret

Nhận được username/password từ Vault mới chứng minh **lệnh cấp phát đã trả response**. Trước khi sử dụng trong nghiệp vụ, cần tạo kết nối PostgreSQL bằng chính thông tin đó và thử **quyền SQL thực** mà role phải có, ví dụ `SELECT COUNT(*) FROM public.orders`. Nếu chỉ kiểm tra `SELECT 1`, ta chưa xác nhận user có quyền đọc bảng nghiệp vụ.

Khi việc kiểm thử kết nối hoặc khởi tạo pool **thất bại**, thế hệ mới không được công bố cho request. Tuy nhiên, Vault đã cấp resource; cần đưa lease ID vào quy trình dọn có kiểm soát, không bỏ mặc username được tạo.

## 5. Quản lý connection pool theo thế hệ

Một thiết kế dễ kiểm thử là tách ba nhiệm vụ:

- **Issuer:** chỉ gọi Vault để nhận credentials + lease (`VaultDatabaseCredentialIssuer`).
- **Pool manager:** tạo/kiểm tra pool mới và chuyển các truy vấn sang pool mới một cách đồng bộ; không tự gọi Vault.
- **Lease coordinator:** theo dõi trạng thái A/B/C, owner, thời gian, xử lý renew/cấp mới và revoke tài nguyên đã hết consumer. Không để HTTP controller trực tiếp điều khiển các thao tác đặc quyền.

```mermaid
flowchart LR
    S["Rotation coordinator"] -->|issueOnce| V["VaultDatabaseCredentialIssuer"]
    V -->|VaultOperations| B["Vault Database Engine"]
    B -->|A, B, C + lease| S
    S -->|cài pool mới| M["GenerationPoolManager"]
    M -->|Pool A| P["PostgreSQL"]
    M -->|Pool B| P
    M -->|Pool C| P
    Q["Order query service"] -->|withConnection| M
    S -->|đối soát / revoke theo lease| L["Lease lifecycle"]
```

### Ví dụ manager tạo pool mới và drain pool cũ

Đoạn Java sau minh họa cách **giữ read lock trong toàn bộ thao tác SQL**, để lúc chuyển pool không còn truy vấn đang dùng pool cũ qua manager. Một request phải gọi `withConnection(...)` cho mọi SQL thuộc transaction liên quan; nếu DAO khác giữ thẳng `HikariDataSource` cũ, manager sẽ không theo dõi được nó.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.locks.ReentrantReadWriteLock;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class GenerationPoolManager implements AutoCloseable {

    @FunctionalInterface
    public interface SqlWork<T> {
        T run(Connection connection) throws SQLException;
    }

    private record PoolGeneration(
        HikariDataSource pool, String leaseId) {}

    private final ReentrantReadWriteLock gate =
        new ReentrantReadWriteLock(true);
    private final String jdbcUrl;

    private PoolGeneration active;
    private boolean closed;

    public GenerationPoolManager(String jdbcUrl) {
        this.jdbcUrl = jdbcUrl;
    }

    public <T> T withConnection(SqlWork<T> work) throws SQLException {
        gate.readLock().lock();
        try {
            if (closed || active == null) {
                throw new IllegalStateException("Database identity not ready");
            }
            try (Connection connection = active.pool().getConnection()) {
                // Giữ lock tới khi query và connection kết thúc.
                return work.run(connection);
            }
        } finally {
            gate.readLock().unlock();
        }
    }

    public synchronized void install(
            DbCredentialGeneration credentials) throws SQLException {
        // Không giữ write lock trong lúc tạo và thử kết nối mới.
        HikariConfig cfg = new HikariConfig();
        cfg.setJdbcUrl(jdbcUrl);
        cfg.setUsername(credentials.username());
        cfg.setPassword(credentials.password());
        cfg.setMaximumPoolSize(4);
        cfg.setConnectionTimeout(5000);

        HikariDataSource candidate = new HikariDataSource(cfg);
        boolean published = false;
        PoolGeneration old = null;

        try {
            // Kiểm tra đăng nhập VÀ quyền nghiệp vụ của user mới.
            try (Connection c = candidate.getConnection();
                 PreparedStatement ps = c.prepareStatement(
                     "SELECT COUNT(*) FROM public.orders");
                 ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Database validation failed");
                }
            }

            gate.writeLock().lock();
            try {
                if (closed) {
                    throw new IllegalStateException("Already shutting down");
                }
                old = active;
                active = new PoolGeneration(
                    candidate, credentials.leaseId());
                published = true;
            } finally {
                gate.writeLock().unlock();
            }
        } finally {
            if (!published) {
                candidate.close(); // Không đưa pool hỏng vào sử dụng.
            }
        }

        // Write lock bảo đảm không còn withConnection cũ đang chạy.
        // Các truy vấn mới từ đây dùng candidate.
        if (old != null) {
            old.pool().close();
        }
    }

    @Override
    public void close() {
        PoolGeneration old;
        gate.writeLock().lock();
        try {
            closed = true;
            old = active;
            active = null;
        } finally {
            gate.writeLock().unlock();
        }
        if (old != null) {
            old.pool().close();
        }
    }
}
```

Đây là **mẫu đồng bộ hóa đơn giản cho bài lab**, không phải một thư viện quản trị datasource hoàn chỉnh. Nó giả định toàn bộ truy vấn đi qua `withConnection`, không giữ JDBC `Connection` ra ngoài lambda và không có transaction dài chạy ngoài manager. `synchronized install(...)` bảo đảm các lần cài pool mới không đè nhau trong một JVM; nếu có **nhiều instance**, từng instance phải có owner/credential riêng và điều phối theo kiến trúc phân tán phù hợp.

HikariCP hỗ trợ giới hạn connection pool, nhưng trong lúc chuyển thế hệ có thể **tồn tại đồng thời A và B**. Với `maximumPoolSize=4`, một instance có thể tạm dùng đến khoảng **8 kết nối** khi hai pool cùng sống, chưa kể kết nối quản trị của Vault và những tiến trình khác. Cần tính ngân sách kết nối PostgreSQL theo số replica, thời gian overlap và số vòng quay; không để mỗi instance tự mở quá nhiều connection khi Vault liên tục cấp tài khoản.

Trong thực tế, cần thêm:

- **Timeout drain** và ngắt/cancel query dài trước deadline; `writeLock().lock()` trong ví dụ có thể chờ vô hạn nếu query treo.
- Tái lập/cấu hình transaction manager, JPA `EntityManagerFactory` hoặc `JdbcTemplate` theo mô hình truy cập thế hệ; không tiêm thẳng một `DataSource` cũ vào các repository rồi hy vọng nó tự đổi.
- Cơ chế giữ metadata lease đầy đủ và giám sát xác nhận pool B hoạt động ổn định trước khi quyết định thu hồi A.
- Quản lý bộ nhớ và log: không in password, không dump `HikariConfig`/credential record; giới hạn truy cập tới nơi giữ secret.
- Xử lý lỗi khi candidate đã được Vault cấp nhưng tạo pool thất bại: revoke đúng lease với quyền được ủy quyền hoặc để reconciler xử lý, **không** retry cấp thêm credential một cách vô hạn.

### Truy vấn dữ liệu qua pool đang hoạt động

Ví dụ service chỉ nhìn thấy manager chứ không nhận password:

```java
// manager là GenerationPoolManager được inject vào service.
long numberOfOrders = manager.withConnection(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
             "SELECT COUNT(*) FROM public.orders");
         ResultSet result = ps.executeQuery()) {
        result.next();
        return result.getLong(1);
    }
});
```

Vì `withConnection` giữ read lock cho đến hết lambda, phép chuyển thế hệ sẽ chờ những truy vấn này kết thúc. Điều đó giảm rủi ro cắt kết nối ngay giữa tác vụ, nhưng vẫn cần database statement timeout và shutdown deadline; việc Vault revoke user A trước lúc query A xong có thể làm query lỗi dù Java chưa swap.

## 6. Điều phối A → B → C và vòng đời lease

### Hai cách xoay vòng không giống nhau

**Cách 1 — gia hạn lease hiện tại:** Nếu một lease có `renewable=true` và chưa tới trần TTL, ứng dụng có thể gọi renewal. Tài khoản A vẫn là A, password không đổi vì renewal đúng nghĩa chỉ kéo dài cùng resource. Khi đạt `max_ttl`, token bị revoke, plugin không hỗ trợ renew hoặc Vault từ chối, phải xử lý hết hạn/cấp bộ mới.

**Cách 2 — chủ động xin thế hệ mới:** Trước khi A hết hạn, ứng dụng yêu cầu `GET database/creds/orders-ro` **một lần có chủ đích** để nhận B, kiểm thử B, chuyển pool rồi dọn A. Lặp lại cho C. Đây là cách có thể xây **khoảng chồng lấn** giữa hai thế hệ và giảm nguy cơ downtime nếu hệ thống yêu cầu kết nối DB liên tục.

Ví dụ endpoint lease dùng trong quá trình vận hành, với **ID đã biết**:

```http
POST /v1/sys/leases/renew HTTP/1.1
X-Vault-Token: <workload-or-lease-owner-token>
Content-Type: application/json

{"lease_id":"database/creds/orders-ro/<exact-lease-id>","increment":120}
```

Một lần renew thành công phải được kiểm tra trên **response thực nhận**: `lease_id`, `lease_duration` và `renewable`. Không cộng cứng 120 giây vào giờ hết hạn nếu Vault chỉ cho gia hạn ít hơn hoặc từ chối do max TTL. Với lease đã biết, đây không phải thao tác `GET /database/creds/orders-ro` tạo user mới.

Trong mô hình chủ động cấp mới, hãy có một **coordinator duy nhất cho một owner instance**. Mỗi thế hệ có trạng thái:

| Trạng thái | Ý nghĩa | Hành động được phép |
|---|---|---|
| `REQUESTING` | Đã ghi ý định cấp mới, có thể đã gửi request Vault | Chỉ một worker gửi request; chưa dùng credential |
| `STAGED` | Đã có username/password/lease ID, đang tạo pool thử | Test kết nối, kiểm tra quyền SQL |
| `ACTIVE` | Pool đã được công bố cho truy vấn mới | Phục vụ nghiệp vụ, theo dõi TTL/health |
| `DRAINING` | Pool cũ không nhận truy vấn mới | Hoàn thành transaction đang dùng |
| `REVOKE_PENDING` | Consumer đã đóng, chuẩn bị revoke lease cũ | Revoke theo ID đúng và quyền phù hợp |
| `REVOKED` | Cleanup được xác nhận theo hợp đồng | Giữ metadata kiểm toán theo retention |
| `UNKNOWN` | Không biết yêu cầu issue/revoke đã hoàn tất chưa | Đối soát, **không tự retry cấp phát** |

```mermaid
flowchart TD
    A["ACTIVE A"] --> B["Ghi REQUESTING B / issue một lần"]
    B --> C{"Nhận B + lease rõ ràng?"}
    C -->|Không| U["UNKNOWN, điều tra / không resend"]
    C -->|Có| D["STAGED B: tạo pool và SELECT thử"]
    D --> E{"B hợp lệ và A còn đủ thời gian?"}
    E -->|Không| F["Giữ A nếu còn hạn; cleanup B"]
    E -->|Có| G["Swap pool sang ACTIVE B"]
    G --> H["DRAINING A, đóng connection A"]
    H --> I["Revoke A theo lease ID nếu được giao quyền"]
    I --> J["Lặp với C khi cần"]
```

**Không có transaction nguyên tử giữa Vault, PostgreSQL và cơ sở dữ liệu trạng thái ứng dụng.** Nếu Vault tạo user B thành công nhưng response bị mất, coordinator không thể biết `lease_id` để dọn ngay. Nếu đã nhận B nhưng ghi trạng thái bị lỗi, user B có thể tồn tại ngoài journal. Với hệ thống có yêu cầu audit/độ tin cậy cao, cần lưu `businessOperationId`, owner, state, lease ID (nếu có) và thời điểm vào storage bền vững, phân quyền hạn chế, kèm quy trình đối soát. Không để một `@Retryable` tổng quát nhân đôi request cấp phát.

### Pseudocode một vòng rotation

```java
// Mẫu thuật toán, không phải class Java độc lập để copy chạy ngay.
// coordinator, issuer, poolManager và leaseLifecycle là các dependency.

void rotateOneGeneration() {
    coordinator.beginSingleFlight("orders-ro");  // chống hai rotation song song

    DbCredentialGeneration candidate = null;
    try {
        // Không retry tự động nếu không nhận được response đáng tin.
        candidate = issuer.issueOnce();
        coordinator.recordStaged(candidate.leaseId(),
                                 candidate.leaseDurationSeconds());

        // Tạo pool mới và thử SELECT quyền nghiệp vụ;
        // chỉ swap khi connection mới sử dụng được.
        poolManager.install(candidate);

        // Ghi generation mới ACTIVE. Manager đã drain và đóng pool cũ.
        var previous = coordinator.confirmNewActive(candidate.leaseId());

        if (previous != null) {
            // Cleanup đúng lease cũ, không revoke theo prefix.
            leaseLifecycle.revokeOwnedLease(previous.leaseId());
        }
    } catch (Exception failure) {
        coordinator.markRotationFailedOrUnknown(candidate, failure);
        // Nếu candidate đã nhận, phải theo dõi lease để cleanup.
        // Nếu chưa nhận response, đừng mặc định request chưa tạo DB user.
        throw failure;
    } finally {
        coordinator.endSingleFlight("orders-ro");
    }
}
```

Đây là **giả mã có chủ đích**: các method `coordinator.*`/`leaseLifecycle.*` không phải API sẵn có của Spring Vault. Người triển khai phải xử lý race condition, trạng thái bền vững, timeout, transaction ordering, ID của lease cũ, partial failure và shutdown. Trong production, không suy rằng `poolManager.install(...)` rồi `confirmNewActive(...)` là atomic: nếu ghi trạng thái ACTIVE thất bại **sau khi đã swap**, phải đối soát trạng thái pool với journal chứ không cấp thêm thế hệ mới ngay.

### Khi nào bắt đầu chuẩn bị B?

Giả sử lease A có `lease_duration=120s` và pool B cần 5–15 giây để kiểm tra, chọn safety window ví dụ **40 giây** để bắt đầu chuẩn bị B. Tuy nhiên, đây chỉ là khoảng đo đạc ban đầu: Vault có thể trả TTL khác mong đợi, pool khởi động chậm khi tải cao và proxy có thể làm tăng latency.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

boolean shouldPrepareReplacement(
        DbCredentialGeneration current,
        Clock clock,
        Duration safetyWindow) {

    Instant approximateExpiry = current.observedAt()
        .plusSeconds(current.leaseDurationSeconds());

    return !clock.instant().isBefore(
        approximateExpiry.minus(safetyWindow));
}
```

Đây là function của **ứng dụng**, không can thiệp đồng hồ Vault. `observedAt()` và TTL chỉ cho thời điểm hết hạn **ước lượng**, cần dùng margin bảo thủ và luôn đọc TTL/lease status thực tế khi quan trọng. Trong unit test, dùng `Clock.fixed` để ép T0/T1/T2 thay vì `Thread.sleep`; trong integration test, Vault vẫn dùng đồng hồ thật và scheduler thật.

**Không vừa bật automatic rotation của `SecretLeaseContainer`, vừa chạy coordinator chủ động ở trên cho cùng path** mà không xác định rõ ownership. Hai thành phần cùng gọi `database/creds/orders-ro` có thể tự phát hành nhiều user/lease và tranh nhau cập nhật pool.

## 7. Lựa chọn Spring Vault SecretLeaseContainer

Nếu không tự quản lý rotation time, `SecretLeaseContainer` có thể quản lý yêu cầu cấp secret, renewal và rotation theo lease. API:

- `requestRenewableSecret("database/creds/orders-ro")`: đăng ký lấy secret và **renew** lease phù hợp; ứng dụng vẫn cần phương án khi không renew được hoặc phải thay credential.
- `requestRotatingSecret("database/creds/orders-ro")`: đăng ký secret có **chế độ rotating**; container renew lease khi đủ điều kiện và **xin secret mới sau khi lease hết hạn** theo semantics của Spring Vault.
- `LeaseListener`/`LeaseErrorListener`: nhận sự kiện ban đầu, renew, hết hạn, rotated và lỗi để cập nhật/giám sát consumer.

Sơ đồ sự kiện:

| Event | Ý nghĩa | Pool nên làm gì? |
|---|---|---|
| `SecretLeaseCreatedEvent` | Nhận secret ban đầu cùng lease | Xác thực dữ liệu và tạo pool A |
| `AfterSecretLeaseRenewedEvent` | Gia hạn cùng lease thành công | Giữ pool đang dùng, cập nhật thời hạn |
| `SecretLeaseExpiredEvent` | Container phát hiện lease đã hết hạn | Không giả định user cũ vẫn kết nối được |
| `SecretLeaseRotatedEvent` | Đã xin secret mới sau expiry | Kiểm tra và chuyển sang pool thế hệ mới |
| `SecretLeaseErrorEvent` / `LeaseErrorListener` | Lỗi API Vault hoặc network ở lifecycle | Cảnh báo, giữ trạng thái chính xác và không log secret |
| `BeforeSecretLeaseRevocationEvent` / `AfterSecretLeaseRevocationEvent` | Trước/sau yêu cầu thu hồi | Đảm bảo consumer không dùng lease cũ, đối soát backend khi cần |

### Ví dụ đăng ký listener **trước khi start**

Đoạn dưới minh họa cấu hình **thủ công** của Spring Vault Core khi `VaultOperations vault`, `TaskScheduler scheduler` và `GenerationPoolManager pool` đã có:

```java
import java.sql.SQLException;
import java.util.Map;

import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;
import org.springframework.vault.core.lease.event.SecretLeaseRotatedEvent;

// Mảnh mã khởi tạo, không đặt trong controller/request handler.
SecretLeaseContainer leases = new SecretLeaseContainer(vault, scheduler);
RequestedSecret subscription =
    leases.requestRotatingSecret("database/creds/orders-ro");

leases.addLeaseListener(new LeaseListenerAdapter() {
    @Override
    public void onLeaseEvent(SecretLeaseEvent event) {
        if (!subscription.equals(event.getSource())) {
            return;
        }

        if (event instanceof SecretLeaseCreatedEvent created) {
            // SecretLeaseRotatedEvent là subclass của CreatedEvent.
            Map<String, Object> secrets = created.getSecrets();

            // KHÔNG log secrets. Chuyển vào một worker tuần tự có queue
            // giới hạn, rồi kiểm tra schema/lease và xây pool mới.
            // credentialHandoff.enqueue(event.getLease(), secrets);
            if (event instanceof SecretLeaseRotatedEvent) {
                // metric: một lần rotate thực sự (khác renewal).
            }
        }
    }

    @Override
    public void onLeaseError(SecretLeaseEvent event, Exception error) {
        if (subscription.equals(event.getSource())) {
            // metric/alert theo loại lỗi, không log response chứa secret.
        }
    }
});

leases.afterPropertiesSet();
leases.start();   // Listener đã gắn trước sự kiện ban đầu.
// Khi ngừng ứng dụng, để Spring gọi destroy() ở lifecycle owner.
```

Mã trên minh họa **API/lifecycle của container**, **chưa là ứng dụng chạy độc lập**: `credentialHandoff` phải được hiện thực, tạo pool phải được điều phối trên executor có giới hạn, payload secret và lease cần được kiểm tra trước khi đưa vào manager. Không làm việc chờ DB nhiều giây ngay trên thread phát sự kiện của `SecretLeaseContainer`; điều đó có thể cản trở lịch renew/rotation. Listener được đăng ký trước `start()` vì đăng ký sau có thể bỏ lỡ sự kiện credentials đầu tiên.

**Quan trọng về availability:** Chế độ `requestRotatingSecret` có thể **xin secret mới sau khi lease cũ hết hạn**, nên không tự bảo đảm A và B cùng còn hợp lệ để thực hiện một cutover không gián đoạn. Muốn overlap chủ động trước hết hạn, cần tự xây coordinator phát hành sớm như mục 6 hoặc sử dụng hạ tầng rotation có hợp đồng cung cấp overlap cụ thể. Đừng hứa zero downtime chỉ bằng cách bật `requestRotatingSecret`.

Trong Spring Vault **4.1 trở lên**, `ManagedSecret.rotating(...)` là lựa chọn API cấp cao hơn để nhận giá trị secret và đẩy vào consumer; việc đăng ký bean phải diễn ra đúng lifecycle. Ví dụ tài liệu có thể cập nhật username/password trên Hikari datasource, nhưng **cập nhật setter không tương đương với bảo đảm mọi connection trong pool đang chạy được thay thế an toàn**. Cần kiểm thử thực tế việc chuyển connection, transaction và giới hạn TTL; với yêu cầu chặt, mô hình pool theo thế hệ thường dễ lý giải hơn.

Khi dùng **Spring Cloud Vault**, nó có thể tự cấu hình database secret backend và lease lifecycle. Ví dụ:

```yaml
spring:
  cloud:
    vault:
      database:
        enabled: true
        backend: database
        role: orders-ro
        username-property: spring.datasource.username
        password-property: spring.datasource.password
```

Cần dependency Spring Cloud Vault **database backend** tương thích release train, cấu hình bootstrap `spring.config.import` theo phiên bản và workload auth đúng môi trường. Đoạn này cho thấy cách lấy credentials làm property để khởi tạo datasource; **không nên khẳng định property mới tự động thay mọi JDBC connection**. Nếu ứng dụng tự cấu hình cả `SecretLeaseContainer` và Spring Cloud Vault lifecycle cho cùng role, phải xác định một owner duy nhất hoặc loại bỏ đăng ký trùng.

## 8. Thực hành ba vòng A → B → C có thể kiểm chứng

Để kiểm tra các yêu cầu trên mà không chờ hàng giờ, lab dùng **mỗi lần issue một thế hệ riêng**. Giữ username/password và lease ID trong bộ nhớ hoặc storage **chỉ dành cho test**, không ghi ra console. Mỗi lần chỉ phát hành khi có quyết định rõ ràng của test/coordinator, không dùng `@Retryable` để chờ username mới.

### Giai đoạn A: khởi động

1. Operator chuẩn bị PostgreSQL, bảng `public.orders`, Vault connection/role `orders-ro` và Vault policy hẹp.
2. `orders-api` đăng nhập Vault qua workload auth; `VaultOperations` truy cập `database/creds/orders-ro`.
3. Issuer nhận bộ A: `username-A`, `password-A`, `lease-A`, `lease_duration-A`.
4. Manager tạo pool A bằng bộ A, kiểm tra `SELECT COUNT(*) FROM public.orders`, sau đó mở readiness cho truy vấn.
5. Lưu metadata A ở trạng thái `ACTIVE`, theo dõi thời hạn gần hết và sức khỏe database. Không log password hoặc response đầy đủ.

### Giai đoạn A-renew: chứng minh gia hạn không phải xoay

Nếu lease A cho phép renew, operator hoặc lease manager được ủy quyền gửi `sys/leases/renew` theo **lease ID A** và quan sát response thực tế. Các kiểm tra cần có:

- Lease được gia hạn hoặc Vault trả lỗi đúng chính sách.
- Nếu gia hạn thành công, username/password vẫn thuộc **thế hệ A** và không mở pool mới chỉ vì event renewal.
- Cập nhật `lease_duration`/thời điểm dự kiến theo response; không tự cộng TTL yêu cầu một cách mù quáng.
- Không gọi `database/creds/orders-ro` trong nhánh chỉ muốn renew.

Việc gia hạn có thể bị giới hạn bởi `max_ttl` của database role, thời hạn token chủ sở hữu hoặc chính sách Vault. Nếu không renew được, coi đây là tín hiệu cần **chuẩn bị thế hệ mới** theo quy trình, không tiếp tục dùng credentials quá hạn.

### Giai đoạn B: thay thế có overlap

1. Trước khi A hết hạn, coordinator xác nhận không có rotation khác đang chạy và ghi ý định cấp B.
2. Gọi `issueOnce()` một lần để nhận B; ghi `lease-B` ngay khi có phản hồi đáng tin.
3. Tạo pool B, kiểm tra kết nối và quyền `SELECT` khi A vẫn phục vụ.
4. Nếu B hợp lệ, chuyển các truy vấn mới sang pool B; chờ các SQL operation cũ dùng A hoàn thành rồi đóng pool A.
5. Chỉ sau khi xác nhận A không còn consumer, gửi yêu cầu revoke A nếu owner/chính sách cho phép. Nếu Vault unavailable ở bước này, ghi `REVOKE_PENDING` để đối soát; không mở rộng quyền tùy tiện.

**Quan sát:** username B phải đại diện bộ credentials **được phát hành mới**; không dùng username A như khóa so sánh duy nhất cho correctness. Hãy kiểm tra lease ID A và B **khác nhau**, pool query thành công và không có truy vấn mới dùng A sau cutover.

### Giai đoạn C: thêm một lần xoay, chứng minh thiết kế lặp được

Lặp đúng quy trình B đối với thế hệ C; trước khi C được công bố, B vẫn là active nếu còn hợp lệ. Sau khi chuyển thành công, B trở thành draining rồi được cleanup. Khi đã xong ba thế hệ, test cần kiểm tra:

| Thuộc tính | Kết quả mong đợi |
|---|---|
| Số lần phát hành chủ đích | **3**: A, B, C (không cộng renewal) |
| Số thế hệ active ở cuối | **1**: C |
| Lease ID | `lease-A`, `lease-B`, `lease-C` được theo dõi riêng |
| Truy vấn tại T0/T3/T6 | Thành công với active pool tương ứng |
| Renewal A hoặc B | Không tăng số lần cấp dynamic username |
| Tài nguyên cũ sau drain | Pool A/B đã đóng; lease cleanup được yêu cầu đúng ID nếu thuộc quyền sở hữu |
| Khi cleanup chưa xác nhận | Có trạng thái `REVOKE_PENDING/UNKNOWN`, không báo success giả |
| Log/test report | Không chứa password, Vault token, private key hoặc full secret payload |

### Pseudocode thực hiện ba vòng trong integration test

```java
// issuer, manager, cleanupRegistry và vault đã được khởi tạo trong lab.
// Code minh họa, cần thêm asserts và quyền cleanup trong test harness.

DbCredentialGeneration previous = null;
try {
    for (int generation = 1; generation <= 3; generation++) {
        DbCredentialGeneration current = issuer.issueOnce();
        cleanupRegistry.registerOwnedLease(current.leaseId());

        manager.install(current);

        long count = manager.withConnection(connection -> {
            try (var stmt = connection.prepareStatement(
                     "SELECT COUNT(*) FROM public.orders");
                 var rows = stmt.executeQuery()) {
                rows.next();
                return rows.getLong(1);
            }
        });
        assertTrue(count >= 0);

        if (previous != null) {
            // Manager đã đóng pool cũ sau khi drain.
            cleanupRegistry.revokeOwnedLease(previous.leaseId());
        }
        previous = current;
    }
} finally {
    // Đóng consumer trước rồi cleanup lease chính xác của từng thế hệ.
    manager.close();
    cleanupRegistry.revokeRemainingOwnedLeases();
}
```

Các phương thức `cleanupRegistry.*` là **hợp đồng của test harness**, không phải API được Spring Vault cung cấp. Hệ thống thật phải tính thêm giới hạn thời gian, quyền revoke, journal và phản hồi mất xác nhận. Ví dụ không gọi `revoke` trước khi `manager.close()` hoặc `manager.install(...)` đã bảo đảm không còn consumer dùng lease đó. **Không thực hiện vòng lặp này trên database production**: mỗi vòng là một lần cấp user thật.

## 9. Thứ tự thu hồi và shutdown sau nhiều vòng

Với dynamic secret, owner của lease cần phân biệt **tài nguyên thuộc instance** với tài nguyên do service khác/quản trị viên sử dụng. Khi làm rolling update, pod A chỉ dọn lease của chính nó; pod B/C có thể có credential khác và không được bị ảnh hưởng.

Đối với manager chủ động cấp nhiều thế hệ:

1. **Ngừng cấp request mới** và chặn coordinator issue generation tiếp theo.
2. **Drain truy vấn** trong deadline, đóng toàn bộ pool/connection thuộc instance.
3. Với các lease đã lưu **đúng ID**, gửi revoke bằng owner có quyền hoặc giao cho component quản lý lease; không dùng `revoke-prefix` trên cả role.
4. **Kết thúc Vault session/token** sau các thao tác cần xác thực. Không revoke parent token dùng chung của nhiều worker.
5. Nếu mạng/permission khiến revoke thất bại, ghi trạng thái và chuyển sang reconciliation; reliance vào TTL cần đi kèm kiểm tra hậu quả ở database backend.

Một số lệnh để operator **quan sát và cleanup trong lab**, chỉ thực hiện khi ID đã xác nhận:

```bash
# Không tạo resource mới: chỉ tra cứu lease A đã biết.
vault lease lookup "<exact-lease-A>"

# Gia hạn lease đã biết, khi đúng quyền và điều kiện.
vault lease renew "<exact-lease-A>"

# Sau khi pool A đã đóng và không còn consumer:
vault lease revoke "<exact-lease-A>"
```

Nếu dùng `SecretLeaseContainer` do Spring quản lý, `stop()` chỉ dừng renewal/rotation mà **không thu hồi active leases**; `destroy()` là đường vòng đời thực hiện cleanup các lease nó quản lý. Đừng dùng cả container và cleanup thủ công với cùng lease mà không xác định rõ ownership. Để framework đóng đúng thứ tự: dừng công việc, đóng consumer, rồi mới để lease container và session manager hoàn tất lifecycle.

### Không lạm dụng TTL và thu hồi

- Vault cố gắng revoke credentials khi lease hết hạn; nếu PostgreSQL không sẵn sàng hoặc SQL revoke thất bại, user ngoài database có thể tồn tại lâu hơn kỳ vọng.
- Thu hồi credential **không tự động bảo đảm** kết thúc tức thì mọi session PostgreSQL đã xác thực trước đó. Kiểm tra plugin/SQL policy và nếu cần kết thúc session phải phối hợp với DBA.
- Không vì thấy “credential A vẫn đăng nhập được” mà cấp thêm B, C, D qua retry vô hạn; phải kiểm tra pool nào đang dùng A và trạng thái Vault/backend.
- Rotation có thể làm tăng số database connections tạm thời. Quy hoạch connection budget trước khi tăng số replica hoặc giảm TTL.

## 10. Lỗi, khả năng phục hồi và fallback an toàn

| Sự cố | Trạng thái đúng | Hành động |
|---|---|---|
| Vault HTTP 403 khi issue | Không đủ quyền hoặc auth sai | Kiểm tra workload identity, Vault policy và role; không dùng root token |
| Vault 429/5xx hoặc timeout trước khi nhận B | **UNKNOWN** nếu request có thể đã tới Vault | Không retry phát hành tự động, đối soát và giới hạn thời gian |
| Vault đã trả B nhưng pool B kiểm tra SQL lỗi | A vẫn active nếu còn hạn; B là resource đã được cấp | Đóng candidate, theo dõi và revoke lease B đúng quyền; không swap |
| Pool B ổn, nhưng đổi trạng thái journal lỗi | Runtime có thể đã chuyển sang B | Đối soát pool/current generation và journal; không cấp C ngay |
| A hết hạn khi B chưa sẵn sàng | Không còn credential đảm bảo dùng được | Readiness không sẵn sàng, trả lỗi phụ thuộc rõ ràng hoặc chờ phục hồi theo deadline |
| Lease renewable đạt `max_ttl` | Không thể renew vô hạn | Chủ động lên kế hoạch thế hệ tiếp theo trước hạn |
| Token Vault của workload hết hạn | Có thể mất quyền renew/issue/revoke | Kiểm tra SessionManager và login/re-auth; không thay bằng token quản trị |
| Role PostgreSQL không có `SELECT` | Candidate B không vượt test quyền | DBA/Vault operator sửa role, giữ A nếu còn hạn |
| Revoke lease A trả lỗi | Cleanup chưa xác nhận | Ghi `REVOKE_PENDING`, đối soát, không tuyên bố user A đã biến mất |
| Pool mới làm tổng connection vượt giới hạn PostgreSQL | Candidate không thể mở đủ kết nối | Giới hạn pool, số replica và overlap; rollback/điều chỉnh capacity |
| Scheduler xoay và operator-trigger cùng lúc | Hai generation được phát hành | Single-flight/ownership hoặc chỉ một cơ chế rotation duy nhất |

### Fallback khi không còn credential hợp lệ

Một câu trả lời vận hành tốt không phải “cứ sử dụng pool cũ cho đến khi Vault hồi phục” trong mọi tình huống. Nếu lease của pool cũ đã bị revoke hoặc PostgreSQL từ chối xác thực, tiếp tục truy vấn bằng credential đó sẽ tạo lỗi/độ trễ và có thể làm cạn connection pool. Phải chuyển trạng thái readiness xuống, dùng circuit breaker/backoff để tránh đè tải lên Vault/backend, và khôi phục theo quy trình có kiểm soát.

Nếu thiết kế phải có **zero downtime** nghiêm ngặt, cần đánh giá tính khả thi của overlap, max TTL và khả năng downstream duy trì quyền đồng thời; có thể phải điều chỉnh TTL, mở pool mới sớm hơn, hoặc dùng một tầng connection proxy/identity chuyên dụng. `SecretLeaseContainer` tự động không cung cấp bảo đảm “không mất một request” cho mọi database và mọi plugin.

## 11. Quan sát nhiều lần xoay vòng

Các số đo cần giúp phân biệt **renew** với **issue/rotate** và chứng minh old pool đã được drain:

| Metric đề xuất | Nội dung | Nhãn phù hợp |
|---|---|---|
| `vault_db_credentials_issued_total` | Lần cấp credentials mới được xác nhận | `role`, `outcome` |
| `vault_db_lease_renew_total` | Lần renew cùng lease | `role`, `outcome` |
| `db_pool_generation_active` | Có thế hệ pool sẵn sàng phục vụ | `role`, `state` |
| `db_pool_rotation_duration_seconds` | Thời gian tạo, kiểm tra và swap pool | `phase`, `outcome` |
| `db_pool_rotation_failures_total` | Thất bại trong quá trình chuẩn bị/swap | `reason` |
| `db_old_generation_drain_seconds` | Thời gian chờ hoàn tất truy vấn pool cũ | `role` |
| `vault_db_lease_cleanup_total` | Trạng thái revoke lease đã biết | `outcome` |
| `vault_db_issuance_unknown_total` | Request có thể đã tạo credential nhưng mất xác nhận | `role` |
| `db_connection_acquire_duration_seconds` | Độ trễ lấy connection qua pool | `pool_state` |

Các metric này là **tên gợi ý**, không phải metric mặc định của Spring Vault/Hikari. Tránh label có cardinality cao hoặc bí mật: không đưa username, password, `lease_id`, Vault token hay JDBC URL có credential vào metric/log. Truy vết nội bộ có thể dùng một generation number hoặc correlation ID đã chuẩn hóa; lease ID chỉ nên lưu trong metadata bảo vệ của operator nếu cần đối soát.

Ví dụ log **không nhạy cảm** cho lab:

```text
db_credential_event phase=issued generation=1 role=orders-ro result=ok
db_lease_event phase=renew generation=1 role=orders-ro result=ok
db_credential_event phase=issued generation=2 role=orders-ro result=ok
db_pool_event phase=validate generation=2 result=ok
db_pool_event phase=swap from=1 to=2 result=ok
db_pool_event phase=drain generation=1 remaining=0
db_credential_event phase=issued generation=3 role=orders-ro result=ok
db_pool_event phase=swap from=2 to=3 result=ok
db_lease_cleanup_event generation=2 result=accepted
```

Không coi `result=accepted` của revoke API luôn bằng “DB user đã hoàn toàn biến mất”; nếu cần mức chứng minh đó, tích hợp một bước xác minh backend có deadline và quyền riêng. Khi kết quả không rõ, gắn `UNKNOWN` thay vì báo động sai hoặc tự xóa tên user theo suy đoán.

## 12. Kiểm thử tích hợp và nghiệm thu nhiều thế hệ

### Hai tầng test không thể thay thế nhau

**Unit test** với fake issuer và fake pool kiểm tra việc gọi `install` đủ ba thế hệ, chỉ một active pool, trạng thái rollback và lịch kích hoạt rotation. Có thể inject `Clock.fixed(...)` để quyết định khi nào cần B mà không phải chờ thật.

**Integration test** cần Vault thật với Database secrets engine và PostgreSQL test: phải quan sát user/lease **thật**, kết nối SQL thực sự và hậu quả khi credential bị thu hồi hoặc hết hạn. Chỉ mock `VaultOperations.read(...)` không xác minh role SQL, ACL, TTL hay database connection.

Môi trường thử nên tạo bằng Testcontainers hoặc Docker Compose dành riêng cho suite, với mạng nội bộ cho Vault ↔ PostgreSQL ↔ test app. Nếu dùng Testcontainers Vault ở chế độ dev, root token chỉ dành cho bootstrap fixture; phần test workload phải dùng token policy hẹp. Không dán root token hoặc database password lab thật vào CI log.

### Ma trận test bắt buộc

| Trường hợp | Kỳ vọng |
|---|---|
| Khởi động với A | Cấp đúng một lease; `SELECT COUNT(*)` qua pool A thành công |
| Renew A thành công | Vẫn username A, không tạo pool/lease generation mới |
| A đạt max TTL / không renewable | Có kế hoạch cấp B, không gọi renew vô hạn |
| Issue B khi A còn hạn | Có lease B độc lập; pool A tiếp tục phục vụ khi B đang được kiểm thử |
| Kiểm thử B thành công | Cắt sang B; truy vấn mới dùng B; A không còn consumer trước cleanup |
| B thiếu quyền `SELECT` | Không công bố B; A tiếp tục nếu còn hợp lệ; lease B không bị bỏ quên |
| Issue C và cutover lần nữa | Pool C active, B đã drain; A/B không bị dùng cho truy vấn mới |
| Hai lời gọi rotation đồng thời | Single-flight chỉ chấp nhận một lần cấp phát có chủ đích |
| Vault timeout **sau khi phát hành** | Trạng thái `UNKNOWN`; không resend tự động gây user dư |
| Vault 403 / token hết hạn | Lỗi auth/policy rõ ràng; không dùng root token fallback |
| Database outage trong lúc chuẩn bị B | Candidate lỗi, pool A không bị đóng sớm; readiness phụ thuộc hạn A |
| Revoke A sau khi pool A đóng | Backend nhận cleanup theo lease A, không ảnh hưởng B |
| Revoke A trước khi drain trong lab | Test chứng minh vì sao thao tác này có thể làm request lỗi |
| Vault không sẵn sàng khi cleanup | Ghi `REVOKE_PENDING`, không khẳng định tài nguyên đã biến mất |
| Restart/rolling update nhiều replica | Mỗi instance quản lý lease riêng, không revoke lease của replica khác |
| Quá hạn rotation deadline | Ứng dụng có cảnh báo/readiness phù hợp, không giữ credential đã biết bị revoke |

### Test logic thời gian bằng Clock cố định

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import org.junit.jupiter.api.Test;

class RotationWindowTest {

    @Test
    void startsPreparingReplacementBeforeExpiry() {
        Clock base = Clock.fixed(
            Instant.parse("2032-06-01T10:00:00Z"), ZoneOffset.UTC);

        DbCredentialGeneration lease = new DbCredentialGeneration(
            "fake-user", "test-only", "fake-lease", 120, true,
            base.instant());

        // Bắt đầu 40 giây trước hạn dự kiến.
        Instant before = Instant.parse("2032-06-01T10:01:19Z");
        Instant threshold = Instant.parse("2032-06-01T10:01:20Z");

        assertFalse(shouldPrepareReplacement(
            lease, Clock.fixed(before, ZoneOffset.UTC),
            Duration.ofSeconds(40)));

        assertTrue(shouldPrepareReplacement(
            lease, Clock.fixed(threshold, ZoneOffset.UTC),
            Duration.ofSeconds(40)));
    }
}
```

`shouldPrepareReplacement` là hàm ví dụ trong mục 6; đưa vào class/service tương ứng khi hiện thực. `Clock.fixed` chỉ điều khiển **logic Java**, không thể làm Vault thật hết hạn lease theo ý muốn. Test TTL/renew/revoke thực tế cần polling có deadline (chẳng hạn Awaitility), không dựa vào một `Thread.sleep` cố định rồi khẳng định cleanup chắc đã xong.

### Test lỗi khó nhất: Vault xử lý thành công nhưng mất response

Một fault-injection test có giá trị cần tái hiện chính xác:

```text
T0  Journal ghi REQUESTING(B), chỉ một worker được phép issue.
T1  App gửi GET /database/creds/orders-ro.
T2  Vault tạo user B + lease B trong PostgreSQL.
T3  Proxy drop response, app nhận read timeout.
T4  Journal đánh dấu UNKNOWN(B); pool A vẫn phục vụ nếu còn hạn.
T5  Scheduler/queue phát lại trigger rotation.
T6  App nhận ra UNKNOWN, không gửi thêm GET cấp user C ngoài ý muốn.
T7  Operator đối soát user B/lease B theo audit/backend test.
```

Nếu bài test chỉ ngắt kết nối **trước khi Vault nhận request**, nó chưa kiểm tra trường hợp khó là **đã tạo user nhưng client không biết kết quả**. Không có idempotency key mặc định ở `database/creds` để bảo đảm resend trả đúng B. Việc chờ lease hết hạn/thu hồi lại cần quan sát backend thực, vì một hệ thống ngoài có thể bị sự cố cleanup.

### Điều kiện nghiệm thu cuối bài

Để kết luận lab thành công, học viên cần xuất trình **bảng thế hệ không chứa bí mật**:

| Thế hệ | Đã issue? | Đã kiểm thử SQL? | Đã ACTIVE? | Đã drain/đóng pool? | Kết quả cleanup |
|---|---|---|---|---|---|
| A | Có | Có | Có, trước B | Có, sau B | Accepted / Pending |
| B | Có | Có | Có, trước C | Có, sau C | Accepted / Pending |
| C | Có | Có | Có, cuối lab | Khi shutdown | Accepted / Pending |

Những mục `Pending` phải có người nhận xử lý và deadline; không đánh dấu `REVOKED` nếu chưa xác minh được. Cần kèm bằng chứng test quyền SQL, renew không cấp generation mới, rollover hai lần liên tiếp và ít nhất một bài test thất bại khi candidate không dùng được.

## 13. Checklist trước khi đưa ra môi trường thật

1. **Cơ sở dữ liệu:** một tài khoản Vault DB admin riêng, quyền tạo/thu hồi user hợp lý, SQL role được DBA duyệt và connection TLS được kiểm chứng.
2. **Vault role:** dynamic role giới hạn quyền/TTL; `default_ttl`, `max_ttl` và khả năng renew có kế hoạch; không hardcode DB password trong ứng dụng.
3. **Vault auth/ACL:** workload identity hợp lệ, `read database/creds/orders-ro` đúng path; lease renew/revoke do owner đã được cấp quyền thực hiện.
4. **Pool thế hệ:** ứng dụng biết rõ nơi giữ connection, có kết nối thử trước cutover, chờ truy vấn cũ và đóng pool cũ; JDBC/JPA/transaction không bypass manager.
5. **Nguồn rotation duy nhất:** không bật đồng thời hai cơ chế issue/rotate cho cùng role và cùng owner nếu chưa thiết kế điều phối.
6. **Tính sẵn sàng:** chuẩn bị trước expiry nếu cần overlap; có safety window, connection timeout, statement timeout và readiness/circuit breaker phù hợp.
7. **Idempotency:** mỗi lần phát hành có intent/state; request mất response được ghi `UNKNOWN` thay vì retry mù quáng.
8. **Cleanup:** lease ID/owner được lưu an toàn, revoke sau khi hết consumer, không dùng `revoke-prefix` diện rộng và có đối soát cho cleanup lỗi.
9. **Quan sát:** phân biệt issue với renew, đo thời gian mở pool, drain, tài nguyên còn lại; không log mật khẩu/token/lease ID công khai.
10. **Kiểm thử:** qua đủ A, renew A, B, C, lỗi kết nối, Vault timeout, token hết hạn, rolling update và cleanup trên Vault/PostgreSQL test.

## Tổng kết

**Sử dụng thông tin cơ sở dữ liệu động qua nhiều lần xoay vòng** nghĩa là quản lý **cả chu kỳ A → B → C**, không chỉ thay mật khẩu trong biến môi trường. Vault chịu trách nhiệm cấp credentials, lease và thu hồi theo engine; Spring Vault cung cấp `VaultOperations` và các cơ chế renewal/rotation; ứng dụng phải đảm bảo **pool mới được thử thành công trước khi chuyển tải, pool cũ hoàn tất công việc trước khi bị thu hồi, và các yêu cầu cấp mới không bị nhân đôi khi gặp lỗi**.

Với ứng dụng phải duy trì truy vấn liên tục, hãy ưu tiên xác định ranh giới ownership và khả năng overlap ngay từ thiết kế. Nếu không bảo đảm được chuyển đổi liên tục khi lease hết hạn, hệ thống phải **báo trạng thái không sẵn sàng một cách trung thực** thay vì tiếp tục dùng credential đã biết không hợp lệ.

## Tài liệu tham khảo chính thức

1. [HashiCorp Vault — Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases): dynamic/static roles, lease, plugin và thu hồi.
2. [HashiCorp Vault — PostgreSQL plugin](https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql): `postgresql-database-plugin`, connection và `creation_statements`.
3. [HashiCorp Vault — Database secrets engine API](https://developer.hashicorp.com/vault/api-docs/secret/databases): role, `GET /database/creds/<role>` và các tham số TTL.
4. [HashiCorp Vault — Lease, renew and revoke](https://developer.hashicorp.com/vault/docs/concepts/lease): lease ID, renewability, TTL và thu hồi.
5. [Spring Vault — Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html): `SecretLeaseContainer`, request rotating/renewable, events và cách đăng ký listener.
6. [Spring Vault — SecretLeaseContainer Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html): lifecycle, `requestRotatingSecret`, `stop` và `destroy`.
7. [Spring Vault — SecretLeaseCreatedEvent](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/SecretLeaseCreatedEvent.html) và [SecretLeaseRotatedEvent](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/SecretLeaseRotatedEvent.html): payload secret và lease khi cấp/rotate.
8. [Spring Vault — VaultOperations Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html): API đọc dynamic secret từ Java.
9. [Spring Cloud Vault — Database secret backends](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html): tự động materialize credentials làm property JDBC và cấu hình role.
10. [HikariCP — GitHub documentation](https://github.com/brettwooldridge/HikariCP): quản lý connection pool, timeout và sizing.
