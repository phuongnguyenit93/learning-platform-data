# Tùy chỉnh VaultClient trên các phiên bản có hỗ trợ

Trong chương **Cấu hình Java** của **SPRING_VAULT**, `VaultTemplate` cho phép ứng dụng Java làm việc với HashiCorp Vault qua API cấp cao như KV secrets, Transit encryption và PKI. Khi cần kiểm soát chi tiết kết nối HTTP, timeout, TLS, namespace hoặc một API Vault chưa được bao phủ bởi operations, **`VaultClient`** là lớp trung gian phù hợp ở những phiên bản Spring Vault đã hỗ trợ.

Bài này hướng dẫn cấu hình và tùy chỉnh `VaultClient` bằng Java, cách nối nó với `VaultTemplate` và `ClientAuthentication`/`SessionManager`, cũng như cách mở rộng cấu hình có sẵn bằng `VaultClientCustomizer`. Các ví dụ dùng **Spring Vault 4.1 trở lên**, vì `org.springframework.vault.client.VaultClient` và `VaultClientCustomizer` được giới thiệu từ **4.1**. Nếu dự án đang dùng 4.0 hoặc 3.x, hãy làm theo hướng tương thích ở mục 3 thay vì sao chép class không tồn tại vào code.

Mục tiêu là tạo một client dùng được, hiểu các điểm tùy chỉnh, giữ authentication và policy đúng, và kiểm tra kết nối bằng secret KV v2 mà không làm lộ dữ liệu nhạy cảm.

## 1. VaultClient đứng ở đâu trong kiến trúc?

`VaultClient` là HTTP client đồng bộ, có fluent API dựa trên `RestClient` của Spring Framework và bổ sung quy ước dành riêng cho Vault. `ReactiveVaultClient` phục vụ trường hợp reactive dựa trên `WebClient`; bài này dùng bản đồng bộ.

~~~mermaid
flowchart LR
    A["VaultEndpoint / VaultEndpointProvider"] --> B["VaultClient<br/>HTTP, TLS, timeout, namespace"]
    C["ClientAuthentication"] --> D["SessionManager"]
    B --> E["VaultTemplate"]
    D --> E
    E --> F["VaultOperations"]
    F --> G["KV / Transit / PKI"]
    B --> H["Fluent HTTP request<br/>API chưa có operations"]
~~~

So sánh trách nhiệm:

| Thành phần | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| `VaultEndpoint` | Địa chỉ server | `https://vault.internal:8200` |
| `VaultClient` | Tạo và gửi HTTP request Vault, chuyển đổi response, xử lý lỗi HTTP | `client.get().path("sys/health")...` |
| `ClientAuthentication` | Login hoặc cung cấp Vault token từ workload | `TokenAuthentication`, AppRole, Kubernetes |
| `SessionManager` | Cấp token cho các request, có thể quản lý vòng đời token tùy triển khai | `SimpleSessionManager`, `LifecycleAwareSessionManager` |
| `VaultTemplate` | API cấp cao, tích hợp session và các operations Vault | `opsForKeyValue("secret", KV_2)` |
| Vault policy | Cấp hoặc từ chối quyền theo token và path | `read` tại `secret/data/orders/app` |

**Điểm quan trọng:** `VaultClient` tự thân không biết biến môi trường `VAULT_TOKEN` và không tự thực hiện lifecycle login. Nếu gọi trực tiếp qua fluent API, ứng dụng phải cung cấp credential khi cần (chẳng hạn `.token(vaultToken)`). Khi bọc bằng `VaultTemplate(client, authentication)` hoặc `VaultTemplate(client, sessionManager)`, template phối hợp với tầng authentication/session để gửi token.

### Vì sao nên dùng VaultClient thay vì RestClient thuần?

Với `RestClient` thuần, ứng dụng phải tự quản lý base URL, `/v1`, HTTP headers, body và response theo cấu trúc Vault. `VaultClient` cung cấp:

- `get()`, `post()`, `put()`, `delete()` và fluent `path(...)` để diễn đạt request.
- `token(VaultToken)` và `namespace(...)` thay vì tự ghép các header tương ứng.
- `retrieve().body()`/`requiredBody()`, `toEntity()` và `onStatus(...)` cho response.
- Endpoint được cấu hình sẵn để dùng đường dẫn tương đối và giúp hạn chế gửi request sai server.
- Thông báo lỗi HTTP qua loại `VaultClientResponseException`, có mã trạng thái và metadata phù hợp để xử lý có kiểm soát.

Mặc dù vậy, **`VaultTemplate` thường vẫn là lựa chọn thuận tiện nhất cho KV v1/v2, Transit và PKI** vì operations cấp cao giúp tránh tự dựng đường dẫn API hoặc tự giải mã cấu trúc dữ liệu của từng engine.

## 2. Khả năng hỗ trợ theo phiên bản

| Nhu cầu/API | Spring Vault 3.2.x | Spring Vault 4.0.x | Spring Vault 4.1.x trở lên |
| --- | --- | --- | --- |
| `VaultTemplate` và `VaultOperations` | Có | Có | Có |
| HTTP nền `RestTemplate` và `RestTemplateBuilder` | Có | Có | Có nhưng nhiều API cũ đã deprecated |
| `RestClientBuilder` của Spring Vault | Chưa có | Có | Có |
| `VaultClient` đồng bộ | **Chưa có** | **Chưa có** | **Có** |
| `VaultClient.Builder` | Chưa có | Chưa có | Có |
| `VaultClientCustomizer` | Chưa có | Chưa có | Có |
| `ReactiveVaultClient`/customizer tương ứng | Chưa có | Chưa có | Có |
| Constructor `VaultTemplate(VaultClient, SessionManager)` | Chưa có | Chưa có | Có |

Các lớp có tên gần giống nhau **không thể tự thay cho nhau**. Ví dụ, `org.springframework.vault.client.RestClientBuilder` đã có từ 4.0; `org.springframework.vault.client.VaultClient` chỉ bắt đầu từ 4.1.

Trong dự án Maven, dependency cần phù hợp BOM/Spring Framework:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Đoạn XML giả định version đã được quản lý. Nếu BOM chưa khai báo `spring-vault-core`, phải chọn version phù hợp với Spring Framework/Boot của ứng dụng. Để xem version thực tế:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.vault:spring-vault-core
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-vault-core \
  --configuration runtimeClasspath
~~~

Nếu IDE báo `Cannot resolve symbol VaultClient`, hãy kiểm tra dependency đã resolve **trước khi** đổi import hoặc sửa business code.

## 3. Nếu dự án chưa có VaultClient thì làm gì?

### Spring Vault 3.2.x

Giữ `VaultTemplate` và tùy chỉnh HTTP qua `ClientHttpRequestFactory`/`RestTemplateBuilder` theo API tương ứng. Ví dụ `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` có thể dùng khi cần timeout, TLS và session manager riêng.

### Spring Vault 4.0.x

Có thể dùng `RestClientBuilder` và `VaultTemplate(RestClientBuilder, SessionManager)`. Tuy nhiên `RestClientBuilder` **không phải `VaultClient.Builder`**; không có `.defaultNamespace(...)` hoặc phương thức fluent `VaultClient.get().path(...)` trên API `VaultClient` khi chưa ở 4.1.

### Spring Vault 4.1.x+

Sử dụng `VaultClient.create(endpoint)` khi cần nhanh; sử dụng `VaultClient.builder()` khi cần cấu hình HTTP và namespace. Với code mới, constructor `VaultTemplate(VaultClient, ClientAuthentication)` hoặc `VaultTemplate(VaultClient, SessionManager)` giúp kết nối cấu hình HTTP mới với API nghiệp vụ. Một số overload kiểu `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` và `RestTemplateBuilder` bị deprecated từ 4.1 nhưng không có nghĩa lập tức bị xóa.

**Quy tắc nâng cấp:** nâng dependency tương thích, biên dịch, kiểm tra connection/auth/policy/TLS, rồi mới thay cấu hình HTTP. Không giả định việc đổi constructor sẽ sửa lỗi 403 hay token hết hạn.

## 4. Tạo VaultClient: các factory và tùy chọn Builder

Một client đơn giản:

~~~java
VaultEndpoint endpoint =
        VaultEndpoint.create("vault.internal", 8200);
endpoint.setScheme("https");

VaultClient client = VaultClient.create(endpoint);
~~~

Khi cần tùy chỉnh, dùng builder:

~~~java
VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .build();
~~~

`VaultClient.Builder` trong Spring Vault 4.1+ cung cấp các điểm tùy chỉnh sau:

| Phương thức | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| `endpoint(VaultEndpoint)` | Endpoint cố định | Là base URL Vault, không chứa secret path |
| `endpoint(VaultEndpointProvider)` | Cần cấp endpoint từ provider | Phù hợp thiết kế endpoint động có kiểm soát |
| `requestFactory(ClientHttpRequestFactory)` | Timeout, proxy, TLS, kết nối HTTP riêng | HTTP factory phải được cấu hình đúng và quản lý tài nguyên |
| `defaultNamespace(String)` | Vault Enterprise namespaces | Không đặt nếu server không dùng namespace |
| `defaultHeader(String, String...)` | Header bổ sung dùng chung | Không hardcode `X-Vault-Token` hoặc header nhạy cảm |
| `configureRestClient(Consumer<RestClient.Builder>)` | Tùy chỉnh các tính năng của Spring `RestClient` | Không phá vỡ đường đi/token của Vault |
| `uriBuilderFactory(UriBuilderFactory)` | Quy tắc tạo URI đặc biệt | Ghi đè hành vi endpoint shortcut; cần kiểm soát rất chặt |
| `apply(Consumer<VaultClient.Builder>)` | Áp dụng nhóm cấu hình tái sử dụng | Tránh áp dụng tùy chỉnh xung đột |
| `build()` | Tạo client cuối cùng | Sau khi tạo có thể dùng an toàn giữa nhiều luồng |

`VaultClient.builder(restClient)` hoặc `builder(restTemplate)` có thể bắt đầu từ cấu hình HTTP đã có. Cần bảo đảm message converters và base URL phù hợp cho JSON/string/bytes của Vault. Tránh vô tình tái sử dụng một `RestClient` dành cho dịch vụ khác có interceptors hoặc authentication headers không phù hợp.

### Giới hạn an toàn của đường dẫn tương đối

`VaultClient` được thiết kế để làm việc với **đường dẫn tương đối** khi có `VaultEndpoint`. Tuy nhiên API vẫn có các cách cung cấp URI đã dựng sẵn, có thể trỏ tới URL tuyệt đối. Do đó:

- Luôn cấp `endpoint(...)` khi ứng dụng chỉ cần gọi một Vault server xác định.
- Với `path("secret/data/orders/app")`, sử dụng chuỗi đường dẫn Vault do ứng dụng kiểm soát, không nhận nguyên URL từ HTTP request của người dùng.
- Không dùng `VaultClient.create()` không endpoint chỉ để tránh phải cấu hình base URL: khi không có endpoint, caller cần cung cấp URL tuyệt đối cho mỗi request.
- Nếu buộc phải xây URI tùy chỉnh hoặc nhận path từ bên ngoài, kiểm tra whitelist host/scheme/path và quyền truy cập.

Việc dùng client chuyên biệt giúp giảm nguy cơ sai URL nhưng **không thay thế validation input, Vault policy hoặc cấu hình mạng**.

## 5. Ví dụ Java hoàn chỉnh: tùy chỉnh HTTP timeout và namespace

Giả sử ứng dụng `orders-api` cần đọc secret KV v2 tại mount `secret`, path `orders/app`. Ta dùng **Spring Vault 4.1+** và cấu hình thủ công ba bean: `VaultEndpoint`, `VaultClient`, `VaultTemplate`.

Đây là một phương án Spring Boot dựa trên Java 17+. Không dùng thêm một cấu hình `AbstractVaultConfiguration` khác trong cùng context để tránh tạo bean `VaultTemplate` trùng lặp.

### 5.1. Biến môi trường chạy lab

Khởi động Vault dev server trong terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal khác (Bash):

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token
vault kv put secret/orders/app apiKey=demo-key
vault kv get secret/orders/app
~~~

PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
vault kv put secret/orders/app apiKey=demo-key
~~~

Dev server thường gắn `secret` làm KV v2. Kiểm tra bằng `vault secrets list -detailed` nếu môi trường được cấu hình khác. Dev root token và kết nối HTTP ở `127.0.0.1` **chỉ dùng cho thực hành**, không mang sang production.

### 5.2. Tạo bean với VaultClient.Builder

Tạo `OrdersVaultConfig.java`:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class OrdersVaultConfig {

    @Bean
    VaultEndpoint vaultEndpoint(
            @Value("${VAULT_ADDR}") String address) {

        URI uri = URI.create(address.trim());
        String scheme = uri.getScheme();

        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là base URL http(s)://host[:port]");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(uri);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Bean
    VaultClient vaultClient(
            VaultEndpoint endpoint,
            @Value("${VAULT_NAMESPACE:}") String namespace) {

        // HTTP factory minh họa timeout; với HTTPS dùng TLS/CA
        // đáng tin cậy từ JVM hoặc HTTP stack.
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3_000);
        factory.setReadTimeout(5_000);

        VaultClient.Builder builder = VaultClient.builder()
                .endpoint(endpoint)
                .requestFactory(factory)
                .defaultHeader("X-App-Name", "orders-api")
                .configureRestClient(rest ->
                        rest.defaultHeader(
                                "X-Client-Component", "orders-api"));

        // Namespace chỉ áp dụng khi Vault Enterprise được cấu hình.
        if (!namespace.isBlank()) {
            builder.defaultNamespace(namespace);
        }

        return builder.build();
    }

    @Bean
    VaultTemplate vaultTemplate(
            VaultClient client,
            @Value("${VAULT_TOKEN}") String token) {

        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "VAULT_TOKEN không được rỗng");
        }

        ClientAuthentication auth = new TokenAuthentication(token);
        return new VaultTemplate(client, auth);
    }
}
~~~

**Giải thích:**

1. `vaultEndpoint(...)` chỉ nhận **base URL**, không nhận `/v1/secret/...`. Việc validate cấu trúc URI giúp phát hiện lỗi sớm nhưng không chứng minh TLS/permission đúng.
2. `vaultClient(...)` cấu hình factory để timeout thay vì phụ thuộc vào giá trị mặc định của hệ thống. `3_000` và `5_000` là thời gian minh họa tính bằng mili giây; chọn giá trị thực theo độ trễ, SLA và chiến lược retry.
3. `defaultHeader(...)` minh họa header ứng dụng không nhạy cảm. Nếu hạ tầng không sử dụng các header tùy chọn này, có thể bỏ cả hai. **Không dùng `defaultHeader("X-Vault-Token", token)`** vì token cần được quản lý đúng theo session/request.
4. `configureRestClient(...)` cho phép điều chỉnh `RestClient.Builder` nằm dưới `VaultClient`. Nếu muốn nhiều tùy chỉnh HTTP, đặt chúng ở một chỗ và kiểm tra tác động của interceptors.
5. `defaultNamespace(...)` chỉ thêm khi `VAULT_NAMESPACE` có giá trị. Namespace là header được Vault hỗ trợ ở môi trường tương ứng; không tự gắn namespace vào đường dẫn secret.
6. `VaultTemplate(client, auth)` kết nối client HTTP đã được cấu hình với nguồn token. Để quản lý token trong workload dài hạn, có thể dùng overload nhận `SessionManager` thay cho overload nhận `ClientAuthentication`.

**Bảo mật transport:** `SimpleClientHttpRequestFactory` ở đây chỉ minh họa timeout. Với production, dùng `https://...`, CA/trust store đáng tin cậy, hostname verification và HTTP factory thích hợp cho TLS/mTLS/proxy nếu cần. Thay đổi scheme thành HTTPS mà không cấu hình trust không bảo đảm kết nối thành công.

### 5.3. Nếu muốn dùng SessionManager đã được quản lý

Khi Spring Context đã có bean `SessionManager` được cấu hình phù hợp, có thể thay phương thức `vaultTemplate(...)` ở trên bằng:

~~~java
@Bean
VaultTemplate vaultTemplate(
        VaultClient client,
        SessionManager sessionManager) {
    return new VaultTemplate(client, sessionManager);
}
~~~

Cần import `org.springframework.vault.authentication.SessionManager`. Đây là **phương án thay thế**, không thêm song song hai bean `VaultTemplate` cùng tên. Một `LifecycleAwareSessionManager` với `TaskScheduler` có thể quản lý renew token trong các điều kiện Vault và auth method cho phép. Cần đưa session manager và scheduler vào Spring lifecycle đúng cách; không tự tạo manager có tác vụ nền trong một local variable rồi bỏ mặc khi shutdown.

## 6. Kiểm tra bằng VaultTemplate: đọc một secret KV v2

Tạo `OrdersSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersSecretReader {

    private final VaultOperations vault;

    public OrdersSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    public boolean hasApiKey() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("apiKey") instanceof String key
                && !key.isBlank();
    }
}
~~~

Phần business chỉ biết `VaultOperations`, nên không phụ thuộc `VaultClient.Builder` đã được tùy chỉnh ra sao. Spring inject `VaultTemplate` qua interface. Khi đọc KV v2:

- `secret` là **mount**.
- `orders/app` là **đường dẫn secret tương đối**.
- Spring Vault tự chuyển thành request `GET /v1/secret/data/orders/app`.
- `response.getData()` trong `VaultKeyValueOperations` cho phép truy cập các field logic đã được unwrapped.

Một policy HCL chỉ đọc:

~~~hcl
path "secret/data/orders/app" {
  capabilities = ["read"]
}
~~~

Policy thực tế cần được gắn vào danh tính/token của ứng dụng. Token hợp lệ mà thiếu `read` trên path KV v2 vẫn có thể trả 403.

Trong lớp Spring Boot application, có thể thêm phương thức kiểm tra khi khởi động:

~~~java
@Bean
CommandLineRunner verifyVault(OrdersSecretReader reader) {
    return args -> {
        if (!reader.hasApiKey()) {
            throw new IllegalStateException(
                    "Không thấy apiKey hợp lệ tại secret/orders/app");
        }
        System.out.println("VaultTemplate đọc KV v2 thành công");
    };
}
~~~

Đoạn trên nằm trong class `@SpringBootApplication`, cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`. Không ghi token, `apiKey` hay `VaultResponse` ra log. Một phép đọc thành công tại startup không chứng minh token sẽ còn hợp lệ mãi hoặc failover Vault HA đã được xử lý.

## 7. Gọi trực tiếp VaultClient: khi nào và như thế nào?

`VaultClient` có ích khi cần gửi request tới Vault API chưa có abstraction cấp cao tương ứng. Khi gọi trực tiếp, ứng dụng cần biết **đường dẫn API thực tế**, cách giải mã response và cách cung cấp token.

Ví dụ đọc cùng secret KV v2 bằng fluent API:

~~~java
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.support.VaultResponse;

VaultResponse rawResponse = client.get()
        .path("secret/data/orders/app")
        .token(VaultToken.of(token))
        .retrieve()
        .requiredBody();
~~~

Ở đây `client` là `VaultClient` 4.1+ đã cấu hình `endpoint`; `token` là chuỗi credential được cấp hợp lệ cho request. `.token(...)` thêm token vào request này, nhưng **không phải cơ chế tự động renew token**. Không tạo token mới từ một chuỗi hằng trong code production.

### KV v2 trả thêm lớp bao dữ liệu

Khi dùng `VaultTemplate.opsForKeyValue(..., KV_2)`, library xử lý cấu trúc KV v2 để service dễ lấy field. Khi gọi HTTP trực tiếp bằng `VaultClient`, JSON logic tương ứng thường có dạng:

~~~json
{
  "data": {
    "data": {
      "apiKey": "demo-key"
    },
    "metadata": {
      "version": 1
    }
  }
}
~~~

Đây là cấu trúc rút gọn để minh họa: Vault thực tế có thêm metadata, timestamps và các field khác. `rawResponse.getData()` chứa lớp `data`/`metadata` của KV v2; không thể coi `rawResponse.getData().get("apiKey")` là field secret trực tiếp. Để đọc KV hằng ngày, dùng `VaultKeyValueOperations` sẽ dễ bảo trì hơn.

### Chỉ gọi retrieve() đã gửi HTTP chưa?

Chưa. `retrieve()` trả về `ResponseSpec`; request được thực thi khi gọi terminal method như `requiredBody()`, `body(...)` hoặc `toBodilessEntity()`. Nếu bỏ terminal method, ví dụ sẽ không thực hiện request như mong muốn.

Có thể lấy status/headers bằng `retrieve().toEntity()`, hoặc map lỗi bằng `retrieve().onStatus(...)`. Không nên in toàn bộ response body/headers, vì một số header hoặc giá trị có thể chứa thông tin nhạy cảm.

## 8. Sử dụng VaultClientCustomizer trong AbstractVaultConfiguration

Nếu ứng dụng đã cấu hình bằng `AbstractVaultConfiguration`, **không cần tự tạo thêm `@Bean VaultClient` và `@Bean VaultTemplate`**. Từ Spring Vault **4.1**, cấu hình cơ sở đã cung cấp `vaultClient()` và `vaultTemplate()`; `VaultClientCustomizer` là một callback được framework áp dụng vào `VaultClient.Builder` khi tạo client. Đây là điểm mở rộng thuận tiện để thay đổi HTTP/headers mà không ghi đè cả luồng tạo bean.

Ví dụ bạn đã có `AppVaultConfiguration extends AbstractVaultConfiguration` với hai phương thức bắt buộc `vaultEndpoint()` và `clientAuthentication()`. Có thể bổ sung một lớp cấu hình riêng:

~~~java
package com.example.vault;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.VaultClientCustomizer;

@Configuration(proxyBeanMethods = false)
public class VaultClientCustomization {

    @Bean
    VaultClientCustomizer vaultClientCustomizer() {
        return builder -> builder
                .defaultHeader("X-App-Name", "orders-api")
                .configureRestClient(rest ->
                        rest.defaultHeader(
                                "X-Client-Component", "orders-api"));
    }
}
~~~

Khi Spring Vault **đang tạo client thông qua hạ tầng hỗ trợ customizer**, bean này được áp dụng. Đảm bảo `VaultClientCustomization` nằm trong component scan hoặc được `@Import` đúng cách.

**Phân biệt hai cách:**

| Cách tạo client | Customizer có được tự áp dụng? |
| --- | --- |
| `AbstractVaultConfiguration.vaultClient()` từ Spring Vault 4.1 | Có, khi bean `VaultClientCustomizer` được phát hiện |
| Một tích hợp Spring Cloud Vault có hỗ trợ customizer tương ứng | Kiểm tra khả năng tích hợp và version đang dùng |
| `VaultClient.builder().build()` do ứng dụng gọi trực tiếp | **Không tự quét bean customizer**; caller phải gọi customizer hoặc áp dụng cùng logic trực tiếp |

Có thể tự áp dụng một customizer vào builder thủ công nếu thực sự muốn dùng chung:

~~~java
VaultClient.Builder builder = VaultClient.builder().endpoint(endpoint);
customizer.customize(builder);
VaultClient client = builder.build();
~~~

Ở đây `customizer` là một instance `VaultClientCustomizer` đã được inject vào cấu hình; đây là snippet minh họa, không phải bean hoàn chỉnh độc lập.

Đừng sử dụng cả override `vaultClient()` và bean customizer để thiết lập cùng một giá trị xung đột. Nếu hệ thống đã dùng `AbstractVaultConfiguration`, ưu tiên customizer để giữ SessionManager và VaultTemplate mặc định nhất quán.

### Vì sao RestClientCustomizer không giống VaultClientCustomizer?

`RestClientCustomizer` can thiệp vào `RestClient.Builder` của tầng HTTP; `VaultClientCustomizer` can thiệp trực tiếp vào builder của client Vault, nên có thể cấu hình endpoint, namespace, default headers hoặc request factory. Từ 4.1, Spring khuyến nghị di chuyển những tùy chỉnh dành riêng cho Vault từ `RestTemplateCustomizer` sang `VaultClientCustomizer`; những tùy chỉnh HTTP phổ thông có thể đi qua `RestClientCustomizer` hoặc `configureRestClient(...)`.

Không giả định một customizer dành cho RestClient ứng dụng khác sẽ tự được áp vào `VaultClient` nếu hạ tầng không đăng ký nó.

## 9. Namespace và header: cấu hình có chủ đích

Ở Vault Enterprise, namespace xác định phạm vi quản lý các tài nguyên Vault. Có hai cách thường dùng:

~~~java
// Mặc định cho mọi request từ client:
VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .defaultNamespace("team-a")
        .build();
~~~

Hoặc ở từng request:

~~~java
VaultResponse response = client.get()
        .path("sys/health")
        .namespace("team-a")
        .retrieve()
        .requiredBody();
~~~

Hai đoạn là minh họa dành cho hệ thống có Vault namespace; đường dẫn `sys/health` và quyền truy cập của từng môi trường cần được kiểm tra. Ở hệ thống không dùng namespaces, không cần đặt header này.

**Không đồng nhất namespace với path của KV:** namespace là ngữ cảnh request (thường thông qua header); mount `secret` và path `orders/app` nằm trong namespace đã chọn. Nếu 404 xuất hiện khi thêm namespace, cần kiểm tra namespace, auth role, mount và policy cùng nhau.

Không nên đưa token vào default header của client dùng chung. Token có TTL, có thể được rotate và mỗi workload có identity riêng. Với `VaultTemplate`, giao phần này cho `ClientAuthentication`/`SessionManager`; khi gọi trực tiếp, sử dụng `token(VaultToken)` cho request cụ thể.

Header nhận diện ứng dụng không nhạy cảm có thể giúp truy vết theo quy định vận hành, nhưng header mặc định nên ít và nhất quán; không cho user input chưa kiểm soát ghi đè các header liên quan auth/namespace.

## 10. HTTP client, TLS và endpoint trong môi trường production

Các tùy chỉnh thường liên quan đến `ClientHttpRequestFactory` hoặc `RestClient.Builder`:

| Nhu cầu | Điểm tùy chỉnh | Kiểm tra thực tế |
| --- | --- | --- |
| Kết nối quá lâu | `requestFactory(...)` và connect timeout | Timeout phát huy tác dụng khi DNS/network/Vault chậm |
| Đọc response quá lâu | Read/response timeout của HTTP stack | Không treo thread nghiệp vụ vô hạn |
| CA nội bộ hoặc mTLS | Factory/SSL context/trust store | Chứng chỉ tin cậy và hostname khớp SAN |
| Proxy hoặc load balancer | HTTP factory và `endpoint(...)` | Request thực sự tới Vault đúng môi trường |
| Vault HA và failover | `VaultEndpointProvider`, DNS/service/LB ổn định | Không hardcode IP node active |
| Header nghiệp vụ | `defaultHeader(...)`/`configureRestClient(...)` | Không ghi credential hoặc header không cần thiết |
| Namespace | `defaultNamespace(...)` hoặc `namespace(...)` | Role/policy/mount đúng namespace |
| URI encoding | `uriBuilderFactory(...)` | Không tạo URL vượt ra khỏi Vault endpoint |

Với staging/production, sử dụng HTTPS và CA tin cậy; **không tắt TLS validation để sửa lỗi chứng chỉ**. `VaultEndpoint` chỉ mô tả đích kết nối; nó không tự tải CA hoặc cung cấp client private key.

Nên gắn URL Vault theo môi trường triển khai (ví dụ `VAULT_ADDR`) và dùng DNS/Service/LB ổn định. Trong Docker/Kubernetes, `127.0.0.1` thường chỉ container/pod hiện tại; không trỏ tới Vault nằm ở host hoặc service khác.

Nếu cần thay client theo runtime, phương thức `client.mutate()` trả về builder dựa trên cấu hình hiện tại, nhưng **không tự làm các bean hoặc request đang dùng client cũ chuyển sang instance mới**. Việc refresh/redeploy phải được thiết kế rõ, đặc biệt với token lifecycle và connection resources.

## 11. Xử lý lỗi sau khi tùy chỉnh VaultClient

`VaultClient` map lỗi HTTP và I/O vào hệ thống exception của Spring Vault; 4xx/5xx thường được biểu diễn bằng subclass của `VaultClientResponseException`. Đừng vội xem mọi lỗi đều do HTTP timeout.

| Biểu hiện | Tầng lỗi thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không import được `VaultClient` | Dependency quá cũ | Xác nhận `spring-vault-core` >= 4.1 và version Spring Framework tương thích |
| Không có `VaultClientCustomizer` | Dự án dùng 4.0/3.x hoặc sai import | Chỉ dùng customizer khi version hỗ trợ |
| `NoUniqueBeanDefinitionException` | Có hai cấu hình tạo `VaultClient`/`VaultTemplate` | Chọn một nguồn cấu hình hoặc qualifier rõ |
| DNS/connection refused/timeout | Endpoint, NetworkPolicy, firewall, Vault listener | Kiểm tra kết nối từ đúng workload |
| `SSLHandshakeException`/PKIX | Trust store, CA, hostname, mTLS | Sửa chứng chỉ và HTTP factory |
| HTTP 401/403 | Token/role/policy hoặc auth mount | Xác nhận danh tính thực tế và policy ở path API |
| HTTP 404/response rỗng | Mount, namespace, path hoặc KV version sai | Kiểm tra `secret`, `orders/app`, KV v2 và namespace |
| Đọc KV trực tiếp nhưng không thấy `apiKey` | KV v2 trả về nested `data.data` | Dùng `VaultKeyValueOperations` hoặc giải mã đúng cấu trúc |
| Token tĩnh hết hạn | Không có cơ chế refresh từ nguồn credential | Dùng auth workload và quản lý session phù hợp |
| Thêm `defaultHeader` khiến request lỗi | Header sai hoặc interceptor xung đột | Loại header tùy chọn, kiểm tra cấu hình client |
| Bean customizer không có tác dụng | Dùng builder thủ công không áp dụng callback | Sử dụng hạ tầng Spring Vault hoặc áp dụng customizer thủ công |

Ví dụ bắt lỗi HTTP status khi gọi fluent API:

~~~java
import org.springframework.vault.client.VaultClientResponseException;

try {
    client.get()
            .path("secret/data/orders/app")
            .token(VaultToken.of(token))
            .retrieve()
            .requiredBody();
} catch (VaultClientResponseException ex) {
    int status = ex.getStatusCode().value();

    // Chỉ ghi nhận nhóm lỗi/trạng thái; không log token,
    // body lỗi hoặc dữ liệu secret.
    throw new IllegalStateException(
            "Vault request thất bại với HTTP " + status, ex);
}
~~~

Đoạn này giả định `client`, `token` và import `VaultToken` đã có trong ngữ cảnh; nó mô tả cách dùng exception, không phải một class độc lập. Khi đưa vào production, kiểm soát cả logging của cause/stack trace vì thư viện có thể chứa nội dung request hoặc response trong thông điệp lỗi. Không lặp vô hạn request 403 hay lỗi URI cấu hình cố định.

## 12. Kiểm thử tích hợp và giám sát

Để xác minh `VaultClient` tùy chỉnh thật sự hoạt động, cần một Vault test instance hoặc Testcontainers phù hợp. Mock `VaultTemplate` chỉ kiểm tra logic service, không chứng minh custom header, TLS, endpoint hay quyền đọc.

| Kịch bản kiểm thử | Điều cần thấy |
| --- | --- |
| `VaultClient.builder().endpoint(endpoint)` | Relative path đi tới Vault dự kiến |
| Timeout connect/read | Request vượt giới hạn được chấm dứt theo HTTP factory |
| Thêm default namespace ở Vault Enterprise | Request được xử lý trong namespace hợp lệ |
| Cấu hình customizer qua `AbstractVaultConfiguration` | Bean `VaultClient` có thiết lập đúng, `VaultTemplate` dùng client đó |
| Builder thủ công không áp customizer | Không có thay đổi cho tới khi caller áp dụng callback |
| `VaultTemplate(client, auth)` đọc KV v2 | Có dữ liệu `apiKey` hợp lệ, đúng mount/secret path |
| Gọi trực tiếp `client.get()` | Có token request phù hợp và hiểu nested response KV v2 |
| Policy thiếu `read` | Bị từ chối, không bị chuyển thành secret rỗng giả |
| Token hết TTL/bị revoke | Lỗi được ghi nhận, lifecycle/session xử lý theo thiết kế |
| TLS CA không đáng tin | Handshake lỗi, không được vô hiệu hóa TLS |
| Không có Vault server | Timeout/kết nối lỗi có giới hạn, không treo vô hạn |
| Spring Context đóng | Các HTTP resource/session quản lý đúng lifecycle |

Giám sát nên có latency, lỗi DNS/TLS/timeout, HTTP 4xx/5xx, authentication và token renewal. Khi điều tra cần ưu tiên audit log Vault có kiểm soát. **Không ghi token, Kubernetes JWT, AppRole SecretID, khóa Transit, private key PKI hoặc secret KV vào logs/traces/metric labels**.

Cần phân biệt giới hạn của từng test: test đơn vị có thể xác minh callback builder; test tích hợp mới cho thấy credential, policy và Vault HTTP server cùng hoạt động.

## 13. Câu hỏi tự luyện

1. `VaultClient` xuất hiện từ Spring Vault phiên bản nào? `RestClientBuilder` xuất hiện từ phiên bản nào?
2. `VaultClient` khác `VaultTemplate` về mức độ trừu tượng và quản lý token ra sao?
3. Khi cấu hình `VaultClient.builder()`, vì sao phải cấp `endpoint(...)` rõ ràng?
4. Điểm khác nhau giữa `requestFactory(...)`, `defaultNamespace(...)` và `configureRestClient(...)` là gì?
5. Tại sao không nên đặt `X-Vault-Token` vào `defaultHeader(...)`?
6. Trong Spring Vault 4.1, khi đã dùng `AbstractVaultConfiguration`, bean `VaultClientCustomizer` có lợi gì?
7. Nếu tự gọi `VaultClient.builder().build()`, callback customizer trong ApplicationContext có tự động chạy không?
8. Vì sao `VaultClient.get().path("secret/data/orders/app")` và `VaultTemplate.opsForKeyValue("secret", KV_2).get("orders/app")` cùng đọc một secret nhưng dữ liệu nhận về có cấu trúc khác?
9. Chỉ gọi `retrieve()` có thực hiện HTTP request không? Cần thêm bước nào?
10. Nếu một request trả HTTP 403, vì sao tăng timeout hoặc đổi TLS factory không sửa được lỗi policy?

**Kết quả mong đợi:** bạn có thể tùy chỉnh `VaultClient` trên Spring Vault 4.1+, áp dụng `VaultClientCustomizer` đúng ngữ cảnh, tạo `VaultTemplate` với nguồn xác thực/session rõ ràng, và kiểm chứng việc đọc KV v2. Bạn cũng phân biệt được giới hạn của 3.x/4.0, của token tĩnh và của direct HTTP API để phát triển các phần tiếp theo về Transit encryption, PKI, token/lease lifecycle, xử lý lỗi, giám sát và kiểm thử tích hợp trong SPRING_VAULT.

### Tài liệu chính thức để đối chiếu API

- [Spring Vault 4.1: Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
- [Javadoc: VaultClient](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html)
- [Javadoc: VaultClient.Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.Builder.html)
- [Javadoc: VaultClientCustomizer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClientCustomizer.html)
- [Javadoc: AbstractVaultConfiguration](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [Javadoc: VaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Blog: Evolving Spring Vault — Introducing VaultClient](https://spring.io/blog/2025/12/26/evolving-spring-vault/)

