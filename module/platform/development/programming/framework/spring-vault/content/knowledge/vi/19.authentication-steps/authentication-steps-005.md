# AuthenticationStepsOperator cho đăng nhập reactive trong Spring Vault

## 1. Vì sao cần đăng nhập reactive?

Khi một ứng dụng Java dùng **Spring Vault** để truy cập HashiCorp Vault, nó cần nhận **Vault token** sau khi chứng minh danh tính. Ứng dụng dùng `VaultTemplate` theo mô hình đồng bộ có thể gọi `ClientAuthentication.login()`. Tuy nhiên, với ứng dụng Spring WebFlux hoặc pipeline Reactor, chờ HTTP đăng nhập trên một thread xử lý sự kiện có thể gây nghẽn, đặc biệt khi nhiều yêu cầu đến đồng thời hoặc khi Vault và hệ thống cung cấp danh tính phản hồi chậm.

**`AuthenticationStepsOperator`** trong package `org.springframework.vault.authentication` giải quyết phần thực thi luồng đăng nhập theo mô hình reactive. Nó nhận bản mô tả luồng `AuthenticationSteps`, sử dụng client reactive để thực hiện các yêu cầu HTTP và cung cấp **`Mono<VaultToken>`** qua giao diện `VaultTokenSupplier`.

Bài này thuộc chương **Authentication Steps**. Mục tiêu là hiểu cách khai báo các bước, cách `AuthenticationStepsOperator` chạy chúng khi có subscription, cách quản lý Vault token và sử dụng token đó trong `ReactiveVaultTemplate`. Chủ đề gắn với các nội dung rộng hơn của module **SPRING_VAULT**: xác thực theo workload, Vault ACL policy, KV v2, vòng đời token/lease, Transit, PKI, xử lý lỗi và kiểm thử tích hợp.

Sau bài học, bạn có thể:

- Phân biệt `AuthenticationSteps`, `AuthenticationStepsOperator`, `AuthenticationStepsExecutor`, `VaultTokenSupplier` và `ReactiveSessionManager`.
- Xây dựng một luồng đăng nhập AppRole có đầu vào được cấp an toàn và được thực thi khi subscribe.
- Tích hợp với `ReactiveVaultTemplate` để đọc KV v2 mà không gọi `.block()` trong luồng xử lý HTTP.
- Hiểu lý do cần tái sử dụng, gia hạn hoặc thay Vault token, thay vì login mới ở mỗi request.
- Kiểm tra luồng reactive, lỗi đăng nhập, lỗi ACL, token hết hạn và khả năng cô lập secret.

## 2. Những thành phần phối hợp trong quá trình xác thực

| Thành phần | Vai trò | Kết quả/kiểu dữ liệu |
| --- | --- | --- |
| `AuthenticationSteps` | **Khai báo** nguồn dữ liệu, bước biến đổi, truy vấn HTTP và bước login cuối cùng. | Một flow description; chưa login ngay khi khai báo. |
| `AuthenticationStepsFactory` | Tạo các `AuthenticationSteps` cho phương thức xác thực cụ thể. | `getAuthenticationSteps()`. |
| `AuthenticationStepsOperator` | **Thực thi reactive** flow, truy cập Vault hoặc dịch vụ bên ngoài, chuyển response login thành token. | `getVaultToken(): Mono<VaultToken>`. |
| `AuthenticationStepsExecutor` | Thực thi flow theo mô hình **đồng bộ**. | `login(): VaultToken`. |
| `VaultTokenSupplier` | Hợp đồng cấp token cho lớp truy cập Vault reactive. | `Mono<VaultToken>`. |
| `ReactiveSessionManager` | Quản lý token dùng chung theo phiên. | Cung cấp token phiên, thường qua `getSessionToken()`. |
| `ReactiveLifecycleAwareSessionManager` | Theo dõi TTL, làm mới hoặc xác thực lại theo vòng đời, thu hồi token phù hợp khi kết thúc. | Token đã được quản lý lifecycle. |
| `ReactiveVaultTemplate` | Gọi KV, Transit, PKI hoặc API Vault bằng token của phiên. | `Mono`/`Flux` của nghiệp vụ. |

Một hình dung hữu ích:

~~~mermaid
flowchart TD
    A["Credentials của workload"] --> B["AuthenticationSteps: khai báo flow"]
    B --> C["AuthenticationStepsOperator"]
    C -->|"subscribe"| D["HTTP login đến Vault"]
    D --> E{"Vault chấp nhận?"}
    E -->|"Có"| F["Mono<VaultToken>"]
    E -->|"Không"| X["Mono.error(...)"]
    F --> G["ReactiveSessionManager"]
    G --> H["ReactiveVaultTemplate"]
    H --> I{"Vault ACL"}
    I -->|"Cho phép"| J["KV v2 / Transit / PKI"]
    I -->|"Từ chối"| K["403 permission denied"]
~~~

`AuthenticationStepsOperator` chỉ là bộ **thực thi đăng nhập**. Nó không quyết định policy hay quyền truy cập secret: các quyết định đó thuộc về Vault auth role và ACL policy. Nó cũng không thay thế toàn bộ session manager.

### Reactive khác synchronous ở đâu?

~~~text
Synchronous:
  AuthenticationSteps -> AuthenticationStepsExecutor.login()
                                        -> VaultToken

Reactive:
  AuthenticationSteps -> AuthenticationStepsOperator.getVaultToken()
                                        -> Mono<VaultToken>
                                        -> thực thi khi subscribe
~~~

`Mono` mô tả một phép tính bất đồng bộ có thể phát ra **một giá trị**, kết thúc rỗng hoặc phát tín hiệu lỗi. Gọi `getVaultToken()` để tạo publisher chưa đồng nghĩa đã thực hiện HTTP request. Khi có subscription từ Reactor/WebFlux, các bước mới được chạy. Mỗi lần subscription lên một publisher không được cache **có thể kích hoạt đăng nhập mới**; vì vậy cần tách khái niệm “reactive” với “đăng nhập chỉ một lần”.

## 3. Cấu trúc DSL `AuthenticationSteps`

`AuthenticationSteps` là một DSL để ghép **nguồn dữ liệu → biến đổi → bước cuối**. Các bước trung gian xử lý một **authentication state object**, chẳng hạn chuỗi JWT, một map chứa `role_id`/`secret_id`, hoặc kết quả lấy từ metadata service.

Các API thường gặp:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `AuthenticationSteps.just(VaultToken.of(...))` | Flow dùng token đã cung cấp sẵn. | Thích hợp minh họa hoặc token được quản lý bên ngoài; không phải login tạo token mới. |
| `AuthenticationSteps.fromSupplier(...)` | Lấy dữ liệu đầu vào từ `Supplier<T>` lúc thực thi. | Supplier tự viết có thể thực hiện tác vụ blocking; cần hiểu ảnh hưởng tới scheduler. |
| `AuthenticationSteps.fromHttpRequest(...)` | Lấy đầu vào từ một HTTP endpoint ngoài Vault. | Phải xác định host đáng tin và bảo vệ credential. |
| `AuthenticationSteps.fromVaultRequest(...)` | Lấy đầu vào từ một endpoint Vault trước khi login. | Dùng khi cần unwrap/pull credential từ Vault. |
| `.map(...)` | Chuyển đổi state object, ví dụ JWT → map login payload. | Không log nội dung state nếu chứa bí mật. |
| `.request(...)` | Thực hiện HTTP request như một bước trung gian. | Kết quả có thể được biến đổi thêm. |
| `.login("auth/{mount}/login", "approle")` | POST payload hiện tại đến Vault để login. | `{mount}` được expand; mount không nhất thiết là đường dẫn mặc định. |
| `.loginAt("approle")` | Cách viết ngắn cho endpoint login chuẩn. | Chỉ dùng nếu phiên bản Spring Vault có API này (có trong 4.1). |

Bước **cuối** phải tạo `VaultToken`, ví dụ `.login(...)`. Không kết thúc flow ở một `.map(...)` rồi kỳ vọng `AuthenticationStepsOperator` tự suy diễn cách đăng nhập.

### Ví dụ một flow AppRole

Vault AppRole dùng `role_id` và (khi role yêu cầu) `secret_id` để đăng nhập qua `auth/approle/login`. Đoạn sau mô tả flow, chưa thực hiện login:

~~~java
import java.util.Map;
import java.util.function.Supplier;
import org.springframework.vault.authentication.AuthenticationSteps;

public final class AppRoleSteps {

    public static AuthenticationSteps create(
            Supplier<String> roleId,
            Supplier<String> secretId) {

        return AuthenticationSteps.fromSupplier(
                () -> Map.of(
                    "role_id", roleId.get(),
                    "secret_id", secretId.get()))
            .login("auth/{mount}/login", "approle");
    }
}
~~~

Giả định `roleId.get()` và `secretId.get()` trả về chuỗi hợp lệ, không `null`. `Map.of` từ Java 9 trở lên không nhận giá trị `null`. Credentials được cấp từ nguồn đã bảo vệ trong môi trường thực, không viết cứng vào source.

Nếu AppRole mount ở đường dẫn khác, ví dụ `auth/production-approle/`, thay `"approle"` bằng `"production-approle"`. Với Spring Vault 4.1+, có thể viết `.loginAt("approle")` cho dạng endpoint login chuẩn; để hỗ trợ các phiên bản 3.x, ví dụ trên dùng `.login(String, String...)`.

Thay vì tự xây dựng state, nhiều auth method của Spring Vault đã có `AuthenticationStepsFactory` hoặc phương thức tĩnh tạo steps. Ví dụ `AppRoleAuthentication.createAuthenticationSteps(options)` dùng `AppRoleAuthenticationOptions`. Cách này đặc biệt hữu ích khi AppRole phải lấy `role_id`/`secret_id` từ Vault, xử lý wrapping, hoặc khi đăng nhập Kubernetes/JWT cần các bước đặc thù.

## 4. Chuẩn bị Vault lab và quyền tối thiểu

Giả sử Vault test chạy tại `https://vault.example.org:8200`, KV v2 được mount ở `secret/` và ứng dụng cần đọc một key `orders/config`. Các lệnh dưới đây do **Vault admin trong lab** thực hiện, không chạy bằng token AppRole runtime:

~~~bash
# Chỉ enable các mount chưa tồn tại.
vault secrets enable -path=secret -version=2 kv
vault auth enable -path=approle approle

vault kv put -mount=secret orders/config \
  endpoint=https://api-orders.example.org \
  mode=test
~~~

Tạo file policy `orders-read.hcl`:

~~~hcl
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Áp dụng policy và tạo AppRole:

~~~bash
vault policy write orders-read orders-read.hcl

vault write auth/approle/role/orders-reactive \
  token_policies=orders-read \
  token_ttl=15m \
  token_max_ttl=1h \
  secret_id_ttl=30m \
  secret_id_num_uses=10
~~~

Tra cứu RoleID, phát hành SecretID cho bài test bằng danh tính admin:

~~~bash
vault read -field=role_id \
  auth/approle/role/orders-reactive/role-id

vault write -f -field=secret_id \
  auth/approle/role/orders-reactive/secret-id
~~~

**Không chia sẻ output của hai lệnh này.** SecretID là thông tin đăng nhập nhạy cảm; tránh đưa nó vào log CI, ảnh chụp màn hình, shell history hoặc source code. Có thể dùng response wrapping và cơ chế phân phối credential riêng cho production. Ví dụ này có `secret_id_num_uses=10`, nên nếu mỗi subscription lại login, quota số lần sử dụng SecretID sẽ bị tiêu thụ rất nhanh.

### Auth role và Vault policy bảo vệ hai lớp khác nhau

AppRole `orders-reactive` quyết định **ai có thể nhận Vault token** và gắn `orders-read` cho token. Policy chỉ cho phép đọc `secret/data/orders/config`; việc login thành công không cho phép liệt kê toàn bộ `secret/`, đọc secret ứng dụng khác, gọi Transit encrypt/decrypt hay PKI issue.

Trước khi kiểm thử bằng Java, có thể đăng nhập thủ công với credential test để xác nhận Vault thực sự đã cấu hình đúng. Không dùng root token cho bài kiểm tra quyền; root token bỏ qua cơ chế ACL thông thường.

## 5. Thực thi reactive với `AuthenticationStepsOperator`

Constructor được hỗ trợ lâu dài là:

~~~java
AuthenticationStepsOperator(
    AuthenticationSteps steps,
    WebClient webClient
)
~~~

Trong Spring Vault 4.1 còn có overload nhận `ReactiveVaultClient` để xử lý request vào Vault và `WebClient` dùng cho những truy vấn HTTP bên ngoài:

~~~java
AuthenticationStepsOperator(
    AuthenticationSteps steps,
    ReactiveVaultClient vaultClient,
    WebClient webClient
)
~~~

Ở các phiên bản cũ, `WebClient` đảm nhiệm HTTP cho luồng xác thực. Hãy chọn overload khớp phiên bản dependency, cấu hình HTTPS/TLS tin cậy, timeout và Vault API base path đúng. Trong ví dụ bên dưới, `vaultApiWebClient` là WebClient **đã cấu hình** trỏ tới Vault API `/v1/`; nếu có request tới hệ thống bên ngoài, phải xác định rõ endpoint và giới hạn truy cập của client đó.

~~~java
import java.util.function.Supplier;
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.vault.authentication.AuthenticationSteps;
import org.springframework.vault.authentication.AuthenticationStepsOperator;
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.support.VaultToken;

public final class ReactiveAppRoleLogin {

    private final VaultTokenSupplier supplier;

    public ReactiveAppRoleLogin(
            WebClient vaultApiWebClient,
            Supplier<String> roleId,
            Supplier<String> secretId) {

        AuthenticationSteps steps = AppRoleSteps.create(roleId, secretId);
        this.supplier = new AuthenticationStepsOperator(steps, vaultApiWebClient);
    }

    public Mono<VaultToken> getVaultToken() {
        // Mô tả đăng nhập; HTTP thực thi khi subscribe.
        return supplier.getVaultToken();
    }
}
~~~

Ví dụ sử dụng trong một ngữ cảnh test với client đã thiết lập:

~~~java
WebClient vaultApiWebClient = WebClient.builder()
    .baseUrl("https://vault.example.org:8200/v1/")
    .build();

ReactiveAppRoleLogin login = new ReactiveAppRoleLogin(
    vaultApiWebClient, roleIdSupplier, secretIdSupplier);

Mono<Boolean> authenticated = login.getVaultToken()
    .map(token -> token != null);
~~~

`roleIdSupplier` và `secretIdSupplier` là các `Supplier<String>` đã được khai báo và bảo vệ ở tầng cấu hình. `authenticated` chưa chạy cho đến khi được subscribe. Ví dụ chỉ kiểm tra token có được phát hành; không được in `token.getToken()` vào log.

**Không gọi `.block()` hoặc `.subscribe()` thủ công trong WebFlux controller** để “kích hoạt đăng nhập”. Hãy trả `Mono` cho Spring WebFlux hoặc ghép nó vào pipeline khác. `.subscribe()` thủ công có thể tách lỗi khỏi request gốc và khiến điều phối vòng đời khó kiểm soát.

### Supplier blocking có làm mất tính reactive?

`AuthenticationStepsOperator` phát hiện một số loại supplier chuyên biệt, chẳng hạn `ResourceCredentialSupplier`, để đọc file bằng I/O không blocking; supplier tổng quát có thể được chuyển sang scheduler thích hợp, tránh chạy trực tiếp công việc blocking trên event loop. Tuy vậy, đó không phải lý do để đặt truy vấn database blocking dài hoặc thao tác đọc secret nặng vào lambda `Supplier`. Khi nguồn credential có tính bất đồng bộ, hãy chọn cách lấy credential phù hợp với phiên bản API, cấu hình timeout và kiểm tra bằng công cụ đo thread/latency.

## 6. Quản lý token với `ReactiveSessionManager`

### Vấn đề: operator tự nó không phải kho token cho toàn ứng dụng

Một thao tác đăng nhập có thể tạo token sống 15 phút. Nếu mọi request HTTP đều subscribe một luồng login mới, ứng dụng sẽ:

- Gọi Vault auth endpoint quá thường xuyên, tăng độ trễ và áp lực lên Vault.
- Tiêu thụ `secret_id_num_uses` của AppRole, nhanh chóng khiến login tiếp theo bị từ chối.
- Phát hành nhiều Vault token hơn cần thiết và khiến revoke/audit khó quản lý.
- Có thể thất bại khi auth backend tạm gián đoạn dù token cũ vẫn còn hiệu lực.

Vì vậy, sau khi tạo `AuthenticationStepsOperator`, nên chuyển việc lấy và tái sử dụng token cho thành phần quản lý phiên. `ReactiveLifecycleAwareSessionManager` có thể lấy token từ một `VaultTokenSupplier`, theo dõi TTL, làm mới token renewable, xác thực lại khi cần và thu hồi `LoginToken` phù hợp khi shutdown.

Ví dụ nối các thành phần với nhau (mã rút gọn, `scheduler` và `vaultApiWebClient` là bean được cấu hình, quản lý vòng đời):

~~~java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.authentication.AuthenticationStepsOperator;
import org.springframework.vault.authentication.ReactiveLifecycleAwareSessionManager;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.web.reactive.function.client.WebClient;

public ReactiveSessionManager createSessionManager(
        AuthenticationStepsOperator operator,
        TaskScheduler scheduler,
        WebClient vaultApiWebClient) {

    return new ReactiveLifecycleAwareSessionManager(
        operator, scheduler, vaultApiWebClient);
}
~~~

Đây là **một ví dụ wiring method**, không phải cấu hình Spring hoàn chỉnh: bạn cần quản lý `TaskScheduler`, `WebClient`, SSL, sự kiện lifecycle và đóng session manager ở shutdown. Các phiên bản 4.1+ còn hỗ trợ constructor dựa trên `ReactiveVaultClient`. Khi sử dụng `AbstractReactiveVaultConfiguration` với một `ClientAuthentication` triển khai `AuthenticationStepsFactory`, Spring Vault có sẵn cơ chế xây dựng các thành phần reactive tương ứng.

`CachingVaultTokenSupplier.of(operator)` cũng tồn tại, nhưng lưu cache token **không đồng nghĩa** tự quản lý đầy đủ TTL, renew và revoke như lifecycle-aware session manager. Chọn một chiến lược session nhất quán; tránh tạo nhiều lớp cache không cần thiết.

### Token TTL khác với lease của secret

Vault token có TTL, có thể renewable hoặc không renewable, và có thể bị thu hồi. Dynamic database credential hoặc PKI certificate có lease/thời hạn **riêng**; quản lý Vault token không tự gia hạn mọi credential mà ứng dụng lấy được. KV v2 chứa static secrets theo phiên bản, cũng không tự tạo lease chỉ vì ứng dụng đăng nhập reactive.

AppRole có `secret_id_ttl`, `secret_id_num_uses` bên cạnh `token_ttl`. Khi SecretID hết hạn hoặc hết lượt dùng, **đăng nhập lại có thể thất bại** dù mã nguồn không đổi; cần cơ chế cấp và xoay credential nguồn trước khi credential hết hạn.

## 7. Dùng token trong `ReactiveVaultTemplate`

`ReactiveVaultTemplate` là lớp reactive thực hiện request tới Vault; `VaultTemplate` là lớp đồng bộ. Với `ReactiveVaultTemplate`, token được cấp bởi supplier/session manager sẽ được gắn vào request cần xác thực. Một ví dụ khởi tạo tương ứng:

~~~java
import java.net.URI;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.ReactiveVaultTemplate;

public ReactiveVaultOperations reactiveVaultOperations(
        ReactiveSessionManager sessionManager) {

    VaultEndpoint endpoint =
        VaultEndpoint.from(URI.create("https://vault.example.org:8200"));

    return new ReactiveVaultTemplate(
        endpoint, new ReactorClientHttpConnector(), sessionManager);
}
~~~

Ví dụ này chỉ nhằm minh họa mối nối giữa `ReactiveSessionManager` và template. Trong production, dùng cùng cấu hình TLS, timeout, proxy, tên Vault namespace (nếu có), endpoint và connector được quản lý tập trung. Một `ReactiveVaultTemplate` có thể được tái sử dụng an toàn cho nhiều request trong cùng phạm vi danh tính.

### Đọc một secret KV v2

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.Versioned;

public final class OrdersConfigReader {

    private final ReactiveVaultOperations vault;

    public OrdersConfigReader(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<String> readEndpoint() {
        return vault.opsForVersionedKeyValue("secret")
            .get("orders/config")
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Orders secret not found")))
            .map(Versioned::getData)
            .map(data -> {
                Object value = data.get("endpoint");
                if (!(value instanceof String)) {
                    throw new IllegalStateException("Invalid endpoint format");
                }
                return (String) value;
            });
    }
}
~~~

Đường dẫn `"secret"` chỉ **mount KV v2**; `"orders/config"` là key tương đối. API của KV v2 thực tế có đoạn `data/` nhưng `opsForVersionedKeyValue` xử lý cấu trúc API này. Nếu token chỉ có quyền `read` trên `secret/data/orders/config`, request đọc `secret/data/finance/config` phải bị từ chối.

Ví dụ `Mono<String>` có thể được trả từ WebFlux handler. Khi Vault phản hồi lỗi quyền, pipeline phải phát ra lỗi tương ứng để caller nhận biết; không nên tự động đổi mọi lỗi `403` thành giá trị trống hoặc dùng một token có nhiều quyền hơn để retry.

## 8. Xác thực theo workload, không đặt bí mật trong ứng dụng

Để nhận token từ AppRole, workload phải có khả năng cung cấp `role_id` và `secret_id` đúng lúc. Trong production, nguồn đầu vào có thể là file chỉ đọc được mount an toàn, token được bọc (response wrapping) hoặc một cơ chế cấp credential được quản lý. Khi dùng Kubernetes, `KubernetesAuthentication` có thể tạo `AuthenticationSteps` dựa trên ServiceAccount JWT; nếu sử dụng JWT auth thì cần cấu hình audience/claims của auth role đúng. Một số phương thức cloud identity cũng cung cấp `AuthenticationStepsFactory`.

Điều đó giúp ứng dụng giữ mô hình chung:

~~~text
Workload identity / Auth options
          |
          v
  AuthenticationSteps
          |
          v
 AuthenticationStepsOperator
          |
          v
  ReactiveSessionManager
          |
          v
    ReactiveVaultTemplate
          |
          v
  Vault ACL -> KV / Transit / PKI
~~~

Không dùng JWT của người dùng bất kỳ để đăng nhập một role Vault rộng quyền. Vault phải xác minh chữ ký token, namespace hoặc audience theo phương thức auth đã chọn và cấp policy tối thiểu. `AuthenticationStepsOperator` chỉ thực thi flow đó, không tự xác minh các quy tắc an toàn của role.

Trong ứng dụng WebFlux phục vụ nhiều người dùng, một `ReactiveVaultTemplate` dùng chung một session manager thường đại diện cho **một danh tính Vault của service**. Nếu cần chính sách Vault theo **từng người dùng**, phải thiết kế session/token riêng cho từng identity, không đưa token của người này sang request người khác.

## 9. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hành động đúng |
| --- | --- | --- |
| `Mono` chưa gọi login | Không có subscription; pipeline chưa được sử dụng. | Trả `Mono` cho WebFlux hoặc ghép vào pipeline đã được subscribe. |
| Vault nhận nhiều login liên tiếp | Gọi `getVaultToken()` trên mỗi request hoặc subscribe lặp. | Dùng `ReactiveSessionManager`, kiểm tra cache/lifecycle. |
| `403` tại `auth/approle/login` | RoleID/SecretID sai, SecretID hết hạn/hết lượt, auth mount nhầm. | Kiểm tra AppRole, quota, TTL, audit, nguồn cấp credential. |
| Login PASS nhưng đọc KV bị `403` | ACL thiếu `read` trên `secret/data/...`. | Đọc role policies và capability thực tế của token. |
| `404` khi đọc KV | Key không có, phiên bản đã bị xóa, hoặc sai path/mount. | Xác minh key và mount với identity có quyền kiểm tra. |
| Lỗi TLS/CA hoặc DNS | Client không tin cậy Vault certificate hoặc host không phân giải được. | Cấu hình truststore/SSL, kiểm tra hostname và mạng. |
| `ReadTimeout`/độ trễ lớn | Vault hoặc nguồn credential phản hồi chậm; supplier blocking. | Đo timeout, latency, scheduler và kết nối upstream. |
| Lỗi xuất hiện khi token hết hạn | Token không được renew, login lại không lấy được credential mới. | Kiểm tra lifecycle-aware manager, token TTL và rotation. |
| WebFlux bị nghẽn | Có `.block()`, file I/O blocking hoặc thao tác đồng bộ trong pipeline. | Loại bỏ blocking khỏi event loop; dùng API reactive/đường I/O phù hợp. |
| Vô tình lộ token trên log | Log payload/state, `VaultToken`, header hoặc response raw. | Xóa log nhạy cảm, hạn chế quyền đọc audit và xoay credential bị lộ. |

**Phân biệt rõ giai đoạn lỗi:** nếu login thất bại, request KV chưa được gửi; nếu login thành công nhưng KV bị từ chối, cần xem Vault ACL. Dùng audit log của Vault và correlation/request ID (không kèm token hoặc giá trị secret) để đối chiếu hai giai đoạn.

Đối với lỗi tạm thời như kết nối Vault gián đoạn, có thể áp dụng retry có giới hạn và backoff phù hợp. Không retry vô hạn với `403` hoặc credential sai; retry liên tục có thể làm cạn số lần dùng SecretID, tăng tải auth backend và che giấu sai cấu hình.

## 10. Kiểm thử `AuthenticationStepsOperator` và reactive session

### 10.1. Đánh giá tính lazy và phản hồi lỗi

Với Reactor, `StepVerifier` xác nhận kết quả của một `Mono`. Ví dụ sau là hàm hỗ trợ integration test đã được truyền một operator có AppRole hợp lệ:

~~~java
import reactor.test.StepVerifier;
import org.springframework.vault.authentication.AuthenticationStepsOperator;

public final class LoginAssertions {
    public static void assertCanLogin(AuthenticationStepsOperator operator) {
        StepVerifier.create(operator.getVaultToken())
            .assertNext(token -> {
                if (token == null) {
                    throw new AssertionError("No Vault token returned");
                }
            })
            .verifyComplete();
    }
}
~~~

Test fixture cần tạo operator qua cấu hình Vault test, sau đó gọi `LoginAssertions.assertCanLogin(operator)`. Khi tạo publisher nhưng chưa `verify()` hoặc `subscribe()`, login chưa chạy; kiểm thử tính lazy nên dùng HTTP stub có bộ đếm request:

1. Tạo `Mono` bằng `operator.getVaultToken()`, xác nhận số request login đang bằng 0.
2. Subscribe lần đầu, xác nhận một request login và nhận token.
3. Subscribe một lần nữa khi **không qua session manager**, kiểm tra có tạo login mới hay không theo thực thi cụ thể.
4. Đưa operator vào session manager, gửi nhiều truy cập KV đồng thời và xác nhận không có cơn bão login.

Không cần test bằng cách `Thread.sleep()` cố định trên thread sự kiện; có thể dùng HTTP stub và Reactor `StepVerifier` cho những trạng thái quan sát được.

### 10.2. Ma trận test tích hợp

| Ca | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| AUTH-01 | AppRole hợp lệ, Vault sẵn sàng | `Mono<VaultToken>` phát token và hoàn tất. |
| AUTH-02 | RoleID hoặc SecretID sai | `Mono` phát lỗi; không có token hợp lệ. |
| AUTH-03 | SecretID quá TTL hoặc hết `num_uses` | Login mới bị từ chối theo cấu hình AppRole. |
| REACTIVE-01 | Chưa subscribe `getVaultToken()` | Chưa có HTTP login. |
| SESSION-01 | Nhiều request dùng cùng session manager | Tái sử dụng token hoặc renew/re-login đúng lifecycle, không login cho mọi request. |
| ACL-01 | Token chỉ có `orders-read`, đọc key `orders/config` | PASS. |
| ACL-02 | Cùng token đọc `finance/config` | DENY do thiếu ACL; xác minh là lỗi quyền. |
| TTL-01 | Vault token đã hết hạn | Session manager xử lý theo renewal/re-login khi còn credential hợp lệ. |
| UPSTREAM-01 | Vault unavailable/timeout | Pipeline báo lỗi có kiểm soát; không che lỗi thành dữ liệu rỗng. |
| ROTATE-01 | AppRole SecretID được xoay | Sau khi cần re-login, workload sử dụng credential mới từ nguồn cấp. |

Mỗi phép kiểm tra phải phân biệt **lỗi xác thực**, **lỗi phân quyền** và **lỗi kết nối**. Nếu `finance/config` không tồn tại hoặc Vault không phản hồi, đó chưa phải bằng chứng policy đã giới hạn quyền; phải xác nhận `403 permission denied` từ endpoint tương ứng hoặc capability `deny` của token.

### 10.3. Đo hoạt động thật mà không lộ bí mật

Các chỉ số có ích trong môi trường staging: số request login theo auth mount; tỷ lệ login thành công/thất bại; số lần renew/re-login; thời gian từ subscribe tới token; `403` ở endpoint login và KV; số lỗi TLS/timeout; số credential đã hết TTL hoặc quota.

Chỉ ghi định danh role đã được duyệt, request ID và loại lỗi. **Không** log `role_id`/`secret_id`, JWT, `VaultToken`, header `X-Vault-Token`, nội dung secret hay response body có credential. Bảo vệ audit log và cấu hình retention theo chính sách tổ chức.

## 11. Checklist triển khai và câu hỏi tự đánh giá

Trước khi dùng reactive login trong production:

- [ ] Đã chọn đúng Vault auth method cho workload và đặt ràng buộc role/ACL tối thiểu.
- [ ] `AuthenticationSteps` thể hiện đúng nguồn credential, bước chuyển đổi và endpoint login của mount.
- [ ] `AuthenticationStepsOperator` dùng client có TLS/CA, timeout và endpoint Vault `/v1/` được kiểm tra.
- [ ] Ứng dụng không gọi `.block()` trên WebFlux event loop; `Mono` được ghép và subscribe theo vòng đời request.
- [ ] Có `ReactiveSessionManager` chịu trách nhiệm tái sử dụng, làm mới/thay token và đóng phiên phù hợp.
- [ ] Có kế hoạch luân chuyển RoleID/SecretID hoặc JWT workload; không đặt credential trong code/log.
- [ ] Đã kiểm thử login thành công, login thất bại, truy cập KV bị ACL từ chối và trường hợp token hết hạn.
- [ ] Nếu dùng Transit hoặc PKI, đã kiểm tra ACL riêng trên những endpoint tương ứng; token login không tự cấp toàn quyền.

### Câu hỏi tự kiểm tra

1. `AuthenticationStepsOperator` khác `AuthenticationStepsExecutor` ở kết quả trả về và cách thực thi như thế nào?
2. Vì sao gọi `getVaultToken()` chưa chắc đã tạo một request HTTP? Thành phần nào kích hoạt luồng?
3. Khi dùng `AuthenticationSteps.fromSupplier(...).map(...).login(...)`, state object được sử dụng ở những thời điểm nào?
4. Vì sao không nên subscribe một `Mono` login mới trên mọi request của WebFlux?
5. Vai trò của `ReactiveLifecycleAwareSessionManager` khác với việc cache `Mono<VaultToken>` thủ công ra sao?
6. Login AppRole thành công nhưng `ReactiveVaultTemplate` nhận `403` khi đọc KV: nên điều tra auth role hay Vault ACL trước?
7. Nếu JWT/SecretID để re-login đã hết hạn, việc token hiện tại có thể gia hạn có đảm bảo dịch vụ luôn hoạt động không? Vì sao?
8. Khi dùng `opsForVersionedKeyValue("secret").get("orders/config")`, Vault API path nào cần được cấp quyền trong policy?

## Tài liệu tham khảo chính thức

- [Spring Vault — Authentication Methods và Authentication Steps](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — AuthenticationStepsOperator](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationStepsOperator.html)
- [Spring Vault API — AuthenticationSteps](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AuthenticationSteps.html)
- [Spring Vault — Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
- [Spring Vault API — ReactiveLifecycleAwareSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html)
- [Spring Vault API — ReactiveVaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html)

Điểm cần ghi nhớ: **`AuthenticationSteps` mô tả cách đăng nhập, `AuthenticationStepsOperator` thực thi flow theo reactive và phát `Mono<VaultToken>`, còn session manager quản lý vòng đời token để `ReactiveVaultTemplate` gọi các API Vault đúng chính sách.**
