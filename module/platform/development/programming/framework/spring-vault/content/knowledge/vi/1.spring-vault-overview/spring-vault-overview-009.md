# Lộ trình từ đọc secret đến quản lý vòng đời trong ứng dụng

> **Chương:** Bản đồ Spring Vault  
> **Phạm vi:** Xây dựng một lộ trình thực hành Spring Vault cho ứng dụng Java, bắt đầu từ đọc KV v2 bằng `VaultTemplate`/`VaultOperations`, rồi từng bước bổ sung xác thực theo workload, phân quyền, xử lý lỗi, rotation, quản lý token và lease, Transit, PKI, giám sát và kiểm thử tích hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chia việc tích hợp HashiCorp Vault vào ứng dụng Spring thành **những giai đoạn có tiêu chí hoàn thành**, thay vì dừng ở lệnh `vault.read(...)` chạy được.
2. Thiết kế hợp đồng giữa ứng dụng và Vault về auth method, mount, policy path, schema của secret, TTL và chủ sở hữu rotation.
3. Viết adapter Java đọc KV v2 qua `VaultOperations`, xử lý thiếu secret/field và không vô tình trả dữ liệu nhạy cảm cho caller.
4. Phân biệt vòng đời **Vault login token**, **secret tĩnh trong KV** và **credential động có lease**.
5. Lên kế hoạch chuyển đổi API key, database credentials và chứng chỉ mà không phụ thuộc vào giả định “secret đổi trong Vault thì bean tự cập nhật”.
6. Mở rộng đúng mục đích sang Transit encryption, PKI, quan sát và kiểm thử tích hợp với Vault thật trong môi trường cô lập.

## 1. Từ “đọc được secret” đến “quản lý được secret”

Giả sử `orders-service` của một hệ thống bán hàng cần API key để gọi cổng thanh toán, username/password PostgreSQL và chức năng mã hóa một trường thông tin khách hàng. Nhóm phát triển đã có code đọc KV:

~~~java
VaultResponse response = vault
    .opsForKeyValue("secret", KeyValueBackend.KV_2)
    .get("prod/orders/payment");
~~~

Đây mới là **mốc kỹ thuật ban đầu**. Một ứng dụng chạy ổn định trong production còn phải trả lời:

- Pod/VM đăng nhập Vault bằng **danh tính nào**, và token được cấp những quyền gì?
- Giá trị `api-key` được phát hành bởi **ai**, thay mới khi nào, có thể dùng song song key cũ và mới không?
- Nếu Vault trả `403`, `404` hoặc timeout, thao tác thanh toán thất bại như thế nào?
- Nếu token hết hạn nhưng API key đã được cache, điều gì còn hợp lệ?
- Nếu Database secrets engine cấp username/password có lease 15 phút, **connection pool** chuyển sang credential mới ra sao?
- Khi mã hóa qua Transit, nếu Vault tạm thời không sẵn sàng thì ứng dụng có được phép lưu plaintext không?
- Ai nhận cảnh báo, làm sao kiểm toán việc truy cập mà không ghi secret vào log?

Mục tiêu của lộ trình là biến một **lời gọi API thành cơ chế sử dụng secret có kiểm soát**, gồm phát hành, phân phối, sử dụng, làm mới, thu hồi và kiểm chứng.

### 1.1. Bản đồ tiến độ

| Giai đoạn | Câu hỏi cần giải quyết | Kết quả phải có |
|---|---|---|
| **0. Phân loại** | Cần loại secret nào và ai sở hữu? | Danh mục secret, mức nhạy cảm, nguồn phát hành, người chịu trách nhiệm |
| **1. Thiết lập tin cậy** | Workload đăng nhập và được cấp quyền thế nào? | Auth role, policy tối thiểu, TLS, mount và keyspace đã được kiểm tra |
| **2. Đọc KV đúng cách** | Java gọi Vault và xử lý response ra sao? | Adapter `VaultOperations` đọc đúng key logic/field, không lộ secret |
| **3. Vận hành khi lỗi** | Ứng dụng ứng xử ra sao khi Vault không phản hồi? | Timeout, phân loại lỗi, retry hữu hạn, hành vi fail closed, cache policy |
| **4. Rotation secret tĩnh** | Key mới được phát hành và key cũ bị thu hồi thế nào? | Quy trình chuyển đổi, refresh client, xác nhận downstream, rollback |
| **5. Token và lease** | Secret có TTL được gia hạn hoặc cấp lại thế nào? | Session lifecycle, lease handling, rollover datasource/connection pool |
| **6. Mở rộng chức năng** | Cần encrypt hoặc certificate động không? | Transit/PKI theo quyền tối thiểu và vòng đời phù hợp |
| **7. Quan sát, kiểm thử** | Chứng minh hệ thống an toàn qua thay đổi/sự cố thế nào? | Metrics, audit, integration tests, runbook và tiêu chí release |

Các giai đoạn có thể triển khai dần. Không phải ứng dụng nào cũng dùng Database dynamic secrets, Transit hoặc PKI. Nhưng nếu đã phụ thuộc vào chúng thì không thể bỏ qua vòng đời, xử lý lỗi và kiểm thử tương ứng.

~~~mermaid
flowchart LR
    A["0. Phân loại<br/>secret"] --> B["1. Workload identity<br/>policy + TLS"]
    B --> C["2. Đọc KV v2<br/>bằng Java"]
    C --> D["3. Lỗi, cache,<br/>timeout"]
    D --> E["4. Rotation<br/>secret tĩnh"]
    E --> F["5. Token và<br/>lease động"]
    F --> G["6. Transit / PKI<br/>nếu cần"]
    G --> H["7. Audit, giám sát,<br/>integration tests"]
    H -.->|"Cải tiến khi vận hành"| A
~~~

## 2. Giai đoạn 0 — Phân loại dữ liệu và xác định chủ sở hữu

Trước khi thêm dependency, tạo một danh sách **những thứ ứng dụng thật sự cần**. Ví dụ:

| Dữ liệu/chức năng | Nguồn phát hành | Hướng tích hợp Vault | Ai phải xử lý khi đổi/hết hạn? |
|---|---|---|---|
| Payment API key | Nhà cung cấp thanh toán | KV v2 giữ secret tĩnh | Chủ sở hữu tích hợp phát/revoke key; App Dev refresh HTTP client |
| PostgreSQL username/password | Database engine cấp theo role | Dynamic secret có lease | Vault Ops/DBA quản lý role; App Dev cập nhật datasource/pool |
| Vault login token | Vault auth method theo danh tính workload | `ClientAuthentication`/`SessionManager` | Platform/Vault Ops quản lý role/TTL; client xử lý renew/re-login |
| Mã hóa thông tin khách hàng | Transit key của Vault | Gọi `transit/encrypt/...` | Security/Vault Ops quản lý key; App Dev giữ ciphertext, xử lý lỗi |
| Chứng chỉ client mTLS | PKI/CA | PKI issue/sign theo role | Vault Ops quản lý CA/role; App Dev thay TLS context và kết nối |
| Timeout, endpoint công khai | Cấu hình ứng dụng | Spring config thông thường | App Dev/Platform, không nhất thiết là secret |

Những điều cần chốt cho mỗi secret:

1. **Tính bí mật:** ai có thể đọc plaintext, ai chỉ được yêu cầu một phép toán như encrypt?
2. **Phạm vi:** chỉ một service/môi trường hay có nhu cầu chia sẻ? Không cho nhiều workload dùng chung quyền chỉ vì cùng nằm trong cluster.
3. **Hệ thống gốc:** Vault có tự phát hành/thu hồi credential không, hay chỉ giữ bản sao một key của đối tác?
4. **Thời gian:** credential có TTL, renewable, max TTL không? Đối với key tĩnh, ai quyết định thời điểm rotation?
5. **Hậu quả hết hạn:** thanh toán bị từ chối, DB pool không tạo được connection hay TLS handshake thất bại?
6. **Chính sách lỗi:** khi secret bắt buộc không có, ứng dụng dừng khởi động, từ chối request hay chuyển sang chế độ hạn chế được phê duyệt?

Đừng trộn **cấu hình không nhạy cảm** với bí mật chỉ để biến Vault thành kho chứa mọi property. URL, retry count hay feature flag thông thường có thể nằm trong cấu hình chuẩn. Một URL có nhúng password, private key hoặc bearer token lại phải được xử lý như secret.

## 3. Giai đoạn 1 — Thiết lập ranh giới tin cậy trước khi gọi API

Ba thành phần phối hợp:

- **Workload/platform:** cung cấp bằng chứng danh tính ban đầu, ví dụ ServiceAccount JWT trên Kubernetes hoặc cơ chế IAM phù hợp.
- **Vault server:** bật auth method, cấu hình role/policy, secrets engines, audit và phát token có giới hạn.
- **Spring Vault client:** đăng nhập theo chiến lược phù hợp, gửi yêu cầu HTTPS cùng Vault token tới path cần thiết.

~~~mermaid
sequenceDiagram
    autonumber
    participant K as Kubernetes / Workload
    participant J as Spring Vault Client
    participant V as Vault Auth + ACL
    participant E as KV / Database Engine

    K-->>J: Bằng chứng workload identity
    J->>V: Login theo auth method
    V-->>J: Vault token + policies + TTL
    J->>V: Request /v1/... với Vault token
    V->>V: Kiểm tra path + capability
    alt Được phép
        V->>E: Thực hiện thao tác
        E-->>J: Secret/kết quả hoặc lease metadata
    else Không đủ quyền
        V-->>J: 403 permission denied
    end
~~~

### 3.1. Thiết kế mount, key logic và policy path

Giả sử Vault Ops đã bật KV v2 tại mount `secret/`:

~~~text
Vault endpoint: https://vault.internal.example:8200
Auth method:    auth/kubernetes
Vault role:     orders-role
KV v2 mount:    secret/
Key logic:      prod/orders/payment
Field:          api-key
Java API:       get("prod/orders/payment")
HTTP API:       GET /v1/secret/data/prod/orders/payment
ACL policy:     secret/data/prod/orders/payment
~~~

Policy HCL tối thiểu cho tác vụ này:

~~~hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Đối với **KV v2**, path đọc dữ liệu có đoạn `data/`. Path policy không chứa prefix HTTP `/v1/`. Quyền `list` dùng endpoint `metadata/` riêng và chỉ nên cấp khi ứng dụng cần liệt kê key; việc biết sẵn key rồi gọi `get` không đòi hỏi cấp quyền liệt kê.

Việc đặt tên `secret` chỉ là ví dụ; trên Vault khác, KV v2 có thể mount ở `kv` hoặc một path khác. Hãy kiểm tra loại engine và path thực tế, không suy từ ví dụ hoặc tên folder mã nguồn.

### 3.2. Bootstrap không nên tạo thêm một “secret gốc” trong Git

Đặt một root Vault token vào `application.yml` làm ứng dụng đọc được secret, nhưng cũng tạo ra một secret quyền rộng, khó thu hồi và dễ lộ. Chọn **workload identity** phù hợp nền tảng và ràng buộc role với đúng danh tính/môi trường:

~~~yaml
# Bản mô tả hợp đồng triển khai, không phải cấu hình tự động chạy Vault
workload: orders-service
environment: prod
serviceAccount: orders-runtime
authMethod: kubernetes
vaultRole: orders-role
kvMount: secret
allowedKey: prod/orders/payment
~~~

Khi dùng `AppRole` cho máy chủ/batch, `SecretId` vẫn cần được phân phối, bảo vệ và giới hạn TTL/số lượt dùng theo mô hình tin cậy. Với cloud IAM/JWT, phải kiểm tra issuer/audience/role binding thích hợp. Không có auth method chung phù hợp tuyệt đối cho mọi workload.

### 3.3. Kết nối HTTPS phải được xác minh

Spring Vault giao tiếp với Vault server qua HTTP client, nhưng môi trường thực nên dùng **HTTPS, xác minh CA chain và hostname**. Nếu Vault dùng private CA, cấu hình truststore/CA trust cho Java thay vì tắt TLS verification. Xác định connect/read timeouts và đường mạng từ pod tới Vault trước khi cho phép production traffic.

**Tiêu chí hoàn thành giai đoạn 1:** workload đúng role đăng nhập và đọc đúng key; workload khác bị từ chối; TLS được kiểm tra; không có root token hoặc secret thật trong repository/image/log.

## 4. Giai đoạn 2 — Viết adapter đọc secret bằng Spring Vault

Trong Spring, business service nên phụ thuộc một adapter có trách nhiệm rõ ràng, thay vì ghép Vault path rải rác ở nhiều controller. Với `VaultOperations` được inject và cấu hình bằng cơ chế phù hợp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentKeyProvider {

    private final VaultKeyValueOperations kv;

    public PaymentKeyProvider(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
            "secret", KeyValueBackend.KV_2);
    }

    public String requiredPaymentKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException(
                "Required payment secret is absent");
        }

        Object field = response.getRequiredData().get("api-key");
        if (!(field instanceof String key) || key.isBlank()) {
            throw new IllegalStateException(
                "Required payment key field is absent");
        }
        return key;
    }
}
~~~

Đây là đoạn code **đọc secret** theo API KV v2, không tự tạo `VaultOperations` bean hoặc auth role. Người vận hành phải tạo mount, key, policy; cấu hình client phải thiết lập endpoint, TLS và authentication. Khi gọi `opsForKeyValue("secret", KV_2)`, phần `get(...)` nhận **key logic**, không được thêm `data/` thủ công.

### 4.1. Không trả secret từ controller

Ứng dụng cần API key để gọi hệ thống đích; caller chỉ cần kết quả thanh toán, không được nhận key:

~~~java
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final PaymentKeyProvider keys;
    private final PaymentGatewayClient paymentGateway;

    public PaymentService(
            PaymentKeyProvider keys,
            PaymentGatewayClient paymentGateway) {
        this.keys = keys;
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult charge(String orderId) {
        String apiKey = keys.requiredPaymentKey();
        return paymentGateway.charge(orderId, apiKey);
    }
}

// Interfaces minh họa ranh giới với nhà cung cấp thanh toán.
interface PaymentGatewayClient {
    PaymentResult charge(String orderId, String apiKey);
}

record PaymentResult(String providerReference, boolean success) { }
~~~

`PaymentService` chỉ chuyển secret tới adapter kết nối đối tác. Caller REST, audit log và kết quả nghiệp vụ không chứa `apiKey`. Ở ứng dụng dùng Spring Security, controller/service còn phải kiểm tra quyền người dùng và quyền trên `orderId`; Vault policy của workload không tự áp dụng authorization theo người dùng cuối.

### 4.2. Khi nào sử dụng `PropertySource` thay vì gọi API?

Nếu secret chỉ cần lúc tạo bean (ví dụ một client secret cấu hình), Spring Cloud Vault có thể nạp giá trị vào `Environment` qua Config Data import:

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
~~~

Ví dụ yêu cầu **Spring Cloud Vault dependency tương thích với Spring Boot**, context/mount/role được cấu hình đầy đủ và TLS trust chuẩn. Cơ chế property source tiện cho bootstrap, nhưng value đã bind vào bean hoặc datasource không tự đổi khi Vault có phiên bản KV mới. Với Transit hoặc PKI operation tùy input lúc chạy, API trực tiếp thường rõ ràng hơn `@Value`.

**Tiêu chí hoàn thành giai đoạn 2:** đọc đúng dữ liệu giả qua KV v2, xử lý key/field thiếu, dùng secret nội bộ qua adapter, không log hoặc serialize plaintext; business code không hard-code endpoint/token/path ở nhiều nơi.

## 5. Giai đoạn 3 — Chuẩn bị ứng dụng cho lỗi mạng và thay đổi dữ liệu

Khi gọi Vault qua mạng, mọi request có thể thất bại. Chương trình chạy được trong điều kiện thuận lợi chưa phải đã chịu lỗi đúng.

| Tín hiệu | Ý nghĩa cần kiểm tra | Phản ứng đề xuất |
|---|---|---|
| **403 Vault** | Token/role/policy thiếu quyền, hoặc sai path KV v2 | Kiểm tra quyền tối thiểu và API path; không thử lại bằng root token |
| **404/response rỗng** | Key/mount/version không có hoặc đã xóa | Phân biệt optional và required secret; không thay bằng credential mặc định |
| **Token hết hạn/revoked** | Session/auth strategy hoặc TTL token | Gia hạn/login lại nếu được phép; giới hạn retry |
| **TLS handshake lỗi** | CA trust, hostname, certificate hoặc clock | Sửa trust/certificate; không tắt kiểm tra TLS |
| **Timeout/DNS/connect** | Vault hoặc mạng chưa truy cập được | Timeout hữu hạn, retry/backoff có giới hạn theo thao tác |
| **429/5xx** | Rate limit, Vault/engine quá tải hoặc sự cố | Giảm tải, backoff + jitter, telemetry và fallback theo chính sách |
| **Credential bên thứ ba trả 401** | API key đã revoke, gửi sai header hoặc cache cũ | Kiểm tra ở hệ thống đích; không mặc định là lỗi Vault auth |

### 5.1. Fail closed cho secret bắt buộc

Nếu không đọc được khóa bắt buộc để xác thực cổng thanh toán, request thanh toán nên thất bại có kiểm soát. Nếu Transit encrypt không sẵn sàng nhưng dữ liệu bắt buộc phải mã hóa, **không** lưu plaintext vào database như một phương án dự phòng ngẫu nhiên.

Phân biệt lỗi của **người gọi REST** với lỗi của **workload gọi Vault**. Vault trả `403` không nhất thiết có nghĩa người dùng cuối vi phạm quyền; ứng dụng cần ánh xạ sang lỗi dịch vụ phù hợp và ghi lại nguyên nhân trong telemetry nội bộ mà không lộ token/path nhạy cảm.

### 5.2. Retry chỉ khi hiểu thao tác

Đọc một KV key theo HTTP GET thường có thể retry có giới hạn khi lỗi mạng tạm thời. Nhưng thao tác cấp credential động, phát certificate hoặc ghi secret có thể tạo **side effect** ngay cả khi client chưa nhận response. Nếu retry sau timeout, có thể phát hành nhiều credential hoặc tạo nhiều version KV ngoài ý muốn.

Thiết lập connect/read timeout, giới hạn số lần retry và backoff có jitter, kết hợp khả năng quan sát. Không đặt một vòng `while(true)` bên ngoài `VaultTemplate` cho mọi lỗi.

### 5.3. Cache ở đâu, trong bao lâu?

| Chiến lược | Lợi ích | Rủi ro cần cân nhắc |
|---|---|---|
| Lấy KV key theo từng request | Nhận thay đổi nhanh hơn, ít quản lý cache | Thêm network hop, tải Vault và phụ thuộc runtime |
| Cache secret tĩnh theo TTL ngắn | Giảm latency và số request tới Vault | Rotation/revoke có thể chậm đến khi TTL hết |
| Refresh chủ động qua deploy/sự kiện | Có thời điểm chuyển key rõ ràng | Phải quản lý nhiều instance và failure giữa chừng |
| Cache vô hạn | Ít request Vault | Dễ dùng credential bị revoke, rotation không có hiệu lực |
| Cache credential DB động vượt lease | Có vẻ tiện nhưng **không hợp lệ** | Account hết TTL, kết nối mới thất bại |

Cache key tĩnh là một **quyết định bảo mật và vận hành**, không chỉ tối ưu hiệu năng. Kể cả khi Vault tạm thời không sẵn sàng, giá trị cache cũ chỉ được dùng nếu vẫn được chấp nhận theo chính sách và nhà phát hành. Không cache vào hệ thống chia sẻ có quyền đọc rộng hoặc log giá trị trong key cache.

**Tiêu chí hoàn thành giai đoạn 3:** đã mô phỏng `403`, `404`, timeout và TLS lỗi; ứng dụng xử lý khác nhau, retry hữu hạn, không lộ secret và không fallback trái chính sách.

## 6. Giai đoạn 4 — Rotation secret tĩnh mà không đứt gãy nghiệp vụ

KV v2 hỗ trợ version history, nhưng **ghi version mới không tự thu hồi key cũ ở nhà phát hành**. Chẳng hạn cổng thanh toán có hai API key:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Secret Owner / Payment Provider
    participant V as Vault KV v2
    participant A as orders-service instances
    participant P as Payment API

    O->>P: Phát hành key B (key A còn hiệu lực)
    P-->>O: Key B
    O->>V: Ghi version KV mới chứa B
    V-->>O: Version N+1
    O->>A: Kích hoạt refresh/redeploy có kiểm soát
    A->>V: Đọc key B
    A->>P: Gửi request bằng key B
    P-->>A: Chấp nhận
    O->>P: Revoke key A sau khi toàn bộ instances đã đổi
    P-->>O: Key A hết hiệu lực
~~~

Quy trình:

1. **Phát hành giá trị mới tại hệ thống nguồn** với quyền tối thiểu; xác định nhà cung cấp có hỗ trợ hai key hoạt động song song không.
2. **Cập nhật KV v2** đúng mount/key, có kiểm soát quyền ghi và metadata; không đưa key vào Git hoặc ticket.
3. **Đưa key mới vào runtime:** invalidate cache, refresh adapter hoặc tái tạo HTTP client theo thiết kế; không chỉ nhìn giá trị trong Vault rồi cho rằng tất cả pod đã đổi.
4. **Xác minh ở downstream:** quan sát kết quả xác thực API, đối soát instance còn dùng key A và số lần lỗi 401/403 từ nhà cung cấp.
5. **Thu hồi key A ở hệ thống nguồn** sau khi chuyển đổi thành công; quản trị lịch sử KV, backup và những bản sao khác theo retention policy.
6. **Ghi nhận bằng chứng:** thời điểm chuyển, chủ sở hữu, kết quả, không ghi giá trị secret.

Nếu nhà cung cấp chỉ hỗ trợ một key hoạt động tại một thời điểm, có thể cần cửa sổ chuyển đổi với downtime hoặc chiến lược riêng. Không được viết một lộ trình “zero downtime” chung khi điều kiện nhà cung cấp không cho phép.

### 6.1. Điểm kiểm soát rollback

Rollback ở đây có nghĩa là **khôi phục quyền truy cập hợp lệ** theo kế hoạch, chứ không đơn thuần đọc lại version KV cũ. Nếu key A đã bị revoke tại đối tác, đọc version KV cũ sẽ chỉ mang lại một chuỗi vô hiệu. Có thể phải **phát hành key C**, cập nhật KV và chuyển client tới C.

**Tiêu chí hoàn thành giai đoạn 4:** một cuộc rotation thử nghiệm đổi key trong Vault lẫn runtime, tất cả instance dùng key mới và key cũ bị vô hiệu hóa theo chính sách tại nhà phát hành.

## 7. Giai đoạn 5A — Quản lý Vault login token đúng vòng đời

Đừng gộp token đăng nhập Vault và secret nghiệp vụ thành một giá trị:

| Đối tượng | Dùng để làm gì? | Ai quản lý thời hạn? |
|---|---|---|
| **Vault login token** | Cho `VaultTemplate` gửi API requests tới Vault | Vault auth/token subsystem; client session xử lý renewal/login lại |
| **API key tĩnh trong KV** | Xác thực với cổng thanh toán | Nhà cung cấp API và quy trình rotation của ứng dụng |
| **Database credential động** | Đăng nhập PostgreSQL với quyền SQL theo role | Database secrets engine và lease; application pool phải cập nhật |
| **Transit key** | Mã hóa/giải mã/ký trong Vault | Transit key lifecycle/phân quyền, không phải lease DB theo từng ciphertext |
| **PKI certificate** | Xác thực TLS theo thời hạn X.509 | CA/PKI issuance/expiry/revocation; app reload TLS |

Trong Spring Vault:

- `ClientAuthentication` xác định cách lấy token (Kubernetes, AppRole, cloud/JWT hoặc token đã có tùy thiết lập).
- `SessionManager` cung cấp token hợp lệ cho những lần gọi Vault theo implementation.
- `SimpleSessionManager` không tự lên lịch renewal/revocation theo vòng đời.
- `LifecycleAwareSessionManager` có thể hỗ trợ gia hạn token đủ điều kiện và quản lý login token theo vòng đời. Thành công còn tùy auth method, TTL tối đa, renewability và cấu hình server.

Ngay cả khi một token renewable, nó **không được bảo đảm gia hạn vô thời hạn**. Token có thể bị thu hồi trước TTL vì thay đổi quyền/sự cố; client cần phản ứng theo chính sách và không giả định mọi lỗi 403 có thể sửa bằng cách login lại.

### 7.1. Kiểm thử token độc lập

Để kiểm tra đúng, dùng role/token thử nghiệm với TTL ngắn hợp lý. Xác minh:

1. Token có policy đúng và đọc được key cần thiết.
2. Token gần hết TTL được renew nếu hợp lệ, hoặc client xác thực lại khi không thể renew và vẫn có bằng chứng danh tính workload hợp lệ.
3. Token bị revoke khiến yêu cầu thất bại hoặc client tái xác thực theo thiết kế; không có vòng lặp vô hạn.
4. Token không bị ghi vào log, trace, exception, metrics, heap dump được phép truy cập rộng hoặc REST response.

**Tiêu chí hoàn thành giai đoạn 5A:** đã hiểu rõ token từ đâu đến, TTL và renewability do đâu quyết định, ai xử lý revoked/expired và không có token quyền rộng được nhúng vào source.

## 8. Giai đoạn 5B — Quản lý secret động, lease và connection pool

Với Database secrets engine, Vault có thể phát hành credential theo role, ví dụ:

~~~text
Vault mount:     database/
Role:            orders-reader
HTTP request:    GET /v1/database/creds/orders-reader
Policy path:     database/creds/orders-reader
Response:        username, password, lease_id, lease_duration, renewable
~~~

Policy ở Vault:

~~~hcl
path "database/creds/orders-reader" {
  capabilities = ["read"]
}
~~~

Role phía Database engine còn phải có kết nối backend và lệnh SQL/phạm vi quyền đúng. Vault policy quyết định **ai được xin credential**, trong khi database role và SQL grants quyết định **credential đó làm được gì trong DB**.

### 8.1. Một request cấp credential có dữ liệu vòng đời

Ví dụ response rút gọn, hoàn toàn là dữ liệu giả:

~~~json
{
  "lease_id": "database/creds/orders-reader/demo-lease",
  "lease_duration": 900,
  "renewable": true,
  "data": {
    "username": "v_orders_reader_demo",
    "password": "demo-only-not-valid"
  }
}
~~~

Ở đây `lease_duration` là 900 giây để minh họa. `renewable: true` không có nghĩa có thể gia hạn mãi: còn phụ thuộc `max_ttl`, lease state, role và backend. Một token Vault có thể còn hiệu lực trong khi credential DB đã hết hạn; **renew token không tự renew DB lease**.

### 8.2. Phần client có thể hỗ trợ

Spring Vault có `SecretLeaseContainer` để quản lý các secret có lease/rotation **đã được đăng ký** và phát thông tin/sự kiện liên quan theo cấu hình. Không nên suy luận rằng mọi `vault.read("database/creds/...")` đều được theo dõi tự động. Ứng dụng phải liên kết việc credential thay đổi với thành phần sử dụng, chẳng hạn `DataSource`/HikariCP.

Một chiến lược ứng dụng có thể là:

~~~mermaid
flowchart TB
    A["Issue credential A<br/>lease còn hiệu lực"] --> POOLA["DataSource / Pool A"]
    POOLA --> Q["Giao dịch đang xử lý"]
    A --> WATCH["Theo dõi lease TTL<br/>renew / rotate sớm"]
    WATCH -->|"Gia hạn được"| KEEP["Renew A theo giới hạn"]
    KEEP --> POOLA
    WATCH -->|"Không thể renew / chủ động rotate"| B["Issue credential B"]
    B --> POOLB["Tạo Pool B với credential B"]
    POOLB --> SWITCH["Chuyển traffic/kết nối mới sang B"]
    Q --> DRAIN["Drain Pool A và xử lý transaction"]
    SWITCH --> DRAIN
    DRAIN --> REVOKE["Revoke / expire A<br/>theo kế hoạch"]
~~~

Những điểm phải tự thiết kế:

- Một số database có thể giữ connection cũ sau khi account bị thu hồi; không suy luận mọi socket tự đóng tức thì.
- Thay đổi property password trong `Environment` **không tự thay HikariCP pool** hoặc username/password đã cấp cho client.
- Cần thời gian chồng lấp giữa A và B nếu backend và chính sách cho phép, tránh chuyển ở giây cuối trước TTL.
- Khi Vault mất kết nối, một credential đã hết hạn không trở thành hợp lệ chỉ vì nằm trong cache.
- Việc cấp credential mới có thể tạo side effect; retry phải dựa trên semantics của engine.

**Tiêu chí hoàn thành giai đoạn 5B:** có integration test với database thử nghiệm chứng minh ứng dụng tiếp tục tạo connection mới bằng credential mới khi lease cũ hết hạn/thu hồi, và xử lý transaction còn mở theo quy tắc đã định.

## 9. Giai đoạn 6 — Mở rộng sang Transit và PKI theo nhu cầu

Sau khi hiểu KV/token/lease, ứng dụng có thể cần chức năng mật mã hoặc chứng chỉ. Hai nhóm này **không nên ép thành API key tĩnh trong một property**.

### 9.1. Transit encryption

Transit giữ key material phía Vault và nhận yêu cầu encrypt/decrypt/rewrap/sign/verify tùy loại key. Đối với mã hóa, dữ liệu plaintext cần được gửi đúng payload (thường base64 của bytes gốc), Vault trả ciphertext và ứng dụng lưu ciphertext trong datastore nghiệp vụ.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class CustomerDataEncryptor {

    private final VaultOperations vault;

    public CustomerDataEncryptor(VaultOperations vault) {
        this.vault = vault;
    }

    public String encrypt(String plaintext) {
        String input = Base64.getEncoder().encodeToString(
            plaintext.getBytes(StandardCharsets.UTF_8));

        VaultResponse response = vault.write(
            "transit/encrypt/orders-pii", Map.of("plaintext", input));

        if (response == null) {
            throw new IllegalStateException("Transit did not return a result");
        }
        Object raw = response.getRequiredData().get("ciphertext");
        if (!(raw instanceof String ciphertext) || ciphertext.isBlank()) {
            throw new IllegalStateException("Transit ciphertext is missing");
        }
        return ciphertext;
    }
}
~~~

Policy chỉ encrypt với key có sẵn:

~~~hcl
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

`orders-service` không có quyền `decrypt` nếu không cần giải mã. Base64 trong request **không phải mã hóa bảo mật**; plaintext vẫn hiện diện trong JVM và được truyền qua TLS. Nếu Transit lỗi, đừng tự lưu plaintext. Khi rotate Transit key, ciphertext cũ không tự biến thành version mới trong database; cần chính sách decrypt version và quy trình rewrap/re-encrypt nếu muốn thay.

### 9.2. PKI cho mTLS

PKI secrets engine có thể phát hành chứng chỉ X.509 theo role với giới hạn tên, TTL và trust chain. Tùy luồng:

- `pki/issue/<role>` có thể để Vault tạo private key và certificate, làm private key có mặt trong response mà Java phải bảo vệ.
- `pki/sign/<role>` có thể ký CSR được tạo từ private key giữ ở workload/HSM/keystore, tránh đưa private key đó lên Vault.

Certificate có hạn hiệu lực; ứng dụng cần xin mới **trước hạn**, cập nhật TLS context/keystore, tạo kết nối mới và xử lý kết nối đang dùng. Đây là **vòng đời certificate**, không phải gia hạn token Vault hay renew database lease.

| Nhóm chức năng | Đối tượng hết hạn/rotate | Thành phần tiêu thụ phải cập nhật |
|---|---|---|
| KV API key | Credential do bên thứ ba cấp | HTTP client/cache và thông tin xác thực gửi đối tác |
| Database | Credential có lease TTL | DataSource, connection pool, transaction routing |
| Transit | Key version, decrypt policy | Quy trình rewrap/ciphertext migration và quyền crypto |
| PKI | Certificate và private key theo workflow | TLS context, certificate chain, connections |

**Tiêu chí hoàn thành giai đoạn 6:** Transit được gọi bằng policy tối thiểu và không có đường fallback plaintext; certificate mới thật sự được nạp vào TLS client trước khi certificate cũ hết hạn.

## 10. Giai đoạn 7 — Quan sát và kiểm toán toàn bộ vòng đời

Một hệ thống chỉ có metric “Vault request OK” sẽ không biết khi nào API key ở đối tác sắp bị thu hồi hoặc database pool vẫn dùng credential cũ. Cần quan sát ở **nhiều lớp**.

| Lớp | Tín hiệu hữu ích | Điều không được đưa vào log/metrics |
|---|---|---|
| Spring Vault client | Latency, timeout, status `403`/`404`/`5xx`, login/renew errors | Vault token, request payload, plaintext, private key |
| KV/app cache | Cache refresh time, số instance đã nhận version, downstream auth failures | API key thực hoặc nguyên response KV |
| Database/pool | Lease gần hết TTL, cấp credential mới, pool rollover, connection auth failures | Username/password thật nếu bị coi nhạy cảm; đặc biệt password |
| Transit/PKI | Encrypt/decrypt errors, certificate expiry, TLS reload success | Transit plaintext, private key, CSR chứa dữ liệu nhạy cảm không cần thiết |
| Vault server | Auth denials, ACL failures, audit events, cluster health, seal state, engine latency | Audit sink/log không được mở rộng quyền hoặc sao chép tùy tiện |
| Hệ thống đích | Payment 401, DB auth failures, mTLS handshake errors | Full headers chứa bearer token/API key |

Vault audit devices được vận hành phía server. Spring Vault client có thể ghi nhận loại hoạt động và correlation metadata an toàn, nhưng **không tự bật audit devices**. Audit cho biết request tới Vault, còn log và trace phía Java vẫn cần được scrub để tránh tiết lộ dữ liệu sau khi được phép đọc.

### 10.1. Cảnh báo theo hành động

Đặt cảnh báo để hành động kịp thời, ví dụ:

- **Tỷ lệ login/403 tăng:** điều tra thay đổi workload role/policy, đừng tự nâng quyền.
- **Lease/credential gần hạn mà chưa cấp mới:** kích hoạt kiểm tra rotation và pool readiness.
- **Nhiều payment 401 sau khi rotate:** kiểm tra client dùng key cũ hay key mới chưa được kích hoạt.
- **Certificate gần hết hạn:** cấp lại và xác minh TLS context đã chuyển.
- **Vault sealed/5xx/timeout tăng:** SRE/Vault Ops xử lý tình trạng cluster; App Dev hạn chế retry storm.

Không dùng giá trị API key hoặc Vault token làm label để “phân biệt instance”; label phải đủ an toàn để hiển thị trong dashboards và alerts.

## 11. Kiểm thử tích hợp: các mốc phải chứng minh bằng hệ thống thật

Mock `VaultOperations` hữu ích cho unit test kiểm tra việc chọn path, xử lý field null và không leak response. Nhưng mock không chứng minh policy, auth role, KV version, lease hoặc Vault server thực sự chạy đúng. Hãy dùng Vault test instance/container cô lập và secret giả; các bài dùng Database/PKI cần backend thử nghiệm tương ứng.

| Giai đoạn | Case tích hợp | Kết quả mong đợi |
|---|---|---|
| **1. Auth/TLS** | Workload đúng/sai danh tính; CA trust/hostname | Đúng role login được, identity sai bị từ chối; TLS chuẩn |
| **2. KV v2** | Đọc key/field hợp lệ, sai mount, thiếu key | Đọc đúng dữ liệu giả, không nhầm `data/`; lỗi được phân loại |
| **1–2. Policy** | Token chỉ có `read` một key, truy cập key khác | Đọc được key orders, key khác bị `403` |
| **3. Runtime error** | Vault timeout, 429/5xx, TLS lỗi | Retry hữu hạn, fail closed khi cần, không lộ secret |
| **4. Rotation KV** | Ghi key B, refresh các instance, revoke key A giả | Tất cả instance dùng B; key cũ không còn được chấp nhận |
| **5A. Token TTL** | Token hết hạn/revoked độc lập với secret | Session/auth xử lý renew/re-login hoặc thất bại đúng chính sách |
| **5B. Database lease** | TTL ngắn, renew hoặc cấp mới, revoke credential cũ | Pool kết nối mới dùng credential mới, transaction xử lý theo kế hoạch |
| **6. Transit** | Token chỉ encrypt, thử decrypt | Encrypt thành công; decrypt bị từ chối khi không có quyền |
| **6. PKI** | Certificate thời hạn ngắn, thay TLS context | Kết nối mới chứng minh certificate mới được nạp |
| **7. Observability** | Kiểm tra log/trace/audit của từng tình huống | Có metadata cần thiết; không xuất hiện secret/token/plaintext |

### 11.1. Một kịch bản tích hợp theo thứ tự triển khai

~~~text
GIVEN:
  Vault test instance bật KV v2 mount secret/
  Key logic prod/orders/payment chứa api-key giả
  Workload role orders-role chỉ có quyền read path đó
  Java VaultOperations được cấu hình đúng auth và TLS

WHEN:
  PaymentKeyProvider.requiredPaymentKey() được gọi
THEN:
  Ứng dụng nhận đúng api-key giả
  Không có api-key trong log hoặc REST response
  Token role khác không đọc được key này

WHEN:
  Test đổi phiên bản key và kích hoạt refresh như thiết kế
THEN:
  Ứng dụng sử dụng key mới tại downstream test provider
  Key cũ chỉ bị vô hiệu khi test provider thực hiện revoke

WHEN:
  Vault bị ngắt kết nối hoặc token bị revoke
THEN:
  Retry hữu hạn; ứng dụng báo lỗi đúng tầng
  Không fallback sang credential mặc định hay plaintext
~~~

Kiểm thử cả *negative cases* rất quan trọng: auth bị từ chối, policy thiếu, key không tồn tại và rotation chưa hoàn tất thường tiết lộ lỗi kiến trúc nhanh hơn một happy-path test duy nhất.

### 11.2. Quy tắc release cho một integration mới

Trước production, cần có bằng chứng:

1. **Hợp đồng đã chốt:** danh tính workload, mount/path, schema, ACL và owner rotation.
2. **Quyền đã thử:** service chỉ làm được thao tác cần thiết, không đọc được key/engine khác.
3. **Vòng đời đã thử:** ít nhất một lần thay secret và một lần mô phỏng revoked/expired.
4. **Lỗi đã thử:** Vault timeout, TLS issue và thiếu secret có phản ứng hữu hạn, có quan sát.
5. **Dữ liệu được bảo vệ:** không có secret thật trong Git/image/log/trace/metric/REST payload.
6. **Runbook có owner:** biết ai sửa policy, ai cấp key mới, ai đổi datasource và ai khôi phục Vault cluster.

## 12. Lộ trình thực hành mini-project: `orders-service`

Để học theo chiều tăng dần, xây một mini-project với ba adapter:

~~~text
orders-service
  domain/
    PaymentService                # nghiệp vụ không biết Vault API path
  infrastructure/
    vault/
      PaymentKeyProvider          # KV v2, trả field api-key
      DatabaseCredentialSource    # đọc credential theo role, quản lý lease
      CustomerDataEncryptor       # Transit encrypt theo input
    payment/
      PaymentGatewayClient        # HTTP client dùng API key
    persistence/
      OrdersDataSourceManager     # thay credential và connection pool
  config/
    VaultClientConfiguration      # endpoint, TLS, workload auth
  tests/
    VaultIntegrationTests         # kiểm thử trên Vault test instance
~~~

Các tên package/class chỉ minh họa cách chia trách nhiệm, không phải bộ source đã được tạo. Mỗi bước có một tiêu chí nhỏ và có thể kiểm chứng:

| Bước | Việc thực hành | Chỉ chuyển bước khi |
|---|---|---|
| **A** | Tạo môi trường Vault test, KV v2, auth role và policy read | Service đọc được key của mình và bị cấm đọc key khác |
| **B** | Viết `PaymentKeyProvider`, inject vào `PaymentService` | Kết quả thanh toán không chứa API key, thiếu field báo lỗi |
| **C** | Thêm timeout/error handling và telemetry | Test Vault timeout/403/404 đạt tiêu chí |
| **D** | Thử phát hành key B và chuyển ứng dụng | Tất cả instance test dùng B, không còn dùng A |
| **E** | Chuyển DB credential test sang engine động nếu phù hợp | Pool chuyển qua account mới khi lease A hết hạn |
| **F** | Bổ sung Transit nếu cần mã hóa trước khi lưu | Encrypt thành công, không lưu plaintext khi Vault lỗi |
| **G** | Bổ sung PKI nếu cần mTLS động | Certificate mới được nạp vào runtime trước hạn |
| **H** | Chạy test suite và diễn tập sự cố | Không rò secret, owner/runbook và alerts hoạt động |

### Một số quyết định thiết kế phải ghi lại

- **Lấy khi startup hay runtime?** Startup giúp tạo bean nhưng có thể làm dịch vụ không boot khi Vault gián đoạn; runtime cho phép thao tác tùy input nhưng tăng network dependencies. Có thể kết hợp với cache có giới hạn.
- **Chọn trực tiếp `VaultTemplate` hay Spring Cloud Vault?** API trực tiếp cho operation/lease/PKI/Transit ở runtime; Spring Cloud Vault cho externalized config. Không mặc định property source tự refresh mọi bean.
- **Từ chối hay cho phép degraded mode?** Tác vụ bắt buộc dùng secret hợp lệ nên fail closed; degraded mode chỉ có khi nghiệp vụ và chính sách cho phép rõ ràng.
- **Ai thay credential?** Khi secret đổi, client đang dùng nó phải cập nhật: HTTP client, HikariCP, TLS context hoặc một adapter khác.
- **Kiểm thử trên backend nào?** KV/policy cần Vault thật; lease DB cần database test; PKI cần kiểm tra cert chain/TLS handshake; chỉ mock client không đủ.

## 13. Những ngộ nhận phổ biến trên lộ trình

| Ngộ nhận | Điều cần nhớ |
|---|---|
| “Thêm `spring-vault-core` là có Vault server” | Thư viện chỉ là client; Vault server/auth/engines/policies phải được triển khai và cấu hình |
| “Login Vault thành công là đọc được mọi secret” | Mỗi request bị kiểm tra theo token, policy, path và capability |
| “KV v2 version là TTL của API key” | Version lưu lịch sử tại Vault, không thu hồi key ở nhà cung cấp |
| “Renew token là renew DB credential” | Vault token và secret lease là hai vòng đời |
| “`SecretLeaseContainer` tự thay datasource” | Nó có thể theo dõi lease/rotation đã đăng ký; ứng dụng vẫn phải cập nhật pool/client |
| “Đổi password trong `Environment` là connection pool đổi theo” | Bean/pool đã khởi tạo có thể giữ giá trị cũ, cần cơ chế refresh/rebuild |
| “Transit mã hóa và giữ toàn bộ dữ liệu” | Transit xử lý mật mã/key; ciphertext nghiệp vụ do ứng dụng lưu |
| “PKI cấp cert mới thì mọi TLS connection đã đổi cert” | Cần nạp lại context và kiểm soát connection lifecycle |
| “Timeout thì retry mọi thao tác vô hạn” | Issue/write có side effect; cần giới hạn và xét idempotency |
| “Vault audit chứng minh Java không làm lộ secret” | Server audit không thay kiểm thử bảo vệ heap/log/trace/REST response |

## 14. Câu hỏi tự kiểm tra và tổng kết

Hãy tự trả lời:

1. Sau khi `PaymentKeyProvider.requiredPaymentKey()` trả đúng giá trị, còn những điều kiện nào phải được xác minh trước production?
2. Với KV v2 mount `secret` và key logic `prod/orders/payment`, Java API, HTTP path và ACL policy path tương ứng là gì?
3. Vì sao rotation API key phải phối hợp **nhà phát hành**, **Vault** và **mọi instance đang sử dụng**?
4. Nếu token Vault còn 20 phút nhưng lease DB đã hết, việc renew token có giúp pool mở connection mới bằng credential cũ không?
5. `SecretLeaseContainer` có thể giúp gì và phần nào phải do ứng dụng tích hợp với HikariCP?
6. Tại sao không nên dùng cache vô hạn cho secret tĩnh, và không thể dùng cache để “kéo dài” credential đã hết lease?
7. Khi Transit unavailable, hành vi nào phù hợp với dữ liệu bắt buộc mã hóa?
8. Trong một integration test, phải chứng minh điều gì về negative policy, rotation, lỗi mạng và secret leakage?

Lộ trình áp dụng Spring Vault có một mạch chính: **xác định bí mật → thiết lập danh tính và quyền → đọc bằng Java API → xử lý lỗi và bảo vệ dữ liệu → thay đổi/thu hồi có kiểm soát → kiểm thử liên tục**. HashiCorp Vault server cung cấp auth, policy, secrets engines, TTL và audit; Spring Vault cung cấp client abstraction; ứng dụng chịu trách nhiệm với bí mật đã nhận và các tài nguyên đang tiêu thụ nó. Khi ba phần phối hợp, việc quản lý secret tập trung mới giảm rủi ro và nâng khả năng vận hành.

## Tài liệu tham khảo chính thức

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Secret Lease Container](https://docs.spring.io/spring-vault/reference/vault/secret-lease-container.html)
- [Spring Vault — Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Cloud Vault — Reference Documentation](https://docs.spring.io/spring-cloud-vault/reference/)
- [HashiCorp Vault — KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Token Concepts](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [HashiCorp Vault — Lease Concepts](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
- [HashiCorp Vault — ACL Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)

> **Lưu ý phiên bản:** API Spring Vault, Spring Cloud Vault, Vault server, hành vi token/lease và lựa chọn auth thay đổi theo phiên bản và cách triển khai. Code, policy path, TTL và tên role trong bài đều là ví dụ học tập. Trước khi áp dụng production, kiểm tra phiên bản dependency, cấu hình thật và chạy kiểm thử tích hợp trên môi trường cô lập.
