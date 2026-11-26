# Phân biệt Spring Vault với Spring Cloud Vault và Spring Security

> **Chương:** Bản đồ Spring Vault  
> **Bối cảnh:** Cả ba dự án đều xuất hiện trong ứng dụng Spring Boot có yêu cầu bảo mật, nhưng trả lời **ba câu hỏi khác nhau**: ứng dụng Java gọi HashiCorp Vault bằng cách nào, secret được đưa vào cấu hình Spring ra sao, và ai được phép gọi API nghiệp vụ của ứng dụng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác mục đích và ranh giới của **Spring Vault**, **Spring Cloud Vault** và **Spring Security**.
2. Phân biệt **Vault token của workload** với **JWT/access token của người dùng gọi REST API**, cũng như Vault policy với phân quyền ở Spring Security.
3. Quyết định khi nào nên gọi `VaultOperations`/`VaultTemplate` trực tiếp, khi nào dùng `spring.config.import: vault://` và khi nào dùng cả hai.
4. Mô tả đường đi của một secret trong giai đoạn khởi động ứng dụng và trong một request nghiệp vụ.
5. Thiết kế ví dụ ứng dụng có Spring Security ở cổng vào, Spring Vault ở cổng ra và Vault server áp policy tối thiểu.
6. Đánh giá lỗi, vòng đời token/lease, rotation, giám sát và kiểm thử tích hợp theo đúng trách nhiệm của từng lớp.

## 1. Ba tên gần nhau, ba vai trò khác nhau

Một ứng dụng `orders-service` cần nhận JWT từ frontend, gọi API thanh toán bằng key bí mật, và sử dụng tài khoản PostgreSQL. Người mới học Spring dễ cho rằng chỉ cần thêm một thư viện “security” hoặc “vault” thì tất cả hoạt động đều tự có. Thực tế:

- **Spring Security** bảo vệ **điểm vào của ứng dụng**, ví dụ xác thực JWT của khách hàng, kiểm tra quyền `orders:write`, bảo vệ phương thức/service và các luồng đăng nhập ứng dụng.
- **Spring Vault** cung cấp **client Java để nói chuyện với HashiCorp Vault**, ví dụ `VaultOperations`/`VaultTemplate` đọc KV v2, lấy credential động, gọi Transit hoặc PKI. Vault server, không phải Spring Vault, xác thực workload và quyết định policy.
- **Spring Cloud Vault** tích hợp Vault vào **hệ thống cấu hình Spring**, đưa các secret được phép đọc thành properties trong `Environment`/`PropertySource`; nó được xây dựng trên các cơ chế client Vault và thường phục vụ lúc bootstrap hoặc chuẩn bị cấu hình.

### Bảng so sánh nhanh

| Tiêu chí | Spring Vault | Spring Cloud Vault | Spring Security |
|---|---|---|---|
| Câu hỏi chính | Java gọi Vault API thế nào? | Lấy cấu hình nhạy cảm từ Vault vào Spring thế nào? | Ai được gọi API/phương thức của ứng dụng? |
| Điểm tích hợp | `VaultOperations`, `VaultTemplate`, auth/session, engine operations | Config Data / `PropertySource`, cấu hình nguồn KV/credential tùy phiên bản | `SecurityFilterChain`, authentication, authorization, method security |
| Thời điểm điển hình | Khi code quyết định ở runtime; cũng có thể lúc khởi động | Chủ yếu trong bootstrap/config loading; refresh phải thiết kế riêng | Mỗi HTTP request, lời gọi method và luồng security liên quan |
| Token thường làm việc với | Vault token của workload | Vault token của workload để đọc nguồn config | Access token/JWT hoặc session của caller ứng dụng |
| Quyền được kiểm tra ở đâu? | Vault server kiểm tra policy với request client gửi | Vault server kiểm tra các path nguồn config được đọc | Spring Security kiểm tra quy tắc của ứng dụng |
| Engine/chức năng đặc trưng | KV, Database, Transit, PKI và API Vault khác | KV và nguồn cấu hình/credential được hỗ trợ | OAuth2 Resource Server, OAuth2 Client, HTTP/method authorization |
| Có thể dùng độc lập? | Có | Có thể sử dụng qua starter/tích hợp phù hợp; bên dưới dựa vào thư viện client Vault | Có |
| Có thay Vault server được không? | Không | Không | Không |

**Ba thư viện không phải ba lựa chọn loại trừ nhau.** Một ứng dụng có thể dùng Spring Security để bảo vệ REST API, Spring Cloud Vault để nạp một API key vào cấu hình khi khởi động và Spring Vault để gọi Transit theo từng nghiệp vụ.

## 2. Sơ đồ kiến trúc và đường đi dữ liệu

~~~mermaid
flowchart LR
    USER["Người dùng / frontend<br/>access token"] -->|HTTPS| SEC["Spring Security<br/>filter chain + method auth"]

    subgraph APP["JVM: orders-service"]
        SEC --> API["Controller / business service"]
        ENV["Spring Environment<br/>cấu hình app"]
        SV["Spring Vault<br/>VaultOperations / VaultTemplate"]
        SCV["Spring Cloud Vault<br/>Config Data integration"]
        API -->|"Lấy property khi cần"| ENV
        API -->|"Gọi Vault API runtime"| SV
        SCV -->|"Nạp properties"| ENV
    end

    ID["Danh tính workload<br/>Kubernetes / IAM / AppRole"] --> VA["Vault auth method<br/>+ token"]
    SV -->|"HTTPS + Vault token"| VA
    SCV -->|"HTTPS + Vault token"| VA
    VA --> POL["Vault policies<br/>theo path + capability"]
    POL --> EN["Secrets engines<br/>KV / Database / Transit / PKI"]
    API -->|"Gọi với API key hoặc DB credential"| TARGET["Dịch vụ đích<br/>payment / database"]
~~~

Sơ đồ có **hai đường bảo mật độc lập**:

1. **Phía vào:** người dùng hoặc ứng dụng khách gọi `orders-service`. Spring Security xác thực caller và đánh giá quyền nghiệp vụ.
2. **Phía ra:** `orders-service` tự chứng minh danh tính **workload** với Vault; Vault cấp token theo role rồi áp policy khi service đọc secret hoặc gọi engine.

Với cấu hình thông thường, nhiều người dùng đầu cuối **cùng đi qua một danh tính Vault của service**. Điều này không sai nếu kiến trúc chủ ý dùng workload identity, nhưng nghĩa là **Vault không thể thay Spring Security quyết định người dùng A có được xử lý đơn hàng B không**.

### Hình dung bằng một request

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Frontend
    participant S as Spring Security
    participant B as Orders business service
    participant C as Spring Vault client
    participant V as Vault server
    participant P as Payment provider

    U->>S: POST /orders/42/payment<br/>Authorization: Bearer user-JWT
    S->>S: Xác thực JWT + kiểm tra quyền/ownership
    alt Người dùng không được phép
        S-->>U: 401 hoặc 403
    else Người dùng có quyền
        S->>B: Xử lý thanh toán
        B->>C: KV v2 get("prod/orders/payment")
        C->>V: Vault HTTPS request với workload token
        V->>V: Xác thực token + policy read trên path
        V-->>C: API key hoặc lỗi Vault
        C-->>B: Dữ liệu secret được phép đọc
        B->>P: Gọi cổng thanh toán bằng API key
        P-->>B: Kết quả giao dịch
        B-->>U: Kết quả nghiệp vụ, không chứa API key
    end
~~~

Nếu Spring Security từ chối trước khi gọi service, **không cần gọi Vault**. Nếu người dùng được phép nhưng Vault policy từ chối, lỗi đó thuộc **quyền của workload đối với Vault**, không phải lỗi JWT của người dùng. Ứng dụng cần xử lý và ghi nhận theo đúng nguồn lỗi.

## 3. Spring Vault: client Java truy cập Vault tại thời điểm cần

**Spring Vault** là lựa chọn trực tiếp khi Java code phải tương tác với Vault API: đọc KV secret, yêu cầu credential Database động, theo dõi token/lease, gọi Transit encrypt/decrypt hoặc PKI issue/sign. Một số thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `VaultOperations` | Interface thao tác Vault; business code nên phụ thuộc interface khi phù hợp |
| `VaultTemplate` | Implementation đồng bộ thường dùng của `VaultOperations` |
| `VaultKeyValueOperations` | API chuyên biệt cho KV; phân biệt KV v1 và KV v2 |
| `VaultEndpoint` | Thông tin địa chỉ Vault server, không phải đường dẫn secret |
| `ClientAuthentication` | Chiến lược đăng nhập Vault hoặc cung cấp Vault token |
| `SessionManager` | Cung cấp token cho client, quản lý phiên theo implementation |
| `LifecycleAwareSessionManager` | Có khả năng xử lý renewal và lifecycle của token đủ điều kiện |
| `SecretLeaseContainer` | Có thể quản lý lease/rotation cho secret được đăng ký theo cấu hình |

`VaultTemplate` **không chạy Vault server trong JVM**. Nó dùng HTTP/TLS để gọi server bên ngoài; server xác thực, áp policy và xử lý secrets engine. Client giúp Java gọi API nhất quán, nhưng không tự tạo mount, policy, role hoặc audit device cho một dự án.

### 3.1. Ví dụ đọc KV v2 bằng `VaultOperations`

Giả sử Vault server đã có mount **KV v2** ở `secret/`, key logic `prod/orders/payment` với field `api-key`; một workload role có quyền `read` đúng path.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentSecretReader {

    private final VaultKeyValueOperations kv;

    public PaymentSecretReader(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String readPaymentApiKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required Vault secret is missing");
        }

        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException("Required API key field is missing");
        }
        return key;
    }
}
~~~

Lời gọi Java `kv.get("prod/orders/payment")` tương ứng HTTP API của KV v2 tại `GET /v1/secret/data/prod/orders/payment`. Policy HCL có thể là:

~~~hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Đường dẫn policy **không** chứa tiền tố `/v1/`. Đoạn `data/` nằm trong đường dẫn API KV v2, còn đối số `get` của API KV cấp cao là **key logic**, không thêm `data/` lần nữa. Không cần `list` nếu ứng dụng biết sẵn key cần đọc.

Ví dụ đã giả định bean `VaultOperations` được cấu hình ở nơi khác với endpoint, authentication, session manager và TLS trust thích hợp. Nó cũng chưa mô tả cache/rotation của API key; việc đọc key thành công không có nghĩa key còn hợp lệ ở nhà cung cấp thanh toán.

### 3.2. Khi gọi API runtime thích hợp hơn đọc cấu hình

Chọn Spring Vault trực tiếp nếu ứng dụng cần:

- Gọi Transit để **mã hóa/ký/giải mã ở runtime**; thao tác này tạo response theo input của từng yêu cầu, không phải một property cấu hình cố định.
- Xin credential Database theo role và quản lý lease, TTL, rollover pool theo lifecycle nghiệp vụ.
- Gọi PKI để phát hành certificate, xử lý CSR/private key và cập nhật TLS context theo thời hạn.
- Lấy một KV key có điều kiện hoặc xử lý version cụ thể, rồi quyết định lúc refresh/cache.
- Phân loại rõ `403`, `404`, timeout, token expired hoặc lỗi từ engine và thể hiện hành vi fail closed phù hợp.

Với tương tác có side effect như phát hành credential, việc retry sau timeout phải cân nhắc request đã được server xử lý nhưng response bị mất. Không coi mọi lệnh gọi Vault như một getter thuần có thể retry vô hạn.

## 4. Spring Cloud Vault: đưa Vault vào nguồn cấu hình Spring

**Spring Cloud Vault** bổ sung một con đường khác: thay vì để service chủ động gọi Vault ở mỗi chỗ cần thiết, framework nạp các giá trị từ những path Vault được cấu hình và đưa chúng thành properties để các thành phần Spring dùng thông qua `Environment`, `@Value` hoặc `@ConfigurationProperties`.

Ví dụ, `payment.api-key` được lưu ở một context KV mà Spring Cloud Vault được phép đọc. Bean cấu hình có thể sử dụng property này mà không trực tiếp gọi `VaultOperations`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(String apiKey, String endpoint) {
}
~~~

Sau khi đăng ký cấu hình properties bằng cơ chế phù hợp (ví dụ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`), ứng dụng có thể inject `PaymentProperties`. Điều này **không biến API key thành công khai**: object cấu hình và Spring `Environment` vẫn chứa giá trị cần bảo vệ.

### 4.1. Ví dụ Config Data import

Với những phiên bản Spring Boot/Spring Cloud Vault tương thích, cấu hình hướng **Config Data API** có thể trông như sau:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-role
      kv:
        enabled: true
        backend: secret
~~~

Đây là **mô hình cấu hình**, chưa phải bản triển khai production hoàn chỉnh. Để chạy thật còn cần dependency Spring Cloud Vault tương thích với Spring Boot, ServiceAccount JWT được cấp và truy cập đúng trong pod, cấu hình Kubernetes auth role tại Vault, CA trust, chính sách đọc đúng context paths, cùng cách xử lý lỗi bootstrap.

Tên context, profile, mount và thứ tự ưu tiên các property sources phụ thuộc lựa chọn cấu hình. Ví dụ, nếu người quản trị dùng KV v2 mount `secret`, ứng dụng phải được cấp quyền trên **HTTP API path thực tế** của những contexts mà Cloud Vault sẽ truy cập; không suy ra policy chỉ từ tên `spring.application.name` mà chưa kiểm tra cấu hình path.

### 4.2. Điều gì xảy ra khi ứng dụng khởi động?

~~~mermaid
sequenceDiagram
    autonumber
    participant Boot as Spring Boot Config Data
    participant Cloud as Spring Cloud Vault
    participant V as Vault server
    participant Env as Spring Environment
    participant Beans as Application beans

    Boot->>Cloud: Xử lý import vault://
    Cloud->>V: Login bằng workload identity
    V-->>Cloud: Vault token + policies
    Cloud->>V: Đọc các config contexts đã khai báo
    V-->>Cloud: Giá trị config được phép đọc
    Cloud-->>Env: Thêm property sources
    Env-->>Beans: Bind @ConfigurationProperties / @Value
    Note over Beans: Bean có thể giữ bản sao giá trị<br/>sau khi đã khởi tạo
~~~

Spring Cloud Vault có thể đọc và quản lý nguồn secret theo lifecycle hỗ trợ, nhưng **không bảo đảm mọi bean, datasource hoặc HTTP client tự đổi credential khi secret ở Vault thay đổi**. Một datasource đã được xây dựng bằng password cũ có thể tiếp tục dùng nó cho đến khi có cơ chế refresh/recreate pool. Cần hiểu cách phiên bản đang dùng quản lý refresh và lease events trước khi thiết kế dynamic credential.

### 4.3. Điểm mạnh và đánh đổi

**Thuận tiện:** có thể cấu hình đối tượng Spring quen thuộc bằng externalized configuration, giảm code HTTP/Vault ở lớp nghiệp vụ, phân tách cấu hình môi trường và dễ thay nguồn config theo profile/role.

**Đánh đổi:** secret có thể đi vào `Environment`, binding objects, actuator/config endpoint hoặc dump chẩn đoán nếu hệ thống bảo vệ không đúng. Thời điểm startup tạo phụ thuộc mới: Vault không sẵn sàng hoặc workload chưa đăng nhập được có thể làm ứng dụng không tải được cấu hình bắt buộc. Rotation và refresh cần kiểm thử, đặc biệt với connection pool và OAuth client.

Đừng dùng Spring Cloud Vault chỉ để giả lập một lời gọi **Transit encrypt per request** bằng property. Đây là operation ở runtime, không phải dữ liệu cấu hình khởi động.

## 5. Spring Security: kiểm soát caller của ứng dụng

**Spring Security** tập trung vào xác thực và phân quyền tại biên ứng dụng hoặc phương thức: HTTP Basic, form login, session, OAuth2/OIDC login, OAuth2 Resource Server JWT, OAuth2 Client và method security tùy trường hợp.

Trong một REST API dùng JWT:

- **Authentication:** bearer token của caller hợp lệ và được nhận diện là một principal.
- **Authorization:** principal có scope/role và quyền trên tài nguyên mà request muốn thao tác.
- **Application enforcement:** `SecurityFilterChain` và các rule như `requestMatchers`, `@PreAuthorize` kiểm tra trước khi gọi nghiệp vụ.

Đây là **phân quyền truy cập nghiệp vụ**, không phải policy của Vault. Spring Security không tự bật auth method Kubernetes trên Vault và Vault cũng không tự biết người dùng REST đã được Spring Security xác thực.

### 5.1. Ví dụ filter chain cho REST API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated())
            // Chỉ dùng cấu hình sau cho API stateless không xác thực bằng cookie.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ dùng API Spring Security 6+ tương ứng với nhánh Spring Boot hiện đại. Ở đây giả định REST API **stateless**, chỉ nhận bearer token qua header và không dựa vào cookie cho authentication, nên có cấu hình tắt CSRF và không tạo session. Nếu ứng dụng dùng cookie/session hoặc có endpoint trình duyệt khác, phải đánh giá lại và bảo vệ CSRF phù hợp; không áp dụng cấu hình tắt CSRF một cách máy móc. Trong triển khai thực tế, cần cấu hình issuer/JWK hoặc bộ kiểm tra JWT tin cậy, giới hạn audience và claims, cùng bảo vệ những endpoint quản trị. Chỉ có filter chain trên **chưa đủ** để xác minh issuer hoặc quyền sở hữu từng đơn hàng.

### 5.2. Quyền business không phải quyền Vault

Ứng dụng có thể áp phương thức security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderPaymentService {

    private final PaymentSecretReader secrets;
    private final PaymentProviderClient provider;

    public OrderPaymentService(
            PaymentSecretReader secrets,
            PaymentProviderClient provider) {
        this.secrets = secrets;
        this.provider = provider;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public PaymentResult pay(String orderId) {
        // Ngoài scope, nghiệp vụ phải kiểm tra quyền trên orderId
        // để tránh người dùng A thanh toán đơn hàng không thuộc quyền.
        String key = secrets.readPaymentApiKey();
        return provider.pay(orderId, key);
    }
}

// Adapter nghiệp vụ minh họa; implementation gửi HTTPS
// đến cổng thanh toán, không trả/ghi log API key.
interface PaymentProviderClient {
    PaymentResult pay(String orderId, String apiKey);
}

record PaymentResult(String status) { }
~~~

`@PreAuthorize` kiểm tra quyền của **caller được Spring Security xác thực** trước khi thực hiện phương thức qua Spring proxy. Quy tắc này không trực tiếp kiểm tra Vault policy; sau đó `PaymentSecretReader` mới đọc KV bằng danh tính Vault của workload. Khi có nhiều tenant/người dùng, kiểm tra resource ownership/ABAC cũng phải xảy ra ở ứng dụng, không chỉ kiểm tra scope rộng.

Không trả lại API key trong `PaymentResult`, không log argument `apiKey`. Nếu Vault trả 403, không biến kết quả thành HTTP 403 ám chỉ **người dùng cuối** thiếu quyền khi nguyên nhân là cấu hình workload; cần mapping lỗi nội bộ phù hợp.

## 6. Phân biệt ba loại danh tính và ba tầng quyền

~~~mermaid
flowchart TB
    E["End user / API client"] -->|"OIDC/JWT / session"| Q["Spring Security principal"]
    Q -->|"Role, scope, quyền tài nguyên"| APP["Ứng dụng cho phép nghiệp vụ"]
    W["Kubernetes pod / VM / CI job"] -->|"ServiceAccount JWT / IAM / AppRole"| V["Vault auth role"]
    V -->|"Vault token và policies"| P["Vault ACL trên API path"]
    P -->|"Secret / operation được cấp"| APP
    APP -->|"API key / DB credential"| SYS["Hệ thống đích kiểm tra credential và quyền"]
~~~

| Danh tính/quyền | Ví dụ | Ai cấp/kiểm tra? | Điều cần tránh |
|---|---|---|---|
| **Người dùng REST** | User JWT có scope `orders.write` | Identity provider phát token; Spring Security xác minh và áp authorization | Cho mọi authenticated user truy cập mọi order |
| **Workload gọi Vault** | Pod `orders-service` đăng nhập bằng Kubernetes auth | Vault auth method kiểm chứng bằng chứng, gắn role/policy vào token | Hard-code root token hoặc dùng token Vault chung cho mọi service |
| **Credential hệ thống đích** | API key payment hoặc DB account được Vault cấp | Payment provider/DB kiểm tra khi service kết nối | Cho rằng Vault policy tự thay phân quyền SQL/đối tác |

**Spring Security token không đồng nhất với Vault token.** Chúng có thể cùng là chuỗi bearer token, nhưng có issuer, audience, semantics và endpoint xác thực khác nhau. Đừng lấy JWT người dùng từ header `Authorization` rồi gắn vào `X-Vault-Token`. Ngược lại, không đưa Vault token vào JWT/response trả người dùng.

Trường hợp phải sử dụng Vault theo **danh tính từng người dùng** có thể tồn tại, nhưng cần một thiết kế explicit: mapping identity, policy, giới hạn ủy quyền và auditing riêng. Nó không tự xuất hiện chỉ vì ứng dụng đồng thời có Spring Security và Spring Vault.

### 6.1. Nguy cơ “confused deputy”

Nếu REST endpoint cho phép bất kỳ caller nào yêu cầu “đọc secret theo path gửi lên”, attacker có thể lợi dụng quyền Vault rộng của service để lấy bí mật mà attacker không trực tiếp đọc được. Vault chỉ nhìn thấy **workload token** hợp lệ; nếu path còn nằm trong policy, Vault có thể trả secret.

Vì vậy:

1. API nghiệp vụ phải kiểm soát **ai được yêu cầu hành động**, và không cho caller tùy ý chọn Vault path.
2. Vault policy của workload chỉ cấp đúng path/operation cần thiết.
3. Secret nhận được phải được dùng trong adapter nội bộ, không serialize thành API response.
4. Với hệ thống nhiều tenant, kiểm tra ownership và giới hạn dữ liệu ở lớp business; không phụ thuộc duy nhất vào một scope chung.

Đây là ví dụ vì sao Spring Security và Vault policy **bổ sung** nhau thay vì thay thế nhau.

## 7. Chọn thư viện theo tình huống sử dụng

| Tình huống | Lựa chọn phù hợp | Vì sao? |
|---|---|---|
| Có 3 API key để cấu hình HTTP client lúc startup | Spring Cloud Vault hoặc Spring Vault tại bootstrap | Nạp property tiện; phải có kế hoạch refresh/rotation |
| Cần gọi Transit encrypt cho từng bản ghi nhạy cảm | Spring Vault trực tiếp | Mỗi request có input và ciphertext response, là operation runtime |
| Cần phát hành certificate PKI ngắn hạn rồi reload mTLS | Spring Vault trực tiếp + quản lý TLS context | Có CSR/private key, certificate TTL và workflow cập nhật |
| Cần credential DB động theo lease | Spring Vault/SecretLeaseContainer hoặc tích hợp Spring Cloud Vault phù hợp | Phải quản lý lease và kết nối pool sau khi nhận credential mới |
| REST API phải chỉ cho người có scope đặt hàng | Spring Security | Xác thực caller và kiểm tra quyền nghiệp vụ |
| REST API cần xác thực caller rồi dùng API key trong Vault | Spring Security + Spring Vault (hoặc Spring Cloud Vault) | Một lớp bảo vệ đầu vào, lớp kia cấp secret cho thao tác đầu ra |
| Chỉ cần bảo vệ REST API, không dùng Vault | Spring Security | Không cần dependency Vault nếu không có nhu cầu |
| Batch job không nhận request từ người dùng nhưng cần secret | Spring Vault hoặc Spring Cloud Vault | Workload vẫn phải xác thực với Vault; không nhất thiết dùng HTTP security filter |

Quy tắc chọn nhanh:

~~~mermaid
flowchart TD
    START{"Bạn đang giải quyết<br/>vấn đề nào?"}
    START -->|"Xác thực/ủy quyền caller"| SEC["Spring Security"]
    START -->|"Nạp property cấu hình từ Vault"| CLOUD["Spring Cloud Vault"]
    START -->|"Thao tác Vault API ở runtime"| VAULT["Spring Vault"]
    CLOUD --> MORE{"Cần Transit/PKI hay thao tác<br/>tùy input lúc chạy?"}
    MORE -->|"Có"| VAULT
    MORE -->|"Không"| DONE["Cấu hình, lifecycle, rotation"]
    SEC --> MIX{"Nghiệp vụ còn cần secret?"}
    MIX -->|"Có"| CLOUD
    MIX -->|"Cần operation runtime"| VAULT
~~~

Một hệ thống sử dụng nhiều thư viện vẫn cần **một mô hình rõ ràng**: lấy secret lần đầu ở đâu, module nào giữ tham chiếu, ai refresh và ai chịu trách nhiệm khi credential hết hạn.

## 8. Tích hợp cả ba trong một dịch vụ Spring Boot

Một thiết kế thực tế có thể chia trách nhiệm như sau:

| Giai đoạn | Thành phần | Hành vi |
|---|---|---|
| Pod khởi động | Kubernetes và Vault auth | Cấp danh tính workload, Vault cấp token theo role có giới hạn |
| Chuẩn bị cấu hình | Spring Cloud Vault | Đọc properties KV được phép theo config context |
| Spring tạo bean | Spring container | Bind `@ConfigurationProperties`; khởi tạo client/datasource cần thiết |
| HTTP request tới | Spring Security | Xác minh JWT, role/scope và quyền trên tài nguyên |
| Logic nghiệp vụ | Business service | Dùng property được nạp, hoặc gọi `VaultOperations` khi cần |
| Vault API runtime | Spring Vault | Gọi KV/Transit/PKI/Database; xử lý HTTP/session/lease theo tích hợp |
| Quyết định truy cập Vault | Vault server | Kiểm tra policy, engine trả secret hoặc lỗi |
| Dịch vụ đích | Payment provider/Database | Kiểm tra credential do ứng dụng mang tới |

### 8.1. Thiết kế policy tối thiểu

Giả sử `orders-service` chỉ được đọc một KV key và encrypt bằng Transit:

~~~hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}

path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Policy này không cấp quyền `transit/decrypt/orders-pii` hoặc đọc secret của service khác. Ứng dụng vẫn cần Spring Security để giới hạn caller có quyền kích hoạt nghiệp vụ dùng những chức năng đó. Vault policy cũng không tự tạo Vault auth role hoặc ServiceAccount Kubernetes.

### 8.2. Cấu hình Vault auth khác cấu hình Spring Security

Hai ví dụ tên trường sau có thể cùng xuất hiện trong một dự án:

~~~yaml
spring:
  cloud:
    vault:
      authentication: KUBERNETES
      kubernetes:
        role: orders-role
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/shop
~~~

`spring.cloud.vault.authentication` chỉ chiến lược **service đăng nhập Vault**. `spring.security.oauth2.resourceserver.jwt.issuer-uri` chỉ issuer mà **service dùng để xác minh JWT từ caller**. Hai hệ thống xác thực có thể dùng cùng hạ tầng danh tính trong một kiến trúc đặc biệt, nhưng cấu hình này không tự kết nối hai quyền với nhau.

Đối với một ứng dụng dùng trực tiếp Spring Vault mà không có Spring Cloud Vault starter, client bean và auth method phải được cấu hình bằng cơ chế phù hợp; không mong thuộc tính `spring.cloud.vault.*` được áp dụng nếu module Spring Cloud Vault chưa có.

## 9. Token, lease, rotation và refresh: mỗi lớp kiểm soát gì?

| Tài nguyên/vòng đời | Cơ chế liên quan | Trách nhiệm ứng dụng |
|---|---|---|
| JWT/access token của caller | Spring Security xác thực, từ chối token hết hạn/sai issuer hoặc audience theo cấu hình | Không dùng JWT caller làm Vault token; phản hồi 401/403 đúng lớp |
| Vault token của workload | Vault auth method cấp token; Spring Vault `SessionManager` sử dụng/lifecycle theo implementation | Xử lý token expired/revoked, tái đăng nhập hoặc fail phù hợp |
| Secret tĩnh KV v2 | KV lưu dữ liệu theo version; phiên bản không tự làm key bên ngoài hết hiệu lực | Refresh property/cache/client khi rotate; thu hồi key cũ tại nhà phát hành |
| Database credential động | Secrets engine cấp lease TTL và có thể renew/revoke theo cấu hình | Tạo credential mới đúng hạn, thay datasource/pool và xử lý transaction |
| Transit key | Vault giữ key versions và xử lý encrypt/decrypt | Giới hạn quyền, quản lý ciphertext, quy hoạch rewrap/re-encrypt |
| PKI certificate | PKI phát hành certificate theo TTL/role | Cấp lại, nạp lại TLS context và kiểm tra expiry |

**`LifecycleAwareSessionManager` của Spring Vault không đồng nghĩa mọi secret đã được gia hạn.** Token dùng để gọi Vault có lifecycle riêng, trong khi credential do Database engine phát hành có lease riêng. `SecretLeaseContainer` có thể theo dõi những secret được cấu hình nhưng không tự bảo đảm HikariCP/HTTP client/TLS context đã nhận credential mới.

Nếu Spring Cloud Vault nạp password vào `Environment` lúc khởi động, thay password trong Vault **không tự thay các kết nối đang mở**. Phải có chiến lược refresh, restart/rebuild bean hoặc đổi pool phù hợp với nhu cầu uptime. Kiểm thử việc chuyển đổi có giá trị hơn chỉ kiểm tra rằng đọc giá trị mới thành công.

## 10. Các lỗi dễ nhầm giữa Spring Security và Vault

| Triệu chứng | Nguồn kiểm tra trước | Diễn giải |
|---|---|---|
| HTTP 401 trả về ngay tại REST API | Spring Security/JWT | Caller chưa được xác thực hoặc bearer token không hợp lệ |
| HTTP 403 từ REST API trước khi vào service | Spring Security authorization | Caller không có scope/role/quyền tài nguyên cần thiết |
| Vault trả 403 khi `kv.get` | Vault policy/role/token | Workload có thể login thành công nhưng thiếu `read` trên đúng KV v2 path |
| Vault trả 404 hoặc response null | Vault mount/key/version | Sai key logic, sai backend KV, secret không tồn tại/bị xóa |
| Ứng dụng không start vì thiếu property | Spring Cloud Vault/config bootstrap | Không đọc được Vault config, sai context, thiếu mount/policy hoặc fail-fast |
| Ứng dụng start được nhưng API key cũ | Cloud Vault property lifecycle hoặc cache của app | Chưa có refresh/rebuild client sau khi rotation |
| Java gọi Vault timeout | Mạng/TLS/client/Vault server | Hỏng DNS, network policy, CA, endpoint hoặc tình trạng Vault |
| PostgreSQL không chấp nhận credential | DB engine/lease/connection pool | Lease hết hạn hoặc pool còn credential cũ, không chỉ do Vault token |
| OAuth2 client credential hết hạn | OAuth2 client/provider và storage | Cần cơ chế lấy/cập nhật token phù hợp; chỉ lưu nó vào KV không tự gia hạn |

Không chuyển bừa Vault 403 thành REST 403 cho người dùng: Vault 403 mô tả quyền **workload với Vault**. Đối với caller có quyền trả tiền nhưng hạ tầng thiếu policy, REST API có thể trả lỗi dịch vụ phù hợp, đồng thời log nội bộ ghi loại lỗi an toàn để đội vận hành xử lý. Không để response trả ra token, Vault path nhạy cảm, header hoặc secret.

### 10.1. Quan sát đúng lớp

- **Spring Security:** tỷ lệ 401/403 ở API, kiểu authentication, method authorization failures; không log raw bearer token.
- **Spring Vault client:** số lần gọi Vault, độ trễ, lỗi token/renewal, lỗi 403/404/5xx, số lần fallback/refresh; không log `X-Vault-Token` hoặc secret payload.
- **Spring Cloud Vault:** lỗi Config Data import khi start, config contexts đã nạp theo metadata an toàn, số sự kiện refresh/rotation và lỗi binding.
- **Vault server:** auth/policy denials, audit devices, sức khỏe cluster/engines, lease/TTL theo thống kê phù hợp.
- **Hệ thống đích:** payment 401 và DB auth failures, chứng chỉ TLS gần hết hạn; Vault đọc secret thành công không chứng minh credential vẫn hợp lệ ở đó.

Một đường trace đủ hữu ích cần nêu được request nghiệp vụ đi qua điểm nào và lỗi ở đâu, nhưng phải **không** mang token/secret/private key/Transit plaintext hoặc giá trị config nhạy cảm vào span attributes, metrics labels hay log messages.

## 11. Bảo mật bootstrap và bảo vệ cấu hình

Một vấn đề căn bản là **ứng dụng lấy bí mật đầu tiên để đăng nhập Vault ở đâu**. Nếu Spring Cloud Vault phải có một root token hard-code để đọc cấu hình trong KV, hệ thống chỉ dời vị trí chứa bí mật. Giải pháp thường là **workload identity** qua Kubernetes auth, AppRole được cấp phát/bảo vệ đúng hoặc cloud IAM tùy hạ tầng; mỗi workload gắn role/policy riêng.

Một số nguyên tắc khi triển khai:

1. **Không commit credential** vào Git, image, tài liệu, test fixture, Dockerfile hay log pipeline. Dùng giá trị giả trong ví dụ.
2. **HTTPS chuẩn:** kiểm tra CA chain và hostname cho Vault, identity provider và service đích. Không tắt TLS verification để khắc phục lỗi cấu hình.
3. **Phân vùng môi trường:** `dev`, `test`, `prod` có role/policy và secret độc lập. Không để ứng dụng test đọc production secrets.
4. **Giới hạn phạm vi config:** Spring Cloud Vault chỉ nạp contexts cần thiết; Spring Vault chỉ gọi mount/path đã được thiết kế; không để caller cung cấp path tùy ý.
5. **Bảo vệ Spring Actuator:** cấu hình exposure và quyền truy cập cho `/actuator/env`, `/actuator/configprops`, heap dumps và các công cụ chẩn đoán, vì chúng có thể phản ánh cấu hình nhạy cảm.
6. **Bảo vệ bộ nhớ:** sau khi đọc KV, secret vẫn nằm trong heap Java; hạn chế nhân bản/cache lâu, không serialize object bí mật hoặc in `VaultResponse` ra log.
7. **Kế hoạch sự cố:** nếu Vault/config import thất bại, quyết định rõ service có thể start hay phải fail closed; nếu Transit bắt buộc, không lưu plaintext khi Vault mất kết nối.

Một token Vault có TTL ngắn vẫn nguy hiểm nếu được log hoặc cấp policy `path "*"` quá rộng. Kiểm soát danh tính, phạm vi quyền và vòng đời phải kết hợp.

## 12. Kiểm thử đúng tầng thay vì chỉ mock một lớp

Một bộ kiểm thử có ý nghĩa nên tách:

| Lớp kiểm thử | Phương tiện | Điều được chứng minh |
|---|---|---|
| Spring Security unit/web slice | Spring Security Test + MockMvc, JWT test | Request thiếu token/thiếu scope bị 401/403; method security áp dụng |
| Business logic | Mock `PaymentSecretReader` hoặc `VaultOperations` | Service chỉ gọi Vault sau khi qua authorization; không đưa key vào response |
| Spring Cloud Vault configuration | Spring context với nguồn config test, Vault test instance khi cần | Config Data import và binding từ đúng context; xử lý secret thiếu |
| Spring Vault integration | Vault server/container cô lập với KV v2, auth role và policy test | HTTP API path, token, KV version, lỗi 403/404 và TLS hoạt động |
| Secret lifecycle | Vault + Database/Transit/PKI test engine phù hợp | TTL/lease, renew/reissue, encrypt/decrypt policy, certificate rotation |
| End-to-end | REST request + Vault + mock provider/DB test | 401/403 của caller độc lập với quyền Vault; credential được sử dụng mà không rò vào output |

### Ví dụ các case phải có

1. **Caller chưa xác thực:** `POST /orders/42/payment` không có JWT → Spring Security từ chối trước khi đọc Vault.
2. **Caller thiếu scope:** JWT hợp lệ nhưng không có `orders.write` → không gọi secret reader.
3. **Caller có scope nhưng không sở hữu order:** business authorization từ chối, không dùng API key để trả tiền.
4. **Vault role đúng:** workload chỉ đọc được `secret/data/prod/orders/payment`; path service khác bị 403.
5. **KV v2 path:** `opsForKeyValue("secret", KV_2)` đọc đúng key; phiên bản xóa hoặc thiếu field được xử lý rõ.
6. **Cloud Vault property:** secret đã nạp đúng context, không bị expose qua actuator/log và ứng dụng phản ứng có kiểm soát khi Vault không sẵn sàng lúc bootstrap.
7. **Rotation:** đổi API key hoặc DB credential; kiểm tra client và connection pool thực sự dùng bản mới, không chỉ `Environment` thay giá trị.
8. **Token/lease:** thử token bị revoke và lease hết hạn độc lập; không có retry vô hạn hoặc fallback sang thông tin mặc định không an toàn.
9. **Transit/PKI nếu dùng:** encrypt thành công với quyền tối thiểu, decrypt bị từ chối khi không có quyền, certificate sắp hết hạn được thay trong TLS context.
10. **Quan sát:** trace/log/metric và response không chứa raw JWT, Vault token, API key, database password hoặc private key.

Mock không kiểm chứng Vault server policy. Một test chỉ xác nhận `@PreAuthorize` hoạt động cũng chưa cho biết client Spring Vault đăng nhập thành công. Cần kiểm tra các ranh giới thực trong môi trường test cô lập trước khi khẳng định tích hợp an toàn.

## 13. Bài tập tình huống

### Tình huống A — Thêm Spring Security nhưng vẫn lộ secret

Một API có `@PreAuthorize("isAuthenticated()")` rồi trả mọi field của KV key theo path do caller gửi. Vì sao nguy hiểm? Bất kỳ caller đã đăng nhập nào cũng có thể lợi dụng policy rộng của workload để đọc secret ngoài phạm vi nghiệp vụ. Cần thiết kế endpoint có mục đích hẹp, kiểm tra ownership, không nhận arbitrary Vault path và không trả secret ra client.

### Tình huống B — Spring Cloud Vault đã nạp secret mới nhưng DB vẫn lỗi

Vault có mật khẩu DB mới; `Environment` đã được refresh, nhưng HikariCP đang dùng connection/credential cũ. Đó là vấn đề **lifecycle của datasource**, cần replace/evict pool hoặc cơ chế kết nối chuyển giao hợp lệ. Việc property đã đổi không bảo đảm SQL connection tự đổi.

### Tình huống C — JWT người dùng hợp lệ, Vault trả 403

Người dùng có scope `orders.write`; `PaymentSecretReader` nhận Vault 403. Kiểm tra **role/policy của workload** và path KV v2 `secret/data/prod/orders/payment`, không đổi quyền của JWT người dùng để sửa sự cố. Đừng dùng root token để né lỗi.

### Tình huống D — Chỉ cần mã hóa, nhưng thêm Cloud Vault không giúp

Một service cần encrypt dữ liệu nhạy cảm theo từng request qua Transit. Spring Cloud Vault giúp nạp property, không thay lời gọi `transit/encrypt/<key>` theo input. Dùng Spring Vault trực tiếp với quyền `update` ở endpoint encrypt và bảo vệ plaintext trong request/response.

### Câu hỏi tự kiểm tra

1. `VaultTemplate`, `spring.config.import: vault://` và `SecurityFilterChain` giải quyết ba bài toán gì?
2. Tại sao Vault token của workload không nên được trả về cho caller có JWT hợp lệ?
3. Nếu Spring Security trả 403, khác gì với Vault server trả 403 khi `kv.get`?
4. Có thể dùng Spring Cloud Vault để cấp API key cho client HTTP không? Khi key đổi, những thành phần nào cần refresh?
5. Vì sao Transit encrypt theo từng request thường phù hợp với Spring Vault trực tiếp hơn với `@Value`?
6. Vault policy có tự bảo vệ được quyền của user A đối với order của user B không? Vì sao?
7. Làm sao kiểm thử độc lập authorization của REST API và authorization của Vault path?

## Tài liệu tham khảo chính thức

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Secret Lease Container](https://docs.spring.io/spring-vault/reference/vault/secret-lease-container.html)
- [Spring Cloud Vault — Reference Documentation](https://docs.spring.io/spring-cloud-vault/reference/)
- [Spring Cloud Vault — Config Data Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)

> **Ghi chú phiên bản:** Spring Security, Spring Vault, Spring Cloud Vault và Spring Boot có ma trận tương thích riêng; API và kiểu bootstrap có thể thay đổi theo phiên bản. Ví dụ dành cho hệ sinh thái Spring Boot hiện đại và minh họa nguyên tắc kiến trúc; khi thực hành cần chọn dependency tương thích, xác minh từng property/path và kiểm thử với Vault server thật trong môi trường test.
