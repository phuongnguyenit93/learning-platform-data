# Thứ tự đăng ký secret và khởi tạo thành phần sử dụng trong Spring Vault

Trong ứng dụng Java sử dụng **Spring Vault** để truy cập HashiCorp Vault, việc lấy dynamic secret và tạo đối tượng sử dụng secret phải tuân thủ một **thứ tự khởi tạo**. Nếu ứng dụng tạo JDBC connection pool trước khi Vault cấp username/password, pool có thể khởi động với credential rỗng. Nếu ứng dụng đăng ký listener sau khi `SecretLeaseContainer` bắt đầu, nó có thể **bỏ lỡ sự kiện secret đầu tiên**. Hai tình huống này thường chỉ xuất hiện lúc khởi động hoặc khi credential được xoay vòng nên dễ gây lỗi khó tái hiện.

Bài thuộc chương **Xoay vòng trong ứng dụng** của module **SPRING_VAULT**. Mục tiêu là hiểu thời điểm secret được đăng ký, được tải và được chuyển đến các thành phần sử dụng như JDBC pool, HTTP client hoặc service cần chứng chỉ/credential; từ đó xây dựng quy trình khởi động, rotation và xử lý lỗi an toàn.

## 1. Phân biệt đăng ký, lấy secret và khởi tạo consumer

`SecretLeaseContainer` là cơ chế Spring Vault quản lý các secret có lease: yêu cầu secret từ Vault, theo dõi TTL, gia hạn và xoay vòng khi cần. Container có thể hoạt động như một Spring `SmartLifecycle` bean. Tài liệu và API phân biệt ba thao tác:

| Thao tác | Ý nghĩa | Đã có credential để sử dụng? |
| --- | --- | --- |
| Tạo `RequestedSecret` | Mô tả path và mode RENEW/ROTATE. | **Chưa**. Đây chỉ là định nghĩa nhu cầu. |
| `register(requestedSecret)` hoặc `requestRotatingSecret(path)` | Đưa secret vào tập cần quản lý. | **Chưa chắc**; nếu container đã chạy, việc đăng ký có thể kích hoạt lấy secret ngay. |
| `SecretLeaseContainer.start()` | Container bắt đầu lấy các secret đã đăng ký, phát event và lập lịch lease. | Chỉ sau khi **request thành công**, ứng dụng mới có credential hợp lệ. |
| Consumer nhận secret mới | Ứng dụng kiểm tra, chuẩn bị và áp dụng credential cho client/pool. | Sẵn sàng sau khi consumer **xác nhận áp dụng thành công**. |
| Renew/rotate tiếp theo | Container quản lý vòng đời lease theo TTL/strategy. | Phải cập nhật consumer khi **secret thay đổi**. |

`SecretLeaseContainer` không phải nơi chứa một username/password dùng được ngay lúc bean được tạo. Một `RequestedSecret` đã đăng ký không bảo đảm secret đã tồn tại, có quyền đọc hoặc đã được chuyển đến consumer.

### 1.1. Thứ tự khởi tạo an toàn

Có thể biểu diễn chuỗi thao tác ở mức ứng dụng:

~~~mermaid
sequenceDiagram
    participant Cfg as Spring configuration
    participant Store as Credential holder
    participant Lease as SecretLeaseContainer
    participant Vault as Vault
    participant App as JDBC/HTTP consumer
    Cfg->>Store: Tạo holder chưa sẵn sàng
    Cfg->>Lease: Tạo container và TaskScheduler
    Cfg->>Lease: Đăng ký lease listener + error listener
    Cfg->>Lease: Đăng ký RequestedSecret (ROTATE)
    Cfg->>Lease: Khởi tạo và start container
    Lease->>Vault: Lấy secret ban đầu
    alt Secret hợp lệ
        Vault-->>Lease: data + lease
        Lease->>Store: SecretLeaseCreatedEvent
        Store->>Store: Kiểm tra và ghi nhận credential
        Store-->>App: Cho phép khởi tạo/áp dụng credential
        App->>App: Kiểm tra kết nối thực
    else Secret lỗi
        Vault-->>Lease: 403/404/timeout...
        Lease->>Store: LeaseErrorListener / SecretNotFoundEvent
        Store-->>App: Chưa có credential; chưa sẵn sàng
    end
    Lease->>Vault: Gia hạn / rotate khi cần
    Vault-->>Lease: Lease hoặc secret mới
    Lease->>App: Thay credential có kiểm soát
~~~

Trình tự thực tế cần đảm bảo:

1. **Khởi tạo nơi tiếp nhận** (holder/handler/consumer callback) mà **không cần credential ngay lúc constructor chạy**.
2. **Đăng ký các listener** bình thường và listener lỗi trước khi có khả năng phát sự kiện.
3. **Đăng ký đúng `RequestedSecret`** và chế độ xử lý lease.
4. **Khởi động container**, để Vault cấp dữ liệu thật và Spring Vault phát event.
5. **Kiểm tra và áp dụng secret ban đầu** vào consumer; chỉ công bố readiness sau khi consumer đã dùng được.
6. **Lắng nghe rotation/expiry/error về sau**; chuyển dữ liệu mới tới consumer mà không tiếp tục dùng credential cũ quá hạn.

Đặc biệt, sự kiện có thể xuất hiện trên **thread gọi `start()`** hoặc worker thread của scheduler; không được giả định mọi callback luôn chạy cùng một thread.

## 2. Đăng ký listener trước khi secret được kích hoạt

Theo tài liệu Spring Vault, container có thể nhận đăng ký khi đang chạy. Nếu một secret đã được lấy và phát `SecretLeaseCreatedEvent` trước khi bạn gắn listener, Spring Vault **không phát lại payload ban đầu cho listener đăng ký muộn**; listener mới thường chỉ thấy các sự kiện renewal/rotation trong tương lai.

### 2.1. Thứ tự dễ gây lỗi

Ví dụ sau **không nên dùng**:

~~~java
SecretLeaseContainer container = new SecretLeaseContainer(vaultOperations, scheduler);
container.afterPropertiesSet();
container.start();

// Sai: container đã hoạt động, yêu cầu secret có thể được xử lý ngay.
RequestedSecret secret = container.requestRotatingSecret("database/creds/orders");

// Listener gắn sau khi yêu cầu: có thể đã lỡ SecretLeaseCreatedEvent.
container.addLeaseListener(event -> {
    // Có thể không nhận được secret ban đầu.
});
~~~

Hậu quả: một bean đang chờ username/password từ event có thể không bao giờ nhận được dữ liệu ban đầu dù Vault đã cấp thành công. Cơ chế renew lease vẫn hoạt động trong nền nên log dễ gây nhầm rằng ứng dụng đã sẵn sàng.

### 2.2. Đăng ký đúng thứ tự

Ví dụ cho Spring Vault **4.1+**:

~~~java
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;

SecretLeaseContainer container =
        new SecretLeaseContainer(vaultOperations, scheduler);

RequestedSecret requested = RequestedSecret.rotating("database/creds/orders");

// Thêm listener và error handler trước khi kích hoạt việc lấy secret.
container.addLeaseListener(event -> {
    if (!requested.equals(event.getSource())) {
        return;
    }

    if (event instanceof SecretLeaseCreatedEvent created) {
        // event.getSecrets() là dữ liệu nhạy cảm; chuyển cho holder.
        credentialHolder.accept(created.getSecrets());
    } else if (event instanceof SecretLeaseExpiredEvent) {
        credentialHolder.markExpired();
    }
});

container.addErrorListener((event, exception) -> {
    if (requested.equals(event.getSource())) {
        credentialHolder.markDegraded();
        // Ghi metric và loại exception; không log payload/token.
    }
});

container.register(requested);  // Spring Vault 4.1+
container.afterPropertiesSet();
container.start();             // Bắt đầu nhận các sự kiện.
~~~

Ở các phiên bản **3.x/4.0**, API `addRequestedSecret(requested)` hoặc `requestRotatingSecret(path)` cũng hỗ trợ đăng ký secret; `SecretsRegistry.register(...)` là API được bổ sung vào Spring Vault 4.1. Cần dùng Javadoc tương ứng với phiên bản dependency.

Có một biến thể gọn cho **4.1+**:

~~~java
// Đăng ký listener riêng gắn với RequestedSecret:
container.register(requested, event -> {
    if (event instanceof SecretLeaseCreatedEvent created) {
        credentialHolder.accept(created.getSecrets());
    }
});
~~~

Với biến thể trên, container tự liên kết listener với `requested`. Vẫn nên đăng ký error listener trước thời điểm secret được kích hoạt, đồng thời không thêm hai listener cùng xử lý sự kiện theo cách gây cập nhật trùng.

### 2.3. Đăng ký trùng không làm phát lại giá trị đầu tiên

Trong Spring Vault 4.1, cùng một `RequestedSecret` được đăng ký nhiều lần thì container quản lý nó như **một registration**. Đăng ký lại để “xin phát lại event” không phải cơ chế lấy snapshot. Nếu cần consumer mới được tạo sau, hãy sử dụng **holder/managed state** lưu credential hiện tại hoặc thiết kế lại vòng đời khởi tạo, thay vì phụ thuộc vào việc đăng ký trùng.

Ngoài ra, khi gọi `unregister(requested)`, container ngừng quản lý renewal/rotation của registration đó và loại bỏ các listener gắn riêng với registration. Consumer đang giữ credential cũ vẫn phải được ứng dụng xử lý đóng/thu hồi khi thích hợp.

## 3. Bẫy vòng đời Spring Bean: constructor, @PostConstruct và SmartLifecycle

Một ứng dụng Spring thường có các giai đoạn:

~~~text
Đăng ký BeanDefinition
   -> Khởi tạo @Bean / constructor
   -> Injection và @PostConstruct / afterPropertiesSet
   -> LifecycleProcessor kích hoạt SmartLifecycle.start()
   -> ApplicationReadyEvent / nhận traffic
~~~

Đây là mô hình tổng quát, còn một số cấu hình có thể chủ động khởi chạy container sớm. Điểm quan trọng: **`@PostConstruct` của consumer có thể chạy trước khi `SecretLeaseContainer.start()` lấy được secret**.

Ví dụ có lỗi:

~~~java
@Component
final class OrdersClient {

    private final CredentialsHolder credentials;

    OrdersClient(CredentialsHolder credentials) {
        this.credentials = credentials;
    }

    @PostConstruct
    void initialize() {
        // Sai nếu SecretLeaseContainer chưa tải credential:
        DbCredentials current = credentials.requireCurrent();
        // Tạo connection pool ngay; dễ lỗi startup.
    }
}
~~~

Ngay cả nếu dùng `@DependsOn("secretLeaseContainer")`, sự phụ thuộc thường chỉ buộc **bean container được tạo trước**, chứ không bảo đảm secret đã được **request và áp dụng** xong. Vì thế `@DependsOn` đơn độc không phải đồng bộ hóa dữ liệu bất đồng bộ.

Spring Vault `AbstractVaultConfiguration` chủ động khởi động container trong quá trình tạo bean để hỗ trợ truy cập credential sớm trong một số cách cấu hình. Tuy nhiên tài liệu vẫn yêu cầu đảm bảo **dependency ordering** đúng cho ứng dụng cụ thể. Còn khi dùng **Spring Boot + Spring Cloud Vault**, thường nên dùng bean/container từ auto-configuration thay vì tự tạo bản thứ hai cho cùng secret.

### 3.1. Nguyên tắc phân quyền tạo bean

| Loại bean | Khi nào tạo? | Khi nào bắt đầu sử dụng thật? |
| --- | --- | --- |
| `VaultTemplate`, `VaultOperations` và session manager | Trong cấu hình nền tảng Vault. | Khi có token/auth hợp lệ để gọi Vault. |
| `TaskScheduler` | Trước container. | Khi container lập lịch renew/rotate. |
| `CredentialsHolder` (chỉ giữ trạng thái) | Sớm, không cần credential. | Được cập nhật qua event. |
| `SecretLeaseContainer` | Sau các dependency cơ sở. | Start sau khi listener và registration đã sẵn sàng. |
| JDBC/HTTP consumer phụ thuộc credential | Có thể tạo **wrapper chưa kết nối** sớm. | Chỉ kết nối/cho phép traffic khi đã nhận và kiểm chứng credential. |
| Readiness/health | Tạo cùng application infrastructure. | Trả READY sau khi secret và consumer đều dùng được. |

Chọn thứ tự theo **điều kiện dữ liệu sẵn sàng**; thời điểm Spring gọi constructor không đủ để xác nhận external secret đã có.

## 4. Mẫu holder: nhận secret ban đầu trước khi consumer hoạt động

Một holder có thể lưu **snapshot credential mới nhất** và báo trạng thái readiness; không tự mở connection trong callback. Mã minh họa (Java 17+) dưới đây độc lập với cơ chế tạo Spring bean:

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class DbCredentialState {

    public record DbCredentials(String username, String password) {
        // Không tự động log/serialize record này.
    }

    private final AtomicReference<DbCredentials> current =
            new AtomicReference<>();
    private final AtomicBoolean degraded = new AtomicBoolean(true);

    public void accept(Map<String, Object> secrets) {
        Object username = secrets.get("username");
        Object password = secrets.get("password");

        if (!(username instanceof String user) || user.isBlank()
                || !(password instanceof String pass) || pass.isBlank()) {
            throw new IllegalArgumentException(
                    "Dynamic secret thiếu username/password hợp lệ");
        }

        current.set(new DbCredentials(user, pass));
        degraded.set(false);
    }

    public DbCredentials requireCurrent() {
        DbCredentials snapshot = current.get();
        if (snapshot == null || degraded.get()) {
            throw new IllegalStateException(
                    "Credential chưa sẵn sàng để sử dụng");
        }
        return snapshot;
    }

    public void markDegraded() {
        degraded.set(true);
    }

    public void markExpired() {
        current.set(null);
        degraded.set(true);
    }
}
~~~

Mẫu này nhằm minh họa **quyết định readiness**. Trong ứng dụng thật, lỗi renew tạm thời chưa chắc làm credential hết hạn; không nên đánh `degraded=true` thành nghĩa “credential bị revoke” nếu chưa có chứng cứ. Tùy use case, có thể lưu thêm mốc TTL và cho phép đọc credential còn hạn khi request mới được kiểm soát.

Dùng holder trong ví dụ `SecretLeaseContainer` ở mục 2:

~~~java
DbCredentialState credentialHolder = new DbCredentialState();

SecretLeaseContainer container = new SecretLeaseContainer(vaultOperations, scheduler);
RequestedSecret requested = RequestedSecret.rotating("database/creds/orders");

container.addLeaseListener(event -> {
    if (!requested.equals(event.getSource())) return;

    if (event instanceof SecretLeaseCreatedEvent created) {
        credentialHolder.accept(created.getSecrets());
    } else if (event instanceof SecretLeaseExpiredEvent) {
        credentialHolder.markExpired();
    }
});

container.addErrorListener((event, error) -> {
    if (requested.equals(event.getSource())) {
        credentialHolder.markDegraded();
    }
});

container.register(requested);
container.afterPropertiesSet();
container.start();

// Chỉ tiêu thụ khi initial fetch đã cung cấp dữ liệu hợp lệ.
// Không mặc định start() luôn thành công; nếu thất bại thì xử lý fail-fast.
DbCredentialState.DbCredentials initial = credentialHolder.requireCurrent();

// Ví dụ: tạo DataSource/HTTP client từ initial sau khi đã có credential.
~~~

**Giới hạn của mẫu:** Đoạn mã trên giả định event ban đầu đã được xử lý vào thời điểm kiểm tra `requireCurrent()`, phù hợp để minh họa chạy khởi tạo đồng bộ trong lab nhưng **không phải hợp đồng bảo đảm mọi biến thể khởi tạo đều đồng bộ**. Ở production, nếu việc nạp secret diễn ra bất đồng bộ hoặc có retry, dùng một **ready signal** có timeout/bảo vệ lỗi thay vì mặc định tạo bean đã thành công.

### 4.1. Chờ signal có giới hạn khi cần consumer khởi tạo đồng bộ

Ví dụ ở lớp orchestration, sử dụng `CompletableFuture` được hoàn thành khi có **secret đầu tiên**:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<DbCredentialState.DbCredentials> initialSecret =
        new CompletableFuture<>();

// Trong listener đã được đăng ký trước start:
if (event instanceof SecretLeaseCreatedEvent created) {
    credentialHolder.accept(created.getSecrets());
    initialSecret.complete(credentialHolder.requireCurrent());
}

// Sau khi start container, ở một worker/khâu startup được phép block:
DbCredentialState.DbCredentials initial = initialSecret.get(
        Duration.ofSeconds(15).toMillis(), TimeUnit.MILLISECONDS);
~~~

Đoạn mã trên là **mảnh ghép minh họa**, phụ thuộc vào các biến và listener đã có. Không đặt lệnh `get(...)` trong callback của chính scheduler hoặc event thread; như vậy có nguy cơ tự chặn nguồn phát signal. Ở production, timeout cần dẫn đến fail-fast hoặc readiness=false và cơ chế retry đã quản lý.

### 4.2. Readiness khác với bean đã được tạo

Một bean `OrdersService` có thể tồn tại trong Spring context nhưng phụ thuộc của nó chưa sẵn sàng. Chỉ công bố **READY** sau khi:

1. Nhận secret hợp lệ từ Vault.
2. Xác minh thông tin có đủ trường và kiểu dữ liệu đúng.
3. Tạo hoặc cập nhật consumer bằng secret mới.
4. Kiểm thử kết nối/đường truyền cần thiết nếu có.
5. Xác nhận consumer đang phục vụ bằng credential mới.

Không coi `SecretLeaseCreatedEvent` tự thân là bằng chứng connection pool đã được cập nhật thành công.

## 5. Mẫu ManagedSecret cho Spring Vault 4.1+

Spring Vault 4.1 bổ sung **`ManagedSecret`** và **`SecretRegistrar`**. `ManagedSecret` kết nối một `RequestedSecret` với callback tiêu thụ dữ liệu, giúp bạn tránh tự quản lý đăng ký listener ở mức thấp trong trường hợp phổ biến.

Ví dụ bean đăng ký cặp username/password vào holder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.lease.ManagedSecret;
import org.springframework.vault.core.lease.ManagedSecret.UsernamePassword;

@Configuration(proxyBeanMethods = false)
class ManagedCredentialsConfiguration {

    @Bean
    DbCredentialState dbCredentialState() {
        return new DbCredentialState();
    }

    @Bean
    ManagedSecret ordersCredentials(DbCredentialState state) {
        return ManagedSecret.rotating(
                "database/creds/orders",
                secrets -> secrets.as(UsernamePassword::from)
                        .applyTo((username, password) ->
                                state.accept(
                                        java.util.Map.of(
                                                "username", username,
                                                "password", password.toString()))),
                failure -> state.markDegraded());
    }
}
~~~

`ManagedSecret.rotating(path, secretsConsumer, errorConsumer)` gọi callback **khi lần đầu lấy secret và khi secret được rotate**. Callback có quyền truy cập kiểu hóa dữ liệu thông qua `UsernamePassword::from`; error callback nhận lỗi tương ứng. Với `AbstractVaultConfiguration` trên Spring Vault 4.1+, các bean `SecretRegistrar` được phát hiện/đăng ký trước khi container start.

**Điều kiện triển khai:** `ManagedSecret` được bổ sung ở **4.1+**. Nếu dự án dùng phiên bản 3.x/4.0, cần dùng `SecretLeaseContainer` + listener như mục 2 hoặc nâng cấp có kiểm tra tương thích. Đừng giả định việc tạo `@Bean ManagedSecret` khiến credential có mặt ngay trong constructor của bean khác; callback vẫn phụ thuộc vào lifecycle start và việc Vault trả secret.

### 5.1. Lý do không nên tạo pool đang kết nối trong constructor của ManagedSecret

Ví dụ trong tài liệu Spring Vault có thể đưa callback trực tiếp tới các setter của Hikari pool, nhưng một số DataSource khởi tạo/kiểm tra connection ngay trong `@Bean`, `afterPropertiesSet` hoặc `@PostConstruct`. Nếu tạo connection pool đang hoạt động **trước lúc credential được cập nhật**, khởi động có thể thất bại.

Vì vậy, khi sử dụng `ManagedSecret` với một consumer phức tạp:

- Có thể tạo **đối tượng cấu hình hoặc holder** sớm nhưng trì hoãn kết nối thật.
- Đảm bảo managed secret được đăng ký trước khi container bắt đầu phát event.
- Nếu pool cần credential ngay trong constructor, phải khởi tạo pool **sau khi nhận credential**, qua startup orchestrator/ready signal đã kiểm soát.
- Ở lần rotation, chuẩn bị pool mới và kiểm chứng trước khi chuyển traffic.

Cách tiếp cận này hữu ích cho JDBC, Redis, Kafka, HTTP client hoặc bất kỳ thư viện nào giữ credential trong một instance lâu dài.

## 6. Rotation không đồng nghĩa consumer đã đổi credential

Giả sử Vault cấp credential database động:

~~~json
{
  "lease_id": "database/creds/orders/<lease-id>",
  "lease_duration": 1800,
  "renewable": true,
  "data": {
    "username": "v-orders-01",
    "password": "<REDACTED>"
  }
}
~~~

Sau một chu kỳ, Vault có thể cấp cặp `v-orders-02` / password mới. Container phát `SecretLeaseRotatedEvent` (là dạng `SecretLeaseCreatedEvent`); listener nhận dữ liệu mới. Tuy nhiên:

- `HikariDataSource#setUsername` và `setPassword` có thể thay cấu hình tạo **kết nối mới**, nhưng các connection đã mở không tự xác thực lại.
- Client HTTP dùng Basic/Auth header có thể đã cache credential cũ.
- Transaction đang hoạt động có thể tiếp tục trên connection trước rotation.
- Nếu lease cũ hết hạn hoặc bị revoke, kết nối mới với username/password cũ có thể bị từ chối.

Cần thiết kế việc thay consumer như một thao tác có kiểm chứng:

~~~mermaid
flowchart TD
    A[Nhận SecretLeaseCreatedEvent / RotatedEvent] --> B[Đọc credential mới]
    B --> C[Kiểm tra trường dữ liệu và TTL]
    C --> D[Chuẩn bị consumer / pool mới]
    D --> E{Kết nối thử thành công?}
    E -->|Có| F[Chuyển traffic sang consumer mới]
    F --> G[Ngừng cấp kết nối mới từ pool cũ]
    G --> H[Đóng pool cũ theo drain deadline]
    E -->|Không| I[Giữ readiness degraded, cảnh báo]
    I --> J[Thử phục hồi có giới hạn]
~~~

**Điểm an toàn:** tránh lập tức ghi đè state “READY” chỉ sau khi lưu password mới. Trạng thái nên phản ánh consumer **thực sự đã kết nối được**. Cũng không xoá dữ liệu consumer cũ trước khi có đường phục hồi phù hợp nếu lease cũ còn hợp lệ; khi lease đã hết thì không tiếp tục sử dụng credential cũ.

### 6.1. Giảm tác động lên request đang xử lý

Ứng dụng có thể dùng `AtomicReference<DbClient>` để chọn client mới cho request mới, trong khi cho phép request đang chạy hoàn tất trên client cũ trong phạm vi an toàn của lease. Cần có:

1. Kế hoạch **drain/close** các kết nối cũ.
2. Thời gian chờ trước khi lease cũ hết hạn.
3. Cách xử lý request đang sử dụng credential bị revoke.
4. Đồng bộ thứ tự event khi xảy ra nhiều lần rotation hoặc startup retry.

Không chạy các thao tác JDBC chặn lâu trong thread callback `SecretLeaseContainer`. Callback nên gửi tác vụ cập nhật sang executor có giới hạn và quan sát kết quả; một callback block lâu có thể ảnh hưởng các lượt renew khác.

## 7. @DependsOn, @PostConstruct, SmartLifecycle và ApplicationReadyEvent

Các cơ chế Spring thường được dùng để “xếp thứ tự”, nhưng giải quyết những vấn đề khác nhau:

| Cơ chế | Bảo đảm điều gì? | Có bảo đảm secret đã tải thành công? |
| --- | --- | --- |
| Constructor injection | Bean phụ thuộc được tạo trước. | **Không**; nó có thể chỉ là holder rỗng. |
| `@DependsOn` | Đảm bảo thứ tự tạo bean và một số quan hệ lifecycle. | **Không tự bảo đảm** Vault đã trả secret hoặc consumer đã áp dụng nó. |
| `@PostConstruct` / `InitializingBean` | Phần khởi tạo của bean được thực thi sau injection. | **Không** nếu container chưa start hoặc Vault lỗi. |
| `SmartLifecycle` + phase | Điều khiển tương đối thứ tự start/stop giữa các lifecycle beans. | **Không tuyệt đối**; còn phải kiểm tra sự kiện dữ liệu và readiness. |
| `ApplicationReadyEvent` | Spring Boot thông báo ứng dụng đã qua quá trình startup. | **Không đủ** nếu secret chưa tải thành công hoặc consumer vẫn lỗi. |
| **Ready signal có timeout và kiểm tra consumer** | Ứng dụng tự xác nhận dữ liệu và hệ thống đích đã dùng được. | **Có, trong phạm vi các điều kiện bạn kiểm tra**. |

Nếu dùng `SmartLifecycle`, các bean có phase thấp hơn thường start trước. Tuy nhiên không nên dựa duy nhất vào phase mặc định của thư viện; cần kiểm tra phiên bản và thời điểm `SecretLeaseContainer` phát event. Event có thể được thực thi trong thread start hoặc qua scheduler. Do đó startup orchestration nên dựa trên **việc đã nhận và áp dụng credential**, không chỉ một thứ tự bean giả định.

Với ứng dụng sử dụng `AbstractVaultConfiguration`, Spring Vault có thể khởi động container sớm để đáp ứng các property source/consumer cần secret trong bean initialization. Với **Spring Boot + Spring Cloud Vault**, kiểm tra auto-configuration thay vì tự tạo container thứ hai. Dùng hai container cùng quản lý một path có thể dẫn đến nhiều lease, tác vụ renew/revoke lặp và sự kiện khó kiểm soát.

## 8. Khi lỗi lấy secret ban đầu: fail-fast hay degraded?

Nếu Vault trả 403, 404 hoặc tạm thời không truy cập được trong lần lấy secret ban đầu, cần một quyết định rõ ràng theo yêu cầu ứng dụng:

| Kiểu dịch vụ | Ứng xử khi chưa có secret |
| --- | --- |
| Service mà mọi API phụ thuộc database | Có thể fail startup hoặc readiness=false cho đến khi lấy được secret và kết nối thành công. |
| Service có một tính năng phụ thuộc Vault | Giữ tính năng đó ở trạng thái unavailable, tránh chặn các chức năng không liên quan nếu an toàn. |
| Job xử lý theo lịch | Không nhận job mới cho đến khi secret hợp lệ; retry có giới hạn/backoff. |
| Đã có credential trước đó nhưng vừa lỗi renew | Đánh giá TTL và trạng thái lease trước khi quyết định còn được dùng không. |

Ví dụ sự kiện:

- `SecretLeaseCreatedEvent`: đã lấy được secret; cần tiếp tục kiểm tra consumer.
- `SecretNotFoundEvent`: không tìm được secret ở path tương ứng, có thể cần kiểm tra mount/path.
- `SecretLeaseErrorEvent` hoặc `LeaseErrorListener`: có exception khi truy vấn Vault hoặc tương tác với lease.
- `SecretLeaseExpiredEvent`: container phát hiện lease hết hạn; có thể quan sát **trễ** so với thời gian hết hạn thật do scheduling.

Không tạo username/password giả hoặc dùng Vault root token làm phương án fallback để startup “thành công”. Điều đó sẽ che mất lỗi quyền và tạo rủi ro bảo mật.

### 8.1. Phục hồi sau khi session token bị thay

Token Vault cấp lease có thể bị hết hạn/revoke, kéo theo lease liên quan. Sau khi `SessionManager` đăng nhập lại, ứng dụng có thể cần yêu cầu lại dynamic secret và cập nhật consumer, thay vì tiếp tục dùng credential thuộc phiên cũ.

Spring Vault có khả năng liên kết thông báo authentication với cơ chế quản lý secret qua `SecretLeaseContainer.getAuthenticationListener()` và `getAuthenticationErrorListener()` (tùy cấu hình phiên bản). Khi áp dụng, kiểm tra việc re-login thực sự dẫn tới việc lấy lại secret và consumer nhận lại dữ liệu phù hợp.

**Session token renewal** và **dynamic secret lease renewal** là hai vòng đời tách biệt. Token sống thêm không tự gia hạn database credential, và credential còn TTL không bảo đảm token của nó vẫn hợp lệ sau khi revoke.

## 9. Quan sát thứ tự đăng ký và readiness mà không làm lộ secret

Một số sự cố startup chỉ xuất hiện vài giây. Nên có metric/tracing ở các điểm:

| Sự kiện/metric | Ví dụ dữ liệu an toàn |
| --- | --- |
| Đăng ký secret | Logical path đã kiểm soát, mode ROTATE/RENEW, thời điểm. |
| Container start | Thời điểm start, số registration. |
| First secret acquired | Thời lượng từ start đến event, trạng thái parse hợp lệ. |
| Consumer applied | Thời lượng từ secret event đến kết nối kiểm tra thành công. |
| Rotation applied | Số lần xoay vòng thành công, thời gian chuyển pool. |
| Lease error / expired | Loại exception, số lần, trạng thái readiness. |

**Không ghi** vào log giá trị `username` động, `password`, `lease_id` đầy đủ, `client_token`, SecretID, JWT cloud hoặc toàn bộ JSON response Vault. Metric tag nên có cardinality thấp; không dùng lease ID/username làm tag.

Khi điều tra tình trạng “container đã start nhưng service không kết nối được database”, kiểm tra theo thứ tự: listener đăng ký lúc nào, registration diễn ra lúc nào, đã nhận `SecretLeaseCreatedEvent` chưa, consumer có áp dụng credential không và readiness đã thay đổi đúng chưa.

## 10. Kiểm thử tích hợp thứ tự khởi tạo

Nên dùng Vault test được cô lập, một database test và token workload có ACL tối thiểu. Đừng dùng root token khi muốn kiểm tra workflow auth/lease thực tế.

| Ca kiểm thử | Tình huống đầu vào | Kỳ vọng |
| --- | --- | --- |
| Listener đăng ký trước start | Gắn listener, đăng ký `RequestedSecret`, start. | Nhận event secret đầu tiên và consumer có credential hợp lệ. |
| Listener đến muộn | Start, đăng ký secret khi running, sau đó mới gắn listener. | Có thể **bỏ lỡ** event đầu tiên; test minh họa rủi ro, không dùng làm thiết kế. |
| Consumer tạo quá sớm | `@PostConstruct` gọi `requireCurrent()` khi holder rỗng. | Fail-fast có kiểm soát, không dùng giá trị rỗng để kết nối. |
| Consumer chờ readiness | Gắn listener trước start, chờ event có timeout. | Consumer khởi tạo thành công khi secret và connection đã hợp lệ. |
| Vault từ chối đọc secret | Token thiếu `read` trên database credential path. | Error listener nhận lỗi; readiness=false. |
| Rotation | Lease hết hạn/đến lúc rotate. | Nhận credential mới, tạo pool mới, consumer phục vụ bằng pool mới. |
| Duplicate registration | Đăng ký cùng một `RequestedSecret` hai lần ở 4.1+. | Chỉ một registration được quản lý; không kỳ vọng event ban đầu phát lại. |
| Session re-login | Token cũ hết hạn/revoke, auth method đăng nhập lại. | Secret được xin mới theo cơ chế đã cấu hình; consumer không dùng lease cũ bị revoke. |
| Slow consumer | Việc tạo pool mới chậm. | Callback không block lâu; readiness chỉ READY khi kết nối thử thành công. |

### 10.1. Kiểm thử thứ tự với event recorder

Trong test, có thể ghi nhận các trạng thái **không chứa secret**:

~~~text
listener_registered
secret_registered
container_started
first_secret_received
consumer_initialized
consumer_ready
~~~

Trình tự mong đợi:

~~~text
listener_registered < secret_registered <= container_started
container_started <= first_secret_received < consumer_ready
~~~

Thời điểm `consumer_initialized` (tạo wrapper/holder) có thể sớm hơn `first_secret_received`, nhưng thời điểm nó **bắt đầu sử dụng credential thật** phải sau khi secret hợp lệ được áp dụng.

Ở test, chỉ so sánh thứ tự event đã ghi; không log raw payload để làm bằng chứng.

## 11. Bài thực hành tự đánh giá

**Câu 1.** Một bean JDBC đọc username/password từ holder trong `@PostConstruct`, trong khi `SecretLeaseContainer` mới start khi Spring context hoàn tất tạo các singleton. Vì sao lỗi?

**Đáp án:** `@PostConstruct` có thể chạy **trước** `SmartLifecycle.start()` của container. Holder chưa nhận `SecretLeaseCreatedEvent` nên chưa có credential. Cần trì hoãn kết nối hoặc bảo đảm quy trình lấy secret sớm có kiểm tra readiness.

**Câu 2.** Nếu `container.register(requested)` đã được gọi trong lúc container đang chạy, sau đó mới gắn `addLeaseListener`, listener có chắc nhận được secret ban đầu?

**Đáp án:** Không. Container có thể đã lấy secret và phát event trước khi gắn listener; Spring Vault không bảo đảm replay payload đầu tiên khi registration đã active. Nên gắn listener **trước** khi đăng ký/start.

**Câu 3.** `SecretLeaseRotatedEvent` được phát nhưng Hikari pool vẫn sử dụng password cũ. Đã hoàn thành rotation chưa?

**Đáp án:** Container đã lấy secret mới, nhưng **consumer chưa hoàn tất chuyển credential**. Cần tạo/kiểm tra pool mới, chuyển traffic và drain/close pool cũ trong giới hạn lease.

**Câu 4.** Có `@DependsOn("secretLeaseContainer")` trên bean consumer. Có thể bỏ kiểm tra readiness?

**Đáp án:** Không. `@DependsOn` giúp điều khiển phụ thuộc Spring bean, không xác minh Vault request đã thành công và connection pool dùng credential mới.

**Câu 5.** Cùng một `RequestedSecret` được đăng ký lại sau khi container đã running, có tự phát lại `SecretLeaseCreatedEvent` cho consumer mới không?

**Đáp án:** Không được giả định như vậy. API 4.1 quản lý các registration trùng như một registration và không replay payload ban đầu. Consumer mới nên lấy snapshot từ state holder hoặc được orchestrate để nhận secret mới một cách có kiểm soát.

**Câu 6.** Khi nào nên dùng `ManagedSecret` thay cho tự đăng ký listener?

**Đáp án:** Khi dùng Spring Vault 4.1+ và muốn gắn secret rotation trực tiếp với callback nhận credential. Vẫn phải đảm bảo bean tiêu thụ không dùng credential trước khi callback đầu tiên chạy.

**Câu 7.** Nếu secret ban đầu chưa đọc được vì Vault trả 503, có nên tự tạo database password giả và đánh READY?

**Đáp án:** Không. 503 là lỗi tạm thời cần retry/backoff hoặc fail-fast/degraded theo yêu cầu hệ thống. Readiness chỉ READY khi đã nhận secret thật và consumer có thể dùng được.

## 12. Ghi nhớ và nguồn đối chiếu

- **Đúng thứ tự:** tạo consumer state → gắn listener → đăng ký `RequestedSecret` → khởi chạy container → chờ secret đầu tiên → áp dụng vào consumer → công bố readiness.
- **Start mới kích hoạt:** chỉ tạo `SecretLeaseContainer` hoặc `RequestedSecret` không đồng nghĩa Vault đã cấp credential.
- **Listener đến muộn có thể bỏ lỡ event**; đăng ký lại secret đã active không phát lại payload đầu tiên theo contract 4.1+.
- **`@PostConstruct` và `@DependsOn` không tự giải quyết mọi race** vì bean initialization và lấy external secret diễn ra theo các lifecycle khác nhau.
- **`ManagedSecret` 4.1+** giúp đăng ký callback gọn hơn, nhưng không tự bảo đảm connection pool đã khởi tạo và hoạt động.
- **Rotation chỉ hoàn thành ở cấp ứng dụng** khi consumer thực sự sử dụng credential mới; cần kiểm soát pool/connection hiện có.
- **Readiness có điều kiện**, trong khi lỗi fetch/renew/rotation cần được theo dõi và phục hồi mà không làm lộ secret.

Tài liệu chính thức:

1. [Spring Vault – Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html): lifecycle, thứ tự listener, ManagedSecret và khởi tạo consumer.
2. [Spring Vault – SecretLeaseContainer Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html): `register`, `start`, lease management.
3. [Spring Vault – SecretsRegistry Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretsRegistry.html): registration và việc không phát lại event đầu tiên.
4. [Spring Vault – ManagedSecret Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/ManagedSecret.html): callback nhận secret và error.
5. [Spring Vault – SecretLeaseCreatedEvent Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/SecretLeaseCreatedEvent.html): payload `getSecrets()`.
6. [HashiCorp Vault – Lease, Renew, Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease): lease TTL và tương tác của server.

Khi kiểm soát được **thời điểm đăng ký**, **thời điểm secret xuất hiện** và **thời điểm consumer thật sự sẵn sàng**, ứng dụng Spring Vault tránh được lỗi khởi tạo quá sớm, bỏ lỡ event đầu tiên và dùng credential cũ sau rotation.
