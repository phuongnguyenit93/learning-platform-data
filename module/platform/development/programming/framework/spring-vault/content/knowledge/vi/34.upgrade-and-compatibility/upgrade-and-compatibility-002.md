# Chuyển API RestTemplate cũ sang lựa chọn phù hợp dòng đích trong Spring Vault

## 1. Bài toán nâng cấp: không chỉ thay tên lớp HTTP client

Trong module **SPRING_VAULT**, ứng dụng Java sử dụng `VaultTemplate`/`VaultOperations` để làm việc với HashiCorp Vault: KV secrets, xác thực workload, token/lease, Transit encryption, PKI, xử lý lỗi và kiểm thử tích hợp. Một ứng dụng cũ có thể đang tùy chỉnh `RestTemplate` bên dưới Spring Vault hoặc gọi thẳng `RestOperations` từ callback `doWithSession()`. Khi nâng cấp thư viện, không nên tìm và thay toàn bộ chuỗi `RestTemplate` bằng `RestClient` một cách máy móc.

Vấn đề thực sự là **chọn lớp trừu tượng phù hợp dòng phiên bản đích**, đồng thời giữ nguyên những đặc tính an toàn: endpoint cố định, HTTPS/TLS, namespace, danh tính workload, header `X-Vault-Token`, JSON mapping, lỗi HTTP và vòng đời token/lease.

Ví dụ service đang dùng:

```java
VaultResponse response =
        vaultOperations.read("secret/data/orders/config");
```

Nếu nâng Spring Vault từ dòng 3.x sang 4.1, nghiệp vụ trên **không nhất thiết phải đổi API**. `VaultOperations` vẫn là interface chính và `VaultTemplate` vẫn cung cấp thao tác domain. Phần cần kiểm tra, thay đổi nhiều hơn là **khởi tạo client, tầng HTTP, customization, callback cấp thấp, xử lý lỗi và thư viện tương thích**.

Ngược lại, một đoạn code cũ truy cập trực tiếp `RestTemplate` có thể đã tự thiết lập header token, sử dụng URI tuyệt đối, interceptors, `ResponseErrorHandler` hoặc logic retry. Nếu chỉ đổi sang client mới mà không kiểm thử, một header xác thực có thể biến mất hoặc tệ hơn: được gửi tới endpoint không được phép.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt lựa chọn được hỗ trợ ở Spring Vault **3.x**, **4.0** và **4.1**.
- Xác định trường hợp **giữ `VaultOperations`**, trường hợp dùng **`VaultClient`**, **`RestClient`** hoặc nhánh reactive.
- Chuyển cấu hình từ `RestTemplateBuilder`/`RestTemplateCustomizer` sang API phù hợp với dòng đích.
- Giữ nguyên authentication, namespace, TLS, timeout, serialization và error semantics.
- Lập kế hoạch nâng cấp, kiểm thử hồi quy, phát hiện API deprecated và kiểm tra bản vá bảo mật.

## 2. Bản đồ phiên bản: chọn đúng dòng đích trước khi sửa code

**Mốc tài liệu đối chiếu: 25/11/2026.** Theo công bố Spring ngày **19/11/2026**, hai bản bảo trì được phát hành là **Spring Vault 4.0.5** và **4.1.2**. Chúng chứa bản vá cho **CVE-2026-41698 — Path Traversal via unsanitized secret path parameter**. Đây là thông tin có ngày cụ thể, không phải cam kết rằng các phiên bản này sẽ luôn mới nhất trong tương lai.

| Dòng Spring Vault | Tầng HTTP / lựa chọn chính | Quyết định khi chuyển từ code cũ |
| --- | --- | --- |
| **3.x** (ví dụ 3.2.x) | `VaultTemplate` dựa trên `RestTemplate`; hỗ trợ `RestTemplateBuilder` và callback `RestOperations` | Giữ API tương thích nếu chưa nâng dependency; cô lập code HTTP thủ công để dễ chuyển sau |
| **4.0.x** | Có thêm `RestClientBuilder` và constructor `VaultTemplate(RestClientBuilder, ...)`; API domain tiếp tục hoạt động | Nếu đích là 4.0, cân nhắc `RestClientBuilder`; không dùng `VaultClient` vì API này **chỉ có từ 4.1** |
| **4.1.x** | Có **`VaultClient`** (sync) và **`ReactiveVaultClient`** (reactive); `VaultTemplate` xây trên `VaultClient` | Ưu tiên `VaultOperations` cho domain hoặc `VaultClient` cho HTTP Vault cấp thấp; nhiều API `RestTemplate` đã **deprecated** |
| **Bản vá trong cùng dòng** | API lớn thường ổn định nhưng lỗi bảo mật/bug vẫn có thể được sửa | Dùng patch mới đã được tổ chức phê duyệt, chạy lại regression/security test |

**Deprecated khác với removed:** ví dụ `RestTemplateBuilder`, `RestTemplateCustomizer`, `RestTemplateFactory`, một số constructor `VaultTemplate` và `VaultClients.createNamespaceInterceptor` được đánh dấu **deprecated từ 4.1**, nhưng điều đó **không có nghĩa mọi API lập tức bị xóa trong 4.1**. Việc deprecated là dấu hiệu cần lên kế hoạch chuyển trước khi nâng đến một major/minor về sau có thể loại bỏ chúng.

### 2.1. Tương thích hệ sinh thái quan trọng ngang API

Không chọn version Spring Vault độc lập với các thành phần còn lại:

| Thành phần | Phải kiểm tra |
| --- | --- |
| **Java runtime** | Spring Vault 4.1 yêu cầu Java **17+**; xem baseline cụ thể của dòng đích |
| **Spring Framework** | Dòng 4.1 sử dụng thế hệ Spring Framework **7.x**; chọn bản sửa lỗi phù hợp với tài liệu dependencies |
| **Spring Boot / Spring Cloud Vault** | Dùng BOM/release train **tương thích**, không chỉ ép override version của `spring-vault-core` |
| **Jackson** | Kiểm tra `jackson-databind`, JSON converters; Spring Vault 4.x hỗ trợ Jackson 2/3 tùy classpath, **ưu tiên Jackson 3 khi cả hai có mặt** |
| **HTTP stack** | Apache HttpClient, JDK HttpClient, Jetty, Reactor Netty... cùng các timeout, pool, TLS |
| **Vault server/engine API** | Mount, KV v1/v2, Transit, PKI, token/lease, namespace và quyền ACL |

Đặc biệt, **Spring Vault 4.x không tự kéo Jackson vào mọi trường hợp như một dependency bắt buộc**. Đối với client gửi/nhận JSON, phải bảo đảm converter tương thích tồn tại. Dự án build thành công không đủ để kết luận JSON payload từ KV/Transit/PKI sẽ serialize và deserialize đúng ở runtime.

## 3. Quy tắc chọn abstraction theo nhu cầu thực

| Nhu cầu | Lựa chọn ưu tiên | Lý do |
| --- | --- | --- |
| Đọc/ghi KV, Transit, PKI, token, lease, system API đã có abstraction | **`VaultOperations`/`VaultTemplate`** | Giảm boilerplate HTTP, tái sử dụng SessionManager và domain semantics |
| Gọi một endpoint Vault chưa có domain API trong **Spring Vault 4.1+** | **`VaultClient`** | Fluent, hiểu Vault endpoint/namespace/token, hỗ trợ response wrapper |
| Gọi endpoint Vault cấp thấp trong **4.0.x** | `RestClientBuilder` + `VaultTemplate` hoặc `RestClient` được cấu hình phù hợp | `VaultClient` chưa tồn tại |
| Có custom legacy `RestTemplate` tại **3.x** | Giữ và cô lập sau adapter | Chưa phải lúc để dùng API chỉ có từ 4.0/4.1 |
| Framework-level code cần kiểm soát HTTP tuyệt đối | `RestClient` + endpoint/TLS/auth tự quản | Linh hoạt nhưng caller phải gánh trách nhiệm về path/header/JSON/error |
| Ứng dụng reactive dùng WebFlux | **`ReactiveVaultOperations`** cho domain; **`ReactiveVaultClient`** từ 4.1 cho HTTP Vault thấp | Tránh gọi blocking client trên event loop |
| Ứng dụng dùng **Spring Cloud Vault auto-configuration** | Giữ bean/config của framework và customizer phù hợp phiên bản | Không tự dựng client/session manager thứ hai nếu không cần |

**Không có lý do tự động thay `VaultTemplate` bằng `RestClient` thuần.** `RestClient` là API HTTP tổng quát của Spring Framework; không tự nhận biết policy, token refresh, Vault-specific error, versioned KV hay định dạng response của từng engine. `VaultClient` thì dành riêng cho Vault, nhưng **khi dùng trực tiếp vẫn phải chỉ định danh tính hoặc tích hợp auth đúng cách**.

## 4. Trước khi nâng: tìm điểm phụ thuộc thực sự vào RestTemplate

Kiểm tra các loại code sau trong phạm vi module ứng dụng đang nâng:

1. Constructor `VaultTemplate(RestTemplateBuilder, ...)` hoặc `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, ...)`.
2. Customizer `RestTemplateCustomizer`, `RestTemplateFactory`, `RestTemplateRequestCustomizer`.
3. Tự gọi `VaultClients.createRestTemplate()` hoặc `createNamespaceInterceptor()`.
4. Subclass `VaultTemplate` override `doCreateRestTemplate()`, `doCreateSessionTemplate()`, `doCreateRestClient()`.
5. Callback `vaultOperations.doWithVault(...)`/`doWithSession(...)` dùng `RestOperations`.
6. Tự gắn `X-Vault-Token`, `X-Vault-Namespace`, response wrapping và HTTP error handler.
7. Tự cấu hình TLS truststore, hostname verification, proxy, connection pool, retry, connect/read timeout.
8. Nhiều `RestTemplate` cho hai loại endpoint khác nhau: **Vault** và **cloud metadata service** (AWS/Azure/GCP). Đây là hai miền tin cậy phải giữ tách biệt.

Không chỉ tìm tên import. Hãy lập bảng “**component → mục đích → owner của auth/session → target API → regression test**”. Có hệ thống dùng `RestTemplate` để gọi Vault API thông qua `doWithSession`, nhưng cũng dùng `RestTemplate` để đăng nhập qua Azure instance metadata. Di chuyển cả hai vào một `VaultClient` chung sẽ không đúng: `VaultClient` phải giới hạn cho Vault server, còn cloud metadata là một HTTP client/connector khác.

### Cảnh báo về secret path

Mọi path được ứng dụng ghép từ input bên ngoài phải được **validate và giới hạn allowlist**. Không cho người dùng tùy ý truyền URI tuyệt đối, `../`, `..` trong phân đoạn hoặc percent-encoding nguy hiểm rồi ghép vào Vault endpoint. `VaultClient` 4.1 cung cấp mô hình relative path chặt hơn, nhưng **các đường truy cập từ `VaultOperations` và cấu hình cũ vẫn cần được kiểm tra theo hợp đồng API**. Sử dụng phiên bản đã được vá bảo mật và kiểm thử riêng trường hợp traversal.

## 5. Ví dụ: nâng cấu hình client từ 3.x lên dòng 4.1

Trong ví dụ, các object `endpoint`, `requestFactory`, `sessionManager` được cung cấp từ cấu hình đáng tin cậy của ứng dụng. `requestFactory` đã cấu hình **HTTPS/TLS, trust material, timeout và connection management** phù hợp. Không chuyển các giá trị này thành HTTP không TLS chỉ để code mẫu ngắn hơn.

### 5.1. Code kiểu 3.x: RestTemplateBuilder

```java
// Spring Vault 3.x — ví dụ legacy để nhận diện khi nâng.
import org.springframework.vault.client.RestTemplateBuilder;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.http.client.ClientHttpRequestFactory;

RestTemplateBuilder oldBuilder = RestTemplateBuilder.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory);

VaultOperations operations =
        new VaultTemplate(oldBuilder, sessionManager);

VaultResponse response =
        operations.read("secret/data/orders/config");
```

Ở dạng này, các tính năng auth thường đi qua `SessionManager` và interceptor được `VaultTemplate` cấu hình trên HTTP client bên dưới. Nếu ứng dụng còn tự chèn `X-Vault-Token` trong interceptor, cần hiểu rõ nguyên nhân trước khi loại bỏ; chèn hai lần có thể gây xung đột hoặc dùng sai token.

### 5.2. Đích 4.0.x: RestClientBuilder là bước chuyển phù hợp

```java
// Spring Vault 4.0.x — RestClientBuilder có từ 4.0.
import org.springframework.vault.client.RestClientBuilder;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

RestClientBuilder builder = RestClientBuilder.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory);

VaultOperations operations =
        new VaultTemplate(builder, sessionManager);

VaultResponse response =
        operations.read("secret/data/orders/config");
```

Nếu target là **4.0.5**, cách này là lựa chọn khả dụng. Đừng import `VaultClient` vào dự án còn ở 4.0 vì lớp đó xuất hiện từ 4.1. Việc có `RestClientBuilder` không đồng nghĩa mọi custom interceptor/error handler của `RestTemplate` sẽ tự hoạt động; phải chuyển theo API của builder mới và kiểm thử hành vi trên dây.

### 5.3. Đích 4.1.x: VaultClient + VaultTemplate

```java
// Spring Vault 4.1.x — cách xây client được khuyến nghị.
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory)
        .defaultNamespace("team-a/") // Chỉ khi dùng Vault namespace này
        .build();

VaultOperations operations =
        new VaultTemplate(client, sessionManager);

// Nghiệp vụ domain không cần viết lại:
VaultResponse response =
        operations.read("secret/data/orders/config");
```

Constructor `VaultTemplate(VaultClient, SessionManager)` có từ **4.1**. Nếu không dùng Vault namespace thì **bỏ** `.defaultNamespace("team-a/")`. `SessionManager` cần được quản lý nhất quán bởi framework: nếu ứng dụng đang dùng Spring Cloud Vault, hãy ưu tiên để auto-configuration tạo và sở hữu session manager thay vì khai báo một manager mới trùng chức năng.

**Đừng nhầm** code `new VaultTemplate(client, sessionManager)` với `new VaultTemplate(client)`: constructor chỉ nhận client được dùng cho kịch bản không quản lý Vault authentication trong template (ví dụ Vault Agent proxy đã xử lý xác thực). Không dùng nó khi ứng dụng vẫn phải gửi token từ `SessionManager`.

### 5.4. Biến thể 4.1 tự xây từ ClientAuthentication

Nếu đang làm một lab thuần Java chưa có `SessionManager` bean, `VaultTemplate` còn có constructor nhận `ClientAuthentication`:

```java
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

// "test-token-only" là fixture cho môi trường test, không dùng production.
VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory)
        .build();

VaultOperations operations = new VaultTemplate(
        client, new TokenAuthentication("test-token-only"));
```

`TokenAuthentication` với token tĩnh là tiện cho test nhưng không tự lấy được token mới nếu token hết hạn. Workload chạy lâu nên dùng **Kubernetes auth, AppRole, JWT** hoặc cơ chế phù hợp và session lifecycle do Spring Vault quản lý.

## 6. Khi nào dùng VaultClient trực tiếp thay callback RestOperations?

### 6.1. Dùng domain operation trước

Một code cũ có thể sử dụng callback:

```java
// Ví dụ kiểu cũ: dùng REST callback cho endpoint tùy biến.
VaultResponse response = vaultOperations.doWithSession(rest ->
        rest.getForObject("auth/token/lookup-self", VaultResponse.class));
```

Với endpoint đã được `VaultOperations` bao phủ, nhiều trường hợp **không cần callback**. Ví dụ thao tác đọc token metadata có thể dùng:

```java
VaultResponse response =
        vaultOperations.read("auth/token/lookup-self");
```

Cách này vẫn dùng `SessionManager` của template để xử lý Vault token và đưa path đến Vault server. Nếu có API chuyên biệt phù hợp hơn, ví dụ `opsForKeyValue`, `opsForTransit`, `opsForPki` hoặc `opsForToken`, ưu tiên API đó để giảm xử lý JSON/URL thủ công.

### 6.2. Dùng VaultClient cho Vault HTTP cấp thấp ở 4.1+

Khi cần gọi endpoint mới hoặc chưa có wrapper domain, `VaultClient` cho phép viết fluent request:

```java
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.VaultToken;
import java.util.Map;

// Ví dụ chỉ dùng token fixture trong test.
// Ở ứng dụng thực cần lấy token hợp lệ qua auth/session manager.
VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory)
        .build();

VaultResponse result = client.post()
        .path("transit/encrypt/orders")
        .token(VaultToken.of("test-token-only"))
        .body(Map.of("plaintext", "c2FtcGxl"))
        .retrieve()
        .requiredBody();
```

`plaintext` trong request Transit phải là **Base64 của bytes plaintext**; `c2FtcGxl` là Base64 của `sample`. Không truyền plaintext thô hoặc ghi plaintext thật vào log.

`VaultClient` là lớp thấp hơn `VaultTemplate`: trong ví dụ gọi trực tiếp, **caller phải cung cấp token** qua `.token(...)` khi endpoint cần xác thực. Không nên giả định vì ứng dụng có một `VaultTemplate` ở nơi khác mà `VaultClient` độc lập sẽ tự gắn token hoặc tự renew. Có thể dùng cơ chế tích hợp `SessionManager` phù hợp cho nghiệp vụ, thay vì giữ token trực tiếp trong business method.

### 6.3. Vì sao không chuyển thẳng sang RestClient thuần?

`RestClient` có thể gọi Vault HTTP, nhưng không có helper Vault-specific về token/namespace và người gọi phải tự định nghĩa URI/serialization:

```java
// Spring Framework RestClient — HTTP thuần, chỉ minh họa trong test.
import org.springframework.web.client.RestClient;

RestClient rest = RestClient.builder()
        .baseUrl("https://vault.example.test:8200")
        .build();

VaultResponse result = rest.get()
        .uri("/v1/secret/data/orders/config")
        .header("X-Vault-Token", "test-token-only")
        .retrieve()
        .body(VaultResponse.class);
```

Đây **không phải ví dụ cấu hình production hoàn chỉnh**: còn thiếu quản lý token/renewal, namespace, TLS trust tùy hệ thống, timeout, error mapping và retry policy. Sử dụng `RestClient` là lựa chọn hợp lý khi đang viết framework/integration HTTP và chủ động muốn kiểm soát toàn bộ contract; với ứng dụng nghiệp vụ đã có Spring Vault, `VaultClient` hoặc `VaultOperations` thường phù hợp hơn.

## 7. Chuyển cấu hình RestTemplateCustomizer và namespace

Khi upgrade từ 3.x/4.0 lên 4.1, chú ý những phần đã được **deprecated**:

| Legacy API / cách cấu hình | Đích phù hợp ở 4.1 | Cần giữ lại |
| --- | --- | --- |
| `RestTemplateBuilder` | `VaultClient.Builder` hoặc `RestClientBuilder` khi cần chuyển tiếp | Endpoint, request factory, timeout, converters |
| `RestTemplateCustomizer` | **`VaultClientCustomizer`** (ưu tiên với Vault) hoặc `RestClientCustomizer` cho lớp HTTP | Interceptor và behavior đặc thù |
| `RestTemplateFactory` | Cơ chế cấu hình `VaultClient`/`RestClientBuilder` | Lifecycle/configuration ownership |
| `RestTemplateRequestCustomizer` | `ClientHttpRequestInitializer` qua cấu hình `RestClient` | Header/metadata phù hợp và giới hạn |
| `VaultClients.createNamespaceInterceptor(...)` | `VaultClient.Builder.defaultNamespace(...)` hoặc `RequestHeadersSpec.namespace(...)` | Namespace đúng theo workload |
| Override `doCreateRestTemplate()` | Sử dụng `VaultClient.Builder` và cấu hình HTTP phù hợp | Mọi customization còn cần thiết |
| `ResponseErrorHandler` tùy biến | `VaultClient` error handling / `onStatus` theo API mới | Phân loại 403/404/5xx và không rò dữ liệu |

### 7.1. Ví dụ VaultClientCustomizer (4.1)

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.VaultClientCustomizer;

@Configuration
class VaultClientCustomization {

    @Bean
    VaultClientCustomizer teamNamespaceCustomizer() {
        return builder -> builder.defaultNamespace("team-a/");
    }
}
```

Đoạn mã giả định ứng dụng dùng **Spring Vault configuration infrastructure nhận bean `VaultClientCustomizer`**. Nếu ứng dụng tự gọi `VaultClient.builder()...build()` hoàn toàn thủ công, bean customizer sẽ **không tự được áp dụng**: cần gọi `customizer.customize(builder)` hoặc cấu hình trực tiếp trên builder trước khi build.

Cũng không nên tạo namespace từ header do người dùng gửi mà thiếu kiểm tra quyền. Namespace phải được liên kết với danh tính workload/tenant được chứng thực.

### 7.2. Lỗi thường gặp: interceptor HTTP cũ bị bỏ qua

Ở code 3.x, một `ClientHttpRequestInterceptor` trên `RestTemplate` có thể thêm custom headers, trace ID, client certificate handling hoặc rewrite URL. Khi chuyển sang `VaultClient`, không được giả định interceptor đó tự chạy trên mọi client. Hãy xác định có còn cần hành vi cũ không, và chuyển phần cần thiết vào `VaultClient.Builder.configureRestClient(...)` hoặc `requestFactory(...)`.

**Ví dụ:** code cũ vô tình inject `X-Vault-Token` tĩnh từ config trong interceptor. Mục tiêu nâng cấp là **loại bỏ lỗi này** và để session manager cùng `VaultTemplate` quản lý token. Không port nguyên interceptor tĩnh sang builder mới vì đó là bug bảo mật và lỗi refresh token tiềm ẩn.

## 8. Reactive: không sửa code đồng bộ bằng cách bọc Mono

Với hệ thống dùng Spring WebFlux hoặc ứng dụng reactive, lựa chọn cần dựa trên cách gọi thực tế:

- `ReactiveVaultOperations`/`ReactiveVaultTemplate` là domain API reactive đã tồn tại trước 4.1.
- `ReactiveVaultClient` từ **4.1** dựa trên `WebClient` và cung cấp request fluent riêng cho Vault.
- `RestClient`/`VaultClient` là **blocking/synchronous**. Không dùng `Mono.just(vaultOperations.read(...))` trên event loop: lời gọi HTTP đã block trước khi Mono được xây dựng.

Ví dụ minh họa dạng reactive ở 4.1:

```java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.support.VaultToken;

// Ví dụ isolated API, không phải session manager reactive hoàn chỉnh.
ReactiveVaultClient client = ReactiveVaultClient.builder()
        .endpoint(VaultEndpoint.create("vault.example.test", 8200))
        .build();

var mono = client.get()
        .path("secret/data/orders/config")
        .token(VaultToken.of("test-token-only"))
        .retrieve()
        .body();
```

Ở môi trường thật, xác thực/rotation vẫn cần được quản lý thông qua reactive authentication/session hoặc `ReactiveVaultTemplate`; mẫu trên chỉ mô tả request đến một endpoint đang cấu hình. Với `ReactiveVaultClient`, cần bảo đảm TLS/WebClient connector và converter được cấu hình đúng.

Nếu đang ở phiên bản cũ chưa có `ReactiveVaultClient`, không được nhập class đó chỉ vì một bài hướng dẫn 4.1 có nhắc tới nó.

## 9. Giữ nguyên semantics về lỗi và response

Di chuyển HTTP adapter có thể làm thay đổi cách exceptions được phát ra, nhất là nếu code cũ đã có `ResponseErrorHandler` tự định nghĩa.

| Tầng client | Lỗi/status cần quan tâm |
| --- | --- |
| `RestTemplate` trực tiếp | Thường phát `HttpStatusCodeException` hoặc lỗi truy cập tài nguyên; phụ thuộc error handler |
| `RestClient` trực tiếp | Thường phát nhóm `RestClientResponseException`/`HttpClientErrorException`/`HttpServerErrorException` |
| **`VaultClient` 4.1+** | Có thể phát **`VaultClientResponseException`** với status, headers, response body nếu có |
| **`VaultTemplate`** | Tiếp tục có thể chuyển lỗi thành `VaultException` hoặc lớp chuyên biệt |
| **Read missing** | `VaultOperations.read(path)` có thể trả `null`; `readRequired(path)` (từ 4.0) ném `SecretNotFoundException` |

Ví dụ chẩn đoán trong một low-level adapter 4.1:

```java
import org.springframework.vault.VaultException;
import org.springframework.vault.client.VaultClientResponseException;

try {
    VaultResponse result = vaultClient.get()
            .path("secret/data/orders/config")
            .token(workloadToken)
            .retrieve()
            .requiredBody();
    // Xử lý dữ liệu theo schema KV v2.
} catch (VaultClientResponseException ex) {
    int status = ex.getStatusCode().value();
    // Chỉ log mã status + operation/path template đã lọc;
    // KHÔNG log ex.getResponseBodyAsString() nguyên văn.
    throw new IllegalStateException(
            "Vault request failed with HTTP status " + status);
} catch (VaultException ex) {
    throw new IllegalStateException(
            "Vault client failed without a confirmed HTTP status");
}
```

`VaultClientResponseException` còn có thể đại diện cho lỗi chuyển đổi phản hồi hoặc I/O ở các tình huống cụ thể; nếu không có HTTP response thực, cần tránh tự suy ra một status như `500` trong metrics. Ví dụ trên nhằm chỉ đường xử lý status, không thay thế failure taxonomy và retry budget của dịch vụ.

**Quan trọng:** `404` từ KV read có thể mang nghĩa khác `404` của PKI, token hoặc issuer. `403` có thể là quyền thiếu hoặc session invalid. `503` có thể cho phép retry hữu hạn với thao tác đọc KV, nhưng một `GET database/creds/role` có thể **tạo lease mới** nên retry mù có thể tạo credential dư. Giữ kiểm thử nghiệp vụ theo loại endpoint, không dựa vào HTTP method duy nhất.

### 9.1. Raw response và JSON converters

Dùng một bộ kiểm thử với JSON response hợp lệ của KV v1/v2, Transit, PKI và auth login. Với KV v2, giá trị thật thường nằm trong `response.data.data`, không phải `response.data` một tầng. Trên Spring Vault 4.x, cấu hình Jackson 2/3 có thể ảnh hưởng cách map `Map`, số nguyên và POJO; phải so sánh data type thực tế, không chỉ response body có nội dung.

Với response không có body (`204`), API `VaultClient.ResponseSpec.body()` có thể trả `null`; `requiredBody()` thì yêu cầu body và báo lỗi nếu không có. Chọn phương thức theo hợp đồng endpoint; không biến mọi `204` thành lỗi không cần thiết.

## 10. Bảo mật trong quá trình chuyển API

### 10.1. Tránh chuyển token/namespace sang sai host

`VaultClient` cung cấp mô hình **relative path gắn với một `VaultEndpoint`**. Đây là cải thiện bảo mật so với callback cấp thấp nhận URI bất kỳ. Tuy vậy, vẫn phải kiểm soát input vào `VaultOperations` và các code HTTP thủ công.

Danh sách cần kiểm tra:

- **Hostname và scheme** của Vault lấy từ cấu hình đáng tin cậy, thông thường HTTPS, có xác thực chứng thư máy chủ.
- Không nhận URL/path Vault hoàn chỉnh do request bên ngoài cung cấp.
- Không chứa `../`, chuỗi encoding bất thường hoặc URL tuyệt đối trong segment secret path.
- Không gắn `X-Vault-Token` tĩnh vào `RestClient` dùng chung nhiều host.
- Không chuyển request mang Vault token sang cloud metadata endpoint (AWS/Azure/GCP) hoặc ngược lại.
- Không log raw token, KV secret, Transit plaintext, private key, header auth hoặc body lỗi chưa lọc.
- Phân biệt token/lease renewal sau nâng cấp; không chỉ kiểm thử một HTTP request thành công.

### 10.2. Bản vá bảo mật là một phần của tiêu chí hoàn thành

Spring công bố ngày **19/11/2026** rằng các bản **4.0.5** và **4.1.2** khắc phục **CVE-2026-41698**, liên quan path traversal khi secret path không được sanitize. Vì vậy nâng code từ `RestTemplate` sang `VaultClient` **không thay thế việc nâng dependency tới patch đã vá**; kiểm tra dependency tree/lockfile và kiểm thử path injection trong CI.

Để chặn lỗi từ thiết kế, hãy đặt path template trong code:

```java
// Chỉ cho đọc khóa cấu hình của các service đã được cho phép.
Set<String> allowedServices = Set.of("orders", "billing");

if (!allowedServices.contains(serviceName)) {
    throw new IllegalArgumentException("Unsupported service");
}

String path = "secret/data/" + serviceName + "/config";
VaultResponse result = vaultOperations.read(path);
```

Ví dụ này dùng allowlist **đóng**, không cố làm sạch mọi chuỗi path tùy ý từ input. Với khóa động có dấu phân cách hoặc ký tự quốc tế, cần một thiết kế mapping/path normalization cẩn thận và test riêng; không đơn giản replace `../` rồi tin rằng đã an toàn.

## 11. Kiểm thử hồi quy sau khi đổi client

Nên thực hiện **HTTP contract test** bằng WireMock/MockWebServer kết hợp **integration test** với Vault thật trong sandbox. Hai lớp test giải quyết các lỗi khác nhau.

### 11.1. Ma trận kiểm tra wire contract

| Kịch bản | Điều phải được giữ đúng |
| --- | --- |
| Đọc KV v2 | `GET /v1/secret/data/orders/config`, token header hợp lệ, schema response `data.data` |
| Ghi KV v2 CAS | `POST /v1/secret/data/orders/config`, JSON `data` + `options.cas` số nguyên |
| Gọi Transit | `POST /v1/transit/encrypt/orders`, plaintext Base64, xử lý `data.ciphertext` |
| Login AppRole/Kubernetes | Auth request đi tới mount đúng, **không đòi token trước login** |
| Gọi API đã có session | `X-Vault-Token` được chèn một lần, không dùng token tĩnh cũ |
| Enterprise namespace | `X-Vault-Namespace` phù hợp, không rò namespace giữa workload |
| Request TLS | Truststore/certificates hợp lệ, hostname verification bật, timeout có giới hạn |
| `403` | Không bị coi là secret missing hay tự tăng quyền |
| `404` từ KV read | Theo hợp đồng `read`/`readRequired`, không che lỗi cấu hình mount |
| `204` | Endpoint có body rỗng vẫn được xử lý đúng |
| Lỗi 5xx/timeout | Policy retry phù hợp tính idempotent, không cấp trùng credential |
| Path traversal | URI tuyệt đối hoặc segment `../` bị từ chối/không gửi token sang host khác |
| Cloud metadata login | HTTP client gọi đúng metadata endpoint, không dùng nhầm `VaultClient` |
| Jackson conversion | Schema KV/Transit/PKI và numeric fields không đổi ngoài ý muốn |
| Background renewal | Login token/secret lease có thể gia hạn hoặc rotate theo cấu hình đã chọn |

Nếu WireMock chỉ nhận request **đúng một lần**, có thể kiểm tra số lượt `GET`/`POST`; điều này đặc biệt quan trọng với endpoint tạo token, PKI, AWS dynamic credentials hoặc database credentials. Một retry dư có thể tạo nhiều secrets/leases mới và ảnh hưởng bảo mật/quota.

### 11.2. Test khói sau build

Ví dụ luồng kiểm thử trong Vault sandbox:

1. Cấu hình một Vault dev/test có KV v2 mount `secret`, Transit key `orders` và auth method dành cho workload.
2. Build ứng dụng với dependency/BOM đúng dòng đích; giải quyết mọi warning deprecation có liên quan.
3. Đăng nhập bằng danh tính workload thật của môi trường test và đọc KV bằng `VaultOperations`.
4. Gọi Transit encrypt/decrypt và kiểm tra dữ liệu ban đầu khớp.
5. Tạo token/lease có TTL ngắn, quan sát renew/re-login hoặc rotation khi gần hết hạn.
6. Kiểm tra `403` với policy thiếu, `404` với path không có, `5xx` và timeout có kiểm soát.
7. Xác minh TLS, namespace, error telemetry; tìm secret/token vô tình bị ghi ra logs.
8. Dừng workload, xác nhận cleanup và chính sách revoke phù hợp.

Test với Vault thật kiểm tra ACL/backend semantics mà mock HTTP không làm được. Test với mock HTTP giúp xác nhận chính xác URL/header/body và phát hiện regressions trước khi phải chạy cả môi trường.

## 12. Kế hoạch nâng cấp từng bước và rollback

Một migration ít rủi ro có thể triển khai theo các giai đoạn:

| Giai đoạn | Việc cần làm | Tiêu chí thông qua |
| --- | --- | --- |
| **A. Inventory** | Ghi lại version Spring Vault, Boot/Cloud, Java, Jackson, các constructor/callback/customizer cũ | Biết ai sở hữu auth/session, request factory và nơi ghép path |
| **B. Khóa đích** | Chọn 4.0.x hoặc 4.1.x, patch bảo mật đã phê duyệt, BOM tương thích | Build dependency tree không lẫn Spring Framework/Jackson các thế hệ không tương thích |
| **C. Tạo adapter nhỏ** | Giữ business code trên `VaultOperations`, chuyển chỗ khởi tạo client | Không nhân đôi SessionManager, token/lease containers |
| **D. Port customizations** | TLS, timeout, namespace, HTTP converter, tracing và error handler | Các header/endpoint không đổi ngoài ý muốn |
| **E. Kiểm thử** | Unit, WireMock contract, Vault integration, security path tests | Các yêu cầu và lỗi quan trọng PASS |
| **F. Canary** | Deploy tỷ lệ nhỏ, theo dõi auth failure, latency, lease renew, 403/5xx | Không tăng lỗi hoặc phát hành credential dư |
| **G. Rollout** | Tăng dần lưu lượng và kiểm tra audit logs | Không có token/secret leak hoặc chênh lệch namespace |
| **H. Rollback plan** | Giữ artifact/config trước đó, quy trình phục hồi session và lease | Có thể đảo phiên bản code không ảnh hưởng dữ liệu, ACL và credentials đang hoạt động |

**Rollback không được hiểu là quay lại dùng một phiên bản có CVE nghiêm trọng**. Nếu một patch đã sửa lỗi bảo mật, chọn bản đã được vá thuộc dòng trước đó hoặc giữ code migration an toàn trong khi xử lý lỗi phát sinh. Rollback dependency có thể thay đổi hành vi auth/lease: cần đánh giá liệu token/lease cũ còn dùng được và tránh tạo thêm dynamic credentials khi restart.

### 12.1. Những lỗi nâng cấp thường gặp

| Biểu hiện | Nguyên nhân hay gặp | Cách khắc phục |
| --- | --- | --- |
| `ClassNotFoundException: VaultClient` | Chạy với Spring Vault 4.0/3.x nhưng dùng API 4.1 | Khóa version và dùng lựa chọn đúng dòng |
| Build lỗi import `RestTemplateCustomizer` mới | Tên API đích là `VaultClientCustomizer`/`RestClientCustomizer` | Đối chiếu Javadoc và wiring bean |
| JSON response không parse được | Chưa có Jackson phù hợp, converters thay đổi | Kiểm tra dependency và converter test |
| `403` sau nâng cấp | Session manager không được truyền cho client mới, token/namespace sai | Kiểm tra `VaultTemplate(client, sessionManager)` và HTTP wire |
| TLS handshake fail | Request factory mới không dùng truststore/hostname verifier cũ | Chuyển cấu hình TLS vào requestFactory đúng |
| Token vô tình được gửi tới URL khác | Caller cho phép absolute URI hoặc HTTP interceptor chung nhiều host | Endpoint scoping, path allowlist, bản vá bảo mật |
| `404` với KV v2 | Sai mount hoặc thiếu segment `data` | Dùng `opsForKeyValue` phù hợp hoặc sửa raw path |
| Request duplicate sau retry | Adapter mới có retry ở cả HTTP client lẫn business | Chỉ một retry budget; kiểm thử cấp phát động |
| Session renew không hoạt động | Dựng client/session manager mới khác với bean đang quản lý login | Để framework quản lý lifecycle thống nhất |
| Warnings deprecation tăng | Vẫn dùng constructor/callback cũ | Lập kế hoạch chuyển dần; không nhầm deprecated thành removed |

## 13. Checklist trước khi chấp nhận pull request nâng cấp

1. Ghi rõ **source Spring Vault version và target patch version**, Java, Spring Framework, Spring Boot/Cloud, Jackson.
2. Các lựa chọn API **đúng dòng**: 3.x legacy, 4.0 `RestClientBuilder`, 4.1+ `VaultClient`.
3. Business code ưu tiên `VaultOperations` nếu đã đủ đáp ứng, không tự viết HTTP cho mọi secrets engine.
4. Có đúng một cơ chế sở hữu **authentication/session/token renewal**; không hardcode token.
5. HTTPS/TLS, truststore, request factory, timeout, proxy và namespace không bị mất khi chuyển adapter.
6. Không gửi token sang host khác, không dùng URI tuyệt đối từ input, không có path traversal.
7. JSON converters hoạt động và KV v2/Transit/PKI payload được test.
8. Status `403/404/204/5xx`, transport timeout và missing response được phân loại đúng.
9. Retry không tự tạo trùng token/lease/PKI/cloud credentials.
10. WireMock contract test và Vault integration test đều PASS.
11. Có metric/auth/lease dashboard, canary rollout và rollback an toàn về mặt bảo mật.
12. Dependency tree xác nhận sử dụng bản đã vá CVE tương ứng dòng đích.

## Tài liệu tham khảo

- [Spring Vault — Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html): so sánh `RestClient`, `VaultClient`, `VaultTemplate` và hướng xây builder.
- [Spring Vault — VaultClient Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html): API fluent từ 4.1, `builder(RestTemplate)` và `builder(RestClient)` khi chuyển đổi cấu hình.
- [Spring Vault — VaultClient.Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.Builder.html): endpoint, namespace, request factory, RestClient customization.
- [Spring Vault — VaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html): constructor theo từng dòng và trạng thái deprecated.
- [Spring Vault — VaultOperations Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html): `read`, `write`, `readRequired` và operations theo engine.
- [Spring Vault — Deprecated APIs in 4.1](https://docs.spring.io/spring-vault/reference/api/java/deprecated-list.html): thay `RestTemplateCustomizer`, `RestTemplateBuilder`, namespace interceptor và các constructor cũ.
- [Spring Vault — Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html): Java, Spring Framework, Jackson và quản lý phiên bản.
- [Spring Blog — Evolving Spring Vault: Introducing VaultClient](https://spring.io/blog/2025/12/26/evolving-spring-vault/): kiến trúc mới, lý do thay đổi và lưu ý migration.
- [Spring Blog — Spring Vault 4.0.5 and 4.1.2 available](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/): công bố bản vá **CVE-2026-41698** ngày 19/11/2026.
- [Spring Vault 3.2 — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html): bối cảnh `RestTemplate` và callback `RestOperations` ở dòng cũ.
- [Spring Vault 4.0 — RestClientBuilder Javadoc](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/client/RestClientBuilder.html): lựa chọn API dành cho dòng 4.0.
- [Spring Vault — ReactiveVaultClient Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.html): lựa chọn reactive từ 4.1.

**Kết luận:** Nâng Spring Vault không đồng nghĩa phải viết lại tất cả lời gọi `VaultTemplate`. Hãy **giữ domain operations nếu thích hợp**, chọn `RestClientBuilder` cho 4.0 hoặc `VaultClient` cho 4.1+, chuyển đúng những HTTP customizations thật sự cần thiết và kiểm tra auth, TLS, namespace, response/error, token/lease cùng lỗ hổng path traversal trước khi triển khai.
