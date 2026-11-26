# Tải nhiều phiên bản ứng dụng và tác động đến số token, lease

Trong chương **Quan sát và hiệu năng**, chúng ta xem xét điều gì xảy ra khi một ứng dụng Java dùng **Spring Vault** triển khai nhiều phiên bản song song: rolling update, canary, blue-green hoặc tăng số replica. Trong một khoảng thời gian, các Pod của phiên bản mới đã đăng nhập Vault trong khi Pod cũ vẫn còn hoạt động. Mỗi instance có thể giữ token, xin database credentials với lease, dùng PKI, Transit hoặc Vault Agent.

**Tăng phiên bản không trực tiếp tạo token hay lease; chính số phiên xác thực, các yêu cầu cấp secret động và vòng đời tài nguyên quyết định mức tăng.** Hiểu nguyên tắc này giúp dự báo tải Vault trước khi rollout, tránh tăng đột biến token/lease và phân biệt mở rộng bình thường với rò rỉ tài nguyên sau khi Pod dừng.

Trong module **SPRING_VAULT**, ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, xác thực theo workload, dùng KV secrets, token/lease, Transit encryption và PKI. Bài này kết hợp các chủ đề đó để:

- Ước tính số token, dynamic lease và lượng request khi chạy nhiều phiên bản.
- Phân biệt token renew với re-login, lease renew với cấp credential mới.
- Hiểu phạm vi quản lý của `LifecycleAwareSessionManager`, `SecretLeaseContainer` và Vault Agent.
- Đo đúng các metrics Vault, Spring Boot và Kubernetes trong lúc triển khai.
- Thiết kế rollout, cleanup, cảnh báo và kiểm thử tải an toàn.

## 1. Cần đếm những thực thể nào?

Vault không tự hiểu nhãn image `orders:v1` hay `orders:v2`. Vault ghi nhận **login, token, API requests và leases**. Mọi ứng dụng, phiên bản hoặc process chỉ là một nguồn phát sinh các hoạt động đó.

| Thực thể | Ví dụ | Có thể làm tăng tài nguyên nào? |
| --- | --- | --- |
| Replica/Pod | 20 Pod v1, 5 Pod v2 | Thêm process có thể tự đăng nhập và đọc secrets |
| Spring Vault client/session | Một `LifecycleAwareSessionManager` trong JVM | Một phiên token hoặc re-login khi hết khả năng renew |
| Vault Agent sidecar | Một Agent auto-auth trên mỗi Pod | Thêm phiên token độc lập so với client Java |
| Database dynamic secret | `database/creds/orders-readonly` | Mỗi lần cấp có thể tạo credential và lease riêng |
| KV v2 read | `secret/data/orders/config` | Request đọc dữ liệu; thông thường không tạo dynamic lease mới |
| Transit encrypt/HMAC | `transit/encrypt/orders-key` | Traffic API theo từng payload; không tự sinh lease credential mới |
| PKI issue/sign | `pki/issue/orders-server` | Chứng thư mới; có lease hay không tùy cấu hình role/backend |

**Không giả định một HTTP request đến ứng dụng tạo một Vault token.** Một client `VaultOperations` được cấu hình để tái sử dụng session có thể thực hiện hàng nghìn lượt đọc KV bằng cùng token. Ngược lại, một Pod có cả Vault Agent auto-auth và Spring Vault đăng nhập trực tiếp có thể giữ hai token độc lập.

### Token khác với lease

**Vault token** là kết quả xác thực, mang policies và thời hạn. Với **service token**, Vault lưu trạng thái và có cơ chế TTL/renew/revoke. **Batch token** ít chi phí lưu trữ hơn nhưng không hỗ trợ nhiều chức năng của service token, đặc biệt không hỗ trợ renew/revoke từng token hay accessor theo cùng cách. Không tự đổi sang batch token chỉ để giảm metric nếu ứng dụng cần lifecycle của service token.

**Lease** theo dõi thời hạn sử dụng của dynamic secrets và service token. Ví dụ:

~~~text
Pod v2 / Spring Vault session
    |
    +-- login Kubernetes/AppRole --> service token (TTL)
    |                               |
    |                               +-- GET database/creds/orders --> DB lease A
    |                               +-- GET database/creds/orders --> DB lease B
    |                               +-- GET secret/data/orders/config --> KV data
    |
    +-- Transit encrypt request --> ciphertext, không phải DB lease
~~~

Hai lần xin `database/creds/orders` thường tạo hai bộ database credentials với hai lease, dù dùng cùng token. Đọc KV v2 thông thường không phát hành lease động. Do đó chỉ đếm số lần gọi API là không đủ để suy ra tổng lease.

### Bốn sự kiện vòng đời khác nhau

| Sự kiện | Bản chất | Số tài nguyên có tăng? |
| --- | --- | --- |
| Token **renew** | Gia hạn token hiện có theo giới hạn cho phép | Không tự tạo token mới |
| Token **re-login** | Xác thực lại để nhận token khác | Có thể tăng tạm thời khi token cũ còn sống |
| Dynamic lease **renew** | Gia hạn lease credential đã cấp | Thường giữ nguyên lease/credential |
| Dynamic secret **rotation** | Xin credential mới khi cần thay đổi/hết hạn | Có thể phát sinh lease mới và overlap với lease cũ |

Khi service token bị revoke/hết hạn, các dynamic leases gắn với token có thể cũng bị revoke. Tuy vậy, Pod bị kill không có nghĩa Vault ngay lập tức nhận lệnh revoke; nếu không có cleanup thành công, phải chờ cơ chế TTL/revocation của Vault.

## 2. Rolling update, canary và blue-green ảnh hưởng ra sao?

| Kiểu rollout | Số Pod chạy đồng thời | Đặc điểm tài nguyên Vault |
| --- | --- | --- |
| **Rolling update** | Một phần v1 và v2 chồng lấn, có thể vượt desired replicas trong giới hạn surge | Peak phụ thuộc `maxSurge`, readiness, drain và TTL |
| **Canary** | Một nhóm v2 nhỏ chạy bên cạnh v1 | Token/lease phụ thuộc **số Pod**, không chỉ tỷ lệ traffic v2 |
| **Blue-green** | Hai nhóm ứng dụng có thể cùng chạy toàn bộ | Peak token/lease có thể gần gấp đôi nếu mỗi nhóm dùng cấu hình tương tự |

Một canary chỉ nhận **5% lưu lượng** vẫn có thể chạy nhiều Pod và mỗi Pod tự login Vault, tạo dynamic secrets ngay lúc startup. Tương tự, blue-green chưa chuyển traffic vẫn có thể tạo gần đủ token/lease của hệ thống thứ hai nếu `readiness` cần lấy secret trước khi mở cổng nhận request.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes Deployment
    participant O as Pod v1
    participant N as Pod v2
    participant V as Vault
    K->>N: Khởi động Pod v2
    N->>V: Login bằng workload identity
    V-->>N: Service token v2
    N->>V: Đọc KV / xin DB credentials
    V-->>N: Secret + lease mới nếu là dynamic secret
    K->>K: V2 vượt readiness
    K->>O: Drain traffic và terminate v1
    O->>V: Shutdown / revoke nếu thành công
    Note over O,V: Nếu Pod chết đột ngột, tài nguyên có thể còn đến TTL
~~~

Đỉnh sử dụng xuất hiện **sau khi Pod mới nhận token/lease nhưng trước khi token/lease cũ biến mất**. Vì thế biểu đồ token và lease có thể giảm chậm hơn biểu đồ số Pod v1.

## 3. Ước lượng số token/lease trước khi triển khai

Với từng phiên bản `v`, đặt:

| Ký hiệu | Diễn giải |
| --- | --- |
| `P_v` | Số Pod/instance còn hoạt động |
| `S_v` | Số phiên xác thực Vault độc lập trên mỗi Pod (Java, Agent...) |
| `D_v` | Số dynamic secret leases mà mỗi Pod đang giữ trung bình |
| `T_old` | Token của instance đã dừng nhưng vẫn còn hiệu lực |
| `L_old` | Dynamic leases từ instance cũ chưa hết hạn/revoke |

Ngân sách **gần đúng**:

\[
T_{\text{active}} \approx \sum_v P_v \times S_v + T_{\text{old}}
\]

\[
L_{\text{dynamic}} \approx \sum_v P_v \times D_v + L_{\text{old}}
\]

Với những token trên là **service tokens**, một mô hình đơn giản cho số lease được Vault theo dõi là:

\[
L_{\text{tracked}} \approx T_{\text{service}} + L_{\text{dynamic}} + L_{\text{other}}
\]

Đây là công thức lập **capacity budget**, không phải đẳng thức chính xác của toàn bộ các metrics. Batch token không có chi phí token-store giống service token; backend, namespace, replication, lease không thể revoke và tình trạng TTL thực tế đều ảnh hưởng kết quả.

### Ví dụ có số liệu cụ thể

Giả sử `orders-api` có 20 Pod v1. Mỗi Pod:

- Sử dụng **một** Spring Vault session với một service token.
- Xin **một** dynamic database credential và duy trì một lease của nó.
- Không chạy Vault Agent, không có lease từ những đợt rollout trước.

| Trạng thái | Pod v1 | Pod v2 | Service tokens | DB leases | Tracked leases ước tính |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bình thường | 20 | 0 | 20 | 20 | 40 |
| Rolling, thêm 5 Pod v2 | 20 | 5 | 25 | 25 | 50 |
| Blue-green, cả hai nhóm đủ 20 Pod | 20 | 20 | 40 | 40 | 80 |
| Hoàn tất và cleanup đầy đủ | 0 | 20 | 20 | 20 | 40 |

Nếu trên 25 Pod ở đỉnh rolling còn có **một Vault Agent tự auto-auth trên mỗi Pod**, trong khi Java vẫn tự login, ước lượng thành **50 service tokens**. Khi chỉ Java xin DB credentials, còn 25 DB leases, tổng tracked leases theo mô hình là **75**. Nếu Agent cũng xin DB credentials độc lập, số DB leases có thể tăng tiếp. Vì vậy phải kiểm kê **chủ sở hữu từng request**, không suy diễn từ tên phiên bản.

Nếu v1 bị force-kill và không dọn token, những token/lease cũ còn TTL sẽ tồn tại cùng v2 và làm tổng số đo cao hơn bảng. Đây chính là lý do cần theo dõi cả **số Pod đang chạy** lẫn **tài nguyên chưa expire**.

### Ước lượng làn sóng request lúc startup

Giả sử một Pod cần ít nhất 1 lần login, 3 lần đọc KV và 2 request cấp dynamic credentials, tổng cộng **6 request Vault/Pod**. Khi 30 Pod khởi động trong 10 giây:

\[
R_{\text{startup}} \approx \frac{30 \times 6}{10} = 18\ \text{request/giây}
\]

Đây chỉ là mức trung bình của các API call được liệt kê: chưa bao gồm token lookup, retry, renew, Transit/PKI, nhiều bước auth hay request khác. Nếu 30 Pod khởi động dàn đều trong 2 phút, tốc độ trung bình giảm nhiều; tuy vậy vẫn cần quan sát **đỉnh theo cửa sổ ngắn**, không chỉ trung bình toàn đợt.

## 4. Spring Vault quản lý token theo phạm vi JVM

### `LifecycleAwareSessionManager`

Spring Vault cung cấp `LifecycleAwareSessionManager` để lấy token thông qua `ClientAuthentication`, quản lý TTL, renew và thực hiện re-login khi cần. Trong một process, manager có thể phối hợp nhiều thread yêu cầu token thay vì tạo một token mới cho mỗi request.

Các điểm quan trọng khi scale:

1. **Mỗi JVM/Pod là một phạm vi session riêng**; hai Pod dùng cùng Kubernetes service account vẫn thường có hai lần login và hai token riêng.
2. Nếu Spring-managed `VaultOperations` và session manager được tái sử dụng qua dependency injection, hàng nghìn lượt đọc KV có thể dùng chung một token còn hợp lệ.
3. Nếu code tự tạo nhiều `VaultTemplate`, `ClientAuthentication` và `SessionManager` độc lập trong cùng process, số phiên login có thể cao hơn số Pod.
4. `LoginToken` do phương thức login cấp được `LifecycleAwareSessionManager` xử lý lifecycle và có thể được revoke khi manager shutdown đúng cách. `VaultToken` cấp tĩnh có semantics khác: tài liệu Spring Vault nêu manager không tự revoke kiểu token này như `LoginToken`.
5. Nếu process bị `SIGKILL`, mất node hoặc shutdown chưa xong, cleanup không chắc chạy; TTL hữu hạn vẫn là cơ chế dự phòng cần thiết.

**Token renew không tạo thêm token mới.** Token count có thể tăng do **re-login**, restart hoặc các session manager độc lập, đặc biệt khi token cũ chưa được revoke/expire.

### `SecretLeaseContainer` quản lý dynamic secret

`SecretLeaseContainer` theo dõi các `RequestedSecret`, renew/rotate lease và phát các sự kiện cho listener. Nhiều đăng ký giống nhau **trong một container** được hợp nhất theo semantics của nó; các **Pod khác nhau không chia sẻ container** hay lease.

| Hành vi | Ý nghĩa |
| --- | --- |
| `start()` | Bắt đầu theo dõi/yêu cầu secret đã đăng ký |
| `renew(...)` | Gia hạn lease đủ điều kiện |
| `rotate(...)` | Lấy secret mới theo chính sách rotation |
| `stop()` | Dừng các hoạt động background; không tương đương revoke toàn bộ lease |
| `destroy()` | Thực hiện cleanup/revoke lease của container khi lifecycle hoàn tất |

Ví dụ, 20 Pod cùng đăng ký `database/creds/orders-readonly` thường nhận 20 bộ credential động độc lập. Khi rotate, một Pod có thể tạm thời có credential cũ và mới. Sự kiện renewal/rotation của Spring Vault chưa có nghĩa connection pool **HikariCP/JDBC đã sử dụng credential mới**: phần cập nhật pool/client cần thiết kế và kiểm thử riêng.

### Vault Agent có thể tạo thêm một token

~~~text
Pod orders-v2
  +-- Spring Boot: Spring Vault auth -> Token A
  |                                  +-- DB lease(s) nếu có
  +-- Vault Agent: auto_auth -------> Token B
                                     +-- KV/DB/PKI template nếu cấu hình
~~~

Nếu Java chỉ đọc file Agent render, nó có thể không cần session/token A. Nếu Java cần Transit encrypt theo từng payload trong khi Agent quản lý file KV, việc tồn tại cả hai là hợp lý nhưng phải tính toán. Tránh để Agent và Java cùng rotation một credential mà không có người sở hữu vòng đời rõ ràng.

## 5. Vì sao scale down không làm lease biến mất ngay?

Sự kiện Pod đã bị xóa **không chứng minh**:

- Spring context đã đóng sạch và session manager/lease container đã chạy cleanup.
- Vault đã nhận request revoke và xử lý xong.
- Database backend đã thu hồi đúng username/password cũ.
- Connection pool ở Pod cũ đã drain toàn bộ giao dịch.
- Telemetry đã cập nhật ngay sau khi thao tác kết thúc.

Một quy trình triển khai có kiểm soát:

1. Khởi động v2 từng nhóm, đợi readiness chứng minh auth và secret cần thiết đã sẵn sàng.
2. Ngừng nhận request mới ở v1, cho request đang xử lý đủ thời gian hoàn tất.
3. Đóng database/HTTP clients và Spring context đúng thứ tự; để các thành phần token/lease cleanup.
4. Theo dõi số Pod v1 giảm, token count và lease count theo thời gian, kể cả độ trễ của metrics.
5. Nếu số liệu không trở về baseline sau cửa sổ TTL kỳ vọng, điều tra token/lease **đúng owner và scope** trước khi revoke.

Một lỗi phổ biến là service crash-loop: Pod mới liên tục login/xin credentials, Pod cũ chết trước cleanup, khiến số lease tăng dù số replica Ready không tăng. **TTL quá dài** làm hiện tượng kéo dài; TTL quá ngắn lại tăng renew/rotation traffic hoặc gây lỗi mất hiệu lực giữa request. Cần một TTL cân bằng với thời gian xử lý, restart, mạng và mục tiêu an toàn.

Không revoke token cũ trước khi connection pool và request của Pod cũ đã drain: Vault có thể revoke dynamic leases phụ thuộc token, khiến credential database bị vô hiệu ngay trong giao dịch.

## 6. Quan sát ở ba tầng cùng một timeline

~~~mermaid
flowchart LR
    K[Kubernetes: Pod v1/v2, Ready, Terminating] --> D[Dashboard rollout]
    A[Java: auth, read, renew, rotate, errors, latency] --> D
    V[Vault: token, lease, expiration, rate limit] --> D
    D --> O[Phân biệt surge bình thường và leak lifecycle]
~~~

### Metrics có sẵn ở Vault

| Metric | Công dụng | Giới hạn diễn giải |
| --- | --- | --- |
| `vault.token.count` | Token chưa expire/revoke trong token store | Được cập nhật theo chu kỳ, ví dụ 10 phút; không phải số Pod real-time |
| `vault.token.count.by_auth` | Đếm service token theo auth method | Kiểm tra Kubernetes/AppRole; labels và khả năng xuất tùy phiên bản |
| `vault.expire.num_leases` | Các leases đủ điều kiện eventual expiry | Bao gồm token lease và dynamic lease, không chỉ database |
| `vault.expire.num_irrevocable_leases` | Lease không thể revoke tự động | Không dùng thay cho total active leases |
| `vault.expire.leases.by_expiration` | Buckets lease sắp đến hạn | Dự báo đợt expire/revocation |
| `vault.expire.register`, `vault.expire.register-auth` | Chi phí đăng ký lease/token lease | Phát hiện chi phí tăng lúc scale |
| `vault.expire.renew`, `vault.expire.renew-token` | Thời gian xử lý renew | Phân biệt renew với login mới |
| `vault.expire.lease_expiration`, `vault.expire.lease_expiration.error` | Expire thành công và lỗi | Theo dõi backlog/khó khăn cleanup |

Tên metric trong tài liệu Vault thường có dấu chấm, còn exporter Prometheus có thể biểu diễn bằng dấu gạch dưới, chẳng hạn `vault_expire_num_leases`. Kiểm tra tên thực trong monitoring của cluster trước khi tạo PromQL/alert. Không giả định mọi metric/nhãn luôn bật.

Monitoring service với quyền riêng có thể đọc `GET /v1/sys/metrics`:

~~~bash
# Chỉ chạy với monitoring token được bảo vệ; không log token.
curl --silent --show-error --fail \
  --header "X-Vault-Token: $VAULT_MONITORING_TOKEN" \
  "$VAULT_ADDR/v1/sys/metrics?format=prometheus"
~~~

Endpoint này cần được cấu hình, phân quyền và bảo vệ bằng TLS; yêu cầu metadata thống kê cần đúng node/namespace theo kiến trúc Vault. **Không cấp quyền đọc metrics toàn cluster cho token của ứng dụng chỉ cần đọc KV.**

### Cạm bẫy của `sys/leases/count`

`GET /v1/sys/leases/count?type=irrevocable` **chỉ đếm irrevocable leases**, không trả tổng mọi active leases. Hãy dùng `vault.expire.num_leases` để theo dõi tổng số lease đủ điều kiện hết hạn, đồng thời xem `vault.expire.num_irrevocable_leases` khi cần.

`LIST /sys/leases/lookup/<prefix>` có thể liệt kê lease IDs nhưng cần quyền `sudo`, có thể gây tải và lộ metadata nhạy cảm. Không dùng thao tác list toàn cluster làm nguồn dashboard thông thường. `sys/leases/tidy` và `revoke-prefix` là các thao tác quản trị mạnh, không phải giải pháp mặc định để làm số lease “đẹp” sau rollout.

### Metrics ứng dụng Spring Boot

Những metric cần tự instrument, thay vì giả định Spring Vault tạo sẵn:

- Login attempts, login failures, token renewal/re-login events theo phiên bản ứng dụng.
- Read KV, lấy DB credentials, gọi Transit/PKI: request duration, lỗi `403`/`429`/`5xx` và timeout.
- Số `RequestedSecret` đang theo dõi trên **mỗi instance**; lease renew/rotation/error events.
- Khoảng thời gian từ khi container khởi động đến khi dependency Vault đủ điều kiện readiness.
- Thời điểm application connection pool hoặc TLS context **áp dụng credential/chứng thư mới**, không chỉ thời điểm Vault cấp thành công.

Có thể dùng Micrometer với các tên tự đặt `app_vault_login_attempts_total`, `app_vault_dynamic_lease_registrations` và `app_vault_read_duration_seconds`. Chúng là ví dụ về custom metrics, **không** mặc định là metric Spring Vault tự phát hành. Nhãn cần có cardinality thấp: `service`, `environment`, `version` và `operation` từ tập định trước. Không gắn raw token, lease ID, SecretID, password, URL chứa secret hoặc request payload vào metric/log/traces.

## 7. Ví dụ Java: một Vault client dùng chung, telemetry không chứa secret

Ví dụ Java 17+, Spring Vault và Micrometer. Bean `VaultOperations` đã được cấu hình workload authentication và TLS trust. Service đọc một KV v2 secret bằng **client được inject**, đo thời gian và tổng lỗi; nó không tự login mới cho từng HTTP request.

~~~java
import java.util.Map;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersConfigReader {

    private final VaultKeyValueOperations kv;
    private final Timer readTimer;
    private final Counter failures;

    public OrdersConfigReader(VaultOperations vault, MeterRegistry meters) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
        this.readTimer = Timer.builder("app.vault.kv.read")
                .tag("operation", "ORDERS_CONFIG_READ")
                .register(meters);
        this.failures = Counter.builder("app.vault.kv.failures")
                .tag("operation", "ORDERS_CONFIG_READ")
                .register(meters);
    }

    public String apiKey() {
        return readTimer.record(() -> {
            try {
                VaultResponse response = kv.get("orders/config");
                if (response == null) {
                    throw new IllegalStateException(
                            "Thiếu cấu hình Vault bắt buộc");
                }
                Map<String, Object> data = response.getRequiredData();
                Object value = data.get("apiKey");
                if (!(value instanceof String key) || key.isBlank()) {
                    throw new IllegalStateException(
                            "Thiếu trường cấu hình bắt buộc");
                }
                return key; // Chỉ trả cho nghiệp vụ nội bộ.
            } catch (RuntimeException ex) {
                failures.increment();
                throw ex; // Lớp trên xử lý lỗi an toàn.
            }
        });
    }
}
~~~

Đoạn mã chỉ đo **KV read timing/error**, không tự đo token/lease lifecycle. Muốn quan sát login/renew và lease events, cần listener/instrumentation riêng tương thích phiên bản Spring Vault đang chạy. Không gọi `log.error(..., ex)` hay xuất raw response khi exception có thể chứa dữ liệu nhạy cảm.

Nếu ứng dụng cache kết quả KV, số request Vault sẽ thấp hơn số lần business logic sử dụng secret. Một cơ chế cache có thể giúp giảm tải nhưng phải đi kèm thời hạn refresh, chính sách dữ liệu cũ và cách phản ứng khi Vault tạm thời mất kết nối.

## 8. Giảm đỉnh tải trong lúc nhiều phiên bản chạy

### Giới hạn số Pod xuất hiện đồng thời

Một cấu hình rollout minh họa cho Deployment:

~~~yaml
# Trích đoạn spec, chưa phải manifest Kubernetes đầy đủ.
spec:
  replicas: 20
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 5
      maxUnavailable: 0
~~~

Trong điều kiện rollout bình thường, controller có thể tạo thêm tới 5 Pod mới so với desired replicas; terminating pods và readiness vẫn ảnh hưởng số Pod thực tế. Cấu hình này **không trực tiếp giới hạn số request Vault mỗi Pod**. Nếu mỗi Pod xin nhiều credentials và retry đồng thời, request peak vẫn có thể rất lớn.

Một số biện pháp hữu ích:

1. **Tái sử dụng session manager** và `VaultOperations` cho mỗi process. Không tạo Vault client/login trong từng request.
2. **Giới hạn concurrency và tốc độ startup** theo tổng request Vault/Pod; thêm jitter khi lịch renew/rotation có thể đồng bộ.
3. **Dùng TTL phù hợp:** quá ngắn làm tăng renew/rotation traffic, quá dài giữ lại token/lease từ Pod đã chết.
4. **Quản lý dynamic credentials theo lifecycle:** cùng Pod nên tránh tạo nhiều credential cho cùng một nhu cầu nếu không cần, nhưng vẫn giữ tách biệt quyền giữa các workload.
5. **Giám sát startup readiness** và backoff khi Vault bị 429/timeout; tránh toàn bộ Pod re-login dồn dập.
6. **Kiểm soát Vault Agent cùng Java:** xác định ai đọc KV, ai xin DB credentials, ai sở hữu rotation và ai đóng token/lease.
7. **Draining trước shutdown:** không revoke credential mà Pod cũ vẫn đang dùng để xử lý transaction.

### Rate limit và lease count quotas

Vault có **rate limit quotas** tùy cấu hình, giúp giới hạn lượng API traffic theo phạm vi namespace/mount/path. Khi chạm giới hạn hoặc gặp sự cố, ứng dụng có thể nhận 429 và cần retry có backoff, jitter, deadline và số lần tối đa.

**Lease count quotas** phụ thuộc phiên bản/edition Vault; tài liệu HashiCorp mô tả tính năng này cho Enterprise. Chạm lease quota có thể làm request cấp credential mới thất bại trong khi đọc KV tĩnh vẫn hoạt động. Không suy đoán nguyên nhân chỉ từ số lỗi 4xx: phải kiểm tra quota thực tế đang bật và audit/metrics.

Không đổi từ service token sang batch token một cách máy móc: batch token không hỗ trợ renew và có semantics lease khác. Lựa chọn token type phải phù hợp auth method, TTL, chính sách và khả năng phục hồi.

## 9. Nhận diện bất thường trên dashboard

| Dấu hiệu | Nguyên nhân khả dĩ | Cần kiểm tra |
| --- | --- | --- |
| Token/lease tăng khi v2 lên | Surge bình thường, nhiều Pod sống song song | Đối chiếu số Pod v1/v2 và số session/lease trên Pod |
| Token tăng gấp đôi số Pod | Java và Agent cùng login, hoặc nhiều session managers | Kiểm kê danh tính auto-auth và Java client |
| Token không tăng nhưng DB lease tăng | Một token xin nhiều credentials, rotation overlap | Endpoint `database/creds`, RequestedSecret registrations |
| Token vẫn tăng sau rollout | Crash loop/re-login, shutdown không cleanup | Restart count, login rate, TTL và token revoke events |
| Lease giảm chậm sau scale down | TTL dài, cleanup lỗi hoặc metric chậm | Thời hạn lease, expire/revoke error, chu kỳ scrape |
| Vault latency/429 tăng lúc canary | Login burst, rate quota, storage/audit bottleneck | RPS theo endpoint, quota, register/renew time |
| Database cạn tài khoản/kết nối | Credential và pool nhân lên theo Pod | DB engine lease, max connections, kích thước Hikari pool |
| `vault.token.count` trễ vài phút | Metric cập nhật theo chu kỳ | Login events và app metrics thời gian gần |
| `sys/leases/count` rất thấp | Đang đếm `irrevocable`, không phải tất cả lease | Dùng `vault.expire.num_leases` và đối chiếu loại |

**Không kết luận ngay có “lease leak” chỉ vì số liệu chưa về baseline một giây sau rollout.** Phải biết TTL, độ trễ metric, các instance còn chạy, trạng thái rotation và số tài nguyên khác dùng chung Vault. Ngược lại, cũng không bỏ qua xu hướng tăng kéo dài khi Pod đã ổn định.

## 10. Thực hành kiểm thử tích hợp theo đợt rollout

Chuẩn bị **môi trường lab riêng**: Vault test instance, KV v2 `secret/`, database role động và Spring Boot service có workload auth. Dùng thông tin giả, không đưa token hoặc password thật vào output test.

1. **Baseline:** chạy 4 Pod v1, mỗi Pod một Spring Vault session và một database lease; đo Pod Ready, login events, token/lease metrics, đọc KV.
2. **Canary:** thêm 2 Pod v2; kỳ vọng token/DB lease tăng gần tương ứng 2 Pod mới, sau khi xét thời gian cập nhật metric.
3. **Blue-green:** giữ 4 Pod v1 và tăng lên 4 Pod v2; đo peak số token, lease, startup RPS, latency và DB connections.
4. **Scale down bình thường:** drain v1, đóng Spring context đúng cách và đo mức giảm; đối chiếu thời hạn TTL và lease revoke/expiration.
5. **Crash test:** ép một Pod lab dừng đột ngột, quan sát những token/lease còn sống cho đến khi Vault xử lý TTL.
6. **Lỗi Vault:** mô phỏng timeout và 429 trong startup/rotation; kiểm tra retry/backoff và readiness, tránh request storm.
7. **Dual client:** thêm Vault Agent auto-auth trong Pod, kiểm chứng số token tăng so với baseline chỉ Java; xác định đúng component cấp DB credential.

| Trường hợp | Điều kiện đạt |
| --- | --- |
| 4 Pod v1, một session/Pod | Khoảng 4 service tokens và 4 DB leases thuộc lab, cộng nhiễu nếu có |
| Thêm 2 Pod v2 | Tăng theo Pod mới, không theo tỷ lệ traffic của canary |
| Mỗi request HTTP chỉ đọc KV | Không tạo thêm dynamic DB lease nếu tái sử dụng session |
| Token renew | Không phát sinh token mới vì chính thao tác renew |
| Token re-login | Có token mới, nhưng token cũ cần được dọn đúng vòng đời |
| Graceful shutdown | Các tài nguyên Spring quản lý được cleanup theo hợp đồng và quyền, có độ trễ thống kê |
| Force kill | Token/lease có thể còn sống theo TTL dù Pod đã mất |
| Lỗi quota/429 | App dùng backoff/jitter, không retry đồng thời vô hạn |
| Vault Agent + Java | Số session/token phản ánh cả hai nếu cả hai tự login |

Không assert con số chính xác từng giây khi metrics có chu kỳ cập nhật, TTL và các workloads khác cùng cluster. Nên dùng namespace/mount lab riêng, ghi baseline trước test và so sánh độ lệch sau các cửa sổ thời gian phù hợp. Tránh thử revoke-prefix trên mount dùng chung.

## 11. Checklist trước khi phát hành

- [ ] Đã tính số Pod v1/v2 chạy đồng thời, `maxSurge`, thời gian canary và blue-green overlap.
- [ ] Đã biết số Vault sessions độc lập trên một Pod, kể cả Java và Agent.
- [ ] Đã phân loại các secret KV tĩnh, dynamic database, PKI và các API Transit.
- [ ] Đã ước lượng token/lease peak, cộng thêm phần tồn do crash, re-login và rotation.
- [ ] Đã kiểm tra `LifecycleAwareSessionManager` và `SecretLeaseContainer` hoạt động/cleanup theo lifecycle.
- [ ] Đã đặt TTL, retry, backoff, jitter và concurrency theo khả năng Vault/DB backend.
- [ ] Dashboard hiển thị Pod Ready/Terminating, login/renew/rotation và metrics token/lease cùng timeline.
- [ ] Đã thử scale down bình thường và force kill trong môi trường lab.
- [ ] Đã biết rate/lease quota hiện hành và quy trình xử lý khi đụng giới hạn.
- [ ] Không log token, lease ID, private key, password hoặc raw Vault response.

## 12. Ghi nhớ

**Khi nhiều phiên bản ứng dụng chạy đồng thời, số token tăng theo các phiên xác thực còn sống và số lease động tăng theo các yêu cầu cấp secret chưa hết hạn.** Rolling update, canary và blue-green làm thay đổi số Pod cùng tồn tại; Spring Vault, Vault Agent và dynamic secret rotation quyết định tài nguyên cụ thể.

Để quản lý hiệu năng, dự báo **Pod × session/token/lease**, cộng phần còn tồn từ Pod cũ; quan sát `vault.token.count`, `vault.expire.num_leases`, chi phí renew/revoke và tốc độ login theo cùng timeline với quá trình rollout. Token renew không phải token mới; đọc KV v2 không giống xin database credentials; dừng Pod cũng không đảm bảo mọi lease biến mất tức thì.

### Câu hỏi tự kiểm tra

1. 20 Pod v1 chuyển thành 20 Pod v1 + 5 Pod v2, mỗi Pod có một service token và một DB lease. Vì sao tracked lease ước tính tăng từ 40 lên 50?
2. Nếu một Pod có cả Spring Vault trực tiếp và Vault Agent auto-auth, bạn cần bổ sung biến nào vào công thức token?
3. Vì sao `vault.expire.num_leases` không bằng số database credentials và `/sys/leases/count?type=irrevocable` không đại diện cho mọi lease?
4. Sự khác biệt về token count giữa thành công `renew` và `re-login` là gì?
5. 1.000 lượt đọc KV v2 bằng cùng một session manager có tạo 1.000 dynamic leases không?
6. Vì sao token/lease có thể giảm chậm hơn số Pod cũ sau rollout?
7. Bạn cần những metric nào để phân biệt blue-green surge với token tăng do crash loop?
8. Vì sao revoke token của Pod cũ trước khi drain xong có thể làm hỏng giao dịch database?

### Tài liệu tham khảo

- [HashiCorp Vault — Token concepts, service và batch tokens](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [HashiCorp Vault — Lease, renew và revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — Telemetry metrics](https://developer.hashicorp.com/vault/docs/internals/telemetry/metrics/all)
- [HashiCorp Vault — Key metrics for common health checks](https://developer.hashicorp.com/vault/docs/internals/telemetry/key-metrics)
- [HashiCorp Vault — System API leases](https://developer.hashicorp.com/vault/api-docs/system/leases)
- [HashiCorp Vault — System API metrics](https://developer.hashicorp.com/vault/api-docs/system/metrics)
- [HashiCorp Vault — Resource quotas](https://developer.hashicorp.com/vault/docs/concepts/resource-quotas)
- [Spring Vault — Authentication and token lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Credentials rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault — LifecycleAwareSessionManager API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [HashiCorp Vault — Agent templates và secret renewal](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent/template)
