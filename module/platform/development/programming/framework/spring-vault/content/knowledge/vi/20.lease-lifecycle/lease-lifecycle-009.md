# LeaseErrorListener và lỗi lấy hoặc gia hạn secret trong Spring Vault

Ứng dụng Java sử dụng **Spring Vault** để truy cập HashiCorp Vault thường cần credential động như username/password database, token truy cập hệ thống khác hoặc những secret có **lease**. Các credential này có thời hạn và có thể được Vault gia hạn hoặc thu hồi. Trong môi trường production, Vault có thể từ chối một lần lấy secret, việc gia hạn lease có thể thất bại vì token không còn hiệu lực, hoặc kết nối mạng gián đoạn trước thời điểm hết hạn. Nếu ứng dụng không nhận biết lỗi và tiếp tục sử dụng credential đã hết hạn, yêu cầu nghiệp vụ sẽ thất bại dù chương trình vẫn đang chạy.

Trong chương **Vòng đời lease** của module **SPRING_VAULT**, bài học này giải thích cách sử dụng **`LeaseErrorListener`** cùng **`SecretLeaseContainer`** để nhận và xử lý lỗi **lấy, gia hạn, thu hồi hoặc xoay vòng secret**. Ta sẽ thực hành cách đăng ký listener, phân biệt sự kiện thành công và lỗi, thiết kế quy trình phục hồi, giám sát an toàn và kiểm thử tích hợp.

> **Nguyên tắc xuyên suốt:** `LeaseErrorListener` thông báo **một thao tác lease gặp lỗi**; chỉ từ callback này không thể kết luận ngay rằng credential đã hết hạn, rằng Vault đã thu hồi lease hoặc rằng ứng dụng chắc chắn sẽ không phục hồi. Cần kết hợp thông tin lease, thời gian còn lại, sự kiện khác và trạng thái của thành phần đang dùng credential.

## 1. Vòng đời lease và điểm phát sinh lỗi

**Lease** là cơ chế Vault gắn quyền sử dụng một số secret với thời hạn. Khi gọi một dynamic secrets engine, chẳng hạn `database/creds/reporting`, Vault có thể trả:

~~~json
{
  "request_id": "57b0...",
  "lease_id": "database/creds/reporting/Hu7m...",
  "lease_duration": 1800,
  "renewable": true,
  "data": {
    "username": "v-reporting-Hu7m",
    "password": "<REDACTED>"
  },
  "auth": null
}
~~~

Các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `data.username`, `data.password` | Credential được engine tạo để ứng dụng sử dụng, phải bảo vệ như secret. |
| `lease_id` | Định danh lease của secret động để quản lý vòng đời. |
| `lease_duration` | Thời gian lease ban đầu được cấp, tính bằng **giây**, không phải timestamp tuyệt đối. |
| `renewable` | Cho phép **yêu cầu** gia hạn; Vault vẫn quyết định kết quả theo quyền và giới hạn TTL. |
| `auth` | Thường là `null` trong phản hồi đọc secret; không phải nơi chứa lease của secret động. |

Khi credential sắp hết hạn, một ứng dụng có thể gọi API gia hạn lease; nếu lease không thể gia hạn nữa, ứng dụng có thể phải **xin credential mới** và cập nhật các client/pool đang sử dụng giá trị cũ.

~~~mermaid
flowchart TD
    A[Đăng nhập Vault và có session token] --> B[Đọc dynamic secret]
    B --> C{Lấy secret thành công?}
    C -->|Không| E[LeaseErrorListener: lỗi lấy secret]
    C -->|Có| D[Nhận credential và lease]
    D --> F[Ứng dụng dùng credential]
    F --> G[SecretLeaseContainer lập lịch renew]
    G --> H{Renew thành công?}
    H -->|Có| I[Nhận lease TTL mới]
    I --> F
    H -->|Lỗi| J[LeaseErrorListener: lỗi renew]
    J --> K{Credential còn hợp lệ?}
    K -->|Có| L[Quan sát và thử phục hồi có giới hạn]
    K -->|Không / không xác định an toàn| M[Ngừng cấp kết nối mới, xin credential mới]
    L --> G
    M --> N[Thay credential và cập nhật client/pool]
    N --> F
    E --> O[Giới hạn readiness và chờ phục hồi có kiểm soát]
~~~

Bốn điểm thường gặp lỗi là **lấy secret lần đầu**, **gia hạn lease**, **thu hồi lease** và **xoay vòng lấy secret mới**. `LeaseErrorListener` được thiết kế để quan sát lỗi phát sinh từ các tương tác đó trong cơ chế container của Spring Vault.

## 2. Vai trò của SecretLeaseContainer và các listener

`SecretLeaseContainer` quản lý các `RequestedSecret` mà ứng dụng đăng ký. Container có thể:

1. Lấy secret tại đường dẫn được đăng ký khi khởi chạy.
2. Theo dõi lease và lên lịch gia hạn trước thời điểm hết hạn.
3. Phát sự kiện khi secret được tạo, lease được gia hạn, secret được xoay vòng hoặc lease được ghi nhận hết hạn.
4. Phát thông báo lỗi khi việc tương tác với Vault gặp exception.

Ba API liên quan có vai trò khác nhau:

| API | Nhiệm vụ | Dữ liệu được nhận |
| --- | --- | --- |
| `LeaseListener` | Quan sát **sự kiện vòng đời** thông thường. | `onLeaseEvent(SecretLeaseEvent event)`. |
| **`LeaseErrorListener`** | Quan sát **exception** khi xử lý secret/lease. | `onLeaseError(SecretLeaseEvent event, Exception exception)`. |
| `LeaseListenerAdapter` | Adapter có thể xử lý cả hai callback. | Override `onLeaseEvent` và/hoặc `onLeaseError` theo nhu cầu. |

`LeaseErrorListener` nằm trong package:

~~~java
org.springframework.vault.core.lease.event.LeaseErrorListener
~~~

Theo API Spring Vault hiện hành, đây là **functional interface** có một callback:

~~~java
@FunctionalInterface
public interface LeaseErrorListener {
    void onLeaseError(SecretLeaseEvent leaseEvent, Exception exception);
}
~~~

- `leaseEvent` không null; nó cho biết **`RequestedSecret` nào đang được xử lý** thông qua `leaseEvent.getSource()`.
- `exception` là lỗi gây ra sự kiện; có thể liên quan HTTP 403/404/5xx, I/O, timeout, việc renew hoặc bước khác.
- `leaseEvent.getLease()` **có thể null**, đặc biệt khi không lấy được secret ban đầu và chưa có lease để gắn với event.
- Không suy rằng `exception.getMessage()` luôn an toàn để ghi log: một số HTTP client hoặc wrapper có thể đưa thông tin request/response vào thông báo lỗi.

**Callback không thay thế logic xử lý secret của ứng dụng.** Đăng ký listener giúp phát hiện và phản ứng với lỗi; nó không tự khiến database connection pool dùng credential mới hoặc bảo đảm mọi lần retry sẽ thành công.

### 2.1. Sự kiện thường và sự kiện lỗi

Trong `org.springframework.vault.core.lease.event` có các event như:

| Event | Điều xảy ra | Cách sử dụng |
| --- | --- | --- |
| `SecretLeaseCreatedEvent` | Lấy được secret, có thể kèm lease. | Cập nhật dữ liệu ứng dụng hoặc khởi tạo client an toàn. |
| `AfterSecretLeaseRenewedEvent` | Renew lease thành công. | Ghi nhận tín hiệu thành công và TTL mới. |
| `SecretLeaseRotatedEvent` | Lấy secret mới theo chế độ rotation. | Thay credential trong client hoặc pool. |
| `SecretLeaseExpiredEvent` | Container nhận thấy lease đã hết hạn. | Ngừng dựa vào credential cũ, kích hoạt phương án phục hồi. |
| `SecretNotFoundEvent` | Không tìm thấy secret ở path được yêu cầu. | Kiểm tra cấu hình đường dẫn/engine và chính sách xử lý secret thiếu. |
| `SecretLeaseErrorEvent` | Container bắt được exception khi lấy hoặc tương tác với lease. | Phân loại nguyên nhân, giám sát và ứng phó theo mức độ. |

Các sự kiện này khác nhau về ý nghĩa: **`SecretLeaseExpiredEvent` không đồng nghĩa `SecretLeaseErrorEvent`**, và **`SecretNotFoundEvent` không nhất thiết luôn xuất hiện dưới dạng cùng một HTTP exception**. Khi cần theo dõi cả hành vi thành công lẫn lỗi, đăng ký **cả `LeaseListener` và `LeaseErrorListener`**.

## 3. Cấu hình RequestedSecret: renew và rotate

`RequestedSecret` mô tả đường dẫn và **chế độ** mà container phải quản lý:

~~~java
RequestedSecret renewing =
        RequestedSecret.renewable("database/creds/reporting");

RequestedSecret rotating =
        RequestedSecret.rotating("database/creds/reporting");
~~~

| Chế độ | Hành vi chủ đạo | Khi lease hết hạn |
| --- | --- | --- |
| **RENEW** (`renewable(path)`) | Xin secret một lần và tìm cách gia hạn lease khi còn hợp lệ. | Lease cũ không còn sử dụng được; ứng dụng cần chiến lược cấp credential mới nếu muốn hoạt động tiếp. |
| **ROTATE** (`rotating(path)`) | Xin và gia hạn secret nếu có thể, sau đó lấy **secret mới** khi cần rotation. | Container có thể yêu cầu lại path để nhận credential và lease mới; thành phần sử dụng secret phải thay giá trị cũ. |

Spring Vault cũng cung cấp:

~~~java
container.requestRotatingSecret("database/creds/reporting");
container.requestRenewableSecret("database/creds/reporting");
~~~

Hai kiểu đăng ký này tương đương với việc tạo `RequestedSecret` theo mode rồi đưa vào container theo API phù hợp.

**Nhận thức quan trọng:** chế độ ROTATE giúp container yêu cầu credential mới, nhưng **không tự cập nhật mọi thư viện hoặc connection pool**. Ví dụ một pool JDBC được khởi tạo bằng username/password cũ vẫn có thể giữ các connection cũ sau khi nhận event xoay vòng. Ứng dụng cần tích hợp với thành phần lưu trữ credential, đổi cấu hình pool hoặc xây dựng pool mới đúng cách.

Container theo dõi các đối tượng `RequestedSecret` đã đăng ký; sự kiện chứa `getSource()` để callback định vị đúng path/mode. Đừng xử lý mọi lỗi của container như lỗi của **cùng một** database nếu nó đang quản lý nhiều secret.

## 4. Ví dụ Java: đăng ký LeaseErrorListener trước khi container chạy

Ví dụ dưới đây sử dụng Spring Vault core, Spring Framework và SLF4J. Giả sử `VaultOperations` đã kết nối Vault bằng một token workload với policy phù hợp, và ứng dụng có bean `TaskScheduler` để lập lịch. Với Spring Boot, cần đối chiếu bean `SecretLeaseContainer` do Spring Cloud Vault tự cấu hình để tránh tạo hai container quản lý cùng secret.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.vault.core.lease.event.AfterSecretLeaseRenewedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseCreatedEvent;
import org.springframework.vault.core.lease.event.SecretLeaseExpiredEvent;
import org.springframework.vault.core.lease.event.SecretLeaseRotatedEvent;

@Configuration(proxyBeanMethods = false)
public class VaultLeaseConfig {

    private static final Logger log =
            LoggerFactory.getLogger(VaultLeaseConfig.class);

    private static final String CREDS_PATH = "database/creds/reporting";

    @Bean
    SecretLeaseContainer reportingLeaseContainer(
            VaultOperations vaultOperations,
            TaskScheduler taskScheduler) {

        SecretLeaseContainer container =
                new SecretLeaseContainer(vaultOperations, taskScheduler);

        // Chỉ một RequestedSecret cho path/chiến lược được giao.
        RequestedSecret requested = RequestedSecret.rotating(CREDS_PATH);

        // Đăng ký callback trước lúc Spring khởi động SmartLifecycle.
        container.addErrorListener((event, exception) -> {
            if (!requested.equals(event.getSource())) {
                return;  // Container có thể theo dõi nhiều path.
            }

            // Lease có thể null nếu ngay từ đầu không lấy được secret.
            boolean leaseAvailable = event.getLease() != null;

            // Ghi log đúng path đã kiểm soát và loại lỗi; không in response.
            log.warn(
                    "Vault lease failed: path={}, leaseAvailable={}, errorType={}",
                    CREDS_PATH,
                    leaseAvailable,
                    exception.getClass().getSimpleName());

            // Ở production: tăng metric theo errorType, phát cảnh báo
            // và chuyển công việc phục hồi sang worker riêng.
            // Không throw lại exception và không gọi API Vault đồng bộ ở đây.
        });

        container.addLeaseListener(event -> {
            if (!requested.equals(event.getSource())) {
                return;
            }

            if (event instanceof SecretLeaseExpiredEvent) {
                log.warn("Vault lease expired: path={}", CREDS_PATH);

            } else if (event instanceof SecretLeaseRotatedEvent) {
                log.info("Vault secret rotated: path={}", CREDS_PATH);
                // Chuyển credential mới cho client/pool ở lớp thích hợp.

            } else if (event instanceof SecretLeaseCreatedEvent) {
                log.info("Vault secret acquired: path={}", CREDS_PATH);

            } else if (event instanceof AfterSecretLeaseRenewedEvent) {
                log.debug("Vault lease renewed: path={}", CREDS_PATH);
            }
        });

        container.register(requested);
        return container;
    }
}
~~~

**Ý nghĩa từng phần:**

1. `new SecretLeaseContainer(vaultOperations, taskScheduler)` tạo container có client Vault và scheduler.
2. `RequestedSecret.rotating(...)` chỉ định path mà ứng dụng muốn container quản lý.
3. `container.addErrorListener(...)` nhận **`(event, exception)`** khi container gặp lỗi.
4. `event.getSource()` trả về `RequestedSecret` tương ứng; mã kiểm tra để tránh xử lý nhầm secret.
5. `event.getLease() != null` kiểm tra xem **event có thông tin lease hay không**, không phải bằng chứng lease còn hiệu lực.
6. `container.addLeaseListener(...)` theo dõi **các sự kiện thông thường**; thứ tự kiểm tra `SecretLeaseRotatedEvent` trước `SecretLeaseCreatedEvent` hữu ích vì rotated event là một dạng created event.
7. `container.register(requested)` thêm secret vào cơ chế quản lý; khi Spring khởi tạo và start bean, container sẽ lấy secret và lập lịch.
8. Log chỉ chứa path cố định, trạng thái lease hiện diện và loại exception. **Không** đưa credential, raw lease ID hoặc exception message vào log.

Nếu tự quản lý `SecretLeaseContainer` ngoài Spring bean lifecycle, tài liệu Spring Vault minh họa gọi `container.afterPropertiesSet()` rồi `container.start()`. Khi container là Spring bean, framework thường gọi các lifecycle method; không gọi thủ công cả hai thêm lần nữa trong `@Bean` để tránh khởi động trùng.

### 4.1. Tại sao phải đăng ký listener trước khi start?

Container có thể yêu cầu secret ngay khi khởi chạy. Nếu đăng ký `LeaseErrorListener` **sau** khi container đã start, ứng dụng có thể **bỏ lỡ lỗi lấy secret ban đầu**. Quy tắc hữu ích là cấu hình listener và đăng ký `RequestedSecret` trước, sau đó mới để container start.

Ngoài ra, callback có thể chạy trên **thread khởi động** hoặc **worker thread của scheduler**. Vì vậy, tránh gọi database blocking, reset connection pool trực tiếp, ngủ để retry hoặc thực hiện HTTP request dài trong callback. Những thao tác này có thể chặn quá trình startup hoặc các công việc renew khác.

## 5. Khi nào LeaseErrorListener được gọi?

### 5.1. Lỗi lấy secret lần đầu

Giả sử container start và yêu cầu:

~~~http
GET /v1/database/creds/reporting
X-Vault-Token: <TOKEN_DA_CHE>
~~~

Nếu token không có capability `read` trên `database/creds/reporting`, Vault có thể trả HTTP **403**. Container không nhận credential/lease hợp lệ; callback lỗi có thể được gọi với `getLease() == null`.

**Hậu quả ứng dụng:** không có username/password để khởi tạo database client. Phải **không coi secret rỗng là credential hợp lệ**. Với service bắt buộc cần database, readiness nên ở trạng thái chưa sẵn sàng hoặc startup thất bại có kiểm soát theo thiết kế.

Không khắc phục bằng cách tự cấp root token hoặc bỏ qua Vault auth. Phải kiểm tra token workload, policy và path thực tế.

### 5.2. Lỗi gia hạn lease

Giả sử Vault đã cấp:

~~~json
{
  "lease_id": "database/creds/reporting/Hu7m...",
  "lease_duration": 1800,
  "renewable": true,
  "data": {
    "username": "<REDACTED>",
    "password": "<REDACTED>"
  }
}
~~~

Container lập lịch yêu cầu renew, tương đương về ý nghĩa với API Vault:

~~~http
POST /v1/sys/leases/renew
X-Vault-Token: <TOKEN_DA_CHE>
Content-Type: application/json

{
  "lease_id": "database/creds/reporting/Hu7m...",
  "increment": 1800
}
~~~

Vault có thể từ chối vì lease không tồn tại, đã bị revoke, token dùng để renew không hợp lệ, thiếu quyền hoặc đã chạm max TTL. **`renewable: true` không cam kết mọi lần renew đều thành công**.

Sau lỗi renew:

- Credential **có thể vẫn còn hiệu lực** nếu còn TTL và Vault chưa thu hồi lease, ví dụ lỗi mạng tạm thời.
- Credential **có thể đã mất hiệu lực** nếu token bị revoke, lease không tồn tại hoặc Vault chủ động thu hồi.
- Bản thân `LeaseErrorListener` không được thiết kế để phân biệt chắc chắn tất cả trạng thái này chỉ bằng một callback.

Ứng dụng phải **kiểm tra trạng thái hiện hành và kế hoạch phục hồi**. Khi không thể xác nhận còn hiệu lực, không tiếp tục mở kết nối mới với credential nghi đã hết hạn.

### 5.3. Lỗi xoay vòng hoặc thu hồi

Với mode ROTATE, sau khi cần credential mới, container yêu cầu lại dynamic secret path. Nếu Vault trả 403/5xx hoặc không cấp được credential, ứng dụng có thể tiếp tục chỉ có giá trị cũ. Lúc đó cần cảnh báo và chuyển traffic sang instance lành mạnh, hoặc tạm dừng chức năng phụ thuộc secret.

Nếu thao tác revoke gặp lỗi, không được hiểu rằng credential đã chắc chắn bị thu hồi; việc thu hồi thực tế cần được xác minh qua Vault hoặc hệ thống đích trong quy trình vận hành. Tùy loại secret engine, Vault có thể sử dụng cơ chế revocation khác nhau.

## 6. Phân biệt LeaseErrorListener với SecretLeaseErrorEvent

Hai khái niệm thường xuất hiện cùng nhau:

- **`LeaseErrorListener`** là interface callback. Container gọi `onLeaseError(SecretLeaseEvent, Exception)` để báo lỗi.
- **`SecretLeaseErrorEvent`** là **một loại `SecretLeaseEvent`** biểu diễn trường hợp xảy ra exception trong quá trình tương tác lease.

`SecretLeaseErrorEvent` có các thành phần:

~~~java
// Minh họa accessor, không phải lớp implement event.
SecretLeaseEvent event = /* event do container phát */;

RequestedSecret source = event.getSource();
Lease lease = event.getLease();  // Có thể null.

if (event instanceof SecretLeaseErrorEvent errorEvent) {
    Throwable cause = errorEvent.getException();
}
~~~

Ở callback `onLeaseError`, bạn đã được truyền trực tiếp `Exception exception` nên **không cần ép kiểu** để lấy lỗi. Có thể dùng `event.getSource().getPath()` để xác định secret liên quan và `event.getSource().getMode()` để phân biệt RENEW/ROTATE.

**Đừng dựa vào `event.getLease().get...` mà không kiểm tra null.** Khi lỗi xảy ra trước lúc Vault tạo lease, event không có lease để truy xuất.

Nếu dự án dùng `LeaseListenerAdapter`, có thể override cả hai callback để xử lý theo một chỗ:

~~~java
container.addLeaseListener(new LeaseListenerAdapter() {
    @Override
    public void onLeaseEvent(SecretLeaseEvent event) {
        // Xử lý created/renewed/expired/rotated event.
    }

    @Override
    public void onLeaseError(SecretLeaseEvent event, Exception exception) {
        // Xử lý lỗi.
    }
});
~~~

**Lưu ý API:** `LeaseListenerAdapter` triển khai cả `LeaseListener` và `LeaseErrorListener`, nhưng `addLeaseListener(...)` chỉ đăng ký phần listener thông thường. Để chắc chắn nhận lỗi, cần đăng ký listener đó qua **`addErrorListener(...)`** nữa. Ví dụ:

~~~java
LeaseListenerAdapter listener = new LeaseListenerAdapter() {
    @Override
    public void onLeaseEvent(SecretLeaseEvent event) {
        // Thành công / hết hạn.
    }

    @Override
    public void onLeaseError(SecretLeaseEvent event, Exception exception) {
        // Lỗi.
    }
};

container.addLeaseListener(listener);
container.addErrorListener(listener);
~~~

Với Java mới, dùng lambda `container.addErrorListener((event, exception) -> {...})` là cách gọn nhất khi chỉ quan tâm lỗi.

## 7. Thiết kế chiến lược xử lý lỗi an toàn

Một handler production nên phân biệt **lỗi tạm thời**, **lỗi cấu hình/quyền** và **lỗi không thể sử dụng credential cũ**. Tuy nhiên, kết luận cuối cùng cần dựa trên thông tin nhận được từ Vault hoặc hệ thống phụ thuộc, vì cùng HTTP 403 có thể đến từ nhiều nguyên nhân.

| Nhóm lỗi | Ví dụ | Phản ứng khuyến nghị |
| --- | --- | --- |
| **Lỗi lấy secret ban đầu** | 403/404, role chưa tồn tại, mount chưa bật. | Đánh dấu dependency chưa sẵn sàng, kiểm tra ACL/path, không tạo client bằng giá trị rỗng. |
| **Lỗi mạng tạm thời** | Timeout, DNS, TLS handshake, 502/503, 429. | Retry có backoff và jitter, giới hạn số lần, chặn request khi đã vượt thời điểm credential an toàn. |
| **Lỗi xác thực token** | Session token hết hạn/revoke hoặc workload auth không làm mới được. | Phục hồi token qua `ClientAuthentication`/`SessionManager` thích hợp; sau đó yêu cầu secret mới nếu cần. |
| **Lease không còn tồn tại** | Vault trả `lease not found` hoặc đã revoke. | Dừng gia hạn lease cũ, xin dynamic secret mới qua cơ chế ROTATE, cập nhật nơi tiêu thụ. |
| **Chạm max TTL hoặc không còn renewable** | Renew không thể kéo dài lease. | Chuẩn bị rotation trước khi credential hết hạn, không retry renew vô hạn. |
| **Lỗi thu hồi** | Revoke trả 403/5xx. | Báo vận hành, xác minh trạng thái thu hồi, không khẳng định đã revoke thành công. |
| **Lỗi callback/consumer** | Cập nhật connection pool thất bại sau rotation. | Bảo vệ trạng thái ứng dụng, báo lỗi riêng, không coi event thành công là consumer đã cập nhật. |

### 7.1. Không chặn thread container trong callback

Một callback tốt chỉ thực hiện các tác vụ **nhanh và an toàn**:

1. Xác định path/mode theo `event.getSource()`.
2. Phân loại exception ở mức an toàn; không log raw secret hoặc request body.
3. Tăng counter/metric, ghi timestamp, ghi nhận trạng thái degraded.
4. Đưa công việc cần I/O vào executor/hàng đợi có giới hạn hoặc cơ chế retry đã quản lý.
5. Nếu dependency bắt buộc không có credential hợp lệ, điều chỉnh readiness/khả năng nhận traffic theo thiết kế.

Tránh triển khai kiểu sau:

~~~java
// Ví dụ không nên áp dụng trong callback:
container.addErrorListener((event, error) -> {
    while (true) {
        // Gọi Vault không giới hạn rồi Thread.sleep(...)
        // có thể block startup hoặc scheduler, tạo retry storm.
    }
});
~~~

Callback không nên `throw` lại exception để “bắt Vault retry”. Spring Vault đã có cơ chế xử lý riêng; ném thêm lỗi có thể phá vỡ luồng publish event hoặc gây tác dụng phụ khó dự đoán.

### 7.2. Tình trạng degraded khác với expired

Ví dụ một lần renew lỗi do Vault trả 503, nhưng lease vẫn còn thời hạn khoảng 10 phút. Ứng dụng nên ghi nhận **degraded** và theo dõi TTL an toàn, trong khi xử lý phục hồi. Đừng tự kết luận lease đã hết hạn ở thời điểm 503.

Nếu quá gần thời điểm hết hạn mà vẫn chưa xác nhận renew thành công, ứng dụng nên chuyển sang trạng thái **không sẵn sàng cấp kết nối mới** hoặc cơ chế phụ thuộc tương ứng, tùy mức độ an toàn. Điều này giúp tránh sử dụng credential không còn hợp lệ khi quá hạn.

~~~text
HEALTHY  --renew thất bại, còn TTL--> DEGRADED
DEGRADED --renew / rotation thành công--> HEALTHY
DEGRADED --hết thời gian an toàn--> UNAVAILABLE
UNAVAILABLE --nhận credential mới và consumer cập nhật--> HEALTHY
~~~

Tài liệu trên mô tả **trạng thái nghiệp vụ do ứng dụng thiết kế**, không phải enum có sẵn của Spring Vault.

## 8. Quan hệ với session token: nguyên nhân sâu hơn của lỗi lease

Một dynamic secret thường được cấp trong phạm vi **Vault session token** đang dùng. Khi token đó hết hạn hoặc bị thu hồi, Vault có thể thu hồi những lease gắn với token. Vì vậy đôi khi lỗi renew secret chỉ là **triệu chứng**, còn nguyên nhân nằm ở **vòng đời xác thực**.

| Đối tượng | Ai quản lý? | Các thông tin cần theo dõi |
| --- | --- | --- |
| Vault client token | `SessionManager` / `LifecycleAwareSessionManager`. | `auth.lease_duration`, trạng thái token, renew/relogin. |
| Secret lease | `SecretLeaseContainer`. | `lease_id`, `lease_duration`, `renewable`, renewal/rotation. |
| Database connection pool | Ứng dụng và driver/pool tương ứng. | Credential đang dùng, kết nối đang tồn tại, thời điểm thay mới. |

Khi token cũ chạm max TTL, session manager có thể cần đăng nhập lại bằng AppRole, Kubernetes, AWS, GCP hoặc workload authentication phù hợp. Nhưng **token mới không làm credential cũ đã bị revoke sống lại**. Cơ chế secret lease phải xin credential mới và chuyển nó đến các consumer.

Tài liệu Spring Vault có đề cập `SessionLeaseContainer` với các listener `getAuthenticationListener()` và `getAuthenticationErrorListener()` nhằm liên kết sự kiện session token với việc khởi động lại secret management. Điều này hữu ích khi cần recovery sau re-login; phải cấu hình đúng phiên bản và bean lifecycle. Đừng tưởng `LeaseErrorListener` tự thực hiện toàn bộ quy trình re-login.

### 8.1. Đừng trộn TTL token và TTL secret

Giả sử:

- Vault token được cấp TTL 1 giờ.
- Database credential có lease TTL 15 phút.
- Renew lease database lỗi sau 10 phút.
- Token Vault vẫn còn 40 phút.

Lỗi renew lease chưa chứng minh token đã hết hạn; có thể do lease bị revoke, engine hoặc mạng. Ngược lại, token còn hạn không đồng nghĩa database credential còn sử dụng được sau khi lease hết 15 phút.

Khi ứng dụng phát cảnh báo, cần ghi rõ **đang gặp lỗi token session hay lỗi secret lease**, để nhóm vận hành không điều tra nhầm nơi.

## 9. Rotation và việc cập nhật connection pool

Giả sử Spring Vault lấy credential mới từ `database/creds/reporting` sau khi lease cũ hết hạn. Container phát `SecretLeaseRotatedEvent`; tuy nhiên connection pool như HikariCP có thể vẫn giữ connection đã mở bằng username/password cũ.

Luồng cập nhật an toàn nên:

1. Nhận sự kiện có credential mới và kiểm tra dữ liệu đủ trường cần thiết.
2. Chuẩn bị cấu hình/client mới hoặc cập nhật cơ chế cấp kết nối theo API chính thức của pool.
3. Kiểm tra kết nối mới bằng credential mới.
4. Chuyển traffic sang client/pool mới, ngừng cấp connection từ pool cũ.
5. Đóng hoặc evict connection cũ theo chính sách và deadline an toàn.
6. Chỉ đánh dấu ứng dụng đã phục hồi khi consumer thực sự dùng credential mới.

**Không nên chỉ gọi `dataSource.setPassword(...)` rồi giả định mọi connection đang mở đều đổi danh tính.** Nhiều connection đã được tạo trước đó tiếp tục tồn tại; việc chuyển pool cần hiểu rõ driver, transaction đang chạy, connection lifetime và chính sách thu hồi bên database.

Spring Vault phiên bản mới có abstraction `ManagedSecret` hỗ trợ gắn vòng đời secret với consumer; nên cân nhắc cơ chế này khi không cần tự điều phối bằng từng listener.

## 10. Quan sát và giám sát LeaseErrorListener

Mục tiêu observability là biết **secret nào đang có sự cố, mức độ, thời gian còn lại và hệ thống có phục hồi hay không**.

### 10.1. Metric nên thu thập

| Metric đề xuất | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `vault_lease_operation_error_total` | Counter | Số lần callback `LeaseErrorListener` được gọi; phân loại `path_label` được kiểm soát, `exception_type`, mode. |
| `vault_secret_acquired_total` | Counter | Số lần lấy/rotation secret thành công. |
| `vault_lease_renew_success_total` | Counter | Số lần renew thành công. |
| `vault_lease_expired_total` | Counter | Số lần container ghi nhận lease hết hạn. |
| `vault_lease_remaining_seconds` | Gauge | Thời gian lease còn lại, dựa trên TTL và thời gian ghi nhận an toàn. |
| `vault_secret_consumer_ready` | Gauge | Consumer đã có credential hợp lệ và dùng được hay chưa. |

Chỉ gắn nhãn có số lượng hữu hạn: tên service, **logical path đã chuẩn hóa**, loại sự kiện/exception. **Không dùng `lease_id` hay username động làm metric tag**, vì sẽ tạo số lượng chuỗi nhãn rất lớn và có thể làm lộ thông tin vận hành.

### 10.2. Logging an toàn

Ví dụ log an toàn:

~~~text
WARN vault_lease_failed path=database/creds/reporting
     mode=ROTATE errorType=VaultException leasePresent=true
~~~

Không nên log:

~~~text
ERROR requestBody={"username":"v-reporting-abc","password":"..."}
ERROR authToken=hvs....
ERROR leaseId=database/creds/reporting/<dynamic-id>
~~~

`exception.getMessage()` và stack trace từ HTTP client cũng cần được đánh giá/redact trước khi đưa vào hệ thống quan sát. Không log trực tiếp `event` hoặc `SecretLeaseCreatedEvent.getSecrets()` vì có thể mang credential.

### 10.3. Cảnh báo theo ý nghĩa, tránh báo động giả

Một lỗi I/O đơn lẻ có thể phục hồi khi retry; không nhất thiết đánh page ngay. Cảnh báo ưu tiên khi:

- Lỗi lặp lại trong nhiều lần liên tiếp hoặc trên nhiều instance.
- Lease chỉ còn rất ít thời gian mà chưa được gia hạn.
- Rotation thất bại và credential cũ gần/đã hết hạn.
- Login token lỗi đồng thời với nhiều secret lease.
- Consumer sau rotation vẫn không tạo được connection bằng credential mới.

Có thể dùng readiness để giảm traffic cho instance đang không có credential hợp lệ. Liveness nên phản ánh tiến trình ứng dụng còn hoạt động; không nên lập tức kill/restart vô hạn chỉ vì một Vault API timeout tạm thời.

## 11. Kiểm thử tích hợp với Vault thật

Sử dụng **Vault trong môi trường test cô lập**, chẳng hạn Vault dev hoặc Testcontainers có cấu hình dynamic secrets engine phù hợp. Không dùng root token làm token workload trong các test phân quyền. Với những kiểm thử dynamic DB, cần database test để Vault thực sự tạo/renew/revoke credential.

| Tình huống | Thiết lập | Kết quả cần xác minh |
| --- | --- | --- |
| Lấy secret ban đầu thành công | Role DB và token có quyền đọc path. | `SecretLeaseCreatedEvent` đến đúng path; không có callback lỗi. |
| Thiếu quyền đọc | Token không có `read` trên dynamic credentials path. | `LeaseErrorListener` nhận lỗi 403; không có credential hợp lệ để khởi tạo consumer. |
| Sai path / mount | RequestedSecret trỏ đến path không tồn tại. | Quan sát `SecretNotFoundEvent` hoặc event lỗi phù hợp; không nhầm với renew failure. |
| Vault tạm thời mất kết nối | Đưa Vault/network vào trạng thái lỗi trong test. | Error callback nhận exception; ứng dụng ghi trạng thái degraded, không block scheduler. |
| Gia hạn thành công | Lease được phép renew và TTL còn đủ. | `AfterSecretLeaseRenewedEvent`, TTL mới; consumer vẫn dùng credential hợp lệ. |
| Gia hạn thất bại | Thu hồi lease hoặc làm token không hợp lệ trước kỳ renew. | Listener nhận lỗi/expired event phù hợp; không tiếp tục dùng credential đã hết hạn. |
| Rotation thành công | Yêu cầu secret mới khi lease cũ hết. | `SecretLeaseRotatedEvent`; consumer/pool thật sự nhận credential mới. |
| Rotation thất bại | Engine/người dùng không cấp được secret mới. | Callback báo lỗi; readiness/consumer state phản ánh đúng rủi ro. |
| Token session hết hạn | Token chạm max TTL, cần re-login. | Kiểm tra cơ chế session phục hồi và secret được yêu cầu lại nếu lease cũ không còn hợp lệ. |

### 11.1. Gợi ý phép thử callback độc lập

Không nhất thiết phải chạy Vault để kiểm tra **logic của riêng listener**. Có thể tách phần xử lý callback thành class nhận:

~~~java
void handleLeaseFailure(SecretLeaseEvent event, Exception failure);
~~~

Sau đó dùng event test được tạo với `RequestedSecret` đúng path và `Lease` null để chứng minh handler không ném `NullPointerException`. Thử với exception thuộc nhóm được xem là transient và permanent, kiểm tra các counter/trạng thái được cập nhật, không đưa secret vào log.

Kiểm thử **vòng đời thực** vẫn cần Vault thật, vì việc gia hạn có được chấp nhận, event phát lúc nào, lease bị revoke ra sao đều phụ thuộc server và timing.

### 11.2. Tình huống thực hành xử lý lỗi

**Tình huống A:** Container start nhưng `GET database/creds/reporting` trả 403. `LeaseErrorListener` nhận event có `getLease() == null`. Ứng dụng có thể dùng username/password mặc định để tiếp tục chạy không?

**Đáp án:** Không nên. Chưa nhận được credential được cấp quyền, nên không sử dụng giá trị giả như dữ liệu thật. Cần đánh dấu dependency chưa sẵn sàng và sửa token policy/role/path.

**Tình huống B:** Lease còn khoảng 10 phút, một lần renew lỗi 503. Có thể kết luận credential đã hết hạn không?

**Đáp án:** Không. 503 thường biểu thị lỗi tạm thời của dịch vụ hoặc đường truyền; callback tự nó không chứng minh lease hết hạn. Phải tiếp tục theo dõi TTL, retry có giới hạn và dùng kế hoạch phục hồi trước deadline.

**Tình huống C:** Callback `onLeaseError` log toàn bộ `exception.getMessage()` và `event.toString()`. Rủi ro là gì?

**Đáp án:** Có thể rò rỉ credential, body, path nhạy cảm hoặc metadata; nên chỉ log thông tin đã lọc như tên path kiểm soát, loại exception và trạng thái lease hiện diện.

**Tình huống D:** Container nhận `SecretLeaseRotatedEvent` nhưng service JDBC vẫn kết nối bằng password cũ. Vì sao?

**Đáp án:** Event cho biết Spring Vault đã lấy secret mới; consumer có thể chưa cập nhật pool, hoặc đang giữ connection cũ. Phải xây dựng và kiểm chứng cơ chế chuyển credential/pool.

**Tình huống E:** Ứng dụng chỉ đăng ký một `LeaseListenerAdapter` bằng `addLeaseListener(adapter)` rồi override `onLeaseError` nhưng không thấy lỗi. Cần làm gì?

**Đáp án:** Đăng ký callback lỗi bằng **`addErrorListener(adapter)`** nữa; `addLeaseListener` chỉ là tuyến đăng ký listener thông thường.

## 12. Tóm lược và nguồn tham khảo

- **`LeaseErrorListener`** nhận `onLeaseError(SecretLeaseEvent, Exception)` khi Spring Vault gặp lỗi lấy secret, renew, revoke hoặc rotate.
- **`SecretLeaseContainer`** quản lý secret đã đăng ký, lập lịch renewal và phát sự kiện; nên thêm listener **trước khi container start**.
- **`event.getSource()`** xác định `RequestedSecret`, còn **`event.getLease()` có thể null**; không xem sự hiện diện của lease là bằng chứng credential còn hạn.
- **`LeaseListener`** theo dõi sự kiện thành công, expired và rotation; **`LeaseErrorListener`** phản ánh lỗi. Với `LeaseListenerAdapter`, phải đăng ký cả hai loại listener nếu cần cả hai callback.
- **Lỗi renew chưa đồng nghĩa lease đã expired**. Phân loại nguyên nhân, theo dõi TTL/lease state và phục hồi có giới hạn.
- **Credential mới cần được áp dụng tới consumer**: client, JDBC pool hoặc service khác không tự đổi ngay chỉ vì Vault đã rotate.
- **Token session và secret lease có vòng đời khác nhau**. Khi token hết hạn/revoke, các lease gắn với token có thể bị thu hồi; cơ chế re-login phải kết hợp với việc xin secret mới.
- **Không log secret, token, lease ID động và phản hồi HTTP nhạy cảm**. Dùng metrics, readiness và test Vault thật để xác minh phục hồi.

Tài liệu chính thức để đối chiếu API theo phiên bản:

1. [Spring Vault – Credential Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html): SecretLeaseContainer, sự kiện, TTL tuning và session token.
2. [Spring Vault – LeaseErrorListener Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/event/LeaseErrorListener.html): callback `onLeaseError`.
3. [Spring Vault – SecretLeaseContainer Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html): đăng ký secret, lifecycle và renewal.
4. [Spring Vault – SecretLeaseEventPublisher Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseEventPublisher.html): `addLeaseListener`, `addErrorListener`.
5. [Spring Vault – RequestedSecret Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/domain/RequestedSecret.html): mode RENEW/ROTATE và đường dẫn.
6. [HashiCorp Vault – Lease, Renew, Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease): cách Vault quản lý lease và quan hệ với token.

Bằng cách xử lý riêng **lỗi lấy secret**, **lỗi gia hạn lease** và **trạng thái thực của credential**, ứng dụng Java dùng Spring Vault có thể phát hiện sự cố kịp thời, tránh cấp kết nối bằng secret không còn hiệu lực và phục hồi có kiểm soát khi Vault trở lại bình thường.
