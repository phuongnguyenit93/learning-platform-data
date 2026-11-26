# VaultTokenSupplier và việc cấp token không chặn

## 1. Vai trò của token trong API reactive

Ứng dụng Java dùng **Spring Vault** phải có một **Vault token** hợp lệ trước khi gọi HashiCorp Vault để đọc KV secrets, thực hiện Transit encryption/decryption, yêu cầu chứng thư PKI hoặc truy cập dynamic credentials. Trong lập trình đồng bộ, `VaultTemplate` sử dụng `SessionManager` cùng `ClientAuthentication`; một lần gọi login bằng HTTP có thể giữ thread đang thực thi cho đến khi Vault phản hồi.

Với ứng dụng WebFlux/Reactor, ta cần một cách **cấp token phù hợp với luồng bất đồng bộ**. Spring Vault cung cấp interface `VaultTokenSupplier` trong package `org.springframework.vault.authentication`. Hợp đồng chỉ có một phương thức:

~~~java
@FunctionalInterface
public interface VaultTokenSupplier {
    Mono<VaultToken> getVaultToken();
}
~~~

`Mono<VaultToken>` mô tả việc cung cấp **không quá một token** hoặc phát tín hiệu lỗi. Token có thể là giá trị đã biết, hoặc được nhận từ một luồng xác thực workload như AppRole, Kubernetes, JWT hoặc cloud identity. Điểm khác biệt quan trọng: **API trả `Mono` không tự bảo đảm mọi thao tác bên trong đều non-blocking**; việc cấp token không chặn còn phụ thuộc cách triển khai supplier, HTTP client, đọc credential và scheduler.

Bài thuộc chương **API reactive**, tập trung vào `VaultTokenSupplier` và cách đưa token vào `ReactiveVaultTemplate`, đồng thời liên hệ với chủ đề của module **SPRING_VAULT**: xác thực workload, Vault ACL, vòng đời token/lease, KV v2, Transit, PKI, giám sát và kiểm thử tích hợp.

Mục tiêu là phân biệt hợp đồng cấp token và quản lý phiên, xây dựng flow AppRole, đọc KV v2 qua WebFlux và kiểm thử tính lazy, đồng thời, TTL cũng như lỗi ACL.

## 2. Hợp đồng `VaultTokenSupplier`: nhỏ nhưng quyết định kiến trúc

| Thành phần | Đầu vào | Đầu ra | Trách nhiệm |
| --- | --- | --- | --- |
| `ClientAuthentication` | Cấu hình auth method đồng bộ | `VaultToken login()` | Đăng nhập đồng bộ, dùng cho hạ tầng imperative. |
| `AuthenticationSteps` | Nguồn credential, các bước biến đổi, endpoint login | Mô tả flow | **Khai báo**, chưa thực thi HTTP. |
| `AuthenticationStepsOperator` | Steps và reactive client | `Mono<VaultToken>` | Thực thi flow xác thực qua reactive pipeline. |
| `VaultTokenSupplier` | Không có tham số phương thức | `Mono<VaultToken>` | Hợp đồng cấp token, chưa quyết định caching. |
| `CachingVaultTokenSupplier` | Supplier khác | `Mono<VaultToken>` | Cache kết quả token cho use case được quản lý bên ngoài. |
| `ReactiveSessionManager` | Supplier và logic phiên | `getSessionToken(): Mono<VaultToken>` | Trừu tượng hóa token cho request Vault reactive. |
| `ReactiveLifecycleAwareSessionManager` | Supplier, scheduler, Vault client | Token có quản lý lifecycle | Tái sử dụng, renew, login lại và revoke theo điều kiện. |
| `ReactiveVaultTemplate` | Endpoint/HTTP client và token supplier | `Mono`/`Flux` cho Vault API | Thực hiện request có xác thực tới secrets engine. |

Theo API, `ReactiveSessionManager` kế thừa `VaultTokenSupplier`, bổ sung `getSessionToken()`; `AuthenticationStepsOperator` chưa phải bộ quản lý phiên.

Ví dụ một supplier đơn giản cho unit test:

~~~java
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;

VaultTokenSupplier stub = () ->
    Mono.just(VaultToken.of("fixture-token-only"));
~~~

Đây là token giả. `VaultToken.of(...)` chỉ bọc chuỗi, **không xác minh** TTL hoặc policy tại Vault.

### Sự khác biệt giữa “cấp token” và “quản lý phiên”

`VaultTokenSupplier.getVaultToken()` có thể phát token mới sau mỗi subscription. Ngược lại, `ReactiveLifecycleAwareSessionManager` dùng supplier làm **nguồn đăng nhập**, nhưng giữ trạng thái phiên và phối hợp các request đồng thời để tránh nhiều login không cần thiết. Nếu không đặt lớp quản lý phiên, một hệ thống có 200 request đồng thời có thể gửi 200 request đăng nhập thay vì dùng token đã có.

Supplier không cấp quyền: Vault ACL vẫn kiểm tra riêng từng path KV v2, Transit hoặc PKI.

## 3. Reactive, lazy và non-blocking không phải một khái niệm

Ba thuộc tính cần tách rõ:

1. **Reactive return type:** một hàm trả `Mono<VaultToken>`; caller có thể ghép toán tử `map`, `flatMap`, `timeout`, `onErrorResume`, `retryWhen`.
2. **Lazy execution:** Publisher chỉ bắt đầu thực hiện tác vụ khi có subscription. Khởi tạo `AuthenticationSteps` hoặc lưu `Mono` chưa đồng nghĩa đã gửi HTTP login.
3. **Non-blocking I/O:** HTTP request sử dụng client bất đồng bộ, không giữ thread xử lý sự kiện chờ socket trả lời. Một `Supplier` tùy ý hoặc `Thread.sleep()` vẫn có thể blocking nếu thực thi sai scheduler.

~~~mermaid
sequenceDiagram
    participant H as WebFlux handler
    participant M as ReactiveSessionManager
    participant S as VaultTokenSupplier
    participant V as Vault auth endpoint
    participant KV as KV v2 endpoint
    H->>M: Tạo publisher để đọc secret
    Note over H,M: Chưa subscribe: chưa chạy HTTP
    H->>M: Subscribe
    M->>S: Lấy token nếu chưa có token hợp lệ
    S->>V: Non-blocking login HTTP
    V-->>S: Vault token T1
    S-->>M: Mono<VaultToken> phát T1
    M-->>H: Token sẵn sàng
    H->>KV: Gọi endpoint với T1
    KV-->>H: Secret hoặc lỗi ACL
    Note over H,KV: Request sau có thể tái sử dụng T1
~~~

Với `AuthenticationStepsOperator`, login chạy khi subscribe, và kết quả/lỗi được phát qua `Mono`; non-blocking không đồng nghĩa có một thread riêng cho mỗi login.

### Ví dụ: lazy và side effect

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;

AtomicInteger executions = new AtomicInteger();
VaultTokenSupplier supplier = () ->
    Mono.fromSupplier(() -> {
        executions.incrementAndGet();
        return VaultToken.of("only-a-test-value");
    });

Mono<VaultToken> tokenFlow = supplier.getVaultToken();
// Tại đây executions vẫn bằng 0.
// Mỗi subscription trực tiếp lên tokenFlow sẽ chạy Supplier thêm lần nữa.
~~~

`Mono.fromSupplier` vẫn có thể block thread nếu lambda làm I/O đồng bộ. Hãy dùng API non-blocking hoặc offload có giới hạn.

### Không `.block()` trong WebFlux request

~~~java
// Không nên làm trong handler reactive:
VaultToken token = supplier.getVaultToken().block();
~~~

Lệnh `.block()` chuyển một flow reactive thành thao tác đồng bộ; trên event-loop thread của WebFlux có thể gây lỗi hoặc giữ thread, làm giảm throughput. Hãy **return `Mono`** hoặc dùng `flatMap` để tiếp tục. Không gọi `.subscribe()` thủ công trong controller chỉ để kích hoạt login, vì subscription tách khỏi lifecycle của HTTP request và có thể làm mất tín hiệu hủy/lỗi.

## 4. Cách Spring Vault tạo supplier từ authentication steps

`AuthenticationSteps` là DSL khai báo nguồn credential, bước biến đổi và bước cuối gửi login request đến Vault. Ví dụ AppRole dùng `role_id` và `secret_id`; thông tin được cấp qua nguồn an toàn (không hardcode).

~~~java
import java.util.Map;
import java.util.function.Supplier;
import org.springframework.vault.authentication.AuthenticationSteps;

public final class AppRoleLoginSteps {

    public static AuthenticationSteps create(
            Supplier<String> roleId,
            Supplier<String> secretId) {

        return AuthenticationSteps.fromSupplier(() ->
                Map.of(
                    "role_id", roleId.get(),
                    "secret_id", secretId.get()))
            .login("auth/{mount}/login", "approle");
    }
}
~~~

Phương thức `.login("auth/{mount}/login", "approle")` thực hiện POST đến Vault API `auth/approle/login` khi executor/operator chạy. Thay `approle` bằng mount thực tế nếu quản trị viên đặt đường dẫn khác. `Map.of` không chấp nhận `null`; nguồn credential phải trả về hai chuỗi đã được cấp hợp lệ.

Tạo `AuthenticationStepsOperator`:

~~~java
import java.util.function.Supplier;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsOperator;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.web.reactive.function.client.WebClient;

public final class AppRoleTokenSuppliers {
    public static VaultTokenSupplier create(
            WebClient vaultAuthClient,
            Supplier<String> roleId,
            Supplier<String> secretId) {

        AuthenticationSteps steps = AppRoleLoginSteps.create(roleId, secretId);
        return new AuthenticationStepsOperator(steps, vaultAuthClient);
    }
}
~~~

`vaultAuthClient` cần HTTPS, base path `/v1/`, TLS trust và timeout đúng; ưu tiên dùng cấu hình HTTP client sẵn có của Spring Vault.

Ở Spring Vault 4.1, `AuthenticationStepsOperator` còn có constructor với `ReactiveVaultClient` và `WebClient`, tách Vault API request khỏi HTTP request đến hệ thống bên ngoài. `AuthenticationStepsOperator` tự xử lý các `ResourceCredentialSupplier` qua I/O bất đồng bộ khi phù hợp và offload các supplier tổng quát; tuy vậy ứng dụng vẫn phải tránh truy vấn blocking nặng hoặc đọc secret từ nguồn không tin cậy.

**Không tự tạo login flow nếu auth method đã hỗ trợ sẵn.** Các loại `ClientAuthentication` có triển khai `AuthenticationStepsFactory` hoặc factory tĩnh để dựng steps theo options, ví dụ AppRole, Kubernetes và một số cloud/workload auth. Dùng factory được hỗ trợ giúp xử lý trường hợp JWT có audience, role mount tùy chỉnh, wrapping hoặc các bước lấy identity phức tạp.

## 5. Từ `VaultTokenSupplier` đến session manager và template

Mỗi lần đăng nhập tạo token mới không phải giải pháp ổn định cho một dịch vụ. Sau khi có supplier, ứng dụng nên đưa nó vào `ReactiveLifecycleAwareSessionManager` để tái sử dụng token và quản lý TTL. Session manager lấy token theo nhu cầu, phối hợp các request cùng lúc, lập lịch renew hoặc re-login theo loại token.

Mã cấu hình minh họa dưới đây dùng Spring Vault, Reactor Netty và một bean `AppRoleCredentialSource` do môi trường triển khai cung cấp. Không được sao chép RoleID/SecretID thật vào mã hoặc log.

~~~java
import java.net.URI;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.authentication.*;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.ReactiveVaultTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveVaultLoginConfig {

    public interface AppRoleCredentialSource {
        String roleId();
        String secretId();
    }

    @Bean("vaultAuthWebClient")
    WebClient vaultAuthWebClient() {
        return WebClient.builder()
            .baseUrl("https://vault.example.org:8200/v1/")
            .build();
    }

    @Bean("vaultTokenSupplier")
    VaultTokenSupplier vaultTokenSupplier(
            AppRoleCredentialSource credentials,
            @Qualifier("vaultAuthWebClient") WebClient webClient) {

        return AppRoleTokenSuppliers.create(
            webClient, credentials::roleId, credentials::secretId);
    }

    @Bean
    ThreadPoolTaskScheduler vaultTokenScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-token-");
        return scheduler; // Spring quản lý initialize và shutdown.
    }

    @Bean
    ReactiveSessionManager reactiveSessionManager(
            @Qualifier("vaultTokenSupplier") VaultTokenSupplier supplier,
            ThreadPoolTaskScheduler vaultTokenScheduler,
            @Qualifier("vaultAuthWebClient") WebClient webClient) {

        return new ReactiveLifecycleAwareSessionManager(
            supplier, vaultTokenScheduler, webClient);
    }

    @Bean
    ReactiveVaultOperations reactiveVaultOperations(
            ReactiveSessionManager sessionManager) {

        VaultEndpoint endpoint = VaultEndpoint.from(
            URI.create("https://vault.example.org:8200"));
        return new ReactiveVaultTemplate(
            endpoint, new ReactorClientHttpConnector(), sessionManager);
    }
}
~~~

Đây là cấu hình dành cho **lab**, chưa bao gồm bean hiện thực `AppRoleCredentialSource`, custom CA/truststore, retry/circuit breaker, Vault Enterprise namespace hoặc điều phối readiness. Cần cấu hình cùng TLS/endpoint nhất quán cho **login client** và **secret client**, đóng session manager đúng vòng đời và xác minh API theo version Spring Vault của dự án.

### Tại sao không dùng `CachingVaultTokenSupplier` ở mọi nơi?

`CachingVaultTokenSupplier.of(delegate)` lưu token, nhưng không tự bảo đảm renew/re-login/revoke. Cache token đã hết TTL sẽ gây lỗi; tránh chồng cache thủ công lên lifecycle-aware session manager.

Với token do Vault Agent xoay ở ngoài ứng dụng, xác định rõ ai cấp mới và ai revoke; `VaultTokenSupplier` không tự cam kết rotation.

## 6. Đọc KV v2 qua `ReactiveVaultTemplate` mà không block

Giả định Vault đã mount KV v2 tại `secret/`, key `apps/orders/config` có field `endpoint`, và AppRole có policy:

~~~hcl
path "secret/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Với KV v2, `secret/data/apps/orders/config` là **API path** cần ghi trong ACL. Lúc gọi `opsForVersionedKeyValue("secret").get("apps/orders/config")`, Spring Vault tự chèn phần `data/`; **không** đưa `secret/data/` vào chuỗi key tương đối.

Một service WebFlux có thể trả về `Mono<String>`:

~~~java
import java.util.Map;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.Versioned;
import reactor.core.publisher.Mono;

public final class OrdersSecrets {
    private final ReactiveVaultOperations vault;

    public OrdersSecrets(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<String> loadEndpoint() {
        return vault.opsForVersionedKeyValue("secret")
            .get("apps/orders/config")
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Orders secret is absent")))
            .map(Versioned::getData)
            .map(data -> {
                Object endpoint = data.get("endpoint");
                if (!(endpoint instanceof String)) {
                    throw new IllegalStateException("Invalid secret format");
                }
                return (String) endpoint;
            });
    }
}
~~~

WebFlux handler có thể ghép `loadEndpoint()` vào pipeline nghiệp vụ. **Không trả secret qua endpoint công khai** hoặc ghi dữ liệu vào log.

Khi có subscription trên `loadEndpoint()`, Spring Vault lấy token đang hoạt động từ session manager, gửi request KV v2 và phát dữ liệu hoặc lỗi trên pipeline. Nó **không** cần đăng nhập mới mỗi lần đọc nếu phiên còn hợp lệ. Trường hợp `403` tại KV thường là lỗi ACL của token, không phải lý do thử lại với token có quyền cao hơn.

Khi gọi Transit encryption/decryption hoặc PKI issue từ reactive API, token vẫn lấy qua cùng supplier/session manager; các endpoint đó đòi capability riêng. Dynamic credentials và PKI certificate có thời hạn/lease riêng với **login token**. Renew token không tự renew mọi lease hoặc cập nhật mọi connection pool.

## 7. Đăng nhập đồng thời, cache, timeout và hủy subscription

### Đăng nhập đồng thời

Giả sử 100 HTTP request đầu tiên đến cùng lúc, khi ứng dụng chưa có Vault token:

~~~text
Không có session manager:
  R1 -> VaultTokenSupplier -> login T1
  R2 -> VaultTokenSupplier -> login T2
  ...
  R100 -> VaultTokenSupplier -> login T100

Có ReactiveLifecycleAwareSessionManager:
  R1, R2, ... R100 -> session manager
                         |
                         +--> phối hợp login một lần
                         |
                         +--> cùng tái sử dụng token hợp lệ
~~~

`ReactiveLifecycleAwareSessionManager` được thiết kế để bảo đảm chỉ thực hiện một lần lấy token khi nhiều request đồng thời yêu cầu lúc chưa có phiên. Với ứng dụng nhiều replica, **mỗi instance có session manager riêng** nên cụm vẫn có nhiều login; cần thiết kế SLO/TTL, rollout và giới hạn tốc độ theo quy mô.

### Những điều không tự được bảo đảm

- **Backpressure:** `Mono` chỉ phát một token; giới hạn concurrency và session manager vẫn cần để tránh login storm.
- **Cancellation:** hủy subscriber không bảo đảm Vault hủy token vừa phát.
- **Timeout:** `.timeout(...)` cần phối hợp HTTP timeout; quá hạn không chứng minh Vault chưa phát token.
- **Retry:** `retryWhen` có thể login lại, tiêu thụ lượt dùng SecretID. Chỉ retry lỗi tạm thời có giới hạn.
- **Caching:** `Mono.cache()` không tự nhận biết token revoke, policy thay đổi hay max TTL.

Nếu cần implement supplier tùy chỉnh sử dụng nguồn credential đồng bộ:

~~~java
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

VaultTokenSupplier legacyAdapter = () ->
    Mono.fromCallable(() -> {
        // DEMO: lấy token từ API đồng bộ được quản lý bên ngoài.
        return VaultToken.of(legacyTokenSource.getCurrentToken());
    }).subscribeOn(Schedulers.boundedElastic());
~~~

`legacyTokenSource` là dependency minh họa, **không có trong Spring Vault**. `boundedElastic` giúp không chiếm event-loop thread khi bắt buộc dùng một API blocking; nó **không biến HTTP/file I/O đồng bộ thành non-blocking I/O** và vẫn có giới hạn thread/queue. Cách ưu tiên là dùng client bất đồng bộ hoặc `AuthenticationStepsOperator` đã được Spring Vault hỗ trợ.

## 8. Lỗi và bảo mật khi cấp token

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/giải pháp |
| --- | --- | --- |
| Không thấy request login | Publisher chưa được subscribe. | Kiểm tra WebFlux handler có trả `Mono` và pipeline đã được dùng. |
| Login mỗi khi gọi KV | Dùng `AuthenticationStepsOperator` trực tiếp trên từng request, bỏ session manager. | Đặt `ReactiveLifecycleAwareSessionManager` giữa supplier và template. |
| `403` ở `auth/approle/login` | RoleID/SecretID sai, hết TTL/lượt sử dụng, role bị đổi. | Kiểm tra auth mount, role, TTL và nguồn credential. |
| Login PASS nhưng `secret/data/...` bị `403` | ACL thiếu `read` hoặc request dùng policy khác mong đợi. | Kiểm tra `token_policies`, `vault token capabilities` và API path. |
| Lỗi sau một khoảng uptime | Vault token đạt TTL/max TTL, source JWT/SecretID không xoay. | Kiểm tra renew/re-login, expiration và nguồn identity. |
| Lỗi TLS/CA hoặc timeout | Truststore, proxy, endpoint, DNS hoặc Vault unavailable. | Xác minh WebClient, HTTP connector, CA/hostname, timeout; phân biệt với credential lỗi. |
| WebFlux event-loop chậm | `.block()`, `Thread.sleep`, đọc credential blocking. | Chuyển sang API reactive hoặc offload hợp lý; đo event-loop latency. |
| Hai lời gọi dùng token khác nhau | Cache/session không được dùng chung hoặc tạo nhiều bean. | Kiểm tra bean scope và đồng thời hóa phiên. |
| Token bị lộ qua log | In `VaultToken`, JWT/SecretID hoặc HTTP header `X-Vault-Token`. | Xóa/sanitize log, thay credential đã lộ, bảo vệ Vault audit log. |

**Phân loại lỗi:** lỗi đăng nhập thuộc auth endpoint, lỗi quyền thuộc secret endpoint, lỗi kết nối thuộc transport. Không chuyển mọi lỗi thành `Mono.empty()` hoặc catch `Throwable` rồi tiếp tục với token mặc định: cách đó che giấu rủi ro và khiến API trả dữ liệu sai.

### Quy tắc bảo mật

1. Không hardcode root token, RoleID/SecretID, Kubernetes JWT hoặc Vault token trong Git, image, CI artifact và log.
2. Dùng HTTPS với CA và hostname verification, thời gian chờ HTTP phù hợp, Vault policy theo **least privilege**.
3. Không truyền URL tuyệt đối từ người dùng vào API Vault đã gắn token; cần giới hạn host/đường dẫn để tránh gửi header xác thực đến host khác.
4. Với Kubernetes/JWT, token nguồn phải có audience/claims được auth role kiểm tra, được xoay trước khi hết hạn.
5. Tái sử dụng session manager theo phạm vi workload; đừng chia sẻ một token Vault chung cho nhiều người dùng nếu nghiệp vụ yêu cầu phân quyền theo từng user.
6. Thu hồi token và xử lý cleanup phù hợp loại token: `VaultToken` tĩnh và `LoginToken` phát từ login có thông tin vòng đời khác nhau.

### Một số khái niệm dễ nhầm

Ghi nhớ phân biệt `VaultTemplate` đồng bộ với `ReactiveVaultTemplate`, token TTL với lease TTL, và một supplier đơn thuần với lifecycle-aware session manager.

## 9. Unit test `VaultTokenSupplier` với StepVerifier

Các unit test kiểm tra **reactive contract** mà không cần một Vault thật. Ví dụ sau minh họa publisher lazy và ảnh hưởng của subscribe lặp:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class VaultTokenSupplierTest {

    @Test
    void tokenIsCreatedOnlyWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();
        VaultTokenSupplier supplier = () ->
            Mono.fromSupplier(() -> {
                calls.incrementAndGet();
                return VaultToken.of("test-only");
            });

        Mono<VaultToken> token = supplier.getVaultToken();
        assertEquals(0, calls.get());

        StepVerifier.create(token)
            .assertNext(value -> assertNotNull(value))
            .verifyComplete();
        assertEquals(1, calls.get());

        StepVerifier.create(token)
            .expectNextCount(1)
            .verifyComplete();
        assertEquals(2, calls.get());
    }

    @Test
    void supplierErrorIsPropagated() {
        VaultTokenSupplier broken = () ->
            Mono.error(new IllegalStateException("Auth unavailable"));

        StepVerifier.create(broken.getVaultToken())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Test này không chứng minh I/O non-blocking vì `fromSupplier` ở đây chỉ tạo object. Để xác nhận event loop không bị block, cần dùng HTTP stub chậm có chủ đích, kiểm tra số thread đang hoạt động/latency hoặc công cụ như BlockHound phù hợp; không nên dựa vào `Thread.sleep` trong event loop.

### Kiểm thử concurrency/caching

Với `AuthenticationStepsOperator`, test có thể cho 20 subscription song song vào publisher do operator tạo; một số trường hợp sẽ gửi nhiều login request. Sau đó lặp lại qua `ReactiveLifecycleAwareSessionManager`, kiểm tra số request login **được phối hợp** và thời gian hoàn tất.

Đừng so sánh token bằng cách in chuỗi thật. Có thể dùng `StepVerifier`, kiểm tra token không rỗng và bộ đếm request tại mock server, đồng thời không để token trong snapshot, exception message hay CI log.

## 10. Kiểm thử tích hợp từ AppRole tới KV v2

Integration test cần chạy trên Vault lab có **AppRole** và KV v2 thật, đồng thời cung cấp credential nguồn qua cơ chế an toàn. Tạo hai secret giả:

~~~bash
# Thực hiện bằng identity quản trị Vault trên môi trường test.
vault secrets enable -path=secret -version=2 kv
vault auth enable -path=approle approle

vault kv put -mount=secret apps/orders/config endpoint=https://orders.example.org
vault kv put -mount=secret apps/payments/config endpoint=https://payments.example.org
~~~

Hai lệnh enable chỉ dùng khi các mount chưa tồn tại. Tạo file `orders-only.hcl` và nạp policy:

~~~hcl
path "secret/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

~~~bash
vault policy write orders-only orders-only.hcl
vault write auth/approle/role/orders-service \
  token_policies=orders-only \
  token_ttl=15m \
  token_max_ttl=1h \
  secret_id_num_uses=10 \
  secret_id_ttl=30m
~~~

Đọc `role_id` và phát `secret_id` bằng một danh tính test được phép, rồi nạp hai giá trị ấy qua `AppRoleCredentialSource`. **Không** copy chúng vào repo, terminal log hoặc screenshot. Với `secret_id_num_uses=10`, các lần login mới có thể tiêu thụ quota, vì vậy test luôn phải ghi nhận số login thực tế.

| Ca | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| AUTH-01 | AppRole hợp lệ, `VaultTokenSupplier` được subscribe | Vault phát token; token không bị log ra. |
| AUTH-02 | RoleID/SecretID sai | `Mono` kết thúc bằng lỗi auth; không có fallback sang root token. |
| AUTH-03 | Chưa có session, nhiều request KV đồng thời | Session manager phối hợp login, không tạo một token cho mỗi request. |
| KV-01 | Token `orders-only` đọc `apps/orders/config` | PASS, đúng dữ liệu giả của test. |
| KV-02 | Cùng token đọc `apps/payments/config` | **DENY** bởi ACL; phải xác minh lỗi `403`. |
| TTL-01 | Login token sắp hết TTL và có thể renew | Manager renew token hợp lệ theo khả năng backend. |
| TTL-02 | Token không còn renew được, credential nguồn hợp lệ | Manager có thể re-login nhận token kế tiếp. |
| TTL-03 | SecretID hết số lần dùng khi phải re-login | Login thất bại rõ ràng; ứng dụng báo unhealthy, không dùng token bí mật mặc định. |
| ERR-01 | Vault timeout hoặc TLS sai | Pipeline trả lỗi transport và retry có giới hạn nếu phù hợp. |
| CANCEL-01 | Caller hủy request đang chờ login | Không phát response giả; quan sát liệu backend đã phát token hay chưa qua audit. |

**Không coi mọi request thất bại là bằng chứng ACL đúng.** Một `404` do sai path, lỗi DNS hoặc TLS không đồng nghĩa token đã bị Vault từ chối quyền. Nếu kiểm tra `403`, phải xem endpoint phát lỗi hoặc `vault token capabilities secret/data/apps/payments/config` bằng chính token của workload (không dùng root token).

### Kiểm thử vòng đời và quan sát

Theo dõi số lần login, renew, re-login, thời gian cấp token, số lỗi auth so với lỗi KV, số connection HTTP mở và độ trễ khi Vault không sẵn sàng. Kiểm thử TTL bằng cấu hình ngắn trong lab, nhưng không dùng vòng `sleep` vô hạn hoặc tự revoke token production để ép test. Với token dynamic, kiểm tra luôn tác động tới lease secret riêng; **re-login thành công không có nghĩa database credential được rotate**.

## 11. Checklist thiết kế, bài tập và tài liệu

### Checklist trước production

- [ ] Đã chọn auth method phù hợp với danh tính workload; Vault auth role kiểm tra audience/namespace/claims hoặc AppRole secret.
- [ ] Dùng `VaultTokenSupplier` phù hợp với reactive I/O; không có `.block()` trên event-loop thread.
- [ ] `AuthenticationStepsOperator` dùng Vault client có CA/hostname verification, HTTP timeout và endpoint chuẩn.
- [ ] Có `ReactiveSessionManager` dùng chung để phối hợp login, tái sử dụng token và xử lý TTL.
- [ ] Kiểm tra token renewable/max TTL và khả năng cấp lại credential nguồn; có logic shutdown/revoke phù hợp.
- [ ] `ReactiveVaultTemplate` chỉ truy cập các path hợp lệ; không lộ token qua URL ngoài, log hoặc header sai host.
- [ ] Có test song song, timeout, cancellation, login denied và ACL denied tại secret endpoint.
- [ ] Token TTL, dynamic secret lease và PKI certificate TTL được quản lý như các vòng đời khác nhau.
- [ ] Metrics/audit không chứa JWT, RoleID/SecretID, token hay plaintext secret.

### Câu hỏi tự đánh giá

1. Vì sao `VaultTokenSupplier` là functional interface và `getVaultToken()` trả `Mono<VaultToken>` thay vì trực tiếp `VaultToken`?
2. Tại sao `Mono.fromSupplier` không đủ để khẳng định tác vụ đọc credential không chặn event loop?
3. Điểm khác nhau giữa `AuthenticationSteps` và `AuthenticationStepsOperator` là gì?
4. Nếu cùng `Mono` login được subscribe ba lần, lúc nào có thể xuất hiện ba lần đăng nhập?
5. `CachingVaultTokenSupplier` và `ReactiveLifecycleAwareSessionManager` khác nhau thế nào trong việc bảo đảm token còn hợp lệ?
6. Vì sao `ReactiveVaultTemplate` đọc KV v2 bằng `opsForVersionedKeyValue("secret").get("apps/orders/config")` trong khi policy cần `secret/data/apps/orders/config`?
7. Khi login PASS nhưng KV trả `403`, nên kiểm tra những lớp nào? Tại sao không retry bằng root token?
8. Tại sao việc gia hạn Vault login token không tự gia hạn dynamic database credentials hoặc chứng thư PKI?

## Nguồn tham khảo chính thức

- [Spring Vault — Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — VaultTokenSupplier](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/VaultTokenSupplier.html)
- [Spring Vault API — AuthenticationStepsOperator](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationStepsOperator.html)
- [Spring Vault API — ReactiveSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveSessionManager.html)
- [Spring Vault API — ReactiveLifecycleAwareSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html)
- [Spring Vault API — ReactiveVaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html)

**Kết luận:** `VaultTokenSupplier` là hợp đồng reactive để nhận Vault token; `AuthenticationStepsOperator` thực thi đăng nhập không chặn qua các bước xác thực, còn `ReactiveLifecycleAwareSessionManager` chịu trách nhiệm tái sử dụng và quản lý thời hạn token. Dùng chúng cùng `ReactiveVaultTemplate`, ACL tối thiểu và kiểm thử lifecycle để ứng dụng Java truy cập Vault ổn định mà không blocking event loop.
