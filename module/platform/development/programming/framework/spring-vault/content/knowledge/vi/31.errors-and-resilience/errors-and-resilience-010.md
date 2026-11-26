# Ứng xử khi secret đang dùng sắp hết hạn trong lúc mất kết nối

## 1. Bối cảnh: Vault mất kết nối đúng lúc chuẩn bị gia hạn

Một ứng dụng Java/Spring Boot dùng Spring Vault để nhận username/password động từ HashiCorp Vault Database secrets engine, sau đó gắn credential vào connection pool. Vault trả một lease có TTL 10 phút. Đến phút thứ 7, đường mạng tới Vault bị gián đoạn; việc renew thất bại. Trong khi đó các kết nối DB đang mở có thể vẫn chạy, còn kết nối mới có thể thành công hoặc thất bại tùy trạng thái credential và cách database xử lý phiên.

Tình huống này đòi hỏi quyết định rõ ràng: **ứng dụng còn được phép bắt đầu tác vụ mới với secret hiện tại bao lâu và sẽ phục hồi như thế nào nếu không thể xác nhận secret còn hợp lệ?** Retry liên tục không trả lời được câu hỏi đó.

Trong module **SPRING_VAULT**, `VaultTemplate`/`VaultOperations` cung cấp giao tiếp tới Vault; xác thực workload, ACL policy, token lifecycle và lease lifecycle quyết định việc truy cập. KV secrets, Transit encryption và PKI có vòng đời riêng, vì vậy không dùng cùng chính sách lưu cache cho mọi loại secret.

Mục tiêu của bài:

1. Phân biệt Vault token TTL, dynamic secret lease TTL, KV secret và thời hạn chứng thư X.509.
2. Tính thời điểm cần renew, ngưỡng an toàn để từ chối tác vụ mới và ngân sách thời gian của một tác vụ.
3. Thiết kế fail closed, graceful degradation, retry/backoff, readiness và phục hồi sau outage.
4. Áp dụng `LifecycleAwareSessionManager`, `SecretLeaseContainer` và các sự kiện renewal/expiry của Spring Vault.
5. Kiểm thử trường hợp secret sát hạn khi Vault ngắt kết nối mà không làm lộ credential.

**Nguyên tắc:** Mất kết nối không đóng băng hoặc kéo dài TTL. Một credential đã hết hạn hoặc bị thu hồi không được coi là còn hợp lệ chỉ vì bản sao còn trong JVM hoặc backend vẫn chấp nhận một số kết nối cũ.

## 2. “Hết hạn” khác nhau theo từng loại secret

| Dữ liệu | Thứ có thời hạn | Gia hạn hay thay thế? | Khi không kết nối được Vault |
| --- | --- | --- | --- |
| Dynamic DB credential | Lease TTL, có thể bị revoke sớm. | Renew nếu renewable và backend cho phép; nếu không thì cấp credential mới. | Không thể xác nhận renewal; giới hạn tác vụ theo thời gian còn lại, sau đó ngừng dùng. |
| Dynamic cloud credential | Lease Vault và có thể có expiration riêng ở cloud. | Tùy backend, quyền và cơ chế cấp. | Xét cả thời hạn phía cloud, không dùng chỉ số Vault làm bảo đảm tuyệt đối. |
| Vault client token | Token TTL, max TTL/period và trạng thái revoke. | Renew hoặc re-login theo auth method và session manager. | Không renew/re-login; request Vault có thể thất bại, các lease phụ thuộc token cũng có thể bị revoke. |
| KV v1/v2 static secret | Secret lưu trong KV, thông thường không có dynamic lease theo lần đọc. | Ghi version mới hoặc thay giá trị theo chính sách. | Có thể dùng cache chỉ nếu chính sách cho phép; không biết giá trị đã bị đổi/revoke ngoài Vault. |
| Transit key | Khóa được Vault quản lý; các operation thực thi trên Vault. | Rotate key version theo vận hành, không phải renew lease dữ liệu. | Không thể gọi phép toán encrypt/decrypt mới nếu Vault không truy cập được. |
| PKI leaf certificate | `NotBefore`/`NotAfter` và trạng thái revoke, tin cậy CA. | Phát hành chứng thư mới hoặc ký CSR mới. | Chứng thư cũ có hiệu lực X.509 tới hạn, nhưng không thể gia hạn ngày hết hạn bằng renew token. |
| AppRole SecretID | `secret_id_ttl`, số lần dùng, CIDR, trạng thái revoke. | Cấp SecretID mới theo provisioning khi cần. | Không được bypass auth; bootstrap có thể phải chờ cơ chế cấp mới. |

HashiCorp Vault cấp lease cho dynamic secret và service token; KV lưu dữ liệu tĩnh **không cấp dynamic lease**, dù một số API có thể hiển thị trường `lease_duration`. Một lease đang còn TTL là thông tin hữu ích nhưng **không loại trừ khả năng bị thu hồi sớm** do người vận hành, policy hoặc token liên quan bị revoke/hết hạn.

### 2.1. Có thể có nhiều “đồng hồ” cùng lúc

Ví dụ 10:00 ứng dụng nhận DB credential có lease TTL 10 phút và token Vault còn 8 phút. Token hết hạn có thể làm lease được tạo dưới token đó bị Vault thu hồi; vì vậy không suy đoán credential còn dùng an toàn đến 10:10 chỉ từ lease TTL.

Certificate PKI khác: leaf certificate đã ký có `NotAfter` cụ thể, không kéo dài chỉ nhờ Vault token hoặc lease được renew. Một peer có thể tạm chấp nhận certificate trước `NotAfter` nhưng còn phụ thuộc CA, hostname, EKU và kiểm tra thu hồi. Nếu không truy cập Vault để cấp mới, mTLS client phải có phương án đã chuẩn bị trước hạn.

## 3. Dòng thời gian khi renew thất bại

Ví dụ dynamic DB lease TTL 600 giây:

~~~text
10:00  Nhận credential A, lease-A TTL 10 phút
  │
10:06  Bắt đầu cửa sổ renew/chuẩn bị rotation
  │
10:07  Mạng tới Vault bị mất; renew chưa có phản hồi xác nhận
  │      Retry có giới hạn + alert
  │
10:09  Còn khoảng 60 giây; ngừng nhận tác vụ DB kéo dài
  │
10:10  Mốc lease hết hạn nếu chưa renew
  │      Chặn mọi tác vụ mới phụ thuộc credential A
  │
10:11  Vault trở lại
         Re-auth/rotate hoặc renew nếu còn hợp lệ theo Vault
         Tạo pool mới, xác minh backend, khôi phục readiness
~~~

Các mốc renewal chỉ để minh họa; Spring Vault có lịch riêng dựa trên TTL, expiry threshold và scheduler clock. Mục tiêu vận hành là **renew hoặc cấp credential thay thế đủ sớm** để còn thời gian mạng gián đoạn, thử kết nối và chuyển pool/SDK.

Khi lease hết hạn, Vault có thể tự thu hồi secret. Nếu Vault đang gặp sự cố hoặc backend chưa thực hiện revoke, credential có thể chưa bị vô hiệu hóa ngay; khả năng đăng nhập tạm thời **không có nghĩa ứng dụng được phép sử dụng vượt hạn**.

### 3.1. Thời gian còn lại và ngân sách tác vụ

Định nghĩa:

- `T_exp`: thời điểm hết hạn **ước lượng từ phản hồi cuối cùng đã xác nhận**.
- `W`: cửa sổ ưu tiên renew/rotate trước hạn.
- `M`: safety margin tính clock skew, scheduling jitter, network latency và sai số.
- `B`: operation budget, thời gian tối đa một tác vụ mới cần giữ credential.

Chỉ tiếp nhận một tác vụ khi:

~~~text
now + B + M < T_exp
~~~

Nếu `now + W >= T_exp`, nên chuyển trạng thái **RENEW_SOON**. Nếu `now + B + M >= T_exp`, chuyển **REJECT_NEW_WORK** cho hoạt động phụ thuộc secret. Các ngưỡng này là policy của ứng dụng, không phải quyền được Vault cấp để tiếp tục dùng sau hạn.

Yêu cầu `vault lease renew -increment=...` chỉ đưa ra TTL mong muốn; Vault/backend có thể giới hạn hoặc không chấp nhận. **Chỉ cập nhật deadline sau khi nhận phản hồi renew thành công và TTL mới được xác nhận.** Nếu client timeout, không tự cộng increment, kể cả khi server có thể đã xử lý request ở phía sau.

## 4. Quyết định fail closed và graceful degradation

| Ngữ cảnh | Có thể tiếp tục? | Giới hạn |
| --- | --- | --- |
| Endpoint chỉ trả dữ liệu công khai từ cache | Có thể, nếu không cần gọi Vault/DB và cache hợp lệ. | Không để cache công khai che lỗi truy cập dữ liệu riêng tư. |
| KV chứa cấu hình ít nhạy cảm | Có thể dùng snapshot gần nhất theo chính sách độ cũ. | KV không có cơ chế xác nhận phiên bản mới trong outage. |
| API key vendor trong KV | Có thể dùng có giới hạn khi doanh nghiệp chấp thuận. | Vendor có thể đã revoke key; theo dõi 401/403 và tuổi cache. |
| DB credential lease còn lớn hơn `B + M` | Có thể phục vụ tác vụ có budget phù hợp. | Vẫn phải xử lý revoke sớm và lỗi xác thực backend. |
| DB credential sát hạn hoặc đã hết hạn | Không bắt đầu tác vụ mới dùng credential đó. | Không kéo dài thời gian bằng local grace tùy tiện. |
| Token Vault hết hạn | Không gọi Vault bằng token đó. | Chờ re-login bằng workload identity sau khi kết nối phục hồi. |
| PKI certificate sát `NotAfter` | Không mở kết nối TLS mới nếu không đủ thời gian an toàn. | Cấp lại và nạp certificate mới trước khi nối traffic. |
| Transit encrypt/decrypt phải thực hiện trên Vault | Không thể xử lý offline theo cùng ranh giới khóa. | Không ghi plaintext nhạy cảm chưa mã hóa xuống hàng đợi không được phép. |

**Fail closed** phù hợp với thao tác cần token/secret còn hiệu lực và chính sách bảo mật nghiêm ngặt. **Graceful degradation** nghĩa là tiếp tục phần chức năng không cần Vault, giảm tải hoặc tạm từ chối phần phụ thuộc credential. Không nên coi “degraded” là lý do cấp quyền quá rộng, giữ token hết hạn hay tắt TLS verification.

Ví dụ `GET /catalog` phục vụ cache công khai có thể vẫn chạy, trong khi `POST /orders` phải ngừng nhận nếu DB credential không còn đủ thời gian an toàn, và `POST /payments` yêu cầu Transit có thể trả 503 tạm thời khi Vault mất kết nối.

## 5. Kiến trúc Credential Manager trong ứng dụng Spring

~~~mermaid
flowchart TD
 A["Workload authentication"] --> B["Spring Vault SessionManager"]
 B --> C["Vault server"]
 C --> D["Lease / PKI / KV credential source"]
 D --> E["Credential generation + expiry metadata"]
 E --> F{"Validity gate"}
 F -->|Đủ thời gian| G["DB pool / SDK / TLS client"]
 F -->|Sát hạn| H["Giảm tải + yêu cầu refresh"]
 F -->|Không đủ| I["Dừng tác vụ phụ thuộc credential"]
 J["Scheduler + lease events"] --> D
 K["Readiness và metrics"] --> F
~~~

Các phần phải phối hợp:

1. **Credential source** xin/cập nhật secret từ Vault, nhận lease metadata hoặc certificate expiration.
2. **Validity gate** xét thời hạn đã xác nhận cùng operation budget và safety margin.
3. **Consumer adapter** đưa credential vào connection pool, SDK hoặc `SSLContext` thực tế.
4. **Rotation coordinator** cấp secret mới, kiểm tra và chuyển traffic sang consumer mới.
5. **Readiness/monitoring** cho biết phần ứng dụng nào có thể nhận request, không phơi lộ secret.

Một credential mới đã được tải từ Vault **chưa chắc** đã được client sử dụng. Ví dụ HikariCP có thể còn các connection cũ; SDK giữ key lúc constructor; TLS client giữ `SSLContext` cũ. Trạng thái healthy chỉ nên được công bố khi **credential generation gắn với consumer đang hoạt động** đã được kiểm tra.

### 5.1. Lưu metadata, không log secret

| Metadata | Mục đích |
| --- | --- |
| `lastSuccessfulRenewAt` | Phân biệt lần renew được xác nhận và lần chỉ thử gửi request. |
| `estimatedExpiry` | Mốc hết hạn cục bộ dùng để từ chối sớm. |
| `renewable` | Có được phép thử renew hay cần rotation. |
| `credentialGeneration` | ID nội bộ không nhạy cảm để theo dõi bản đang dùng. |
| `activeConsumerGeneration` | Bản mà DB pool/SDK/TLS thực tế đang phục vụ. |
| `lastErrorCategory` | Network, 403, invalid lease, timeout, backend auth failure. |
| `refreshInProgress` | Giới hạn nhiều thread cùng tạo credential khi Vault hồi phục. |

Có thể dùng đồng hồ monotonic để đo thời gian trôi qua trong cùng tiến trình; nếu dùng `Clock.instant()` cần safety margin và xử lý clock skew/NTP step. Dù đồng hồ chính xác, local deadline cũng không thể phát hiện mọi trường hợp Vault revoke sớm.

## 6. Mã Java: cổng quyết định theo TTL đã xác nhận

Ví dụ này giữ **thời hạn** mà không giữ plaintext credential. Sử dụng `Clock` injectable để dễ test ở ranh giới thời gian.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class CredentialValidityGate {

    public enum Decision {
        AVAILABLE, RENEW_SOON, REJECT_NEW_WORK
    }

    private record Snapshot(Instant estimatedExpiry, String generation) {}

    private final Clock clock;
    private final Duration renewalWindow;
    private final Duration safetyMargin;
    private final AtomicReference<Snapshot> latest = new AtomicReference<>();

    public CredentialValidityGate(
            Clock clock, Duration renewalWindow, Duration safetyMargin) {
        this.clock = Objects.requireNonNull(clock);
        this.renewalWindow = Objects.requireNonNull(renewalWindow);
        this.safetyMargin = Objects.requireNonNull(safetyMargin);
        if (renewalWindow.isNegative() || safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Durations must be >= 0");
        }
    }

    /** Gọi sau response create/renew thành công từ Vault. */
    public void confirmFromVault(Duration ttl, String generation) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            latest.set(null);
            return;
        }
        latest.set(new Snapshot(clock.instant().plus(ttl), generation));
    }

    public Decision decide(Duration operationBudget) {
        if (operationBudget.isNegative()) {
            throw new IllegalArgumentException("Budget cannot be negative");
        }
        Snapshot snapshot = latest.get();
        if (snapshot == null) {
            return Decision.REJECT_NEW_WORK;
        }

        Instant now = clock.instant();
        Instant usableUntil =
                snapshot.estimatedExpiry().minus(safetyMargin);

        if (!now.plus(operationBudget).isBefore(usableUntil)) {
            return Decision.REJECT_NEW_WORK;
        }

        if (!now.plus(renewalWindow).isBefore(usableUntil)) {
            return Decision.RENEW_SOON;
        }

        return Decision.AVAILABLE;
    }

    public void invalidateAfterConfirmedRevocation() {
        latest.set(null);
    }
}
~~~

Cách sử dụng minh họa:

~~~java
CredentialValidityGate gate = new CredentialValidityGate(
        Clock.systemUTC(),
        Duration.ofMinutes(2),
        Duration.ofSeconds(30));

// Chỉ khi Vault đã xác nhận tạo/renew lease TTL 600 giây:
gate.confirmFromVault(Duration.ofSeconds(600), "db-gen-7");

var decision = gate.decide(Duration.ofSeconds(20));

if (decision == CredentialValidityGate.Decision.REJECT_NEW_WORK) {
    throw new IllegalStateException(
            "Không đủ thời gian an toàn cho request cần DB");
}

if (decision == CredentialValidityGate.Decision.RENEW_SOON) {
    // Kích hoạt refresh ở background qua coordinator,
    // không gọi Vault blocking trên event loop WebFlux.
}

// Tiếp tục bằng DB pool thực sự gắn với db-gen-7.
~~~

**Giới hạn của ví dụ:** Gate bảo đảm quyết định *thận trọng dựa trên TTL đã quan sát*, không chứng minh Vault/DB chưa revoke credential. Backend có thể từ chối bất kỳ lúc nào. Vì vậy vẫn phải xử lý lỗi permission/expired từ đích. Khi renew thất bại hoặc timeout, **không gọi `confirmFromVault`**. Khi chuyển credential A sang B, chỉ xác nhận generation mới phục vụ traffic sau khi pool/client B sẵn sàng và đã được kiểm tra.

Nếu dùng cache hoặc deadline lưu qua lần restart, không giữ nguyên tính toán dựa trên clock của tiến trình cũ; phải dựng lại trạng thái từ thông tin đáng tin cậy và giới hạn startup/readiness.

## 7. Spring Vault quản lý token và lease bằng gì?

Các thành phần Spring Vault có trách nhiệm khác nhau:

- `LifecycleAwareSessionManager` quản lý vòng đời token đăng nhập, có thể tự renew và re-login theo auth method, renewability, TTL, max TTL và cấu hình thực tế.
- `SimpleSessionManager` là cơ chế session cơ bản, không tự renew/revoke token như lifecycle-aware manager.
- `SecretLeaseContainer` quản lý secret có lease, renew lease hoặc rotate secret theo đăng ký và phát sự kiện cho listener.
- `SessionLeaseContainer` phối hợp token session và lease theo một số cấu hình.
- Spring Cloud Vault có thể tự cấu hình các thành phần này cho property sources/secret lifecycle; cần xem version đang dùng và tránh quản lý trùng.

**Token và secret lease không phải cùng đối tượng.** Token hết hạn hoặc bị revoke có thể khiến các secret lease cấp dưới token bị revoke theo. Trong outage, không renew được token cũng có thể phá vỡ việc renew secret, ngay cả khi secret lease vẫn còn TTL.

Một `LoginToken` có thể chứa thông tin TTL/renewability, còn `TokenAuthentication` sử dụng token được cung cấp từ bên ngoài có cách quản lý khác. Không giải quyết rủi ro bằng root token lâu hạn, role wildcard hoặc tắt kiểm tra TTL.

### 7.1. Sự kiện lease không phải thông báo push từ Vault

`SecretLeaseContainer` lập lịch renew/rotation theo thời gian; Vault không gửi một event trực tiếp tới tất cả Java process khi lease vừa hết hạn. Scheduler có thể bị trễ vì JVM pause, clock skew, CPU hoặc mạng. Vì vậy `SecretLeaseExpiredEvent` có thể đến **sau** thời điểm hết hạn thực ở Vault.

Kết hợp lease events với validity gate và lỗi xác thực backend. Không dựa duy nhất vào “chưa nhận event expired” để cho phép request mới.

## 8. SecretLeaseContainer: lắng nghe renew, rotation và lỗi

Ví dụ rút gọn theo API Spring Vault, nhằm mô tả event handling:

~~~java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.LeaseListenerAdapter;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;

public class LeaseCoordinatorExample {

    public SecretLeaseContainer configure(
            VaultOperations vault, TaskScheduler scheduler) {

        SecretLeaseContainer container =
                new SecretLeaseContainer(vault, scheduler);

        RequestedSecret requested =
                container.requestRotatingSecret(
                        "database/creds/orders-readonly");

        LeaseListenerAdapter listener = new LeaseListenerAdapter() {
            @Override
            public void onLeaseEvent(SecretLeaseEvent event) {
                if (!requested.equals(event.getSource())) {
                    return;
                }
                if (event instanceof SecretLeaseCreatedEvent) {
                    // Có secret mới: tạo pool mới, test, rồi chuyển traffic.
                }
                if (event instanceof SecretLeaseExpiredEvent) {
                    // Từ chối tác vụ mới phụ thuộc credential đã hết hạn.
                }
            }

            @Override
            public void onLeaseError(
                    SecretLeaseEvent event, Exception error) {
                // Báo degraded/metric; không giả định renewal thành công.
                // Không log password hoặc Vault token.
            }
        };

        container.addLeaseListener(listener);
        container.addErrorListener(listener);

        container.afterPropertiesSet();
        container.start();
        return container;
    }
}
~~~

Đây là ví dụ **không đầy đủ về quản lý bean**, chưa cập nhật DB pool, chưa xử lý cleanup. Production nên dùng lifecycle của container do Spring/Cloud Vault quản lý, đóng/destroy đúng quy trình và không tạo hai container cùng xin/rotate một secret path không chủ đích. Đăng ký listener **trước** khi container bắt đầu, nếu không có thể bỏ lỡ sự kiện đầu tiên.

| Sự kiện | Ý nghĩa |
| --- | --- |
| `SecretLeaseCreatedEvent` | Có secret/lease được tạo, cần chuẩn bị consumer. |
| `AfterSecretLeaseRenewedEvent` | Vault xác nhận renew; cập nhật deadline theo TTL mới. |
| `SecretLeaseRotatedEvent` | Có credential mới; chuyển consumer generation. |
| `SecretLeaseExpiredEvent` | Ứng dụng phát hiện lease hết hạn; dừng dùng/cleanup. |
| `SecretLeaseErrorEvent`, `LeaseErrorListener` | Vault trả lỗi hoặc I/O thất bại; phân loại, alert, không cộng TTL local. |
| `SecretNotFoundEvent` | Secret path không trả kết quả, cần kiểm tra role/mount/policy. |

`SecretLeaseContainer` có expiry threshold và minimum renewal time; lịch cụ thể phụ thuộc phiên bản. Chúng chỉ điều phối **khi gọi Vault**, không thay thế ngân sách an toàn của tác vụ.

### 8.1. Retain-on-error không đồng nghĩa “vẫn hợp lệ”

Spring Cloud Vault có các chiến lược xử lý lỗi renewal như `DropOnError`, `RetainOnError` và `RetainOnIoError` trong những phiên bản có hỗ trợ. Chế độ retain có thể giữ secret đã tải trong property source khi I/O lỗi để ứng dụng không mất property ngay lập tức.

**Giữ giá trị trong property source không làm lease được Vault gia hạn.** Nếu credential động đã hết TTL hoặc backend từ chối, vẫn phải dừng sử dụng cho thao tác mới. Chọn strategy theo đặc tính secret và policy availability, đồng thời áp validity gate/readiness riêng.

## 9. Renew và rotate là hai hành vi khác nhau

**Renew:** Vault cho phép kéo dài lease của cùng credential. Phải kiểm tra `renewable` và phản hồi TTL thực tế; không suy increment chắc chắn được chấp nhận.

**Rotate:** Xin credential mới từ role, có thể tạo lease mới. Phải cập nhật consumer thực sự thay vì chỉ thay bản cache.

~~~text
Pool-A đang dùng credential-A, lease-A còn thời gian
    │
    ├── renew(A) thành công
    │       → tiếp tục Pool-A, cập nhật T_exp theo TTL mới
    │
    └── renew không thể / cần credential mới
            → Vault kết nối lại và cấp credential-B
            → tạo Pool-B, kiểm tra kết nối bằng B
            → atomic switch traffic mới sang Pool-B
            → drain Pool-A, revoke/cleanup lease-A
~~~

Với HikariCP hoặc pool khác, thay `username`/`password` trong config chưa chắc cập nhật connection đang mở. Có thể phải tạo pool mới hoặc thực hiện cơ chế soft eviction/refresh được thư viện hỗ trợ, kiểm thử dưới tải và khi transaction đang chạy.

Backend có thể cho session cũ tiếp tục dù credential không thể tạo kết nối mới. Không sử dụng sự khác biệt đó như “cách lách” lease expiry; hạn chế tuổi connection và đóng resource theo quy trình.

Khi Vault hồi phục **sau khi lease đã hết hạn**, xin credential mới và xác nhận backend kết nối được trước khi mở traffic. Không gán TTL mới cho credential A chỉ vì đã có đường mạng trở lại.

## 10. Retry có giới hạn và circuit breaker

| Loại lỗi | Xử lý đề xuất |
| --- | --- |
| Timeout, network reset, DNS tạm thời | Retry exponential backoff + jitter, có deadline và tổng số lần giới hạn. |
| Vault 429/quota | Tôn trọng tín hiệu hạn chế tải/`Retry-After` khi có; không tạo bão request. |
| Vault 5xx/HA endpoint tạm không phục vụ | Retry hoặc chuyển endpoint theo cấu hình Vault HA đã được kiểm chứng. |
| Vault 403 | Kiểm token/role/policy/namespace; không spam cùng request bị từ chối. |
| Vault 400 invalid/nonrenewable lease | Ngừng renew vô ích; chọn rotation/re-auth theo quy trình. |
| Vault 404 sai mount/role/path | Sửa provisioning/config, không xem là outage ngẫu nhiên. |
| DB báo login/password invalid | Không tin TTL local; degrade và điều tra revoked/rotation. |
| Tạo credential thành công nhưng thay pool thất bại | Giữ trạng thái degraded; không báo đã chuyển sang generation mới. |

Một yêu cầu tạo dynamic credential **có side effect**: nếu timeout, server có thể đã tạo credential/lease dù client không nhận response. Retry có thể tạo thêm secret. Cần giới hạn đồng thời, dọn lease khi biết được ID và tránh việc nhiều replica cùng tạo hàng loạt credential lúc Vault hồi phục.

Circuit breaker giúp tránh nghẽn thread pool, nhưng không thay validity gate. Một breaker đã mở không đồng nghĩa mọi cached secret đã hết hạn; ngược lại, breaker đóng lại cũng không làm secret cũ tự hợp lệ.

### 10.1. Các tác vụ đang chạy

Khi gần expiry, hạn chế **tác vụ mới** sao cho còn thời gian hoàn tất trong `B + M`. Với tác vụ đang chạy, đặt timeout theo policy và xử lý ngay khi backend báo secret invalid. Đừng retry vô hạn giao dịch có side effect; với các endpoint tạo đơn hàng/thanh toán, cần idempotency mechanism để xử lý request có thể đã hoàn thành ở backend nhưng client timeout.

## 11. Readiness, liveness và giám sát

- **Liveness:** JVM/process còn hoạt động và có thể tự phục hồi không? Không restart toàn bộ pod liên tục chỉ vì Vault tạm unreachable.
- **Readiness:** phần chức năng cần credential có sẵn sàng nhận request và có đủ thời gian an toàn không?
- **Dependency status:** Vault connection/auth/renewal có đang healthy hay degraded?

Ví dụ một quy tắc readiness cho service chỉ hoạt động khi DB sẵn sàng:

~~~text
ready =
  credential_present
  AND enough_confirmed_time_for_expected_operation
  AND active_pool_generation_matches_confirmed_credential
  AND backend_validation_succeeds
~~~

Ứng dụng đa chức năng có thể vẫn phục vụ endpoint không phụ thuộc DB khi Vault mất mạng, nhưng không đánh dấu readiness thành healthy chỉ vì actuator trả 200 trong khi mọi request nghiệp vụ đều cần DB và đang thất bại.

Các metric hữu ích:

| Metric | Giải thích |
| --- | --- |
| `secret_remaining_seconds` | Số giây còn tới expiry ước lượng theo loại secret. |
| `vault_renew_success_age_seconds` | Bao lâu chưa có phản hồi renew thành công. |
| `vault_renew_failures_total` | Lỗi theo nhóm: I/O, 403, invalid lease, timeout, quota. |
| `credential_generation_mismatch` | Provider cập nhật nhưng pool/SDK chưa đổi. |
| `db_new_connection_auth_failures` | DB từ chối credential mới/cũ. |
| `vault_reauth_failures` | Workload không lấy được Vault token mới. |
| `certificate_seconds_until_not_after` | Thời gian còn lại của certificate TLS đang dùng. |
| `readiness_degraded_duration_seconds` | Thời gian ứng dụng hạn chế tính năng. |

Không đưa token, password, `lease_id` đầy đủ, key, CSR/private key, plaintext hoặc ciphertext nhạy cảm vào metric label, logs, traces và exception. Chỉ ghi loại lỗi, endpoint template được phép quan sát, latency và correlation ID.

## 12. Runbook xử lý outage khi secret sát hạn

~~~text
Alert: renew thất bại / secret remaining < renewal window
  │
  ├── 1. Xác minh lỗi network/TLS/HA hay lỗi ACL/token.
  ├── 2. Xác định loại secret, T_exp, token TTL, khả năng revoked sớm.
  ├── 3. So sánh now + operationBudget + safetyMargin với T_exp.
  ├── 4. Giảm tải hoặc dừng request mới cần credential khi không đủ hạn.
  ├── 5. Giữ liveness, cập nhật readiness/degraded và alert đúng mức.
  ├── 6. Khi Vault hồi phục: re-auth/renew nếu hợp lệ hoặc rotate.
  ├── 7. Thay pool/SDK/SSLContext, kiểm chứng backend hoạt động thật.
  └── 8. Khôi phục traffic, dọn secret cũ và hậu kiểm sự cố.
~~~

Không tắt TLS validation, đặt token root vào container, bỏ kiểm tra lease, tăng wildcard policy, dùng secret hết hạn qua “grace period” hoặc ghi secret ra log. Nếu cần mở rộng TTL để phù hợp tác vụ dài, đó là quyết định vận hành/an toàn được phê duyệt, áp dụng từ trước thay vì thay đổi tùy tiện trong sự cố.

## 13. Kiểm thử tích hợp và test thời gian

Có thể dùng Vault test riêng, database test và một network proxy như Toxiproxy để chặn kết nối **ứng dụng → Vault**. Không làm hết hạn credential trên hệ thống production nhằm thử nghiệm.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Vault bình thường, lease renewable | Renew trước hạn; nhận TTL mới, cập nhật deadline. |
| Vault mất kết nối khi lease còn xa hạn | Retry giới hạn; tác vụ đủ an toàn vẫn có thể chạy theo policy. |
| Vault mất kết nối khi còn ít hơn `B + M` | Từ chối request mới dùng credential, readiness degraded. |
| Renew request timeout | Không tự cộng thời hạn lease local. |
| Token Vault hết hạn trong outage | Không giả định credential vẫn hợp lệ, re-login chỉ khi kết nối được khôi phục. |
| Vault hồi phục trước expiry | Kiểm chứng renew còn được phép, cập nhật TTL sau response thành công. |
| Vault hồi phục sau expiry | Lấy credential mới, thay pool, không dùng secret đã hết hạn. |
| Credential bị revoke sớm | Backend từ chối dù local còn TTL; invalidate/degrade. |
| KV static secret trong outage | Chỉ sử dụng cache theo quy tắc riêng, không renew như dynamic lease. |
| PKI certificate sắp hết hạn | Không mở TLS connection mới bằng certificate hết hạn; cấp mới và reload. |
| Nhiều replica cùng refresh | Backoff/jitter và hạn mức, tránh bão request. |
| Consumer chưa đổi sang credential mới | Readiness không healthy chỉ vì provider đã fetch thành công. |

### 13.1. Unit test validity gate với Clock

Không dùng `Thread.sleep` kéo dài để test ngưỡng TTL. Inject `Clock` có thể điều khiển thời gian; một ví dụ cho trạng thái ban đầu:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T10:00:00Z"),
        ZoneOffset.UTC);

CredentialValidityGate gate = new CredentialValidityGate(
        testClock,
        Duration.ofMinutes(2),
        Duration.ofSeconds(30));

gate.confirmFromVault(Duration.ofMinutes(10), "db-gen-1");

assertEquals(
        CredentialValidityGate.Decision.AVAILABLE,
        gate.decide(Duration.ofSeconds(20)));
~~~

Để test dịch chuyển sau thời điểm confirm, dùng `Clock` có `Instant` cập nhật được, rồi thử ngay trước/sau biên `T_exp - B - M`. `Clock.fixed` ở ví dụ chỉ chứng minh trạng thái ban đầu.

### 13.2. Integration test với Vault và DB test

1. Bật Database engine tại Vault test với TTL ngắn; tạo role và ACL tối thiểu.
2. Đăng nhập bằng identity workload, cấp credential A, mở pool A, ghi lease TTL/ID vào trạng thái test an toàn.
3. Cắt đường mạng từ ứng dụng tới Vault ngay trước renewal; giữ DB connection path bình thường.
4. Xác minh lease error events, retry/backoff và readiness; khi tới ngưỡng hạn, request DB mới bị từ chối.
5. Thử phản hồi backend khi lease quá hạn để hiểu đặc tính DB/plugin, **không lấy kết quả tạm thành công làm chính sách sử dụng quá hạn**.
6. Khôi phục kết nối Vault; re-auth và xin credential B hoặc renew nếu vẫn được phép; tạo pool B và xác minh request mới thực sự dùng B.
7. Thử thu hồi credential A sớm, token mất quyền, policy đổi và role không tồn tại.
8. Kiểm tra log/trace không tiết lộ password, Vault token hay lease metadata nhạy cảm.

Mock `VaultOperations` chỉ kiểm tra logic Java; không chứng minh lease, ACL, revocation và backend thực tế hoạt động.

## 14. Bài tập tình huống

Ứng dụng `orders` có DB lease TTL 12 phút, được Vault cấp lúc **10:00**. Vault mất kết nối lúc **10:09**. Renewal lúc 10:10 timeout. Mỗi request ghi đơn hàng có operation budget tối đa **90 giây**, safety margin **30 giây**.

- Mốc hết hạn đã xác nhận vẫn là **10:12** vì chưa nhận phản hồi renew thành công.
- Lúc **10:09**, còn 3 phút, lớn hơn 90 + 30 giây: có thể nhận request theo policy nếu backend vẫn hợp lệ và không có dấu hiệu revoked.
- Lúc **10:10:30**, chỉ còn 90 giây, không vượt 120 giây cần thiết: **từ chối request mới** phụ thuộc DB credential.
- Nếu Vault hồi phục lúc **10:13**, credential A đã qua deadline; phải xác thực và nhận credential B mới, kiểm chứng pool B rồi mở lại traffic.
- Nếu DB vẫn cho các connection cũ truy vấn tới 10:14, điều đó **không chứng minh quyền sử dụng hợp lệ** của credential A.

Hãy đề xuất cách theo dõi `T_exp`, cách tạo pool B và loại readiness response cho request DB trong từng mốc, đồng thời nêu giới hạn của ước lượng local khi Vault có thể revoke secret sớm.

## 15. Câu hỏi tự đánh giá

1. Vì sao outage Vault không làm TTL bị “đóng băng”?
2. Dynamic DB lease khác gì với KV secret chứa API key tĩnh?
3. Tại sao renew timeout không được coi như renew thành công?
4. Vì sao token Vault hết hạn có thể ảnh hưởng tới lease của credential đã cấp?
5. `LifecycleAwareSessionManager` và `SecretLeaseContainer` đảm nhiệm hai vòng đời nào?
6. Vì sao `SecretLeaseExpiredEvent` có thể đến muộn hơn deadline thực?
7. `RetainOnIoError` giữ giá trị property có đồng nghĩa credential vẫn hợp lệ không?
8. Điều kiện `now + B + M < T_exp` hỗ trợ quyết định nghiệp vụ nào?
9. Làm thế nào xác nhận HikariCP hoặc SDK thực sự dùng credential mới?
10. KV, Transit và certificate PKI có xử lý renew theo cùng cách với dynamic DB lease không?
11. Readiness và liveness phải khác nhau như thế nào trong sự cố Vault?
12. Những dữ liệu nào cần che trong log, trace, metric khi điều tra renewal failure?

## Tài liệu tham khảo

- [HashiCorp Vault — Lease, Renew, and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — Tokens](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [HashiCorp Vault — Lease Renew CLI](https://developer.hashicorp.com/vault/docs/commands/lease/renew)
- [Spring Vault — Credential Rotation, SecretLeaseContainer và CertificateContainer](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — Authentication và token lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — VaultTemplate và Session Management](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault — Lease Event API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/package-summary.html)
- [Spring Cloud Vault — Advanced Topics](https://docs.spring.io/spring-cloud-vault/reference/advanced-topics.html)
- [HashiCorp Vault — Key metrics for common health checks](https://developer.hashicorp.com/vault/docs/internals/telemetry/key-metrics)
