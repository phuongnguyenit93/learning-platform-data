# ReactiveVaultClient và thay đổi callback theo phiên bản

Trong chương **Nâng cấp và tương thích**, một điểm cần đặc biệt lưu ý khi nâng cấp Spring Vault là sự xuất hiện của **`ReactiveVaultClient` ở Spring Vault 4.1**. Trước đó, lập trình reactive thường bắt đầu từ `ReactiveVaultOperations`/`ReactiveVaultTemplate` hoặc dùng callback `doWithSession(...)`/`doWithVault(...)` để thao tác trực tiếp trên `WebClient`. Từ 4.1, Spring Vault bổ sung client fluent chuyên biệt dành cho Vault, cùng callback tùy chỉnh `ReactiveVaultClientCustomizer`.

Điểm dễ nhầm nhất: **thêm `ReactiveVaultClient` không đồng nghĩa các callback cũ đã đổi tham số thành `ReactiveVaultClient`**. Theo Javadoc Spring Vault 4.1, `doWithSession` và `doWithVault` vẫn nhận `Function<WebClient, ? extends Publisher>`. Callback mới dành cho **cấu hình client builder** có nhiệm vụ khác với callback **thực thi một HTTP request**.

Bài này đặt trong bối cảnh **SPRING_VAULT**: ứng dụng Java truy cập HashiCorp Vault để đọc KV secrets, xác thực theo workload và policy, quản lý token/lease, gọi Transit encryption hoặc PKI. Mục tiêu là nâng cấp thư viện mà vẫn duy trì tính đúng đắn của Vault endpoint, token, callback, xử lý lỗi và quy trình kiểm thử tích hợp.

> **Phạm vi phiên bản:** Các ví dụ `ReactiveVaultClient` dưới đây dựa trên **dòng Spring Vault 4.1.x**, nơi interface này được giới thiệu. Khi dự án dùng 2.x, 3.x hay 4.0.x, không sao chép API 4.1 rồi kỳ vọng compile. Hãy khóa version cụ thể, xem Javadoc tương ứng và dùng ma trận kiểm thử trước khi đổi dependency.

## 1. Bốn khái niệm không được đồng nhất

| Thành phần | Lớp/interface | Vai trò |
| --- | --- | --- |
| **API thao tác mức cao** | `ReactiveVaultOperations`, `ReactiveVaultTemplate` | Đọc/ghi KV, quản lý secret engine, dùng Transit, xử lý session theo cấu hình |
| **Callback thực thi của Template** | `doWithSession(Function<WebClient,...>)`, `doWithVault(Function<WebClient,...>)` | Thoát xuống `WebClient` để gọi endpoint Vault chưa có API mức cao; có/không có session |
| **Client HTTP fluent mới** | `ReactiveVaultClient` (từ 4.1) | Gửi request reactive với `get/post/put/delete`, `path`, `token`, `namespace`, `retrieve` |
| **Callback cấu hình client** | `ReactiveVaultClientCustomizer` (từ 4.1) | Tùy chỉnh `ReactiveVaultClient.Builder` **khi xây bean/client**, không thực thi một request |

### Phân biệt với cách đồng bộ

`VaultTemplate` và `VaultOperations` là API **imperative**, các callback của chúng gắn với `RestOperations`. Còn `ReactiveVaultTemplate`/`ReactiveVaultOperations` là API **reactive** trên Reactor `Mono`/`Flux`, các callback lịch sử gắn với `WebClient`.

Spring Vault 4.1 cũng thêm `VaultClient` **đồng bộ** dựa trên `RestClient`. Tên gần giống nhưng **`VaultClient` không trả `Mono`**, còn **`ReactiveVaultClient` trả publisher/reactive stream**. Nhầm hai kiểu có thể gây lỗi compile hoặc chèn blocking I/O vào WebFlux.

### `ReactiveVaultClients` có chữ “s” ở cuối không phải `ReactiveVaultClient`

Lớp tiện ích `org.springframework.vault.client.ReactiveVaultClients` đã có từ dòng **2.0**, dùng để tạo/cấu hình `WebClient` cho Vault. Nó **không phải** interface fluent `org.springframework.vault.client.ReactiveVaultClient` được giới thiệu trong **4.1**.

| Tên | Xuất hiện | Cần nhớ |
| --- | --- | --- |
| `ReactiveVaultClients` (số nhiều) | Từ 2.0 | Factory/utilities cho `WebClient` và endpoint |
| `ReactiveVaultClient` (số ít) | Từ 4.1 | Client fluent chuyên biệt cho Vault |
| `ReactiveVaultClientCustomizer` | Từ 4.1 | Callback nhận `ReactiveVaultClient.Builder` |

Đừng sửa import bằng cách thêm/bớt chữ `s` rồi cho rằng đó chỉ là đổi tên class.

## 2. Ma trận phiên bản và phương án sử dụng

| Spring Vault | Hạ tầng HTTP reactive chính | Có `ReactiveVaultClient`? | Callback `doWithSession` / `doWithVault` | Hướng xử lý |
| --- | --- | --- | --- | --- |
| **2.x / 3.x** | `ReactiveVaultTemplate` với `WebClient` | **Chưa** | `Function<WebClient,...>` | Dùng `ReactiveVaultOperations`, callback `WebClient` khi cần |
| **4.0.x** | Template reactive trên nền `WebClient`; baseline Spring Framework 7 | **Chưa** | Vẫn `Function<WebClient,...>` | Kiểm tra Spring 7, Jackson, HTTP client và các API Template |
| **4.1.x** | `ReactiveVaultClient` + Template có thể dựa trên client mới | **Có** | Theo Javadoc 4.1 vẫn `Function<WebClient,...>` | Ưu tiên API engine mức cao; dùng client fluent cho request thấp tầng; chuyển customization phù hợp |
| **Phiên bản tương lai** | Chưa chốt từ ví dụ này | Tra Javadoc/notes | Không suy đoán callback sẽ tự đổi kiểu | Kiểm tra API tại đúng version đang nâng cấp |

**Không đặt `ReactiveVaultClient` vào source module vẫn dùng `spring-vault-core:4.0.x`**: class chưa tồn tại trong dòng đó. Ngược lại, khi chuyển lên 4.1, không xóa mọi `doWithSession` vì giả định nó bị loại bỏ: API này vẫn được tài liệu 4.1 mô tả.

### Tương thích dependency không chỉ là một con số

Spring Vault 4.0 nâng baseline lên **Spring Framework 7.0**, đồng thời hỗ trợ hướng Jackson 3 và tương thích Jackson 2. Dòng 4.1 tiếp tục dựa trên hệ sinh thái đó. Vì vậy một dự án Boot/Framework đời trước không thể chỉ đổi `spring-vault-core` sang 4.1 mà bỏ qua:

- Phiên bản **Spring Framework / Spring Boot / Spring Cloud Vault** được BOM quản lý; tránh trộn release train không tương thích.
- Java runtime và bytecode target mà từng phiên bản Spring Boot/Framework yêu cầu.
- Jackson 2 hay Jackson 3 hiện diện trong classpath; codec JSON của `WebClient` phải hoạt động cho `VaultResponse` và POJO.
- Reactor, Reactor Netty, HTTP connector, TLS trust, timeout và dependency bảo mật liên quan.
- Các constructor và customizer cũ bị đánh dấu deprecated, đặc biệt quanh `RestTemplate`/`RestOperations` ở 4.1.

Nếu dùng Spring Boot với dependency management, kiểm tra version cuối cùng qua `dependency:tree` (Maven) hoặc `dependencyInsight` (Gradle) **trong bước kiểm thử dự án**, không chốt version thủ công theo ví dụ. Bài này là tài liệu hướng dẫn; không đòi hỏi người học nâng tất cả thành phần cùng lúc trên production.

## 3. Callback lịch sử: `doWithVault` khác `doWithSession`

`ReactiveVaultOperations` cho phép dùng API mức cao `read`/`write`, hoặc callback khi cần endpoint chưa được trừu tượng hóa. Với callback:

- **`doWithVault`**: cung cấp `WebClient` cho thao tác **không dùng Vault login session**, ví dụ các endpoint health/init được phép gọi theo policy/kiểu endpoint. Không phải mọi endpoint ở đây đều có quyền truy cập công khai.
- **`doWithSession`**: cung cấp `WebClient` **trong ngữ cảnh session đã xác thực**; token/headers được quản lý theo cấu hình của Template.

Ví dụ phù hợp với dạng callback trong các dòng 3.x, 4.0 và Javadoc 4.1:

~~~java
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

public final class LegacyVaultCallbackReader {

    private final ReactiveVaultOperations vault;

    public LegacyVaultCallbackReader(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<VaultResponse> readKv2() {
        return vault.doWithSession(webClient ->
                webClient.get()
                        // Đường dẫn HTTP của KV v2:
                        .uri("secret/data/orders/config")
                        .retrieve()
                        .bodyToMono(VaultResponse.class));
    }
}
~~~

Hàm `webClient` trong lambda trên là **`org.springframework.web.reactive.function.client.WebClient`**, không phải `ReactiveVaultClient`. Nếu mã viết `webClient.path(...)` thì không compile, vì `WebClient` truyền thống dùng `uri(...)`.

Callback `WebClient` nhận URI string; nếu application lấy nguyên URL tuyệt đối từ đầu vào không tin cậy, một thao tác `doWithSession` có thể bị đưa tới máy chủ ngoài dự kiến **kèm thông tin session**. Hãy dùng **đường dẫn tương đối cố định hoặc allowlist**, không ghép URL do người dùng cung cấp vào callback đã xác thực.

### Sự thay đổi ở WebClient có thể bị nhầm là thay đổi Spring Vault

Trong ví dụ code cũ, bạn có thể gặp:

~~~java
// Ví dụ MÃ CŨ dùng một số API WebClient đã thay đổi/deprecated:
// webClient.put()
//     .uri("some/path")
//     .syncBody(request)
//     .retrieve()
//     .bodyToMono(Response.class);
~~~

`syncBody(...)` là cú pháp của `WebClient` đời trước; khi chuyển sang Spring Framework mới, dùng `bodyValue(request)` theo API `WebClient` tương ứng:

~~~java
return vault.doWithSession(webClient ->
        webClient.post()
                .uri("transit/encrypt/orders-key")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(VaultResponse.class));
~~~

Đoạn trên giả định `request` đã chứa payload phù hợp hợp đồng Transit (ví dụ `plaintext` phải được Base64 encode) và có scope kiểu `Mono<VaultResponse>`. **Đổi `syncBody` sang `bodyValue` là thay đổi API WebClient**, không phải bằng chứng `doWithSession` đã đổi callback type.

## 4. Khi endpoint có API mức cao, đừng tự rơi xuống HTTP

Từ Spring Vault 3.1, `ReactiveVaultOperations` có `opsForKeyValue` và các API `opsForTransit`/`opsForSys` tương ứng. Khi đọc KV v2, sử dụng API đúng engine thường dễ nâng cấp và ít lỗi đường dẫn:

~~~java
import java.util.Map;

import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

public final class OrdersSecretReader {

    private final ReactiveVaultOperations vault;

    public OrdersSecretReader(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<String> currentApiKey() {
        return vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config") // Đường logic, KHÔNG thêm data/.
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("KV secret bắt buộc không tồn tại")))
                .map(VaultResponse::getRequiredData)
                .flatMap(data -> {
                    Object value = data.get("apiKey");
                    if (value instanceof String key && !key.isBlank()) {
                        return Mono.just(key);
                    }
                    return Mono.error(new IllegalStateException(
                            "KV secret thiếu trường cấu hình bắt buộc"));
                });
    }
}
~~~

Code này **không cần biết `ReactiveVaultClient` đã xuất hiện hay chưa** nếu phiên bản đang dùng hỗ trợ API `opsForKeyValue`. Trình xử lý KV biết mount là `secret` và backend là `KV_2`; đường dẫn `data/` được framework quản lý.

### Mỗi tầng có mức tương thích khác nhau

| Tầng code | Phụ thuộc vào | Rủi ro nâng cấp |
| --- | --- | --- |
| `opsForKeyValue(...).get(...)` | Contract Spring Vault + KV version | Thấp hơn, vì ít phụ thuộc HTTP/client details |
| `ReactiveVaultOperations.read("...")` | Vault API path và response | Cần quản lý `data/`, JSON shape, mounted path |
| `doWithSession(webClient -> ...)` | Contract Spring Vault callback **và** `WebClient` | Có rủi ro với URI, body, status handling và codec |
| `ReactiveVaultClient.get().path(...)` | API fluent mới từ 4.1 | Không compile ở 4.0; cần hiểu token/namespace và response |
| Tự tạo raw `WebClient` | Spring Framework, URL, token, codec, TLS | Dễ bỏ sót Vault-specific safety, retry và session management |

Ưu tiên API mức cao cho KV/Transit/PKI khi có đầy đủ chức năng. Client fluent là công cụ phù hợp cho HTTP request Vault thấp tầng, **không phải lý do để thay toàn bộ code nghiệp vụ bằng manual JSON/HTTP**.

## 5. `ReactiveVaultClient` từ 4.1: client fluent riêng cho Vault

Client mới thuộc package `org.springframework.vault.client`, hỗ trợ `get`, `post`, `put`, `delete`, `method(HttpMethod)` và đối tượng request spec có `path`, `token`, `namespace`, `retrieve`, `exchangeToMono`/`exchangeToFlux`.

Với `VaultEndpoint` được cấu hình, dùng **`path(...)` cho đường dẫn tương đối**: API ngăn việc đưa một absolute URI vào `path(...)` nhằm tránh gửi request đến server ngoài Vault đã được cấu hình.

~~~java
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.client.VaultEndpoint;

ReactiveVaultClient client = ReactiveVaultClient.builder()
        .endpoint(VaultEndpoint.create("vault.example.internal", 8200))
        .build();
~~~

Đây là **mã ví dụ**, không thực hiện kết nối ngay. Ứng dụng production phải cấu hình TLS trust/HTTP connector phù hợp. **Không mặc định `ReactiveVaultClient.create()` tự cung cấp token**: khi gọi API cần auth, phải chỉ định token bằng `token(...)` hoặc sử dụng `ReactiveVaultTemplate` đã được cấu hình với `VaultTokenSupplier`.

### Gọi KV v2 qua low-level fluent API và token supplier

Ví dụ dưới đây minh họa hợp đồng của `ReactiveVaultClient` (4.1+) và `VaultTokenSupplier`; supplier được cấu hình từ workload identity/session manager, không lấy token từ chuỗi hardcode:

~~~java
import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

public final class OrdersRawVaultReader {

    private final ReactiveVaultClient client;
    private final VaultTokenSupplier tokens;

    public OrdersRawVaultReader(
            ReactiveVaultClient client, VaultTokenSupplier tokens) {
        this.client = client;
        this.tokens = tokens;
    }

    public Mono<VaultResponse> readKv2Response() {
        return tokens.getVaultToken()
                .flatMap(token -> client.get()
                        .path("secret/data/orders/config")
                        .token(token)
                        .retrieve()
                        .body())
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Vault KV response rỗng")));
    }
}
~~~

Đây là **dạng thấp tầng**, nên response KV v2 vẫn có cấu trúc JSON của Vault (thường `data.data` chứa giá trị secret). **Không gọi `getRequiredData().get("apiKey")` trên response KV v2 thô rồi mặc định thấy field đó ở tầng ngoài**; với API `ReactiveVaultKeyValueOperations`, framework đã xử lý cấu trúc này.

`VaultTokenSupplier.getVaultToken()` trả `Mono<VaultToken>`; một implementation quản lý session có thể cache/renew token. Không tự login trong mỗi request. Nếu không cần truy cập HTTP thấp tầng, inject `ReactiveVaultOperations` và dùng API engine mức cao vẫn đơn giản hơn.

### Gửi body với client fluent

Ví dụ ký/ mã hóa bằng Transit dưới dạng HTTP POST (chỉ minh họa cấu trúc request; dữ liệu đầu vào là giả):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import org.springframework.vault.authentication.VaultTokenSupplier;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;
import reactor.core.publisher.Mono;

public final class RawTransitEncryptor {

    private final ReactiveVaultClient client;
    private final VaultTokenSupplier tokens;

    public RawTransitEncryptor(
            ReactiveVaultClient client, VaultTokenSupplier tokens) {
        this.client = client;
        this.tokens = tokens;
    }

    public Mono<VaultResponse> encryptExample() {
        String b64 = Base64.getEncoder().encodeToString(
                "demo-only".getBytes(StandardCharsets.UTF_8));

        return tokens.getVaultToken().flatMap(token ->
                client.post()
                        .path("transit/encrypt/orders-key")
                        .token(token)
                        .bodyValue(Map.of("plaintext", b64))
                        .retrieve()
                        .body());
    }
}
~~~

Trước khi dùng trong ứng dụng thật, bảo đảm Transit key `orders-key` đã được tạo, workload được cấp policy `update` trên `transit/encrypt/orders-key`, body tuân API và dữ liệu mã hóa không bị ghi log. Với chức năng Transit phổ biến, cân nhắc `ReactiveVaultOperations.opsForTransit()` trước khi tự dựng HTTP.

## 6. Ba loại callback và khác biệt chữ ký

Đây là phần quyết định khi sửa code theo phiên bản:

| Callback | Thời điểm được gọi | Tham số lambda | Kết quả |
| --- | --- | --- | --- |
| `ReactiveVaultOperations.doWithSession` | Khi thực hiện thao tác qua Template | `WebClient` | Một `Publisher` (`Mono`/`Flux`), với session auth |
| `ReactiveVaultOperations.doWithVault` | Khi thực hiện thao tác qua Template | `WebClient` | Một `Publisher`, không có session auth |
| `ReactiveVaultClientCustomizer.customize` (4.1+) | **Lúc xây client bean/builder** | `ReactiveVaultClient.Builder` | `void`; sửa cấu hình HTTP/Vault |
| `ReactiveVaultClient.exchangeToMono` (4.1+) | Khi xử lý một response HTTP | `ClientResponse` | `Mono<V>` sau khi tự xử lý response |
| `ReactiveVaultClient.ResponseSpec.onStatus` (4.1+) | Khi status khớp rule | `ClientResponse` | `Mono<? extends Throwable>` để phát lỗi |

**Không có phép đổi cơ học** từ:

~~~java
// Callback cũ: nhận WebClient, được dùng để gọi Vault API.
vault.doWithSession(webClient -> webClient.get()
        .uri("secret/data/orders/config")
        .retrieve()
        .bodyToMono(VaultResponse.class));
~~~

sang:

~~~java
// KHÔNG ĐÚNG: doWithSession không đột ngột chuyển callback sang
// ReactiveVaultClient; WebClient không có phương thức path(...).
// vault.doWithSession(client -> client.get()
//         .path("secret/data/orders/config")
//         .retrieve().body());
~~~

Khi nâng cấp lên 4.1, bạn có thể **giữ callback cũ nếu vẫn còn phù hợp**, hoặc chủ động **chuyển sang client fluent mới** với token supplier/session được quản lý đúng cách. Việc đổi là **di chuyển sang một API khác**, không phải thay chữ ký tự động của method cũ.

### Callback tùy chỉnh client builder (4.1+)

`ReactiveVaultClientCustomizer` là functional interface:

~~~java
void customize(ReactiveVaultClient.Builder builder);
~~~

Ví dụ cấu hình giới hạn bộ nhớ dùng để decode HTTP response, bằng cách can thiệp `WebClient.Builder` bên dưới:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.ReactiveVaultClientCustomizer;

@Configuration
public class VaultClientTuning {

    @Bean
    ReactiveVaultClientCustomizer vaultResponseSizePolicy() {
        return builder -> builder.configureWebClient(web ->
                web.codecs(codecs -> codecs.defaultCodecs()
                        .maxInMemorySize(512 * 1024)));
    }
}
~~~

Callback trên được áp dụng khi framework **xây `ReactiveVaultClient` qua infrastructure có hỗ trợ customizer bean** (ví dụ `AbstractReactiveVaultConfiguration`). Nếu bạn tự gọi `ReactiveVaultClient.builder().build()` độc lập, **đừng giả định** mọi bean customizer được tự động áp dụng: phải truyền/applied rõ ràng hoặc dùng bean do cấu hình Spring tạo.

Ví dụ này chỉ thay kích thước bộ nhớ dành cho codec; tăng quá cao có thể làm một response không mong đợi tiêu thụ quá nhiều RAM. Không bật filter log body hoặc header `X-Vault-Token` chỉ để điều tra nâng cấp.

### Không đồng nhất customizer của các thế hệ HTTP client

`RestTemplateCustomizer` là hướng customizer **imperative/RestTemplate**, trong Spring Vault 4.1 được đánh dấu deprecated theo đường chuyển sang `VaultClientCustomizer`/`RestClientCustomizer`. Trong luồng **reactive**, cần xem `ReactiveVaultClientCustomizer` hoặc customization của `WebClient` tùy phạm vi. Đây là những callback **cấu hình**, khác hoàn toàn callback `doWithSession`.

Một đoạn cấu hình cần audit có thể đang dùng:

~~~text
RestTemplateCustomizer       -> imperative RestTemplate (đời cũ)
VaultClientCustomizer        -> VaultClient.Builder (4.1+)
RestClientCustomizer         -> RestClient.Builder
ReactiveVaultClientCustomizer -> ReactiveVaultClient.Builder (4.1+)
WebClient customization      -> WebClient.Builder (reactive HTTP)
~~~

Không tự đổi import trong project reactive sang `VaultClientCustomizer` chỉ vì thấy `ReactiveVaultClient` có tên gần giống. Hãy đối chiếu loại bean, loại callback và nơi Spring Vault thực sự áp dụng nó.

## 7. `retrieve`, `exchangeToMono` và `onStatus` khác nhau thế nào?

### `retrieve()` dành cho trường hợp phổ biến

~~~java
Mono<VaultResponse> result = client.get()
        .path("secret/data/orders/config")
        .token(token)
        .retrieve()
        .body();
~~~

`ReactiveVaultClient.ResponseSpec.body()` trả `Mono<VaultResponse>`. Bạn cũng có thể dùng `bodyToMono(SomeType.class)` khi response khớp kiểu đó. Mặc định response lỗi HTTP 4xx/5xx được chuyển thành exception họ **`VaultClientResponseException`**, thay vì trả như một body thành công.

### `exchangeToMono` khi cần xử lý status thấp tầng

~~~java
Mono<VaultResponse> response = client.get()
        .path("secret/data/orders/config")
        .token(token)
        .exchangeToMono(raw -> {
            if (raw.statusCode().is2xxSuccessful()) {
                return raw.bodyToMono(VaultResponse.class);
            }
            return raw.createError();
        });
~~~

Trong callback này, `raw` là **Spring WebClient `ClientResponse`**; bạn phải chủ động quyết định decode hay tạo lỗi. Javadoc nêu response body chưa được tiêu thụ sẽ được giải phóng sau khi publisher từ callback hoàn tất. Không giữ `ClientResponse` ở field để đọc lại sau đó.

### `onStatus` nhận callback trả `Mono<Throwable>`, không phải message

~~~java
Mono<VaultResponse> response = client.get()
        .path("secret/data/orders/config")
        .token(token)
        .retrieve()
        .onStatus(status -> status.value() == 429,
                ignored -> Mono.just(
                        new IllegalStateException("VAULT_RATE_LIMITED")))
        .body();
~~~

Ví dụ chỉ cho thấy callback signature: `onStatus(Predicate<HttpStatusCode>, Function<ClientResponse, Mono<? extends Throwable>>)`. Callback có thể tạo lỗi khác cho một status nhất định; không chuyển mọi 4xx thành cùng một loại lỗi chỉ để pass test. Nếu cần chẩn đoán, giữ exception gốc/cause trong kênh nội bộ có bảo vệ, nhưng **không ghi raw response body, token hoặc secret vào log/HTTP**.

Một khác biệt quan trọng khi học từ blog cũ: `WebClient.retrieve().onStatus(...)` và `ReactiveVaultClient.ResponseSpec.onStatus(...)` có hình dạng tương tự nhưng nằm trên **hai kiểu nhận khác nhau**. Tên `ClientResponse` ở callback không biến `ReactiveVaultClient` thành `WebClient`.

## 8. Path, endpoint và token: nâng cấp mà không đổi ranh giới tin cậy

### Vì sao nên dùng `path(...)` với endpoint cố định?

Client mới được thiết kế để dùng đường dẫn tương đối Vault và ngăn URL tuyệt đối đi qua `path(...)` khi client đã gắn `VaultEndpoint`. Điều này hạn chế lỗi SSRF/gửi token sai server thường gặp khi callback raw `WebClient` nhận một URL bất kỳ.

~~~java
// ĐÚNG: path là phần đường dẫn Vault, được code cố định hoặc allowlist.
client.get()
        .path("secret/data/orders/config")
        .token(token)
        .retrieve()
        .body();
~~~

Tuy nhiên, `ReactiveVaultClient` còn có phương thức `uri(URI)` và có thể dùng URI tuyệt đối trong những tình huống được thiết kế. **Không kết luận mọi request đều được bảo vệ tuyệt đối chỉ vì đang dùng client mới**. Nếu tham số từ người dùng có thể trở thành `uri(...)`, vẫn phải chặn host ngoài Vault, xử lý path traversal, path escape và giới hạn namespace.

### Token và session phải được theo dõi sau migration

`ReactiveVaultTemplate` có constructor mới trong dòng 4.1, chẳng hạn:

~~~java
// Spring Vault 4.1+; các bean cần được cấu hình thực tế trước.
ReactiveVaultTemplate template =
        new ReactiveVaultTemplate(client, vaultTokenSupplier);
~~~

Constructor nhận `ReactiveVaultClient` cùng `VaultTokenSupplier` cho phép Template gắn token theo flow đã cấu hình. Ngược lại, khi dùng `ReactiveVaultClient` **trực tiếp**, code phải chủ động truyền `token(token)` cho endpoint yêu cầu xác thực. Không được bỏ qua bước này rồi diễn giải mọi HTTP 403 thành lỗi policy của role.

Đảm bảo workload authentication tiếp tục hoạt động với đúng **auth mount path**, policy và Vault namespace. Với Kubernetes/AppRole, kiểm thử login/renew/re-login thực tế sau khi nâng cấp; không chỉ test object `ReactiveVaultClient` được tạo thành công.

### Tương thích bảo mật kết nối

Khi tạo `ReactiveVaultClient` bằng builder riêng:

- Cấu hình `VaultEndpoint` đúng host/port/scheme.
- Sử dụng HTTP connector có TLS trust/hostname verification chuẩn; không dùng trust-all certificate.
- Giữ namespace đúng nếu dùng Vault Enterprise/HCP Vault.
- Không làm mất timeout, connection pool limits, request headers bắt buộc và HTTP codecs đã có từ cấu hình cũ.
- Không dùng `.block()` trong Reactor event loop khi triển khai WebFlux, vì làm mất tính non-blocking và có thể gây nghẽn luồng.

## 9. Sự khác nhau về lỗi và retry giữa phiên bản

Ở client fluent 4.1, lỗi response được biểu diễn bởi exception họ `org.springframework.vault.client.VaultClientResponseException` (subclass của `VaultException`), có thể lấy `getStatusCode()` và metadata cần thiết. Từ các callback `WebClient` trước đây, loại lỗi phát sinh có thể là `WebClientResponseException`, `VaultException` hoặc lớp bọc khác tùy API/phiên bản.

| Tình huống | Rủi ro khi nâng cấp | Cách kiểm tra |
| --- | --- | --- |
| `404` đọc KV path không tồn tại | `Mono.empty()` hoặc error có thể khác giữa API engine và raw HTTP | Test endpoint bằng cả API cao/thấp và xác định hợp đồng mong muốn |
| `403` policy thiếu | Exception class/metadata thay đổi | Assert status bằng typed API, không parse text |
| `429` giới hạn request | Retry có thể nhân số request khi nhiều Pod cùng lên | Backoff/jitter/deadline, kiểm tra tối đa attempts |
| `500/503` từ Vault | `onStatus` và `exchangeToMono` phải trả publisher lỗi đúng | Kiểm tra mapping từ response tới error signal |
| Timeout hoặc lỗi TLS | Có thể nằm ở HTTP connector, không phải HTTP status | Bảo toàn cause, phân biệt I/O và lỗi quyền |
| Vault trả response 204/no body | `Mono.empty()` có thể là kết quả hợp lệ cho thao tác ghi | Không coi mọi empty response là lỗi |
| URI tuyệt đối không hợp lệ ở `path` | Client mới từ chối sớm | Sửa caller dùng path tương đối, không bỏ guard |

Đừng gọi `onErrorResume(e -> Mono.empty())` cho **mọi lỗi**: một lỗi policy 403 hoặc mất Vault có thể bị nuốt thành “secret không tồn tại”, khiến app chạy với thiếu cấu hình. Hãy chỉ chuyển thành empty khi nghiệp vụ thật sự cho phép vắng secret và class/status được xác minh.

Với các endpoint **cấp PKI certificate, rotate Transit key hoặc tạo dynamic credential**, retry sau timeout có thể có tác dụng phụ nếu request đầu đã được Vault xử lý nhưng response thất lạc. Không sao chép chính sách retry của `GET KV` sang mọi POST.

## 10. Checklist migration theo từng bước

Để nâng cấp từ 3.x/4.0.x lên 4.1.x, có thể đi theo trình tự:

1. **Inventory dependency:** khóa version `spring-vault-core`, Spring Framework/Boot/Cloud, Jackson, Reactor, HTTP connector. Ghi baseline hoạt động trước thay đổi.
2. **Tìm mọi callback:** tìm `doWithSession`, `doWithVault`, `WebClientCustomizer`, `WebClientBuilder`, `RestTemplateCustomizer`, các chỗ tự tạo `WebClient` và client tự dựng.
3. **Phân loại callback:** callback thực thi request (`WebClient`) hay callback cấu hình builder? Không thay import theo tên gần giống.
4. **Ưu tiên API engine:** nơi chỉ đọc KV/Transit/PKI thông thường, thử chuyển sang `ReactiveVaultOperations` cho logic ít phụ thuộc HTTP.
5. **Xem có thật sự cần client 4.1:** nếu cần HTTP API đặc biệt, cân nhắc `ReactiveVaultClient` với `path`, `token`/`VaultTokenSupplier` và exception handling rõ ràng.
6. **Chuyển customization đúng tầng:** đánh giá `ReactiveVaultClientCustomizer`, `WebClient.Builder`, TLS connector và namespace; kiểm tra bean customizer có được apply.
7. **Cập nhật WebClient cũ:** `syncBody` sang `bodyValue`, kiểm tra status handler, Reactor operators và cách decode JSON.
8. **Thử ranh giới auth/URI:** kiểm tra endpoint cố định, path không tuyệt đối, policy đúng KV v2/Transit/PKI; thử URL độc hại xem có bị chặn.
9. **Thử failure behavior:** 403, 404, 429, 5xx, timeout, body rỗng, TLS lỗi, token hết hạn, cancellation và retry.
10. **Triển khai canary:** đo latency, error rate, token/lease count, session login/re-login; rollback về artifact/dependency cũ nếu fail gate.

Không áp dụng đồng thời quá nhiều thay đổi không liên quan (chuyển HTTP client, nâng Jackson, đổi Vault auth role, sửa path KV) trong một commit/đợt phát hành nếu có thể tách ra. Việc cô lập thay đổi giúp tìm nguyên nhân chính xác khi xảy ra lỗi.

### Kiểm thử bằng StepVerifier

`StepVerifier` giúp khẳng định `Mono` phát đúng value hoặc error. Ví dụ dưới đây giả sử đã có một bean `ReactiveVaultOperations` trỏ đến Vault test instance chứa KV v2 `secret/orders/config` với `apiKey` giả; **không dùng secret thật trong test**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.vault.core.ReactiveVaultOperations;
import reactor.test.StepVerifier;

final class VaultReactiveCompatibilityTest {

    private final ReactiveVaultOperations vault;

    VaultReactiveCompatibilityTest(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    @Test
    void readsExpectedKv2Structure() {
        OrdersSecretReader reader = new OrdersSecretReader(vault);

        StepVerifier.create(reader.currentApiKey())
                .expectNext("DEMO_ONLY_NOT_A_REAL_SECRET")
                .verifyComplete();
    }
}
~~~

Đoạn `@Test` chỉ minh họa phần assert Reactor; muốn chạy nó cần thiết lập JUnit/Spring test injection đúng cách (ví dụ Spring test context hoặc constructor được test fixture gọi) và test Vault đã provision. Không coi ví dụ đó là một test class chạy độc lập không cần fixture.

### Ma trận regression cho callback/client

| Kiểm thử | Legacy callback `WebClient` | `ReactiveVaultClient` 4.1 | Kỳ vọng |
| --- | --- | --- | --- |
| KV v2 GET thành công | `doWithSession(...uri...)` | `get().path(...).token(...).retrieve().body()` | Đọc được `data.data`, không lộ secret ở log |
| KV v2 qua API engine | `opsForKeyValue(...).get(...)` | Vẫn dùng API engine | Kết quả business nhất quán |
| Không có Vault token | Session manager thất bại | Raw client không truyền `token` | Nhận lỗi xác thực/phân quyền, không dùng token giả |
| Token renew hoặc re-login | Reactive session manager | Token supplier khi dùng low-level client | Không tạo login cho từng request |
| 404 / 403 / 429 | WebClient/template response | `VaultClientResponseException`/handler | Phân loại bằng status/loại, không parse message |
| Untrusted absolute URL | Callback raw có nguy cơ | `path` cố định từ chối URL tuyệt đối | Không có request tới host ngoài Vault |
| HTTP 204 no body | Có thể `Mono.empty()` | Có thể `Mono.empty()` | Hợp đồng thao tác ghi xác định rõ |
| Header/namespace | Cấu hình WebClient/Template | Builder `defaultNamespace`/request `namespace` | Chỉ đúng namespace, không lộ token |
| Mất mạng/TLS lỗi | I/O từ WebClient | Connector/client mới | Preserve cause và dùng deadline |
| Canary trước/ sau | Theo dõi p95, lỗi và session | Cùng bộ đo | Không tăng rate 403, không sinh token bất thường |

Trong các test bảo mật, bắt request outgoing bằng fake Vault server/HTTP test transport và xác nhận **host, path, token header, namespace header** đúng. Tránh ghi toàn request vào log test nếu request có secret, JWT hoặc Vault token. Khi cần đối chiếu, chỉ log tên operation cố định và request ID giả.

## 11. Câu hỏi ôn tập

1. `ReactiveVaultClients` và `ReactiveVaultClient` khác nhau ở chữ ký, thời điểm xuất hiện và trách nhiệm như thế nào?
2. Tại sao nói Spring Vault 4.1 giới thiệu client mới **không có nghĩa** `doWithSession` đã đổi callback `WebClient` thành `ReactiveVaultClient`?
3. Phân biệt `ReactiveVaultClientCustomizer` với `doWithSession` và `exchangeToMono`; mỗi callback được gọi lúc nào?
4. Khi nâng cấp từ 4.0 lên 4.1, vì sao `ReactiveVaultClient.get().path(...)` không compile trên bản cũ?
5. Khi dùng `ReactiveVaultClient` trực tiếp, token đến từ đâu? `VaultTokenSupplier` khác với hardcode token như thế nào?
6. Khi đọc KV v2, vì sao `ReactiveVaultOperations.opsForKeyValue(...).get("orders/config")` dễ bảo trì hơn gọi raw `GET secret/data/orders/config`?
7. Khi thay `WebClient.syncBody(...)` bằng `bodyValue(...)`, bạn đang xử lý thay đổi của thư viện nào?
8. Vì sao nên dùng `path(...)` với `VaultEndpoint` được cấu hình và vẫn phải cẩn trọng khi dùng `uri(URI)`?
9. Một `Mono.empty()` sau HTTP 204 có phải luôn là lỗi không? Làm sao kiểm tra hợp đồng?
10. Bạn sẽ dùng những test nào để bảo đảm migration không gây tăng login, lỗi policy, gửi token ra sai host hoặc rò rỉ secret?

## 12. Ghi nhớ

**Spring Vault 4.1 thêm `ReactiveVaultClient`, không thay thế tức thì `ReactiveVaultOperations`.** API mức cao tiếp tục phù hợp cho KV, Transit và các tác vụ secrets engine thông thường. Callback `doWithSession`/`doWithVault` vẫn dùng `WebClient` trong Javadoc 4.1; `ReactiveVaultClientCustomizer` mới nhận `ReactiveVaultClient.Builder` để cấu hình, còn `exchangeToMono`/`onStatus` xử lý một response.

Khi nâng cấp, kiểm tra **đúng dependency version, đúng callback signature, token/session, path tương đối, namespace, TLS và error mapping**. Chuyển sang client fluent mới một cách có chủ đích, không tự động thay import. Đặt kiểm thử compile, integration, failure/security và canary làm điều kiện trước production để tránh một thay đổi API vô tình trở thành sự cố Vault auth hoặc lộ token.

### Tài liệu tham khảo

- [Spring Vault — Reactive Infrastructure và execution callbacks](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
- [Spring Vault — Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
- [Spring Vault — ReactiveVaultClient API (4.1.x)](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.html)
- [Spring Vault — ReactiveVaultClient.ResponseSpec API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.ResponseSpec.html)
- [Spring Vault — ReactiveVaultClientCustomizer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClientCustomizer.html)
- [Spring Vault — ReactiveVaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultOperations.html)
- [Spring Vault — ReactiveVaultTemplate constructors](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html)
- [Spring Vault — Dependencies và Spring Framework baseline](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
- [Spring Vault — Deprecated APIs](https://docs.spring.io/spring-vault/reference/api/java/deprecated-list.html)
- [Spring Blog — Evolving Spring Vault: Introducing VaultClient (26/12/2025)](https://spring.io/blog/2025/12/26/evolving-spring-vault/)
- [Spring Blog — Spring Vault 4.1 Generally Available (10/06/2026)](https://spring.io/blog/2026/06/10/spring-vault-4-1-available/)
