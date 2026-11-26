# ReactiveSessionManager cùng quản lý gia hạn trong Spring Vault

Trong một ứng dụng Java sử dụng **Spring Vault** theo mô hình reactive, mọi lần đọc KV secret, mã hóa qua Transit hoặc gọi PKI đều cần **Vault client token** hợp lệ. Nếu tự đăng nhập ở mỗi yêu cầu HTTP, ứng dụng sẽ tăng tải cho Vault và khó xử lý khi nhiều luồng truy cập đồng thời; nếu giữ một token mãi mãi, token có thể hết TTL hoặc bị thu hồi. **`ReactiveSessionManager`** giải quyết bài toán cung cấp token trong reactive pipeline, còn **`ReactiveLifecycleAwareSessionManager`** bổ sung quản lý **gia hạn (renew)**, đăng nhập lại khi cần và kết thúc phiên.

Bài thuộc chương **API reactive** của module **SPRING_VAULT**. Người học sẽ phân biệt `VaultTokenSupplier` và `ReactiveSessionManager`, tìm hiểu lifecycle của `LoginToken`, kết hợp `AuthenticationStepsOperator` và `ReactiveVaultTemplate`, xử lý lỗi token renewal, hiểu giới hạn TTL của Vault, đồng thời thiết kế kiểm thử và giám sát mà không rò rỉ credential.

> **Phạm vi:** Bài này tập trung vào **vòng đời token dùng để xác thực Vault**. Lease của database credentials, chứng chỉ PKI hoặc secret động có cơ chế gia hạn/rotation **riêng**; không được hiểu rằng gia hạn session token tự gia hạn mọi secret.

## 1. Vì sao cần quản lý phiên trong reactive application?

Một pipeline Reactor có thể xử lý hàng trăm request cùng cần đọc secret ở Vault. Hãy so sánh ba cách tiếp cận:

| Cách dùng token | Vấn đề hoặc đặc tính | Phù hợp |
| --- | --- | --- |
| Tự gọi Vault login trước **mỗi** lần đọc. | Gây nhiều request auth, dễ tạo token thừa, khó phối hợp khi concurrent. | Chỉ thích hợp cho demo đặc biệt, **không** phải default production. |
| Giữ cố định một `VaultToken` trong field. | Ít request login nhưng không tự xử lý TTL, revoke hoặc re-login. | Token tĩnh có chính sách xoay vòng riêng, dùng thận trọng. |
| Sử dụng **`ReactiveSessionManager`**. | Tái sử dụng token phiên, lấy token theo `Mono` khi cần; implementation lifecycle-aware có thể gia hạn và tái đăng nhập. | Lựa chọn chuẩn cho `ReactiveVaultTemplate`. |

Một `ReactiveVaultOperations.read(...)` trả về `Mono<VaultResponse>`. Mỗi subscription có thể dẫn đến một lời gọi HTTP cần token. Session manager phải đảm bảo ứng dụng không đăng nhập lại vô ích cho các request song song, và phải cung cấp token hợp lệ trong phạm vi năng lực của nó.

~~~mermaid
sequenceDiagram
    participant Http as WebFlux handler
    participant Template as ReactiveVaultTemplate
    participant Session as ReactiveSessionManager
    participant Auth as AuthenticationStepsOperator
    participant Vault as HashiCorp Vault
    Http->>Template: read("secret/data/payments/config")
    Template->>Session: getSessionToken()
    alt Chưa có token
        Session->>Auth: getVaultToken()
        Auth->>Vault: Login qua workload auth
        Vault-->>Auth: LoginToken và TTL
        Auth-->>Session: VaultToken
    else Đã có token đang dùng
        Session-->>Template: Tái sử dụng token
    end
    Session-->>Template: VaultToken
    Template->>Vault: GET secret (X-Vault-Token)
    Vault-->>Template: VaultResponse
    Template-->>Http: Mono kết quả
    Note over Session,Vault: Scheduler gia hạn token khi cần, không login trên mọi request
~~~

**Tách vai trò:** `ReactiveVaultTemplate` là client thực hiện API; `ReactiveSessionManager` cung cấp token; cơ chế xác thực tạo token mới; **Vault server quyết định** token có thể được gia hạn và TTL thực sự được cấp.

## 2. API nền tảng: VaultTokenSupplier, ReactiveSessionManager và ReactiveLifecycleAwareSessionManager

### 2.1. VaultTokenSupplier: một nguồn token reactive

Giao diện `org.springframework.vault.authentication.VaultTokenSupplier` là functional interface:

~~~java
@FunctionalInterface
public interface VaultTokenSupplier {
    Mono<VaultToken> getVaultToken();
}
~~~

`Mono<VaultToken>` mô tả quá trình nhận token, có thể là token có sẵn hoặc token được cấp sau một chuỗi login bất đồng bộ. Khi subscribe, nguồn có thể thực hiện I/O.

`VaultTokenSupplier` **không tự hứa** lưu phiên, renew hay login lại. Đó là trách nhiệm của implementation cụ thể hoặc một lớp bao ngoài.

### 2.2. ReactiveSessionManager: contract của phiên

Giao diện `org.springframework.vault.authentication.ReactiveSessionManager` mở rộng `VaultTokenSupplier` và có phương thức mặc định:

~~~java
public interface ReactiveSessionManager extends VaultTokenSupplier {
    default Mono<VaultToken> getSessionToken() {
        // Minh họa cách phương thức mặc định ủy quyền cho token supplier.
        return getVaultToken();
    }
}
~~~

Đây là **mã minh họa contract và ủy quyền mặc định**, không phải copy nguyên văn body từ Spring Vault. Trong code nghiệp vụ, gọi `getSessionToken()` khi cần truy cập trạng thái phiên. Tuy nhiên, với `ReactiveVaultTemplate`, thông thường **không cần tự gắn token vào HTTP header**: template kết hợp session manager với client để làm việc này.

### 2.3. ReactiveLifecycleAwareSessionManager: quản lý toàn bộ lifecycle

`ReactiveLifecycleAwareSessionManager` là implementation lifecycle-aware, đồng thời implements:

- `ReactiveSessionManager` để cung cấp token cho reactive client.
- `VaultTokenSupplier` thông qua `getVaultToken()` trả về `Mono<VaultToken>`.
- `DisposableBean` để giải phóng tài nguyên phiên theo chính sách của implementation.
- `AuthenticationEventMulticaster` để phát sự kiện xác thực và sự kiện lỗi.

Theo Spring Vault Javadoc 4.1.2, lớp này **đồng bộ hóa trạng thái theo cách thread-safe/lock-free**: nếu nhiều luồng cùng yêu cầu token khi chưa có phiên, nó chỉ cần lấy token qua phương thức xác thực **một lần** trong đợt đó, thay vì bắn nhiều lần login không cần thiết.

Sau khi đã có token, manager có thể **tái sử dụng** token và **renew bất đồng bộ** khi có dữ liệu TTL. Nếu token không thể gia hạn hoặc đã hết hiệu lực, manager có thể bỏ trạng thái token để **yêu cầu login mới** khi ứng dụng cần phiên tiếp theo.

| Thành phần | Vai trò chính | Có tự renew token? |
| --- | --- | --- |
| `VaultTokenSupplier` | Tạo hoặc cung cấp `Mono<VaultToken>`. | **Không theo contract**. |
| `AuthenticationStepsOperator` | Thực thi `AuthenticationSteps` non-blocking khi subscribe để login. | Không quản lý phiên/TTL dài hạn. |
| `CachingVaultTokenSupplier` | Cache token được nguồn tạo ra. | **Không phải lifecycle renew manager**; chỉ cache là chưa đủ cho token TTL ngắn. |
| `ReactiveSessionManager` | Giao diện quản lý phiên cho reactive components. | Phụ thuộc implementation. |
| **`ReactiveLifecycleAwareSessionManager`** | Cache/điều phối login, renew và re-login theo TTL. | **Có**, nếu token và điều kiện Vault cho phép. |

## 3. Cách token được cấp và gia hạn

### 3.1. Login trả LoginToken khác token được cung cấp sẵn

Vault login từ AppRole, Kubernetes, AWS IAM hay cơ chế workload phù hợp có thể trả:

~~~json
{
  "auth": {
    "client_token": "<VAULT_TOKEN_REDACTED>",
    "lease_duration": 1800,
    "renewable": true,
    "token_type": "service",
    "policies": ["default", "payments-read"]
  }
}
~~~

Spring Vault phân biệt:

| Loại | Dữ liệu đi kèm | Cơ chế quản lý |
| --- | --- | --- |
| `VaultToken` | Bao bọc giá trị token; bản thân loại cơ bản không nhất thiết có TTL/renewability. | Nếu cần, session manager có thể tra cứu `auth/token/lookup-self` để bổ sung thông tin. |
| `LoginToken` | Token có thông tin TTL/renewable từ phản hồi login. | Session manager có thể lên lịch renew mà không phải self-lookup lại chỉ để biết TTL ban đầu. |

Theo Javadoc Spring Vault, **self-lookup của `VaultToken` được bật mặc định** trong lifecycle-aware manager. `LoginToken` đã có thông tin từ login nên không cần self-lookup vì mục đích này.

Self-lookup có thể gọi `auth/token/lookup-self` và **tiêu tốn một lần sử dụng token** khi token có giới hạn `num_uses`. Nếu thiếu quyền self-lookup, Spring Vault có cơ chế bỏ qua gracefully và không thực hiện renewal dựa trên thông tin không có. Vì vậy nên kiểm tra rõ loại token và chính sách dự kiến, không giả định token static sẽ tự động có TTL.

### 3.2. Gia hạn được lên lịch như thế nào?

Khi token có lease duration, `ReactiveLifecycleAwareSessionManager` lên lịch gia hạn bất đồng bộ. **Mặc định hiện hành của Spring Vault là kích hoạt refresh khoảng 5 giây trước khi token hết hạn**, theo `LifecycleAwareSessionManagerSupport.REFRESH_PERIOD_BEFORE_EXPIRY` và refresh trigger mặc định.

Đây là hành vi thư viện theo phiên bản Javadoc, **không** phải yêu cầu Vault token luôn sống thêm 5 giây hay server renew bắt buộc trong 5 giây. Trong mạng chậm hoặc token TTL cực ngắn, cần cân nhắc một refresh trigger khác và dự phòng thời gian phù hợp.

~~~text
09:00  Vault cấp LoginToken: TTL 30 phút, renewable=true
       Session manager giữ token, phục vụ các yêu cầu Vault
       |
       v
09:29:55  Refresh trigger mặc định dự kiến chạy (~5 giây trước hạn)
       |
       +-- Renew thành công: Vault trả TTL thực tế mới, lên lịch lại
       |
       +-- Renew bị từ chối/hết hạn: manager bỏ trạng thái cũ;
       |   lần yêu cầu phiên tiếp theo cần login mới
       |
       +-- Lỗi mạng tạm thời: cần theo dõi/ứng xử theo LeaseStrategy
           và chính sách session đang áp dụng
~~~

**Đừng dùng timeline trên để hardcode lịch 5 giây ở code nghiệp vụ.** Công việc được scheduler quản lý theo token TTL và trigger. Các lần refresh thực tế chịu sai lệch lịch, thread scheduling, network latency, trạng thái Vault và giới hạn renewal.

### 3.3. Vault, không phải Reactor, quyết định TTL thực tế

Request renew self ở phía Vault có hình thức tương đương:

~~~http
POST /v1/auth/token/renew-self
X-Vault-Token: <CURRENT_TOKEN>
Content-Type: application/json

{"increment": "30m"}
~~~

`increment` là **thời lượng yêu cầu**, không có nghĩa Vault bắt buộc cấp đúng 30 phút. Vault áp dụng max TTL của server/auth mount/role, explicit max TTL, token type và các điều kiện khác. Ví dụ:

- Token bình thường được cấp TTL 30 phút lúc 09:00, max TTL hiệu lực 2 giờ.
- Renew lúc 10:40 xin thêm 60 phút, nhưng token chỉ còn tối đa khoảng 20 phút trước mốc tuổi đời 2 giờ.
- Vault có thể trả TTL ngắn hơn yêu cầu; ứng dụng phải dùng **TTL mới từ Vault** thay vì tự cộng 60 phút vào đồng hồ.

`renewable: true` có nghĩa **có thể thử renewal**, không bảo đảm renew mãi. Periodic service token có quy tắc riêng; batch token không hỗ trợ renew theo cách của service token. Token bị revoke hoặc hết hạn không thể cứu bằng cách retry `renew-self` vô hạn.

## 4. Thiết lập ReactiveVaultTemplate qua AbstractReactiveVaultConfiguration

Spring Vault cung cấp `AbstractReactiveVaultConfiguration` để cấu hình client, session manager và template dùng chung. Đây thường là cách đơn giản hơn tự lắp các constructor hoặc tự quản lý vòng đời token.

### 4.1. Ví dụ Java AppRole theo Spring Vault 4.1+

Ví dụ bên dưới dành cho **Java 17+ và Spring Vault 4.1+**. AppRole đã được bật ở Vault và cần có `roleId`, `secretId` được phân phối an toàn cho workload. Không commit chúng vào repository.

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractReactiveVaultConfiguration;

@Configuration(proxyBeanMethods = false)
public class ReactiveVaultConfig extends AbstractReactiveVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
                URI.create("https://vault.internal.example:8200"));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = getEnvironment().getRequiredProperty("VAULT_ROLE_ID");
        String secretId = getEnvironment().getRequiredProperty("VAULT_SECRET_ID");

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .roleId(RoleId.provided(roleId))
                        .secretId(SecretId.provided(secretId))
                        .build();

        return new AppRoleAuthentication(options, vaultClient());
    }
}
~~~

**Cần lưu ý các điểm sau:**

1. `AbstractReactiveVaultConfiguration` tạo bean `reactiveSessionManager()` cùng `reactiveVaultTemplate()` theo cấu hình.
2. Phương thức `clientAuthentication()` ở đây trả một object vừa implement `ClientAuthentication` vừa implement **`AuthenticationStepsFactory`**. `AppRoleAuthentication` hỗ trợ cả hai contract.
3. Reactive configuration dùng `AuthenticationSteps` của phương thức xác thực để thực hiện login **reactive**, chứ không đơn giản gọi phương thức blocking `ClientAuthentication.login()` trên event loop.
4. `vaultClient()` phục vụ phần cơ chế xác thực đồng bộ khi cần; reactive infrastructure tạo reactive client và token supplier theo cấu hình của chính nó.
5. `getEnvironment()` lấy cấu hình bootstrap. Trong production, `roleId`/`secretId` cần đến từ nguồn bí mật an toàn; biến môi trường là ví dụ minh họa, không phải giải pháp bảo mật hoàn chỉnh.
6. `VaultEndpoint` phải dùng HTTPS với xác thực CA/trust store đúng chuẩn. Ví dụ không cấu hình đầy đủ proxy, TLS, timeout hoặc Vault namespace; triển khai thực tế phải bổ sung.
7. Với Spring Cloud Vault/WebFlux, nên dùng auto-configuration tương thích nếu dự án đã có sẵn; **đừng tự định nghĩa session manager thứ hai** cho cùng client mà không có chủ đích.

Một phương thức xác thực chỉ triển khai `ClientAuthentication` nhưng **không** triển khai `AuthenticationStepsFactory` có thể không dùng được qua reactive configuration mặc định. Ví dụ một số tích hợp cloud yêu cầu SDK blocking; cần kiểm tra hỗ trợ reactive thực tế của auth method, không giả định chỉ vì có `WebClient` là toàn bộ login non-blocking.

### 4.2. Lifecycle của bean được framework quản lý

Khi template bean được tạo từ cấu hình Spring:

~~~text
AbstractReactiveVaultConfiguration
   -> VaultEndpoint / TLS / HTTP client
   -> AuthenticationStepsFactory / VaultTokenSupplier
   -> ReactiveLifecycleAwareSessionManager (ReactiveSessionManager)
   -> ReactiveVaultTemplate (ReactiveVaultOperations)
   -> Service dùng Mono/Flux
~~~

Phần quản lý token thuộc session manager; mã nghiệp vụ không nên tự gọi `auth/token/renew-self` song song với scheduler của manager. Nếu làm vậy, TTL mà các luồng theo dõi có thể mất đồng bộ.

## 5. Tự lắp manager khi cần kiểm soát sâu

Nếu ứng dụng không dùng `AbstractReactiveVaultConfiguration` hoặc cần cấu hình trigger/metrics riêng, Spring Vault 4.1+ có constructor:

~~~java
new ReactiveLifecycleAwareSessionManager(
        VaultTokenSupplier authentication,
        TaskScheduler taskScheduler,
        ReactiveVaultClient reactiveVaultClient);
~~~

Ví dụ thành phần lắp ghép (đã có `AuthenticationSteps` và các dependency tương ứng):

~~~java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsOperator;
import org.springframework.vault.authentication.ReactiveLifecycleAwareSessionManager;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.web.reactive.function.client.WebClient;

public final class ReactiveSessionSetup {

    public static ReactiveSessionManager create(
            AuthenticationSteps authenticationSteps,
            TaskScheduler scheduler,
            ReactiveVaultClient vaultClient,
            WebClient externalWebClient) {

        VaultTokenSupplier loginSupplier =
                new AuthenticationStepsOperator(
                        authenticationSteps, vaultClient, externalWebClient);

        ReactiveLifecycleAwareSessionManager manager =
                new ReactiveLifecycleAwareSessionManager(
                        loginSupplier, scheduler, vaultClient);

        manager.addErrorListener(event -> {
            // Tách login / renew / revoke error theo event type.
            // Không log event đầy đủ, token hoặc HTTP response body.
            String type = event.getClass().getSimpleName();
            String causeType = event.getException()
                    .getClass().getSimpleName();
            System.err.printf("Vault auth error: %s, %s%n",
                    type, causeType);
        });

        return manager;
    }
}
~~~

Điểm cần hiểu:

- `AuthenticationStepsOperator` là `VaultTokenSupplier` dùng **reactive HTTP**; request login thực hiện khi pipeline được subscribe.
- `TaskScheduler` chịu trách nhiệm kích hoạt các lần refresh theo lịch; đây là cơ chế scheduler **phục vụ lifecycle**, không phải lời khuyên gọi `Thread.sleep` trong reactive pipeline.
- `ReactiveVaultClient` là client **được cấu hình riêng cho Vault**; `WebClient` thứ hai dùng với các bước HTTP ngoài Vault khi auth flow cần.
- `ReactiveLifecycleAwareSessionManager` công bố event cho login/renew/revoke; callback nên nhẹ và chỉ ghi metadata không nhạy cảm.
- Khi dùng thủ công, phải nối **cùng manager** vào reactive template phù hợp với phiên bản thư viện, và để Spring quản lý `DisposableBean.destroy()`. Đoạn trên chỉ minh họa **lắp manager**, không phải toàn bộ bootstrap của ứng dụng.

Không tạo một manager mới **cho mỗi HTTP request**, vì khi đó token cache/renewal không thể được chia sẻ và dễ sinh nhiều token không được revoke đúng hạn. Một bean ứng dụng hoặc session scope phù hợp thường tái sử dụng manager cho các request.

### 5.1. Constructor WebClient và khác biệt phiên bản

Các phiên bản Spring Vault trước 4.1 có thể dùng:

~~~java
new ReactiveLifecycleAwareSessionManager(
        authenticationSupplier, scheduler, webClient);
~~~

Trong **4.1+**, constructor nhận `ReactiveVaultClient` cho Vault HTTP là lựa chọn mới; constructor nhận `WebClient` vẫn hiện diện trong Javadoc. `AuthenticationStepsOperator` cũng có constructor nhận `(AuthenticationSteps, ReactiveVaultClient, WebClient)` từ 4.1.

Không sao chép một constructor 4.1 vào dự án 3.x rồi kết luận API bị hỏng. Cần đối chiếu dependency được khóa bởi BOM và Javadoc đúng version đang chạy.

### 5.2. Tùy chỉnh token self-lookup và refresh trigger

`ReactiveLifecycleAwareSessionManager` kế thừa từ `LifecycleAwareSessionManagerSupport` nên có các cấu hình:

- `setTokenSelfLookupEnabled(boolean)`: bật/tắt self-lookup cho `VaultToken` (mặc định bật; `LoginToken` bỏ qua lookup này).
- `setLeaseStrategy(LeaseStrategy)`: điều khiển xử lý lỗi renewal theo chiến lược thư viện, khác với việc tự retry mọi request nghiệp vụ.
- Constructor nhận `LifecycleAwareSessionManagerSupport.RefreshTrigger`: thay đổi thời điểm kích hoạt refresh theo nhu cầu, đặc biệt khi muốn nhiều thời gian dự phòng hơn 5 giây.
- `addAuthenticationListener(...)`, `addErrorListener(...)`: quan sát sự kiện authentication.

Những cấu hình này phải được thiết lập **trước khi session manager bắt đầu được dùng rộng rãi**. Khi tùy chỉnh trigger hay chiến lược lỗi, hãy kiểm tra bằng test có Vault thật; một trigger chạy quá muộn có thể khiến token hết hạn trước khi renew.

## 6. Sử dụng ReactiveVaultOperations mà không chặn event loop

Khi các bean đã được cấu hình, mã nghiệp vụ nên phụ thuộc `ReactiveVaultOperations` thay vì tự lấy token và gọi `WebClient`.

### 6.1. Đọc KV v2 bằng Reactor Mono

~~~java
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentSecretService {

    private final ReactiveVaultOperations vault;

    public PaymentSecretService(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<String> loadGatewayUrl() {
        return vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("payments/config")
                .switchIfEmpty(Mono.error(new IllegalStateException(
                        "Không tìm thấy KV secret payments/config")))
                .map(this::requireGatewayUrl);
    }

    private String requireGatewayUrl(VaultResponse response) {
        Map<String, Object> data = response.getData();
        Object raw = data == null ? null : data.get("gateway-url");

        if (!(raw instanceof String value) || value.isBlank()) {
            throw new IllegalStateException(
                    "Secret thiếu gateway-url hợp lệ");
        }

        return value;
    }
}
~~~

Giải thích:

1. `opsForKeyValue("secret", KeyValueBackend.KV_2)` ánh xạ logical path `payments/config` sang API KV v2 tương ứng.
2. `get(...)` trả `Mono<VaultResponse>`; khi không tìm thấy path có thể trả `Mono.empty()`, do đó cần `switchIfEmpty(...)` nếu secret là bắt buộc.
3. `map(...)` kiểm tra dữ liệu theo kiểu, không cần `block()`.
4. `ReactiveVaultTemplate` gửi Vault token do session manager cung cấp, ứng dụng không cần tự gắn header `X-Vault-Token`.
5. Token phải có capability `read` trên **`secret/data/payments/config`** của KV v2. Login thành công không đồng nghĩa được đọc mọi secret.

Trong WebFlux handler, có thể trả trực tiếp `Mono<String>` hoặc chuyển kết quả thành DTO đáp ứng. **Không trả giá trị secret thật ra API công khai**; ví dụ URL chỉ là trường cấu hình không nhạy cảm. Nếu giá trị là password/API key, truyền an toàn cho consumer nội bộ và không ghi vào response hay log.

### 6.2. Tránh block và subscribe thủ công

~~~java
// Không nên thực hiện trong WebFlux handler:
String url = paymentSecretService.loadGatewayUrl().block();

// Cũng không nên tạo subscribe ẩn rồi trả response ngay:
paymentSecretService.loadGatewayUrl().subscribe();
~~~

`block()` giữ thread chờ và có thể gây lỗi khi chạy trên non-blocking event loop. `subscribe()` thủ công trong handler khiến việc xử lý lỗi, cancellation và vòng đời request không còn nằm trong pipeline do WebFlux quản lý.

Cách phù hợp là **trả Mono/Flux** cho framework, hoặc dùng `flatMap` / `map` để tiếp tục xử lý. Với một API không hỗ trợ reactive và bắt buộc blocking, cần cô lập trên scheduler dành cho blocking I/O sau khi đánh giá tác động; không đánh đồng việc “đặt vào Mono” với non-blocking.

### 6.3. Lưu ý khi retry tác vụ nghiệp vụ

`Mono.retry(...)` hoặc `retryWhen(...)` có thể **subscribe lại** pipeline, tạo thêm HTTP request. Với thao tác đọc KV có thể cân nhắc retry lỗi tạm thời có giới hạn; với `write`, Transit hoặc PKI, cần xem endpoint có idempotent hay không trước khi tự động retry.

Không dùng `retryWhen(Retry.indefinitely())` để “đảm bảo token được gia hạn”. Nếu token mất quyền ACL, bị revoke hoặc role không còn cho login, retry vô hạn sẽ tạo tải không cần thiết và che giấu lỗi cấu hình.

## 7. Gia hạn bị lỗi: mô hình xử lý và xác thực lại

Reactive session manager có thể nhận lỗi ở ba giai đoạn:

1. **Login lỗi**: workload credential sai/hết hiệu lực, role bị xóa hoặc Vault không sẵn sàng.
2. **Renew lỗi**: token bị revoke, hết TTL, thiếu permission, chạm max TTL hoặc mạng/server lỗi.
3. **Revoke lỗi**: khi manager kết thúc phiên nhưng yêu cầu thu hồi bị từ chối/không gửi được.

Theo Javadoc Spring Vault, nếu renewal gặp **lỗi phía client như permission denied**, manager xem token cũ như đã hết hiệu lực/revoke và **loại bỏ trạng thái token**, để lần cần phiên tiếp theo thử đăng nhập mới. Không có cam kết rằng lỗi nào cũng được tự khắc phục: khi workload identity hoặc Vault policy bị hỏng, login mới cũng có thể thất bại.

~~~mermaid
flowchart TD
    A[ReactiveVaultOperations cần session] --> B{Đang có token hợp lệ?}
    B -->|Chưa| C[Reactive auth flow lấy token mới]
    C --> D{Login thành công?}
    D -->|Không| E[Mono error, quan sát và fail có kiểm soát]
    D -->|Có| F[Cache token + tính TTL]
    B -->|Có| F
    F --> G[Vault API trả kết quả theo ACL]
    F --> H[Scheduler đến thời điểm renew]
    H --> I{Renew thành công?}
    I -->|Có| J[Nhận TTL thực tế, lập lịch lại]
    J --> F
    I -->|Không, token bị từ chối| K[Loại trạng thái token cũ]
    K --> C
    I -->|Lỗi tạm thời| L[Xử lý theo LeaseStrategy và thời hạn]
    L --> H
~~~

Đây là **mô hình giải thích**, không phải máy trạng thái public API. Khi nào sự kiện được phát và token được tái cấp phụ thuộc loại lỗi, token, refresh trigger và implementation đang chạy.

### 7.1. Khác biệt giữa lỗi xác thực và lỗi quyền secret

| Lỗi | Tầng gặp lỗi | Nhận định và phản ứng |
| --- | --- | --- |
| `auth/token/renew-self` trả 403 | Session renewal. | Kiểm tra token còn hợp lệ, capability renew và max TTL; manager có thể cần login lại. |
| `auth/approle/login` trả 403 | Workload login. | RoleId/SecretId sai hoặc hết hạn, role/policy sai; phải khắc phục credential/role. |
| `secret/data/payments/config` trả 403 | KV ACL. | Token có thể còn hợp lệ nhưng không có quyền đọc path; renew token **không** cấp thêm quyền. |
| `auth/token/lookup-self` trả 403 | Token metadata lookup. | Thiếu quyền lookup hoặc token hỏng; không kết luận mọi API Vault khác đều bị cấm. |
| Timeout/502/503 khi renew | Network/Vault availability. | Có thể transient; phân biệt với token revoke, tránh retry storm. |
| Login thành công, dynamic credential DB hết hạn | Secret lease lifecycle. | Cần xử lý lease/rotation riêng; không chỉ renew session token. |

### 7.2. Không tự renew đồng thời từ code nghiệp vụ

`ReactiveLifecycleAwareSessionManager` có public method `renewToken(): Mono<VaultToken>` và `revoke(): Mono<Void>`. Chúng phục vụ lifecycle và các tình huống quản trị có chủ đích, **không** nên được gọi từ mọi HTTP request.

Ví dụ để quan sát renew **trong lab**, với manager đã được tạo:

~~~java
Mono<String> result = manager.renewToken()
        .map(token -> "Gia hạn hoặc lấy token thành công")
        .switchIfEmpty(Mono.just("Không có token mới để báo cáo"))
        .onErrorResume(error ->
                Mono.just("Gia hạn bị từ chối hoặc thất bại"));
~~~

Đây là snippet minh họa cách xử lý trạng thái **mà không in token**, không phải đề xuất tự quản lý renewal bên ngoài scheduler. Trong production, để manager làm chủ lifecycle và dùng authentication event để giám sát.

Nếu nhiều thành phần cùng cố renew và re-login, chúng có thể cập nhật state không đồng bộ và tạo race với background refresh.

## 8. Authentication event và quan sát lỗi

`ReactiveLifecycleAwareSessionManager` phát authentication events. Có thể đăng ký:

- `addAuthenticationListener(...)`: sự kiện login/renew/revoke theo API.
- `addErrorListener(...)`: `AuthenticationErrorEvent` và subtype như `LoginFailedEvent`, `LoginTokenRenewalFailedEvent`, `LoginTokenRevocationFailedEvent`.
- `AuthenticationErrorEvent.getException()`: nguyên nhân, nhưng **không được log toàn bộ message/stack trace** nếu có nguy cơ chứa thông tin nhạy cảm.

Ví dụ listener tối thiểu trong cấu hình, trước khi manager bắt đầu được dùng:

~~~java
manager.addErrorListener(event -> {
    String eventType = event.getClass().getSimpleName();
    String failureType = event.getException()
            .getClass().getSimpleName();

    // Chỉ log nhãn loại lỗi, không log token/response body.
    metrics.recordAuthFailure(eventType, failureType);
});

manager.addAuthenticationListener(event -> {
    metrics.recordAuthenticationEvent(
            event.getClass().getSimpleName());
});
~~~

Đoạn trên giả định `metrics` là một abstraction của ứng dụng đã được cấu hình; tên class/event được giữ làm nhãn có cardinality thấp. Callback có thể được phát trên thread request hoặc background scheduler: không thực hiện I/O blocking lâu trong listener.

### 8.1. Những metric có ích

| Metric gợi ý | Ý nghĩa | Không nên gắn nhãn |
| --- | --- | --- |
| `vault_auth_login_success_total` | Số lần login thành công theo auth method. | JWT, SecretID, Vault token. |
| `vault_auth_login_failed_total` | Số lần login lỗi theo nhóm nguyên nhân. | Raw exception message hoặc body. |
| `vault_token_renew_success_total` | Số lần renewal thành công. | Client token, token accessor. |
| `vault_token_renew_failed_total` | Renewal bị lỗi/không còn gia hạn được. | Raw lease ID, token. |
| `vault_token_ttl_seconds` | TTL hiện tại hoặc TTL được báo gần nhất theo nguồn đáng tin. | Giá trị credential. |
| `vault_relogin_total` | Tần suất re-login; tăng đột biến có thể là dấu hiệu mất phiên. | Danh tính workload chi tiết không cần thiết. |

Không phải metric nào cũng được Spring Vault xuất sẵn; bảng này là **đề xuất quan sát của ứng dụng**. Cần tránh đếm trùng cùng một sự kiện ở cả callback và filter HTTP nếu sử dụng cả hai nguồn telemetry.

### 8.2. Tránh lộ token trên Reactor hooks

Những nơi có nguy cơ tiết lộ credential:

- `log()` trên `Mono<VaultToken>` hoặc toàn bộ response login.
- `doOnNext(token -> logger.info("{}", token))`.
- Logging request header `X-Vault-Token` ở `WebClient` filter hoặc reverse proxy.
- Reactor context/tracing baggage vô tình mang JWT, Token, AppRole SecretID.
- `onErrorResume` tạo exception chứa raw HTTP request/response body.

Chỉ ghi metric/trace với operation, endpoint đã chuẩn hóa, mã trạng thái, TTL dạng số và loại exception đã lọc an toàn. Không chia sẻ token qua log, Java exception, HTTP response hoặc metric tag.

## 9. Shutdown và revoke: khi nào Spring Vault thu hồi token?

`ReactiveLifecycleAwareSessionManager` implement `DisposableBean`. Khi kết thúc phiên, manager có thể thu hồi **`LoginToken`** do login-based authentication cấp (khi đó là **service token**), đồng thời dừng lịch gia hạn. `VaultToken` tĩnh không được Spring Vault tự thu hồi giống `LoginToken`.

| Loại token | Khi session manager dừng | Cần lưu ý |
| --- | --- | --- |
| `LoginToken` service token do auth method cấp | Có thể được revoke theo lifecycle khi manager bị destroy. | Shutdown phải có đủ thời gian và kết nối để gửi revoke. |
| `VaultToken` được cung cấp sẵn | Không tự revoke bởi lifecycle manager theo quy tắc của thư viện. | Chủ sở hữu token cần quy trình rotation/revoke độc lập. |
| Batch token | Không hỗ trợ renewal như service token; không áp dụng lifecycle revoke giống service token. | Dùng TTL/phương thức xác thực phù hợp. |
| Dynamic secret lease | Được quản lý qua secret lease mechanism. | Thu hồi token cha có thể dẫn đến revoke lease liên quan. |

Spring Vault có `revoke(): Mono<Void>` cho yêu cầu revoke theo API; `revokeNow()` là lời gọi đồng bộ/blocking dùng trong quy trình giải phóng tài nguyên, **không đặt nó trên WebFlux event loop**.

Khi deploy Rolling Update, cần đánh giá tương quan giữa token cũ, secret lease, thời gian shutdown grace và các connection còn đang xử lý. Không giả định mọi Vault revoke request đều thành công nếu pod bị kill ngay sau khi gửi signal.

## 10. Phân biệt token session với dynamic secret lease

Điều quan trọng của module Spring Vault là quản lý **hai vòng đời** độc lập:

| Đối tượng | TTL đọc ở đâu | Gia hạn hoặc thay mới | Ảnh hưởng đến ứng dụng |
| --- | --- | --- | --- |
| Vault session token | `auth.lease_duration` khi login, `auth/token/lookup-self` trả `data.ttl`. | `ReactiveLifecycleAwareSessionManager`, `auth/token/renew-self`, re-login. | Cho phép các request Vault API hoạt động. |
| Database dynamic credential | `lease_id`, `lease_duration`, `renewable` của response `database/creds/...`. | Secret lease renewal/rotation, `SecretLeaseContainer` hoặc cơ chế tương thích. | JDBC pool/client phải thay username/password khi credential đổi. |
| KV v2 secret tĩnh | Không có dynamic lease renew theo cách database creds. | Ghi phiên bản KV mới hoặc refresh theo chính sách ứng dụng. | Cấu hình/credential cần reload theo nghiệp vụ. |
| Chứng chỉ PKI | TTL/lease và hiệu lực X.509 riêng. | Xin lại cert/rotate key theo chính sách PKI. | TLS handshake dùng certificate còn hiệu lực. |

**Không có lớp `ReactiveSessionManager` nào tự đảm bảo database password vừa bị rotate được nạp vào Hikari pool**. Với nhiều thành phần Spring Vault, `SecretLeaseContainer` quản lý lease của secret động và có sự kiện rotation; nếu dùng với reactive application, phải xét phần nào là blocking và phối hợp qua adapter/scheduler hợp lý.

Nếu token đã bị thu hồi, các lease liên kết có thể bị thu hồi theo. Khi manager re-login thành công, ứng dụng phải bảo đảm credential cũ không còn phụ thuộc vào token trước đó và nạp lại secret nếu cần.

## 11. Kiểm thử reactive session và renewal

Để kiểm chứng hành vi, nên chia thành **unit test reactive flow** và **integration test Vault server**. Không chạy production auth với root token chỉ để test.

### 11.1. Unit test: lazy token supplier

Một `VaultTokenSupplier` dùng `Mono.defer` để biểu diễn việc chỉ tính nguồn khi subscribe:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;

AtomicInteger created = new AtomicInteger();

VaultTokenSupplier supplier = () -> Mono.defer(() -> {
    created.incrementAndGet();
    return Mono.just(VaultToken.of("unit-test-only-not-a-real-token"));
});

// Chưa subscribe: chưa thực thi Supplier.
if (created.get() != 0) {
    throw new AssertionError("Supplier được chạy quá sớm");
}

StepVerifier.create(supplier.getVaultToken())
        .expectNextCount(1)
        .verifyComplete();

if (created.get() != 1) {
    throw new AssertionError("Supplier không được chạy đúng thời điểm");
}
~~~

Đây là **test contract của supplier**, chưa chứng minh session manager có caching hoặc renewable. `reactor-test` là dependency phục vụ test, không cần trong runtime ứng dụng.

### 11.2. Integration test với Vault thật

Dùng Vault test cô lập (ví dụ Testcontainers nếu phù hợp), một workload role có TTL ngắn nhưng còn đủ thời gian cho scheduler và network, policy tối thiểu và một KV v2 secret.

| Kịch bản | Thiết lập | Điều cần xác minh |
| --- | --- | --- |
| Login lần đầu | Chưa có token, nhiều `Mono` cùng cần Vault. | Login được điều phối, không nhân bản vô hạn token khi concurrent. |
| Tái sử dụng phiên | Gọi hai lần đọc KV trong một khoảng TTL hợp lệ. | Không login trên **mỗi** request; đọc thành công bằng session manager. |
| Token renewable | Service token có TTL/permission renew. | Sự kiện renewal, TTL mới và request sau renew thành công. |
| Đã chạm max TTL | Token thường gần giới hạn tuổi đời. | Renew không kéo dài được; manager xử lý mất phiên và có thể login lại. |
| Token không renewable | Token false/batch. | Không cố renew liên tục; cấp token mới theo cơ chế auth khi cần. |
| Token bị revoke | Revoke token ở Vault trong test. | API sau đó gặp auth error; nếu auth method còn dùng được thì lần tiếp theo có thể re-login. |
| Thiếu quyền KV | Token login hợp lệ nhưng không có `read` trên path. | KV 403; **không** tự coi là lỗi phải renew token. |
| Self-lookup không được cấp quyền | Token dạng `VaultToken` nhưng ACL chặn lookup-self. | Graceful fallback theo behavior thư viện; không mặc định có token TTL. |
| Vault tạm thời unavailable | Tạm chặn kết nối trong môi trường test. | Mono error và authentication error event; phục hồi có retry/backoff hợp lý. |
| Shutdown | Session manager bị destroy dưới Spring context. | Kiểm tra quy trình revoke `LoginToken` và không chặn event loop. |

**Chú ý test thời gian:** Reactor `VirtualTimeScheduler` không tự điều khiển `TaskScheduler` của Spring. Nếu muốn unit test deterministic cho lịch renewal, cần fake/test scheduler phù hợp; không giả định chỉ dùng `StepVerifier.withVirtualTime` là đã điều khiển được toàn bộ timer của session manager.

### 11.3. Bài tập tình huống

**Tình huống A.** Một ứng dụng tạo mới `ReactiveLifecycleAwareSessionManager` cho mỗi WebFlux request. Các request đến đồng thời và tạo hàng trăm token. Sai ở đâu?

**Đáp án:** Session manager phải được chia sẻ theo vòng đời ứng dụng/phiên thích hợp. Tạo manager per request phá cache/coalescing và có thể tạo dư token, lịch renew và các revoke khó kiểm soát.

**Tình huống B.** `renewable=true` và token sống 30 phút. 5 giây trước khi hết hạn, Spring Vault gửi renew, Vault chỉ gia hạn thêm 10 giây. Có được giả định session sống thêm 30 phút?

**Đáp án:** Không. Vault quyết định TTL thực tế; renew có thể bị max TTL/explicit max TTL chặn. Manager phải dùng kết quả thực tế và chuẩn bị re-login khi token không còn renew được.

**Tình huống C.** WebFlux handler gọi `reactiveVaultOperations.read(...).block()` để “đợi chắc có secret”. Đây có phải cách dùng ReactiveSessionManager đúng?

**Đáp án:** Không. `block()` chặn event loop và phá ưu điểm reactive. Hãy trả `Mono`/`Flux` hoặc phối hợp với `flatMap`, và để template/session manager cung cấp token khi subscribe.

**Tình huống D.** Sau khi login lại, `ReactiveVaultOperations` đọc KV được, nhưng connection pool database tiếp tục thất bại với credential cũ. Vì sao?

**Đáp án:** Đăng nhập lại chỉ thay **Vault session token**. Database credential là secret có **lease riêng**, phải được xin mới/rotate và áp dụng vào connection pool đang chạy.

**Tình huống E.** `CachingVaultTokenSupplier` đã giữ token. Có thể thay `ReactiveLifecycleAwareSessionManager` và kỳ vọng renewal tự động không?

**Đáp án:** Không. Cache chỉ lưu token; muốn TTL-aware renewal/re-login cần lifecycle manager hoặc cơ chế tương đương. Token cache lâu quá hạn có thể gây 403.

**Tình huống F.** Tất cả request KV đều trả 403 vì policy không cấp `read`, nhóm phát triển thêm retry và ép renew. Liệu có sửa được?

**Đáp án:** Không. Đây là vấn đề ACL trên API path, không phải chắc chắn token hết hạn. Cần sửa policy/role/path theo quyền tối thiểu, không đổi token liên tục để che lỗi.

## 12. Tổng kết và tài liệu chính thức

- **`ReactiveSessionManager`** là contract quản lý phiên cho `ReactiveVaultTemplate`; `VaultTokenSupplier` cung cấp `Mono<VaultToken>`.
- **`ReactiveLifecycleAwareSessionManager`** có cache/điều phối concurrent login, **renew bất đồng bộ** và xử lý re-login khi token không còn dùng được theo điều kiện.
- `LoginToken` mang TTL/renewability; `VaultToken` cơ bản có thể cần `lookup-self` (mặc định bật), nhưng self-lookup cũng tiêu hao lượt dùng token và phụ thuộc ACL.
- Refresh trigger mặc định của Spring Vault thực hiện khoảng **5 giây trước khi token hết hạn**; trong môi trường chậm có thể cần trigger phù hợp hơn. **Vault luôn quyết định TTL và max TTL** cuối cùng.
- `AbstractReactiveVaultConfiguration` kết nối authentication steps, reactive session manager và template; không nhất thiết phải tự viết token caching/renewal.
- Với Spring Vault **4.1+**, `AuthenticationStepsOperator` và `ReactiveLifecycleAwareSessionManager` hỗ trợ `ReactiveVaultClient` trong constructor; dự án phiên bản cũ cần đối chiếu Javadoc.
- **Đừng `block()` hoặc tự `subscribe()` trong handler**. Hãy trả `Mono`/`Flux`, dùng retry có giới hạn và chỉ cho lỗi tạm thời.
- **Token renewal khác secret lease renewal**. Nếu database credential hoặc chứng chỉ thay đổi, consumer phải có cơ chế rotation riêng.
- Không log bearer token, JWT, AppRole SecretID hoặc HTTP response nhạy cảm; kiểm thử với workload token và policy tối thiểu.

Nguồn tài liệu chính thức:

1. [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html): reactive client, template, session management.
2. [Spring Vault – Authentication Methods và Token Lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html): LoginToken, renewal và authentication steps.
3. [Spring Vault – ReactiveSessionManager Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveSessionManager.html): contract reactive session.
4. [Spring Vault – ReactiveLifecycleAwareSessionManager Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html): caching, concurrency, renew, revoke, error handling.
5. [Spring Vault – LifecycleAwareSessionManagerSupport Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManagerSupport.html): refresh trigger, self-lookup, lease strategy.
6. [Spring Vault – AbstractReactiveVaultConfiguration Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractReactiveVaultConfiguration.html): cấu hình session manager và reactive template.
7. [Spring Vault – AuthenticationStepsOperator Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationStepsOperator.html): reactive login flow và VaultTokenSupplier.
8. [HashiCorp Vault – Tokens](https://developer.hashicorp.com/vault/docs/concepts/tokens): TTL, max TTL, renewability và token types.

Hiểu đúng ranh giới giữa **reactive token supplier**, **session manager**, **Vault server TTL** và **lease của secrets** giúp ứng dụng Spring Vault tránh đăng nhập lặp, gia hạn không đúng lúc, làm nghẽn event loop và sử dụng credential đã hết hạn.
