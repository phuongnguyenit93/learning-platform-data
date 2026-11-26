# Tương tác giữa đăng nhập lại và việc đăng ký secret trong Spring Vault

## 1. Bài toán: token mới nhưng secret cũ còn dùng được không?

Một ứng dụng Java sử dụng **Spring Vault** thường có hai hoạt động chạy song song: đăng nhập vào **HashiCorp Vault** để lấy token, và đăng ký những secret cần quản lý trong suốt vòng đời ứng dụng. Chẳng hạn dịch vụ Orders dùng `VaultTemplate` với **AppRole/Kubernetes auth**, đồng thời lấy thông tin tài khoản database động từ `database/creds/orders-readonly`. Cả Vault token lẫn database credential đều có thời hạn, nhưng chúng **không phải cùng một đối tượng**.

Giả sử phiên đăng nhập tạo token `T1` với TTL 15 phút; ở phút thứ 1, ứng dụng dùng `T1` yêu cầu database credential `C1` với lease TTL 30 phút. Khi `T1` sắp hết hạn, `LifecycleAwareSessionManager` có thể gia hạn nó hoặc đăng nhập lại để nhận `T2`. Câu hỏi cần trả lời là: **đăng nhập lại có khiến Spring Vault đăng ký secret thêm lần nữa, tự tạo credential mới hoặc giữ cho `C1` luôn hợp lệ hay không?**

Không có một phép suy ra đơn giản như vậy. Cần phân biệt:

- **Đăng ký secret:** yêu cầu Spring Vault quản lý một đường dẫn và chế độ `RENEW` hoặc `ROTATE`. Việc đăng ký là trạng thái trong ứng dụng.
- **Đăng nhập lại:** dùng phương thức xác thực nhận **Vault token mới**, có thể thay token đang gắn với các request tiếp theo.
- **Cấp mới, renew, revoke secret:** là hoạt động của Vault secrets engine và lease riêng biệt; phụ thuộc TTL, quyền và quan hệ giữa token với lease.
- **Tiêu thụ credential:** kết nối database, pool connection hoặc đối tượng nghiệp vụ phải sử dụng bộ credential còn hiệu lực. Thay giá trị ở Vault không mặc nhiên thay credential đã nằm trong một connection pool.

Trong chương **Vòng đời lease**, bài học tập trung vào **dynamic secrets**, xác thực workload, `RequestedSecret` và kiểm thử tích hợp. KV v2, Transit và PKI có những đặc điểm vòng đời riêng.

## 2. Ba vòng đời cần giữ tách biệt

| Đối tượng | Ai quản lý? | Thông tin quan trọng | Hết hạn/đổi mới có ý nghĩa gì? |
| --- | --- | --- | --- |
| **Login token** | Vault auth method và `LifecycleAwareSessionManager` | Token TTL, max TTL, renewable, policy, parent/orphan relationship | Renew token hiện tại hoặc re-login để nhận token khác. |
| **Secret lease** | Vault secrets engine và `SecretLeaseContainer` | `lease_id`, `lease_duration`, `renewable`, giới hạn backend | Gia hạn được trong giới hạn, hoặc hết hiệu lực và cần cấp lại nếu chế độ cho phép. |
| **Đăng ký RequestedSecret** | `SecretLeaseContainer` / `SecretsRegistry` trong process Java | Secret path và mode `RENEW`/`ROTATE` | Giữ ý định quản lý secret; đăng ký không phải token và không tự hết hạn theo token TTL. |

Một số khái niệm dễ nhầm:

**`VaultToken` khác `LoginToken`.** `LoginToken` chứa thông tin phục vụ renew và expiry; token được trả về bởi các phương thức login thường có lifecycle cần quản lý. Với token được cung cấp sẵn qua `TokenAuthentication`, có thể phải tra cứu token tự thân để biết TTL/renewability. Quy tắc tự thu hồi token khi shutdown cũng phụ thuộc loại token và cách session manager được cấu hình.

**Lease không phải “secret đã đăng ký”.** `RequestedSecret.rotating("database/creds/orders-readonly")` chỉ mô tả mong muốn quản lý endpoint. Một lần GET tới endpoint này có thể tạo username/password mới cùng `lease_id`. Một `RequestedSecret` có thể lần lượt gắn với nhiều lease trong quá trình rotate.

**Secret tĩnh khác secret động.** Đọc KV v2 tại `secret/data/orders/config` thường không phát hành credential có khả năng revoke qua lease như database dynamic credentials. Đừng mong `SecretLeaseContainer` làm cho giá trị KV v2 mới tự động có hiệu lực trong mọi bean, pool hoặc tiến trình. `delete_version_after` của KV v2 cũng không phải TTL của login token.

## 3. Luồng đầy đủ từ login đến đăng ký và rotation

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant SM as LifecycleAwareSessionManager
    participant LC as SecretLeaseContainer
    participant V as Vault
    participant DB as Database / Consumer
    App->>LC: register ROTATE(database/creds/orders-readonly)
    App->>LC: start (thường qua Spring lifecycle)
    LC->>SM: lấy token cho request
    SM->>V: đăng nhập bằng workload identity
    V-->>SM: T1 + TTL + policies
    SM-->>LC: T1
    LC->>V: đọc database/creds/orders-readonly
    V-->>LC: C1 + lease L1
    LC-->>DB: SecretLeaseCreatedEvent(C1)
    SM->>V: renew T1 hoặc login lại
    V-->>SM: token hợp lệ / T2
    Note over LC,SM: Việc đổi token không đồng nghĩa cấp C2 ngay
    LC->>V: renew L1 (nếu còn hợp lệ)
    V-->>LC: gia hạn L1 hoặc lỗi/expiry
    LC->>V: request lại khi mode ROTATE và cần rotate
    V-->>LC: C2 + lease L2
    LC-->>DB: SecretLeaseRotatedEvent(C2)
~~~

Biểu đồ thể hiện **các khả năng** chứ không ngụ ý mọi sự kiện sẽ diễn ra chính xác theo một lịch cố định. Nếu `T1` hết hạn rồi bị thu hồi cùng những lease phụ thuộc nó, `L1` có thể không còn giá trị. Nếu token chỉ được **renew**, định danh token không thay đổi. Nếu token được cấp lại thành `T2`, request mới của `VaultOperations` dùng session manager sẽ lấy token hiện hành, còn khả năng tiếp tục renew lease cũ phải được kiểm chứng theo quyền và quan hệ lease thực tế.

Tại mọi mốc, cần đối chiếu **auth event, lease event và trạng thái consumer**. Token lifecycle và secret lease lifecycle chạy trên những scheduler/quy tắc riêng; “re-login thành công” không chứng minh database credential đã rotate.

## 4. Đăng ký secret bằng `SecretLeaseContainer`

Spring Vault cung cấp `SecretLeaseContainer` trong package `org.springframework.vault.core.lease`. Container đăng ký những `RequestedSecret`, lấy secret từ `VaultOperations`, chạy tác vụ gia hạn/rotation trên background scheduler và gửi sự kiện tới listener.

Hai chế độ quan trọng:

| Chế độ | Khai báo | Khi lease còn renewable | Khi lease hết hạn |
| --- | --- | --- | --- |
| `RENEW` | `RequestedSecret.renewable(path)` hoặc `requestRenewableSecret(path)` | Thử renew lease hợp lệ | Không tự lấy một credential mới như chế độ rotate. |
| `ROTATE` | `RequestedSecret.rotating(path)` hoặc `requestRotatingSecret(path)` | Thử renew khi có thể | Yêu cầu secret mới tại cùng path, tạo lease mới nếu backend chấp nhận. |

`ROTATE` không có nghĩa cứ mỗi lần session manager đăng nhập lại thì phải cấp credential mới; nó có nghĩa container **tiếp tục quản lý khả năng cấp mới** khi lease cần rotation. Với credential có giới hạn sử dụng hay TTL từ database backend, ứng dụng thường chọn `ROTATE` vì muốn tiếp tục hoạt động sau khi lease cũ hết hiệu lực.

### Mã Java đăng ký secret và lắng nghe sự kiện

Ví dụ dưới giả định `VaultOperations` đã được cấu hình với `SessionManager` theo workload identity và ứng dụng có bean `CredentialSink` chịu trách nhiệm đưa dữ liệu vào connection pool một cách an toàn:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;
import org.springframework.vault.core.lease.event.SecretLeaseRotatedEvent;

@Configuration
public class OrdersLeaseConfiguration {

    @Bean
    ThreadPoolTaskScheduler leaseTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-lease-");
        return scheduler; // Spring quản lý initialize/shutdown.
    }

    @Bean
    SecretLeaseContainer ordersLeaseContainer(
            VaultOperations vault,
            ThreadPoolTaskScheduler leaseTaskScheduler,
            CredentialSink sink) {

        SecretLeaseContainer container =
            new SecretLeaseContainer(vault, leaseTaskScheduler);

        container.setMinRenewal(Duration.ofSeconds(10));
        container.setExpiryThreshold(Duration.ofSeconds(30));

        RequestedSecret secret = container.requestRotatingSecret(
            "database/creds/orders-readonly");

        // Listener được gắn trước khi Spring khởi động container.
        container.addLeaseListener(new LeaseListenerAdapter() {
            @Override
            public void onLeaseEvent(SecretLeaseEvent event) {
                if (!secret.equals(event.getSource())) {
                    return;
                }
                if (event instanceof SecretLeaseRotatedEvent) {
                    sink.replace(((SecretLeaseRotatedEvent) event)
                        .getSecrets());
                } else if (event instanceof SecretLeaseCreatedEvent) {
                    sink.replace(((SecretLeaseCreatedEvent) event)
                        .getSecrets());
                } else if (event instanceof SecretLeaseExpiredEvent) {
                    sink.markUnavailable();
                }
            }
        });

        container.addErrorListener((event, error) ->
            sink.recordError(error.getClass().getSimpleName()));
        return container;
    }

    public interface CredentialSink {
        void replace(Map<String, Object> credentialValues);
        void markUnavailable();
        void recordError(String errorType);
    }
}
~~~

**Giới hạn của ví dụ:** `CredentialSink` là hợp đồng nghiệp vụ cần được ứng dụng hiện thực thành bean. Hàm `replace` phải kiểm tra `username`/`password`, thay thế credential trong pool theo cách không gián đoạn và hạn chế lưu plaintext lâu hơn cần thiết. Không log map `credentialValues`. Listener có thể chạy trên thread khởi động hoặc background thread: không thực hiện thao tác blocking kéo dài trực tiếp trong callback; chuyển việc thay pool sang bộ điều phối có kiểm soát.

Là `SmartLifecycle`, `SecretLeaseContainer` do Spring quản lý có thể tự khởi động khi context sẵn sàng và dừng theo lifecycle. Nếu tự tạo container bên ngoài Spring, phải gọi `afterPropertiesSet()`, `start()`, và quản lý `stop()/destroy()` phù hợp. Đừng gọi `start()` thủ công lặp lại trong mỗi business request.

### Đăng ký trùng và listener đăng ký muộn

`SecretLeaseContainer` xem các đăng ký `RequestedSecret` bằng nhau như **một đăng ký**. Gọi `addRequestedSecret` lặp lại không nên được dùng làm chiến lược “refresh sau re-login”. Khi đăng ký listener cho một secret đã active, listener mới **không được bảo đảm nhận lại `SecretLeaseCreatedEvent` chứa giá trị đã phát trước đó**; nó có thể chỉ thấy những sự kiện renew/rotate tiếp theo.

Do đó, cần gắn listener và đăng ký đường dẫn **trước khi container bắt đầu fetch**. Nếu ứng dụng tự thêm secret động sau startup, hãy xây dựng quy trình đồng bộ trạng thái hiện tại và sắp xếp thứ tự nhận sự kiện cẩn thận. `unregister` loại bỏ đăng ký, ngừng renew/rotation và listener gắn với nó; không được mặc nhiên coi `unregister` là đã xóa tài khoản database hoặc revoke mọi lease.

## 5. Đăng nhập lại diễn ra ở đâu?

Trong luồng Spring Vault đồng bộ, `ClientAuthentication` (như Kubernetes auth, JWT/AppRole phù hợp) tạo Vault token. `LifecycleAwareSessionManager` cung cấp token cho `VaultTemplate`, duy trì token theo TTL, thử renew và khi cần có thể **đăng nhập lại** để nhận token tiếp theo.

~~~text
ClientAuthentication ──login──> LoginToken T1
         |                         |
         |                LifecycleAwareSessionManager
         |                     renew T1
         +──────re-login──────> LoginToken T2
                                  |
                          VaultTemplate request
                                  |
                         SecretLeaseContainer
                                  |
                         renew / rotate L1
~~~

Lưu ý thứ tự: secret container **gọi `VaultOperations`**, còn `VaultOperations` sử dụng session manager. Vì vậy token mới được gắn cho những HTTP request được thực hiện sau đó nếu cả hai cùng dùng **session manager được quản lý**. Nếu tạo `VaultTemplate` với chuỗi token tĩnh hoặc một `SimpleSessionManager` khác, việc re-login ở manager kia không tự cập nhật token của template này.

### Renew token khác login lại

- **Renew:** Vault gia hạn một token hiện hữu trong giới hạn cho phép. Token identity vẫn là T1; các lease đang quản lý không được tự động cấp mới chỉ vì TTL của token tăng.
- **Re-login:** Vault auth method tạo token mới T2 khi token cũ đã đến hạn hoặc không thể tiếp tục sử dụng. T2 phải được cấp đúng ACL để đọc/renew/revoke secret mà ứng dụng cần. T2 không tự biến lease L1 thành lease khác.
- **Đăng nhập lại thất bại:** nếu AppRole SecretID hết hạn, JWT của workload không được xoay, API authentication không sẵn sàng hoặc chính sách role thay đổi, manager không thể nhận token mới. Các lần fetch/renew phụ thuộc login sẽ phát sinh lỗi dù đăng ký trong container vẫn tồn tại.

Ví dụ với `AppRole`: thông tin `role_id` và `secret_id` có vòng đời riêng. Nếu cấu hình `secret_id_num_uses=1` nhưng workload cần re-login, lần login thứ hai có thể bị Vault từ chối. Với Kubernetes auth, projected ServiceAccount JWT cũng có thể hết hạn và cần được đọc lại từ nguồn đã được kubelet xoay. Không cache vô hạn JWT đã hết hạn trong `ClientAuthentication`.

**Không đồng nhất TTL của token và TTL của secret:** token T2 còn sống không chứng minh database credential C1 còn hợp lệ; lease L1 chưa hết hạn cũng không bảo đảm T2 có khả năng renew lease đó nếu thiếu quyền hoặc quan hệ với token phát hành L1.

## 6. Quan hệ parent token và lease khi re-login

Vault có thể liên kết lease của dynamic secret với token đã tạo ra nó. **Việc thu hồi hoặc hết hạn token cha có thể dẫn tới việc thu hồi các lease/credential phụ thuộc**. Chính xác tác động phụ thuộc loại token, token hierarchy (orphan hay không), loại secrets engine và cấu hình Vault.

Ví dụ T1 TTL 15 phút nhưng C1/L1 được cấp TTL 30 phút: tại phút 15, T1 có thể re-login thành T2, trong khi L1 còn thời hạn trên giấy nhưng thực tế có thể đã bị thu hồi theo quan hệ token. Container phải kiểm tra lease và quyền thực tế trước khi tiếp tục; mode `ROTATE` mới dự kiến cấp C2 khi cần. Vault không đẩy expiry event tới Java process, nên `SecretLeaseExpiredEvent` có thể đến sau thời điểm TTL thật.

Nếu worker chỉ sử dụng **KV v2 static secret**, đọc lại bằng T2 khi hợp lệ vẫn có thể trả phiên bản mới nhất; không tồn tại `lease_id` dynamic để renew. Nếu dùng **Transit encryption**, token T2 cần capability trên endpoint `transit/encrypt/.../decrypt/...` tương ứng, nhưng không có “credential rotation lease” do gọi Transit. Nếu sử dụng **PKI**, thời hạn chứng thư đã cấp chịu chính sách PKI và người dùng phải thay certificate tại TLS client/server; re-login không làm chứng thư cũ tự đổi.

### Phân biệt “giữ đăng ký” và “giữ quyền sử dụng”

Khi session manager đăng nhập lại, `SecretLeaseContainer` có thể **vẫn giữ `RequestedSecret`**. Nhưng giữ đăng ký chỉ là “tiếp tục theo dõi đường dẫn”. Ứng dụng vẫn cần:

1. Request/renew được Vault chấp nhận.
2. Lease mới hoặc cũ còn hiệu lực và phù hợp với policy.
3. Dữ liệu credential đã được áp dụng vào consumer (đặc biệt database pool).
4. Tình huống credentials bị revoke sớm được xử lý bằng cơ chế phát hiện lỗi, phục hồi và giới hạn retry.

Các điều kiện này phải được kiểm thử trong môi trường Vault tích hợp thực tế.

## 7. Bắt sự kiện token và secret để đồng bộ trạng thái

Spring Vault phát ra nhiều loại event giúp tách **xác thực** khỏi **secret management**:

| Nhóm | Sự kiện / hook | Hành động phù hợp |
| --- | --- | --- |
| Login token | `AuthenticationListener` / `AuthenticationErrorListener` của lifecycle session manager | Quan sát login, renew, revoke, lỗi xác thực, cập nhật trạng thái sức khỏe token. |
| Secret tạo lần đầu | `SecretLeaseCreatedEvent` | Kiểm tra payload, cài credential vào consumer. |
| Secret xoay | `SecretLeaseRotatedEvent` | Thay credential/pool, rút dần connection cũ theo chính sách. |
| Lease renew thành công | `AfterSecretLeaseRenewedEvent` | Cập nhật thời gian sống, tránh reload credential nếu giá trị không đổi. |
| Lease hết hạn | `SecretLeaseExpiredEvent` | Đánh dấu credential có thể không hợp lệ, kích hoạt phương án dự phòng. |
| Secret không tìm thấy | `SecretNotFoundEvent` | Báo tình huống thiếu secret hoặc sai đường dẫn/quyền. |
| Lỗi gọi Vault/renew | `SecretLeaseErrorEvent`, `LeaseErrorListener` | Phân loại 403, 404, timeout; báo lỗi và backoff phù hợp. |

Ở những phiên bản Spring Vault có hỗ trợ, `SecretLeaseContainer.getAuthenticationListener()` và `getAuthenticationErrorListener()` có thể được nối với hệ thống phát sự kiện xác thực của `LifecycleAwareSessionManager`. Đây là tích hợp để container **biết các thay đổi/ lỗi xác thực**, không phải lệnh bắt buộc mọi lần login lại phải cấp secret mới. Khi dùng Spring Cloud Vault auto-configuration, cần kiểm tra wiring đã được framework đăng ký để tránh lắp listener trùng.

Đặc biệt, `SecretLeaseRotatedEvent` là một dạng `SecretLeaseCreatedEvent`; trong callback có nhiều nhánh, hãy kiểm tra **rotated trước created** để tránh chạy logic thay pool hai lần. `SecretLeaseCreatedEvent.getSecrets()` có thể chứa username/password thật; không log raw event, JSON secrets hoặc stack trace có request body nhạy cảm.

### Phản ứng ở connection pool

Khi database credential đổi từ C1 sang C2, cần cập nhật datasource/pool bằng một quy trình có điểm nhất quán:

~~~text
Nhận credential C2 hợp lệ
       |
       v
Tạo / làm mới pool bằng C2
       |
       v
Kiểm tra kết nối và quyền SELECT thử
       |
       +--- FAIL ---> Giữ trạng thái lỗi, retry có giới hạn
       |
       v
Chuyển request mới sang pool C2
       |
       v
Drain/đóng pool C1 theo thời hạn an toàn
~~~

Không “thay biến password” rồi giả định mọi TCP connection hiện hữu đổi identity. Các thư viện pool có cách tái tạo connection khác nhau. Listener là tín hiệu **cấp dữ liệu mới**, còn việc bảo đảm DB không còn kết nối với user đã revoke là trách nhiệm phối hợp giữa application, pool và backend database.

## 8. Quy trình cấu hình và thao tác lab

Giả định có Vault dùng môi trường test với **database secrets engine** đã được cấu hình kết nối database và role `orders-readonly`. Lệnh dưới đây không tạo database thật; cấu hình connection, role SQL và quyền revoke nằm ở bước chuẩn bị của quản trị lab.

Tạo Vault policy tối thiểu:

~~~hcl
# orders-secrets-read.hcl
path "database/creds/orders-readonly" {
  capabilities = ["read"]
}
~~~

Đối với lease renew/revoke, cần kiểm tra quyền tương ứng trên các API `sys/leases/...`, quyền sở hữu lease và policy đang áp dụng. Không cấp wildcard `sys/*` hoặc `sudo` chỉ vì ứng dụng cần đọc credential. Đối chiếu capability thực tế ở môi trường tích hợp.

Một vài lệnh quan sát an toàn trong Vault CLI:

~~~bash
# Chạy bằng identity lab có quyền; không log phần dữ liệu password.
vault token lookup

vault read -format=json database/creds/orders-readonly \
  | jq '{lease_id, lease_duration, renewable}'

# Xem Vault role/AppRole hoặc auth backend đã cấu hình riêng;
# không chia sẻ role secret/JWT trong artifact kiểm thử.
~~~

**Cảnh báo về chi phí tạo credential:** mỗi lần `vault read database/creds/orders-readonly` thường tạo **một database user mới** và lease mới. Đừng dùng lệnh đó như một lệnh “kiểm tra vô hại” trong vòng lặp liên tục; nó có thể làm cạn tài nguyên database hoặc gây tải revoke. Hãy thử có kiểm soát trong lab cô lập.

Trong ứng dụng, thứ tự cấu hình khuyến nghị:

1. Cấu hình xác thực workload của Vault, session manager và `VaultOperations` dùng chung.
2. Khởi tạo sink thay credential, scheduler và `SecretLeaseContainer`.
3. Đăng ký `RequestedSecret` theo đúng path/mode; thêm listener trước khi fetch đầu tiên.
4. Để Spring quản lý lifecycle `start/stop/destroy`, chỉ bắt đầu nhận traffic khi secret tối thiểu đã sẵn sàng.
5. Quan sát cả login token và lease event. Nếu login lại, kiểm tra trạng thái lease/consumer, không gọi `register` lặp lại như cách làm mới.
6. Khi secret rotate, thực hiện thay pool với kiểm tra kết nối; nếu login/renew/rotate fail, chuyển sang trạng thái suy giảm và retry/backoff phù hợp.

### Khi nào cần đăng ký lại?

Đăng ký lại là thao tác **thay đổi tập secret được quản lý**, chẳng hạn ứng dụng được bật thêm một backend hoặc đổi path `database/creds/...`. Re-login của cùng workload không làm path/mode thay đổi, vì vậy việc tự `unregister` rồi `register` trên mỗi lần đăng nhập thường gây hiệu ứng không mong muốn: event lặp, credential mới không cần thiết và race với listener/pool.

Nếu ứng dụng **restart toàn process**, `SecretLeaseContainer` mới mất state trong RAM của process cũ và phải đăng ký lại các path lúc khởi động. Đây là trường hợp khác hoàn toàn với re-login khi process vẫn đang chạy.

## 9. Ma trận kiểm thử tương tác giữa re-login và secret

Kiểm thử tích hợp cần có Vault thật trong môi trường lab, backend database có thể tạo/revoke credential và quyền quan sát phù hợp. Mock `VaultTemplate` có thể kiểm tra lời gọi register nhưng không chứng minh được quan hệ giữa Vault token và lease.

| Ca | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| AUTH-01 | T1 hợp lệ, lần đầu register `ROTATE` | Tạo yêu cầu secret, nhận `SecretLeaseCreatedEvent`, consumer dùng C1. |
| AUTH-02 | T1 được **renew** thành công | Không có đăng ký trùng; lease L1 không mặc nhiên biến thành L2. |
| AUTH-03 | T1 hết TTL tối đa, có thể re-login thành T2 | Request tiếp theo dùng T2; kiểm tra trạng thái L1 và khả năng renew theo backend. |
| AUTH-04 | Re-login thất bại vì credential nguồn hết hạn | Có lỗi authentication; không cấp token giả; fetch/renew thất bại được quan sát. |
| LEASE-01 | L1 còn renewable | Container renew L1 trước expiry; `AfterSecretLeaseRenewedEvent` phù hợp. |
| LEASE-02 | L1 không renew được, mode `ROTATE`, backend cho phép | Khi phát hiện hết hạn, container yêu cầu C2/L2; sink thay pool sau kiểm tra kết nối. |
| LEASE-03 | L1 hết hạn, mode `RENEW` | Không giả định tự fetch C2; ứng dụng báo secret không dùng được. |
| LEASE-04 | Lease bị revoke sớm do token cha bị revoke | Consumer không tiếp tục dùng C1 như credential hợp lệ; lỗi và phục hồi được xử lý. |
| ACL-01 | T2 thiếu quyền `database/creds/orders-readonly` | Re-login có thể PASS nhưng fetch secret bị `403`. |
| REG-01 | Register lại cùng `RequestedSecret` | Không tạo hai đăng ký độc lập; listener được gắn muộn không có replay bắt buộc. |
| REG-02 | Restart process, cùng cấu hình workload | Container mới đăng ký path và lấy credential/lease phù hợp; startup readiness được xác minh. |
| OPS-01 | Vault timeout khi renew token hoặc lease | Có tín hiệu lỗi và metric riêng; không dùng retry vô hạn hoặc log secret. |

Khi cần **ép re-login**, hãy dùng token và database của lab với TTL ngắn hoặc thu hồi token thử nghiệm bằng quyền quản trị. Quan sát lần lượt T1 → T2, trạng thái L1, sự kiện C2/L2 và việc đổi pool, rồi kiểm tra cleanup khi shutdown. Thu hồi token trong production có thể lập tức làm mất credential đang phục vụ traffic.

Kiểm tra hành vi chứ không chỉ đếm sự kiện: một `SecretLeaseRotatedEvent` không bảo đảm mọi request đã chuyển sang pool mới; cần một thao tác database thật với connection mới. Khi kiểm tra `403`, phân biệt lỗi quyền với lỗi DNS/timeout, Vault seal hoặc secret path không tồn tại.

## 10. Lỗi thường gặp khi kết hợp hai lifecycle

| Hiện tượng | Giải thích khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Login lại thành công nhưng DB vẫn trả lỗi xác thực | Pool vẫn dùng C1 đã bị revoke, hoặc sink chưa áp dụng C2. | Đọc lease events, thay pool/connection và kiểm tra C2 trước khi chuyển. |
| Secret registration vẫn còn nhưng `renew` bị `403` | T2 không có quyền/quan hệ lease phù hợp hoặc L1 đã không còn hợp lệ. | So sánh token policies, trạng thái L1 và auth event. |
| Đăng ký cùng path nhiều lần không nhận created event mới | Registry xem `RequestedSecret` trùng là một; listener không replay dữ liệu đầu. | Thiết kế init listener trước start; không dùng re-register để refresh. |
| Mỗi lần re-login lại sinh DB user mới | App tự request lại secret khi nhận auth event thay vì chờ lease rotation. | Tách lifecycle token khỏi lifecycle lease. |
| App không hoạt động sau thời gian dài | Login credential nguồn (JWT, SecretID) đã hết hạn; renew token đến max TTL. | Làm mới credential nguồn, quan sát re-login và TTL. |
| Không thấy `SecretLeaseExpiredEvent` đúng thời điểm | Vault không push event; scheduler/connection có thể chậm. | Dùng TTL margin và readiness/error handling, không dựa vào đồng hồ event tuyệt đối. |
| Khi stop, credential còn dùng được | `stop()` chỉ dừng hoạt động theo dõi; khác `destroy()` và revoke lease. | Quản lý shutdown với container lifecycle và quyền revoke phù hợp. |
| Re-login được nhưng không gọi Transit/PKI | Token T2 có ACL khác T1 hoặc đường dẫn policy sai. | Đọc `token_policies` của auth role và capability endpoint. |

Với `SecretLeaseContainer`, **`stop()`** dừng gia hạn/rotation và phát sự kiện nhưng không tự làm lease đang có hết hạn ngay. **`destroy()`** dọn container và thực hiện revoke các lease thích hợp; khả năng revoke thực tế phụ thuộc quyền và trạng thái của Vault. Không dùng shutdown ứng dụng như cơ chế duy nhất để đảm bảo credential đã bị hủy ở mọi hệ thống.

Trong hệ thống nhiều replica, mỗi instance có thể được cấp lease/credential riêng. Khi một instance re-login hoặc shutdown, không được giả định tất cả instance khác có cùng trạng thái. Theo dõi theo instance, role, auth mount và secret path; tránh dùng username/password của một replica cho mọi replica nếu thiết kế cần cô lập.

## 11. Giám sát, bảo mật và câu hỏi tổng kết

### Những tín hiệu nên thu thập

- **Auth:** số login, renew, re-login, tỷ lệ thất bại và thời gian từ lúc token gần hết hạn đến lần xác thực kế tiếp.
- **Lease:** số `RequestedSecret` đang quản lý, số renew thành công, rotate, expired, revoke và lỗi theo secret path.
- **Consumer:** trạng thái database pool, số lần credential mới được cài đặt thành công, thời gian phục hồi và số lỗi kết nối do credential đã hết hạn.
- **Vận hành:** `403` phân biệt ở endpoint auth, `database/creds`, `sys/leases/renew` và `sys/leases/revoke`; timeout/TLS riêng biệt.

Khi ghi log, không đưa **Vault token, JWT, AppRole SecretID, password database, nội dung `getSecrets()`** hoặc HTTP response chứa credential vào log. Dùng định danh path, loại event, thời gian, instance ID và request ID phù hợp. Audit device của Vault cần được bật và bảo vệ; chính sách retry/backoff nên tránh tạo bão login hoặc phát sinh quá nhiều database user khi Vault có sự cố.

### Checklist trước production

- [ ] `VaultOperations` dùng đúng session manager có renew/re-login theo loại auth workload.
- [ ] `SecretLeaseContainer` đăng ký đúng path/mode và listener được gắn trước fetch đầu tiên.
- [ ] `ROTATE` được chọn khi cần credential mới sau khi lease cũ không còn hiệu lực.
- [ ] AppRole/JWT/Kubernetes credential nguồn có chiến lược cấp lại trước khi cần re-login.
- [ ] Có cách cập nhật datasource/pool khi nhận `SecretLeaseCreatedEvent` hoặc `SecretLeaseRotatedEvent`.
- [ ] Có phương án khi parent token bị revoke, khi lease renew fail và khi Vault unavailable.
- [ ] Policy cấp đúng quyền đọc dynamic secret và các lease API cần thiết; đã kiểm tra khả năng 403 thực tế.
- [ ] Shutdown/stop/destroy, lease revoke và restart process đã được kiểm thử trên lab.
- [ ] Không lộ credential qua log, metrics, exceptions hay file test.

### Câu hỏi tự đánh giá

1. Sự khác nhau giữa `LifecycleAwareSessionManager` và `SecretLeaseContainer` là gì? Vì sao cần cả hai với dynamic secret?
2. Nếu token T1 được re-login thành T2, có thể kết luận lease L1 vẫn còn hợp lệ hay credential C2 đã được cấp không?
3. Khi nào nên chọn `RequestedSecret.renewable(...)` thay vì `RequestedSecret.rotating(...)`?
4. Vì sao gọi `register` cho cùng `RequestedSecret` nhiều lần không thay thế được quy trình rotate?
5. Khi `SecretLeaseRotatedEvent` xuất hiện, phải làm gì để database pool thật sự dùng credential mới?
6. Vì sao cần kiểm thử trường hợp token T2 có quyền đăng nhập nhưng bị `403` khi truy cập `database/creds/orders-readonly`?
7. Khác biệt giữa `stop()` và `destroy()` của `SecretLeaseContainer` liên quan đến lease như thế nào?
8. Nếu một token đã renew thành công nhưng SecretID để re-login đã hết hạn, ứng dụng có thể gặp sự cố gì khi đạt max TTL?

## Tài liệu tham khảo chính thức

- [Spring Vault — Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — Authentication Methods và Token Lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault API — RequestedSecret](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/domain/RequestedSecret.html)
- [Spring Vault API — LifecycleAwareSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [Spring Cloud Vault — Lease Lifecycle Management](https://docs.spring.io/spring-cloud-vault/reference/advanced-topics.html)

Điểm cần nhớ: **đăng nhập lại thay thế danh tính token dùng cho các request, còn đăng ký secret thể hiện những đường dẫn và lease mà ứng dụng muốn quản lý.** Việc renew, rotate hoặc revoke credential phụ thuộc lease, quyền Vault và trạng thái backend; ứng dụng phải xử lý các sự kiện đó để bảo đảm consumer luôn sử dụng credential hợp lệ.
