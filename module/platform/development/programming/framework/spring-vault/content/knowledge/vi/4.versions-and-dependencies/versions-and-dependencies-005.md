# HTTP client, thư viện JSON và cơ chế chuyển đổi dữ liệu

Trong **SPRING_VAULT**, ứng dụng Java thường gọi HashiCorp Vault thông qua `VaultOperations`/`VaultTemplate` để đọc KV secrets, mã hóa bằng Transit, xin chứng chỉ PKI, xác thực theo workload và theo dõi token/lease. Lời gọi Java như `kv.get("orders/config")` nhìn rất gọn, nhưng bên dưới phải hoàn thành nhiều việc: xây đường dẫn HTTP đúng, gắn token và namespace, thiết lập TLS, gửi request, đọc phản hồi JSON, chuyển thành đối tượng Java, rồi phân loại lỗi.

**Chương:** Phiên bản và phụ thuộc. Bài này giải thích **HTTP client, thư viện JSON và cơ chế chuyển đổi dữ liệu** trong Spring Vault; đồng thời hướng dẫn chọn dependency, cấu hình bảo mật/kết nối, xử lý KV v1/v2 và kiểm thử tích hợp.

**Kết quả mong đợi:** người học có thể giải thích đường đi của dữ liệu, chọn `RestClient`/`VaultClient` hoặc reactive client phù hợp, cấu hình HTTP transport và Jackson, đọc secret thành `Map` hoặc POJO mà không nhầm định dạng response, và phát hiện lỗi do TLS, quyền Vault, JSON mapping hay khác biệt API.

> **Phiên bản tham chiếu: 25/11/2026.** Ví dụ tập trung vào **Spring Vault 4.1.2**, **Java 17+**, **Spring Framework 7.0.11+** theo tài liệu dependency 4.1.2. Dòng 3.x dùng nền Spring Framework 6.x và kiến trúc HTTP khác. Tên artifact, class và cách khởi tạo cần được đối chiếu với Javadoc của đúng phiên bản đang triển khai.

## 1. Đường đi của một thao tác đọc secret

```text
Business code: VaultOperations / VaultTemplate
              |
              |  kv.get("orders/config", AppSettings.class)
              v
  API KV (biết KV v1 hay v2, ghép endpoint, đọc response)
              |
              v
  VaultClient (Spring Vault 4.1+)
      path + token + namespace + error translation
              |
              v
  Spring RestClient + HttpMessageConverter
      object -> JSON bytes / JSON bytes -> VaultResponse
              |
              v
  ClientHttpRequestFactory / HTTP transport
      TLS + CA trust + mTLS + connection/read timeout
              |
              v
  HTTPS /v1/... --> Vault Server
      workload token --> ACL policy --> KV / Transit / PKI
```

Chiều phản hồi đi ngược lại:

1. HTTP transport nhận **status, headers và body**.
2. Spring Web HTTP message converter dùng **Jackson** để giải mã JSON; kiểu đích có thể là `VaultResponse`, `VaultResponseSupport<T>` hoặc kiểu khác.
3. `VaultClient`/`VaultTemplate` xử lý status và các chi tiết Vault như KV version, lease metadata, `wrap_info`.
4. API domain trả về `Map`, POJO hoặc kiểu domain như token/certificate tùy thao tác.

**Ba tầng không nên đánh đồng:** transport quyết định kết nối HTTPS; converter quyết định JSON ↔ Java; Vault API domain quyết định ý nghĩa của đường dẫn và dữ liệu. Một dependency JSON sai có thể làm request HTTP thành công nhưng ứng dụng không chuyển được response, còn một Vault policy sai có thể gây HTTP 403 dù tất cả thư viện và mapper đều đúng.

## 2. Phân biệt API HTTP theo thế hệ Spring Vault

| Dòng | API HTTP nền | API Spring Vault nên dùng | Lưu ý khi nâng cấp |
| --- | --- | --- | --- |
| **3.1.x / 3.2.x** | `RestTemplate`, `RestOperations` (imperative); `WebClient` (reactive) | `VaultTemplate`, `ReactiveVaultTemplate` | Giữ cùng thế hệ Spring Framework 6.x; kiểm tra các `RestTemplateCustomizer` và request factory đang dùng |
| **4.0.x** | Bổ sung `RestClient` và `RestClientBuilder` trên Spring Framework 7 | `VaultTemplate`; có thể khởi tạo từ `RestClientBuilder` | Kiểm tra HTTP transport, Jackson 3/2, API đã deprecated/bị bỏ; OkHttp không còn là client được hỗ trợ |
| **4.1.x** | `VaultClient` fluent dựa trên `RestClient`, `ReactiveVaultClient` dựa trên `WebClient` | `VaultOperations`/`VaultTemplate` cho API domain; `VaultClient` cho endpoint đặc biệt | `VaultTemplate(VaultClient, SessionManager)`; một số API `RestTemplate`/customizer cũ được đánh dấu deprecated từ 4.1 |

**Chọn theo nhu cầu:**

- **`VaultTemplate`:** lựa chọn chính cho KV, Transit, PKI, token và lease. Nó che bớt chi tiết của Vault HTTP API và cung cấp tiện ích chuyển đổi dữ liệu.
- **`VaultClient`:** dùng khi cần gọi endpoint Vault chưa có abstraction domain, muốn thao tác method/path/header/response ở tầng HTTP nhưng vẫn có cú pháp dành riêng cho Vault.
- **`RestClient`:** dành cho code hạ tầng cần điều khiển HTTP trực tiếp. Bản thân `RestClient` **không tự đăng nhập Vault**; phải xử lý token/namespace và path.
- **`ReactiveVaultTemplate` / `ReactiveVaultClient`:** dùng cho chuỗi non-blocking dựa trên `WebClient` và Reactor; cần quản lý session/token theo reactive contract.

Đừng chuyển toàn bộ business code từ `VaultOperations` sang HTTP fluent chỉ vì có API 4.1. Ngược lại, nếu code đang tùy biến `RestTemplate` sâu để thêm Vault token, namespace, nên cân nhắc nâng lên `VaultClient` và `VaultClientCustomizer` khi nền đã tương thích.

Nguồn: [VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html), [Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html), [VaultTemplate Javadoc 4.1](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html).

## 3. Chọn HTTP transport: JDK hay thư viện bên ngoài?

Spring Vault 4.1.2 hỗ trợ các transport sau; **JDK `HttpClient` là lựa chọn mặc định khi không có client bên ngoài phù hợp**:

| HTTP transport | Dependency thường gặp | Khi phù hợp | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **JDK `HttpClient`** | Không cần thư viện HTTP ngoài JDK | Ứng dụng đơn giản, TLS theo truststore của JVM | Truststore, connect/read timeout, proxy; mặc định không thể suy ra đã cấu hình mTLS riêng |
| **Apache HttpComponents 5** | `org.apache.httpcomponents.client5:httpclient5` | Muốn `SslConfiguration` riêng cho Vault, keystore/truststore, quản trị kết nối chi tiết | Xác minh request factory thực tế, mTLS, pooling, shutdown; tránh wire logging |
| **Reactor Netty** | `io.projectreactor.netty:reactor-netty` | Ứng dụng cần transport Netty, đặc biệt với reactive integration | Reactor/WebFlux phiên bản phù hợp, resource lifecycle, timeout và TLS |
| **Jetty** | Client module Jetty phù hợp với stack | Hệ thống đang dùng Jetty hoặc yêu cầu connector riêng | Không nhầm artifact reactive Jetty với các artifact Jetty khác |
| **Apache HTTP Core reactive** | `org.apache.httpcomponents.core5:httpcore5-reactive` | Reactive client theo HTTP Components | Phiên bản và tích hợp reactive tương ứng |

Việc thêm một JAR **không bảo đảm** client được chọn đúng như mong muốn nếu classpath có nhiều transport. Trong trường hợp cần cố định transport, tạo `ClientHttpRequestFactory` / reactive connector theo cấu hình rõ ràng rồi xác minh lúc chạy.

Ví dụ Maven chỉ khi **muốn Apache HttpComponents 5**:

```xml
<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
    <!-- Phiên bản do BOM tương thích quản lý -->
</dependency>
```

Ví dụ Gradle nếu chọn **Reactor Netty** và đã import BOM tương ứng:

```kotlin
dependencies {
    implementation("io.projectreactor.netty:reactor-netty")
}
```

Các đoạn trên chỉ minh họa dependency. Cần đồng bộ Spring Framework/WebFlux, HTTP client và Reactor theo BOM; không khai báo nhiều transport chỉ vì muốn “đủ tính năng”. **Không bật HTTP wire logging trong production**: header `X-Vault-Token` và body secret có thể xuất hiện trong log.

Nguồn: [HTTP Client Support – Spring Vault 4.1.2](https://docs.spring.io/spring-vault/reference/vault/client-support.html).

## 4. Dependency JSON: Jackson 3, Jackson 2 và HTTP message converters

### 4.1. Vì sao `spring-vault-core` chưa đủ cho JSON?

Spring Vault 4.x **không kéo Jackson transitively** theo mặc định để ứng dụng có thể chọn thế hệ JSON. Với Spring Framework 7, **Jackson 3** (group `tools.jackson.*`) là hướng ưu tiên. Spring Vault 4.x còn khả năng tương thích Jackson 2 (group `com.fasterxml.jackson.*`), nhưng nếu **cả Jackson 2 và 3** có mặt, Spring Vault **ưu tiên Jackson 3**; tài liệu cũng nêu HTTP client hướng đến Jackson 3.

Ví dụ `pom.xml` trong ứng dụng **đã có Spring Boot 4.x parent/BOM**, có thể khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
    </dependency>
    <dependency>
        <groupId>tools.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <!-- Version được BOM Boot 4.x quản lý -->
    </dependency>
</dependencies>
```

Ví dụ Gradle tương ứng, khi **đã import Spring Boot BOM**:

```kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("tools.jackson.core:jackson-databind")
}
```

Nếu dùng Spring Framework thuần, cần chủ động quản lý phiên bản Jackson 3 và Spring Framework 7 bằng BOM hoặc khai báo cụ thể. **Không copy một dependency không có `<version>` sang Maven/Gradle không dùng dependency management.**

Với dự án Spring Vault 3.x + Spring Framework 6.x, hãy giữ **Jackson 2** theo BOM của stack 3.x và đọc đúng tài liệu phiên bản đó. Khi nâng lên Framework 7, kiểm tra toàn bộ mapper/module (kể cả Java Time, Kotlin, custom serializers) chứ không chỉ đổi groupId.

### 4.2. Mapper khác converter

**Jackson mapper** chuyển JSON ↔ Java object; ví dụ Jackson 3 có các loại thuộc namespace `tools.jackson.databind` và Spring Boot 4 thường quản lý `JsonMapper`. **Spring HTTP message converters/codecs** chọn mapper thích hợp cho `Content-Type: application/json` và kiểu đích của request/response.

```text
Java request object
      ↓  (Jackson + HttpMessageConverter)
JSON body  --HTTPS-->  Vault
      ↑
Vault JSON response
      ↓  (HttpMessageConverter + Jackson)
VaultResponse / VaultResponseSupport<T> / domain object
```

Nếu ứng dụng tự cấu hình một `RestClient` rồi truyền vào `VaultClient.builder(restClient)`, client đó **phải có message converters** hỗ trợ `String`, `byte[]` và JSON. Một client được tạo chỉ với converter tùy biến và bỏ mất JSON converter có thể kết nối được nhưng thất bại lúc `retrieve().body(...)`.

Trong ứng dụng Boot có cả Jackson 2/3, đừng mặc định rằng custom `com.fasterxml.jackson.databind.ObjectMapper` cũ tự động điều khiển mọi request của Spring Vault 4.x. Kiểm tra converter thực sự được gắn với client và kiểm thử response có cấu trúc của Vault.

Nguồn: [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html), [VaultClient API – Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html), [Spring Boot – JSON](https://docs.spring.io/spring-boot/reference/features/json.html).

## 5. Cấu hình endpoint, timeout và TLS cho `VaultClient`

### 5.1. Khởi tạo bằng `VaultEndpoint` và `SessionManager`

Với Spring Vault 4.1, đoạn code sau thể hiện cách gắn **HTTP client cấp thấp** vào `VaultTemplate`; giả định ứng dụng đã cấu hình một `SessionManager` có thể đăng nhập workload (Kubernetes/JWT/AppRole hoặc cơ chế thích hợp):

```java
import java.net.URI;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

class VaultClientSetup {
    static VaultOperations create(SessionManager sessionManager) {
        VaultEndpoint endpoint = VaultEndpoint.from(
                URI.create("https://vault.internal.example:8200"));
        VaultClient client = VaultClient.builder()
                .endpoint(endpoint)
                .build();

        return new VaultTemplate(client, sessionManager);
    }
}
```

`https://vault.internal.example:8200` chỉ là endpoint minh họa. `VaultClient` xử lý request Vault; **`SessionManager` chịu trách nhiệm lấy và tái sử dụng token** khi được kết hợp với `VaultTemplate`. Nếu gọi `VaultClient` trực tiếp để làm một thao tác có xác thực, cần đặt token của session hoặc dùng cơ chế client phù hợp; việc gọi `VaultClient.create(...)` đơn lẻ không tự đăng nhập.

### 5.2. Timeout và SSL certificate

`ClientOptions` của Spring Vault cung cấp connect/read timeout (mặc định được Javadoc mô tả là 5 giây kết nối và 15 giây đọc). Có thể tạo request factory với cấu hình phù hợp. Ví dụ dưới đây cố ý không ghi mật khẩu truststore vào source:

```java
import java.time.Duration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.vault.client.ClientHttpRequestFactoryFactory;
import org.springframework.vault.support.ClientOptions;
import org.springframework.vault.support.SslConfiguration;

// trustStorePassword được cấp từ secret/config runtime,
// không viết hằng mật khẩu vào file Java.
ClientOptions options = new ClientOptions(
        Duration.ofSeconds(3), Duration.ofSeconds(12));

SslConfiguration ssl = SslConfiguration.forTrustStore(
        new FileSystemResource("/etc/vault/tls/truststore.p12"),
        trustStorePassword);

ClientHttpRequestFactory factory =
        ClientHttpRequestFactoryFactory.create(options, ssl);
```

Đoạn trên giả định **`trustStorePassword` là `char[]` đã được cấp bởi môi trường** và file truststore đã tồn tại; phần kết nối factory với client:

```java
VaultClient client = VaultClient.builder()
        .endpoint(VaultEndpoint.from(
                URI.create("https://vault.internal.example:8200")))
        .requestFactory(factory)
        .build();

VaultOperations operations = new VaultTemplate(client, sessionManager);
```

Hai khối mã là **minh họa cấu hình**, cần đặt trong cùng method với các import và biến thuộc phạm vi. Khi tạo/chạy request factory thủ công, quản lý lifecycle khởi tạo và đóng tài nguyên theo loại factory. Trong Spring context, nên để các thành phần có lifecycle được quản lý đúng cách.

**Ràng buộc quan trọng:** tài liệu Spring Vault ghi `SslConfiguration` **chỉ được áp dụng theo cơ chế này khi Apache HttpComponents có mặt trên classpath**. Nếu dùng JDK `HttpClient` mặc định, cấu hình JVM truststore như `javax.net.ssl.trustStore` hoặc cung cấp SSL context/request factory phù hợp; không giả định truyền `SslConfiguration` vào bất kỳ transport nào cũng mang lại cùng kết quả. Với mTLS, ngoài truststore còn phải cấu hình **keystore chứa client certificate/private key**, và Vault server phải bật xác thực TLS tương ứng.

Kiểm tra riêng:

- **Connect timeout:** thời gian thiết lập kết nối, kể cả DNS/proxy theo đặc tính transport.
- **Read/response timeout:** chờ phản hồi Vault; đừng đặt ngắn đến mức các request PKI hoặc retry ngắn thường xuyên bị ngắt.
- **TLS:** hostname verification, CA chain, ngày hết hạn certificate, SNI, mTLS client cert, truststore đúng vị trí.
- **Connection pooling/keep-alive:** phù hợp với số pod, số request và giới hạn Vault; không tạo một HTTP client mới trên mỗi lần gọi `kv.get()`.
- **HA/load balancer:** endpoint hoặc cơ chế failover phù hợp; timeout không tự tạo chiến lược retry và không bảo đảm idempotency.

Không khắc phục lỗi TLS bằng cách tắt kiểm tra chứng chỉ/hostname trong production. Điều này làm mất bảo đảm định danh Vault server và có thể khiến token/secret bị gửi đến endpoint giả mạo.

Nguồn: [ClientOptions API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/ClientOptions.html), [ClientHttpRequestFactoryFactory API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ClientHttpRequestFactoryFactory.html), [HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html).

## 6. Dữ liệu Vault JSON: envelope khác payload của secret

### 6.1. Phản hồi Vault không phải lúc nào cũng là POJO “trần”

Vault HTTP API thường trả **envelope** gồm metadata như `request_id`, `lease_id`, `lease_duration`, `renewable`, `data`, `auth` hoặc `wrap_info` tùy endpoint. `VaultResponse` ánh xạ trường `data` thành `Map<String, Object>`; `VaultResponseSupport<T>` là kiểu tổng quát cho `data` có kiểu `T`.

Ví dụ payload logic của một KV v1 có thể là:

```json
{
  "request_id": "example-request-id",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "url": "https://api.internal.example",
    "maxRetries": 3
  }
}
```

Với KV v2, **HTTP JSON thô** thường có một lớp `data` lồng bên trong `data` và metadata phiên bản:

```json
{
  "data": {
    "data": {
      "url": "https://api.internal.example",
      "maxRetries": 3
    },
    "metadata": {
      "version": 7
    }
  }
}
```

Hai ví dụ được **rút gọn** để tập trung vào sự khác nhau, không phải toàn bộ response có thể có từ Vault Server. Nếu gọi `VaultClient.get().path("secret/data/orders/config")` trực tiếp, bạn phải hiểu cấu trúc JSON của endpoint v2. Nếu gọi API domain `vault.opsForKeyValue("secret", KV_2).get("orders/config")`, Spring Vault xử lý khác biệt KV v1/v2 và trả phần **secret data** qua `VaultResponse.getData()`.

**Sai lầm phổ biến:** truyền `"secret/data/orders/config"` vào `opsForKeyValue("secret", KV_2).get(...)`, khiến tiền tố KV bị thêm hai lần. Hãy tách **mount** (`secret`) và **đường dẫn trong mount** (`orders/config`).

### 6.2. Đọc KV dưới dạng `Map<String, Object>`

Ví dụ dưới đây giả định đã inject bean `VaultOperations` và Vault mount `secret` là **KV v2**:

```java
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

class SecretSettingsReader {
    private final VaultOperations vault;

    SecretSettingsReader(VaultOperations vault) {
        this.vault = vault;
    }

    Map<String, Object> load() {
        VaultKeyValueOperations kv =
                vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
        VaultResponse response = kv.get("orders/config");

        if (response == null || !response.hasData()) {
            throw new IllegalStateException("Required Vault config is missing");
        }
        return response.getRequiredData();
    }
}
```

Kiểu `Map` hữu ích cho secret có cấu trúc động; nhưng nên kiểm tra kiểu dữ liệu cụ thể trước khi ép kiểu. Chẳng hạn, một số JSON number có thể thành `Integer`, `Long` hoặc kiểu số khác tùy mapper và độ lớn; không viết `(Integer) map.get("maxRetries")` nếu không kiểm soát kiểu. Với cấu hình có schema cố định, dùng POJO thường an toàn hơn.

### 6.3. Chuyển đổi typed response thành POJO

`VaultKeyValueOperations` có overload `get(String path, Class<T> responseType)`, trả `VaultResponseSupport<T>`. Có thể định nghĩa DTO:

```java
public record OrderConfig(String url, int maxRetries) { }
```

Và đọc thành kiểu cụ thể:

```java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

class TypedSecretReader {
    private final VaultOperations vault;

    TypedSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    OrderConfig load() {
        VaultResponseSupport<OrderConfig> result = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config", OrderConfig.class);
        if (result == null || !result.hasData()) {
            throw new IllegalStateException("Required Vault config is missing");
        }
        return result.getRequiredData();
    }
}
```

`OrderConfig` là **Java record** (Java 17+), các trường JSON phải có tên và kiểu tương ứng. Đoạn code không xác thực dữ liệu nghiệp vụ: ngoài việc đọc thành công, nên validate `url`, giới hạn `maxRetries` và những thuộc tính bắt buộc. Với nested object, datetime, enum hoặc kiểu giá trị riêng, có thể cần Jackson modules/converters tương ứng.

**Khi nào không nên map thẳng vào POJO?** Secret có schema thường xuyên thay đổi, response chứa metadata lease/token đặc biệt hoặc endpoint Transit/PKI có response domain riêng. Khi đó bắt đầu từ API domain hoặc `VaultResponse`, rồi chuyển đổi đúng phần `data` cần thiết.

Nguồn: [VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html), [VaultResponse API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html), [Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html).

## 7. Gọi endpoint bằng `VaultClient` và hiểu HTTP message conversion

Ví dụ khi cần một endpoint không có API domain tương ứng, sử dụng client fluent (Spring Vault 4.1+). Đoạn code nhận `VaultClient` và `SessionManager` từ cấu hình hạ tầng:

```java
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.support.VaultResponse;

class RawVaultReader {
    static VaultResponse readKvV2(
            VaultClient client, SessionManager sessionManager) {

        return client.get()
                .path("secret/data/orders/config")
                .token(sessionManager.getSessionToken())
                .retrieve()
                .requiredBody();
    }
}
```

Ở đây:

- `path(...)` là **đường dẫn Vault HTTP API**, không phải đường dẫn tương đối trong KV mount như `kv.get(...)`.
- `token(...)` nhận `VaultToken` từ session manager. Không hard-code token, cũng không in token hoặc toàn bộ `VaultResponse` ra log.
- `retrieve()` chỉ tạo `ResponseSpec`; **lời gọi terminal** như `body(...)`, `requiredBody()` hoặc `toBodilessEntity()` mới gửi HTTP request.
- `requiredBody()` lấy response theo kiểu Vault mặc định; `body(SomeType.class)` dựa trên HTTP message converter để chuyển **toàn bộ JSON response** sang kiểu đích. Nếu muốn chỉ payload ở `data.data` của KV v2, xử lý envelope đúng cách hoặc ưu tiên `VaultKeyValueOperations`.

Khi chuyển dữ liệu với generic type, Spring `ParameterizedTypeReference<T>` giúp giữ thông tin kiểu (ví dụ `List<SomeDto>`) cho message converter. Tuy nhiên không giả định response của Vault là danh sách thuần: hầu hết endpoint đặt dữ liệu dưới khóa `data` và có metadata. Cần xác minh schema API cụ thể trước khi tạo type đích.

### Phân biệt chuyển đổi của `VaultClient` và Spring Data Vault repositories

Nếu dùng **Spring Data Vault repositories**, còn có tầng mapping khác:

```text
Vault JSON
   ↓ Jackson (HTTP → VaultResponse.data)
Map<String, Object>
   ↓ SecretDocument / VaultConverter / VaultCustomConversions
Spring Data entity (có @Secret, @Id...)
```

`VaultConverter` ánh xạ document sang entity, có thể ghi metadata `_class` cho kiểu đa hình; `VaultCustomConversions` tùy biến mapping một số kiểu như `LocalDate` hoặc một kiểu value object. Tầng này chỉ cần khi dùng **repositories**; một ứng dụng gọi `VaultTemplate.opsForKeyValue(...)` trực tiếp **không phải** cấu hình toàn bộ Spring Data mapping.

Lưu ý khi ghi repository: mapping lại document có thể **ghi đè trường không được model hóa** trong entity. Nếu nhiều ứng dụng cùng sửa một KV secret, cần thỏa thuận schema, concurrency/CAS (khi dùng KV v2) và tránh lưu object chứa field nhạy cảm ngoài ý muốn.

Nguồn: [VaultClient – Request/Response Conversion](https://docs.spring.io/spring-vault/reference/vault/vault-client.html), [Vault Repositories – Object to Vault JSON Mapping](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html).

## 8. JSON ngoài KV: Transit, PKI, token và lease

Cùng là response HTTP/JSON nhưng **không thể coi `data` của mọi endpoint là một cấu trúc secret KV**:

| Vault endpoint | Ví dụ nội dung trong JSON response | Cách dùng ở Spring Vault |
| --- | --- | --- |
| KV v1/v2 | Những cặp khóa–giá trị của secret; KV v2 có metadata phiên bản | `opsForKeyValue` / `opsForVersionedKeyValue` |
| Transit encrypt/decrypt | Ciphertext, key version, plaintext Base64 theo API | `opsForTransit`; đối tượng kết quả domain thay cho tự ép kiểu JSON thô |
| PKI issue | Certificate, private key, issuing CA, serial, lease/duration tùy vai trò | `opsForPki`; bảo vệ key/cert và vòng đời rotation |
| Token/auth | `auth.client_token`, policies, TTL, renewable | `ClientAuthentication` + `SessionManager`; không chỉ đọc `data` |
| Dynamic credentials | `data.username`/`data.password` cùng `lease_id`, `lease_duration` | `SecretLeaseContainer` và các API quản lý vòng đời; metadata quyết định renew/rotate |

**Ví dụ lỗi logic:** map mọi response vào `Map<String, String>` rồi bỏ qua `lease_duration` sẽ khiến ứng dụng giữ credential đã hết hạn. Hoặc map JSON Transit trực tiếp thành secret KV có thể dẫn đến nhầm một chuỗi Base64 với plaintext. Nên ưu tiên domain API đã hiểu semantics của engine, rồi kiểm thử schema với server thực.

## 9. Reactive `WebClient` và chuyển đổi không chặn luồng

Spring Vault reactive dùng **`ReactiveVaultTemplate`/`ReactiveVaultClient`** dựa trên `WebClient`. Để dùng, classpath cần Spring WebFlux và Reactor (thông thường được `spring-webflux`/starter kéo theo), cùng JSON codecs thích hợp.

```kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("org.springframework:spring-webflux")
    implementation("tools.jackson.core:jackson-databind")
}
```

Đoạn Gradle giả định có BOM quản lý phiên bản Spring/Jackson. **Không cần chạy HTTP server WebFlux** chỉ để gọi Vault theo reactive API; vẫn cần cấu hình reactive session manager và HTTP connector phù hợp.

Điểm cần kiểm tra:

- **Reactive chain** trả `Mono`/`Flux`; mapping JSON có thể xảy ra khi được subscribe, không phải tại thời điểm tạo pipeline.
- Dùng `ReactiveSessionManager` để cấp token theo reactive contract; tránh lấy token bằng lời gọi chặn luồng trong event loop.
- Timeout, retry, cancellation và backpressure được quản lý phù hợp; retry vô hạn với 403/404 hoặc lặp lại request ghi secret/PKI không có kiểm soát có thể tạo tác dụng phụ.
- WebFlux codec có kích thước buffer và cách giải mã riêng. Nếu response chứa certificate chain hoặc payload lớn, kiểm tra giới hạn codec thay vì tăng vô điều kiện.

**Không trộn `RestTemplate` và `WebClient` chỉ vì cùng dùng Jackson.** Tầng HTTP và cơ chế giải mã/khởi tạo client khác nhau; phải xác minh converter (imperative) hoặc codec (reactive) trên đường thực thi.

Nguồn: [Reactive Infrastructure – Spring Vault](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html), [Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html).

## 10. Bảng chẩn đoán lỗi HTTP/JSON và hướng xử lý

| Hiện tượng | Tầng nghi ngờ | Cách xác minh |
| --- | --- | --- |
| `SSLHandshakeException` hoặc `PKIX path building failed` | TLS/truststore/CA | Kiểm tra certificate chain, hostname, truststore của **transport đang dùng**, mTLS role |
| `ConnectException`, timeout | DNS/network/proxy/request factory | Kiểm tra endpoint, routing, timeout kết nối/đọc và kết nối từ cùng container/pod |
| JSON `HttpMessageNotReadableException`, lỗi converter hoặc deserialize | Jackson/HTTP message conversion | Kiểm tra Jackson 2/3, `Content-Type`, DTO schema, custom module, converter đã cấu hình |
| `NoClassDefFoundError`/`NoSuchMethodError` | Classpath/BOM | Kiểm tra `spring-vault-core`, Spring Framework, Jackson/WebFlux/transport ở runtime |
| Dữ liệu KV v2 trông như `{data:{...},metadata:{...}}` | Chọn sai tầng API | Phân biệt `VaultClient` raw với `opsForKeyValue(..., KV_2)`; tránh lồng `data` hai lần |
| Không tìm thấy secret, trả `null` hoặc `404` | Sai mount/version/path, secret bị xóa | Kiểm tra KV v1/v2 và đường dẫn tương đối; `readRequired` và optional read khác semantics |
| HTTP 401/403 | Auth, namespace, Vault policy | Kiểm tra token workload, TTL, ACL path/capability, auth mount; không tự coi là lỗi JSON |
| HTTP 429/5xx | Vault tải cao hoặc lỗi server | Áp dụng retry giới hạn có backoff/jitter theo loại thao tác; giám sát saturation |
| JSON đã đọc được nhưng POJO có `null` sai | Schema/mapping | Kiểm tra tên khóa, camelCase/snake_case, trường thiếu, kiểu số, null, nested object |
| Lỗi chỉ xảy ra sau khi token/lease hết hạn | Session/rotation | Xem `SessionManager`, lease renewal/rotation và các client đang giữ credential cũ |

### Nguyên tắc xử lý lỗi

`VaultClient` chuyển HTTP **4xx/5xx** thành `VaultClientResponseException` hoặc lớp con theo chính sách mặc định; `VaultTemplate` có thể chuyển đổi thành `VaultException`/lỗi domain tương ứng. Chỉ override `onStatus(...)` khi hiểu rõ semantics. Đặc biệt:

- **Không retry 403** vô hạn; kiểm tra ACL và phương thức xác thực.
- **Không coi 404 nào cũng là “đường dẫn không tồn tại”**: có thể sai KV version, mount/path hoặc endpoint.
- **Không retry POST PKI/ghi KV** mà không đánh giá idempotency, CAS và tác dụng phụ.
- **Không log response đầy đủ** để debug JSON nếu có secret hoặc token; dùng mã lỗi, thời gian, tên endpoint đã làm mờ và correlation/request id an toàn.

**Ghi chú bảo mật phiên bản:** Spring công bố **4.0.5 và 4.1.2** ngày **19/11/2026** để sửa **CVE-2026-41698** liên quan path traversal của secret path. Khi nhận path từ dữ liệu ngoài, validate segment, loại bỏ `../` hoặc URL tuyệt đối không mong muốn, ưu tiên `VaultClient.path(...)` với endpoint đã cố định và giữ dependency đã vá. Tự thay đổi converter/transport không sửa được vấn đề validate path.

## 11. Bài tập tích hợp: từ HTTPS đến DTO có kiểu

Một nhóm phát triển cần dịch vụ `orders-api` đọc cấu hình từ `secret/orders/config` (KV v2), dùng Kubernetes workload authentication, Vault policy chỉ cho phép đúng secret đó. Mục tiêu: đọc thành `OrderConfig`, từ chối thiếu field và không rò dữ liệu.

**Các bước đề xuất:**

1. Chọn bộ phiên bản đồng nhất `JDK 17+ / Spring Framework 7 / Spring Vault 4.1.2`; khai báo Jackson 3. Chỉ thêm Apache HttpComponents nếu cần `SslConfiguration` riêng.
2. Xác định endpoint HTTPS, CA truststore, connect/read timeout; cấu hình `VaultClient` và `SessionManager` dùng ServiceAccount JWT/workload role thay vì root token.
3. Mount KV v2 tại `secret`; tạo secret `orders/config` với hai khóa `url`, `maxRetries`; cấp ACL `read` trên path API `secret/data/orders/config`.
4. Đọc bằng `opsForKeyValue("secret", KV_2).get("orders/config", OrderConfig.class)`; kiểm tra `null`, validate url/retries và tránh in giá trị.
5. Kiểm thử đường thành công, field JSON sai kiểu, secret chưa tồn tại, policy thiếu `read`, CA sai và Vault timeout.
6. Nếu dùng Transit/PKI hoặc dynamic credentials, bổ sung thử nghiệm theo domain API tương ứng, bao gồm token/lease hết hạn và việc sử dụng dữ liệu sau rotation.

Ví dụ kiểm tra quyền (Vault policy minh họa):

```hcl
path "secret/data/orders/config" {
  capabilities = ["read"]
}
```

Policy này **chỉ cho quyền đọc secret KV v2** ở path đã chỉ định. Nó không tự cho quyền phát hiện mount, list metadata, ghi secret, gọi Transit hay PKI. Nếu chọn `opsForKeyValue("secret")` tự phát hiện KV version, cần kiểm tra thêm quyền/phản hồi mount discovery theo cách Spring Vault sử dụng; khi đã biết chắc KV v2, chỉ định rõ `KeyValueBackend.KV_2` giúp chủ động hơn.

## 12. Checklist trước khi đưa vào production

- [ ] Dòng Spring Vault và Spring Framework/JDK tương thích; `spring-vault-core` chỉ resolve về một phiên bản đúng.
- [ ] Jackson 3/2 đã được chọn có chủ đích, test được converter và POJO response thực tế.
- [ ] HTTP client được xác minh (JDK, Apache, Reactor/Jetty); timeout, TLS, mTLS, proxy và tài nguyên kết nối được quản lý.
- [ ] `VaultClient`/`VaultTemplate` được tái sử dụng, session manager gắn với workload auth và Vault policy quyền tối thiểu.
- [ ] Path KV v1/v2, lớp envelope `data` và metadata được xử lý đúng theo API domain.
- [ ] Transit/PKI và dynamic secret không bị map sai thành KV thuần; token/lease renewal/rotation có test.
- [ ] Không hard-code root token, bỏ qua certificate validation hay bật wire logging chứa secret.
- [ ] Có integration test với Vault thật/mô phỏng và có metric/trace an toàn cho lỗi HTTP/JSON.
- [ ] Các bản vá bảo mật Spring Vault và dependency HTTP/JSON đã được đối chiếu trước khi triển khai.

**Quy tắc ghi nhớ:** **`VaultTemplate` hiểu nghiệp vụ Vault**, **`VaultClient` hiểu request/response Vault**, **HTTP client đảm nhiệm HTTPS/TLS/timeout**, **Jackson cùng message converters/codecs chuyển JSON thành Java**. Khi gặp lỗi, hãy phân loại đúng tầng trước khi sửa dependency hoặc sửa chính sách truy cập.

### Tài liệu tham khảo chính thức

1. [Spring Vault 4.1.2 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
2. [Spring Vault – HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html)
3. [Spring Vault – Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
4. [Spring Vault – Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
5. [Spring Vault – Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
6. [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
7. [Spring Vault – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
8. [Spring Vault 4.1 – VaultClient.Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.Builder.html)
9. [Spring Vault 4.1 – VaultKeyValueOperations Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html)
10. [Spring Vault 4.1 – ClientHttpRequestFactoryFactory Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ClientHttpRequestFactoryFactory.html)
11. [Spring Boot 4 – JSON](https://docs.spring.io/spring-boot/reference/features/json.html)
12. [Spring Vault 4.0.5/4.1.2 – Security Fixes, 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
