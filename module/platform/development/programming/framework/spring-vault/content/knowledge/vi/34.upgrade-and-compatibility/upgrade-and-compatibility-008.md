# ManagedSecret và lựa chọn quản lý xoay vòng theo phiên bản

## 1. Vấn đề thực tế và mục tiêu bài học

Một ứng dụng Spring Boot thường lấy secret từ HashiCorp Vault qua `VaultTemplate` hoặc `VaultOperations`. Lấy được mật khẩu, token hay chứng thư tại thời điểm khởi động **chưa đủ**: secret có thể hết TTL, bị thu hồi hoặc được cấp lại khi ứng dụng vẫn đang chạy. Nếu ứng dụng tiếp tục dùng thông tin cũ, lỗi có thể chỉ xuất hiện ở lần tạo kết nối JDBC tiếp theo hoặc khi kết nối TLS mới được mở.

Trong chương **Nâng cấp và tương thích** của module **SPRING_VAULT**, bài **ManagedSecret và lựa chọn quản lý xoay vòng theo phiên bản** trả lời ba câu hỏi:

1. `ManagedSecret` là gì, có mặt từ phiên bản nào, và khác `SecretLeaseContainer` thế nào?
2. Với phiên bản Spring Vault/Spring Cloud Vault đang triển khai, nên quản lý **renewal** hay **rotation** bằng API nào?
3. Làm sao bảo đảm khi secret đổi, **thành phần tiêu thụ secret** như HikariCP thật sự sử dụng credential mới, không chỉ cập nhật một biến trong bộ nhớ?

**Mốc tương thích quan trọng:** Spring Vault **4.1** (phát hành tháng 6/2026) giới thiệu `ManagedSecret` và `ManagedCertificate` để đơn giản hóa quản lý secret động. Các nhánh Spring Vault trước đó đã có `SecretLeaseContainer` và `RequestedSecret` cho renew/rotate nhưng không thể mặc định dùng API `ManagedSecret` của 4.1 trong dự án 3.x/4.0.

Bài trình bày ví dụ Java, bảng lựa chọn theo phiên bản, quy trình nâng cấp, lỗi thường gặp, kiểm thử tích hợp và vận hành theo policy/workload. Không có `SPECIAL_NOTE` bổ sung cho bài này.

## 2. Bốn khái niệm dễ bị nhầm lẫn

### 2.1. Đọc một lần, gia hạn lease và xoay vòng là ba hành động khác nhau

| Cách xử lý | Thao tác điển hình | Kết quả | Rủi ro khi áp dụng sai |
| --- | --- | --- | --- |
| **Read once** | `vaultOperations.read("database/creds/orders-ro")` | Nhận credential và lease tại thời điểm đó | Không có cơ chế renew/replace khi hết hạn |
| **Renew lease** | Gia hạn lease hiện có trước TTL | Có thể giữ credential hiện tại còn hiệu lực lâu hơn | Không được renew vô hạn; tùy quyền, max TTL và loại secret |
| **Rotate secret** | Xin **credential mới** khi credential cũ hết hiệu lực/theo chính sách | Có generation credential mới, lease mới | Consumer phải nhận và áp dụng giá trị mới; có thể làm gián đoạn kết nối |
| **Cập nhật config KV v2** | Ghi version mới của secret | KV `version` tăng | Không đồng nghĩa phát sinh lease hoặc sự kiện rotation tự động |

**Renew** và **rotate** không phải cùng một thao tác. Trong trường hợp database dynamic secret có lease, bộ quản lý có thể **renew trước** rồi chỉ **rotate khi không thể tiếp tục giữ lease** theo chế độ đã chọn. Ở những secret không có lease, không được tự suy ra một quy trình gia hạn Vault tương ứng.

### 2.2. Phân biệt bốn vòng đời

~~~mermaid
flowchart TD
    A[Workload identity: Kubernetes/JWT/AppRole] --> B[Vault auth token]
    B --> C[Vault Database secrets engine]
    C --> D[DB credential có lease]
    D --> E[Spring Vault lease manager]
    E --> F[Consumer: JDBC connection pool]
    G[KV v2 version] --> H[Cấu hình có version riêng]
    I[PKI certificate validity] --> J[TLS certificate rotation riêng]
    K[Transit key version] --> L[Quản lý khóa mật mã riêng]
~~~

- **Vault authentication token** cho phép workload gọi Vault; token có TTL, policy và quy tắc renew/re-login riêng.
- **Lease của dynamic secret** mô tả thời gian credential được Vault quản lý; lease có thể liên quan tới auth token đã cấp nó.
- **Connection pool** giữ JDBC connections đã tạo. Nó không tự thay username/password chỉ vì Vault có lease mới.
- **KV version, Transit key version và X.509 certificate validity** là các cơ chế khác, không phải lease database credential.

Đặc biệt, khi token gốc hết hạn hoặc bị revoke, các lease phụ thuộc vào phiên đăng nhập đó có thể bị ảnh hưởng. Một thiết kế xoay vòng secret phải xét cả **session lifecycle** chứ không chỉ đồng hồ TTL của lease.

## 3. Kiến trúc của SecretLeaseContainer và ManagedSecret

### 3.1. SecretLeaseContainer là lớp điều phối nền tảng

`SecretLeaseContainer` là thành phần Spring Vault quản lý các `RequestedSecret`. Nó có thể:

- Đọc secret khi container bắt đầu.
- Gia hạn lease trước ngưỡng hết hạn khi lease được phép renew.
- Với chế độ rotating, cấp secret mới khi lease được coi là hết hiệu lực.
- Phát các sự kiện, chẳng hạn `SecretLeaseCreatedEvent`, `SecretLeaseRotatedEvent`, `AfterSecretLeaseRenewedEvent`, `SecretLeaseExpiredEvent` và `SecretLeaseErrorEvent`.
- Tự thực hiện các công việc nền thông qua scheduler và lifecycle của Spring.

Nó không phải một JDBC driver và cũng không tự biết cách thay pool. Ứng dụng cần **listener** hoặc một abstraction cao hơn để đưa secret mới đến consumer.

### 3.2. ManagedSecret làm gì thêm trong Spring Vault 4.1+?

`ManagedSecret` thuộc package `org.springframework.vault.core.lease`, triển khai interface `SecretRegistrar`. Nó khai báo **secret path + cách tiếp nhận secret + xử lý lỗi**. Khi đăng ký với `SecretsRegistry`/container, `ManagedSecret` theo dõi sự kiện lease và gọi callback khi nhận secret ban đầu hoặc secret mới sau rotation.

**Vai trò chính là giảm boilerplate listener**, không thay đổi semantics của Vault. Vẫn cần kiểm tra TTL, renewal, dữ liệu secret, policy, lỗi networking và cập nhật consumer.

~~~mermaid
sequenceDiagram
    autonumber
    participant Spring as Spring Context
    participant M as ManagedSecret
    participant C as SecretLeaseContainer
    participant V as Vault
    participant P as Pool Rotation Coordinator

    Spring->>M: Tạo Bean ManagedSecret
    Spring->>C: Đăng ký SecretRegistrar trước startup
    C->>V: GET database/creds/orders-ro
    V-->>C: username/password + lease
    C-->>M: Secret obtained event
    M->>P: Callback với credential đầu tiên
    Note over C,V: Renew lease nếu có thể
    C->>V: Renew lease trước TTL
    V-->>C: TTL mới
    Note over C,P: Renew không đồng nghĩa có credential mới
    C->>V: Request credential mới khi phải rotate
    V-->>C: Credential generation mới
    C-->>M: Rotation event
    M->>P: Callback với credential mới
    P->>P: Stage, verify, switch, drain old pool
~~~

### 3.3. ManagedSecret không phải scheduler tự động của mọi loại secret

Không nên mặc định `ManagedSecret` có thể tự:

- Nhận thông báo push ngay lập tức khi một người sửa `secret/data/...` của KV v2.
- Dùng được cho tất cả endpoint Transit/PKI; ví dụ xoay vòng Transit key không đồng nghĩa thay username/password.
- Thay đổi các JDBC connections đã được tạo trước đó.
- Gia hạn một lease đã bị thu hồi hoặc vượt qua max TTL.
- Bảo đảm callback chạy trong thread xử lý HTTP request; callback có thể chạy trong lifecycle/scheduler thread.
- Tự cân bằng transaction và drain traffic giữa các Pod.

Những nhiệm vụ đó thuộc thiết kế của ứng dụng và loại secret cụ thể.

## 4. Ma trận lựa chọn theo phiên bản

Dưới đây là **ma trận quyết định**, không phải ma trận tương thích đầy đủ giữa các phiên bản Spring Boot, Spring Framework, Spring Cloud và JDK. Phiên bản thực tế phải được kiểm tra từ dependency tree/BOM/release notes của dự án.

| Spring Vault đang dùng | API có thể lựa chọn | Khuyến nghị |
| --- | --- | --- |
| **3.1.x / 3.2.x** | `SecretLeaseContainer`, `RequestedSecret`, listener sự kiện lease | Dùng renew/rotation qua container; **không import ManagedSecret 4.1** |
| **4.0.x** | `SecretLeaseContainer` và API lifecycle của nhánh này | Giữ implementation theo API 4.0; chỉ thêm `ManagedSecret` nếu đã nâng lên nhánh hỗ trợ |
| **4.1.x trở lên có API ManagedSecret** | `ManagedSecret.rotating(...)`, `ManagedSecret.from(...)`, `SecretRegistrar`, `SecretLeaseContainer` | Ưu tiên declarative callback cho use case đơn giản; dùng listener khi cần điều khiển chi tiết |
| **Spring Cloud Vault auto-configuration** | Property sources và lease lifecycle do Cloud Vault cấu hình | Kiểm tra release train và bean thực tế; không tự giả định mọi registrar được auto-register trong mọi phiên bản |
| **API thủ công dùng VaultOperations** | `VaultTemplate.read()`, gọi API lease có kiểm soát | Hợp lệ khi cần orchestration đặc biệt; phải sở hữu rõ vòng đời lease/token |

**Không đồng nhất Spring Vault 4.1 với Spring Cloud Vault 4.1:** đây là các dự án có lịch phát hành và cơ chế quản lý dependency khác nhau. Dùng BOM tương thích được tài liệu Spring Cloud xác nhận; tránh ép chỉ một thư viện lên version mới nếu framework hoặc Cloud Vault còn sử dụng API cũ.

### 4.1. Chọn theo nhu cầu chứ không chỉ theo version

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Một dynamic database credential, có consumer callback đơn giản, đang dùng Spring Vault 4.1+ | `ManagedSecret.rotating` |
| Cần chỉ renew lease và không tự xin secret mới khi hết hạn | `RequestedSecret.renewable` với container; trong 4.1+ có thể dùng `ManagedSecret.from` theo mode đã chọn |
| Cần kiểm soát đầy đủ sự kiện, metadata lease, error và thứ tự revocation | `SecretLeaseContainer` + `LeaseListener`/`LeaseErrorListener` |
| Spring Cloud Vault đã quản lý lease/PropertySource | Dùng một nguồn quản lý thống nhất; xác minh cách cập nhật consumer, tránh hai managers |
| Chỉ đọc secret tĩnh tại startup, có quy trình rolling deployment khi đổi cấu hình | Read once + rollout có kiểm soát có thể đơn giản hơn |
| PKI certificate rotation | Xét `CertificateContainer`/`ManagedCertificate` khi version hỗ trợ; không dùng ManagedSecret một cách máy móc |

## 5. Ví dụ ManagedSecret trong Spring Vault 4.1+

### 5.1. Kiểu dữ liệu mong đợi từ Vault Database engine

Giả sử Database secrets engine đã cấu hình role `orders-readonly` và workload có policy `read` trên:

~~~hcl
path "database/creds/orders-readonly" {
  capabilities = ["read"]
}
~~~

Vault có thể trả:

~~~json
{
  "lease_id": "database/creds/orders-readonly/abcd...",
  "lease_duration": 900,
  "renewable": true,
  "data": {
    "username": "v-orders-ro-example",
    "password": "<REDACTED>"
  }
}
~~~

Đây là ví dụ đã ẩn credential. Một request `GET database/creds/orders-readonly` mới có thể **phát hành user và lease mới**, khác với đọc lại một mật khẩu tĩnh.

### 5.2. Bean declarative đăng ký một managed secret

Ví dụ Java dùng trực tiếp API Spring Vault **4.1.x**:

~~~java
package com.example.orders.vault;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.core.lease.ManagedSecret;
import org.springframework.vault.core.lease.ManagedSecret.UsernamePassword;

@Configuration
public class DatabaseSecretConfiguration {

    @Bean
    ManagedSecret ordersDatabaseCredentials(
            PoolRotationCoordinator coordinator) {

        return ManagedSecret.rotating(
                "database/creds/orders-readonly",

                secrets -> secrets.as(UsernamePassword::from)
                        .applyTo((username, password) ->
                                coordinator.acceptNextCredentials(
                                        username, password)),

                failure -> coordinator.onLeaseOrRotationError()
        );
    }
}

/**
 * Interface do ứng dụng triển khai; không thuộc Spring Vault.
 * Không log hoặc trả password ra API.
 */
interface PoolRotationCoordinator {
    void acceptNextCredentials(
            String username, CharSequence password);

    void onLeaseOrRotationError();
}
~~~

**Các điểm cần hiểu:**

1. `ManagedSecret.rotating(path, successConsumer, errorConsumer)` là API **4.1+**, không tương thích source với nhánh chưa cung cấp `ManagedSecret`.
2. `UsernamePassword::from` chuyển secret accessor thành giá trị username/password có kiểm tra field bắt buộc.
3. Callback được gọi khi nhận secret đầu tiên và khi **có secret mới sau rotation**; renewal lease thành công **không có nghĩa** callback phải chạy lại để nhận credential khác.
4. `PoolRotationCoordinator` là thành phần **do ứng dụng viết**, ví dụ tạo Hikari pool mới và chuyển traffic sau khi đã kiểm tra sức khỏe.
5. Error callback chỉ báo lỗi có thể quan sát được, không ghi nguyên exception/body chứa thông tin nhạy cảm vào log.
6. Bean `ManagedSecret` cần được **đăng ký thực tế với `SecretsRegistry` trước khi container khởi động**; chỉ khai báo Bean không tự bảo đảm hoạt động trong mọi cấu hình Spring Boot.

Trong cấu hình kế thừa `AbstractVaultConfiguration` theo cơ chế Spring Vault 4.1, registrar bean có thể được phát hiện và đăng ký trước khi container start. Với ứng dụng Spring Boot dùng Spring Cloud Vault, cần kiểm tra auto-configuration và extension point của release train đang dùng, **không tự tạo thêm SecretLeaseContainer trong khi Cloud Vault đã quản lý cùng secret**.

### 5.3. Chọn mode renewable thay vì rotating

Không phải ứng dụng nào cũng muốn nhận một tài khoản mới sau khi lease hết hạn. Khi nghiệp vụ cần giữ nguyên account trong thời hạn được phép và **không tự phát hành account mới**, có thể chọn `RequestedSecret.renewable(path)`.

Trong API 4.1+:

~~~java
import org.springframework.vault.core.lease.ManagedSecret;
import org.springframework.vault.core.lease.domain.RequestedSecret;

ManagedSecret managed = ManagedSecret.from(
        RequestedSecret.renewable("database/creds/orders-readonly"),
        secrets -> {
            // Callback nhận secret ban đầu khi container lấy được.
            // Ứng dụng tự định nghĩa cách sử dụng secret.
            String username = secrets.getRequiredString("username");
            onInitialCredential(username);
        },
        failure -> notifyLifecycleFailure()
);
~~~

`onInitialCredential` và `notifyLifecycleFailure` là helper giả định của ứng dụng; ví dụ chỉ minh họa factory `from`. Với `renewable`, manager renew lease khi được phép, nhưng **không tự xin secret mới sau khi lease hết hạn** theo chế độ rotating. Nếu hết max TTL, phải có chính sách phục hồi riêng.

**Không dùng chế độ renewable như lời hứa rằng lease sống mãi**: Vault quyết định renewability/TTL cuối cùng, và một token bị revoke hoặc session hết hạn có thể khiến lease không còn hợp lệ.

## 6. Với nhánh cũ: SecretLeaseContainer và listener trực tiếp

Nếu ứng dụng đang dùng Spring Vault **3.x hoặc 4.0**, nên giữ cơ chế đã được version đó hỗ trợ thay vì cố import `ManagedSecret`.

Ví dụ Java (mẫu lifecycle ở mức container độc lập, dùng Vault test):

~~~java
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;

ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
scheduler.initialize();

SecretLeaseContainer container =
        new SecretLeaseContainer(vaultOperations, scheduler);

RequestedSecret requested = container.requestRotatingSecret(
        "database/creds/orders-readonly");

container.addLeaseListener(new LeaseListenerAdapter() {
    @Override
    public void onLeaseEvent(SecretLeaseEvent event) {
        if (!requested.equals(event.getSource())) {
            return;
        }

        // SecretLeaseRotatedEvent là subclass của CreatedEvent,
        // nên nhận được cả giá trị đầu tiên và giá trị sau rotate.
        if (event instanceof SecretLeaseCreatedEvent created) {
            var fields = created.getSecrets();
            Object username = fields.get("username");
            Object password = fields.get("password");

            if (!(username instanceof String user)
                    || !(password instanceof String pass)) {
                signalInvalidSecretStructure();
                return;
            }

            enqueuePoolRotation(user, pass);
        }
    }
});

container.afterPropertiesSet();
container.start();

// Khi kết thúc lifecycle của fixture:
// container.destroy(); scheduler.shutdown();
~~~

Các hàm `signalInvalidSecretStructure` và `enqueuePoolRotation` là pseudo-helper của ứng dụng, không phải API Spring Vault. Đây là **mẫu Java 17+** vì sử dụng pattern matching cho `instanceof`. Đối với Java version thấp hơn, thay bằng ép kiểu truyền thống theo compiler target thực tế.

**Thứ tự quan trọng:** đăng ký secret và listener **trước khi `start()`** để không bỏ lỡ sự kiện nhận secret đầu tiên. Trong Spring context, dùng lifecycle bean/auto-config do framework quản lý; không gọi `afterPropertiesSet()` và `start()` lần hai trên một container đã được auto-start.

`SecretLeaseContainer.stop()` ngừng gia hạn và rotation nhưng không tương đương mọi trường hợp với `destroy()`, vốn thực hiện cleanup theo lifecycle container. Cần thử trong môi trường kiểm thử để biết các lease cũ có bị thu hồi đúng ý định, tránh gọi cleanup khiến connection pool vẫn phục vụ request bằng account đã bị revoke.

### 6.1. Khi nào nên giữ listener thay vì nâng abstraction?

Giữ listener khi bạn cần:

- Xử lý riêng sự kiện `AfterSecretLeaseRenewedEvent` với metrics và logic renewal.
- Phân biệt `SecretLeaseCreatedEvent`, `SecretLeaseRotatedEvent`, `SecretLeaseExpiredEvent` và lỗi.
- Điều khiển thứ tự ngắt pool, revoke, rollback, notification và checkpoint của application.
- Tương thích với nhánh Spring Vault cũ hoặc codebase có lifecycle đã được kiểm thử kỹ.

`ManagedSecret` không làm những yêu cầu chi tiết đó tự biến mất; nó chỉ giúp wiring callback đơn giản hơn khi use case cho phép.

## 7. Vòng đời SecretLeaseContainer: renew, rotate và thông báo trễ

Cơ chế hoạt động được mô tả qua những bước sau:

1. Đăng ký `RequestedSecret` với đường dẫn và mode.
2. Khi container chạy, Vault được yêu cầu cấp secret lần đầu; container nhận lease và secret.
3. Container tính lịch renew theo TTL, ngưỡng expiry và scheduler.
4. Nếu lease có thể renew, nó gửi yêu cầu gia hạn khi thích hợp.
5. Nếu lease đã được coi là hết hiệu lực và secret ở chế độ rotating, container yêu cầu secret **mới** và phát sự kiện rotation.
6. Nếu không thể liên lạc Vault, policy lỗi hoặc secret không tồn tại, container phát sự kiện/lỗi thích hợp để ứng dụng xử lý.

**Vault không chủ động push một event đến container mỗi khi TTL kết thúc.** Container phải tự theo dõi và gọi Vault; vì vậy thời điểm phát sự kiện `SecretLeaseExpiredEvent` có thể **muộn hơn thời điểm lease thực sự hết hiệu lực**.

Spring Vault 4.1 reference mô tả ngưỡng expiry mặc định khoảng **1 phút** và minimum renewal khoảng **10 giây**; các giá trị này tùy phiên bản và cấu hình cụ thể. Với lease TTL cực ngắn trong integration test, cần chú ý ngưỡng expiry: một lease ngắn hơn ngưỡng có thể bị đánh giá gần hết hạn ngay sau lúc cấp. Đừng hardcode chính sách quay vòng từ con số mặc định nếu chưa xác minh Javadoc/config của version dự án.

### 7.1. Phân biệt sự kiện renew và rotate

| Event/khái niệm | Ý nghĩa | Hành động điển hình |
| --- | --- | --- |
| `SecretLeaseCreatedEvent` | Nhận secret và lease lần đầu | Khởi tạo consumer generation 1 |
| `AfterSecretLeaseRenewedEvent` | Lease hiện có được renew | Cập nhật TTL metrics, **không tự đổi username/password** |
| `SecretLeaseRotatedEvent` | Nhận secret mới sau rotation | Stage credential generation mới, chuyển consumer |
| `SecretLeaseExpiredEvent` | Container phát hiện lease hết hiệu lực | Ngừng cấp kết nối mới bằng credential cũ; đối soát |
| `SecretLeaseErrorEvent` | Có lỗi liên quan tới request/renew/revoke | Báo degraded, phân loại và retry có giới hạn |
| `SecretNotFoundEvent` | Không tìm thấy secret tương ứng | Kiểm tra path/role/policy; không tự lộ secret |

Một câu hỏi thiết kế cần trả lời là: **nếu lease thực tế đã hết hạn nhưng callback rotation chưa đến, ứng dụng sẽ làm gì?** Đừng giữ traffic bất chấp trạng thái credential. Có thể cần giới hạn thời hạn sử dụng thực tế, giữ số Pod đủ hoạt động hoặc áp dụng rolling restart có kiểm soát.

## 8. Áp dụng credential mới cho HikariCP: không chỉ setUsername

Trong tài liệu Spring Vault có ví dụ callback:

~~~java
ManagedSecret.rotating(
    "database/creds/orders-readonly",
    secrets -> secrets.as(UsernamePassword::from)
            .applyTo((user, password) -> {
                dataSource.setUsername(user);
                dataSource.setPassword(password.toString());
            })
);
~~~

Đây là **mẫu minh họa cách nhận và truyền credential**, **không phải cam kết tất cả JDBC connections sẽ được đổi account ngay lập tức**. Với HikariCP, connection đã mở có thể tiếp tục nằm trong pool và đang phục vụ transaction. Thay username/password ở cấu hình pool chủ yếu ảnh hưởng việc mở connection **mới**, không biến các connection cũ thành phiên xác thực mới. Cần cân nhắc concurrency, rollback và cách database thực thi revocation.

### 8.1. Mô hình an toàn hơn: staging và chuyển pool

~~~mermaid
flowchart TD
    A[Pool A, credential lease A] --> B[Callback secret mới lease B]
    B --> C[Tạo Pool B riêng]
    C --> D[Kiểm tra JDBC TLS, health, quyền tối thiểu]
    D --> E{Pool B hoạt động?}
    E -- Không --> F[Báo degraded, không đánh dấu rotation hoàn tất]
    E -- Có --> G[Định tuyến request mới sang Pool B]
    G --> H[Drain in-flight transaction trên Pool A]
    H --> I[Đóng Pool A]
    I --> J[Revoke/cleanup lease A khi được phép]
~~~

**Chú ý:** nếu mã chỉ biết `username`/`password` mà không biết lease cũ, nó không thể tự quyết định đúng thời điểm revoke. Việc quản lý lease cũ phải giao cho một owner rõ ràng (`SecretLeaseContainer` hoặc coordinator kết hợp với container), không để hai nơi cùng renew/revoke một lease.

Một giao diện coordinator hữu ích:

~~~java
public interface PoolRotationCoordinator {

    // Có thể được gọi từ thread lifecycle của secret manager.
    // Không log username/password và không làm block scheduler lâu.
    void acceptNextCredentials(String username, CharSequence password);

    // Ghi metric/alert, không in raw HTTP response hoặc secret.
    void onLeaseOrRotationError();
}
~~~

Implementation production có thể enqueue một yêu cầu rotation vào **bounded executor**, tạo pool mới trong worker riêng và chỉ switch khi `SELECT 1` + các kiểm tra quyền được xác nhận. Cần lưu ý không vô tình giữ `CharSequence` bí mật trong hàng đợi lâu hơn cần thiết; dọn dữ liệu khi có thể và giới hạn phạm vi truy cập.

### 8.2. Startup ordering và dependency

`ManagedSecret` cần container có vòng đời được khởi động, trong khi một `DataSource` có thể thử mở JDBC connection ngay tại `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()`. Nếu secret chưa được cấp, lỗi khởi tạo sẽ xảy ra trước callback.

Hướng giải quyết:

- Bố trí dependency/lifecycle để consumer chỉ mở connection sau khi có credential hợp lệ.
- Định nghĩa readiness probe dựa trên **pool generation đã xác minh**, không chỉ application context khởi động.
- Nếu cần secret trước một bean khác, dùng chiến lược bootstrap được framework hỗ trợ; không tự hack thứ tự BeanPostProcessor hoặc tạo vòng phụ thuộc bean.
- Trong môi trường nhiều Pod, dùng rolling deployment hoặc readiness gate để không mất toàn bộ khả năng phục vụ trong lúc rotation.

## 9. Spring Cloud Vault và PropertySource có tự cập nhật consumer không?

Spring Cloud Vault có thể tích hợp Vault thành nguồn property/config của Spring Boot và có các cơ chế lease lifecycle. Ví dụ minh họa:

~~~yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
      database:
        enabled: true
        backend: database
        role: orders-readonly
        username-property: spring.datasource.username
        password-property: spring.datasource.password
~~~

**Cú pháp property và hành vi bootstrap phải đối chiếu với Spring Cloud Vault release train của dự án.** Đây là ví dụ khái niệm, không phải khẳng định một cấu hình duy nhất hoạt động trên mọi nhánh Spring Boot/Cloud.

Ngay cả khi `LeaseAwareVaultPropertySource` cập nhật property từ luồng nền, **một bean đã khởi tạo không tự động bị tạo lại** và HikariCP không mặc nhiên thay toàn bộ connections. Phải tách rõ:

- **Property trong Spring Environment có thay đổi?**
- **Bean lấy property có được refresh/rebind?**
- **JDBC connections mới có dùng credential mới?**
- **Các connections cũ đã được drain hoặc thu hồi an toàn?**

Không nên lắp thêm `ManagedSecret` và `SecretLeaseContainer` thủ công nếu Spring Cloud Vault đã sở hữu lease đó, trừ khi bạn cố ý thiết kế một ownership duy nhất và kiểm thử không có hai manager cạnh tranh.

## 10. Quy trình nâng cấp từ code listener sang ManagedSecret

Giả sử một hệ thống đang chạy Spring Vault 3.2, dùng `SecretLeaseContainer` và listener để đẩy credential mới vào pool. Muốn chuyển sang Spring Vault 4.1+, **không nên chỉ đổi import**. Cần thực hiện theo quy trình có kiểm soát.

### 10.1. Bước 1 — Kiểm kê dependency và runtime

Ghi lại:

- Version Java và Spring Boot.
- Version Spring Framework, Spring Vault, Spring Cloud Vault và Spring Cloud release train/BOM.
- HTTP client (JDK/Apache HttpClient), driver JDBC, HikariCP.
- Vault server version, auth method, token TTL và Database secrets engine plugin.
- Các API thực sự đang dùng: `SecretLeaseContainer`, `VaultOperations`, property sources, listeners, session manager.
- Ownership hiện tại của renew, revoke, rotation, scheduler và pooling.

Một lệnh Maven để **xem** dependency trong môi trường dự án (không phải lệnh cần chạy tại bước viết nội dung):

~~~bash
mvn dependency:tree \
  -Dincludes=org.springframework.vault:*,org.springframework.cloud:*
~~~

Với Gradle có thể dùng `dependencies` hoặc `dependencyInsight` trong workflow của dự án. Không ép thủ công một version Spring Vault mà bỏ qua BOM.

### 10.2. Bước 2 — Xác định migration path

| Cấu hình ban đầu | Mục tiêu | Biện pháp |
| --- | --- | --- |
| Listener renew/rotation phức tạp và ổn định | Giữ tính đúng đắn | Có thể tiếp tục `SecretLeaseContainer` sau nâng version, kiểm tra API |
| Listener chỉ chuyển username/password tới một consumer | Giảm boilerplate | Đổi sang `ManagedSecret.rotating` nếu đang dùng 4.1+ |
| Spring Cloud Vault đã sở hữu lease | Không tạo hai managers | Giữ auto-config, chỉ bổ sung wiring tiêu thụ secret theo extension point được hỗ trợ |
| Cần nhiều event để audit lease | Đo lường độc lập | Giữ listener/metrics có kiểm soát, không đăng ký trùng secret |
| Chỉ cần restart khi đổi credential | Đơn giản hóa vận hành | Rolling rollout có thể phù hợp hơn live pool rotation |

### 10.3. Bước 3 — Tách consumer khỏi lease manager

Không để callback vừa đọc Vault, vừa tạo pool, vừa gửi thông báo, vừa revoke lease trong một đoạn code dài. Tạo một boundary như `PoolRotationCoordinator`:

~~~text
Old flow:
SecretLeaseContainer -> LeaseListener -> sửa Hikari settings

New flow:
ManagedSecret / SecretLeaseContainer
       -> credential callback / event adapter
       -> PoolRotationCoordinator
       -> validate -> switch -> drain -> cleanup
~~~

Khi cần rollback, chỉ đổi adapter kết nối vào coordinator, không viết lại toàn bộ pool lifecycle.

### 10.4. Bước 4 — Không để hai manager cùng sở hữu lease

Mỗi `RequestedSecret` nên có một lifecycle owner rõ ràng. Khi chuyển qua `ManagedSecret`, gỡ đăng ký cũ hoặc cấu hình cùng registry đúng cách để tránh:

- Hai lần gọi `database/creds/role` cấp hai account mới.
- Hai scheduler renew/revoke cùng lease.
- Callback chạy hai lần và pool tạo trùng.
- Lỗi cleanup một nơi revoke credential đang được nơi khác sử dụng.

**Không dựa vào việc registry deduplicate cùng RequestedSecret để hợp thức hóa hai hệ thống lifecycle độc lập.** Hai container hoặc hai connection/session manager khác nhau vẫn có thể tạo credential và lease riêng.

### 10.5. Bước 5 — Kiểm chứng trước khi rollout

Chạy unit test mapping, integration test trên Vault Database engine test, thử max TTL, token revoke, load/cập nhật pool, rolling deployment và lỗi Vault. Khi tất cả đạt, rollout một nhóm Pod nhỏ, quan sát credential counts và connection errors, rồi mới mở rộng.

## 11. Lựa chọn cho các loại secret khác

### 11.1. KV v2: phiên bản dữ liệu không phải vòng đời lease

`secret/data/orders/config` có metadata `version`, hỗ trợ CAS để cập nhật cạnh tranh. **Thay đổi KV version không nhất thiết phát ra lease event đến ManagedSecret**. Nếu cần auto-refresh cấu hình, lựa chọn bao gồm:

- Cơ chế property source có quản lý refresh được version đang dùng hỗ trợ.
- Polling với caching/ETag hoặc version check phù hợp, có rate limit.
- Trigger deployment/rolling restart khi config đổi.
- Cơ chế phân phối sự kiện từ hệ thống quản lý cấu hình riêng.

Không đọc `database/creds/role` theo lịch mỗi khi HTTP request đến như một cách refresh chung: endpoint đó có thể **tạo một user mới mỗi lần**.

### 11.2. Transit: xoay vòng khóa mật mã khác xoay vòng credential

Transit key rotation thay đổi **phiên bản khóa** tại Vault và ảnh hưởng ciphertext mới; có thể cần job rewrap ciphertext cũ. Nó không phải thao tác thay username/password ở ứng dụng và không có cùng lease semantics với database secrets. Do đó không dùng `ManagedSecret.rotating("transit/keys/...")` như một thay thế cho quản lý khóa Transit.

### 11.3. PKI: ManagedCertificate là abstraction khác

Spring Vault 4.1 giới thiệu `ManagedCertificate` và `CertificateContainer` để hỗ trợ xoay vòng chứng thư. X.509 certificate có thời hạn `notAfter`, nhưng không phải lúc nào cũng mang một renewable lease. Certificate issuance/renewal thực tế có thể là **cấp lại chứng thư mới**, không phải gọi renew lease như database credentials.

Với TLS server, ngoài việc nhận certificate/key mới còn cần:

- Cập nhật `KeyStore`/SSL bundle theo cơ chế hỗ trợ.
- Reload TLS context/listener theo framework thực tế.
- Kiểm thử handshake mới dùng đúng certificate chain.
- Xử lý key rotation, CA trust, CRL/OCSP, số sê-ri và thu hồi theo policy.

Không giả định một Bean `ManagedCertificate` đơn lẻ tự thay thế mọi socket TLS đang hoạt động.

### 11.4. Response wrapping token và auth token

Wrapping token thường chỉ được dùng một lần để unwrap phản hồi; nó không phải secret có lease được rotate như account database. Vault authentication token có `SessionManager` và login/renew riêng; **đừng đăng ký auth token như database secret** rồi tạo hai cơ chế quản lý token song song.

## 12. Lỗi thường gặp sau nâng cấp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Cannot resolve symbol ManagedSecret` | Đang dùng Spring Vault trước 4.1 hoặc dependency tree không đúng | Kiểm tra version thực tế, BOM và imports |
| Bean ManagedSecret được tạo nhưng không thấy callback | Không được đăng ký registry hoặc container chưa start | Kiểm tra lifecycle, `SecretRegistrar` và cấu hình Spring |
| Callback đầu tiên đến quá muộn | Pool mở trong `@PostConstruct` trước khi secret được cấp | Sửa thứ tự bean, readiness và bootstrap |
| Callback chạy nhưng JDBC login vẫn lỗi | Pool chưa switch hoặc connection mới vẫn dùng credential cũ | Kiểm tra Hikari generation, active/idle connections |
| Rotation sinh rất nhiều user | Hai manager, TTL quá ngắn, retry quá nhiều hoặc nhiều Pod restart | Kiểm kê ownership và default TTL |
| Renew thành công nhưng callback không gọi lại | Đây là **renew lease**, không phải secret mới | Quan sát event renew riêng, không coi là lỗi |
| Lease hết trước khi thấy rotation event | Vault không push event; scheduler/callback trễ | Điều chỉnh threshold/TTL, cảnh báo và failover |
| Sau upgrade auth/renew thất bại | Session manager, policy, max TTL hoặc behavior khác | Test lại authentication theo workload |
| 403/404 khi đọc `database/creds` | Policy/mount/role sai, token không hợp lệ | Kiểm tra auth và đường dẫn, không bỏ TLS |
| Timeout khi cấp credential | Vault có thể đã tạo user nhưng response mất | Đối soát audit/lease, không retry mù |
| Rollback lỗi vì bean lifecycle trùng | Old container chưa tắt, auto-config khác | Chỉ để một owner, rollback theo kế hoạch |

**Đừng xem mọi exception là yêu cầu quay vòng:** lỗi policy 403, mount sai 404, token hết hạn, timeout và credential thực sự hết TTL có phương án xử lý khác nhau. Với timeout sau khi gửi `database/creds/...`, Vault có thể đã cấp account; retry ngay có thể tạo thêm tài nguyên.

## 13. Bảo mật và vận hành khi ManagedSecret chạy nền

Một cơ chế tự động không thay thế các nguyên tắc bảo mật:

1. **Workload identity:** Kubernetes, JWT hoặc AppRole theo vai trò; không dùng root token trong ứng dụng.
2. **Policy ít quyền:** chỉ `read` trên role cần thiết; quyền renew/revoke theo thiết kế và endpoint thực tế.
3. **TLS:** kiểm tra certificate chain/hostname khi Spring Vault gọi Vault và JDBC gọi database.
4. **Không log secret:** không log `username/password`, token, `VaultResponse`, raw error body hoặc HTTP headers.
5. **Một lifecycle owner:** xác định ai đăng nhập, ai renew token, ai renew/revoke lease, ai thay pool.
6. **Bounded executors:** callback secret nên chuyển việc nặng sang worker có giới hạn, không block scheduler lâu.
7. **Readiness:** chỉ báo ready khi credential generation đã qua health check.
8. **Cleanup:** khi drain/stop Pod, dừng cấp kết nối mới, đóng pool và xử lý lease theo ownership.
9. **Không hardcode version nhạy cảm:** kiểm tra ảnh hưởng của update Spring Vault lên API, HTTP client và auto-config.
10. **Không in exception chứa secret:** error callback nên ghi mã loại lỗi, thao tác, timestamp và request correlation ID không nhạy cảm.

Trong multi-Pod deployment, mỗi Pod có thể nhận credential riêng và lease riêng. Khi rollout đồng thời hàng trăm Pod, Vault Database plugin phải tạo và dọn lượng account lớn, ảnh hưởng database connection limits và Vault request throughput. Cần giới hạn startup concurrency và theo dõi số lease đang sống.

## 14. Metrics và audit hỗ trợ quyết định rotation

| Metric/sự kiện gợi ý | Ý nghĩa |
| --- | --- |
| `vault_managed_secret_initial_total` | Số lần nhận credential đầu tiên |
| `vault_managed_secret_rotated_total` | Số lần nhận credential mới |
| `vault_lease_renew_success_total` | Số lease renew thành công |
| `vault_lease_renew_failure_total` | Renew thất bại, cần kiểm tra trước TTL |
| `vault_managed_secret_errors_total` | Số lỗi request/callback theo loại đã chuẩn hóa |
| `vault_lease_seconds_remaining` | TTL còn lại của lease đang dùng |
| `jdbc_pool_generation_switch_total` | Số lần chuyển sang pool mới |
| `jdbc_pool_rotation_failure_total` | Pool mới không khởi tạo/health check thành công |
| `jdbc_pool_active_connections` | Số connection đang sử dụng |
| `vault_reauth_failure_total` | Lỗi xác thực lại Vault sau token expiry/revoke |

Đây là **tên metric đề xuất phía ứng dụng**, không phải tên được Spring Vault xuất tự động. Để tránh cardinality cao và rò rỉ, không đưa token, username phát hành ngẫu nhiên, password, private key, certificate private material hoặc lease ID vào metric labels.

Audit Vault có thể giúp đối chiếu các lệnh `database/creds`, renew/revoke và thời điểm lỗi. Nên ghi thêm sự kiện ứng dụng `STAGED`, `VERIFIED`, `SWITCHED`, `DRAINED` và `DEGRADED`, kèm correlation ID không nhạy cảm. Không dùng riêng log ứng dụng để khẳng định Vault đã thu hồi account nếu revoke request timeout; phải đối soát với backend.

## 15. Kiểm thử tích hợp cho đường nâng cấp

Một chiến lược nâng cấp đúng phải kiểm tra **hành vi** chứ không chỉ build thành công.

### 15.1. Test nền tảng

Dùng Vault và PostgreSQL test cô lập, role `orders-readonly` TTL ngắn có giới hạn, policy đọc role và một consumer JDBC test. Không dùng Vault production hoặc credential thật.

| Test | Kết quả mong đợi |
| --- | --- |
| **Bean registration** | ManagedSecret 4.1+ thực sự được đăng ký và callback initial chạy đúng một lần cho một secret |
| **Version fallback** | Nhánh Spring Vault cũ chạy qua SecretLeaseContainer, không tham chiếu ManagedSecret |
| **Renew existing lease** | Renewal thành công, TTL mới được quan sát; không ghi nhận nhầm là credential rotation |
| **Rotate credential** | Nhận username/password mới và tạo pool generation mới |
| **Verify and switch** | Pool mới kết nối thành công trước khi traffic được chuyển |
| **Drain old pool** | Transaction cũ hoàn tất hoặc timeout có kiểm soát; pool cũ được đóng |
| **Revoke old lease** | Connection mới bằng credential cũ không còn được cho phép theo semantics plugin |
| **Lease max TTL** | Không renew vô hạn; đến hạn phải theo chính sách rotate/recovery |
| **Vault token revoke** | Session manager xử lý re-login nếu được phép, không coi renew lease cũ vẫn hợp lệ |
| **403/404** | Phân loại lỗi auth/role/path, không retry vô hạn |
| **Network timeout khi issue** | Không tạo vòng lặp cấp credential không giới hạn; có đối soát |
| **Two managers** | Startup validation/cấu hình chặn đăng ký trùng ownership |
| **Startup ordering** | Bean cần credential chỉ hoạt động sau callback/ready |
| **Rolling deployment** | Nhiều Pod mới/cũ hoạt động không gián đoạn quá mức SLA |

### 15.2. Ví dụ test callback của ManagedSecret

Đối với **unit test** không cần Vault, có thể kiểm tra coordinator bằng một event/callback abstraction do ứng dụng xây dựng; không cần ép `ManagedSecret` chạy scheduler thật trong unit test.

Ví dụ giả lập nghiệp vụ pool rotation (JUnit 5 + AssertJ, pseudocode với fixture):

~~~java
@Test
void acceptsNewCredentialOnlyAfterPoolHealthCheck() {
    coordinator.acceptNextCredentials("user-v2", "test-password-v2");

    // fixture đợi bounded task hoàn tất
    fixture.awaitRotationCompleted();

    assertThat(fixture.activePoolGeneration()).isEqualTo(2);
    assertThat(fixture.newPoolPassedHealthCheck()).isTrue();
    assertThat(fixture.oldPoolIsDraining()).isTrue();
}

@Test
void doesNotSwitchPoolIfNewCredentialsFail() {
    fixture.failNextJdbcLogin();

    coordinator.acceptNextCredentials("bad-user", "bad-password");
    fixture.awaitRotationAttempt();

    assertThat(fixture.activePoolGeneration()).isEqualTo(1);
    assertThat(fixture.healthStatus()).isEqualTo("DEGRADED");
}
~~~

`fixture` và các phương thức coordinator là **hạ tầng test do dự án triển khai**, không phải mã có thể chạy độc lập. Integration test thật phải khởi động context với `ManagedSecret` đã đăng ký, Vault Database engine và PostgreSQL để xác minh callback initial/rotation, SQL grants và lease behavior.

### 15.3. Kiểm thử đúng version

Trong CI, có thể chạy hai nhóm bài test:

- **Nhánh legacy:** build bằng dependency/BOM nhánh cũ, kiểm tra `SecretLeaseContainer` event listener và operation thực tế.
- **Nhánh 4.1+:** build bằng BOM/phiên bản được hỗ trợ, kiểm tra `ManagedSecret` registration, callback, lifecycle và thứ tự startup.

Không cố gắng biên dịch cùng source sử dụng `ManagedSecret` trên một classpath 3.2. Có thể tách module adapter, profile hoặc branch nâng cấp, nhưng **mỗi build phải dùng một bộ dependency nhất quán**.

## 16. Bài thực hành: lựa chọn và nâng cấp quản lý credential

**Bối cảnh:** `orders-api` dùng Spring Vault đọc `database/creds/orders-readonly` cho PostgreSQL, mỗi Pod có HikariCP. Dự án đang dùng Spring Vault 3.2 với listener và cân nhắc nâng lên Spring Vault 4.1+.

Hãy thực hiện trong môi trường test:

1. Kiểm kê Spring Boot/Cloud/Vault, Java, Hikari, auth method, Database plugin và Vault server version.
2. Xác minh version đang dùng **chưa/có `ManagedSecret`**, lập bảng chọn legacy listener hay declarative API.
3. Thiết lập Vault Database role test, TTL ngắn nhưng đủ cho scheduler, policy `read` đúng path, không dùng root token ở workload.
4. Trong cấu hình 3.2, chạy `SecretLeaseContainer` với `requestRotatingSecret`, lắng nghe initial và rotated events.
5. Trong cấu hình 4.1+, khai báo `ManagedSecret.rotating` và kiểm tra Bean thực sự được đăng ký registry trước startup.
6. Tạo coordinator nhận credential mới, mở pool mới, kiểm tra JDBC login rồi chuyển traffic; không chỉ gọi `HikariDataSource.setPassword()`.
7. Xác minh gia hạn lease **không** được nhầm với sự kiện credential mới; thử hết max TTL.
8. Mô phỏng token revoke, Vault timeout khi cấp credential, 403 do policy, PostgreSQL downtime và lỗi health check của pool mới.
9. Quan sát metrics số rotation, renew, lỗi, pool generation, leased connections; kiểm tra log không chứa token/password.
10. Rollback adapter trên môi trường test, đảm bảo không còn hai lease managers và mọi lease/DB user test được cleanup.

**Câu hỏi tự kiểm tra:**

1. `ManagedSecret` được giới thiệu từ Spring Vault nhánh nào?
2. Vì sao `ManagedSecret` không thay thế hoàn toàn `SecretLeaseContainer`?
3. Khi `renew` thành công, có nhất thiết nhận username/password mới không?
4. Khác biệt quan trọng giữa `RequestedSecret.renewable` và `RequestedSecret.rotating` là gì?
5. Tại sao Bean ManagedSecret tồn tại chưa chứng minh callback sẽ chạy?
6. Vì sao secret đã cập nhật trong Spring Environment vẫn có thể để JDBC connection dùng credential cũ?
7. Cần làm gì trước khi thu hồi lease của connection pool cũ?
8. Nếu Vault auth token bị revoke, điều gì có thể xảy ra với các lease liên quan?
9. Tại sao không dùng `ManagedSecret` để mặc định quản lý KV version hoặc Transit key rotation?
10. Những kịch bản nào phải có trong integration test trước khi nâng cấp production?

## 17. Kết luận

**ManagedSecret** là abstraction cấp cao được giới thiệu trong **Spring Vault 4.1** để khai báo một secret cần quản lý và callback nhận credential khi có lần cấp đầu tiên hoặc rotation. Nó xây dựng trên cơ chế `SecretLeaseContainer`/`RequestedSecret` và `SecretRegistrar`, giúp giảm code listener cho các use case phù hợp nhưng **không tự thay thế connection pool, không giải quyết mọi sự cố token/lease và không chuyển đổi mọi loại secret thành renewable lease**.

**Lựa chọn theo phiên bản**: với Spring Vault **3.x/4.0**, tiếp tục dùng `SecretLeaseContainer` và event listeners; với **4.1+**, có thể dùng `ManagedSecret` khi registration, callback và lifecycle được hỗ trợ trong cấu hình ứng dụng thực. Dù dùng cách nào, ứng dụng Spring Boot vẫn cần authentication theo workload, policy tối thiểu, startup ordering, kiểm tra TTL, một owner cho mỗi lease, rotation an toàn ở consumer, metrics/audit và integration test trước rollout.

### Nguồn tham khảo để đối chiếu phiên bản

- [Spring Vault 4.1 — Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html): mô hình container, ManagedSecret và TTL tuning.
- [Spring Vault 4.1 — ManagedSecret JavaDoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/ManagedSecret.html): factory `rotating`, `from` và `SecretRegistrar`.
- [Spring Vault 4.1 — SecretLeaseContainer JavaDoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html): renewal, rotation, registration và lifecycle.
- [Spring Vault 3.2 — SecretLeaseContainer JavaDoc](https://docs.spring.io/spring-vault/reference/3.2/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html): lựa chọn cho nhánh legacy.
- [Spring Vault 4.1 Generally Available (10/06/2026)](https://spring.io/blog/2026/06/10/spring-vault-4-1-available/): mốc giới thiệu các API mới.
- [Spring Cloud Vault documentation](https://docs.spring.io/spring-cloud-vault/reference/): xem compatibility và auto-configuration theo release train.

Các đoạn mã được dùng cho mục đích học và thiết kế; trước khi đưa vào production cần xác minh compile, bean lifecycle và hợp đồng API với dependency đã khóa.
