# AuthenticationListener và AuthenticationErrorListener trong Spring Vault

## 1. Mục tiêu và bối cảnh

Trong chương **Phiên và vòng đời token** của module **SPRING_VAULT**, ứng dụng Java dùng `VaultTemplate` để đọc KV secrets, gọi Transit encryption, PKI hoặc các secrets engine khác của HashiCorp Vault. Để thực hiện request, ứng dụng cần **Vault client token** hợp lệ. Với phương thức đăng nhập theo workload như Kubernetes, AppRole hoặc AWS, token được cấp sau khi `ClientAuthentication` đăng nhập, rồi được `SessionManager` cung cấp cho `VaultTemplate`.

Token có thể hết hạn, được gia hạn, bị thu hồi hoặc phải cấp lại. Khi nhiều Pod cùng chạy, cần phân biệt một lần renew bình thường với sự cố đăng nhập ảnh hưởng nhiều replica. Spring Vault cung cấp hai giao diện lắng nghe **vòng đời xác thực**:

- `AuthenticationListener`: nhận các sự kiện bình thường liên quan đến đăng nhập và token, chẳng hạn vừa đăng nhập thành công, chuẩn bị/đã gia hạn, chuẩn bị/đã thu hồi hoặc session token bị loại bỏ do hết hạn.
- `AuthenticationErrorListener`: nhận các sự kiện lỗi trong quá trình đăng nhập, gia hạn hay thu hồi token.

Hai listener giúp **quan sát và kết nối các thành phần quản lý vòng đời**, không phải một cơ chế tự động sửa lỗi quyền truy cập hoặc thay thế `LifecycleAwareSessionManager`.

Sau bài học, bạn có thể phân biệt hai callback, đăng ký listener đúng chỗ, hiểu các loại event, đo metrics không làm lộ token, xử lý các tình huống lỗi và lập kiểm thử tích hợp.

## 2. Nằm ở đâu trong kiến trúc Spring Vault?

Luồng xác thực đồng bộ thông thường:

1. `VaultTemplate` chuẩn bị gọi KV/Transit/PKI và yêu cầu `SessionManager.getSessionToken()`.
2. Nếu chưa có session hợp lệ, `LifecycleAwareSessionManager` dùng `ClientAuthentication` đăng nhập Vault.
3. Sau khi đăng nhập thành công, manager phát sự kiện `AfterLoginEvent`.
4. Khi token có TTL và đủ điều kiện renew, manager lên lịch gia hạn; vòng đời renew phát các sự kiện tương ứng.
5. Nếu login, renew hoặc revoke gặp lỗi, manager có thể phát một `AuthenticationErrorEvent` cụ thể; logic quản lý session quyết định có tiếp tục giữ, bỏ hoặc cấp lại token.
6. Listener được gọi để ghi nhận sự kiện, tăng metric hoặc kích hoạt một phối hợp có kiểm soát với thành phần quản lý secret lease.

~~~mermaid
flowchart TD
    A[VaultTemplate cần Vault token] --> B[SessionManager]
    B --> C{Token sử dụng được?}
    C -- Có --> D[Request tới KV / Transit / PKI]
    C -- Không --> E[ClientAuthentication login vào Vault]
    E --> F{Login thành công?}
    F -- Có --> G[AfterLoginEvent]
    F -- Không --> H[LoginFailedEvent]
    G --> I[AuthenticationListener]
    H --> J[AuthenticationErrorListener]
    G --> D
    B --> K[Đến lịch renew / shutdown]
    K --> L{Renew hoặc revoke thành công?}
    L -- Có --> M[Before/After ... Event]
    L -- Không --> N[Renewal/RevocationFailedEvent]
    M --> I
    N --> J
~~~

**Quan trọng:** `LifecycleAwareSessionManager` là nguồn event phổ biến; `SimpleSessionManager` hoặc một `SessionManager` tùy biến không nhất thiết phát các sự kiện này. Nếu ứng dụng dùng token được quản lý hoàn toàn từ bên ngoài và không login/renew qua manager đang quan sát, bạn có thể không thấy các event mong đợi.

## 3. API và chữ ký callback

Các API thuộc package `org.springframework.vault.authentication.event`:

~~~java
import org.springframework.vault.authentication.event.AuthenticationEvent;
import org.springframework.vault.authentication.event.AuthenticationErrorEvent;
import org.springframework.vault.authentication.event.AuthenticationListener;
import org.springframework.vault.authentication.event.AuthenticationErrorListener;

AuthenticationListener normalListener =
        (AuthenticationEvent event) -> {
            // Sự kiện vòng đời không lỗi.
        };

AuthenticationErrorListener errorListener =
        (AuthenticationErrorEvent event) -> {
            // Sự kiện lỗi đăng nhập, gia hạn hoặc thu hồi token.
        };
~~~

| Giao diện | Phương thức | Tham số | Mục đích |
|---|---|---|---|
| `AuthenticationListener` | `void onAuthenticationEvent(AuthenticationEvent event)` | Một `AuthenticationEvent`, ví dụ `AfterLoginEvent` | Theo dõi tiến trình bình thường của token/session. |
| `AuthenticationErrorListener` | `void onAuthenticationError(AuthenticationErrorEvent event)` | Một `AuthenticationErrorEvent`, ví dụ `LoginFailedEvent` | Theo dõi lỗi xuất hiện trong vòng đời auth token. |

Mỗi giao diện là **functional interface** nên có thể đăng ký lambda, method reference hoặc một class triển khai đầy đủ. Hai callback **không trả về token mới, không quyết định có retry hay không**. Chúng nhận sự kiện do session manager phát.

### Event object chứa gì?

`AuthenticationEvent` kế thừa `ApplicationEvent`; phương thức `getSource()` trả về một `VaultToken`. Đó là **credential nhạy cảm**. **Không log `event.getSource()`, `getToken()`, `toString()` hoặc serialize event** vào HTTP/log/metrics.

`AuthenticationErrorEvent` cũng là `ApplicationEvent` và cung cấp `getException()` để lấy nguyên nhân lỗi. `getSource()` của loại event này là `Object` và **cũng có thể chứa token**. Thông điệp lỗi HTTP có thể chứa dữ liệu vận hành nhạy cảm; nên phân loại exception bằng type/status đã kiểm duyệt thay vì xuất raw object hoặc stack trace lên hệ thống rộng quyền.

Lưu ý: dù các event kế thừa `ApplicationEvent`, Spring Vault có cơ chế multicaster **riêng**. Cách đăng ký có căn cứ là `addAuthenticationListener(...)` và `addErrorListener(...)` trên đúng session manager. Chỉ đánh dấu `@EventListener` hoặc khai báo class listener thành `@Component` không bảo đảm nhận được các event nội bộ này.

## 4. Các sự kiện mà AuthenticationListener nhận

Các tên class sau thuộc `org.springframework.vault.authentication.event`:

| Event | Thời điểm phát | Cách hiểu đúng |
|---|---|---|
| `AfterLoginEvent` | Sau khi login vào Vault thành công và nhận token. | Xác thực thành công; có thể tăng counter `login_success`. Không có nghĩa mọi path KV/Transit sẽ được phép truy cập. |
| `BeforeLoginTokenRenewedEvent` | Trước khi thực hiện renew của login token. | **Bắt đầu thử renew**, chưa chứng minh đã gia hạn thành công. |
| `AfterLoginTokenRenewedEvent` | Sau khi renew login token thành công. | Token đã được gia hạn; phù hợp để tăng counter `renew_success`. |
| `BeforeLoginTokenRevocationEvent` | Trước khi cố thu hồi login token. | Bắt đầu cố revoke, không có nghĩa token đã bị thu hồi. |
| `AfterLoginTokenRevocationEvent` | Sau khi thu hồi login token thành công. | Ghi nhận sự kiện revoke thành công, thường trong quá trình shutdown hoặc xử lý lifecycle. |
| `LoginTokenExpiredEvent` | Khi manager loại bỏ một login token bị xem là hết hạn. | Session cũ không còn được giữ để sử dụng như trước; có thể cần lần login mới. Đây không phải counter cho mọi lỗi HTTP `401`. |

Vì vậy, một chu trình có thể cho thấy:

~~~text
AfterLoginEvent                 : Đăng nhập lần đầu thành công
BeforeLoginTokenRenewedEvent    : Bắt đầu renew token đang dùng
AfterLoginTokenRenewedEvent     : Renew thành công
... (có thể renew thêm nhiều lần)
LoginTokenExpiredEvent          : Loại bỏ session token hết hạn
AfterLoginEvent                 : Đăng nhập lại thành công
BeforeLoginTokenRevocationEvent : Bắt đầu revoke khi shutdown
AfterLoginTokenRevocationEvent  : Revoke thành công
~~~

Đây chỉ là **một kịch bản minh họa**, không phải chuỗi event luôn xuất hiện đúng thứ tự trong mọi ứng dụng: token không renewable có thể bỏ qua renew; shutdown đột ngột không bảo đảm revoke; renew thất bại có thể tạo chuỗi sự kiện lỗi thay thế.

## 5. Các sự kiện mà AuthenticationErrorListener nhận

| Event lỗi | Tình huống điển hình | Hướng xử lý / điều tra |
|---|---|---|
| `LoginFailedEvent` | Vault login thất bại do credential sai/hết hạn, role/policy auth không hợp lệ hoặc kết nối tới Vault hỏng. | Kiểm tra auth method, workload credential, TLS/network, role và Vault audit. Không log login credential. |
| `LoginTokenRenewalFailedEvent` | Renew thất bại khi token bị revoke, hết TTL tối đa, không renewable hoặc Vault tạm không sẵn sàng. | Phân biệt lỗi token với lỗi mạng; quan sát khả năng session manager re-login bằng credential hiện hành. |
| `LoginTokenRevocationFailedEvent` | Thu hồi token không thành công khi dừng session hoặc thao tác vòng đời. | Ghi nhận sự cố để kiểm tra thu hồi; không tự kết luận token đã hết hiệu lực. |

Sự kiện lỗi mang `Throwable` trong `getException()`. Đối với giám sát, ưu tiên một tập nhãn ổn định như `login_failed`, `renew_failed`, `revoke_failed`. Có thể kết hợp dữ liệu HTTP status, Vault request ID hoặc log bảo mật được quyền truy cập, nhưng tránh dùng raw token, raw exception message hoặc path chứa bí mật làm nhãn metric.

**Phạm vi quan sát có giới hạn:** Nếu `VaultTemplate` gửi request KV và nhận `403 permission denied` do Vault policy thiếu quyền, lỗi đó **không mặc nhiên tạo `LoginFailedEvent`**. Token có thể đã đăng nhập thành công và vẫn hợp lệ; lỗi là ở **authorization của secret endpoint**. Tương tự, `404` vì secret path không tồn tại là lỗi dữ liệu/đường dẫn, không phải failure event của `SessionManager`.

## 6. Cách đăng ký hai listener

`LifecycleAwareSessionManager` triển khai `AuthenticationEventMulticaster` và cung cấp:

~~~java
// manager là LifecycleAwareSessionManager đã được cấu hình
// và cũng chính là manager mà VaultTemplate đang sử dụng.
manager.addAuthenticationListener(event -> {
    // Quan sát event bình thường, không chạm tới token value.
});

manager.addErrorListener(event -> {
    // Ghi nhận lỗi theo type, không in raw Throwable/source.
});
~~~

Các phương thức tương ứng `removeAuthenticationListener(...)` và `removeErrorListener(...)` cho phép gỡ listener khi cần. Nếu quản lý listener động, phải **giữ tham chiếu đến chính listener đã đăng ký**, vì tạo một lambda mới khi gọi `remove...` sẽ không phải cùng instance.

### Ví dụ thực tế: cấu hình Spring Boot và Micrometer

Đoạn code sau minh họa **đăng ký trực tiếp trên `SessionManager`** và đưa sự kiện vào Micrometer bằng nhãn cố định. Giả định ứng dụng dùng Spring Boot, có `MeterRegistry` (ví dụ qua Actuator/Micrometer), có một bean `SessionManager` quan sát được và `VaultTemplate` thực sự dùng chính bean đó.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.authentication.event.*;

@Configuration(proxyBeanMethods = false)
public class VaultAuthTelemetryConfiguration {

    @Bean
    SmartInitializingSingleton registerVaultAuthenticationListeners(
            SessionManager sessionManager, MeterRegistry meterRegistry) {

        return () -> {
            if (!(sessionManager instanceof
                    AuthenticationEventMulticaster multicaster)) {
                throw new IllegalStateException(
                        "Vault SessionManager does not publish auth events");
            }

            AuthenticationListener normal = event ->
                    meterRegistry.counter(
                            "vault.auth.lifecycle.events",
                            "kind", normalKind(event))
                    .increment();

            AuthenticationErrorListener errors = event ->
                    meterRegistry.counter(
                            "vault.auth.lifecycle.errors",
                            "kind", errorKind(event))
                    .increment();

            multicaster.addAuthenticationListener(normal);
            multicaster.addErrorListener(errors);
        };
    }

    private static String normalKind(AuthenticationEvent event) {
        if (event instanceof AfterLoginEvent) {
            return "login_success";
        }
        if (event instanceof BeforeLoginTokenRenewedEvent) {
            return "renew_started";
        }
        if (event instanceof AfterLoginTokenRenewedEvent) {
            return "renew_success";
        }
        if (event instanceof BeforeLoginTokenRevocationEvent) {
            return "revoke_started";
        }
        if (event instanceof AfterLoginTokenRevocationEvent) {
            return "revoke_success";
        }
        if (event instanceof LoginTokenExpiredEvent) {
            return "token_expired";
        }
        return "other";
    }

    private static String errorKind(AuthenticationErrorEvent event) {
        if (event instanceof LoginFailedEvent) {
            return "login_failed";
        }
        if (event instanceof LoginTokenRenewalFailedEvent) {
            return "renew_failed";
        }
        if (event instanceof LoginTokenRevocationFailedEvent) {
            return "revoke_failed";
        }
        return "other";
    }
}
~~~

Code dùng `instanceof` với pattern variable, phù hợp Java 17 trở lên. Với Java cũ hơn, dùng cast truyền thống; với phiên bản Spring Vault cũ, cần kiểm tra availability của `AuthenticationEventMulticaster` (API này được giới thiệu ở nhánh Spring Vault 3.1). Đảm bảo dependency Micrometer có sẵn để import `MeterRegistry`; tên metric chỉ là đề xuất phục vụ observability, không phải metric tự động của Spring Vault.

**Cổng quan trọng khi cấu hình:** bean `SessionManager` mà code nhìn thấy phải đúng instance dùng cho những Vault request cần quan sát. Trong ứng dụng Spring Cloud Vault, bootstrap/config import có thể kích hoạt login rất sớm hoặc dùng ApplicationContext riêng; đăng ký ở `SmartInitializingSingleton` **có thể bỏ lỡ event đầu tiên**. Nếu cần bắt cả login lúc bootstrap, phải đăng ký listener **khi tạo session manager và trước lời gọi login đầu tiên**, ở đúng context quản lý Vault. Việc đăng ký trong main context không bảo đảm nhìn thấy sự kiện từ một manager khác trong bootstrap context.

Nếu tự xây `LifecycleAwareSessionManager` trong Spring Vault Core, có thể đăng ký sớm ngay lúc dựng bean:

~~~java
// Một đoạn trong phương thức @Bean tạo LifecycleAwareSessionManager:
LifecycleAwareSessionManager manager = /* cấu hình manager theo phiên bản */;

manager.addAuthenticationListener(event -> {
    auditCounters.recordNormalEvent(event.getClass());
});
manager.addErrorListener(event -> {
    auditCounters.recordAuthError(event.getClass());
});

return manager;
~~~

Đây là **đoạn minh họa ý tưởng**: `auditCounters` là service do ứng dụng tự định nghĩa; constructor/session manager API có thể khác giữa các phiên bản Spring Vault. Cách đăng ký sớm phù hợp nếu cần nhận chính xác sự kiện đăng nhập đầu tiên. Không đồng thời tạo hai session manager cạnh tranh để cùng quản lý một `VaultTemplate`.

## 7. Listener chạy trên luồng nào?

Tài liệu `LifecycleAwareSessionManager` nêu rõ event có thể phát trên **thread đang thực hiện request** hoặc **worker thread** dùng cho background renewal. Vì vậy listener cần:

1. **Không làm việc chặn lâu:** callback nên tăng counter, cập nhật trạng thái nhẹ hoặc enqueue vào một hàng đợi đã kiểm soát. Không gửi email, gọi mạng, truy vấn database chậm hay sleep trong callback.
2. **An toàn đa luồng:** dùng counter thread-safe, `Atomic*` hoặc công cụ metrics hỗ trợ concurrency; tránh cập nhật `ArrayList`/`HashMap` dùng chung không đồng bộ.
3. **Không giả định thứ tự tổng:** event của nhiều token, retry hoặc replica có thể xen kẽ. Không khôi phục lịch sử của toàn cluster chỉ từ thứ tự log ở một Pod.
4. **Giữ callback đơn giản:** lỗi trong chính listener có thể ảnh hưởng tới luồng phát event; code quan sát nên tránh ném exception bất ngờ. Nếu phải thực hiện side effect, thiết kế ranh giới lỗi rõ ràng và kiểm thử.
5. **Chống lộ bí mật:** không xuất `event.getSource()`, token accessor, exception raw payload, login request hoặc Vault secret value; chỉ ghi event type, stage, môi trường và trace ID đã làm sạch khi cần.

Nếu muốn biểu thị sức khỏe dịch vụ theo sự kiện, không nên cho một `LoginTokenRenewalFailedEvent` đơn lẻ lập tức đưa tất cả Pod sang `NotReady`. Session manager có thể đăng nhập lại thành công ngay sau đó. Readiness phải phản ánh **khả năng phục vụ hiện tại**, qua một phép kiểm tra an toàn hoặc trạng thái ứng dụng được quản lý đúng, có hysteresis để tránh dao động.

## 8. Kết hợp với Spring Cloud Vault và vòng đời token

Trong ứng dụng Spring Cloud Vault, có thể bật quản lý session token bằng cấu hình sau (kiểm tra tên property theo version đang dùng):

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.example.internal:8200
      authentication: KUBERNETES
      kubernetes:
        kubernetes-path: kubernetes
        role: payments-read
        service-account-token-file: /var/run/secrets/vault/token
      session:
        lifecycle:
          enabled: true
          refresh-before-expiry: 10s
          expiry-threshold: 20s
~~~

Kịch bản minh họa: Pod có projected ServiceAccount JWT được Kubernetes xoay vòng; Vault role trả Vault token có TTL và khả năng renew. `LifecycleAwareSessionManager` định kỳ gia hạn Vault token; listener đo các lần `renew_started`, `renew_success` và `renew_failed`. Khi cần login lại, `KubernetesAuthentication` phải lấy JWT mới từ file được Kubernetes duy trì.

**Listener không làm mới Kubernetes JWT và cũng không làm mới secret thuê theo lease.** Nếu workload dùng AppRole, AWS, mTLS certificate hay một auth method khác, các event auth token vẫn có thể tương tự nhau, nhưng cơ chế cung cấp credential để **login lại** phải được thiết kế riêng.

### Vault token khác dynamic secret lease

Giả sử ứng dụng dùng Vault database secrets engine tạo tài khoản database tạm thời. Vault client token xác thực request xin credential; credential có **lease TTL** riêng. Khi session token hết hạn hoặc bị revoke, Vault có thể revoke những lease thuộc session đó. `AuthenticationListener` quan sát vòng đời **session token**, không phải mọi lần renew/reissue database credential.

Spring Vault cung cấp `SecretLeaseContainer` và những cơ chế lease event dành riêng cho secret lifecycle. Ngoài ra, `SessionLeaseContainer` có các listener hỗ trợ phối hợp tái khởi động secret management sau re-login. Tài liệu Spring Vault mô tả phương thức `getAuthenticationListener()` và `getAuthenticationErrorListener()` để đăng ký lên đúng SessionManager. Không tự coi việc bắt được `AfterLoginEvent` là tất cả database credential, PKI certificate hoặc cache KV đã được refresh.

## 9. Đọc bảng tình huống: sự kiện nào, xử lý thế nào?

| Tình huống | Event có thể quan sát | Điều nên làm |
|---|---|---|
| Pod khởi động, Vault login thành công | `AfterLoginEvent` | Tăng `login_success`, theo dõi latency login riêng nếu cần; không log Vault token. |
| Token renewable, renew thành công | `BeforeLoginTokenRenewedEvent` → `AfterLoginTokenRenewedEvent` | Tăng `renew_started` và `renew_success`, giữ dashboard TTL. |
| Token chạm max TTL hoặc không renewable | Có thể hết hạn/bị loại bỏ rồi `AfterLoginEvent` sau re-login | Theo dõi số lần re-login tăng bất thường, kiểm tra auth role TTL và workload credential. |
| JWT Kubernetes đã cũ nên re-login thất bại | `LoginFailedEvent` | Kiểm tra projected token file, Vault role, TokenReview và Kubernetes API; không dùng JWT cache. |
| Vault tạm không truy cập được lúc renew | `LoginTokenRenewalFailedEvent` | Kiểm tra network/TLS/DNS/Vault health, quan sát việc session re-login sau phục hồi. |
| AppRole SecretID hết hiệu lực lúc re-login | `LoginFailedEvent` | Sửa luồng cung cấp credential hợp lệ; listener chỉ phát hiện lỗi. |
| Shutdown bình thường, revoke token thành công | `BeforeLoginTokenRevocationEvent` / `AfterLoginTokenRevocationEvent` | Ghi nhận shutdown sạch; không bảo đảm mọi Pod bị kill có event này. |
| Shutdown nhưng Vault unreachable | `LoginTokenRevocationFailedEvent` có thể xuất hiện | Điều tra token cũ có còn sống tới TTL hay không, xem chính sách revocation. |
| Login thành công nhưng KV `403` | Không nhất thiết có auth error event | Kiểm tra Vault ACL trên `data/`, `metadata/` hoặc Transit path; lỗi này thuộc resource authorization. |
| KV secret `404` | Thường không có auth error event | Kiểm tra mount và key path, dữ liệu có tồn tại hay không. |

Không nên đặt một quy tắc “gặp `LoginTokenRenewalFailedEvent` là gọi login ngay trong callback”. Việc lấy token mới phải đi qua state machine/session manager, tránh cuộc đua token giữa request thread và background renew.

## 10. Metrics và cảnh báo thiết thực

Các tên metric ở ví dụ Java là do chúng ta tạo:

| Metric | Nhãn gợi ý | Ý nghĩa |
|---|---|---|
| `vault.auth.lifecycle.events` | `kind=login_success` | Số lần login thành công do manager phát event. |
| `vault.auth.lifecycle.events` | `kind=renew_success` | Số lần renew token thành công. |
| `vault.auth.lifecycle.events` | `kind=token_expired` | Số event loại bỏ session token hết hạn. |
| `vault.auth.lifecycle.errors` | `kind=login_failed` | Số lần đăng nhập Vault thất bại. |
| `vault.auth.lifecycle.errors` | `kind=renew_failed` | Số lần renew thất bại. |
| `vault.auth.lifecycle.errors` | `kind=revoke_failed` | Số lần revoke token lỗi. |

Các nhãn có số giá trị hữu hạn, nên phù hợp với Prometheus/Micrometer. Có thể thêm `application`, `namespace`, `cluster` ở tầng registry nếu cần, nhưng **không** đưa raw token, accessor, Pod UID động theo request, role ID/secret ID, username hoặc secret path không kiểm soát vào metric labels.

**Ví dụ diễn giải:** nếu `renew_failed` tăng trên nhiều Pod trong vài phút đồng thời lỗi `login_failed` tăng, điều tra Vault auth endpoint, Vault cluster, mạng và workload credential. Nếu chỉ `renew_failed` tăng nhưng ngay sau đó `login_success` cũng tăng và request KV vẫn thành công, đó có thể là đường chuyển phiên hợp lệ khi token hết khả năng renew. Không kết luận tình trạng chỉ từ một counter đơn lẻ.

Với alert, nên dùng tỷ lệ theo cửa sổ thời gian, ngưỡng phù hợp lưu lượng và phối hợp với metric lỗi HTTP/Vault health. Số `login_success` tăng không tự động là tốt: vòng đăng nhập liên tục cũng có thể phản ánh TTL quá ngắn, cấu hình renew sai hoặc lỗi đồng bộ session.

## 11. Kiểm thử hai listener

### Kiểm thử callback riêng lẻ

Đối với mục tiêu “event được phân loại đúng và không log token”, có thể tạo event giả, gọi trực tiếp hai callback rồi kiểm tra counter. Các lớp sự kiện đều là public; ví dụ `AfterLoginEvent` nhận `VaultToken`. Dùng một token giả chỉ nằm trong test, không kết nối Vault:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.event.AfterLoginEvent;
import org.springframework.vault.authentication.event.AuthenticationListener;
import org.springframework.vault.support.VaultToken;

class AuthenticationListenerUnitTest {

    @Test
    void countsSuccessfulLoginWithoutReadingTokenValue() {
        AtomicInteger successfulLogins = new AtomicInteger();
        AuthenticationListener listener = event -> {
            if (event instanceof AfterLoginEvent) {
                successfulLogins.incrementAndGet();
            }
        };

        listener.onAuthenticationEvent(
                new AfterLoginEvent(VaultToken.of("test-only-fake-token")));

        assertEquals(1, successfulLogins.get());
    }
}
~~~

Test này **chỉ kiểm tra logic callback**, chưa chứng minh Spring Vault tự phát event hay Micrometer đã được nối tới đúng manager. Nếu dùng code cấu hình ở mục 6, test nên kiểm tra ít nhất ba điều: listener được đăng ký lên đúng `AuthenticationEventMulticaster`, metric `login_success` có tăng khi manager phát event, và token giả không có mặt trong log.

### Kiểm thử tích hợp với Vault thật

Thực hiện trong Vault dev/Testcontainers hoặc cluster test có auth method và role riêng; không dùng token/secret production:

1. **Đăng nhập thành công:** khởi tạo `LifecycleAwareSessionManager` mới, đăng ký listener **trước lần `getSessionToken()` đầu tiên**; dùng `VaultTemplate` đọc KV secret mẫu. Xác nhận có `AfterLoginEvent`, counter `login_success` tăng và secret chỉ đọc được theo policy test.
2. **Sai credential/role:** cấu hình auth method với credential không hợp lệ. Gọi `getSessionToken()` và xác nhận login thất bại, listener lỗi ghi nhận `LoginFailedEvent` nếu manager phát event; không in credential hoặc token.
3. **Renew thành công:** dùng Vault role với TTL ngắn, `renewable=true` và hạn mức cho phép; quan sát `BeforeLoginTokenRenewedEvent` và `AfterLoginTokenRenewedEvent`. Kiểm tra request vẫn chạy được sau thời điểm TTL cũ.
4. **Renew thất bại:** trong môi trường test, chặn có kiểm soát quyền renew hoặc thu hồi token; quan sát `LoginTokenRenewalFailedEvent` và hành vi manager bỏ session/re-login. Lỗi mạng có thể khiến nhận event muộn hoặc khác theo thời điểm.
5. **Shutdown/revoke:** đóng session manager một cách bình thường và kiểm tra `BeforeLoginTokenRevocationEvent` / `AfterLoginTokenRevocationEvent` khi role phát **service token** có thể revoke; không giả định có revoke event nếu dùng `VaultToken` được quản lý ngoài ứng dụng.
6. **Lỗi KV sau khi auth tốt:** cho role login thành công nhưng policy thiếu quyền đọc `kv-app/data/...`. Xác nhận `VaultTemplate` nhận `403` mà metric `login_failed` **không bị tăng sai** chỉ vì lỗi resource authorization.

Các event renew/revoke thường diễn ra bất đồng bộ. Dùng `CountDownLatch`/Awaitility có timeout hợp lý, không `Thread.sleep` vô hạn; tách từng kịch bản để không phụ thuộc thứ tự ngẫu nhiên. Nếu không có quyền chỉnh Vault role/TTL hoặc network lab, đánh dấu bài test tích hợp tương ứng chưa chạy thay vì giả lập kết quả thành công.

### Tiêu chí nghiệm thu trong production

- [ ] Listener đăng ký trên **đúng session manager của `VaultTemplate`**, trước sự kiện cần quan sát.
- [ ] Phân biệt login/renew/revoke thành công, chuẩn bị thực hiện và các lỗi tương ứng.
- [ ] Callback thread-safe, hoàn thành nhanh, không thực hiện request đăng nhập lại hoặc retry vô hạn trong chính callback.
- [ ] Không log/serialize `AuthenticationEvent.getSource()`, raw `AuthenticationErrorEvent.getException()` hay credential.
- [ ] Metrics có tập nhãn hữu hạn; giám sát được lỗi tăng đồng thời trên nhiều Pod và tình huống re-login lặp lại.
- [ ] Sự cố `403` ở KV/Transit/PKI được phân loại riêng với `LoginFailedEvent`.
- [ ] Có kiểm thử tích hợp login, renew, lỗi login, token expiry, revoke và shutdown trong môi trường cô lập.
- [ ] Nếu dùng dynamic leases, đã tích hợp vòng đời lease/credential riêng và xem xét `SessionLeaseContainer` phù hợp.

## 12. Những hiểu nhầm cần tránh

**“AuthenticationListener là cơ chế tự renew token.”** Không đúng. `LifecycleAwareSessionManager` quản lý token; listener chỉ nhận sự kiện để quan sát hoặc phối hợp.

**“Chỉ cần implements AuthenticationListener và @Component là xong.”** Không chắc. Đăng ký trực tiếp lên `AuthenticationEventMulticaster` của manager phù hợp, kiểm tra thứ tự initialization và context thực tế.

**“Đăng nhập thành công chứng tỏ luôn đọc được secret.”** Không đúng. Vault policy trên KV v2 `data/`, `metadata/`, Transit hay PKI kiểm tra quyền riêng sau khi login.

**“Mọi HTTP 401/403 đều tạo AuthenticationErrorListener event.”** Không đúng. Listener lỗi theo dõi **lỗi vòng đời xác thực token** được session manager phát; request business có thể thất bại độc lập.

**“Log cả event và exception để dễ debug.”** Rủi ro cao. Event source có thể chứa Vault token; exception/message có thể chứa URL và dữ liệu vận hành nhạy cảm. Dùng loại event, status đã kiểm duyệt, correlation ID và audit có phân quyền.

**“Có AfterLoginEvent nghĩa là secret lease đã được gia hạn.”** Không đúng. Session token và secret lease là hai vòng đời khác nhau. Cần dùng cơ chế lease management/rotation phù hợp.

## 13. Kết luận

Trong SPRING_VAULT, `AuthenticationListener` và `AuthenticationErrorListener` là hai điểm móc quan trọng để quan sát **phiên xác thực và vòng đời Vault token** mà `LifecycleAwareSessionManager` sử dụng. Listener bình thường giúp thấy login, renew, expiry và revoke; listener lỗi giúp nhận biết các thất bại trong login/renew/revoke. Đăng ký chúng lên đúng manager, xử lý nhanh và không làm lộ credential giúp ứng dụng Java đo được chất lượng xác thực workload, chẩn đoán lỗi theo lớp và kết nối với giám sát.

Để vận hành ổn định, cần kết hợp listeners với cấu hình auth method, TTL/renew/re-login hợp lệ, Vault policy ít quyền nhất, cơ chế quản lý dynamic lease riêng và kiểm thử tích hợp trên Vault thật. **Listener báo điều gì đã xảy ra; session manager cùng chính sách vận hành quyết định cách khôi phục.**

## Tài liệu tham khảo

- Spring Vault Javadoc — [`AuthenticationListener`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/event/AuthenticationListener.html).
- Spring Vault Javadoc — [`AuthenticationErrorListener`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/event/AuthenticationErrorListener.html).
- Spring Vault Javadoc — [`AuthenticationEvent`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/event/AuthenticationEvent.html) và [`AuthenticationErrorEvent`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/event/AuthenticationErrorEvent.html).
- Spring Vault Javadoc — [`AuthenticationEventMulticaster`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/event/AuthenticationEventMulticaster.html).
- Spring Vault Javadoc — [`LifecycleAwareSessionManager`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html).
- Spring Vault Reference — [Authentication Methods / Token Lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- Spring Vault Reference — [Credential Rotation / Token Renewal and Session Management](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html).
