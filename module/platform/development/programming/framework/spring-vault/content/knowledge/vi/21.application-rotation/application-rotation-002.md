# Ứng dụng tiếp nhận dữ liệu từ sự kiện lease

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot kết nối PostgreSQL bằng tài khoản động do HashiCorp Vault cấp. Mật khẩu có hạn sử dụng và có thể thay đổi khi Vault gia hạn, xoay vòng hoặc cấp một **secret mới**. Nếu Spring Vault đã nhận credential mới nhưng connection pool vẫn giữ username/password cũ, yêu cầu nghiệp vụ có thể thất bại khi Vault thu hồi tài khoản cũ. Vì vậy, xoay vòng có **hai nửa**: Vault quản lý vòng đời secret, còn **ứng dụng phải tiếp nhận và áp dụng dữ liệu mới vào thành phần đang sử dụng**.

Trong module **SPRING_VAULT**, Spring Vault cung cấp `VaultTemplate` để gọi Vault với danh tính workload và policy phù hợp. `SecretLeaseContainer` theo dõi lease; các callback như `LeaseListener` cho phép ứng dụng phản ứng khi secret được cấp, renew hoặc rotate. Bài thuộc chương **Xoay vòng trong ứng dụng**, tập trung vào **cách nhận dữ liệu trực tiếp từ sự kiện lease**, đặc biệt `SecretLeaseCreatedEvent.getSecrets()` và `SecretLeaseRotatedEvent.getSecrets()`.

Sau bài học, bạn có thể:

1. Phân biệt **Vault server**, `SecretLeaseContainer`, **event** và thành phần tiêu thụ secret trong ứng dụng.
2. Đăng ký `RequestedSecret` chế độ *rotating*, đăng ký listener trước khi start container.
3. Đọc đúng `event.getSource()`, `getSecrets()`, `getLease()` và nhận diện event tạo mới, gia hạn, hết hạn, lỗi.
4. Đưa credential mới vào cấu hình chạy thực tế, xử lý trạng thái ứng dụng trước và sau rotation.
5. Thiết kế kiểm thử tích hợp, giới hạn log và xử lý lỗi khi Vault token hoặc lease hết hiệu lực.

## 2. Mô hình sự kiện và ai phát sự kiện?

**Vault không chủ động đẩy sự kiện lease tới JVM của ứng dụng.** `SecretLeaseContainer` của Spring Vault chủ động yêu cầu secret, lên lịch renew hoặc rotate, quan sát kết quả rồi **phát event cục bộ** tới `LeaseListener` / `LeaseErrorListener`. Callback có thể chạy trong luồng gọi `start()` hoặc luồng scheduler.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot ứng dụng
    participant Container as SecretLeaseContainer
    participant Vault as HashiCorp Vault
    participant Consumer as Credential consumer
    App->>Container: Đăng ký RequestedSecret + listener
    App->>Container: start()
    Container->>Vault: GET database/creds/readonly
    Vault-->>Container: username,password,lease_id,TTL
    Container-->>Consumer: SecretLeaseCreatedEvent.getSecrets()
    Consumer->>Consumer: Kiểm tra + áp dụng credential ban đầu
    loop Trong thời hạn lease
        Container->>Vault: renew nếu đủ điều kiện
        Vault-->>Container: TTL/renewable mới
        Container-->>Consumer: AfterSecretLeaseRenewedEvent
    end
    Container-->>Consumer: SecretLeaseExpiredEvent nếu phát hiện hết hạn
    Container->>Vault: GET credential mới theo rotating mode
    Vault-->>Container: username/password/lease mới
    Container-->>Consumer: SecretLeaseRotatedEvent.getSecrets()
    Consumer->>Consumer: Thay credential và chuyển kết nối
~~~

Sơ đồ thể hiện đường đi logic. Trong thực tế **thứ tự và thời điểm** event phụ thuộc scheduler, TTL, trạng thái Vault và chiến lược lease. Sự kiện hết hạn có thể được phát **sau thời điểm credential thật sự hết hạn**, nên không dùng nó như đồng hồ bảo đảm chuyển đổi không gián đoạn.

## 3. Các event ứng dụng cần biết

| Event | Khi nào xảy ra | Dữ liệu hữu ích | Ứng dụng nên làm gì? |
| --- | --- | --- | --- |
| `SecretLeaseCreatedEvent` | Lần đầu lấy được secret | `getSecrets()`, `getLease()`, `getSource()` | Xác thực dữ liệu, cấu hình thành phần sử dụng secret |
| `SecretLeaseRotatedEvent` | Nhận secret thay thế sau rotation | `getSecrets()`, lease cũ/mới | Cập nhật credential, chuyển connection pool |
| `AfterSecretLeaseRenewedEvent` | Renew lease thành công | Lease/TTL mới | Cập nhật deadline/metric, **không mặc định có mật khẩu mới** |
| `SecretLeaseExpiredEvent` | Container quan sát lease hết hạn | Lease và nguồn secret | Ngừng sử dụng credential hết hạn, cảnh báo hoặc giảm readiness |
| `BeforeSecretLeaseRevocationEvent` | Trước khi container revoke lease | Nguồn và lease | Chuẩn bị cleanup có kiểm soát |
| `AfterSecretLeaseRevocationEvent` | Sau khi revoke thành công | Nguồn và lease | Hoàn tất cleanup và cập nhật trạng thái |
| `SecretNotFoundEvent` | Không tìm thấy secret theo path | Nguồn được yêu cầu | Báo lỗi cấu hình hoặc nguồn dữ liệu thiếu |
| `SecretLeaseErrorEvent` | Lỗi đọc/renew/rotate/revoke | Thông tin sự kiện; ngoại lệ qua error listener | Ghi metric và xử lý khôi phục phù hợp |

Các class event thuộc package `org.springframework.vault.core.lease.event`. Mọi `SecretLeaseEvent` có `getSource()`, trả về `RequestedSecret` ứng với path đã đăng ký, và `getLease()` có thể không có giá trị. **Chỉ `SecretLeaseCreatedEvent` và các subclass thích hợp có `getSecrets()`** trả `Map<String,Object>` chứa các field bí mật mà Vault trả về.

Đặc biệt, `SecretLeaseRotatedEvent extends SecretLeaseCreatedEvent`. Khi dùng chuỗi `instanceof`, kiểm tra `SecretLeaseRotatedEvent` trước nếu cần logic riêng cho rotation; nếu chỉ cần **nạp credential mới** thì có thể xử lý cả hai bằng `SecretLeaseCreatedEvent`.

## 4. Phân biệt renew và rotate

Với một dynamic secret từ `database/creds/readonly`:

- **Renew:** Vault kéo dài thời hạn một lease còn được phép gia hạn. Thông thường username/password **không đổi**. Listener cập nhật thông tin TTL, không tự dựng username/password từ event renew.
- **Rotate:** ứng dụng nhận một bộ credential **khác** khi container yêu cầu secret mới. `SecretLeaseRotatedEvent.getSecrets()` cung cấp dữ liệu mới để cài đặt lại phía ứng dụng.
- **Expire:** lease cũ hết hiệu lực. Vault có thể đã thu hồi user/credential; event expire có thể đến trễ.
- **Revoke:** yêu cầu thu hồi lease sớm; khác với tự gia hạn và không mặc định tạo secret mới.

Hai cách đăng ký `RequestedSecret` có hành vi khác nhau:

~~~java
RequestedSecret renewOnly =
        container.requestRenewableSecret("database/creds/readonly");

RequestedSecret rotateWhenNeeded =
        container.requestRotatingSecret("database/creds/readonly");
~~~

Chế độ **renewable** tập trung duy trì lease hiện tại và ngừng khi hết hạn; chế độ **rotating** có thể lấy secret khác sau khi lease hết hạn. Container vẫn có thể **renew lease đủ điều kiện** trong chế độ rotating. Nếu mục tiêu là áp dụng credential mới, chọn rotating khi nghiệp vụ và engine thích hợp.

**Cần nhớ:** `renewable: true` trong phản hồi Vault nghĩa là *có thể yêu cầu gia hạn*; nó không hứa kéo dài vô hạn. Max TTL, loại secret, policy, Vault token, backend và cấu hình scheduler quyết định kết quả.

## 5. Chuẩn bị môi trường và lựa chọn secrets engine

Bài thực hành giả sử Vault đang chạy trong môi trường dev/test có:

- **Database secrets engine** tại `database/`, role `readonly` đã cấu hình với một database thử nghiệm. Path đọc là `database/creds/readonly`.
- **Vault token của ứng dụng** được cấp bởi workload authentication (Kubernetes, AppRole, cloud IAM...) và có quyền đọc path đó.
- Spring Boot đã có Spring Vault, một `VaultOperations` hoặc `VaultTemplate` dùng token trên, và Spring `TaskScheduler` để container lên lịch.

Policy tối thiểu cho việc **đọc dynamic credential**:

~~~hcl
path "database/creds/readonly" {
  capabilities = ["read"]
}
~~~

Phương thức đọc secret ở path này thường phát hành một username/password cùng `lease_id`, `lease_duration` và `renewable`. Việc gia hạn/thu hồi lease có thể đòi capability riêng ở API quản lý lease; hãy tuân theo chính sách và API phù hợp của Vault. **Không gán root token** cho ứng dụng để giải quyết lỗi permission denied.

**Vault dev server tự nó không tạo PostgreSQL, database secrets engine hay role.** Muốn chạy lab đầy đủ, phải cấu hình database plugin, connection, role và tài khoản quản trị cấp phát credential **trong một database sandbox**. Không dùng database production hoặc secret có dữ liệu thật trong bài thực hành.

## 6. Đăng ký listener trước khi container bắt đầu chạy

Ví dụ Java dưới đây cấu hình Spring Vault 3.2+/4.x theo API `SecretLeaseContainer`. Chúng ta đăng ký một `RequestedSecret` chế độ rotating; class `RotatingDatabaseAccess` ở mục 7 chịu trách nhiệm nhận secret mới và cung cấp credential cho các kết nối **được tạo sau sự kiện**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.AfterSecretLeaseRenewedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;
import org.springframework.vault.core.lease.event.SecretLeaseRotatedEvent;

@Configuration
public class LeaseRotationConfiguration {

    @Bean
    public TaskScheduler vaultLeaseScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-lease-");
        return scheduler;
    }

    @Bean
    public SecretLeaseContainer orderDatabaseLease(
            VaultOperations vault,
            TaskScheduler vaultLeaseScheduler,
            RotatingDatabaseAccess database) {

        SecretLeaseContainer container =
                new SecretLeaseContainer(vault, vaultLeaseScheduler);

        RequestedSecret requested = container.requestRotatingSecret(
                "database/creds/readonly");

        // Đăng ký callback TRƯỚC khi Spring start container.
        container.addLeaseListener(event -> {
            if (!requested.equals(event.getSource())) {
                return;
            }

            // RotatedEvent kế thừa CreatedEvent.
            if (event instanceof SecretLeaseRotatedEvent rotated) {
                database.accept(rotated.getSecrets(), rotated.getLease());
            } else if (event instanceof SecretLeaseCreatedEvent created) {
                database.accept(created.getSecrets(), created.getLease());
            } else if (event instanceof AfterSecretLeaseRenewedEvent renewed) {
                database.renewed(renewed.getLease());
            } else if (event instanceof SecretLeaseExpiredEvent expired) {
                database.expired(expired.getLease());
            }
        });

        container.addErrorListener((event, exception) -> {
            if (requested.equals(event.getSource())) {
                database.leaseError();
                // Ghi metric/alert tại đây. Không log nội dung secret.
            }
        });

        // Spring gọi afterPropertiesSet(), quản lý SmartLifecycle
        // và start/stop bean trong ApplicationContext.
        return container;
    }
}
~~~

Điểm cần đọc kỹ:

1. `requested.equals(event.getSource())` lọc sự kiện đúng path/mode. Một container có thể theo dõi nhiều secret; **không** cập nhật datasource từ một event thuộc key khác.
2. `container.addLeaseListener(...)` và `addErrorListener(...)` được gọi **trước khi bean được khởi chạy**. Listener thêm muộn có thể bỏ lỡ event secret đầu tiên.
3. `SecretLeaseRotatedEvent` được xét **trước** `SecretLeaseCreatedEvent`; cả hai đều mang `getSecrets()`.
4. `AfterSecretLeaseRenewedEvent` chỉ cập nhật vòng đời lease; không coi renew là nhận password mới.
5. `SecretLeaseExpiredEvent` được dùng để đánh dấu credential của đúng lease đã hết hạn; event không có nghĩa nên tự gọi một API cấp secret lần nữa trong listener.
6. `addErrorListener` nhận **exception riêng** để phát hiện lỗi. Không in `getSecrets()`, username, password, token hoặc `VaultResponse` vào log.
7. `SecretLeaseContainer` là Spring `SmartLifecycle`. Khi quản lý như bean, tránh tự gọi `start()` lần nữa hoặc tạo thêm container có cùng registration mà không kiểm soát lifecycle.

Ví dụ cấu hình scheduler trên chỉ là một cách đơn giản. Nếu Spring Cloud Vault hoặc `AbstractVaultConfiguration` đã cung cấp `SecretLeaseContainer` và scheduler, hãy **tái sử dụng, đăng ký listener vào đúng container** theo cấu hình dự án để tránh hai container cùng lấy credential động và cùng điều khiển một tài nguyên.

### Chế độ rotating có bảo đảm chuyển trước hạn không?

Không. Spring Vault có thể renew lease đủ điều kiện **cho đến lúc lease hết hạn**, sau đó mới lấy secret mới. Khi Vault chặn renew vì max TTL, hoặc việc rotate diễn ra sau expiry, có thể xuất hiện khoảng không có credential hợp lệ. Nếu ứng dụng yêu cầu chuyển đổi không gián đoạn, cần thiết kế **cấp và chuẩn bị credential mới sớm hơn hạn**, điều chỉnh chiến lược rotation theo yêu cầu, hoặc sử dụng cách quản lý credential phù hợp hệ thống. Không khẳng định `requestRotatingSecret` tự cung cấp giao dịch chuyển pool “zero downtime”.
## 7. Ứng dụng nhận và sử dụng credential mới

Ví dụ sau nhận **username/password** từ `getSecrets()`, lưu **một snapshot bất biến** bằng `AtomicReference`, rồi dùng snapshot đó khi tạo JDBC connection mới. Mẫu này phục vụ thực hành; hệ thống production thường cần connection pool và chiến lược chuyển pool.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.vault.core.lease.domain.Lease;

@Component
public final class RotatingDatabaseAccess {

    private final String jdbcUrl;
    private final AtomicReference<Snapshot> active = new AtomicReference<>();
    private final AtomicLong renewalCount = new AtomicLong();
    private final AtomicLong errorCount = new AtomicLong();

    public RotatingDatabaseAccess(
            @Value("${app.db.jdbc-url}") String jdbcUrl) {
        this.jdbcUrl = jdbcUrl;
    }

    public void accept(Map<String, Object> secrets, Lease lease) {
        if (lease == null || !lease.hasLeaseId()) {
            throw new IllegalArgumentException("Missing dynamic secret lease");
        }

        Object user = secrets.get("username");
        Object pass = secrets.get("password");
        if (!(user instanceof String username) || username.isBlank()
                || !(pass instanceof String password) || password.isBlank()) {
            throw new IllegalArgumentException(
                    "Incomplete dynamic database credentials");
        }

        // Công bố đồng thời username, password và lease hiện hành.
        Snapshot next = new Snapshot(
                username, password, Objects.requireNonNull(lease.getLeaseId()),
                Instant.now().plus(lease.getLeaseDuration()));
        active.set(next);
        // Không log secrets, snapshot hoặc lease ID.
    }

    public void renewed(Lease lease) {
        if (lease == null || !lease.hasLeaseId()) {
            return;
        }
        active.updateAndGet(current -> {
            if (current == null || !Objects.equals(
                    current.leaseId, lease.getLeaseId())) {
                return current;
            }
            // Renew chỉ cập nhật thời gian, không đổi credential.
            return new Snapshot(
                    current.username, current.password,
                    current.leaseId,
                    Instant.now().plus(lease.getLeaseDuration()));
        });
        renewalCount.incrementAndGet();
    }

    public void expired(Lease lease) {
        if (lease == null || !lease.hasLeaseId()) {
            return;
        }
        // Sự kiện lease cũ đến trễ không được xóa credential mới.
        active.updateAndGet(current ->
                current != null && Objects.equals(
                        current.leaseId, lease.getLeaseId())
                    ? null : current);
    }

    public void leaseError() {
        errorCount.incrementAndGet();
        // Metric, alert và retry theo loại lỗi do ứng dụng cấu hình.
    }

    public boolean isReady() {
        Snapshot current = active.get();
        return current != null
                && Instant.now().isBefore(current.expiresAt);
    }

    public Connection newConnection() throws SQLException {
        Snapshot current = active.get();
        if (current == null
                || !Instant.now().isBefore(current.expiresAt)) {
            throw new IllegalStateException(
                    "No currently usable credentials");
        }
        return DriverManager.getConnection(
                jdbcUrl, current.username, current.password);
    }

    private static final class Snapshot {
        final String username;
        final String password;
        final String leaseId;
        final Instant expiresAt;

        Snapshot(String username, String password,
                String leaseId, Instant expiresAt) {
            this.username = username;
            this.password = password;
            this.leaseId = leaseId;
            this.expiresAt = expiresAt;
        }
        // Không thêm toString sinh ra giá trị password.
    }
}
~~~

Ví dụ cấu hình URL dùng PostgreSQL sandbox:

~~~yaml
app:
  db:
    jdbc-url: jdbc:postgresql://localhost:5432/lease_demo
~~~

Cần JDBC driver tương ứng và role Vault hợp lệ. **Không** đặt username/password thực vào file YAML: dữ liệu đến qua `SecretLeaseCreatedEvent` hoặc `SecretLeaseRotatedEvent`.

Điểm mấu chốt: `accept()` xác minh dữ liệu trước khi đổi `active`. Sau rotation, connection **mở mới** sẽ dùng credential mới. `renewed()` chỉ gia hạn thời điểm quan sát của đúng lease. `expired()` so khớp lease ID trước khi đánh dấu unavailable, tránh event hết hạn của **lease trước** xóa snapshot vừa nhận từ rotation.

`Instant.now()` ở đây chỉ là ước lượng TTL theo đồng hồ client. Vault/database mới có quyền quyết định hiệu lực thật; phải có ngưỡng an toàn, giám sát và cơ chế xử lý backend từ chối credential. `DriverManager` mở connection riêng mỗi lần, chưa thay thế thiết kế connection pool trong production. Bảo vệ cả heap dump, debugger, metric và exception khỏi lộ password.

## 8. Áp dụng sự kiện vào connection pool mà không làm hỏng yêu cầu đang chạy

Ví dụ ở mục 7 chứng minh **truyền secret mới** tới nơi sử dụng credential, nhưng `DriverManager` tạo connection mỗi lần không phù hợp hệ thống lưu lượng lớn. Khi dùng HikariCP, Tomcat JDBC pool hoặc pool khác, ứng dụng còn phải xử lý vòng đời **các connection đã tạo bằng credential cũ**.

Một quy trình chuyển pool an toàn về mặt thiết kế:

1. Listener nhận `SecretLeaseCreatedEvent` hoặc `SecretLeaseRotatedEvent`, trích xuất và kiểm tra đủ username/password.
2. Khởi tạo **pool ứng viên** bằng cặp credential mới, chưa chuyển request nghiệp vụ sang pool này.
3. Mở connection thử trong database sandbox, kiểm tra xác thực và quyền tối thiểu; đảm bảo JDBC URL/database/tenant đúng cấu hình.
4. Chỉ khi kết nối ứng viên hợp lệ mới đổi bộ định tuyến để **connection được cấp sau đó** sử dụng pool mới.
5. Để các giao dịch trên pool cũ thoát dần; đóng pool cũ theo giới hạn drain/timeout đã xác định.
6. Nếu ứng viên thất bại, ghi lỗi vận hành và giữ hệ thống ở trạng thái an toàn. Chỉ dùng tiếp credential cũ khi lease và backend thực sự còn hợp lệ.
7. Tách cleanup khỏi callback xử lý event nếu thao tác kết nối/đợi giao dịch mất nhiều thời gian.

~~~mermaid
flowchart TD
    A["Sự kiện có secret mới"] --> B["Đọc đủ username + password"]
    B --> C{"Kiểm tra dữ liệu hợp lệ?"}
    C -->|Không| F["Báo lỗi, không công bố credential"]
    C -->|Có| D["Chuẩn bị pool ứng viên"]
    D --> E{"Test kết nối thành công?"}
    E -->|Không| F
    E -->|Có| G["Đổi routing atomically"]
    G --> H["Request mới dùng pool mới"]
    G --> I["Drain pool cũ rồi đóng"]
    F --> J["Health/alert và chính sách fail closed"]
~~~

**Không đủ chỉ gọi `setUsername()` hoặc `setPassword()` trên một DataSource đang hoạt động.** Ví dụ với HikariCP, việc thay cấu hình runtime phụ thuộc phiên bản và kiểu kết nối; thay mật khẩu có thể chỉ tác động các connection **được tạo mới**. Hai setter độc lập còn có nguy cơ xuất hiện **cặp username/password không đồng bộ** nếu không có cơ chế thích hợp. Với database và JDBC driver của dự án, hãy xác minh API Hikari đang dùng, rồi chọn cập nhật credential nguyên cặp/evict connection có kiểm soát hoặc thay pool mới.

Ngay cả khi việc đổi pool thành công, connection hiện hữu trên pool cũ có thể tiếp tục chạy hoặc thất bại tùy backend và trạng thái user cũ. Rotation cần được thử với **giao dịch dài, connection đang bận, retry và điểm cắt chuyển**; không chỉ kiểm tra ứng dụng có nhận event.

## 9. Sự kiện không tự bảo đảm availability

Ba điều kiện độc lập quyết định một request database có thể thành công:

- **Vault token hợp lệ:** `VaultTemplate` và `SecretLeaseContainer` có token workload để đọc/renew lease theo policy.
- **Secret lease còn hiệu lực:** credential động chưa hết hạn hoặc bị revoke; việc renew chịu giới hạn của Vault.
- **Consumer đã áp dụng secret đúng:** datasource/pool hoặc client khác đang sử dụng đúng credential và endpoint.

Ví dụ: `AfterSecretLeaseRenewedEvent` xuất hiện nghĩa là lease được gia hạn, nhưng nếu datasource giữ sai username/password, ứng dụng vẫn lỗi. Ngược lại, `SecretLeaseCreatedEvent` đã chứa mật khẩu đúng, nhưng nếu consumer chưa sẵn sàng, request nghiệp vụ vẫn có thể thất bại.

### Readiness nên phản ánh credential đã áp dụng

Trong hệ thống dùng credential động, readiness cần chứng minh tối thiểu rằng:

1. Đã nhận secret đầu tiên và kiểm tra schema.
2. Đã chuẩn bị thành phần sử dụng credential (đặc biệt connection pool).
3. Có thể dùng credential còn hiệu lực trong ngưỡng thời gian đủ an toàn.
4. Không có tình trạng rotation lỗi kéo dài vượt chính sách chấp nhận.

**Đừng dùng việc nhận một event là điều kiện duy nhất để trả READY.** Khi app bắt đầu, `SecretLeaseContainer` có thể chưa lấy secret; endpoint nghiệp vụ phải xử lý trạng thái “chưa sẵn sàng” thay vì tự dùng mật khẩu tĩnh dự phòng.

### Thời gian của event và TTL

`SecretLeaseContainer` tính lịch renew/rotate dựa trên TTL và scheduler. Tài liệu Spring Vault mô tả tham số **expiry threshold** và **minimum renewal time**; các ngưỡng mặc định có thể được điều chỉnh theo phiên bản và đặc điểm lease. Một event hết hạn có thể tới **trễ hơn hạn thật**, nên việc chặn sử dụng credential hết hạn cần kiểm tra TTL và lỗi backend, không đợi riêng `SecretLeaseExpiredEvent`.

Khi Vault có `max_ttl` khiến renewal không thể tiếp tục, container có thể cần lấy credential thay thế; ứng dụng cần có kế hoạch cho khoảng chuyển đổi. Thay đổi lịch renew/rotate phải được kiểm tra với chính sách backend, tránh tạo quá nhiều tài khoản tạm thời hoặc làm tăng tải.

## 10. Spring Vault 4.1+: ManagedSecret khi không cần tự xử lý event

Với Spring Vault 4.1+, **`ManagedSecret`** là abstraction mức cao hơn `SecretLeaseContainer` để nối secret có vòng đời với thành phần nhận dữ liệu. Một mẫu trong tài liệu Spring Vault có dạng:

~~~java
// Phác thảo cho Spring Vault 4.1+ (kiểm tra API phiên bản dự án):
@Bean
ManagedSecret databaseCredentials(RotatingConnectionPool pool) {
    return ManagedSecret.rotating(
        "database/creds/readonly",
        secrets -> secrets.as(UsernamePassword::from)
                .applyTo((user, pass) ->
                        pool.installNewCredentials(user, pass)));
}
~~~

Đoạn này là **phác thảo tích hợp**: `RotatingConnectionPool`, `UsernamePassword` là kiểu ứng dụng phải triển khai; cần khớp API `ManagedSecret` đang dùng trước khi biên dịch. Nó minh họa cách chuyển xử lý dữ liệu vào một consumer khi secret được cấp/rotate, giảm nhu cầu viết `LeaseListener` thủ công.

**Chọn một chiến lược đăng ký cho mỗi path:** dùng `ManagedSecret`/registrar hoặc listener thủ công phù hợp, tránh cùng lúc đăng ký hai consumer tranh nhau cập nhật một datasource. Khi dùng `Spring Cloud Vault` hoặc `AbstractVaultConfiguration`, hãy kiểm tra bean được auto-configure và thứ tự startup. Thành phần nghiệp vụ không nên truy cập database bằng credential chưa được cấp.

Ngoài database credential, luồng Spring Vault còn liên quan tới **KV secrets**, Transit encryption và PKI. Không áp quy tắc “renew lease của database” cho mọi loại dữ liệu: KV tĩnh có thể không mang lease, Transit trả ciphertext/khóa theo API riêng, còn chứng thư PKI có validity/reissuance và container/cơ chế rotation phù hợp. Hãy chọn cơ chế theo semantics của secrets engine.

## 11. Thực hành kiểm chứng sự kiện lease

**Tiền điều kiện**: môi trường Vault dev/test có database secrets engine và role `readonly` thật, JDBC database sandbox, token ứng dụng có quyền đọc/renew cần thiết theo policy, Java runtime và Spring Vault dependency khớp code ở trên.

### Bước 1 — Xác minh Vault có phát hành dynamic secret

Trong Bash, kiểm tra role và lấy một secret mẫu. **Không in nguyên response** vì nó có username/password:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# VAULT_TOKEN được cấp cho môi trường thử nghiệm.
vault status
vault read database/roles/readonly

# Ví dụ chỉ in lease metadata, không in credential.
vault read -format=json database/creds/readonly \
  | jq '{lease_id_present:(.lease_id != ""),
         lease_duration, renewable}'
~~~

Lưu ý: mỗi lần gọi `database/creds/readonly` có thể **phát hành một credential mới**. Lệnh chỉ xem metadata ở trên vẫn tạo một lease thật; dọn lease thử nghiệm theo quy trình operator sau khi lab kết thúc. Trong bài test CI, nên ghi nhận ID vào biến nội bộ bảo mật để có thể revoke đúng đối tượng, thay vì tạo lease không theo dõi.

Nếu role chưa tồn tại, Vault dev server không tự tạo nó. Cần chuẩn bị sandbox database/role theo tài liệu Vault Database Secrets Engine trước khi tiếp tục; không chuyển sang KV tĩnh rồi kỳ vọng nhận event lease động tương đương.

### Bước 2 — Khởi động Spring Boot với listener đã đăng ký

Trình tự mong đợi:

~~~text
ApplicationContext khởi tạo
  -> tạo VaultOperations và scheduler
  -> tạo RotatingDatabaseAccess
  -> tạo SecretLeaseContainer + RequestedSecret rotating
  -> đăng ký LeaseListener và LeaseErrorListener
  -> SmartLifecycle start
  -> Vault đọc database/creds/readonly
  -> SecretLeaseCreatedEvent (có username/password)
  -> RotatingDatabaseAccess.accept(...)
  -> ứng dụng có thể mở connection mới
~~~

Để kiểm tra không lộ bí mật, chỉ in những tín hiệu như `lease.created.count`, `lease.rotated.count`, `credential.applied`, `connection.probe.success`; không in event object trực tiếp vì một số event chứa `getSecrets()`.

### Bước 3 — Quan sát renew và rotation

Trong sandbox có TTL nhỏ và giới hạn max TTL rõ ràng, để ứng dụng chạy qua nhiều chu kỳ quản lý lease. Kiểm tra:

- Lần cấp đầu: `SecretLeaseCreatedEvent` xuất hiện và consumer đã nạp credential.
- Khi renew thành công: `AfterSecretLeaseRenewedEvent` cho biết lease được gia hạn; không cần ghi đè username/password.
- Khi Vault không thể renew thêm và container tạo secret mới: `SecretLeaseRotatedEvent` xuất hiện, consumer nhận cặp credential mới.
- Khi lease cũ đã hết hạn: `SecretLeaseExpiredEvent` có thể xuất hiện, **không được** vô hiệu hóa snapshot của lease mới.
- Khi database plugin hoặc Vault mất kết nối: `LeaseErrorListener` ghi nhận lỗi đã loại thông tin nhạy cảm.

**Không cam kết rotation xảy ra ở một giây cố định.** Container có thể gia hạn nhiều lần trước khi rotate; điều kiện TTL/renewability/max TTL và scheduler ảnh hưởng thời điểm. Nếu cần thử rotation chủ động, API container có `rotate(RequestedSecret)`; chỉ dùng trên đối tượng đã đăng ký và với quyền thích hợp, trong môi trường sandbox.

### Bước 4 — Kiểm tra consumer dùng secret đã nhận

Trong Java code test nội bộ:

~~~java
// Ví dụ một thao tác kết nối ngắn với credential hiện hành.
try (Connection connection = databaseAccess.newConnection()) {
    if (!connection.isValid(3)) {
        throw new IllegalStateException("Database probe failed");
    }
}
~~~

Sau rotation, mở connection **mới** và kiểm tra cơ chế xác thực của database. Với pool thật, phải thử connection pool mới và cả giao dịch đang dùng pool cũ để chứng minh cutover thực sự hoạt động.

## 12. Ma trận kiểm thử callback và consumer

| Tình huống | Input/sự kiện | Kết quả phải xác minh |
| --- | --- | --- |
| Secret đầu tiên | `SecretLeaseCreatedEvent` với username/password hợp lệ | Đã cài credential, kết nối mới thành công |
| Secret thiếu field | `getSecrets()` không có `password` hoặc giá trị rỗng | Từ chối dữ liệu, không công bố snapshot hỏng |
| Nhầm nguồn | Event `RequestedSecret` khác path đăng ký | Listener bỏ qua; dữ liệu đang dùng không đổi |
| Renew thành công | `AfterSecretLeaseRenewedEvent` cùng lease ID | Cập nhật TTL quan sát; không thay password |
| Rotate thành công | `SecretLeaseRotatedEvent` có lease/credential mới | Consumer nhận cặp mới, kết nối mới dùng cặp mới |
| Expire đến trễ | `SecretLeaseExpiredEvent` của lease cũ đến sau rotate | Không xóa credential mới |
| Expire hiện tại | `SecretLeaseExpiredEvent` khớp lease ID hiện hành | Không tiếp tục tạo kết nối bằng credential hết hạn |
| Thất bại cấp mới | Error listener nhận exception khi đọc/rotate | Metric/alert; không lộ secret; sẵn sàng giảm nếu cần |
| Token Vault bị thu hồi | Auth/session lỗi, container không đọc được secret | Phân loại lỗi workload/token và re-authentication phù hợp |
| Database tạm mất kết nối | Có secret nhưng connection probe thất bại | Không công bố pool mới chưa được kiểm tra |
| Container chưa start | Chưa có event tạo secret | API phụ thuộc database phải chờ readiness |
| Container stop/destroy | Không còn scheduling lease | Cleanup theo chính sách, không giữ credential sống vô hạn |

Tách **unit test** của parser/snapshot khỏi **integration test** của Vault và database: unit test kiểm tra đúng cách `Map<String,Object>` được tiếp nhận, event của lease cũ không lấn lease mới; integration test kiểm tra quyền Vault, TTL và khả năng mở JDBC connection thật sau rotation. Không tạo kiểm thử bằng cách chỉ gọi lại implementation rồi kiểm tra field vừa gán; quan trọng là hành vi **được phép, bị từ chối và chuyển credential**.

## 13. Các sai lầm dễ gặp

**“Vault sẽ push event lease trực tiếp vào Spring Boot.”** Không. Spring Vault theo dõi lease bằng các request và scheduler; event là cơ chế trong JVM sau khi nó quan sát kết quả.

**“Có `AfterSecretLeaseRenewedEvent` thì phải nạp password mới.”** Không. Renew lease không đồng nghĩa secrets engine đã phát hành username/password khác. Chỉ sự kiện cấp mới/rotate có dữ liệu secret cần được cài lại.

**“Chỉ lắng nghe `SecretLeaseExpiredEvent` là đủ.”** Không. Event có thể xuất hiện sau lúc lease thật sự hết hạn. Consumer cần TTL, readiness, chính sách retry và đường cấp credential mới; phản hồi từ backend vẫn là nguồn kiểm chứng cuối.

**“Sau rotation, thay thuộc tính DataSource là mọi kết nối tự chuyển.”** Không. Connection đã mở có thể tiếp tục dùng quyền cũ. Cần chiến lược pool replacement, kiểm tra kết nối và drain.

**“Lỗi 403 của Vault là lỗi password của database.”** Không nhất thiết. 403 ở Vault có thể đến từ token workload hết hạn, policy thiếu capability hoặc sai path. Lỗi đăng nhập database là một biên khác và phải được chẩn đoán riêng.

**“Tái sử dụng Vault token là đồng nghĩa gia hạn secret lease.”** Không. Session manager điều phối token; secret lease có `lease_id`, TTL và renewable riêng. Mất Vault session còn có thể dẫn tới thu hồi các lease liên quan.

**“Log event giúp dễ debug.”** Log event thô có thể lộ credential, lease metadata hoặc dữ liệu nhạy cảm. Chỉ log trạng thái, mã lỗi đã phân loại, role/path đã được kiểm soát và correlation ID; không ghi secret.

## 14. Câu hỏi và tiêu chí hoàn thành

1. Khi nào phải lấy credential từ `SecretLeaseCreatedEvent.getSecrets()`, và vì sao `AfterSecretLeaseRenewedEvent` khác?
2. Vì sao cần `requested.equals(event.getSource())` khi container quản lý nhiều path?
3. Nếu event expired của lease A đến sau khi consumer đã nạp lease B, ứng dụng phải xử lý thế nào?
4. Vì sao cặp username/password nên được thay nguyên một snapshot?
5. Một `SecretLeaseRotatedEvent` đến nhưng database sandbox từ chối password mới. Điều gì cần xảy ra trước khi chuyển connection mới?
6. `SecretLeaseContainer` khác `LifecycleAwareSessionManager` ở phạm vi trách nhiệm ra sao?
7. Sự kiện nào và kiểm tra nào cần có để chứng minh pool thật đã chuyển sang credential mới?

**Gợi ý:** (1) Created/Rotated mang secret mới, renew chỉ gia hạn; (2) tránh lẫn nguồn; (3) không ghi đè/hủy B; (4) tránh lệch cặp; (5) probe ứng viên và fail closed; (6) quản lý secret lease khác với token session; (7) event + thử kết nối mới + chuyển pool + dọn pool cũ.

**Tiêu chí hoàn thành kỹ thuật:** ứng dụng đăng ký listener trước startup; nhận được secret đầu qua `getSecrets()`, áp dụng được vào consumer; có logic cho renew/rotate/expire/error; không dùng sai lease ID; kiểm tra bằng ít nhất một yêu cầu database thật trong sandbox; không để lộ secret; và có hành vi an toàn khi credential không còn sử dụng được.

### Tài liệu tham khảo

- [Spring Vault — Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault — SecretLeaseCreatedEvent API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/SecretLeaseCreatedEvent.html)
- [Spring Vault — SecretLeaseRotatedEvent API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/SecretLeaseRotatedEvent.html)
- [Spring Vault — Lease event package](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/package-summary.html)
- [Spring Vault — Lease API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/domain/Lease.html)
- [HashiCorp Vault — Lease lifecycle](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HikariCP — Runtime configuration FAQ](https://github.com/brettwooldridge/HikariCP/wiki/FAQ)

**Ứng dụng tiếp nhận dữ liệu từ sự kiện lease** nghĩa là nối quá trình quản lý secret trong Vault với quá trình cập nhật tài nguyên đang chạy của Java. `SecretLeaseContainer` báo khi secret mới đã có; ứng dụng phải **kiểm tra, cài đặt, chuyển đổi và xử lý lỗi** để credential mới thực sự được sử dụng đúng thời điểm.
