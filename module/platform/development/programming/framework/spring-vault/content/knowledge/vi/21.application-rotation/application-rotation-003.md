# ManagedSecret và SecretRegistrar từ Spring Vault 4.1

Một ứng dụng Java dùng **Spring Vault** thường lấy thông tin đăng nhập database từ **HashiCorp Vault** qua `VaultTemplate`. Với dynamic secrets, Vault có thể cấp cặp username/password có lease ngắn. Nếu ứng dụng chỉ đọc credential một lần khi khởi động, đến lúc lease hết hạn hoặc tài khoản bị thu hồi, các kết nối mới sẽ thất bại. Ứng dụng cần một cơ chế nhận credential mới, chuyển credential đến consumer và quản lý vòng đời renew/rotation.

Từ **Spring Vault 4.1**, hai API quan trọng cho bài toán này là **`ManagedSecret`** và **`SecretRegistrar`**. `ManagedSecret` cung cấp cách khai báo một secret cần được quản lý cùng callback nhận giá trị khi secret được tạo hoặc xoay vòng. `SecretRegistrar` là hợp đồng để đăng ký các `RequestedSecret` với `SecretsRegistry`, thường được triển khai bởi `SecretLeaseContainer`.

Bài học nằm trong chương **Xoay vòng trong ứng dụng**. Mục tiêu là hiểu chính xác vai trò từng API, triển khai callback nhận username/password đúng kiểu dữ liệu, kết nối vòng đời lease với consumer Java, thiết kế startup/shutdown và kiểm thử các lỗi thực tế. Phần này thuộc module **SPRING_VAULT**, nơi `VaultTemplate`, workload authentication, KV, Transit, PKI, token và lease đều được điều khiển bằng chính sách quyền hạn của Vault.

## 1. Vấn đề mà ManagedSecret giải quyết

Xét ứng dụng `orders-api` kết nối PostgreSQL. Vault Database secrets engine cấp tài khoản tạm thời:

~~~text
GET /v1/database/creds/orders-reader

lease_id: database/creds/orders-reader/...
lease_duration: 1800
renewable: true
data.username: v-orders-reader-...
data.password: [được che]
~~~

Ứng dụng có thể đọc phản hồi bằng `VaultTemplate`. Nhưng thao tác đọc đơn lẻ không tự bảo đảm rằng:

- Lease sẽ được gia hạn đúng thời điểm và không vượt giới hạn Vault cho phép.
- Khi lease không thể gia hạn hoặc hết hạn, credential mới sẽ được yêu cầu.
- JDBC connection pool, HTTP client hay component đang giữ password cũ sẽ chuyển sang bản mới.
- Lỗi quyền, lỗi mạng và TTL sẽ được theo dõi mà không rò rỉ secret.
- Tác vụ gia hạn và đăng ký listener sẽ dừng khi Spring `ApplicationContext` đóng.

`SecretLeaseContainer` từ các phiên bản Spring Vault trước đã xử lý việc yêu cầu secret, renew/rotate theo lease và phát sự kiện. Spring Vault 4.1 thêm `ManagedSecret` để gắn **secret path → callback consumer** theo lối khai báo, giảm lượng mã lặp để tự đăng ký và lọc từng sự kiện.

### Điều ManagedSecret thực sự làm và không làm

| Khả năng | Có thuộc ManagedSecret / hạ tầng Spring Vault? | Phần ứng dụng vẫn phải chịu trách nhiệm |
| --- | --- | --- |
| Khai báo path secret cần xoay vòng | Có, qua `ManagedSecret.rotating(path, callback)`. | Chọn path và Vault role đúng engine, đúng quyền. |
| Đăng ký secret với registry | Có, vì `ManagedSecret implements SecretRegistrar`. | Bảo đảm có registry/container được tạo và khởi động đúng. |
| Nhận secret ban đầu và secret mới khi rotation | Có, callback `SecretAccessor`. | Chuyển sang cấu trúc/consumer phù hợp, xử lý lỗi cập nhật. |
| Renew lease và yêu cầu secret mới | `SecretLeaseContainer` thực hiện theo chế độ requested secret và điều kiện TTL. | Quan sát lỗi, xác định SLA và chiến lược fallback. |
| Thay connection đang hoạt động trong JDBC pool | Không phải bảo đảm tự động. | Quản lý rotation của pool/connection và dừng dùng credential cũ. |
| Xác thực Vault token cho mọi request | Thuộc `ClientAuthentication`/`SessionManager`. | Cấu hình workload auth, policy tối thiểu, token lifecycle. |
| Xoay private key/certificate PKI | Có API khác `ManagedCertificate`/`CertificateContainer` từ 4.1. | Tích hợp TLS keystore/SSLContext/reload theo hệ thống. |
| Xoay khóa Transit | Không phải mục đích của `ManagedSecret`. | Dùng cơ chế Transit key rotation và policy phù hợp. |

**Phân biệt quan trọng:** *renew* giữ lease hiện tại hợp lệ lâu hơn khi được Vault cho phép; *rotation* nhận một phiên bản credential mới. Callback `ManagedSecret.rotating` được gọi khi nhận secret mới ban đầu và khi secret được xoay vòng; một lần **renew thành công không nhất thiết gọi lại callback như một rotation**.

## 2. Kiến trúc và mối quan hệ API từ Spring Vault 4.1

~~~mermaid
flowchart TD
    A["Workload identity<br/>Kubernetes / AppRole / Cloud"] --> B["ClientAuthentication"]
    B --> C["SessionManager: Vault client token"]
    C --> D["VaultTemplate / VaultOperations"]
    D --> E["Vault Database engine"]
    E --> F["Dynamic username/password + lease"]
    H["ManagedSecret bean"] --> I["SecretRegistrar.registerSecret"]
    J["Custom SecretRegistrar bean"] --> I
    I --> K["SecretsRegistry"]
    K --> L["SecretLeaseContainer"]
    D --> L
    L --> M["Renew lease / request rotating secret"]
    M --> N["Secret lease events"]
    N --> O["ManagedSecret callback"]
    O --> P["Application credential consumer"]
    P --> Q["New connections / client reconfiguration"]
~~~

Các thành phần cần biết:

| API | Gói Java | Vai trò |
| --- | --- | --- |
| `ManagedSecret` | `org.springframework.vault.core.lease` | Đối tượng khai báo một secret và callback nhận secret mới. |
| `SecretRegistrar` | `org.springframework.vault.core.lease` | Functional interface có phương thức `registerSecret(SecretsRegistry)`, được giới thiệu từ 4.1. |
| `SecretsRegistry` | `org.springframework.vault.core.lease` | Hợp đồng `register`/`unregister` các `RequestedSecret`; `SecretLeaseContainer` triển khai. |
| `SecretLeaseContainer` | `org.springframework.vault.core.lease` | Lifecycle component yêu cầu secret, renew lease, rotate theo mode, phát sự kiện và đóng tài nguyên. |
| `RequestedSecret` | `org.springframework.vault.core.lease.domain` | Định nghĩa path và mode `renewable` hoặc `rotating`. |
| `ManagedSecret.SecretAccessor` | Kiểu lồng trong `ManagedSecret` | Truy cập dữ liệu secret qua `getRequiredString`, `getString`, `as(...)`… |
| `ManagedSecret.UsernamePassword` | Kiểu lồng trong `ManagedSecret` | Adapter có `from(SecretAccessor)`, `getUsername()`, `getPassword()` và `applyTo(...)`. |
| `AbstractVaultConfiguration` | `org.springframework.vault.config` | Cấu hình Spring Vault có thể nhận các registrar bean và đăng ký với container trước lúc chạy. |

`SecretsRegistry` không tự chạy background jobs. Thường **`SecretLeaseContainer`** đảm nhận điều này, và `ManagedSecret` mô tả *đăng ký gì* cùng *chuyển secret đến ai*. Khi ứng dụng dùng **Spring Cloud Vault/Spring Boot**, cần kiểm tra cấu hình tự động và phiên bản thực tế; không mặc định mọi context đều tạo và phát hiện registrar như `AbstractVaultConfiguration`.

## 3. Chu trình từ đăng ký đến xoay vòng

~~~mermaid
sequenceDiagram
    autonumber
    participant Spring as Spring ApplicationContext
    participant Registrar as ManagedSecret / SecretRegistrar
    participant Container as SecretLeaseContainer
    participant Vault as HashiCorp Vault
    participant Consumer as Ứng dụng / credential consumer
    Spring->>Registrar: Tạo registrar bean
    Registrar->>Container: registerSecret(registry) trước startup
    Spring->>Container: start()
    Container->>Vault: Đọc database/creds/orders-reader
    Vault-->>Container: Username/password, lease_id, TTL
    Container->>Registrar: Thông báo secret mới
    Registrar->>Consumer: Callback cập nhật credential
    loop Theo TTL và renewability
        Container->>Vault: Renew lease khi đủ điều kiện
        Vault-->>Container: TTL máy chủ thực cấp hoặc lỗi
    end
    Container->>Vault: Request new secret khi cần rotation
    Vault-->>Container: Credential mới, lease mới
    Container->>Registrar: Callback với secret mới
    Registrar->>Consumer: Chuẩn bị consumer cho credential mới
    Spring->>Container: stop / destroy khi context đóng
~~~

Giá trị `lease_duration` do Vault trả về và đồng hồ của scheduler điều khiển quyết định gia hạn. Secret lease có thể hết hạn trong lúc Vault không sẵn sàng, nên ứng dụng không được suy rằng callback mới luôn xuất hiện đúng từng giây như lịch. Thời gian chuyển pool sang credential mới, trạng thái các connection cũ và deadline của credential cũ phải được kiểm thử riêng.

## 4. Điều kiện trước khi triển khai

Ví dụ xuyên suốt dùng một Vault test/staging với Database secrets engine mount tại `database/`, role `orders-reader` và ứng dụng Java chạy Spring Vault **4.1.x**.

Cần bảo đảm:

1. Vault có Database connection và role `orders-reader` thật; đọc `database/creds/orders-reader` sẽ tạo credential động với lease. Chỉ bật và cấu hình engine trong môi trường được quản trị phù hợp.
2. Workload có một auth method hợp lệ (AppRole, Kubernetes, GCP, v.v.) để lấy Vault token. Không đưa root token hoặc service account private key vào source.
3. Policy của Vault token được phép `read` path cấp credential, nhưng không có quyền quản trị ngoài nhu cầu.
4. Java client dùng HTTPS và xác minh CA/hostname Vault. Đường tới Vault và Database có timeout hữu hạn.
5. Spring context có `SecretLeaseContainer`/registrar được đăng ký đúng. Nếu ứng dụng đã dùng Spring Cloud Vault auto-configuration, kiểm tra tránh tạo hai container cho cùng path.
6. Consumer có cách thay credential an toàn và khả năng quan sát rotation thất bại.

Ví dụ Vault policy cấp quyền đọc dynamic credential:

~~~hcl
path "database/creds/orders-reader" {
  capabilities = ["read"]
}
~~~

Khi có KV v2, `secret/data/...` là một đường API khác. Không dùng `ManagedSecret` làm lý do mở rộng quyền `secret/*`. Một số credential rất nhạy cảm; log nên ghi trạng thái operation mà không ghi `username`, `password`, full response hay token.

## 5. Viết ManagedSecret bean theo API 4.1

### 5.1. Cách tối thiểu: callback nhận username/password

Một cấu hình Java minh họa API đã được công bố của Spring Vault 4.1:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.lease.ManagedSecret;
import org.springframework.vault.core.lease.ManagedSecret.UsernamePassword;

@Configuration(proxyBeanMethods = false)
class OrdersSecretConfiguration {

    @Bean
    ManagedSecret ordersDbCredentials(RotatingCredentialStore store) {
        return ManagedSecret.rotating(
                "database/creds/orders-reader",
                secrets -> secrets.as(UsernamePassword::from)
                        .applyTo(store::replace)
        );
    }
}
~~~

Đoạn trên tạo bean `ManagedSecret`. Khi nhận secret mới, `SecretAccessor` được chuyển sang `UsernamePassword`, rồi `applyTo` gọi `store.replace(username, password)`. Kiểu password của callback là **`CharSequence`**, không phải lúc nào cũng là `String`, nên cần chú ý kiểu dữ liệu khi kết nối với API consumer.

Dưới đây là một implementation đơn giản cho `RotatingCredentialStore`, minh họa cập nhật **cặp username/password như một snapshot**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class RotatingCredentialStore {

    public record Credentials(String username, String password) {}

    private final AtomicReference<Credentials> current = new AtomicReference<>();

    public void replace(String username, CharSequence password) {
        if (username == null || password == null) {
            throw new IllegalArgumentException("Incomplete Vault credentials");
        }
        current.set(new Credentials(username, password.toString()));
    }

    public Credentials currentRequired() {
        Credentials result = current.get();
        if (result == null) {
            throw new IllegalStateException("Database credentials not available yet");
        }
        return result;
    }
}
~~~

Để ví dụ trên tạo đủ bean trong Spring:

~~~java
@Bean
RotatingCredentialStore rotatingCredentialStore() {
    return new RotatingCredentialStore();
}
~~~

Đăng ký phương thức `@Bean` này trong cùng lớp `@Configuration` hoặc cấu hình được import. **Đây là store minh họa**, chưa trực tiếp thay connection pool. Nó giữ password dạng `String` trong bộ nhớ cho đến khi bị thay; ứng dụng thật phải giới hạn tuổi thọ và bản sao, quản lý quyền truy cập, dọn tài nguyên và chọn kiểu lưu/handler phù hợp.

Có thể viết callback trực tiếp vào component xử lý rotation thay vì tạo store. Quan trọng là thao tác **cập nhật cả cặp** phải tránh thời điểm dùng username mới với password cũ, và component cuối phải áp dụng credential mới lên những request/kết nối được tạo tiếp theo.

### 5.2. Cung cấp error callback

`ManagedSecret.rotating` có overload nhận cả `Consumer<Throwable>` để xử lý lỗi liên quan đến secret:

~~~java
@Bean
ManagedSecret ordersDbCredentials(RotatingCredentialStore store) {
    return ManagedSecret.rotating(
        "database/creds/orders-reader",
        secret -> secret.as(ManagedSecret.UsernamePassword::from)
                        .applyTo(store::replace),
        failure -> {
            // Ghi tên loại lỗi và trạng thái, không ghi password/token hay HTTP body.
            System.err.println("Vault credential rotation error type: "
                    + failure.getClass().getSimpleName());
        });
}
~~~

Hai ví dụ `ordersDbCredentials` là **hai lựa chọn thay thế** cho cùng một bean; chỉ sử dụng một cách trong ứng dụng. Trong sản phẩm, thay `System.err` bằng metrics/logger có kiểm soát và chính sách cảnh báo. Error callback không tự sửa được lỗi: phải phân loại lỗi HTTP 403, token hết hạn, mất kết nối, Vault sealed, lỗi secret engine hoặc lỗi chính consumer.

### 5.3. Đọc secret với SecretAccessor

`ManagedSecret.SecretAccessor` cung cấp các phương thức như:

~~~java
String username = secrets.getRequiredString("username");
String password = secrets.getRequiredString("password");
long retryHint = secrets.getLong("retry_hint", 0);
~~~

Đoạn trên chỉ minh họa khi biến `secrets` thuộc kiểu `ManagedSecret.SecretAccessor`. `getRequiredString` sẽ báo lỗi nếu không có dữ liệu cần thiết; `getString` có thể trả null. Trường `retry_hint` chỉ là ví dụ giả định, không phải trường mặc định mà Vault Database engine trả.

Sử dụng `UsernamePassword::from` thuận tiện khi response thực sự có cặp `username/password`. Với secret có schema khác, khai thác `getRequiredString(key)` hoặc adapter riêng. Không ép một KV secret hoặc response Transit vào adapter username/password nếu cấu trúc không phù hợp.

## 6. SecretRegistrar: hợp đồng đăng ký mà ManagedSecret triển khai

Định nghĩa rút gọn theo Spring Vault 4.1:

~~~java
@FunctionalInterface
public interface SecretRegistrar {
    void registerSecret(SecretsRegistry registry);
}
~~~

`SecretRegistrar` là giao diện chức năng, còn `ManagedSecret` là một implementation có sẵn. Khi muốn dùng listener hoặc điều kiện đăng ký tùy biến, có thể tạo registrar của riêng mình.

Ví dụ một registrar **thay thế**, sử dụng path `database/creds/billing-reader` để không đăng ký trùng với ví dụ `orders-reader`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.lease.SecretRegistrar;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.SecretLeaseRotatedEvent;

@Configuration(proxyBeanMethods = false)
class BillingLeaseConfiguration {

    @Bean
    SecretRegistrar billingReaderRegistrar() {
        RequestedSecret requested =
                RequestedSecret.rotating("database/creds/billing-reader");

        return registry -> registry.register(requested, event -> {
            if (event instanceof SecretLeaseRotatedEvent) {
                // Signal application-level rotation without logging the secret body.
                System.out.println("Billing credential rotation event observed");
            }
        });
    }
}
~~~

Về mặt API, `SecretsRegistry.register(RequestedSecret, LeaseListener)` cho phép gắn listener riêng cho secret đó, còn `unregister(RequestedSecret)` xóa đăng ký và listener liên quan. Ví dụ listener ở trên **chỉ quan sát sự kiện**, chưa áp dụng credential vào billing pool. Nếu cần propagation dữ liệu, dùng `ManagedSecret` hoặc xử lý nội dung event có kiểm soát.

Nếu ứng dụng không dùng `AbstractVaultConfiguration` hoặc phần tự động cấu hình có hỗ trợ phát hiện registrar, phải tự bảo đảm `registerSecret(...)` được gọi với đúng registry **trước khi container start**. Chỉ khai báo bean tùy ý không đồng nghĩa mọi phiên bản/kiểu cấu hình sẽ tự động nhận nó.

### Đăng ký thủ công khi tự sở hữu SecretLeaseContainer

Trong một cấu hình test/manual, phần cốt lõi của thứ tự là:

~~~java
SecretLeaseContainer container = new SecretLeaseContainer(vaultOperations);
ManagedSecret managed = ManagedSecret.rotating(
        "database/creds/orders-reader",
        secret -> secret.as(ManagedSecret.UsernamePassword::from)
                        .applyTo(credentialStore::replace));

managed.registerSecret(container);  // đăng ký trước startup
container.afterPropertiesSet();
container.start();

// Khi hoàn tất, gọi container.destroy() theo lifecycle/ownership.
~~~

`vaultOperations` và `credentialStore` là các biến đã được tạo trong fixture hoặc DI; khối này minh họa thứ tự API, không phải một Java class standalone. Trong Spring context, ưu tiên để container là bean được quản lý lifecycle và không gọi `start()` lần hai tùy tiện. Để tránh trùng đăng ký, chọn một đường sở hữu: registrar bean được cấu hình tự động **hoặc** tự đăng ký vào container thủ công.

## 7. Renew và rotation: chính xác điều gì kích hoạt callback?

`RequestedSecret` có hai mode:

| Mode | Cách dùng | Kỳ vọng đúng |
| --- | --- | --- |
| `RequestedSecret.renewable(path)` | Theo dõi một lease để gia hạn khi còn đủ điều kiện. | Lease cũ tiếp tục được dùng đến lúc hết hạn/không renew; không coi đây là cơ chế bắt buộc cấp credential mới. |
| `RequestedSecret.rotating(path)` | Renew khi thích hợp và yêu cầu secret mới sau khi lease được xem là expired. | Khi secret mới được cấp, container phát sự kiện rotation và `ManagedSecret` gọi consumer. |

Trong Spring Vault 4.1, `ManagedSecret.rotating(path, callback)` tạo một cấu hình phù hợp luồng rotation. Nếu lease vẫn renewable và được gia hạn liên tục, **không nhất thiết có credential mới sau mỗi mốc TTL ban đầu**. Nếu muốn ép đổi account định kỳ theo chính sách bảo mật, cần thiết kế TTL/max TTL/lease engine và rotation behavior theo yêu cầu, không chỉ nhìn tên phương thức `rotating` rồi giả định callback chạy mỗi 15 phút.

### Những sự kiện mà hạ tầng có thể phát

| Event | Diễn giải | Cách dùng |
| --- | --- | --- |
| `SecretLeaseCreatedEvent` | Secret/lease ban đầu được tạo. | Quan sát lần cấp đầu, nhận credential ban đầu. |
| `AfterSecretLeaseRenewedEvent` | Lease được gia hạn. | Đọc TTL thực tế được cấp; không nhầm với đổi password. |
| `SecretLeaseRotatedEvent` | Secret mới được cấp sau rotation. | Chuyển credential mới đến consumer. |
| `SecretLeaseExpiredEvent` | Container phát hiện lease expired. | Cảnh báo, chuyển chế độ dự phòng nếu credential cũ không còn dùng được. |
| `SecretLeaseErrorEvent` | Vault trả lỗi hoặc có lỗi I/O khi quản lý secret. | Metric/error handling, retry phù hợp; tuyệt đối không log bearer token. |
| `BeforeSecretLeaseRevocationEvent` và `AfterSecretLeaseRevocationEvent` | Lease bị thu hồi theo lifecycle. | Đối chiếu cleanup, audit; phân biệt before/after. |

Vault không đẩy trực tiếp từng sự kiện này đến Java. `SecretLeaseContainer` chủ động gọi Vault và phát event theo lịch/điều kiện quan sát, nên sự kiện expiry có thể đến **muộn hơn** thời điểm lease hết hạn thực tế trên server. Không dùng một event trễ làm bằng chứng credential vẫn còn hạn tại DB.

### TTL tuning của SecretLeaseContainer

Tài liệu Spring Vault 4.1 nêu giá trị mặc định tham khảo:

- **Expiry threshold:** 1 phút, để xác định thời điểm lease được coi là gần hết/expired theo logic container.
- **Minimum renewal TTL:** 10 giây, giảm renew quá dày khi TTL nhỏ.
- Scheduler dùng đồng hồ của `TaskScheduler` và TTL do Vault cấp.

Khi lease rất ngắn (ví dụ 10–20 giây trong test), các ngưỡng này có thể khiến hành vi khác với trực giác. Trong ứng dụng thật, đo TTL thực tế và chọn cấu hình phù hợp SLA, độ trễ mạng và khả năng cấp lại credential. Việc điều chỉnh không thay đổi giới hạn TTL tối đa do Vault/secret engine áp dụng.

## 8. Bài toán thật: cập nhật connection pool khi credential xoay vòng

Một ví dụ dễ viết là:

~~~java
dataSource.setUsername(newUsername);
dataSource.setPassword(newPassword);
~~~

Nhưng với một pool đã khởi động, thay hai giá trị cấu hình **không tự bảo đảm các connection đang mở được tạo lại**. Một số pool có thể khóa cấu hình sau khi start hoặc chỉ dùng credential lúc tạo connection. Trong callback, cập nhật mỗi thuộc tính rời rạc còn có thể gây trạng thái username mới + password cũ.

### Kiến trúc rotation an toàn hơn cho JDBC

1. **Nhận credential mới** dưới dạng một snapshot nguyên tử.
2. **Tạo connection/pool mới** bằng credential mới trong thành phần quản lý DB; kiểm tra kết nối và câu SQL `SELECT 1` với account được cấp.
3. **Chuyển consumer sang pool mới** theo cách atomic hoặc có synchronization phù hợp.
4. **Cho các transaction cũ hoàn tất** theo deadline rồi đóng pool cũ; bảo đảm chúng không tiếp tục dùng credential đã bị Vault revoke.
5. **Theo dõi lỗi chuyển tiếp**; nếu credential mới không hợp lệ, báo trạng thái degraded và quyết định rollback chỉ khi account cũ vẫn hợp lệ, không giả định mãi như vậy.
6. **Không ghi password** vào log, config dump, tracing hoặc exception.

~~~mermaid
flowchart LR
    A["ManagedSecret nhận credential mới"] --> B["Build pool B"]
    B --> C{"Kiểm DB bằng credential mới"}
    C -- "OK" --> D["Atomically switch A → B"]
    D --> E["Drain/close pool A"]
    C -- "Lỗi" --> F["Cảnh báo và giữ trạng thái theo SLA"]
~~~

Cách thực hiện phụ thuộc Hibernate/JPA, HikariCP, Spring transaction management và thời gian sống của transaction. Không nên thay `DataSource` bean khi consumer đã giữ reference trực tiếp đến pool cũ nếu không có một delegating data source hoặc integration rotation được thiết kế rõ ràng. Việc cập nhật store ở phần 5 là **bước nhận dữ liệu**, không phải phép kiểm chứng DB pool đã xoay vòng thành công.

## 9. Startup và thứ tự phụ thuộc giữa Spring beans

Trong Spring, `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()` của một consumer có thể chạy **trước** khi `SecretLeaseContainer` start và lấy credential đầu tiên. Nếu bean DataSource muốn tạo connection ngay khi khởi tạo, nó có thể thấy credential còn null.

Tài liệu Spring Vault 4.1 cho biết `AbstractVaultConfiguration` chủ động start container ngay trong lúc tạo bean để cung cấp secret sớm hơn. Tuy nhiên, thứ tự phụ thuộc của **ứng dụng** vẫn cần thiết kế và xác minh.

Một số cách tổ chức:

- Cho consumer có trạng thái `NOT_READY` cho đến khi callback lần đầu đã cung cấp credential và kiểm thử DB thành công.
- Tách thành phần **nhận credential** khỏi thành phần **mở connection**; tránh mở DB connection trong constructor khi secret chưa được cấp.
- Đảm bảo các bean phụ thuộc đúng vào thành phần sở hữu việc khởi tạo, không tạo vòng phụ thuộc bean giữa pool, registrar và container.
- Nếu dùng Spring Boot readiness probe, chỉ báo ready sau khi secret đầu tiên đã được áp dụng và consumer thật sự truy cập được backend.
- Nếu cần startup fail-fast khi Vault không sẵn sàng, định nghĩa timeout/error rõ ràng và test theo phiên bản; không chờ mãi trong bean initialization.

**Bẫy phụ thuộc:** nếu tạo bean `ManagedSecret mysqlCredentials(HikariDataSource dataSource)` nhưng chính bean `dataSource` cần credential từ callback để hoàn tất khởi tạo, có nguy cơ vòng phụ thuộc. Ví dụ tài liệu với `HikariDataSource` minh họa cách gắn callback; hệ thống production cần thiết kế dependency và lifecycle cụ thể, nhất là khi pool được dựng sớm.

## 10. Phân biệt ba vòng đời trong Spring Vault

Trong module Spring Vault, ứng dụng có thể quản lý cùng lúc:

| Vòng đời | Ví dụ | API/phần việc chính |
| --- | --- | --- |
| **Vault token/session** | Token từ Kubernetes/AppRole/GCP auth hết hạn hoặc được renew. | `ClientAuthentication`, `SessionManager`, thường `LifecycleAwareSessionManager`. |
| **Secret lease/rotation** | Dynamic database username/password được renew hoặc cấp lại. | `SecretLeaseContainer`, `RequestedSecret`, `ManagedSecret`, `SecretRegistrar`. |
| **Chứng chỉ PKI** | Certificate/private key hết `notAfter` và cần phát hành lại/reload. | Từ 4.1 có `ManagedCertificate`, `CertificateRegistrar`, `CertificateContainer`. |

Renew Vault client token **không đồng nghĩa** một dynamic secret được renew, và một `ManagedSecret` thành công **không tự cập nhật** private key TLS. Khi session token bị revoke hoặc đạt max TTL, các lease gắn với token đó có thể bị ảnh hưởng; cần kết nối listener/session phù hợp để quản lý secret sau re-login.

Với **KV v2** static secrets, một lần `VaultTemplate.opsForKeyValue(...).get(...)` đọc version hiện tại nhưng không mặc định sinh dynamic lease. Các cập nhật do người vận hành ghi vào KV không tự động trở thành callback rotation trên mọi client. Nếu muốn ứng dụng nhận thay đổi KV, phải có chiến lược refresh theo API/phiên bản và kiểm thử rõ. Các cải tiến hỗ trợ rotation cho một số secret không có lease trong Spring Vault 4.1 không biến Vault KV thành dịch vụ push event.

Với **Transit encryption**, khóa thường ở lại Vault, ứng dụng gọi `transit/encrypt`, `transit/decrypt` hoặc `transit/sign` theo policy. Key rotation của Transit có cơ chế riêng; không sử dụng `ManagedSecret.rotating` để kéo key material về JVM.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra |
| --- | --- | --- |
| Không chạy callback lần đầu | Registrar chưa được đăng ký, container chưa start, lỗi auth/Vault, bean lifecycle sai. | Xác minh `SecretRegistrar`, `SecretsRegistry`, container start và Vault HTTP. |
| Callback chạy khi start nhưng không chạy khi renew | Renew không phải rotation. | Theo dõi `AfterSecretLeaseRenewedEvent` và TTL; đợi rotation thật mới kỳ vọng callback mới. |
| Callback thấy thiếu `username/password` | Path trả schema khác hoặc sai engine. | Kiểm tra path `database/creds/...` và dữ liệu đã lọc; không in secret. |
| Vault trả `403` khi yêu cầu credential | Sai policy hoặc token không hợp lệ. | Kiểm auth role, mount path, token validity, `read` capability. |
| Vault HTTP `5xx`/timeout khi gia hạn | Vault/backend/mạng không sẵn sàng. | Quan sát retry, TTL còn lại, cảnh báo và recovery. |
| Có credential mới, JDBC vẫn authentication failed | Consumer chưa thay pool, connection đang dùng password cũ. | Kiểm cơ chế refresh/rebuild pool và quyền DB của credential mới. |
| Nhiều account DB được tạo không kiểm soát | Registrations trùng, tạo secret thủ công song song, vòng retry. | Đảm bảo một owner/path, số lượng requested secrets và lịch rotation. |
| Context đóng nhưng request renew còn chạy | Container tự tạo ngoài Spring, chưa destroy, task đang in-flight. | Kiểm bean lifecycle, `close()`, scheduler và cleanup. |
| Sau re-login token, secret không tiếp tục hoạt động | Lease cũ gắn với token đã hết/revoke, container/session listener thiếu. | Kiểm sự kiện auth và tái lấy credential theo contract. |

### Kiểm Vault bằng CLI một cách tối thiểu

Trong môi trường test có quyền phù hợp:

~~~bash
export VAULT_ADDR="https://vault.internal.example:8200"

# Kiểm tra có engine/role tương ứng, không in secret.
vault secrets list

# Yêu cầu credential thử nghiệm và chỉ xuất metadata lease.
vault read -format=json database/creds/orders-reader |
  jq '{lease_id_present: (.lease_id != ""),
       ttl_seconds: .lease_duration,
       renewable: .renewable}'
~~~

Lưu ý lệnh đọc `database/creds/...` có thể **tạo một tài khoản mới** ở database. Hạn chế dùng nó để polling hoặc chạy lặp trong CI. Response gốc chứa password, vì vậy chỉ lọc metadata ở công cụ được tin cậy và không lưu full body.

## 12. Kiểm thử đúng ba lớp: callback, lease và consumer

### 12.1. Unit test callback nhận giá trị đúng

Test `RotatingCredentialStore` độc lập để chứng minh cập nhật cặp credential là nguyên tử ở mức reference:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class RotatingCredentialStoreTest {

    @Test
    void replacesWholeCredentialSnapshot() {
        RotatingCredentialStore store = new RotatingCredentialStore();

        store.replace("orders-a", "secret-a");
        store.replace("orders-b", new StringBuilder("secret-b"));

        assertEquals("orders-b", store.currentRequired().username());
        assertEquals("secret-b", store.currentRequired().password());
    }

    @Test
    void failsBeforeFirstSecretIsAvailable() {
        RotatingCredentialStore store = new RotatingCredentialStore();

        assertThrows(IllegalStateException.class, store::currentRequired);
    }
}
~~~

Đây là test logic ứng dụng, **chưa chứng minh `ManagedSecret` được Spring đăng ký hay Vault đã rotate**. Không dùng password thật trong unit tests. Khi kiểm thử callback của `ManagedSecret`, có thể tạo fake registry và phát lease events bằng fixture/mocks theo API chính xác của phiên bản thư viện; tránh khẳng định Vault đã cấp credential mới chỉ vì `store.replace` chạy thành công.

### 12.2. Integration test với Vault Database engine thật

Dựng một Vault test instance với Database engine gắn PostgreSQL/MySQL test và role có TTL ngắn nhưng đủ rộng cho CI. Chạy:

1. Xác nhận auth của workload test và policy `read database/creds/orders-reader`. Không dùng root token cho business request.
2. Khởi động Spring `ApplicationContext` có `ManagedSecret` + container và đợi callback lần đầu với deadline hữu hạn.
3. Kiểm tra consumer thực sự dùng credential mới để kết nối DB test.
4. Khi Vault renew lease, xác minh callback rotation không bị tính nhầm là renew; quan sát TTL/lease events riêng.
5. Khi lease hết hạn hoặc không thể renew, đợi rotation theo lịch thật; xác minh callback có credential khác và pool kết nối mới thành công.
6. Kiểm tra account cũ bị thu hồi theo engine/backend trong điều kiện test. Test phải xem cả database, không chỉ HTTP status từ Vault.
7. Đóng context, xác minh scheduler/containers dừng, không tiếp tục cấp tài khoản mới hoặc giữ tài nguyên vô thời hạn.
8. Thu hồi tài khoản, lease và role do test tạo; không động tới environment khác.

Không dùng `Thread.sleep(10000)` làm bằng chứng rotation: thời gian CI, scheduler clock, expiry threshold và TTL server đều có thể thay đổi. Dùng polling có deadline và đọc state thực. Khi token/lease còn hợp lệ, Vault có thể renew thành công mà không phát credential mới; để test rotation, điều kiện phải khiến lease thực sự được thay thế theo thiết kế.

### 12.3. Ma trận lỗi tối thiểu

| Case | Đầu vào gây lỗi | Kỳ vọng |
| --- | --- | --- |
| Role Vault thiếu quyền | Login OK nhưng `read database/creds/...` bị 403 | Error callback/metric nhận lỗi; không in token/password. |
| Vault unavailable lúc startup | HTTP timeout hoặc 503 | Readiness không OK; lỗi có deadline, không treo bean initialization. |
| Lease không renewable | `renewable=false` | Cơ chế lấy credential mới theo mode rotation; không cố renew vô hạn. |
| Lease đạt max TTL | Server cấp TTL giảm dần hoặc từ chối renew | Không giả định `increment` được cấp; thực hiện rotation theo expiry. |
| Database không chấp nhận credential mới | Account mới sai quyền hoặc DB outage | Không báo rotation end-to-end thành công khi pool chưa kết nối. |
| Callback ném exception | Consumer update thất bại | Lỗi được quan sát và xử lý theo contract; không âm thầm che mất. |
| Vault token bị revoke | Lệnh renew/read trả 403 | Phân biệt token session với secret lease; thử reauth khi hỗ trợ. |
| Container đóng khi renew đang chạy | `ApplicationContext.close()` trong test | Không tạo tác vụ mới, không leak thread, cleanup được quan sát. |

## 13. Giám sát, bảo mật và vận hành

Trong môi trường production, nên đo cả **rotation event** và **rotation thực sự có hiệu lực tại consumer**:

| Tín hiệu | Lợi ích | Không đưa vào metric/log |
| --- | --- | --- |
| Secret acquisition/rotation count | Biết callback có được gọi và bao lâu một lần. | Secret data, username/password gốc. |
| Lease renewal success/failure | Phát hiện renew lỗi, gần TTL tối đa. | Token, toàn bộ response Vault. |
| TTL thực cấp/TTL còn lại | Cảnh báo trước expiry, điều chỉnh lịch. | Lease ID nguyên văn ở metrics label công khai. |
| Pool switch success/failure | Biết kết nối mới thực sự dùng credential mới. | Password, connection URL kèm credential. |
| Database authentication failures | Nhận biết user cũ bị revoke hoặc pool chưa đổi. | Thông tin kết nối nhạy cảm. |
| Vault login/reauth failures | Phân biệt lỗi workload identity/token với lỗi secret lease. | JWT, AppRole secret ID, Vault token. |
| Shutdown duration và task còn sót | Phát hiện leak container/scheduler hoặc deadlock. | Request/response body có secret. |

Khi rotation thất bại liên tục, phân loại HTTP `403` (token/role/policy), `5xx` (Vault/backend), DNS/TCP/TLS, lease nonrenewable và lỗi callback consumer. Retry có backoff/jitter, hữu hạn và theo TTL còn lại; không tạo tài khoản DB mới mỗi vài mili giây. Ghi log loại lỗi, operation, service logic và thời điểm, tránh wire log HTTP vì response chứa credential động.

Ứng dụng cần chính sách rõ ràng nếu không có credential mới: fail-fast, từ chối request cần DB, hoặc cho phép connection cũ hoàn tất trong thời gian credential cũ vẫn hợp lệ. Không tự tiếp tục sử dụng credential đã bị revoke hay trượt sang root token. Đối với credential được cấp bởi một ứng dụng nhưng dùng chung ngoài ý muốn, việc đóng context có thể revoke lease liên quan; hãy quản lý ownership và scope từng instance.

## 14. Checklist triển khai và bài tập tự đánh giá

Trước khi đưa `ManagedSecret` vào dự án thật, nhóm phát triển phải xác nhận:

1. **Phiên bản:** dự án sử dụng Spring Vault 4.1+; không dùng API mới với thư viện 3.x/4.0.
2. **Đúng secret:** `ManagedSecret.rotating(path, ...)` trỏ engine/path thực có credential và được policy cho phép.
3. **Đúng đăng ký:** `SecretRegistrar` bean được infrastructure phát hiện, hoặc gọi `registerSecret(registry)` trước container startup.
4. **Đúng lifecycle:** container/scheduler thuộc `ApplicationContext` hoặc có quy trình `destroy()` rõ; không tạo duplicate secret owner.
5. **Đúng schema:** `UsernamePassword::from` chỉ dùng khi response có username/password; callback xử lý `CharSequence` phù hợp.
6. **Đúng chuyển giao:** consumer áp dụng credential mới, không chỉ thay hai thuộc tính cấu hình; pool connection được refresh có kiểm chứng.
7. **Đúng lịch:** phân biệt renew với rotate, dùng TTL thật Vault trả về, có buffer và handling cho lease nonrenewable.
8. **Đúng bootstrap:** consumer cần secret trước khi sẵn sàng phải được sắp thứ tự và readiness phù hợp.
9. **Đúng phân quyền:** auth theo workload, Vault token policy tối thiểu; không dùng root/shared token để giải quyết lỗi rotation.
10. **Đúng quan sát và kiểm thử:** có integration test Vault + backend, negative cases, callback failure, token expiry và context shutdown.

Câu hỏi tự luyện tập:

- Một lease được gia hạn thành công ba lần, nhưng callback `ManagedSecret.rotating` chỉ chạy lúc đầu. Đây có nhất thiết là lỗi không?
- Vì sao `SecretRegistrar` có thể là lambda, trong khi `SecretLeaseContainer` mới là thành phần chạy task theo TTL?
- Khi ứng dụng có `HikariDataSource` đang phục vụ traffic, tại sao chỉ gọi `setUsername` và `setPassword` chưa chứng minh rotation thành công?
- Khi Vault token hết hạn, secret lease và session manager liên quan thế nào? Điều gì cần test sau re-login?
- Nếu muốn đổi certificate PKI cho TLS của ứng dụng, API nào phù hợp hơn `ManagedSecret`?

**Ghi nhớ:** từ Spring Vault 4.1, `ManagedSecret` mô tả **secret nào cần quản lý và gửi dữ liệu mới đến đâu**, còn `SecretRegistrar` chuẩn hóa việc **đăng ký yêu cầu quản lý** với `SecretsRegistry`. `SecretLeaseContainer` chịu trách nhiệm theo dõi TTL, renew và rotation. Phần không thể bỏ qua trong ứng dụng Java là đảm bảo callback thật sự chuyển credential mới vào consumer, xác minh kết nối sau rotation, xử lý lỗi an toàn và đóng các tài nguyên theo lifecycle.

### Tài liệu tham khảo API Spring Vault 4.1

- [Spring Vault – Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html).
- [ManagedSecret API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/ManagedSecret.html).
- [SecretRegistrar API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretRegistrar.html).
- [SecretsRegistry API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretsRegistry.html).
- [SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html).
