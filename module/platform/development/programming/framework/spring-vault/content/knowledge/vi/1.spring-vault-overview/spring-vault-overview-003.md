# Quan hệ giữa ứng dụng Spring, thư viện client và máy chủ Vault

> **Chương:** Bản đồ Spring Vault  
> **Trọng tâm:** Hiểu chính xác phần nào chạy bên trong ứng dụng Java, phần nào do thư viện Spring Vault thực hiện và phần nào chỉ máy chủ HashiCorp Vault mới có quyền quyết định.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ được kiến trúc từ Spring `@Service`, `VaultOperations`/`VaultTemplate`, kết nối HTTP/TLS đến Vault server, auth method, policy và secrets engine.
2. Giải thích một lệnh Java được chuyển thành yêu cầu Vault API thế nào, trong đó **client gửi yêu cầu còn server quyết định có cho phép hay không**.
3. Phân biệt Vault authentication của **workload** với việc Spring Security xác thực **người dùng cuối** của ứng dụng.
4. Hiểu vai trò của `ClientAuthentication`, `SessionManager`, Vault token, TTL và lease mà không nhầm vòng đời của chúng.
5. Viết code Spring gọi KV v2 thông qua `VaultOperations` và đọc một ví dụ cấu hình client tối thiểu.
6. Khoanh vùng lỗi ở lớp ứng dụng, client, kết nối, máy chủ, policy hoặc secrets engine; thiết kế giám sát và kiểm thử tích hợp tương ứng.

## 1. Nhìn từ một tình huống thực tế

Giả sử `order-service` là ứng dụng Spring Boot chạy trên Kubernetes. Service cần:

- Lấy API key của cổng thanh toán từ KV v2.
- Xin credential PostgreSQL có TTL qua Database secrets engine.
- Yêu cầu Transit mã hóa một trường dữ liệu cần bảo vệ.
- Sau này có thể nhận chứng chỉ mTLS từ PKI.

Nếu tạo `VaultTemplate` trong Java, **ứng dụng vẫn không sở hữu Vault server**. Nó chỉ có một client biết cách gửi HTTP request. Vault nằm ở tiến trình/hệ thống khác, áp policy và thực hiện hoạt động trên secrets engines đã được cấu hình. Việc dùng chung hệ sinh thái Spring không làm ba phần trở thành một tiến trình.

### 1.1. Sơ đồ ranh giới triển khai

~~~mermaid
flowchart LR
    subgraph JVM["JVM: ứng dụng Spring Boot"]
        B["Business service<br/>@Service / @Component"]
        O["VaultOperations<br/>VaultTemplate"]
        S["ClientAuthentication<br/>SessionManager"]
        H["HTTP client / TLS<br/>VaultEndpoint"]
        B -->|"Gọi Java API"| O
        O --> S
        O --> H
    end

    W["Danh tính workload<br/>Kubernetes SA / IAM / AppRole"] --> S

    subgraph VAULT["Máy chủ / cụm HashiCorp Vault"]
        A["Auth methods<br/>xác thực workload"]
        P["Token + ACL policies<br/>kiểm tra quyền theo path"]
        E["Secrets engines<br/>KV / Database / Transit / PKI"]
        U["Audit devices"]
        A --> P
        P --> E
        P --> U
    end

    H <-->|"HTTPS: /v1/..."| A
    H <-->|"HTTPS: /v1/..."| P
    E -.->|"Database engine có thể quản lý credential"| D[("Database đích")]
    B -->|"Dùng credential đã nhận"| D
~~~

Mũi tên từ `order-service` đến Vault là **giao tiếp qua mạng**. Mũi tên giữa `@Service` và `VaultOperations` là **lời gọi hàm trong JVM**. Đây là khác biệt quyết định khi phân tích lỗi, tính sẵn sàng, độ trễ và bảo mật.

Không phải mọi engine đều kết nối tới database đích: KV lưu/đọc dữ liệu ở Vault; Transit thực hiện phép mật mã rồi trả kết quả; Database secrets engine có thể kết nối tới DB để tạo/thu hồi account; PKI cấp chứng chỉ theo cấu hình CA/role.

### 1.2. Trách nhiệm ở từng nơi

| Thành phần | Chạy ở đâu? | Chịu trách nhiệm | Không tự làm được |
|---|---|---|---|
| **Spring application** | JVM/process của service | Nghiệp vụ, chọn lúc cần secret, dùng và bảo vệ dữ liệu trong bộ nhớ, xử lý lỗi | Không tự quyết định Vault policy; không thể kéo dài credential đã bị hệ đích thu hồi |
| **Spring Vault client** | Thư viện bên trong JVM | Chuyển Java API thành HTTP request, ánh xạ dữ liệu, hỗ trợ auth/session/token và gọi engines | Không lưu Vault secret ở server; không tự tạo policy hay cấu hình mount |
| **HTTP client/TLS** | JVM và mạng | Kết nối đến Vault endpoint, timeout, TLS trust, gửi headers/payload | Không thay thế policy hoặc kiểm soát cách app dùng plaintext |
| **Vault server** | Cụm Vault riêng | Xác thực, cấp token, kiểm tra policy, thực thi engine, audit, lease/revoke | Không quản lý mọi bản sao secret trong heap/log/cache của ứng dụng |
| **Nền tảng triển khai** | Kubernetes/VM/cloud | Danh tính ban đầu, networking, CA trust, tài nguyên runtime và phân quyền hạ tầng | Không tự bảo đảm Java xử lý đúng TTL/rotation |
| **Hệ thống đích** | PostgreSQL, API đối tác... | Quyền thật trên tài nguyên cuối, hiệu lực credential, kết nối dữ liệu | Không nhất thiết biết Vault đã cấp token nào cho ứng dụng |

Khi cần tìm nguyên nhân sự cố, hãy hỏi: **lỗi xảy ra trước khi gửi HTTP, trong vận chuyển, khi Vault từ chối, hay sau khi secret đã đến ứng dụng?**

## 2. Spring Vault nằm ở lớp nào của ứng dụng?

### 2.1. Phần do Spring quản lý

Spring IoC container thường giữ các bean dùng chung. Business service chỉ cần inject interface `VaultOperations`. `VaultTemplate` là triển khai chính của interface này, có thể tái sử dụng qua nhiều request khi được cấu hình đúng.

~~~mermaid
flowchart TB
    C["Spring @Configuration<br/>đăng ký client beans"]
    V["VaultOperations interface"]
    T["VaultTemplate implementation"]
    M["SessionManager"]
    A["ClientAuthentication"]
    R["HTTP/TLS transport + VaultEndpoint"]
    F["PaymentSecretGateway @Service"]
    N["Các business services khác"]

    C --> T
    T -.implements.-> V
    F -->|"inject VaultOperations"| V
    N -->|"inject VaultOperations"| V
    T --> M
    M --> A
    T --> R
~~~

Các thành phần chính:

- `VaultOperations`: giao diện thao tác như `read`, `write`, `delete` và các API chuyên biệt cho từng backend. Viết business code qua interface giúp cô lập phụ thuộc và kiểm thử dễ hơn.
- `VaultTemplate`: triển khai đồng bộ, đóng vai trò cổng vào Spring Vault; tổ chức request và response với Vault. Với ứng dụng reactive, Spring Vault có API reactive riêng; không nên coi gọi đồng bộ `VaultTemplate` là thao tác không chặn luồng.
- `VaultEndpoint`: mô tả địa chỉ Vault server, ví dụ `https://vault.internal.example:8200`. Đây là URL hạ tầng, **không phải** path secret.
- `ClientAuthentication`: chiến lược thu thập/trao đổi thông tin đăng nhập để có Vault token, tùy phương thức xác thực.
- `SessionManager`: cung cấp token cho những lần gọi tiếp theo, quyết định việc tái sử dụng/gia hạn/thu hồi theo cách triển khai và loại token.
- HTTP client: thiết lập TLS, connect/read timeout, connection management và thực hiện các request. Các phiên bản Spring Vault mới có những abstraction transport khác nhau; mô hình client/server không đổi.

**Thêm dependency Spring Vault không đồng nghĩa đã có một Vault server hoặc một client bean hoạt động.** Bạn vẫn phải cấu hình endpoint, auth, TLS và beans bằng `AbstractVaultConfiguration`, cơ chế cấu hình tương thích hoặc starter phù hợp.

### 2.2. Ví dụ cấu hình bean Spring Vault

Ví dụ minh họa cấu trúc bean trong môi trường thử nghiệm. Token được cấp sẵn ở ngoài tiến trình và chỉ có quyền tối thiểu; **không đặt root token, token thật hoặc mật khẩu trong source code**.

~~~java
import java.net.URI;
import java.util.Objects;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class DemoVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
            URI.create("https://vault.internal.example:8200"));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = Objects.requireNonNull(
            System.getenv("VAULT_TOKEN"), "VAULT_TOKEN is required");
        return new TokenAuthentication(token);
    }
}
~~~

`AbstractVaultConfiguration` đăng ký các thành phần Spring Vault, bao gồm `VaultTemplate` và session manager phù hợp với cấu hình. Cấu hình trên minh họa một **token có sẵn** để dễ quan sát quan hệ lớp; production nên chọn auth theo workload, ví dụ Kubernetes/JWT/cloud identity hoặc AppRole theo mô hình tin cậy của hạ tầng.

Với Vault dùng CA nội bộ, phần kết nối HTTP/TLS còn cần truststore hoặc CA trust tương ứng. Không dùng `https` chỉ bằng tên URL rồi bỏ qua việc kiểm tra chứng chỉ, và không tắt hostname verification khi gặp lỗi TLS.

### 2.3. Chỗ business code thực sự dùng Vault

Giả sử người vận hành đã mount **KV v2** ở `secret/` và lưu key logic `prod/orders/payment` chứa field `api-key`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentSecretGateway {

    private final VaultKeyValueOperations kv;

    public PaymentSecretGateway(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String loadApiKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Payment secret is missing");
        }

        Object raw = response.getRequiredData().get("api-key");
        if (!(raw instanceof String apiKey) || apiKey.isBlank()) {
            throw new IllegalStateException("Payment key field is missing");
        }
        return apiKey;
    }
}
~~~

Phương thức `loadApiKey()` thuộc ứng dụng, nhưng lệnh `kv.get(...)` được Spring Vault triển khai thành request đến Vault. Application không cần tự gắn `X-Vault-Token` hay parse toàn bộ cấu trúc JSON của KV v2 trong business service.

Mã trên cố ý **không** cache hoặc log secret; chính sách cache/rotation phải chọn theo nhu cầu thực tế. Nếu service nhận API key rồi gửi tới cổng thanh toán, phần gửi đó là trách nhiệm của service và HTTP client gọi đối tác, không phải chức năng của Vault server.

## 3. Một lời gọi Java đi qua những lớp nào?

### 3.1. Luồng đọc KV v2 từ đầu đến cuối

~~~mermaid
sequenceDiagram
    autonumber
    participant B as PaymentSecretGateway
    participant T as VaultTemplate / KV operations
    participant S as SessionManager
    participant V as Vault API
    participant E as Policy + KV v2 engine

    B->>T: get("prod/orders/payment")
    T->>S: Lấy token cho phiên
    opt Chưa có token hợp lệ / cần login lại
        S->>V: Login qua auth method đã cấu hình
        V-->>S: Token + policy/TTL
    end
    S-->>T: Vault token
    T->>V: GET /v1/secret/data/prod/orders/payment
    Note right of T: Header X-Vault-Token qua HTTPS
    V->>E: Kiểm tra read trên đúng API path
    alt Có quyền và key tồn tại
        E-->>V: Dữ liệu + metadata KV
        V-->>T: HTTP 200 + JSON
        T-->>B: VaultResponse chứa data
    else Bị từ chối hoặc không tìm thấy
        E-->>V: Từ chối / không có resource
        V-->>T: HTTP 403 / 404
        T-->>B: Kết quả rỗng hoặc exception tương ứng
    end
~~~

Chi tiết quan trọng:

1. `get("prod/orders/payment")` là **key logic** đối với KV v2 API của Spring Vault.
2. `"secret"` là **mount path** do quản trị viên chọn, không mặc nhiên là mount có sẵn trong mọi Vault.
3. HTTP path đọc KV v2 là `/v1/secret/data/prod/orders/payment`; đoạn `data/` là quy ước của KV v2 API.
4. Policy kiểm tra `secret/data/prod/orders/payment` với capability `read`. **Path trong policy không chứa tiền tố HTTP `/v1/`.**
5. Response đi ngược qua Spring Vault để ứng dụng lấy field cần dùng. Không tự thêm `data/` vào đối số `get` của API KV cấp cao.

Ví dụ policy HCL tương ứng:

~~~hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Policy trên **không** tự cấp quyền liệt kê, sửa hoặc xóa key; cũng không cấp quyền ở `secret/data/prod/other-service`. Đối với KV v2, thao tác liệt kê keys thường dùng đường dẫn `secret/metadata/...` với capability `list`, là một quyền riêng.

### 3.2. HTTP response có thể khác dữ liệu business cần

Một response KV v2 ở mức HTTP API có dạng rút gọn:

~~~json
{
  "data": {
    "data": {
      "api-key": "demo-only-placeholder"
    },
    "metadata": {
      "version": 3
    }
  }
}
~~~

Ở mức API chuyên biệt `opsForKeyValue("secret", KV_2)`, Spring Vault xử lý cấu trúc KV v2 và trả về dữ liệu thuận tiện hơn cho người gọi. Nếu dùng `vault.read("secret/data/prod/orders/payment")` ở API tổng quát, bạn phải hiểu cách dữ liệu lồng trong response của Vault. Không được nhầm `metadata.version` với TTL của API key: version KV không làm key của nhà cung cấp tự hết hạn.

## 4. Xác thực workload và phân quyền là hai lần kiểm tra khác nhau

### 4.1. Ai đăng nhập Vault?

Trong ví dụ Kubernetes, `order-service` có ServiceAccount riêng. Khi đăng nhập, client có thể gửi bằng chứng danh tính workload đến auth method Kubernetes của Vault. Vault xác minh điều kiện theo cấu hình auth/role (ví dụ ServiceAccount và namespace được phép) rồi phát Vault token phù hợp.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes workload
    participant S as Spring Vault ClientAuthentication
    participant V as Vault auth/kubernetes
    participant P as Vault policy + KV

    K->>S: ServiceAccount JWT của pod
    S->>V: POST /v1/auth/kubernetes/login<br/>role + JWT
    V-->>S: Vault token + TTL + policies
    S->>P: GET /v1/secret/data/prod/orders/payment<br/>X-Vault-Token
    P-->>S: Cho phép / từ chối theo token
~~~

`role` ở auth method ánh xạ danh tính tới chính sách Vault; `policy` giới hạn hành động sau khi đăng nhập. Login thành công **không có nghĩa** token được đọc mọi key hay gọi mọi engine.

Không nên cấp root token cố định cho tất cả pod. Nếu một pod bị chiếm quyền, quyền token nên chỉ cho phép những thao tác tối thiểu của chính workload đó.

### 4.2. Xác thực người dùng Spring Security không thay thế Vault auth

Giả sử người dùng gửi JWT đến REST API của `order-service`:

~~~text
Người dùng -> Spring Security -> OrderController -> PaymentSecretGateway
                                         |
                                         v
                               Spring Vault client
                                         |
                                         v
                                    Vault server
~~~

JWT của người dùng cuối được ứng dụng kiểm tra để quyết định **người dùng được tạo đơn hàng hay không**. Vault token của workload cho biết **service được đọc secret nào**. Đây là hai quan hệ tin cậy độc lập:

- **Spring Security:** bảo vệ API nghiệp vụ trước người dùng/ứng dụng gọi tới.
- **Vault auth và policy:** bảo vệ Vault API trước workload hoặc danh tính được cấu hình hợp lệ.

Không tự động chuyển bearer token của người dùng cuối thành `X-Vault-Token`. Nếu nghiệp vụ thực sự cần phân quyền Vault theo từng người dùng, đó là một thiết kế ủy quyền khác và phải được phân tích riêng.

### 4.3. Token có vòng đời riêng

`ClientAuthentication` là chiến lược lấy token; `SessionManager` quyết định cung cấp token cho `VaultTemplate` như thế nào. Spring Vault có các triển khai thông dụng:

| Thành phần | Hành vi khái quát | Hệ quả thiết kế |
|---|---|---|
| `TokenAuthentication` | Dùng Vault token đã được cấp từ bên ngoài | Cần bảo vệ cách cấp token ban đầu và giới hạn quyền/TTL |
| Kubernetes/AppRole/JWT/IAM auth | Login bằng bằng chứng danh tính tương ứng | Phải cấu hình role/trust relationship và bảo đảm bằng chứng còn hợp lệ |
| `SimpleSessionManager` | Lấy token từ auth strategy, không quản lý refresh/revoke theo vòng đời | Không giả định có tự động gia hạn token |
| `LifecycleAwareSessionManager` | Có khả năng theo dõi và gia hạn token đủ điều kiện, xử lý vòng đời khi đóng phiên | Renewal phụ thuộc loại token, TTL và chính sách của Vault |

`AbstractVaultConfiguration` thường cấu hình `LifecycleAwareSessionManager`. Tuy nhiên, không phải token nào cũng gia hạn được và không phải token nào cũng được revoke theo cùng quy tắc khi client shutdown. Cần kiểm tra loại `VaultToken`/`LoginToken` và auth method trong phiên bản đang dùng.

Đặc biệt, **login token TTL** khác **lease TTL của secret động**. Một service có thể vẫn đăng nhập Vault thành công trong khi DB credential do engine cấp trước đó đã hết hạn. Vòng đời của connection pool và credential DB phải được xử lý riêng.

## 5. Spring Vault gọi các secrets engines theo cách nào?

Vault không cung cấp một endpoint có thể làm mọi thứ. Các loại engine được mount ở path do quản trị viên chọn và có mô hình thao tác khác nhau:

| Bài toán Java | API Spring Vault/kiểu thao tác | Ví dụ Vault HTTP API | Quyền thường cần |
|---|---|---|---|
| Đọc secret tĩnh KV v2 | `opsForKeyValue("secret", KV_2).get("prod/orders/payment")` | `GET /v1/secret/data/prod/orders/payment` | `read` |
| Nhận credential Database động | Đọc đường dẫn credential engine | `GET /v1/database/creds/orders-reader` | `read` |
| Mã hóa bằng Transit | Gọi API Transit encrypt qua client/operation tương ứng | `POST /v1/transit/encrypt/orders-pii` | `update` khi chỉ dùng key đã có |
| Giải mã qua Transit | Gọi API Transit decrypt, kiểm soát dữ liệu trả về | `POST /v1/transit/decrypt/orders-pii` | `update` |
| Cấp certificate PKI | Gọi PKI operations hoặc endpoint phù hợp | `POST /v1/pki/issue/orders-client` | `update` |
| Đăng nhập Kubernetes | `ClientAuthentication` theo Kubernetes | `POST /v1/auth/kubernetes/login` | Auth role cho phép danh tính tương ứng |

Các path `secret`, `database`, `transit` và `pki` là **mount ví dụ**. Nếu quản trị viên mount Transit ở `encryption/` thì endpoint thực tế bắt đầu từ `/v1/encryption/...`, và policy phải đổi theo. Tên mount, tên key và đường dẫn HTTP là thông tin khác nhau.

Với Transit, plaintext của request encrypt phải được biểu diễn theo format API (thường là Base64 của bytes gốc); Vault giữ key phía server và trả ciphertext cho ứng dụng lưu tại datastore của mình. PKI trả chứng chỉ và đôi khi cả private key tùy endpoint issue hay sign; ứng dụng/hạ tầng phải bảo vệ private key và cập nhật TLS context khi chứng chỉ thay đổi.

### 5.1. Hình dung ba kết quả trả về khác nhau

~~~mermaid
flowchart TB
    S["Spring business code"] --> O["VaultOperations / VaultTemplate"]
    O --> V["Vault server + policy"]
    V --> K["KV v2"]
    V --> D["Database"]
    V --> T["Transit"]
    V --> P["PKI"]
    K --> RK["Dữ liệu secret + version"]
    D --> RD["Username / password + lease TTL"]
    T --> RT["Ciphertext / chữ ký / kết quả crypto"]
    P --> RP["Certificate / chain / TTL<br/>có thể kèm private key"]
~~~

API đọc KV chỉ lấy dữ liệu đã lưu. Database engine có thể cấp mới credential có lease; Transit thực hiện phép mật mã mà không phải trả khóa ra ứng dụng; PKI phát hành chứng chỉ theo role. Vì vậy, wrapper `VaultResponse` hoặc API engine chuyên biệt cần được xử lý theo **ngữ nghĩa của engine**, không cố nhét tất cả kết quả vào một kiểu cấu hình bất biến.

## 6. Spring Vault và Spring Cloud Vault đứng ở đâu trong sơ đồ?

Hai tên gần nhau nhưng phục vụ cách tích hợp khác nhau:

| Câu hỏi | Spring Vault | Spring Cloud Vault |
|---|---|---|
| Mục tiêu chính | Gọi Vault API bằng code Java | Đưa cấu hình từ Vault vào hệ thống cấu hình của Spring |
| Cách dùng điển hình | Inject `VaultOperations`, gọi KV/Transit/PKI ở runtime | Cấu hình `spring.config.import: vault://` và nguồn `PropertySource` tương thích |
| Thời điểm đọc | Do service quyết định, có thể sau khi khởi động | Thường ở giai đoạn chuẩn bị cấu hình/khởi động; refresh tùy cơ chế cụ thể |
| Quyền cần có | Theo từng path/API được code gọi | Theo các config path mà integration đọc |
| Điểm cần kiểm soát | Lỗi runtime, timeout, TTL, callback, cache | Thứ tự và phạm vi property sources, fail-fast, refresh và rò rỉ qua endpoints cấu hình |

Ví dụ minh họa Spring Cloud Vault theo **Config Data API** của các phiên bản tương thích:

~~~yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-role
~~~

Các giá trị này chỉ minh họa hướng cấu hình; còn cần dependency, mount/context paths, Kubernetes auth được cấu hình phía Vault và CA trust hợp lệ. Không thể chỉ thêm `spring.config.import` rồi mong có sẵn role, policy, mount hoặc service account.

Spring Cloud Vault có thể sử dụng Spring Vault dưới lớp tích hợp của nó. **Đưa secret vào `Environment` không có nghĩa Vault server trở thành bean trong JVM**. Khi secret thay đổi, ứng dụng không mặc nhiên tự tái tạo datasource/HTTP client đang dùng credential cũ; cần cơ chế refresh/rotation thực tế.

## 7. Ranh giới kỹ thuật thường gây nhầm lẫn

### 7.1. Đường dẫn Java, URL API và policy path

~~~text
Vault server: https://vault.internal.example:8200
Mount:        secret/                      (KV v2)
Key logic:    prod/orders/payment
Spring call:  kv.get("prod/orders/payment")
HTTP API:     GET /v1/secret/data/prod/orders/payment
Policy path:  secret/data/prod/orders/payment
~~~

Không dùng URL bên ngoài làm key logic, không thêm `data/` hai lần, và không đặt tiền tố `/v1/` trong ACL policy. Với KV v2, metadata path khác data path; cấp quyền `list` ở metadata có thể làm lộ tên secret nên chỉ cấp nếu có nhu cầu.

### 7.2. Vault không phải database của business service

Một API `get` đến Vault có thể trả về API key để service gọi thanh toán, nhưng bản ghi đơn hàng vẫn thuộc PostgreSQL hoặc datastore nghiệp vụ. Không thiết kế “mỗi request người dùng thì ghi toàn bộ order dưới KV path” như một cơ sở dữ liệu ứng dụng.

Nếu cần Database dynamic credentials, Vault kết nối tới DB để phát hành credential theo cấu hình engine; service sau đó dùng credential ấy để kết nối DB. **Hai kết nối mạng này có mục tiêu khác nhau**, do các thành phần khác nhau quản lý.

### 7.3. Vault không tự chặn rò rỉ sau khi secret đã được trả

Vault kiểm soát API path và capability. Sau khi dữ liệu plaintext đã về JVM, các lớp application logging, exception handling, debug endpoint, thread dump, memory dump, cache và HTTP client downstream có thể làm dữ liệu lộ ra. Do đó:

- Không log `VaultResponse` nguyên bản hoặc header chứa Vault token.
- Không truyền secret vào lỗi trả cho người dùng cuối.
- Chỉ trao field cần thiết cho thành phần cần dùng, tránh chia sẻ một object chứa nhiều secret.
- Dùng TLS và kiểm tra certificate chain/hostname cả với Vault lẫn dịch vụ đích.
- Không đẩy secret vào metric labels, trace tags hoặc event có phạm vi đọc rộng.

### 7.4. Cluster/HA không triệt tiêu lỗi phía client

Một cụm Vault có thể sử dụng cơ chế HA, load balancer hoặc địa chỉ service ổn định, nhưng client vẫn cần timeout, retry có giới hạn và kiểm tra tình trạng kết nối. Thao tác ghi hoặc cấp phát credential không phải lúc nào cũng an toàn để retry mù quáng: cần hiểu tính idempotent của endpoint, khả năng request đã được xử lý nhưng response bị mất và hậu quả phát hành trùng.

Spring Vault giảm công việc xây dựng HTTP client; nó không tự thay kiến trúc failover, kế hoạch downtime hoặc chiến lược khôi phục của ứng dụng.

## 8. Phân tích lỗi theo đúng lớp

Khi `PaymentSecretGateway.loadApiKey()` lỗi, đừng mặc định tất cả đều là “Vault down”.

| Biểu hiện | Lớp cần kiểm tra trước | Ví dụ nguyên nhân | Hành động |
|---|---|---|---|
| Không có bean `VaultOperations` | Cấu hình Spring | Thiếu bean/config hoặc autoconfiguration phù hợp | Kiểm tra dependency, `@Configuration`, profile và điều kiện khởi tạo |
| Không resolve được hostname/không kết nối | Endpoint/mạng | Sai DNS, port, network policy, proxy | Kiểm tra đường đi từ pod tới Vault endpoint |
| TLS handshake thất bại | HTTP/TLS | CA không tin cậy, hostname khác cert, cert hết hạn | Sửa truststore/certificate; không bỏ kiểm tra TLS |
| Login thất bại | `ClientAuthentication`/Vault auth | Sai Kubernetes role, audience, token file hoặc trust config | Kiểm tra workload identity và cấu hình auth role |
| HTTP 403 khi đọc | Vault policy | Token có thật nhưng thiếu `read` trên đúng KV v2 path | So path/API/capability; không dùng root token để né lỗi |
| HTTP 404/secret trống | Secrets engine hoặc dữ liệu | Mount/key sai, KV v1/v2 nhầm, key chưa tạo/đã xóa | Kiểm tra đúng mount và key logic |
| Token hết hạn/revoke | Session/auth | TTL, policy thay đổi, không renew được | Xử lý đăng nhập lại hoặc fail hợp lệ; quan sát expiry |
| Database credential cũ không còn hợp lệ | Secret lease/DB pool | Lease hết hạn; pool chưa thay kết nối | Xin credential mới, kiểm soát pool rollover |
| Transit lỗi payload | Application/engine API | Không Base64 đúng, key sai, thiếu quyền encrypt | Kiểm tra request và policy mà không log plaintext |
| Lỗi timeout/5xx | Network/Vault/engine | Vault quá tải, mạng gián đoạn | Backoff + jitter, circuit breaker/giới hạn retry theo loại thao tác |

**Phân biệt 403, 404, timeout và lỗi TLS trong xử lý ứng dụng.** Ví dụ, 403 là dấu hiệu không được cấp phép; retry cùng token nhiều lần thường không làm policy thay đổi. Một 404 ở KV có thể chỉ ra key không tồn tại. Lỗi connect là sự cố hạ tầng, không nên chuyển thành chuỗi secret rỗng làm ứng dụng tiếp tục sai.

Đối với secret bắt buộc để xác thực hoặc mã hóa, ưu tiên quy tắc **fail closed**: khi không thể lấy secret/cấp quyền cần thiết, ứng dụng từ chối thao tác phụ thuộc thay vì dùng mật khẩu mặc định hoặc lưu dữ liệu dưới dạng plaintext.

## 9. Hệ quả vận hành: thời điểm đọc, cache và giám sát

### 9.1. Hai chiến lược đọc secret

**Đọc khi khởi động:** ứng dụng lấy credential một lần và xây dựng client/datasource. Cách này có thể giảm độ trễ runtime nhưng đòi hỏi chiến lược refresh khi secret bị rotate và thiết kế startup nếu Vault tạm thời không sẵn sàng.

**Đọc theo nhu cầu runtime:** ứng dụng có thể tiếp cận dữ liệu mới hơn và gọi Transit/PKI theo nghiệp vụ, nhưng thêm network hop, tải lên Vault và khả năng lỗi lúc xử lý request. Cần cache TTL phù hợp, timeout và backpressure/rate limit theo tình huống.

Không có chiến lược “mỗi request đều đọc Vault” hay “cache vĩnh viễn” phù hợp cho tất cả engine. KV tĩnh, dynamic database credential, Transit encrypt và PKI certificate đều có ràng buộc khác nhau.

### 9.2. Quan sát hai đầu kết nối

Ở **ứng dụng**, theo dõi tỷ lệ và độ trễ các request Vault, loại HTTP status, lỗi login/renewal, số lần miss cache và thời gian gần hết hạn credential/certificate. Không ghi payload chứa secret, token hoặc private key vào log/trace/metric.

Ở **Vault server**, vận hành audit devices và metrics phù hợp, theo dõi sức khỏe cluster, lỗi auth, lỗi policy, tình trạng secrets engines và giới hạn truy cập log. Bật audit phía Vault không bảo vệ được một `logger.info(apiKey)` bên Java.

Ở **hệ thống đích**, theo dõi lỗi xác thực database/đối tác hoặc TLS của service tiêu thụ secret. Vault có thể trả secret thành công nhưng credential tại hệ thống đích đã bị thu hồi hoặc thay đổi.

### 9.3. Ma trận trách nhiệm khi rotation

| Sự kiện | Vault server/engine | Spring Vault client | Ứng dụng |
|---|---|---|---|
| Token sắp hết TTL | Xác định renewability/giới hạn token | `SessionManager` có thể renew/login lại nếu cấu hình và token cho phép | Thiết kế hành vi khi refresh thất bại |
| API key đối tác đổi | KV giữ phiên bản mới nếu người vận hành cập nhật | Trả secret khi được yêu cầu đọc | Bỏ cache cũ, chuyển key, phối hợp thu hồi key tại đối tác |
| DB dynamic credential hết lease | Engine revoke/expire theo khả năng backend | Đọc credential mới hoặc quản lý lease khi có cấu hình phù hợp | Tạo lại connection pool/connection theo thời hạn |
| Transit key có phiên bản mới | Engine quản lý key versions | Gọi encrypt/decrypt/rewrap theo API | Quản lý ciphertext cũ, kiểm tra version được giải mã |
| Certificate PKI sắp hết hạn | PKI phát hành certificate theo role/TTL | Gọi PKI endpoint để lấy/ký certificate | Nạp cert mới vào TLS context và thay kết nối |

## 10. Kiểm thử tích hợp để xác nhận kiến trúc thực sự hoạt động

Unit test dùng mock `VaultOperations` giúp kiểm tra code chọn đúng key và xử lý response lỗi, nhưng **không chứng minh** cấu hình auth, HTTP path hay ACL policy ở Vault server. Để thử toàn bộ quan hệ client/server, cần môi trường Vault thật và cô lập dành cho test (ví dụ Vault container hoặc dev instance chỉ cho kiểm thử).

Một kế hoạch thử nghiệm có ý nghĩa:

1. **Bean wiring:** khởi động Spring context, xác nhận service inject được `VaultOperations` và dùng TLS client đã cấu hình.
2. **Kubernetes/AppRole login:** dùng identity/role thử nghiệm hợp lệ để nhận token giới hạn quyền; thử identity khác phải bị từ chối.
3. **KV v2 path:** mount KV v2 và tạo `prod/orders/payment`, xác nhận `kv.get(...)` đọc đúng field; sau đó thử sai mount và key thiếu.
4. **Policy âm tính:** tạo token chỉ đọc key orders, xác nhận đọc được orders và nhận `403` khi gọi path dành cho service khác.
5. **Token lifecycle:** thử token hết hạn hoặc bị revoke, xác minh ứng dụng/login/session có hành vi đúng; kiểm tra không dùng mãi token chết.
6. **Engine khác:** gọi Transit encrypt với quyền chỉ encrypt rồi thử decrypt phải bị từ chối; nếu dùng Database/PKI thì kiểm thử credential lease/certificate TTL.
7. **Sự cố mạng:** mô phỏng Vault timeout, mất kết nối, TLS sai hoặc 5xx; xác nhận retry có giới hạn, không rò payload, không fallback sang plaintext.
8. **Giám sát:** kiểm tra log/trace/metrics chỉ có metadata an toàn; audit tại Vault ghi nhận hoạt động theo cấu hình test.

Không cần chạy test trong bài lý thuyết này; đây là các trường hợp cần triển khai trong bài thực hành và pipeline thích hợp sau khi có Vault server và tài khoản test.

## 11. Bài tập đọc sơ đồ và tình huống chẩn đoán

### Bài tập 1 — Tách đúng trách nhiệm

Một lập trình viên viết `vault.opsForKeyValue("secret", KV_2).get("prod/orders/payment")`. Hãy xác định:

- Ai quyết định request được phép thực hiện?
- Ai biến lời gọi Java thành HTTP API?
- Ai bảo vệ secret sau khi nó đã nằm trong heap của `order-service`?
- Nếu không có KV mount `secret/`, việc thêm dependency Maven/Gradle có giải quyết được không?

**Gợi ý:** Vault server áp policy; Spring Vault client tạo request; application bảo vệ dữ liệu đã nhận; mount secrets engine phải được tạo/cấu hình trên Vault.

### Bài tập 2 — Token hợp lệ nhưng không đọc được

Một pod Kubernetes đăng nhập thành công và có Vault token. Lời gọi Java đọc KV v2 trả 403. Chính sách hiện tại là:

~~~hcl
path "secret/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Giả sử mount `secret/` là KV v2, lỗi có thể nằm ở đâu? Path đọc dữ liệu qua HTTP là `secret/data/prod/orders/payment`, nên policy đang thiếu đoạn `data/`. Việc login thành công chỉ xác nhận auth, không tự cấp đúng ACL path.

### Bài tập 3 — Secret đúng nhưng dịch vụ vẫn lỗi

Vault trả API key phiên bản mới thành công; cổng thanh toán vẫn trả 401 cho ứng dụng. Những lớp cần kiểm tra là: key mới đã có hiệu lực ở bên thứ ba chưa, client thanh toán còn cache key cũ không, application có đang gửi đúng header/endpoint không và có bước revoke/phát hành bị thiếu hay không. **Không quy mọi 401 từ hệ đích thành lỗi Vault auth**.

## 12. Tổng kết

Một ứng dụng Spring sử dụng `VaultTemplate` theo mô hình **client–server** rõ ràng: business code gọi API Java, Spring Vault xử lý giao tiếp và session, còn HashiCorp Vault xác thực workload, áp policy và thực hiện yêu cầu với secrets engine tương ứng. Địa chỉ server, mount path, key logic, HTTP API path và policy path là các khái niệm liên quan nhưng không thay thế cho nhau.

Điểm then chốt để ứng dụng Java truy cập Vault an toàn là **cả ba lớp phải đúng**:

1. **Ứng dụng:** chỉ xin dữ liệu/chức năng cần thiết, xử lý runtime error, TTL, cache/rotation và bảo vệ secret sau khi nhận.
2. **Spring Vault client:** cấu hình endpoint, auth, session, TLS và API theo engine/phiên bản.
3. **Vault server:** cấu hình auth method, role, policies, mounts, audit, lease và trạng thái dịch vụ.

### Câu hỏi tự kiểm tra

1. `VaultTemplate` chạy ở đâu và tại sao cài dependency không tự tạo Vault server?
2. `ClientAuthentication` và `SessionManager` khác vai trò nhau thế nào?
3. Với mount KV v2 `secret/` và key logic `prod/orders/payment`, hãy nêu Java call, HTTP path và policy path.
4. Vì sao JWT người dùng cuối trong Spring Security không mặc nhiên là Vault token?
5. 403 khi đọc KV v2 và lỗi SSL handshake chỉ về hai lớp khác nhau như thế nào?
6. Vì sao thành công khi đọc secret không bảo đảm kết nối tới database/API đối tác sẽ thành công?
7. Nếu service cần mã hóa dữ liệu qua Transit mà không cần giải mã, tại sao chỉ cấp quyền encrypt lại quan trọng?

## Tài liệu chính thức

- [Spring Vault — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Cloud Vault — Quick Start / Config Data](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html)
- [HashiCorp Vault — KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Lease, Renew and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)

> **Lưu ý phiên bản:** Spring Vault, Spring Cloud Vault và Vault server có nhiều nhánh phiên bản. Tên API, lựa chọn auth, quản lý lifecycle và cấu hình tự động có thể thay đổi; luôn đối chiếu dependency và documentation của chính phiên bản triển khai. Các path trong bài là ví dụ cho mount/role đã giả định.
