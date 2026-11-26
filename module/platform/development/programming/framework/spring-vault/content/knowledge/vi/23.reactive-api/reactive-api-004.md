# ReactiveVaultClient trên các phiên bản Spring Vault có hỗ trợ

## 1. Mục tiêu và phạm vi

Trong chương **API reactive** của module **SPRING_VAULT**, ứng dụng Java có thể truy cập HashiCorp Vault để đọc KV secrets, mã hóa dữ liệu qua Transit, sử dụng PKI hoặc thực hiện các thao tác quản trị theo chính sách phân quyền. Với một ứng dụng WebFlux, mỗi request tới Vault đều là I/O mạng: nếu gọi bằng API đồng bộ trên event-loop, thời gian chờ mạng có thể làm nghẽn các request khác.

Spring Vault cung cấp hạ tầng reactive dựa trên Spring WebFlux và Reactor. Đặc biệt, kể từ **Spring Vault 4.1**, thư viện có thêm interface `org.springframework.vault.client.ReactiveVaultClient`: một **HTTP client fluent, non-blocking** dành riêng cho Vault, xây trên `WebClient` và biết cách xử lý endpoint, Vault token, namespace, request/response. Trước phiên bản đó, ứng dụng vẫn có API reactive qua `ReactiveVaultTemplate`/`ReactiveVaultOperations`.

Bài học tập trung vào **điều kiện phiên bản** và cách sử dụng client mới một cách an toàn. Sau bài, bạn có thể:

- Kiểm tra đúng Spring Vault version trước khi import `ReactiveVaultClient`.
- Chọn giữa `ReactiveVaultClient`, `ReactiveVaultTemplate`, `WebClient` và `VaultTemplate` theo nhu cầu.
- Cấu hình `VaultEndpoint`, HTTP connector, TLS, token, namespace và Vault policy.
- Gọi các endpoint như KV v2 hoặc Transit bằng `Mono`, phân biệt xử lý thành công, `404`, `403` và lỗi mạng.
- Tích hợp `ReactiveSessionManager` để token được cấp và gia hạn theo workload, thay cho gắn token cố định.
- Kiểm thử client bằng `WebClient ExchangeFunction` giả và `StepVerifier`, sau đó kiểm chứng với Vault thật trong môi trường cô lập.

> Các đường dẫn và tên như `kv-app`, `payments/config`, `transit/encrypt/payments-key`, `vault.example.internal` chỉ là ví dụ. Không đưa Vault token thật, JWT, AppRole SecretID, private key hay giá trị secret vào source code hoặc log.

## 2. Ma trận phiên bản: phân biệt ReactiveVaultClient và ReactiveVaultTemplate

**Điểm mấu chốt:** “Spring Vault có hỗ trợ reactive” và “Spring Vault có class `ReactiveVaultClient`” là hai mệnh đề khác nhau.

| Dòng Spring Vault | Reactive API có thể dùng | Điều cần biết |
|---|---|---|
| **2.x** (từ khi reactive support xuất hiện) | `ReactiveVaultTemplate`, `ReactiveVaultOperations`, `ReactiveSessionManager` | Có reactive template; **chưa có** fluent interface `ReactiveVaultClient` của 4.1. |
| **3.x** | `ReactiveVaultTemplate`, các reactive operations cho KV/Transit, WebClient callback | Dùng API template; **không import** `org.springframework.vault.client.ReactiveVaultClient` của 4.1. |
| **4.0.x** | Reactive template/operations và WebClient | Vẫn **chưa có** `ReactiveVaultClient` mới. |
| **4.1.x trở lên** | Các API reactive cũ **và** `ReactiveVaultClient` | Fluent client mới được giới thiệu ở **4.1**, thêm các constructor/integration dùng client này. |

Spring Vault **4.1 GA được công bố ngày 10/06/2026**. Vì vậy khi dự án dùng Spring Boot/Spring Cloud Vault, cần kiểm tra **dependency thực sự được resolve** thay vì mặc định code biên dịch được vì đọc Javadoc mới nhất.

Để kiểm tra trong Gradle:

~~~powershell
# Chỉ chạy ở dự án có Gradle; lệnh phục vụ kiểm tra dependency.
./gradlew dependencyInsight --dependency spring-vault-core --configuration runtimeClasspath
~~~

Hoặc trên Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.vault:spring-vault-core
~~~

Không nâng riêng `spring-vault-core` lên 4.1 chỉ để dùng interface mới khi Spring Boot/Spring Cloud Vault của hệ thống chưa tương thích. Cần kiểm tra BOM, Spring Framework/WebFlux, Reactor, Jackson, các starter và ma trận hỗ trợ của bản phát hành tương ứng. Nếu ứng dụng bắt buộc dùng Spring Vault 3.x/4.0, hãy sử dụng `ReactiveVaultTemplate` và các callback với `WebClient` đã có.

### 2.1. So sánh bốn lựa chọn

| Thành phần | Bản chất | Thích hợp khi |
|---|---|---|
| `VaultTemplate` | Template **đồng bộ** | Ứng dụng Servlet/batch hoặc code blocking bình thường. |
| `ReactiveVaultTemplate` | Reactive operations mức cao, có hỗ trợ session/token | Đọc/ghi KV, Transit hoặc API domain phổ biến trong WebFlux; mong muốn ít code HTTP. |
| `WebClient` | HTTP reactive tổng quát | Cần điều khiển HTTP ở mức thấp; tự chịu trách nhiệm URI Vault, token, headers và lỗi. |
| `ReactiveVaultClient` (**4.1+**) | HTTP reactive fluent dành cho Vault, xây trên WebClient | Cần gọi endpoint Vault đặc thù, điều khiển request/response nhưng muốn dùng xử lý endpoint, token, namespace của Vault. |

Sơ đồ phân lớp:

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B{Nhu cầu?}
    B -- CRUD/Transit chuẩn --> C[ReactiveVaultTemplate]
    B -- API Vault riêng/custom --> D[ReactiveVaultClient 4.1+]
    B -- Spring Vault 3.x/4.0 --> E[ReactiveVaultTemplate / WebClient callback]
    C --> F[ReactiveSessionManager / VaultTokenSupplier]
    D --> G[Token per request hoặc SessionManager]
    E --> F
    F --> H[WebClient / HTTP connector]
    G --> H
    H --> I[Vault HTTPS API]
~~~

## 3. Các API chính của ReactiveVaultClient 4.1+

Package chuẩn:

~~~java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;
~~~

Interface cung cấp các phương thức HTTP fluent `get()`, `post()`, `put()`, `delete()`, `method(HttpMethod)`; các phương thức dựng request như `path(...)`, `token(VaultToken)`, `namespace(String)`, `header(...)` và `bodyValue(...)`; các phương thức lấy kết quả như `retrieve().body()`, `bodyToMono(Type.class)`, `bodyToFlux(Type.class)`, `toEntity(...)`, `exchangeToMono(...)` hoặc `exchangeToFlux(...)`.

| Nhóm | API tiêu biểu | Hành vi |
|---|---|---|
| Khởi tạo | `create()`, `create(String)`, `create(VaultEndpoint)`, `builder()`, `builder(WebClient)` | Tạo client hoặc dựa trên WebClient cấu hình sẵn. |
| Endpoint | `builder().endpoint(VaultEndpoint)` | Giới hạn path tương đối tới Vault server đã cấu hình. |
| HTTP verbs | `get()`, `post()`, `put()`, `delete()` | Bắt đầu xây request, chưa gọi network ngay. |
| Path | `path("kv-app/data/payments/config")` | Path tương đối của **Vault API**; không gắn trước scheme/host. |
| Xác thực | `token(VaultToken)` | Gắn Vault client token cho request cụ thể. |
| Namespace | `namespace("team/payments")` | Gắn Vault namespace khi môi trường dùng Vault Enterprise namespaces. |
| Body | `bodyValue(Map.of(...))`, `body(publisher, Type.class)` | Ghi JSON hoặc dữ liệu từ reactive publisher. |
| Response | `retrieve().body()` | Trả `Mono<VaultResponse>`. |
| Response tùy chỉnh | `retrieve().bodyToMono(...)`, `exchangeToMono(...)` | Điều khiển kiểu dữ liệu/trạng thái HTTP và mapping. |
| Lỗi | `retrieve().onStatus(...)` | Thay đổi xử lý một số mã HTTP; mặc định lỗi 4xx/5xx trở thành error signal. |

Khác với `WebClient.get().uri(...)`, client mới sử dụng `path(...)` để định vị tài nguyên trong Vault. Khi tạo client bằng `VaultEndpoint`, **path không cần prefix `/v1`**; tầng client xây đường dẫn API phù hợp. Ví dụ:

| Mục đích | Vault API HTTP thực tế | Path truyền cho ReactiveVaultClient |
|---|---|---|
| Đọc KV v2 | `GET /v1/kv-app/data/payments/config` | `kv-app/data/payments/config` |
| Đọc metadata KV v2 | `GET /v1/kv-app/metadata/payments/config` | `kv-app/metadata/payments/config` |
| Transit encrypt | `POST /v1/transit/encrypt/payments-key` | `transit/encrypt/payments-key` |
| AppRole login | `POST /v1/auth/approle/login` | `auth/approle/login` |

**Phân biệt với Template KV v2:** khi gọi `ReactiveVaultTemplate.opsForVersionedKeyValue("kv-app").get("payments/config")`, thư viện tự chèn nhánh `data/`. Với `ReactiveVaultClient` cấp HTTP, **bạn phải chỉ rõ nhánh `data/` hoặc `metadata/`**.

## 4. Tạo client với endpoint, TLS và WebClient

Tạo client ngắn gọn, giả định server Vault đã có chứng thư TLS được JVM tin cậy:

~~~java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;

ReactiveVaultClient client = ReactiveVaultClient.create(
        VaultEndpoint.create("vault.example.internal", 8200));
~~~

`VaultEndpoint.create(host, port)` tạo endpoint **HTTPS**. Với URL khác như reverse proxy có base path hoặc cấu hình scheme riêng, dùng `VaultEndpoint.from(...)` và kiểm tra lại path thực tế. Không tắt xác minh TLS server hoặc hostname verification.

Trong Spring Boot, có thể cấu hình bean khi bạn **tự quản lý client**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;

@Configuration(proxyBeanMethods = false)
class VaultReactiveHttpConfiguration {

    @Bean
    ReactiveVaultClient reactiveVaultClient() {
        return ReactiveVaultClient.builder()
                .endpoint(VaultEndpoint.create("vault.example.internal", 8200))
                .build();
    }
}
~~~

**Chú ý auto-configuration:** `AbstractReactiveVaultConfiguration` ở Spring Vault 4.1 có thể tạo `ReactiveVaultClient` cùng `ReactiveVaultTemplate`. Không định nghĩa bean trùng khi cấu hình framework hoặc Spring Cloud Vault đã cấp bean phù hợp. Client ở trên chỉ là phần giao tiếp HTTP; nó chưa tự đăng nhập Vault và chưa có token để đọc secret được bảo vệ.

Nếu cần tùy biến pool/timeout/SSL, cấu hình `ClientHttpConnector` của WebFlux hoặc dùng:

~~~java
ReactiveVaultClient client = ReactiveVaultClient.builder()
        .endpoint(VaultEndpoint.create("vault.example.internal", 8200))
        .configureWebClient(webClientBuilder -> {
            // Thêm filter/codec/timeouts đã được phê duyệt.
            // Không log Authorization hoặc X-Vault-Token.
        })
        .build();
~~~

`builder(WebClient)` cũng cho phép tận dụng cấu hình WebClient được khởi tạo ở nơi khác. Khi làm vậy, xác minh WebClient có codec cho String, byte[], JSON và request URI thật sự trỏ về Vault. Một client không có endpoint sẽ yêu cầu URI tuyệt đối; nên cấu hình endpoint rõ để tránh nhầm server.

## 5. Đọc KV v2 bằng ReactiveVaultClient

Giả sử Vault KV v2 mount là `kv-app`, key path là `payments/config`, response dữ liệu Vault có dạng:

~~~json
{
  "data": {
    "data": {
      "mode": "demo",
      "region": "test"
    },
    "metadata": {
      "version": 3
    }
  }
}
~~~

Ở đây lớp `data` ngoài là wrapper KV v2, còn `data.data` mới là các key/value của secret. Với `ReactiveVaultClient`, tạo một method trả publisher mà không block:

~~~java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;

class Kv2RawReader {

    private final ReactiveVaultClient client;

    Kv2RawReader(ReactiveVaultClient client) {
        this.client = client;
    }

    // vaultToken ở đây chỉ là credential của request hiện tại.
    // Trong production lấy từ ReactiveSessionManager, xem mục 7.
    Mono<VaultResponse> readConfig(VaultToken vaultToken) {
        return client.get()
                .path("kv-app/data/payments/config")
                .token(vaultToken)
                .retrieve()
                .body()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Vault returned no body")));
    }
}
~~~

**Không gọi `block()` trong WebFlux controller hoặc scheduler event-loop.** Trả `Mono` cho caller và kết hợp với `map`, `flatMap`, `switchIfEmpty`. Một `Mono.empty()` có thể biểu thị không có body hoặc không tìm thấy dữ liệu tùy client/endpoint và status handling; không đồng nhất nó với lỗi “đúng quyền nhưng secret trống”. `403` nên đi vào error signal và được xử lý tách biệt.

Ví dụ xử lý dữ liệu nhận được:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;

Mono<String> loadRegion(VaultToken token) {
    return readConfig(token).flatMap(response -> {
        Map<String, Object> root = response.getData();
        if (root == null || !(root.get("data") instanceof Map<?, ?> secret)) {
            return Mono.error(new IllegalStateException(
                    "Invalid KV v2 response shape"));
        }
        Object region = secret.get("region");
        if (!(region instanceof String value) || value.isBlank()) {
            return Mono.error(new IllegalStateException(
                    "Required region is absent"));
        }
        return Mono.just(value);
    });
}
~~~

Thí dụ minh họa thao tác đọc, không khuyến khích đưa giá trị nhạy cảm của secret vào HTTP response hoặc log. Với ứng dụng chủ yếu thao tác KV v2, `ReactiveVaultTemplate` ở mục 8 sẽ xử lý wrapper và API phiên bản một cách tiện hơn.

## 6. Gửi HTTP body: Transit encryption

Khi dùng Vault Transit secrets engine, client có thể yêu cầu Vault mã hóa dữ liệu bằng một key do Vault quản lý. Endpoint minh họa:

~~~http
POST /v1/transit/encrypt/payments-key
Content-Type: application/json
X-Vault-Token: <token-duoc-cap-quyen>

{"plaintext":"ZGVtby1wYXlsb2Fk"}
~~~

Trường `plaintext` theo Transit API phải được **Base64-encode** trước khi gửi; đây là quy tắc biểu diễn payload, **không phải một lớp mã hóa bảo mật thay cho Transit/TLS**. Kết quả ciphertext thường nằm ở `data.ciphertext`, ví dụ chuỗi bắt đầu bằng `vault:v1:...`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;

public final class TransitRawClient {

    private final ReactiveVaultClient client;

    public TransitRawClient(ReactiveVaultClient client) {
        this.client = client;
    }

    public Mono<String> encryptDemo(VaultToken token) {
        String plaintext = Base64.getEncoder().encodeToString(
                "demo-payload".getBytes(StandardCharsets.UTF_8));

        return client.post()
                .path("transit/encrypt/payments-key")
                .token(token)
                .bodyValue(Map.of("plaintext", plaintext))
                .retrieve()
                .body()
                .flatMap(response -> {
                    Map<String, Object> data = response.getData();
                    if (data == null ||
                            !(data.get("ciphertext") instanceof String ciphertext)) {
                        return Mono.error(new IllegalStateException(
                                "Transit response does not contain ciphertext"));
                    }
                    return Mono.just(ciphertext);
                });
    }
}
~~~

Vault policy phải có capability `update` trên `transit/encrypt/payments-key`. Mã trên dùng một chuỗi demo; trong sản phẩm thực tế, xác định quy tắc lưu giữ plaintext/ciphertext, độ lớn payload, context/associated data nếu cần và không log input/output nhạy cảm. Với nhu cầu Transit thông thường, có thể dùng `ReactiveVaultTemplate.opsForTransit()` để giảm code xử lý HTTP và kiểu dữ liệu.

### 6.1. Các phương thức trả publisher

| API | Giá trị trả về | Khi dùng |
|---|---|---|
| `retrieve().body()` | `Mono<VaultResponse>` | Phản hồi JSON Vault thông thường |
| `retrieve().bodyToMono(MyDto.class)` | `Mono<MyDto>` | Có DTO riêng cho response của endpoint |
| `retrieve().bodyToFlux(MyDto.class)` | `Flux<MyDto>` | Endpoint có response phù hợp danh sách/stream; không tự suy diễn Vault endpoint nào cũng stream |
| `retrieve().toEntity(MyDto.class)` | `Mono<ResponseEntity<MyDto>>` | Cần status/headers cùng body |
| `retrieve().toBodilessEntity()` | `Mono<ResponseEntity<Void>>` | Request chỉ quan tâm thành công, ví dụ DELETE |
| `exchangeToMono(response -> ...)` | `Mono<T>` | Cần xử lý khác nhau theo HTTP status/content type |
| `exchangeToFlux(response -> ...)` | `Flux<T>` | Cần quyền truy cập `ClientResponse` và decode stream theo contract |

Lệnh `retrieve()` chỉ chuyển sang pha đọc response; **cần gọi một terminal method** như `body()` hoặc `toBodilessEntity()` và subscribe vào publisher thì mới có request thực tế. Không gọi `subscribe()` thủ công ngay trong service trả `Mono`, vì sẽ làm mất khả năng kiểm soát vòng đời request của caller.

## 7. Xác thực theo workload bằng ReactiveSessionManager

`ReactiveVaultClient` là một HTTP client và cung cấp `token(VaultToken)` cho từng request; **nó không tự phát hành, gia hạn hoặc đăng nhập lại Vault token** chỉ vì đã tạo bằng `ReactiveVaultClient.create(...)`.

Trong ứng dụng dùng Kubernetes auth, AppRole, AWS hoặc phương thức xác thực khác, nên để `VaultTokenSupplier`/`ReactiveSessionManager` xử lý việc lấy token. `ReactiveLifecycleAwareSessionManager` là một triển khai quản lý token, bao gồm renew, re-login và thu hồi token phù hợp với loại token. Trường hợp Kubernetes, credential JWT cần được đọc lại từ projected ServiceAccount token file khi cần đăng nhập mới.

Một service có thể nhận bean `ReactiveSessionManager` do cấu hình Spring Vault tạo ra, rồi kết hợp nó với fluent client:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

@Service
public final class PaymentsVaultGateway {

    private final ReactiveVaultClient client;
    private final ReactiveSessionManager sessions;

    public PaymentsVaultGateway(
            ReactiveVaultClient client,
            ReactiveSessionManager sessions) {
        this.client = client;
        this.sessions = sessions;
    }

    public Mono<VaultResponse> readPaymentsConfig() {
        return Mono.defer(() -> sessions.getSessionToken()
                .flatMap(token -> client.get()
                        .path("kv-app/data/payments/config")
                        .token(token)
                        .retrieve()
                        .body()))
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Secret or token unavailable")));
    }
}
~~~

**Điểm cần hiểu ở ví dụ:**

1. `sessions.getSessionToken()` trả `Mono<VaultToken>`; service không cần giữ một chuỗi token lâu dài hoặc tự gửi login trên mỗi request.
2. `Mono.defer(...)` trì hoãn việc lấy token cho đến khi một subscriber yêu cầu thực hiện. SessionManager tự quyết định dùng lại token đang còn hợp lệ hay lấy token khác.
3. `.token(token)` gắn token lấy được **cho request cụ thể**. Không đặt `defaultHeader("X-Vault-Token", "...")` cố định khi workload cần renew/re-login.
4. `switchIfEmpty` là chính sách của ứng dụng: ở đây coi thiếu token hoặc thiếu body là lỗi. Nếu sản phẩm cho phép secret không tồn tại, xử lý trường hợp đó có chủ đích thay vì làm sai lệch lỗi ACL.

**Giới hạn giả định:** cấu hình Spring đã phải tạo sẵn `ReactiveSessionManager` và `ReactiveVaultClient` đúng instance/endpoint; đoạn service không tự cấu hình credential Kubernetes hay AppRole. Với Spring Cloud Vault hoặc `AbstractReactiveVaultConfiguration`, đọc đúng cấu hình version trước khi thêm bean thủ công.

### 7.1. Namespace và Vault policy

Nếu Vault Enterprise dùng namespace, có thể chỉ rõ namespace cho request:

~~~java
return client.get()
        .path("kv-app/data/payments/config")
        .namespace("team/payments")
        .token(token)
        .retrieve()
        .body();
~~~

Đoạn code minh họa nằm **trong một phương thức trả `Mono<VaultResponse>`**, với biến `client` và `token` có sẵn. Namespace phải khớp tổ chức Vault, role và token đã được cấp. Không suy luận rằng chỉ thêm header namespace sẽ mở rộng quyền token.

Ví dụ policy tối thiểu cho thao tác đọc KV v2 và Transit encryption:

~~~hcl
path "kv-app/data/payments/config" {
  capabilities = ["read"]
}

path "transit/encrypt/payments-key" {
  capabilities = ["update"]
}
~~~

`read` ở KV v2 là quyền trên endpoint `data/`; `update` ở Transit encryption là quyền gọi endpoint mã hóa. Quyền phải gắn với Vault token từ workload authentication. Không cấp wildcard rộng hoặc quyền quản trị cho app chỉ để chạy ví dụ.

### 7.2. Khác biệt giữa token, lease và secret value

Vault client token có TTL/renewability riêng; database credentials hoặc PKI certificates có **lease/certificate lifecycle** riêng; KV v2 có **version history**. `ReactiveSessionManager` gia hạn/đăng nhập lại Vault token **không tự làm mới** mọi giá trị API key hoặc database connection pool mà ứng dụng đã giữ. Nếu secret cần rotation, phải có cơ chế lấy lại và đưa secret mới vào consumer ở tầng ứng dụng.

## 8. Khi nên ưu tiên ReactiveVaultTemplate

`ReactiveVaultTemplate` đã tồn tại **trước 4.1** và tiếp tục là lựa chọn tốt nếu ứng dụng thao tác theo các domain operations phổ biến. Từ Spring Vault 4.1, có thể dựng template từ `ReactiveVaultClient` và `VaultTokenSupplier`. Constructor có 2 tham số liên quan:

~~~java
// Spring Vault 4.1+, fragment minh họa wiring khi client
// và sessionManager đã được cấu hình đầy đủ.
ReactiveVaultTemplate template =
        new ReactiveVaultTemplate(client, sessionManager);
~~~

Trong đó `sessionManager` triển khai `VaultTokenSupplier` (ví dụ `ReactiveSessionManager`), giúp template lấy Vault token khi thực hiện request có xác thực. Constructor `new ReactiveVaultTemplate(client)` **không dùng `VaultTokenSupplier`**, phù hợp với một số kiến trúc Vault Agent đã xác thực thay ứng dụng; không dùng constructor đó khi app cần tự login Vault mà chưa có proxy auth được cấu hình.

Đọc KV v2 bằng API mức cao:

~~~java
import org.springframework.vault.core.ReactiveVaultOperations;
import reactor.core.publisher.Mono;

class ReactiveKvService {

    private final ReactiveVaultOperations vault;

    ReactiveKvService(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    Mono<?> readConfig() {
        return vault.opsForVersionedKeyValue("kv-app")
                .get("payments/config")
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("KV secret not found")));
    }
}
~~~

Không thêm `data/` vào key path khi gọi `opsForVersionedKeyValue`: template hiểu mount và phiên bản API. Dữ liệu trả về có thể là đối tượng versioned/domain riêng, nên ví dụ sử dụng `Mono<?>` để minh họa điểm khác với `VaultResponse` cấp HTTP. Trong ứng dụng thực tế, dùng đúng kiểu theo API/version và kiểm tra metadata/version khi cần CAS.

Các thao tác như `opsForTransit()`, `opsForSys()`, `read()`, `write()` và `list()` cũng có reactive variants. Chọn template để tận dụng các kiểu dữ liệu/validation sẵn có; chọn `ReactiveVaultClient` nếu cần endpoint đặc thù hoặc phải kiểm soát HTTP request chính xác.

### 8.1. Nếu đang dùng Spring Vault 3.x hoặc 4.0

Không viết:

~~~java
// KHÔNG biên dịch trên Spring Vault trước 4.1
ReactiveVaultClient client = ReactiveVaultClient.create();
~~~

Thay vào đó, dùng `ReactiveVaultTemplate` có session và client connector được cấu hình theo phiên bản đang sử dụng, hoặc callback `doWithSession(webClient -> ...)` cho request được xác thực:

~~~java
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

Mono<VaultResponse> readRaw(ReactiveVaultOperations vault) {
    return vault.doWithSession(webClient -> webClient.get()
            .uri("kv-app/data/payments/config")
            .retrieve()
            .bodyToMono(VaultResponse.class));
}
~~~

Đây là ví dụ callback **dành cho kiến trúc dùng WebClient từ template**; cú pháp và URI resolution phụ thuộc cấu hình `ReactiveVaultTemplate` thực tế. Callback `doWithSession` cấp session context; không tự thêm token header hoặc cố truyền URL ngoài Vault. Nếu cần thô hơn nữa, có thể dùng trực tiếp `WebClient` đã cấu hình, nhưng phải tự bảo đảm token, TLS, namespace, URI và xử lý lỗi.

## 9. Lỗi HTTP và Reactor: phân biệt 404, 403, lỗi mạng

`ReactiveVaultClient.retrieve()` xử lý trạng thái HTTP theo contract của client:

| Tình huống | Hành vi thông thường | Hướng xử lý |
|---|---|---|
| HTTP 2xx với JSON hợp lệ | `Mono<VaultResponse>` có dữ liệu | Kiểm tra schema/field cần thiết, không in secret |
| HTTP 204 hoặc body rỗng | Publisher có thể hoàn thành không có body | Với DELETE dùng `toBodilessEntity()`; không ép body JSON |
| HTTP 404 | Mặc định tạo error signal từ phản hồi HTTP | Chỉ chuyển thành `Mono.empty()` khi **business rule** xác định vắng mặt là hợp lệ |
| HTTP 401 / 403 | Token không hợp lệ, hết hạn hoặc policy thiếu quyền tùy request | Xác minh Vault auth method, session token, policy và endpoint; không tự xin quyền rộng |
| HTTP 429 hoặc 5xx | Vault bị giới hạn tải hoặc có sự cố tạm thời | Retry có giới hạn khi idempotent, dùng backoff/jitter/deadline |
| TLS/DNS/connection timeout | Không hoàn tất HTTP exchange | Kiểm tra CA, TLS, địa chỉ, network policy, timeout; không xem như secret missing |
| JSON sai định dạng hoặc field thiếu | Deserialization/validation lỗi | Chặn sử dụng dữ liệu; phân biệt response của KV v1 và KV v2 |

Theo Javadoc Spring Vault 4.1, lỗi status từ request được biểu diễn bằng những ngoại lệ kế thừa `VaultClientResponseException`. Khi xử lý lỗi, giữ phân biệt giữa request đọc KV bị `403` do policy và request `auth/kubernetes/login` bị `403` do xác thực: cùng status HTTP nhưng nguồn lỗi khác nhau.

### 9.1. Chỉ biến 404 thành empty khi được phép

~~~java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultClientResponseException;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import reactor.core.publisher.Mono;

Mono<VaultResponse> findOptionalSecret(
        ReactiveVaultClient client, VaultToken token) {

    return client.get()
            .path("kv-app/data/payments/optional")
            .token(token)
            .retrieve()
            .body()
            .onErrorResume(VaultClientResponseException.class, ex ->
                    ex.getStatusCode().value() == 404
                            ? Mono.empty()
                            : Mono.error(ex));
}
~~~

Đoạn code đặt chính sách **chỉ với secret tùy chọn**. Với password hoặc credential bắt buộc, `404` phải dẫn đến lỗi rõ ràng thay vì tự cài giá trị rỗng. Tuyệt đối không bắt `VaultClientResponseException` rồi luôn trả `Mono.empty()`: cách đó che mất lỗi `403`, `500` và sự cố TLS.

### 9.2. Khi cần phân tích response sâu hơn

`exchangeToMono(...)` nhận `ClientResponse` và cho phép tự quyết định cách decode. Ví dụ:

~~~java
Mono<VaultResponse> response = client.get()
        .path("kv-app/data/payments/config")
        .token(token)
        .exchangeToMono(http -> {
            if (http.statusCode().is2xxSuccessful()) {
                return http.bodyToMono(VaultResponse.class);
            }
            return http.createError();
        });
~~~

Ở đây `client` và `token` là biến đã có trong phương thức hiện hành. Nếu callback cần xử lý một response lỗi cụ thể, phải tiêu thụ hoặc giải phóng body đúng contract. Sau khi publisher hoàn tất, WebClient sẽ giải phóng phần body chưa sử dụng; không giữ tham chiếu `ClientResponse` hoặc buffer ngoài vòng đời publisher.

### 9.3. Retry an toàn trong hệ thống reactive

Ví dụ về giới hạn thời gian và retry **chỉ với tác vụ đọc idempotent**, sau khi đã xác nhận lỗi là tạm thời:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<VaultResponse> guardedRead = findOptionalSecret(client, token)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(error -> isTransientNetworkOrServerError(error)));
~~~

`isTransientNetworkOrServerError` là **hàm phân loại lỗi do ứng dụng tự triển khai**; ví dụ này không thể copy chạy nếu chưa định nghĩa nó. Hàm cần chỉ chấp nhận lỗi mạng/tạm thời hoặc HTTP 429/5xx phù hợp; không retry `403`, lỗi credential sai hay lỗi format. Thiết lập deadline tổng, không chỉ timeout per-attempt nếu cần SLA chặt. Không tự động retry các request ghi KV, cấp PKI certificate hay thao tác khác có side effect khi chưa xác định idempotency và trạng thái xử lý ở server.

## 10. Tính reactive thực chất: subscription, concurrency và backpressure

Chỉ sử dụng `Mono` không đảm bảo một chương trình là non-blocking nếu code vẫn gọi `block()` hoặc dùng JDBC/file I/O đồng bộ ngay trên event-loop.

**Quy tắc chính:**

1. **Cold publisher:** một HTTP request thường chỉ được thực hiện khi có subscription; mỗi lần subscribe lại có thể tạo request mới. Không tự gọi `subscribe()` trong service rồi cũng trả về publisher cho controller vì có thể tạo request đôi.
2. **Không block event-loop:** tránh `block()`, `Thread.sleep()`, đọc file/keystore chậm hay gọi thư viện JDBC đồng bộ trong `map`/`flatMap`.
3. **Token không phải secret cache:** `ReactiveSessionManager` quản lý session token, còn KV cache của ứng dụng có thời gian sống và chiến lược refresh riêng.
4. **Giới hạn số request song song:** khi đọc nhiều KV keys, sử dụng giới hạn concurrency của `flatMap`, timeout và rate limiting. Không tạo hàng nghìn request đồng thời trong lúc Vault đang bị quá tải.
5. **Phân loại retry:** không retry theo kiểu “mọi exception đều retry”, nhất là khi lỗi do thiếu quyền hoặc request có side effect.
6. **Cẩn thận với trace/logging:** WebClient filter, HTTP wire logs và Reactor hooks có thể vô tình ghi token, payload KV/Transit và certificate material. Luôn che `X-Vault-Token`, `Authorization` và request body nhạy cảm.

Ví dụ đọc một danh sách **đã cho phép** trong ứng dụng:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

List<String> allowedPaths = List.of(
        "kv-app/data/payments/config",
        "kv-app/data/payments/features",
        "kv-app/data/payments/limits");

Flux<VaultResponse> stream = Flux.fromIterable(allowedPaths)
        .flatMap(path -> sessions.getSessionToken().flatMap(token ->
                client.get()
                        .path(path)
                        .token(token)
                        .retrieve()
                        .body()), 3);
~~~

Ví dụ là **đoạn trích trong một service có biến `sessions` và `client` đã được cấu hình**. Có giới hạn concurrency bằng `3`. Danh sách path phải là **allowlist do ứng dụng quản lý**, không lấy trực tiếp path tùy ý từ untrusted request để tạo truy vấn Vault. Nếu cần đưa dữ liệu động vào URI template, kiểm tra quy tắc URL encoding của `WebClient` (đặc biệt với dấu `/`) và kiểm chứng URI thực tế trong HTTP mock test.

## 11. Bảo mật khi dùng API HTTP fluent

Fluent client cho quyền kiểm soát HTTP lớn hơn template, vì vậy ứng dụng cũng chịu thêm trách nhiệm:

| Rủi ro | Hành động phòng tránh |
|---|---|
| Token bị hard-code/đóng băng | Lấy token tại thời điểm request qua `ReactiveSessionManager`; không lưu token trong mã nguồn |
| Vượt phạm vi endpoint | Khởi tạo bằng `VaultEndpoint`; ưu tiên `path(...)` tương đối với các path được phép |
| Gửi token tới host ngoài ý muốn | **Không** xây `URI` tuyệt đối từ input không tin cậy; `uri(URI)` có thể dùng một URL tuyệt đối khác endpoint |
| Sai KV v2 API | Dùng `data/` cho đọc/ghi dữ liệu, `metadata/` cho metadata; tốt nhất dùng template KV v2 khi có thể |
| Namespace sai | Chỉ gắn namespace từ cấu hình đã xác minh và policy đúng workload |
| Bỏ qua TLS | Dùng HTTPS, truststore đúng CA, xác minh hostname và client cert nếu dùng mTLS |
| Log rò rỉ | Redact token, Authorization, Vault response data và các credential/ciphertext nhạy cảm |
| Quyền quá rộng | Vault policy chỉ cấp capability trên đúng mount/key hoặc Transit key |
| Retry nguy hiểm | Chỉ retry lỗi tạm thời, khi request idempotent hoặc có cơ chế chống lặp rõ ràng |

**Cảnh báo về URI tuyệt đối:** Javadoc `ReactiveVaultClient.PathSpec.uri(URI)` cho phép truyền `URI` đã dựng; URI tuyệt đối có thể được sử dụng nguyên trạng. Nếu gắn Vault token và dùng URL do người dùng gửi, có nguy cơ gửi token tới host khác. Do đó không mở endpoint kiểu `/vault/proxy?url=...` rồi truyền URL đó vào client đã xác thực. Hãy định nghĩa những đường dẫn API Vault cố định và kiểm soát input thật sự cần biến đổi.

## 12. Kiểm thử ReactiveVaultClient không cần Vault server

Có thể dùng `WebClient` với `ExchangeFunction` giả. Test chạy **client thật** nhưng chặn HTTP ở ranh giới network, xác nhận đúng path/header và giải mã body với `StepVerifier`.

### 12.1. Test đọc KV v2 thành công

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveVaultClientTest {

    @Test
    void readsKvV2WithExpectedEndpointAndFakeToken() {
        AtomicReference<ClientRequest> observed = new AtomicReference<>();

        ExchangeFunction fakeHttp = request -> {
            observed.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE,
                            MediaType.APPLICATION_JSON_VALUE)
                    .body("""
                        {
                          "data": {
                            "data": {"region": "test"},
                            "metadata": {"version": 3}
                          }
                        }
                        """)
                    .build());
        };

        WebClient webClient = WebClient.builder()
                .exchangeFunction(fakeHttp)
                .build();

        ReactiveVaultClient client = ReactiveVaultClient
                .builder(webClient)
                .endpoint(VaultEndpoint.create("vault.test.invalid", 8200))
                .build();

        Mono<VaultResponse> result = client.get()
                .path("kv-app/data/payments/config")
                .token(VaultToken.of("fake-test-token"))
                .retrieve()
                .body();

        // Chưa subscribe: chưa có HTTP exchange.
        assertNull(observed.get());

        StepVerifier.create(result)
                .assertNext(response -> {
                    assertNotNull(response.getData());
                    Object secret = response.getData().get("data");
                    assertTrue(secret instanceof Map<?, ?>);
                    assertEquals("test", ((Map<?, ?>) secret).get("region"));
                })
                .verifyComplete();

        assertNotNull(observed.get());
        assertEquals(HttpMethod.GET, observed.get().method());
        assertEquals("/v1/kv-app/data/payments/config",
                observed.get().url().getPath());
        assertEquals("fake-test-token",
                observed.get().headers().getFirst("X-Vault-Token"));
    }
}
~~~

Giá trị `fake-test-token` là **token giả**, chỉ dành cho test. Trong môi trường thực, không assert/log token thật thành một chuỗi cố định. Test còn chứng minh request chỉ xảy ra khi subscribe; nếu không có publisher terminal và subscription thì Vault không nhận request.

### 12.2. Test lỗi 403

Dùng cùng kiểu `ExchangeFunction` để trả status lỗi. Ví dụ nhỏ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultClientResponseException;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.support.VaultToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveVaultClientForbiddenTest {

    @Test
    void returnsErrorWhenVaultDeniesRequest() {
        WebClient webClient = WebClient.builder()
                .exchangeFunction(request -> Mono.just(
                        ClientResponse.create(HttpStatus.FORBIDDEN)
                                .body("{\"errors\":[\"permission denied\"]}")
                                .build()))
                .build();

        ReactiveVaultClient client = ReactiveVaultClient
                .builder(webClient)
                .endpoint(VaultEndpoint.create("vault.test.invalid", 8200))
                .build();

        StepVerifier.create(client.get()
                        .path("kv-app/data/payments/config")
                        .token(VaultToken.of("fake-denied-token"))
                        .retrieve()
                        .body())
                .expectError(VaultClientResponseException.class)
                .verify();
    }
}
~~~

Test chỉ xác nhận **hành vi client khi Vault trả 403**, không chứng minh Vault policy ngoài đời thật đã chặn đúng workload. Phải có integration test với role/policy riêng trên một Vault test server để xác minh quyền thực tế.

### 12.3. Bộ kiểm thử tích hợp nên bao phủ

| Case | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| KV v2 đọc được | Vault dev/Testcontainers, role chỉ `read` một key | `Mono` trả dữ liệu đúng wrapper/metadata |
| KV v2 404 | Đọc key test không tồn tại | Chính sách app phân biệt missing và unauthorized |
| KV v2 403 | Token không có `read` tại key khác | Error signal, không che thành dữ liệu rỗng |
| Token hết hạn | Role TTL ngắn, session manager đang hoạt động | Re-login/renew theo lifecycle; không giữ token tĩnh |
| Transit encryption | Role được `update` trên đúng key Transit | Ciphertext hợp lệ; mã hóa/giải mã theo contract |
| Timeout/5xx | Mô phỏng Vault outage trên lab | Deadline, backoff và cảnh báo hoạt động; không retry vô hạn |
| Endpoint scope | Mock một URI tuyệt đối khác host | Test chặn đường dẫn không được phép, tránh gửi token ra ngoài |
| Multi-subscription | Subscribe publisher hai lần | Request count phản ánh hai lần thực thi nếu không có cache chủ động |
| Shutdown/Pod restart | Tạo session mới | Workload đăng nhập lại an toàn bằng credential hiện hành |

Một mock HTTP hoặc unit test **không thay thế** cho kiểm tra cấu hình TLS, role, namespace, policy và tương thích Vault server. Ngược lại, integration test không nên dùng credential production; tạo secrets và policies test cô lập, dọn chúng sau khi hoàn tất.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Cannot resolve symbol ReactiveVaultClient` | Dùng `spring-vault-core` trước 4.1 hoặc sai package | Kiểm tra dependencyInsight; dùng `ReactiveVaultTemplate` ở phiên bản cũ |
| `NoClassDefFoundError` khi khởi động | Trộn Spring Vault mới với Spring Framework/WebFlux không tương thích | Đồng bộ BOM/starter, kiểm tra dependency tree |
| HTTP 404 cho KV v2 | Dùng `kv-app/payments/config` thay vì `kv-app/data/payments/config` hoặc mount sai | Kiểm tra đường dẫn KV v2; dùng template versioned để giảm nhầm lẫn |
| HTTP 403 cho request có token | Token hết hạn hoặc Vault policy không có quyền endpoint | Kiểm tra auth/TTL/ACL; phân biệt login failure và resource authorization |
| Request gửi sai host hoặc `/v1/v1/...` | Ghép URL/prefix sai hoặc dùng URI tuyệt đối | Dùng `VaultEndpoint` và `path(...)` tương đối; mock URI |
| Không thấy request nào thực thi | Quên subscribe publisher hoặc chỉ gọi `retrieve()` | Trả `Mono` cho caller và dùng terminal `body()`/`toBodilessEntity()` |
| Event-loop bị nghẽn | Gọi `block()` hay xử lý file/JDBC blocking trong pipeline | Giữ thao tác non-blocking; đưa blocking I/O ra scheduler chuyên dụng khi bắt buộc |
| Token cũ vẫn được gửi | Dùng `defaultHeader("X-Vault-Token", ... )` cố định | Lấy token qua `ReactiveSessionManager` per request |
| Lỗi TLS handshake | Truststore/CA, hostname, client certificate hoặc TLS proxy sai | Sửa trust và connector; không tắt xác minh TLS |
| Lỗi JSON parse | Mock sai schema, codec thiếu hoặc Vault response khác kiểu | Cấu hình Jackson codec, xác minh response contract |
| Retry làm tăng tải Vault | Retry mọi lỗi hoặc không giới hạn concurrency | Giới hạn request, retry chỉ lỗi tạm thời và idempotent |

## 14. Bài tập thực hành và checklist

**Bài tập A — Lựa chọn theo phiên bản:** xác nhận version `spring-vault-core` của dự án. Nếu thấp hơn 4.1, viết cách đọc KV v2 bằng `ReactiveVaultTemplate`; nếu từ 4.1, viết thêm `ReactiveVaultClient.get().path(...).retrieve().body()`.

**Bài tập B — KV v2:** mock GET `/v1/kv-app/data/payments/config` với response 200 chứa `data.data`; dùng `StepVerifier` kiểm tra một giá trị không nhạy cảm và completion. Lặp lại với 404 và 403, phân biệt kết quả.

**Bài tập C — Transit:** mock POST `/v1/transit/encrypt/payments-key`; kiểm tra JSON body có trường `plaintext` Base64, và reply có `data.ciphertext`. Không dùng plaintext thật trong fixture.

**Bài tập D — Token lifecycle:** chạy một Vault lab với workload auth, tạo `ReactiveSessionManager` và client kết hợp qua `flatMap`. Dùng role TTL ngắn trong test để kiểm tra renew hoặc login mới, xác minh không hard-code token vào bean.

**Bài tập E — Lỗi mạng:** mock HTTP 503/timeout, áp dụng `retryWhen` có giới hạn. Đảm bảo `403` không bị retry liên tục, không log secret khi lỗi.

Tiêu chí nghiệm thu:

- [ ] Đã kiểm tra version/BOM; không gọi `ReactiveVaultClient` trên Spring Vault trước 4.1.
- [ ] HTTP client cấu hình `VaultEndpoint` HTTPS và connector/TLS theo policy.
- [ ] Request dùng path Vault API tương đối chính xác; KV v2 có `data/` khi dùng client mức thấp.
- [ ] Token đến từ workload/session manager, có TTL và re-login được quản lý.
- [ ] Không gọi `block()` trên event-loop; publisher có terminal operation và subscriber phù hợp.
- [ ] `404`, `403`, timeout, `5xx` và response schema sai được phân loại khác nhau.
- [ ] Retry có giới hạn, chỉ dùng khi an toàn; concurrency được kiểm soát.
- [ ] Token, JWT, SecretID, Transit payload, PKI private key không xuất hiện trong source/log/trace.
- [ ] Có unit test HTTP mock + `StepVerifier` và integration test Vault cô lập.

## 15. Tổng kết

**`ReactiveVaultClient` là fluent reactive HTTP API mới từ Spring Vault 4.1**, sử dụng `WebClient` làm nền tảng, cung cấp thao tác HTTP, Vault endpoint, token, namespace và phản hồi dưới dạng `Mono`/`Flux`. Trong những bản Spring Vault trước 4.1, ứng dụng vẫn có thể làm việc non-blocking với Vault qua `ReactiveVaultTemplate` hoặc callback `WebClient` phù hợp.

Để dùng đúng trong sản phẩm Java: kiểm tra version thực tế, cấu hình Vault endpoint và TLS an toàn, đưa token qua `ReactiveSessionManager`, dùng path chính xác cho KV v2/Transit, giữ pipeline không chặn và kiểm thử cả đường thành công lẫn lỗi. Khi logic chỉ cần KV/Transit chuẩn, `ReactiveVaultTemplate` thường gọn hơn; khi cần điều khiển HTTP endpoint đặc thù, `ReactiveVaultClient` từ 4.1 mang lại khả năng cấu hình rõ ràng.

## Tài liệu tham khảo

- Spring Vault 4.1 API — [`ReactiveVaultClient`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.html), giới thiệu từ 4.1.
- Spring Vault 4.1 API — [`ReactiveVaultClient.Builder`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.Builder.html).
- Spring Vault 4.1 API — [`ReactiveVaultClient.ResponseSpec`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.ResponseSpec.html).
- Spring Vault Reference — [Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html).
- Spring Vault Reference — [Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html).
- Spring Vault 4.1 API — [`ReactiveVaultTemplate`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html) và [`ReactiveVaultOperations`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultOperations.html).
- Spring Vault 4.1 API — [`ReactiveSessionManager`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveSessionManager.html) và [`ReactiveLifecycleAwareSessionManager`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html).
- Spring Blog — [Spring Vault 4.1 Generally Available (10/06/2026)](https://spring.io/blog/2026/06/10/spring-vault-4-1-available/).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- HashiCorp Vault — [KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2) và [Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit).
